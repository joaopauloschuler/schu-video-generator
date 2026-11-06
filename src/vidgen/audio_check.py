"""Loudness presets of audio files and the check that measures a file against them (DESIGN.md
§111.2): ``vidgen audio check`` and the end of an audio-only render with
``audio_output.loudness``.

:func:`measure_file` decodes the file once with the ``ffmpeg`` executable: its ``ebur128``
filter gives the integrated loudness, loudness range, true peak and sample peak (BS.1770, the
measure podcast hosts and broadcasters use), and the decoded samples (48 kHz, the file's
channels) give the RMS over the whole file, the noise floor (the quietest 0.5 s), and the
silence before the first and after the last sound (room tone head and tail; a sound is a 10 ms
frame above :data:`SOUND_DB`); for a stereo file also the channels' correlation and how much the
mono fold loses (:func:`mono_check`, DESIGN.md §111.4). Nothing is held in memory but a few
values per 10 ms.

:data:`PRESETS` are the targets: ``podcast`` (-16 LUFS stereo, -19 mono, ±1 LU; true peak at
most -1 dBTP), ``audiobook`` (ACX: RMS -23 to -18 dB, sample peaks at most -3 dB, noise floor at
most -60 dB, 0.5-1 s of room tone at the head and 1-5 s at the tail; the file format and the
length per file only as notes), ``broadcast`` (EBU R128: -23 LUFS ±0.5 LU, -1 dBTP) and
``custom`` (``audio.target_lufs`` ±1 LU, ``audio.true_peak``). :func:`mix_targets` turns a
project's preset into what its mix aims for, a little inside the limits (lossy encoders move
the peaks).
"""

from __future__ import annotations

import difflib
import math
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from vidgen.config import AudioConfig, AudioOutputConfig
from vidgen.errors import VidgenError
from vidgen.mix import MixTargets

if TYPE_CHECKING:
    from vidgen.project import Project

#: A 10 ms frame above this RMS (dBFS) counts as sound (head and tail measures).
SOUND_DB = -50.0
#: The noise floor is the RMS of the quietest window of this many seconds.
FLOOR_SECONDS = 0.5
#: Rate the samples are decoded at for the RMS, floor, head and tail.
RATE = 48000
FRAME = RATE // 100
#: Decoder names shown as the format's name.
CODEC_NAMES = {"mp3float": "mp3", "libopus": "opus", "libvorbis": "vorbis"}


@dataclass(frozen=True)
class LoudnessPreset:
    """A loudness preset: the targets a file is checked against and what the mix aims for."""

    name: str
    description: str
    lufs: float | None = None  # integrated loudness of a stereo file
    mono_lufs: float | None = None  # ... of a mono file
    tolerance: float = 1.0  # LU either side
    max_true_peak: float | None = None  # dBTP
    rms: tuple[float, float] | None = None  # whole-file RMS range (dBFS)
    rms_target: float | None = None  # what the mix aims for
    max_sample_peak: float | None = None  # dBFS
    noise_floor: float | None = None  # dBFS RMS at most
    head: tuple[float, float] | None = None  # seconds of room tone before the first sound
    tail: tuple[float, float] | None = None  # ... after the last
    mix_true_peak: float = -1.5  # the limiter's setting
    level_voice: bool = False  # the voice leveller's default
    acx_notes: bool = False  # notes on ACX's file format and length


