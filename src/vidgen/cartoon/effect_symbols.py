"""Effect symbols drawn and moved with manim (DESIGN.md §69.40); the geometry is in
:mod:`vidgen.cartoon.effects`.

An :class:`EffectSymbol` is a mobject of its own, never a part of the character it marks (a
character's parts never change, §69.22): :meth:`EffectSymbol.follow` gives it an updater that, on
every frame, reads the head's box on screen and the facing (so it goes along with walks, jumps,
turns and shots), counts its own seconds and redraws every shape from its points in symbol units.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from manim import Mobject, VGroup, VMobject

from vidgen.cartoon.character import OUTER_HAIR_ATTRIBUTE, OUTLINE_WIDTH, REFERENCE_HEIGHT, Character, one_pixel_stroke
from vidgen.cartoon.effects import (
    EFFECT_STYLES,
    Box,
    EffectShape,
    EffectSpot,
    effect_pieces,
    effect_spot,
    exit_scale,
    piece_center,
    piece_pose,
    pop_scale,
    spot_at,
)
from vidgen.cartoon.stage import facing_sign
from vidgen.config import CHARACTER_INK

#: Fills of the shapes besides the symbol's colour (``main``).
SHINE = "#FFFFFF"
BASE = "#9AA3AF"
#: Outline width as a share of a character's (the symbols are small).
OUTLINE_SHARE = 0.8
#: Below this scale a shape is not drawn (a stroke round nothing would leave an ink dot).
HIDDEN_SCALE = 0.03


def _shape_mobject(shape: EffectShape, color: str, stroke: float) -> VMobject:
    mob = VMobject()
    mob.set_points_as_corners(np.array([[x, y, 0.0] for x, y in (*shape.points, shape.points[0])]))
    fill = {"main": color, "shine": SHINE, "base": BASE}[shape.fill]
    mob.set_fill(fill, opacity=1.0)
    mob.set_stroke(CHARACTER_INK, width=stroke if shape.outline else 0.0, opacity=1.0 if shape.outline else 0.0)
    return mob


def _head_members(character: Character) -> tuple[list[VMobject], list[VMobject]]:
    """The drawn members of ``character``'s head part: the head's own, and the hair beyond the
    head (:data:`~vidgen.cartoon.character.OUTER_HAIR_ATTRIBUTE`: an afro, braids, a beard)."""
    members = character.parts["head"].family_members_with_points()
    outer = [m for m in members if getattr(m, OUTER_HAIR_ATTRIBUTE, False)]
    return [m for m in members if not getattr(m, OUTER_HAIR_ATTRIBUTE, False)], outer


def head_box(character: Character) -> Box:
    """The box ``(left, bottom, right, top)`` of ``character``'s head on screen now (without the
    hair beyond the head, DESIGN.md §69.47); without a ``head`` part, the top 30 % of its box."""
    if character.has_part("head"):
        head = character.parts["head"]
        own, outer = _head_members(character)
        if outer and own:
            points = np.vstack([m.points for m in own])
            return (float(points[:, 0].min()), float(points[:, 1].min()), float(points[:, 0].max()), float(points[:, 1].max()))
        return (float(head.get_left()[0]), float(head.get_bottom()[1]), float(head.get_right()[0]), float(head.get_top()[1]))
    x0, x1 = float(character.get_left()[0]), float(character.get_right()[0])
    y0, y1 = float(character.get_bottom()[1]), float(character.get_top()[1])
    return (x0, y1 - 0.3 * (y1 - y0), x1, y1)


def crown_top(character: Character) -> float | None:
    """The top of what ``character`` wears on its head on screen: its ``accessory`` (a hat, a
    cap) or hair beyond the head (an afro), whichever is higher; ``None`` without either drawn."""
    tops = []
    accessory = character.parts.get("accessory")
    if accessory is not None and accessory.family_members_with_points():
        tops.append(float(accessory.get_top()[1]))
    if character.has_part("head"):
        outer = _head_members(character)[1]
        if outer:
            tops.append(float(np.vstack([m.points for m in outer])[:, 1].max()))
    return max(tops) if tops else None


def eye_point(character: Character) -> tuple[float, float] | None:
    """The middle of ``character``'s eyes on screen (``None``: it has no ``eyes`` part)."""
    if not character.has_part("eyes"):
        return None
    center = character.parts["eyes"].get_center()
    return float(center[0]), float(center[1])


