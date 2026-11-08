"""Guide passes of the ``3d`` scene type (Step 301, DESIGN.md §114.14): which passes are asked for
(YAML and CLI), their descriptions (same camera and timing, one depth range for the shot, a mask
colour per object), the files beside the clip; tiny renders through Playwright's Chromium
(skipped when it is missing): the pixels of each pass and the render pipeline asking for them."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest

from vidgen.config import FormatConfig, ThemeConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.theme import Theme
from vidgen.three_d import browser
from vidgen.three_d.description import plan_world, scene_description
from vidgen.three_d.motion import ObjectChange
from vidgen.three_d.passes import (
    FLOOR_MASK, GUIDE_PASSES, MASK_PALETTE, depth_range, guide_pass, make_guide_passes, mask_colors, mask_table, parse_passes, pass_files,
)
from vidgen.three_d.spec import Scene3DParams

THEME = Theme.for_format(ThemeConfig(), FormatConfig())
FPS = 10

SCENE = {
    "floor": True,
    "background": "#203040",
    "camera": {"position": [0, 2, 8], "look_at": [0, 0.5, 0]},
    "objects": [
        {"id": "near", "shape": "box", "position": [-1.2, 0.5, 2], "color": "#e04040"},
        {"id": "far", "shape": "sphere", "position": [1.5, 0.5, -3], "color": "#40e040"},
        {"id": "ana", "shape": "standin", "name": "Ana", "position": [0, 0.8, 0]},
        {"id": "cart", "shape": "group", "position": [3, 0, 0]},
        {"id": "wheel", "parent": "cart", "shape": "cylinder", "size": [0.5, 0.2, 0.5], "position": [0, 0.25, 0]},
        {"id": "tag", "shape": "label", "text": "Tag", "position": [0, 2.2, 0]},
    ],
}


def params(**raw: Any) -> Scene3DParams:
    return Scene3DParams.model_validate(raw)


def describe(p: Scene3DParams, *changes: ObjectChange, width: int = 160, height: int = 90, frames: int = 4) -> tuple[dict[str, Any], Any]:
    d = scene_description(p, THEME, width=width, height=height, fps=FPS, frames=frames, beats=[], object_changes=list(changes))
    return d, plan_world(p, FPS, frames, list(changes))


# ----- which passes -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "passes"),
    [
        (None, ()), (False, ()), ("", ()), (True, GUIDE_PASSES), ("all", GUIDE_PASSES),
        ("mask,depth", ("depth", "mask")), (["outline"], ("outline",)), (["mask", "all"], GUIDE_PASSES),
    ],
)
def test_parse_passes(value: Any, passes: tuple[str, ...]) -> None:
    assert parse_passes(value) == passes


def test_unknown_pass_suggests_the_right_name() -> None:
    with pytest.raises(ValueError, match="--guide-passes: no guide pass 'dpeth'.*did you mean 'depth'"):
        parse_passes("dpeth,mask", "--guide-passes")


def test_yaml_switch_is_off_by_default_and_checked() -> None:
    from vidgen.scenes.scene_3d import Scene3D

    assert params().passes() == ()
    assert params(guide_passes=True).passes() == GUIDE_PASSES
    assert params(guide_passes=["mask", "depth"]).passes() == ("depth", "mask")
    with pytest.raises(VidgenError, match="did you mean 'outline'"):
        Scene3D.parse_params({"guide_passes": ["outlines"]}, "s", THEME)


def test_cli_option_reaches_the_worker() -> None:
    from vidgen.cli import _guide_passes, build_parser
    from vidgen.render.worker import build_parser as worker_parser

    parse = build_parser().parse_args
    assert _guide_passes(parse(["render"])) == ()
    assert _guide_passes(parse(["render", "--guide-passes"])) == GUIDE_PASSES
    assert _guide_passes(parse(["render", "--guide-passes", "outline,mask"])) == ("outline", "mask")
    with pytest.raises(VidgenError, match="did you mean 'mask'"):
        _guide_passes(parse(["render", "--guide-passes=mask,masc"]))
    assert worker_parser().parse_args(["p", "s", "--guide-passes", "depth,mask"]).guide_passes == "depth,mask"


# ----- descriptions -----------------------------------------------------------------------------


def test_a_pass_keeps_camera_timing_and_objects() -> None:
    p = params(**SCENE)
    d, world = describe(p, ObjectChange("move", "near", 0.0, 0.3, point=(-1.2, 0.5, 4.0)))
    for mode in GUIDE_PASSES:
        pass_d = guide_pass(d, world, mode)
        assert pass_d["draw_mode"] == mode and d["draw_mode"] == "normal"
        same = {k: v for k, v in pass_d.items() if k not in ("draw_mode", "depth_range", "mask_colors")}
        assert same == {k: v for k, v in d.items() if k != "draw_mode"}   # camera, timeline, frames, objects
    assert scene_description(p, THEME, width=160, height=90, fps=FPS, frames=4, beats=[],
                             object_changes=[ObjectChange("move", "near", 0.0, 0.3, point=(-1.2, 0.5, 4.0))],
                             draw_mode="mask") == guide_pass(d, world, "mask")
    with pytest.raises(ValueError, match="did you mean 'depth'"):
        guide_pass(d, world, "deep")


def test_mask_colours_are_unique_and_skip_groups_and_labels() -> None:
    many = params(objects=[{"id": f"o{k}", "position": [k, 0, 0]} for k in range(60)] + [{"id": "g", "shape": "group"}])
    d, _ = describe(many)
    colors = mask_colors(d)
    assert list(colors) == [f"o{k}" for k in range(60)]   # more objects than the palette has colours
    assert len(set(colors.values())) == 60 and "#000000" not in colors.values() and FLOOR_MASK not in colors.values()
    d, _ = describe(params(**SCENE))
    table = mask_table({**d, "mask_colors": mask_colors(d)}, "plaza")
    assert set(table["colors"]) == {"floor", "near", "far", "ana", "wheel"}   # no group, no label
    assert table["colors"]["floor"] == FLOOR_MASK == "#404040"   # the floor a neutral dark grey
    assert table["background"] == "#000000" and table["names"] == {"Ana": table["colors"]["ana"]}
    assert next(o for o in table["objects"] if o["id"] == "wheel")["parent"] == "cart"


def test_mask_colours_come_from_the_ids_and_stay_when_objects_are_added() -> None:
    from vidgen.three_d import passes

    d, _ = describe(params(**SCENE))
    before = mask_colors(d)
    assert set(before.values()) - {FLOOR_MASK} <= set(MASK_PALETTE)
    home = {MASK_PALETTE[passes._id_hash(i) % len(MASK_PALETTE)] for i in before}
    fresh = [f"new{k}" for k in range(100) if MASK_PALETTE[passes._id_hash(f"new{k}") % len(MASK_PALETTE)] not in set(before.values()) | home][:2]
    added = {**SCENE, "objects": [{"id": fresh[0]}, *SCENE["objects"][1:], SCENE["objects"][0], {"id": fresh[1], "shape": "cone"}]}
    after = mask_colors(describe(params(**added))[0])
    assert {k: after[k] for k in before} == before   # an object added before, one after, the rest reordered
    assert len(set(after.values())) == len(after)
    a, b = (mask_colors(describe(params(objects=[{"id": i}]))[0])[i] for i in ("a", "b"))
    assert a != b   # different ids, different colours (from the id, not the place in the list)


def test_mask_colour_clash_goes_to_the_id_later_in_the_alphabet() -> None:
    from vidgen.three_d import passes

    size = len(MASK_PALETTE)
    other = next(f"z{k}" for k in range(500) if passes._id_hash(f"z{k}") % size == passes._id_hash("a") % size)
    alone = mask_colors(describe(params(objects=[{"id": "a"}]))[0])["a"]
    for order in (["a", other], [other, "a"]):
        colors = mask_colors(describe(params(objects=[{"id": i} for i in order]))[0])
        assert colors["a"] == alone and colors[other] != alone and colors[other] in MASK_PALETTE


def test_depth_range_holds_the_whole_shot() -> None:
    p = params(objects=[{"id": "ball", "shape": "sphere", "position": [0, 0, 0]}], camera={"position": [0, 0, 5], "look_at": [0, 0, 0]})
    d, world = describe(p, frames=20)
    near, far = depth_range(d, world)
    assert 4.0 < near < 4.5 and 5.5 < far < 6.0   # the sphere from 4.5 to 5.5, widened a little
    moving, world = describe(p, ObjectChange("move", "ball", 0.5, 1.5, point=(0.0, 0.0, -10.0)), frames=20)
    near, far = guide_pass(moving, world, "depth")["depth_range"]
    assert near < 4.5 and far > 15.5   # one range covering where the ball goes, not one per frame
    alone, world = describe(params(), frames=2)
    assert depth_range(alone, world)[0] == alone["camera"]["near"]


def test_depth_range_fits_the_objects_not_the_floor() -> None:
    p = params(floor={"size": 200}, camera={"position": [0, 2, 6], "look_at": [0, 0.5, 0]},
               objects=[{"id": "box", "position": [0, 0.5, 0]}, {"id": "ball", "shape": "sphere", "position": [1, 0.5, -2]}])
    d, world = describe(p, frames=1)
    near, far = depth_range(d, world)
    assert 4.5 < near < 6 and 7.5 < far < 9.5   # the box and the ball, not the floor 100 units back


def test_depth_range_of_a_long_thin_object_uses_its_box() -> None:
    p = params(camera={"position": [0, 0, 5], "look_at": [0, 0, 0]},
               objects=[{"id": "rod", "shape": "arrow", "position": [-2, 0, 0], "to": [2, 0, 0]}])
    near, far = depth_range(*describe(p, frames=1))
    assert 4.8 < near < 5 < far < 5.2   # across the view: not its 4-unit sphere


def test_depth_range_of_a_floor_alone_counts_only_what_is_in_view() -> None:
    p = params(floor={"size": 400}, camera={"position": [0, 2, 0], "look_at": [0, 2, -10], "fov": 30})
    d, world = describe(p, frames=1)
    near, far = depth_range(d, world)
    assert near > 2 and far > 150   # the floor below the frame (under the camera) is not in view


def test_depth_range_can_be_given() -> None:
    p = params(depth_range=[1, 20], objects=[{"id": "box"}])
    d = scene_description(p, THEME, width=160, height=90, fps=FPS, frames=2, beats=[], draw_mode="depth")
    assert d["depth_range"] == [1.0, 20.0]
    for bad in ([5, 2], [-1, 3], [2, 2]):
        with pytest.raises(ValueError, match="depth_range: .* must be \\[near, far\\]"):
            params(depth_range=bad)


def test_pass_files_sit_beside_the_clip(tmp_path: Path) -> None:
    assert [f.name for f in pass_files(tmp_path, "plaza", ("depth", "mask"))] == ["plaza.depth.mkv", "plaza.mask.mkv", "plaza.mask-colors.json"]
    assert [f.name for f in pass_files(tmp_path, "plaza", ("outline",))] == ["plaza.outline.mkv"]


# ----- renders (Chromium) -----------------------------------------------------------------------


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    try:
        with browser.PageRenderer(describe(params(), width=16, height=16, frames=1)[0]) as page:
            page.frame(0)
    except VidgenError as exc:
        pytest.skip(f"Chromium for Playwright is not available: {exc}")


def _frames(path: Path) -> list[np.ndarray]:
    with av.open(str(path)) as container:
        return [f.to_ndarray(format="rgb24") for f in container.decode(video=0)]


def _hex(pixels: np.ndarray) -> set[str]:
    return {"#%02x%02x%02x" % tuple(int(c) for c in rgb) for rgb in np.unique(pixels.reshape(-1, 3), axis=0)}


@pytest.mark.render
def test_passes_draw_depth_outline_and_mask(tmp_path: Path) -> None:
    _chromium_or_skip()
    d, world = describe(params(**SCENE), width=192, height=108, frames=3)
    files = make_guide_passes(tmp_path, "plaza", d, world, GUIDE_PASSES)
    assert all(f.is_file() for f in files)
    depth, outline, mask = (_frames(tmp_path / f"plaza.{m}.mkv") for m in GUIDE_PASSES)
    assert len(depth) == len(outline) == len(mask) == 3

    table = json.loads((tmp_path / "plaza.mask-colors.json").read_text(encoding="utf-8"))
    seen = _hex(mask[1])
    assert seen <= set(table["colors"].values()) | {"#000000"}   # flat: no light, no blending, no label
    assert {table["colors"][i] for i in ("near", "far", "ana", "floor")} <= seen

    def where(obj: str) -> np.ndarray:
        rgb = [int(table["colors"][obj][i : i + 2], 16) for i in (1, 3, 5)]
        return np.all(mask[1] == rgb, axis=2)

    grey = depth[1]
    assert np.array_equal(grey[..., 0], grey[..., 1]) and np.array_equal(grey[..., 0], grey[..., 2])
    assert grey[0, 0, 0] == 0   # the background (sky) is black
    assert grey[where("near")][:, 0].mean() > grey[where("far")][:, 0].mean() + 20   # near is lighter
    assert grey[where("floor")][:, 0].min() >= 35   # the floor far back is clamped to a grey, not black

    lines = outline[1]
    assert _hex(lines) == {"#000000", "#ffffff"}
    assert 0.005 < (lines[..., 0] == 255).mean() < 0.2   # white edges on black
    edge_of_near = where("near") & ~np.roll(where("near"), 1, axis=1)
    assert (lines[..., 0][np.roll(edge_of_near, -1, axis=1)] == 255).mean() > 0.5   # the box's silhouette is drawn

    stamp = os.stat(tmp_path / "plaza.depth.mkv").st_mtime_ns
    make_guide_passes(tmp_path, "plaza", d, world, ("depth",))
    assert os.stat(tmp_path / "plaza.depth.mkv").st_mtime_ns == stamp   # cached like the clip


@pytest.mark.render
@pytest.mark.slow
def test_render_asks_for_passes_by_yaml_and_cli(make_project) -> None:
    _chromium_or_skip()
    from vidgen.render.pipeline import render_project

    root = make_project({
        "title": "3D",
        "format": {"width": 160, "height": 90, "fps": 5},
        "preview": {"width": 160, "height": 90, "fps": 5},
        "overlays": [{"type": "captions"}],
        "scenes": [{
            "id": "cube", "type": "3d",
            "params": {"title": "Box", "guide_passes": ["mask"],
                       "objects": [{"id": "crate", "color": "#e04040", "size": 1.6, "spin": [0, 30, 0]}]},
            "beats": [{"id": "b1", "text": "A box turns slowly in the middle."}],
        }],
    })
    folder = root / "build" / "preview" / "three_d"
    result = render_project(Project.load(root), preview=True)
    assert [f.name for f in result.guide_passes["cube"]] == ["cube.mask.mkv", "cube.mask-colors.json"]
    assert not (folder / "cube.depth.mkv").exists()   # off unless asked for
    clip, mask = _frames(folder / "cube.mkv"), _frames(folder / "cube.mask.mkv")
    assert len(clip) == len(mask)
    crate = json.loads((folder / "cube.mask-colors.json").read_text(encoding="utf-8"))["colors"]["crate"]
    assert _hex(mask[len(mask) // 2]) == {"#000000", crate}   # no title, no caption: only the 3D shape

    stamp = os.stat(folder / "cube.mkv").st_mtime_ns
    again = render_project(Project.load(root), preview=True, guide_passes=("depth",))
    assert again.rendered == ["cube"]   # its render had no depth pass
    assert (folder / "cube.depth.mkv").is_file() and os.stat(folder / "cube.mkv").st_mtime_ns == stamp
    assert len(_frames(folder / "cube.depth.mkv")) == len(clip)
    assert render_project(Project.load(root), preview=True, guide_passes=("depth",)).rendered == []
