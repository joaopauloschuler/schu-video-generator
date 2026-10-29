"""A portal (a rift in space) that opens, crackles, pulses and seals (DESIGN.md §100.4): the
maths, without manim. :mod:`vidgen.cartoon.living_drawing` draws it.

The ``portal`` prop is switched like a lamp: ``on: true`` starts it open, ``switch_on`` opens it
and ``switch_off`` seals it. Opening takes :data:`OPEN_SECONDS`: a thin glowing crack grows to
its full height, then splits open into an oval (:func:`openness`, :func:`opening_size`). While
open its rim crackles (a jagged edge, new jags :data:`CRACKLE_RATE` times a second), sparks fly
off the rim, swirls turn inside, and the whole pulses gently; sealing (:data:`CLOSE_SECONDS`) is
the opening backwards, faster. Everything is in prop units as drawn facing right: the foot's
middle at (0, 0), the top at 1, the oval's middle at :data:`CENTRE`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from vidgen.cartoon.living import _noise, _unit

#: The oval's middle and half sizes (prop units).
CENTRE = (0.0, 0.5)
HALF_WIDTH = 0.2
HALF_HEIGHT = 0.4
#: The box the drawing keeps to (sparks included): left, bottom, right, top in prop units.
EXTENT = (-0.3, 0.0, 0.3, 1.0)
#: Seconds to open and to seal.
OPEN_SECONDS = 1.6
CLOSE_SECONDS = 1.0
#: The share of the opening during which the crack grows to its full height (then it widens).
CRACK_SHARE = 0.4
#: The narrowest the oval is drawn (a share of its width): a crack.
CRACK_WIDTH = 0.04
#: The rim: corners round the oval, how often its jags change (per second) and how far they reach
#: (a share of the radius, either way).
RIM_POINTS = 36
CRACKLE_RATE = 14.0
JAG = 0.07
#: The pulse: seconds per beat and how much the oval grows and shrinks (a share).
PULSE_SECONDS = 1.8
PULSE = 0.03
#: The swirls inside: how many arms, how fast they turn (radians a second), points per arm.
SWIRL_ARMS = 3
SWIRL_SPEED = 0.9
SWIRL_POINTS = 12
#: The depth rings inside (shares of the oval's size).
DEPTH_RINGS = (0.72, 0.42)
#: Sparks: how many at a time, how long one lasts (s), how long it is (prop units, at most).
SPARKS = 6
SPARK_SECONDS = 0.28
SPARK_LENGTH = 0.08

Point = tuple[float, float]


def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def openness(on_at_start: bool, switches: Sequence[tuple[float, bool]], now: float) -> float:
    """How open a portal is at scene time ``now`` (0 sealed .. 1 open): open from the start when
    ``on_at_start``; each switch (scene time, on) opens it over :data:`OPEN_SECONDS` or seals it
    over :data:`CLOSE_SECONDS` from where it was."""
    level = 1.0 if on_at_start else 0.0
    last_time, last_level, target = 0.0, level, level
    for time, on in sorted((s for s in switches if s[0] <= now), key=lambda s: s[0]):
        level = _level_at(last_level, target, float(time) - last_time)
        last_time, last_level, target = float(time), level, 1.0 if on else 0.0
    return _level_at(last_level, target, now - last_time)


def _level_at(start: float, target: float, elapsed: float) -> float:
    """The level ``elapsed`` seconds after it set off from ``start`` towards ``target`` at the
    opening or sealing speed (a straight ramp; :func:`opening_size` eases it)."""
    if target > start:
        return min(target, start + max(elapsed, 0.0) / OPEN_SECONDS)
    return max(target, start - max(elapsed, 0.0) / CLOSE_SECONDS)


def opening_size(level: float) -> tuple[float, float]:
    """(width share, height share) of the oval at ``level`` of :func:`openness`: the crack grows
    to its full height in the first :data:`CRACK_SHARE`, then widens from :data:`CRACK_WIDTH`."""
    if level <= 0.0:
        return 0.0, 0.0
    height = _ease(level / CRACK_SHARE)
    width = CRACK_WIDTH + (1.0 - CRACK_WIDTH) * _ease((level - CRACK_SHARE * 0.6) / (1.0 - CRACK_SHARE * 0.6))
    return width, height


def changing(on_at_start: bool, switches: Sequence[tuple[float, bool]], start: float, end: float) -> bool:
    """Whether a portal shows anything that moves between scene times ``start`` and ``end``: it is
    open (or opening, or sealing) at either end, or switched in between."""
    if any(start <= time <= end for time, _ in switches):
        return True
    return openness(on_at_start, switches, start) > 0.0 or openness(on_at_start, switches, end) > 0.0


@dataclass(frozen=True)
class PortalShape:
    """A portal as it is drawn at one moment (prop units): the oval's outline (``inside``: the
    smooth oval, ``rim``: its crackling edge), the depth rings, the swirl arms (open polylines),
    the sparks (two points each) and how strongly it glows (0-1)."""

    inside: tuple[Point, ...]
    rim: tuple[Point, ...]
    rings: tuple[tuple[Point, ...], ...]
    swirls: tuple[tuple[Point, ...], ...]
    sparks: tuple[tuple[Point, Point], ...]
    glow: float


def _oval(rx: float, ry: float, n: int, jag: Sequence[float] | None = None) -> tuple[Point, ...]:
    cx, cy = CENTRE
    out = []
    for k in range(n):
        a = 2.0 * math.pi * k / n
        grow = 1.0 + (jag[k] if jag is not None else 0.0)
        out.append((cx + rx * grow * math.cos(a), cy + ry * grow * math.sin(a)))
    return tuple(out)


def portal_shape(level: float, now: float, seed: int = 0) -> PortalShape | None:
    """The portal at :func:`openness` ``level`` and scene time ``now`` (``seed`` varies its
    crackle, swirls and sparks); ``None`` while sealed."""
    width, height = opening_size(level)
    if height <= 0.0:
        return None
    pulse = 1.0 + PULSE * math.sin(2.0 * math.pi * now / PULSE_SECONDS) * width
    rx, ry = HALF_WIDTH * width * pulse, HALF_HEIGHT * height * pulse
    tick = math.floor(now * CRACKLE_RATE)
    jag = [JAG * (2.0 * _unit(seed, "jag", tick, k) - 1.0) for k in range(RIM_POINTS)]
    rings = tuple(_oval(rx * share, ry * share, RIM_POINTS) for share in DEPTH_RINGS)
    cx, cy = CENTRE
    swirls = []
    for arm in range(SWIRL_ARMS):
        turn = now * SWIRL_SPEED + 2.0 * math.pi * arm / SWIRL_ARMS
        points = []
        for k in range(SWIRL_POINTS):
            t = k / (SWIRL_POINTS - 1)
            a = turn + 2.4 * t
            r = 0.15 + 0.7 * t
            points.append((cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)))
        swirls.append(tuple(points))
    sparks = []
    for k in range(SPARKS):
        life = math.floor((now + k * SPARK_SECONDS / SPARKS) / SPARK_SECONDS)
        age = ((now + k * SPARK_SECONDS / SPARKS) / SPARK_SECONDS) % 1.0
        a = 2.0 * math.pi * _unit(seed, "spark", k, life)
        length = SPARK_LENGTH * (0.5 + 0.5 * _unit(seed, "spark_length", k, life)) * width * (1.0 - age)
        start = (cx + rx * math.cos(a), cy + ry * math.sin(a))
        end = (start[0] + length * math.cos(a), start[1] + length * math.sin(a))
        sparks.append((start, end))
    glow = width * (0.85 + 0.15 * _noise(now, seed, "portal_glow"))
    return PortalShape(_oval(rx, ry, RIM_POINTS), _oval(rx, ry, RIM_POINTS, jag), rings, tuple(swirls), tuple(sparks), max(glow, 0.0))


__all__ = [
    "CENTRE",
    "CLOSE_SECONDS",
    "CRACKLE_RATE",
    "EXTENT",
    "HALF_HEIGHT",
    "HALF_WIDTH",
    "OPEN_SECONDS",
    "PortalShape",
    "changing",
    "opening_size",
    "openness",
    "portal_shape",
]
