"""Foley: the sounds tied to the characters' actions on a ``stage`` (DESIGN.md §69.19), worked
out without manim. :func:`foley_cues` turns one action *as it played* (its scene start time and
the seconds it took, after any shortening to fit its beat; :class:`PlayedAction`) into sound
cues of the built-in sound library (:mod:`vidgen.sfx`): footsteps on each footfall of a walk
(``walk_to``, ``run_to``, ``enter``, ``exit``), a whoosh as a character enters and a swoosh as it leaves, a
boing as a jump takes off, a thud where a thrown prop lands (``throw``), a pop on a surprised
face (``emote`` / ``react``), a short sound as most effect symbols pop up (``effect``,
:data:`EFFECT_SOUNDS`), and a bicycle's bell, an engine, a balloon's burner or a toy rocket's
launch as a vehicle sets off, its brakes as it stops, and a soft thud where a balloon or a rocket
lands (``ride_to``, :data:`RIDE_SOUNDS`); a door's creak as it opens or closes (``open`` /
``close``, an ``enter`` / ``exit`` through a closed door) and its thud as it shuts, a splash as a
boat sets off and where a watering can's water lands (``pour``), and a splash under each step on
wet ground (:func:`wet_steps`) (DESIGN.md §69.62). On a platform level (DESIGN.md §86.9) a jump
also lands with a soft thud and step, a walk or a jump plays a coin's or a star's sound at each one
it picks up (:func:`pickup_cues`), a locked door opened with its key clicks open before it creaks,
and a blocker stepping aside shuffles off.

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
from vidgen.cartoon.holding import RESHAPE_SHARE
from vidgen.cartoon.motion import Phases
from vidgen.cartoon.small_props import pour_flow
from vidgen.cartoon.vehicles import ROCKET_ASCENT_SHARE

#: Level (dB) of each sound tied to an action, under the library's level (about 7 dB under
#: narration at 0): footsteps are the quietest, as they repeat.
FOOTSTEP_GAIN = -5.0
WHOOSH_GAIN = -6.0
BOING_GAIN = -3.0
POP_GAIN = -3.0
LANDING_GAIN = -4.0
#: The expression that gets a pop when an ``emote`` or ``react`` puts it on a face.
POP_EXPRESSION = "surprised"
#: Footsteps alternate between two feet: ``(pitch semitones, intensity)`` of each.
FEET: tuple[tuple[float, float], tuple[float, float]] = ((0.0, 0.5), (-1.5, 0.4))
#: The step that brings the feet together when a walk stops is softer.
LAST_STEP_INTENSITY = 0.3
#: A stop closer than this (in steps) after the last footfall adds no step of its own.
LAST_STEP_MIN = 0.25
#: The actions that walk (footsteps).
WALKING_ACTIONS: frozenset[str] = frozenset({"walk_to", "run_to", "enter", "exit"})
#: A ride's sounds (DESIGN.md §69.52), per vehicle: the sound as it sets off (``bell`` or
#: ``engine``), its pitch (semitones) and gain (dB); then its brakes as it stops: pitch and gain.
#: A boat's outboard motor is a small engine, high; a balloon roars its burner, a toy rocket fizzes
#: off (DESIGN.md §69.53).
RIDE_SOUNDS: dict[str, tuple[str, float, float]] = {
    "bicycle": ("bell", 0.0, -6.0), "car": ("engine", 0.0, -5.0), "bus": ("engine", -5.0, -4.0),
    "boat": ("engine", 6.0, -8.0), "hot_air_balloon": ("burner", 0.0, -7.0), "toy_rocket": ("launch", 0.0, -5.0),
}
#: Brakes as it stops (pitch, gain); a vehicle not listed stops without them.
BRAKES: dict[str, tuple[float, float]] = {"bicycle": (4.0, -12.0), "car": (0.0, -8.0), "bus": (-3.0, -7.0)}
#: A landing balloon's basket and a toy rocket touching down: a soft thud (pitch, gain); the
#: rocket's parachute opening: a pop (pitch, gain).
TOUCHDOWN: dict[str, tuple[float, float]] = {"hot_air_balloon": (-2.0, -10.0), "toy_rocket": (6.0, -12.0)}
CHUTE_POP = (-3.0, -8.0)
#: An engine sounds for this share of the ride, at least / at most these seconds.
ENGINE_SHARE = 0.8
ENGINE_MIN_SECONDS = 0.8
ENGINE_MAX_SECONDS = 6.0
#: The sound of each effect symbol as it pops up (DESIGN.md §69.40): built-in sound, gain (dB)
#: and its params; sleep, stars and a tear are silent. Idea's short ding is the chime cut short.
EFFECT_SOUNDS: dict[str, tuple[str, float, dict[str, float]]] = {
    "sweat": ("pop", -8.0, {"pitch": -5.0, "intensity": 0.3}),
    "anger": ("thud", -6.0, {"duration": 0.3}),
    "idea": ("chime", -6.0, {"duration": 0.5, "pitch": 3.0}),
    "question": ("pop", -5.0, {"pitch": -4.0}),
    "exclaim": ("pop", -4.0, {"pitch": 5.0}),
    "hearts": ("pop", -6.0, {"pitch": 2.0, "intensity": 0.4}),
    "sparkle": ("chime", -9.0, {"duration": 0.4, "pitch": 12.0}),
}
#: A door (DESIGN.md §69.62): ``(gain dB, params)`` of its creak as it opens, of the shorter,
#: higher creak as it closes, and of the thud as it shuts (when its shape switches).
DOOR_OPEN_CREAK: tuple[float, dict[str, float]] = (-8.0, {"duration": 0.9})
DOOR_CLOSE_CREAK: tuple[float, dict[str, float]] = (-10.0, {"duration": 0.5, "pitch": 2.0})
DOOR_SHUT: tuple[float, dict[str, float]] = (-6.0, {"duration": 0.3, "pitch": 5.0})
#: A boat setting off: a soft, low splash (gain dB, params).
BOAT_SPLASH: tuple[float, dict[str, float]] = (-12.0, {"duration": 0.9, "pitch": -3.0, "intensity": 0.3})
#: A watering can's water landing: a long, soft, high splash of droplets (gain dB, pitch,
#: intensity) while the water runs, from :data:`POUR_FALL_SECONDS` after it leaves the spout.
POUR_SPLASH: tuple[float, float, float] = (-10.0, 7.0, 0.15)
POUR_FALL_SECONDS = 0.25
#: A step on wet ground (puddles): a tiny splash under the footstep (gain dB, params).
WET_STEP: tuple[float, dict[str, float]] = (-14.0, {"duration": 0.25, "pitch": 4.0, "intensity": 0.2})
#: A jump on a platform level landing (DESIGN.md §86.9): a short, soft, higher thud and a footstep
#: (gain dB, params); both louder (``intensity``) after a longer drop, from
#: :data:`LANDING_INTENSITY` by :data:`LANDING_INTENSITY_PER_HEIGHT` per character height fallen,
#: at most :data:`LANDING_INTENSITY_MAX`.
LEVEL_LANDING_THUD: tuple[float, dict[str, float]] = (-8.0, {"duration": 0.3, "pitch": 4.0})
LEVEL_LANDING_STEP: tuple[float, dict[str, float]] = (-5.0, {"pitch": -2.0})
LANDING_INTENSITY = 0.35
LANDING_INTENSITY_PER_HEIGHT = 0.1
LANDING_INTENSITY_MAX = 0.7
#: The sound of each kind of thing a level move picks up, and its gain (dB); each further one of a
#: kind in the same move is :data:`PICKUP_PITCH_STEP` semitones higher, up to
#: :data:`PICKUP_PITCH_MAX`.
PICKUP_SOUNDS: dict[str, tuple[str, float]] = {"coin": ("coin", -4.0), "star": ("twinkle", -4.0)}
PICKUP_PITCH_STEP = 1.0
PICKUP_PITCH_MAX = 5.0
#: A locked door opened with its key: the key's ``unlock`` (gain dB), then the creak this many
#: seconds later.
UNLOCK_GAIN = -6.0
UNLOCK_SECONDS = 0.3
#: A blocker stepping aside (``step_aside``): its footsteps (gain dB, pitch: a heavier, slower
#: tread) and a soft low swoosh as it sets off (gain dB, params).
ASIDE_STEP: tuple[float, float] = (-8.0, -3.0)
ASIDE_SWOOSH: tuple[float, dict[str, float]] = (-12.0, {"duration": 0.6, "pitch": -7.0, "intensity": 0.3})


@dataclass(frozen=True)
class PlayedAction:
    """One character's action as it played: its type, the scene time it started (``start``) and
    the seconds it took (``seconds``); ``expression``: the expression an ``emote`` / ``react``
    put on; ``heights``: how far a walk went, in the character's heights; ``phases``: the wind-up
    and settle shares of a walk or a jump (``cartoon_motion``); the others below. Foley
    (:func:`foley_cues`) and motion effects
    (:func:`~vidgen.cartoon.motion_effects.motion_effect_cues`) read it."""

    action: str
    start: float
    seconds: float
    expression: str | None = None
    heights: float = 0.0
    phases: Phases = field(default_factory=Phases)
    lands: float | None = None
    """The share of its time at which a prop it moved lands on the ground (a ``throw``), or at
    which a jump on a platform level touches down."""
    effect: str | None = None
    """The symbol an ``effect`` put up (``None``: none, or its ``sound: false``)."""
    step_length: float = STEP_LENGTH
    """A walk's step length in the character's heights (longer for a run)."""
    lift: float = 0.0
    """How high a jump went, in the character's heights."""
    gesture: str | None = None
    """The gesture a ``gesture`` made; ``big``: it was marked ``big: true``."""
    big: bool = False
    flight: tuple[float, float] | None = None
    """The shares of its time between which a prop it moved flew (a ``throw``, ``blow_away``)."""
    vehicle: str | None = None
    """The kind of the vehicle a ``ride_to`` moved (DESIGN.md §69.52)."""
    rolls: bool = False
    """A walk on wheels (a robot's, DESIGN.md §69.58): no footsteps."""
    prop: str | None = None
    """The kind of the prop an ``open`` / ``close`` reshaped (a ``door`` creaks, §69.62)."""
    through_door: bool = False
    """An ``enter`` / ``exit`` through a room's door (no whoosh or swoosh: it fades in the doorway)."""
    opens_door: bool = False
    """... and it opened that door, closed until then (a creak)."""
    pours: bool = False
    """The water of a ``pour`` (it lands on the ground: a splash)."""
    pickups: tuple[tuple[float, str], ...] = ()
    """The coins and stars a move on a platform level picks up, in order: ``(share, kind)``, the
    share of the walk's distance or of the jump's flight at which it gets there (DESIGN.md §86.8)."""
    unlocks: bool = False
    """An ``open`` of a locked door with its key on a platform level (the key clicks first)."""


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


