"""Lightning, thunder and rainbows on a stage (DESIGN.md §69.61). No manim:
:mod:`vidgen.cartoon.weather_drawing` draws the bolt and the rainbow, and the stage's light
(:class:`~vidgen.cartoon.shading.StageLight`) flashes.

A *strike* lights the whole set in two or three quick pulses (:func:`strike_pulses`), each held
for a few hundredths of a second and dying away; the light's grade is taken part of the way to a
cold white (:func:`flash_grade`). Its thunder comes ``distance`` km later at the speed of sound
(:func:`thunder_delay`), quieter, longer and lower the farther away (:func:`thunder_cue`). A rain
field with ``lightning`` strikes at seeded times (:func:`storm_strikes`).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from vidgen.cartoon.lighting import LightGrade, fade_at
from vidgen.lint.color import hex_rgb

#: The speed of sound, km per second (thunder comes this much later per km).
SOUND_KM_PER_SECOND = 0.343
#: How far a strike is when nothing says (km), and the farthest it may be.
THUNDER_DISTANCE = 1.0
MAX_DISTANCE = 10.0
#: The colour a flash lights the set towards, and how far (0..1) a full nearby flash takes it.
FLASH_COLOR = "#EEF2FF"
FLASH_SHARE = 0.5
#: In a room only the light through the windows reaches the set: this share of a flash.
ROOM_FLASH = 0.5
#: How far (0..1) a full flash takes the sky seen through a room's windows to its colour.
WINDOW_FLASH = 0.85
#: A flash's pulses: (start s after the strike, length s, peak 0..1); a strike shows the first two
#: or all three. Each holds its peak for its length and dies away with :data:`FLASH_DECAY` (s)
#: over :data:`FLASH_TAIL` seconds.
FLASH_PULSES: tuple[tuple[float, float, float], ...] = ((0.0, 0.1, 1.0), (0.2, 0.08, 0.7), (0.36, 0.06, 0.45))
FLASH_DECAY = 0.07
FLASH_TAIL = 0.25
#: How long a ``lightning`` action's flash lasts at most (its run time), s.
FLASH_SECONDS = FLASH_PULSES[-1][0] + 0.03 + FLASH_PULSES[-1][1] + FLASH_TAIL
#: A rain storm: seconds between strikes on average when ``lightning: true``, and the share of
#: strikes with a bolt (the others are sheet lightning: a flash only).
STORM_EVERY = 8.0
STORM_BOLTS = 0.7
#: Thunder: its level at the strike (dB) and per km farther, the quietest, its length at the strike
#: (s) and per km, and how much lower it is per km (semitones).
THUNDER_GAIN = -3.0
THUNDER_GAIN_PER_KM = -3.0
THUNDER_QUIETEST = -18.0
THUNDER_SECONDS = 2.2
THUNDER_SECONDS_PER_KM = 0.6
THUNDER_PITCH_PER_KM = -1.0

#: A bolt: corners of its main channel, and how many branches it may fork into.
BOLT_CORNERS = 11
BOLT_BRANCHES = (1, 3)

#: A rainbow's bands from the outside in (red to violet, soft), how strongly it shows when fully
#: in (opacity), its width (the outer diameter as a share of the frame width), its bands' thickness
#: all together (a share of its radius) and how long it fades in by default (s).
RAINBOW_COLORS = ("#E8665F", "#F2A050", "#F2D65E", "#7FC77B", "#5FA9DE", "#6F7FD2", "#9B78C4")
RAINBOW_OPACITY = 0.55
RAINBOW_WIDTH = 0.75
RAINBOW_THICKNESS = 0.16
RAINBOW_FADE_SECONDS = 3.0


def thunder_delay(distance: float) -> float:
    """Seconds from a strike ``distance`` km away to its thunder."""
    return max(float(distance), 0.0) / SOUND_KM_PER_SECOND


@dataclass(frozen=True)
class ThunderCue:
    """A strike's thunder: ``delay`` after the light (s), ``gain`` (dB) and the built-in
    ``thunder`` sound's ``duration`` (s), ``intensity`` (0..1: the crack) and ``pitch`` (semitones)."""

    delay: float
    gain: float
    duration: float
    intensity: float
    pitch: float


def thunder_cue(distance: float) -> ThunderCue:
    """The thunder of a strike ``distance`` km away: later, quieter, longer, lower and with less
    of a crack the farther it is."""
    d = min(max(float(distance), 0.0), MAX_DISTANCE)
    return ThunderCue(
        delay=thunder_delay(d),
        gain=max(THUNDER_GAIN + THUNDER_GAIN_PER_KM * d, THUNDER_QUIETEST),
        duration=min(THUNDER_SECONDS + THUNDER_SECONDS_PER_KM * d, 7.0),
        intensity=min(max(0.9 - 0.15 * d, 0.15), 0.9),
        pitch=max(THUNDER_PITCH_PER_KM * d, -6.0),
    )


