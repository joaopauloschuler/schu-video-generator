"""More iso lab and sci-fi objects (Step 258, DESIGN.md §103): footprints, states, a wall clock's
time and wall, the moving parts of working objects, validation; one small render of them all."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST, stage_params
from vidgen import extensions, registry
from vidgen.cartoon.iso_objects import MOVING_KINDS, OBJECT_COLORS, ObjectLook, clock_hands, object_box, object_motion, object_shapes
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.world.iso import OBJECT_KINDS, OPENING_KINDS, SWITCHED_KINDS, ObjectPlacing, ObjectState, default_state, parse_iso_map, place_objects

NEW = ("laptop", "terminal_kiosk", "quantum_core", "robot_arm", "microscope", "centrifuge", "coffee_machine", "lab_stool", "wall_clock")
ROOM = "#########\n#.......#\n#.......#\n#.......#\n#.......#\n####+####"


def _room(placings: list[ObjectPlacing]):
    return place_objects(parse_iso_map(ROOM, place="indoor"), tuple(placings))


def _look(kind: str, moving: bool = False) -> ObjectLook:
    return ObjectLook(*OBJECT_COLORS[kind], moving=moving)


def test_new_objects_have_footprints_colours_and_states() -> None:
    for kind in NEW:
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS
        assert OBJECT_KINDS[kind].width == OBJECT_KINDS[kind].depth == 1 and OBJECT_KINDS[kind].height <= 2.65   # under a back wall's top
    assert {"laptop", "terminal_kiosk", "quantum_core", "robot_arm", "centrifuge", "coffee_machine"} <= SWITCHED_KINDS
    assert "laptop" in OPENING_KINDS and default_state("laptop").open and not default_state("laptop").on
    assert OBJECT_KINDS["lab_stool"].top is not None and set(MOVING_KINDS) == {"quantum_core", "robot_arm", "centrifuge", "coffee_machine"}


def test_new_objects_draw_on_and_off_facing_both_ways() -> None:
    placings = [ObjectPlacing(kind, (2 + (k % 4) * 2, 2 + (k // 4) * 2), facing="right" if k % 2 else "left") for k, kind in enumerate(NEW[:-1])]
    place = _room(placings)
    for item in place.objects:
        off, on = (object_shapes(item, _look(item.kind), 0.0, ObjectState(open=True, on=state)) for state in (False, True))
        assert off and on
        if item.kind in ("laptop", "terminal_kiosk", "quantum_core"):   # a screen or the sphere glows when on only
            assert any(getattr(s, "glow", False) for s in on) and not any(getattr(s, "glow", False) for s in off)
    laptop = place.object("laptop")
    assert len(object_shapes(laptop, _look("laptop"), 0.0, ObjectState(open=False))) < len(object_shapes(laptop, _look("laptop"), 0.0, ObjectState(open=True)))
    arm = place.object("robot_arm")   # its arm left to the stage while it swings
    assert len(object_shapes(arm, _look("robot_arm", True), 0.0, ObjectState(on=True))) < len(object_shapes(arm, _look("robot_arm"), 0.0, ObjectState(on=True)))


def test_moving_parts_move_and_keep_their_count() -> None:
    place = _room([ObjectPlacing(kind, (2 + k * 2, 2)) for k, kind in enumerate(MOVING_KINDS)])
    for item in place.objects:
        early, late = object_motion(item, _look(item.kind), 0.0, 0.2), object_motion(item, _look(item.kind), 0.0, 1.1)
        assert early and len(early) == len(late) and [p.points for p in early] != [p.points for p in late]
    assert object_motion(place.object("quantum_core"), _look("quantum_core"), 0.0, 0.0)[0].glow


def test_a_wall_clock_hangs_on_a_back_wall() -> None:
    assert clock_hands("03:27") == (3 * 30 + 13.5, 162.0) and clock_hands(None) == (305.0, 60.0)
    north = _room([ObjectPlacing("wall_clock", (3, 1), time="03:27")]).object("wall_clock")
    west = _room([ObjectPlacing("wall_clock", (1, 3))]).object("wall_clock")
    assert (north.facing, north.time, west.facing) == ("left", "03:27", "right")
    box = object_box(north, 0.0)
    assert box.y0 == 1 and box.y1 - box.y0 < 0.1 and box.z0 > 1.5   # a thin slab on the wall's face, over the heads
    for bad, message in (((3, 2), "standing wall"), ((5, 6), "hangs on a wall"), ((1, 1), "floor below it")):
        with pytest.raises(VidgenError, match=message):
            _room([ObjectPlacing("wall_clock", bad)])
    with pytest.raises(VidgenError, match="time is for a wall_clock"):
        _room([ObjectPlacing("laptop", (2, 2), time="03:00")])


ISO = {"place": "indoor", "map": ROOM.replace("#.......#\n#.......#\n#.......#\n#.......#", "#.......#\n#.l.k...#\n#.......#\n#...a...#"),
       "spots": {"l": "desk", "k": "kiosk", "a": "here"}}


def test_object_keys_validate() -> None:
    good = stage_params(iso={**ISO, "objects": [{"object": "laptop", "at": "desk", "open": False, "on": True},
                                               {"object": "wall_clock", "at": {"column": 4, "row": 1}, "time": "03:27"}]})
    assert good.iso.objects[0].state() == ObjectState(True, False, True) and good.iso.objects[1].placing().time == "03:27"
    for bad, message in (({"object": "lab_stool", "at": "desk", "on": True}, "on is for"), ({"object": "microscope", "at": "desk", "open": True}, "open is for"),
                         ({"object": "laptop", "at": "desk", "time": "03:27"}, "time is for a wall_clock"),
                         ({"object": "wall_clock", "at": {"column": 4, "row": 1}, "time": "25:00"}, "time"),
                         ({"object": "lapotp", "at": "desk"}, "did you mean laptop"), ({"object": "laptop", "at": "desk", "glow": True}, "glow")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso={**ISO, "objects": [bad]})


@pytest.mark.render
def test_the_lab_objects_render_and_move(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    room = "##########\n#........#\n#.a.b.c.d#\n#........#\n#.e.f.g.h#\n#......p.#\n####+#####"
    spots = {"a": "kiosk", "b": "core", "c": "arm", "d": "scope", "e": "desk", "f": "spin", "g": "coffee", "h": "stool", "p": "here"}
    kinds = ("terminal_kiosk", "quantum_core", "robot_arm", "microscope", "laptop", "centrifuge", "coffee_machine", "lab_stool")
    objects = [{"object": kind, "at": spot, **({"on": True} if kind in SWITCHED_KINDS else {})} for kind, spot in zip(kinds, spots.values())]
    objects.append({"object": "wall_clock", "at": {"column": 4, "row": 1}, "time": "03:27"})
    params = {"light": "night", "iso": {"place": "indoor", "map": room, "spots": spots, "objects": objects},
              "characters": [{"name": "pip", "at": "here"}]}
    beats = [{"text": "The lab hums at night.", "actions": [{"switch_off": "centrifuge", "at": 0.6}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "lab", monkeypatch)
    gadgets = next(thing for thing in scene.story_things if type(thing).__name__ == "IsoGadgets")
    assert len(gadgets.gadgets) == 3 and gadgets.glowing   # the core stands behind the coffee machine: its picture shows it still
    end = float(scene.renderer.time)
    assert gadgets.gadgets[0].working(end) and not gadgets.gadgets[1].working(end)   # the arm still swings; the centrifuge stopped
    assert len(frames) > 5 and np.any(frames[-1] != frames[3])
