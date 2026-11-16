"""A drawbar organ for score files (DESIGN.md §120.4): nine ranks at the organ footages, each
drawn 0 (off) to 8 (full, 3 dB a step), their pipes a sine (an electric drawbar organ), a
principal, a stopped flute or a reed. A rank's pipe for a note stands a little to the left or to
the right (neighbouring semitones and neighbouring ranks on opposite sides, as in an organ
case), so a chord is wide.
Pipes speak after a number of periods (low pipes later) with a short "chiff" and hold steadily
until the key is let go; the ranks are a cent or so out of tune with each other, and ``chorus``
adds a second, detuned pipe to every rank (a slow beating: a celeste)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio.additive import HIGHEST_PARTIAL, band_noise, harmonic_count, phase_cycles, raised_cosine, read_tables, remembered, seeded, wavetables

#: The nine drawbars from left to right, and each rank's pitch as a multiple of the 8' rank's.
FOOTAGES = ("16'", "5 1/3'", "8'", "4'", "2 2/3'", "2'", "1 3/5'", "1 1/3'", "1'")
RATIOS = (0.5, 1.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0)
#: A rank above ``FOLD_ABOVE`` Hz plays an octave lower (an organ's mixtures "break back", a
#: tonewheel organ folds its top octave), one under ``FOLD_BELOW`` an octave higher.
FOLD_ABOVE, FOLD_BELOW = 6000.0, 27.0
#: dB per drawbar step.
DRAWBAR_DB = 3.0
#: Seconds the fastest rank takes to speak (an electric organ's key; slower would not click either).
_FASTEST_SPEECH = 0.01
_MIDDLE_C = 261.63
#: The least the two pipes of a rank are apart with ``chorus`` (cents, times 1 to 2).
_CHORUS_CENTS = 3.0
#: How far from the middle a pipe stands (0 middle, 1 hard left or right), and with ``chorus: 1``
#: (its second pipe then stands as far on the other side: the beating moves between the sides).
_PIPE_PAN, _CHORUS_PAN = 0.2, 0.65


def _pan_gains(pan: float) -> np.ndarray:
    """Left and right gains of a pipe at ``pan`` (-1 to 1), constant power, 1 each in the middle."""
    angle = (pan + 1) * math.pi / 4
    return math.sqrt(2) * np.array([math.cos(angle), math.sin(angle)])


def _pipe_harmonics(pipe: str, freq: float, tone: float) -> np.ndarray:
    """The harmonic amplitudes of one pipe of ``freq`` Hz: ``sine`` (one), ``principal`` (a
    strong fundamental, then about -9 dB an octave), ``flute`` (stopped: a little third and
    fifth harmonic), ``reed`` (many harmonics and a nasal peak near 1.5 kHz); low-passed at
    ``tone`` Hz."""
    if pipe == "sine":
        return np.ones(1)
    k = np.arange(1, harmonic_count(freq * 1.01) + 1, dtype=float)
    if pipe == "principal":
        amps = k**-1.5 * np.exp(-(k - 1) / 9.0)
    elif pipe == "flute":
        amps = np.where(k % 2 == 1, k**-2.6, 0.012 * k**-1.5)
    else:
        amps = k**-0.85 * (1 + 1.6 * np.exp(-0.5 * (np.log2(k * freq / 1500.0) / 0.45) ** 2))
    f = k * freq
    return amps / np.sqrt(1 + (f / tone) ** 4) * np.clip((16000.0 - f) / 2000.0, 0.0, 1.0)


@dataclass(frozen=True)
class Registration:
    """A named registration: its ``drawbars`` (nine digits 0-8), its pipes' kind, how many
    periods a pipe takes to speak (``speech``) and the strength of its ``chiff``."""

    name: str
    drawbars: str
    pipe: str
    speech: float
    chiff: float
    words: str


#: The named registrations, in the order of the ``registration`` setting's numbers.
REGISTRATIONS: tuple[Registration, ...] = (
    Registration("cathedral", "608756045", "principal", 9.0, 1.0,
                 "a full principal chorus with mixtures (16' 8' 4' 2 2/3' 2' 1 1/3' 1'): the big church organ, pipes speaking softly with a chiff"),
    Registration("principal", "008500000", "principal", 9.0, 0.7, "an 8' and a 4' principal: plain, singing, for a quiet chorale"),
    Registration("flute", "008300000", "flute", 7.0, 1.0, "a soft stopped flute, 8' with a little 4': round and hollow, a breathy start"),
    Registration("reed", "008400000", "reed", 5.0, 0.3, "a reed stop (trumpet/oboe-like pipes), 8' with a little 4': nasal and rich"),
    Registration("drawbar", "888000000", "sine", 0.0, 0.0, "an electric drawbar organ's first three bars (sine ranks 16' 5 1/3' 8'): warm and round"),
    Registration("full", "888888888", "sine", 0.0, 0.0, "an electric drawbar organ with every bar out: bright and thick"),
)
REGISTRATION_NAMES = tuple(r.name for r in REGISTRATIONS)


def read_drawbars(value: Any, where: str) -> float:
    """The ``drawbars`` setting as the number the score keeps: nine digits 0-8, written in quotes
    (``"00 8400 000"``, spaces free) or as a nine-digit number; 0: the registration's own.
    :class:`VidgenError` for anything else (YAML reads an unquoted number that starts with 0
    as another number, so that is refused with the hint to quote it)."""
    text = "".join(value.split()) if isinstance(value, str) else str(value) if isinstance(value, int) and not isinstance(value, bool) else ""
    if text == "0":
        return 0.0
    if len(text) != 9 or not all(c in "012345678" for c in text) or (not isinstance(value, str) and text[0] == "0"):
        raise VidgenError(
            f"{where}: expected nine drawbar digits 0 to 8 in quotes, e.g. \"00 8400 000\" ({', '.join(FOOTAGES)}), or 0 for the "
            f"registration's own, got {value!r}" + (" (quote it: YAML reads a number that starts with 0 differently)" if not isinstance(value, str) else "")
        )
    return float(int(text))


def drawbar_levels(s: Mapping[str, float]) -> tuple[Registration, tuple[int, ...]]:
    """The registration the settings name and the nine drawbars' positions (the ``drawbars``
    setting when it is not 0, else the registration's)."""
    registration = REGISTRATIONS[int(round(s["registration"]))]
    text = f"{int(round(s['drawbars'])):09d}" if s["drawbars"] > 0 else registration.drawbars
    return registration, tuple(int(c) for c in text)


