"""Step 170: the iso example `examples/iso-story` through `vidgen validate` (16:9 and its 9:16
variant) using the phase's features, and the fixes found while making it: a thing held by a
character that leaves the place (or comes onto it) fades with it."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout
from test_iso_staging import ISO
from vidgen.cli import main, validate_all
from vidgen.project import Project

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "iso-story"


# ----- the example -------------------------------------------------------------------------------


@pytest.mark.parametrize("variant", [None, "short"])
def test_the_example_validates_and_uses_phase_q(variant: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "story", ignore=shutil.ignore_patterns("build", "output", "exports", "audio"))
    assert main(["validate", str(root)]) == 0
    capsys.readouterr()
    project = Project.load(root, variant=variant)
    assert validate_all(project, keep_going=True)[0] == []
    stages = [s for s in project.config.scenes if s.type == "stage"]
    places = {s.id: s.params["iso"].get("place", "outdoor") for s in stages}
    assert list(places.values()).count("indoor") == 1 and list(places.values()).count("outdoor") >= 3
    voices = {c.name: c.voice for c in project.config.characters}
    assert all(voices.values()) and len(set(voices.values())) == len(voices)   # each character its own voice
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("place: indoor", "~~", "object: bridge", "object: lamp", "object: house", "open: false", "meet:", "walk_to:",
                 "run_to:", "enter:", "exit:", "door: rowan_door", "pick_up:", "give:", "hold:", "open: rowan_house",
                 "switch_on: lamp", "open: bud_1", "light: night", "light: sunset", "light: morning", "particles: rain",
                 "follow:", "shot: closeup", "shot: two_shot", "shot: wide", "zoom:", "set: village"):
        assert used in text, used


# ----- what a character carries fades with it ----------------------------------------------------


@pytest.mark.render
def test_a_held_thing_leaves_the_place_with_its_holder(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.scenes import stage_iso

    made: list[stage_iso.IsoWalk] = []

    class Recorded(stage_iso.IsoWalk):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(stage_iso, "IsoWalk", Recorded)
    beats = [
        {"text": "Pip picks up the gift.", "actions": [{"walk_to": "pip", "to": "table"}, {"pick_up": "pip", "to": "gift", "at": 0.6}]},
        {"text": "And Pip walks away with it, off the place.", "actions": [{"exit": "pip", "to": "left"}]},
    ]
    stage: dict[str, Any] = {"idle": False, "background": "#BFE3F5", "iso": ISO, "props": [{"prop": "gift", "at": "table"}],
                             "characters": [{"name": "pip", "at": "start"}, {"name": "kit", "at": "far"}]}
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=[{"id": "pond", "type": "stage", "params": stage, "beats": beats}])))
    scene, _ = render_with_layout(project, "pond", tmp_path / "media")
    gift, pip = scene.props["gift"], scene.cast["pip"]
    assert scene.holdings.holder("gift") == ("pip", "left")
    left, right = scene.camera_bounds()[:2]
    assert not left <= float(pip.feet()[0]) <= right   # parked off the place
    assert abs(float(gift.get_center()[0]) - float(pip.feet()[0])) < pip.character_height, "the gift stayed behind on the place"
    exits = [walk for walk in made if walk.park_x is not None]
    assert exits and all(walk.fade_out > 0 and walk.carried == [gift] for walk in exits)   # it fades out with pip
    assert all(walk.carried == [] for walk in made if walk.park_x is None)


# ----- rain on an iso place reads as rain --------------------------------------------------------


def test_rain_on_an_iso_place_darkens_it_unless_a_light_is_given() -> None:
    from test_cartoon_stage import stage_params
    from vidgen.cartoon.shading import CustomLight
    from vidgen.scenes.stage import ISO_RAIN_LIGHT

    rainy = stage_params(iso=ISO, characters=[{"name": "pip", "at": "start"}], particles=["rain"])
    assert rainy.light == CustomLight(tint=ISO_RAIN_LIGHT[0], strength=ISO_RAIN_LIGHT[1])
    assert stage_params(iso=ISO, characters=[{"name": "pip", "at": "start"}], particles=["rain"], light="night").light == "night"
    assert stage_params(iso=ISO, characters=[{"name": "pip", "at": "start"}], particles=["snow"]).light == "day"
    assert stage_params(characters=["pip"], particles=["rain"]).light == "day"   # a flat stage as before


# ----- a walk to where someone stands does not end across a stream ------------------------------


def test_a_walk_to_someone_across_water_is_refused_not_ended_on_the_near_bank() -> None:
    from vidgen.errors import VidgenError
    from vidgen.world.iso import parse_iso_map
    from vidgen.world.iso_moves import BESIDE_REACH, find_route

    place = parse_iso_map("a..~~..b\n...~~...\n...~~...", names={"a": "left_bank", "b": "right_bank"})
    with pytest.raises(VidgenError, match=r"'juno' cannot walk from row 1, column 8 to 'left_bank': the way stops at .*water"):
        find_route(place, (7, 0), (0, 0), crowd={(0, 0)}, who="'juno'", to="'left_bank'")
    near = find_route(place, (2, 2), (0, 0), crowd={(0, 0)})   # on its bank: beside it, as before
    assert max(abs(near.end_cell[0]), abs(near.end_cell[1])) <= BESIDE_REACH and near.end_cell != (0, 0)


# ----- a name tag is not a label the narration must not name early ------------------------------


def test_a_name_tag_is_not_a_label_for_said_before_shown() -> None:
    from test_narration_rule import dump, frame, label
    from vidgen.lint.narration_rule import shown_labels

    frames = dump(frame("b1", 2.8, label("sign", "Bakery")), frame("b2", 5.8, label("sign", "Bakery"), label("tag", "Juno", name_tag="juno")))
    assert [lb.text for lb in shown_labels(frames)] == ["Bakery"]   # "Juno" named in b1 is fine: she is on screen, tagged in b2
