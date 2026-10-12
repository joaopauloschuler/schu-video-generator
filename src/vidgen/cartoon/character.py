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
from pathlib import Path
from typing import Any

import numpy as np
from manim import VGroup, VMobject

from vidgen.cartoon.idle import IdleClock, breath_scale, idle_seed, sway_angle
from vidgen.cartoon.poses import KINDS, PoseTable, chosen_shape, find_entry, kind_parts, merged_table
from vidgen.cartoon.visemes import VISEME_SHAPES, VISEMES, VisemeTrack
from vidgen.config import CharacterEntry, PartPoseEntry
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


def _check_parts(specs: Mapping[str, CharacterPart], who: str, required: Iterable[str]) -> dict[str, str | None]:
    """The parent of each part; raises :class:`VidgenError` for unknown, missing (of ``required``)
    or badly linked parts."""
    unknown = [n for n in specs if n not in PART_NAMES]
    if unknown:
        raise VidgenError(f"character '{who}': unknown part(s) {_known(unknown)} (parts: {_known(PART_NAMES)})")
    missing = [n for n in required if n not in specs]
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
        required: Iterable[str] = REQUIRED_PARTS,
        poses: PoseTable | None = None,
        expressions: PoseTable | None = None,
    ) -> None:
        super().__init__()
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
        self._own_entries: dict[str, PoseTable] = {"pose": dict(poses or {}), "expression": dict(expressions or {})}
        self._shapes = {n: {k: v.copy() for k, v in s.shapes.items()} for n, s in specs.items()}
        stroke_factor, stroke_floor = height / REFERENCE_HEIGHT, one_pixel_stroke()
        for shapes in self._shapes.values():
            for shape in shapes.values():
                scale_strokes(shape, stroke_factor, stroke_floor)
        self._pivots = {n: np.array(s.pivot, dtype=float) for n, s in specs.items()}
        self._order = sorted(
            specs,
            key=lambda n: (specs[n].order if specs[n].order is not None else DEFAULT_DRAW_ORDER[n], PART_NAMES.index(n)),
        )
        self._tree_order = sorted(specs, key=self._depth)
        self._poses = {n: PartPose() for n in specs}
        self._overlays: dict[str, PartPose] = {}  # idle motion on top of the poses (:meth:`start_idle`)
        self._idle: IdleClock | None = None
        self._lip_sync: Any = None  # the running lip sync updater (:meth:`lip_sync`)
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

    def shown_shape(self, part: str) -> str:
        """The name of ``part``'s shape on screen now (a blink's ``closed`` eyes included)."""
        return self._shape_name(self._part_name(part))

    def pose_of(self, part: str) -> PartPose:
        """``part``'s current :class:`PartPose`."""
        return self._poses[self._part_name(part)]

    def state(self) -> CharacterState:
        """A snapshot of the facing and every part's pose (for :meth:`set_state`)."""
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
                if part in self._shapes:
                    parts[part] = self._entry_pose(part, entry.get(part))
        return CharacterState(self.facing, parts)

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
        self._store_pose(name, replace(pose, **changes))
        return self.refresh()

    def swap(self, part: str, shape: str) -> Character:
        """Show ``part``'s shape ``shape`` (e.g. a mouth shape); same as ``set_part(part, shape=...)``."""
        return self.set_part(part, shape=shape)

    def reset(self, part: str | None = None) -> Character:
        """Put ``part`` (default: every part) back to its rest pose and shape."""
        for name in [self._part_name(part)] if part is not None else list(self._poses):
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
            self._store_pose(self._part_name(part), pose)
        return self.refresh()

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

    def lip_sync(self, track: VisemeTrack, *, start: float = 0.0) -> Character:
        """Make the mouth follow ``track`` from now: an updater advances a clock by each frame's
        time, starting ``start`` seconds into the track (negative: a delay), and shows the viseme
        at that time. At ``rest`` the mouth shows the shape it has now (the expression's). It
        replaces a running lip sync; :meth:`stop_lip_sync` ends it. Manim pauses a mobject's
        updaters while an animation plays on it (e.g. :class:`PoseChange`): the mouth holds then."""
        self.stop_lip_sync()
        if not self.has_part("mouth"):
            return self
        rest, before = self._shape_name("mouth"), self._poses["mouth"].shape
        clock = [float(start)]

        def follow(mob: Character, dt: float) -> None:
            clock[0] += dt
            mob.show_viseme(track.at(clock[0]), rest)

        self._lip_sync = (follow, before)
        self.add_updater(follow)
        return self.show_viseme(track.at(clock[0]), rest)

    def stop_lip_sync(self) -> Character:
        """End :meth:`lip_sync` and show the mouth's shape from before it started."""
        if self._lip_sync is None:
            return self
        follow, before = self._lip_sync
        self.remove_updater(follow)
        self._lip_sync = None
        self._store_pose("mouth", replace(self._poses["mouth"], shape=before))
        return self.refresh()

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

    def _entry_pose(self, part: str, entry: PartPoseEntry | None) -> PartPose:
        if entry is None:
            return PartPose()
        shift = (float(entry.shift[0]), float(entry.shift[1]))
        return PartPose(float(entry.angle), entry.scale_xy(), shift, chosen_shape(entry, self._shapes[part]))

    def _shape_name(self, part: str) -> str:
        """The shape shown: the idle overlay's (a blink), else the pose's, else the rest shape."""
        overlay = self._overlays.get(part)
        if overlay is not None and overlay.shape is not None:
            return overlay.shape
        return self._poses[part].shape or next(iter(self._shapes[part]))

    def _store_pose(self, part: str, pose: PartPose) -> None:
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

    def _show_shape(self, part: str, before: str) -> None:
        if self._shape_name(part) != before:
            self.parts[part].submobjects = [self._shapes[part][self._shape_name(part)].copy()]

    def _world(self) -> dict[str, np.ndarray]:
        """Each part's matrix in character units: its idle overlay and pose about its pivot, then
        its parents'."""
        world: dict[str, np.ndarray] = {}
        for name in self._tree_order:
            local = self._poses[name].matrix(self._pivots[name])
            overlay = self._overlays.get(name)
            if overlay is not None:
                local = local @ overlay.matrix(self._pivots[name])
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


