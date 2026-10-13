"""Ambience (DESIGN.md §69.39, §69.55): a generated sound bed under the scenes while something on
screen lasts: ``rain`` under a stage's rain field and ``fire`` (a crackle) while a fireplace burns,
both while foley is on (:data:`BEDS`).

The rain bed is a seamless 8 s stereo loop made with numpy only (no recordings, deterministic):
a soft hiss (noise band-passed around 2.5 kHz), many small drop ticks (sparse impulses
band-passed around 3.5 kHz) and fewer, lower plops (around 900 Hz), each channel drawn on its
own (wide), with a slow swell of whole cycles per loop. All filtering is circular (one FFT over
the loop), so it repeats without a seam. It is set to :data:`RAIN_LEVEL` integrated loudness and
mixed by :func:`vidgen.mix.plan_ambience` like the music, fading in and out with the rain and
ducking under the narration by less than the music (:data:`RAIN_DUCK`).
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

from vidgen.config import DuckConfig
from vidgen.loudness import integrated_loudness
from vidgen.sfx import RATE, _band, _highpass, _lowpass

#: The ambience beds a scene's timings may name (``ambience: [{bed, start, end}]``).
AMBIENCE_BEDS = ("rain", "fire")
#: Integrated loudness (LUFS) of the rain bed before ducking: 4 dB under the music's
#: (:data:`vidgen.music.MUSIC_LEVEL` -28), so about 11 dB under narration in its pauses.
RAIN_LEVEL = -32.0
#: How the rain ducks under the narration: 5 dB (the music: 12), so it stays audible under the
#: voice, about 16 dB under it, without masking a word.
RAIN_DUCK = DuckConfig(depth=5.0, attack=0.4, release=1.0, hold=1.5, clips=False)
#: Seconds of fade at the start and end of the rain (ending where the rain ends).
RAIN_FADE_IN = 1.5
RAIN_FADE_OUT = 1.5
#: Spans of the same bed less than this apart (seconds) play as one, without a dip (rain from one
#: stage scene into the next).
JOIN_GAP = 0.25
#: Length of the rain loop (seconds).
RAIN_LOOP_SECONDS = 8.0


def merge_spans(spans: Iterable[tuple[float, float]], gap: float = JOIN_GAP) -> list[tuple[float, float]]:
    """``spans`` (start, end seconds) sorted, overlapping ones and ones less than ``gap`` apart
    joined, empty ones dropped."""
    merged: list[tuple[float, float]] = []
    for start, end in sorted(s for s in spans if s[1] > s[0]):
        if merged and start - merged[-1][1] < gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def ambience_spans(timings: Mapping[str, Any], bed: str) -> list[tuple[float, float]]:
    """The video seconds where ``bed`` plays: every scene's ``ambience`` entries of that bed in
    the combined ``timings`` (already at video times), merged (:func:`merge_spans`)."""
    return merge_spans(
        (float(entry["start"]), float(entry["end"]))
        for scene in timings["scenes"]
        for entry in scene.get("ambience", [])
        if entry["bed"] == bed
    )


def _circular(x: np.ndarray, gain: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """``x`` filtered by the magnitude response ``gain(Hz)`` around a circle (one FFT of its
    length), so the result loops without a seam; RMS 1."""
    out = np.fft.irfft(np.fft.rfft(x) * gain(np.fft.rfftfreq(len(x), 1 / RATE)), len(x))
    return out / max(float(np.sqrt(np.mean(out**2))), 1e-12)


def _impulses(rng: np.random.Generator, n: int, count: int) -> np.ndarray:
    """``count`` impulses at random places of ``n`` samples, random signs, mostly soft with a few
    up to three times louder (Pareto amplitudes, capped so no drop cracks out)."""
    out = np.zeros(n)
    amplitude = 1.0 + np.minimum(rng.pareto(2.5, count), 2.0)
    np.add.at(out, rng.integers(0, n, count), rng.choice((-1.0, 1.0), count) * amplitude)
    return out


@lru_cache(maxsize=1)
def rain_loop() -> np.ndarray:
    """The rain bed's seamless loop: float32 ``(n, 2)`` at :data:`RATE`, :data:`RAIN_LEVEL`
    integrated loudness, read-only; made once per process (well under a second)."""
    n = int(RAIN_LOOP_SECONDS * RATE)
    rng = np.random.default_rng(zlib.crc32(b"ambience:rain"))
    t = np.arange(n) / n
    channels = []
    for _ in range(2):
        hiss = _circular(rng.standard_normal(n), lambda f: _band(f, 2500.0, 1.1) * _highpass(f, 300.0) * _lowpass(f, 9000.0))
        ticks = _circular(_impulses(rng, n, int(240 * RAIN_LOOP_SECONDS)), lambda f: _band(f, 3500.0, 0.7) * _lowpass(f, 10000.0))
        plops = _circular(_impulses(rng, n, int(25 * RAIN_LOOP_SECONDS)), lambda f: _band(f, 900.0, 0.5))
        swell = 1.0 + 0.15 * np.sin(2 * math.pi * 2 * t + rng.uniform(0, 2 * math.pi))
        channels.append((0.6 * hiss + 0.35 * ticks + 0.2 * plops) * swell)
    x = np.stack(channels, axis=1)
    out = (x * 10 ** ((RAIN_LEVEL - integrated_loudness(x)) / 20)).astype(np.float32)
    out.setflags(write=False)
    return out


#: Integrated loudness (LUFS) of the fire's crackle before ducking (a little under the rain: a
#: fire is a small sound in a room), its ducking (as the rain's), its fades (s: it lights and goes
#: out quicker than rain starts) and its loop's length (s).
FIRE_LEVEL = -34.0
FIRE_DUCK = RAIN_DUCK
FIRE_FADE_IN = 0.6
FIRE_FADE_OUT = 0.8
FIRE_LOOP_SECONDS = 8.0


def _ringing(impulses: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Each impulse followed by ``ring``, around a circle (a ring past the end goes on at the
    start), so the result loops without a seam."""
    full = np.convolve(impulses, ring)
    out = full[: len(impulses)].copy()
    out[: len(full) - len(impulses)] += full[len(impulses) :]
    return out


