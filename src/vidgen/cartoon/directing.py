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
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any

from vidgen.camera import Bounds, view_center_within
from vidgen.cartoon.acting import GESTURE_EASE, GESTURE_SECONDS, GESTURES, look_pose, nearer_side
from vidgen.cartoon.effects import EXPRESSION_EFFECTS
from vidgen.cartoon.holding import HoldingError, Holdings, put_down_x
from vidgen.cartoon.reframe import ReframeBeat, ReframeFigure, reframe_needed, reframe_path, stage_base_width
from vidgen.cartoon.seating import SEAT_BACKS, SEAT_PLACES, PostureError, Postures
from vidgen.cartoon.shots import FIGURE_HALF_WIDTH, Shot, ShotFigure, ShotView, shot_figures, shot_view
from vidgen.cartoon.stage import mark_x
from vidgen.config import DIRECTING_KINDS, ActionConfig, AutoDirectSetting, BeatConfig, ReframeSetting, SceneConfig, directing_kinds

if TYPE_CHECKING:
    from vidgen.lint.rules import StillContext
    from vidgen.overlap import BeatWindow
    from vidgen.project import Project
    from vidgen.speech import WordTime

#: Actions that only frame, voice or point at a character: written ones leave it to automatic
#: directing in their beat.
FRAMING_ACTIONS = frozenset({"say", "zoom", "pan", "follow", "shot", "highlight", "dim", "callout"})
#: Written actions after which a character's look is not known (it turned, moved or took a pose).
LOOK_CHANGING = frozenset({"turn", "walk_to", "run_to", "enter", "exit", "move_along", "keyframes", "pose", "emote", "sit_on", "lean_on"})
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
#: speaker's look), else a ``shot: closeup`` of the speaker (a cut held for the line, DESIGN.md
#: §69.29).
SHORT_LINE_WORDS = 5
LONG_LINE_WORDS = 8
CLOSEUP_SCALE: float = 2
CLOSEUP_SECONDS = 0.5
#: Written actions during which no close-up is added: walks and other moves of a character, and
#: the camera's own moves.
MOVING_ACTIONS = frozenset({
    "walk_to", "run_to", "enter", "exit", "move_along", "keyframes", "pan", "follow", "zoom", "pick_up", "put_down", "give", "throw",
    "sit_on", "lean_on", "stand_up", "shot", "blow_away",
})
#: A generated figure's proportions, in its heights (measured on the generator's looks; an SVG
#: look is taken to be alike): half its width (``FIGURE_HALF_WIDTH``, shared with the shots'
#: framing), the bottom of its face box (above its feet), and
#: how far an arm gesture reaches from its middle (``point`` and ``wave`` forward, ``shrug`` to
#: both sides).
FACE_BOTTOM = 0.5
GESTURE_REACH: dict[str, float] = {"point": 0.4, "wave": 0.35, "shrug": 0.34}
#: The hands each arm gesture moves (``near``: the character's near hand, :attr:`CastMember.near_hand`):
#: none is added while one of them holds a prop (DESIGN.md §69.27).
GESTURE_HANDS: dict[str, tuple[str, ...]] = {"point": ("near",), "wave": ("near",), "shrug": ("left", "right")}
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
    near_hand: str = "left"
    """The hand ``point`` and ``wave`` use (``left``, else ``right`` without a left arm)."""


