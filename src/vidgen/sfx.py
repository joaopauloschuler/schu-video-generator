"""Sound effects (DESIGN.md §47): a procedurally synthesised set of short sounds, the project's
own sounds in ``assets/sfx/``, loudness measurement and the video's SFX track.

Built-in sounds are made by small deterministic generators (numpy only: noise from a seeded
generator, filters applied in the frequency domain), so no recordings with licences ship with
vidgen and each sound takes a few parameters (``duration``, ``pitch`` in semitones,
``intensity`` 0-1). Every sound gets the same finishing: a high-pass at 25 Hz, raised-cosine
fades so it starts and ends at exactly zero, the mean removed (no DC offset), and a level set by
loudness — the loudest 400 ms (BS.1770 K-weighted "momentary" loudness) at
:data:`LOUDNESS_TARGET`, peaks at most :data:`PEAK_CEILING` — so that, at ``gain: 0``, a sound
sits clearly under typical narration.

Sounds are synthesised when the video is joined (a few milliseconds each, cached per process)
rather than shipped as files: the parameters are continuous, so pre-rendered files could only
offer the defaults. ``vidgen list-sfx --render-dir DIR`` writes previews.

A scene records *events* (:class:`SfxEvent`: scene time, sound, gain, pan, align, params); the
worker stores them in the scene's timings; the render pipeline places them, sample-exact, on one
stereo track for the whole video (:func:`write_track`), which the final mux adds to the
narration track (no Manim sound mixing involved).
"""

from __future__ import annotations

import difflib
import io
import logging
import math
import re
import wave
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.config import SOUND_NAME_PATTERN
from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.config import VideoConfig

log = logging.getLogger("vidgen.sfx")

#: Sample rate of every sound and of the SFX track (the rate of the padded scene audio).
RATE = 48000
#: Loudness of a sound at gain 0 and intensity 0.5: its loudest 400 ms, K-weighted, in LUFS of
#: one channel (a centred sound plays at this level on both channels).
#: ElevenLabs narration measures about -19 to -21 LUFS this way, so effects sit ~7 dB under it.
LOUDNESS_TARGET = -27.0
#: Highest sample peak of a built-in sound (dBFS), whatever its loudness (narration peaks
#: around -4 to -7 dBFS).
PEAK_CEILING = -9.0
#: dB from ``intensity`` 0 to 1 (centred on 0.5): intensity also changes the timbre.
INTENSITY_DB = 6.0
#: Allowed ``pitch`` (semitones; checked by ``config.SfxParams``).
PITCH_RANGE = (-24.0, 24.0)
#: Folder of the project's own sounds (``<name>.wav``; also .flac, .ogg, .mp3).
PROJECT_SFX_DIR = Path("assets") / "sfx"
#: Suffixes of project sounds, in the order a name's file is picked when several exist.
SFX_SUFFIXES = (".wav", ".flac", ".ogg", ".mp3")
#: A sound name: letters, digits, ``_`` and ``-``.
SOUND_NAME = re.compile(SOUND_NAME_PATTERN)
#: With ``sfx: {auto: true}``: ``(sound, gain dB, params)`` played when a built-in beat action
#: of that name starts animating (not in beats that have their own ``sfx`` actions).
AUTO_ACTION_SFX: dict[str, tuple[str, float, dict[str, float]]] = {
    "reveal": ("pop", -3.0, {}),
    "highlight": ("tick", -3.0, {}),
    "callout": ("click", -2.0, {}),
    "zoom": ("whoosh", -6.0, {"duration": 0.5}),
    "transform": ("swoosh", -6.0, {}),
}
#: Samples written at once by :func:`write_track` (10 s).
_BLOCK = RATE * 10


# ----- signal helpers ------------------------------------------------------------------------------


