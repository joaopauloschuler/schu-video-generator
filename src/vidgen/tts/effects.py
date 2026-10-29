"""A voice's ``effect:`` applied to every beat it says, whatever the provider (DESIGN.md §100.2).

:class:`EffectProvider` wraps a provider: it synthesises with it, then runs the audio through the
effect's ffmpeg filter chain (:func:`vidgen.voice_effects.effect_filter`) and encodes it as MP3
again. The hash is the wrapped provider's with the effect added, so a voice without an effect
keeps every hash, and changing the effect re-voices that voice's beats. The word timings and the
lip-sync phonemes of the wrapped provider are kept: no effect moves the speech in time (the
tails come after it).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from vidgen.voice_effects import VoiceEffect, effect_filter


def with_effect(mp3: bytes, effect: VoiceEffect, ffmpeg: str | None = None) -> bytes:
    """``mp3`` (any audio ffmpeg reads) through ``effect``, as MP3."""
    from vidgen.tts.openrouter import convert_to_mp3

    return convert_to_mp3(mp3, [], ffmpeg, source="the voice effect's audio", filters=effect_filter(effect))


class EffectProvider:
    """``inner`` (any provider) speaking through ``effect``. Everything else (its name, its
    timings, the phonemes of its last line, what it reports) is the inner provider's."""

    def __init__(self, inner: Any, effect: VoiceEffect, *, ffmpeg: str | None = None) -> None:
        self.inner = inner
        self.effect = effect
        self._ffmpeg = ffmpeg

    def __getattr__(self, name: str) -> Any:
        if name == "inner":   # not set yet (copy, pickle)
            raise AttributeError(name)
        return getattr(self.inner, name)

    def cache_key(self, text: str) -> str:
        """sha1 of the inner provider's hash and the effect's spec."""
        head = json.dumps(self.effect.spec(), sort_keys=True)
        return hashlib.sha1(f"{self.inner.cache_key(text)}|effect|{head}".encode("utf-8")).hexdigest()

    def matches(self, text: str, stored: str) -> bool:
        """True if a stored hash says the audio for ``text`` is up to date."""
        return stored.strip() == self.cache_key(text)

    def check_credentials(self) -> None:
        """The inner provider's check."""
        self.inner.check_credentials()

    def synthesize(self, text: str, previous_text: str | None = None, next_text: str | None = None) -> bytes:
        """The inner provider's audio for ``text`` through the effect."""
        return with_effect(self.inner.synthesize(text, previous_text, next_text), self.effect, self._ffmpeg)

    def synthesize_timed(
        self, text: str, previous_text: str | None = None, next_text: str | None = None
    ) -> tuple[bytes, dict[str, list[Any]] | None]:
        """The inner provider's audio and timings (``None`` when it gives none) with the effect."""
        timed = getattr(self.inner, "synthesize_timed", None)
        if timed is None:
            return self.synthesize(text, previous_text, next_text), None
        audio, alignment = timed(text, previous_text, next_text)
        return with_effect(audio, self.effect, self._ffmpeg), alignment


__all__ = ["EffectProvider", "with_effect"]
