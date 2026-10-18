"""Step 160: the ``function_plot`` scene type (maths axes, functions written as expressions and
parsed safely, dots with live value labels and tangents, shaded areas) and the ``trace`` action:
the parser, the labels, the layout helpers, params and targets, checks, and tiny renders in 16:9
and 9:16 on spoken words."""

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
from vidgen.cli import check_project
from vidgen.config import VideoConfig
from vidgen.project import Project
from vidgen.regions import Region
from vidgen.scenes.function_plot import auto_y_range, clip_segment, curve_runs, fill_label, label_problem
from vidgen.mathexpr import parse_expression, pretty_expression, split_definition
from vidgen.terms import term_conflicts
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def params(**values: Any) -> Any:
    return cls_of("function_plot").validate_params({"functions": ["x^2"], "x_range": [-2, 2], **values}, Theme())


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides)))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- the expression parser --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "x", "value"),
    [("x^2 - 1", 3, 8), ("2x + 1", 2, 5), ("-x^2", 2, -4), ("2^-1", 0, 0.5), ("3(x + 1)", 1, 6), ("x(x - 1)", 3, 6),
     ("(x + 1)(x - 1)", 3, 8), ("2 sin(x)^2", np.pi / 2, 2), ("e^x", 1, np.e), ("pi x", 1, np.pi), ("2πx", 0.5, np.pi),
     ("x**3", 2, 8), ("2^3^2", 0, 512), ("x²−1", 2, 3), ("max(x, 0) + min(x, 0)", -2, -2), ("sqrt(abs(x))", -4, 2),
     ("exp(-x^2/2)", 0, 1), ("log10(x) + ln(e)", 100, 3), ("2e3", 0, 2000), ("1/2x", 4, 2)],
)
def test_expressions_evaluate(text: str, x: float, value: float) -> None:
    assert parse_expression(text).at(x) == pytest.approx(value)


def test_undefined_values_are_nan_and_arrays_work() -> None:
    f = parse_expression("sqrt(x) + 1/x")
    values = f(np.array([-1.0, 0.0, 4.0]))
    assert np.isnan(values[0]) and np.isnan(values[1]) and values[2] == pytest.approx(2.25)
    assert parse_expression("3").at(5) == 3 and parse_expression("x^2").slope(3) == pytest.approx(6)


def test_a_function_may_call_one_defined_before() -> None:
    f = parse_expression("x^2")
    g = parse_expression("f(x + 1) / 2", {"f": f})
    assert g.at(1) == pytest.approx(2) and g.names == ("f",)


@pytest.mark.parametrize(
    ("text", "message"),
    [("sinn(x)", "unknown name 'sinn' at character 1 (did you mean sin"), ("x +", "expected a number, x, a function or '(' at character 4, found the end"),
     ("2 $ 3", "unexpected '$' at character 3"), ("", "the expression is empty"), ("sin x", "sin needs its argument in brackets"),
     ("max(x)", "max takes 2 arguments, got 1"), ("(x", "expected ')'"), ("__import__('os')", "unexpected"),
     ("x.real", "unexpected"), ("y + 1", "unknown name 'y'"), ("f(x)", "unknown name 'f'")],
)
def test_expression_errors(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(")", r"\)").replace("$", r"\$").replace("+", r"\+")):
        parse_expression(text)


def test_definitions_and_pretty_labels() -> None:
    assert split_definition("f(x) = x^2") == ("f", "x^2")
    assert split_definition(" y = 3x ") == (None, "3x") and split_definition("x^2") == (None, "x^2")
    assert [pretty_expression(t) for t in ("x^2 - 1", "2*x + 1", "x**3", "pi*x", "x^-1", "3*sin(x)")] == ["x² − 1", "2x + 1", "x³", "π·x", "x⁻¹", "3sin(x)"]


# ----- labels and layout helpers ------------------------------------------------------------------


def test_label_templates() -> None:
    assert fill_label("{name}({x}) = {y}", {"name": "f", "x": 1.0, "y": -0.04}, 1) == "f(1.0) = 0.0"   # never -0.0
    assert fill_label("slope {slope:.3f}", {"slope": -2.0}, 1) == "slope −2.000"
    assert label_problem("{x} {nope}", ("x", "y")) == "label '{x} {nope}': unknown field {nope}; it may use {x}, {y}"
    assert "write { and } as {{ and }}" in (label_problem("{x", ("x",)) or "")
    assert label_problem("{y:q}", ("y",)) is not None and label_problem("{{y}} {y:+.2f}", ("y",)) is None


