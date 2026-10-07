"""Background music and the final mix (Step 45, DESIGN.md §48): the generated beds, music files,
loudness measurement, ducking, the limiter, the ``music:`` / ``audio:`` config, ``vidgen
list-music`` and the mix of a rendered video."""

from __future__ import annotations

import contextlib
import io
import json
import math
import re
import shutil
import wave
import zlib
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest
import yaml

from conftest import write_clip
from vidgen import loudness, mix, music, registry
from vidgen.cli import main, project_problems
from vidgen.config import AudioConfig, DuckConfig, MusicCue, SceneMusic, parse_config
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.sfx import RATE, read_wav, write_wav

ROOT = Path(__file__).resolve().parents[1]
KPHI3_AUDIO = ROOT / "examples" / "kphi3" / "audio"


def _db(ratio: float) -> float:
    return 20 * math.log10(ratio)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


# ----- loudness ----------------------------------------------------------------------------------------


def test_loudness_of_reference_sines() -> None:
    t = np.arange(RATE * 12) / RATE
    tone = 0.1 * np.sin(2 * np.pi * 997 * t)  # -20 dBFS
    stereo = np.stack([tone, tone], axis=1)
    meter = loudness.measure(len(stereo), lambda a, b: stereo[a:b])
    assert meter.integrated == pytest.approx(-20.0, abs=0.05)  # BS.1770: a 997 Hz sine on both channels
    assert meter.true_peak == pytest.approx(-20.0, abs=0.05)
    assert loudness.integrated_loudness(tone) == pytest.approx(-23.01, abs=0.05)  # one channel
    # gating: silence (below -70 LUFS) does not pull the level down
    gapped = np.concatenate([stereo, np.zeros((RATE * 12, 2))])
    assert loudness.integrated_loudness(gapped) == pytest.approx(-20.0, abs=0.1)  # blocks across the edge count
    assert loudness.integrated_loudness(np.zeros((RATE, 2))) == -math.inf


def test_true_peak_sees_intersample_peaks() -> None:
    n = np.arange(RATE)
    x = np.sin(2 * np.pi * n / 4 + np.pi / 4)[:, None]  # samples at ±0.707, the wave peaks at 1
    assert np.abs(x).max() == pytest.approx(0.7071, abs=1e-4)
    assert loudness.measure(len(x), lambda a, b: x[a:b]).true_peak == pytest.approx(0.0, abs=0.15)


def test_meter_is_block_independent() -> None:
    x = np.random.default_rng(3).standard_normal((RATE * 23 + 123, 2)) * 0.05
    whole = loudness.integrated_loudness(x)
    meter = loudness.LoudnessMeter()
    power = loudness.kweighted_power(x)
    for lo in range(0, len(x), 7777):  # odd chunk sizes
        meter.add(power[lo : lo + 7777], np.abs(x[lo : lo + 7777]).max(axis=1))
    assert meter.integrated == pytest.approx(whole, abs=0.01)


# ----- beds ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(music.BUILTIN_BEDS))
def test_bed_is_deterministic_and_clean(name: str) -> None:
    bed = music.BUILTIN_BEDS[name]
    loop = music.bed_loop(name)
    fresh = bed.generate(np.random.default_rng(zlib.crc32(f"music:{name}".encode("utf-8"))))
    assert np.array_equal(loop, fresh)  # same samples every time
    assert loop.dtype == np.float32 and loop.shape == (round(bed.seconds * RATE), 2) and not loop.flags.writeable
    assert loudness.integrated_loudness(loop) == pytest.approx(music.MUSIC_LEVEL, abs=0.05)
    assert _db(float(np.abs(loop).max())) < -12  # lots of headroom
    assert np.abs(loop.mean(axis=0)).max() < 1e-3  # no DC
    # no harsh highs, no rumble: little energy above 5 kHz or below 35 Hz
    spectrum = np.abs(np.fft.rfft(loop.mean(axis=1).astype(np.float64))) ** 2
    freqs = np.fft.rfftfreq(len(loop), 1 / RATE)
    total = spectrum.sum()
    assert spectrum[freqs > 5000].sum() / total < 10 ** (-30 / 10)
    assert spectrum[freqs < 35].sum() / total < 10 ** (-30 / 10)
    # the two channels differ (a wide pad), but not opposite
    left, right = loop[:, 0].astype(np.float64), loop[:, 1].astype(np.float64)
    corr = float(np.dot(left, right) / math.sqrt(np.dot(left, left) * np.dot(right, right)))
    assert -0.2 < corr < 0.95


