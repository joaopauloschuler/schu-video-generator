"""Automatic directing of stage scenes (``auto_direct:``; DESIGN.md §69.23). No manim.

:func:`plan_directions` is a pure function from a scene's beats (who speaks, the line, the
actions written in the beat, the kinds of directing on) and its cast to the actions it adds, per
beat. Each added action is an ordinary :class:`~vidgen.config.ActionConfig` marked
:attr:`~vidgen.config.ActionConfig.auto`; :func:`with_auto_actions` appends them to the beats
before the scene plans its actions, so the action runner plays them like written ones.

Each kind of directing is one pass over a beat (:data:`_PASSES`, in :data:`DIRECTING_KINDS`
order), reading and updating one :class:`_SceneState` (who is on stage, where each looks, whom
each speaker talks to, the last reaction). A later kind (gestures, close-ups, shots) is one more
pass. Written actions always win: a character that a beat's own actions act on
(:data:`FRAMING_ACTIONS` aside) gets no automatic action in that beat.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any

from vidgen.config import DIRECTING_KINDS, ActionConfig, AutoDirectSetting, BeatConfig, SceneConfig, directing_kinds

if TYPE_CHECKING:
    from vidgen.project import Project

#: Actions that only frame, voice or point at a character: written ones leave it to automatic
#: directing in their beat.
FRAMING_ACTIONS = frozenset({"say", "zoom", "pan", "follow", "highlight", "dim", "callout"})
#: Written actions after which a character's look is not known (it turned, moved or took a pose).
LOOK_CHANGING = frozenset({"turn", "walk_to", "enter", "exit", "move_along", "keyframes", "pose", "emote"})
#: When an automatic reaction starts, as a fraction of the line: it plays in the pause after it.
REACTION_AT = 0.95
#: Expressions a listener reacts with, by the line's cue (:func:`line_cue`); never the same one
#: twice in a row for a character, so each cue has two.
REACTIONS: dict[str, tuple[str, str]] = {
    "question": ("thinking", "surprised"),
    "negation": ("worried", "sad"),
    "exclaim": ("surprised", "happy"),
}
#: Words that make a line a negation (English; apostrophes as typed or curly).
NEGATIONS = frozenset({
    "no", "not", "never", "nothing", "nobody", "none", "nope", "nowhere", "cannot", "can't", "won't", "don't",
    "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't", "shouldn't", "wouldn't", "couldn't", "haven't", "hasn't",
})
_WORD = re.compile(r"[A-Za-z']+")


@dataclass(frozen=True)
class CastMember:
    """A character on the stage as the planner sees it: its name and what its parts allow
    (:data:`~vidgen.cartoon.cast.ACTION_NEEDS` of ``look_at`` and ``emote``)."""

    name: str
    can_look: bool = True
    can_emote: bool = True


@dataclass(frozen=True)
class BeatInput:
    """One beat for the planner: its id, its line, who says it (characters on the stage), the
    actions written in it (resolved) and the kinds of directing on for it."""

    id: str
    text: str
    speakers: tuple[str, ...]
    actions: tuple[ActionConfig, ...] = ()
    kinds: frozenset[str] = frozenset()


@dataclass(frozen=True)
class DirectedBeat:
    """What automatic directing adds to one beat: its actions, after the written ones."""

    beat: str
    actions: tuple[ActionConfig, ...]


def line_cue(text: str) -> str | None:
    """What a line asks a listener to react to: ``question`` (a ``?``), ``negation`` (a word of
    :data:`NEGATIONS`), ``exclaim`` (a ``!``), in that order; ``None`` for a plain statement."""
    if "?" in text:
        return "question"
    words = {w.lower() for w in _WORD.findall(text.replace("’", "'"))}
    if words & NEGATIONS:
        return "negation"
    return "exclaim" if "!" in text else None


@dataclass
class _SceneState:
    """What the passes know while they walk through a scene's beats."""

    cast: dict[str, CastMember]
    present: set[str]
    looking: dict[str, str | None] = field(default_factory=dict)  # character -> what it last looked at
    addressed: dict[str, str] = field(default_factory=dict)       # speaker -> whom it last talked to
    spoken: list[tuple[str, ...]] = field(default_factory=list)   # the speakers of the lines so far
    reacted: dict[str, str] = field(default_factory=dict)         # character -> its last automatic reaction
    later: list[tuple[str, ...]] = field(default_factory=list)    # the speakers of the lines to come


@dataclass(frozen=True)
class _Beat:
    """A beat during planning: its input, the speakers on stage and the characters its written
    actions act on."""

    input: BeatInput
    speakers: tuple[str, ...]
    touched: frozenset[str]
    scene_id: str


def _named(patterns: Sequence[str], names: Sequence[str]) -> set[str]:
    """The characters ``patterns`` select (``kit``, ``k*``, a part ``kit.arm_left``)."""
    found: set[str] = set()
    for pattern in patterns:
        base = pattern.split(".", 1)[0]
        found |= {n for n in names if fnmatchcase(n, base)}
    return found


