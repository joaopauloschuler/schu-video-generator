"""Prop beat actions (DESIGN.md §69.27): ``pick_up``, ``hold``, ``put_down``, ``give`` and
``throw`` on the characters and props of a ``stage``, ``open`` / ``close`` on its props
(an umbrella, §69.37; a book, a letter, a gift, §69.56), ``blow_away`` (the wind takes a light
prop, out of a hand too, §69.32), ``let_go`` (held balloons float away) and ``pour`` (a held
watering can pours water, §69.56).
Written against ``vidgen.api`` only, like project actions.

Who holds what is a :class:`Holdings` on the scene. A held prop is not added to its character
(a character's parts never change, §69.22): it stays a mobject of its own, drawn right after its
holder (in front of it, behind what stands in front of it; right before it when held overhead),
and an updater keeps its grip (its middle unless it has one) at the
hand (:meth:`Character.hand_point`) on every frame, so it goes along with walks, jumps and turns.
The arm reaches with :meth:`Character.reached_parts` (:class:`ArmMove`) and the prop travels with
:class:`PropMove`. The geometry and the checks are in :mod:`vidgen.cartoon.holding`.
"""

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, ClassVar, Literal

import numpy as np

from vidgen.api import *

from .acting import _Acting, _characters, is_part_target, is_posed, posture_parts
from .moving import Place, _place_x
from .stage_iso import IsoObject

#: Which hand: left (the near one, drawn in front of the body) or right.
Hand = Literal["left", "right"]


@dataclass
class _Held:
    """A prop in a hand: its holder, hand, the follow updater, the holder's arm before it took
    the prop (put back when it lets go) and the prop's standing height before it was taken."""

    character: Character
    hand: str
    updater: Any
    arm_before: dict[str, PartPose]
    standing_height: float


def holdings(scene: NarratedScene) -> Holdings:
    """The scene's :class:`Holdings` (made on first use)."""
    found = getattr(scene, "holdings", None)
    if found is None:
        found = scene.holdings = Holdings()
    return found


def _held(scene: NarratedScene) -> dict[str, _Held]:
    found = getattr(scene, "_held_props", None)
    if found is None:
        found = scene._held_props = {}
    return found


def _prop(scene: NarratedScene, name: str) -> Prop:
    found = [t.mobject for t in scene.find_targets(name) if isinstance(t.mobject, Prop)]
    if not found:
        raise VidgenError(f"scene '{scene.spec.id}': '{name}' is not a prop of the scene")
    return found[0]


def _hand(scene: NarratedScene, character: Character, hand: str | None) -> str | None:
    """``hand``, else the first free hand ``character`` has an arm for (``None``: none is;
    :class:`Holdings` then says so)."""
    if hand is not None:
        return hand
    busy = holdings(scene).hands(character.name)
    return next((h for h in HAND_ORDER if h not in busy and character.has_part(f"arm_{h}")), None)


def _arm(character: Character, hand: str) -> dict[str, PartPose]:
    """The ``hand``'s arm poses now (upper and lower part, a folded lower part too)."""
    upper = f"arm_{hand}"
    return {upper: character.pose_of(upper), f"{upper}_lower": character.pose_of(f"{upper}_lower")}


def is_overhead(prop: Prop, shape: str | None = None) -> bool:
    """Whether ``prop`` is held overhead when it shows ``shape`` (default: the shape it shows; an
    open umbrella, :data:`OVERHEAD_PROPS` in :data:`OVERHEAD_SHAPES`)."""
    return prop.kind in OVERHEAD_PROPS and (shape or prop.shape) in OVERHEAD_SHAPES


def _carry(character: Character, hand: str, overhead: bool = False) -> dict[str, PartPose]:
    """The arm poses that hold a prop in front of the shoulder (:func:`hold_point`), or
    ``overhead`` (:func:`overhead_point`)."""
    h = character.character_height
    if overhead:
        point = overhead_point(character.feet(), h, character.facing)
    else:
        point = hold_point(character.shoulder_point(hand), h, character.facing)
    return character.reached_parts(hand, [point[0], point[1], 0.0])


def crouch(character: Character, hand: str, point: Any) -> CharacterState | None:
    """The crouched state from which ``character``'s ``hand`` reaches ``point`` (screen) when it
    cannot from where it stands (:func:`crouch_drop`: the knees bend, the body lowers and bends
    forward, the feet stay); ``None``: no crouch needed, or none it can make (it sits or leans,
    or has no legs)."""
    hips = character.hip_height()
    if hips is None or is_posed(character):
        return None
    h = character.character_height
    shoulder = character.shoulder_point(hand)
    _, upper, lower = character.limb_rest(f"arm_{hand}")
    above = (float(shoulder[1]) - float(point[1])) / h
    ahead = abs(float(point[0]) - float(shoulder[0])) / h
    drop = crouch_drop(above, ahead, upper + lower, hips)
    if drop < CROUCH_MIN:
        return None
    return character.lowered(character.state(), drop, stoop=crouch_stoop(drop, hips))


