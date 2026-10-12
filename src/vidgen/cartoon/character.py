"""Cartoon characters as named vector parts with pivots (DESIGN.md §69).

A :class:`Character` is a ``VGroup`` of parts (``head``, ``eyes``, ``brows``, ``mouth``, ``body``,
``arm_left``, ``arm_right``, optional ``legs`` and ``accessory``). Each part has one or more named
shapes, a pivot, a parent and a draw order. Parts are drawn in *character units*: the origin is
the point between the feet, ``y`` points up and 1 is the top of the character.

The character keeps the rest shapes and a :class:`PartPose` per part (angle, scale, shift,
shape). :meth:`Character.refresh` redraws every part from its rest shape: the part's pose about
its pivot, then its parent's (so the head carries the eyes), then the mirror for ``facing:
left``, then the placement on screen. The placement is read from an invisible anchor
(``submobjects[0]``) that Manim's own ``shift`` / ``scale`` / ``move_to`` move with the parts,
so a pose set after a move lands where the character is.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from manim import PI, Arc, Circle, Ellipse, Line, RoundedRectangle, VGroup, VMobject

from vidgen.config import CharacterEntry
from vidgen.errors import VidgenError
from vidgen.helpers import resolve_color
from vidgen.theme import Theme

#: Every part name, in the order used to break draw-order ties.
PART_NAMES: tuple[str, ...] = ("body", "legs", "arm_left", "arm_right", "head", "eyes", "brows", "mouth", "accessory")
#: Parts every character has; ``legs`` and ``accessory`` are optional.
REQUIRED_PARTS: tuple[str, ...] = ("body", "arm_left", "arm_right", "head", "eyes", "brows", "mouth")
#: The part each part hangs from (moves with); ``body`` is the root.
DEFAULT_PARENTS: dict[str, str | None] = {
    "body": None, "legs": "body", "arm_left": "body", "arm_right": "body", "head": "body",
    "eyes": "head", "brows": "head", "mouth": "head", "accessory": "head",
}
#: Default draw order (low first). Facing right, ``arm_right`` is the far arm (behind the body).
DEFAULT_DRAW_ORDER: dict[str, int] = {
    "arm_right": 10, "legs": 20, "body": 30, "arm_left": 40, "head": 50,
    "eyes": 60, "mouth": 60, "brows": 70, "accessory": 80,
}
FACINGS: tuple[str, ...] = ("right", "left")
#: Outline width of the basic figure (Manim stroke width).
OUTLINE_WIDTH = 4.0
#: Side of the anchor triangle in character units (small, so it stays inside the figure's box).
_ANCHOR_SIDE = 0.05


@dataclass(frozen=True)
class PartPose:
    """How one part is posed relative to its rest shape: ``angle`` in degrees counterclockwise
    about the pivot (as drawn facing right), ``scale`` (x, y) about the pivot, ``shift`` in
    character units, ``shape`` the name of the shape shown (``None``: the part's first shape)."""

    angle: float = 0.0
    scale: tuple[float, float] = (1.0, 1.0)
    shift: tuple[float, float] = (0.0, 0.0)
    shape: str | None = None

    def matrix(self, pivot: np.ndarray) -> np.ndarray:
        """The 3x3 affine matrix of this pose for a part pivoting at ``pivot`` (x, y)."""
        cos, sin = math.cos(math.radians(self.angle)), math.sin(math.radians(self.angle))
        sx, sy = self.scale
        linear = np.array([[cos * sx, -sin * sy], [sin * sx, cos * sy]])
        out = np.eye(3)
        out[:2, :2] = linear
        out[:2, 2] = pivot - linear @ pivot + np.asarray(self.shift, dtype=float)
        return out


@dataclass(frozen=True)
class CharacterState:
    """A snapshot of a character's pose: which way it faces and every part's :class:`PartPose`."""

    facing: str
    parts: dict[str, PartPose] = field(default_factory=dict)


@dataclass(frozen=True)
class CharacterPart:
    """One part as drawn at rest, in character units: its ``shapes`` (name -> drawing; the first
    is shown at rest), its ``pivot`` (x, y), its ``parent`` (``None``: :data:`DEFAULT_PARENTS`)
    and its draw ``order`` (``None``: :data:`DEFAULT_DRAW_ORDER`)."""

    name: str
    shapes: Mapping[str, VMobject]
    pivot: tuple[float, float]
    parent: str | None = None
    order: int | None = None


def _known(names: Iterable[str]) -> str:
    return ", ".join(names)


def _check_parts(specs: Mapping[str, CharacterPart], who: str) -> dict[str, str | None]:
    """The parent of each part; raises :class:`VidgenError` for unknown, missing or badly linked parts."""
    unknown = [n for n in specs if n not in PART_NAMES]
    if unknown:
        raise VidgenError(f"character '{who}': unknown part(s) {_known(unknown)} (parts: {_known(PART_NAMES)})")
    missing = [n for n in REQUIRED_PARTS if n not in specs]
    if missing:
        raise VidgenError(f"character '{who}': missing part(s) {_known(missing)}")
    parents: dict[str, str | None] = {}
    for name, spec in specs.items():
        if not spec.shapes:
            raise VidgenError(f"character '{who}': part '{name}' has no shapes")
        parent = spec.parent if spec.parent is not None else DEFAULT_PARENTS[name]
        if name == "body":
            parent = None
        elif parent not in specs:
            raise VidgenError(f"character '{who}': part '{name}' hangs from '{parent}', which the character does not have")
        parents[name] = parent
    for name in parents:
        seen = {name}
        parent = parents[name]
        while parent is not None:
            if parent in seen:
                raise VidgenError(f"character '{who}': part '{name}' hangs from itself through '{parent}'")
            seen.add(parent)
            parent = parents[parent]
    return parents


def _apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    out = np.array(points, dtype=float)
    out[:, :2] = points[:, :2] @ matrix[:2, :2].T + matrix[:2, 2]
    return out


class Character(VGroup):
    """A rigged cartoon character (see the module docstring). ``height`` is the character's
    height in Manim units (1 character unit); the feet start at the origin.

    ``parts`` maps each part name to its live ``VGroup`` (one child: the shape shown).
    """

    def __init__(
        self,
        parts: Iterable[CharacterPart],
        *,
        name: str = "character",
        height: float = 3.0,
        facing: str = "right",
        voice: str | None = None,
    ) -> None:
        super().__init__()
        specs: dict[str, CharacterPart] = {}
        for spec in parts:
            if spec.name in specs:
                raise VidgenError(f"character '{name}': part '{spec.name}' given twice")
            specs[spec.name] = spec
        self._parents = _check_parts(specs, name)
        if height <= 0:
            raise VidgenError(f"character '{name}': height must be positive, got {height}")
        self.name = name
        self.voice = voice
        self.facing = self._checked_facing(facing)
        self._shapes = {n: {k: v.copy() for k, v in s.shapes.items()} for n, s in specs.items()}
        self._pivots = {n: np.array(s.pivot, dtype=float) for n, s in specs.items()}
        self._order = sorted(
            specs,
            key=lambda n: (specs[n].order if specs[n].order is not None else DEFAULT_DRAW_ORDER[n], PART_NAMES.index(n)),
        )
        self._tree_order = sorted(specs, key=self._depth)
        self._poses = {n: PartPose() for n in specs}
        self._anchor = VMobject(fill_opacity=0, stroke_width=0, stroke_opacity=0)
        side = _ANCHOR_SIDE * height
        self._anchor.set_points(np.array([[0, 0, 0], [side, 0, 0], [0, side, 0], [0, side, 0]], dtype=float))
        self.parts: dict[str, VGroup] = {}
        for part_name in self._order:
            self.parts[part_name] = VGroup(next(iter(self._shapes[part_name].values())).copy())
        self.add(self._anchor, *(self.parts[n] for n in self._order))
        self.refresh()

    # ----- queries --------------------------------------------------------------------------

    @property
    def draw_order(self) -> list[str]:
        """Part names from the back to the front."""
        return list(self._order)

    def has_part(self, part: str) -> bool:
        """True if the character has ``part``."""
        return part in self._shapes

    def parent_of(self, part: str) -> str | None:
        """The part ``part`` hangs from (``None`` for ``body``)."""
        return self._parents[self._part_name(part)]

    def shape_names(self, part: str) -> list[str]:
        """The names of ``part``'s shapes; the first is its rest shape."""
        return list(self._shapes[self._part_name(part)])

    def pose_of(self, part: str) -> PartPose:
        """``part``'s current :class:`PartPose`."""
        return self._poses[self._part_name(part)]

    def state(self) -> CharacterState:
        """A snapshot of the facing and every part's pose (for :meth:`set_state`)."""
        return CharacterState(self.facing, dict(self._poses))

    def feet(self) -> np.ndarray:
        """The point between the feet on screen (the character's origin)."""
        return np.array(self._anchor.points[0], dtype=float)

    def pivot(self, part: str) -> np.ndarray:
        """Where ``part``'s pivot is on screen now (it moves with the part's shift and parents)."""
        name = self._part_name(part)
        parent = self._parents[name]
        world = self._world()[parent] if parent is not None else np.eye(3)
        local = self._pivots[name] + np.asarray(self._poses[name].shift, dtype=float)
        x, y, _ = self._screen() @ world @ np.array([local[0], local[1], 1.0])
        return np.array([x, y, 0.0])

    # ----- changes --------------------------------------------------------------------------

    def set_part(
        self,
        part: str,
        *,
        angle: float | None = None,
        scale: float | tuple[float, float] | None = None,
        shift: tuple[float, float] | None = None,
        shape: str | None = None,
    ) -> Character:
        """Pose ``part`` about its pivot: ``angle`` in degrees counterclockwise (as drawn facing
        right), ``scale`` (one factor or x, y), ``shift`` in character units, ``shape`` a name of
        :meth:`shape_names`. Values not given keep the current pose. Its child parts follow; the
        other parts do not move."""
        name = self._part_name(part)
        pose = self._poses[name]
        changes: dict[str, Any] = {}
        if angle is not None:
            changes["angle"] = float(angle)
        if scale is not None:
            changes["scale"] = (float(scale), float(scale)) if isinstance(scale, (int, float)) else (float(scale[0]), float(scale[1]))
        if shift is not None:
            changes["shift"] = (float(shift[0]), float(shift[1]))
        if shape is not None:
            if shape not in self._shapes[name]:
                raise VidgenError(f"character '{self.name}': part '{name}' has no shape '{shape}' (shapes: {_known(self._shapes[name])})")
            changes["shape"] = shape
        self._set_pose(name, replace(pose, **changes))
        return self.refresh()

    def swap(self, part: str, shape: str) -> Character:
        """Show ``part``'s shape ``shape`` (e.g. a mouth shape); same as ``set_part(part, shape=...)``."""
        return self.set_part(part, shape=shape)

    def reset(self, part: str | None = None) -> Character:
        """Put ``part`` (default: every part) back to its rest pose and shape."""
        for name in [self._part_name(part)] if part is not None else list(self._poses):
            self._set_pose(name, PartPose())
        return self.refresh()

    def face(self, direction: str) -> Character:
        """Face ``right`` or ``left``: facing left is the mirror image of the whole character
        about the vertical line through its feet."""
        self.facing = self._checked_facing(direction)
        return self.refresh()

    def turn(self) -> Character:
        """Face the other way."""
        return self.face("left" if self.facing == "right" else "right")

    def set_state(self, state: CharacterState) -> Character:
        """Apply a :meth:`state` snapshot (parts it does not name keep their pose)."""
        self.facing = self._checked_facing(state.facing)
        for part, pose in state.parts.items():
            self._set_pose(self._part_name(part), pose)
        return self.refresh()

    def refresh(self) -> Character:
        """Redraw every part's points from its rest shape, pose, parents, facing and placement.
        Styles (colour, opacity) of the live parts are kept."""
        screen = self._screen()
        world = self._world()
        for name, slot in self.parts.items():
            matrix = screen @ world[name]
            rest = self._shapes[name][self._shape_name(name)]
            for live, source in zip(slot.family_members_with_points(), rest.family_members_with_points()):
                live.points = _apply(matrix, source.points)
        return self

    # ----- internals ------------------------------------------------------------------------

    def _part_name(self, part: str) -> str:
        if part not in self._shapes:
            raise VidgenError(f"character '{self.name}' has no part '{part}' (parts: {_known(self._order)})")
        return part

    @staticmethod
    def _checked_facing(direction: str) -> str:
        if direction not in FACINGS:
            raise VidgenError(f"facing must be right or left, not {direction!r}")
        return direction

    def _depth(self, part: str) -> int:
        depth, parent = 0, self._parents[part]
        while parent is not None:
            depth, parent = depth + 1, self._parents[parent]
        return depth

    def _shape_name(self, part: str) -> str:
        return self._poses[part].shape or next(iter(self._shapes[part]))

    def _set_pose(self, part: str, pose: PartPose) -> None:
        if pose.shape is not None and pose.shape not in self._shapes[part]:
            raise VidgenError(f"character '{self.name}': part '{part}' has no shape '{pose.shape}' (shapes: {_known(self._shapes[part])})")
        before = self._shape_name(part)
        self._poses[part] = pose
        if self._shape_name(part) != before:
            self.parts[part].submobjects = [self._shapes[part][self._shape_name(part)].copy()]

    def _world(self) -> dict[str, np.ndarray]:
        """Each part's matrix in character units: its pose about its pivot, then its parents'."""
        world: dict[str, np.ndarray] = {}
        for name in self._tree_order:
            local = self._poses[name].matrix(self._pivots[name])
            parent = self._parents[name]
            world[name] = local if parent is None else world[parent] @ local
        return world

    def _screen(self) -> np.ndarray:
        """Character units -> screen: the mirror for ``facing: left``, then the anchor's placement."""
        p0, p1, p2 = (np.asarray(p, dtype=float) for p in self._anchor.points[:3])
        placement = np.eye(3)
        placement[:2, 0] = (p1 - p0)[:2] / _ANCHOR_SIDE
        placement[:2, 1] = (p2 - p0)[:2] / _ANCHOR_SIDE
        placement[:2, 2] = p0[:2]
        mirror = np.diag([-1.0 if self.facing == "left" else 1.0, 1.0, 1.0])
        return placement @ mirror


# ----- the basic figure ---------------------------------------------------------------------


def _outlined(mob: VMobject, fill: str, outline: str) -> VMobject:
    return mob.set_fill(fill, opacity=1).set_stroke(outline, width=OUTLINE_WIDTH)


def _arm(side: float, clothes: str, skin: str, outline: str) -> VGroup:
    sleeve = _outlined(RoundedRectangle(width=0.08, height=0.26, corner_radius=0.035).move_to([side * 0.2, 0.43, 0]), clothes, outline)
    hand = _outlined(Circle(radius=0.045).move_to([side * 0.2, 0.3, 0]), skin, outline)
    return VGroup(sleeve, hand)


def basic_parts(colors: Mapping[str, str]) -> list[CharacterPart]:
    """The parts of the basic figure (a round head on an oval body, two arms, two legs; facing a
    little to the right) in character units. ``colors`` maps ``skin``, ``clothes``, ``outline``
    and ``features`` to Manim colours. Eyes have the shapes ``open`` and ``closed``, the mouth
    ``smile`` and ``open``."""
    skin, clothes, outline, features = (colors[k] for k in ("skin", "clothes", "outline", "features"))
    face_x = 0.025
    legs = VGroup(
        *(_outlined(RoundedRectangle(width=0.08, height=0.24, corner_radius=0.035).move_to([x, 0.12, 0]), clothes, outline) for x in (-0.07, 0.07))
    )
    body = _outlined(Ellipse(width=0.4, height=0.44).move_to([0, 0.4, 0]), clothes, outline)
    head = _outlined(Circle(radius=0.2).move_to([0, 0.8, 0]), skin, outline)
    eye_xs = (face_x - 0.07, face_x + 0.07)
    open_eyes = VGroup(*(Ellipse(width=0.05, height=0.075).move_to([x, 0.83, 0]).set_fill(features, opacity=1).set_stroke(width=0) for x in eye_xs))
    closed_eyes = VGroup(*(Line([x - 0.03, 0.825, 0], [x + 0.03, 0.825, 0]).set_stroke(features, width=OUTLINE_WIDTH) for x in eye_xs))
    brows = VGroup(*(Line([x - 0.035, 0.895, 0], [x + 0.035, 0.905, 0]).set_stroke(features, width=OUTLINE_WIDTH) for x in eye_xs))
    smile = Arc(radius=0.06, start_angle=PI * 1.2, angle=PI * 0.6, arc_center=[face_x, 0.76, 0]).set_stroke(features, width=OUTLINE_WIDTH)
    open_mouth = Ellipse(width=0.09, height=0.07).move_to([face_x, 0.71, 0]).set_fill(features, opacity=1).set_stroke(width=0)
    return [
        CharacterPart("legs", {"default": legs}, (0.0, 0.22)),
        CharacterPart("body", {"default": body}, (0.0, 0.2)),
        CharacterPart("arm_left", {"default": _arm(1.0, clothes, skin, outline)}, (0.2, 0.54)),
        CharacterPart("arm_right", {"default": _arm(-1.0, clothes, skin, outline)}, (-0.2, 0.54)),
        CharacterPart("head", {"default": head}, (0.0, 0.6)),
        CharacterPart("eyes", {"open": open_eyes, "closed": closed_eyes}, (face_x, 0.83)),
        CharacterPart("brows", {"default": brows}, (face_x, 0.9)),
        CharacterPart("mouth", {"smile": smile, "open": open_mouth}, (face_x, 0.72)),
    ]


def build_character(entry: CharacterEntry, *, theme: Theme | None = None, height: float = 3.0, facing: str = "right") -> Character:
    """The :class:`Character` of a ``characters:`` entry, its colours resolved in ``theme``
    (default: the current theme). The feet start at the origin."""
    colors = {part: resolve_color(value, theme) for part, value in entry.colors.model_dump().items()}
    return Character(basic_parts(colors), name=entry.name, height=height, facing=facing, voice=entry.voice)


def character(name: str, *, height: float = 3.0, facing: str = "right") -> Character:
    """The character ``name`` of the active project's ``characters:``, ``height`` Manim units
    tall, feet at the origin. Unknown names raise :class:`VidgenError` with suggestions."""
    from vidgen.cartoon.cast import find_character
    from vidgen.runtime import current_project, current_theme

    entry = find_character(current_project().config, name)
    return build_character(entry, theme=current_theme(), height=height, facing=facing)


__all__ = [
    "Character",
    "CharacterPart",
    "CharacterState",
    "PartPose",
    "PART_NAMES",
    "basic_parts",
    "build_character",
    "character",
]