# ----- characters of the config ------------------------------------------------------------


def build_character(
    entry: CharacterEntry,
    *,
    theme: Theme | None = None,
    height: float = 3.0,
    facing: str = "right",
    root: Path | None = None,
) -> Character:
    """The :class:`Character` of a ``characters:`` entry, feet at the origin: its ``look`` drawn
    by the generator with its colours resolved in ``theme`` (default: the current theme), or
    ``look.svg`` (relative to ``root``, default: the active project's folder) split into parts.
    Its idle motion runs unless the entry says ``idle: false``."""
    if entry.look.svg is not None:
        from vidgen.cartoon.svg_look import SVG_REQUIRED_PARTS, svg_character_parts

        if root is None:
            from vidgen.runtime import current_project

            root = current_project().root
        parts = svg_character_parts(root / entry.look.svg, where=f"characters '{entry.name}': {entry.look.svg}")
        built = Character(
            parts, name=entry.name, height=height, facing=facing, voice=entry.voice, required=SVG_REQUIRED_PARTS,
            poses=entry.poses, expressions=entry.expressions,
        )
    else:
        from vidgen.cartoon.generator import generate_parts

        colors = {part: resolve_color(value, theme) for part, value in entry.colors.model_dump().items()}
        built = Character(
            generate_parts(entry.look, colors), name=entry.name, height=height, facing=facing, voice=entry.voice,
            poses=entry.poses, expressions=entry.expressions,
        )
    return built.start_idle() if entry.idle else built


def character(name: str, *, height: float = 3.0, facing: str = "right") -> Character:
    """The character ``name`` of the active project's ``characters:``, ``height`` Manim units
    tall, feet at the origin. Unknown names raise :class:`VidgenError` with suggestions."""
    from vidgen.cartoon.cast import find_character
    from vidgen.runtime import current_project, current_theme

    project = current_project()
    entry = find_character(project.config, name)
    return build_character(entry, theme=current_theme(), height=height, facing=facing, root=project.root)


__all__ = [
    "Character",
    "CharacterPart",
    "CharacterState",
    "PartPose",
    "PART_NAMES",
    "build_character",
    "character",
]