def _reach_low(character: Character, hand: str, point: Any, share: float, back: dict[str, PartPose]) -> Animation:
    """The arm reaching ``point`` at ``share`` of the action and going to ``back`` at its end,
    crouching for a low point (:func:`crouch`) and rising again (from its side: a character
    facing the front turns to its side first, DESIGN.md §69.44)."""
    low = crouch(character, hand, point)
    if low is not None and character.facing == "front":
        character.face(character.side_facing)
        low = crouch(character, hand, point)
    reach = character.reached_parts(hand, point, state=low)
    if low is None:
        return ArmMove(character, [(share, reach), (1.0, back)])
    standing = posture_parts(character.state())
    return BodyMove(character, [(share, {**posture_parts(low), **reach}), (1.0, {**standing, **back})],
                    soles=character.sole_points() or None)


def _standing_height(prop: Prop, character: Character) -> float:
    """How tall ``prop`` stands next to ``character`` (at its depth)."""
    if prop.height_factor is not None:
        return prop.height_factor * character.character_height
    return float(prop.height)


def _in_hand_height(prop: Prop, character: Character, overhead: bool = False) -> float:
    """How tall ``prop`` is in ``character``'s hand (:func:`held_height`)."""
    factor = prop.height_factor if prop.height_factor is not None else prop.height / character.character_height
    return held_height(factor, character.character_height, overhead=overhead, full_size=prop.kind in FULL_SIZE_HELD)


def _standing_grip(prop: Prop, x: float, ground: float, height: float) -> list[float]:
    """Where ``prop``'s grip (its middle without one) is when it stands ``height`` tall with its
    feet at (``x``, ``ground``): the target of a :class:`PropMove` onto the ground."""
    offset = (prop.grip_point() - prop.feet()) * (height / max(float(prop.height), 1e-9))
    return [x + float(offset[0]), ground + float(offset[1])]


def _draw_beside(scene: NarratedScene, prop: Prop, character: Character, overhead: bool) -> None:
    """Draw ``prop`` right after ``character`` (in front of it, behind later ones), or right
    before it when it is held ``overhead`` (the shaft behind the head, the canopy above it) or
    rises behind the head (balloons)."""
    mobjects = getattr(scene, "mobjects", [])
    if prop not in mobjects or character not in mobjects:
        return
    mobjects.remove(prop)
    mobjects.insert(mobjects.index(character) + (0 if overhead else 1), prop)


def attach(scene: NarratedScene, prop: Prop, character: Character, hand: str, arm_before: dict[str, PartPose], standing: float) -> None:
    """Make ``prop`` follow ``character``'s ``hand`` from now on (an updater on the prop that
    keeps its grip there, :meth:`Prop.grip_point`)."""
    def follow(mob: Mobject) -> None:
        mob.shift(character.hand_point(hand) - mob.grip_point())

    detach(scene, prop)
    prop.add_updater(follow)
    prop.held_by, prop.hand = character.name, hand
    prop.keyed_feet = None
    character.holding[hand] = prop.name
    _held(scene)[prop.name] = _Held(character, hand, follow, arm_before, standing)
    _draw_beside(scene, prop, character, is_overhead(prop) or prop.kind in FULL_SIZE_HELD)   # balloons rise behind the head


def detach(scene: NarratedScene, prop: Prop) -> _Held | None:
    """Stop ``prop`` following a hand; what it was (``None``: it was not held)."""
    held = _held(scene).pop(prop.name, None)
    if held is not None:
        prop.remove_updater(held.updater)
        held.character.holding.pop(held.hand, None)
    prop.held_by = prop.hand = None
    return held


class _Handling(_Acting):
    """A prop action: its targets must be characters of a stage; ``to`` / ``prop`` name props,
    characters or places as each action says. :meth:`scene_problems` checks names; the order of
    the scene's actions (who holds what when, distances) is checked by the stage
    (:func:`holding_problems`)."""

    #: The option that names a prop (``None``: no prop option) and whether it must be given.
    prop_option: str | None = None

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = self._target_characters(scene_cls, params)[1]
        if "<prop>" not in scene_cls.target_patterns:
            return problems + [("target", f"{self.config.action} is for the characters and props of a stage")]
        props = params.prop_names()
        name = getattr(self.options, self.prop_option, None) if self.prop_option is not None else None
        if name is not None and name not in props:
            known = f"props: {', '.join(props)}" if props else "the scene has no props"
            problems.append((self.prop_option, f"'{name}' is not a prop of the scene ({known})"))
        kinds = dict(zip(props, (p.prop for p in params.stage_props())))
        if name is not None and kinds.get(name) in SCIFI_PROPS:   # a rift in space, a beam of light (§100.4)
            problems.append((self.prop_option, f"'{name}' is a {kinds[name]}: it cannot be held or carried"))
        return problems

    def _move(self, scene: NarratedScene, prop: Prop, *, leave: float, arrive: float, to: Any,
              height: float, rise: float = 0.0, turns: int = 0, lands: bool = False) -> Animation:
        """A :class:`PropMove` of ``prop``, from the hand holding it until ``leave``."""
        held = _held(scene).get(prop.name)
        follow = (lambda h=held: h.character.hand_point(h.hand)) if held is not None else None
        return PropMove(prop, to=to, follow=follow, leave=leave, arrive=arrive, height=height, rise=rise, turns=turns, lands=lands)


