"""Bowed strings for score files (DESIGN.md §120.5): violins, violas, cellos and double basses,
each a section or a solo, with four strokes (sustained, spiccato, tremolo, pizzicato),
synthesised from the things that make a string sound bowed.

- **The string**: a bowed string moves like a sawtooth, so every harmonic is there, weaker by
  about its number; where the bow touches (``brightness``) tilts that.
- **The body**: a wooden box with resonances at fixed frequencies (the air inside, the plates,
  the "bridge hill") and a ragged response between them. They do not move with the note, so
  every pitch has its own balance of harmonics, and a vibrato sweeps each harmonic up and down
  the body's slopes: the tone moves with the pitch, which a filtered saw wave's does not.
- **The bow**: rosin noise in step with the string, a bite at the start of a stroke, and after
  the bow leaves the string the note rings on, its upper harmonics dying first.
- **A section** is several players, each with an instrument of its own: a few cents apart, their
  own vibrato speed and phase, a few milliseconds apart, spread from left to right.

Short strokes are made from time alone: the same note is the same samples every time, and every
pitch has the same energy, so an ostinato is even.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from vidgen.sfx import RATE, _filtered
from vidgen.studio.additive import (
    Phrase,
    harmonic_count,
    levelled,
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
from vidgen.studio.additive import loudness as _loud

#: The strokes, in the order of the ``stroke`` setting's numbers.
STROKES = ("sustain", "spiccato", "tremolo", "pizzicato")
_SPICCATO, _TREMOLO, _PIZZICATO = 1, 2, 3

#: Vibrato: the default seconds before it begins (the setting ``vibrato_delay``), the seconds over
#: which it grows, and a solo's default speed in Hz (``vibrato_speed``).
VIBRATO_DELAY, VIBRATO_GROWS, VIBRATO_HZ = 0.16, 0.35, 5.8
#: Tables across the vibrato's swing (the body's response at pitches from flat to sharp).
_PITCH_ROWS = 5
#: An attack at or under this many seconds bites: a short accent and a scratch at its start.
_BITTEN = 0.15
#: Narrow resonances of the wood between the main ones, per instrument.
_WOOD_PEAKS = 40
#: Level of the rosin noise against the tone, and of a stroke's scratch and a pluck's thump.
_ROSIN, _SCRATCH, _THUMP = 0.035, 0.22, 0.3
#: Short strokes against a sustained note at its full level (they are over sooner).
_SPICCATO_LEVEL, _PIZZICATO_LEVEL = 1.3, 1.8
#: Row times of a ringing string, in units of its fundamental's decay time.
_RING_TIMES = np.array([0.0, 0.05, 0.12, 0.25, 0.45, 0.7, 1.0, 1.4, 1.9, 2.6, 3.5, 4.6, 6.0, 8.0])


@dataclass(frozen=True)
class Body:
    """One instrument's box. ``air``: its lowest resonance in Hz (little is radiated under it);
    ``formants``: ``(Hz, dB, width in octaves)``, the air and plate resonances and last the
    bridge hill; ``top``: Hz above which it rolls off; ``slow``: how much slower than a violin
    its strings speak and ring."""

    name: str
    air: float
    formants: tuple[tuple[float, float, float], ...]
    top: float
    slow: float


VIOLIN = Body("violin", 275.0, ((275.0, 5.0, 0.11), (460.0, 5.0, 0.11), (550.0, 4.5, 0.11), (1000.0, 2.0, 0.3), (1550.0, -3.0, 0.22), (2700.0, 7.0, 0.36)), 4600.0, 1.0)
VIOLA = Body("viola", 225.0, ((225.0, 5.0, 0.12), (375.0, 4.5, 0.12), (490.0, 4.0, 0.13), (880.0, 2.5, 0.3), (1350.0, -3.0, 0.22), (2200.0, 5.5, 0.4)), 3900.0, 1.15)
CELLO = Body("cello", 98.0, ((98.0, 5.0, 0.13), (178.0, 5.0, 0.13), (285.0, 4.0, 0.14), (520.0, 2.5, 0.3), (850.0, -3.0, 0.22), (1400.0, 5.5, 0.42)), 3000.0, 1.5)
BASS = Body("bass", 60.0, ((60.0, 5.0, 0.14), (106.0, 5.0, 0.14), (172.0, 4.0, 0.15), (340.0, 2.5, 0.3), (520.0, -2.5, 0.22), (820.0, 5.0, 0.45)), 2100.0, 2.0)


@lru_cache(maxsize=64)
def _wood(name: str, player: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The narrow resonances of player ``player``'s instrument: octaves above 1 Hz, dB, widths.
    Every player's instrument is another piece of wood, the same one for every note."""
    body = _BODIES[name]
    rng = seeded("wood", name, player)
    octaves = np.sort(rng.uniform(math.log2(1.2 * body.air), math.log2(1.9 * body.top), _WOOD_PEAKS))
    return octaves, rng.uniform(-5.0, 5.0, _WOOD_PEAKS), rng.uniform(0.03, 0.07, _WOOD_PEAKS)


