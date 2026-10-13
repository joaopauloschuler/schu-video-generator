"""The animation principles characters move with (DESIGN.md §69.13), worked out without manim:
anticipation before a move, squash and stretch on jumps and landings, overshoot and settle on
stops, and follow-through of the parts that hang on the body (arms, head, accessory; a generated
character's hair and ears are drawn in its head and move with it) on a damped spring
(:mod:`vidgen.cartoon.spring`, §69.15).

Every effect is scaled by a *strength* from the ``cartoon_motion`` setting (:data:`MOTION_LEVELS`:
``lively`` 1, ``calm`` 0.4, ``none`` 0); at strength 0 each function gives the plain motion of
Steps 70 and 79 back (no offset, no extra time). The animations of
:mod:`vidgen.cartoon.transition` (``PoseChange``, ``Walk``, ``Gesture``, ``Jump``) apply them.

Times ``t``, ``u``, ``v`` are shares (0..1) of an animation or of one of its phases; angles are
in degrees counterclockwise as drawn facing right (a positive body or head angle leans back from
the way the character faces, a positive arm angle swings the hand forward); lengths and speeds
are in character heights.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from vidgen.cartoon.spring import Spring

#: Strength of the animation principles for each ``cartoon_motion`` setting.
MOTION_LEVELS: dict[str, float] = {"lively": 1.0, "calm": 0.4, "none": 0.0}
#: The setting when neither the character, the scene nor the video gives one.
DEFAULT_MOTION = "lively"


def resolve_motion(*settings: str | None) -> str:
    """The first setting given (pass the nearest first: character, scene, video), else
    :data:`DEFAULT_MOTION`."""
    return next((s for s in settings if s is not None), DEFAULT_MOTION)


def motion_strength(setting: str) -> float:
    """The strength (0..1) of a ``cartoon_motion`` setting."""
    if setting not in MOTION_LEVELS:
        raise ValueError(f"cartoon_motion must be one of {', '.join(MOTION_LEVELS)}, not {setting!r}")
    return MOTION_LEVELS[setting]


def smoothstep(x: float) -> float:
    """3x² − 2x³ on 0..1 (clamped): eases in and out, flat at both ends."""
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def _raw_wobble(v: float) -> float:
    return math.sin(math.pi * v) * math.sin(2.0 * math.pi * v) * math.exp(-3.0 * v)


_WOBBLE_PEAK = max(_raw_wobble(k / 1000) for k in range(1001))


def settle_wobble(v: float) -> float:
    """A settle after a stop at ``v`` (0..1 of the settle): past the end (peak 1), back a little
    the other way (about a third), then still; 0 and flat at both ends."""
    if v <= 0.0 or v >= 1.0:
        return 0.0
    return _raw_wobble(v) / _WOBBLE_PEAK


@dataclass(frozen=True)
class Phases:
    """An animation split in three: a wind-up (``before``), the move, a settle (``after``); the
    shares of the animation's time the first and the last take."""

    before: float = 0.0
    after: float = 0.0

    @classmethod
    def of(cls, before_seconds: float, main_seconds: float, after_seconds: float) -> Phases:
        """The shares of a wind-up, a move and a settle lasting these seconds."""
        total = before_seconds + main_seconds + after_seconds
        return cls() if total <= 0 else cls(before_seconds / total, after_seconds / total)

    def split(self, t: float) -> tuple[float, float, float]:
        """How far (0..1) into the wind-up, the move and the settle the animation is at ``t``."""
        t = min(max(t, 0.0), 1.0)
        main = 1.0 - self.before - self.after
        wind = 1.0 if self.before <= 0 else min(t / self.before, 1.0)
        move = 1.0 if main <= 0 else min(max((t - self.before) / main, 0.0), 1.0)
        settle = 0.0 if self.after <= 0 else max((t - self.before - main) / self.after, 0.0)
        return wind, move, min(settle, 1.0)


# ----- anticipation, overshoot and settle (pose changes, gestures) -------------------------------

#: Share of a pose change's (or a gesture's move in) time spent winding up (moving the other way
#: first), and how far back, as a share of the move; at strength 1.
ANTICIPATION_SHARE = 0.2
ANTICIPATION = 0.12
#: Share of the time spent settling after the move (past the end and back), and how far past.
SETTLE_SHARE = 0.25
OVERSHOOT = 0.1


def motion_ease(u: float, strength: float, base: Callable[[float], float] = smoothstep) -> float:
    """Progress (0 → 1) of a move at ``u`` (0..1) with anticipation and overshoot: it goes
    back ``ANTICIPATION × strength`` of the way first, moves with ``base`` easing, passes the end
    by up to ``OVERSHOOT × strength`` and settles (:func:`settle_wobble`). Strength 0 is ``base``."""
    if strength <= 0:
        return base(u)
    phases = Phases(ANTICIPATION_SHARE * strength, SETTLE_SHARE * strength)
    wind, move, settle = phases.split(u)
    if wind < 1.0:
        return -ANTICIPATION * strength * math.sin(math.pi * wind) ** 2
    if settle > 0.0:
        return 1.0 + OVERSHOOT * strength * settle_wobble(settle)
    return base(move)


