"""Pydantic v2 models for ``video.yaml`` (see DESIGN.md §4).

These models validate *structure* only. Whether a scene ``type`` is registered and whether its
``params`` match the scene's ``Params`` model is checked later, once extensions are loaded.

Use :func:`parse_config` to turn a raw mapping into a :class:`VideoConfig`; it converts pydantic
errors into a readable :class:`~vidgen.errors.VidgenError`.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Annotated, Any, Literal, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    PlainSerializer,
    PositiveFloat,
    PositiveInt,
    PrivateAttr,
    ValidationError,
    WithJsonSchema,
    field_serializer,
    field_validator,
    model_validator,
)

from vidgen.errors import Problem, VidgenError
from vidgen.languages import LANGUAGE_TAG_PATTERN, normalize_language
from vidgen.voicesounds import VoiceSound, take_out_sounds
from vidgen.word_anchors import ACTION_ANCHOR_PATTERN, is_word_anchor, parse_word_anchor, time_beat_anchors, time_config_anchors

ID_PATTERN = r"^[A-Za-z0-9_]+$"
HEX_COLOR_PATTERN = r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$"

#: An action target name: ``name``, ``name3``, ``name1.part2`` or ``kind:label`` (DESIGN.md §26).
TARGET_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*(?::.+)?$"

Identifier = Annotated[str, Field(pattern=ID_PATTERN)]
HexColor = Annotated[str, Field(pattern=HEX_COLOR_PATTERN)]
#: A theme colour token (``secondary``) or a hex colour; the token is checked by ``vidgen validate``.
ColorRef = Annotated[str, Field(pattern=r"^(?:#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})|[A-Za-z0-9_]+)$")]
#: A positive font size (pydantic would put a non-standard ``gt`` into the JSON Schema of the union).
Size = Annotated[int | float, Field(gt=0), WithJsonSchema({"type": "number", "exclusiveMinimum": 0})]
#: A font role's family: a token (``sans``, ``serif``, ``mono``) or a font family name.
FontChoice = Annotated[str, Field(min_length=1)]
#: JSON Schema hint for even pixel sizes (the check itself is ``FormatConfig._even``).
_EVEN = {"multipleOf": 2}
#: A BCP-47 language tag (``en``, ``pt-BR``), normalised to the usual case (DESIGN.md §54).
LanguageTag = Annotated[str, Field(pattern=LANGUAGE_TAG_PATTERN), AfterValidator(normalize_language)]
#: An ElevenLabs ``language_code`` (ISO 639-1, e.g. ``pt``), or ``false``: never send one.
LanguageCode = Annotated[str, Field(pattern=r"^[A-Za-z]{2,3}$")] | Literal[False]


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
        return _even_pixels(value)


def _even_pixels(value: int) -> int:
    # H.264 in yuv420p needs even sizes; Manim's encoder crashes on odd ones.
    if value % 2:
        raise ValueError(f"must be an even number of pixels (got {value}; H.264 video needs even sizes)")
    return value


def _preview_format() -> FormatConfig:
    return FormatConfig(width=854, height=480, fps=15)


#: A draft's shorter side in pixels and its frame rate when ``draft:`` does not set them (DESIGN.md §74).
DRAFT_SHORT_SIDE = 240
DRAFT_FPS = 8


class DraftConfig(_Strict):
    """Resolution and frame rate of a draft (`vidgen render --draft`); unset keys follow the video's format."""

    width: PositiveInt | None = Field(default=None, json_schema_extra=_EVEN)
    """Width in pixels (even; give height too); default: 240 pixels on the shorter side at the format's shape (426x240 for 16:9, 240x426 for 9:16)."""
    height: PositiveInt | None = Field(default=None, json_schema_extra=_EVEN)
    """Height in pixels (even; give width too)."""
    fps: PositiveInt | None = None
    """Frames per second; default 8 (the format's when lower)."""

    @field_validator("width", "height")
    @classmethod
    def _even(cls, value: int | None) -> int | None:
        return None if value is None else _even_pixels(value)

    @model_validator(mode="after")
    def _both_sides(self) -> DraftConfig:
        if (self.width is None) != (self.height is None):
            raise ValueError("give both width and height, or neither (the draft then keeps the format's shape)")
        return self


def draft_format(video: FormatConfig, draft: DraftConfig | None = None) -> FormatConfig:
    """The format of a draft of a video in the ``video`` format: ``draft``'s size and frame rate
    where set, else :data:`DRAFT_SHORT_SIDE` pixels on the shorter side at the video's shape (even
    sizes, never larger than the video) and :data:`DRAFT_FPS` (never more than the video's)."""
    draft = draft or DraftConfig()
    fps = draft.fps if draft.fps is not None else min(DRAFT_FPS, video.fps)
    if draft.width is not None and draft.height is not None:
        return FormatConfig(width=draft.width, height=draft.height, fps=fps)
    short = min(DRAFT_SHORT_SIDE, video.width, video.height)
    long_side = 2 * int(short * max(video.width, video.height) / min(video.width, video.height) / 2)
    width, height = (long_side, short) if video.width >= video.height else (short, long_side)
    return FormatConfig(width=width, height=height, fps=fps)


class DrawingConfig(_Strict):
    """How cartoons are drawn (DESIGN.md §79): outline weight, shading, a paper texture; unset keys
    follow the video's ``drawing:`` (on a stage scene), else the defaults."""

    outline: Literal["thin", "normal", "bold"] | None = None
    """Outline weight of every stroke on stage scenes (characters, props, sets, effects, bubbles) and of a host: thin (0.6x, never under one pixel), normal (as drawn), bold (1.7x); default normal."""
    shading: Literal["flat", "soft"] | None = None
    """flat: filled shapes in one colour; soft: characters' and props' filled shapes lighter at the top and darker at the bottom (the outline and the silhouette unchanged); default flat; drafts draw flat."""
    texture: Literal["none", "paper", "storybook"] | None = None
    """A still grain over each stage scene's frame, under the overlays and captions: none, paper (fine grain), storybook (stronger grain, blotches and darker corners); default none; drafts have none."""
    seed: int | None = Field(default=None, ge=0)
    """Seed of the texture's grain (the same seed and frame size give the same grain); default 0."""


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


#: The built-in emotions (:data:`vidgen.emotions.EMOTIONS`; a test keeps the two equal).
EmotionName = Literal[
    "neutral", "happy", "excited", "sad", "angry", "worried", "scared", "surprised", "calm", "doubtful", "sleepy", "whisper", "shout",
]


class EmotionConfig(_Strict):
    """``emotion:`` as a mapping: a built-in emotion with some of its numbers changed (DESIGN.md §72)."""

    like: EmotionName = "neutral"
    """The built-in emotion to start from."""
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    """Factor on the voice's speed (0.5-2); default the emotion's."""
    pitch: float | None = Field(default=None, ge=-3.0, le=3.0)
    """Pitch shift in semitones (-3 to 3; the length is kept); default the emotion's."""
    gain: float | None = Field(default=None, ge=-12.0, le=6.0)
    """Loudness change in dB (-12 to 6; a boost is soft-limited below full scale); default the emotion's."""
    pauses: float | None = Field(default=None, ge=0.25, le=3.0)
    """Factor on the pauses at commas and full stops inside the line (0.25-3; Kokoro English); default the emotion's."""


#: ``emotion:``: a built-in emotion's name or ``{like, speed, pitch, gain, pauses}``.
EmotionSetting = Union[EmotionName, EmotionConfig]

#: Text-to-speech providers ``voice.provider`` accepts (one per video, DESIGN.md §66, §68).
TTS_PROVIDERS: tuple[str, ...] = ("elevenlabs", "openrouter", "kokoro")
#: Keys of ``voice:`` used only by some providers (the others ignore them).
ELEVENLABS_VOICE_KEYS: tuple[str, ...] = ("voice_id", "model_id", "output_format", "settings", "context", "language_code")
OPENROUTER_VOICE_KEYS: tuple[str, ...] = ("model", "voice", "instructions", "speed")
KOKORO_VOICE_KEYS: tuple[str, ...] = ("voice", "speed", "lang", "device")
#: Provider -> the keys of ``voice:`` it uses (besides ``provider``, ``timestamps``, ``label``, ``color``).
PROVIDER_VOICE_KEYS: dict[str, tuple[str, ...]] = {
    "elevenlabs": ELEVENLABS_VOICE_KEYS,
    "openrouter": OPENROUTER_VOICE_KEYS,
    "kokoro": KOKORO_VOICE_KEYS,
}
#: Kokoro's language codes (``voice.lang``; the first letter of its voice names).
KokoroLang = Literal["a", "b", "e", "f", "h", "i", "j", "p", "z"]


class VoiceSettingsOverride(_Strict):
    """``voice_settings`` of a named voice: what is not given comes from ``voice.settings``."""

    stability: float | None = Field(default=None, ge=0, le=1)
    """ElevenLabs stability (0-1); default the base voice's."""
    similarity_boost: float | None = Field(default=None, ge=0, le=1)
    """ElevenLabs similarity boost (0-1); default the base voice's."""
    style: float | None = Field(default=None, ge=0, le=1)
    """ElevenLabs style exaggeration (0-1); default the base voice's."""
    use_speaker_boost: bool | None = None
    """ElevenLabs speaker boost; default the base voice's."""


class DubVoice(_Strict):
    """A voice in one language of ``dub:`` (DESIGN.md §80) as a mapping: the keys given replace
    the voice's own in videos of that language."""

    voice: str | None = Field(default=None, min_length=1)
    """kokoro / openrouter: the voice in this language (pf_dora, pm_alex...; a Kokoro blend such as pf_dora+af_heart:0.3)."""
    voice_id: str | None = Field(default=None, min_length=1)
    """elevenlabs: the voice id in this language."""
    model_id: str | None = Field(default=None, min_length=1)
    """elevenlabs: the model id in this language."""
    model: str | None = Field(default=None, min_length=1)
    """openrouter: the TTS model in this language."""
    instructions: str | None = Field(default=None, min_length=1)
    """openrouter: how to speak in this language."""
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
    """kokoro / openrouter: speaking speed multiplier in this language (0.25-4)."""
    lang: KokoroLang | None = None
    """kokoro: the voice's language letter; default the first letter of voice."""
    settings: VoiceSettingsOverride | None = None
    """elevenlabs: voice_settings changed in this language."""


#: A ``dub:`` value: the provider's voice (Kokoro / OpenRouter ``voice``, ElevenLabs ``voice_id``)
#: or a mapping of voice keys (:class:`DubVoice`).
DubSetting = Union[Annotated[str, Field(min_length=1)], DubVoice]


class VoiceConfig(_Strict):
    """Text-to-speech voice: ElevenLabs (default), OpenRouter (DESIGN.md §66) or local Kokoro (§68)."""

    provider: Literal["elevenlabs", "openrouter", "kokoro"] = "elevenlabs"
    """TTS provider of the whole video: elevenlabs (ELEVENLABS_API_KEY), openrouter (many TTS models through OpenRouter; OPENROUTER_API_KEY; needs model) or kokoro (Kokoro-82M on this computer, free; pip install "schu-video-generator[kokoro]")."""
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
    timestamps: bool = False
    """Also fetch when each character is spoken (ElevenLabs with-timestamps), stored as audio/<beat>.align.json for exact karaoke captions."""
    language_code: LanguageCode | None = None
    """ElevenLabs language_code (ISO 639-1, e.g. pt) sent with every request, or false: never; default: the video's language for models that accept one (eleven_turbo_v2_5, eleven_flash_v2_5)."""
    model: str | None = Field(default=None, min_length=1)
    """openrouter only (required there): the OpenRouter text-to-speech model id, e.g. mistralai/voxtral-mini-tts-2603 (`vidgen tts --dry-run` shows its price)."""
    voice: str | None = Field(default=None, min_length=1)
    """openrouter and kokoro: the voice name, e.g. en_paul_neutral (each OpenRouter model lists its own; default: the model's own default voice, if it has one); kokoro: af_heart, bf_emma, pf_dora... (default: a voice of voice.lang)."""
    instructions: str | None = Field(default=None, min_length=1)
    """openrouter only: how to speak, e.g. "warm, unhurried explainer; slight pause before numbers" (models that take instructions: Gemini TTS, OpenAI; others ignore it)."""
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
    """openrouter and kokoro: speaking speed multiplier (0.25-4); openrouter: for models that have one, default not sent (the model's own pace); kokoro: default 1."""
    lang: KokoroLang | None = None
    """kokoro only: language of the voice: a American English, b British English, e Spanish, f French, h Hindi, i Italian, j Japanese, p Brazilian Portuguese, z Mandarin Chinese; default: the first letter of voice, else from the video's language (English: a)."""
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    """kokoro only: where the model runs: cpu, cuda (an NVIDIA GPU) or auto (a GPU if PyTorch sees one); does not change the audio hash."""
    emotion: EmotionSetting | None = None
    """How this voice's beats feel unless a beat says otherwise: a built-in emotion (excited, sad, whisper...) or {like, speed, pitch, gain, pauses}; ElevenLabs and OpenRouter models with instructions use only its name; not inherited by voices:."""
    dub: dict[LanguageTag, DubSetting] | None = None
    """This voice in other languages, by language tag: {pt: pf_dora} or {pt: {voice: pm_alex, speed: 0.9}}; used in videos (variants) of that language; without one, a Kokoro voice of another language is replaced by one of the video's language of the same kind (feminine / masculine)."""
    label: str | None = Field(default=None, min_length=1)
    """Speaker name shown in subtitles / captions when speakers are shown (default: none for this voice)."""
    color: ColorRef | None = None
    """Speaker colour (theme token or hex) for captions that colour speakers; default the theme's text colour."""

    @model_validator(mode="after")
    def _provider_options(self) -> VoiceConfig:
        # Keys of the other provider are ignored (a variant may switch the provider while the
        # base config's keys are merged in); only openrouter's required model and a Kokoro
        # voice blend are checked here.
        if self.provider == "kokoro" and self.voice is not None:
            from vidgen.kokoro_voices import blend_weights

            blend_weights(self.voice)
        if self.provider != "openrouter":
            return self
        if self.model is None:
            raise ValueError(
                "provider openrouter needs a model, e.g. model: mistralai/voxtral-mini-tts-2603 (`vidgen tts --dry-run` shows its price)"
            )
        if "/" not in self.model.strip("/"):
            raise ValueError(f"OpenRouter model ids look like author/name (e.g. mistralai/voxtral-mini-tts-2603), not {self.model!r}")
        return self


