"""Named voices: who says each beat, and how speakers are shown (DESIGN.md §46). No manim.

A project's base ``voice:`` narrates every beat unless a scene or a beat names another voice
from ``voices:``. A named voice is the base voice with the keys it gives changed (``settings``
merge value by value); its ``label`` and ``color`` name the speaker in subtitles and captions
and are never inherited. The name ``default`` means the base voice (e.g. a beat back to the
narrator inside a scene of another voice).

The audio of a beat is hashed with its effective voice (``provider.cache_key`` of that voice),
so a beat of the base voice keeps its hash, and editing one named voice re-voices only its beats.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from vidgen.config import VideoConfig, VoiceConfig
from vidgen.errors import Problem, VidgenError

if TYPE_CHECKING:
    from vidgen.theme import Theme

#: The name of the base voice (the ``voice:`` section) wherever a voice name is expected.
DEFAULT_VOICE = "default"
#: Fields of a voice that name the speaker and do not change its audio.
DISPLAY_FIELDS = frozenset({"label", "color"})


def voice_names(config: VideoConfig) -> list[str]:
    """Every name a scene or beat may use: ``default`` and the ``voices:`` names."""
    return [DEFAULT_VOICE, *config.voices]


def unknown_voice_message(name: str, known: Iterable[str]) -> str:
    """``unknown voice 'anna'; did you mean 'ana'? voices: default, ana, ben``."""
    known = list(known)
    close = difflib.get_close_matches(name, known, n=1, cutoff=0.6)
    hint = f"; did you mean '{close[0]}'?" if close else ""
    return f"unknown voice '{name}'{hint} voices: {', '.join(known)} (define more under voices:)"


def voice_reference_problems(config: VideoConfig) -> list[Problem]:
    """Scene and beat ``voice:`` names that are not in ``voices:`` (nor ``default``)."""
    known = voice_names(config)
    problems = []
    for i, scene in enumerate(config.scenes):
        if scene.voice is not None and scene.voice not in known:
            problems.append(Problem(f"scenes[{i}].voice", unknown_voice_message(scene.voice, known)))
        for j, beat in enumerate(scene.beats):
            if beat.voice is not None and beat.voice not in known:
                problems.append(Problem(f"scenes[{i}].beats[{j}].voice", unknown_voice_message(beat.voice, known)))
    return problems


def resolve_voice(config: VideoConfig, name: str | None) -> VoiceConfig:
    """The effective voice called ``name`` (``None`` / ``default``: the base voice): the base
    voice's audio settings with the named voice's given values over them; ``label`` / ``color``
    only from the named voice."""
    if name is None or name == DEFAULT_VOICE:
        return config.voice
    entry = config.voices.get(name)
    if entry is None:
        raise VidgenError(unknown_voice_message(name, voice_names(config)))
    data: dict[str, Any] = config.voice.model_dump(exclude=set(DISPLAY_FIELDS))
    given = entry.model_dump(exclude_none=True)
    settings = given.pop("settings", None)
    data.update(given)
    if settings:
        data["settings"] = {**data["settings"], **settings}
    return VoiceConfig.model_validate(data)


def audio_fields(voice: VoiceConfig) -> dict[str, Any]:
    """What of ``voice`` the audio depends on (everything but the speaker's label and colour)."""
    return voice.model_dump(exclude=set(DISPLAY_FIELDS))


def beat_voice_names(config: VideoConfig) -> dict[str, str | None]:
    """Beat id -> the name of the voice that says it (the beat's ``voice``, else its scene's;
    ``None`` for the base voice), in video order."""
    out: dict[str, str | None] = {}
    for scene in config.scenes:
        for beat in scene.beats:
            name = beat.voice if beat.voice is not None else scene.voice
            out[beat.id] = None if name == DEFAULT_VOICE else name
    return out


def speaker_label(config: VideoConfig, name: str | None) -> str | None:
    """How subtitles name the speaker of voice ``name``: its ``label``; for a named voice
    without one its name (``dr_ana`` -> ``Dr ana``); ``None`` for a base voice without a label."""
    if name is None:
        return config.voice.label
    entry = config.voices[name]
    if entry.label is not None:
        return entry.label
    text = name.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else name


def speaker_color(config: VideoConfig, name: str | None, theme: Theme) -> str:
    """The speaker's colour as hex: its ``color``; else for a named voice the palette colour
    of its position in ``voices:``, for the base voice the theme's ``text``."""
    if name is None:
        return theme.color(config.voice.color or "text")
    entry = config.voices[name]
    if entry.color is not None:
        return theme.color(entry.color)
    return theme.palette_color(list(config.voices).index(name))


def speaker_tags(config: VideoConfig, names: Mapping[str, str | None] | None = None) -> dict[str, str]:
    """Beat id -> the speaker label to show before the beat, for every beat (video order) whose
    voice differs from the previous beat's (the first beat included) and that has a label."""
    names = beat_voice_names(config) if names is None else names
    tags: dict[str, str] = {}
    previous: object = object()
    for beat_id, name in names.items():
        if name != previous:
            label = speaker_label(config, name)
            if label:
                tags[beat_id] = label
        previous = name
    return tags


def speaker_prefix(label: str) -> str:
    """The tag before a speaker's words in subtitles and captions: ``"Ana:"``."""
    return f"{label}:"


def voice_color_problems(config: VideoConfig, theme: Theme) -> list[Problem]:
    """``color`` values of ``voice`` / ``voices`` that are not theme colours."""
    problems = []
    entries: list[tuple[str, str | None]] = [("voice.color", config.voice.color)]
    entries += [(f"voices.{name}.color", entry.color) for name, entry in config.voices.items()]
    for where, color in entries:
        if color is not None:
            try:
                theme.color(color)
            except VidgenError as exc:
                problems.append(Problem(where, str(exc)))
    return problems


def voice_warnings(config: VideoConfig) -> list[str]:
    """Named voices no scene or beat uses (``vidgen validate`` warns)."""
    used = set(beat_voice_names(config).values())
    return [f"voices: '{name}' is not used by any scene or beat" for name in config.voices if name not in used]
