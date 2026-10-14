"""Wind on a stage (DESIGN.md §69.32): its strength over time (the ``wind`` param and the fades
of the ``wind`` beat action), seeded gusts, how far props lean and how far a character's scarf,
hair, ears and hat trail behind. No manim: :mod:`vidgen.cartoon.windblown` draws them.

A wind *level* is signed: ``0`` is calm, ``1`` a gale blowing to the right (towards ``+x`` on
screen), ``-1`` one blowing to the left. Its *force* at a time is the level times a steady share
plus a gust share, the gusts being smooth seeded noise (:func:`gust`), so the same seed gives the
same wind in every render. Every function is pure: values depend only on the arguments and the
scene time, never on frames drawn before (a storyboard still or a seek shows the same).

Strong wind shows more than its force alone (:func:`felt_force`), and a light prop can blow away
(the ``blow_away`` action) along a seeded gusty, tumbling path (:func:`blown_point`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated, Literal

import numpy as np
from pydantic import Field

from vidgen.cartoon.idle import idle_seed
from vidgen.cartoon.lighting import changing, fade_at
from vidgen.cartoon.spring import Spring

#: Named wind levels (the ``wind`` param and action also take a number from -1 to 1).
WIND_LEVELS: dict[str, float] = {"calm": 0.0, "breeze": 0.3, "windy": 0.6, "gale": 1.0}
#: A ``wind`` setting: a signed level or a name of :data:`WIND_LEVELS`.
WindSetting = Annotated[float, Field(ge=-1.0, le=1.0)] | Literal[tuple(WIND_LEVELS)]  # type: ignore[valid-type]
#: Seconds a ``wind`` beat action fades over by default.
WIND_FADE_SECONDS = 2.0
#: The share of the force that blows steadily; the rest comes and goes in gusts.
STEADY_SHARE = 0.5
#: The gusts' noise: (seconds between two random values, weight) per octave.
GUST_OCTAVES: tuple[tuple[float, float], ...] = ((2.6, 0.65), (0.85, 0.35))
#: Seconds a gust takes to cross the stage from the side it blows from to the other.
GUST_CROSSING_SECONDS = 1.2
#: Seconds between the samples :meth:`Wind.blown` adds up (particles drifting).
BLOWN_STEP = 0.05


@dataclass(frozen=True)
class Sway:
    """How a prop kind sways: ``degrees`` its top leans at force 1, ``hz`` its own to-and-fro on
    top of that, ``bend_from`` the share of its height that stays straight (a plant's pot)."""

    degrees: float
    hz: float
    bend_from: float = 0.0


#: The built-in props that sway, pivoting at their base.
SWAYS: dict[str, Sway] = {
    "tree": Sway(8.0, 0.45, 0.08),
    "bush": Sway(6.0, 0.8),
    "plant": Sway(12.0, 1.1, 0.45),
    "sign": Sway(2.0, 1.4),
    "lamp": Sway(1.5, 1.2),
    "pine": Sway(6.0, 0.4, 0.08),
    "flowers": Sway(10.0, 1.2, 0.2),
}
#: How much a prop's own to-and-fro adds to its lean (a share of it).
SWAY_WOBBLE = 0.25
#: Strong wind moves things more than its force alone says (:func:`felt_force`): the felt force
#: is the force times ``1 + WIND_BOOST × |force|``, so a gale (force 1) bends and trails
#: ``1 + WIND_BOOST`` times as far as the linear rule, a breeze little more.
WIND_BOOST = 2.0

#: How far a trailing piece (scarf end, long hair, floppy ears, hat) turns at felt force 1,
#: before its own weight (:data:`vidgen.cartoon.generator.TRAIL_WEIGHTS`).
TRAIL_DEGREES = 24.0
#: A trailing piece turns at most about this far (degrees before its weight; a soft limit, so a
#: gale's scarf streams out flat but does not swing over the head).
TRAIL_LIMIT = 80.0
#: The spring a trailing piece follows the force with: it lags a gust and swings past it.
TRAIL_SPRING = Spring.tuned(1.2, 0.3)
#: A small quick flutter on top (degrees at felt level 1, and its frequency).
FLUTTER_DEGREES = 4.0
FLUTTER_HZ = 2.5

_MASK = (1 << 64) - 1


def wind_level(setting: float | str) -> float:
    """The signed level of a ``wind`` setting: a number from -1 to 1 (also as text, the action's
    ``- wind: 0.6``) or a name of :data:`WIND_LEVELS`; ``ValueError`` otherwise."""
    if isinstance(setting, str):
        if setting in WIND_LEVELS:
            return WIND_LEVELS[setting]
        try:
            value = float(setting)
        except ValueError:
            raise ValueError(f"unknown wind {setting!r}; a number from -1 to 1 or {', '.join(WIND_LEVELS)}") from None
    else:
        value = float(setting)
    if not -1.0 <= value <= 1.0 or math.isnan(value):
        raise ValueError(f"wind {value:g} is out of range: from -1 (a gale to the left) to 1 (a gale to the right)")
    return value


@lru_cache(maxsize=4096)
def _knot(seed: int, octave: int, k: int) -> float:
    """A random value in 0..1 for knot ``k`` of an octave (splitmix64 of the three integers)."""
    x = (seed * 0x9E3779B97F4A7C15 + octave * 0xC2B2AE3D27D4EB4F + k * 0xD6E8FEB86659FD93) & _MASK
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _MASK
    return (x ^ (x >> 31)) / float(1 << 64)


def gust(seconds: float, seed: int = 1) -> float:
    """The gusts at ``seconds``: smooth noise from 0 (a lull) to 1 (a gust), the weighted sum of
    :data:`GUST_OCTAVES` (random values at even steps, eased between with a quintic so the force
    has no kinks); the same ``seed`` always gives the same gusts."""
    total = 0.0
    for octave, (step, weight) in enumerate(GUST_OCTAVES):
        u = seconds / step
        k = math.floor(u)
        f = u - k
        ease = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)
        a, b = _knot(seed, octave, k), _knot(seed, octave, k + 1)
        total += weight * (a + (b - a) * ease)
    return total / sum(w for _, w in GUST_OCTAVES)


