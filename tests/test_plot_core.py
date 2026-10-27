"""The chart core (``vidgen.plotcore``, Phase W Step 222): tick values, number formats, axes
(linear, log, symlog, reversed, broken), CSV tables with units, and the figure layout. No manim."""

from __future__ import annotations

import math
import re
import subprocess
import sys

import numpy as np
import pytest

from vidgen.errors import VidgenError
from vidgen.plotcore import (
    Axis,
    AxisSpec,
    PanelInput,
    Rect,
    approx_measure,
    axis_title,
    build_axis,
    check_tick_format,
    clip_polyline,
    default_linthresh,
    exponent_of,
    label_stride,
    layout_axes,
    layout_figure,
    linear_ticks,
    log_ticks,
    plain_number,
    prefixed_unit_problem,
    read_table,
    sci_number,
    si_number,
    split_header,
    symlog_inverse,
    symlog_ticks,
    symlog_transform,
    tick_labels,
)
from vidgen.plotcore.numbers import decimals_needed

# ----- ticks -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lo", "hi", "n", "ticks"),
    [
        (0, 9.3, 6, [0, 2, 4, 6, 8, 10]),
        (-3.2, 7.1, 6, [-5, -2.5, 0, 2.5, 5, 7.5]),
        (-7.1, -3.2, 6, [-8, -7, -6, -5, -4, -3]),
        (1e-9, 7e-9, 6, [0, 2e-9, 4e-9, 6e-9, 8e-9]),
        (1e9, 1e9 + 3, 6, [1e9, 1e9 + 1, 1e9 + 2, 1e9 + 3]),
        (0, 3.2e7, 5, [0, 1e7, 2e7, 3e7, 4e7]),
        (5, 5, 6, [4.5, 4.75, 5, 5.25, 5.5]),
        (0, 0, 6, [-1, -0.5, 0, 0.5, 1]),
    ],
)
def test_linear_ticks_are_round_and_cover_the_range(lo: float, hi: float, n: int, ticks: list[float]) -> None:
    got = linear_ticks(lo, hi, n)
    assert got == pytest.approx(ticks, rel=1e-12, abs=1e-24)
    assert len(got) <= n and got[0] <= min(lo, hi) and got[-1] >= max(lo, hi)
    assert all(t == float(f"{t:.12g}") for t in got)   # no float noise (0.30000000000000004)


def test_linear_ticks_inside_a_fixed_domain() -> None:
    assert linear_ticks(0.13, 0.87, 6, inside=True) == [0.2, 0.4, 0.6, 0.8]
    assert linear_ticks(-2.41, 2.41, 7, inside=True) == [-2, -1, 0, 1, 2]
    ticks = linear_ticks(1.37, 1.52, 4, inside=True)
    assert 2 <= len(ticks) <= 4 and all(1.37 <= t <= 1.52 for t in ticks)


def test_log_ticks_decades_and_minor() -> None:
    major, minor = log_ticks(3, 4e7, 6)
    assert major == [1, 100, 1e4, 1e6, 1e8] and minor == []           # every 2nd decade
    major, minor = log_ticks(1, 1000, 6)
    assert major == [1, 10, 100, 1000]
    assert 2 in minor and 9 in minor and 20 in minor                 # 2-9 per decade
    major, minor = log_ticks(2, 80, 6)
    assert major == [2, 5, 10, 20, 50, 100]                          # 1-2-5 within two decades
    major, _ = log_ticks(1e-12, 1e-3, 6)
    assert major == pytest.approx([1e-12, 1e-10, 1e-8, 1e-6, 1e-4, 1e-2], rel=1e-12)
    major, _ = log_ticks(0.02, 0.7, 6, inside=True)
    assert all(0.02 <= t <= 0.7 for t in major)
    with pytest.raises(VidgenError, match="positive"):
        log_ticks(0, 10)


