"""Snow that settles on a stage (DESIGN.md §69.60). No manim.

A ``snow`` field with ``settle: true`` on a ``stage`` ends on the ground like rain (Step 105's
landing band and landing lines, :mod:`vidgen.cartoon.rain`) and on the props: a prop that catches
snow has a :class:`TopLine`, the upper edge of its drawing in columns (:func:`top_line`), and a
flake over it that would land behind its front stops there; an open umbrella stops flakes like
rain. A landed flake lies still and fades over :data:`FLAKE_REST` seconds (:func:`rest_flakes`).

Where the flakes land a white layer grows with the seconds of snowfall (:func:`settled_seconds`,
counted in :data:`SETTLE_STEP` steps, so the layer changes now and then, not on every frame, and
:func:`settle_amount`): a *blanket* over the ground area, opaque from :data:`COVER_SHARE` of the
full amount on and rising above the ground area's back edge in lumps (:func:`blanket_outline`),
thin under trees and standing open umbrellas (:func:`bare_patches`); and a *cap* on each prop's top
line where the line is flat enough to hold snow (:func:`cap_thickness`, :func:`cap_outlines`).

Everything is in Manim units of the scene (``y`` up), numpy arrays, so it is tested without
rendering; :mod:`vidgen.cartoon.weather_drawing` draws it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from vidgen.cartoon.rain import SHELTER_REACH, RainGround, ShelterBox
from vidgen.cartoon.stage import depth_scale

#: Seconds of snowfall at density 1 until the layer is full (twice the density: half the time).
SETTLE_SECONDS = 24.0
#: The layer grows in steps of this many seconds of snowfall.
SETTLE_STEP = 0.5
#: Share of the full amount at which the blanket hides the ground (it fades in until then).
COVER_SHARE = 0.4
#: The blanket's opacity once it covers the ground.
BLANKET_OPACITY = 0.97
#: How far (frame heights) the full blanket rises above the ground area's back edge, on average.
BLANKET_RISE = 0.018
#: The lumps along the blanket's back edge: their wavelengths (frame heights), weights and how much
#: they vary the rise (a share of it, either way).
LUMP_WAVELENGTHS = (0.9, 0.37, 0.16)
LUMP_WEIGHTS = (0.5, 0.3, 0.2)
LUMP_DEPTH = 0.6
#: Frame heights between the corners of the blanket's back edge.
BLANKET_STEP = 0.02
#: A bare patch under a shelter: its half width as a share of the shelter's, height over width,
#: and how thinly snow still covers it (a share of the blanket's opacity).
BARE_WIDTH = 0.8
BARE_FLAT = 0.22
THIN_SNOW = 0.45
#: A full cap's thickness on a prop at depth 0 (frame's shorter sides; smaller further back), and
#: at most this share of the prop's height.
CAP_THICKNESS = 0.03
CAP_SHARE = 0.2
#: Columns of a prop's top line.
CAP_COLUMNS = 28
#: A top line steeper than this (rise over run) holds no snow there.
CAP_SLOPE = 1.0
#: A cap reaches this share of its thickness below the top line (over the prop's outline).
CAP_SINK = 0.35
#: Seconds a landed flake lies still, fading, before it is gone.
FLAKE_REST = 0.5
#: The settled snow's colour (white with a touch of blue, so it reads on a white sky).
SNOW_COLOR = "#F4F7FC"


@dataclass(frozen=True, eq=False)
class TopLine:
    """The upper edge of a prop that catches snow: ``ys`` over the increasing ``xs`` (Manim units),
    and ``feet``, the y of the ground line where it stands. Like a
    :class:`~vidgen.cartoon.rain.ShelterBox`, but its top follows the drawing."""

    xs: np.ndarray
    ys: np.ndarray
    feet: float

    def top_at(self, x: np.ndarray) -> np.ndarray:
        """The line's height over each ``x`` (its end heights beyond its ends)."""
        return np.interp(x, self.xs, self.ys)

    def covers(self, x: np.ndarray, landing: np.ndarray, reach: float) -> np.ndarray:
        """Which flakes at ``x`` landing on the lines ``landing`` stop on it: over it, landing at
        most ``reach`` in front of its feet, and below the line."""
        return (x >= self.xs[0]) & (x <= self.xs[-1]) & (landing >= self.feet - reach) & (landing < self.top_at(x))


def settled_seconds(now: float, start: float, ended: float | None, settled: float = 0.0, step: float = SETTLE_STEP) -> float:
    """Seconds of snowfall lying at scene time ``now`` for snow that started at ``start`` with
    ``settled`` seconds already lying and stopped at ``ended`` (``None``: still snowing), counted
    in whole ``step`` s. ``now`` may be infinite (the layer it ends with)."""
    end = now if ended is None else min(now, ended)
    seconds = max(end - start, 0.0)
    if math.isinf(seconds):
        return math.inf
    return settled + math.floor(seconds / step + 1e-9) * step


