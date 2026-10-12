"""Props in the characters' hands (DESIGN.md §69.27). No manim.

:class:`Holdings` is the state machine of who holds which prop in which hand: ``take`` (a
``pick_up`` or ``hold``), ``release`` (a ``put_down`` or ``throw``) and ``give`` (from one
character's hand to another's); each refuses with a :class:`HoldingError` whose message says what
to do instead. The stage keeps one while it plays, ``vidgen validate`` replays the beats through
one (:func:`holding_problems`, with the distances), and the automatic directing planner keeps one
so it adds no arm gesture with a hand that holds something.

The geometry is in Manim units and character heights: where a held prop sits (:func:`hold_point`,
in front of the shoulder; :func:`overhead_point` for an open umbrella, §69.37), how tall it is
in the hand (:func:`held_height`), where a prop is put
down (:func:`put_down_x`) and the arc and spin of a throw (:func:`throw_point`, :func:`spin_degrees`).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidgen.cartoon.seating import LEAN_REACH, SIT_REACH, PostureError, Postures

#: The hands, the near one (``left``, drawn in front of the body) first: a hand is taken in this
#: order when the action does not name one.
HAND_ORDER: tuple[str, ...] = ("left", "right")
#: Where a held prop's middle sits, from the holding arm's shoulder: forward and down, in the
#: holder's heights (within reach of the generated looks' arms, the elbow bent).
HOLD_FORWARD = 0.12
HOLD_DROP = 0.13
#: A held prop is at most this many of its holder's heights tall (a bigger one is scaled down
#: while it is held, and back when it is put down or lands).
HOLD_MAX_HEIGHT = 0.4
#: How far (in the character's heights, between its feet's x and the prop's or the other
#: character's) a character can pick a prop up, put it down, or hand it over.
PICK_UP_REACH = 0.75
PUT_DOWN_REACH = 0.75
GIVE_REACH = 1.2
#: Where ``put_down`` puts a prop without ``to``: this many heights in front of the feet.
PUT_DOWN_AHEAD = 0.35
#: Where a ``walk_to`` suggestion stands the character: this many heights from the prop's x.
STAND_BESIDE = 0.4
#: Seconds of each action, and the share of it at which the hand reaches the prop (``pick_up``,
#: ``give``) or the spot (``put_down``), and at which a put-down prop stands on the ground.
PICK_UP_SECONDS = 1.2
PUT_DOWN_SECONDS = 1.0
GIVE_SECONDS = 1.2
HOLD_SECONDS = 0.4
REACH_SHARE = 0.45
PUT_DOWN_REACH_SHARE = 0.5
PUT_DOWN_LAND_SHARE = 0.75
#: A throw: the arm winds up (``THROW_WIND_UP`` s), swings forward and lets go
#: (``THROW_SWING`` s), then the prop flies (:func:`throw_flight_seconds`). The arc rises
#: ``THROW_HEIGHT`` of the thrower's heights above the higher end; the prop spins ``THROW_SPIN``
#: turns (whole turns, so it lands upright).
THROW_WIND_UP = 0.35
THROW_SWING = 0.15
THROW_HEIGHT = 0.5
THROW_SPIN = 1
#: Flight time: ``THROW_FLIGHT_MIN`` s plus ``THROW_FLIGHT_PER_UNIT`` s per Manim unit thrown, at
#: most ``THROW_FLIGHT_MAX`` s.
THROW_FLIGHT_MIN = 0.45
THROW_FLIGHT_PER_UNIT = 0.06
THROW_FLIGHT_MAX = 1.6
#: The actions that hand props around or take one out of a hand (``blow_away``, DESIGN.md §69.32).
HANDLING_ACTIONS: frozenset[str] = frozenset({"pick_up", "hold", "put_down", "give", "throw", "blow_away"})
#: A prop showing one of these shapes (an open umbrella) is held overhead (DESIGN.md §69.37): the
#: hand ``OVERHEAD_FORWARD`` of its holder's heights in front of the feet and ``OVERHEAD_HAND``
#: above them (where every generated look's arm reaches, or nearly), the prop
#: ``OVERHEAD_HEIGHT`` holder heights tall (not :data:`HOLD_MAX_HEIGHT`), so an umbrella's canopy
#: is above the head of every generated look and wide enough to cover it.
OVERHEAD_SHAPES: frozenset[str] = frozenset({"open"})
OVERHEAD_FORWARD = 0.08
OVERHEAD_HAND = 0.6
OVERHEAD_HEIGHT = 0.85
#: Seconds of an ``open`` / ``close`` action, and the share of it at which the shape changes.
RESHAPE_SECONDS = 0.6
RESHAPE_SHARE = 0.5


class HoldingError(ValueError):
    """A change :class:`Holdings` refuses; the message says why and what to do instead."""


@dataclass
class Holdings:
    """Who holds which prop: prop name -> (character, hand)."""

    held: dict[str, tuple[str, str]] = field(default_factory=dict)

    def holder(self, prop: str) -> tuple[str, str] | None:
        """``(character, hand)`` holding ``prop``, or ``None`` (it stands somewhere)."""
        return self.held.get(prop)

    def hands(self, character: str) -> dict[str, str]:
        """What ``character`` holds: hand -> prop, in :data:`HAND_ORDER`."""
        mine = {hand: prop for prop, (who, hand) in self.held.items() if who == character}
        return {hand: mine[hand] for hand in HAND_ORDER if hand in mine}

    def free_hand(self, character: str, hand: str | None = None) -> str:
        """``hand`` if it is free, else (no ``hand``) the first free one of :data:`HAND_ORDER`."""
        busy = self.hands(character)
        if hand is not None:
            if hand in busy:
                raise HoldingError(f"{character}'s {hand} hand already holds '{busy[hand]}'; use the other hand or put_down first")
            return hand
        for candidate in HAND_ORDER:
            if candidate not in busy:
                return candidate
        raise HoldingError(f"{character} already holds '{busy['left']}' and '{busy['right']}'; put_down, give or throw one first")

    def take(self, character: str, prop: str, hand: str | None = None) -> str:
        """``character`` takes ``prop`` in ``hand`` (default: a free one); returns the hand."""
        holder = self.holder(prop)
        if holder is not None:
            if holder[0] == character:
                raise HoldingError(f"{character} already holds '{prop}'")
            raise HoldingError(f"'{prop}' is held by {holder[0]}; {holder[0]} can give it (give: {holder[0]}, to: {character})")
        chosen = self.free_hand(character, hand)
        self.held[prop] = (character, chosen)
        return chosen

    def held_prop(self, character: str, prop: str | None = None) -> tuple[str, str]:
        """``(prop, hand)``: ``prop`` if ``character`` holds it, else the only prop it holds."""
        mine = self.hands(character)
        if prop is not None:
            for hand, name in mine.items():
                if name == prop:
                    return prop, hand
            holder = self.holder(prop)
            elsewhere = f" ({holder[0]} holds it)" if holder is not None else ""
            raise HoldingError(f"{character} does not hold '{prop}'{elsewhere}; pick_up it first")
        if not mine:
            raise HoldingError(f"{character} holds no prop then; pick_up one first")
        if len(mine) > 1:
            raise HoldingError(f"{character} holds two props ({', '.join(mine.values())}); name one with prop:")
        hand, name = next(iter(mine.items()))
        return name, hand

    def release(self, character: str, prop: str | None = None) -> tuple[str, str]:
        """``character`` lets go of ``prop`` (default: the only one it holds); ``(prop, hand)``."""
        name, hand = self.held_prop(character, prop)
        del self.held[name]
        return name, hand

    def drop(self, prop: str) -> tuple[str, str] | None:
        """Whoever holds ``prop`` loses it (it blows out of the hand); ``(character, hand)`` that
        held it, or ``None`` (nobody did)."""
        return self.held.pop(prop, None)

    def give(self, giver: str, receiver: str, prop: str | None = None, hand: str | None = None) -> tuple[str, str, str]:
        """``giver`` hands ``prop`` (default: the only one it holds) to ``receiver``'s ``hand``
        (default: a free one); ``(prop, giver's hand, receiver's hand)``."""
        if giver == receiver:
            raise HoldingError(f"{giver} cannot give a prop to itself")
        name, from_hand = self.held_prop(giver, prop)
        to_hand = self.free_hand(receiver, hand)
        self.held[name] = (receiver, to_hand)
        return name, from_hand, to_hand


# ----- geometry (Manim units) --------------------------------------------------------------------------


def hold_point(shoulder: Sequence[float], height: float, facing: str) -> tuple[float, float]:
    """Where a held prop's middle (and the hand) is: :data:`HOLD_FORWARD` heights in front of
    the holding arm's ``shoulder`` (screen) and :data:`HOLD_DROP` below it."""
    ahead = HOLD_FORWARD * height * (1.0 if facing == "right" else -1.0)
    return float(shoulder[0]) + ahead, float(shoulder[1]) - HOLD_DROP * height


