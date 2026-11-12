"""Step 279 fixes (DESIGN.md §108): a crisp blue hour (hues kept, a tone curve), a coloured fill
light, ``bright`` eyes, thin strokes one pixel of the fixed wide view (``pixel_zoom``) and a room
framed from its back corner (``show_walls``); logic without rendering, and one small render."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST, stage_params
from vidgen import extensions, registry
from vidgen.cartoon.character import one_pixel_stroke, pixel_zoom
from vidgen.cartoon.generator import BRIGHT_EYE, generate_parts
from vidgen.cartoon.iso_stage import WALL_VIEW_MARGIN, fixed_tiles, fixed_view, iso_view, on_ground, wall_reach
from vidgen.cartoon.lighting import (PRESET_TONES, LightGrade, blend_grades, grade_pixels, grade_rgbas, lifted, light_grade, tint_grade)
from vidgen.cartoon.storm import flash_grade
from vidgen.cartoon.vignette import flashback_grade
from vidgen.config import CharacterLook
from vidgen.project import Project
from vidgen.cartoon.iso_objects import OBJECT_COLORS, ObjectLook, object_box, object_shapes
from vidgen.world.iso import POSTER_PICTURES, WALL_HEIGHT, WALL_KINDS, ObjectPlacing, parse_iso_map, place_objects
from vidgen.world.iso_view import ISO_RISE

MINT, CORAL, CREAM = (0.62, 0.9, 0.78), (1.0, 0.5, 0.42), (0.96, 0.92, 0.87)


def _graded(color: tuple[float, float, float], grade: LightGrade) -> np.ndarray:
    return grade_rgbas(np.array([[*color, 1.0]]), grade)[0, :3]


def test_blue_hour_is_crisp_its_colours_keep_their_hues() -> None:
    blue, night = light_grade("blue_hour"), light_grade("night")
    assert blue.curved and blue.gamma > 1.0 and blue.contrast > 1.0 and blue.glow == (0.0, 0.0, 0.0)
    flat = LightGrade(blue.multiply, blue.glow, blue.stars, blue.shadow)   # the tint alone
    coral, mint = _graded(CORAL, blue), _graded(MINT, blue)
    assert coral[0] > coral[2] and mint[1] > mint[0]   # coral stays warm, mint green-teal
    assert np.ptp(coral) > np.ptp(_graded(CORAL, flat))   # more saturated than the tint alone
    spread = _graded(CREAM, blue).mean() - _graded((0.3, 0.3, 0.35), blue).mean()
    assert spread > _graded(CREAM, flat).mean() - _graded((0.3, 0.3, 0.35), flat).mean()   # more contrast
    assert _graded(CREAM, blue).mean() > _graded(CREAM, night).mean() + 0.1   # clearly brighter than night
    assert _graded((0.0, 0.0, 0.0), blue).max() < 0.02   # clean blacks, no haze
    picture = grade_pixels(np.array([[[245, 235, 222], [255, 128, 107]]], dtype=np.uint8), blue)[0] / 255
    assert np.allclose(picture, [_graded(CREAM, blue), _graded(CORAL, blue)], atol=0.02)   # pictures graded the same way
    day = light_grade("day")
    assert not day.changes_colors and "blue_hour" in PRESET_TONES
    assert np.array_equal(grade_rgbas(np.array([[0.2, 0.4, 0.6, 1.0]]), light_grade("sunset")),
                          grade_rgbas(np.array([[0.2, 0.4, 0.6, 1.0]]), tint_grade("#FF8A5C", 0.55, glow=(0.13, 0.04, 0.03))))


@pytest.mark.slow
def test_fill_lights_fades_and_flashes_carry_the_curve() -> None:
    blue = light_grade("blue_hour")
    warm = tint_grade("#FFE6C4", 1.0).multiply
    lit = lifted(blue, 0.7, warm)
    assert lit.multiply[0] > lit.multiply[2] and 1.0 <= lit.gamma < blue.gamma and 1.0 <= lit.contrast < blue.contrast
    assert lit.saturation < blue.saturation and lifted(blue, 0.7).multiply[2] > lit.multiply[2]   # warm: less blue than white
    assert lifted(blue, 0.0, warm) is blue
    half = blend_grades(blue, light_grade("day"), 0.5)
    assert half.gamma == pytest.approx((blue.gamma + 1) / 2) and half.contrast == pytest.approx((blue.contrast + 1) / 2)
    assert blend_grades(blue, blue, 0.3).gamma == blue.gamma
    assert flash_grade(blue, 0.5).gamma == blue.gamma and flashback_grade(blue).contrast == blue.contrast and flashback_grade(blue).vivid <= 1.0
    with pytest.raises(ValidationError):
        stage_params(fill_light=0.5, fill_color=12)
    assert stage_params(fill_light=0.5, fill_color="#FFE6C4").fill_color == "#FFE6C4"


@pytest.mark.slow
def test_bright_eyes_have_a_clear_white_a_fine_rim_and_a_catchlight() -> None:
    colors = {"skin": "#F0D2B4", "clothes": "#3C6E71", "outline": "#1F2430", "features": "#1F2430", "hair": "#2A1810"}
    eyes = {}
    for kind in ("round", "bright"):
        parts = {p.name: p for p in generate_parts(CharacterLook(eyes=kind), colors)}
        eyes[kind] = parts["eyes"].shapes["open"]
    one_round, one_bright = eyes["round"][0], eyes["bright"][0]
    assert len(one_round) == 2 and len(one_bright) == 3   # white, pupil, catchlight
    assert one_bright[0].get_stroke_width() < one_round[0].get_stroke_width()
    assert one_bright[1].width < one_round[1].width and BRIGHT_EYE[1] > BRIGHT_EYE[0]
    with pytest.raises(ValidationError):
        CharacterLook(eyes="brite")


def test_pixel_zoom_thins_the_one_pixel_floor() -> None:
    plain = one_pixel_stroke()
    with pixel_zoom(4.0):
        assert one_pixel_stroke() == pytest.approx(plain / 4)
        with pixel_zoom(0.5):   # never wider than the frame
            assert one_pixel_stroke() == pytest.approx(plain)
        assert one_pixel_stroke() == pytest.approx(plain / 4)
    assert one_pixel_stroke() == plain


ROOM = "\n".join(["#" * 20] + ["#" + "." * 18 + "#"] * 18 + ["#" * 20])


def test_standing_back_walls_let_the_view_reach_behind_the_floor() -> None:
    room = parse_iso_map(ROOM, place="indoor")
    assert wall_reach(room) == pytest.approx(2 * WALL_HEIGHT * ISO_RISE - WALL_VIEW_MARGIN)
    assert wall_reach(parse_iso_map(ROOM.replace("#", "."))) == 0.0   # outdoors
    gap = ROOM.splitlines()
    gap[0] = "#" * 5 + " " + "#" * 14   # a back edge with a hole: no reach
    assert wall_reach(parse_iso_map("\n".join(gap), place="indoor")) == 0.0
    back = wall_reach(room)
    assert on_ground(room, 0.0, -50.0, 3.0, 2.0, back)[1] < on_ground(room, 0.0, -50.0, 3.0, 2.0)[1]
    fw, fh = 16.0, 9.0
    view = iso_view(room, fw, fh)
    tiles = fixed_tiles(fw, fh, "large")
    plain_width, plain_center = fixed_view(room, view, fw, fh, tiles)
    width, center = fixed_view(room, view, fw, fh, tiles, back=back)
    assert width == plain_width and center[1] > plain_center[1] and center[0] == pytest.approx(0.0, abs=1e-6)   # up, on the back corner


def test_show_walls_is_for_a_room_with_the_fixed_view() -> None:
    iso = {"place": "indoor", "map": ROOM, "wide": "fixed", "show_walls": True}
    params = stage_params(iso=iso)
    assert params.iso.wall_room() == pytest.approx(wall_reach(params.iso.parsed()))
    assert stage_params(iso={**iso, "show_walls": False}).iso.wall_room() == 0.0
    for bad in ({**iso, "wide": "auto"}, {**iso, "place": "outdoor", "map": ROOM.replace("#", ".")}):
        with pytest.raises(ValidationError, match="show_walls"):
            stage_params(iso=bad)


def test_posters_and_shelves_dress_the_walls() -> None:
    room = parse_iso_map(ROOM, place="indoor")
    placings = [ObjectPlacing("poster", (4 + 2 * k, 1), features=(picture,)) for k, picture in enumerate(POSTER_PICTURES)]   # 1-based
    placings += [ObjectPlacing("wall_shelf", (1, 5)), ObjectPlacing("poster", (1, 8))]
    placed = place_objects(room, placings)
    assert {"poster", "wall_shelf"} <= WALL_KINDS
    pictures = []
    for item in placed.objects:
        shapes = object_shapes(item, ObjectLook(*OBJECT_COLORS[item.kind]), 0.0)
        box = object_box(item, 0.0)
        assert shapes and box.z0 > 1.0 and box.z1 < WALL_HEIGHT, item.name
        pictures.append(len(shapes))
    assert len(set(pictures[:3])) > 1   # each picture its own drawing
    assert placed.object("poster_4").facing == "right"   # on the left back wall it turns to the room
    with pytest.raises(Exception, match="standing wall"):
        place_objects(room, [ObjectPlacing("poster", (6, 6))])
    with pytest.raises(ValidationError, match="did you mean atom"):
        stage_params(iso={"place": "indoor", "map": ROOM, "objects": [{"object": "poster", "at": {"column": 4, "row": 1}, "kind": "atomm"}]})


@pytest.mark.slow
@pytest.mark.render
def test_a_room_framed_from_its_back_corner_renders(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    rows = ROOM.splitlines()
    rows[3] = "#..a..............#"
    params = {"light": "blue_hour", "fill_light": 0.6, "fill_color": "#FFE6C4", "character_size": "large",
              "iso": {"place": "indoor", "map": "\n".join(rows), "spots": {"a": "desk"}, "wide": "fixed", "show_walls": True},
              "characters": [{"name": "pip", "at": "desk"}]}
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": [{"text": "A room at blue hour."}]}]
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), tmp_path / "room", monkeypatch)
    assert scene.zoom_base() > 1.0 and len(frames) > 3