def settle_amount(seconds: float, density: float = 1.0) -> float:
    """How much snow lies after ``seconds`` of snowfall at ``density``: 0 (none) .. 1 (the full
    layer, after :data:`SETTLE_SECONDS` at density 1), growing evenly."""
    if seconds <= 0.0:
        return 0.0
    return min(seconds * density / SETTLE_SECONDS, 1.0)


def blanket_cover(amount: float) -> float:
    """How much the blanket hides the ground (0..1) at ``amount``: fully from :data:`COVER_SHARE`."""
    return min(max(amount / COVER_SHARE, 0.0), 1.0)


def edge_lumps(x: np.ndarray, frame_height: float, seed: int) -> np.ndarray:
    """Factors (1 ± :data:`LUMP_DEPTH`) along the blanket's back edge at ``x``: smooth seeded lumps."""
    rng = np.random.default_rng([seed, 126])
    phases = rng.uniform(0.0, 2 * math.pi, len(LUMP_WAVELENGTHS))
    wave = sum(w * np.sin(2 * math.pi * x / (length * frame_height) + p) for w, length, p in zip(LUMP_WEIGHTS, LUMP_WAVELENGTHS, phases))
    return 1.0 + LUMP_DEPTH * np.asarray(wave)


def blanket_outline(left: float, right: float, bottom: float, back: float, rise: float, frame_height: float, seed: int) -> np.ndarray:
    """The blanket's corners counter-clockwise (``(n, 2)``): from ``bottom`` (the frame's bottom
    edge) between ``left`` and ``right`` up to the ground area's ``back`` edge raised by ``rise``
    (Manim units) times :func:`edge_lumps`."""
    count = max(2, math.ceil((right - left) / (BLANKET_STEP * frame_height)) + 1)
    xs = np.linspace(left, right, count)
    tops = back + rise * edge_lumps(xs, frame_height, seed)
    edge = np.stack([xs[::-1], tops[::-1]], axis=1)
    return np.concatenate([np.array([[left, bottom], [right, bottom]]), edge])


def bare_patches(shelters: Sequence[ShelterBox], corners: int = 24) -> list[np.ndarray]:
    """The ground under each shelter, where snow lies only thinly (:data:`THIN_SNOW`): an ellipse
    :data:`BARE_WIDTH` of its width wide on its feet line, corners clockwise (``(corners, 2)``; a
    hole in the counter-clockwise blanket)."""
    angles = np.linspace(0.0, -2 * math.pi, corners, endpoint=False)
    patches = []
    for box in shelters:
        half = BARE_WIDTH * (box.right - box.left) / 2
        centre = (box.left + box.right) / 2
        patches.append(np.stack([centre + half * np.cos(angles), box.feet + BARE_FLAT * half * np.sin(angles)], axis=1))
    return patches


