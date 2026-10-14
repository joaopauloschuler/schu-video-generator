"""Words to check in a beat's narration (DESIGN.md §78): the word flags of ``vidgen readback``
and the ``unclear_speech`` lint rule.

:func:`flag_words` reads a beat's transcript (word times and, from faster-whisper, each word's
probability) and its comparison with the text (:func:`vidgen.readback.compare_beat`), with the
thresholds of ``lint.rules.unclear_speech``:

- a word heard with a probability below ``min_probability`` is **unclear**, below
  ``doubtful_probability`` **doubtful**;
- a pause longer than ``max_gap`` before a word inside a sentence is unclear: not after
  punctuation (in the spoken text or the transcript), not where a voice sound sits;
- each difference with the text (an :class:`~vidgen.readback.Edit`) is a flag too, merged with
  the flags of its heard words: unclear when it is about a term (a name, acronym, number or
  pronunciation entry) or covers two or more words, else doubtful (one ordinary word heard
  differently may be the transcriber's slip).

Each :class:`WordFlag` names the beat, the word heard and the written word, when (in the beat's
MP3 and in the video), why, and a suggested fix. No manim import.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from vidgen.readback import EDGE_CHARS, BeatReadback, Edit, entries_by_word, entry_says, hard_term, term_core, written_owner

if TYPE_CHECKING:
    from vidgen.config import UnclearSpeechRule
    from vidgen.project import Project
    from vidgen.pronunciation import Spoken

FlagLevel = Literal["unclear", "doubtful"]

#: A word after which a pause is expected (it ends with punctuation).
_PAUSE_AFTER = re.compile(r"[,.;:!?…—–\-)\]}\"'”’»]$")
#: A word before which a pause is expected (it opens a quote or a parenthesis, or is a dash).
_PAUSE_BEFORE = re.compile(r"^[(\[{\"'“‘«—–\-¿¡]")


@dataclass
class WordFlag:
    """A word (or a difference with the text) to listen to. ``word`` is what was heard ("" for
    words not heard), ``written`` the beat's words concerned ("" for an extra word); ``start`` /
    ``end`` seconds in the beat's MP3 (``None`` without word times), ``video_time`` the start in
    the video (``None`` without a render); ``reasons`` some of ``low_probability``, ``gap``,
    ``mismatch``; ``probability`` the lowest of its words, ``gap`` the pause before it (s)."""

    scene: str
    beat: str
    word: str
    written: str
    level: FlagLevel
    reasons: list[str]
    start: float | None
    end: float | None
    probability: float | None = None
    gap: float | None = None
    detail: str = ""
    suggestion: str = ""
    video_time: float | None = None

    def to_json(self) -> dict[str, Any]:
        """The flag in ``vidgen readback --json``."""
        return {
            "scene": self.scene,
            "beat": self.beat,
            "word": self.word,
            "written": self.written,
            "level": self.level,
            "reasons": list(self.reasons),
            "time": _round(self.start),
            "end": _round(self.end),
            "video_time": _round(self.video_time),
            "probability": None if self.probability is None else round(self.probability, 3),
            "gap": _round(self.gap),
            "detail": self.detail,
            "suggestion": self.suggestion,
        }


def _round(seconds: float | None) -> float | None:
    return None if seconds is None else round(seconds, 3)


@dataclass
class _Unit:
    """Heard words flagged together: one word, or the words of one edit."""

    indices: tuple[int, ...]
    edit: Edit | None = None
    reasons: dict[str, FlagLevel] = field(default_factory=dict)


def flag_words(result: BeatReadback, spoken: Spoken, settings: UnclearSpeechRule, pauses_before: Collection[int] = ()) -> list[WordFlag]:
    """The flags of a compared beat (``result`` from :func:`~vidgen.readback.compare_beat` of
    ``spoken``), in time order. ``pauses_before``: written word indices with a voice sound
    before them (a pause there is expected)."""
    transcript = result.transcript
    if transcript is None:
        return []
    heard = transcript.word_texts()
    times = transcript.word_times()
    probabilities = transcript.word_probabilities()
    written_words = spoken.text.split()
    spoken_words = spoken.spoken.split()
    owner = written_owner(spoken, len(spoken_words))

    units: list[_Unit] = []
    by_edit: dict[int, _Unit] = {}
    edit_of = {i: edit for edit in result.edits for i in edit.heard_indices}
    for i in sorted(result.heard_spoken):
        edit = edit_of.get(i)
        if edit is None:
            units.append(_Unit((i,)))
        elif id(edit) not in by_edit:
            by_edit[id(edit)] = _Unit(edit.heard_indices, edit)
            units.append(by_edit[id(edit)])
    units += [_Unit((), edit) for edit in result.edits if not edit.heard_indices]

    flags: list[WordFlag] = []
    for unit in units:
        known = [probabilities[i] for i in unit.indices if probabilities[i] is not None]
        probability = min(known) if known else None
        if probability is not None and probability < settings.min_probability:
            unit.reasons["low_probability"] = "unclear"
        elif probability is not None and probability < settings.doubtful_probability:
            unit.reasons["low_probability"] = "doubtful"
        gaps = [g for g in (_pause(j, heard, times, result.heard_spoken, spoken_words, owner, pauses_before) for j in unit.indices) if g is not None]
        gap = max(gaps) if gaps else None
        if gap is not None and gap > settings.max_gap:
            unit.reasons["gap"] = "unclear"
        if unit.edit is not None:
            unit.reasons["mismatch"] = "unclear" if unit.edit.term is not None or unit.edit.errors >= 2 else "doubtful"
        if not unit.reasons:
            continue
        flags.append(_flag(result, unit, heard, times, written_words, owner, spoken, probability, gap if "gap" in unit.reasons else None))
    flags.sort(key=lambda f: (f.start is None, f.start or 0.0))
    return flags


def _pause(
    j: int,
    heard: Sequence[str],
    times: Sequence[tuple[float, float] | None],
    heard_spoken: dict[int, int | None],
    spoken_words: Sequence[str],
    owner: Sequence[int],
    pauses_before: Collection[int],
) -> float | None:
    """Seconds of silence before heard word ``j`` when no pause is expected there, else ``None``."""
    if j == 0 or j - 1 not in heard_spoken or j not in heard_spoken:
        return None  # the first word, or next to a voice sound's words
    before, after = times[j - 1], times[j]
    if before is None or after is None:
        return None
    if _PAUSE_AFTER.search(heard[j - 1]) or _PAUSE_BEFORE.search(heard[j]):
        return None
    s_prev, s_next = heard_spoken[j - 1], heard_spoken[j]
    if s_prev is not None:
        last = s_next if s_next is not None and s_next > s_prev else s_prev + 1
        if any(_PAUSE_AFTER.search(spoken_words[s]) for s in range(s_prev, last)):
            return None  # punctuation after the word before (or after words not heard)
    if s_next is not None:
        if _PAUSE_BEFORE.search(spoken_words[s_next]):
            return None
        if owner[s_next] in pauses_before and (s_prev is None or owner[s_prev] != owner[s_next]):
            return None
    return max(after[0] - before[1], 0.0)


def _flag(
    result: BeatReadback,
    unit: _Unit,
    heard: Sequence[str],
    times: Sequence[tuple[float, float] | None],
    written_words: Sequence[str],
    owner: Sequence[int],
    spoken: Spoken,
    probability: float | None,
    gap: float | None,
) -> WordFlag:
    edit = unit.edit
    word = " ".join(heard[i] for i in unit.indices).strip(EDGE_CHARS)
    written_index = _written_index(result, unit, owner)
    if edit is not None:
        written = edit.written
    else:
        written = "" if written_index is None else written_words[written_index].strip(EDGE_CHARS)
    start, end = _span(result, unit, times, owner)
    level: FlagLevel = "unclear" if "unclear" in unit.reasons.values() else "doubtful"
    flag = WordFlag(result.scene, result.beat, word, written, level, list(unit.reasons), start, end, probability, gap)
    parts = []
    if edit is not None:
        parts.append(edit.describe())
    else:
        text = f' (text "{written}")' if written and written.casefold() != word.casefold() else ""
        parts.append(f'"{word}"{text}')
    if probability is not None and "low_probability" in unit.reasons:
        parts.append(f"heard with probability {probability:.2f}")
    if gap is not None:
        parts.append(f"after a {gap:.2f} s pause inside the sentence")
    flag.detail = ", ".join(parts)
    flag.suggestion = _suggestion(result.beat, unit, word, written_words, written_index, spoken)
    return flag


def _written_index(result: BeatReadback, unit: _Unit, owner: Sequence[int]) -> int | None:
    if unit.edit is not None and unit.edit.written:
        return unit.edit.written_index
    for i in unit.indices:
        s = result.heard_spoken.get(i)
        if s is not None:
            return owner[s]
    return None


def _span(result: BeatReadback, unit: _Unit, times: Sequence[tuple[float, float] | None], owner: Sequence[int]) -> tuple[float | None, float | None]:
    """``(start, end)`` of the unit's heard words; for words not heard, the end of the last heard
    word before them (0 at the start)."""
    spans = [times[i] for i in unit.indices if times[i] is not None]
    if spans:
        return spans[0][0], spans[-1][1]
    if unit.edit is None or not any(t is not None for t in times):
        return None, None
    before = [
        times[i][1]  # type: ignore[index]
        for i, s in result.heard_spoken.items()
        if s is not None and owner[s] < unit.edit.written_index and times[i] is not None
    ]
    at = max(before) if before else 0.0
    return at, at


def _suggestion(beat: str, unit: _Unit, word: str, written_words: Sequence[str], written_index: int | None, spoken: Spoken) -> str:
    if unit.edit is not None and unit.edit.suggestion:
        return unit.edit.suggestion.replace("<id>", beat)
    if written_index is not None:
        entry = entries_by_word(spoken).get(written_index)
        if entry is not None:
            return (
                f'the pronunciation entry "{entry}" (says "{entry_says(spoken, entry)}") is not heard clearly: respell its '
                "spoken form (other letters, syllables split by hyphens), then `vidgen tts`"
            )
        if hard_term(written_words, written_index):
            term = term_core(written_words[written_index])
            return f'"{term}" is not heard clearly: add a pronunciation entry `{term}: <how to say it>` (a respelling), then `vidgen tts`'
    if set(unit.reasons) == {"gap"}:
        return (
            f'listen to the pause before "{word}": if the voice hesitates, give the beat another speed or emotion '
            "(the voice's `speed`, `emotion:`) or rephrase the sentence, then `vidgen tts`; if the pause is wanted, write a comma there"
        )
    target = term_core(written_words[written_index]) if written_index is not None else word
    return (
        f'listen to "{target}": if it is slurred, change how the beat is said (another `voice:`, the voice\'s `speed`, an '
        f"`emotion:`) or respell the word in `pronunciation:` (`{target}: <respelling>`), then `vidgen tts`"
    )


# ----- a project's beats ------------------------------------------------------------------------


def beat_flags(project: Project, result: BeatReadback, settings: UnclearSpeechRule) -> list[WordFlag]:
    """:func:`flag_words` of a beat of ``project`` compared by ``vidgen readback`` (its text as
    pronounced; a pause is expected where a voice sound sits)."""
    beat = project.beat(result.beat)
    spoken = project.pronunciation.apply(beat.text)
    return flag_words(result, spoken, settings, {sound.word for sound in beat.voice_sounds})


def beat_video_starts(project: Project) -> dict[str, float]:
    """Each beat's narration start in the video (seconds), from the last render's scene timings
    (the preview's, else the final format's); empty when no format has every scene rendered."""
    from vidgen.render.worker import scene_timings_path
    from vidgen.storyboard import scene_starts

    for preview in (True, False):
        starts = scene_starts(project, preview)
        if any(start is None for start in starts.values()):
            continue
        out: dict[str, float] = {}
        for scene_id, start in starts.items():
            timings = json.loads(scene_timings_path(project, preview, scene_id).read_text(encoding="utf-8"))
            for beat in timings.get("beats", []):
                out[str(beat["id"])] = float(start or 0.0) + float(beat["start"])
        return out
    return {}


def set_video_times(flags: Sequence[WordFlag], beat_starts: dict[str, float]) -> None:
    """Fill each flag's ``video_time`` from its beat's start in the video (when known)."""
    for flag in flags:
        start = beat_starts.get(flag.beat)
        if start is not None and flag.start is not None:
            flag.video_time = start + flag.start
