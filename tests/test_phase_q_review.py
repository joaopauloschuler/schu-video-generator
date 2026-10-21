"""Step 171: the review of Phase Q (isometric places) — the wide view that fits the place to the
frame (16:9 and 9:16), a pan that moves in from it, lamplight on the characters near a lit lamp,
flower beds and hedges drawn a clump per cell, a bare YAML ``on:`` key in the JSON Schema, and
the clearer error messages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from test_iso_staging import FH, FW, ISO, iso_project, problems
from vidgen import extensions, registry, schema
from vidgen.cartoon.iso_drawing import Blobs, Disc
from vidgen.cartoon.iso_objects import ObjectLook, object_box, object_shapes
from vidgen.cartoon.iso_stage import ISO_PAN_ZOOM, ISO_WIDE_MAX, iso_stand, iso_view, place_bounds, standing_box, wide_view
from vidgen.cartoon.lighting import LAMP_LIFT, lamp_lit, light_grade
from vidgen.cartoon.shading import LAMP_LIT, LampLit, StageLight, mark_lamp_lit
from vidgen.theme import Theme
from vidgen.world.iso import ISO_CHARACTER_HEIGHT, ObjectPlacing, parse_iso_map, place_objects

VILLAGE = """
-.@.......@...~~..@.
..h......r....~~....
......w.......~~..&.
..............~~....
...a......d.l.~~....
.::::::::p:q::~~.y..
......j....:..~~....
.....g.....:s.~~....
....v.........~~....
-.&...........~~.&..
"""
SPOTS = {"h": "hazel_home", "r": "rowan_home", "a": "hazel_door", "d": "rowan_door", "l": "lamp", "w": "well", "g": "garden",
         "v": "lawn", "j": "green", "s": "bench", "y": "far_bank", "p": "porch", "q": "path_end"}
PLACED = [ObjectPlacing("house", "hazel_home", "hazel_house"), ObjectPlacing("house", "rowan_home", "rowan_house"),
          ObjectPlacing("lamp", "lamp"), ObjectPlacing("well", "well"), ObjectPlacing("bench", "bench"),
          ObjectPlacing("bridge", (15, 6), facing="right", size=(2, 1))]
PORTRAIT = (4.5, 8.0)


def village() -> Any:
    return place_objects(parse_iso_map(VILLAGE, names=SPOTS), PLACED)


def body(place: Any, spot: str) -> Any:
    return standing_box(place, iso_stand(place, spot), ISO_CHARACTER_HEIGHT)


def on_screen(place: Any, view: Any, bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Picture bounds (tile widths) in Manim units: left, bottom, right, top."""
    left, top, right, bottom = bounds
    return ((left - view.u0) * view.unit, -(bottom - view.v0) * view.unit, (right - view.u0) * view.unit, -(top - view.v0) * view.unit)


def inside(box: tuple[float, float, float, float], width: float, height: float, center: tuple[float, float]) -> bool:
    return (box[0] >= center[0] - width / 2 - 1e-9 and box[2] <= center[0] + width / 2 + 1e-9
            and box[1] >= center[1] - height / 2 - 1e-9 and box[3] <= center[1] + height / 2 + 1e-9)


# ----- the wide view (no manim) ---------------------------------------------------------------------


def test_the_wide_view_fills_a_landscape_frame_and_keeps_the_placed_objects_and_spots() -> None:
    place = village()
    view = iso_view(place, FW, FH)
    placed = [item.name for item in place.objects if item.kind in ("house", "lamp", "well", "bench", "bridge")]
    bodies = [body(place, spot) for spot in ("hazel_door", "well", "rowan_door")]
    width, center = wide_view(place, view, FW, FH, bodies, placed)
    scale = FW / width
    assert 1.15 < scale <= ISO_WIDE_MAX   # the whole place fitted left wide empty bands
    height = width * FH / FW
    for item in place.objects:
        if item.name in placed:   # whole: no roof cut
            assert inside(on_screen(place, view, object_box(item, 0.0).picture_bounds()), width, height, center), item.name
    for spot in SPOTS.values():
        assert inside(on_screen(place, view, body(place, spot).picture_bounds()), width, height, center), spot
    left, top, right, bottom = place_bounds(place)
    assert (right - left) * view.unit * scale >= FW * 0.9 - 1e-6   # the place spans the frame's width


