"""`vidgen render`: worker, padding, concat, --scene, variants, hooks, failures, SRT.

Rendering tests use tiny formats (160x90 @ 10 fps); each scene is a separate worker process
(~1 s each), so the projects are kept small and the main one is rendered once per module.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest
import yaml

from conftest import write_files
from vidgen.cli import main
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render import ffmpeg as ff
from vidgen.render import pipeline
from vidgen.render.pipeline import render_project
from vidgen.render.worker import frame_size
from vidgen.subtitles import format_time

FPS = 10
FRAME = 1 / FPS
LONG_TEXT = "This is a deliberately long beat text that must be split into more than one cue. Ação!"


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe is None:
        pytest.skip("ffmpeg not found on PATH")
    return exe


def make_tone(path: Path, seconds: float, freq: int = 440) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
         "-c:a", "libmp3lame", str(path)],
        check=True,
        capture_output=True,
    )


def write_project(root: Path, config: dict[str, Any], files: dict[str, str] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    base = {
        "title": "Render test",
        "output": "out",
        "format": {"width": 160, "height": 90, "fps": FPS},
        "preview": {"width": 96, "height": 54, "fps": 5},
        "narration": {"pad": 0.3, "words_per_second": 3.0},
        "theme": {"background": "#203040"},
    }
    (root / "video.yaml").write_text(yaml.safe_dump({**base, **config}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    write_files(root, files or {})
    return root


def decode_audio(path: Path) -> np.ndarray:
    """Mono float samples at 48 kHz."""
    with av.open(str(path)) as c:
        resampler = av.AudioResampler(format="flt", layout="mono", rate=48000)
        chunks = [g.to_ndarray().ravel() for f in c.decode(c.streams.audio[0]) for g in resampler.resample(f)]
    return np.concatenate(chunks)


def streams(path: Path) -> dict[str, Any]:
    with av.open(str(path)) as c:
        info: dict[str, Any] = {"types": [s.type for s in c.streams]}
        v = c.streams.video[0]
        info.update(width=v.codec_context.width, height=v.codec_context.height, video=float(v.duration * v.time_base))
        if c.streams.audio:
            a = c.streams.audio[0]
            info.update(audio=float(a.duration * a.time_base), rate=a.rate, channels=a.codec_context.channels)
    return info


HOOKS_EXT = """
import json
from pathlib import Path
from vidgen.api import *

@scene("dot")
class DotScene(NarratedScene):
    def construct(self):
        dot = Dot(color=self.theme.color("accent"))
        for i, (_, d) in enumerate(self.narrate_all()):
            if i == 0:
                self.play(FadeIn(dot), run_time=min(0.5, d))

def _record(ctx):
    keep = {}
    for key, value in ctx.data.items():
        if key == "timings":
            value = {"duration": value["duration"], "n": len(value.get("scenes", value.get("beats", [])))}
        elif isinstance(value, Path):
            value = str(value)
        keep[key] = value
    with open(ctx.project.root / "hooks.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": ctx.event, "data": keep}) + "\\n")

for _event in ("pre_render", "post_scene", "post_render"):
    hook(_event)(_record)
"""


@pytest.fixture(scope="module")
def main_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 3-scene project in a folder with spaces, an apostrophe and non-ASCII characters,
    rendered once (final quality)."""
    root = tmp_path_factory.mktemp("render") / "my vídeo's dir" / "proj ç"
    write_project(
        root,
        {
            "scenes": [
                {"id": "s1", "type": "text_card", "params": {"text": "Olá"}, "beats": [{"text": "One."}, {"text": LONG_TEXT}]},
                {"id": "quiet", "type": "text_card", "params": {"text": "..."}, "duration": 1.0},
                {"id": "s3", "type": "dot", "beats": [{"text": "Last beat."}]},
            ]
        },
        {"extensions/hooks_ext.py": HOOKS_EXT},
    )
    make_tone(root / "audio" / "s1_b1.mp3", 1.0, 440)
    make_tone(root / "audio" / "s1_b2.mp3", 0.6, 660)
    make_tone(root / "audio" / "s3_b1.mp3", 0.8, 880)
    from vidgen import hooks, registry, runtime

    with registry.isolated(), hooks.isolated():
        render_project(Project.load(root))
    runtime.clear_context()
    return root


def combined_timings(root: Path, sub: str = "final") -> dict[str, Any]:
    return json.loads((root / "build" / sub / "timings.json").read_text(encoding="utf-8"))


# ----- full render --------------------------------------------------------------------------------