PRESETS: dict[str, LoudnessPreset] = {
    "podcast": LoudnessPreset(
        "podcast", "-16 LUFS stereo / -19 mono (±1 LU), true peak ≤ -1 dBTP",
        lufs=-16.0, mono_lufs=-19.0, tolerance=1.0, max_true_peak=-1.0, mix_true_peak=-1.5, level_voice=True,
    ),
    "audiobook": LoudnessPreset(
        "audiobook", "ACX: RMS -23 to -18 dB, peaks ≤ -3 dB, noise floor ≤ -60 dB, room tone 0.5-1 s head / 1-5 s tail",
        rms=(-23.0, -18.0), rms_target=-20.0, max_sample_peak=-3.0, noise_floor=-60.0, head=(0.5, 1.0), tail=(1.0, 5.0),
        mix_true_peak=-3.5, level_voice=True, acx_notes=True,
    ),
    "broadcast": LoudnessPreset(
        "broadcast", "EBU R128: -23 LUFS (±0.5 LU), true peak ≤ -1 dBTP",
        lufs=-23.0, mono_lufs=-23.0, tolerance=0.5, max_true_peak=-1.0, mix_true_peak=-1.5,
    ),
}
#: Pacing an audiobook gets where ``pacing:`` does not say (seconds; the speech's own lead-in
#: silence comes on top of ``lead_in``): inside ACX's room tone head and tail.
AUDIOBOOK_PACING = {"lead_in": 0.6, "tail": 2.5}
#: ACX's limits on a file, given as notes: MP3 at 192 kb/s or more, 44.1 kHz, at most 120 min.
ACX_BITRATE = 192_000
ACX_RATE = 44100
ACX_MINUTES = 120


def custom_preset(audio: AudioConfig) -> LoudnessPreset:
    """The ``custom`` preset of ``audio:``: ``target_lufs`` ±1 LU, ``true_peak``."""
    return LoudnessPreset(
        "custom", f"{audio.target_lufs:g} LUFS (±1 LU), true peak ≤ {audio.true_peak:g} dBTP",
        lufs=audio.target_lufs, mono_lufs=audio.target_lufs, max_true_peak=audio.true_peak, mix_true_peak=audio.true_peak,
    )


def preset_named(name: str, audio: AudioConfig | None = None) -> LoudnessPreset:
    """The preset ``name`` (``custom`` from ``audio``); :class:`VidgenError` with a did-you-mean."""
    if name == "custom":
        return custom_preset(audio or AudioConfig())
    if name not in PRESETS:
        names = [*PRESETS, "custom"]
        close = difflib.get_close_matches(name, names, n=1)
        hint = f"; did you mean '{close[0]}'?" if close else ""
        raise VidgenError(f"unknown loudness preset '{name}'{hint} (presets: {', '.join(names)})")
    return PRESETS[name]


def project_preset(project: Project) -> LoudnessPreset | None:
    """The preset of ``project``'s ``audio_output.loudness`` (``None`` for ``none``)."""
    name = project.config.audio_output.loudness
    return None if name == "none" else preset_named(name, project.config.audio)


def mix_targets(project: Project) -> MixTargets | None:
    """What ``project``'s mix aims for under its loudness preset (``None`` without one): the
    preset's loudness for the file's channels (or its RMS), the limiter a little under its peak
    limit, the leveller (``audio.level_voice`` or the preset's default), the room tone."""
    preset = project_preset(project)
    if preset is None:
        return None
    out: AudioOutputConfig = project.config.audio_output
    mono = out.channels == "mono"
    level = project.config.audio.level_voice
    return MixTargets(
        lufs=None if preset.rms_target is not None else (preset.mono_lufs if mono else preset.lufs),
        rms=preset.rms_target,
        true_peak=preset.mix_true_peak,
        mono=mono,
        level_voice=preset.level_voice if level is None else level,
        room_tone=out.room_tone,
    )


# ----- measuring ----------------------------------------------------------------------------------


