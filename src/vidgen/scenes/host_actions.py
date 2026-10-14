"""Host beat actions (DESIGN.md §71.1): ``host_point``, ``host_look``, ``host_react``,
``host_move``, ``host_enter`` and ``host_exit`` act on the scene's cartoon host (``host:``, §71),
in any scene type that draws one. Written against ``vidgen.api`` only, like project actions.

The host is not a target: ``host_point`` / ``host_look`` name a target of the scene (``item2``,
``bar:2024``) and turn the host towards the edge of its box nearest the host; ``host_react``
names an expression; the moves name a side. Every one changes only the host (and a ``host_move``
the camera), which :meth:`Action.alters` tells the runner. A pointing hand stays in the host's room
(:func:`hand_goal`): out of reach, the arm points straight at the target, and ``line: true``
draws a thin pointer line from the hand to just short of the target.

``host_move`` walks the host to the other side; beside the content its column swaps sides and
the content slides the column's width the other way with it (the camera moves, so every object
of the scene, also one revealed later, moves together; overlays and captions stay): the content
reflows mid-scene, in the beat of the move. In a band below the content (9:16) only the host
walks. Each scene starts with its own ``host:`` side.
"""

import logging
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .acting import _Acting, _head_point, looked_state
from .actions import MoveCamera
from .effect_action import hide_symbol, show_symbol
from .moving import _speed, _walk_time

log = logging.getLogger("vidgen.actions")

#: How far short of a target a pointer line stops (Manim units), and its stroke width.
POINTER_GAP = 0.12
POINTER_WIDTH = 3.0
#: Seconds a host takes to turn back to the content after a walk.
TURN_SECONDS = 0.3
#: The sides a host move, entrance or exit names.
MOVE_PLACES = ("other_side", "left", "right")


def _host(scene: NarratedScene, name: str) -> Any:
    """The scene's host (a ``HostFigure``); a :class:`VidgenError` when it has none."""
    host = getattr(scene, "host", None)
    if host is None:
        raise VidgenError(f"scene '{scene.spec.id}': {name} needs a host, and this scene has none (host:)")
    return host


def _target_box(scene: NarratedScene, targets: list[Target]) -> tuple[float, float, float, float]:
    """The box around the targets: each one's ``outline`` (a bar without its axis label), else
    its parts on screen, else its whole mobject."""
    parts: list[Mobject] = []
    for t in targets:
        parts += [t.outline] if t.outline is not None else (scene.on_screen_parts(t) or [t.mobject])
    lows = [p.get_corner(DL) for p in parts]
    highs = [p.get_corner(UR) for p in parts]
    return (min(float(p[0]) for p in lows), min(float(p[1]) for p in lows), max(float(p[0]) for p in highs), max(float(p[1]) for p in highs))


def _near_hand(character: Character) -> str | None:
    """The hand a host points with: the near one (``left``), else ``right``; none without arms."""
    return next((hand for hand in ("left", "right") if character.has_part(f"arm_{hand}")), None)


def _room(host: Any) -> tuple[float, float, float, float]:
    """The host's room (its column or band) in scene coordinates."""
    x0, y0, x1, y1 = host.room
    return x0 - host.content_shift, y0, x1 - host.content_shift, y1


class _HostAction(_Acting):
    """An action on the scene's host: it changes the host (not its targets), and a scene type
    that draws no host (``stage``, ``card``) cannot use it."""

    alters_targets = False

    def alters(self, scene: NarratedScene) -> list[Mobject]:
        host = getattr(scene, "host", None)
        return [host] if host is not None else []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not scene_cls.takes_host:
            return [("action", f"{self.config.action}: this scene type draws no host (DESIGN.md §71)")]
        return []

    def _place(self) -> str | None:
        """The side the target names (``None``: none given)."""
        names = self.config.targets()
        return names[0] if names else None

    def _place_problems(self, allowed: tuple[str, ...]) -> list[tuple[str, str]]:
        names = self.config.targets()
        if len(names) > 1 or any(name not in allowed for name in names):
            return [("target", f"{self.config.action} takes one of {', '.join(allowed)}, not {', '.join(names)}")]
        return []


def _looked(character: Character, box: tuple[float, float, float, float]) -> CharacterState:
    """``character``'s state looking at the edge of ``box`` nearest its head."""
    head = _head_point(character)
    spot = pointed_spot((float(head[0]), float(head[1])), box)
    return looked_state(character, look_pose(spot[0] - float(head[0]), spot[1] - float(head[1]), character.facing))


