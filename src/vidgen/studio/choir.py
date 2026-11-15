"""A choir for score files (DESIGN.md §120.6): sections of singers holding a vowel, by formant
synthesis. It is a choir *pad*: ooh, aah, eeh, a hum. It sings no words.

- **The voice**: the vocal folds give every harmonic of the note, each weaker than the one
  before (the softer the singing, the faster they fall).
- **The vowel** is the mouth and throat: five resonances (formants) at fixed frequencies with
  fixed bandwidths, different for every vowel and for basses, tenors, altos and sopranos. They
  stay where they are while the pitch moves, so each harmonic grows and shrinks as vibrato
  carries it across them.
- **High notes**: above its first formant a voice would lose its fundamental's resonance;
  singers open the mouth until the first formant follows the note. So does this one (and the
  vowels of a high soprano note then sound alike, as they do in a hall).
- **A section** is several singers: each with a slightly longer or shorter throat (the formants
  a few percent apart), a few cents off, with a vibrato of its own speed, depth and delay,
  entering a little apart, with breath in the tone.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

from vidgen.sfx import RATE, _filtered
from vidgen.studio.additive import harmonic_count, levelled, loudness, phase_cycles, raised_cosine, read_tables, remembered, seeded, smoothed, wavetables

#: The vowels, in the order of the ``vowel`` setting's numbers.
VOWELS = ("ooh", "aah", "eeh", "mm", "oh", "ee")
#: Who sings, in the order of the ``voices`` setting's numbers.
VOICES = ("mixed", "men", "women", "basses", "tenors", "altos", "sopranos")
#: The four kinds of voice, low to high.
KINDS = ("basses", "tenors", "altos", "sopranos")
#: ``morph``: the vowel a held note turns into (0: it keeps its own).
MORPHS = ("none",) + VOWELS

#: Formants of sung vowels: per kind of voice and vowel five ``(Hz, bandwidth in Hz)``. The
#: frequencies and bandwidths are the table for sung voices in the Csound manual (after IRCAM's
#: CHANT); "mm" (a hum: the mouth closed, the sound through the nose) is a low first formant
#: and broad, weak ones above it.
FORMANTS: dict[str, dict[str, tuple[tuple[float, float], ...]]] = {
    "basses": {
        "aah": ((600, 60), (1040, 70), (2250, 110), (2450, 120), (2750, 130)),
        "eeh": ((400, 40), (1620, 80), (2400, 100), (2800, 120), (3100, 120)),
        "ee": ((250, 60), (1750, 90), (2600, 100), (3050, 120), (3340, 120)),
        "oh": ((400, 40), (750, 80), (2400, 100), (2600, 120), (2900, 120)),
        "ooh": ((350, 40), (600, 80), (2400, 100), (2675, 120), (2950, 120)),
        "mm": ((240, 70), (950, 300), (2100, 350), (2700, 400), (3300, 400)),
    },
    "tenors": {
        "aah": ((650, 80), (1080, 90), (2650, 120), (2900, 130), (3250, 140)),
        "eeh": ((400, 70), (1700, 80), (2600, 100), (3200, 120), (3580, 120)),
        "ee": ((290, 40), (1870, 90), (2800, 100), (3250, 120), (3540, 120)),
        "oh": ((400, 40), (800, 80), (2600, 100), (2800, 120), (3000, 120)),
        "ooh": ((350, 40), (600, 60), (2700, 100), (2900, 120), (3300, 120)),
        "mm": ((250, 70), (1000, 300), (2200, 350), (2900, 400), (3500, 400)),
    },
    "altos": {
        "aah": ((800, 80), (1150, 90), (2800, 120), (3500, 130), (4950, 140)),
        "eeh": ((400, 60), (1600, 80), (2700, 120), (3300, 150), (4950, 200)),
        "ee": ((350, 50), (1700, 100), (2700, 120), (3700, 150), (4950, 200)),
        "oh": ((450, 70), (800, 80), (2830, 100), (3500, 130), (4950, 135)),
        "ooh": ((325, 50), (700, 60), (2530, 170), (3500, 180), (4950, 200)),
        "mm": ((280, 80), (1100, 320), (2400, 380), (3300, 420), (4500, 450)),
    },
    "sopranos": {
        "aah": ((800, 80), (1150, 90), (2900, 120), (3900, 130), (4950, 140)),
        "eeh": ((350, 60), (2000, 100), (2800, 120), (3600, 150), (4950, 200)),
        "ee": ((270, 60), (2140, 90), (2950, 100), (3900, 120), (4950, 120)),
        "oh": ((450, 70), (800, 80), (2830, 100), (3800, 130), (4950, 135)),
        "ooh": ((325, 50), (700, 60), (2700, 170), (3800, 180), (4950, 200)),
        "mm": ((300, 80), (1150, 320), (2500, 380), (3500, 420), (4700, 450)),
    },
}
#: Where each kind of voice sings comfortably, as MIDI notes (E2–G3, D3–E4, A3–C5, E4–E6): in
#: ``mixed``, ``men`` and ``women`` a note is shared out among the kinds that reach it.
COMFORT = {"basses": (40, 55), "tenors": (50, 64), "altos": (57, 72), "sopranos": (64, 88)}
#: Semitones outside its comfortable notes over which a kind of voice leaves a shared note.
_REACH = 4.0
#: How fast the voice's harmonics fall with their number when sung softly and at full voice.
_SOFT, _FULL = 2.0, 1.0
#: Tables across a singer's pitch swing (the formants sampled at pitches from flat to sharp).
_PITCH_ROWS = 5
#: Breath against the tone.
_BREATH = 0.03


def formants(kind: str, vowel: str, freq: float, throat: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """The formant frequencies and bandwidths (Hz) of a ``kind`` of voice singing ``vowel`` on a
    note of ``freq`` Hz. ``throat``: this singer's formants against the table's (a shorter throat
    has higher ones). Above the first formant the mouth opens: the first formant follows the
    note, and the second stays at least a third above it."""
    table = np.array(FORMANTS[kind][vowel], dtype=float)
    hz, width = table[:, 0] * throat, table[:, 1].copy()
    if freq > hz[0]:
        width[0] *= freq / hz[0]
        hz[0] = freq
    hz[1] = max(hz[1], 1.33 * hz[0])
    return hz, width


def spectrum(kind: str, vowel: str, freq: float, brightness: float, throat: float = 1.0, cents: float = 0.0) -> np.ndarray:
    """The amplitudes of the harmonics of a sung note of ``freq`` Hz (all under 16 kHz): the
    folds' harmonics, weaker by ``h ** -2`` (``brightness`` 0, soft) to ``h ** -1`` (1, full
    voice), through the formants as five resonances one after another. ``cents``: the voice is
    this far off the note at the moment (vibrato moves the pitch; the mouth stays shaped for
    ``freq``)."""
    number = np.arange(1, harmonic_count(freq * 1.05) + 1, dtype=float)
    freqs = freq * 2 ** (cents / 1200) * number
    hz, width = formants(kind, vowel, freq, throat)
    gain = number ** -(_SOFT + (_FULL - _SOFT) * float(np.clip(brightness, 0.0, 1.0)))
    for center, band in zip(hz, width):
        gain = gain * center**2 / np.sqrt((center**2 - freqs**2) ** 2 + (band * freqs) ** 2)
    if vowel == "mm":
        gain = gain / (1 + (freqs / 700.0) ** 2)  # the lips are closed: little but the lowest harmonics gets out
    return gain * np.clip((16000.0 - freq * 1.05 * number) / 2000.0, 0.0, 1.0)


def section(voices: str, midi: float, singers: int) -> list[str]:
    """The kind of voice of each of ``singers`` singing the MIDI note ``midi``: for one kind all
    of them; for ``mixed``, ``men`` and ``women`` shared out among the kinds that reach the note
    (middle C in a mixed choir: tenors and altos), the nearest kind when none does."""
    if voices in KINDS:
        return [voices] * singers
    kinds = {"men": KINDS[:2], "women": KINDS[2:]}.get(voices, KINDS)
    share = np.array([float(np.clip(1 - max(COMFORT[k][0] - midi, midi - COMFORT[k][1], 0.0) / _REACH, 0.0, 1.0)) for k in kinds])
    if not share.any():
        share[int(np.argmin([max(COMFORT[k][0] - midi, midi - COMFORT[k][1]) for k in kinds]))] = 1.0
    wanted = share / share.sum() * singers
    counts = np.floor(wanted).astype(int)
    for k in np.argsort(counts - wanted)[: singers - int(counts.sum())]:
        counts[k] += 1
    return [kind for kind, count in zip(kinds, counts) for _ in range(count)]


def _cents(n: int, s: Mapping[str, float], rng: np.random.Generator, offset: int, alone: bool) -> np.ndarray:
    """A singer's pitch over the note in cents around its own tuning: a scoop into the note, a
    slow wander of a few cents, and after its delay the vibrato (each singer's own speed, depth
    and delay)."""
    t = (np.arange(n) - offset) / RATE
    cents = -rng.uniform(10.0, 35.0) * np.where(t >= 0, np.exp(-np.maximum(t, 0.0) / 0.06), 0.0)
    for depth in (3.0, 2.0, 1.2):
        cents += depth * np.sin(2 * np.pi * (rng.uniform(0.3, 2.6) * t + rng.uniform()))
    speed, depth, delay = (5.5, 1.0, 0.3) if alone else (rng.uniform(4.8, 6.2), rng.uniform(0.5, 1.2), rng.uniform(0.2, 0.6))
    phase = rng.uniform()
    if s["vibrato"] > 0:
        cents += s["vibrato"] * depth * np.clip((t - delay) / 0.5, 0.0, 1.0) * np.sin(2 * np.pi * (speed * t + phase))
    return cents


def _singer(kind: str, freq: float, n: int, held: int, s: Mapping[str, float], offset: int, alone: bool, rng: np.random.Generator) -> np.ndarray:
    """One singer's note at ``freq`` Hz (the singer's own tuning): mono, the held part as loud
    (:func:`~vidgen.studio.additive.loudness`) whatever the pitch, vowel and kind of voice."""
    throat = 1.0 if alone else rng.uniform(0.96, 1.04)
    attack = s["attack"] * (1.0 if alone else rng.uniform(0.8, 1.3))
    level = raised_cosine(n, int(attack * RATE), offset) * (1 - raised_cosine(n, n - held, held))
    level *= 1 + 0.06 * np.sin(2 * np.pi * (rng.uniform(0.2, 0.9) * np.arange(n) / RATE + rng.uniform()))
    cents = _cents(n, s, rng, offset, alone)
    span = float(np.abs(cents).max()) + 1.0
    offsets = np.linspace(-span, span, _PITCH_ROWS)
    phase = phase_cycles(freq * 2 ** (cents / 1200), n, rng.uniform())
    row = (cents + span) * ((_PITCH_ROWS - 1) / (2 * span))

    def sung(vowel: str) -> np.ndarray:
        spectra = np.stack([spectrum(kind, vowel, freq, s["brightness"], throat, float(c)) for c in offsets])
        return read_tables(wavetables(spectra), phase, row) / loudness(spectra[_PITCH_ROWS // 2], freq)

    tone = sung(VOWELS[int(s["vowel"])])
    if int(s["morph"]):
        # the mouth moves from one vowel to the other over the middle of the held note
        share = raised_cosine(n, max(int(0.7 * held), 1), int(0.15 * held))
        tone += share * (sung(MORPHS[int(s["morph"])]) - tone)
    return tone * level


def _breath(kinds: list[str], freq: float, n: int, s: Mapping[str, float], power: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """The air in the voices: noise through the vowel's formants (of the first singer's kind),
    following the singers' level (``power``, per sample), a little more as they begin."""
    hz, width = formants(kinds[0], VOWELS[int(s["vowel"])], freq)

    def gain(freqs: np.ndarray) -> np.ndarray:
        f = np.maximum(freqs, 1.0)
        out = 1 / np.sqrt(1 + (900.0 / f) ** 4) / np.sqrt(1 + (f / 9000.0) ** 4)
        for center, band in zip(hz, 3 * width):
            out = out * center**2 / np.sqrt((center**2 - f**2) ** 2 + (band * f) ** 2)
        return out

    noise = _filtered(rng.standard_normal(n), gain)
    noise /= max(float(np.sqrt(np.mean(noise**2))), 1e-12)
    t = np.arange(n) / RATE
    hummed = 0.3 if VOWELS[int(s["vowel"])] == "mm" and not int(s["morph"]) else 1.0  # little air passes closed lips
    return hummed * _BREATH * s["breath"] * noise * np.sqrt(np.maximum(power, 0.0)) * (1 + 1.5 * np.exp(-t / 0.15)) * raised_cosine(n, int(0.005 * RATE))