def test_symlog_transform_and_ticks() -> None:
    for v in (-3e4, -1.0, -0.002, 0.0, 0.0005, 1.0, 7e5):
        assert symlog_inverse(symlog_transform(v, 1e-3), 1e-3) == pytest.approx(v, rel=1e-12, abs=1e-15)
    assert symlog_transform(1e-3, 1e-3) == 1.0 and symlog_transform(1.0, 1e-3) == pytest.approx(4.0)
    ticks = symlog_ticks(-1000, 1e5, 1.0, 7)
    assert 0.0 in ticks and ticks[0] <= -1000 and ticks[-1] >= 1e5 and len(ticks) <= 7
    assert all(abs(t) in (0, 1) or math.log10(abs(t)) == int(math.log10(abs(t))) for t in ticks)
    assert default_linthresh([0, 0.5, -1e4]) == 10.0            # at most 1/1000 of the largest
    assert default_linthresh([0.03, -2]) == 0.01
    with pytest.raises(VidgenError, match="linthresh"):
        symlog_ticks(-1, 1, 0)


# ----- numbers -----------------------------------------------------------------------------------


def test_plain_sci_and_si_numbers() -> None:
    assert plain_number(-2.5, 1) == "−2.5" and plain_number(-0.04, 1) == "0.0" and plain_number(3, 0) == "3"
    assert sci_number(2.5e-3) == "2.5 × 10⁻³"
    assert sci_number(1e6) == "10⁶" and sci_number(-1e6) == "−10⁶" and sci_number(0) == "0" and sci_number(4.2) == "4.2"
    assert sci_number(9.9996e5, 3) == "10⁶"                     # rounding carries into the next decade
    assert si_number(2.5e-6, "s") == "2.5 µs" and si_number(1.25e11, "eV") == "125 GeV" and si_number(1e3, "Hz") == "1 kHz"
    assert exponent_of(1000) == 3 and exponent_of(999.9999) == 2 and exponent_of(-0.002) == -3
    assert decimals_needed([0, 0.5, 1]) == 1 and decimals_needed([0.25]) == 2 and decimals_needed([1e-9], 8) == 8


def test_tick_labels_auto_moves_a_power_of_ten_into_the_title() -> None:
    big = tick_labels([0, 2e6, 4e6])
    assert big.labels == ["0", "2", "4"] and big.exponent == 6
    small = tick_labels([0, 0.0002, 0.0004])
    assert small.labels == ["0", "200", "400"] and small.exponent == -6
    plain = tick_labels([-2.5, 0, 2.5, 5])
    assert plain.labels == ["−2.5", "0.0", "2.5", "5.0"] and plain.exponent == 0
    narrow = tick_labels([1e9, 1e9 + 1, 1e9 + 2])
    assert narrow.labels == ["1000000000", "1000000001", "1000000002"] and narrow.exponent == 0
    assert tick_labels([1, 10, 100, 1000], scale="log").labels == ["1", "10", "100", "1000"]
    assert tick_labels([1e-9, 1e-6, 1e-3], scale="log").labels == ["10⁻⁹", "10⁻⁶", "10⁻³"]
    assert tick_labels([0.001, 0.01], scale="log").labels == ["0.001", "0.01"]


def test_tick_label_formats() -> None:
    assert tick_labels([0, 2e-4], "sci").labels == ["0", "2 × 10⁻⁴"]
    assert tick_labels([0, 1.5, 3], "plain").labels == ["0.0", "1.5", "3.0"]
    si = tick_labels([0, 2e-6, 4e-6], "si", "s")
    assert si.labels == ["0", "2", "4"] and si.title_unit == "µs"
    assert tick_labels([1e3, 1e4, 1e5], "si", "Hz", scale="log").labels == ["1 kHz", "10 kHz", "100 kHz"]
    assert tick_labels([0, 0.5, -1], "{:.2f}").labels == ["0.00", "0.50", "−1.00"]
    with pytest.raises(VidgenError, match="already has the prefix 'k'"):
        tick_labels([0, 1000], "si", "km")
    assert prefixed_unit_problem("m") is None and prefixed_unit_problem("eV") is None
    assert "write the base unit 'eV'" in prefixed_unit_problem("MeV")
    assert "needs a unit" in prefixed_unit_problem("")
    assert "does not take SI prefixes" in prefixed_unit_problem("min")
    for bad in ("loud", "{:q}"):
        with pytest.raises(ValueError):
            check_tick_format(bad)
    assert check_tick_format("{:.1f}") == "{:.1f}"


