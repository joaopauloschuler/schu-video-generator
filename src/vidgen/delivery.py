"""Delivering an audio drama (DESIGN.md §112.3): a cold open, spoken credits from the cast, one
file per chapter (episode) with a playlist and per-file transcripts, and what the drama
loudness preset's dialogue checks measure.

**Config** (:func:`apply_delivery`, on the raw config after ``sections`` and a ``cut``, before
it is validated, like :func:`vidgen.cuts.apply_cut`): ``cold_open: ID`` moves that scene
(section) to the very start, before the title and the theme (its chapter title dropped, so it
belongs to the first chapter's file); ``cold_open: [beat ids]`` copies those beats, in order,
into a scene ``cold_open`` at the start (ids ``cold_open_<beat id>``: re-voiced; the lines are
heard again in their place; the first beat's scene gives the room, ambience and music; a copied
beat keeps its sound actions only). ``credits: {speak: true}`` appends a closing scene: the
title, "Starring <actor> as <character>, ..." for every named voice that speaks (in the order
they first speak; the actor from ``voiced_by``, else a Kokoro voice's own name, ``af_bella`` ->
Bella; without one the character alone), "Narrated by <actor>." when the base voice speaks and
has an actor, then ``lines``; read by ``voice`` (default the narrator) under the score theme
``music`` (default ``main`` when the score has one).

**Files** (``audio_output.split: chapters``): :func:`plan_parts` cuts the audio at the chapter
starts (the first file also holds what comes before the first chapter: a cold open), each cut
:data:`pacing.lead_in <vidgen.config.PacingConfig>` before the chapter's first line but never
more than half-way back into the silence before it; a file ends with a fade of at most
:data:`PART_FADE_OUT` after its last line and starts with one of at most :data:`PART_FADE_IN`
before its first. :mod:`vidgen.mix` writes each part normalised on its own
(:class:`~vidgen.mix.MixPart`); :func:`write_parts` encodes them as
``<output>_<NN>_<title>.<format>``, writes ``<output>.m3u`` and each file's transcripts (txt,
srt, vtt; times in that file).
"""

from __future__ import annotations

import copy
import difflib
import json
import math
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from vidgen.config import CreditsConfig
from vidgen.cuts import _moved_origins, _with_beat_ids
from vidgen.errors import VidgenError
from vidgen.includes import Origin
from vidgen.voices import DEFAULT_VOICE

if TYPE_CHECKING:
    from vidgen.audio_check import Dialogue
    from vidgen.mix import MixPart
    from vidgen.project import Project

#: The id of the scene a cold open of beats becomes (its beats: ``cold_open_<beat id>``).
COLD_OPEN_ID = "cold_open"
#: The scene type the cold open and the credits become (as sections do).
CARD_TYPE = "text_card"
#: A Kokoro voice id: two letters (language, kind), then the voice's name.
KOKORO_NAME = re.compile(r"^[a-z]{2}_([a-z]+)$")
#: Longest fades (seconds) at a split file's end (after its last line) and start (before its first).
PART_FADE_OUT = 2.0
PART_FADE_IN = 0.3


# ----- config: cold open and spoken credits ---------------------------------------------------------


def _did_you_mean(name: str, known: Sequence[str]) -> str:
    close = difflib.get_close_matches(name, list(known), n=1)
    return f"; did you mean '{close[0]}'?" if close else ""


def _sound_actions(beat: dict[str, Any]) -> dict[str, Any]:
    """``beat`` with only its sound actions (``sfx``): the cold open is a card scene."""
    actions = beat.get("actions")
    if isinstance(actions, list):
        kept = [a for a in actions if isinstance(a, Mapping) and ("sfx" in a or a.get("action") == "sfx")]
        if kept:
            beat["actions"] = kept
        else:
            beat.pop("actions")
    return beat