def held_height(height_factor: float, holder_height: float, *, overhead: bool = False) -> float:
    """How tall a prop is in a hand: its height next to the holder (``height_factor`` of the
    holder's height), at most :data:`HOLD_MAX_HEIGHT` of it; held ``overhead``:
    :data:`OVERHEAD_HEIGHT` of it."""
    if overhead:
        return OVERHEAD_HEIGHT * holder_height
    return min(height_factor, HOLD_MAX_HEIGHT) * holder_height


def overhead_point(feet: Sequence[float], height: float, facing: str) -> tuple[float, float]:
    """Where the hand holding a prop overhead is: :data:`OVERHEAD_FORWARD` heights in front of
    the holder's ``feet`` (screen) and :data:`OVERHEAD_HAND` above them."""
    ahead = OVERHEAD_FORWARD * height * (1.0 if facing == "right" else -1.0)
    return float(feet[0]) + ahead, float(feet[1]) + OVERHEAD_HAND * height


def put_down_x(feet_x: float, height: float, facing: str) -> float:
    """Where ``put_down`` without ``to`` puts a prop: :data:`PUT_DOWN_AHEAD` heights in front."""
    return feet_x + PUT_DOWN_AHEAD * height * (1.0 if facing == "right" else -1.0)


def throw_flight_seconds(distance: float) -> float:
    """How long a thrown prop flies ``distance`` Manim units (either way)."""
    return min(THROW_FLIGHT_MIN + THROW_FLIGHT_PER_UNIT * abs(distance), THROW_FLIGHT_MAX)