@action("pick_up")
class PickUp(_Handling):
    """The target character reaches for the prop ``to`` (its arm bends towards it; it crouches
    for a low one, knees bent), lifts it and
    holds it in front of it in its ``hand`` (default: a free one, the near one first); a prop
    taller than 0.4 of the character is made smaller while it is held. It holds it until a
    put_down, give or throw (walks, jumps and turns take it along). It must stand next to the
    prop: vidgen validate says where to walk_to first."""

    class Options(ActionOptions):
        to: str
        """The prop it picks up (a prop of the stage, by its name)."""
        hand: Hand | None = None
        """left (the near hand) or right; default: a free one, the left first."""

    run_time = PICK_UP_SECONDS
    prop_option = "to"
    needs = "gesture: point"

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Reach for the prop, then carry it to the hold point."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "pick_up")[:1]:
            prop = _prop(scene, self.options.to)
            hand = holdings(scene).take(character.name, prop.name, _hand(scene, character, self.options.hand))
            before, standing, overhead = _arm(character, hand), float(prop.height), is_overhead(prop)
            grip = prop.grip_point() if prop.grip is not None else prop.get_top()
            anims.append(_reach_low(character, hand, grip, REACH_SHARE, _carry(character, hand, overhead)))
            anims.append(PropMove(prop, to=lambda c=character, h=hand: c.hand_point(h), leave=REACH_SHARE,
                                  height=_in_hand_height(prop, character, overhead)))
            attach(scene, prop, character, hand, before, standing)
        return anims


@action("hold")
class Hold(_Handling):
    """The target character holds the prop ``to`` in its ``hand`` from now on without picking it
    up (a prop it has from the start; use at: 0 of the scene's first beat): the prop moves into
    its hand while the arm comes up. Held by a character waiting off stage for its enter, the prop
    waits there with it (the stage puts it beside it)."""

    class Options(ActionOptions):
        to: str
        """The prop it holds (a prop of the stage, by its name)."""
        hand: Hand | None = None
        """left (the near hand) or right; default: a free one, the left first."""

    run_time = HOLD_SECONDS
    prop_option = "to"
    needs = "gesture: point"

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Raise the arm to the hold point; the prop goes there with the hand."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "hold")[:1]:
            prop = _prop(scene, self.options.to)
            hand = holdings(scene).take(character.name, prop.name, _hand(scene, character, self.options.hand))
            before, standing, overhead = _arm(character, hand), float(prop.height), is_overhead(prop)
            anims.append(ArmMove(character, [(1.0, _carry(character, hand, overhead))]))
            anims.append(PropMove(prop, to=lambda c=character, h=hand: c.hand_point(h), height=_in_hand_height(prop, character, overhead)))
            attach(scene, prop, character, hand, before, standing)
        return anims