class VoiceEntry(_Strict):
    """A named voice of ``voices:`` (DESIGN.md §46): the base ``voice:`` with what is given here
    changed. ``label`` and ``color`` are not inherited (they name this speaker)."""

    provider: Literal["elevenlabs", "openrouter", "kokoro"] | None = None
    """TTS provider; only the base voice's (one provider per video: a variant may switch it for the whole video)."""
    voice_id: str | None = Field(default=None, min_length=1)
    """ElevenLabs voice id; default the base voice's."""
    model_id: str | None = Field(default=None, min_length=1)
    """ElevenLabs model id; default the base voice's."""
    output_format: str | None = Field(default=None, min_length=1)
    """ElevenLabs output format; default the base voice's."""
    settings: VoiceSettingsOverride | None = None
    """voice_settings; each value not given comes from the base voice's settings."""
    context: bool | None = None
    """Send neighbouring beats of the same voice as context; default the base voice's."""
    timestamps: bool | None = None
    """Fetch character timings for this voice's beats; default the base voice's."""
    language_code: LanguageCode | None = None
    """ElevenLabs language_code for this voice's beats, or false; default the base voice's."""
    model: str | None = Field(default=None, min_length=1)
    """openrouter: the TTS model of this voice's beats; default the base voice's."""
    voice: str | None = Field(default=None, min_length=1)
    """openrouter / kokoro: the voice name for this speaker; default the base voice's."""
    instructions: str | None = Field(default=None, min_length=1)
    """openrouter: how this speaker talks; default the base voice's."""
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
    """openrouter / kokoro: speaking speed multiplier (0.25-4); default the base voice's."""
    lang: KokoroLang | None = None
    """kokoro: language of this speaker's voice (a, b, e, f, h, i, j, p, z); default the first letter of its voice, else the base voice's."""
    emotion: EmotionSetting | None = None
    """How this speaker's beats feel unless a beat says otherwise (excited, sad, whisper... or {like, speed, pitch, gain, pauses}); not inherited from the base voice."""
    dub: dict[LanguageTag, DubSetting] | None = None
    """This speaker's voice in other languages, by language tag ({pt: pf_dora}); default: the base voice's dub when this voice keeps the base voice, else chosen automatically (Kokoro: a voice of the video's language of the same kind)."""
    label: str | None = Field(default=None, min_length=1)
    """Speaker name in subtitles / captions; default the voice's name (underscores as spaces, first letter capital)."""
    color: ColorRef | None = None
    """Speaker colour (theme token or hex) for captions; default the theme palette colour of the voice's position in voices."""


class SubtitlesConfig(_Strict):
    """The optional ``subtitles:`` section: what the SRT file shows besides the narration."""

    speakers: Literal["off", "name"] = "off"
    """name: put the speaker's label before a beat's first cue when the speaker changes ("Ana: ..."); also the captions' default."""


#: Default outline and feature colour of a character: a dark ink that reads on light and dark themes.
CHARACTER_INK = "#1F2430"


class CharacterColors(_Strict):
    """``colors`` of a character (DESIGN.md §69): theme tokens or hex colours of its parts."""

    skin: ColorRef = "secondary"
    """Head, ears, nose and hands (skin; an animal's fur or feathers, its muzzle and tail tints of it)."""
    clothes: ColorRef = "primary"
    """Body and legs."""
    outline: ColorRef = CHARACTER_INK
    """Outline of every part."""
    features: ColorRef = CHARACTER_INK
    """Eyes, brows, mouth and a dot nose."""
    hair: ColorRef = "accent"
    """Hair (look.hair)."""
    accessory: ColorRef = "highlight"
    """Hat, cap, bow, scarf, bag, backpack, necklace (look.accessories) and shoes (look.shoes); glasses use outline."""
    trim: ColorRef = "dim"
    """The second clothes colour (look.outfit): trousers under a coat, shorts, the shirt under overalls, an apron."""


BodyShape = Literal["round", "tall", "square", "bean", "pear", "triangle"]
EyeStyle = Literal["dot", "oval", "round", "sleepy"]
NoseStyle = Literal["none", "dot", "round", "triangle"]
HairStyle = Literal["none", "short", "spiky", "long", "bun", "curly", "ponytail", "braids", "afro"]
EarStyle = Literal["none", "round", "pointy", "floppy"]
Accessory = Literal[
    "glasses", "hat", "scarf", "bag", "bow", "cap", "backpack", "necklace", "crown", "wizard_hat", "party_hat", "cape",
]
ProportionStyle = Literal["adult", "kid", "tall_kid"]
Outfit = Literal["plain", "dress", "overalls", "coat", "shorts", "apron"]
ClothesPattern = Literal["none", "stripes", "dots"]
ShoeStyle = Literal["none", "shoes", "boots"]
FacialHair = Literal["none", "moustache", "beard"]
Species = Literal["human", "cat", "dog", "bird", "bear", "rabbit", "mouse", "fox", "owl", "frog", "turtle", "penguin", "snail", "robot"]
#: Look keys an animal or a robot (``species`` other than ``human``) draws its own way, so they
#: are not given with it (DESIGN.md §69.48); a robot has no hair either (§69.58).
SPECIES_OWN_KEYS: tuple[str, ...] = ("ears", "nose", "facial_hair")
ROBOT_OWN_KEYS: tuple[str, ...] = (*SPECIES_OWN_KEYS, "hair")
#: Species drawn without a ``tail`` part (DESIGN.md §69.57, §69.58).
SPECIES_WITHOUT_TAIL: frozenset[str] = frozenset({"frog", "snail", "robot"})
#: Species with a shell on the back in ``colors.hair`` (a turtle's domed one, a snail's spiral).
SHELLED_SPECIES: frozenset[str] = frozenset({"turtle", "snail"})
#: Accessories worn on the head: they make the optional ``accessory`` part (DESIGN.md §69.1,
#: the costume pieces §69.58).
HEAD_ACCESSORIES: frozenset[str] = frozenset({"glasses", "hat", "bow", "cap", "crown", "wizard_hat", "party_hat"})
#: Accessories worn on top of the head: a look wears at most one of them.
TOP_OF_HEAD: tuple[str, ...] = ("hat", "cap", "crown", "wizard_hat", "party_hat")
RobotHead = Literal["box", "round"]
RobotFace = Literal["eyes", "screen"]
RobotMoves = Literal["legs", "wheels"]


class RobotLook(_Strict):
    """``look.robot``: how a ``species: robot`` is built (DESIGN.md §69.58)."""

    head: RobotHead = "box"
    """box (a rounded box) or round."""
    face: RobotFace = "eyes"
    """eyes (eyes and a mouth on a light face plate) or screen (a dark screen showing glowing eyes and mouth shapes)."""
    antenna: bool = True
    """An antenna on a spring with a light on top (it wobbles, blinks while idle and trails in the wind)."""
    moves_on: RobotMoves = "legs"
    """legs (it walks), or wheels (it rolls: no steps, no footsteps)."""
#: Outfits with a skirt or coat tails hanging from the body: their ``body`` part has a second
#: shape, ``seated``, the cloth over the lap (DESIGN.md §69.47).
SKIRTED_OUTFITS: frozenset[str] = frozenset({"dress", "coat"})
#: The name of that shape: a seated character shows it (``Character.seated``, the ``sitting`` pose).
SEATED_BODY_SHAPE = "seated"


class CharacterLook(_Strict):
    """``look`` of a character: the parameters of the character generator (DESIGN.md §69.1).
    Every value builds an original figure from primitives (circles, ellipses, rounded
    rectangles, polygons); ``seed`` varies its proportions a little. ``svg`` draws the character
    from an SVG file split into parts by element ids instead (§69.2)."""

    body: BodyShape = "round"
    """Body shape: round, tall, square, bean, pear (narrow shoulders, wide hips) or triangle (broad shoulders)."""
    head_size: float = Field(1.0, ge=0.6, le=1.6)
    """Head size relative to the default head (0.6 to 1.6)."""
    eyes: EyeStyle = "dot"
    """Eye style: dot, oval, round (white with a pupil) or sleepy."""
    nose: NoseStyle = "none"
    """Nose: none, dot, round or triangle."""
    hair: HairStyle = "none"
    """Hair: none, short, spiky, long, bun, curly, ponytail, braids or afro (colour: colors.hair)."""
    ears: EarStyle = "none"
    """Ears: none, round, pointy or floppy (skin colour)."""
    accessories: list[Accessory] = Field(default_factory=list)
    """Any of glasses, hat, scarf, bag, bow, cap, backpack, necklace and the costume pieces crown, wizard_hat, party_hat, cape (each at most once; one of hat, cap, crown, wizard_hat, party_hat)."""
    proportions: ProportionStyle = "adult"
    """adult, kid (big head, short body and legs) or tall_kid (lankier); pair a kid with the stage's scale (e.g. 0.7)."""
    outfit: Outfit = "plain"
    """plain (one colour), dress, overalls, coat, shorts or apron (second colour: colors.trim)."""
    pattern: ClothesPattern = "none"
    """none, stripes or dots on the clothes (a lighter or darker tone of their colour)."""
    shoes: ShoeStyle = "none"
    """none, shoes or boots (colour: colors.accessory)."""
    facial_hair: FacialHair = "none"
    """none, moustache or beard (with a moustache; colour: colors.hair; hair: none for bald)."""
    species: Species = "human"
    """human, or an original animal: cat, dog, bird, bear, rabbit, mouse, fox, owl, frog, turtle, penguin, snail (its own head, ears, muzzle or beak, paws, wings or flippers, a tail but a frog's or a snail's, a turtle's or a snail's shell, a snail's feelers; fur colour: colors.skin, a shell: colors.hair); or robot (see robot; plating: colors.skin)."""
    robot: RobotLook | None = None
    """species robot only: {head: box | round, face: eyes | screen, antenna: true | false, moves_on: legs | wheels}; default a box head, eyes, an antenna, legs."""
    seed: int | None = None
    """A number that varies the proportions a little (same seed, same figure); none: no variation."""
    svg: str | None = Field(default=None, min_length=1)
    """An SVG file (relative to the project folder; best under assets/) drawn instead of the generator: parts by id (head, mouth, arm_left, mouth_A, ...), data-pivot="x y"."""

    @field_validator("accessories")
    @classmethod
    def _unique_accessories(cls, value: list[str]) -> list[str]:
        repeated = sorted({a for a in value if value.count(a) > 1})
        if repeated:
            raise ValueError(f"accessory listed twice: {', '.join(repeated)}")
        on_top = [a for a in TOP_OF_HEAD if a in value]
        if len(on_top) > 1:
            listed = f"{', '.join(on_top[:-1])} and {on_top[-1]} are {'both' if len(on_top) == 2 else 'all'}"
            raise ValueError(f"{listed} worn on top of the head: choose one")
        return value

    @model_validator(mode="after")
    def _svg_alone(self) -> CharacterLook:
        generator_keys = sorted(self.model_fields_set - {"svg"})
        if self.svg is not None and generator_keys:
            raise ValueError(f"svg draws the character from the file; {', '.join(generator_keys)} only apply to the generator (remove them or svg)")
        if self.svg is not None and not self.svg.lower().endswith(".svg"):
            raise ValueError(f"svg must name an .svg file, not {self.svg!r}")
        if self.species == "robot":
            own = [key for key in ROBOT_OWN_KEYS if key in self.model_fields_set and getattr(self, key) != "none"]
            if own:
                raise ValueError(f"a robot draws its own head and face and has no hair; remove {', '.join(own)} (or use another species)")
            if self.robot is not None and self.robot.moves_on == "wheels" and self.shoes != "none":
                raise ValueError("a robot on wheels wears no shoes; remove shoes (or use robot: {moves_on: legs})")
            return self
        if self.robot is not None:
            raise ValueError(f"robot only applies to species: robot (this look is a {self.species}); remove robot or set species: robot")
        own = [key for key in SPECIES_OWN_KEYS if key in self.model_fields_set and getattr(self, key) != "none"]
        if self.species != "human" and own:
            raise ValueError(f"a {self.species} draws its own ears, nose and face; remove {', '.join(own)} (or use species: human)")
        return self

    def robot_look(self) -> RobotLook:
        """``robot``, or the default robot (a box head, eyes, an antenna, legs) when not given."""
        return self.robot if self.robot is not None else RobotLook()


#: How strongly characters move with the animation principles (anticipation, squash and
#: stretch, overshoot and settle, follow-through; DESIGN.md §69.13): ``cartoon_motion:``.
MotionSetting = Literal["lively", "calm", "none"]

#: Parts a pose sets (DESIGN.md §69.3, the two-segment limbs §69.26, an animal's tail §69.48); the parts of an expression
#: are :data:`ExpressionPart` (``cheeks``: a blush or tears; ``bristles``: hair or fur standing up, §69.59).
PosePart = Literal[
    "body", "legs", "leg_left", "leg_left_lower", "leg_right", "leg_right_lower",
    "arm_left", "arm_left_lower", "arm_right", "arm_right_lower", "head", "accessory", "tail", "antenna", "cape",
]
ExpressionPart = Literal["eyes", "brows", "mouth", "cheeks", "bristles"]


