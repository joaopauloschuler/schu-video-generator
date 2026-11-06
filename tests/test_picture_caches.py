"""Graded pictures and resized tiles kept between frames (DESIGN.md §109): a lit iso frame draws
the same as without them; logic without rendering, and one small render."""

from __future__ import annotations

import gc
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST
from vidgen import extensions, registry
from vidgen.cartoon import iso_pictures, shading
from vidgen.cartoon.iso_pictures import TileParts
from vidgen.cartoon.lighting import grade_pixels, light_grade
from vidgen.cartoon.shading import GradedPictures, pixels_digest
from vidgen.project import Project
from vidgen.world.iso_view import Box3, iso_point


def _picture(seed: int = 1, size: int = 24) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, (size, size, 4), dtype=np.uint8)


class _Picture:
    """A stand-in for a picture mobject: what the caches keep values for."""


def test_a_picture_is_graded_again_only_when_its_pixels_or_the_grade_change() -> None:
    pictures, pixels, owner = GradedPictures(), _picture(), _Picture()
    night, blue = light_grade("night"), light_grade("blue_hour")
    first = pictures.graded(owner, pixels, blue)
    assert np.array_equal(first, grade_pixels(pixels, blue)) and not first.flags.writeable
    assert pictures.graded(owner, pixels, blue) is first   # unchanged: the kept one
    pixels[3, 4, 0] ^= 0xFF                             # changed in place: graded again
    again = pictures.graded(owner, pixels, blue)
    assert again is not first and np.array_equal(again, grade_pixels(pixels, blue))
    assert np.array_equal(pictures.graded(owner, pixels, night), grade_pixels(pixels, night))
    assert pictures.used == pixels.nbytes
    del owner
    gc.collect()
    assert pictures.used == 0   # gone with its picture


def test_past_its_budget_nothing_new_is_kept() -> None:
    pictures, pixels, owner = GradedPictures(budget=0), _picture(), _Picture()
    blue = light_grade("blue_hour")
    assert pictures.graded(owner, pixels, blue) is not pictures.graded(owner, pixels, blue) and pictures.used == 0
    assert TileParts(budget=0).used == 0


def test_fingerprints_tell_changed_pixels() -> None:
    pixels = _picture()
    digest = pixels_digest(pixels)
    assert pixels_digest(pixels.copy()) == digest
    pixels[0, 0, 3] ^= 1
    assert pixels_digest(pixels) != digest
    assert pixels_digest(pixels[:, :12]) != pixels_digest(pixels)   # a view, other shape


def test_a_tile_is_resized_again_when_its_place_size_or_pixels_change() -> None:
    parts, pixels, owner, other = TileParts(), _picture(), _Picture(), _Picture()
    box = (0.0, 0.0, 24.0, 24.0)
    first = parts.part(owner, pixels, (48, 48), box)
    assert np.array_equal(np.asarray(first), np.asarray(Image.fromarray(pixels, "RGBA").resize((48, 48), Image.Resampling.BILINEAR, box=box)))
    assert parts.part(owner, pixels, (48, 48), box) is first
    assert parts.part(owner, pixels, (47, 48), box) is not first
    kept = parts.part(owner, pixels, (48, 48), box)
    pixels[5, 5] ^= 0xFF
    assert parts.part(owner, pixels, (48, 48), box) is not kept
    frozen = pixels.copy()
    frozen.flags.writeable = False                     # a graded picture: trusted by identity
    trusted = parts.part(other, frozen, (48, 48), box)
    assert parts.part(other, frozen, (48, 48), box) is trusted
    pictures, blue = GradedPictures(), light_grade("blue_hour")   # graded as it is drawn, only when it changed
    lit = parts.part(owner, pixels, (48, 48), box, (pictures, blue))
    expected = Image.fromarray(grade_pixels(pixels, blue), "RGBA").resize((48, 48), Image.Resampling.BILINEAR, box=box)
    assert np.array_equal(np.asarray(lit), np.asarray(expected)) and pictures.used == pixels.nbytes
    assert parts.part(owner, pixels, (48, 48), box, (pictures, blue)) is lit
    assert parts.part(owner, pixels, (48, 48), box, (pictures, light_grade("night"))) is not lit


