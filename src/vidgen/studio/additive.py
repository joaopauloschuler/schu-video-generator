"""Additive synthesis for the orchestral score instruments (DESIGN.md §120.4): a note's harmonics
summed once into one-period wave tables, which are then read along the note's phase. A note
with a hundred harmonics costs the same per sample as one with three, and a spectrum that changes
over the note (brass getting brighter as it gets louder) is a cross-fade between a few tables."""

from __future__ import annotations

import zlib
from collections.abc import Callable, Mapping
from functools import lru_cache

import numpy as np

from vidgen.sfx import RATE, _band, _filtered, _lowpass

#: No harmonic is made above this (Hz): room under the Nyquist frequency for vibrato and detune.
HIGHEST_PARTIAL = 16000.0
#: Table samples per period of the highest harmonic: linear interpolation then errs by under -70 dB.
_SAMPLES_PER_CYCLE = 128


#: Notes up to this many samples are remembered (the last 48: under 70 MB of stereo notes).
_REMEMBERED_SAMPLES = 2 * RATE

NoteMaker = Callable[[float, int, Mapping[str, float], str], np.ndarray]


def remembered(make: NoteMaker) -> NoteMaker:
    """``make`` (``(Hz, samples, settings, seed) -> note``) remembering its last short notes: an
    ostinato repeats a few notes hundreds of times. The notes it returns are read-only."""

    @lru_cache(maxsize=48)
    def kept(freq: float, n: int, settings: tuple[tuple[str, float], ...], seed: str) -> np.ndarray:
        note = make(freq, n, dict(settings), seed)
        note.setflags(write=False)
        return note

    def note(freq: float, n: int, s: Mapping[str, float], seed: str) -> np.ndarray:
        if n > _REMEMBERED_SAMPLES:
            return make(freq, n, s, seed)
        return kept(freq, n, tuple(sorted(s.items())), seed)

    return note


def seeded(*parts: object) -> np.random.Generator:
    """A random generator that depends on ``parts`` only (their text, CRC-32)."""
    return np.random.default_rng(zlib.crc32(":".join(str(p) for p in parts).encode("utf-8")))


def harmonic_count(freq: float, limit: float = HIGHEST_PARTIAL) -> int:
    """How many harmonics of ``freq`` lie at or under ``limit`` Hz (at least 1)."""
    return max(int(limit / freq), 1)


def wavetables(amplitudes: np.ndarray) -> np.ndarray:
    """One period of ``sum(a[h] * sin(2 pi (h + 1) x))`` per row of ``amplitudes`` ``(rows,
    harmonics)``: float64 ``(rows, size + 1)``, the first sample repeated at the end (for
    :func:`read_tables`)."""
    rows, count = amplitudes.shape
    size = max(2048, 1 << (count * _SAMPLES_PER_CYCLE - 1).bit_length())
    spectrum = np.zeros((rows, size // 2 + 1), dtype=np.complex128)
    spectrum[:, 1 : count + 1] = -0.5j * size * amplitudes
    tables = np.empty((rows, size + 1))
    tables[:, :size] = np.fft.irfft(spectrum, size, axis=1)
    tables[:, size] = tables[:, 0]
    return tables


def read_tables(tables: np.ndarray, phase: np.ndarray, row: np.ndarray | None = None) -> np.ndarray:
    """``tables`` (from :func:`wavetables`) read at ``phase`` (in cycles, any real number), linear
    interpolation between samples; with ``row`` (per sample, 0 to ``rows - 1``, fractions allowed)
    also between neighbouring rows."""
    size = tables.shape[1] - 1
    x = (phase - np.floor(phase)) * size
    i = np.minimum(x.astype(np.intp), size - 1)
    x -= i
    if row is None:
        table = tables[0]
        low = table[i]
        return low + (table[i + 1] - low) * x
    k = np.clip(row.astype(np.intp), 0, max(len(tables) - 2, 0))
    flat = tables.ravel()
    i += k * (size + 1)
    low = flat[i]
    low += (flat[i + 1] - low) * x
    if len(tables) == 1:
        return low
    i += size + 1
    high = flat[i]
    high += (flat[i + 1] - high) * x
    high -= low
    high *= row - k
    return low + high


def phase_cycles(freq: np.ndarray | float, n: int, start: float = 0.0) -> np.ndarray:
    """The phase in cycles of a tone of ``freq`` Hz (constant or per sample) over ``n`` samples,
    from ``start``."""
    if np.ndim(freq) == 0:
        return start + np.arange(n) * (float(freq) / RATE)
    return start + np.cumsum(freq) / RATE


def raised_cosine(n: int, length: int, start: int = 0) -> np.ndarray:
    """0 before sample ``start``, a raised-cosine rise over ``length`` samples, then 1."""
    u = np.clip((np.arange(n) - start) / max(length, 1), 0.0, 1.0)
    return 0.5 - 0.5 * np.cos(np.pi * u)


def band_noise(rng: np.random.Generator, n: int, center: float, width: float, lowpass: float = HIGHEST_PARTIAL) -> np.ndarray:
    """``n`` samples of noise in a band ``width`` octaves (sigma) around ``center`` Hz, nothing
    much above ``lowpass``; RMS 1."""
    noise = _filtered(rng.standard_normal(n), lambda f: _band(f, center, width) * _lowpass(f, lowpass, 4))
    return noise / max(float(np.sqrt(np.mean(noise**2))), 1e-12)
