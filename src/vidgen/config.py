"""Pydantic v2 models for ``video.yaml`` (see DESIGN.md §4).

These models validate *structure* only. Whether a scene ``type`` is registered and whether its
``params`` match the scene's ``Params`` model is checked later, once extensions are loaded.

Use :func:`parse_config` to turn a raw mapping into a :class:`VideoConfig`; it converts pydantic
errors into a readable :class:`~vidgen.errors.VidgenError`.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    PositiveFloat,
    PositiveInt,
    PrivateAttr,
    ValidationError,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from vidgen.errors import Problem, VidgenError

ID_PATTERN = r"^[A-Za-z0-9_]+$"
HEX_COLOR_PATTERN = r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$"

Identifier = Annotated[str, Field(pattern=ID_PATTERN)]
HexColor = Annotated[str, Field(pattern=HEX_COLOR_PATTERN)]
#: A positive font size (pydantic would put a non-standard ``gt`` into the JSON Schema of the union).
Size = Annotated[int | float, Field(gt=0), WithJsonSchema({"type": "number", "exclusiveMinimum": 0})]
#: A font role's family: a token (``sans``, ``serif``, ``mono``) or a font family name.
FontChoice = Annotated[str, Field(min_length=1)]
#: JSON Schema hint for even pixel sizes (the check itself is ``FormatConfig._even``).
_EVEN = {"multipleOf": 2}


class _Strict(BaseModel):
    """Base for structural models: unknown keys are an error (typo protection)."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)


class FormatConfig(_Strict):
    """Resolution and frame rate of a render."""

    width: PositiveInt = Field(default=1920, json_schema_extra=_EVEN)
    """Width in pixels (even)."""
    height: PositiveInt = Field(default=1080, json_schema_extra=_EVEN)
    """Height in pixels (even)."""
    fps: PositiveInt = 30
    """Frames per second."""

    @field_validator("width", "height")
    @classmethod
    def _even(cls, value: int) -> int:
        # H.264 in yuv420p needs even sizes; Manim's encoder crashes on odd ones.
        if value % 2:
            raise ValueError(f"must be an even number of pixels (got {value}; H.264 video needs even sizes)")
        return value


def _preview_format() -> FormatConfig:
    return FormatConfig(width=854, height=480, fps=15)


class ThemeConfig(_Strict):
    """Theme values from the config.

    Only the values written in the config are stored here (unset values are ``None``/empty);
    :class:`vidgen.theme.Theme` merges them over the preset and the defaults.
    """

    preset: Identifier | None = None
    """Theme preset (built-in: see `vidgen list-themes`, or a project preset); values set here win over it."""
    background: HexColor | None = None
    """Background color (hex); default: the preset's, else #0E1116."""
    font: str | None = Field(default=None, min_length=1)
    """Sans font family (body text and roles without their own); default: the preset's, else Inter (bundled)."""
    font_serif: str | None = Field(default=None, min_length=1)
    """Serif font family (font role token `serif`); default: the preset's, else Source Serif 4 (bundled)."""
    font_mono: str | None = Field(default=None, min_length=1)
    """Monospace font family (token `mono`, code listings); default: the preset's, else JetBrains Mono NL (bundled)."""
    fonts: dict[Identifier, FontChoice] = Field(default_factory=dict)
    """Font per role (heading, quote, quote_mark, code, body...): sans, serif, mono or a family name; merged over the preset's."""
    code_style: str | None = None
    """Pygments style of code listings; default: the preset's, else github-dark."""
    colors: dict[Identifier, HexColor] = Field(default_factory=dict)
    """Color tokens (name: hex) merged over the defaults; projects may add any name."""
    palette: list[HexColor] | None = Field(default=None, min_length=1)
    """Ordered series colors (charts, groups); replaces the default palette."""
    sizes: dict[Identifier, Size] = Field(default_factory=dict)
    """Font size tokens (name: points) merged over the defaults; projects may add any name."""
    scale: Literal["compact", "standard", "large", "auto"] | None = None
    """Type scale (the six built-in sizes); default: the preset's, else auto (large in portrait video, else standard)."""

    @field_validator("code_style")
    @classmethod
    def _known_style(cls, value: str | None) -> str | None:
        if value is not None:
            from vidgen.presets import check_code_style

            check_code_style(value)
        return value


