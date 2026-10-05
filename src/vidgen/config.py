"""Pydantic v2 models for ``video.yaml`` (see DESIGN.md §4).

These models validate *structure* only. Whether a scene ``type`` is registered and whether its
``params`` match the scene's ``Params`` model is checked later, once extensions are loaded.

Use :func:`parse_config` to turn a raw mapping into a :class:`VideoConfig`; it converts pydantic
errors into a readable :class:`~vidgen.errors.VidgenError`.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    PositiveInt,
    ValidationError,
    field_validator,
    model_validator,
)

from vidgen.errors import VidgenError

ID_PATTERN = r"^[A-Za-z0-9_]+$"
HEX_COLOR_PATTERN = r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$"

Identifier = Annotated[str, Field(pattern=ID_PATTERN)]
HexColor = Annotated[str, Field(pattern=HEX_COLOR_PATTERN)]
Size = Annotated[int | float, Field(gt=0)]


class _Strict(BaseModel):
    """Base for structural models: unknown keys are an error (typo protection)."""

    model_config = ConfigDict(extra="forbid")


class FormatConfig(_Strict):
    """Resolution and frame rate of a render."""

    width: PositiveInt = 1920
    height: PositiveInt = 1080
    fps: PositiveInt = 30


def _preview_format() -> FormatConfig:
    return FormatConfig(width=854, height=480, fps=15)


class ThemeConfig(_Strict):
    """Theme values from the config.

    Only the values written in the config are stored here; ``colors``, ``sizes`` and
    ``palette`` are merged with the built-in defaults by :class:`vidgen.theme.Theme`.
    """

    background: HexColor = "#0E1116"
    font: str = "Inter"
    colors: dict[Identifier, HexColor] = Field(default_factory=dict)
    palette: list[HexColor] | None = Field(default=None, min_length=1)
    sizes: dict[Identifier, Size] = Field(default_factory=dict)


class VoiceSettings(_Strict):
    """ElevenLabs ``voice_settings``."""

    stability: float = Field(default=0.55, ge=0, le=1)
    similarity_boost: float = Field(default=0.75, ge=0, le=1)
    style: float = Field(default=0.0, ge=0, le=1)
    use_speaker_boost: bool = True


class VoiceConfig(_Strict):
    """Text-to-speech voice. Only the ElevenLabs provider exists for now."""

    provider: Literal["elevenlabs"] = "elevenlabs"
    voice_id: str = Field(default="nPczCjzI2devNBz1zQrb", min_length=1)
    model_id: str = Field(default="eleven_multilingual_v2", min_length=1)
    output_format: str = Field(default="mp3_44100_128", min_length=1)
    settings: VoiceSettings = Field(default_factory=VoiceSettings)
    context: bool = True


class NarrationConfig(_Strict):
    """Timing of narrated beats."""

    pad: float = Field(default=0.35, ge=0)
    words_per_second: PositiveFloat = 2.6


class BeatConfig(_Strict):
    """One narrated sentence/paragraph. ``id`` is filled in by :class:`SceneConfig` if omitted."""

    id: Identifier
    text: str = Field(min_length=1)

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
    type: Identifier
    params: dict[str, Any] = Field(default_factory=dict)
    beats: list[BeatConfig] = Field(default_factory=list)
    duration: PositiveFloat | None = None

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
        return self

    @property
    def silent(self) -> bool:
        """True if the scene has no narrated beats."""
        return not self.beats


class VideoConfig(_Strict):
    """The whole ``video.yaml``."""

    title: str = Field(min_length=1)
    output: str | None = Field(default=None, pattern=r"^[^/\\:*?\"<>|]+$")
    format: FormatConfig = Field(default_factory=FormatConfig)
    preview: FormatConfig = Field(default_factory=_preview_format)
    variants: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    narration: NarrationConfig = Field(default_factory=NarrationConfig)
    extensions: list[str] = Field(default_factory=lambda: ["extensions"])
    scenes: list[SceneConfig] = Field(min_length=1)

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


def validation_error_lines(error: ValidationError, prefix: tuple[str | int, ...] = ()) -> list[str]:
    """One ``path: message`` line per error; ``prefix`` is prepended to every path
    (e.g. ``("scenes", 2, "params")`` gives ``scenes[2].params.values: ...``)."""
    lines = []
    for item in error.errors():
        # Model validators raise from the model itself; drop pydantic's "Value error, " prefix.
        message = item["msg"].removeprefix("Value error, ")
        path = format_location((*prefix, *item["loc"]))
        lines.append(f"{path}: {message}" if path else message)
    return lines


def format_validation_error(error: ValidationError, source: str) -> str:
    """A readable multi-line message for a pydantic ``ValidationError``."""
    lines = [f"{source}: invalid config"]
    lines.extend(f"  {line}" for line in validation_error_lines(error))
    return "\n".join(lines)


def parse_config(data: Any, source: str = "video.yaml") -> VideoConfig:
    """Validate a raw mapping into a :class:`VideoConfig`.

    ``source`` (usually the file name) is included in error messages.
    Raises :class:`VidgenError` on any validation error.
    """
    if not isinstance(data, dict):
        raise VidgenError(f"{source}: the top level must be a mapping (key: value pairs)")
    try:
        return VideoConfig.model_validate(data)
    except ValidationError as exc:
        raise VidgenError(format_validation_error(exc, source)) from None
