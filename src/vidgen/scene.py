"""``NarratedScene``: the base class of every scene type (DESIGN.md §5.1).

A scene is constructed with its config and the active project/theme injected::

    scene = SceneClass(spec, project, theme, audio=True)   # needs Manim's config set up
    scene.render()
    scene.timings()   # {"scene", "duration", "beats": [{"id", "start", "end", "text"}]}

Params validation does not need Manim to be configured: ``SceneClass.validate_params(raw)``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, NamedTuple, Union

import av
from manim import NORMAL, Animation, FadeOut, MarkupText, Scene, Text, config
from pydantic import AfterValidator, BaseModel, ConfigDict, GetJsonSchemaHandler, ValidationError, ValidationInfo

from vidgen import helpers, runtime
from vidgen.layout import distribute
from vidgen.config import BeatConfig, SceneConfig, validation_error_lines
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.theme import Theme

log = logging.getLogger("vidgen.scene")


class SceneParams(BaseModel):
    """Base class for a scene type's ``Params`` model; unknown keys are an error.

    A docstring under a field (or ``Field(description=...)``) documents it; ``vidgen
    list-scenes --json`` shows it as the field's ``doc``.
    """

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)


_HEX = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")


def _check_theme_color(value: str, info: ValidationInfo) -> str:
    if value.startswith("#"):
        if not _HEX.match(value):
            raise ValueError(f"invalid hex color {value!r} (use #RGB, #RRGGBB or #RRGGBBAA)")
        return value
    theme = (info.context or {}).get("theme")
    if theme is not None and value not in theme.colors:
        raise ValueError(f"unknown theme color '{value}'; known colors: {', '.join(sorted(theme.colors))}")
    return value


def _check_theme_size(value: str | float, info: ValidationInfo) -> str | float:
    if isinstance(value, str):
        theme = (info.context or {}).get("theme")
        if theme is not None and value not in theme.sizes:
            raise ValueError(f"unknown theme size '{value}'; known sizes: {', '.join(sorted(theme.sizes))}")
    elif value <= 0:
        raise ValueError("size must be positive")
    return value


class ThemeToken(NamedTuple):
    """Marker in ``ThemeColor``/``ThemeSize`` annotations (``kind`` is ``"color"`` or ``"size"``)."""

    kind: str

    def __get_pydantic_json_schema__(self, core_schema: Any, handler: GetJsonSchemaHandler) -> dict[str, Any]:
        """Mark the field's JSON Schema with ``x-vidgen-theme: <kind>`` (see ``vidgen.schema``)."""
        schema = handler(core_schema)
        schema["x-vidgen-theme"] = self.kind
        return schema


#: A ``Params`` field holding a color: a theme token (``"primary"``) or ``#hex``. Tokens are
#: checked against the project's theme by ``vidgen validate`` and when the scene is built.
ThemeColor = Annotated[str, AfterValidator(_check_theme_color), ThemeToken("color")]
#: A ``Params`` field holding a font size: a theme token (``"body"``) or a number of points.
ThemeSize = Annotated[Union[str, float], AfterValidator(_check_theme_size), ThemeToken("size")]


class BeatTiming(NamedTuple):
    """When a beat was narrated, in seconds from the start of the scene (``end = start + d``)."""

    beat_id: str
    start: float
    end: float
    text: str


def audio_duration(path: Path) -> float:
    """Length of an audio file in seconds: its decoded samples / sample rate (read with PyAV).

    Decoding (rather than reading the container's duration) gives the same answer with every
    PyAV/FFmpeg version: older ones (PyAV 13, which Manim 0.19 pins on Python 3.10) include the
    MP3 encoder padding in the container duration, ~25-50 ms more per file.
    """
    try:
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            samples = 0
            rate = stream.rate or 0
            for frame in container.decode(stream):
                samples += frame.samples
                rate = frame.sample_rate or rate
            if not samples or not rate:
                raise ValueError("no audio samples")
            return samples / rate
    except (OSError, ValueError, IndexError, av.error.FFmpegError) as exc:
        raise VidgenError(f"cannot read audio file {path}: {exc}") from None


