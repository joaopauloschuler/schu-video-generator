"""Where a character looks (DESIGN.md §69.11): the facing, head tilt and eye shift of the
``look_at`` action, worked out without manim.

Angles are in degrees counterclockwise as drawn facing right (a character facing left is the
mirror image, so a positive angle tilts the head up towards where it looks in both facings);
shifts are in character units (1 = the character's height).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

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


__all__ = ["CAMERA_EYES_BACK", "LOOK_EYES_AHEAD", "LOOK_MAX_DEGREES", "SAME_X", "LookPose", "camera_look", "look_pose"]