def _folded(freq: float) -> float:
    while freq > FOLD_ABOVE:
        freq /= 2
    while freq < FOLD_BELOW:
        freq *= 2
    return freq


def _click(rng: np.random.Generator, n: int, held: int) -> np.ndarray:
    """A key click: 2 ms of noise from 1.5 to 7 kHz when the key goes down, half of it when it
    comes up."""
    length = min(int(0.012 * RATE), n)
    burst = band_noise(rng, length, 3200.0, 0.7, 7000.0) * np.exp(-np.arange(length) / (0.002 * RATE)) * raised_cosine(length, 12)
    out = np.zeros(n)
    out[:length] += burst
    end = min(held + length, n)
    out[held:end] += 0.5 * burst[: end - held]
    return out


def _drawn_ranks(freq: float, bars: tuple[int, ...]) -> list[tuple[int, float, float]]:
    """The ranks that sound for a note of ``freq`` Hz: ``(drawbar index, Hz, gain)``. Ranks that
    fold onto the same pitch are one rank with their powers added (two would beat)."""
    ranks: dict[int, tuple[int, float, float]] = {}
    for index, (ratio, bar) in enumerate(zip(RATIOS, bars)):
        if bar == 0:
            continue
        rank = _folded(freq * ratio)
        key = round(12 * math.log2(rank / freq))
        gain = 10 ** (-DRAWBAR_DB * (8 - bar) / 20)
        ranks[key] = (ranks[key][0], rank, math.hypot(ranks[key][2], gain)) if key in ranks else (index, rank, gain)
    return list(ranks.values())