@action("host_look")
class HostLook(_HostAction):
    """The scene's host turns its head to the target (the edge of its box nearest the host),
    until the next beat starts (``until: <beat>``: until that beat starts)."""

    run_time = 0.5
    reversible = True
    until_next_beat = True

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`PoseChange` of the host's head (and facing) towards the targets."""
        host = _host(scene, "host_look")
        if not host.present or not targets:
            return []
        character = host.character
        return [self._change(character, _looked(character, _target_box(scene, targets)))]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to where it looked before."""
        return self._undo()


@action("host_point")
class HostPoint(_HostAction):
    """The scene's host points at the target: its near arm reaches towards the edge of the
    target's box nearest it (out of reach: straight at it; the hand stays in the host's room) and
    its head looks there; ``line: true`` also draws a thin line from the hand to just short of
    the target. Until the next beat starts (``until: <beat>``: until that beat starts)."""

    class Options(ActionOptions):
        line: bool = False
        """true: a thin pointer line from the hand to the target."""
        color: ThemeColor = "dim"
        """Colour of the pointer line (theme token or hex)."""

    run_time = 0.6
    reversible = True
    until_next_beat = True

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`PoseChange` of the host's arm and head; the pointer line growing in its
        second half."""
        host = _host(scene, "host_point")
        self.line: Mobject | None = None
        if not host.present or not targets:
            return []
        character = host.character
        box = _target_box(scene, targets)
        state = _looked(character, box)
        hand = _near_hand(character)
        end = None
        if hand is not None:
            before = character.state()
            character.set_state(state)   # the shoulder where the look turned it
            shoulder = character.shoulder_point(hand)
            spot = pointed_spot((float(shoulder[0]), float(shoulder[1])), box)
            goal = hand_goal((float(shoulder[0]), float(shoulder[1])), spot, _room(host))
            state = CharacterState(state.facing, {**state.parts, **character.reached_parts(hand, [goal[0], goal[1], 0.0])})
            character.set_state(state)
            end = character.hand_point(hand)
            character.set_state(before)
        anims: list[Animation] = [self._change(character, state)]
        host.pointing_at = targets[0].name
        if self.options.line and end is not None:
            anims += self._line(scene, host, hand, end, np.array([spot[0], spot[1], 0.0]))
        return anims

    def _line(self, scene: NarratedScene, host: Any, hand: str, start: np.ndarray, spot: np.ndarray) -> list[Animation]:
        """The pointer line from the hand (``start``) to :data:`POINTER_GAP` short of ``spot``;
        it keeps to the hand afterwards."""
        direction = spot - start
        length = float(np.linalg.norm(direction))
        if length <= 2 * POINTER_GAP:
            return []
        tip = spot - direction / length * POINTER_GAP
        line = Line(start, tip, color=scene.theme.color(self.options.color), stroke_width=POINTER_WIDTH)
        line.host_pointer_of = host.host_name   # the layout dump's kind pointer
        character = host.character
        line.add_updater(lambda m: m.put_start_and_end_on(character.hand_point(hand), tip))
        self.line = line
        return [Create(line, rate_func=lambda t: smooth(max(0.0, 2.0 * t - 1.0)))]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Arm and head back; the pointer line fades."""
        host = getattr(scene, "host", None)
        if host is not None:
            host.pointing_at = None
        anims = self._undo()
        line = getattr(self, "line", None)
        if line is not None:
            line.clear_updaters()
            anims.append(FadeOut(line))
            self.line = None
        return anims


@action("host_react")
class HostReact(_HostAction):
    """The scene's host shows an expression (the target: happy, surprised, worried... or its own)
    and, with ``effect``, a symbol over its head, until the next beat starts (``until: <beat>``:
    until that beat starts)."""

    class Options(ActionOptions):
        effect: Literal[EFFECT_KINDS] | None = None  # type: ignore[valid-type]
        """A symbol over its head with it: sweat, anger, idea, question, exclaim, sleep, hearts, stars, sparkle or tear."""

    run_time = 0.6
    reversible = True
    until_next_beat = True
    scene_targets = False

    def problems(self) -> list[tuple[str, str]]:
        names = self.config.targets()
        if len(names) != 1 or not names[0].replace("_", "").isalnum():
            return [("target", "host_react takes one expression (happy, surprised, worried... or the host's own)")]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`PoseChange` to the expression; the symbol popping in."""
        host = _host(scene, "host_react")
        self.symbols: list[EffectSymbol] = []
        if not host.present:
            return []
        character = host.character
        anims: list[Animation] = [self._change(character, character.posed_state(expression=self.config.targets()[0]))]
        kind = self.options.effect
        if kind is not None:
            symbol, appear = show_symbol(scene, character, kind, effect_color(kind, None, scene.theme.color))
            self.symbols.append(symbol)
            anims.append(appear)
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The expression before; the symbol shrinks away."""
        anims = self._undo() + [hide_symbol(symbol) for symbol in getattr(self, "symbols", [])]
        self.symbols = []
        return anims


def _fade_floor(floor: Mobject, start: float, end: float) -> Animation:
    """The floor line's opacity going from ``start`` to ``end``."""
    return UpdateFromAlphaFunc(floor, lambda m, alpha: m.set_stroke(opacity=start + (end - start) * alpha))


def _move_floor(floor: Mobject, to: np.ndarray) -> Animation:
    """The floor line fading out, moving to ``to`` half-way and fading in there."""
    def update(m: Mobject, alpha: float) -> None:
        if alpha >= 0.5:
            m.move_to(to)
        m.set_stroke(opacity=abs(1.0 - 2.0 * alpha))

    return UpdateFromAlphaFunc(floor, update)