@pytest.mark.render
@pytest.mark.slow
def test_full_render_outputs(main_project: Path) -> None:
    out = main_project / "out.mp4"
    info = streams(out)
    assert sorted(info["types"]) == ["audio", "video"]
    assert (info["width"], info["height"], info["rate"], info["channels"]) == (160, 90, 48000, 2)
    timings = combined_timings(main_project)
    assert [s["id"] for s in timings["scenes"]] == ["s1", "quiet", "s3"]
    assert timings["format"] == {"width": 160, "height": 90, "fps": FPS} and timings["audio"] is True
    total = sum(s["duration"] for s in timings["scenes"])
    assert timings["duration"] == pytest.approx(total)
    assert info["video"] == pytest.approx(total, abs=FRAME)
    assert info["audio"] == pytest.approx(total, abs=0.03)
    # scene offsets are cumulative; each scene lasts what its worker measured (within a frame)
    offset = 0.0
    for scene in timings["scenes"]:
        assert scene["start"] == pytest.approx(offset)
        per_scene = json.loads((main_project / "build/final/timings" / f"{scene['id']}.json").read_text(encoding="utf-8"))
        assert scene["duration"] == pytest.approx(per_scene["duration"], abs=FRAME / 2)
        assert ff.probe(main_project / "build/final/scenes" / f"{scene['id']}.mp4").duration == pytest.approx(scene["duration"])
        offset += scene["duration"]
    assert timings["scenes"][1]["duration"] == pytest.approx(1.0, abs=FRAME)
    # build layout
    build = main_project / "build" / "final"
    assert sorted(p.name for p in (build / "padded").glob("*.wav")) == ["quiet.wav", "s1.wav", "s3.wav"]
    assert not (build / "scenes" / "quiet.wav").exists()  # silent scene: Manim wrote no audio


@pytest.mark.render
@pytest.mark.slow
def test_no_drift_beats_start_where_timings_say(main_project: Path) -> None:
    samples = decode_audio(main_project / "out.mp4")
    rate = 48000
    timings = combined_timings(main_project)
    beats = [b for s in timings["scenes"] for b in s["beats"]]
    assert [b["id"] for b in beats] == ["s1_b1", "s1_b2", "s3_b1"]
    for beat in beats:
        lo = max(0, int((beat["start"] - 0.1) * rate))
        window = np.abs(samples[lo : int((beat["start"] + 0.2) * rate)])
        onset = (lo + int(np.argmax(window > 0.03))) / rate
        assert onset == pytest.approx(beat["start"], abs=0.01), beat["id"]
        # silence after the narration (the pad) before the next beat
        tail = samples[int((beat["end"] + 0.05) * rate) : int((beat["end"] + 0.25) * rate)]
        assert np.abs(tail).max() < 0.01, beat["id"]
    quiet = timings["scenes"][1]
    segment = samples[int(quiet["start"] * rate) : int((quiet["start"] + quiet["duration"]) * rate)]
    assert np.abs(segment).max() < 0.001


@pytest.mark.render
def test_srt_from_render(main_project: Path) -> None:
    text = (main_project / "out.srt").read_text(encoding="utf-8")
    blocks = text.strip().split("\n\n")
    assert len(blocks) == 4  # One. | long text in 2 cues | Last beat.
    assert [b.split("\n")[0] for b in blocks] == ["1", "2", "3", "4"]
    assert blocks[0] == "1\n00:00:00,000 --> 00:00:01,000\nOne."
    timings = combined_timings(main_project)
    s3_start = timings["scenes"][2]["start"]
    assert blocks[3].split("\n")[1].startswith(format_time(s3_start))
    assert blocks[3].endswith("\nLast beat.") and "Ação!" in text


@pytest.mark.render
def test_hooks_dispatched_with_data(main_project: Path) -> None:
    records = [json.loads(line) for line in (main_project / "hooks.jsonl").read_text(encoding="utf-8").splitlines()]
    events = [r["event"] for r in records]
    assert events == ["pre_render", "post_scene", "post_scene", "post_scene", "post_render"]
    pre = records[0]["data"]
    assert pre["scenes"] == ["s1", "quiet", "s3"] and pre["preview"] is False and pre["variant"] is None
    assert pre["no_audio"] is False and Path(pre["render_dir"]) == main_project / "build" / "final"
    assert [r["data"]["scene_id"] for r in records[1:4]] == ["s1", "quiet", "s3"]
    assert Path(records[1]["data"]["video"]) == main_project / "build/final/scenes/s1.mp4"
    assert records[1]["data"]["timings"]["n"] == 2
    post = records[-1]["data"]
    assert Path(post["output"]) == main_project / "out.mp4" and Path(post["srt"]) == main_project / "out.srt"
    assert Path(post["timings_file"]) == main_project / "build/final/timings.json"
    assert post["timings"]["n"] == 3 and post["timings"]["duration"] > 3


