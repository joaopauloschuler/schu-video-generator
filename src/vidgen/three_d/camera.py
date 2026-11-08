"""Camera moves of a ``3d`` scene (DESIGN.md §114.8): the beat actions ``camera_orbit``,
``camera_dolly``, ``camera_fly_to``, ``camera_look_at`` and ``camera_move`` become
:class:`CameraMove` s with a start and an end on the scene's clock; :func:`camera_tracks` turns
them into the description's ``position`` and ``look_at`` tracks of ``camera``, one key per frame
while the camera moves (the eased path computed here, so the page only interpolates).

Each move starts from where the camera is when it starts (the moves before it, in time order);
a move still running when the next one starts stops there. An object named by a move (or by
``camera.look_at``) is followed while it moves (its position each frame, from the object actions):
after ``camera_fly_to`` the camera keeps its distance to it, after ``camera_look_at`` it keeps
looking at it, until the next move. No manim, no browser.
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


@dataclass(frozen=True)
class Ref:
    """A point the camera stands at or looks at: ``base``, or — with ``obj`` — ``base`` carried
    along as that object moves after ``since`` (seconds), so the camera follows it."""

    base: np.ndarray
    obj: str | None = None
    since: float = 0.0

    def at(self, world: World, t: float) -> np.ndarray:
        """Where the point is at ``t``."""
        if self.obj is None:
            return self.base
        return self.base + world.position(self.obj, t) - world.position(self.obj, self.since)

    def shifted(self, by: np.ndarray) -> Ref:
        return Ref(self.base + by, self.obj, self.since)


def follow(world: World, object_id: str, t: float) -> Ref:
    """The centre of ``object_id`` at ``t``, followed as the object moves."""
    return Ref(world.follow(object_id, t)[0], object_id, t)


@dataclass(frozen=True)
class CameraState:
    """Where the camera stands and what it looks at between moves (either may follow an object:
    after ``camera_fly_to`` it keeps its distance to the object, after ``camera_look_at`` an
    object it keeps looking at it)."""

    position: Ref
    look_at: Ref

    def pose(self, world: World, t: float) -> Pose:
        return Pose(self.position.at(world, t), self.look_at.at(world, t))


class MovePath:
    """The camera's pose along a move: ``path(u, t)`` (u: 0..1 of the move, eased; t: the
    scene time, for objects that move meanwhile; default the move's start), and the state it
    leaves the camera in when it ends (:meth:`end_state`)."""

    def __init__(self, start: float, pose: Callable[[float, float], Pose], end: Callable[[float], CameraState]) -> None:
        self.start = start
        self._pose = pose
        self._end = end

    def __call__(self, u: float, t: float | None = None) -> Pose:
        return self._pose(u, self.start if t is None else t)

    def end_state(self, t: float) -> CameraState:
        """The camera after the move, ended at ``t``."""
        return self._end(t)


def ease(easing: str, u: float) -> float:
    """``u`` (0..1) eased like the page's ``EASINGS``."""
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u) if easing == "smooth" else u


def _lerp(a: np.ndarray, b: np.ndarray, u: float) -> np.ndarray:
    return a + (b - a) * u


def start_state(params: Scene3DParams, world: World) -> CameraState:
    """The camera of ``params`` at the scene's start (``look_at`` an object: its centre, followed)."""
    look = params.camera.look_at
    target = follow(world, look, 0.0) if isinstance(look, str) else Ref(np.array(look, dtype=float))
    position = np.array(params.camera.position, dtype=float)
    if np.linalg.norm(target.at(world, 0.0) - position) < MIN_DISTANCE:
        raise ValueError(f"camera.look_at: the camera stands on '{look}'; move it away")
    return CameraState(Ref(position), target)


def start_pose(params: Scene3DParams, world: World) -> Pose:
    """The camera of ``params`` at the scene's start (``look_at`` an object: its centre then)."""
    return start_state(params, world).pose(world, 0.0)


def check_3d_scene(params: Scene3DParams) -> None:
    """``ValueError`` when validated ``params`` cannot be built: an arrow whose tip is its tail,
    a camera standing on the object it looks at."""
    start_pose(params, World(params))


def _ref(world: World, ref: str | Vec3, t: float) -> Ref:
    return follow(world, ref, t) if isinstance(ref, str) else Ref(np.array(ref, dtype=float))


