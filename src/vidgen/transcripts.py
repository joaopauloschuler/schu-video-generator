"""Transcripts of an audio-only render from its timings (DESIGN.md §111.3): plain text with the
speakers' names and the chapter titles, SRT and WebVTT cues timed by the words
(:func:`vidgen.render.pipeline.video_cues`, the cues a video's SRT holds), and the chapter list
``<output>_chapters.txt`` (the same file a video render writes).

The plain text starts with the title; each chapter starts with ``[M:SS] Title``; each turn of a
voice in a scene (section) is a paragraph, ``Name: text`` when the project has more than one
voice (the base voice without a label is ``Narrator``), lines of one voice in a row joined.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vidgen.chapter_export import clean_title, youtube_time
from vidgen.fileio import write_text_atomic
from vidgen.subtitles import Cue, format_srt
from vidgen.voices import beat_voice_names, speaker_label

if TYPE_CHECKING:
    from vidgen.project import Project

#: The base voice's name in a transcript of several voices, when it has no ``label``.
NARRATOR = "Narrator"


def vtt_time(seconds: float) -> str:
    """WebVTT timestamp ``HH:MM:SS.mmm``."""
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def vtt_text(text: str) -> str:
    """Cue text as WebVTT requires: ``&``, ``<``, ``>`` escaped (so ``-->`` cannot occur) and no
    blank line inside the cue (a blank line ends it)."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "\n".join(line for line in escaped.splitlines() if line.strip())


def format_vtt(cues: Iterable[Cue]) -> str:
    """A WebVTT document of ``cues``."""
    blocks = [f"{vtt_time(c.start)} --> {vtt_time(c.end)}\n{vtt_text(c.text)}\n" for c in cues]
    return "WEBVTT\n\n" + "\n".join(blocks)


def plain_text(project: Project, timings: dict[str, Any]) -> str:
    """The plain-text transcript of an audio-only render's ``timings`` (see the module doc)."""
    config = project.config
    names = beat_voice_names(config)
    several = len(set(names.values())) > 1
    starts = {c["scene"]: c for c in timings.get("chapters", []) if not c.get("intro")}
    lines = [config.title, ""]
    turn: tuple[str | None, list[str]] | None = None

    def flush() -> None:
        nonlocal turn
        if turn is not None:
            speaker, texts = turn
            label = (speaker_label(config, speaker) or NARRATOR) if several else None
            lines.extend([f"{label}: {' '.join(texts)}" if label else " ".join(texts), ""])
        turn = None

    for scene in timings["scenes"]:
        flush()
        chapter = starts.get(scene["id"])
        if chapter is not None:
            lines.extend([f"[{youtube_time(chapter['start'])}] {clean_title(chapter['title'])}", ""])
        for beat in scene["beats"]:
            text = " ".join(beat["text"].split())
            if not text:
                continue
            speaker = names.get(beat["id"])
            if turn is not None and turn[0] == speaker:
                turn[1].append(text)
            else:
                flush()
                turn = (speaker, [text])
    flush()
    return "\n".join(lines).rstrip() + "\n"


def transcript_paths(project: Project, preview: bool) -> dict[str, Path]:
    """Where each transcript goes: ``<output>_transcript.txt``, ``.srt``, ``.vtt``,
    ``_chapters.txt``."""
    srt = project.srt_path(preview)
    return {
        "txt": srt.with_name(srt.stem + "_transcript.txt"),
        "srt": srt,
        "vtt": srt.with_suffix(".vtt"),
        "chapters": project.chapters_path(preview),
    }


def write_transcripts(project: Project, timings: dict[str, Any], preview: bool, kinds: Iterable[str]) -> dict[str, Path]:
    """Write the transcripts ``kinds`` (``txt``, ``srt``, ``vtt``, ``chapters``) of an audio-only
    render; returns the files written (``chapters`` only when there are chapters or references,
    as for a video)."""
    from vidgen.render.pipeline import video_cues, write_chapter_list

    kinds = list(kinds)
    paths = transcript_paths(project, preview)
    written: dict[str, Path] = {}
    cues = video_cues(project, timings) if {"srt", "vtt"} & set(kinds) else []
    for kind in kinds:
        if kind == "txt":
            write_text_atomic(paths["txt"], plain_text(project, timings))
        elif kind == "srt":
            write_text_atomic(paths["srt"], format_srt(cues))
        elif kind == "vtt":
            write_text_atomic(paths["vtt"], format_vtt(cues))
        elif kind == "chapters":
            if write_chapter_list(project, preview, timings, warn=False) is None:   # YouTube's rules do not apply
                continue
        written[kind] = paths[kind]
    return written