# ----- walking: lean back before, lean on past the stop ------------------------------------------

#: Seconds a walk winds up before the feet move (the body crouches and leans back) and settles
#: after they stop (the body leans on forward and back), at strength 1; added to its run time.
WALK_WIND_UP_SECONDS = 0.25
WALK_SETTLE_SECONDS = 0.4
#: How far the body crouches (a share of its height) and leans back (degrees) when winding up,
#: and how far it leans on forward (degrees) past the stop.
WALK_CROUCH = 0.05
WALK_LEAN_DEGREES = 6.0
STOP_LEAN_DEGREES = 6.0


def walk_motion_seconds(walk_time: float, strength: float) -> float:
    """How long a walk whose feet move for ``walk_time`` seconds
    (:func:`~vidgen.cartoon.acting.walk_seconds`) lasts with its wind-up and settle (no walk: 0)."""
    return 0.0 if walk_time <= 0 else walk_time + strength * (WALK_WIND_UP_SECONDS + WALK_SETTLE_SECONDS)


def walk_phases(walk_time: float, strength: float) -> Phases:
    """The wind-up and settle shares of a walk whose feet move for ``walk_time`` seconds."""
    return Phases.of(strength * WALK_WIND_UP_SECONDS, walk_time, strength * WALK_SETTLE_SECONDS)


@dataclass(frozen=True)
class BodyAccent:
    """A change to the body for the principles: ``lean`` (degrees, positive leans back) and
    ``stretch`` (the figure's height − 1: negative squashes, positive stretches)."""

    lean: float = 0.0
    stretch: float = 0.0


def walk_accent(t: float, phases: Phases, strength: float) -> BodyAccent:
    """The body's anticipation (crouch and lean back) and overshoot (leaning on past the stop and
    settling) at ``t`` of a walk."""
    wind, _, settle = phases.split(t)
    if wind < 1.0:
        pull = strength * math.sin(math.pi * wind) ** 2
        return BodyAccent(WALK_LEAN_DEGREES * pull, -WALK_CROUCH * pull)
    if settle > 0.0:
        return BodyAccent(-STOP_LEAN_DEGREES * strength * settle_wobble(settle), 0.0)
    return BodyAccent()


# ----- jumping: crouch, stretch, squash on landing -----------------------------------------------

#: Seconds a jump crouches before take-off and squashes and settles after landing, at strength 1;
#: added to its flight (``JUMP_SECONDS`` of :mod:`vidgen.cartoon.acting` by default).
JUMP_CROUCH_SECONDS = 0.18
JUMP_LAND_SECONDS = 0.3
#: How much the figure squashes (crouch, landing) and stretches (take-off, fall), as a share of
#: its height; its width changes the other way so its area stays.
JUMP_SQUASH = 0.22
JUMP_STRETCH = 0.15


def jump_motion_seconds(flight_seconds: float, strength: float) -> float:
    """How long a jump whose flight lasts ``flight_seconds`` takes with its crouch and landing."""
    return flight_seconds + strength * (JUMP_CROUCH_SECONDS + JUMP_LAND_SECONDS)


def jump_phases(flight_seconds: float, strength: float) -> Phases:
    """The crouch and landing shares of a jump."""
    return Phases.of(strength * JUMP_CROUCH_SECONDS, flight_seconds, strength * JUMP_LAND_SECONDS)


def landing_bounce(v: float) -> float:
    """The squash after landing at ``v`` (0..1): full at touch-down (1), a small stretch back
    (negative), then still (0, flat)."""
    v = min(max(v, 0.0), 1.0)
    return (1.0 - v) ** 2 * math.cos(2.5 * math.pi * v)


def jump_stretch(t: float, phases: Phases, strength: float) -> float:
    """The figure's stretch at ``t`` of a jump: the crouch squashes it on the ground, the flight
    (``phases.split(t)[1]``) stretches it most when it is fastest (take-off, landing) and least
    at the top, landing squashes it and it settles."""
    wind, move, settle = phases.split(t)
    if wind < 1.0:
        return -JUMP_SQUASH * strength * math.sin(0.5 * math.pi * wind) ** 2
    if settle > 0.0:
        return -JUMP_SQUASH * strength * landing_bounce(settle)
    return JUMP_STRETCH * strength * (1.0 - 2.0 * move) ** 2


def squash_scale(stretch: float) -> tuple[float, float]:
    """The figure's (x, y) scale for ``stretch``: taller by it, narrower so its area stays."""
    tall = max(1.0 + stretch, 0.05)
    return 1.0 / tall, tall