def flash_strength(distance: float) -> float:
    """How bright a strike ``distance`` km away lights the set (1 nearby, at least 0.4 far off)."""
    return min(max(1.1 - 0.14 * float(distance), 0.4), 1.0)


def strike_pulses(seed: int) -> tuple[tuple[float, float, float], ...]:
    """The pulses of a strike (:data:`FLASH_PULSES`, seeded): two or three, the later ones a little
    earlier or later and dimmer or brighter."""
    rng = random.Random(seed)
    count = 3 if rng.random() < 0.5 else 2
    pulses = [FLASH_PULSES[0]]
    for start, length, peak in FLASH_PULSES[1:count]:
        pulses.append((start + 0.06 * (rng.random() - 0.5), length, peak * (0.85 + 0.15 * rng.random())))
    return tuple(pulses)


def pulse_level(pulses: Sequence[tuple[float, float, float]], age: float) -> float:
    """How bright (0..1) ``pulses`` light ``age`` seconds after their strike."""
    level = 0.0
    for start, length, peak in pulses:
        since = age - start
        if since < 0:
            continue
        if since <= length:
            level = max(level, peak)
        elif since - length <= FLASH_TAIL:
            level = max(level, peak * math.exp(-(since - length) / FLASH_DECAY))
    return level


@dataclass(frozen=True)
class Strike:
    """A lightning strike at scene time ``time``: where (``x``, 0..1 of the stage's width), how far
    (``distance``, km), its ``seed`` (pulses and bolt) and whether a ``bolt`` shows."""

    time: float
    x: float
    distance: float = THUNDER_DISTANCE
    seed: int = 1
    bolt: bool = True
    pulses: tuple[tuple[float, float, float], ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pulses", strike_pulses(self.seed))

    @property
    def end(self) -> float:
        """When its light is gone (scene time)."""
        start, length, _ = self.pulses[-1]
        return self.time + start + length + FLASH_TAIL

    def level(self, now: float) -> float:
        """How bright it lights the set at scene time ``now`` (0..1, nearer brighter)."""
        if not self.time <= now <= self.end:
            return 0.0
        return flash_strength(self.distance) * pulse_level(self.pulses, now - self.time)

    @property
    def thunder(self) -> ThunderCue:
        """Its thunder."""
        return thunder_cue(self.distance)


def flash_level(strikes: Sequence[Strike], now: float) -> float:
    """How bright the strikes light the set at scene time ``now`` (the brightest)."""
    return max((s.level(now) for s in strikes), default=0.0)


def flashing(strikes: Sequence[Strike], start: float, end: float) -> bool:
    """Whether a strike lights the set between scene times ``start`` and ``end`` (a stage then
    redraws everything on every frame)."""
    return any(s.time < end and s.end > start for s in strikes)


def flash_grade(grade: LightGrade, level: float, *, share: float = FLASH_SHARE, color: str = FLASH_COLOR) -> LightGrade:
    """``grade`` lit by a flash at ``level`` (0..1): every colour ``level * share`` of the way to
    ``color``, the stars and shadows fading as much. ``grade`` itself at level 0."""
    f = min(max(float(level) * float(share), 0.0), 1.0)
    if f <= 0.0:
        return grade
    white = hex_rgb(color)
    multiply = tuple(m * (1.0 - f) for m in grade.multiply)
    glow = tuple(g * (1.0 - f) + f * w for g, w in zip(grade.glow, white))
    return LightGrade(multiply, glow, grade.stars * (1.0 - f), grade.shadow * (1.0 - f), grade.saturation)  # type: ignore[arg-type]


def storm_strikes(start: float, until: float, *, every: float = STORM_EVERY, seed: int = 1, stop: float | None = None) -> list[Strike]:
    """The strikes of a rain storm from scene time ``start`` that happen before ``until`` (and
    before ``stop``, when the rain stopped): seeded gaps of ``every`` × 0.5..1.5 seconds (the first
    0.3..1 × ``every`` in), places across the stage, 0.6 to 4 km away, most with a bolt. The same
    seed gives the same strikes, whatever ``until`` is."""
    rng = random.Random(seed)
    end = until if stop is None else min(until, stop)
    strikes: list[Strike] = []
    time = start + every * (0.3 + 0.7 * rng.random())
    while time < end:
        x, far, bolt, own = rng.random(), rng.random(), rng.random(), rng.random()
        strikes.append(Strike(time, 0.12 + 0.76 * x, round(0.6 + 3.4 * far ** 1.5, 3), int(own * 2**31), bolt < STORM_BOLTS))
        time += every * (0.5 + rng.random())
    return strikes


@dataclass(frozen=True)
class RainStorm:
    """The lightning of a rain field with ``lightning`` (:func:`storm_strikes`): from scene time
    ``start``, every ``every`` seconds or so (seeded by ``seed``), until the field's fade out ends
    (``ended()``, ``None`` while it rains)."""

    start: float
    every: float
    seed: int
    ended: Callable[[], float | None]

    def strikes(self, until: float) -> list[Strike]:
        """Its strikes before scene time ``until``."""
        return storm_strikes(self.start, until, every=self.every, seed=self.seed, stop=self.ended())

    def over(self, now: float) -> bool:
        """Whether no strike lights the set after scene time ``now`` (the rain has stopped and its
        last strike is over)."""
        stop = self.ended()
        return stop is not None and all(s.end <= now for s in self.strikes(stop))


def thunder_pan(x: float) -> float:
    """Where a strike at ``x`` (0..1 of the stage) is heard, -0.8 (left) .. 0.8 (right)."""
    return min(max((float(x) - 0.5) * 1.6, -0.8), 0.8)


def bolt_paths(seed: int, x: float, top: float, bottom: float, spread: float) -> list[np.ndarray]:
    """A bolt from ``top`` down to ``bottom`` (y, Manim units) striking at ``x``: its main channel,
    zigzagging up to ``spread`` sideways, then one to three shorter branches forking off it; each
    an ``(n, 2)`` array of corners."""
    rng = random.Random(seed)
    corners = BOLT_CORNERS
    start_x = x + spread * 0.6 * (rng.random() - 0.5)
    main = np.zeros((corners, 2))
    for k in range(corners):
        share = k / (corners - 1)
        jitter = 0.0 if k in (0, corners - 1) else spread * 0.35 * (rng.random() - 0.5)
        main[k] = (start_x + (x - start_x) * share + jitter, top + (bottom - top) * share)
    paths = [main]
    low, high = BOLT_BRANCHES
    for _ in range(low + int(rng.random() * (high - low + 1) * 0.999)):
        at = 2 + int(rng.random() * (corners - 5))
        side = 1.0 if rng.random() < 0.5 else -1.0
        steps = 3 + int(rng.random() * 2)
        branch = [main[at].copy()]
        for _ in range(steps):
            prev = branch[-1]
            branch.append(np.array([prev[0] + side * spread * (0.12 + 0.18 * rng.random()), prev[1] + (bottom - top) / corners * (0.6 + 0.5 * rng.random())]))
        paths.append(np.array(branch))
    return paths


@dataclass(frozen=True)
class RainbowChange:
    """A rainbow fading to ``value`` (0 gone .. 1 fully in) from scene time ``start`` over
    ``seconds`` (:func:`~vidgen.cartoon.lighting.fade_at`)."""

    start: float
    seconds: float
    value: float

    @property
    def end(self) -> float:
        """When the fade is over."""
        return self.start + max(self.seconds, 0.0)


def rainbow_level(changes: Sequence[RainbowChange], now: float) -> float:
    """How much of the rainbow shows at scene time ``now`` (0..1; none before its first change)."""
    return fade_at(0.0, changes, now, lambda a, b, s: a + (b - a) * s)


def rainbow_bands(cx: float, base: float, radius: float, *, thickness: float = RAINBOW_THICKNESS, points: int = 48) -> list[np.ndarray]:
    """The outlines of a rainbow's bands (:data:`RAINBOW_COLORS`, outside in): half rings about
    (``cx``, ``base``), the outer one ``radius`` wide, all of them ``thickness`` × ``radius``
    together; each an ``(n, 2)`` array, the outer arc left to right, then the inner one back."""
    width = radius * thickness / len(RAINBOW_COLORS)
    angles = np.linspace(math.pi, 0.0, points)
    unit = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    bands = []
    for k in range(len(RAINBOW_COLORS)):
        outer, inner = radius - k * width, radius - (k + 1) * width
        ring = np.concatenate([unit * outer, unit[::-1] * inner]) + np.array([cx, base])
        bands.append(ring)
    return bands


__all__ = [
    "FLASH_COLOR",
    "FLASH_SECONDS",
    "FLASH_SHARE",
    "MAX_DISTANCE",
    "RAINBOW_COLORS",
    "RAINBOW_FADE_SECONDS",
    "RAINBOW_OPACITY",
    "RAINBOW_WIDTH",
    "ROOM_FLASH",
    "SOUND_KM_PER_SECOND",
    "STORM_EVERY",
    "THUNDER_DISTANCE",
    "WINDOW_FLASH",
    "RainStorm",
    "RainbowChange",
    "Strike",
    "ThunderCue",
    "bolt_paths",
    "flash_grade",
    "flash_level",
    "flash_strength",
    "flashing",
    "pulse_level",
    "rainbow_bands",
    "rainbow_level",
    "storm_strikes",
    "strike_pulses",
    "thunder_cue",
    "thunder_delay",
    "thunder_pan",
]