def _walk_then_face(character: Character, x: float, facing: str, speed: float, **walk: Any) -> Animation:
    """A :class:`Walk` to ``x``, then a turn to ``facing`` (towards the content)."""
    turn = PoseChange(character, state=CharacterState(facing, dict(character.state().parts)), run_time=TURN_SECONDS)
    return Succession(Walk(character, x, speed=speed, **walk), turn)


def _view(scene: NarratedScene) -> tuple[float, float]:
    """The left and right x of what the camera shows now."""
    frame = scene.camera.frame
    middle = float(frame.get_center()[0])
    return middle - frame.width / 2, middle + frame.width / 2


@action("host_move")
class HostMoveAction(_HostAction):
    """The scene's host walks to the other side (``other_side``, the default, or ``left`` /
    ``right``) and turns to the content. Beside the content its column swaps sides and the content
    slides over with it (in a band below the content only the host walks). It stays there for
    the rest of the scene."""

    class Options(ActionOptions):
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second (the frame's shorter side is 8 units)."""

    run_time = 2.0
    needs_target = False
    scene_targets = False
    moves_camera = True

    def problems(self) -> list[tuple[str, str]]:
        return self._place_problems(MOVE_PLACES)

    def _plan(self, host: Any) -> Any:
        return host_move_plan(host.area, host.feet_x, host.room, host.side, host.layout.below, self._place() or "other_side")

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        host = _host(scene, "host_move")
        plan = self._plan(host)
        if plan is None or not host.present:
            return None
        distance = abs(plan.feet_x - plan.content_shift - host.feet_x)
        return _walk_time(host.character, distance, _speed(self.options, host.character)) + TURN_SECONDS

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The walk (and turn), the camera sliding the content, the floor line moving over."""
        host = _host(scene, "host_move")
        plan = self._plan(host)
        if plan is None or not host.present:
            return []
        character = host.character
        shift = host.content_shift + plan.content_shift
        facing = facing_for(plan.side, host.config.facing)
        anims: list[Animation] = [_walk_then_face(character, plan.feet_x - shift, facing, _speed(self.options, character))]
        if plan.content_shift:
            frame = scene.camera.frame
            center = np.array(frame.get_center())
            center[0] -= plan.content_shift
            anims.append(MoveCamera(scene, frame.width, center))
        if host.floor is not None:
            y = float(host.floor.get_center()[1])
            anims.append(_move_floor(host.floor, np.array([plan.feet_x - shift, y, 0.0])))
        host.side, host.feet_x, host.room, host.content_shift = plan.side, plan.feet_x, plan.reserve, shift
        return anims


class _Passage(_HostAction):
    """``host_enter`` / ``host_exit``: a walk between the host's place and beyond the view's edge
    (the target: ``left`` or ``right``; default its own side)."""

    class Options(ActionOptions):
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second (the frame's shorter side is 8 units)."""

    run_time = 2.0
    needs_target = False
    scene_targets = False
    #: Seconds it turns to the content at its end (an entrance does, an exit does not).
    turn_seconds = TURN_SECONDS

    def problems(self) -> list[tuple[str, str]]:
        return self._place_problems(("left", "right"))

    def _ends(self, scene: NarratedScene, host: Any) -> tuple[float, float]:
        """``(off screen x, its place's x)`` in scene coordinates."""
        left, right = _view(scene)
        return offstage_x(self._place() or host.side, left, right, host.half_reach), host.scene_x(host.feet_x)

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        host = _host(scene, self.config.action)
        away, home = self._ends(scene, host)
        return _walk_time(host.character, abs(home - away), _speed(self.options, host.character)) + self.turn_seconds


@action("host_enter")
class HostEnter(_Passage):
    """The scene's host walks in from beyond the edge of the view (``left`` or ``right``; default
    its own side) to its place and turns to the content, its floor line fading in. A scene with
    a ``host_enter`` before any ``host_exit`` starts without the host on screen (its room stays
    free)."""

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The walk in and the floor fading in."""
        host = _host(scene, "host_enter")
        if host.present:
            log.warning("scene '%s': host_enter, but the host is on screen already; skipped", scene.spec.id)
            return []
        away, home = self._ends(scene, host)
        character = host.character
        facing = facing_for(host.side, host.config.facing)
        anims = [_walk_then_face(character, home, facing, _speed(self.options, character), start_x=away)]
        if host.floor is not None:
            anims.append(_fade_floor(host.floor, 0.0, 1.0))
        host.present = True
        return anims


@action("host_exit")
class HostExit(_Passage):
    """The scene's host walks out beyond the edge of the view (``left`` or ``right``; default its
    own side), its floor line fading out; its room stays free (a ``host_enter`` brings it back)."""

    turn_seconds = 0.0

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The walk out and the floor fading out."""
        host = _host(scene, "host_exit")
        if not host.present:
            log.warning("scene '%s': host_exit, but the host is not on screen; skipped", scene.spec.id)
            return []
        away, _ = self._ends(scene, host)
        character = host.character
        anims: list[Animation] = [Walk(character, away, speed=_speed(self.options, character))]
        if host.floor is not None:
            anims.append(_fade_floor(host.floor, 1.0, 0.0))
        host.present = False
        host.pointing_at = None
        return anims