def test_axis_titles() -> None:
    assert axis_title("time", "s") == "time (s)"
    assert axis_title("distance", "km", 6) == "distance (10⁶ km)"
    assert axis_title("count", "", 3) == "count (× 10³)"
    assert axis_title("count") == "count" and axis_title("", "m") == "m"


# ----- axes --------------------------------------------------------------------------------------


def test_build_axis_log_reversed_and_large() -> None:
    a = build_axis([3, 7, 100], AxisSpec(scale="log", label="activity", unit="Bq"))
    assert a.ticks == (2, 5, 10, 20, 50, 100) and a.title == "activity (Bq)" and 3 in a.minor
    assert a.fraction(2) == pytest.approx(0) and a.fraction(100) == pytest.approx(1)
    assert a.fraction(math.sqrt(200)) == pytest.approx(0.5)
    r = build_axis([0, 10], AxisSpec(reversed=True))
    assert r.fraction(0) == 1.0 and r.fraction(10) == 0.0
    d = build_axis([0, 3e7], AxisSpec(label="distance", unit="km"))
    assert d.title == "distance (10⁶ km)" and d.labels[-1] == "30"
    fixed = build_axis([0.3, 0.9], AxisSpec(lo=0.25, hi=1.0))
    assert (fixed.lo, fixed.hi) == (0.25, 1.0) and all(0.25 <= t <= 1 for t in fixed.ticks)


def test_build_axis_symlog() -> None:
    a = build_axis([-2, 0, 30], AxisSpec(scale="symlog", linthresh=1e-3, unit="A", format="si"))
    assert a.lo <= -2 and a.hi >= 30 and 0.0 in a.ticks
    assert "1 mA" in a.labels and a.title == ""
    assert a.fraction(0) == pytest.approx((0 - a.transform(a.lo)) / (a.transform(a.hi) - a.transform(a.lo)))


def test_broken_axis_maps_pieces_with_a_gap() -> None:
    b = build_axis([0, 5, 95, 100], AxisSpec(breaks=((10, 90),)))
    assert b.segments == ((0, 10), (90, 100)) and b.ticks == (0, 5, 10, 90, 95, 100)
    assert b.fraction(10) < b.fraction(90) and b.fraction(90) - b.fraction(10) == pytest.approx(0.04)
    assert b.fraction(0) == 0 and b.fraction(100) == 1 and not b.contains(50) and b.contains(95)
    assert b.break_fractions() == [pytest.approx(0.5)]


@pytest.mark.parametrize(
    ("values", "spec", "message"),
    [
        ([0, 5], AxisSpec(scale="log"), "log scale needs positive values, but the data has 0"),
        ([1, 5], AxisSpec(lo=3, hi=1), r"max \(1\) must be greater than min \(3\)"),
        ([1, 5], AxisSpec(hi=4), "the value 5 lies outside max 4"),
        ([1, 50, 99], AxisSpec(breaks=((10, 90),)), "the value 50 lies inside the break"),
        ([1, 99], AxisSpec(scale="log", breaks=((10, 90),)), "breaks need a linear scale"),
        ([1, 99], AxisSpec(breaks=((10, 50), (40, 90))), "overlap"),
        ([1, 5], AxisSpec(breaks=((10, 90),)), "data on both sides"),
        ([1, 5], AxisSpec(linthresh=1), "linthresh is for scale: symlog"),
        ([1, 5], AxisSpec(format="si", unit="ms"), "already has the prefix 'm'"),
        ([1, 5], AxisSpec(scale="cubic"), "not one of linear, log, symlog"),
    ],
)
def test_axis_spec_problems(values: list[float], spec: AxisSpec, message: str) -> None:
    problems = spec.problems(values, "y")
    assert problems and problems[0].startswith("y: ")
    assert any(re.search(message, p) for p in problems), problems
    with pytest.raises(VidgenError):
        build_axis(values, spec)


# ----- tables ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "parts"),
    [("time (s)", ("time", "s")), ("E [MeV]", ("E", "MeV")), ("v / km/s", ("v", "km/s")), ("count", ("count", "")),
     ("f(x)", ("f(x)", "")), ("rate (s⁻¹)", ("rate", "s⁻¹"))],
)
def test_split_header(header: str, parts: tuple[str, str]) -> None:
    assert split_header(header) == parts