def test_auto_y_range_trims_an_asymptote_and_reaches_zero() -> None:
    lo, hi = auto_y_range(parse_expression("x^2 + 1")(np.linspace(-2, 2, 101)))
    assert lo < 0 < 5 < hi < 5.5   # 0 is near: the range reaches it
    lo, hi = auto_y_range(parse_expression("1/x")(np.linspace(-3, 3, 600)))
    assert -40 < lo < -3 and 3 < hi < 40
    with pytest.raises(ValueError, match="no function has a value"):
        auto_y_range(np.array([np.nan]))


def test_curve_runs_split_at_asymptotes_and_end_on_the_edge() -> None:
    runs = curve_runs(parse_expression("1/x"), -2, 2, (-3, 3), 400)
    assert len(runs) == 2
    assert runs[0][-1][1] == pytest.approx(-3) and runs[1][0][1] == pytest.approx(3)
    assert len(curve_runs(parse_expression("tan(x)"), -4, 4, (-3, 3), 800)) == 3
    assert curve_runs(parse_expression("sqrt(x)"), -1, 4, (0, 2), 101)[0][0][0] >= 0


def test_clip_segment() -> None:
    a, b = clip_segment(np.array([-2.0, 0, 0]), np.array([2.0, 0, 0]), Region(-1, -1, 1, 1))
    assert a[0] == pytest.approx(-1) and b[0] == pytest.approx(1)
    a, b = clip_segment(np.array([-2.0, 5, 0]), np.array([2.0, 5, 0]), Region(-1, -1, 1, 1))
    assert np.allclose(a, b)


# ----- params, targets and checks -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "message"),
    [({"x_range": [2, 1]}, "x_range [2, 1]: the second end must be greater"),
     ({"functions": ["x^"]}, "functions[0]: 'x^': expected a number"),
     ({"functions": ["x^2", "g(x) = h(x)", "h(x) = 1"]}, "a function may use only those before it, not h"),
     ({"functions": ["f(x) = x", "f(x) = 2x"]}, "two functions are called 'f'"),
     ({"functions": [{"expr": "x", "name": "sin"}]}, "'sin' is the variable, a constant or a built-in function"),
     ({"functions": [{"expr": "f(x) = x", "name": "g"}]}, "expr names the function 'f' but name is 'g'"),
     ({"functions": ["sqrt(x - 5)"]}, "has no value on the x range"),
     ({"dots": [{"x": 3}]}, "dots[0].x: x = 3 is outside f's drawn range [-2, 2]"),
     ({"functions": ["1/x"], "dots": [{"x": 0}]}, "dots[0].x: f has no value at x = 0"),
     ({"dots": [{"x": 1, "on": "g"}]}, "dots[0]: no function 'g'; the functions are f"),
     ({"dots": [{"x": 1, "label": "{z}"}]}, "unknown field {z}"),
     ({"areas": [{"between": [1, 0]}]}, "between [1.0, 0.0]: the second end must be greater"),
     ({"functions": ["x^2", {"expr": "x", "domain": [0, 1]}], "areas": [{"under": "f", "over": "g", "between": [0, 1.5]}]}, "x = 1.5 is outside g's drawn range [0, 1]"),
     ({"areas": [{"between": [0, 1], "label": "{area"}]}, "label '{area'")],
)
def test_param_errors(values: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message.replace("[", r"\[").replace("]", r"\]").replace("(", r"\(").replace(")", r"\)").replace("^", r"\^")):
        params(**values)


def test_names_targets_and_reveal_steps() -> None:
    cls = cls_of("function_plot")
    p = params(title="T", functions=["x^2", "loss(x) = 2 - x", {"expr": "x"}], dots=[{"x": 1, "tangent": True}, {"x": 0, "on": "loss"}], areas=[{"between": [0, 1]}])
    assert p.function_names() == ["f", "loss", "g"]
    assert cls.target_names(p) == ["title", "axes", "function1", "function:f", "function2", "function:loss", "function3", "function:g",
                                   "dot1", "tangent1", "dot2", "area1"]
    assert [(s.focus, s.result) for s in cls.reveal_steps(p)] == [("function1", None), ("function2", "fall"), ("function3", "rise"),
                                                                   ("dot1", None), ("dot2", None), ("area1", None)]


def plot_scene(beats: list[dict[str, Any]], **values: Any) -> dict[str, Any]:
    return {"id": "p", "type": "function_plot", "params": {"functions": ["x^2"], "x_range": [-2, 2], **values}, "beats": beats}


