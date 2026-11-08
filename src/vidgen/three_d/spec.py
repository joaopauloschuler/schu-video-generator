"""The YAML side of a ``3d`` scene (DESIGN.md §114.2, §114.7, §114.11): the params models for its
camera, light, floor and objects (shapes, labels, arrows, groups, character stand-ins), checked
with did-you-mean messages."""

from __future__ import annotations

import re
from pydantic import Field, field_validator, model_validator

from vidgen.cellworld.model import did_you_mean
from vidgen.scene import SceneParams, ThemeColor
from vidgen.translation import TranslatableStr

#: Shapes an object can have (``group`` draws nothing: its children move with it; ``standin`` is a
#: character stand-in: a capsule with a nose showing where it faces, and a name above it).
SHAPES: tuple[str, ...] = ("box", "sphere", "cylinder", "cone", "torus", "plane", "arrow", "label", "group", "standin")
#: Names a scene description keeps for itself (a track's target ``camera``).
RESERVED_IDS: frozenset[str] = frozenset({"camera"})
#: The id of the scene's ``floor`` (taken when the scene has one).
FLOOR_ID = "floor"
_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

#: A point or a size in scene units (y is up), or angles in degrees.
Vec3 = tuple[float, float, float]

#: Each shape's size when ``size`` is not given: ``[width, height, depth]`` (a ``plane`` is flat,
#: an ``arrow`` is ``[thickness, length, thickness]``, a ``label`` its text height).
DEFAULT_SIZES: dict[str, Vec3] = {
    "box": (1.0, 1.0, 1.0),
    "sphere": (1.0, 1.0, 1.0),
    "cylinder": (1.0, 1.0, 1.0),
    "cone": (1.0, 1.0, 1.0),
    "torus": (1.0, 0.25, 1.0),
    "plane": (4.0, 0.0, 4.0),
    "arrow": (0.08, 1.0, 0.08),
    "label": (0.0, 0.3, 0.0),
    "group": (0.0, 0.0, 0.0),
    "standin": (0.5, 1.6, 0.5),
}
#: Each shape's colour when ``color`` is not given.
DEFAULT_COLORS: dict[str, str] = {"label": "text"}
DEFAULT_COLOR = "accent"


def check_id(value: str, what: str = "id") -> str:
    """``value`` if it is a usable object id; ``ValueError`` naming ``what`` otherwise."""
    if not _ID.match(value):
        raise ValueError(f"{what}: {value!r} must start with a letter or _ and hold only letters, digits, _ and -")
    if value in RESERVED_IDS:
        raise ValueError(f"{what}: {value!r} is reserved; choose another name")
    return value


class Camera3D(SceneParams):
    """The camera at the scene's start: where it stands, what it looks at and how wide it sees
    (beat actions ``camera_orbit``, ``camera_dolly``... move it from there)."""

    position: Vec3 = (3.0, 2.5, 5.0)
    """[x, y, z] of the camera (scene units, y up)."""
    look_at: Vec3 | str = (0.0, 0.0, 0.0)
    """[x, y, z] the camera looks at (the middle of the frame), or the id of an object (its centre)."""
    fov: float = Field(40.0, ge=10.0, le=120.0)
    """Field of view in degrees across the frame's shorter side (the same subject fills 16:9 and 9:16 alike)."""

    @model_validator(mode="after")
    def _apart(self) -> Camera3D:
        if isinstance(self.look_at, str):
            check_id(self.look_at, "look_at")
        elif self.position == self.look_at:
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


class Floor3D(SceneParams):
    """A square floor (a ``plane`` with id ``floor``) the objects stand on."""

    size: float = Field(12.0, gt=0)
    """Width and depth in scene units."""
    color: ThemeColor = "surface"
    """Colour (theme token or #hex)."""
    y: float = 0.0
    """Height of the floor (objects of height h stand on it at y + h / 2)."""


