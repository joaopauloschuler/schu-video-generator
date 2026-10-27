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


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


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
