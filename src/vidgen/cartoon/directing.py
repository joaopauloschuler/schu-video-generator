"""Automatic directing of stage scenes (``auto_direct:``; DESIGN.md §69.23). No manim.

:func:`plan_directions` is a pure function from a scene's beats (who speaks, the line, the
actions written in the beat, the kinds of directing on) and its cast to the actions it adds, per
beat. Each added action is an ordinary :class:`~vidgen.config.ActionConfig` marked
:attr:`~vidgen.config.ActionConfig.auto`; :func:`with_auto_actions` appends them to the beats
before the scene plans its actions, so the action runner plays them like written ones.

Each kind of directing is one pass over a beat (:data:`_PASSES`, in :data:`DIRECTING_KINDS`
order), reading and updating one :class:`_SceneState` (who is on stage, where each stands, looks
and faces, whom each speaker talks to, the last reaction and gesture). A later kind (shots) is
one more pass. Written actions always win: a character that a beat's own actions act on
(:data:`FRAMING_ACTIONS` aside) gets no automatic action in that beat.

With the stage's geometry (:class:`StageFrame`, from :func:`~vidgen.cartoon.stage.stage_layout`,
no rendering) the planner checks each look, arm gesture and close-up it adds: it predicts the
beat's still with and without the action and runs the lint rules of :data:`CHECKED_RULES` on
both; an action that would add a finding is not added (DESIGN.md §69.24).
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any

from vidgen.camera import Bounds, view_center_within
from vidgen.cartoon.acting import GESTURE_EASE, GESTURE_SECONDS, GESTURES, look_pose, nearer_side
from vidgen.cartoon.stage import mark_x
from vidgen.config import DIRECTING_KINDS, ActionConfig, AutoDirectSetting, BeatConfig, SceneConfig, directing_kinds

if TYPE_CHECKING:
    from vidgen.lint.rules import StillContext
    from vidgen.project import Project
    from vidgen.speech import WordTime

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

# ----- gestures and close-ups (Step 90) -----

#: Stressed words that call for a gesture of their own (English; besides :data:`NEGATIONS`,
#: which shake the head).
AFFIRMATIONS = frozenset({"yes", "yeah", "yep", "sure", "right", "exactly", "okay", "ok", "indeed", "agreed"})
GREETINGS = frozenset({"hello", "hi", "hey", "bye", "goodbye", "welcome"})
POINTING = frozenset({"this", "that", "these", "those", "here", "there", "look", "you", "your"})
#: Gestures for a stressed word without one of its own, tried in an order seeded by the scene,
#: beat and speaker (the speaker's last automatic gesture last).
EMPHASIS_GESTURES: tuple[str, ...] = ("point", "nod", "shrug")
#: The longest word of a line is stressed from this many letters, and only when its speaker did
#: not gesture in its previous line (an emphasised or all-capitals word always is).
LONG_WORD_LETTERS = 6
#: How long an automatic look takes (seconds, ``look_at``'s run time): a gesture of the same
#: character in the beat starts after it.
LOOK_SECONDS = 0.5
#: A close-up: a line of at most :data:`SHORT_LINE_WORDS` words right after a beat of at least
#: :data:`LONG_LINE_WORDS`; a ``zoom`` on the speaker by :data:`CLOSEUP_SCALE`, moving in and
#: back in :data:`CLOSEUP_SECONDS` each when both fit in 80 % of the narration (after the
#: speaker's look), else cutting in and back (:data:`CLOSEUP_CUT_SECONDS`: under a frame at
#: 25 fps, so the action runner never has to rush it).
SHORT_LINE_WORDS = 5
LONG_LINE_WORDS = 8
CLOSEUP_SCALE: float = 2
CLOSEUP_SECONDS = 0.5
CLOSEUP_CUT_SECONDS = 0.03
#: Written actions during which no close-up is added: walks and other moves of a character, and
#: the camera's own moves.
MOVING_ACTIONS = frozenset({"walk_to", "enter", "exit", "move_along", "keyframes", "pan", "follow", "zoom"})
#: A generated figure's proportions, in its heights (measured on the generator's looks; an SVG
#: look is taken to be alike): half its width, the bottom of its face box (above its feet), and
#: how far an arm gesture reaches from its middle (``point`` and ``wave`` forward, ``shrug`` to
#: both sides).
FIGURE_HALF_WIDTH = 0.21
FACE_BOTTOM = 0.5
GESTURE_REACH: dict[str, float] = {"point": 0.4, "wave": 0.35, "shrug": 0.34}
#: The lint rules (DESIGN.md §69.17) the planner runs on its predicted stills. ``bubble_overlap``
#: needs no check: automatic actions draw no bubble and move no face, and no close-up is added
#: to a beat with a speech bubble (the bubble is placed for the view at its start).
CHECKED_RULES: tuple[str, ...] = ("off_stage", "facing_away")
#: Pixels per Manim unit of a predicted still.
_PX = 100.0


@dataclass(frozen=True)
class CastMember:
    """A character on the stage as the planner sees it: its name and what its parts allow
    (:data:`~vidgen.cartoon.cast.ACTION_NEEDS` of ``look_at`` and ``emote``)."""

    name: str
    can_look: bool = True
    can_emote: bool = True
    gestures: tuple[str, ...] = ()
    """The gestures its parts allow (``gesture: <kind>`` of ``ACTION_NEEDS``)."""


@dataclass(frozen=True)
class BeatInput:
    """One beat for the planner: its id, its line, who says it (characters on the stage), the
    actions written in it (resolved), the kinds of directing on for it, and its narration's
    length (``seconds``) and word times (from its start; none: no gestures)."""

    id: str
    text: str
    speakers: tuple[str, ...]
    actions: tuple[ActionConfig, ...] = ()
    kinds: frozenset[str] = frozenset()
    seconds: float = 0.0
    words: tuple[WordTime, ...] = ()


@dataclass(frozen=True)
class StagePlace:
    """Where a character stands when the scene starts (Manim units): its feet's ``x`` and
    ``feet_y``, its ``height`` (depth and scale applied) and its ``facing``."""

    x: float
    feet_y: float
    height: float
    facing: str = "right"


@dataclass(frozen=True)
class StageFrame:
    """A stage's geometry as the planner's lint check sees it (Manim units, no rendering): the
    frame's size, the stage's width, the x the camera's view is centred on at the start, each
    character's :class:`StagePlace`, each prop's x and the stage's own marks."""

    frame_width: float
    frame_height: float
    stage_width: float
    camera_x: float
    places: Mapping[str, StagePlace]
    props: Mapping[str, float] = field(default_factory=dict)
    marks: Mapping[str, float] = field(default_factory=dict)

    @property
    def bounds(self) -> Bounds:
        """The box a camera view stays in: the stage's width, the frame's height."""
        return (-self.stage_width / 2, self.stage_width / 2, -self.frame_height / 2, self.frame_height / 2)

    def place_x(self, place: Any) -> float | None:
        """A mark or an x (0..1) of the stage in Manim units (``None``: neither)."""
        if not isinstance(place, (str, int, float)) or isinstance(place, bool):
            return None
        try:
            return (mark_x(place, self.marks) - 0.5) * self.stage_width
        except ValueError:
            return None

    def view_x(self, x: float, scale: float = 1.0) -> float:
        """The centre x of a view ``scale`` times magnified pointed at ``x``, kept on the stage."""
        return view_center_within(self.bounds, (x, 0.0), self.frame_width / scale, self.frame_height / scale)[0]


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
    frame: StageFrame | None = None                               # the stage's geometry (none: not checked)
    x: dict[str, float | None] = field(default_factory=dict)      # character -> its feet's x (None: not known)
    facing: dict[str, str] = field(default_factory=dict)          # character -> left / right
    camera_x: float | None = None                                 # the view's centre x (None: following)
    gestured: dict[str, str] = field(default_factory=dict)        # character -> its last automatic gesture
    gestured_line: dict[str, bool] = field(default_factory=dict)  # speaker -> it gestured in its previous line
    looked_now: set[str] = field(default_factory=set)             # characters given a look in this beat
    gestured_now: set[str] = field(default_factory=set)           # characters given a gesture in this beat
    words_before: int = 0                                         # the words of the beat before
    closeup_at: int = -2                                          # the last beat (index) with a close-up


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


