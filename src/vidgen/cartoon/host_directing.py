"""Automatic directing of a cartoon host (``auto_direct`` with ``host:``; DESIGN.md §71.2). No manim.

:func:`plan_host_directions` is a pure function from a scene's beats (the actions written in each,
the kinds of directing on, what the scene's own reveal shows in it) to the host actions it adds,
per beat: the host points at each newly revealed item once (at most one point per beat), looks at
what a beat highlights (a written ``highlight`` / ``callout`` / ``zoom``) or reveals when it does
not point, and reacts to results (a chart going up: happy; down: worried; a code error:
surprised). It never adds a move: ``host_move`` / ``host_enter`` / ``host_exit`` change the layout
(the content slides), so they are the author's; in a beat with one the host gets nothing
automatic, and ``vidgen validate`` allows one move per beat. Written host actions win: a beat's
written ``host_point`` / ``host_look`` stop the automatic point and look, a written
``host_react`` the automatic reaction.

What a scene type reveals is its :meth:`~vidgen.scene.NarratedScene.reveal_steps` (one
:class:`RevealStep` per step of its reveal, mapped to beats as ``reveal()`` does, with
:func:`~vidgen.layout.distribute`); a type without them gives the host only the looks at written
highlights. Every added action is lint-safe by construction: a pointing hand stays in the host's
room (:func:`~vidgen.cartoon.host.hand_goal`), looks and reactions move only the host, and no
pointer line is added.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from vidgen.cartoon.directing import DirectedBeat
from vidgen.cartoon.host import HOST_MOVES, scene_host
from vidgen.config import ActionConfig, SceneConfig, directing_kinds
from vidgen.layout import distribute

if TYPE_CHECKING:
    from vidgen.project import Project

#: What a reveal step shows: a rise, a fall, an error, or nothing to react to.
Result = Literal["rise", "fall", "error"]
#: The host's reaction to each result, and the effect symbol with it (``effects`` kind on).
HOST_REACTIONS: dict[str, str] = {"rise": "happy", "fall": "worried", "error": "surprised"}
HOST_EFFECTS: dict[str, str] = {"rise": "sparkle", "fall": "sweat", "error": "exclaim"}
#: When an automatic reaction starts (a fraction of the beat's narration): after the point.
REACT_AT = 0.4
#: A change smaller than this share of the largest value is no rise or fall.
TREND_SHARE = 0.05
#: Written actions whose first target is what the beat highlights (the host looks at it).
HIGHLIGHTING = ("highlight", "callout", "zoom")
_ERROR_TEXT = re.compile(r"error|exception|traceback|\bfail(?:ed|ure|s)?\b|\bpanic\b", re.IGNORECASE)


@dataclass(frozen=True)
class RevealStep:
    """One step of a scene's own reveal as host directing sees it: the target the step shows or
    marks (``focus``, a target name of the scene) and what it shows (``result``: ``rise``,
    ``fall``, ``error`` or ``None``)."""

    focus: str
    result: Result | None = None


def value_trend(values: Sequence[float]) -> Result | None:
    """``rise`` when the last value is above the first by more than :data:`TREND_SHARE` of the
    largest value's size, ``fall`` when below, else ``None`` (also for fewer than two values)."""
    if len(values) < 2:
        return None
    scale = max(abs(v) for v in values) or 1.0
    change = (values[-1] - values[0]) / scale
    return "rise" if change > TREND_SHARE else "fall" if change < -TREND_SHARE else None


def has_error_text(lines: Sequence[str]) -> bool:
    """Whether code ``lines`` show an error: error, exception, traceback, fail(ed / ure / s),
    panic (any case; ``ValueError`` counts)."""
    return any(_ERROR_TEXT.search(line) for line in lines)


@dataclass(frozen=True)
class HostBeat:
    """One beat for the host planner: its id, its written actions (resolved), the kinds of
    directing on for it (:data:`~vidgen.config.DIRECTING_KINDS`: ``looks``, ``gestures`` =
    points, ``reactions``, ``effects`` = a symbol with a reaction) and the reveal steps it plays."""

    id: str
    actions: tuple[ActionConfig, ...] = ()
    kinds: frozenset[str] = frozenset()
    steps: tuple[RevealStep, ...] = ()