def _cold_open(data: dict[str, Any], origins: dict[str, Origin]) -> tuple[dict[str, Any], dict[str, Origin]]:
    spec = data.get("cold_open")
    scenes = data.get("scenes")
    if spec is None or not isinstance(scenes, list) or not (isinstance(spec, str) or isinstance(spec, list) and all(isinstance(s, str) for s in spec)):
        return data, origins
    ids = [s.get("id") if isinstance(s, Mapping) else None for s in scenes]
    if isinstance(spec, str) and spec in ids:
        i = ids.index(spec)
        moved = copy.deepcopy(dict(scenes[i]))
        moved.pop("chapter", None)
        moved.pop("transition", None)
        order = [i, *(k for k in range(len(scenes)) if k != i)]
        return {**data, "scenes": [moved if k == i else scenes[k] for k in order]}, _moved_origins(origins, order)
    wanted = [spec] if isinstance(spec, str) else list(spec)
    found: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for scene in scenes:
        if isinstance(scene, Mapping) and isinstance(scene.get("id"), str):
            filled = _with_beat_ids(dict(scene))
            for beat in filled.get("beats") or []:
                if isinstance(beat, Mapping):
                    found[str(beat.get("id"))] = (filled, dict(beat))
    for name in wanted:
        if name not in found:
            known = [*(str(i) for i in ids if i is not None), *found]
            raise VidgenError(f"cold_open: no scene or beat '{name}'{_did_you_mean(name, known)} (a scene / section id, or a list of beat ids)")
    if COLD_OPEN_ID in ids:
        raise VidgenError(f"cold_open: a scene '{COLD_OPEN_ID}' exists already; name the beats to copy or the scene to move")
    beats = []
    for name in wanted:
        scene, beat = found[name]
        beat = _sound_actions(copy.deepcopy(beat))
        beat["id"] = f"{COLD_OPEN_ID}_{name}"
        if "voice" not in beat and "voice" in scene:
            beat["voice"] = scene["voice"]
        beats.append(beat)
    first = found[wanted[0]][0]
    opener: dict[str, Any] = {"id": COLD_OPEN_ID, "type": CARD_TYPE, "params": {"text": str(data.get("title") or "…")}, "beats": beats}
    for key in ("room", "ambience", "music"):
        if key in first:
            opener[key] = copy.deepcopy(first[key])
    sources: list[int | None] = [None, *range(len(scenes))]
    return {**data, "scenes": [opener, *scenes]}, _moved_origins(origins, sources)


def _speaking_voices(scenes: Sequence[Any]) -> tuple[list[str], bool]:
    """The named voices that say a line, in the order they first do, and whether the base voice
    says one."""
    named: list[str] = []
    base = False
    for scene in scenes:
        if not isinstance(scene, Mapping) or scene.get("id") == COLD_OPEN_ID:   # the cast in the story's order
            continue
        for beat in scene.get("beats") or []:
            beat = {"text": beat} if isinstance(beat, str) else beat
            if not isinstance(beat, Mapping):
                continue
            name = beat.get("voice", scene.get("voice"))
            if name is None or name == DEFAULT_VOICE:
                base = True
            elif isinstance(name, str) and name not in named:
                named.append(name)
    return named, base


def _actor(data: Mapping[str, Any], credits: CreditsConfig, name: str, entry: Mapping[str, Any] | None) -> str | None:
    """Who plays voice ``name`` (``narrator``: the base voice, ``entry`` ``None``)."""
    if name in credits.voiced_by:
        return credits.voiced_by[name]
    base = data.get("voice") if isinstance(data.get("voice"), Mapping) else {}
    entry = entry or {}
    provider = entry.get("provider") or base.get("provider")
    voice = entry.get("voice") or base.get("voice")
    match = KOKORO_NAME.match(voice) if provider == "kokoro" and isinstance(voice, str) else None
    return match[1].capitalize() if match else None