class PartPoseEntry(_Strict):
    """How a pose or an expression sets one part of a character (DESIGN.md §69.3), relative to
    its rest drawing."""

    angle: float = 0.0
    """Degrees counterclockwise about the part's pivot, as drawn facing right (facing left mirrors it)."""
    scale: float | tuple[float, float] = 1.0
    """One factor, or [x, y], about the pivot; a negative factor flips the part (y -1 turns a smile into a frown)."""
    shift: tuple[float, float] = (0.0, 0.0)
    """[x, y] in character units (1 = the character's height)."""
    shape: str | list[str] | None = None
    """The shape shown: a name, or a list of names (the first the character has); none: the rest shape."""

    @field_validator("scale")
    @classmethod
    def _nonzero_scale(cls, value: float | tuple[float, float]) -> float | tuple[float, float]:
        if 0 in ((value,) if isinstance(value, (int, float)) else value):
            raise ValueError("a scale factor of 0 makes the part vanish; use a small number instead")
        return value

    def shape_choices(self) -> list[str]:
        """The shape names to try, in order (empty: the rest shape)."""
        return [] if self.shape is None else [self.shape] if isinstance(self.shape, str) else list(self.shape)

    def scale_xy(self) -> tuple[float, float]:
        """``scale`` as (x, y)."""
        return (float(self.scale), float(self.scale)) if isinstance(self.scale, (int, float)) else (float(self.scale[0]), float(self.scale[1]))


class CharacterEntry(_Strict):
    """One entry of ``characters:`` (DESIGN.md §69): a cartoon character declared once and used
    by any scene."""

    name: Identifier
    """Name scenes and beats use for this character (letters, digits, _); unique."""
    voice: Identifier | None = None
    """Who speaks for this character: a name from voices (or default: the base voice); none: the character does not speak."""
    look: CharacterLook = Field(default_factory=CharacterLook)
    """How the character is drawn: body shape, head size, eyes, nose, hair, ears, accessories, proportions, outfit, pattern, shoes, facial hair, species, seed; or svg: a file split into parts."""
    colors: CharacterColors = Field(default_factory=CharacterColors)
    """Part colours {skin, clothes, outline, features, hair, accessory, trim}: theme tokens or hex (not used by an svg look)."""
    poses: dict[Identifier, dict[PosePart, PartPoseEntry]] = Field(default_factory=dict)
    """The character's own poses (name -> part -> {angle, scale, shift, shape}); a built-in name is replaced."""
    expressions: dict[Identifier, dict[ExpressionPart, PartPoseEntry]] = Field(default_factory=dict)
    """The character's own expressions (eyes, brows, mouth, cheeks, bristles), like poses."""
    idle: bool = True
    """Breathe, sway the head slightly and blink every 2 to 6 s on its own; false: hold still between actions."""
    cartoon_motion: MotionSetting | None = None
    """Animation principles for this character (anticipation, squash and stretch, overshoot and settle, follow-through): lively, calm or none; wins over the scene's and the video's; default lively."""


#: A host's height as a fraction of the frame's shorter side (DESIGN.md §71).
HostSize = Annotated[float, Field(gt=0, le=0.9)]


class HostConfig(_Strict):
    """``host:`` (DESIGN.md §71): a character of ``characters:`` drawn beside the content of any
    scene type (bullets, charts, code...), whose region shrinks to make room."""

    character: Identifier
    """The character (a name from characters:)."""
    side: Literal["left", "right"] = "right"
    """Which side of the content it stands on (in 9:16, below the content: the side of the band it stands on)."""
    size: HostSize | None = None
    """Its height as a fraction of the frame's shorter side; default 0.5 in 16:9, 0.42 in 1:1, 0.36 in 9:16."""
    place: Literal["auto", "beside", "below"] = "auto"
    """beside: a column next to the content; below: a band under it; auto: below in a vertical (9:16) frame, else beside."""
    floor: bool = True
    """A plain line it stands on; false: no floor."""
    floor_color: ColorRef = "dim"
    """Colour of the floor line (a theme token or hex)."""
    facing: Literal["auto", "left", "right", "front"] = "auto"
    """Which way it looks; auto: towards the content; front: at the viewer (an SVG character keeps its side)."""
    speaks: Literal["narrator", "own"] = "narrator"
    """Whose lines move its mouth (lip sync): narrator: every beat except those in another character's voice (the host speaks for the narrator); own: only beats in its own voice."""
    pose: Identifier | None = None
    """Its pose (stand, thinking, arms_crossed... or its own); none: standing."""
    expression: Identifier | None = None
    """Its expression (happy, neutral... or its own); none: its rest face."""
    auto_direct: bool | None = None
    """Automatic host directing (look at what is highlighted, point at each new item, react to results); default: on when the video's auto_direct is (a beat's auto_direct wins)."""


class HostOverride(_Strict):
    """A scene's ``host:`` as a mapping: the keys of the video's ``host:`` that change in this
    scene (``character`` is required when the video has no host)."""

    character: Identifier | None = None
    """The character (a name from characters:)."""
    side: Literal["left", "right"] | None = None
    """left or right."""
    size: HostSize | None = None
    """Height as a fraction of the frame's shorter side."""
    place: Literal["auto", "beside", "below"] | None = None
    """auto, beside or below."""
    floor: bool | None = None
    """A floor line or not."""
    floor_color: ColorRef | None = None
    """Colour of the floor line."""
    facing: Literal["auto", "left", "right", "front"] | None = None
    """auto, left, right or front."""
    speaks: Literal["narrator", "own"] | None = None
    """narrator or own."""
    pose: Identifier | None = None
    """Its pose in this scene."""
    expression: Identifier | None = None
    """Its expression in this scene."""
    auto_direct: bool | None = None
    """Automatic host directing in this scene: true or false."""


#: A scene's ``host:``: false (none in this scene), true or unset (the video's), a character
#: name (the video's host settings with that character), or a mapping of :class:`HostOverride`.
SceneHost = bool | Identifier | HostOverride


class PronunciationEntry(_Strict):
    """The long form of a ``pronunciation:`` entry (DESIGN.md §45): how the narrator says a
    term. Applied to the text sent to the TTS only; subtitles and captions keep the term."""

    say: str
    """Spoken form sent to the TTS instead of the term (with regex: true, \\1 or \\g<name> insert a group)."""
    case_sensitive: bool = True
    """Match the term's capitals exactly (false: any case)."""
    whole_word: bool = True
    """Match only where the term is not part of a longer word (no letter, digit or _ right before or after it)."""
    regex: bool = False
    """The term is a Python regular expression (re module syntax), not plain text."""
    language: LanguageTag | list[LanguageTag] | None = None
    """Only in videos of this language (or one of these): pt matches pt-BR and pt-PT; default: every language."""


#: A ``pronunciation:`` value: the spoken form, the long form, or ``null`` (removes an entry of
#: the pronunciation file or of the base config, e.g. in a variant).
PronunciationValue = str | PronunciationEntry | None
#: The ``pronunciation:`` mapping (term -> value); also the content of a ``pronunciation_file``.
PronunciationMap = dict[Annotated[str, Field(min_length=1)], PronunciationValue]


#: The speech rate a beat's length is estimated with when it has no audio (``narration.words_per_second``).
DEFAULT_WORDS_PER_SECOND = 2.6


class NarrationConfig(_Strict):
    """Timing of narrated beats."""

    pad: float = Field(default=0.35, ge=0)
    """Seconds of silence after each beat."""
    words_per_second: PositiveFloat = DEFAULT_WORDS_PER_SECOND
    """Speech rate used to estimate a beat's duration when it has no audio yet."""


class SttConfig(_Strict):
    """The optional ``stt:`` section: the speech-to-text provider of ``vidgen readback`` (DESIGN.md §57)."""

    provider: Literal["faster_whisper", "elevenlabs"] = "faster_whisper"
    """faster_whisper (local and free; pip install "schu-video-generator[stt]") or elevenlabs (ElevenLabs Speech to Text, paid; ELEVENLABS_API_KEY)."""
    model: str | None = Field(default=None, min_length=1)
    """Model: a Whisper size (tiny, base, small, medium, large-v3, turbo; .en for English only) or a folder with a converted model; ElevenLabs: scribe_v1. Default: small.en for English, else small; scribe_v1."""
    language: Literal["auto"] | LanguageTag | None = None
    """Language of the audio (BCP-47; its language subtag is sent), or auto: detected; default: the video's language (English without one)."""
    device: Literal["auto", "cpu", "cuda"] = "auto"
    """faster_whisper: where the model runs (auto: a CUDA GPU if there is one, else the CPU)."""


#: An image size ``WIDTHxHEIGHT`` in pixels (``1536x1024``).
ImageSize = Annotated[str, Field(pattern=r"^[1-9][0-9]{1,4}x[1-9][0-9]{1,4}$")]


class ImagegenConfig(_Strict):
    """The optional ``imagegen:`` section: the image-generation provider of ``vidgen imagegen``
    and of ``generate:`` params (DESIGN.md §58)."""

    provider: Literal["openai", "openrouter"] = "openai"
    """Image-generation provider: openai (OpenAI Images API, paid; OPENAI_API_KEY) or openrouter (many models through OpenRouter, paid; OPENROUTER_API_KEY; needs model)."""
    model: str = Field(default="gpt-image-1", min_length=1)
    """Model: openai: gpt-image-1, dall-e-3 or dall-e-2 (another name is sent as is, with gpt-image-1's sizes); openrouter: required, an OpenRouter model id such as bytedance-seed/seedream-4.5."""
    size: Literal["auto"] | ImageSize = "auto"
    """Picture size WIDTHxHEIGHT sent to the provider, or auto: the model's landscape, portrait or square size by the video's format (or the generate: aspect); openrouter: auto sends an aspect ratio (16:9, 9:16, 1:1) instead."""
    quality: str | None = Field(default=None, min_length=1)
    """Quality sent to the provider (gpt-image-1: low, medium, high; dall-e-3: standard, hd; openrouter: auto, low, medium, high, xhigh, max where the model has it); default: medium for gpt-image models, standard for dall-e-3, none for dall-e-2 and openrouter."""
    resolution: Literal["512", "768", "1K", "1.5K", "2K", "4K"] | None = None
    """openrouter only: resolution tier (512, 768, 1K, 1.5K, 2K, 4K) where the model has it, with the aspect ratio; default: the model's own; not with a WIDTHxHEIGHT size."""
    style: str | None = Field(default=None, min_length=1)
    """Style added to every prompt for a consistent look: a preset (photo, illustration, flat, isometric, watercolor, line_art, render_3d, cinematic) or your own words; a generate: style replaces it."""
    negative: str | None = Field(default=None, min_length=1)
    """What every picture should avoid (added to each generate: negative), e.g. "text, watermarks"."""
    svg_model: str | None = Field(default=None, min_length=1)
    """openrouter only: the model of generate: pictures with format: svg (default: model), e.g. recraft/recraft-v4.1-vector, so one video can mix raster and vector pictures."""

    @model_validator(mode="after")
    def _provider_options(self) -> ImagegenConfig:
        if self.provider == "openai":
            if self.resolution is not None:
                raise ValueError("resolution is an openrouter option; with openai set size: WIDTHxHEIGHT (or auto)")
            if self.svg_model is not None:
                raise ValueError("svg_model is an openrouter option (OpenAI makes no SVG pictures); set provider: openrouter")
            return self
        if self.svg_model is not None and "/" not in self.svg_model.strip("/"):
            raise ValueError(f"OpenRouter model ids look like author/name (e.g. recraft/recraft-v4.1-vector), not svg_model {self.svg_model!r}")
        if "model" not in self.model_fields_set:
            raise ValueError("provider openrouter needs a model, e.g. model: bytedance-seed/seedream-4.5 (`vidgen imagegen --dry-run` shows its price)")
        if "/" not in self.model.strip("/"):
            raise ValueError(f"OpenRouter model ids look like author/name (e.g. openai/gpt-image-1), not {self.model!r}")
        if self.quality is not None and self.quality not in OPENROUTER_QUALITIES:
            raise ValueError(f"quality {self.quality!r} is not an OpenRouter quality; use one of {', '.join(OPENROUTER_QUALITIES)}")
        if self.resolution is not None and self.size != "auto":
            raise ValueError("set size: WIDTHxHEIGHT or resolution, not both (OpenRouter rejects a size that disagrees with the resolution)")
        return self


#: ``quality`` values OpenRouter's image API accepts (a model may take fewer; DESIGN.md §64).
OPENROUTER_QUALITIES: tuple[str, ...] = ("auto", "low", "medium", "high", "xhigh", "max")