def test_trace_is_checked(make_project) -> None:
    beats = [{"text": "one two three", "actions": [{"trace": "dot1", "to": 5}, {"trace": "function1", "to": 1}, {"trace": "area1", "to": -3}]}]
    problems = check_project(load(make_project, [plot_scene(beats, dots=[{"x": 0}], areas=[{"between": [0, 1]}])]))
    assert any("dot1: x = 5 is outside f's drawn range [-2, 2]" in p for p in problems)
    assert any("function1: trace moves a dot<N> or an area<N>" in p for p in problems)
    assert any("area1: x = -3 is outside" in p for p in problems)
    other = {"id": "b", "type": "bullets", "params": {"items": ["a"]}, "beats": [{"text": "one", "actions": [{"trace": "item1", "to": 1}]}]}
    assert any("trace moves the dots and areas of a function_plot" in p for p in check_project(load(make_project, [other])))


def test_a_term_coloured_otherwise_by_a_function_or_area_is_a_conflict() -> None:
    spec = plot_scene([{"text": "one"}], functions=[{"expr": "x", "name": "loss", "color": "primary"}], areas=[{"between": [0, 1], "label": "loss {area}", "color": "accent"}])
    config = VideoConfig.model_validate(minimal_config(scenes=[spec], terms={"loss": "secondary"}))
    messages = [m for _, _, m in term_conflicts(config, Theme())]
    assert len(messages) == 2 and all("the term 'loss'" in m for m in messages)


# ----- rendering ----------------------------------------------------------------------------------


@pytest.mark.render
def test_dots_trace_on_words_in_both_formats(make_project, media: Path) -> None:
    beats = [{"text": "the parabola and its tangent at one"},
             {"text": "now the dot moves to the right until here", "actions": [{"reveal": "tangent1", "at": "@moves"}, {"trace": "dot1", "to": 1.5, "at": "@right"}]},
             {"text": "and the area under it grows", "actions": [{"trace": "area1", "to": 2, "at": "@grows"}]}]
    values = {"title": "Slope", "functions": ["x^2", {"expr": "2x - 1", "dashed": True}], "dots": [{"x": -1, "tangent": True, "guides": True, "label": "slope {slope}"}],
              "areas": [{"between": [0, 1], "label": "A = {area}"}], "reveal": "all"}
    for size, fmt in (((160, 90), {}), ((90, 160), {"format": {"width": 1080, "height": 1920}})):
        scene = render(load(make_project, [plot_scene(beats, **values)], **fmt), "p", media, size=size)
        assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
        assert all(scene.is_shown(n) for n in type(scene).target_names(scene.params))
        dot, area = scene.dots[0], scene.areas[0]
        assert dot.x == pytest.approx(1.5) and np.allclose(dot.dot.get_center(), scene.axes.point(1.5, 2.25))
        assert dot.shown_text == "slope 3.0" and area.shown_text == "A = 2.67"
        assert dot.live.text.original_text == "slope 3.0"   # what the layout dump and lint read
        direction = dot.tangent.get_end() - dot.tangent.get_start()
        ux, uy = scene.axes.units
        assert direction[1] / direction[0] == pytest.approx(3 * uy / ux, rel=1e-3)   # the tangent turned with the dot
        tangent_start = [p.start for p in scene.play_log if p.beat == "p_b2" and "Create" in p.animations]
        assert tangent_start and tangent_start[0] > [t for t in scene.beat_log if t.beat_id == "p_b2"][0].start + 0.5   # on its word
        for mob in scene.mobjects:
            assert safe_area_of(size).contains(mob, tolerance=0.05), type(mob).__name__


@pytest.mark.render
def test_per_beat_reveal_and_trace_back(make_project, media: Path) -> None:
    beats = [{"text": "one two three"}, {"text": "four five six"}, {"text": "seven eight nine", "actions": [{"trace": "dot1", "to": 2, "at": 0.3, "until": "p_b4"}]},
             {"text": "ten eleven twelve"}]
    scene = render(load(make_project, [plot_scene(beats, functions=["x^2", "1/x"], dots=[{"x": 1, "on": "g"}], y_range=[-4, 4], aspect="equal")]), "p", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    plays = {b: [p.animations for p in scene.play_log if p.beat == b and not p.wait] for b in ("p_b1", "p_b2", "p_b3", "p_b4")}
    assert plays["p_b1"] and plays["p_b2"]   # f with the axes, then g
    assert [sum("_Trace" in a for a in plays[b]) for b in ("p_b3", "p_b4")] == [1, 1]   # the dot appears and moves; back in beat 4
    assert scene.dots[0].x == pytest.approx(1)
    ux, uy = scene.axes.units
    assert ux == pytest.approx(uy)


def test_lint_reads_a_typographic_minus_as_a_small_glyph() -> None:
    """Tick labels write negative numbers with U+2212; the cap height is that of the digits."""
    from vidgen.lint.layout_rules import cap_height

    assert cap_height({"kind": "text", "text": "−3", "font_px": 10.0}) == cap_height({"kind": "text", "text": "-3", "font_px": 10.0})
