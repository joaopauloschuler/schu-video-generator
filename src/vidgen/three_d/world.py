"""Where a ``3d`` scene's objects are (DESIGN.md §114.7, §114.11): their world transforms at a
time (their object actions through an attached :class:`~vidgen.three_d.motion.Motion`; a
group's spin and moves carry its children), and the centre and size of an object or group, for
the camera moves (``camera_fly_to``), ``look_at`` an object, arrows pointing at one and lint.
No manim, no browser: the page applies the same transforms (three.js, Euler order XYZ, T·R·S)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from vidgen.three_d.spec import FLOOR_ID, Scene3DParams, Vec3

if TYPE_CHECKING:
    from vidgen.three_d.motion import Motion


@dataclass(frozen=True)
class Placed:
    """One object as the page builds it: its parent, shape, size and pose in the parent's frame."""

    id: str
    shape: str
    parent: str | None
    size: Vec3
    position: Vec3
    rotation: Vec3
    spin: Vec3


def rotation_matrix(degrees: Vec3) -> np.ndarray:
    """The 3x3 rotation of Euler angles in degrees, order XYZ (three.js: ``Rx @ Ry @ Rz``)."""
    x, y, z = (math.radians(a) for a in degrees)
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rx @ ry @ rz


def euler_xyz(matrix: np.ndarray) -> Vec3:
    """Euler angles in degrees (order XYZ) of a 3x3 rotation (three.js ``setFromRotationMatrix``)."""
    m = matrix
    y = math.asin(max(-1.0, min(1.0, float(m[0, 2]))))
    if abs(m[0, 2]) < 0.9999999:
        x, z = math.atan2(-m[1, 2], m[2, 2]), math.atan2(-m[0, 1], m[0, 0])
    else:
        x, z = math.atan2(m[2, 1], m[1, 1]), 0.0
    return (math.degrees(x), math.degrees(y), math.degrees(z))


def shape_radius(shape: str, size: Vec3, text: str = "") -> float:
    """Radius of a sphere around an object of ``shape`` and ``size`` at its centre (a label's
    width estimated from its text)."""
    w, h, d = size
    if shape == "sphere":
        return max(size) / 2
    if shape in ("cylinder", "cone", "torus", "standin"):
        return math.hypot(max(w, d) / 2, h / 2)
    if shape == "label":
        return math.hypot(0.62 * h * max(len(text), 1) / 2, h / 2)
    if shape == "arrow":
        return h / 2
    return math.hypot(w, h, d) / 2


