"""The final audio mix (DESIGN.md §48): narration (+ clip sound), sound effects and background
music, ducking, loudness normalisation and a true-peak limiter.

``vidgen render`` builds three tracks for the whole video: the *voice* track (the scenes' padded
WAVs: narration and clip sound, Step 4 / 35), the *SFX* track (Step 44) and, here, the *music*
track. Music is ducked under the narration only: the key is where the narrator speaks — each
beat from its start to the end of its speech (the MP3's trailing silence cut off; the whole beat
for a beat without audio), pauses shorter than ``duck.hold`` filled — plus, with
``duck.clips``, the scenes whose ``video_clip`` has sound. Sound effects never duck the music.
The gain curve is computed at 100 Hz (10 ms frames) and interpolated per sample: in dB, the
music falls by ``depth`` over ``attack`` seconds *ending* where the speech starts (the mix is
offline, so it can look ahead) and rises over ``release`` seconds after it ends, both with
raised-cosine shapes.

The sum is written block by block (10 s, never the whole video in memory) to
``padded/mix.wav`` (48 kHz stereo, 24-bit), which the final mux encodes once. With
normalisation the sum is measured first (BS.1770-4 integrated loudness, :mod:`vidgen.loudness`)
and scaled to ``audio.target_lufs``; a look-ahead true-peak limiter (10 ms, gain never above
what keeps the 4x-oversampled peak under ``audio.true_peak``) then catches the peaks. Every step
is deterministic numpy.
"""

from __future__ import annotations

import logging
import math
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen import loudness
from vidgen.config import DuckConfig, MusicCue, SceneMusic
from vidgen.errors import VidgenError
from vidgen.music import Source, is_bed
from vidgen.sfx import RATE

if TYPE_CHECKING:
    from vidgen.project import Project

log = logging.getLogger("vidgen.mix")

#: Samples per control frame of the music's gain curve (10 ms).
FRAME = RATE // 100
#: Seconds over which the music's level changes at a scene with its own ``music:`` setting
#: (ending where a quieter scene starts, starting where it ends).
SCENE_RAMP = 0.75
#: Look-ahead / smoothing of the true-peak limiter (samples).
LIMITER_WINDOW = RATE // 100
#: The limiter aims this far (dB) under ``audio.true_peak``: room for the interpolation and for
#: the AAC encode, which moved the gallery's true peak up by 0.2 dB (Step 48).
LIMITER_MARGIN_DB = 0.4


# ----- tracks ----------------------------------------------------------------------------------------


class WavTrack:
    """Consecutive 16-bit stereo 48 kHz WAV files read as one signal (``read(a, b)`` → float64
    ``(b - a, 2)``)."""

    def __init__(self, files: Sequence[Path]) -> None:
        self.parts: list[tuple[Path, int, int]] = []
        start = 0
        for path in files:
            with wave.open(str(path), "rb") as src:
                if src.getnchannels() != 2 or src.getsampwidth() != 2 or src.getframerate() != RATE:
                    raise VidgenError(f"{path}: expected a 48 kHz stereo 16-bit WAV")
                frames = src.getnframes()
            self.parts.append((path, start, frames))
            start += frames
        self.length = start

    def read(self, a: int, b: int) -> np.ndarray:
        out = np.zeros((b - a, 2))
        for path, start, frames in self.parts:
            lo, hi = max(a, start), min(b, start + frames)
            if lo >= hi:
                continue
            with wave.open(str(path), "rb") as src:
                src.setpos(lo - start)
                data = np.frombuffer(src.readframes(hi - lo), dtype="<i2").reshape(-1, 2)
            out[lo - a : lo - a + len(data)] = data / 32768
        return out


def _ramp(u: np.ndarray) -> np.ndarray:
    """Raised cosine: 1 at ``u <= 0`` falling to 0 at ``u >= 1``."""
    return 0.5 + 0.5 * np.cos(np.pi * np.clip(u, 0.0, 1.0))


def _spans_mask(spans: Sequence[tuple[float, float]], frames: int) -> np.ndarray:
    mask = np.zeros(frames, dtype=bool)
    for a, b in spans:
        lo, hi = max(0, math.floor(a * 100)), min(frames, math.ceil(b * 100))
        mask[lo:hi] = True
    return mask


