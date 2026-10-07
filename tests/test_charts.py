"""Step 30: the shared chart helpers (``vidgen.charts``: ticks, number labels, axes, legends,
markers, least squares, title and caption), ``bar_chart`` / ``line_chart`` on them (title in the
header band, theme-sized labels in 9:16), and the ``scatter`` and ``histogram`` scene types."""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import Text, tempconfig

from conftest import minimal_config
from test_actions import beat_total, beats, render
from test_builtin_scenes import cls_of, expected_duration, render_scene
from test_comparison_table import safe_area_of
from vidgen import runtime
from vidgen.charts import (
    ChartAxis,
    auto_legend,
    axis_ticks,
    chart_axes,
    chart_caption,
    chart_label_size,
    chart_legend,
    chart_marker,
    chart_title,
    legend_spot,
    linear_fit,
    sample_path,
    short_number,
    tick_texts,
    value_axis,
)
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.regions import Region, readable_size, region, safe_area
from vidgen.render.worker import frame_size
from vidgen.scenes.histogram import aligned_edges, nice_width
from vidgen.theme import Theme

ROOT = Path(__file__).resolve().parents[1]
FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
SIZES = {"landscape": (160, 90), "portrait": (90, 160)}
POINTS = {"base": [[1.3, 61], [2.7, 64], [6.7, 70, "7B"], [13, 73], [65, 80, "65B"]], "ours": [[1.0, 66], [3.8, 72, "small"], [7.0, 75]]}
VALUES = [12, 15, 17, 18, 21, 22, 22, 23, 25, 26, 27, 28, 29, 30, 31, 31, 32, 33, 34, 35, 38, 40, 43, 48, 55, 67, 88, 120]


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides)))


#: A vertical project: its theme uses the portrait type scale (``large``).
VERTICAL = {"format": {"width": 1080, "height": 1920}}


def overlaps(a: Any, b: Any) -> bool:
    return not (a.get_right()[0] <= b.get_left()[0] or b.get_right()[0] <= a.get_left()[0]
                or a.get_top()[1] <= b.get_bottom()[1] or b.get_top()[1] <= a.get_bottom()[1])


def n_beats(n: int) -> list[dict[str, str]]:
    return [{"text": "one two three four five six seven eight"} for _ in range(n)]


def scatter(**changes: Any) -> Any:
    return cls_of("scatter").validate_params({"series": POINTS, **changes}, Theme())


