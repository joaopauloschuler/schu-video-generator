"""``NarratedScene``: the base class of every scene type (DESIGN.md §5.1).

A scene is constructed with its config and the active project/theme injected::

    scene = SceneClass(spec, project, theme, audio=True)   # needs Manim's config set up
    scene.render()
    scene.timings()   # {"scene", "duration", "beats": [{"id", "start", "end", "text"}]}

Params validation does not need Manim to be configured: ``SceneClass.validate_params(raw)``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple

import av
from manim import NORMAL, FadeOut, MarkupText, Scene, Text, config
from pydantic import BaseModel, ConfigDict, ValidationError

from vidgen import helpers, runtime
from vidgen.config import BeatConfig, SceneConfig, validation_error_lines
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.theme import Theme

log = logging.getLogger("vidgen.scene")


class SceneParams(BaseModel):
    """Base class for a scene type's ``Params`` model; unknown keys are an error."""

    model_config = ConfigDict(extra="forbid")


class BeatTiming(NamedTuple):
    """When a beat was narrated, in seconds from the start of the scene (``end = start + d``)."""

    beat_id: str
    start: float
    end: float
    text: str


def audio_duration(path: Path) -> float:
    """Length of an audio file in seconds (read with PyAV)."""
    try:
        with av.open(str(path)) as container:
            if container.duration is not None:
                return container.duration / av.time_base
            stream = container.streams.audio[0]
            if stream.duration is None or stream.time_base is None:
                raise ValueError("no duration information")
            return float(stream.duration * stream.time_base)
    except (OSError, ValueError, IndexError, av.error.FFmpegError) as exc:
        raise VidgenError(f"cannot read audio file {path}: {exc}") from None


