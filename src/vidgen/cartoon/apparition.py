"""How characters appear, flicker and shimmer (DESIGN.md §100.9): the maths, no manim.

- A hologram *materialises* (the ``materialise`` action) in :data:`MATERIALISE_SECONDS`: its
  outlines first, a flickering wireframe (:data:`WIREFRAME_SHARE` of the time), then its fills
  come in, still flickering, until it stands solid (:func:`materialise_levels`);
  ``dematerialise`` is the same backwards.
- A hologram *flickers* now and then (:func:`flicker_level`): short dips of its opacity, seeded,
  a few seconds apart, over a faint steady shimmer.
- An *iridescent* skin shifts its colours like oil on water (:func:`iridescent_rgb`): bands of
  hue running up the figure and drifting slowly with time.
"""

from __future__ import annotations

import colorsys
import math

from vidgen.cartoon.living import _noise, _unit

#: Seconds a materialise (or dematerialise) takes by default, and the share of it spent as a
#: wireframe (outlines only) before the fills come in.
MATERIALISE_SECONDS = 2.2
WIREFRAME_SHARE = 0.4
#: How deep the flicker cuts while a hologram materialises (a share of its opacity).
MATERIALISE_FLICKER = 0.45
#: A hologram's flicker: seconds between dips (from .. to, seeded), how long a dip lasts, how
#: deep it goes (a share of the opacity left at its bottom, seeded between these), and the
#: steady shimmer (a share either way).
FLICKER_GAP = (2.2, 5.0)
FLICKER_DIP = 0.16
FLICKER_DEPTH = (0.25, 0.65)
FLICKER_SHIMMER = 0.05


def _smooth(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def flicker_level(now: float, seed: int = 0) -> float:
    """A hologram's opacity factor at scene time ``now`` (about 1; a dip now and then): the
    dips start every :data:`FLICKER_GAP` seconds (seeded), each :data:`FLICKER_DIP` long, a
    jagged double drop to its depth; between them a faint shimmer."""
    shimmer = 1.0 - FLICKER_SHIMMER * (0.5 + 0.5 * _noise(now, seed, "holo_shimmer"))
    low, high = FLICKER_GAP
    mean = (low + high) / 2
    k = max(math.floor(now / mean) - 1, 0)
    for index in (k, k + 1, k + 2):
        start = index * mean + (_unit(seed, "holo_dip", index) - 0.5) * (high - low)
        into = (now - start) / FLICKER_DIP
        if 0.0 <= into < 1.0:
            depth = FLICKER_DEPTH[0] + (FLICKER_DEPTH[1] - FLICKER_DEPTH[0]) * _unit(seed, "holo_depth", index)
            jag = 0.5 + 0.5 * math.cos(2.0 * math.pi * 2.0 * into)   # two drops in one dip
            return shimmer * (depth + (1.0 - depth) * jag)
    return shimmer


def materialise_levels(share: float, now: float, seed: int = 0) -> tuple[float, float]:
    """``(outline, fill)`` opacity factors ``share`` (0..1) of the way through a materialise at
    scene time ``now``: the outlines rise over the first :data:`WIREFRAME_SHARE`, the fills over
    the rest, both flickering (:data:`MATERIALISE_FLICKER`) until it is whole (1, 1 at the end)."""
    s = min(max(share, 0.0), 1.0)
    if s >= 1.0:
        return 1.0, 1.0
    flicker = 1.0 - MATERIALISE_FLICKER * (1.0 - s) * (0.5 + 0.5 * _noise(now * 3.0, seed, "materialise"))
    outline = _smooth(s / WIREFRAME_SHARE) * flicker
    fill = _smooth((s - WIREFRAME_SHARE) / (1.0 - WIREFRAME_SHARE)) * flicker
    return outline, fill


#: An iridescent skin: seconds for the colours to go once round the hue circle, how many bands of
#: hue run up the figure, and the lightness range it shimmers in (darker parts - outlines, eyes -
#: and white parts keep their colours).
IRIDESCENT_SECONDS = 12.0
IRIDESCENT_BANDS = 1.3
IRIDESCENT_DARK = 0.18
IRIDESCENT_LIGHT = 0.93
#: The least saturation an iridescent colour shows (a pale skin still shows its sheen).
IRIDESCENT_SATURATION = 0.5


def iridescent_rgb(rgb: tuple[float, float, float], height: float, now: float, *, strength: float = 1.0,
                   seconds: float = IRIDESCENT_SECONDS) -> tuple[float, float, float]:
    """``rgb`` (0..1) on an iridescent skin at ``height`` (0 the feet .. 1 the head's top) at
    scene time ``now``: its hue turned by bands running up the figure and drifting round the hue
    circle once in ``seconds``, at least :data:`IRIDESCENT_SATURATION` saturated, mixed in by
    ``strength``; very dark and very light colours are kept."""
    h, light, sat = colorsys.rgb_to_hls(*rgb)
    if light < IRIDESCENT_DARK or light > IRIDESCENT_LIGHT or strength <= 0:
        return rgb
    turn = now / max(seconds, 1e-6) + IRIDESCENT_BANDS * height + 0.08 * math.sin(2.0 * math.pi * (now / seconds * 2.0 + height * 3.0))
    shifted = colorsys.hls_to_rgb((h + turn) % 1.0, light, max(sat, IRIDESCENT_SATURATION))
    k = min(max(strength, 0.0), 1.0)
    return tuple(a * (1.0 - k) + b * k for a, b in zip(rgb, shifted))  # type: ignore[return-value]


__all__ = [
    "FLICKER_DIP",
    "FLICKER_GAP",
    "IRIDESCENT_SECONDS",
    "MATERIALISE_SECONDS",
    "WIREFRAME_SHARE",
    "flicker_level",
    "iridescent_rgb",
    "materialise_levels",
]