def histogram(**changes: Any) -> Any:
    raw = {"values": VALUES, **changes}
    return cls_of("histogram").validate_params({k: v for k, v in raw.items() if v is not None}, Theme())


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture(params=["landscape", "portrait"])
def frame(request: pytest.FixtureRequest, make_project) -> Iterator[str]:
    """A project context and Manim's config set to a 16:9 or 9:16 frame."""
    runtime.set_context(Project.load(make_project()))
    w, h = SIZES[request.param]
    fw, fh = frame_size(w, h)
    with tempconfig({"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "verbosity": "ERROR"}):
        yield request.param
    runtime.clear_context()


# ----- numbers ---------------------------------------------------------------------------------------


def test_axis_ticks_linear_and_log() -> None:
    assert axis_ticks(1.2, 2.25) == [1.0, 1.25, 1.5, 1.75, 2.0, 2.25]
    assert axis_ticks(3, 70, 6, log=True) == [2.0, 5.0, 10.0, 20.0, 50.0, 100.0]       # two decades: 1-2-5
    ticks = axis_ticks(0.03, 5000, 6, log=True)
    assert ticks[0] <= 0.03 and ticks[-1] >= 5000 and len(ticks) <= 6
    assert all(math.log10(t) == round(math.log10(t)) for t in ticks)                    # powers of ten
    assert axis_ticks(1, 1e9, 4, log=True) == [1.0, 1e3, 1e6, 1e9]                        # every third decade
    with pytest.raises(VidgenError, match="positive"):
        axis_ticks(0, 10, log=True)


@pytest.mark.parametrize(
    ("value", "decimals", "text"),
    [(1500, None, "1.5k"), (2_000_000, None, "2M"), (3.2e9, None, "3.2B"), (999, None, "999"), (0.05, None, "0.05"), (12, None, "12"),
     (-45_000, None, "-45k"), (1500, 2, "1.50k"), (7, 1, "7.0")],
)
def test_short_number(value: float, decimals: int | None, text: str) -> None:
    assert short_number(value, decimals) == text


def test_tick_texts() -> None:
    assert tick_texts([1.4, 1.6, 1.8]) == ["1.4", "1.6", "1.8"]
    assert tick_texts([0, 1000, 2000]) == ["0", "1,000", "2,000"]
    assert tick_texts([0, 20000, 40000]) == ["0", "20k", "40k"]
    assert tick_texts([0, 2.5e6, 5e6], unit=" €") == ["0 €", "2.5M €", "5.0M €"]
    assert tick_texts([0.5, 1.0], "{:.0%}") == ["50%", "100%"]
    assert tick_texts([0.01, 1, 100, 10000], log=True) == ["0.01", "1", "100", "10k"]


def test_linear_fit() -> None:
    fit = linear_fit([1, 2, 3, 4], [3, 5, 7, 9])
    assert fit.slope == pytest.approx(2) and fit.intercept == pytest.approx(1) and fit.r2 == pytest.approx(1)
    assert fit(10) == pytest.approx(21)
    assert fit.equation() == "y = 2x + 1"
    assert linear_fit([0, 1, 2], [1, 0, -1.5]).equation().startswith("y = −1.25x + ")
    noisy = linear_fit([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
    assert 0 < noisy.r2 < 1
    assert linear_fit([1, 2], [5, 5]).r2 == 1.0
    with pytest.raises(VidgenError, match="two points with different x"):
        linear_fit([1, 1], [2, 3])


def test_value_axis() -> None:
    axis = value_axis([1.48, 2.25], max_ticks=5)
    assert (axis.lo, axis.hi) == (1.25, 2.25) and axis.labels[0] == "1.25"
    fixed = value_axis([3, 7], lo=2, hi=8)
    assert (fixed.lo, fixed.hi) == (2, 8) and all(2 <= t <= 8 for t in fixed.ticks)
    assert value_axis([3, 9], include_zero=True).lo == 0
    log = value_axis([12, 20000], log=True, unit=" rps", title="load")
    assert log.log and log.ticks[0] == 10 and log.labels[-1] == "100k rps" and log.title == "load"
    assert log.fraction(log.lo) == pytest.approx(0) and log.fraction(log.hi) == pytest.approx(1)
    assert log.fraction(1000) == pytest.approx(0.5)    # 10 .. 100k: 1k is halfway in decades
    with pytest.raises(VidgenError, match="positive"):
        value_axis([0, 5], log=True)
    with pytest.raises(VidgenError, match="one label per tick"):
        ChartAxis(0, 1, (0.0, 1.0), ("0",))


# ----- layout helpers (16:9 and 9:16) ------------------------------------------------------------------


def test_chart_axes_fit_the_area_with_readable_labels(frame: str) -> None:
    area = safe_area()
    x = ChartAxis(1, 20, tuple(float(i) for i in range(1, 21)), tuple(str(i) for i in range(1, 21)), title="epoch")
    y = value_axis([0.2, 9.7], title="loss")
    axes = chart_axes(area, x, y, grid="both", lines="xy")
    group = axes.group
    assert area.contains(group, tolerance=1e-6)
    floor = readable_size()
    for label in axes.x_labels + axes.y_labels:
        assert label.font_size >= floor - 1e-6
    assert axes.label_size == chart_label_size() >= floor
    # 20 x labels do not fit side by side in 9:16: thinned to every k-th, never colliding
    lefts = [t.get_left()[0] for t in axes.x_labels]
    rights = [t.get_right()[0] for t in axes.x_labels]
    assert all(r < l2 for r, l2 in zip(rights, lefts[1:]))
    if frame == "portrait":
        assert len(axes.x_labels) < 20
    assert axes.x_title is not None and axes.y_title is not None
    assert axes.y_title.get_bottom()[1] > axes.plot.y1      # the y title stands above the plot
    assert axes.x_title.get_top()[1] < axes.plot.y0
    assert np.allclose(axes.point(1, y.lo)[:2], [axes.plot.x0, axes.plot.y0])
    assert np.allclose(axes.point(20, y.hi)[:2], [axes.plot.x1, axes.plot.y1])
    assert len(axes.lines) == 2 and len(axes.grid) > 0


def test_chart_axes_keep_room_and_label_sizes_follow_the_theme(frame: str) -> None:
    area = safe_area()
    x, y = value_axis([0, 10]), value_axis([0, 5])
    plain = chart_axes(area, x, y)
    roomy = chart_axes(area, x, y, right=1.5, top=1.0)
    assert roomy.plot.x1 == pytest.approx(area.x1 - 1.5) and roomy.plot.y1 == pytest.approx(plain.plot.y1 - 1.0)
    assert plain.plot.x1 < area.x1                     # the last x label, centred on the end, stays inside
    big = chart_axes(area, x, y, size="body")
    assert big.label_size == runtime.current_theme().size("body") > plain.label_size
    assert chart_label_size(8) == pytest.approx(readable_size())   # never below the floor


def test_legend_spot_and_auto_legend(frame: str) -> None:
    plot = Region(-3, -3, 3, 3)
    assert np.allclose(legend_spot((1.0, 0.5), plot, []), [3 - 0.15 - 0.5, 3 - 0.15 - 0.25, 0])   # top right first
    top_right = [[2.5, 2.7, 0]]
    spot = legend_spot((1.0, 0.5), plot, top_right)
    assert spot[0] < 0 and spot[1] > 0                                                            # then top left
    corners = [[2.5, 2.7, 0], [-2.5, 2.7, 0], [2.5, -2.7, 0], [-2.5, -2.7, 0]]
    assert legend_spot((1.0, 0.5), plot, corners) is None
    assert legend_spot((7.0, 0.5), plot, []) is None                                              # too wide
    entries = [("baseline", "primary", "line"), ("sparse", "secondary", "circle"), ("third", "tertiary", "box")]
    legend, centre = auto_legend(entries, plot, [], 6.0)
    assert centre is not None and len(legend) == 2 and plot.contains(legend)                     # framed: box + rows
    assert legend.z_index == 1
    path = sample_path([np.array([-3, 3, 0]), np.array([3, -3, 0])])
    legend, centre = auto_legend(entries, Region(-3, -3, 3, 3), np.vstack([path, sample_path([np.array([-3, -3, 0]), np.array([3, 3, 0])])]), 6.0)
    assert centre is None and len(legend) >= 1                                                   # both diagonals: no free corner
    stacked = chart_legend(entries, 10.0, stack=True)
    assert len(stacked) == 3 and len(chart_legend(entries, 10.0)) == 1


def test_markers_title_and_caption(frame: str) -> None:
    for kind in ("circle", "square", "triangle", "diamond"):
        mark = chart_marker(kind, 0.1, "primary")
        assert 0.15 < max(mark.width, mark.height) < 0.3
    with pytest.raises(VidgenError, match="unknown marker"):
        chart_marker("star", 0.1, "primary")
    title = chart_title("A fairly long chart title that has to wrap in a narrow frame")
    header = region("header")
    assert header.contains(title, tolerance=1e-6)
    assert abs(title.get_center()[0] - header.center[0]) < 1e-6
    body = safe_area().below(title, gap=0.45)
    cap = chart_caption("Source: somewhere", body)
    assert abs(cap.get_bottom()[1] - body.y0) < 1e-6


# ----- scatter: params ---------------------------------------------------------------------------------


def test_scatter_params_forms_and_refs() -> None:
    p = scatter()
    series = p.series_list()
    assert [s.name for s in series] == ["base", "ours"] and series[0].points[2].label == "7B"
    assert (p.reveal, p.trend, p.show_labels, p.show_legend()) == ("series", "none", "all", True)
    listed = scatter(series=[{"name": "a", "points": [{"x": 1, "y": 2, "group": "g"}, [2, 3]], "marker": "diamond", "color": "accent"}])
    assert listed.series_list()[0].points[0].group == "g" and not listed.show_legend()
    assert p.point_ref("ours@2") == (1, 1) and p.point_ref("ours@small") == (1, 1) and p.point_ref("7B") == (0, 2)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"series": {"a": [[1]]}}, "[x, y] or [x, y, label]"),
        ({"series": [{"name": "a", "points": [[1, 2]]}, {"name": "a", "points": [[2, 3]]}]}, "series name 'a' is used twice"),
        ({"series": {"a": [[1, 2, "p"], [2, 3, "p"]]}}, "point label 'p' is used twice"),
        ({"x_log": True, "series": {"a": [[0, 1], [2, 3]]}}, "x_log needs positive values"),
        ({"x_max": 10}, "lies outside x_min..x_max"),
        ({"y_min": 5, "y_max": 1}, "y_max must be greater"),
        ({"trend": "all", "y_log": True}, "trend lines need linear axes"),
        ({"trend": "each", "series": {"a": [[1, 2], [1, 3]]}}, "at least two different x"),
        ({"trend_label": "r2"}, "trend_label needs a trend"),
        ({"reveal": "groups"}, "needs points with a group"),
        ({"highlight": ["base@9"]}, "series 'base' has no point '9'"),
        ({"highlight": ["nobody@1"]}, "no series 'nobody'"),
        ({"highlight": ["huge"]}, "is not '<series>@<N>'"),
        ({"series": {"a": [[1, 2, "x"]], "b": [[2, 3, "x"]]}, "highlight": ["x"]}, "several series"),
        ({"point_radius": 0}, "greater than 0"),
        ({"x_format": "{:q}"}, "invalid number format"),
    ],
)
def test_scatter_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception) as caught:
        scatter(**changes)
    assert message in str(caught.value)


