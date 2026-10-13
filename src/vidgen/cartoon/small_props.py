"""Everyday small props (DESIGN.md §69.56): the maths, without manim.

Balloons that a character lets go of (the ``let_go`` action) float up and out of the frame,
drifting with the stage's wind and swaying (:func:`float_point`); a watering can tilts and pours
water drops (the ``pour`` action: :func:`pour_tilt`, :func:`pour_drops`). A ringing phone's
shake is in :mod:`vidgen.cartoon.living` (it rings like a lamp shines: switched on and off).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

#: The props that float up when let go (``let_go``), and the props that pour (``pour``).
FLOATING_PROPS: frozenset[str] = frozenset({"balloons"})
POURING_PROPS: frozenset[str] = frozenset({"watering_can"})
#: Balloons rise this many Manim units a second once going (they speed up over
#: :data:`FLOAT_SPEED_UP` of the way), drift sideways ``FLOAT_DRIFT`` units per unit risen at felt
#: wind force 1 and sway ``FLOAT_SWAY`` units either way, ``FLOAT_SWAYS`` times on the way, leaning
#: up to ``FLOAT_LEAN`` degrees with it.
FLOAT_SPEED = 1.6
FLOAT_SPEED_UP = 0.25
FLOAT_DRIFT = 0.6
FLOAT_SWAY = 0.12
FLOAT_SWAYS = 2.0
FLOAT_LEAN = 8.0
#: The shortest and longest a float up takes (s).
FLOAT_MIN_SECONDS = 1.0
FLOAT_MAX_SECONDS = 6.0
#: A pour: the can tilts ``POUR_TILT`` degrees (the spout down) over the first ``POUR_RAMP`` of
#: the action, holds, and comes back over the last ``POUR_RAMP``; water runs while the tilt is
#: past ``POUR_FLOWS`` of it. ``POUR_SECONDS``: the action's default length.
POUR_SECONDS = 2.0
POUR_TILT = 40.0
POUR_RAMP = 0.2
POUR_FLOWS = 0.7
#: The water drops: ``DROP_RATE`` a second leave the spout, ``DROP_AHEAD`` holder heights a
#: second forward, falling at ``DROP_GRAVITY`` holder heights / s², ``DROP_RADIUS`` holder heights
#: round (each ± a seeded 30 %).
DROP_RATE = 22.0
DROP_AHEAD = 0.35
DROP_GRAVITY = 4.0
DROP_RADIUS = 0.012


def _unit(seed: int, *keys: object) -> float:
    """A number in [0, 1) fixed by ``seed`` and ``keys``."""
    return random.Random(":".join(str(k) for k in (seed, *keys))).random()


# ----- balloons floating away -----------------------------------------------------------------------


def float_end(start: tuple[float, float], top: float, force: float) -> tuple[float, float]:
    """Where balloons let go at ``start`` (their grip: the strings' end, screen) end: at ``top``
    (above the frame) and as far downwind as the signed felt wind ``force`` drifts them on the
    way (:data:`FLOAT_DRIFT` per unit risen)."""
    rise = max(top - float(start[1]), 0.0)
    return float(start[0]) + FLOAT_DRIFT * force * rise, float(top)


def float_seconds(rise: float) -> float:
    """How long balloons take to float up ``rise`` Manim units (speeding up first)."""
    seconds = abs(rise) / FLOAT_SPEED * (1.0 + FLOAT_SPEED_UP)
    return min(max(seconds, FLOAT_MIN_SECONDS), FLOAT_MAX_SECONDS)


def float_progress(share: float) -> float:
    """How far up (0..1) balloons are at ``share`` (0..1) of their float: speeding up from rest
    over :data:`FLOAT_SPEED_UP` of the time (a parabola), then rising evenly; 1 at 1."""
    s = min(max(float(share), 0.0), 1.0)
    a = FLOAT_SPEED_UP
    total = 1.0 - a / 2.0
    if s < a:
        return s * s / (2.0 * a) / total
    return (s - a / 2.0) / total


def float_point(share: float, start: tuple[float, float] | object, end: tuple[float, float] | object, *, seed: int = 1) -> tuple[float, float, float]:
    """Balloons' grip (x, y) and their lean (degrees, counterclockwise) at ``share`` (0..1) of
    their float from ``start`` to ``end`` (screen): up by :func:`float_progress`, across by the
    same share, swaying :data:`FLOAT_SWAY` either way (seeded phase, none at the ends) and leaning
    with the sway. Pure: the same arguments give the same point."""
    x0, y0 = float(start[0]), float(start[1])  # type: ignore[index]
    x1, y1 = float(end[0]), float(end[1])  # type: ignore[index]
    g = float_progress(share)
    phase = 2.0 * math.pi * _unit(seed, "sway")
    sway = FLOAT_SWAY * math.sin(2.0 * math.pi * FLOAT_SWAYS * g + phase) * math.sin(math.pi * g) ** 0.5
    lean = -FLOAT_LEAN * math.cos(2.0 * math.pi * FLOAT_SWAYS * g + phase) * math.sin(math.pi * g)
    return x0 + (x1 - x0) * g + sway, y0 + (y1 - y0) * g, lean


# ----- a watering can pouring -------------------------------------------------------------------


def pour_tilt(share: float) -> float:
    """How far a pouring can is tilted at ``share`` (0..1) of the ``pour`` action, a share of
    :data:`POUR_TILT`: easing in over :data:`POUR_RAMP`, held, easing back over the last."""
    s = min(max(float(share), 0.0), 1.0)
    edge = min(s, 1.0 - s) / POUR_RAMP
    if edge >= 1.0:
        return 1.0
    return 0.5 - 0.5 * math.cos(math.pi * edge)


def pour_flow(seconds: float) -> tuple[float, float]:
    """When the water runs during a ``pour`` of ``seconds``: (start, end) seconds after it
    begins, while :func:`pour_tilt` is past :data:`POUR_FLOWS`."""
    share = POUR_RAMP * math.acos(1.0 - 2.0 * POUR_FLOWS) / math.pi
    return share * seconds, (1.0 - share) * seconds


@dataclass(frozen=True)
class Drop:
    """A water drop: its middle (``x``, ``y``) and ``radius`` (Manim units)."""

    x: float
    y: float
    radius: float


def pour_drops(
    elapsed: float, flow: tuple[float, float], spout: tuple[float, float], ground: float, height: float, direction: float, seed: int = 1,
) -> list[Drop]:
    """The drops in the air ``elapsed`` seconds into a pour whose water runs over ``flow`` (start,
    end s): :data:`DROP_RATE` a second leave the ``spout`` (screen), thrown forward
    (``direction`` +1 right, −1 left) and falling until they reach the ``ground`` y; ``height``:
    the holder's height (the drops' sizes and speeds scale with it). Seeded: the same arguments
    give the same drops."""
    start, end = flow
    drops: list[Drop] = []
    first = max(0, math.floor((elapsed - 2.0 - start) * DROP_RATE))
    k = first
    while True:
        born = start + k / DROP_RATE + 0.4 / DROP_RATE * (_unit(seed, "born", k) - 0.5)
        if born > min(elapsed, end):
            break
        age = elapsed - born
        if age >= 0.0:
            ahead = DROP_AHEAD * height * (0.7 + 0.6 * _unit(seed, "ahead", k))
            x = float(spout[0]) + direction * ahead * age
            y = float(spout[1]) - 0.5 * DROP_GRAVITY * height * age * age
            if y > ground:
                drops.append(Drop(x, y, DROP_RADIUS * height * (0.7 + 0.6 * _unit(seed, "size", k))))
        k += 1
    return drops


__all__ = [
    "DROP_AHEAD",
    "DROP_GRAVITY",
    "DROP_RADIUS",
    "DROP_RATE",
    "FLOATING_PROPS",
    "FLOAT_DRIFT",
    "FLOAT_SPEED",
    "POURING_PROPS",
    "POUR_SECONDS",
    "POUR_TILT",
    "Drop",
    "float_end",
    "float_point",
    "float_progress",
    "float_seconds",
    "pour_drops",
    "pour_flow",
    "pour_tilt",
]
