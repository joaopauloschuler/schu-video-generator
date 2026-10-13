"""Automatic life of characters: blinking, breathing, head sway, an animal's tail swishing and a
robot's antenna wobbling with its light blinking (DESIGN.md §69.5, §69.48, §69.58), and the
motion some expressions add (*moods*, §69.59). No manim.

A character's *idle clock* runs while its updaters run. Manim suspends a mobject's updaters
while an animation plays on it, so the clock stops during a :class:`~vidgen.cartoon.transition.PoseChange`
and no blink starts then; ``PoseChange`` ends a blink that is running when it begins.
:func:`blink_times` gives the same schedule in scene seconds without drawing anything.

A mood follows from the shapes the face shows (:data:`MOOD_SHAPES`): ``swirl`` eyes sway the
body and head (``dizzy``), ``wide`` eyes shiver and stretch a robot's antenna (``frightened``),
a ``laugh`` mouth or ``tears`` bounce the shoulders. Its strength grows and dies away on
:data:`MOOD_SPRING` (a little past full: an antenna springs up), so nothing jumps when the
expression changes. Closed eyes (:data:`BLINKLESS_EYES`) do not blink; ``swirl`` eyes and
``tears`` alternate with a second shape (:data:`ALTERNATE_SHAPES`).
"""

from __future__ import annotations

import math
import random
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from vidgen.cartoon.spring import Spring
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
#: One swish of an animal's tail, to and fro (seconds), and its largest angle (degrees).
TAIL_SWAY_SECONDS = 2.6
TAIL_SWAY_DEGREES = 5.0
#: A robot's antenna on its spring: one wobble (seconds) and its largest angle (degrees); its light
#: goes dim once per :data:`ANTENNA_BLINK_SECONDS` for :data:`ANTENNA_DIM_SHARE` of it (the
#: ``antenna`` part's shape :data:`ANTENNA_DIM_SHAPE`, DESIGN.md §69.58).
ANTENNA_SWAY_SECONDS = 1.7
ANTENNA_SWAY_DEGREES = 3.0
ANTENNA_BLINK_SECONDS = 1.3
ANTENNA_DIM_SHARE = 0.3
ANTENNA_DIM_SHAPE = "dim"

#: Which mood a shown shape starts: (part, shape, mood), the first that matches wins.
MOOD_SHAPES: tuple[tuple[str, str, str], ...] = (
    ("eyes", "swirl", "sway"), ("eyes", "wide", "shiver"), ("mouth", "laugh", "bounce"), ("cheeks", "tears", "bounce"),
)
MOODS: tuple[str, ...] = ("sway", "shiver", "bounce")
#: How a mood's strength (0..1) grows in and dies away (DESIGN.md §69.15's spring).
MOOD_SPRING = Spring.tuned(1.4, 0.45)
#: After this long a mood that ended has died away (within 0.5 % of rest).
MOOD_SETTLE_SECONDS = MOOD_SPRING.settle_seconds(0.005)
#: ``sway``: one sway of the body about the hips (seconds), its largest angle and the head's
#: (degrees; the head lags a quarter of a sway behind).
MOOD_SWAY_SECONDS = 1.8
MOOD_SWAY_DEGREES = 4.0
MOOD_SWAY_HEAD_DEGREES = 6.0
#: ``shiver``: shakes per second and how far the body shakes (character units); a robot's antenna
#: stretches by this share of its length.
SHIVER_HZ = 13.0
SHIVER_SHIFT = 0.005
ANTENNA_FRIGHT_STRETCH = 0.35
#: ``bounce`` (laughing, sobbing): bounces per second and their height (character units).
BOUNCE_HZ = 4.5
BOUNCE_SHIFT = 0.008
#: Eye shapes that are closed already: no blink shows over them.
BLINKLESS_EYES: frozenset[str] = frozenset({"closed", "laughing", "swirl", "swirl_turned"})
#: Shapes shown in turn with a second one every :data:`ALTERNATE_SECONDS`: (part, shape) -> the other.
ALTERNATE_SHAPES: dict[tuple[str, str], str] = {("eyes", "swirl"): "swirl_turned", ("cheeks", "tears"): "tears_running"}
ALTERNATE_SECONDS = 0.2


def shape_mood(shapes: Mapping[str, str | None]) -> str | None:
    """The mood of a face showing ``shapes`` (part -> shape name; :data:`MOOD_SHAPES`), ``None``: none."""
    return next((mood for part, shape, mood in MOOD_SHAPES if shapes.get(part) == shape), None)


def alternate_shape(part: str, shape: str | None, seconds: float) -> str | None:
    """The shape ``part`` shows ``seconds`` into the idle clock instead of ``shape``: its
    :data:`ALTERNATE_SHAPES` partner every other :data:`ALTERNATE_SECONDS`, else ``None`` (``shape``)."""
    other = ALTERNATE_SHAPES.get((part, shape)) if shape is not None else None
    return other if other is not None and int(seconds / ALTERNATE_SECONDS) % 2 else None


@dataclass(frozen=True)
class MoodMotion:
    """The motion moods add now: the body's angle (degrees, about the hips) and shift (character
    units), the head's extra angle, a robot's antenna's stretch (a factor on its height) and how
    much hair standing up quivers (a factor on its height)."""

    body_angle: float = 0.0
    body_shift: tuple[float, float] = (0.0, 0.0)
    head_angle: float = 0.0
    antenna_stretch: float = 1.0
    bristle_quiver: float = 1.0

    @property
    def is_still(self) -> bool:
        """True when it moves nothing."""
        return self == MoodMotion()


