"""A hologram display (DESIGN.md §100.10): a projector on the floor or a desk throwing a floating,
translucent panel of light that shows moving patterns. The maths, no manim;
:mod:`vidgen.cartoon.living_drawing` draws it.

The ``hologram_display`` prop is switched like a television: ``on: true`` starts it on,
``switch_on`` makes the panel grow out of the projector's beam in :data:`GROW_SECONDS` (with a
flicker), ``switch_off`` puts it out. Its ``pattern`` is ``fractal`` (curves of light turning
and breathing, a spiral growing), ``data`` (bars rising and falling, a wave running across, a
ring gauge) or ``text`` (lines being written one after another, then scrolling on). Everything
is in prop units: the projector's foot at (0, 0), the top at 1; the panel's corners
:data:`PANEL`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from vidgen.cartoon.living import _noise, _unit

#: The patterns a display shows.
DISPLAY_PATTERNS: tuple[str, ...] = ("fractal", "data", "text")
#: The panel (left, bottom, right, top) and the projector's lens (x, y, half width) in prop units.
PANEL = (-0.46, 0.4, 0.46, 0.98)
LENS = (0.0, 0.07, 0.12)
#: Seconds the panel takes to grow out of the beam when switched on (and to fold back).
GROW_SECONDS = 0.6
#: How many curves, bars and text lines a pattern draws (the drawing keeps this many members).
CURVES = 4
BARS = 6
TEXT_LINES = 7
#: Points per curve.
CURVE_POINTS = 72
#: Text: seconds per line written, and how many lines show before they scroll.
LINE_SECONDS = 0.7

Point = tuple[float, float]


@dataclass(frozen=True)
class DisplayFrame:
    """A display as drawn at one moment: how far the panel has grown (0..1), its opacity factor
    (a flicker), and the pattern's curves (open polylines), bars (rectangles: left, bottom,
    right, top) and text lines (rectangles), all in prop units."""

    grow: float
    level: float
    curves: tuple[tuple[Point, ...], ...] = ()
    bars: tuple[tuple[float, float, float, float], ...] = ()
    lines: tuple[tuple[float, float, float, float], ...] = ()


def _panel_point(u: float, v: float, grow: float) -> Point:
    """A point ``u``, ``v`` (0..1 across and up) of the panel, grown ``grow`` from its bottom."""
    left, bottom, right, top = PANEL
    return left + (right - left) * u, bottom + (top - bottom) * v * grow


def display_frame(pattern: str, since: float | None, now: float, seed: int = 0) -> DisplayFrame | None:
    """The display at scene time ``now``, switched on at ``since`` (``None``: off, nothing
    drawn): its panel grown over :data:`GROW_SECONDS`, flickering now and then, and the
    ``pattern``'s shapes."""
    if since is None:
        return None
    age = now - since
    grow = min(max(age / GROW_SECONDS, 0.0), 1.0)
    grow = grow * grow * (3.0 - 2.0 * grow)
    level = 0.88 + 0.12 * _noise(now, seed, "display")
    if age < GROW_SECONDS * 1.5:
        level *= 0.6 + 0.4 * abs(math.sin(31.0 * age))
    if pattern == "fractal":
        return DisplayFrame(grow, level, curves=_fractal(now, grow, seed))
    if pattern == "data":
        bars, wave = _data(now, grow, seed)
        return DisplayFrame(grow, level, curves=wave, bars=bars)
    return DisplayFrame(grow, level, lines=_text(age, grow, seed))


def _fractal(now: float, grow: float, seed: int) -> tuple[tuple[Point, ...], ...]:
    """Rose curves of 3 to 6 petals turning at their own speeds and breathing, and a spiral
    winding in and out, centred on the panel."""
    curves = []
    for k in range(CURVES - 1):
        petals = 3 + k
        turn = now * (0.35 + 0.2 * k) * (-1 if k % 2 else 1)
        breathe = 0.75 + 0.25 * math.sin(now * (0.9 + 0.3 * k) + _unit(seed, "rose", k) * 6.28)
        points = []
        for j in range(CURVE_POINTS + 1):
            a = 2.0 * math.pi * j / CURVE_POINTS
            r = 0.42 * breathe * (0.35 + 0.65 * abs(math.cos(petals * a / 2.0 + turn)))
            points.append(_panel_point(0.5 + 0.55 * r * math.cos(a + turn), 0.5 + r * math.sin(a + turn), grow))
        curves.append(tuple(points))
    wind = 2.0 + 1.5 * math.sin(now * 0.5)
    spiral = []
    for j in range(CURVE_POINTS + 1):
        t = j / CURVE_POINTS
        a = 2.0 * math.pi * wind * t - now * 1.1
        spiral.append(_panel_point(0.5 + 0.22 * t * math.cos(a), 0.5 + 0.4 * t * math.sin(a), grow))
    curves.append(tuple(spiral))
    return tuple(curves)


def _data(now: float, grow: float, seed: int) -> tuple[tuple[tuple[float, float, float, float], ...], tuple[tuple[Point, ...], ...]]:
    """Bars rising and falling on the left half, a wave running along the top right, a ring
    gauge turning at the bottom right."""
    bars = []
    for k in range(BARS):
        height = 0.15 + 0.6 * (0.5 + 0.5 * _noise(now * 0.6, seed, "bar", k))
        x0, y0 = _panel_point(0.06 + k * 0.075, 0.1, grow)
        x1, y1 = _panel_point(0.06 + k * 0.075 + 0.05, 0.1 + height * 0.8, grow)
        bars.append((x0, y0, x1, y1))
    wave = tuple(_panel_point(0.55 + 0.4 * j / 40, 0.72 + 0.12 * math.sin(10.0 * j / 40 * math.pi - 3.0 * now) * math.sin(math.pi * j / 40), grow)
                 for j in range(41))
    gauge = tuple(_panel_point(0.75 + 0.13 * math.cos(a), 0.3 + 0.2 * math.sin(a), grow)
                  for a in (now * 1.5 + 4.6 * j / 30 for j in range(31)))
    return tuple(bars), (wave, gauge)


def _text(age: float, grow: float, seed: int) -> tuple[tuple[float, float, float, float], ...]:
    """Lines being written one after another (each grows to its seeded length in
    :data:`LINE_SECONDS`), scrolling up once the panel is full."""
    written = max(age, 0.0) / LINE_SECONDS
    first = max(int(written) - TEXT_LINES + 1, 0)
    lines = []
    for slot in range(TEXT_LINES):
        index = first + slot
        share = min(max(written - index, 0.0), 1.0)
        if share <= 0.0:
            break
        length = (0.45 + 0.45 * _unit(seed, "line", index)) * share
        indent = 0.08 if index % 4 else 0.04
        v = 0.88 - slot * 0.12
        x0, y0 = _panel_point(indent, v - 0.035, grow)
        x1, y1 = _panel_point(indent + length * (0.9 - indent), v, grow)
        lines.append((x0, y0, x1, y1))
    return tuple(lines)


__all__ = ["DISPLAY_PATTERNS", "GROW_SECONDS", "LENS", "PANEL", "DisplayFrame", "display_frame"]
