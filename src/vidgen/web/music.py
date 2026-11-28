"""Built-in music data for ``web`` scenes: ``music_data: true`` gives the page
``ctx.music``, made from the video's own music without a script of the author's.

- **Analysis**, one value per video frame of the whole video, of the music the video plays (every
  ``music:`` cue and scene theme with its ``start``, ``loop``, ``volume``, fades, scene levels and
  ducking, as the join mixes it; no narration, effects or ambience): ``bands`` spectrum bands
  (log-spaced from 40 Hz to 12 kHz), the overall level, the level under 150 Hz and the onset
  strength, each normalised to 0..1 and smoothed with a fast attack and a slow release (the
  measure the music films "Parallel Space" and "Escapement" once made with a script of their own).
- **Score events** of the score the scene's music cue plays (a project piece or a score bed):
  every track's drum hits and notes (:func:`vidgen.studio.events.score_events`), in song time.

Made once per video and frame rate and kept in ``build/music/music-data-<key>.json``; the key
(:func:`music_data_key`) is cheap (no synthesis) and is in the scene's render fingerprint. The
music itself comes from the music cache (a project piece's render in ``build/music``), rendered
and stored there only when missing, as the join would.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic

log = logging.getLogger("vidgen.web")

#: Version of the analysis and of the data's layout (bumped when either changes).
MUSIC_DATA_VERSION = 1
#: The analysis window (samples at 48 kHz; Hann) and the bands' range, as the films used them.
WINDOW = 4096
BAND_LOW_HZ, BAND_HIGH_HZ = 40.0, 12000.0
#: The bins summed for the level and for the low end (Hz, lower edge included).
LEVEL_HZ, LOW_HZ = (25.0, 14000.0), (25.0, 150.0)
#: The level is 0 this many dB under its loudest frames (the 99.5th percentile), the low end too.
LEVEL_RANGE_DB, LOW_RANGE_DB = 36.0, 30.0
#: A band is 0 at its 20th percentile and 1 at its 99.5th; the onset 1 at its 99.7th.
BAND_PERCENTILES, TOP_PERCENTILE, ONSET_PERCENTILE = (20.0, 99.5), 99.5, 99.7
#: A frame whose level is under this (dB of the window's power; digital silence is -120) is
#: silence: it sets no percentile (all silence: every series 0).
SILENT_DB = -100.0
#: The release of each series: a value falls to this share of itself per frame at most.
RELEASE: dict[str, float] = {"bands": 0.82, "level": 0.9, "low": 0.8, "onset": 0.7}
#: The series the page is given, in this order.
SERIES = ("bands", "level", "low", "onset")
DEFAULT_BANDS, MAX_BANDS = 16, 64
#: Extra frames analysed after the video's planned end (a scene may run a frame or two longer).
SPARE_FRAMES = 2
#: Seconds of analysis a page gets before its scene's start and after its end (the whole video's
#: is made once; each page is sent its own part, the score's events whole).
PAGE_MARGIN_SECONDS = 5.0
#: Where the data is kept (under the project's build folder) and the helper the page gets.
CACHE_FOLDER = "music"
HELPER_FILE = Path(__file__).resolve().parent.parent / "data" / "web" / "music.js"


class MusicDataSettings(BaseModel):
    """``music_data:`` of a ``web`` scene in its long form."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    bands: int = Field(default=DEFAULT_BANDS, ge=1, le=MAX_BANDS)
    """Spectrum bands, log-spaced from 40 Hz to 12 kHz (1 to 64)."""
    tracks: list[str] | None = None
    """Only these score tracks' hits and notes (default: every track)."""
    t0: float | None = None
    """Song time (seconds into the music) at the scene's start, instead of the one vidgen works out."""

    @field_validator("t0")
    @classmethod
    def _finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("t0 must be a finite number of seconds")
        return value


def music_settings(value: Any) -> MusicDataSettings | None:
    """The settings of a scene's ``music_data:`` (a model, a mapping, ``True``), ``None`` when off."""
    if value is None or value is False:
        return None
    if value is True:
        return MusicDataSettings()
    if isinstance(value, MusicDataSettings):
        return value
    return MusicDataSettings.model_validate(value)


def scene_music_settings(params: Any) -> MusicDataSettings | None:
    """The ``music_data:`` of a ``web`` scene's params (a model or a mapping)."""
    value = params.get("music_data") if isinstance(params, Mapping) else getattr(params, "music_data", None)
    return music_settings(value)