@pytest.mark.parametrize("name", list(music.BUILTIN_BEDS))
def test_bed_loop_seam_is_continuous(name: str) -> None:
    loop = music.bed_loop(name).astype(np.float64)
    steps = np.abs(np.diff(loop, axis=0))
    seam = np.abs(loop[0] - loop[-1])
    assert (seam <= np.quantile(steps, 0.999, axis=0)).all()  # the jump around the loop is an ordinary step
    # the level runs on across the seam: 50 ms RMS just before and just after it within 1.5 dB
    w = RATE // 20
    before, after = _rms(loop[-w:]), _rms(loop[:w])
    assert abs(_db(after / before)) < 1.5
    # tiled, the source reads straight across the seam
    source = music.Source(MusicCue(source=name, start=1.0), ROOT)
    n = len(loop)
    across = source.read(n - RATE - 10, n - RATE + 10)
    assert np.array_equal(across[:10], loop[-10:]) and np.array_equal(across[10:], loop[:10])


def test_bed_sources_differ_and_describe_themselves() -> None:
    a, b = music.bed_loop("calm"), music.bed_loop("pulse")
    assert a.shape != b.shape or not np.allclose(a, b)
    for bed in music.BUILTIN_BEDS.values():
        assert len(bed.description) > 150 and bed.use and bed.key and bed.chords
    with pytest.raises(VidgenError, match="unknown music bed 'nope'"):
        music.bed_loop("nope")


# ----- music files ----------------------------------------------------------------------------------


def _tone_file(path: Path, seconds: float, freq: float = 220.0, level: float = 0.3, channels: int = 1) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    x = level * np.sin(2 * np.pi * freq * t) * (1 + 0.5 * t / seconds)  # gets louder: tells positions apart
    data = np.repeat(x[:, None], channels, axis=1)
    write_wav(path, data)
    return data


def test_file_source_is_matched_trimmed_and_looped(tmp_path: Path) -> None:
    _tone_file(tmp_path / "assets" / "song.wav", 6.0)
    cue = MusicCue(source="assets/song.wav", start=1.0, crossfade=1.0)
    source = music.Source(cue, tmp_path)
    body_len = 5 * RATE
    assert loudness.integrated_loudness(source.head) == pytest.approx(music.MUSIC_LEVEL, abs=0.3)
    assert source.ends_at is None and source.length == body_len - RATE  # the loop drops the cross-faded tail
    played = source.read(0, 3 * body_len).astype(np.float64)
    original = read_wav(tmp_path / "assets" / "song.wav")[RATE:, 0].astype(np.float64)
    gain = np.abs(source.head[:, 0]).max() / np.abs(original[: len(source.head)]).max()
    assert np.allclose(played[: 4 * RATE, 0], original[: 4 * RATE] * gain, atol=2e-4)  # first pass from `start`
    # every repeat joins without a click (an equal-power cross-fade of this one tone may add up
    # to √2; a click would be a step many times the tone's own)
    seam = len(source.head)
    steps = np.abs(np.diff(played[seam - 100 : seam + 100, 0]))
    assert steps.max() < 1.5 * np.abs(np.diff(original)).max() * gain
    # without loop it plays once and then is silent
    once = music.Source(MusicCue(source="assets/song.wav", loop=False), tmp_path)
    assert once.ends_at == 6 * RATE and not once.read(6 * RATE, 7 * RATE).any()
    with pytest.raises(VidgenError, match="past the end"):
        music.Source(MusicCue(source="assets/song.wav", start=7), tmp_path)
    with pytest.raises(VidgenError, match="music file not found"):
        music.Source(MusicCue(source="assets/none.mp3"), tmp_path)


# ----- ducking and smoothing -----------------------------------------------------------------------------


