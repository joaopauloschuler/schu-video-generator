"""Step 162: charts that change between beats (``changes`` on ``bar_chart`` and ``line_chart``):
params and checks, the states, the y axis rescale rule, ``change<N>`` targets and steps, the
``trace`` cursor on a line, and tiny renders in 16:9 and 9:16, on words, with concept colours."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from manim import ManimColor
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import beat_total, render
from test_builtin_scenes import cls_of
from test_comparison_table import safe_area_of
from vidgen.charts import value_axis
from vidgen.cli import check_project
from vidgen.project import Project
from vidgen.scenes.bar_chart import BarChart
from vidgen.scenes.chart_changes import needs_rescale, state_axes
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
BARS = {"labels": ["a", "b", "c"], "values": [3, 2, 1], "changes": [[1, 2, 5], [4, 4, 4]]}
LINES = {"x": [1, 2, 3, 4], "series": {"loss": [4, 3, 2, 1.5], "acc": [1, 2, 3, 3.5]}, "changes": [{"loss": [2, 1, 0.5, 0.4]}]}


def params(kind: str, **raw: Any) -> Any:
    return cls_of(kind).validate_params(raw, Theme())


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides)))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


def texts(mob: Any) -> str:
    return "".join(t.original_text for t in mob.get_family() if hasattr(t, "original_text"))


# ----- params, states, targets and steps ------------------------------------------------------------


def test_bar_states_targets_and_steps() -> None:
    p = params("bar_chart", **BARS, highlight="c")
    assert p.states() == [[3, 2, 1], [1, 2, 5], [4, 4, 4]]
    assert cls_of("bar_chart").target_names(p)[-2:] == ["change1", "change2"]
    steps = cls_of("bar_chart").reveal_steps(p)
    assert [(s.focus, s.result) for s in steps] == [("bar3", "fall"), ("change1", "rise"), ("change2", "rise"), ("bar3", None)]
    assert cls_of("bar_chart").target_names(params("bar_chart", labels=["a"], values=[1])) == ["bar1", "bar:a"]   # one state: unchanged


@pytest.mark.parametrize(
    ("raw", "message"),
    [({"labels": ["a", "b"], "values": [1, 2], "changes": [[1]]}, "changes[0] has 1 values but there are 2 bars"),
     ({"labels": ["a"], "values": [1], "changes": [["x"]]}, "valid number")],
)
def test_bar_change_checks(raw: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message.replace("[", r"\[").replace("]", r"\]")):
        params("bar_chart", **raw)


def test_sorting_ranks_the_bars_largest_first_ties_in_label_order() -> None:
    chart = SimpleNamespace(params=SimpleNamespace(sort=True))
    assert BarChart._order(chart, [2, 5, 2, 9]) == [2, 1, 3, 0]
    assert BarChart._order(SimpleNamespace(params=SimpleNamespace(sort=False)), [2, 5]) == [0, 1]


def test_line_states_keep_series_a_change_leaves_out() -> None:
    p = params("line_chart", **LINES)
    assert p.states() == [[[4, 3, 2, 1.5], [1, 2, 3, 3.5]], [[2, 1, 0.5, 0.4], [1, 2, 3, 3.5]]]
    one = params("line_chart", x=[1, 2], series={"s": [1, 2]}, changes=[[3, 4]])
    assert one.states() == [[[1, 2]], [[3, 4]]]
    assert cls_of("line_chart").target_names(p)[-1] == "change1"
    steps = cls_of("line_chart").reveal_steps(p)
    assert [(s.focus, s.result) for s in steps] == [("series1", "fall"), ("series2", "rise"), ("change1", "fall")]


@pytest.mark.parametrize(
    ("changes", "message"),
    [([[1, 2, 3, 4]], "changes[0] is a list of values, but the chart has 2 series: write {name: [values]}"),
     ([{"los": [1, 2, 3, 4]}], "changes[0]: 'los' is not a series (series: loss, acc)"),
     ([{"loss": [1, 2]}], "changes[0].loss has 2 values but x has 4"),
     ([{}], "changes[0] is empty")],
)
def test_line_change_checks(changes: list[Any], message: str) -> None:
    with pytest.raises(ValidationError) as info:
        params("line_chart", **{**LINES, "changes": changes})
    assert message in str(info.value)


def test_the_y_axis_rescales_when_values_leave_it_or_would_look_flat() -> None:
    axis = value_axis([0, 4])
    assert not needs_rescale(axis, [0.5, 3.5])
    assert needs_rescale(axis, [1, 6])           # leaves it
    assert needs_rescale(axis, [1, 1.5])         # spans less than half of it
    states = [[0, 4], [0.5, 3.5], [0.1, 0.9], [0.2, 0.8]]
    axes = state_axes(states, lambda v: value_axis(v), rescale=True)
    assert axes[1] is axes[0] and axes[2] is not axes[1] and axes[3] is axes[2]
    assert axes[2].hi == pytest.approx(1.0)
    fixed = state_axes(states, lambda v: value_axis(v), rescale=False)
    assert all(a is fixed[0] for a in fixed) and fixed[0].hi == pytest.approx(4)
    pinned = state_axes(states, lambda v: value_axis(v, lo=0, hi=5), rescale=True)
    assert all(a is pinned[0] for a in pinned)   # y_min / y_max fix the axis: nothing to rescale


@pytest.mark.parametrize(
    ("target", "options", "x", "problem"),
    [("series1", {"to": 3}, [1, 2, 4], None),
     ("series:s", {"to": 5}, [1, 2, 4], "5 is outside the x values [1, 4]"),
     ("series1", {"to": 3}, ["Q1", "Q2", "Q3"], None),
     ("series1", {"to": 4}, ["Q1", "Q2", "Q3"], "a position from 1 to 3 (to: 2 is 'Q2'), not 4"),
     ("series1", {"to": [1, 2]}, [1, 2], "to is where the cursor stops on the x axis"),
     ("series1", {"scale": 2}, [1, 2], "scale is for a function_plot's vector"),
     ("point:s@1", {"to": 1}, [1, 2], "trace sweeps a cursor along a line_chart series")],
)
def test_trace_checks_on_a_line_chart(target: str, options: dict[str, Any], x: list[Any], problem: str | None, make_project) -> None:
    scene = {"id": "c", "type": "line_chart", "params": {"x": x, "series": {"s": list(range(len(x)))}},
             "beats": [{"text": "one two three", "actions": [{"trace": target, **options}]}]}
    found = [m for m in check_project(load(make_project, [scene])) if "trace" in m or "to" in m or "scale" in m]
    if problem is None:
        assert found == []
    else:
        assert any(problem in m for m in found), found


def test_unknown_change_and_trace_on_a_bar_chart_are_refused(make_project) -> None:
    scene = {"id": "c", "type": "bar_chart", "params": BARS,
             "beats": [{"text": "one two", "actions": [{"reveal": "change3"}, {"trace": "bar1", "to": 2}]}]}
    problems = check_project(load(make_project, [scene]))
    assert any("change3" in m for m in problems)
    assert any("a cursor along a line_chart series" in m for m in problems)


# ----- renders ---------------------------------------------------------------------------------------


def plays(scene: Any, beat: str, name: str) -> list[Any]:
    return [p for p in scene.play_log if p.beat == beat and any(name in a for a in p.animations)]


@pytest.mark.render
def test_bars_change_and_resort_beat_by_beat(make_project, media: Path) -> None:
    beats = [{"text": "first the old numbers"}, {"text": "then they change"}, {"text": "and change again"}]
    spec = {"id": "c", "type": "bar_chart", "params": {**BARS, "sort": True, "title": "T", "unit": "%"}, "beats": beats}
    for size, fmt in (((160, 90), {}), ((90, 160), {"format": {"width": 1080, "height": 1920}})):
        scene = render(load(make_project, [spec], **fmt), "c", media, size=size)
        assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
        assert plays(scene, "c_b2", "UpdateFromAlphaFunc") and plays(scene, "c_b3", "UpdateFromAlphaFunc")
        assert all(scene.is_shown(n) for n in ("change1", "change2"))
        assert [texts(m) for m in scene._labels] == ["4%", "4%", "4%"]
        heights = [r.height if not scene.is_portrait or r.height > r.width else r.width for r in scene._rects]
        assert max(heights) - min(heights) < 1e-6   # every bar at 4
        assert scene._slots == [0, 1, 2]   # ties: in the order of the labels
        for mob in scene.mobjects:
            assert safe_area_of(size).contains(mob, tolerance=0.02), type(mob).__name__


@pytest.mark.render
def test_a_change_on_a_word_resorts_and_moves_the_highlight_box(make_project, media: Path) -> None:
    beats = [{"text": "the start and then the change comes now and we watch the bars settle in their new places", "actions": [{"reveal": "change1", "at": "@now"}]},
             {"text": "hold it"}]
    spec = {"id": "c", "type": "bar_chart", "params": {"labels": ["a", "b"], "values": [1, 3], "changes": [[5, 2]], "sort": True}, "beats": beats}
    scene = render(load(make_project, [spec]), "c", media)
    start = {t.beat_id: t for t in scene.beat_log}["c_b1"]
    moved = plays(scene, "c_b1", "UpdateFromAlphaFunc")
    assert moved and moved[-1].start - start.start > 0.3 * (start.end - start.start)
    assert moved[-1].end - moved[-1].start == pytest.approx(1.2, abs=0.25)   # CHANGE_TIME
    assert plays(scene, "c_b2", "UpdateFromAlphaFunc") == []   # the scene left change1 to the action
    a, b = scene._rects
    assert a.get_center()[0] < b.get_center()[0] and a.height > b.height   # a (5) now first, taller
    box = scene.find_targets("bar1")[0].outline
    assert box.get_center()[0] == pytest.approx(a.get_center()[0], abs=0.05)


@pytest.mark.render
def test_lines_morph_rescale_and_a_cursor_rides_along(make_project, media: Path) -> None:
    beats = [{"text": "loss and accuracy over four epochs", "actions": [{"trace": "series:loss", "to": 3, "at": "@over"}]},
             {"text": "with pretraining the loss is much lower"}]
    raw = {**LINES, "changes": [{"loss": [0.4, 0.3, 0.2, 0.1], "acc": [0.5, 0.6, 0.7, 0.9]}], "title": "Loss", "reveal": "all"}
    for size, fmt in (((160, 90), {}), ((90, 160), {"format": {"width": 1080, "height": 1920}})):
        scene = render(load(make_project, [{"id": "c", "type": "line_chart", "params": raw, "beats": beats}], **fmt), "c", media, size=size)
        assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
        before, after = scene._state_axes
        assert after is not before and after.y.hi == pytest.approx(1.0)
        holder = scene._grid
        family = {id(m) for m in scene.get_mobject_family_members()}
        assert all(any(t is m for m in holder) for t in after.y_labels) and not any(any(t is m for m in holder) for t in before.y_labels)
        assert all(id(t) in family for t in after.y_labels) and not any(id(t) in family for t in before.y_labels)
        assert holder in scene.mobjects   # still one group: the axes target
        line = scene._lines[0][0]
        assert np.allclose(np.array(line.get_anchors())[[0, -1]], scene._points[1][0][[0, -1]])
        assert "0.1" in texts(scene._notes[0])
        cursor = scene._cursors[0]
        assert cursor.x == pytest.approx(3) and texts(cursor.live.group) == "0.2"
        assert cursor.dot.get_center() == pytest.approx(after.point(3, 0.2), abs=1e-3)
        for mob in scene.mobjects:
            assert safe_area_of(size).contains(mob, tolerance=0.02), type(mob).__name__


@pytest.mark.render
def test_concept_colours_hold_through_a_change(make_project, media: Path) -> None:
    theme = Theme()
    beats = [{"text": "one two"}, {"text": "three four"}]
    scenes = [{"id": "b", "type": "bar_chart", "params": {"labels": ["Rust", "Go"], "values": [1, 2], "changes": [[3, 1]], "sort": True}, "beats": beats},
              {"id": "l", "type": "line_chart", "params": {"x": [1, 2], "series": {"loss": [2, 1]}, "changes": [[1, 0.5]]}, "beats": beats}]
    project = load(make_project, scenes, terms={"Rust": "accent", "loss": "#E07A5F"})
    bars = render(project, "b", media)
    accent = tuple(np.round(ManimColor(theme.color("accent")).to_rgb(), 3))
    glyph = bars._cats[0].family_members_with_points()[0]
    assert tuple(np.round(glyph.get_fill_color().to_rgb(), 3)) == accent
    assert bars._slots == [0, 1]   # Rust (3) first after the change
    lines = render(project, "l", media)
    assert lines._lines[0][0].get_stroke_color().to_hex().upper() == "#E07A5F"
