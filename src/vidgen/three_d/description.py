"""The scene description a ``3d`` scene sends to its page (DESIGN.md §114.3): plain JSON, so it can
be stored next to the render, hashed for the cache and read again by later passes.

Version 1::

    {"version": 1, "width": px, "height": px, "fps": n, "frames": n, "duration": s,
     "draw_mode": "normal" | "depth" | "outline" | "mask", "background": "#rrggbb",
     (+ "depth_range": [near, far] for depth, "mask_colors": {id: "#rrggbb"} for mask)
     "camera": {"fov", "position", "look_at", "near", "far"},
     "lights": [{"id": "ambient", "kind": "ambient", "color", "intensity"},
                {"id": "sun", "kind": "sun", "color", "intensity", "position"}],
     "objects": [{"id", "shape", "parent", "size", "color", "position", "rotation"
                  (+ "opacity": 0 when hidden at the start; "text", "plate", "plate_opacity",
                  "screen_depth" for a label; "nose", "name", "name_size", "name_gap",
                  "name_color", "plate", "plate_opacity" for a stand-in)}],
     "timeline": {"beats": [{"id", "start", "end"}],
                  "tracks": [{"target", "property", "easing", "keys": [{"t", "value"}]}]}}

Times are seconds from the scene's start; frame ``n`` shows ``t = n / fps``. A track sets a
property (``position``, ``rotation`` in degrees, ``scale``, ``opacity`` [v], ``emissive``
[r, g, b] 0..1, an arrow's ``length`` [L], the camera's ``look_at``) of an object (by id)
or of ``camera`` from its keys, eased between neighbours and held outside them. Objects come in
the order the page builds them: a ``parent`` (an id, or ``null``) before its children, whose
position and rotation are in its frame. A group has ``shape: group`` and no ``size``/``color``.
Camera moves (Step 299) are ``position`` and ``look_at`` tracks of ``camera`` with a key per
frame while it moves; object actions (Step 300) are tracks of the objects, a key per frame while
they change (a ``spin`` alone stays a 2-key track).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from vidgen.theme import Theme
from vidgen.three_d.camera import CameraMove, camera_tracks, start_pose
from vidgen.three_d.motion import ObjectChange, object_tracks, plan_motion
from vidgen.three_d.spec import Object3D, Scene3DParams
from vidgen.three_d.world import World

DESCRIPTION_VERSION = 1
#: Ways the page can draw a scene: as it looks, or one of the guide passes (§114.14:
#: ``three_d/passes.py``).
DRAW_MODES: tuple[str, ...] = ("normal", "depth", "outline", "mask")
#: Nearest and farthest distance the camera draws (scene units).
CAMERA_NEAR, CAMERA_FAR = 0.1, 500.0
#: Distance of the sun from the origin along ``sun_from`` (only its direction matters).
SUN_DISTANCE = 20.0


@dataclass(frozen=True)
class BeatSpan:
    """A beat on the scene's clock: seconds from the scene's start to its start and its end."""

    id: str
    start: float
    end: float


def hex6(color: str) -> str:
    """``#rgb`` / ``#rrggbb`` / ``#rrggbbaa`` -> ``#rrggbb`` (lower case; alpha dropped)."""
    digits = color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits[:6].lower()


def _vector(v: Any) -> list[float]:
    return [round(float(c), 6) for c in v]


#: A label's plate: the theme colour behind its text and its opacity (as ``text_plate``'s).
LABEL_PLATE, LABEL_PLATE_OPACITY = "surface", 0.88


#: A stand-in's name: its text height as a share of the stand-in's height, and the gap above its head.
NAME_SHARE, NAME_GAP = 0.14, 0.12


def nose_color(color: str) -> str:
    """A stand-in's nose: its colour made darker (a light colour) or lighter (a dark one)."""
    rgb = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    light = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255 > 0.5
    mixed = [round(c * 0.5) if light else round(c + (255 - c) * 0.55) for c in rgb]
    return "#" + "".join(f"{c:02x}" for c in mixed)


def plan_world(params: Scene3DParams, fps: int, frames: int, object_changes: list[ObjectChange] | None = None) -> World:
    """The world of ``params`` with ``object_changes`` planned over ``frames`` frames at
    ``fps`` (``ValueError`` for a change that cannot be made)."""
    world = World(params)
    plan_motion(params, world, object_changes or [], fps, frames)
    return world