def test_the_wide_view_of_a_portrait_frame_shows_where_the_characters_stand() -> None:
    place = village()
    view = iso_view(place, *PORTRAIT)
    bodies = [body(place, spot) for spot in ("hazel_door", "well", "rowan_door")]
    width, center = wide_view(place, view, *PORTRAIT, bodies, ["hazel_house"])
    assert PORTRAIT[0] / width == pytest.approx(ISO_WIDE_MAX)   # not the whole village small in the middle
    for box in bodies:
        assert inside(on_screen(place, view, box.picture_bounds()), width, width * PORTRAIT[1] / PORTRAIT[0], center)
    spread = [body(place, spot) for spot in ("hazel_home", "far_bank", "lawn")]
    assert PORTRAIT[0] / wide_view(place, view, *PORTRAIT, spread)[0] < ISO_WIDE_MAX   # everyone stays in view


def test_a_room_keeps_all_of_itself_in_a_landscape_frame() -> None:
    room = parse_iso_map("#####\n#...#\n#.k.#\n#...#\n##+##", names={"k": "middle"}, place="indoor")
    view = iso_view(room, FW, FH)
    width, center = wide_view(room, view, FW, FH, [body(room, "middle")])
    assert width == pytest.approx(FW) and center == pytest.approx((0.0, 0.0))


# ----- lamplight on the characters (no manim) ---------------------------------------------------


def test_a_lamp_lights_what_stands_near_it_only_in_the_dark() -> None:
    night, day = light_grade("night"), light_grade("day")
    assert lamp_lit(day, 1.0) is day and lamp_lit(night, 0.0) is night
    lit = lamp_lit(night, 1.0)
    assert all(a > b for a, b in zip(lit.multiply, night.multiply))   # brighter, warmer
    assert lit.multiply[0] - night.multiply[0] > lit.multiply[2] - night.multiply[2]   # warm: red lifted more than blue
    half = lamp_lit(night, 0.5)
    assert night.multiply[0] < half.multiply[0] < lit.multiply[0]
    assert 0 < LAMP_LIFT < 1


def test_the_stage_light_grades_a_lamp_lit_shape_with_its_lamplight() -> None:
    import numpy as np
    from manim import Square

    class Camera:
        def get_fill_rgbas(self, mob: Any) -> Any:
            return np.array([[0.8, 0.8, 0.8, 1.0]])

        def get_stroke_rgbas(self, mob: Any, *args: Any, **kwargs: Any) -> Any:
            return np.array([[0.8, 0.8, 0.8, 1.0]])

        def display_image_mobject(self, image: Any, pixels: Any) -> None:
            return None

    camera = Camera()
    StageLight(camera, light_grade("night"))
    plain, near = Square(), Square()
    for mob in (plain, near):
        setattr(mob, "light_graded", True)
    share = [1.0]
    mark_lamp_lit(near, LampLit(lambda: share[0]))
    assert getattr(near, LAMP_LIT) is not None
    dark, bright = camera.get_fill_rgbas(plain)[0, 0], camera.get_fill_rgbas(near)[0, 0]
    assert bright > dark
    share[0] = 0.0
    assert camera.get_fill_rgbas(near)[0, 0] == pytest.approx(dark)


# ----- flower beds and hedges (no manim) ------------------------------------------------------------


@pytest.mark.parametrize("kind,per_clump", [("flowers", 6), ("bush", 2)])
def test_a_larger_flower_bed_or_bush_draws_a_clump_in_each_cell(kind: str, per_clump: int) -> None:
    place = place_objects(parse_iso_map("....\n....\n....", names={}), [ObjectPlacing(kind, (1, 1), size=(3, 2))])
    one = place_objects(parse_iso_map("....\n....\n....", names={}), [ObjectPlacing(kind, (1, 1))])
    look = ObjectLook("#E06060", "#F0C040")
    bed = object_shapes(place.objects[0], look, 0.0)
    single = object_shapes(one.objects[0], look, 0.0)
    blobs = lambda shapes: [s for s in shapes if isinstance(s, Blobs)]   # noqa: E731
    discs = lambda shapes: [s for s in shapes if isinstance(s, Disc)]   # noqa: E731
    assert len(blobs(bed)) == 6 * len(blobs(single)) and len(discs(bed)) == 6 * len(discs(single)) == 6   # a shadow each
    middles = [s.centres[0][:2] for s in blobs(bed)][::per_clump]
    assert len({(round(x), round(y)) for x, y in [(m[0] - 0.5, m[1] - 0.5) for m in middles]}) == 6   # one per cell
    assert [sum(m) for m in middles] == sorted(sum(m) for m in middles)   # back to front