class VoiceSettings(_Strict):
    """ElevenLabs ``voice_settings``."""

    stability: float = Field(default=0.55, ge=0, le=1)
    """ElevenLabs stability (0-1)."""
    similarity_boost: float = Field(default=0.75, ge=0, le=1)
    """ElevenLabs similarity boost (0-1)."""
    style: float = Field(default=0.0, ge=0, le=1)
    """ElevenLabs style exaggeration (0-1)."""
    use_speaker_boost: bool = True
    """ElevenLabs speaker boost."""


class VoiceConfig(_Strict):
    """Text-to-speech voice. Only the ElevenLabs provider exists for now."""

    provider: Literal["elevenlabs"] = "elevenlabs"
    """TTS provider; only elevenlabs."""
    voice_id: str = Field(default="nPczCjzI2devNBz1zQrb", min_length=1)
    """ElevenLabs voice id."""
    model_id: str = Field(default="eleven_multilingual_v2", min_length=1)
    """ElevenLabs model id."""
    output_format: str = Field(default="mp3_44100_128", min_length=1)
    """ElevenLabs output format."""
    settings: VoiceSettings = Field(default_factory=VoiceSettings)
    """ElevenLabs voice_settings."""
    context: bool = True
    """Send the neighbouring beats' text for continuous intonation."""


class NarrationConfig(_Strict):
    """Timing of narrated beats."""

    pad: float = Field(default=0.35, ge=0)
    """Seconds of silence after each beat."""
    words_per_second: PositiveFloat = 2.6
    """Speech rate used to estimate a beat's duration when it has no audio yet."""


#: ``vidgen lint`` rule names (DESIGN.md §16). :class:`LintRules` has one field per name and
#: :mod:`vidgen.lint` one rule per name (a test keeps the three in sync).
LINT_RULES: tuple[str, ...] = (
    "off_frame",
    "safe_area",
    "text_overlap",
    "covered_text",
    "min_font",
    "contrast",
    "max_words",
    "narration_speed",
    "dead_air",
    "animation_overrun",
    "rushed_animation",
)
RuleName = Literal[
    "off_frame",
    "safe_area",
    "text_overlap",
    "covered_text",
    "min_font",
    "contrast",
    "max_words",
    "narration_speed",
    "dead_air",
    "animation_overrun",
    "rushed_animation",
]
#: Severity of a lint finding; ``off`` disables a rule.
Severity = Literal["error", "warning", "info", "off"]
#: A fraction of the frame's shorter side (its height for landscape video).
Fraction = Annotated[float, Field(gt=0, lt=1)]


class RuleConfig(_Strict):
    """Settings every lint rule has."""

    severity: Severity | None = None
    """Severity of all this rule's findings (error, warning, info), or off; default: the rule's own."""


class OffFrameRule(RuleConfig):
    """``off_frame``: an object cut off by the frame edge."""

    tolerance: Fraction = 0.004
    """How far (fraction of the frame's shorter side) an object may cross the edge unflagged."""


class SafeAreaRule(RuleConfig):
    """``safe_area``: text inside the frame but outside the safe area (the scene's margins)."""

    tolerance: Fraction = 0.01
    """How far (fraction of the frame's shorter side) text may cross the safe area unflagged."""


class TextOverlapRule(RuleConfig):
    """``text_overlap``: two texts whose boxes overlap."""

    min_overlap: Fraction = 0.1
    """Overlap (fraction of the smaller box's area) from which two texts count as overlapping."""


class CoveredTextRule(RuleConfig):
    """``covered_text``: a shape or image drawn on top of text."""

    min_covered: Fraction = 0.02
    """Part of the middle of the text's box that must show the shape's colour to be reported."""


class MinFontRule(RuleConfig):
    """``min_font``: text too small for the frame (cap height, fraction of the shorter side)."""

    min_size: Fraction = 0.025
    """Warning below this cap height (0.025: 12 px at 480p, 27 px at 1080p)."""
    error_size: Fraction = 0.018
    """Error below this cap height (0.018: 8.6 px at 480p, 19.4 px at 1080p)."""

    @model_validator(mode="after")
    def _ordered(self) -> MinFontRule:
        if self.error_size > self.min_size:
            raise ValueError("error_size must not be larger than min_size")
        return self


