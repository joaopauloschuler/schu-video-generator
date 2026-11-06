"""Step 284: the file of an audio-only render (formats, channels, rates), loudness presets and
their check (``vidgen audio check``), the voice leveller, room tone and transcripts (DESIGN.md
§111.6-111.8). Narration is mocked: each beat's "MP3" is a WAV of speech-like bursts."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import audio_check, cli, mix
from vidgen.audio_encode import encode, encode_args
from vidgen.audio_only import effective_pacing, render_audio
from vidgen.config import AudioOutputConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.sfx import RATE, write_wav
from vidgen.subtitles import Cue
from vidgen.transcripts import format_vtt, plain_text

STORY: dict[str, Any] = {
    "title": "The Ferry",
    "output": "ferry",
    "narration": {"pad": 0.3, "words_per_second": 2},
    "voices": {"man": {"voice_id": "x", "label": "Ferryman"}},
    "sections": [
        {"id": "shore", "title": "The Shore", "beats": ["one two three four", {"text": "five six", "voice": "man"}, "seven eight"]},
        {"id": "river", "title": "The River", "beats": ["nine ten", "eleven twelve", {"text": "Home.", "voice": "man"}]},
    ],
}


def _write(root: Path, data: dict[str, Any]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return root


def _speech(seconds: float, seed: int) -> np.ndarray:
    """Speech-like mono: syllables of a harmonic tone, each 120-250 ms, a few much louder."""
    rng = np.random.default_rng(seed)
    n = round(seconds * RATE)
    t = np.arange(n) / RATE
    tone = sum(np.sin(2 * np.pi * 150 * h * t) / h for h in range(1, 6))
    envelope = np.zeros(n)
    pos = 0
    while pos < n:
        length = int(rng.uniform(0.12, 0.25) * RATE)
        level = 0.08 * (4.0 if rng.random() < 0.1 else rng.uniform(0.6, 1.2))
        envelope[pos : pos + length] = level * np.hanning(min(length, n - pos))
        pos += length + int(0.05 * RATE)
    return (tone * envelope).astype(np.float32)


def _voice_all(project: Project, seconds: float = 1.6) -> None:
    for k, (_, beat) in enumerate(project.beats()):
        write_wav(project.audio_dir / f"{beat.id}.mp3", _speech(seconds, k))


def _project(tmp_path: Path, name: str, **extra: Any) -> Project:
    project = Project.load(_write(tmp_path / name, {**STORY, **extra}))
    _voice_all(project)
    return project


# ----- config --------------------------------------------------------------------------------------


def test_audio_output_config() -> None:
    plain = AudioOutputConfig()
    assert plain.plain and plain.effective_bitrate is None and plain.transcript_kinds == ("txt", "srt", "vtt", "chapters")
    mp3 = AudioOutputConfig(format="mp3", transcripts=["vtt", "txt"])
    assert not mp3.plain and mp3.effective_bitrate == "192k" and mp3.transcript_kinds == ("txt", "vtt")
    assert AudioOutputConfig(format="ogg").effective_bitrate == "96k" and AudioOutputConfig(transcripts=False).transcript_kinds == ()
    assert not AudioOutputConfig(loudness="podcast").plain


@pytest.mark.parametrize("output, message", [
    ({"format": "ogg", "sample_rate": 44100}, "Opus (format: ogg) encodes 16000, 24000, 48000 only"),
    ({"format": "flac"}, "audio_output.format"),
    ({"bitrate": "192"}, "audio_output.bitrate"),
    ({"loudness": "podcasts"}, "audio_output.loudness"),
])
def test_audio_output_problems(tmp_path: Path, output: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError) as caught:
        Project.load(_write(tmp_path / "p", {**STORY, "audio_output": output}))
    assert message in str(caught.value)


def test_audiobook_pacing_fills_only_unset_keys(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "a", {**STORY, "audio_output": {"loudness": "audiobook"}, "pacing": {"tail": 4.0}}))
    pacing = effective_pacing(project)
    assert (pacing.lead_in, pacing.tail) == (0.6, 4.0)
    plain = Project.load(_write(tmp_path / "b", STORY))
    assert effective_pacing(plain) is plain.config.pacing


# ----- leveller and room tone ------------------------------------------------------------------------


def test_leveller_lowers_only_the_loud_peaks() -> None:
    peaks = np.full(400, -20.0)
    peaks[:100] = -200.0                     # silence: ignored by the reference
    peaks[200:203] = -8.0                    # a loud syllable, 12 dB above the usual peak
    gain = mix.leveller_gain(peaks)
    assert gain.max() <= 0 and gain[150] == 0.0 and gain[300] == 0.0
    over = -8.0 - (-20.0 + mix.LEVEL_ABOVE_DB)  # 4 dB over the threshold: past the soft knee
    assert -gain[201] == pytest.approx((1 - 1 / mix.LEVEL_RATIO) * over)
    assert gain[194] == 0.0 and gain[196] < 0 and gain[207] < 0 and gain[209] == 0.0   # 50 ms ramps around it (look-ahead)
    assert not mix.leveller_gain(np.full(10, -200.0)).any()


def test_room_tone_is_faint_steady_and_fixed() -> None:
    tone = mix.room_tone(-72.0)
    assert len(tone) == mix.ROOM_TONE_LOOP
    assert 10 * math.log10(np.mean(tone**2)) == pytest.approx(-72.0, abs=0.01)
    assert np.array_equal(tone, mix.room_tone(-72.0))
    halves = [10 * math.log10(np.mean(h**2)) for h in np.array_split(tone, 4)]
    assert max(halves) - min(halves) < 1.0


def test_a_video_mix_levels_only_when_asked(tmp_path: Path) -> None:
    scenes = [{"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "a b c"}]}]
    voice = np.repeat(_speech(3.0, 2)[:, None], 2, axis=1)
    wav = tmp_path / "v.wav"
    write_wav(wav, voice)
    timings = {"scenes": [{"id": "s", "start": 0.0, "duration": 3.0, "beats": [{"id": "s_b1", "start": 0.0, "end": 3.0}]}]}
    reports = {}
    for level in (None, True):
        audio = {"normalize": True} if level is None else {"normalize": True, "level_voice": level}
        project = Project.load(_write(tmp_path / f"p{level}", {"title": "t", "audio": audio, "scenes": scenes}))
        write_wav(project.audio_dir / "s_b1.mp3", voice[:, 0])
        reports[level] = mix.mix_audio(project, timings, [wav], None, tmp_path / f"m{level}.wav")
    assert reports[None].levelled_db is None and "levelled_db" not in reports[None].to_json()
    assert reports[True].levelled_db > 1.0 and reports[True].limited_db < reports[None].limited_db


# ----- rendering with presets ---------------------------------------------------------------------


def test_default_render_is_the_mix_as_before(tmp_path: Path) -> None:
    project = _project(tmp_path, "plain")
    result = render_audio(project)
    assert result.output.name == "ferry.wav" and result.check is None
    assert result.output.read_bytes() == (project.render_dir(False) / "audio" / "mix.wav").read_bytes()
    assert set(result.transcripts) == {"txt", "srt", "vtt", "chapters"}
    assert "levelled_db" not in result.timings["mix"] and "audio_output" not in result.timings


def test_podcast_mp3_mono(tmp_path: Path) -> None:
    project = _project(tmp_path, "pod", audio_output={"format": "mp3", "channels": "mono", "loudness": "podcast", "transcripts": ["txt", "vtt"]})
    result = render_audio(project)
    assert result.output.name == "ferry.mp3" and set(result.transcripts) == {"txt", "vtt"}
    measured = audio_check.measure_file(result.output)
    assert (measured.codec, measured.channels, measured.sample_rate) == ("mp3", 1, 48000)
    assert measured.integrated_lufs == pytest.approx(-19.0, abs=0.6) and result.check is not None and result.check.ok
    mixed = result.timings["mix"]
    assert mixed["mono"] and mixed["levelled_db"] > 0 and mixed["target_lufs"] == pytest.approx(-19 + mix.DUAL_MONO_LU)
    assert result.timings["audio_output"]["check"]["preset"] == "podcast"


def test_leveller_reduces_the_limiting(tmp_path: Path) -> None:
    levelled = render_audio(_project(tmp_path, "on", audio_output={"loudness": "podcast"}))
    plain = render_audio(_project(tmp_path, "off", audio_output={"loudness": "podcast"}, audio={"level_voice": False}))
    assert "levelled_db" not in plain.timings["mix"]
    assert levelled.timings["mix"]["limited_db"] < plain.timings["mix"]["limited_db"] - 1.0


def test_audiobook_rms_peaks_room_tone(tmp_path: Path) -> None:
    project = _project(tmp_path, "book", music=False,
                       audio_output={"format": "wav", "sample_rate": 44100, "bit_depth": 16, "channels": "mono", "loudness": "audiobook", "room_tone": -70})
    result = render_audio(project)
    m = audio_check.measure_file(result.output)
    assert (m.codec, m.sample_rate, m.channels) == ("pcm_s16le", 44100, 1)
    assert m.rms == pytest.approx(-20.0, abs=0.6) and m.sample_peak <= -3.0   # the limiter takes a little off
    assert m.noise_floor == pytest.approx(-70.0, abs=1.5) and not m.digital_silence
    assert 0.5 <= m.head <= 1.0 and 1.0 <= m.tail <= 5.0
    assert result.check is not None and result.check.ok, result.check.line()
    notes = {i.name: i.status for i in result.check.items}
    assert notes["ACX format"] == "note"   # a WAV: ACX wants MP3


@pytest.mark.parametrize("fmt, codec", [("m4a", "aac"), ("ogg", "opus"), ("wav", "pcm_s24le")])
def test_formats_encode(tmp_path: Path, fmt: str, codec: str) -> None:
    src = tmp_path / "mix.wav"
    write_wav(src, np.repeat(_speech(2.0, 1)[:, None], 2, axis=1))
    out = AudioOutputConfig(format=fmt, sample_rate=24000 if fmt == "ogg" else 48000)
    dst = tmp_path / f"x.{fmt}"
    encode(src, dst, out, {"title": "Ünïcode title"})
    m = audio_check.measure_file(dst)
    assert m.codec == codec and m.channels == 2 and m.duration == pytest.approx(2.0, abs=0.08)


def test_encode_args() -> None:
    args = encode_args(Path("in.wav"), Path("out.mp3.part"), AudioOutputConfig(format="mp3", channels="mono", sample_rate=44100), {"title": "T"})
    assert args[args.index("-af") + 1] == "pan=mono|c0=0.5*c0+0.5*c1,aresample=44100"
    assert args[args.index("-c:a") + 1] == "libmp3lame" and args[args.index("-b:a") + 1] == "192k"
    assert "title=T" in args and args[-3:] == ["-f", "mp3", "out.mp3.part"]
    wav = encode_args(Path("a"), Path("b"), AudioOutputConfig(bit_depth=16), {})
    assert "pcm_s16le" in wav and "-af" not in wav and "-b:a" not in wav


# ----- measuring and checking ------------------------------------------------------------------------


EBUR128 = """[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -16.2 LUFS
    Threshold: -26.5 LUFS

  Loudness range:
    LRA:         5.1 LU
    Threshold: -36.6 LUFS
    LRA low:   -19.9 LUFS
    LRA high:  -14.8 LUFS

  True peak:
    Peak:       -1.4 dBFS

  Sample peak:
    Peak:       -1.6 dBFS
"""


def test_parse_ebur128() -> None:
    assert audio_check.parse_ebur128("noise\n" + EBUR128) == {"integrated_lufs": -16.2, "loudness_range": 5.1, "true_peak": -1.4, "sample_peak": -1.6}
    silent = EBUR128.replace("-16.2 LUFS", "-70.0 LUFS").replace("-1.4 dBFS", "-inf dBFS")
    values = audio_check.parse_ebur128(silent)
    assert values["integrated_lufs"] == -math.inf and values["true_peak"] == -math.inf


def test_measure_file_head_tail_floor(tmp_path: Path) -> None:
    x = np.zeros(4 * RATE, dtype=np.float32)
    t = np.arange(2 * RATE) / RATE
    x[RATE // 2 : RATE // 2 + 2 * RATE] = 0.1 * np.sin(2 * np.pi * 440 * t)    # 0.5-2.5 s
    path = tmp_path / "x.wav"
    write_wav(path, x)
    m = audio_check.measure_file(path)
    assert m.head == pytest.approx(0.5, abs=0.011) and m.tail == pytest.approx(1.5, abs=0.011) and m.duration == pytest.approx(4.0)
    assert m.digital_silence and m.sample_peak == pytest.approx(-20.0, abs=0.1)
    assert m.rms == pytest.approx(20 * math.log10(0.1 / math.sqrt(2)) + 10 * math.log10(0.5), abs=0.1)   # half the file sounds


def _measured(**values: Any) -> audio_check.AudioMeasurement:
    base = dict(path=Path("x"), codec="mp3", sample_rate=44100, channels=1, bitrate=192000, duration=60.0, integrated_lufs=-19.2,
                loudness_range=4.0, true_peak=-2.0, sample_peak=-3.5, rms=-20.0, noise_floor=-math.inf, head=0.7, tail=2.0)
    return audio_check.AudioMeasurement(**{**base, **values})


def test_check_presets() -> None:
    mono = _measured()
    podcast = audio_check.check(mono, audio_check.PRESETS["podcast"])
    assert podcast.ok and podcast.items[0].target == "-19 ±1 mono"
    assert not audio_check.check(_measured(channels=2), audio_check.PRESETS["podcast"]).ok   # stereo wants -16
    book = audio_check.check(mono, audio_check.PRESETS["audiobook"])
    assert book.ok and {i.name: i.status for i in book.items}["noise floor"] == "pass"
    failing = audio_check.check(_measured(sample_peak=-2.0, head=0.2, noise_floor=-55.0), audio_check.PRESETS["audiobook"])
    assert [i.name for i in failing.failures] == ["peak", "noise floor", "head"]
    assert "FAIL" in failing.line() and failing.line().startswith("audiobook")
    wav = audio_check.check(_measured(codec="pcm_s16le", bitrate=None), audio_check.PRESETS["audiobook"])
    assert wav.ok and {i.name: i.status for i in wav.items}["ACX format"] == "note"
    assert not audio_check.check(mono, audio_check.PRESETS["broadcast"]).ok
    with pytest.raises(Exception, match="did you mean 'podcast'"):
        audio_check.preset_named("podcst")


def test_cli_audio_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _project(tmp_path, "cli", audio_output={"format": "m4a", "loudness": "podcast"})
    render_audio(project)
    assert cli.main(["audio", "check", str(project.root)]) == 0
    out = capsys.readouterr().out
    assert "ferry.m4a" in out and "podcast    PASS" in out and "audiobook" not in out
    path = project.root / "output" / "ferry.m4a"
    assert cli.main(["audio", "check", str(path), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert [c["preset"] for c in doc["checks"]] == ["podcast", "audiobook", "broadcast"] and doc["measured"]["codec"] == "aac"
    assert cli.main(["audio", "check", str(path), "--preset", "broadcast"]) == 1
    assert "broadcast  FAIL" in capsys.readouterr().out
    assert cli.main(["audio", "check", str(path), "--lufs", "-16", "--true-peak", "-1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["checks"][-1]["preset"] == "custom"
    assert cli.main(["audio", "check", str(tmp_path / "missing.mp3")]) == 1


# ----- transcripts -----------------------------------------------------------------------------------


def test_transcripts(tmp_path: Path) -> None:
    project = _project(tmp_path, "tr", subtitles={"speakers": "name"})
    result = render_audio(project)
    text = result.transcripts["txt"].read_text(encoding="utf-8")
    assert text.startswith("The Ferry\n\n[0:00] The Shore\n\nNarrator: one two three four\n\nFerryman: five six\n\nNarrator: seven eight\n")
    assert "The River\n\nNarrator: nine ten eleven twelve\n\nFerryman: Home.\n" in text   # one voice's lines joined
    vtt = result.transcripts["vtt"].read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT\n\n00:00:00.500 --> ") and "Ferryman: five six" in vtt
    srt = result.transcripts["srt"].read_text(encoding="utf-8")
    assert srt.startswith("1\n00:00:00,500 --> ")
    chapters = result.transcripts["chapters"].read_text(encoding="utf-8").splitlines()
    assert chapters[0] == "0:00 The Shore" and chapters[1].endswith("The River")
    river = next(c for c in result.timings["chapters"] if c["title"] == "The River")
    assert f"[{int(river['start']) // 60}:{int(river['start']) % 60:02d}] The River" in text


def test_plain_text_of_one_voice_has_no_names(tmp_path: Path) -> None:
    data = {"title": "T", "sections": [{"beats": ["a b", "c d"]}, {"beats": ["e f"]}]}
    project = Project.load(_write(tmp_path / "p", data))
    timings = {"scenes": [{"id": s.id, "beats": [{"id": b.id, "text": b.text} for b in s.beats]} for s in project.config.scenes], "chapters": []}
    assert plain_text(project, timings) == "T\n\na b c d\n\ne f\n"   # a paragraph per section


def test_cookbook_examples_load_and_are_linked(tmp_path: Path) -> None:
    import re

    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "COOKBOOK-AUDIO.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", text, flags=re.S)
    assert len(blocks) == 2
    for k, block in enumerate(blocks):
        project = Project.load(_write(tmp_path / f"c{k}", yaml.safe_load(block)))
        assert project.config.audio_only and project.config.audio_output.loudness in ("audiobook", "podcast")
    for doc in ("docs/COOKBOOK.md", "README.md", "docs/CONFIG.md", "AGENTS.md", "src/vidgen/data/guide/AGENTS.md"):
        assert "COOKBOOK-AUDIO.md" in (root / doc).read_text(encoding="utf-8"), doc


def test_format_vtt() -> None:
    assert format_vtt([Cue(3661.5, 3662.25, "a --> b")]) == "WEBVTT\n\n01:01:01.500 --> 01:01:02.250\na -> b\n"
