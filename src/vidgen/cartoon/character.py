"""Cartoon characters as named vector parts with pivots (DESIGN.md §69).

A :class:`Character` is a ``VGroup`` of parts (``head``, ``eyes``, ``brows``, ``mouth``, ``body``,
``arm_left``, ``arm_right``, optional ``legs`` and ``accessory``; arms and legs may come in two
segments, ``arm_left`` + ``arm_left_lower``, ``leg_left`` + ``leg_left_lower``, ...: §69.26).
Each part has one or more named shapes, a pivot, a parent and a draw order. Parts are drawn in
*character units*: the origin is the point between the feet, ``y`` points up and 1 is the top
of the character.

The character keeps the rest shapes and a :class:`PartPose` per part (angle, scale, shift,
shape). :meth:`Character.refresh` redraws every part from its rest shape: the part's pose about
its pivot, then its parent's (so the head carries the eyes), then the mirror for ``facing:
left``, then the placement on screen. The placement is read from an invisible anchor
(``submobjects[0]``) that Manim's own ``shift`` / ``scale`` / ``move_to`` move with the parts,
so a pose set after a move lands where the character is.
"""

from __future__ import annotations

import json
import math
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
from manim import VGroup, VMobject

from vidgen.cartoon.idle import IdleClock, breath_scale, idle_seed, sway_angle
from vidgen.cartoon.limbs import ELBOW_BEND, FEET, HANDS, KNEE_BEND, LIMBS, fold, limb_side, solve_two_bone, wrap_degrees
from vidgen.cartoon.motion import DEFAULT_MOTION, motion_strength, resolve_motion
from vidgen.cartoon.poses import KINDS, PoseTable, chosen_shape, find_entry, kind_parts, merged_table
from vidgen.cartoon.seating import LEAN_DEGREES, SEATED_LEGS_DEGREES, seated_sole
from vidgen.cartoon.visemes import VISEME_SHAPES, VISEMES, VisemeTrack
from vidgen.config import CharacterEntry, CharacterLook, PartPoseEntry
from vidgen.errors import VidgenError
from vidgen.helpers import resolve_color
from vidgen.theme import Theme

#: Every part name, in the order used to break draw-order ties (and in which a pose change
#: moves them). ``arm_left`` is the upper arm, ``arm_left_lower`` the forearm and hand;
#: ``legs`` is both legs in one piece, ``leg_left`` / ``leg_right`` (+ ``_lower``) one leg each.
PART_NAMES: tuple[str, ...] = (
    "body", "legs", "leg_left", "leg_left_lower", "leg_right", "leg_right_lower",
    "arm_left", "arm_left_lower", "arm_right", "arm_right_lower", "head", "eyes", "brows", "mouth", "accessory",
)
#: Parts every character has; the legs, the lower segments and ``accessory`` are optional.
REQUIRED_PARTS: tuple[str, ...] = ("body", "arm_left", "arm_right", "head", "eyes", "brows", "mouth")
#: The legs drawn one leg each; a character draws its legs either so or as one ``legs`` part.
SINGLE_LEG_PARTS: tuple[str, ...] = ("leg_left", "leg_left_lower", "leg_right", "leg_right_lower")
#: The part each part hangs from (moves with); ``body`` is the root. A default parent the
#: character lacks is replaced by its own parent (a forearm without its upper arm hangs from the body).
DEFAULT_PARENTS: dict[str, str | None] = {
    "body": None, "legs": "body", "leg_left": "body", "leg_left_lower": "leg_left", "leg_right": "body",
    "leg_right_lower": "leg_right", "arm_left": "body", "arm_left_lower": "arm_left", "arm_right": "body",
    "arm_right_lower": "arm_right", "head": "body", "eyes": "head", "brows": "head", "mouth": "head", "accessory": "head",
}
#: Default draw order (low first). Facing right, ``arm_right`` is the far arm (behind the body)
#: and ``leg_right`` the far leg; each lower segment is drawn over its upper one.
DEFAULT_DRAW_ORDER: dict[str, int] = {
    "arm_right": 10, "arm_right_lower": 11, "leg_right": 16, "leg_right_lower": 17, "legs": 20,
    "leg_left": 22, "leg_left_lower": 23, "body": 30, "arm_left": 40, "arm_left_lower": 41, "head": 50,
    "eyes": 60, "mouth": 60, "brows": 70, "accessory": 80,
}
FACINGS: tuple[str, ...] = ("right", "left")
#: Outline width of parts drawn for a character :data:`REFERENCE_HEIGHT` tall (Manim stroke width).
OUTLINE_WIDTH = 4.0
#: The height (Manim units) at which a character's strokes keep the widths its parts were drawn with.
REFERENCE_HEIGHT = 3.0
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


@dataclass
class _LipSync:
    """A running lip sync: the track, the seconds into it now and the clock giving them (``None``:
    advanced by each frame's time)."""

    track: VisemeTrack
    seconds: float
    clock: Callable[[], float] | None


@dataclass(frozen=True)
class CharacterPart:
    """One part as drawn at rest, in character units: its ``shapes`` (name -> drawing; the first
    is shown at rest), its ``pivot`` (x, y), its ``parent`` (``None``: :data:`DEFAULT_PARENTS`),
    its draw ``order`` (``None``: :data:`DEFAULT_DRAW_ORDER`) and, for the last segment of an arm
    or a leg, its ``end``: the hand or the foot's sole (``None``: the point of the limb's drawing
    farthest from the shoulder or hip)."""

    name: str
    shapes: Mapping[str, VMobject]
    pivot: tuple[float, float]
    parent: str | None = None
    order: int | None = None
    end: tuple[float, float] | None = None


@dataclass(frozen=True)
class _Limb:
    """An arm's or a leg's rest geometry in character units: the shoulder or hip (``root``), the
    elbow or knee (``joint``; half-way for a limb in one piece) and the hand or foot (``end``)."""

    root: np.ndarray
    joint: np.ndarray
    end: np.ndarray


def _known(names: Iterable[str]) -> str:
    return ", ".join(names)


