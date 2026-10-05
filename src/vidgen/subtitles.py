"""SRT subtitles from beat timings (DESIGN.md §5.2).

Each beat becomes one or more cues. Long beat texts are wrapped into lines of at most
``width`` characters and grouped into cues of at most ``max_lines`` lines; the beat's time is
shared between its cues in proportion to their number of characters. Cue ends are beat ends
(the narration), not including the silence pad after a beat.
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

LINE_WIDTH = 42
MAX_LINES = 2


class Cue(NamedTuple):
    """One subtitle: absolute start/end in seconds and its text (lines joined by ``\\n``)."""

    start: float
    end: float
    text: str


def split_text(text: str, width: int = LINE_WIDTH, max_lines: int = MAX_LINES) -> list[str]:
    """Split ``text`` into cue texts of at most ``max_lines`` lines of ``width`` characters."""
    lines = textwrap.wrap(" ".join(text.split()), width=width, break_on_hyphens=False)
    return ["\n".join(lines[i : i + max_lines]) for i in range(0, len(lines), max_lines)]


def beat_cues(start: float, end: float, text: str, width: int = LINE_WIDTH, max_lines: int = MAX_LINES) -> list[Cue]:
    """Cues for one beat spanning ``start``..``end``, time shared in proportion to characters."""
    parts = split_text(text, width, max_lines)
    total = sum(len(p) for p in parts)
    cues = []
    done = 0
    for part in parts:
        cue_start = start + (end - start) * done / total
        done += len(part)
        cues.append(Cue(cue_start, start + (end - start) * done / total, part))
    return cues


def cues_from_timings(timings: dict) -> list[Cue]:
    """All cues of a combined ``timings.json`` mapping (beat times are absolute)."""
    cues: list[Cue] = []
    for scene in timings["scenes"]:
        for beat in scene["beats"]:
            cues.extend(beat_cues(beat["start"], beat["end"], beat["text"]))
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


def write_srt(path: Path, timings: dict) -> list[Cue]:
    """Write the SRT for a combined timings mapping as UTF-8; returns the cues."""
    cues = cues_from_timings(timings)
    path.write_text(format_srt(cues), encoding="utf-8")
    return cues
