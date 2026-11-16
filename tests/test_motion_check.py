"""``vidgen motion check`` (DESIGN.md §121.3): the checks on synthetic frames (no ffmpeg), the
thresholds, the score's events, and the command on tiny encoded clips."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pytest
import yaml

from vidgen import cli
from vidgen import motion_check as mc
from vidgen.errors import VidgenError
from vidgen.project import Project

W, H, FPS = 80, 40, 30
TH = mc.Thresholds()


def scene(t: int) -> np.ndarray:
    """A frame that moves a little every frame: a slow colour wave and a dot drifting right."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    f = np.empty((H, W, 3), np.float32)
    f[..., 0] = 0.3 + 0.2 * np.sin(x / 12 + t * 0.05)
    f[..., 1] = 0.35 + 0.1 * np.cos(y / 9)
    f[..., 2] = 0.45
    f[(x - (10 + t % 60)) ** 2 + (y - 30) ** 2 < 16] = 0.9
    return f


def u8(frames: list[np.ndarray]) -> Iterator[np.ndarray]:
    return (np.clip(f * 255, 0, 255).astype(np.uint8) for f in frames)


def check(frames: list[np.ndarray], cuts: tuple[int, ...] = (), hits: list[float] | None = None,
          th: mc.Thresholds = TH) -> list[mc.Finding]:
    """The findings of ``frames`` (0..1 floats) as one video, scenes cut at ``cuts``."""
    feats = mc.measure([u8(frames)])
    edges = [0, *cuts, len(frames)]
    scenes = [mc.SceneSpan(f"s{k}", a, b) for k, (a, b) in enumerate(zip(edges, edges[1:]))]
    source = mc.Source("test", [mc.Segment(Path("x.mp4"))], FPS, scenes, np.array(hits or [], float))
    return mc.find_faults(feats, source, th)


def kinds(found: list[mc.Finding]) -> list[tuple[str, str, int]]:
    return [(f.kind, f.severity, f.frame) for f in found]


def clean(n: int = 90) -> list[np.ndarray]:
    return [scene(t) for t in range(n)]


# ----- the checks -----------------------------------------------------------------------------------


def test_clean_motion_has_no_findings() -> None:
    assert check(clean()) == []


def test_black_frames_inside_a_scene_are_an_error_at_a_cut_info_and_at_the_ends_nothing() -> None:
    frames = clean()
    for t in range(40, 60):  # the Parallel Space v7 bug: 20 black frames from a NaN in a shader
        frames[t] = np.zeros_like(frames[t])
    (found,) = check(frames, cuts=(30,))
    assert (found.kind, found.severity, found.frame, found.end, found.scene) == ("blank", "error", 40, 59, "s1")
    assert found.message.startswith("20 black frames inside the scene") and found.time == pytest.approx(40 / FPS)
    assert kinds(check(frames, cuts=(40,))) == [("blank", "info", 40)]  # a cut to black
    white = clean()
    white[50] = np.ones_like(white[50])
    assert kinds(check(white)) == [("blank", "error", 50)] and "1 white frame" in check(white)[0].message
    ends = clean()
    for t in [*range(0, 10), *range(80, 90)]:  # starts and ends on black
        ends[t] = np.zeros_like(ends[t])
    assert check(ends) == []


def test_a_fade_to_black_is_info_only_when_long() -> None:
    frames = clean(150)
    for t in range(40, 150):
        frames[t] = frames[t] * max(0.0, 1 - (t - 40) / 15) if t < 55 or t >= 110 else np.zeros_like(frames[t])
    for t in range(110, 125):
        frames[t] = scene(t) * (t - 110) / 15
    (found,) = check(frames)
    assert (found.kind, found.severity) == ("blank", "info") and "reached by a fade" in found.message
    assert check(frames, th=mc.Thresholds(dark_seconds=5.0)) == []


def test_one_frame_flash_and_drop_out_are_warnings_and_on_a_hit_info() -> None:
    frames = clean()
    frames[30] = frames[30] * 1.5
    frames[60] = frames[60] * 0.5
    found = check(frames)
    assert kinds(found) == [("flash", "warning", 30), ("flash", "warning", 60)]
    assert "1-frame flash" in found[0].message and "1-frame drop-out" in found[1].message
    on_hit = check(frames, hits=[29.6, 59.0])
    assert kinds(on_hit) == [("flash", "info", 30), ("flash", "info", 60)] and "on a hit or note" in on_hit[0].message
    assert kinds(check(frames, hits=[25.0, 62.0])) == [("flash", "warning", 30), ("flash", "warning", 60)]  # too far from them
    two = clean()
    two[30], two[31] = two[30] * 1.5, two[31] * 1.5
    assert kinds(check(two)) == [("flash", "warning", 30)] and "2-frame flash" in check(two)[0].message


