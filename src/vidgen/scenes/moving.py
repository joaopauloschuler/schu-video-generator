"""Moving beat actions (DESIGN.md §69.12): ``walk_to``, ``run_to`` (§69.41), ``enter``, ``exit``,
``gesture``, ``jump`` and ``step_aside`` on the characters of a scene, and on an iso place
``wander`` and ``meet``. Written against ``vidgen.api`` only, like project actions; on a stage's
platform level the stage plans the walks and jumps with its rules (``level_walk``,
``level_enter``, ``level_exit``, ``level_jump``, DESIGN.md §86.7), with its story props in the way
and coins and stars picked up on the way, a reaction (``react``) during or after the move and a
blocker stepping aside (§86.8); on an iso place it plans the walks from cell to cell
(``iso_walks``, §89.9).

The motion is worked out without manim in :mod:`vidgen.cartoon.acting` (walk times, the walk
cycle, where an entrance starts and an exit ends, gestures, jumps) and played with the
:class:`Walk`, :class:`Gesture` and :class:`Jump` animations. A walk lasts its distance over its
speed (:meth:`Action.run_time_for`) plus the wind-up and settle of the character's
``cartoon_motion`` (§69.13), shortened like any action when its beat has less time.
"""

import logging
from typing import Annotated, Any, Literal

from vidgen.api import *

from .acting import _Acting, _characters

log = logging.getLogger("vidgen.actions")

#: Where a walk goes: a mark of the stage, or an x from 0 (left edge) to 1 (right edge).
Place = str | Annotated[float, Field(ge=0.0, le=1.0)]
#: How far back a walk goes on the stage (0 front .. 1 back).
Depth = Annotated[float, Field(ge=0.0, le=1.0)]
#: The seconds a blocker takes to step back off a level's path (``step_aside`` without ``to``).
STEP_ASIDE_SECONDS = 1.0


class MapTile(ActionOptions):
    """A tile of a level's map to walk or jump onto, as the author reads the map (DESIGN.md §86.7)."""

    column: int = Field(ge=1)
    """Its column, from 1 at the map's left."""
    row: int = Field(ge=1)
    """Its row, from 1 at the map's top line."""


class MoveReaction(ActionOptions):
    """A reaction during or after a move on a platform level (DESIGN.md §86.8)."""

    when: Literal["pickup", "land", "arrive"] | None = None
    """When it reacts: pickup (as it picks up the first coin or star on the way), land (as a jump lands) or arrive (as it stops); default: land for a jump, else arrive."""
    expression: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]+$")
    """The expression it changes to then (happy, surprised, laughing... or its own); it keeps it, like emote."""
    effect: Literal[EFFECT_KINDS] | None = None  # type: ignore[valid-type]
    """A symbol popping over its head then for a moment: sweat, anger, idea, question, exclaim, sleep, hearts, stars, sparkle or tear."""


def _tile_place(to: Any) -> Any:
    """``to`` as the stage's level methods take it (a tile as ``{column, row}``)."""
    return to.model_dump() if isinstance(to, MapTile) else to


class WalkPlace(ActionOptions):
    """Where a walk goes on the stage: a mark or an x, and a depth (DESIGN.md §69.44)."""

    mark: Place | None = None
    """A mark (left, centre, right, ... or the stage's own) or an x from 0 (left edge) to 1 (right edge); default: where it is."""
    depth: Depth | None = None
    """How far back: 0 = the front (the ground line, full size) .. 1 = the back of the stage; default: its depth now."""


def _place_x(scene: NarratedScene, place: str | float) -> float:
    """``place`` (a mark or an x 0..1 of the stage) in Manim units."""
    left, right = scene.camera_bounds()[:2]
    return left + scene.camera_place(scene.params, place) * (right - left)


def _view(scene: NarratedScene) -> tuple[float, float]:
    """The left and right x of what the camera shows now."""
    frame = scene.camera.frame
    middle = float(frame.get_center()[0])
    return middle - frame.width / 2, middle + frame.width / 2


def _feet_x(character: Character) -> float:
    return float(character.feet()[0])


def _walk_time(character: Character, distance: float, speed: float) -> float:
    """How long ``character`` takes to walk ``distance`` units at ``speed``, with its
    ``cartoon_motion``'s wind-up and settle."""
    return walk_motion_seconds(walk_seconds(distance, speed), character.motion_strength)


def _speed(options: ActionOptions, character: Character) -> float:
    """The action's ``speed``, or when it gives none its default times the character's species
    factor (a turtle plods, a penguin waddles; DESIGN.md §69.57)."""
    if "speed" in options.model_fields_set:
        return options.speed
    return options.speed * character.species_motion.speed


def _on_level(scene: NarratedScene) -> bool:
    """Whether the scene is a stage with a platform level (DESIGN.md §86.7): walks and jumps
    follow its tiles (the stage's ``level_walk``, ``level_jump``...)."""
    return bool(getattr(scene, "on_level", False))


