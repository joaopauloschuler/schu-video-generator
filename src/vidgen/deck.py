"""Key frames of a video as a slide deck (DESIGN.md §55): shared by ``vidgen slides`` (HTML,
Step 52) and the PDF deck (Step 53).

:func:`deck_frames` makes sure every scene has current frame stills (Step 10 capture, reused
like ``vidgen storyboard``: only scenes whose stills are missing or stale are rendered) and
picks the slides:

- ``mode="beat"`` (default): one slide per beat, its beat-end still (the fully built state of a
  reveal-per-beat scene); with ``per_beat`` N, N slides per beat (evenly spaced stills, the
  last at the beat's end); a silent scene gives its still(s) before the fade-out;
- ``mode="scene"``: one slide per scene, the still at the end of its last beat.

Consecutive near-identical stills of one scene (a beat that changes nothing on screen) are
merged into one slide carrying both beats' narration (``dedupe``). Each slide knows its scene,
chapter, the beats whose narration it carries (speaker notes, translated in a language
variant: the project is loaded with its variant), its times in the video and on the deck's
narration timeline (the scenes back to back, no transition overlaps), and the beats' MP3s.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

from vidgen.chapters import chapter_marks
from vidgen.config import FormatConfig, SceneConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.worker import scene_frames_dir, scene_timings_path

DeckMode = Literal["beat", "scene"]
DECK_MODES: tuple[str, ...] = ("beat", "scene")

#: Stills are compared at most this wide (px) for :func:`stills_alike`.
COMPARE_WIDTH = 320
#: A pixel "changed" when a channel differs by more than this (0-255).
PIXEL_TOLERANCE = 24
#: Two stills are alike when at most this fraction of their pixels changed.
CHANGED_FRACTION = 0.0005
#: Params read (in order) for a slide's scene title.
TITLE_PARAMS: tuple[str, ...] = ("title", "heading", "text", "name", "quote")


@dataclass(frozen=True)
class DeckBeat:
    """A beat whose narration a slide carries: ``id``, ``text`` (as configured, translated in a
    language variant), ``start`` / ``end`` of its speech in the scene (seconds), its MP3 (``None``
    when there is none: the scene was rendered with an estimate)."""

    id: str
    text: str
    start: float
    end: float
    audio: Path | None


@dataclass(frozen=True)
class DeckChapter:
    """The chapter a slide belongs to: ``title``, ``label`` (its number as written, else its
    position) and ``index`` (1-based)."""

    title: str
    label: str
    index: int


@dataclass(frozen=True)
class DeckSlide:
    """One slide: the ``still`` (PNG) and what it shows.

    ``beats``: the beats whose narration belongs to it (several after a merge or in scene mode;
    a beat with N stills is on each of its N slides; empty for a silent scene). ``k`` / ``n``:
    the still's place among its beat's stills. ``time``: the still's time in the video (``None``
    if not every scene has a render at this format), ``scene_time`` from the scene's start;
    ``at`` / ``until``: when the slide is on screen on the deck's narration timeline.
    ``merged``: how many stills were merged into it (1: none)."""

    index: int
    scene: str
    scene_type: str
    scene_number: int
    scene_title: str | None
    chapter: DeckChapter | None
    still: Path
    beats: tuple[DeckBeat, ...]
    k: int
    n: int
    time: float | None
    scene_time: float
    at: float
    until: float
    merged: int = 1

    @property
    def notes(self) -> str:
        """The speaker notes: the beats' narration, one paragraph per beat."""
        return "\n\n".join(beat.text for beat in self.beats)

    def alt_text(self, limit: int = 160) -> str:
        """A description for screen readers: scene type, title and the start of the narration."""
        parts = [f"{self.scene_type.replace('_', ' ')} scene"]
        if self.scene_title:
            parts[0] += f" “{self.scene_title}”"
        narration = " ".join(self.notes.split())
        if narration:
            if len(narration) > limit:
                narration = narration[: limit - 1].rsplit(" ", 1)[0] + "…"
            parts.append(narration)
        return ": ".join(parts)


