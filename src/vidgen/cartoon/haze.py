"""Shimmering air over a spot (DESIGN.md §102.12): the maths of a heat-haze ripple, no manim;
:class:`~vidgen.cartoon.iso_overlays.IsoHaze` draws it over an iso place.

A haze is a column of faint, wavering ribbons of light rising from its foot, swaying more the
higher they go and tapering at both ends, a soft glow on the floor under it and a few small
sparkles drifting up through it. Everything is in the haze's own units: ``u`` across (-0.5 ..
0.5 of its width), ``v`` up (0 at its foot, 1 at its top).
"""

from __future__ import annotations

import math

from vidgen.cartoon.living import _unit

#: How many ribbons and sparkles a haze has, and the corners down each side of a ribbon.
HAZE_RIBBONS = 7
HAZE_SPARKS = 8
RIBBON_POINTS = 12
#: A ribbon's half width at its widest (a share of the haze's width), how far it sways (at its
#: top, a share of the width) and how fast its ripple climbs (cycles a second).
RIBBON_HALF = 0.045
RIBBON_SWAY = 0.09
RIPPLE_SPEED = 0.9
#: Seconds a sparkle takes to rise through the haze, and its size (a share of the width).
SPARK_SECONDS = 2.6
SPARK_SIZE = 0.05
#: Seconds a haze takes to fade in from its ``from``.
HAZE_FADE = 0.8

Point = tuple[float, float]


def haze_level(now: float, start: float = 0.0) -> float:
    """How much a haze that fades in from scene time ``start`` shows at ``now`` (0 .. 1)."""
    share = min(max((now - start) / HAZE_FADE, 0.0), 1.0)
    return share * share * (3.0 - 2.0 * share)


def haze_ribbons(now: float, seed: int = 0, count: int = HAZE_RIBBONS) -> list[tuple[tuple[Point, ...], float]]:
    """The ribbons at scene time ``now``: each an outline (up its left side, down its right) in
    haze units and its opacity share (0.35 .. 1, breathing slowly). Each sways on a ripple that
    climbs it, more towards the top, and tapers at both ends."""
    out = []
    for k in range(count):
        across = (k + 0.5) / count - 0.5
        phase = _unit(seed, "ribbon", k)
        left: list[Point] = []
        right: list[Point] = []
        for j in range(RIBBON_POINTS):
            v = j / (RIBBON_POINTS - 1)
            sway = RIBBON_SWAY * (0.3 + v) * math.sin(2.0 * math.pi * (1.6 * v - RIPPLE_SPEED * now + phase))
            half = RIBBON_HALF * math.sin(math.pi * v) ** 0.6 * (1.0 - 0.4 * v)
            u = across * (1.0 - 0.25 * v) + sway
            left.append((u - half, v))
            right.append((u + half, v))
        breathe = 0.675 + 0.325 * math.sin(2.0 * math.pi * (0.3 * now + phase))
        out.append(((*left, *reversed(right)), breathe))
    return out


def haze_sparks(now: float, seed: int = 0, count: int = HAZE_SPARKS) -> list[tuple[float, float, float, float]]:
    """The sparkles at scene time ``now``: (u, v, size, opacity) each, rising through the haze
    over :data:`SPARK_SECONDS` one after another, swaying a little, brightest half-way up."""
    out = []
    for k in range(count):
        v = (now / SPARK_SECONDS + (k + _unit(seed, "spark", k)) / count) % 1.0
        u = (_unit(seed, "spark_u", k) - 0.5) * 0.8 + 0.05 * math.sin(2.0 * math.pi * (v + _unit(seed, "spark_s", k)))
        out.append((u, v, SPARK_SIZE * (0.6 + 0.4 * _unit(seed, "spark_r", k)), math.sin(math.pi * v)))
    return out


__all__ = ["HAZE_FADE", "HAZE_RIBBONS", "HAZE_SPARKS", "haze_level", "haze_ribbons", "haze_sparks"]