@action("put_down")
class PutDown(_Handling):
    """The target character puts the prop it holds (``prop``: which, when it holds two) down on
    the ground at ``to`` (a mark or an x of the stage; default: just in front of it), at its
    own depth, back to its full size, crouching when the spot is low; its arm goes back to how it
    was. The spot must be within
    its reach (vidgen validate says where to walk_to first). On an iso place ``to`` is a spot
    next to it (on the table or bench standing there: placing it); without ``to`` it drops it on
    the ground beside it."""

    class Options(ActionOptions):
        to: Place | None = None
        """Where it puts it: a mark or an x from 0 (left edge) to 1 (right edge) of the stage (on an iso place a spot next to it, on a table or bench there); default: just in front of it."""
        prop: str | None = None
        """Which prop, when it holds two."""

    run_time = PUT_DOWN_SECONDS
    prop_option = "prop"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = super().scene_problems(scene_cls, params)
        return problems + _place_problem(scene_cls, params, self.options.to)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Reach down to the spot; the prop goes from the hand onto the ground."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "put_down")[:1]:
            name, hand = holdings(scene).release(character.name, self.options.prop)
            prop = _prop(scene, name)
            prop.stage_depth = character.stage_depth   # it lands at its holder's depth (DESIGN.md §69.44)
            held = _held(scene).get(name)
            feet = character.feet()
            ground = float(feet[1])
            if getattr(scene, "on_iso", False):   # on a spot of the place, or on the ground beside it (DESIGN.md §89.10)
                prop.iso_feet = scene.iso_put_point(character, self.options.to)
                x, ground = scene.iso_view.point(*prop.iso_feet)
            elif self.options.to is not None:
                x = _place_x(scene, self.options.to)
            else:
                x = put_down_x(float(feet[0]), character.character_height, character.facing)
            height = _standing_height(prop, character)
            spot = [x, ground + height, 0.0]
            back = held.arm_before if held is not None else _arm(character, hand)
            anims.append(_reach_low(character, hand, spot, PUT_DOWN_REACH_SHARE, back))
            anims.append(self._move(scene, prop, leave=PUT_DOWN_REACH_SHARE, arrive=PUT_DOWN_LAND_SHARE,
                                    to=_standing_grip(prop, x, ground, height), height=height))
            detach(scene, prop)
            if getattr(scene, "on_iso", False):
                scene.iso_put_down(prop, ground)
        return anims