# ----- the analysis --------------------------------------------------------------------------------


def band_edges(bands: int) -> np.ndarray:
    """The ``bands + 1`` edges (Hz) of log-spaced bands from :data:`BAND_LOW_HZ` to :data:`BAND_HIGH_HZ`."""
    return np.geomspace(BAND_LOW_HZ, BAND_HIGH_HZ, bands + 1)


def _bins(freqs: np.ndarray, lo: float, hi: float) -> tuple[int, int]:
    """The FFT bins ``[a, b)`` with ``lo <= f < hi``; a band narrower than one bin takes the bin
    nearest its geometric centre."""
    a, b = int(np.searchsorted(freqs, lo, "left")), int(np.searchsorted(freqs, hi, "left"))
    if b > a:
        return a, b
    k = int(np.argmin(np.abs(freqs - math.sqrt(lo * hi))))
    return k, k + 1


def released(x: np.ndarray, keep: float) -> np.ndarray:
    """Fast attack, slow release along axis 0: each value is at least ``keep`` of the one before
    (mixed with itself: ``max(x, before * keep + x * (1 - keep))``)."""
    out = np.array(x, dtype=float)
    for i in range(1, len(out)):
        out[i] = np.maximum(out[i], out[i - 1] * keep + out[i] * (1 - keep))
    return out


