"""The retro-future kit (DESIGN.md §107): its iso objects, a car's rocket kind, a place's style and
textures, the blue-hour light, saucer and monorail traffic and the retro looks; logic without
rendering, and one small render."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST, stage_params
from vidgen import extensions, registry
from vidgen.cartoon.generator import generate_parts
from vidgen.cartoon.iso_drawing import Disc, Poly
from vidgen.cartoon.iso_objects import (LAMPLIGHT_KINDS, MORE_MODULES, MOVING_KINDS, OBJECT_COLORS, ObjectLook, object_box, object_colors,
                                        object_motion, object_shapes)
from vidgen.cartoon.iso_overlays import IsoTraffic, PodLane
from vidgen.cartoon.iso_scenery import DEFAULT_TEXTURES, STYLE_COLORS, TEXTURES, IsoColors, ground_shapes
from vidgen.cartoon.lighting import DUSK_DARK, darkness, grade_rgbas, light_grade
from vidgen.cartoon.room import window_sky
from vidgen.config import CharacterLook
from vidgen.project import Project
from vidgen.world.iso import (AUTO_LIGHT_KINDS, OBJECT_KINDS, SWITCHED_KINDS, TALL_KINDS, WALL_KINDS, ObjectPlacing, ObjectState, default_state,
                              parse_iso_map, place_objects)
from vidgen.world.iso_seats import ISO_USES

RETRO = ("googie_building", "retro_tower", "starburst_sign", "ray_lamp", "atomic_sculpture", "monorail", "tube_computer", "sunburst_clock",
         "tv_console", "retro_desk", "hedge", "planter")
WORKING = ("googie_building", "retro_tower", "starburst_sign", "ray_lamp", "atomic_sculpture", "tube_computer", "tv_console", "retro_desk")
MOVING = ("atomic_sculpture", "tube_computer", "tv_console")
FIELD = "\n".join(["." * 12] * 12)


def _look(kind: str, moving: bool = False) -> ObjectLook:
    return ObjectLook(*OBJECT_COLORS[kind], moving=moving)


def _placed():
    spots = {"googie_building": (1, 1), "retro_tower": (5, 1), "starburst_sign": (8, 1), "ray_lamp": (9, 1), "atomic_sculpture": (10, 1),
             "monorail": (1, 5), "tube_computer": (6, 5), "tv_console": (9, 5), "retro_desk": (1, 7), "hedge": (4, 7), "planter": (6, 7)}
    return place_objects(parse_iso_map(FIELD), [ObjectPlacing(kind, at) for kind, at in spots.items()])


def test_the_retro_objects_have_footprints_colours_and_states() -> None:
    for kind in RETRO:
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS and MORE_MODULES[kind] == "iso_retro"
    assert set(RETRO) & SWITCHED_KINDS == set(WORKING) and set(RETRO) & set(MOVING_KINDS) == set(MOVING)
    assert "ray_lamp" in LAMPLIGHT_KINDS and {"googie_building", "starburst_sign", "ray_lamp"} <= AUTO_LIGHT_KINDS
    assert "sunburst_clock" in WALL_KINDS and TALL_KINDS["retro_tower"] == (4.0, 30.0) and default_state("retro_tower").on
    assert OBJECT_KINDS["retro_desk"].top is not None and {"retro_desk", "tube_computer", "tv_console"} <= set(ISO_USES)


def test_the_retro_objects_draw_light_up_and_move() -> None:
    place = _placed()
    for item in place.objects:
        off = object_shapes(item, _look(item.kind), 0.0, ObjectState())
        assert off and not any(getattr(s, "glow", False) for s in off), item.kind
        if item.kind in WORKING:
            on = object_shapes(item, _look(item.kind), 0.0, ObjectState(on=True))
            assert any(getattr(s, "glow", False) for s in on), item.kind
        if item.kind in MOVING:
            early, late = (object_motion(item, _look(item.kind), 0.0, t, ObjectState(on=True)) for t in (0.2, 1.1))
            assert early and len(early) == len(late) and [(p.points, p.opacity) for p in early] != [(p.points, p.opacity) for p in late], item.kind
    lamp = object_shapes(place.object("ray_lamp"), _look("ray_lamp"), 0.0, ObjectState(on=True))
    assert len([s for s in lamp if isinstance(s, Disc) and s.pool]) == 3   # a warm pool of light
    atom = place.object("atomic_sculpture")   # its electrons left to the stage while it works
    assert len(object_shapes(atom, _look("atomic_sculpture", True), 0.0, ObjectState(on=True))) < len(object_shapes(atom, _look("atomic_sculpture"), 0.0, ObjectState(on=True)))
    hedge = place_objects(parse_iso_map(FIELD), [ObjectPlacing("hedge", (1, 1), size=(5, 1))]).object("hedge")
    assert object_box(hedge, 0.0).x1 - object_box(hedge, 0.0).x0 == 5


def test_kinds_a_rocket_car_and_a_console_face() -> None:
    place = place_objects(parse_iso_map(FIELD), [ObjectPlacing("car", (1, 1)), ObjectPlacing("car", (1, 3), features=("rocket",)),
                                                 ObjectPlacing("tv_console", (5, 5), features=("face",)), ObjectPlacing("tv_console", (7, 5))])
    sedan, rocket = (object_shapes(place.objects[k], _look("car"), 0.0, ObjectState(on=True)) for k in (0, 1))
    assert len(sedan) != len(rocket)
    face, wave = (object_motion(place.objects[k], _look("tv_console"), 0.0, 0.5) for k in (2, 3))
    assert len(face) == 3 and len(wave) == 2   # two eyes over a mouth; a grid line under a wave
    from vidgen.cartoon.iso_driving import vehicle_shapes
    assert len(vehicle_shapes("car", _look("car"), heading=(1, 0), on=False, features=("rocket",))) != len(vehicle_shapes("car", _look("car"), heading=(1, 0), on=False))


ISO = {"place": "indoor", "map": "#########\n#.......#\n#.l.k...#\n#.......#\n####+####", "spots": {"l": "here", "k": "there"}}


@pytest.mark.slow
def test_retro_keys_validate() -> None:
    good = stage_params(iso={**ISO, "style": "retro", "textures": {"floor": "checker"},
                             "objects": [{"object": "car", "at": "here", "kind": "rocket"}, {"object": "sunburst_clock", "at": {"column": 4, "row": 1}, "time": "03:27"},
                                         {"object": "retro_tower", "at": "there", "height": 12}]})
    assert good.iso.style == "retro" and good.iso.objects[0].placing().features == ("rocket",)
    for bad, message in (({"object": "car", "at": "here", "kind": "rockt"}, "did you mean rocket"), ({"object": "googie_bulding", "at": "here"}, "did you mean googie_building"),
                         ({"object": "retro_tower", "at": "here", "height": 3}, "retro_tower's height is 4 to 30"),
                         ({"object": "hedge", "at": "here", "on": True}, "on is for"), ({"object": "planter", "at": "here", "time": "03:00"}, "time is for a wall_clock or a sunburst_clock")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso={**ISO, "objects": [bad]})
    with pytest.raises(ValidationError):
        stage_params(iso={**ISO, "textures": {"floor": "marble"}})
    lane = stage_params(iso={"map": FIELD, "traffic": [{"from": {"column": 1, "row": 1}, "to": {"column": 9, "row": 9}, "shape": "monorail"}]})
    assert lane.iso.traffic[0].shape == "monorail"


def test_a_style_and_textures_dress_the_ground() -> None:
    place = parse_iso_map("..::\n..::\n..::")
    plain = ground_shapes(place, IsoColors())
    assert plain == ground_shapes(place, IsoColors(textures=tuple(DEFAULT_TEXTURES.items())))   # the own textures change nothing
    for texture in TEXTURES:
        shapes = ground_shapes(place, IsoColors(textures=(("path", texture), ("grass", texture))))
        assert shapes, texture
    checker = ground_shapes(place, IsoColors(textures=(("path", "checker"),)))
    assert len([s for s in checker if isinstance(s, Poly)]) > len([s for s in plain if isinstance(s, Poly)])
    assert set(STYLE_COLORS["retro"]) <= set(IsoColors.__dataclass_fields__)
    assert object_colors("house", "retro") != OBJECT_COLORS["house"] and object_colors("house") == OBJECT_COLORS["house"]
    assert object_colors("tube_computer", "retro") == OBJECT_COLORS["tube_computer"]


def test_blue_hour_is_a_bright_clean_night() -> None:
    blue, night = light_grade("blue_hour"), light_grade("night")
    assert sum(blue.multiply) > sum(night.multiply) * 1.25 and darkness(blue) >= DUSK_DARK   # lamps glow, pools show
    assert blue.saturation > 1.0 and blue.stars > 0 and blue.multiply[2] > blue.multiply[0]
    rows = np.array([[0.0, 0.0, 0.0, 1.0], [1.0, 0.5, 0.4, 1.0]])
    graded = grade_rgbas(rows, blue)
    assert np.all((graded >= 0.0) & (graded <= 1.0)) and graded[1, 0] > graded[1, 2]   # coral stays warm (§108: crisp, not a haze)
    assert window_sky("blue_hour").stars > 0


def test_saucers_and_trains_glide() -> None:
    lanes = [PodLane((0.0, 0.0), (4.0, -2.0), 4.0, 1, "#FF7F6B", 0.4, shape=shape) for shape in ("capsule", "saucer", "monorail")]
    traffic = IsoTraffic(lanes)
    hulls = [traffic.pods[k][0][2] for k in range(3)]
    widths = [float(np.ptp(h.points[:, 0])) for h in hulls]
    assert widths[1] > widths[0] and widths[2] > widths[1]   # a saucer wider than a pod, a train longer


@pytest.mark.slow
@pytest.mark.parametrize("front", [False, True])
def test_retro_looks_draw(front: bool) -> None:
    colors = {"skin": "#F0D2B4", "clothes": "#3C6E71", "trim": "#F4EBDD", "outline": "#1F2430", "features": "#1F2430", "hair": "#2A1810",
              "accessory": "#FF7F6B"}
    for look in (CharacterLook(hair="pompadour", outfit="suit", accessories=["fedora"]), CharacterLook(hair="bob", outfit="jumpsuit", accessories=["pillbox"]),
                 CharacterLook(hair="wavy", outfit="lab_coat")):
        parts = {p.name: p for p in generate_parts(look, colors, front=front)}
        assert "accessory" in parts or not look.accessories
        if look.outfit == "lab_coat":
            assert "seated" in parts["body"].shapes   # its tails lie over the lap
    with pytest.raises(ValidationError, match="worn on top of the head"):
        CharacterLook(accessories=["fedora", "hat"])


@pytest.mark.slow
@pytest.mark.render
def test_a_retro_street_renders_at_blue_hour(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    street = "............\n.g....s.....\n............\n::::::a:::::\n............\n..r...t.....\n............"
    spots = {"g": "diner", "s": "sign", "a": "near", "r": "atom", "t": "tv"}
    objects = [{"object": "googie_building", "at": "diner", "on": True}, {"object": "starburst_sign", "at": "sign", "on": True},
               {"object": "atomic_sculpture", "at": "atom", "on": True}, {"object": "ray_lamp", "at": "tv", "on": True}]
    params = {"light": "blue_hour", "iso": {"map": street, "spots": spots, "objects": objects, "style": "retro",
                                            "traffic": [{"from": "diner", "to": "tv", "height": 4}]},
              "characters": [{"name": "pip", "at": "near"}]}
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": [{"text": "A street of tomorrow."}]}]
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "street", monkeypatch)
    places = {scene.iso_scenery.pieces[k].name for _, k, _ in scene._iso_gadget_places}
    assert places == {"atomic_sculpture"} and "ray_lamp" in scene._iso_lamps
    assert len(frames) > 5 and np.any(frames[-1] != frames[3])
