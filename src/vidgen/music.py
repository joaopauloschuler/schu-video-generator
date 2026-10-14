"""Background music (DESIGN.md §48, §69.63, §82, §83): five procedurally generated beds, the
project's own music files, composed music (:mod:`vidgen.composer`, played by
:mod:`vidgen.synth`), and the sources the mix reads from.

A *bed* is a seamless loop made of a chord progression (numpy only, no recordings, no samples,
deterministic): sustained pads are built with the PADsynth method (Nasca Octavian
Paul's algorithm, from ZynAddSubFX) — each chord's
harmonics as narrow Gaussian bumps of a spectrum with seeded random phases, turned into a
periodic wave by one inverse FFT — and cross-faded from chord to chord; plucked arpeggios,
pizzicato strings, bells, music-box tines and woodblocks are added note by note. Everything is rendered *circularly* (notes running past the loop's
end continue at its start; the final filtering is a circular FFT filter), so the loop repeats
without a seam. The loop is set to :data:`MUSIC_LEVEL` integrated loudness.

A *file* (any format FFmpeg reads, decoded with PyAV) is matched to the same loudness; it can
start later (``start``) and loop with a cross-faded seam (``crossfade``).
"""

from __future__ import annotations

import logging
import math
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.loudness import integrated_loudness
from vidgen.sfx import RATE, _band, _filtered, _highpass, _lowpass, decode_audio, write_wav

if TYPE_CHECKING:
    from vidgen.config import MusicCue, VideoConfig
    from vidgen.score import Score

log = logging.getLogger("vidgen.music")