@dataclass(frozen=True)
class BeatInput:
    """One beat for the planner: its id, its line, who says it (characters on the stage), the
    actions written in it (resolved), the kinds of directing on for it, and its narration's
    length (``seconds``) and word times (from its start; none: no gestures). ``next_joins``:
    the next beat overlaps or interrupts it (DESIGN.md §69.34), so ``seconds`` and ``words``
    are what is heard before that beat starts and no pause follows (no reactions)."""

    id: str
    text: str
    speakers: tuple[str, ...]
    actions: tuple[ActionConfig, ...] = ()
    kinds: frozenset[str] = frozenset()
    seconds: float = 0.0
    words: tuple[WordTime, ...] = ()
    next_joins: bool = False


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
    character's :class:`StagePlace`, each prop's x, the stage's own marks and the facing of each
    prop with a seat back (a character sitting on it faces that way, DESIGN.md §69.28), and how
    many sit side by side on each prop that seats more than one (§69.43)."""

    frame_width: float
    frame_height: float
    stage_width: float
    camera_x: float
    places: Mapping[str, StagePlace]
    props: Mapping[str, float] = field(default_factory=dict)
    marks: Mapping[str, float] = field(default_factory=dict)
    seat_facings: Mapping[str, str] = field(default_factory=dict)
    seat_places: Mapping[str, int] = field(default_factory=dict)

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
    holdings: Holdings = field(default_factory=Holdings)          # who holds which prop
    postures: Postures = field(default_factory=Postures)          # who sits or leans on which prop
    prop_x: dict[str, float | None] = field(default_factory=dict)  # prop -> its x where it stands (None: not known)
    shot: tuple[ShotView, Shot] | None = None                      # the beat's shot (written or automatic), if any
    faces_now: list[tuple[float, str, str]] = field(default_factory=list)  # (at, character, expression) of this beat's automatic reactions


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
           zoomed: bool = True, shot: Shot | None = None) -> StillContext:
    """The beat's still as the lint rules would see it, predicted from the state (no rendering):
    each present character whose place is known as a box (with ``reach``'s character in its
    arm gesture), its face box, facing, whether it speaks and what it looks at; the camera at
    ``view`` (centre x, centre y, magnification) in ``shot`` (default: the beat's shot, else the
    state's view). ``zoomed`` false leaves the magnification out of the frame's camera (so
    ``off_stage`` checks the view)."""
    from vidgen.lint.rules import StillContext

    frame = state.frame
    assert frame is not None and (view is not None or state.camera_x is not None or state.shot is not None)
    shot = state.shot[1] if state.shot is not None and view is None else shot
    if view is None and state.shot is not None:
        view = (state.shot[0].center_x, state.shot[0].center_y, state.shot[0].scale)
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
    still = {"beat": beat.input.id, "camera": camera, **({"shot": shot.layout()} if shot is not None else {})}
    return StillContext(layout, still, objects)


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
        holder = state.holdings.holder(to)
        return state.x.get(holder[0]) if holder is not None else state.prop_x.get(to, state.frame.props[to])
    return state.frame.place_x(to)


def _turn_to(state: _SceneState, name: str, to: Any) -> None:
    """``name`` faces ``to`` as a look turns it (``look_pose``; kept when either is not known, and
    while it sits or leans: a look turns only its head then)."""
    here, there = state.x.get(name), _target_x(state, to)
    if here is not None and there is not None and state.postures.of(name) is None:
        state.facing[name] = look_pose(there - here, 0.0, state.facing.get(name, "right")).facing


def _behind(state: _SceneState, name: str, to: Any) -> bool:
    """Whether ``to`` is behind ``name`` while it sits or leans (it cannot turn to look at it)."""
    here, there = state.x.get(name), _target_x(state, to)
    if state.postures.of(name) is None or here is None or there is None:
        return False
    return (there - here) * (1.0 if state.facing.get(name, "right") == "right" else -1.0) < 0


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
        if name in beat.touched or not member.can_look or state.looking.get(name) == wanted[name] or _behind(state, name, wanted[name]):
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
    cue = line_cue(beat.input.text) if beat.speakers and not beat.input.next_joins else None
    if cue is None:
        return []
    added: list[ActionConfig] = []
    for name, member in state.cast.items():
        if name not in state.present or name in beat.speakers or name in beat.touched or not member.can_emote:
            continue
        choices = [e for e in REACTIONS[cue] if e != state.reacted.get(name)]
        expression = random.Random(f"{beat.scene_id}/{beat.input.id}/{name}").choice(choices)
        state.reacted[name] = expression
        state.faces_now.append((REACTION_AT, name, expression))
        added.append(ActionConfig.automatic({"action": "react", "target": name, "expression": expression, "at": REACTION_AT}))
    return added


def _face_changes(state: _SceneState, beat: _Beat) -> list[tuple[float, int, str, str]]:
    """The beat's changes of expression, ``(at, order, character, expression)``: its written
    ``emote`` / ``react`` actions (a voice sound's face too), then the automatic reactions."""
    names = list(state.cast)
    found: list[tuple[float, int, str, str]] = []
    for k, act in enumerate(beat.input.actions):
        expression = act.options.get("to") if act.action == "emote" else act.options.get("expression") if act.action == "react" else None
        if isinstance(expression, str):
            found += [(act.at, k, name, expression) for name in sorted(_named(act.targets(), names), key=names.index)]
    first = len(beat.input.actions)
    return found + [(at, first + k, name, expression) for k, (at, name, expression) in enumerate(state.faces_now)]


def _plan_effects(state: _SceneState, beat: _Beat) -> list[ActionConfig]:
    """At most one effect symbol per line: over the head of the character whose expression
    changes first in the beat to one of :data:`~vidgen.cartoon.effects.EXPRESSION_EFFECTS`
    (surprised: exclaim, thinking: question, angry: anger), as the change starts; none in a beat
    with a written ``effect``. A written ``emote`` or ``react`` gets one too: the symbol adds to the
    face and changes nothing the action set."""
    if any(act.action == "effect" for act in beat.input.actions):
        return []
    for at, _, name, expression in sorted(_face_changes(state, beat)):
        if expression in EXPRESSION_EFFECTS and name in state.present:
            timing = {"at": at} if at > 0 else {}
            return [ActionConfig.automatic({"action": "effect", "target": name, "to": EXPRESSION_EFFECTS[expression], **timing})]
    return []


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


def _hands_free(state: _SceneState, name: str, kind: str) -> bool:
    """Whether the hands gesture ``kind`` moves (:data:`GESTURE_HANDS`) hold no prop."""
    held = state.holdings.hands(name)
    near = state.cast[name].near_hand
    return not any((near if hand == "near" else hand) in held for hand in GESTURE_HANDS.get(kind, ()))


def _gesture_is_safe(state: _SceneState, beat: _Beat, name: str, kind: str) -> bool:
    """A head gesture always is; an arm gesture when its hands hold no prop and the character's
    arm stays as much in view as before (``off_stage`` on the predicted still with the arm out),
    known only with the geometry, the character's place and the camera's view."""
    if kind not in GESTURE_REACH:
        return True
    if not _hands_free(state, name, kind):
        return False
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


def _present_figures(state: _SceneState) -> dict[str, ShotFigure]:
    """The characters on stage whose place is known, as a shot frames them (in the stage's order)."""
    frame = state.frame
    found: dict[str, ShotFigure] = {}
    for name in state.cast:
        x, place = state.x.get(name), frame.places.get(name) if frame is not None else None
        if name in state.present and x is not None and place is not None:
            found[name] = ShotFigure(name, x, place.feet_y, place.height, state.facing.get(name, place.facing))
    return found


def _framed(state: _SceneState, beat: _Beat, kind: str, names: Sequence[str]) -> tuple[ShotView, Shot] | None:
    """The view and figures of a ``kind`` shot of ``names`` as the beat starts (``None``: no
    geometry, or a named character whose place is not known)."""
    frame = state.frame
    present = _present_figures(state)
    if frame is None or any(n not in present for n in names):
        return None
    shot = shot_figures(kind, names, present, speakers=beat.speakers, looked_at=state.looking)
    view = shot_view(shot, present, frame_width=frame.frame_width, frame_height=frame.frame_height, bounds=frame.bounds)
    return view, shot


def _closeup_shot(state: _SceneState, beat: _Beat, name: str) -> tuple[ShotView, Shot] | None:
    """A ``closeup`` shot of ``name`` when it adds no lint finding (``off_stage`` checks its face
    in the shot, ``facing_away`` the one it talks to if in view); ``None`` otherwise."""
    if state.frame is None or state.camera_x is None:
        return None
    framed = _framed(state, beat, "closeup", [name])
    if framed is None:
        return None
    view, shot = framed
    after = _still(state, beat, view=(view.center_x, view.center_y, view.scale), shot=shot)
    return None if _adds_finding(_still(state, beat), after) else framed


def _plan_closeups(state: _SceneState, beat: _Beat) -> list[ActionConfig]:
    """A close-up for a short line right after a long one: a ``zoom`` on the speaker moving in
    and back when both moves fit the narration (after the speaker's look), else a ``shot:
    closeup`` of it (a cut held for the line). Never in two beats in a row, nor in a beat with a
    written move or shot (:data:`MOVING_ACTIONS`), a speech bubble or an automatic gesture of the
    speaker, nor while the camera follows something; only where the lint check passes."""
    if not beat.speakers or state.closeup_at == state.index - 1:
        return []
    if len(beat.input.text.split()) > SHORT_LINE_WORDS or state.words_before < LONG_LINE_WORDS:
        return []
    written = beat.input.actions
    if any(a.action in MOVING_ACTIONS or (a.action == "say" and a.options.get("bubble")) for a in written):
        return []
    speaker = beat.speakers[0]
    if speaker in state.gestured_now:
        return []
    room = beat.input.seconds - (LOOK_SECONDS if speaker in state.looked_now else 0.0)
    if beat.input.seconds <= 0 or 2 * CLOSEUP_SECONDS <= 0.8 * room:
        if not _closeup_is_safe(state, beat, speaker):
            return []
        state.closeup_at = state.index
        return [ActionConfig.automatic({"action": "zoom", "target": speaker, "scale": CLOSEUP_SCALE, "run_time": CLOSEUP_SECONDS})]
    framed = _closeup_shot(state, beat, speaker)
    if framed is None:
        return []
    state.closeup_at, state.shot = state.index, framed
    return [ActionConfig.automatic({"action": "shot", "target": speaker, "kind": "closeup"})]


#: The passes of each kind of directing.
_PASSES: dict[str, Callable[[_SceneState, _Beat], list[ActionConfig]]] = {
    "looks": _plan_looks,
    "reactions": _plan_reactions,
    "gestures": _plan_gestures,
    "closeups": _plan_closeups,
    "effects": _plan_effects,
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


def _handle(state: _SceneState, action: str, targets: set[str], options: Mapping[str, Any]) -> None:
    """A written prop action: who holds what, and where a put-down or thrown prop stands (a
    change :class:`Holdings` refuses is ignored: ``vidgen validate`` reports it)."""
    for name in sorted(targets):
        try:
            if action in ("pick_up", "hold"):
                state.holdings.take(name, str(options.get("to")), options.get("hand"))
            elif action == "give":
                state.holdings.give(name, str(options.get("to")), options.get("prop"), options.get("hand"))
            else:
                prop, _ = state.holdings.release(name, options.get("prop"))
                here, frame = state.x.get(name), state.frame
                place = frame.place_x(options["to"]) if frame is not None and options.get("to") is not None else None
                if place is None and here is not None and action == "put_down" and frame is not None and name in frame.places:
                    place = put_down_x(here, frame.places[name].height, state.facing.get(name, "right"))
                state.prop_x[prop] = place
        except HoldingError:
            continue


def _pose(state: _SceneState, action: str, targets: set[str], options: Mapping[str, Any]) -> None:
    """A written ``sit_on`` / ``lean_on`` / ``stand_up``: who sits or leans, where and which way
    it faces (a change :class:`Postures` refuses is ignored: ``vidgen validate`` reports it)."""
    prop = str(options.get("to"))
    there = state.prop_x.get(prop, state.frame.props.get(prop)) if state.frame is not None else None
    for name in sorted(targets):
        try:
            if action == "stand_up":
                state.postures.stand(name)
                continue
            if action == "sit_on":
                state.postures.sit(name, prop, state.frame.seat_places.get(prop, 1) if state.frame is not None else 1)
            else:
                state.postures.lean(name, prop)
        except PostureError:
            continue
        here = state.x.get(name)
        if action == "sit_on":
            state.x[name] = there
            if state.frame is not None and prop in state.frame.seat_facings:
                state.facing[name] = state.frame.seat_facings[prop]
        elif here is not None and there is not None:
            state.facing[name] = "left" if here < there else "right"   # its back to the prop


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
        elif act.action in ("walk_to", "run_to"):
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
        elif act.action in ("pick_up", "hold", "give", "put_down", "throw"):
            _handle(state, act.action, targets, options)
        elif act.action == "blow_away":   # out of any hand; where it lands, or gone
            for prop in act.targets():
                state.holdings.drop(prop)
                to = options.get("to")
                state.prop_x[prop] = state.frame.place_x(to) if state.frame is not None and to is not None else None
        elif act.action in ("sit_on", "lean_on", "stand_up"):
            _pose(state, act.action, targets, options)
        if act.action == "look_at":
            to = options.get("to")
            for name in targets:
                state.looking[name] = to if isinstance(to, str) else None
                _turn_to(state, name, to)
        elif act.action in LOOK_CHANGING:
            for name in targets:
                state.looking[name] = None


def _start_state(cast: Sequence[CastMember], beats: Sequence[BeatInput], stage: StageFrame | None) -> _SceneState:
    """The state as the scene starts: characters an ``enter`` of the scene brings in are off
    stage, the others on their places (with the geometry), the camera on its start view."""
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
    return state


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
    state = _start_state(cast, beats, stage)
    directed: list[DirectedBeat] = []
    for k, beat in enumerate(beats):
        state.later = [b.speakers for b in beats[k + 1 :]]
        state.index, state.looked_now, state.gestured_now, state.faces_now = k, set(), set(), []
        _follow_written(state, beat, names)
        touched = set()
        for act in beat.actions:
            if act.action not in FRAMING_ACTIONS:
                touched |= _named(act.targets(), names)
        current = _Beat(beat, tuple(s for s in beat.speakers if s in state.present), frozenset(touched), scene_id)
        home_x = state.camera_x
        written_shot = next((a for a in beat.actions if a.action == "shot" and a.options.get("kind")), None)
        if written_shot is not None:   # the passes check their actions in the shot's view
            framed = [n for pattern in written_shot.targets() for n in names if fnmatchcase(n, pattern.split(".", 1)[0])]
            state.shot = _framed(state, current, str(written_shot.options["kind"]), framed)
            if state.shot is None:
                state.camera_x = None   # a view not known: nothing is checked against it
        added = [a for kind in DIRECTING_KINDS if kind in beat.kinds and kind in _PASSES for a in _PASSES[kind](state, current)]
        state.camera_x, state.shot = home_x, None   # the next beat goes back to the view before the shot
        if any(act.action in ("zoom", "shot") for act in beat.actions):
            state.closeup_at = k
        for speaker in current.speakers:
            state.gestured_line[speaker] = any(a.action == "gesture" and a.target == speaker for a in added)
        if current.speakers:
            state.spoken.append(current.speakers)
        state.words_before = len(beat.text.split())
        if added:
            directed.append(DirectedBeat(beat.id, tuple(added)))
    return directed


#: Written actions that move the camera: reframing leaves their beat alone (DESIGN.md §69.30).
CAMERA_ACTIONS = frozenset({"pan", "follow", "zoom", "shot"})


def _reframe_beat(state: _SceneState, beat: BeatInput, names: Sequence[str]) -> ReframeBeat:
    """``beat`` as reframing sees it, with the state as the beat starts; updates the state with
    the beat's written actions."""
    before = dict(state.x)
    _follow_written(state, beat, names)
    frame = state.frame
    assert frame is not None
    figures = []
    for name in names:
        x, place = state.x.get(name), frame.places.get(name)
        if name in state.present and x is not None and place is not None:
            start = before.get(name)
            figures.append(ReframeFigure(
                name, x, FIGURE_HALF_WIDTH * place.height, state.facing.get(name, place.facing),
                start if start is not None and abs(start - x) > 1e-6 else None,
            ))
    written = {a.action for a in beat.actions if a.action in CAMERA_ACTIONS and not (a.action == "shot" and not a.options.get("kind"))}
    camera = "follow" if "follow" in written else "pan" if "pan" in written else "held" if written else "free"
    speakers = tuple(s for s in beat.speakers if s in state.present)
    bubble = any(a.action == "say" and a.options.get("bubble") for a in beat.actions)
    return ReframeBeat(beat.id, speakers, beat.seconds, tuple(figures), camera, state.camera_x if camera == "pan" else None, bubble)


def plan_reframe(cast: Sequence[CastMember], beats: Sequence[BeatInput], stage: StageFrame) -> list[DirectedBeat]:
    """The ``pan`` actions that keep each speaker of a stage scene in view (``reframe: speaker``;
    DESIGN.md §69.30): the beats with the characters' places replayed from their written actions
    (as :func:`plan_directions` does), then :func:`~vidgen.cartoon.reframe.reframe_path`, each move
    a ``pan`` to an x of the stage from the beat's start (``cut: true`` for a cut). Pure."""
    names = [m.name for m in cast]
    state = _start_state(cast, beats, stage)
    inputs = [_reframe_beat(state, beat, names) for beat in beats]
    left, right = stage.bounds[:2]
    moves = reframe_path(inputs, frame_width=stage.frame_width, bounds=(left, right), start_x=stage.camera_x)
    found = []
    for move in moves:
        timing = {"run_time": move.seconds} if move.seconds > 0 else {"cut": True}
        pan = ActionConfig.automatic({"action": "pan", "to": round((move.x - left) / (right - left), 4), **timing})
        found.append(DirectedBeat(move.beat, (pan,)))
    return found


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
    """The beat's written actions, its ``shot:`` first (as the action it stands for)."""
    shot = (beat.shot.action(),) if beat.shot is not None else ()
    return (*shot, *(act.resolved(known) for act in beat.actions))


def stage_frame(project: Project, params: Any) -> StageFrame:
    """The geometry of a ``stage`` scene with validated ``params`` (its characters, props, marks,
    ground, size, width and ``camera_at``) in the video's frame, placed by
    :func:`~vidgen.cartoon.stage.stage_layout` as the stage places them (no rendering)."""
    from vidgen.cartoon.stage import facing_towards_centre, stage_layout
    from vidgen.render.worker import frame_size

    fmt = project.config.format
    frame_width, frame_height = frame_size(fmt.width, fmt.height)
    stage_width = params.width * stage_base_width(frame_width, frame_height, stage_reframes(project, params))
    placements = stage_layout(
        params.items(), marks=params.stage_marks(), ground=params.ground, size=params.size,
        frame_width=frame_width, frame_height=frame_height, stage_width=stage_width,
    )
    facings = {c.name: c.facing for c in params.characters}
    seat_facings = {name: p.facing for name, p in zip(params.prop_names(), params.stage_props()) if p.prop in SEAT_BACKS}
    seat_places = {name: len(SEAT_PLACES[p.prop]) for name, p in zip(params.prop_names(), params.stage_props()) if p.prop in SEAT_PLACES}
    places: dict[str, StagePlace] = {}
    props: dict[str, float] = {}
    for placed in placements:
        if placed.kind != "character":
            props[placed.name] = placed.feet[0]
            continue
        facing = facings.get(placed.name, "auto")
        facing = facing_towards_centre(placed.x_fraction) if facing == "auto" else facing
        places[placed.name] = StagePlace(placed.feet[0], placed.feet[1], placed.height, facing)
    camera_x = (mark_x(params.camera_at, params.stage_marks()) - 0.5) * stage_width
    return StageFrame(frame_width, frame_height, stage_width, camera_x, places, props, params.stage_marks(), seat_facings, seat_places)


def stage_reframes(project: Project, params: Any) -> bool:
    """Whether the camera keeps the speaker in view on a ``stage`` scene with validated
    ``params`` (DESIGN.md §69.30): its ``reframe``, else the video's, else ``speaker`` when its
    characters, where they start on the stage as wide as :func:`stage_base_width` lays it out
    while reframing, are wider together than the frame."""
    from vidgen.cartoon.stage import stage_layout
    from vidgen.render.worker import frame_size

    setting: ReframeSetting | None = params.reframe if params.reframe is not None else project.config.reframe
    if setting is not None:
        return setting == "speaker"
    fmt = project.config.format
    frame_width, frame_height = frame_size(fmt.width, fmt.height)
    placements = stage_layout(
        params.items(), marks=params.stage_marks(), ground=params.ground, size=params.size, frame_width=frame_width,
        frame_height=frame_height, stage_width=params.width * stage_base_width(frame_width, frame_height, True),
    )
    boxes = [(p.feet[0] - FIGURE_HALF_WIDTH * p.height, p.feet[0] + FIGURE_HALF_WIDTH * p.height) for p in placements if p.kind == "character"]
    return reframe_needed(boxes, frame_width)


def _beat_seconds(project: Project, beat: BeatConfig) -> float:
    """A beat's narration length: its MP3's, else the word-count estimate."""
    from vidgen.speech import audio_duration

    mp3 = project.audio_dir / f"{beat.id}.mp3"
    return audio_duration(mp3) if mp3.is_file() else beat.estimated_duration(project.config.narration.words_per_second)


def _beat_words(project: Project, beat: BeatConfig) -> tuple[float, tuple[WordTime, ...]]:
    """A beat's narration length (its MP3's, else the word-count estimate) and its word times
    from its start (the stored alignment, else estimated: :func:`~vidgen.speech.beat_word_times`),
    each word as written (:attr:`~vidgen.config.BeatConfig.marked_text`)."""
    from vidgen.speech import WordTime, beat_word_times

    seconds = _beat_seconds(project, beat)
    spoken = project.spoken(beat) if beat.voice_sounds else None   # the audio also says the sounds (§69.33)
    times = beat_word_times(project.audio_dir, beat.id, beat.text, 0.0, seconds, spoken, project.config.language)
    marked = beat.marked_text.split()   # the words as written, *word* marks included (same count)
    if len(marked) == len(times):
        times = [WordTime(word, t.start, t.end) for word, t in zip(marked, times)]
    return seconds, tuple(times)


def _joined_windows(project: Project, spec: SceneConfig) -> dict[str, BeatWindow]:
    """The beats of ``spec`` that the next beat overlaps or interrupts, with their
    :class:`~vidgen.overlap.BeatWindow` (DESIGN.md §69.34); empty when none is."""
    from vidgen.overlap import beat_lines, beat_windows, has_joins

    if not has_joins(spec.beats):
        return {}
    lines = beat_lines(project, spec.beats, lambda b: _beat_seconds(project, b))
    return {b.id: w for b, w in zip(spec.beats, beat_windows(lines, project.config.narration.pad)) if w.joined}


def _stage_cast(project: Project, characters: Sequence[str]) -> list[CastMember]:
    """The ``characters`` on a stage as the planner sees them (what their parts allow; a
    character whose parts cannot be read allows nothing)."""
    from vidgen.cartoon.cast import character_part_shapes, missing_needs
    from vidgen.errors import VidgenError

    entries = {e.name: e for e in project.config.characters}
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
            near_hand="right" if shapes is not None and "arm_left" not in shapes and "arm_right" in shapes else "left",
        ))
    return cast


def _beat_speakers(project: Project, spec: SceneConfig, beat: BeatConfig, written: Sequence[ActionConfig], characters: Sequence[str]) -> list[str]:
    """Who says ``beat`` among ``characters``: its ``say`` actions' targets, else the characters
    of its voice."""
    from vidgen.cartoon.cast import beat_voice, speaking_characters

    said = [act for act in written if act.action == "say"]
    if said:
        return [n for n in characters if n in _named([p for act in said for p in act.targets()], characters)]
    return speaking_characters(project.config, beat_voice(spec, beat), characters)


#: Written actions that set a character's face: a voice sound adds no expression to it.
FACE_ACTIONS = frozenset({"emote", "react"})


def sound_reactions(project: Project, spec: SceneConfig, characters: Sequence[str]) -> list[DirectedBeat]:
    """The faces of a stage's speakers for the voice sounds of their lines (DESIGN.md §69.33,
    whatever ``auto_direct`` says): a ``react`` with the expression of the beat's first sound
    (:data:`~vidgen.voicesounds.VOICE_SOUNDS`: laugh -> happy, gasp -> surprised...) as it is
    heard, for each speaker that can emote and that no ``emote`` / ``react`` of the beat acts on.
    Needs the project's registry (a project session)."""
    from vidgen import registry
    from vidgen.voicesounds import VOICE_SOUNDS, beat_sound_spans

    if not any(beat.voice_sounds for beat in spec.beats):
        return []
    can_emote = {member.name for member in _stage_cast(project, characters) if member.can_emote}
    known = registry.action_names()
    joined = _joined_windows(project, spec)
    out: list[DirectedBeat] = []
    for beat in spec.beats:
        if not beat.voice_sounds:
            continue
        written = _resolved_actions(beat, known)
        faced = _named([p for act in written if act.action in FACE_ACTIONS for p in act.targets()], characters)
        speakers = [n for n in _beat_speakers(project, spec, beat, written, characters) if n in can_emote and n not in faced]
        if not speakers:
            continue
        seconds, _ = _beat_words(project, beat)
        span = beat_sound_spans(project, beat, seconds)[0]
        if beat.id in joined:   # the next beat starts before this one ends (§69.34)
            seconds = joined[beat.id].body
            if span.start >= seconds:
                continue   # heard only under the next line, or cut by it
        at = round(min(max(span.start / seconds, 0.0), REACTION_AT), 3) if seconds > 0 else 0.0
        expression = VOICE_SOUNDS[span.kind].expression
        out.append(DirectedBeat(beat.id, tuple(
            ActionConfig.automatic({"action": "react", "target": name, "expression": expression, "at": at}) for name in speakers
        )))
    return out


def _merged_directions(spec: SceneConfig, *lists: Sequence[DirectedBeat]) -> list[DirectedBeat]:
    """Several lists of automatic actions of ``spec``'s beats as one: per beat (in the scene's
    order), the actions in the order of the lists."""
    merged: dict[str, tuple[ActionConfig, ...]] = {}
    for directed in lists:
        for d in directed:
            merged[d.beat] = (*merged.get(d.beat, ()), *d.actions)
    return [DirectedBeat(beat.id, merged[beat.id]) for beat in spec.beats if beat.id in merged]


def stage_directions(
    project: Project, spec: SceneConfig, characters: Sequence[str], setting: AutoDirectSetting | None, stage: StageFrame | None = None,
    *, reframe: bool = False,
) -> list[DirectedBeat]:
    """The automatic actions of a stage scene ``spec`` with ``characters`` on it (in the stage's
    order), the stage's ``auto_direct`` ``setting`` and its geometry ``stage``
    (:func:`stage_frame`; none: arm gestures and close-ups are not added): reads who speaks each
    beat (its ``say`` actions, else its voice), the beats' word times, the characters' parts (a
    ``look: {svg}`` from the project folder) and the video's setting, then
    :func:`plan_directions`. With ``reframe`` (:func:`stage_reframes`) and the geometry, the
    pans of :func:`plan_reframe` come first in their beats, and the directing passes see them as
    written. Whatever ``setting`` says, the speakers' faces for the voice sounds of their lines
    (:func:`sound_reactions`) come first, seen as written too. Needs the project's registry (a
    project session) for the action names."""
    from vidgen import registry

    config = project.config
    sounds = sound_reactions(project, spec, characters)
    spec = with_auto_actions(spec, sounds)
    kinds = [directing_kinds(beat.auto_direct, setting, config.auto_direct) for beat in spec.beats]
    reframe = reframe and stage is not None
    if not any(kinds) and not reframe:
        return sounds
    cast = _stage_cast(project, characters)
    known = registry.action_names()
    joined = _joined_windows(project, spec)
    beats: list[BeatInput] = []
    for beat, on in zip(spec.beats, kinds):
        written = _resolved_actions(beat, known)
        speakers = _beat_speakers(project, spec, beat, written, characters)
        seconds, words = _beat_words(project, beat) if ({"gestures", "closeups"} & on or reframe) and speakers else (0.0, ())
        window = joined.get(beat.id)
        if window is not None and seconds:   # only what is heard before the next beat starts (§69.34)
            seconds, words = window.body, tuple(w for w in words if w.end <= window.body + 1e-6)
        beats.append(BeatInput(beat.id, beat.marked_text, tuple(speakers), written, on, seconds, words, window is not None))
    if not reframe or stage is None:
        return _merged_directions(spec, sounds, plan_directions(spec.id, cast, beats, stage))
    pans = {d.beat: d.actions for d in plan_reframe(cast, beats, stage)}
    beats = [replace(b, actions=(*b.actions, *pans[b.id])) if b.id in pans else b for b in beats]
    directed = {d.beat: d.actions for d in plan_directions(spec.id, cast, beats, stage)}
    return _merged_directions(spec, sounds, [
        DirectedBeat(b.id, (*pans.get(b.id, ()), *directed.get(b.id, ()))) for b in beats if b.id in pans or b.id in directed
    ])


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
    """Whether automatic actions are possible: ``auto_direct`` is set anywhere (the video, a
    scene's params, a beat), a ``stage`` scene may reframe (its ``reframe``, else the video's,
    is not ``none``) or has voice sounds: a cheap check before :func:`project_directions`."""
    config = project.config
    if config.auto_direct:
        return True
    if any(spec.type == "stage" and (spec.params.get("reframe") or config.reframe) != "none" for spec in config.scenes):
        return True
    if any(spec.type == "stage" and any(b.voice_sounds for b in spec.beats) for spec in config.scenes):
        return True   # a speaker's face for a voice sound (§69.33)
    return any(spec.params.get("auto_direct") or any(b.auto_direct for b in spec.beats) for spec in config.scenes)


def auto_label(act: ActionConfig) -> str:
    """``look_at kit pip`` / ``react pip surprised`` / ``shot closeup kit`` / ``pan 0.31 cut``: the
    action, its target and option values, a true flag by its name (a shot: its kind first, as the
    ``shot:`` key reads; for the storyboard)."""
    if act.action == "shot":
        return " ".join(["shot", str(act.options.get("kind")), *act.targets()])
    values = [k if v is True else str(v) for k, v in act.options.items() if v is not False]
    return " ".join([act.action, *act.targets(), *values])


def directions_yaml(directed: Mapping[str, Sequence[DirectedBeat]]) -> str:
    """The automatic actions (scene id -> directed beats) as ``video.yaml`` text an author can
    paste and edit: ``scenes`` -> each scene's ``id`` and ``beats`` -> each beat's ``id``, its
    ``shot`` (the ``shot:`` key: ``closeup kit``) and its added ``actions``, one action per line
    in the shorthand form."""
    import yaml

    def flow(data: Any) -> str:
        """``data`` on one line; a scalar quoted only when YAML needs it (``"yes"``)."""
        text = yaml.safe_dump([data], default_flow_style=True, sort_keys=False, width=10**6, allow_unicode=True).strip()
        return text[1:-1]

    lines = [
        "# Actions auto_direct adds (vidgen direct --print). Paste a beat's actions into its actions: list",
        "# (and a shot: line into the beat) and edit them: actions written in a beat win, so the automatic",
        "# ones for those characters go away.",
    ]
    if not directed:
        return "\n".join([*lines, "# Nothing added: auto_direct is off, or no character speaks to another on a stage.", "scenes: []", ""])
    lines.append("scenes:")
    for scene_id, beats in directed.items():
        lines += [f"  - id: {flow(scene_id)}", "    beats:"]
        for beat in beats:
            lines.append(f"      - id: {flow(beat.beat)}")
            shots = [act for act in beat.actions if act.action == "shot"]
            others = [act for act in beat.actions if act.action != "shot"]
            lines += [f"        shot: {flow(' '.join([str(act.options['kind']), *act.targets()]))}" for act in shots[:1]]
            if others:
                lines.append("        actions:")
                lines += [f"          - {flow(act.shorthand())}" for act in others]
    return "\n".join(lines) + "\n"
