"""Background music (DESIGN.md §48): three procedurally generated ambient beds, the project's
own music files, and the sources the mix reads from.

A *bed* is a seamless loop made of a slowly evolving chord progression (numpy only, no
recordings, deterministic): sustained pads are built with the PADsynth method — each chord's
harmonics as narrow Gaussian bumps of a spectrum with seeded random phases, turned into a
periodic wave by one inverse FFT — and cross-faded from chord to chord; plucked arpeggios and
bells are added note by note. Everything is rendered *circularly* (notes running past the loop's
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
from vidgen.sfx import RATE, _highpass, _lowpass, decode_audio, write_wav

if TYPE_CHECKING:
    from vidgen.config import MusicCue, VideoConfig

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
    )
}


@lru_cache(maxsize=4)
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
    (a file with a cross-faded seam, a bed seamlessly) or ending, at :data:`MUSIC_LEVEL`."""

    def __init__(self, cue: MusicCue, root: Path) -> None:
        if is_bed(cue.source):
            data = bed_loop(cue.source)
            self.seamless = True
            self.data = data
            self.offset = round(cue.start * RATE) % len(data)
            self.loop = True
        else:
            path = root / cue.source
            if not path.is_file():
                raise VidgenError(f"music file not found: {cue.source} (looked for {path})")
            audio, level = file_audio(path)
            first = round(cue.start * RATE)
            if first >= len(audio):
                raise VidgenError(f"music: start {cue.start:g} s is past the end of {cue.source} ({len(audio) / RATE:.1f} s)")
            gain = 10 ** ((MUSIC_LEVEL - level) / 20) if math.isfinite(level) else 1.0
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
    a file under the project."""
    found: list[tuple[str, str]] = []
    cues = config.music_cues
    for k, cue in enumerate(cues):
        where = "music" if not isinstance(config.music, list) else f"music[{k}]"
        if is_bed(cue.source) or root is None:
            continue
        path = root / cue.source
        if not path.is_file():
            hint = f"; built-in beds: {', '.join(BUILTIN_BEDS)} (vidgen list-music)"
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
