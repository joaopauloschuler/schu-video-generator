"""Step 253 (DESIGN.md §102.18-§102.19): neon strip lights along a room's walls
(``iso.wall_lights``) and a kiss between two characters holding hands."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from vidgen import extensions, registry
from vidgen.cartoon.iso_drawing import Poly
from vidgen.cartoon.iso_overlays import IsoBlinkers
from vidgen.cartoon.iso_scenery import STRIP_CORE, IsoColors, place_pieces
from vidgen.project import Project
from vidgen.scenes.stage import StageIso

ROOM = "#####\n#...#\n#...#\n#...#\n##+##"


def strips(colors: IsoColors) -> dict[str, set[str]]:
    """The glowing bands near the top of the walls, by the side they run along (x: a row's wall
    facing down-left, y: a column's wall facing down-right), as their colours."""
    found: dict[str, set[str]] = {"x": set(), "y": set()}
    place = StageIso(place="indoor", map=ROOM).parsed()
    for piece in place_pieces(place, colors, {}):
        for shape in piece.shapes:
            if isinstance(shape, Poly) and shape.glow and min(p[2] for p in shape.points) >= STRIP_CORE[0] - 0.2:
                xs, ys = {p[0] for p in shape.points}, {p[1] for p in shape.points}
                found["x" if len(ys) == 1 else "y"].add(shape.fill)
    return found


def test_wall_lights_take_one_colour_or_two_indoors_only() -> None:
    assert StageIso(place="indoor", map=ROOM, wall_lights="#FF2E8B").wall_light_colors() == ("#FF2E8B", "#FF2E8B")
    assert StageIso(place="indoor", map=ROOM, wall_lights=["cyan", "#FF2E8B"]).wall_light_colors() == ("cyan", "#FF2E8B")
    assert StageIso(place="indoor", map=ROOM).wall_light_colors() is None
    with pytest.raises(ValidationError, match="indoor"):
        StageIso(map="...\n...", wall_lights="#FF2E8B")
    with pytest.raises(ValidationError):
        StageIso(place="indoor", map=ROOM, wall_lights=["#111111", "#222222", "#333333"])


def test_strips_glow_along_both_back_walls_in_their_colours() -> None:
    assert strips(IsoColors()) == {"x": set(), "y": set()}   # none unless asked for
    found = strips(IsoColors(wall="#202030", strips=("#00FFFF", "#FF00FF")))
    assert len(found["x"]) == 2 and len(found["y"]) == 2      # a bright tube and its glow on each
    assert any(c.upper().startswith("#FF") for c in found["x"]) and any(c.upper().startswith("#") for c in found["y"])
    assert found["x"] != found["y"]                            # the right back wall's colour, the left one's


def test_a_hidden_blinking_light_is_not_drawn() -> None:
    lights = IsoBlinkers([(0.0, 0.0), (1.0, 0.0)], ["#FFB547", "#FFB547"], 0.1, hidden=lambda k: k == 0)
    seen = []
    for now in np.linspace(0.0, 6.0, 25):
        lights.update_to(float(now))
        assert lights.lights[0][1].get_fill_opacity() == 0.0   # hidden: never lit
        seen.append(lights.lights[1][1].get_fill_opacity())
    assert max(seen) > 0.0   # the other blinks as before


@pytest.mark.render
@pytest.mark.parametrize(("spot", "hides"), [("front", True), ("back", False)])
def test_a_character_in_front_of_a_console_hides_its_lights(make_project, tmp_path: Path, monkeypatch, spot: str, hides: bool) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    cast = [{"name": "pip", "look": {"body": "round", "outfit": "coat"}}]
    iso = {"place": "indoor", "map": "#######\n#..b..#\n#.d...#\n#..m..#\n#.....#\n#######",
           "spots": {"d": "desk", "m": "front", "b": "back"}, "objects": [{"object": "console", "at": "desk"}]}
    params = {"light": "night", "iso": iso, "characters": [{"name": "pip", "at": spot, "scale": 1.4}]}
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": [{"text": "Lights."}]}]
    scene, _ = frames_of(Project.load(make_project(minimal_config(characters=cast, scenes=scenes))), tmp_path / spot, monkeypatch)
    lights = next(t for t in scene.story_things if isinstance(t, IsoBlinkers))
    assert any(lights.hidden(k) for k in range(len(lights.lights))) is hides


def test_an_overlay_over_the_frame_does_not_hide_a_speaker() -> None:
    from test_cartoon_lint import check, fig, thing

    pip = fig("pip", [300, 100, 400, 400], speaking=True, face=[310, 100, 370, 160])
    hud = thing("frame", [0, 0, 854, 480], kind="group", order=20, overlay="implant", path="overlay:implant/g")
    hud_still = [{"id": "implant", "type": "hud", "faces": True}]
    assert check("hidden_speaker", [pip, hud], overlays=hud_still) == []   # a HUD's frame is overlay_face's to check
    assert len(check("hidden_speaker", [pip, hud])) == 1   # another overlay over the face still counts
    assert len(check("hidden_speaker", [pip, thing("tree", [280, 50, 420, 300], order=9)], overlays=hud_still)) == 1


@pytest.mark.render
def test_a_kiss_while_holding_hands_lets_go_and_stays_in_place(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    cast = [{"name": "pip", "look": {"body": "tall"}}, {"name": "kit", "look": {"body": "pear", "hair": "wavy"}}]
    iso = {"place": "indoor", "map": "######\n#....#\n#..b.#\n#.a..#\n#....#\n######", "spots": {"a": "left", "b": "right"},
           "wall_lights": ["#5FE8FF", "#FF2E8B"]}
    params = {"light": "night", "iso": iso, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}]}
    beats = [{"text": "Hands.", "actions": [{"hold_hands": "kit", "with": "pip", "at": 0.0}]},
             {"text": "A long kiss under the lights of the room, late at night.",
              "actions": [{"kiss": "pip", "with": "kit", "at": 0.05, "run_time": 3.0}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=cast, scenes=scenes))), tmp_path / "kiss", monkeypatch)
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    width = scene.camera.frame.width
    middle = float(scene.camera.frame.get_center()[0])
    # back where the hold left them, side by side about the middle (before, the hold and the kiss
    # each took the other's step for a move of the stage and the pair drifted off the frame)
    assert abs((float(pip.feet()[0]) + float(kit.feet()[0])) / 2 - middle) < 0.05 * width
    assert 0.0 < float(kit.feet()[0] - pip.feet()[0]) < 0.15 * width
    assert pip.kissing is None and pip.hand_in_hand is None and kit.hand_in_hand is None   # the kiss let go of the hands
    assert len(frames) > 5 and np.any(frames[-1] != frames[0])
