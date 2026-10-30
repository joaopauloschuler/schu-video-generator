"""A cartoon kiss (DESIGN.md §102.15): the maths, no manim; :class:`~vidgen.cartoon.figure_fx.KissMotion`
and :class:`~vidgen.cartoon.figure_fx.KissBurst` draw it.

Two characters turn to each other, lean in (their bodies tilt forward, the taller one more when
their heads are at different heights) and step in across the picture until their faces touch,
close their eyes and hold; a small burst of hearts and sparkles rises from where their faces
meet; then they lean back to where they stood. Times are seconds since the kiss began.
"""

from __future__ import annotations

import math

#: Seconds the lean in and the lean back take; the action's default length.
KISS_IN = 0.7
KISS_OUT = 0.6
KISS_SECONDS = 3.0
#: How far each leans forward (degrees) and how much more the taller one leans per head height
#: their heads differ (at most :data:`KISS_EXTRA_LEAN`).
KISS_LEAN = 11.0
KISS_TALLER_LEAN = 6.0
KISS_EXTRA_LEAN = 8.0
#: How far their heads overlap when the faces touch (a share of the smaller head's width).
KISS_TOUCH = 0.03
#: The eyes close once the lean is this far in.
EYES_CLOSE = 0.6
#: The burst: seconds it lasts, how many hearts and sparkles, how high it rises (head heights).
BURST_SECONDS = 2.0
BURST_HEARTS = 5
BURST_SPARKLES = 6
BURST_RISE = 1.1


def _ease(share: float) -> float:
    share = min(max(share, 0.0), 1.0)
    return share * share * (3.0 - 2.0 * share)


def kiss_share(t: float, seconds: float = KISS_SECONDS) -> float:
    """How far in the lean is ``t`` seconds into a kiss of ``seconds`` (0 .. 1): easing in over
    :data:`KISS_IN`, held, easing back over :data:`KISS_OUT` at its end (both shortened to fit a
    short kiss)."""
    lean_in = min(KISS_IN, seconds * 0.4)
    lean_out = min(KISS_OUT, seconds * 0.35)
    if t <= 0.0 or t >= seconds:
        return 0.0
    if t < lean_in:
        return _ease(t / lean_in)
    if t > seconds - lean_out:
        return _ease((seconds - t) / lean_out)
    return 1.0


def contact_time(seconds: float = KISS_SECONDS) -> float:
    """When the faces touch, seconds into a kiss of ``seconds`` (the burst starts then)."""
    return min(KISS_IN, seconds * 0.4)


def lean_angles(head_a: float, head_b: float, head_height: float) -> tuple[float, float]:
    """How far (degrees, forward) each of two characters leans, given the heights (y) of their
    heads' middles and a head's height: the same lean, the taller one more by how much higher
    its head is."""
    extra = min(max(abs(head_a - head_b) / max(head_height, 1e-9), 0.0) * KISS_TALLER_LEAN, KISS_EXTRA_LEAN)
    return (KISS_LEAN + (extra if head_a > head_b else 0.0), KISS_LEAN + (extra if head_b > head_a else 0.0))


def step_in(gap: float, head_width: float) -> float:
    """How far (screen units) each of two characters steps in across the picture so their heads,
    ``gap`` apart at full lean (negative: overlapping), overlap by :data:`KISS_TOUCH` of
    ``head_width``: half of what closes it (0 when they already touch)."""
    return max(gap + KISS_TOUCH * head_width, 0.0) / 2.0


def burst(age: float, seed: int = 0) -> list[tuple[str, float, float, float, float]]:
    """The burst ``age`` seconds after the faces touch: ``(kind, dx, dy, size, opacity)`` per
    heart (``heart``) and sparkle (``sparkle``), in head heights from where the faces meet. The
    hearts pop up (overshooting their size), fan out as they rise and fade over the last half;
    the sparkles twinkle round them. Nothing before 0 or after :data:`BURST_SECONDS`."""
    if age < 0.0 or age > BURST_SECONDS:
        return []
    u = age / BURST_SECONDS
    out: list[tuple[str, float, float, float, float]] = []
    fade = 1.0 if u < 0.5 else max(1.0 - (u - 0.5) / 0.5, 0.0)
    for k in range(BURST_HEARTS):
        start = 0.12 * k
        own = min(max((age - start) / (BURST_SECONDS - start), 0.0), 1.0)
        if own <= 0.0:
            continue
        spread = (k - (BURST_HEARTS - 1) / 2) / max(BURST_HEARTS - 1, 1)
        pop = min(own / 0.15, 1.0)
        size = (0.22 + 0.06 * ((k + seed) % 3)) * (pop * (1.0 + 0.25 * math.sin(math.pi * pop)))
        dx = spread * 0.9 * own ** 0.7 + 0.05 * math.sin(6.0 * own + k)
        dy = 0.25 + BURST_RISE * own ** 0.8
        out.append(("heart", dx, dy, size, fade))
    for k in range(BURST_SPARKLES):
        a = 2.0 * math.pi * (k / BURST_SPARKLES) + 0.6 * seed
        r = 0.35 + 0.45 * u
        twinkle = abs(math.sin(math.pi * (3.0 * u + k * 0.37)))
        out.append(("sparkle", r * math.cos(a), 0.3 + r * math.sin(a) * 0.8 + 0.4 * u, 0.12 * twinkle, fade * twinkle))
    return out


__all__ = [
    "BURST_SECONDS",
    "EYES_CLOSE",
    "KISS_IN",
    "KISS_LEAN",
    "KISS_OUT",
    "KISS_SECONDS",
    "KISS_TOUCH",
    "burst",
    "contact_time",
    "kiss_share",
    "lean_angles",
    "step_in",
]
