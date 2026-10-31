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
from test_iso_staging import FH, FW, looks
from vidgen import extensions, registry
from vidgen.cartoon.iso_drawing import Disc, canvas_for, draw_shapes
from vidgen.cartoon.iso_objects import LAMPLIGHT_KINDS, MORE_MODULES, MOVING_KINDS, OBJECT_COLORS, ObjectLook, object_motion, object_shapes
from vidgen.cartoon.iso_pictures import POOL_STRENGTH
from vidgen.cartoon.iso_scenery import IsoColors
from vidgen.cartoon.iso_stage import IsoScenery, iso_view
from vidgen.cartoon.lighting import POOL_DAY, light_grade, pool_strength
from vidgen.cartoon.iso_town import SIGNAL_COLORS
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

# ----- Step 263: town --------------------------------------------------------------------------------------

TOWN = ("street_lamp", "traffic_light", "bus_stop", "mailbox", "fountain", "phone_booth", "car", "bicycle", "newsstand")
TOWN_SIZES = {"bus_stop": (2, 1), "fountain": (2, 2), "car": (2, 1), "newsstand": (2, 1)}
TOWN_WORKING = ("street_lamp", "traffic_light", "fountain", "phone_booth", "car")
TOWN_MOVING = ("traffic_light", "fountain")


def test_town_objects_have_footprints_colours_and_states() -> None:
    for kind in TOWN:
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS and MORE_MODULES[kind] == "iso_town" and OBJECT_KINDS[kind].height <= 4.0
        assert (OBJECT_KINDS[kind].width, OBJECT_KINDS[kind].depth) == TOWN_SIZES.get(kind, (1, 1))
        assert default_state(kind) == ObjectState() and kind not in OPENING_KINDS and kind not in OBJECT_STYLES
    assert set(TOWN) & SWITCHED_KINDS == set(TOWN_WORKING) and set(TOWN) & set(MOVING_KINDS) == set(TOWN_MOVING)
    assert set(TOWN) & LAMPLIGHT_KINDS == {"street_lamp", "phone_booth"}


def test_town_objects_draw_light_up_and_move() -> None:
    place = _placed(TOWN)
    for item in place.objects:
        off = object_shapes(item, _look(item.kind), 0.0, ObjectState())
        assert off and not any(getattr(s, "glow", False) for s in off), item.kind
        if item.kind in TOWN_WORKING:
            on = object_shapes(item, _look(item.kind), 0.0, ObjectState(on=True))
            assert len(on) > len(off) and (item.kind == "fountain" or any(getattr(s, "glow", False) for s in on)), item.kind   # its water is no light
        if item.kind in TOWN_MOVING:
            early, late = (object_motion(item, _look(item.kind), 0.0, t, ObjectState(on=True)) for t in (0.2, 4.3))
            assert early and len(early) == len(late) and [(p.points, p.fill, p.opacity) for p in early] != [(p.points, p.fill, p.opacity) for p in late]
    lights = place.object("traffic_light")   # red, then green, then amber
    fills = [object_motion(lights, _look("traffic_light"), 0.0, t, ObjectState(on=True))[1].fill for t in (1.0, 5.0, 7.8)]
    assert fills == list(SIGNAL_COLORS[k] for k in (0, 2, 1))


def test_light_pools_are_warm() -> None:
    """A lit lamp's pool is rings of warm light (red over green over blue), not a pale tint (DESIGN.md §104)."""
    place = _placed(("street_lamp", "floor_lamp", "vending_machine", "phone_booth", "car", "campfire"))
    for item in place.objects:
        pool = [s for s in object_shapes(item, _look(item.kind), 0.0, ObjectState(on=True)) if isinstance(s, Disc) and s.pool and s.opacity < 1]
        assert len(pool) == 3, item.kind
        for disc in pool:
            r, g, b = (int(disc.fill[k:k + 2], 16) for k in (1, 3, 5))
            assert r > g > b and r - b > 120, item.kind


def test_town_keys_validate() -> None:
    good = stage_params(iso={**ISO, "objects": [{"object": "street_lamp", "at": "here", "on": True}, {"object": "car", "at": "there", "color": "#E2574C"}]})
    assert good.iso.objects[0].state().on and good.iso.objects[1].placing().color == "#E2574C"
    for bad, message in (({"object": "mailbox", "at": "here", "on": True}, "on is for"), ({"object": "car", "at": "here", "open": True}, "open is for"),
                         ({"object": "bicycle", "at": "here", "kind": "bmx"}, "kind is for a hazard_sign"),
                         ({"object": "streetlamp", "at": "here"}, "did you mean street_lamp"), ({"object": "fountian", "at": "here"}, "did you mean fountain")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso={**ISO, "objects": [bad]})