def throw_seconds(distance: float) -> float:
    """A throw's whole time: wind-up, swing and the flight of ``distance`` units."""
    return THROW_WIND_UP + THROW_SWING + throw_flight_seconds(distance)


def throw_release_share(distance: float) -> float:
    """The share of a throw's time at which the hand lets the prop go."""
    return (THROW_WIND_UP + THROW_SWING) / throw_seconds(distance)


def throw_point(t: float, start: Sequence[float], end: Sequence[float], rise: float) -> tuple[float, float]:
    """The prop's middle at ``t`` (0..1) of its flight from ``start`` to ``end`` (screen): x
    evenly, y on a parabola that peaks ``rise`` units above the higher end."""
    x0, y0, x1, y1 = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    top = max(y0, y1) + rise
    # y(t) = a t^2 + b t + y0 through y(1) = y1 with its peak at top (the larger root of b)
    a_plus_b = y1 - y0
    peak_rise = top - y0
    b = 2.0 * (peak_rise + math.sqrt(max(peak_rise * (peak_rise - a_plus_b), 0.0)))
    a = a_plus_b - b
    return x0 + (x1 - x0) * t, y0 + b * t + a * t * t


def spin_degrees(t: float, turns: int, towards: float) -> float:
    """The prop's turn at ``t`` (0..1) of its flight: ``turns`` whole turns, clockwise when it
    flies right (``towards`` > 0), counterclockwise when it flies left."""
    return -360.0 * turns * t * (1.0 if towards >= 0 else -1.0)


# ----- replaying a scene's beats (vidgen validate) ---------------------------------------------------------


