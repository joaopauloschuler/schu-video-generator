"""The sun's and the moon's path across a stage's sky and the shadows they cast (DESIGN.md
§69.61). No manim: the stage moves its ``sun`` and ``moon`` props and turns the shadows.

A body's place is a *path share*: 0 on the horizon at the left (east), 0.5 at the top of its arc,
1 on the horizon at the right (west); below the horizon the path goes on hidden for
:data:`PATH_HIDDEN` at each end and comes round, so a sun that set (1.08) rises again at the left
(-0.08 → 0) when the light turns to ``morning``. A ``light`` change with ``move_sun`` moves every
sun and moon forward along the path, never back, to the place of the new light
(:data:`PATH_PLACES`), eased like the light's fade.

The higher the sun, the shorter the shadows: a shadow is stretched along the ground away from the
sun by :func:`shadow_cast` (cot of its elevation, at most :data:`MAX_SHADOW_STRETCH`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from vidgen.cartoon.lighting import ShadowEllipse, fade_at

#: The props that move along the sky's path.
SKY_BODIES = ("sun", "moon")
#: The path's hidden length beyond each horizon (path shares), and one round of it.
PATH_HIDDEN = 0.08
PATH_ROUND = 1.0 + 2 * PATH_HIDDEN
#: The share of the stage's width left free at each end of the arc, how high its top is above the
#: horizon (a share of the room up to the frame's top edge) and how high (path height) a body
#: must be to show fully (it fades in rising and out setting).
PATH_MARGIN = 0.1
PATH_TOP = 0.8
RISE_FADE = 0.15
#: Where each body is under each light preset (path shares; beyond 0..1: below the horizon).
PATH_PLACES: dict[str, dict[str, float]] = {
    "sun": {"morning": 0.1, "day": 0.5, "sunset": 0.9, "night": 1.0 + PATH_HIDDEN, "indoor": 1.0 + PATH_HIDDEN},
    "moon": {"morning": 0.9, "day": -PATH_HIDDEN, "sunset": 0.1, "night": 0.5, "indoor": 0.3},
}
#: The sun's highest elevation (degrees, at the top of the arc).
TOP_ELEVATION = 65.0
#: Shadows: the longest stretch (cot of the elevation), how far the stretch reaches (a shadow's
#: widths per unit of stretch) and how much a long shadow softens (opacity divided by 1 + this ×
#: stretch).
MAX_SHADOW_STRETCH = 3.0
SHADOW_REACH = 0.6
SHADOW_SOFTEN = 0.25


def wrap_share(share: float) -> float:
    """``share`` brought into one round of the path, ``-PATH_HIDDEN`` .. ``1 + PATH_HIDDEN``
    (unchanged when it is in it already)."""
    s = float(share)
    return s if -PATH_HIDDEN <= s < 1.0 + PATH_HIDDEN else (s + PATH_HIDDEN) % PATH_ROUND - PATH_HIDDEN


def path_blend(start: float, end: float, share: float) -> float:
    """``share`` (0..1) of the way from path share ``start`` forward to ``end`` (round the path
    when ``end`` is behind), wrapped (:func:`wrap_share`)."""
    ahead = (wrap_share(end) - wrap_share(start)) % PATH_ROUND
    return wrap_share(wrap_share(start) + ahead * float(share))


@dataclass(frozen=True)
class PathMove:
    """A body moving along the path to share ``value`` from scene time ``start`` over ``seconds``
    (0: at once)."""

    start: float
    seconds: float
    value: float

    @property
    def end(self) -> float:
        """When it is there."""
        return self.start + max(self.seconds, 0.0)


def path_share_at(base: float, moves: Sequence[PathMove], now: float) -> float:
    """Where a body starting at path share ``base`` is at scene time ``now`` (each move eased like
    a light's fade, :func:`~vidgen.cartoon.lighting.fade_at`)."""
    return wrap_share(fade_at(wrap_share(base), moves, now, path_blend))


def place_for(body: str, light: str) -> float:
    """The path share of ``body`` (``sun`` or ``moon``) under the light preset ``light``."""
    return PATH_PLACES[body][light]


def path_height(share: float) -> float:
    """How high a body at ``share`` is: 1 at the top of the arc, 0 on the horizon, below 0 under it."""
    return math.sin(math.pi * float(share))


def path_point(share: float) -> tuple[float, float, float]:
    """A body at path share ``share``: its x (0..1 of the stage's width), its height (0 on the
    horizon .. 1 at the arc's top; below 0 under it) and how much of it shows (0..1)."""
    s = float(share)
    height = path_height(s) if 0.0 <= s <= 1.0 else -abs(path_height(s))
    shown = min(max(height / RISE_FADE, 0.0), 1.0)
    return PATH_MARGIN + s * (1.0 - 2 * PATH_MARGIN), height, shown * shown * (3.0 - 2.0 * shown)


def elevation(share: float) -> float:
    """The elevation (degrees) of a body at ``share``; 0 at or under the horizon."""
    return TOP_ELEVATION * max(path_height(share), 0.0) if 0.0 <= share <= 1.0 else 0.0


def shadow_cast(share: float | None) -> tuple[float, float]:
    """``(stretch, side)`` of the shadows a sun (or moon) at path share ``share`` casts: how long
    (cot of its elevation, at most :data:`MAX_SHADOW_STRETCH`; 0 with the body straight overhead
    or none, ``None``) and which way they point (+1 right, away from a body in the east; -1 left).
    A body under the horizon casts long shadows away from where it set or will rise."""
    if share is None:
        return 0.0, 0.0
    s = wrap_share(share)
    side = 1.0 if s < 0.5 else -1.0 if s > 0.5 else 0.0
    angle = elevation(s)
    stretch = MAX_SHADOW_STRETCH if angle <= 0 else min(1.0 / math.tan(math.radians(angle)), MAX_SHADOW_STRETCH)
    return stretch, side


def cast_shadow(ellipse: ShadowEllipse, stretch: float, side: float) -> ShadowEllipse:
    """``ellipse`` cast by a low sun: ``stretch`` × :data:`SHADOW_REACH` of its width longer,
    reaching out on ``side`` (+1 right, -1 left; its foot stays under the caster) and softer.
    ``ellipse`` itself when ``stretch`` or ``side`` is 0."""
    if stretch <= 0 or side == 0:
        return ellipse
    extra = ellipse.width * SHADOW_REACH * stretch
    return ShadowEllipse(
        ellipse.x + side * extra / 2, ellipse.y, ellipse.width + extra, ellipse.height, ellipse.opacity / (1.0 + SHADOW_SOFTEN * stretch),
    )


__all__ = [
    "MAX_SHADOW_STRETCH",
    "PATH_HIDDEN",
    "PATH_PLACES",
    "SKY_BODIES",
    "PathMove",
    "cast_shadow",
    "elevation",
    "path_blend",
    "path_height",
    "path_point",
    "path_share_at",
    "place_for",
    "shadow_cast",
    "wrap_share",
]