def _auto(data: dict[str, Any]) -> ActionConfig:
    return ActionConfig.automatic(data)


def plan_host_directions(beats: Sequence[HostBeat], *, present: bool = True) -> list[DirectedBeat]:
    """The host actions automatic directing adds to each beat (module docstring); ``present``:
    the host is on screen when the scene starts (no ``host_enter`` brings it in first). Pure."""
    pointed: set[str] = set()
    directed: list[DirectedBeat] = []
    for beat in beats:
        written = {act.action for act in beat.actions}
        moving = bool(written & HOST_MOVES)
        here = present
        for act in beat.actions:   # one move per beat (validate), so this is where it ends up
            if act.action in ("host_enter", "host_exit"):
                present = act.action == "host_enter"
        if moving or not here or not beat.kinds:
            continue
        added: list[ActionConfig] = []
        focus = [step.focus for step in beat.steps]
        if "gestures" in beat.kinds and not written & {"host_point", "host_look"}:
            fresh = next((name for name in focus if name not in pointed), None)
            if fresh is not None:
                pointed.add(fresh)
                added.append(_auto({"action": "host_point", "target": fresh}))
        if "looks" in beat.kinds and not added and not written & {"host_point", "host_look"}:
            marked = next((act for act in beat.actions if act.action in HIGHLIGHTING and act.targets()), None)
            if marked is not None:
                added.append(_auto({"action": "host_look", "target": marked.targets()[0], "at": marked.at}))
            elif focus:
                added.append(_auto({"action": "host_look", "target": focus[0]}))
        result = next((step.result for step in beat.steps if step.result is not None), None)
        if "reactions" in beat.kinds and result is not None and "host_react" not in written:
            react: dict[str, Any] = {"action": "host_react", "target": HOST_REACTIONS[result], "at": REACT_AT}
            if "effects" in beat.kinds:
                react["effect"] = HOST_EFFECTS[result]
            added.append(_auto(react))
        if added:
            directed.append(DirectedBeat(beat.id, tuple(added)))
    return directed


def starts_present(actions: Sequence[ActionConfig]) -> bool:
    """Whether the host is on screen when the scene starts: unless its first ``host_enter`` /
    ``host_exit`` (``actions`` in beat order) is an enter."""
    first = next((act.action for act in actions if act.action in ("host_enter", "host_exit")), None)
    return first != "host_enter"


def host_directions(project: Project, spec: SceneConfig, scene_cls: Any, params: Any) -> list[DirectedBeat]:
    """The host actions automatic directing adds to scene ``spec`` (validated ``params``) of type
    ``scene_cls``: none without a host, or when ``auto_direct`` (the beat's, else the host's,
    else the video's) is off in every beat. Reads the beats' written actions (resolved with the
    registered action names: call it in a project session) and the type's
    :meth:`~vidgen.scene.NarratedScene.reveal_steps`, then :func:`plan_host_directions`."""
    from vidgen import registry

    config = project.config
    if not getattr(scene_cls, "takes_host", False) or not spec.beats:
        return []
    try:
        host = scene_host(config, spec)
    except (ValueError, ValidationError):
        return []
    if host is None:
        return []
    kinds = [directing_kinds(beat.auto_direct, host.auto_direct, config.auto_direct) for beat in spec.beats]
    if not any(kinds):
        return []
    steps = list(scene_cls.reveal_steps(params)) if params is not None else []
    plan = distribute(len(steps), len(spec.beats)) if steps else [[] for _ in spec.beats]
    known = registry.action_names()
    beats = [
        HostBeat(beat.id, tuple(act.resolved(known) for act in beat.actions), on, tuple(steps[k] for k in plan[j]))
        for j, (beat, on) in enumerate(zip(spec.beats, kinds))
    ]
    every = [act for beat in beats for act in beat.actions]
    return plan_host_directions(beats, present=starts_present(every))
