"""Motion effects (DESIGN.md §69.41), worked out without manim: when they fire and how they look.

The motion code adds them on its own while ``cartoon_motion`` is on (``lively``; ``calm`` draws
them smaller) and ``motion_effects`` is not false: dust puffs where a fast walk or a run sets off
and stops and where a jump lands, speed lines behind a fast walk or run and behind a thrown or
blown prop, impact stars on a hard landing, and a whoosh arc trailing the hand of a gesture
marked ``big: true``. :func:`motion_effect_cues` turns one action *as it played* (the
:class:`~vidgen.cartoon.foley.PlayedAction` foley reads) into :class:`MotionEffectCue` s; the
shapes are pure functions of the seconds since a cue started and a seed (:func:`dust_puffs`,
:func:`speed_lines`, :func:`impact_stars`, :func:`arc_band`).

Lengths are in the mover's heights (a character's height, a prop's size); ``x`` runs the way the
mover goes (forward), ``y`` up from the ground; angles in degrees counterclockwise.
"""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass

from vidgen.cartoon.acting import GESTURE_EASE, WALK_EASE
from vidgen.cartoon.effects import Point, _counterclockwise
from vidgen.cartoon.foley import WALKING_ACTIONS, PlayedAction
from vidgen.cartoon.motion import ANTICIPATION_SHARE, SETTLE_SHARE, smoothstep

#: The motion effects, in the order the docs list them.
MOTION_EFFECT_KINDS: tuple[str, ...] = ("dust", "speed_lines", "impact", "whoosh")
#: A walk is fast (dust where it sets off and stops, speed lines) from this top speed, in the
#: character's heights per second (a default walk goes about 0.7, a default run about 1.7).
FAST_SPEED = 1.15
#: Speed lines show while a fast walk goes at least this share of its top speed.
SPEED_SHOWN = 0.7
#: A jump this high or higher (character heights) lands hard: impact stars.
HARD_LANDING = 0.7
#: How long a dust cloud and an impact burst last (seconds).
DUST_SECONDS = 0.55
IMPACT_SECONDS = 0.6
#: Seconds speed lines and a whoosh arc take to fade in and out.
FADE_SECONDS = 0.1
#: How far back a whoosh arc trails the hand (seconds of its path), and how long it stays
#: after the hand stops.
WHOOSH_TRAIL_SECONDS = 0.15
#: The gestures with a whoosh when ``big``, and the arms whose hands it trails (``None``: the
#: gesture's own arm, the near one).
WHOOSH_ARMS: dict[str, tuple[str | None, ...]] = {"point": (None,), "wave": (None,), "shrug": ("arm_left", "arm_right")}
#: How many puffs a dust cloud has, stars an impact, lines a speed-lines cue.
DUST_PUFFS = 5
IMPACT_STARS = 4
SPEED_LINES = 3


@dataclass(frozen=True)
class MotionEffectCue:
    """One effect to draw: its ``kind`` (:data:`MOTION_EFFECT_KINDS`), the scene ``time`` (s) it
    starts and the ``seconds`` it lasts; a dust cloud blows ``toward`` the ``back``, the
    ``front`` or ``both`` ways (of the way the mover goes); a whoosh trails ``arm``'s hand
    (``None``: the gesture's own arm)."""

    kind: str
    time: float
    seconds: float
    toward: str = "both"
    arm: str | None = None


def effect_scale(strength: float) -> float:
    """How big the effects are drawn for a ``cartoon_motion`` strength (lively 1, calm 0.76)."""
    return 0.6 + 0.4 * strength


def walk_top_speed(heights: float, move_seconds: float) -> float:
    """The top speed (heights per second) of a walk of ``heights`` whose feet move for
    ``move_seconds`` (it speeds up and slows down over :data:`~vidgen.cartoon.acting.WALK_EASE`
    of that time at each end)."""
    return 0.0 if move_seconds <= 0 else heights / (move_seconds * (1.0 - WALK_EASE))


