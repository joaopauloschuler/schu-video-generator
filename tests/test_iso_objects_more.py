"""More iso objects (Phase AC, DESIGN.md §104): footprints, colours, states, validation and the
moving parts of the working ones, without rendering; one small render of each batch."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST, stage_params
from vidgen import extensions, registry
from vidgen.cartoon.iso_objects import LAMPLIGHT_KINDS, MORE_MODULES, MOVING_KINDS, OBJECT_COLORS, ObjectLook, object_motion, object_shapes
from vidgen.project import Project
from vidgen.world.iso import (DISPLAY_CASES, OBJECT_KINDS, OBJECT_STYLES, OPENING_KINDS, SWITCHED_KINDS, ObjectPlacing, ObjectState, default_state,
                              parse_iso_map, place_objects)

WIDE = "###########\n" + "#.........#\n" * 6 + "#####+#####"


def _look(kind: str, moving: bool = False) -> ObjectLook:
    return ObjectLook(*OBJECT_COLORS[kind], moving=moving)


def _placed(kinds: tuple[str, ...]):
    placings = [ObjectPlacing(kind, (2 + (k % 3) * 3, 2 + (k // 3) * 2), facing="right" if k % 2 else "left") for k, kind in enumerate(kinds)]
    return place_objects(parse_iso_map(WIDE, place="indoor"), tuple(placings))


# ----- Step 261: home I ------------------------------------------------------------------------------------

HOME_1 = ("fireplace", "kitchen_counter", "stove", "sink", "bookshelf_tall", "armchair", "floor_lamp", "tv", "piano")
HOME_1_WORKING = ("fireplace", "stove", "floor_lamp", "tv")
HOME_1_MOVING = ("fireplace", "stove", "tv")
WIDE_KINDS = ("fireplace", "kitchen_counter", "piano")


def test_home_objects_have_footprints_colours_and_states() -> None:
    for kind in HOME_1:
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS and kind in MORE_MODULES and OBJECT_KINDS[kind].height <= 2.65
        assert (OBJECT_KINDS[kind].width, OBJECT_KINDS[kind].depth) == ((2, 1) if kind in WIDE_KINDS else (1, 1))
        assert default_state(kind) == ObjectState() and kind not in OPENING_KINDS
    assert set(HOME_1_WORKING) <= SWITCHED_KINDS and not (set(HOME_1) - set(HOME_1_WORKING)) & SWITCHED_KINDS
    assert set(HOME_1_MOVING) <= set(MOVING_KINDS) and "floor_lamp" not in MOVING_KINDS
    assert {"floor_lamp", "fireplace"} <= LAMPLIGHT_KINDS
    assert all(OBJECT_KINDS[kind].top is not None for kind in ("kitchen_counter", "bookshelf_tall", "armchair", "piano"))


def test_home_objects_draw_light_up_and_move() -> None:
    place = _placed(HOME_1)
    for item in place.objects:
        off = object_shapes(item, _look(item.kind), 0.0, ObjectState())
        assert off and not any(getattr(s, "glow", False) for s in off), item.kind
        if item.kind in HOME_1_WORKING:
            on = object_shapes(item, _look(item.kind), 0.0, ObjectState(on=True))
            assert any(getattr(s, "glow", False) for s in on), item.kind
        if item.kind in HOME_1_MOVING:
            early, late = (object_motion(item, _look(item.kind), 0.0, t, ObjectState(on=True)) for t in (0.2, 1.3))
            assert early and len(early) == len(late) and [(p.points, p.opacity) for p in early] != [(p.points, p.opacity) for p in late], item.kind
    fire = place.object("fireplace")   # its flames left to the stage while it burns
    assert len(object_shapes(fire, _look("fireplace", True), 0.0, ObjectState(on=True))) < len(object_shapes(fire, _look("fireplace"), 0.0, ObjectState(on=True)))


ISO = {"place": "indoor", "map": "#########\n#.......#\n#.l.k...#\n#.......#\n####+####", "spots": {"l": "here", "k": "there"}}


def test_home_keys_validate() -> None:
    good = stage_params(iso={**ISO, "objects": [{"object": "fireplace", "at": "here", "on": True}, {"object": "tv", "at": "there", "on": True}]})
    assert good.iso.objects[0].state().on and good.iso.objects[1].placing().kind == "tv"
    for bad, message in (({"object": "piano", "at": "here", "on": True}, "on is for"), ({"object": "stove", "at": "here", "open": True}, "open is for"),
                         ({"object": "armchair", "at": "here", "kind": "radiation"}, "kind is for a hazard_sign"),
                         ({"object": "fireplce", "at": "here"}, "did you mean fireplace"), ({"object": "floorlamp", "at": "here"}, "did you mean floor_lamp")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso={**ISO, "objects": [bad]})


@pytest.mark.render
def test_the_home_objects_render_move_and_light(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    room = "############\n#f.p.k.sn..#\n#..l.m.....#\n#b.a..y....#\n#.....t....#\n####+#######"
    spots = {"f": "fire", "p": "piano", "k": "counter", "s": "stove", "n": "sink", "l": "lamp", "m": "near", "b": "books", "a": "chair", "y": "back", "t": "telly"}
    kinds = {"fire": "fireplace", "piano": "piano", "counter": "kitchen_counter", "stove": "stove", "sink": "sink", "lamp": "floor_lamp",
             "books": "bookshelf_tall", "chair": "armchair", "telly": "tv"}
    objects = [{"object": kind, "at": spot, **({"on": True} if kind in HOME_1_WORKING else {})} for spot, kind in kinds.items()]
    params = {"light": "night", "iso": {"place": "indoor", "map": room, "spots": spots, "objects": objects},
              "characters": [{"name": "pip", "at": "near"}]}
    beats = [{"text": "A warm evening at home.", "actions": [{"switch_off": "stove", "at": 0.6}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "home", monkeypatch)
    places = {scene.iso_scenery.pieces[k].name: gadget for gadget, k, _ in scene._iso_gadget_places}
    assert set(places) == set(HOME_1_MOVING)
    end = float(scene.renderer.time)
    assert places["fireplace"].gadgets[0].working(end) and not places["stove"].gadgets[0].working(end)
    assert set(scene._iso_lamps) == {"fireplace", "floor_lamp"} and scene._iso_lamp_share("pip") > 0.0   # pip stands near the lit lamp
    assert len(frames) > 5 and np.any(frames[-1] != frames[3])


# ----- Step 262: home II, café and shop --------------------------------------------------------------------

SHOP = ("bathtub", "wardrobe", "crib", "cafe_table", "counter", "cash_register", "display_case", "market_stall", "vending_machine")
SHOP_WIDE = ("bathtub", "wardrobe", "cafe_table", "counter", "display_case", "market_stall")


def test_shop_objects_have_footprints_colours_and_states() -> None:
    for kind in SHOP:
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS and MORE_MODULES[kind] == "iso_shop" and OBJECT_KINDS[kind].height <= 2.7
        assert (OBJECT_KINDS[kind].width, OBJECT_KINDS[kind].depth) == ((2, 1) if kind in SHOP_WIDE else (1, 1))
        assert default_state(kind) == ObjectState() and kind not in MOVING_KINDS
    assert set(SHOP) & SWITCHED_KINDS == {"vending_machine"} and set(SHOP) & OPENING_KINDS == {"wardrobe"}
    assert OBJECT_STYLES["display_case"] == DISPLAY_CASES == ("cakes", "jewels")
    assert all(OBJECT_KINDS[kind].top is not None for kind in ("wardrobe", "cafe_table", "counter", "display_case"))


def test_shop_objects_draw_open_and_light_up() -> None:
    place = _placed(SHOP)
    for item in place.objects:
        off = object_shapes(item, _look(item.kind), 0.0, ObjectState())
        assert off and not any(getattr(s, "glow", False) for s in off), item.kind
    machine, wardrobe = place.object("vending_machine"), place.object("wardrobe")
    assert any(getattr(s, "glow", False) for s in object_shapes(machine, _look("vending_machine"), 0.0, ObjectState(on=True)))
    assert object_shapes(wardrobe, _look("wardrobe"), 0.0, ObjectState(open=True)) != object_shapes(wardrobe, _look("wardrobe"), 0.0, ObjectState())
    cases = [place_objects(parse_iso_map(WIDE, place="indoor"), (ObjectPlacing("display_case", (2, 2), features=(kind,)),)).object("display_case")
             for kind in DISPLAY_CASES]
    assert repr(object_shapes(cases[0], _look("display_case"), 0.0)) != repr(object_shapes(cases[1], _look("display_case"), 0.0))


def test_shop_keys_validate() -> None:
    good = stage_params(iso={**ISO, "objects": [{"object": "display_case", "at": "here", "kind": "jewels"},
                                                {"object": "wardrobe", "at": "there", "open": True}]})
    assert good.iso.objects[0].placing().features == ("jewels",) and good.iso.objects[1].state().open
    for bad, message in (({"object": "display_case", "at": "here", "kind": "jewls"}, "unknown display_case kind 'jewls'; did you mean jewels"),
                         ({"object": "display_case", "at": "here", "kind": "radiation"}, "kinds: cakes, jewels"),
                         ({"object": "hazard_sign", "at": "here", "kind": "cakes"}, "unknown hazard_sign kind"),
                         ({"object": "counter", "at": "here", "kind": "cakes"}, "kind is for a hazard_sign or a display_case"),
                         ({"object": "crib", "at": "here", "on": True}, "on is for"), ({"object": "bathtub", "at": "here", "open": True}, "open is for"),
                         ({"object": "vending_machin", "at": "here"}, "did you mean vending_machine")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso={**ISO, "objects": [bad]})


@pytest.mark.render
def test_the_shop_objects_render(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    room = "############\n#b..w..c.v.#\n#..........#\n#k..t..r...#\n#.......m..#\n#d...s.....#\n####+#######"
    spots = {"b": "bath", "w": "wardrobe", "c": "crib", "v": "vend", "k": "counter", "t": "table", "r": "till", "d": "case", "s": "stall", "m": "near"}
    kinds = {"bath": "bathtub", "wardrobe": "wardrobe", "crib": "crib", "vend": "vending_machine", "counter": "counter", "table": "cafe_table",
             "till": "cash_register", "case": "display_case", "stall": "market_stall"}
    objects = [{"object": kind, "at": spot, **({"on": True} if kind == "vending_machine" else {})} for spot, kind in kinds.items()]
    params = {"light": "night", "iso": {"place": "indoor", "map": room, "spots": spots, "objects": objects},
              "characters": [{"name": "pip", "at": "near"}]}
    beats = [{"text": "The shop at closing time.", "actions": [{"open": "wardrobe", "at": 0.5}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]   # frames_of renders the scene "home"
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "shop", monkeypatch)
    assert not scene._iso_gadget_places   # nothing here moves
    assert len(frames) > 5 and np.any(frames[-1] != frames[1])   # the wardrobe opens