@dataclass(frozen=True)
class DeckClip:
    """A beat's narration on the deck timeline: ``beat`` id, its MP3, ``at`` (seconds on the
    timeline) and ``duration``."""

    beat: str
    audio: Path
    at: float
    duration: float


@dataclass
class Deck:
    """What :func:`deck_frames` picked: the slides in video order, the narration clips (beats
    with an MP3) on the deck timeline of length ``duration``, the scenes rendered for it and
    those whose stills were reused, and the workers' ``(scene_id, message)`` warnings."""

    project: Project
    format: FormatConfig
    preview: bool
    mode: DeckMode
    per_beat: int
    overlays: bool
    dedupe: bool
    slides: list[DeckSlide] = field(default_factory=list)
    clips: list[DeckClip] = field(default_factory=list)
    duration: float = 0.0
    stills: int = 0
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)

    @property
    def merged(self) -> int:
        """Stills dropped because they looked like the slide before (``dedupe``)."""
        return sum(slide.merged - 1 for slide in self.slides)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VidgenError(f"cannot read {path}: {exc}; render the scene again (--force)") from None
    if not isinstance(data, dict):
        raise VidgenError(f"{path} is not a JSON object; render the scene again (--force)")
    return data


def scene_title(spec: SceneConfig) -> str | None:
    """The scene's on-screen title for alt text: the first text param of :data:`TITLE_PARAMS`."""
    for key in TITLE_PARAMS:
        value = spec.params.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return None