# ----- predicted stills and the lint check -------------------------------------------------------------


def _still(state: _SceneState, beat: _Beat, *, view: tuple[float, float, float] | None = None, reach: tuple[str, str] | None = None,
           zoomed: bool = True) -> StillContext:
    """The beat's still as the lint rules would see it, predicted from the state (no rendering):
    each present character whose place is known as a box (with ``reach``'s character in its
    arm gesture), its face box, facing, whether it speaks and what it looks at; the camera at
    ``view`` (centre x, centre y, magnification; default the state's view). ``zoomed`` false
    leaves the magnification out of the frame's camera (so ``off_stage`` checks the view)."""
    from vidgen.lint.rules import StillContext

    frame = state.frame
    assert frame is not None and (view is not None or state.camera_x is not None)
    cx, cy, scale = view if view is not None else (state.camera_x, 0.0, 1.0)
    view_width, view_height = frame.frame_width / scale, frame.frame_height / scale
    px = _PX * scale
    left, top = cx - view_width / 2, cy + view_height / 2

    def box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
        return [(x0 - left) * px, (top - y1) * px, (x1 - left) * px, (top - y0) * px]

    objects: list[dict[str, Any]] = []
    for order, name in enumerate(state.cast):
        x, place = state.x.get(name), frame.places.get(name)
        if name not in state.present or x is None or place is None:
            continue
        facing = state.facing.get(name, place.facing)
        h, feet = place.height, place.feet_y
        x0, x1 = x - FIGURE_HALF_WIDTH * h, x + FIGURE_HALF_WIDTH * h
        if reach is not None and reach[0] == name:
            far = GESTURE_REACH.get(reach[1], FIGURE_HALF_WIDTH) * h
            if reach[1] == "shrug":
                x0, x1 = min(x0, x - far), max(x1, x + far)
            elif facing == "right":
                x1 = max(x1, x + far)
            else:
                x0 = min(x0, x - far)
        objects.append({
            "kind": "character", "name": name, "order": order, "bbox": box(x0, feet, x1, feet + h),
            "face": box(x - FIGURE_HALF_WIDTH * h, feet + FACE_BOTTOM * h, x + FIGURE_HALF_WIDTH * h, feet + h),
            "facing": facing, "speaking": name in beat.speakers, "looked_at": state.looking.get(name),
        })
    layout = {"width": frame.frame_width * _PX, "height": frame.frame_height * _PX}
    camera = {"zoom": scale if zoomed else 1.0, "center": [cx, cy]}
    return StillContext(layout, {"beat": beat.input.id, "camera": camera}, objects)


