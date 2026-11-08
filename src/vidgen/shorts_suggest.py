"""Shorts suggestions (DESIGN.md §105.6): windows of a longer video that would make good Shorts,
scored by rules, with a hook line each, written as ``cut:`` variants on request. No model is
called: an agent driving vidgen can take the report and refine the cuts.

How it works:

- **Timing** (:func:`timed_beats`): every narrated beat with its planned start and length
  (:class:`vidgen.videoplan.VideoPlan`: the MP3's length when the narration exists, else the
  word-count estimate at ``narration.words_per_second``, as the silent storyboard times it).
- **Windows** (:func:`candidate_windows`): runs of consecutive beats of narrated scenes (a
  silent scene — a card — breaks a run) whose planned length with the end card lies between
  ``min_seconds`` and ``max_seconds``; they start and end on beat boundaries. A window whose
  beat has an action ``until`` a beat outside it, or that starts on an ``overlap`` /
  ``interrupt`` beat, is left out.
- **Score** (:func:`score_window`): dialogue density, questions, exclamations, emotional and
  action words, action beats, variety (scenes, speakers, shots), a clean start (a scene's start;
  not a reply or a sentence opening on ``he`` / ``then``...), a strong last line, a length near
  :data:`IDEAL_SECONDS`; a window holding the film's ending (:func:`ending_beats`) loses
  :data:`SPOILER_PENALTY` unless spoilers are allowed. The best windows are kept greedily, each
  overlapping a kept one by at most :data:`MAX_OVERLAP` of its length.
- **Hook** (:func:`hook_line`): a question or exclamation from the window's dialogue (else
  narration), shortened to at most :data:`HOOK_WORDS` words (a clause of it, fillers dropped);
  else a template from the window's situation (:data:`HOOK_TEMPLATES`).
- **Variants** (:func:`short_variant`): 9:16, ``shorts``, louder audio, karaoke captions, the
  ``cut`` (scenes and beats), the hook, an end card "Full story on the channel" under the title,
  and a ``zoom ... cut: true, hold: true`` opening every stage scene of the cut framed on its
  speakers (a wide 16:9 place is small in a tall frame; the hook is not shown over a wide view;
  without ``hold`` when a framed character moves later, with a note). A mid-scene start restates
  the light the left-out beats left (their last ``time_of_day`` / ``light``, at once); notes list
  their other moves for the author to restate.
- **Teaser** (:func:`teaser_beats`): about :data:`TEASER_SECONDS` of the best short beats across
  the film (not its ending), in film order, ending on a card with the title.
- **Writing** (:func:`write_suggestions`): the variants go to a separate file (``shorts.yaml``)
  that the config includes (``include:``; an included file may hold ``variants``), so the
  config's text and comments stay as written; the include line is added once (the config is
  backed up first as ``<name>.bak``) and an existing ``shorts.yaml`` is backed up before it is
  replaced.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from vidgen.errors import VidgenError
from vidgen.project import Project, read_config_file

#: Default window lengths (seconds, with the end card).
MIN_SECONDS = 30.0
MAX_SECONDS = 60.0
#: The length a Short scores best at (seconds).
IDEAL_SECONDS = 45.0
#: The share of a window that may overlap an already suggested one.
MAX_OVERLAP = 0.25
#: What a window holding the film's ending loses (unless spoilers are allowed).
SPOILER_PENALTY = 4.0
#: The share of the film's narration at the end that counts as its ending.
ENDING_SHARE = 0.15
#: Longest hook (words).
HOOK_WORDS = 6
#: The teaser's length without its card (seconds) and the longest beat it takes.
TEASER_SECONDS = 15.0
TEASER_BEAT_SECONDS = 6.0
#: The end card's line and lengths.
END_CARD_TEXT = "Full story on the channel"
END_CARD_SECONDS = 3.0
TEASER_CARD_SECONDS = 2.5
#: The file the variants are written to (next to the config) and its variants' names.
SHORTS_FILE = "shorts.yaml"
SHORT_NAME = "short"
TEASER_NAME = "teaser"
#: What a Short variant sets besides its cut.
SHORT_FORMAT: dict[str, Any] = {"width": 1080, "height": 1920}
SHORT_PREVIEW: dict[str, Any] = {"width": 360, "height": 640}
SHORT_AUDIO: dict[str, Any] = {"target_lufs": -14, "bitrate": "256k"}
#: Overlays of the full video kept in a Short (others — captions, chapters, progress — are not).
KEPT_OVERLAYS = ("watermark",)

#: Words that make a line emotional or eventful (lower case; a word starting with one counts).
EMOTION_WORDS: tuple[str, ...] = (
    "afraid", "alarm", "alone", "angry", "attack", "blood", "broke", "burn", "chase", "crash", "cried", "cries", "cry",
    "danger", "dark", "dead", "die", "disappear", "escape", "explod", "fear", "fell", "fall", "fight", "fire", "flood",
    "frighten", "gone", "heart", "help", "hid", "hope", "hurr", "hurt", "kiss", "laugh", "lost", "love", "miss", "never",
    "panic", "please", "promise", "ran", "run", "scared", "scream", "secret", "shak", "shout", "silent", "smash", "sorry",
    "storm", "strange", "sudden", "tear", "terrif", "thunder", "trap", "trembl", "wait", "warn", "whisper", "wrong",
)
_EMOTION = re.compile(r"\b(" + "|".join(EMOTION_WORDS) + r")\w*", re.IGNORECASE)
#: Words a clean start does not open on (they lean on a line before it).
LEANING_WORDS = frozenset({"he", "she", "it", "they", "him", "her", "his", "their", "them", "then", "but", "and", "so", "this", "that", "these", "those", "there"})
#: Words dropped from the front of a hook.
FILLERS = frozenset({"but", "and", "so", "well", "oh", "then", "now", "yes", "no"})
#: Hook templates by the window's words (the first group with a word in the window wins).
HOOK_TEMPLATES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("storm", "thunder", "rain", "wind", "gale"), "Caught in the storm."),
    (("help", "danger", "fire", "alarm", "trap"), "Can they make it in time?"),
    (("lost", "missing", "gone", "vanish", "disappear"), "Something is missing."),
    (("secret", "strange", "signal", "mystery", "clue"), "Nobody expected this."),
    (("night", "midnight", "dark"), "Something happens tonight."),
    (("love", "kiss", "heart"), "Will they say it?"),
)
HOOK_FALLBACK = "Wait for the ending."
#: Action kinds that count as action beats (a beat's own actions, not automatic directing).
MOVE_ACTIONS = frozenset({
    "walk_to", "run_to", "enter", "exit", "jump", "drive_to", "sail_to", "lift_off", "sit_on", "lie_on", "stand_up", "use",
    "time_of_day", "alarm", "wind", "throw", "pick_up", "put_down", "give", "kiss", "hold_hands", "lightning", "explode",
    "get_in", "get_out", "ride_to", "blow_away", "knock", "light", "switch_on", "switch_off",
})
#: Weights of the score's parts (see :func:`score_window`).
WEIGHTS: dict[str, float] = {"dialogue": 6.0, "question": 1.5, "exclaim": 1.0, "emotion": 0.6, "action": 0.75, "variety": 1.0}


# ----- the video's beats, timed -------------------------------------------------------------


@dataclass(frozen=True)
class TimedBeat:
    """A narrated beat as planned: its scene (id, index, type), id, position in its scene
    (``index``, ``first`` / ``last``), ``start`` in the video and ``seconds`` it takes (its
    window: narration and pad), text, ``speaker`` (its voice's name when a named voice speaks it,
    else ``None``: the narrator), whether it carries a shot / an emotion, its own action kinds,
    the beats its actions wait for (``until``), whether it may open a cut (no ``overlap`` /
    ``interrupt``), and the run of narrated scenes it belongs to (``run``)."""

    scene: str
    scene_index: int
    scene_type: str
    id: str
    index: int
    first: bool
    last: bool
    start: float
    seconds: float
    text: str
    speaker: str | None
    shot: bool
    emotion: bool
    actions: tuple[str, ...]
    until: tuple[str, ...]
    can_open: bool
    run: int

    @property
    def end(self) -> float:
        """Where it ends in the video (seconds)."""
        return self.start + self.seconds


def _action_kind(action: Any) -> str:
    return str(getattr(action, "action", "") or "")


def timed_beats(project: Project) -> tuple[list[TimedBeat], dict[str, float]]:
    """Every narrated beat of ``project`` timed by its plan (narration audio when there is some,
    else the word-count estimate), and the fade-out (``outro``) of each scene type in seconds."""
    from vidgen import extensions, registry
    from vidgen.videoplan import VideoPlan, scene_outro

    config = project.config
    voices = project.voice_names()
    with extensions.project_session(project):
        plan = VideoPlan(project, config.format.fps)
        slots = plan.scenes
        outros = {}
        for spec in config.scenes:
            entry = registry.find(spec.type)
            outros[spec.type] = float(getattr(entry.cls, "outro", 0.0)) if entry is not None else 0.0
            outros[spec.id] = scene_outro(spec)   # by scene: a scene's params can change it
        holds = [plan.transition(i + 1).hold / plan.fps if i + 1 < len(slots) else 0.0 for i in range(len(slots))]
    beats: list[TimedBeat] = []
    run = 0
    for i, (spec, slot) in enumerate(zip(config.scenes, slots)):
        if spec.silent or not spec.beats:
            run += 1
            continue
        narrated_end = slot.duration - outros[spec.id] - holds[i]
        for k, (beat, beat_slot) in enumerate(zip(spec.beats, slot.beats)):
            following = slot.beats[k + 1].start if k + 1 < len(slot.beats) else narrated_end
            beats.append(TimedBeat(
                scene=spec.id, scene_index=i, scene_type=spec.type, id=beat.id, index=k, first=k == 0,
                last=k == len(spec.beats) - 1, start=slot.start + beat_slot.start,
                seconds=max(following - beat_slot.start, 0.0), text=beat.text, speaker=voices.get(beat.id),
                shot=beat.shot is not None, emotion=beat.emotion is not None,
                actions=tuple(_action_kind(a) for a in beat.actions),
                until=tuple(str(a.until) for a in beat.actions if a.until),
                can_open=beat.overlap is None and not beat.interrupt, run=run,
            ))
    return beats, outros


def ending_beats(beats: Sequence[TimedBeat]) -> set[str]:
    """The beats that tell the film's ending: those starting in the last :data:`ENDING_SHARE` of
    the narration, and the last beat."""
    if not beats:
        return set()
    first, last = beats[0].start, beats[-1].end
    cut = last - ENDING_SHARE * (last - first)
    return {b.id for b in beats if b.start >= cut} | {beats[-1].id}


# ----- windows and scores -------------------------------------------------------------------


@dataclass
class Window:
    """A run of consecutive beats (``beats``) of the film: its planned length as a Short
    (``seconds``: the beats, each scene's fade-out and the end card), its score and the parts of
    it (``parts``), whether it holds the ending (``spoils``), its hook (``hook`` and where it came
    from: ``hook_source``) and the notes for the author (``notes``)."""

    beats: list[TimedBeat]
    seconds: float
    score: float = 0.0
    parts: dict[str, float] = field(default_factory=dict)
    spoils: bool = False
    hook: str = ""
    hook_source: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def start(self) -> float:
        """Where it starts in the film (seconds)."""
        return self.beats[0].start

    @property
    def end(self) -> float:
        """Where it ends in the film (seconds)."""
        return self.beats[-1].end

    @property
    def scenes(self) -> list[str]:
        """Its scenes' ids, in order."""
        return list(dict.fromkeys(b.scene for b in self.beats))

    def overlap(self, other: Window) -> float:
        """Seconds of the film this window shares with ``other``."""
        return max(0.0, min(self.end, other.end) - max(self.start, other.start))


def cut_seconds(beats: Sequence[TimedBeat], outros: Mapping[str, float], card: float) -> float:
    """The planned length of a cut of ``beats``: the beats, the fade-out of each scene entry and
    the end card (``card`` seconds)."""
    entries: list[tuple[str, int]] = []
    for b in beats:
        if not entries or entries[-1][0] != b.scene:
            entries.append((b.scene, b.scene_index))
    types = {b.scene: b.scene_type for b in beats}
    return sum(b.seconds for b in beats) + sum(outros.get(s, outros.get(types[s], 0.0)) for s, _ in entries) + card


def candidate_windows(beats: Sequence[TimedBeat], outros: Mapping[str, float], min_seconds: float, max_seconds: float,
                      card: float = END_CARD_SECONDS) -> list[Window]:
    """Every run of consecutive beats (in one run of narrated scenes) whose cut lasts
    ``min_seconds`` .. ``max_seconds`` (end card included); not starting on an overlapping beat,
    no action waiting for a beat outside it."""
    out: list[Window] = []
    for i, first in enumerate(beats):
        if not first.can_open:
            continue
        for j in range(i, len(beats)):
            if beats[j].run != first.run:
                break
            chosen = list(beats[i:j + 1])
            seconds = cut_seconds(chosen, outros, card)
            if seconds > max_seconds + 1e-6:
                break
            if seconds < min_seconds - 1e-6:
                continue
            ids = {b.id for b in chosen}
            if any(u not in ids for b in chosen for u in b.until):
                continue
            out.append(Window(chosen, seconds))
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]