def test_scatter_target_names() -> None:
    cls = cls_of("scatter")
    names = cls.target_names(scatter(title="T", trend="each"))
    assert names[:3] == ["title", "axes", "legend"]
    assert names[3:5] == ["series1", "series:base"] and "point:base@1" in names and "point:base@7B" in names
    assert names[-3:] == ["trend", "trend:base", "trend:ours"]
    one = cls.target_names(scatter(series={"a": [[1, 2, "2"], [2, 3, "top"]]}))
    assert one == ["axes", "series1", "series:a", "point:a@1", "point:a@2", "point:a@top"]   # a label that is a number names nothing


# ----- histogram: params -------------------------------------------------------------------------------


def test_nice_widths_and_aligned_edges() -> None:
    assert [nice_width(w) for w in (0.7, 1.4, 3.3, 7.4, 23)] == [0.5, 1, 2.5, 10, 25]
    assert aligned_edges(12, 120, 10) == [10.0 + 10 * k for k in range(12)]
    assert aligned_edges(0.03, 0.31, 0.1) == [0.0, 0.1, 0.2, 0.3, 0.4]
    assert aligned_edges(5, 20, 10, start=5) == [5.0, 15.0, 25.0]


def test_histogram_bins() -> None:
    auto = histogram()
    edges = auto.bin_edges()
    assert edges[0] <= min(VALUES) and edges[-1] >= max(VALUES)
    w = edges[1] - edges[0]
    assert nice_width(w) == pytest.approx(w) and all(e / w == pytest.approx(round(e / w)) for e in edges)
    assert sum(auto.bin_counts()) == len(VALUES)
    assert histogram(bins=4).bin_edges() == pytest.approx(list(np.linspace(12, 120, 5)))
    assert histogram(bin_width=25).bin_edges() == [0.0, 25.0, 50.0, 75.0, 100.0, 125.0]
    ranged = histogram(bin_width=10, bin_range=[20, 60])
    assert ranged.bin_edges() == [20.0, 30.0, 40.0, 50.0, 60.0] and sum(ranged.bin_counts()) == len([v for v in VALUES if 20 <= v <= 60])
    assert histogram(bin_width=10).bin_labels()[:2] == ["10-20", "20-30"]
    for rule in ("sturges", "sqrt", "fd"):
        e = histogram(bins=rule).bin_edges()
        assert nice_width(e[1] - e[0]) == pytest.approx(e[1] - e[0]) and e[0] <= 12 and e[-1] >= 120
    given = histogram(values=[], counts=[1, 3, 2], edges=[0, 10, 20, 30])
    assert given.bin_counts() == [1, 3, 2] and given.bin_labels() == ["0-10", "10-20", "20-30"]
    mean, median = given.stats()
    assert mean == pytest.approx((5 + 45 + 50) / 6) and median == pytest.approx(10 + 10 * (3 - 1) / 3)
    assert histogram().stats() == (pytest.approx(np.mean(VALUES)), pytest.approx(np.median(VALUES)))
    assert histogram(bin_width=10, highlight=[0, "30-40"]).bin_index("30-40") == 2
    big = histogram(values=[1000, 25000, 48000, 52000], bin_width=10000)
    assert big.bin_labels()[0] == "0-10k"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"values": None}, "either values"),
        ({"counts": [1, 2], "edges": [0, 1, 2]}, "either values"),
        ({"values": None, "counts": [1, 2], "edges": [0, 1]}, "one more entry than counts"),
        ({"values": None, "counts": [1, 2], "edges": [0, 2, 1]}, "increasing"),
        ({"values": None, "counts": [1, -2], "edges": [0, 1, 2]}, "must not be negative"),
        ({"values": None, "counts": [1, 2], "edges": [0, 1, 2], "bin_width": 1}, "counts come with their edges"),
        ({"edges": [0, 1]}, "edges go with counts"),
        ({"bins": 0}, "bins must be 1.."),
        ({"bin_width": 0.1}, "use a larger bin_width"),
        ({"bin_range": [5, 1]}, "high > low"),
        ({"bin_range": [500, 600]}, "the histogram is empty"),
        ({"compare": {"name": "b"}}, "either values or counts"),
        ({"bin_width": 10, "compare": {"counts": [1, 2]}}, "one count per bin"),
        ({"bin_width": 10, "highlight": [40]}, "out of range"),
        ({"bin_width": 10, "highlight": ["15-25"]}, "is not a bin"),
    ],
)
def test_histogram_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception) as caught:
        histogram(**changes)
    assert message in str(caught.value)


