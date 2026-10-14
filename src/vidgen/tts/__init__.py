"""Text-to-speech: the provider seam and the audio cache status (DESIGN.md §7).

- :func:`get_provider` returns the provider for a ``voice`` config: ElevenLabs
  (:mod:`vidgen.tts.elevenlabs`, the default), OpenRouter (:mod:`vidgen.tts.openrouter`) or
  Kokoro on this computer (:mod:`vidgen.tts.kokoro`, an optional extra); one provider per video
  (DESIGN.md §66, §68).
- :func:`audio_status` tells, without an API key, which beats have up-to-date, stale or missing
  audio; ``vidgen render`` uses it to warn and ``vidgen validate`` to summarise.
- :func:`vidgen.tts.run.run_tts` is the ``vidgen tts`` command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from vidgen.config import TTS_PROVIDERS, VoiceConfig
from vidgen.emotions import Prosody
from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.project import Project

#: Providers that speak a beat's ``emotion`` (DESIGN.md §72); the others ignore it.
EMOTION_PROVIDERS: tuple[str, ...] = ("kokoro",)


class TTSProvider(Protocol):
    """What the TTS command needs from a provider. Constructing one never needs an API key.

    A provider that can say when each character is spoken also has ``synthesize_timed(text,
    previous_text=None, next_text=None) -> (audio, alignment | None)`` (``alignment``:
    ``{characters, character_start_times_seconds, character_end_times_seconds}``); ``vidgen
    tts`` calls it when ``voice.timestamps`` is on, or always when the provider's
    ``timings_included`` is true (Kokoro: the timings cost nothing), and stores the alignment
    next to the MP3 (:func:`vidgen.speech.write_alignment`)."""

    name: str

    def cache_key(self, text: str) -> str:
        """Hash written to ``<beat_id>.hash`` after generating ``text``."""

    def matches(self, text: str, stored: str) -> bool:
        """True if a stored hash means the audio for ``text`` is up to date."""

    def check_credentials(self) -> None:
        """Raise ``VidgenError`` (with setup instructions) if the API key is not available."""

    def synthesize(self, text: str, previous_text: str | None = None, next_text: str | None = None) -> bytes:
        """Audio bytes for ``text``; neighbours are context only. Raises ``VidgenError``."""


def get_provider(voice: VoiceConfig, emotion: Prosody | None = None) -> TTSProvider:
    """The provider for ``voice.provider`` (ElevenLabs, OpenRouter: DESIGN.md §66, or Kokoro on
    this computer: §68) speaking with ``emotion`` (§72; only Kokoro uses it so far). Constructing
    one loads no model and needs no key."""
    if voice.provider == "elevenlabs":
        from vidgen.tts.elevenlabs import ElevenLabsProvider

        return ElevenLabsProvider(voice)
    if voice.provider == "openrouter":
        from vidgen.tts.openrouter import OpenRouterTTSProvider

        return OpenRouterTTSProvider(voice)
    if voice.provider == "kokoro":
        from vidgen.tts.kokoro import KokoroProvider

        return KokoroProvider(voice, emotion=emotion)
    raise VidgenError(f"unknown voice provider {voice.provider!r}; available: {', '.join(TTS_PROVIDERS)}")


def tts_warnings(project: Project) -> list[str]:
    """What ``vidgen validate`` warns about the voices (no network): OpenRouter models and voices
    not in the bundled list, Kokoro voices not in its list or of another language, the Kokoro
    extra not installed, ``timestamps`` with a provider or language that returns no timings."""
    from vidgen.tts import kokoro
    from vidgen.tts.openrouter import model_warnings

    used = set(project.voice_names().values())
    names = [None, *(n for n in project.config.voices if n in used)]
    out: list[str] = []
    seen: set[str] = set()  # a named voice inheriting the base model says the same once
    for name in names:
        voice, where = project.voice(name), "voice" if name is None else f"voices.{name}"
        for warning in [*model_warnings(voice, where), *kokoro.voice_warnings(voice, where, project.config.language)]:
            said = warning.split(": ", 1)[-1]
            if said not in seen:
                seen.add(said)
                out.append(warning)
    return out + kokoro.install_warnings(project.voice(n) for n in names) + emotion_warnings(project)


def emotion_warnings(project: Project) -> list[str]:
    """A warning naming the beats whose ``emotion`` their voice's provider does not speak yet."""
    ignored = [
        beat_id for beat_id, name in project.voice_names().items()
        if project.voice(name).provider not in EMOTION_PROVIDERS and project.beat_emotion(beat_id) is not None
    ]
    if not ignored:
        return []
    shown = ", ".join(ignored[:5]) + (f" and {len(ignored) - 5} more" if len(ignored) > 5 else "")
    providers = ", ".join(EMOTION_PROVIDERS)
    return [f"emotion: only {providers} voices speak an emotion so far; the audio of {shown} ignores it"]


def beat_providers(project: Project) -> dict[str, TTSProvider]:
    """Beat id -> the provider of the beat's effective voice and emotion (DESIGN.md §46, §72; one
    provider per voice and emotion), in video order."""
    made: dict[tuple[str | None, Prosody | None], TTSProvider] = {}
    out: dict[str, TTSProvider] = {}
    for beat_id, name in project.voice_names().items():
        voice = project.voice(name)
        key = (name, project.beat_emotion(beat_id) if voice.provider in EMOTION_PROVIDERS else None)
        if key not in made:
            made[key] = get_provider(voice, key[1])
        out[beat_id] = made[key]
    return out


from vidgen.tts.cache import (  # noqa: E402
    BeatAudioStatus,
    audio_status,
    format_audio_summary,
    orphaned_audio,
)

__all__ = [
    "BeatAudioStatus",
    "TTSProvider",
    "audio_status",
    "beat_providers",
    "format_audio_summary",
    "get_provider",
    "orphaned_audio",
    "tts_warnings",
]