def test_read_table_with_units_comments_and_gaps() -> None:
    text = "# a comment\ntime (s); signal [mV]\n0; 1.5\n1; −2e-3\n\n2; NA\n"
    t = read_table(text, "d.csv")
    assert t.names() == ["time", "signal"]
    sig = t.column("signal")
    assert sig.unit == "mV" and sig.values[:2] == (1.5, -0.002) and math.isnan(sig.values[2])
    assert t.column("Signal [mV]").name == "signal"           # by full header, any case
    tabs = read_table("a\tb\n1\t2\n", "t.tsv")
    assert tabs.column("b").values == (2.0,)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "has no rows"),
        ("a, b\n", "header but no data rows"),
        ("a, b\n1, 2\n3\n", r"d.csv, line 3: 1 values, but the header names 2 columns"),
        ("a, b\n1, x\n", r"d.csv, line 2, column 'b': 'x' is not a number"),
        ("a, b\n1, 2,5\n", "3 values"),
        ("a; b\n1; 2,5\n", r"'2,5' is not a number \(use a dot for decimals\)"),
        ("a, a\n1, 2\n", "the column 'a' appears twice"),
        ("a, \n1, 2\n", "column 2 has no name"),
        ("a, b\n1, \n2, NA\n", "the column 'b' has no numbers"),
    ],
)
def test_read_table_errors(text: str, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        read_table(text, "d.csv")


def test_unknown_column_suggests() -> None:
    t = read_table("time (s), activity (Bq)\n0, 1\n", "d.csv")
    with pytest.raises(VidgenError, match=r"d.csv has no column 'activty' \(columns: time, activity\); did you mean 'activity'\?"):
        t.column("activty", "series 'a' y")


# ----- layout ------------------------------------------------------------------------------------


AREA = Rect(-7.0, -4.0, 7.0, 3.0)


def two_panels(arrange: str = "rows") -> list:
    spec_x = AxisSpec(label="time", unit="s")
    return [
        PanelInput((0, 1, 2), (0, 10, 20), spec_x, AxisSpec(label="x", unit="m")),
        PanelInput((0, 2.5), (5, -5), spec_x, AxisSpec(label="v", unit="m/s")),
    ]


def test_layout_is_deterministic() -> None:
    a = layout_figure(AREA, two_panels(), approx_measure())
    b = layout_figure(AREA, two_panels(), approx_measure())
    assert a == b


def test_stacked_panels_share_x_and_line_up() -> None:
    top, bottom = layout_figure(AREA, two_panels(), approx_measure())
    assert top.x == bottom.x and top.x.ticks[-1] >= 2.5               # one x axis from both panels
    assert not top.x_labels and top.x_title is None and bottom.x_labels and bottom.x_title.text == "time (s)"
    assert top.plot.x0 == bottom.plot.x0 and top.plot.x1 == bottom.plot.x1
    assert top.plot.y0 > bottom.plot.y1                                 # stacked with a gap
    assert top.y_title.text == "x (m)" and bottom.y_title.text == "v (m/s)"
    for lay in (top, bottom):
        for lab in [*lay.x_labels, *lay.y_labels, *(t for t in (lay.x_title, lay.y_title) if t)]:
            assert AREA.contains(lab.x - lab.width / 2, lab.y - lab.height / 2, 1e-6) and AREA.contains(lab.x + lab.width / 2, lab.y + lab.height / 2, 1e-6), lab


def test_panels_side_by_side_share_y() -> None:
    left, right = layout_figure(AREA, two_panels(), approx_measure(), arrange="columns")
    assert left.y == right.y and left.y_labels and not right.y_labels and right.y_title is None
    assert left.plot.y0 == right.plot.y0 and left.plot.x1 < right.plot.x0
    assert left.x_labels and right.x_labels


def test_unshared_panels_and_weights() -> None:
    top, bottom = layout_figure(AREA, two_panels(), approx_measure(), share=False, weights=[2, 1])
    assert top.x != bottom.x and top.x_labels and bottom.x_labels
    assert top.plot.height == pytest.approx(2 * bottom.plot.height)
    with pytest.raises(VidgenError, match="weights"):
        layout_figure(AREA, two_panels(), approx_measure(), weights=[1])


def test_equal_aspect_widens_the_axis_with_room() -> None:
    panel = PanelInput((-1, 1), (-1, 1), AxisSpec(exact=True, margin=0.05), AxisSpec(exact=True, margin=0.05))
    (lay,) = layout_figure(AREA, [panel], approx_measure(), aspect="equal")
    per_x = lay.plot.width / (lay.x.hi - lay.x.lo)
    per_y = lay.plot.height / (lay.y.hi - lay.y.lo)
    assert per_x == pytest.approx(per_y, rel=1e-6)
    assert lay.x.hi - lay.x.lo > 2.1 and lay.y.lo == pytest.approx(-1.1)
    fixed = PanelInput((-1, 1), (-1, 1), AxisSpec(lo=-1, hi=1), AxisSpec(lo=-1, hi=1))
    (shrunk,) = layout_figure(AREA, [fixed], approx_measure(), aspect="equal")
    assert shrunk.plot.width == pytest.approx(shrunk.plot.height) and (shrunk.x.lo, shrunk.x.hi) == (-1, 1)
    with pytest.raises(VidgenError, match="one panel"):
        layout_figure(AREA, two_panels(), approx_measure(), aspect="equal")


def test_tick_labels_are_thinned_so_none_touch() -> None:
    panel = PanelInput(tuple(range(0, 1_000_001, 1000)), (0, 1), AxisSpec(max_ticks=21, format="plain"), AxisSpec())
    (lay,) = layout_figure(Rect(-2, -2, 2, 2), [panel], approx_measure())
    xs = sorted(lay.x_labels, key=lambda lab: lab.x)
    assert len(xs) < len(lay.x.ticks)
    assert all(b.x - b.width / 2 > a.x + a.width / 2 for a, b in zip(xs, xs[1:]))
    assert xs[-1].text == lay.x.labels[-1]                     # the end of the axis keeps its label
    assert label_stride([0, 1, 2, 3], [0.5] * 4, 0.6) == [0, 2]
    assert label_stride([0, 1, 2, 3], [0.5] * 4, 0.6, keep_last=True) == [0, 3]


def test_layout_axes_takes_hand_built_axes() -> None:
    """Step 227: a panel whose ticks the caller placed (the PCR trace: cycle numbers between the
    ticks of a cycle, three named temperatures), laid out like a figure's panel."""
    x = Axis("linear", 0.0, 9.0, (1.5, 4.5, 7.5), ("cycle 1", "cycle 2", "cycle 3"))
    y = Axis("linear", 45.0, 100.0, (50.0, 72.0, 95.0), ("anneal 50", "extend 72", "denature 95"), title="temperature (°C)")
    lay = layout_axes(Rect(-3, -1.5, 3, 1.5), x, y, approx_measure(height=0.2))
    assert lay.x is x and lay.y is y and lay.x_title is None and lay.y_title.text == "temperature (°C)"
    assert lay.frame_x(4.5) == pytest.approx(lay.plot.center[0]) and lay.plot.x0 > -3 + 0.11 * 11   # room for "denature 95"
    assert [lab.text for lab in lay.x_labels] == ["cycle 1", "cycle 2", "cycle 3"]
    assert lay == layout_axes(Rect(-3, -1.5, 3, 1.5), x, y, approx_measure(height=0.2))   # deterministic


def test_clip_polyline() -> None:
    box = Rect(0, 0, 1, 1)
    runs = clip_polyline(np.array([[-1, 0.5, 0], [0.5, 0.5, 0], [0.5, 2, 0], [0.8, 0.2, 0], [np.nan, np.nan, 0], [0.1, 0.1, 0], [0.2, 0.2, 0]]), box)
    assert len(runs) == 3
    assert runs[0][0][:2] == pytest.approx([0, 0.5]) and runs[0][-1][:2] == pytest.approx([0.5, 1])
    assert runs[1][0][1] == pytest.approx(1) and runs[1][-1][:2] == pytest.approx([0.8, 0.2])
    assert runs[2][:, :2] == pytest.approx(np.array([[0.1, 0.1], [0.2, 0.2]]))
    assert clip_polyline(np.array([[2, 2, 0], [3, 3, 0]]), box) == []


def test_the_core_does_not_import_manim() -> None:
    code = "import sys, vidgen.plotcore; print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