def _first_word(text: str) -> str:
    match = re.match(r"\W*(\w+)", text)
    return match.group(1).lower() if match else ""


def strong_line(beat: TimedBeat) -> bool:
    """A last line that lands: spoken by a character and ending on ``!`` / ``?``, or at most
    eight words."""
    text = beat.text.strip()
    return (beat.speaker is not None and text[-1:] in "!?") or len(text.split()) <= 8


def score_window(window: Window, all_beats: Sequence[TimedBeat], ending: set[str], spoilers: bool = False) -> None:
    """Score ``window`` (in place: ``score``, ``parts``, ``spoils``); see the module doc."""
    beats = window.beats
    spoken = sum(b.seconds for b in beats if b.speaker is not None)
    text_of = [b.text for b in beats]
    dialogue = [b.text for b in beats if b.speaker is not None]
    questions = sum(t.count("?") for t in dialogue) + 0.5 * sum(t.count("?") for t in text_of if t not in dialogue)
    exclaims = sum(t.count("!") for t in dialogue) + 0.5 * sum(t.count("!") for t in text_of if t not in dialogue)
    emotion = sum(len(_EMOTION.findall(t)) for t in text_of) + sum(1 for b in beats if b.emotion)
    action = sum(1 for b in beats if any(a in MOVE_ACTIONS for a in b.actions))
    speakers = {b.speaker for b in beats if b.speaker is not None}
    variety = (len(window.scenes) - 1) + 0.75 * len(speakers) + 0.5 * sum(1 for b in beats if b.shot)
    parts = {
        "dialogue": WEIGHTS["dialogue"] * spoken / max(sum(b.seconds for b in beats), 1e-6),
        "question": WEIGHTS["question"] * min(questions, 3),
        "exclaim": WEIGHTS["exclaim"] * min(exclaims, 3),
        "emotion": WEIGHTS["emotion"] * min(emotion, 8),
        "action": WEIGHTS["action"] * min(action, 4),
        "variety": WEIGHTS["variety"] * min(variety, 4),
    }
    first, last = beats[0], beats[-1]
    position = {b.id: k for k, b in enumerate(all_beats)}
    before = all_beats[position[first.id] - 1] if position[first.id] > 0 else None
    start = 1.0 if first.first else 0.0
    if first.speaker is None and _first_word(first.text) in LEANING_WORDS:
        start -= 1.5
    if first.speaker is not None and before is not None and before.scene == first.scene and before.speaker not in (None, first.speaker):
        start -= 1.5   # opens on a reply to a line it leaves out
    parts["start"] = start
    parts["end"] = (2.0 if strong_line(last) else 0.0) + (1.0 if last.last else 0.0)
    parts["length"] = -0.1 * abs(window.seconds - IDEAL_SECONDS)
    window.spoils = any(b.id in ending for b in beats)
    parts["spoiler"] = -SPOILER_PENALTY if window.spoils and not spoilers else 0.0
    window.parts = {k: round(v, 2) for k, v in parts.items()}
    window.score = round(sum(parts.values()), 2)


