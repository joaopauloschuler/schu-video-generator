"""Review of Phase O (Step 155): the example `examples/platform-story` through `vidgen validate`
(16:9 and its 9:16 variant), and the fixes found on the way: a set's props on a level (they stand
at depths, so a level could not use a set with props of its own), `vidgen screenplay` with a
level (a multi-line map did not round-trip in the written YAML, front-matter sets were not
usable by `set:` lines, spots were not marks, no "jumps onto" verb), and a refusal's wording."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen.cli import main, validate_all
from vidgen.errors import VidgenError
from vidgen.includes import LEVEL_DROPPED_KEYS, apply_set, builtin_sets
from vidgen.plan_yaml import commented_yaml
from vidgen.project import Project
from vidgen.screenplay import parse_screenplay, screenplay_project, stage_marks
from vidgen.world import parse_level, place_bodies, step_aside
from vidgen.world.world import Placing

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "platform-story"


def json_out(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


# ----- the example -------------------------------------------------------------------------------


@pytest.mark.parametrize("variant", [None, "short"])
def test_the_example_validates_and_uses_phase_o(variant: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "story", ignore=shutil.ignore_patterns("build", "output", "exports", "audio"))
    assert main(["validate", str(root), "--json"]) == 0   # the base config and its variants
    assert json_out(capsys)["ok"]
    project = Project.load(root, variant=variant)
    assert validate_all(project, keep_going=True)[0] == []
    stages = [s for s in project.config.scenes if s.type == "stage"]
    assert len(stages) == 3 and all(s.params["level"]["follow"] == "nutmeg" for s in stages)
    sizes = {s.params.get("character_size") for s in stages}
    assert sizes == ({"large"} if variant else {"medium"})
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("|=======", "~~~~", "$", "*", "locks:", "blockers:", "step_aside:", "open: gate, by: nutmeg", "pick_up:", "jump:",
                 "react: {when: pickup", "when: land", "when: arrive", "shot: closeup", "species: snail", "character_size: large",
                 "music: {source: cartoon", "set: park"):
        assert used in text, used


# ----- a set on a level --------------------------------------------------------------------------


def test_a_level_takes_a_sets_sky_and_layers_but_not_its_props() -> None:
    park = builtin_sets()["park"]
    plain = apply_set(park, {"props": [{"prop": "tree", "at": 0.7}]}).params
    assert len(plain["props"]) == len(park["props"]) + 1   # a plain stage keeps the set's props
    level = apply_set(park, {"props": [{"prop": "tree", "at": 0.7}], "level": {"map": "..a..\n#####"}}).params
    assert level["props"] == [{"prop": "tree", "at": 0.7}] and "ground_color" not in level
    assert level["layers"] == park["layers"] and level["background"] == park["background"] and level["marks"] == park["marks"]
    assert not LEVEL_DROPPED_KEYS & set(apply_set(builtin_sets()["beach"], {"level": {"map": "#"}}).params) - {"props"}


# ----- vidgen screenplay with a level ------------------------------------------------------------


SCREENPLAY = """---
title: Level play
sets:
  meadow:
    background: ["#9CCBEA", "#E4F3FB"]
    level:
      map: |
        ......................
        ..a......b....c.......
        ##########....########
      spots: {a: start, b: brink, c: over}
      follow: nutmeg
characters:
  - {name: nutmeg, look: {species: mouse}}
---
# Scene: meadow
set: meadow; characters: nutmeg at start

[Nutmeg walks to brink.]

Nutmeg skipped to the edge of the meadow.

[Nutmeg jumps onto over.]