def still_findings(ctx: StillContext) -> set[tuple[str, tuple[str, ...]]]:
    """``(rule, names of the objects)`` of each finding the rules of :data:`CHECKED_RULES` report
    on ``ctx`` (with their default settings)."""
    from vidgen.config import LintRules
    from vidgen.lint import RULES

    defaults = LintRules()
    found: set[tuple[str, tuple[str, ...]]] = set()
    for name in CHECKED_RULES:
        for issue in RULES[name].check(ctx, getattr(defaults, name)):
            found.add((name, tuple(str(o.get("name")) for o in issue.objects)))
    return found


def _adds_finding(before: StillContext, after: StillContext) -> bool:
    return bool(still_findings(after) - still_findings(before))


def _target_x(state: _SceneState, to: Any) -> float | None:
    """Where ``to`` (a character, a prop, a mark or an x of the stage) is; ``None``: not known
    (the camera, or no geometry)."""
    if isinstance(to, str) and to in state.cast:
        return state.x.get(to)
    if state.frame is None or to == "camera":
        return None
    if isinstance(to, str) and to in state.frame.props:
        return state.frame.props[to]
    return state.frame.place_x(to)


def _turn_to(state: _SceneState, name: str, to: Any) -> None:
    """``name`` faces ``to`` as a look turns it (``look_pose``; kept when either is not known)."""
    here, there = state.x.get(name), _target_x(state, to)
    if here is not None and there is not None:
        state.facing[name] = look_pose(there - here, 0.0, state.facing.get(name, "right")).facing