@pytest.mark.render
def test_the_town_objects_render_move_and_light(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    square = "..l..t..m..p\n:::y::::::::\n.s...f....n.\n............\n::::::::::::\n.c....b.....\n............"
    spots = {"l": "lamp", "t": "lights", "m": "mail", "p": "booth", "y": "near", "s": "stop", "f": "fountain", "n": "news", "c": "car", "b": "bike"}
    kinds = {"lamp": "street_lamp", "lights": "traffic_light", "mail": "mailbox", "booth": "phone_booth", "stop": "bus_stop", "fountain": "fountain",
             "news": "newsstand", "car": "car", "bike": "bicycle"}
    objects = [{"object": kind, "at": spot, **({"on": True} if kind in TOWN_WORKING else {})} for spot, kind in kinds.items()]
    params = {"light": "night", "iso": {"place": "outdoor", "map": square, "spots": spots, "objects": objects},
              "characters": [{"name": "pip", "at": "near"}]}
    beats = [{"text": "The square at night.", "actions": [{"switch_off": "car", "at": 0.6}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]   # frames_of renders the scene "home"
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "town", monkeypatch)
    places = {scene.iso_scenery.pieces[k].name: gadget for gadget, k, _ in scene._iso_gadget_places}
    assert set(places) == set(TOWN_MOVING)
    assert set(scene._iso_lamps) == {"street_lamp", "phone_booth"} and scene._iso_lamp_share("pip") > 0.0   # pip stands by the lit street lamp
    assert len(frames) > 5 and np.any(frames[-1] != frames[3])


# ----- Step 264: nature; pools of light by day ----------------------------------------------------------------

NATURE = ("campfire", "tent", "log", "stump", "mushroom_ring", "pond", "scarecrow", "beehive")
NATURE_SIZES = {"tent": (2, 2), "log": (2, 1), "mushroom_ring": (2, 2), "pond": (2, 2)}
NATURE_WORKING = ("campfire", "pond", "beehive")


def test_nature_objects_have_footprints_colours_and_states() -> None:
    for kind in NATURE:
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS and MORE_MODULES[kind] == "iso_nature" and OBJECT_KINDS[kind].height <= 2.4
        assert (OBJECT_KINDS[kind].width, OBJECT_KINDS[kind].depth) == NATURE_SIZES.get(kind, (1, 1))
        assert default_state(kind) == ObjectState() and kind not in OPENING_KINDS and kind not in OBJECT_STYLES
    assert set(NATURE) & SWITCHED_KINDS == set(NATURE) & set(MOVING_KINDS) == set(NATURE_WORKING)
    assert set(NATURE) & LAMPLIGHT_KINDS == {"campfire"} and OBJECT_KINDS["log"].top and OBJECT_KINDS["stump"].top


def test_nature_objects_draw_light_up_and_move() -> None:
    place = place_objects(parse_iso_map(WIDE.replace("#", ".").replace("+", "."), place="outdoor"),
                          tuple(ObjectPlacing(kind, (1 + (k % 4) * 2, 1 + (k // 4) * 3), facing="right" if k % 2 else "left") for k, kind in enumerate(NATURE)))
    for item in place.objects:
        off = object_shapes(item, _look(item.kind), 0.0, ObjectState())
        assert off and not any(getattr(s, "glow", False) for s in off if item.kind != "mushroom_ring"), item.kind
        if item.kind in NATURE_WORKING:
            on = object_shapes(item, _look(item.kind), 0.0, ObjectState(on=True))
            moving = object_shapes(item, _look(item.kind, True), 0.0, ObjectState(on=True))
            assert (on != off or item.kind == "pond") and len(moving) < len(on), item.kind   # a still pond: the same rings on or off
            early, late = (object_motion(item, _look(item.kind), 0.0, t, ObjectState(on=True)) for t in (0.2, 1.3))
            assert early and len(early) == len(late) and [(p.points, p.opacity) for p in early] != [(p.points, p.opacity) for p in late], item.kind
    fire, ring = place.object("campfire"), place.object("mushroom_ring")
    lit = object_shapes(fire, _look("campfire"), 0.0, ObjectState(on=True))
    assert any(getattr(s, "glow", False) for s in lit) and len([s for s in lit if isinstance(s, Disc) and s.pool]) == 3
    assert len(object_shapes(fire, _look("campfire", True), 0.0, ObjectState(on=True))) < len(lit)   # its flames left to the stage
    glowing = object_shapes(ring, _look("mushroom_ring"), 0.0)   # spots and a faint glow on the grass, at night only
    assert any(getattr(s, "glow", False) for s in glowing) and any(isinstance(s, Disc) and s.pool for s in glowing)


def test_nature_keys_validate() -> None:
    good = stage_params(iso={**ISO, "objects": [{"object": "campfire", "at": "here", "on": True}, {"object": "pond", "at": "there", "on": True}]})
    assert good.iso.objects[0].state().on and good.iso.objects[1].placing().kind == "pond"
    for bad, message in (({"object": "tent", "at": "here", "on": True}, "on is for"), ({"object": "beehive", "at": "here", "open": True}, "open is for"),
                         ({"object": "log", "at": "here", "kind": "oak"}, "kind is for a hazard_sign"),
                         ({"object": "campfir", "at": "here"}, "did you mean campfire"), ({"object": "mushrooms_ring", "at": "here"}, "did you mean mushroom_ring")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso={**ISO, "objects": [bad]})


def test_pools_of_light_are_their_own_picture_and_faint_by_day() -> None:
    """A lit lamp's pool is drawn only in the picture of the pools, which shows as strong as the
    light is dark (it was a strong orange patch by day, DESIGN.md §104); a front picture has none."""
    strengths = {name: pool_strength(light_grade(name)) for name in ("day", "morning", "indoor", "sunset", "night")}
    assert strengths["day"] == POOL_DAY < strengths["morning"] < strengths["indoor"] < strengths["sunset"] < strengths["night"] == 1.0
    assert 0.3 < strengths["indoor"] < 0.7 and 0.4 < strengths["sunset"] < 0.8
    place = place_objects(parse_iso_map("....\n....\n....", place="outdoor"), (ObjectPlacing("street_lamp", (2, 1)),))
    shapes = object_shapes(place.objects[0], _look("street_lamp"), 0.0, ObjectState(on=True))
    pools = [s for s in shapes if isinstance(s, Disc) and s.pool]
    canvas = canvas_for((-2.0, -3.0, 2.0, 2.0), 40)
    assert pools and not any(s.glow for s in pools)
    assert np.array_equal(np.asarray(draw_shapes(shapes, canvas)), np.asarray(draw_shapes([s for s in shapes if s not in pools], canvas)))
    alone = np.asarray(draw_shapes(shapes, canvas, pool=True))
    assert alone[..., 3].max() > 60 and np.asarray(draw_shapes(pools, canvas, pool=True))[..., 3].sum() >= alone[..., 3].sum()
    scenery = IsoScenery(place, IsoColors(), looks(place), iso_view(place, FW, FH), 30.0, states={"street_lamp": ObjectState(on=True)})
    assert scenery.pools(scenery.base()) and not scenery.pools((False, scenery.base()[1]))   # a front picture: no pool


@pytest.mark.render
def test_the_nature_objects_render_move_and_light(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    meadow = "...t....p......\n...........b.k.\n.m.............\n....g...c......\n..s.....y......\n..............."
    spots = {"t": "tent", "p": "pond", "b": "hive", "k": "crow", "m": "ring", "g": "log", "c": "fire", "s": "stump", "y": "near"}
    objects = [{"object": kind, "at": spot, **({"on": True} if kind in NATURE_WORKING else {})}
               for spot, kind in {"tent": "tent", "pond": "pond", "hive": "beehive", "crow": "scarecrow", "ring": "mushroom_ring", "log": "log",
                                  "fire": "campfire", "stump": "stump"}.items()]
    params = {"light": "night", "iso": {"place": "outdoor", "map": meadow, "spots": spots, "objects": objects},
              "characters": [{"name": "pip", "at": "near"}]}
    beats = [{"text": "A campfire under the stars.", "actions": [{"switch_off": "pond", "at": 0.6}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]   # frames_of renders the scene "home"
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "meadow", monkeypatch)
    places = {scene.iso_scenery.pieces[k].name: gadget for gadget, k, _ in scene._iso_gadget_places}
    assert set(places) == set(NATURE_WORKING)
    assert set(scene._iso_lamps) == {"campfire"} and scene._iso_lamp_share("pip") > 0.0   # pip sits by the fire
    assert getattr(scene.renderer.camera, POOL_STRENGTH) == 1.0   # the pools at full strength at night
    assert len(frames) > 5 and np.any(frames[-1] != frames[3])


# ----- Step 265: farm, school and office -----------------------------------------------------------------------

SCHOOL = ("vegetable_patch", "wheelbarrow", "hay_bale", "school_desk", "desk_with_pc", "water_cooler", "printer", "globe", "trophy_shelf")
SCHOOL_SIZES = {"vegetable_patch": (2, 1), "hay_bale": (2, 1), "desk_with_pc": (2, 1), "trophy_shelf": (2, 1)}
SCHOOL_WORKING = ("desk_with_pc", "water_cooler", "printer", "globe")


def test_school_objects_have_footprints_colours_and_states() -> None:
    for kind in SCHOOL:
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS and MORE_MODULES[kind] == "iso_school" and OBJECT_KINDS[kind].height <= 2.1
        assert (OBJECT_KINDS[kind].width, OBJECT_KINDS[kind].depth) == SCHOOL_SIZES.get(kind, (1, 1))
        assert default_state(kind) == ObjectState() and kind not in OPENING_KINDS and kind not in OBJECT_STYLES
    assert set(SCHOOL) & SWITCHED_KINDS == set(SCHOOL) & set(MOVING_KINDS) == set(SCHOOL_WORKING)
    assert not set(SCHOOL) & LAMPLIGHT_KINDS and OBJECT_KINDS["hay_bale"].top and OBJECT_KINDS["trophy_shelf"].top


def test_school_objects_draw_light_up_and_move() -> None:
    place = _placed(SCHOOL)
    for item in place.objects:
        off = object_shapes(item, _look(item.kind), 0.0, ObjectState())
        assert off and not any(getattr(s, "glow", False) for s in off), item.kind
        if item.kind in SCHOOL_WORKING:
            on = object_shapes(item, _look(item.kind), 0.0, ObjectState(on=True))
            moving = object_shapes(item, _look(item.kind, True), 0.0, ObjectState(on=True))
            assert (on != off or item.kind == "globe") and len(moving) < len(on), item.kind   # a still globe: the same on or off
            early, late = (object_motion(item, _look(item.kind), 0.0, t, ObjectState(on=True)) for t in (0.2, 1.3))
            assert early and len(early) == len(late) and [(p.points, p.opacity) for p in early] != [(p.points, p.opacity) for p in late], item.kind
    pc, globe = place.object("desk_with_pc"), place.object("globe")
    assert any(getattr(s, "glow", False) for s in object_shapes(pc, _look("desk_with_pc"), 0.0, ObjectState(on=True)))   # its screen
    still = object_shapes(globe, _look("globe", True), 0.0, ObjectState())   # off, its land is in its picture
    assert len(still) == len(object_shapes(globe, _look("globe"), 0.0, ObjectState()))


def test_school_keys_validate() -> None:
    good = stage_params(iso={**ISO, "objects": [{"object": "globe", "at": "here", "on": True}, {"object": "school_desk", "at": "there"}]})
    assert good.iso.objects[0].state().on and good.iso.objects[1].placing().kind == "school_desk"
    for bad, message in (({"object": "hay_bale", "at": "here", "on": True}, "on is for"), ({"object": "printer", "at": "here", "open": True}, "open is for"),
                         ({"object": "trophy_shelf", "at": "here", "kind": "gold"}, "kind is for a hazard_sign"),
                         ({"object": "water_coler", "at": "here"}, "did you mean water_cooler"), ({"object": "desk_pc", "at": "here"}, "did you mean desk_with_pc")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso={**ISO, "objects": [bad]})


@pytest.mark.render
def test_the_school_objects_render_and_move(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    room = "############\n#t..p..c...#\n#..........#\n#v...h..d..#\n#..........#\n#s.w..g.y..#\n####+#######"
    spots = {"t": "trophies", "p": "printer", "c": "cooler", "v": "patch", "h": "hay", "d": "pc", "s": "desk", "w": "barrow", "g": "globe", "y": "near"}
    kinds = {"trophies": "trophy_shelf", "printer": "printer", "cooler": "water_cooler", "patch": "vegetable_patch", "hay": "hay_bale",
             "pc": "desk_with_pc", "desk": "school_desk", "barrow": "wheelbarrow", "globe": "globe"}
    objects = [{"object": kind, "at": spot, **({"on": True} if kind in SCHOOL_WORKING else {})} for spot, kind in kinds.items()]
    params = {"light": "night", "iso": {"place": "indoor", "map": room, "spots": spots, "objects": objects},
              "characters": [{"name": "pip", "at": "near"}]}
    beats = [{"text": "Late at the school office.", "actions": [{"switch_off": "printer", "at": 0.6}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]   # frames_of renders the scene "home"
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "school", monkeypatch)
    places = {scene.iso_scenery.pieces[k].name: gadget for gadget, k, _ in scene._iso_gadget_places}
    assert set(places) == set(SCHOOL_WORKING) and not places["printer"].gadgets[0].working(float(scene.renderer.time))
    assert not scene._iso_lamps and len(frames) > 5 and np.any(frames[-1] != frames[3])