def test_histogram_target_names() -> None:
    cls = cls_of("histogram")
    names = cls.target_names(histogram(bin_width=25, title="T", mean=True, compare={"values": [30, 40]}))
    assert names == ["title", "axes", "legend", "bin1", "bin:0-25", "bin2", "bin:25-50", "bin3", "bin:50-75", "bin4", "bin:75-100",
                     "bin5", "bin:100-125", "compare", "mean"]


def test_validate_checks_chart_targets(make_project) -> None:
    project = load(make_project, [
        {"id": "s", "type": "scatter", "params": {"series": POINTS}, "beats": [{"text": "a", "actions": [{"highlight": "point:ours@smal"}]}]},
        {"id": "h", "type": "histogram", "params": {"values": VALUES, "bin_width": 10}, "beats": [{"text": "a", "actions": [{"highlight": "bin:30-41"}]}]},
    ])
    messages = [p.message for p in project_problems(project)]
    assert any("unknown target 'point:ours@smal'" in m and "did you mean 'point:ours@small'" in m for m in messages)
    assert any("unknown target 'bin:30-41'" in m for m in messages)


# ----- rendering ---------------------------------------------------------------------------------------


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)])
@pytest.mark.parametrize(
    ("kind", "p", "timing"),
    [
        ("scatter", {"title": "Size vs accuracy", "series": POINTS, "trend": "all", "trend_label": "both", "highlight": ["small"], "x_label": "params", "y_label": "acc"}, 4),
        ("scatter", {"series": {"a": [{"x": 10, "y": 12, "group": 1}, {"x": 1000, "y": 20, "group": 2}, {"x": 20000, "y": 120, "group": 2, "label": "peak"}]},
                     "x_log": True, "reveal": "groups"}, 2),
        ("histogram", {"title": "Latency", "values": VALUES, "mean": True, "median": True, "highlight": ["40-50"], "x_label": "ms"}, 4),
        ("histogram", {"counts": [2, 5, 9, 14, 11], "edges": [40, 50, 60, 70, 80, 90], "percent": True, "compare": {"name": "2025", "counts": [1, 3, 6, 11, 15]}}, 0),
    ],
)
@pytest.mark.slow
def test_charts_render_within_their_beats_and_the_safe_area(kind: str, p: dict[str, Any], timing: int, size: tuple[int, int], make_project, media: Path) -> None:
    extra = {"beats": n_beats(timing)} if timing else {"duration": 2.5}
    project = load(make_project, [{"id": "s", "type": kind, "params": p, **extra}])
    scene, duration, _ = render_scene(project, "s", media, *size)
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    assert all(scene.beat_busy[b] <= scene.beat_duration(b) + scene.pad + 1e-6 for b in scene.beat_busy)
    safe = safe_area_of(size)
    for t in scene.targets:
        assert safe.contains(t.mobject, tolerance=0.05), t.name
    floor = None
    texts = [m for t in scene.targets for m in t.mobject.get_family() if isinstance(m, Text)]
    assert texts
    with tempconfig({"frame_width": frame_size(*size)[0], "frame_height": frame_size(*size)[1]}):
        runtime.set_context(project)
        floor = readable_size()
        runtime.clear_context()
    assert min(t.font_size for t in texts) >= floor * 0.99