def _filtered(x: np.ndarray, gain: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """``x`` filtered by the zero-phase magnitude response ``gain(frequencies in Hz)`` (FFT,
    zero-padded so nothing wraps around)."""
    n = len(x)
    size = 1 << max(1, (2 * n - 1).bit_length())
    spectrum = np.fft.rfft(x, size)
    freqs = np.fft.rfftfreq(size, 1 / RATE)
    return np.fft.irfft(spectrum * gain(freqs), size)[:n]


def _band(freqs: np.ndarray, center: np.ndarray | float, width: float) -> np.ndarray:
    """A band-pass bump: Gaussian in octaves around ``center`` with ``width`` octaves (σ)."""
    octaves = np.log2(np.maximum(freqs, 1.0) / center)
    return np.exp(-0.5 * (octaves / width) ** 2)


def _lowpass(freqs: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    return 1 / np.sqrt(1 + (freqs / cutoff) ** (2 * order))


def _highpass(freqs: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    ratio = np.divide(cutoff, freqs, out=np.full_like(freqs, np.inf), where=freqs > 0)
    return 1 / np.sqrt(1 + ratio ** (2 * order))


def _sweep(noise: np.ndarray, centers: Callable[[np.ndarray], np.ndarray], width: float) -> np.ndarray:
    """``noise`` through a band-pass whose centre moves over time: ``centers(u)`` gives the
    centre (Hz) at ``u`` in [0, 1] of the sound. Short-time Fourier transform (1024-sample Hann
    frames, hop 256), each frame filtered in the middle of a buffer twice its size (so the
    filter's response never wraps around), overlap-added."""
    size, hop = 1024, 256
    half = size // 2
    n = len(noise)
    padded = np.concatenate([np.zeros(size), noise, np.zeros(size)])
    starts = np.arange(0, len(padded) - size + 1, hop)
    window = np.hanning(size)
    frames = np.zeros((len(starts), 2 * size))
    frames[:, half : half + size] = padded[starts[:, None] + np.arange(size)] * window
    spectra = np.fft.rfft(frames, axis=1)
    freqs = np.fft.rfftfreq(2 * size, 1 / RATE)
    u = np.clip((starts + half - size) / max(n - 1, 1), 0.0, 1.0)
    shaped = np.fft.irfft(spectra * _band(freqs[None, :], centers(u)[:, None], width), 2 * size, axis=1)
    out = np.zeros(len(padded) + size)
    weight = np.zeros(len(padded) + size)
    for k, start in enumerate(starts):
        out[start : start + 2 * size] += shaped[k]  # buffer k starts `half` before frame k
        weight[start + half : start + half + size] += window
    return (out[half:] / np.maximum(weight[half:], 1e-3))[size : size + n]


def _bump(u: np.ndarray, peak: float) -> np.ndarray:
    """A smooth hump over ``u`` in [0, 1]: 0 at both ends, 1 at ``peak`` (sine-squared sides)."""
    rise = np.sin(0.5 * np.pi * np.clip(u / peak, 0, 1)) ** 2
    fall = np.cos(0.5 * np.pi * np.clip((u - peak) / (1 - peak), 0, 1)) ** 2
    return np.where(u <= peak, rise, fall)


def _decay(t: np.ndarray, attack: float, tau: float) -> np.ndarray:
    """A struck envelope: rises over ``attack`` seconds, then decays exponentially with ``tau``."""
    return (1 - np.exp(-t / attack)) * np.exp(-t / tau)


def _tone(freq: np.ndarray | float, n: int) -> np.ndarray:
    """The phase (radians) of a tone of ``freq`` Hz (constant or per sample)."""
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    return 2 * np.pi * np.cumsum(f) / RATE


def _fades(n: int, fade_in: float, fade_out: float) -> np.ndarray:
    """1 in the middle, raised-cosine ramps from exactly 0 at the first and last sample."""
    env = np.ones(n)
    for length, side in ((max(2, int(fade_in * RATE)), 1), (max(2, int(fade_out * RATE)), -1)):
        length = min(length, n // 2)
        ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(length) / length)
        if side == 1:
            env[:length] *= ramp
        else:
            env[n - length :] *= ramp[::-1]
    env[0] = env[-1] = 0.0
    return env


# ----- loudness ------------------------------------------------------------------------------------

#: BS.1770 K-weighting at 48 kHz: a high shelf (+4 dB above ~1.5 kHz) and a high-pass (~38 Hz).
_SHELF = ((1.53512485958697, -2.69169618940638, 1.19839281085285), (1.0, -1.69065929318241, 0.73248077421585))
_RLB = ((1.0, -2.0, 1.0), (1.0, -1.99004745483398, 0.99007225036621))


def _k_weighting(freqs: np.ndarray) -> np.ndarray:
    z = np.exp(-2j * np.pi * freqs / RATE)
    gain = np.ones(len(freqs))
    for b, a in (_SHELF, _RLB):
        gain = gain * np.abs((b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z))
    return gain


def loudness(samples: np.ndarray) -> float:
    """Loudness (LUFS) of the loudest 400 ms of ``samples`` (48 kHz; mono ``(n,)`` or channels
    ``(n, c)``): BS.1770 K-weighted mean square summed over channels, windows every 10 ms. A sound
    shorter than 400 ms is measured with silence around it (so short clicks count as quiet, as
    they sound). ``-inf`` for silence."""
    x = samples.reshape(len(samples), -1).astype(np.float64)
    window, step = int(0.4 * RATE), int(0.01 * RATE)
    if len(x) < window:
        x = np.concatenate([x, np.zeros((window - len(x), x.shape[1]))])
    power = sum(_filtered(x[:, c], _k_weighting) ** 2 for c in range(x.shape[1]))
    total = np.concatenate([[0.0], np.cumsum(power)])
    starts = np.arange(0, len(power) - window + 1, step)
    mean = (total[starts + window] - total[starts]) / window
    loudest = float(np.max(mean)) if len(mean) else 0.0
    return -0.691 + 10 * math.log10(loudest) if loudest > 1e-20 else -math.inf


def peak_db(samples: np.ndarray) -> float:
    """The highest absolute sample in dBFS (``-inf`` for silence)."""
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    return 20 * math.log10(peak) if peak > 0 else -math.inf


def _finish(x: np.ndarray, intensity: float, fade_in: float = 0.002, fade_out: float = 0.01) -> np.ndarray:
    """High-pass at 25 Hz, fade both ends to exactly zero, remove the mean, set the level (loudness
    target, then ``intensity`` ±3 dB, peak ceiling) and return float32."""
    x = _filtered(x, lambda f: _highpass(f, 25.0, 2))
    x = x * _fades(len(x), fade_in, fade_out)
    hann = np.hanning(len(x))  # 0 at both ends: removing the mean keeps the ends at zero
    x = x - x.mean() / hann.mean() * hann
    level = loudness(x)
    gain = 10 ** ((LOUDNESS_TARGET - level + (intensity - 0.5) * INTENSITY_DB) / 20)
    peak = float(np.max(np.abs(x))) * gain
    ceiling = 10 ** (PEAK_CEILING / 20)
    if peak > ceiling:
        gain *= ceiling / peak
    return (x * gain).astype(np.float32)


# ----- the built-in sounds -------------------------------------------------------------------------


@dataclass(frozen=True)
class Synth:
    """What a generator gets: the length in samples, ``ratio`` (frequency factor of ``pitch``),
    ``intensity`` (0-1) and a seeded random generator."""

    n: int
    ratio: float
    intensity: float
    rng: np.random.Generator

    @property
    def duration(self) -> float:
        """Seconds."""
        return self.n / RATE

    @property
    def t(self) -> np.ndarray:
        """Time of each sample (s)."""
        return np.arange(self.n) / RATE

    @property
    def u(self) -> np.ndarray:
        """Position of each sample in the sound, 0 to 1."""
        return np.arange(self.n) / max(self.n - 1, 1)


def _whoosh(s: Synth, rising: bool = True) -> np.ndarray:
    low, high = 380 * s.ratio, (1700 + 2000 * s.intensity) * s.ratio
    start, end, curve, peak = (low, high, 0.8, 0.55) if rising else (high, low, 0.6, 0.3)
    body = _sweep(s.rng.standard_normal(s.n), lambda u: start * (end / start) ** (u**curve), 0.55)
    body = _filtered(body, lambda f: _lowpass(f, 7000 * s.ratio, 2))
    return body * _bump(s.u, peak)


def _swoosh(s: Synth) -> np.ndarray:
    return _whoosh(s, rising=False)


def _pop(s: Synth) -> np.ndarray:
    t = s.t
    f0 = 480 * s.ratio
    freq = f0 * (1 + 0.85 * (1 - np.exp(-t / 0.012)))  # a quick upward "bloop"
    phase = _tone(freq, s.n)
    tone = np.sin(phase) + (0.15 + 0.25 * s.intensity) * np.sin(2 * phase)
    return tone * _decay(t, 0.0012, 0.03 * s.duration / 0.12)


def _click(s: Synth) -> np.ndarray:
    t = s.t
    center = 3200 * s.ratio * 2 ** (s.intensity - 0.5)
    noise = _filtered(s.rng.standard_normal(s.n), lambda f: _band(f, center, 0.45))
    noise *= _decay(t, 0.0003, 0.0028 * s.duration / 0.03)
    tone = 0.5 * np.sin(_tone(2100 * s.ratio, s.n)) * _decay(t, 0.0004, 0.006 * s.duration / 0.03)
    return noise / max(float(np.max(np.abs(noise))), 1e-9) + tone


def _tick(s: Synth) -> np.ndarray:
    t = s.t
    f0 = 1500 * s.ratio
    scale = s.duration / 0.09
    body = sum(
        amp * np.sin(_tone(f0 * ratio, s.n)) * _decay(t, 0.0005, tau * scale)
        for ratio, amp, tau in ((1.0, 1.0, 0.016), (2.32, 0.3 + 0.2 * s.intensity, 0.009), (4.1, 0.08 + 0.12 * s.intensity, 0.005))
    )
    knock = _filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 2500 * s.ratio, 0.6)) * _decay(t, 0.0002, 0.0015)
    return body + 0.3 * knock / max(float(np.max(np.abs(knock))), 1e-9)


def _keystroke(n: int, ratio: float, intensity: float, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / RATE
    center = 2600 * ratio * rng.uniform(0.85, 1.15) * 2 ** (intensity - 0.5)
    noise = _filtered(rng.standard_normal(n), lambda f: _band(f, center, 0.6)) * _decay(t, 0.0003, 0.004)
    noise /= max(float(np.max(np.abs(noise))), 1e-9)
    thock = 0.35 * np.sin(_tone(190 * ratio, n)) * _decay(t, 0.0008, 0.012)
    return (noise + thock) * _fades(n, 0.0003, 0.015) * rng.uniform(0.55, 1.0)


def _typing(s: Synth) -> np.ndarray:
    out = np.zeros(s.n)
    stroke = int(0.06 * RATE)
    time = 0.004
    while True:
        start = int(time * RATE)
        if start + stroke > s.n:
            break
        out[start : start + stroke] += _keystroke(stroke, s.ratio, s.intensity, s.rng)
        time += float(s.rng.uniform(0.07, 0.16))
    return out


def _riser(s: Synth) -> np.ndarray:
    u = s.u
    low, high = 250 * s.ratio, (2800 + 3000 * s.intensity) * s.ratio
    noise = _sweep(s.rng.standard_normal(s.n), lambda v: low * (high / low) ** (v**1.5), 0.8)
    noise /= max(float(np.max(np.abs(noise))), 1e-9)
    glide = 0.3 * np.sin(_tone(200 * s.ratio * 4 ** (u**1.5), s.n))
    return (noise + glide) * u**2.2


def _bell(n: int, freq: float, intensity: float, tau: float, partials: Sequence[tuple[float, float, float]]) -> np.ndarray:
    """A struck bell: ``(ratio, amplitude, decay share)`` partials of ``freq``; the upper ones
    louder with ``intensity``."""
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for k, (ratio, amp, share) in enumerate(partials):
        bright = 1.0 if k == 0 else 0.5 + intensity
        out += amp * bright * np.sin(_tone(freq * ratio, n)) * _decay(t, 0.002, tau * share)
    return out


_CHIME_PARTIALS = ((1.0, 1.0, 1.0), (2.0, 0.45, 0.6), (3.01, 0.2, 0.4), (4.17, 0.1, 0.26), (5.43, 0.05, 0.17))
_SOFT_BELL = ((1.0, 1.0, 1.0), (2.0, 0.3, 0.5), (3.0, 0.08, 0.3))


def _chime(s: Synth) -> np.ndarray:
    return _bell(s.n, 880 * s.ratio, s.intensity, 0.36 * s.duration, _CHIME_PARTIALS)


def _notes(s: Synth, notes: Sequence[tuple[float, float, float]], tau: float, partials: Sequence[tuple[float, float, float]]) -> np.ndarray:
    """``(start s, frequency Hz, amplitude)`` notes of a bell, each decaying with ``tau``."""
    out = np.zeros(s.n)
    for start, freq, amp in notes:
        k = int(start * RATE)
        out[k:] += amp * _bell(s.n - k, freq * s.ratio, s.intensity, tau, partials)
    return out


def _success(s: Synth) -> np.ndarray:
    return _notes(s, ((0.0, 659.26, 0.8), (0.11, 987.77, 1.0)), 0.3 * s.duration, _SOFT_BELL)


def _error(s: Synth) -> np.ndarray:
    soft_square = ((1.0, 1.0, 1.0), (3.0, 0.22 + 0.15 * s.intensity, 0.7), (5.0, 0.08, 0.5))
    tone = _notes(s, ((0.0, 392.0, 1.0), (0.16, 311.13, 1.0)), 0.25 * s.duration, soft_square)
    return _filtered(tone, lambda f: _lowpass(f, 2500 * s.ratio, 2))


def _thud(s: Synth) -> np.ndarray:
    t = s.t
    f0 = 55 * s.ratio
    body = np.sin(_tone(f0 * (1 + np.exp(-t / 0.03)), s.n)) * _decay(t, 0.002, 0.12 * s.duration / 0.45)
    knock = _filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 320 * s.ratio, 0.9)) * _decay(t, 0.0005, 0.012)
    knock /= max(float(np.max(np.abs(knock))), 1e-9)
    return body + (0.15 + 0.35 * s.intensity) * knock


def _normalized(x: np.ndarray) -> np.ndarray:
    return x / max(float(np.max(np.abs(x))), 1e-9)


def _footstep(s: Synth) -> np.ndarray:
    t = s.t
    scale = s.duration / 0.14
    heel = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 260 * s.ratio, 0.7))) * _decay(t, 0.0015, 0.018 * scale)
    thump = np.sin(_tone(95 * s.ratio * (1 + 0.5 * np.exp(-t / 0.01)), s.n)) * _decay(t, 0.002, 0.03 * scale)
    scuff = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 1800 * s.ratio * 2 ** (s.intensity - 0.5), 0.8)))
    scuff_start, scuff_length = 0.035 * scale, 0.07 * scale
    scuff *= _bump(np.clip((t - scuff_start) / scuff_length, 0.0, 1.0), 0.3)
    return heel + 0.6 * thump + (0.12 + 0.2 * s.intensity) * scuff


def _step_grass(s: Synth) -> np.ndarray:
    # a step on grass: a soft swish of blades (noise around 2.5 kHz, swelling over ~25 ms and
    # trailing off over ~90 ms) over a faint, muffled heel (noise around 180 Hz, ~15 ms)
    t = s.t
    scale = s.duration / 0.16
    swish = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 2500 * s.ratio * 2 ** (0.5 * (s.intensity - 0.5)), 0.6) * _lowpass(f, 5000 * s.ratio)))
    swish *= _bump(np.clip(t / (0.12 * scale), 0.0, 1.0), 0.22)
    heel = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 180 * s.ratio, 0.6))) * _decay(t, 0.002, 0.015 * scale)
    return 0.8 * swish + 0.5 * heel


