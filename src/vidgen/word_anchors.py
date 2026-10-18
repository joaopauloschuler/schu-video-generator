"""Actions timed to a spoken word (DESIGN.md §87.2): ``at: "@gradient"``.

A *word anchor* is the text ``@WORDS[#N][+S s | -S s]``: the ``N``-th time (default the first)
the beat says ``WORDS`` (one word or a few in a row, matched without case, accents or the
punctuation around them), moved by ``S`` seconds. :func:`parse_word_anchor` reads it,
:func:`find_words` finds it in a beat's words, :func:`anchor_fraction` turns its word's start
into the fraction of the beat's narration that a numeric ``at`` gives.

Where the word times come from: the beat's MP3 when it has one (the TTS provider's stored
alignment, else an estimate within the MP3's speech, :func:`vidgen.speech.beat_word_times`),
else the estimate from the text over the word-count length (``narration.words_per_second``),
so drafts, storyboards, ``vidgen direct`` and lint work before ``vidgen tts``. The config
resolves anchors with the estimate (:func:`time_beat_anchors`); a loaded project refines them
with its audio (:func:`retime_project_anchors`).

An overlay that starts at a word (``lower_third``'s ``at``) may name the beat first
(``intro_b2@gradient``); without it the anchor is the scene's first beat that says the word.
No manim import.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, NamedTuple

from vidgen.textnorm import fold

if TYPE_CHECKING:
    from vidgen.config import BeatConfig, VideoConfig
    from vidgen.project import Project
    from vidgen.speech import WordTime

#: The largest fraction a word anchor resolves to (a numeric ``at`` is below 1).
MAX_FRACTION = 0.999
#: How many of a beat's words an "unknown word" message lists when none is close.
SHOWN_WORDS = 12
#: JSON-schema pattern of a word anchor as an action's ``at`` (the full check is :func:`parse_word_anchor`).
ACTION_ANCHOR_PATTERN = r"^\s*@"

_EDGE = ".,;:!?\"'()[]{}…“”‘’«»*"
_ANCHOR = re.compile(
    r"^(?P<beat>[A-Za-z0-9_]+)?@(?P<words>(?:[^@#]|#(?!\d))*?)(?:#(?P<occurrence>\d+))?"
    r"(?:\s*(?P<sign>[+-])\s*(?P<seconds>\d+(?:\.\d+)?|\.\d+)\s*s)?\s*$",
    re.S,
)
_EXAMPLES = '"@gradient", "@gradient#2" (its second time), "@gradient+0.3s" or "@learning rate-0.2s"'


class WordAnchor(NamedTuple):
    """A parsed word anchor: the words to find (as written), which time they are said (from 1),
    seconds to move from the first word's start, and the beat it is in (``None``: the action's
    own beat, or for an overlay the scene's first beat that says them)."""

    words: tuple[str, ...]
    occurrence: int = 1
    offset: float = 0.0
    beat: str | None = None

    def describe(self) -> str:
        """``"learning rate"`` (``#2``, ``+0.3 s`` when given), for messages."""
        text = f'"{" ".join(self.words)}"'
        if self.occurrence != 1:
            text += f" #{self.occurrence}"
        if self.offset:
            text += f" {self.offset:+g} s"
        return text


def is_word_anchor(value: object) -> bool:
    """Whether ``value`` is written as a word anchor (a text with ``@``)."""
    return isinstance(value, str) and "@" in value


def parse_word_anchor(text: str, *, beat_allowed: bool = False) -> WordAnchor:
    """``text`` as a :class:`WordAnchor`; ``beat_allowed``: it may start with a beat id
    (``intro_b2@gradient``, for an overlay). Raises ``ValueError`` with an example on bad syntax."""
    match = _ANCHOR.match(text.strip())
    if match is None:
        raise ValueError(f"{text!r}: a word anchor is @WORD, @WORD#N and an optional offset in seconds, e.g. {_EXAMPLES}")
    beat = match.group("beat")
    if beat is not None and not beat_allowed:
        raise ValueError(f"{text!r}: an action's word is in its own beat; write {text.strip()[len(beat):]!r} (or move the action to beat '{beat}')")
    words = tuple(w for w in (_core(w) for w in match.group("words").split()) if w)
    if not words:
        raise ValueError(f"{text!r}: which word? write the word after @, e.g. {_EXAMPLES}")
    occurrence = int(match.group("occurrence") or 1)
    if occurrence < 1:
        raise ValueError(f"{text!r}: #N counts from 1 (#1 is the first time the word is said)")
    seconds = float(match.group("seconds") or 0.0)
    return WordAnchor(words, occurrence, -seconds if match.group("sign") == "-" else seconds, beat)


