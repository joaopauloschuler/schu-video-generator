"""Guide passes of a ``3d`` scene (DESIGN.md §114.14): the same frames drawn three more ways, for
tools that read a scene's shape and layout rather than its look (later: video-to-video).

- ``depth``: grey by distance from the camera, near white and far dark, over one range for the
  whole shot (it does not flicker as things move), fitted to the objects (the floor and other
  planes are clamped to it) or given as ``depth_range``;
- ``outline``: white edges on black, like a line drawing (what edge inputs of video models expect);
- ``mask``: every object in one flat colour of its own on black, derived from its id (adding an
  object does not change the others'), the floor a dark grey, with a table object id -> colour
  (``<scene>.mask-colors.json``).

A pass is the scene description with another ``draw_mode`` (and its range or colours), so it
shares the camera, timing and frame count by construction; it is drawn and cached like the
scene's clip, beside it: ``<render_dir>/three_d/<scene>.<pass>.mkv`` + ``.json``. Labels and name
tags are left out (only the 3D shapes), as are the title, captions and overlays (Manim draws
those over the clip, never into it).
"""

from __future__ import annotations

import colorsys
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from vidgen.cellworld.model import did_you_mean
from vidgen.fileio import write_text_atomic
from vidgen.three_d.clip import make_3d_clip
from vidgen.three_d.framing import SHOWN, camera_at, view_basis
from vidgen.three_d.spec import ALL_PASSES, FLOOR_ID, GUIDE_PASSES, parse_passes
from vidgen.three_d.world import World

#: Shapes a pass does not draw: groups draw nothing, labels are text, not shape.
NOT_DRAWN: frozenset[str] = frozenset({"group", "label"})
#: The mask's background (no object).
MASK_BACKGROUND = "#000000"
#: The floor's mask colour: a neutral dark grey (a large area, not one of the objects of interest).
FLOOR_MASK = "#404040"
#: Hues of the mask palette (evenly spread) and its tones (saturation, value): bright, dark, pale.
MASK_HUES = 16
MASK_TONES: tuple[tuple[float, float], ...] = ((0.85, 1.0), (0.9, 0.6), (0.45, 1.0))
#: When an object's colour is taken, the next one tried is this many places further on (7 is
#: coprime with the palette's 48 colours, so every colour is tried; it also changes hue and tone).
MASK_PROBE = 7
#: The depth range is widened by this share of its span at each end: the nearest object is not
#: clipped to white, the farthest stays a grey apart from what lies behind it.
DEPTH_PAD = 0.05
#: At most this many frames are looked at for the depth range (evenly spread, first and last).
DEPTH_SAMPLES = 120
#: The corners of a unit box around the origin (homogeneous), scaled by an object's size.
BOX_CORNERS = np.array([[x, y, z, 1.0] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)])
#: Points per side of the grid a plane is sampled with for the depth range (a scene of planes only).
PLANE_GRID = 17


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)


#: The mask palette: :data:`MASK_HUES` hues x :data:`MASK_TONES`, well apart, never black or grey.
MASK_PALETTE: tuple[str, ...] = tuple(
    _hex(colorsys.hsv_to_rgb(h / MASK_HUES, sat, val)) for h in range(MASK_HUES) for sat, val in MASK_TONES
)


def _id_hash(object_id: str, salt: int = 0) -> int:
    """A number from ``object_id`` that is the same on every machine and every run."""
    return int.from_bytes(hashlib.sha256(f"{object_id}\0{salt}".encode("utf-8")).digest()[:8], "big")


