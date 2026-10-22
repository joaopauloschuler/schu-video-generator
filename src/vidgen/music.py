"""Background music (DESIGN.md §48, §69.63, §82, §83, §91, §93.12): sixteen procedurally generated
beds (two of them, ``tidewater`` and ``skyline``, written as score files and rendered by
:mod:`vidgen.studio`), the project's own music files, composed music (:mod:`vidgen.composer`,
played by :mod:`vidgen.synth`), and the sources the mix reads from.

A *bed* is a seamless loop made of a chord progression (numpy only, no recordings, no samples,
deterministic): sustained pads are built with the PADsynth method (Nasca Octavian
Paul's algorithm, from ZynAddSubFX) — each chord's
harmonics as narrow Gaussian bumps of a spectrum with seeded random phases, turned into a
periodic wave by one inverse FFT — and cross-faded from chord to chord; plucked arpeggios,
pizzicato strings, bells, music-box tines and woodblocks are added note by note (the documentary
beds also a soft kick, synth bass, hi-hats and side-chain dips; the energetic beds supersaw-like
chords, a trance gate, an analog bass, a gated snare, pulsar pulses). Everything is rendered *circularly* (notes running past the loop's
end continue at its start; the final filtering is a circular FFT filter), so the loop repeats
without a seam. The loop is set to :data:`MUSIC_LEVEL` integrated loudness.

A *file* (any format FFmpeg reads, decoded with PyAV) is matched to the same loudness; it can
start later (``start``) and loop with a cross-faded seam (``crossfade``).
"""

from __future__ import annotations

import difflib
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
from vidgen.sfx import RATE, _band, _bump, _filtered, _highpass, _lowpass, _sweep, _tone, decode_audio, write_wav

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


# ----- voices of the documentary beds (Step 179) ---------------------------------------------------


@lru_cache(maxsize=16)
def _kick(f_hi: float = 92.0, f_lo: float = 47.0, tau: float = 0.16, click: float = 0.06, seconds: float = 0.5) -> np.ndarray:
    """A soft kick: a sine gliding from ``f_hi`` to ``f_lo`` Hz in ~35 ms, 2 ms attack, decay
    ``tau``, a faint low-passed click for definition (nothing above ~2.5 kHz); peak 1."""
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    freq = f_lo + (f_hi - f_lo) * np.exp(-t / 0.035)
    body = np.sin(_tone(freq, n)) * (1 - np.exp(-t / 0.002)) * np.exp(-t / tau)
    burst = np.random.default_rng(7).standard_normal(n) * np.exp(-t / 0.003)
    body += click * _filtered(burst, lambda f: _lowpass(f, 2500.0, 2) * _highpass(f, 400.0, 2))
    tail = int(0.03 * RATE)
    body[-tail:] *= np.linspace(1, 0, tail)
    body.setflags(write=False)
    return body / np.abs(body).max()


def _synth_bass(freq: float, n: int, tau: float, cutoff: float) -> np.ndarray:
    """A warm saw-like synth bass: 10 harmonics at 1/h shaped by :func:`_shape` at ``cutoff``,
    the upper ones dying faster (a closing filter), 4 ms attack."""
    partials = tuple((float(h), 1.0 / h, 1.0 / (1 + 0.35 * (h - 1))) for h in range(1, 11))
    return _partials(freq, n, tau, 0.004, partials, cutoff)


@lru_cache(maxsize=4)
def _hat(seed: int = 3, tau: float = 0.022, center: float = 6500.0) -> np.ndarray:
    """A soft closed hi-hat: a noise burst around ``center`` Hz, 4.5-9 kHz, steep both sides; peak 1."""
    n = int(0.09 * RATE)
    t = np.arange(n) / RATE
    burst = np.random.default_rng(seed).standard_normal(n) * np.exp(-t / tau) * (1 - np.exp(-t / 0.0005))
    hat = _filtered(burst, lambda f: _band(f, center, 0.3) * _highpass(f, 4500.0, 4) * _lowpass(f, 9000.0, 4))
    hat[-int(0.01 * RATE) :] *= np.linspace(1, 0, int(0.01 * RATE))
    hat.setflags(write=False)
    return hat / np.abs(hat).max()


def _clap(seed: int = 21, center: float = 1300.0) -> np.ndarray:
    """A soft clap: band-passed noise around ``center`` Hz and a short 190 Hz body; peak 1."""
    n = int(0.11 * RATE)
    t = np.arange(n) / RATE
    noise = np.random.default_rng(seed).standard_normal(n) * np.exp(-t / 0.03) * (1 - np.exp(-t / 0.001))
    clap = _filtered(noise, lambda f: _band(f, center, 0.5) * _lowpass(f, 3500.0, 4)) + 0.6 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.03)
    clap[-480:] *= np.linspace(1, 0, 480)
    return clap / np.abs(clap).max()


#: ``momentum``'s accent (also in the Step 181 beds): 3+3+2 sixteenths, twice a bar.
_ACCENTS = (0, 3, 6, 8, 11, 14)
#: ``momentum``'s sixteenth-note figure: indices into four tones.
_FIGURE = (0, 1, 2, 0, 1, 3, 0, 1, 2, 0, 1, 3, 2, 1, 0, 1)


@lru_cache(maxsize=4)
def _clock(center: float, seed: int = 11) -> np.ndarray:
    """A clock tick: a 4 ms burst around ``center`` Hz with a little ring; peak 1."""
    n = int(0.03 * RATE)
    t = np.arange(n) / RATE
    burst = np.random.default_rng(seed).standard_normal(n) * np.exp(-t / 0.0015)
    ring = 0.4 * np.sin(2 * np.pi * center * t) * np.exp(-t / 0.004)
    tick = _filtered(burst, lambda f: _band(f, center, 0.25) * _lowpass(f, 7000.0, 4)) + ring
    tick[-int(0.005 * RATE) :] *= np.linspace(1, 0, int(0.005 * RATE))
    tick.setflags(write=False)
    return tick / np.abs(tick).max()


def _piano(freq: float, n: int, tau: float, lowpass: float) -> np.ndarray:
    """A soft piano-like note: slightly stretched partials, the upper ones dying first, 3 ms attack."""
    partials = ((1.0, 1.0, 1.0), (2.003, 0.45, 0.6), (3.008, 0.2, 0.45), (4.015, 0.1, 0.35), (5.025, 0.05, 0.28))
    return _partials(freq, n, tau, 0.003, partials, lowpass)


@lru_cache(maxsize=128)
def _fm_pluck(freq: float, n: int, tau: float, index: float, lowpass: float) -> np.ndarray:
    """A modern electronic pluck: two-operator FM (modulator at twice the pitch) whose index
    falls fast (a bright "blip" settling into a sine), 2 ms attack, low-passed at ``lowpass``."""
    t = np.arange(n) / RATE
    idx = index * np.exp(-t / (0.25 * tau))
    y = np.sin(2 * np.pi * freq * t + idx * np.sin(2 * np.pi * 2 * freq * t)) * (1 - np.exp(-t / 0.002)) * np.exp(-t / tau)
    y = _filtered(y, lambda f: _lowpass(f, lowpass, 2) * _highpass(f, 120.0, 2))
    tail = min(n, int(0.02 * RATE))
    y[-tail:] *= np.linspace(1, 0, tail)
    y.setflags(write=False)
    return y


def _pump(total: int, beat: int, depth: float, release: float = 0.16) -> np.ndarray:
    """A side-chain gain curve ``(total,)``: dips by ``depth`` just after every beat and recovers
    with ``release`` seconds; built circularly, so it is smooth across beats and the loop's end."""
    t = np.arange(2 * beat) / RATE
    dip = depth * (1 - np.exp(-t / 0.008)) * np.exp(-t / release)
    curve = np.zeros(total)
    for start in range(0, total, beat):
        _circular_add(curve, start, dip)
    return 1.0 - curve


def _riser(seconds: float, lo: float, hi: float, seed: int = 5) -> np.ndarray:
    """A soft noise riser: band-passed noise sweeping ``lo`` to ``hi`` Hz, swelling to its end,
    which is cut with a 10 ms fade; peak 1."""
    n = int(seconds * RATE)
    noise = np.random.default_rng(seed).standard_normal(n)
    swept = _sweep(noise, lambda u: lo * (hi / lo) ** u, 0.35)
    env = np.sin(0.5 * np.pi * np.linspace(0, 1, n)) ** 3
    out = swept * env
    out[-int(0.01 * RATE) :] *= np.linspace(1, 0, int(0.01 * RATE))
    return out / np.abs(out).max()


def _echoed(out: np.ndarray, start: int, sound: np.ndarray, pan: float, delay: int, feedback: float, repeats: int) -> None:
    """``sound`` at ``start`` plus ``repeats`` echoes ``delay`` samples apart, each ``feedback``
    quieter and on the other side (ping-pong)."""
    for k in range(repeats + 1):
        _add_panned(out, start + k * delay, sound * feedback**k, pan if k % 2 == 0 else -pan)


def _hits(out: np.ndarray, sound: np.ndarray, positions: Sequence[int], gain: float | Sequence[float], pan: float = 0.0) -> None:
    """``sound`` at each of ``positions``, times ``gain`` (one for all or one per position)."""
    gains = [gain] * len(positions) if isinstance(gain, (int, float)) else list(gain)
    for p, g in zip(positions, gains):
        _add_panned(out, p, sound * g, pan)