def wind_seed(name: str) -> int:
    """The gusts' seed of a scene called ``name`` (the name hash of the idle motion)."""
    return idle_seed(name)


def wind_phase(name: str) -> float:
    """A phase (radians) from a name, so two props or characters do not move in step."""
    return 2.0 * math.pi * (idle_seed(name) / float(1 << 32))


@dataclass(frozen=True)
class WindChange:
    """A change of the wind: from whatever it is at ``start`` (scene seconds) to the signed level
    ``value`` over ``seconds`` (0: at once)."""

    start: float
    seconds: float
    value: float

    @property
    def end(self) -> float:
        """When it is over."""
        return self.start + max(self.seconds, 0.0)


def _mix(a: float, b: float, share: float) -> float:
    return a * (1.0 - share) + b * share


@dataclass
class Wind:
    """A stage's wind: the signed level ``base`` from the start, then the :class:`WindChange`\\s
    the ``wind`` action schedules (fades like the light's), with gusts from ``seed``."""

    base: float = 0.0
    seed: int = 1
    changes: list[WindChange] = field(default_factory=list)
    _blown: list[float] = field(default_factory=lambda: [0.0], repr=False)

    def change(self, value: float, start: float, seconds: float) -> None:
        """Fade to the signed level ``value`` from scene time ``start`` over ``seconds``."""
        self.changes.append(WindChange(float(start), max(float(seconds), 0.0), float(value)))
        self._blown = [0.0]

    def level(self, now: float) -> float:
        """The signed level at scene time ``now`` (eased fades, :func:`~vidgen.cartoon.lighting.fade_at`)."""
        return fade_at(self.base, self.changes, now, _mix) if self.changes else self.base

    def force(self, now: float, delay: float = 0.0) -> float:
        """The signed force at scene time ``now`` where gusts arrive ``delay`` seconds late: the
        level times :data:`STEADY_SHARE` plus the rest times :func:`gust`."""
        level = self.level(now)
        if level == 0.0:
            return 0.0
        return level * (STEADY_SHARE + (1.0 - STEADY_SHARE) * gust(now - delay, self.seed))

    def delay(self, x_share: float, now: float) -> float:
        """Seconds a gust takes to reach ``x_share`` (0 left edge .. 1 right edge of the stage)
        from the side the wind blows from at ``now``."""
        x = min(max(float(x_share), 0.0), 1.0)
        return GUST_CROSSING_SECONDS * (x if self.level(now) >= 0.0 else 1.0 - x)

    def blowing(self, start: float, end: float) -> bool:
        """Whether the wind may blow at some time from ``start`` to ``end`` (a change under way
        counts)."""
        return self.level(start) != 0.0 or self.level(end) != 0.0 or changing(self.changes, start, end)

    def calm(self) -> bool:
        """Whether it never blows (level 0 from the start and no change to anything else)."""
        return self.base == 0.0 and all(c.value == 0.0 for c in self.changes)

    def blown(self, since: float, now: float) -> float:
        """The force added up from scene time ``since`` to ``now`` (force × seconds; how far
        particles drift), from samples :data:`BLOWN_STEP` apart; cached, the same at every frame
        rate."""
        return self._blown_to(now) - self._blown_to(since)

    def _blown_to(self, now: float) -> float:
        if now <= 0.0:
            return 0.0
        u = now / BLOWN_STEP
        k = math.floor(u)
        while len(self._blown) <= k + 1:  # trapezoids from 0, one per step
            j = len(self._blown)
            step = 0.5 * (self.force((j - 1) * BLOWN_STEP) + self.force(j * BLOWN_STEP)) * BLOWN_STEP
            self._blown.append(self._blown[-1] + step)
        return self._blown[k] + (self._blown[k + 1] - self._blown[k]) * (u - k)