def curve_segments(points: np.ndarray, per_curve: int = 6) -> np.ndarray:
    """Cubic Bézier curves given as Manim stores them (four points per curve: anchor, two handles,
    anchor) as straight segments, ``per_curve - 1`` per curve: ``(n, 2, 2)`` (start, end; x, y)."""
    count = len(points) // 4 * 4
    if count == 0:
        return np.zeros((0, 2, 2))
    curves = np.asarray(points[:count, :2], dtype=float).reshape(-1, 4, 2)
    t = np.linspace(0.0, 1.0, per_curve)[:, None]
    weights = np.concatenate([(1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t**2, t**3], axis=1)
    samples = np.einsum("pk,ckd->cpd", weights, curves)
    return np.stack([samples[:, :-1], samples[:, 1:]], axis=2).reshape(-1, 2, 2)


def top_line(segments: np.ndarray, columns: int = CAP_COLUMNS) -> tuple[np.ndarray, np.ndarray]:
    """The upper edge of the straight ``segments`` ``(n, 2, 2)``: the highest point any of them
    reaches over the middle of each of ``columns`` columns across them (or at its ends inside the
    column), with the left and right ends added, as ``(xs, ys)``."""
    x0, y0, x1, y1 = segments[:, 0, 0], segments[:, 0, 1], segments[:, 1, 0], segments[:, 1, 1]
    left, right = float(min(x0.min(), x1.min())), float(max(x0.max(), x1.max()))
    highest = float(max(y0.max(), y1.max()))
    if right - left < 1e-9:
        return np.array([left, right]), np.full(2, highest)
    edges = np.linspace(left, right, columns + 1)
    centres = (edges[:-1] + edges[1:]) / 2
    low, high = np.minimum(x0, x1)[:, None], np.maximum(x0, x1)[:, None]
    over = (low <= centres) & (centres <= high)
    run = (x1 - x0)[:, None]
    share = np.where(np.abs(run) > 1e-12, (centres - x0[:, None]) / np.where(np.abs(run) > 1e-12, run, 1.0), 1.0)
    crossing = np.where(np.abs(run) > 1e-12, y0[:, None] + share * (y1 - y0)[:, None], np.maximum(y0, y1)[:, None])
    tops = np.where(over, crossing, -np.inf).max(axis=0)
    ends = np.concatenate([segments[:, 0], segments[:, 1]])
    index = np.clip(np.searchsorted(edges, ends[:, 0], side="right") - 1, 0, columns - 1)
    np.maximum.at(tops, index, ends[:, 1])
    found = np.isfinite(tops)
    tops = np.interp(centres, centres[found], tops[found])   # a gap between parts: between its neighbours
    return np.concatenate([[left], centres, [right]]), np.concatenate([[tops[0]], tops, [tops[-1]]])


def cap_full_thickness(short_side: float, depth: float, height: float) -> float:
    """How thick the full cap of a prop ``height`` tall (Manim units) at ``depth`` is, in a frame
    whose shorter side is ``short_side``: :data:`CAP_THICKNESS` times the depth scale, at most
    :data:`CAP_SHARE` of its height."""
    return min(CAP_THICKNESS * short_side * depth_scale(min(max(depth, 0.0), 1.0)), CAP_SHARE * height)


def cap_thickness(xs: np.ndarray, ys: np.ndarray, full: float, amount: float) -> np.ndarray:
    """A cap's thickness over each point of a top line: ``full`` × ``amount`` where the line is at
    most :data:`CAP_SLOPE` steep, less next to a steeper part (the cap's ends taper), 0 on it."""
    if len(xs) < 2:
        return np.zeros(len(xs))
    slope = np.gradient(ys, xs)
    flat = (np.abs(slope) <= CAP_SLOPE).astype(float)
    padded = np.concatenate([[0.0], flat, [0.0]])
    taper = 0.25 * padded[:-2] + 0.5 * padded[1:-1] + 0.25 * padded[2:]
    return full * amount * taper * flat


def cap_outlines(xs: np.ndarray, ys: np.ndarray, thickness: np.ndarray, sink: float = CAP_SINK) -> list[np.ndarray]:
    """The caps on a top line, one per run of points with snow, corners counter-clockwise: along
    the line ``sink`` × the thickness below it, back along it the thickness above, coming to a
    point at both ends."""
    outlines = []
    on = thickness > 0
    k = 0
    while k < len(xs):
        if not on[k]:
            k += 1
            continue
        end = k
        while end + 1 < len(xs) and on[end + 1]:
            end += 1
        low, high = max(k - 1, 0), min(end + 1, len(xs) - 1)
        x, y, t = xs[low:high + 1], ys[low:high + 1], thickness[low:high + 1].copy()
        t[0] = t[-1] = 0.0
        lower = np.stack([x, y - sink * t], axis=1)
        upper = np.stack([x[::-1], (y + t)[::-1]], axis=1)
        outlines.append(np.concatenate([lower, upper[1:-1]]))
        k = end + 1
    return outlines


def flake_floors(x: np.ndarray, landing: np.ndarray, ground: RainGround) -> np.ndarray:
    """Where each flake at ``x`` ends: its landing line, or the highest top over it of a shelter or
    a prop's :class:`TopLine` that it would land behind (:data:`~vidgen.cartoon.rain.SHELTER_REACH`)."""
    floor = landing.copy()
    reach = SHELTER_REACH * ground.frame_height
    for shelter in ground.shelters:
        under = shelter.covers(x, landing, reach)
        top = shelter.top_at(x) if isinstance(shelter, TopLine) else np.full(len(x), shelter.top)
        floor = np.where(under, np.maximum(floor, top), floor)
    return floor


def rest_flakes(bottom: np.ndarray, floor: np.ndarray, speed: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Flakes against their floors: how much of each is seen (1 while it falls, fading to 0 over
    :data:`FLAKE_REST` seconds after it landed, then 0 until it starts again at the top) and how
    far to raise it (Manim units: a landed flake lies on its floor). ``bottom``: each flake's
    lowest point, ``speed`` its fall speed (Manim units per second)."""
    below = np.maximum(floor - bottom, 0.0)
    falling = bottom > floor
    age = below / np.maximum(speed, 1e-9)
    resting = ~falling & (age < FLAKE_REST)
    shown = np.where(falling, 1.0, np.where(resting, 1.0 - age / FLAKE_REST, 0.0))
    return shown, np.where(resting, below, 0.0)


__all__ = [
    "BLANKET_RISE",
    "CAP_THICKNESS",
    "COVER_SHARE",
    "FLAKE_REST",
    "SETTLE_SECONDS",
    "SETTLE_STEP",
    "SNOW_COLOR",
    "THIN_SNOW",
    "TopLine",
    "bare_patches",
    "blanket_cover",
    "blanket_outline",
    "cap_full_thickness",
    "cap_outlines",
    "cap_thickness",
    "curve_segments",
    "edge_lumps",
    "flake_floors",
    "rest_flakes",
    "settle_amount",
    "settled_seconds",
    "top_line",
]