def test_a_picture_lets_its_oldest_unshown_tiles_go() -> None:
    tiles = iso_pictures.IsoTiles.__new__(iso_pictures.IsoTiles)
    made = [_Picture() for _ in range(40)]
    tiles._tiles = {(0, (k, 0), "picture"): m for k, m in enumerate(made)}
    tiles._snow_sources, tiles._snow_shown = {}, {}
    tiles._forget_old({id(made[-1]), id(made[0])})
    limit = iso_pictures.TILES_KEPT * 2 + iso_pictures.TILES_SPARE
    assert len(tiles._tiles) == limit
    kept = list(tiles._tiles.values())
    assert made[0] in kept and made[-1] in kept and made[1] not in kept   # the shown stay, the oldest others go
    tiles._forget_levels(1)
    assert tiles._tiles == {}


def test_a_box_works_out_its_picture_once() -> None:
    box = Box3(0, 0, 0, 2, 1, 3)
    bounds = box.picture_bounds()
    points = [iso_point(*corner) for corner in box.corners()]
    assert bounds == (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points))
    assert box.picture_bounds() is bounds and box == Box3(0, 0, 0, 2, 1, 3)


MAP = "\n".join(["#" * 14] + ["#" + "." * 12 + "#"] * 3 + ["#..a.........#"] + ["#" + "." * 12 + "#"] * 9)


@pytest.mark.render
def test_a_lit_place_draws_the_same_with_and_without_the_caches(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    objects = [{"object": "ray_lamp", "at": {"column": 6, "row": 4}, "on": True}, {"object": "tube_computer", "at": {"column": 3, "row": 2}, "on": True},
               {"object": "tv_console", "at": {"column": 8, "row": 2}, "kind": "wave", "on": True}]
    params = {"light": "blue_hour", "fill_light": 0.6, "character_size": "large", "characters": [{"name": "pip", "at": "desk"}],
              "iso": {"place": "indoor", "map": MAP, "spots": {"a": "desk"}, "wide": "fixed", "show_walls": True, "objects": objects}}
    beats = [{"text": "A room at blue hour.", "actions": [{"action": "pan", "to": "desk", "run_time": 0.6, "at": 0.3}]}]
    config = minimal_config(characters=CAST, scenes=[{"id": "home", "type": "stage", "params": params, "beats": beats}])
    _, kept = frames_of(Project.load(make_project(config)), tmp_path / "kept", monkeypatch)
    monkeypatch.setattr(shading, "GRADED_CACHE_BYTES", 0)
    monkeypatch.setattr(iso_pictures, "TILE_PARTS_BYTES", 0)
    _, plain = frames_of(Project.load(make_project(config)), tmp_path / "plain", monkeypatch)
    assert len(kept) == len(plain) > 3
    assert max(int(np.abs(a.astype(int) - b.astype(int)).max()) for a, b in zip(kept, plain)) == 0


@pytest.mark.render
def test_a_zoom_frames_an_object_and_moving_parts_stay_in_front(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    # the TV stands in front of the water cooler; both have moving parts, the TV listed first
    objects = [{"object": "tv_console", "at": {"column": 10, "row": 3}, "kind": "face", "on": True, "name": "screen"},
               {"object": "water_cooler", "at": {"column": 9, "row": 2}, "on": True}]
    params = {"character_size": "large", "characters": [{"name": "pip", "at": "desk"}],
              "iso": {"place": "indoor", "map": MAP, "spots": {"a": "desk"}, "wide": "fixed", "objects": objects}}
    beats = [{"text": "The screen comes on.", "actions": [{"zoom": "screen", "scale": 2, "hold": True, "at": 0.1, "run_time": 0.3}]}]
    config = minimal_config(characters=CAST, scenes=[{"id": "home", "type": "stage", "params": params, "beats": beats}])
    scene, _ = frames_of(Project.load(make_project(config)), tmp_path / "zoom", monkeypatch)
    left, bottom, right, top = scene.target_box(type("T", (), {"name": "screen"})())
    centre = scene.camera.frame.get_center()
    assert abs(centre[0] - (left + right) / 2) < 1e-6 and abs(centre[1] - (bottom + top) / 2) < 1e-6
    assert scene.target_box(type("T", (), {"name": "pip"})()) is None
    order = [k for _, k, _ in scene._iso_gadget_places]
    assert len(order) == 2 and order == sorted(order)   # back to front: the cooler's cover never hides the screen
    groups = [m for top in scene.mobjects for m in top.get_family() if isinstance(m, iso_pictures.IsoTiles) and m._tiles]
    assert groups and all(len({key[0] for key in g._tiles}) == 1 for g in groups)   # zoomed in: one level's tiles kept