def pick_windows(windows: Sequence[Window], count: int) -> list[Window]:
    """The best ``count`` windows (by score; then earlier, then longer), each sharing at most
    :data:`MAX_OVERLAP` of its length with a window picked before it."""
    ranked = sorted(windows, key=lambda w: (-w.score, w.start, -w.seconds))
    picked: list[Window] = []
    for window in ranked:
        if len(picked) >= count:
            break
        length = window.end - window.start
        if all(window.overlap(p) <= MAX_OVERLAP * min(length, p.end - p.start) for p in picked):
            picked.append(window)
    return picked


# ----- hooks --------------------------------------------------------------------------------


def shorten(sentence: str, limit: int = HOOK_WORDS) -> str | None:
    """``sentence`` as a hook of at most ``limit`` words: itself, else a clause of it (split at
    commas, semicolons, dashes and colons; a question's last clause first), leading fillers
    (``but``, ``so``, ``oh``...) dropped; ``None`` when no part fits (or has fewer than two words)."""
    end = sentence.rstrip()[-1:] if sentence.rstrip()[-1:] in "?!." else "."
    body = sentence.strip().rstrip("?!.…").strip()
    clauses = [c.strip(" \"'“”") for c in re.split(r"[,;:—–]|\s-\s", body) if c.strip(" \"'“”")]
    options = [body.strip(" \"'“”")] + (list(reversed(clauses)) if end == "?" else clauses)
    for option in options:
        words = option.split()
        while words and words[0].lower().strip(",") in FILLERS and len(words) > 2:
            words = words[1:]
        if 2 <= len(words) <= limit:
            text = " ".join(words)
            return text[0].upper() + text[1:] + end
    return None


