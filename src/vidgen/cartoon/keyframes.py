"""Keyframes and motion paths (DESIGN.md §69.14), worked out without manim: the values a
``keyframes`` action gives its target at a moment, and the curve a ``move_along`` action follows.

A target has four *channels*: ``x``, ``y``, ``rotate`` (degrees, counterclockwise) and ``scale``
(a factor). A key sets some of them at a time; a channel a key does not set holds, and between
two keys that set it the value moves with the ease of the later key. Times are seconds from the
action's start, or shares of the beat's narration written as ``"40%"``.

Eases carry the names of Manim's rate functions (``linear``, ``smooth``, ``ease_in_out_sine``,
``ease_out_back`` ...; the same curves, checked by a test), plus ``lively`` and ``calm``: a smooth
move with the anticipation and overshoot of that ``cartoon_motion`` level (§69.13).
"""

from __future__ import annotations

import bisect
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vidgen.cartoon.motion import MOTION_LEVELS, motion_ease, smoothstep

#: The channels a key may set.
CHANNELS = ("x", "y", "rotate", "scale")
#: A key time written as a share of the beat's narration: ``"40%"``.
SHARE_PATTERN = r"^\d+(\.\d+)?%$"
_SHARE = re.compile(SHARE_PATTERN)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _manim_smooth(t: float, inflection: float = 10.0) -> float:
    error = _sigmoid(-inflection / 2)
    return min(max((_sigmoid(inflection * (t - 0.5)) - error) / (1 - 2 * error), 0.0), 1.0)


def _in_out(t: float, power: int) -> float:
    return 2 ** (power - 1) * t**power if t < 0.5 else 1 - (-2 * t + 2) ** power / 2


_BACK = 1.70158


def _ease_in_out_back(t: float) -> float:
    c2 = _BACK * 1.525
    if t < 0.5:
        return (2 * t) ** 2 * ((c2 + 1) * 2 * t - c2) / 2
    return ((2 * t - 2) ** 2 * ((c2 + 1) * (2 * t - 2) + c2) + 2) / 2


def _ease_out_bounce(t: float) -> float:
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def _ease_out_elastic(t: float) -> float:
    if t <= 0 or t >= 1:
        return float(t >= 1)
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


#: Ease name -> the progress (0 at 0, 1 at 1) at a share of the time; Manim's rate functions of
#: those names, plus the ``cartoon_motion`` levels with anticipation and overshoot.
EASES: dict[str, Callable[[float], float]] = {
    "linear": lambda t: t,
    "smooth": _manim_smooth,
    "rush_into": lambda t: 2 * _manim_smooth(t / 2.0),
    "rush_from": lambda t: 2 * _manim_smooth(t / 2.0 + 0.5) - 1,
    "ease_in_sine": lambda t: 1 - math.cos(t * math.pi / 2),
    "ease_out_sine": lambda t: math.sin(t * math.pi / 2),
    "ease_in_out_sine": lambda t: -(math.cos(math.pi * t) - 1) / 2,
    "ease_in_quad": lambda t: t * t,
    "ease_out_quad": lambda t: 1 - (1 - t) ** 2,
    "ease_in_out_quad": lambda t: _in_out(t, 2),
    "ease_in_cubic": lambda t: t**3,
    "ease_out_cubic": lambda t: 1 - (1 - t) ** 3,
    "ease_in_out_cubic": lambda t: _in_out(t, 3),
    "ease_in_back": lambda t: (_BACK + 1) * t**3 - _BACK * t * t,
    "ease_out_back": lambda t: 1 + (_BACK + 1) * (t - 1) ** 3 + _BACK * (t - 1) ** 2,
    "ease_in_out_back": _ease_in_out_back,
    "ease_out_bounce": _ease_out_bounce,
    "ease_out_elastic": _ease_out_elastic,
    "lively": lambda t: motion_ease(t, MOTION_LEVELS["lively"], smoothstep),
    "calm": lambda t: motion_ease(t, MOTION_LEVELS["calm"], smoothstep),
}
EASE_NAMES = tuple(EASES)
#: The ease of a key that names none (and of an action that names none).
DEFAULT_EASE = "smooth"
#: An ``ease:`` value.
EaseName = Literal[EASE_NAMES]  # type: ignore[valid-type]


