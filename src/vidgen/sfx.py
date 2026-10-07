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
import logging
import math
import re
import wave
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
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
    )
}


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


def decode_audio(path: Path) -> np.ndarray:
    """An audio file as float32 samples at :data:`RATE`: ``(n, 1)`` for mono files, ``(n, 2)``
    otherwise (more channels are mixed down to stereo). Read with PyAV."""
    import av

    try:
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            channels = 1 if (stream.channels or 2) == 1 else 2
            resampler = av.AudioResampler(format="flt", layout="mono" if channels == 1 else "stereo", rate=RATE)
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
    there), the sound's ``params`` and the ``beat`` it belongs to (``None``: none)."""

    time: float
    sound: str
    gain: float = 0.0
    pan: float = 0.0
    align: str = "start"
    params: Mapping[str, Any] = field(default_factory=dict)
    beat: str | None = None

    def to_json(self) -> dict[str, Any]:
        """``{time, sound, gain, pan, align, params, beat}``."""
        return {
            "time": round(self.time, 6),
            "sound": self.sound,
            "gain": self.gain,
            "pan": self.pan,
            "align": self.align,
            "params": dict(self.params),
            "beat": self.beat,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SfxEvent:
        """The event of :meth:`to_json`."""
        return cls(
            float(data["time"]), str(data["sound"]), float(data.get("gain", 0.0)), float(data.get("pan", 0.0)),
            str(data.get("align", "start")), dict(data.get("params") or {}), data.get("beat"),
        )

    def shifted(self, offset: float) -> SfxEvent:
        """The same event ``offset`` seconds later (scene time → video time)."""
        return SfxEvent(self.time + offset, self.sound, self.gain, self.pan, self.align, self.params, self.beat)


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


def placed(event: SfxEvent, library: SoundLibrary, master_db: float = 0.0) -> tuple[int, np.ndarray]:
    """``(first sample, (n, 2) samples)`` of an event on a track that starts at time 0 (the first
    sample may be negative: the part before 0 is cut)."""
    data = stereo(library.audio(event.sound, event.params), event.gain + master_db, event.pan)
    start = round(event.time * RATE)
    if event.align == "end":
        start -= len(data)
    return start, data


def write_track(path: Path, events: Sequence[SfxEvent], samples: int, library: SoundLibrary, master_db: float = 0.0) -> None:
    """Write ``path``: a 48 kHz stereo 16-bit WAV of exactly ``samples`` samples holding the
    events (video times) at their sample positions; written in 10 s blocks (a long video's track
    never sits in memory whole); sums beyond full scale are clipped."""
    sounds = [placed(e, library, master_db) for e in events]
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


def write_wav(path: Path, samples: np.ndarray) -> None:
    """Write float samples (mono ``(n,)`` or ``(n, c)``, 48 kHz) as a 16-bit PCM WAV."""
    x = samples.reshape(len(samples), -1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(x.shape[1])
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(np.clip(np.round(x * 32767), -32768, 32767).astype("<i2").tobytes())