def move_path(move: CameraMove, start: Pose | CameraState, world: World, fov: float) -> MovePath:
    """The camera's path along ``move`` from ``start`` (a pose, or a state that may follow
    objects); ``ValueError`` when the move cannot be made from there."""
    state = start if isinstance(start, CameraState) else CameraState(Ref(start.position), Ref(start.look_at))
    ts = move.start
    pos, look = state.position, state.look_at
    p0, l0 = pos.at(world, ts), look.at(world, ts)
    if move.kind == "orbit":
        ref = move.target or move.point
        centre = _ref(world, ref, ts) if ref is not None else look
        c0 = centre.at(world, ts)
        v = p0 - c0
        radius = math.hypot(v[0], v[2])
        if radius < MIN_DISTANCE:
            raise ValueError("the camera stands right above (or below) the centre it would orbit; move it to the side first")
        a0 = math.atan2(v[0], v[2])

        def offset(u: float) -> np.ndarray:
            a = a0 + math.radians(move.degrees) * u
            return np.array([radius * math.sin(a), v[1] + move.up * u, radius * math.cos(a)])

        return MovePath(ts, lambda u, t: Pose(centre.at(world, t) + offset(u), _lerp(look.at(world, t), centre.at(world, t), u)),
                        lambda t: CameraState(Ref(centre.at(world, t) + offset(1.0), centre.obj, t), centre))
    if move.kind == "dolly":
        towards = l0 - p0
        distance = float(np.linalg.norm(towards))
        if distance - move.by < MIN_DISTANCE:
            raise ValueError(f"by: {move.by:g} would take the camera to or past the point it looks at ({distance:.2f} away)")
        step = towards / distance * move.by
        return MovePath(ts, lambda u, t: Pose(pos.at(world, t) + step * u, look.at(world, t)),
                        lambda t: CameraState(pos.shifted(step), look))
    if move.kind == "fly_to":
        target = move.target or ""
        centre = follow(world, target, ts)
        radius = world.follow(target, ts)[1]
        distance = move.distance if move.distance is not None else max(radius / math.sin(math.radians(fov) * FILL / 2), radius + MIN_DISTANCE)
        back = (p0 - l0) / np.linalg.norm(p0 - l0) * distance

        def fly(u: float, t: float) -> Pose:
            c = centre.at(world, t)
            return Pose(_lerp(pos.at(world, t), c + back, u), _lerp(look.at(world, t), c, u))

        return MovePath(ts, fly, lambda t: CameraState(Ref(centre.at(world, t) + back, target, t), centre))
    if move.kind == "look_at":
        goal = _ref(world, move.target if move.target is not None else move.point, ts)  # type: ignore[arg-type]
        if np.linalg.norm(goal.at(world, ts) - p0) < MIN_DISTANCE:
            raise ValueError("the camera stands on the point it would look at")
        return MovePath(ts, lambda u, t: Pose(pos.at(world, t), _lerp(look.at(world, t), goal.at(world, t), u)),
                        lambda t: CameraState(pos, goal))
    if move.kind == "move":
        p1 = np.array(move.point, dtype=float)
        goal = _ref(world, move.look_at, ts) if move.look_at is not None else look
        if np.linalg.norm(goal.at(world, ts) - p1) < MIN_DISTANCE:
            raise ValueError("to: the camera would stand on the point it looks at")
        return MovePath(ts, lambda u, t: Pose(_lerp(pos.at(world, t), p1, u), _lerp(look.at(world, t), goal.at(world, t), u)),
                        lambda t: CameraState(Ref(p1), goal))
    raise ValueError(f"unknown camera move {move.kind!r}")


def camera_problems(params: Scene3DParams, moves: Sequence[CameraMove]) -> list[tuple[int, str]]:
    """Moves (by index in ``moves``) that cannot be made, each run to its end in time order
    from the camera of ``params``: ``[(index, message)]`` (empty: all fine)."""
    world = World(params)
    state = start_state(params, world)
    problems = []
    for k in sorted(range(len(moves)), key=lambda i: moves[i].start):
        try:
            state = move_path(moves[k], state, world, params.camera.fov).end_state(moves[k].end)
        except ValueError as exc:
            problems.append((k, str(exc)))
    return problems


def _vector(v: np.ndarray) -> list[float]:
    return [round(float(c), 6) for c in v]


def camera_poses(params: Scene3DParams, world: World, moves: Sequence[CameraMove], fps: int, frames: int) -> list[Pose]:
    """The camera's pose at every frame: held (or following an object) between moves, along
    each move from its first frame to its last; a move still running when the next starts stops
    there. ``ValueError`` for a move that cannot be made."""
    state = start_state(params, world)
    poses: list[Pose] = [state.pose(world, 0.0)] * frames
    last = frames - 1
    ordered = sorted(moves, key=lambda m: m.start)
    cursor = 0
    for k, move in enumerate(ordered):
        first = min(round(move.start * fps), last)
        end = max(round(move.end * fps), first + 1)
        stop = max(min(end, last, round(ordered[k + 1].start * fps) if k + 1 < len(ordered) else end), first)
        for n in range(cursor, first):
            poses[n] = state.pose(world, n / fps)
        path = move_path(move, state, world, params.camera.fov)
        for n in range(first, stop + 1):
            poses[n] = path(ease(move.easing, (n - first) / (end - first)), n / fps)
        state = path.end_state(end / fps) if stop >= end else CameraState(Ref(poses[stop].position), Ref(poses[stop].look_at))
        cursor = stop + 1
    for n in range(cursor, frames):
        poses[n] = state.pose(world, n / fps)
    return poses


def camera_tracks(params: Scene3DParams, world: World, moves: Sequence[CameraMove], fps: int, frames: int) -> list[dict[str, Any]]:
    """The description's tracks of ``camera`` for ``moves``: ``position`` and ``look_at``, one
    key per frame while the camera moves or follows a moving object (``linear``: the easing is
    in the keys), none while it holds still; none at all for a still camera. ``ValueError``
    for a move that cannot be made."""
    poses = camera_poses(params, world, moves, fps, frames)
    rounded = [(_vector(p.position), _vector(p.look_at)) for p in poses]
    times = [n for n, value in enumerate(rounded)
             if value != (rounded[n - 1] if n > 0 else value) or value != (rounded[n + 1] if n + 1 < len(rounded) else value)]
    if not times:
        return []
    return [
        {"target": "camera", "property": prop, "easing": "linear",
         "keys": [{"t": round(n / fps, 6), "value": rounded[n][k]} for n in times]}
        for k, prop in enumerate(("position", "look_at"))
    ]


__all__ = ["CAMERA_MOVES", "EASINGS", "CameraMove", "CameraState", "MovePath", "Pose", "Ref", "camera_poses", "camera_problems", "camera_tracks", "check_3d_scene", "ease", "follow", "move_path", "start_pose", "start_state"]