def analyse(mono: np.ndarray, rate: int, fps: float, frames: int, bands: int = DEFAULT_BANDS,
            playing: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """The per-frame series of ``mono`` (float samples at ``rate``): frame ``f`` is a
    :data:`WINDOW`-sample Hann window centred on sample ``round(f * rate / fps)``. ``bands``
    (frames x bands): mean power per band in dB, 0 at its 20th percentile and 1 at its 99.5th;
    ``level`` / ``low``: total power 25 Hz-14 kHz / 25-150 Hz in dB, 0 at 36 / 30 dB under the
    99.5th percentile; ``onset``: the mean rise of the log spectrum since the frame before, 1 at
    its 99.7th percentile; then each released (:data:`RELEASE`). The percentiles are taken over
    the frames where ``playing`` is true (default all) and that are not silent
    (:data:`SILENT_DB`); none: everything 0."""
    x = np.asarray(mono, dtype=np.float64)
    freqs = np.fft.rfftfreq(WINDOW, 1 / rate)
    edges = band_edges(bands)
    spans = [_bins(freqs, edges[i], edges[i + 1]) for i in range(bands)]
    lv0, lv1 = _bins(freqs, *LEVEL_HZ)
    lo0, lo1 = _bins(freqs, *LOW_HZ)
    window = np.hanning(WINDOW)
    half = WINDOW // 2
    centres = np.round(np.arange(frames) * rate / fps).astype(np.int64)
    padded = np.concatenate([np.zeros(half), x, np.zeros(WINDOW + int(rate / fps) + 1)])
    need = int(centres[-1]) + WINDOW + 1 if frames else 0
    if len(padded) < need:
        padded = np.concatenate([padded, np.zeros(need - len(padded))])
    power = np.zeros((frames, bands))
    level, low, onset = np.zeros(frames), np.zeros(frames), np.zeros(frames)
    before: np.ndarray | None = None
    offsets = np.arange(WINDOW)
    for a in range(0, frames, 256):
        idx = centres[a:a + 256, None] + offsets[None, :]
        spectrum = np.abs(np.fft.rfft(padded[idx] * window, axis=1)) ** 2
        for b, (s0, s1) in enumerate(spans):
            power[a:a + 256, b] = 10 * np.log10(spectrum[:, s0:s1].mean(axis=1) + 1e-12)
        level[a:a + 256] = 10 * np.log10(spectrum[:, lv0:lv1].sum(axis=1) + 1e-12)
        low[a:a + 256] = 10 * np.log10(spectrum[:, lo0:lo1].sum(axis=1) + 1e-12)
        logs = np.log10(spectrum[:, lv0:lv1] + 1e-9)
        rise = np.maximum(np.diff(logs, axis=0, prepend=logs[:1] if before is None else before[None, :]), 0).mean(axis=1)
        if before is None:
            rise[0] = 0.0
        onset[a:a + 256] = rise
        before = logs[-1]
    mask = np.ones(frames, dtype=bool) if playing is None else np.asarray(playing, dtype=bool)[:frames]
    mask &= level > SILENT_DB
    if not mask.any():
        return {"bands": np.zeros((frames, bands)), "level": np.zeros(frames), "low": np.zeros(frames), "onset": np.zeros(frames)}
    lo_p, hi_p = np.percentile(power[mask], BAND_PERCENTILES, axis=0)
    out_bands = np.clip((power - lo_p) / (hi_p - lo_p + 1e-9), 0, 1)
    top = np.percentile(level[mask], TOP_PERCENTILE)
    out_level = np.clip((level - (top - LEVEL_RANGE_DB)) / LEVEL_RANGE_DB, 0, 1)
    top = np.percentile(low[mask], TOP_PERCENTILE)
    out_low = np.clip((low - (top - LOW_RANGE_DB)) / LOW_RANGE_DB, 0, 1)
    out_onset = np.clip(onset / (np.percentile(onset[mask], ONSET_PERCENTILE) + 1e-9), 0, 1)
    series = {"bands": out_bands, "level": out_level, "low": out_low, "onset": out_onset}
    return {name: released(values, RELEASE[name]) for name, values in series.items()}


def pcm16(samples: np.ndarray) -> np.ndarray:
    """Float samples as a 16-bit WAV file holds them (:func:`vidgen.sfx.wav_bytes`' rounding,
    read back over 32768): the analysis hears the music as the films' WAV files gave it, with
    the same floor of rounding noise under which a quiet part counts as silence."""
    return np.clip(np.round(np.asarray(samples, dtype=np.float64) * 32767), -32768, 32767) / 32768


def quantised(values: np.ndarray) -> str:
    """Values from 0 to 1 as one byte each (0..255), base64."""
    q = np.clip(np.round(np.asarray(values, dtype=float) * 255), 0, 255).astype(np.uint8)
    return base64.b64encode(q.tobytes()).decode("ascii")


def _packed(values: Sequence[float] | np.ndarray, dtype: str) -> str:
    return base64.b64encode(np.asarray(values, dtype=dtype).tobytes()).decode("ascii")


# ----- the video's music ---------------------------------------------------------------------------


def planned_timings(project: Any, fps: int) -> dict[str, Any]:
    """The video's timings as planned before anything is rendered (:class:`vidgen.videoplan.VideoPlan`),
    in the shape the join's mix reads: scenes with ``id``, ``type``, ``start``, ``duration`` and
    ``beats`` (``id``, ``text``, ``start``, ``end``; video seconds), and ``duration``."""
    from vidgen.videoplan import VideoPlan

    plan = VideoPlan(project, fps)
    scenes = [
        {"id": s.id, "type": s.type, "start": s.start, "duration": s.duration,
         "beats": [{"id": b.id, "text": b.text, "start": s.start + b.start, "end": s.start + b.end} for b in s.beats]}
        for s in plan.scenes
    ]
    return {"scenes": scenes, "duration": plan.duration}


def has_music(config: Any) -> bool:
    """Whether the video plays music: a ``music:`` cue or a scene theme or beat motif."""
    from vidgen import scoring

    return bool(config.music_cues) or scoring.uses_score(config)


def _ducks(config: Any) -> bool:
    from vidgen import scoring

    depths = [cue.duck.depth for cue in config.music_cues]
    if scoring.uses_score(config):
        depths.append(getattr(config.score.duck, "depth", 0.0))
    return any(d > 0 for d in depths)


def _file_digest(path: Path) -> Any:
    """A score file's SHA-256 (they are small and often edited), another file's size and time."""
    if not path.is_file():
        return None
    if path.suffix.lower() in (".yaml", ".yml"):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]