def _look(target: str, at: str) -> ActionConfig:
    return ActionConfig.automatic({"action": "look_at", "target": target, "to": at})


def _addressee(state: _SceneState, speaker: str) -> str | None:
    """Whom ``speaker`` talks to: the last other character who spoke, else the one it last
    talked to, else the next other one to speak, else the only other character on stage."""
    others = state.present - {speaker}
    for line in reversed(state.spoken):
        for name in line:
            if name in others:
                return name
    if state.addressed.get(speaker) in others:
        return state.addressed[speaker]
    for line in state.later:
        for name in line:
            if name in others:
                return name
    return next(iter(others)) if len(others) == 1 else None


def _plan_looks(state: _SceneState, beat: _Beat) -> list[ActionConfig]:
    """Listeners look at the (first) speaker; each speaker at the one it talks to. A look a
    character already has is not added again."""
    if not beat.speakers:
        return []
    added: list[ActionConfig] = []
    focus = beat.speakers[0]
    wanted = {name: focus for name in sorted(state.present - set(beat.speakers))}
    for speaker in beat.speakers:
        other = _addressee(state, speaker)
        if other is not None:
            state.addressed[speaker] = other
            wanted[speaker] = other
    for name in [n for n in state.cast if n in wanted]:   # in the stage's order
        member = state.cast[name]
        if name in beat.touched or not member.can_look or state.looking.get(name) == wanted[name]:
            continue
        added.append(_look(name, wanted[name]))
        state.looking[name] = wanted[name]
    return added


def _plan_reactions(state: _SceneState, beat: _Beat) -> list[ActionConfig]:
    """Each listener reacts to a line with a cue (:func:`line_cue`) in the pause after it: one
    of the cue's :data:`REACTIONS`, picked by a generator seeded with the scene, beat and
    character, never the expression of its last automatic reaction."""
    cue = line_cue(beat.input.text) if beat.speakers else None
    if cue is None:
        return []
    added: list[ActionConfig] = []
    for name, member in state.cast.items():
        if name not in state.present or name in beat.speakers or name in beat.touched or not member.can_emote:
            continue
        choices = [e for e in REACTIONS[cue] if e != state.reacted.get(name)]
        expression = random.Random(f"{beat.scene_id}/{beat.input.id}/{name}").choice(choices)
        state.reacted[name] = expression
        added.append(ActionConfig.automatic({"action": "react", "target": name, "expression": expression, "at": REACTION_AT}))
    return added


#: The passes of each kind of directing (Step 90 adds gestures and close-ups).
_PASSES: dict[str, Callable[[_SceneState, _Beat], list[ActionConfig]]] = {
    "looks": _plan_looks,
    "reactions": _plan_reactions,
}


def _follow_written(state: _SceneState, beat: BeatInput, names: Sequence[str]) -> None:
    """Update the state with the beat's written actions: entrances and exits, looks and what
    makes a look unknown."""
    for act in beat.actions:
        targets = _named(act.targets(), names)
        if act.action == "enter":
            state.present |= targets
        elif act.action == "exit":
            state.present -= targets
        if act.action == "look_at":
            to = act.options.get("to")
            for name in targets:
                state.looking[name] = to if isinstance(to, str) else None
        elif act.action in LOOK_CHANGING:
            for name in targets:
                state.looking[name] = None


def plan_directions(scene_id: str, cast: Sequence[CastMember], beats: Sequence[BeatInput]) -> list[DirectedBeat]:
    """The actions automatic directing adds to each beat of a stage scene (DESIGN.md §69.23):
    for each beat with kinds on, the passes of those kinds in :data:`DIRECTING_KINDS` order.
    Pure: the same input gives the same actions. Characters an ``enter`` of the scene brings in
    are off stage until their first ``enter`` beat; an ``exit`` takes them off."""
    names = [m.name for m in cast]
    entering = {n for b in beats for act in b.actions if act.action == "enter" for n in _named(act.targets(), names)}
    state = _SceneState(cast={m.name: m for m in cast}, present=set(names) - entering)
    directed: list[DirectedBeat] = []
    for k, beat in enumerate(beats):
        state.later = [b.speakers for b in beats[k + 1 :]]
        _follow_written(state, beat, names)
        touched = set()
        for act in beat.actions:
            if act.action not in FRAMING_ACTIONS:
                touched |= _named(act.targets(), names)
        current = _Beat(beat, tuple(s for s in beat.speakers if s in state.present), frozenset(touched), scene_id)
        added = [a for kind in DIRECTING_KINDS if kind in beat.kinds and kind in _PASSES for a in _PASSES[kind](state, current)]
        if current.speakers:
            state.spoken.append(current.speakers)
        if added:
            directed.append(DirectedBeat(beat.id, tuple(added)))
    return directed


def with_auto_actions(spec: SceneConfig, directed: Sequence[DirectedBeat]) -> SceneConfig:
    """``spec`` with each beat's automatic actions appended to its written ones (a copy; ``spec``
    is unchanged)."""
    if not directed:
        return spec
    added = {d.beat: d.actions for d in directed}
    beats = [b.model_copy(update={"actions": [*b.actions, *added[b.id]]}) if b.id in added else b for b in spec.beats]
    return spec.model_copy(update={"beats": beats})


