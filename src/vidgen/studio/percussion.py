"""Orchestral percussion for score files (DESIGN.md §120.6): timpani and concert toms played by
note name, a taiko, a concert bass drum, a frame drum and a snare drum played as drum steps, a
suspended cymbal and a tam-tam. No samples: every drum is a sum of the modes its head or its
metal really has.

- **A struck head** rings in modes that are *not* a harmonic series. A plain membrane's lie at
  1 : 1.59 : 2.14 : 2.30 : 2.65 : 2.92 ... of its lowest; a kettledrum's air and kettle pull the
  modes with a line across the head to nearly 1 : 1.5 : 2 : 2.44 : 2.9 above a missing
  fundamental, which is why a timpano has a note. Every mode dies at its own speed.
- **The mallet** is a low-pass on the blow: a soft felt head stays on the skin for milliseconds
  and wakes the low modes only, a wooden stick wakes all of them and adds its own knock.
- **The blow stretches the head**, so the pitch starts sharp and falls: a few cents on a
  timpano, a semitone or more on a tom or a taiko.
- **Metal** (cymbal, tam-tam) has hundreds of modes: the lowest are made one by one, the rest
  as bands of noise that each die (and, in a tam-tam, each arrive) at their own speed.

A drum is made once per setting and pitch and then only cut and damped, so a pattern of
hundreds of hits is cheap and every hit at the same settings is the same samples. Rolls and
swells are a train of strokes through the drum's own ring (a convolution).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from vidgen.sfx import RATE, _filtered
from vidgen.studio.additive import HIGHEST_PARTIAL, raised_cosine, seeded

#: The modes of a plain membrane as multiples of its lowest, (0,1) (1,1) (2,1) (0,2) (3,1) (1,2)
#: (4,1) (2,2) (0,3) (5,1) and on: the zeros of the Bessel functions.
MEMBRANE = (1.0, 1.594, 2.136, 2.296, 2.653, 2.918, 3.156, 3.501, 3.600, 3.652, 4.060, 4.154, 4.601, 4.832, 5.131, 5.412)
#: A kettledrum's "preferred" modes (1,1) (2,1) (3,1) ... (the ones with lines across the head)
#: as multiples of its note, after Rossing's measurements: near 1 : 1.5 : 2 : 2.5 : 3.
KETTLE = (1.0, 1.504, 1.99, 2.44, 2.91, 3.36, 3.79, 4.22, 4.65, 5.07, 5.50, 5.93, 6.36, 6.79, 7.22)
#: Its short-lived modes without a line across, (0,1) (0,2) (1,2) (0,3): ``(multiple, level,
#: share of the main mode's ring)``. The (0,1) mode under the note is the thump of the blow.
KETTLE_DULL = ((0.85, 0.5, 0.07), (1.68, 0.25, 0.08), (2.09, 0.2, 0.1), (2.66, 0.12, 0.08))
#: A drum's loudness is measured over its first seconds: the RMS there is 1. Metal: its loudest.
_LOUD_SECONDS, _METAL_SECONDS = 0.15, 0.4
#: No blow's peak is more than this many times its RMS (a short, sharp blow is turned down).
_HIGHEST_PEAK = 3.6
#: A roll at full force against the start of one blow.
_ROLL_LEVEL = 0.7
#: The signs with which a blow off the middle of the head sets its modes going (they do not all
#: start the same way, or every blow would begin with a spike of all of them together).
_SIGNS = (1.0, -1.0, 1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
#: Seconds over which a drum cut short by its steps is damped (a hand on the head).
_DAMP = 0.07


@dataclass(frozen=True)
class Head:
    """A drum: its ``modes`` (multiples of the written pitch); under a medium mallet the mode at
    multiple ``m`` has the level ``m ** -falls`` (a soft one: ``m ** -(1.5 * falls)``, a hard one ``m ** -(0.5 * falls)``) and rings ``m ** -dies`` as long as the lowest;
    ``seconds``: the time the lowest takes to fall by 60 dB at 110 Hz, longer for lower drums by
    ``by_pitch`` (the power of 110 / Hz); ``contact``: the mallet's low-pass in Hz at ``mallet``
    0 and 1; ``knock``: the level and the centre (in multiples of the pitch) of the blow's own
    noise; ``more``: further modes ``(multiple, level, share of the lowest's ring)``, a
    kettledrum's short-lived ones; ``shell``: modes of the shell or barrel ``(multiple, level,
    seconds)``; ``lasting``: the ring of the first modes where it is not ``m ** -dies`` (a
    kettledrum's note sends its sound out best and so dies before its fifth and octave)."""

    name: str
    modes: tuple[float, ...]
    falls: float
    dies: float
    seconds: float
    by_pitch: float
    contact: tuple[float, float]
    knock: tuple[float, float]
    more: tuple[tuple[float, float, float], ...] = ()
    shell: tuple[tuple[float, float, float], ...] = ()
    lasting: tuple[float, ...] = ()


TIMPANO = Head("timpano", KETTLE, 1.3, 0.6, 2.6, 0.5, (160.0, 3000.0), (0.2, 6.0), more=KETTLE_DULL, lasting=(1.0, 1.25, 1.15, 0.9))
TOM = Head("tom", MEMBRANE, 1.6, 1.2, 0.95, 0.5, (350.0, 5000.0), (0.2, 9.0), shell=((3.4, 0.16, 0.16), (5.3, 0.1, 0.11)))
TAIKO = Head("taiko", MEMBRANE, 1.3, 1.4, 1.9, 0.4, (500.0, 4200.0), (0.8, 18.0), shell=((4.6, 0.3, 0.2), (7.1, 0.22, 0.12)))
BASS_DRUM = Head("bass drum", MEMBRANE, 1.2, 0.7, 3.4, 0.3, (110.0, 1500.0), (0.3, 8.0))
FRAME_DRUM = Head("frame drum", MEMBRANE, 1.3, 1.0, 0.75, 0.4, (500.0, 5000.0), (0.35, 12.0))
SNARE = Head("snare drum", MEMBRANE, 0.8, 0.7, 0.3, 0.3, (900.0, 7000.0), (0.3, 14.0))

_HEADS = {head.name: head for head in (TIMPANO, TOM, TAIKO, BASS_DRUM, FRAME_DRUM, SNARE)}


def mode_frequencies(head: Head, freq: float) -> np.ndarray:
    """The frequencies in Hz of ``head``'s modes when it is tuned to ``freq``."""
    return freq * np.array(head.modes)


def ring_seconds(head: Head, freq: float, decay: float = 1.0) -> float:
    """Seconds the main mode of ``head`` tuned to ``freq`` Hz takes to fall by 60 dB."""
    return head.seconds * (110.0 / freq) ** head.by_pitch * decay


def _contact(head: Head, mallet: float) -> float:
    """The mallet's low-pass in Hz: the softer it is, the longer it stays on the head."""
    low, high = head.contact
    return low * (high / low) ** float(np.clip(mallet, 0.0, 1.0))


def _dying(n: int, seconds: float) -> np.ndarray:
    """A decay by 60 dB in ``seconds``, faded to nothing over its last tenth (``n`` samples)."""
    fall = np.exp(-math.log(1000.0) * np.arange(n) / (seconds * RATE))
    tail = max(n // 10, 1)
    fall[-tail:] *= np.linspace(1.0, 0.0, tail)
    return fall


def _noise(rng: np.random.Generator, n: int, low: float, high: float) -> np.ndarray:
    """``n`` samples of noise between about ``low`` and ``high`` Hz, nothing above 16 kHz."""
    return _filtered(rng.standard_normal(n), lambda f: 1 / np.sqrt(1 + (low / np.maximum(f, 1.0)) ** 4) / np.sqrt(1 + (f / min(high, 12000.0)) ** 6)
                     * np.clip((HIGHEST_PARTIAL - f) / 2000.0, 0.0, 1.0))


def _unit(y: np.ndarray, seconds: float = _LOUD_SECONDS) -> np.ndarray:
    """``y`` with the RMS of its first ``seconds`` set to 1 (a hit shorter than that counts as
    if it filled them: short drums are not made louder to make up for their length), and less
    than that when its peak would pass :data:`_HIGHEST_PEAK`."""
    size = int(seconds * RATE)
    return y / max(math.sqrt(float(np.sum(y[:size] ** 2)) / size), float(np.abs(y).max()) / _HIGHEST_PEAK, 1e-30)


@lru_cache(maxsize=48)
def struck(name: str, freq: float, mallet: float, decay: float, drop: float, edge: float = 0.0, shell: float = 1.0, drum: str = "") -> np.ndarray:
    """One blow on the head ``name`` tuned to ``freq`` Hz, ringing out: mono, read-only, starting
    at exactly 0, its first 0.15 s at RMS 1. ``mallet`` 0 (soft felt) to 1 (hard wood); ``decay``
    times the natural ring; ``drop``: semitones the pitch starts sharp; ``edge`` 0 (struck where
    the low modes are strongest) to 1 (at the rim: the low modes thin, short); ``shell``: level
    of the shell's modes; ``drum``: a text naming this one drum (its modes are up to half a
    percent off the model's, another way for every text)."""
    head = _HEADS[name]
    rng = seeded("drum", name, drum)
    ring = ring_seconds(head, freq, decay) * (1 - 0.6 * edge)
    n = int(min(1.25 * ring * max(head.lasting + (1.0,)), 9.0) * RATE) + int(0.05 * RATE)
    t = np.arange(n) / RATE
    cutoff = _contact(head, mallet)
    # the blow stretches the head: every mode starts sharp by `drop` semitones and settles in about 60 ms
    turns = np.cumsum(2 ** (drop / 12 * np.exp(-t / (0.045 + 4.0 / freq)))) / RATE
    out = np.zeros(n)
    falls = head.falls * (1.5 - float(np.clip(mallet, 0.0, 1.0)))  # a hard blow is short: it wakes the upper modes as much as the lower
    modes = [(m, m**-falls * ((1 - edge) ** (1.5 / m) + edge * 0.5 * min(m, 3.0)), m**-head.dies) for m in head.modes]
    modes[: len(head.lasting)] = [(m, level, share) for (m, level, _), share in zip(modes, head.lasting)]
    modes += list(head.more) + [(m, shell * level, seconds / max(ring, 1e-6)) for m, level, seconds in head.shell]
    for k, (multiple, level, share) in enumerate(modes):
        hz = freq * multiple * (1 + (rng.uniform(-0.005, 0.005) if k and drum else 0.0))
        if hz > HIGHEST_PARTIAL / 1.2:
            continue
        size = min(n, int(1.25 * ring * share * RATE) + 64)
        level = level / (1 + (hz / cutoff) ** 2)
        out[:size] += _SIGNS[k % len(_SIGNS)] * level * np.sin(2 * np.pi * hz * turns[:size]) * _dying(size, ring * share)
    # the mallet's own sound: a knock that is over in milliseconds, and the head's rattle after a hard blow
    level, center = head.knock
    hardness = 0.05 + mallet**1.5
    knock = _noise(rng, n, 0.5 * center * freq * (0.5 + mallet), min(2.5 * cutoff, 12000.0)) * np.exp(-t / (0.008 + 1.0 / cutoff))
    out += level * hardness * knock / max(float(np.abs(knock).max()), 1e-12) * float(np.abs(out).max())
    out *= raised_cosine(n, max(int(0.4 * RATE / cutoff), 8))
    out = _unit(out)
    out.setflags(write=False)
    return out


def _cut(hit: np.ndarray, n: int) -> np.ndarray:
    """``hit`` for ``n`` samples: padded with silence, or cut and damped over the last 70 ms."""
    out = np.zeros((n,) + hit.shape[1:])
    size = min(n, len(hit))
    out[:size] = hit[:size]
    if n < len(hit):
        fade = min(int(_DAMP * RATE), n)
        out[n - fade :] *= (1 - raised_cosine(fade, fade)).reshape((fade,) + (1,) * (hit.ndim - 1))
    return out


def _strokes(n: int, held: int, speed: float, rng: np.random.Generator, grows: float = 0.0, period: float = 0.0) -> np.ndarray:
    """A roll as a train of blows over ``held`` samples of ``n``: ``speed`` blows a second, each
    up to 6 % early or late and the two hands not quite equal; with ``grows`` > 0 the blows start
    at 1 / (1 + 30 * grows) of the last one's force and grow to it. ``period``: the samples of
    one wave of the drum's note: every blow then falls on a whole number of them after the
    first (a blow against the head's motion would stop the drum; a player feels the head)."""
    count = max(int(held / RATE * speed), 1)
    at = (np.arange(count) + np.concatenate([[0.0], rng.uniform(-0.06, 0.06, count - 1)])) * (RATE / speed)
    if period > 0:
        at = np.round(at / period) * period
    force = np.where(np.arange(count) % 2 == 0, 1.0, 0.88) * rng.uniform(0.92, 1.08, count)
    if grows > 0:
        force *= ((1 + 30 * grows) ** (np.minimum(at / max(held, 1), 1.0) - 1))
    train = np.zeros(n)
    np.add.at(train, np.clip(at.astype(np.intp), 0, n - 1), force)
    return train


def _rolled(hit: np.ndarray, train: np.ndarray, held: int = 0) -> np.ndarray:
    """``train`` played on a drum whose single blow is ``hit`` (mono or stereo): each blow adds
    its ring to what still sounds. With ``held`` (samples) the roll's level is set: over the
    last two thirds of its held time it has :data:`_ROLL_LEVEL` times the RMS of the start of
    one blow."""
    n = len(train)
    size = 1 << (n + len(hit) - 1).bit_length()
    out = np.fft.irfft(np.fft.rfft(train, size)[:, None] * np.fft.rfft(hit.reshape(len(hit), -1), size, axis=0), size, axis=0)[:n]
    if held:
        out *= _ROLL_LEVEL / math.sqrt(float(np.mean(out[held // 3 : max(held, 1)] ** 2)) + 1e-30)
    return out.reshape((n,) + hit.shape[1:])


# ----- timpani and toms: played by note name ----------------------------------------------------


def _pitched(head: Head, freq: float, n: int, s: Mapping[str, float], seed: str, drop: float, shell: float) -> np.ndarray:
    hit = struck(head.name, round(freq, 4), s["mallet"], s["decay"], drop, 0.0, shell, seed)
    held = max(n - int(s["ring"] * RATE), 1)
    if int(s.get("stroke", 0.0)) == 1:
        fade = min(int(_DAMP * RATE), n)
        train = _strokes(n, held, s["speed"], seeded("roll", seed, round(freq, 3), n), period=RATE / freq)
        return _rolled(hit, train, held) * (1 - raised_cosine(n, fade, n - fade))
    return _cut(hit, n)


def timpani_note(freq: float, n: int, s: Mapping[str, float], seed: str) -> np.ndarray:
    """A timpano tuned to ``freq`` Hz for ``n`` samples (its held steps and ``ring`` seconds,
    then damped): one blow, or with ``stroke`` 1 a roll over the held steps."""
    return _pitched(TIMPANO, freq, n, s, seed, 0.12 * (0.5 + s["mallet"]), 0.0)


def toms_note(freq: float, n: int, s: Mapping[str, float], seed: str) -> np.ndarray:
    """A concert tom tuned to ``freq`` Hz for ``n`` samples."""
    return _pitched(TOM, freq, n, s, seed, s["drop"], s["shell"])


# ----- big drums: played as drum steps -----------------------------------------------------------


def _ensemble(make: Callable[[int], np.ndarray], players: int, apart: float, name: str) -> np.ndarray:
    """``players`` drums together: ``make(k)`` is player ``k``'s blow (mono); each up to
    ``apart`` seconds late, up to 1.5 dB off, spread from left to right; the energy of one drum
    (stereo ``(n, 2)``; one player is mono, on time)."""
    if players <= 1:
        return np.array(make(0))
    rng = seeded("ensemble", name, players)
    late = (rng.uniform(0.0, apart, players) * RATE).astype(np.intp)
    late -= late.min()
    hits = [make(k) for k in range(players)]
    out = np.zeros((max(len(h) + int(d) for h, d in zip(hits, late)), 2))
    places = rng.permutation(np.linspace(-1.0, 1.0, players))
    for hit, delay, place in zip(hits, late, places):
        angle = (0.7 * place + 1) * math.pi / 4
        gain = 10 ** (rng.uniform(-1.5, 1.5) / 20) * math.sqrt(2 / players)
        out[int(delay) : int(delay) + len(hit)] += hit[:, None] * (gain * np.array([math.cos(angle), math.sin(angle)]))
    # drums a few milliseconds apart add up by chance: the ensemble's energy is set to one drum's
    return out * math.sqrt(float(np.sum(hits[0] ** 2)) / (0.5 * float(np.sum(out**2)) + 1e-30))


@lru_cache(maxsize=16)
def _big(name: str, pitch: float, mallet: float, decay: float, drop: float, edge: float, players: int, apart: float) -> np.ndarray:
    """A big drum or an ensemble of them, each player's drum up to 3 % higher or lower."""
    tuning = seeded("tuning", name).uniform(-0.03, 0.03, 16)
    out = _ensemble(lambda k: struck(name, round(pitch * (1 + (tuning[k] if players > 1 else 0.0)), 4), mallet, decay, drop, edge, 1.0, f"player {k}"),
                    players, apart, name)
    out.setflags(write=False)
    return out


def taiko_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    """A taiko (or an ensemble of them): a hard stick on a thick head over a barrel."""
    return _big(TAIKO.name, s["pitch"], s["mallet"], s["decay"], s["drop"], 0.0, int(round(s["players"])), s["apart"])


def bass_drum_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    """A concert bass drum (gran cassa): a soft beater on a wide, slack head."""
    return _big(BASS_DRUM.name, s["pitch"], s["mallet"], s["decay"], 0.5, 0.0, int(round(s["players"])), s["apart"])


def frame_drum_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    """A frame drum played by hand: one head on a hoop, no shell."""
    return _big(FRAME_DRUM.name, s["pitch"], s["mallet"], s["decay"], 0.6, s["edge"], int(round(s["players"])), s["apart"])


@lru_cache(maxsize=16)
def _snare_hit(pitch: float, mallet: float, snares: float, decay: float, player: int) -> np.ndarray:
    """One blow on a snare drum: the head (short) and the snare wires under it rattling, a noise
    of 1 to 6 kHz that dies in ``0.16 * decay`` s; mono, the first 0.15 s at RMS 1."""
    head = struck(SNARE.name, pitch, mallet, decay, 0.3, 0.0, 1.0, f"player {player}")
    n = int((0.45 * decay + 0.1) * RATE)
    t = np.arange(n) / RATE
    rng = seeded("snares", player)
    wires = _noise(rng, n, 900.0, 5000.0 * (0.6 + 0.8 * mallet)) * (0.25 * np.exp(-t / (0.016 * decay)) + np.exp(-t / (0.055 * decay))) * raised_cosine(n, int(0.0015 * RATE))
    out = np.zeros(max(n, len(head)))
    out[: len(head)] += 0.35 * head
    out[:n] += 1.6 * snares * wires / math.sqrt(float(np.sum(wires**2)) / (_LOUD_SECONDS * RATE))
    return _unit(out)


@lru_cache(maxsize=8)
def _snare(pitch: float, mallet: float, snares: float, decay: float, players: int, apart: float, roll: bool, speed: float, held: int) -> np.ndarray:
    def player(k: int) -> np.ndarray:
        hit = _snare_hit(round(pitch * (1 + (0.02 * (2 * k / (players - 1) - 1) if players > 1 else 0.0)), 3), mallet, snares, decay, k)
        if not roll:
            return hit
        n = held + len(hit)
        # a snare's blow is over in a tenth of a second, its roll is not: the roll a little lower, or it would be far louder than the blows
        return 0.6 * _rolled(hit, _strokes(n, held, speed * (1 + 0.07 * k / max(players, 1)), seeded("snare roll", k, held)), held)

    out = _ensemble(player, players, apart, "snare")
    out.setflags(write=False)
    return out


def snare_drum_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    """An orchestral snare drum (or a line of them): one blow, or with ``stroke`` 1 a roll for
    its held steps."""
    roll = int(s["stroke"]) == 1
    return _snare(s["pitch"], s["mallet"], s["snares"], s["decay"], int(round(s["players"])), s["apart"], roll, s["speed"], int(held * RATE) if roll else 0)


# ----- metal ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Metal:
    """A cymbal or gong. ``lowest``: Hz of its lowest mode at ``pitch`` 1; ``single``: how many
    modes are made one by one, up to ``dense`` Hz (above, bands of noise); ``seconds``: the 60 dB
    time at 1 kHz, shorter for higher partials by ``faster`` (the power of the frequency);
    ``tilt``: the power by which the blow's spectrum falls with frequency; ``bloom``: seconds
    the upper bands take to arrive after the blow (0: at once) and by how much they grow."""

    name: str
    lowest: float
    single: int
    dense: float
    seconds: float
    faster: float
    tilt: float
    bloom: tuple[float, float]


CYMBAL = Metal("cymbal", 310.0, 36, 2600.0, 7.0, 0.25, -0.5, (0.0, 0.0))
TAM_TAM = Metal("tam-tam", 58.0, 44, 900.0, 8.0, 0.4, 0.6, (0.7, 3.0))
_BANDS = 14


@lru_cache(maxsize=6)
def clanged(name: str, pitch: float, mallet: float, decay: float, bloom: float = 1.0) -> np.ndarray:
    """One blow on the metal ``name``, ringing out: stereo ``(n, 2)``, read-only, the loudest
    0.4 s at RMS 1 (a swell's too). The modes of a plate are not harmonic and lie ever closer: the lowest
    ``single`` are sines (fixed for the instrument, at ``lowest * pitch`` and above, the same
    every time), the rest bands of noise up to 14 kHz, every band with its own decay."""
    metal = _METALS[name]
    rng = seeded("metal", name)
    lowest = metal.lowest * pitch
    dense = metal.dense * pitch
    ring = metal.seconds * decay
    n = int(min(1.1 * ring * (1000.0 / lowest) ** metal.faster, 10.0) * RATE)
    t = np.arange(n) / RATE
    cutoff = 20 * lowest ** 0.6 * 20.0 ** float(np.clip(mallet, 0.0, 1.0))
    grows, more = metal.bloom

    def shape(hz: float, size: int) -> np.ndarray:
        """A partial's level over time: the blow's share of it, its decay, and the bloom."""
        seconds = ring * (1000.0 / hz) ** metal.faster
        level = (lowest / hz) ** metal.tilt / math.sqrt(1 + (hz / cutoff) ** 2)
        late = bloom * more * min(hz / dense, 4.0) ** 1.5 * (lowest / hz) ** metal.tilt if grows else 0.0
        arrives = (1 - np.exp(-t[:size] / (grows * (0.4 + min(hz / dense, 3.0)) / 2))) ** 2 if grows else 0.0
        return (level + late * arrives) * _dying(size, seconds)

    out = np.zeros((n, 2))
    # the single modes: spaced as a plate's (ever closer in pitch), each a little to one side
    hzs = lowest * (dense / lowest) ** (((np.arange(metal.single) + rng.uniform(0.15, 0.85, metal.single)) / metal.single) ** 0.8)
    hzs[0] = lowest
    for hz in hzs:
        size = min(n, int(1.1 * ring * (1000.0 / hz) ** metal.faster * RATE))
        partial = np.sin(2 * np.pi * (hz * t[:size] + rng.uniform())) * shape(float(hz), size) * raised_cosine(size, int(0.002 * RATE))
        place = rng.uniform(0.25, 0.75) * math.pi / 2
        out[:size] += partial[:, None] * (math.sqrt(2) * np.array([math.cos(place), math.sin(place)]))
    # the dense part: bands of noise (random spectra between the band's edges), each side its own
    edges = dense * (14000.0 / dense) ** np.linspace(0.0, 1.0, _BANDS + 1)
    # a plate's modes lie closer the higher they are: a band holds more of them than the same span among the single ones
    per_band = 2.5 * math.sqrt(metal.single / math.log(dense / lowest) * math.log(edges[1] / edges[0]))
    for low, high in zip(edges, edges[1:]):
        center = math.sqrt(low * high)
        length = min(n, int(1.1 * ring * (1000.0 / center) ** metal.faster * RATE))
        size = 1 << (length - 1).bit_length()
        first, last = int(low * size / RATE), max(int(high * size / RATE), int(low * size / RATE) + 1)
        level = shape(center, length) * raised_cosine(length, int(0.002 * RATE))
        for side in range(2):
            spectrum = np.zeros(size // 2 + 1, dtype=np.complex128)
            spectrum[first:last] = rng.standard_normal(last - first) + 1j * rng.standard_normal(last - first)
            band = np.fft.irfft(spectrum, size)[:length]
            out[:length, side] += band * (per_band / math.sqrt(2 * float(np.mean(band**2)) + 1e-30)) * level
    out = _loudest_unit(out)
    out.setflags(write=False)
    return out


def _loudest_unit(out: np.ndarray) -> np.ndarray:
    """Stereo ``out`` with its loudest 0.4 s at RMS 1 (the two sides' mean power)."""
    window = int(_METAL_SECONDS * RATE)
    total = np.concatenate([[0.0], np.cumsum(0.5 * np.sum(out**2, axis=1))])
    return out / math.sqrt(float((total[window:] - total[:-window]).max()) / window + 1e-30)


_METALS = {metal.name: metal for metal in (CYMBAL, TAM_TAM)}


@lru_cache(maxsize=6)
def _metal(name: str, pitch: float, mallet: float, decay: float, bloom: float, swell: bool, speed: float, held: int) -> np.ndarray:
    hit = clanged(name, pitch, mallet, decay, bloom)
    if not swell:
        return hit
    # a roll with soft mallets that grows until the held steps end: the soft blows' ring first, the harder ones' on top
    n = held + len(hit)
    rng = seeded("swell", name, held)
    soft = clanged(name, pitch, max(mallet - 0.35, 0.0), decay, bloom)
    out = 0.6 * _rolled(soft, _strokes(n, held, speed, rng, 0.5)) + 0.8 * _rolled(hit, _strokes(n, held, speed, rng, 3.0))
    out = _loudest_unit(out * raised_cosine(n, int(0.05 * RATE))[:, None])
    out.setflags(write=False)
    return out


def cymbal_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    """A suspended cymbal: one blow, or with ``stroke`` 1 a mallet roll swelling until its held
    steps end and ringing out after them."""
    swell = int(s["stroke"]) == 1
    return _metal(CYMBAL.name, s["pitch"], s["mallet"], s["decay"], 0.0, swell, s["speed"], int(held * RATE) if swell else 0)


def tam_tam_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    """A tam-tam (a large flat gong): one blow whose highs arrive after it, or a swell."""
    swell = int(s["stroke"]) == 1
    return _metal(TAM_TAM.name, s["pitch"], s["mallet"], s["decay"], s["bloom"], swell, s["speed"], int(held * RATE) if swell else 0)