def _check_parts(specs: Mapping[str, CharacterPart], who: str, required: Iterable[str]) -> dict[str, str | None]:
    """The parent of each part; raises :class:`VidgenError` for unknown, missing (of ``required``)
    or badly linked parts."""
    unknown = [n for n in specs if n not in PART_NAMES]
    if unknown:
        raise VidgenError(f"character '{who}': unknown part(s) {_known(unknown)} (parts: {_known(PART_NAMES)})")
    missing = [n for n in required if n not in specs]
    if missing:
        raise VidgenError(f"character '{who}': missing part(s) {_known(missing)}")
    single = [n for n in SINGLE_LEG_PARTS if n in specs]
    if "legs" in specs and single:
        raise VidgenError(
            f"character '{who}': part 'legs' and {_known(single)}: draw the legs as one part 'legs' "
            "or as leg_left / leg_right (each with an optional _lower), not both"
        )
    parents: dict[str, str | None] = {}
    for name, spec in specs.items():
        if not spec.shapes:
            raise VidgenError(f"character '{who}': part '{name}' has no shapes")
        parent = spec.parent
        if parent is None:
            parent = DEFAULT_PARENTS[name]
            while parent is not None and parent not in specs:
                parent = DEFAULT_PARENTS[parent]
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


def one_pixel_stroke() -> float:
    """The Manim stroke width of one pixel in the current Manim config (Cairo draws a stroke
    width ``w`` as ``w * 0.01`` frame units)."""
    from manim import config

    return 100.0 * float(config.frame_height) / float(config.pixel_height)


def scale_strokes(shape: VMobject, factor: float, floor: float) -> None:
    """Multiply the stroke widths of ``shape``'s family by ``factor``, keeping drawn strokes at
    least ``floor`` wide."""
    for member in shape.get_family():
        if isinstance(member, VMobject) and member.get_stroke_width() > 0:
            member.set_stroke(width=max(member.get_stroke_width() * factor, floor), family=False)


def shape_drawing(shape: VMobject) -> tuple[np.ndarray, ...]:
    """``shape`` as drawn: the points of each member of its family that has points, in family
    order (what a redraw transforms; the styles stay on the live copy)."""
    return tuple(np.array(member.points, dtype=float) for member in shape.family_members_with_points())


def _apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    out = np.array(points, dtype=float)
    out[:, :2] = points[:, :2] @ matrix[:2, :2].T + matrix[:2, 2]
    return out