def test_duck_curve_follows_the_speech() -> None:
    duck = DuckConfig(depth=10, attack=0.5, release=1.0, hold=0.6)
    curve = mix.duck_curve([(2.0, 4.0), (4.4, 6.0), (8.0, 9.0)], 1200, duck)
    assert curve[0] == 0 and curve[1199] == 0
    assert (curve[200:600] == -10).all()  # speech, and the 0.4 s pause (shorter than hold) between
    assert (curve[800:900] == -10).all()
    assert curve[150] == 0 and -10 < curve[175] < 0 and curve[199] == pytest.approx(-10, abs=0.01)  # attack ends at 2.0 s
    assert curve[599] == -10 and -10 < curve[650] < 0 and curve[700] == 0  # release over 1 s after 6.0
    assert (np.diff(curve[150:200]) <= 0).all() and (np.diff(curve[600:700]) >= 0).all()
    assert curve[749] == 0 and curve[760] < 0  # the attack of the 8 s speech starts at 7.5 s
    assert not mix.duck_curve([(2.0, 4.0)], 1200, DuckConfig(depth=0)).any()
    assert not mix.duck_curve([], 1200, duck).any()
    instant = mix.duck_curve([(2.0, 4.0)], 1200, DuckConfig(depth=6, attack=0, release=0, hold=0))
    assert curve[199] != 0 and instant[199] == 0 and instant[200] == -6 and instant[400] == 0


def test_smooth_steps_ramps_on_the_louder_side() -> None:
    levels = np.concatenate([np.ones(100), np.zeros(100), np.full(100, 0.5)])
    out = mix.smooth_steps(levels, 20)
    assert (out <= levels + 1e-12).all()
    assert out[79] == 1 and out[99] < 0.1  # down before the quiet part
    assert (out[100:202] == 0).all() and 0 < out[202] < 0.05 and out[221] == 0.5  # up after it


def test_limiter_keeps_true_peaks_under_the_ceiling() -> None:
    rng = np.random.default_rng(5)
    x = rng.standard_normal((RATE * 2, 2)) * 0.1
    x[RATE : RATE + 50] *= 12  # a burst far over full scale
    ceiling = 10 ** (-1.5 / 20)
    out, lowest = mix.limit(x, ceiling)
    assert lowest < 0.5
    assert loudness.peak_envelope(out).max() <= ceiling * 1.003
    untouched = slice(0, RATE - 2 * mix.LIMITER_WINDOW)
    assert np.array_equal(out[untouched], x[untouched])  # only around the burst
    quiet, low = mix.limit(x * 0.1, ceiling)
    assert low == 1.0 and np.array_equal(quiet, x * 0.1)


def test_clip_spans(tmp_path: Path) -> None:
    write_clip(tmp_path / "assets" / "loud.mp4", seconds=1.0)
    write_clip(tmp_path / "assets" / "silent.mp4", seconds=1.0, audio=False)
    scenes = [
        {"id": "a", "type": "video_clip", "params": {"path": "assets/loud.mp4"}, "duration": 2},
        {"id": "b", "type": "video_clip", "params": {"path": "assets/silent.mp4"}, "duration": 2},
        {"id": "c", "type": "video_clip", "params": {"path": "assets/loud.mp4", "mute": True}, "duration": 2},
        {"id": "d", "type": "video_clip", "params": {"path": "assets/loud.mp4", "volume": 0}, "duration": 2},
        {"id": "e", "type": "video_clip", "params": {"path": "assets/loud.mp4", "volume": 0.5}, "duration": 2},
    ]
    (tmp_path / "video.yaml").write_text(yaml.safe_dump({"title": "t", "scenes": scenes}), encoding="utf-8")
    timings = {"scenes": [{"id": s["id"], "start": 2.0 * i, "duration": 2.0, "beats": []} for i, s in enumerate(scenes)]}
    assert mix.clip_spans(Project.load(tmp_path), timings) == [(0.0, 2.0), (8.0, 10.0)]


