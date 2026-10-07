"""The video's planned timeline: where every scene and beat will be, before anything is rendered.

Overlays (DESIGN.md §41) are drawn inside each scene's own render, but some depend on the whole
video: a lower third that runs on after a cut, a progress bar, a chapter indicator. Each scene
is rendered in its own process, so they cannot wait for the other scenes' renders; instead every
scene's length is *planned* from what fixes it (DESIGN.md §5):

- a narrated beat lasts ``d + narration.pad`` rounded to whole frames, ``d`` being its MP3's
  length (decoded, as the scene measures it) or, without audio, the word-count estimate;
- a narrated scene lasts its beats plus its type's ``outro`` (the fade-out of ``finish()``,
  Manim plays ``ceil(outro * fps)`` frames);
- a silent scene lasts its ``duration``.

Built-in scenes keep to this exactly; a scene whose animations overrun its narration (lint
``animation_overrun``) or an extension that times itself differently ends later or earlier than
planned, and overlays timed in the video are off by that much in the scenes after it (``vidgen
render`` warns). The plan is lazy: a scene's audio is only read when a time that depends on it
is asked for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from vidgen.chapters import chapter_marks
from vidgen.config import SceneConfig
from vidgen.project import Project


@dataclass(frozen=True)
class BeatSlot:
    """A beat as planned: ``start`` / ``end`` in seconds from its scene's start (``end`` is the
    end of its narration, ``start + d``; the pad follows), and its text."""

    id: str
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SceneSlot:
    """A scene as planned: position in the video (``start``, ``duration``, seconds), its beats,
    and the chapter it belongs to (the title of the last chapter starting at or before it: a
    ``chapter`` scene or a scene's ``chapter:``; ``None`` before the first)."""

    index: int
    id: str
    type: str
    start: float
    duration: float
    beats: tuple[BeatSlot, ...]
    chapter: str | None

    @property
    def end(self) -> float:
        """Where the scene ends in the video (seconds)."""
        return self.start + self.duration


@dataclass(frozen=True)
class Chapter:
    """A chapter of the video (DESIGN.md §42): its ``title``, ``number`` as written (``None``:
    not numbered), the ``scene`` it starts at, ``start`` / ``end`` in the video (seconds; a
    chapter ends where the next starts, the last one at the video's end), its position
    ``index`` (1-based), the number of chapters ``count``, and whether it starts with a
    ``chapter`` card (``card``)."""

    title: str
    number: str | None
    scene: str
    start: float
    end: float
    index: int
    count: int
    card: bool

    @property
    def label(self) -> str:
        """The number as shown: ``number``, else ``index``."""
        return self.number if self.number is not None else str(self.index)

    @property
    def duration(self) -> float:
        """Its length in seconds."""
        return self.end - self.start


@lru_cache(maxsize=4096)
def _decoded_length(path: str, size: int, mtime: int) -> float:
    from vidgen.scene import audio_duration

    return audio_duration(Path(path))


def beat_seconds(project: Project, beat_id: str, text: str) -> float:
    """``d`` of a beat: its MP3's decoded length, else the word-count estimate."""
    path = project.audio_dir / f"{beat_id}.mp3"
    try:
        st = path.stat()
    except OSError:
        return len(text.split()) / project.config.narration.words_per_second
    return _decoded_length(str(path), st.st_size, st.st_mtime_ns)


def _outro(spec: SceneConfig) -> float:
    from vidgen import registry

    entry = registry.find(spec.type)
    return float(getattr(entry.cls, "outro", 0.0)) if entry is not None else 0.0


class VideoPlan:
    """The planned timeline of ``project`` at ``fps`` frames per second (see the module doc).

    Durations are computed on first use and cached; :meth:`scene` of a scene needs the lengths of
    the scenes before it, :attr:`duration` all of them.
    """

    def __init__(self, project: Project, fps: int) -> None:
        self.project = project
        self.fps = fps
        self._specs = list(project.config.scenes)
        self._index = {spec.id: i for i, spec in enumerate(self._specs)}
        self._beats: dict[int, tuple[BeatSlot, ...]] = {}
        self._narrated: dict[int, int] = {}  # frames of a scene's beats (with their pads)
        self._durations: dict[int, float] = {}
        self._marks = chapter_marks(self._specs)
        self._chapters: tuple[Chapter, ...] | None = None

    def _frames(self, seconds: float) -> int:
        return round(seconds * self.fps)

    def _scene_beats(self, i: int) -> tuple[BeatSlot, ...]:
        if i not in self._beats:
            pad = self.project.config.narration.pad
            frames = 0
            slots = []
            for beat in self._specs[i].beats:
                d = beat_seconds(self.project, beat.id, beat.text)
                start = frames / self.fps
                slots.append(BeatSlot(beat.id, start, start + d, beat.text))
                frames += self._frames(d + pad)
            self._beats[i] = tuple(slots)
            self._narrated[i] = frames
        return self._beats[i]

    def scene_duration(self, i: int) -> float:
        """Planned length of scene ``i`` (seconds)."""
        if i not in self._durations:
            spec = self._specs[i]
            outro = _outro(spec)
            outro_frames = math.ceil(outro * self.fps - 1e-9) if outro > 0 else 0
            if spec.silent:
                duration = spec.duration or 0.0
                frames = max(self._frames(duration), self._frames(max(duration - outro, 0.0)) + outro_frames)
            else:
                self._scene_beats(i)
                frames = self._narrated[i] + outro_frames
            self._durations[i] = frames / self.fps
        return self._durations[i]

    def index(self, scene_id: str) -> int:
        """Position of ``scene_id`` in the video (0-based)."""
        return self._index[scene_id]

    def scene_start(self, scene_id: str) -> float:
        """Where ``scene_id`` starts in the video (seconds)."""
        i = self._index[scene_id]
        return sum(self.scene_duration(k) for k in range(i))

    def scene(self, scene_id: str) -> SceneSlot:
        """The planned :class:`SceneSlot` of ``scene_id``."""
        i = self._index[scene_id]
        spec = self._specs[i]
        return SceneSlot(
            i, spec.id, spec.type, self.scene_start(scene_id), self.scene_duration(i), self._scene_beats(i), self._chapter_at(i)
        )

    @property
    def scenes(self) -> tuple[SceneSlot, ...]:
        """Every scene, in order."""
        return tuple(self.scene(spec.id) for spec in self._specs)

    @property
    def duration(self) -> float:
        """Planned length of the whole video (seconds)."""
        return sum(self.scene_duration(i) for i in range(len(self._specs)))

    @property
    def chapters(self) -> tuple[Chapter, ...]:
        """The chapters, in order (``chapter`` scenes and scenes with a ``chapter:``)."""
        if self._chapters is None:
            marks = self._marks
            starts = [self.scene_start(m.scene) for m in marks]
            ends = [*starts[1:], self.duration]
            self._chapters = tuple(
                Chapter(m.title, m.number, m.scene, float(start), float(end), k, len(marks), m.card)
                for k, (m, start, end) in enumerate(zip(marks, starts, ends), start=1)
            )
        return self._chapters

    def chapter_of(self, scene_id: str) -> Chapter | None:
        """The chapter scene ``scene_id`` belongs to (``None`` before the first chapter)."""
        i = self._index[scene_id]
        found = None
        for mark, chapter in zip(self._marks, self.chapters):
            if mark.scene_index > i:
                break
            found = chapter
        return found

    def chapter_at(self, t: float) -> Chapter | None:
        """The chapter at video time ``t`` (``None`` before the first chapter)."""
        found = None
        for chapter in self.chapters:
            if chapter.start > t + 1e-9:
                break
            found = chapter
        return found

    def _chapter_at(self, i: int) -> str | None:
        title = None
        for mark in self._marks:
            if mark.scene_index > i:
                break
            title = mark.title
        return title

    def resolve(self, value: Any, end: bool) -> float | None:
        """A ``from`` / ``to`` value in video seconds: a number as it is, a scene id as that
        scene's start (``end``: its end); ``None`` stays ``None``."""
        if value is None:
            return None
        if isinstance(value, str):
            start = self.scene_start(value)
            return start + self.scene_duration(self._index[value]) if end else start
        return float(value)


def video_chapters(project: Project, fps: int | None = None) -> tuple[Chapter, ...]:
    """The chapters of ``project``'s video (DESIGN.md §42): ``chapter`` scenes and scenes with a
    ``chapter:`` field, each with its title, number, scene, planned ``start`` / ``end`` in seconds
    (at ``fps``, default the final format's), position and count. Empty without chapters.

    Scene lengths need the scene types (their fade-out); when one is not registered (called
    outside a render or an extension), the project's types are loaded for the call."""
    from vidgen import extensions, registry

    fps = fps or project.config.format.fps
    if all(registry.find(spec.type) is not None for spec in project.config.scenes):
        return VideoPlan(project, fps).chapters
    with extensions.project_session(project):
        return VideoPlan(project, fps).chapters