class ContrastRule(RuleConfig):
    """``contrast``: WCAG contrast ratio of text against what is behind it."""

    min_ratio: float = Field(default=4.5, ge=1, le=21)
    """Minimum ratio for normal text (WCAG AA: 4.5)."""
    large_ratio: float = Field(default=3.0, ge=1, le=21)
    """Minimum ratio for large text (WCAG AA: 3)."""
    large_size: Fraction = 0.045
    """Cap height (fraction of the shorter side) from which text counts as large."""
    dimmed_ratio: float = Field(default=2.0, ge=1, le=21)
    """Minimum ratio for text faded on purpose (opacity below 1, e.g. a previous bullet)."""


class MaxWordsRule(RuleConfig):
    """``max_words``: too many words on screen at once."""

    max_words: PositiveInt = 40
    """Most words of visible text (not code or math) in one still."""


class NarrationSpeedRule(RuleConfig):
    """``narration_speed``: a beat spoken too fast or too slow (spoken words per second)."""

    min_rate: PositiveFloat = 1.8
    """Slowest acceptable rate in words per second (1.8 = 108 words a minute)."""
    max_rate: PositiveFloat = 3.5
    """Fastest acceptable rate in words per second (3.5 = 210 words a minute)."""
    min_words: PositiveInt = 5
    """Beats with fewer spoken words are not checked (their rate is mostly pauses)."""

    @model_validator(mode="after")
    def _ordered(self) -> NarrationSpeedRule:
        if self.min_rate >= self.max_rate:
            raise ValueError("min_rate must be smaller than max_rate")
        return self


class DeadAirRule(RuleConfig):
    """``dead_air``: nothing on screen changes for too long."""

    max_seconds: PositiveFloat = 6.0
    """Longest acceptable stretch without any visual change, in seconds."""
    min_change: Fraction = 0.0002
    """Part of the frame that must change between two frames to count as a change."""


class AnimationOverrunRule(RuleConfig):
    """``animation_overrun``: a beat's animations take longer than its narration (+ pad)."""

    tolerance: float = Field(default=0.1, ge=0)
    """Seconds a beat may run past its narration and pad unflagged."""


class RushedAnimationRule(RuleConfig):
    """``rushed_animation``: animations squeezed to fit a beat that is too short for them."""

    min_run_time: PositiveFloat = 0.5
    """Shortest acceptable run time (seconds) of an animation `play_steps` had to shorten."""


class LintRules(_Strict):
    """Per-rule settings of ``vidgen lint``."""

    off_frame: OffFrameRule = Field(default_factory=OffFrameRule)
    """Objects cut off by the frame edge (default: error for text, warning for other objects)."""
    safe_area: SafeAreaRule = Field(default_factory=SafeAreaRule)
    """Text outside the safe area (default: warning)."""
    text_overlap: TextOverlapRule = Field(default_factory=TextOverlapRule)
    """Overlapping texts (default: error)."""
    covered_text: CoveredTextRule = Field(default_factory=CoveredTextRule)
    """Shapes or images drawn over text (default: warning)."""
    min_font: MinFontRule = Field(default_factory=MinFontRule)
    """Text too small (default: warning, error below error_size)."""
    contrast: ContrastRule = Field(default_factory=ContrastRule)
    """Low text contrast (default: warning)."""
    max_words: MaxWordsRule = Field(default_factory=MaxWordsRule)
    """Too many words on screen (default: warning)."""
    narration_speed: NarrationSpeedRule = Field(default_factory=NarrationSpeedRule)
    """Narration too fast or too slow (default: warning; info for beats without audio)."""
    dead_air: DeadAirRule = Field(default_factory=DeadAirRule)
    """No visual change for too long (default: warning)."""
    animation_overrun: AnimationOverrunRule = Field(default_factory=AnimationOverrunRule)
    """Animations running past the narration (default: warning)."""
    rushed_animation: RushedAnimationRule = Field(default_factory=RushedAnimationRule)
    """Animations shortened to fit a too short beat (default: warning)."""