# ----- a bare `on:` in the JSON Schema ----------------------------------------------------------------


def test_a_bare_on_key_validates_against_the_schema_as_json_reads_it() -> None:
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), [Theme()])
    text = """
title: T
scenes:
  - id: s
    type: stage
    params:
      iso:
        map: |
          l..
        spots: {l: lamp}
        objects:
          - {object: lamp, at: lamp, on: true}
    beats: [{text: "Hi."}]
  - id: t
    type: stage
    params:
      props:
        - {prop: lamp, on: true}
    beats: [{text: "Hi."}]
"""
    data = json.loads(json.dumps(yaml.safe_load(text)))   # YAML 1.1 reads the key as true; JSON writes it "true"
    assert data["scenes"][0]["params"]["iso"]["objects"][0]["true"] is True
    errors = [e.message for e in jsonschema.Draft202012Validator(doc).iter_errors(data)]
    assert errors == []


# ----- clearer messages -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action,message",
    [({"jump": "pip", "to": "far"}, "an iso place has no jumping to a place: walk_to or run_to it")],
)
def test_staging_messages_name_the_alternative(make_project, action: dict[str, Any], message: str) -> None:
    found = problems(iso_project(make_project, [{"text": "Something happens.", "actions": [action]}]))
    assert any(message in text for _, text in found), found


def test_object_state_messages_read_well() -> None:
    from pydantic import ValidationError

    from test_cartoon_stage import stage_params

    with pytest.raises(ValidationError, match="not flowers"):
        stage_params(iso={**ISO, "objects": [{"object": "flowers", "at": "well", "on": True}]}, characters=[{"name": "pip", "at": "start"}])
    with pytest.raises(ValidationError, match="shot: closeup"):
        stage_params(iso=ISO, characters=[{"name": "pip", "at": "start"}], character_size="large")


# ----- a tiny render: the wide view, a pan, a wide shot and lamplight --------------------------------


@pytest.mark.render
def test_the_wide_view_pan_and_lamplight_render(make_project, tmp_path: Path) -> None:
    from test_cartoon_stage import render_with_layout
    from vidgen.introspect import LayoutRecorder

    beats = [
        {"text": "Night by the pond.", "actions": [{"switch_off": "lamp", "at": 0.6}]},
        {"text": "The camera looks at the well.", "actions": [{"action": "pan", "to": "well"}]},
        {"text": "Everyone again.", "shot": "wide"},
    ]
    project = iso_project(make_project, beats, light="night", characters=[{"name": "pip", "at": "start"}, {"name": "kit", "at": "well"}])
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "pond", tmp_path / "media", recorder)
    last = {frame["beat"]: frame for frame in recorder.frames}
    wide = last["pond_b1"]["camera"]["zoom"]
    assert wide >= 1.0
    assert last["pond_b2"]["camera"]["zoom"] >= ISO_PAN_ZOOM - 1e-6   # the pan moved in from the wide view
    assert last["pond_b3"]["camera"]["zoom"] == pytest.approx(wide, rel=0.05)
    assert scene._iso_lamp_level("lamp", 0.0) == 1.0 and scene._iso_lamp_level("lamp", 1e6) == 0.0   # switched off
    assert scene._iso_lamp_share("kit") == 0.0   # now: the lamp is off
    scene._iso_lamps["lamp"][1][:] = [(0.0, 0.0, 1.0)]
    scene._iso_lamp_time = -1.0
    assert scene._iso_lamp_share("kit") > 0.5 and scene._iso_lamp_share("pip") == 0.0   # by the lamp, across the pond
    assert isinstance(getattr(scene.cast["kit"], LAMP_LIT), LampLit)
