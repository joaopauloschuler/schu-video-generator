"""Where a ``3d`` scene's objects are on screen at a time (DESIGN.md §114.12), for lint: each
object's sphere projected by the camera of the scene description, how much of it lies outside
the frame and how much of it nearer objects cover. A cheap estimate from spheres (no pixels):
boxes count as a little smaller than their sphere when they cover something."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from vidgen.three_d.world import World

#: Shapes that never hide another object (flat, thin, drawn over or nothing at all).
NOT_COVERING: frozenset[str] = frozenset({"plane", "label", "arrow", "group"})
#: A covering object's sphere is shrunk by this much (its corners are not solid).
COVER_SHRINK = 0.85
#: Below this opacity an object is not on screen (hidden, fading).
SHOWN = 0.5


def _disc(count: int = 64) -> np.ndarray:
    """``count`` points spread evenly over the unit disc (a sunflower pattern)."""
    k = np.arange(count) + 0.5
    radius = np.sqrt(k / count)
    angle = k * math.pi * (3 - math.sqrt(5))
    return np.stack([radius * np.cos(angle), radius * np.sin(angle)], axis=1)


DISC = _disc()


def track_value(track: dict[str, Any], t: float) -> list[float]:
    """The value of a description track at ``t`` (as the page's ``trackValue``)."""
    keys = track["keys"]
    if t <= keys[0]["t"]:
        return list(keys[0]["value"])
    if t >= keys[-1]["t"]:
        return list(keys[-1]["value"])
    k = 0
    while keys[k + 1]["t"] < t:
        k += 1
    a, b = keys[k], keys[k + 1]
    u = (t - a["t"]) / (b["t"] - a["t"])
    if track.get("easing") == "smooth":
        u = u * u * (3 - 2 * u)
    return [va + (vb - va) * u for va, vb in zip(a["value"], b["value"])]


def camera_at(description: dict[str, Any], t: float) -> tuple[np.ndarray, np.ndarray]:
    """The camera's position and the point it looks at, at ``t``."""
    pose = {"position": description["camera"]["position"], "look_at": description["camera"]["look_at"]}
    for track in description["timeline"]["tracks"]:
        if track["target"] == "camera" and track["property"] in pose:
            pose[track["property"]] = track_value(track, t)
    return np.array(pose["position"], dtype=float), np.array(pose["look_at"], dtype=float)


def view_basis(description: dict[str, Any], t: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """The camera of ``description`` at ``t`` as the page sees it: its position, unit forward,
    right and up vectors, and the tangents of half the horizontal and vertical fov (vidgen's
    ``fov`` is across the shorter side)."""
    width, height = int(description["width"]), int(description["height"])
    aspect = width / height
    fov = math.radians(float(description["camera"]["fov"]))
    tan_v = math.tan(fov / 2) if aspect >= 1 else math.tan(fov / 2) / aspect
    position, look = camera_at(description, t)
    forward = (look - position) / np.linalg.norm(look - position)
    right = np.cross(forward, [0.0, 1.0, 0.0])
    right = right / np.linalg.norm(right) if np.linalg.norm(right) > 1e-9 else np.array([1.0, 0.0, 0.0])
    return position, forward, right, np.cross(right, forward), tan_v * aspect, tan_v


def framing_3d(description: dict[str, Any], world: World, t: float) -> list[dict[str, Any]]:
    """The objects on screen at ``t``: ``[{id, shape, box: [x0, y0, x1, y1] px, off: share of it
    outside the frame, hidden: share of it nearer objects cover, by: the nearest of those}]``
    (objects at least half visible; the floor and groups' parts included, groups too)."""
    width, height = int(description["width"]), int(description["height"])
    position, forward, right, up, tan_h, tan_v = view_basis(description, t)
    near = float(description["camera"]["near"])
    seen = []
    for obj_id, placed in world.objects.items():
        if world.opacity(obj_id, t) < SHOWN:
            continue
        centre, radius = world.focus(obj_id, t)
        d = centre - position
        depth = float(d @ forward)
        if depth <= near:
            seen.append({"id": obj_id, "shape": placed.shape, "depth": depth, "behind": True})
            continue
        x = (1 + float(d @ right) / (depth * tan_h)) / 2 * width
        y = (1 - float(d @ up) / (depth * tan_v)) / 2 * height
        r = radius / depth / tan_v * height / 2
        seen.append({"id": obj_id, "shape": placed.shape, "depth": depth, "x": x, "y": y, "r": r})
    out = []
    for obj in seen:
        if obj.get("behind"):
            out.append({"id": obj["id"], "shape": obj["shape"], "box": None, "off": 1.0, "hidden": 0.0, "by": None})
            continue
        points = DISC * obj["r"] + [obj["x"], obj["y"]]
        inside = (points[:, 0] >= 0) & (points[:, 0] <= width) & (points[:, 1] >= 0) & (points[:, 1] <= height)
        covered = np.zeros(len(points), dtype=bool)
        by, nearest = None, math.inf
        for other in seen:
            if (other is obj or other.get("behind") or other["shape"] in NOT_COVERING or other["depth"] >= obj["depth"]
                    or _related(world, obj["id"], other["id"])):
                continue
            under = np.hypot(points[:, 0] - other["x"], points[:, 1] - other["y"]) <= other["r"] * COVER_SHRINK
            if under.any():
                covered |= under
                if other["depth"] < nearest:
                    by, nearest = other["id"], other["depth"]
        shown = max(int(inside.sum()), 1)
        out.append({
            "id": obj["id"], "shape": obj["shape"],
            "box": [round(obj["x"] - obj["r"], 1), round(obj["y"] - obj["r"], 1), round(obj["x"] + obj["r"], 1), round(obj["y"] + obj["r"], 1)],
            "off": round(1 - float(inside.mean()), 3),
            "hidden": round(float((covered & inside).sum()) / shown, 3) if inside.any() else 0.0,
            "by": by,
        })
    return out


def _related(world: World, a: str, b: str) -> bool:
    """Whether one object is part of the other (a group and its children)."""
    return world.within(a, b) or world.within(b, a)


__all__ = ["camera_at", "framing_3d", "track_value", "view_basis"]
