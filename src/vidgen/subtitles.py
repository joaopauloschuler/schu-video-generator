"""SRT subtitles from beat timings (DESIGN.md §5.2, §43).

Each beat becomes one or more cues, cut at natural phrase boundaries into at most ``max_lines``
lines of ``width`` characters by :func:`vidgen.cues.segment_cues` — the same cutting the burned-in
``captions`` overlay uses, so both show the same pieces. A cue starts when its first word is
spoken (the beat's first cue at the beat's start) and lasts until the next one; word times come
from :func:`vidgen.speech.beat_word_times` (the TTS alignment, else an estimate within the
MP3's speech, else over the beat). Cue ends are beat ends (the narration), not including the
silence pad after a beat.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import NamedTuple

from vidgen.cues import caption_cues, split_cues
from vidgen.fileio import write_text_atomic
from vidgen.pronunciation import Pronunciation
from vidgen.speech import WordTime, beat_word_times
from vidgen.voices import speaker_prefix

LINE_WIDTH = 42
MAX_LINES = 2


class Cue(NamedTuple):
    """One subtitle: absolute start/end in seconds and its text (lines joined by ``\\n``)."""

    start: float
    end: float
    text: str


def split_text(text: str, width: int = LINE_WIDTH, max_lines: int = MAX_LINES) -> list[str]:
    """Split ``text`` into cue texts of at most ``max_lines`` lines of ``width`` characters."""
    return ["\n".join(lines) for lines in split_cues(text, width, max_lines)]


def beat_cues(
    start: float,
    end: float,
    text: str,
    width: int = LINE_WIDTH,
    max_lines: int = MAX_LINES,
    words: list[WordTime] | None = None,
    speaker: str | None = None,
) -> list[Cue]:
    """Cues for one beat spanning ``start``..``end``, timed by its ``words`` (default: estimated
    over the beat); with ``speaker`` the first cue starts with ``"<speaker>:"``."""
    prefix = speaker_prefix(speaker) if speaker else ""
    cues = caption_cues(text, start, end, words=words, max_width=float(width), max_lines=max_lines, prefix=prefix)
    return [Cue(c.start, c.end, c.text) for c in cues]


def cues_from_timings(
    timings: dict,
    audio_dir: Path | None = None,
    pronunciation: Pronunciation | None = None,
    speakers: Mapping[str, str] | None = None,
) -> list[Cue]:
    """All cues of a combined ``timings.json`` mapping (beat times are absolute); with
    ``audio_dir``, word times come from the beats' MP3s and alignments there. The cues show the
    written text; with ``pronunciation`` (the project's) the words are timed by their spoken
    form, which is what the MP3s say. ``speakers`` (beat id -> label, see
    :meth:`vidgen.project.Project.speaker_tags`) names the speaker before those beats."""
    cues: list[Cue] = []
    speakers = speakers or {}
    for scene in timings["scenes"]:
        for beat in scene["beats"]:
            words = None
            if audio_dir is not None:
                spoken = pronunciation.apply(beat["text"]) if pronunciation is not None else None
                words = beat_word_times(audio_dir, beat["id"], beat["text"], beat["start"], beat["end"], spoken)
            cues.extend(beat_cues(beat["start"], beat["end"], beat["text"], words=words, speaker=speakers.get(beat["id"])))
    return cues


def format_time(seconds: float) -> str:
    """SRT timestamp ``HH:MM:SS,mmm``."""
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def format_srt(cues: Iterable[Cue]) -> str:
    """SRT document text: numbered from 1, blank line between cues."""
    blocks = [
        f"{i}\n{format_time(cue.start)} --> {format_time(cue.end)}\n{cue.text}\n"
        for i, cue in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)


def write_srt(
    path: Path,
    timings: dict,
    audio_dir: Path | None = None,
    pronunciation: Pronunciation | None = None,
    speakers: Mapping[str, str] | None = None,
) -> list[Cue]:
    """Write the SRT for a combined timings mapping as UTF-8 (word times from ``audio_dir`` and
    ``pronunciation``, speaker names ``speakers``, see :func:`cues_from_timings`); returns the cues."""
    cues = cues_from_timings(timings, audio_dir, pronunciation, speakers)
    write_text_atomic(path, format_srt(cues))
    return cues