def _silent_scenes(root: Path, seconds: list[float], **extra: Any) -> tuple[Project, dict[str, Any], list[Path]]:
    """A project of silent scenes (or, with ``beats``, narrated ones without audio), its timings
    and padded WAVs of silence, as ``join_scenes`` would have them."""
    root.mkdir(parents=True, exist_ok=True)
    scenes = [{"id": f"s{i}", "type": "title", "params": {"title": "x"}, "duration": d} for i, d in enumerate(seconds)]
    if extra.pop("beats", False):
        scenes = [{**s, "beats": [{"text": "Words here."}]} for s in scenes]
        for s in scenes:
            del s["duration"]
    (root / "video.yaml").write_text(yaml.safe_dump({"title": "t", "scenes": scenes, **extra}), encoding="utf-8")
    starts = np.concatenate([[0.0], np.cumsum(seconds)])
    timings = {
        "scenes": [
            {"id": s["id"], "start": float(starts[i]), "duration": d, "beats": [{"id": f"s{i}_b1", "start": float(starts[i]), "end": float(starts[i]) + d - 0.4}] if "beats" in s else []}
            for i, (s, d) in enumerate(zip(scenes, seconds))
        ]
    }
    wavs = []
    for i, d in enumerate(seconds):
        wavs.append(root / "padded" / f"s{i}.wav")
        write_wav(wavs[-1], np.zeros((round(d * RATE), 2)))
    return Project.load(root), timings, wavs


def test_music_only_video_is_normalised(tmp_path: Path) -> None:
    project, timings, wavs = _silent_scenes(tmp_path, [4.0, 5.0], music={"source": "pulse", "fade_in": 0.5}, audio={"target_lufs": -14})
    out = tmp_path / "mix.wav"
    report = mix.mix_audio(project, timings, wavs, None, out)
    assert report.mixed and report.normalized and report.integrated_lufs == pytest.approx(-14, abs=0.5)
    assert report.gain_db == pytest.approx(16, abs=1) and report.true_peak_dbtp <= -1.5
    assert report.music == [{"source": "pulse", "kind": "bed", "from": "s0", "to": "s1", "start": 0.0, "end": 9.0, "volume": 0.0, "duck": 12.0}]
    written = _read_24(out)
    assert len(written) == 9 * RATE and written[0].tolist() == [0.0, 0.0]  # the fade starts from silence
    assert loudness.integrated_loudness(written) == pytest.approx(report.integrated_lufs, abs=0.01)


def test_unvoiced_narration_is_not_normalised(tmp_path: Path) -> None:
    project, timings, wavs = _silent_scenes(tmp_path, [4.0, 4.0], beats=True, music="calm")
    report = mix.mix_audio(project, timings, wavs, None, tmp_path / "mix.wav")
    assert report.mixed and not report.normalized and report.gain_db == 0  # music under the estimate, as is
    assert report.integrated_lufs < music.MUSIC_LEVEL  # ducked under the (estimated) beats
    no_music = _silent_scenes(tmp_path / "plain", [2.0], audio={"normalize": False})
    report = mix.mix_audio(*no_music, None, tmp_path / "plain" / "mix.wav")
    assert not report.mixed and report.integrated_lufs == -math.inf and report.to_json()["integrated_lufs"] is None
    assert not (tmp_path / "plain" / "mix.wav").exists()


# ----- config, validate, list-music ------------------------------------------------------------------------


def _video(**extra: Any) -> dict[str, Any]:
    return {
        "title": "t",
        "scenes": [{"id": sid, "type": "title", "params": {"title": sid}, "duration": 1} for sid in "abc"],
        **extra,
    }


def test_music_config_forms() -> None:
    assert parse_config(_video()).music_cues == [] and parse_config(_video(music=False)).music_cues == []
    [cue] = parse_config(_video(music="calm")).music_cues
    assert cue == MusicCue(source="calm") and cue.duck == DuckConfig() and cue.loop and cue.fade_out == 3.0
    [cue] = parse_config(_video(music={"source": "assets/a.mp3", "duck": False, "volume": -3})).music_cues
    assert cue.duck.depth == 0 and cue.volume == -3
    [cue] = parse_config(_video(music={"source": "calm", "duck": {"depth": 6}})).music_cues
    assert cue.duck == DuckConfig(depth=6)
    cues = parse_config(_video(music=[{"source": "calm", "to": "a"}, {"source": "pulse", "from": "b"}])).music_cues
    assert [(c.source, c.from_, c.to) for c in cues] == [("calm", None, "a"), ("pulse", "b", None)]
    cfg = parse_config(_video(scenes=[{"id": "a", "type": "t", "duration": 1, "music": False}, {"id": "b", "type": "t", "duration": 1, "music": {"volume": -6}}]))
    assert cfg.scenes[0].music is False and cfg.scenes[1].music == SceneMusic(volume=-6)
    assert cfg.audio == AudioConfig() and cfg.audio.normalize == "auto" and cfg.audio.target_lufs == -16


