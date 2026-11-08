"""Camera moves of a ``3d`` scene (DESIGN.md §114.8): the beat actions ``camera_orbit``,
``camera_dolly``, ``camera_fly_to``, ``camera_look_at`` and ``camera_move`` become
:class:`CameraMove` s with a start and an end on the scene's clock; :func:`camera_tracks` turns
them into the description's ``position`` and ``look_at`` tracks of ``camera``, one key per frame
while the camera moves (the eased path computed here, so the page only interpolates).

Each move starts from where the camera is when it starts (the moves before it, in time order);
a move still running when the next one starts stops there. No manim, no browser.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from vidgen.three_d.spec import Scene3DParams, Vec3
from vidgen.three_d.world import World

#: The kinds of move (the action ``camera_<kind>``).
CAMERA_MOVES: tuple[str, ...] = ("orbit", "dolly", "fly_to", "look_at", "move")
#: Easings of a move (the page's names).
EASINGS: tuple[str, ...] = ("smooth", "linear")
#: Closest the camera may come to the point it looks at (scene units).
MIN_DISTANCE = 0.1
#: ``camera_fly_to`` without a ``distance``: the object's sphere fills this share of the frame's shorter side.
FILL = 0.6


@dataclass(frozen=True)
class CameraMove:
    """One move of the camera from ``start`` to ``end`` (seconds of the scene's clock).

    ``kind`` is one of :data:`CAMERA_MOVES`; the fields it reads: ``orbit`` — ``degrees`` around
    the vertical axis through ``target``'s centre or ``point`` (default: the point looked at),
    rising by ``up``; ``dolly`` — ``by`` units towards the point looked at (negative: away);
    ``fly_to`` — to ``target`` (an object id), keeping the direction it looks from, at
    ``distance`` (default: the object fills :data:`FILL` of the frame); ``look_at`` — turn to
    ``target`` or ``point``; ``move`` — stand at ``point``, looking at ``look_at`` (an object
    id or a point; default: where it looks)."""

    kind: str
    start: float = 0.0
    end: float = 1.0
    easing: str = "smooth"
    target: str | None = None
    point: Vec3 | None = None
    look_at: str | Vec3 | None = None
    degrees: float = 0.0
    up: float = 0.0
    by: float = 0.0
    distance: float | None = None


@dataclass(frozen=True)
class Pose:
    """Where the camera stands and the point it looks at."""

    position: np.ndarray
    look_at: np.ndarray


Path = Callable[[float], Pose]


def ease(easing: str, u: float) -> float:
    """``u`` (0..1) eased like the page's ``EASINGS``."""
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u) if easing == "smooth" else u


def _lerp(a: np.ndarray, b: np.ndarray, u: float) -> np.ndarray:
    return a + (b - a) * u


def start_pose(params: Scene3DParams, world: World) -> Pose:
    """The camera of ``params`` at the scene's start (``look_at`` an object: its centre then)."""
    look = params.camera.look_at
    point = world.focus(look, 0.0)[0] if isinstance(look, str) else np.array(look, dtype=float)
    position = np.array(params.camera.position, dtype=float)
    if np.linalg.norm(point - position) < MIN_DISTANCE:
        raise ValueError(f"camera.look_at: the camera stands on '{look}'; move it away")
    return Pose(position, point)


def check_3d_scene(params: Scene3DParams) -> None:
    """``ValueError`` when validated ``params`` cannot be built: an arrow whose tip is its tail,
    a camera standing on the object it looks at."""
    start_pose(params, World(params))


def _point(world: World, ref: str | Vec3, t: float) -> np.ndarray:
    return world.focus(ref, t)[0] if isinstance(ref, str) else np.array(ref, dtype=float)


