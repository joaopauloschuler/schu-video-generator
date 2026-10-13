"""Nature that moves by itself, drawn with manim (DESIGN.md §69.55); the maths is in
:mod:`vidgen.cartoon.nature`.

A :class:`Flock` is a mobject of its own in a stage's sky (drawn after the sky, before its layers,
props and characters): each bird two short smooth strokes, placed and flapped for the scene time
by :meth:`Flock.update_to` from a scene updater. A :class:`FallenFruit` is a fruit that left its
tree: a copy of the tree's fruit as it hung there, moved by the ``drop_fruit`` action, never a part
of the tree (whose fruit is hidden instead).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from manim import Mobject, VGroup, VMobject

from vidgen.cartoon.character import Character, one_pixel_stroke
from vidgen.cartoon.effect_symbols import EffectSymbol
from vidgen.cartoon.effects import EXIT_SECONDS
from vidgen.cartoon.nature import HIT_STARS_SECONDS, DropTiming, FlockPlan, bird_outline, bird_place, drop_point, flock_box
from vidgen.cartoon.transition import PropMove

#: The birds' ink (dark in every theme, like a character's outline but a little softer), and how
#: wide their strokes are for their span (Manim stroke width per Manim unit of span).
BIRD_INK = "#2E3440"
BIRD_STROKE = 9.0


def wing_curve(start: np.ndarray, through: np.ndarray, end: np.ndarray) -> np.ndarray:
    """One cubic Bézier (Manim's 4 points) from ``start`` to ``end`` passing ``through`` half-way:
    the quadratic whose middle is there, raised to a cubic."""
    control = 2.0 * through - (start + end) / 2.0
    return np.array([start, start + 2.0 / 3.0 * (control - start), end + 2.0 / 3.0 * (control - end), end])


class Flock(VGroup):
    """The birds of ``plan``, stroked in ``color`` (:data:`BIRD_INK`) :data:`BIRD_STROKE` times
    their span wide (at least a pixel): one group of two wings per bird, without points while the
    flock is not in the air."""

    def __init__(self, plan: FlockPlan, *, color: str = BIRD_INK, name: str = "birds") -> None:
        super().__init__()
        self.plan = plan
        self.name = name
        stroke = max(BIRD_STROKE * plan.span, one_pixel_stroke())
        for _ in plan.birds:
            wings = VGroup(*(VMobject() for _ in range(2)))
            for wing in wings:
                wing.set_fill(opacity=0.0)
                wing.set_stroke(color, width=stroke, opacity=1.0)
                wing.points = np.zeros((0, 3))
            self.add(wings)

    def update_to(self, now: float) -> Flock:
        """Place and flap every bird for scene time ``now``."""
        for k, wings in enumerate(self.submobjects):
            place = bird_place(self.plan, k, now)
            if place is None:
                for wing in wings.submobjects:
                    wing.points = np.zeros((0, 3))
                continue
            x, y, lift = place
            corners = np.array([[x + px, y + py, 0.0] for px, py in bird_outline(lift, self.plan.span * self.plan.birds[k].size)])
            wings.submobjects[0].points = wing_curve(corners[0], corners[1], corners[2])
            wings.submobjects[1].points = wing_curve(corners[2], corners[3], corners[4])
        return self

    # ----- the living interface of a stage (DESIGN.md §69.54) ----------------------------------

    def changing(self, start: float, end: float) -> bool:
        """Whether a bird is in the air (or sets off or leaves) between scene times ``start`` and
        ``end``."""
        return self.plan.flying(start, end)

    def movers(self) -> list[VGroup]:
        """What it changes on every frame: itself."""
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> tuple[float, float, float, float]:
        """The box its birds cover between scene times ``start`` and ``end`` (Manim units)."""
        return flock_box(self.plan, start, end) or (0.0, 0.0, 0.0, 0.0)

    def done(self, now: float) -> bool:
        """Whether every bird has left (after scene time ``now`` nothing changes any more)."""
        return now > self.plan.end


def fruit_skin(members: Sequence[VMobject]) -> VMobject:
    """The round skin among a fruit's members (the widest: not the stalk or the shine)."""
    return max(members, key=lambda m: m.width)


class FallenFruit(VGroup):
    """A fruit off its tree ``fruit_of``: copies of the tree's members of fruit ``index`` as they
    are on screen now, at the ``opacities`` (fill, stroke) they were drawn with. A
    :class:`~vidgen.cartoon.transition.PropMove` moves and turns it by its skin's middle
    (:meth:`grip_point`)."""

    def __init__(self, members: list[VMobject], *, fruit_of: str, index: int, opacities: list[tuple[float, float]]) -> None:
        super().__init__()
        self.fruit_of = fruit_of
        self.index = index
        self.name = f"{fruit_of}_fruit_{index + 1}"
        for member, (fill, stroke) in zip(members, opacities):
            copy = member.copy()
            copy.clear_updaters()
            copy.set_fill(opacity=fill)
            copy.set_stroke(opacity=stroke)
            self.add(copy)
        self.skin = fruit_skin(self.submobjects)

    def grip_point(self) -> np.ndarray:
        """The middle of its skin on screen now."""
        return np.array(self.skin.get_center(), dtype=float)


class FruitDrop(PropMove):
    """A :class:`FallenFruit` falling from where it hung: to ``impact`` (the ground or a head) at
    ``timing.impact`` of the animation (its ``lands_at``: the thud), then bouncing ``bounce`` high
    to ``end`` (:func:`~vidgen.cartoon.nature.drop_point`; middles of the fruit, Manim units).
    ``stars`` (a :func:`hit_stars` symbol) start circling at the impact."""

    def __init__(self, fruit: Mobject, *, impact: Sequence[float], end: Sequence[float], timing: DropTiming, bounce: float,
                 stars: EffectSymbol | None = None, **kwargs) -> None:
        hit = (float(impact[0]), float(impact[1]))

        def path(u: float, start: np.ndarray, finish: np.ndarray) -> tuple[float, float, float]:
            return drop_point(u, (float(start[0]), float(start[1])), hit, (float(finish[0]), float(finish[1])),
                              hit_share=timing.impact, bounce=bounce)

        super().__init__(fruit, to=[float(end[0]), float(end[1])], path=path, lands=True, **kwargs)
        self.lands_at = timing.impact
        self.stars = stars

    def interpolate_mobject(self, alpha: float) -> None:
        super().interpolate_mobject(alpha)
        if self.stars is not None and self.stars.age < 0 and self.rate_func(alpha) >= self.lands_at:
            self.stars.age = 0.0


def hit_stars(character: Character, *, color: str) -> EffectSymbol:
    """The stars that circle ``character``'s head once a fruit falls on it (Step 107's ``stars``
    symbol in ``color``): hidden until a :class:`FruitDrop` sets its ``age`` to 0, then
    :data:`~vidgen.cartoon.nature.HIT_STARS_SECONDS` long, shrinking away; ``done`` once gone."""
    symbol = EffectSymbol("stars", color=color, character_height=character.character_height)
    symbol.follow(character)
    symbol.age = -1e6   # hidden (no size before 0) until the impact sets it to 0
    symbol.done = False

    def leave(mob: Mobject) -> None:
        if mob.leaving is None and mob.age >= HIT_STARS_SECONDS:
            mob.leaving = mob.age
        mob.done = mob.leaving is not None and mob.age - mob.leaving > EXIT_SECONDS

    symbol.add_updater(leave)
    return symbol


__all__ = ["BIRD_INK", "FallenFruit", "Flock", "FruitDrop", "fruit_skin", "hit_stars", "wing_curve"]