@pytest.mark.parametrize(
    "value, message",
    [
        ([{"source": "calm"}, {"source": "pulse", "from": "b"}], "music[1] overlaps music[0]"),
        ([{"source": "calm", "from": "c", "to": "a"}], "from 'c' comes after to 'a'"),
        ({"source": "calm", "to": "zz"}, "music: unknown scene to 'zz'"),
        ({"source": "calm", "volume": 20}, "less than or equal to 12"),
        ({"source": "calm", "duck": {"depth": -1}}, "greater than or equal to 0"),
        ({"source": "calm", "fade": 1}, "fade"),
    ],
)
def test_music_config_errors(value: Any, message: str) -> None:
    with pytest.raises(VidgenError, match=re.escape(message)):
        parse_config(_video(music=value))


def test_validate_reports_missing_music_file(make_project: Any) -> None:
    root = make_project(_video(music={"source": "assets/music/theme.mp3"}))
    problems = {p.location: p.message for p in project_problems(Project.load(root))}
    assert "neither a built-in bed nor a file: assets/music/theme.mp3" in problems["music.source"]
    assert "calm, pulse, bright" in problems["music.source"]
    root2 = make_project(_video(music=[{"source": "calm", "to": "a"}, {"source": "assets/x.wav", "from": "b"}]), folder="p2")
    assert [p.location for p in project_problems(Project.load(root2))] == ["music[1].source"]