def _core(word: str) -> str:
    return word.strip(_EDGE)


def _key(word: str) -> str:
    return fold(_core(word))


def _matches(anchor: WordAnchor, words: Sequence[str]) -> list[int]:
    """Indexes of ``words`` where the anchor's words start, in order."""
    want = [_key(w) for w in anchor.words]
    keys = [_key(w) for w in words]
    n = len(want)
    return [i for i in range(len(keys) - n + 1) if keys[i : i + n] == want]


def nearby_words(anchor: WordAnchor, words: Sequence[str]) -> str:
    """``words like it: ...`` (words of ``words`` that look like the anchor's first word), else
    ``its words: ...`` (the first :data:`SHOWN_WORDS` distinct words), for an "unknown word" message."""
    distinct = list(dict.fromkeys(_core(w) for w in words if _core(w)))
    by_key: dict[str, str] = {}
    for word in distinct:
        by_key.setdefault(fold(word), word)
    close = difflib.get_close_matches(_key(anchor.words[0]), list(by_key), n=5, cutoff=0.6)
    if close:
        return "words like it: " + ", ".join(by_key[k] for k in close)
    return "its words: " + (", ".join(distinct[:SHOWN_WORDS]) + (", ..." if len(distinct) > SHOWN_WORDS else "") or "none")


def find_words(anchor: WordAnchor, words: Sequence[str], beat_id: str) -> int:
    """Index in ``words`` (a beat's text split at spaces) of the first word of the anchor's
    ``occurrence``-th match; ``ValueError`` naming the beat and listing nearby words when the
    beat does not say it (that often)."""
    found = _matches(anchor, words)
    said = f'"{" ".join(anchor.words)}"'
    if not found:
        raise ValueError(f"beat '{beat_id}' does not say {said} ({nearby_words(anchor, words)})")
    if anchor.occurrence > len(found):
        times = "once" if len(found) == 1 else f"{len(found)} times"
        raise ValueError(f"beat '{beat_id}' says {said} {times}, so there is no #{anchor.occurrence}")
    return found[anchor.occurrence - 1]


def anchor_fraction(anchor: WordAnchor, index: int, times: Sequence[WordTime], seconds: float) -> float:
    """The fraction of the beat's narration (``seconds`` long; ``times`` its words from its
    start) where the word at ``index`` starts, moved by the anchor's offset, within
    0..:data:`MAX_FRACTION`."""
    if seconds <= 0 or index >= len(times):
        return 0.0
    return min(max((times[index].start + anchor.offset) / seconds, 0.0), MAX_FRACTION)


def estimated_times(text: str, seconds: float, language: str | None = None) -> list[WordTime]:
    """The words of ``text`` spread over ``seconds`` by their syllables (no audio yet)."""
    from vidgen.speech import estimate_word_times

    return estimate_word_times(text.split(), 0.0, seconds, language)


def time_beat_anchors(beat: BeatConfig, times: Sequence[WordTime] | None, seconds: float) -> None:
    """Set ``at`` of the beat's word-anchored actions to their fraction, from its word
    ``times`` over ``seconds`` (``None``: estimated from the text over ``seconds``). The
    anchor stays in :attr:`~vidgen.config.ActionConfig.anchor`. ``ValueError`` when the beat
    does not say a word."""
    anchored = [act for act in beat.actions if act.anchor is not None]
    if not anchored:
        return
    words = beat.text.split()
    if times is None or len(times) != len(words):
        times = estimated_times(beat.text, seconds)
    for k, act in enumerate(anchored):
        anchor = parse_word_anchor(act.anchor or "")
        try:
            index = find_words(anchor, words, beat.id)
        except ValueError as exc:
            raise ValueError(f"actions: {act.describe()} at {act.anchor!r}: {exc}") from None
        act.set_fraction(anchor_fraction(anchor, index, times, seconds))