def response(body: Body, freqs: np.ndarray, player: int = 0, mute: float = 0.0) -> np.ndarray:
    """What the body does to a partial at each of ``freqs`` (Hz), in dB: fixed in frequency,
    whatever note is played. ``mute`` 0 to 1: a mute on the bridge (the bridge hill gone, a
    small hump under it, the highs down: veiled)."""
    db = -10 * np.log10(1 + (0.92 * body.air / freqs) ** 4) - 10 * np.log10(1 + (freqs / body.top) ** 4)
    octaves = np.log2(freqs)
    for center, level, width in body.formants:
        db += level * np.exp(-0.5 * ((octaves - math.log2(center)) / width) ** 2)
    centers, levels, widths = _wood(body.name, player)
    db += np.sum(levels * np.exp(-0.5 * ((octaves[:, None] - centers) / widths) ** 2), axis=1)
    if mute > 0:
        hill, level, width = body.formants[-1]
        db += mute * (-level * np.exp(-0.5 * ((octaves - math.log2(hill)) / width) ** 2) + 3 * np.exp(-0.5 * ((octaves - math.log2(0.55 * hill)) / 0.3) ** 2)
                      - 9 / (1 + (0.8 * hill / freqs) ** 4) - 1.5)
    return db


def _partials(freq: float) -> tuple[np.ndarray, np.ndarray]:
    """The harmonic numbers of a note of ``freq`` Hz (all under 16 kHz, with room for vibrato)
    and a fade of the last ones (nothing near the Nyquist frequency)."""
    number = np.arange(1, harmonic_count(freq * 1.04) + 1, dtype=float)
    return number, np.clip((16000.0 - freq * 1.04 * number) / 2000.0, 0.0, 1.0)


def bowed(body: Body, freq: float, brightness: float) -> np.ndarray:
    """The amplitudes of a bowed string's harmonics before the body: a sawtooth (harmonic ``h``
    at ``1 / h``) for ``brightness`` 0.5; towards 0 the bow is over the fingerboard (sul tasto:
    the upper harmonics fall away, flute-like), towards 1 at the bridge (sul ponticello: the
    upper harmonics as strong as the lower, the fundamental thin, glassy)."""
    b = float(np.clip(brightness, 0.0, 1.0))
    number, fade = _partials(freq)
    corner = 3200.0 * (body.top / VIOLIN.top) * 2 ** (3.2 * (b - 0.5))
    gain = number ** -(1.0 + (2.2 if b < 0.5 else 1.4) * (0.5 - b)) / np.sqrt(1 + (freq * number / corner) ** 2)
    return gain * (1 - 0.7 * max(2 * b - 1, 0.0) / number**2) * fade


def plucked(body: Body, freq: float, brightness: float, accent: float) -> np.ndarray:
    """The amplitudes of a plucked string's harmonics before the body: plucked by a fingertip a
    sixth of the way along (nearer the bridge and harder for more ``brightness`` and ``accent``),
    so every sixth harmonic or so is weak and the highs fall away quickly."""
    b = float(np.clip(brightness, 0.0, 1.0))
    number, fade = _partials(freq)
    place = 0.25 - 0.15 * b
    corner = 2400.0 * (body.top / VIOLIN.top) * 2 ** (2.0 * (b - 0.5) + 0.5 * (accent - 1.0))
    return np.sqrt(np.sin(np.pi * number * place) ** 2 + 0.02) / number / np.sqrt(1 + (freq * number / corner) ** 2) * fade


def _gain(body: Body, freqs: np.ndarray, player: int, s: Mapping[str, float]) -> np.ndarray:
    return 10 ** (response(body, freqs, player, s["mute"]) / 20)


# ----- sustained and tremolo -----------------------------------------------------------------------


