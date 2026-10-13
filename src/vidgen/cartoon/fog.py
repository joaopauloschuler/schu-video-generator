"""Fog on a stage (DESIGN.md §69.60). No manim.

Fog is a few translucent *bands*, one at each depth of :data:`FOG_DEPTHS` (back to front): a band
lies on the ground line of its depth, and the stage draws it right in front of everything standing
further back. So a thing is seen through every band in front of it, and the further back it stands
the more fog covers it (:func:`fog_cover`); the sky and the background are behind every band. Each
band is :data:`FOG_LAYERS` layers sharing its opacity (:data:`FOG_LAYER_SHARES`): a haze up to the
top of the frame and two banks with wavy tops (:data:`FOG_LAYER_REACH`), the taller layers reaching
lower too, so fog lies thickest near the ground and its edges are soft. The waves drift sideways
(nearer bands faster) and with the stage's wind.

Manim units of the scene (``y`` up); :mod:`vidgen.cartoon.weather_drawing` draws it.
"""

from __future__ import annotations

import math

import numpy as np

from vidgen.cartoon.stage import FAR_RISE, depth_scale

#: The depths of the bands, back to front (the first, at the back of the stage, is also a haze
#: over the sky). A thing at a depth is behind every band less deep.
FOG_DEPTHS = (1.0, 0.8, 0.6, 0.4, 0.2)
#: ``fog: true``'s density.
FOG_DENSITY = 0.5
#: How fast fog thickens with depth: at density ``d`` a thing at the back is seen through
#: ``1 - exp(-FOG_THICKNESS × d)`` of fog.
FOG_THICKNESS = 1.8
#: How high a band's banks reach above its ground line (frame heights; times the depth scale), and
#: the back band's (low over the sky).
FOG_HEIGHT = 0.3
FOG_HAZE_HEIGHT = 0.4
#: Layers per band: the share of its fog each holds (the haze first), how high each reaches (a
#: share of the band's height; ``None``: the top of the frame), and how much lower (frame heights)
#: each taller layer reaches.
FOG_LAYERS = 3
FOG_LAYER_SHARES = (0.5, 0.25, 0.25)
FOG_LAYER_REACH: tuple[float | None, ...] = (None, 1.0, 0.5)
FOG_FEATHER = 0.015
#: How much the waves raise or lower a band's top (a share of its height), their wavelengths
#: (frame heights) and weights.
FOG_WAVE = 0.3
FOG_WAVELENGTHS = (1.3, 0.55)
FOG_WAVE_WEIGHTS = (0.65, 0.35)
#: How fast the back band's waves drift (frame heights per second at ``drift: 1``; the front band
#: twice as fast), and how far the wind pushes them (frame heights per force × second).
FOG_DRIFT = 0.02
FOG_WIND_DRIFT = 0.12
#: Frame heights between the corners of a band's top.
FOG_STEP = 0.025
#: The fog's colour (a pale grey blue).
FOG_COLOR = "#DCE2EA"


def band_opacities(density: float) -> tuple[float, ...]:
    """Each band's opacity at ``density`` (0..1), back to front: together the bands in front of a
    depth hide ``1 - exp(-FOG_THICKNESS × density × depth)`` of it (at the band depths)."""
    nearer = (*FOG_DEPTHS[1:], 0.0)
    return tuple(1.0 - math.exp(-FOG_THICKNESS * density * (d - n)) for d, n in zip(FOG_DEPTHS, nearer))


def fog_cover(depth: float, density: float, *, high: bool = False) -> float:
    """How much fog covers a thing at ``depth`` (``math.inf``: the sky) near the ground, where every
    layer of the bands lies (``high``: above the banks, in the haze alone): 1 minus what shows
    through every band less deep than it (0 at the front, more further back)."""
    seen = 1.0
    for band_depth, opacity in zip(FOG_DEPTHS, band_opacities(density)):
        if band_depth < depth:
            seen *= 1.0 - (layer_opacity(opacity, FOG_LAYER_SHARES[0]) if high else opacity)
    return 1.0 - seen