def _small(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        if rgb.width > COMPARE_WIDTH:
            rgb = rgb.resize((COMPARE_WIDTH, max(1, round(rgb.height * COMPARE_WIDTH / rgb.width))), Image.Resampling.BOX)
        return np.asarray(rgb, dtype=np.int16)


def stills_alike(a: Path, b: Path) -> bool:
    """True when two stills look the same: at most :data:`CHANGED_FRACTION` of their pixels
    (compared at most :data:`COMPARE_WIDTH` wide) differ by more than :data:`PIXEL_TOLERANCE`."""
    one, two = _small(a), _small(b)
    if one.shape != two.shape:
        return False
    changed = np.abs(one - two).max(axis=2) > PIXEL_TOLERANCE
    return float(changed.mean()) <= CHANGED_FRACTION


def _chapters(project: Project) -> dict[str, DeckChapter | None]:
    """Scene id -> the chapter it is in (``None`` before the first)."""
    marks = {m.scene: m for m in chapter_marks(project.config.scenes)}
    out: dict[str, DeckChapter | None] = {}
    current: DeckChapter | None = None
    for spec in project.config.scenes:
        mark = marks.get(spec.id)
        if mark is not None:
            index = (current.index + 1) if current is not None else 1
            current = DeckChapter(mark.title, mark.number if mark.number is not None else str(index), index)
        out[spec.id] = current
    return out


@dataclass
class _Still:
    beat: str | None
    k: int
    n: int
    scene_time: float
    path: Path


def _scene_stills(project: Project, preview: bool, scene_id: str) -> tuple[dict[str, Any], list[_Still]]:
    timings = _read_json(scene_timings_path(project, preview, scene_id))
    folder = scene_frames_dir(project, preview, scene_id)
    index = _read_json(folder / "index.json")
    stills = [_Still(s["beat"], int(s["k"]), int(s["n"]), float(s["time"]), folder / s["path"]) for s in index.get("frames", [])]
    if not stills:
        raise VidgenError(f"scene '{scene_id}' has no stills in {folder}; render it again (--force)")
    return timings, stills


def deck_frames(
    project: Project,
    *,
    preview: bool = True,
    mode: DeckMode = "beat",
    per_beat: int = 1,
    overlays: bool = True,
    dedupe: bool = True,
    jobs: int = 1,
    force: bool = False,
) -> Deck:
    """Render what is needed and pick the slides of ``project`` (loaded with its variant).

    ``mode``: ``beat`` (a slide per beat, ``per_beat`` stills each) or ``scene`` (a slide per
    scene); ``overlays``: ``False`` takes the stills from renders without overlays
    (:meth:`Project.without_overlays`, ``build/..._bare``); ``dedupe``: merge consecutive
    near-identical slides of a scene; ``jobs``: scenes rendered in parallel; ``force``: render
    every scene again.
    """
    from vidgen.render.pipeline import render_scenes
    from vidgen.storyboard import scene_starts, stills_current

    if mode not in DECK_MODES:
        raise VidgenError(f"--mode must be one of {', '.join(DECK_MODES)}")
    if per_beat < 1:
        raise VidgenError("--per-beat must be at least 1")
    if per_beat > 1 and mode == "scene":
        raise VidgenError("--per-beat is for --mode beat (a scene slide is the end of its last beat)")
    if jobs < 1:
        raise VidgenError("--jobs must be at least 1")
    source = project if overlays else project.without_overlays()
    ids = [s.id for s in source.config.scenes]
    to_render = [sid for sid in ids if force or not stills_current(source, preview, sid, per_beat)]
    runs = render_scenes(source, preview, to_render, jobs=jobs, frames=per_beat)
    deck = Deck(
        project=project,
        format=source.render_format(preview),
        preview=preview,
        mode=mode,
        per_beat=per_beat,
        overlays=overlays,
        dedupe=dedupe,
        rendered=runs.rendered,
        reused=[sid for sid in ids if sid not in runs.rendered],
        warnings=runs.warnings,
    )
    starts = scene_starts(source, preview)
    chapters = _chapters(project)
    offset = 0.0  # the scene's start on the deck timeline
    for number, spec in enumerate(project.config.scenes, start=1):
        timings, stills = _scene_stills(source, preview, spec.id)
        deck.stills += len(stills)
        beats = {b["id"]: b for b in timings.get("beats", [])}
        deck_beats: dict[str, DeckBeat] = {}
        for beat in spec.beats:
            timing = beats.get(beat.id, {"start": 0.0, "end": 0.0})
            begin, end = float(timing["start"]), float(timing["end"])
            mp3 = project.audio_dir / f"{beat.id}.mp3"
            audio = mp3 if mp3.is_file() else None
            deck_beats[beat.id] = DeckBeat(beat.id, beat.text, begin, end, audio)
            if audio is not None:
                deck.clips.append(DeckClip(beat.id, audio, round(offset + begin, 6), round(end - begin, 6)))
        start = starts.get(spec.id)
        chosen = stills[-1:] if mode == "scene" else stills
        scene_slides: list[DeckSlide] = []
        previous_time = 0.0
        for still in chosen:
            if mode == "scene":
                carried = tuple(deck_beats.values())
            else:
                carried = (deck_beats[still.beat],) if still.beat in deck_beats else ()
            slide = DeckSlide(
                index=0,
                scene=spec.id,
                scene_type=spec.type,
                scene_number=number,
                scene_title=scene_title(spec),
                chapter=chapters[spec.id],
                still=still.path,
                beats=carried,
                k=still.k,
                n=still.n,
                time=None if start is None else round(start + still.scene_time, 6),
                scene_time=still.scene_time,
                at=round(offset + (0.0 if mode == "scene" else previous_time), 6),
                until=round(offset + still.scene_time, 6),
            )
            previous_time = still.scene_time
            if dedupe and scene_slides and stills_alike(scene_slides[-1].still, slide.still):
                slide = _merge(scene_slides.pop(), slide)
            scene_slides.append(slide)
        if scene_slides:  # the last slide stays up to the scene's end
            last = scene_slides[-1]
            scene_slides[-1] = replace(last, until=round(offset + float(timings["duration"]), 6))
        deck.slides.extend(scene_slides)
        offset += float(timings["duration"])
    deck.slides = [replace(slide, index=i) for i, slide in enumerate(deck.slides, start=1)]
    deck.duration = round(offset, 6)
    return deck


def _merge(first: DeckSlide, later: DeckSlide) -> DeckSlide:
    """``later``'s still (the more finished one) with the narration of both, from ``first``'s
    start on the timeline."""
    beats = first.beats + tuple(b for b in later.beats if b not in first.beats)
    return replace(later, beats=beats, at=first.at, merged=first.merged + later.merged)