class Character(VGroup):
    """A rigged cartoon character (see the module docstring). ``height`` is the character's
    height in Manim units (1 character unit); the feet start at the origin. Stroke widths scale
    with ``height`` (as drawn at :data:`REFERENCE_HEIGHT`), at least one pixel wide.
    ``required`` names the parts it must have (default :data:`REQUIRED_PARTS`; an imported SVG
    needs only ``body``, §69.2). ``poses`` / ``expressions`` are the character's own entries
    (name -> part -> :class:`~vidgen.config.PartPoseEntry`), added to the built-in tables (§69.3).
    ``motion`` is its ``cartoon_motion`` setting (``lively``, ``calm``, ``none``; §69.13), read by
    the animations of :mod:`vidgen.cartoon.transition`.

    ``parts`` maps each part name to its live ``VGroup``: one child per shape, in
    :meth:`shape_names` order, all kept for the character's life; the shapes not shown have no
    points (so Manim draws only the shown one). Its family never changes, so an animation that
    lists the character's family when it begins draws every frame what is shown, where it is
    (a swapped-out mouth is never left behind, DESIGN.md §69.22).
    """

    def __init__(
        self,
        parts: Iterable[CharacterPart],
        *,
        name: str = "character",
        height: float = 3.0,
        facing: str = "right",
        voice: str | None = None,
        required: Iterable[str] = REQUIRED_PARTS,
        poses: PoseTable | None = None,
        expressions: PoseTable | None = None,
        motion: str = DEFAULT_MOTION,
    ) -> None:
        super().__init__()
        try:
            motion_strength(motion)
        except ValueError as exc:
            raise VidgenError(f"character '{name}': {exc}") from None
        specs: dict[str, CharacterPart] = {}
        for spec in parts:
            if spec.name in specs:
                raise VidgenError(f"character '{name}': part '{spec.name}' given twice")
            specs[spec.name] = spec
        self._parents = _check_parts(specs, name, required)
        if height <= 0:
            raise VidgenError(f"character '{name}': height must be positive, got {height}")
        self.name = name
        self.voice = voice
        self.facing = self._checked_facing(facing)
        #: The ``cartoon_motion`` setting its animations use (anticipation, squash and stretch,
        #: overshoot, follow-through; DESIGN.md §69.13).
        self.motion = motion
        self._squash = (1.0, 1.0)  # the whole figure's scale about its feet (squash and stretch)
        self._own_entries: dict[str, PoseTable] = {"pose": dict(poses or {}), "expression": dict(expressions or {})}
        self._shapes = {n: {k: v.copy() for k, v in s.shapes.items()} for n, s in specs.items()}
        stroke_factor, stroke_floor = height / REFERENCE_HEIGHT, one_pixel_stroke()
        for shapes in self._shapes.values():
            for shape in shapes.values():
                scale_strokes(shape, stroke_factor, stroke_floor)
        # each shape's drawing as point arrays, so a redraw only transforms them (DESIGN.md §69.20)
        self._drawings = {n: {k: shape_drawing(v) for k, v in s.items()} for n, s in self._shapes.items()}
        #: part -> shape -> the members of that shape's live copy that are drawn (have points
        #: when shown), in the order of its drawing
        self._members: dict[str, dict[str, list[VMobject]]] = {}
        self._pivots = {n: np.array(s.pivot, dtype=float) for n, s in specs.items()}
        #: lower segments of limbs drawn in one piece: they have a pose (the joint's bend) but no
        #: shapes; the upper part shows the bend folded (:func:`~vidgen.cartoon.limbs.fold`)
        self._folded = {lower for upper, lower in LIMBS.items() if upper in specs and lower not in specs}
        self._limbs = {upper: self._limb_geometry(upper, specs) for upper in LIMBS if upper in specs}
        self._order = sorted(
            specs,
            key=lambda n: (specs[n].order if specs[n].order is not None else DEFAULT_DRAW_ORDER[n], PART_NAMES.index(n)),
        )
        self._tree_order = sorted(specs, key=self._depth)
        self._poses = {n: PartPose() for n in [*specs, *sorted(self._folded)]}
        self._overlays: dict[str, PartPose] = {}  # idle motion on top of the poses (:meth:`start_idle`)
        self._idle: IdleClock | None = None
        self._lip_sync: _LipSync | None = None  # the running lip sync (:meth:`lip_sync`)
        self._spoken: str | None = None  # the mouth shape lip sync shows over the pose's
        #: The beat in which the character's last walk ended (set by the walking actions; the
        #: layout dump records it for the ``walk_overlap`` lint rule), ``None`` before any walk.
        self.walked_in: str | None = None
        #: What its last ``look_at`` looked at (a target name or ``camera``; set by the action,
        #: recorded in the layout dump for the ``facing_away`` lint rule), ``None`` before any.
        self.looked_at: str | None = None
        #: ``enter`` or ``exit`` while a :class:`~vidgen.cartoon.transition.Walk` brings it in
        #: from off stage or takes it off (lint ``off_stage`` skips it then), else ``None``.
        self.passage: str | None = None
        #: The props in its hands (hand -> prop name; set by the prop actions, recorded in the
        #: layout dump as ``holding``), empty while it holds nothing (DESIGN.md §69.27).
        self.holding: dict[str, str] = {}
        #: The prop it sits on / leans on (set by ``sit_on`` / ``lean_on``, cleared by ``stand_up``;
        #: recorded in the layout dump), ``None`` while it stands (DESIGN.md §69.28).
        self.sitting_on: str | None = None
        self.leaning_on: str | None = None
        self._anchor = VMobject(fill_opacity=0, stroke_width=0, stroke_opacity=0)
        side = _ANCHOR_SIDE * height
        self._anchor.set_points(np.array([[0, 0, 0], [side, 0, 0], [0, side, 0], [0, side, 0]], dtype=float))
        self.parts: dict[str, VGroup] = {}
        for part_name in self._order:
            copies = {shape: drawing.copy() for shape, drawing in self._shapes[part_name].items()}
            self._members[part_name] = {shape: copy.family_members_with_points() for shape, copy in copies.items()}
            self.parts[part_name] = VGroup(*copies.values())
            for shape in list(copies)[1:]:  # the rest shape shows
                self._hide(part_name, shape)
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

    def shown_shape(self, part: str) -> str:
        """The name of ``part``'s shape on screen now (a blink's ``closed`` eyes included)."""
        return self._shape_name(self._part_name(part))

    def pose_of(self, part: str) -> PartPose:
        """``part``'s current :class:`PartPose` (also the lower segment of a limb drawn in one
        piece: its bend, shown folded)."""
        return self._poses[self._posed_name(part)]

    def state(self) -> CharacterState:
        """A snapshot of the facing and every part's pose (for :meth:`set_state`; with the lower
        segment of each limb drawn in one piece)."""
        return CharacterState(self.facing, dict(self._poses))

    def names(self, kind: str) -> list[str]:
        """The ``pose`` or ``expression`` names this character knows (built-in, then its own)."""
        return list(merged_table(kind, self._own_entries[kind]))

    def posed_state(self, pose: str | None = None, expression: str | None = None) -> CharacterState:
        """The current state with pose ``pose`` and / or expression ``expression`` applied (not
        drawn: pass it to :meth:`set_state` or :class:`~vidgen.cartoon.transition.PoseChange`).
        A pose sets every body part it does not name back to rest, an expression every face part.
        Parts the character lacks are skipped; a shape the character lacks leaves the rest shape."""
        parts = dict(self._poses)
        for kind, name in zip(KINDS, (pose, expression)):
            if name is None:
                continue
            entry = find_entry(kind, name, self._own_entries[kind], self.name)
            for part in kind_parts(kind):
                if part in self._poses:
                    parts[part] = self._entry_pose(part, entry.get(part))
        return CharacterState(self.facing, parts)

    @property
    def character_height(self) -> float:
        """The character's height in Manim units now (one character unit): the ``height`` it was
        made with, times any Manim ``scale`` since. Its box (``height``) changes with the pose."""
        p0, _, p2 = (np.asarray(p, dtype=float) for p in self._anchor.points[:3])
        return float(np.linalg.norm((p2 - p0)[:2])) / _ANCHOR_SIDE

    @property
    def motion_strength(self) -> float:
        """The strength (0..1) of its :attr:`motion` setting."""
        return motion_strength(self.motion)

    def set_squash(self, x: float = 1.0, y: float = 1.0) -> Character:
        """Scale the whole figure by ``x``, ``y`` about its feet (squash and stretch, §69.13), on
        top of the poses: not part of :meth:`state`; ``set_squash()`` puts it back."""
        squash = (float(x), float(y))
        if squash == self._squash:
            return self
        self._squash = squash
        return self.refresh()

    def feet(self) -> np.ndarray:
        """The point between the feet on screen (the character's origin)."""
        return np.array(self._anchor.points[0], dtype=float)

    def hand_point(self, hand: str) -> np.ndarray:
        """Where the ``left`` or ``right`` hand is on screen now (the end of that arm: the hand's
        middle on a generated character; on an SVG the point of the arm farthest from the
        shoulder), with the arm's pose, its parents and the facing (§69.26)."""
        return self._limb_end(self._limb_of(HANDS, hand, "hand"))

    def shoulder_point(self, hand: str) -> np.ndarray:
        """Where the ``left`` or ``right`` arm turns (its shoulder pivot) on screen now."""
        return self.pivot(self._limb_of(HANDS, hand, "hand"))

    def foot_point(self, foot: str) -> np.ndarray:
        """Where the sole of the ``left`` or ``right`` foot is on screen now (needs ``leg_left`` /
        ``leg_right``; the end of that leg)."""
        return self._limb_end(self._limb_of(FEET, foot, "foot"))

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
        name = self._posed_name(part)
        pose = self._poses[name]
        changes: dict[str, Any] = {}
        if angle is not None:
            changes["angle"] = float(angle)
        if scale is not None:
            changes["scale"] = (float(scale), float(scale)) if isinstance(scale, (int, float)) else (float(scale[0]), float(scale[1]))
        if shift is not None:
            changes["shift"] = (float(shift[0]), float(shift[1]))
        if shape is not None:
            if shape not in self._shapes.get(name, {}):
                raise VidgenError(f"character '{self.name}': part '{name}' has no shape '{shape}' (shapes: {_known(self._shapes.get(name, {}))})")
            changes["shape"] = shape
        self._store_pose(name, replace(pose, **changes))
        return self.refresh()

    def swap(self, part: str, shape: str) -> Character:
        """Show ``part``'s shape ``shape`` (e.g. a mouth shape); same as ``set_part(part, shape=...)``."""
        return self.set_part(part, shape=shape)

    def reset(self, part: str | None = None) -> Character:
        """Put ``part`` (default: every part) back to its rest pose and shape."""
        for name in [self._posed_name(part)] if part is not None else list(self._poses):
            self._store_pose(name, PartPose())
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
            self._store_pose(self._posed_name(part), pose)
        return self.refresh()

    def reach(self, hand: str, point: Sequence[float], *, bend: float = ELBOW_BEND) -> Character:
        """Turn the ``left`` or ``right`` arm so its hand (:meth:`hand_point`) is at ``point``
        (screen, Manim units), bending the elbow the way of ``bend``'s sign (+1: counterclockwise
        as drawn facing right, the natural elbow; -1 the other way). Out of reach, the arm
        points at it, straight. Only the upper and lower arm's angles change (their shift and
        scale stay); an arm in one piece turns and shortens (:func:`~vidgen.cartoon.limbs.fold`)."""
        return self._bend_limb(self._limb_of(HANDS, hand, "hand"), point, bend)

    def reached_parts(
        self, hand: str, point: Sequence[float], *, bend: float = ELBOW_BEND, state: CharacterState | None = None,
    ) -> dict[str, PartPose]:
        """The poses :meth:`reach` would give the ``left`` or ``right`` arm (upper and lower part
        names -> :class:`PartPose`), without changing the character (for an animation's target).
        ``state``: reach from the shoulder as it is in that state (a crouch), not as it is now."""
        poses = {**self._poses, **(state.parts if state is not None else {})}
        return self._limb_poses(self._limb_of(HANDS, hand, "hand"), self._to_character(point), bend, poses)

    def plant(self, foot: str, point: Sequence[float], *, bend: float = KNEE_BEND) -> Character:
        """Bend the ``left`` or ``right`` leg so its sole (:meth:`foot_point`) is at ``point``
        (screen), the knee forward (``bend`` -1; +1 bends it backwards), as :meth:`reach` does
        for a hand. Needs ``leg_left`` / ``leg_right`` (a ``legs`` part in one piece cannot)."""
        return self._bend_limb(self._limb_of(FEET, foot, "foot"), point, bend)

    def sole_height(self, state: CharacterState | None = None) -> float | None:
        """How high the lower foot's sole is in ``state`` (default: now), in character units
        above the ground (0 at rest); ``None`` without ``leg_left`` / ``leg_right``."""
        legs = [upper for upper in FEET.values() if upper in self._limbs]
        if not legs:
            return None
        world = self._world({**self._poses, **(state.parts if state is not None else {})})
        return min(float(self._end_in_character(upper, world)[1]) for upper in legs)

    def grounded(self, state: CharacterState, level: float = 0.0) -> CharacterState:
        """``state`` with the body raised or lowered so the lower foot's sole is ``level``
        character units above the ground (:meth:`sole_height`); unchanged for a character without
        ``leg_left`` / ``leg_right`` or without a body pose in ``state``."""
        height = self.sole_height(state)
        if height is None or "body" not in state.parts or height == level:
            return state
        body = state.parts["body"]
        moved = replace(body, shift=(body.shift[0], body.shift[1] - (height - level)))
        return CharacterState(state.facing, {**state.parts, "body": moved})

    def limb_rest(self, limb: str) -> tuple[tuple[float, float], float, float]:
        """An arm or a leg (``arm_left``, ``leg_right``, ...) at rest, in character units: where it
        turns (shoulder or hip) and the lengths of its upper and lower segment (one-piece limbs:
        the halves)."""
        if limb not in self._limbs:
            raise VidgenError(f"character '{self.name}' has no {limb} (limbs: {_known(self._limbs)})")
        rest = self._limbs[limb]
        upper, lower = float(np.linalg.norm(rest.joint - rest.root)), float(np.linalg.norm(rest.end - rest.joint))
        return (float(rest.root[0]), float(rest.root[1])), upper, lower

    def hip_height(self) -> float | None:
        """How high the hips are at rest (character units): where ``leg_left`` / ``leg_right`` or
        the one-piece ``legs`` turn; ``None`` without legs."""
        for part in (*FEET.values(), "legs"):
            if part in self._pivots:
                return float(self._pivots[part][1])
        return None

    def part_box(self, part: str, state: CharacterState | None = None) -> tuple[float, float, float, float]:
        """``part``'s box ``(left, bottom, right, top)`` in character units as drawn facing right,
        in ``state`` (default: now)."""
        name = self._part_name(part)
        matrix = self._world({**self._poses, **(state.parts if state is not None else {})})[name]
        points = np.concatenate([_apply(matrix, p)[:, :2] for p in self._drawings[name][self._shape_name(name)] if len(p)])
        return float(points[:, 0].min()), float(points[:, 1].min()), float(points[:, 0].max()), float(points[:, 1].max())

    def sole_points(self, state: CharacterState | None = None) -> dict[str, tuple[float, float]]:
        """Where each single leg's sole is in ``state`` (default: now): ``left`` / ``right`` ->
        (x, y) in character units as drawn facing right; empty without ``leg_left`` / ``leg_right``."""
        world = self._world({**self._poses, **(state.parts if state is not None else {})})
        found = {}
        for foot, upper in FEET.items():
            if upper in self._limbs:
                x, y = self._end_in_character(upper, world)
                found[foot] = (float(x), float(y))
        return found

    def planted(self, state: CharacterState, soles: Mapping[str, Sequence[float]], *, bend: float = KNEE_BEND) -> CharacterState:
        """``state`` with each single leg of ``soles`` (``left`` / ``right`` -> (x, y), character
        units as drawn facing right) bent so its sole is there, the knee forward (:meth:`plant`
        for a state, not drawn). Legs the character lacks are skipped."""
        parts = dict(state.parts)
        for foot, sole in soles.items():
            upper = FEET.get(foot)
            if upper in self._limbs:
                poses = {**self._poses, **parts}
                parts.update(self._limb_poses(upper, np.array([float(sole[0]), float(sole[1])]), bend, poses))
        return CharacterState(state.facing, parts)

    def lowered(self, state: CharacterState, drop: float, *, stoop: float = 0.0, soles: Mapping[str, Sequence[float]] | None = None) -> CharacterState:
        """``state`` crouched: the body ``drop`` character units lower and bent ``stoop`` degrees
        forward, the feet kept on the ground: single legs planted at ``soles`` (default: where they
        are in ``state``), knees forward; a one-piece ``legs`` part shortened from its top (and
        turned back upright) so it still reaches the ground. Not drawn."""
        feet = dict(soles) if soles is not None else self.sole_points(state)
        parts = dict(state.parts)
        body = parts["body"]
        parts["body"] = replace(body, angle=body.angle - stoop, shift=(body.shift[0], body.shift[1] - drop))
        if "legs" in self._pivots:
            top = float(self._pivots["legs"][1])
            legs = parts["legs"]
            squeeze = max(top - drop, 0.1 * top) / top if top > 0 else 1.0
            parts["legs"] = replace(legs, angle=legs.angle + stoop, scale=(legs.scale[0], legs.scale[1] * squeeze))
        return self.planted(CharacterState(state.facing, parts), feet)

    def seated(self, state: CharacterState, seat: float) -> CharacterState:
        """``state`` sitting on a seat ``seat`` character units above the ground: the body lowered
        until its lowest point is on the seat; single legs with the thighs forward and the shins
        down to the ground (:func:`~vidgen.cartoon.seating.seated_sole`); a one-piece ``legs`` part
        turned forward until its feet rest on the ground, or on a seat higher than the legs are
        long held out (:data:`~vidgen.cartoon.seating.SEATED_LEGS_DEGREES`). Not drawn."""
        parts = dict(state.parts)
        body = parts["body"]
        bottom = self.part_box("body", state)[1]
        parts["body"] = replace(body, shift=(body.shift[0], body.shift[1] + seat - bottom))
        world = self._world({**self._poses, **parts})
        if "legs" in self._pivots:
            pivot = self._pivots["legs"]
            top = float((world["body"] @ np.array([*(pivot + np.asarray(parts["legs"].shift)), 1.0]))[1])
            length = float(pivot[1]) - min(float(p[:, 1].min()) for p in self._drawings["legs"][self._shape_name("legs")] if len(p))
            angle = math.degrees(math.acos(top / length)) if 0 < top < length else SEATED_LEGS_DEGREES
            parts["legs"] = replace(parts["legs"], angle=angle)
        soles = {}
        for foot, upper in FEET.items():
            if upper in self._limbs:
                hip = world[self._parents[upper]] @ np.array([*(self._limbs[upper].root + np.asarray(parts[upper].shift)), 1.0])
                _, thigh, shin = self.limb_rest(upper)
                soles[foot] = seated_sole((float(hip[0]), float(hip[1])), thigh, shin)
        return self.planted(CharacterState(state.facing, parts), soles)

    def leaning(self, state: CharacterState, degrees: float = LEAN_DEGREES) -> CharacterState:
        """``state`` leaning back ``degrees`` (the body turned back about its pivot, the legs with
        it, so the feet come forward), lowered until the higher sole is on the ground and the other
        leg planted beside it. Not drawn."""
        body = state.parts["body"]
        leant = CharacterState(state.facing, {**state.parts, "body": replace(body, angle=body.angle + degrees)})
        soles = self.sole_points(leant)
        if not soles:
            return leant
        return self.lowered(leant, max(y for _, y in soles.values()), soles={foot: (x, 0.0) for foot, (x, _) in soles.items()})

    def set_pose(self, name: str) -> Character:
        """Show pose ``name`` at once (``stand``, ``pointing``, ...; :meth:`names`)."""
        return self.set_state(self.posed_state(pose=name))

    def set_expression(self, name: str) -> Character:
        """Show expression ``name`` at once (``neutral``, ``happy``, ...; :meth:`names`)."""
        return self.set_state(self.posed_state(expression=name))

    # ----- lip sync (DESIGN.md §69.4) -------------------------------------------------------

    def viseme_shape(self, viseme: str) -> str | None:
        """The mouth shape that shows ``viseme``: the first of :data:`VISEME_SHAPES` the
        character has (``None``: the mouth's rest shape at the time, as for ``rest``)."""
        if viseme not in VISEMES:
            raise VidgenError(f"unknown viseme {viseme!r} (visemes: {_known(VISEMES)})")
        shapes = self._shapes.get("mouth", {})
        return next((shape for shape in VISEME_SHAPES[viseme] if shape in shapes), None)

    def show_viseme(self, viseme: str, rest: str | None = None) -> Character:
        """Show ``viseme``'s mouth shape (:meth:`viseme_shape`); ``rest`` names the shape for
        ``rest`` and for a viseme the character has no shape for (default: the mouth's first
        shape). A character without a mouth is left as it is."""
        if not self.has_part("mouth"):
            return self
        shape = self.viseme_shape(viseme) or rest or self.shape_names("mouth")[0]
        return self if shape == self._shape_name("mouth") else self.set_part("mouth", shape=shape)

    def lip_sync(self, track: VisemeTrack, *, start: float = 0.0, clock: Callable[[], float] | None = None) -> Character:
        """Make the mouth follow ``track`` from now. ``clock`` gives the seconds into the track
        when called (e.g. the scene time since the beat's audio started:
        :meth:`NarratedScene.beat_clock <vidgen.scene.NarratedScene.beat_clock>`), so the mouth
        stays in step with the audio whatever plays meanwhile; without it, a clock starting
        ``start`` seconds into the track (negative: a delay) advances by each frame's time. The
        viseme's mouth shape is shown on top of the mouth's pose; at ``rest`` (or for a viseme
        the character has no shape for) the pose's shape shows (the expression's). It replaces
        a running lip sync; :meth:`stop_lip_sync` ends it. Manim pauses a mobject's updaters
        while an animation plays on it: :class:`PoseChange` calls :meth:`sync_mouth` on every
        frame, other animations hold the mouth until they end."""
        self.stop_lip_sync()
        if not self.has_part("mouth"):
            return self
        self._lip_sync = _LipSync(track, float(start), clock)
        self.add_updater(Character._lip_sync_step)
        return self.sync_mouth()

    def stop_lip_sync(self) -> Character:
        """End :meth:`lip_sync`: the mouth shows its pose's shape."""
        if self._lip_sync is None:
            return self
        self.remove_updater(Character._lip_sync_step)
        self._lip_sync = None
        self._set_spoken(None)
        return self.refresh()

    @property
    def lip_sync_track(self) -> VisemeTrack | None:
        """The track the running :meth:`lip_sync` follows (``None`` when none runs)."""
        return self._lip_sync.track if self._lip_sync is not None else None

    @property
    def spoken_viseme(self) -> str | None:
        """The viseme the running :meth:`lip_sync` showed last (``rest`` between words; ``None``
        when none runs)."""
        speech = self._lip_sync
        return speech.track.at(speech.seconds) if speech is not None else None

    def sync_mouth(self) -> Character:
        """Show the running lip sync's viseme for its clock now (nothing without one)."""
        speech = self._lip_sync
        if speech is None:
            return self
        if speech.clock is not None:
            speech.seconds = float(speech.clock())
        before = self._shape_name("mouth")
        self._set_spoken(self.viseme_shape(speech.track.at(speech.seconds)))
        return self.refresh() if self._shape_name("mouth") != before else self

    def _lip_sync_step(self, dt: float) -> Character:
        if self._lip_sync is not None and self._lip_sync.clock is None:
            self._lip_sync.seconds += dt
        return self.sync_mouth()

    def _set_spoken(self, shape: str | None) -> None:
        """Show ``shape`` instead of the mouth's pose shape (``None``: the pose's); not redrawn."""
        before = self._shape_name("mouth")
        self._spoken = shape
        self._show_shape("mouth", before)

    # ----- idle motion (DESIGN.md §69.5) ----------------------------------------------------

    @property
    def is_idle(self) -> bool:
        """True while :meth:`start_idle`'s motion runs."""
        return self._idle is not None

    def start_idle(self, seed: int | None = None) -> Character:
        """Breathe (the body scales a little), sway the head slightly and blink (eyes ``closed``)
        at seeded random intervals of 2 to 6 s (``seed`` default: from the name;
        :func:`~vidgen.cartoon.idle.blink_times`), from now, through an updater. The motion is a
        layer on top of the poses: :meth:`state`, :meth:`set_state`, :class:`PoseChange` and
        :meth:`lip_sync` never see it. Its clock stops while Manim suspends the updaters (an
        animation playing on the character); :class:`PoseChange` ends a running blink."""
        self.stop_idle()
        self._idle = IdleClock(idle_seed(self.name) if seed is None else int(seed))
        self.add_updater(Character._idle_step)
        return self._idle_step(0.0)

    def stop_idle(self) -> Character:
        """End :meth:`start_idle`: the body, head and eyes show their poses only."""
        if self._idle is None:
            return self
        self.remove_updater(Character._idle_step)
        self._idle = None
        for part in list(self._overlays):
            self._set_overlay(part, None)
        return self.refresh()

    def end_blink(self) -> Character:
        """Open the eyes now if a blink is running (it is not resumed)."""
        if self._idle is None or not self._idle.is_blinking:
            return self
        self._idle.end_blink()
        self._set_overlay("eyes", None)
        return self.refresh()

    def _idle_step(self, dt: float) -> Character:
        idle = self._idle
        if idle is None:
            return self
        idle.advance(dt)
        self._set_overlay("body", PartPose(scale=breath_scale(idle.seconds, idle.seed)))
        if "head" in self._shapes:
            self._set_overlay("head", PartPose(angle=sway_angle(idle.seconds, idle.seed)))
        if "closed" in self._shapes.get("eyes", {}):
            self._set_overlay("eyes", PartPose(shape="closed") if idle.is_blinking else None)
        return self.refresh()

    def refresh(self) -> Character:
        """Redraw every part's points from its rest shape, pose, parents, facing and placement.
        Styles (colour, opacity) of the live parts are kept."""
        screen = self._screen()
        world = self._world()
        for name in self.parts:
            matrix = screen @ world[name]
            for live, points in zip(self._live_members(name), self._drawings[name][self._shape_name(name)]):
                live.points = _apply(matrix, points)
        return self

    # ----- internals ------------------------------------------------------------------------

    def _part_name(self, part: str) -> str:
        if part not in self._shapes:
            raise VidgenError(f"character '{self.name}' has no part '{part}' (parts: {_known(self._order)})")
        return part

    def _posed_name(self, part: str) -> str:
        """``part`` if it has a pose: a part, or the lower segment of a limb drawn in one piece."""
        return part if part in self._folded else self._part_name(part)

    def _limb_geometry(self, upper: str, specs: Mapping[str, CharacterPart]) -> _Limb:
        """The rest geometry of the limb whose upper part is ``upper``: the end given by its last
        segment, else the drawn point farthest from the root; the joint at the lower part's pivot,
        else half-way."""
        lower = LIMBS[upper]
        root = self._pivots[upper]
        last = lower if lower in specs else upper
        if specs[last].end is not None:
            end = np.array(specs[last].end, dtype=float)
        else:
            drawn = [points[:, :2] for part in (upper, lower) if part in specs for points in self._drawings[part][next(iter(specs[part].shapes))]]
            stacked = np.concatenate(drawn) if drawn else root[None, :]
            end = stacked[int(np.argmax(np.linalg.norm(stacked - root, axis=1)))]
        joint = self._pivots[lower] if lower in specs else (root + end) / 2
        return _Limb(root, np.array(joint, dtype=float), np.array(end, dtype=float))

    def _limb_of(self, names: dict[str, str], side: str, what: str) -> str:
        try:
            upper = limb_side(names, side, what)
        except ValueError as exc:
            raise VidgenError(f"character '{self.name}': {exc}") from None
        if upper not in self._limbs:
            kind = "an arm" if what == "hand" else "a leg of its own (its legs are one part 'legs', or it has none)"
            raise VidgenError(f"character '{self.name}' has no {upper}: its {side} {what} needs {kind}")
        return upper

    def _end_in_character(self, upper: str, world: Mapping[str, np.ndarray]) -> np.ndarray:
        """The limb's end in character units under ``world`` (its last segment's matrix; a folded
        lower part is in the upper's)."""
        lower = LIMBS[upper]
        matrix = world[lower] if lower in world else world[upper]
        end = self._limbs[upper].end
        return (matrix @ np.array([end[0], end[1], 1.0]))[:2]

    def _limb_end(self, upper: str) -> np.ndarray:
        x, y = (self._screen() @ np.array([*self._end_in_character(upper, self._world()), 1.0]))[:2]
        return np.array([x, y, 0.0])

    def _bend_limb(self, upper: str, point: Sequence[float], bend: float) -> Character:
        """Set the angles of the limb ``upper`` (and its lower part) that put its end at ``point``
        (screen)."""
        for part, pose in self._limb_poses(upper, self._to_character(point), bend, self._poses).items():
            self._store_pose(part, pose)
        return self.refresh()

    def _to_character(self, point: Sequence[float]) -> np.ndarray:
        """A screen point in character units (as drawn facing right)."""
        return np.linalg.solve(self._screen(), np.array([float(point[0]), float(point[1]), 1.0]))[:2]

    def _limb_poses(self, upper: str, point: np.ndarray, bend: float, poses: Mapping[str, PartPose]) -> dict[str, PartPose]:
        """The poses of the limb ``upper`` and its lower part that put its end at ``point``
        (character units) with the other parts posed as ``poses`` says, from
        :func:`~vidgen.cartoon.limbs.solve_two_bone`."""
        lower = LIMBS[upper]
        limb = self._limbs[upper]
        parent = self._parents[upper]
        frame = self._world(poses)[parent] if parent is not None else np.eye(3)
        target = np.linalg.solve(frame, np.array([float(point[0]), float(point[1]), 1.0]))[:2]
        root = limb.root + np.asarray(poses[upper].shift, dtype=float)
        upper_rest, lower_rest = limb.joint - limb.root, limb.end - limb.joint
        solution = solve_two_bone(
            (float(root[0]), float(root[1])), (float(target[0]), float(target[1])),
            float(np.linalg.norm(upper_rest)), float(np.linalg.norm(lower_rest)), bend,
        )
        upper_dir = math.degrees(math.atan2(upper_rest[1], upper_rest[0]))
        lower_dir = math.degrees(math.atan2(lower_rest[1], lower_rest[0]))
        return {
            upper: replace(poses[upper], angle=wrap_degrees(solution.direction - upper_dir)),
            lower: replace(poses[lower], angle=wrap_degrees(solution.bend + upper_dir - lower_dir)),
        }

    def _fold_matrix(self, upper: str, bend: float) -> np.ndarray:
        """A folded lower part's ``bend`` shown on the one-piece ``upper``: turned by half the
        bend and shortened along the limb, about the root."""
        limb = self._limbs[upper]
        turn, length = fold(bend)
        axis = limb.end - limb.root
        norm = float(np.linalg.norm(axis))
        unit = axis / norm if norm > 1e-12 else np.array([0.0, -1.0])
        shorten = np.eye(2) + (length - 1.0) * np.outer(unit, unit)
        cos, sin = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        linear = np.array([[cos, -sin], [sin, cos]]) @ shorten
        out = np.eye(3)
        out[:2, :2] = linear
        out[:2, 2] = limb.root - linear @ limb.root
        return out

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

    def _entry_pose(self, part: str, entry: PartPoseEntry | None) -> PartPose:
        if entry is None:
            return PartPose()
        shift = (float(entry.shift[0]), float(entry.shift[1]))
        return PartPose(float(entry.angle), entry.scale_xy(), shift, chosen_shape(entry, self._shapes.get(part, {})))

    def _shape_name(self, part: str) -> str:
        """The shape shown: lip sync's (the mouth), the idle overlay's (a blink), else the pose's,
        else the rest shape."""
        if part == "mouth" and self._spoken is not None:
            return self._spoken
        overlay = self._overlays.get(part)
        if overlay is not None and overlay.shape is not None:
            return overlay.shape
        return self._poses[part].shape or next(iter(self._shapes[part]))

    def _store_pose(self, part: str, pose: PartPose) -> None:
        if part in self._folded:
            self._poses[part] = replace(pose, shape=None)
            return
        if pose.shape is not None and pose.shape not in self._shapes[part]:
            raise VidgenError(f"character '{self.name}': part '{part}' has no shape '{pose.shape}' (shapes: {_known(self._shapes[part])})")
        before = self._shape_name(part)
        self._poses[part] = pose
        self._show_shape(part, before)

    def _set_overlay(self, part: str, overlay: PartPose | None) -> None:
        """Set (``None``: remove) ``part``'s idle overlay, applied after its pose; not redrawn."""
        before = self._shape_name(part)
        if overlay is None:
            self._overlays.pop(part, None)
        else:
            self._overlays[part] = overlay
        self._show_shape(part, before)

    def _live_members(self, part: str) -> list[VMobject]:
        """The drawn members of ``part``'s shown shape (its live copy, kept for the character's
        life), in the order of the shape's drawing."""
        return self._members[part][self._shape_name(part)]

    def _hide(self, part: str, shape: str) -> None:
        """Take the points off ``shape``'s live copy (it stays in the family, not drawn)."""
        for member in self._members[part][shape]:
            member.points = np.zeros((0, 3))

    def _show_shape(self, part: str, before: str) -> None:
        """Hide the shape ``before`` when ``part`` now shows another; the next :meth:`refresh`
        draws the new one (only points change: the family stays as it is, §69.22)."""
        if self._shape_name(part) != before:
            self._hide(part, before)

    def _world(self, poses: Mapping[str, PartPose] | None = None) -> dict[str, np.ndarray]:
        """Each part's matrix in character units: its idle overlay and pose about its pivot (and
        a folded lower part's bend), then its parents'. ``poses``: these instead of the current."""
        poses = self._poses if poses is None else poses
        world: dict[str, np.ndarray] = {}
        for name in self._tree_order:
            local = poses[name].matrix(self._pivots[name])
            overlay = self._overlays.get(name)
            if overlay is not None:
                local = local @ overlay.matrix(self._pivots[name])
            if LIMBS.get(name) in self._folded and poses[LIMBS[name]].angle:
                local = local @ self._fold_matrix(name, poses[LIMBS[name]].angle)
            parent = self._parents[name]
            world[name] = local if parent is None else world[parent] @ local
        return world

    def _screen(self) -> np.ndarray:
        """Character units -> screen: the squash about the feet, the mirror for ``facing: left``,
        then the anchor's placement."""
        p0, p1, p2 = (np.asarray(p, dtype=float) for p in self._anchor.points[:3])
        placement = np.eye(3)
        placement[:2, 0] = (p1 - p0)[:2] / _ANCHOR_SIDE
        placement[:2, 1] = (p2 - p0)[:2] / _ANCHOR_SIDE
        placement[:2, 2] = p0[:2]
        mirror = np.diag([(-1.0 if self.facing == "left" else 1.0) * self._squash[0], self._squash[1], 1.0])
        return placement @ mirror


