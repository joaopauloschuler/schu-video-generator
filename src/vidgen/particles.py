"""Particles: rain, snow, sparkles, dust, confetti, smoke and bubbles (DESIGN.md §69.9).

The motion is a pure function of a seed and the time, without manim, so it is tested without
rendering: :func:`particle_seeds` draws each particle's start (position, size, speed, phase,
colour) from the seed once, and :func:`particle_states` gives where every particle is, how big,
turned and opaque at a time ``t``. Positions are fractions of the particles' *area* (0..1, ``y``
from the top down, like a callout's area); sizes and speeds are in the frame's shorter side, so
16:9 and 9:16 look alike. :func:`particle_count` sets how many there are, capped at
:data:`MAX_PARTICLES` for render speed and fewer at preview quality.
:mod:`vidgen.particle_field` draws them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

#: The kinds of particles, in a fixed order (part of each kind's random stream).
PARTICLE_KINDS = ("rain", "snow", "sparkles", "dust", "confetti", "smoke", "bubbles")
#: At most this many particles in one field, whatever the density and area.
MAX_PARTICLES = 300
#: Share of the particles drawn at preview quality.
PREVIEW_SHARE = 0.5
#: Particles fade out within this share of the area next to its edges (no popping in or out).
EDGE_FADE = 0.06

Shape = Literal["streak", "dot", "star", "chip", "ring"]


@dataclass(frozen=True)
class ParticleKind:
    """How one kind of particle looks and moves. Sizes and speeds are fractions of the frame's
    shorter side (per second)."""

    shape: Shape
    #: Particles in a whole frame at density 1.
    count: int
    #: Smallest and largest size: a dot's radius, a streak's or chip's half length.
    size: tuple[float, float]
    #: Speed downwards (negative: rising).
    fall: float
    #: Each particle's speed factor is drawn from this range (dust: -1..1, any direction).
    speed: tuple[float, float]
    #: Sideways speed: the same for every particle (rain's slant), or with ``drift_spread`` a
    #: random one between ``-drift`` and ``drift``.
    drift: float
    drift_spread: bool
    #: Side-to-side swing: amplitude and the range of its frequency (Hz).
    sway: float
    sway_hz: tuple[float, float]
    #: Largest spin in turns per second (confetti); 0: no spin.
    spin: float
    #: Seconds of one twinkle (sparkles); 0: none.
    twinkle: float
    #: Size at the top of its rise, as a factor of its starting size (smoke); 1: no growth.
    grow: float
    opacity: float
    #: Default colours: theme tokens, or hex where no token fits every theme (white snow).
    colors: tuple[str, ...]


KINDS: dict[str, ParticleKind] = {
    "rain": ParticleKind("streak", 160, (0.018, 0.03), 1.6, (0.85, 1.15), 0.18, False, 0.0, (0.0, 0.0), 0.0, 0.0, 1.0, 0.55, ("#A9C1DD",)),
    "snow": ParticleKind("dot", 120, (0.004, 0.011), 0.12, (0.7, 1.3), 0.0, False, 0.03, (0.2, 0.5), 0.0, 0.0, 1.0, 0.9, ("#FFFFFF",)),
    "sparkles": ParticleKind("star", 40, (0.008, 0.02), -0.02, (0.5, 1.5), 0.0, False, 0.004, (0.1, 0.3), 0.0, 1.8, 1.0, 1.0, ("highlight",)),
    "dust": ParticleKind("dot", 60, (0.0015, 0.004), 0.015, (-1.0, 1.0), 0.02, True, 0.01, (0.05, 0.2), 0.0, 0.0, 1.0, 0.4, ("#E6DCC8",)),
    "confetti": ParticleKind(
        "chip", 90, (0.007, 0.013), 0.22, (0.7, 1.3), 0.0, False, 0.05, (0.3, 0.8), 1.5, 0.0, 1.0, 1.0,
        ("accent", "highlight", "primary", "secondary", "tertiary"),
    ),
    "smoke": ParticleKind("dot", 24, (0.03, 0.055), -0.1, (0.7, 1.3), 0.0, False, 0.02, (0.1, 0.3), 0.0, 0.0, 2.2, 0.32, ("#B9BEC6",)),
    "bubbles": ParticleKind("ring", 30, (0.01, 0.025), -0.15, (0.7, 1.3), 0.0, False, 0.025, (0.5, 1.0), 0.0, 0.0, 1.0, 0.85, ("#CFE9FF",)),
}


@dataclass(frozen=True)
class ParticleSeeds:
    """Each particle's start, drawn once from the seed (arrays of one value per particle)."""

    kind: str
    x: np.ndarray
    y: np.ndarray
    size: np.ndarray
    speed: np.ndarray
    drift: np.ndarray
    phase: np.ndarray
    sway_hz: np.ndarray
    spin: np.ndarray
    color: np.ndarray

    def __len__(self) -> int:
        return len(self.x)


