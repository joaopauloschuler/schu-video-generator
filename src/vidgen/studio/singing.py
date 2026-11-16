"""Syllables, a soloist and a whispered tone for the choir (DESIGN.md §121.4). Still synthesis:
the voices sing no words.

- **A syllable** is a short consonant into a vowel (``la``, ``na``, ``ma``, ``da``, ``loo`` ...)
  or two vowels, the second taking over at ``turn`` (``ah-oh``, ``oo-ah``, ``mm-ah``). The
  mouth is a line of shapes in time (*keys*): each key a set of formants (and for ``m`` and
  ``n`` the nose's antiformant), each sample a cross-fade of its two neighbouring keys' wave
  tables, so the formants move from the consonant into the vowel in steps of under 10 ms.
  ``l``: a lateral (low first, low second formant) for 50 ms; ``m`` and ``n``: the nasal
  murmur (a low nasal formant, an antiformant near 1 kHz or 1.8 kHz, little above) for 60-70
  ms; ``d``: a closure with only a voice bar, then a burst of noise and the formants moving
  from the alveolar locus (second formant near 1.7 kHz).
- **A soloist** is one voice, louder in its upper harmonics (the singer's formant near 3 kHz
  that lets a soloist carry over a choir), with a wider vibrato that comes later, a scoop up
  into each note and more breath.
- **Whisper** moves the voice from tone to breath: at 1 only noise through the vowel's
  formants is left, as loud as the voice was.

A note that uses none of this (``syllable: vowel``, ``soloist: false``, ``whisper: 0``) is
made by :func:`vidgen.studio.choir.held_vowels`, the code of Step 345, sample for sample.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio.additive import (
    Phrase,
    band_noise,
    harmonic_count,
    levelled,
    loudness,
    phase_cycles,
    phrase_pitch,
    phrase_tone,
    raised_cosine,
    read_tables,
    remembered,
    seeded,
    smoothed,
    wavetables,
)
from vidgen.studio.choir import _BREATH, _FULL, _PITCH_ROWS, _SOFT, MORPHS, VOICES, VOWELS, _cents, formants, held_vowels, section

#: How the vowels are spelt inside a syllable.
_SPELT = {"a": "aah", "ah": "aah", "o": "oh", "oh": "oh", "oo": "ooh", "e": "eeh", "eh": "eeh", "ee": "ee", "mm": "mm"}
#: The ``syllable`` setting's names, in the order of its numbers: ``vowel`` (the ``vowel``
#: setting held, as before), a consonant and a vowel, two vowels.
SYLLABLES: tuple[str, ...] = (
    ("vowel",)
    + tuple(onset + vowel for onset in "lnmd" for vowel in ("a", "o", "oo", "e", "ee"))
    + ("mm-ah", "mm-oh", "mm-oo", "ah-oh", "oo-ah", "oh-ah", "ah-ee")
)


@dataclass(frozen=True)
class Consonant:
    """A consonant at the start of a syllable, for a bass (other voices scale its formants).
    ``hold``: seconds of the consonant itself; ``move``: seconds its formants take to reach the
    vowel's; ``level``: its amplitude against the vowel's; ``formants``: ``(Hz, bandwidth)`` of
    the first three formants during the hold (the fourth and fifth are the vowel's, broader);
    ``locus``: the first three formants where the move begins; ``zero``: the antiformant
    ``(Hz, bandwidth)`` of a nasal; ``damp``: a low-pass corner (Hz) during the hold (a closed
    mouth lets little but the lowest harmonics out); ``burst``: the level of the noise burst
    as it opens (a stop)."""

    hold: float
    move: float
    level: float
    formants: tuple[tuple[float, float], ...]
    locus: tuple[float, float, float]
    zero: tuple[float, float] | None = None
    damp: float = 0.0
    burst: float = 0.0


#: The consonants (figures from the phonetics literature for adult male speech; held a little
#: longer, as singers do).
CONSONANTS: dict[str, Consonant] = {
    "l": Consonant(0.05, 0.06, 0.5, ((330, 70), (1150, 140), (2650, 200)), (330, 1200, 2650)),
    "m": Consonant(0.07, 0.045, 0.35, ((270, 80), (1350, 300), (2250, 350)), (300, 1000, 2300), (950, 160), 1000.0),
    "n": Consonant(0.06, 0.045, 0.35, ((270, 80), (1250, 300), (2450, 350)), (300, 1700, 2600), (1800, 220), 1300.0),
    "d": Consonant(0.035, 0.04, 0.07, ((200, 60), (1200, 400), (2500, 500)), (250, 1700, 2650), None, 350.0, 0.1),
}
#: A consonant's formants per kind of voice against a bass's (shorter throats, higher formants).
_SCALE = {"basses": 1.0, "tenors": 1.06, "altos": 1.14, "sopranos": 1.2}
#: A d's burst: where it lies (Hz, for a bass), how wide it is (octaves), the corner above which
#: little of it is left (Hz, for a bass), and the seconds it takes to rise and to decay.
_BURST_HZ, _BURST_WIDTH, _BURST_TOP = 2400.0, 0.25, 3400.0
_BURST_RISE, _BURST_DECAY = 0.0015, 0.003
#: Seconds two vowels take to glide into each other (at most 40 % of the note), and the steps of a move.
_VOWEL_GLIDE, _STEPS = 0.15, 6
#: A stop opens: seconds from its closure to the voice's level after the burst (``_OPENED``).
_OPEN, _OPENED = 0.002, 0.45
#: A consonant inside a slur: seconds the vowel before takes to close into it.
_CLOSE = 0.025
#: Seconds over which a note that starts with a consonant enters (the ``attack`` then shapes nothing).
_ENTRY = 0.012
#: The singers of a section are this much closer together on a consonant than on a vowel.
_TOGETHER = 0.4
#: The soloist: the singer's formant per kind of voice (Hz, bandwidth, dB at its peak), how much
#: brighter, wider and later its vibrato is, its scoop (cents under the note, seconds to rise)
#: and its breath.
_RING = {"basses": (2700.0, 500.0, 9.0), "tenors": (2900.0, 500.0, 9.0), "altos": (3100.0, 550.0, 6.0), "sopranos": (3300.0, 600.0, 6.0)}
_SOLO_BRIGHTER, _SOLO_WIDER, _SOLO_LATER, _SOLO_GROW = 0.15, 1.7, 1.6, 0.6
_SOLO_SCOOP, _SOLO_SCOOP_TIME, _SOLO_BREATH = (35.0, 55.0), 0.08, 1.6
#: A whisper's noise against the voice it replaces (amplitude at ``whisper: 1``).
_WHISPER = 0.8
#: The short-time Fourier transform that shapes the noise: hop and frame in samples.
_HOP, _FRAME = 256, 1024


def read_yes_no(value: Any, where: str) -> float:
    """A yes-or-no setting as the number the score keeps: ``true`` / ``false`` (YAML), ``yes`` /
    ``no``, ``on`` / ``off``, 1 / 0."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)) and value in (0, 1):
        return float(value)
    words = {"true": 1.0, "yes": 1.0, "on": 1.0, "false": 0.0, "no": 0.0, "off": 0.0}
    if isinstance(value, str) and value.lower() in words:
        return words[value.lower()]
    raise VidgenError(f"{where}: expected true or false, got {value!r}")


def syllable_parts(name: str) -> tuple[str, tuple[str, ...]]:
    """A syllable's consonant (``""``: none) and vowels: ``la`` → ``("l", ("aah",))``,
    ``mm-ah`` → ``("", ("mm", "aah"))``."""
    if "-" in name:
        return "", tuple(_SPELT[part] for part in name.split("-"))
    return name[0], (_SPELT[name[1:]],)


# ----- the mouth: shapes and keys ------------------------------------------------------------------


@dataclass(frozen=True)
class Shape:
    """The mouth at a moment: five formants (Hz, bandwidths in Hz), an antiformant ``zero``
    (Hz, bandwidth) as deep as ``zero_depth`` (0 none, 1 all of it) and a low-pass corner
    ``damp`` as strong as ``damp_depth``."""

    hz: np.ndarray
    width: np.ndarray
    zero: tuple[float, float] = (1000.0, 200.0)
    zero_depth: float = 0.0
    damp: float = 1000.0
    damp_depth: float = 0.0

    def response(self, freqs: np.ndarray) -> np.ndarray:
        """Its gain at ``freqs`` (Hz): the five resonances one after another, the antiformant and
        the low-pass."""
        gain = np.ones_like(freqs)
        for center, band in zip(self.hz, self.width):
            gain = gain * center**2 / np.sqrt((center**2 - freqs**2) ** 2 + (band * freqs) ** 2)
        if self.zero_depth:
            center, band = self.zero
            gain *= 1 - self.zero_depth + self.zero_depth * np.sqrt((center**2 - freqs**2) ** 2 + (band * freqs) ** 2) / center**2
        if self.damp_depth:
            gain *= 1 - self.damp_depth + self.damp_depth / (1 + (freqs / self.damp) ** 2)
        return gain


def _opened(hz: np.ndarray, width: np.ndarray, freq: float) -> tuple[np.ndarray, np.ndarray]:
    """As :func:`~vidgen.studio.choir.formants`: a note above the first formant takes it along."""
    if freq > hz[0]:
        width[0] *= freq / hz[0]
        hz[0] = freq
    hz[1] = max(hz[1], 1.33 * hz[0])
    return hz, width


def _shape(desc: tuple[str, ...], kind: str, freq: float, throat: float) -> Shape:
    """The shape a key's description names, for one singer: ``("v", vowel)`` the vowel, ``("h",
    consonant, vowel)`` the consonant held before that vowel, ``("r", consonant, vowel)`` the
    formants where its move into the vowel begins."""
    hz, width = formants(kind, desc[-1], freq, throat)
    vowel = Shape(hz, width, damp=700.0, damp_depth=1.0 if desc[-1] == "mm" else 0.0)
    if desc[0] == "v":
        return vowel
    c = CONSONANTS[desc[1]]
    scale = _SCALE[kind] * throat
    if desc[0] == "h":
        hz = np.array([f * scale for f, _ in c.formants] + list(vowel.hz[3:]))
        width = np.array([b * scale for _, b in c.formants] + list(2 * vowel.width[3:]))
        hz, width = _opened(hz, width, freq)
        zero = (c.zero[0] * scale, c.zero[1] * scale) if c.zero else (1000.0, 200.0)
        return Shape(hz, width, zero, 1.0 if c.zero else 0.0, c.damp * scale if c.damp else 1000.0, 1.0 if c.damp else 0.0)
    hz = np.array([f * scale for f in c.locus] + list(vowel.hz[3:]))
    hz, width = _opened(hz, vowel.width.copy(), freq)
    return Shape(hz, width)


def _between(a: Shape, b: Shape, u: float) -> Shape:
    """The shape ``u`` of the way from ``a`` to ``b`` (formants move in a straight line in Hz)."""
    return Shape(
        a.hz + (b.hz - a.hz) * u,
        a.width + (b.width - a.width) * u,
        a.zero if a.zero_depth else b.zero,
        a.zero_depth + (b.zero_depth - a.zero_depth) * u,
        a.damp if a.damp_depth and not b.damp_depth else b.damp if not a.damp_depth else a.damp + (b.damp - a.damp) * u,
        a.damp_depth + (b.damp_depth - a.damp_depth) * u,
    )


#: A key of the mouth's line: its sample, what it is (one description, or two and the share
#: of the way from the first to the second) and the voice's level there.
Key = tuple[int, tuple[Any, ...], float]


def _recipe(a: tuple[str, ...], b: tuple[str, ...], u: float) -> tuple[Any, ...]:
    return (a,) if u <= 0 else (b,) if u >= 1 else (a, b, round(u, 6))


def _last(recipe: tuple[Any, ...]) -> tuple[str, ...]:
    """The description a key's recipe ends on (where the mouth is going)."""
    return recipe[0] if len(recipe) == 1 else recipe[1]


def _resolve(recipe: tuple[Any, ...], kind: str, freq: float, throat: float) -> Shape:
    if len(recipe) == 1:
        return _shape(recipe[0], kind, freq, throat)
    return _between(_shape(recipe[0], kind, freq, throat), _shape(recipe[1], kind, freq, throat), recipe[2])


def _move(keys: list[Key], start: float, length: float, a: tuple[str, ...], b: tuple[str, ...], level_from: float, level_to: float) -> None:
    """Keys for the mouth moving from ``a`` to ``b`` over ``length`` samples from ``start``
    (a raised cosine, in :data:`_STEPS` steps), the level going along."""
    for i in range(_STEPS + 1):
        u = 0.5 - 0.5 * math.cos(math.pi * i / _STEPS)
        keys.append((int(round(start + i * length / _STEPS)), _recipe(a, b, u), level_from + (level_to - level_from) * u))


def mouth(n: int, held: int, s: Mapping[str, float], phrase: Phrase = (), offset: int = 0) -> list[Key]:
    """The mouth's keys over a note of ``n`` samples (``held`` of them before its release) for
    a singer who starts ``offset`` samples late: the syllable of the note (``syllable``, else
    ``vowel``; ``morph`` when there is no syllable), and for each slurred note of ``phrase``
    that names its own syllable or vowel the way to it (a consonant there only when written)."""
    segments = [(offset, int(s.get("syllable", 0.0)), VOWELS[int(s["vowel"])])]
    for start, _, _, *named in phrase:
        if named:
            segments.append((start + offset, int(named[0][0]), VOWELS[int(named[0][1])]))
    keys: list[Key] = []
    for k, (start, syllable, vowel) in enumerate(segments):
        end = segments[k + 1][0] if k + 1 < len(segments) else max(held, start + 1)
        length = end - start
        onset, vowels = ("", (vowel,)) if syllable == 0 else syllable_parts(SYLLABLES[syllable])
        before = _last(keys[-1][1]) if keys else None
        target = ("v", vowels[0])
        if onset:
            c = CONSONANTS[onset]
            hold, held_shape, release = c.hold * RATE, ("h", onset, vowels[0]), ("r", onset, vowels[0])
            if before is not None:
                keys.append((int(start - _CLOSE * RATE), (before,), 1.0))
            keys.append((start, (held_shape,), c.level))
            keys.append((int(start + hold), (held_shape,), c.level))
            _move(keys, start + hold + _OPEN * RATE, c.move * RATE, release, target, _OPENED if c.burst else c.level, 1.0)
        elif before is None:
            keys.append((start, (target,), 1.0))
        elif before != target:
            glide = min(_VOWEL_GLIDE * RATE, 0.4 * length)
            _move(keys, start - glide / 2, glide, before, target, 1.0, 1.0)
        if len(vowels) == 2:
            glide = min(_VOWEL_GLIDE * RATE, 0.4 * length)
            _move(keys, start + s.get("turn", 0.5) * length - glide / 2, glide, target, ("v", vowels[1]), 1.0, 1.0)
        elif k == 0 and syllable == 0 and len(segments) == 1 and int(s["morph"]):
            _move(keys, 0.15 * held, 0.7 * held, target, ("v", MORPHS[int(s["morph"])]), 1.0, 1.0)
    out: list[Key] = []
    for at, recipe, level in keys:
        at = min(max(at, 0), max(n - 1, 0))
        if out and at <= out[-1][0]:
            if at < out[-1][0] or recipe == out[-1][1]:
                continue
            out.pop()
        out.append((at, recipe, level))
    return out


def bursts(keys: list[Key]) -> list[int]:
    """The samples where a stop's burst sounds: where a consonant with a burst opens."""
    return [at for (at, recipe, _), (_, after, _) in zip(keys, keys[1:]) if recipe[0][0] == "h" and CONSONANTS[recipe[0][1]].burst and after[0][0] == "r"]


def _shares(times: np.ndarray, k: int, at: np.ndarray) -> np.ndarray:
    """Key ``k``'s share of the mouth at the samples ``at`` (straight lines between keys; the
    first key alone before it, the last alone after it)."""
    fp = np.zeros(len(times))
    fp[k] = 1.0
    return np.interp(at, times, fp)


# ----- one singer ------------------------------------------------------------------------------------


def _harmonics(shape: Shape, freq: float, brightness: float, cents: float, ring: tuple[float, float, float] | None) -> np.ndarray:
    """As :func:`~vidgen.studio.choir.spectrum` for a mouth of any shape; ``ring``: the
    soloist's singer's formant (Hz, bandwidth, dB at its peak)."""
    number = np.arange(1, harmonic_count(freq * 1.05) + 1, dtype=float)
    freqs = freq * 2 ** (cents / 1200) * number
    gain = number ** -(_SOFT + (_FULL - _SOFT) * float(np.clip(brightness, 0.0, 1.0))) * shape.response(freqs)
    if ring is not None:
        center, band, db = ring
        gain *= 1 + (10 ** (db / 20) - 1) / np.sqrt(1 + ((freqs**2 - center**2) / (band * freqs)) ** 2)
    return gain * np.clip((16000.0 - freq * 1.05 * number) / 2000.0, 0.0, 1.0)


def _solo_cents(n: int, s: Mapping[str, float], rng: np.random.Generator, offset: int) -> np.ndarray:
    """A soloist's pitch in cents: a scoop up into the note, a slow wander, and a vibrato wider
    and later than a choir singer's, its depth breathing a little."""
    t = (np.arange(n) - offset) / RATE
    cents = -rng.uniform(*_SOLO_SCOOP) * np.where(t >= 0, np.exp(-np.maximum(t, 0.0) / _SOLO_SCOOP_TIME), 0.0)
    for depth in (3.0, 2.0, 1.2):
        cents += depth * np.sin(2 * np.pi * (rng.uniform(0.3, 2.6) * t + rng.uniform()))
    if s["vibrato"] > 0:
        depth = _SOLO_WIDER * s["vibrato"] * (1 + 0.12 * np.sin(2 * np.pi * (rng.uniform(0.25, 0.45) * t + rng.uniform())))
        delay = _SOLO_LATER * s["vibrato_delay"]
        cents += depth * np.clip((t - delay) / _SOLO_GROW, 0.0, 1.0) * np.sin(2 * np.pi * (s["vibrato_speed"] * t + rng.uniform()))
    return cents


def _singer(kind: str, freq: float, n: int, held: int, s: Mapping[str, float], offset: int, alone: bool, solo: bool, rng: np.random.Generator,
            phrase: Phrase) -> tuple[np.ndarray, np.ndarray]:
    """One singer's note (as :func:`~vidgen.studio.choir._singer`) singing the mouth's keys: the
    voiced tone and, apart from it, the bursts of its stops (which a whisper keeps)."""
    throat = 1.0 if alone else rng.uniform(0.96, 1.04)
    keys = mouth(n, held, s, phrase, offset)
    entry = _ENTRY if keys[0][1][0][0] == "h" else s["attack"] * (1.0 if alone else rng.uniform(0.8, 1.3))
    times = np.array([at for at, _, _ in keys], dtype=float)
    level = raised_cosine(n, int(entry * RATE), offset) * (1 - raised_cosine(n, n - held, held))
    level *= 1 + 0.06 * np.sin(2 * np.pi * (rng.uniform(0.2, 0.9) * np.arange(n) / RATE + rng.uniform()))
    level *= np.interp(np.arange(n), times, [lv for _, _, lv in keys])
    cents = _solo_cents(n, s, rng, offset) if solo else _cents(n, s, rng, offset, alone)
    span = float(np.abs(cents).max()) + 1.0
    offsets = np.linspace(-span, span, _PITCH_ROWS)
    turns = freq * 2 ** (cents / 1200) if not phrase else freq * 2 ** (cents / 1200 + phrase_pitch(n, phrase, offset) / 12)
    phase = phase_cycles(turns, n, rng.uniform())
    row = (cents + span) * ((_PITCH_ROWS - 1) / (2 * span))
    brightness = s["brightness"] + (_SOLO_BRIGHTER if solo else 0.0)
    ring = _RING[kind] if solo else None
    made: dict[tuple[Any, ...], tuple[np.ndarray, float, bool]] = {}

    def tables(recipe: tuple[Any, ...], hz: float) -> tuple[np.ndarray, float, bool]:
        """A key's wave tables at ``hz``: across the singer's pitch swing for a held vowel, one
        row for the short shapes of a consonant or a glide."""
        if (recipe, hz) not in made:
            shape = _resolve(recipe, kind, hz, throat)
            steady = len(recipe) == 1 and recipe[0][0] == "v"
            spectra = np.stack([_harmonics(shape, hz, brightness, float(c), ring) for c in (offsets if steady else [0.0])])
            made[recipe, hz] = (wavetables(spectra), loudness(spectra[len(spectra) // 2], hz), steady)
        return made[recipe, hz]

    def voiced(semitones: float, first: int, last: int) -> np.ndarray:
        hz = freq * 2 ** (semitones / 12) if semitones else freq
        out = np.zeros(last - first)
        for k, (_, recipe, _) in enumerate(keys):
            lo = max(first, int(times[k - 1]) if k else first)
            hi = min(last, int(times[k + 1]) + 1 if k + 1 < len(keys) else last)
            if hi <= lo:
                continue
            table, norm, steady = tables(recipe, hz)
            share = _shares(times, k, np.arange(lo, hi, dtype=float))
            out[lo - first : hi - first] += share * read_tables(table, phase[lo:hi], row[lo:hi] if steady else None) / norm
        return out

    tone = voiced(0.0, 0, n) if not phrase else phrase_tone(n, phrase, offset, voiced)
    burst = np.zeros(n)
    for at in bursts(keys):
        size = min(int(0.02 * RATE), n - at)
        if size > 8:
            scale = _SCALE[kind] * throat
            noise = band_noise(rng, size, _BURST_HZ * scale, _BURST_WIDTH, _BURST_TOP * scale)
            burst[at : at + size] += CONSONANTS["d"].burst * noise * np.exp(-np.arange(size) / (_BURST_DECAY * RATE)) * raised_cosine(size, int(_BURST_RISE * RATE))
    return tone * level, burst


# ----- breath and whisper ----------------------------------------------------------------------------


def _shaped_noise(rng: np.random.Generator, n: int, gains: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """``n`` samples of white noise (RMS 1) through a filter that changes in time: ``gains(at)``
    gives its response ``(len(at), bins of a 1024-sample frame)`` around the samples ``at``
    (short-time Fourier transform: Hann frames at a hop of 256)."""
    frames = (n + _FRAME) // _HOP + 2
    noise = rng.standard_normal((frames - 1) * _HOP + _FRAME)
    window = np.hanning(_FRAME + 1)[:-1]
    spectra = np.fft.rfft(noise[np.arange(_FRAME)[None, :] + _HOP * np.arange(frames)[:, None]] * window, axis=1)
    centres = _HOP * np.arange(frames) - _FRAME / 2  # each frame's middle, in output samples
    parts = np.fft.irfft(spectra * gains(centres), _FRAME, axis=1) * window
    out = np.zeros((frames + _FRAME // _HOP) * _HOP)
    for r in range(_FRAME // _HOP):
        out[r * _HOP : r * _HOP + frames * _HOP] += parts[:, r * _HOP : (r + 1) * _HOP].reshape(-1)
    return out[_FRAME : _FRAME + n] / 1.5  # Hann frames at a quarter's hop add up to 1.5


def _air(kind: str, freq: float, n: int, held: int, s: Mapping[str, float], phrase: Phrase, power: np.ndarray, breath: float, whisper: float,
         rng: np.random.Generator) -> np.ndarray:
    """The air in the voices: breath (as :func:`~vidgen.studio.choir._breath`: the formants
    three times as broad, little under 900 Hz, more as a note begins, less through closed
    lips) and the whisper (the formants half as broad again, from 250 Hz up), both through the
    mouth's keys, following the singers' level (``power``, per sample)."""
    keys = mouth(n, held, s, phrase)
    times = np.array([at for at, _, _ in keys], dtype=float)
    f = np.maximum(np.fft.rfftfreq(_FRAME, 1 / RATE), 1.0)
    airy, hushed = [], []
    for _, recipe, _ in keys:
        shape = _resolve(recipe, kind, freq, 1.0)
        hummed = 0.3 if shape.damp_depth > 0.5 else 1.0
        a = replace(shape, width=3 * shape.width, zero_depth=0.0, damp_depth=0.0).response(f) / np.sqrt(1 + (900.0 / f) ** 4) / np.sqrt(1 + (f / 9000.0) ** 4)
        w = replace(shape, width=1.5 * shape.width).response(f) / np.sqrt(1 + (250.0 / f) ** 4) / np.sqrt(1 + (f / 10000.0) ** 4)
        airy.append(hummed * breath * _BREATH * a / max(float(np.sqrt(np.mean(a**2))), 1e-30))
        hushed.append(whisper * _WHISPER * w / max(float(np.sqrt(np.mean(w**2))), 1e-30))

    def gains(at: np.ndarray) -> np.ndarray:
        shares = np.stack([_shares(times, k, at) for k in range(len(keys))], axis=1)
        return (1 + 1.5 * np.exp(-np.maximum(at, 0.0) / (0.15 * RATE)))[:, None] * (shares @ np.array(airy)) + shares @ np.array(hushed)

    return _shaped_noise(rng, n, gains) * np.sqrt(np.maximum(power, 0.0)) * raised_cosine(n, int(0.005 * RATE))


# ----- the note ---------------------------------------------------------------------------------------


def is_plain(s: Mapping[str, float], phrase: Phrase = ()) -> bool:
    """Whether a choir note uses none of this module (it is then Step 345's)."""
    return not (s.get("syllable", 0.0) or s.get("soloist", 0.0) or s.get("whisper", 0.0) or any(len(note) > 3 for note in phrase))


def sung_note(freq: float, n: int, s: Mapping[str, float], seed: str, phrase: Phrase = ()) -> np.ndarray:
    """A choir note with syllables, a soloist or a whisper (as
    :func:`~vidgen.studio.choir.held_vowels`: stereo for a section, mono for one voice)."""
    held = max(n - max(int(s["ring"] * RATE), 1), 0)
    solo = bool(s.get("soloist", 0.0))
    singers = 1 if solo else int(round(s["singers"]))
    rng = seeded("choir", seed, round(freq, 3))
    kinds = section(VOICES[int(s["voices"])], 69 + 12 * math.log2(freq / 440.0), singers)
    spread = np.linspace(-1.0, 1.0, singers) if singers > 1 else np.zeros(1)
    tuned = freq * 2 ** ((rng.permutation(spread) * s["detune"] + rng.uniform(-2.0, 2.0, singers)) / 1200)
    consonant = bool(syllable_parts(SYLLABLES[int(s.get("syllable", 0.0))])[0]) if s.get("syllable", 0.0) else False
    together = _TOGETHER if consonant else 1.0
    late = np.zeros(1, dtype=np.intp) if singers == 1 else (rng.uniform(0.0, min(0.07, 0.4 * s["attack"]) * together, singers) * RATE).astype(np.intp)
    late -= late.min()
    whisper = float(s.get("whisper", 0.0))
    voiced = math.cos(0.5 * math.pi * whisper)
    breath = s["breath"] * (_SOLO_BREATH if solo else 1.0)
    hushed = math.sin(0.5 * math.pi * whisper)
    if singers == 1:
        mono, burst = _singer(kinds[0], float(tuned[0]), n, held, s, 0, True, solo, rng, phrase)
        power = smoothed(mono**2, int(RATE / freq) + 1)
        return mono * voiced + burst + _air(kinds[0], freq, n, held, s, phrase, power, breath, hushed, rng)
    out, pops = np.zeros((n, 2)), np.zeros((n, 2))
    sides_power = np.zeros((n, 2))
    places = rng.permutation(spread)
    for k in range(singers):
        mono, burst = _singer(kinds[k], float(tuned[k]), n, held, s, int(late[k]), False, False, rng, phrase)
        angle = (0.8 * places[k] + 1) * math.pi / 4
        sides = math.sqrt(2 / singers) * np.array([math.cos(angle), math.sin(angle)])
        out += mono[:, None] * sides
        pops += burst[:, None] * sides
        sides_power += (mono**2)[:, None] * sides**2
    for side in range(2):
        out[:, side : side + 1] = levelled(out[:, side : side + 1], 0.5 * sides_power[:, side], freq)
    power = smoothed(0.5 * sides_power.sum(axis=1), int(RATE / freq) + 1)
    air = np.stack([_air(kinds[0], freq, n, held, s, phrase, power, breath, hushed, rng) for _ in range(2)], axis=1)
    return out * voiced + pops + air


@remembered
def choir_note(freq: float, n: int, s: Mapping[str, float], seed: str, phrase: Phrase = ()) -> np.ndarray:
    """A choir note of ``n`` samples (its last ``ring`` seconds are the release): held vowels
    as in Step 345 (:func:`~vidgen.studio.choir.held_vowels`, sample for sample) unless the
    settings ask for a syllable, a soloist or a whisper, or a slurred note names its own
    syllable or vowel. The same ``seed``, pitch, length, settings and phrase give the same
    samples."""
    if is_plain(s, phrase):
        return held_vowels(freq, n, s, seed, phrase)
    return sung_note(freq, n, s, seed, phrase)
