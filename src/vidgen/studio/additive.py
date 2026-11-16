"""Additive synthesis for the orchestral score instruments (DESIGN.md §120.4): a note's harmonics
summed once into one-period wave tables, which are then read along the note's phase. A note
with a hundred harmonics costs the same per sample as one with three, and a spectrum that changes
over the note (brass getting brighter as it gets louder) is a cross-fade between a few tables."""

from __future__ import annotations

import math
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

#: The further notes of a slurred phrase (DESIGN.md §120.7): per note its start in samples from
#: the phrase's start, its pitch in semitones above the first note and its glide in samples.
Phrase = tuple[tuple[int, float, int], ...]
#: Seconds over which one note's wave tables give way to the next's in a slurred phrase.
_JOIN = 0.03
#: The share of a glide that lies before the new note's step (the rest after it).
_GLIDE_EARLY = 0.7

NoteMaker = Callable[..., np.ndarray]


def remembered(make: NoteMaker) -> NoteMaker:
    """``make`` (``(Hz, samples, settings, seed) -> note``; one that can slur also takes a
    :data:`Phrase`) remembering its last short notes: an ostinato repeats a few notes hundreds
    of times. The notes it returns are read-only."""

    @lru_cache(maxsize=48)
    def kept(freq: float, n: int, settings: tuple[tuple[str, float], ...], seed: str, phrase: Phrase) -> np.ndarray:
        note = make(freq, n, dict(settings), seed, phrase) if phrase else make(freq, n, dict(settings), seed)
        note.setflags(write=False)
        return note

    def note(freq: float, n: int, s: Mapping[str, float], seed: str, phrase: Phrase = ()) -> np.ndarray:
        if n > _REMEMBERED_SAMPLES:
            return make(freq, n, s, seed, phrase) if phrase else make(freq, n, s, seed)
        return kept(freq, n, tuple(sorted(s.items())), seed, phrase)

    return note


def _glides(n: int, phrase: Phrase, offset: int) -> list[tuple[int, int, float, float]]:
    """The glides of a slurred phrase of ``n`` samples whose player starts ``offset`` samples
    late: per further note the first and last sample of its glide and the pitches (semitones
    above the first note) it leaves and reaches. A glide begins before its note's step and
    never before the glide before it is over."""
    join = int(_JOIN * RATE)
    out: list[tuple[int, int, float, float]] = []
    earliest, before = join, 0.0
    for start, semitones, glide in phrase:
        first = min(max(start + offset - int(_GLIDE_EARLY * glide), earliest), max(n - 1, 0))
        last = min(first + max(glide, 1), n)
        out.append((first, last, before, semitones))
        earliest, before = last + 2 * join, semitones
    return out


def phrase_pitch(n: int, phrase: Phrase, offset: int = 0) -> np.ndarray:
    """The pitch of a slurred phrase over its ``n`` samples, in semitones above its first note:
    level on each note, a raised-cosine glide to each further one."""
    pitch = np.zeros(n)
    for first, last, before, after in _glides(n, phrase, offset):
        pitch[first:last] = before + (after - before) * raised_cosine(last - first, last - first)
        pitch[last:] = after
    return pitch


def phrase_tone(n: int, phrase: Phrase, offset: int, tone: Callable[[float, int, int], np.ndarray]) -> np.ndarray:
    """A slurred phrase's tone: ``tone(semitones, first, last)`` is the tone of the note that
    many semitones above the first over the samples ``first`` to ``last`` (every note read
    along the same phase, so two of them add harmonic by harmonic). Each note's tone gives way
    to the next's over 30 ms: before a glide upwards and after a glide downwards, so the
    higher note's wave tables (which hold fewer harmonics) sound while the pitch moves and
    nothing is read above the pitch it was made for."""
    join = int(_JOIN * RATE)
    windows = [(max(first - join, 0), first) if after > before else (last, min(last + join, n)) for first, last, before, after in _glides(n, phrase, offset)]
    out = np.zeros(n)
    for k, semitones in enumerate([0.0] + [note[1] for note in phrase]):
        first = windows[k - 1][0] if k else 0
        last = windows[k][1] if k < len(windows) else n
        if last <= first:
            continue
        weight = np.ones(last - first)
        if k:
            size = windows[k - 1][1] - first
            weight[:size] = raised_cosine(size, size)
        if k < len(windows):
            size = last - windows[k][0]
            weight[len(weight) - size :] *= 1 - raised_cosine(size, size)
        out[first:last] += weight * tone(semitones, first, last)
    return out


