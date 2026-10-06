"""Per-beat actions (DESIGN.md §26): named targets, the ``Action`` base class, validation and the
runner that plays actions inside their beat.

A beat's ``actions`` (``vidgen.config.ActionConfig``) name an action type (``@action``, see
``vidgen.registry``) and targets of the scene (``item3``, ``bar:Preview 480p``). Scenes register
their targets with :meth:`NarratedScene.target <vidgen.scene.NarratedScene.target>` and declare
the names statically in ``target_names(params)`` so ``vidgen validate`` can check them.

Timing: an action is due at ``at`` x the beat's narration after the beat starts. It starts in the
first wait of the scene at or after that moment (so it never fights the scene's own animation of
the same objects) and runs for its ``run_time``, shortened so the beat never lasts longer than
its narration plus ``narration.pad``.
"""

from __future__ import annotations

import difflib
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from manim import Animation, Mobject, config
from pydantic import BaseModel, ConfigDict, ValidationError

from vidgen.config import ACTION_KEYS, ActionConfig, SceneConfig, validation_problems
from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.registry import ActionType
    from vidgen.scene import NarratedScene
    from vidgen.theme import Theme

log = logging.getLogger("vidgen.actions")

#: A target name: an identifier (``heading``, ``item3``), optionally ``kind:label`` (``bar:4K``).
TARGET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?::.+)?$", re.S)
#: How many target names an "unknown target" message lists.
_SHOWN_NAMES = 14


@dataclass(eq=False)
class Target:
    """A named part of a scene that actions can act on.

    ``names`` (the first is the main name) are what ``target:`` refers to; ``mobject`` is the
    part (it may be a group that is not itself added to the scene); ``entrance`` builds the
    scene's own animations that bring it on screen (default ``FadeIn``).
    """

    names: tuple[str, ...]
    mobject: Mobject
    entrance: Callable[[], Sequence[Animation]] | None = None

    @property
    def name(self) -> str:
        """The main name."""
        return self.names[0]


class ActionOptions(BaseModel):
    """Base class of an action type's ``Options`` model; unknown keys are an error.

    Fields may use ``ThemeColor`` / ``ThemeSize`` (checked against the project's theme). Field
    names must differ from the keys every action has (``action``, ``target``, ``at``, ``until``,
    ``run_time``).
    """

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)


class Action:
    """Base class of a per-beat action type (register with ``@action("name")``).

    One instance is made per use in the config (so it can remember state for :meth:`revert`);
    ``self.options`` is the validated ``Options`` and ``self.config`` the
    :class:`~vidgen.config.ActionConfig`. Subclasses implement :meth:`apply` (and
    :meth:`revert` when ``reversible``).
    """

    #: Options of this action (keys besides ``action``/``target``/``at``/``until``/``run_time``).
    Options: ClassVar[type[ActionOptions]] = ActionOptions
    #: Seconds the animation takes by default (``run_time:`` in the config overrides it).
    run_time: ClassVar[float] = 0.6
    #: Whether ``until:`` may undo it (then :meth:`revert` must be implemented).
    reversible: ClassVar[bool] = False
    #: Targets not on screen yet are first brought in with their entrance animation.
    needs_visible: ClassVar[bool] = True
    #: Whether the action needs a ``target``.
    needs_target: ClassVar[bool] = True

    def __init__(self, options: ActionOptions, config: ActionConfig) -> None:
        self.options = options
        self.config = config

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The animations that perform the action on ``targets`` (played together; an empty
        list means nothing to do). Build them from the targets' current state."""
        raise NotImplementedError

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The animations that undo :meth:`apply` (for ``until:``)."""
        return []


def check_action_class(name: str, cls: object) -> None:
    """Raise :class:`VidgenError` unless ``cls`` is a usable action class."""
    if not (isinstance(cls, type) and issubclass(cls, Action)):
        raise VidgenError(f"@action({name!r}) must decorate a subclass of Action, got {cls!r}")
    where = f"action '{name}' ({cls.__qualname__})"
    options = cls.Options
    if not (isinstance(options, type) and issubclass(options, ActionOptions)):
        raise VidgenError(f"{where}: 'Options' must be a subclass of ActionOptions")
    clash = sorted(set(options.model_fields) & set(ACTION_KEYS))
    if clash:
        raise VidgenError(f"{where}: option names {', '.join(clash)} are reserved (every action has {', '.join(ACTION_KEYS)})")
    if not (isinstance(cls.run_time, (int, float)) and cls.run_time > 0):
        raise VidgenError(f"{where}: run_time must be a positive number of seconds")
    if cls.apply is Action.apply:
        raise VidgenError(f"{where}: implement apply(self, scene, targets)")
    if cls.reversible and cls.revert is Action.revert:
        raise VidgenError(f"{where}: reversible actions implement revert(self, scene, targets)")


# ----- target names --------------------------------------------------------------------------------


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    return re.compile("".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern), re.S)


def match_names(pattern: str, names: Sequence[str]) -> list[str]:
    """The names ``pattern`` selects: itself, or with ``*``/``?`` wildcards every match."""
    if "*" not in pattern and "?" not in pattern:
        return [pattern] if pattern in names else []
    regex = _pattern_regex(pattern)
    return [n for n in names if regex.fullmatch(n)]


def supported_scene_types() -> list[str]:
    """Registered scene types that declare action targets."""
    from vidgen import registry

    return [e.name for e in registry.all() if e.cls.target_patterns]


def unknown_target_message(pattern: str, scene_type: str, names: Sequence[str], patterns: Sequence[str]) -> str:
    """``unknown target 'x'`` with close matches and the scene's targets."""
    if not names:
        supported = ", ".join(supported_scene_types()) or "none"
        return f"scene type '{scene_type}' has no action targets (types with targets: {supported})"
    unique = list(dict.fromkeys(names))
    message = f"unknown target '{pattern}' for scene type '{scene_type}'"
    close = difflib.get_close_matches(pattern, unique, n=3)
    if close:
        message += f"; did you mean {' or '.join(repr(c) for c in close)}?"
    shown = ", ".join(unique[:_SHOWN_NAMES]) + (f", ... ({len(unique) - _SHOWN_NAMES} more)" if len(unique) > _SHOWN_NAMES else "")
    return message + f" (targets: {shown}; forms: {', '.join(patterns)}; * and ? match several)"