# ----- follow-through ----------------------------------------------------------------------------

#: The spring hanging parts follow the body's speed on: it lags (about
#: 2ζ/ω = 0.08 s), passes the body's speed by about 16 % when it changes and settles in 0.6 s.
FOLLOW_SPRING_HZ = 2.0
FOLLOW_DAMPING_RATIO = 0.5
FOLLOW_SPRING = Spring.tuned(FOLLOW_SPRING_HZ, FOLLOW_DAMPING_RATIO)
#: Degrees a part turns per character height per second its speed lags the body's, and the most
#: it turns (an arm swinging inwards in a jump: :data:`FOLLOW_INWARD_LIMIT`).
FOLLOW_ARM_DEGREES = 30.0
FOLLOW_HEAD_DEGREES = 10.0
FOLLOW_ACCESSORY_DEGREES = 18.0
FOLLOW_TAIL_DEGREES = 45.0
FOLLOW_ARM_LIMIT = 25.0
FOLLOW_HEAD_LIMIT = 8.0
FOLLOW_ACCESSORY_LIMIT = 12.0
FOLLOW_TAIL_LIMIT = 30.0
FOLLOW_INWARD_LIMIT = 8.0
#: Share of an animation's end over which follow-through fades out, so it ends in its state.
FOLLOW_FADE_SHARE = 0.12
_SPEED_STEP = 1e-3


def follow_lag(signal: Callable[[float], float], seconds: float, spring: Spring = FOLLOW_SPRING) -> float:
    """``signal`` (a function of seconds from 0, as it was before 0) as a part hanging on
    ``spring`` sees it at ``seconds``: late, then past it and back (:meth:`Spring.follow`).

    This is the one place follow-through's lag is computed."""
    return spring.follow(signal, seconds)


def follow_through(position: Callable[[float], float], seconds: float, spring: Spring = FOLLOW_SPRING) -> float:
    """How far behind (negative) or ahead of the body's speed a hanging part's speed is at
    ``seconds``, the body at ``position(seconds)`` (character heights): lagging when the body
    speeds up, carrying on when it slows down or stops and swinging back once, nothing at a
    steady speed."""
    def speed(at: float) -> float:
        return (position(at + _SPEED_STEP) - position(at - _SPEED_STEP)) / (2.0 * _SPEED_STEP)

    return follow_lag(speed, seconds, spring) - speed(seconds)


def end_fade(t: float) -> float:
    """1, falling to 0 over the last :data:`FOLLOW_FADE_SHARE` of an animation (``t`` 0..1)."""
    return smoothstep((1.0 - t) / FOLLOW_FADE_SHARE)


def _limited(value: float, low: float, high: float) -> float:
    return min(max(value, -low), high)


def follow_angles(forward: float, up: float, strength: float) -> dict[str, float]:
    """Degrees each hanging part turns for follow-through ``forward`` (along the way the
    character faces) and ``up`` (:func:`follow_through`, heights per second): the arms trail
    and swing on, raised outwards while falling; the head and accessory tip back and on; an
    animal's tail (drawn behind it, DESIGN.md §69.48) swings back and down as the body sets off or
    rises, and on past it as the body stops or falls."""
    arm = _limited(FOLLOW_ARM_DEGREES * forward * strength, FOLLOW_ARM_LIMIT, FOLLOW_ARM_LIMIT)
    out = _limited(FOLLOW_ARM_DEGREES * up * strength, FOLLOW_INWARD_LIMIT, FOLLOW_ARM_LIMIT)
    head = _limited(-FOLLOW_HEAD_DEGREES * forward * strength, FOLLOW_HEAD_LIMIT, FOLLOW_HEAD_LIMIT)
    hat = _limited(-FOLLOW_ACCESSORY_DEGREES * forward * strength, FOLLOW_ACCESSORY_LIMIT, FOLLOW_ACCESSORY_LIMIT)
    tail = _limited(-FOLLOW_TAIL_DEGREES * (forward + up) * strength, FOLLOW_TAIL_LIMIT, FOLLOW_TAIL_LIMIT)
    return {"arm_left": arm + out, "arm_right": arm - out, "head": head, "accessory": hat, "tail": tail}


__all__ = [
    "DEFAULT_MOTION",
    "MOTION_LEVELS",
    "BodyAccent",
    "Phases",
    "end_fade",
    "follow_angles",
    "follow_lag",
    "follow_through",
    "jump_motion_seconds",
    "jump_phases",
    "jump_stretch",
    "landing_bounce",
    "motion_ease",
    "motion_strength",
    "resolve_motion",
    "settle_wobble",
    "smoothstep",
    "squash_scale",
    "walk_accent",
    "walk_motion_seconds",
    "walk_phases",
]
