"""Text-to-speech: the provider seam and the audio cache status (DESIGN.md §7).

- :func:`get_provider` returns the provider for a ``voice`` config: ElevenLabs
  (:mod:`vidgen.tts.elevenlabs`, the default) or OpenRouter (:mod:`vidgen.tts.openrouter`); one
  provider per video (DESIGN.md §66).
- :func:`audio_status` tells, without an API key, which beats have up-to-date, stale or missing
  audio; ``vidgen render`` uses it to warn and ``vidgen validate`` to summarise.
- :func:`vidgen.tts.run.run_tts` is the ``vidgen tts`` command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from vidgen.config import TTS_PROVIDERS, VoiceConfig
from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.project import Project


class TTSProvider(Protocol):
    """What the TTS command needs from a provider. Constructing one never needs an API key.

    A provider that can say when each character is spoken also has ``synthesize_timed(text,
    previous_text=None, next_text=None) -> (audio, alignment | None)`` (``alignment``:
    ``{characters, character_start_times_seconds, character_end_times_seconds}``); ``vidgen
    tts`` calls it when ``voice.timestamps`` is on and stores the alignment next to the MP3
    (:func:`vidgen.speech.write_alignment`)."""

    name: str

    def cache_key(self, text: str) -> str:
        """Hash written to ``<beat_id>.hash`` after generating ``text``."""

    def matches(self, text: str, stored: str) -> bool:
        """True if a stored hash means the audio for ``text`` is up to date."""

    def check_credentials(self) -> None:
        """Raise ``VidgenError`` (with setup instructions) if the API key is not available."""

    def synthesize(self, text: str, previous_text: str | None = None, next_text: str | None = None) -> bytes:
        """Audio bytes for ``text``; neighbours are context only. Raises ``VidgenError``."""


def get_provider(voice: VoiceConfig) -> TTSProvider:
    """The provider for ``voice.provider`` (ElevenLabs, or OpenRouter: DESIGN.md §66)."""
    if voice.provider == "elevenlabs":
        from vidgen.tts.elevenlabs import ElevenLabsProvider

        return ElevenLabsProvider(voice)
    if voice.provider == "openrouter":
        from vidgen.tts.openrouter import OpenRouterTTSProvider

        return OpenRouterTTSProvider(voice)
    raise VidgenError(f"unknown voice provider {voice.provider!r}; available: {', '.join(TTS_PROVIDERS)}")


def tts_warnings(project: Project) -> list[str]:
    """What ``vidgen validate`` warns about the voices (no network): OpenRouter models and voices
    not in the bundled list, ``timestamps`` with a provider that returns no timings."""
    from vidgen.tts.openrouter import model_warnings

    used = set(project.voice_names().values())
    out: list[str] = []
    seen: set[str] = set()  # a named voice inheriting the base model says the same once
    for name in [None, *(n for n in project.config.voices if n in used)]:
        for warning in model_warnings(project.voice(name), "voice" if name is None else f"voices.{name}"):
            said = warning.split(": ", 1)[-1]
            if said not in seen:
                seen.add(said)
                out.append(warning)
    return out


def beat_providers(project: Project) -> dict[str, TTSProvider]:
    """Beat id -> the provider of the beat's effective voice (DESIGN.md §46; one provider per
    voice), in video order."""
    by_voice: dict[str | None, TTSProvider] = {}
    out: dict[str, TTSProvider] = {}
    for beat_id, name in project.voice_names().items():
        if name not in by_voice:
            by_voice[name] = get_provider(project.voice(name))
        out[beat_id] = by_voice[name]
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