def felt_force(force: float) -> float:
    """The signed ``force`` as the swaying and trailing feel it: ``force × (1 + WIND_BOOST ×
    |force|)`` (:data:`WIND_BOOST`), so strong wind shows clearly; 0 stays 0."""
    return force * (1.0 + WIND_BOOST * abs(force))


def sway_degrees(kind: str, force: float, seconds: float, phase: float = 0.0) -> float:
    """How many degrees a ``kind`` prop (:data:`SWAYS`) leans to the right (negative: to the left)
    under the signed ``force`` at ``seconds``: its lean at felt force 1 times the
    :func:`felt_force`, with its own to-and-fro (:data:`SWAY_WOBBLE`) at its frequency, shifted
    by ``phase``. 0 without force."""
    sway = SWAYS[kind]
    return sway.degrees * felt_force(force) * (1.0 + SWAY_WOBBLE * math.sin(2.0 * math.pi * sway.hz * seconds + phase))


def trail_degrees(wind: Wind, seconds: float, *, delay: float = 0.0, phase: float = 0.0) -> float:
    """How many degrees a trailing piece of weight 1 turns with the wind at ``seconds`` (positive:
    its free end towards the right of the screen): the :func:`felt_force` (gusts ``delay``
    seconds late) followed by :data:`TRAIL_SPRING`, so it lags a gust and swings past it, plus a
    small flutter, softly limited to :data:`TRAIL_LIMIT`. Exactly 0 while the wind has been calm
    for the spring's whole memory."""
    lagged = TRAIL_SPRING.follow(lambda s: felt_force(wind.force(s, delay)), seconds)
    flutter = FLUTTER_DEGREES * felt_force(wind.level(seconds)) * math.sin(2.0 * math.pi * FLUTTER_HZ * seconds + phase)
    return TRAIL_LIMIT * math.tanh((TRAIL_DEGREES * lagged + flutter) / TRAIL_LIMIT)


def trail_memory_seconds() -> float:
    """How long a trailing piece still moves after the wind drops to 0 (the spring's memory)."""
    return TRAIL_SPRING.memory_seconds


def bent_points(points: np.ndarray, degrees: float, foot_y: float, height: float, bend_from: float = 0.0) -> np.ndarray:
    """``points`` (Manim rows ``x, y, z``) of something ``height`` tall standing at ``foot_y``,
    bent so its top leans ``degrees`` to the right: each point moves sideways by the square of
    its height above ``bend_from`` of the way up (the base stays, the top moves most); a new
    array, equal to ``points`` at 0 degrees."""
    out = np.array(points, dtype=float, copy=True)
    if degrees == 0.0 or height <= 0.0 or not len(out):
        return out
    straight = min(max(bend_from, 0.0), 0.95)
    bending = (1.0 - straight) * height
    u = np.clip((out[:, 1] - foot_y) / height - straight, 0.0, None) / (1.0 - straight)
    out[:, 0] += math.tan(math.radians(degrees)) * bending * u * u
    return out


# ----- props that blow away (the ``blow_away`` action) ---------------------------------------------