def music_inputs(project: Any, fps: int) -> dict[str, Any]:
    """What the video's music data is made from, without making it: the version, vidgen's
    version (a piece's render depends on it), the frame rate, the music settings (``music:``,
    ``score:``, ``soundfont``, every scene's ``music:`` and beats' motifs), the music files (score
    files by contents, others by size and time), the planned timeline and, when the music ducks,
    the narration files' sizes and times."""
    from vidgen import __version__
    from vidgen.music import PROJECT_MUSIC_DIR

    cfg = project.config
    root = project.root
    files: dict[str, Any] = {}
    folder = root / PROJECT_MUSIC_DIR
    if folder.is_dir():
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                files[path.relative_to(root).as_posix()] = _file_digest(path)
    for cue in cfg.music_cues:
        if cue.source is not None and (root / cue.source).is_file():
            files.setdefault(Path(cue.source).as_posix(), _file_digest(root / cue.source))
    timings = planned_timings(project, fps)
    data: dict[str, Any] = {
        "version": MUSIC_DATA_VERSION, "vidgen": __version__, "fps": fps,
        "music": [cue.model_dump(mode="json") for cue in cfg.music_cues],
        "score": cfg.score.model_dump(mode="json") if cfg.score is not None else None,
        "soundfont": cfg.soundfont,
        "scenes": [[s.id, s.music if isinstance(s.music, bool) else s.music.model_dump(mode="json"), [b.motif for b in s.beats]]
                   for s in cfg.scenes],
        "files": files,
        "timeline": [[s["id"], round(s["start"], 6), round(s["duration"], 6), [[round(b["start"], 6), round(b["end"], 6)] for b in s["beats"]]]
                     for s in timings["scenes"]],
    }
    if _ducks(cfg):
        data["speech"] = {b.id: _file_digest(project.audio_dir / f"{b.id}.mp3") for _, b in project.beats()}
    return data


def music_data_key(project: Any, fps: int, bands: int = DEFAULT_BANDS) -> str:
    """The cache key (SHA-256 hex) of the video's music data at ``fps`` with ``bands`` bands."""
    inputs = {**music_inputs(project, fps), "bands": bands}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _cue_entry(project: Any, placement: Any) -> dict[str, Any]:
    """A placed cue as the data names it: where it plays (video seconds), the song time at its
    start (seconds into its source), whether it loops and the score file it plays (if any)."""
    from vidgen.music import RATE, source_kind
    from vidgen.music_pieces import cue_score, section_start

    cue = placement.cue
    root = project.root
    kind = placement.source.kind
    offset = float(cue.start)
    length: float | None = None
    score_rel: str | None = None
    if placement.index >= 0 and cue.source is not None and source_kind(cue, root) in ("score", "bed"):
        path = cue_score(cue, root)
        if path is not None:
            from vidgen.studio import load_music_score

            score = load_music_score(path)
            offset += section_start(cue, root)
            length = score.seconds
            if score.loop:
                offset %= length
            score_rel = path.resolve().relative_to(root.resolve()).as_posix() if path.resolve().is_relative_to(root.resolve()) else str(path)
    return {"start": placement.start / RATE, "end": placement.end / RATE, "offset": offset, "kind": kind, "label": placement.source.label,
            "loop": bool(placement.source.loop), "length": length, "score": score_rel, "theme": placement.theme}


def _track_columns(events: Sequence[Any], kind: str) -> dict[str, Any]:
    """One track's events as columns (base64 typed arrays; default columns left out): ``t`` /
    ``d`` start and length in 48 kHz samples (uint32: exact, and a third of the text of decimal
    seconds), ``p`` the first pitch (uint8), ``c`` the other pitches of chords, ``v`` / ``e`` dynamic in dB at start
    and end, ``g`` the step's gain, ``i`` the instrument, ``s`` the stroke, ``l`` slurred."""
    from vidgen.sfx import RATE

    instruments = list(dict.fromkeys(e.instrument for e in events))
    strokes = list(dict.fromkeys(e.stroke for e in events if e.stroke is not None))
    out: dict[str, Any] = {"kind": kind, "instruments": instruments, "count": len(events),
                           "t": _packed([round(e.time * RATE) for e in events], "<u4"),
                           "d": _packed([round(e.duration * RATE) for e in events], "<u4")}
    if any(e.pitches for e in events):
        out["p"] = _packed([e.pitches[0] if e.pitches else 255 for e in events], "u1")
        chords = {str(k): list(e.pitches[1:]) for k, e in enumerate(events) if len(e.pitches) > 1}
        if chords:
            out["c"] = chords
    if any(e.dynamic for e in events):
        out["v"] = _packed([e.dynamic for e in events], "<f4")
    if any(e.dynamic_end != e.dynamic for e in events):
        out["e"] = _packed([e.dynamic_end for e in events], "<f4")
    if any(e.gain != 1.0 for e in events):
        out["g"] = _packed([e.gain for e in events], "<f4")
    if len(instruments) > 1:
        out["i"] = _packed([instruments.index(e.instrument) for e in events], "u1")
    if strokes:
        out["strokes"] = strokes
        out["s"] = _packed([strokes.index(e.stroke) if e.stroke is not None else 255 for e in events], "u1")
    if any(e.slur for e in events):
        out["l"] = _packed([int(e.slur) for e in events], "u1")
    return out


