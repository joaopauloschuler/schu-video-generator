"""The ``plot`` scene type (Phase W Step 222): params and their checks, data from a CSV in the
project with units in its headers, targets and legends, and tiny renders in 16:9 and 9:16."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import render
from vidgen import extensions, registry
from vidgen.cli import project_problems
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 3.0}
DECAY_CSV = "# illustrative\ntime (d), activity (Bq), model (Bq), dose (mSv)\n0, 1000, 1000, 1\n8, 506, 500, 2\n16, 248, 250, 3\n24, 124, 125, 4\n"


def cls() -> Any:
    extensions.load_builtins()
    return registry.get("plot").cls


def params(**p: Any) -> Any:
    return cls().validate_params(p)


INLINE = [{"name": "a", "x": [0, 1, 2], "y": [1, 10, 100]}]


def test_inline_series_forms() -> None:
    p = params(series=[{"name": "a", "x": [0, 1, 2], "y": [1, None, 3]}, {"name": "b", "points": [[0, 1], [2, 2]], "style": "both", "dashed": True}])
    (panel,) = p.resolve()
    a, b = panel.series
    assert a.xs == [0, 1, 2] and a.ys[1] != a.ys[1] and b.xs == [0, 2]   # null is a gap (nan)
    assert panel.x.label == "" and panel.y.scale == "linear"


@pytest.mark.parametrize(
    ("p", "message"),
    [
        ({}, "give series"),
        ({"series": INLINE, "panels": [{"series": INLINE}]}, "not both"),
        ({"series": [{"name": "a", "x": [0, 1]}]}, "give x and y"),
        ({"series": [{"name": "a", "x": [0, 1], "y": [1], }]}, "x has 2 values but y has 1"),
        ({"series": [{"name": "a", "points": [[0, 1]], "x": [0]}]}, "points or x and y, not both"),
        ({"series": [{"name": "a", "x": "time", "y": "activity"}]}, "no data file is given"),
        ({"series": INLINE * 2}, "series name 'a' is used twice"),
        ({"series": INLINE, "y": {"scale": "log"}, "x": {"scale": "log"}}, "x: a log scale needs positive values, but the data has 0"),
        ({"series": INLINE, "y": {"max": 50}}, "the value 100 lies outside max 50"),
        ({"series": INLINE, "aspect": "equal", "y": {"scale": "log"}}, "aspect: equal needs linear x and y"),
        ({"panels": [{"series": INLINE}, {"series": [{"name": "b", "points": [[0, 1]]}], "x": {"label": "t"}}]}, r"panels\[2\].x: the panels share the x axis"),
        ({"series": INLINE, "y": {"format": "si", "unit": "km"}}, "already has the prefix 'k'"),
        ({"series": INLINE, "y": {"format": "pretty"}}, "is not one of auto, plain, sci, si"),
        ({"series": INLINE, "x": {"breaks": [[0.5, 1.5]]}}, "the value 1 lies inside the break"),
        ({"series": INLINE, "data": "values.xlsx"}, "not a .csv or .tsv file"),
        ({"series": INLINE, "y": {"linthresh": 1}}, "linthresh is for scale: symlog"),
    ],
)
def test_params_errors(p: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(p)


def test_targets_and_legends() -> None:
    c = cls()
    one = params(title="T", series=INLINE)
    assert c.target_names(one) == ["title", "axes", "series1", "series:a"]
    two = params(series=[*INLINE, {"name": "b", "points": [[0, 1]]}])
    assert "legend" in c.target_names(two)
    stacked = params(panels=[{"series": INLINE}, {"series": [{"name": "speed", "points": [[0, 1]]}], "y": {"label": "speed"}}])
    assert c._legend_panels(stacked) == [True, False]     # the second panel's y title already names its series
    assert c.target_names(stacked)[:4] == ["axes", "panel1", "panel2", "legend"]
    assert c._legend_panels(params(series=[*INLINE, {"name": "b", "points": [[0, 1]]}], legend=False)) == [False]


def scene(params: dict[str, Any], texts: tuple[str, ...] = ("one two",)) -> dict[str, Any]:
    return {"id": "p", "type": "plot", "params": params, "beats": [{"text": t} for t in texts]}


def test_a_csv_in_the_project_gives_columns_and_units(make_project) -> None:
    good = {"data": "assets/decay.csv", "y": {"scale": "log"},
            "series": [{"name": "measured", "x": "time", "y": "activity", "style": "points"}, {"name": "model", "x": "time", "y": "model (Bq)"}]}
    root = make_project(minimal_config(scenes=[scene(good)], narration=NARRATION))
    (root / "assets").mkdir(exist_ok=True)
    (root / "assets" / "decay.csv").write_text(DECAY_CSV, encoding="utf-8")
    project = Project.load(root)
    assert [p.message for p in project_problems(project)] == []
    (panel,) = cls().validate_params(good).resolve(project)
    assert (panel.x.label, panel.x.unit, panel.y.label, panel.y.unit) == ("time", "d", "activity", "Bq")

    def problem(p: dict[str, Any]) -> str:
        found = [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[scene(p)], narration=NARRATION))))]
        assert found, p
        return found[0]

    typo = {**good, "series": [{"name": "m", "x": "time", "y": "activty"}]}
    assert "has no column 'activty'" in problem(typo) and "did you mean 'activity'?" in problem(typo)
    mixed = {**good, "series": [{"name": "m", "x": "time", "y": "activity"}, {"name": "d", "x": "time", "y": "dose"}]}
    assert "different units (Bq and mSv)" in problem(mixed)
    stated = {**good, "y": {"unit": "kBq"}}
    assert "the axis is in kBq but the column 'activity' is in Bq" in problem(stated)
    missing = {**good, "data": "assets/nope.csv"}
    assert "asset not found: assets/nope.csv" in problem(missing)


# ----- Step 223: error bars, fits, histograms, annotations ---------------------------------------

POINTS = [{"name": "m", "x": [0, 2, 4, 6, 8, 10], "y": [100, 61, 37, 22, 13.5, 8.2], "style": "points"}]


@pytest.mark.parametrize(
    ("p", "message"),
    [
        ({"series": [{**POINTS[0], "error": "sem"}]}, "says what the error bars mean, but there are none"),
        ({"series": [{**POINTS[0], "y_err": [1, 2]}]}, "y_err has 2 values for 6 points"),
        ({"series": [{**POINTS[0], "y_err": -1}]}, "must not be negative"),
        ({"series": [{**POINTS[0], "x_err": "sqrt"}]}, "sqrt \\(Poisson\\) is for y_err"),
        ({"series": [{"name": "h", "values": [1, 2, 3], "x": [1, 2, 3]}]}, "a histogram takes values"),
        ({"series": [{"name": "h", "values": [1, 2, 3], "style": "line"}]}, "drawn as bars, step or points"),
        ({"series": [{"name": "h", "values": [1, 2, 3], "y_err": 2}]}, "y_err: sqrt"),
        ({"series": [{**POINTS[0], "bins": 5}]}, "are for a histogram"),
        ({"series": POINTS, "fits": [{"series": "n", "model": "linear"}]}, "no series 'n'"),
        ({"series": POINTS, "fits": [{"series": "m", "model": "exponentail"}]}, "did you mean 'exponential'"),
        ({"series": POINTS, "fits": [{"series": "m", "model": "normal"}]}, "fitted to a histogram"),
        ({"series": POINTS, "fits": [{"series": "m", "model": "custom"}]}, "custom needs expr"),
        ({"series": POINTS, "fits": [{"series": "m", "model": "custom", "expr": "a*x + q", "params": {"a": 1}}]}, "unknown name 'q'"),
        ({"series": POINTS, "fits": [{"series": "m", "model": "linear", "background": 1}]}, "background is for the peak models"),
        ({"series": POINTS, "fits": [{"series": "m"}, {"series": "m"}]}, "two fits are called 'linear fit'"),
        ({"series": POINTS, "fits": [{"series": "m", "model": "poly", "degree": 6}]}, "needs more than 7 points"),
        ({"series": POINTS, "annotations": [{"type": "label", "text": "a"}]}, "needs its point"),
        ({"series": POINTS, "annotations": [{"type": "label", "series": "m", "y": 3, "text": "a"}]}, "takes x or index"),
        ({"series": POINTS, "annotations": [{"type": "hline", "x": 3}]}, "needs y: a number"),
        ({"series": POINTS, "annotations": [{"type": "xrange", "x": [5, 2]}]}, r"needs x: \[from, to\]"),
        ({"series": POINTS, "annotations": [{"type": "note"}]}, "a note needs text"),
        ({"series": POINTS, "annotations": [{"type": "label", "series": "q", "x": 1, "text": "a"}]}, "no series 'q'"),
        ({"series": POINTS, "annotations": [{"type": "hline", "y": 3, "panel": 2}]}, "panel 2, but the plot has 1 panel"),
        ({"series": POINTS, "annotations": [{"type": "hline", "y": 3, "id": "a"}, {"type": "vline", "x": 3, "id": "a"}]}, "the id 'a' is used twice"),
        ({"panels": [{"series": POINTS}, {"series": INLINE}], "arrange": "columns", "fits": [{"series": "m", "residuals": True}]}, "use arrange: rows"),
    ],
)
def test_data_feature_errors(p: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(p)


def test_errors_histograms_and_fits_resolve() -> None:
    p = params(series=[{**POINTS[0], "y_err": {"minus": 1, "plus": [1, 2, 3, 4, 5, 6]}, "x_err": 0.1, "error": "sd"}],
               fits=[{"series": "m", "model": "exponential", "band": "confidence", "residuals": True}])
    s = p.resolve()[0].series[0]
    assert list(s.y_err[0]) == [1] * 6 and list(s.y_err[1]) == [1, 2, 3, 4, 5, 6] and list(s.x_err[0]) == [0.1] * 6
    assert s.extents("y")[:2] == [99, 60]
    (fit,) = p.resolve().fits
    assert fit.result.params[1] == pytest.approx(-0.25, abs=0.01) and fit.result.sigma is not None   # weighted by the y errors
    assert fit.lines()[0].startswith("A = ") and any(line.startswith("χ²/ν = ") for line in fit.lines())
    h = params(series=[{"name": "h", "values": [1, 2, 2, 3, 3, 3, 4, 4, 5], "bins": "integers", "y_err": "sqrt"}],
               fits=[{"series": "h", "model": "poisson"}])
    (panel,) = h.resolve()
    hs = panel.series[0]
    assert hs.xs == [1, 2, 3, 4, 5] and hs.ys == [1, 2, 3, 2, 1] and panel.y.include_zero and panel.y.label == "count"
    assert list(hs.y_err[0]) == pytest.approx([1, 2**0.5, 3**0.5, 2**0.5, 1])
    (pfit,) = h.resolve().fits
    assert pfit.discrete and pfit.result.params[0] == pytest.approx(3.0) and pfit.lines()[0] == "μ = 3.0 ± 0.6"
    dens = params(series=[{"name": "h", "values": [1, 2, 2, 3, 3, 3], "bins": [0.5, 1.5, 3.5], "density": True}])
    assert dens.resolve()[0].y.label == "density"
    with pytest.raises(ValidationError, match=r"fits\[1\] \(power fit\): a power fit needs positive x values"):
        params(series=POINTS, fits=[{"series": "m", "model": "power"}])


def test_targets_of_fits_errors_and_annotations() -> None:
    c = cls()
    p = params(series=[{**POINTS[0], "y_err": 1, "error": "sem"}], fits=[{"series": "m", "model": "exponential", "name": "decay"}],
               annotations=[{"type": "hline", "y": 50}, {"type": "label", "series": "m", "index": 2, "text": "two", "id": "two"}])
    assert c.target_names(p) == ["axes", "legend", "series1", "series:m", "errors:m", "fit1", "fit:decay", "annotation1", "annotation2", "annotation:two"]
    assert c._legend_panels(params(series=POINTS, fits=[{"series": "m"}])) == [True]          # a fit: a legend
    assert c._legend_panels(params(series=[{**POINTS[0], "y_err": "sqrt"}])) == [True]        # error bars with a meaning (poisson)


def test_fit_and_annotate_actions_are_checked(make_project) -> None:
    base = {"series": POINTS, "fits": [{"series": "m", "model": "exponential", "name": "decay"}], "annotations": [{"type": "hline", "y": 50, "id": "half"}]}

    def problems(p: dict[str, Any], actions: list[dict[str, Any]], kind: str = "plot") -> list[str]:
        sc = {"id": "p", "type": kind, "params": p, "beats": [{"text": "one two", "actions": actions}]}
        return [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[sc], narration=NARRATION))))]

    assert problems(base, [{"fit": "fit:decay", "at": "@two"}, {"annotate": "annotation:half"}, {"reveal": "series1"}]) == []
    assert any("fit acts on a fit: fit1, fit:decay; 'fit:decy' is not one" in m and "did you mean" in m for m in problems(base, [{"fit": "fit:decy"}]))
    assert any("annotate needs an annotation" in m for m in problems({"series": POINTS}, [{"annotate": "annotation1"}]))
    assert any("fit is an action of plot scenes" in m for m in problems({"title": "x", "values": [1, 2]}, [{"fit": "fit1"}], kind="histogram"))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_fits_histograms_and_annotations_render(size: tuple[int, int], make_project, media: Path) -> None:
    decay = {"title": "Decay", "series": [{**POINTS[0], "y_err": 2, "error": "sem"}],
             "fits": [{"series": "m", "model": "exponential", "band": "confidence", "residuals": True, "name": "decay"}],
             "annotations": [{"type": "hline", "y": 50, "text": "half"}, {"type": "label", "series": "m", "index": 3, "text": "three", "id": "three"},
                             {"type": "note", "text": "illustrative"}, {"type": "xrange", "x": [4, 6], "text": "window"}]}
    values = [float(v) for v in [3, 4, 4, 5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 8, 8, 9, 5, 6, 4, 6, 7, 5]]
    hist = {"series": [{"name": "h", "values": values, "bins": "integers"}], "fits": [{"series": "h", "model": "normal"}],
            "annotations": [{"type": "arrow", "x": 6, "y": 4, "text": "mode"}]}
    scenes = [
        {"id": "decay", "type": "plot", "params": decay,
         "beats": [{"text": "points"}, {"text": "the fit now", "actions": [{"fit": "fit:decay", "at": "@now"}, {"annotate": "annotation:three"}]}]},
        {"id": "hist", "type": "plot", "params": hist, "beats": [{"text": "bars"}, {"text": "a curve"}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))
    s = render(project, "decay", media, size)
    assert len(s.layouts) == 2 and s.layouts[0].x == s.layouts[1].x and s.layouts[1].y.title == "residual"   # the residual panel shares x
    assert all(s.is_shown(t) for t in s.targets)
    boxes = [b for b in s.annotation_boxes if b is not None]
    assert len(boxes) == 4
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert min(a.x1, b.x1) <= max(a.x0, b.x0) + 1e-6 or min(a.y1, b.y1) <= max(a.y0, b.y0) + 1e-6, "annotations overlap"
    (fit,) = s.fit_results
    assert fit.result.params[1] == pytest.approx(-0.25, abs=0.01)
    h = render(project, "hist", media, size)
    assert all(h.is_shown(t) for t in h.targets) and h.layouts[0].y.lo == 0


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_plot_scenes_render(size: tuple[int, int], make_project, media: Path) -> None:
    decay = {"title": "Decay", "data": "assets/decay.csv", "y": {"scale": "log"},
             "series": [{"name": "measured", "x": "time", "y": "activity", "style": "points"}, {"name": "model", "x": "time", "y": "model", "dashed": True}]}
    orbit = {"aspect": "equal", "x": {"label": "x", "unit": "AU"}, "y": {"label": "y", "unit": "AU"},
             "series": [{"name": "orbit", "points": [[1, 0], [0, 1], [-1, 0], [0, -1], [1, 0]]}, {"name": "Sun", "points": [[0, 0]], "style": "points"}]}
    panels = {"panels": [{"series": [{"name": "E", "x": [0, 1, 2], "y": [-3e32, -2e32, -3e32]}], "y": {"label": "energy", "unit": "J"}},
                         {"series": [{"name": "r", "x": [0, 1, 2], "y": [1.4, 1.6, 1.4]}], "y": {"label": "r", "unit": "AU"}}],
              "x": {"label": "time", "unit": "yr", "reversed": True}}
    scenes = [
        {"id": "decay", "type": "plot", "params": decay, "beats": [{"text": "points"}, {"text": "the model", "actions": [{"highlight": "series:model"}]}]},
        {"id": "orbit", "type": "plot", "params": orbit, "beats": [{"text": "an orbit"}]},
        {"id": "panels", "type": "plot", "params": panels, "beats": [{"text": "energy"}, {"text": "distance", "actions": [{"dim": "panel1"}]}]},
    ]
    root = make_project(minimal_config(scenes=scenes, narration=NARRATION))
    (root / "assets").mkdir(exist_ok=True)
    (root / "assets" / "decay.csv").write_text(DECAY_CSV, encoding="utf-8")
    project = Project.load(root)
    s = render(project, "decay", media, size)
    (lay,) = s.layouts
    assert lay.y.scale == "log" and lay.y.title == "activity (Bq)" and lay.x.title == "time (d)" and s.legends
    assert all(s.is_shown(t) for t in s.find_targets("series*"))
    o = render(project, "orbit", media, size)
    (lay,) = o.layouts
    assert lay.plot.width / (lay.x.hi - lay.x.lo) == pytest.approx(lay.plot.height / (lay.y.hi - lay.y.lo), rel=1e-6)
    p = render(project, "panels", media, size)
    top, bottom = p.layouts
    assert top.x is bottom.x or top.x == bottom.x
    assert top.y.title == "energy (10³⁰ J)" and bottom.frame_x(0) > bottom.frame_x(2)   # reversed x
