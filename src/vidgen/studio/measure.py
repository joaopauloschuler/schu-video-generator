"""Measurements of a piece of music, for agents who cannot listen (DESIGN.md §93.8): the tempo
heard in its onsets, its pitch-class (chroma) profile and key, its loudness bar by bar and the
balance of its frequency bands. Used to check that a bed's template sounds close to the bed;
Step 187's ``vidgen music check`` builds on them.

All take float audio ``(n,)`` or ``(n, 2)`` at 48 kHz.
"""

from __future__ import annotations

import math

import numpy as np

from vidgen.loudness import integrated_loudness
from vidgen.sfx import RATE

#: Frequency bands of :func:`band_balance` (Hz): sub and kick, bass, low mids, the voice's
#: core, presence, air.
BANDS = ((20.0, 150.0), (150.0, 300.0), (300.0, 1000.0), (1000.0, 3000.0), (3000.0, 6000.0), (6000.0, 20000.0))
#: Krumhansl-Kessler key profiles (major, minor), tonic first.
_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
_HOP = 480  # 10 ms
_FRAME = 2048


def _mono(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return x.mean(axis=1) if x.ndim == 2 else x


def onset_strength(x: np.ndarray) -> np.ndarray:
    """The rise of the sound every 10 ms: the positive change of the log spectrum (2048-sample
    Hann frames) summed over 30 Hz - 8 kHz, minus its local mean."""
    mono = _mono(x)
    count = max(1, (len(mono) - _FRAME) // _HOP + 1)
    frames = np.lib.stride_tricks.sliding_window_view(mono, _FRAME)[::_HOP][:count] * np.hanning(_FRAME)
    freqs = np.fft.rfftfreq(_FRAME, 1 / RATE)
    keep = (freqs >= 30) & (freqs <= 8000)
    mag = np.log1p(1000 * np.abs(np.fft.rfft(frames, axis=1))[:, keep])
    flux = np.maximum(np.diff(mag, axis=0), 0).sum(axis=1)
    kernel = np.ones(50) / 50
    return np.maximum(flux - np.convolve(flux, kernel, mode="same"), 0)


def tempo(x: np.ndarray, low: float = 70.0, high: float = 180.0) -> float | None:
    """The tempo (quarter notes per minute) the onsets repeat at, between ``low`` and ``high``
    BPM; ``None`` when there is no clear beat (the autocorrelation's best peak under 0.2)."""
    onsets = onset_strength(x)
    onsets = onsets - onsets.mean()
    energy = float(np.dot(onsets, onsets))
    if energy <= 0:
        return None
    spectrum = np.fft.rfft(onsets, 2 * len(onsets))
    corr = np.fft.irfft(spectrum * np.conj(spectrum))[: len(onsets)] / energy
    rate = RATE / _HOP
    lags = np.arange(int(rate * 60 / high), int(rate * 60 / low) + 2)
    best = int(lags[np.argmax(corr[lags])])
    if corr[best] < 0.2:
        return None
    # parabolic refinement of the peak
    a, b, c = corr[best - 1], corr[best], corr[best + 1]
    shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    return 60 * rate / (best + shift)


def chroma(x: np.ndarray, low: float = 60.0, high: float = 2500.0) -> np.ndarray:
    """The share of the power in each pitch class (C first) between ``low`` and ``high`` Hz,
    from one spectrum of the whole sound; sums to 1."""
    mono = _mono(x)
    power = np.abs(np.fft.rfft(mono)) ** 2
    freqs = np.fft.rfftfreq(len(mono), 1 / RATE)
    keep = (freqs >= low) & (freqs <= high)
    classes = np.round(12 * np.log2(freqs[keep] / 440.0) + 69).astype(int) % 12
    out = np.bincount(classes, weights=power[keep], minlength=12)
    return out / max(float(out.sum()), 1e-30)


def chroma_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """The cosine similarity of two chroma profiles (1: the same)."""
    return float(np.dot(a, b) / max(float(np.linalg.norm(a) * np.linalg.norm(b)), 1e-30))


def key_fits(profile: np.ndarray) -> dict[str, float]:
    """How well a chroma ``profile`` fits each of the 24 major and minor keys: its correlation
    with the key's Krumhansl-Kessler profile (``{"C major": 0.71, ...}``)."""
    return {
        f"{_NAMES[tonic]} {mode}": float(np.corrcoef(profile, np.roll(shape, tonic))[0, 1])
        for mode, shape in (("major", _MAJOR), ("minor", _MINOR))
        for tonic in range(12)
    }


def key(profile: np.ndarray) -> str:
    """The key that fits a chroma ``profile`` best (``"G minor"``; :func:`key_fits`)."""
    fits = key_fits(profile)
    return max(fits, key=fits.__getitem__)


def loudness_curve(x: np.ndarray, block: int) -> np.ndarray:
    """The integrated loudness (LUFS) of each ``block`` samples (a bar, say)."""
    x = np.asarray(x, dtype=np.float64)
    return np.array([integrated_loudness(x[a : a + block]) for a in range(0, len(x) - block + 1, block)])


def band_balance(x: np.ndarray) -> np.ndarray:
    """The level of each of :data:`BANDS` against the whole sound's power, in dB."""
    mono = _mono(x)
    power = np.abs(np.fft.rfft(mono)) ** 2
    freqs = np.fft.rfftfreq(len(mono), 1 / RATE)
    total = max(float(power.sum()), 1e-30)
    return np.array([10 * math.log10(max(float(power[(freqs >= lo) & (freqs < hi)].sum()), 1e-30) / total) for lo, hi in BANDS])