#: The built-in props light enough for ``blow_away`` (an SVG prop may too: the author knows).
LIGHT_PROPS: frozenset[str] = frozenset({"napkin", "umbrella", "ball", "cup", "basket", "box", "letter", "balloons"})
#: A blown prop's speed along the stage: Manim units per second at felt force 1 (:func:`felt_force`;
#: at least :data:`BLOW_SLOWEST` of it in a light wind), plus :data:`BLOW_MIN_SECONDS` to get going;
#: at most :data:`BLOW_MAX_SECONDS` in all.
BLOW_SPEED = 3.0
BLOW_SLOWEST = 0.5
BLOW_MIN_SECONDS = 0.6
BLOW_MAX_SECONDS = 6.0
#: How far it is blown per tumble (Manim units per whole turn; at least one turn).
BLOW_TURN_UNITS = 3.0
#: How much faster than the gusts the path's own gusts come (gust seconds per share of the path).
BLOW_GUSTS = 6.0
#: Its bobbing on the way: cycles over the path, and their height as a share of the rise.
BLOW_BOBS = 3.0
BLOW_BOB_SHARE = 0.3
#: A tumble's extra wobble (degrees) on top of its whole turns.
BLOW_WOBBLE = 25.0
_PROGRESS_SAMPLES = 64


def blow_seconds(distance: float, level: float) -> float:
    """How long a prop takes to blow ``distance`` Manim units in a wind of signed ``level``."""
    speed = BLOW_SPEED * max(felt_force(abs(level)), BLOW_SLOWEST)
    return min(BLOW_MIN_SECONDS + abs(distance) / speed, BLOW_MAX_SECONDS)


def blow_turns(distance: float) -> int:
    """The whole turns a prop tumbles over ``distance`` Manim units (at least 1)."""
    return max(1, round(abs(distance) / BLOW_TURN_UNITS))


@lru_cache(maxsize=64)
def _gusty_progress_table(seed: int) -> tuple[float, ...]:
    """Cumulative gusty speed at :data:`_PROGRESS_SAMPLES` + 1 even shares, from 0 to 1."""
    speeds = [0.35 + gust(k / _PROGRESS_SAMPLES * BLOW_GUSTS, seed) for k in range(_PROGRESS_SAMPLES + 1)]
    sums = [0.0]
    for k in range(_PROGRESS_SAMPLES):
        sums.append(sums[-1] + 0.5 * (speeds[k] + speeds[k + 1]))
    return tuple(s / sums[-1] for s in sums)


def gusty_progress(share: float, seed: int = 1) -> float:
    """How far along its path (0..1) a blown prop is at ``share`` (0..1) of its time: it surges
    with each seeded gust and slows in the lulls, never going back; 0 at 0 and 1 at 1."""
    table = _gusty_progress_table(seed)
    u = min(max(float(share), 0.0), 1.0) * _PROGRESS_SAMPLES
    k = min(int(u), _PROGRESS_SAMPLES - 1)
    return table[k] + (table[k + 1] - table[k]) * (u - k)


def blown_point(share: float, start: tuple[float, float] | np.ndarray, end: tuple[float, float] | np.ndarray, *,
                rise: float, seed: int = 1) -> tuple[float, float, float]:
    """A blown prop's middle (x, y) and its turn (degrees, counterclockwise) at ``share`` (0..1)
    of its time, from ``start`` to ``end`` (screen): along by :func:`gusty_progress`, lifted in an
    arc ``rise`` units high with a few bobs (never below the straight line from start to end),
    tumbling :func:`blow_turns` whole turns the way it goes, so it ends upright. Pure: the same
    arguments give the same point."""
    x0, y0, x1, y1 = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    g = gusty_progress(share, seed)
    arc = math.sin(math.pi * g)
    phase = wind_phase(str(seed))
    bob = BLOW_BOB_SHARE * math.sin(2.0 * math.pi * BLOW_BOBS * g + phase)
    x = x0 + (x1 - x0) * g
    y = y0 + (y1 - y0) * g + rise * arc * (1.0 + bob)
    towards = 1.0 if x1 >= x0 else -1.0
    turn = -360.0 * blow_turns(x1 - x0) * g * towards + BLOW_WOBBLE * math.sin(2.0 * math.pi * 1.5 * g + phase) * arc
    return x, y, turn
