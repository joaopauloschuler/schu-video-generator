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
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from vidgen.voice_effects import EFFECT_RATE, MATCH_LIMIT, VoiceEffect, effect_filter


def level_match(dry: np.ndarray, wet: np.ndarray) -> float:
    """dB that bring ``wet``'s integrated loudness to ``dry``'s (mono samples at
    :data:`~vidgen.voice_effects.EFFECT_RATE`), within ±:data:`~vidgen.voice_effects.MATCH_LIMIT`;
    0 when either is silent or too short to measure."""
    from vidgen.loudness import integrated_loudness

    before, after = integrated_loudness(dry), integrated_loudness(wet)
    if not (math.isfinite(before) and math.isfinite(after)):
        return 0.0
    return float(np.clip(before - after, -MATCH_LIMIT, MATCH_LIMIT))


def with_effect(mp3: bytes, effect: VoiceEffect, ffmpeg: str | None = None) -> bytes:
    """``mp3`` (any audio ffmpeg reads) through ``effect``, as MP3, level-matched to the dry
    voice (:func:`level_match`; a limiter keeps the peaks below full scale)."""
    from vidgen.render.ffmpeg import decode_mono, find_ffmpeg, run_ffmpeg
    from vidgen.tts.openrouter import convert_to_mp3

    exe = ffmpeg or find_ffmpeg()
    with tempfile.TemporaryDirectory(prefix="vidgen-fx-") as folder:
        given, wet = Path(folder) / "in.audio", Path(folder) / "wet.wav"
        given.write_bytes(mp3)
        run_ffmpeg(exe, ["-i", str(given), "-af", effect_filter(effect), "-c:a", "pcm_f32le", str(wet)], "applying a voice effect")
        gain = level_match(decode_mono(given, EFFECT_RATE), decode_mono(wet, EFFECT_RATE))
        filters = f"volume={gain:.2f}dB,alimiter=limit=0.89:level=false"
        return convert_to_mp3(wet.read_bytes(), [], ffmpeg, source="the voice effect's audio", filters=filters)


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


__all__ = ["EffectProvider", "level_match", "with_effect"]
