"""One colour per concept (DESIGN.md §87.3): the video's ``terms:`` map, where it colours text
(fit_text, T, captions, callouts, line series, equations), the scene opt-out, validation, the
``concept_colors`` lint rule, and one tiny render."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from manim import tempconfig
from vidgen.errors import VidgenError

from conftest import minimal_config
from vidgen.cli import project_problems
from vidgen.config import ActionConfig, ConceptColorsRule, VideoConfig, parse_config
from vidgen.project import Project
from vidgen.terms import (
    Term,
    active_terms,
    find_term,
    resolve_terms,
    scene_terms,
    set_active_terms,
    term_conflicts,
    term_spans,
    term_t2c,
    using_terms,
)
from vidgen.theme import Theme

LOSS = Term("loss", "#FF0000")
GRADIENT = Term("gradient", "#00FF00")
RATE = Term("learning rate", "#0000FF", ("\\eta",))
TERMS = (LOSS, GRADIENT, RATE)


@pytest.fixture
def text_media(tmp_path: Path) -> Iterator[None]:
    with tempconfig({"media_dir": str(tmp_path / "media"), "verbosity": "ERROR"}):
        yield


def config(terms: dict[str, Any], scenes: list[dict[str, Any]] | None = None, **extra: Any) -> VideoConfig:
    data = minimal_config(terms=terms, **extra)
    if scenes is not None:
        data["scenes"] = scenes
    return parse_config(data)


# ----- matching ------------------------------------------------------------------------------------


def test_spans_whole_words_any_case_and_plurals() -> None:
    text = "Loss, losses and glossy; the GRADIENTS of the loss's slope"
    found = [(text[a:b], t.name) for a, b, t in term_spans(text, TERMS)]
    assert found == [("Loss", "loss"), ("losses", "loss"), ("GRADIENTS", "gradient"), ("loss", "loss")]


def test_spans_phrase_across_spaces_and_longest_first() -> None:
    rate = Term("rate", "#123456")
    text = "a learning\n rate, then a rate"
    found = [(text[a:b], t.name) for a, b, t in term_spans(text, (rate, RATE))]
    assert found == [("learning\n rate", "learning rate"), ("rate", "rate")]


def test_find_term_and_t2c_leave_explicit_colours() -> None:
    assert find_term("the gradient of the loss", TERMS) is GRADIENT
    assert find_term("nothing here", TERMS) is None
    text = "loss and gradient"
    assert term_t2c(text, TERMS) == {"[0:4]": "#FF0000", "[9:17]": "#00FF00"}
    assert term_t2c(text, TERMS, {"[0:2]": "#FFFFFF"}) == {"[9:17]": "#00FF00"}
    assert term_t2c(text, TERMS, {"gradient": "#FFFFFF"}) == {"[0:4]": "#FF0000"}


def test_using_terms_restores_the_previous_ones() -> None:
    set_active_terms((LOSS,))
    with using_terms(TERMS):
        assert active_terms() == TERMS
    assert active_terms() == (LOSS,)
    set_active_terms(())


# ----- config --------------------------------------------------------------------------------------


def test_config_terms_resolve_against_the_theme() -> None:
    cfg = config({"loss": "accent", "Learning rate": {"color": "#E07A5F", "tex": "\\eta"}})
    theme = Theme()
    terms = resolve_terms(cfg, theme)
    assert terms == (Term("loss", theme.color("accent")), Term("Learning rate", "#E07A5F", ("\\eta",)))
    assert scene_terms(cfg, cfg.scenes[0], theme) == terms


def test_scene_opts_out() -> None:
    data = minimal_config(terms={"loss": "accent"})
    data["scenes"][0]["terms"] = False
    cfg = parse_config(data)
    assert scene_terms(cfg, cfg.scenes[0], Theme()) == ()
    assert scene_terms(cfg, cfg.scenes[1], Theme()) != ()


@pytest.mark.parametrize(
    ("terms", "message"),
    [
        ({"loss": "accent", "LOSS": "primary"}, "are the same term"),
        ({"--": "accent"}, "has no word in it"),
        ({"loss": "not a colour!"}, "String should match pattern"),
        ({"loss": {"color": "accent", "tex": "{x"}}, "do not balance"),
        ({"loss": {"color": "accent", "tex": [" "]}}, "cannot be empty"),
        ({"loss": {"colour": "accent"}}, "did you mean 'color'"),
    ],
)
def test_config_terms_errors(terms: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        config(terms)


def test_validate_names_an_unknown_theme_colour(make_project) -> None:
    root = make_project(minimal_config(terms={"loss": "acent", "gradient": "#E07A5F"}))
    problems = [str(p) for p in project_problems(Project.load(root))]
    assert any("terms.loss" in p and "unknown theme color 'acent'" in p for p in problems), problems
    assert not any("gradient" in p for p in problems)


# ----- where the colours go (builds text, no rendering) ---------------------------------------------


def glyph_colors(mob: Any) -> list[str]:
    return [g.get_color().to_hex().upper() for g in mob.family_members_with_points()]


def test_fit_text_and_t_draw_terms(text_media: None) -> None:
    from vidgen.helpers import styled
    from vidgen.layout import fit_text

    theme = Theme()
    with using_terms(TERMS):
        block = fit_text("the loss falls", 20.0, theme=theme)
        assert glyph_colors(block).count("#FF0000") == 4
        assert "#FF0000" not in glyph_colors(fit_text("the loss falls", 20.0, theme=theme, terms=False))
        lit = fit_text("the loss falls", 20.0, theme=theme, highlights={"loss": "#FFFF00"})
        assert "#FF0000" not in glyph_colors(lit) and glyph_colors(lit).count("#FFFF00") == 4
        from manim import NORMAL, Text

        text = styled(Text, theme, "a gradient", "body", "text", NORMAL)
        assert glyph_colors(text).count("#00FF00") == 8
    assert "#FF0000" not in glyph_colors(fit_text("the loss falls", 20.0, theme=theme))


def test_callout_takes_the_term_colour() -> None:
    from vidgen.scenes.callout_action import CalloutAction

    def made(**options: Any) -> CalloutAction:
        cfg = ActionConfig.model_validate({"action": "callout", "target": "item1", **options})
        return CalloutAction(CalloutAction.Options.model_validate(options), cfg)

    with using_terms(TERMS):
        assert made(label="the loss").color() == "#FF0000"
        assert made(label="the loss", color="primary").color() == "primary"
        assert made(label="other").color() == "highlight"


def test_line_series_named_a_term() -> None:
    from vidgen.scenes.line_chart import LineChart

    with using_terms(TERMS):
        assert LineChart._term_color("Loss") == "#FF0000"
        assert LineChart._term_color("training loss") is None


def test_tex_parts_of_terms() -> None:
    from vidgen.scenes.equation_derivation import term_tex_colors

    assert term_tex_colors("w - \\eta \\nabla L", TERMS) == {"\\eta": "#0000FF"}
    assert term_tex_colors("\\theta", (Term("t", "#111111", ("t",)),)) == {}


def test_equation_colours_term_tex_and_keeps_targets(text_media: None) -> None:
    from types import SimpleNamespace

    from vidgen.layout import latex_available
    from vidgen.scenes.equation import Equation

    if not latex_available():
        pytest.skip("needs LaTeX")
    me = SimpleNamespace(params=Equation.Params(latex="w - \\eta g", terms=["g"]), theme=Theme(), spec=SimpleNamespace(id="eq"))
    with using_terms(TERMS):
        formula = Equation._tex(me, "w - \\eta g", 48)
    assert formula.tex_string == "w - \\eta g"
    assert {g.get_color().to_hex().upper() for g in Equation._term_part(formula, "\\eta").family_members_with_points()} == {"#0000FF"}
    assert Equation._term_part(formula, "g") is not None


# ----- lint ----------------------------------------------------------------------------------------


def test_conflicts_with_scene_colour_settings() -> None:
    scenes = [
        {"id": "t", "type": "title", "params": {"title": "The loss", "highlight": "loss", "highlight_color": "primary"}, "beats": [{"text": "Hi."}]},
        {"id": "c", "type": "line_chart", "params": {"x": [1, 2], "series": [{"name": "loss", "values": [1, 2], "color": "#FF0000"}, {"name": "gradient", "values": [1, 2], "color": "primary"}]}, "beats": [{"text": "Hi."}]},
        {"id": "d", "type": "equation_derivation", "params": {"steps": ["\\eta x"], "colors": {"\\eta": "highlight"}}, "beats": [{"text": "Hi."}]},
        {"id": "b", "type": "bullets", "params": {"items": ["a"]}, "beats": [{"id": "b1", "text": "Hi.", "actions": [{"callout": "item1", "label": "loss", "color": "primary"}]}]},
        {"id": "off", "type": "title", "terms": False, "params": {"title": "The loss", "highlight": "loss"}, "beats": [{"text": "Hi."}]},
    ]
    cfg = config({"loss": "#FF0000", "gradient": "#00FF00", "learning rate": {"color": "#0000FF", "tex": "\\eta"}}, scenes)
    found = term_conflicts(cfg, Theme())
    assert [(scene, beat) for scene, beat, _ in found] == [("t", None), ("c", None), ("d", None), ("b", "b1")]
    assert "highlight_color colours the term 'loss' primary" in found[0][2]
    assert "series 'gradient' color" in found[1][2]
    assert "'\\eta', the TeX of the term 'learning rate'" in found[2][2]
    assert "a callout's color" in found[3][2]


def test_rule_counts_colours_and_checks_contrast() -> None:
    from vidgen.lint.rules import SceneContext
    from vidgen.lint.term_rule import concept_colors, term_issues

    theme = Theme()
    many = {f"term{k}": color for k, color in enumerate(["accent", "primary", "secondary", "tertiary", "highlight", "#E07A5F"])}
    cfg = config({**many, "faint": theme.background})
    issues = term_issues(cfg, theme, "intro", ConceptColorsRule())
    assert [message.split(";")[0] for _, message, _, _ in issues] == [
        "terms: uses 7 different colours",
        f"the term 'faint' ({theme.background}) has contrast 1.00:1 on the background {theme.background}",
    ]
    assert term_issues(cfg, theme, "main", ConceptColorsRule()) == []   # reported once, on the first scene
    assert len(term_issues(cfg, theme, "intro", ConceptColorsRule(max_colors=8, min_contrast=1))) == 0
    ctx = SceneContext("intro", {"fps": 5, "beats": [{"id": "intro_b1", "start": 0.0}]}, Path("."), term_issues=issues)
    assert [i.beat for i in concept_colors(ctx, ConceptColorsRule())] == ["intro_b1", "intro_b1"]


# ----- one tiny render -----------------------------------------------------------------------------


@pytest.mark.render
def test_terms_drawn_and_opted_out(make_project, tmp_path: Path) -> None:
    from vidgen import extensions, registry
    from vidgen.render.worker import frame_size

    card = {"type": "text_card", "params": {"text": "loss"}, "beats": [{"text": "The loss."}]}
    root = make_project(minimal_config(terms={"loss": "#FF0000"}, scenes=[{"id": "on", **card}, {"id": "off", "terms": False, **card}]))
    project = Project.load(root)
    w, h = 160, 90
    fw, fh = frame_size(w, h)
    reds = {}
    for scene_id in ("on", "off"):
        settings = {"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": 5,
                    "media_dir": str(tmp_path / "media"), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR", "output_file": scene_id}
        with tempconfig(settings):
            spec = project.scene(scene_id)
            scene = registry.get(spec.type).cls(spec, project, extensions.activate(project))
            scene.render()
            pixels = scene.renderer.get_frame()
        reds[scene_id] = int(((pixels[..., 0] > 180) & (pixels[..., 1] < 60) & (pixels[..., 2] < 60)).sum())
        assert active_terms() == ()   # the scene's terms end with it
    assert reds["on"] > 5 and reds["off"] == 0, reds