@dataclass(frozen=True)
class HandlingStep:
    """One action of a stage scene, in play order, as :func:`holding_problems` reads it: where it
    is in the config, its type, the characters and props it targets, and its options."""

    location: str
    action: str
    targets: tuple[str, ...]
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class _Positions:
    """Each character's and prop's feet x (``None``: not known), the characters' heights, and
    who is on stage."""

    x: dict[str, float | None]
    heights: Mapping[str, float]
    present: set[str]


def _too_far(who: str, what: str, gap: float, height: float, reach: float, fix: str) -> str | None:
    if abs(gap) <= reach * height:
        return None
    return f"{who} is {abs(gap) / height:.1f} of its heights from {what} (it reaches {reach}); {fix}"


def holding_problems(
    steps: Sequence[HandlingStep],
    *,
    characters: Mapping[str, tuple[float, float]],
    props: Mapping[str, float],
    place_x: Callable[[Any], float | None],
    to_fraction: Callable[[float], float],
    entering: Sequence[str] = (),
) -> list[tuple[str, str]]:
    """Replay a stage scene's actions (``steps`` in play order) through :class:`Holdings`,
    :class:`~vidgen.cartoon.seating.Postures` and the characters' positions; ``(location,
    message)`` per action that cannot happen then: a prop held by another or a hand full
    (``pick_up``, ``hold``, ``give``), nothing to put down, give or throw, a prop or a spot too far
    without a walk (with the ``walk_to`` that fixes it), a character to give to who is not next to
    the giver, a keyed move of a prop someone holds; sitting or leaning (DESIGN.md §69.28): a seat
    taken, a prop held or too far to sit or lean on, a ``stand_up`` with nothing to stand up from,
    a walk, jump, turn or keyed move of a character that sits or leans, a prop picked up or moved
    while someone sits or leans on it; ``blow_away`` (§69.32) takes a prop out of whoever's hand,
    and one blown off stage (no ``to``) cannot be used again. ``characters``: name -> (feet x, height); ``props``: name ->
    x; ``place_x`` a mark or x of the stage in Manim units (``None``: neither); ``to_fraction`` an
    x back to 0..1 of the stage; ``entering``: characters off stage until their first ``enter``."""
    holdings = Holdings()
    postures = Postures()
    where = _Positions({n: x for n, (x, _) in characters.items()}, {n: h for n, (_, h) in characters.items()}, set(characters) - set(entering))
    where.x.update(props)
    problems: list[tuple[str, str]] = []

    def x_of(name: str) -> float | None:
        holder = holdings.holder(name)
        return where.x.get(holder[0] if holder is not None else name)

    def beside(who: str, x: float) -> str:
        here = where.x.get(who)
        side = -1.0 if here is None or here <= x else 1.0
        return f"walk_to first (- walk_to: {who}, to: {to_fraction(x + side * STAND_BESIDE * where.heights[who]):.2f})"

    def in_use(prop: str) -> str | None:
        users = postures.on(prop)
        if not users:
            return None
        verb = "sits" if postures.of(users[0])[0] == "sitting" else "leans"
        return f"{users[0]} {verb} on '{prop}' then; stand_up first (- stand_up: {users[0]})"

    def blown_off(prop: str) -> str | None:
        if prop not in gone:
            return None
        return f"'{prop}' blew away off stage ({gone[prop]}); blow it to: a mark instead to use it again"

    #: props a ``blow_away`` without ``to`` took off stage -> where that action is
    gone: dict[str, str] = {}
    for step in steps:
        o = step.options
        for who in [t for t in step.targets if t in characters]:
            here, height = where.x.get(who), where.heights[who]
            named = str(o.get("to")) if step.action in ("pick_up", "hold", "sit_on", "lean_on") else None
            if named is not None and blown_off(named) is not None:
                problems.append((f"{step.location}.to", blown_off(named)))
                continue
            try:
                postures.pinned(who, step.action)
                if step.action in ("sit_on", "lean_on"):
                    prop = str(o.get("to"))
                    if prop not in props:
                        continue
                    holder = holdings.holder(prop)
                    if holder is not None:
                        problems.append((f"{step.location}.to", f"'{prop}' is held by {holder[0]} then; put_down it first"))
                        continue
                    reach = SIT_REACH if step.action == "sit_on" else LEAN_REACH
                    if here is not None and x_of(prop) is not None:
                        message = _too_far(who, f"'{prop}'", x_of(prop) - here, height, reach, beside(who, x_of(prop)))
                        if message is not None:
                            problems.append((f"{step.location}.to", message))
                            continue
                    (postures.sit if step.action == "sit_on" else postures.lean)(who, prop)
                    where.x[who] = x_of(prop)
                elif step.action == "stand_up":
                    postures.stand(who)
                elif step.action == "enter":
                    where.present.add(who)
                    where.x[who] = place_x(o["to"]) if o.get("to") is not None else characters[who][0]
                elif step.action == "exit":
                    where.present.discard(who)
                elif step.action in ("walk_to", "run_to"):
                    where.x[who] = place_x(o.get("to"))
                elif step.action in ("move_along", "keyframes"):
                    where.x[who] = None
                elif step.action in ("pick_up", "hold"):
                    prop = str(o.get("to"))
                    if prop not in props:
                        continue
                    if in_use(prop) is not None:
                        problems.append((f"{step.location}.to", in_use(prop)))
                        continue
                    if step.action == "pick_up" and here is not None and holdings.holder(prop) is None and x_of(prop) is not None:
                        message = _too_far(who, f"'{prop}'", x_of(prop) - here, height, PICK_UP_REACH, beside(who, x_of(prop)))
                        if message is not None:
                            problems.append((f"{step.location}.to", message))
                            continue
                    holdings.take(who, prop, o.get("hand"))
                elif step.action == "give":
                    other = str(o.get("to"))
                    if other not in characters:
                        continue
                    there = where.x.get(other)
                    if other not in where.present:
                        problems.append((f"{step.location}.to", f"{other} is not on stage then; enter it first"))
                        continue
                    if here is not None and there is not None:
                        message = _too_far(who, other, there - here, height, GIVE_REACH, f"they must stand next to each other: {beside(who, there)}")
                        if message is not None:
                            problems.append((f"{step.location}.to", message))
                            continue
                    holdings.give(who, other, o.get("prop"), o.get("hand"))
                elif step.action in ("put_down", "throw"):
                    prop, _ = holdings.held_prop(who, o.get("prop"))
                    spot = place_x(o["to"]) if o.get("to") is not None else here
                    if step.action == "put_down" and here is not None and spot is not None:
                        message = _too_far(who, "where it puts the prop down", spot - here, height, PUT_DOWN_REACH, beside(who, spot))
                        if message is not None:
                            problems.append((f"{step.location}.to", message))
                            continue
                    holdings.release(who, prop)
                    where.x[prop] = spot
            except (HoldingError, PostureError) as exc:
                key = "prop" if step.action in ("put_down", "throw", "give") and o.get("prop") is not None else "target"
                problems.append((f"{step.location}.{key}", str(exc)))
        for prop in [t for t in step.targets if t in props]:
            holder = holdings.holder(prop)
            if step.action in ("move_along", "keyframes", "blow_away", "open", "close") and blown_off(prop) is not None:
                problems.append((f"{step.location}.target", blown_off(prop)))
            elif step.action == "blow_away" and in_use(prop) is not None:
                problems.append((f"{step.location}.target", in_use(prop)))
            elif step.action == "blow_away":
                holdings.drop(prop)
                where.x[prop] = place_x(o["to"]) if o.get("to") is not None else None
                if o.get("to") is None:
                    gone[prop] = step.location
            elif step.action in ("move_along", "keyframes") and holder is not None:
                problems.append((f"{step.location}.target", f"'{prop}' is held by {holder[0]} then; put_down or throw it first"))
            elif step.action in ("move_along", "keyframes") and in_use(prop) is not None:
                problems.append((f"{step.location}.target", in_use(prop)))
            elif step.action in ("move_along", "keyframes"):
                where.x[prop] = None
    return problems