@pytest.mark.render
@pytest.mark.slow
def test_scatter_points_labels_trend_and_highlight(make_project, media: Path) -> None:
    p = {"series": POINTS, "trend": "each", "trend_label": "r2", "highlight": ["ours@small"], "point_radius": 0.12}
    project = load(make_project, [{"id": "s", "type": "scatter", "params": p, "beats": n_beats(4)}])
    scene = render(project, "s", media)
    axes = scene._axes
    for i, (name, pts) in enumerate(POINTS.items()):
        for j, q in enumerate(pts):
            assert np.allclose(scene._markers[i][j].get_center()[:2], axes.point(q[0], q[1])[:2], atol=1e-6)
    labels = [m for row in scene._labels for m in row if m is not None]
    assert len(labels) == 3
    for a in range(len(labels)):                     # labels never overlap each other
        for b in range(a + 1, len(labels)):
            assert not overlaps(labels[a], labels[b])
    fit = linear_fit([q[0] for q in POINTS["base"]], [q[1] for q in POINTS["base"]])
    line = scene.find_targets("trend:base")[0].mobject[0]
    (x0, y0), (x1, y1) = line.get_start()[:2], line.get_end()[:2]
    slope = ((y1 - y0) / axes.plot.height * (axes.y.hi - axes.y.lo)) / ((x1 - x0) / axes.plot.width * (axes.x.hi - axes.x.lo))
    assert slope == pytest.approx(fit.slope, rel=1e-6)
    assert all(scene.is_shown(t) for t in scene.targets)
    ring = [m for m in scene.mobjects if type(m).__name__ == "Circle" and m.get_stroke_width() >= 2.9]
    assert len(ring) == 1 and np.allclose(ring[0].get_center(), scene._markers[1][1].get_center())
    assert scene._markers[0][0].get_fill_opacity() < 0.5        # the others dimmed