# ----- the passes ------------------------------------------------------------------------------------


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


def _look_is_safe(state: _SceneState, beat: _Beat, name: str, to: str) -> bool:
    """Whether ``name`` looking at ``to`` adds no lint finding (true without the geometry)."""
    if state.frame is None or state.camera_x is None:
        return True
    before = _still(state, beat)
    facing, looking = state.facing.get(name), state.looking.get(name)
    state.looking[name] = to
    _turn_to(state, name, to)
    after = _still(state, beat)
    state.looking[name] = looking
    if facing is not None:
        state.facing[name] = facing
    return not _adds_finding(before, after)


def _plan_looks(state: _SceneState, beat: _Beat) -> list[ActionConfig]:
    """Listeners look at the (first) speaker; each speaker at the one it talks to. A look a
    character already has, or one that would add a lint finding, is not added."""
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
        if not _look_is_safe(state, beat, name, wanted[name]):
            continue
        added.append(_look(name, wanted[name]))
        state.looking[name] = wanted[name]
        _turn_to(state, name, wanted[name])
        state.looked_now.add(name)
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


def _letters(word: str) -> str:
    return "".join(ch for ch in word if ch.isalpha())


def stressed_word(words: Sequence[str], seconds: Sequence[float] | None = None) -> tuple[int, str] | None:
    """The word of a line its speaker stresses, and why: the first ``*word*`` (``emphasis``),
    else the first all-capitals word of two letters or more (``capitals``), else the longest of
    the words of :data:`LONG_WORD_LETTERS` letters or more (``longest``: by how long it is
    spoken, ``seconds`` per word, else by its letters); ``None``: no stressed word."""
    for k, word in enumerate(words):
        core = word.strip(".,;:!?\"'()…“”‘’")
        if len(core) > 2 and core.startswith("*") and core.endswith("*") and _letters(core):
            return k, "emphasis"
    for k, word in enumerate(words):
        letters = _letters(word)
        if len(letters) >= 2 and letters.isupper():
            return k, "capitals"
    long = [k for k, word in enumerate(words) if len(_letters(word)) >= LONG_WORD_LETTERS]
    if not long:
        return None
    return max(long, key=lambda k: (seconds[k] if seconds is not None else 0.0, len(_letters(words[k])), -k)), "longest"


def gesture_choices(word: str, text: str, seed: str, last: str | None = None) -> list[str]:
    """The gestures for stressed ``word`` of line ``text``, best first: the word's own (a
    negation shakes the head, a yes nods, a greeting waves, ``this`` / ``there`` / ``you``
    point), the line's (a question shrugs, a negation shakes the head), then
    :data:`EMPHASIS_GESTURES` in an order seeded by ``seed``, ``last`` (the speaker's last
    automatic gesture) at the end."""
    plain = word.replace("’", "'").strip(".,;:!?\"()…“”‘’*").lower()
    own = {**dict.fromkeys(NEGATIONS, "shake_head"), **dict.fromkeys(AFFIRMATIONS, "nod"), **dict.fromkeys(GREETINGS, "wave"),
           **dict.fromkeys(POINTING, "point")}
    found = [own[plain]] if plain in own else []
    cue = line_cue(text)
    found += {"question": ["shrug"], "negation": ["shake_head"]}.get(cue or "", [])
    rest = list(EMPHASIS_GESTURES)
    random.Random(seed).shuffle(rest)
    rest.sort(key=lambda g: g == last)
    return list(dict.fromkeys(found + rest))


def _gesture_is_safe(state: _SceneState, beat: _Beat, name: str, kind: str) -> bool:
    """A head gesture always is; an arm gesture when the character's arm stays as much in view
    as before (``off_stage`` on the predicted still with the arm out), known only with the
    geometry, the character's place and the camera's view."""
    if kind not in GESTURE_REACH:
        return True
    if state.frame is None or state.camera_x is None or state.x.get(name) is None:
        return False
    return not _adds_finding(_still(state, beat), _still(state, beat, reach=(name, kind)))