def _on_iso(scene: NarratedScene) -> bool:
    """Whether the scene is a stage with an iso place (DESIGN.md §89.9): walks go from cell to
    cell on its map (the stage's ``iso_walks``)."""
    return bool(getattr(scene, "on_iso", False))


def _pace(scene: NarratedScene, options: ActionOptions, character: Character) -> float:
    """:func:`_speed`; on a level or an iso place a default speed is scaled by its smaller
    characters (``level_pace``), so they walk as many of their heights per second as on a plain stage."""
    speed = _speed(options, character)
    if (_on_level(scene) or _on_iso(scene)) and "speed" not in options.model_fields_set:
        speed *= scene.level_pace
    return speed


def _iso_seconds(scene: NarratedScene, action: str, options: ActionOptions, plan: dict[str, Any], targets: list[Target],
                 label: str, gait: Gait = WALKING) -> float | None:
    """The longest of the iso walks of ``action`` for the target characters (``None``: none, or
    the rules refuse one now: :meth:`Action.apply` plans it again when it plays, and raises)."""
    times = []
    for c in _characters(scene, targets, label):
        try:
            times += [walk.run_time for walk in scene.iso_walks(action, c, plan, pace=lambda f: _pace(scene, options, f), gait=gait)]
        except VidgenError:
            continue
    return max(times, default=None)


def _iso_apply(scene: NarratedScene, action: str, options: ActionOptions, plan: dict[str, Any], targets: list[Target],
               label: str, gait: Gait = WALKING) -> list[Animation]:
    """The iso walks of ``action`` for the target characters, recorded on the stage."""
    anims: list[Animation] = []
    for character in _characters(scene, targets, label):
        walks = scene.iso_walks(action, character, plan, pace=lambda f: _pace(scene, options, f), gait=gait)
        scene.iso_moved(walks, leaving=action == "exit")
        for walk in walks:
            _ended_walk(scene, walk.mobject)
        anims += walks
    return anims


def _spot_problems(params: Any, place: Any, key: str = "to") -> list[tuple[str, str]]:
    """On an iso place: ``place`` is a spot of its map or a cell ``{column, row}``, not an x or another mark."""
    if place is None or isinstance(place, (MapTile, dict)):
        return []
    spots = params.iso.parsed().spot_names()
    if isinstance(place, str) and place in spots:
        return []
    return [(key, f"on an iso place a move goes to a spot of the map ({', '.join(spots) or 'none: put a letter on the map'}) "
                  f"or a cell {{column, row}}, not '{place}'")]


def _level_seconds(make: Any) -> float | None:
    """The run time of the level animation ``make()`` builds, or ``None`` when the rules refuse it
    now (its batch may start after another move of the same character: :meth:`Action.apply`
    plans it again then, and raises)."""
    try:
        return float(make().run_time)
    except VidgenError:
        return None


def _carried(scene: NarratedScene, character: Character) -> list[Mobject]:
    """The props ``character`` holds (they grow with a walk in depth and fade through a door)."""
    return [p for p in getattr(scene, "props", {}).values() if getattr(p, "held_by", None) == character.name]


def _ended_walk(scene: NarratedScene, character: Character) -> None:
    """Record the beat its walk ends in (the layout dump's ``walked_in``, lint ``walk_overlap``)."""
    beat = scene.current_beat
    character.walked_in = beat.id if beat is not None else None


class _Moving(_Acting):
    """A moving action: its targets must be characters; ``to`` (when it is a place) must be a
    mark of the scene or an x, or on a level a tile of its map; a ``react`` is for a level."""

    def _place_problems(self, scene_cls: type[NarratedScene], params: Any, place: Any) -> list[tuple[str, str]]:
        problems = self._target_characters(scene_cls, params)[1]
        if getattr(params, "iso", None) is not None:
            return problems + _spot_problems(params, place)
        if isinstance(place, (MapTile, dict)):
            if getattr(params, "level", None) is None:
                problems.append(("to", "a tile {column, row} is a place on a platform level (params.level); give a mark or an x"))
            return problems
        if place is None:
            return problems
        try:
            scene_cls.camera_place(params, place)
        except ValueError as exc:
            problems.append(("to", str(exc)))
        return problems

    def character_needs(self) -> str | None:
        react = getattr(self.options, "react", None)
        return "emote" if react is not None and react.expression is not None else self.needs

    def _react_problems(self, scene_cls: type[NarratedScene], params: Any, *, jumps: bool) -> list[tuple[str, str]]:
        """A ``react`` names an expression or an effect, lands only on a jump, and is for a level."""
        react = getattr(self.options, "react", None)
        if react is None:
            return []
        if getattr(params, "level", None) is None:
            return [("react", "react is for moves on a platform level (params.level); use emote, react or effect actions on a plain stage")]
        if react.expression is None and react.effect is None:
            return [("react", "say how it reacts: an expression and / or an effect")]
        if react.when == "land" and not jumps:
            return [("react", "when: land is for a jump; a walk reacts when: pickup or when: arrive")]
        named = self._named_problems(scene_cls, params, "expression", react.expression, "expression")
        return [("react", text) for key, text in named if key == "expression"]