@pytest.mark.render
@pytest.mark.slow
def test_scene_option_rerenders_only_that_scene(main_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    scenes_dir = main_project / "build" / "final" / "scenes"
    before = {p.name: p.stat().st_mtime_ns for p in scenes_dir.glob("*.mp4")}
    out_before = (main_project / "out.mp4").stat().st_mtime_ns
    (main_project / "hooks.jsonl").unlink()
    assert main(["render", str(main_project), "--scene", "s3"]) == 0
    after = {p.name: p.stat().st_mtime_ns for p in scenes_dir.glob("*.mp4")}
    assert after["s1.mp4"] == before["s1.mp4"] and after["quiet.mp4"] == before["quiet.mp4"]
    assert after["s3.mp4"] != before["s3.mp4"]
    assert (main_project / "out.mp4").stat().st_mtime_ns != out_before
    out = capsys.readouterr().out
    assert "[1/1] s3: rendering" in out and "rendered 1 scene(s), 2 reused" in out
    assert f"video:     {main_project / 'out.mp4'}" in out and "duration:  0:0" in out
    records = [json.loads(line)["event"] for line in (main_project / "hooks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records == ["pre_render", "post_scene", "post_render"]
    assert streams(main_project / "out.mp4")["video"] == pytest.approx(combined_timings(main_project)["duration"], abs=FRAME)


# ----- single-scene projects ----------------------------------------------------------------------


@pytest.fixture
def small(tmp_path: Path) -> Callable[..., Path]:
    def make(scenes: list[dict[str, Any]] | None = None, files: dict[str, str] | None = None, **config: Any) -> Path:
        scenes = scenes or [{"id": "only", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Hello."}]}]
        root = write_project(tmp_path / "small", {"scenes": scenes, **config}, files)
        if any(s["id"] == "only" for s in scenes):
            make_tone(root / "audio" / "only_b1.mp3", 0.5)
        return root

    return make


@pytest.mark.render
@pytest.mark.slow
def test_no_audio_has_silent_track(small: Callable[..., Path]) -> None:
    root = small()
    result = render_project(Project.load(root), preview=True, no_audio=True)
    assert result.output == root / "out_preview.mp4" and result.srt == root / "out_preview.srt"
    info = streams(result.output)
    assert sorted(info["types"]) == ["audio", "video"] and (info["width"], info["height"]) == (96, 54)
    assert np.abs(decode_audio(result.output)).max() < 0.001
    timings = json.loads(result.timings_file.read_text(encoding="utf-8"))
    assert timings["audio"] is False and timings["scenes"][0]["beats"][0]["end"] == pytest.approx(0.5, abs=0.05)
    assert result.timings_file == root / "build" / "preview" / "timings.json"


VARIANT_EXT = """
import json
from vidgen.api import *

@scene("probe")
class Probe(NarratedScene):
    def construct(self):
        (self.project.root / "frame.json").write_text(
            json.dumps([self.frame_width, self.frame_height, self.is_portrait]), encoding="utf-8")
        self.add(Square(side_length=min(self.frame_width, self.frame_height) * 0.8))
"""


@pytest.mark.render
@pytest.mark.slow
def test_variant_naming_resolution_and_frame(small: Callable[..., Path]) -> None:
    root = small(
        scenes=[{"id": "p", "type": "probe", "duration": 0.5}],
        files={"extensions/probe.py": VARIANT_EXT},
        variants={"vertical": {"format": {"width": 90, "height": 160}}},
    )
    result = render_project(Project.load(root, variant="vertical"))
    assert result.output == root / "out_vertical.mp4" and result.srt == root / "out_vertical.srt"
    assert result.timings_file == root / "build" / "final_vertical" / "timings.json"
    assert (root / "build" / "final_vertical" / "scenes" / "p.mp4").is_file()
    info = streams(result.output)
    assert (info["width"], info["height"]) == (90, 160)
    width, height, portrait = json.loads((root / "frame.json").read_text(encoding="utf-8"))
    assert (width, height, portrait) == (pytest.approx(8.0), pytest.approx(8.0 * 160 / 90), True)
    assert result.srt.read_text(encoding="utf-8") == ""  # silent scene: no cues


BOOM_EXT = """
from vidgen.api import *

@scene("boom")
class Boom(NarratedScene):
    def construct(self):
        self.add(Square())
        explode_here = 1 / 0

@scene("clear_error")
class ClearError(NarratedScene):
    def construct(self):
        self.project.asset("assets/missing.png")
"""


@pytest.mark.render
@pytest.mark.slow
def test_worker_failure_shows_user_traceback(small: Callable[..., Path]) -> None:
    root = small(scenes=[{"id": "b", "type": "boom", "duration": 1}, {"id": "ok", "type": "text_card", "params": {"text": "x"}, "duration": 0.4}],
                 files={"extensions/bad.py": BOOM_EXT})
    with pytest.raises(VidgenError) as info:
        render_project(Project.load(root))
    message = str(info.value)
    assert message.startswith("scene 'b' failed (worker exit code 2):")
    assert "bad.py" in message and "explode_here = 1 / 0" in message and "ZeroDivisionError" in message
    assert not (root / "build/final/scenes/ok.mp4").exists()  # stopped at the first failure
    assert not (root / "out.mp4").exists()


@pytest.mark.render
@pytest.mark.slow
def test_keep_going_reports_failures_at_end(small: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    root = small(
        scenes=[
            {"id": "b", "type": "boom", "duration": 1},
            {"id": "ok", "type": "text_card", "params": {"text": "x"}, "duration": 0.4},
            {"id": "c", "type": "clear_error", "duration": 1},
        ],
        files={"extensions/bad.py": BOOM_EXT},
    )
    assert main(["render", str(root), "--keep-going", "--jobs", "3"]) == 1
    err = capsys.readouterr().err
    assert "error: scene 'b' failed" in err and "ZeroDivisionError" in err
    assert "error: scene 'c' failed (worker exit code 1):\nerror: asset not found: assets/missing.png" in err
    assert err.rstrip().endswith("error: 2 scene(s) failed: b, c; the video was not joined (1 scene(s) rendered)")
    assert (root / "build/final/scenes/ok.mp4").is_file() and not (root / "out.mp4").exists()


# ----- no rendering -------------------------------------------------------------------------------


def test_ffmpeg_missing(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(ff.shutil, "which", lambda name: None)
    monkeypatch.setattr(ff.sys, "platform", "win32")
    assert main(["render", str(make_project())]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ffmpeg not found on PATH; install it with `winget install ffmpeg`")


def test_unknown_scene_option(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    ffmpeg_exe()
    assert main(["render", str(make_project()), "--scene", "nope", "--scene", "intro"]) == 1
    assert capsys.readouterr().err == "error: unknown scene(s): nope; scenes: intro, main\n"


def test_unknown_scene_type_fails_before_rendering(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    text = (root / "video.yaml").read_text(encoding="utf-8").replace("type: text_card", "type: text_crad", 1)
    (root / "video.yaml").write_text(text, encoding="utf-8")
    assert main(["render", str(root)]) == 1
    assert "unknown scene type 'text_crad'; did you mean 'text_card'?" in capsys.readouterr().err
    assert not (root / "build").exists()


def test_jobs_must_be_positive(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["render", str(make_project()), "--jobs", "0"]) == 1
    assert "--jobs must be at least 1" in capsys.readouterr().err


def test_audio_warning(make_project, caplog: pytest.LogCaptureFixture) -> None:
    project = Project.load(make_project())
    (project.audio_dir).mkdir()
    (project.audio_dir / "custom.mp3").write_bytes(b"x")
    with caplog.at_level(logging.WARNING, logger="vidgen.render"):
        pipeline.warn_audio(project)
    assert "audio stale for custom; missing for intro_b1, intro_b2;" in caplog.text
    assert "run `vidgen tts`" in caplog.text


def test_frame_size() -> None:
    assert frame_size(1920, 1080) == (pytest.approx(14.2222222), 8.0)
    assert frame_size(1080, 1920) == (8.0, pytest.approx(14.2222222))
    assert frame_size(1080, 1080) == (8.0, 8.0)


def test_concat_quote_and_tail() -> None:
    assert ff.concat_quote("C:/Users/jp/my vídeo's dir/a.mp4") == "'C:/Users/jp/my vídeo'\\''s dir/a.mp4'"
    assert pipeline._tail("a\rb\r\nc\n\n" + "\n".join(str(i) for i in range(100)), lines=3) == "97\n98\n99"
    assert pipeline._tail("x 10%\rx 100%\ndone\n") == "x 100%\ndone"


def test_worker_usage_error() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "vidgen.render.worker", "nowhere", "s"], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 1 and result.stderr.startswith("error: project not found: nowhere")
