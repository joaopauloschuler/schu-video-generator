"""Guide passes of a ``3d`` scene (DESIGN.md §114.14): the same frames drawn three more ways, for
tools that read a scene's shape and layout rather than its look (later: video-to-video).

- ``depth``: grey by distance from the camera, near white and far dark, over one range for the
  whole shot (it does not flicker as things move);
- ``outline``: black edges on white, like a line drawing;
- ``mask``: every object in one flat colour of its own on black, with a table object id ->
  colour (``<scene>.mask-colors.json``).

A pass is the scene description with another ``draw_mode`` (and its range or colours), so it
shares the camera, timing and frame count by construction; it is drawn and cached like the
scene's clip, beside it: ``<render_dir>/three_d/<scene>.<pass>.mkv`` + ``.json``. Labels and name
tags are left out (only the 3D shapes), as are the title, captions and overlays (Manim draws
those over the clip, never into it).
"""

from __future__ import annotations

import colorsys
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from vidgen.cellworld.model import did_you_mean
from vidgen.fileio import write_text_atomic
from vidgen.three_d.clip import make_3d_clip
from vidgen.three_d.framing import SHOWN, camera_at
from vidgen.three_d.world import World

#: The guide passes, in the order they are drawn.
GUIDE_PASSES: tuple[str, ...] = ("depth", "outline", "mask")
#: What ``guide_passes: true`` or ``--guide-passes`` alone mean.
ALL_PASSES = "all"
#: Shapes a pass does not draw: groups draw nothing, labels are text, not shape.
NOT_DRAWN: frozenset[str] = frozenset({"group", "label"})
#: The mask's background (no object).
MASK_BACKGROUND = "#000000"
#: The depth range is widened by this share of its span at each end: the nearest point is not clipped to white, the farthest stays a dark grey apart
#: from the black background.
DEPTH_PAD = 0.05
#: At most this many frames are looked at for the depth range (evenly spread, first and last).
DEPTH_SAMPLES = 120
#: Points per side of the grid a plane is sampled with for the depth range.
PLANE_GRID = 17


def parse_passes(value: Any, where: str = "guide_passes") -> tuple[str, ...]:
    """The passes asked for by ``value``: ``True`` / ``"all"`` (all three), ``False`` / ``None`` /
    empty (none), a name, a comma list (``"depth,mask"``) or a list of names; in
    :data:`GUIDE_PASSES` order. ``ValueError`` (with did-you-mean) for an unknown name."""
    if value is None or value is False:
        return ()
    if value is True:
        return GUIDE_PASSES
    names = [n.strip() for n in value.split(",")] if isinstance(value, str) else [str(n).strip() for n in value]
    names = [n for n in names if n]
    if ALL_PASSES in names:
        return GUIDE_PASSES
    for name in names:
        if name not in GUIDE_PASSES:
            raise ValueError(f"{where}: no guide pass {name!r} (passes: {', '.join(GUIDE_PASSES)}, or {ALL_PASSES}){did_you_mean(name, GUIDE_PASSES)}")
    return tuple(p for p in GUIDE_PASSES if p in names)