def footfall_shares(heights: float, phases: Phases = Phases(), step_length: float = STEP_LENGTH) -> list[tuple[float, bool]]:
    """When a walk of ``heights`` character heights (steps ``step_length`` heights long) puts a
    foot down, as shares (0..1) of the whole animation with its wind-up and settle ``phases``:
    ``(share, last)`` per footfall, ``last`` for the step that brings the feet together at the
    stop."""
    steps = heights / step_length
    if steps <= 0:
        return []
    move = 1.0 - phases.before - phases.after
    falls = [k + 0.5 for k in range(math.floor(steps - 0.5) + 1)] if steps >= 0.5 else []
    shares = [(phases.before + move * _walk_time_share(fall / steps), False) for fall in falls]
    if not falls or steps - falls[-1] >= LAST_STEP_MIN:
        shares.append((phases.before + move, True))
    return shares


def ride_cues(played: PlayedAction) -> list[FoleyCue]:
    """The sounds of a ``ride_to`` (DESIGN.md §69.52, §69.53): as it sets off a bicycle's bell, a
    balloon's burner or a toy rocket's launch, or an engine (a car's, a bus's, a boat's motor) for
    most of the ride (at least :data:`ENGINE_MIN_SECONDS`), a boat with a splash (§69.62); its brakes ending as it stops
    (:data:`BRAKES`); a rocket's parachute popping open at the top of a landing flight; a soft thud
    as a balloon or a rocket touches down (``played.lands``: it lands)."""
    start, seconds = played.start, played.seconds
    vehicle = played.vehicle or ""
    off, pitch, gain = RIDE_SOUNDS[vehicle]
    if off == "engine":
        length = min(max(ENGINE_SHARE * seconds, ENGINE_MIN_SECONDS), ENGINE_MAX_SECONDS)
        cues = [FoleyCue(start, "engine", gain, {"duration": round(length, 3), "pitch": pitch})]
    else:
        cues = [FoleyCue(start, off, gain, {"pitch": pitch})]
    if vehicle == "boat":
        cues.append(FoleyCue(start, "splash", BOAT_SPLASH[0], BOAT_SPLASH[1]))
    if vehicle in BRAKES:
        brakes_pitch, brakes_gain = BRAKES[vehicle]
        cues.append(FoleyCue(start + seconds, "brakes", brakes_gain, {"pitch": brakes_pitch}, align="end"))
    if played.lands is not None and vehicle in TOUCHDOWN:
        if vehicle == "toy_rocket":
            cues.append(FoleyCue(start + ROCKET_ASCENT_SHARE * seconds, "pop", CHUTE_POP[1], {"pitch": CHUTE_POP[0]}))
        thud_pitch, thud_gain = TOUCHDOWN[vehicle]
        cues.append(FoleyCue(start + played.lands * seconds, "thud", thud_gain, {"pitch": thud_pitch}))
    return cues