class LintConfig(_Strict):
    """The optional ``lint:`` section: thresholds and severities of ``vidgen lint``."""

    fail_on: Literal["error", "warning", "info", "never"] = "error"
    """Lowest severity that makes `vidgen lint` fail (exit code 1); never: always exit 0."""
    min_opacity: float = Field(default=0.1, ge=0, le=1)
    """Objects fainter than this are ignored by every rule (the end of a fade)."""
    rules: LintRules = Field(default_factory=LintRules)
    """Per-rule settings (severity and thresholds)."""


class LintIgnore(_Strict):
    """A ``lint_ignore`` entry: skip a rule's findings in this scene, optionally only some."""

    rule: RuleName | Literal["all"]
    """Rule name, or all."""
    object: str | None = None
    """Only findings about objects whose name, path or text matches this pattern (* and ? wildcards)."""
    beat: Identifier | None = None
    """Only findings at this beat's end."""


#: Keys every action has; any other key of an action is an option of that action type.
ACTION_KEYS = ("action", "target", "at", "until", "run_time")
#: A target name or pattern: ``item3``, ``bar:Preview 480p``, ``bar*`` (``*``/``?`` wildcards).
TargetPattern = Annotated[str, Field(min_length=1)]


def _unshorten(data: dict[str, Any], name: str) -> dict[str, Any]:
    return {"action": name, "target": data[name], **{k: v for k, v in data.items() if k != name}}


class ActionConfig(BaseModel):
    """A per-beat action (DESIGN.md §26): ``{action: NAME, target: TARGET, at, until, run_time,
    ...options}`` or the shorthand ``{NAME: TARGET, ...options}`` (the action name first).

    Which actions exist, their options and the scene's targets depend on the registered action
    and scene types, so they are checked by ``vidgen validate`` (``vidgen.actions``), not here.
    """

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)

    action: Identifier
    """Action type: reveal, dim, highlight, or a project action (`vidgen list-scenes`)."""
    target: TargetPattern | list[TargetPattern] | None = Field(default=None, min_length=1)
    """Target name(s) of the scene (item3, bar:<label>, ...); * and ? match several."""
    at: float = Field(default=0.0, ge=0, lt=1)
    """When in the beat, as a fraction of its narration (0 = start); the action waits for the
    scene's own animation running then."""
    until: Identifier | None = None
    """A later beat of the scene at whose start the action is undone (dim, highlight)."""
    run_time: PositiveFloat | None = None
    """Seconds the action's animation takes (default: the action's own); shortened to fit the beat."""

    _shorthand: dict[str, Any] | None = PrivateAttr(default=None)

    @model_validator(mode="wrap")
    @classmethod
    def _from_shorthand(cls, data: Any, handler: ModelWrapValidatorHandler[ActionConfig]) -> ActionConfig:
        """``{NAME: TARGET, ...options}`` → ``{action: NAME, target: TARGET, ...options}``.

        ``NAME`` is the first key other than the common keys; :meth:`resolved` corrects the
        choice once the registered actions are known (for configs whose keys a tool sorted).
        """
        if not isinstance(data, dict) or "action" in data:
            return handler(data)
        names = [k for k in data if not (isinstance(k, str) and k in ACTION_KEYS)]
        if not names or not isinstance(names[0], str):
            keys = ", ".join(map(str, data)) or "none"
            raise ValueError(
                "an action is {action: NAME, target: TARGET, ...options} or the shorthand "
                f"{{NAME: TARGET, ...options}} (got keys: {keys}; no action name)"
            )
        if "target" in data:
            raise ValueError(f"the shorthand {{{names[0]}: TARGET}} already gives the target; remove 'target'")
        model = handler(_unshorten(data, names[0]))
        model._shorthand = dict(data)
        return model

    def resolved(self, known: Collection[str]) -> ActionConfig:
        """This action, or — for a shorthand whose first key is not a known action but exactly
        one other key is (keys sorted by a tool) — the action that key names."""
        if self._shorthand is None or self.action in known:
            return self
        names = [k for k in self._shorthand if k in known and k not in ACTION_KEYS]
        if len(names) != 1:
            return self
        return ActionConfig.model_validate(_unshorten(self._shorthand, names[0]))

    @property
    def options(self) -> dict[str, Any]:
        """The action-specific options (every key other than :data:`ACTION_KEYS`)."""
        return dict(self.model_extra or {})

    def targets(self) -> list[str]:
        """``target`` as a list (empty when there is none)."""
        if self.target is None:
            return []
        return [self.target] if isinstance(self.target, str) else list(self.target)

    def describe(self) -> str:
        """``highlight item3`` (for messages)."""
        return " ".join([self.action, *self.targets()])


