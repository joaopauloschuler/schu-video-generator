"""Sitting on, lying on and using the objects of an iso place (DESIGN.md §105.2): the part of a
``stage`` that places a character on a seat or in a bed of the place, draws the parts of the
object in front of it over it, stands it up again and moves its hands to use an object. Written
against ``vidgen.api`` only; :class:`IsoSeating` is a part of :class:`~vidgen.scenes.stage.Stage`.

A character sits with its feet on the ground under the seat's middle and its hips on the seat
(:meth:`Character.seated`), facing the way the seat faces; it lies in bed turned along the bed on
the picture, smaller (:data:`LIE_SCALE`), its legs folded away under the blanket. From half way
through sitting down its front picture starts with the object's *part* in front of it (an
armchair's near arm, a desk chair's back, a blanket: :meth:`IsoScenery.part`), and leaves out the
object itself (it sits inside its box).
"""

import math
from dataclasses import dataclass, replace
from typing import Any

from vidgen.api import *

#: How far (character heights) the hands move while typing, warming or pressing, and how long
#: each of their small moves takes (seconds).
USE_BOB = 0.025
USE_STEP = {"type": 0.18, "warm": 0.7, "read": 1.2, "reach": 0.6}
#: The share of a use (at most :data:`USE_IN` seconds) the hands take to get there and back.
USE_IN = 0.45


@dataclass(frozen=True)
class SeatPlace:
    """Where a character sits or lies on an object: its feet (world, tile units), how high its
    hips rest over them (tile units), the way it faces, the object and its part's key (the part
    drawn over it)."""

    feet: tuple[float, float, float]
    lift: float
    facing: str
    seat: tuple[str, str]