@pytest.mark.render
@pytest.mark.slow
def test_scatter_reveals_one_series_per_beat(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "scatter", "params": {"series": POINTS}, "beats": beats(None, [{"reveal": "point:ours@small"}])}])
    scene = render(project, "s", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert all(scene.is_shown(t) for t in scene.targets)


@pytest.mark.render
@pytest.mark.slow
def test_histogram_bars_markers_and_highlight(make_project, media: Path) -> None:
    p = {"values": VALUES, "bin_width": 10, "mean": True, "median": True, "highlight": [2], "compare": {"values": [20, 30, 35, 45, 60]}}
    project = load(make_project, [{"id": "h", "type": "histogram", "params": p, "beats": n_beats(5)}])
    scene = render(project, "h", media)
    counts = scene.params.bin_counts()
    axes = scene._axes
    for bar, c, a in zip(scene._bars, counts, scene.params.bin_edges()):
        assert bar.height == pytest.approx(max(axes.y_pos(c) - axes.plot.y0, 1e-3), abs=1e-6)
        assert bar.get_bottom()[1] == pytest.approx(axes.plot.y0) and bar.get_left()[0] > axes.x_pos(a)
    mean_line = scene.find_targets("mean")[0].mobject[0]
    assert mean_line.get_x() == pytest.approx(axes.x_pos(float(np.mean(VALUES))), abs=1e-6)
    labels = [scene.find_targets(k)[0].mobject[1] for k in ("mean", "median")]
    assert not overlaps(labels[0], labels[1])
    assert scene._bars[2].get_fill_color().to_hex().lower() == scene.theme.color("highlight").lower()
    assert scene._bars[0].get_fill_opacity() < 0.5
    assert [t.name for t in scene.targets if not scene.is_shown(t)] == []


@pytest.mark.render
def test_histogram_percent_axis(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "h", "type": "histogram", "params": {"counts": [1, 3], "edges": [0, 1, 2], "percent": True}, "duration": 1.5}])
    scene = render(project, "h", media)
    assert scene._axes.y.labels[-1].endswith("%") and scene._axes.y.hi >= 75