def duck_curve(spans: Sequence[tuple[float, float]], frames: int, duck: DuckConfig) -> np.ndarray:
    """The ducking gain in dB per 10 ms frame (0 or negative): ``-depth`` where something in the
    foreground (``spans``, seconds) sounds or pauses for less than ``hold``; ramps of ``attack``
    seconds ending where it starts and ``release`` seconds starting where it ends."""
    if duck.depth == 0 or not spans:
        return np.zeros(frames)
    mask = _spans_mask(spans, frames)
    idx = np.arange(frames)
    on = np.nonzero(mask)[0]
    if on.size > 1:  # fill short pauses
        gaps = np.nonzero(np.diff(on) > 1)[0]
        for g in gaps:
            a, b = on[g] + 1, on[g + 1]
            if (b - a) / 100 < duck.hold:
                mask[a:b] = True
    last = np.maximum.accumulate(np.where(mask, idx, -(10**9)))
    upcoming = np.minimum.accumulate(np.where(mask, idx, 10**9)[::-1])[::-1]
    since = (idx - last) / 100
    until = (upcoming - idx) / 100
    down = _ramp(until / duck.attack) if duck.attack > 0 else (until <= 0).astype(float)
    up = _ramp(since / duck.release) if duck.release > 0 else (since <= 0).astype(float)
    return -duck.depth * np.maximum(down, up)