def _walk_problems(params: Any, to: Any, depth: float | None) -> list[tuple[str, str]]:
    """A walk names where it goes (``to`` or ``depth``), its depth once, and, in a room, not
    behind the wall (DESIGN.md §69.44)."""
    inner = to.depth if isinstance(to, WalkPlace) else None
    if to is None and depth is None:
        return [("to", "say where it walks: to (a mark or an x, or {mark, depth}) and / or depth")]
    if isinstance(to, WalkPlace) and to.mark is None and to.depth is None:
        return [("to", "give the place a mark and / or a depth: {mark: right, depth: 0.4}")]
    if inner is not None and depth is not None:
        return [("depth", "give the depth once: in to ({mark, depth}) or as depth, not both")]
    if getattr(params, "level", None) is not None and (inner is not None or depth is not None):
        return [("depth", "a level has no depth: walks go along its tiles; remove depth (and give to: a spot, a mark or an x)")]
    if getattr(params, "iso", None) is not None and (isinstance(to, WalkPlace) or depth is not None):
        return [("depth", "an iso place has no depth: walks go from cell to cell; remove depth and give to: a spot or {column, row}")]
    wall = params.wall_depth() if hasattr(params, "wall_depth") else None
    going = inner if inner is not None else depth
    if wall is not None and going is not None and going > wall + SAME_DEPTH:
        return [("depth", f"depth {going} is behind the room's wall (at depth {wall}); walk to at most {wall}")]
    return []