#: ``vidgen lint`` rule names (DESIGN.md §16). :class:`LintRules` has one field per name and
#: :mod:`vidgen.lint` one rule per name (a test keeps the three in sync).
LINT_RULES: tuple[str, ...] = (
    "off_frame",
    "safe_area",
    "text_overlap",
    "covered_text",
    "label_spacing",
    "min_font",
    "contrast",
    "max_words",
    "overlay_overlap",
    "host_overlap",
    "walk_overlap",
    "off_stage",
    "character_overlap",
    "prop_overlap",
    "bubble_overlap",
    "facing_away",
    "hidden_speaker",
    "small_speaker",
    "mouth_without_voice",
    "look_alike",
    "narration_speed",
    "dead_air",
    "animation_overrun",
    "rushed_animation",
    "talked_over",
    "readback",
    "unclear_speech",
)
RuleName = Literal[
    "off_frame",
    "safe_area",
    "text_overlap",
    "covered_text",
    "label_spacing",
    "min_font",
    "contrast",
    "max_words",
    "overlay_overlap",
    "host_overlap",
    "walk_overlap",
    "off_stage",
    "character_overlap",
    "prop_overlap",
    "bubble_overlap",
    "facing_away",
    "hidden_speaker",
    "small_speaker",
    "mouth_without_voice",
    "look_alike",
    "narration_speed",
    "dead_air",
    "animation_overrun",
    "rushed_animation",
    "talked_over",
    "readback",
    "unclear_speech",
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


class LabelSpacingRule(RuleConfig):
    """``label_spacing``: a label on its own coloured plate (a callout label, a tag) touching
    other text."""

    min_gap: Fraction = 0.02
    """Smallest gap (fraction of the frame's shorter side) between a label's plate and other text (0.02: 7 px at 360p, 22 px at 1080p)."""


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


class OverlayOverlapRule(RuleConfig):
    """``overlay_overlap``: an overlay (lower third, watermark...) drawn over the scene's text or icons."""

    min_overlap: Fraction = 0.05
    """Part of a scene object's box an overlay must cover to be reported."""


class HostOverlapRule(RuleConfig):
    """``host_overlap``: the cartoon host (``host:``) overlapping the scene's content, a caption or another overlay."""

    min_overlap: Fraction = 0.02
    """Part of the smaller of the two boxes they must share to be reported."""


class WalkOverlapRule(RuleConfig):
    """``walk_overlap``: a character's walk (``walk_to``, ``enter``) ends on another character."""

    min_overlap: Fraction = 0.25
    """Share of the narrower character's width the two must share side by side to be reported."""


class OffStageRule(RuleConfig):
    """``off_stage``: a character partly outside the view (not while it enters or exits); in a shot, a character the shot frames."""

    min_hidden: Fraction = 0.05
    """Share of the character's box outside the view from which it is reported."""


class CharacterOverlapRule(RuleConfig):
    """``character_overlap``: two characters standing on each other (neither walked there in the beat)."""

    min_overlap: Fraction = 0.25
    """Share of the narrower character's width the two must share side by side to be reported."""


class PropOverlapRule(RuleConfig):
    """``prop_overlap``: two props standing on the floor at about the same depth drawn over each other (a door and the sofa against the wall)."""

    min_overlap: Fraction = 0.15
    """Share of the narrower prop's width the two must share side by side to be reported."""


class BubbleOverlapRule(RuleConfig):
    """``bubble_overlap``: a speech bubble covering a character's face, another bubble or an effect symbol."""

    min_overlap: Fraction = 0.1
    """Share of the face's box (or of the smaller bubble's box, or of the effect symbol's box) the bubble must cover to be reported."""


class FacingAwayRule(RuleConfig):
    """``facing_away``: a speaking character facing away from the one it talks to."""


class HiddenSpeakerRule(RuleConfig):
    """``hidden_speaker``: a speaking character whose face something in front of it hides."""

    min_hidden: Fraction = 0.5
    """Share of the face's box covered by things drawn in front from which it is reported."""


class SmallSpeakerRule(RuleConfig):
    """``small_speaker``: a speaking character too small on screen to read its face and lip sync."""

    min_face: Fraction = 0.075
    """Smallest acceptable height of a speaking character's head on screen (its box, fraction of the frame's shorter side: 0.075 is 36 px at 480p, 81 px at 1080p; a character on a level has about 0.07 at character_size small, 0.095 at medium)."""


class MouthWithoutVoiceRule(RuleConfig):
    """``mouth_without_voice``: a character's lip sync showing a speech shape while no narration is heard."""


class LookAlikeRule(RuleConfig):
    """``look_alike``: two generated characters of the video too alike to tell apart at a glance (DESIGN.md §69.49)."""

    min_contrast: float = Field(default=0.35, ge=0, le=1)
    """Lowest acceptable contrast score of two characters (0 the same look, 1 fully different: silhouette, colours, accessories)."""


class NarrationSpeedRule(RuleConfig):
    """``narration_speed``: a beat spoken too fast or too slow (spoken words, or characters, per second)."""

    unit: Literal["auto", "words", "characters"] = "auto"
    """What is counted: words, characters (letters and digits), or auto: words for languages vidgen has a word rate for (en, pt, es, fr, de, it; also a video without language), else characters."""
    min_rate: PositiveFloat | None = None
    """Slowest acceptable rate per second in the unit; default the language's (English 1.8 words = 108 a minute; characters 8)."""
    max_rate: PositiveFloat | None = None
    """Fastest acceptable rate per second in the unit; default the language's (English 3.5 words = 210 a minute; characters 17)."""
    min_words: PositiveInt = 5
    """Beats with fewer spoken words are not checked (their rate is mostly pauses)."""

    @model_validator(mode="after")
    def _ordered(self) -> NarrationSpeedRule:
        if self.min_rate is not None and self.max_rate is not None and self.min_rate >= self.max_rate:
            raise ValueError("min_rate must be smaller than max_rate")
        return self

    def limits(self, language: str | None) -> tuple[str, float, float]:
        """``(unit, min_rate, max_rate)`` for a video in ``language``: the configured values, the
        missing ones from the language's range (DESIGN.md §54)."""
        from vidgen.languages import CHARACTER_RATE, language_rules

        words = language_rules(language).words_per_second
        unit = ("words" if words is not None else "characters") if self.unit == "auto" else self.unit
        default = (words or (1.8, 3.5)) if unit == "words" else CHARACTER_RATE
        low = self.min_rate if self.min_rate is not None else default[0]
        high = self.max_rate if self.max_rate is not None else default[1]
        return unit, low, max(high, low + 1e-6)


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
    max_speedup: float = Field(default=1.5, ge=1.0)
    """Fastest acceptable speed-up of a walk or a jump on a platform level squeezed into its beat (its own time over the time it got)."""


class TalkedOverRule(RuleConfig):
    """``talked_over``: a beat's ``overlap`` starts so early that whole words of the line before are spoken under it,
    or its ``interrupt`` cuts that line before whole words."""


class ReadbackRule(RuleConfig):
    """``readback``: a beat whose audio, transcribed by `vidgen readback`, differs from its text."""

    max_wer: float = Field(default=0.1, ge=0, lt=1)
    """Highest acceptable word error rate (differing words / words of the text); also `vidgen readback`'s threshold."""


class UnclearSpeechRule(RuleConfig):
    """``unclear_speech``: words the speech-to-text heard with low confidence, after an unusual pause, or differently from the text (`vidgen lint --readback`; `vidgen readback`'s word flags)."""

    min_probability: float = Field(default=0.5, gt=0, le=1)
    """A word heard with a probability below this is unclear (the rule's severity)."""
    doubtful_probability: float = Field(default=0.75, gt=0, le=1)
    """A word heard with a probability below this (and not below min_probability) is doubtful (info)."""
    max_gap: PositiveFloat = 0.5
    """Seconds of silence between two words inside a sentence (not at punctuation or a voice sound) from which the pause is unclear."""

    @model_validator(mode="after")
    def _ordered(self) -> UnclearSpeechRule:
        if self.min_probability > self.doubtful_probability:
            raise ValueError("min_probability must not be larger than doubtful_probability")
        return self


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
    label_spacing: LabelSpacingRule = Field(default_factory=LabelSpacingRule)
    """A label on its own coloured plate touching other text (default: warning)."""
    min_font: MinFontRule = Field(default_factory=MinFontRule)
    """Text too small (default: warning, error below error_size)."""
    contrast: ContrastRule = Field(default_factory=ContrastRule)
    """Low text contrast (default: warning)."""
    max_words: MaxWordsRule = Field(default_factory=MaxWordsRule)
    """Too many words on screen (default: warning)."""
    overlay_overlap: OverlayOverlapRule = Field(default_factory=OverlayOverlapRule)
    """Overlays covering scene text or icons (default: warning)."""
    host_overlap: HostOverlapRule = Field(default_factory=HostOverlapRule)
    """The cartoon host overlapping the scene's content, captions or other overlays (default: warning)."""
    walk_overlap: WalkOverlapRule = Field(default_factory=WalkOverlapRule)
    """A character ending its walk on another character (default: warning)."""
    off_stage: OffStageRule = Field(default_factory=OffStageRule)
    """A character partly outside the view, not entering or exiting (default: warning)."""
    character_overlap: CharacterOverlapRule = Field(default_factory=CharacterOverlapRule)
    """Two characters standing on each other (default: warning)."""
    prop_overlap: PropOverlapRule = Field(default_factory=PropOverlapRule)
    """Two props on the floor at about the same depth drawn over each other (default: warning)."""
    bubble_overlap: BubbleOverlapRule = Field(default_factory=BubbleOverlapRule)
    """A speech bubble covering a face or another bubble (default: warning)."""
    facing_away: FacingAwayRule = Field(default_factory=FacingAwayRule)
    """A speaking character facing away from its listener (default: warning)."""
    hidden_speaker: HiddenSpeakerRule = Field(default_factory=HiddenSpeakerRule)
    """A speaking character whose face is hidden by something in front of it (default: warning)."""
    small_speaker: SmallSpeakerRule = Field(default_factory=SmallSpeakerRule)
    """A speaking character too small on screen to read its face and lip sync (default: warning)."""
    mouth_without_voice: MouthWithoutVoiceRule = Field(default_factory=MouthWithoutVoiceRule)
    """A mouth moving with lip sync while no narration is heard (default: warning)."""
    look_alike: LookAlikeRule = Field(default_factory=LookAlikeRule)
    """Two characters of the video that look too alike (default: warning)."""
    narration_speed: NarrationSpeedRule = Field(default_factory=NarrationSpeedRule)
    """Narration too fast or too slow (default: warning; info for beats without audio)."""
    dead_air: DeadAirRule = Field(default_factory=DeadAirRule)
    """No visual change for too long (default: warning)."""
    animation_overrun: AnimationOverrunRule = Field(default_factory=AnimationOverrunRule)
    """Animations running past the narration (default: warning)."""
    rushed_animation: RushedAnimationRule = Field(default_factory=RushedAnimationRule)
    """Animations shortened to fit a too short beat (default: warning)."""
    talked_over: TalkedOverRule = Field(default_factory=TalkedOverRule)
    """Whole words of a line spoken under the next beat's overlap (default: warning)."""
    readback: ReadbackRule = Field(default_factory=ReadbackRule)
    """Audio heard differently from its text, from the transcripts `vidgen readback` stored (default: warning; nothing without them)."""
    unclear_speech: UnclearSpeechRule = Field(default_factory=UnclearSpeechRule)
    """Words heard with low confidence or after an unusual pause; runs only with `vidgen lint --readback` (default: warning; info for doubtful words)."""


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
    at: Annotated[float, Field(ge=0, lt=1)] | Annotated[str, Field(pattern=ACTION_ANCHOR_PATTERN)] = 0.0
    """When in the beat: a fraction of its narration (0 = start), or a spoken word of the beat ("@gradient", "@gradient#2" its second time, "@gradient+0.3s" moved by seconds); the action waits for the scene's own animation running then."""
    until: Identifier | None = None
    """A later beat of the scene at whose start the action is undone (dim, highlight)."""
    run_time: PositiveFloat | None = None
    """Seconds the action's animation takes (default: the action's own); shortened to fit the beat."""

    _shorthand: dict[str, Any] | None = PrivateAttr(default=None)
    _auto: bool = PrivateAttr(default=False)
    _anchor: str | None = PrivateAttr(default=None)

    @field_validator("at", mode="before")
    @classmethod
    def _word_or_fraction(cls, value: Any) -> Any:
        """A word anchor's syntax is checked here (its word against the beat's text by
        :class:`BeatConfig`); a number must be a fraction 0 <= at < 1."""
        if isinstance(value, str) and is_word_anchor(value):
            parse_word_anchor(value)
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool) and not 0 <= value < 1:
            raise ValueError(f"at {value:g}: a fraction of the beat's narration, 0 <= at < 1 (0.5 is its middle), or a word it says: \"@word\"")
        return value

    @model_validator(mode="after")
    def _keep_anchor(self) -> ActionConfig:
        if isinstance(self.at, str):
            self._anchor = self.at
        return self

    @property
    def anchor(self) -> str | None:
        """The word anchor ``at`` was written as (``"@gradient#2"``), else ``None``; ``at``
        itself is its fraction of the beat once resolved (DESIGN.md §87.2)."""
        return self._anchor

    @property
    def fraction(self) -> float:
        """``at`` as a fraction of the beat (a word anchor not resolved yet: 0)."""
        return self.at if isinstance(self.at, float | int) else 0.0

    def set_fraction(self, fraction: float) -> None:
        """Set ``at`` to the fraction a word anchor resolves to (the anchor is kept)."""
        self.at = fraction

    @field_serializer("at")
    def _written_at(self, value: float | str) -> float | str:
        return self._anchor if self._anchor is not None else value

    @classmethod
    def automatic(cls, data: dict[str, Any]) -> ActionConfig:
        """An action that automatic directing adds (``auto_direct``, DESIGN.md §69.23), not the
        config: :attr:`auto` is true."""
        made = cls.model_validate(data)
        made._auto = True
        return made

    @property
    def auto(self) -> bool:
        """Whether automatic directing added this action (it is not in the config)."""
        return self._auto

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

    @field_validator("target", mode="before")
    @classmethod
    def _number_text(cls, value: Any) -> Any:
        """A number as the target (``- wind: 0.6``) is kept as its text; the action reads it."""
        return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value

    def resolved(self, known: Collection[str]) -> ActionConfig:
        """This action, or — for a shorthand whose first key is not a known action but exactly
        one other key is (keys sorted by a tool) — the action that key names."""
        if self._shorthand is None or self.action in known:
            return self
        names = [k for k in self._shorthand if k in known and k not in ACTION_KEYS]
        if len(names) != 1:
            return self
        made = ActionConfig.model_validate(_unshorten(self._shorthand, names[0]))
        made.at = self.at
        return made

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
        """``highlight item3`` (for messages); ``look_at kit (auto)`` for an automatic action."""
        return " ".join([self.action, *self.targets(), *(["(auto)"] if self._auto else [])])

    def shorthand(self) -> dict[str, Any]:
        """The action as written in ``video.yaml``: ``{NAME: TARGET, ...options}`` (``at``,
        ``until`` and ``run_time`` only when set)."""
        data: dict[str, Any] = {self.action: self.target} if self.target is not None else {"action": self.action}
        data.update(self.options)
        if self._anchor is not None or self.at:
            data["at"] = self._anchor if self._anchor is not None else self.at
        for key in ("until", "run_time"):
            if getattr(self, key) is not None:
                data[key] = getattr(self, key)
        return data


#: Keys every overlay entry has; any other key of an entry is an option of its overlay type.
OVERLAY_KEYS = ("type", "id", "scenes", "exclude", "from", "to", "reserve")
#: Keys a scene's override of a video-level overlay may set besides the type's options.
OVERLAY_OVERRIDE_KEYS = ("reserve",)
#: Where an overlay starts or ends: seconds in the video, or a scene id (its start / its end).
OverlayTime = Annotated[float, Field(ge=0)] | Identifier