@dataclass
class AudioMeasurement:
    """What :func:`measure_file` measured (levels in dB; ``-inf`` for silence)."""

    path: Path
    codec: str
    sample_rate: int
    channels: int
    bitrate: int | None  # bits per second, as the container says
    duration: float
    integrated_lufs: float
    loudness_range: float
    true_peak: float
    sample_peak: float
    rms: float
    noise_floor: float
    head: float  # seconds before the first sound
    tail: float  # seconds after the last sound
    correlation: float | None = None  # stereo only (DESIGN.md §111.4): of the two channels, whole file
    worst_correlation: float | None = None  # ... its lowest over 1 s windows with sound
    mono_fold_db: float | None = None  # ... how much quieter the mono fold (L + R) / 2 is

    @property
    def digital_silence(self) -> bool:
        """Whether the quietest part is exact zeros (no room tone)."""
        return self.noise_floor == -math.inf

    def to_json(self) -> dict[str, Any]:
        def num(v: float) -> float | None:
            return round(v, 2) if math.isfinite(v) else None

        data = asdict(self)
        data["path"] = str(self.path)
        for key in ("duration", "integrated_lufs", "loudness_range", "true_peak", "sample_peak", "rms", "noise_floor", "head", "tail", "mono_fold_db"):
            data[key] = None if data[key] is None else num(data[key])
        for key in ("correlation", "worst_correlation"):
            data[key] = None if data[key] is None else round(data[key], 3)
        data["digital_silence"] = self.digital_silence
        return data


def _probe(path: Path) -> tuple[str, int, int, int | None]:
    """``(codec, sample_rate, channels, bitrate)`` of ``path``'s first audio stream."""
    import av

    try:
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            ctx = stream.codec_context
            bitrate = ctx.bit_rate or stream.bit_rate or container.bit_rate or None
            return CODEC_NAMES.get(ctx.name, ctx.name), ctx.sample_rate, ctx.channels, bitrate
    except (OSError, IndexError, av.error.FFmpegError) as exc:
        raise VidgenError(f"cannot read audio file {path}: {exc}") from None


_SUMMARY = {
    "integrated_lufs": r"Integrated loudness:\s+I:\s+(\S+) LUFS",
    "loudness_range": r"Loudness range:\s+LRA:\s+(\S+) LU",
    "true_peak": r"True peak:\s+Peak:\s+(\S+) dBFS",
    "sample_peak": r"Sample peak:\s+Peak:\s+(\S+) dBFS",
}


def parse_ebur128(text: str) -> dict[str, float]:
    """The summary of ffmpeg's ``ebur128=peak=true+sample`` log (its last ``Summary:``)."""
    summary = text[text.rfind("Summary:") :]
    values = {}
    for key, pattern in _SUMMARY.items():
        match = re.search(pattern, summary)
        if match is None:
            raise VidgenError(f"ffmpeg's ebur128 summary has no {key.replace('_', ' ')}")
        values[key] = float(match.group(1))
    if values["integrated_lufs"] <= -70.0:
        values["integrated_lufs"] = -math.inf
    return values


class _Frames:
    """Per 10 ms frame mean power of samples fed in order (any chunk sizes)."""

    def __init__(self, channels: int) -> None:
        self.channels = channels
        self.rest = np.zeros((0, channels), dtype=np.float64)
        self.powers: list[np.ndarray] = []
        self.products: list[np.ndarray] = []  # stereo: per frame sums of L², R², L·R
        self.total = 0.0
        self.count = 0

    def add(self, x: np.ndarray) -> None:
        self.total += float(np.sum(x.astype(np.float64) ** 2))
        self.count += x.size
        x = np.concatenate([self.rest, x])
        n = len(x) // FRAME
        if n:
            frames = x[: n * FRAME]
            self.powers.append(np.mean(frames.reshape(n, FRAME * self.channels) ** 2, axis=1))
            if self.channels == 2:
                self.products.append(self._products(frames.reshape(n, FRAME, 2)))
        self.rest = x[n * FRAME :]

    @staticmethod
    def _products(frames: np.ndarray) -> np.ndarray:
        left, right = frames[..., 0], frames[..., 1]
        return np.stack([np.sum(left**2, axis=1), np.sum(right**2, axis=1), np.sum(left * right, axis=1)], axis=1)

    def finish(self) -> np.ndarray:
        if len(self.rest):
            self.powers.append(np.array([np.sum(self.rest**2) / (FRAME * self.channels)]))
            if self.channels == 2:
                self.products.append(self._products(self.rest.reshape(1, -1, 2)))
        return np.concatenate(self.powers) if self.powers else np.zeros(0)


