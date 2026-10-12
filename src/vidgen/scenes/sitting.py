"""Sitting and leaning beat actions (DESIGN.md §69.28): ``sit_on``, ``lean_on`` and ``stand_up``
on the characters and props of a ``stage``. Written against ``vidgen.api`` only, like project
actions.

Who sits or leans on what is a :class:`Postures` on the scene. Sitting lowers the body until it
rests on the prop's seat line and bends the hips and knees with the two-bone solver (the feet
planted on the ground in front, or hanging from a high seat: :meth:`Character.seated`); leaning
turns the body back against the prop's edge with the feet forward (:meth:`Character.leaning`).
:class:`BodyMove` plays both, and ``stand_up`` brings back the body and legs as they were. The
pure parts (seats, lean edges, the checks) are in :mod:`vidgen.cartoon.seating`.
"""

from typing import Any

from vidgen.api import *

from .acting import _Acting, _characters, posture_parts
from .handling import _prop


def postures(scene: NarratedScene) -> Postures:
    """The scene's :class:`Postures` (made on first use)."""
    found = getattr(scene, "postures", None)
    if found is None:
        found = scene.postures = Postures()
    return found


def _posed(scene: NarratedScene) -> dict[str, dict[str, PartPose]]:
    """The body's and legs' poses of each character that sits or leans, from before it did."""
    found = getattr(scene, "_posed", None)
    if found is None:
        found = scene._posed = {}
    return found


def _stage_prop(params: Any, name: str) -> Any:
    return dict(zip(params.prop_names(), params.stage_props())).get(name)


def _svg_points(svg: str) -> tuple[Any, Any]:
    """The seat and lean edges an SVG prop of the active project gives (none when it cannot be read:
    ``vidgen validate`` reports the file itself)."""
    try:
        return read_svg_seat_and_lean(current_project().asset(svg), where=svg)
    except VidgenError:
        return None, None


class _Posture(_Acting):
    """``sit_on`` or ``lean_on``: its target is a character of a stage, ``to`` a prop with a seat
    (``what`` = ``seat``) or lean edges (``lean``)."""

    what = "seat"
    kinds: dict[str, Any] = PROP_SEATS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = self._target_characters(scene_cls, params)[1]
        if "<prop>" not in scene_cls.target_patterns:
            return problems + [("target", f"{self.config.action} is for the characters and props of a stage")]
        props = params.prop_names()
        name = self.options.to
        entry = _stage_prop(params, name)
        if entry is None:
            known = f"props: {', '.join(props)}" if props else "the scene has no props"
            return problems + [("to", f"'{name}' is not a prop of the scene ({known})")]
        if entry.prop is not None:
            has = entry.prop in self.kinds
        else:
            seat, lean = _svg_points(entry.svg)
            has = (seat if self.what == "seat" else lean) is not None
        if not has:
            attribute = "data-seat" if self.what == "seat" else "data-lean"
            kinds = ", ".join(self.kinds)
            problems.append(("to", f"'{name}' has no {self.what} ({self.what}s: {kinds}, or an SVG prop with {attribute})"))
        return problems


@action("sit_on")
class SitOn(_Posture):
    """The target character sits down on the prop ``to`` (a chair, a rock, a box, or an SVG prop
    with data-seat): it moves onto the seat, its body lowers onto the seat line and its hips and
    knees bend, the feet on the ground in front (hanging from a high seat). On a chair it faces the
    way the chair faces. It stays seated (it keeps its facing; looks turn only its head) until a
    stand_up; it cannot walk, jump or turn before. It must be next to the prop (vidgen validate
    says where to walk_to first)."""

    class Options(ActionOptions):
        to: str
        """The prop it sits on (a prop of the stage with a seat, by its name)."""

    run_time = SIT_SECONDS

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Move onto the seat, lower the body onto it, bend the legs."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "sit_on")[:1]:
            prop = _prop(scene, self.options.to)
            seat = prop.seat_point()
            if seat is None:
                raise VidgenError(f"scene '{scene.spec.id}': '{prop.name}' has no seat")
            postures(scene).sit(character.name, prop.name)
            before = character.state()
            seated = character.seated(before, float(seat[1] - character.feet()[1]) / character.character_height)
            facing = prop.facing if prop.kind in SEAT_BACKS else character.facing
            anims.append(BodyMove(character, [(1.0, posture_parts(seated))], x=float(seat[0]), facing=facing,
                                  soles=character.sole_points(seated) or None))
            _posed(scene)[character.name] = posture_parts(before)
            character.sitting_on = prop.name
        return anims


@action("lean_on")
class LeanOn(_Posture):
    """The target character leans its back on the prop ``to`` (a tree, a door, a sign, a lamp, a
    house, or an SVG prop with data-lean), on the side of it where it stands: it turns its back to
    the prop, steps against its edge and leans back, the feet forward. It stays so (it keeps its
    facing; looks turn only its head) until a stand_up; it cannot walk, jump or turn before. It
    must be next to the prop (vidgen validate says where to walk_to first)."""

    class Options(ActionOptions):
        to: str
        """The prop it leans on (a prop of the stage with lean edges, by its name)."""

    run_time = LEAN_SECONDS
    what = "lean"
    kinds = PROP_LEANS

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Turn the back to the prop, step against its edge, lean back."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "lean_on")[:1]:
            prop = _prop(scene, self.options.to)
            edges = prop.lean_edges()
            if edges is None:
                raise VidgenError(f"scene '{scene.spec.id}': '{prop.name}' has nothing to lean on")
            postures(scene).lean(character.name, prop.name)
            on_left = float(character.feet()[0]) < float(prop.feet()[0])
            facing = "left" if on_left else "right"   # its back to the prop
            before = character.state()
            leant = character.leaning(before)
            back = character.part_box("body", leant)[0]
            sign = 1.0 if facing == "right" else -1.0
            x = (edges[0] if on_left else edges[1]) - sign * back * character.character_height
            anims.append(BodyMove(character, [(1.0, posture_parts(leant))], x=x, facing=facing,
                                  soles=character.sole_points(leant) or None))
            _posed(scene)[character.name] = posture_parts(before)
            character.leaning_on = prop.name
        return anims


@action("stand_up")
class StandUp(_Acting):
    """The target character stands up from where it sits or leans (after a sit_on or a lean_on),
    over its feet: its body and legs go back to how they were before."""

    class Options(ActionOptions):
        pass

    run_time = STAND_UP_SECONDS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Each character that sits or leans stands up over its feet."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "stand_up"):
            before = _posed(scene).pop(character.name, None)
            if before is None:
                continue
            postures(scene).stand(character.name)
            now = character.state()
            soles = character.sole_points()
            sign = 1.0 if character.facing == "right" else -1.0
            x = None
            if soles:
                middle = sum(x for x, _ in soles.values()) / len(soles)
                x = float(character.feet()[0]) + sign * middle * character.character_height
            standing = CharacterState(now.facing, {**now.parts, **before})
            anims.append(BodyMove(character, [(1.0, before)], x=x, soles=character.sole_points(standing) or None))
            character.sitting_on = character.leaning_on = None
        return anims