def _step_gravel(s: Synth) -> np.ndarray:
    # a step on a sandy path with small stones: a crunch of 25-40 tiny grain clicks (noise
    # around 2.2 kHz) spread over ~80 ms, thickest at the start, over a soft heel (~240 Hz)
    t = s.t
    scale = s.duration / 0.18
    grains = np.zeros(s.n)
    count = int(s.rng.integers(25, 41))
    at = (s.rng.beta(1.2, 3.0, count) * 0.08 * scale * RATE).astype(int)
    grains[np.clip(at, 0, s.n - 1)] = s.rng.uniform(0.3, 1.0, count) * s.rng.choice([-1.0, 1.0], count)
    crunch = _normalized(_filtered(grains, lambda f: _band(f, 2200 * s.ratio * 2 ** (s.intensity - 0.5), 0.8)))
    heel = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 240 * s.ratio, 0.7))) * _decay(t, 0.0015, 0.018 * scale)
    return crunch + 0.5 * heel


def _step_wood(s: Synth) -> np.ndarray:
    # a step on wooden boards: a hollow knock, a thump near 150 Hz with the boards ringing at
    # ~340 and ~720 Hz (~45 ms), and a short tap of the heel (noise around 1.2 kHz)
    t = s.t
    scale = s.duration / 0.16
    thump = np.sin(_tone(150 * s.ratio * (1 + 0.3 * np.exp(-t / 0.008)), s.n)) * _decay(t, 0.0015, 0.035 * scale)
    ring = (0.55 * np.sin(_tone(340 * s.ratio, s.n)) + 0.25 * np.sin(_tone(720 * s.ratio, s.n))) * _decay(t, 0.001, 0.045 * scale)
    tap = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 1200 * s.ratio * 2 ** (s.intensity - 0.5), 0.6))) * _decay(t, 0.0005, 0.006)
    return thump + ring + (0.25 + 0.3 * s.intensity) * tap


def _step_stone(s: Synth) -> np.ndarray:
    # a step on stone or tiles: a hard, short heel click (noise around 2.8 kHz, ~5 ms) with a
    # small dry body (~260 Hz, ~15 ms); no scuff
    t = s.t
    scale = s.duration / 0.12
    click = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 2800 * s.ratio * 2 ** (s.intensity - 0.5), 0.5))) * _decay(t, 0.0003, 0.005 * scale)
    body = np.sin(_tone(260 * s.ratio, s.n)) * _decay(t, 0.0008, 0.015 * scale)
    return click + 0.6 * body


def _boing(s: Synth) -> np.ndarray:
    t = s.t
    scale = s.duration / 0.5
    wobble = 1 + 0.07 * np.exp(-t / (0.18 * scale)) * np.sin(2 * np.pi * 12 * t)
    phase = _tone(140 * s.ratio * (1 + 0.85 * (1 - np.exp(-t / (0.06 * scale)))) * wobble, s.n)
    tone = np.sin(phase) + (0.3 + 0.3 * s.intensity) * np.sin(2 * phase) + (0.1 + 0.15 * s.intensity) * np.sin(3 * phase)
    return tone * _decay(t, 0.003, 0.16 * scale)


_RING_PARTIALS = ((1.0, 1.0, 1.0), (2.76, 0.5, 0.55), (5.4, 0.25, 0.3), (8.93, 0.1, 0.18))


def _ring(s: Synth) -> np.ndarray:
    # a bicycle bell, "ring-ring": two quick strikes of a small bright bell, its partials beating
    scale = s.duration / 0.7
    out = np.zeros(s.n)
    for start in (0.0, 0.13):
        k = int(start * scale * RATE)
        out[k:] += _bell(s.n - k, 2350 * s.ratio, s.intensity, 0.22 * scale, _RING_PARTIALS)
    return out * (1 + 0.25 * np.sin(2 * np.pi * 18 * s.t))


def _engine(s: Synth) -> np.ndarray:
    # a small engine starting and running: a buzzy low tone (firing pulses) revving up over the
    # first fifth and settling, with a little rumble noise
    u = s.u
    rev = 1 + 0.55 * _bump(np.clip(u / 0.4, 0.0, 1.0), 0.5)
    freq = 42 * s.ratio * rev
    tone = _harmonic_tone(_tone(freq, s.n), 0.7 + 0.2 * s.intensity, 14, 0.7)
    tone *= 1 + 0.35 * np.sin(_tone(freq / 2, s.n))   # uneven firing
    rumble = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 180 * s.ratio, 1.2)))
    body = _filtered(_normalized(tone) + 0.25 * rumble, lambda f: _lowpass(f, 1400 * s.ratio, 2))
    return body * _fades(s.n, 0.06, 0.25)


def _brakes(s: Synth) -> np.ndarray:
    # brakes squealing to a stop: a thin tone near 2.1 kHz wavering and falling a little, over a
    # soft scrape of noise, swelling and stopping short
    u = s.u
    freq = 2100 * s.ratio * (1 - 0.06 * u) * (1 + 0.012 * np.sin(2 * np.pi * 9 * s.t))
    squeal = np.sin(_tone(freq, s.n)) + 0.3 * np.sin(2 * _tone(freq, s.n))
    scrape = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 1500 * s.ratio, 1.0)))
    return (squeal + (0.25 + 0.3 * s.intensity) * scrape) * _bump(u, 0.6) * _fades(s.n, 0.02, 0.04)


def _burner(s: Synth) -> np.ndarray:
    # a hot-air balloon's gas burner: a deep breathy roar (noise around 450 Hz, low-passed at
    # 1.4 kHz) catching at once, fluttering a little at 9 Hz, held and dying away at the end
    roar = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 450 * s.ratio, 1.6) * _lowpass(f, 1400 * s.ratio, 2)))
    hiss = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 2600 * s.ratio, 0.8)))
    flutter = 1 + 0.12 * np.sin(2 * np.pi * 9 * s.t)
    return (roar + (0.08 + 0.12 * s.intensity) * hiss) * flutter * _fades(s.n, 0.03, 0.3)


def _launch(s: Synth) -> np.ndarray:
    # a toy rocket taking off: a soft low "whump" as it lights, then a fizzing hiss whose band
    # climbs from ~1.5 to ~5 kHz with a crackle of tiny clicks, fading out as it flies away
    t, u = s.t, s.u
    whump = np.sin(_tone(75 * s.ratio * (1 + np.exp(-t / 0.04)), s.n)) * _decay(t, 0.002, 0.08)
    fizz = _normalized(_sweep(s.rng.standard_normal(s.n), lambda v: 1500 * s.ratio * (5000 / 1500) ** v, 0.7))
    crackle = np.where(s.rng.random(s.n) < 0.004, s.rng.standard_normal(s.n), 0.0)
    crackle = _normalized(_filtered(crackle, lambda f: _band(f, 3500 * s.ratio, 1.0)))
    body = (fizz + (0.2 + 0.3 * s.intensity) * crackle) * np.clip(u / 0.06, 0.0, 1.0) * (1 - u) ** 1.5
    return 0.8 * whump + body


def _phone(s: Synth) -> np.ndarray:
    # a phone ringing, "brring-brring": a soft electronic trill (a tone flipping between ~1.1 and
    # ~1.4 kHz 20 times a second) in two pulses, 0-42 % and 50-92 % of its length
    t, u = s.t, s.u
    flip = 0.5 + 0.5 * np.tanh(6.0 * np.sin(2 * np.pi * 20 * t))
    phase = _tone(1100 * s.ratio * (1 + 0.27 * flip), s.n)
    tone = np.sin(phase) + (0.15 + 0.3 * s.intensity) * np.sin(2 * phase)
    edge = 0.02
    gate = sum(np.clip((u - a) / edge, 0.0, 1.0) * np.clip((b - u) / edge, 0.0, 1.0) for a, b in ((0.0, 0.42), (0.5, 0.92)))
    return tone * gate


def _beep(s: Synth) -> np.ndarray:
    # a friendly robot chirp, "bee-boop": two soft electronic notes (7 harmonics), ~1.3 kHz with a
    # quick upward blip at its start, then ~880 Hz; the first 42 % and the last 52 % of the length
    u = s.u
    high = (u < 0.42).astype(float)
    freq = s.ratio * np.where(u < 0.45, 1320.0 * (1 + 0.08 * np.exp(-s.t / 0.015)), 880.0)
    tone = _harmonic_tone(_tone(freq, s.n), 0.35 + 0.2 * s.intensity, 7, 1.0)
    edge = 0.03
    gate = np.clip(u / edge, 0, 1) * np.clip((0.42 - u) / edge, 0, 1) * high + np.clip((u - 0.48) / edge, 0, 1) * np.clip((1.0 - u) / edge, 0, 1)
    return tone * gate


def _thunder(s: Synth) -> np.ndarray:
    # thunder: a crack of bright noise at the start (stronger with intensity: a near strike), then
    # a deep rumble (noise low-passed near 120 Hz) rolling in three to five seeded swells and dying
    # away over the whole length
    t, u = s.t, s.u
    crack = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 1800 * s.ratio, 1.4))) * _decay(t, 0.002, 0.06)
    rumble = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _lowpass(f, 120 * s.ratio, 2) * _highpass(f, 28.0, 2)))
    swells = np.zeros(s.n)
    for _ in range(3 + int(s.rng.integers(0, 3))):
        middle, width = s.rng.uniform(0.05, 0.6), s.rng.uniform(0.08, 0.25)
        swells += s.rng.uniform(0.5, 1.0) * np.exp(-(((u - middle) / width) ** 2))
    roll = (0.35 + swells) * np.clip(u / 0.03, 0.0, 1.0) * (1 - u) ** 1.2
    return 1.6 * s.intensity * crack + rumble * roll