@action("walk_to")
class WalkTo(_Moving):
    """The target character walks along the ground to ``to`` (a mark of the stage, or an x from 0
    = left to 1 = right), facing the way it goes, at ``speed`` (Manim units per second; the frame's
    shorter side is 8). ``depth`` (or ``to: {mark, depth}``) walks it towards (smaller) or away
    from (larger) the camera too: it grows or shrinks, its shadow with it, and passes in front of
    or behind the others on the way; walking only in depth it keeps its facing (``facing: front``:
    it steps towards the camera). It takes as long as the distance needs (``run_time`` sets it
    instead); a beat shorter than that speeds it up. It stays there. On a platform level it walks
    along the tiles (``to`` may be a tile ``{column, row}`` of the map), picks up the coins and
    stars it touches and cannot pass a closed door or a blocker; ``react`` changes its expression
    and / or pops an effect when it picks one up or arrives (DESIGN.md §86.8)."""

    class Options(ActionOptions):
        to: MapTile | WalkPlace | Place | None = None
        """Where it walks: a mark (left, centre, right, ... or the stage's own), an x from 0 (left edge) to 1 (right edge) of the stage, or {mark, depth}; on a platform level also a tile {column, row} of the map (from 1 at the top left); default: where it is (with depth)."""
        depth: Depth | None = None
        """How far back it walks to: 0 = the front (the ground line, full size) .. 1 = the back of the stage, smaller; default: its depth now."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second (the frame's shorter side is 8 units; a stage character is about 3.6 tall); default 2.5 (a turtle 1, a penguin 1.75)."""
        react: MoveReaction | None = None
        """On a platform level: {when: pickup | arrive, expression, effect}: how it reacts as it picks up the first coin or star on the way, or as it arrives (default)."""
        after: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]+$")
        """On an iso place, instead of to: a character it follows: it walks to it and on behind it along its way when that one moves in the same beat at the same time (write this move after the leader's), stopping gap cells behind it."""
        gap: int = Field(1, ge=1, le=5)
        """With after: how many cells behind the leader it stops."""

    run_time = 2.0

    def _destination(self) -> tuple[Any, float | None]:
        """Where it goes (a mark or an x, a tile as ``{column, row}``; ``None``: its x now) and to
        what depth (``None``: its own)."""
        to = self.options.to
        if isinstance(to, WalkPlace):
            return to.mark, to.depth if to.depth is not None else self.options.depth
        return _tile_place(to), self.options.depth

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        place = self._destination()[0]
        after = self.options.after
        if after is not None:
            return self._after_problems(scene_cls, params)
        return (self._place_problems(scene_cls, params, place) + _walk_problems(params, self.options.to, self.options.depth)
                + self._react_problems(scene_cls, params, jumps=False))

    def _after_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """``after`` follows another character of the scene, on an iso place, instead of ``to``."""
        names, problems = self._target_characters(scene_cls, params)
        after = self.options.after
        if getattr(params, "iso", None) is None:
            return problems + [("after", "after (walking behind a leader) is for an iso place (params.iso); give to: a mark or an x")]
        if self.options.to is not None or self.options.depth is not None:
            return problems + [("after", "give to (a place) or after (a character to follow), not both")]
        if after not in [c.name for c in params.characters]:
            return problems + [("after", f"'{after}' is not a character of this scene ({', '.join(c.name for c in params.characters)})")]
        if after in names:
            return problems + [("after", f"'{after}' cannot walk after itself")]
        return problems + self._react_problems(scene_cls, params, jumps=False)

    def _iso_plan(self) -> dict[str, Any]:
        """The move as the iso rules take it (DESIGN.md §89.9)."""
        if self.options.after is not None:
            return {"after": self.options.after, "gap": self.options.gap}
        return {"to": self._destination()[0]}

    def _goal(self, scene: NarratedScene, character: Character) -> tuple[float, float | None]:
        """The x it walks to and its depth there (``None``: no walk in depth on this scene)."""
        place, depth = self._destination()
        x = _feet_x(character) if place is None else _place_x(scene, place)
        if depth is not None and not hasattr(scene, "feet_y_at"):
            log.warning("scene '%s': %s depth needs a stage; it walks across only", scene.spec.id, self.label)
            depth = None
        return x, depth

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        if _on_iso(scene):
            return _iso_seconds(scene, "walk_to", self.options, self._iso_plan(), targets, self.label, self.gait)
        if _on_level(scene):
            place = self._destination()[0]
            found = [_level_seconds(lambda c=c: scene.level_walk(c, place, speed=_pace(scene, self.options, c), gait=self.gait,
                                                                 react=self.options.react))
                     for c in _characters(scene, targets, self.label)]
            return max((t for t in found if t is not None), default=None)
        times = []
        for c in _characters(scene, targets, self.label):
            x, depth = self._goal(scene, c)
            far = abs(x - _feet_x(c)) if depth is None else depth_walk_distance(x - _feet_x(c), c.stage_depth, depth, c.character_height)
            times.append(_walk_time(c, far, _speed(self.options, c)))
        return max(times, default=None)

    #: Its action name (in log messages) and how it moves its feet (a run: :data:`RUNNING`).
    label = "walk_to"
    gait = WALKING

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`Walk` to the place (and depth) for each character not there yet; on a level
        along its tiles and ladders (the stage's ``level_walk``)."""
        if _on_iso(scene):
            return _iso_apply(scene, "walk_to", self.options, self._iso_plan(), targets, self.label, self.gait)
        anims: list[Animation] = []
        if _on_level(scene):
            for character in _characters(scene, targets, self.label):
                walk = scene.level_walk(character, self._destination()[0], speed=_pace(scene, self.options, character), gait=self.gait,
                                        react=self.options.react)
                if walk.route.effort > 1e-6:
                    anims.append(walk)
                    scene.level_moved(character, walk)
                    _ended_walk(scene, character)
            return anims
        for character in _characters(scene, targets, self.label):
            x, depth = self._goal(scene, character)
            deeper = depth is not None and abs(depth - character.stage_depth) > SAME_DEPTH
            if abs(x - _feet_x(character)) <= 1e-6 and not deeper:
                continue
            if not deeper:
                anims.append(Walk(character, x, speed=_speed(self.options, character), gait=self.gait))
            else:
                walk = Walk(character, x, speed=_speed(self.options, character), gait=self.gait, depth=depth, feet_y=scene.feet_y_at,
                            carried=_carried(scene, character))
                anims.append(walk)
                scene.walk_in_depth(character, walk)
            _ended_walk(scene, character)
        return anims


@action("run_to")
class RunTo(WalkTo):
    """The target character runs along the ground to ``to`` (a mark of the stage, or an x from 0
    = left to 1 = right): a walk at running ``speed`` with longer strides, bigger swings and the
    body leaning forward. With motion effects (``cartoon_motion`` not none) dust puffs up where
    it sets off and stops and speed lines trail it."""

    class Options(ActionOptions):
        to: MapTile | WalkPlace | Place | None = None
        """Where it runs: a mark (left, centre, right, ... or the stage's own), an x from 0 (left edge) to 1 (right edge) of the stage, or {mark, depth}; on a platform level also a tile {column, row} of the map; default: where it is (with depth)."""
        depth: Depth | None = None
        """How far back it runs to: 0 = the front (the ground line, full size) .. 1 = the back of the stage, smaller; default: its depth now."""
        speed: float = Field(RUN_SPEED, gt=0.0, le=20.0)
        """Running speed in units per second (the frame's shorter side is 8 units; a stage character is about 3.6 tall); default 6 (a turtle 2.4, a penguin 4.2)."""
        react: MoveReaction | None = None
        """On a platform level: {when: pickup | arrive, expression, effect}: how it reacts as it picks up the first coin or star on the way, or as it arrives (default)."""
        after: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]+$")
        """On an iso place, instead of to: a character it follows: it runs to it and on behind it along its way when that one moves in the same beat at the same time (write this move after the leader's), stopping gap cells behind it."""
        gap: int = Field(1, ge=1, le=5)
        """With after: how many cells behind the leader it stops."""

    run_time = 1.2
    label = "run_to"
    gait = RUNNING


