"""Sitting and leaning beat actions (DESIGN.md §69.28): ``sit_on``, ``lean_on`` and ``stand_up``
on the characters and props of a ``stage``; on an iso place also on its objects, with ``lie_on``
(a bed) and ``use`` (§105.2: the stage's ``iso_seat``, ``iso_bed``, ``iso_use``). Written against
``vidgen.api`` only, like project actions.

Who sits or leans on what is a :class:`Postures` on the scene. Sitting lowers the body until it
rests on the prop's seat line and bends the hips and knees with the two-bone solver (the feet
planted on the ground in front, or hanging from a high seat: :meth:`Character.seated`); leaning
turns the body back against the prop's edge with the feet forward (:meth:`Character.leaning`).
:class:`BodyMove` plays both, and ``stand_up`` brings back the body and legs as they were. The
pure parts (seats, lean edges, the checks) are in :mod:`vidgen.cartoon.seating`.
"""

import difflib
from typing import Any

from vidgen.api import *

from .acting import _Acting, _characters, is_posed, posture_parts
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


def _iso_object_problems(params: Any, name: str, table: dict[str, Any], verb: str) -> list[tuple[str, str]]:
    """``name`` must be an object of the stage's iso place one can ``verb`` (its kind in ``table``)."""
    objects = params.iso.object_kinds()
    fitting = sorted(n for n, kind in objects.items() if kind in table)
    known = ", ".join(fitting) or f"none: add one to iso.objects ({kinds_words(table)})"
    if name not in objects:
        close = difflib.get_close_matches(name, fitting or list(objects), n=1, cutoff=0.6)
        hint = f"; did you mean {close[0]}?" if close else ""
        return [("to", f"'{name}' is not an object of the place{hint} (objects to {verb}: {known})")]
    if objects[name] not in table:
        kind = objects[name]
        return [("to", f"'{name}' is a {kind}: nothing to {verb} {object_uses_hint(kind)}; the place's objects to {verb}: {known}")]
    return []


def _posture_error(scene: NarratedScene, exc: PostureError) -> VidgenError:
    return VidgenError(f"scene '{scene.spec.id}': {exc}")