def door_cues(played: PlayedAction) -> list[FoleyCue]:
    """A door's ``open`` (its creak from the start; after the key's ``unlock`` when it
    ``unlocks``) or ``close`` (a shorter, higher creak, then a thud when it shuts, at
    :data:`~vidgen.cartoon.holding.RESHAPE_SHARE` of the action)."""
    if played.action == "open":
        if played.unlocks:
            creak = played.start + min(UNLOCK_SECONDS, RESHAPE_SHARE * played.seconds)
            return [FoleyCue(played.start, "unlock", UNLOCK_GAIN), FoleyCue(creak, "creak", DOOR_OPEN_CREAK[0], DOOR_OPEN_CREAK[1])]
        return [FoleyCue(played.start, "creak", DOOR_OPEN_CREAK[0], DOOR_OPEN_CREAK[1])]
    return [
        FoleyCue(played.start, "creak", DOOR_CLOSE_CREAK[0], DOOR_CLOSE_CREAK[1]),
        FoleyCue(played.start + RESHAPE_SHARE * played.seconds, "thud", DOOR_SHUT[0], DOOR_SHUT[1]),
    ]


def pickup_cues(played: PlayedAction) -> list[FoleyCue]:
    """A ``coin`` or a ``twinkle`` (:data:`PICKUP_SOUNDS`) on the frame a level move gets to each
    coin or star it picks up (``played.pickups``): a share of a walk's distance is turned into its
    time with the walk's easing and wind-up (:func:`footfall_shares`' mapping), a share of a jump's
    flight with its crouch; each further one of a kind a little higher."""
    move = 1.0 - played.phases.before - played.phases.after
    walks = played.action != "jump"
    cues, counts = [], dict.fromkeys(PICKUP_SOUNDS, 0)
    for share, kind in played.pickups:
        if kind not in PICKUP_SOUNDS:
            continue
        sound, gain = PICKUP_SOUNDS[kind]
        pitch = min(PICKUP_PITCH_STEP * counts[kind], PICKUP_PITCH_MAX)
        counts[kind] += 1
        when = played.phases.before + move * (_walk_time_share(share) if walks else min(max(share, 0.0), 1.0))
        cues.append(FoleyCue(played.start + when * played.seconds, sound, gain, {"pitch": pitch} if pitch else {}))
    return cues