def mask_colors(description: dict[str, Any]) -> dict[str, str]:
    """A colour of its own for every drawn object of ``description`` (in its order; groups and
    labels have none): hues spread by the golden angle, two brightness levels, never black or
    the background."""
    out: dict[str, str] = {}
    taken = {MASK_BACKGROUND}
    k = 0
    for obj in description["objects"]:
        if obj["shape"] in NOT_DRAWN:
            continue
        while True:
            hue = (k * 0.618033988749895) % 1.0
            value = (1.0, 0.72)[(k // 3) % 2]
            r, g, b = colorsys.hsv_to_rgb(hue, 0.85, value)
            color = "#" + "".join(f"{round(c * 255):02x}" for c in (r, g, b))
            k += 1
            if color not in taken:
                break
        taken.add(color)
        out[obj["id"]] = color
    return out


def mask_table(description: dict[str, Any], scene_id: str) -> dict[str, Any]:
    """The mask's colour table: ``{scene, background, colors: {id: colour}, objects: [{id,
    shape, color, parent (+ name for a named stand-in)}], names: {stand-in name: colour}}``."""
    colors = description.get("mask_colors") or mask_colors(description)
    objects, names = [], {}
    for obj in description["objects"]:
        if obj["id"] not in colors:
            continue
        entry = {"id": obj["id"], "shape": obj["shape"], "color": colors[obj["id"]], "parent": obj.get("parent")}
        if obj.get("name"):
            entry["name"] = obj["name"]
            names[obj["name"]] = colors[obj["id"]]
        objects.append(entry)
    return {"scene": scene_id, "background": MASK_BACKGROUND, "colors": dict(colors), "objects": objects, "names": names}


def _sample_frames(frames: int) -> list[int]:
    if frames <= DEPTH_SAMPLES:
        return list(range(frames))
    return sorted({round(k * (frames - 1) / (DEPTH_SAMPLES - 1)) for k in range(DEPTH_SAMPLES)})


def depth_range(description: dict[str, Any], world: World) -> list[float]:
    """``[near, far]``: the distances from the camera (along its view) the depth pass maps to
    white and black (linear between them), one range for the whole shot. From the shown objects in view at up to
    :data:`DEPTH_SAMPLES` frames: a plane by a grid of its points inside the view, every other
    shape by its sphere; then widened by :data:`DEPTH_PAD`."""
    width, height = int(description["width"]), int(description["height"])
    aspect = width / height
    fov = math.radians(float(description["camera"]["fov"]))
    tan_v = math.tan(fov / 2) if aspect >= 1 else math.tan(fov / 2) / aspect
    tan_h = tan_v * aspect
    near_limit = float(description["camera"]["near"])
    fps = int(description["fps"])
    grid = np.linspace(-0.5, 0.5, PLANE_GRID)
    plane_local = np.array([[x, 0.0, z, 1.0] for x in grid for z in grid])
    lows, highs = [], []
    for n in _sample_frames(int(description["frames"])):
        t = n / fps
        position, look = camera_at(description, t)
        forward = (look - position) / np.linalg.norm(look - position)
        right = np.cross(forward, [0.0, 1.0, 0.0])
        right = right / np.linalg.norm(right) if np.linalg.norm(right) > 1e-9 else np.array([1.0, 0.0, 0.0])
        up = np.cross(right, forward)
        for obj_id, placed in world.objects.items():
            if placed.shape in NOT_DRAWN or world.opacity(obj_id, t) < SHOWN:
                continue
            if placed.shape == "plane":
                points = (world.matrix(obj_id, t) @ (plane_local * [placed.size[0], 1, placed.size[2], 1]).T).T[:, :3] - position
                depth = points @ forward
                ahead = depth > near_limit
                inside = ahead & (np.abs(points @ right) <= depth * tan_h * 1.05) & (np.abs(points @ up) <= depth * tan_v * 1.05)
                if inside.any():
                    lows.append(float(depth[inside].min()))
                    highs.append(float(depth[inside].max()))
                continue
            centre, radius = world.focus(obj_id, t)
            d = centre - position
            depth_c = float(d @ forward)
            if depth_c + radius <= near_limit:
                continue
            slack = radius / max(depth_c, near_limit)   # the sphere's half-size in view-tangent units
            seen = max(depth_c, near_limit)
            if abs(float(d @ right)) / seen > tan_h + slack or abs(float(d @ up)) / seen > tan_v + slack:
                continue
            lows.append(max(depth_c - radius, near_limit))
            highs.append(depth_c + radius)
    if not lows:
        return [near_limit, round(near_limit + 10.0, 6)]
    low, high = min(lows), max(max(highs), min(lows) + 0.1)
    pad = (high - low) * DEPTH_PAD
    return [round(max(low - pad, near_limit), 6), round(high + pad, 6)]


def guide_pass(description: dict[str, Any], world: World, mode: str) -> dict[str, Any]:
    """The description of guide pass ``mode`` of the (normal) ``description``: the same, with
    ``draw_mode`` = ``mode`` and, for ``depth``, ``depth_range``, for ``mask``, ``mask_colors``."""
    if mode not in GUIDE_PASSES:
        raise ValueError(f"no guide pass {mode!r}{did_you_mean(mode, GUIDE_PASSES)}")
    out = {**description, "draw_mode": mode}
    if mode == "depth":
        out["depth_range"] = depth_range(description, world)
    elif mode == "mask":
        out["mask_colors"] = mask_colors(description)
    return out


def pass_clip(folder: Path, name: str, mode: str) -> Path:
    """Where guide pass ``mode`` of scene ``name`` is stored: ``folder/<name>.<mode>.mkv``."""
    return folder / f"{name}.{mode}.mkv"


def mask_table_path(folder: Path, name: str) -> Path:
    """The mask's colour table of scene ``name``: ``folder/<name>.mask-colors.json``."""
    return folder / f"{name}.mask-colors.json"


def pass_files(folder: Path, name: str, passes: tuple[str, ...] | list[str]) -> list[Path]:
    """The files guide ``passes`` of scene ``name`` leave in ``folder`` (clips and the mask table)."""
    out = [pass_clip(folder, name, mode) for mode in passes]
    return out + ([mask_table_path(folder, name)] if "mask" in passes else [])


def make_guide_passes(folder: Path, name: str, description: dict[str, Any], world: World, passes: tuple[str, ...]) -> list[Path]:
    """Draw (or reuse, :func:`~vidgen.three_d.clip.make_3d_clip`) guide ``passes`` of the scene
    ``name`` with the normal ``description`` and its planned ``world``; with ``mask``, also write
    its colour table. Returns the files (:func:`pass_files`)."""
    for mode in passes:
        pass_description = guide_pass(description, world, mode)
        make_3d_clip(folder, f"{name}.{mode}", pass_description)
        if mode == "mask":
            write_text_atomic(mask_table_path(folder, name), json.dumps(mask_table(pass_description, name), indent=1) + "\n")
    return pass_files(folder, name, passes)


__all__ = [
    "ALL_PASSES", "GUIDE_PASSES", "depth_range", "guide_pass", "make_guide_passes", "mask_colors", "mask_table", "mask_table_path",
    "parse_passes", "pass_clip", "pass_files",
]
