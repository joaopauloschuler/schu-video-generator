"""``vidgen music check`` (DESIGN.md §93.9): what a piece will sound like under narration, in
words and numbers, for agents who cannot listen — loudness and its steadiness, peaks and
clipping, the tempo heard against the score's, the loop's seam, how much sound sits in the
voice's range, the bass weight, harsh highs, whether each section does its job (does the lift
lift? does the build build?) and the key — with advice that names the score's keys to change.

A score is played track by track (:func:`vidgen.studio.render.render_music_stems`), so each
problem is put down to the tracks that cause it. The limits were set on the 14 built-in beds
and their templates (all fine; the two score beds of Step 190 and the per-chord and lift checks
of Step 191 calibrated on all 16 templates, the shipped piece and the cookbook's sketches) and on
deliberately bad scores (all flagged); §93.9 and §93.13 have the numbers. Pictures (:func:`spectrogram_image`) and the narration demo (:func:`narration_demo`)
are made here; the command writes them.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from vidgen.loudness import LoudnessMeter, integrated_loudness, kweighted_power, peak_envelope
from vidgen.music import MUSIC_LEVEL
from vidgen.sfx import RATE, _highpass, _lowpass, decode_audio
from vidgen.studio import measure
from vidgen.studio.render import render_music_stems
from vidgen.studio.score_file import ChordSlot, MusicScore, Section, Track
from vidgen.studio.theory import note_name

#: The narration sample the demo plays when no ``--narration`` is given: two original lines
#: spoken by Kokoro (``af_heart``, Apache-2.0), 20 s with the music alone at the end.
NARRATION_SAMPLE = Path(__file__).parent / "data" / "narration_sample.mp3"
#: The level vidgen's narration sits at (integrated, as stereo; DESIGN §48: the kphi3 MP3s).
NARRATION_LUFS = -21.5
#: vidgen's default ducking (``DuckConfig()``: depth dB, attack s, release s, hold s); a test
#: keeps them equal.
DUCK = (12.0, 0.4, 1.0, 1.5)
#: The demo's final level, as a video's mix (``audio.target_lufs``, ``audio.true_peak``).
DEMO_LUFS, DEMO_TRUE_PEAK = -16.0, -1.5
#: Frequency bands (Hz) measured per frame.
BANDS = {"bass": (20.0, 150.0), "voice": (300.0, 3000.0), "bright": (2000.0, 20000.0), "highs": (5000.0, 20000.0), "all": (20.0, 20000.0)}
#: Bumped when the check's measures, limits or words change (cached reports of project pieces,
#: ``vidgen.music_pieces.piece_check``, are then made again). 2: Step 191 (per-chord fit, lifts).
CHECK_VERSION = 2
#: Block length (s) standing in for bars when an audio file is checked.
BLOCK_SECONDS = 2.0
#: Section names that are meant to lift / to build.
LIFT_NAMES = ("lift", "drop", "chorus", "climax", "peak", "high")
BUILD_NAMES = ("build", "buildup", "build_up", "rise", "riser", "climb")
#: Instruments that mark a change rather than carry a section (the advice does not suggest them for a lift).
TRANSITION_INSTRUMENTS = ("riser", "boom")
#: Ratios of the heard tempo to the score's that are the same beat heard another way: double /
#: half time, and the 2/3 (or 4/3) a 3+3+2 figure makes the onsets show.
TEMPO_RATIOS = {1.0: "", 2.0: "double time", 0.5: "half time", 2 / 3: "2/3", 1.5: "3/2", 4 / 3: "4/3", 0.75: "3/4"}

#: The limits (calibrated: §93.9, §93.13). Each is crossed by none of the 16 beds or their templates.
LIMITS = {
    "steadiness_db": 8.0,  # 3 s loudness p10..p95 range (beds 0.5-1.5, skyline_lift 4.1); over: it swings under the voice
    "plr_db": 19.0,  # true peak over integrated loudness (beds 10.8-14.5); over: single hits jump out
    "seam_ratio": 1.0,  # the loop's end-to-start step over its 99.9th-percentile step (beds 0.03-0.44)
    "voice_bar_db": -26.0,  # a bar's 300 Hz-3 kHz level at -28 LUFS (beds -35.0 .. -27.2, lullaby)
    "voice_share": 0.72,  # the whole piece's 300 Hz-3 kHz share of the power (beds 7-63 %)
    "bass_share_high": 0.85,  # share under 150 Hz (beds 23-78 %); over: boomy
    "bass_share_low": 0.05,  # under: thin (a note only)
    "highs_db": -30.0,  # level above 5 kHz against the whole (beds -94 .. -34.8, bright); over: hiss and sizzle
    "highs_bar_db": -24.0,  # the same in the brightest bar (beds up to -28.6)
    "in_key": 0.75,  # share of the pitched sound on the key's notes (templates 0.90-1.00)
    "in_chord": 0.25,  # under each chord, each audible pitched part's share on the key's or the chord's notes (templates 0.39-0.99, a wrong line 0.01-0.04)
    "lift_db": 0.5,  # a lift's loudness over the section before it, or
    "lift_bright_db": 1.5,  # ... its brightness (power above 2 kHz; ascent +1.9 dB at +0.3 dB louder)
    "lift_under_db": 1.0,  # a note: a lift this much quieter (and no brighter) than an earlier section (no template or piece is)
    "build_db": 0.5,  # a build's second half over its first (loudness), or
    "build_bright_db": 1.0,  # ... its brightness (tidewater +1.3, ascent +3.0)
    "voice_clear_db": 15.0,  # demo: the voice's 300 Hz-3 kHz over the music's while it speaks (beds 17.6-26.2)
    "clipped_runs": 0,  # runs of 3+ samples at full scale (audio files)
}


@dataclass
class Finding:
    """One thing the check says: its ``topic``, ``level`` (``ok``, ``note`` or ``fix``), what
    was measured in words, and the changes that would help (naming the score's keys)."""

    topic: str
    level: str
    text: str
    fixes: list[str] = field(default_factory=list)


@dataclass
class Frames:
    """Per-frame measures of a sound: the frames' centres (samples), each band's power and,
    for the picture, the log-frequency spectrogram in dB (rows high to low)."""

    centres: np.ndarray
    bands: dict[str, np.ndarray]
    image: np.ndarray | None = None


@dataclass
class MusicCheck:
    """What :func:`check_music_score` / :func:`check_music_audio` found. ``audio``: the piece at -28 LUFS
    (float32 ``(n, 2)``); ``marks``: ``(seconds, section name)``; ``bar``: samples per bar (or
    per block for an audio file); not in the JSON."""

    name: str
    kind: str
    seconds: float
    loop: bool | None
    facts: dict[str, Any]
    sections: list[dict[str, Any]]
    tracks: list[dict[str, Any]]
    findings: list[Finding]
    audio: np.ndarray
    frames: Frames
    marks: list[tuple[float, str]]
    bar: int
    unit: str
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        fixes = [f for f in self.findings if f.level == "fix"]
        notes = [f for f in self.findings if f.level == "note"]
        if fixes:
            return f"needs work: {len(fixes)} thing{'s' if len(fixes) > 1 else ''} to fix ({', '.join(f.topic for f in fixes)})"
        if notes:
            return f"fine under narration, {len(notes)} note{'s' if len(notes) > 1 else ''} ({', '.join(f.topic for f in notes)})"
        return "fine under narration"


# ----- measuring -------------------------------------------------------------------------------


IMAGE_ROWS = 200
IMAGE_HZ = (30.0, 16000.0)
_FFT = 4096


def frame_hop(seconds: float) -> int:
    """Samples between the frames (and picture columns): 20 per second up to 80 s, fewer for
    longer pieces (at most 1600 columns)."""
    return max(RATE // 20, int(math.ceil(seconds * RATE / 1600 / 100)) * 100)


def _db(power: float) -> float:
    return 10 * math.log10(max(power, 1e-30))


def master_response(lowpass: float, highpass: float) -> np.ndarray:
    """The power response of a score's master filter (``_tone_filter``) on the frames' bins."""
    freqs = np.fft.rfftfreq(_FFT, 1 / RATE)
    return (_highpass(freqs, highpass, 2) * _lowpass(freqs, lowpass, 2)) ** 2


def measure_frames(x: np.ndarray, loop: bool, hop: int, image: bool = True, response: np.ndarray | None = None) -> Frames:
    """Hann-windowed spectra every ``hop`` samples (4096-sample frames centred on the hop's
    middle; wrapped round for a loop): each band's power and, with ``image``, the picture.
    ``response``: power weights per bin (a filter the sound has not been through yet)."""
    mono = np.asarray(x, dtype=np.float64).reshape(len(x), -1).mean(axis=1)
    n = len(mono)
    count = max(1, n // hop)
    centres = np.arange(count) * hop + hop // 2
    half = _FFT // 2
    padded = np.concatenate([mono[-half:], mono, mono[:half]]) if loop and n > _FFT else np.pad(mono, (half, half))
    window = np.hanning(_FFT)
    freqs = np.fft.rfftfreq(_FFT, 1 / RATE)
    masks = {name: (freqs >= lo) & (freqs < hi) for name, (lo, hi) in BANDS.items()}
    rows = np.geomspace(IMAGE_HZ[1], IMAGE_HZ[0], IMAGE_ROWS)
    bands = {name: np.zeros(count) for name in BANDS}
    picture = np.zeros((IMAGE_ROWS, count)) if image else None
    for a in range(0, count, 256):
        idx = centres[a : a + 256]
        frames = np.stack([padded[c : c + _FFT] for c in idx]) * window
        power = np.abs(np.fft.rfft(frames, axis=1)) ** 2 / (window.sum() / 2) ** 2
        if response is not None:
            power *= response
        for name, mask in masks.items():
            bands[name][a : a + len(idx)] = power[:, mask].sum(axis=1)
        if picture is not None:
            db = 10 * np.log10(np.maximum(power, 1e-14))
            picture[:, a : a + len(idx)] = np.stack([np.interp(rows, freqs, column) for column in db], axis=1)
    return Frames(centres, bands, picture)


def _gated(power: np.ndarray) -> float:
    """The integrated (gated) loudness of a stretch of K-weighted power."""
    meter = LoudnessMeter()
    meter.add(power, np.zeros(0))
    return meter.integrated


def _short_term(power: np.ndarray, loop: bool) -> np.ndarray:
    """Loudness (LUFS, ungated) of 3 s windows every 0.5 s (wrapped round for a loop), from
    the K-weighted power."""
    step = RATE // 2
    steps = power[: len(power) // step * step].reshape(-1, step).sum(axis=1)
    width = 6
    if len(steps) < width:
        return np.array([-0.691 + _db(float(power.mean()))])
    ext = np.concatenate([steps, steps[: width - 1]]) if loop else steps
    sums = np.convolve(ext, np.ones(width), mode="valid")
    return -0.691 + 10 * np.log10(np.maximum(sums / (width * step), 1e-30))


def _seam(x: np.ndarray) -> float:
    """The sample step across a loop's end-to-start over its 99.9th-percentile step (under 1: no
    click). The level either side is not compared: a downbeat's hit makes it jump on purpose."""
    steps = np.abs(np.diff(x, axis=0)).max(axis=1)
    jump = float(np.abs(x[0] - x[-1]).max())
    return jump / max(float(np.percentile(steps, 99.9)), 1e-12)


def _clipped_runs(x: np.ndarray) -> int:
    """Runs of three or more samples at full scale (|x| >= 0.999) in any channel."""
    runs = 0
    for c in range(x.shape[1]):
        hot = np.abs(x[:, c]) >= 0.999
        edges = np.diff(np.concatenate([[0], hot.astype(np.int8), [0]]))
        starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
        runs += int(np.sum(ends - starts >= 3))
    return runs


def _tempo_words(heard: float | None, written: float | None) -> tuple[str, str]:
    """The level and the words comparing the tempo heard with the score's."""
    if heard is None:
        return "ok", "no steady beat heard" + (f" (the score says {written:g} BPM: its beat is soft or sparse; fine for a calm bed)" if written else "")
    if written is None:
        return "ok", f"heard {heard:.1f} BPM"
    for ratio, name in TEMPO_RATIOS.items():
        if abs(heard / (written * ratio) - 1) <= 0.02:
            if ratio == 1.0:
                return "ok", f"heard {heard:.1f} BPM, as the score's {written:g}"
            why = "accents or figures grouped in threes, such as 3+3+2, make the onsets repeat in threes" if ratio in (2 / 3, 4 / 3, 1.5, 0.75) else "the same beat counted twice as fast or slow"
            return "ok", f"heard {heard:.1f} BPM = {name} of the score's {written:g} ({why}; the same beat, fine)"
    return "note", f"heard {heard:.1f} BPM, not the score's {written:g} or a simple ratio of it"


def _bars_of(frames: Frames, bar: int, bars: int) -> np.ndarray:
    return np.minimum(frames.centres // bar, bars - 1)


def _per_bar(values: np.ndarray, index: np.ndarray, bars: int) -> np.ndarray:
    total = np.bincount(index, weights=values, minlength=bars)
    count = np.maximum(np.bincount(index, minlength=bars), 1)
    return total / count


def _ranges(bars: Sequence[int]) -> list[tuple[int, int]]:
    """Consecutive runs of bar numbers (0-based) as ``(first, last)``."""
    out: list[tuple[int, int]] = []
    for b in sorted(bars):
        if out and b == out[-1][1] + 1:
            out[-1] = (out[-1][0], b)
        else:
            out.append((b, b))
    return out


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def _span_words(first: int, last: int, unit: str, bar: int) -> str:
    if unit == "bars":
        return f"bar {first + 1}" if first == last else f"bars {first + 1}-{last + 1}"
    return f"{_clock(first * bar / RATE)}-{_clock((last + 1) * bar / RATE)}"


@dataclass
class _Stems:
    """Per-track measures gathered while a score plays track by track."""

    hop: int
    response: np.ndarray
    spans: list[tuple[int, int]] = field(default_factory=list)
    frames: dict[str, Frames] = field(default_factory=dict)
    peaks: dict[str, float] = field(default_factory=dict)
    seams: dict[str, float] = field(default_factory=dict)
    pitched: np.ndarray | None = None
    chord_power: dict[str, np.ndarray] = field(default_factory=dict)

    def add(self, name: str, sound: np.ndarray, loop: bool, is_pitched: bool) -> None:
        """A track's sound before the master filter (its response is applied to the bands; the
        peak and seam are the unfiltered sound's); a pitched track's chroma power under each
        chord (``spans``: samples), to say which track plays off the chord."""
        self.frames[name] = measure_frames(sound, loop, self.hop, image=False, response=self.response)
        self.peaks[name] = float(np.abs(sound).max())
        self.seams[name] = float(np.abs(sound[0] - sound[-1]).max())
        if is_pitched:
            self.pitched = sound.copy() if self.pitched is None else self.pitched + sound
            self.chord_power[name] = np.array([measure.chroma_power(sound[a:z]) for a, z in self.spans]).reshape(len(self.spans), 12)


# ----- the checks ------------------------------------------------------------------------------


def check_music_score(score: MusicScore, hop: int | None = None) -> MusicCheck:
    """Play ``score`` track by track and check it (:class:`MusicCheck`)."""
    import time

    began = time.perf_counter()
    hop = hop or frame_hop(score.seconds)
    slots = _chord_slots(score)
    stems = _Stems(hop, master_response(score.lowpass, score.highpass), [(c.start, c.start + c.length) for _, c in slots])
    kinds = {t.name: t.instrument.kind for t in score.tracks}
    mix, gain = render_music_stems(score, lambda name, sound: stems.add(name, sound, score.loop, kinds[name] != "drum"))
    for f in stems.frames.values():
        for name in f.bands:
            f.bands[name] *= gain**2
    stems.peaks = {k: v * gain for k, v in stems.peaks.items()}
    rendered = time.perf_counter()
    piece = np.asarray(mix[: score.samples], dtype=np.float64)
    spans =[(s.name, s.first_bar, s.bars, s.key) for s in score.sections]
    report = _analyse(
        name=score.title or Path(score.origin).stem,
        kind="score",
        x=piece,
        original=None,
        loop=score.loop,
        bar=score.bar,
        unit="bars",
        sections=spans,
        tempo=score.tempo,
        key=score.key,
        stems=stems,
        score=score,
        hop=hop,
    )
    report.audio = mix
    report.facts.update(
        {"title": score.title, "key": score.key.name, "tempo": score.tempo, "time": f"{score.time[0]}/{score.time[1]}", "bars": score.bars}
    )
    report.timings = {"render": round(rendered - began, 2), "total": round(time.perf_counter() - began, 2)}
    return report


def check_music_audio(samples: np.ndarray, name: str, loop: bool = True, hop: int | None = None) -> MusicCheck:
    """Check an audio file's ``samples`` (any level; measured as vidgen plays it, at -28 LUFS).
    ``loop``: check the seam too (vidgen loops a music file that is shorter than its cue)."""
    import time

    began = time.perf_counter()
    x = np.asarray(samples, dtype=np.float64).reshape(len(samples), -1)
    x = np.repeat(x, 2, axis=1) if x.shape[1] == 1 else x[:, :2]
    level = integrated_loudness(x)
    scaled = x * 10 ** ((MUSIC_LEVEL - level) / 20) if math.isfinite(level) else x
    seconds = len(x) / RATE
    bar = int(BLOCK_SECONDS * RATE)
    report = _analyse(
        name=name, kind="audio", x=scaled, original=x, loop=loop, bar=bar, unit="seconds", sections=[], tempo=None, key=None,
        stems=None, score=None, hop=hop or frame_hop(seconds),
    )
    report.audio = scaled.astype(np.float32)
    report.facts["file_lufs"] = round(level, 2) if math.isfinite(level) else None
    report.timings = {"total": round(time.perf_counter() - began, 2)}
    return report


def _analyse(
    name: str, kind: str, x: np.ndarray, original: np.ndarray | None, loop: bool, bar: int, unit: str, sections: list[tuple[str, int, int, Any]],
    tempo: float | None, key: Any, stems: _Stems | None, score: MusicScore | None, hop: int,
) -> MusicCheck:
    n = len(x)
    bars = max(1, int(math.ceil(n / bar)))
    frames = measure_frames(x, loop, hop)
    index = _bars_of(frames, bar, bars)
    b = frames.bands
    total = float(b["all"].sum()) or 1e-30
    findings: list[Finding] = []
    facts: dict[str, Any] = {}

    # loudness, steadiness, peaks
    kpower = kweighted_power(x)
    lufs = _gated(kpower)
    st = _short_term(kpower, loop)
    st = st[st > -70] if (st > -70).any() else st
    p10, p95 = (float(v) for v in np.percentile(st, [10, 95]))
    steady = p95 - p10
    true_peak = 20 * math.log10(max(float(peak_envelope(x).max()), 1e-12))
    plr = true_peak - lufs
    facts.update(lufs=round(lufs, 2), short_term_p10=round(p10, 2), short_term_p95=round(p95, 2), steadiness_db=round(steady, 2),
                 true_peak=round(true_peak, 2), peak_to_loudness_db=round(plr, 2))
    section_rows: list[dict[str, Any]] = []
    for sname, first, count, skey in sections:
        a, z = first * bar, min(n, (first + count) * bar)
        mid = (a + z) // 2
        row = {"name": sname, "first_bar": first + 1, "bars": count, "start": round(a / RATE, 3), "key": skey.name if skey is not None else None,
               "lufs": round(_gated(kpower[a:z]), 2), "bright_db": round(_band_level(frames, "bright", a, z), 2)}
        if count >= 2:
            row["first_half_lufs"] = round(_gated(kpower[a:mid]), 2)
            row["second_half_lufs"] = round(_gated(kpower[mid:z]), 2)
            row["brighter_db"] = round(_band_level(frames, "bright", mid, z) - _band_level(frames, "bright", a, mid), 2)
        section_rows.append(row)
    if original is None:
        findings.append(Finding("loudness", "ok", f"{lufs:.1f} LUFS integrated (vidgen plays music at -28 LUFS at volume 0)"))
    else:
        file_lufs = integrated_loudness(original)
        findings.append(Finding("loudness", "ok", f"the file is {file_lufs:.1f} LUFS; vidgen plays it at -28 LUFS (volume 0), as measured here"))
    if steady > LIMITS["steadiness_db"]:
        findings.append(Finding("steadiness", "fix", f"the 3 s loudness swings {steady:.1f} dB (10th to 95th percentile; limit {LIMITS['steadiness_db']:g}): "
                                "under a voice the quiet parts vanish and the loud ones push", _steady_fixes(score, section_rows)))
    else:
        findings.append(Finding("steadiness", "ok", f"the 3 s loudness stays within {steady:.1f} dB (10th to 95th percentile)"))
    if plr > LIMITS["plr_db"]:
        findings.append(Finding("peaks", "fix", f"true peak {true_peak:.1f} dBTP, {plr:.1f} dB over the loudness (limit {LIMITS['plr_db']:g}): single hits jump out "
                                "of the bed and the video's limiter will press on them", _peak_fixes(score, stems, plr)))
    else:
        findings.append(Finding("peaks", "ok", f"true peak {true_peak:.1f} dBTP, {plr:.1f} dB over the loudness"))
    if original is not None:
        runs = _clipped_runs(original)
        facts["clipped_runs"] = runs
        if runs > LIMITS["clipped_runs"]:
            findings.append(Finding("clipping", "fix", f"{runs} run{'s' if runs > 1 else ''} of samples at full scale: the file was clipped when it was made "
                                    "(vidgen turns it down to -28 LUFS but cannot undo clipping)", ["export it again with 1-2 dB of headroom"]))
        else:
            findings.append(Finding("clipping", "ok", "no clipping"))

    # tempo
    heard = measure.tempo(x)
    facts["tempo_heard"] = round(heard, 2) if heard is not None else None
    level, words = _tempo_words(heard, tempo)
    fixes = []
    if level == "note" and score is not None:
        drums = [t.name for t in score.tracks if t.instrument.kind == "drum"]
        fixes = [f"check that the drums land on the beat ({', '.join(f'`{d}.steps`' for d in drums[:3])})"] if drums else []
    findings.append(Finding("tempo", level, words, fixes))

    # loop seam
    if loop and n > RATE:
        ratio = _seam(x)
        facts["seam_ratio"] = round(ratio, 3)
        if ratio > LIMITS["seam_ratio"]:
            findings.append(Finding("loop seam", "fix", f"a click where the loop starts again: the sample step there is {ratio:.1f} times the music's "
                                    "own biggest steps", _seam_fixes(stems)))
        else:
            findings.append(Finding("loop seam", "ok", f"clean: the step across it is {ratio:.2f} of the music's own biggest steps"))

    # voice range, bass, highs
    voice_share = float(b["voice"].sum()) / total
    bass_share = float(b["bass"].sum()) / total
    highs_db = _db(float(b["highs"].sum()) / total)
    bar_voice = 10 * np.log10(np.maximum(_per_bar(b["voice"], index, bars), 1e-30))
    bar_all = _per_bar(b["all"], index, bars)
    bar_highs = 10 * np.log10(np.maximum(_per_bar(b["highs"], index, bars) / np.maximum(bar_all, 1e-30), 1e-30))
    facts.update(voice_share=round(voice_share, 3), voice_bar_max_db=round(float(bar_voice.max()), 2), bass_share=round(bass_share, 3),
                 highs_db=round(highs_db, 2), highs_bar_max_db=round(float(bar_highs.max()), 2))
    loud_bars = [int(i) for i in np.flatnonzero(bar_voice > LIMITS["voice_bar_db"])]
    if loud_bars or voice_share > LIMITS["voice_share"]:
        where = ", ".join(_span_words(a, z, unit, bar) for a, z in _ranges(loud_bars)) or "throughout"
        findings.append(Finding("voice range", "fix", f"{100 * voice_share:.0f} % of the sound is in the voice's range (300 Hz-3 kHz); it is loud there in {where} "
                                f"(up to {bar_voice.max():.1f} dB, limit {LIMITS['voice_bar_db']:g}): it will compete with the narration",
                                _voice_fixes(score, stems, loud_bars or list(range(bars)), bar_voice, unit, bar)))
    else:
        findings.append(Finding("voice range", "ok", f"{100 * voice_share:.0f} % of the sound in 300 Hz-3 kHz, at most {bar_voice.max():.1f} dB in a bar: "
                                "room for the voice"))
    if bass_share > LIMITS["bass_share_high"]:
        findings.append(Finding("bass", "fix", f"{100 * bass_share:.0f} % of the power under 150 Hz (limit {100 * LIMITS['bass_share_high']:.0f} %): boomy; "
                                "the low end takes the level and the rest sounds far away",
                                _band_fixes(score, stems, "bass", _excess_for_share(bass_share, LIMITS["bass_share_high"]))))
    elif bass_share < LIMITS["bass_share_low"]:
        findings.append(Finding("bass", "note", f"only {100 * bass_share:.1f} % of the power under 150 Hz: light and thin (fine for a delicate bed)",
                                ["for more weight add a `sub` or a bass track, or a pad's `settings: {sub: 0.3}`"] if kind == "score" else []))
    else:
        findings.append(Finding("bass", "ok", f"{100 * bass_share:.0f} % of the power under 150 Hz"))
    if highs_db > LIMITS["highs_db"] or float(bar_highs.max()) > LIMITS["highs_bar_db"]:
        findings.append(Finding("highs", "fix", f"the highs (above 5 kHz) are {highs_db:.1f} dB under the whole, {bar_highs.max():.1f} dB in the brightest "
                                f"{'bar' if unit == 'bars' else 'stretch'} (limits {LIMITS['highs_db']:g} / {LIMITS['highs_bar_db']:g}): hiss and sizzle that tire "
                                "the ear under a voice",
                                _band_fixes(score, stems, "highs", max(highs_db - LIMITS["highs_db"], float(bar_highs.max()) - LIMITS["highs_bar_db"]) + 0.5)))
    else:
        findings.append(Finding("highs", "ok", f"the highs (above 5 kHz) {highs_db:.1f} dB under the whole: smooth"))

    # key
    chroma_source = stems.pitched if stems is not None and stems.pitched is not None else x
    profile = measure.chroma(chroma_source)
    best = measure.key(profile)
    fits = measure.key_fits(profile)
    facts.update(key_heard=best, key_fit=round(fits[best], 3))
    if key is not None:
        shares = []
        for sname, first, count, skey in sections or [("", 0, bars, key)]:
            part = chroma_source[first * bar : (first + count) * bar]
            prof = measure.chroma(part) if len(part) > _FFT else profile
            shares.append((sname, skey, float(sum(prof[p] for p in skey.scale)), count))
        in_key = sum(s * c for _, _, s, c in shares) / max(sum(c for *_, c in shares), 1)
        facts["in_key"] = round(in_key, 3)
        worst = min(shares, key=lambda s: s[2])
        chords = [c for c in (_chord_fits(score, stems) if score is not None and stems is not None else []) if c["track"] is not None]
        clash = min(chords, key=lambda c: c["share"]) if chords else None
        if clash is not None:
            facts["in_chord_min"] = {"track": clash["track"], "share": round(clash["share"], 3), "where": clash["where"], "chord": clash["chord"]}
        if worst[2] < LIMITS["in_key"]:
            where = f" in the {worst[0]}" if worst[0] and len(shares) > 1 else ""
            findings.append(Finding("key", "fix", f"only {100 * worst[2]:.0f} % of the pitched sound{where} is on {worst[1].name}'s notes (limit "
                                    f"{100 * LIMITS['in_key']:.0f} %; it fits {best} best): notes clash with the key",
                                    ["check `key:` (it sets the scale the degrees use) and the written notes (`E5`, `F#3`...) and chord names in `progression`"]))
        elif clash is not None and clash["share"] < LIMITS["in_chord"]:
            findings.append(Finding("key", "fix", f"under the {clash['chord']} at {clash['where']} only {100 * clash['share']:.0f} % of `{clash['track']}` is on "
                                    f"the key's or the chord's notes (limit {100 * LIMITS['in_chord']:.0f} %; the piece as a whole: {100 * in_key:.0f} % on the "
                                    "key's notes): it clashes with the chord there", _chord_fixes(clash)))
        else:
            findings.append(Finding("key", "ok", f"{100 * in_key:.0f} % of the pitched sound on the key's notes (the chroma fits {best} best, {fits[best]:.2f})"
                                    + (f"; every part fits every chord (at least {100 * clash['share']:.0f} %)" if clash is not None else "")))
    else:
        findings.append(Finding("key", "ok", f"the pitches fit {best} best ({fits[best]:.2f})"))

    # sections: does the lift lift, does the build build?
    for i, row in enumerate(section_rows):
        if row["name"] in LIFT_NAMES:
            # the section before (round the loop for the first one); a one-pass piece's first section: the rest
            before = section_rows[i - 1] if i > 0 else (section_rows[-1] if loop and len(section_rows) > 1 else None)
            others = [r["lufs"] for r in section_rows if r is not row]
            ref = before["lufs"] if before is not None else (float(np.mean(others)) if others else None)
            if ref is None:
                continue
            gain_db = row["lufs"] - ref
            brighter = row["bright_db"] - (before["bright_db"] if before is not None else float(np.mean([r["bright_db"] for r in section_rows if r is not row])))
            row["lift_db"], row["lift_brighter_db"] = round(gain_db, 2), round(brighter, 2)
            against = (f"the {before['name']}" + (" (before it round the loop)" if i == 0 else "")) if before is not None else "the rest"
            if gain_db >= LIMITS["lift_db"] or brighter >= LIMITS["lift_bright_db"]:
                findings.append(Finding("sections", "ok", f"the {row['name']} lifts: {gain_db:+.1f} dB louder and {brighter:+.1f} dB brighter than {against}"))
            else:
                findings.append(Finding("sections", "fix", f"the {row['name']} does not lift: {gain_db:+.1f} dB louder and {brighter:+.1f} dB brighter than "
                                        f"{against} (it should be {LIMITS['lift_db']:g} dB louder or {LIMITS['lift_bright_db']:g} dB brighter)",
                                        _lift_fixes(score, stems, row["name"], before["name"] if before else None, sections, bar)))
            # a lift after a quiet break passes against the break: it should still top what came before
            earlier = [r for r in section_rows[:i] if r is not before and r["name"] not in LIFT_NAMES]
            peak = max(earlier, key=lambda r: r["lufs"], default=None)
            if peak is not None and peak["lufs"] - row["lufs"] >= LIMITS["lift_under_db"] and peak["bright_db"] >= row["bright_db"]:
                lifted = findings[-1].level == "ok"  # else the fix above already gives the advice
                findings.append(Finding("sections", "note", f"the {row['name']} is {peak['lufs'] - row['lufs']:.1f} dB quieter than the {peak['name']} before it, "
                                        "and no brighter: it may not feel like the high point",
                                        _lift_fixes(score, stems, row["name"], peak["name"], sections, bar) if lifted else []))
        if row["name"] in BUILD_NAMES and "first_half_lufs" in row:
            rise = row["second_half_lufs"] - row["first_half_lufs"]
            row["build_db"] = round(rise, 2)
            if rise >= LIMITS["build_db"] or row["brighter_db"] >= LIMITS["build_bright_db"]:
                findings.append(Finding("sections", "ok", f"the {row['name']} builds: its second half {rise:+.1f} dB, {row['brighter_db']:+.1f} dB brighter"))
            else:
                findings.append(Finding("sections", "fix", f"the {row['name']} does not build: its second half {rise:+.1f} dB, {row['brighter_db']:+.1f} dB brighter "
                                        f"(it should rise {LIMITS['build_db']:g} dB or brighten {LIMITS['build_bright_db']:g} dB)",
                                        _build_fixes(score, stems, row["name"], ((row["first_bar"] - 1) * bar, (row["first_bar"] - 1 + row["bars"]) * bar))))

    # tracks
    track_rows: list[dict[str, Any]] = []
    if stems is not None and score is not None:
        sums = {band: sum(float(f.bands[band].sum()) for f in stems.frames.values()) or 1e-30 for band in BANDS}
        mix_peak = max(float(np.abs(x).max()), 1e-12)
        for t in score.tracks:
            f = stems.frames[t.name]
            track_rows.append({
                "name": t.name, "instrument": t.instrument.name,
                **{f"{band}_share": round(float(f.bands[band].sum()) / sums[band], 3) for band in ("all", "voice", "bass", "highs")},
                "peak_db": round(20 * math.log10(max(stems.peaks[t.name], 1e-12) / mix_peak), 2),
            })
    report = MusicCheck(name, kind, n / RATE, loop, facts, section_rows, track_rows, findings, np.zeros((0, 2), np.float32), frames,
                         [(first * bar / RATE, sname) for sname, first, _, _ in sections], bar, unit)
    report.facts["bar_voice_db"] = [round(float(v), 2) for v in bar_voice]
    report.facts["bar_lufs"] = [round(float(v), 2) for v in _bar_lufs(kpower, bar, bars)]
    return report


#: The shortest chord (seconds) the per-chord key check looks at (shorter spans blur the pitches).
CHORD_MIN_SECONDS = 0.5
#: A pitched track counts under a chord when it holds this share of the pitched power there.
CHORD_TRACK_SHARE = 0.05


def _chord_slots(score: MusicScore) -> list[tuple[Section, ChordSlot]]:
    """Every chord as it plays (section, slot) that lasts long enough to measure its pitches."""
    return [(s, c) for s in score.sections for c in s.chords if c.length >= CHORD_MIN_SECONDS * RATE]


def _chord_fits(score: MusicScore, stems: _Stems) -> list[dict[str, Any]]:
    """Under each chord, the pitched track that fits it worst: its share of its own sound on the
    key's scale or the chord's notes (a chromatic chord's tones are fine), among the tracks that
    hold :data:`CHORD_TRACK_SHARE` of the pitched sound there, and the notes it plays off them.
    (Per track, as a quiet melody that clashes hides in the whole: overtones of rich sounds keep
    every part above 35 %, a wrong note line falls under 5 %.)"""
    out = []
    for k, (section, slot) in enumerate(_chord_slots(score)):
        allowed = set(slot.key.scale) | set(slot.chord.pitch_classes) | {slot.chord.bass}
        allowed |= {n % 12 for n in slot.notes or ()} | ({slot.bass_note % 12} if slot.bass_note is not None else set())
        off = [p for p in range(12) if p not in allowed]
        total = sum(float(power[k].sum()) for power in stems.chord_power.values()) or 1e-30
        fits = [(1 - float(power[k][off].sum()) / float(power[k].sum()), name) for name, power in stems.chord_power.items()
                if float(power[k].sum()) >= CHORD_TRACK_SHARE * total]
        share, track = min(fits) if fits else (1.0, None)
        power = stems.chord_power[track][k] if track is not None else np.zeros(12)
        out.append({
            "chord": slot.chord.name,
            "where": f"bar {slot.start // score.bar + 1} ({section.name})",
            "track": track,
            "share": share,
            "off_notes": [note_name(60 + p, slot.key.flats)[:-1] for p in sorted(off, key=lambda p: -power[p])[:3] if power[p] > 0.05 * power.sum()],
            "chord_notes": [note_name(60 + p, slot.key.flats)[:-1] for p in slot.chord.pitch_classes],
        })
    return out


def _chord_fixes(clash: dict[str, Any]) -> list[str]:
    notes = f" ({', '.join(clash['off_notes'])})" if clash["off_notes"] else ""
    return [f"`{clash['track']}` plays notes off it{notes}: check its notes there against {clash['chord']} ({', '.join(clash['chord_notes'])}) "
            "and the key, or write degrees (1 3 5 8) that follow each chord",
            "or change that chord in `progression` to one that holds those notes"]


def _band_level(frames: Frames, band: str, a: int, z: int) -> float:
    pick = (frames.centres >= a) & (frames.centres < z)
    return _db(float(frames.bands[band][pick].mean())) if pick.any() else -300.0


def _bar_lufs(power: np.ndarray, bar: int, bars: int) -> np.ndarray:
    """The loudness (ungated) of each bar, from the K-weighted power."""
    return np.array([-0.691 + _db(float(power[k * bar : (k + 1) * bar].mean())) if len(power[k * bar : (k + 1) * bar]) else -300.0 for k in range(bars)])


# ----- advice ----------------------------------------------------------------------------------


#: The most the advice lowers one track (dB); beyond it, rest the part or change it.
MAX_CUT_DB = 20


def _round_db(value: float) -> int:
    return int(min(MAX_CUT_DB, max(2, math.ceil(value))))


def _top(stems: _Stems, band: str, a: int = 0, z: int | None = None) -> list[tuple[str, float]]:
    """Tracks by their share of ``band``'s power between samples ``a`` and ``z``, largest first."""
    found = []
    for name, f in stems.frames.items():
        pick = (f.centres >= a) & (f.centres < (z if z is not None else f.centres[-1] + 1))
        found.append((name, float(f.bands[band][pick].sum())))
    whole = sum(v for _, v in found) or 1e-30
    return sorted(((n, v / whole) for n, v in found), key=lambda t: -t[1])


def _cut_for(share: float, excess_db: float) -> float | None:
    """dB to lower tracks holding ``share`` of a band's power so the band falls ``excess_db``;
    ``None`` when they alone cannot do it."""
    keep = 10 ** (-excess_db / 10) - (1 - share)
    if keep <= 0 or share <= 0:
        return None
    return -10 * math.log10(keep / share)


def _excess_for_share(share: float, limit: float) -> float:
    """dB a band must fall for its share of the whole to go from ``share`` down to ``limit``."""
    ratio = limit * (1 - share) / max((1 - limit) * share, 1e-12)
    return -10 * math.log10(max(ratio, 1e-12)) + 0.5


def _cuts(top: list[tuple[str, float]], excess_db: float) -> tuple[list[str], float] | None:
    """The fewest of the ``top`` tracks (up to three) that, lowered together by the same dB (at
    most :data:`MAX_CUT_DB`), make their band fall ``excess_db``; with that dB."""
    names: list[str] = []
    share = 0.0
    for name, part in top[:3]:
        names.append(name)
        share += part
        cut = _cut_for(share, excess_db)
        if cut is not None and cut <= MAX_CUT_DB:
            return names, cut
    return None


def _part_volume(track: Track, section: str) -> float | None:
    """A track's constant volume (dB) in a section (``None``: a volume curve there)."""
    part = track.parts[section]
    return None if part.volume_curve is not None else part.volume_db


def _volume_text(track: Track, sections: Sequence[str], change: float) -> str:
    """The score change that moves ``track``'s volume by ``change`` dB in ``sections``: its
    ``volume`` when it covers every section the track plays at one level, else ``sections:``."""
    playing = [s for s in sections if s in track.parts]
    levels = {s: _part_volume(track, s) for s in track.parts}
    if set(playing) == set(track.parts) and len(set(levels.values())) == 1 and None not in levels.values():
        now = next(iter(levels.values()))
        return f"`{track.name}.volume: {now + change:g}` (now {now:g})"
    items = ", ".join(f"{s}: {{volume: {levels[s] + change:g}}}" if levels[s] is not None else f"{s}: {{volume: ...}}" for s in playing)
    return f"`{track.name}: sections: {{{items}}}` ({change:+g} dB)"


def _sections_of(score: MusicScore, first: int, last: int) -> list[str]:
    return [s.name for s in score.sections if s.first_bar <= last and s.first_bar + s.bars - 1 >= first]


def _alternative(track: Track, band: str) -> str:
    """Another way than its volume to take ``track`` out of ``band``."""
    inst = track.instrument
    if band == "voice":
        if inst.kind == "note" and inst.octave is not None:
            octave = next((p.octave for p in track.parts.values() if p.octave is not None), inst.octave)
            return f"or move `{track.name}` an octave up (`octave: {octave + 1}`), above the voice's core, or rest it while the narrator speaks"
        if inst.kind == "pad":
            return f"or darken `{track.name}` (`settings: {{tone: 1200}}` or `lowpass: 1500`) so it sits under the voice"
        return f"or `lowpass: 2000` on `{track.name}`"
    if band == "bass":
        return f"or a shorter `{track.name}` (`settings: {{decay: ...}}`)" if "decay" in inst.settings else f"or `highpass: 60` on `{track.name}` to drop the rumble"
    tone = f" or a darker `settings: {{tone: ...}}`" if "tone" in inst.settings else ""
    return f"or `lowpass: 5000` on `{track.name}`{tone}"


def _lower_tracks(score: MusicScore, stems: _Stems, band: str, excess_db: float, sections: Sequence[str], what: str, a: int = 0,
                  z: int | None = None) -> str:
    """One line of advice: which tracks hold ``band`` between samples ``a`` and ``z`` and how
    far to lower them (score keys)."""
    tracks = {t.name: t for t in score.tracks}
    top = [t for t in _top(stems, band, a, z) if t[1] > 0]
    if not top:
        return "lower the busiest parts"
    found = _cuts(top, excess_db)
    picked = top[: len(found[0]) if found else 2]
    if len(picked) == 1:
        holders = f"`{picked[0][0]}` ({tracks[picked[0][0]].instrument.name}) holds"
    else:
        holders = " and ".join(f"`{n}` ({tracks[n].instrument.name}, {100 * s:.0f} %)" for n, s in picked) + " hold"
    share = 100 * sum(s for _, s in picked)
    if found is None:
        return f"{holders} {share:.0f} % of {what}; lowering them by {MAX_CUT_DB} dB is not enough: rest one of them there or swap it for a darker part"
    change = -float(_round_db(found[1]))
    lowered = "; ".join(_volume_text(tracks[n], sections, change) for n, _ in picked)
    return f"{holders} {share:.0f} % of {what}: lower {lowered}; " + _alternative(tracks[picked[0][0]], band)


def _voice_fixes(score: MusicScore | None, stems: _Stems | None, loud: list[int], bar_voice: np.ndarray, unit: str, bar: int) -> list[str]:
    if score is None or stems is None:
        return ["turn the mid-range down (an EQ dip around 1-2 kHz) or pick a darker, sparser piece"]
    fixes = []
    for first, last in _ranges(loud)[:3]:
        excess = float(bar_voice[first : last + 1].max()) - LIMITS["voice_bar_db"] + 0.5
        where = _span_words(first, last, unit, bar)
        fixes.append(f"{where}: " + _lower_tracks(score, stems, "voice", excess, _sections_of(score, first, last), "the voice range there",
                                                  first * bar, (last + 1) * bar))
    return fixes


def _band_fixes(score: MusicScore | None, stems: _Stems | None, band: str, excess_db: float) -> list[str]:
    if score is None or stems is None:
        return ["an EQ shelf on the file: " + ("cut the lows under 150 Hz" if band == "bass" else "cut above 5 kHz")]
    fixes = []
    if band == "highs" and score.lowpass > 8000:
        fixes.append(f"the score's `master: {{lowpass: {score.lowpass:g}}}` lets highs through that the default 4500 Hz would soften: "
                     "remove it or lower it to 6000")
    fixes.append(_lower_tracks(score, stems, band, excess_db, [s.name for s in score.sections], "the bass" if band == "bass" else "the highs"))
    return fixes


def _peak_fixes(score: MusicScore | None, stems: _Stems | None, plr: float) -> list[str]:
    if score is None or stems is None:
        return ["a gentle compressor or limiter on the file before using it"]
    name = max(stems.peaks.items(), key=lambda kv: kv[1])[0]
    track = next(t for t in score.tracks if t.name == name)
    change = -float(_round_db(plr - LIMITS["plr_db"] + 1))
    return [f"`{name}` ({track.instrument.name}) makes the highest peaks: lower {_volume_text(track, list(track.parts), change)}, "
            "or soften its hits (`o` or `?` steps)"]


def _seam_fixes(stems: _Stems | None) -> list[str]:
    if stems is None:
        return ["cut the file at a zero crossing on the beat, or cross-fade its end into its start"]
    name = max(stems.seams.items(), key=lambda kv: kv[1])[0]
    return [f"`{name}` jumps most across the seam: let its last note end before the loop's end"]


def _steady_fixes(score: MusicScore | None, rows: list[dict[str, Any]]) -> list[str]:
    if score is None or len(rows) < 2:
        return ["a gentler arrangement or a compressor; vidgen does not level music within a piece"]
    loud = max(rows, key=lambda r: r["lufs"])
    quiet = [r for r in rows if loud["lufs"] - r["lufs"] >= 6] or [min(rows, key=lambda r: r["lufs"])]
    names = [r["name"] for r in quiet]
    gap = loud["lufs"] - min(r["lufs"] for r in quiet)
    fixes = []
    for t in score.tracks:
        if loud["name"] not in t.parts or _part_volume(t, loud["name"]) is None:
            continue
        top = _part_volume(t, loud["name"]) or 0.0
        lower = [(s, top - v) for s in names if s in t.parts and (v := _part_volume(t, s)) is not None and top - v >= 3]
        if lower:
            diff = min(d for _, d in lower)
            where = " and ".join(f"the {s}" for s, _ in lower)
            fixes.append(f"`{t.name}` is {diff:g} dB quieter in {where} than in the {loud['name']}: "
                         f"{_volume_text(t, [s for s, _ in lower], round(min(diff, gap) - 3))}")
    only_loud = [t.name for t in score.tracks if loud["name"] in t.parts and not any(s in t.parts for s in names)]
    if only_loud:
        fixes.append(f"the {loud['name']} adds {', '.join(f'`{n}`' for n in only_loud)}: let one of them play softly in the {names[0]} too, "
                     f"or lower them in the {loud['name']}")
    fixes.append(f"the {' and '.join(names)} {'is' if len(names) == 1 else 'are'} up to {gap:.1f} dB under the {loud['name']}: keep sections "
                 "within about 4 dB, and move with `volume: {from: -6, to: 0}` ramps rather than jumps")
    return fixes


def _lift_fixes(score: MusicScore | None, stems: _Stems | None, name: str, before: str | None, sections: list[tuple[str, int, int, Any]],
                bar: int) -> list[str]:
    if score is None or stems is None:
        return []
    fixes = []
    if before is not None:
        for t in score.tracks:
            if name in t.parts and before in t.parts:
                now, prev = _part_volume(t, name), _part_volume(t, before)
                if now is not None and prev is not None and now < prev:
                    fixes.append(f"`{t.name}` is {prev - now:g} dB quieter in the {name} than in the {before}: {_volume_text(t, [name], prev - now + 2)}")
    spans = {s: (first * bar, (first + count) * bar) for s, first, count, _ in sections}
    a, z = spans[name]
    tracks = {t.name: t for t in score.tracks}
    main = [n for n, share in _top(stems, "all", a, z) if share > 0 and tracks[n].instrument.kind != "drum"]
    if main and not fixes:
        fixes.append(f"raise its main part: {_volume_text(tracks[main[0]], [name], 3)}")
    # a part that rests in the lift but plays elsewhere — not a transition sound (riser, boom) and
    # not one that only plays in builds: bringing those in would not lift it
    resting = [t for t in score.tracks if name not in t.parts and t.instrument.name not in TRANSITION_INSTRUMENTS
               and any(s not in BUILD_NAMES for s in t.parts)]
    if resting:
        t = max(resting, key=lambda t: float(stems.frames[t.name].bands["all"].sum()))
        playing = [s for s in t.parts if s not in BUILD_NAMES]
        fixes.append(f"bring in a part there: `{t.name}` ({t.instrument.name}) plays in the {' and '.join(playing)} but rests in the {name} "
                     "(its `rest:` / `only:`)")
    else:
        fixes.append(f"add a part that plays only there (`only: [{name}]`): a bell or soft lead line, an open hat, a clap")
    if before is not None:
        ba, bz = spans[before]
        lead = [n for n, share in _top(stems, "all", ba, bz) if share > 0 and tracks[n].instrument.kind != "drum"]
        if lead:
            fixes.append(f"or make the {before} smaller: {_volume_text(tracks[lead[0]], [before], -3)}")
    return fixes


#: The share of a build's second half a riser needs to be heard rising (the advice raises it to this).
RISER_SHARE = 0.1


def _build_fixes(score: MusicScore | None, stems: _Stems | None, name: str, span: tuple[int, int]) -> list[str]:
    if score is None:
        return []
    pads = [t.name for t in score.tracks if t.instrument.kind == "pad" and name in t.parts]
    target = pads[0] if pads else next((t.name for t in score.tracks if name in t.parts), "pad")
    fixes = [f"a volume ramp: `{target}: sections: {{{name}: {{volume: {{from: -6, to: 0}}}}}}`",
             f"or open a filter through it: `{target}: sections: {{{name}: {{lowpass: {{from: 800, to: 4000}}}}}}`"]
    risers = [t for t in score.tracks if t.instrument.name == "riser" and name in t.parts]
    if not risers or stems is None:
        return fixes + [f"or a riser in its last bars: `riser: {{instrument: riser, only: [{name}], steps: \". | . | x | -\"}}` "
                        "(at `volume: 6` or more: at its normal level a riser is felt more than it is measured)"]
    # a riser that is there but too quiet to count: how far to raise it (its share of the second half)
    mid = (span[0] + span[1]) // 2
    shares = dict(_top(stems, "all", mid, span[1]))
    riser = max(risers, key=lambda t: shares.get(t.name, 0.0))
    share = shares.get(riser.name, 0.0)
    if share < RISER_SHARE and 0 < share:
        under = -10 * math.log10(share / (1 - share))
        raise_db = min(MAX_CUT_DB, math.ceil(10 * math.log10(RISER_SHARE * (1 - share) / ((1 - RISER_SHARE) * share))))
        fixes.append(f"or raise the riser: `{riser.name}` sits {under:.0f} dB under the rest of the {name}'s second half, too quiet to make it "
                     f"build (at its normal level a riser is a hint): {_volume_text(riser, [name], raise_db)}"
                     + (", and still use a ramp or a sweep" if raise_db >= MAX_CUT_DB else ""))
    else:
        fixes.append(f"the riser `{riser.name}` is {100 * share:.0f} % of the second half: let it start earlier (more bars held) or rise higher "
                     "(`settings: {high: 5000}`)")
    return fixes


# ----- narration demo --------------------------------------------------------------------------


def duck_gain_db(spans: Sequence[tuple[float, float]], frames: int, depth: float = DUCK[0], attack: float = DUCK[1], release: float = DUCK[2],
                 hold: float = DUCK[3]) -> np.ndarray:
    """vidgen's ducking curve (``vidgen.mix.duck_curve``) in dB per 10 ms frame: ``-depth``
    while the voice speaks or pauses for less than ``hold``, raised-cosine ramps of ``attack``
    seconds before and ``release`` after."""
    if depth == 0 or not spans:
        return np.zeros(frames)
    mask = np.zeros(frames, dtype=bool)
    for a, z in spans:
        mask[max(0, math.floor(a * 100)) : min(frames, math.ceil(z * 100))] = True
    idx = np.arange(frames)
    on = np.nonzero(mask)[0]
    if on.size > 1:
        for g in np.nonzero(np.diff(on) > 1)[0]:
            a, z = on[g] + 1, on[g + 1]
            if (z - a) / 100 < hold:
                mask[a:z] = True
    last = np.maximum.accumulate(np.where(mask, idx, -(10**9)))
    upcoming = np.minimum.accumulate(np.where(mask, idx, 10**9)[::-1])[::-1]

    def ramp(u: np.ndarray) -> np.ndarray:
        return 0.5 + 0.5 * np.cos(np.pi * np.clip(u, 0.0, 1.0))

    down = ramp((upcoming - idx) / 100 / attack) if attack > 0 else (upcoming <= idx).astype(float)
    up = ramp((idx - last) / 100 / release) if release > 0 else (last >= idx).astype(float)
    return -depth * np.maximum(down, up)


def speech_spans(voice: np.ndarray) -> list[tuple[float, float]]:
    """Where a narration track speaks (seconds): 10 ms frames within 40 dB of its loudest."""
    mono = np.asarray(voice, dtype=np.float64).reshape(len(voice), -1).mean(axis=1)
    step = RATE // 100
    count = len(mono) // step
    rms = np.sqrt(np.mean(mono[: count * step].reshape(count, step) ** 2, axis=1))
    on = rms > max(float(rms.max()), 1e-9) * 10 ** (-40 / 20)
    edges = np.diff(np.concatenate([[0], on.astype(np.int8), [0]]))
    return [(a / 100, z / 100) for a, z in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]


def load_narration(path: Path | None) -> tuple[np.ndarray, str]:
    """A narration track (stereo float64) and its name: ``path`` as it is (vidgen plays narration at
    its own level) or the shipped sample."""
    source = path or NARRATION_SAMPLE
    voice = np.asarray(decode_audio(source), dtype=np.float64)
    voice = np.repeat(voice, 2, axis=1) if voice.shape[1] == 1 else voice
    return voice[: 60 * RATE], source.name


def narration_demo(music: np.ndarray, voice: np.ndarray, tail: float = 0.0) -> tuple[np.ndarray, dict[str, float]]:
    """The music (looped from its start, at volume 0: -28 LUFS) under ``voice`` with vidgen's
    default ducking, a 1.5 s fade-in and a 2 s fade-out, then set to the video's level (-16
    LUFS, true peak at most -1.5 dBTP). Returns the stereo mix and what was measured while the
    voice speaks: its loudness, the music's, and how far the voice's 300 Hz-3 kHz stands over
    the music's (dB)."""
    total = len(voice) + int(tail * RATE)
    voice = np.concatenate([voice, np.zeros((total - len(voice), 2))])
    spans = speech_spans(voice)
    frames = total // (RATE // 100) + 2
    gain_db = np.interp(np.arange(total) / (RATE // 100), np.arange(frames), duck_gain_db(spans, frames))
    t = np.arange(total) / RATE
    fades = np.clip(t / 1.5, 0, 1) * np.clip((total / RATE - t) / 2.0, 0, 1)
    bed = np.asarray(music, dtype=np.float64)[np.arange(total) % len(music)] * (fades * 10 ** (gain_db / 20))[:, None]
    mix = voice + bed
    speaking = np.zeros(total, bool)
    for a, z in spans:
        speaking[int(a * RATE) : int(z * RATE)] = True
    hop = RATE // 20
    vf, bf = measure_frames(voice, False, hop, image=False), measure_frames(bed, False, hop, image=False)
    pick = speaking[np.minimum(vf.centres, total - 1)]
    clear = _db(float(vf.bands["voice"][pick].sum())) - _db(float(bf.bands["voice"][pick].sum())) if pick.any() else math.inf
    level = integrated_loudness(mix)
    scale = 10 ** ((DEMO_LUFS - level) / 20) if math.isfinite(level) else 1.0
    peak = float(peak_envelope(mix * scale).max())
    if peak > 10 ** (DEMO_TRUE_PEAK / 20):
        scale *= 10 ** (DEMO_TRUE_PEAK / 20) / peak
    facts = {
        "seconds": round(total / RATE, 2),
        "voice_lufs": round(integrated_loudness(voice[speaking]), 2) if speaking.any() else None,
        "music_under_voice_lufs": round(integrated_loudness(bed[speaking]), 2) if speaking.any() else None,
        "music_alone_lufs": round(integrated_loudness(bed[~speaking & (t > 1.5)]), 2) if (~speaking & (t > 1.5)).sum() > RATE else None,
        "voice_clear_db": round(clear, 2),
    }
    return (mix * scale).astype(np.float32), facts


def add_demo(report: MusicCheck, voice: np.ndarray, narration: str, tail: float = 0.0) -> np.ndarray:
    """Make the narration demo of ``report``'s piece, add what it measured to the report
    (``facts["demo"]`` and a ``narration`` finding) and return the demo's samples."""
    mix, facts = narration_demo(report.audio, voice, tail)
    facts["narration"] = narration
    report.facts["demo"] = facts
    report.findings.append(demo_finding(facts, narration))
    return mix


def demo_finding(facts: dict[str, Any], narration: str) -> Finding:
    """What the demo measured, in words."""
    clear = facts["voice_clear_db"]
    text = (f"under {narration} with vidgen's default ducking ({DUCK[0]:g} dB): voice {facts['voice_lufs']} LUFS, music under it "
            f"{facts['music_under_voice_lufs']} LUFS; the voice's range stands {clear:.1f} dB over the music's")
    if clear < LIMITS["voice_clear_db"]:
        return Finding("narration", "fix", text + f" (it should be at least {LIMITS['voice_clear_db']:g} dB: words will be hard to follow)",
                       ["see the voice-range advice; or duck deeper in the video: `music: {source: ..., duck: {depth: 18}}`"])
    return Finding("narration", "ok", text)


# ----- words -----------------------------------------------------------------------------------


def music_check_text(report: MusicCheck) -> str:
    """The report in plain words (what ``vidgen music check`` prints)."""
    f = report.facts
    lines = []
    if report.kind == "score":
        lines.append(f"{report.name}: {f['key']}, {f['tempo']:g} BPM, {f['time']}, {f['bars']} bars = {report.seconds:.1f} s "
                     f"({'a loop' if report.loop else 'one pass'})")
    else:
        lines.append(f"{report.name}: an audio file, {report.seconds:.1f} s")
    lines.append(f"verdict: {report.verdict}")
    lines.append("")
    width = max(len(x.topic) for x in report.findings)
    for x in report.findings:
        mark = {"ok": "ok  ", "note": "note", "fix": "FIX "}[x.level]
        lines.append(f"  {mark} {x.topic:<{width}}  {x.text}")
    if report.sections:
        lines.append("")
        lines.append("sections (LUFS; brightness = level above 2 kHz):")
        for s in report.sections:
            extra = ""
            if "lift_db" in s:
                extra += f"  lift {s['lift_db']:+.1f} dB, {s['lift_brighter_db']:+.1f} dB brighter"
            if "build_db" in s:
                extra += f"  build {s['build_db']:+.1f} dB, {s['brighter_db']:+.1f} dB brighter"
            lines.append(f"  {s['name']:<10} bars {s['first_bar']:>3}-{s['first_bar'] + s['bars'] - 1:<3} {s['start']:6.1f} s  {s['lufs']:6.1f} LUFS  "
                         f"brightness {s['bright_db']:6.1f} dB{extra}")
    if report.tracks:
        lines.append("")
        lines.append("tracks (share of the power: all / voice range / bass / highs; peak against the mix's):")
        for t in report.tracks:
            lines.append(f"  {t['name']:<12} {t['instrument']:<12} {100 * t['all_share']:5.1f} % {100 * t['voice_share']:5.1f} % "
                         f"{100 * t['bass_share']:5.1f} % {100 * t['highs_share']:5.1f} %   {t['peak_db']:+6.1f} dB")
    advice = [x for x in report.findings if x.level != "ok" and x.fixes]
    if advice:
        lines.append("")
        lines.append("advice (change one thing, check again, compare):")
        for x in advice:
            lines.append(f"  {x.topic}:")
            lines.extend(f"    - {fix}" for fix in x.fixes)
    return "\n".join(lines)


#: Rows of the side-by-side table: (label, fact key, format).
COMPARE_ROWS = (
    ("length (s)", "seconds", "{:.1f}"),
    ("loudness (LUFS)", "lufs", "{:.1f}"),
    ("steadiness (dB)", "steadiness_db", "{:.1f}"),
    ("true peak (dBTP)", "true_peak", "{:.1f}"),
    ("peak over loudness (dB)", "peak_to_loudness_db", "{:.1f}"),
    ("tempo heard (BPM)", "tempo_heard", "{:.1f}"),
    ("loop seam (x)", "seam_ratio", "{:.2f}"),
    ("voice range share (%)", "voice_share", "{:.0%}"),
    ("loudest voice bar (dB)", "voice_bar_max_db", "{:.1f}"),
    ("bass share (%)", "bass_share", "{:.0%}"),
    ("highs (dB)", "highs_db", "{:.1f}"),
    ("key heard", "key_heard", "{}"),
    ("on the key's notes (%)", "in_key", "{:.0%}"),
    ("voice clear of music (dB)", "voice_clear_db", "{:.1f}"),
)


def compare_rows(a: MusicCheck, b: MusicCheck) -> list[dict[str, Any]]:
    """The side-by-side table of two checks (``label``, ``a``, ``b`` as text)."""
    rows = []
    for label, key, fmt in COMPARE_ROWS:
        values = []
        for r in (a, b):
            v = r.seconds if key == "seconds" else r.facts.get(key, r.facts.get("demo", {}).get(key))
            values.append("-" if v is None else fmt.format(v))
        rows.append({"label": label, "a": values[0], "b": values[1]})
    rows.append({"label": "verdict", "a": a.verdict, "b": b.verdict})
    return rows


def compare_text(a: MusicCheck, b: MusicCheck) -> str:
    rows = compare_rows(a, b)
    wa = max(len(a.name), *(len(r["a"]) for r in rows[:-1]))
    lines = [f"{'':<26} {a.name:<{wa}}  {b.name}"]
    lines += [f"{r['label']:<26} {r['a']:<{wa}}  {r['b']}" for r in rows]
    return "\n".join(lines)


def check_dict(report: MusicCheck) -> dict[str, Any]:
    """The report as JSON-ready data (``vidgen music check --json``)."""
    return {
        "name": report.name,
        "kind": report.kind,
        "seconds": round(report.seconds, 3),
        "loop": report.loop,
        "verdict": report.verdict,
        "facts": report.facts,
        "findings": [{"topic": x.topic, "level": x.level, "text": x.text, "fixes": x.fixes} for x in report.findings],
        "sections": report.sections,
        "tracks": report.tracks,
        "timings": report.timings,
    }


# ----- pictures --------------------------------------------------------------------------------

_STOPS = ((0, 0, 4), (40, 11, 84), (101, 21, 110), (159, 42, 99), (212, 72, 66), (245, 125, 21), (250, 193, 39), (252, 255, 164))
#: The picture's level range, dB of a frame's power at -28 LUFS (the same for every piece).
IMAGE_DB = (-105.0, -30.0)
_LANE = 46
_HEAD = 18
_LEFT = 34


def _font(size: int = 11) -> Any:
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _colour(v: np.ndarray) -> np.ndarray:
    stops = np.asarray(_STOPS, dtype=np.float64)
    pos = np.clip(v, 0, 1) * (len(stops) - 1)
    i = np.minimum(pos.astype(int), len(stops) - 2)
    t = (pos - i)[..., None]
    return (stops[i] * (1 - t) + stops[i + 1] * t).astype(np.uint8)


def _row_image(report: MusicCheck, width: int) -> Any:
    """One piece: a title line, the spectrogram with section marks and the voice band's edges,
    and a lane with each bar's voice-range level against the limit."""
    from PIL import Image, ImageDraw

    frames = report.frames
    assert frames.image is not None
    cols = frames.image.shape[1]
    height = _HEAD + IMAGE_ROWS + _LANE
    im = Image.new("RGB", (width, height), (18, 18, 22))
    spec = _colour((frames.image - IMAGE_DB[0]) / (IMAGE_DB[1] - IMAGE_DB[0]))
    im.paste(Image.fromarray(spec), (_LEFT, _HEAD))
    d = ImageDraw.Draw(im)
    font = _font()
    f = report.facts
    title = f"{report.name}   {report.verdict}   voice range {100 * f['voice_share']:.0f} %, bass {100 * f['bass_share']:.0f} %, highs {f['highs_db']:.0f} dB"
    d.text((4, 3), title, fill=(235, 235, 235), font=font)
    rows = np.geomspace(IMAGE_HZ[1], IMAGE_HZ[0], IMAGE_ROWS)
    for hz in (100, 300, 1000, 3000, 10000):
        y = _HEAD + int(np.argmin(np.abs(rows - hz)))
        voice = hz in (300, 3000)
        colour = (90, 200, 255) if voice else (110, 110, 110)
        for x0 in range(_LEFT, _LEFT + cols, 6 if voice else 4):
            d.point((x0, y), fill=colour)
        d.text((2, y - 6), f"{hz}" if hz < 1000 else f"{hz // 1000}k", fill=(200, 200, 200), font=font)
    hop = int(frames.centres[1] - frames.centres[0]) if len(frames.centres) > 1 else RATE // 20
    px = RATE / hop  # columns per second
    lane_top = _HEAD + IMAGE_ROWS
    for s in range(0, int(report.seconds) + 1, 10):
        x0 = _LEFT + int(s * px)
        d.line([(x0, lane_top - 5), (x0, lane_top)], fill=(255, 255, 255))
        d.text((x0 + 2, lane_top - 14), f"{s}s", fill=(255, 255, 255), font=font)
    for seconds, name in report.marks:
        x0 = _LEFT + int(seconds * px)
        d.line([(x0, _HEAD), (x0, height)], fill=(255, 255, 255), width=1)
        d.text((x0 + 3, _HEAD + 2), name, fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    # the lane: each bar's voice-range level, red above the limit
    voice = f["bar_voice_db"]
    lo, hi = LIMITS["voice_bar_db"] - 20, LIMITS["voice_bar_db"] + 4
    limit_y = lane_top + _LANE - 4 - int((LIMITS["voice_bar_db"] - lo) / (hi - lo) * (_LANE - 8))
    for k, v in enumerate(voice):
        x0, x1 = _LEFT + int(k * report.bar / hop), _LEFT + int((k + 1) * report.bar / hop) - 1
        top = lane_top + _LANE - 4 - int((min(max(v, lo), hi) - lo) / (hi - lo) * (_LANE - 8))
        d.rectangle([x0, top, max(x0, x1), lane_top + _LANE - 4], fill=(220, 70, 60) if v > LIMITS["voice_bar_db"] else (70, 150, 200))
    d.line([(_LEFT, limit_y), (_LEFT + cols, limit_y)], fill=(255, 210, 80), width=2)
    d.text((_LEFT + cols - 30, limit_y - 13), "limit", fill=(255, 210, 80), font=font)
    d.text((2, lane_top + 4), "voice", fill=(200, 200, 200), font=font)
    d.text((2, lane_top + 16), "range", fill=(200, 200, 200), font=font)
    return im


def spectrogram_image(reports: Sequence[MusicCheck]) -> Any:
    """One row per report (two for ``--compare``) on the same time scale: a PIL image."""
    from PIL import Image

    width = _LEFT + max(r.frames.image.shape[1] for r in reports if r.frames.image is not None) + 4
    rows = [_row_image(r, width) for r in reports]
    sheet = Image.new("RGB", (width, sum(r.height for r in rows) + 4 * (len(rows) - 1)), (0, 0, 0))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 4
    return sheet