class OverlayConfig(BaseModel):
    """An entry of the video-level ``overlays:`` list (DESIGN.md §41): ``{type, id, scenes,
    exclude, from, to, reserve, ...options}``.

    Which overlay types exist and their options depend on the registered overlay types, so they
    are checked by ``vidgen validate`` (``vidgen.overlays``), not here.
    """

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True, populate_by_name=True)

    type: Identifier
    """Overlay type: lower_third, watermark, or a project overlay (`vidgen list-scenes`)."""
    id: Identifier | None = None
    """Name for scene overrides (`overlays: {ID: false}` on a scene); default the type, or <type><n> when several entries share a type."""
    scenes: Literal["all"] | list[Identifier] = "all"
    """Scenes it is drawn on: all, or a list of scene ids."""
    exclude: list[Identifier] = Field(default_factory=list)
    """Scenes it is not drawn on."""
    from_: OverlayTime | None = Field(default=None, alias="from")
    """Where it starts: seconds in the video, or a scene id (that scene's start); default the video's start."""
    to: OverlayTime | None = None
    """Where it ends: seconds in the video, or a scene id (that scene's end); default the video's end."""
    reserve: bool | None = None
    """Keep scene layouts clear of it: the safe area of every scene it is drawn on shrinks to avoid its box (default: the type's choice, false for most; captions at the top or bottom: true)."""

    @property
    def options(self) -> dict[str, Any]:
        """The type-specific options (every key other than :data:`OVERLAY_KEYS`)."""
        return dict(self.model_extra or {})


#: A scene's ``overlays:`` setting: on/off, or per overlay id ``false`` / ``true`` / a mapping
#: of option overrides (or, with ``type``, an overlay of this scene only).
SceneOverlays = bool | dict[Identifier, bool | dict[str, Any]]


#: A sound effect's name: a built-in sound or a file assets/sfx/<name>.wav (DESIGN.md §47).
SOUND_NAME_PATTERN = r"^[A-Za-z0-9_][A-Za-z0-9_-]*$"
SoundName = Annotated[str, Field(pattern=SOUND_NAME_PATTERN)]


class SfxParams(_Strict):
    """Parameters of a built-in sound effect (`vidgen list-sfx` describes the sounds)."""

    duration: PositiveFloat | None = None
    """Seconds; default the sound's own (each sound has a range, see vidgen list-sfx)."""
    pitch: float | None = Field(default=None, ge=-24, le=24)
    """Semitones up (positive) or down (negative); default 0."""
    intensity: float | None = Field(default=None, ge=0, le=1)
    """0 to 1: brighter and up to 3 dB louder towards 1, softer towards 0; default 0.5."""


class SfxCue(_Strict):
    """A sound effect at a time of the scene (an entry of a scene's ``sfx:`` list; a plain
    string is the sound at the scene's start)."""

    sound: SoundName
    """A built-in sound (whoosh, pop, click, ...; vidgen list-sfx) or the project's assets/sfx/<sound>.wav."""
    at: float = Field(default=0.0, ge=0)
    """Seconds from the scene's start."""
    gain: float = Field(default=0.0, ge=-60, le=12)
    """Level change in dB (0: the sound's own level, about 7 dB under narration)."""
    pan: float = Field(default=0.0, ge=-1, le=1)
    """-1 left, 0 centre, 1 right."""
    align: Literal["start", "end"] = "start"
    """start: the sound starts at `at`; end: it ends there (a riser landing on a reveal)."""
    params: SfxParams = Field(default_factory=SfxParams)
    """duration, pitch, intensity of a built-in sound."""

    @field_validator("at", mode="before")
    @classmethod
    def _no_word(cls, value: Any) -> Any:
        if is_word_anchor(value):
            raise ValueError(f"{value!r}: a scene's sfx list is timed in seconds; for a sound on a spoken word use the beat's sfx action: actions: [{{sfx: NAME, at: \"@word\"}}]")
        return value


def _cue(value: str | SfxCue) -> SfxCue:
    return SfxCue(sound=value) if isinstance(value, str) else value


#: An entry of a scene's ``sfx:`` list: a cue, or a sound name (that sound at the scene's start).
SfxEntry = Annotated[Union[SoundName, SfxCue], AfterValidator(_cue)]


#: The kinds of a beat's music sting (``sting:``; DESIGN.md §69.19).
StingKind = Literal["reveal", "comic", "sad"]


class StingCue(_Strict):
    """A short music sting on a beat (``sting:``): a reveal, a comic drum hit or a sad trombone,
    ducked under the narration like the music."""

    kind: StingKind
    """reveal (a "ta-da" chord), comic (ba-dum-tss) or sad (wah wah wah waaah)."""
    at: Literal["start", "end"] | None = None
    """start: as the beat starts; end: when its narration ends, in the pause after the line; default start for reveal, end for comic and sad."""
    gain: float = Field(default=0.0, ge=-60, le=12)
    """Level change in dB (0: about 7 dB under the narration before ducking)."""

    @property
    def placed_at(self) -> Literal["start", "end"]:
        """``at``, or the kind's default (reveal: start; comic, sad: end)."""
        return self.at or ("start" if self.kind == "reveal" else "end")


def _sting(value: str | StingCue) -> StingCue:
    return StingCue(kind=value) if isinstance(value, str) else value


#: A beat's ``sting:``: a kind, or ``{kind, at, gain}``.
StingSetting = Annotated[Union[StingKind, StingCue], AfterValidator(_sting)]


#: The framings of a beat's ``shot:`` (DESIGN.md §69.29; :data:`vidgen.cartoon.shots.SHOT_KINDS`).
ShotKind = Literal["wide", "two_shot", "medium", "over_shoulder", "closeup"]
#: How many characters each framing names: (fewest, most); fewer than the most are filled in
#: when the shot is framed (:func:`vidgen.cartoon.shots.shot_figures`).
SHOT_NAMES: dict[str, tuple[int, int]] = {"wide": (0, 0), "two_shot": (0, 2), "medium": (1, 1), "over_shoulder": (1, 2), "closeup": (1, 1)}


def _name_or_names_schema(schema: dict[str, Any]) -> None:
    """JSON Schema of a list of names that may also be written as one name (``of: kit``), which a
    model's ``before`` validator turns into a list."""
    names = {key: schema.pop(key) for key in ("type", "items") if key in schema}
    schema["anyOf"] = [names["items"], names]


class ShotConfig(_Strict):
    """A beat's camera framing on a stage (``shot:``): ``closeup kit`` or ``{kind, of, move,
    run_time}``. It cuts to the framing as the beat starts (eases with ``move: true``) and holds
    for the beat; the next beat without a shot goes back to the view before the shots."""

    kind: ShotKind
    """wide (everyone, no zoom), two_shot (two characters, whole), medium (one from the hips up), over_shoulder (one seen past another, who stands cut by the frame's edge) or closeup (head and shoulders)."""
    of: list[Identifier] = Field(default_factory=list, json_schema_extra=_name_or_names_schema)
    """The characters it frames: none for wide; two_shot two (default: the speaker and the one nearest it); medium and closeup one; over_shoulder the one seen, then the near one (default: the one it looks at, else the nearest)."""
    move: bool = False
    """true: the camera eases to the framing (and back after the beat) instead of cutting."""
    run_time: PositiveFloat | None = None
    """Seconds of the move with move: true (default 1.0)."""

    @model_validator(mode="before")
    @classmethod
    def _from_words(cls, data: Any) -> Any:
        """``"over_shoulder kit pip"`` -> ``{kind: over_shoulder, of: [kit, pip]}``; ``of`` may be one name."""
        if isinstance(data, str):
            kind, *names = data.split()
            return {"kind": kind, "of": names}
        if isinstance(data, dict) and isinstance(data.get("of"), str):
            return {**data, "of": [data["of"]]}
        return data

    @model_validator(mode="after")
    def _check_names(self) -> ShotConfig:
        fewest, most = SHOT_NAMES[self.kind]
        if not fewest <= len(self.of) <= most:
            wanted = "no character" if most == 0 else f"{fewest} to {most} characters" if fewest != most else f"{most} character"
            raise ValueError(f"a {self.kind} shot names {wanted}, got {len(self.of)} ({' '.join(self.of) or 'none'})")
        if len(set(self.of)) != len(self.of):
            raise ValueError(f"a {self.kind} shot names a character twice ({' '.join(self.of)})")
        if self.run_time is not None and not self.move:
            raise ValueError("run_time is for a shot with move: true (a cut takes no time)")
        return self

    def action(self) -> ActionConfig:
        """The ``shot`` action this key stands for (at the beat's start)."""
        data: dict[str, Any] = {"action": "shot", "kind": self.kind}
        if self.of:
            data["target"] = list(self.of)
        if self.move:
            data["move"] = True
        if self.run_time is not None:
            data["run_time"] = self.run_time
        return ActionConfig.model_validate(data)


def _shot_words_schema(schema: dict[str, Any]) -> None:
    """JSON Schema of a beat's ``shot:``: also the words form (``"two_shot kit pip"``), which
    :meth:`ShotConfig._from_words` reads but the generated schema does not list."""
    words = {"type": "string", "pattern": r"^\s*(wide|two_shot|medium|over_shoulder|closeup)(\s+\S+)*\s*$"}
    schema.setdefault("anyOf", []).insert(0, words)


#: The kinds of automatic directing (``auto_direct:``; DESIGN.md §69.23), in planning order.
DIRECTING_KINDS: tuple[str, ...] = ("looks", "reactions", "gestures", "closeups", "effects")


class AutoDirect(_Strict):
    """Which kinds of automatic directing a stage scene gets (``auto_direct: {...}``); a kind not
    given is on. Actions written in a beat always win over automatic ones."""

    looks: bool = True
    """Listeners turn and look at whoever speaks; the speaker looks at the one it talks to."""
    reactions: bool = True
    """Listeners react in the pause after a line with an expression chosen from its punctuation and words (! surprised or happy, ? thinking, a negation worried)."""
    gestures: bool = True
    """The speaker gestures on a line's stressed word (*word*, an all-capitals word, else a long one): at most one per line, from the gestures its parts allow."""
    closeups: bool = True
    """A short punchy line right after a long one gets a close-up (a zoom on the speaker, or a closeup shot when the line is too short for the zoom's moves): never two beats in a row, never during a walk, a camera move or a written shot."""
    effects: bool = True
    """A strong change of expression gets an effect symbol over the head (surprised: exclaim, thinking: question, angry: anger): at most one per line, none in a beat with a written effect."""


#: ``auto_direct:`` on the video, a stage scene or a beat: ``true`` (every kind), ``false``
#: (none) or ``{looks, reactions, gestures, closeups, effects}``; the nearest one wins.
AutoDirectSetting = Union[bool, AutoDirect]


#: ``reframe:`` on the video or a stage scene (DESIGN.md §69.30): ``speaker`` (the camera keeps
#: whoever speaks in view on a stage wider than the frame) or ``none``; not given: ``speaker``
#: when the stage's characters do not fit in one view.
ReframeSetting = Literal["speaker", "none"]
#: ``character_size:`` on the video or a stage scene (DESIGN.md §86.10): the base size of the
#: characters and of the world they stand in (``small``: a wide landscape, for cinema; ``medium``:
#: TV / YouTube, the default; ``large``: big characters, for phones and Shorts).
CharacterSize = Literal["small", "medium", "large"]


def directing_kinds(*settings: AutoDirectSetting | None) -> frozenset[str]:
    """The kinds of automatic directing on, from settings nearest first (a beat's, its scene's,
    the video's): the first one given wins; none given: off."""
    for setting in settings:
        if setting is None:
            continue
        if isinstance(setting, bool):
            return frozenset(DIRECTING_KINDS) if setting else frozenset()
        return frozenset(kind for kind in DIRECTING_KINDS if getattr(setting, kind))
    return frozenset()


class SfxConfig(_Strict):
    """Video-wide sound effect settings (DESIGN.md §47)."""

    auto: bool = False
    """Add soft sounds to built-in animations: reveal (pop), highlight (tick), callout (click), zoom (whoosh), transform (swoosh) actions and chapter cards (whoosh)."""
    gain: float = Field(default=0.0, ge=-60, le=12)
    """Level change in dB of every sound effect of the video."""


class DuckConfig(_Strict):
    """How music ducks under the narration (DESIGN.md §48)."""

    depth: float = Field(default=12.0, ge=0, le=40)
    """dB the music drops while the narrator speaks (0: no ducking)."""
    attack: float = Field(default=0.4, ge=0, le=5)
    """Seconds the music takes to go down; it is down when the speech starts."""
    release: float = Field(default=1.0, ge=0, le=10)
    """Seconds the music takes to come back up after the speech ends."""
    hold: float = Field(default=1.5, ge=0, le=10)
    """Pauses in the speech shorter than this keep the music down (no pumping between beats and sentences)."""
    clips: bool = True
    """A video_clip scene's own sound counts as foreground too (the music ducks under it)."""


def _duck(value: bool | DuckConfig) -> DuckConfig:
    if isinstance(value, DuckConfig):
        return value
    return DuckConfig() if value else DuckConfig(depth=0)


class ComposeInstrument(_Strict):
    """One part of composed music in its long form: the instrument and its mix."""

    instrument: str | None = None
    """A friendly instrument name (piano, strings, flute, ...; vidgen list-music); default: the mood's."""
    volume: float | None = Field(default=None, ge=-60, le=12)
    """dB against the other parts (each part is first set to the same loudness); default: the mood's."""
    pan: float | None = Field(default=None, ge=-1, le=1)
    """-1 (left) to 1 (right); default: the mood's."""
    reverb: float | None = Field(default=None, ge=0, le=1)
    """Share sent to the reverb, 0-1; default: the mood's."""


def _compose_shorthand(value: Any) -> Any:
    return {"mood": value} if isinstance(value, str) else value


def _mood_name_schema(schema: dict[str, Any]) -> None:
    """JSON Schema of ``compose:``: also a mood's name alone (``compose: playful``), which
    :func:`_compose_shorthand` reads but the generated schema does not list."""
    schema.setdefault("anyOf", []).insert(0, {"type": "string", "minLength": 1})


