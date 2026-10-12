"""The geometry and timing of the acting actions, worked out without manim: where a character
looks (``look_at``, DESIGN.md §69.11), and how it walks, enters, leaves, gestures and jumps
(``walk_to``, ``enter``, ``exit``, ``gesture``, ``jump``, §69.12; ``run_to``, §69.41).

Angles are in degrees counterclockwise as drawn facing right (a character facing left is the
mirror image, so a positive angle tilts the head up towards where it looks in both facings);
shifts are in character units (1 = the character's height); distances and speeds on the stage
are in Manim units (the frame's shorter side is 8 units in every aspect).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from vidgen.cartoon.motion import motion_ease

#: Largest head tilt (degrees) when looking up or down at something.
LOOK_MAX_DEGREES = 20.0
#: How far the eyes move forward (character units) when looking at something beside the character.
LOOK_EYES_AHEAD = 0.008
#: How far the eyes move back towards the middle of the face (character units) when looking at
#: the camera (a generated face sits 0.025 forward of the head's middle).
CAMERA_EYES_BACK = 0.025
#: Something nearer than this (Manim units) in x is straight above or below: the facing stays.
SAME_X = 0.05


@dataclass(frozen=True)
class LookPose:
    """How a character looks somewhere: its ``facing``, the head's ``head_angle`` and the eyes'
    ``eyes_shift`` (x, y)."""

    facing: str
    head_angle: float
    eyes_shift: tuple[float, float]


def look_pose(dx: float, dy: float, facing: str) -> LookPose:
    """Looking at a point ``dx``, ``dy`` (Manim units) from the character's head: facing that
    way (kept when the point is within :data:`SAME_X`), the head tilted up or down towards it (at
    most :data:`LOOK_MAX_DEGREES`) and the eyes a little forward, raised or lowered with the head."""
    if abs(dx) >= SAME_X:
        facing = "right" if dx > 0 else "left"
    angle = math.degrees(math.atan2(dy, max(abs(dx), SAME_X)))
    angle = max(-LOOK_MAX_DEGREES, min(LOOK_MAX_DEGREES, angle))
    return LookPose(facing, angle, (LOOK_EYES_AHEAD, LOOK_EYES_AHEAD * angle / LOOK_MAX_DEGREES))


def camera_look(facing: str) -> LookPose:
    """Looking at the camera (the viewer): the facing kept, the head straight, the eyes moved to
    the middle of the face."""
    return LookPose(facing, 0.0, (-CAMERA_EYES_BACK, 0.0))


# ----- walking (Step 79) ------------------------------------------------------------------------

#: Walking speed (Manim units per second) when a walk gives none: about 0.7 of a stage character's
#: height (0.45 x 8 units) per second.
WALK_SPEED = 2.5
#: Share of a walk spent speeding up, and the same share slowing down at the end.
WALK_EASE = 0.15
#: Length of one step, in character heights.
STEP_LENGTH = 0.35
#: Largest swing of the legs (degrees about the hips) and of the arms (about the shoulders).
WALK_LEG_DEGREES = 10.0
WALK_ARM_DEGREES = 16.0
#: Legs drawn one each (§69.26): the largest swing of a thigh about its hip, and the largest bend
#: of the knee of the leg swinging forward (as it passes the other).
WALK_THIGH_DEGREES = 20.0
WALK_KNEE_DEGREES = 40.0
#: The elbows' bend while walking, and how much more an elbow bends as its arm swings forward.
WALK_ELBOW_DEGREES = 10.0
WALK_ELBOW_SWING = 20.0
#: How much narrower the legs get as they pass each other in mid-step (a share of their width).
WALK_LEG_SQUEEZE = 0.3
#: How far the body rises in mid-step (character units).
WALK_BOB = 0.02
#: Gap (Manim units) between a character waiting off stage and the edge it is beyond.
OFFSTAGE_GAP = 0.25
SIDES: tuple[str, ...] = ("left", "right")


def walk_seconds(distance: float, speed: float = WALK_SPEED) -> float:
    """How long a walk of ``distance`` units takes at ``speed`` units per second (the speed of its
    middle part; it speeds up and slows down over :data:`WALK_EASE` of the time at each end)."""
    if speed <= 0:
        raise ValueError(f"speed must be positive, got {speed}")
    return abs(distance) / (speed * (1.0 - WALK_EASE))


def walk_progress(t: float) -> float:
    """Share of the distance covered at ``t`` (0..1, a share of the walk's time): speeding up
    evenly over :data:`WALK_EASE`, at full speed, then slowing down evenly to a stop."""
    t = min(max(t, 0.0), 1.0)
    r, top = WALK_EASE, 1.0 / (1.0 - WALK_EASE)
    if t < r:
        return 0.5 * top * t * t / r
    if t > 1.0 - r:
        return 1.0 - 0.5 * top * (1.0 - t) ** 2 / r
    return top * (t - r / 2)


def walk_amplitude(t: float) -> float:
    """The walk's speed at ``t`` (0..1) as a share of its full speed: how far the legs, arms and
    body move then (0 at the start and the end, so the walk starts and ends in the pose)."""
    t = min(max(t, 0.0), 1.0)
    return min(1.0, t / WALK_EASE, (1.0 - t) / WALK_EASE)


@dataclass(frozen=True)
class WalkCycle:
    """The walk's change to the pose at one moment: ``legs_angle`` and ``arm_angle`` (degrees,
    added to the legs' and the near arm's angles; the far arm swings the other way),
    ``legs_width`` (the legs' x scale factor) and ``body_lift`` (character units), for legs in
    one piece. Legs drawn one each: ``thigh_angle`` (added to ``leg_left``; ``leg_right`` the
    other way) and ``knee_bends`` (left, right; degrees each knee bends, the foot back). Arms in
    two segments (or folded): ``elbow_bends`` (left, right; degrees, the hand forward)."""

    legs_angle: float
    legs_width: float
    arm_angle: float
    body_lift: float
    thigh_angle: float = 0.0
    knee_bends: tuple[float, float] = (0.0, 0.0)
    elbow_bends: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class Gait:
    """How a character moves its feet along the ground, as factors of a walk's: ``stride`` (the
    step length, :data:`STEP_LENGTH` × it), ``swing`` (legs, thighs and arms), ``knee`` and
    ``elbow`` (the bends), ``bob`` (the body's rise); ``lean``: degrees the body leans forward at
    full speed (it builds up and fades with the speed)."""

    stride: float = 1.0
    swing: float = 1.0
    knee: float = 1.0
    elbow: float = 1.0
    bob: float = 1.0
    lean: float = 0.0


#: A walk, and a run (``run_to``, DESIGN.md §69.41): longer strides, bigger swings and bends, the
#: body leaning forward.
WALKING = Gait()
RUNNING = Gait(stride=1.6, swing=1.5, knee=1.6, elbow=2.0, bob=2.0, lean=12.0)
#: Running speed (Manim units per second) when a ``run_to`` gives none: about 1.7 of a stage
#: character's heights per second.
RUN_SPEED = 6.0


def walk_cycle(steps: float, amplitude: float = 1.0, gait: Gait = WALKING) -> WalkCycle:
    """The pose change after ``steps`` steps (a step every :data:`STEP_LENGTH` × ``gait.stride``
    character heights walked, so the feet keep pace with the ground), scaled by ``amplitude``
    (0..1) and ``gait``. Legs and arms swing furthest one way at a footfall (half-way through a
    step) and the other way at the next; between footfalls, as the legs pass each other, they are
    narrowest and the body is highest. Legs drawn one each: the knee of the leg swinging forward
    bends most as it passes the other and is straight at the footfall; an elbow bends more as its
    arm swings forward."""
    swing = math.sin(math.pi * steps)
    forward = math.cos(math.pi * steps)  # > 0 while the left leg swings forward
    passing = 1.0 - swing * swing
    sway, knee, elbow = amplitude * gait.swing, amplitude * gait.knee, amplitude * gait.elbow
    return WalkCycle(
        legs_angle=WALK_LEG_DEGREES * swing * sway,
        legs_width=1.0 - WALK_LEG_SQUEEZE * passing * amplitude,
        arm_angle=WALK_ARM_DEGREES * swing * sway,
        body_lift=WALK_BOB * passing * amplitude * gait.bob,
        thigh_angle=WALK_THIGH_DEGREES * swing * sway,
        knee_bends=(WALK_KNEE_DEGREES * max(forward, 0.0) * knee, WALK_KNEE_DEGREES * max(-forward, 0.0) * knee),
        elbow_bends=(
            (WALK_ELBOW_DEGREES + WALK_ELBOW_SWING * max(swing, 0.0)) * elbow,
            (WALK_ELBOW_DEGREES + WALK_ELBOW_SWING * max(-swing, 0.0)) * elbow,
        ),
    )


# ----- entering and leaving -------------------------------------------------------------------------


def nearer_side(x: float, left: float, right: float) -> str:
    """``left`` or ``right``: the edge of ``left``..``right`` nearer ``x`` (``left`` on a tie)."""
    return "left" if x - left <= right - x else "right"


def offstage_x(side: str, left: float, right: float, half_width: float) -> float:
    """Where a character ``half_width`` units wide on each side of its feet stands just beyond the
    ``side`` edge of ``left``..``right`` (wholly outside, :data:`OFFSTAGE_GAP` away)."""
    if side not in SIDES:
        raise ValueError(f"side must be left or right, not {side!r}")
    return left - half_width - OFFSTAGE_GAP if side == "left" else right + half_width + OFFSTAGE_GAP


def enter_path(side: str | None, to_x: float, view: tuple[float, float], half_width: float) -> tuple[str, float, float]:
    """``(side, start x, end x)`` of a character entering the view (``view`` = its left and right
    x) at ``to_x``: it starts just beyond the view's ``side`` edge (default: the edge nearer
    ``to_x``) and walks to ``to_x``."""
    side = side or nearer_side(to_x, *view)
    return side, offstage_x(side, view[0], view[1], half_width), to_x


def exit_path(side: str | None, from_x: float, view: tuple[float, float], half_width: float) -> tuple[str, float]:
    """``(side, end x)`` of a character at ``from_x`` leaving the view (``view`` = its left and
    right x): it walks until it is just beyond the view's ``side`` edge (default: the edge nearer
    it)."""
    side = side or nearer_side(from_x, *view)
    return side, offstage_x(side, view[0], view[1], half_width)


# ----- gestures and jumps ------------------------------------------------------------------------------

GESTURES: tuple[str, ...] = ("point", "wave", "shrug", "nod", "shake_head")
#: How long each gesture takes (seconds) when ``run_time`` does not say.
GESTURE_SECONDS: dict[str, float] = {"point": 1.2, "wave": 1.6, "shrug": 1.0, "nod": 0.9, "shake_head": 1.1}
#: Share of a gesture spent moving into it, and the same share moving back out.
GESTURE_EASE = 0.25
#: The near arm's angle (degrees, at rest it hangs down) for ``point`` and ``wave`` (the upper
#: arm; the elbow bends ``POINT_ELBOW`` / ``WAVE_ELBOW`` more, the hand forward: an arm in one
#: piece shows half the bend, 88° and 145°), and how far a wave swings to and fro (three times,
#: the forearm about the elbow; an arm in one piece swings half as far).
POINT_DEGREES = 82.0
POINT_ELBOW = 12.0
WAVE_DEGREES = 115.0
WAVE_ELBOW = 60.0
WAVE_SWING = 40.0
WAVES = 3
#: Both upper arms' angle for ``shrug`` (raised outwards), their elbows' bend (the forearms out)
#: and how far the shoulders rise (character units).
SHRUG_DEGREES = 15.0
SHRUG_ELBOW = 60.0
SHRUG_LIFT = 0.02
#: How far the head dips in a nod (twice), and how far it moves (and the eyes with it, twice as
#: far) to each side in a ``shake_head`` (twice), in degrees and character units.
NOD_DEGREES = 12.0
SHAKE_SHIFT = 0.012
#: How high a jump goes when ``height`` does not say (character heights).
JUMP_HEIGHT = 0.4
#: How long a jump takes (seconds) when ``run_time`` does not say.
JUMP_SECONDS = 0.6


@dataclass(frozen=True)
class PartMove:
    """A gesture's change to one part at one moment: the part turns ``weight`` (0..1) of the way
    from its pose's angle to ``angle`` (``None``: no such turn), then by ``turn`` degrees more,
    and shifts by ``shift`` (character units)."""

    angle: float | None = None
    weight: float = 0.0
    turn: float = 0.0
    shift: tuple[float, float] = (0.0, 0.0)


def gesture_weight(t: float, strength: float = 0.0) -> float:
    """How far into a gesture the parts are at ``t`` (0..1): easing in over
    :data:`GESTURE_EASE`, held, easing back out (0 at both ends, so it ends in the pose). With
    the animation principles' ``strength`` (§69.13) each ease winds up the other way first and
    passes its end and settles (:func:`~vidgen.cartoon.motion.motion_ease`; the way back is the
    way in, reversed)."""
    t = min(max(t, 0.0), 1.0)
    return motion_ease(min(1.0, t / GESTURE_EASE, (1.0 - t) / GESTURE_EASE), strength)


def gesture_moves(kind: str, t: float, arm: str = "arm_left", strength: float = 0.0) -> dict[str, PartMove]:
    """The part changes of gesture ``kind`` at ``t`` (0..1). ``point`` and ``wave`` use ``arm``
    and its forearm ``<arm>_lower`` (the near arm ``arm_left``, or ``arm_right`` when the
    character has no left arm: its angles are mirrored, as it hangs on the other side), ``shrug``
    both arms and forearms, ``nod`` and
    ``shake_head`` the head (and the eyes). ``strength``: the animation principles' anticipation
    and overshoot on the arms' ease in and out (:func:`gesture_weight`)."""
    if kind not in GESTURES:
        raise ValueError(f"unknown gesture {kind!r} (gestures: {', '.join(GESTURES)})")
    w = gesture_weight(t, strength)
    sign = 1.0 if arm == "arm_left" else -1.0
    lower = f"{arm}_lower"
    if kind == "point":
        return {arm: PartMove(sign * POINT_DEGREES, w), lower: PartMove(sign * POINT_ELBOW, w)}
    if kind == "wave":
        held = min(max((t - GESTURE_EASE) / (1.0 - 2 * GESTURE_EASE), 0.0), 1.0)
        swing = sign * WAVE_SWING * w * math.sin(2 * math.pi * WAVES * held)
        return {arm: PartMove(sign * WAVE_DEGREES, w), lower: PartMove(sign * WAVE_ELBOW, w, swing)}
    if kind == "shrug":
        lift = (0.0, SHRUG_LIFT * w)
        return {
            "arm_left": PartMove(SHRUG_DEGREES, w, shift=lift), "arm_left_lower": PartMove(SHRUG_ELBOW, w),
            "arm_right": PartMove(-SHRUG_DEGREES, w, shift=lift), "arm_right_lower": PartMove(-SHRUG_ELBOW, w),
        }
    if kind == "nod":
        return {"head": PartMove(turn=-NOD_DEGREES * math.sin(2 * math.pi * t) ** 2)}
    side = SHAKE_SHIFT * gesture_weight(t) * math.sin(4 * math.pi * t)
    return {"head": PartMove(shift=(side, 0.0)), "eyes": PartMove(shift=(side, 0.0))}


def jump_lift(t: float, height: float = JUMP_HEIGHT) -> float:
    """How high (in the unit of ``height``) a jump of ``height`` is at ``t`` (0..1): a parabola,
    0 at take-off and landing, ``height`` half-way."""
    t = min(max(t, 0.0), 1.0)
    return 4.0 * height * t * (1.0 - t)


__all__ = [
    "CAMERA_EYES_BACK",
    "GESTURES",
    "GESTURE_SECONDS",
    "JUMP_HEIGHT",
    "JUMP_SECONDS",
    "LOOK_EYES_AHEAD",
    "LOOK_MAX_DEGREES",
    "OFFSTAGE_GAP",
    "RUNNING",
    "RUN_SPEED",
    "SAME_X",
    "SIDES",
    "STEP_LENGTH",
    "WALKING",
    "WALK_SPEED",
    "Gait",
    "LookPose",
    "PartMove",
    "WalkCycle",
    "camera_look",
    "enter_path",
    "exit_path",
    "gesture_moves",
    "gesture_weight",
    "jump_lift",
    "look_pose",
    "nearer_side",
    "offstage_x",
    "walk_amplitude",
    "walk_cycle",
    "walk_progress",
    "walk_seconds",
]