def hook_line(window: Window) -> tuple[str, str]:
    """The window's hook and where it came from (``question``, ``exclamation``, ``line``: a
    beat's sentence; ``template``: from the window's words)."""
    choices: list[tuple[float, int, str, str]] = []
    for k, beat in enumerate(window.beats):
        for sentence in _sentences(beat.text):
            hook = shorten(sentence)
            if hook is None:
                continue
            spoken = beat.speaker is not None
            bonus = (1.0 if spoken else 0.0) - (1.5 if k == 0 and len(window.beats) > 1 else 0.0)  # the first line is heard at once anyway
            if sentence.endswith("?"):
                choices.append((3.0 + bonus, k, hook, "question"))
            elif sentence.endswith("!"):
                choices.append((2.0 + bonus, k, hook, "exclamation"))
            elif spoken and len(sentence.split()) <= HOOK_WORDS and _EMOTION.search(sentence):
                choices.append((1.5 + bonus, k, hook, "line"))
    if choices:
        best = max(choices, key=lambda c: (c[0], -c[1]))
        return best[2], best[3]
    words = " ".join(b.text for b in window.beats).lower()
    for keys, template in HOOK_TEMPLATES:
        if any(re.search(rf"\b{key}", words) for key in keys):
            return template, "template"
    return HOOK_FALLBACK, "template"


# ----- variants -----------------------------------------------------------------------------


def _raw_scene(project: Project, scene_id: str) -> dict[str, Any]:
    for scene in project.source_data.get("scenes") or []:
        if isinstance(scene, Mapping) and scene.get("id") == scene_id:
            return dict(scene)
    return {}


def _raw_actions(project: Project, beat: TimedBeat) -> list[Any]:
    beats = _raw_scene(project, beat.scene).get("beats") or []
    raw = beats[beat.index] if beat.index < len(beats) else None
    return list(raw.get("actions") or []) if isinstance(raw, Mapping) else []