class EffectSymbol(VGroup):
    """The ``kind`` symbol (:data:`~vidgen.cartoon.effects.EFFECT_KINDS`) in ``color`` (hex),
    outlined in the characters' ink as wide as on a character ``character_height`` tall:
    one :class:`VGroup` per piece, its shapes drawn about 1 tall. ``effect_of`` names the
    character it marks (the layout dump's ``effect_of``); ``age``: seconds since it appeared;
    ``leaving``: its age when its effect ended (``None`` while it lasts)."""

    def __init__(self, kind: str, *, color: str, character_height: float, effect_of: str | None = None) -> None:
        super().__init__()
        self.kind = kind
        self.effect_of = effect_of
        self.age = 0.0
        self.leaving: float | None = None
        self._pieces = effect_pieces(kind)
        stroke = max(OUTLINE_WIDTH * OUTLINE_SHARE * character_height / REFERENCE_HEIGHT, one_pixel_stroke())
        self._members: list[list[tuple[VMobject, np.ndarray]]] = []
        for piece in self._pieces:
            group = VGroup(*(_shape_mobject(shape, color, stroke) for shape in piece.shapes))
            self._members.append([(m, np.array(m.points, dtype=float)) for m in group.submobjects])
            self.add(group)

    def place(self, spot: EffectSpot, facing: str, strength: float = 1.0) -> EffectSymbol:
        """Draw every piece for its pose at :attr:`age` (popped in with ``cartoon_motion``
        ``strength``, shrinking once leaving) with the symbol's middle and height ``spot``."""
        side = facing_sign(facing)
        whole = pop_scale(self.age, strength)
        if self.leaving is not None:
            whole *= exit_scale(self.age - self.leaving)
        for k, (piece, members) in enumerate(zip(self._pieces, self._members)):
            pose = piece_pose(self.kind, k, self.age)
            scale = piece.size * pose.scale * whole * spot.size
            angle = math.radians(side * pose.angle)
            c, s = math.cos(angle), math.sin(angle)
            matrix = np.array([[c, -s], [s, c]]) * scale
            center = np.array([spot.x, spot.y]) + np.array(piece_center(self.kind, k, self.age, facing)) * whole * spot.size
            for member, home in members:
                if abs(scale) < HIDDEN_SCALE * spot.size:
                    member.points = np.zeros((0, 3))
                    continue
                points = np.array(home)
                points[:, :2] = home[:, :2] @ matrix.T + center
                member.points = points
        return self

    def follow(self, character: Character, *, avoid: Sequence[Box] = ()) -> EffectSymbol:
        """Keep the symbol on ``character``'s head from now on: its spot (chosen now, clear of
        ``avoid``; :func:`~vidgen.cartoon.effects.effect_spot`) worked out again on every frame
        from the head's box and the facing, its :attr:`age` counted by the frames' ``dt`` (an
        updater)."""
        chosen = effect_spot(
            self.kind, head_box(character), character.facing, eye=eye_point(character), crown=crown_top(character), avoid=avoid,
        ).spot

        def step(mob: Mobject, dt: float) -> None:
            mob.age += dt
            spot = spot_at(chosen, mob.kind, head_box(character), character.facing, eye_point(character), crown_top(character))
            mob.place(spot, character.facing, character.motion_strength)

        self.effect_of = character.name
        self._step = step
        self.add_updater(step)
        step(self, 0.0)
        return self

    def stop_following(self) -> None:
        """Remove the :meth:`follow` updater (the symbol stays where it is)."""
        step = getattr(self, "_step", None)
        if step is not None:
            self.remove_updater(step)
            self._step = None


def effect_color(kind: str, color: str | None, resolve: Callable[[str], str]) -> str:
    """The hex colour of a ``kind`` symbol: ``color`` (a theme token or hex) when given, else its
    style's token (:data:`~vidgen.cartoon.effects.EFFECT_STYLES`), resolved by ``resolve``."""
    return resolve(color or EFFECT_STYLES[kind].color)