Hop! She landed on the other side.
"""


def test_a_screenplay_uses_a_level_from_its_front_matter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    draft = screenplay_project(parse_screenplay(SCREENPLAY))
    scene = draft.config["scenes"][0]
    assert scene["set"] == "meadow" and scene["params"]["characters"] == [{"name": "nutmeg", "at": "start"}]
    actions = [a for beat in scene["beats"] for a in beat.get("actions", [])]
    assert actions == [{"walk_to": "nutmeg", "to": "brink"}, {"jump": "nutmeg", "to": "over"}]
    text = commented_yaml(draft.config)   # the map keeps its final line break (it did not load back before)
    assert "      map: |\n" in text and yaml.safe_load(text)["sets"]["meadow"]["level"]["map"].endswith("#\n")
    story = tmp_path / "story.md"
    story.write_text(SCREENPLAY, encoding="utf-8")
    assert main(["screenplay", str(story), "--out", str(tmp_path / "out"), "--json"]) == 0
    assert json_out(capsys)["todo_count"] == 0
    assert main(["validate", str(tmp_path / "out"), "--json"]) == 0
    assert json_out(capsys)["ok"]


def test_spots_are_marks_and_jumps_onto_need_a_level() -> None:
    level = {"map": "..a..b..\n########", "spots": {"a": "start"}}
    assert stage_marks({"marks": {"tree": 0.9}, "level": level}) == {"tree": 0.9, "start": 2.5 / 8, "b": 5.5 / 8}
    assert stage_marks({"level": {"map": "..@.."}}) == {}   # a bad map: validate reports it
    plain = SCREENPLAY.replace("set: meadow; ", "").replace("nutmeg at start", "nutmeg at left").replace("onto over", "onto right")
    beats = screenplay_project(parse_screenplay(plain)).config["scenes"][0]["beats"]
    assert not any("jump" in a for b in beats for a in b.get("actions", []))   # no level: left as a TODO


# ----- messages ----------------------------------------------------------------------------------


def test_a_refusal_lists_the_kind_it_wanted() -> None:
    world = place_bodies(parse_level("..a..\n#####"), [Placing("pip", "character", spot="a")])
    with pytest.raises(VidgenError, match=r"'pip' is not a blocker of the level \(blockers: none\)"):
        step_aside(world, "pip")


# ----- stars over a tall level -------------------------------------------------------------------


@pytest.mark.render
def test_the_night_has_stars_over_a_tall_level(make_project, tmp_path: Path) -> None:
    """A level the camera rises over had no stars at night (they were kept clear of the heads at
    the start, here above the frame) and would have scrolled away: now they fill the top of the
    view and move with the camera, like the sky."""
    from test_cartoon_stage import render_with_layout
    from test_platform_camera import tall_project
    from vidgen.introspect import LayoutRecorder

    scene, _ = render_with_layout(tall_project(make_project, light="night"), "hills", tmp_path / "media", LayoutRecorder())
    assert scene.stars is not None and len(scene.stars.submobjects) > 10
    assert any(layer.mobject is scene.stars and layer.factor == 0.0 for layer in scene._parallax)
    view = scene.camera.frame
    assert view.get_center()[1] > 0.5   # the camera rose with the hero ...
    tops = [float(s.get_center()[1]) for s in scene.stars.submobjects]
    assert min(tops) > view.get_center()[1] and max(tops) <= view.get_top()[1] + 1e-6   # ... and the stars with it


# ----- shots in a portrait frame -----------------------------------------------------------------


def test_a_portrait_closeup_is_never_narrower_than_the_face() -> None:
    """The example's 9:16 close-ups cut the mouse's face in half (lint off_stage: 48 % outside):
    framed by height alone, a portrait close-up was 0.41 of the character's height wide."""
    from vidgen.cartoon.shots import SHOT_MIN_WIDTHS, SHOT_SPANS, ShotFigure, frame_shot
    from vidgen.render.worker import frame_size

    figure = ShotFigure("pip", 0.0, -3.0, 2.8, "right")
    for width, height in ((1080, 1920), (1920, 1080)):
        fw, fh = frame_size(width, height)
        bounds = (-20.0, 20.0, -fh / 2, fh / 2)
        for kind in ("closeup", "medium"):
            view = frame_shot(kind, [figure], frame_width=fw, frame_height=fh, bounds=bounds)
            view_width, view_height = view.size(fw, fh)
            assert view_width >= SHOT_MIN_WIDTHS[kind] * figure.height - 1e-9
            if width > height:   # landscape: framed by its span, as before
                assert view_height == pytest.approx(sum(SHOT_SPANS[kind]) * figure.height)