def _stage_characters(project: Project, scene_id: str) -> list[str]:
    params = _raw_scene(project, scene_id).get("params")
    entries = params.get("characters") if isinstance(params, Mapping) else None
    names = []
    for entry in entries or []:
        name = entry.get("name") if isinstance(entry, Mapping) else entry
        if isinstance(name, str):
            names.append(name)
    return names


def _framing(project: Project, beats: Sequence[TimedBeat]) -> list[str]:
    """Who a scene entry opens framed on: the characters (on its stage) whose voices speak its
    beats, in order of speaking (at most two); else the stage's first two characters."""
    on_stage = _stage_characters(project, beats[0].scene)
    by_voice = {c.voice: c.name for c in project.config.characters if c.voice}
    speakers = [by_voice[b.speaker] for b in beats if b.speaker in by_voice and by_voice[b.speaker] in on_stage]
    chosen = list(dict.fromkeys(speakers))[:2]
    return chosen or on_stage[:2]


def _action_target(action: Mapping[str, Any]) -> tuple[str, Any]:
    """``(kind, target)`` of a raw action, long form or shorthand (the action's name first)."""
    if "action" in action:
        return str(action["action"]), action.get("target")
    kind = str(next(iter(action), ""))
    return kind, action.get(kind)


def _moved(project: Project, beat: TimedBeat) -> list[str]:
    """The characters ``beat``'s own move actions move."""
    out = []
    for action in _raw_actions(project, beat):
        if isinstance(action, Mapping):
            kind, target = _action_target(action)
            if kind in MOVE_ACTIONS and kind != "time_of_day":
                out.extend([target] if isinstance(target, str) else [t for t in target or [] if isinstance(t, str)])
    return out


#: How long the light a left-out ``time_of_day`` / ``light`` set takes to come back at a cut's
#: start (seconds: at once, the lights switching on by themselves fade in).
RESTATE_SECONDS = 0.1


def _left_out_light(project: Project, scene: str, first_index: int) -> dict[str, Any] | None:
    """The light the beats of ``scene`` before ``first_index`` left (their last ``time_of_day``
    or ``light`` to a preset), as an action restating it at once at a cut's start; ``None``:
    none changed it (DESIGN.md §105.8)."""
    found = None
    for raw in (_raw_scene(project, scene).get("beats") or [])[:first_index]:
        for action in (raw.get("actions") or []) if isinstance(raw, Mapping) else []:
            if isinstance(action, Mapping):
                kind, target = _action_target(action)
                if kind in ("time_of_day", "light") and isinstance(target, str):
                    found = {kind: target, "at": 0, "run_time": RESTATE_SECONDS}
    return found


def _left_out_notes(project: Project, scene: str, first_index: int) -> list[str]:
    """What the beats of ``scene`` before ``first_index`` did that a cut starting there loses (a
    light change is restated: :func:`_left_out_light`)."""
    raw_beats = _raw_scene(project, scene).get("beats") or []
    notes = []
    for raw in raw_beats[:first_index]:
        for action in (raw.get("actions") or []) if isinstance(raw, Mapping) else []:
            if not isinstance(action, Mapping):
                continue
            kind, target = _action_target(action)
            if kind in MOVE_ACTIONS and not (kind in ("time_of_day", "light") and isinstance(target, str)):
                notes.append(f"{kind} {target}" if target is not None else kind)
    if not notes:
        return []
    return [f"{scene} starts mid-scene: left-out beats did {', '.join(notes)}; restate them (params, cut.beats) if the kept beats need them"]


def _entries(project: Project, beats: Sequence[TimedBeat]) -> tuple[list[Any], dict[str, Any], list[str]]:
    """The cut's ``scenes`` entries for ``beats`` (the beats of a scene in one entry: a run as
    ``{from, to}``, others as a list), the ``beats`` changes (an opening zoom) and the notes."""
    groups: list[list[TimedBeat]] = []
    for b in beats:
        if groups and groups[-1][-1].scene == b.scene:
            groups[-1].append(b)
        else:
            groups.append([b])
    entries: list[Any] = []
    changes: dict[str, Any] = {}
    notes: list[str] = []
    for group in groups:
        scene_beats = len(_raw_scene(project, group[0].scene).get("beats") or [])
        whole = group[0].first and len(group) == scene_beats
        run = all(b.index + 1 == c.index for b, c in zip(group, group[1:]))
        if whole:
            entries.append(group[0].scene)
        elif not run:
            entries.append({"scene": group[0].scene, "beats": [b.id for b in group]})
        elif group[-1].last:
            entries.append({"scene": group[0].scene, "beats": {"from": group[0].id}})
        else:
            entries.append({"scene": group[0].scene, "beats": {"from": group[0].id, "to": group[-1].id}})
        opening: list[Any] = []
        if not group[0].first:
            notes.extend(_left_out_notes(project, group[0].scene, group[0].index))
            light = _left_out_light(project, group[0].scene, group[0].index) if group[0].scene_type == "stage" else None
            if light is not None:   # the light the left-out beats left, at once (§105.8)
                opening.append(light)
        targets = _framing(project, group) if group[0].scene_type == "stage" else []
        if targets:
            moving = sorted({t for b in group for t in _moved(project, b) if t in targets})
            zoom: dict[str, Any] = {"zoom": targets if len(targets) > 1 else targets[0], "at": 0, "cut": True}
            if moving:   # a held view would lose them: zoom back out after the first beat
                notes.append(f"{group[0].scene}: opens framed on {', '.join(targets)} for its first beat only (later moving: {', '.join(moving)}); check the framing")
            else:
                zoom["hold"] = True
            opening.append(zoom)
        if opening:
            changes[group[0].id] = {"actions": [*opening, *_raw_actions(project, group[0])]}
    return entries, changes, notes