# ----- characters of the config ------------------------------------------------------------

#: How many generated looks' part drawings :func:`look_parts` keeps (the oldest is dropped).
LOOK_CACHE_SIZE = 16
_look_cache: OrderedDict[str, list[CharacterPart]] = OrderedDict()


def look_key(look: CharacterLook, colors: Mapping[str, Any]) -> str:
    """The key of a generated look's part drawings in :func:`look_parts`: the ``look``
    parameters and the resolved ``colors``. A character's poses, expressions, name, voice and
    state are not in it: they never change a part's drawing, only how it is transformed."""
    resolved = {part: str(color) for part, color in sorted(colors.items())}
    return json.dumps([look.model_dump(mode="json"), resolved], sort_keys=True)


def look_parts(look: CharacterLook, colors: Mapping[str, Any]) -> list[CharacterPart]:
    """The generator's parts for ``look`` in ``colors`` (:func:`~vidgen.cartoon.generator.generate_parts`),
    drawn once per :func:`look_key` and shared: a :class:`Character` copies the shapes it is
    given, so callers must not change them."""
    from vidgen.cartoon.generator import generate_parts

    key = look_key(look, colors)
    parts = _look_cache.get(key)
    if parts is None:
        parts = generate_parts(look, colors)
        _look_cache[key] = parts
        while len(_look_cache) > LOOK_CACHE_SIZE:
            _look_cache.popitem(last=False)
    else:
        _look_cache.move_to_end(key)
    return parts