# ----- validation ----------------------------------------------------------------------------------


@dataclass(eq=False)
class ActionUse:
    """One action of a beat, validated: its type, an instance with its options, and whether it
    has been applied (so ``until`` knows what to undo)."""

    beat: str
    location: str
    config: ActionConfig
    kind: ActionType
    action: Action
    applied: bool = False
    targets: list[Target] = field(default_factory=list)

    @property
    def run_time(self) -> float:
        """The configured run time, else the action type's default."""
        return float(self.config.run_time or self.kind.cls.run_time)


def scene_actions(
    scene_type: str, cls: type[NarratedScene], spec: SceneConfig, params: Any, theme: Theme | None
) -> tuple[list[ActionUse], list[tuple[str, str]]]:
    """Validate the actions of every beat of ``spec``: ``(uses, problems)``.

    Problems are ``(location, message)`` with locations relative to the scene
    (``beats[1].actions[0].target``). ``params`` are the validated params (``None`` when they
    are invalid: targets are then not checked).
    """
    from vidgen import registry

    uses: list[ActionUse] = []
    problems: list[tuple[str, str]] = []
    names = cls.target_names(params) if params is not None else None
    known = registry.action_names()
    for j, beat in enumerate(spec.beats):
        for k, act in enumerate(beat.actions):
            where = f"beats[{j}].actions[{k}]"
            act = act.resolved(known)
            kind = registry.find_action(act.action)
            if kind is None:
                problems.append((f"{where}.action", registry.unknown_action_message(act.action)))
                continue
            try:
                options = kind.cls.Options.model_validate(act.options, context={"theme": theme})
            except ValidationError as exc:
                problems += [(f"{where}.{p.location}", p.message) for p in validation_problems(exc)]
                continue
            found = len(problems)
            if act.until is not None and not kind.cls.reversible:
                reversible = ", ".join(e.name for e in registry.all_actions() if e.cls.reversible) or "none"
                problems.append((f"{where}.until", f"action '{act.action}' cannot be undone; until works with: {reversible}"))
            if kind.cls.needs_target and not act.targets():
                problems.append((f"{where}.target", f"action '{act.action}' needs a target"))
            for pattern in act.targets() if names is not None else []:
                if not match_names(pattern, names):
                    problems.append((f"{where}.target", unknown_target_message(pattern, scene_type, names, cls.target_patterns)))
            if len(problems) == found:
                uses.append(ActionUse(beat.id, where, act, kind, kind.cls(options, act)))
    return uses, problems


def plan_actions(scene_type: str, cls: type[NarratedScene], spec: SceneConfig, params: Any, theme: Theme | None) -> list[ActionUse]:
    """:func:`scene_actions`, raising one :class:`VidgenError` listing every problem."""
    uses, problems = scene_actions(scene_type, cls, spec, params, theme)
    if problems:
        lines = [f"scene '{spec.id}': invalid actions", *(f"  {loc}: {msg}" for loc, msg in problems)]
        raise VidgenError("\n".join(lines))
    return uses


# ----- runtime -------------------------------------------------------------------------------------


@dataclass(eq=False)
class _Due:
    frame: int
    use: ActionUse
    revert: bool


