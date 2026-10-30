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
DISPLAY_PATTERNS: tuple[str, ...] = ("fractal", "data", "text", "equations", "timelines")
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
#: ``equations`` and ``timelines`` (DESIGN.md §102.10): how many glyph strokes, wings, small
#: panels and dots they draw at most (the drawing keeps this many members).
GLYPHS = 48
WINGS = 12
BOXES = 8
DOTS = 16
#: Where the floating formulas may drift (prop units): within the display's glow, over the
#: panel and a little round it.
FLOAT_BOX = (-0.62, 0.42, 0.62, 1.34)
#: Formula butterflies: how many, the seconds one takes to drift up and away, its size (prop
#: units) and how often its wings beat (Hz).
BUTTERFLIES = 6
BUTTERFLY_SECONDS = 5.5
BUTTERFLY_SIZE = 0.11
WING_BEATS = 1.6
#: Timelines: the branching levels of the tree (its tips hold the panels), the seconds it takes to
#: grow, and the seconds of one meeting in a panel (two figures coming together, a pulse).
TIMELINE_LEVELS = 3
TIMELINE_GROW = 1.6
MEETING_SECONDS = 3.2

Point = tuple[float, float]


@dataclass(frozen=True)
class DisplayFrame:
    """A display as drawn at one moment: how far the panel has grown (0..1), its opacity factor
    (a flicker), and the pattern's curves (open polylines), bars (rectangles: left, bottom,
    right, top) and text lines (rectangles), all in prop units. ``equations`` and ``timelines``
    add ``glyphs`` (thin open strokes: formula symbols, a tree's branches), ``wings`` (closed
    outlines, filled faintly), ``boxes`` (small faint panels) and ``dots`` (x, y, radius)."""

    grow: float
    level: float
    curves: tuple[tuple[Point, ...], ...] = ()
    bars: tuple[tuple[float, float, float, float], ...] = ()
    lines: tuple[tuple[float, float, float, float], ...] = ()
    glyphs: tuple[tuple[Point, ...], ...] = ()
    wings: tuple[tuple[Point, ...], ...] = ()
    boxes: tuple[tuple[float, float, float, float], ...] = ()
    dots: tuple[tuple[float, float, float], ...] = ()


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
    if pattern == "equations":
        glyphs, wings = _equations(now, age, grow, seed)
        return DisplayFrame(grow, level, glyphs=glyphs, wings=wings)
    if pattern == "timelines":
        glyphs, boxes, dots = _timelines(now, age, grow, seed)
        return DisplayFrame(grow, level, glyphs=glyphs, boxes=boxes, dots=dots)
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


# ----- floating formulas and timelines (DESIGN.md §102.10) ----------------------------------------

#: Formula symbols as strokes in a unit box (x across, y up, 0..1): a sum, an integral, equals,
#: x, psi, pi, a root, plus.
GLYPH_STROKES: dict[str, tuple[tuple[Point, ...], ...]] = {
    "sum": (((0.9, 1.0), (0.1, 1.0), (0.55, 0.5), (0.1, 0.0), (0.9, 0.0)),),
    "integral": (((0.8, 0.95), (0.65, 1.0), (0.52, 0.86), (0.48, 0.14), (0.35, 0.0), (0.2, 0.05)),),
    "equals": (((0.15, 0.65), (0.85, 0.65)), ((0.15, 0.35), (0.85, 0.35))),
    "x": (((0.15, 0.85), (0.85, 0.15)), ((0.15, 0.15), (0.85, 0.85))),
    "psi": (((0.5, 1.0), (0.5, 0.0)), ((0.1, 0.8), (0.2, 0.45), (0.5, 0.33), (0.8, 0.45), (0.9, 0.8))),
    "pi": (((0.05, 0.85), (0.95, 0.85)), ((0.3, 0.85), (0.3, 0.05)), ((0.7, 0.85), (0.7, 0.05), (0.85, 0.0))),
    "root": (((0.0, 0.45), (0.15, 0.5), (0.35, 0.0), (0.6, 1.0), (1.0, 1.0)),),
    "plus": (((0.5, 0.85), (0.5, 0.15)), ((0.15, 0.5), (0.85, 0.5))),
}
#: The formulas written on the panel, row by row, and the symbol each butterfly carries.
FORMULAS: tuple[tuple[str, ...], ...] = (("psi", "equals", "sum", "x"), ("integral", "psi", "x"), ("root", "x", "plus", "pi"))
BUTTERFLY_GLYPHS: tuple[str, ...] = ("psi", "sum", "pi", "integral", "x", "root")
#: Seconds the panel's formulas take to be written, a symbol after another.
WRITE_SECONDS = 2.4


def _glyph(name: str, x: float, y: float, size: float) -> list[tuple[Point, ...]]:
    """Symbol ``name``'s strokes, ``size`` tall (and as wide) with its bottom left at (x, y)."""
    return [tuple((x + px * size, y + py * size) for px, py in stroke) for stroke in GLYPH_STROKES[name]]


def _clamped(x: float, y: float) -> Point:
    left, bottom, right, top = FLOAT_BOX
    return min(max(x, left), right), min(max(y, bottom), top)