def _overlays(project: Project) -> list[Any]:
    """The Short's overlays: the full video's kept ones (:data:`KEPT_OVERLAYS`) and karaoke
    captions (in the speakers' colours when the video has named voices)."""
    kept = [dict(o) for o in project.source_data.get("overlays") or [] if isinstance(o, Mapping) and o.get("type") in KEPT_OVERLAYS]
    captions: dict[str, Any] = {"type": "captions", "style": "karaoke"}
    if project.config.voices:
        captions["speakers"] = "color"
    return [*kept, captions]


def short_variant(project: Project, beats: Sequence[TimedBeat], hook: str, max_seconds: float, *, teaser: bool = False,
                  end_text: str = END_CARD_TEXT) -> tuple[dict[str, Any], list[str]]:
    """The variant (a mapping for ``variants:``) of a Short of ``beats`` with ``hook``, and the
    notes for its author (see the module doc). ``teaser``: the end card is a title card."""
    entries, changes, notes = _entries(project, beats)
    shorts: Any = True if max_seconds <= MAX_SECONDS else {"max_seconds": round(max_seconds, 1)}
    end_card: Any = {"text": end_text, "type": "card", "seconds": TEASER_CARD_SECONDS} if teaser else end_text
    cut: dict[str, Any] = {"scenes": entries}
    if changes:
        cut["beats"] = changes
    cut["hook"] = hook
    cut["end_card"] = end_card
    variant = {
        "format": dict(SHORT_FORMAT), "preview": dict(SHORT_PREVIEW), "shorts": shorts, "audio": dict(SHORT_AUDIO),
        "overlays": _overlays(project), "cut": cut,
    }
    return variant, notes


# ----- teaser -------------------------------------------------------------------------------


def beat_score(beat: TimedBeat) -> float:
    """How much a single beat is worth in a teaser: spoken, a question or exclamation, emotional
    words, an emotion, an action; short beats a little more."""
    text = beat.text
    score = (2.0 if beat.speaker is not None else 0.0) + 1.5 * min(text.count("?"), 1) + 1.0 * min(text.count("!"), 2)
    score += 0.5 * min(len(_EMOTION.findall(text)), 3) + (0.5 if beat.emotion else 0.0)
    score += 0.5 if any(a in MOVE_ACTIONS for a in beat.actions) else 0.0
    return score - 0.1 * beat.seconds


def teaser_beats(beats: Sequence[TimedBeat], ending: set[str], spoilers: bool = False, seconds: float = TEASER_SECONDS) -> list[TimedBeat]:
    """The teaser's beats (see the module doc): the best beats of at most
    :data:`TEASER_BEAT_SECONDS`, at most two per scene, about ``seconds`` in all, in film order."""
    pool = [b for b in beats if b.can_open and not b.until and b.seconds <= TEASER_BEAT_SECONDS and (spoilers or b.id not in ending)]
    chosen: list[TimedBeat] = []
    total = 0.0
    per_scene: dict[str, int] = {}
    for beat in sorted(pool, key=lambda b: (-beat_score(b), b.start)):
        if total + beat.seconds > seconds or per_scene.get(beat.scene, 0) >= 2:
            continue
        chosen.append(beat)
        total += beat.seconds
        per_scene[beat.scene] = per_scene.get(beat.scene, 0) + 1
        if total >= seconds - 1.0:
            break
    return sorted(chosen, key=lambda b: b.start)


# ----- the whole suggestion -----------------------------------------------------------------


@dataclass
class Suggestion:
    """A suggested Short (or the teaser): its variant ``name``, the :class:`Window`, the
    ``variant`` mapping and its notes."""

    name: str
    window: Window
    variant: dict[str, Any]
    rank: int = 0
    teaser: bool = False


@dataclass
class Suggestions:
    """What :func:`suggest_shorts` found: the Shorts (best first), the teaser (if asked), how many
    windows were scored, the film's narrated length, the settings."""

    shorts: list[Suggestion]
    teaser: Suggestion | None
    candidates: int
    film_seconds: float
    min_seconds: float
    max_seconds: float
    timed_by: str


def _free_names(own: set[str], count: int, teaser: bool) -> tuple[list[str], str]:
    names, n = [], 1
    while len(names) < count:
        if f"{SHORT_NAME}{n}" not in own:
            names.append(f"{SHORT_NAME}{n}")
        n += 1
    teaser_name = TEASER_NAME
    k = 2
    while teaser and teaser_name in own:
        teaser_name, k = f"{TEASER_NAME}{k}", k + 1
    return names, teaser_name


