"""More iso lab and sci-fi objects (Steps 258–260, DESIGN.md §103): footprints, states, a wall
clock's time and wall, the moving parts of working objects, validation; one small render of each
batch."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST, stage_params
from vidgen import extensions, registry
from vidgen.cartoon.iso_objects import MOVING_KINDS, OBJECT_COLORS, ObjectLook, clock_hands, object_box, object_motion, object_shapes, object_working
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
    assert OBJECT_KINDS["lab_stool"].top is not None and {"quantum_core", "robot_arm", "centrifuge", "coffee_machine"} <= set(MOVING_KINDS)


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
    place = _room([ObjectPlacing(kind, (2 + k * 2, 2)) for k, kind in enumerate(("quantum_core", "robot_arm", "centrifuge", "coffee_machine"))])
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
    places = scene._iso_gadget_places   # the core, the arm, the centrifuge, the coffee machine
    assert len(places) == 4 and places[0][0].glowing
    assert places[0][2] is not None   # the core stands behind the coffee machine: it moves under a picture of the machine
    end = float(scene.renderer.time)
    assert places[1][0].gadgets[0].working(end) and not places[2][0].gadgets[0].working(end)   # the arm still swings; the centrifuge stopped
    assert len(frames) > 5 and np.any(frames[-1] != frames[3])


# ----- Step 259: plants, glassware and liquids -----------------------------------------------------------

NEW_2 = ("grow_rack", "terrarium", "specimen_tank", "chemistry_bench", "distillation_rig", "lab_fridge", "fume_hood")
WIDE = "###########\n" + "#.........#\n" * 6 + "#####+#####"


def test_glassware_objects_have_footprints_colours_and_states() -> None:
    for kind in NEW_2:
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS and OBJECT_KINDS[kind].height <= 2.65
        assert (OBJECT_KINDS[kind].width, OBJECT_KINDS[kind].depth) == ((2, 1) if kind == "chemistry_bench" else (1, 1))
    assert set(NEW_2) - {"terrarium"} <= SWITCHED_KINDS and "terrarium" not in SWITCHED_KINDS
    assert "lab_fridge" in OPENING_KINDS and not default_state("lab_fridge").open
    assert {"specimen_tank", "chemistry_bench", "distillation_rig", "lab_fridge", "fume_hood"} <= set(MOVING_KINDS)
    assert object_working("lab_fridge", ObjectState(open=True)) and not object_working("fume_hood", ObjectState(open=True))
    assert not object_working("specimen_tank", ObjectState(shown=False, on=True))


def test_glassware_glows_when_on_and_moves() -> None:
    placings = [ObjectPlacing(kind, (2 + (k % 3) * 3, 2 + (k // 3) * 2), facing="right" if k % 2 else "left") for k, kind in enumerate(NEW_2)]
    place = place_objects(parse_iso_map(WIDE, place="indoor"), tuple(placings))
    for item in place.objects:
        off, on = (object_shapes(item, _look(item.kind), 0.0, ObjectState(on=state)) for state in (False, True))
        assert off and on
        if item.kind != "terrarium":   # its flowers glow faintly all the time
            assert any(getattr(s, "glow", False) for s in on) and not any(getattr(s, "glow", False) for s in off), item.kind
        if item.kind in MOVING_KINDS:
            early, late = (object_motion(item, _look(item.kind), 0.0, t, ObjectState(on=True)) for t in (0.2, 1.1))
            assert early and len(early) == len(late) and [p.points for p in early] != [p.points for p in late]
    fridge = place.object("lab_fridge")
    closed, opened = (object_motion(fridge, _look("lab_fridge"), 0.0, 0.5, ObjectState(open=state)) for state in (False, True))
    assert [p.points for p in closed] != [p.points for p in opened]   # the mist pours from the opening
    plain = place_objects(parse_iso_map(WIDE, place="indoor"), (ObjectPlacing("specimen_tank", (2, 2)),)).object("specimen_tank")
    floating = place_objects(parse_iso_map(WIDE, place="indoor"), (ObjectPlacing("specimen_tank", (2, 2), detail="#203040"),)).object("specimen_tank")
    assert len(object_shapes(floating, _look("specimen_tank"), 0.0)) > len(object_shapes(plain, _look("specimen_tank"), 0.0))   # detail: a silhouette


def test_glassware_keys_validate() -> None:
    good = stage_params(iso={**ISO, "objects": [{"object": "lab_fridge", "at": "desk", "open": True, "on": True}, {"object": "terrarium", "at": "kiosk"}]})
    assert good.iso.objects[0].state() == ObjectState(True, True, True)
    for bad, message in (({"object": "terrarium", "at": "desk", "on": True}, "on is for"), ({"object": "fume_hood", "at": "desk", "open": True}, "open is for"),
                         ({"object": "grow_rak", "at": "desk"}, "did you mean grow_rack")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso={**ISO, "objects": [bad]})


@pytest.mark.render
def test_the_glassware_renders_and_moves_over_who_stands_behind(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    room = "##########\n#...b....#\n#.g.s.f..#\n#.t.d....#\n#.c...h..#\n#......p.#\n####+#####"
    spots = {"g": "grow", "s": "tank", "f": "fridge", "t": "terra", "d": "rig", "c": "bench", "h": "hood", "p": "here", "b": "back"}
    kinds = {"grow": "grow_rack", "tank": "specimen_tank", "fridge": "lab_fridge", "terra": "terrarium", "rig": "distillation_rig",
             "bench": "chemistry_bench", "hood": "fume_hood"}
    objects = [{"object": kind, "at": spot} for spot, kind in kinds.items()]
    params = {"light": "night", "iso": {"place": "indoor", "map": room, "spots": spots, "objects": objects},
              "characters": [{"name": "pip", "at": "back"}]}   # right behind the specimen tank
    beats = [{"text": "The lab wakes up at night.", "actions": [{"switch_on": [k for k in kinds.values() if k != "terrarium"]},
                                                               {"open": "lab_fridge", "at": 0.5}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "lab", monkeypatch)
    places = {scene.iso_scenery.pieces[k].name: (gadget, cover) for gadget, k, cover in scene._iso_gadget_places}
    assert set(places) == {"specimen_tank", "chemistry_bench", "distillation_rig", "lab_fridge", "fume_hood"}
    tank, cover = places["specimen_tank"]
    front = scene._iso_fronts["pip"][1]   # pip's front picture shows the tank: its bubbles are drawn after it
    assert front is not None and scene.mobjects.index(tank) > scene.mobjects.index(front)
    rig = scene.iso_scenery.index["distillation_rig"]   # the rig stands in front of the tank: its picture over the bubbles follows its switch
    assert cover is not None and dict(cover.submobjects[-1].picture[1])[rig].on
    end = float(scene.renderer.time)
    assert places["lab_fridge"][0].gadgets[0].working(end) and tank.gadgets[0].working(end)
    assert len(frames) > 5 and np.any(frames[-1] != frames[3])


# ----- Step 260: space, workshop and safety objects ------------------------------------------------------

NEW_3 = ("telescope", "satellite_dish", "charging_station", "crate_stack", "airlock", "printer_3d", "hazard_sign", "fire_extinguisher")
WORKSHOP_MOVING = ("satellite_dish", "charging_station", "airlock", "printer_3d")


def test_workshop_objects_have_footprints_colours_and_states() -> None:
    for kind in NEW_3:
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS and OBJECT_KINDS[kind].height <= 2.5
        assert (OBJECT_KINDS[kind].width, OBJECT_KINDS[kind].depth) == ((2, 1) if kind == "airlock" else (1, 1))
    assert set(WORKSHOP_MOVING) <= SWITCHED_KINDS and set(WORKSHOP_MOVING) <= set(MOVING_KINDS)
    assert not {"telescope", "crate_stack", "hazard_sign", "fire_extinguisher"} & SWITCHED_KINDS
    assert "airlock" in OPENING_KINDS and not default_state("airlock").open and OBJECT_KINDS["crate_stack"].top is not None


def test_workshop_objects_draw_and_move() -> None:
    placings = [ObjectPlacing(kind, (2 + (k % 3) * 3, 2 + (k // 3) * 2), facing="right" if k % 2 else "left") for k, kind in enumerate(NEW_3)]
    place = place_objects(parse_iso_map(WIDE, place="indoor"), tuple(placings))
    for item in place.objects:
        off = object_shapes(item, _look(item.kind), 0.0, ObjectState())
        assert off and not any(getattr(s, "glow", False) for s in off), item.kind
        if item.kind in WORKSHOP_MOVING:
            on = object_shapes(item, _look(item.kind), 0.0, ObjectState(on=True))
            assert any(getattr(s, "glow", False) for s in on), item.kind
            still = object_shapes(item, _look(item.kind, True), 0.0, ObjectState(on=True))   # its moving parts left to the stage
            early, late = (object_motion(item, _look(item.kind), 0.0, t, ObjectState(on=True)) for t in (0.2, 3.1))
            assert len(still) <= len(on) and early and len(early) == len(late) and [(p.points, p.opacity) for p in early] != [(p.points, p.opacity) for p in late]
    airlock = place.object("airlock")
    assert object_shapes(airlock, _look("airlock"), 0.0, ObjectState(open=True)) != object_shapes(airlock, _look("airlock"), 0.0, ObjectState())
    signs = [place_objects(parse_iso_map(WIDE, place="indoor"), (ObjectPlacing("hazard_sign", (2, 2), features=(kind,)),)).object("hazard_sign")
             for kind in ("biohazard", "radiation", "authorised")]
    assert len({repr(object_shapes(sign, _look("hazard_sign"), 0.0)) for sign in signs}) == 3
    with pytest.raises(VidgenError, match="its extras: biohazard, radiation, authorised"):
        place_objects(parse_iso_map(WIDE, place="indoor"), (ObjectPlacing("hazard_sign", (2, 2), features=("toxic",)),))


def test_screen_text_reads_from_the_left_facing_either_way() -> None:
    place = place_objects(parse_iso_map(WIDE, place="indoor"), (ObjectPlacing("laptop", (2, 2)), ObjectPlacing("laptop", (5, 2), facing="right")))
    for item in place.objects:   # the longest and the shortest line (neither indented) start at the same left edge
        lines = [s for s in object_shapes(item, _look("laptop"), 0.0, ObjectState(open=True, on=True)) if getattr(s, "glow", False)][1:]
        lefts = [min(x - y for x, y, _ in s.points) for s in lines]
        assert abs(lefts[5] - lefts[0]) < 0.1, item.facing


def test_workshop_keys_validate() -> None:
    good = stage_params(iso={**ISO, "objects": [{"object": "hazard_sign", "at": "desk", "kind": "radiation"}, {"object": "airlock", "at": "kiosk", "open": True}]})
    assert good.iso.objects[0].placing().features == ("radiation",) and good.iso.objects[1].state().open
    for bad, message in (({"object": "hazard_sign", "at": "desk", "kind": "radiaton"}, "did you mean radiation"),
                         ({"object": "laptop", "at": "desk", "kind": "radiation"}, "kind is for a hazard_sign"),
                         ({"object": "crate_stack", "at": "desk", "on": True}, "on is for"), ({"object": "telescop", "at": "desk"}, "did you mean telescope")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso={**ISO, "objects": [bad]})


@pytest.mark.render
def test_the_workshop_objects_render_and_move(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    room = "###########\n#.a..t.s..#\n#.........#\n#.c.d.p.h.#\n#.......f.#\n#....x....#\n#####+#####"
    spots = {"a": "lock", "t": "scope", "s": "dish", "c": "charge", "d": "crates", "p": "printer", "h": "sign", "f": "fire", "x": "here"}
    kinds = ("airlock", "telescope", "satellite_dish", "charging_station", "crate_stack", "printer_3d", "hazard_sign", "fire_extinguisher")
    objects = [{"object": kind, "at": spot, **({"on": True} if kind in SWITCHED_KINDS else {})} for kind, spot in zip(kinds, spots.values())]
    objects[6]["kind"] = "radiation"
    params = {"light": "night", "iso": {"place": "indoor", "map": room, "spots": spots, "objects": objects},
              "characters": [{"name": "pip", "at": "here"}]}
    beats = [{"text": "The station keeps working at night.", "actions": [{"open": "airlock", "at": 0.5}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "lab", monkeypatch)
    places = {scene.iso_scenery.pieces[k].name: gadget for gadget, k, _ in scene._iso_gadget_places}
    assert set(places) == set(WORKSHOP_MOVING)
    end = float(scene.renderer.time)
    assert all(gadget.gadgets[0].working(end) for gadget in places.values())
    assert len(frames) > 5 and np.any(frames[-1] != frames[3])