@lru_cache(maxsize=1)
def fire_loop() -> np.ndarray:
    """The fire bed's seamless loop: float32 ``(n, 2)`` at :data:`RATE`, :data:`FIRE_LEVEL`
    integrated loudness, read-only. Per channel a low soft roar (noise around 220 Hz with a slow
    breath), many small crackles (sparse impulses around 3 kHz, each ringing a few milliseconds)
    and fewer louder pops (around 1.2 kHz); numpy only, seeded, circular filters (no seam)."""
    n = int(FIRE_LOOP_SECONDS * RATE)
    rng = np.random.default_rng(zlib.crc32(b"ambience:fire"))
    t = np.arange(n) / n
    ring = np.exp(-np.arange(int(0.004 * RATE)) / (0.0012 * RATE))
    channels = []
    for _ in range(2):
        roar = _circular(rng.standard_normal(n), lambda f: _band(f, 220.0, 1.2) * _highpass(f, 60.0))
        breath = 1.0 + 0.25 * np.sin(2 * math.pi * 3 * t + rng.uniform(0, 2 * math.pi))
        crackles = _circular(_ringing(_impulses(rng, n, int(9 * FIRE_LOOP_SECONDS)), ring), lambda f: _band(f, 3000.0, 0.9) * _lowpass(f, 9000.0))
        pops = _circular(_ringing(_impulses(rng, n, int(1.5 * FIRE_LOOP_SECONDS)), ring), lambda f: _band(f, 1200.0, 0.6))
        channels.append(0.5 * roar * breath + 0.45 * crackles + 0.35 * pops)
    x = np.stack(channels, axis=1)
    out = (x * 10 ** ((FIRE_LEVEL - integrated_loudness(x)) / 20)).astype(np.float32)
    out.setflags(write=False)
    return out


@dataclass(frozen=True)
class AmbienceBed:
    """How a bed plays: its loop, its ducking under the narration and its fades (s)."""

    loop: Callable[[], np.ndarray]
    duck: DuckConfig
    fade_in: float
    fade_out: float


#: Each bed of :data:`AMBIENCE_BEDS`.
BEDS: dict[str, AmbienceBed] = {
    "rain": AmbienceBed(rain_loop, RAIN_DUCK, RAIN_FADE_IN, RAIN_FADE_OUT),
    "fire": AmbienceBed(fire_loop, FIRE_DUCK, FIRE_FADE_IN, FIRE_FADE_OUT),
}


class LoopSource:
    """A seamless loop read from its start (``read(a, b)`` → float32 ``(b - a, 2)``), like a
    music bed's :class:`vidgen.music.Source`."""

    def __init__(self, data: np.ndarray) -> None:
        self.data = data

    def read(self, a: int, b: int) -> np.ndarray:
        return self.data[np.arange(a, b) % len(self.data)]