class World:
    """The objects of validated ``3d`` params (the floor first), with their transforms; with a
    :class:`~vidgen.three_d.motion.Motion` attached (:meth:`attach`) they move as it says."""

    def __init__(self, params: Scene3DParams) -> None:
        self.objects: dict[str, Placed] = {}
        self.motion: Motion | None = None
        self._texts: dict[str, str] = {}
        self._to: dict[str, Vec3 | str] = {}
        self._tails: dict[str, Vec3] = {}
        self._matrices: dict[tuple[str, float], np.ndarray] = {}
        self._rest_focus: dict[str, tuple[np.ndarray, float]] = {}
        self._busy: set[str] = set()
        if params.floor is not None:
            f = params.floor
            self.objects[FLOOR_ID] = Placed(FLOOR_ID, "plane", None, (f.size, 0.0, f.size), (0.0, f.y, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        for obj in params.objects:
            self.objects[obj.id] = Placed(obj.id, obj.shape, obj.parent, obj.resolved_size(), obj.position, obj.rotation, obj.spin)
            self._texts[obj.id] = obj.text or ""
            if obj.to is not None:
                self._to[obj.id] = obj.to
                self._tails[obj.id] = obj.position
        for obj in params.objects:   # arrows with `to`, once every object they may point at is placed
            if obj.to is not None:
                position, rotation, length = self.arrow_pose(obj.id, 0.0)
                size = self.objects[obj.id].size
                self.objects[obj.id] = Placed(obj.id, obj.shape, obj.parent, (size[0], length, size[2]), position, rotation, obj.spin)

    def attach(self, motion: Motion) -> None:
        """Place the objects as ``motion`` moves them from now on (what :meth:`follow` carries
        along stays each object's sphere at rest)."""
        for object_id in self.objects:
            self.follow(object_id, 0.0)
        self.motion = motion
        self.forget()

    def forget(self) -> None:
        """Drop the transforms worked out so far (the motion changed)."""
        self._matrices.clear()

    def points_somewhere(self, object_id: str) -> bool:
        """Whether ``object_id`` is an arrow with ``to`` (its pose follows its tip)."""
        return object_id in self._to

    def arrow_pose(self, object_id: str, t: float) -> tuple[Vec3, Vec3, float]:
        """Centre, rotation and length at ``t`` of an arrow from its ``position`` (tail, as it
        moves) to ``to``, in its parent's frame; an object as ``to`` is met at the edge of its
        sphere and followed as it moves."""
        to = self._to[object_id]
        p = self.objects[object_id]
        tail = self.motion.at(object_id, "position", t) if self.motion is not None else np.array(self._tails[object_id], dtype=float)
        if isinstance(to, str):
            if object_id in self._busy:
                raise ValueError(f"objects '{object_id}'.to: arrows point at each other in a loop; point one at a point")
            self._busy.add(object_id)
            try:
                centre, radius = self.follow(to, t)
                parent = self.matrix(p.parent, t) if p.parent else np.eye(4)
            finally:
                self._busy.discard(object_id)
            target = (np.linalg.inv(parent) @ np.append(centre, 1.0))[:3]
            gap = np.linalg.norm(target - tail)
            tip = target - (target - tail) / gap * min(radius, 0.9 * gap) if gap > 0 else target
        else:
            tip = np.array(to, dtype=float)
        along = tip - tail
        length = float(np.linalg.norm(along))
        if length < 1e-6:
            raise ValueError(f"objects '{object_id}'.to: the arrow's tip is at its tail ({[round(float(c), 3) for c in tail]}); move one of them")
        return tuple(float(c) for c in (tail + tip) / 2), euler_xyz(_turn_up_to(along / length)), length

    def follow(self, object_id: str, t: float) -> tuple[np.ndarray, float]:
        """The centre and radius of ``object_id``'s sphere at rest, carried along as the object
        moves (its origin's path), so a turning group does not wobble what follows it and an
        object growing in keeps its full size."""
        if object_id not in self._rest_focus:
            self._rest_focus[object_id] = self.focus(object_id, 0.0)
        centre, radius = self._rest_focus[object_id]
        return centre + self.position(object_id, t) - self.position(object_id, 0.0), radius

    def matrix(self, object_id: str, t: float) -> np.ndarray:
        """The 4x4 world matrix of ``object_id`` at ``t`` seconds (its motion and spin, and its parents')."""
        key = (object_id, float(t))
        cached = self._matrices.get(key)
        if cached is not None:
            return cached
        p = self.objects[object_id]
        motion = self.motion
        if object_id in self._to:
            position, rotation, _ = self.arrow_pose(object_id, t)
        elif motion is not None:
            position = tuple(motion.at(object_id, "position", t))
            rotation = tuple(motion.at(object_id, "rotation", t) + np.array(p.spin) * t)
        else:
            position, rotation = p.position, tuple(r + s * t for r, s in zip(p.rotation, p.spin))
        local = np.eye(4)
        local[:3, :3] = rotation_matrix(rotation)
        if motion is not None:
            local[:3, :3] = local[:3, :3] @ np.diag(motion.scale(object_id, motion.frame(t)))
        local[:3, 3] = position
        out = (self.matrix(p.parent, t) @ local) if p.parent else local
        self._matrices[key] = out
        return out

    def position(self, object_id: str, t: float) -> np.ndarray:
        """Where the centre of ``object_id`` is at ``t`` seconds (world coordinates)."""
        return self.matrix(object_id, t)[:3, 3].copy()

    def opacity(self, object_id: str, t: float) -> float:
        """How visible ``object_id`` is at ``t`` (0..1: its own and its parents' opacity)."""
        if self.motion is None:
            return 1.0
        n = self.motion.frame(t)
        out, current = 1.0, object_id
        while current is not None:
            out *= self.motion.opacity(current, n)
            current = self.objects[current].parent
        return out

    def focus(self, object_id: str, t: float) -> tuple[np.ndarray, float]:
        """The centre and radius of a sphere around ``object_id`` at ``t`` (a group: around
        all its descendants)."""
        parts = []
        for i, p in self.objects.items():
            if p.shape != "group" and self.within(i, object_id):
                m = self.matrix(i, t)
                stretch = float(np.max(np.linalg.norm(m[:3, :3], axis=0)))
                parts.append((m[:3, 3].copy(), shape_radius(p.shape, p.size, self._texts.get(i, "")) * stretch))
        if not parts:
            return self.position(object_id, t), 0.5
        low = np.min([c - r for c, r in parts], axis=0)
        high = np.max([c + r for c, r in parts], axis=0)
        centre = (low + high) / 2
        return centre, max(float(np.linalg.norm(c - centre)) + r for c, r in parts)

    def within(self, object_id: str, ancestor: str) -> bool:
        """Whether ``object_id`` is ``ancestor`` or one of its descendants."""
        current: str | None = object_id
        while current is not None:
            if current == ancestor:
                return True
            current = self.objects[current].parent
        return False


def _turn_up_to(direction: np.ndarray) -> np.ndarray:
    """The rotation that turns +y onto the unit vector ``direction``."""
    up = np.array([0.0, 1.0, 0.0])
    axis = np.cross(up, direction)
    sin, cos = float(np.linalg.norm(axis)), float(np.dot(up, direction))
    if sin < 1e-9:
        return np.eye(3) if cos > 0 else np.diag([1.0, -1.0, -1.0])
    k = axis / sin
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + sin * kx + (1 - cos) * (kx @ kx)


__all__ = ["Placed", "World", "euler_xyz", "rotation_matrix", "shape_radius"]