def _gesture_at(beat: _Beat, word: WordTime, kind: str, after: float) -> float | None:
    """When (a fraction of the narration) a gesture starts so that it is held on ``word``, not
    before ``after`` seconds and over before the narration ends (the action runner would rush
    it); ``None``: the line is too short for it."""
    seconds, length = beat.input.seconds, GESTURE_SECONDS[kind]
    if after + length > seconds:
        return None
    start = min(max(word.start - GESTURE_EASE * length, after), seconds - length)
    return math.floor(start / seconds * 100) / 100   # rounded down: still over in time


def _plan_gestures(state: _SceneState, beat: _Beat) -> list[ActionConfig]:
    """At most one gesture per line, by its (first) speaker able to make one, held on the line's
    stressed word (:func:`stressed_word`): the first of :func:`gesture_choices` its parts allow
    that adds no lint finding."""
    words = beat.input.words
    if not beat.speakers or not words:
        return []
    found = stressed_word([w.text for w in words], [w.end - w.start for w in words])
    if found is None:
        return []
    index, why = found
    for speaker in beat.speakers:
        member = state.cast[speaker]
        if speaker in beat.touched or not member.gestures or (why == "longest" and state.gestured_line.get(speaker)):
            continue
        seed = f"{beat.scene_id}/{beat.input.id}/{speaker}"
        for kind in gesture_choices(words[index].text, beat.input.text, seed, state.gestured.get(speaker)):
            after = LOOK_SECONDS if speaker in state.looked_now else 0.0
            at = _gesture_at(beat, words[index], kind, after)
            if at is not None and kind in member.gestures and _gesture_is_safe(state, beat, speaker, kind):
                state.gestured[speaker] = kind
                state.gestured_now.add(speaker)
                return [ActionConfig.automatic({"action": "gesture", "target": speaker, "to": kind, "at": at})]
        return []
    return []


def _closeup_is_safe(state: _SceneState, beat: _Beat, name: str) -> bool:
    """Whether a close-up on ``name`` keeps it wholly in the view (``off_stage`` on the zoomed
    view) and adds no ``facing_away`` (the rules on the predicted zoomed still)."""
    frame, x = state.frame, state.x.get(name)
    place = frame.places.get(name) if frame is not None else None
    if frame is None or place is None or x is None or state.camera_x is None:
        return False
    vw, vh = frame.frame_width / CLOSEUP_SCALE, frame.frame_height / CLOSEUP_SCALE
    cx, cy = view_center_within(frame.bounds, (x, place.feet_y + place.height / 2), vw, vh)
    view = (cx, cy, CLOSEUP_SCALE)
    if any(rule == "off_stage" and name in names for rule, names in still_findings(_still(state, beat, view=view, zoomed=False))):
        return False
    return not _adds_finding(_still(state, beat), _still(state, beat, view=view))


def _plan_closeups(state: _SceneState, beat: _Beat) -> list[ActionConfig]:
    """A close-up (a ``zoom`` on the speaker) for a short line right after a long one: never in
    two beats in a row, nor in a beat with a written move (:data:`MOVING_ACTIONS`), a speech
    bubble or an automatic gesture of the speaker, nor while the camera follows something; its
    moves in and back fit the narration (after the speaker's look); only where the lint check
    passes."""
    if not beat.speakers or state.closeup_at == state.index - 1:
        return []
    if len(beat.input.text.split()) > SHORT_LINE_WORDS or state.words_before < LONG_LINE_WORDS:
        return []
    written = beat.input.actions
    if any(a.action in MOVING_ACTIONS or (a.action == "say" and a.options.get("bubble")) for a in written):
        return []
    speaker = beat.speakers[0]
    room = beat.input.seconds - (LOOK_SECONDS if speaker in state.looked_now else 0.0)
    run_time = CLOSEUP_SECONDS if beat.input.seconds <= 0 or 2 * CLOSEUP_SECONDS <= 0.8 * room else CLOSEUP_CUT_SECONDS
    if speaker in state.gestured_now or not _closeup_is_safe(state, beat, speaker):
        return []
    state.closeup_at = state.index
    return [ActionConfig.automatic({"action": "zoom", "target": speaker, "scale": CLOSEUP_SCALE, "run_time": run_time})]