def mood_motion(levels: Mapping[str, float], seconds: float, seed: int) -> MoodMotion:
    """The motion of the moods at strengths ``levels`` (mood -> 0..1, a little more while it
    springs in) ``seconds`` into the idle clock (phases from ``seed``)."""
    sway, shiver, bounce = (levels.get(mood, 0.0) for mood in MOODS)
    phase = 2.0 * math.pi * seconds / MOOD_SWAY_SECONDS + _phase(seed, 0.137)
    shake = math.sin(2.0 * math.pi * SHIVER_HZ * seconds)
    hop = abs(math.sin(math.pi * BOUNCE_HZ * seconds))
    return MoodMotion(
        body_angle=sway * MOOD_SWAY_DEGREES * math.sin(phase),
        body_shift=(shiver * SHIVER_SHIFT * shake, bounce * BOUNCE_SHIFT * hop),
        head_angle=sway * MOOD_SWAY_HEAD_DEGREES * math.sin(phase - 0.5 * math.pi),
        antenna_stretch=1.0 + shiver * ANTENNA_FRIGHT_STRETCH,
        bristle_quiver=1.0 + shiver * 0.06 * math.sin(2.0 * math.pi * 0.7 * SHIVER_HZ * seconds),
    )


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


def tail_sway_angle(seconds: float, seed: int) -> float:
    """A tail's extra angle (degrees) ``seconds`` into the idle clock: 0 at the clock's start,
    within ±2 × :data:`TAIL_SWAY_DEGREES` (one swish every :data:`TAIL_SWAY_SECONDS`)."""
    phase = _phase(seed, 0.302776)
    return TAIL_SWAY_DEGREES * (math.sin(2.0 * math.pi * seconds / TAIL_SWAY_SECONDS + phase) - math.sin(phase))


def antenna_sway_angle(seconds: float, seed: int) -> float:
    """A robot's antenna's extra angle (degrees) ``seconds`` into the idle clock: 0 at the clock's
    start, within ±2 × :data:`ANTENNA_SWAY_DEGREES` (one wobble every :data:`ANTENNA_SWAY_SECONDS`)."""
    phase = _phase(seed, 0.236068)
    return ANTENNA_SWAY_DEGREES * (math.sin(2.0 * math.pi * seconds / ANTENNA_SWAY_SECONDS + phase) - math.sin(phase))


def antenna_light_on(seconds: float, seed: int) -> bool:
    """Whether a robot's antenna light is lit ``seconds`` into the idle clock: lit at the clock's
    start, dim for :data:`ANTENNA_DIM_SHARE` of each :data:`ANTENNA_BLINK_SECONDS` (phase from ``seed``)."""
    cycle = (seconds / ANTENNA_BLINK_SECONDS + 0.5 * ((seed * 0.381966) % 1.0)) % 1.0
    return not 0.6 <= cycle < 0.6 + ANTENNA_DIM_SHARE


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
    #: The mood now (``None``: none), the one dying away, when it changed and their strengths then.
    mood: str | None = None
    fading: str | None = None
    mood_since: float = 0.0
    mood_from: float = 0.0
    fading_from: float = 0.0

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.next_blink = next_blink_gap(self.rng)

    def mood_levels(self) -> dict[str, float]:
        """Each mood's strength now (mood -> level; moods at rest left out): the mood growing on
        :data:`MOOD_SPRING` from its strength when it began, the one before dying away."""
        elapsed = self.seconds - self.mood_since
        grown = MOOD_SPRING.step_response(elapsed)
        levels = {}
        if self.fading is not None and elapsed < MOOD_SETTLE_SECONDS:   # a strength, not a place: never below nothing
            levels[self.fading] = self.fading_from * max(0.0, 1.0 - grown)
        if self.mood is not None:
            levels[self.mood] = self.mood_from + (1.0 - self.mood_from) * grown
        return levels

    def set_mood(self, mood: str | None) -> None:
        """Change the mood to ``mood`` from now (nothing when it is the mood already)."""
        if mood == self.mood:
            return
        levels = self.mood_levels()
        self.fading, self.fading_from = self.mood, levels.get(self.mood, 0.0) if self.mood is not None else 0.0
        self.mood, self.mood_from = mood, levels.get(mood, 0.0) if mood is not None else 0.0
        self.mood_since = self.seconds

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
    "ALTERNATE_SECONDS",
    "ALTERNATE_SHAPES",
    "ANTENNA_BLINK_SECONDS",
    "ANTENNA_DIM_SHAPE",
    "ANTENNA_DIM_SHARE",
    "ANTENNA_FRIGHT_STRETCH",
    "ANTENNA_SWAY_DEGREES",
    "ANTENNA_SWAY_SECONDS",
    "BLINKLESS_EYES",
    "BLINK_GAP_SECONDS",
    "BLINK_SECONDS",
    "BOUNCE_HZ",
    "BOUNCE_SHIFT",
    "BREATH_SCALE",
    "BREATH_SECONDS",
    "MOODS",
    "MOOD_SETTLE_SECONDS",
    "MOOD_SHAPES",
    "MOOD_SPRING",
    "MOOD_SWAY_DEGREES",
    "MOOD_SWAY_HEAD_DEGREES",
    "MOOD_SWAY_SECONDS",
    "SHIVER_HZ",
    "SHIVER_SHIFT",
    "SWAY_DEGREES",
    "SWAY_SECONDS",
    "TAIL_SWAY_DEGREES",
    "TAIL_SWAY_SECONDS",
    "IdleClock",
    "MoodMotion",
    "alternate_shape",
    "antenna_light_on",
    "antenna_sway_angle",
    "blink_times",
    "breath_scale",
    "idle_seed",
    "mood_motion",
    "next_blink_gap",
    "shape_mood",
    "sway_angle",
    "tail_sway_angle",
]