@action("give")
class Give(_Handling):
    """The target character hands the prop it holds (``prop``: which, when it holds two) to the
    character ``to``, who takes it in its ``hand``: both reach towards each other (each turns to
    face the other first) and the prop goes from one hand to the other. They must stand next to
    each other (vidgen validate says where to walk_to first)."""

    class Options(ActionOptions):
        to: str
        """The character it gives the prop to (on the stage, next to it)."""
        prop: str | None = None
        """Which prop, when it holds two."""
        hand: Hand | None = None
        """The receiver's hand: left or right; default: a free one, the left first."""

    run_time = GIVE_SECONDS
    prop_option = "prop"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = super().scene_problems(scene_cls, params)
        names = [c.name for c in getattr(params, "characters", [])]
        if self.options.to not in names:
            known = ", ".join(names) or "none"
            problems.append(("to", f"'{self.options.to}' is not a character on the stage (characters: {known})"))
        elif self.options.to in self.config.targets():
            problems.append(("to", f"{self.options.to} cannot give a prop to itself"))
        return problems

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Giver and receiver reach to the point between their hands; the prop changes hands."""
        anims: list[Animation] = []
        found = [t.mobject for t in scene.find_targets(self.options.to) if isinstance(t.mobject, Character)]
        for giver in _characters(scene, targets, "give")[:1]:
            if not found:
                break
            receiver = found[0]
            name, from_hand, to_hand = holdings(scene).give(giver.name, receiver.name, self.options.prop, _hand(scene, receiver, self.options.hand))
            prop = _prop(scene, name)
            towards = 1.0 if receiver.feet()[0] >= giver.feet()[0] else -1.0
            for who, facing in ((giver, "right" if towards > 0 else "left"), (receiver, "left" if towards > 0 else "right")):
                if not is_posed(who):   # one that sits or leans keeps its facing
                    who.face(facing)
            held = _held(scene).get(name)
            meet = (np.array(hold_point(giver.shoulder_point(from_hand), giver.character_height, giver.facing))
                    + np.array(hold_point(receiver.shoulder_point(to_hand), receiver.character_height, receiver.facing))) / 2
            point = [float(meet[0]), float(meet[1]), 0.0]
            back = held.arm_before if held is not None else _arm(giver, from_hand)
            receiver_before = _arm(receiver, to_hand)
            anims.append(ArmMove(giver, [(REACH_SHARE, giver.reached_parts(from_hand, point)), (1.0, back)]))
            overhead = is_overhead(prop)
            anims.append(ArmMove(receiver, [(REACH_SHARE, receiver.reached_parts(to_hand, point)), (1.0, _carry(receiver, to_hand, overhead))]))
            anims.append(self._move(scene, prop, leave=REACH_SHARE, arrive=1.0, to=lambda r=receiver, h=to_hand: r.hand_point(h),
                                    height=_in_hand_height(prop, receiver, overhead)))
            standing = held.standing_height if held is not None else float(prop.height)
            attach(scene, prop, receiver, to_hand, receiver_before, standing)
        return anims


@action("throw")
class Throw(_Handling):
    """The target character throws the prop it holds (``prop``: which, when it holds two) to
    ``to`` (a mark or an x of the stage): its arm winds up and swings, the prop flies an arc
    ``height`` of the character's heights above the higher end, spinning ``spin`` whole turns,
    and lands on the ground there (at the thrower's depth, at its full size) with a thud."""

    class Options(ActionOptions):
        to: Place
        """Where it lands: a mark or an x from 0 (left edge) to 1 (right edge) of the stage."""
        prop: str | None = None
        """Which prop, when it holds two."""
        height: float = Field(THROW_HEIGHT, ge=0.05, le=3.0)
        """How high the arc rises above the higher end, in the thrower's heights."""
        spin: int = Field(THROW_SPIN, ge=0, le=6)
        """Whole turns the prop spins in the air (0: none)."""

    run_time = 1.2
    prop_option = "prop"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = super().scene_problems(scene_cls, params)
        if getattr(params, "iso", None) is not None:
            return problems + [("action", "throw is not for an iso place (things do not fly across it); put_down the prop "
                                          "(to: a spot next to it) or give it to someone")]
        return problems + _place_problem(scene_cls, params, self.options.to)

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        x = _place_x(scene, self.options.to)
        times = [throw_seconds(x - float(c.feet()[0])) for c in _characters(scene, targets, "throw")[:1]]
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Wind up, swing, let go; the prop flies and lands."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "throw")[:1]:
            name, hand = holdings(scene).release(character.name, self.options.prop)
            prop = _prop(scene, name)
            prop.stage_depth = character.stage_depth   # it lands at its holder's depth (DESIGN.md §69.44)
            held = _held(scene).get(name)
            feet = character.feet()
            x = _place_x(scene, self.options.to)
            towards = 1.0 if x >= feet[0] else -1.0
            if not is_posed(character):
                character.face("right" if towards > 0 else "left")
            h, shoulder = character.character_height, character.shoulder_point(hand)
            release = throw_release_share(x - float(feet[0]))
            wind = THROW_WIND_UP / (THROW_WIND_UP + THROW_SWING) * release
            behind = [shoulder[0] - towards * 0.15 * h, shoulder[1] + 0.12 * h, 0.0]
            ahead = [shoulder[0] + towards * 0.2 * h, shoulder[1] + 0.15 * h, 0.0]
            back = held.arm_before if held is not None else _arm(character, hand)
            settle = release + (1.0 - release) * 0.4
            anims.append(ArmMove(character, [
                (wind, character.reached_parts(hand, behind)), (release, character.reached_parts(hand, ahead)), (settle, back),
            ]))
            height = _standing_height(prop, character)
            anims.append(self._move(scene, prop, leave=release, arrive=1.0, to=_standing_grip(prop, x, float(feet[1]), height), height=height,
                                    rise=self.options.height * h, turns=self.options.spin, lands=True))
            detach(scene, prop)
        return anims


class _Reshape(Action):
    """``open`` / ``close``: the target props (by name) switch to the action's shape
    (:data:`PROP_SHAPES`); a held one is lifted overhead or brought back to the hold point by its
    holder's arm, changing size in the hand (DESIGN.md §69.37)."""

    #: The shape the prop shows afterwards.
    shape: ClassVar[str]
    run_time = RESHAPE_SECONDS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        action = self.config.action
        if "<prop>" not in scene_cls.target_patterns:
            return [("target", f"{action} is for the props of a stage")]
        kinds = dict(zip(params.prop_names(), (p.prop for p in params.stage_props())))
        able = sorted(kind for kind, shapes in PROP_SHAPES.items() if self.shape in shapes)
        objects = params.iso.object_kinds() if getattr(params, "iso", None) is not None else {}   # an iso place's (§89.10)
        problems: list[tuple[str, str]] = []
        for pattern in self.config.targets():
            for name in [n for n in scene_cls.target_names(params) if fnmatchcase(n, pattern) and not is_part_target(n)]:
                if name in objects:
                    if objects[name] not in OPENING_KINDS:
                        problems.append(("target", f"'{name}' (a {objects[name]}) cannot {action}; on an iso place a house (its door), "
                                         "a door of a room's wall (door_1...), flowers (they bloom, or close to buds), a laptop, a lab_fridge and an airlock can"))
                elif name not in kinds:
                    problems.append(("target", f"'{name}' is not a prop; {action} acts on props (- {action}: <prop>)"))
                elif self.shape not in PROP_SHAPES.get(kinds[name] or "", ()):
                    problems.append(("target", f"'{name}' cannot {action} (props that can: {', '.join(able)})"))
        return problems

    def _on_level(self, scene: NarratedScene, prop: Prop) -> bool:
        """On a platform level, the rules' record (and check) of a door opening or closing
        (DESIGN.md §86.8); nothing elsewhere. Whether a key unlocked it (foley, §86.9)."""
        return False

    def _opener(self, scene: NarratedScene, prop: Prop) -> list[Animation]:
        """The animations of whoever opens or closes ``prop`` (none)."""
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Switch each target prop's shape half-way; a held one's arm moves to where it holds
        it in its new shape (overhead or in front), the prop at the hand."""
        anims: list[Animation] = []
        seconds = float(self.config.run_time or self.run_time)
        for target in [t for t in targets if isinstance(t.mobject, IsoObject)]:   # an iso place's house, door, flowers (§89.10)
            scene.iso_change(target.name, float(scene.renderer.time) + seconds / 4, seconds / 2, open=self.shape == "open")
        for prop in [t.mobject for t in targets if isinstance(t.mobject, Prop)]:
            if self.shape not in prop.shapes or prop.shape == self.shape:
                continue
            unlocks = getattr(scene, "on_level", False) and prop.kind == "door" and self._on_level(scene, prop)
            held = _held(scene).get(prop.name)
            if held is None:
                anims += self._opener(scene, prop)
                reshape = PropReshape(prop, self.shape, at=RESHAPE_SHARE)
                reshape.unlocks = unlocks   # a locked door opened with its key: foley clicks the lock (DESIGN.md §86.9)
                anims.append(reshape)
                continue
            character, hand, overhead = held.character, held.hand, is_overhead(prop, self.shape)
            anims.append(ArmMove(character, [(1.0, _carry(character, hand, overhead))]))
            anims.append(PropReshape(prop, self.shape, at=RESHAPE_SHARE, height=_in_hand_height(prop, character, overhead),
                                     follow=lambda c=character, h=hand: c.hand_point(h)))
            _draw_beside(scene, prop, character, overhead)
        return anims


@action("open")
class Open(_Reshape):
    """The target prop opens (an umbrella or a door: `- open: umbrella`). Held, it goes up overhead, the
    holder's arm raised; standing, it opens where it stands; ``by``: that character reaches for it
    as it opens. A prop can also start open (`open: true` in the stage's props). On a platform
    level a closed door is in the way of walks and jumps, and a locked one (``level.locks``) opens
    only ``by`` a character holding its key and standing next to it (DESIGN.md §86.8)."""

    class Options(ActionOptions):
        by: str | None = None
        """A character who opens it: it reaches for it (with the hand holding the key of a locked door); on a level it must stand next to it."""

    shape = "open"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = super().scene_problems(scene_cls, params)
        by = self.options.by
        if by is not None and by not in [c.name for c in getattr(params, "characters", [])]:
            problems.append(("by", f"'{by}' is not a character on the stage"))
        return problems

    def alters(self, scene: NarratedScene) -> list[Mobject]:
        """The character opening it (its arm reaches)."""
        by = getattr(scene, "cast", {}).get(self.options.by) if self.options.by is not None else None
        return [by] if by is not None else []

    def _on_level(self, scene: NarratedScene, prop: Prop) -> bool:
        return scene.level_open(prop.name, self.options.by)

    def _opener(self, scene: NarratedScene, prop: Prop) -> list[Animation]:
        """``by`` turns to the door and reaches for its edge (with the hand holding the door's key
        when it holds one), then lowers its arm back."""
        by = self.options.by
        if by is None or by not in getattr(scene, "cast", {}):
            return []
        character = scene.cast[by]
        door_x, feet_x = float(prop.feet()[0]), float(character.feet()[0])
        if abs(door_x - feet_x) > 1e-6:
            character.face("right" if door_x > feet_x else "left")
        state = getattr(scene, "level_state", None)
        door = state.item(prop.name) if state is not None else None
        key = scene.props.get(door.key) if door is not None and door.key else None
        hand = (key.hand if key is not None and key.held_by == by else None) or _hand(scene, character, None)
        if hand is None:
            return []
        edge = door_x - (1 if door_x > feet_x else -1) * float(prop.width) / 2
        point = [edge, float(prop.feet()[1]) + 0.45 * float(prop.height), 0.0]
        return [_reach_low(character, hand, point, RESHAPE_SHARE, _arm(character, hand))]


@action("close")
class Close(_Reshape):
    """The target prop closes (an umbrella or a door: `- close: door`). Held, it comes down to the
    holder's hand in front of it; standing, it closes where it stands (on a platform level a door
    is in the way again)."""

    shape = "closed"

    def _on_level(self, scene: NarratedScene, prop: Prop) -> bool:
        scene.level_close(prop.name)
        return False


#: A prop blown off stage ends this many frame heights above where it started (up and away), and
#: its path's arc rises at most ``BLOW_RISE`` frame heights (less over a short way: ``BLOW_RISE_SHARE``
#: of the distance).
BLOW_AWAY_UP = 0.2
BLOW_RISE = 0.12
BLOW_RISE_SHARE = 0.35
#: Share of a ``blow_away`` by which the holder's empty arm is back down.
BLOW_ARM_SHARE = 0.35


@action("blow_away")
class BlowAway(Action):
    """The wind blows the target prop away (`- blow_away: napkin`): it tumbles along a gusty
    path, out of a holder's hand too, downwind and off the stage, or to `to` (a mark or an x of
    the stage), where it lands upright at its full size. Light props only (napkin, umbrella,
    ball, cup, basket, box, letter, balloons, or an SVG prop); faster in a stronger wind. Without `to` the stage's
    wind must blow then (vidgen validate checks); a prop blown off stage is gone for the scene."""

    class Options(ActionOptions):
        to: Place | None = None
        """Where it lands: a mark or an x from 0 (left edge) to 1 (right edge) of the stage; default: off the stage, downwind."""

    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """Targets are props light enough to blow away; ``to`` a place of the stage."""
        if "<prop>" not in scene_cls.target_patterns:
            return [("target", "blow_away is for the props of a stage")]
        if getattr(params, "iso", None) is not None:
            return [("action", "blow_away is not for an iso place (no wind there yet); hide an object, or put_down a prop")]
        kinds = dict(zip(params.prop_names(), (p.prop for p in params.stage_props())))
        light = ", ".join(sorted(LIGHT_PROPS))
        problems: list[tuple[str, str]] = []
        for pattern in self.config.targets():
            for name in [n for n in scene_cls.target_names(params) if fnmatchcase(n, pattern) and not is_part_target(n)]:
                if name not in kinds:
                    problems.append(("target", f"'{name}' is not a prop; blow_away acts on props (- blow_away: <prop>)"))
                elif kinds[name] is not None and kinds[name] not in LIGHT_PROPS:
                    problems.append(("target", f"'{name}' ({kinds[name]}) is too heavy to blow away (props that can: {light}, or an svg prop)"))
        return problems + _place_problem(scene_cls, params, self.options.to)

    def _props(self, targets: list[Target]) -> list[Prop]:
        return [t.mobject for t in targets if isinstance(t.mobject, Prop)]

    def _level(self, scene: NarratedScene) -> float:
        """The stage's signed wind level now (0: calm)."""
        blowing = getattr(scene, "blowing", None)
        return blowing.wind.level(float(scene.renderer.time)) if blowing is not None else 0.0

    def _end(self, scene: NarratedScene, prop: Prop, height: float) -> list[float]:
        """Where its grip ends (screen): standing at ``to``, else up and off the stage downwind."""
        held = _held(scene).get(prop.name)
        if self.options.to is not None:
            x = _place_x(scene, self.options.to)
            ground = float(held.character.feet()[1]) if held is not None else getattr(scene, "grounds", {}).get(prop.name, float(prop.feet()[1]))
            return _standing_grip(prop, x, ground, height)
        left, right = scene.camera_bounds()[:2]
        margin = max(float(prop.width), float(prop.height), height) + 0.3
        x = right + margin if self._level(scene) >= 0.0 else left - margin
        return [x, float(prop.grip_point()[1]) + BLOW_AWAY_UP * scene.frame_height]

    def _height(self, scene: NarratedScene, prop: Prop) -> float:
        """How tall it ends: its standing height (a held one grows back to it)."""
        held = _held(scene).get(prop.name)
        return _standing_height(prop, held.character) if held is not None else float(prop.height)

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """By the longest way and the wind now (:func:`blow_seconds`)."""
        level = self._level(scene)
        times = [blow_seconds(self._end(scene, p, self._height(scene, p))[0] - float(p.grip_point()[0]), level) for p in self._props(targets)]
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Each prop leaves the hand holding it (that arm goes back down) and tumbles away."""
        anims: list[Animation] = []
        for prop in self._props(targets):
            height = self._height(scene, prop)
            end = self._end(scene, prop, height)
            start = prop.grip_point()
            rise = min(BLOW_RISE * scene.frame_height, BLOW_RISE_SHARE * abs(end[0] - float(start[0])))
            seed = wind_seed(f"{scene.spec.id}:{prop.name}")
            held = _held(scene).get(prop.name)
            follow = None
            if held is not None:
                holdings(scene).drop(prop.name)
                anims.append(ArmMove(held.character, [(BLOW_ARM_SHARE, held.arm_before)]))
                follow = (lambda h=held: h.character.hand_point(h.hand))
            anims.append(PropMove(prop, to=end, follow=follow, height=height,
                                  path=lambda u, a, b, rise=rise, seed=seed: blown_point(u, a, b, rise=rise, seed=seed)))
            detach(scene, prop)
        return anims


def _kind_problems(params: Any, name: str | None, kinds: frozenset[str], verb: str) -> list[tuple[str, str]]:
    """A ``prop`` option naming a prop whose kind is not one of ``kinds`` (which ``verb``)."""
    found = dict(zip(params.prop_names(), (p.prop for p in params.stage_props())))
    if name is None or name not in found or found[name] in kinds:
        return []
    return [("prop", f"'{name}' ({found[name] or 'an svg prop'}) does not {verb} (props that do: {', '.join(sorted(kinds))})")]


#: Share of a ``let_go`` by which the empty arm is back down.
LET_GO_ARM_SHARE = 0.3


@action("let_go")
class LetGo(_Handling):
    """The target character lets go of the balloons it holds (`- let_go: kit`; ``prop``: which,
    when it holds two): they float up out of the frame, swaying, drifting with the stage's wind,
    and are gone for the scene; its arm goes back down. Only props that float (balloons):
    put_down the others."""

    class Options(ActionOptions):
        prop: str | None = None
        """Which prop, when it holds two."""

    run_time = 3.0
    prop_option = "prop"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = super().scene_problems(scene_cls, params)
        return problems + _kind_problems(params, self.options.prop, FLOATING_PROPS, "float away")

    @staticmethod
    def _end(scene: NarratedScene, prop: Prop) -> tuple[float, float]:
        """Where ``prop``'s grip ends: above the stage, downwind (:func:`float_end`)."""
        start = prop.grip_point()
        top = scene.camera_bounds()[3] + float(prop.height) + 0.3
        blowing = getattr(scene, "blowing", None)
        force = felt_force(blowing.wind.level(float(scene.renderer.time))) if blowing is not None else 0.0
        return float_end((float(start[0]), float(start[1])), top, force)

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """By how far the balloons rise (:func:`float_seconds`)."""
        for character in _characters(scene, targets, "let_go")[:1]:
            try:
                name, _ = holdings(scene).held_prop(character.name, self.options.prop)
            except HoldingError:
                return None
            prop = _prop(scene, name)
            return float_seconds(self._end(scene, prop)[1] - float(prop.grip_point()[1]))
        return None

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The hand opens, the arm comes down, the balloons float away."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "let_go")[:1]:
            name, hand = holdings(scene).release(character.name, self.options.prop)
            prop = _prop(scene, name)
            end = self._end(scene, prop)
            held = _held(scene).get(name)
            back = held.arm_before if held is not None else _arm(character, hand)
            anims.append(ArmMove(character, [(LET_GO_ARM_SHARE, back)]))
            seed = wind_seed(f"{scene.spec.id}:{name}:let_go")
            anims.append(PropMove(prop, to=list(end), path=lambda u, a, b, seed=seed: float_point(u, a, b, seed=seed)))
            detach(scene, prop)
        return anims


