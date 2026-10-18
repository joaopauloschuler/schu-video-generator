"""Review of Phase P (Step 164): the example `examples/gradient-descent` through `vidgen validate`
(16:9 and its 9:16 variant), and the fixes found on the way: a `code_morph` version revealed by
an action morphs for the scene's own 1.5 s, a `diagram` node revealed on a word brings the edges
to the nodes on screen, a dot's live label keeps clear of the plane's labels, a number line's
jump labels show the decimals their ends need and keep clear of each other, the axes' numbers
stay readable on a shaded area, and lint measures sub- and superscript digits as small glyphs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from manim import Rectangle, Text

from conftest import minimal_config
from test_actions import plays, render
from vidgen import runtime
from vidgen.cli import main, validate_all
from vidgen.lint.layout_rules import cap_height
from vidgen.project import Project
from vidgen.scenes.code_morph import MORPH_SECONDS
from vidgen.scenes.math_axes import LABEL_PLATE_Z, math_axes
from vidgen.regions import Region
from vidgen.scenes.number_line import ends_places, lift_clear, signed
from vidgen.textnorm import normalize_text, normalize_words

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "gradient-descent"
NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def load(make_project, scenes: list[dict[str, Any]]) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- the example -------------------------------------------------------------------------------


@pytest.mark.parametrize("variant", [None, "short"])
def test_the_example_validates_and_uses_phase_p(variant: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "gd", ignore=shutil.ignore_patterns("build", "output", "exports", "audio"))
    assert main(["validate", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    project = Project.load(root, variant=variant)
    assert validate_all(project, keep_going=True)[0] == []
    types = {s.type for s in project.config.scenes}
    assert {"function_plot", "number_line", "code_morph", "terminal", "line_chart", "equation"} <= types
    assert set(project.config.terms) == {"loss", "gradient", "learning rate"}
    anchored = [a.anchor for s in project.config.scenes for b in s.beats for a in b.actions if a.anchor]
    assert len(anchored) == 18   # actions on spoken words
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("tangent: true", "areas:", "trace: area1", "vectors:", "angle:", "segment:", "scale: 2", "jumps:",
                 "reveal: version2", "highlight: changed", "carry:", "changes:", "trace: \"series:loss\"", "reveal: change2"):
        assert used in text, used


# ----- number line labels ------------------------------------------------------------------------


def test_jump_labels_show_the_decimals_their_ends_need() -> None:
    assert ends_places(2.25, 2.625) == 3 and ends_places(0, 1.5) == 1 and ends_places(2, 5) == 0
    assert signed(2.625 - 2.25, ends_places(2.25, 2.625)) == "+0.375"   # was +0.4
    assert signed(2.25 - 1.5, ends_places(1.5, 2.25)) == "+0.75" and signed(-2, 0) == "−2"


def test_overlapping_labels_are_lifted_clear() -> None:
    fixed = Rectangle(width=1, height=0.3).move_to([0.8, 0, 0])
    first = Rectangle(width=1, height=0.3).move_to([0, 0, 0])
    second = Rectangle(width=1, height=0.3).move_to([0.5, 0.1, 0])
    apart = Rectangle(width=1, height=0.3).move_to([5, 0, 0])
    lift_clear([first, second, apart], [fixed])
    assert first.get_bottom()[1] >= fixed.get_top()[1]
    assert second.get_bottom()[1] >= first.get_top()[1]
    assert apart.get_center()[1] == pytest.approx(0)   # nothing in its way


# ----- axes and lint -----------------------------------------------------------------------------


def test_axis_numbers_have_plates_between_the_areas_and_the_curves(make_project) -> None:
    project = load(make_project, [{"id": "a", "type": "bullets", "params": {"items": ["x"]}, "beats": [{"text": "one"}]}])
    with runtime.use_context(project):
        axes = math_axes(Region(-6, -3, 6, 3), (-1, 4), (-3, 2), label=lambda s: Text(s, font_size=20))
    plates = [m for m in axes.group if m.z_index == LABEL_PLATE_Z]
    assert len(plates) == 1 and len(plates[0]) == len(axes.labels)
    for plate, label in zip(plates[0], axes.labels):
        assert plate.width > label.width and plate.get_center() == pytest.approx(label.get_center())


def test_sub_and_superscript_digits_count_as_small_glyphs() -> None:
    plain = cap_height({"kind": "text", "text": "w", "font_px": 10.0})
    assert cap_height({"kind": "text", "text": "w₁", "font_px": 9.3}) == pytest.approx(plain * 9.3 / 10 * 0.55 / 0.5125, rel=0.01)
    assert cap_height({"kind": "text", "text": "x²", "font_px": 9.3}) > cap_height({"kind": "text", "text": "x2", "font_px": 9.3})


def test_readback_joins_a_transcripts_split_decimals_and_reads_its_minus() -> None:
    heard = normalize_words(["of", "0", ".5,", "lands", "at", "3", ".375."])   # how faster-whisper writes them
    assert [t.text for t in heard] == normalize_text("of 0.5, lands at 3.375.") == [
        "of", "zero", "point", "five", "lands", "at", "three", "point", "three", "seven", "five"]
    assert [t[1] for t in heard][:4] == [0, 1, 1, 1]   # the joined decimal keeps its number's word
    assert normalize_text("is -3 and −2.5") == ["is", "minus", "three", "and", "minus", "two", "point", "five"]
    assert normalize_text("é 1 ,5 e -3", "pt-BR") == ["e", "um", "virgula", "cinco", "e", "menos", "tres"]
    assert normalize_text("one-by-one 3-4") == ["one", "by", "one", "three", "four"]   # hyphens still split


# ----- renders -----------------------------------------------------------------------------------


@pytest.mark.render
def test_a_version_revealed_by_an_action_morphs_for_the_scenes_own_time(make_project, media: Path) -> None:
    versions = ["def f(x):\n    return x\n", {"code": "def f(x: int) -> int:\n    return x\n", "highlight": "changed"}]
    words = "now we add the types to it and then wait for a while before this beat comes to its end"
    scene = render(load(make_project, [{"id": "m", "type": "code_morph", "params": {"versions": versions},
                                        "beats": [{"text": "one two three"}, {"text": words, "actions": [{"reveal": "version2", "at": "@types"}]}]}]), "m", media)
    morph = next(p for p in scene.play_log if p.beat == "m_b2" and any(a.startswith("_Morph(") for a in p.animations))
    assert morph.end - morph.start == pytest.approx(MORPH_SECONDS, abs=0.25)   # was the action's 0.8 s


@pytest.mark.render
def test_a_node_revealed_on_a_word_brings_its_edge(make_project, media: Path) -> None:
    p = {"nodes": ["app", "cache", "db"], "edges": ["app -> cache", "cache -> db"]}
    beats = [{"text": "the app asks the cache first and waits", "actions": [{"reveal": "node:cache", "at": "@cache"}]},
             {"text": "four five six seven"}, {"text": "eight nine ten eleven"}]
    scene = render(load(make_project, [{"id": "s", "type": "diagram", "params": p, "beats": beats}]), "s", media)
    assert scene.is_shown("edge:app->cache")
    assert plays(scene, "s_b2") == []   # the node's own step finds node and edge on screen already


@pytest.mark.render
def test_a_dots_label_keeps_clear_of_a_points_label(make_project, media: Path) -> None:
    p = {"functions": ["(x - 3)^2/2 + 1"], "x_range": [0, 6.5], "dots": [{"x": 0, "label": "slope {slope}"}],
         "points": [{"at": [3, 1], "name": "minimum"}], "reveal": "all"}
    beats = [{"text": "the dot moves down to the bottom now", "actions": [{"trace": "dot1", "to": 2.625, "at": "@moves", "run_time": 0.6}]}]
    scene = render(load(make_project, [{"id": "f", "type": "function_plot", "params": p, "beats": beats}]), "f", media)
    label = scene.dots[0].label
    a = (label.get_left()[0], label.get_bottom()[1], label.get_right()[0], label.get_top()[1])
    boxes = scene.geometry.label_boxes()
    assert boxes and not any(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3] for b in boxes)