@remembered
def choir_note(freq: float, n: int, s: Mapping[str, float], seed: str) -> np.ndarray:
    """A choir note of ``n`` samples (its last ``ring`` seconds are the release): stereo
    ``(n, 2)`` for a section, mono for one singer. A section's slow level swings are taken out
    on each side (:func:`~vidgen.studio.additive.levelled`). The same ``seed``, pitch, length
    and settings give the same samples."""
    held = max(n - max(int(s["ring"] * RATE), 1), 0)
    singers = int(round(s["singers"]))
    rng = seeded("choir", seed, round(freq, 3))
    kinds = section(VOICES[int(s["voices"])], 69 + 12 * math.log2(freq / 440.0), singers)
    spread = np.linspace(-1.0, 1.0, singers) if singers > 1 else np.zeros(1)
    tuned = freq * 2 ** ((rng.permutation(spread) * s["detune"] + rng.uniform(-2.0, 2.0, singers)) / 1200)
    late = np.zeros(1, dtype=np.intp) if singers == 1 else (rng.uniform(0.0, min(0.07, 0.4 * s["attack"]), singers) * RATE).astype(np.intp)
    late -= late.min()
    if singers == 1:
        mono = _singer(kinds[0], float(tuned[0]), n, held, s, 0, True, rng)
        return mono + _breath(kinds, freq, n, s, smoothed(mono**2, int(RATE / freq) + 1), rng)
    out = np.zeros((n, 2))
    sides_power = np.zeros((n, 2))
    places = rng.permutation(spread)  # the kinds of voice stand mixed, not basses left and sopranos right
    for k in range(singers):
        mono = _singer(kinds[k], float(tuned[k]), n, held, s, int(late[k]), False, rng)
        angle = (0.8 * places[k] + 1) * math.pi / 4
        sides = math.sqrt(2 / singers) * np.array([math.cos(angle), math.sin(angle)])
        out += mono[:, None] * sides
        sides_power += (mono**2)[:, None] * sides**2
    for side in range(2):
        out[:, side : side + 1] = levelled(out[:, side : side + 1], 0.5 * sides_power[:, side], freq)
    power = smoothed(0.5 * sides_power.sum(axis=1), int(RATE / freq) + 1)
    return out + np.stack([_breath(kinds, freq, n, s, power, rng) for _ in range(2)], axis=1)