#: The passes of each kind of directing (Step 95 adds shots).
_PASSES: dict[str, Callable[[_SceneState, _Beat], list[ActionConfig]]] = {
    "looks": _plan_looks,
    "reactions": _plan_reactions,
    "gestures": _plan_gestures,
    "closeups": _plan_closeups,
}


def _walk(state: _SceneState, name: str, to_x: float | None) -> None:
    """``name`` walks to ``to_x`` (``None``: somewhere not known), facing the way it goes."""
    here = state.x.get(name)
    if here is not None and to_x is not None and abs(to_x - here) > 1e-6:
        state.facing[name] = "right" if to_x > here else "left"
    state.x[name] = to_x


def _enter(state: _SceneState, name: str, options: Mapping[str, Any]) -> None:
    """``name`` walks in from the ``side`` edge of the view (default: the nearer one) to ``to``
    (default: its own place), facing the way it goes."""
    frame = state.frame
    place = frame.places.get(name) if frame is not None else None
    if frame is None or place is None:
        state.x[name] = None
        return
    to_x = frame.place_x(options["to"]) if options.get("to") is not None else place.x
    if to_x is None or state.camera_x is None:
        state.x[name] = to_x
        return
    side = options.get("side") or nearer_side(to_x, state.camera_x - frame.frame_width / 2, state.camera_x + frame.frame_width / 2)
    state.facing[name] = "right" if side == "left" else "left"
    state.x[name] = to_x


def _follow_written(state: _SceneState, beat: BeatInput, names: Sequence[str]) -> None:
    """Update the state with the beat's written actions: entrances and exits, walks and other
    moves, turns, looks and what makes a look unknown, and the camera's pans and follows."""
    for act in beat.actions:
        targets = _named(act.targets(), names)
        options = act.options
        if act.action == "enter":
            state.present |= targets
            for name in targets:
                _enter(state, name, options)
        elif act.action == "exit":
            state.present -= targets
        elif act.action == "walk_to":
            for name in targets:
                _walk(state, name, state.frame.place_x(options.get("to")) if state.frame is not None else None)
        elif act.action in ("move_along", "keyframes"):
            for name in _named([p for p in act.targets() if "." not in p], names):
                state.x[name] = None
        elif act.action == "turn":
            for name in targets:
                facing = state.facing.get(name, "right")
                state.facing[name] = options.get("to") or ("left" if facing == "right" else "right")
        elif act.action == "pan" and state.frame is not None:
            places = [state.x.get(n) for n in targets] if targets else [state.frame.place_x(options.get("to"))]
            known = [x for x in places if x is not None]
            state.camera_x = state.frame.view_x(sum(known) / len(known)) if known and len(known) == len(places) else None
        elif act.action == "follow":
            state.camera_x = None
        if act.action == "look_at":
            to = options.get("to")
            for name in targets:
                state.looking[name] = to if isinstance(to, str) else None
                _turn_to(state, name, to)
        elif act.action in LOOK_CHANGING:
            for name in targets:
                state.looking[name] = None


def plan_directions(
    scene_id: str, cast: Sequence[CastMember], beats: Sequence[BeatInput], stage: StageFrame | None = None,
) -> list[DirectedBeat]:
    """The actions automatic directing adds to each beat of a stage scene (DESIGN.md §69.23,
    §69.24): for each beat with kinds on, the passes of those kinds in :data:`DIRECTING_KINDS`
    order. Pure: the same input gives the same actions. Characters an ``enter`` of the scene
    brings in are off stage until their first ``enter`` beat; an ``exit`` takes them off. With
    the ``stage``'s geometry each look, arm gesture and close-up is checked against the lint
    rules of :data:`CHECKED_RULES`; without it arm gestures and close-ups are not added."""
    names = [m.name for m in cast]
    entering = {n for b in beats for act in b.actions if act.action == "enter" for n in _named(act.targets(), names)}
    state = _SceneState(cast={m.name: m for m in cast}, present=set(names) - entering, frame=stage)
    if stage is not None:
        state.camera_x = stage.view_x(stage.camera_x)
        for name in names:
            place = stage.places.get(name)
            state.x[name] = None if place is None or name in entering else place.x
            if place is not None:
                state.facing[name] = place.facing
    directed: list[DirectedBeat] = []
    for k, beat in enumerate(beats):
        state.later = [b.speakers for b in beats[k + 1 :]]
        state.index, state.looked_now, state.gestured_now = k, set(), set()
        _follow_written(state, beat, names)
        touched = set()
        for act in beat.actions:
            if act.action not in FRAMING_ACTIONS:
                touched |= _named(act.targets(), names)
        current = _Beat(beat, tuple(s for s in beat.speakers if s in state.present), frozenset(touched), scene_id)
        added = [a for kind in DIRECTING_KINDS if kind in beat.kinds and kind in _PASSES for a in _PASSES[kind](state, current)]
        if any(act.action == "zoom" for act in beat.actions):
            state.closeup_at = k
        for speaker in current.speakers:
            state.gestured_line[speaker] = any(a.action == "gesture" and a.target == speaker for a in added)
        if current.speakers:
            state.spoken.append(current.speakers)
        state.words_before = len(beat.text.split())
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


