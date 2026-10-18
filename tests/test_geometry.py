"""Step 161: geometry basics. The mark builders (``vidgen.geometry_marks``: braces, angle arcs,
dimension lines), points, vectors (sums, scaling) and marks on a ``function_plot`` plane, the
``number_line`` scene type (points, intervals, jumps), the generalised ``trace`` action, terms,
and tiny renders in 16:9 and 9:16 on spoken words."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import beat_total, render
from test_builtin_scenes import cls_of
from test_comparison_table import safe_area_of
from vidgen import runtime
from vidgen.cli import check_project
from vidgen.config import VideoConfig
from vidgen.geometry_marks import angle_between, angle_mark, brace_mark, dimension_mark, segment_normal
from vidgen.project import Project
from vidgen.scenes.number_line import interval_lanes, jump_heights, signed
from vidgen.scenes.plane_geometry import PlaneFigure, PlotMark, PlotPoint, PlotVector, geometry_range, mark_numbers
from vidgen.terms import term_conflicts
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides)))


def plane(**values: Any) -> Any:
    return cls_of("function_plot").validate_params(values, Theme())


def line(**values: Any) -> Any:
    return cls_of("number_line").validate_params({"range": [-5, 5], **values}, Theme())


def escaped(message: str) -> str:
    for c in "[]()^+{}":
        message = message.replace(c, "\\" + c)
    return message


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture
def active(make_project) -> Project:
    project = load(make_project, [{"id": "a", "type": "bullets", "params": {"items": ["x"]}, "beats": [{"text": "one"}]}])
    runtime.set_context(project)
    yield project
    runtime.clear_context()


# ----- the mark builders (frame coordinates) ------------------------------------------------------


def test_segment_normal_points_away_from_the_figure() -> None:
    assert np.allclose(segment_normal([0, 0], [2, 0]), [0, -1, 0])                 # default: down
    assert np.allclose(segment_normal([0, 0], [0, 2]), [-1, 0, 0])                 # vertical: left
    assert np.allclose(segment_normal([0, 0], [2, 0], away_from=[1, -1]), [0, 1, 0])
    assert np.allclose(segment_normal([2, 0], [2, 2], away_from=[0, 1]), [1, 0, 0])


def test_angle_between_takes_the_smaller_angle() -> None:
    start, sweep = angle_between([0, 0], [1, 0], [0, 1])
    assert start == pytest.approx(0) and sweep == pytest.approx(np.pi / 2)
    assert angle_between([0, 0], [0, 1], [1, 0])[1] == pytest.approx(-np.pi / 2)  # clockwise
    assert angle_between([0, 0], [1, 0], [-1, -0.01])[1] == pytest.approx(-np.pi + 0.01, abs=1e-3)


def test_marks_put_their_labels_outside(active: Project) -> None:
    from manim import Square

    label = Square(0.2)
    brace = brace_mark([0, 0], [2, 0], label=label, normal=[0, -1])
    assert label.get_top()[1] < brace.shape.get_bottom()[1] + 1e-6 and label.get_center()[0] == pytest.approx(1, abs=0.05)
    label = Square(0.2)
    right = angle_mark([0, 0], [1, 0], [0, 1], label=label)
    assert len(right.shape.points) == 8 and right.shape.width == pytest.approx(0.4 * 0.7)   # a square's two sides (radius: 40 % of the ray)
    assert label.get_center()[0] > 0.3 and label.get_center()[1] > 0.3                       # on the bisector, outside
    arc = angle_mark([0, 0], [1, 0], [1, 1], label=Square(0.2), radius=10)
    assert type(arc.shape).__name__ == "Arc" and arc.shape.width <= 0.4 + 1e-6                 # shrinks on short rays
    label = Square(0.2)
    dim = dimension_mark([0, 0], [3, 0], label=label, normal=[0, 1])
    assert dim.shape.get_bottom()[1] == pytest.approx(0.06, abs=1e-6) and label.get_bottom()[1] > dim.shape[0].get_center()[1]


# ----- the figure (no manim) ----------------------------------------------------------------------


def figure(points: list[Any], vectors: list[Any]) -> PlaneFigure:
    return PlaneFigure([PlotPoint.model_validate(p) for p in points], [PlotVector.model_validate(v) for v in vectors])


def test_figure_resolves_names_numbers_and_sums() -> None:
    f = figure([{"at": [1, 1], "name": "A"}, [3, 0]],
               [{"from": "A", "to": "point2", "name": "a"}, {"components": [0, 2], "name": "b"}, {"sum": ["a", "vector2"]}, {"from": "a", "to": [0, 0]}])
    assert np.allclose(f.ends(0), [[1, 1], [3, 0]]) and np.allclose(f.ends(1), [[0, 0], [0, 2]])
    assert np.allclose(f.ends(2), [[1, 1], [3, 2]])                       # from a's tail to the end of the chain
    assert np.allclose([e for pair in f.chain(2) for e in pair], [[1, 1], [3, 0], [3, 0], [3, 2]])
    assert np.allclose(f.ends(3)[0], [3, 0])                               # from a vector: its tip
    f.move("point", 1, np.array([5.0, 1.0]))                              # a's tip follows point 2, the sum follows a
    assert np.allclose(f.ends(0)[1], [5, 1]) and np.allclose(f.ends(2)[1], [5, 3])


def test_trace_goals_move_and_scale() -> None:
    f = figure([[0, 0]], [{"from": [1, 1], "to": [3, 2]}, {"from": [1, 1], "components": [2, 1]}])
    assert np.allclose(f.goal("vector", 0, None, 2.0), [5, 3])            # the tip, the tail stays
    assert np.allclose(f.goal("vector", 1, None, -1.0), [-2, -1])         # components
    assert np.allclose(f.goal("vector", 1, (0, 0), None), [-1, -1])
    assert np.allclose(f.goal("point", 0, (2, 2), None), [2, 2])
    g = figure([{"at": [1, 1], "name": "A"}], [{"to": "A"}, [1, 0], {"sum": ["vector1", "vector2"]}])
    assert "trace A instead" in g.trace_problem("vector", 0) and "is a sum" in g.trace_problem("vector", 2)
    assert g.trace_problem("vector", 1) is None and g.trace_problem("point", 0) is None


def test_mark_values() -> None:
    f = figure([{"at": [0, 0], "name": "A"}, {"at": [4, 0], "name": "B"}, {"at": [4, 3], "name": "C"}], [])
    mark = PlotMark.model_validate
    assert f.mark_value(mark({"segment": ["A", "B", "C"], "closed": True})) == pytest.approx(12)
    assert f.mark_value(mark({"dimension": ["A", "C"]})) == pytest.approx(5)
    assert f.mark_value(mark({"angle": ["B", "A", "C"]})) == pytest.approx(36.87, abs=0.01)
    assert mark_numbers([mark({"brace": ["A", "B"]}), mark({"angle": ["A", "B", "C"]}), mark({"brace": ["B", "C"]})]) == ["brace1", "angle1", "brace2"]


def test_geometry_range() -> None:
    assert geometry_range(np.array([1.0, 4.0]), True) == (-1.0, 5.0)
    assert geometry_range(np.array([1.0, 4.0]), False) == (0.0, 5.0)
    assert geometry_range(np.array([0.2, 0.4]), False) == (-0.5, 1.0)


@pytest.mark.parametrize(
    ("values", "message"),
    [({"points": [{"at": [0, 0], "name": "A"}], "marks": [{"brace": ["A", "B"]}]}, "marks[0].brace: no point or vector 'B'; the names are A"),
     ({"vectors": [{"sum": ["vector2", "vector1"]}, [1, 0]]}, "vectors[0]: no vector 'vector2'; the vectors before it are"),
     ({"vectors": [{"to": [1, 0], "components": [1, 1]}]}, "exactly one of to, components or sum (got to, components)"),
     ({"vectors": [{"sum": ["a"]}]}, "sum: list at least two vectors"),
     ({"vectors": [[1, 0], [0, 1], {"sum": ["vector1", "vector2"], "from": [1, 1]}]}, "a sum starts at its first vector's tail"),
     ({"points": [{"at": [0, 0], "name": "A"}, {"at": [1, 0], "name": "A"}]}, "two points are called 'A'"),
     ({"points": [{"at": [0, 0], "name": "v"}], "vectors": [{"to": [1, 1], "name": "v"}]}, "'v' names a point and a vector"),
     ({"points": [{"at": [0, 0], "name": "point2"}]}, "looks like a numbered target"),
     ({"points": [{"at": [0, 0], "name": "my point"}]}, "without spaces"),
     ({"vectors": [{"from": [1, 1], "to": [1, 1]}]}, "its tail and tip are the same point"),
     ({"marks": [{"angle": [[0, 0], [0, 0], [1, 1]]}]}, "a ray has no length"),
     ({"marks": [{"angle": [[0, 0], [1, 1]]}]}, "angle: list exactly 3 positions, [A, V, B]"),
     ({"marks": [{"brace": [[0, 0], [1, 0]], "angle": [[0, 0], [1, 0], [1, 1]]}]}, "exactly one of segment, brace, angle or dimension"),
     ({"marks": [{"angle": [[1, 0], [0, 0], [0, 1]], "side": "left"}]}, "side is for a brace or a dimension"),
     ({"marks": [{"brace": [[0, 0], [1, 0]], "label": "{angle}"}]}, "unknown field {angle}; it may use {length}"),
     ({"points": [[1, 1]], "x_range": [-1, 0]}, "(1, 1) is outside the plot"),
     ({"dots": [{"x": 1}], "points": [[1, 1]]}, "dots sit on a function: add functions"),
     ({"functions": ["x"]}, "x_range: give the x axis's"),
     ({}, "give at least one of functions, points, vectors or marks")],
)
def test_plane_param_errors(values: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=escaped(message)):
        plane(**values)


def test_plane_targets_ranges_aspect_and_steps() -> None:
    cls = cls_of("function_plot")
    p = plane(points=[{"at": [0, 0], "name": "A"}, [4, 3]], vectors=[{"to": [2, 1], "name": "a"}], marks=[{"segment": ["A", "point2"]}, {"brace": ["A", "point2"]}],
              axes=False)
    assert cls.target_names(p) == ["point1", "point:A", "point2", "vector1", "vector:a", "segment1", "brace1"]
    assert p.plot_ranges() == ((-1.0, 5.0), (-1.0, 4.0)) and p.shape() == "equal"
    assert [s.focus for s in cls.reveal_steps(p)] == ["point1", "point2", "vector1", "segment1", "brace1"]
    with_axes = plane(functions=["x^2"], x_range=[-2, 2], points=[[1, 5]])
    assert with_axes.plot_ranges()[1][1] >= 5.3 and with_axes.shape() == "auto"
    assert plane(functions=["x"], x_range=[0, 1], marks=[{"angle": [[1, 0], [0, 0], [1, 1]]}]).shape() == "equal"


def test_trace_of_plane_items_is_checked(make_project) -> None:
    beats = [{"text": "one two three", "actions": [
        {"trace": "point1", "to": [9, 9]}, {"trace": "vector:s", "scale": 2}, {"trace": "vector1", "to": 2}, {"trace": "point:A", "scale": 2},
        {"trace": "vector2", "scale": 10}, {"trace": "vector1", "to": [1, 2]}]}]
    spec = {"id": "p", "type": "function_plot", "beats": beats, "params": {
        "x_range": [-3, 3], "y_range": [-3, 3], "points": [{"at": [1, 1], "name": "A"}],
        "vectors": [[1, 0], [0, 1], {"sum": ["vector1", "vector2"], "name": "s"}]}}
    problems = check_project(load(make_project, [spec]))
    assert any("point1: (9, 9) is outside the plot" in p for p in problems)
    assert any("vector3 is a sum: it follows its vectors" in p for p in problems)
    assert any("vector1: to is a position [x, y] for a vector" in p for p in problems)
    assert any("point:A: scale is for a vector" in p for p in problems)
    assert any("vector2: (0, 10) is outside the plot" in p for p in problems)
    assert not any("vector1: (1, 2)" in p for p in problems)
    missing = check_project(load(make_project, [{**spec, "beats": [{"text": "one", "actions": [{"trace": "vector1"}]}]}]))
    assert any("trace needs to (where it ends) or, for a vector, scale" in p for p in missing)


def test_terms_colour_geometry_and_conflicts_are_found() -> None:
    spec = {"id": "p", "type": "function_plot", "beats": [{"text": "one"}], "params": {
        "points": [{"at": [0, 0], "label": "origin", "color": "primary"}], "vectors": [{"to": [1, 1], "label": "force", "color": "accent"}],
        "marks": [{"angle": [[1, 0], [0, 0], [0, 1]], "label": "angle", "color": "#FF0000"}]}}
    numbers = {"id": "n", "type": "number_line", "beats": [{"text": "one"}], "params": {
        "range": [0, 5], "intervals": [{"from": 1, "to": 2, "label": "range", "color": "accent"}], "jumps": [{"from": 1, "to": 3, "label": "step", "color": "primary"}]}}
    config = VideoConfig.model_validate(minimal_config(scenes=[spec, numbers], terms={"origin": "secondary", "force": "accent", "angle": "secondary",
                                                                                     "range": "secondary", "step": "primary"}))
    messages = [m for _, _, m in term_conflicts(config, Theme())]
    assert sorted(m.split(" colours ")[0] for m in messages) == ["interval 'range' color", "mark 'angle' color", "point 'origin' color"]


# ----- the number line (no rendering) ---------------------------------------------------------------


def test_interval_notation_and_number_line_params() -> None:
    p = line(points=[2, {"at": -1, "name": "a"}], intervals=["[-1, 3)", "(−∞, 0]", {"from": 1, "to": "inf"}], jumps=[[0, 3], {"from": 3, "to": 1}])
    assert [(i.start, i.to, i.closed) for i in p.intervals] == [(-1, 3, (True, False)), (-np.inf, 0, (False, True)), (1, np.inf, (True, False))]
    assert cls_of("number_line").target_names(p) == ["line", "point1", "point2", "point:a", "interval1", "interval2", "interval3", "jump1", "jump2"]
    assert [s.focus for s in cls_of("number_line").reveal_steps(p)] == ["point1", "point2", "interval1", "interval2", "interval3", "jump1", "jump2"]
    assert signed(3) == "+3" and signed(-2) == "−2" and signed(0.5) == "+0.5"
    assert jump_heights([(0, 3), (3, 5), (5, 1)], [3.0, 2.0, 4.0]) == pytest.approx([1.1, 0.84, 1.1 + 2 * 0.32])
    assert interval_lanes([(0, 2), (3, 4), (1, 3.5), (5, 6)]) == [0, 0, 1, 0]


@pytest.mark.parametrize(
    ("values", "message"),
    [({"range": [3, 1]}, "range [3, 1]: the second end must be greater"),
     ({"intervals": ["-1 to 3"]}, "write it like '[-1, 3)'"),
     ({"intervals": ["[3, 1]"]}, "the right end must be greater than the left"),
     ({"intervals": ["[a, 1]"]}, "interval bound 'a': write a number, inf or -inf"),
     ({"points": [9]}, "points[0].at: 9 is outside the range [-5, 5]"),
     ({"jumps": [[1, 1]]}, "the ends are the same"),
     ({"jumps": [{"from": 1, "to": 2, "label": "{by:.1f}"}]}, "write {by} without a format"),
     ({"step": 0.01}, "use a larger step"),
     ({"points": [{"at": 1, "name": "a"}, {"at": 2, "name": "a"}]}, "two points have the same name")],
)
def test_number_line_param_errors(values: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=escaped(message)):
        line(**values)


def test_number_line_trace_is_checked(make_project) -> None:
    beats = [{"text": "one two", "actions": [{"trace": "point1", "to": 9}, {"trace": "jump1", "to": 1}, {"trace": "point1", "to": [1, 1]}]}]
    spec = {"id": "n", "type": "number_line", "params": {"range": [0, 5], "points": [1], "jumps": [[1, 2]]}, "beats": beats}
    problems = check_project(load(make_project, [spec]))
    assert any("point1: 9 is outside the range [0, 5]" in p for p in problems)
    assert any("jump1: trace moves a point<N> of a number_line" in p for p in problems)
    assert any("point1: to is a number on the line" in p for p in problems)


# ----- rendering ----------------------------------------------------------------------------------


@pytest.mark.render
def test_geometry_moves_on_words_in_both_formats(make_project, media: Path) -> None:
    beats = [{"text": "a right triangle and two vectors"},
             {"text": "now move C up and scale a by two", "actions": [{"trace": "point:C", "to": [4, 4], "at": "@move"}, {"trace": "vector:a", "scale": 2, "at": "@scale"}]},
             {"text": "and now look closely at the angle at A", "actions": [{"reveal": "angle1", "at": "@angle"}]}]
    params = {"title": "Geometry", "x_range": [-1, 9], "y_range": [-1, 5], "reveal": "all",
              "points": [{"at": [0, 0], "name": "A"}, {"at": [4, 0], "name": "B"}, {"at": [4, 3], "name": "C", "label": "C ({x}, {y})", "decimals": 0}],
              "vectors": [{"from": [5, 0], "to": [6, 1], "name": "a"}, {"from": [5, 0], "components": [0, 1], "name": "b"}, {"sum": ["a", "b"], "label": "a + b"}],
              "marks": [{"segment": ["A", "B", "C"], "closed": True}, {"angle": ["B", "A", "C"], "label": "{angle}°"}, {"brace": ["A", "B"], "label": "4"},
                        {"dimension": ["A", "C"]}]}
    for size, fmt in (((160, 90), {}), ((90, 160), {"format": {"width": 1080, "height": 1920}})):
        scene = render(load(make_project, [{"id": "g", "type": "function_plot", "params": params, "beats": beats}], **fmt), "g", media, size=size)
        assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
        assert all(scene.is_shown(n) for n in type(scene).target_names(scene.params))
        geo = scene.geometry
        assert np.allclose(geo.figure.points[2], [4, 4]) and np.allclose(geo.figure.ends(0), [[5, 0], [7, 2]])
        assert np.allclose(geo.figure.ends(2), [[5, 0], [7, 3]])          # the sum followed a
        assert np.allclose(geo.points[2].dot.get_center(), scene.axes.point(4, 4))
        assert geo.points[2].label.content == "C (4, 4)" and geo.marks[3].label.content == "5.7"
        assert geo.marks[1].label.content == "45°"
        angle_start = [p.start for p in scene.play_log if p.beat == "g_b3" and not p.wait]
        assert angle_start and angle_start[0] > [t for t in scene.beat_log if t.beat_id == "g_b3"][0].start + 0.3   # on its word
        for mob in scene.mobjects:
            assert safe_area_of(size).contains(mob, tolerance=0.05), type(mob).__name__


@pytest.mark.render
def test_number_line_reveals_per_beat_and_traces(make_project, media: Path) -> None:
    beats = [{"text": "one two three"}, {"text": "four five six"}, {"text": "seven eight nine ten", "actions": [{"trace": "point:p", "to": 4, "at": "@nine", "until": "n_b4"}]},
             {"text": "eleven twelve"}]
    params = {"title": "Line", "range": [-2, 6], "points": [{"at": 1, "name": "p", "label": "{name} = {x}", "decimals": 0}],
              "intervals": ["[0, 2)", "(3, inf)"], "jumps": [[1, 4]]}
    for size, fmt in (((160, 90), {}), ((90, 160), {"format": {"width": 1080, "height": 1920}})):
        scene = render(load(make_project, [{"id": "n", "type": "number_line", "params": params, "beats": beats}], **fmt), "n", media, size=size)
        assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
        assert all(scene.is_shown(n) for n in type(scene).target_names(scene.params))
        plays = {b: [p.animations for p in scene.play_log if p.beat == b and not p.wait] for b in ("n_b1", "n_b2", "n_b3", "n_b4")}
        assert [sum("TraceMove" in a for a in plays[b]) for b in ("n_b3", "n_b4")] == [1, 1]   # there on "nine", back in beat 4
        assert scene.points[0].x == pytest.approx(1) and scene.points[0].live.content == "p = 1"
        for mob in scene.mobjects:
            assert safe_area_of(size).contains(mob, tolerance=0.05), type(mob).__name__


def test_lint_reads_operators_as_low_glyphs() -> None:
    """A live label such as 'x = −3' is as large as '3': '=' is not a capital-height glyph."""
    from vidgen.lint.layout_rules import cap_height

    assert cap_height({"kind": "text", "text": "x = −3", "font_px": 10.0}) == cap_height({"kind": "text", "text": "x x −3", "font_px": 10.0})