#: Seconds of the windows the worst correlation is taken over (only windows with sound count).
CORRELATION_WINDOW = 1.0


def _stereo_image(products: np.ndarray, power: np.ndarray) -> tuple[float, float, float]:
    """``(correlation, worst correlation, mono fold dB)`` of a stereo file from its per-frame
    sums of L², R², L·R (``products``) and frame powers: the correlation of the two channels over
    the whole file (1: the same, 0: unrelated or one silent, -1: opposite), its lowest over
    :data:`CORRELATION_WINDOW` windows with sound, and how much quieter (dB) the mono fold
    ``(L + R) / 2`` is than the stereo channels' mean power (0 for a centred voice, 3 for a
    hard-panned or fully decorrelated one, more where they cancel)."""
    ll, rr, lr = (float(v) for v in products.sum(axis=0))
    corr = lr / math.sqrt(ll * rr) if ll > 0 and rr > 0 else 0.0
    fold = (ll + rr + 2 * lr) / 4
    drop = 10 * math.log10(((ll + rr) / 2) / fold) if fold > 0 else (math.inf if ll + rr > 0 else 0.0)
    width = round(CORRELATION_WINDOW * 100)
    worst = corr
    if len(products) >= width:
        sums = np.concatenate([np.zeros((1, 3)), np.cumsum(products, axis=0)])
        win = sums[width:] - sums[:-width]
        loud = np.concatenate([[0.0], np.cumsum(power)])
        heard = (loud[width:] - loud[:-width]) / width > 10 ** (SOUND_DB / 10)
        denom = np.sqrt(win[:, 0] * win[:, 1])
        ok = heard & (denom > 0)
        if ok.any():
            worst = float(np.min(win[ok, 2] / denom[ok]))
    return corr, worst, drop


def _db(power: float) -> float:
    return 10 * math.log10(power) if power > 0 else -math.inf