class ComposeConfig(_Strict):
    """Music composed for the video from a mood (``compose:``; DESIGN.md §83), played with real
    instruments (needs the ``music`` extra; without it a built-in bed plays)."""

    mood: str
    """calm, focused, curious, upbeat (explainers), playful, sleepy, tense, triumphant (cartoons); vidgen list-music."""
    key: str | None = None
    """A note, or a note with the mood's mode (e.g. E, 'Eb major', 'F# minor'); default: the mood's."""
    tempo: float | None = Field(default=None, ge=40, le=200)
    """Quarter notes per minute; default: the mood's."""
    instruments: dict[str, str | ComposeInstrument | None] = Field(default_factory=dict)
    """Per part (melody, chords, pad, bass, drums): an instrument name, none (leave the part out), or {instrument, volume, pan, reverb}."""
    seed: int = Field(default=1, ge=0)
    """Another seed gives another piece in the same mood; the same seed always the same notes."""
    bars: int | None = Field(default=None, ge=4, le=128, multiple_of=4)
    """A piece of this many bars (a multiple of 4) that loops; default: none, the piece is composed for the video (as long as the cue, scene changes on bar lines, a cadence at the end)."""

    @model_validator(mode="after")
    def _check(self) -> ComposeConfig:
        from vidgen.composer import settings_problems

        problems = settings_problems(self.mood, self.key, self.tempo, self.instrument_settings(), self.bars)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def instrument_settings(self) -> dict[str, Any]:
        """``instruments`` as plain data for :func:`vidgen.composer.compose`."""
        return {role: v.model_dump() if isinstance(v, ComposeInstrument) else v for role, v in self.instruments.items()}


class MusicCue(_Strict):
    """Background music (``music:``, or one entry of a list of cues): a built-in bed, a file or
    composed music, over the whole video or from one scene to another."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True, populate_by_name=True)

    source: str | None = Field(default=None, min_length=1)
    """A built-in bed (calm, pulse, bright, cartoon, lullaby; vidgen list-music) or an audio file under the project (e.g. assets/music/theme.mp3); give this or compose."""
    compose: Annotated[ComposeConfig | None, BeforeValidator(_compose_shorthand)] = Field(default=None, json_schema_extra=_mood_name_schema)
    """Music composed from a mood instead of a source: a mood name or {mood, key, tempo, instruments, seed, bars}; needs the music extra."""
    volume: float = Field(default=0.0, ge=-60, le=12)
    """Level change in dB (0: -28 LUFS, about 7 dB under typical narration before ducking)."""
    start: float = Field(default=0.0, ge=0)
    """Seconds into the source where the music starts (a loop restarts there too)."""
    loop: bool = True
    """Repeat the source while the cue lasts; false: it plays once and fades out at its end."""
    crossfade: float = Field(default=2.0, ge=0, le=30)
    """Seconds over which a file's end cross-fades into its start at each repeat (beds loop seamlessly)."""
    fade_in: float = Field(default=1.5, ge=0)
    """Seconds of fade-in at the cue's start."""
    fade_out: float = Field(default=3.0, ge=0)
    """Seconds of fade-out ending at the cue's end."""
    duck: Annotated[DuckConfig | bool, AfterValidator(_duck)] = Field(default_factory=DuckConfig)
    """Ducking under the narration: {depth, attack, release, hold, clips}; false: none."""
    from_: Identifier | None = Field(default=None, alias="from")
    """First scene of the cue (from its start); default the video's first scene."""
    to: Identifier | None = None
    """Last scene of the cue (to its end); default the video's last scene."""

    @model_validator(mode="after")
    def _one_source(self) -> MusicCue:
        if (self.source is None) == (self.compose is None):
            raise ValueError("give either source (a bed or a file) or compose (a mood), not both" if self.source else "give source (a bed or a file) or compose (a mood)")
        return self

    @property
    def label(self) -> str:
        """The source as summaries name it: the bed or file, or ``compose: <mood>``."""
        return self.source if self.source is not None else f"compose: {self.compose.mood}"  # type: ignore[union-attr]


def _music_cue(value: str | MusicCue) -> MusicCue:
    return MusicCue(source=value) if isinstance(value, str) else value


def _no_music(value: Any) -> Any:
    return None if value is False else value


#: A music cue, or a source name (that source with the defaults).
MusicEntry = Annotated[Union[Annotated[str, Field(min_length=1)], MusicCue], AfterValidator(_music_cue)]
#: The video-level ``music:``: a source name, one cue, a list of cues, or ``false`` / null (none).
MusicSetting = Annotated[Union[MusicEntry, list[MusicEntry], Literal[False], None], AfterValidator(_no_music)]


class SceneMusic(_Strict):
    """A scene's ``music:`` override in its long form: its level and, under composed music that
    follows the video (a ``compose:`` cue without ``bars``, DESIGN.md §84), other compose
    settings from this scene's first bar to its end."""

    volume: float = Field(default=0.0, ge=-60, le=12)
    """dB added to the music's volume during this scene."""
    mood: str | None = None
    """Composed music only: another mood for this scene (vidgen list-music); it starts from that mood's defaults."""
    key: str | None = None
    """Composed music only: another key for this scene (a note, or a note with the mood's mode)."""
    tempo: float | None = Field(default=None, ge=40, le=200)
    """Composed music only: another tempo for this scene (quarter notes per minute)."""
    instruments: dict[str, str | ComposeInstrument | None] = Field(default_factory=dict)
    """Composed music only: other instruments for this scene, per part (added to the cue's for the same mood)."""
    seed: int | None = Field(default=None, ge=0)
    """Composed music only: another seed for this scene."""

    @property
    def compose_keys(self) -> list[str]:
        """The compose settings this scene changes (``mood``, ``key``...), in field order."""
        return [k for k in ("mood", "key", "tempo", "seed") if getattr(self, k) is not None] + (["instruments"] if self.instruments else [])

    def instrument_settings(self) -> dict[str, Any]:
        """``instruments`` as plain data for :func:`vidgen.composer.compose`."""
        return {role: v.model_dump() if isinstance(v, ComposeInstrument) else v for role, v in self.instruments.items()}


class AudioConfig(_Strict):
    """The final mix: loudness normalisation (DESIGN.md §48)."""

    normalize: bool | Literal["auto"] = "auto"
    """Normalise the final mix to target_lufs: true, false, or auto (only when the video has music; narration-only videos keep their level)."""
    target_lufs: float = Field(default=-16.0, ge=-40, le=-5)
    """Integrated loudness (EBU R128 / BS.1770) of a normalised mix: -16 for web and social, -23 / -24 for broadcast."""
    true_peak: float = Field(default=-1.5, ge=-9, le=0)
    """Highest true peak (dBTP) of a mixed track; a limiter keeps every peak under it."""


class ChaptersConfig(_Strict):
    """What the render writes about the video's chapters (DESIGN.md §52)."""

    metadata: bool = True
    """Write the chapters into the MP4 (players list them and jump to them)."""
    youtube: bool = True
    """Write <output>_chapters.txt, the chapter list to paste into a YouTube description, and warn when YouTube would ignore it."""
    intro: Annotated[str, Field(min_length=1)] | Literal[False] = "Intro"
    """Title of the chapter added at 0:00 when the first chapter starts later (YouTube needs one at 0:00); false: the first chapter starts at 0:00 instead."""


class MetadataConfig(_Strict):
    """Tags of the final MP4 (DESIGN.md §52); unset tags are not written."""

    title: str | None = Field(default=None, min_length=1)
    """The video's title in players and file browsers (default: the top-level title)."""
    artist: str | None = Field(default=None, min_length=1)
    """Author / channel."""
    album: str | None = Field(default=None, min_length=1)
    """Series or collection."""
    comment: str | None = Field(default=None, min_length=1)
    """A free comment."""
    description: str | None = Field(default=None, min_length=1)
    """A longer description."""
    copyright: str | None = Field(default=None, min_length=1)
    """Copyright notice, e.g. "© 2026 Jane Doe, CC BY 4.0"."""
    date: str | None = Field(default=None, min_length=1)
    """Release date or year, e.g. 2026 or 2026-10-07."""
    genre: str | None = Field(default=None, min_length=1)
    """Genre, e.g. Education."""


#: Keys of a thumbnail grabbed from a scene's frame, and of a designed one (DESIGN.md §53).
THUMBNAIL_FRAME_KEYS = ("scene", "beat", "at", "overlays")
THUMBNAIL_DESIGN_KEYS = ("title", "subtitle", "icon", "image", "preset", "background")


class ThumbnailConfig(_Strict):
    """The video's thumbnail (DESIGN.md §53): a frame of a scene (``scene``, ``beat``, ``at``,
    ``overlays``) or a designed title card (``title``, ``subtitle``, ``icon`` / ``image``,
    ``preset`` / ``background``); without either, a designed card of the video's title."""

    scene: Identifier | None = None
    """Frame thumbnail: the scene whose frame is used."""
    beat: Identifier | PositiveInt | None = None
    """Frame thumbnail: a beat of that scene (its id, or its number from 1); default: the scene's last beat."""
    at: float | None = Field(default=None, ge=0)
    """Frame thumbnail: seconds into the beat (or into the scene without beat); default: the beat's last frame."""
    overlays: bool | None = None
    """Frame thumbnail: draw the video's overlays (captions, watermark...) on the frame; default true (false renders the scene once more without them)."""
    title: str | None = Field(default=None, min_length=1)
    """Designed thumbnail: the big title (a few words); default: the video's title."""
    subtitle: str | None = Field(default=None, min_length=1)
    """Designed thumbnail: a smaller line under the title."""
    icon: str | None = Field(default=None, min_length=1)
    """Designed thumbnail: an icon (vidgen list-icons) beside the title (above it in 9:16)."""
    image: str | None = Field(default=None, min_length=1)
    """Designed thumbnail: a picture (path relative to the project) beside the title (above it in 9:16)."""
    preset: Identifier | None = None
    """Designed thumbnail: draw it in this theme preset's colours and fonts instead of the video's theme."""
    background: ColorRef | None = None
    """Designed thumbnail: background colour (theme token or hex); default: the theme's background."""
    jpeg: bool = False
    """Also write <output>_thumbnail.jpg, under YouTube's 2 MB limit."""
    auto: bool = True
    """Write the thumbnail at the end of every `vidgen render` (false: only with `vidgen thumbnail`)."""

    @model_validator(mode="after")
    def _one_kind(self) -> ThumbnailConfig:
        frame = [k for k in THUMBNAIL_FRAME_KEYS if getattr(self, k) is not None]
        design = [k for k in THUMBNAIL_DESIGN_KEYS if getattr(self, k) is not None]
        if frame and design:
            raise ValueError(
                f"a thumbnail is either a scene's frame ({', '.join(frame)}) or a designed card ({', '.join(design)}), not both"
            )
        if frame and self.scene is None:
            raise ValueError(f"{', '.join(frame)} need scene: the scene whose frame becomes the thumbnail")
        if self.icon is not None and self.image is not None:
            raise ValueError("a designed thumbnail shows an icon or an image, not both")
        return self

    @property
    def kind(self) -> Literal["frame", "design"]:
        """``frame`` (a scene's frame) or ``design`` (a designed title card)."""
        return "frame" if self.scene is not None else "design"


#: Transition types (DESIGN.md §49, §50, §69.45).
TRANSITION_TYPES = ("cut", "crossfade", "fade_color", "push", "wipe", "iris_out", "iris_in")
#: Transitions that overlap the two scenes (both pictures are on screen at once).
OVERLAPPING_TRANSITIONS = ("crossfade", "push", "wipe")
#: Transitions that move a picture or an edge in a ``direction`` (DESIGN.md §50).
DIRECTED_TRANSITIONS = ("push", "wipe")
#: Cartoon irises (DESIGN.md §69.45): a circle closes on the scene before, then opens on the next.
IRIS_TRANSITIONS = ("iris_out", "iris_in")
#: Transitions through a colour, inside the renders: the scene before ends in it, the next
#: scene starts from it (no overlap; fade_color and the irises).
COLOR_TRANSITIONS = ("fade_color", *IRIS_TRANSITIONS)
#: Seconds of a transition when its entry gives no ``duration``.
TRANSITION_DURATIONS = {"cut": 0.0, "crossfade": 0.5, "fade_color": 1.0, "push": 0.6, "wipe": 0.6, "iris_out": 1.2, "iris_in": 1.2}
#: Directions of a push or wipe: where the pictures (push) or the edge (wipe) move.
TransitionDirection = Literal["left", "right", "up", "down"]
#: A transition's ``type`` as written.
TransitionType = Literal["cut", "crossfade", "fade_color", "push", "wipe", "iris_out", "iris_in"]


class TransitionConfig(_Strict):
    """How the video passes into a scene from the one before it (DESIGN.md §49, §50, §69.45)."""

    type: TransitionType = "cut"
    """cut: straight to the next scene (the default: the scene before fades out by itself); crossfade: the two scenes blend; fade_color: the picture fades to a colour and the next scene fades in from it; push: the next scene slides in and pushes the previous one out; wipe: an edge sweeps across, uncovering the next scene; iris_out: a circle closes on a character or point of the scene before, then opens on the next scene; iris_in: a circle closes on the scene before, then opens on a character or point of the next scene."""
    duration: float | None = Field(default=None, gt=0, le=5)
    """Seconds of the transition (default: crossfade 0.5, fade_color 1.0 split evenly between fading out and in, push and wipe 0.6, iris_out and iris_in 1.2 split evenly between closing and opening)."""
    color: ColorRef | None = None
    """fade_color, iris_out, iris_in only: a theme colour token or hex (default: the theme's background for fade_color, black for an iris)."""
    direction: TransitionDirection | None = None
    """push / wipe only: where the pictures (push) or the edge (wipe) move: left, right, up or down (default: left in a wide or square frame, up in a tall one: the next scene comes in from the right / from below)."""
    soft: bool | None = None
    """wipe only: a soft (blurred) edge instead of a hard one (default false)."""
    character: str | None = None
    """iris_out / iris_in only: the character the circle closes on (iris_out: one of the scene before, its head as the scene ends) or opens on (iris_in: one of this scene, its head as it starts); it pauses around the head (default: the point at)."""
    at: tuple[float, float] | None = None
    """iris_out / iris_in only: the point [x, y] the circle closes on (iris_out) or opens on (iris_in), as fractions of the frame from its top-left corner (default: the centre); the other side of the iris uses the centre."""

    @model_validator(mode="after")
    def _keys_of_type(self) -> TransitionConfig:
        if self.type == "cut" and self.duration is not None:
            raise ValueError("a cut has no duration")
        if self.type not in COLOR_TRANSITIONS and self.color is not None:
            raise ValueError(f"color is only for fade_color, iris_out and iris_in, not {self.type}")
        if self.type not in DIRECTED_TRANSITIONS and self.direction is not None:
            raise ValueError(f"direction is only for push and wipe, not {self.type}")
        if self.type != "wipe" and self.soft is not None:
            raise ValueError(f"soft is only for wipe, not {self.type}")
        for key in ("character", "at"):
            if self.type not in IRIS_TRANSITIONS and getattr(self, key) is not None:
                raise ValueError(f"{key} is only for iris_out and iris_in, not {self.type}")
        if self.character is not None and self.at is not None:
            raise ValueError("an iris closes on a character or a point (at), not both")
        if self.at is not None and not all(0.0 <= v <= 1.0 for v in self.at):
            raise ValueError(f"at {list(self.at)}: x and y are fractions of the frame, from 0 to 1")
        return self

    @property
    def through_color(self) -> bool:
        """Whether the scene before ends in a colour the next one starts from (fade_color, iris)."""
        return self.type in COLOR_TRANSITIONS

    @property
    def overlaps(self) -> bool:
        """Whether the scene starts before the one before it ends (crossfade, push, wipe)."""
        return self.type in OVERLAPPING_TRANSITIONS

    @property
    def seconds(self) -> float:
        """``duration``, or the type's default."""
        return self.duration if self.duration is not None else TRANSITION_DURATIONS[self.type]


