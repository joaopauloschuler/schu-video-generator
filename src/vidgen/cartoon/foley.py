"""Foley: the sounds tied to the characters' actions on a ``stage`` (DESIGN.md §69.19), worked
out without manim. :func:`foley_cues` turns one action *as it played* (its scene start time and
the seconds it took, after any shortening to fit its beat; :class:`PlayedAction`) into sound
cues of the built-in sound library (:mod:`vidgen.sfx`): footsteps on each footfall of a walk
(``walk_to``, ``enter``, ``exit``), a whoosh as a character enters and a swoosh as it leaves, a
boing as a jump takes off and a pop on a surprised face (``emote`` / ``react``).

Footfalls follow the walk cycle of :func:`~vidgen.cartoon.acting.walk_cycle`: a foot lands each
time the legs are furthest apart (half a step, :data:`~vidgen.cartoon.acting.STEP_LENGTH`
character heights, past a whole step), and once more when the walk stops between two footfalls;
the walk's wind-up and settle (``cartoon_motion``, :class:`~vidgen.cartoon.motion.Phases`) are
standing still.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from vidgen.cartoon.acting import STEP_LENGTH, WALK_EASE
from vidgen.cartoon.motion import Phases

#: Level (dB) of each sound tied to an action, under the library's level (about 7 dB under
#: narration at 0): footsteps are the quietest, as they repeat.
FOOTSTEP_GAIN = -5.0
WHOOSH_GAIN = -6.0
BOING_GAIN = -3.0
POP_GAIN = -3.0
#: The expression that gets a pop when an ``emote`` or ``react`` puts it on a face.
POP_EXPRESSION = "surprised"
#: Footsteps alternate between two feet: ``(pitch semitones, intensity)`` of each.
FEET: tuple[tuple[float, float], tuple[float, float]] = ((0.0, 0.5), (-1.5, 0.4))
#: The step that brings the feet together when a walk stops is softer.
LAST_STEP_INTENSITY = 0.3
#: A stop closer than this (in steps) after the last footfall adds no step of its own.
LAST_STEP_MIN = 0.25
#: The actions that walk (footsteps).
WALKING_ACTIONS: frozenset[str] = frozenset({"walk_to", "enter", "exit"})


@dataclass(frozen=True)
class PlayedAction:
    """One character's action as it played: its type, the scene time it started (``start``) and
    the seconds it took (``seconds``); ``expression``: the expression an ``emote`` / ``react``
    put on; ``heights``: how far a walk went, in the character's heights; ``phases``: the wind-up
    and settle shares of a walk or a jump (``cartoon_motion``)."""

    action: str
    start: float
    seconds: float
    expression: str | None = None
    heights: float = 0.0
    phases: Phases = field(default_factory=Phases)


@dataclass(frozen=True)
class FoleyCue:
    """A sound to play: scene ``time`` (s), the built-in ``sound``, ``gain`` (dB), the sound's
    ``params`` and ``align`` (``start``: it starts at ``time``; ``end``: it ends there)."""

    time: float
    sound: str
    gain: float = 0.0
    params: Mapping[str, float] = field(default_factory=dict)
    align: str = "start"


def _walk_time_share(distance_share: float) -> float:
    """The share of a walk's time at which it has covered ``distance_share`` of its distance
    (the inverse of :func:`~vidgen.cartoon.acting.walk_progress`)."""
    p = min(max(distance_share, 0.0), 1.0)
    r, top = WALK_EASE, 1.0 / (1.0 - WALK_EASE)
    edge = 0.5 * top * r
    if p < edge:
        return math.sqrt(2.0 * p * r / top)
    if p > 1.0 - edge:
        return 1.0 - math.sqrt(2.0 * (1.0 - p) * r / top)
    return p / top + r / 2.0


def footfall_shares(heights: float, phases: Phases = Phases()) -> list[tuple[float, bool]]:
    """When a walk of ``heights`` character heights puts a foot down, as shares (0..1) of the
    whole animation with its wind-up and settle ``phases``: ``(share, last)`` per footfall,
    ``last`` for the step that brings the feet together at the stop."""
    steps = heights / STEP_LENGTH
    if steps <= 0:
        return []
    move = 1.0 - phases.before - phases.after
    falls = [k + 0.5 for k in range(math.floor(steps - 0.5) + 1)] if steps >= 0.5 else []
    shares = [(phases.before + move * _walk_time_share(fall / steps), False) for fall in falls]
    if not falls or steps - falls[-1] >= LAST_STEP_MIN:
        shares.append((phases.before + move, True))
    return shares


def foley_cues(played: PlayedAction) -> list[FoleyCue]:
    """The sounds of one action as it played (scene times from ``played.start``, scaled by the
    seconds it took): none for actions without foley."""
    start, seconds = played.start, played.seconds
    cues: list[FoleyCue] = []
    if played.action in WALKING_ACTIONS:
        if played.action == "enter":
            cues.append(FoleyCue(start, "whoosh", WHOOSH_GAIN))
        for k, (share, last) in enumerate(footfall_shares(played.heights, played.phases)):
            pitch, intensity = FEET[k % 2]
            cues.append(FoleyCue(start + share * seconds, "footstep", FOOTSTEP_GAIN, {"pitch": pitch, "intensity": LAST_STEP_INTENSITY if last else intensity}))
        if played.action == "exit":
            moved = start + (1.0 - played.phases.after) * seconds
            cues.append(FoleyCue(moved, "swoosh", WHOOSH_GAIN, align="end"))
    elif played.action == "jump":
        cues.append(FoleyCue(start + played.phases.before * seconds, "boing", BOING_GAIN))
    elif played.action in ("emote", "react") and played.expression == POP_EXPRESSION:
        cues.append(FoleyCue(start, "pop", POP_GAIN))
    return sorted(cues, key=lambda cue: cue.time)
