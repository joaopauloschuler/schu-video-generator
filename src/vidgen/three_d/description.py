"""The scene description a ``3d`` scene sends to its page (DESIGN.md §114.3): plain JSON, so it can
be stored next to the render, hashed for the cache and read again by later passes.

Version 1::

    {"version": 1, "width": px, "height": px, "fps": n, "frames": n, "duration": s,
     "draw_mode": "normal", "background": "#rrggbb",
     "camera": {"fov", "position", "look_at", "near", "far"},
     "lights": [{"id": "ambient", "kind": "ambient", "color", "intensity"},
                {"id": "sun", "kind": "sun", "color", "intensity", "position"}],
     "objects": [{"id", "shape", "size", "color", "position", "rotation"}],
     "timeline": {"beats": [{"id", "start", "end"}],
                  "tracks": [{"target", "property", "easing", "keys": [{"t", "value"}]}]}}

Times are seconds from the scene's start; frame ``n`` shows ``t = n / fps``. A track sets a
property (``position``, ``rotation`` in degrees, the camera's ``look_at``) of an object (by id)
or of ``camera`` from its keys, eased between neighbours and held outside them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from vidgen.theme import Theme
from vidgen.three_d.spec import Object3D, Scene3DParams

DESCRIPTION_VERSION = 1
#: Ways the page can draw a scene; Step 301 adds the guide passes (depth, outline, mask).
DRAW_MODES: tuple[str, ...] = ("normal",)
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


def _vector(v: tuple[float, float, float]) -> list[float]:
    return [round(float(c), 6) for c in v]


def _spin_track(obj: Object3D, duration: float) -> dict[str, Any] | None:
    """A linear rotation track over the scene for an object with a ``spin``."""
    if not any(obj.spin):
        return None
    end = [r + s * duration for r, s in zip(obj.rotation, obj.spin)]
    return {
        "target": obj.id,
        "property": "rotation",
        "easing": "linear",
        "keys": [{"t": 0.0, "value": _vector(obj.rotation)}, {"t": round(duration, 6), "value": _vector(tuple(end))}],
    }


def scene_description(
    params: Scene3DParams,
    theme: Theme,
    *,
    width: int,
    height: int,
    fps: int,
    frames: int,
    beats: list[BeatSpan],
    draw_mode: str = "normal",
) -> dict[str, Any]:
    """The description of a ``3d`` scene with validated ``params`` (colours resolved with
    ``theme``) for ``frames`` frames of ``width`` x ``height`` at ``fps``."""
    if draw_mode not in DRAW_MODES:
        raise ValueError(f"unknown draw mode {draw_mode!r}")
    duration = frames / fps
    light = params.light
    norm = sum(c * c for c in light.sun_from) ** 0.5
    sun_position = tuple(c / norm * SUN_DISTANCE for c in light.sun_from)
    light_color = hex6(theme.color(light.color))
    tracks = [t for t in (_spin_track(o, duration) for o in params.objects) if t is not None]
    return {
        "version": DESCRIPTION_VERSION,
        "width": int(width),
        "height": int(height),
        "fps": int(fps),
        "frames": int(frames),
        "duration": round(duration, 6),
        "draw_mode": draw_mode,
        "background": hex6(theme.color(params.background) if params.background else theme.background),
        "camera": {
            "fov": float(params.camera.fov),
            "position": _vector(params.camera.position),
            "look_at": _vector(params.camera.look_at),
            "near": CAMERA_NEAR,
            "far": CAMERA_FAR,
        },
        "lights": [
            {"id": "ambient", "kind": "ambient", "color": light_color, "intensity": float(light.ambient)},
            {"id": "sun", "kind": "sun", "color": light_color, "intensity": float(light.sun), "position": _vector(sun_position)},
        ],
        "objects": [
            {
                "id": o.id,
                "shape": o.shape,
                "size": _vector(o.size),
                "color": hex6(theme.color(o.color)),
                "position": _vector(o.position),
                "rotation": _vector(o.rotation),
            }
            for o in params.objects
        ],
        "timeline": {
            "beats": [{"id": b.id, "start": round(b.start, 6), "end": round(b.end, 6)} for b in beats],
            "tracks": tracks,
        },
    }


def description_key(description: dict[str, Any], engine: str) -> str:
    """Digest of a description and of what draws it (``engine``: page files, three.js and
    browser versions): equal keys give the same frames."""
    text = json.dumps(description, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{engine}\n{text}".encode("utf-8")).hexdigest()


__all__ = ["DESCRIPTION_VERSION", "DRAW_MODES", "BeatSpan", "description_key", "hex6", "scene_description"]