def _strokes(n: int, s: Mapping[str, float], rng: np.random.Generator, alone: bool) -> np.ndarray:
    """The level of a tremolo's bow strokes over the note, between a floor and 1: ``speed``
    strokes a second (each player of a section a little faster or slower, starting anywhere in
    a stroke, the speed wandering); the string rings on between two strokes, so the floor is
    not silence. More ``accent`` is a deeper dip."""
    t = np.arange(n) / RATE
    speed = s["speed"] * (1.0 if alone else rng.uniform(0.9, 1.1))
    turns = speed * t + (0.0 if alone else rng.uniform()) + 0.12 * np.sin(2 * np.pi * (rng.uniform(0.3, 0.9) * t + rng.uniform()))
    floor = float(np.clip(0.4 - 0.2 * s["accent"], 0.0, 0.6))
    return floor + (1 - floor) * ((np.sin(np.pi * turns) ** 2 + 0.03) / 1.03) ** 0.4


def _cents(n: int, s: Mapping[str, float], rng: np.random.Generator, offset: int, alone: bool, vibrato: bool) -> np.ndarray:
    """A player's pitch over the note in cents around its own tuning: a slow drift of a cent or
    two and, ``vibrato`` wanted, the vibrato after its delay (each player of a section at its
    own speed, depth and delay)."""
    t = (np.arange(n) - offset) / RATE
    cents = np.zeros(n)
    for depth in (1.2, 0.8):
        cents += depth * np.sin(2 * np.pi * (rng.uniform(0.4, 2.2) * t + rng.uniform()))
    hz, wait = s.get("vibrato_speed", VIBRATO_HZ), s.get("vibrato_delay", VIBRATO_DELAY)
    speed, depth, delay = (hz, 1.0, wait) if alone else (rng.uniform(5.2, 6.4) * (hz / VIBRATO_HZ), rng.uniform(0.6, 1.1), wait * rng.uniform(0.7, 1.6))
    phase = rng.uniform()
    if vibrato and s["vibrato"] > 0:
        grown = np.clip((t - delay) / VIBRATO_GROWS, 0.0, 1.0)
        cents += s["vibrato"] * depth * grown * np.sin(2 * np.pi * (speed * t + phase))
    return cents