def _creak(s: Synth) -> np.ndarray:
    # a door's hinge creaking: stick-slip pulses whose rate glides from ~45 up to ~110 Hz and back
    # to ~70 with a seeded wobble, each pulse ringing a wooden body (~550 Hz, ~1.3 kHz, ~2.6 kHz)
    t, u = s.t, s.u
    wobble = 1 + 0.1 * np.sin(2 * np.pi * 3.3 * t + s.rng.uniform(0, 2 * np.pi)) + 0.05 * np.sin(2 * np.pi * 7.9 * t + s.rng.uniform(0, 2 * np.pi))
    rate = s.ratio * (45 + 65 * np.sin(np.pi * np.clip(u, 0, 1) ** 0.7) - 20 * u) * wobble
    cycles = np.floor(np.cumsum(rate) / RATE)
    pulses = np.zeros(s.n)
    slips = np.nonzero(np.diff(cycles) > 0)[0] + 1
    pulses[slips] = s.rng.uniform(0.6, 1.0, len(slips))
    r = s.ratio
    body = _filtered(pulses, lambda f: _band(f, 550 * r, 0.3) + 0.8 * _band(f, 1300 * r, 0.25) + (0.25 + 0.5 * s.intensity) * _band(f, 2600 * r, 0.25))
    return body * _bump(u, 0.35)


def _knock(s: Synth) -> np.ndarray:
    # knock-knock-knock: three knuckle raps on a wooden door 190 ms apart, each a dull hollow
    # thump (~190 and ~410 Hz, ringing ~30 ms) with a short bright tap (noise around 1.5 kHz)
    scale = s.duration / 0.75
    out = np.zeros(s.n)
    for start, amp in ((0.0, 1.0), (0.19, 0.85), (0.38, 0.95)):
        a = int(start * scale * RATE)
        m = s.n - a
        t = np.arange(m) / RATE
        tap = _normalized(_filtered(s.rng.standard_normal(m), lambda f: _band(f, 1500 * s.ratio * 2 ** (s.intensity - 0.5), 0.8))) * _decay(t, 0.0003, 0.004)
        thump = np.sin(_tone(190 * s.ratio * (1 + 0.15 * np.exp(-t / 0.006)), m)) * _decay(t, 0.0008, 0.035)
        hollow = 0.5 * np.sin(_tone(410 * s.ratio, m)) * _decay(t, 0.0008, 0.02)
        out[a:] += amp * (thump + hollow + (0.35 + 0.4 * s.intensity) * tap)
    return out


def _unlock(s: Synth) -> np.ndarray:
    # a key turning in a lock: a small metallic tick as the key catches (noise around 2.2 kHz with
    # a ~1.7 kHz ping, ~5 ms), then 90 ms later the bolt sliding back, a rounder clack (~620 Hz
    # with a soft ~170 Hz knock), low-passed so neither is sharp
    scale = s.duration / 0.3
    out = np.zeros(s.n)
    for start, ping, body, amp in ((0.0, 1700.0, 0.0, 0.55), (0.09, 620.0, 170.0, 1.0)):
        a = int(start * scale * RATE)
        m = s.n - a
        t = np.arange(m) / RATE
        tick = _normalized(_filtered(s.rng.standard_normal(m), lambda f: _band(f, 2200 * s.ratio * 2 ** (s.intensity - 0.5), 0.5))) * _decay(t, 0.0003, 0.005)
        ring = 0.6 * np.sin(_tone(ping * s.ratio, m)) * _decay(t, 0.0005, 0.018)
        knock = 0.7 * np.sin(_tone(body * s.ratio, m)) * _decay(t, 0.001, 0.03) if body else 0.0
        out[a:] += amp * ((0.3 + 0.3 * s.intensity) * tick + ring + knock)
    return _filtered(out, lambda f: _lowpass(f, 5000 * s.ratio, 2))


def _coin(s: Synth) -> np.ndarray:
    # a coin picked up, "pling-ling": two quick soft bell notes rising a fourth, B5 then E6, 70 ms
    # apart, the second held a little longer, with a faint shimmer
    scale = s.duration / 0.45
    tone = _notes(s, ((0.0, 987.77, 0.7), (0.07 * scale, 1318.51, 1.0)), 0.22 * s.duration, _SOFT_BELL)
    return tone * (1 + 0.12 * np.sin(2 * np.pi * 14 * s.t))


def _twinkle(s: Synth) -> np.ndarray:
    # a star picked up: a quick rising arpeggio of four soft bell notes (C6 E6 G6 C7), 50 ms apart,
    # ringing on together, with a faint airy glitter around 6 kHz fading away
    scale = s.duration / 0.8
    notes = tuple((k * 0.05 * scale, freq, 0.6 + 0.12 * k) for k, freq in enumerate((1046.5, 1318.51, 1567.98, 2093.0)))
    tone = _notes(s, notes, 0.25 * s.duration, _SOFT_BELL)
    glitter = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 6000 * s.ratio, 0.4))) * _decay(s.t, 0.05, 0.12 * scale)
    return _filtered(tone + (0.03 + 0.05 * s.intensity) * glitter, lambda f: _lowpass(f, 8000 * s.ratio, 2))


def _splash(s: Synth) -> np.ndarray:
    # something dropping into water: a burst of bright noise (around 2.5 kHz, ~70 ms) with a low
    # "plunk" gliding up from ~250 to ~600 Hz, then droplets falling back (tiny rising blips at
    # 1-3 kHz, thinning out) and a fading fizz; intensity sets the burst against the droplets
    t, u = s.t, s.u
    scale = s.duration / 0.6
    burst = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 2500 * s.ratio, 1.2) * _highpass(f, 300 * s.ratio, 2)))
    burst *= _decay(t, 0.003, 0.07 * min(scale, 1.5))
    plunk = np.sin(_tone(250 * s.ratio * (1 + 1.4 * (1 - np.exp(-t / 0.02))), s.n)) * _decay(t, 0.002, 0.05)
    drops = np.zeros(s.n)
    blip = int(0.03 * RATE)
    for _ in range(int(18 * s.duration) + 4):
        a = int(s.rng.uniform(0.04, 1.0) ** 1.5 * (s.n - blip))
        tt = np.arange(blip) / RATE
        f0 = s.rng.uniform(1000, 3000) * s.ratio
        drops[a : a + blip] += s.rng.uniform(0.2, 1.0) * np.sin(_tone(f0 * (1 + 0.6 * tt / 0.03), blip)) * _decay(tt, 0.0005, 0.008)
    fizz = _normalized(_filtered(s.rng.standard_normal(s.n), lambda f: _band(f, 4000 * s.ratio, 1.0))) * (1 - u) ** 2
    impact = 0.35 + 1.3 * s.intensity
    return impact * (burst + 0.4 * plunk) + 0.5 * drops + 0.12 * fizz


def _harmonic_tone(phase: np.ndarray, brightness: np.ndarray | float, harmonics: int, tilt: float) -> np.ndarray:
    """A tone of ``harmonics`` partials of ``phase``: partial ``h`` at ``brightness ** (h - 1) /
    h ** tilt`` (brightness 0..1, constant or per sample: a brass or muted-horn timbre)."""
    return sum(np.asarray(brightness) ** (h - 1) / h**tilt * np.sin(h * phase) for h in range(1, harmonics + 1))


def _sting_reveal(s: Synth) -> np.ndarray:
    scale = s.duration / 1.4
    out = np.zeros(s.n)
    bright = 0.45 + 0.3 * s.intensity
    for start, freq, amp, tau in ((0.0, 392.0, 0.6, 0.06), *((0.14, f, 0.5, 0.5) for f in (523.25, 659.26, 783.99, 1046.5))):
        k = int(start * scale * RATE)
        m = s.n - k
        t = np.arange(m) / RATE
        out[k:] += amp * _harmonic_tone(_tone(freq * s.ratio, m), bright, 8, 1.3) * _decay(t, 0.012, tau * scale)
    k = int(0.14 * scale * RATE)
    out[k:] += 0.25 * _bell(s.n - k, 2093.0 * s.ratio, s.intensity, 0.5 * scale, _SOFT_BELL)
    return _filtered(out, lambda f: _lowpass(f, 6000 * s.ratio, 2))


def _drum(n: int, high: float, low: float, tau: float) -> np.ndarray:
    """A tom hit: a sine dropping from ``high`` to ``low`` Hz, decaying with ``tau`` seconds."""
    t = np.arange(n) / RATE
    return np.sin(_tone(low + (high - low) * np.exp(-t / 0.04), n)) * _decay(t, 0.001, tau)


def _sting_comic(s: Synth) -> np.ndarray:
    scale = s.duration / 1.1
    out = np.zeros(s.n)
    for start, high, low in ((0.0, 200.0, 130.0), (0.15, 150.0, 100.0)):
        k = int(start * scale * RATE)
        out[k:] += _drum(s.n - k, high * s.ratio, low * s.ratio, 0.12 * scale)
    k = int(0.33 * scale * RATE)
    t = np.arange(s.n - k) / RATE
    noise = s.rng.standard_normal(s.n - k)
    cymbal = _normalized(_filtered(noise, lambda f: _band(f, 7500 * s.ratio, 0.5) * _highpass(f, 4000 * s.ratio, 2)))
    out[k:] += (0.5 + 0.4 * s.intensity) * cymbal * _decay(t, 0.001, 0.25 * scale)
    return out


def _sting_sad(s: Synth) -> np.ndarray:
    scale = s.duration / 2.2
    out = np.zeros(s.n)
    notes = ((0.0, 233.08, 0.38), (0.42, 220.0, 0.38), (0.84, 207.65, 0.38), (1.26, 196.0, 0.94))
    for k, (start, freq, length) in enumerate(notes):
        a = int(start * scale * RATE)
        m = min(int(length * scale * RATE), s.n - a)
        t = np.arange(m) / RATE
        u = t / max(t[-1], 1e-9)
        last = k == len(notes) - 1
        if last:  # a long falling note with a slow vibrato, the mute opening once
            freq_curve = freq * s.ratio * (1 - 0.03 * u) * (1 + 0.012 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.15) / 0.2, 0, 1))
            opening = _bump(u, 0.3)
        else:  # "wah": the mute opens and closes over the note
            freq_curve = np.full(m, freq * s.ratio)
            opening = np.sin(np.pi * u)
        bright = 0.2 + (0.3 + 0.25 * s.intensity) * opening
        out[a : a + m] += _harmonic_tone(_tone(freq_curve, m), bright, 10, 0.5) * _fades(m, 0.025, 0.4 if last else 0.06)
    return _filtered(out, lambda f: _lowpass(f, 3000 * s.ratio, 2))


