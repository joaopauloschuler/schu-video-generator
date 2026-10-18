"""Step 150: platform worlds — the world model, ASCII levels and their checks, and a level drawn
on a ``stage`` (tiles drawn once into pictures, the background moving behind by parallax)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen.cartoon.level_drawing import CHUNK_COLUMNS, LevelColors, draw_columns, drawn_rows, level_shapes
from vidgen.cartoon.level_stage import LEVEL_SIZE, level_fit_problems, level_frame, level_layout
from vidgen.cartoon.stage import StageItem
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.world import AIR, CHARACTER_TILES, CLOUD, GROUND, LADDER, PLATFORM, Placing, Run, parse_level, place_bodies

FW, FH = 8 * 16 / 9, 8.0
MAP = """
.......~~~......
..a.......====|.
......b.......|.
###..#######.###
####.#######.###
"""


# ----- the world model (no manim) ----------------------------------------------------------------


def test_parse_reads_rows_from_the_bottom() -> None:
    level = parse_level(MAP, {"a": "start"})
    assert (level.columns, level.rows, level.used_rows()) == (16, 5, 5)
    assert level.tile(0, 0) == GROUND and level.tile(3, 1) == AIR and level.tile(4, 0) == AIR
    assert level.tile(7, 4) == CLOUD and level.tile(10, 3) == PLATFORM and level.tile(14, 2) == LADDER
    assert level.tile(-1, 0) == AIR and level.tile(0, 9) == AIR   # outside: air
    start, b = level.spots
    assert (start.name, start.letter, start.column, start.row, start.x, start.y) == ("start", "a", 2, 3, 2.5, 2.0)
    assert (b.name, b.x, b.y) == ("b", 6.5, 2.0)   # a letter without a name is named by itself
    assert level.spot("start") is start and level.spot_names() == ["start", "b"]
    with pytest.raises(VidgenError, match="no spot 'home' \\(spots: start, b\\)"):
        level.spot("home")


def test_surfaces_runs_and_padding() -> None:
    level = parse_level("....=\n...\n#####\n")   # a short row is padded with air
    assert level.columns == 5 and level.tile(4, 1) == AIR
    assert level.top_surface(4) == 3.0 and level.top_surface(0) == 1.0
    assert level.surface_below(4, 2) == 1.0 and level.surface_below(4, 0) is None
    assert level.runs(GROUND) == [Run(GROUND, 0, 0, 4)] and level.runs(PLATFORM) == [Run(PLATFORM, 2, 4, 4)]
    assert level.column_at(-0.5) == 0 and level.column_at(5.0) == 4 and level.column_at(2.7) == 2
    gap = parse_level("a....\n#...#")
    assert gap.top_surface(2) is None


@pytest.mark.parametrize(
    "text,spots,message",
    [
        ("", {}, "the map is empty"),
        ("....\n....", {}, "nothing to stand on"),
        ("..?.\n####", {}, "map row 1, column 3: unknown symbol '\\?'"),
        ("a.\n#%", {}, "map row 2, column 2: unknown symbol '%'"),   # * is a star since Step 152
        ("a..a\n####", {}, "map row 1, column 4: spot 'a' is already at row 1, column 1"),
        ("..a.\n##..", {}, "map row 1, column 3: spot 'a' has nothing below it to stand on"),
        ("a...\n####", {"b": "home"}, "spots: letter 'b' is not on the map"),
        ("a..b\n####", {"a": "home", "b": "home"}, "'home' names both 'a' and 'b'"),
        ("#" * 401, {}, "401 columns wide; at most 400"),
        ("\n".join(["#"] * 41), {}, "41 rows; at most 40"),
    ],
)
def test_bad_maps_name_the_row_and_column(text: str, spots: dict[str, str], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        parse_level(text, spots)


def test_bodies_stand_on_spots_and_tiles() -> None:
    level = parse_level(MAP, {"a": "start"})
    world = place_bodies(level, [Placing("pip", "character", spot="start"), Placing("kit", "character", x=10.5, scale=1.5),
                                 Placing("box", "prop", x=14.2, scale=0.25)])
    assert world.body("pip").x == 2.5 and world.body("pip").y == 2.0 and world.body("pip").height == CHARACTER_TILES
    assert world.body("kit").y == 4.0 and world.body("kit").height == 1.5 * CHARACTER_TILES   # on the platform: the highest tile
    assert world.body("box").y == 2.0   # a ladder is not stood on: the ground under it
    with pytest.raises(VidgenError, match="nothing named 'zed'"):
        world.body("zed")
    with pytest.raises(VidgenError, match="'pip' would stand over a gap \\(map column 5"):
        place_bodies(level, [Placing("pip", "character", x=4.5)])
    with pytest.raises(VidgenError, match="outside the level"):
        place_bodies(level, [Placing("pip", "character", x=17.0)])


def test_world_and_rules_modules_do_not_import_manim() -> None:
    code = ("import sys, vidgen.world, vidgen.world.moves, vidgen.world.story_props, vidgen.cartoon.level_stage, "
            "vidgen.cartoon.level_drawing, vidgen.camera, vidgen.cartoon.foley; print('manim' in sys.modules)")   # the camera and foley too (Step 155)
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout
    assert out.strip() == "False"


# ----- the level on a stage: geometry and drawing (no manim) -----------------------------------------


def test_level_frame_and_layout() -> None:
    level = parse_level("." * 20 + "\n" + "..a" + "." * 17 + "\n" + "#" * 20, {"a": "start"})
    frame = level_frame(level, LEVEL_SIZE, FW, FH)
    assert frame.tile == pytest.approx(LEVEL_SIZE * FH / CHARACTER_TILES) == pytest.approx(1.0)
    assert frame.stage_width == pytest.approx(20.0) and frame.point(0, 0) == pytest.approx((-10.0, -4.0))
    assert frame.x_fraction(frame.world_x(0.3)) == pytest.approx(0.3)
    items = [StageItem("pip", "character", "start"), StageItem("lamp", "prop", 0.9, scale=0.5, lift=0.1)]
    pip, lamp = level_layout(level, items, size=LEVEL_SIZE, frame_width=FW, frame_height=FH)
    assert pip.feet == pytest.approx((-10.0 + 2.5, -3.0)) and pip.height == pytest.approx(2.0) and pip.x_fraction == pytest.approx(2.5 / 20)
    assert lamp.feet == pytest.approx((-10.0 + 18.0, -3.0 + 0.1 * FH)) and lamp.height == pytest.approx(1.0)


def test_level_must_fit_the_frame() -> None:
    narrow = parse_level("#" * 10)
    assert level_fit_problems(narrow, LEVEL_SIZE, FW, FH) == [
        "the map is 10 columns wide, narrower than the frame (14.2 columns at size 0.25); add columns or make the characters "
        "larger (character_size: large, or a larger size)"]
    tall = parse_level("\n".join(["#" + "." * 19] * 9 + ["#" * 20]))
    assert level_fit_problems(tall, LEVEL_SIZE, FW, FH) == []   # taller than the frame: the camera rises with its hero (Step 154)
    assert level_fit_problems(parse_level("." * 9 + "\n" + "#" * 9), LEVEL_SIZE, 4.5, 8.0) == []   # 9:16: 8 columns are enough


def test_tile_shapes() -> None:
    level = parse_level("....\n.#..\n##=~")
    shapes = level_shapes(level, LevelColors(grass="#00ff00"))
    grass = [s for s in shapes if s.fill == "#00ff00"]
    # grass on the two exposed tops: (0, 0) and (1, 1); not on (1, 0) under another ground tile
    tops = sorted({round(s.box[3], 3) for s in grass if s.kind == "rect"})
    assert tops == [pytest.approx(1 - 0.04), pytest.approx(2 - 0.04)]
    assert any(s.fill == LevelColors().platform for s in shapes) and any(s.fill == LevelColors().cloud for s in shapes)
    bold = level_shapes(level, outline=2.0)
    assert bold[0].box == shapes[0].box and len(bold) == len(shapes)


def test_chunks_join_without_a_seam() -> None:
    level = parse_level("...~~~~..==...|.\n.a............|.\n####..##########")
    shapes = level_shapes(level)
    rows = drawn_rows(level)
    whole = np.array(draw_columns(shapes, 0, 15, rows, 12))
    halves = np.hstack([np.array(draw_columns(shapes, 0, 7, rows, 12)), np.array(draw_columns(shapes, 8, 15, rows, 12))])
    assert whole.shape == (round(rows * 12), 16 * 12, 4) and np.array_equal(whole, halves)
    assert whole[-1, 4 * 12 + 6, 3] == 0 and whole[-1, 6, 3] == 255   # the gap is transparent, the ground opaque


# ----- the stage's params -------------------------------------------------------------------------


LEVEL = {"map": "....................\n..a.......b.........\n######..############", "spots": {"a": "start"}}


def test_stage_params_with_a_level() -> None:
    p = stage_params(level=LEVEL, characters=[{"name": "pip", "at": "start"}, {"name": "kit", "at": "b"}])
    assert p.size == LEVEL_SIZE and p.level.parsed().spot_names() == ["start", "b"]
    assert p.stage_marks()["start"] == pytest.approx(2.5 / 20) and p.stage_marks()["b"] == pytest.approx(10.5 / 20)
    assert stage_params(level=LEVEL, size=0.3).size == 0.3
    assert stage_params(size=0.3).level is None and stage_params().size == 0.45   # no level: unchanged
    placements = p.layout(frame_width=FW, frame_height=FH, stage_width=0.0)
    assert [pl.feet[1] for pl in placements] == pytest.approx([-3.0, -3.0])


@pytest.mark.parametrize(
    "params,message",
    [
        ({"level": {"map": "..@.\n####"}}, "map row 1, column 3: unknown symbol '@'"),
        ({"level": LEVEL, "width": 2}, "a level is the ground and sets the stage's width: remove width"),
        ({"level": LEVEL, "room": True}, "remove room"),
        ({"level": LEVEL, "water": True}, "remove water"),
        ({"level": LEVEL, "props": [{"prop": "tree", "at": "start", "depth": 0.5}]}, "props\\[0\\]: on a level everything stands on the tiles at depth 0"),
        ({"level": LEVEL, "characters": [{"name": "pip", "at": "start", "depth": 0.2}]}, "characters\\[0\\]: on a level"),
        ({"level": LEVEL, "characters": [{"name": "pip", "at": 0.35}]}, "'pip' would stand over a gap \\(map column 8"),
        ({"level": LEVEL, "marks": {"start": 0.4}}, "'start' is also one of the stage's marks"),
        ({"level": {"map": "a...\n####", "spots": {"a": "two words"}}}, "level.spots"),
    ],
)
def test_bad_level_params(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        stage_params(**params)


def level_project(make_project, params: dict[str, Any], beats: list[dict[str, Any]] | None = None) -> Project:
    scenes = [{"id": "hills", "type": "stage", "params": params, "beats": beats or [{"text": "Pip stands on the hill."}]}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


def test_validate_checks_the_level_fits_the_frame(make_project) -> None:
    from vidgen import registry

    project = level_project(make_project, {"level": {"map": "a.........\n##########"}})
    spec = project.scene("hills")
    cls = registry.get("stage").cls
    problems = cls.validate_project(cls.validate_params(spec.params), project)
    assert problems == ["level: the map is 10 columns wide, narrower than the frame (14.2 columns at size 0.25); "
                        "add columns or make the characters larger (character_size: large, or a larger size)"]


# ----- render -------------------------------------------------------------------------------------


@pytest.mark.render
def test_level_renders_on_a_stage(make_project, tmp_path: Path) -> None:
    from PIL import Image

    level = {
        "map": "\n".join([
            "......................~~~.......",
            "..a............b.....===....c...",
            "########..########...........###",
            "########..######################",
        ]),
        "spots": {"a": "start", "b": "hill", "c": "home"},
        "colors": {"grass": "accent"},
    }
    params = {"image": "assets/sky.png", "idle": False, "level": level, "camera_at": "start",
              "characters": [{"name": "pip", "at": "start"}, {"name": "kit", "at": "hill"}]}
    beats = [{"text": "Pip and Kit.", "actions": [{"action": "pan", "to": "home", "at": 0.2}]}]
    project = level_project(make_project, params, beats)
    (project.root / "assets").mkdir()
    Image.new("RGB", (64, 36), (120, 180, 230)).save(project.root / "assets" / "sky.png")
    scene, objects = render_with_layout(project, "hills", tmp_path / "media")
    frame = scene.params.level_frame(scene.frame_width, scene.frame_height)
    assert scene.stage_width == pytest.approx(32 * frame.tile)
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    assert pip.feet()[:2] == pytest.approx(frame.point(2.5, 2.0), abs=1e-6)   # on the ground's top
    assert kit.feet()[:2] == pytest.approx(frame.point(15.5, 2.0), abs=1e-6)
    assert scene.grounds["pip"] == pytest.approx(frame.point(0, 2.0)[1])   # its shadow lies on the tile
    named = {obj["name"]: obj for obj in objects if obj["name"]}
    chunks = [o for o in objects if (o["name"] or "").startswith("level_")]
    assert chunks and all(named["background"]["order"] < o["order"] < named["pip"]["order"] for o in chunks)
    assert "ground" not in named   # the tiles are the ground
    tiles = scene._backdrop[-1]
    assert len(tiles.chunks) == 4 and all(type(c).__name__ == "ImageMobject" for c in tiles.chunks)
    # the camera panned to the right end: only the chunks in view are drawn
    view = scene.camera.frame
    assert view.get_right()[0] == pytest.approx(scene.stage_width / 2)
    assert tiles.submobjects == [c for c in tiles.chunks if c.get_right()[0] >= view.get_left()[0]] and len(tiles.submobjects) < 4
    # the background picture moved by its parallax factor, not with the stage
    picture = next(m for m in scene._backdrop if getattr(m, "name", "") == "background")
    assert picture.get_center()[0] - view.get_center()[0] == pytest.approx(-0.2 * view.get_center()[0], abs=1e-6)