def motion_effect_cues(played: PlayedAction, strength: float) -> list[MotionEffectCue]:
    """The motion effects of one action as it played (scene times from ``played.start``, scaled
    by the seconds it took), for a mover whose ``cartoon_motion`` has ``strength``: none at 0.

    - a walk (``walk_to``, ``run_to``, ``enter``, ``exit``) at :data:`FAST_SPEED` or faster:
      dust blowing back where its feet set off (not for an ``enter``: off stage), dust blowing
      forward where they stop (not for an ``exit``), speed lines while it goes at least
      :data:`SPEED_SHOWN` of its top speed;
    - a jump: dust both ways where it lands, impact stars too from :data:`HARD_LANDING` up;
    - a prop flying (``throw``, ``blow_away``): speed lines from take-off to landing;
    - a ``big`` gesture of :data:`WHOOSH_ARMS`: a whoosh arc while the arm sweeps in, and
      :data:`WHOOSH_TRAIL_SECONDS` after."""
    if strength <= 0:
        return []
    start, seconds = played.start, played.seconds
    cues: list[MotionEffectCue] = []
    if played.action in WALKING_ACTIONS:
        before, after = played.phases.before, played.phases.after
        move = 1.0 - before - after
        if walk_top_speed(played.heights, move * seconds) < FAST_SPEED:
            return []
        if played.action != "enter":
            cues.append(MotionEffectCue("dust", start + before * seconds, DUST_SECONDS, "back"))
        fast = SPEED_SHOWN * WALK_EASE   # the share of the move at which it reaches SPEED_SHOWN
        cues.append(MotionEffectCue("speed_lines", start + (before + fast * move) * seconds, (1.0 - 2.0 * fast) * move * seconds))
        if played.action != "exit":
            cues.append(MotionEffectCue("dust", start + (before + move) * seconds, DUST_SECONDS, "front"))
    elif played.action == "jump":
        land = start + (1.0 - played.phases.after) * seconds
        cues.append(MotionEffectCue("dust", land, DUST_SECONDS, "both"))
        if played.lift >= HARD_LANDING:
            cues.append(MotionEffectCue("impact", land, IMPACT_SECONDS))
    elif played.flight is not None:
        leave, arrive = played.flight
        if arrive > leave:
            cues.append(MotionEffectCue("speed_lines", start + leave * seconds, (arrive - leave) * seconds))
    elif played.gesture in WHOOSH_ARMS and played.big:
        sweep_from = GESTURE_EASE * ANTICIPATION_SHARE * strength
        sweep_to = GESTURE_EASE * (1.0 - SETTLE_SHARE * strength)
        for arm in WHOOSH_ARMS[played.gesture]:
            cues.append(MotionEffectCue("whoosh", start + sweep_from * seconds, (sweep_to - sweep_from) * seconds + WHOOSH_TRAIL_SECONDS, arm=arm))
    return sorted(cues, key=lambda cue: cue.time)


def motion_seed(*parts: object) -> int:
    """A seed from ``parts`` (scene, mover, time...): the same effect looks the same in every
    render."""
    return zlib.crc32(":".join(str(p) for p in parts).encode("utf-8"))


def fade(age: float, seconds: float, edge: float = FADE_SECONDS) -> float:
    """0 → 1 over the first ``edge`` seconds of ``seconds``, 1 → 0 over the last (0 outside)."""
    if age <= 0 or age >= seconds:
        return 0.0
    edge = min(edge, seconds / 2)
    return smoothstep(min(age, seconds - age) / edge) if edge > 0 else 1.0


# ----- shapes ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Puff:
    """One round puff of a dust cloud: its middle ``x``, ``y`` and ``radius`` (heights) and its
    ``opacity`` (0..1)."""

    x: float
    y: float
    radius: float
    opacity: float


def dust_puffs(age: float, seed: int, toward: str = "both", count: int = DUST_PUFFS) -> list[Puff]:
    """The puffs of a dust cloud ``age`` seconds after it rose from the ground at ``x`` 0: each
    starts small near the feet a little after the others, drifts ``toward`` the back (``x``
    falling), the front or both ways (alternately) and a little up, grows and fades out by
    :data:`DUST_SECONDS`."""
    rng = random.Random(seed)
    puffs: list[Puff] = []
    for k in range(count):
        side = {"back": -1.0, "front": 1.0}.get(toward, -1.0 if k % 2 else 1.0)
        drift, rise = rng.uniform(0.2, 0.45), rng.uniform(0.03, 0.12)
        radius, delay, near = rng.uniform(0.06, 0.1), rng.uniform(0.0, 0.08), rng.uniform(0.02, 0.1)
        u = (age - delay) / (DUST_SECONDS - delay)
        if u <= 0.0 or u >= 1.0:
            continue
        out = 1.0 - (1.0 - u) ** 2
        r = radius * (0.45 + 0.75 * out)
        puffs.append(Puff(side * (near + drift * out), 0.8 * r + rise * out, r, 1.0 - smoothstep((u - 0.35) / 0.65)))
    return puffs