def landing_cues(played: PlayedAction) -> list[FoleyCue]:
    """A jump on a platform level touching down (``played.lands``): a soft thud and a footstep,
    louder after a longer drop (``played.lift``)."""
    if played.lands is None:
        return []
    time = played.start + played.lands * played.seconds
    intensity = round(min(LANDING_INTENSITY + LANDING_INTENSITY_PER_HEIGHT * max(played.lift, 0.0), LANDING_INTENSITY_MAX), 3)
    return [
        FoleyCue(time, "thud", LEVEL_LANDING_THUD[0], {**LEVEL_LANDING_THUD[1], "intensity": intensity}),
        FoleyCue(time, "footstep", LEVEL_LANDING_STEP[0], {**LEVEL_LANDING_STEP[1], "intensity": intensity}),
    ]


def wet_steps(cues: list[FoleyCue], wet_from: float | None) -> list[FoleyCue]:
    """``cues`` with a tiny splash (:data:`WET_STEP`) under each footstep from scene time
    ``wet_from`` on (the ground is wet: puddles lie there; ``None``: dry)."""
    if wet_from is None:
        return cues
    splashes = [FoleyCue(cue.time, "splash", WET_STEP[0], WET_STEP[1]) for cue in cues if cue.sound == "footstep" and cue.time >= wet_from]
    return sorted([*cues, *splashes], key=lambda cue: cue.time)


