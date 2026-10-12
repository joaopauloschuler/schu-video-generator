"""Automatic life of characters: blinking, breathing and head sway (DESIGN.md §69.5). No manim.

A character's *idle clock* runs while its updaters run. Manim suspends a mobject's updaters
while an animation plays on it, so the clock stops during a :class:`~vidgen.cartoon.transition.PoseChange`
and no blink starts then; ``PoseChange`` ends a blink that is running when it begins.
:func:`blink_times` gives the same schedule in scene seconds without drawing anything.
"""

from __future__ import annotations

import math
import random
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field

from vidgen.errors import VidgenError

#: How long the eyes stay closed in one blink (seconds).
BLINK_SECONDS = 0.15
#: Shortest and longest time from one blink's start to the next (seconds).
BLINK_GAP_SECONDS: tuple[float, float] = (2.0, 6.0)
#: One breath (seconds) and the body's largest extra (x, y) scale in it.
BREATH_SECONDS = 3.6
BREATH_SCALE: tuple[float, float] = (0.006, 0.015)
#: One head sway, left and right (seconds), and its largest angle (degrees).
SWAY_SECONDS = 5.5
SWAY_DEGREES = 1.5


def idle_seed(name: str) -> int:
    """The default seed of a character called ``name`` (so two characters do not blink together)."""
    return zlib.crc32(name.encode("utf-8"))


def next_blink_gap(rng: random.Random) -> float:
    """Seconds from one blink's start to the next: uniform in :data:`BLINK_GAP_SECONDS`
    (``random()``, unlike ``uniform()``, gives the same sequence in every Python version)."""
    low, high = BLINK_GAP_SECONDS
    return low + (high - low) * rng.random()


def _phase(seed: int, ratio: float) -> float:
    return 2.0 * math.pi * ((seed * ratio) % 1.0)


def breath_scale(seconds: float, seed: int) -> tuple[float, float]:
    """The body's (x, y) scale ``seconds`` into the idle clock: 1 at the clock's start, within
    1 ± :data:`BREATH_SCALE` (one breath every :data:`BREATH_SECONDS`, phase from ``seed``)."""
    phase = _phase(seed, 0.618034)
    breath = 0.5 * (math.cos(phase) - math.cos(2.0 * math.pi * seconds / BREATH_SECONDS + phase))
    return 1.0 + BREATH_SCALE[0] * breath, 1.0 + BREATH_SCALE[1] * breath


def sway_angle(seconds: float, seed: int) -> float:
    """The head's extra angle (degrees) ``seconds`` into the idle clock: 0 at the clock's start,
    within ±2 × :data:`SWAY_DEGREES` (one sway every :data:`SWAY_SECONDS`, phase from ``seed``)."""
    phase = _phase(seed, 0.414214)
    return SWAY_DEGREES * (math.sin(2.0 * math.pi * seconds / SWAY_SECONDS + phase) - math.sin(phase))


def _merged(windows: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for start, end in sorted((float(a), float(b)) for a, b in windows):
        if end <= start:
            raise VidgenError(f"pose change window ({start}, {end}) must end after it starts")
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def blink_times(
    seed: int, duration: float, *, pose_changes: Iterable[tuple[float, float]] = ()
) -> list[tuple[float, float]]:
    """The blinks (start, end) in scene seconds of a character idling from 0 to ``duration``,
    with pose changes (or other animations played on it) at the ``pose_changes`` windows (start,
    end): the idle clock stops in them, so no blink starts there, and a blink running when one
    begins ends then. Blinks start :func:`next_blink_gap` apart on the idle clock, the first one
    gap after its start. The same seed always gives the same blinks."""
    pauses = _merged(pose_changes)
    rng = random.Random(seed)
    clock = next_blink_gap(rng)
    blinks: list[tuple[float, float]] = []
    while True:
        start = clock
        for pause_start, pause_end in pauses:
            if pause_start <= start:
                start += pause_end - pause_start
        if start >= duration:
            return blinks
        end = min([start + BLINK_SECONDS, *(p for p, _ in pauses if p > start)])
        blinks.append((start, end))
        clock += next_blink_gap(rng)


@dataclass
class IdleClock:
    """The running idle state of one character (driven by :meth:`advance` each frame)."""

    seed: int
    seconds: float = 0.0
    blink_end: float | None = None
    rng: random.Random = field(init=False, repr=False)
    next_blink: float = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.next_blink = next_blink_gap(self.rng)

    @property
    def is_blinking(self) -> bool:
        """True while the eyes are closed in a blink."""
        return self.blink_end is not None

    def advance(self, dt: float) -> None:
        """Move the clock ``dt`` seconds on: start a blink that is due, end one that is over."""
        self.seconds += dt
        while self.seconds >= self.next_blink:
            self.blink_end = self.next_blink + BLINK_SECONDS
            self.next_blink += next_blink_gap(self.rng)
        if self.blink_end is not None and self.seconds >= self.blink_end:
            self.blink_end = None

    def end_blink(self) -> None:
        """Open the eyes now (the blink is not resumed)."""
        self.blink_end = None


__all__ = [
    "BLINK_GAP_SECONDS",
    "BLINK_SECONDS",
    "BREATH_SCALE",
    "BREATH_SECONDS",
    "SWAY_DEGREES",
    "SWAY_SECONDS",
    "IdleClock",
    "blink_times",
    "breath_scale",
    "idle_seed",
    "next_blink_gap",
    "sway_angle",
]