def _breath(s: Synth, formants: Sequence[tuple[float, float, float]], glide: float) -> np.ndarray:
    """Breath noise through ``(Hz, octaves wide, amplitude)`` formants whose centres move by the
    factor ``glide`` over the sound (a mouth shape rather than a pitch)."""
    noise = s.rng.standard_normal(s.n)
    out = np.zeros(s.n)
    for freq, width, amplitude in formants:
        band = _sweep(noise, lambda u, f=freq: f * s.ratio * glide**u, width)
        out += amplitude * _normalized(band)
    return out


def _gasp(s: Synth) -> np.ndarray:
    # a sharp breath in through an open mouth ("hah"): loudest after ~50 ms, cut off at the end
    body = _breath(s, ((1100.0, 0.45, 1.0), (1750.0, 0.4, 0.7), (2900.0, 0.5, 0.35 + 0.3 * s.intensity)), 1.25)
    return body * _bump(s.u, 0.12) ** 0.5


def _sigh(s: Synth) -> np.ndarray:
    # a long breath out ("haaah"): breathy noise of an open "ah" with a faint low hum falling
    # from ~190 to ~130 Hz, swelling early and trailing off
    body = _breath(s, ((750.0, 0.5, 1.0), (1200.0, 0.45, 0.6), (2600.0, 0.6, 0.15 + 0.2 * s.intensity)), 0.85)
    hum = _harmonic_tone(_tone(190 * s.ratio * (130 / 190) ** s.u, s.n), 0.45, 6, 1.0)
    hum = _filtered(hum, lambda f: _lowpass(f, 900 * s.ratio, 2))
    return (body + 0.25 * _normalized(hum)) * _bump(s.u, 0.2)


# ----- story sounds (DESIGN.md §100.8): a lab, an alarm, a rift ------------------------------------------

#: The alarm's two tones (Hz) and how long each sounds (s): whole cycles in each half, so a loop of
#: whole periods repeats without a seam (the ambience's ``alarm`` bed).
SIREN_TONES = (960.0, 780.0)
SIREN_HALF = 0.45


