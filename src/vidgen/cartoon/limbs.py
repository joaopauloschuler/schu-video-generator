"""Arms and legs in two segments, and the two-bone solver that bends them (DESIGN.md §69.26). No manim.

A *limb* is an upper part that turns about the shoulder or the hip (``arm_left``, ``arm_right``,
``leg_left``, ``leg_right``) and, optionally, its lower part that turns about the elbow or the
knee and hangs from it (``arm_left_lower``, ...). The hand or the foot is the far end of the
lower part. A limb drawn in one piece still has its lower part's pose (a *folded* lower part):
the piece turns by half the joint's angle and gets shorter by the chord, so its end lands where
a two-segment limb's would (:func:`fold`).

Angles are in degrees counterclockwise, as drawn facing right; a joint's bend is the lower
part's angle relative to the upper. Natural joints: an elbow bends counterclockwise (the hand
comes forward, the elbow stays behind and below), a knee clockwise (the foot goes back, the knee
forward).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Each limb: its upper part (the limb's name) and its lower part.
LIMBS: dict[str, str] = {
    "arm_left": "arm_left_lower", "arm_right": "arm_right_lower",
    "leg_left": "leg_left_lower", "leg_right": "leg_right_lower",
}
#: The upper part of each lower part.
UPPER_OF: dict[str, str] = {lower: upper for upper, lower in LIMBS.items()}
#: ``reach`` and ``plant`` name a side: the arm or leg on that side of the character.
HANDS: dict[str, str] = {"left": "arm_left", "right": "arm_right"}
FEET: dict[str, str] = {"left": "leg_left", "right": "leg_right"}
#: Which way each joint bends when the call does not say: +1 counterclockwise (an elbow: the
#: hand forward), -1 clockwise (a knee: the foot back).
ELBOW_BEND = 1.0
KNEE_BEND = -1.0
#: The shortest a folded one-piece limb gets (a share of its length), so its hand or foot is
#: not squashed flat.
FOLD_MIN_LENGTH = 0.6
#: The part whose time window in a pose change a part shares (``PoseChange``): a lower part
#: moves with its upper part, and the legs of either kind move together, as one ``legs`` did.
TIMING_GROUP: dict[str, str] = {
    "arm_left_lower": "arm_left", "arm_right_lower": "arm_right",
    "leg_left": "legs", "leg_left_lower": "legs", "leg_right": "legs", "leg_right_lower": "legs",
}


def limb_side(names: dict[str, str], side: str, what: str) -> str:
    """The limb of ``names`` (:data:`HANDS` or :data:`FEET`) on ``side``; ``ValueError`` otherwise."""
    if side not in names:
        raise ValueError(f"{what} must be {' or '.join(names)}, not {side!r}")
    return names[side]


@dataclass(frozen=True)
class TwoBone:
    """A two-bone solution: the upper segment's ``direction`` (degrees counterclockwise from +x),
    the joint's ``bend`` (degrees, the lower segment relative to the upper) and whether the end
    ``reached`` the point (else the limb points at it, straight, or folded as far as it goes)."""

    direction: float
    bend: float
    reached: bool


def solve_two_bone(
    root: tuple[float, float],
    target: tuple[float, float],
    upper_length: float,
    lower_length: float,
    bend: float = ELBOW_BEND,
) -> TwoBone:
    """Where a limb from ``root`` with segments ``upper_length`` and ``lower_length`` long puts
    its end on ``target``, the joint bending the way of ``bend``'s sign (+1 counterclockwise).
    A point too far: the limb straight towards it; too near: folded as far as the lengths allow,
    towards it; on the root: the upper segment points along +x (degenerate)."""
    if upper_length <= 0 or lower_length <= 0:
        raise ValueError("segment lengths must be positive")
    dx, dy = target[0] - root[0], target[1] - root[1]
    distance = math.hypot(dx, dy)
    base = math.degrees(math.atan2(dy, dx)) if distance > 1e-12 else 0.0
    longest, shortest = upper_length + lower_length, abs(upper_length - lower_length)
    reached = shortest - 1e-9 <= distance <= longest + 1e-9
    d = min(max(distance, shortest, 1e-12), longest)
    cos_root = (upper_length ** 2 + d ** 2 - lower_length ** 2) / (2 * upper_length * d)
    cos_joint = (upper_length ** 2 + lower_length ** 2 - d ** 2) / (2 * upper_length * lower_length)
    at_root = math.degrees(math.acos(min(max(cos_root, -1.0), 1.0)))
    at_joint = math.degrees(math.acos(min(max(cos_joint, -1.0), 1.0)))
    sign = 1.0 if bend >= 0 else -1.0
    return TwoBone(direction=base - sign * at_root, bend=sign * (180.0 - at_joint), reached=reached)


def fold(bend: float) -> tuple[float, float]:
    """How a limb drawn in one piece shows a joint bent ``bend`` degrees: ``(turn, length)``, the
    piece turned by half the bend and shortened to the chord (``cos(bend / 2)``, at least
    :data:`FOLD_MIN_LENGTH`), so its end is where a limb of two equal halves would put it."""
    return bend / 2.0, max(math.cos(math.radians(bend / 2.0)), FOLD_MIN_LENGTH)


def wrap_degrees(angle: float) -> float:
    """``angle`` in (-180, 180]."""
    wrapped = math.fmod(angle + 180.0, 360.0)
    return (wrapped + 360.0 if wrapped <= 0 else wrapped) - 180.0


__all__ = [
    "ELBOW_BEND",
    "FEET",
    "FOLD_MIN_LENGTH",
    "HANDS",
    "KNEE_BEND",
    "LIMBS",
    "TIMING_GROUP",
    "TwoBone",
    "UPPER_OF",
    "fold",
    "limb_side",
    "solve_two_bone",
    "wrap_degrees",
]