@dataclass(frozen=True)
class SpeedLine:
    """One speed line behind a mover: ``across`` its way (mover sizes from its middle, up when it
    goes right), starting ``behind`` its back edge and ``length`` long (mover sizes), at
    ``opacity``."""

    across: float
    behind: float
    length: float
    opacity: float


def speed_lines(age: float, seconds: float, seed: int, count: int = SPEED_LINES) -> list[SpeedLine]:
    """The speed lines ``age`` seconds into a cue lasting ``seconds``: :data:`SPEED_LINES` lanes
    across the mover, each line flickering in length, all fading in and out
    (:func:`fade`)."""
    weight = fade(age, seconds)
    if weight <= 0:
        return []
    rng = random.Random(seed)
    lines: list[SpeedLine] = []
    for k in range(count):
        lane = (k - (count - 1) / 2) * 0.2 + rng.uniform(-0.04, 0.04)
        length, gap, phase = rng.uniform(0.35, 0.55), rng.uniform(0.04, 0.12), rng.random()
        flicker = 0.75 + 0.25 * math.sin(2 * math.pi * (3.0 * age + phase))
        lines.append(SpeedLine(lane, gap, length * flicker * weight, weight))
    return lines


@dataclass(frozen=True)
class ImpactStar:
    """One star of an impact burst: its middle ``x``, ``y`` and outer radius ``size`` (heights)
    and its turn ``angle`` (degrees)."""

    x: float
    y: float
    size: float
    angle: float


def impact_stars(age: float, seed: int, count: int = IMPACT_STARS) -> list[ImpactStar]:
    """The stars of an impact ``age`` seconds after a hard landing at ``x`` 0: they burst out of
    the ground in a fan (25° to 155°), pop in, spin and shrink away by :data:`IMPACT_SECONDS`."""
    u = age / IMPACT_SECONDS
    if u <= 0.0 or u >= 1.0:
        return []
    rng = random.Random(seed)
    stars: list[ImpactStar] = []
    out = 1.0 - (1.0 - u) ** 2
    for k in range(count):
        angle = math.radians(25.0 + 130.0 * (k + 0.5) / count + rng.uniform(-10.0, 10.0))
        reach, size, spin = rng.uniform(0.22, 0.38), rng.uniform(0.07, 0.1), rng.choice((-1.0, 1.0))
        scale = smoothstep(u / 0.15) * (1.0 - smoothstep((u - 0.6) / 0.4))
        stars.append(ImpactStar(math.cos(angle) * reach * out, 0.04 + math.sin(angle) * reach * out, size * scale, spin * 270.0 * u))
    return stars


def arc_band(cx: float, cy: float, radius: float, start: float, end: float, width: float, n: int = 16) -> tuple[Point, ...]:
    """The outline (counterclockwise) of a band along the circle about ``cx``, ``cy`` from angle
    ``start`` to ``end`` (degrees, either way), tapering from nothing at ``start`` to ``width`` at
    ``end``: a whoosh arc, its thick end at the hand."""
    outer, inner = [], []
    for k in range(n + 1):
        share = k / n
        a = math.radians(start + (end - start) * share)
        half = width * share / 2
        outer.append((cx + (radius + half) * math.cos(a), cy + (radius + half) * math.sin(a)))
        inner.append((cx + (radius - half) * math.cos(a), cy + (radius - half) * math.sin(a)))
    return _counterclockwise([*outer, *reversed(inner[1:])])


__all__ = [
    "DUST_SECONDS",
    "FAST_SPEED",
    "HARD_LANDING",
    "IMPACT_SECONDS",
    "MOTION_EFFECT_KINDS",
    "WHOOSH_ARMS",
    "ImpactStar",
    "MotionEffectCue",
    "Puff",
    "SpeedLine",
    "arc_band",
    "dust_puffs",
    "effect_scale",
    "fade",
    "impact_stars",
    "motion_effect_cues",
    "motion_seed",
    "speed_lines",
    "walk_top_speed",
]