@action("pour")
class Pour(_Handling):
    """The target character pours with the watering can it holds (`- pour: kit`; ``prop``:
    which, when it holds two): the can tilts forward at its hand, water drops leave the spout and
    fall to the ground in front of it, then the can comes back up. Only props that pour (a
    watering_can)."""

    class Options(ActionOptions):
        prop: str | None = None
        """Which prop, when it holds two."""

    run_time = POUR_SECONDS
    prop_option = "prop"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = super().scene_problems(scene_cls, params)
        return problems + _kind_problems(params, self.options.prop, POURING_PROPS, "pour")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Tilt the can at the hand; water runs from its spout to the ground."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "pour")[:1]:
            name, hand = holdings(scene).held_prop(character.name, self.options.prop)
            prop = _prop(scene, name)
            if prop.kind not in POURING_PROPS:
                raise VidgenError(f"scene '{scene.spec.id}': '{name}' does not pour (props that do: {', '.join(sorted(POURING_PROPS))})")
            drops = WaterDrops(name=f"{name}_water")
            mark_lit(drops)
            mobjects = scene.mobjects
            mobjects.insert(mobjects.index(prop) + 1 if prop in mobjects else len(mobjects), drops)
            spout = (lambda p=prop: p.prop_point(*WATERING_SPOUT))
            way = 1.0 if float(spout()[0]) >= float(prop.grip_point()[0]) else -1.0
            if character.facing in ("left", "right") and way != (1.0 if character.facing == "right" else -1.0):
                # held props are not mirrored with their holder: turn the can round in the hand so it pours ahead
                prop.flip(np.array([0.0, 1.0, 0.0]), about_point=prop.grip_point())
                prop.facing, way = character.facing, -way
            follow = (lambda c=character, h=hand: c.hand_point(h))
            anims.append(Pouring(prop, follow=follow, spout=spout))
            anims.append(WaterFlow(drops, spout=spout, direction=lambda w=way: w, ground=float(character.feet()[1]),
                                   height=character.character_height, seed=wind_seed(f"{scene.spec.id}:{name}:pour")))
        return anims


def _place_problem(scene_cls: type[NarratedScene], params: Any, place: Any) -> list[tuple[str, str]]:
    if place is None:
        return []
    try:
        scene_cls.camera_place(params, place)
    except ValueError as exc:
        return [("to", str(exc))]
    return []