class IsoSeating:
    """Sitting, lying and using on an iso place: a part of the ``stage`` (DESIGN.md §105.2)."""

    def _iso_part(self, item: Any, base: float, regions: Any, key: str) -> None:
        """Make the part of ``item`` (standing on ``base``) inside ``regions`` (drawn over who
        sits or lies there)."""
        parts = self.__dict__.setdefault("_iso_seat_parts", {})
        if (item.name, key) in parts:
            return
        index = None
        if regions:
            index = self.iso_scenery.part(item.name, key, lambda shape: in_regions(item, base, regions, shape_points(shape)))
        parts[(item.name, key)] = index

    def iso_seat(self, name: str, place: int) -> SeatPlace:
        """The seat ``place`` of the object ``name`` of the place."""
        world = self.iso_place_now()
        item = world.object(name)
        base = world.floor_z(item.column, item.row)
        seat = ISO_SEATS[item.kind][place]
        x, y, _ = seat_hips(item, base, seat)
        key = f"seat{place}"
        self._iso_part(item, base, seat.front, key)
        return SeatPlace((x, y, base), seat.z, seat_facing(item, seat), (name, key))

    def iso_bed(self, name: str, character: Character) -> SeatPlace:
        """Where ``character`` lies in the bed ``name``: its hips on the mattress so far along the
        bed that the top of its head (lying, :data:`LIE_SCALE`) is at the bed's head."""
        world = self.iso_place_now()
        item = world.object(name)
        base = world.floor_z(item.column, item.row)
        bed = ISO_BEDS[item.kind]
        hips = self.iso_hips(character)
        across = math.hypot(*iso_point(0.0, 1.0)) * self.iso_view.unit   # Manim units per tile along the bed
        length = (character.standing_height - hips) * LIE_SCALE / across
        depth = (item.width if item.facing == "right" else item.depth)
        b = min(bed.head + length / depth, 0.9)
        x, y, _ = object_frame_point(item, base, bed.a, b, 0.0)
        self._iso_part(item, base, bed.front, "bed")
        return SeatPlace((x, y, base), bed.z, bed_facing(item), (name, "bed"))

    @staticmethod
    def iso_hips(character: Character) -> float:
        """How high (Manim units, upright and unscaled) its hips are over its feet now."""
        return float(character.pivot("body")[1] - character.feet()[1])

    def iso_lying(self, character: Character, before: CharacterState, lift: float) -> CharacterState:
        """``before`` lying on its back along a bed on the picture: the body turned
        :data:`LIE_DEGREES` about the hips and raised so the hips (drawn :data:`LIE_SCALE` smaller)
        are ``lift`` (tile units) over the feet, the legs folded away under the blanket."""
        height = character.character_height
        hips = self.iso_hips(character) / height
        parts = dict(before.parts)
        body = parts["body"]
        rise = self.iso_view.height(lift) / (LIE_SCALE * height) - hips
        parts["body"] = replace(body, angle=LIE_DEGREES, shift=(body.shift[0], body.shift[1] + rise))
        for leg in ("legs", "leg_left", "leg_right"):
            if leg in parts:
                parts[leg] = replace(parts[leg], scale=(0.05, 0.05))
        return CharacterState(before.facing, parts)

    def iso_seat_move(self, character: Character, keys: Any, place: SeatPlace | None, *, end: Any = None, facing: str | None = None,
                      soles: Any = None, scale: float = 1.0, run_time: float = SIT_SECONDS) -> IsoSeatMove:
        """The move sitting ``character`` down on (lying it on) ``place``, or standing it up at
        ``end`` (``place`` ``None``; its feet's world point): an :class:`IsoSeatMove`. Where it
        stood before sitting down is kept for its stand-up."""
        stands = self.__dict__.setdefault("_iso_stands", {})
        if place is not None:
            stands[character.name] = tuple(character.iso_feet)
            end = place.feet
        self._watch_draw_order()
        return IsoSeatMove(character, keys, self.iso_view, end, seat=place.seat if place is not None else None, scale=scale,
                           facing=facing, soles=soles, run_time=run_time)

    def iso_stand_point(self, name: str) -> tuple[float, float, float] | None:
        """Where the character ``name`` stood before it sat or lay down (``None``: it did not)."""
        return self.__dict__.get("_iso_stands", {}).pop(name, None)

    def _iso_seat_front(self, figure: Any) -> Any:
        """The front picture of a character sitting or lying on an object: the object's part in
        front of it first, then what stands in front of it but the object itself."""
        name, key = figure.iso_seat
        first = self.__dict__.get("_iso_seat_parts", {}).get((name, key))
        return self.iso_scenery.front(self._iso_body(figure), exclude=(name,), first=first)

    # ----- using an object -------------------------------------------------------------------------

    def iso_use(self, character: Character, name: str, seconds: float, *, posed: bool) -> Animation:
        """``character`` uses the object ``name`` for ``seconds``: it turns to it (not when it sits:
        ``posed``) and its hands go to where the object is used (:data:`ISO_USES`), type, warm
        or press there in small moves (:data:`USE_STEP`) and come back."""
        world = self.iso_place_now()
        item = world.object(name)
        use = ISO_USES[item.kind]
        x, y = self.iso_view.point(*use_point(item, world.floor_z(item.column, item.row), use, character.iso_feet))   # seated: under its seat
        here = float(character.feet()[0])
        if not posed:   # it turns to the object (straight behind or in front of it: to its side, it has no back view)
            if abs(x - here) > 0.02 * character.character_height:
                character.face("right" if x > here else "left")
            elif character.facing == "front":
                character.face(character.side_facing)
        before = character.state()
        height = character.character_height
        hands = ("left", "right") if use.style in ("type", "warm") else ("left",)
        sign = 1.0 if character.facing == "right" else -1.0

        def reach(lift: float, k: int = -1) -> dict[str, PartPose]:
            poses: dict[str, PartPose] = {}
            for j, hand in enumerate(hands):
                up = lift if k < 0 or j == k else 0.0
                ahead = 0.02 * height * (1 - j)   # the near hand a little ahead
                poses.update(character.reached_parts(hand, (x + sign * ahead, y + up * height, 0.0)))
            return poses

        arms = {part: pose for part, pose in before.parts.items() if part.startswith("arm")}
        span = max(float(seconds), 0.5)
        lead = min(USE_IN, span * 0.25) / span
        keys: list[tuple[float, dict[str, PartPose]]] = [(lead, reach(0.0))]
        step = USE_STEP[use.style] / span
        t, k = lead + step, 0
        while t < 1.0 - lead - 1e-9:
            if use.style == "type":
                keys.append((t, reach(USE_BOB, k % len(hands))))
            else:
                keys.append((t, reach(USE_BOB if k % 2 == 0 else 0.0)))
            t, k = t + step, k + 1
        keys += [(1.0 - lead, reach(0.0)), (1.0, arms)]
        return ArmMove(character, keys, run_time=span)


__all__ = ["IsoSeating", "SeatPlace", "USE_BOB", "USE_IN", "USE_STEP"]