def test_list_music(tmp_path: Path, make_project: Any, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(_video())
    _tone_file(root / "assets" / "music" / "theme.wav", 2.0, channels=2)
    previews = tmp_path / "previews"
    assert main(["list-music", str(root), "--json", "--render-dir", str(previews)]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "list-music" and doc["ok"] and doc["count"] == len(music.BUILTIN_BEDS) + 1
    assert doc["level"] == music.MUSIC_LEVEL and doc["duck"]["depth"] == 12.0
    items = {m["name"]: m for m in doc["music"]}
    calm = items["calm"]
    assert calm["origin"] == "builtin" and calm["tempo"] is None and calm["key"] == "D major" and calm["loop_seconds"] == 60.0
    assert calm["loudness"] == pytest.approx(music.MUSIC_LEVEL, abs=0.1) and calm["description"].startswith("A slow, warm ambient pad")
    assert items["pulse"]["tempo"] == 96 and items["bright"]["tempo"] == 120
    theme = items["assets/music/theme.wav"]
    assert theme["origin"] == "project" and theme["duration"] == 2.0 and theme["description"] is None
    assert Path(calm["preview"]) == previews / "calm.wav" and len(list(previews.glob("*.wav"))) == 3
    assert np.allclose(read_wav(previews / "calm.wav"), music.bed_loop("calm"), atol=1.5 / 32768)
    assert main(["list-music", str(root)]) == 0
    out = capsys.readouterr().out
    assert "calm  builtin  D major, no beat, 60 s loop" in out and "pulse  builtin  A minor, 96 BPM" in out
    assert "assets/music/theme.wav  project file  2.0 s" in out and "level at volume 0: -30 LUFS" in out


def test_schema_has_music(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert {"music", "audio"} <= set(schema["properties"]) and "music" in schema["$defs"]["SceneConfig"]["properties"]
    import jsonschema

    for value in ("calm", {"source": "pulse", "duck": False}, [{"source": "calm", "to": "a"}, "bright"], False):
        jsonschema.validate(_video(music=value), schema)


# ----- rendering ------------------------------------------------------------------------------------------

BEATS = ("s1_b1", "s1_b2")


def _write(root: Path, extra: dict[str, Any], scenes: list[dict[str, Any]]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "audio").mkdir(exist_ok=True)
    for beat in BEATS:  # real ElevenLabs narration (kphi3), so ducking keys off real speech
        shutil.copy(KPHI3_AUDIO / f"{beat}.mp3", root / "audio" / f"{beat}.mp3")
    data = {
        "title": "Music test",
        "output": "out",
        "format": {"width": 96, "height": 54, "fps": 10},
        "preview": {"width": 96, "height": 54, "fps": 10},
        **extra,
        "scenes": scenes,
    }
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return root


TALK = {"id": "talk", "type": "title", "params": {"title": "Talk"}, "beats": [{"id": b, "text": "Words."} for b in BEATS]}


@pytest.fixture(scope="module")
def music_project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    """A silent intro, a scene narrated with two real MP3s, a silent scene without music and a
    silent outro; the calm bed ducked under the narration; rendered once with ``render --json``."""
    root = _write(
        tmp_path_factory.mktemp("music") / "proj",
        {"music": {"source": "calm", "fade_in": 1.0, "fade_out": 2.0}, "sfx": {"auto": False}},
        [
            {"id": "intro", "type": "title", "params": {"title": "Hi"}, "duration": 3, "sfx": ["chime"]},
            TALK,
            {"id": "quiet", "type": "title", "params": {"title": "Shh"}, "duration": 3, "music": False},
            {"id": "outro", "type": "title", "params": {"title": "Bye"}, "duration": 4},
        ],
    )
    out = io.StringIO()
    with registry.isolated(), contextlib.redirect_stdout(out):
        assert main(["render", str(root), "--preview", "--json"]) == 0
    from vidgen import runtime

    runtime.clear_context()
    return root, json.loads(out.getvalue())


def _timings(root: Path) -> dict[str, Any]:
    return json.loads((root / "build" / "preview" / "timings.json").read_text(encoding="utf-8"))


def _mp4_audio(path: Path) -> np.ndarray:
    with av.open(str(path)) as c:
        resampler = av.AudioResampler(format="flt", layout="stereo", rate=RATE)
        chunks = [g.to_ndarray().reshape(-1, 2) for f in c.decode(c.streams.audio[0]) for g in resampler.resample(f)]
    return np.concatenate(chunks)


def _read_24(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as src:
        assert (src.getnchannels(), src.getsampwidth(), src.getframerate()) == (2, 3, RATE)
        raw = np.frombuffer(src.readframes(src.getnframes()), dtype=np.uint8).reshape(-1, 3)
    ints = (raw[:, 0].astype(np.int32) | raw[:, 1].astype(np.int32) << 8 | raw[:, 2].astype(np.int32) << 16)
    ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
    return (ints / 8388608).reshape(-1, 2)


@pytest.mark.render
def test_render_reports_and_reaches_the_target_loudness(music_project: tuple[Path, dict[str, Any]]) -> None:
    root, doc = music_project
    report = doc["mix"]
    assert report == _timings(root)["mix"]
    assert report["mixed"] and report["normalized"] and report["target_lufs"] == -16.0 and report["true_peak_limit"] == -1.5
    assert report["integrated_lufs"] == pytest.approx(-16.0, abs=1.0) and report["true_peak_dbtp"] <= -1.5
    [cue] = report["music"]
    assert cue == {"source": "calm", "kind": "bed", "from": "intro", "to": "outro", "start": 0.0, "end": doc["duration"], "volume": 0.0, "duck": 12.0}
    mixed = _read_24(root / "build/preview/padded/mix.wav")
    assert len(mixed) == round(doc["duration"] * RATE)
    meter = loudness.measure(len(mixed), lambda a, b: mixed[a:b])
    assert meter.integrated == pytest.approx(-16.0, abs=1.0) and meter.true_peak <= -1.5 + 0.05
    # the encoded video: within 1 LU of the target, nothing clipped
    audio = _mp4_audio(root / "out_preview.mp4")
    assert loudness.integrated_loudness(audio) == pytest.approx(-16.0, abs=1.0)
    assert np.abs(audio).max() < 1.0


@pytest.mark.render
def test_music_ducks_under_the_narration(music_project: tuple[Path, dict[str, Any]]) -> None:
    root, _ = music_project
    project = Project.load(root)
    timings = _timings(root)
    total = round(timings["duration"] * RATE)
    [placed] = mix.plan_music(project, timings, total)
    speech = mix.speech_spans(project, timings)
    talk = timings["scenes"][1]
    assert len(speech) == 2 and talk["start"] < speech[0][0] < talk["start"] + 0.5  # the MP3's lead-in silence is cut
    unducked = placed.cue.model_copy(update={"duck": DuckConfig(depth=0)})
    flat_project = Project(project.root, project.config_file, project.config.model_copy(update={"music": unducked}), None)
    [flat] = mix.plan_music(flat_project, timings, total)
    track, plain = mix.MusicTrack([placed]), mix.MusicTrack([flat])
    a, b = round((speech[0][0] + 0.5) * RATE), round((speech[1][1] - 0.5) * RATE)  # well inside the speech
    assert _db(_rms(track.read(a, b)) / _rms(plain.read(a, b))) == pytest.approx(-12.0, abs=0.1)
    intro = (round(1.5 * RATE), round(2.4 * RATE))  # after the fade-in, before the attack
    assert _rms(track.read(*intro)) == pytest.approx(_rms(plain.read(*intro)), rel=1e-6)
    # the 1 s pause between the two beats (shorter than hold) stays ducked
    pause = (round(speech[0][1] * RATE), round(speech[1][0] * RATE))
    assert _db(_rms(track.read(*pause)) / _rms(plain.read(*pause))) == pytest.approx(-12.0, abs=0.1)
    # no music in the scene with `music: false` (it fades out before it)
    quiet = timings["scenes"][2]
    assert not track.read(round(quiet["start"] * RATE), round((quiet["start"] + quiet["duration"]) * RATE)).any()
    # in the mix, the music under speech is ~20 dB under the voice
    voice = mix.WavTrack([root / "build/preview/padded" / f"{s['id']}.wav" for s in timings["scenes"]])
    assert -24 < _db(_rms(track.read(a, b)) / _rms(voice.read(a, b))) < -16


@pytest.mark.render
def test_mix_is_the_sum_where_the_limiter_rests(music_project: tuple[Path, dict[str, Any]]) -> None:
    root, doc = music_project
    project = Project.load(root)
    timings = _timings(root)
    padded = root / "build/preview/padded"
    voice = mix.WavTrack([padded / f"{s['id']}.wav" for s in timings["scenes"]])
    effects = mix.WavTrack([padded / "sfx.wav"])
    music_track = mix.MusicTrack(mix.plan_music(project, timings, voice.length))
    mixed = _read_24(padded / "mix.wav")
    a, b = round(0.2 * RATE), round(2.5 * RATE)  # the intro: music and the chime, far under the ceiling
    total = voice.read(a, b) + effects.read(a, b) + music_track.read(a, b)
    assert np.abs(effects.read(a, b)).max() > 0.01  # the chime is in there
    gain = float(np.sum(mixed[a:b] * total) / np.sum(total * total))
    assert _db(gain) == pytest.approx(doc["mix"]["gain_db"], abs=0.006)  # the reported gain
    assert np.abs(mixed[a:b] - total * gain).max() < 2 / 8388608


@pytest.mark.render
def test_narration_only_video_keeps_its_level(tmp_path: Path) -> None:
    root = _write(tmp_path / "plain", {}, [TALK])
    with registry.isolated():
        from vidgen.render.pipeline import render_project

        result = render_project(Project.load(root), preview=True)
    report = result.timings["mix"]
    assert not report["mixed"] and not report["normalized"] and report["music"] == [] and report["gain_db"] == 0
    assert report["integrated_lufs"] == pytest.approx(-24.4, abs=1.0)  # the narration as rendered (Step 4)
    assert not (root / "build/preview/padded/mix.wav").exists()
    # asked for, normalisation applies without music too
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["audio"] = {"normalize": True, "target_lufs": -18}
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with registry.isolated():
        result = render_project(Project.load(root), preview=True, scenes=[])
    report = result.timings["mix"]
    assert report["mixed"] and report["normalized"] and report["integrated_lufs"] == pytest.approx(-18, abs=0.5)
    assert loudness.integrated_loudness(_mp4_audio(root / "out_preview.mp4")) == pytest.approx(-18, abs=1.0)
    # --no-audio: no mix at all
    with registry.isolated():
        result = render_project(Project.load(root), preview=True, scenes=[], no_audio=True)
    assert "mix" not in result.timings and not (root / "build/preview/padded/mix.wav").exists()