def measure_file(path: Path) -> AudioMeasurement:
    """Measure the audio file ``path`` (see the module doc); :class:`VidgenError` if ffmpeg
    cannot read it."""
    from vidgen.render.ffmpeg import find_ffmpeg

    if not path.is_file():
        raise VidgenError(f"{path}: no such audio file")
    codec, rate, channels, bitrate = _probe(path)
    channels = max(1, channels)
    ffmpeg = find_ffmpeg()
    frames = _Frames(channels)
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(
            [ffmpeg, "-hide_banner", "-nostats", "-nostdin", "-v", "info", "-i", str(path), "-vn",
             "-af", f"ebur128=peak=true+sample:framelog=quiet,aresample={RATE}", "-ac", str(channels), "-f", "f32le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=log,
        )
        assert proc.stdout is not None
        chunk = RATE * channels * 4
        pending = b""
        while True:
            data = proc.stdout.read(chunk)
            if not data:
                break
            data = pending + data
            usable = len(data) - len(data) % (4 * channels)
            pending = data[usable:]
            frames.add(np.frombuffer(data[:usable], dtype="<f4").reshape(-1, channels))
        code = proc.wait()
        log.seek(0)
        text = log.read().decode("utf-8", errors="replace")
    if code != 0:
        raise VidgenError(f"cannot read audio file {path}: {text.strip()[-500:] or f'exit code {code}'}")
    levels = parse_ebur128(text)
    power = frames.finish()
    duration = frames.count / channels / RATE
    loud = np.nonzero(power > 10 ** (SOUND_DB / 10))[0]
    head = float(loud[0]) * FRAME / RATE if loud.size else duration
    tail = max(0.0, duration - (float(loud[-1]) + 1) * FRAME / RATE) if loud.size else duration
    width = round(FLOOR_SECONDS * 100)
    if len(power) >= width:
        sums = np.concatenate([[0.0], np.cumsum(power)])
        floor = _db(float(np.min(sums[width:] - sums[:-width])) / width)
    else:
        floor = _db(float(power.mean())) if len(power) else -math.inf
    image: tuple[float | None, float | None, float | None] = (None, None, None)
    if channels == 2 and frames.products:
        image = _stereo_image(np.concatenate(frames.products), power)
    return AudioMeasurement(
        path, codec, rate, channels, bitrate, duration, levels["integrated_lufs"], levels["loudness_range"],
        levels["true_peak"], levels["sample_peak"], _db(frames.total / frames.count) if frames.count else -math.inf, floor, head, tail,
        *image,
    )


# ----- checking -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckItem:
    """One measured value against its target: ``pass``, ``fail``, or a ``note`` that does not
    count."""

    name: str
    value: str
    target: str
    status: Literal["pass", "fail", "note"]


@dataclass
class PresetResult:
    """A file checked against one preset."""

    preset: str
    description: str
    items: list[CheckItem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(item.status != "fail" for item in self.items)

    @property
    def failures(self) -> list[CheckItem]:
        return [item for item in self.items if item.status == "fail"]

    def to_json(self) -> dict[str, Any]:
        return {"preset": self.preset, "description": self.description, "ok": self.ok, "items": [asdict(i) for i in self.items]}

    def line(self) -> str:
        """``podcast    PASS  loudness -16.1 LUFS (-16 ±1) ok; ...``."""
        verdict = "PASS" if self.ok else "FAIL"
        parts = [f"{i.name} {i.value} ({i.target}) {'ok' if i.status == 'pass' else i.status.upper() if i.status == 'fail' else 'note'}" for i in self.items]
        return f"{self.preset:<10} {verdict}  " + "; ".join(parts)


def _fmt(value: float, unit: str) -> str:
    return f"{value:.1f} {unit}" if math.isfinite(value) else f"-inf {unit}"


def _at_most(name: str, value: float, limit: float, unit: str) -> CheckItem:
    return CheckItem(name, _fmt(value, unit), f"≤ {limit:g}", "pass" if value <= limit + 1e-9 else "fail")


def _between(name: str, value: float, lo: float, hi: float, unit: str, fmt: str = "{:.1f}") -> CheckItem:
    shown = (fmt.format(value) + f" {unit}") if math.isfinite(value) else f"-inf {unit}"
    return CheckItem(name, shown, f"{lo:g} to {hi:g}", "pass" if lo - 1e-9 <= value <= hi + 1e-9 else "fail")


def check(m: AudioMeasurement, preset: LoudnessPreset) -> PresetResult:
    """``m`` against ``preset`` (see :data:`PRESETS`)."""
    result = PresetResult(preset.name, preset.description)
    items = result.items
    if preset.lufs is not None:
        target = preset.mono_lufs if m.channels == 1 and preset.mono_lufs is not None else preset.lufs
        layout = "mono" if m.channels == 1 else "stereo"
        ok = math.isfinite(m.integrated_lufs) and abs(m.integrated_lufs - target) <= preset.tolerance + 1e-9
        items.append(CheckItem("loudness", _fmt(m.integrated_lufs, "LUFS"), f"{target:g} ±{preset.tolerance:g} {layout}", "pass" if ok else "fail"))
    if preset.max_true_peak is not None:
        items.append(_at_most("true peak", m.true_peak, preset.max_true_peak, "dBTP"))
    if preset.rms is not None:
        items.append(_between("RMS", m.rms, preset.rms[0], preset.rms[1], "dB"))
    if preset.max_sample_peak is not None:
        items.append(_at_most("peak", m.sample_peak, preset.max_sample_peak, "dB"))
    if preset.noise_floor is not None:
        item = _at_most("noise floor", m.noise_floor, preset.noise_floor, "dB")
        if m.digital_silence:
            item = CheckItem(item.name, "digital silence", item.target, "pass")
        items.append(item)
    if preset.head is not None:
        items.append(_between("head", m.head, preset.head[0], preset.head[1], "s", "{:.2f}"))
    if preset.tail is not None:
        items.append(_between("tail", m.tail, preset.tail[0], preset.tail[1], "s", "{:.2f}"))
    if preset.acx_notes:
        rate = f"{m.sample_rate / 1000:g} kHz"
        kbps = f"{m.bitrate // 1000} kb/s" if m.bitrate else "? kb/s"
        fits = m.codec == "mp3" and (m.bitrate or 0) >= ACX_BITRATE and m.sample_rate == ACX_RATE
        items.append(CheckItem("ACX format", f"{m.codec} {kbps} {rate}", "mp3 ≥ 192 kb/s CBR, 44.1 kHz", "pass" if fits else "note"))
        minutes = m.duration / 60
        items.append(CheckItem("length", f"{minutes:.1f} min", f"≤ {ACX_MINUTES} min per file", "pass" if minutes <= ACX_MINUTES else "note"))
    return result


#: Mono compatibility (DESIGN.md §111.4): the channels' correlation over the file at least
#: :data:`MIN_CORRELATION`, over every second with sound at least :data:`MIN_WORST_CORRELATION`
#: (a moment that cancels), the mono fold at most :data:`MAX_MONO_FOLD_DB` quieter (a voice panned
#: hard to one side, or a wholly decorrelated bed, loses 3 dB).
MIN_CORRELATION = 0.0
MIN_WORST_CORRELATION = -0.3
MAX_MONO_FOLD_DB = 3.5


def mono_check(m: AudioMeasurement) -> PresetResult:
    """Whether stereo ``m`` folds to mono well (see :data:`MAX_MONO_FOLD_DB`); a mono file
    passes with a note."""
    result = PresetResult("mono", f"mono compatibility: correlation ≥ {MIN_CORRELATION:g} (each second ≥ {MIN_WORST_CORRELATION:g}), mono fold ≤ {MAX_MONO_FOLD_DB:g} dB quieter")
    if m.correlation is None or m.worst_correlation is None or m.mono_fold_db is None:
        result.items.append(CheckItem("channels", f"{m.channels}", "2", "note"))
        return result
    items = result.items
    items.append(CheckItem("correlation", f"{m.correlation:.2f}", f"≥ {MIN_CORRELATION:g}", "pass" if m.correlation >= MIN_CORRELATION - 1e-9 else "fail"))
    items.append(CheckItem("worst second", f"{m.worst_correlation:.2f}", f"≥ {MIN_WORST_CORRELATION:g}", "pass" if m.worst_correlation >= MIN_WORST_CORRELATION - 1e-9 else "fail"))
    items.append(_at_most("mono fold", m.mono_fold_db, MAX_MONO_FOLD_DB, "dB"))
    return result


def check_all(m: AudioMeasurement, presets: list[LoudnessPreset]) -> list[PresetResult]:
    """``m`` against each of ``presets``."""
    return [check(m, p) for p in presets]


def summary_line(m: AudioMeasurement) -> str:
    """``mp3 192 kb/s, 44.1 kHz stereo, 0:38; -16.1 LUFS, true peak -1.9 dBTP, ...``."""
    minutes, seconds = divmod(round(m.duration), 60)
    kbps = f" {m.bitrate // 1000} kb/s" if m.bitrate and m.codec not in ("pcm_s16le", "pcm_s24le", "pcm_f32le") else ""
    layout = {1: "mono", 2: "stereo"}.get(m.channels, f"{m.channels} channels")
    floor = "digital silence" if m.digital_silence else _fmt(m.noise_floor, "dB")
    return (
        f"{m.codec}{kbps}, {m.sample_rate / 1000:g} kHz {layout}, {minutes}:{seconds:02d}; "
        f"{_fmt(m.integrated_lufs, 'LUFS')}, true peak {_fmt(m.true_peak, 'dBTP')}, peak {_fmt(m.sample_peak, 'dB')}, "
        f"RMS {_fmt(m.rms, 'dB')}, LRA {m.loudness_range:.1f} LU, noise floor {floor}, head {m.head:.2f} s, tail {m.tail:.2f} s"
    )