def siren(n: int, ratio: float = 1.0, brightness: float = 0.5, *, circular: bool = False) -> np.ndarray:
    """A two-tone alarm ('hee-haw') of ``n`` samples: :data:`SIREN_TONES` (times ``ratio``)
    alternating every :data:`SIREN_HALF` seconds, a buzzy tone (7 harmonics) with soft 15 ms
    edges, low-passed at 4.5 kHz (``circular``: around a circle, for a loop of whole periods)."""
    t = np.arange(n) / RATE
    half = (t // SIREN_HALF).astype(int) % 2
    freq = np.where(half == 0, SIREN_TONES[0], SIREN_TONES[1]) * ratio
    tone = _harmonic_tone(_tone(freq, n), 0.45 + 0.3 * brightness, 7, 1.2)
    into = (t % SIREN_HALF) / SIREN_HALF
    edge = 0.015 / SIREN_HALF
    gate = np.clip(into / edge, 0.0, 1.0) * np.clip((1.0 - into) / edge, 0.0, 1.0)
    raw = tone * (0.25 + 0.75 * gate)
    if circular:
        return np.fft.irfft(np.fft.rfft(raw) * _lowpass(np.fft.rfftfreq(n, 1 / RATE), 4500 * ratio, 2), n)
    return _filtered(raw, lambda f: _lowpass(f, 4500 * ratio, 2))


def _alarm(s: Synth) -> np.ndarray:
    # an alarm siren: two tones (~960 and ~780 Hz) alternating every 0.45 s, buzzy, held for the length
    return siren(s.n, s.ratio, s.intensity) * _fades(s.n, 0.02, 0.05)


def _crackle(s: Synth) -> np.ndarray:
    # crackling energy: bursts of sharp electric snaps (impulses ringing a few ms, bright around
    # 3-5 kHz) in seeded clusters, over a faint buzzing arc (a 100 Hz buzz that flares with them)
    n = s.n
    snaps = np.zeros(n)
    rate = 250 + 250 * s.intensity
    count = max(int(rate * s.duration), 1)
    centres = s.rng.uniform(0.0, s.duration, max(int(5 * s.duration), 1))
    for _ in range(count):
        at = float(np.clip(s.rng.choice(centres) + s.rng.normal(0, 0.08), 0.0, s.duration - 0.005))
        snaps[int(at * RATE)] += s.rng.choice((-1.0, 1.0)) * s.rng.uniform(0.3, 1.0)
    ring = np.exp(-np.arange(int(0.006 * RATE)) / (0.0015 * RATE))
    bright = _filtered(np.convolve(snaps, ring)[:n], lambda f: _band(f, 3800 * s.ratio, 0.8) + 0.4 * _band(f, 1500 * s.ratio, 0.6))
    flare = _filtered(np.abs(snaps), lambda f: _lowpass(f, 12.0, 1))
    flare /= max(float(np.max(flare)), 1e-9)
    buzz = _harmonic_tone(_tone(100 * s.ratio, n), 0.7, 12, 0.8) * (0.15 + flare)
    return _normalized(bright) + 0.12 * _normalized(buzz) * _fades(n, 0.01, 0.05)


def _hum(s: Synth) -> np.ndarray:
    # an electronic hum: a soft 110 Hz tone and its harmonics, a second voice a hair sharp beating
    # slowly against it, a faint high whine (~3.5 kHz) and air; fading in and out
    n = s.n
    tone = _harmonic_tone(_tone(110 * s.ratio, n), 0.55, 8, 1.1) + 0.6 * _harmonic_tone(_tone(110.125 * s.ratio, n), 0.5, 6, 1.2)
    whine = 0.04 * (0.5 + s.intensity) * np.sin(_tone(3520 * s.ratio, n))
    air = 0.08 * _normalized(_filtered(s.rng.standard_normal(n), lambda f: _band(f, 900 * s.ratio, 1.2)))
    return (_normalized(tone) + whine + air) * _fades(n, min(0.4, s.duration / 4), min(0.6, s.duration / 4))


#: The crystal drone's partials: (Hz, amplitude, swell cycles over the sound) - a high, glassy
#: chord (C6 G6 C7 E7 G7) that swells and fades in turn.
DRONE_PARTIALS = ((1046.5, 1.0, 1.0), (1567.98, 0.7, 1.5), (2093.0, 0.55, 2.0), (2637.02, 0.35, 2.5), (3135.96, 0.25, 3.0))


def _drone(s: Synth) -> np.ndarray:
    # a crystalline singing drone over a deep rumble: glassy high partials (C6 G6 C7 E7 G7) with a
    # slow shimmer, each swelling in its own time, above a rumble (noise under ~90 Hz and a 55 Hz hum)
    t, u, n = s.t, s.u, s.n
    glass = np.zeros(n)
    for k, (freq, amp, cycles) in enumerate(DRONE_PARTIALS):
        shimmer = 1 + 0.004 * np.sin(2 * np.pi * (4.5 + 0.7 * k) * t)
        swell = 0.55 + 0.45 * np.sin(2 * np.pi * cycles * u + k)
        glass += amp * swell * np.sin(_tone(freq * s.ratio * shimmer, n))
    rumble = _normalized(_filtered(s.rng.standard_normal(n), lambda f: _lowpass(f, 90 * s.ratio, 2) * _highpass(f, 28.0, 2)))
    low = np.sin(_tone(55 * s.ratio, n))
    body = (0.55 + 0.25 * s.intensity) * _normalized(glass) + 0.6 * rumble + 0.35 * low
    return body * _fades(n, min(1.2, s.duration / 3), min(1.5, s.duration / 3))


def _slam(s: Synth) -> np.ndarray:
    # a steel shutter slamming down: a heavy low impact (~75 Hz falling), a metallic clang of
    # inharmonic partials ringing ~0.3 s, and a short rattle of slats (bright noise bursts)
    t, n = s.t, s.n
    scale = s.duration / 0.8
    impact = np.sin(_tone(75 * s.ratio * (1 + 0.8 * np.exp(-t / 0.02)), n)) * _decay(t, 0.001, 0.09 * scale)
    clang = _bell(n, 310 * s.ratio, s.intensity, 0.32 * scale, ((1.0, 1.0, 1.0), (2.32, 0.6, 0.7), (4.16, 0.4, 0.5), (6.39, 0.25, 0.35)))
    rattle = np.zeros(n)
    for k in range(6):
        a = int((0.03 + 0.045 * k) * scale * RATE)
        if a >= n:
            break
        m = n - a
        rattle[a:] += (0.8 - 0.1 * k) * _normalized(_filtered(s.rng.standard_normal(m), lambda f: _band(f, 2600 * s.ratio, 0.7))) * _decay(np.arange(m) / RATE, 0.0005, 0.012)
    return 1.1 * impact + 0.55 * _normalized(clang) + (0.2 + 0.25 * s.intensity) * rattle


@dataclass(frozen=True)
class BuiltinSound:
    """A built-in sound: its generator, default ``duration`` and allowed range (s), and a precise
    description of what it sounds like (for authors who cannot listen) and when to use it."""

    name: str
    generate: Callable[[Synth], np.ndarray]
    duration: float
    duration_range: tuple[float, float]
    description: str
    use: str


#: The built-in sounds, in listing order.
BUILTIN_SOUNDS: dict[str, BuiltinSound] = {
    s.name: s
    for s in (
        BuiltinSound(
            "whoosh", _whoosh, 0.6, (0.2, 3.0),
            "Air rushing past: soft band-passed noise (no pitch) whose band sweeps up from ~380 Hz to "
            "~2.7 kHz while it swells to its peak at 55% of its length and fades out smoothly.",
            "a slide, card or element moving in; a camera move",
        ),
        BuiltinSound(
            "swoosh", _swoosh, 0.45, (0.15, 3.0),
            "The reverse movement of whoosh: the noise band falls from ~2.7 kHz to ~380 Hz, "
            "peaking early (30% of its length) and trailing off.",
            "something leaving, collapsing or being swapped out",
        ),
        BuiltinSound(
            "pop", _pop, 0.12, (0.05, 0.4),
            "A short round bubble 'bloop': a sine at ~480 Hz gliding up to ~890 Hz within 30 ms, "
            "a 1 ms attack and a ~30 ms decay; friendly, not sharp.",
            "an item, bullet, icon or dot appearing",
        ),
        BuiltinSound(
            "click", _click, 0.03, (0.01, 0.1),
            "A crisp, very short UI click: a 3 ms burst of noise around 3.2 kHz with a faint 2.1 kHz "
            "ping; like a mouse button or a toggle.",
            "a selection, a toggle, a cursor click in a screen recording",
        ),
        BuiltinSound(
            "tick", _tick, 0.09, (0.03, 0.3),
            "A soft wooden tick: a 1.5 kHz woodblock-like tone with two inharmonic overtones, "
            "decaying in ~20 ms; like a clock or a counter step.",
            "counting steps, timeline marks, each step of a sequence",
        ),
        BuiltinSound(
            "typing", _typing, 1.0, (0.2, 8.0),
            "Keyboard typing: irregular soft key clicks (noise around 2.6 kHz with a low 190 Hz thock), "
            "6 to 14 keys per second for the whole duration.",
            "text or code being typed on screen",
        ),
        BuiltinSound(
            "riser", _riser, 2.0, (0.5, 8.0),
            "A build-up: noise whose band climbs from ~250 Hz to ~4.3 kHz plus a faint sine gliding up "
            "two octaves from 200 Hz, getting louder all the way and stopping at its loudest point.",
            "tension before a reveal; use align: end so it peaks on the reveal",
        ),
        BuiltinSound(
            "chime", _chime, 1.6, (0.4, 5.0),
            "A clear bell note at A5 (880 Hz) with soft inharmonic overtones, a 2 ms strike and a "
            "ringing decay over about its length.",
            "a key insight, a highlight, a result appearing",
        ),
        BuiltinSound(
            "success", _success, 0.9, (0.4, 3.0),
            "A positive two-note ding: soft bell notes E5 then B5 (a rising fifth) 110 ms apart, "
            "ringing out.",
            "a check mark, a test passing, a goal reached",
        ),
        BuiltinSound(
            "error", _error, 0.5, (0.3, 2.0),
            "A gentle 'nope': two muted, slightly hollow notes falling from G4 to E-flat4, 160 ms "
            "apart, low-passed so they stay soft.",
            "a mistake, a failing case, a crossed-out option",
        ),
        BuiltinSound(
            "thud", _thud, 0.45, (0.15, 1.5),
            "A soft low impact: a sine dropping from 110 Hz to 55 Hz with a muffled knock at "
            "~320 Hz, decaying in ~0.15 s; felt more than heard on small speakers.",
            "something heavy landing, a big number or a final statement",
        ),
        BuiltinSound(
            "footstep", _footstep, 0.14, (0.06, 0.4),
            "One soft footstep: a muffled heel knock (noise around 260 Hz with a low 95 Hz thump) "
            "decaying in ~20 ms, then a faint scuff of the sole (noise around 1.8 kHz).",
            "a character's step; stage walks play one per footfall (foley)",
        ),
        BuiltinSound(
            "step_grass", _step_grass, 0.16, (0.06, 0.4),
            "One step on grass: a soft swish of blades (noise around 2.5 kHz, swelling over ~25 ms "
            "and trailing off over ~90 ms) over a faint, muffled heel (noise around 180 Hz).",
            "a character's step on grass (walks on an iso place's grass play it: foley)",
        ),
        BuiltinSound(
            "step_gravel", _step_gravel, 0.18, (0.06, 0.4),
            "One step on a sandy path: a crunch of 25-40 tiny grain clicks (noise around 2.2 kHz) "
            "spread over ~80 ms, thickest at the start, over a soft heel knock (~240 Hz).",
            "a step on a path, gravel or sand (walks on an iso place's paths play it: foley)",
        ),
        BuiltinSound(
            "step_wood", _step_wood, 0.16, (0.06, 0.4),
            "One step on wooden boards: a hollow knock, a thump near 150 Hz with the boards ringing "
            "at ~340 and ~720 Hz for ~45 ms, and a short heel tap (noise around 1.2 kHz).",
            "a step on a wooden floor or a bridge (walks on an iso place's boards and bridges play "
            "it, a bridge lower: foley)",
        ),
        BuiltinSound(
            "step_stone", _step_stone, 0.12, (0.05, 0.3),
            "One step on stone or tiles: a hard, short heel click (noise around 2.8 kHz, ~5 ms) with "
            "a small dry body (~260 Hz, ~15 ms); no scuff.",
            "a step on stone, steps or tiles (walks on an iso place's stone blocks and tiles play "
            "it: foley)",
        ),
        BuiltinSound(
            "boing", _boing, 0.5, (0.2, 1.5),
            "A cartoon spring: a twangy tone gliding up from ~140 Hz to ~260 Hz with a fast 12 Hz "
            "wobble that dies away, decaying over about its length.",
            "a jump, a bounce, something springy (stage jumps play it: foley)",
        ),
        BuiltinSound(
            "bell", _ring, 0.7, (0.3, 2.0),
            "A bicycle bell, 'ring-ring': two quick strikes 130 ms apart of a small bright bell at "
            "~2.35 kHz with inharmonic overtones, a fast shimmer, each ringing out in ~0.2 s.",
            "a bicycle setting off (a stage's bicycle ride_to plays it: foley), a doorbell-like call",
        ),
        BuiltinSound(
            "engine", _engine, 1.6, (0.5, 8.0),
            "A small engine starting and running: a buzzy low tone (~42 Hz with many harmonics and "
            "uneven firing pulses) revving up over the first fifth, settling, with a soft rumble "
            "around 180 Hz; fades in and out.",
            "a car or a bus setting off (a stage's ride_to plays it for most of the ride: foley)",
        ),
        BuiltinSound(
            "brakes", _brakes, 0.5, (0.2, 1.5),
            "Brakes squealing to a stop: a thin tone near 2.1 kHz wavering and falling a little, "
            "over a soft scrape of noise, swelling and stopping short.",
            "a vehicle stopping (a stage's ride_to plays it as the vehicle stops: foley)",
        ),
        BuiltinSound(
            "burner", _burner, 1.2, (0.4, 4.0),
            "A gas burner's roar: deep breathy noise around 450 Hz (low-passed at 1.4 kHz) with a "
            "faint hiss near 2.6 kHz, catching at once, fluttering a little at 9 Hz, dying away "
            "over the last 0.3 s.",
            "a hot-air balloon rising (a stage's balloon ride_to plays it: foley), a gas flame",
        ),
        BuiltinSound(
            "launch", _launch, 1.0, (0.4, 3.0),
            "A toy rocket taking off: a soft low 'whump' (~75 Hz falling) as it lights, then a "
            "fizzing hiss whose band climbs from ~1.5 to ~5 kHz with a crackle of tiny clicks, "
            "fading out as it flies away.",
            "a toy rocket or a firework launching (a stage's toy_rocket ride_to plays it: foley)",
        ),
        BuiltinSound(
            "phone", _phone, 1.0, (0.4, 3.0),
            "A phone ringing, 'brring-brring': a soft electronic trill (a tone flipping between ~1.1 "
            "and ~1.4 kHz 20 times a second) in two pulses of about 0.4 s with a short gap.",
            "a phone ringing (a stage's phone plays it at each burst of rings while it is on: foley)",
        ),
        BuiltinSound(
            "thunder", _thunder, 3.0, (1.0, 8.0),
            "Thunder: a crack of bright noise around 1.8 kHz at the start (stronger with intensity, "
            "as from a near strike), then a deep rumble (noise below ~120 Hz) rolling in three to "
            "five swells over the first 60% and dying away over its whole length.",
            "a storm (a stage's lightning action and rain with lightning play it after the flash, "
            "later, quieter, longer and lower the farther the strike: foley)",
        ),
        BuiltinSound(
            "creak", _creak, 0.9, (0.3, 3.0),
            "A door's hinge creaking: a rough, buzzy squeak of stick-slip pulses whose rate glides "
            "from ~45 up to ~110 Hz and back to ~70 Hz with a wobble, coloured by a wooden body "
            "(~550 Hz, ~1.3 kHz, ~2.6 kHz), swelling early and fading out.",
            "a door opening or closing (a stage's open / close of a door and an enter / exit through "
            "a closed one play it: foley), an old chair, a spooky moment",
        ),
        BuiltinSound(
            "knock", _knock, 0.75, (0.3, 2.0),
            "Knock-knock-knock: three knuckle raps on a wooden door 190 ms apart, each a dull hollow "
            "thump (~190 and ~410 Hz, ringing ~30 ms) with a short bright tap around 1.5 kHz.",
            "someone at the door (a stage's knock action plays it: foley)",
        ),
        BuiltinSound(
            "unlock", _unlock, 0.3, (0.15, 0.8),
            "A key turning in a lock: a small metallic tick as the key catches (noise around 2.2 kHz "
            "with a ~1.7 kHz ping, ~5 ms), then 90 ms later a rounder clack of the bolt sliding back "
            "(~620 Hz with a soft ~170 Hz knock); low-passed, not sharp.",
            "a key opening a lock (a locked door opened with its key on a platform level plays it, "
            "before the creak: foley), a box or a chest unlocking",
        ),
        BuiltinSound(
            "coin", _coin, 0.45, (0.2, 1.5),
            "A coin picked up, 'pling-ling': two quick soft bell notes rising a fourth, B5 (~990 Hz) "
            "then E6 (~1.3 kHz) 70 ms apart, the second ringing a little longer, with a faint "
            "14 Hz shimmer.",
            "a coin collected (walks and jumps on a platform level play it at each coin, a little "
            "higher for each further coin of the same move: foley), a point scored",
        ),
        BuiltinSound(
            "twinkle", _twinkle, 0.8, (0.3, 2.5),
            "A star picked up: a quick rising arpeggio of four soft bell notes, C6 E6 G6 C7 (~1 to "
            "~2.1 kHz) 50 ms apart, ringing on together, with a faint airy glitter around 6 kHz "
            "fading away.",
            "a star or something magic collected (walks and jumps on a platform level play it at "
            "each star: foley), a wish, a sparkle",
        ),
        BuiltinSound(
            "splash", _splash, 0.6, (0.2, 3.0),
            "Something dropping into water: a burst of bright noise around 2.5 kHz (~70 ms) with a "
            "low 'plunk' gliding up from ~250 to ~600 Hz, then droplets falling back (tiny rising "
            "blips at 1-3 kHz, thinning out) and a fading fizz; at low intensity mostly droplets.",
            "water (a boat setting off, a watering can pouring, steps in puddles play it: foley), "
            "something falling into a pond",
        ),
        BuiltinSound(
            "gasp", _gasp, 0.35, (0.15, 1.0),
            "A sharp breath in through an open mouth, 'hah': unvoiced breath noise in three bands "
            "(~1.1, ~1.75 and ~2.9 kHz) rising a little, at its loudest after ~50 ms, held, then cut "
            "off quickly at the end.",
            "a character's surprise (a beat's [gasp] at the start or end of a line plays it)",
        ),
        BuiltinSound(
            "sigh", _sigh, 0.9, (0.4, 2.5),
            "A long breath out, 'haaah': breathy noise shaped like an open 'ah' (~750 Hz and "
            "~1.2 kHz, falling a little) with a faint low hum gliding from ~190 to ~130 Hz, swelling "
            "over the first fifth and trailing off.",
            "tiredness, relief or giving up (a beat's [sigh] at the start or end of a line plays it)",
        ),
        BuiltinSound(
            "beep", _beep, 0.4, (0.2, 1.2),
            "A friendly robot chirp, 'bee-boop': two soft electronic notes, ~1.3 kHz (with a quick "
            "upward blip as it starts) then ~880 Hz, the first 42% and the last 52% of its length.",
            "a robot's voice sound (a beat's [beep] at the start or end of a line plays it), a gadget",
        ),
        BuiltinSound(
            "sting_reveal", _sting_reveal, 1.4, (0.6, 4.0),
            "A short 'ta-da' music sting: a brassy pickup note G4, then a bright C major chord "
            "(C5 E5 G5 C6) with a soft high bell, ringing out over about a second.",
            "a reveal or a triumphant moment (beat sting: reveal)",
        ),
        BuiltinSound(
            "sting_comic", _sting_comic, 1.1, (0.6, 3.0),
            "A comedy drum sting, 'ba-dum-tss': two tom hits falling in pitch (~200 then ~150 Hz) "
            "150 ms apart, then a splashy cymbal (noise around 7.5 kHz) decaying in ~0.3 s.",
            "right after a punchline (beat sting: comic)",
        ),
        BuiltinSound(
            "sting_sad", _sting_sad, 2.2, (1.2, 5.0),
            "A 'sad trombone' sting, 'wah wah wah waaah': four muted brass notes falling by "
            "semitones from B-flat3 to G3, each opening and closing like a wah mute; the last "
            "one long, sagging and wobbling.",
            "a failure or a let-down, played for laughs (beat sting: sad)",
        ),
        BuiltinSound(
            "alarm", _alarm, 2.7, (0.9, 12.0),
            "An alarm siren, 'hee-haw': two buzzy tones, ~960 and ~780 Hz, alternating every 0.45 s "
            "for the whole length.",
            "an alarm going off (a stage's alarm action plays it as a bed while it runs: foley), a warning",
        ),
        BuiltinSound(
            "crackle", _crackle, 1.5, (0.3, 8.0),
            "Crackling energy: clusters of sharp electric snaps (bright, around 3-5 kHz) over a faint "
            "100 Hz buzz that flares with them.",
            "sparks, a short circuit, a rift or a force field crackling",
        ),
        BuiltinSound(
            "hum", _hum, 3.0, (0.5, 15.0),
            "A soft electronic hum: a 110 Hz tone with its harmonics and a second voice beating slowly "
            "against it, a faint ~3.5 kHz whine and air, fading in and out.",
            "a machine or a screen powering up, a lab or a spaceship (the hum bed holds it under a scene)",
        ),
        BuiltinSound(
            "drone", _drone, 6.0, (1.5, 20.0),
            "A crystalline singing drone: a high glassy chord (C6 G6 C7 E7 G7) shimmering slowly, each "
            "note swelling in turn, over a deep rumble (noise under ~90 Hz and a 55 Hz hum); slow fades.",
            "awe, a magical or otherworldly place, a doorway to another world",
        ),
        BuiltinSound(
            "slam", _slam, 0.8, (0.3, 2.0),
            "A steel shutter slamming down: a heavy low impact (~75 Hz falling), a metallic clang ringing "
            "~0.3 s and a short rattle of slats.",
            "shutters or a metal door slamming (a stage's shutters action plays it: foley), a heavy impact",
        ),
    )
}
#: The music stings of a beat's ``sting:`` (DESIGN.md §69.19): kind -> built-in sound.
STING_SOUNDS: dict[str, str] = {"reveal": "sting_reveal", "comic": "sting_comic", "sad": "sting_sad"}


@lru_cache(maxsize=128)
def _builtin(name: str, duration: float, pitch: float, intensity: float) -> np.ndarray:
    sound = BUILTIN_SOUNDS[name]
    n = max(int(round(duration * RATE)), 64)
    rng = np.random.default_rng(zlib.crc32(name.encode("utf-8")))
    raw = sound.generate(Synth(n, 2 ** (pitch / 12), intensity, rng))
    fade_out = 0.04 if name == "riser" else min(0.01, duration / 4)
    out = _finish(raw, intensity, fade_out=fade_out)
    out.setflags(write=False)
    return out


def synthesize(name: str, duration: float | None = None, pitch: float = 0.0, intensity: float = 0.5) -> np.ndarray:
    """A built-in sound as mono float32 samples at :data:`RATE` (read-only; cached).

    ``duration`` defaults to the sound's own; ``pitch`` shifts its frequencies by semitones;
    ``intensity`` (0-1) makes it brighter and up to 3 dB louder (0.5: as designed).
    """
    sound = BUILTIN_SOUNDS.get(name)
    if sound is None:
        raise VidgenError(unknown_sound_message(name, list(BUILTIN_SOUNDS)))
    return _builtin(name, float(duration or sound.duration), float(pitch), float(intensity))


# ----- project sounds ------------------------------------------------------------------------------


def project_sounds(root: Path | None) -> dict[str, Path]:
    """The project's own sounds: ``assets/sfx/<name>.<wav|flac|ogg|mp3>`` by name (a name with
    several files: the first suffix of :data:`SFX_SUFFIXES`). Files whose name is not a valid
    sound name are skipped with a warning."""
    folder = None if root is None else root / PROJECT_SFX_DIR
    if folder is None or not folder.is_dir():
        return {}
    found: dict[str, Path] = {}
    for suffix in SFX_SUFFIXES:
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() != suffix or not path.is_file():
                continue
            if not SOUND_NAME.match(path.stem):
                log.warning("%s: not a valid sound name (letters, digits, _ and -); skipped", path.name)
                continue
            found.setdefault(path.stem, path)
    return dict(sorted(found.items()))


def decode_audio(path: Path, rate: int = RATE, mono: bool = False) -> np.ndarray:
    """An audio file as float32 samples at ``rate`` (default :data:`RATE`): ``(n, 1)`` for mono
    files or with ``mono``, ``(n, 2)`` otherwise (more channels are mixed down). Read with PyAV."""
    import av

    try:
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            channels = 1 if mono or (stream.channels or 2) == 1 else 2
            resampler = av.AudioResampler(format="flt", layout="mono" if channels == 1 else "stereo", rate=rate)
            chunks = []
            for frame in container.decode(stream):
                chunks += [f.to_ndarray().reshape(-1, channels) for f in resampler.resample(frame)]
            chunks += [f.to_ndarray().reshape(-1, channels) for f in resampler.resample(None)]
    except (OSError, IndexError, ValueError, av.error.FFmpegError) as exc:
        raise VidgenError(f"cannot read sound file {path}: {exc}") from None
    if not chunks:
        raise VidgenError(f"cannot read sound file {path}: no audio samples")
    return np.concatenate(chunks).astype(np.float32)


@lru_cache(maxsize=64)
def _project_sound(path: Path, size: int, mtime: int) -> np.ndarray:
    data = decode_audio(path)
    data.setflags(write=False)
    return data


# ----- library and checks --------------------------------------------------------------------------


def unknown_sound_message(name: str, names: Sequence[str]) -> str:
    """``unknown sound 'x'; did you mean 'y'? (sounds: ...)``."""
    message = f"unknown sound '{name}'"
    close = difflib.get_close_matches(name, names, n=2)
    if close:
        message += f"; did you mean {' or '.join(repr(c) for c in close)}?"
    return message + f" (sounds: {', '.join(names)}; `vidgen list-sfx` describes them, assets/sfx/NAME.wav adds one)"


def config_problems(config: VideoConfig, root: Path | None) -> list[tuple[str, str]]:
    """``(location, message)`` problems of the scenes' ``sfx:`` lists (unknown sounds, params
    that do not fit; the cues' structure is checked by the config model)."""
    library = SoundLibrary(root)
    found: list[tuple[str, str]] = []
    for i, scene in enumerate(config.scenes):
        for k, cue in enumerate(scene.sfx):
            for key, message in library.problems(cue.sound, cue.params.model_dump(exclude_none=True)):
                found.append((f"scenes[{i}].sfx[{k}].{key}", message))
    return found


def sound_library() -> SoundLibrary:
    """The sounds of the active project (``vidgen.runtime`` context): built-ins and its
    ``assets/sfx``; only the built-ins without a context."""
    from vidgen import runtime

    return SoundLibrary(runtime.current_project().root if runtime.has_context() else None)


class SoundLibrary:
    """The sounds a project can use: the built-ins and its ``assets/sfx`` files (a project file
    with a built-in's name replaces it)."""

    def __init__(self, root: Path | None) -> None:
        self.root = root
        self.custom = project_sounds(root)

    def names(self) -> list[str]:
        """Every sound name: built-ins in listing order, then the project's own."""
        return list(BUILTIN_SOUNDS) + [n for n in self.custom if n not in BUILTIN_SOUNDS]

    def file(self, name: str) -> Path | None:
        """The project file of ``name``, or ``None`` (a built-in, or unknown)."""
        return self.custom.get(name)

    def knows(self, name: str) -> bool:
        """Whether ``name`` is a sound of the library."""
        return name in self.custom or name in BUILTIN_SOUNDS

    def problems(self, name: str, params: Mapping[str, Any]) -> list[tuple[str, str]]:
        """``(key, message)`` problems of playing ``name`` with ``params`` (``duration``,
        ``pitch``, ``intensity``; only those given): an unknown name, params on a project file,
        a duration outside the sound's range."""
        if not self.knows(name):
            return [("sound", unknown_sound_message(name, self.names()))]
        given = {k: v for k, v in params.items() if v is not None}
        path = self.file(name)
        if path is not None:
            if given:
                where = path.relative_to(self.root).as_posix() if self.root is not None else path.name
                return [("params", f"params ({', '.join(given)}) shape the built-in sounds; '{name}' is the project's file {where}")]
            return []
        lo, hi = BUILTIN_SOUNDS[name].duration_range
        duration = given.get("duration")
        if duration is not None and not lo <= duration <= hi:
            return [("params.duration", f"'{name}' lasts {lo:g} to {hi:g} s, got {duration:g}")]
        return []

    def audio(self, name: str, params: Mapping[str, Any]) -> np.ndarray:
        """The samples of ``name`` (mono ``(n,)`` for built-ins; ``(n, 1|2)`` for files)."""
        path = self.file(name)
        if path is not None:
            st = path.stat()
            return _project_sound(path, st.st_size, st.st_mtime_ns)
        given = {k: v for k, v in params.items() if v is not None}
        return synthesize(name, **given)


def _decibels(value: float) -> float | None:
    """A level rounded to 0.1 dB for listings (``None`` for silence)."""
    return round(value, 1) if math.isfinite(value) else None


def sound_entries(library: SoundLibrary, preview_dir: Path | None = None) -> list[dict[str, Any]]:
    """Every sound of ``library`` described for ``vidgen list-sfx``: ``{name, origin,
    overrides_builtin, description, use, duration, duration_range, channels, loudness, peak_db,
    preview}`` (the sound at its defaults; ``preview``: the WAV written to ``preview_dir``, else
    ``None``). Project sounds have no ``description`` / ``use`` / ``duration_range``."""
    entries = []
    for name in library.names():
        path = library.file(name)
        builtin = BUILTIN_SOUNDS.get(name) if path is None else None
        data = library.audio(name, {})
        preview = None
        if preview_dir is not None:
            preview = preview_dir / f"{name}.wav"
            write_wav(preview, data)
        entries.append(
            {
                "name": name,
                "origin": "builtin" if path is None else path.relative_to(library.root).as_posix() if library.root else path.name,
                "overrides_builtin": path is not None and name in BUILTIN_SOUNDS,
                "description": builtin.description if builtin else None,
                "use": builtin.use if builtin else None,
                "duration": round(len(data) / RATE, 3),
                "duration_range": list(builtin.duration_range) if builtin else None,
                "channels": 1 if data.ndim == 1 else int(data.shape[1]),
                "loudness": _decibels(loudness(data)),
                "peak_db": _decibels(peak_db(data)),
                "preview": preview,
            }
        )
    return entries


# ----- events and the track ------------------------------------------------------------------------


@dataclass(frozen=True)
class SfxEvent:
    """One sound effect of a scene: when (``time``, seconds), which ``sound``, ``gain`` (dB),
    ``pan`` (-1 left to 1 right), ``align`` (``start``: it starts at ``time``; ``end``: it ends
    there), the sound's ``params``, the ``beat`` it belongs to (``None``: none) and ``duck``:
    whether it ducks under the narration (a beat's music sting, DESIGN.md §69.19)."""

    time: float
    sound: str
    gain: float = 0.0
    pan: float = 0.0
    align: str = "start"
    params: Mapping[str, Any] = field(default_factory=dict)
    beat: str | None = None
    duck: bool = False

    def to_json(self) -> dict[str, Any]:
        """``{time, sound, gain, pan, align, params, beat}``, plus ``duck: true`` when it ducks."""
        data = {
            "time": round(self.time, 6),
            "sound": self.sound,
            "gain": self.gain,
            "pan": self.pan,
            "align": self.align,
            "params": dict(self.params),
            "beat": self.beat,
        }
        if self.duck:
            data["duck"] = True
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SfxEvent:
        """The event of :meth:`to_json`."""
        return cls(
            float(data["time"]), str(data["sound"]), float(data.get("gain", 0.0)), float(data.get("pan", 0.0)),
            str(data.get("align", "start")), dict(data.get("params") or {}), data.get("beat"), bool(data.get("duck", False)),
        )

    def shifted(self, offset: float) -> SfxEvent:
        """The same event ``offset`` seconds later (scene time → video time)."""
        return replace(self, time=self.time + offset)


def stereo(samples: np.ndarray, gain_db: float = 0.0, pan: float = 0.0) -> np.ndarray:
    """``(n, 2)`` float32: mono samples on both channels (pan 0: each at full level; equal-power
    pan law, hard left/right +3 dB on one side), or a stereo file balanced by ``pan``."""
    gain = 10 ** (gain_db / 20)
    angle = (pan + 1) * math.pi / 4
    left, right = math.sqrt(2) * math.cos(angle), math.sqrt(2) * math.sin(angle)
    x = samples.reshape(len(samples), -1)
    if x.shape[1] == 1:
        return (x * np.array([left, right], dtype=np.float32) * gain).astype(np.float32)
    balance = np.array([min(1.0, 1 - pan), min(1.0, 1 + pan)], dtype=np.float32)
    return (x[:, :2] * balance * gain).astype(np.float32)


def placed(event: SfxEvent, library: SoundLibrary, master_db: float = 0.0, audio: np.ndarray | None = None) -> tuple[int, np.ndarray]:
    """``(first sample, (n, 2) samples)`` of an event on a track that starts at time 0 (the first
    sample may be negative: the part before 0 is cut); ``audio``: samples to play instead of the
    event's sound."""
    data = stereo(library.audio(event.sound, event.params) if audio is None else audio, event.gain + master_db, event.pan)
    start = round(event.time * RATE)
    if event.align == "end":
        start -= len(data)
    return start, data


def ducked(start: int, data: np.ndarray, ducking_db: np.ndarray) -> np.ndarray:
    """``data`` (``(n, 2)``, from sample ``start`` of the track) times the ducking gain
    ``ducking_db`` (dB per 10 ms frame of the track, :func:`vidgen.mix.duck_curve`), interpolated
    per sample."""
    frames = np.arange(start, start + len(data)) / (RATE // 100)
    gain_db = np.interp(frames, np.arange(len(ducking_db)), ducking_db)
    return (data * (10 ** (gain_db / 20))[:, None]).astype(np.float32)


def write_track(
    path: Path,
    events: Sequence[SfxEvent],
    samples: int,
    library: SoundLibrary,
    master_db: float = 0.0,
    ducking_db: np.ndarray | None = None,
    replaced: Mapping[int, np.ndarray] | None = None,
) -> None:
    """Write ``path``: a 48 kHz stereo 16-bit WAV of exactly ``samples`` samples holding the
    events (video times) at their sample positions; written in 10 s blocks (a long video's track
    never sits in memory whole); sums beyond full scale are clipped. Events with ``duck`` are
    scaled by ``ducking_db`` (dB per 10 ms frame; ``None``: not ducked). ``replaced``: samples
    played instead of the sound of the event at that index (stings with composed music)."""
    replaced = replaced or {}
    sounds = [placed(e, library, master_db, replaced.get(k)) for k, e in enumerate(events)]
    if ducking_db is not None:
        sounds = [(start, ducked(start, data, ducking_db)) if e.duck else (start, data) for e, (start, data) in zip(events, sounds)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        for block in range(0, samples, _BLOCK):
            size = min(_BLOCK, samples - block)
            buf = np.zeros((size, 2), dtype=np.float32)
            for start, data in sounds:
                lo, hi = max(start, block), min(start + len(data), block + size)
                if lo < hi:
                    buf[lo - block : hi - block] += data[lo - start : hi - start]
            pcm = np.clip(np.round(buf * 32767), -32768, 32767).astype("<i2")
            out.writeframes(pcm.tobytes())


def read_wav(path: Path) -> np.ndarray:
    """A 16-bit PCM WAV as float32 ``(n, channels)`` (for tests and previews)."""
    with wave.open(str(path), "rb") as src:
        channels = src.getnchannels()
        data = np.frombuffer(src.readframes(src.getnframes()), dtype="<i2")
    return (data.reshape(-1, channels) / 32768).astype(np.float32)


def wav_bytes(samples: np.ndarray) -> bytes:
    """Float samples (mono ``(n,)`` or ``(n, c)``, 48 kHz) as the bytes of a 16-bit PCM WAV file."""
    x = samples.reshape(len(samples), -1)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(x.shape[1])
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(np.clip(np.round(x * 32767), -32768, 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def write_wav(path: Path, samples: np.ndarray) -> None:
    """Write float samples (mono ``(n,)`` or ``(n, c)``, 48 kHz) as a 16-bit PCM WAV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav_bytes(samples))