class BeatConfig(_Strict):
    """One narrated sentence/paragraph. ``id`` is filled in by :class:`SceneConfig` if omitted."""

    id: Identifier
    """Unique in the whole video (names audio/<id>.mp3); default <scene id>_b<n> (1-based)."""
    text: str = Field(min_length=1)
    """What the narrator says; also the subtitle."""
    actions: list[ActionConfig] = Field(default_factory=list)
    """Per-beat actions on the scene's targets (reveal, dim, highlight, ...), run during this beat."""

    def estimated_duration(self, words_per_second: float) -> float:
        """Speech duration estimated from the word count (no padding)."""
        return len(self.text.split()) / words_per_second


class SceneConfig(_Strict):
    """A scene: a registered scene ``type`` plus its params and narrated beats.

    A scene normally has at least one beat. A *silent* scene has ``beats: []`` (or no ``beats``
    key) and must then give ``duration`` in seconds; ``duration`` is not allowed on narrated
    scenes, whose length comes from their audio.
    """

    id: Identifier
    """Scene id (letters, digits, _), unique."""
    type: Identifier
    """Scene type: a built-in or project extension type (`vidgen list-scenes`)."""
    params: dict[str, Any] = Field(default_factory=dict)
    """Parameters of the scene type."""
    beats: list[BeatConfig] = Field(default_factory=list)
    """Narrated beats in order; each animation lasts as long as its audio plus narration.pad."""
    duration: PositiveFloat | None = None
    """Seconds; required on a silent scene (no beats), not allowed on a scene with beats."""
    lint_ignore: list[RuleName | Literal["all"] | LintIgnore] = Field(default_factory=list)
    """`vidgen lint` findings to skip in this scene: rule names, or {rule, object, beat} filters."""

    @model_validator(mode="before")
    @classmethod
    def _default_beat_ids(cls, data: Any) -> Any:
        """Give beats without an ``id`` the id ``f"{scene_id}_b{n}"`` (1-based)."""
        if not isinstance(data, dict):
            return data
        scene_id = data.get("id")
        beats = data.get("beats")
        if not isinstance(scene_id, str) or not isinstance(beats, list):
            return data
        filled = []
        for n, beat in enumerate(beats, start=1):
            if isinstance(beat, dict) and beat.get("id") is None:
                beat = {**beat, "id": f"{scene_id}_b{n}"}
            filled.append(beat)
        return {**data, "beats": filled}

    @model_validator(mode="after")
    def _check_duration(self) -> SceneConfig:
        if not self.beats and self.duration is None:
            raise ValueError("a scene without beats (silent scene) needs a 'duration' in seconds")
        if self.beats and self.duration is not None:
            raise ValueError("'duration' is only allowed on silent scenes (scenes without beats)")
        beat_ids = {beat.id for beat in self.beats}
        order = [beat.id for beat in self.beats]
        for j, beat in enumerate(self.beats):
            for action in beat.actions:
                if action.until is not None and action.until not in order[j + 1 :]:
                    raise ValueError(
                        f"beats[{j}] action '{action.describe()}': until '{action.until}' is not a later beat of "
                        f"scene '{self.id}' (later beats: {', '.join(order[j + 1:]) or 'none'})"
                    )
        for entry in self.lint_ignore:
            if isinstance(entry, LintIgnore) and entry.beat is not None and entry.beat not in beat_ids:
                raise ValueError(f"lint_ignore: scene '{self.id}' has no beat '{entry.beat}'")
        return self

    def lint_ignores(self) -> list[LintIgnore]:
        """``lint_ignore`` with plain rule names turned into :class:`LintIgnore` entries."""
        return [LintIgnore(rule=e) if isinstance(e, str) else e for e in self.lint_ignore]

    @property
    def silent(self) -> bool:
        """True if the scene has no narrated beats."""
        return not self.beats