def _door_problems(params: Any, door: str | None, other: str, given: Any) -> list[tuple[str, str]]:
    """``door`` names a door of the stage's room (on an iso place a spot of its map), and the edge
    option ``other`` is not ``given`` too (DESIGN.md §69.42)."""
    if door is None:
        return []
    if getattr(params, "iso", None) is not None:
        both = [("door", f"give {other} (a side of the place's edge) or door (a spot), not both")] if given is not None else []
        return _spot_problems(params, door, "door") + both
    doors = params.door_names() if hasattr(params, "door_names") else []
    problems: list[tuple[str, str]] = []
    if door not in doors:
        known = ", ".join(doors) or "none (add room: {doors: [...]} to the stage)"
        problems.append(("door", f"no door '{door}' on this stage (its room's doors: {known})"))
    if given is not None:
        problems.append(("door", f"give {other} (an edge) or door, not both"))
    return problems


def _door_closed(scene: NarratedScene, name: str | None) -> bool:
    """Whether the room's door ``name`` is closed now (``None``: no door)."""
    return name is not None and scene.door(name).shape != "open"


def _door_x(scene: NarratedScene, name: str) -> float:
    """The x of the room's door ``name`` (opened if it is closed: a character goes through it)."""
    door = scene.door(name)
    if door.shape != "open":
        door.show_shape("open")
    return float(door.feet()[0])