def test_flicker_is_a_warning_and_the_same_on_the_beat_is_info() -> None:
    frames = [scene(t) * (0.8 if 20 <= t < 70 and t % 2 else 1.0) for t in range(90)]
    (found,) = check(frames)
    assert (found.kind, found.severity) == ("flicker", "warning") and "the whole frame" in found.message
    assert 18 <= found.frame <= 22 and 67 <= found.end <= 71
    hits = [float(t) for t in range(20, 70) if t % 2 == 0]  # a peak on every hit: beat-locked pulses
    (locked,) = check(frames, hits=hits)
    assert (locked.kind, locked.severity) == ("flicker", "info") and locked.message.startswith("beat-locked pulses")


def test_kick_pulses_that_decay_are_not_flicker() -> None:
    gains = [1.3, 1.2, 1.12, 1.06, 1.02]
    frames = [scene(t) * (gains[(t - 5) % 13] if t >= 5 and (t - 5) % 13 < 5 else 1.0) for t in range(120)]
    assert check(frames) == []


def test_local_flicker_names_the_blocks() -> None:
    frames = clean()
    for t in range(20, 70, 2):  # a lamp of 2 x 2 blocks
        frames[t] = frames[t].copy()
        frames[t][0:20, 50:70] *= 0.8
    (found,) = check(frames)
    assert (found.kind, found.severity) == ("flicker", "warning") and "flicker in 4 blocks" in found.message


def test_a_region_appearing_for_one_or_two_frames_pops_and_moving_things_do_not() -> None:
    for width in (1, 2):
        frames = clean()
        for t in range(40, 40 + width):
            frames[t] = frames[t].copy()
            frames[t][0:10, 10:30] = 1.0
        (found,) = check(frames)
        assert (found.kind, found.severity, found.frame, found.end) == ("pop", "warning", 40, 39 + width)
        assert f"appear for {width} frame(s)" in found.message and found.box == (0.125, 0.0, 0.375, 0.25)
    small = clean()
    small[40] = small[40].copy()
    small[40][0:10, 10:20] = 1.0
    assert kinds(check(small)) == [("pop", "info", 40)] and "small" in check(small)[0].message
    moving = clean()
    for t in range(30, 60):  # a bright square crossing the frame one block a frame
        moving[t] = moving[t].copy()
        x = 10 * (t - 30) % W
        moving[t][0:10, x : x + 10] = 1.0
    assert [f for f in check(moving) if f.kind == "pop"] == []


def test_a_wheel_turning_half_a_spoke_a_frame_strobes() -> None:
    frames = clean()
    y, x = np.mgrid[0:40, 0:40]
    for t in range(20, 70):
        angle = np.arctan2(y - 20, x - 20) + t * np.pi / 6
        frames[t] = frames[t].copy()
        frames[t][0:40, 0:40] = (np.sin(6 * angle) > 0)[..., None] * 0.9
    (found,) = check(frames)
    assert (found.kind, found.severity) == ("strobe", "warning") and found.box is not None
    assert 18 <= found.frame <= 23 and 66 <= found.end <= 70


def test_frozen_stretches_are_info_and_a_cut_splits_them() -> None:
    frames = [scene(min(t, 30)) if t < 90 else scene(t) for t in range(120)]
    (found,) = check(frames)
    assert (found.kind, found.severity, found.frame, found.end) == ("frozen", "info", 30, 89)
    assert found.message == "60 frames without visible change (2.0 s)"
    assert check(frames, th=mc.Thresholds(frozen_seconds=2.5)) == []
    split = check(frames, cuts=(60,), th=mc.Thresholds(frozen_seconds=0.9))
    assert [(f.frame, f.end, f.scene) for f in split if f.kind == "frozen"] == [(30, 59, "s0"), (60, 89, "s1")]


def test_a_brightness_jump_at_a_cut_is_info() -> None:
    frames = [scene(t) * (0.25 if t >= 45 else 1.0) for t in range(90)]
    (found,) = check(frames, cuts=(45,))
    assert (found.kind, found.severity, found.frame, found.scene) == ("cut_jump", "info", 45, "s1")
    assert "darker" in found.message
    assert check(frames, cuts=(45,), th=mc.Thresholds(cut_luma=0.5, cut_hist=2.1)) == []


# ----- thresholds, events ----------------------------------------------------------------------------


def test_thresholds_are_set_by_name() -> None:
    th = TH.with_overrides(["flash=0.2", "frozen-seconds=3", "pop_blocks=4"])
    assert (th.flash, th.frozen_seconds, th.pop_blocks) == (0.2, 3.0, 4) and isinstance(th.pop_blocks, int)
    assert th.to_json()["flash"] == 0.2 and TH.flash == 0.08
    with pytest.raises(VidgenError, match="did you mean 'flash'"):
        TH.with_overrides(["flsh=1"])
    with pytest.raises(VidgenError, match="not a whole number"):
        TH.with_overrides(["pop_blocks=1.5"])
    with pytest.raises(VidgenError, match="expected NAME=VALUE"):
        TH.with_overrides(["flash"])