class VideoConfig(_Strict):
    """The whole ``video.yaml``."""

    title: str = Field(min_length=1)
    """The video's title."""
    output: str | None = Field(default=None, pattern=r"^[^/\\:*?\"<>|]+$")
    """Base name of the output files (no path separators); default: the project folder name."""
    format: FormatConfig = Field(default_factory=FormatConfig)
    """Final render resolution and frame rate."""
    preview: FormatConfig = Field(default_factory=_preview_format)
    """Resolution and frame rate of `vidgen render --preview`."""
    variants: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)
    """Named overrides deep-merged onto this config (mappings merge, lists and scalars replace)."""
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    """Colors, sizes, font and background."""
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    """Text-to-speech voice."""
    narration: NarrationConfig = Field(default_factory=NarrationConfig)
    """Beat padding and duration estimate."""
    extensions: list[str] = Field(default_factory=lambda: ["extensions"])
    """Folders (relative to the project) whose *.py files and packages are imported."""
    lint: LintConfig = Field(default_factory=LintConfig)
    """Thresholds and severities of `vidgen lint`."""
    scenes: list[SceneConfig] = Field(min_length=1)
    """The scenes in order (at least one); scene ids and beat ids must be unique."""

    @field_validator("variants")
    @classmethod
    def _variants_cannot_nest(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        for name, override in value.items():
            if "variants" in override:
                raise ValueError(f"variant '{name}' must not contain 'variants'")
        return value

    @model_validator(mode="after")
    def _check_unique_ids(self) -> VideoConfig:
        scene_seen: dict[str, int] = {}
        beat_seen: dict[str, str] = {}
        for i, scene in enumerate(self.scenes):
            if scene.id in scene_seen:
                raise ValueError(
                    f"duplicate scene id '{scene.id}' (scenes[{scene_seen[scene.id]}] and scenes[{i}])"
                )
            scene_seen[scene.id] = i
            for j, beat in enumerate(scene.beats):
                where = f"scenes[{i}].beats[{j}]"
                if beat.id in beat_seen:
                    raise ValueError(
                        f"duplicate beat id '{beat.id}' ({beat_seen[beat.id]} and {where}); "
                        "beat ids must be unique across the whole video"
                    )
                beat_seen[beat.id] = where
        return self


def format_location(loc: tuple[str | int, ...]) -> str:
    """Render a pydantic error location as a config path, e.g. ``scenes[2].beats[0].id``."""
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def validation_problems(error: ValidationError, prefix: tuple[str | int, ...] = ()) -> list[Problem]:
    """One :class:`~vidgen.errors.Problem` per error; ``prefix`` is prepended to every location
    (e.g. ``("scenes", 2, "params")`` gives ``scenes[2].params.values``)."""
    # Model validators raise from the model itself; drop pydantic's "Value error, " prefix.
    return [
        Problem(format_location((*prefix, *item["loc"])), item["msg"].removeprefix("Value error, "))
        for item in error.errors()
    ]


def validation_error_lines(error: ValidationError, prefix: tuple[str | int, ...] = ()) -> list[str]:
    """One ``path: message`` line per error (see :func:`validation_problems`)."""
    return [str(problem) for problem in validation_problems(error, prefix)]


def format_validation_error(error: ValidationError, source: str) -> str:
    """A readable multi-line message for a pydantic ``ValidationError``."""
    lines = [f"{source}: invalid config"]
    lines.extend(f"  {line}" for line in validation_error_lines(error))
    return "\n".join(lines)


def parse_config(data: Any, source: str = "video.yaml") -> VideoConfig:
    """Validate a raw mapping into a :class:`VideoConfig`.

    ``source`` (usually the file name) is included in error messages.
    Raises :class:`VidgenError` on any validation error; its ``problems`` give each error's
    config location.
    """
    if not isinstance(data, dict):
        raise VidgenError(f"{source}: the top level must be a mapping (key: value pairs)")
    try:
        return VideoConfig.model_validate(data)
    except ValidationError as exc:
        raise VidgenError(format_validation_error(exc, source), problems=validation_problems(exc)) from None