def _objects(params: Scene3DParams, world: World, theme: Theme, camera: Any) -> list[dict[str, Any]]:
    """The description's objects: the floor, then ``params.objects`` as the world places them."""
    sources: dict[str, Object3D] = {o.id: o for o in params.objects}
    out = []
    for placed in world.objects.values():
        entry: dict[str, Any] = {"id": placed.id, "shape": placed.shape, "parent": placed.parent}
        if placed.shape != "group":
            obj = sources.get(placed.id)
            token = obj.color_token() if obj is not None else params.floor.color  # type: ignore[union-attr]
            entry["size"] = _vector(placed.size)
            entry["color"] = hex6(theme.color(token))
        entry["position"] = _vector(placed.position)
        entry["rotation"] = _vector(placed.rotation)
        obj = sources.get(placed.id)
        if obj is not None and not obj.visible:
            entry["opacity"] = 0.0
        if placed.shape == "label" or (placed.shape == "standin" and obj is not None and obj.name):
            entry["plate"] = hex6(theme.color(LABEL_PLATE))
            entry["plate_opacity"] = LABEL_PLATE_OPACITY
        if placed.shape == "label":
            entry["text"] = sources[placed.id].text
            if sources[placed.id].screen_size:
                view = camera.look_at - camera.position
                depth = float((world.position(placed.id, 0.0) - camera.position) @ (view / (view @ view) ** 0.5))
                entry["screen_depth"] = round(max(depth, 0.1), 6)
        if placed.shape == "standin":
            entry["nose"] = nose_color(entry["color"])
            if obj is not None and obj.name:
                entry["name"] = obj.name
                entry["name_size"] = round(NAME_SHARE * placed.size[1], 6)
                entry["name_gap"] = NAME_GAP
                entry["name_color"] = hex6(theme.color("text"))
        out.append(entry)
    return out


def scene_description(
    params: Scene3DParams,
    theme: Theme,
    *,
    width: int,
    height: int,
    fps: int,
    frames: int,
    beats: list[BeatSpan],
    camera_moves: list[CameraMove] | None = None,
    object_changes: list[ObjectChange] | None = None,
    draw_mode: str = "normal",
) -> dict[str, Any]:
    """The description of a ``3d`` scene with validated ``params`` (colours resolved with
    ``theme``) for ``frames`` frames of ``width`` x ``height`` at ``fps``, the objects changed by
    ``object_changes`` and the camera moved by ``camera_moves``. ``ValueError`` for an arrow, an
    object change or a camera move that cannot be made. Another ``draw_mode`` than ``normal``
    gives that guide pass's description (:func:`vidgen.three_d.passes.guide_pass`)."""
    if draw_mode not in DRAW_MODES:
        raise ValueError(f"unknown draw mode {draw_mode!r}")
    duration = frames / fps
    light = params.light
    norm = sum(c * c for c in light.sun_from) ** 0.5
    sun_position = tuple(c / norm * SUN_DISTANCE for c in light.sun_from)
    light_color = hex6(theme.color(light.color))
    world = plan_world(params, fps, frames, object_changes)
    camera = start_pose(params, world)
    tracks = object_tracks(world, duration) + camera_tracks(params, world, camera_moves or [], fps, frames)
    described = {
        "version": DESCRIPTION_VERSION,
        "width": int(width),
        "height": int(height),
        "fps": int(fps),
        "frames": int(frames),
        "duration": round(duration, 6),
        "draw_mode": "normal",
        "background": hex6(theme.color(params.background) if params.background else theme.background),
        "camera": {
            "fov": float(params.camera.fov),
            "position": _vector(camera.position),
            "look_at": _vector(camera.look_at),
            "near": CAMERA_NEAR,
            "far": CAMERA_FAR,
        },
        "lights": [
            {"id": "ambient", "kind": "ambient", "color": light_color, "intensity": float(light.ambient)},
            {"id": "sun", "kind": "sun", "color": light_color, "intensity": float(light.sun), "position": _vector(sun_position)},
        ],
        "objects": _objects(params, world, theme, camera),
        "timeline": {
            "beats": [{"id": b.id, "start": round(b.start, 6), "end": round(b.end, 6)} for b in beats],
            "tracks": tracks,
        },
    }
    if draw_mode == "normal":
        return described
    from vidgen.three_d.passes import guide_pass

    return guide_pass(described, world, draw_mode)


def description_key(description: dict[str, Any], engine: str) -> str:
    """Digest of a description and of what draws it (``engine``: page files, three.js and
    browser versions): equal keys give the same frames."""
    text = json.dumps(description, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{engine}\n{text}".encode("utf-8")).hexdigest()


__all__ = ["DESCRIPTION_VERSION", "DRAW_MODES", "BeatSpan", "description_key", "hex6", "nose_color", "plan_world", "scene_description"]