class _Posture(_Acting):
    """``sit_on`` or ``lean_on``: its target is a character of a stage, ``to`` a prop with a seat
    (``what`` = ``seat``) or lean edges (``lean``)."""

    what = "seat"
    kinds: dict[str, Any] = PROP_SEATS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = self._target_characters(scene_cls, params)[1]
        if self.what == "seat" and getattr(params, "iso", None) is not None and self.options.to not in params.prop_names():
            return problems + _iso_object_problems(params, self.options.to, ISO_SEATS, "sit on")   # an object of the place (§105.2)
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
    """The target character sits down on the prop ``to`` (a chair, a rock, a box, a sofa, an
    armchair, a bed, a desk's chair, or an SVG prop with data-seat): it moves onto the seat (on a
    sofa or a bed, the free place nearest to it; two sit side by side), its body lowers onto the
    seat line and its hips and knees bend, the feet on the ground in front (hanging from a high
    seat). On a chair or at a desk it faces the way the prop faces. It stays seated (it keeps its facing; looks turn only its head) until a
    stand_up; it cannot walk, jump or turn before. It must be next to the prop (vidgen validate
    says where to walk_to first)."""

    class Options(ActionOptions):
        to: str
        """The prop it sits on (a prop of the stage with a seat, by its name)."""

    run_time = SIT_SECONDS

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Move onto the seat, lower the body onto it, bend the legs."""
        anims: list[Animation] = []
        if getattr(scene, "on_iso", False) and self.options.to not in getattr(scene, "props", {}):
            return [self._iso_sit(scene, character) for character in _characters(scene, targets, "sit_on")[:1]]
        for character in _characters(scene, targets, "sit_on")[:1]:
            prop = _prop(scene, self.options.to)
            if prop.seat is None:
                raise VidgenError(f"scene '{scene.spec.id}': '{prop.name}' has no seat")
            here = float(character.feet()[0])
            nearest = sorted(range(len(prop.seat_places)), key=lambda k: abs(float(prop.seat_point(k)[0]) - here))
            place = postures(scene).sit(character.name, prop.name, max(len(prop.seat_places), 1), nearest)
            seat = prop.seat_point(place if prop.seat_places else None)
            before = character.state()
            seated = character.seated(before, float(seat[1] - character.feet()[1]) / character.character_height)
            facing = prop.facing if prop.kind in SEAT_BACKS else character.side_facing   # sitting is drawn from the side (§69.44)
            anims.append(BodyMove(character, [(1.0, posture_parts(seated))], x=float(seat[0]), facing=facing,
                                  soles=character.sole_points(seated) or None))
            _posed(scene)[character.name] = posture_parts(before)
            character.sitting_on = prop.name
        return anims

    def _iso_sit(self, scene: NarratedScene, character: Character) -> Animation:
        """Sit down on a seat of an object of the iso place (DESIGN.md §105.2): the free one
        nearest the feet, facing the way it faces, the feet under it."""
        world = scene.iso_place_now()  # type: ignore[attr-defined]
        item = world.object(self.options.to)
        order = seat_order(item, world.floor_z(item.column, item.row), character.iso_feet)
        try:
            place = postures(scene).sit(character.name, item.name, len(ISO_SEATS[item.kind]), order)
        except PostureError as exc:
            raise _posture_error(scene, exc) from None
        seat = scene.iso_seat(item.name, place)  # type: ignore[attr-defined]
        before = character.state()
        seated = character.seated(CharacterState(seat.facing, before.parts), scene.iso_view.height(seat.lift) / character.character_height)  # type: ignore[attr-defined]
        _posed(scene)[character.name] = posture_parts(before)
        character.sitting_on = item.name
        return scene.iso_seat_move(character, [(1.0, posture_parts(seated))], seat, facing=seat.facing,  # type: ignore[attr-defined]
                                   soles=character.sole_points(seated) or None)


@action("lie_on")
class LieOn(_Acting):
    """The target character lies down in the bed ``to`` of an iso place: it climbs in on its back,
    its head on the pillow, the blanket over it (drawn a little smaller: a cartoon bed is short). It
    stays so (looks turn only its head; it can talk and make faces) until a stand_up. It must
    stand next to the bed (vidgen validate says where to walk_to first); nobody else sits or lies
    on it meanwhile."""

    class Options(ActionOptions):
        to: str
        """The bed it lies in (an object of the place, by its name)."""

    run_time = LIE_SECONDS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = self._target_characters(scene_cls, params)[1]
        if getattr(params, "iso", None) is None:
            return problems + [("action", "lie_on is for a bed of an iso place (params.iso); on a plain stage sit_on a bed")]
        return problems + _iso_object_problems(params, self.options.to, ISO_BEDS, "lie on")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Turn onto the back along the bed, the legs under the blanket."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "lie_on")[:1]:
            try:
                postures(scene).lie(character.name, self.options.to)
            except PostureError as exc:
                raise _posture_error(scene, exc) from None
            bed = scene.iso_bed(self.options.to, character)  # type: ignore[attr-defined]
            before = character.state()
            lying = scene.iso_lying(character, CharacterState(bed.facing, before.parts), bed.lift)  # type: ignore[attr-defined]
            _posed(scene)[character.name] = posture_parts(before)
            character.sitting_on = self.options.to
            anims.append(scene.iso_seat_move(character, [(1.0, posture_parts(lying))], bed, facing=bed.facing, scale=LIE_SCALE,  # type: ignore[attr-defined]
                                             run_time=LIE_SECONDS))
        return anims


@action("use")
class Use(_Acting):
    """The target character uses the object ``to`` of an iso place for ``run_time`` seconds
    (default 3): it turns to it and its hands go there: it types at a laptop, a desk's PC, a
    console, a kiosk, a till or a piano; warms its hands at a campfire or a fireplace; reaches for
    a book on a shelf; presses, pours or turns at a stove, a sink, a coffee or vending machine, a
    microscope, a globe... Then its hands come back. Sitting (a chair at the desk), it keeps its
    seat and facing. It must be next to the object, or sit next to it (vidgen validate says where
    to walk_to first)."""

    class Options(ActionOptions):
        to: str
        """The object it uses (an object of the place, by its name)."""

    run_time = USE_SECONDS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = self._target_characters(scene_cls, params)[1]
        if getattr(params, "iso", None) is None:
            return problems + [("action", "use is for the objects of an iso place (params.iso)")]
        return problems + _iso_object_problems(params, self.options.to, ISO_USES, "use")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The hands go to the object, work there and come back."""
        seconds = self.config.run_time if self.config.run_time is not None else USE_SECONDS
        return [scene.iso_use(character, self.options.to, seconds, posed=is_posed(character))  # type: ignore[attr-defined]
                for character in _characters(scene, targets, "use")]


@action("lean_on")
class LeanOn(_Posture):
    """The target character leans its back on the prop ``to`` (a tree, a door, a sign, a lamp, a
    house, a bookshelf, a counter, a fridge, or an SVG prop with data-lean), on the side of it where it stands: it turns its back to
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
            posture = postures(scene).stand(character.name)
            end = scene.iso_stand_point(character.name) if getattr(scene, "on_iso", False) else None  # type: ignore[attr-defined]
            if end is not None:   # back to where it stood before it sat or lay down on an object of the place (§105.2)
                now = character.state()
                lying = posture[0] == "lying"
                soles = None if lying else character.sole_points(CharacterState(now.facing, {**now.parts, **before})) or None
                anims.append(scene.iso_seat_move(character, [(1.0, before)], None, end=end, soles=soles,  # type: ignore[attr-defined]
                                                 run_time=LIE_SECONDS if lying else STAND_UP_SECONDS))
                character.sitting_on = None
                continue
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
