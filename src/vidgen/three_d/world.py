"""Where a ``3d`` scene's objects are (DESIGN.md §114.7): their world transforms at a time (a
group's spin carries its children), and the centre and size of an object or group, for the
camera moves (``camera_fly_to``), ``look_at`` an object and arrows pointing at one. No manim,
no browser: the page applies the same transforms (three.js, Euler order XYZ)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from vidgen.three_d.spec import FLOOR_ID, Object3D, Scene3DParams, Vec3


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
    if shape in ("cylinder", "cone", "torus"):
        return math.hypot(max(w, d) / 2, h / 2)
    if shape == "label":
        return math.hypot(0.62 * h * max(len(text), 1) / 2, h / 2)
    if shape == "arrow":
        return h / 2
    return math.hypot(w, h, d) / 2


class World:
    """The objects of validated ``3d`` params (the floor first), with their transforms."""

    def __init__(self, params: Scene3DParams) -> None:
        self.objects: dict[str, Placed] = {}
        self._texts: dict[str, str] = {}
        if params.floor is not None:
            f = params.floor
            self.objects[FLOOR_ID] = Placed(FLOOR_ID, "plane", None, (f.size, 0.0, f.size), (0.0, f.y, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        for obj in params.objects:
            self.objects[obj.id] = Placed(obj.id, obj.shape, obj.parent, obj.resolved_size(), obj.position, obj.rotation, obj.spin)
            self._texts[obj.id] = obj.text or ""
        for obj in params.objects:   # arrows with `to` once every object they may point at is placed
            if obj.to is not None:
                position, rotation, length = self._arrow_pose(obj)
                size = self.objects[obj.id].size
                self.objects[obj.id] = Placed(obj.id, obj.shape, obj.parent, (size[0], length, size[2]), position, rotation, obj.spin)

    def _arrow_pose(self, obj: Object3D) -> tuple[Vec3, Vec3, float]:
        """Centre, rotation and length of an arrow from its ``position`` (tail) to ``to``, in
        its parent's frame; an object as ``to`` is met at the edge of its sphere."""
        tail = np.array(obj.position, dtype=float)
        if isinstance(obj.to, str):
            centre, radius = self.focus(obj.to, 0.0)
            parent = self.matrix(obj.parent, 0.0) if obj.parent else np.eye(4)
            target = (np.linalg.inv(parent) @ np.append(centre, 1.0))[:3]
            gap = np.linalg.norm(target - tail)
            tip = target - (target - tail) / gap * min(radius, 0.9 * gap) if gap > 0 else target
        else:
            tip = np.array(obj.to, dtype=float)
        along = tip - tail
        length = float(np.linalg.norm(along))
        if length < 1e-6:
            raise ValueError(f"objects '{obj.id}'.to: the arrow's tip is at its tail ({list(obj.position)}); move one of them")
        return tuple((tail + tip) / 2), euler_xyz(_turn_up_to(along / length)), length

    def matrix(self, object_id: str, t: float) -> np.ndarray:
        """The 4x4 world matrix of ``object_id`` at ``t`` seconds (its spin and its parents')."""
        p = self.objects[object_id]
        local = np.eye(4)
        local[:3, :3] = rotation_matrix(tuple(r + s * t for r, s in zip(p.rotation, p.spin)))
        local[:3, 3] = p.position
        return (self.matrix(p.parent, t) @ local) if p.parent else local

    def position(self, object_id: str, t: float) -> np.ndarray:
        """Where the centre of ``object_id`` is at ``t`` seconds (world coordinates)."""
        return self.matrix(object_id, t)[:3, 3].copy()

    def focus(self, object_id: str, t: float) -> tuple[np.ndarray, float]:
        """The centre and radius of a sphere around ``object_id`` at ``t`` (a group: around
        all its descendants)."""
        parts = [(self.position(i, t), shape_radius(p.shape, p.size, self._texts.get(i, "")))
                 for i, p in self.objects.items() if p.shape != "group" and self._within(i, object_id)]
        if not parts:
            return self.position(object_id, t), 0.5
        low = np.min([c - r for c, r in parts], axis=0)
        high = np.max([c + r for c, r in parts], axis=0)
        centre = (low + high) / 2
        return centre, max(float(np.linalg.norm(c - centre)) + r for c, r in parts)

    def _within(self, object_id: str, ancestor: str) -> bool:
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