@action("enter")
class Enter(_Moving):
    """The target character walks in from beyond the ``side`` edge of what the camera shows (left
    or right; default: the edge nearer where it goes), or through the room's ``door`` (it opens,
    the character appears in it and walks on), to ``to`` (a mark or an x; default its own mark on
    the stage). On a ``stage`` a character with an enter action waits off stage until then."""

    class Options(ActionOptions):
        side: Literal["left", "right"] | None = None
        """The edge it comes in from: left or right; default: the one nearer where it goes."""
        door: str | None = None
        """Instead of side: a door of the stage's room (its name) it comes in through; on an iso place a spot of the map it comes out of (fading in there: a house's door, a gate)."""
        to: Place | None = None
        """Where it walks to: a mark or an x from 0 to 1 of the stage; default: its own mark (its at on the stage)."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second."""

    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._place_problems(scene_cls, params, self.options.to) + _door_problems(params, self.options.door, "side", self.options.side)

    def _path(self, scene: NarratedScene, character: Character, *, opening: bool = False) -> tuple[str, float, float]:
        if self.options.to is not None:
            to_x = _place_x(scene, self.options.to)
        else:
            to_x = getattr(scene, "homes", {}).get(character.name, _feet_x(character))
        if self.options.door is not None:
            door = scene.door(self.options.door)
            return "door", _door_x(scene, self.options.door) if opening else float(door.feet()[0]), to_x
        return enter_path(self.options.side, to_x, _view(scene), character.width / 2)

    def _seconds(self, character: Character, start: float, end: float) -> float:
        walk = _walk_time(character, end - start, _speed(self.options, character))
        return max(walk, 2 * DOOR_FADE_SECONDS) if self.options.door is not None else walk

    def _level_walk(self, scene: NarratedScene, character: Character) -> Animation:
        """On a level: in from beyond the view's edge along the tiles (the stage's ``level_enter``)."""
        side, start, _ = self._path(scene, character)
        return scene.level_enter(character, side, start, self.options.to, speed=_pace(scene, self.options, character))

    def _iso_plan(self) -> dict[str, Any]:
        return {"to": self.options.to, "door": self.options.door, "side": self.options.side}

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        if _on_iso(scene):
            return _iso_seconds(scene, "enter", self.options, self._iso_plan(), targets, "enter")
        if _on_level(scene):
            found = [_level_seconds(lambda c=c: self._level_walk(scene, c)) for c in _characters(scene, targets, "enter")]
            return max((t for t in found if t is not None), default=None)
        times = []
        for character in _characters(scene, targets, "enter"):
            _, start, end = self._path(scene, character)
            times.append(self._seconds(character, start, end))
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Put each character just beyond the view's edge, or in the open door, and walk it in
        (fading in at the door); on a level along the tiles; on an iso place from beyond its edge
        or out of a spot (DESIGN.md §89.9)."""
        if _on_iso(scene):
            return _iso_apply(scene, "enter", self.options, self._iso_plan(), targets, "enter")
        anims: list[Animation] = []
        if _on_level(scene):
            for character in _characters(scene, targets, "enter"):
                walk = self._level_walk(scene, character)
                anims.append(walk)
                scene.level_moved(character, walk)
                _ended_walk(scene, character)
            return anims
        for character in _characters(scene, targets, "enter"):
            closed = _door_closed(scene, self.options.door)
            _, start, end = self._path(scene, character, opening=True)
            door = {} if self.options.door is None else {
                "fade_in": DOOR_FADE_SECONDS, "run_time": self._seconds(character, start, end), "carried": _carried(scene, character),
                "opens_door": closed,
            }
            anims.append(Walk(character, end, start_x=start, speed=_speed(self.options, character), **door))
            _ended_walk(scene, character)
        return anims


@action("exit")
class Exit(_Moving):
    """The target character walks out of what the camera shows, beyond its ``to`` edge (left or
    right; default: the nearer one), or out through the room's ``door`` (it opens; the character
    fades away in it), and then waits off the stage (an ``enter`` brings it back). A camera
    following it stops following (and stays)."""

    class Options(ActionOptions):
        to: Literal["left", "right"] | None = None
        """The edge it leaves by: left or right; default: the nearer one."""
        door: str | None = None
        """Instead of to: a door of the stage's room (its name) it leaves through; on an iso place a spot of the map it goes into (fading away there)."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second."""

    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1] + _door_problems(params, self.options.door, "to", self.options.to)

    def _end(self, scene: NarratedScene, character: Character, *, opening: bool = False) -> tuple[str, float]:
        if self.options.door is not None:
            door = scene.door(self.options.door)
            return nearer_side(_feet_x(character), *scene.camera_bounds()[:2]), _door_x(scene, self.options.door) if opening else float(door.feet()[0])
        return exit_path(self.options.to, _feet_x(character), _view(scene), character.width / 2)

    def _seconds(self, character: Character, end: float) -> float:
        walk = _walk_time(character, end - _feet_x(character), _speed(self.options, character))
        return max(walk, 2 * DOOR_FADE_SECONDS) if self.options.door is not None else walk

    def _level_walk(self, scene: NarratedScene, character: Character) -> Animation:
        """On a level: out beyond the view's edge along the tiles (the stage's ``level_exit``),
        then beyond the stage's edge."""
        left, right = scene.camera_bounds()[:2]
        side, end = self._end(scene, character)
        park = offstage_x(side, left, right, character.width / 2)
        return scene.level_exit(character, side, end, park, speed=_pace(scene, self.options, character))

    def _iso_plan(self) -> dict[str, Any]:
        return {"to": self.options.to, "door": self.options.door}

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        if _on_iso(scene):
            return _iso_seconds(scene, "exit", self.options, self._iso_plan(), targets, "exit")
        if _on_level(scene):
            found = [_level_seconds(lambda c=c: self._level_walk(scene, c)) for c in _characters(scene, targets, "exit")]
            return max((t for t in found if t is not None), default=None)
        times = [self._seconds(c, self._end(scene, c)[1]) for c in _characters(scene, targets, "exit")]
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Walk each character out of the view or into the door (fading away there); then put it
        beyond the stage's edge. On a level along the tiles."""
        left, right = scene.camera_bounds()[:2]
        anims: list[Animation] = []
        if _on_iso(scene):
            for character in _characters(scene, targets, "exit"):
                if getattr(scene.camera_following, "followed", None) is character:
                    scene.follow_with_camera(None)
            return _iso_apply(scene, "exit", self.options, self._iso_plan(), targets, "exit")
        for character in _characters(scene, targets, "exit"):
            if getattr(scene.camera_following, "followed", None) is character:
                scene.follow_with_camera(None)
            if _on_level(scene):
                anims.append(self._level_walk(scene, character))
                continue
            half = character.width / 2
            closed = _door_closed(scene, self.options.door)
            side, end = self._end(scene, character, opening=True)
            door = {} if self.options.door is None else {
                "fade_out": DOOR_FADE_SECONDS, "run_time": self._seconds(character, end), "carried": _carried(scene, character),
                "opens_door": closed,
            }
            anims.append(Walk(character, end, park_x=offstage_x(side, left, right, half), speed=_speed(self.options, character), **door))
        return anims


