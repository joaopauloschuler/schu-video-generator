"""``vidgen screenplay``: a stage project from a screenplay, with no AI involved (DESIGN.md §69.25).

The format (Markdown-like, one element per line or paragraph):

- optional YAML front matter between ``---`` lines: top-level ``video.yaml`` keys (``title``,
  ``theme``, ``voice``, ``voices``, ``characters``, ``format``...; not ``scenes``) that win over
  the generated ones; ``characters`` listed there are *declared* (kept as written);
- ``# Title``: the first heading, when it is a level-1 heading that does not start with
  ``Scene`` or ``Card``; ``# Scene: yard`` (any level) starts a ``stage`` scene, followed by optional
  ``set:`` lines: ``background: night; props: box (kite) at 0.4, tree at right; marks: gate 0.9;
  characters: wren at left`` (:func:`parse_set`); ``# Card: Later that day…`` (any level) is
  a ``card`` scene with that text, silent unless lines follow it, coming in with an
  ``iris_out`` (after another scene), the scene after it with an ``iris_in``;
- ``WREN: line`` (a name in capitals) is a line of that character, ``PELL (doubtful): line``
  one with a manner: words naming a built-in expression or pose (or one of :data:`MANNERS`)
  become a ``react`` for the line; a pronoun among those words (``FEN (she): ...``, ``(he,
  doubtful)``, ``(they)``) states the speaker's voice kind (:data:`PRONOUN_KINDS`; a front matter
  character may say ``voice_kind:`` instead); ``[...]`` inside a line is a stage direction of its speaker
  at that point of the line, except a voice sound marker (``[laugh]``, ``[gasp]``...:
  :mod:`vidgen.voicesounds`), which stays in the line's text;
- a plain paragraph (or ``NARRATOR: ...``) is the narrator's line;
- ``[Wren walks to the box]`` on its own is a stage direction for the next line (the last one
  at the end of a scene): :func:`direction_actions` maps each of its sentences to actions where a
  small grammar matches (walk / run to, enter, exit, jump, look at, point at, wave, nod, shrug,
  shake head; ``has an idea``, ``is confused``, ``falls asleep``, ``cries``... put an effect
  symbol over the head, :data:`_EFFECT_VERBS`); the others become ``# TODO:`` comments above the
  beat.

:func:`parse_screenplay` reads the text (pure); :func:`screenplay_project` builds the
``video.yaml`` mapping and its comments: every character without a declaration gets a generator
look of :data:`LOOKS` (shape, colours and accessories differ; of the stated voice kind when there
is one) and a voice of the provider's list that suits it (:func:`assign_voices`: the look's or
the stated voice kind, other accent first), ``auto_direct: true``. No manim import
(the props' kinds come from :mod:`vidgen.cartoon.props` when a ``set:`` line is read).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import yaml

from vidgen.cartoon.acting import GESTURE_SECONDS, JUMP_SECONDS, walk_seconds
from vidgen.cartoon.directing import LOOK_SECONDS
from vidgen.cartoon.effects import EFFECT_SECONDS
from vidgen.cartoon.motion import jump_motion_seconds, walk_motion_seconds
from vidgen.cartoon.poses import EXPRESSIONS, POSES
from vidgen.cartoon.stage import MARKS, mark_x
from vidgen.errors import VidgenError
from vidgen.voicesounds import is_voice_sound, take_out_sounds

#: Gradients (top to bottom) for ``background: <word>``.
SKIES: dict[str, list[str]] = {
    "day": ["#9CCBEA", "#E4F3FB"],
    "night": ["#1B2140", "#3D4677"],
    "dusk": ["#6C5B9E", "#F4B183"],
    "dawn": ["#F6C1A8", "#FBEBD2"],
    "indoors": ["#E9DCC9", "#F6EFE4"],
}
#: Ground colour per sky word (default: ``tertiary``).
GROUNDS: dict[str, str] = {"night": "#2E4A3A", "indoors": "#C9A27A"}
#: Big props put towards the back by default.
BACKDROP_PROPS: dict[str, float] = {"house": 0.6, "tree": 0.5}
#: Where props without ``at`` go, in turn (the middle stays free for the characters).
PROP_SLOTS: tuple[float, ...] = (0.85, 0.15, 0.65, 0.35)
#: Other words for built-in props in a ``set:`` line.
PROP_WORDS: dict[str, str] = {
    "couch": "sofa", "settee": "sofa", "easy chair": "armchair", "bookcase": "bookshelf", "shelf": "bookshelf",
    "kitchen counter": "counter", "worktop": "counter", "refrigerator": "fridge", "picture frame": "picture",
    "painting": "picture", "carpet": "rug", "plant pot": "houseplant", "potted plant": "houseplant",
    "wall clock": "clock", "television": "tv", "desk with chair": "desk", "desk and chair": "desk",
}
#: The words of a ``room:`` part of a ``set:`` line besides windows and doors.
ROOM_WORDS: dict[str, tuple[str, str | bool]] = {
    "stripes": ("wallpaper", "stripes"), "striped": ("wallpaper", "stripes"), "dots": ("wallpaper", "dots"),
    "dotted": ("wallpaper", "dots"), "plain": ("wallpaper", "plain"), "boards": ("flooring", "boards"),
    "tiles": ("flooring", "tiles"), "tiled": ("flooring", "tiles"), "ceiling": ("ceiling", True),
}
#: Marks for 1-5 characters on a stage, in order of appearance.
PLACES: dict[int, tuple[str, ...]] = {
    1: ("centre",), 2: ("left", "right"), 3: ("left", "centre", "right"),
    4: ("far_left", "left", "right", "far_right"), 5: ("far_left", "left", "centre", "right", "far_right"),
}
#: Closest a character placed automatically stands to one the set places (fraction of the stage).
SPACING = 0.12
#: How far from a prop / a character a walk to it stops (fraction of the stage).
PROP_GAP = 0.1
CHARACTER_GAP = 0.14
#: Walking speed of ``runs to`` (twice the default walk).
RUN_SPEED = 5.0
#: Seconds of a ``# Card:`` without lines (a silent ``card`` scene).
CARD_SECONDS = 2.5
#: Latest ``at`` of a direction's action; where directions after a scene's last line start.
LATEST_AT = 0.95
TRAILING_AT = 0.6
#: Manim units of the frame's shorter side; the narration's words per second for the estimate.
FRAME_UNITS = 8.0
WORDS_PER_SECOND = 2.6
#: Seconds added to each move's estimate (the runner starts a due action on the next frame).
MARGIN = 0.1
#: Manner words that mean a built-in expression or pose (besides their own names).
MANNERS: dict[str, tuple[str, str]] = {
    **{w: ("expression", "happy") for w in ("glad", "cheerful", "excited", "delighted", "pleased", "proud", "smiling", "beaming")},
    **{w: ("expression", "sad") for w in ("unhappy", "upset", "glum", "gloomy", "disappointed", "crying")},
    **{w: ("expression", "angry") for w in ("cross", "annoyed", "furious", "mad", "grumpy", "irritated")},
    **{w: ("expression", "surprised") for w in ("shocked", "amazed", "astonished", "startled", "stunned")},
    **{w: ("expression", "worried") for w in ("nervous", "anxious", "scared", "afraid", "uneasy", "frightened")},
    **{w: ("expression", "thinking") for w in ("doubtful", "puzzled", "curious", "pondering", "unsure", "sceptical", "skeptical")},
    **{w: ("expression", "neutral") for w in ("calm", "flat", "deadpan")},
    "arms crossed": ("pose", "arms_crossed"), "crossing arms": ("pose", "arms_crossed"), "pointing": ("pose", "pointing"),
    "waving": ("pose", "waving"), "shrugging": ("pose", "shrug"), "sitting": ("pose", "sitting"), "standing": ("pose", "stand"),
}
#: Speaker names that mean the narrator.
NARRATOR_NAMES = frozenset({"NARRATOR", "NARRATION", "VOICE OVER", "V.O."})
#: Kinds of voice a character can be given (:func:`assign_voices`); ``neutral`` takes either.
VOICE_KINDS: tuple[str, ...] = ("feminine", "masculine", "neutral")
#: Pronouns in a line's brackets (``FEN (she): ...``) that state its speaker's voice kind.
PRONOUN_KINDS: dict[str, str] = {"she": "feminine", "he": "masculine", "they": "neutral"}
_PRONOUN = re.compile(r"^(she|he|they)(?:\s*/\s*(?:her|him|them))?$", re.IGNORECASE)
#: Generator looks for characters without a declaration, in turn: each differs from the others in
#: body, hair, eyes, accessories and colours (skin, clothes, hair) and has the ``voice_kind`` that
#: suits it (the voice is chosen from that kind); later ones repeat with a seed.
LOOKS: tuple[dict[str, Any], ...] = (
    {"look": {"body": "round", "head_size": 1.15, "eyes": "round", "hair": "bun", "accessories": ["scarf"]},
     "colors": {"skin": "#F2C9A0", "clothes": "primary", "hair": "#6B4226", "accessory": "accent"}, "voice_kind": "feminine"},
    {"look": {"body": "tall", "eyes": "sleepy", "nose": "round", "hair": "short", "ears": "round", "accessories": ["glasses"]},
     "colors": {"skin": "#B97A4E", "clothes": "tertiary", "hair": "#2B2B2B"}, "voice_kind": "masculine"},
    {"look": {"body": "square", "head_size": 0.9, "eyes": "oval", "nose": "triangle", "hair": "spiky", "ears": "pointy", "accessories": ["hat"]},
     "colors": {"skin": "#9BD3AE", "clothes": "accent", "hair": "highlight", "accessory": "secondary"}, "voice_kind": "neutral"},
    {"look": {"body": "bean", "head_size": 1.3, "eyes": "dot", "nose": "dot", "hair": "curly", "ears": "floppy", "accessories": ["bag"]},
     "colors": {"skin": "#8D5A3B", "clothes": "highlight", "hair": "#E7E1D5", "accessory": "primary"}, "voice_kind": "neutral"},
    {"look": {"body": "round", "head_size": 0.85, "eyes": "oval", "hair": "long", "ears": "round", "accessories": ["glasses", "scarf"]},
     "colors": {"skin": "#FFE0BD", "clothes": "secondary", "hair": "#B5532E", "accessory": "tertiary"}, "voice_kind": "feminine"},
    {"look": {"body": "tall", "head_size": 1.1, "eyes": "round", "nose": "dot", "hair": "none", "ears": "round", "accessories": ["hat", "bag"]},
     "colors": {"skin": "#D9A3E0", "clothes": "#5B6C8F", "accessory": "highlight"}, "voice_kind": "masculine"},
    # since Step 113: outfits, patterns, shoes, more hair and accessories (DESIGN.md §69.47)
    {"look": {"body": "pear", "head_size": 1.05, "eyes": "oval", "hair": "ponytail", "outfit": "dress", "pattern": "dots", "shoes": "shoes",
              "accessories": ["necklace"]},
     "colors": {"skin": "#E8B48A", "clothes": "accent", "hair": "#3B2A1E", "accessory": "highlight"}, "voice_kind": "feminine"},
    {"look": {"body": "triangle", "eyes": "dot", "nose": "round", "hair": "none", "facial_hair": "beard", "outfit": "coat", "shoes": "boots",
              "accessories": ["cap"]},
     "colors": {"skin": "#C68B59", "clothes": "#7A5C3E", "hair": "#4A3426", "accessory": "highlight", "trim": "dim"}, "voice_kind": "masculine"},
    {"look": {"body": "bean", "head_size": 1.2, "eyes": "round", "hair": "afro", "outfit": "overalls", "pattern": "stripes", "accessories": ["backpack"]},
     "colors": {"skin": "#6B4429", "clothes": "primary", "hair": "#1E1A17", "accessory": "secondary", "trim": "highlight"}, "voice_kind": "neutral"},
    {"look": {"body": "square", "eyes": "sleepy", "nose": "triangle", "hair": "braids", "outfit": "apron", "shoes": "shoes", "accessories": ["bow"]},
     "colors": {"skin": "#F5D0B5", "clothes": "tertiary", "hair": "#B5532E", "accessory": "highlight", "trim": "#E7E1D5"}, "voice_kind": "feminine"},
    {"look": {"body": "round", "eyes": "oval", "hair": "short", "facial_hair": "moustache", "outfit": "shorts", "pattern": "stripes", "shoes": "shoes"},
     "colors": {"skin": "#A7C7E7", "clothes": "secondary", "hair": "#2B2B2B", "accessory": "accent", "trim": "dim"}, "voice_kind": "masculine"},
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SCENE = re.compile(r"^scene\s*[:.\-–—]?\s*(.*)$", re.IGNORECASE)
_SET = re.compile(r"^set\s*:\s*(.*)$", re.IGNORECASE)
_CARD = re.compile(r"^card\s*[:.\-–—]\s*(\S.*)$", re.IGNORECASE)
_SPEAKER = re.compile(r"^(?P<name>[A-Z][A-Z0-9'’.\-]*(?: [A-Z][A-Z0-9'’.\-]*)*)\s*(?:\((?P<manner>[^)]*)\))?\s*:\s*(?P<text>.*)$")
_INLINE = re.compile(r"\[([^\[\]]*)\]")
_SLUG = re.compile(r"[^a-z0-9]+")
_ARTICLES = re.compile(r"^(?:the|a|an|his|her|their|its|my|your)\s+", re.IGNORECASE)
_LEADING = re.compile(r"^(?:and then|then|and|suddenly|finally|now|slowly|quickly|at last)\s+", re.IGNORECASE)
_TRAILING = re.compile(r"(?:\s+(?:\w+ly|again|away|too))+$", re.IGNORECASE)
_SENTENCES = re.compile(r"\s*(?:[.;!]+(?:\s+|$)|,\s*(?:and\s+)?then\s+|\s+and\s+then\s+)\s*", re.IGNORECASE)
_PRONOUNS = frozenset({"he", "she", "they", "it"})
_CAMERA = frozenset({"camera", "the camera", "us", "the audience", "the viewer", "the viewers"})
_SIDE = r"(?:\s+(?:from|to(?:wards)?|towards|on|at)?\s*(?:the\s+)?(?P<side>left|right))?"
#: The grammar of a direction's predicate (after its subject): pattern -> what it makes.
_VERBS: tuple[tuple[re.Pattern[str], str], ...] = tuple((re.compile(p, re.IGNORECASE), kind) for p, kind in (
    (r"^(?P<verb>walks?|goes|go|steps?|wanders?|strolls?|moves?|heads?|hurr(?:y|ies)|runs?|dash(?:es)?)\s+"
     r"(?:over\s+|back\s+|up\s+|across\s+)?(?:to(?:wards)?|toward|up to)\s+(?P<obj>.+)$", "walk"),
    (r"^(?P<verb>enters?|comes? in|walks? in|runs? in|arrives?|steps? in)" + _SIDE + "$", "enter"),
    (r"^(?P<verb>exits?|leaves?|walks? (?:off|out|away)|goes (?:off|out|away)|runs? (?:off|out|away))" + _SIDE + "$", "exit"),
    (r"^(?:jumps?|hops?|leaps?)(?:\s+(?:up|for joy|with joy|in the air|high|up and down))?$", "jump"),
    (r"^(?:looks?|glances?|stares?|turns?|peeks?|peers?)\s+(?:over\s+|up\s+|back\s+|round\s+|around\s+)?(?:at|to(?:wards)?|toward)\s+(?P<obj>.+)$", "look"),
    (r"^points?\s+(?:at|to(?:wards)?|toward)\s+(?P<obj>.+)$", "point"),
    (r"^waves?(?:\s+(?:at|to)\s+(?P<obj>.+))?$", "wave"),
    (r"^nods?(?:\s+(?:at|to)\s+(?P<obj>.+))?$", "nod"),
    (r"^shrugs?$", "shrug"),
    (r"^shakes?\s+(?:his|her|their|its)\s+head$", "shake_head"),
))
#: Gestures a direction may name (``wave`` / ``nod`` turn to their object first).
_GESTURE_KINDS = ("wave", "nod", "shrug", "shake_head")
_MOOD = r"^(?:is|looks|seems|gets|feels|becomes)\s+(?:very\s+|so\s+|a bit\s+|quite\s+|all\s+)?"
#: Predicates that put an effect symbol over the subject's head (DESIGN.md §69.40): pattern ->
#: the symbol. Tried before :data:`_VERBS`.
_EFFECT_VERBS: tuple[tuple[re.Pattern[str], str], ...] = tuple((re.compile(p, re.IGNORECASE), kind) for p, kind in (
    (r"^(?:has|gets|had|got)\s+(?:an?\s+)?(?:bright\s+|great\s+|sudden\s+|new\s+|good\s+)?idea$|^lights?\s+up$", "idea"),
    (_MOOD + r"(?:confused|puzzled|baffled|lost)$|^wonders?$|^scratch(?:es)?\s+(?:his|her|their|its)\s+head$", "question"),
    (_MOOD + r"(?:startled|alarmed|shocked)$|^startles?$|^gets\s+a\s+fright$", "exclaim"),
    (r"^(?:sweats?|is\s+sweating|breaks?\s+(?:out\s+)?into\s+a\s+sweat|gulps?)$|" + _MOOD + r"nervous$", "sweat"),
    (_MOOD + r"(?:angry|furious|cross|mad)$|^(?:fumes?|seethes?|is\s+fuming)$", "anger"),
    (r"^(?:falls?\s+asleep|is\s+asleep|sleeps?|dozes?(?:\s+off)?|nods?\s+off|snores?|naps?)$", "sleep"),
    (r"^(?:falls?\s+in\s+love|is\s+in\s+love|swoons?|is\s+smitten|is\s+lovestruck)(?:\s+with\s+.+)?$", "hearts"),
    (_MOOD + r"(?:dizzy|dazed)$|^sees?\s+stars$", "stars"),
    (r"^(?:sparkles?|shines?|gleams?|glows?|beams?\s+with\s+pride)$", "sparkle"),
    (r"^(?:cries|cry|weeps?|sheds?\s+a\s+tear|tears?\s+up|sobs?)$", "tear"),
))


# ----- parsing ------------------------------------------------------------------------------------


@dataclass
class Direction:
    """A stage direction (without its brackets), its ``line`` number and, inside a line of
    dialogue, where it falls (``at``, a fraction of the line's words) and its speaker."""

    text: str
    line: int
    at: float | None = None
    speaker: str | None = None


@dataclass
class Line:
    """A spoken line: its ``text`` (inline directions taken out), the ``speaker`` as written
    (``None``: the narrator), its ``manner`` (the words in brackets after the name, a pronoun
    taken out), its ``line`` number, its inline ``directions`` and the speaker's ``voice_kind``
    when the brackets name a pronoun (``(she)``: :data:`PRONOUN_KINDS`)."""

    text: str
    speaker: str | None
    manner: str = ""
    line: int = 0
    directions: list[Direction] = field(default_factory=list)
    voice_kind: str | None = None


@dataclass
class ScriptScene:
    """A ``# Scene:`` section: its ``name``, its ``set:`` text and its lines and directions in
    order; a ``# Card:`` section (``card``: its ``name`` is the card's text) has no set."""

    name: str
    line: int
    set_text: str = ""
    items: list[Line | Direction] = field(default_factory=list)
    card: bool = False


@dataclass
class Screenplay:
    """A parsed screenplay: its ``title`` (``None``: none written), its ``front`` matter and scenes."""

    title: str | None
    front: dict[str, Any]
    scenes: list[ScriptScene]


def _front_matter(lines: list[str]) -> tuple[dict[str, Any], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    end = next((k for k in range(1, len(lines)) if lines[k].strip() in ("---", "...")), None)
    if end is None:
        raise VidgenError("line 1: front matter starts with --- but has no closing --- line")
    try:
        data = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        raise VidgenError(f"front matter is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise VidgenError("front matter must be a mapping of video.yaml keys (title, voice, characters...)")
    if "scenes" in data:
        raise VidgenError("front matter: scenes come from the screenplay's # Scene: headings, not from scenes:")
    return data, end + 1


def _paragraphs(lines: list[str], start: int) -> list[tuple[int, str]]:
    """``(line number, text)`` of each element: headings, ``set:`` and speaker lines stand alone;
    other lines join the element above until a blank line; HTML comments are left out."""
    out: list[tuple[int, str]] = []
    joinable = False
    in_comment = False
    for k in range(start, len(lines)):
        raw = lines[k].strip()
        if in_comment or raw.startswith("<!--"):
            in_comment = "-->" not in raw
            joinable = False
            continue
        if not raw:
            joinable = False
            continue
        alone = bool(_HEADING.match(raw) or _SET.match(raw) or (_SPEAKER.match(raw) and not raw.startswith("[")))
        opens = raw.startswith("[")
        if joinable and not alone and not opens:
            number, text = out[-1]
            out[-1] = (number, f"{text} {raw}")
        else:
            out.append((k + 1, raw))
        joinable = not _HEADING.match(raw) and not _SET.match(raw)
        if opens and raw.endswith("]"):
            joinable = False
    return out


def _speaker_line(match: re.Match[str], number: int) -> Line:
    name = " ".join(match.group("name").split())
    text = match.group("text").strip()
    speaker = None if name.upper() in NARRATOR_NAMES else name
    directions: list[Direction] = []
    words_before = 0
    spoken: list[str] = []
    rest = text
    total = len(_INLINE.sub(" ", text).split())
    while (found := _INLINE.search(rest)) is not None:
        before = rest[: found.start()].split()
        spoken.extend(before)
        words_before += len(before)
        rest = rest[found.end():]
        if is_voice_sound(found.group(1)):   # [laugh] is a voice sound of the line, not a direction
            spoken.append(found.group(0))
            continue
        at = round(min(words_before / total, 0.9), 2) if total else 0.0
        directions.append(Direction(found.group(1).strip(), number, at, speaker))
    spoken.extend(rest.split())
    manner, kind = _pronoun_kind(match.group("manner") or "")
    if kind is not None and speaker is None:
        raise VidgenError(f"line {number}: a pronoun in brackets states a voice kind, but the narrator's voice is the front matter's voice:")
    return Line(" ".join(spoken), speaker, manner, number, directions, kind)


def _pronoun_kind(manner: str) -> tuple[str, str | None]:
    """A line's bracket words without a pronoun (``she, doubtful`` -> ``doubtful``) and the voice
    kind the pronoun states (``None``: none)."""
    kind = None
    kept = []
    for part in (p.strip() for p in manner.split(",")):
        found = _PRONOUN.match(part)
        if found:
            kind = PRONOUN_KINDS[found.group(1).lower()]
        elif part:
            kept.append(part)
    return ", ".join(kept), kind


def parse_screenplay(text: str) -> Screenplay:
    """The screenplay in ``text`` (see the module doc); :class:`VidgenError` names the line of a
    malformed element."""
    lines = text.splitlines()
    front, start = _front_matter(lines)
    title: str | None = None
    scenes: list[ScriptScene] = []
    for number, raw in _paragraphs(lines, start):
        heading = _HEADING.match(raw)
        if heading:
            level, name = len(heading.group(1)), heading.group(2).strip()
            scene_name, card = _SCENE.match(name), _CARD.match(name)
            if level == 1 and not scene_name and not card and title is None and not scenes:
                title = name
                continue
            if card:
                scenes.append(ScriptScene(card.group(1).strip(), number, card=True))
                continue
            name = (scene_name.group(1) if scene_name else name).strip() or f"scene {len(scenes) + 1}"
            scenes.append(ScriptScene(name, number))
            continue
        if not scenes:
            scenes.append(ScriptScene("scene 1", number))
        scene = scenes[-1]
        set_line = _SET.match(raw)
        if set_line:
            if scene.card:
                raise VidgenError(f"line {number}: set: belongs to a # Scene:, not to a # Card: (a card has no stage)")
            if scene.items:
                raise VidgenError(f"line {number}: set: belongs right under its scene's heading, before the first line")
            scene.set_text = f"{scene.set_text}; {set_line.group(1)}" if scene.set_text else set_line.group(1)
            continue
        if raw.startswith("["):
            if not raw.endswith("]"):
                raise VidgenError(f"line {number}: a stage direction starts with [ but does not end with ]")
            scene.items.append(Direction(raw[1:-1].strip(), number))
            continue
        speaker = _SPEAKER.match(raw)
        line = _speaker_line(speaker, number) if speaker else _speaker_line(_SPEAKER.match(f"NARRATOR: {raw}"), number)  # type: ignore[arg-type]
        if not take_out_sounds(line.text)[0]:
            raise VidgenError(f"line {number}: {raw[:40]!r} has nothing to say (a line needs words besides its [directions] and [sounds])")
        scene.items.append(line)
    if not scenes:
        raise VidgenError("the screenplay has no scenes (start one with a heading: # Scene: yard)")
    return Screenplay(title, front, scenes)


# ----- the set ------------------------------------------------------------------------------------


@dataclass
class SetDesign:
    """A scene's ``set:`` line read: stage ``params`` (background, ground_color, marks, props),
    the characters placed by it (name -> place), the props' names (name -> kind), what it did
    not understand (``todos``) and the named set it starts from (``set_name``: a set of
    ``--cast``, whose params are ``set_params``; DESIGN.md §69.35)."""

    params: dict[str, Any]
    placed: dict[str, str | float] = field(default_factory=dict)
    props: dict[str, str] = field(default_factory=dict)
    todos: list[str] = field(default_factory=list)
    set_name: str | None = None
    set_params: dict[str, Any] = field(default_factory=dict)

    def stage_params(self) -> dict[str, Any]:
        """The stage's params with its named set applied (:func:`vidgen.includes.apply_set`)."""
        from vidgen.includes import apply_set

        return apply_set(self.set_params, self.params).params if self.set_name else self.params


def _place(text: str) -> str | float:
    """A mark name or an x position."""
    try:
        return float(text)
    except ValueError:
        word = text.strip().lower().replace(" ", "_")
        return {"center": "centre", "middle": "centre"}.get(word, word)


def _item(text: str) -> tuple[str, str | None, str | float | None]:
    """``box (kite) at 0.4`` -> ``("box", "kite", 0.4)``."""
    found = re.match(r"^(?P<what>[\w\s-]+?)\s*(?:\((?P<name>[^)]*)\))?\s*(?:\bat\s+(?P<at>[\w.\s]+))?$", text.strip())
    if not found:
        return text.strip(), None, None
    at = found.group("at")
    return _ARTICLES.sub("", found.group("what").strip()).lower(), (found.group("name") or "").strip() or None, _place(at) if at else None


_AGAINST_WALL = re.compile(r"\s*\b(?:against|on)\s+(?:the\s+)?(?:back\s+)?wall\b", re.IGNORECASE)


def _room(text: str, design: SetDesign) -> None:
    """A ``room`` part of a ``set:`` line into ``design.params["room"]``: nothing (a room with the
    defaults), or comma separated :data:`ROOM_WORDS`, ``window [at place]`` and ``[open] door
    [(name)] [at place]`` (DESIGN.md §69.43)."""
    room: dict[str, Any] = {}
    for entry in (e.strip() for e in text.split(",") if e.strip()):
        what, name, at = _item(entry)
        opened = what.startswith("open ")
        what = what.removeprefix("open ")
        if what in ROOM_WORDS and name is None and at is None:
            key, word = ROOM_WORDS[what]
            room[key] = word
        elif what == "window" and name is None and not opened:
            room.setdefault("windows", []).append(at if at is not None else "centre")
        elif what == "door":
            door: dict[str, Any] = {"at": at if at is not None else "right"}
            if name:
                door["name"] = re.sub(r"\W+", "_", name.lower()).strip("_")
            if opened:
                door["open"] = True
            room.setdefault("doors", []).append(door if len(door) > 1 else door["at"])
        else:
            design.todos.append(f"set: room {entry!r} is not {', '.join(ROOM_WORDS)}, a window or a door")
    design.params["room"] = room or True


def parse_set(text: str, known_characters: Mapping[str, str], sets: Mapping[str, Any] | None = None) -> SetDesign:
    """A ``set:`` text: ``;``-separated ``key: value`` parts (the colon is optional): ``background``
    (a word of :data:`SKIES`, a theme colour / hex or two of them for a gradient, or a picture
    file: ``image``), ``room`` (an indoor set instead: :func:`_room`), ``props`` (``kind [(name)]
    [at place] [against the wall]``, comma separated; kinds also by :data:`PROP_WORDS`),
    ``marks`` (``name x``) and ``characters`` (``name at place``; names as in
    ``known_characters``, lower-case written name -> character id). A first part naming one of
    ``sets`` (``set: pond; props: ball``) starts from that set: no default sky, its marks and
    characters' places count."""
    from vidgen.cartoon.props import PROP_KINDS

    design = SetDesign({})
    sky = "day"
    asked_sky = ""   # a sky word the line gives
    used: dict[str, int] = {}
    slot = 0
    parts = [p.strip() for p in text.split(";")]
    named = {name.lower(): name for name in sets or {}}
    if parts and parts[0].lower() in named:
        design.set_name = named[parts.pop(0).lower()]
        design.set_params = dict(sets[design.set_name]) if sets and isinstance(sets[design.set_name], Mapping) else {}
        sky = ""
        ids = set(known_characters.values())
        for entry in map(_as_member, design.set_params.get("characters") or []):
            if entry and entry["name"] in ids:
                design.placed[entry["name"]] = entry.get("at", "centre")
    for part in parts:
        if not part:
            continue
        found = re.match(r"^(\w+)\s*:?\s*(.*)$", part)
        if found is None:
            design.todos.append(f"set: {part!r} is not background, props, marks or characters")
            continue
        key, value = found.group(1).lower(), found.group(2).strip()
        if key == "background":
            if re.search(r"\.(png|jpe?g|webp|svg)$", value, re.IGNORECASE):
                design.params["image"] = value
                continue
            colors = [c.strip() for c in re.split(r",|\s+to\s+", value) if c.strip()]
            if value.lower() in SKIES:
                sky = asked_sky = value.lower()
            elif colors and all(re.fullmatch(r"#?[A-Za-z0-9_]+", c) for c in colors):
                design.params["background"] = colors[0] if len(colors) == 1 else colors
                sky = ""
            else:
                design.todos.append(f"set: background {value!r} is not a sky ({', '.join(SKIES)}), a colour or a picture file")
        elif key == "room":
            _room(value, design)
        elif key == "props":
            for entry in (e for e in value.split(",") if e.strip()):
                walled = _AGAINST_WALL.search(entry) is not None
                kind, name, at = _item(_AGAINST_WALL.sub("", entry))
                kind = PROP_WORDS.get(kind, kind)
                if kind not in PROP_KINDS:
                    design.todos.append(f"set: prop {entry.strip()!r} is not a built-in prop ({', '.join(PROP_KINDS)}); use svg: for your own")
                    continue
                if at is None:
                    at = PROP_SLOTS[slot % len(PROP_SLOTS)]
                    slot += 1
                prop: dict[str, Any] = {"prop": kind}
                if name:
                    prop["name"] = re.sub(r"\W+", "_", name.lower()).strip("_")
                prop["at"] = at
                if walled:
                    prop["against"] = "wall"
                elif kind in BACKDROP_PROPS:
                    prop["depth"] = BACKDROP_PROPS[kind]
                used[kind] = used.get(kind, 0) + 1
                own = prop.get("name") or (kind if used[kind] == 1 else f"{kind}_{used[kind]}")
                design.props[own] = kind
                design.params.setdefault("props", []).append(prop)
        elif key == "marks":
            for entry in (e for e in value.split(",") if e.strip()):
                found = re.match(r"^\s*(\w+)\s*(?:at\s+)?([0-9.]+)\s*$", entry)
                if found and 0.0 <= float(found.group(2)) <= 1.0:
                    design.params.setdefault("marks", {})[found.group(1).lower()] = float(found.group(2))
                else:
                    design.todos.append(f"set: mark {entry.strip()!r} is not 'name x' (x from 0 to 1)")
        elif key in ("characters", "cast"):
            for entry in (e for e in value.split(",") if e.strip()):
                who, _, at = _item(entry)
                if who not in known_characters:
                    design.todos.append(f"set: {entry.strip()!r}: no character called {who!r} speaks or is declared")
                    continue
                design.placed[known_characters[who]] = at if at is not None else "centre"
        else:
            design.todos.append(f"set: {part!r} is not background, room, props, marks or characters")
    indoors = design.stage_params().get("room") is not None
    if "room" in design.params:
        given = [k for k in ("image", "background") if k in design.params or (k == "background" and asked_sky)]
        if given:
            design.todos.append(f"set: a room draws its own wall and floor; {' and '.join(given)} left out")
        for k in given:
            design.params.pop(k, None)
    elif "image" not in design.params and sky:
        design.params["background"] = SKIES[sky]
    if "image" not in design.params and design.set_name is None and not indoors:
        design.params["ground_color"] = GROUNDS.get(sky, "tertiary")
    for prop in design.params.get("props", []):
        if prop.get("against") and not indoors:
            prop.pop("against")
            design.todos.append(f"set: {prop['prop']} against the wall needs a room (room: ...)")
    marks = design.stage_params().get("marks")
    for name, at in design.placed.items():
        try:
            mark_x(at, marks)
        except ValueError as exc:
            design.todos.append(f"set: {name} at {at}: {exc}")
    for prop in design.params.get("props", []):
        try:
            mark_x(prop["at"], marks)
        except ValueError as exc:
            design.todos.append(f"set: {prop['prop']} at {prop['at']}: {exc}")
    return design


# ----- stage directions ---------------------------------------------------------------------------


@dataclass
class StageState:
    """What a scene's directions know while they are read in order: the characters' x (0-1, ``None``
    off stage or unknown) and where they stand at first (``home``), the props' x and kinds, the
    stage's marks, the names (written, lower case -> id), the stage's width in Manim units, and
    the last subjects and object."""

    x: dict[str, float | None]
    home: dict[str, float]
    props: dict[str, float]
    kinds: dict[str, str]
    marks: dict[str, float]
    names: dict[str, str]
    width: float = 14.22
    last: list[str] = field(default_factory=list)
    last_object: str | float | None = None


def _subjects(text: str, state: StageState) -> tuple[list[str], str] | None:
    """The characters a sentence starts with (``Wren``, ``Wren and Pell``, a pronoun for the last
    ones) and the rest of it."""
    words = text.split()
    lowered = [w.lower().strip(",") for w in words]
    if lowered and lowered[0] in _PRONOUNS and state.last and (lowered[0] == "they" or len(state.last) == 1):
        return list(state.last), " ".join(words[1:])
    found: list[str] = []
    k = 0
    names = sorted(state.names, key=lambda n: -len(n.split()))
    while k < len(words):
        for name in names:
            size = len(name.split())
            if " ".join(lowered[k : k + size]) == name:
                found.append(state.names[name])
                k += size
                break
        else:
            break
        if k < len(words) and lowered[k] in ("and", ",", "&"):
            k += 1
        elif k < len(words) and words[k - 1].endswith(","):
            continue
        else:
            break
    if not found or k >= len(words):
        return None
    return list(dict.fromkeys(found)), " ".join(words[k:])


def _object(text: str, state: StageState, *, camera: bool) -> tuple[str, str | float] | None:
    """What a direction's object names: ``("character" | "prop" | "mark" | "camera", value)``."""
    plain = _ARTICLES.sub("", text.strip().strip(".,!").lower()).strip()
    found = _named_object(plain, text, state, camera=camera)
    if found is not None:
        state.last_object = found[1]
    return found


def _named_object(plain: str, text: str, state: StageState, *, camera: bool) -> tuple[str, str | float] | None:
    if plain in ("it", "him", "her", "them") and state.last_object is not None:
        value = state.last_object
        kind = "character" if value in state.names.values() else "prop" if value in state.props else "camera" if value == "camera" else "mark"
        return None if kind == "camera" and not camera else (kind, value)
    if camera and (plain in _CAMERA or text.strip().lower() in _CAMERA):
        return "camera", "camera"
    if plain in state.names:
        return "character", state.names[plain]
    if plain.replace(" ", "_") in state.props:
        return "prop", plain.replace(" ", "_")
    kinds = [name for name, kind in state.kinds.items() if kind == plain]
    if len(kinds) == 1:
        return "prop", kinds[0]
    place = _place(re.sub(r"\s+(?:side|edge)$", "", plain))
    if isinstance(place, float) and 0.0 <= place <= 1.0:
        return "mark", place
    if isinstance(place, str) and place in {**MARKS, **state.marks}:
        return "mark", place
    return None


def _target_x(state: StageState, who: str, kind: str, value: str | float) -> float | str:
    """Where a walk to ``value`` ends: a mark as it is, else beside the character / prop on the
    walker's side; when another character stands there, the other side, then a character's gap
    further out (so two walks to one tree do not end on one spot)."""
    if kind == "mark":
        return value
    there = state.props[str(value)] if kind == "prop" else state.x.get(str(value))
    if there is None:
        there = state.home.get(str(value), 0.5)
    here = state.x.get(who)
    here = state.home.get(who, 0.5) if here is None else here
    gap = PROP_GAP if kind == "prop" else CHARACTER_GAP
    side = -1.0 if here <= there else 1.0
    others = [x for name, x in state.x.items() if name != who and x is not None]
    for extra in range(len(others) + 1):
        for sign in (side, -side):
            x = round(there + sign * (gap + extra * CHARACTER_GAP), 2)
            if 0.05 <= x <= 0.95 and all(abs(x - other) >= CHARACTER_GAP - 1e-6 for other in others):
                return x
    return round(min(max(there + side * gap, 0.05), 0.95), 2)


def _clauses(sentence: str, state: StageState) -> list[str]:
    """A sentence cut at ``and`` where the next words do not start with a character's name
    (``Wren walks to the box and points at it``; not ``Wren and Pell jump``)."""
    parts = re.split(r",?\s+and\s+", sentence)
    out = [parts[0]]
    for part in parts[1:]:
        lowered = part.lower()
        if any(lowered == n or lowered.startswith(f"{n} ") or lowered.startswith(f"{n},") for n in state.names):
            out[-1] = f"{out[-1]} and {part}"
        else:
            out.append(part)
    return out


def direction_actions(text: str, state: StageState, default: str | None = None) -> tuple[list[list[dict[str, Any]]], list[str]]:
    """The actions of a stage direction, one list per sentence or clause matched (in order), and
    the sentences (or clauses) no rule matches. ``default`` is the subject of a sentence that names none (the
    speaker, for a direction inside a line); a clause after ``and`` has its sentence's subject.
    Updates ``state`` (who stands where, the last subjects and object)."""
    groups: list[list[dict[str, Any]]] = []
    unmatched: list[str] = []
    for sentence in (s.strip() for s in _SENTENCES.split(text.strip())):
        if not sentence:
            continue
        subjects: list[str] | None = [default] if default else None
        for clause in _clauses(sentence, state):
            clause = _LEADING.sub("", clause).strip(" ,")
            found = _subjects(clause, state)
            if found is None and subjects:
                found = subjects, clause
            actions = None
            if found is not None:
                actions = _predicate(found[1], found[0], state)
                trimmed = _TRAILING.sub("", found[1]).strip()
                if actions is None and trimmed != found[1]:
                    actions = _predicate(trimmed, found[0], state)
            if actions is None or found is None:
                unmatched.append(clause)
                continue
            subjects = found[0]
            state.last = list(subjects)
            groups.append(actions)
    return groups, unmatched


def _predicate(text: str, who: list[str], state: StageState) -> list[dict[str, Any]] | None:
    target: str | list[str] = who[0] if len(who) == 1 else list(who)
    for pattern, symbol in _EFFECT_VERBS:
        if pattern.match(text):
            return [{"effect": target, "to": symbol, "_seconds": EFFECT_SECONDS + MARGIN}]
    for pattern, kind in _VERBS:
        found = pattern.match(text)
        if not found:
            continue
        groups = found.groupdict()
        obj_text = groups.get("obj")
        fast = bool(re.match(r"^(?:runs?|dash|hurr)", groups.get("verb") or "", re.IGNORECASE))
        speed = {"speed": RUN_SPEED} if fast else {}
        pace = RUN_SPEED if fast else None
        if kind == "walk":
            obj = _object(obj_text or "", state, camera=False)
            if obj is None or obj[0] == "camera" or obj[1] in who:
                return None
            out = []
            for name in who:
                to = _target_x(state, name, obj[0], obj[1])
                end = mark_x(to, state.marks) if isinstance(to, str) else to
                out.append({"walk_to": name, "to": to, **speed, "_seconds": _walk_time(state, _here(state, name), end, pace)})
                state.x[name] = end
            return out
        if kind in ("enter", "exit"):
            side = {"side": groups["side"].lower()} if groups.get("side") else {}
            seconds = 0.0
            for name in who:
                here = _here(state, name)
                edge = (0.0 if side["side"] == "left" else 1.0) if side else (0.0 if here < 0.5 else 1.0)
                seconds = max(seconds, _walk_time(state, edge, here, pace))
                state.x[name] = state.home.get(name) if kind == "enter" else None
            return [{kind: target, **side, **speed, "_seconds": seconds}]
        if kind == "jump":
            return [{"jump": target, "_seconds": jump_motion_seconds(JUMP_SECONDS, 1.0) + MARGIN}]
        if kind == "look":
            if obj_text and obj_text.strip().lower() in ("each other", "one another") and len(who) == 2:
                return [_look(who[0], who[1]), _look(who[1], who[0])]
            obj = _object(obj_text or "", state, camera=True)
            return None if obj is None else [_look(target, obj[1])]
        if kind == "point":
            obj = _object(obj_text or "", state, camera=True)
            if obj is None:
                return None
            return [_look(target, obj[1]), _gesture(target, "point", LOOK_SECONDS)]
        if kind in _GESTURE_KINDS:
            obj = _object(obj_text, state, camera=True) if obj_text else None
            if obj_text and obj is None:
                return None
            if obj is None:
                return [_gesture(target, kind)]
            return [_look(target, obj[1]), _gesture(target, kind, LOOK_SECONDS)]
    return None


def _look(who: str | list[str], to: str | float) -> dict[str, Any]:
    return {"look_at": who, "to": to, "_seconds": LOOK_SECONDS + MARGIN}


def _gesture(who: str | list[str], kind: str, after: float = 0.0) -> dict[str, Any]:
    return {"gesture": who, "to": kind, "_after": after + MARGIN if after else 0.0, "_seconds": GESTURE_SECONDS[kind]}


def _here(state: StageState, name: str) -> float:
    here = state.x.get(name)
    return state.home.get(name, 0.5) if here is None else here


def _walk_time(state: StageState, start: float, end: float, speed: float | None) -> float:
    """Estimated seconds of a walk from ``start`` to ``end`` (stage fractions) with the lively
    wind-up and settle; off stage is a tenth of the stage beyond the edge."""
    if start in (0.0, 1.0) or end in (0.0, 1.0):
        start, end = min(start, end) - (0.1 if min(start, end) == 0.0 else 0.0), max(start, end) + (0.1 if max(start, end) == 1.0 else 0.0)
    return walk_motion_seconds(walk_seconds(abs(end - start) * state.width, *([speed] if speed else [])), 1.0) + MARGIN


# ----- the project --------------------------------------------------------------------------------


def character_id(name: str) -> str:
    """``OLD PIP`` -> ``old_pip``."""
    return _SLUG.sub("_", name.lower()).strip("_") or "character"


def _display(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split())


def manner_actions(manner: str) -> tuple[dict[str, str], list[str]]:
    """``{expression, pose}`` of a line's manner (``doubtful, arms crossed``) and the words that
    name neither."""
    found: dict[str, str] = {}
    unknown: list[str] = []
    for part in (p.strip().lower() for p in re.split(r",|;|\band\b", manner) if p.strip()):
        word = part.replace(" ", "_")
        if word in EXPRESSIONS:
            found.setdefault("expression", word)
        elif word in POSES:
            found.setdefault("pose", word)
        elif part in MANNERS:
            kind, name = MANNERS[part]
            found.setdefault(kind, name)
        else:
            unknown.append(part)
    return found, unknown


def assign_voices(
    voice: Mapping[str, Any], language: str | None, kinds: int | Sequence[str | None]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Voice settings for characters of the given voice ``kinds`` (:data:`VOICE_KINDS`; ``None``
    or ``neutral``: either; a count: that many without a kind) with the base ``voice`` (its
    provider) and the video's ``language``. Kokoro: from the voices of the character's kind
    (``feminine``: ``?f_``, ``masculine``: ``?m_``; a neutral one balances the two), the least
    used accent of the language first, best grade first, the narrator's voice left out and its
    own kind of voice last; OpenRouter: the model's listed voices in turn (no kinds known);
    ElevenLabs has no list here (the entries stay empty) and a note says so."""
    from vidgen import kokoro_voices
    from vidgen.tts.openrouter import known_voices

    wanted = [None] * kinds if isinstance(kinds, int) else list(kinds)
    count = len(wanted)
    provider = voice.get("provider", "elevenlabs")
    if provider == "kokoro":
        narrator, lang = kokoro_voices.resolve(voice.get("voice"), voice.get("lang"), language)
        if lang is None:
            return [{} for _ in range(count)], ["the video's language has no Kokoro voices: give each voices: entry a voice"]
        langs = [lang, "b" if lang == "a" else "a"] if lang in ("a", "b") else [lang]
        groups: list[list[str]] = []
        for accent in langs:
            for gender in ("f", "m"):
                names = [v for v in kokoro_voices.voices_of(accent) if v[1] == gender and v != narrator and "santa" not in v]
                if names:
                    groups.append(names)
        mine = (narrator or "")[:2]
        groups.sort(key=lambda g: g[0][:2] == mine)   # the narrator's own kind of voice last
        if not groups:
            return [{} for _ in range(count)], [f"Kokoro lists no other voice of lang {lang}: give each voices: entry a voice"]
        return [{"voice": v} for v in _kokoro_picks(groups, wanted)], []
    if provider == "openrouter":
        listed = [v for v in known_voices(str(voice.get("model", ""))) or [] if v != voice.get("voice")]
        if not listed:
            return [{} for _ in range(count)], [f"the model {voice.get('model')} lists no voices here: give each voices: entry a voice"]
        return [{"voice": listed[k % len(listed)]} for k in range(count)], []
    return [{} for _ in range(count)], ["every character speaks with the base voice: give each voices: entry its own voice_id"]


def _kokoro_picks(groups: Sequence[Sequence[str]], kinds: Sequence[str | None]) -> list[str]:
    """A voice of ``groups`` (Kokoro voices of one accent and gender each, in order of
    preference) for each of ``kinds``: of the kind's gender when there is one, the least used
    group and accent first; a neutral kind takes the gender used least so far."""
    group_uses = [0] * len(groups)
    accent_uses: dict[str, int] = {}
    gender_uses = {"f": 0, "m": 0}
    picks = []
    for kind in kinds:
        gender = {"feminine": "f", "masculine": "m"}.get(kind or "")
        fitting = [k for k, g in enumerate(groups) if g[0][1] == gender] or list(range(len(groups)))
        best = min(fitting, key=lambda k: (0 if gender else gender_uses[groups[k][0][1]], group_uses[k], accent_uses.get(groups[k][0][0], 0), k))
        group = groups[best]
        picks.append(group[group_uses[best] % len(group)])
        group_uses[best] += 1
        accent_uses[group[0][0]] = accent_uses.get(group[0][0], 0) + 1
        gender_uses[group[0][1]] = gender_uses.get(group[0][1], 0) + 1
    return picks


@dataclass
class ScreenplayProject:
    """The ``video.yaml`` mapping made from a screenplay, with the comments to write above the
    video's keys (``notes``), each scene and each beat (``# TODO:`` texts), and the generated
    characters' names."""

    config: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    scene_todos: list[list[str]] = field(default_factory=list)
    beat_todos: list[list[list[str]]] = field(default_factory=list)
    generated: list[str] = field(default_factory=list)

    @property
    def todo_count(self) -> int:
        """``# TODO:`` comments in the project."""
        return len(self.notes) + sum(map(len, self.scene_todos)) + sum(len(t) for beat in self.beat_todos for t in beat)


#: The generated project's defaults (front matter keys win).
DEFAULTS: dict[str, Any] = {
    "format": {"width": 1920, "height": 1080, "fps": 30},
    "preview": {"width": 854, "height": 480, "fps": 15},
    "theme": {"preset": "soft_pastel"},
    "voice": {"provider": "kokoro", "voice": "bf_emma", "speed": 0.85},
    "narration": {"pad": 0.7},
    "auto_direct": True,
}


def _speakers(play: Screenplay) -> list[str]:
    return list(dict.fromkeys(item.speaker for scene in play.scenes for item in scene.items if isinstance(item, Line) and item.speaker))


def _stated_kinds(play: Screenplay, declared: list[dict[str, Any]]) -> dict[str, str]:
    """Character id -> the voice kind the screenplay states: ``voice_kind:`` of a front matter
    character (taken out of the entry, which ``video.yaml`` does not know) or a pronoun in a
    line's brackets (``FEN (she): ...``). Two different kinds for one character are an error."""
    stated: dict[str, tuple[str, str]] = {}

    def state(cid: str, kind: str, where: str) -> None:
        if kind not in VOICE_KINDS:
            raise VidgenError(f"{where}: voice_kind {kind!r} is not one of {', '.join(VOICE_KINDS)}")
        if cid in stated and stated[cid][0] != kind:
            raise VidgenError(f"{where}: {cid} is {kind} here but {stated[cid][0]} at {stated[cid][1]}")
        stated.setdefault(cid, (kind, where))

    for entry in declared:
        if "voice_kind" in entry:
            state(str(entry.get("name")), str(entry.pop("voice_kind")), "front matter")
    for scene in play.scenes:
        for item in scene.items:
            if isinstance(item, Line) and item.speaker and item.voice_kind:
                state(character_id(item.speaker), item.voice_kind, f"line {item.line}")
    return {cid: kind for cid, (kind, _) in stated.items()}


def _pick_look(kind: str | None, uses: Sequence[int]) -> int:
    """The index in :data:`LOOKS` of the look for a generated character of voice ``kind``
    (``None``: any), ``uses`` being how often each look is taken: a look of that kind (then a
    neutral one) used least, else the least used look, in order."""
    def fit(k: int) -> int:
        own = LOOKS[k]["voice_kind"]
        return 0 if kind is None or own == kind else 1 if own == "neutral" else 2

    return min(range(len(LOOKS)), key=lambda k: (fit(k), uses[k], k))


def screenplay_project(
    play: Screenplay, default_title: str = "Untitled", cast: Mapping[str, Any] | None = None, include: str | None = None
) -> ScreenplayProject:
    """The stage project of ``play`` (see the module doc). With ``cast`` (an include file read
    by :func:`vidgen.includes.read_include_file`, ``vidgen screenplay --cast``) its characters
    count as declared and keep their voices, its sets are what ``set: NAME`` lines name, and the
    project includes it (``include``: its path from the project folder) instead of copying it."""
    front = dict(play.front)
    cast = cast or {}
    declared: list[dict[str, Any]] = [dict(c) for c in front.pop("characters", None) or [] if isinstance(c, dict)]
    from_cast = [dict(c) for c in cast.get("characters") or [] if isinstance(c, dict) and isinstance(c.get("name"), str)]
    declared_ids = {str(c.get("name")) for c in [*declared, *from_cast]}
    written = {character_id(s): s for s in _speakers(play)}
    names = {_display(s).lower(): character_id(s) for s in written.values()}
    for entry in [*declared, *from_cast]:
        names.setdefault(str(entry.get("name", "")).replace("_", " ").lower(), str(entry.get("name")))
    last_words = [n.split()[-1] for n in names if " " in n]
    for name, cid in list(names.items()):   # "Ash" for OLD ASH, when no one else is called that
        if " " in name and last_words.count(name.split()[-1]) == 1:
            names.setdefault(name.split()[-1], cid)
    config: dict[str, Any] = {"title": front.pop("title", None) or play.title or default_title}
    if include is not None:
        config["include"] = [include]
    for key, value in DEFAULTS.items():
        config[key] = front.pop(key, value)
    voices: dict[str, Any] = dict(front.pop("voices", None) or {})
    config.update(front)
    project = ScreenplayProject(config)

    stated = _stated_kinds(play, declared)
    generated = [cid for cid in written if cid not in declared_ids]
    characters = [*declared]
    kinds: dict[str, str] = dict(stated)
    uses = [0] * len(LOOKS)
    for k, cid in enumerate(generated):
        pick = _pick_look(stated.get(cid), uses)
        look = LOOKS[pick]
        entry = {"name": cid, "look": dict(look["look"]), "colors": dict(look["colors"])}
        if uses[pick]:
            entry["look"]["seed"] = k
        uses[pick] += 1
        kinds.setdefault(cid, look["voice_kind"])
        characters.append(entry)
    project.generated = generated
    speaking = [c for c in characters if c["name"] in written and not c.get("voice")]
    voice_base = config["voice"] if isinstance(config["voice"], dict) else {}
    settings, notes = assign_voices(voice_base, config.get("language"), [kinds.get(c["name"]) for c in speaking])
    wished = [f"{c['name']}: {kinds[c['name']]}" for c in speaking if kinds.get(c["name"])]
    if notes and voice_base.get("provider", "elevenlabs") == "elevenlabs" and wished:
        notes = [f"{notes[0]} of the kind that suits the character ({', '.join(wished)})", *notes[1:]]
    project.notes.extend(notes)
    for entry, setting in zip(speaking, settings):
        name = f"{entry['name']}_voice"
        voices.setdefault(name, {**setting, "label": _display(written[entry["name"]])})
        entry["voice"] = name
    if voices:
        config["voices"] = voices
    if characters or not from_cast:
        config["characters"] = characters
    config["scenes"] = []
    used: dict[str, int] = {}
    voice_of = {str(c["name"]): c.get("voice") for c in [*from_cast, *characters]}
    sets = cast.get("sets") if isinstance(cast.get("sets"), Mapping) else {}
    for k, scene in enumerate(play.scenes):
        if scene.card:
            _add_card(project, scene, voice_of, used)
        else:
            _add_scene(project, scene, names, voice_of, used, sets)
        if k and play.scenes[k - 1].card:   # the scene after a card opens with an iris
            entry = project.config["scenes"][-1]
            project.config["scenes"][-1] = {"id": entry["id"], "type": entry["type"], "transition": "iris_in", **entry}
    return project


def _scene_id(name: str, used: dict[str, int]) -> str:
    """A scene id from a heading's name, numbered from its second use (``yard``, ``yard_2``)."""
    base = character_id(name)
    used[base] = used.get(base, 0) + 1
    return base if used[base] == 1 else f"{base}_{used[base]}"


def _add_card(project: ScreenplayProject, scene: ScriptScene, voice_of: Mapping[str, Any], used: dict[str, int]) -> None:
    """A ``# Card:`` section as a ``card`` scene: silent for :data:`CARD_SECONDS` without lines,
    else narrated by them (stage directions become TODOs: a card has no stage); after another
    scene it comes in with an ``iris_out``."""
    entry: dict[str, Any] = {"id": _scene_id(scene.name, used), "type": "card", "params": {"text": scene.name}}
    if project.config["scenes"]:
        entry["transition"] = "iris_out"
    beats: list[dict[str, Any]] = []
    todos: list[list[str]] = []
    pending: list[str] = []
    for item in scene.items:
        if isinstance(item, Direction):
            pending.append(f"TODO: [{item.text}] (line {item.line}): a card has no stage; act it in the scene before or after")
            continue
        beat: dict[str, Any] = {"text": item.text}
        cid = character_id(item.speaker) if item.speaker else None
        if cid and voice_of.get(cid):
            beat["voice"] = voice_of[cid]
        notes = pending + [f"TODO: [{d.text}] (line {d.line}): a card has no stage" for d in item.directions]
        pending = []
        beats.append(beat)
        todos.append(notes)
    if beats:
        entry["beats"] = beats
        todos[-1].extend(pending)
    else:
        entry["duration"] = CARD_SECONDS
    project.config["scenes"].append(entry)
    project.scene_todos.append([] if beats else pending)
    project.beat_todos.append(todos)


def _scene_cast(scene: ScriptScene, names: Mapping[str, str], design: SetDesign) -> list[str]:
    """The characters on a scene's stage: placed by its set, speaking, or named by a direction."""
    found: list[str] = list(design.placed)
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b", re.IGNORECASE) if names else None
    for item in scene.items:
        if isinstance(item, Line) and item.speaker:
            found.append(character_id(item.speaker))
        texts = [item.text] if isinstance(item, Direction) else [d.text for d in item.directions]
        for text in texts:
            found.extend(names[m.lower()] for m in (pattern.findall(text) if pattern else []))
    return list(dict.fromkeys(found))


def _add_scene(
    project: ScreenplayProject, scene: ScriptScene, names: Mapping[str, str], voice_of: Mapping[str, Any], used: dict[str, int], sets: Mapping[str, Any]
) -> None:
    from vidgen.includes import entry_names

    scene_id = _scene_id(scene.name, used)
    design = parse_set(scene.set_text, names, sets)
    stage = design.stage_params()
    marks = dict(stage.get("marks") or {})
    cast = _scene_cast(scene, names, design)
    taken = [mark_x(at, marks) for at in design.placed.values() if _valid_place(at, marks)]
    free = [m for m in PLACES.get(len(cast), ()) if all(abs(MARKS[m] - x) >= SPACING for x in taken)]
    placed: list[dict[str, Any]] = []
    for k, name in enumerate(cast):
        at = design.placed.get(name)
        if at is None:
            at = free.pop(0) if free else round((k + 1) / (len(cast) + 1), 2)
        placed.append({"name": name, "at": at})
    order = ("image", "background", "ground_color", "room", "marks", "props")
    by_set = {e["name"]: e.get("at", "centre") for e in map(_as_member, design.set_params.get("characters") or []) if e}
    written = [p for p in placed if by_set.get(p["name"]) != p["at"]]   # the set already places the others
    params = {**{k: design.params[k] for k in order if k in design.params}, "characters": written}
    stage_props = [(name, _as_prop(p)) for name, p in zip(entry_names("props", stage.get("props") or []), stage.get("props") or [])]
    kinds = {str(name): p.get("prop") or "prop" for name, p in stage_props}
    props = {str(name): mark_x(p.get("at", "centre"), marks) for name, p in stage_props if _valid_place(p.get("at", "centre"), marks)}
    home = {p["name"]: mark_x(p["at"], marks) for p in placed if _valid_place(p["at"], marks)}
    fmt = project.config.get("format") or {}
    width, height = (fmt.get("width", 16), fmt.get("height", 9)) if isinstance(fmt, dict) else (16, 9)
    state = StageState(dict(home), home, props, kinds, marks, {**names}, FRAME_UNITS * max(width / height, 1.0))
    narration = project.config.get("narration")
    words_per_second = float(narration.get("words_per_second", WORDS_PER_SECOND)) if isinstance(narration, dict) else WORDS_PER_SECOND
    beats: list[dict[str, Any]] = []
    todos: list[list[str]] = []
    pending: list[tuple[Direction, list[list[dict[str, Any]]], list[str]]] = []

    def attach(beat: dict[str, Any], notes: list[str], groups: list[list[dict[str, Any]]], unmatched: list[str], start: float, direction: str) -> float:
        """Add the groups' actions to ``beat`` one group after the other from ``start`` seconds
        (each by its estimated length); returns when the last one ends."""
        seconds = max(len(beat["text"].split()) / words_per_second, 0.1)
        for group in groups:
            length = 0.0
            for action in group:
                after, took = action.pop("_after", 0.0), action.pop("_seconds", 0.0)
                at = min(math.floor((start + after) / seconds * 100) / 100, LATEST_AT)
                beat.setdefault("actions", []).append({**action, **({"at": at} if at > 0 else {})})
                length = max(length, after + took)
            start += length
        notes.extend(f"TODO: [{s}] ({direction}): no action matches it; write it as actions (walk_to, enter, exit, jump, look_at, gesture...)" for s in unmatched)
        return start

    for item in scene.items:
        if isinstance(item, Direction):
            groups, unmatched = direction_actions(item.text, state)
            pending.append((item, groups, unmatched))
            continue
        beat: dict[str, Any] = {"text": item.text}
        notes: list[str] = []
        cid = character_id(item.speaker) if item.speaker else None
        if cid and voice_of.get(cid):
            beat["voice"] = voice_of[cid]
        cursor = 0.0
        for direction, groups, unmatched in pending:
            cursor = attach(beat, notes, groups, unmatched, cursor, f"line {direction.line}")
        pending.clear()
        if item.manner:
            change, unknown = manner_actions(item.manner)
            if cid and change:
                beat.setdefault("actions", []).insert(0, {"react": cid, **change})
            if unknown or (change and not cid):
                notes.append(f"TODO: ({item.manner}) (line {item.line}): no expression or pose matches "
                              f"{', '.join(unknown) or item.manner}; react / emote / pose take {', '.join(EXPRESSIONS)}; {', '.join(POSES)}")
        for direction in item.directions:
            groups, unmatched = direction_actions(direction.text, state, cid)
            attach(beat, notes, groups, unmatched, (direction.at or 0.0) * len(item.text.split()) / words_per_second, f"line {direction.line}")
        beats.append(beat)
        todos.append(notes)
    if not beats:
        raise VidgenError(f"line {scene.line}: scene {scene.name!r} has no lines (a stage scene needs at least one line to speak)")
    cursor = TRAILING_AT * len(beats[-1]["text"].split()) / words_per_second
    for direction, groups, unmatched in pending:
        cursor = attach(beats[-1], todos[-1], groups, unmatched, cursor, f"line {direction.line}")
    project.config["scenes"].append({"id": scene_id, "type": "stage", **({"set": design.set_name} if design.set_name else {}), "params": params, "beats": beats})
    project.scene_todos.append([f"TODO: {t}" for t in design.todos])
    project.beat_todos.append(todos)


def _as_member(entry: Any) -> dict[str, Any]:
    """A stage's character entry as a mapping (``nib`` -> ``{name: nib}``); ``{}`` if malformed."""
    found = {"name": entry} if isinstance(entry, str) else dict(entry) if isinstance(entry, Mapping) else {}
    return found if isinstance(found.get("name"), str) else {}


def _as_prop(entry: Any) -> dict[str, Any]:
    """A stage's prop entry as a mapping (``tree`` -> ``{prop: tree}``)."""
    return {"prop": entry} if isinstance(entry, str) else dict(entry) if isinstance(entry, Mapping) else {}


def _valid_place(at: str | float, marks: Mapping[str, float]) -> bool:
    try:
        mark_x(at, marks)
    except ValueError:
        return False
    return True
