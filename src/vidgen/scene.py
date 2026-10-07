"""``NarratedScene``: the base class of every scene type (DESIGN.md §5.1).

A scene is constructed with its config and the active project/theme injected::

    scene = SceneClass(spec, project, theme, audio=True)   # needs Manim's config set up
    scene.render()
    scene.timings()   # {"scene", "duration", "beats": [{"id", "start", "end", "text"}]}

Params validation does not need Manim to be configured: ``SceneClass.validate_params(raw)``.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, ClassVar, NamedTuple, Union

import av
from manim import DEFAULT_WAIT_TIME, NORMAL, Animation, FadeIn, MarkupText, Mobject, MovingCameraScene, Text, Wait, config
from pydantic import AfterValidator, AliasChoices, BaseModel, ConfigDict, GetJsonSchemaHandler, ValidationError, ValidationInfo

from vidgen import helpers, regions, runtime
from vidgen.actions import TARGET_NAME, ActionRunner, Target, match_names, plan_actions
from vidgen.capture import FrameCapture
from vidgen.layout import distribute
from vidgen.overlay_layer import OverlayLayer
from vidgen.overlays import Overlay, avoid, mobject_region, scene_overlays
from vidgen.config import BeatConfig, SceneConfig, SfxCue, validation_error_lines
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.sfx import AUTO_ACTION_SFX, SfxEvent, SoundLibrary
from vidgen.theme import Theme
from vidgen.videoplan import VideoPlan

log = logging.getLogger("vidgen.scene")


class SceneParams(BaseModel):
    """Base class for a scene type's ``Params`` model; unknown keys are an error.

    A docstring under a field (or ``Field(description=...)``) documents it; ``vidgen
    list-scenes --json`` shows it as the field's ``doc``. A nested model that also accepts a
    shorthand (e.g. a plain string, converted by a ``model_validator(mode="before")``) lists
    those types in ``also_accepts``, so ``list-scenes`` shows ``str | Item`` instead of ``Item``.
    """

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)
    #: Other input types this model is built from (shown by ``vidgen list-scenes``).
    also_accepts: ClassVar[tuple[type, ...]] = ()
    #: Whether the text in the frame's header band answers to both names, ``heading`` and
    #: ``title`` (with ``_size`` / ``_color``): a model with only one of a pair also accepts the
    #: other (:data:`HEADER_SYNONYMS`). Off for types whose ``title`` is their main text
    #: (``title``, ``chapter``, ``end_card``).
    header_synonyms: ClassVar[bool] = True

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if not cls.header_synonyms:
            return
        changed = False
        for a, b in HEADER_SYNONYMS:
            for name, other in ((a, b), (b, a)):
                field = cls.model_fields.get(name)
                if field is not None and other not in cls.model_fields and field.alias is None and field.validation_alias is None:
                    field.validation_alias = AliasChoices(name, other)
                    changed = True
        if changed:
            cls.model_rebuild(force=True)


#: Pairs of param names that mean the same in every scene type with a header band (the scene
#: types grew up with both: ``bullets`` has a ``heading``, the charts a ``title``).
HEADER_SYNONYMS: tuple[tuple[str, str], ...] = (("heading", "title"), ("heading_size", "title_size"), ("heading_color", "title_color"))



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


def _check_icon_name(value: str, info: ValidationInfo) -> str:
    from vidgen.icons import NAME_PATTERN, active_icons, resolve_icon, unknown_icon_message

    if not NAME_PATTERN.match(value):
        raise ValueError(f"invalid icon name {value!r} (letters, digits, '-' and '_')")
    if (info.context or {}).get("theme") is not None:
        icons = active_icons()
        if resolve_icon(value, icons) is None:
            raise ValueError(unknown_icon_message(value, icons))
    return value


class ThemeToken(NamedTuple):
    """Marker in ``ThemeColor``/``ThemeSize``/``IconName`` annotations: names resolved in the
    project (``kind`` is ``"color"``, ``"size"`` or ``"icon"``)."""

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
#: A ``Params`` field holding an icon name (built-in or the project's ``assets/icons``); checked
#: against the available icons by ``vidgen validate`` and when the scene is built.
IconName = Annotated[str, AfterValidator(_check_icon_name), ThemeToken("icon")]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def one_or_many(item: Any) -> Any:
    """A ``Params`` field type for a list that may also be written as a single item
    (``highlight: Lint`` means ``[Lint]``); the validated value is always a list."""
    return Annotated[Union[list[item], item], AfterValidator(_as_list)]


class BeatTiming(NamedTuple):
    """When a beat was narrated, in seconds from the start of the scene (``end = start + d``)."""

    beat_id: str
    start: float
    end: float
    text: str


class PlayRecord(NamedTuple):
    """One ``self.play(...)`` (``self.wait`` included) as the scene ran it: scene times
    ``start``/``end`` (s), the beat being narrated (``None`` outside ``narrate``), the
    animations' names, whether it only waited, and ``requested``: the run time the caller
    wanted when :meth:`NarratedScene.play_steps` had to shorten it to fit the beat."""

    start: float
    end: float
    beat: str | None
    animations: tuple[str, ...]
    wait: bool
    requested: float | None = None


def _animation_name(item: Any) -> str:
    """``FadeIn``, ``animate`` (``mobject.animate...``) or ``AnimationGroup(Write, FadeIn)``."""
    if isinstance(item, Animation):
        inner = getattr(item, "animations", None)
        name = type(item).__name__
        if inner:
            parts = list(dict.fromkeys(_animation_name(a) for a in inner))
            name += "(" + ", ".join(parts[:3]) + (", …" if len(parts) > 3 else "") + ")"
        return name
    if type(item).__name__ == "_AnimationBuilder":
        return "animate"
    return type(item).__name__


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


class NarratedScene(MovingCameraScene):
    """A Manim scene timed by narration.

    The camera can move (``self.camera.frame``, Manim's ``MovingCameraScene``; the ``zoom`` beat
    action uses it); it starts on the whole frame, so scenes that never move it render as with a
    static camera.

    Inside ``construct()``: ``self.spec`` (``SceneConfig``), ``self.params`` (validated
    ``Params`` instance, or a dict), ``self.beats``, ``self.theme``, ``self.project``.
    Subclasses may define ``class Params(SceneParams)`` to validate their params.

    ``audio=False`` renders without adding narration sounds; durations still come from the
    audio files, so timing is identical to a render with audio.

    ``capture`` (a :class:`~vidgen.capture.FrameCapture`, set by the worker for ``vidgen
    render --frames``) takes stills at the end of / during each beat; it only observes the
    frames written, so timing is unchanged. ``self.capture`` is ``None`` otherwise.

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
        capture: FrameCapture | None = None,
        **scene_kwargs: Any,
    ) -> None:
        self.spec = spec
        self.project = project if project is not None else runtime.current_project()
        if theme is None:
            active = runtime.has_context() and runtime.current_project() is self.project
            theme = runtime.current_theme() if active else Theme.for_format(self.project.config.theme, self.project.config.format)
        self.theme = theme
        self.params = type(self).parse_params(spec.params, scene_id=spec.id, theme=self.theme)
        problem = type(self).check_beat_count(len(spec.beats))
        if problem is not None:
            raise VidgenError(f"scene '{spec.id}': {problem}")
        self.beats: list[BeatConfig] = list(spec.beats)
        self._targets: list[Target] = []
        self._rest: dict[int, tuple[float, float]] = {}  # full opacity of target parts (shared)
        uses = plan_actions(spec.type, type(self), spec, self.params, self.theme)
        self._actions = ActionRunner(self, uses) if uses else None
        self.audio_enabled = audio
        self.beat_log: list[BeatTiming] = []
        #: Every ``play``/``wait`` in order (:class:`PlayRecord`); read by ``vidgen lint``.
        self.play_log: list[PlayRecord] = []
        #: Seconds each narrated beat's body took (before the wait to ``d + pad``); more than
        #: ``d + pad`` means its animations overran the narration.
        self.beat_busy: dict[str, float] = {}
        #: Seconds a silent scene's code took before being held to its ``duration``.
        self.silent_busy: float | None = None
        self._durations: dict[str, float] = {}
        self._current_beat: str | None = None
        self._requested: float | None = None
        #: Sound effects of the scene (:class:`~vidgen.sfx.SfxEvent`, scene times), in the order
        #: they were added; the worker stores them in the timings, the pipeline mixes them.
        self.sfx_log: list[SfxEvent] = []
        self._sounds: SoundLibrary | None = None
        super().__init__(**scene_kwargs)
        self.capture = capture
        if capture is not None:
            capture.attach(self)
            if spec.silent:
                length = max((spec.duration or 0.0) - self.outro, 1 / config.frame_rate)
                capture.begin_segment(None, round(length * config.frame_rate), include_end=True)
        #: The video's overlays drawn on this scene (DESIGN.md §41), or ``None`` without any.
        self.overlay_layer: OverlayLayer | None = None
        self._reserved: list[regions.Region] = []
        overlays = self._build_overlays()
        if overlays:
            self.overlay_layer = OverlayLayer(self, overlays)
            self.overlay_layer.attach()  # after the capture: stills and the layout dump see overlays
            for overlay, mob in zip(self.overlay_layer.overlays, self.overlay_layer.mobjects):
                box = mobject_region(mob) if overlay.reserves and mob is not None else None
                if box is not None:
                    self._reserved.append(box)
        if self.entrance_sfx is not None and self.project.config.sfx.auto:
            sound, gain = self.entrance_sfx
            self.sfx(sound, 0.0, gain=gain)
        for k, cue in enumerate(spec.sfx):
            params = cue.params.model_dump(exclude_none=True)
            self._add_sfx(cue.sound, cue.at, cue.gain, cue.pan, cue.align, params, f"sfx[{k}]")

    def _build_overlays(self) -> list[Overlay]:
        """The overlays of the project drawn on this scene (none without an ``overlays:``)."""
        cfg = self.project.config
        if not cfg.overlays and not any(isinstance(s.overlays, dict) for s in cfg.scenes):
            return []
        return scene_overlays(self.project, self.spec, self.theme, VideoPlan(self.project, int(config.frame_rate)))

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
        in it (it is passed to validators as ``info.context["theme"]``) and :data:`IconName`
        fields icons of the active project (or built-ins).
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
            lines = validation_error_lines(exc, ("params",), cls.params_model())
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
        if self.capture is not None:
            self.capture.begin_segment(b.id, round((d + self.pad) * config.frame_rate), include_end=False)
        self._current_beat = b.id
        if self._actions is not None:
            self._actions.start_beat(b.id, d, self.pad)
        try:
            yield d
            self.beat_busy[b.id] = float(self.renderer.time) - start
            self.wait_seconds(d + self.pad - (self.renderer.time - start))
            if self._actions is not None:
                self._actions.end_beat()
        finally:
            self._current_beat = None
        self.beat_log.append(BeatTiming(b.id, start, start + d, b.text))
        if self.capture is not None:
            self.capture.end_segment(b.id)

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
        takes longer than ``d`` (slots end at fixed times from the call's start, so a slot that a
        beat action lengthened is made up by the following waits; beat actions played in a wait
        leave the later steps their run time). A step is an animation, a list of animations
        played together,
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
        # a group that may animate (empty lists only wait); the time the later ones need is held
        # back from beat actions played in the waits, so the beat still ends on time
        animates = [any(isinstance(steps[k], Animation) or callable(steps[k]) or len(steps[k]) for k in g) for g in groups]
        begin = float(self.renderer.time)
        try:
            for n, group in enumerate(groups):
                anims: list[Animation] = []
                for k in group:
                    step = steps[k]
                    built = step() if callable(step) and not isinstance(step, Animation) else step
                    anims += [built] if isinstance(built, Animation) else list(built or [])
                if anims:
                    self._requested = cap if run_time < cap - 1e-9 else None
                    try:
                        self.play(*anims, run_time=run_time)
                    finally:
                        self._requested = None
                if self._actions is not None:  # Manim plays a run time as whole frames, rounded up
                    self._actions.held = math.ceil(run_time / frame - 1e-6) * frame * sum(animates[n + 1 :])
                self.wait_seconds(begin + (n + 1) * slot - self.renderer.time)
        finally:
            if self._actions is not None:
                self._actions.held = 0.0

    def play(self, *args: Any, **kwargs: Any) -> None:
        """Manim's ``play``, also recorded in :attr:`play_log` (scene times, beat, names)."""
        start = float(self.renderer.time)
        super().play(*args, **kwargs)
        frame = getattr(self.camera, "frame", None)
        if frame is not None and frame in self.mobjects and not frame.updaters:  # added by a camera move; never drawn
            self.remove(frame)
        waiting = bool(args) and all(isinstance(a, Wait) for a in args)
        self.play_log.append(
            PlayRecord(
                start,
                float(self.renderer.time),
                self._current_beat,
                tuple(_animation_name(a) for a in args),
                waiting,
                self._requested,
            )
        )

    def wait_seconds(self, seconds: float) -> None:
        """Wait ``seconds`` rounded to whole frames (no-op if that is zero frames).

        Unlike Manim's ``wait``, the number of frames written is exact, so scene lengths do not
        drift by a frame per wait. Beat actions due meanwhile are played inside the wait.
        """
        frames = round(seconds * config.frame_rate)
        if frames <= 0:
            return
        if self._actions is not None and self._actions.pending:
            self._actions.wait(frames)
        else:
            self._wait_frames(frames)

    def wait(self, duration: float = DEFAULT_WAIT_TIME, stop_condition: Callable[[], bool] | None = None, frozen_frame: bool | None = None) -> None:
        """Manim's ``wait``; inside a beat with actions due, they are played within it (rounded to
        whole frames)."""
        if stop_condition is None and self._actions is not None and self._actions.pending:
            self._actions.wait(round(duration * config.frame_rate))
            return
        super().wait(duration, stop_condition, frozen_frame)

    def _wait_frames(self, frames: int) -> None:
        """Write exactly ``frames`` frames of waiting (no actions)."""
        fps = config.frame_rate
        # Mirror Scene.should_update_mobjects: Manim writes int(t*fps) frames for a frozen wait
        # but ceil(t*fps) frames when it redraws every frame; ask for a time that gives `frames`.
        frozen = not (
            getattr(self, "always_update_mobjects", False)
            or getattr(self, "updaters", None)
            or any(m.has_time_based_updater() for m in self.get_mobject_family_members())
        )
        super().wait((frames + 0.5) / fps if frozen else (frames - 0.5) / fps, frozen_frame=frozen)

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
            self.silent_busy = float(self.renderer.time)
            self.hold()
        narrated = {entry.beat_id for entry in self.beat_log}
        missing = [b.id for b in self.beats if b.id not in narrated]
        if missing:
            log.warning("scene '%s' never narrated beats: %s", self.spec.id, ", ".join(missing))
        late = [f"{e.sound} at {e.time:.2f} s" for e in self.sfx_log if e.align == "start" and e.time >= self.renderer.time]
        if late:
            log.warning("scene '%s' lasts %.2f s; sound effects after its end play in the next scene: %s", self.spec.id, self.renderer.time, ", ".join(late))
        if self.capture is not None:
            self.capture.finish()
        super().tear_down()

    def timings(self) -> dict[str, Any]:
        """JSON-ready timings: scene id, total duration and the beat log (and ``sfx``, the
        :attr:`sfx_log`, when the scene has sound effects)."""
        data: dict[str, Any] = {
            "scene": self.spec.id,
            "duration": float(self.renderer.time),
            "beats": [
                {"id": t.beat_id, "start": t.start, "end": t.end, "text": t.text} for t in self.beat_log
            ],
        }
        if self.sfx_log:
            data["sfx"] = [event.to_json() for event in self.sfx_log]
        return data

    # ----- sound effects (DESIGN.md §47) -------------------------------------------------------

    #: ``(sound, gain in dB)`` played at the scene's start when the video sets ``sfx: {auto:
    #: true}`` (``chapter``: a whoosh); ``None``: nothing.
    entrance_sfx: ClassVar[tuple[str, float] | None] = None

    @property
    def sounds(self) -> SoundLibrary:
        """The sounds this scene can play: the built-ins and the project's ``assets/sfx``."""
        if self._sounds is None:
            self._sounds = SoundLibrary(self.project.root)
        return self._sounds

    def sfx(
        self, sound: str, at: float | None = None, *, gain: float = 0.0, pan: float = 0.0, align: str = "start", **params: float
    ) -> SfxEvent:
        """Play the sound effect ``sound`` at scene time ``at`` (seconds; default: now, i.e. with
        the next ``play``). ``gain`` in dB, ``pan`` -1 (left) to 1 (right), ``align="end"`` ends
        the sound at ``at`` instead of starting it there; ``params`` (``duration``, ``pitch``,
        ``intensity``) shape a built-in sound. Unknown sounds and bad values raise
        :class:`VidgenError`.

        Nothing is drawn and no time passes: the sound is recorded (:attr:`sfx_log`) and mixed
        into the video's sound by the render pipeline, sample-exact, unless rendering with
        ``--no-audio``.
        """
        time = float(self.renderer.time) if at is None else at
        return self._add_sfx(sound, time, gain, pan, align, params, "sfx")

    def _add_sfx(
        self, sound: str, time: float, gain: float, pan: float, align: str, params: Mapping[str, Any], where: str
    ) -> SfxEvent:
        try:
            cue = SfxCue.model_validate({"sound": sound, "at": time, "gain": gain, "pan": pan, "align": align, "params": dict(params)})
        except ValidationError as exc:
            lines = validation_error_lines(exc, (), SfxCue)
            raise VidgenError("\n".join([f"scene '{self.spec.id}' {where} '{sound}': invalid", *(f"  {x}" for x in lines)])) from None
        given = cue.params.model_dump(exclude_none=True)
        problems = self.sounds.problems(cue.sound, given)
        if problems:
            raise VidgenError(f"scene '{self.spec.id}' {where}: " + "; ".join(f"{key}: {message}" for key, message in problems))
        event = SfxEvent(round(cue.at, 6), cue.sound, cue.gain, cue.pan, cue.align, given, self._current_beat)
        self.sfx_log.append(event)
        return event

    def auto_sfx(self, action: str) -> None:
        """When the video sets ``sfx: {auto: true}``, play the automatic sound of the built-in
        action ``action`` now (:data:`vidgen.sfx.AUTO_ACTION_SFX`; none for other names)."""
        entry = AUTO_ACTION_SFX.get(action)
        if entry is not None and self.project.config.sfx.auto:
            sound, gain, params = entry
            self.sfx(sound, gain=gain, **params)

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

    #: Margins (Manim units) between the frame edge and the safe area (``vidgen.regions``
    #: defaults). The layout dump and ``vidgen lint``'s ``safe_area`` rule use the same values.
    margin_x: float = regions.MARGIN_X
    margin_y: float = regions.MARGIN_Y

    @property
    def safe_area(self) -> regions.Region:
        """The frame minus this scene's margins, as a :class:`~vidgen.regions.Region`, shrunk to
        stay clear of overlays drawn with ``reserve: true`` (DESIGN.md §41)."""
        area = regions.safe_area(self.margin_x, self.margin_y)
        for box in getattr(self, "_reserved", ()):
            area = avoid(area, box)
        return area

    @property
    def safe_width(self) -> float:
        """Frame width minus the side margins: the width content should stay within."""
        return self.safe_area.width

    @property
    def safe_height(self) -> float:
        """Frame height minus the top/bottom margins."""
        return self.safe_area.height

    def region(self, name: str, gap: float = regions.GAP) -> regions.Region:
        """A named region (``header``, ``body``, ``left``...) of this scene's safe area; see
        :func:`vidgen.regions.region`."""
        return regions.region(name, self.safe_area, gap)

    # ----- targets (per-beat actions, DESIGN.md §26) -----------------------------------------

    #: The target names this type registers, as documentation patterns (``item<N>``,
    #: ``bar:<label>``); shown by ``vidgen list-scenes``. Empty: the type has no targets.
    target_patterns: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """Every target name the scene registers for these (validated) params; ``vidgen
        validate`` checks the ``target:`` of beat actions against it. Default: none."""
        return []

    def target(
        self,
        names: str | Sequence[str],
        mobject: Mobject,
        *,
        entrance: Callable[[], Sequence[Animation]] | None = None,
        outline: Mobject | None = None,
        on_fill: Sequence[tuple[Mobject, Mobject]] = (),
    ) -> Target:
        """Register ``mobject`` as an action target under ``names`` (the first is its main name).

        Register targets before the beat whose actions use them, while the mobject has its full
        look (normally right after building the layout: ``dim`` and ``highlight`` measure "full
        opacity" from that moment). ``entrance`` builds the scene's own animations that bring it
        on screen (used by the ``reveal`` action and :meth:`entrance`; default ``FadeIn``);
        ``outline`` is what a ``highlight`` box surrounds (default: ``mobject``); ``on_fill``
        lists ``(text, shape)`` pairs of text written on a filled shape of the target, which
        ``dim`` and ``highlight`` recolour to stay readable on the shape (see ``Target.on_fill``).
        """
        names = (names,) if isinstance(names, str) else tuple(names)
        if not names:
            raise VidgenError(f"scene '{self.spec.id}': a target needs at least one name")
        for name in names:
            if not isinstance(name, str) or not TARGET_NAME.match(name):
                raise VidgenError(f"scene '{self.spec.id}': invalid target name {name!r} (use name, name3, name1.part2 or kind:label)")
        target = Target(names, mobject, entrance, outline, self._rest, tuple(on_fill))
        self._targets.append(target)
        return target

    @property
    def targets(self) -> list[Target]:
        """The registered targets, in registration order."""
        return list(self._targets)

    def find_targets(self, pattern: str) -> list[Target]:
        """The targets a name or ``*``/``?`` pattern selects (``title`` / ``heading`` stand for
        each other when the scene has only one of them)."""
        wanted = set(match_names(pattern, [n for t in self._targets for n in t.names]))
        return [t for t in self._targets if wanted.intersection(t.names)]

    def on_screen_parts(self, target: Target | Mobject) -> list[Mobject]:
        """The largest parts of the target that are on screen (its mobject itself when it was
        added whole; otherwise its submobjects that were, e.g. a bar and its labels)."""
        mob = target.mobject if isinstance(target, Target) else target
        present = {id(m) for m in self.get_mobject_family_members()}

        def walk(m: Mobject) -> list[Mobject]:
            if id(m) in present:
                return [m]
            return [part for sub in m.submobjects for part in walk(sub)]

        return walk(mob)

    def is_shown(self, target: Target | str) -> bool:
        """Whether (a part of) the target is on screen."""
        found = self.find_targets(target) if isinstance(target, str) else [target]
        return any(self.on_screen_parts(t) for t in found)

    def entrance(self, target: Target | str) -> list[Animation]:
        """The animations that bring the target on screen, or ``[]`` when it already is (so a
        target an action revealed early is not revealed twice by the scene's own steps)."""
        found = self.find_targets(target) if isinstance(target, str) else [target]
        anims: list[Animation] = []
        for t in found:
            if not self.is_shown(t):
                anims += list(t.entrance()) if t.entrance is not None else [FadeIn(t.mobject)]
        return anims

    def _apply_now(self, animations: Sequence[Animation]) -> None:
        """Jump ``animations`` to their end state without writing frames."""
        self.add_mobjects_from_animations(list(animations))
        for anim in animations:
            anim._setup_scene(self)
            anim.begin()
        for anim in animations:
            anim.finish()
            anim.clean_up_from_scene(self)

    # ----- drawing ---------------------------------------------------------------------------

    def text(
        self, s: str, size: str | float = "body", color: Any = "text", weight: str = NORMAL, *, role: str | None = None, **kwargs: Any
    ) -> Text:
        """A ``Text`` in the theme font; ``size``/``color`` accept theme tokens or literal values,
        ``role`` picks the theme's family for a font role (``heading``, ``quote``, ``code``...)."""
        return helpers.styled(Text, self.theme, s, size, color, weight, role=role, **kwargs)

    def markup(
        self, s: str, size: str | float = "body", color: Any = "text", weight: str = NORMAL, *, role: str | None = None, **kwargs: Any
    ) -> MarkupText:
        """A Pango ``MarkupText`` in the theme font (``<b>``, ``<sup>``, ``<span>``...); ``role`` as
        for :meth:`text`."""
        return helpers.styled(MarkupText, self.theme, s, size, color, weight, role=role, **kwargs)

    def clear_all(self, run_time: float = 0.6) -> None:
        """Fade out every mobject on screen (vector mobjects without copying them: see
        :class:`vidgen.helpers.Fade`)."""
        if self.mobjects:
            self.play(*[helpers.fade_out(m) for m in self.mobjects], run_time=run_time)