class ActionRunner:
    """Plays a scene's actions inside its beats (owned by :class:`~vidgen.scene.NarratedScene`).

    ``start_beat`` schedules the beat's actions (and the undoing of earlier ones whose ``until``
    is this beat); the scene's waits call :meth:`wait`, which splits a wait at due actions and
    plays them; ``end_beat`` applies whatever found no time (without animation, logged).
    """

    #: Seconds given to bringing hidden targets on screen before an action that needs them.
    reveal_time = 0.6

    def __init__(self, scene: NarratedScene, uses: list[ActionUse]) -> None:
        self.scene = scene
        self.uses = uses
        self._pending: list[_Due] = []
        self._end = 0
        self._beat = ""

    def _now(self) -> int:
        return round(float(self.scene.renderer.time) * config.frame_rate)

    @property
    def pending(self) -> bool:
        """Whether actions of the current beat are still to run."""
        return bool(self._pending)

    def start_beat(self, beat_id: str, d: float, pad: float) -> None:
        """Schedule the beat's actions: undoing (``until`` = this beat) first, then its own by ``at``."""
        fps = config.frame_rate
        now = self._now()
        self._beat = beat_id
        self._end = now + round((d + pad) * fps)
        due = [_Due(now, u, True) for u in self.uses if u.config.until == beat_id and u.applied]
        due += [_Due(now + round(u.config.at * d * fps), u, False) for u in self.uses if u.beat == beat_id]
        self._pending = sorted(due, key=lambda x: x.frame)

    def wait(self, frames: int) -> None:
        """Wait ``frames`` frames, playing the actions that fall due meanwhile."""
        end = self._now() + frames
        while self._pending and self._pending[0].frame < end:
            now = self._now()
            if self._pending[0].frame > now:
                self.scene._wait_frames(self._pending[0].frame - now)
            self._run(self._take(self._now()), instant=False)
        remaining = end - self._now()
        if remaining > 0:
            self.scene._wait_frames(remaining)

    def end_beat(self) -> None:
        """Apply the actions that never found time in the beat, without animation."""
        if self._pending:
            left = self._take(None)
            names = ", ".join(("undo " if d.revert else "") + d.use.config.describe() for d in left)
            log.warning("scene '%s' beat '%s': no time left for actions (%s); applied without animation", self.scene.spec.id, self._beat, names)
            self._run(left, instant=True)
        self._pending = []

    def _take(self, frame: int | None) -> list[_Due]:
        due = [d for d in self._pending if frame is None or d.frame <= frame]
        self._pending = [d for d in self._pending if d not in due]
        return due

    def _resolve(self, use: ActionUse) -> list[Target]:
        """The registered targets the use's patterns select (in registration order)."""
        found: list[Target] = []
        for pattern in use.config.targets():
            matches = self.scene.find_targets(pattern)
            if not matches:
                names = [n for t in self.scene.targets for n in t.names]
                message = unknown_target_message(pattern, self.scene.spec.type, names, type(self.scene).target_patterns)
                raise VidgenError(f"scene '{self.scene.spec.id}' {use.location}: {message}")
            found += [t for t in matches if t not in found]
        return found

    def _phases(self, due: list[_Due]) -> list[tuple[Callable[[], list[Animation]], float]]:
        """Hidden targets' entrances first, then batches of actions whose targets do not overlap."""
        scene = self.scene
        for d in due:
            d.use.targets = self._resolve(d.use)
        hidden: list[Target] = []
        for d in due:
            if not d.revert and d.use.kind.cls.needs_visible:
                hidden += [t for t in d.use.targets if t not in hidden and not scene.is_shown(t)]
        phases: list[tuple[Callable[[], list[Animation]], float]] = []
        if hidden:
            phases.append((lambda: [a for t in hidden for a in scene.entrance(t)], self.reveal_time))
        batch: list[_Due] = []
        batches = [batch]
        for d in due:
            mobs = {id(m) for t in d.use.targets for m in t.mobject.get_family()}
            taken = {id(m) for b in batch for t in b.use.targets for m in t.mobject.get_family()}
            if mobs & taken:
                batch = []
                batches.append(batch)
            batch.append(d)
        for b in batches:
            if b:
                phases.append((lambda b=b: self._build(b), max(d.use.run_time for d in b)))
        return phases

    def _build(self, batch: list[_Due]) -> list[Animation]:
        anims: list[Animation] = []
        for d in batch:
            act = d.use.action
            anims += act.revert(self.scene, d.use.targets) if d.revert else act.apply(self.scene, d.use.targets)
            d.use.applied = not d.revert
        return anims

    def _run(self, due: list[_Due], instant: bool) -> None:
        """Play ``due`` within the beat's remaining time (proportionally shortened if needed)."""
        if not due:
            return
        fps = config.frame_rate
        phases = self._phases(due)
        budget = max(self._end - self._now(), 0) / fps
        total = sum(p[1] for p in phases)
        factor = min(1.0, budget / total) if total > 0 else 1.0
        for build, natural in phases:
            anims = build()
            if not anims:
                continue
            frames = int(natural * factor * fps + 1e-6)  # whole frames: the beat's end stays exact
            if instant or frames < 1:
                self.scene._apply_now(anims)
                continue
            self.scene._requested = natural if factor < 1 - 1e-9 else None
            try:
                self.scene.play(*anims, run_time=frames / fps)
            finally:
                self.scene._requested = None