def ease_progress(name: str, share: float) -> float:
    """Ease ``name`` at ``share`` (clamped to 0..1) of a move."""
    return EASES[name](min(max(share, 0.0), 1.0))


# ----- key times ----------------------------------------------------------------------------------


def is_share(t: float | str) -> bool:
    """Whether a key time is a share of the beat (``"40%"``) rather than seconds."""
    return isinstance(t, str)


def key_seconds(t: float | str, beat_seconds: float) -> float:
    """A key time in seconds from the action's start: seconds as given, ``"40%"`` as 0.4 of the
    beat's narration (``beat_seconds``)."""
    if isinstance(t, str):
        if not _SHARE.match(t):
            raise ValueError(f"a key time is seconds (1.5) or a share of the beat ('40%'), not {t!r}")
        return float(t[:-1]) / 100.0 * beat_seconds
    return float(t)


def key_time_problems(times: Sequence[float | str]) -> list[tuple[int | None, str]]:
    """Problems of a ``keys`` list's times, as (key index or ``None`` for the list, message): all
    in seconds or all shares of the beat (so they can be ordered without the audio), each later
    than the one before, a share at most 100 %."""
    if not times:
        return [(None, "give at least one key")]
    if len({is_share(t) for t in times}) > 1:
        return [(None, "give every key's t in seconds (1.5) or every one as a share of the beat ('40%'), not both")]
    problems: list[tuple[int | None, str]] = []
    values = [key_seconds(t, 1.0) for t in times]
    for k, t in enumerate(times):
        if is_share(t) and values[k] > 1.0:
            problems.append((k, f"t {t} is past the end of the beat (at most 100%)"))
        if k and values[k] <= values[k - 1]:
            problems.append((k, f"t {t} is not after the key before ({times[k - 1]}); keys go in time order"))
    return problems


class KeyFrame(BaseModel):
    """One key of a ``keyframes`` action: a time and the channels it sets."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    t: Annotated[float, Field(ge=0.0, le=600.0, strict=True)] | Annotated[str, Field(pattern=SHARE_PATTERN)]
    """When: seconds from the action's start (1.5), or a share of the beat's narration ('40%')."""
    x: str | float | None = None
    """A character or prop: a mark or an x from 0 (left edge) to 1 (right edge) of the stage; a part: its shift right, in character heights."""
    y: float | None = Field(None, ge=-2.0, le=2.0)
    """A character or prop: the height of its feet above its ground line, in frame heights; a part: its shift up, in character heights."""
    rotate: float | None = Field(None, ge=-1080.0, le=1080.0)
    """Degrees counterclockwise: a character or prop about its feet, on screen; a part about its pivot, as drawn facing right."""
    scale: float | None = Field(None, gt=0.0, le=10.0)
    """Size factor: a character or prop about its feet; a part about its pivot."""
    ease: EaseName | None = None  # type: ignore[valid-type]
    """How it moves from the key before to this one (linear, smooth, ease_in_out_sine, ease_out_back, lively, ...); default: the action's ease."""

    @model_validator(mode="after")
    def _sets_something(self) -> KeyFrame:
        if all(getattr(self, c) is None for c in CHANNELS):
            raise ValueError("a key sets at least one of x, y, rotate, scale")
        return self

    def values(self) -> dict[str, float | str]:
        """The channels it sets."""
        return {c: getattr(self, c) for c in CHANNELS if getattr(self, c) is not None}


# ----- interpolation ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Key:
    """A key resolved for drawing: ``seconds`` from the action's start, the channel values it
    sets (in the units the animation uses), the ease into it."""

    seconds: float
    values: Mapping[str, float]
    ease: str = DEFAULT_EASE


def keyed_values(start: Mapping[str, float], keys: Sequence[Key], seconds: float) -> dict[str, float]:
    """Every channel of ``start`` at ``seconds`` from the action's start: ``start`` (the target
    as it was) before the first key that sets the channel, then from key to key with the later
    key's ease, held after the last. A key at 0 s sets its channels at once. ``keys`` are in time
    order (:func:`key_time_problems`)."""
    out: dict[str, float] = {}
    for channel, value in start.items():
        before_t, before_v = 0.0, value
        for key in keys:
            if channel not in key.values:
                continue
            if seconds < key.seconds:
                span = key.seconds - before_t
                share = (seconds - before_t) / span if span > 0 else 1.0
                value = before_v + (key.values[channel] - before_v) * ease_progress(key.ease, share)
                break
            before_t, before_v = key.seconds, key.values[channel]
            value = before_v
        out[channel] = value
    return out