# ----- gathering a scene's input (reads the project) ---------------------------------------------------


def _resolved_actions(beat: BeatConfig, known: Sequence[str]) -> tuple[ActionConfig, ...]:
    return tuple(act.resolved(known) for act in beat.actions)


def stage_directions(project: Project, spec: SceneConfig, characters: Sequence[str], setting: AutoDirectSetting | None) -> list[DirectedBeat]:
    """The automatic actions of a stage scene ``spec`` with ``characters`` on it (in the stage's
    order) and the stage's ``auto_direct`` ``setting``: reads who speaks each beat (its ``say``
    actions, else its voice), the characters' parts (a ``look: {svg}`` from the project folder)
    and the video's setting, then :func:`plan_directions`. Needs the project's registry (a
    project session) for the action names."""
    from vidgen import registry
    from vidgen.cartoon.cast import beat_voice, character_part_shapes, missing_needs, speaking_characters
    from vidgen.errors import VidgenError

    config = project.config
    kinds = [directing_kinds(beat.auto_direct, setting, config.auto_direct) for beat in spec.beats]
    if not any(kinds):
        return []
    entries = {e.name: e for e in config.characters}
    cast: list[CastMember] = []
    for name in characters:
        try:
            shapes: Mapping[str, Any] | None = character_part_shapes(entries[name], project.root)
        except (KeyError, VidgenError):
            shapes = None
        cast.append(CastMember(
            name,
            can_look=shapes is not None and missing_needs(shapes, "look_at") is None,
            can_emote=shapes is not None and missing_needs(shapes, "emote") is None,
        ))
    known = registry.action_names()
    beats: list[BeatInput] = []
    for beat, on in zip(spec.beats, kinds):
        written = _resolved_actions(beat, known)
        said = [act for act in written if act.action == "say"]
        if said:
            speakers = [n for n in characters if n in _named([p for act in said for p in act.targets()], characters)]
        else:
            speakers = speaking_characters(config, beat_voice(spec, beat), characters)
        beats.append(BeatInput(beat.id, beat.text, tuple(speakers), written, on))
    return plan_directions(spec.id, cast, beats)


def project_directions(project: Project, scenes: Sequence[str] | None = None) -> dict[str, list[DirectedBeat]]:
    """Each scene's automatic actions (scene id -> its directed beats; scenes with none left
    out), for ``scenes`` or every scene: what each scene type's
    :meth:`~vidgen.scene.NarratedScene.auto_actions` adds. Call it in a project session; raises
    :class:`~vidgen.errors.VidgenError` for a scene whose params are invalid."""
    from vidgen import registry

    found: dict[str, list[DirectedBeat]] = {}
    for spec in project.config.scenes:
        if scenes is not None and spec.id not in scenes:
            continue
        cls = registry.get(spec.type).cls
        directed = cls.auto_actions(project, spec, cls.parse_params(spec.params, scene_id=spec.id))
        if directed:
            found[spec.id] = directed
    return found


def directing_used(project: Project) -> bool:
    """Whether ``auto_direct`` is set anywhere (the video, a scene's params, a beat): a cheap
    check before :func:`project_directions`."""
    config = project.config
    if config.auto_direct:
        return True
    return any(spec.params.get("auto_direct") or any(b.auto_direct for b in spec.beats) for spec in config.scenes)


def auto_label(act: ActionConfig) -> str:
    """``look_at kit pip`` / ``react pip surprised``: the action, its target and option values
    (for the storyboard)."""
    return " ".join([act.action, *act.targets(), *(str(v) for v in act.options.values())])


def directions_yaml(directed: Mapping[str, Sequence[DirectedBeat]]) -> str:
    """The automatic actions (scene id -> directed beats) as ``video.yaml`` text an author can
    paste and edit: ``scenes`` -> each scene's ``id`` and ``beats`` -> each beat's ``id`` and its
    added ``actions``, one action per line in the shorthand form."""
    import yaml

    def flow(data: Any) -> str:
        """``data`` on one line; a scalar quoted only when YAML needs it (``"yes"``)."""
        text = yaml.safe_dump([data], default_flow_style=True, sort_keys=False, width=10**6, allow_unicode=True).strip()
        return text[1:-1]

    lines = [
        "# Actions auto_direct adds (vidgen direct --print). Paste a beat's actions into its actions: list",
        "# and edit them: actions written in a beat win, so the automatic ones for those characters go away.",
    ]
    if not directed:
        return "\n".join([*lines, "# Nothing added: auto_direct is off, or no character speaks to another on a stage.", "scenes: []", ""])
    lines.append("scenes:")
    for scene_id, beats in directed.items():
        lines += [f"  - id: {flow(scene_id)}", "    beats:"]
        for beat in beats:
            lines += [f"      - id: {flow(beat.beat)}", "        actions:"]
            lines += [f"          - {flow(act.shorthand())}" for act in beat.actions]
    return "\n".join(lines) + "\n"
