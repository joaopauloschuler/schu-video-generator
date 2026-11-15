"""Brass for score files (DESIGN.md §120.4): a solo trumpet, a horn and a low brass section,
synthesised from the things that make brass sound like brass.

- **The spectrum follows the level.** A brass tube radiates little below its bell's cutoff and,
  above it, the harder it is blown the more harmonics it has. :func:`spectrum` is that curve for
  a brightness ``b``; a note cross-fades between a few of them along ``b(t) = brightness *
  level(t) ** 1.6``, so the upper harmonics arrive after the fundamental in the attack (the
  "blare"), a slow attack is a swell that opens, and the release darkens as it dies.
- **Fixed body resonances** (formants) that do not move with the pitch.
- **The lips**: the pitch starts a little flat and slides up in about 35 ms; a solo voice's
  vibrato begins only after the note has settled; the pitch drifts by a cent or two.
- **A section** is several players: each a few cents off, entering a few milliseconds apart,
  spread from left to right.
- **Breath**: a little band noise, most of it in the attack.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from vidgen.sfx import RATE
from vidgen.studio.additive import band_noise, harmonic_count, phase_cycles, raised_cosine, read_tables, remembered, seeded, wavetables

#: Tables a note cross-fades between, from brightness 0 to its highest.
_LEVELS = 8
#: The exponent of ``level`` in the brightness: above 1, so harmonics lag behind the fundamental.
_BLARE = 1.6
#: Played softly, harmonic ``h`` is weaker by ``h ** -(_SOFT_TILT * (1 - brightness))``.
_SOFT_TILT = 1.2
#: Seconds the pitch scoop takes to come within a third of its start.
_SCOOP_SECONDS = 0.035
#: Vibrato: speed (Hz), seconds before it begins and seconds over which it grows.
VIBRATO_HZ, VIBRATO_DELAY, VIBRATO_GROWS = 5.3, 0.28, 0.45
#: The tuba doubles a note an octave lower down to this (Hz); under it, in unison.
_LOWEST_TUBA = 27.0
#: An attack at or under this many seconds is tongued hard: a short accent at its start.
_TONGUED = 0.12


@dataclass(frozen=True)
class Body:
    """One brass instrument's tube: ``cutoff`` (Hz, where the bell stops reflecting: the top of
    the spectrum's hump), ``formants`` (``(Hz, dB, width in octaves)`` resonances), the roll-off
    above the cutoff in powers of the frequency when played softly (``soft``) and at full
    brightness (``loud``), ``scoop`` (cents the attack starts flat)."""

    cutoff: float
    formants: tuple[tuple[float, float, float], ...]
    soft: float
    loud: float
    scoop: float


#: A B-flat trumpet, a horn in F, a tenor trombone and a tuba.
TRUMPET = Body(1250.0, ((1300.0, 4.0, 0.35), (2600.0, 3.0, 0.3)), 4.2, 1.5, 28.0)
HORN = Body(480.0, ((360.0, 3.0, 0.45), (780.0, 2.0, 0.4), (2100.0, -3.0, 0.5)), 4.6, 1.7, 36.0)
TROMBONE = Body(620.0, ((540.0, 3.0, 0.4), (1400.0, 2.5, 0.4)), 4.2, 1.4, 22.0)
TUBA = Body(300.0, ((230.0, 3.0, 0.5), (480.0, 1.5, 0.4)), 4.6, 2.0, 18.0)


def spectrum(body: Body, freq: float, brightness: float, mute: float = 0.0) -> np.ndarray:
    """The amplitudes of the harmonics of a note of ``freq`` Hz (all under 16 kHz) for
    ``brightness`` 0 (pianissimo: the lips move like a sine, so each harmonic is weaker than the
    one before, and little passes the cutoff) to 1 (fortissimo: every harmonic up to the cutoff
    as strong as the tube lets it be, and a slow roll-off above; over 1 brassier still).
    ``mute`` 0 to 1: a straight mute (the lows thinned, a nasal peak near 2 kHz)."""
    b = float(brightness)
    number = np.arange(1, harmonic_count(freq * 1.03) + 1, dtype=float)
    freqs = freq * number
    power = max(body.soft * (body.loud / body.soft) ** b, 1.0)
    top = body.cutoff * 2 ** (0.5 * (b - 0.5))
    gain = number ** (-_SOFT_TILT * max(1 - b, 0.0)) / np.sqrt(1 + (body.cutoff / freqs) ** 2) / np.sqrt(1 + (freqs / top) ** (2 * power))
    db = np.zeros_like(freqs)
    for center, level, width in body.formants:
        db += level * np.exp(-0.5 * (np.log2(freqs / center) / width) ** 2)
    if mute > 0:
        db += mute * (-10 * np.log10(1 + (1500.0 / freqs) ** 3) + 7 * np.exp(-0.5 * (np.log2(freqs / 2200.0) / 0.35) ** 2) - 3)
    # nothing near the Nyquist frequency: the last harmonics fade out over the top 2 kHz
    fade = np.clip((16000.0 - freqs) / 2000.0, 0.0, 1.0)
    return gain * 10 ** (db / 20) * fade


def _level(n: int, held: int, attack: float, offset: int) -> np.ndarray:
    """A player's loudness over the note, 0 to about 1: silent for ``offset`` samples, a
    raised-cosine rise over ``attack`` seconds (a hard tongued attack overshoots by up to a
    quarter for a tenth of a second), held, then a raised-cosine fall from sample ``held`` to
    the end."""
    rise = raised_cosine(n, int(attack * RATE), offset)
    hardness = float(np.clip(1 - attack / _TONGUED, 0.0, 1.0))
    if hardness > 0:
        rise *= 1 + 0.25 * hardness * np.exp(-np.maximum(np.arange(n) - offset, 0) / (0.09 * RATE))
    return rise * (1 - raised_cosine(n, n - held, held))


def _cents(n: int, body: Body, s: Mapping[str, float], detune: float, rng: np.random.Generator, offset: int) -> np.ndarray:
    """A player's pitch over the note in cents around the written note: the player's ``detune``,
    the scoop into the note, a slow drift of about 2 cents, and the vibrato after its delay."""
    t = (np.arange(n) - offset) / RATE
    cents = detune - body.scoop * np.where(t >= 0, np.exp(-np.maximum(t, 0.0) / _SCOOP_SECONDS), 0.0)
    for depth in (1.4, 0.9):
        cents += depth * np.sin(2 * np.pi * (rng.uniform(0.4, 2.4) * t + rng.uniform()))
    if s["vibrato"] > 0:
        grown = np.clip((t - VIBRATO_DELAY) / VIBRATO_GROWS, 0.0, 1.0)
        cents += s["vibrato"] * grown * np.sin(2 * np.pi * (VIBRATO_HZ * t + rng.uniform()))
    return cents


def _player(body: Body, freq: float, n: int, held: int, s: Mapping[str, float], detune: float, offset: int, start: float, rng: np.random.Generator) -> np.ndarray:
    """One player's note from the point ``start`` of its wave (in cycles): mono, the sustained
    part at RMS 1 whatever the pitch and brightness."""
    level = _level(n, held, s["attack"], offset)
    brightness = s["brightness"] * level**_BLARE
    highest = max(float(brightness.max()), 1e-3)
    levels = np.linspace(0.0, highest, _LEVELS)
    spectra = np.stack([spectrum(body, freq, b, s.get("mute", 0.0)) for b in levels])
    cents = _cents(n, body, s, detune, rng, offset)
    tone = read_tables(wavetables(spectra), phase_cycles(freq * 2 ** (cents / 1200), n, start), brightness * ((_LEVELS - 1) / highest))
    # the held note's spectrum as the tables give it (between two of them), for its RMS
    k = min(int(s["brightness"] / highest * (_LEVELS - 1)), _LEVELS - 2)
    share = s["brightness"] / highest * (_LEVELS - 1) - k
    steady = (1 - share) * spectra[k] + share * spectra[k + 1]
    return tone * level / math.sqrt(0.5 * float(np.sum(steady**2)))


def _breath(body: Body, n: int, held: int, s: Mapping[str, float], rng: np.random.Generator) -> np.ndarray:
    """The air: noise around twice the cutoff, loudest in the first 50 ms."""
    t = np.arange(n) / RATE
    level = _level(n, held, min(s["attack"], 0.05), 0)
    return 0.012 * s["breath"] * band_noise(rng, n, 2 * body.cutoff, 0.9, 9000.0) * level * (0.5 + 2.0 * np.exp(-t / 0.05))


def _smoothed(power: np.ndarray, length: int) -> np.ndarray:
    """``power`` averaged twice over ``length`` samples around each sample (a triangle window)."""
    for _ in range(2):
        total = np.concatenate([[0.0], np.cumsum(power)])
        at = np.arange(len(power))
        power = (total[np.minimum(at + length // 2 + 1, len(power))] - total[np.maximum(at - length // 2, 0)]) / length
    return power


def _levelled(section: np.ndarray, players_power: np.ndarray, freq: float) -> np.ndarray:
    """``section`` (stereo, the players summed) with its slow level changes taken out. Players a
    few cents apart drift in and out of step, so their sum is, for a second at a time and by
    chance, up to 6 dB louder or far quieter than the players are together: one note of a line
    would be weak, the next strong. The gain here (at most 8 dB either way) brings the sum's power,
    averaged over whole periods of the note (50 ms or more), to the sum of the players' powers
    (``players_power``, per sample); the tone still moves as harmonics come and go."""
    period = RATE / freq
    length = max(int(round(period * math.ceil(0.05 * RATE / period))), 1)
    wanted = _smoothed(players_power, length)
    measured = _smoothed(0.5 * np.sum(section**2, axis=1), length)
    floor = 1e-9 * max(float(wanted.max()), 1e-30)
    return section * np.clip(np.sqrt((wanted + floor) / (measured + floor)), 0.4, 2.5)[:, None]


def brass_note(body: Body, freq: float, n: int, s: Mapping[str, float], seed: str, below: Body | None = None) -> np.ndarray:
    """A brass note of ``n`` samples (its last ``ring`` seconds are the release): mono for one
    player, stereo ``(n, 2)`` for a section (``players`` > 1) or when ``below`` doubles it an
    octave lower (the ``tuba`` setting's level). A section's level is evened out
    (:func:`_levelled`). The same ``seed``, pitch, length and settings give the same samples."""
    held = max(n - max(int(s["ring"] * RATE), 1), 0)
    players = int(round(s.get("players", 1.0)))
    rng = seeded("brass", seed, round(freq, 3))
    spread = np.linspace(-1.0, 1.0, players) if players > 1 else np.zeros(1)
    detunes = rng.permutation(spread) * s.get("detune", 0.0) + rng.uniform(-1.5, 1.5, players)
    late = rng.uniform(0.0, 0.028, players) * RATE if players > 1 else np.zeros(1)
    late -= late.min()
    doubled = below is not None and s.get("tuba", 0.0) > 0
    if players == 1 and not doubled:
        return _player(body, freq, n, held, s, float(detunes[0]), 0, 0.0, rng) + _breath(body, n, held, s, rng)
    out = np.zeros((n, 2))
    players_power = np.zeros(n)
    for k in range(players):
        angle = (0.7 * spread[k] + 1) * math.pi / 4
        mono = _player(body, freq, n, held, s, float(detunes[k]), int(late[k]), rng.uniform(), rng) / math.sqrt(players)
        out += mono[:, None] * (math.sqrt(2) * np.array([math.cos(angle), math.sin(angle)]))
        players_power += mono**2
    lowest = freq
    if doubled:
        assert below is not None
        lowest = freq / 2 if freq / 2 >= _LOWEST_TUBA else freq
        mono = s["tuba"] * _player(below, lowest, n, held, s, float(rng.uniform(-2, 2)), int(0.01 * RATE), rng.uniform(), rng)
        out += mono[:, None]
        players_power += mono**2
    out = _levelled(out, players_power, lowest)
    return out + _breath(body, n, held, s, rng)[:, None]


@remembered
def trumpet_note(freq: float, n: int, s: Mapping[str, float], seed: str) -> np.ndarray:
    return brass_note(TRUMPET, freq, n, s, seed)


@remembered
def horn_note(freq: float, n: int, s: Mapping[str, float], seed: str) -> np.ndarray:
    return brass_note(HORN, freq, n, s, seed)


@remembered
def low_brass_note(freq: float, n: int, s: Mapping[str, float], seed: str) -> np.ndarray:
    return brass_note(TROMBONE, freq, n, s, seed, below=TUBA)