def _circular_smooth(x: np.ndarray, width: int) -> np.ndarray:
    """``x`` averaged over a centred window of ``width`` samples, wrapping around the loop."""
    kernel = np.zeros(len(x))
    kernel[:width] = 1.0 / width
    kernel = np.roll(kernel, -(width // 2))
    return np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(kernel), len(x))


def _tone_filter(x: np.ndarray, lowpass: float, highpass: float = 32.0) -> np.ndarray:
    """The whole stereo loop through a circular (FFT over the loop) high-pass and gentle
    low-pass: the loop's end and start are filtered as neighbours, so the seam stays clean."""
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    gain = _highpass(freqs, highpass, 2) * _lowpass(freqs, lowpass, 2)
    return np.fft.irfft(np.fft.rfft(x, axis=0) * gain[:, None], len(x), axis=0)


# ----- the beds ------------------------------------------------------------------------------------

#: Harmonic amplitudes of the pads: warm (falls fast) and airy (more upper partials).
_WARM = tuple(1.0 / h**1.6 for h in range(1, 9))
_AIRY = tuple(1.0 / h**1.1 for h in range(1, 13))


@dataclass(frozen=True)
class Bed:
    """A built-in music bed: its generator, loop length, musical facts and a precise textual
    description (for authors who cannot listen) and when to use it. ``seed``: the name its random
    generator is seeded with (``crc32("music:<seed>")``) when it is not the bed's own: the Step
    181 beds keep their prototype's, so they sound exactly as approved. ``score``: the bed is a
    score file, ``studio/beds/<name>.yaml`` (also its template), rendered by
    :func:`vidgen.studio.render_music_score` (Step 190; the generator's ``rng`` is not used)."""

    name: str
    generate: Callable[[np.random.Generator], np.ndarray]
    seconds: float
    tempo: int | None
    key: str
    chords: tuple[str, ...]
    description: str
    use: str
    seed: str | None = None
    score: bool = False


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


# The documentary beds (Step 179, DESIGN.md §91): a soft kick and synth bass under pads and
# arpeggios, side-chained, the whole loop through :func:`_tone_filter`. Bass-heavy on purpose.


def _opening_pads(
    chords: Sequence[Sequence[int]], bass: Sequence[int], seg: int, rng: np.random.Generator, dark: float, open_: float, curve: np.ndarray, air: float
) -> np.ndarray:
    """Pads whose filter opens and closes along ``curve`` (0 dark .. 1 open, per sample): a dark
    and an open render (``dark`` / ``open_`` Hz) cross-faded with equal power."""
    a = _pads(chords, bass, seg, seg // 2, rng, air=0.0, air_cycles=1, lowpass=dark)
    b = _pads(chords, bass, seg, seg // 2, rng, air=air, air_cycles=1, lowpass=open_)
    w = 0.5 * np.pi * curve[:, None]
    return np.cos(w) * a + np.sin(w) * b


def _discovery(rng: np.random.Generator) -> np.ndarray:
    lowpass = 4200.0
    beat = RATE * 60 // 104  # 104 BPM
    bar = 4 * beat
    seg = 2 * bar
    chords = (
        (50, 57, 62, 64, 65),  # Dm(add9)
        (46, 53, 57, 62, 65),  # Bbmaj7
        (53, 57, 60, 65, 67),  # Fadd9
        (48, 55, 60, 62, 67),  # Csus2
        (50, 57, 60, 65, 69),  # Dm7
        (43, 50, 57, 58, 62),  # Gm9
        (46, 53, 57, 60, 62),  # Bbmaj9
        (45, 52, 57, 62, 64),  # Asus4
        (50, 57, 62, 64, 65),  # Dm(add9)
        (46, 53, 58, 62, 64),  # Bb(add#11)
        (43, 50, 58, 62, 65),  # Gm7
        (45, 52, 57, 61, 64),  # A
    )
    roots = (38, 34, 41, 36, 38, 43, 34, 33, 38, 34, 43, 33)
    total = len(chords) * seg
    u = np.arange(total) / total
    opening = _bump(u, 0.72)
    out = 0.42 * _opening_pads(chords, roots, seg, rng, 800.0, 3000.0, opening, air=0.25)
    out *= _pump(total, beat, 0.35)[:, None]
    arp = np.zeros((total, 2))
    _arpeggio(arp, chords, seg, beat // 2, rng, octave=0, tau=0.2, bright=0.4, level=0.32, lowpass=2400.0)
    out += arp * (0.75 + 0.25 * opening)[:, None]
    _hits(out, _kick(), range(0, total, beat), 0.7)
    hat = _hat()
    for p in range(beat // 2, total, beat):
        _add_panned(out, p, hat * 0.09 * (0.6 + 0.6 * opening[p]), 0.3)
    for i, root in enumerate(roots):  # pulsing eighths, octave on the last eighth of every second bar
        for k in range(16):
            note = root + (12 if k == 15 else 0)
            level = 0.4 if k % 2 == 0 else 0.3
            _add_panned(out, i * seg + k * beat // 2, _synth_bass(_hz(note), int(0.26 * RATE), 0.11, 650.0) * level, 0.0)
    return _finish(_tone_filter(out, lowpass))


def _breakthrough(rng: np.random.Generator) -> np.ndarray:
    lowpass = 4300.0
    beat = RATE * 60 // 112  # 112 BPM
    bar = 4 * beat
    seg = 2 * bar
    chords = (
        (48, 55, 60, 62, 63),  # Cm(add9)
        (44, 51, 55, 60, 63),  # Abmaj7
        (41, 48, 55, 56, 60),  # Fm9
        (43, 55, 60, 62, 63),  # Cm(add9)/G
        (44, 51, 55, 60, 62),  # Abmaj7(#11)
        (43, 50, 53, 55, 60),  # G7sus4
        (51, 58, 63, 65, 67),  # Eb(add9): the lift
        (50, 53, 58, 60, 65),  # Bb(add9)/D
        (44, 51, 55, 58, 60),  # Abmaj9
        (43, 51, 55, 58, 63),  # Eb/G
        (46, 53, 58, 60, 62),  # Bb(add9)
        (43, 50, 55, 59, 62),  # G
    )
    roots = (36, 44, 41, 43, 44, 43, 39, 38, 44, 43, 46, 43)
    total = len(chords) * seg
    half = 6 * seg
    step = (np.arange(total) >= half).astype(float)  # 1 in the second half
    lifted = _circular_smooth(step, int(0.06 * RATE))
    out = 0.4 * _opening_pads(chords, roots, seg, rng, 900.0, 3200.0, 0.15 + 0.85 * lifted, air=0.35)
    out *= (1 - lifted + lifted * _pump(total, beat, 0.35))[:, None]  # pumping only once lifted
    dark, bright = np.zeros((total, 2)), np.zeros((total, 2))
    _arpeggio(dark, chords, seg, beat // 2, rng, octave=0, tau=0.18, bright=0.3, level=0.3, lowpass=1900.0)
    _arpeggio(bright, chords, seg, beat // 2, rng, octave=1, tau=0.2, bright=0.45, level=0.2, lowpass=3200.0)
    out += dark * (1 - 0.6 * lifted)[:, None] + bright * lifted[:, None]
    kick, hat = _kick(), _hat()
    for b in range(0, total, beat):
        k = (b // beat) % 4
        if b < half:
            if k in (0, 2):
                _add_panned(out, b, kick * (0.72 if k == 0 else 0.6), 0.0)
        else:
            _add_panned(out, b, kick * 0.72, 0.0)
            _add_panned(out, b + beat // 2, hat * 0.1, 0.3)
    for k, p in enumerate(range(0, half, beat // 4)):  # a sixteenth tick growing through the first half
        _add_panned(out, p, _clock(3600.0) * (0.012 + 0.03 * p / half) * (1.0 if k % 4 == 0 else 0.6), -0.3)
    for i, root in enumerate(roots):
        start = i * seg
        if start < half:  # staccato quarter notes
            for k in range(8):
                _add_panned(out, start + k * beat, _synth_bass(_hz(root), int(0.3 * RATE), 0.09, 600.0) * (0.45 if k % 2 == 0 else 0.36), 0.0)
        else:  # driving eighths
            for k in range(16):
                _add_panned(out, start + k * beat // 2, _synth_bass(_hz(root), int(0.24 * RATE), 0.1, 700.0) * (0.42 if k % 2 == 0 else 0.34), 0.0)
    rise = _riser(4 * bar / RATE, 250.0, 2200.0)
    _add_panned(out, half - len(rise), rise * 0.07, 0.0)
    boom = _kick(f_hi=70.0, f_lo=38.0, tau=0.9, click=0.02, seconds=2.5)
    _add_panned(out, half, boom * 0.55, 0.0)
    return _finish(_tone_filter(out, lowpass))


#: The ``enigma`` bed's piano motif per 4-bar phrase: (beat, midi) pairs; sparse, B3 to C#5.
_ENIGMA_MOTIF = (
    ((0, 66), (1.5, 61), (3, 62), (8, 66), (9.5, 61), (11, 59)),
    ((0, 66), (1.5, 64), (3, 59), (8, 61), (9.5, 66), (12, 73)),
    ((0, 66), (1.5, 61), (3, 62), (8, 69), (9.5, 66), (11, 64)),
    ((0, 67), (1.5, 62), (3, 59), (8, 64), (9.5, 59), (11, 62)),
    ((0, 66), (1.5, 71), (3, 72), (8, 66), (10, 61)),
)


def _enigma(rng: np.random.Generator) -> np.ndarray:
    lowpass = 3600.0
    beat = RATE * 60 // 96  # 96 BPM
    bar = 4 * beat
    seg = 2 * bar
    chords = (
        (47, 54, 61, 62, 66),  # Bm(add9)
        (43, 50, 54, 61, 62),  # Gmaj7(#11)
        (40, 47, 54, 59, 66),  # Esus2
        (42, 49, 54, 59, 61),  # F#sus4
        (47, 54, 61, 62, 66),  # Bm(add9)
        (45, 50, 54, 57, 61),  # Dmaj7/A
        (43, 50, 54, 61, 62),  # Gmaj7(#11)
        (40, 47, 55, 62, 66),  # Em9
        (36, 43, 47, 54, 59),  # Cmaj7(#11)
        (42, 49, 54, 59, 61),  # F#sus4
    )
    roots = (35, 43, 40, 42, 35, 33, 43, 40, 36, 42)
    total = len(chords) * seg
    out = 0.38 * _pads(chords, roots, seg, seg // 2, rng, air=0.1, air_cycles=1, lowpass=1400.0)
    out *= _pump(total, beat, 0.3, release=0.25)[:, None]
    kick = _kick(f_hi=75.0, f_lo=42.0, tau=0.22, click=0.03)
    for b in range(0, total, 2 * beat):
        _add_panned(out, b, kick * (0.68 if (b // beat) % 4 == 0 else 0.52), 0.0)
    for i, root in enumerate(roots):
        sub = _partials(_hz(root), int(0.7 * RATE), 0.3, 0.012, ((1.0, 1.0, 1.0), (2.0, 0.18, 0.6)), 600.0)
        for k in range(8):
            _add_panned(out, i * seg + k * beat, sub * (0.58 if k % 2 == 0 else 0.46), 0.0)
    for p, motif in enumerate(_ENIGMA_MOTIF):
        for at, note in motif:
            sound = _piano(_hz(note), int(2.4 * RATE), 0.7, 2400.0) * 0.26
            _echoed(out, p * 2 * seg + int(at * beat), sound, 0.25, beat * 3 // 4, 0.38, 3)
    for b in range(0, total, 4 * bar):  # a faint high glint every 4 bars, alternating B5 / F#5
        note = 83 if (b // (4 * bar)) % 2 == 0 else 78
        _echoed(out, b + 2 * bar + 2 * beat, _bell(_hz(note), int(2.0 * RATE), 0.6, 3000.0) * 0.06, -0.4, beat * 3 // 4, 0.4, 3)
    return _finish(_tone_filter(out, lowpass))


def _momentum(rng: np.random.Generator) -> np.ndarray:
    lowpass = 4500.0
    beat = RATE * 60 // 120  # 120 BPM
    bar = 4 * beat
    seg = 2 * bar
    six = beat // 4
    chords = (
        (43, 50, 57, 58, 62),  # Gm(add9)
        (51, 55, 58, 62, 63),  # Ebmaj7
        (48, 55, 58, 62, 63),  # Cm9
        (50, 55, 57, 62, 64),  # Dsus4(add9)
        (43, 50, 53, 58, 62),  # Gm7
        (51, 55, 58, 62, 65),  # Ebmaj9
        (46, 53, 58, 60, 62),  # Bb(add9)
        (41, 48, 55, 57, 60),  # F(add9)
        (48, 55, 58, 62, 63),  # Cm9
        (51, 55, 58, 62, 63),  # Ebmaj7
        (50, 55, 57, 62, 64),  # Dsus4
        (50, 54, 57, 62, 66),  # D
    )
    roots = (43, 39, 36, 38, 43, 39, 46, 41, 36, 39, 38, 38)
    total = len(chords) * seg
    out = 0.32 * _pads(chords, roots, seg, seg // 2, rng, air=0.3, air_cycles=2, lowpass=2600.0)
    out *= _pump(total, beat, 0.45, release=0.14)[:, None]
    kick, hat = _kick(f_hi=100.0, f_lo=50.0, tau=0.14, click=0.08), _hat()
    _hits(out, kick, range(0, total, beat), 0.75)
    clap = _clap()
    for b in range(beat, total, 2 * beat):
        _add_panned(out, b, clap * 0.13, 0.0)
    for k, p in enumerate(range(0, total, six)):
        _add_panned(out, p, hat * (0.085 if k % 4 == 2 else 0.035), 0.25 if k % 2 else -0.25)
    for i, (notes, root) in enumerate(zip(chords, roots)):
        tones = (root + 12, root + 19, root + 24, sorted(notes)[2])
        for bar_k in range(2):
            for k, idx in enumerate(_FIGURE):
                level = 0.36 if k in _ACCENTS else 0.22
                note = _synth_bass(_hz(tones[idx]), int(0.2 * RATE), 0.06, 1500.0) * level
                _add_panned(out, i * seg + bar_k * bar + k * six, note, 0.15 if k % 2 else -0.15)
        for k in range(8):  # off-beat bass
            _add_panned(out, i * seg + k * beat + beat // 2, _synth_bass(_hz(root), int(0.22 * RATE), 0.1, 550.0) * 0.45, 0.0)
    rise = _riser(2 * bar / RATE, 300.0, 2500.0, seed=9)
    _add_panned(out, total - len(rise), rise * 0.06, 0.0)
    return _finish(_tone_filter(out, lowpass))


def _lab(rng: np.random.Generator) -> np.ndarray:
    lowpass = 4800.0
    beat = RATE * 60 // 108  # 108 BPM
    bar = 4 * beat
    seg = 2 * bar
    six = beat // 4
    chords = (
        (41, 48, 55, 56, 60),  # Fm9
        (49, 56, 60, 65),  # Dbmaj7
        (46, 53, 56, 60, 61),  # Bbm9
        (51, 58, 63, 65),  # Ebsus2
        (41, 48, 55, 56, 60),  # Fm9
        (44, 51, 55, 60, 63),  # Abmaj7
        (49, 56, 60, 67),  # Dbmaj7(#11)
        (46, 53, 56, 61),  # Bbm7
        (43, 49, 53, 58),  # Gm7b5
        (48, 52, 55, 58),  # C7
    )
    roots = (41, 37, 46, 39, 41, 44, 37, 46, 43, 36)
    total = len(chords) * seg
    out = 0.26 * _pads(chords, roots, seg, seg // 2, rng, air=0.2, air_cycles=1, lowpass=2000.0)
    out *= _pump(total, beat, 0.5, release=0.13)[:, None]
    _hits(out, _kick(f_hi=105.0, f_lo=50.0, tau=0.13, click=0.08), range(0, total, beat), 0.72)
    n = int(0.06 * RATE)  # a soft snap: band-passed noise
    t = np.arange(n) / RATE
    noise = np.random.default_rng(31).standard_normal(n) * np.exp(-t / 0.012)
    snap = _filtered(noise, lambda f: _band(f, 1800.0, 0.45) * _lowpass(f, 4000.0, 4))
    snap[-240:] *= np.linspace(1, 0, 240)
    snap /= np.abs(snap).max()
    for b in range(beat, total, 2 * beat):
        _add_panned(out, b, snap * 0.08, 0.1)
    click_hi, click_lo = _clock(5200.0, seed=41), _clock(3800.0, seed=42)
    glitch = np.random.default_rng(55)
    slots = [s for s in range(16) if glitch.random() < 0.45 and s % 4 != 0]
    for b in range(0, total, bar):
        for s in slots:
            _add_panned(out, b + s * six, (click_hi if s % 2 else click_lo) * 0.05, 0.5 if s % 3 else -0.5)
        if (b // bar) % 4 == 3:  # a stutter: 32nd-note clicks rising in level into the next bar
            for k in range(8):
                _add_panned(out, b + 3 * beat + k * six // 2, click_hi * (0.02 + 0.006 * k), -0.2)
    bass_slots = (2, 3, 6, 10, 11, 14)
    pluck_slots = (0, 3, 6, 8, 10, 13)
    for i, (notes, root) in enumerate(zip(chords, roots)):
        upper = sorted(notes)[1:]
        for bar_k in range(2):
            start = i * seg + bar_k * bar
            for k in bass_slots:
                _add_panned(out, start + k * six, _synth_bass(_hz(root), int(0.18 * RATE), 0.08, 450.0) * (0.45 if k in (2, 10) else 0.34), 0.0)
            for j, k in enumerate(pluck_slots):
                note = upper[(j + bar_k) % len(upper)] + 12
                sound = _fm_pluck(_hz(note), int(0.5 * RATE), 0.16, 1.6, 2600.0) * 0.2
                _echoed(out, start + k * six, sound, 0.35, 3 * six, 0.33, 2)
    return _finish(_tone_filter(out, lowpass))


# The energetic beds (Step 181, DESIGN.md §91): uplifting trance, a pulsar beacon and a night
# drive, built on ``momentum``'s 3+3+2 accent, a steady low pulse and an off-beat or rolling bass.

#: Harmonic amplitudes of the supersaw-like chords: a saw, and a softer saw for warm pads.
_SAW = tuple(1.0 / h for h in range(1, 25))
_SOFT_SAW = tuple(1.0 / h**1.35 for h in range(1, 17))


def _grid(tempo: int, bars_per_chord: int = 2) -> tuple[int, int, int, int]:
    """``(beat, bar, chord segment, sixteenth)`` in samples at ``tempo`` BPM, the beat rounded
    down to whole sixteenths so the sixteenth grid is exact."""
    beat = RATE * 60 // tempo
    beat -= beat % 4
    bar = 4 * beat
    return beat, bar, bars_per_chord * bar, beat // 4


def _grid_seconds(tempo: int, bars: int) -> float:
    """The length of ``bars`` bars of 4/4 on :func:`_grid`'s beat."""
    return _grid(tempo)[1] * bars / RATE


def _saw_chords(
    chords: Sequence[Sequence[int]], seg: int, table: int, rng: np.random.Generator, harmonics: Sequence[float], width: float, lowpass: float, octave: int = 0, fade_s: float = 0.25
) -> np.ndarray:
    """Stereo ``(len(chords) * seg, 2)`` supersaw-like chords: each chord as a PADsynth wave of
    saw ``harmonics`` spread ``width`` cents (a cloud of detuned saws, band-limited by
    :func:`_shape` at ``lowpass``), independent phases per channel (wide), cross-faded in
    ``fade_s`` seconds; RMS ~1 per channel. ``table`` divides ``seg``, so it loops."""
    total = len(chords) * seg
    fade = 2 * int(fade_s * RATE)
    env = _xfade_window(seg, fade)
    out = np.zeros((total, 2))
    for i, notes in enumerate(chords):
        first = i * seg - fade // 2
        idx = (first + np.arange(seg + fade)) % table
        for c in range(2):
            wave = _pad_wave([n + 12 * octave for n in notes], table, rng, harmonics, width, lowpass)
            _circular_add(out[:, c], first, env * wave[idx])
    return out


def _sweep_mix(dark: np.ndarray, bright: np.ndarray, curve: np.ndarray) -> np.ndarray:
    """A filter sweep: an equal-power cross-fade of a dark and a bright render along ``curve``
    (0 dark .. 1 bright, per sample)."""
    w = 0.5 * np.pi * np.clip(curve, 0, 1)[:, None]
    return np.cos(w) * dark + np.sin(w) * bright


def _section_curve(total: int, bar: int, points: Sequence[tuple[float, float]], smooth: float = 0.4) -> np.ndarray:
    """A per-sample curve through ``(bar, value)`` points, periodic over the loop (the last point
    leads back to the first), smoothed circularly over ``smooth`` seconds."""
    xs = np.array([p[0] * bar for p in points], float)
    ys = np.array([p[1] for p in points], float)
    curve = np.interp(np.arange(total), xs, ys, period=total)
    return _circular_smooth(curve, max(1, int(smooth * RATE)))


def _gate(total: int, six: int, levels: Sequence[float], duty: float = 0.55, floor: float = 0.08) -> np.ndarray:
    """A trance gate ``(total,)``: one window per sixteenth (3 ms attack, open ``duty`` of the
    step, 18 ms release) scaled by ``levels[slot]`` (16 per bar), never below ``floor``."""
    bar = 16 * six
    n = 2 * six
    t = np.arange(n) / RATE
    hold = duty * six / RATE
    win = (1 - np.exp(-t / 0.003)) * np.where(t < hold, 1.0, np.exp(-(t - hold) / 0.018))
    g = np.zeros(bar)
    for s, lv in enumerate(levels):
        pos = (s * six + np.arange(n)) % bar
        g[pos] = np.maximum(g[pos], lv * win)
    g = np.tile(g, total // bar)
    return floor + (1 - floor) * g


@lru_cache(maxsize=512)
def _analog_bass(freq: float, n: int, tau: float, cut_hi: float, cut_lo: float, ftau: float, detune: float = 7.0) -> np.ndarray:
    """An analog-style bass: two saws ``detune`` cents apart through a two-pole low-pass whose
    cutoff falls from ``cut_hi`` to ``cut_lo`` Hz (time constant ``ftau``), 3 ms attack, decay
    ``tau``, a 15 ms tail fade; peak 1."""
    t = np.arange(n) / RATE
    fc = cut_lo + (cut_hi - cut_lo) * np.exp(-t / ftau)
    y = np.zeros(n)
    f2 = freq * 2 ** (detune / 1200)
    h = 1
    while h * freq < min(3 * cut_hi, 5000.0):
        for f, ph in ((freq, 0.0), (f2, 1.3 * h)):
            g = (1.0 / h) / np.sqrt(1 + (h * f / fc) ** 4)
            y += g * np.sin(2 * np.pi * h * f * t + ph)
        h += 1
    y *= (1 - np.exp(-t / 0.003)) * np.exp(-t / tau)
    tail = min(n, int(0.015 * RATE))
    y[-tail:] *= np.linspace(1, 0, tail)
    y = y / max(np.abs(y).max(), 1e-12)
    y.setflags(write=False)
    return y


def _square_pluck(freq: float, n: int, tau: float, lowpass: float) -> np.ndarray:
    """A retro square-ish pluck: odd harmonics at 1/h, the upper ones dying first, 3 ms attack."""
    return _partials(freq, n, tau, 0.003, ((1.0, 1.0, 1.0), (3.0, 0.33, 0.55), (5.0, 0.2, 0.4), (7.0, 0.14, 0.3)), lowpass)


def _gated_snare(seed: int, gate: float = 0.24, body: float = 190.0) -> np.ndarray:
    """A gated-reverb snare ``(n, 2)``: a short crack (noise around 1.8 kHz) and body (a falling
    ``body`` Hz tone), then a dense noise "room" of 1-4.5 kHz held flat for ``gate`` seconds and
    cut with a 20 ms fade; the room has a different noise per channel (wide); peak 1."""
    n = int((gate + 0.03) * RATE)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(seed)
    crack = _filtered(rng.standard_normal(n) * np.exp(-t / 0.01), lambda f: _band(f, 1800.0, 0.6) * _lowpass(f, 4500.0, 4))
    tone = np.sin(_tone(body * (1 + 0.35 * np.exp(-t / 0.01)), n)) * np.exp(-t / 0.05)
    gate_env = np.where(t < gate, 1.0, np.cos(0.5 * np.pi * np.clip((t - gate) / 0.02, 0, 1)))
    out = np.zeros((n, 2))
    for c in range(2):
        room = _filtered(rng.standard_normal(n), lambda f: _highpass(f, 900.0, 2) * _lowpass(f, 4500.0, 4) * _band(f, 2000.0, 0.9))
        room *= (1 - np.exp(-t / 0.012)) * np.exp(-t / 0.5)
        out[:, c] = (0.8 * crack + 0.9 * tone + 0.7 * room / np.abs(room).max() * np.abs(crack).max()) * gate_env
    return out / np.abs(out).max()


def _add_stereo(out: np.ndarray, start: int, sound: np.ndarray) -> None:
    """Add a stereo ``sound`` to ``out`` at ``start`` (circularly)."""
    for c in range(2):
        _circular_add(out[:, c], start, sound[:, c])


@lru_cache(maxsize=16)
def _pulsar_pulse(f_hi: float, f_lo: float, sweep: float, noise: float, seed: int, lowpass: float = 1800.0) -> np.ndarray:
    """A radio pulsar's pulse heard as sound: a dispersed chirp (high frequencies arrive first,
    falling from ``f_hi`` to ``f_lo`` Hz with time constant ``sweep / 3``) and a short burst of
    band-limited static shaped like a pulse profile; nothing above ``lowpass``; peak 1."""
    n = int((sweep + 0.07) * RATE)
    t = np.arange(n) / RATE
    freq = f_lo + (f_hi - f_lo) * np.exp(-t / (sweep / 3))
    chirp = np.sin(_tone(freq, n)) * (1 - np.exp(-t / 0.0015)) * np.exp(-t / sweep)
    width = 0.006
    profile = (t / width) * np.exp(1 - t / width)
    burst = np.random.default_rng(seed).standard_normal(n) * profile
    burst = _filtered(burst, lambda f: _highpass(f, 150.0, 2) * _lowpass(f, lowpass, 4))
    y = chirp + noise * burst / max(np.abs(burst).max(), 1e-12)
    y = _filtered(y, lambda f: _lowpass(f, lowpass, 2) * _highpass(f, 60.0, 2))
    tail = int(0.02 * RATE)
    y[-tail:] *= np.linspace(1, 0, tail)
    y = y / np.abs(y).max()
    y.setflags(write=False)
    return y


def _static(total: int, lo: float, hi: float, seed: int, wander: float = 1.5) -> np.ndarray:
    """Soft stereo radio static ``(total, 2)``: noise band-limited to ``lo``-``hi`` Hz (circular
    filter), its level wandering slowly (smoothed noise over ``wander`` s); RMS ~1."""
    rng = np.random.default_rng(seed)
    freqs = np.fft.rfftfreq(total, 1 / RATE)
    gain = _highpass(freqs, lo, 2) * _lowpass(freqs, hi, 3)
    out = np.zeros((total, 2))
    level = _circular_smooth(rng.standard_normal(total), int(wander * RATE))
    level = 0.6 + 0.4 * level / np.abs(level).max()
    for c in range(2):
        x = np.fft.irfft(np.fft.rfft(rng.standard_normal(total)) * gain, total)
        out[:, c] = x / np.sqrt(np.mean(x**2)) * level
    return out


def _ascent(rng: np.random.Generator) -> np.ndarray:
    beat, bar, seg, six = _grid(136)
    chords = (
        (45, 52, 57, 59, 60),  # Am(add9)
        (41, 53, 57, 60, 64),  # Fmaj7
        (48, 55, 60, 62, 64),  # C(add9)
        (43, 50, 55, 60, 62),  # Gsus4
        (45, 52, 55, 60, 64),  # Am7
        (41, 48, 55, 57, 60),  # Fmaj9
        (38, 50, 53, 57, 60),  # Dm7
        (40, 52, 56, 59, 64),  # E: the build
        (41, 53, 57, 60, 67),  # F(add9): the lift
        (48, 55, 60, 64, 67),  # C
        (47, 55, 57, 62, 67),  # G(add9)/B
        (45, 52, 57, 59, 64),  # Am(add9)
        (41, 53, 57, 60, 67),  # F(add9)
        (40, 52, 55, 60, 64),  # C/E
        (43, 50, 55, 60, 62),  # Gsus4
        (43, 50, 55, 59, 62),  # G
    )
    roots = (45, 41, 48, 43, 45, 41, 38, 40, 41, 48, 47, 45, 41, 40, 43, 43)
    total = len(chords) * seg
    lift = _section_curve(total, bar, [(0, 0), (16, 0), (16.02, 1), (28, 1), (32, 0)], smooth=0.08)
    open_ = _section_curve(total, bar, [(0, 0.3), (12, 0.5), (16, 0.85), (16.02, 1.0), (28, 1.0), (32, 0.3)], smooth=0.5)
    dark = _saw_chords(chords, seg, seg // 2, rng, _SAW, 28.0, 900.0)
    bright = _saw_chords(chords, seg, seg // 2, rng, _SAW, 34.0, 3200.0)
    out = 0.2 * _sweep_mix(dark, bright, open_)
    out += 0.16 * _pads(chords, roots, seg, seg // 2, rng, air=0.0, air_cycles=1, lowpass=700.0)  # warm body and sub
    out *= _pump(total, beat, 0.55, release=0.13)[:, None]
    kick = _kick(f_hi=118.0, f_lo=50.0, tau=0.16, click=0.08)
    for b in range(0, total, beat):
        if b == 16 * bar - beat:  # the gap before the lift
            continue
        _add_panned(out, b, kick * 0.78, 0.0)
    hat, ohat = _hat(), _hat(seed=5, tau=0.05, center=7000.0)
    for b in range(0, total, beat):
        _add_panned(out, b + beat // 2, ohat * 0.07 * (0.8 + 0.4 * lift[b]), 0.2)
    for k, p in enumerate(range(0, total, six)):
        if k % 2:
            _add_panned(out, p, hat * 0.035 * lift[p], 0.3 if k % 4 == 1 else -0.3)
    clap = _clap()
    for b in range(beat, total, 2 * beat):
        _add_panned(out, b, clap * (0.09 + 0.04 * lift[b]), 0.0)
    roll = [14 * bar + k * beat // 2 for k in range(8)] + [15 * bar + k * six for k in range(16)]
    for k, p in enumerate(roll):  # a clap roll: eighths in bar 15, sixteenths in bar 16, growing
        _add_panned(out, p, clap * (0.02 + 0.06 * k / (len(roll) - 1)), 0.1)
    for i, (notes, root) in enumerate(zip(chords, roots)):
        start = i * seg
        lifted = i >= 8 and i < 14
        tones = (root + 12, root + 19, root + 24, sorted(notes)[2])
        for bar_k in range(2):
            for k, idx in enumerate(_FIGURE):  # momentum's ostinato, low
                level = (0.3 if k in _ACCENTS else 0.17) * (0.8 if lifted else 1.0)
                _add_panned(out, start + bar_k * bar + k * six, _synth_bass(_hz(tones[idx]), int(0.17 * RATE), 0.05, 1300.0) * level, 0.15 if k % 2 else -0.15)
        for k in range(8):
            if lifted:  # rolling bass: the three sixteenths after each kick
                for s in (1, 2, 3):
                    _add_panned(out, start + k * beat + s * six, _synth_bass(_hz(root), int(0.12 * RATE), 0.06, 600.0) * (0.36 if s == 2 else 0.3), 0.0)
            else:  # off-beat eighths
                _add_panned(out, start + k * beat + beat // 2, _synth_bass(_hz(root), int(0.2 * RATE), 0.09, 560.0) * 0.44, 0.0)
        if 8 <= i < 14:  # the bright arp lead on the accents, sparse and soft
            upper = sorted(notes)[2:]
            for bar_k in range(2):
                for j, k in enumerate(_ACCENTS):
                    note = upper[(j + bar_k) % len(upper)] + 12
                    sound = _fm_pluck(_hz(note), int(0.45 * RATE), 0.14, 1.4, 3000.0) * 0.13
                    _echoed(out, start + bar_k * bar + k * six, sound, 0.35, 3 * six, 0.35, 2)
    rise = _riser(4 * bar / RATE, 300.0, 3000.0, seed=13)
    _add_panned(out, 16 * bar - len(rise), rise * 0.07, 0.0)
    boom = _kick(f_hi=70.0, f_lo=38.0, tau=0.8, click=0.02, seconds=2.2)
    _add_panned(out, 16 * bar, boom * 0.5, 0.0)
    return _finish(_tone_filter(out, 4600.0))


def _horizon(rng: np.random.Generator) -> np.ndarray:
    beat, bar, seg, six = _grid(132)
    chords = (
        (38, 50, 53, 57, 64),  # Dm9
        (46, 50, 53, 57, 62),  # Bbmaj7
        (43, 50, 53, 57, 58),  # Gm9
        (45, 52, 55, 57, 62),  # A7sus4
        (38, 52, 53, 57, 62),  # Dm(add9): the build
        (46, 53, 58, 60, 62),  # Bb(add9)
        (48, 55, 60, 62, 64),  # C(add9)
        (45, 52, 57, 61, 64),  # A
        (41, 53, 57, 60, 67),  # F(add9): the lift
        (40, 52, 55, 62, 64),  # C(add9)/E
        (38, 50, 53, 57, 64),  # Dm9
        (46, 53, 58, 60, 65),  # Bb(add9)
        (45, 53, 57, 60, 65),  # F/A
        (43, 50, 53, 57, 58),  # Gm9
        (46, 53, 57, 62, 64),  # Bbmaj7(#11)
        (48, 55, 58, 60, 65),  # C7sus4
    )
    roots = (38, 46, 43, 45, 38, 46, 48, 45, 41, 40, 38, 46, 45, 43, 46, 48)
    total = len(chords) * seg
    build = _section_curve(total, bar, [(0, 0), (8, 0), (16, 1), (16.02, 0), (32, 0)], smooth=0.05)
    lift = _section_curve(total, bar, [(0, 0), (16, 0), (16.02, 1), (30, 1), (32, 0)], smooth=0.08)
    open_ = _section_curve(total, bar, [(0, 0.3), (8, 0.3), (16, 0.9), (16.02, 1.0), (30, 1.0), (32, 0.3)], smooth=0.3)
    levels = [1.0 if s in _ACCENTS else 0.38 for s in range(16)]
    gate = _gate(total, six, levels, duty=0.5, floor=0.05)
    g_dark = _saw_chords(chords, seg, seg // 2, rng, _SAW, 22.0, 1100.0)
    g_bright = _saw_chords(chords, seg, seg // 2, rng, _SAW, 26.0, 3400.0, octave=1)
    hook = _sweep_mix(g_dark, g_bright, open_) * gate[:, None]  # the gated supersaw
    out = 0.3 * hook
    pad = _saw_chords(chords, seg, seg // 2, rng, _SOFT_SAW, 40.0, 1800.0)
    out += 0.14 * pad * (0.5 + 0.5 * lift)[:, None]
    out += 0.07 * _pads(chords, roots, seg, seg // 2, rng, air=0.25, air_cycles=1, lowpass=900.0)
    out *= _pump(total, beat, 0.45, release=0.15)[:, None]
    kick = _kick(f_hi=110.0, f_lo=48.0, tau=0.17, click=0.07)
    _hits(out, kick, range(0, total, beat), 0.66)
    for k in range(1, 8):  # the last half bar of the build: sixteenth kicks, growing
        _add_panned(out, 16 * bar - 2 * beat + k * six, kick * (0.18 + 0.05 * k), 0.0)
    ohat = _hat(seed=8, tau=0.06, center=6800.0)
    for b in range(0, total, beat):
        _add_panned(out, b + beat // 2, ohat * (0.04 + 0.05 * lift[b] + 0.03 * build[b]), -0.2)
    clap = _clap(seed=23, center=1500.0)
    for b in range(beat, total, 2 * beat):
        _add_panned(out, b, clap * 0.1 * (0.6 + 0.4 * lift[b]), 0.0)
    for i, root in enumerate(roots):
        start = i * seg
        if 4 <= i < 8:  # the build: the bass rests (a single long root every two bars)
            _add_panned(out, start, _synth_bass(_hz(root), int(1.6 * RATE), 0.6, 450.0) * 0.4, 0.0)
            continue
        for k in range(8):  # momentum's off-beat bass, a pickup sixteenth on beat 4
            _add_panned(out, start + k * beat + beat // 2, _synth_bass(_hz(root), int(0.21 * RATE), 0.1, 560.0) * 0.38, 0.0)
            if k % 4 == 3:
                _add_panned(out, start + k * beat + 3 * six, _synth_bass(_hz(root + 12), int(0.1 * RATE), 0.05, 700.0) * 0.26, 0.0)
    rise = _riser(8 * bar / RATE, 250.0, 3200.0, seed=17)
    _add_panned(out, 16 * bar - len(rise), rise * 0.065, 0.0)
    boom = _kick(f_hi=68.0, f_lo=37.0, tau=0.9, click=0.02, seconds=2.4)
    _add_panned(out, 16 * bar, boom * 0.5, 0.0)
    return _finish(_tone_filter(out, 4600.0))


def _beacon(rng: np.random.Generator) -> np.ndarray:
    beat, bar, seg, six = _grid(120)
    chords = (
        (40, 52, 54, 55, 59),  # Em(add9)
        (36, 52, 55, 59, 62),  # Cmaj9
        (38, 50, 55, 59, 66),  # G/D
        (47, 54, 57, 59, 64),  # Bm7sus4
        (40, 50, 55, 59, 66),  # Em9
        (45, 52, 57, 59, 60),  # Am(add9)
        (36, 52, 54, 59, 64),  # Cmaj7(#11)
        (38, 50, 57, 62, 64),  # Dsus2
        (40, 52, 54, 55, 59),  # Em(add9)
        (36, 52, 55, 59, 62),  # Cmaj9
        (45, 52, 57, 59, 64),  # Asus2
        (47, 52, 54, 57, 64),  # B7sus4
    )
    roots = (40, 36, 38, 47, 40, 45, 36, 38, 40, 36, 45, 47)
    total = len(chords) * seg
    u = np.arange(total) / total
    out = 0.34 * _pads(chords, roots, seg, seg // 2, rng, air=0.15, air_cycles=1, lowpass=1300.0)
    shimmer = _saw_chords([sorted(c)[2:] for c in chords], seg, seg // 2, rng, (1.0, 0.25, 0.08), 45.0, 4200.0, octave=2, fade_s=0.8)
    out += 0.06 * shimmer * (0.4 + 0.6 * np.sin(2 * np.pi * u) ** 2)[:, None]
    out *= _pump(total, beat, 0.3, release=0.22)[:, None]
    out += 0.006 * _static(total, 1800.0, 4200.0, seed=77)
    kick = _kick(f_hi=80.0, f_lo=44.0, tau=0.2, click=0.03)
    _hits(out, kick, range(0, total, beat), 0.74)
    main = _pulsar_pulse(1400.0, 160.0, 0.035, 0.6, seed=61)
    inter = _pulsar_pulse(1100.0, 200.0, 0.025, 0.8, seed=62)
    for b in range(0, total, bar):  # the beacon: a main pulse on 1 and 3, interpulses on the other accents
        for k in _ACCENTS:
            is_main = k in (0, 8)
            _add_panned(out, b + k * six, (main * 0.15 if is_main else inter * 0.085), 0.0 if is_main else (0.35 if k in (3, 11) else -0.35))
    for i, (notes, root) in enumerate(zip(chords, roots)):
        start = i * seg
        tones = (root + 12, root + 19, root + 24, sorted(notes)[2])
        for bar_k in range(2):
            for k, idx in enumerate(_FIGURE):  # the ostinato, lower and softer than momentum's
                level = 0.2 if k in _ACCENTS else 0.1
                _add_panned(out, start + bar_k * bar + k * six, _synth_bass(_hz(tones[idx]), int(0.16 * RATE), 0.05, 900.0) * level, 0.2 if k % 2 else -0.2)
        for k in range(8):
            sub = _partials(_hz(root), int(0.24 * RATE), 0.12, 0.006, ((1.0, 1.0, 1.0), (2.0, 0.3, 0.6), (3.0, 0.1, 0.4)), 500.0)
            _add_panned(out, start + k * beat + beat // 2, sub * 0.5, 0.0)
    return _finish(_tone_filter(out, 4200.0))


def _neon(rng: np.random.Generator) -> np.ndarray:
    beat, bar, seg, six = _grid(116)
    chords = (
        (42, 54, 57, 61, 68),  # F#m(add9)
        (38, 54, 57, 61, 62),  # Dmaj7
        (45, 52, 57, 59, 61),  # A(add9)
        (40, 52, 56, 59, 61),  # E6
        (42, 52, 57, 61, 64),  # F#m7
        (38, 52, 54, 57, 61),  # Dmaj9
        (47, 54, 57, 61, 62),  # Bm9
        (49, 54, 56, 61, 66),  # C#7sus4
        (42, 54, 57, 61, 68),  # F#m(add9)
        (38, 54, 56, 57, 61),  # Dmaj7(#11)
        (40, 52, 54, 56, 59),  # E(add9)
        (49, 53, 56, 61, 65),  # C#
    )
    roots = (42, 38, 45, 40, 42, 38, 47, 37, 42, 38, 40, 37)
    total = len(chords) * seg
    pads = _saw_chords(chords, seg, seg // 2, rng, _SOFT_SAW, 24.0, 1700.0, fade_s=0.5)
    out = 0.24 * pads + 0.1 * _pads(chords, roots, seg, seg // 2, rng, air=0.3, air_cycles=2, lowpass=1500.0)
    out *= _pump(total, beat, 0.3, release=0.18)[:, None]
    kick = _kick(f_hi=95.0, f_lo=48.0, tau=0.2, click=0.06)
    _hits(out, kick, range(0, total, beat), 0.74)
    snare = _gated_snare(seed=91)
    for b in range(beat, total, 2 * beat):
        _add_stereo(out, b, snare * 0.12)
    hat = _hat(seed=4, tau=0.018, center=6000.0)
    for k, p in enumerate(range(0, total, six)):
        _add_panned(out, p, hat * (0.05 if k % 4 == 2 else 0.022), 0.3 if k % 2 else -0.3)
    for i, (notes, root) in enumerate(zip(chords, roots)):
        start = i * seg
        for k in range(16):  # octave bass on the eighths
            note = root + (12 if k % 2 else 0)
            b = _analog_bass(_hz(note), int(0.2 * RATE), 0.12, 1400.0, 260.0, 0.05)
            _add_panned(out, start + k * beat // 2, b * (0.32 if k % 2 == 0 else 0.25), 0.0)
        tones = sorted(notes)[1:]
        for bar_k in range(2):  # the square-pluck arpeggio, the figure turned around in the second bar
            for k in range(16):
                idx = _FIGURE[k] if bar_k == 0 else (3 - _FIGURE[k]) % 4
                note = tones[idx % len(tones)] + 12
                level = 0.12 if k in _ACCENTS else 0.055
                _add_panned(out, start + bar_k * bar + k * six, _square_pluck(_hz(note), int(0.25 * RATE), 0.09, 2200.0) * level, 0.3 if k % 2 else -0.3)
    return _finish(_tone_filter(out, 4400.0))


def _score_bed(name: str) -> Callable[[np.random.Generator], np.ndarray]:
    """The generator of a bed written as a score file (``studio/beds/<name>.yaml``, package data):
    the file rendered by :func:`vidgen.studio.render_music_score` — a seamless loop at
    :data:`MUSIC_LEVEL`, float32, read-only; the same file gives the same samples."""

    def generate(rng: np.random.Generator) -> np.ndarray:
        from vidgen.studio import load_music_score, render_music_score
        from vidgen.studio.templates import TEMPLATE_DIR

        return render_music_score(load_music_score(TEMPLATE_DIR / f"{name}.yaml"))

    return generate


def _loop_seconds(tempo: int, bars: int) -> float:
    """The length of ``bars`` bars of 4/4 at ``tempo`` BPM as the beds count it (whole samples per beat)."""
    return RATE * 60 // tempo * 4 * bars / RATE


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
        Bed(
            "discovery", _discovery, _loop_seconds(104, 24), 104, "D minor",
            ("Dm(add9)", "Bbmaj7", "Fadd9", "Csus2", "Dm7", "Gm9", "Bbmaj9", "Asus4", "Dm(add9)", "Bb(add#11)", "Gm7", "A"),
            "A steady, forward-moving documentary bed at 104 BPM in D minor, 4/4: a soft kick on every "
            "beat, a pulsing synth bass in eighth notes (A1 to F2, an octave up on the last eighth of "
            "each chord), a plucked minor arpeggio in eighths, soft off-beat hi-hats, and a pad that "
            "opens slowly from dark to bright over the loop (brightest about three quarters through) "
            "and dips gently with each kick; 24 bars, a chord every two bars (4.6 s), A major leading "
            "back to the top. Rolled off above ~4 kHz; bass-heavy (57% of its power under 150 Hz: "
            "lighter on phone speakers); curious, purposeful, building.",
            "documentaries approaching a discovery, science stories, explainers that build to a finding",
        ),
        Bed(
            "breakthrough", _breakthrough, _loop_seconds(112, 24), 112, "C minor to E-flat major",
            ("Cm(add9)", "Abmaj7", "Fm9", "Cm(add9)/G", "Abmaj7(#11)", "G7sus4", "Eb(add9)", "Bb(add9)/D", "Abmaj9", "Eb/G", "Bb(add9)", "G"),
            "A two-part bed at 112 BPM in C minor, 4/4, that lifts to E-flat major halfway, 25.7 s into "
            "the loop. The first 12 bars hold tension: a soft kick on beats 1 and 3, staccato synth-bass "
            "quarter notes, a dark plucked arpeggio, a quiet sixteenth-note tick that grows, and a soft "
            "noise riser into the lift. The last 12 bars release it: a deep low boom on the lift, a kick "
            "on every beat, driving eighth-note bass, the arpeggio an octave higher, an open pad dipping "
            "with each kick and off-beat hi-hats; a G chord turns back to C minor at the top. A chord "
            "every two bars (4.3 s). Rolled off above ~4 kHz; bass-heavy (59% of its power under 150 Hz: "
            "lighter on phone speakers); suspense, then a reveal.",
            "a reveal or result that lands mid-video, problem-to-solution stories, before / after",
        ),
        Bed(
            "enigma", _enigma, _loop_seconds(96, 20), 96, "B minor",
            ("Bm(add9)", "Gmaj7(#11)", "Esus2", "F#sus4", "Bm(add9)", "Dmaj7/A", "Gmaj7(#11)", "Em9", "Cmaj7(#11)", "F#sus4"),
            "A dark, mysterious bed at 96 BPM in B minor, 4/4, with suspended chords and a Neapolitan "
            "C major: a deep sub-bass pulse on every beat (A1 to G2), a soft felt kick on beats 1 and 3, "
            "a dark, muffled pad that breathes with the pulse, a sparse piano motif (B3 to C#5, a few "
            "notes every two bars) with ping-pong echoes, and a faint high bell (B5 or F#5) with echoes "
            "every eight bars; 20 bars, a chord every two bars (5 s), F#sus4 leading back to the top. "
            "Rolled off above ~3.5 kHz; bass-heavy (65% of its power under 150 Hz: lighter on "
            "phone speakers) and quiet in the voice's range; mysterious, unresolved, searching.",
            "mysteries and unsolved questions, investigations, history or true-crime style stories, space and the deep sea",
        ),
        Bed(
            "momentum", _momentum, _loop_seconds(120, 24), 120, "G minor",
            ("Gm(add9)", "Ebmaj7", "Cm9", "Dsus4(add9)", "Gm7", "Ebmaj9", "Bb(add9)", "F(add9)", "Cm9", "Ebmaj7", "Dsus4", "D"),
            "The most energetic documentary bed, at 120 BPM in G minor, 4/4: a driving synth ostinato in sixteenth "
            "notes accented 3+3+2 (C3 to B-flat 4, slightly left / right), a kick on every beat, synth "
            "bass on the off-beat eighths, a soft clap on beats 2 and 4, sixteenth-note hi-hats, a pad "
            "that pumps with the kick and a soft noise riser into the top of the loop; 24 bars, a chord "
            "every two bars (4 s), D major leading back to G minor. Rolled off above ~4.5 kHz; "
            "bass-heavy (61% of its power under 150 Hz: lighter on phone speakers); urgent, driving.",
            "fast-paced explainers and Shorts, montages, countdowns, races and high-energy intros",
        ),
        Bed(
            "lab", _lab, _loop_seconds(108, 20), 108, "F minor",
            ("Fm9", "Dbmaj7", "Bbm9", "Ebsus2", "Fm9", "Abmaj7", "Dbmaj7(#11)", "Bbm7", "Gm7b5", "C7"),
            "A modern tech bed at 108 BPM in F minor, 4/4: a steady kick on every beat, a rolling, "
            "syncopated synth bass, syncopated electronic (FM) plucks (E4 to G5) with ping-pong echoes, "
            "light glitchy clicks left and right (a short rising stutter every fourth bar), a soft snap "
            "on beats 2 and 4, and a thin pad that pumps with the kick; 20 bars, a chord every two bars "
            "(4.4 s), C7 leading back to the top. Rolled off above ~4.5 kHz; bass-heavy (67% of its "
            "power under 150 Hz: lighter on phone speakers); clean, precise, electronic.",
            "technology, AI, software and engineering explainers, lab science, product demos with a modern feel",
        ),
        Bed(
            "ascent", _ascent, _grid_seconds(136, 32), 136, "A minor",
            ("Am(add9)", "Fmaj7", "C(add9)", "Gsus4", "Am7", "Fmaj9", "Dm7", "E",
             "F(add9)", "C", "G(add9)/B", "Am(add9)", "F(add9)", "C/E", "Gsus4", "G"),
            "An uplifting-trance bed at 136 BPM in A minor, 4/4, that builds and lifts. Bars 1-12 "
            "groove: a kick on every beat, off-beat synth bass, a low synth ostinato in sixteenth notes "
            "accented 3+3+2 (D3 to C5), a half-open supersaw pad pumping with the kick, open hi-hats "
            "on the off-beats, a soft clap on 2 and 4. Bars 13-16 build: the supersaw's filter opens, "
            "a noise riser, a clap roll (eighths, then sixteenths), the last kick dropped. At 28.2 s the "
            "lift: a deep low boom, bright major-key chords (F, C, G, A minor), a bass rolling on the "
            "sixteenths after each kick, the supersaw wide open, a soft bright electronic (FM) "
            "arpeggio (G4 to G5) on the 3+3+2 accents with echoes, sixteenth-note hi-hats; after 12 "
            "bars it settles back for four (Gsus4, G, back to A minor at the top). 32 bars, a chord "
            "every two bars (3.5 s). Rolled off above ~4.5 kHz; bass-heavy (71% of its power under "
            "150 Hz: lighter on phone speakers); energetic, hopeful, euphoric.",
            "energetic reveals, tech launches, montages, uplifting endings, a build to a climax",
            seed="trance_a",
        ),
        Bed(
            "horizon", _horizon, _grid_seconds(132, 32), 132, "D minor to F major",
            ("Dm9", "Bbmaj7", "Gm9", "A7sus4", "Dm(add9)", "Bb(add9)", "C(add9)", "A",
             "F(add9)", "C(add9)/E", "Dm9", "Bb(add9)", "F/A", "Gm9", "Bbmaj7(#11)", "C7sus4"),
            "An anthemic uplifting-trance bed at 132 BPM in D minor, 4/4, that lifts to F major "
            "halfway, 29.1 s into the loop. Its hook is a gated supersaw: the chords chopped into "
            "sixteenth notes, accented 3+3+2. Bars 1-8 groove: a kick on every beat, off-beat synth "
            "bass with a pickup sixteenth, the gate on a dark supersaw, a soft clap on 2 and 4, open "
            "off-beat hi-hats. Bars 9-16 build: the bass rests (one long note every two bars), the "
            "gate's filter opens, a long noise riser, sixteenth-note kicks in the last half bar. At the "
            "lift: a deep low boom, the bass back, the gate an octave higher and bright over a soft "
            "supersaw pad, louder hi-hats, for 14 bars, settling over the last two; C7sus4 leads "
            "back to the top. 32 bars, a chord every two bars (3.6 s). Rolled off above ~4.5 kHz; "
            "the most bass-heavy (78% of its power under 150 Hz: lighter on phone speakers); bright, "
            "anthemic, soaring.",
            "energetic reveals, tech launches, montages, uplifting endings, anthemic intros",
            seed="trance_b",
        ),
        Bed(
            "beacon", _beacon, _grid_seconds(120, 24), 120, "E minor",
            ("Em(add9)", "Cmaj9", "G/D", "Bm7sus4", "Em9", "Am(add9)", "Cmaj7(#11)", "Dsus2", "Em(add9)", "Cmaj9", "Asus2", "B7sus4"),
            "A cosmic bed at 120 BPM in E minor, 4/4, built on a ticking beacon like a radio pulsar: "
            "short dispersed pulses (a chirp falling from ~1.4 kHz with a burst of soft static) on "
            "the 3+3+2 sixteenths, a strong main pulse on beats 1 and 3 in the centre and weaker "
            "pulses left and right, the same in every bar like a lighthouse. Under it a deep kick on "
            "every beat, off-beat sub bass (C2 to B2), a low, soft synth ostinato in sixteenth notes "
            "(C3 to B4), a deep space pad low-passed at 1.3 kHz breathing with a slow side-chain, a "
            "soft shimmer two octaves up swelling twice per loop and faint radio static. 24 bars, a "
            "chord every two bars (4 s), B7sus4 leading back to the top. Rolled off above ~4 kHz; "
            "bass-heavy (72% of its power under 150 Hz: lighter on phone speakers) and the quietest "
            "in the voice's range; steady, spacious, curious.",
            "space and astronomy, science, signals and data, steady explainers with a cosmic feel",
            seed="pulsar_a",
        ),
        Bed(
            "neon", _neon, _grid_seconds(116, 24), 116, "F-sharp minor",
            ("F#m(add9)", "Dmaj7", "A(add9)", "E6", "F#m7", "Dmaj9", "Bm9", "C#7sus4", "F#m(add9)", "Dmaj7(#11)", "E(add9)", "C#"),
            "A synthwave night-drive bed at 116 BPM in F-sharp minor, 4/4: a steady kick on every "
            "beat, a big gated-reverb snare on 2 and 4, an analog bass bouncing in octaves on the "
            "eighth notes (C#2 to B3, its filter snapping open on each note), a square-wave pluck "
            "arpeggio in sixteenth notes accented 3+3+2 (E4 to G#5, left / right), warm detuned saw "
            "pads breathing with a light side-chain and soft sixteenth-note hi-hats. 24 bars, a chord "
            "every two bars (4.1 s), C# major leading back to the top. Rolled off above ~4.5 kHz; "
            "bass-heavy (71% of its power under 150 Hz: lighter on phone speakers); retro, "
            "nocturnal, cool, driving.",
            "tech at night, retro-futurism, cities, coding Shorts",
            seed="night_drive_a",
        ),
        Bed(
            "tidewater", _score_bed("tidewater"), _grid_seconds(108, 24), 108, "E minor",
            ("Em", "C", "Em", "C", "G", "D", "C", "D", "Em", "Em", "Em", "C"),
            "A steady, hopeful bed at 108 BPM in E minor, 4/4, written as a score file. Bars 1-4 "
            "intro: a warm pad and a plucked arpeggio in sixteenth notes accented 3+3+2 (C4 to G5, "
            "slightly left). Bars 5-12 build: a soft kick on every beat, off-beat hi-hats and a "
            "syncopated synth bass (C2 to G3), a noise riser over the last two bars. At 26.7 s the "
            "lift (bars 13-20, C, D, E minor): a deep low boom, the pad opens brighter, a clap on 2 "
            "and 4, busier hats and a sparse bell melody (D5 to E6, slightly right). Bars 21-24 "
            "settle back to the opening chords. 24 bars, a chord every two bars (4.4 s). Rolled off "
            "above ~4.5 kHz; 39% of its power under 150 Hz (lighter in the bass than the "
            "documentary beds); hopeful, flowing, gently driving.",
            "explainers and documentaries that need a steady, hopeful pulse: nature, the sea, travel, "
            "progress stories, calm walkthroughs",
            score=True,
        ),
        Bed(
            "skyline", _score_bed("skyline"), _grid_seconds(128, 32), 128, "D minor",
            ("Dm", "Bb", "F", "C", "Dm", "Bb", "F", "C", "Bb", "C", "Dm", "Dm", "F", "C", "Dm", "Bb"),
            "A pumping supersaw bed at 128 BPM in D minor, 4/4, written as a score file, that builds "
            "and lifts. Bars 1-8 intro: a dark, filtered cloud of supersaw chords over a soft pad and "
            "sub, ticking pulsar pulses on the 3+3+2 sixteenths left and right, faint radio static; "
            "no kick. Bars 9-16 build (from 15 s): a kick on every beat, the supersaw's filter opens "
            "under a sixteenth-note trance gate, off-beat analog bass (C2 to B-flat 2), an electronic "
            "(FM) arpeggio (C4 to B-flat 5) with echoes, open hi-hats growing, a noise riser over the "
            "last four bars and a kick roll into the lift. At 30 s the lift (bars 17-28, B-flat, C, "
            "D minor, F, C): a deep low boom, the supersaw wide open and pumping with the kick, a "
            "rolling bass, a clap on 2 and 4, sixteenth hi-hats and a soft lead melody (G4 to C6) "
            "in a hall with echoes. Bars 29-32 the filter closes and the saws fade back to the "
            "intro. 32 bars, a chord every two bars (3.75 s). Rolled off above ~4.5 kHz; bass-heavy "
            "(63% of its power under 150 Hz: lighter on phone speakers); bright, energetic, euphoric.",
            "energetic reveals, product launches, montages, a build to a big moment, upbeat intros and endings",
            score=True,
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
    return bed.generate(np.random.default_rng(zlib.crc32(f"music:{bed.seed or name}".encode("utf-8"))))


# ----- sources -------------------------------------------------------------------------------------


def is_bed(source: str) -> bool:
    """Whether ``source`` names a built-in bed (else it is a file path)."""
    return source in BUILTIN_BEDS


def source_kind(cue: MusicCue, root: Path | None = None) -> str:
    """``composed`` (``compose:``), ``bed`` (a built-in bed), ``score`` (a project piece: a score
    file, :mod:`vidgen.music_pieces`) or ``file``. ``root``: the project's folder (a name
    without a suffix that is a file there stays a file)."""
    from vidgen.music_pieces import is_score_source

    if cue.compose is not None:
        return "composed"
    assert cue.source is not None
    if is_bed(cue.source):
        return "bed"
    return "score" if is_score_source(cue.source, root) else "file"


def cue_scene_range(cue: MusicCue, scene_ids: Sequence[str]) -> tuple[int, int]:
    """The indices of the first and last scene ``cue`` plays over (``from`` / ``to``, default the
    video's first / last scene)."""
    first = list(scene_ids).index(cue.from_) if cue.from_ else 0
    last = list(scene_ids).index(cue.to) if cue.to else len(scene_ids) - 1
    return first, last


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
    without the ``music`` extra its mood's bed plays instead (a warning says so). ``fitted``: the
    score composed for the cue's span (:mod:`vidgen.musicfit`), played once from its start."""

    def __init__(self, cue: MusicCue, root: Path, soundfont: str | None = None, cache_dir: Path | None = None, fitted: Score | None = None) -> None:
        kind = source_kind(cue, root)
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
            start = cue.start
            if cue.section is not None and kind == "bed":  # a score bed's section (DESIGN.md §93.13)
                from vidgen.music_pieces import section_start

                start += section_start(cue, root)
            self.offset = round(start * RATE) % len(data)
            self.loop = True
            self.length = len(data)
            return
        if kind == "composed":
            self._composed(cue, root, soundfont, cache_dir, fitted)
            return
        if kind == "score":
            self._piece(cue, root, cache_dir)
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

    def _composed(self, cue: MusicCue, root: Path, soundfont: str | None, cache_dir: Path | None, fitted: Score | None) -> None:
        """Composed music: the piece plus its reverb tail; looped, the tail is added onto the
        piece's start (the piece ends turning back to its beginning), so it repeats without a
        seam, and ``start`` wraps around the piece. A ``fitted`` piece plays once, from its start."""
        from vidgen import soundfont as soundfonts
        from vidgen.synth import render_score

        score = fitted if fitted is not None else composed_score(cue)
        audio = render_score(score, soundfonts.resolve(soundfont, root), cache_dir)  # at the music level
        piece = min(len(audio), round(score.length_seconds * RATE))
        first = 0 if fitted is not None else round(cue.start * RATE) % piece
        self.seamless = False
        self.offset = 0
        self.loop = cue.loop and fitted is None
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

    def _piece(self, cue: MusicCue, root: Path, cache_dir: Path | None) -> None:
        """A project piece (a score file, DESIGN.md §93.10), rendered (cached in ``cache_dir``):
        a ``loop: true`` piece under a looping cue repeats seamlessly from ``start`` (wrapping
        round, as a bed); otherwise it plays once from ``start`` (a loop piece's ``start`` wraps,
        a one-shot's may not pass its end) and the cue's fade-out applies at its end."""
        from vidgen.music_pieces import piece_audio, piece_path, section_start

        assert cue.source is not None
        audio, score = piece_audio(piece_path(cue.source, root), cache_dir)
        start = cue.start + section_start(cue, root)
        first = round(start * RATE)
        if score.loop:
            first %= len(audio)
        elif first >= len(audio):
            raise VidgenError(f"music: start {start:g} s is past the end of {cue.source} ({len(audio) / RATE:.1f} s with its ending)")
        self.offset = 0
        self.loop = score.loop and cue.loop
        self.seamless = self.loop
        if self.loop:
            self.data, self.offset = audio, first
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
    """``(location, message)`` problems of the ``music:`` cues: a source that is neither a bed, a
    project piece nor a file under the project, a bed's name that is also a project piece, the
    problems of the pieces' score files (``where: what``; ``compose:`` settings are checked
    when the config loads) and a ``section`` the source does not have."""
    from vidgen.music_pieces import bed_conflict, piece_path, score_problems, section_problem

    found: list[tuple[str, str]] = []
    cues = config.music_cues
    for k, cue in enumerate(cues):
        where = "music" if not isinstance(config.music, list) else f"music[{k}]"
        kind = source_kind(cue, root)
        if cue.section is not None and root is not None:
            problem = section_problem(cue, root)
            if problem is not None:
                found.append((f"{where}.section", problem))
        if root is None or kind in ("composed", "bed"):
            conflict = None if root is None or kind != "bed" else bed_conflict(cue.source or "", root)
            if conflict is not None:
                found.append((f"{where}.source", conflict))
            continue
        assert cue.source is not None
        if kind == "score":
            try:
                path = piece_path(cue.source, root)
            except VidgenError as exc:
                found.append((f"{where}.source", str(exc)))
                continue
            rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
            found.extend((f"{where}.source", f"{rel}: {problem}") for problem in score_problems(path))
            continue
        path = root / cue.source
        if not path.is_file():
            close = difflib.get_close_matches(cue.source.lower(), list(BUILTIN_BEDS), n=1, cutoff=0.7)
            guess = f"; did you mean '{close[0]}'?" if close else ""
            hint = f"; built-in beds: {', '.join(BUILTIN_BEDS)}, or compose: {{mood: ...}} (vidgen list-music)"
            found.append((f"{where}.source", f"neither a built-in bed nor a file: {cue.source} (looked for {path}){guess}{hint}"))
    return found


def music_warnings(config: VideoConfig) -> list[str]:
    """``vidgen validate`` warnings about composed music (DESIGN.md §83, §85): without the
    ``music`` extra the moods' beds play instead (named, with the install command); with it, the
    default SoundFont not downloaded yet (the first render downloads it)."""
    from vidgen import soundfont
    from vidgen.synth import symusic_status

    cues = [c for c in config.music_cues if c.compose is not None]
    if not cues:
        return []
    beds = [(cue.label, fallback_bed(cue)) for cue in cues]
    if any(bed is not None for _, bed in beds):
        plays = ", ".join(f"{label} plays the bed '{bed}'" for label, bed in beds if bed is not None)
        scene_moods = " (scenes' compose settings are not played)" if any(_compose_keys(s.music) for s in config.scenes) else ""
        return [f"music: composed music needs the music extra (symusic {symusic_status()}); until then {plays}{scene_moods}"]
    if config.soundfont is None and not soundfont.default_path().is_file():
        return [
            f"music: composed music plays with the {soundfont.NAME} SoundFont, not downloaded yet: run `vidgen soundfont "
            f"fetch` ({soundfont.SIZE_BYTES / 1e6:.1f} MB, once) or the first render downloads it; offline, set soundfont: PATH"
        ]
    return []


def music_summary(config: VideoConfig, root: Path | None = None) -> list[dict[str, Any]]:
    """What each music cue plays, for ``vidgen validate``: ``{source, kind, plays, fitted, from,
    to, scenes}`` (``plays``: ``composed``, ``bed <name>``, ``score`` or ``file``; ``fitted``:
    composed for the video's timings; ``scenes``: scene id → the compose settings it changes).
    ``root``: the project's folder (tells a project piece from a file without a suffix)."""
    from vidgen.musicfit import is_fitted

    out = []
    ids = [s.id for s in config.scenes]
    for cue in config.music_cues:
        kind = source_kind(cue, root)
        bed = cue.source if kind == "bed" else fallback_bed(cue)
        first, last = cue_scene_range(cue, ids)
        changes = {}
        if is_fitted(cue) and bed is None:
            changes = {s.id: _compose_keys(s.music) for s in config.scenes[first : last + 1] if _compose_keys(s.music)}
        out.append(
            {
                "source": cue.label,
                "kind": kind,
                "plays": f"bed {bed}" if bed is not None else kind,
                "fitted": is_fitted(cue) and bed is None,
                "from": cue.from_,
                "to": cue.to,
                "scenes": changes,
            }
        )
    return out


def _compose_keys(scene_music: Any) -> list[str]:
    """The compose settings a scene's ``music:`` changes (none for ``true`` / ``false``)."""
    keys = getattr(scene_music, "compose_keys", None)
    return list(keys) if keys else []


def music_summary_line(entry: dict[str, Any]) -> str:
    """One :func:`music_summary` entry as ``vidgen validate`` prints it."""
    text = entry["source"]
    if entry["kind"] == "composed":
        text += ", composed for the video" if entry["fitted"] else (", looped" if entry["plays"] == "composed" else "")
        if entry["plays"] != "composed":
            text += f" -> {entry['plays']} (no music extra)"
    elif entry["kind"] == "score":
        text += ", a project piece (score file, rendered at the join)"
    span = f" ({entry['from'] or 'start'} to {entry['to'] or 'end'})" if entry["from"] or entry["to"] else ""
    scenes = "; ".join(f"{sid}: {', '.join(keys)}" for sid, keys in entry["scenes"].items())
    return text + span + (f"; scenes {scenes}" if scenes else "")


def project_music(root: Path | None) -> list[Path]:
    """The audio files under the project's ``assets/music`` (sorted)."""
    folder = None if root is None else root / PROJECT_MUSIC_DIR
    if folder is None or not folder.is_dir():
        return []
    return [p for p in sorted(folder.rglob("*")) if p.is_file() and p.suffix.lower() in MUSIC_SUFFIXES]


def _decibels(value: float) -> float | None:
    return round(value, 1) if math.isfinite(value) else None


def music_entries(root: Path | None, preview_dir: Path | None = None) -> list[dict[str, Any]]:
    """The beds, the project's pieces (score files, origin ``score``,
    :func:`vidgen.music_pieces.piece_entry`: also ``path``, ``title``, ``time``, ``bars``,
    ``loop``, ``sections``, ``problems``) and the project's ``assets/music`` files described for
    ``vidgen list-music``: ``{name, origin, description, use, tempo, key, chords, loop_seconds,
    duration, channels, loudness, preview}`` (beds: their loop; files: as decoded; ``preview``: a
    WAV of the bed written to ``preview_dir``, else ``None``)."""
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
    if root is not None:
        from vidgen.music_pieces import piece_entry, project_pieces

        entries.extend(piece_entry(name, path, root) for name, path in project_pieces(root).items())
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