def layer_opacity(opacity: float, share: float) -> float:
    """The opacity of a band's layer holding ``share`` of its fog: where all its layers overlap,
    the band's ``opacity``."""
    return 1.0 - (1.0 - opacity) ** share


def fog_shift(t: float, blown: float, depth: float, drift: float = 1.0) -> float:
    """How far (frame heights) the waves of the band at ``depth`` have drifted ``t`` seconds into
    the scene, with ``blown`` the stage's wind force added up since then (signed)."""
    return drift * FOG_DRIFT * (2.0 - depth) * t + FOG_WIND_DRIFT * blown


def band_height(index: int, depth: float) -> float:
    """How high (frame heights) band ``index`` (of :data:`FOG_DEPTHS`) at ``depth`` reaches."""
    return FOG_HAZE_HEIGHT if index == 0 else FOG_HEIGHT * depth_scale(depth)


def _waves(x: np.ndarray, shift: float, index: int, seed: int) -> np.ndarray:
    """The waves of band ``index`` at ``x`` (frame heights), drifted by ``shift``: -1..1."""
    rng = np.random.default_rng([seed, 1126, index])
    phases = rng.uniform(0.0, 2 * math.pi, len(FOG_WAVELENGTHS))
    return np.asarray(sum(w * np.sin(2 * math.pi * (x - shift) / length + p) for w, length, p in zip(FOG_WAVE_WEIGHTS, FOG_WAVELENGTHS, phases)))


def band_outlines(
    index: int, ground: float, left: float, right: float, frame_height: float, shift: float, seed: int,
) -> list[np.ndarray]:
    """The layers of band ``index`` on a stage whose ground line is ``ground`` (a fraction of the
    frame height above its bottom edge) from ``left`` to ``right`` (Manim units), its waves drifted
    by ``shift`` frame heights: :data:`FOG_LAYERS` outlines, corners counter-clockwise, in the
    order of :data:`FOG_LAYER_REACH` (the haze up to the frame's top edge first; each taller layer
    reaches lower too)."""
    depth = FOG_DEPTHS[index]
    base = (ground + FAR_RISE * depth - 0.5) * frame_height
    height = band_height(index, depth) * frame_height
    count = max(2, math.ceil((right - left) / (FOG_STEP * frame_height)) + 1)
    xs = np.linspace(left, right, count)
    wave = 1.0 + FOG_WAVE * _waves(xs / frame_height, shift, index, seed)
    outlines = []
    for layer, reach in enumerate(FOG_LAYER_REACH):
        bottom = base - (FOG_LAYERS - 1 - layer) * FOG_FEATHER * frame_height
        if reach is None:
            top = frame_height / 2
            outlines.append(np.array([[left, bottom], [right, bottom], [right, top], [left, top]]))
            continue
        tops = base + height * reach * wave
        edge = np.stack([xs[::-1], tops[::-1]], axis=1)
        outlines.append(np.concatenate([np.array([[left, bottom], [right, bottom]]), edge]))
    return outlines


def band_box(index: int, ground: float, left: float, right: float, frame_height: float) -> tuple[float, float, float, float]:
    """The box (left, bottom, right, top) band ``index`` stays in whatever its waves' drift."""
    depth = FOG_DEPTHS[index]
    base = (ground + FAR_RISE * depth - 0.5) * frame_height
    low = base - (FOG_LAYERS - 1) * FOG_FEATHER * frame_height
    return (left, low, right, frame_height / 2)


__all__ = [
    "FOG_COLOR",
    "FOG_DENSITY",
    "FOG_DEPTHS",
    "FOG_LAYERS",
    "band_box",
    "band_opacities",
    "band_outlines",
    "fog_cover",
    "fog_shift",
    "layer_opacity",
]