def _transition(value: str | TransitionConfig) -> TransitionConfig:
    return TransitionConfig(type=value) if isinstance(value, str) else value  # type: ignore[arg-type]


#: A ``transition:`` value: a type name, or {type, duration, color, direction, soft, character, at}.
TransitionSetting = Annotated[Union[TransitionType, TransitionConfig], AfterValidator(_transition)]

#: ``carry:`` entry: ``name`` or ``"name -> other"`` (a target of the scene before -> one of this scene).
CARRY_ARROW = "->"


class CarryEntry(BaseModel):
    """One object a scene carries over from the scene before it (DESIGN.md §50): the target
    ``source`` of that scene, shown where it ended, then moved into this scene's target ``dest``."""

    model_config = ConfigDict(frozen=True)

    source: str
    dest: str

    def __str__(self) -> str:
        return self.source if self.source == self.dest else f"{self.source} {CARRY_ARROW} {self.dest}"


def _carry_entry(value: str) -> CarryEntry:
    parts = [p.strip() for p in value.split(CARRY_ARROW)]
    if len(parts) > 2 or not all(parts):
        raise ValueError(f"invalid carry entry {value!r}: use NAME or 'NAME -> NAME'")
    for name in parts:
        if not re.match(TARGET_NAME_PATTERN, name, re.S):
            raise ValueError(f"invalid target name {name!r} in carry entry {value!r}")
    return CarryEntry(source=parts[0], dest=parts[-1])


def _carry_list(value: str | list[str]) -> list[CarryEntry]:
    entries = [_carry_entry(v) for v in ([value] if isinstance(value, str) else value)]
    seen: set[str] = set()
    for entry in entries:
        if entry.dest in seen:
            raise ValueError(f"two entries move into '{entry.dest}'")
        seen.add(entry.dest)
    return entries


#: A ``carry:`` value: one entry or a list (``title``, ``"title -> heading"``); validated into
#: :class:`CarryEntry` items, written back as the strings.
CarrySetting = Annotated[
    Union[str, list[str]],
    AfterValidator(_carry_list),
    PlainSerializer(lambda entries: [str(e) for e in entries], return_type=list[str]),
]


class ChapterConfig(_Strict):
    """A scene's ``chapter:`` in its long form: a new chapter starts at this scene."""

    title: str = Field(min_length=1)
    """The chapter's name (in the chapter indicator and chapter lists)."""
    number: int | Annotated[str, Field(min_length=1)] | None = None
    """Its number as shown (1, or text such as "Part II"); default its position among the chapters."""


#: ``*word*`` (or ``*a few words*``) in a beat's text: stressed by its speaker (DESIGN.md §69.24).
EMPHASIS = re.compile(r"(?<![\w*])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?![\w*])")


def strip_emphasis(text: str) -> str:
    """``text`` without the asterisks of its ``*word*`` emphasis marks (words and spaces kept)."""
    return EMPHASIS.sub(r"\1", text)