def build_character(
    entry: CharacterEntry,
    *,
    theme: Theme | None = None,
    height: float = 3.0,
    facing: str = "right",
    root: Path | None = None,
    motion: str | None = None,
) -> Character:
    """The :class:`Character` of a ``characters:`` entry, feet at the origin: its ``look`` drawn
    by the generator with its colours resolved in ``theme`` (default: the current theme), or
    ``look.svg`` (relative to ``root``, default: the active project's folder) split into parts.
    Its idle motion runs unless the entry says ``idle: false``. Its ``cartoon_motion`` is the
    entry's, else ``motion`` (the scene's or the video's), else ``lively``."""
    motion = resolve_motion(entry.cartoon_motion, motion)
    if entry.look.svg is not None:
        from vidgen.cartoon.svg_look import SVG_REQUIRED_PARTS, svg_character_parts

        if root is None:
            from vidgen.runtime import current_project

            root = current_project().root
        parts = svg_character_parts(root / entry.look.svg, where=f"characters '{entry.name}': {entry.look.svg}")
        built = Character(
            parts, name=entry.name, height=height, facing=facing, voice=entry.voice, required=SVG_REQUIRED_PARTS,
            poses=entry.poses, expressions=entry.expressions, motion=motion,
        )
    else:
        colors = {part: resolve_color(value, theme) for part, value in entry.colors.model_dump().items()}
        built = Character(
            look_parts(entry.look, colors), name=entry.name, height=height, facing=facing, voice=entry.voice,
            poses=entry.poses, expressions=entry.expressions, motion=motion,
        )
    return built.start_idle() if entry.idle else built


def character(name: str, *, height: float = 3.0, facing: str = "right", motion: str | None = None) -> Character:
    """The character ``name`` of the active project's ``characters:``, ``height`` Manim units
    tall, feet at the origin. Unknown names raise :class:`VidgenError` with suggestions. Its
    ``cartoon_motion`` is its own, else ``motion`` (a scene's), else the video's, else ``lively``."""
    from vidgen.cartoon.cast import find_character
    from vidgen.runtime import current_project, current_theme

    project = current_project()
    entry = find_character(project.config, name)
    return build_character(
        entry, theme=current_theme(), height=height, facing=facing, root=project.root,
        motion=resolve_motion(motion, project.config.cartoon_motion),
    )


__all__ = [
    "Character",
    "CharacterPart",
    "CharacterState",
    "PartPose",
    "PART_NAMES",
    "build_character",
    "character",
]