def time_config_anchors(config: VideoConfig) -> None:
    """Resolve every word anchor of ``config`` with the estimate in its language and
    ``narration.words_per_second`` (:func:`time_beat_anchors`)."""
    wps, language = config.narration.words_per_second, config.language
    for scene in config.scenes:
        for beat in scene.beats:
            if any(act.anchor is not None for act in beat.actions):
                seconds = beat.estimated_duration(wps)
                time_beat_anchors(beat, estimated_times(beat.text, seconds, language), seconds)


def beat_words(project: Project, beat: BeatConfig, seconds: float | None = None) -> tuple[float, list[WordTime]]:
    """A beat's narration length (``seconds``, else its MP3's, else the word-count estimate)
    and its word times from its start: the stored alignment, else estimated within the MP3's
    speech or over the length (:func:`vidgen.speech.beat_word_times`, with the beat's spoken
    form: pronunciation, voice sounds)."""
    from vidgen.speech import audio_duration, beat_word_times

    if seconds is None:
        mp3 = project.audio_dir / f"{beat.id}.mp3"
        seconds = audio_duration(mp3) if mp3.is_file() else beat.estimated_duration(project.config.narration.words_per_second)
    spoken = project.spoken(beat)
    return seconds, beat_word_times(project.audio_dir, beat.id, beat.text, 0.0, seconds, spoken, project.config.language)


def retime_project_anchors(project: Project) -> None:
    """Re-resolve the word anchors of the project's beats that have an MP3 from that audio's
    word times (the config resolved them from the text alone)."""
    for _, beat in project.beats():
        if any(act.anchor is not None for act in beat.actions) and (project.audio_dir / f"{beat.id}.mp3").is_file():
            seconds, times = beat_words(project, beat)
            time_beat_anchors(beat, times, seconds)


def locate_word_anchor(project: Project, scene_id: str, anchor: WordAnchor, beats: Sequence[tuple[str, float | None]]) -> tuple[str, float]:
    """Where a word anchor (an overlay's ``at``, say) is in a scene: ``(beat id, seconds from
    that beat's start)``. ``beats`` are the scene's beats with their narration seconds (``None``: the MP3's,
    else the estimate); the anchor's beat,
    else the first that says the words (``#N`` counts over the scene). ``ValueError`` when no beat says them."""
    seen = 0
    pool = [b for b in beats if anchor.beat is None or b[0] == anchor.beat]
    if not pool:
        raise ValueError(f"at: scene '{scene_id}' has no beat '{anchor.beat}' (beats: {', '.join(b for b, _ in beats) or 'none'})")
    for beat_id, seconds in pool:
        beat = project.beat(beat_id)
        found = _matches(anchor, beat.text.split())
        if seen + len(found) >= anchor.occurrence:
            index = found[anchor.occurrence - seen - 1]
            seconds, times = beat_words(project, beat, seconds)
            start = times[index].start if index < len(times) else 0.0
            return beat_id, min(max(start + anchor.offset, 0.0), seconds)
        seen += len(found)
    words = [w for beat_id, _ in pool for w in project.beat(beat_id).text.split()]
    where = f"beat '{anchor.beat}'" if anchor.beat else f"scene '{scene_id}'"
    said = f'"{" ".join(anchor.words)}"'
    if seen:
        raise ValueError(f"at: {where} says {said} {'once' if seen == 1 else f'{seen} times'}, so there is no #{anchor.occurrence}")
    raise ValueError(f"at: {where} does not say {said} ({nearby_words(anchor, words)})")


def pin_translated_anchors(translated: dict[str, Any], source: dict[str, Any], config: VideoConfig) -> None:
    """In the raw ``translated`` config (``translations:`` applied to ``source``), replace each
    word anchor of a beat whose text was translated by the fraction it has in the source
    ``config`` (the translated text says other words; the moment stays where it was)."""
    pairs = zip(_list(translated.get("scenes")), _list(source.get("scenes")), config.scenes)
    for raw_scene, src_scene, scene in pairs:
        for raw_beat, src_beat, beat in zip(_list(_get(raw_scene, "beats")), _list(_get(src_scene, "beats")), scene.beats):
            if not isinstance(raw_beat, dict) or _get(raw_beat, "text") == _get(src_beat, "text"):
                continue
            for raw_action, action in zip(_list(raw_beat.get("actions")), beat.actions):
                if isinstance(raw_action, dict) and is_word_anchor(raw_action.get("at")):
                    raw_action["at"] = round(action.fraction, 4)


def _get(node: Any, key: str) -> Any:
    return node.get(key) if isinstance(node, dict) else None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
