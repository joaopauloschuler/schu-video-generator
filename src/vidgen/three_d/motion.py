"""Object actions of a ``3d`` scene (DESIGN.md §114.11): the beat actions ``object_move``,
``object_path``, ``object_rotate``, ``object_spin``, ``object_scale``, ``object_show``,
``object_hide``, ``object_highlight``, ``object_walk`` and ``object_face`` become
:class:`ObjectChange` s with a start and an end on the scene's clock; :func:`plan_motion` turns
them into per-frame values of five *channels* per object (``position``, ``rotation``, ``scale``,
``appear`` = [opacity, grow], ``glow`` = an emissive colour), which :class:`~vidgen.three_d.world.World`
reads (so the camera, arrows and lint follow a moving object) and :func:`object_tracks` writes
into the description, one key per frame while something changes.

A change starts from the value its channel has when it starts (the changes before it, in time
order); a change still running when the next one of the same channel of the same object starts
stops there. Highlights do not stop each other: the brightest glow wins. A change that needs
where another object is (walk to it, turn to face it) reads it at its own start, from the changes
that started before it, so the order is exact. No manim, no browser.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.three_d.camera import ease
from vidgen.three_d.spec import FLOOR_ID, Scene3DParams, Vec3

if TYPE_CHECKING:
    from vidgen.three_d.world import World

#: The kinds of change (the action ``object_<kind>``).
OBJECT_CHANGES: tuple[str, ...] = ("move", "path", "rotate", "spin", "scale", "show", "hide", "highlight", "walk", "face")
#: What a change sets, per object: its channels.
CHANNELS: tuple[str, ...] = ("position", "rotation", "scale", "appear", "glow")
#: How ``object_show`` / ``object_hide`` bring an object in or take it away.
APPEAR_STYLES: tuple[str, ...] = ("fade", "grow")
#: A highlight's glow comes up and goes down over this long (seconds; at most half its length).
GLOW_RAMP = 0.25
#: A walk's turn takes this long for half a turn (seconds; less for a smaller turn).
TURN_SECONDS = 0.4
#: A walking stand-in's step length and how high it bobs, as shares of its height.
STEP_SHARE, BOB_SHARE = 0.38, 0.025
#: A walk to an object stops this far (scene units) from the edge of its sphere.
WALK_GAP = 0.15


@dataclass(frozen=True)
class ObjectChange:
    """One change of an object (``target``) from ``start`` to ``end`` (seconds of the scene's
    clock; ``end=None``: the change's own length, a walk's distance over its ``speed``).

    ``kind`` is one of :data:`OBJECT_CHANGES`; the fields it reads: ``move`` — to ``point`` or
    by ``by`` (in its parent's frame); ``path`` — through ``points`` (a smooth curve, or straight
    lines with ``smooth=False``), turning to face along it with ``turn``; ``rotate`` — to
    ``angles`` or by ``by`` (degrees, XYZ); ``spin`` — ``turns`` full turns about ``axis``;
    ``scale`` — to ``factor`` times its size; ``show`` / ``hide`` — ``style`` fade or grow;
    ``highlight`` — glow in ``color`` (``#rrggbb``) at ``strength``; ``walk`` — turn to and walk
    to ``point`` (``[x, z]``: it keeps its height) or ``toward`` an object (stopping in front of
    it) at ``speed`` units per second; ``face`` — turn about the vertical to face ``toward`` (an
    object id) or ``point``."""

    kind: str
    target: str
    start: float = 0.0
    end: float | None = 1.0
    easing: str = "smooth"
    point: tuple[float, ...] | None = None
    toward: str | None = None
    by: Vec3 | None = None
    angles: Vec3 | None = None
    factor: Vec3 | None = None
    points: tuple[Vec3, ...] = ()
    smooth: bool = True
    turn: bool = False
    turns: float = 1.0
    axis: str = "y"
    style: str = "fade"
    color: str = "#ffcc00"
    strength: float = 0.6
    speed: float = 1.4


Value = Callable[[int], np.ndarray]


@dataclass
class _Segment:
    """A change of one channel: from frame ``first`` to ``end`` (its own length), cut at ``stop``."""

    first: int
    end: int
    value: Value
    stop: int = field(default=-1)

    def __post_init__(self) -> None:
        if self.stop < 0:
            self.stop = self.end


def _wrap(degrees: float) -> float:
    """``degrees`` turned into -180..180 (the shorter way round)."""
    return (degrees + 180.0) % 360.0 - 180.0


def hex_rgb(color: str) -> np.ndarray:
    """``#rrggbb`` as three numbers 0..1."""
    digits = color.lstrip("#")
    return np.array([int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4)])