def _held_player(body: Body, freq: float, n: int, held: int, s: Mapping[str, float], player: int, offset: int, alone: bool,
                 rng: np.random.Generator, phrase: Phrase = ()) -> np.ndarray:
    """One player's sustained or tremolo note at ``freq`` Hz (the player's own tuning): mono, the
    held part as loud (:func:`~vidgen.studio.additive.loudness`) whatever the pitch and settings.
    ``phrase``: the further notes it is slurred to: the bow stays on the string, the pitch glides
    to each, and every note is the body's answer to its own pitch."""
    tremolo = int(s["stroke"]) == _TREMOLO
    t = np.arange(n) / RATE
    shape = raised_cosine(n, int(s["attack"] * RATE), offset) * (1 - raised_cosine(n, n - held, held))
    bite = s["accent"] * float(np.clip(1 - s["attack"] / _BITTEN, 0.0, 1.0))
    level = shape * (1 + 0.25 * bite * np.exp(-np.maximum(t - offset / RATE, 0.0) / 0.07))
    loudness = 1.0
    if tremolo:
        strokes = _strokes(n, s, rng, alone)
        shape = shape * strokes
        level = level * strokes
        loudness = math.sqrt(float(np.mean(strokes**2)))
    cents = _cents(n, s, rng, offset, alone, vibrato=not tremolo)
    span = float(np.abs(cents).max()) + 1.0
    offsets = np.linspace(-span, span, _PITCH_ROWS)
    turns = freq * 2 ** (cents / 1200) if not phrase else freq * 2 ** (cents / 1200 + phrase_pitch(n, phrase, offset) / 12)
    phase = phase_cycles(turns, n, 0.0 if alone else rng.uniform())
    row = (cents + span) * ((_PITCH_ROWS - 1) / (2 * span))

    def voiced(semitones: float, first: int, last: int) -> np.ndarray:
        """The tone of the note ``semitones`` above ``freq`` over the samples ``first`` to ``last``."""
        hz = freq * 2 ** (semitones / 12) if semitones else freq
        number, _ = _partials(hz)
        string = bowed(body, hz, s["brightness"])
        spectra = np.stack([string * _gain(body, hz * 2 ** (c / 1200) * number, player, s) for c in offsets])
        steady = _loud(spectra[_PITCH_ROWS // 2], hz)
        tone = read_tables(wavetables(spectra), phase[first:last], row[first:last]) / steady
        # the bow not yet (or no longer) biting: the note starts and ends with fewer upper harmonics
        soft = np.flatnonzero(shape[first:last] < 0.995)
        if len(soft):
            dark = bowed(body, hz, max(s["brightness"] - 0.3, 0.0)) * _gain(body, hz * number, player, s)
            weight = shape[first:last][soft] ** 0.8
            tone[soft] = weight * tone[soft] + (1 - weight) * read_tables(wavetables(dark[None, :]), phase[first:last][soft]) / _loud(dark, hz)
        return tone

    tone = voiced(0.0, 0, n) if not phrase else phrase_tone(n, phrase, offset, voiced)
    return tone * level / loudness


# ----- short strokes -------------------------------------------------------------------------------


def _ringing(body: Body, freq: float, s: Mapping[str, float], player: int) -> tuple[np.ndarray, np.ndarray]:
    """The harmonics of one player's spiccato stroke or pizzicato note at ``freq`` Hz as they
    change with the time since its start: ``(times, spectra)``, a row of amplitudes per time. A
    spiccato's bow is on the string for ``length`` seconds (the first row: the bite), then the
    string rings on; a plucked string rings from the start. Each harmonic dies at its own speed
    (the upper ones first)."""
    number, _ = _partials(freq)
    gain = _gain(body, freq * number, player, s)
    if int(s["stroke"]) == _PIZZICATO:
        ring = 0.2 * body.slow * math.sqrt(440.0 / freq) * s["decay"]
        string = plucked(body, freq, s["brightness"], s["accent"]) * gain
        spectra = string * np.exp(-(ring * _RING_TIMES)[:, None] * ((1 + 0.3 * (number - 1)) / ring))
        # a high note is over sooner: it starts a little louder, so a plucked line holds its level as it climbs
        return ring * _RING_TIMES, spectra * (_PIZZICATO_LEVEL * (freq / 200.0) ** 0.13 / _loud(string, freq))
    ring = 0.055 * body.slow * (440.0 / freq) ** 0.3 * s["decay"]
    string = bowed(body, freq, s["brightness"]) * gain
    bitten = bowed(body, freq, min(s["brightness"] + 0.12 * s["accent"], 1.0)) * gain
    rung = 0.85 * string * np.exp(-(ring * _RING_TIMES)[:, None] * ((1 + 0.12 * (number - 1)) / ring))
    spectra = np.concatenate([bitten[None, :] * (_loud(string, freq) / _loud(bitten, freq)), rung])
    return np.concatenate([[0.0], s["length"] + ring * _RING_TIMES]), spectra * (_SPICCATO_LEVEL / _loud(string, freq))


def _short_player(body: Body, freq: float, n: int, held: int, s: Mapping[str, float], times: np.ndarray, spectra: np.ndarray, phases: np.ndarray | None,
                  offset: int) -> np.ndarray:
    """One player's short stroke from :func:`_ringing`, mono, starting ``offset`` samples in.
    Its shape depends on the time since its start alone. After the held steps the note is
    damped over what is left of it."""
    t = np.maximum((np.arange(n) - offset) / RATE, 0.0)
    if int(s["stroke"]) == _PIZZICATO:
        level = raised_cosine(n, int(0.002 * RATE), offset)
        cents = 10.0 * s["accent"] * np.exp(-t / 0.03)  # a plucked string is sharp for a moment
        phase = np.cumsum(np.where(np.arange(n) >= offset, freq * 2 ** (cents / 1200), 0.0)) / RATE
    else:
        level = raised_cosine(n, int(0.007 * body.slow * RATE), offset) * (1 + 0.3 * s["accent"] * np.exp(-t / 0.025))
        phase = freq * t
    row = np.interp(t, times, np.arange(len(times)))
    return read_tables(wavetables(spectra, phases), phase, row) * level * (1 - raised_cosine(n, n - held, held))


def _in_step(amplitudes: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A phase (in cycles) for every harmonic of every player of a section playing a short
    stroke, ``amplitudes`` being ``(players, harmonics)``. Players start anywhere in their wave,
    and in a stroke of a tenth of a second the low harmonics stay as they began: by chance they
    would add up or cancel, another way at every pitch, and one note of an ostinato would be
    thin and the next full. Of sixteen random draws per harmonic this keeps the one whose sum is
    nearest to what players out of step give on average (the sum of their powers)."""
    players, count = amplitudes.shape
    draws = rng.uniform(size=(16, players, count))
    together = np.abs(np.sum(amplitudes * np.exp(2j * np.pi * draws), axis=1)) ** 2
    best = np.argmin(np.abs(np.log(np.maximum(together, 1e-30) / np.maximum(np.sum(amplitudes**2, axis=0), 1e-30))), axis=0)
    return draws[best, :, np.arange(count)].T


# ----- the bow's noise -----------------------------------------------------------------------------


@lru_cache(maxsize=16)
def _body_curve(name: str, mute: float) -> tuple[np.ndarray, np.ndarray]:
    """The first player's body response on a grid of octaves above 1 Hz (for filtering noise)."""
    octaves = np.linspace(math.log2(20.0), math.log2(24000.0), 4096)
    return octaves, response(_BODIES[name], 2**octaves, 0, mute)


def _through_body(body: Body, noise: np.ndarray, mute: float, low: float, high: float) -> np.ndarray:
    """``noise`` as the body radiates it between about ``low`` and ``high`` Hz; RMS 1."""
    octaves, db = _body_curve(body.name, mute)

    def gain(freqs: np.ndarray) -> np.ndarray:
        f = np.maximum(freqs, 1.0)
        return 10 ** (np.interp(np.log2(f), octaves, db) / 20) / np.sqrt(1 + (low / f) ** 4) / np.sqrt(1 + (f / high) ** 4)

    out = _filtered(noise, gain)
    return out / max(float(np.sqrt(np.mean(out**2))), 1e-12)


def _bow_noise(body: Body, freq: float, n: int, s: Mapping[str, float], power: np.ndarray, start: np.ndarray, rng: np.random.Generator,
               phrase: Phrase = ()) -> np.ndarray:
    """The noise of a note: rosin hiss while the bow is on the string, in step with the string
    (a burst each period) and following the players' level (``power``, per sample); a scratch
    where a stroke begins; for a pizzicato the thump of the finger leaving the string instead.
    ``start``: 0 before the note's first player starts, rising to 1 within 2 ms. ``phrase``: the
    notes slurred to it (the bursts follow the pitch)."""
    stroke = int(s["stroke"])
    t = np.arange(n) / RATE
    hill = body.formants[-1][0]
    if stroke == _PIZZICATO:
        thump = _through_body(body, rng.standard_normal(n), s["mute"], body.air, 1.5 * hill)
        return _THUMP * s["accent"] * thump * start * np.exp(-t / (0.006 * body.slow))
    hiss = _through_body(body, rng.standard_normal(n), s["mute"], 0.5 * hill, 12000.0)
    angle = 2 * np.pi * freq * t if not phrase else 2 * np.pi * phase_cycles(freq * 2 ** (phrase_pitch(n, phrase) / 12), n)
    pulse = (0.5 + 0.5 * np.cos(angle)) ** 3 / 0.56  # RMS 1
    bite = s["accent"] * (1.0 if stroke == _SPICCATO else float(np.clip(1 - s["attack"] / _BITTEN, 0.0, 1.0)))
    level = _ROSIN * (2.0 if stroke == _TREMOLO else 1.0) * np.sqrt(np.maximum(power, 0.0)) * pulse + _SCRATCH * bite * start * np.exp(-t / (0.012 * body.slow))
    return s["bow"] * hiss * level * start * start[::-1]


# ----- a note --------------------------------------------------------------------------------------


def string_note(body: Body, freq: float, n: int, s: Mapping[str, float], seed: str, phrase: Phrase = ()) -> np.ndarray:
    """A string note of ``n`` samples (its last ``ring`` seconds are the release): mono for one
    player, stereo ``(n, 2)`` for a section (``players`` > 1), whose level is evened (a
    sustained note's slow swings by :func:`~vidgen.studio.additive.levelled`, each side alone; a short stroke's
    players begin in step harmonic by harmonic, :func:`_in_step`, and its energy on each side is
    set to that of its players). ``phrase``: the notes slurred to it (sustained and tremolo
    notes; :data:`~vidgen.studio.additive.Phrase`). The same ``seed``, pitch, length, settings
    and phrase give the same samples."""
    stroke = int(s["stroke"])
    short = stroke in (_SPICCATO, _PIZZICATO)
    held = max(n - max(int(s["ring"] * RATE), 1), 0)
    players = int(round(s["players"]))
    rng = seeded("strings", body.name, seed, round(freq, 3))
    spread = np.linspace(-1.0, 1.0, players) if players > 1 else np.zeros(1)
    tuned = freq * 2 ** ((rng.permutation(spread) * s["detune"] + rng.uniform(-1.5, 1.5, players)) / 1200)
    apart = {_SPICCATO: 0.006, _PIZZICATO: 0.012}.get(stroke, min(0.03, 0.3 * s["attack"]))
    late = np.zeros(1, dtype=np.intp) if players == 1 else (rng.uniform(0.0, apart, players) * RATE).astype(np.intp)
    late -= late.min()
    start = raised_cosine(n, int(0.002 * RATE))
    if short:
        rings = [_ringing(body, float(tuned[k]), s, k) for k in range(players)]
        count = min(spectra.shape[1] for _, spectra in rings)
        rings = [(times, spectra[:, :count]) for times, spectra in rings]
        power = _contact(n, s)
        if players == 1:
            return _short_player(body, float(tuned[0]), n, held, s, *rings[0], None, 0) + _bow_noise(body, freq, n, s, power, start, rng)
        # the players' phases are chosen where the stroke is loudest: 20 ms after the first begins
        phases = _in_step(np.stack([spectra[0] for _, spectra in rings]), rng)
        phases -= np.arange(1, count + 1) * (tuned * (0.02 - late / RATE))[:, None]
        notes = [_short_player(body, float(tuned[k]), n, held, s, *rings[k], phases[k], int(late[k])) for k in range(players)]
    elif players == 1:
        mono = _held_player(body, float(tuned[0]), n, held, s, 0, 0, True, rng, phrase)
        return mono + _bow_noise(body, freq, n, s, smoothed(mono**2, int(RATE / freq) + 1), start, rng, phrase)
    else:
        notes = [_held_player(body, float(tuned[k]), n, held, s, k, int(late[k]), False, rng, phrase) for k in range(players)]
    out = np.zeros((n, 2))
    sides_power = np.zeros((n, 2))
    for k, mono in enumerate(notes):
        angle = (0.7 * spread[k] + 1) * math.pi / 4
        sides = math.sqrt(2 / players) * np.array([math.cos(angle), math.sin(angle)])
        out += mono[:, None] * sides
        sides_power += (mono**2)[:, None] * sides**2
    if short:
        out *= np.clip(np.sqrt(sides_power.sum(axis=0) / np.maximum((out**2).sum(axis=0), 1e-30)), 0.5, 2.0)
    else:
        for side in range(2):  # each side on its own, so the section does not lean left on one note and right on the next
            out[:, side : side + 1] = levelled(out[:, side : side + 1], 0.5 * sides_power[:, side], freq)
        power = smoothed(0.5 * sides_power.sum(axis=1), int(RATE / freq) + 1)
    return out + np.stack([_bow_noise(body, freq, n, s, power, start, rng, phrase) for _ in range(2)], axis=1)


def _contact(n: int, s: Mapping[str, float]) -> np.ndarray:
    """1 while a spiccato's bow is on the string (``length`` seconds), then falling away."""
    t = np.arange(n) / RATE
    return np.where(t < s["length"], 1.0, np.exp(-(t - s["length"]) / 0.01)) * raised_cosine(n, int(0.004 * RATE))


_BODIES = {body.name: body for body in (VIOLIN, VIOLA, CELLO, BASS)}


@remembered
def violins_note(freq: float, n: int, s: Mapping[str, float], seed: str, phrase: Phrase = ()) -> np.ndarray:
    return string_note(VIOLIN, freq, n, s, seed, phrase)


@remembered
def violas_note(freq: float, n: int, s: Mapping[str, float], seed: str, phrase: Phrase = ()) -> np.ndarray:
    return string_note(VIOLA, freq, n, s, seed, phrase)


@remembered
def cellos_note(freq: float, n: int, s: Mapping[str, float], seed: str, phrase: Phrase = ()) -> np.ndarray:
    return string_note(CELLO, freq, n, s, seed, phrase)


@remembered
def basses_note(freq: float, n: int, s: Mapping[str, float], seed: str, phrase: Phrase = ()) -> np.ndarray:
    return string_note(BASS, freq, n, s, seed, phrase)