class NarratedScene(Scene):
    """A Manim scene timed by narration.

    Inside ``construct()``: ``self.spec`` (``SceneConfig``), ``self.params`` (validated
    ``Params`` instance, or a dict), ``self.beats``, ``self.theme``, ``self.project``.
    Subclasses may define ``class Params(SceneParams)`` to validate their params.

    ``audio=False`` renders without adding narration sounds; durations still come from the
    audio files, so timing is identical to a render with audio.

    If you override ``tear_down``, call ``super().tear_down()`` (it pads silent scenes to their
    ``duration``).
    """

    def __init__(
        self,
        spec: SceneConfig,
        project: Project | None = None,
        theme: Theme | None = None,
        *,
        audio: bool = True,
        **scene_kwargs: Any,
    ) -> None:
        self.spec = spec
        self.project = project if project is not None else runtime.current_project()
        if theme is None:
            active = runtime.has_context() and runtime.current_project() is self.project
            theme = runtime.current_theme() if active else Theme(self.project.config.theme)
        self.theme = theme
        self.params = type(self).parse_params(spec.params, scene_id=spec.id)
        self.beats: list[BeatConfig] = list(spec.beats)
        self.audio_enabled = audio
        self.beat_log: list[BeatTiming] = []
        self._durations: dict[str, float] = {}
        super().__init__(**scene_kwargs)

    # ----- params ----------------------------------------------------------------------------

    @classmethod
    def params_model(cls) -> type[SceneParams] | None:
        """The ``Params`` model of this class (inherited ones count), or ``None``."""
        model = getattr(cls, "Params", None)
        return model if isinstance(model, type) and issubclass(model, SceneParams) else None

    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> SceneParams | dict[str, Any]:
        """Validate raw params; raises ``pydantic.ValidationError``. No Manim setup needed."""
        model = cls.params_model()
        if model is None:
            return dict(params)
        return model.model_validate(dict(params))

    @classmethod
    def parse_params(cls, params: Mapping[str, Any], scene_id: str = "?") -> SceneParams | dict[str, Any]:
        """Like :meth:`validate_params` but raises a readable :class:`VidgenError`."""
        try:
            return cls.validate_params(params)
        except ValidationError as exc:
            lines = validation_error_lines(exc, ("params",))
            raise VidgenError("\n".join([f"scene '{scene_id}': invalid params", *(f"  {x}" for x in lines)])) from None

    # ----- beats and timing ------------------------------------------------------------------

    @property
    def pad(self) -> float:
        """Silence after each beat (``narration.pad``)."""
        return self.project.config.narration.pad

    def beat(self, beat: str | int | BeatConfig) -> BeatConfig:
        """Resolve a beat id, 0-based index or ``BeatConfig`` to this scene's ``BeatConfig``."""
        if isinstance(beat, BeatConfig):
            return beat
        if isinstance(beat, int) and not isinstance(beat, bool):
            if not 0 <= beat < len(self.beats):
                raise VidgenError(
                    f"scene '{self.spec.id}': beat index {beat} out of range (it has {len(self.beats)} beats)"
                )
            return self.beats[beat]
        for candidate in self.beats:
            if candidate.id == beat:
                return candidate
        known = ", ".join(b.id for b in self.beats) or "none"
        raise VidgenError(f"scene '{self.spec.id}': unknown beat {beat!r} (beats: {known})")

    def beat_audio(self, beat: str | int | BeatConfig) -> Path | None:
        """The beat's MP3 in ``project.audio_dir``, or ``None`` if it does not exist."""
        path = self.project.audio_dir / f"{self.beat(beat).id}.mp3"
        return path if path.is_file() else None

    def beat_duration(self, beat: str | int | BeatConfig) -> float:
        """Audio length of the beat, or the word-count estimate when it has no audio."""
        b = self.beat(beat)
        if b.id not in self._durations:
            path = self.beat_audio(b)
            if path is not None:
                self._durations[b.id] = audio_duration(path)
            else:
                self._durations[b.id] = b.estimated_duration(self.project.config.narration.words_per_second)
        return self._durations[b.id]

    @contextmanager
    def narrate(self, beat: str | int | BeatConfig) -> Iterator[float]:
        """Narrate one beat: ``with self.narrate(0) as d: ...``.

        Starts the beat's audio now (unless ``audio=False``), yields its duration ``d`` and on
        exit waits until ``d + pad`` seconds have passed since entering. Records a
        :class:`BeatTiming` in ``self.beat_log``.
        """
        b = self.beat(beat)
        if any(entry.beat_id == b.id for entry in self.beat_log):
            raise VidgenError(f"scene '{self.spec.id}': beat '{b.id}' is narrated twice")
        d = self.beat_duration(b)
        path = self.beat_audio(b)
        if path is not None and self.audio_enabled:
            self.add_sound(str(path))
        start = float(self.renderer.time)
        yield d
        self.wait_seconds(d + self.pad - (self.renderer.time - start))
        self.beat_log.append(BeatTiming(b.id, start, start + d, b.text))

    def narrate_all(self) -> Iterator[tuple[BeatConfig, float]]:
        """Narrate every beat in order: ``for beat, d in self.narrate_all(): ...``."""
        for i, beat in enumerate(self.beats):
            with self.narrate(i) as d:
                yield beat, d

    def wait_seconds(self, seconds: float) -> None:
        """Wait ``seconds`` rounded to whole frames (no-op if that is zero frames).

        Unlike ``self.wait``, the number of frames written is exact, so scene lengths do not
        drift by a frame per wait.
        """
        fps = config.frame_rate
        frames = round(seconds * fps)
        if frames <= 0:
            return
        # Mirror Scene.should_update_mobjects: Manim writes int(t*fps) frames for a frozen wait
        # but ceil(t*fps) frames when it redraws every frame; ask for a time that gives `frames`.
        frozen = not (
            getattr(self, "always_update_mobjects", False)
            or getattr(self, "updaters", None)
            or any(m.has_time_based_updater() for m in self.get_mobject_family_members())
        )
        self.wait((frames + 0.5) / fps if frozen else (frames - 0.5) / fps, frozen_frame=frozen)

    def hold(self, until: float | None = None) -> None:
        """Wait until the scene has lasted ``until`` seconds (default: ``spec.duration``).

        Silent scenes are held automatically at the end; call this to hold earlier. No-op if
        the scene is already that long or no duration applies.
        """
        target = until if until is not None else self.spec.duration
        if target is not None:
            self.wait_seconds(target - self.renderer.time)

    def tear_down(self) -> None:
        """Hold silent scenes to ``spec.duration``; warn about beats that were never narrated."""
        if self.spec.silent:
            self.hold()
        narrated = {entry.beat_id for entry in self.beat_log}
        missing = [b.id for b in self.beats if b.id not in narrated]
        if missing:
            log.warning("scene '%s' never narrated beats: %s", self.spec.id, ", ".join(missing))
        super().tear_down()

    def timings(self) -> dict[str, Any]:
        """JSON-ready timings: scene id, total duration and the beat log."""
        return {
            "scene": self.spec.id,
            "duration": float(self.renderer.time),
            "beats": [
                {"id": t.beat_id, "start": t.start, "end": t.end, "text": t.text} for t in self.beat_log
            ],
        }

    # ----- frame -----------------------------------------------------------------------------

    @property
    def frame_width(self) -> float:
        """Width of the visible frame in Manim units (``config.frame_width``).

        vidgen sets the shorter side to 8 units with square pixels: 16:9 gives 14.22 x 8,
        9:16 (vertical variants) gives 8 x 14.22. Lay out relative to these values rather than
        assuming Manim's landscape defaults.
        """
        return float(config.frame_width)

    @property
    def frame_height(self) -> float:
        """Height of the visible frame in Manim units (``config.frame_height``)."""
        return float(config.frame_height)

    @property
    def is_portrait(self) -> bool:
        """True when the frame is taller than wide (e.g. a 1080x1920 vertical variant)."""
        return config.pixel_height > config.pixel_width

    # ----- drawing ---------------------------------------------------------------------------

    def text(self, s: str, size: str | float = "body", color: Any = "text", weight: str = NORMAL, **kwargs: Any) -> Text:
        """A ``Text`` in the theme font; ``size``/``color`` accept theme tokens or literal values."""
        return helpers.styled(Text, self.theme, s, size, color, weight, **kwargs)

    def markup(
        self, s: str, size: str | float = "body", color: Any = "text", weight: str = NORMAL, **kwargs: Any
    ) -> MarkupText:
        """A Pango ``MarkupText`` in the theme font (``<b>``, ``<sup>``, ``<span>``...)."""
        return helpers.styled(MarkupText, self.theme, s, size, color, weight, **kwargs)

    def clear_all(self, run_time: float = 0.6) -> None:
        """Fade out every mobject on screen."""
        if self.mobjects:
            self.play(*[FadeOut(m) for m in self.mobjects], run_time=run_time)