#: Integrated loudness (LUFS) of the music at ``volume: 0``, before ducking: a bed or a file is
#: set to this level. ElevenLabs narration plays at about -21.4 LUFS integrated in a rendered
#: video (its MP3s' level: mono files play on both channels unchanged), so music sits ~6.5 dB
#: under the voice in pauses and, ducked by 12 dB, ~18.5 dB under it while it speaks.
MUSIC_LEVEL = -28.0
#: Suggested folder of the project's music files (any path under the project works).
PROJECT_MUSIC_DIR = Path("assets") / "music"
#: Suffixes listed by ``vidgen list-music`` as the project's music files.
MUSIC_SUFFIXES = (".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".opus", ".webm")


# ----- synthesis helpers ---------------------------------------------------------------------------


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _pad_wave(
    notes: Sequence[float], n: int, rng: np.random.Generator, harmonics: Sequence[float], width_cents: float, lowpass: float
) -> np.ndarray:
    """A periodic wave of ``n`` samples (PADsynth): every note's harmonics (amplitudes
    ``harmonics``, shaped by :func:`_shape`) as Gaussian bumps ``width_cents`` wide with random
    phases, one inverse FFT; RMS 1."""
    step = RATE / n
    spectrum = np.zeros(n // 2 + 1, dtype=np.complex128)
    for note in notes:
        f0 = _hz(note)
        for h, amp in enumerate(harmonics, start=1):
            f = f0 * h
            if f > lowpass * 2:
                break
            sigma = max(f * (2 ** (width_cents / 1200) - 1) / 2, step)
            lo, hi = int((f - 4 * sigma) / step), int((f + 4 * sigma) / step) + 2
            k = np.arange(max(lo, 1), min(hi, len(spectrum)))
            bump = np.exp(-0.5 * ((k * step - f) / sigma) ** 2) / math.sqrt(sigma)
            spectrum[k] += amp * bump * _shape(f, lowpass) * np.exp(1j * rng.uniform(0, 2 * np.pi, len(k)))
    wave = np.fft.irfft(spectrum, n)
    return wave / max(float(np.sqrt(np.mean(wave**2))), 1e-12)


def _shape(freq: float, lowpass: float) -> float:
    """The beds' tone shaping: a high-pass at 40 Hz and a gentle low-pass at ``lowpass`` Hz
    (second order each), so nothing is boomy or harsh."""
    f = np.array([freq])
    return float((_highpass(f, 40.0, 2) * _lowpass(f, lowpass, 2))[0])


def _xfade_window(seg: int, fade: int) -> np.ndarray:
    """The envelope of one chord over ``seg + fade`` samples starting ``fade / 2`` before its
    segment: equal-power fades of ``fade`` samples centred on the segment's boundaries, so
    neighbouring chords cross-fade."""
    u = np.clip((np.arange(seg + fade) + 0.5) / fade, 0.0, 1.0)
    rise = np.sin(0.5 * np.pi * u)
    return rise * rise[::-1]


def _circular_add(out: np.ndarray, start: int, data: np.ndarray) -> None:
    """Add ``data`` to ``out`` from ``start`` on, continuing at the beginning past its end."""
    total = len(out)
    start %= total
    first = min(len(data), total - start)
    out[start : start + first] += data[:first]
    rest = data[first:]
    while len(rest):
        part = rest[:total]
        out[: len(part)] += part
        rest = rest[total:]


@lru_cache(maxsize=256)
def _partials(freq: float, n: int, tau: float, attack: float, partials: tuple[tuple[float, float, float], ...], lowpass: float) -> np.ndarray:
    """A struck / plucked note: ``(ratio, amplitude, decay share)`` partials of ``freq`` shaped
    by :func:`_shape`, an exponential ``attack``, decays ``tau * share`` and a 30 ms fade at the
    end (so it ends at exactly zero)."""
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for ratio, amp, share in partials:
        out += amp * _shape(freq * ratio, lowpass) * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t / (tau * share))
    env = 1 - np.exp(-t / attack)
    tail = min(n, int(0.03 * RATE))
    env[n - tail :] *= np.linspace(1, 0, tail)
    note = out * env
    note.setflags(write=False)
    return note


def _pluck(freq: float, n: int, tau: float, bright: float, lowpass: float) -> np.ndarray:
    """A soft plucked note: a sine with a little second / third harmonic, 4 ms attack."""
    return _partials(freq, n, tau, 0.004, ((1.0, 1.0, 1.0), (2.0, 0.25 * bright, 0.6), (3.0, 0.08 * bright, 0.4)), lowpass)


def _bell(freq: float, n: int, tau: float, lowpass: float) -> np.ndarray:
    """A soft bell (glockenspiel-like): 2 ms strike, two quiet overtones."""
    return _partials(freq, n, tau, 0.002, ((1.0, 1.0, 1.0), (2.0, 0.28, 0.55), (3.0, 0.07, 0.35)), lowpass)


def _pizzicato(freq: float, n: int, tau: float, lowpass: float) -> np.ndarray:
    """A plucked string (pizzicato): 3 ms attack, a woody body of five harmonics, the upper ones
    dying first."""
    partials = ((1.0, 1.0, 1.0), (2.0, 0.45, 0.55), (3.0, 0.22, 0.4), (4.0, 0.1, 0.3), (5.0, 0.05, 0.25))
    return _partials(freq, n, tau, 0.003, partials, lowpass)


def _music_box(freq: float, n: int, tau: float, lowpass: float) -> np.ndarray:
    """A music-box tine: 1.5 ms strike, a second tine 3.5 cents sharp (a slow shimmer of beats), a
    faint octave and a short inharmonic ping at 5.4 times the pitch."""
    partials = ((1.0, 1.0, 1.0), (1.002, 0.3, 0.9), (2.0, 0.1, 0.4), (5.4, 0.04, 0.08))
    return _partials(freq, n, tau, 0.0015, partials, lowpass)


def _woodblock(freq: float, lowpass: float) -> np.ndarray:
    """A small woodblock tock (60 ms): a hollow tone with an inharmonic partial, 0.5 ms strike."""
    return _partials(freq, int(0.06 * RATE), 0.018, 0.0005, ((1.0, 1.0, 1.0), (2.76, 0.3, 0.5)), lowpass)


def _tick(rng: np.random.Generator) -> np.ndarray:
    """A soft snare-like tick (80 ms): a noise burst around 2.2 kHz, nothing above ~3.5 kHz."""
    t = np.arange(int(0.08 * RATE)) / RATE
    burst = rng.standard_normal(len(t)) * np.exp(-t / 0.018) * (1 - np.exp(-t / 0.0008))
    tick = _filtered(burst, lambda f: _band(f, 2200.0, 0.7) * _lowpass(f, 3500.0, 4))
    tick[-int(0.01 * RATE) :] *= np.linspace(1, 0, int(0.01 * RATE))
    return tick / np.abs(tick).max()


def _add_panned(out: np.ndarray, start: int, sound: np.ndarray, pan: float) -> None:
    """Add a mono ``sound`` to stereo ``out`` at ``start`` (circularly), ``pan`` -1 (left) to 1."""
    for c, side in enumerate((1 - pan, 1 + pan)):
        _circular_add(out[:, c], start, sound * side)


# ----- the beds ------------------------------------------------------------------------------------

#: Harmonic amplitudes of the pads: warm (falls fast) and airy (more upper partials).
_WARM = tuple(1.0 / h**1.6 for h in range(1, 9))
_AIRY = tuple(1.0 / h**1.1 for h in range(1, 13))


@dataclass(frozen=True)
class Bed:
    """A built-in music bed: its generator, loop length, musical facts and a precise textual
    description (for authors who cannot listen) and when to use it."""

    name: str
    generate: Callable[[np.random.Generator], np.ndarray]
    seconds: float
    tempo: int | None
    key: str
    chords: tuple[str, ...]
    description: str
    use: str


def _pads(
    chords: Sequence[Sequence[int]], bass: Sequence[int], seg: int, table: int, rng: np.random.Generator, air: float, air_cycles: int, lowpass: float
) -> np.ndarray:
    """Stereo ``(len(chords) * seg, 2)``: a warm pad of each chord (independent phases per
    channel: wide), a softer airy layer an octave up whose level swells ``air_cycles`` times
    per loop, and a sub-bass on each chord's ``bass`` note, cross-faded chord to chord. The
    waves repeat every ``table`` samples (a divisor of ``seg``), so they continue across the
    loop's end."""
    count = len(chords)
    total = count * seg
    fade = 2 * int(0.8 * RATE)
    env = _xfade_window(seg, fade)
    out = np.zeros((total, 2))
    for i, (notes, root) in enumerate(zip(chords, bass)):
        first = i * seg - fade // 2
        t = first + np.arange(seg + fade)
        idx = t % table
        swell = air * (0.5 - 0.5 * np.cos(2 * np.pi * air_cycles * t / total))
        sub = 0.55 * _pad_wave([root], table, rng, (1.0, 0.15), 4.0, lowpass)[idx]
        for c in range(2):
            warm = _pad_wave(notes, table, rng, _WARM, 18.0, lowpass)[idx]
            airy = _pad_wave([n + 12 for n in notes[1:]], table, rng, _AIRY, 30.0, lowpass)[idx]
            _circular_add(out[:, c], first, env * (warm + swell * airy + sub))
    return out


def _finish(x: np.ndarray) -> np.ndarray:
    """The level (:data:`MUSIC_LEVEL` integrated loudness); float32, read-only."""
    y = x * 10 ** ((MUSIC_LEVEL - integrated_loudness(x)) / 20)
    out = y.astype(np.float32)
    out.setflags(write=False)
    return out


def _calm(rng: np.random.Generator) -> np.ndarray:
    lowpass = 3800.0
    seg = int(7.5 * RATE)
    chords = (
        (50, 57, 61, 64, 66),  # Dmaj9
        (47, 54, 57, 61, 62),  # Bm(add9)
        (55, 59, 62, 66, 69),  # Gmaj9
        (52, 57, 59, 64, 66),  # A6sus2 (E A B E F#)
        (54, 57, 61, 64, 69),  # D/F#
        (52, 55, 59, 62, 66),  # Em9
        (55, 59, 62, 66, 73),  # Gmaj7#11 colour (C# on top)
        (52, 57, 62, 64, 69),  # Asus4
    )
    bass = (38, 35, 43, 45, 42, 40, 43, 45)
    pads = _pads(chords, bass, seg, seg // 3, rng, air=0.35, air_cycles=2, lowpass=lowpass)
    return _finish(pads)


def _arpeggio(
    out: np.ndarray, chords: Sequence[Sequence[int]], seg: int, step: int, rng: np.random.Generator, octave: int, tau: float, bright: float, level: float, lowpass: float
) -> None:
    """Plucked eighth notes (``step`` samples apart) through each chord's tones, a pattern per
    bar chosen by ``rng``; alternate notes slightly left / right."""
    patterns = ((0, 1, 2, 3, 4, 3, 2, 1), (0, 2, 1, 3, 2, 4, 3, 1), (0, 1, 2, 4, 3, 2, 1, 2), (4, 3, 2, 1, 0, 1, 2, 3))
    length = int(tau * 5 * RATE)
    for i, notes in enumerate(chords):
        tones = sorted(n + 12 * octave for n in notes)
        for bar_start in range(i * seg, (i + 1) * seg, step * 8):
            pattern = patterns[int(rng.integers(len(patterns)))]
            for k, idx in enumerate(pattern):
                accent = 1.0 if k % 2 == 0 else 0.72
                note = _pluck(_hz(tones[idx % len(tones)]), length, tau, bright, lowpass) * level * accent
                pan = 0.25 if k % 2 else -0.25
                for c, side in enumerate((1 - pan, 1 + pan)):
                    _circular_add(out[:, c], bar_start + k * step, note * side)


def _pulse(rng: np.random.Generator) -> np.ndarray:
    lowpass = 3500.0
    beat = RATE * 60 // 96  # 96 BPM
    seg = 8 * beat  # two bars per chord
    chords = (
        (57, 60, 64, 67, 71),  # Am9
        (53, 57, 60, 64, 67),  # Fmaj9
        (48, 55, 60, 62, 64),  # Cadd9
        (55, 59, 62, 64, 69),  # G6/9
        (57, 60, 64, 67, 72),  # Am7
        (53, 57, 60, 64, 69),  # Fmaj7(add13)
        (50, 57, 60, 62, 65),  # Dm9-ish
        (52, 57, 59, 64, 68),  # E7sus4 -> E
    )
    bass = (45, 41, 48, 43, 45, 41, 38, 40)
    out = 0.55 * _pads(chords, bass, seg, seg // 2, rng, air=0.2, air_cycles=1, lowpass=lowpass)
    _arpeggio(out, chords, seg, beat // 2, rng, octave=0, tau=0.22, bright=0.6, level=0.55, lowpass=lowpass)
    for i, root in enumerate(bass):  # a soft low pulse on every beat, stronger on 1 and 3
        thump = _pluck(_hz(root), int(0.5 * RATE), 0.16, 0.3, lowpass)
        for k in range(8):
            for c in range(2):
                _circular_add(out[:, c], i * seg + k * beat, thump * (0.7 if k % 2 == 0 else 0.4))
    return _finish(out)


def _bright(rng: np.random.Generator) -> np.ndarray:
    lowpass = 4500.0
    beat = RATE * 60 // 120  # 120 BPM
    seg = 8 * beat  # two bars per chord
    chords = (
        (60, 64, 67, 71, 74),  # Cmaj9
        (59, 62, 67, 69, 74),  # G/B (add9)
        (57, 64, 67, 72, 76),  # Am7
        (53, 60, 64, 65, 69),  # Fmaj7
        (60, 64, 67, 72, 74),  # Cadd9
        (55, 62, 67, 71, 74),  # G
        (57, 60, 64, 67, 71),  # Am9
        (53, 57, 64, 67, 72),  # Fmaj7/9
        (50, 57, 60, 65, 69),  # Dm7
        (55, 59, 62, 67, 74),  # G
        (52, 59, 62, 67, 71),  # Em7
        (53, 60, 65, 69, 72),  # F (sus-ish) back to C
    )
    bass = (48, 47, 45, 41, 48, 43, 45, 41, 38, 43, 40, 41)
    out = 0.6 * _pads(chords, bass, seg, seg // 2, rng, air=0.5, air_cycles=3, lowpass=lowpass)
    _arpeggio(out, chords, seg, beat // 2, rng, octave=1, tau=0.18, bright=0.5, level=0.42, lowpass=lowpass)
    # a sparse bell melody: a chord tone two octaves up on beats 1 and 3, some rests
    length = int(1.6 * RATE)
    for i, notes in enumerate(chords):
        tones = sorted(n + 24 for n in notes[1:])
        for k in range(0, 8, 2):
            if rng.random() < 0.3:
                continue
            note = _bell(_hz(tones[int(rng.integers(len(tones)))]), length, 0.5, lowpass) * 0.22
            for c, side in enumerate((0.85, 1.15) if k % 4 else (1.15, 0.85)):
                _circular_add(out[:, c], i * seg + k * beat, note * side)
    return _finish(out)


@dataclass(frozen=True)
class _CartoonBar:
    """One bar of the ``cartoon`` bed: its chord, the chord's voicing (pad and off-beat stabs),
    the bass on beats 1 and 3 (and an optional pickup on the last eighth) and the melody in
    eighth-note slots (``None``: rest)."""

    chord: str
    voicing: tuple[int, ...]
    bass: tuple[int, int, int | None]
    melody: tuple[int | None, ...]


_ = None  # a rest in the melodies below
_G, _C, _D7 = (55, 59, 62, 67), (55, 60, 64, 67), (54, 57, 60, 62)
_EM, _A7, _AM = (55, 59, 64, 67), (55, 57, 61, 64), (57, 60, 64, 69)
#: Six four-bar phrases in G major: A, A' (to the dominant), B (syncopated, lower), A an octave
#: up, C (call and response with the woodblocks), a turnaround back to the top.
_CARTOON_BARS = (
    _CartoonBar("G", _G, (43, 50, _), (74, _, 79, _, 78, 79, 81, _)),
    _CartoonBar("C", _C, (48, 43, _), (79, _, 76, _, 72, _, 76, 79)),
    _CartoonBar("D7", _D7, (38, 45, _), (78, _, 81, 78, 74, _, 72, _)),
    _CartoonBar("G", _G, (43, 50, 42), (71, 74, 79, _, 79, _, _, 74)),
    _CartoonBar("G", _G, (43, 50, _), (74, _, 79, _, 78, 79, 83, _)),
    _CartoonBar("Em", _EM, (40, 47, _), (83, _, 79, _, 76, _, 79, 83)),
    _CartoonBar("A7", _A7, (45, 40, _), (81, _, 85, 81, 79, _, 76, _)),
    _CartoonBar("D7", _D7, (38, 45, 47), (78, _, 74, _, 72, 74, 78, 81)),
    _CartoonBar("C", _C, (48, 43, _), (76, _, _, 72, 79, _, _, 76)),
    _CartoonBar("G/B", _G, (47, 43, _), (74, _, _, 71, 79, _, _, 74)),
    _CartoonBar("Am", _AM, (45, 52, _), (72, _, 76, _, 81, _, 79, 76)),
    _CartoonBar("D7", _D7, (38, 45, 42), (78, _, 74, _, 81, 79, 78, 76)),
    _CartoonBar("G", _G, (43, 50, _), (79, _, 83, _, 81, 83, 86, _)),
    _CartoonBar("C", _C, (48, 43, _), (84, _, 79, _, 76, _, 79, 84)),
    _CartoonBar("D7", _D7, (38, 45, _), (81, _, 84, 81, 78, _, 74, _)),
    _CartoonBar("G", _G, (43, 50, 47), (79, _, _, _, 71, _, 74, _)),
    _CartoonBar("Em", _EM, (40, 47, _), (71, 74, 76, _, _, _, _, _)),
    _CartoonBar("Am", _AM, (45, 52, _), (72, 76, 81, _, _, _, _, _)),
    _CartoonBar("D7", _D7, (38, 45, _), (78, 81, 84, _, 81, _, 78, _)),
    _CartoonBar("G", _G, (43, 50, 47), (79, _, 74, _, 71, _, _, _)),
    _CartoonBar("C", _C, (48, 43, _), (76, _, 79, 76, 72, _, 76, _)),
    _CartoonBar("D7", _D7, (38, 45, _), (78, _, 81, 78, 74, _, 78, _)),
    _CartoonBar("G", _G, (43, 50, _), (79, _, 74, _, 71, 74, 79, _)),
    _CartoonBar("D7", _D7, (38, 45, 42), (81, _, 78, _, 74, 76, 78, 76)),
)
#: Percussion per phrase, as eighth-note slots: (soft ticks, high woodblock, low woodblock).
_CARTOON_PERCUSSION = (
    ((2, 6), (7,), ()),
    ((2, 6), (3, 7), (5,)),
    ((6,), (), (3,)),
    ((2, 6), (3, 7), (5,)),
    ((2,), (4, 5), (6, 7)),
    ((2, 6), (7,), (3,)),
)


def _cartoon(rng: np.random.Generator) -> np.ndarray:
    lowpass = 4200.0
    beat = RATE * 60 // 128  # 128 BPM
    step = beat // 2
    seg = 4 * beat  # a chord per bar
    bars = _CARTOON_BARS
    out = 0.1 * _pads([b.voicing for b in bars], [b.bass[0] for b in bars], seg, seg // 2, rng, air=0.15, air_cycles=1, lowpass=lowpass)
    tick, wood_high, wood_low = _tick(rng), _woodblock(1250.0, lowpass), _woodblock(880.0, lowpass)
    for i, bar in enumerate(bars):
        start = i * seg
        for k, note in enumerate(bar.melody):
            if note is not None:
                accent = 1.0 if k % 2 == 0 else 0.8
                _add_panned(out, start + k * step, _pizzicato(_hz(note), int(1.2 * RATE), 0.2, lowpass) * 0.55 * accent, 0.2)
        for k, note in zip((0, 4, 7), bar.bass):
            if note is not None:
                _add_panned(out, start + k * step, _pizzicato(_hz(note), int(1.5 * RATE), 0.32, lowpass) * (0.8 if k < 7 else 0.5), 0.0)
        for k in (2, 6):  # "oom-pah": a short pizzicato chord on beats 2 and 4
            for n, note in enumerate(bar.voicing[1:]):
                _add_panned(out, start + k * step + 60 * n, _pizzicato(_hz(note), int(0.6 * RATE), 0.1, lowpass) * 0.2, -0.35)
        ticks, high, low = _CARTOON_PERCUSSION[i // 4]
        if i % 4 == 3:  # each phrase ends with a woodblock fill
            ticks, high, low = (2,), (5, 7), (6,)
        for k in ticks:
            _add_panned(out, start + k * step, tick * 0.25, 0.0)
        for k in high:
            _add_panned(out, start + k * step, wood_high * 0.4, 0.4)
        for k in low:
            _add_panned(out, start + k * step, wood_low * 0.4, -0.4)
    return _finish(out)


@dataclass(frozen=True)
class _LullabyBar:
    """One bar of 3/4 of the ``lullaby`` bed: its chord, voicing (pad and music-box
    accompaniment), bass note and melody as ``(note, beats)``."""

    chord: str
    voicing: tuple[int, ...]
    bass: int
    melody: tuple[tuple[int, int], ...]


_F, _BB, _C7, _GM7 = (53, 57, 60, 65), (53, 58, 62, 65), (52, 55, 58, 60), (53, 58, 62, 67)
#: Four 4-bar phrases in F major ending on C7, which leads back to the top.
_LULLABY_BARS = (
    _LullabyBar("F", _F, 41, ((81, 2), (79, 1))),
    _LullabyBar("Bb/F", _BB, 41, ((77, 1), (82, 1), (81, 1))),
    _LullabyBar("F", _F, 41, ((84, 2), (81, 1))),
    _LullabyBar("C7", _C7, 36, ((79, 2), (76, 1))),
    _LullabyBar("F", _F, 41, ((77, 1), (81, 1), (84, 1))),
    _LullabyBar("Dm", (53, 57, 62, 65), 38, ((86, 2), (84, 1))),
    _LullabyBar("Gm7", _GM7, 43, ((82, 1), (81, 1), (79, 1))),
    _LullabyBar("C7", _C7, 36, ((79, 3),)),
    _LullabyBar("Bb", _BB, 46, ((77, 1), (82, 1), (86, 1))),
    _LullabyBar("F/A", _F, 45, ((84, 1), (81, 1), (77, 1))),
    _LullabyBar("Gm7", _GM7, 43, ((82, 1), (79, 1), (77, 1))),
    _LullabyBar("C7", _C7, 36, ((76, 2), (79, 1))),
    _LullabyBar("F", _F, 41, ((81, 2), (84, 1))),
    _LullabyBar("Dm7", (53, 57, 60, 62), 38, ((86, 1), (84, 1), (81, 1))),
    _LullabyBar("Gm7", _GM7, 43, ((82, 2), (79, 1))),
    _LullabyBar("C7", _C7, 36, ((76, 2), (72, 1))),
)
#: Broken-chord patterns (indices into the voicing an octave up) in eighths, one per phrase.
_LULLABY_PATTERNS = ((0, 2, 1, 2, 3, 2), (0, 1, 2, 3, 2, 1), (0, 2, 1, 2, 3, 2), (0, 2, 3, 2, 1, 2))


def _lullaby(rng: np.random.Generator) -> np.ndarray:
    lowpass = 3600.0
    beat = RATE * 60 // 64  # 64 BPM
    seg = 3 * beat  # a chord per bar of 3/4
    bars = _LULLABY_BARS
    out = 0.22 * _pads([b.voicing for b in bars], [b.bass for b in bars], seg, seg // 3, rng, air=0.3, air_cycles=2, lowpass=lowpass)
    for i, bar in enumerate(bars):
        start = i * seg
        _add_panned(out, start, _pluck(_hz(bar.bass), int(2.5 * RATE), 0.9, 0.2, lowpass) * 0.45, 0.0)
        tones = [n + 12 for n in bar.voicing]
        for k, idx in enumerate(_LULLABY_PATTERNS[i // 4]):
            level = 0.2 if k == 0 else 0.14
            _add_panned(out, start + k * beat // 2, _music_box(_hz(tones[idx]), int(2.0 * RATE), 0.7, lowpass) * level, -0.25)
        at = start
        for note, beats in bar.melody:
            _add_panned(out, at, _music_box(_hz(note), int(3.0 * RATE), 1.3, lowpass) * 0.42, 0.2)
            at += beats * beat
    return _finish(out)


#: The built-in beds, in listing order.
BUILTIN_BEDS: dict[str, Bed] = {
    b.name: b
    for b in (
        Bed(
            "calm", _calm, 60.0, None, "D major",
            ("Dmaj9", "Bm(add9)", "Gmaj9", "A6sus2", "D/F#", "Em9", "Gmaj7#11", "Asus4"),
            "A slow, warm ambient pad with no beat: soft synthesizer-string chords in D major, "
            "each held 7.5 s and cross-faded into the next, over a quiet sub-bass; an airy layer an "
            "octave higher swells and fades twice per minute. Mostly 70 Hz to 2 kHz, rolled off above "
            "~4 kHz; no percussion, no melody.",
            "a calm explainer, a reflective or serious topic, under long narration",
        ),
        Bed(
            "pulse", _pulse, 40.0, 96, "A minor",
            ("Am9", "Fmaj9", "Cadd9", "G6/9", "Am7", "Fmaj7(add13)", "Dm9", "E7sus4"),
            "A soft rhythmic bed at 96 BPM in A minor: a gentle plucked arpeggio in eighth notes "
            "(sine-like, slightly left / right) over a muted pad, with a soft low thump on every beat "
            "(stronger on 1 and 3) like a heartbeat; chords change every two bars (5 s). Nothing above "
            "~3.5 kHz; focused, forward-moving, not dramatic.",
            "tech and product explainers, step-by-step walkthroughs, data stories",
        ),
        Bed(
            "bright", _bright, 48.0, 120, "C major",
            ("Cmaj9", "G/B", "Am7", "Fmaj7", "Cadd9", "G", "Am9", "Fmaj7/9", "Dm7", "G", "Em7", "F"),
            "An uplifting, light bed at 120 BPM in C major: a brighter pad with a shimmering upper "
            "layer, a plucked arpeggio an octave higher in eighth notes, and a sparse soft bell melody "
            "two octaves up on beats 1 and 3 (some rests); a I-V-vi-IV style progression, chords every "
            "two bars (4 s). Rolled off above ~4.5 kHz; optimistic, friendly, never loud.",
            "launches, tutorials, upbeat social clips, positive results",
        ),
        Bed(
            "cartoon", _cartoon, 45.0, 128, "G major",
            tuple(b.chord for b in _CARTOON_BARS),
            "A playful, bouncy bed at 128 BPM in G major, 4/4: a staccato pizzicato-string melody "
            "(B4 to D6, slightly right) on a short motif that comes back varied (an octave up, "
            "towards the dominant, as call and response with the woodblocks), a plucked bass "
            "bouncing root to fifth on beats 1 and 3 (D2 to E3), short pizzicato chords on beats 2 "
            "and 4 (oom-pah), two woodblocks (high right, low left), soft snare-like noise ticks "
            "and a faint pad; six 4-bar phrases, a chord per bar (I-IV-V7-I, ii and VI7 turns, "
            "a turnaround back to the top). Rolled off above ~4 kHz; cheerful, light, mischievous, "
            "never loud.",
            "cartoons and stories for children, comic or light-hearted scenes, playful how-tos",
        ),
        Bed(
            "lullaby", _lullaby, 45.0, 64, "F major",
            tuple(b.chord for b in _LULLABY_BARS),
            "A gentle, slow lullaby at 64 BPM in F major, 3/4 (waltz time, bars of 2.8 s): a "
            "music-box melody of bell-like tines (C5 to D6, slightly right; a soft shimmer as each "
            "note rings ~1.5 s) over a quieter music-box broken chord in eighth notes (E4 to G5, "
            "slightly left), a warm soft pad and a low sine bass note on each bar's first beat "
            "(C2 to Bb2); 16 bars, a chord per bar (I-IV-I-V7, ii, vi, IV turns, ending on V7 back "
            "to the top). No percussion; rolled off above ~3.5 kHz; tender, dreamy, sleepy.",
            "bedtime stories, soft or sentimental moments, endings, calm scenes for young children",
        ),
    )
}


@lru_cache(maxsize=8)
def bed_loop(name: str) -> np.ndarray:
    """A built-in bed's seamless loop: float32 ``(n, 2)`` at :data:`RATE`, :data:`MUSIC_LEVEL`
    integrated loudness, read-only; made once per process (about a second)."""
    bed = BUILTIN_BEDS.get(name)
    if bed is None:
        raise VidgenError(f"unknown music bed '{name}' (beds: {', '.join(BUILTIN_BEDS)})")
    return bed.generate(np.random.default_rng(zlib.crc32(f"music:{name}".encode("utf-8"))))


# ----- sources -------------------------------------------------------------------------------------


def is_bed(source: str) -> bool:
    """Whether ``source`` names a built-in bed (else it is a file path)."""
    return source in BUILTIN_BEDS


def source_kind(cue: MusicCue) -> str:
    """``composed`` (``compose:``), ``bed`` (a built-in bed) or ``file``."""
    if cue.compose is not None:
        return "composed"
    assert cue.source is not None
    return "bed" if is_bed(cue.source) else "file"


def composed_score(cue: MusicCue) -> Score:
    """The score a ``compose:`` cue plays (:func:`vidgen.composer.compose`)."""
    from vidgen.composer import compose

    settings = cue.compose
    assert settings is not None
    return compose(settings.mood, settings.key, settings.tempo, settings.instrument_settings(), settings.seed, settings.bars)


def fallback_bed(cue: MusicCue) -> str | None:
    """The built-in bed a ``compose:`` cue plays instead when the ``music`` extra is missing (or
    another symusic version is installed); ``None`` when composed music can play."""
    from vidgen.composer import MOODS
    from vidgen.synth import SYMUSIC_VERSION, symusic_version

    if cue.compose is None or symusic_version() == SYMUSIC_VERSION:
        return None
    return MOODS[cue.compose.mood].bed


@lru_cache(maxsize=4)
def _file_audio(path: Path, size: int, mtime: int) -> tuple[np.ndarray, float]:
    data = decode_audio(path)
    stereo = np.repeat(data, 2, axis=1) if data.shape[1] == 1 else data[:, :2]
    stereo = np.ascontiguousarray(stereo, dtype=np.float32)
    stereo.setflags(write=False)
    return stereo, integrated_loudness(stereo)


def file_audio(path: Path) -> tuple[np.ndarray, float]:
    """A music file decoded to float32 stereo ``(n, 2)`` at :data:`RATE` and its integrated
    loudness (cached per process while the file is unchanged)."""
    st = path.stat()
    return _file_audio(path, st.st_size, st.st_mtime_ns)


class Source:
    """The samples of a music cue's source as the cue plays them: from ``start`` seconds on, looped
    (a file with a cross-faded seam, a bed or composed music seamlessly) or ending, at
    :data:`MUSIC_LEVEL`. Composed music is rendered with the SoundFont ``soundfont`` (the
    project's ``soundfont:`` setting, relative to ``root``) and its render kept in ``cache_dir``;
    without the ``music`` extra its mood's bed plays instead (a warning says so)."""

    def __init__(self, cue: MusicCue, root: Path, soundfont: str | None = None, cache_dir: Path | None = None) -> None:
        kind = source_kind(cue)
        bed = cue.source if kind == "bed" else fallback_bed(cue)
        #: What plays, as the mix summary names it: its kind and its source.
        self.kind, self.label = kind, cue.label
        if bed is not None:
            if kind == "composed":
                from vidgen.synth import symusic_status

                log.warning("music: compose (mood %s) needs the music extra (symusic: %s); playing the built-in bed '%s' instead", cue.compose.mood, symusic_status(), bed)  # type: ignore[union-attr]
                self.kind, self.label = "bed", f"{cue.label} (bed {bed}: no music extra)"
            data = bed_loop(bed)
            self.seamless = True
            self.data = data
            self.offset = round(cue.start * RATE) % len(data)
            self.loop = True
            self.length = len(data)
            return
        if kind == "composed":
            self._composed(cue, root, soundfont, cache_dir)
            return
        assert cue.source is not None
        path = root / cue.source
        if not path.is_file():
            raise VidgenError(f"music file not found: {cue.source} (looked for {path})")
        audio, level = file_audio(path)
        gain = 10 ** ((MUSIC_LEVEL - level) / 20) if math.isfinite(level) else 1.0
        first = round(cue.start * RATE)
        if first >= len(audio):
            raise VidgenError(f"music: start {cue.start:g} s is past the end of {cue.source} ({len(audio) / RATE:.1f} s)")
        body = audio[first:] * np.float32(gain)
        self.seamless = False
        self.offset = 0
        self.loop = cue.loop
        fade = min(round(cue.crossfade * RATE), len(body) // 3)
        if self.loop and fade > 0:
            self.data = _crossfaded_loop(body, fade)
            self.head = body[: len(body) - fade]  # the first pass, without the seam's tail
        else:
            self.data = body
            self.head = body
        self.length = len(self.data)

    def _composed(self, cue: MusicCue, root: Path, soundfont: str | None, cache_dir: Path | None) -> None:
        """Composed music: the piece plus its reverb tail; looped, the tail is added onto the
        piece's start (the piece ends turning back to its beginning), so it repeats without a
        seam, and ``start`` wraps around the piece."""
        from vidgen import soundfont as soundfonts
        from vidgen.synth import render_score

        score = composed_score(cue)
        audio = render_score(score, soundfonts.resolve(soundfont, root), cache_dir)  # at the music level
        piece = min(len(audio), round(score.length_seconds * RATE))
        first = round(cue.start * RATE) % piece
        self.seamless = False
        self.offset = 0
        self.loop = cue.loop
        if self.loop:
            loop = np.array(audio[:piece], dtype=np.float32)
            for c in range(2):
                _circular_add(loop[:, c], 0, audio[piece:, c])
            loop.setflags(write=False)
            self.data = loop
            self.head = audio[first:piece]
        else:
            self.data = self.head = audio[first:]
        self.length = len(self.data)

    @property
    def ends_at(self) -> int | None:
        """Sample (from the cue's start) where the source runs out; ``None`` when it loops."""
        return None if self.loop else len(self.data)

    def read(self, a: int, b: int) -> np.ndarray:
        """Samples ``a`` to ``b`` (from the cue's start) as float32 ``(b - a, 2)``."""
        idx = np.arange(a, b)
        if self.seamless:
            return self.data[(idx + self.offset) % self.length]
        if not self.loop:
            out = np.zeros((b - a, 2), dtype=np.float32)
            inside = idx < self.length
            out[inside] = self.data[idx[inside]]
            return out
        first = len(self.head)
        out = np.empty((b - a, 2), dtype=np.float32)
        early = idx < first
        out[early] = self.head[idx[early]]
        out[~early] = self.data[(idx[~early] - first) % self.length]
        return out


def _crossfaded_loop(body: np.ndarray, fade: int) -> np.ndarray:
    """A loop of ``body`` with its last ``fade`` samples cross-faded (equal power) into its
    first: played after the first pass (``body[:-fade]``), it continues exactly where that pass
    stops and repeats without a seam."""
    u = (np.arange(fade) + 0.5) / fade
    fade_in = np.sin(0.5 * np.pi * u)[:, None].astype(np.float32)
    fade_out = np.cos(0.5 * np.pi * u)[:, None].astype(np.float32)
    loop = np.array(body[: len(body) - fade], dtype=np.float32)
    loop[:fade] = body[:fade] * fade_in + body[len(body) - fade :] * fade_out
    return loop


# ----- checks and listing --------------------------------------------------------------------------


def config_problems(config: VideoConfig, root: Path | None) -> list[tuple[str, str]]:
    """``(location, message)`` problems of the ``music:`` cues: a source that is neither a bed nor
    a file under the project (``compose:`` settings are checked when the config loads)."""
    found: list[tuple[str, str]] = []
    cues = config.music_cues
    for k, cue in enumerate(cues):
        where = "music" if not isinstance(config.music, list) else f"music[{k}]"
        if source_kind(cue) != "file" or root is None:
            continue
        assert cue.source is not None
        path = root / cue.source
        if not path.is_file():
            hint = f"; built-in beds: {', '.join(BUILTIN_BEDS)}, or compose: {{mood: ...}} (vidgen list-music)"
            found.append((f"{where}.source", f"neither a built-in bed nor a file: {cue.source} (looked for {path}){hint}"))
    return found


def project_music(root: Path | None) -> list[Path]:
    """The audio files under the project's ``assets/music`` (sorted)."""
    folder = None if root is None else root / PROJECT_MUSIC_DIR
    if folder is None or not folder.is_dir():
        return []
    return [p for p in sorted(folder.rglob("*")) if p.is_file() and p.suffix.lower() in MUSIC_SUFFIXES]


def _decibels(value: float) -> float | None:
    return round(value, 1) if math.isfinite(value) else None


def music_entries(root: Path | None, preview_dir: Path | None = None) -> list[dict[str, Any]]:
    """The beds and the project's ``assets/music`` files described for ``vidgen list-music``:
    ``{name, origin, description, use, tempo, key, chords, loop_seconds, duration, channels,
    loudness, preview}`` (beds: their loop; files: as decoded; ``preview``: a WAV of the bed
    written to ``preview_dir``, else ``None``)."""
    entries: list[dict[str, Any]] = []
    for bed in BUILTIN_BEDS.values():
        data = bed_loop(bed.name)
        preview = None
        if preview_dir is not None:
            preview = preview_dir / f"{bed.name}.wav"
            write_wav(preview, data)
        entries.append(
            {
                "name": bed.name,
                "origin": "builtin",
                "description": bed.description,
                "use": bed.use,
                "tempo": bed.tempo,
                "key": bed.key,
                "chords": list(bed.chords),
                "loop_seconds": round(len(data) / RATE, 3),
                "duration": None,
                "channels": 2,
                "loudness": _decibels(integrated_loudness(data)),
                "preview": preview,
            }
        )
    for path in project_music(root):
        assert root is not None
        rel = path.relative_to(root).as_posix()
        try:
            data, level = file_audio(path)
        except VidgenError as exc:
            log.warning("%s", exc)
            continue
        entries.append(
            {
                "name": rel,
                "origin": "project",
                "description": None,
                "use": None,
                "tempo": None,
                "key": None,
                "chords": None,
                "loop_seconds": None,
                "duration": round(len(data) / RATE, 3),
                "channels": 2,
                "loudness": _decibels(level),
                "preview": None,
            }
        )
    return entries