# ----- motion paths -------------------------------------------------------------------------------

#: Straight pieces a smooth path's segment is measured and drawn with.
PATH_SAMPLES = 32


def _hermite(p0: Sequence[float], p1: Sequence[float], m0: Sequence[float], m1: Sequence[float], s: float) -> tuple[float, float]:
    h00, h10 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s
    h01, h11 = -2 * s**3 + 3 * s**2, s**3 - s**2
    return (
        h00 * p0[0] + h10 * m0[0] + h01 * p1[0] + h11 * m1[0],
        h00 * p0[1] + h10 * m0[1] + h01 * p1[1] + h11 * m1[1],
    )


def path_curve(points: Sequence[Sequence[float]], smooth: bool = True, samples: int = PATH_SAMPLES) -> list[tuple[float, float]]:
    """The path through ``points`` (x, y) as a polyline: the points themselves when not
    ``smooth``; else a Catmull-Rom curve (each point's tangent half the way from the point before
    to the point after; the ends' from their one neighbour) sampled ``samples`` times a segment."""
    pts = [(float(p[0]), float(p[1])) for p in points]
    if not smooth or len(pts) < 3:
        return pts
    tangents = []
    for k in range(len(pts)):
        a, b = pts[max(k - 1, 0)], pts[min(k + 1, len(pts) - 1)]
        share = 0.5 if 0 < k < len(pts) - 1 else 1.0
        tangents.append(((b[0] - a[0]) * share, (b[1] - a[1]) * share))
    curve = [pts[0]]
    for k in range(len(pts) - 1):
        curve += [_hermite(pts[k], pts[k + 1], tangents[k], tangents[k + 1], j / samples) for j in range(1, samples + 1)]
    return curve


def _cumulative(curve: Sequence[tuple[float, float]]) -> list[float]:
    lengths = [0.0]
    for a, b in zip(curve, curve[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    return lengths


def path_length(points: Sequence[Sequence[float]], smooth: bool = True) -> float:
    """The length of the path through ``points`` (:func:`path_curve`), in the points' units."""
    return _cumulative(path_curve(points, smooth))[-1]


@dataclass(frozen=True)
class MotionPath:
    """A path through ``points`` (:func:`path_curve`), walked at an even speed: :meth:`at` gives
    the point ``share`` of its length along."""

    points: tuple[tuple[float, float], ...]
    smooth: bool = True
    curve: tuple[tuple[float, float], ...] = field(init=False, repr=False)
    lengths: tuple[float, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        curve = path_curve(self.points, self.smooth)
        object.__setattr__(self, "curve", tuple(curve))
        object.__setattr__(self, "lengths", tuple(_cumulative(curve)))

    @property
    def length(self) -> float:
        """Its length, in the points' units."""
        return self.lengths[-1]

    def at(self, share: float) -> tuple[float, float]:
        """The point ``share`` (0..1, clamped) of the length along."""
        if self.length <= 0:
            return self.curve[0]
        wanted = min(max(share, 0.0), 1.0) * self.length
        k = min(max(bisect.bisect_right(self.lengths, wanted) - 1, 0), len(self.curve) - 2)
        piece = self.lengths[k + 1] - self.lengths[k]
        u = (wanted - self.lengths[k]) / piece if piece > 0 else 0.0
        (x0, y0), (x1, y1) = self.curve[k], self.curve[k + 1]
        return (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u)


__all__ = [
    "CHANNELS",
    "DEFAULT_EASE",
    "EASES",
    "EASE_NAMES",
    "EaseName",
    "Key",
    "KeyFrame",
    "MotionPath",
    "PATH_SAMPLES",
    "SHARE_PATTERN",
    "ease_progress",
    "is_share",
    "key_seconds",
    "key_time_problems",
    "keyed_values",
    "path_curve",
    "path_length",
]