def _score_tracks(path: Path, first: float, last: float, loop_length: float | None, wanted: Sequence[str] | None) -> dict[str, Any]:
    """The score's facts and its tracks' events with song times from ``first`` to ``last``
    (seconds; a loop's events repeated for every pass in that span)."""
    from vidgen.studio import load_music_score
    from vidgen.studio.events import ScoreEvent, score_events, score_facts, track_kind

    score = load_music_score(path)
    events = score_events(score)
    if wanted is not None:
        unknown = [name for name in wanted if name not in events]
        if unknown:
            import difflib

            hints = [f"'{n}'" + (f" (did you mean '{c[0]}'?)" if (c := difflib.get_close_matches(n, list(events), n=1)) else "") for n in unknown]
            raise VidgenError(f"music_data.tracks: {path.name} has no track {', '.join(hints)}; its tracks: {', '.join(events)}")
        events = {name: events[name] for name in wanted}
    kinds = {t.name: track_kind(t) for t in score.tracks}
    tracks: dict[str, Any] = {}
    for name, found in events.items():
        if score.loop and loop_length:
            passes = range(math.floor(first / loop_length) - 1, math.ceil(last / loop_length) + 1)
            spread = [ScoreEvent(**{**e.__dict__, "time": e.time + k * loop_length}) for k in passes for e in found]
            found = [e for e in sorted(spread, key=lambda e: e.time) if max(0.0, first - loop_length) <= e.time <= last]
        tracks[name] = _track_columns(found, kinds[name])
    return {**score_facts(score), "file": path.name, "tracks": tracks}


def video_music_data(project: Any, fps: int, bands: int = DEFAULT_BANDS) -> dict[str, Any]:
    """The video's music data at ``fps`` (cached in ``build/music/music-data-<key>.json``):
    ``frames``, ``bands``, ``edges`` (Hz), ``series`` (base64 bytes, 0..255 for 0..1: ``bands``
    frame by frame, ``level``, ``low``, ``onset``) and ``cues`` (each placed cue: ``start`` /
    ``end`` video seconds, ``offset`` the song time at its start, ``kind``, ``label``, ``loop``,
    ``length``, ``score``). :class:`VidgenError` when the video has no music."""
    if not has_music(project.config):
        raise VidgenError("music_data: the video plays no music; add music: (a score file, a bed or a music file) or turn music_data off")
    key = music_data_key(project, fps, bands)
    cached = project.build_dir / CACHE_FOLDER / f"music-data-{key}.json"
    if cached.is_file():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass  # damaged: made again
    data = _make_music_data(project, fps, bands)
    write_text_atomic(cached, json.dumps(data, separators=(",", ":")) + "\n")
    return data


def _make_music_data(project: Any, fps: int, bands: int) -> dict[str, Any]:
    from vidgen.mix import MusicTrack, plan_music, plan_score
    from vidgen.music import RATE

    log.info("music data: analysing the video's music at %d fps (%d bands)", fps, bands)
    timings = planned_timings(project, fps)
    total = round(timings["duration"] * RATE)
    placements = plan_music(project, timings, total) + plan_score(project, timings, total)
    frames = round(timings["duration"] * fps) + SPARE_FRAMES
    mono = pcm16(MusicTrack(placements).read(0, total)).mean(axis=1)
    frame_times = np.arange(frames) / fps
    playing = np.zeros(frames, dtype=bool)
    for p in placements:
        playing |= (frame_times >= p.start / RATE) & (frame_times < p.end / RATE)
    series = analyse(mono, RATE, fps, frames, bands, playing)
    return {
        "version": MUSIC_DATA_VERSION, "fps": fps, "frames": frames, "bands": bands,
        "edges": [round(float(e), 3) for e in band_edges(bands)],
        "series": {name: quantised(series[name]) for name in SERIES},
        "cues": [_cue_entry(project, p) for p in placements],
    }