def test_music_events_are_the_scores_hits_and_notes_in_video_time(make_project: Callable[..., Path]) -> None:
    data = {"title": "T", "music": {"source": "tidewater", "start": 50.0},
            "scenes": [{"id": "a", "type": "text_card", "params": {"text": "x"}, "duration": 3},
                       {"id": "b", "type": "text_card", "params": {"text": "y"}, "duration": 3}]}
    project = Project.load(make_project(data))
    times, name, notes = mc.music_events(project, {"a": 0.0, "b": 3.0}, {"a": 3.0, "b": 6.0})
    assert name == "tidewater" and notes == [] and len(times) > 20
    assert times.min() >= 0 and times.max() < 6 and np.all(np.diff(times) >= 0)
    # tidewater loops (53.3 s): starting 50 s in, its first bar comes round again 3.3 s into the video
    from vidgen.studio import load_music_score
    from vidgen.studio.templates import TEMPLATE_DIR

    length = load_music_score(TEMPLATE_DIR / "tidewater.yaml").seconds
    assert np.any(np.abs(times - (length - 50.0)) < 1e-6)


# ----- the command on encoded clips ------------------------------------------------------------------


def encode(path: Path, frames: list[np.ndarray]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv444p", str(path)]
    subprocess.run(command, input=b"".join(f.tobytes() for f in u8(frames)), check=True, capture_output=True)
    return path


def black_inside(n: int = 60, at: tuple[int, int] = (30, 36)) -> list[np.ndarray]:
    frames = clean(n)
    for t in range(*at):
        frames[t] = np.zeros_like(frames[t])
    return frames


def test_the_command_reports_a_file_with_strips(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    video = encode(tmp_path / "v.mp4", black_inside())
    code = cli.main(["motion", "check", str(video), "--out", str(tmp_path / "strips"), "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert code == 1 and doc["command"] == "motion" and doc["ok"] is False and doc["action"] == "check"
    assert (doc["frames"], doc["fps"], doc["size"], doc["scenes"], doc["hits"]) == (60, 30.0, [W, H], [], 0)
    (found,) = doc["findings"]
    assert (found["kind"], found["severity"], found["frame"], found["end_frame"], found["time"]) == ("blank", "error", 30, 35, 1.0)
    strip = Path(found["strip"])
    assert strip.name == "01_blank_0001.00s.png" and strip.is_file()
    from PIL import Image

    image = np.asarray(Image.open(strip).convert("L"), dtype=float)
    # 8 tiles (2 before, the first 2, the last 2, 2 after), 80 px each: tiles 3-6 are black, 1-2 and 7-8 not
    tiles = [image[30:60, 4 + k * 84 + 10 : 4 + k * 84 + 70].mean() for k in range(8)]
    assert all(v < 5 for v in tiles[2:6]) and all(v > 40 for v in tiles[:2] + tiles[6:])
    assert cli.main(["motion", "check", str(video), "--no-strips", "--fail-on", "never"]) == 0
    out = capsys.readouterr().out
    assert "error       1.00 s  frame     30  blank: 6 black frames inside the scene" in out and "strip:" not in out


@pytest.mark.slow
def test_a_projects_video_and_scene_clips_name_the_scenes(make_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    data = {"title": "T", "output": "t",
            "scenes": [{"id": "one", "type": "text_card", "params": {"text": "x"}, "duration": 1},
                       {"id": "two", "type": "text_card", "params": {"text": "y"}, "duration": 1}]}
    root = make_project(data)
    with pytest.raises(VidgenError, match="nothing rendered at final quality"):
        mc.project_source(Project.load(root), False)
    final = root / "build" / "final"
    encode(final / "scenes" / "one.mp4", clean(30))
    encode(final / "scenes" / "two.mp4", black_inside(30, (10, 14)))
    for sid in ("one", "two"):
        (final / "timings" / f"{sid}.json").parent.mkdir(parents=True, exist_ok=True)
        (final / "timings" / f"{sid}.json").write_text(json.dumps({"scene": sid, "duration": 1.0}), encoding="utf-8")
    assert cli.main(["motion", "check", str(root), "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["source"].endswith("(scene clips)") and [s["id"] for s in doc["scenes"]] == ["one", "two"]
    assert [(f["kind"], f["frame"], f["scene"]) for f in doc["findings"]] == [("blank", 40, "two")]
    assert Path(doc["findings"][0]["strip"]).parent == final / "motion"
    encode(root / "output" / "t.mp4", clean(30) + black_inside(30, (10, 14)))
    (final / "timings.json").write_text(json.dumps({"scenes": [{"id": "one", "start": 0.0, "duration": 1.0},
                                                               {"id": "two", "start": 1.0, "duration": 1.0}]}), encoding="utf-8")
    assert cli.main(["motion", "check", str(root), "--json", "--no-strips"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["source"].endswith("t.mp4") and [(f["kind"], f["frame"], f["scene"]) for f in doc["findings"]] == [("blank", 40, "two")]
    assert cli.main(["motion", "check", str(root), "--source", "nope"]) == 2
    assert yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))["output"] == "t"
