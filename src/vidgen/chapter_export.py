"""Chapters as the render publishes them (DESIGN.md §52): MP4 chapter entries and tags, the
YouTube chapter list ``<output>_chapters.txt`` and its rules.

Published lists start at 0:00 (YouTube requires it, and a player's chapter menu should cover the
whole video): when the first chapter starts later, an intro chapter titled ``chapters.intro``
("Intro") is added before it, or with ``intro: false`` the first chapter is moved to 0:00. The
overlays (progress bar, chapter indicator) keep the plain list, which has nothing before the
first chapter.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from vidgen.chapters import chapter_marks
from vidgen.config import VideoConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videoplan import Chapter, video_chapters

#: YouTube shows a description's chapter list only with at least this many chapters...
YOUTUBE_MIN_CHAPTERS = 3
#: ... each lasting at least this many seconds, the first at 0:00, in ascending order.
YOUTUBE_MIN_SECONDS = 10
#: A first chapter starting less than this after 0 (seconds) counts as starting at 0:00.
AT_START = 1e-3
#: FFMETADATA chapter time base (milliseconds).
TIMEBASE = 1000


def clean_title(title: str) -> str:
    """``title`` on one line: runs of whitespace (a card title's ``\\n``) become one space."""
    return " ".join(title.split())


def published_chapters(config: VideoConfig, chapters: Sequence[Chapter]) -> tuple[Chapter, ...]:
    """``chapters`` (in order, from the plan or the joined video) as published: starting at 0:00
    (an intro chapter before a later first chapter, or that chapter moved to 0:00 with
    ``chapters.intro: false``), ``index`` / ``count`` their positions in this list."""
    if not chapters:
        return ()
    out = list(chapters)
    first = out[0]
    intro = config.chapters.intro
    if first.start > AT_START and intro is not False:
        out.insert(0, Chapter(intro, None, config.scenes[0].id, 0.0, first.start, 0, 0, False, intro=True))
    elif first.start != 0.0:
        out[0] = dataclasses.replace(first, start=0.0)
    return tuple(dataclasses.replace(c, index=k, count=len(out)) for k, c in enumerate(out, start=1))


def joined_chapters(config: VideoConfig, scenes: Sequence[Mapping[str, Any]], duration: float) -> tuple[Chapter, ...]:
    """The published chapters of a joined video: each chapter starts where its scene starts in
    ``scenes`` (the combined timings' entries, ``{id, start, ...}``: with transitions' overlaps;
    equal to the plan for scenes that keep to it), the last ends at ``duration``."""
    marks = chapter_marks(config.scenes)
    starts = {scene["id"]: float(scene["start"]) for scene in scenes}
    begins = [starts[mark.scene] for mark in marks]
    ends = [*begins[1:], duration]
    chapters = [
        Chapter(mark.title, mark.number, mark.scene, start, end, k, len(marks), mark.card)
        for k, (mark, start, end) in enumerate(zip(marks, begins, ends), start=1)
    ]
    return published_chapters(config, chapters)


def chapter_json(chapter: Chapter) -> dict[str, Any]:
    """A chapter as JSON (``timings.json``, ``render --json``): its fields, times rounded to 1 µs."""
    data = dataclasses.asdict(chapter)
    data["start"] = round(chapter.start, 6)
    data["end"] = round(chapter.end, 6)
    return data


def chapter_from_json(data: Mapping[str, Any]) -> Chapter:
    """The inverse of :func:`chapter_json`."""
    return Chapter(**data)


# ----- MP4 metadata ------------------------------------------------------------------------------


def video_tags(config: VideoConfig) -> dict[str, str]:
    """The MP4's tags: ``metadata.title`` (default the video's ``title``) and every other
    ``metadata`` key that is set."""
    tags = config.metadata.model_dump(exclude_none=True)
    title = tags.pop("title", None) or config.title
    return {"title": title, **tags}


def _escape(value: str) -> str:
    """``value`` for an FFMETADATA file: ``\\``, ``=``, ``;``, ``#`` and newlines escaped."""
    for char in ("\\", "=", ";", "#", "\n"):
        value = value.replace(char, "\\" + char)
    return value


def ffmetadata(tags: Mapping[str, str], chapters: Sequence[Chapter]) -> str:
    """An FFMETADATA file with the global ``tags`` and one ``[CHAPTER]`` per chapter (time base
    1/1000, ``START`` / ``END`` rounded to the millisecond, the title on one line)."""
    lines = [";FFMETADATA1", *(f"{key}={_escape(value)}" for key, value in tags.items())]
    for chapter in chapters:
        start = round(chapter.start * TIMEBASE)
        end = max(round(chapter.end * TIMEBASE), start + 1)
        lines += [
            "[CHAPTER]",
            f"TIMEBASE=1/{TIMEBASE}",
            f"START={start}",
            f"END={end}",
            f"title={_escape(clean_title(chapter.title))}",
        ]
    return "\n".join(lines) + "\n"


# ----- YouTube -----------------------------------------------------------------------------------


def youtube_seconds(seconds: float) -> int:
    """A time as a YouTube timestamp counts it: whole seconds, rounded down (a click lands at or
    just before the chapter's first frame, never after it)."""
    return max(0, math.floor(seconds + 1e-6))


def youtube_time(seconds: float) -> str:
    """``M:SS`` (``H:MM:SS`` from an hour on) of :func:`youtube_seconds`."""
    hours, rest = divmod(youtube_seconds(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def youtube_list(chapters: Sequence[Chapter]) -> str:
    """The chapter list for a YouTube description: one ``M:SS Title`` line per chapter."""
    return "".join(f"{youtube_time(c.start)} {clean_title(c.title)}\n" for c in chapters)


def youtube_problems(chapters: Sequence[Chapter]) -> list[str]:
    """Why YouTube would ignore ``chapters`` (published, so the first starts at 0:00), one
    message each: fewer than :data:`YOUTUBE_MIN_CHAPTERS`, or a chapter shorter than
    :data:`YOUTUBE_MIN_SECONDS` as its whole-second timestamps measure it."""
    if not chapters:
        return []
    problems = []
    if len(chapters) < YOUTUBE_MIN_CHAPTERS:
        intro = " (with the intro chapter)" if chapters[0].intro else ""
        problems.append(
            f"chapters: the YouTube chapter list has {len(chapters)} chapter(s){intro}; YouTube shows chapters only with at "
            f"least {YOUTUBE_MIN_CHAPTERS} (add chapter cards or scene `chapter:` keys)"
        )
    starts = [youtube_seconds(c.start) for c in chapters]
    ends = [*starts[1:], chapters[-1].end]
    for chapter, start, end in zip(chapters, starts, ends):
        length = end - start
        if length >= YOUTUBE_MIN_SECONDS - 1e-6:
            continue
        where = f"{youtube_time(chapter.start)}-{youtube_time(end)}"
        if chapter.intro:
            first = chapters[1]
            advice = (
                f"it runs until the first chapter '{clean_title(first.title)}' starts; begin the video with a chapter, "
                "or set `chapters: {intro: false}` to start the first chapter at 0:00"
            )
        else:
            advice = "merge it with a neighbour or lengthen it"
        problems.append(
            f"chapters: '{clean_title(chapter.title)}' ({where}) lasts {length:.1f} s; YouTube ignores the whole chapter "
            f"list when a chapter is shorter than {YOUTUBE_MIN_SECONDS} s ({advice})"
        )
    return problems


def write_youtube_list(path: Path, chapters: Sequence[Chapter]) -> list[str]:
    """Write :func:`youtube_list` of ``chapters`` to ``path`` (UTF-8); returns
    :func:`youtube_problems`."""
    path.write_text(youtube_list(chapters), encoding="utf-8")
    return youtube_problems(chapters)


def chapter_warnings(project: Project) -> list[str]:
    """``vidgen validate``'s warnings about the YouTube chapter list of ``project`` (planned
    times), when it writes one."""
    if not project.config.chapters.youtube or not chapter_marks(project.config.scenes):
        return []
    try:
        return youtube_problems(video_chapters(project, intro=True))
    except VidgenError:
        return []  # reported as problems elsewhere
