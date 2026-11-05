"""Step 271: iso weather (DESIGN.md §105.4) — the place's lights mirrored in its puddles at night,
fog lying over the place in bands by depth, and its plants and balloons swaying in the wind; a
tiny render of all three."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST
from test_iso_moves import problems
from test_iso_staging import looks
from vidgen import extensions, registry
from vidgen.cartoon.fog import FOG_DEPTHS, ISO_FOG_LAYER_SHARES, iso_band_outlines, iso_fog_depths
from vidgen.cartoon.iso_drawing import Disc, Poly
from vidgen.cartoon.iso_scenery import IsoColors
from vidgen.cartoon.iso_stage import IsoScenery, iso_view
from vidgen.cartoon.iso_weather import (
    ISO_SWAYS,
    REFLECTION_SHIMMER,
    IsoPuddle,
    clip_convex,
    glow_outlines,
    iso_sway_degrees,
    mirrored,
    puddle_lights,
    puddle_outline,
    reflection,
    still_reflection,
    sway_rows,
)
from vidgen.particle_field import ParticleSettings, settle_problem
from vidgen.project import Project
from vidgen.world.iso import OBJECT_KINDS, ObjectPlacing, parse_iso_map, place_objects
from vidgen.world.iso_view import ISO_RISE, Box3, iso_point


def test_weather_rules_do_not_import_manim() -> None:
    code = "import sys, vidgen.cartoon.iso_weather, vidgen.cartoon.fog; assert 'manim' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


# ----- reflections (no manim) -------------------------------------------------------------------------


def test_a_light_mirrors_as_far_under_the_water_as_it_stands_over_it() -> None:
    image = mirrored([(3.0, 4.0, 2.0)], 0.0)
    assert tuple(image[0]) == pytest.approx(iso_point(3.0, 4.0, -2.0))
    assert image[0][1] - iso_point(3.0, 4.0, 0.0)[1] == pytest.approx(2.0 * ISO_RISE)   # under its foot on the picture


def test_lights_are_glowing_shapes_not_pools_of_light() -> None:
    window = Poly(((0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 0.0, 2.0)), "#FFE08A", glow=True)
    wall = Poly(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 1.0)), "#888888")
    bulb = Disc((2.0, 2.0, 3.0), 0.1, "#FFF2B0", glow=True)
    pool = Disc((2.0, 2.0, 0.0), 1.1, "#FFD27A", opacity=0.4, glow=True, pool=True)
    found = glow_outlines([window, wall, bulb, pool])
    assert [color for _, color in found] == ["#FFE08A", "#FFF2B0"] and len(found[1][0]) == 16


def test_clipping_keeps_the_part_inside() -> None:
    square = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
    window = np.array([[1.0, 1.0], [3.0, 1.0], [3.0, 3.0], [1.0, 3.0]])
    cut = clip_convex(square, window)
    assert cut.min(axis=0) == pytest.approx([1.0, 1.0]) and cut.max(axis=0) == pytest.approx([2.0, 2.0])
    assert len(clip_convex(square, window[::-1])) == 4   # either turning sense
    assert len(clip_convex(square, window + 5.0)) == 0


def test_a_reflection_stays_inside_its_puddle_also_when_it_wobbles() -> None:
    puddle = IsoPuddle(5.0, 5.0, 0.0, 0.4, 7)
    neon = (((4.5, 4.5, 0.0), (4.5, 4.5, 3.0), (4.6, 4.4, 3.0), (4.6, 4.4, 0.0)), "#FF4FA3")   # a trim up a wall behind it
    far = (((1.0, 1.0, 0.5), (1.2, 1.0, 0.5), (1.2, 1.0, 0.7)), "#FFFFFF")
    assert puddle_lights(puddle, [neon, far]) == [0]
    outline = puddle_outline(puddle)
    left, right = outline[:, 0].min(), outline[:, 0].max()
    for seconds in (0.0, 0.3, 1.7):
        shape = reflection(puddle, neon, size=1.0, seconds=seconds, rain=1.0)
        assert len(shape) >= 3 and left - 1e-9 <= shape[:, 0].min() and shape[:, 0].max() <= right + 1e-9
    still = still_reflection(puddle, neon, size=1.0)
    moved = reflection(puddle, neon, size=1.0, seconds=0.3, rain=1.0)
    assert 0 < np.abs(moved - still).max() <= REFLECTION_SHIMMER + 1e-9
    assert np.array_equal(reflection(puddle, neon, size=1.0, seconds=0.3, rain=0.0), still)   # still water after the rain
    assert len(still_reflection(puddle, neon, size=0.0)) == 0
    assert np.ptp(still_reflection(puddle, neon, size=1.0, widen=0.06)[:, 0]) > np.ptp(still[:, 0])   # the glow is wider


# ----- wind (no manim) --------------------------------------------------------------------------------


def test_swaying_kinds_are_objects_and_lean_with_the_wind() -> None:
    assert set(ISO_SWAYS) <= set(OBJECT_KINDS)
    assert iso_sway_degrees("tree", 0.0, 1.0) == 0.0
    assert iso_sway_degrees("tree", 0.6, 0.0) > 0 > iso_sway_degrees("tree", -0.6, 0.0)
    assert abs(iso_sway_degrees("tree", 1.0, 0.0)) > abs(iso_sway_degrees("tree", 0.3, 0.0)) * 3   # a gale bends far more than a breeze
    assert abs(iso_sway_degrees("balloon_bunch", 0.6, 0.0)) > abs(iso_sway_degrees("scarecrow", 0.6, 0.0))


def test_a_windy_day_bends_trees_visibly_and_balloons_swing_whole() -> None:
    """Step 275: on a windy day (0.6) a tree leans enough to read at a preview's size and a gale
    does not throw it flat; a bunch of balloons swings about its foot (turned, not stretched)."""
    from vidgen.cartoon.iso_weather import ISO_SWINGS, swing_pixels

    assert 7.0 < iso_sway_degrees("tree", 0.6, 0.0) < 12.0 and iso_sway_degrees("tree", 1.0, 0.0) < 20.0
    assert iso_sway_degrees("tree", 0.3, 0.0) > 3.0   # a breeze shows too
    assert ISO_SWINGS == {"balloon_bunch"} and iso_sway_degrees("balloon_bunch", 1.0, 0.0) < 35.0
    pixels = np.zeros((40, 30, 4), dtype=np.uint8)
    pixels[5:12, 11:19] = (220, 60, 60, 255)   # a balloon over its string
    pixels[12:40, 14:16] = (240, 240, 240, 255)
    assert np.array_equal(swing_pixels(pixels, 40.0, 15.0, 0.0), pixels)
    swung = swing_pixels(pixels, 40.0, 15.0, 20.0)
    def columns(image: np.ndarray, rows: slice) -> tuple[float, float]:
        alpha = image[rows, :, 3].astype(float).sum(axis=0)
        found = np.flatnonzero(alpha > 128)
        return float(found.min()), float(found.max())
    left, right = columns(pixels, slice(5, 12))
    left2, right2 = columns(swung, slice(0, 14))
    assert left2 > left + 3 and (right2 - left2) == pytest.approx(right - left, abs=2)   # moved right, as wide: not stretched
    assert columns(swung, slice(37, 40))[0] == pytest.approx(columns(pixels, slice(37, 40))[0], abs=1)   # the foot stays


def test_bending_moves_the_top_and_keeps_the_foot() -> None:
    pixels = np.zeros((40, 30, 4), dtype=np.uint8)
    pixels[5:40, 12:16] = (90, 60, 30, 255)   # a trunk from its foot (row 40) up
    assert np.array_equal(sway_rows(pixels, 40.0, 35.0, 0.0), pixels)
    bent = sway_rows(pixels, 40.0, 35.0, 20.0)
    def middle(image: np.ndarray, row: int) -> float:
        alpha = image[row, :, 3].astype(float)
        return float((alpha * np.arange(image.shape[1])).sum() / alpha.sum())
    assert middle(bent, 39) == pytest.approx(middle(pixels, 39), abs=0.05)   # the foot stays
    assert middle(bent, 6) > middle(pixels, 6) + 5   # the top leans right
    assert middle(sway_rows(pixels, 40.0, 35.0, -20.0), 6) < middle(pixels, 6) - 5
    assert bent[6, :, :3][bent[6, :, 3] == 255].tolist() == [[90, 60, 30]] * int((bent[6, :, 3] == 255).sum())   # no dark fringe
    assert abs(int(bent[..., 3].astype(int).sum()) - int(pixels[..., 3].astype(int).sum())) < 255 * 2


# ----- fog (no manim) ---------------------------------------------------------------------------------


def test_fog_bands_lie_from_the_back_to_near_the_front() -> None:
    depths = iso_fog_depths(20.0, 0.0)
    assert depths[0] == 0.0 and list(depths) == sorted(depths) and depths[-1] < 20.0 and len(depths) == len(FOG_DEPTHS)
    layers = iso_band_outlines(1, -1.0, -5.0, 5.0, 4.0, 0.5, 0.0, 3)
    assert len(layers) == len(ISO_FOG_LAYER_SHARES)
    assert layers[0][:, 1].max() == 4.0   # the haze up to the top
    assert all(layer[:, 1].min() <= -1.0 for layer in layers) and max(layer[:, 1].max() for layer in layers[1:]) < 4.0
    drifted = iso_band_outlines(1, -1.0, -5.0, 5.0, 4.0, 0.5, 0.3, 3)
    assert not np.allclose(drifted[1], layers[1])


# ----- the scenery: a swaying object on its own -----------------------------------------------------------


def test_a_swaying_object_leaves_the_pictures_but_keeps_the_rain_off() -> None:
    place = place_objects(parse_iso_map(".....\n.....\n..t..\n.....\n.p...", names={"t": "oak", "p": "pip"}),
                          [ObjectPlacing("tree", "oak"), ObjectPlacing("lamp", (4, 4))])
    view = iso_view(place, 8 * 16 / 9, 8.0)
    plain = IsoScenery(place, IsoColors(), looks(place), view, 20.0)
    apart = IsoScenery(place, IsoColors(), looks(place), view, 20.0, apart=["tree"])
    k = apart.index["tree"]
    assert any(j == k for j, _ in plain.base()[1]) and not any(j == k for j, _ in apart.base()[1])
    box = Box3(1.6, 1.6, 0.0, 2.4, 2.4, 1.6)   # a character right behind the tree
    assert k in plain.over(box) and any(j == k for j, _ in plain.front(box)[1]) and not any(j == k for j, _ in apart.front(box)[1])
    assert np.array_equal(plain.top_surface().tops, apart.top_surface().tops)   # its crown still keeps the rain off


# ----- validation ---------------------------------------------------------------------------------------------

MAP = """
............
............
....t.......
::::::::::::
....s....g..
............
............
"""
OBJECTS = [{"object": "tree", "at": "oak"}, {"object": "street_lamp", "at": {"column": 7, "row": 3}, "on": True},
           {"object": "balloon_bunch", "at": {"column": 10, "row": 2}, "on": True},
           {"object": "tower", "at": {"column": 7, "row": 1}, "height": 4},
           {"object": "phone_booth", "at": {"column": 2, "row": 4}, "on": True}]


def weather_project(make_project, beats: list[dict[str, Any]], **params: Any) -> Project:
    iso = {"map": MAP, "spots": {"s": "square", "g": "gate", "t": "oak"}, "objects": OBJECTS}
    params = {"idle": False, "iso": iso, "characters": [{"name": "pip", "at": "square"}, {"name": "kit", "at": "gate"}], **params}
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


def stage_params(**params: Any) -> Any:
    from vidgen.scenes.stage import Stage

    iso = {"map": MAP, "spots": {"s": "square", "g": "gate", "t": "oak"}, "objects": OBJECTS, **params.pop("iso", {})}
    return Stage.Params.model_validate({"iso": iso, **params})


def test_fog_and_wind_on_an_iso_place() -> None:
    assert stage_params(fog=0.7).fog.density == 0.7
    assert stage_params(wind="windy", fog={"density": 0.4, "drift": 2}).fog.drift == 2
    room = {"place": "indoor", "map": "#####\n#...#\n#.s.#", "spots": {"s": "middle"}, "objects": []}
    with pytest.raises(ValidationError, match="there is no fog inside an indoor place"):
        stage_params(iso=room, fog=True)
    with pytest.raises(ValidationError, match="there is no wind inside an indoor place"):
        stage_params(iso=room, wind=0.5)
    from vidgen.config import validation_problems
    from vidgen.scenes.stage import Stage

    with pytest.raises(ValidationError) as typo:
        stage_params(fog={"densty": 0.5})
    assert "did you mean 'density'" in str(validation_problems(typo.value, (), Stage.Params)[0])


def test_puddles_lying_from_the_start() -> None:
    assert settle_problem("rain", ParticleSettings(puddles=True, settled=12)) is None
    assert settle_problem("rain", ParticleSettings(settled=12))[1].startswith("settled is for rain with puddles")
    assert "add settle: true" in settle_problem("snow", ParticleSettings(settled=12))[1]


def test_no_wind_action_inside(make_project) -> None:
    room = {"place": "indoor", "map": "#####\n#...#\n#.s.#", "spots": {"s": "middle"}, "objects": []}
    params = {"idle": False, "iso": room, "characters": [{"name": "pip", "at": "middle"}]}
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": [{"text": "A draught.", "actions": [{"wind": "gale"}]}]}]
    found = problems(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), "home")
    assert any("no wind inside an indoor place" in text for _, text in found), found


def test_weather_validates(make_project) -> None:
    beats = [{"text": "A wet and windy night in the square.", "actions": [{"wind": "gale", "run_time": 1}]}]
    project = weather_project(make_project, beats, light="night", wind="breeze", fog=0.5,
                              particles=[{"kind": "rain", "puddles": True, "settled": 12}])
    assert problems(project, "home") == []


# ----- a tiny render ------------------------------------------------------------------------------------------


@pytest.mark.render
def test_rain_fog_and_wind_on_a_place_at_night(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    beats = [{"text": "Rain and wind on the square tonight.", "actions": [{"wind": -1, "run_time": 1}]},
             {"text": "The lamps shine in the puddles."}]
    project = weather_project(make_project, beats, light="night", wind="windy", fog=0.6,
                              particles=[{"kind": "rain", "puddles": True, "settled": 12, "seed": 2}])
    scene, frames = frames_of(project, tmp_path / "weather", monkeypatch)
    assert set(scene.iso_swayers) == {"tree", "balloon_bunch"}   # the lamp and the house stay in the pictures
    swayer = scene.iso_swayers["tree"][0]
    assert swayer in scene.mobjects and swayer.degrees < 0   # the gale blows to the left at the end
    assert not any(j == scene.iso_scenery.index["tree"] for j, _ in scene.iso_scenery.base()[1])
    fog = scene.fog
    assert fog is not None and all(band in scene.mobjects for band in fog.bands)
    order = [scene.mobjects.index(band) for band in fog.bands]
    assert order == sorted(order)   # back to front
    reflections = [thing for thing in scene.story_things if type(thing).__name__ == "IsoReflections"]
    assert reflections and reflections[0].pairs and reflections[0] in scene.mobjects
    assert scene.mobjects.index(reflections[0]) == scene.mobjects.index(scene.puddles[0]) + 1
    shown = [piece for _, _, _, piece in reflections[0].pairs if len(piece.points)]
    assert shown and all(piece.get_fill_opacity() > 0.5 for piece in shown)   # night: they shine
    assert len(frames) > 10 and max(np.abs(b.astype(int) - a.astype(int)).max() for a, b in zip(frames[-6:], frames[-5:])) > 0