def scene_music(project: Any, scene_id: str, fps: int, settings: MusicDataSettings) -> dict[str, Any]:
    """``ctx.music`` of scene ``scene_id`` as the page is given it (the helper ``music.js``
    turns it into functions): the video's series (:func:`video_music_data`), ``first`` (the
    video frame of the scene's frame 0), ``start`` (its video second), ``from`` / ``to`` (the
    video frames of the series sent: the scene and :data:`PAGE_MARGIN_SECONDS` on each side),
    ``t0`` (the song time
    there: ``settings.t0``, else the song time of the music cue playing at the scene's start,
    else the video time), ``source`` (that cue: ``kind``, ``label``, ``loop``; ``None`` when no
    cue plays) and ``score`` (the cue's score with its tracks' events in song time, ``None``
    for audio)."""
    from vidgen.videoplan import VideoPlan

    video = video_music_data(project, fps, settings.bands)
    slot = VideoPlan(project, fps).scene(scene_id)
    start = slot.start
    cues = [c for c in video["cues"] if c["theme"] is None] or video["cues"]
    cue = next((c for c in cues if c["start"] - 1e-9 <= start < c["end"]), None)
    t0 = settings.t0 if settings.t0 is not None else (cue["offset"] + start - cue["start"] if cue is not None else start)
    score = None
    if cue is not None and cue["score"] is not None:
        path = Path(cue["score"]) if Path(cue["score"]).is_absolute() else project.root / cue["score"]
        first, last = cue["offset"], cue["offset"] + cue["end"] - cue["start"]
        score = _score_tracks(path, first, last, cue["length"] if cue["loop"] else None, settings.tracks)
    elif settings.tracks:
        raise VidgenError(f"music_data.tracks: scene '{scene_id}' starts where no score file plays (its music is "
                          f"{cue['label'] if cue else 'none'}): only a score file has tracks")
    source = None if cue is None else {k: cue[k] for k in ("kind", "label", "loop")}
    first = round(start * fps)
    margin = round(PAGE_MARGIN_SECONDS * fps)
    a = max(0, first - margin)
    b = min(video["frames"], first + round(slot.duration * fps) + margin)
    series = {name: _cut_series(video["series"][name], a, b, video["bands"] if name == "bands" else 1) for name in SERIES}
    return {"version": video["version"], "fps": fps, "frames": video["frames"], "first": first, "start": round(start, 6),
            "t0": round(t0, 6), "bands": video["bands"], "edges": video["edges"], "from": a, "to": b, "series": series,
            "source": source, "score": score}


def _cut_series(b64: str, a: int, b: int, stride: int) -> str:
    """Frames ``a`` to ``b`` of a base64 series of ``stride`` bytes per frame."""
    return base64.b64encode(base64.b64decode(b64)[a * stride:b * stride]).decode("ascii")


def payload_digest(music: Mapping[str, Any]) -> str:
    """The SHA-256 of a scene's music data (for its clip's key)."""
    return hashlib.sha256(json.dumps(music, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def helper_source() -> str:
    """The page's music helper (``data/web/music.js``)."""
    return HELPER_FILE.read_text(encoding="utf-8")


def helper_digest() -> str:
    return hashlib.sha256(HELPER_FILE.read_bytes()).hexdigest()


def prepare_music_data(project: Any, preview: bool, scene_ids: Sequence[str]) -> None:
    """Make the music data of the ``web`` scenes among ``scene_ids`` that use it, before their
    workers start (so two workers never render the music at once); nothing for other scenes."""
    from vidgen.web.entry import is_web_type

    fps = project.render_format(preview).fps
    wanted = {settings.bands for sid in scene_ids if is_web_type(project.scene(sid).type)
              and (settings := _settings_or_none(project.scene(sid).params)) is not None}
    for bands in sorted(wanted):
        video_music_data(project, fps, bands)


def _settings_or_none(params: Any) -> MusicDataSettings | None:
    try:
        return scene_music_settings(params)
    except ValueError:
        return None   # the scene's own check reports it


__all__ = ["DEFAULT_BANDS", "MAX_BANDS", "MUSIC_DATA_VERSION", "MusicDataSettings", "analyse", "band_edges", "has_music",
           "helper_digest", "helper_source", "music_data_key", "music_inputs", "music_settings", "payload_digest", "planned_timings",
           "prepare_music_data", "quantised", "released", "scene_music", "scene_music_settings", "video_music_data"]