def _joined(parts: Sequence[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text[-1:] in ".!?…" else text + "."


def credit_lines(data: Mapping[str, Any], credits: CreditsConfig) -> list[str]:
    """The lines of the spoken credits of the raw config ``data`` (see the module doc)."""
    lines = [_sentence(credits.title or str(data.get("title") or ""))] if (credits.title or data.get("title")) else []
    if credits.cast:
        named, base = _speaking_voices(data.get("scenes") or [])
        voices = data.get("voices") if isinstance(data.get("voices"), Mapping) else {}
        parts = []
        for name in named:
            entry = voices.get(name) if isinstance(voices.get(name), Mapping) else {}
            label = entry.get("label") or name.replace("_", " ").capitalize()
            actor = _actor(data, credits, name, entry)
            parts.append(f"{actor} as {label}" if actor else str(label))
        if parts:
            lines.append(f"Starring {_joined(parts)}.")
        narrator = _actor(data, credits, "narrator", None) if base else None
        if narrator:
            lines.append(f"Narrated by {narrator}.")
    return lines + [_sentence(line) for line in credits.lines]


def _credits(data: dict[str, Any], origins: dict[str, Origin]) -> tuple[dict[str, Any], dict[str, Origin]]:
    raw = data.get("credits")
    scenes = data.get("scenes")
    if not isinstance(raw, Mapping) or raw.get("speak") is not True or not isinstance(scenes, list):
        return data, origins
    try:
        credits = CreditsConfig.model_validate(raw)
    except ValidationError:   # the config check reports it
        return data, origins
    if any(isinstance(s, Mapping) and s.get("id") == credits.id for s in scenes):
        raise VidgenError(f"credits: a scene '{credits.id}' exists already; give the spoken credits another id (credits: {{speak: true, id: closing}})")
    lines = credit_lines(data, credits)
    if not lines:
        raise VidgenError("credits: nothing to say (no title, no cast, no lines)")
    voice = {"voice": credits.voice} if credits.voice is not None else {}
    scene: dict[str, Any] = {"id": credits.id, "type": CARD_TYPE, "params": {"text": credits.chapter or "Credits"},
                             "beats": [{"text": line, **voice} for line in lines]}
    if credits.chapter is not None:
        scene["chapter"] = credits.chapter
    music: str | bool | None = credits.music
    if music is None:
        score = data.get("score") if isinstance(data.get("score"), Mapping) else {}
        themes = score.get("themes") if isinstance(score.get("themes"), Mapping) else {}
        music = "main" if "main" in themes else None
    if music is not None:
        scene["music"] = music
    return {**data, "scenes": [*scenes, scene]}, origins


def apply_delivery(data: Any, origins: Mapping[str, Origin] | None = None) -> tuple[Any, dict[str, Origin]]:
    """``data`` (a raw config with ``scenes``) with its ``cold_open`` and spoken ``credits``
    applied (see the module doc), ``origins`` moved with the scenes; unchanged without them.
    :class:`VidgenError` for an unknown cold-open id (did-you-mean) or a scene id taken."""
    origins = dict(origins or {})
    if not isinstance(data, Mapping) or (data.get("cold_open") is None and not isinstance(data.get("credits"), Mapping)):
        return data, origins
    out, origins = _cold_open(dict(data), origins)
    return _credits(out, origins)


# ----- files per chapter ------------------------------------------------------------------------


@dataclass(frozen=True)
class Part:
    """One file of a split render: its number (from 1), title, seconds of the whole audio, the
    scenes in it (ids) and its edge fades (seconds)."""

    index: int
    title: str
    start: float
    end: float
    scenes: tuple[str, ...]
    fade_in: float = 0.0
    fade_out: float = 0.0


def speech_lines(project: Project, timings: Mapping[str, Any]) -> list[tuple[int, str, float, float]]:
    """``(scene index, beat id, start, end)`` of each beat's speech (the MP3's silence cut off;
    the whole beat without one), in order."""
    from vidgen.speech import speech_bounds

    out = []
    for i, scene in enumerate(timings["scenes"]):
        for beat in scene["beats"]:
            start, end = beat["start"], beat["end"]
            mp3 = project.audio_dir / f"{beat['id']}.mp3"
            if mp3.is_file():
                try:
                    s0, s1 = speech_bounds(mp3)
                    start, end = min(start + s0, end), min(start + s1, end)
                except VidgenError:
                    pass
            if end > start:
                out.append((i, str(beat["id"]), start, end))
    return out


def plan_parts(project: Project, timings: Mapping[str, Any], lead_in: float) -> list[Part]:
    """The files of ``audio_output.split: chapters`` (see the module doc); one part (the title)
    without chapters."""
    from vidgen.chapters import chapter_marks

    scenes = timings["scenes"]
    duration = float(timings["duration"])
    marks = chapter_marks(project.config.scenes)
    speech = speech_lines(project, timings)
    starts = [0] + [m.scene_index for m in marks[1:]]
    titles = [m.title for m in marks] or [project.config.title]
    cuts = [0.0]
    for index in starts[1:]:
        scene_start = float(scenes[index]["start"])
        before = [end for i, _, _, end in speech if i < index]
        after = [start for i, _, start, _ in speech if i >= index]
        prev_end = max(before) if before else 0.0
        cut = scene_start
        if after:
            first = min(after)
            cut = max(min(scene_start, first - lead_in), (prev_end + first) / 2)
        cuts.append(cut)
    cuts.append(duration)
    parts = []
    for k, (title, first_scene) in enumerate(zip(titles, starts)):
        last_scene = starts[k + 1] if k + 1 < len(starts) else len(scenes)
        lo, hi = cuts[k], cuts[k + 1]
        said = [(start, end) for i, _, start, end in speech if first_scene <= i < last_scene]
        fade_in = min(PART_FADE_IN, max(0.0, said[0][0] - lo)) if k and said else 0.0
        fade_out = min(PART_FADE_OUT, max(0.0, hi - said[-1][1])) if k + 1 < len(starts) and said else 0.0
        ids = tuple(str(s["id"]) for s in scenes[first_scene:last_scene])
        parts.append(Part(k + 1, title, round(lo, 6), round(hi, 6), ids, round(fade_in, 6), round(fade_out, 6)))
    return parts


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40].strip("_")


def part_path(project: Project, preview: bool, part: Part, count: int) -> Path:
    """``<output>_<NN>_<title>.<format>`` next to the unsplit file's place."""
    whole = project.audio_path(preview)
    digits = max(2, len(str(count)))
    slug = _slug(part.title)
    return whole.with_name(f"{whole.stem}_{part.index:0{digits}d}{'_' + slug if slug else ''}{whole.suffix}")


def playlist_path(project: Project, preview: bool) -> Path:
    """``<output>.m3u``."""
    return project.audio_path(preview).with_suffix(".m3u")


def mix_parts(parts: Sequence[Part], folder: Path) -> list[MixPart]:
    """The mix's parts of ``parts`` (WAVs in ``folder``)."""
    from vidgen.mix import MixPart
    from vidgen.sfx import RATE

    return [MixPart(folder / f"part_{p.index:02d}.wav", round(p.start * RATE), round(p.end * RATE), p.fade_in, p.fade_out) for p in parts]


def part_timings(timings: Mapping[str, Any], part: Part) -> dict[str, Any]:
    """The timings of one file: its scenes and beats (and chapters, without the intro) at that
    file's times; the shape the transcripts read."""
    ids = set(part.scenes)

    def at(t: float) -> float:
        return round(t - part.start, 6)

    scenes = []
    for scene in timings["scenes"]:
        if scene["id"] in ids:
            beats = [{**b, "start": at(b["start"]), "end": at(b["end"])} for b in scene["beats"]]
            scenes.append({"id": scene["id"], "type": scene["type"], "start": at(scene["start"]), "duration": scene["duration"], "beats": beats})
    chapters = [{**c, "start": max(0.0, at(c["start"])), "end": at(c["end"])} for c in timings.get("chapters", []) if c["scene"] in ids and not c.get("intro")]
    keep = {k: v for k, v in timings.items() if k not in ("scenes", "chapters", "mix", "duration")}
    return {**keep, "duration": round(part.end - part.start, 6), "scenes": scenes, "chapters": chapters}


def _tags(project: Project, part: Part, count: int) -> dict[str, str]:
    from vidgen.chapter_export import clean_title, video_tags

    tags = video_tags(project.config)
    title = tags["title"]
    tags.setdefault("album", title)
    return {**tags, "title": f"{title}: {clean_title(part.title)}" if clean_title(part.title) != title else title, "track": f"{part.index}/{count}"}


def write_playlist(path: Path, title: str, entries: Sequence[tuple[Path, str, float]]) -> None:
    """An extended M3U (UTF-8) of ``entries`` (file, title, seconds), the files named relative
    to the playlist; a file the playlist listed before and lists no more is removed."""
    from vidgen.fileio import remove_file, write_text_atomic

    names = [f.name for f, _, _ in entries]
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "/" not in line and "\\" not in line and line not in names:
                remove_file(path.parent / line)
    lines = ["#EXTM3U", f"#PLAYLIST:{title}"]
    for file, name, seconds in entries:
        lines += [f"#EXTINF:{math.ceil(seconds)},{name}", file.name]
    write_text_atomic(path, "\n".join(lines) + "\n")


@dataclass
class WrittenParts:
    """What :func:`write_parts` wrote: each part's file, the playlist and the transcripts
    (``<kind>_<NN>`` -> file)."""

    files: list[tuple[Part, Path]]
    playlist: Path
    transcripts: dict[str, Path]


def write_parts(project: Project, preview: bool, timings: Mapping[str, Any], parts: Sequence[Part], mixed: Sequence[MixPart]) -> WrittenParts:
    """The split render's deliverables from the parts' mixes ``mixed`` (see the module doc)."""
    from vidgen import audio_encode
    from vidgen.chapter_export import clean_title
    from vidgen.fileio import replace_file, write_text_atomic
    from vidgen.render.pipeline import video_cues
    from vidgen.subtitles import format_srt
    from vidgen.transcripts import format_vtt, plain_text

    out = project.config.audio_output
    kinds = [k for k in out.transcript_kinds if k != "chapters"]
    files: list[tuple[Part, Path]] = []
    transcripts: dict[str, Path] = {}
    for part, wav in zip(parts, mixed):
        path = part_path(project, preview, part, len(parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        if out.format == "wav" and out.channels == "stereo" and out.sample_rate == 48000 and out.bit_depth == 24:
            partial = path.with_name(path.name + ".part")
            shutil.copyfile(wav.path, partial)
            replace_file(partial, path)
        else:
            audio_encode.encode(wav.path, path, out, _tags(project, part, len(parts)))
        files.append((part, path))
        own = part_timings(timings, part)
        cues = video_cues(project, own) if {"srt", "vtt"} & set(kinds) else []
        for kind in kinds:
            target = path.with_name(path.stem + ("_transcript.txt" if kind == "txt" else f".{kind}"))
            text = plain_text(project, own) if kind == "txt" else format_srt(cues) if kind == "srt" else format_vtt(cues)
            write_text_atomic(target, text)
            transcripts[f"{kind}_{part.index:02d}"] = target
    playlist = playlist_path(project, preview)
    title = project.config.title
    write_playlist(playlist, title, [(path, f"{title} - {clean_title(part.title)}" if clean_title(part.title) != title else title, part.end - part.start)
                                     for part, path in files])
    return WrittenParts(files, playlist, transcripts)


# ----- what the checks need ------------------------------------------------------------------------


def dialogue(project: Project, timings: Mapping[str, Any], start: float = 0.0, end: float = math.inf) -> Dialogue:
    """The drama preset's :class:`~vidgen.audio_check.Dialogue` of the file holding the seconds
    ``start`` to ``end`` of the audio: the lines in it (at its times; who says them as the
    transcripts name them), the mix's music check (its dense runs those in the file; its
    ``under_dialogue_lu`` the whole's), ``score.dense_lu``."""
    from vidgen.audio_check import Dialogue, DialogueLine
    from vidgen.transcripts import NARRATOR
    from vidgen.voices import beat_voice_names, speaker_label

    config = project.config
    names = beat_voice_names(config)
    lines = [DialogueLine(beat, speaker_label(config, names.get(beat)) or NARRATOR, round(a - start, 6), round(b - start, 6))
             for _, beat, a, b in speech_lines(project, timings) if start <= a < end]
    music = (timings.get("mix") or {}).get("music_check")
    if music is not None and (start > 0 or end < math.inf):   # the dense runs in this file; under_dialogue_lu stays the whole's
        dense = [r for r in music.get("dense", []) if start <= r["start"] < end]
        lus = [r["lu"] for r in dense if r["lu"] is not None]
        music = {**music, "dense": dense, "worst_dense_lu": min(lus) if lus else None}
    return Dialogue(lines, music, config.score.dense_lu)


@dataclass(frozen=True)
class RenderedFile:
    """A file of a project's last audio-only render and the seconds of the audio it holds."""

    path: Path
    start: float
    end: float
    title: str


def rendered_files(project: Project, preview: bool) -> tuple[list[RenderedFile], dict[str, Any] | None]:
    """The files of ``project``'s last audio-only render (the parts of a split one, else the
    file) and its ``timings.json`` (``None`` when there is none)."""
    timings_file = project.render_dir(preview) / "audio" / "timings.json"
    timings = json.loads(timings_file.read_text(encoding="utf-8")) if timings_file.is_file() else None
    written = (timings or {}).get("audio_output", {}).get("files")
    whole = project.audio_path(preview)
    if written:
        return [RenderedFile(whole.with_name(f["file"]), f["start"], f["end"], f["title"]) for f in written], timings
    end = float(timings["duration"]) if timings else math.inf
    return [RenderedFile(whole, 0.0, end, project.config.title)], timings