class Object3D(SceneParams):
    """One object of the scene, named by its ``id``."""

    id: str
    """Name of the object (letters, digits, _ and -); actions, groups and guide passes use it."""
    shape: str = "box"
    """box, sphere, cylinder, cone, torus, plane, arrow, label (text that faces the camera), group (draws nothing; its children move with it) or standin (a character stand-in: a capsule with a nose showing where it faces, +z unturned)."""
    size: float | Vec3 | None = None
    """[width, height, depth] in scene units, or one number for all three (a plane: [width, -, depth]; an arrow: [thickness, length, thickness]; a torus: [outer width, thickness, outer depth]; a label: its text height, one number). Default 1 (a plane 4, a torus [1, 0.25, 1], an arrow [0.08, 1, 0.08], a label 0.3, a stand-in [0.5, 1.6, 0.5])."""
    color: ThemeColor | None = None
    """Colour (theme token or #hex); default accent (a label: text)."""
    position: Vec3 = (0.0, 0.0, 0.0)
    """[x, y, z] of the object's centre (an arrow with `to`: its tail), in its parent's frame."""
    rotation: Vec3 = (0.0, 0.0, 0.0)
    """[x, y, z] rotation in degrees (applied in that order)."""
    spin: Vec3 = (0.0, 0.0, 0.0)
    """[x, y, z] degrees per second it keeps turning through the scene (0 = still); a group's children turn with it."""
    parent: str | None = None
    """The id of a group (or any object) written before this one: this object's position and rotation are then in its frame, and it moves with it."""
    text: TranslatableStr | None = None
    """A label's text."""
    to: Vec3 | str | None = None
    """An arrow's tip: [x, y, z] (in its parent's frame), or the id of an object it points at (it stops at its edge and follows it when it moves)."""
    visible: bool = True
    """false: hidden at the start (the action object_show brings it in)."""
    name: TranslatableStr | None = None
    """A stand-in's name, shown above its head."""
    voice: str | None = None
    """The voice (from voices) that speaks a stand-in's lines (default: its id); lint checks that a stand-in is on screen while it speaks."""
    screen_size: bool = False
    """A label keeps the size on screen it has at the start, however near or far the camera goes (default: it gets smaller with distance)."""

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return check_id(v)

    @field_validator("shape")
    @classmethod
    def _shape(cls, v: str) -> str:
        if v not in SHAPES:
            raise ValueError(f"shape: unknown shape {v!r}{did_you_mean(v, SHAPES)} (shapes: {', '.join(SHAPES)})")
        return v

    @model_validator(mode="after")
    def _fits_shape(self) -> Object3D:
        shape = self.shape
        if self.text is not None and shape != "label":
            raise ValueError("text: only a label has a text (shape: label)")
        if shape == "label" and not (self.text or "").strip():
            raise ValueError("text: a label needs a text")
        if self.name is not None and shape != "standin":
            raise ValueError("name: only a stand-in has a name (shape: standin); a label shows text (shape: label, text: ...)")
        if self.voice is not None and shape != "standin":
            raise ValueError("voice: only a stand-in speaks (shape: standin)")
        if self.screen_size and shape != "label":
            raise ValueError("screen_size: only a label keeps its size on screen (shape: label)")
        if shape == "standin" and isinstance(self.size, (int, float)):
            raise ValueError("size: a stand-in's size is [width, height, depth] (e.g. [0.5, 1.6, 0.5])")
        if self.to is not None and shape != "arrow":
            raise ValueError("to: only an arrow points somewhere (shape: arrow)")
        if self.to is not None and any(self.rotation):
            raise ValueError("rotation: an arrow with `to` points there; leave rotation out")
        if isinstance(self.to, str):
            check_id(self.to, "to")
            if self.to == self.id:
                raise ValueError("to: an arrow cannot point at itself")
        if shape == "group" and (self.size is not None or self.color is not None):
            raise ValueError(f"{'size' if self.size is not None else 'color'}: a group draws nothing; give its children a size and colour")
        if shape == "label" and isinstance(self.size, tuple):
            raise ValueError("size: a label's size is its text height, one number (e.g. size: 0.3)")
        if isinstance(self.size, tuple) and min(self.size) <= 0:
            raise ValueError(f"size: {list(self.size)} must be positive in every direction")
        if isinstance(self.size, (int, float)) and self.size <= 0:
            raise ValueError(f"size: {self.size:g} must be positive")
        if shape == "standin":
            width, height, depth = self.resolved_size()
            if height <= max(width, depth):
                raise ValueError(f"size: a stand-in must be taller ({height:g}) than wide and deep")
        if shape == "torus":
            width, thick, depth = self.resolved_size()
            if thick >= min(width, depth):
                raise ValueError(f"size: a torus's thickness ({thick:g}) must be less than its outer width and depth")
        if self.parent is not None:
            check_id(self.parent, "parent")
            if self.parent == self.id:
                raise ValueError("parent: an object cannot be its own parent")
        return self

    def resolved_size(self) -> Vec3:
        """``size`` as ``[width, height, depth]`` (the shape's default when not given; a plane's
        height and a label's width and depth are 0)."""
        if self.size is None:
            return DEFAULT_SIZES[self.shape]
        if isinstance(self.size, tuple):
            w, h, d = self.size
        else:
            w = h = d = float(self.size)
        if self.shape == "plane":
            return (w, 0.0, d)
        if self.shape == "label":
            return (0.0, h, 0.0)
        return (w, h, d)

    def color_token(self) -> str:
        """``color``, or the shape's default colour token."""
        return self.color or DEFAULT_COLORS.get(self.shape, DEFAULT_COLOR)


