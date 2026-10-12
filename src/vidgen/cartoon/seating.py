"""Sitting on props, leaning against them, and crouching (DESIGN.md §69.28). No manim.

Props carry their *seat* and *lean edges* in prop units (the origin at the middle of the prop's
foot, ``y`` up, the top at 1, ``x`` in the same unit), as drawn facing right: built-in props by
kind (:data:`PROP_SEATS`, :data:`PROP_LEANS`), SVG props by ``data-seat="x y"`` and
``data-lean="left right"`` on their ``<svg>`` element, in ``viewBox`` coordinates
(:func:`svg_seat_and_lean`).

:class:`Postures` is the state machine of who sits or leans on which prop (``sit_on``,
``lean_on``, ``stand_up``); each refusal is a :class:`PostureError` whose message says what to do
instead. ``vidgen validate`` replays a scene through one (with the props in hands:
:func:`~vidgen.cartoon.holding.holding_problems`) and the automatic directing planner keeps one,
so it does not turn a character that sits or leans.

The geometry in character units: where a seated character's feet go (:func:`seated_sole`) and
how far a character crouches to reach a low point (:func:`crouch_drop`).
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

#: The seat of each built-in prop that has one: the middle of its seat line, (x, y) in prop units
#: as drawn facing right (a chair's back is on its left: a character sitting on it faces right).
PROP_SEATS: dict[str, tuple[float, float]] = {"chair": (0.1, 0.54), "rock": (0.0, 0.9), "box": (-0.1, 0.9)}
#: Props with a back: a character sitting on one faces the way the prop faces.
SEAT_BACKS: frozenset[str] = frozenset({"chair"})
#: The edges a character leans its back on, (left x, right x) in prop units as drawn facing right:
#: a tree's trunk, a door's frame, a sign's board, a lamp's post, a house's wall.
PROP_LEANS: dict[str, tuple[float, float]] = {
    "tree": (-0.08, 0.08), "door": (-0.3, 0.3), "sign": (-0.4, 0.36), "lamp": (-0.04, 0.04), "house": (-0.5, 0.5),
}
#: How far (in the character's heights, between its feet's x and the prop's) a character can sit
#: down on a prop or lean on it without walking first.
SIT_REACH = 0.75
LEAN_REACH = 1.0
#: How far a leaning character's body tilts back (degrees).
LEAN_DEGREES = 12.0
#: A character whose legs are one part (``legs``) sits with them turned this far forward, as in
#: the ``sitting`` pose.
SEATED_LEGS_DEGREES = 80.0
#: A crouch: the body lowers at most this share of the hips' height, the hand uses at most
#: ``CROUCH_REACH`` of the arm's length, and the body bends forward up to ``CROUCH_STOOP``
#: degrees (in proportion to how deep it crouches); a drop under ``CROUCH_MIN`` (character
#: units) is no crouch.
CROUCH_MAX = 0.6
CROUCH_REACH = 0.95
CROUCH_STOOP = 15.0
CROUCH_MIN = 0.01
#: Seconds of each action.
SIT_SECONDS = 1.0
STAND_UP_SECONDS = 0.8
LEAN_SECONDS = 0.8
#: The actions that sit, lean or stand up, and the whole-character moves a character that sits or
#: leans cannot make before it stands up.
POSTURE_ACTIONS: frozenset[str] = frozenset({"sit_on", "lean_on", "stand_up"})
PINNED_ACTIONS: frozenset[str] = frozenset({"walk_to", "run_to", "enter", "exit", "jump", "turn", "move_along", "keyframes"})


class PostureError(ValueError):
    """A change :class:`Postures` refuses; the message says why and what to do instead."""


@dataclass
class Postures:
    """Who sits or leans on which prop: character -> (``sitting`` | ``leaning``, prop)."""

    held: dict[str, tuple[str, str]] = field(default_factory=dict)

    def of(self, character: str) -> tuple[str, str] | None:
        """``(posture, prop)`` of ``character``, or ``None`` (it stands)."""
        return self.held.get(character)

    def on(self, prop: str) -> list[str]:
        """The characters sitting or leaning on ``prop``."""
        return [who for who, (_, name) in self.held.items() if name == prop]

    def _free(self, character: str) -> None:
        now = self.of(character)
        if now is not None:
            verb = "sits on" if now[0] == "sitting" else "leans on"
            raise PostureError(f"{character} {verb} '{now[1]}' then; stand_up first (- stand_up: {character})")

    def sit(self, character: str, prop: str) -> None:
        """``character`` sits down on ``prop`` (one character per seat)."""
        self._free(character)
        sitting = [who for who in self.on(prop) if self.held[who][0] == "sitting"]
        if sitting:
            raise PostureError(f"'{prop}' is taken: {sitting[0]} sits on it then")
        self.held[character] = ("sitting", prop)

    def lean(self, character: str, prop: str) -> None:
        """``character`` leans its back on ``prop`` (several may lean on one prop)."""
        self._free(character)
        self.held[character] = ("leaning", prop)

    def stand(self, character: str) -> tuple[str, str]:
        """``character`` stands up; what it did: ``(posture, prop)``."""
        now = self.held.pop(character, None)
        if now is None:
            raise PostureError(f"{character} neither sits nor leans then; stand_up follows a sit_on or a lean_on")
        return now

    def pinned(self, character: str, action: str) -> None:
        """Refuse ``action`` (one of :data:`PINNED_ACTIONS`) while ``character`` sits or leans."""
        if action in PINNED_ACTIONS:
            self._free(character)


# ----- props' seats and lean edges ------------------------------------------------------------------


def mirrored_seat(seat: tuple[float, float] | None, facing: str) -> tuple[float, float] | None:
    """A seat as drawn facing right, for a prop facing ``facing``."""
    if seat is None or facing == "right":
        return seat
    return -seat[0], seat[1]


def mirrored_lean(lean: tuple[float, float] | None, facing: str) -> tuple[float, float] | None:
    """Lean edges as drawn facing right, for a prop facing ``facing``."""
    if lean is None or facing == "right":
        return lean
    return -lean[1], -lean[0]


def _numbers(value: str, count: int, what: str, where: str) -> list[float]:
    try:
        numbers = [float(v) for v in value.replace(",", " ").split()]
    except ValueError:
        numbers = []
    if len(numbers) != count or not all(math.isfinite(n) for n in numbers):
        raise ValueError(f"{where}: {what} must be {count} numbers in viewBox coordinates, not {value!r}")
    return numbers


def svg_seat_and_lean(
    root: ET.Element, view_box: tuple[float, float, float, float], where: str,
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    """The seat and the lean edges an SVG prop's ``<svg>`` element ``root`` gives (``data-seat="x
    y"``: the middle of its seat line; ``data-lean="left right"``: the x of the edges a character
    leans on), from ``viewBox`` coordinates to prop units (``None`` where it gives none).
    ``ValueError`` for a value that is not those numbers."""
    vx, vy, vw, vh = view_box
    middle, bottom = vx + vw / 2, vy + vh
    seat = lean = None
    if root.get("data-seat") is not None:
        x, y = _numbers(root.get("data-seat", ""), 2, "data-seat", where)
        seat = ((x - middle) / vh, (bottom - y) / vh)
    if root.get("data-lean") is not None:
        left, right = sorted(_numbers(root.get("data-lean", ""), 2, "data-lean", where))
        lean = ((left - middle) / vh, (right - middle) / vh)
    return seat, lean


# ----- geometry (character units) -------------------------------------------------------------------


def seated_sole(hip: tuple[float, float], thigh: float, shin: float) -> tuple[float, float]:
    """Where a seated leg's sole goes, its hip at ``hip`` (x forward, y above the ground): the shin
    straight down to the ground in front, the knee forward; on a seat too high for that the thigh
    lies level and the foot hangs; on one too low the knee is folded as far as it goes."""
    x, y = hip
    drop = y - shin   # how far the thigh goes down if the shin stands straight on the ground
    if drop > thigh:
        return x + thigh, drop
    return x + math.sqrt(max(thigh * thigh - drop * drop, 0.0)), 0.0


def crouch_drop(above: float, ahead: float, arm_length: float, hip_height: float) -> float:
    """How far a character lowers its body to reach a point ``above`` below its shoulder and
    ``ahead`` in front of it with an arm ``arm_length`` long (using :data:`CROUCH_REACH` of it):
    0 when it reaches already, at most :data:`CROUCH_MAX` of ``hip_height`` (any unit, the same for
    all)."""
    reach = CROUCH_REACH * arm_length
    level = math.sqrt(max(reach * reach - ahead * ahead, 0.0))
    return min(max(above - level, 0.0), CROUCH_MAX * hip_height)


def crouch_stoop(drop: float, hip_height: float) -> float:
    """How far (degrees) a character crouching ``drop`` bends forward: :data:`CROUCH_STOOP` at the
    deepest crouch, less in proportion."""
    deepest = CROUCH_MAX * hip_height
    return CROUCH_STOOP * min(drop / deepest, 1.0) if deepest > 0 else 0.0


__all__ = [
    "CROUCH_MAX",
    "CROUCH_MIN",
    "CROUCH_REACH",
    "CROUCH_STOOP",
    "LEAN_DEGREES",
    "LEAN_REACH",
    "LEAN_SECONDS",
    "PINNED_ACTIONS",
    "POSTURE_ACTIONS",
    "PROP_LEANS",
    "PROP_SEATS",
    "PostureError",
    "Postures",
    "SEATED_LEGS_DEGREES",
    "SEAT_BACKS",
    "SIT_REACH",
    "SIT_SECONDS",
    "STAND_UP_SECONDS",
    "crouch_drop",
    "crouch_stoop",
    "mirrored_lean",
    "mirrored_seat",
    "seated_sole",
    "svg_seat_and_lean",
]