@remembered
def organ_note(freq: float, n: int, s: Mapping[str, float], seed: str) -> np.ndarray:
    """An organ note of ``n`` samples, stereo ``(n, 2)``; its last ``ring`` seconds are the
    release. Every pipe starts at the same point of its wave, so a note sounds the same each time
    and whatever its pitch; its power is the same whatever the registration, 1 dB more per octave
    towards the bass. The same ``seed``, pitch, length and settings give the same samples."""
    registration, bars = drawbar_levels(s)
    rng = seeded("organ", seed, round(freq, 3))
    held = max(n - max(int(s["ring"] * RATE), 1), 0)
    t = np.arange(n) / RATE
    release = 1 - raised_cosine(n, n - held, held)
    out = np.zeros((n, 2))
    grid = freq / 16  # every harmonic of every rank is a multiple of it
    partials = np.zeros((2, int(HIGHEST_PARTIAL / grid) + 2))
    chiff = registration.chiff * s["chiff"]
    for index, rank, gain in _drawn_ranks(freq, bars):
        harmonics = _pipe_harmonics(registration.pipe, rank, s["tone"])
        table = wavetables(harmonics[None, :])
        speaks = max(registration.speech / rank * s["attack"], _FASTEST_SPEECH)
        level = gain * raised_cosine(n, int(speaks * RATE)) * release
        if chiff > 0:  # the pipe overblows for a moment: its octave (a stopped flute: its twelfth) sounds first
            over = 3.0 if registration.pipe == "flute" else 2.0
            chiff_level = 0.5 * chiff * gain * np.exp(-t / (1.5 * speaks)) * raised_cosine(n, int(0.3 * speaks * RATE) + 48) * release
        off = rng.normal(0.0, 0.4) * s["detune"]
        side = (_PIPE_PAN + (_CHORUS_PAN - _PIPE_PAN) * s["chorus"]) * (1 if (round(12 * math.log2(rank / _MIDDLE_C)) + index) % 2 == 0 else -1)
        apart = rng.uniform(1.0, 2.0) * max(s["detune"], _CHORUS_CENTS)
        pipes = [(off, 1.0, side, 0.0)] + ([(off + apart, s["chorus"], -side, rng.uniform())] if s["chorus"] > 0 else [])
        for cents, share, pan, start in pipes:
            pipe_freq = rank * 2 ** (cents / 1200)
            pipe = read_tables(table, phase_cycles(pipe_freq, n, start)) * level
            if chiff > 0 and pipe_freq * over < 12000.0:
                pipe += np.sin(2 * np.pi * phase_cycles(pipe_freq * over * 1.004, n, rng.uniform())) * chiff_level
            out += pipe[:, None] * (share * _pan_gains(pan))
        at = np.rint(rank * np.arange(1, len(harmonics) + 1) / grid).astype(np.intp)
        partials[:, at] += gain * harmonics * _pan_gains(side)[:, None]
    power = 0.5 * (1 + s["chorus"] ** 2) * float(np.mean(np.sum(partials**2, axis=1)))
    # equal power would leave low notes quieter to the ear: 1 dB more per octave under middle C
    out *= (_MIDDLE_C / freq) ** (1 / 6) / math.sqrt(max(2 * power, 1e-12))
    if chiff > 0:  # the wind before the tone: a burst of noise around the pipes' upper harmonics
        wind = float(np.clip(5 * freq, 900.0, 5000.0))
        burst = np.exp(-t / 0.035) * raised_cosine(n, int(0.004 * RATE)) * release
        for channel in range(2):
            out[:, channel] += 0.11 * chiff * band_noise(rng, n, wind, 0.8, 9000.0) * burst
    if s["click"] > 0:
        out += (0.5 * s["click"] * _click(rng, n, held))[:, None]
    return out