def foley_cues(played: PlayedAction) -> list[FoleyCue]:
    """The sounds of one action as it played (scene times from ``played.start``, scaled by the
    seconds it took): none for actions without foley."""
    start, seconds = played.start, played.seconds
    cues: list[FoleyCue] = []
    if played.action == "step_aside":
        cues.append(FoleyCue(start, "swoosh", ASIDE_SWOOSH[0], ASIDE_SWOOSH[1]))
        gain, pitch = ASIDE_STEP
        footfalls = [] if played.rolls else footfall_shares(played.heights, played.phases, played.step_length)
        for k, (share, last) in enumerate(footfalls):
            foot_pitch, intensity = FEET[k % 2]
            cues.append(FoleyCue(start + share * seconds, "footstep", gain, {"pitch": pitch + foot_pitch, "intensity": LAST_STEP_INTENSITY if last else intensity}))
    elif played.action in WALKING_ACTIONS:
        if played.opens_door:
            cues.append(FoleyCue(start, "creak", DOOR_OPEN_CREAK[0], DOOR_OPEN_CREAK[1]))
        if played.action == "enter" and not played.through_door:
            cues.append(FoleyCue(start, "whoosh", WHOOSH_GAIN))
        footfalls = [] if played.rolls else footfall_shares(played.heights, played.phases, played.step_length)
        for k, (share, last) in enumerate(footfalls):
            pitch, intensity = FEET[k % 2]
            cues.append(FoleyCue(start + share * seconds, "footstep", FOOTSTEP_GAIN, {"pitch": pitch, "intensity": LAST_STEP_INTENSITY if last else intensity}))
        if played.action == "exit" and not played.through_door:
            moved = start + (1.0 - played.phases.after) * seconds
            cues.append(FoleyCue(moved, "swoosh", WHOOSH_GAIN, align="end"))
    elif played.action in ("open", "close") and played.prop == "door":
        cues += door_cues(played)
    elif played.pours:
        flow_start, flow_end = pour_flow(seconds)
        gain, pitch, intensity = POUR_SPLASH
        length = min(max(flow_end - flow_start, 0.2), 3.0)
        cues.append(FoleyCue(start + flow_start + POUR_FALL_SECONDS, "splash", gain, {"duration": round(length, 3), "pitch": pitch, "intensity": intensity}))
    elif played.action == "jump":
        cues.append(FoleyCue(start + played.phases.before * seconds, "boing", BOING_GAIN))
        cues += landing_cues(played)
    elif played.action == "ride_to" and played.vehicle in RIDE_SOUNDS:
        cues += ride_cues(played)
    elif played.lands is not None:
        cues.append(FoleyCue(start + played.lands * seconds, "thud", LANDING_GAIN))
    elif played.action == "effect" and played.effect in EFFECT_SOUNDS:
        sound, gain, params = EFFECT_SOUNDS[played.effect]
        cues.append(FoleyCue(start, sound, gain, params))
    elif played.action in ("emote", "react") and played.expression == POP_EXPRESSION:
        cues.append(FoleyCue(start, "pop", POP_GAIN))
    cues += pickup_cues(played)
    return sorted(cues, key=lambda cue: cue.time)