class Motion:
    """The channels of every object of validated ``params`` over ``frames`` frames at ``fps``:
    their rest values, and the changes planned so far (:meth:`add`)."""

    def __init__(self, params: Scene3DParams, fps: int, frames: int) -> None:
        self.fps, self.frames = int(fps), max(int(frames), 1)
        self.params = params
        self._rest: dict[tuple[str, str], np.ndarray] = {}
        self._segments: dict[tuple[str, str], list[_Segment]] = {}
        self._heights: dict[str, float] = {}
        objects = [(FLOOR_ID, (0.0, params.floor.y, 0.0), (0.0, 0.0, 0.0), True)] if params.floor is not None else []
        objects += [(o.id, o.position, o.rotation, o.visible) for o in params.objects]
        for obj_id, position, rotation, visible in objects:
            self._rest[(obj_id, "position")] = np.array(position, dtype=float)
            self._rest[(obj_id, "rotation")] = np.array(rotation, dtype=float)
            self._rest[(obj_id, "scale")] = np.ones(3)
            self._rest[(obj_id, "appear")] = np.array([1.0 if visible else 0.0, 1.0])
            self._rest[(obj_id, "glow")] = np.zeros(3)
        for o in params.objects:
            self._heights[o.id] = o.resolved_size()[1]

    # ----- reading -------------------------------------------------------------------------------

    def frame(self, t: float) -> int:
        """The frame showing scene time ``t`` (clamped to the clip)."""
        return min(max(int(round(t * self.fps)), 0), self.frames - 1)

    def changed(self, obj_id: str, channel: str) -> bool:
        """Whether any change sets ``channel`` of ``obj_id``."""
        return bool(self._segments.get((obj_id, channel)))

    def value(self, obj_id: str, channel: str, n: int) -> np.ndarray:
        """``channel`` of ``obj_id`` at frame ``n``."""
        segments = self._segments.get((obj_id, channel), [])
        if channel == "glow":
            lit = [s.value(n) for s in segments if s.first <= n <= s.stop]
            return np.max(lit, axis=0) if lit else self._rest[(obj_id, channel)]
        current = None
        for s in segments:
            if s.first <= n:
                current = s
        if current is None:
            return self._rest[(obj_id, channel)]
        return current.value(min(n, current.stop))

    def at(self, obj_id: str, channel: str, t: float) -> np.ndarray:
        """``channel`` of ``obj_id`` at scene time ``t``."""
        return self.value(obj_id, channel, self.frame(t))

    def scale(self, obj_id: str, n: int) -> np.ndarray:
        """The object's scale at frame ``n``: its ``scale`` channel times its grow."""
        return self.value(obj_id, "scale", n) * self.value(obj_id, "appear", n)[1]

    def opacity(self, obj_id: str, n: int) -> float:
        """The object's own opacity at frame ``n`` (its parents' multiply it)."""
        return float(self.value(obj_id, "appear", n)[0])

    # ----- planning ------------------------------------------------------------------------------

    def _add(self, obj_id: str, channel: str, segment: _Segment) -> None:
        segments = self._segments.setdefault((obj_id, channel), [])
        if channel != "glow":
            for s in segments:
                if s.first <= segment.first:
                    s.stop = min(s.stop, segment.first)
        segments.append(segment)

    def _frames(self, change: ObjectChange, natural: float | None = None) -> tuple[int, int]:
        """First and end frame of ``change`` (``natural``: its own length in seconds when it has no end)."""
        last = self.frames - 1
        first = min(int(round(change.start * self.fps)), last)
        seconds = (change.end - change.start) if change.end is not None else (natural if natural is not None else 1.0)
        return first, max(int(round((change.start + seconds) * self.fps)), first + 1)

    def add(self, change: ObjectChange, world: World) -> None:
        """Plan ``change`` from the values its channels have when it starts; ``ValueError`` when
        it cannot be made."""
        kind, obj = change.kind, change.target
        if (obj, "position") not in self._rest:
            raise ValueError(f"no object {obj!r}")
        handler = getattr(self, f"_plan_{kind}", None)
        if handler is None:
            raise ValueError(f"unknown object change {kind!r}")
        handler(change, world)
        world.forget()

    def _eased(self, change: ObjectChange, first: int, end: int) -> Callable[[int], float]:
        return lambda n: ease(change.easing, (n - first) / (end - first))

    def _plan_move(self, change: ObjectChange, world: World) -> None:
        first, end = self._frames(change)
        v0 = self.value(change.target, "position", first)
        v1 = np.array(change.point, dtype=float) if change.point is not None else v0 + np.array(change.by or (0.0, 0.0, 0.0))
        u = self._eased(change, first, end)
        self._add(change.target, "position", _Segment(first, end, lambda n: v0 + (v1 - v0) * u(n)))

    def _plan_path(self, change: ObjectChange, world: World) -> None:
        first, end = self._frames(change)
        v0 = self.value(change.target, "position", first)
        curve = _curve([v0, *(np.array(p, dtype=float) for p in change.points)], change.smooth)
        lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(curve, axis=0), axis=1))])
        total = float(lengths[-1])
        if total < 1e-9:
            raise ValueError("points: the path does not go anywhere from where the object is")
        u = self._eased(change, first, end)

        def along(n: int) -> np.ndarray:
            s = u(n) * total
            k = min(int(np.searchsorted(lengths, s, side="right")) - 1, len(curve) - 2)
            share = (s - lengths[k]) / max(lengths[k + 1] - lengths[k], 1e-12)
            return curve[k] + (curve[k + 1] - curve[k]) * share

        self._add(change.target, "position", _Segment(first, end, along))
        if change.turn:
            r0 = self.value(change.target, "rotation", first)
            yaws = np.degrees(np.unwrap(np.arctan2(*np.diff(curve, axis=0)[:, [0, 2]].T)))
            yaws = r0[1] + _wrap(yaws[0] - r0[1]) + (yaws - yaws[0])

            def heading(n: int) -> np.ndarray:
                s = u(n) * total
                k = min(max(int(np.searchsorted(lengths, s, side="right")) - 1, 0), len(yaws) - 1)
                return np.array([r0[0], yaws[k], r0[2]])

            self._add(change.target, "rotation", _Segment(first, end, heading))

    def _plan_rotate(self, change: ObjectChange, world: World) -> None:
        first, end = self._frames(change)
        r0 = self.value(change.target, "rotation", first)
        r1 = np.array(change.angles, dtype=float) if change.angles is not None else r0 + np.array(change.by or (0.0, 0.0, 0.0))
        u = self._eased(change, first, end)
        self._add(change.target, "rotation", _Segment(first, end, lambda n: r0 + (r1 - r0) * u(n)))

    def _plan_spin(self, change: ObjectChange, world: World) -> None:
        first, end = self._frames(change)
        r0 = self.value(change.target, "rotation", first)
        r1 = r0 + np.array([360.0 * change.turns if change.axis == a else 0.0 for a in "xyz"])
        u = self._eased(change, first, end)
        self._add(change.target, "rotation", _Segment(first, end, lambda n: r0 + (r1 - r0) * u(n)))

    def _plan_scale(self, change: ObjectChange, world: World) -> None:
        first, end = self._frames(change)
        s0 = self.value(change.target, "scale", first)
        s1 = np.array(change.factor or (1.0, 1.0, 1.0), dtype=float)
        u = self._eased(change, first, end)
        self._add(change.target, "scale", _Segment(first, end, lambda n: s0 + (s1 - s0) * u(n)))

    def _plan_appear(self, change: ObjectChange, show: bool) -> None:
        first, end = self._frames(change)
        a0 = self.value(change.target, "appear", first)
        u = self._eased(change, first, end)
        if change.style == "grow":
            if show:
                value: Value = lambda n: np.array([1.0, u(n)])
            else:
                value = lambda n: np.array([0.0, 1.0]) if n >= end else np.array([a0[0], 1.0 - u(n)])
        else:
            goal = 1.0 if show else 0.0
            value = lambda n: np.array([a0[0] + (goal - a0[0]) * u(n), a0[1]])
        self._add(change.target, "appear", _Segment(first, end, value))

    def _plan_show(self, change: ObjectChange, world: World) -> None:
        self._plan_appear(change, True)

    def _plan_hide(self, change: ObjectChange, world: World) -> None:
        self._plan_appear(change, False)

    def _plan_highlight(self, change: ObjectChange, world: World) -> None:
        first, end = self._frames(change)
        ramp = max(min(int(round(GLOW_RAMP * self.fps)), (end - first) // 2), 1)
        glow = hex_rgb(change.color) * change.strength
        self._add(change.target, "glow", _Segment(first, end, lambda n: glow * min(1.0, (n - first) / ramp, (end - n) / ramp)))

    def _local_point(self, obj: str, world: World, t: float, toward: str | None, point: tuple[float, ...] | None) -> np.ndarray:
        """Where ``toward`` (an object) or ``point`` is at ``t``, in ``obj``'s parent's frame
        (a 2-number point is ``[x, z]`` at ``obj``'s height)."""
        if toward is not None:
            parent = world.objects[obj].parent
            centre = world.follow(toward, t)[0]
            inverse = np.linalg.inv(world.matrix(parent, t)) if parent else np.eye(4)
            return (inverse @ np.append(centre, 1.0))[:3]
        assert point is not None
        if len(point) == 2:
            here = self.at(obj, "position", t)
            return np.array([point[0], here[1], point[1]])
        return np.array(point, dtype=float)

    def _turn_segment(self, obj: str, first: int, frames: int, yaw: float, easing: str) -> float:
        """Turn ``obj`` about the vertical to ``yaw`` (degrees) from frame ``first`` over
        ``frames`` frames, the shorter way round; returns how far it turns."""
        r0 = self.value(obj, "rotation", first)
        delta = _wrap(yaw - r0[1])
        if abs(delta) > 1e-6:
            r1 = r0 + np.array([0.0, delta, 0.0])
            end = first + max(frames, 1)
            self._add(obj, "rotation", _Segment(first, end, lambda n: r0 + (r1 - r0) * ease(easing, (n - first) / (end - first))))
        return delta

    def _plan_face(self, change: ObjectChange, world: World) -> None:
        first, end = self._frames(change)
        t = first / self.fps
        here = self.value(change.target, "position", first)
        goal = self._local_point(change.target, world, t, change.toward, change.point)
        dx, dz = goal[0] - here[0], goal[2] - here[2]
        if math.hypot(dx, dz) < 1e-6:
            return   # standing on it: nothing to turn to
        self._turn_segment(change.target, first, end - first, math.degrees(math.atan2(dx, dz)), change.easing)

    def _plan_walk(self, change: ObjectChange, world: World) -> None:
        obj = change.target
        last = self.frames - 1
        first = min(int(round(change.start * self.fps)), last)
        t = first / self.fps
        here = self.value(obj, "position", first)
        goal = self._local_point(obj, world, t, change.toward, change.point)
        flat = np.array([goal[0] - here[0], 0.0, goal[2] - here[2]])
        distance = float(np.linalg.norm(flat))
        if change.toward is not None:   # stop in front of it
            gap = world.follow(change.toward, t)[1] + world.objects[obj].size[0] / 2 + WALK_GAP
            distance = max(distance - gap, 0.0)
        if distance < 1e-6:
            return
        direction = flat / float(np.linalg.norm(flat))
        yaw = math.degrees(math.atan2(direction[0], direction[2]))
        r0 = self.value(obj, "rotation", first)
        turn_s = TURN_SECONDS * abs(_wrap(yaw - r0[1])) / 180.0
        natural = turn_s + distance / change.speed
        _, end = self._frames(change, natural)
        seconds = (end - first) / self.fps
        turn_frames = int(round(min(turn_s, 0.25 * seconds) * self.fps))
        self._turn_segment(obj, first, turn_frames, yaw, "smooth")
        height = self._heights.get(obj, 1.0)
        steps = max(1, round(distance / (STEP_SHARE * height)))
        bob = BOB_SHARE * height
        start = first + turn_frames
        goal_point = here + direction * distance

        def walking(n: int) -> np.ndarray:
            if n <= start:
                return here
            u = ease(change.easing, (n - start) / max(end - start, 1))
            return here + (goal_point - here) * u + np.array([0.0, bob * abs(math.sin(math.pi * steps * u)), 0.0])

        self._add(obj, "position", _Segment(first, end, walking))


def _curve(points: Sequence[np.ndarray], smooth: bool, samples: int = 24) -> np.ndarray:
    """The polyline through ``points``: straight, or a Catmull-Rom curve (``samples`` points per stretch)."""
    pts = [p for k, p in enumerate(points) if k == 0 or np.linalg.norm(p - points[k - 1]) > 1e-9]
    if not smooth or len(pts) < 3:
        return np.array(pts, dtype=float) if len(pts) > 1 else np.array([pts[0], pts[0]], dtype=float)
    padded = [pts[0], *pts, pts[-1]]
    out = []
    for k in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[k - 1 : k + 3]
        for s in np.linspace(0.0, 1.0, samples, endpoint=False):
            out.append(0.5 * (2 * p1 + (p2 - p0) * s + (2 * p0 - 5 * p1 + 4 * p2 - p3) * s * s + (3 * p1 - p0 - 3 * p2 + p3) * s ** 3))
    out.append(pts[-1])
    return np.array(out, dtype=float)


def plan_motion(params: Scene3DParams, world: World, changes: Sequence[ObjectChange], fps: int, frames: int) -> Motion:
    """The motion of ``params``' objects with ``changes`` planned in time order, attached to
    ``world`` (which then places the objects as they move). ``ValueError`` for a change that
    cannot be made."""
    motion = Motion(params, fps, frames)
    world.attach(motion)
    for change in sorted(changes, key=lambda c: c.start):
        motion.add(change, world)
    return motion


def held_keys(values: Sequence[Sequence[float]], fps: int) -> list[dict[str, Any]]:
    """Track keys ``{t, value}`` from one value per frame, keeping a frame only where the value
    changes (a value held over frames keeps its first and last frame, a still one none)."""
    rounded = [[round(float(c), 6) for c in v] for v in values]
    keys = []
    for n, value in enumerate(rounded):
        before = rounded[n - 1] if n > 0 else value
        after = rounded[n + 1] if n + 1 < len(rounded) else value
        if value != before or value != after:
            keys.append({"t": round(n / fps, 6), "value": value})
    return keys


def _track(target: str, prop: str, keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"target": target, "property": prop, "easing": "linear", "keys": keys}] if keys else []


def object_tracks(world: World, duration: float) -> list[dict[str, Any]]:
    """The description's tracks of the objects of ``world`` (with its motion): a 2-key
    ``rotation`` track for a ``spin`` alone, else one key per frame while a ``position``,
    ``rotation``, ``scale``, ``opacity`` or ``emissive`` (the highlight's glow) changes; an
    arrow pointing at an object that moves gets ``position``, ``rotation`` and ``length``."""
    motion = world.motion
    tracks: list[dict[str, Any]] = []
    for placed in world.objects.values():
        obj = placed.id
        spin = any(placed.spin)
        if motion is None:
            if spin:
                tracks += _track(obj, "rotation", _spin_keys(placed.rotation, placed.spin, duration))
            continue
        fps, frames = motion.fps, motion.frames
        times = [n / fps for n in range(frames)]
        if world.points_somewhere(obj):
            poses = [world.arrow_pose(obj, t) for t in times]
            tracks += _track(obj, "position", held_keys([p[0] for p in poses], fps))
            tracks += _track(obj, "rotation", held_keys([p[1] for p in poses], fps))
            tracks += _track(obj, "length", held_keys([[p[2]] for p in poses], fps))
        else:
            if motion.changed(obj, "position"):
                tracks += _track(obj, "position", held_keys([motion.value(obj, "position", n) for n in range(frames)], fps))
            if motion.changed(obj, "rotation"):
                spun = np.array(placed.spin)
                tracks += _track(obj, "rotation", held_keys([motion.value(obj, "rotation", n) + spun * t for n, t in enumerate(times)], fps))
            elif spin:
                tracks += _track(obj, "rotation", _spin_keys(placed.rotation, placed.spin, duration))
        if motion.changed(obj, "scale") or motion.changed(obj, "appear"):
            tracks += _track(obj, "scale", held_keys([motion.scale(obj, n) for n in range(frames)], fps))
        if motion.changed(obj, "appear"):
            tracks += _track(obj, "opacity", held_keys([[motion.opacity(obj, n)] for n in range(frames)], fps))
        if motion.changed(obj, "glow"):
            tracks += _track(obj, "emissive", held_keys([motion.value(obj, "glow", n) for n in range(frames)], fps))
    return tracks


def _spin_keys(rotation: Vec3, spin: Vec3, duration: float) -> list[dict[str, Any]]:
    """A spin alone: two keys, from the rest rotation to where it has turned at the end."""
    end = [r + s * duration for r, s in zip(rotation, spin)]
    return [{"t": 0.0, "value": [round(float(c), 6) for c in rotation]}, {"t": round(duration, 6), "value": [round(float(c), 6) for c in end]}]


__all__ = ["APPEAR_STYLES", "CHANNELS", "OBJECT_CHANGES", "Motion", "ObjectChange", "held_keys", "hex_rgb", "object_tracks", "plan_motion"]