def _beats(k: int) -> str:
    return f"{k} beat" if k == 1 else f"{k} beats"


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
        self.params = type(self).parse_params(spec.params, scene_id=spec.id, theme=self.theme)
        problem = type(self).check_beat_count(len(spec.beats))
        if problem is not None:
            raise VidgenError(f"scene '{spec.id}': {problem}")
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
    def validate_params(cls, params: Mapping[str, Any], theme: Theme | None = None) -> SceneParams | dict[str, Any]:
        """Validate raw params; raises ``pydantic.ValidationError``. No Manim setup needed.

        With ``theme``, :data:`ThemeColor` / :data:`ThemeSize` fields must name tokens that exist
        in it (it is passed to validators as ``info.context["theme"]``).
        """
        model = cls.params_model()
        if model is None:
            return dict(params)
        return model.model_validate(dict(params), context={"theme": theme})

    @classmethod
    def parse_params(
        cls, params: Mapping[str, Any], scene_id: str = "?", theme: Theme | None = None
    ) -> SceneParams | dict[str, Any]:
        """Like :meth:`validate_params` but raises a readable :class:`VidgenError`."""
        try:
            return cls.validate_params(params, theme)
        except ValidationError as exc:
            lines = validation_error_lines(exc, ("params",))
            raise VidgenError("\n".join([f"scene '{scene_id}': invalid params", *(f"  {x}" for x in lines)])) from None

    @classmethod
    def validate_project(cls, params: Any, project: Project) -> list[str]:
        """Project-aware checks run by ``vidgen validate`` after params validated (no Manim setup).

        Override to check things a ``Params`` model cannot see, e.g. that an asset file exists.
        ``params`` is the validated ``Params`` instance (or dict). Return one message per
        problem, starting with the param name (``"path: file not found: assets/x.png"``); an
        empty list means no problems. Use the logger for warnings. Call ``super()`` to keep the
        checks of a parent class.
        """
        return []

    #: How many beats the scene type narrates: ``None`` (any number, the default), an ``int``
    #: (exactly that many) or ``(min, max)`` (``max`` may be ``None``). Checked by
    #: ``vidgen validate`` and when the scene is built; set it on types that narrate fixed
    #: beat indices (``self.narrate(0)``, ``self.narrate(1)``...).
    beat_count: int | tuple[int, int | None] | None = None

    @classmethod
    def beat_count_text(cls) -> str | None:
        """:attr:`beat_count` in words (``"exactly 2 beats"``, ``"at least 1 beat"``,
        ``"2 to 4 beats"``), or ``None`` when any number of beats is accepted."""
        spec = cls.beat_count
        if spec is None:
            return None
        lo, hi = (spec, spec) if isinstance(spec, int) else spec
        if lo == hi:
            return f"exactly {_beats(lo)}"
        if hi is None:
            return f"at least {_beats(lo)}"
        return f"{lo} to {hi} beats"

    @classmethod
    def check_beat_count(cls, n: int) -> str | None:
        """Why ``n`` beats do not fit :attr:`beat_count` (``"needs exactly 2 beats, got 3"``),
        or ``None`` when they do."""
        spec = cls.beat_count
        if spec is None:
            return None
        lo, hi = (spec, spec) if isinstance(spec, int) else spec
        if lo <= n and (hi is None or n <= hi):
            return None
        return f"needs {cls.beat_count_text()}, got {n}"

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

    #: Seconds of fade-out added by :meth:`finish` (built-in scenes use 0.5).
    outro: float = 0.0

    def timeline(self) -> Iterator[tuple[int, float]]:
        """Like :meth:`narrate_all` but yields ``(index, d)`` and also works for silent scenes.

        A silent scene yields one step ``(0, duration - outro)`` and holds until that time has
        passed, so the same ``construct`` code serves narrated and silent scenes; call
        :meth:`finish` afterwards to fade out within the scene's duration.
        """
        if self.beats:
            for i in range(len(self.beats)):
                with self.narrate(i) as d:
                    yield i, d
            return
        start = float(self.renderer.time)
        d = max((self.spec.duration or 0.0) - self.outro, 1 / config.frame_rate)
        yield 0, d
        self.wait_seconds(d - (self.renderer.time - start))

    def reveal(
        self,
        steps: Sequence[Animation | Sequence[Animation] | Callable[[], Any]],
        fraction: float = 0.7,
        cap: float = 1.2,
    ) -> None:
        """Narrate the whole scene, revealing ``steps`` beat by beat.

        Steps are assigned to beats with :func:`~vidgen.layout.distribute` (step ``i`` at beat
        ``i``; more steps than beats are spread evenly; extra beats hold) and each beat's steps
        are played with :meth:`play_steps`. Works for silent scenes (one step slot). Does not
        fade out: call :meth:`finish` afterwards.
        """
        plan = distribute(len(steps), len(self.beats))
        for i, d in self.timeline():
            self.play_steps(d, [steps[k] for k in plan[i]], fraction=fraction, cap=cap)

    def finish(self) -> None:
        """Fade out everything over :attr:`outro` seconds (no-op when ``outro`` is 0)."""
        if self.outro > 0:
            self.clear_all(run_time=self.outro)

    def play_steps(
        self,
        d: float,
        steps: Sequence[Animation | Sequence[Animation] | Callable[[], Any]],
        fraction: float = 0.7,
        cap: float = 1.2,
    ) -> None:
        """Spread ``steps`` evenly over ``d`` seconds (typically a beat's duration).

        Each step gets a slot of ``d / len(steps)`` seconds; its animations run for
        ``min(cap, fraction * slot)`` and the rest of the slot is waited, so the whole call never
        takes longer than ``d``. A step is an animation, a list of animations played together,
        or a callable returning either (built lazily, after the previous steps ran); a step
        that is an empty list just waits its slot. When ``d`` is too short for one frame per
        step, consecutive steps are merged and played together.
        """
        if not steps:
            return
        frame = 1 / config.frame_rate
        groups = distribute(len(steps), min(len(steps), max(1, int(d / frame + 1e-9))))
        slot = d / len(groups)
        run_time = max(min(cap, fraction * slot), frame)
        for group in groups:
            start = float(self.renderer.time)
            anims: list[Animation] = []
            for k in group:
                step = steps[k]
                built = step() if callable(step) and not isinstance(step, Animation) else step
                anims += [built] if isinstance(built, Animation) else list(built or [])
            if anims:
                self.play(*anims, run_time=run_time)
            self.wait_seconds(slot - (self.renderer.time - start))

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

    #: Margins (Manim units) between the frame edge and the safe area used by built-in layouts.
    margin_x: float = 0.6
    margin_y: float = 0.5

    @property
    def safe_width(self) -> float:
        """Frame width minus the side margins: the width content should stay within."""
        return self.frame_width - 2 * self.margin_x

    @property
    def safe_height(self) -> float:
        """Frame height minus the top/bottom margins."""
        return self.frame_height - 2 * self.margin_y

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