# ----- bar_chart and line_chart on the helpers -----------------------------------------------------------


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)])
@pytest.mark.slow
def test_chart_titles_stand_in_the_header(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [
        {"id": "b", "type": "bar_chart", "params": {"title": "Render time per minute of video", "labels": ["480p", "720p", "1080p", "4K"],
                                                     "values": [0.4, 1.1, 2.6, 9.8], "unit": " min"}, "beats": n_beats(1)},
        {"id": "l", "type": "line_chart", "params": {"title": "Validation loss", "x": [1, 2, 3, 4], "series": {"a": [3, 2, 1.5, 1.2], "b": [3.2, 2.5, 1.4, 1.1]}}, "beats": n_beats(2)},
    ]
    project = load(make_project, scenes)
    for sid in ("b", "l"):
        scene = render(project, sid, media, size=size)
        title = scene.find_targets("title")[0].mobject
        fw, fh = frame_size(*size)
        safe = safe_area_of(size)
        band = 0.12 if fh > fw else 0.16
        assert title.get_bottom()[1] >= safe.y1 - safe.height * band - 1e-6, sid


@pytest.mark.render
@pytest.mark.slow
def test_bar_values_stay_readable_in_portrait(make_project, media: Path) -> None:
    """9:16: value labels keep a theme size (the unit goes under the number) instead of being
    scaled down to the bar's slot (Step 22 finding)."""
    p = {"labels": ["Preview 480p", "720p", "1080p", "4K"], "values": [0.4, 1.1, 2.6, 9.8], "unit": " min"}
    project = load(make_project, [{"id": "b", "type": "bar_chart", "params": p, "beats": n_beats(1)}], **VERTICAL)
    scene = render(project, "b", media, size=(90, 160))
    value = scene.find_targets("bar4")[0].mobject[1]
    assert len(value) == 2 and [m.original_text for m in value] == ["9.8", "min"]     # number over its unit
    assert value[0].font_size >= scene.theme.size("body") * 0.99
    bar = scene.find_targets("bar4")[0].mobject[0]
    assert value.get_bottom()[1] > bar.get_top()[1]                                    # stands on its (vertical) bar
    wide = load(make_project, [{"id": "w", "type": "bar_chart", "params": {"labels": ["a", "b", "c", "d", "e"],
                                                                           "values": [12345678, 2, 3, 4, 5], "unit": "%"}, "beats": n_beats(1)}], **VERTICAL)
    scene = render(wide, "w", media, size=(90, 160))
    bars = [scene.find_targets(f"bar{i}")[0].mobject[0] for i in range(1, 6)]
    assert len({round(b.get_x(), 6) for b in bars}) < 5 or len({round(b.get_y(), 6) for b in bars}) == 5   # horizontal bars


@pytest.mark.render
def test_line_chart_labels_and_legend(make_project, media: Path) -> None:
    p = {"x": [1, 2, 3, 4, 5, 6, 7, 8], "series": {"baseline": [2.1, 1.82, 1.66, 1.58, 1.53, 1.5, 1.49, 1.48],
                                                   "sparse": [2.25, 1.9, 1.68, 1.56, 1.49, 1.45, 1.43, 1.41]}, "x_label": "epoch", "y_label": "loss"}
    project = load(make_project, [{"id": "l", "type": "line_chart", "params": p, "beats": n_beats(2)}], **VERTICAL)
    scene = render(project, "l", media, size=(90, 160))
    texts = [m for m in scene.get_mobject_family_members() if isinstance(m, Text)]
    assert min(t.font_size for t in texts) >= scene.theme.size("caption") * 0.99       # large scale in 9:16
    names = {t.original_text for t in texts}
    assert {"baseline", "sparse"} <= names                                              # in a legend (too wide as end labels)
    frames = [m for m in scene.get_mobject_family_members() if type(m).__name__ == "RoundedRectangle"]
    assert len(frames) == 1                                                             # framed: inside the plot


# ----- docs example --------------------------------------------------------------------------------------


@pytest.mark.render
@pytest.mark.slow
def test_extending_charts_example_renders(make_project, media: Path) -> None:
    text = (ROOT / "docs" / "EXTENDING.md").read_text(encoding="utf-8")
    code = re.search(r"\*\*Charts\.\*\*.*?```python\n(.*?)```", text, re.S).group(1)
    root = make_project(minimal_config(scenes=[{"id": "g", "type": "growth", "beats": n_beats(2)}], narration=NARRATION))
    (root / "extensions").mkdir(exist_ok=True)
    (root / "extensions" / "growth.py").write_text("from vidgen.api import *\n\n\n" + code, encoding="utf-8")
    scene = render(Project.load(root), "g", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)


def test_api_exports_the_chart_helpers() -> None:
    import vidgen.api as api

    for name in ("ChartAxis", "ChartAxes", "LinearFit", "CHART_MARKERS", "axis_ticks", "auto_legend", "chart_axes", "chart_caption",
                 "chart_label_size", "chart_legend", "chart_marker", "chart_title", "legend_spot", "linear_fit", "sample_path",
                 "short_number", "tick_texts", "value_axis"):
        assert name in api.__all__ and getattr(api, name).__doc__, name