def own_variant_names(project: Project) -> set[str]:
    """The variants the project's config file itself defines (not those of its include files)."""
    data = read_config_file(project.config_file)
    variants = data.get("variants") if isinstance(data, Mapping) else None
    return set(variants) if isinstance(variants, Mapping) else set()


def suggest_shorts(project: Project, count: int = 3, min_seconds: float = MIN_SECONDS, max_seconds: float = MAX_SECONDS, *,
                   teaser: bool = False, spoilers: bool = False, end_text: str = END_CARD_TEXT) -> Suggestions:
    """Suggest up to ``count`` Shorts of ``project`` (and a teaser) — see the module doc."""
    if count < 1:
        raise VidgenError("--count: give at least 1")
    if not 5 <= min_seconds <= max_seconds:
        raise VidgenError(f"--min {min_seconds:g} / --max {max_seconds:g}: give 5 <= min <= max (seconds, e.g. --min 30 --max 60)")
    if project.config.cut is not None:
        raise VidgenError("the config is itself a cut (cut:); suggest Shorts from the full video's config")
    beats, outros = timed_beats(project)
    if not beats:
        raise VidgenError("the video has no narrated beats to cut Shorts from")
    audio = sum(1 for b in beats if (project.audio_dir / f"{b.id}.mp3").is_file())
    timed_by = "audio" if audio == len(beats) else ("words" if audio == 0 else f"audio for {audio} of {len(beats)} beats, words for the rest")
    ending = ending_beats(beats)
    windows = candidate_windows(beats, outros, min_seconds, max_seconds)
    for window in windows:
        score_window(window, beats, ending, spoilers)
    picked = pick_windows(windows, count)
    names, teaser_name = _free_names(own_variant_names(project), len(picked), teaser)
    shorts = []
    for rank, (window, name) in enumerate(zip(picked, names), start=1):
        window.hook, window.hook_source = hook_line(window)
        variant, notes = short_variant(project, window.beats, window.hook, max_seconds, end_text=end_text)
        window.notes = notes
        shorts.append(Suggestion(name, window, variant, rank))
    teaser_suggestion = None
    if teaser:
        chosen = teaser_beats(beats, ending, spoilers)
        if chosen:
            window = Window(chosen, cut_seconds(chosen, outros, TEASER_CARD_SECONDS))
            score_window(window, beats, ending, spoilers)
            window.hook, window.hook_source = hook_line(window)
            variant, notes = short_variant(project, chosen, window.hook, max_seconds, teaser=True, end_text=end_text)
            window.notes = notes
            teaser_suggestion = Suggestion(teaser_name, window, variant, 0, teaser=True)
    return Suggestions(shorts, teaser_suggestion, len(windows), beats[-1].end - beats[0].start, min_seconds, max_seconds, timed_by)


# ----- report -------------------------------------------------------------------------------


def _clock(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}:{secs:02d}"


#: The score parts shown in the report, with their short column names.
REPORT_PARTS: tuple[tuple[str, str], ...] = (
    ("dialogue", "dlg"), ("question", "?"), ("exclaim", "!"), ("emotion", "emo"), ("action", "act"), ("variety", "var"),
    ("start", "start"), ("end", "end"), ("length", "len"), ("spoiler", "spoil"),
)


def report_rows(suggestions: Suggestions) -> list[list[str]]:
    """The report table's rows (a header first): rank, variant, window (film time and beats),
    length, score and its parts, hook."""
    head = ["rank", "variant", "window", "beats", "secs", "score", *(short for _, short in REPORT_PARTS), "hook"]
    rows = [head]
    items = [*suggestions.shorts, *([suggestions.teaser] if suggestions.teaser else [])]
    for s in items:
        w = s.window
        window = f"{_clock(w.start)}-{_clock(w.end)}" if not s.teaser else "across the film"
        beats = f"{w.beats[0].id} .. {w.beats[-1].id}" if not s.teaser else f"{len(w.beats)} beats"
        parts = [f"{w.parts.get(key, 0.0):g}" for key, _ in REPORT_PARTS]
        rows.append([str(s.rank) if not s.teaser else "-", s.name, window, beats, f"{w.seconds:.1f}", f"{w.score:g}", *parts, f'"{w.hook}" ({w.hook_source})'])
    return rows


def report_text(suggestions: Suggestions) -> str:
    """The report as an aligned text table, then each suggestion's first and last line and notes."""
    rows = report_rows(suggestions)
    widths = [max(len(r[c]) for r in rows) for c in range(len(rows[0]))]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows]
    for s in [*suggestions.shorts, *([suggestions.teaser] if suggestions.teaser else [])]:
        w = s.window
        lines.append(f"{s.name}: opens \"{_clip(w.beats[0].text)}\" ... ends \"{_clip(w.beats[-1].text)}\""
                     + (" [holds the ending]" if w.spoils else ""))
        lines.extend(f"  note: {note}" for note in w.notes)
    return "\n".join(lines)