def _running_min(x: np.ndarray, half: int) -> np.ndarray:
    """The minimum of ``x`` over ``[i - half, i + half]`` for every ``i`` (edges: what exists)."""
    if half <= 0:
        return x.copy()
    padded = np.concatenate([np.full(half, np.inf), x, np.full(half, np.inf)])
    window = 2 * half + 1
    size = -(-len(padded) // window) * window
    padded = np.concatenate([padded, np.full(size - len(padded), np.inf)])
    blocks = padded.reshape(-1, window)
    prefix = np.minimum.accumulate(blocks, axis=1).ravel()
    suffix = np.minimum.accumulate(blocks[:, ::-1], axis=1)[:, ::-1].ravel()
    i = np.arange(len(x))
    return np.minimum(suffix[i], prefix[i + window - 1])


def _moving_average(x: np.ndarray, width: int) -> np.ndarray:
    """The mean of ``x`` over a centred window of ``width`` samples (edges: the edge value)."""
    if width <= 1:
        return x.copy()
    half = width // 2
    padded = np.concatenate([np.full(half, x[0]), x, np.full(width - half - 1, x[-1])])
    total = np.concatenate([[0.0], np.cumsum(padded)])
    return (total[width:] - total[:-width]) / width


def smooth_steps(levels: np.ndarray, width: int) -> np.ndarray:
    """``levels`` with every step turned into a ``width``-long ramp lying on the *louder* side
    (a minimum filter then a moving average: the result is never above ``levels``, and the
    quieter side keeps its level up to and including the step's sample)."""
    return _moving_average(_running_min(levels, width // 2 + 1), width)


@dataclass
class Placement:
    """A music cue placed in the video: samples ``start`` to ``end``, its source and its gain per
    10 ms frame of the whole video (linear)."""

    index: int
    cue: MusicCue
    start: int
    end: int
    scenes: list[str]
    source: Source
    gain: np.ndarray

    def summary(self) -> dict[str, Any]:
        """``{source, kind, from, to, start, end, volume, duck}`` (times in seconds)."""
        return {
            "source": self.cue.source,
            "kind": "bed" if is_bed(self.cue.source) else "file",
            "from": self.scenes[0],
            "to": self.scenes[-1],
            "start": round(self.start / RATE, 6),
            "end": round(self.end / RATE, 6),
            "volume": self.cue.volume,
            "duck": self.cue.duck.depth,
        }


class MusicTrack:
    """The music of the whole video: every cue's source times its gain curve."""

    def __init__(self, placements: Sequence[Placement]) -> None:
        self.placements = list(placements)

    def read(self, a: int, b: int) -> np.ndarray:
        out = np.zeros((b - a, 2))
        for p in self.placements:
            lo, hi = max(a, p.start), min(b, p.end)
            if lo >= hi:
                continue
            gain = np.interp(np.arange(lo, hi) / FRAME, np.arange(len(p.gain)), p.gain)
            out[lo - a : hi - a] += p.source.read(lo - p.start, hi - p.start) * gain[:, None]
        return out


# ----- planning --------------------------------------------------------------------------------------


def speech_spans(project: Project, timings: dict[str, Any]) -> list[tuple[float, float]]:
    """Where the narrator speaks (video seconds): each beat from its start to the end of its
    speech (the MP3's silence cut off), or the whole beat without audio."""
    from vidgen.speech import speech_bounds

    spans = []
    for scene in timings["scenes"]:
        for beat in scene["beats"]:
            start, end = beat["start"], beat["end"]
            mp3 = project.audio_dir / f"{beat['id']}.mp3"
            if mp3.is_file():
                try:
                    s0, s1 = speech_bounds(mp3)
                    start, end = min(start + s0, end), min(start + s1, end)
                except VidgenError:
                    pass
            if end > start:
                spans.append((start, end))
    return spans


def clip_spans(project: Project, timings: dict[str, Any]) -> list[tuple[float, float]]:
    """The scenes whose ``video_clip`` plays sound (not muted, volume above 0, the file has
    audio), as video seconds."""
    from vidgen.clips import probe_clip

    spans = []
    for spec, scene in zip(project.config.scenes, timings["scenes"]):
        params = spec.params
        if spec.type != "video_clip" or params.get("mute") or params.get("volume", 1) == 0 or not params.get("path"):
            continue
        try:
            has_audio = probe_clip(project.root / str(params["path"])).audio
        except VidgenError:
            continue
        if has_audio:
            spans.append((scene["start"], scene["start"] + scene["duration"]))
    return spans


def _scene_level(setting: bool | SceneMusic) -> float:
    if isinstance(setting, SceneMusic):
        return 10 ** (setting.volume / 20)
    return 1.0 if setting else 0.0


def _fade_curve(times: np.ndarray, start: float, end: float, fade_in: float, fade_out: float) -> np.ndarray:
    """1 between the fades; raised-cosine fade-in from ``start``, fade-out ending at ``end``,
    0 outside."""
    out = np.where((times >= start) & (times <= end), 1.0, 0.0)
    if fade_in > 0:
        out *= 1 - _ramp((times - start) / fade_in)
    if fade_out > 0:
        out *= 1 - _ramp((end - times) / fade_out)
    return out


def plan_music(project: Project, timings: dict[str, Any], total: int) -> list[Placement]:
    """Place the ``music:`` cues in the video of ``total`` samples (``timings``: the combined
    timings): their spans, sources and gain curves (volume, fades, scene levels, ducking)."""
    cfg = project.config
    cues = cfg.music_cues
    if not cues:
        return []
    scenes = timings["scenes"]
    order = [s["id"] for s in scenes]
    frames = total // FRAME + 2
    times = np.arange(frames) * FRAME / RATE
    # the level each scene asks for, per frame, its steps smoothed into ramps on the louder side
    levels = np.ones(frames)
    for spec, scene in zip(cfg.scenes, scenes):
        lo = round(scene["start"] * 100)
        levels[lo:] = _scene_level(spec.music)
    scene_curve = smooth_steps(levels, round(SCENE_RAMP * 100))
    speech = speech_spans(project, timings)
    clips = None
    placements = []
    for k, cue in enumerate(cues):
        first = order.index(cue.from_) if cue.from_ else 0
        last = order.index(cue.to) if cue.to else len(order) - 1
        start = round(scenes[first]["start"] * RATE)
        end = total if last == len(order) - 1 else round((scenes[last]["start"] + scenes[last]["duration"]) * RATE)
        source = Source(cue, project.root)
        stop = end if source.ends_at is None else min(end, start + source.ends_at)
        spans = speech
        if cue.duck.clips and cue.duck.depth > 0:
            clips = clip_spans(project, timings) if clips is None else clips
            spans = speech + clips
        gain = (
            10 ** (cue.volume / 20)
            * _fade_curve(times, start / RATE, stop / RATE, cue.fade_in, cue.fade_out)
            * scene_curve
            * 10 ** (duck_curve(spans, frames, cue.duck) / 20)
        )
        placements.append(Placement(k, cue, start, stop, order[first : last + 1], source, gain))
    return placements


# ----- the mix ---------------------------------------------------------------------------------------


@dataclass
class MixReport:
    """What the final mix measured and did (``timings.json`` ``mix``, ``vidgen render --json``)."""

    mixed: bool  # written by this module (else: narration + effects joined by ffmpeg as before)
    normalized: bool
    target_lufs: float | None
    true_peak_limit: float | None
    gain_db: float
    integrated_lufs: float
    true_peak_dbtp: float
    limited_db: float  # the limiter's largest gain reduction (0: never engaged)
    music: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        def num(value: float | None) -> float | None:
            return None if value is None or not math.isfinite(value) else round(value, 2)

        return {
            "mixed": self.mixed,
            "normalized": self.normalized,
            "target_lufs": self.target_lufs,
            "true_peak_limit": self.true_peak_limit,
            "gain_db": num(self.gain_db),
            "integrated_lufs": num(self.integrated_lufs),
            "true_peak_dbtp": num(self.true_peak_dbtp),
            "limited_db": num(self.limited_db),
            "music": self.music,
        }


def limit(x: np.ndarray, ceiling: float) -> tuple[np.ndarray, float]:
    """``x`` (``(n, c)``) with its true peaks kept under ``ceiling`` (linear) by a smooth gain:
    the gain each sample needs, its minimum over ±1 window, averaged over a window (never above
    the need). Returns the limited signal and the lowest gain applied."""
    need = np.minimum(1.0, ceiling / np.maximum(loudness.peak_envelope(x), 1e-12))
    if need.min() >= 1.0:
        return x, 1.0
    gain = smooth_steps(need, LIMITER_WINDOW)
    return x * gain[:, None], float(gain.min())


def _write_block(out: wave.Wave_write, x: np.ndarray) -> None:
    ints = np.clip(np.round(x * 8388607), -8388608, 8388607).astype("<i4")
    out.writeframes(ints.view(np.uint8).reshape(-1, 4)[:, :3].tobytes())


def write_mix(
    path: Path, read: Callable[[int, int], np.ndarray], total: int, gain_db: float, true_peak: float
) -> tuple[loudness.LoudnessMeter, float]:
    """Write ``read(a, b)`` × ``gain_db`` through the limiter (``true_peak`` dBTP) to ``path``
    (48 kHz stereo 24-bit), block by block; returns the output's meter and the lowest limiter
    gain."""
    gain = 10 ** (gain_db / 20)
    ceiling = 10 ** ((true_peak - LIMITER_MARGIN_DB) / 20)
    meter = loudness.LoudnessMeter()
    lowest = 1.0
    m = loudness.MARGIN
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(3)
        out.setframerate(RATE)
        for lo, hi, ext in loudness.blocks(total, read):
            limited, low = limit(ext * gain, ceiling)
            lowest = min(lowest, low)
            part = slice(m, m + hi - lo)
            meter.add(loudness.kweighted_power(limited)[part], loudness.peak_envelope(limited)[part])
            _write_block(out, limited[part])
    return meter, lowest


def _has_narration_audio(project: Project) -> bool:
    """Whether some beat has its MP3, or the video has no narrated beats at all."""
    beats = [beat.id for _, beat in project.beats()]
    return not beats or any((project.audio_dir / f"{b}.mp3").is_file() for b in beats)


def mix_audio(project: Project, timings: dict[str, Any], voices: Sequence[Path], sfx_track: Path | None, out: Path) -> MixReport:
    """Mix the video's audio (``timings``: combined timings; ``voices``: the padded scene WAVs in
    order; ``sfx_track``: the SFX track or ``None``).

    With music or normalisation (``audio.normalize``: true, or ``auto`` with music) the mix is
    written to ``out`` and the report says ``mixed``; otherwise nothing is written (the final
    mux sums narration and effects as before) and the report only measures that sum. A video
    whose narrated beats have no MP3 yet is not normalised.
    """
    audio = project.config.audio
    voice = WavTrack(voices)
    total = voice.length
    sfx = WavTrack([sfx_track]) if sfx_track is not None else None
    placements = plan_music(project, timings, total)
    music = MusicTrack(placements) if placements else None

    def read(a: int, b: int) -> np.ndarray:
        x = voice.read(a, b)
        if sfx is not None:
            x += sfx.read(a, b)
        if music is not None:
            x += music.read(a, b)
        return x

    normalize = audio.normalize is True or (audio.normalize == "auto" and bool(placements))
    if normalize and not _has_narration_audio(project):
        # Normalising a video whose narration is not voiced yet would lift the music and the
        # effects to the target on their own (a preview timed from word counts).
        log.info("no narration audio yet (vidgen tts): the mix is not normalised")
        normalize = False
    summaries = [p.summary() for p in placements]
    out.unlink(missing_ok=True)
    if not normalize and music is None:
        meter = loudness.measure(total, read)
        return MixReport(False, False, None, None, 0.0, meter.integrated, meter.true_peak, 0.0, summaries)
    gain_db = 0.0
    if normalize:
        before = loudness.measure(total, read, peaks=False).integrated
        if math.isfinite(before):
            gain_db = audio.target_lufs - before
        else:
            log.warning("the audio is silent; it is not normalised")
    meter, lowest = write_mix(out, read, total, gain_db, audio.true_peak)
    return MixReport(
        True,
        normalize,
        audio.target_lufs if normalize else None,
        audio.true_peak,
        gain_db,
        meter.integrated,
        meter.true_peak,
        -20 * math.log10(lowest) if lowest > 0 else math.inf,
        summaries,
    )
