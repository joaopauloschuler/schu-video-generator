"""The final audio mix (DESIGN.md §48): narration (+ clip sound), sound effects and background
music, ducking, loudness normalisation and a true-peak limiter.

``vidgen render`` builds three tracks for the whole video: the *voice* track (the scenes' padded
WAVs: narration and clip sound, Step 4 / 35), the *SFX* track (Step 44) and, here, the *music*
track. Music is ducked under the narration only: the key is where the narrator speaks — each
beat from its start to the end of its speech (the MP3's trailing silence cut off; the whole beat
for a beat without audio), pauses shorter than ``duck.hold`` filled — plus, with
``duck.clips``, the scenes whose ``video_clip`` has sound. Sound effects never duck the music;
a beat's music sting, on the SFX track, ducks under the narration too (:func:`sting_ducking`).
The rain bed of a stage's rain (:mod:`vidgen.ambience`) is mixed with the music, ducked less
(:func:`plan_ambience`).
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

Opt-in (DESIGN.md §111.2): ``audio.level_voice`` puts a gentle leveller on the voice track before
the sum (:class:`LevelledTrack`); an audio-only render's loudness preset passes
:class:`MixTargets` (a file loudness or RMS, a mono mix, a limiter setting, a room tone added
after the gain). ``audio.music_width`` / ``ambience_width`` (§111.4) scale the side signal of the
music and of the beds. Without them a video's mix is what it was.

Opt-in (DESIGN.md §112.2): the scenes' themes and the beats' motifs of ``score:``
(:func:`plan_score`, :mod:`vidgen.scoring`) are music placements beside the cues; a duck's
``swell`` lifts the music in the pauses (:func:`duck_gain_db`); ``score.check`` measures the music
under dense dialogue after the mix.
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

from vidgen import loudness, musicfit
from vidgen.ambience import AMBIENCE_BEDS, BEDS, LoopSource, ambience_spans, designed_entries
from vidgen.config import DuckConfig, MusicCue, SceneMusic
from vidgen.errors import VidgenError
from vidgen.music import Source, cue_scene_range, fallback_bed
from vidgen.sfx import RATE
from vidgen.staging import widen

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
#: How a beat's music sting (DESIGN.md §69.19) ducks under the narration: by the music's
#: ducking curve (:func:`duck_curve` over :func:`speech_spans`), lighter and quicker, and with no
#: hold (a sting lasts 1-2.5 s; the music's 1.5 s hold would keep it down through every pause).
STING_DUCK = DuckConfig(depth=6.0, attack=0.15, release=0.3, hold=0.0, clips=False)
#: The limiter aims this far (dB) under ``audio.true_peak``: room for the interpolation and for
#: the AAC encode, which moved the gallery's true peak up by 0.2 dB (Step 48).
LIMITER_MARGIN_DB = 0.4
#: The voice leveller (``audio.level_voice``, DESIGN.md §111.2): 3:1 with a 6 dB soft knee
#: above the voices' usual peak (the median 10 ms peak of the frames within 45 dB of the
#: loudest, plus 8 dB), its gain ramped over 50 ms on the louder side (look-ahead: the mix is
#: offline). Chosen on Step 283's samples: the limiter's gain reduction at -16 LUFS fell from
#: 5.0 to 0.6 dB (ElevenLabs) and 0.4 to 0 dB (Kokoro), the voices lowered 0.4 dB on average
#: where they are lowered at all.
LEVEL_ABOVE_DB = 8.0
LEVEL_RATIO = 3.0
LEVEL_KNEE_DB = 6.0
LEVEL_RAMP_FRAMES = 5
LEVEL_RANGE_DB = 45.0
#: Length of the room tone's loop (``audio_output.room_tone``; samples) and its band (Hz).
ROOM_TONE_LOOP = RATE * 10
ROOM_TONE_BAND = (80.0, 6000.0)


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


def frame_peaks(track: WavTrack) -> np.ndarray:
    """The sample peak (dBFS, over both channels) of every 10 ms frame of ``track``, read 10 s
    at a time."""
    frames = -(-track.length // FRAME)
    out = np.zeros(frames)
    step = FRAME * 1000
    for lo in range(0, track.length, step):
        x = np.max(np.abs(track.read(lo, min(track.length, lo + step))), axis=1)
        n = -(-len(x) // FRAME)
        out[lo // FRAME : lo // FRAME + n] = np.pad(x, (0, n * FRAME - len(x))).reshape(n, FRAME).max(axis=1)
    return 20 * np.log10(np.maximum(out, 1e-9))


def leveller_gain(peaks_db: np.ndarray) -> np.ndarray:
    """The voice leveller's gain (dB per 10 ms frame, 0 or negative) for frame peaks
    ``peaks_db`` (see :data:`LEVEL_ABOVE_DB`)."""
    if not len(peaks_db) or peaks_db.max() <= -150:
        return np.zeros(len(peaks_db))
    active = peaks_db > peaks_db.max() - LEVEL_RANGE_DB
    over = peaks_db - (float(np.median(peaks_db[active])) + LEVEL_ABOVE_DB)
    slope, knee = 1 - 1 / LEVEL_RATIO, LEVEL_KNEE_DB
    soft = slope * (over + knee / 2) ** 2 / (2 * knee)
    reduction = np.where(over <= -knee / 2, 0.0, np.where(over >= knee / 2, slope * over, soft))
    return smooth_steps(-reduction, LEVEL_RAMP_FRAMES)


class LevelledTrack:
    """A voice track through the leveller (:func:`leveller_gain`, its curve computed once over
    the whole track); ``reduction_db`` is its largest gain reduction."""

    def __init__(self, track: WavTrack) -> None:
        self.track = track
        self.length = track.length
        self.gain = leveller_gain(frame_peaks(track))
        self.reduction_db = float(-self.gain.min()) if len(self.gain) else 0.0

    def read(self, a: int, b: int) -> np.ndarray:
        x = self.track.read(a, b)
        if not len(self.gain):
            return x
        at = np.arange(a, b) / FRAME - 0.5
        return x * (10 ** (np.interp(at, np.arange(len(self.gain)), self.gain) / 20))[:, None]


def room_tone(level_db: float) -> np.ndarray:
    """A seamless loop (:data:`ROOM_TONE_LOOP` samples, mono) of faint pink noise in
    :data:`ROOM_TONE_BAND` at ``level_db`` dBFS RMS; always the same samples."""
    rng = np.random.default_rng(111)
    spectrum = np.fft.rfft(rng.standard_normal(ROOM_TONE_LOOP))
    freqs = np.fft.rfftfreq(ROOM_TONE_LOOP, 1 / RATE)
    band = (freqs >= ROOM_TONE_BAND[0]) & (freqs <= ROOM_TONE_BAND[1])
    spectrum = np.where(band, spectrum / np.sqrt(np.maximum(freqs, 1.0)), 0.0)
    loop = np.fft.irfft(spectrum, ROOM_TONE_LOOP)
    return loop * (10 ** (level_db / 20) / float(np.sqrt(np.mean(loop**2))))


def rms_db(total: int, read: Callable[[int, int], np.ndarray]) -> float:
    """The RMS (dBFS) of a whole signal over all its samples and channels (the ACX measure),
    read 10 s at a time."""
    power, count = 0.0, 0
    for lo in range(0, total, loudness.BLOCK):
        x = read(lo, min(total, lo + loudness.BLOCK))
        power += float(np.sum(x**2))
        count += x.size
    return 10 * math.log10(power / count) if power > 0 else -math.inf


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
    fit: dict[str, Any] | None = None  # composed music fitted to the video (musicfit summary)
    theme: str | None = None  # a scene's theme or a beat's motif (DESIGN.md §112.2): its name
    motif: bool = False

    def summary(self) -> dict[str, Any]:
        """``{source, kind, from, to, start, end, volume, duck}`` (times in seconds), and
        ``fit`` (sections, swells, pauses) for composed music fitted to the video; a theme's
        ``theme`` (and ``motif: true``) and ``swell``."""
        data: dict[str, Any] = {
            "source": self.source.label,
            "kind": self.source.kind,
            "from": self.scenes[0],
            "to": self.scenes[-1],
            "start": round(self.start / RATE, 6),
            "end": round(self.end / RATE, 6),
            "volume": self.cue.volume,
            "duck": self.cue.duck.depth,
        }
        if self.fit is not None:
            data["fit"] = self.fit
        if self.theme is not None:
            data["theme"] = self.theme
            if self.motif:
                data["motif"] = True
        if self.cue.duck.swell:
            data["swell"] = self.cue.duck.swell
        return data


@dataclass
class AmbiencePlacement:
    """An ambience bed (DESIGN.md §69.39) placed in the video: samples ``start`` to ``end``, its
    loop and its gain per 10 ms frame of the whole video (linear)."""

    bed: str
    start: int
    end: int
    source: LoopSource
    gain: np.ndarray
    duck: float
    width: float | None = None  # its own stereo width (a scene's ambience, DESIGN.md §112); None: audio.ambience_width

    def summary(self) -> dict[str, Any]:
        """``{bed, start, end, duck}`` (times in seconds), and ``width`` when it has its own."""
        data = {"bed": self.bed, "start": round(self.start / RATE, 6), "end": round(self.end / RATE, 6), "duck": self.duck}
        if self.width is not None:
            data["width"] = self.width
        return data


class MusicTrack:
    """The music of the whole video: every cue's source times its gain curve (and the ambience
    beds, mixed the same way); ``widths``: the stereo width of the music and of the beds
    (``audio.music_width`` / ``ambience_width``, DESIGN.md §111.4; 1: as they are)."""

    def __init__(self, placements: Sequence[Placement | AmbiencePlacement], widths: tuple[float, float] = (1.0, 1.0)) -> None:
        self.placements = list(placements)
        self.widths = widths

    def read(self, a: int, b: int) -> np.ndarray:
        out = np.zeros((b - a, 2))
        for p in self.placements:
            lo, hi = max(a, p.start), min(b, p.end)
            if lo >= hi:
                continue
            gain = np.interp(np.arange(lo, hi) / FRAME, np.arange(len(p.gain)), p.gain)
            part = p.source.read(lo - p.start, hi - p.start) * gain[:, None]
            if isinstance(p, AmbiencePlacement):
                width = self.widths[1] if p.width is None else p.width
            else:
                width = self.widths[0]
            out[lo - a : hi - a] += widen(part, width)
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


def sting_ducking(project: Project, timings: dict[str, Any], total: int) -> np.ndarray:
    """The ducking gain (dB per 10 ms frame of a video of ``total`` samples) of the SFX track's
    ducked events (a beat's ``sting``): :data:`STING_DUCK` where the narrator speaks."""
    return duck_curve(speech_spans(project, timings), total // FRAME + 2, STING_DUCK)


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


def _scene_curve(project: Project, scenes: Sequence[dict[str, Any]], frames: int) -> np.ndarray:
    """The level each scene's ``music:`` asks for, per frame, its steps smoothed into ramps on
    the louder side (:data:`SCENE_RAMP`)."""
    levels = np.ones(frames)
    for spec, scene in zip(project.config.scenes, scenes):
        lo = round(scene["start"] * 100)
        levels[lo:] = _scene_level(spec.music)
    return smooth_steps(levels, round(SCENE_RAMP * 100))


def duck_gain_db(spans: Sequence[tuple[float, float]], frames: int, duck: DuckConfig) -> np.ndarray:
    """The music's gain in dB per frame under ``spans`` (:func:`duck_curve`) plus its ``swell``:
    up to ``swell`` dB where it is not ducked, rising with the release and falling with the
    attack (DESIGN.md §112.2)."""
    gain = duck_curve(spans, frames, duck)
    if duck.swell > 0:
        released = 1.0 + duck_curve(spans, frames, duck.model_copy(update={"depth": 1.0}))
        gain = gain + duck.swell * released
    return gain


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
    scene_curve = _scene_curve(project, scenes, frames)
    speech = speech_spans(project, timings)
    clips = None
    placements = []
    for k, cue in enumerate(cues):
        first, last = cue_scene_range(cue, order)
        start = round(scenes[first]["start"] * RATE)
        end = total if last == len(order) - 1 else round((scenes[last]["start"] + scenes[last]["duration"]) * RATE)
        fitted = None
        if musicfit.is_fitted(cue) and fallback_bed(cue) is None:  # composed for this video's timings
            fitted = musicfit.fitted_music(project, timings, cue, first, last, start / RATE, end / RATE)
        source = Source(cue, project.root, cfg.soundfont, project.build_dir / "music", fitted.score if fitted else None)
        stop = end if source.ends_at is None else min(end, start + source.ends_at)
        fade_out = cue.fade_out
        if fitted is not None:  # the piece ends by itself: the fade never starts before its closing chord
            fade_out = min(fade_out, max(0.0, stop / RATE - start / RATE - fitted.closing_seconds))
        spans = speech
        if cue.duck.clips and cue.duck.depth > 0:
            clips = clip_spans(project, timings) if clips is None else clips
            spans = speech + clips
        gain = (
            10 ** (cue.volume / 20)
            * _fade_curve(times, start / RATE, stop / RATE, cue.fade_in, fade_out)
            * scene_curve
            * 10 ** (duck_gain_db(spans, frames, cue.duck) / 20)
        )
        placements.append(Placement(k, cue, start, stop, order[first : last + 1], source, gain, fitted.summary(start / RATE) if fitted else None))
    return placements


def plan_score(project: Project, timings: dict[str, Any], total: int) -> list[Placement]:
    """Place the scenes' themes and the beats' motifs (``score:``, DESIGN.md §112.2;
    :mod:`vidgen.scoring`) in the audio of ``total`` samples: each piece's source, its fades in
    ``score.curve``, its level, the scenes' levels, ``score.duck`` (with its swell) and, on the
    scene themes, the dips under motifs and stings."""
    from vidgen import scoring

    cfg = project.config
    if not scoring.uses_score(cfg):
        return []
    score = cfg.score
    duck = score.duck
    assert isinstance(duck, DuckConfig)
    scenes = timings["scenes"]
    order = [s["id"] for s in scenes]
    frames = total // FRAME + 2
    times = np.arange(frames) * FRAME / RATE
    scene_curve = _scene_curve(project, scenes, frames)
    spans = speech_spans(project, timings)
    if duck.clips and duck.depth > 0:
        spans = spans + clip_spans(project, timings)
    ducking = 10 ** (duck_gain_db(spans, frames, duck) / 20)
    pieces = scoring.theme_pieces(cfg, [(float(s["start"]), float(s["duration"])) for s in scenes], total / RATE)
    pieces += scoring.motif_pieces(project, timings)
    stings = scoring.sting_windows(project, timings) if score.sting_dip > 0 else []
    dips = 10 ** (scoring.dip_curve(times, pieces, stings, score.sting_dip, score.curve) / 20)
    sources: dict[scoring.ThemePlay, Any] = {}
    placements = []
    for piece in pieces:
        start, end = round(piece.start * RATE), min(round(piece.end * RATE), total)
        if end <= start:
            continue
        if piece.play not in sources:
            sources[piece.play] = scoring.theme_source(piece.play, project)
        fades = scoring.envelope(times, piece.start, end / RATE, piece.fade_in, piece.fade_out, score.curve)
        gain = 10 ** (piece.play.volume / 20) * fades * scene_curve * ducking * (1.0 if piece.motif else dips)
        cue = MusicCue(source=piece.play.source, volume=piece.play.volume, duck=duck, fade_in=piece.fade_in, fade_out=piece.fade_out)
        last = next((k for k in range(len(scenes) - 1, -1, -1) if scenes[k]["start"] < end / RATE), piece.scene)
        placements.append(Placement(-1, cue, start, end, order[piece.scene : last + 1] or [order[piece.scene]], sources[piece.play], gain,
                                    theme=piece.play.name, motif=piece.motif))
    return placements


def plan_ambience(project: Project, timings: dict[str, Any], total: int) -> list[AmbiencePlacement]:
    """Place the ambience beds (DESIGN.md §69.39, §69.55) in the video of ``total`` samples
    wherever a scene's timings name one (``ambience``, joined across scenes): the rain bed while it
    rains, the fire's crackle while a fireplace burns; each fades in from its span's start and out
    ending at its end (:data:`~vidgen.ambience.BEDS`: the rain over
    :data:`~vidgen.ambience.RAIN_FADE_IN` / ``RAIN_FADE_OUT``) and ducks under the narration (the
    rain by :data:`~vidgen.ambience.RAIN_DUCK`)."""
    frames = total // FRAME + 2
    times = np.arange(frames) * FRAME / RATE
    speech: list[tuple[float, float]] | None = None
    placements = []
    for name in AMBIENCE_BEDS:
        spans = ambience_spans(timings, name)
        if not spans:
            continue
        bed = BEDS[name]
        speech = speech_spans(project, timings) if speech is None else speech
        ducking = 10 ** (duck_curve(speech, frames, bed.duck) / 20)
        source = LoopSource(bed.loop())
        for a, b in spans:
            start, end = round(a * RATE), min(round(b * RATE), total)
            if end > start:
                gain = _fade_curve(times, a, b, bed.fade_in, bed.fade_out) * ducking
                placements.append(AmbiencePlacement(name, start, end, source, gain, bed.duck.depth))
    designed = designed_entries(timings)
    if designed:  # a scene's / beat's ambience (DESIGN.md §112): each piece with its own fades, level and width
        speech = speech_spans(project, timings) if speech is None else speech
        ducks: dict[str, np.ndarray] = {}
        for entry in designed:
            name = str(entry["bed"])
            bed = BEDS[name]
            if name not in ducks:
                ducks[name] = 10 ** (duck_curve(speech, frames, bed.duck) / 20)
            a, b = float(entry["start"]), float(entry["end"])
            start, end = round(a * RATE), min(round(b * RATE), total)
            if end > start:
                fades = _fade_curve(times, a, b, float(entry["fade_in"]), float(entry["fade_out"]))
                gain = 10 ** (float(entry.get("gain", 0.0)) / 20) * fades * ducks[name]
                width = entry.get("width")
                placements.append(AmbiencePlacement(name, start, end, LoopSource(bed.loop()), gain, bed.duck.depth, None if width is None else float(width)))
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
    ambience: list[dict[str, Any]] = field(default_factory=list)
    levelled_db: float | None = None  # the voice leveller's largest gain reduction (None: off)
    target_rms: float | None = None  # normalised to this RMS (dBFS) instead of target_lufs
    mono: bool = False  # the left and right mixed to one before the limiter
    music_check: dict[str, Any] | None = None  # the music under dense dialogue (score.check, DESIGN.md §112.2)
    parts: list[dict[str, Any]] = field(default_factory=list)  # the files of a split mix (audio_output.split, §112.3)

    def to_json(self) -> dict[str, Any]:
        """The report; ``ambience`` only when a bed played (DESIGN.md §69.39); ``levelled_db``,
        ``target_rms`` and ``mono`` only when set (DESIGN.md §111.2); ``music_check`` when
        measured (§112.2)."""

        def num(value: float | None) -> float | None:
            return None if value is None or not math.isfinite(value) else round(value, 2)

        data = {
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
        if self.ambience:
            data["ambience"] = self.ambience
        if self.levelled_db is not None:
            data["levelled_db"] = num(self.levelled_db)
        if self.target_rms is not None:
            data["target_rms"] = self.target_rms
        if self.mono:
            data["mono"] = True
        if self.music_check is not None:
            data["music_check"] = self.music_check
        if self.parts:
            data["parts"] = self.parts
        return data


#: How much louder (LU) a mix whose two channels are the same measures than one of them alone.
DUAL_MONO_LU = 10 * math.log10(2)


@dataclass(frozen=True)
class MixTargets:
    """What an audio-only render's loudness preset asks of the mix (DESIGN.md §111.2), in place
    of ``audio:``: the file's integrated loudness ``lufs`` (a mono file's, when ``mono``: the mix
    is the channels' average in both, so it measures :data:`DUAL_MONO_LU` more) or its RMS
    ``rms`` (dBFS), the limiter's ``true_peak``, the voice leveller, a ``room_tone`` (dBFS RMS)
    under everything, and whether the music is measured under the voices (``music_check``: the
    drama preset, §112.3, unless ``score.check: false``)."""

    lufs: float | None = None
    rms: float | None = None
    true_peak: float = -1.5
    mono: bool = False
    level_voice: bool = False
    room_tone: float | None = None
    music_check: bool = False


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
    path: Path, read: Callable[[int, int], np.ndarray], total: int, gain_db: float, true_peak: float, floor: np.ndarray | None = None
) -> tuple[loudness.LoudnessMeter, float]:
    """Write ``read(a, b)`` × ``gain_db`` (plus the loop ``floor``, a :func:`room_tone`, after
    the gain) through the limiter (``true_peak`` dBTP) to ``path`` (48 kHz stereo 24-bit), block
    by block; returns the output's meter and the lowest limiter gain."""
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
            ext = ext * gain
            if floor is not None:
                ext += floor[np.arange(lo - m, lo - m + len(ext)) % len(floor)][:, None]
            limited, low = limit(ext, ceiling)
            lowest = min(lowest, low)
            part = slice(m, m + hi - lo)
            meter.add(loudness.kweighted_power(limited)[part], loudness.peak_envelope(limited)[part])
            _write_block(out, limited[part])
    return meter, lowest


@dataclass(frozen=True)
class MixPart:
    """One file of a split mix (``audio_output.split``, DESIGN.md §112.3): samples ``start`` to
    ``end`` of the whole, faded in and out over ``fade_in`` / ``fade_out`` seconds at its edges
    (raised cosine), written to ``path`` normalised on its own."""

    path: Path
    start: int
    end: int
    fade_in: float = 0.0
    fade_out: float = 0.0

    def reader(self, read: Callable[[int, int], np.ndarray]) -> Callable[[int, int], np.ndarray]:
        """``read`` of the whole as this part's samples, its fades applied."""
        n = self.end - self.start
        fade_in, fade_out = round(self.fade_in * RATE), round(self.fade_out * RATE)

        def part(a: int, b: int) -> np.ndarray:
            x = read(self.start + a, self.start + b)
            if fade_in or fade_out:
                at = np.arange(a, b, dtype=np.float64)
                gain = np.ones(b - a)
                if fade_in:
                    gain *= 1.0 - _ramp(at / fade_in)
                if fade_out:
                    gain *= _ramp((at - (n - fade_out)) / fade_out)
                x = x * gain[:, None]
            return x

        return part


def _write_part(part: MixPart, read: Callable[[int, int], np.ndarray], gain_db: float, target: tuple[float | None, float | None] | None,
                true_peak: float, floor: np.ndarray | None) -> dict[str, Any]:
    """Write ``part`` of the mix ``read``: normalised to ``target`` (``(lufs, rms)``) on its own,
    else with the whole's ``gain_db``; returns its entry of :attr:`MixReport.parts`."""
    n = part.end - part.start
    sub = part.reader(read)
    gain = gain_db
    if target is not None:
        lufs, rms = target
        before = rms_db(n, sub) if rms is not None else loudness.measure(n, sub, peaks=False).integrated
        if math.isfinite(before):
            gain = (rms if rms is not None else lufs or 0.0) - before
    meter, lowest = write_mix(part.path, sub, n, gain, true_peak, floor)

    def num(value: float) -> float | None:
        return round(value, 2) if math.isfinite(value) else None

    return {
        "file": part.path.name, "start": round(part.start / RATE, 3), "end": round(part.end / RATE, 3), "gain_db": num(gain),
        "integrated_lufs": num(meter.integrated), "true_peak_dbtp": num(meter.true_peak), "limited_db": num(-20 * math.log10(lowest) if lowest > 0 else math.inf),
    }


def _has_narration_audio(project: Project) -> bool:
    """Whether some beat has its MP3, or the video has no narrated beats at all."""
    beats = [beat.id for _, beat in project.beats()]
    return not beats or any((project.audio_dir / f"{b}.mp3").is_file() for b in beats)


def mix_audio(
    project: Project,
    timings: dict[str, Any],
    voices: Sequence[Path],
    sfx_track: Path | None,
    out: Path,
    always_write: bool = False,
    targets: MixTargets | None = None,
    parts: Sequence[MixPart] = (),
) -> MixReport:
    """Mix the video's audio (``timings``: combined timings; ``voices``: the padded scene WAVs in
    order; ``sfx_track``: the SFX track or ``None``).

    With music or normalisation (``audio.normalize``: true, or ``auto`` with music) the mix is
    written to ``out`` and the report says ``mixed``; otherwise nothing is written (the final
    mux sums narration and effects as before) and the report only measures that sum, unless
    ``always_write`` (an audio-only render, DESIGN.md §111: the sum goes through the limiter into
    ``out``). A video whose narrated beats have no MP3 yet is not normalised. The voices go
    through the leveller with ``audio.level_voice: true``. ``targets`` (an audio-only render's
    loudness preset) replace ``audio:``'s normalisation, limit and leveller setting and always
    normalise. ``parts`` (``audio_output.split``, DESIGN.md §112.3): after the whole, each part
    is written to its own file, normalised on its own when the whole is (:attr:`MixReport.parts`).
    """
    audio = project.config.audio
    plain_voice = WavTrack(voices)
    total = plain_voice.length
    level = targets.level_voice if targets is not None else audio.level_voice is True
    voice: WavTrack | LevelledTrack = LevelledTrack(plain_voice) if level else plain_voice
    mono = targets is not None and targets.mono
    sfx = WavTrack([sfx_track]) if sfx_track is not None else None
    placements = plan_music(project, timings, total) + plan_score(project, timings, total)
    beds = plan_ambience(project, timings, total)
    music = MusicTrack([*placements, *beds], (audio.music_width, audio.ambience_width)) if placements or beds else None

    def read(a: int, b: int) -> np.ndarray:
        x = voice.read(a, b)
        if sfx is not None:
            x += sfx.read(a, b)
        if music is not None:
            x += music.read(a, b)
        if mono:
            x[:] = x.mean(axis=1, keepdims=True)
        return x

    normalize = targets is not None or audio.normalize is True or (audio.normalize == "auto" and bool(placements))
    if normalize and not _has_narration_audio(project):
        # Normalising a video whose narration is not voiced yet would lift the music and the
        # effects to the target on their own (a preview timed from word counts).
        log.info("no narration audio yet (vidgen tts): the mix is not normalised")
        normalize = False
    summaries = [p.summary() for p in placements]
    ambience = [b.summary() for b in beds]
    levelled = voice.reduction_db if isinstance(voice, LevelledTrack) else None
    out.unlink(missing_ok=True)
    if not normalize and music is None and not always_write:
        meter = loudness.measure(total, read)
        return MixReport(False, False, None, None, 0.0, meter.integrated, meter.true_peak, 0.0, summaries, ambience, levelled)
    true_peak = audio.true_peak if targets is None else targets.true_peak
    target_lufs: float | None = audio.target_lufs
    target_rms = None
    if targets is not None:
        target_rms = targets.rms
        target_lufs = None if targets.lufs is None else targets.lufs + (DUAL_MONO_LU if mono else 0.0)
    gain_db = 0.0
    if normalize:
        before = rms_db(total, read) if target_rms is not None else loudness.measure(total, read, peaks=False).integrated
        if math.isfinite(before):
            gain_db = (target_rms if target_rms is not None else target_lufs or 0.0) - before
        else:
            log.warning("the audio is silent; it is not normalised")
    floor = room_tone(targets.room_tone) if targets is not None and targets.room_tone is not None else None
    meter, lowest = write_mix(out, read, total, gain_db, true_peak, floor)
    target = (target_lufs, target_rms) if normalize else None
    written = [_write_part(part, read, gain_db, target, true_peak, floor) for part in parts]
    forced = targets is not None and targets.music_check
    checked = _check_music(project, timings, voice, placements, total, forced) if placements else None
    return MixReport(
        True,
        normalize,
        target_lufs if normalize and target_rms is None else None,
        true_peak,
        gain_db,
        meter.integrated,
        meter.true_peak,
        -20 * math.log10(lowest) if lowest > 0 else math.inf,
        summaries,
        ambience,
        levelled,
        target_rms if normalize else None,
        mono,
        checked,
        written,
    )


def _check_music(project: Project, timings: dict[str, Any], voice: WavTrack | LevelledTrack, placements: Sequence[Placement],
                 total: int, forced: bool = False) -> dict[str, Any] | None:
    """``score.check`` (DESIGN.md §112.2): the music (no ambience) measured under the voices
    (:func:`vidgen.scoring.dense_dialogue_check`), a warning where it fights dense dialogue;
    ``forced`` (the drama preset, §112.3) measures any music unless ``score.check: false``."""
    from vidgen import scoring

    cfg = project.config
    if not (scoring.check_wanted(cfg) or (forced and cfg.score.check is not False)):
        return None
    music = MusicTrack(placements, (cfg.audio.music_width, cfg.audio.ambience_width))
    report = scoring.dense_dialogue_check(total, voice.read, music.read, speech_spans(project, timings), cfg.score.dense_lu)
    if not report["ok"]:
        worst = [r for r in report["dense"] if r["lu"] is not None and r["lu"] < cfg.score.dense_lu]
        where = ", ".join(f"{r['start']:.1f}-{r['end']:.1f} s ({r['lu']:.1f} LU)" for r in worst[:3])
        log.warning("music: in dense dialogue the music is less than %g LU under the voices at %s: duck it deeper (score.duck: deep) "
                    "or lower it there (music: {volume: -6})", cfg.score.dense_lu, where)
    return report
