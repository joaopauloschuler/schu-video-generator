"""The YAML side of a ``3d`` scene (DESIGN.md §114.2): the params models for its camera, light and
objects, checked with did-you-mean messages."""

from __future__ import annotations

import re

from pydantic import Field, field_validator, model_validator

from vidgen.cellworld.model import did_you_mean
from vidgen.scene import SceneParams, ThemeColor
from vidgen.translation import TranslatableStr

#: Shapes an object can have.
SHAPES: tuple[str, ...] = ("box",)
#: Names a scene description keeps for itself (a track's target ``camera``).
RESERVED_IDS: frozenset[str] = frozenset({"camera"})
_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

#: A point or a size in scene units (y is up), or angles in degrees.
Vec3 = tuple[float, float, float]


class Camera3D(SceneParams):
    """The fixed camera: where it stands, the point it looks at and how wide it sees."""

    position: Vec3 = (3.0, 2.5, 5.0)
    """[x, y, z] of the camera (scene units, y up)."""
    look_at: Vec3 = (0.0, 0.0, 0.0)
    """[x, y, z] the camera looks at (the middle of the frame)."""
    fov: float = Field(40.0, ge=10.0, le=120.0)
    """Field of view in degrees across the frame's shorter side (the same subject fills 16:9 and 9:16 alike)."""

    @model_validator(mode="after")
    def _apart(self) -> Camera3D:
        if self.position == self.look_at:
            raise ValueError("look_at: the camera cannot look at the point it stands on")
        return self


class Light3D(SceneParams):
    """The default light: an even ambient part plus a sun (parallel rays from one direction)."""

    ambient: float = Field(0.5, ge=0.0, le=5.0)
    """Strength of the even light from everywhere (0 = none)."""
    sun: float = Field(2.5, ge=0.0, le=10.0)
    """Strength of the sun (0 = none)."""
    sun_from: Vec3 = (-2.0, 6.0, 4.0)
    """[x, y, z]: the sun shines from this direction towards the origin."""
    color: ThemeColor = "#ffffff"
    """Colour of both lights."""

    @field_validator("sun_from")
    @classmethod
    def _not_zero(cls, v: Vec3) -> Vec3:
        if not any(v):
            raise ValueError("sun_from: [0, 0, 0] is no direction")
        return v


class Object3D(SceneParams):
    """One object of the scene, named by its ``id``."""

    id: str
    """Name of the object (letters, digits, _ and -); later actions and guide passes use it."""
    shape: str = "box"
    """box."""
    size: Vec3 = (1.0, 1.0, 1.0)
    """[width, height, depth] in scene units."""
    color: ThemeColor = "accent"
    """Colour (theme token or #hex)."""
    position: Vec3 = (0.0, 0.0, 0.0)
    """[x, y, z] of the object's centre."""
    rotation: Vec3 = (0.0, 0.0, 0.0)
    """[x, y, z] rotation in degrees (applied in that order)."""
    spin: Vec3 = (0.0, 0.0, 0.0)
    """[x, y, z] degrees per second it keeps turning through the scene (0 = still)."""

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError(f"id: {v!r} must start with a letter or _ and hold only letters, digits, _ and -")
        if v in RESERVED_IDS:
            raise ValueError(f"id: {v!r} is reserved; choose another name")
        return v

    @field_validator("shape")
    @classmethod
    def _shape(cls, v: str) -> str:
        if v not in SHAPES:
            raise ValueError(f"shape: unknown shape {v!r}{did_you_mean(v, SHAPES)} (shapes: {', '.join(SHAPES)})")
        return v

    @field_validator("size")
    @classmethod
    def _size(cls, v: Vec3) -> Vec3:
        if min(v) <= 0:
            raise ValueError(f"size: {list(v)} must be positive in every direction")
        return v


class Scene3DParams(SceneParams):
    """Params of the ``3d`` scene type."""

    title: TranslatableStr = ""
    """Heading over the 3D picture (on a plate at the top)."""
    background: ThemeColor | None = None
    """Colour behind the objects (theme token or #hex; default: the theme's background)."""
    camera: Camera3D = Field(default_factory=Camera3D)
    """The fixed camera: {position, look_at, fov}."""
    light: Light3D = Field(default_factory=Light3D)
    """The default light: {ambient, sun, sun_from, color}."""
    objects: list[Object3D] = Field(default_factory=list)
    """The objects: [{id, shape, size, color, position, rotation, spin}]."""

    @model_validator(mode="after")
    def _unique_ids(self) -> Scene3DParams:
        seen: set[str] = set()
        for k, obj in enumerate(self.objects):
            if obj.id in seen:
                raise ValueError(f"objects[{k}].id: {obj.id!r} is used twice; every object needs its own id")
            seen.add(obj.id)
        return self


__all__ = ["SHAPES", "Camera3D", "Light3D", "Object3D", "Scene3DParams", "Vec3"]