def seeded(*parts: object) -> np.random.Generator:
    """A random generator that depends on ``parts`` only (their text, CRC-32)."""
    return np.random.default_rng(zlib.crc32(":".join(str(p) for p in parts).encode("utf-8")))


def harmonic_count(freq: float, limit: float = HIGHEST_PARTIAL) -> int:
    """How many harmonics of ``freq`` lie at or under ``limit`` Hz (at least 1)."""
    return max(int(limit / freq), 1)


def wavetables(amplitudes: np.ndarray, phases: np.ndarray | None = None) -> np.ndarray:
    """One period of ``sum(a[h] * sin(2 pi (h + 1) x))`` per row of ``amplitudes`` ``(rows,
    harmonics)``: float64 ``(rows, size + 1)``, the first sample repeated at the end (for
    :func:`read_tables`). With ``phases`` (per harmonic, in cycles) harmonic ``h`` is
    ``sin(2 pi ((h + 1) x + phases[h]))`` in every row."""
    rows, count = amplitudes.shape
    size = max(2048, 1 << (count * _SAMPLES_PER_CYCLE - 1).bit_length())
    spectrum = np.zeros((rows, size // 2 + 1), dtype=np.complex128)
    spectrum[:, 1 : count + 1] = -0.5j * size * amplitudes
    if phases is not None:
        spectrum[:, 1 : count + 1] *= np.exp(2j * np.pi * phases)
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


def smoothed(power: np.ndarray, length: int) -> np.ndarray:
    """``power`` averaged twice over ``length`` samples around each sample (a triangle window)."""
    for _ in range(2):
        total = np.concatenate([[0.0], np.cumsum(power)])
        at = np.arange(len(power))
        power = (total[np.minimum(at + length // 2 + 1, len(power))] - total[np.maximum(at - length // 2, 0)]) / length
    return power


def levelled(section: np.ndarray, players_power: np.ndarray, freq: float) -> np.ndarray:
    """``section`` (stereo, the players summed) with its slow level changes taken out. Players a
    few cents apart drift in and out of step, so their sum is, for a second at a time and by
    chance, up to 6 dB louder or far quieter than the players are together: one note of a line
    would be weak, the next strong. The gain here (at most 8 dB either way) brings the sum's power,
    averaged over whole periods of the note (50 ms or more), to the sum of the players' powers
    (``players_power``, per sample); the tone still moves as harmonics come and go."""
    period = RATE / freq
    length = max(int(round(period * math.ceil(0.05 * RATE / period))), 1)
    wanted = smoothed(players_power, length)
    measured = smoothed(0.5 * np.sum(section**2, axis=1), length)
    floor = 1e-9 * max(float(wanted.max()), 1e-30)
    return section * np.clip(np.sqrt((wanted + floor) / (measured + floor)), 0.4, 2.5)[:, None]


def loudness(amplitudes: np.ndarray, freq: float) -> float:
    """How loud harmonics of ``freq`` Hz with these amplitudes are together: their RMS as the
    ear weighs it (the loudness measure's curve: 4 dB more above about 1.5 kHz, little under
    40 Hz). Notes are set to the same value of this, so a high note with all its energy where
    the ear is keen is not louder than a low one."""
    freqs = freq * np.arange(1, len(amplitudes) + 1)
    weight = 10 ** (0.2 / (1 + (1500.0 / freqs) ** 2)) / (1 + (38.0 / freqs) ** 2)
    return math.sqrt(0.5 * float(np.sum((amplitudes * weight) ** 2))) + 1e-30