def mask_colors(description: dict[str, Any]) -> dict[str, str]:
    """A colour of its own for every drawn object of ``description`` (groups and labels have
    none; in description order): the floor :data:`FLOOR_MASK`; every other object the
    :data:`MASK_PALETTE` colour its id hashes to. When two ids hash to the same colour, the one
    first in alphabetical order keeps it and the other takes the next free colour
    (:data:`MASK_PROBE` places on; past the palette, a colour from its hash). So the colours
    depend only on the set of ids, not their order, and adding an object changes another's only
    when the two clash. Never black."""
    drawn = [obj["id"] for obj in description["objects"] if obj["shape"] not in NOT_DRAWN]
    chosen: dict[str, str] = {FLOOR_ID: FLOOR_MASK} if FLOOR_ID in drawn else {}
    taken = {MASK_BACKGROUND, FLOOR_MASK}
    size = len(MASK_PALETTE)
    for object_id in sorted(i for i in drawn if i != FLOOR_ID):
        start = _id_hash(object_id) % size
        color = next((c for c in (MASK_PALETTE[(start + k * MASK_PROBE) % size] for k in range(size)) if c not in taken), None)
        salt = 0
        while color is None or color in taken:   # every palette colour is taken: one from the hash
            salt += 1
            color = "#" + f"{_id_hash(object_id, salt) & 0xFFFFFF:06x}"
        taken.add(color)
        chosen[object_id] = color
    return {object_id: chosen[object_id] for object_id in drawn}


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
    white and to its darkest grey (linear between them), one range for the whole shot, fitted to
    the **objects**: at up to :data:`DEPTH_SAMPLES` frames, every shown object in view except
    planes (the floor), from the nearest to the farthest point of its sphere or its box (the
    tighter), then widened by :data:`DEPTH_PAD`. A plane nearer or farther
    than the range is clamped to white or the darkest grey, so the objects get the contrast. A
    scene with only planes fits them instead (a grid of their points inside the view)."""
    near_limit = float(description["camera"]["near"])
    fps = int(description["fps"])
    grid = np.linspace(-0.5, 0.5, PLANE_GRID)
    plane_local = np.array([[x, 0.0, z, 1.0] for x in grid for z in grid])
    objects: list[tuple[float, float]] = []
    planes: list[tuple[float, float]] = []
    for n in _sample_frames(int(description["frames"])):
        t = n / fps
        position, forward, right, up, tan_h, tan_v = view_basis(description, t)
        for obj_id, placed in world.objects.items():
            if placed.shape in NOT_DRAWN or world.opacity(obj_id, t) < SHOWN:
                continue
            if placed.shape == "plane":
                points = (world.matrix(obj_id, t) @ (plane_local * [placed.size[0], 1, placed.size[2], 1]).T).T[:, :3] - position
                depth = points @ forward
                inside = (depth > near_limit) & (np.abs(points @ right) <= depth * tan_h * 1.05) & (np.abs(points @ up) <= depth * tan_v * 1.05)
                if inside.any():
                    planes.append((float(depth[inside].min()), float(depth[inside].max())))
                continue
            centre, radius = world.focus(obj_id, t)
            d = centre - position
            depth_c = float(d @ forward)
            if depth_c + radius <= near_limit:
                continue
            seen = max(depth_c, near_limit)
            slack = radius / seen   # the sphere's half-size in view-tangent units
            if abs(float(d @ right)) / seen > tan_h + slack or abs(float(d @ up)) / seen > tan_v + slack:
                continue
            # its extent along the view: within its sphere and within its box (an arrow's or a
            # stand-in's sphere reaches far past it), whichever is tighter at each end
            size = placed.size if not world.points_somewhere(obj_id) else (placed.size[0], world.arrow_pose(obj_id, t)[2], placed.size[2])
            corners = (world.matrix(obj_id, t) @ (BOX_CORNERS * [*size, 1.0]).T).T[:, :3] - position
            along = corners @ forward
            low, high = max(depth_c - radius, float(along.min())), min(depth_c + radius, float(along.max()))
            objects.append((max(low, near_limit), max(high, near_limit)))
    spans = objects or planes
    if not spans:
        return [near_limit, round(near_limit + 10.0, 6)]
    low = min(a for a, _ in spans)
    high = max(max(b for _, b in spans), low + 0.1)
    pad = (high - low) * DEPTH_PAD
    return [round(max(low - pad, near_limit), 6), round(high + pad, 6)]


def guide_pass(description: dict[str, Any], world: World, mode: str, depth: tuple[float, float] | None = None) -> dict[str, Any]:
    """The description of guide pass ``mode`` of the (normal) ``description``: the same, with
    ``draw_mode`` = ``mode`` and, for ``depth``, ``depth_range`` (``depth``, the scene's
    ``depth_range``, or fitted: :func:`depth_range`), for ``mask``, ``mask_colors``."""
    if mode not in GUIDE_PASSES:
        raise ValueError(f"no guide pass {mode!r}{did_you_mean(mode, GUIDE_PASSES)}")
    out = {**description, "draw_mode": mode}
    if mode == "depth":
        out["depth_range"] = [round(float(depth[0]), 6), round(float(depth[1]), 6)] if depth is not None else depth_range(description, world)
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


def make_guide_passes(
    folder: Path, name: str, description: dict[str, Any], world: World, passes: tuple[str, ...], depth: tuple[float, float] | None = None,
) -> list[Path]:
    """Draw (or reuse, :func:`~vidgen.three_d.clip.make_3d_clip`) guide ``passes`` of the scene
    ``name`` with the normal ``description`` and its planned ``world`` (``depth``: the depth
    pass's range, else fitted); with ``mask``, also write its colour table. Returns the files
    (:func:`pass_files`)."""
    for mode in passes:
        pass_description = guide_pass(description, world, mode, depth)
        make_3d_clip(folder, f"{name}.{mode}", pass_description)
        if mode == "mask":
            write_text_atomic(mask_table_path(folder, name), json.dumps(mask_table(pass_description, name), indent=1) + "\n")
    return pass_files(folder, name, passes)


__all__ = [
    "ALL_PASSES", "FLOOR_MASK", "GUIDE_PASSES", "MASK_PALETTE", "depth_range", "guide_pass", "make_guide_passes", "mask_colors", "mask_table", "mask_table_path",
    "parse_passes", "pass_clip", "pass_files",
]