class Scene3DParams(SceneParams):
    """Params of the ``3d`` scene type."""

    title: TranslatableStr = ""
    """Heading over the 3D picture (on a plate at the top)."""
    background: ThemeColor | None = None
    """Colour behind the objects (theme token or #hex; default: the theme's background)."""
    camera: Camera3D = Field(default_factory=Camera3D)
    """The camera at the start: {position, look_at, fov}; beat actions (camera_orbit, camera_dolly, camera_fly_to, camera_look_at, camera_move) move it."""
    light: Light3D = Field(default_factory=Light3D)
    """The default light: {ambient, sun, sun_from, color}."""
    floor: Floor3D | bool | None = None
    """A square floor the objects stand on: true, or {size, color, y} (an object with id floor)."""
    objects: list[Object3D] = Field(default_factory=list)
    """The objects: [{id, shape, size, color, position, rotation, spin, parent, text, to, visible, name, voice, screen_size}]; object actions (object_move, object_walk...) move them."""
    guide_passes: bool | list[str] = False
    """Also draw guide passes of the 3D picture (same frames, camera and timing; labels left out), stored beside its clip: true (all), or a list of depth (near white, far dark), outline (edges like a line drawing), mask (each object one flat colour, with a colour table); also `vidgen render --guide-passes`."""

    @field_validator("guide_passes")
    @classmethod
    def _guide_passes(cls, v: bool | list[str]) -> bool | list[str]:
        from vidgen.three_d.passes import parse_passes

        return list(parse_passes(v)) if isinstance(v, list) else v

    @field_validator("floor")
    @classmethod
    def _floor(cls, v: Floor3D | bool | None) -> Floor3D | None:
        if isinstance(v, bool):
            return Floor3D() if v else None
        return v

    @model_validator(mode="after")
    def _ids_and_references(self) -> Scene3DParams:
        seen: list[str] = [FLOOR_ID] if self.floor is not None else []
        for k, obj in enumerate(self.objects):
            where = f"objects[{k}]"
            if obj.id in seen:
                what = "the floor's id (floor: is set)" if obj.id == FLOOR_ID and self.floor is not None else "used twice"
                raise ValueError(f"{where}.id: {obj.id!r} is {what}; every object needs its own id")
            if obj.parent is not None and obj.parent not in seen:
                later = any(o.id == obj.parent for o in self.objects[k + 1 :])
                hint = f"; write '{obj.parent}' before '{obj.id}'" if later else did_you_mean(obj.parent, seen)
                raise ValueError(f"{where}.parent: no object {obj.parent!r} before this one{hint}")
            seen.append(obj.id)
        ids = self.object_ids()
        for k, obj in enumerate(self.objects):
            if isinstance(obj.to, str) and obj.to not in ids:
                raise ValueError(f"objects[{k}].to: no object {obj.to!r}{did_you_mean(obj.to, ids)}")
            if isinstance(obj.to, str) and obj.id in self.ancestors(obj.to):
                raise ValueError(f"objects[{k}].to: '{obj.to}' moves with the arrow '{obj.id}' (its parent); an arrow cannot point at its own part")
        if isinstance(self.camera.look_at, str) and self.camera.look_at not in ids:
            raise ValueError(f"camera.look_at: no object {self.camera.look_at!r}{did_you_mean(self.camera.look_at, ids)}")
        return self

    def ancestors(self, object_id: str) -> list[str]:
        """The parents of ``object_id``, nearest first."""
        parents = {o.id: o.parent for o in self.objects}
        out: list[str] = []
        current = parents.get(object_id)
        while current is not None and current not in out:
            out.append(current)
            current = parents.get(current)
        return out

    def passes(self) -> tuple[str, ...]:
        """The guide passes ``guide_passes`` asks for (DESIGN.md §114.14), in drawing order."""
        from vidgen.three_d.passes import parse_passes

        return parse_passes(self.guide_passes)

    def object(self, object_id: str) -> Object3D | None:
        """The object with ``object_id`` (``None`` for the floor or an unknown id)."""
        return next((o for o in self.objects if o.id == object_id), None)

    def object_ids(self) -> list[str]:
        """The ids of the scene's objects (the floor's first, when it has one)."""
        return ([FLOOR_ID] if self.floor is not None else []) + [o.id for o in self.objects]


__all__ = ["DEFAULT_SIZES", "FLOOR_ID", "SHAPES", "Camera3D", "Floor3D", "Light3D", "Object3D", "Scene3DParams", "Vec3", "check_id"]