@action("gesture")
class GestureAction(_Moving):
    """The target character makes a gesture ``to``: point (the near arm forward), wave, shrug,
    nod or shake_head, and comes back to its pose. ``big: true``: a sweeping gesture; with motion
    effects (``cartoon_motion`` not none) a small whoosh arc trails the hand of a point, wave or
    shrug."""

    class Options(ActionOptions):
        to: Literal[GESTURES]  # type: ignore[valid-type]
        """The gesture: point, wave, shrug, nod or shake_head."""
        big: bool = False
        """true: a big, sweeping gesture: with motion effects a whoosh arc trails the hand (point, wave, shrug)."""

    run_time = 1.2

    def character_needs(self) -> str | None:
        return f"gesture: {self.options.to}"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1]

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return GESTURE_SECONDS[self.options.to]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`Gesture` on each character."""
        return [Gesture(c, self.options.to) for c in _characters(scene, targets, "gesture")]


@action("jump")
class JumpAction(_Moving):
    """The target character jumps up (``height`` in character heights) and lands where it stood.
    Without a ``height`` a frog jumps higher (its species' factor, DESIGN.md §69.57). On a
    platform level, ``to`` (a spot, a mark, an x or a tile ``{column, row}``) jumps it there: it
    walks to the best take-off point, crouches, flies an arc clear of the tiles and lands with a
    squash and a wobble (DESIGN.md §86.7), picking up the coins and stars it touches on the way
    (mid-jump too), never through a closed door or a blocker; ``react`` changes its expression
    and / or pops an effect as it picks one up, lands or stops (§86.8). ``vidgen validate`` says
    why a jump cannot be made."""

    class Options(ActionOptions):
        height: float = Field(JUMP_HEIGHT, gt=0.0, le=2.0)
        """How high it jumps, in its own heights (0.4: a hop; 1: its own height); default 0.4 (a frog 0.72)."""
        to: MapTile | Place | None = None
        """On a platform level: where it jumps to: a spot, a mark or an x 0..1 of the stage (onto the highest tile there a jump reaches), or a tile {column, row} of the map (from 1 at the top left); default: up where it stands."""
        react: MoveReaction | None = None
        """With to, on a platform level: {when: pickup | land | arrive, expression, effect}: how it reacts as it picks up the first coin or star on the way, as it lands (default) or once it stands still."""

    def _place(self) -> Any:
        """``to`` as the stage's ``level_jump`` takes it (a tile as ``{column, row}``)."""
        return _tile_place(self.options.to)

    def _height(self, character: Character) -> float:
        if "height" in self.options.model_fields_set:
            return self.options.height
        return self.options.height * character.species_motion.jump

    run_time = JUMP_SECONDS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        to = self.options.to
        problems = self._place_problems(scene_cls, params, None if isinstance(to, MapTile) else to)
        problems += self._react_problems(scene_cls, params, jumps=True)
        if to is not None and getattr(params, "iso", None) is not None:
            problems.append(("to", "an iso place has no jumping to a place: walk_to or run_to it (a jump without to jumps up where it stands)"))
        elif to is not None and getattr(params, "level", None) is None:
            problems.append(("to", "jumping to a place needs a platform level (params.level); without one a character jumps up where it stands"))
        if to is not None and "height" in self.options.model_fields_set:
            problems.append(("height", "give height (a jump where it stands) or to (a jump to a place on the level), not both"))
        if to is None and self.options.react is not None:
            problems.append(("react", "react goes with a jump to a place (to) on a platform level"))
        return problems

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        if self.options.to is not None and _on_level(scene):
            found = [_level_seconds(lambda c=c: scene.level_jump(c, self._place(), react=self.options.react))
                     for c in _characters(scene, targets, "jump")]
            return max((t for t in found if t is not None), default=None)
        times = [jump_motion_seconds(JUMP_SECONDS, c.motion_strength) for c in _characters(scene, targets, "jump")]
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`Jump` on each character; with ``to`` on a level, the planned run-up and arc
        (the stage's ``level_jump``)."""
        if self.options.to is None or not _on_level(scene):
            return [Jump(c, self._height(c)) for c in _characters(scene, targets, "jump")]
        anims: list[Animation] = []
        for character in _characters(scene, targets, "jump"):
            jump = scene.level_jump(character, self._place(), react=self.options.react)
            anims.append(jump)
            scene.level_moved(character, jump)
            _ended_walk(scene, character)
        return anims


@action("step_aside")
class StepAside(_Moving):
    """On a platform level, the target character, one of the level's ``blockers`` (a grumpy
    turtle on the path), moves out of the way, as when it is asked nicely in the beat's line: it
    steps back off the path (a little smaller, drawn behind the others), or with ``to`` walks
    there along the tiles. From then on walks and jumps pass where it stood (DESIGN.md §86.8)."""

    class Options(ActionOptions):
        to: MapTile | Place | None = None
        """Where it walks out of the way: a spot, a mark, an x 0..1 of the stage or a tile {column, row} of the map; default: a step back off the path."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second; default 2.5 (a turtle 1)."""

    run_time = STEP_ASIDE_SECONDS

    def _destination(self) -> tuple[Any, None]:
        return _tile_place(self.options.to), None

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        names, problems = self._target_characters(scene_cls, params)
        level = getattr(params, "level", None)
        if level is None:
            return problems + [("action", "step_aside is for the blockers of a platform level (params.level.blockers)")]
        for name in names:
            if name not in level.blockers:
                problems.append(("target", f"'{name}' is not one of the level's blockers ({', '.join(level.blockers) or 'none'}); "
                                           "list it in level.blockers"))
        to = self.options.to
        return problems + ([] if isinstance(to, MapTile) else self._place_problems(scene_cls, params, to))

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        place = self._destination()[0]
        if place is None or not _on_level(scene):
            return None
        found = [_level_seconds(lambda c=c: scene.level_walk(c, place, speed=_pace(scene, self.options, c), gait=WALKING))
                 for c in _characters(scene, targets, "step_aside")]
        return max((t for t in found if t is not None), default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Each blocker moves out of the way (the stage's ``level_step_aside``)."""
        if not _on_level(scene):
            return []
        place = self._destination()[0]
        return [scene.level_step_aside(c, place, speed=_pace(scene, self.options, c)) for c in _characters(scene, targets, "step_aside")]


def _iso_only(params: Any, action: str) -> list[tuple[str, str]]:
    """``action`` moves characters about an iso place (DESIGN.md §89.9)."""
    if getattr(params, "iso", None) is None:
        return [("action", f"{action} is for an iso place (params.iso); on a plain stage use walk_to")]
    return []


@action("wander")
class Wander(_Moving):
    """On an iso place, the target character strolls about: it walks to ``stops`` cells picked at
    random (the same ones on every render; another ``seed`` picks others) within ``radius`` cells
    of ``around`` (a spot; default where it stands), round what is in the way, and stays at the
    last one. It takes as long as the way needs (``run_time`` sets it instead)."""

    class Options(ActionOptions):
        around: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]+$")
        """A spot of the map it strolls around; default: where it stands."""
        radius: int = Field(WANDER_RADIUS, ge=1, le=12)
        """How far from there (cells) it may go; default 3."""
        stops: int = Field(WANDER_STOPS, ge=1, le=8)
        """How many places it walks to in turn; default 3."""
        seed: int | None = None
        """Picks other places (the same seed, the same stroll); default: one from the character and the beat."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second; default 2.5 (scaled to the place's characters)."""

    run_time = 3.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = self._target_characters(scene_cls, params)[1] + _iso_only(params, "wander")
        return problems if problems else _spot_problems(params, self.options.around, "around")

    def _iso_plan(self) -> dict[str, Any]:
        return {"around": self.options.around, "radius": self.options.radius, "stops": self.options.stops, "seed": self.options.seed}

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return _iso_seconds(scene, "wander", self.options, self._iso_plan(), targets, "wander") if _on_iso(scene) else None

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """An iso walk along the stroll for each character (the stage's ``iso_walks``)."""
        return _iso_apply(scene, "wander", self.options, self._iso_plan(), targets, "wander") if _on_iso(scene) else []


@action("meet")
class Meet(_Moving):
    """On an iso place, the target character and the character ``with`` walk to each other: along
    the way between them, round what is in the way, to two cells next to each other half way. Each
    ends facing the other. It takes as long as the longer walk needs."""

    class Options(ActionOptions):
        with_: str = Field(alias="with", pattern=r"^[A-Za-z0-9_]+$")
        """The other character, who walks towards it too."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second (both); default 2.5 (scaled to the place's characters)."""

    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        names, problems = self._target_characters(scene_cls, params)
        problems += _iso_only(params, "meet")
        other = self.options.with_
        if other not in [c.name for c in params.characters]:
            problems.append(("with", f"'{other}' is not a character of this scene ({', '.join(c.name for c in params.characters)})"))
        elif other in names:
            problems.append(("with", f"'{other}' cannot meet itself; target the other character"))
        elif len(names) > 1:
            problems.append(("target", "meet moves one character towards another: one target, and the other in with"))
        return problems

    def alters(self, scene: NarratedScene) -> list[Mobject]:
        other = getattr(scene, "cast", {}).get(self.options.with_)
        return [other] if other is not None else []

    def _iso_plan(self) -> dict[str, Any]:
        return {"with": self.options.with_}

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return _iso_seconds(scene, "meet", self.options, self._iso_plan(), targets, "meet") if _on_iso(scene) else None

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Both walk (the stage's ``iso_walks``) and end facing each other (one that does not
        walk turns to the other)."""
        if not _on_iso(scene):
            return []
        anims: list[Animation] = []
        for character in _characters(scene, targets, "meet"):
            walks = _iso_apply(scene, "meet", self.options, self._iso_plan(), [t for t in targets if t.mobject is character], "meet")
            pair = (character, scene.cast[self.options.with_])
            ends = {walk.mobject.name: walk.to_x for walk in walks}
            x = [ends.get(c.name, _feet_x(c)) for c in pair]
            if abs(x[0] - x[1]) > 1e-6:
                for k, figure in enumerate(pair):
                    towards = "right" if x[k] < x[1 - k] else "left"
                    walk = next((w for w in walks if w.mobject is figure), None)
                    if walk is not None:
                        walk.end_facing = towards
                    elif figure.facing != towards:
                        anims.append(self._change(figure, CharacterState(towards, figure.state().parts)))
            anims += walks
        return anims