@dataclass(frozen=True)
class ParticleStates:
    """Every particle at one time: ``x``, ``y`` (fractions of the area, ``y`` from the top),
    ``size`` (shorter sides), ``angle`` (radians, counter-clockwise), ``flip`` (a width factor
    -1..1: confetti tumbling) and ``opacity`` (0..1)."""

    x: np.ndarray
    y: np.ndarray
    size: np.ndarray
    angle: np.ndarray
    flip: np.ndarray
    opacity: np.ndarray


def particle_kind(kind: str) -> ParticleKind:
    """The table entry of ``kind``; ``ValueError`` naming the kinds otherwise."""
    try:
        return KINDS[kind]
    except KeyError:
        raise ValueError(f"unknown particles {kind!r}; kinds: {', '.join(PARTICLE_KINDS)}") from None


def particle_count(kind: str, density: float = 1.0, area_share: float = 1.0, *, preview: bool = False) -> int:
    """How many particles of ``kind`` a field has: the kind's count for a whole frame times
    ``density`` and the share of the frame its area covers, at most :data:`MAX_PARTICLES`;
    at preview quality :data:`PREVIEW_SHARE` of that. At least 1."""
    wanted = round(particle_kind(kind).count * density * area_share)
    count = min(wanted, MAX_PARTICLES)
    if preview:
        count = math.ceil(count * PREVIEW_SHARE)
    return max(count, 1)


def particle_seeds(kind: str, count: int, seed: int = 1, colors: int = 1) -> ParticleSeeds:
    """``count`` particles of ``kind`` drawn from ``seed`` (the same arguments give the same
    particles); ``colors``: how many colours they pick from."""
    spec = particle_kind(kind)
    rng = np.random.default_rng([seed, PARTICLE_KINDS.index(kind)])
    n = count
    drift = rng.uniform(-spec.drift, spec.drift, n) if spec.drift_spread else np.full(n, spec.drift)
    return ParticleSeeds(
        kind=kind,
        x=rng.uniform(0.0, 1.0, n),
        y=rng.uniform(0.0, 1.0, n),
        size=rng.uniform(*spec.size, n),
        speed=rng.uniform(*spec.speed, n),
        drift=drift,
        phase=rng.uniform(0.0, 2 * math.pi, n),
        sway_hz=rng.uniform(*spec.sway_hz, n),
        spin=rng.uniform(-spec.spin, spec.spin, n),
        color=rng.integers(0, max(colors, 1), n),
    )


def _edge_fade(u: np.ndarray) -> np.ndarray:
    """1 inside the area, falling to 0 within :data:`EDGE_FADE` of either edge."""
    return np.clip(np.minimum(u, 1.0 - u) / EDGE_FADE, 0.0, 1.0)


def particle_states(seeds: ParticleSeeds, t: float, width: float = 1.0, height: float = 1.0) -> ParticleStates:
    """Where the particles are ``t`` seconds after they started, in an area ``width`` x
    ``height`` shorter sides large. A particle leaving one edge comes back at the other."""
    spec = particle_kind(seeds.kind)
    sway = spec.sway * np.sin(2 * math.pi * seeds.sway_hz * t + seeds.phase)
    y = np.mod(seeds.y + spec.fall * seeds.speed * t / height, 1.0)
    x = np.mod(seeds.x + (seeds.drift * t + sway) / width, 1.0)
    size = seeds.size.copy()
    angle = np.zeros(len(seeds))
    flip = np.ones(len(seeds))
    opacity = np.full(len(seeds), spec.opacity) * _edge_fade(x)
    if spec.shape == "streak":  # along its fall: tilted by the wind
        angle[:] = math.atan2(spec.drift, spec.fall)
    if spec.spin:
        turns = seeds.spin * t
        angle = seeds.phase + 2 * math.pi * turns
        flip = np.cos(2 * math.pi * 1.3 * turns + seeds.phase)
    if spec.twinkle:
        opacity *= np.sin(math.pi * np.mod(t / (spec.twinkle * seeds.speed) + seeds.phase / (2 * math.pi), 1.0)) ** 2
    if spec.grow != 1.0:  # smoke: grows and thins out as it rises (life 0 at the bottom, 1 at the top)
        life = 1.0 - y
        size *= 1.0 + (spec.grow - 1.0) * life
        opacity *= np.clip(life / 0.15, 0.0, 1.0) * (1.0 - life)
    else:
        opacity *= _edge_fade(y)
    return ParticleStates(x=x, y=y, size=size, angle=angle, flip=flip, opacity=opacity)


def check_area(area: list[float]) -> list[float]:
    """``[x, y, w, h]`` fractions of the frame from its top-left corner, inside the frame;
    ``ValueError`` otherwise."""
    if len(area) != 4:
        raise ValueError("area is [x, y, w, h]: fractions 0-1 of the frame from its top-left corner")
    x, y, w, h = area
    if not all(0.0 <= v <= 1.0 for v in area) or w <= 0 or h <= 0:
        raise ValueError("area: every value is a fraction from 0 to 1, and w and h are above 0")
    if x + w > 1.0 + 1e-6 or y + h > 1.0 + 1e-6:
        raise ValueError("area: x + w and y + h must be at most 1 (inside the frame)")
    return area