def move_path(move: CameraMove, pose: Pose, world: World, fov: float) -> Path:
    """The camera's pose along ``move`` (u: 0..1 of it, not eased yet) from ``pose``;
    ``ValueError`` when the move cannot be made from there."""
    p0, l0 = pose.position, pose.look_at
    if move.kind == "orbit":
        centre = _point(world, move.target or move.point, move.start) if (move.target or move.point) is not None else l0
        v = p0 - centre
        radius = math.hypot(v[0], v[2])
        if radius < MIN_DISTANCE:
            raise ValueError("the camera stands right above (or below) the centre it would orbit; move it to the side first")
        a0 = math.atan2(v[0], v[2])

        def orbit(u: float) -> Pose:
            a = a0 + math.radians(move.degrees) * u
            return Pose(centre + np.array([radius * math.sin(a), v[1] + move.up * u, radius * math.cos(a)]), _lerp(l0, centre, u))

        return orbit
    if move.kind == "dolly":
        towards = l0 - p0
        distance = float(np.linalg.norm(towards))
        if distance - move.by < MIN_DISTANCE:
            raise ValueError(f"by: {move.by:g} would take the camera to or past the point it looks at ({distance:.2f} away)")
        step = towards / distance * move.by
        return lambda u: Pose(p0 + step * u, l0)
    if move.kind == "fly_to":
        centre, radius = world.focus(move.target or "", move.start)
        distance = move.distance if move.distance is not None else max(radius / math.sin(math.radians(fov) * FILL / 2), radius + MIN_DISTANCE)
        back = p0 - l0
        p1 = centre + back / np.linalg.norm(back) * distance
        return lambda u: Pose(_lerp(p0, p1, u), _lerp(l0, centre, u))
    if move.kind == "look_at":
        l1 = _point(world, move.target if move.target is not None else move.point, move.start)  # type: ignore[arg-type]
        if np.linalg.norm(l1 - p0) < MIN_DISTANCE:
            raise ValueError("the camera stands on the point it would look at")
        return lambda u: Pose(p0, _lerp(l0, l1, u))
    if move.kind == "move":
        p1 = np.array(move.point, dtype=float)
        l1 = _point(world, move.look_at, move.start) if move.look_at is not None else l0
        if np.linalg.norm(l1 - p1) < MIN_DISTANCE:
            raise ValueError("to: the camera would stand on the point it looks at")
        return lambda u: Pose(_lerp(p0, p1, u), _lerp(l0, l1, u))
    raise ValueError(f"unknown camera move {move.kind!r}")


def camera_problems(params: Scene3DParams, moves: Sequence[CameraMove]) -> list[tuple[int, str]]:
    """Moves (by index in ``moves``) that cannot be made, each run to its end in time order
    from the camera of ``params``: ``[(index, message)]`` (empty: all fine)."""
    world = World(params)
    pose = start_pose(params, world)
    problems = []
    for k in sorted(range(len(moves)), key=lambda i: moves[i].start):
        try:
            pose = move_path(moves[k], pose, world, params.camera.fov)(1.0)
        except ValueError as exc:
            problems.append((k, str(exc)))
    return problems


def _vector(v: np.ndarray) -> list[float]:
    return [round(float(c), 6) for c in v]


def camera_tracks(params: Scene3DParams, world: World, moves: Sequence[CameraMove], fps: int, frames: int) -> list[dict[str, Any]]:
    """The description's tracks of ``camera`` for ``moves``: ``position`` and ``look_at``, one
    key per frame from each move's first frame to its last (``linear``: the easing is in the
    keys), held between moves; none without moves. ``ValueError`` for a move that cannot be made."""
    if not moves:
        return []
    pose = start_pose(params, world)
    keys: dict[int, Pose] = {}
    last = frames - 1
    ordered = sorted(moves, key=lambda m: m.start)
    for k, move in enumerate(ordered):
        first = min(round(move.start * fps), last)
        end = max(round(move.end * fps), first + 1)
        stop = min(end, last, round(ordered[k + 1].start * fps) if k + 1 < len(ordered) else end)
        path = move_path(move, pose, world, params.camera.fov)
        for n in range(first, max(stop, first) + 1):
            keys[n] = path(ease(move.easing, (n - first) / (end - first)))
        pose = keys[max(stop, first)]
    times = sorted(keys)
    return [
        {"target": "camera", "property": prop, "easing": "linear",
         "keys": [{"t": round(n / fps, 6), "value": _vector(getattr(keys[n], attr))} for n in times]}
        for prop, attr in (("position", "position"), ("look_at", "look_at"))
    ]


__all__ = ["CAMERA_MOVES", "EASINGS", "CameraMove", "Pose", "camera_problems", "camera_tracks", "check_3d_scene", "ease", "move_path", "start_pose"]
