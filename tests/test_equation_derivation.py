"""Step 33: the ``equation_derivation`` scene type (steps morphing into each other with matching
parts, notes, history / replace, alignment at ``=``, colours, result box, line breaks, TeX
errors) and its TeX helpers."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import pytest
from manim import MathTex, Transform, TransformMatchingShapes, tempconfig
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import beat_total, beats, plays, render
from test_builtin_scenes import cls_of, expected_duration, render_scene
from test_comparison_table import safe_area_of
from test_schema import errors
from vidgen import registry, schema
from vidgen.cli import check_project
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.scenes.equation_derivation import (
    _Line,
    break_lines,
    contains,
    isolated_source,
    marked_terms,
    morph,
    plain,
    readable_opacity,
    split_marked,
    term_key,
    tex_error_excerpt,
)
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
LATEX = pytest.mark.skipif(shutil.which("dvisvgm") is None, reason="LaTeX (dvisvgm) not installed")
SOLVE = ["{{ 2x }} + 3 = 11", {"tex": "{{ 2x }} = 8", "note": "Subtract 3"}, {"tex": "x = 4", "note": "Halve"}]


def params(**changes: Any) -> Any:
    return cls_of("equation_derivation").validate_params({"steps": SOLVE, **changes}, Theme())


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides)))


def scene_of(steps: list[Any], n_beats: int | None = None, **changes: Any) -> dict[str, Any]:
    return {"id": "d", "type": "equation_derivation", "params": {"steps": steps, **changes},
            "beats": beats(*([None] * (n_beats or len(steps))))}


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- TeX helpers ----------------------------------------------------------------------------------


def test_parts_are_whole_tokens_spaces_ignored() -> None:
    assert term_key("2 ab") == term_key("2ab") == "2 a b"
    assert term_key(r"\alpha  x") == r"\alpha x"
    assert contains(r"y = \exp(x)", "x") and not contains(r"\exp(y)", "x")      # x is not part of \exp
    assert not contains(r"\alphabet", r"\alpha") and contains(r"\alpha + b", r"\alpha")
    assert contains("{{ 2x }} + 1", "2x")


def test_double_brace_marks() -> None:
    assert split_marked("{{ 2x }} + 3 = {{ y }}") == [(" 2x ", True), (" + 3 = ", False), (" y ", True)]
    assert marked_terms("a + {{ b^{2} }}") == ["b^{2}"]
    assert plain("{{ 2x }} + 3") == " 2x  + 3"
    assert split_marked(r"\frac{{a}}{b}") == [(r"\frac{{a}}{b}", False)]       # {{ after a letter is plain TeX
    with pytest.raises(ValueError, match="not closed"):
        split_marked("{{ x + 1 = 2")
    with pytest.raises(ValueError, match="empty"):
        split_marked("{{  }} + 1")


def test_isolated_source_wraps_whole_tokens_safely() -> None:
    source, parts = isolated_source(r"{{ 2x }} + \exp(x) = a^x + \vec x", ["x", "="])
    assert [k for k, _ in parts] == ["2 x", "x", "x", "=", "x", "x"]   # the mark, x inside it, \exp untouched, the rest
    assert r"\exp(\special" in source                                   # \exp kept whole, its argument isolated
    assert "^{\\special" in source and "\\vec {\\special" in source       # one-argument places get braces
    source, parts = isolated_source(r"\left( x \right) + (y)", ["("])
    assert len(parts) == 1 and source.startswith(r"\left( x")         # a delimiter after \left is not wrapped
    longest, parts = isolated_source("2ab + ab", ["ab", "2ab"])
    assert [k for k, _ in parts] == ["2 a b", "a b"]                    # the longest part first


@pytest.mark.parametrize(
    ("tex", "every", "broken"),
    [("a = b = c", False, r"a & = b \\ & = c"),
     ("a = b = c", True, r"a \\ & = b \\ & = c"),
     ("a = b", False, None),                                            # one relation: nothing to break before
     ("a = b", True, r"a \\ & = b"),
     ("a + b", True, None),
     (r"f(x) = \frac{a = b}{c} \le d", False, r"f(x) & = \frac{a = b}{c} \\ & \le d"),   # only top-level relations
     (r"\left( a = b \right) = c", True, r"\left( a = b \right) \\ & = c"),
     (r"a &= b \\ &= c", True, None),                                   # the author broke it already
     ("{{ a = b }} = c", True, r"{{ a = b }} \\ & = c")],
)
def test_break_lines(tex: str, every: bool, broken: str | None) -> None:
    assert break_lines(tex, every) == broken


def test_tex_error_excerpt_reads_the_log(tmp_path: Path) -> None:
    log = tmp_path / "f.log"
    log.write_text(
        "This is pdfTeX\n! Undefined control sequence.\n<argument> ...aw <g id='vgpart000'>}x \\badcommand \n"
        "                                                  y\\special {dvisvgm:raw </g>} \nl.8 \\end{align*}\n",
        encoding="utf-8",
    )
    exc = ValueError(f"latex error converting to dvi. See log output above or the log file: {log}")
    assert tex_error_excerpt(exc) == "Undefined control sequence (at: x \\badcommand y)"
    assert tex_error_excerpt(ValueError("plain failure\nmore")) == "plain failure"


def test_readable_opacity_keeps_dimmed_text_readable() -> None:
    assert readable_opacity(["#FFFFFF"], "#000000", 0.45) == 0.45
    grey_on_white = readable_opacity(["#59606B"], "#F8F7F3", 0.45)
    assert 0.45 < grey_on_white < 0.7


# ----- params ---------------------------------------------------------------------------------------


def test_params_accept_strings_and_objects() -> None:
    p = params()
    assert [s.tex for s in p.steps] == ["{{ 2x }} + 3 = 11", "{{ 2x }} = 8", "x = 4"]
    assert (p.steps[1].note, p.steps[0].transition, p.mode, p.result, p.align_at) == ("Subtract 3", "auto", "history", "box", "=")
    assert p.term_names() == ["2x"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [({"steps": []}, "at least 1 item"),
     ({"steps": [" "]}, "tex cannot be empty"),
     ({"steps": ["x = \\frac{1}{2"]}, "unbalanced braces.*not closed"),
     ({"steps": ["x}"]}, "closes nothing"),
     ({"steps": ["{{ x = 1"]}, "a '{' is not closed"),
     ({"steps": ["{{ a }b}"]}, "'{{' is not closed"),
     ({"terms": ["q"]}, "terms: 'q' is not part of any step"),
     ({"colors": {"p": "accent"}}, "colors: 'p' is not part of any step"),
     ({"colors": {"x": "nonsense"}}, "nonsense"),
     ({"steps": [{"tex": "x", "match": ["x"]}]}, "first step has no step before it"),
     ({"steps": ["a + b", {"tex": "a + c", "match": ["c"]}]}, r"steps\[1\].match: 'c' is not part of step 1"),
     ({"steps": ["a + b", {"tex": "a", "transition": "spin"}]}, "'auto', 'shapes' or 'fade'"),
     ({"keep": 0}, "greater than or equal to 1"),
     ({"dim_opacity": 0.05}, "greater than or equal to 0.15")],
)
def test_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        params(**changes)


def test_target_names() -> None:
    cls = cls_of("equation_derivation")
    p = params(title="T", terms=["3"], colors={"x": "accent"}, steps=[*SOLVE[:2], {"tex": "x = 4", "match": ["x"]}])
    assert cls.target_names(p) == ["title", "step1", "step2", "step3", "note2", "result", "term:3", "term:x", "term:2x"]


def test_json_schema_takes_a_string_or_an_object_per_step() -> None:
    doc = schema.params_schema(registry.get("equation_derivation"), [Theme()])
    assert errors(doc, {"steps": ["a = b", {"tex": "a", "note": "n", "match": ["a"]}]}) == []
    assert errors(doc, {"steps": [3]}) != []


def test_validate_reports_bad_steps(make_project) -> None:
    project = Project.load(make_project(minimal_config(scenes=[scene_of(["a = {{ b }c}", "b"])])))
    problems = check_project(project)
    assert problems == ["scenes[0].params.steps[0].tex: a '{{' is not closed with '}}'"]


# ----- rendering ------------------------------------------------------------------------------------


@LATEX
def test_morph_pairs_marked_parts_then_shapes() -> None:
    with tempconfig({"verbosity": "ERROR"}):
        def line(tex: str) -> _Line:
            source, groups = isolated_source(tex, ["="])
            formula = MathTex(source)
            return _Line(formula, [(k, formula.id_to_vgroup_dict[g]) for k, g in groups], None)

        a, b = line("{{ 2x }} + 3 = 11"), line("{{ 2x }} = 8")
        anims = morph(a, b, "auto")
    assert [type(x) for x in anims] == [Transform, Transform, TransformMatchingShapes]   # 2x, =, the rest
    assert len(anims[0].mobject.family_members_with_points()) == 2                        # the two glyphs of 2x
    assert [type(x).__name__ for x in morph(a, b, "fade")] == ["FadeOut", "FadeIn"]


@LATEX
@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
@pytest.mark.slow
def test_history_keeps_earlier_steps_aligned_and_dimmed(make_project, media: Path, size: tuple[int, int]) -> None:
    project = load(make_project, [scene_of(SOLVE, colors={"x": "accent"}, title="Solve")])
    scene = render(project, "d", media, size=size)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert all(scene.is_shown(f"step{k}") for k in (1, 2, 3)) and scene.is_shown("result")
    live = [line.formula for line in scene._lines]
    assert [scene.on_screen_parts(f) != [] for f in live] == [False, False, True]   # earlier steps: their dimmed copies
    archived = [a for a in scene._archive if a is not None and scene.on_screen_parts(a)]
    assert len(archived) == 2 and all(max(m.get_fill_opacity() for m in a.family_members_with_points()) < 0.6 for a in archived)
    # aligned at '=': the same x for every step's sign
    signs = [scene._anchor(scene._lines[k]) for k in range(3)]
    assert max(signs) - min(signs) < 1e-6
    shown = [a for a in scene._archive if a is not None] + [live[2]]
    tops = [m.get_top()[1] for m in shown]
    assert tops == sorted(tops, reverse=True)                                       # stacked, oldest on top
    safe = safe_area_of(size)
    assert all(safe.contains(m, tolerance=0.02) for m in shown)
    # x keeps its colour in every step, the dimmed ones too
    accent = Theme().color("accent").lower()
    for line, mob in zip(scene._lines, shown):
        xs = [g for k, g in line.parts if k == "x"]
        assert xs and all(m.get_fill_color().to_hex().lower() == accent for g in xs for m in g.family_members_with_points())
    notes = [line.note for line in scene._lines[1:]]
    if size[0] > size[1]:   # 16:9: notes beside, level with their step
        assert all(n.get_left()[0] > live[2].get_right()[0] for n in notes)
        assert scene.on_screen_parts(scene._archive_notes[1]) and scene.on_screen_parts(notes[1])
    else:                   # 9:16: one note below the block
        assert notes[1].get_top()[1] < live[2].get_bottom()[1]
        assert not scene.on_screen_parts(notes[0]) and scene.on_screen_parts(notes[1])
    assert scene.on_screen_parts(scene._box)


@LATEX
@pytest.mark.render
@pytest.mark.slow
def test_replace_mode_shows_one_step_and_the_terms_of_the_current_step(make_project, media: Path) -> None:
    steps = ["(a+b)^2", {"tex": "(a+b)(a+b)", "match": ["(a+b)"]}, "a^2 + 2ab + b^2"]
    project = load(make_project, [scene_of(steps, mode="replace", terms=["2ab"], result="highlight")])
    scene = render(project, "d", media)
    assert [scene.is_shown(f"step{k}") for k in (1, 2, 3)] == [False, False, True]
    assert scene.is_shown("term:2ab") and not any(scene.is_shown(t) for t in scene.find_targets("term:(a+b)"))
    assert scene._box.get_fill_opacity() > 0 and scene._box.get_stroke_width() == 0   # a band behind the result
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)


@LATEX
@pytest.mark.render
@pytest.mark.slow
def test_keep_scrolls_the_oldest_steps_away(make_project, media: Path) -> None:
    steps = ["a = 1", "b = 2", "c = 3", "d = 4"]
    project = load(make_project, [scene_of(steps, keep=2, result="none")])
    scene = render(project, "d", media)
    assert [scene.is_shown(f"step{k}") for k in (1, 2, 3, 4)] == [False, False, True, True]
    assert scene._box is None and "result" in [n for t in scene.targets for n in t.names]


@LATEX
@pytest.mark.render
def test_term_target_means_the_current_step(make_project, media: Path) -> None:
    acts = beats(None, [{"highlight": "term:x", "at": 0.5}])
    project = load(make_project, [{"id": "d", "type": "equation_derivation", "params": {"steps": ["x + 1 = 2", "x = 1"], "terms": ["x"]}, "beats": acts}])
    scene = render(project, "d", media)
    highlight = Theme().color("highlight").lower()
    first, second = scene._lines
    colour = lambda line: {m.get_fill_color().to_hex().lower() for k, g in line.parts if k == "x" for m in g.family_members_with_points()}
    assert colour(second) == {highlight}
    assert highlight not in {m.get_fill_color().to_hex().lower() for m in scene._archive[0].family_members_with_points()}


@LATEX
@pytest.mark.render
@pytest.mark.slow
def test_transform_jump_skips_the_middle_step_and_still_boxes_the_result(make_project, media: Path) -> None:
    acts = beats(None, [{"transform": "step2", "into": "step3", "at": 0.3}], None)
    project = load(make_project, [{"id": "d", "type": "equation_derivation", "params": {"steps": ["a = b", "a = c", "a = d"]}, "beats": acts}])
    scene = render(project, "d", media)
    assert scene.is_shown("step3") and not scene.is_shown("step2")
    assert scene.on_screen_parts(scene._box)
    assert all("_Swap" not in "".join(a) for a in plays(scene, "d_b3"))   # beat 3 only adds the box


@LATEX
@pytest.mark.render
@pytest.mark.slow
def test_long_steps_break_at_relations_in_portrait(make_project, media: Path) -> None:
    long = r"\mathrm{Var}(X) = \mathbb{E}\left[(X - \mu)^2\right] = \mathbb{E}\left[X^2 - 2\mu X + \mu^2\right]"
    project = load(make_project, [scene_of([long, r"\sigma^2 = \mathbb{E}[X^2] - \mu^2"])])
    portrait = render(project, "d", media, size=(90, 160))
    assert "\\\\" in portrait._lines[0].tex and "\\\\" not in portrait._lines[1].tex
    assert portrait._lines[0].formula.tex_string == long        # lint and the layout dump show the step as written
    landscape = render(project, "d", media, size=(160, 90))
    assert "\\\\" not in landscape._lines[0].tex


@LATEX
@pytest.mark.render
@pytest.mark.slow
def test_too_long_to_read_warns(make_project, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    long = " + ".join(f"x_{{{k}}}" for k in range(40)) + " = y"
    project = load(make_project, [scene_of([long])])
    with caplog.at_level(logging.WARNING, logger="vidgen.scenes"):
        render(project, "d", media)
    assert "below the readable size" in caplog.text


@LATEX
@pytest.mark.render
def test_latex_errors_name_the_step_and_show_tex_s_message(make_project, media: Path) -> None:
    project = load(make_project, [scene_of(["x = 1", r"x = \badcommand{2}"])])
    with pytest.raises(VidgenError, match=r"scene 'd': step 2 does not compile: Undefined control sequence \(at: .*\\badcommand.*'x = \\badcommand\{2\}'"):
        render(project, "d", media)


@LATEX
@pytest.mark.render
@pytest.mark.slow
def test_silent_scene_and_more_steps_than_beats(make_project, media: Path) -> None:
    steps = ["a = 1", "a = 2", "a = 3", "a = 4"]
    project = load(make_project, [
        {"id": "s", "type": "equation_derivation", "params": {"steps": steps}, "duration": 2.0},
        {"id": "m", "type": "equation_derivation", "params": {"steps": steps}, "beats": beats(None, None)},
    ])
    for scene_id in ("s", "m"):
        scene, duration, _ = render_scene(project, scene_id, media, 160, 90)
        assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