def stage_frame(project: Project, params: Any) -> StageFrame:
    """The geometry of a ``stage`` scene with validated ``params`` (its characters, props, marks,
    ground, size, width and ``camera_at``) in the video's frame, placed by
    :func:`~vidgen.cartoon.stage.stage_layout` as the stage places them (no rendering)."""
    from vidgen.cartoon.stage import facing_towards_centre, stage_layout
    from vidgen.render.worker import frame_size

    fmt = project.config.format
    frame_width, frame_height = frame_size(fmt.width, fmt.height)
    stage_width = params.width * frame_width
    placements = stage_layout(
        params.items(), marks=params.marks, ground=params.ground, size=params.size,
        frame_width=frame_width, frame_height=frame_height, stage_width=stage_width,
    )
    facings = {c.name: c.facing for c in params.characters}
    places: dict[str, StagePlace] = {}
    props: dict[str, float] = {}
    for placed in placements:
        if placed.kind != "character":
            props[placed.name] = placed.feet[0]
            continue
        facing = facings.get(placed.name, "auto")
        facing = facing_towards_centre(placed.x_fraction) if facing == "auto" else facing
        places[placed.name] = StagePlace(placed.feet[0], placed.feet[1], placed.height, facing)
    camera_x = (mark_x(params.camera_at, params.marks) - 0.5) * stage_width
    return StageFrame(frame_width, frame_height, stage_width, camera_x, places, props, dict(params.marks))


def _beat_words(project: Project, beat: BeatConfig) -> tuple[float, tuple[WordTime, ...]]:
    """A beat's narration length (its MP3's, else the word-count estimate) and its word times
    from its start (the stored alignment, else estimated: :func:`~vidgen.speech.beat_word_times`)."""
    from vidgen.speech import audio_duration, beat_word_times

    mp3 = project.audio_dir / f"{beat.id}.mp3"
    seconds = audio_duration(mp3) if mp3.is_file() else beat.estimated_duration(project.config.narration.words_per_second)
    return seconds, tuple(beat_word_times(project.audio_dir, beat.id, beat.text, 0.0, seconds, language=project.config.language))


def stage_directions(
    project: Project, spec: SceneConfig, characters: Sequence[str], setting: AutoDirectSetting | None, stage: StageFrame | None = None,
) -> list[DirectedBeat]:
    """The automatic actions of a stage scene ``spec`` with ``characters`` on it (in the stage's
    order), the stage's ``auto_direct`` ``setting`` and its geometry ``stage``
    (:func:`stage_frame`; none: arm gestures and close-ups are not added): reads who speaks each
    beat (its ``say`` actions, else its voice), the beats' word times, the characters' parts (a
    ``look: {svg}`` from the project folder) and the video's setting, then
    :func:`plan_directions`. Needs the project's registry (a project session) for the action
    names."""
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
            gestures=() if shapes is None else tuple(g for g in GESTURES if missing_needs(shapes, f"gesture: {g}") is None),
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
        seconds, words = _beat_words(project, beat) if {"gestures", "closeups"} & on and speakers else (0.0, ())
        beats.append(BeatInput(beat.id, beat.text, tuple(speakers), written, on, seconds, words))
    return plan_directions(spec.id, cast, beats, stage)


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