class BeatConfig(_Strict):
    """One narrated sentence/paragraph. ``id`` is filled in by :class:`SceneConfig` if omitted.
    ``text`` is what is spoken and shown: the voice sound markers (``[laugh]``,
    :mod:`vidgen.voicesounds`) are taken out of it here and kept in :attr:`voice_sounds`, then
    the ``*word*`` emphasis marks (:func:`strip_emphasis`), kept in :attr:`marked_text` for
    automatic directing."""

    id: Identifier
    """Unique in the whole video (names audio/<id>.mp3); default <scene id>_b<n> (1-based)."""
    text: str = Field(min_length=1)
    """What the narrator says; also the subtitle. *word* stresses a word (its speaker gestures on it with auto_direct); the asterisks are not spoken or shown. [gasp] [hmm] [laugh] [sigh] [giggle] [groan] are voice sounds at that point (not shown)."""

    _marked_text: str | None = PrivateAttr(default=None)
    _voice_sounds: tuple[VoiceSound, ...] = PrivateAttr(default=())

    @model_validator(mode="after")
    def _take_out_marks(self) -> BeatConfig:
        text, self._voice_sounds = take_out_sounds(self.text)
        if not text.strip():
            raise ValueError("text: has only voice sounds; a beat needs words to say besides [gasp], [laugh]...")
        plain = strip_emphasis(text)
        if plain != text:
            self._marked_text = text
        self.text = plain
        return self

    @property
    def marked_text(self) -> str:
        """The text with its ``*word*`` emphasis marks (voice sound markers taken out: the same
        words as :attr:`text`)."""
        return self._marked_text or self.text

    @property
    def voice_sounds(self) -> tuple[VoiceSound, ...]:
        """The voice sounds of the text, each after its number of words of :attr:`text`."""
        return self._voice_sounds
    actions: list[ActionConfig] = Field(default_factory=list)
    """Per-beat actions on the scene's targets (reveal, dim, highlight, ...), run during this beat."""
    voice: Identifier | None = None
    """Who says this beat: a name from voices (or default: the base voice); default the scene's voice."""
    sting: StingSetting | None = None
    """A short music sting on this beat: reveal, comic or sad, or {kind, at: start | end, gain}; ducked under the narration; played by the composed music's instruments under compose: music."""
    music_pause: bool | None = None
    """Composed music that follows the video: true pauses the music just before this beat (a punchline) until the next bar line after it; false stops the automatic pause (before a card scene, before a short last line)."""
    auto_direct: AutoDirectSetting | None = None
    """On a stage scene: automatic looks and reactions for this beat (true, false or {looks, reactions, gestures, closeups, effects}); default: the scene's, else the video's."""
    shot: ShotConfig | None = Field(default=None, json_schema_extra=_shot_words_schema)
    """On a stage scene: the camera's framing for this beat (wide, two_shot, medium KIT, over_shoulder KIT [NEAR], closeup KIT, or {kind, of, move, run_time}); a cut as the beat starts, back to the view before at the next beat without one."""
    overlap: float | None = Field(default=None, ge=0)
    """Seconds this beat starts before the previous beat's speech ends: both lines are heard (the earlier a little lower) and both mouths move; not on a scene's first beat."""
    interrupt: bool = False
    """This beat cuts the previous beat's line where it starts (a short fade; its mouth stops); starts overlap seconds (default 0.5) before that line's speech ends; not on a scene's first beat."""
    emotion: EmotionSetting | None = None
    """How the line feels: excited, happy, sad, angry, worried, scared, surprised, calm, doubtful, sleepy, whisper, shout or neutral, or {like, speed, pitch, gain, pauses}; Kokoro changes speed, pitch, loudness and pauses; ElevenLabs uses an audio tag (eleven_v3) or voice settings, OpenRouter an instruction or the audio's speed, pitch and loudness; default the voice's emotion."""

    @model_validator(mode="after")
    def _check_interrupt(self) -> BeatConfig:
        if self.interrupt and self.overlap == 0:
            raise ValueError("interrupt: true with overlap: 0 cuts nothing; give the seconds it starts before the line ends (or leave overlap out: 0.5)")
        return self

    @model_validator(mode="after")
    def _time_word_anchors(self) -> BeatConfig:
        """Actions at a spoken word (``at: "@gradient"``): the beat must say it; ``at`` becomes
        its estimated fraction (the video's language and speech rate, then the beat's audio,
        refine it: DESIGN.md §87.2)."""
        if any(act.anchor is not None for act in self.actions):
            time_beat_anchors(self, None, self.estimated_duration(DEFAULT_WORDS_PER_SECOND))
        return self

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
    overlays: SceneOverlays = True
    """Video overlays on this scene: false for none, or per overlay id false / option overrides (with type: an overlay of this scene only)."""
    chapter: Annotated[str, Field(min_length=1)] | ChapterConfig | None = None
    """A new chapter starts at this scene: its title, or {title, number}; a `chapter` scene starts one by itself (this then renames it in chapter lists)."""
    voice: Identifier | None = None
    """Voice of this scene's beats: a name from voices (or default: the base voice); a beat's own voice wins."""
    sfx: list[SfxEntry] = Field(default_factory=list)
    """Sound effects at seconds from the scene's start ({sound, at, gain, pan, align, params}, or a sound name); for silent scenes too."""
    music: bool | SceneMusic = True
    """Background music during this scene: false for none (it fades out before the scene and back in after it), or {volume: dB} to change its level here; under composed music also {mood, key, tempo, instruments, seed} from this scene's first bar."""
    transition: TransitionSetting | None = None
    """How the video passes into this scene from the one before: cut, crossfade, fade_color, push, wipe, iris_out, iris_in or {type, duration, color, direction, soft, character, at}; default the video's transition."""
    carry: CarrySetting = Field(default_factory=list)
    """Objects of the scene before that this scene starts with, where they were (a match cut): its target names, or 'NAME -> NAME' to move one into a target of this scene (default: the target of the same name)."""
    set: Identifier | None = None
    """A stage scene's set: a name from sets:, or a built-in set (city_street, park, beach, forest, snowy_hills; rooms: classroom, kitchen, shop, living_room, bedroom), whose params (background, layers, props, marks, light...) this scene starts from; its own params win."""
    host: SceneHost | None = None
    """The cartoon host beside this scene's content: false for none, a character name, or {character, side, size, place, floor, facing, speaks, pose, expression, auto_direct} changing the video's host here; default the video's host."""

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
        if self.beats and (self.beats[0].overlap is not None or self.beats[0].interrupt):
            key = "overlap" if self.beats[0].overlap is not None else "interrupt"
            raise ValueError(f"beats[0] {key}: the first beat of scene '{self.id}' has no beat before it to overlap or interrupt (a scene's lines overlap only within the scene)")
        for j, beat in enumerate(self.beats):
            for action in beat.actions:
                if action.until is not None and action.until not in order[j + 1 :]:
                    raise ValueError(
                        f"beats[{j}] action '{action.describe()}': until '{action.until}' is not a later beat of "
                        f"scene '{self.id}' (later beats: {', '.join(order[j + 1:]) or 'none'})"
                    )
        for k, cue in enumerate(self.sfx):
            if self.duration is not None and cue.at >= self.duration:
                raise ValueError(f"sfx[{k}]: at {cue.at:g} s is not within the scene's duration ({self.duration:g} s)")
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
    output_dir: str | None = Field(default=None, min_length=1)
    """Folder of the rendered MP4, SRT, chapter list and thumbnail: relative to the project folder, or absolute; default: output."""
    format: FormatConfig = Field(default_factory=FormatConfig)
    """Final render resolution and frame rate."""
    preview: FormatConfig = Field(default_factory=_preview_format)
    """Resolution and frame rate of `vidgen render --preview`."""
    draft: DraftConfig | None = None
    """Resolution and frame rate of `vidgen render --draft` (fast drafts without decoration); default: 240 pixels on the shorter side at the format's shape, 8 fps."""
    include: Annotated[str, Field(min_length=1)] | list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    """YAML / JSON files (relative to this file, e.g. cast.yaml or ../shared/sets.yaml) whose characters, voices and sets this config starts from; this config's own entries win (a character of the same name: its keys win)."""
    sets: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)
    """Named stage sets (name: stage params such as background, layers, props, marks, light, wind, ground_color, width) that a stage scene uses with set: NAME and may override."""
    variants: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)
    """Named overrides deep-merged onto this config (mappings merge, lists and scalars replace)."""
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    """Colors, sizes, font and background."""
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    """Text-to-speech voice."""
    voices: dict[Identifier, VoiceEntry] = Field(default_factory=dict)
    """Named voices for dialogue (name: {voice_id, settings, label, color, ...}), each the base voice with what it sets changed; scenes and beats pick one with voice: NAME."""
    characters: list[CharacterEntry] = Field(default_factory=list)
    """Cartoon characters ({name, voice, look, colors}), declared once and used by any scene; names unique."""
    host: Identifier | HostConfig | None = None
    """A cartoon host drawn beside the content of every scene (not stage or card scenes): a character name, or {character, side, size, place, floor, floor_color, facing, speaks, pose, expression, auto_direct}; a scene's host: wins (false: none there)."""
    subtitles:SubtitlesConfig = Field(default_factory=SubtitlesConfig)
    """What the SRT shows besides the narration (speaker names)."""
    narration: NarrationConfig = Field(default_factory=NarrationConfig)
    """Beat padding and duration estimate."""
    pronunciation: PronunciationMap = Field(default_factory=dict)
    """How the narrator says terms (term: spoken form, or {say, case_sensitive, whole_word, regex}); TTS text only, subtitles keep the written words."""
    pronunciation_file: str | list[str] | None = None
    """YAML/JSON file(s) (relative to the project) with more pronunciation entries; `pronunciation:` entries win over them."""
    language: LanguageTag | None = None
    """Language of the narration and on-screen text (BCP-47: en, pt-BR, es...): caption cutting, narration-speed lint, ElevenLabs language_code, the MP4's audio language; default: English rules, no language sent."""
    translations: str | None = Field(default=None, min_length=1)
    """Translation file (YAML, relative to the project; `vidgen translate-template`) whose texts replace the beat texts and on-screen texts, usually set in a variant."""
    extensions: list[str] = Field(default_factory=lambda: ["extensions"])
    """Folders (relative to the project) whose *.py files and packages are imported."""
    lint: LintConfig = Field(default_factory=LintConfig)
    """Thresholds and severities of `vidgen lint`."""
    overlays: list[OverlayConfig] = Field(default_factory=list)
    """Overlays drawn on top of the scenes (lower thirds, watermark, ...), fixed to the screen."""
    sfx: SfxConfig = Field(default_factory=SfxConfig)
    """Sound effects of the whole video: automatic sounds for built-in animations, overall level."""
    music: MusicSetting = None
    """Background music: a bed name or file, {source | compose, volume, start, loop, crossfade, fade_in, fade_out, duck}, or a list of such cues with from / to scene ids; compose: {mood, ...} composes music."""
    soundfont: str | None = Field(default=None, min_length=1)
    """SoundFont (an .sf2 or .sf3 file, relative to the project) that composed music is played with; default: GeneralUser GS 2.0.3, downloaded once into vidgen's cache (`vidgen soundfont fetch`)."""
    audio: AudioConfig = Field(default_factory=AudioConfig)
    """The final mix: loudness normalisation {normalize, target_lufs, true_peak}."""
    transition: TransitionSetting | None = None
    """Default transition between scenes (cut, crossfade, fade_color, push, wipe, iris_out, iris_in or {type, duration, color, direction, soft, character, at}); a scene's transition wins."""
    chapters: ChaptersConfig = Field(default_factory=ChaptersConfig)
    """What the render writes about the chapters: MP4 chapter entries, the YouTube list <output>_chapters.txt, the intro chapter at 0:00 {metadata, youtube, intro}."""
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    """Tags of the final MP4 {title, artist, album, comment, description, copyright, date, genre}; title defaults to the top-level title."""
    thumbnail: ThumbnailConfig | None = None
    """The thumbnail <output>_thumbnail.png: a scene's frame {scene, beat, at, overlays} or a designed card {title, subtitle, icon, image, preset, background}, + {jpeg, auto}."""
    stt: SttConfig = Field(default_factory=SttConfig)
    """Speech to text for `vidgen readback` (the narration transcribed and compared with the text): {provider, model, language, device}."""
    imagegen: ImagegenConfig = Field(default_factory=ImagegenConfig)
    """Image generation for generate: params and `vidgen imagegen`: {provider (openai or openrouter), model, size, quality, resolution, style, negative}."""
    cartoon_style: str | None = Field(default=None, min_length=1)
    """Style words added to every generate: prompt of stage scenes, so a cartoon's backgrounds look alike, e.g. "flat colours, thick outlines, soft shadows"; part of the picture's cache key."""
    foley: bool = True
    """Sounds for the characters' actions on stage scenes: footsteps on walks, a whoosh on enter / exit, a boing on jump, a pop on a surprised face, a sound with most effect symbols; false: none (a stage's foley param wins)."""
    ambience: bool = True
    """A sound bed chosen from each stage scene's set while foley is on: a room tone in a room, birdsong outdoors while the light is day or morning and it does not rain; false: none unless a stage's ambience param names one."""
    auto_direct: AutoDirectSetting = False
    """Automatic directing on stage scenes: listeners look at whoever speaks and react after lines (true, false or {looks, reactions, gestures, closeups, effects}); a stage's or a beat's setting wins; actions written in a beat always win."""
    character_size: CharacterSize | None = None
    """How big the characters are on stage scenes: small (a wide landscape, for cinema), medium (TV / YouTube) or large (big characters, for phones and Shorts); on a platform level the tiles, props, coins and stars scale with them; captions, on-screen text and speech bubbles keep their size; a stage's character_size or size param wins; default medium."""
    reframe: ReframeSetting | None = None
    """On stage scenes wider than the frame (a 9:16 variant crops the landscape stage): speaker moves the camera to whoever speaks, easing between speakers and holding during short replies; none: only the beats' own pan / follow / zoom / shot move it; default: speaker when the characters do not fit in one view (a stage's reframe param wins)."""
    cartoon_motion: MotionSetting | None = None
    """Animation principles for every character (anticipation, squash and stretch, overshoot and settle, follow-through): lively, calm or none; a stage's or a character's own setting wins; default lively."""
    motion_effects: bool = True
    """Motion effects on stage scenes, added on their own while cartoon_motion is lively or calm (smaller): dust where a run sets off and stops and where a jump lands, speed lines behind runs, fast walks and thrown or blown props, impact stars on a hard landing, a whoosh arc on a big gesture; false: none (a stage's motion_effects param wins)."""
    drawing: DrawingConfig | None = None
    """How the cartoons are drawn {outline: thin | normal | bold, shading: flat | soft, texture: none | paper | storybook, seed}: stage scenes and the host; a stage's drawing param wins key by key; default: normal, flat, none (as drawn)."""
    scenes: list[SceneConfig] = Field(min_length=1)
    """The scenes in order (at least one); scene ids and beat ids must be unique."""

    @field_validator("variants")
    @classmethod
    def _variants_cannot_nest(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        for name, override in value.items():
            for key in ("variants", "include"):
                if key in override:
                    raise ValueError(f"variant '{name}' must not contain '{key}'")
        return value

    @field_validator("voices")
    @classmethod
    def _reserved_voice(cls, value: dict[str, VoiceEntry]) -> dict[str, VoiceEntry]:
        from vidgen.voices import DEFAULT_VOICE

        if DEFAULT_VOICE in value:
            raise ValueError(f"'{DEFAULT_VOICE}' is the base voice (the voice: section) and cannot be a name in voices")
        return value

    @field_validator("characters")
    @classmethod
    def _unique_character_names(cls, value: list[CharacterEntry]) -> list[CharacterEntry]:
        seen: dict[str, int] = {}
        for k, entry in enumerate(value):
            if entry.name in seen:
                raise ValueError(f"duplicate character name '{entry.name}' (characters[{seen[entry.name]}] and characters[{k}])")
            seen[entry.name] = k
        return value

    @field_validator("pronunciation", mode="before")
    @classmethod
    def _one_form(cls, value: Any) -> Any:
        from vidgen.pronunciation import form_problems

        problems = form_problems(value) if isinstance(value, dict) else []
        if problems:
            raise ValueError("; ".join(problems))
        return value

    @field_validator("pronunciation")
    @classmethod
    def _compilable(cls, value: dict[str, Any]) -> dict[str, Any]:
        from vidgen.pronunciation import entry_problems

        problems = entry_problems(value)
        if problems:
            raise ValueError("; ".join(problems))
        return value

    @property
    def include_files(self) -> list[str]:
        """``include`` as a list (empty when unset)."""
        return [self.include] if isinstance(self.include, str) else list(self.include)

    @property
    def pronunciation_files(self) -> list[str]:
        """``pronunciation_file`` as a list (empty when unset)."""
        value = self.pronunciation_file
        return [] if value is None else [value] if isinstance(value, str) else list(value)

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
        from vidgen.chapters import chapter_problems

        problems = chapter_problems(self.scenes) + self._music_problems(scene_seen)
        if self.thumbnail is not None:
            problems += self.thumbnail_problems(self.thumbnail)
        first = self.scenes[0].transition
        if first is not None and (first.overlaps or first.type == "iris_out"):
            problems.append(
                f"scenes[0].transition: the first scene has no scene before it to {first.type} from "
                "(fade_color fades it in from a colour, iris_in opens on it)"
            )
        if self.scenes[0].carry:
            problems.append("scenes[0].carry: the first scene has no scene before it to carry objects from")
        if problems:
            raise ValueError("; ".join(problems))
        time_config_anchors(self)
        return self

    def thumbnail_problems(self, thumb: ThumbnailConfig) -> list[str]:
        """A frame thumbnail ``thumb`` names a scene of this video and one of its beats."""
        if thumb.scene is None:
            return []
        index = {s.id: i for i, s in enumerate(self.scenes)}
        if thumb.scene not in index:
            return [f"thumbnail.scene: unknown scene '{thumb.scene}' (scenes: {', '.join(index)})"]
        scene = self.scenes[index[thumb.scene]]
        if thumb.beat is None:
            return []
        ids = [b.id for b in scene.beats]
        if not ids:
            return [f"thumbnail.beat: scene '{scene.id}' has no beats (it is silent); use at: seconds into the scene"]
        if isinstance(thumb.beat, int):
            if thumb.beat > len(ids):
                return [f"thumbnail.beat: scene '{scene.id}' has {len(ids)} beat(s), not {thumb.beat}"]
        elif thumb.beat not in ids:
            return [f"thumbnail.beat: scene '{scene.id}' has no beat '{thumb.beat}' (beats: {', '.join(ids)})"]
        return []

    def _music_problems(self, index: dict[str, int]) -> list[str]:
        """Cues name existing scenes, in order (``from`` not after ``to``), without overlapping."""
        problems: list[str] = []
        spans: list[tuple[int, int, str]] = []
        listed = isinstance(self.music, list)
        for k, cue in enumerate(self.music_cues):
            where = f"music[{k}]" if listed else "music"
            bad = [f"{key} '{sid}'" for key, sid in (("from", cue.from_), ("to", cue.to)) if sid is not None and sid not in index]
            if bad:
                problems.append(f"{where}: unknown scene {', '.join(bad)} (scenes: {', '.join(index)})")
                continue
            first = index[cue.from_] if cue.from_ is not None else 0
            last = index[cue.to] if cue.to is not None else len(self.scenes) - 1
            if first > last:
                problems.append(f"{where}: from '{cue.from_}' comes after to '{cue.to}'")
                continue
            for a, b, other in spans:
                if first <= b and a <= last:
                    problems.append(f"{where} overlaps {other} (each scene can have one music cue)")
            spans.append((first, last, where))
        return problems + self._scene_compose_problems(index)

    def _scene_compose_problems(self, index: dict[str, int]) -> list[str]:
        """A scene's ``music: {mood, key, ...}`` needs a fitted ``compose:`` cue over the scene
        (no ``bars``) and must compose."""
        from vidgen.composer import settings_problems
        from vidgen.musicfit import cue_settings, is_fitted, scene_settings

        problems: list[str] = []
        cues = self.music_cues
        for i, scene in enumerate(self.scenes):
            if not isinstance(scene.music, SceneMusic) or not scene.music.compose_keys:
                continue
            where = f"scenes[{i}].music"
            covering = [c for c in cues if (index.get(c.from_, -1) if c.from_ else 0) <= i <= (index.get(c.to, -1) if c.to else len(self.scenes) - 1)]
            if not covering or not is_fitted(covering[0]):
                keys = ", ".join(scene.music.compose_keys)
                problems.append(f"{where}: {keys} change composed music that follows the video: put the scene under a music cue with compose: and no bars")
                continue
            settings = scene_settings(cue_settings(covering[0].compose), scene.music)  # type: ignore[arg-type]
            for problem in settings_problems(settings.mood, settings.key, settings.tempo, settings.instruments):
                problems.append(f"{where}: {problem}")
        return problems

    @property
    def music_cues(self) -> list[MusicCue]:
        """``music`` as a list of cues (empty without music)."""
        value = self.music
        return [] if value is None else list(value) if isinstance(value, list) else [value]


def format_location(loc: tuple[str | int, ...]) -> str:
    """Render a pydantic error location as a config path, e.g. ``scenes[2].beats[0].id``."""
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def validation_problems(
    error: ValidationError, prefix: tuple[str | int, ...] = (), model: type[BaseModel] | None = None, noun: str = "parameter"
) -> list[Problem]:
    """One :class:`~vidgen.errors.Problem` per error; ``prefix`` is prepended to every location
    (e.g. ``("scenes", 2, "params")`` gives ``scenes[2].params.values``). With ``model`` (the
    model validated), an unknown key gets a did-you-mean message and the known names (``noun``:
    what a key is called, e.g. ``option``)."""
    from vidgen.describe import unknown_key_message

    problems = []
    for item in error.errors():
        # Model validators raise from the model itself; drop pydantic's "Value error, " prefix.
        message = item["msg"].removeprefix("Value error, ")
        if item["type"] == "extra_forbidden" and model is not None:
            message = unknown_key_message(model, item["loc"], noun) or message
        problems.append(Problem(format_location((*prefix, *item["loc"])), message))
    return problems


def validation_error_lines(error: ValidationError, prefix: tuple[str | int, ...] = (), model: type[BaseModel] | None = None) -> list[str]:
    """One ``path: message`` line per error (see :func:`validation_problems`)."""
    return [str(problem) for problem in validation_problems(error, prefix, model)]


def format_validation_error(error: ValidationError, source: str, model: type[BaseModel] | None = None) -> str:
    """A readable multi-line message for a pydantic ``ValidationError`` (of ``model``, which
    improves unknown-key messages)."""
    lines = [f"{source}: invalid config"]
    lines.extend(f"  {problem}" for problem in validation_problems(error, model=model, noun="key"))
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
        config = VideoConfig.model_validate(data)
    except ValidationError as exc:
        raise VidgenError(format_validation_error(exc, source, VideoConfig), problems=validation_problems(exc, model=VideoConfig, noun="key")) from None
    from vidgen.cartoon.host import host_problems
    from vidgen.includes import set_reference_problems
    from vidgen.voices import voice_provider_problems, voice_reference_problems

    problems = voice_reference_problems(config) + voice_provider_problems(config) + set_reference_problems(config) + host_problems(config)
    if problems:
        lines = [f"{source}: invalid config", *(f"  {problem}" for problem in problems)]
        raise VidgenError("\n".join(lines), problems=problems)
    return config