def _equations(now: float, age: float, grow: float, seed: int) -> tuple[tuple[tuple[Point, ...], ...], tuple[tuple[Point, ...], ...]]:
    """Formulas written on the panel, symbol by symbol, and formula "butterflies": a symbol
    between two beating wings, each rising from the panel and drifting up and out of it on a
    swaying path, growing in and shrinking away (one after another, looping)."""
    glyphs: list[tuple[Point, ...]] = []
    size = 0.075
    written = max(age, 0.0) / WRITE_SECONDS * sum(len(f) for f in FORMULAS)
    count = 0
    for row, formula in enumerate(FORMULAS):
        for k, name in enumerate(formula):
            if count >= written:
                break
            count += 1
            x, y = _panel_point(0.08 + k * 0.12, 0.74 - row * 0.27, grow)
            glyphs += _glyph(name, x, y, size * grow)
    wings: list[tuple[Point, ...]] = []
    for k in range(BUTTERFLIES):
        share = (now / BUTTERFLY_SECONDS + k / BUTTERFLIES + _unit(seed, "fly", k) * 0.1) % 1.0
        shown = math.sin(math.pi * share) ** 0.6 * grow
        if shown < 0.05:
            continue
        side = -1.0 if k % 2 else 1.0
        x0, y0 = _panel_point(0.25 + 0.5 * _unit(seed, "from", k), 0.3 + 0.35 * _unit(seed, "rise", k), 1.0)
        sway = 2.0 * math.pi * (1.1 * share + _unit(seed, "sway", k))
        cx, cy = _clamped(x0 + side * 0.32 * share + 0.06 * math.sin(sway), y0 + 0.62 * share + 0.03 * math.sin(2.0 * sway))
        body = BUTTERFLY_SIZE * shown
        beat = 0.25 + 0.75 * abs(math.cos(2.0 * math.pi * (WING_BEATS * now + _unit(seed, "beat", k))))
        for wing in (-1.0, 1.0):
            outline = []
            for j in range(10):
                a = math.pi * j / 9
                reach = body * 1.1 * math.sin(a) * (1.0 + 0.35 * math.sin(2.0 * a))
                outline.append((cx + wing * (body * 0.35 + reach * beat), cy + body * 0.9 * math.cos(a) * 0.8))
            wings.append(tuple(outline))
        glyphs += _glyph(BUTTERFLY_GLYPHS[k % len(BUTTERFLY_GLYPHS)], cx - body * 0.3, cy - body * 0.3, body * 0.6)
    return tuple(glyphs[:GLYPHS]), tuple(wings[:WINGS])


def _timelines(now: float, age: float, grow: float, seed: int) -> tuple[tuple[tuple[Point, ...], ...], tuple[tuple[float, float, float, float], ...], tuple[tuple[float, float, float], ...]]:
    """A tree of timelines branching from the panel's foot, growing level by level over
    :data:`TIMELINE_GROW`, each tip holding a small panel in which two small figures come
    together and pulse as they meet, every panel at its own moment (the same meeting in every
    timeline)."""
    branches: list[tuple[Point, ...]] = []
    tips = 2 ** TIMELINE_LEVELS
    grown = min(max(age, 0.0) / TIMELINE_GROW, 1.0) * (TIMELINE_LEVELS + 1)

    def node(level: int, index: int) -> tuple[float, float]:
        span = 2 ** (TIMELINE_LEVELS - level)
        u = 0.06 + 0.88 * ((index + 0.5) * span) / tips
        return u, 0.06 + 0.56 * level / TIMELINE_LEVELS

    def segment(a: tuple[float, float], b: tuple[float, float], share: float) -> tuple[Point, ...]:
        points = []
        for j in range(6):
            s = share * j / 5
            u = a[0] + (b[0] - a[0]) * (s * s * (3.0 - 2.0 * s))
            points.append(_panel_point(u, a[1] + (b[1] - a[1]) * s, grow))
        return tuple(points)

    trunk = min(grown, 1.0)
    if trunk > 0:
        branches.append(segment((0.5, 0.0), node(0, 0), trunk))
    for level in range(1, TIMELINE_LEVELS + 1):
        share = min(max(grown - level, 0.0), 1.0)
        if share <= 0:
            break
        for index in range(2 ** level):
            branches.append(segment(node(level - 1, index // 2), node(level, index), share))
    boxes: list[tuple[float, float, float, float]] = []
    dots: list[tuple[float, float, float]] = []
    shown = min(max(grown - TIMELINE_LEVELS, 0.0), 1.0)
    if shown > 0:
        for index in range(tips):
            u, v = node(TIMELINE_LEVELS, index)
            x0, y0 = _panel_point(u - 0.05, v + 0.04, grow)
            x1, y1 = _panel_point(u + 0.05, v + 0.04 + 0.26 * shown, grow)
            boxes.append((x0, y0, x1, y1))
            phase = (now / MEETING_SECONDS + index * 0.37 + 0.2 * _unit(seed, "meet", index)) % 1.0
            close = phase / 0.55 if phase < 0.55 else 1.0
            close = close * close * (3.0 - 2.0 * close)
            pulse = 1.0 + (0.35 * math.sin(math.pi * (phase - 0.55) / 0.45) if phase >= 0.55 else 0.0)
            r = 0.016 * shown * pulse
            mid, low = (x0 + x1) / 2, y0 + (y1 - y0) * 0.45
            apart = (x1 - x0) * 0.32 * (1.0 - close) + r
            dots += [(mid - apart, low, r), (mid + apart, low, r)]
    return tuple(branches[:GLYPHS]), tuple(boxes[:BOXES]), tuple(dots[:DOTS])


__all__ = ["BOXES", "DISPLAY_PATTERNS", "DOTS", "FLOAT_BOX", "GLYPHS", "GLYPH_STROKES", "GROW_SECONDS", "LENS", "PANEL", "WINGS", "DisplayFrame",
           "display_frame"]