def _clip(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


# ----- writing ------------------------------------------------------------------------------


def shorts_yaml(suggestions: Suggestions, config_name: str) -> str:
    """The text of :data:`SHORTS_FILE`: a header, then ``variants:`` with each suggestion (a
    comment with its window, score and notes above it)."""
    from vidgen.plan_yaml import _comment, _entry

    out = [
        f"# Written by `vidgen shorts suggest` (no AI: timing, rules and keyword lists); included by {config_name}.",
        "# Each variant is a Short cut from the full video: vidgen storyboard --variant NAME, vidgen lint --variant NAME,",
        "# vidgen render --variant NAME. Running the command with --write again replaces this file (backup: shorts.yaml.bak).",
        "variants:",
    ]
    for s in [*suggestions.shorts, *([suggestions.teaser] if suggestions.teaser else [])]:
        w = s.window
        what = "teaser" if s.teaser else f"rank {s.rank}: film {_clock(w.start)}-{_clock(w.end)}"
        parts = ", ".join(f"{k} {v:g}" for k, v in w.parts.items() if v)
        out.extend(_comment("", f"{what}, about {w.seconds:.0f} s, score {w.score:g} ({parts}); hook: {w.hook_source}"
                            + ("; holds the ending" if w.spoils else ""), 2))
        for note in w.notes:
            out.extend(_comment("TODO:", note, 2))
        out.extend(_entry(f"  {s.name}:", s.variant, 2))
    text = "\n".join(out) + "\n"
    expected = {s.name: s.variant for s in [*suggestions.shorts, *([suggestions.teaser] if suggestions.teaser else [])]}
    if (yaml.safe_load(text) or {}).get("variants") != expected:   # a bug in the writer, never the user's fault
        raise AssertionError("schu-video-generator wrote shorts YAML that does not load back to the variants it meant")
    return text


@dataclass(frozen=True)
class WriteResult:
    """What :func:`write_suggestions` wrote: the shorts file, whether the config was changed (the
    include added), and the backups made."""

    file: Path
    config_changed: bool
    backups: tuple[Path, ...]


def _with_include(text: str, data: Any, name: str) -> str | None:
    """The config's ``text`` with ``name`` added to its top-level ``include:`` (``None``: already
    there). The rest of the text (and its comments) is kept as written."""
    current = data.get("include") if isinstance(data, Mapping) else None
    names = [current] if isinstance(current, str) else list(current or [])
    if name in names:
        return None
    lines = text.splitlines(keepends=True)
    key = re.compile(r"^include\s*:(.*)$")
    for k, line in enumerate(lines):
        match = key.match(line.rstrip("\r\n"))
        if match is None:
            continue
        rest = match.group(1).split(" #")[0].strip()
        if rest:   # include: a.yaml / include: [a.yaml, b.yaml]
            lines[k] = "include: " + json.dumps([*names, name]) + "\n"
        else:      # a block list under it
            indent = "  "
            if k + 1 < len(lines):
                found = re.match(r"^(\s*)-", lines[k + 1])
                indent = found.group(1) if found else indent
            lines.insert(k + 1, f"{indent}- {name}\n")
        return "".join(lines)
    k = 0
    while k < len(lines) and (lines[k].startswith("#") or not lines[k].strip()):
        k += 1   # after the header comments
    lines.insert(k, f"include: [{name}]\n")
    return "".join(lines)


def _loads(text: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def write_suggestions(project: Project, suggestions: Suggestions, file_name: str = SHORTS_FILE) -> WriteResult:
    """Write the suggestions' variants to ``file_name`` next to the config and include it from the
    config (see the module doc)."""
    from vidgen.fileio import write_text_atomic

    if Path(file_name).name != file_name or Path(file_name).suffix.lower() not in (".yaml", ".yml"):
        raise VidgenError(f"--out {file_name}: give a .yaml file name (no folder), e.g. {SHORTS_FILE}")
    config_file = project.config_file
    target = config_file.parent / file_name
    backups: list[Path] = []
    if target.exists():
        backup = target.with_name(target.name + ".bak")
        shutil.copy2(target, backup)
        backups.append(backup)
    write_text_atomic(target, shorts_yaml(suggestions, config_file.name))
    data = read_config_file(config_file)
    current = data.get("include") if isinstance(data, Mapping) else None
    names = [current] if isinstance(current, str) else list(current or [])
    wanted = {"include": [*names, file_name], **{k: v for k, v in data.items() if k != "include"}}
    changed = None if file_name in names else _with_include(config_file.read_text(encoding="utf-8-sig"), data, file_name)
    if changed is not None and (config_file.suffix.lower() == ".json" or _loads(changed) != wanted):
        # JSON, or YAML written in flow style: the whole config written again (the backup keeps the original)
        changed = json.dumps(wanted, indent=2, ensure_ascii=False) + "\n" if config_file.suffix.lower() == ".json" else yaml.safe_dump(wanted, sort_keys=False, allow_unicode=True)
    if changed is not None:
        backup = config_file.with_name(config_file.name + ".bak")
        shutil.copy2(config_file, backup)
        backups.append(backup)
        write_text_atomic(config_file, changed)
    return WriteResult(target, changed is not None, tuple(backups))
