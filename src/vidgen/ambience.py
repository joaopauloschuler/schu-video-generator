"""Ambience (DESIGN.md §69.39, §69.55, §69.62): a generated sound bed under the scenes while
something on screen lasts: ``rain`` under a stage's rain field and ``fire`` (a crackle) while a
fireplace burns; and the beds of the set itself (:data:`SET_BEDS`): ``birdsong`` outdoors by day,
``room_tone`` in a room (chosen by :func:`set_ambience`), ``crickets`` in the evening and at night outdoors on an iso
place (§89.11) and ``city`` when a stage names it; all while foley is on (:data:`BEDS`).

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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

from vidgen.config import DuckConfig
from vidgen.loudness import integrated_loudness
from vidgen.sfx import RATE, _band, _highpass, _lowpass, _tone

#: The ambience beds a scene's timings may name (``ambience: [{bed, start, end}]``).
AMBIENCE_BEDS = ("rain", "fire", "birdsong", "city", "room_tone", "crickets")
#: The beds of a set (DESIGN.md §69.62, §89.11): what a stage's ``ambience`` may name.
SET_BEDS = ("birdsong", "city", "room_tone", "crickets")
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
    return _leveled(np.stack(channels, axis=1), RAIN_LEVEL)


def _leveled(x: np.ndarray, level: float) -> np.ndarray:
    """``x`` scaled to ``level`` integrated loudness (LUFS), float32, read-only."""
    out = (x * 10 ** ((level - integrated_loudness(x)) / 20)).astype(np.float32)
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
    return _leveled(np.stack(channels, axis=1), FIRE_LEVEL)


# ----- the beds of a set (DESIGN.md §69.62) -----------------------------------------------------------

#: Integrated loudness (LUFS) of each set bed before ducking: birdsong and the city a little under
#: the rain (a background, not an event), the room tone far under everything (felt as air more
#: than heard).
BIRDSONG_LEVEL = -36.0
CITY_LEVEL = -35.0
ROOM_TONE_LEVEL = -46.0
#: How they duck under the narration: birdsong 4 dB, the city as the rain (5 dB); the room tone
#: not at all (it is about 25 dB under the voice).
BIRDSONG_DUCK = DuckConfig(depth=4.0, attack=0.4, release=1.0, hold=1.5, clips=False)
CITY_DUCK = RAIN_DUCK
ROOM_TONE_DUCK = DuckConfig(depth=0.0, clips=False)
#: Seconds of fade at the start and end of a set bed's span.
SET_FADE_IN = 2.0
SET_FADE_OUT = 1.5
#: Lengths of the loops (s): birdsong and the city long, so their events do not repeat noticeably.
BIRDSONG_LOOP_SECONDS = 20.0
CITY_LOOP_SECONDS = 16.0
ROOM_TONE_LOOP_SECONDS = 8.0


def _placed(out: np.ndarray, sound: np.ndarray, at: int) -> None:
    """Add ``sound`` into ``out`` from sample ``at``, around a circle (what passes the end goes on
    at the start), so the result loops without a seam."""
    out[(at + np.arange(len(sound))) % len(out)] += sound


def _chirp(freq: np.ndarray, m: int) -> np.ndarray:
    """A bird's note: a tone of ``freq`` (Hz per sample, ``m`` samples) with a faint octave,
    rising and falling as a sine squared."""
    phase = _tone(freq, m)
    return (np.sin(phase) + 0.12 * np.sin(2 * phase)) * np.sin(np.pi * np.arange(m) / m) ** 2


def _bird_phrase(rng: np.random.Generator) -> np.ndarray:
    """One seeded bird phrase: a run of 3-6 short tweets falling in pitch (3-5 kHz), a two-note
    whistle (2-3.2 kHz, the second lower) or a trill (3.5-5.5 kHz warbling 18-25 times a second)."""
    kind = int(rng.integers(0, 3))
    parts: list[np.ndarray] = []
    if kind == 0:
        f0, length, gap = rng.uniform(3000, 5000), rng.uniform(0.05, 0.08), rng.uniform(0.05, 0.09)
        m = int(length * RATE)
        for _ in range(int(rng.integers(3, 7))):
            t = np.arange(m) / RATE
            parts += [_chirp(f0 * rng.uniform(0.97, 1.03) * (1 - 0.25 * t / length), m), np.zeros(int(gap * RATE))]
    elif kind == 1:
        f0 = rng.uniform(2000, 3200)
        for ratio in (1.0, rng.uniform(0.75, 0.85)):
            m = int(rng.uniform(0.18, 0.25) * RATE)
            t = np.arange(m) / RATE
            parts += [_chirp(f0 * ratio * (1 + 0.01 * np.sin(2 * math.pi * 6 * t)), m), np.zeros(int(0.06 * RATE))]
    else:
        m = int(rng.uniform(0.5, 0.9) * RATE)
        t = np.arange(m) / RATE
        rate = rng.uniform(18, 25)
        tremolo = (0.5 + 0.5 * np.sin(2 * math.pi * rate * t)) ** 2
        parts.append(_chirp(rng.uniform(3500, 5500) * (1 + 0.12 * np.sin(2 * math.pi * rate * t)), m) * tremolo)
    return np.concatenate(parts)


@lru_cache(maxsize=1)
def birdsong_loop() -> np.ndarray:
    """The birdsong bed's seamless loop: float32 ``(n, 2)`` at :data:`RATE`, :data:`BIRDSONG_LEVEL`
    integrated loudness, read-only. About one seeded bird phrase a second (:func:`_bird_phrase`),
    each nearer or farther (30-100 %) and placed left or right, over a faint airy rustle (noise
    around 3 kHz); numpy only, around a circle (no seam)."""
    n = int(BIRDSONG_LOOP_SECONDS * RATE)
    rng = np.random.default_rng(zlib.crc32(b"ambience:birdsong"))
    out = np.zeros((n, 2))
    for _ in range(int(0.9 * BIRDSONG_LOOP_SECONDS)):
        phrase = _bird_phrase(rng) * rng.uniform(0.3, 1.0)
        angle = (rng.uniform(-0.8, 0.8) + 1) * math.pi / 4
        at = int(rng.integers(0, n))
        _placed(out[:, 0], math.cos(angle) * phrase, at)
        _placed(out[:, 1], math.sin(angle) * phrase, at)
    t = np.arange(n) / n
    for c in range(2):
        rustle = _circular(rng.standard_normal(n), lambda f: _band(f, 3000.0, 1.0) * _lowpass(f, 8000.0))
        out[:, c] += 0.04 * rustle * (1 + 0.3 * np.sin(2 * math.pi * 2 * t + rng.uniform(0, 2 * math.pi)))
    return _leveled(out, BIRDSONG_LEVEL)


def _wrapped_swell(t: np.ndarray, middle: float, width: float) -> np.ndarray:
    """A Gaussian swell over ``t`` in [0, 1) of a loop, around ``middle``, ``width`` wide (shares of
    the loop), wrapping around its ends."""
    d = (t - middle + 0.5) % 1.0 - 0.5
    return np.exp(-((d / width) ** 2))


@lru_cache(maxsize=1)
def city_loop() -> np.ndarray:
    """The city bed's seamless loop: float32 ``(n, 2)`` at :data:`RATE`, :data:`CITY_LEVEL`
    integrated loudness, read-only. Per channel a low traffic rumble (noise 35-250 Hz, slowly
    swelling), three or four cars passing (noise around 600 Hz swelling for 1-2 s) and a far murmur
    of people (noise around 900 Hz, its loudness wandering 3-6 times a second); numpy only,
    circular (no seam)."""
    n = int(CITY_LOOP_SECONDS * RATE)
    rng = np.random.default_rng(zlib.crc32(b"ambience:city"))
    t = np.arange(n) / n
    cycles = CITY_LOOP_SECONDS   # whole cycles per loop of a 1 Hz wander
    channels = []
    for _ in range(2):
        rumble = _circular(rng.standard_normal(n), lambda f: _lowpass(f, 250.0) * _highpass(f, 35.0))
        rumble *= 1 + 0.15 * np.sin(2 * math.pi * t + rng.uniform(0, 2 * math.pi))
        cars = _circular(rng.standard_normal(n), lambda f: _band(f, 600.0, 0.9))
        swells = sum(
            rng.uniform(0.5, 1.0) * _wrapped_swell(t, rng.uniform(0, 1), rng.uniform(0.8, 1.6) / CITY_LOOP_SECONDS)
            for _ in range(int(rng.integers(3, 5)))
        )
        murmur = _circular(rng.standard_normal(n), lambda f: _band(f, 900.0, 0.7))
        wander = 1 + 0.5 * sum(np.sin(2 * math.pi * round(rng.uniform(3, 6) * cycles) * t + rng.uniform(0, 2 * math.pi)) for _ in range(3)) / 3
        channels.append(0.7 * rumble + 0.5 * cars * (0.15 + swells) + 0.15 * murmur * np.maximum(wander, 0.0))
    return _leveled(np.stack(channels, axis=1), CITY_LEVEL)


@lru_cache(maxsize=1)
def room_tone_loop() -> np.ndarray:
    """The room tone's seamless loop: float32 ``(n, 2)`` at :data:`RATE`, :data:`ROOM_TONE_LEVEL`
    integrated loudness, read-only. Per channel a soft low air noise (40-250 Hz) with a faint wider
    hiss around 1.5 kHz, breathing by 5 % once a loop; numpy only, circular (no seam)."""
    n = int(ROOM_TONE_LOOP_SECONDS * RATE)
    rng = np.random.default_rng(zlib.crc32(b"ambience:room_tone"))
    t = np.arange(n) / n
    channels = []
    for _ in range(2):
        low = _circular(rng.standard_normal(n), lambda f: _lowpass(f, 250.0, 1) * _highpass(f, 40.0))
        air = _circular(rng.standard_normal(n), lambda f: _band(f, 1500.0, 1.5))
        channels.append((low + 0.2 * air) * (1 + 0.05 * np.sin(2 * math.pi * t + rng.uniform(0, 2 * math.pi))))
    return _leveled(np.stack(channels, axis=1), ROOM_TONE_LEVEL)


#: Integrated loudness (LUFS) of the crickets bed, how it ducks (as birdsong) and its loop's length.
CRICKETS_LEVEL = -37.0
CRICKETS_DUCK = BIRDSONG_DUCK
CRICKETS_LOOP_SECONDS = 12.0


def _cricket_chirp(rng: np.random.Generator, pitch: float) -> np.ndarray:
    """One cricket's chirp: 3-4 quick pulses (each ~14 ms, ~20 ms apart) of a pure tone near
    ``pitch`` Hz with a faint second harmonic, the first pulse softest."""
    pulse_s, gap_s = rng.uniform(0.012, 0.016), rng.uniform(0.018, 0.024)
    m = int(pulse_s * RATE)
    count = int(rng.integers(3, 5))
    out = np.zeros(int((count * (pulse_s + gap_s)) * RATE) + m)
    for k in range(count):
        at = int(k * (pulse_s + gap_s) * RATE)
        phase = _tone(pitch * rng.uniform(0.995, 1.005), m)
        out[at:at + m] += (0.6 + 0.4 * min(k, 1)) * (np.sin(phase) + 0.08 * np.sin(2 * phase)) * np.sin(np.pi * np.arange(m) / m) ** 2
    return out


@lru_cache(maxsize=1)
def crickets_loop() -> np.ndarray:
    """The crickets bed's seamless loop (a night outdoors on an iso place, DESIGN.md §89.11):
    float32 ``(n, 2)`` at :data:`RATE`, :data:`CRICKETS_LEVEL` integrated loudness, read-only.
    Four crickets, each at its own pitch (3.8-5.2 kHz), place (left to right) and loudness, chirping
    at its own steady rate (1.3-2.6 chirps a second, a little uneven), over a faint low night air
    (noise under 400 Hz); numpy only, around a circle (no seam)."""
    n = int(CRICKETS_LOOP_SECONDS * RATE)
    rng = np.random.default_rng(zlib.crc32(b"ambience:crickets"))
    out = np.zeros((n, 2))
    for _ in range(4):
        pitch, rate, loud = rng.uniform(3800, 5200), rng.uniform(1.3, 2.6), rng.uniform(0.35, 1.0)
        angle = (rng.uniform(-0.8, 0.8) + 1) * math.pi / 4
        count = round(rate * CRICKETS_LOOP_SECONDS)
        start = rng.uniform(0, n / count)
        for k in range(count):
            chirp = _cricket_chirp(rng, pitch) * loud
            at = int(start + k * n / count + rng.normal(0, 0.03 * RATE)) % n
            _placed(out[:, 0], math.cos(angle) * chirp, at)
            _placed(out[:, 1], math.sin(angle) * chirp, at)
    for c in range(2):
        air = _circular(rng.standard_normal(n), lambda f: _lowpass(f, 400.0) * _highpass(f, 40.0))
        out[:, c] += 0.05 * air
    return _leveled(out, CRICKETS_LEVEL)


#: The lights (presets) by day, when birds sing outdoors.
DAYLIGHT: frozenset[str] = frozenset({"day", "morning"})
#: The lights (presets) when crickets chirp outdoors on an iso place: the evening and the night.
NIGHT: frozenset[str] = frozenset({"sunset", "night"})
#: Seconds after the rain stops before the birds sing again.
BIRDS_AFTER_RAIN = 2.0
#: Birdsong for less than this (s) is left out.
MIN_BIRDSONG_SECONDS = 2.0


def _without(spans: list[tuple[float, float]], cuts: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    """``spans`` with every ``cut`` (start, end) taken out."""
    for a, b in cuts:
        spans = [piece for s, e in spans for piece in ((s, min(e, a)), (max(s, b), e)) if piece[1] > piece[0]]
    return spans


def set_ambience(
    setting: bool | Sequence[str],
    *,
    room: bool,
    lights: Sequence[tuple[float, str | None]],
    rain: Iterable[tuple[float, float]],
    end: float,
    crickets: bool = False,
) -> list[tuple[str, float, float]]:
    """The set beds of a stage scene of ``end`` seconds (DESIGN.md §69.62) as ``(bed, start,
    end)``: ``setting`` ``False`` none; a list of :data:`SET_BEDS` names those beds for the whole
    scene; ``True`` chooses: a ``room`` its ``room_tone`` all along; outdoors ``birdsong`` while the
    light is a :data:`DAYLIGHT` preset (``lights``: ``(scene time, preset or None for a tint)``
    from the first, sorted), not while it rains (``rain`` spans) nor :data:`BIRDS_AFTER_RAIN` after,
    each span at least :data:`MIN_BIRDSONG_SECONDS`; with ``crickets`` (an iso place outdoors,
    §89.11) also ``crickets`` while the light is ``sunset`` or ``night`` (:data:`NIGHT`), under the
    same rules."""
    if setting is False or end <= 0:
        return []
    if setting is not True:
        return [(name, 0.0, end) for name in dict.fromkeys(setting)]
    if room:
        return [("room_tone", 0.0, end)]
    marks = sorted(lights)
    rain = list(rain)

    def sung(lit: frozenset[str]) -> list[tuple[float, float]]:
        spans = [(t, min(nxt, end)) for (t, light), nxt in zip(marks, [*(m[0] for m in marks[1:]), end]) if light in lit and t < end]
        return [s for s in _without(merge_spans(spans, 1e-6), ((a, b + BIRDS_AFTER_RAIN) for a, b in rain)) if s[1] - s[0] >= MIN_BIRDSONG_SECONDS]

    beds = [("birdsong", a, b) for a, b in sung(DAYLIGHT)]
    if crickets:
        beds += [("crickets", a, b) for a, b in sung(NIGHT)]
    return beds


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
    "birdsong": AmbienceBed(birdsong_loop, BIRDSONG_DUCK, SET_FADE_IN, SET_FADE_OUT),
    "city": AmbienceBed(city_loop, CITY_DUCK, SET_FADE_IN, SET_FADE_OUT),
    "room_tone": AmbienceBed(room_tone_loop, ROOM_TONE_DUCK, SET_FADE_IN, SET_FADE_OUT),
    "crickets": AmbienceBed(crickets_loop, CRICKETS_DUCK, SET_FADE_IN, SET_FADE_OUT),
}


class LoopSource:
    """A seamless loop read from its start (``read(a, b)`` → float32 ``(b - a, 2)``), like a
    music bed's :class:`vidgen.music.Source`."""

    def __init__(self, data: np.ndarray) -> None:
        self.data = data

    def read(self, a: int, b: int) -> np.ndarray:
        return self.data[np.arange(a, b) % len(self.data)]
