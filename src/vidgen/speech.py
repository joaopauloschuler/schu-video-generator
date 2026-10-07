"""Speech timing: where the words of a beat are spoken (DESIGN.md §17, §43).

- :func:`spoken_words` counts the words a narrator says for a text (numbers and acronyms take
  longer), :func:`speech_bounds` finds the speech in an MP3 (leading / trailing silence cut off);
  both are used by ``vidgen lint``'s ``narration_speed``.
- :func:`estimate_word_times` spreads a text's words over a stretch of time by their syllables,
  with pauses at punctuation; :func:`beat_word_times` gives a beat's word times from what is
  known best: the TTS provider's character timings (an *alignment* stored next to the MP3), else
  the estimate within the MP3's speech, else the estimate over the beat. Burned-in captions
  (``captions`` overlay) and the SRT read them.
- An alignment is stored as ``<audio_dir>/<beat_id>.align.json`` (:func:`write_alignment`) with
  the text and a hash of the MP3 it belongs to, so a stale one is never used.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import av
import numpy as np

from vidgen.errors import VidgenError
from vidgen.fileio import remove_file, write_text_atomic

if TYPE_CHECKING:
    from vidgen.pronunciation import Spoken

# ----- spoken words -----------------------------------------------------------------------------

_TOKEN = re.compile(r"[^\s\-–—/]+")  # hyphens, dashes and slashes separate words ("one-by-one": 3)
_EDGE = ".,;:!?\"'()[]{}…“”‘’«»"
_ACRONYM = re.compile(r"[A-Z]{2,5}s?")
_SYMBOLS = re.compile(r"[%$€£+=×&#@]")


def spoken_words(text: str) -> float:
    """How many words a narrator says for ``text`` (an estimate for counting speech rate).

    Words split at spaces, hyphens, dashes and slashes (``K-Phi-3`` is 3, ``one-by-one`` 3). In
    a token with digits every digit run counts as ``min(len, 3)`` words ("227": "two hundred
    twenty-seven"), a decimal or thousands separator before a digit as one ("point"), symbols
    ``% $ € £ + = × & # @`` as one each, and letters next to the digits as one more. An
    all-capitals acronym of 2-5 letters (``GPU``, ``NVIDIA`` is a word) counts half a word per
    letter, at least one. Everything else is one word.
    """
    total = 0.0
    for token in _TOKEN.findall(text):
        core = token.strip(_EDGE)
        if not core:
            continue
        if any(ch.isdigit() for ch in core):
            total += sum(min(len(run), 3) for run in re.findall(r"\d+", core))
            total += len(re.findall(r"[.,]\d", core))
            total += len(_SYMBOLS.findall(core))
            total += 1 if any(ch.isalpha() for ch in core) else 0
        elif _ACRONYM.fullmatch(core):
            total += max(1.0, len(core.rstrip("s")) / 2)
        elif any(ch.isalnum() for ch in core):
            total += 1
        else:
            total += len(_SYMBOLS.findall(core))
    return total


# ----- speech in an audio file ------------------------------------------------------------------

#: Speech starts/ends where the 10 ms envelope first/last exceeds this level below the peak.
SILENCE_DB = -40.0


@lru_cache(maxsize=256)
def _speech_bounds(path: Path, mtime_ns: int) -> tuple[float, float]:
    try:
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            rate = stream.rate or 0
            chunks: list[np.ndarray] = []
            for frame in container.decode(stream):
                samples = frame.to_ndarray()
                if not frame.format.is_planar:
                    samples = samples.reshape(-1, len(frame.layout.channels)).T
                chunks.append(np.abs(samples.astype(np.float32)).max(axis=0))
                rate = frame.sample_rate or rate
    except (OSError, ValueError, IndexError, av.error.FFmpegError) as exc:
        raise VidgenError(f"cannot read audio file {path}: {exc}") from None
    if not chunks or not rate:
        raise VidgenError(f"cannot read audio file {path}: no audio samples")
    level = np.concatenate(chunks)
    window = max(1, int(rate * 0.01))
    count = len(level) // window
    if count == 0:
        return 0.0, len(level) / rate
    envelope = level[: count * window].reshape(count, window).max(axis=1)
    loud = np.nonzero(envelope > envelope.max() * 10 ** (SILENCE_DB / 20))[0]
    if loud.size == 0:
        return 0.0, len(level) / rate
    return float(loud[0] * window / rate), float((loud[-1] + 1) * window / rate)


def speech_bounds(path: Path) -> tuple[float, float]:
    """Start and end (seconds) of the speech in an audio file: the leading and trailing
    silence (below :data:`SILENCE_DB` relative to its loudest 10 ms) cut off."""
    return _speech_bounds(path, path.stat().st_mtime_ns)


# ----- estimated word times ---------------------------------------------------------------------


class WordTime(NamedTuple):
    """A word of a text (as written, punctuation included) and when it is spoken: ``start`` /
    ``end`` in seconds (on the caller's clock: a scene's or the video's)."""

    text: str
    start: float
    end: float


_VOWELS = re.compile(r"[aeiouyàáâãäåæèéêëìíîïòóôõöøœùúûüý]+")
#: Pauses after a word, in syllables: a sentence end, a clause mark or dash.
SENTENCE_PAUSE = 2.0
CLAUSE_PAUSE = 1.0
_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*$")
_CLAUSE_END = re.compile(r"[,;:][\"'”’)\]]*$|[-–—]$")


def syllables(word: str) -> float:
    """About how many syllables a narrator says for ``word``: vowel groups of a word (a silent
    final ``e`` dropped, at least one), one per letter of an all-capitals acronym, two per
    spoken word of a number (``77%``: "seventy-seven percent")."""
    core = word.strip(_EDGE)
    if not core:
        return 0.0
    if any(ch.isdigit() for ch in core):
        return 2.0 * max(spoken_words(core), 1.0)
    if _ACRONYM.fullmatch(core):
        return float(len(core.rstrip("s")))
    total = 0.0
    for part in re.split(r"[-–—/]+", core.lower()):
        groups = len(_VOWELS.findall(part))
        if groups > 1 and part.endswith("e") and not part.endswith(("le", "ee", "ye")):
            groups -= 1
        total += max(groups, 1) if any(ch.isalpha() for ch in part) else len(_SYMBOLS.findall(part))
    return max(total, 1.0)


def pause_after(word: str) -> float:
    """The pause a narrator makes after ``word``, in syllables (:data:`SENTENCE_PAUSE` after a
    sentence end, :data:`CLAUSE_PAUSE` after a comma, semicolon, colon or dash, else 0)."""
    if _SENTENCE_END.search(word):
        return SENTENCE_PAUSE
    if _CLAUSE_END.search(word):
        return CLAUSE_PAUSE
    return 0.0


def estimate_word_times(words: Sequence[str], start: float, end: float) -> list[WordTime]:
    """``words`` spread over ``start``..``end`` (the speech): each takes time in proportion to
    its :func:`syllables` (plus a little per letter), with :func:`pause_after` its punctuation
    between it and the next word. The first word starts at ``start``, the last ends at ``end``."""
    if not words:
        return []
    weights = [syllables(w) + 0.05 * len(w) for w in words]
    pauses = [pause_after(w) for w in words[:-1]] + [0.0]
    total = sum(weights) + sum(pauses)
    scale = (end - start) / total if total > 0 else 0.0
    out = []
    t = start
    for word, weight, pause in zip(words, weights, pauses):
        out.append(WordTime(word, t, t + weight * scale))
        t += (weight + pause) * scale
    return out


# ----- alignments from the TTS provider ---------------------------------------------------------

#: Version of the alignment file format.
ALIGNMENT_VERSION = 1


def alignment_path(audio_dir: Path, beat_id: str) -> Path:
    """``<audio_dir>/<beat_id>.align.json``: the character timings of a beat's MP3."""
    return audio_dir / f"{beat_id}.align.json"


def _audio_digest(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def write_alignment(audio_dir: Path, beat_id: str, text: str, audio: bytes, alignment: Mapping[str, Any] | None) -> Path | None:
    """Store a provider's character timings for the MP3 ``audio`` of ``text`` (ElevenLabs'
    ``{characters, character_start_times_seconds, character_end_times_seconds}``); ``None``
    removes a stored one (the audio has no timings). Returns the file written, if any."""
    path = alignment_path(audio_dir, beat_id)
    if alignment is None:
        remove_file(path)
        return None
    doc = {
        "version": ALIGNMENT_VERSION,
        "text": text,
        "audio_sha1": _audio_digest(audio),
        "characters": list(alignment["characters"]),
        "starts": [float(t) for t in alignment["character_start_times_seconds"]],
        "ends": [float(t) for t in alignment["character_end_times_seconds"]],
    }
    write_text_atomic(path, json.dumps(doc, ensure_ascii=False))
    return path


@lru_cache(maxsize=512)
def _read_alignment(path: Path, mtime_ns: int, mp3: Path, mp3_mtime_ns: int) -> dict[str, Any] | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        digest = _audio_digest(mp3.read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("version") != ALIGNMENT_VERSION or doc.get("audio_sha1") != digest:
        return None
    chars, starts, ends = doc.get("characters"), doc.get("starts"), doc.get("ends")
    if not (isinstance(chars, list) and isinstance(starts, list) and isinstance(ends, list) and len(chars) == len(starts) == len(ends)):
        return None
    return doc


def read_alignment(audio_dir: Path, beat_id: str, text: str) -> dict[str, Any] | None:
    """The stored alignment of a beat when it belongs to its current MP3 and ``text``, else
    ``None``: ``{text, audio_sha1, characters, starts, ends}``."""
    path, mp3 = alignment_path(audio_dir, beat_id), audio_dir / f"{beat_id}.mp3"
    try:
        stamp, mp3_stamp = path.stat().st_mtime_ns, mp3.stat().st_mtime_ns
    except OSError:
        return None
    doc = _read_alignment(path, stamp, mp3, mp3_stamp)
    return doc if doc is not None and doc.get("text") == text else None


def aligned_word_times(text: str, alignment: Mapping[str, Any], offset: float = 0.0) -> list[WordTime] | None:
    """The words of ``text`` timed by an alignment (``characters`` / ``starts`` / ``ends``, as
    :func:`read_alignment` gives it), shifted by ``offset``; ``None`` when its characters are
    not the text's."""
    chars = "".join(alignment["characters"])
    if chars != text:
        if chars != " ".join(text.split()):
            return None
        text = chars
    starts, ends = alignment["starts"], alignment["ends"]
    out = []
    for match in re.finditer(r"\S+", text):
        a, b = match.start(), match.end() - 1
        out.append(WordTime(match.group(), offset + float(starts[a]), offset + max(float(ends[b]), float(starts[a]))))
    return out


def map_word_times(spoken: Spoken, times: Sequence[WordTime]) -> list[WordTime]:
    """The written words of ``spoken.text`` timed by ``times``, the times of the words of
    ``spoken.spoken`` (what the TTS said): a written word lasts from its first spoken word's
    start to its last one's end (``K-Phi-3`` said "kay fye three": three spoken words, one
    written word); a word said as nothing gets a zero-length time where the next word starts
    (the previous one's end at the end)."""
    groups = spoken.word_groups()
    out: list[WordTime] = []
    words = spoken.text.split()
    for k, (word, group) in enumerate(zip(words, groups)):
        group = [i for i in group if i < len(times)]
        if group:
            out.append(WordTime(word, times[group[0]].start, max(times[group[-1]].end, times[group[0]].start)))
            continue
        later = next((g for g in groups[k + 1 :] if g and g[0] < len(times)), None)
        at = times[later[0]].start if later else (out[-1].end if out else (times[0].start if times else 0.0))
        out.append(WordTime(word, at, at))
    return out


def beat_word_times(
    audio_dir: Path | None, beat_id: str, text: str, start: float, end: float, spoken: Spoken | None = None
) -> list[WordTime]:
    """When each word of a beat is spoken, ``start``..``end`` being the beat's narration (its
    MP3's length or the estimate): from the stored alignment of its MP3 when there is one, else
    estimated (:func:`estimate_word_times`) within the MP3's speech (silence cut off,
    :func:`speech_bounds`), else over the whole beat.

    ``spoken`` (the beat's text with the project's pronunciation applied,
    :meth:`vidgen.pronunciation.Pronunciation.apply`): when it differs from ``text``, the
    spoken words are timed (the alignment and the audio are of the spoken text; an estimate
    weighs the spoken syllables) and the written words take their times
    (:func:`map_word_times`)."""
    if spoken is not None and spoken.changed and spoken.text == text:
        times = beat_word_times(audio_dir, beat_id, spoken.spoken, start, end)
        return map_word_times(spoken, times)
    words = text.split()
    mp3 = audio_dir / f"{beat_id}.mp3" if audio_dir is not None else None
    if mp3 is None or not mp3.is_file():
        return estimate_word_times(words, start, end)
    alignment = read_alignment(mp3.parent, beat_id, text)
    if alignment is not None:
        timed = aligned_word_times(text, alignment, start)
        if timed is not None and len(timed) == len(words):
            return timed
    try:
        s0, s1 = speech_bounds(mp3)
    except VidgenError:
        return estimate_word_times(words, start, end)
    lo, hi = min(start + s0, end), min(start + s1, end)
    return estimate_word_times(words, lo, hi) if hi > lo else estimate_word_times(words, start, end)
