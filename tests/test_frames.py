"""Frame capture (`vidgen render --frames`): planning, the capture hook, stills and indexes.

Rendering tests use 160x90 @ 10 fps (preview 96x54 @ 5 fps) and a few small scenes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import av
import numpy as np
import pytest
from PIL import Image

from test_json_output import documented
from test_render import make_tone, write_project
from vidgen.capture import CapturedFrame, FrameCapture, StillWriter, plan_targets
from vidgen.cli import main
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render import worker
from vidgen.render.pipeline import render_project

FPS = 10


# ----- planning and the capture hook (no rendering) ----------------------------------------------


@pytest.mark.parametrize(
    ("start", "frames", "n", "include_end", "expected"),
    [
        (0, 10, 1, True, [(1, 9)]),
        (0, 10, 1, False, []),
        (5, 10, 2, True, [(1, 9), (2, 14)]),
        (0, 10, 3, False, [(1, 3), (2, 6)]),
        (0, 2, 4, True, [(2, 0), (4, 1)]),  # fewer frames than stills: merged, highest k kept
        (0, 2, 4, False, [(2, 0)]),
        (3, 0, 1, True, [(1, 3)]),  # an empty segment still has one frame
    ],
)
def test_plan_targets(start: int, frames: int, n: int, include_end: bool, expected: list[tuple[int, int]]) -> None:
    assert plan_targets(start, frames, n, include_end) == expected


class FakeRenderer:
    def __init__(self) -> None:
        self.skip_animations = False
        self.written: list[tuple[int, int]] = []

    def add_frame(self, frame: np.ndarray, num_frames: int = 1) -> None:
        self.written.append((int(frame[0, 0, 0]), num_frames))


def fake_scene() -> SimpleNamespace:
    return SimpleNamespace(renderer=FakeRenderer(), spec=SimpleNamespace(id="sc"))


def pixel(value: int) -> np.ndarray:
    return np.full((2, 3, 4), value, dtype=np.uint8)


def test_capture_observes_without_changing_frames() -> None:
    from manim import config

    scene = fake_scene()
    seen: list[tuple[CapturedFrame, Any]] = []
    capture = FrameCapture(3, [lambda sc, cap: seen.append((cap, sc))])
    capture.attach(scene)  # type: ignore[arg-type]
    capture.begin_segment("b1", 9, include_end=False)  # stills 1, 2 at frames 2, 5; 3 at the end
    scene.renderer.add_frame(pixel(1), 2)
    scene.renderer.add_frame(pixel(2))
    scene.renderer.skip_animations = True
    scene.renderer.add_frame(pixel(99), 5)  # skipped frames are not written: not counted
    scene.renderer.skip_animations = False
    scene.renderer.add_frame(pixel(3), 4)
    scene.renderer.add_frame(pixel(4), 5)  # the beat ran longer than planned
    capture.end_segment("b1")
    assert scene.renderer.written == [(1, 2), (2, 1), (99, 5), (3, 4), (4, 5)]  # passed through unchanged
    assert capture.frames_written == 12
    got = [(c.beat_id, c.k, c.n, c.frame, int(c.pixels[0, 0, 0])) for c, _ in seen]
    assert got == [("b1", 1, 3, 2, 2), ("b1", 2, 3, 5, 3), ("b1", 3, 3, 11, 4)]
    assert all(sc is scene for _, sc in seen)
    assert seen[2][0].time == pytest.approx(11 / config.frame_rate)


def test_capture_finish_takes_unreached_stills_from_the_last_frame() -> None:
    scene = fake_scene()
    seen: list[CapturedFrame] = []
    capture = FrameCapture(2, [lambda sc, cap: seen.append(cap)])
    capture.attach(scene)  # type: ignore[arg-type]
    capture.begin_segment(None, 10, include_end=True)  # frames 4 and 9
    scene.renderer.add_frame(pixel(7), 6)
    capture.finish()
    capture.finish()  # idempotent
    assert [(c.beat_id, c.k, c.frame, int(c.pixels[0, 0, 0])) for c in seen] == [(None, 1, 4, 7), (None, 2, 5, 7)]


def test_capture_validation_and_empty_beat() -> None:
    with pytest.raises(ValueError):
        FrameCapture(0)
    scene = fake_scene()
    seen: list[CapturedFrame] = []
    capture = FrameCapture(1, [lambda sc, cap: seen.append(cap)])
    capture.attach(scene)  # type: ignore[arg-type]
    capture.begin_segment("b", 3, include_end=False)
    capture.end_segment("b")  # no frame written during the beat: no still
    capture.end_segment("unknown")
    assert seen == []


def test_still_writer(tmp_path: Path) -> None:
    writer = StillWriter(tmp_path / "f")
    rgba = np.zeros((4, 6, 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 3] = 200, 255
    writer(None, CapturedFrame("sc", None, 1, 2, 7, 0.7, rgba))  # type: ignore[arg-type]
    writer(None, CapturedFrame("sc", "b1", 1, 2, 3, 0.3, rgba))  # type: ignore[arg-type]
    with Image.open(tmp_path / "f" / "sc-1.png") as image:
        assert image.mode == "RGB" and image.size == (6, 4) and image.getpixel((0, 0)) == (200, 0, 0)
    index = writer.index("sc", 2, 6, 4, 10)
    assert [e["path"] for e in index["frames"]] == ["b1-1.png", "sc-1.png"]  # frame order
    assert index["frames"][0] == {"beat": "b1", "k": 1, "n": 2, "frame": 3, "time": 0.3, "path": "b1-1.png"}
    assert (index["scene"], index["per_beat"], index["width"], index["height"], index["fps"]) == ("sc", 2, 6, 4, 10)


def test_options_are_checked(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    assert main(["render", str(root), "--frames-per-beat", "0"]) == 1
    assert "--frames-per-beat must be at least 1" in capsys.readouterr().err
    with pytest.raises(VidgenError, match="must not be negative"):
        render_project(Project.load(root), frames=-1)
    assert worker.build_parser().parse_args(["p", "s"]).frames == 0
    assert worker.build_parser().parse_args(["p", "s", "--frames", "3"]).frames == 3


# ----- rendering ---------------------------------------------------------------------------------

CAPTURE_EXT = """
import json
from vidgen.api import *

@scene("mover")
class Mover(NarratedScene):
    \"\"\"A dot moving left to right during each beat; records what listeners see.\"\"\"

    def construct(self):
        seen = []
        if self.capture is not None:
            self.capture.listeners.append(
                lambda scene, cap: seen.append([cap.beat_id, cap.frame, [type(m).__name__ for m in scene.mobjects]]))
        dot = Dot(LEFT * 5, color=self.theme.color("accent"), radius=0.6)
        self.add(dot)
        for i, (_, d) in enumerate(self.narrate_all()):
            if i == 1:
                self.add(Square(side_length=1).to_edge(UP))
            self.play(dot.animate.shift(RIGHT * 5), run_time=d, rate_func=linear)
        if self.capture is not None:
            (self.project.root / "seen.json").write_text(json.dumps(seen), encoding="utf-8")

@scene("fader")
class Fader(NarratedScene):
    outro = 0.4

    def construct(self):
        steps = [FadeIn(Square(side_length=6, fill_opacity=1, color=WHITE))]
        self.reveal(steps)
        self.finish()
"""


def scenes_config() -> list[dict[str, Any]]:
    return [
        {"id": "m", "type": "mover", "beats": [{"text": "One."}, {"text": "Two."}]},
        {"id": "q", "type": "fader", "duration": 1.0},
        {"id": "t", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Short words here."}]},
    ]


@pytest.fixture
def capture_project(tmp_path: Path) -> Path:
    root = write_project(tmp_path / "proj", {"scenes": scenes_config()}, {"extensions/capture_ext.py": CAPTURE_EXT})
    make_tone(root / "audio" / "m_b1.mp3", 1.0)
    make_tone(root / "audio" / "m_b2.mp3", 0.6)
    return root


def decode_frames(path: Path) -> list[np.ndarray]:
    with av.open(str(path)) as container:
        return [f.to_ndarray(format="rgb24") for f in container.decode(container.streams.video[0])]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def render(root: Path, **kwargs: Any):
    from vidgen import hooks, registry, runtime

    with registry.isolated(), hooks.isolated():
        result = render_project(Project.load(root, variant=kwargs.pop("variant", None)), **kwargs)
    runtime.clear_context()
    return result


@pytest.mark.render
def test_stills_at_beat_ends_match_the_video(capture_project: Path) -> None:
    root = capture_project
    build = root / "build" / "final"
    plain = render(root)
    assert plain.frames_index is None and not (build / "frames").exists()
    before = {sid: read_json(build / "timings" / f"{sid}.json") for sid in ("m", "q", "t")}
    lengths = {sid: len(decode_frames(build / "scenes" / f"{sid}.mp4")) for sid in ("m", "q", "t")}

    result = render(root, frames=1)
    assert result.frames_index == build / "frames" / "index.json" and result.rendered == ["m", "q", "t"]
    for sid in ("m", "q", "t"):  # capture changes neither the beat log nor the frames
        after = read_json(build / "timings" / f"{sid}.json")
        assert after["render"].pop("frames") == 1 and before[sid]["render"].pop("frames") == 0
        assert after == before[sid]
        assert len(decode_frames(build / "scenes" / f"{sid}.mp4")) == lengths[sid]

    index = read_json(build / "frames" / "m" / "index.json")
    assert (index["scene"], index["per_beat"], index["width"], index["height"], index["fps"]) == ("m", 1, 160, 90, FPS)
    beats = before["m"]["beats"]
    # the last frame of beat 1 is the one before beat 2 starts; beat 2 ends with the scene
    expected = [round(beats[1]["start"] * FPS) - 1, lengths["m"] - 1]
    assert [(f["beat"], f["k"], f["n"], f["frame"]) for f in index["frames"]] == [
        ("m_b1", 1, 1, expected[0]), ("m_b2", 1, 1, expected[1])]
    assert [f["path"] for f in index["frames"]] == ["m_b1-1.png", "m_b2-1.png"]
    assert index["frames"][0]["time"] == pytest.approx(expected[0] / FPS)
    video = decode_frames(build / "scenes" / "m.mp4")
    for still in index["frames"]:
        with Image.open(build / "frames" / "m" / still["path"]) as image:
            png = np.asarray(image.convert("RGB"), dtype=np.int16)
        assert png.shape == (90, 160, 3)
        diffs = [np.abs(png - frame.astype(np.int16)).mean() for frame in video]
        assert diffs[still["frame"]] < 3 and diffs[still["frame"]] <= min(diffs) + 0.5  # the pad holds the frame

    # listeners get the scene in the state of the captured frame
    seen = read_json(root / "seen.json")
    assert [(b, f) for b, f, _ in seen] == [("m_b1", expected[0]), ("m_b2", expected[1])]
    assert "Dot" in seen[0][2] and "Square" not in seen[0][2] and "Square" in seen[1][2]  # added when beat 2 starts
    # silent scene with an outro: one still before the fade-out, not a blank frame
    quiet = read_json(build / "frames" / "q" / "index.json")["frames"]
    assert [(f["beat"], f["k"], f["frame"]) for f in quiet] == [(None, 1, round(0.6 * FPS) - 1)]
    with Image.open(build / "frames" / "q" / "q-1.png") as image:
        assert np.asarray(image.convert("L")).max() > 200

    combined = read_json(result.frames_index)
    assert (combined["per_beat"], combined["preview"], combined["variant"]) == (1, False, None)
    assert combined["format"] == {"width": 160, "height": 90, "fps": FPS}
    timings = read_json(result.timings_file)
    for scene, timed in zip(combined["scenes"], timings["scenes"]):
        assert (scene["id"], scene["start"], scene["duration"]) == (timed["id"], timed["start"], timed["duration"])
        for still in scene["frames"]:
            assert still["time"] == pytest.approx(timed["start"] + still["scene_time"])
            assert (build / "frames" / still["path"]).is_file()
    assert combined["scenes"][2]["frames"][0]["path"] == "t/t_b1-1.png"

    # a render without frames removes the stills of the scenes it renders and the combined index
    render(root, scenes=["t"])
    assert not (build / "frames" / "t").exists() and not (build / "frames" / "index.json").exists()
    assert (build / "frames" / "m" / "index.json").is_file()


@pytest.mark.render
def test_n_stills_per_beat(capture_project: Path) -> None:
    root = capture_project
    result = render(root, frames=3, scenes=["m"], preview=True)
    build = root / "build" / "preview"
    timings = read_json(build / "timings" / "m.json")
    frames = read_json(build / "frames" / "m" / "index.json")["frames"]
    assert [(f["beat"], f["k"], f["n"]) for f in frames] == [("m_b1", k, 3) for k in (1, 2, 3)] + [("m_b2", k, 3) for k in (1, 2, 3)]
    index = [f["frame"] for f in frames]
    assert index == sorted(set(index))
    fps = 5
    b2_start = round(timings["beats"][1]["start"] * fps)
    assert index[2] == b2_start - 1 and index[0] < index[1] < b2_start - 1 and b2_start <= index[3]
    assert index[5] == round(timings["duration"] * fps) - 1
    video = decode_frames(build / "scenes" / "m.mp4")
    for still in frames[:2]:  # mid-beat stills while the dot moves: exactly that frame of the video
        with Image.open(build / "frames" / "m" / still["path"]) as image:
            png = np.asarray(image.convert("RGB"), dtype=np.int16)
        diffs = [np.abs(png - frame.astype(np.int16)).mean() for frame in video]
        assert int(np.argmin(diffs)) == still["frame"], diffs
    assert len(read_json(build / "frames" / "q" / "index.json")["frames"]) == 3
    assert sum(len(s["frames"]) for s in read_json(result.frames_index)["scenes"]) == 6 + 3 + 3


@pytest.mark.render
def test_frames_with_variant_scene_and_cli(capture_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = capture_project
    config = (root / "video.yaml").read_text(encoding="utf-8")
    (root / "video.yaml").write_text(
        config + "variants:\n  vertical:\n    preview: {width: 54, height: 96}\n", encoding="utf-8"
    )
    args = ["render", str(root), "--preview", "--variant", "vertical", "--no-audio"]
    assert main(args) == 0
    build = root / "build" / "preview_vertical"
    assert not (build / "frames").exists()
    capsys.readouterr()

    # --scene with stills: scenes rendered without stills are rendered again
    assert main([*args, "--scene", "t", "--frames"]) == 0
    out = capsys.readouterr().out
    assert "rendered 3 scene(s)" in out and f"frames:    {build / 'frames' / 'index.json'}" in out
    with Image.open(build / "frames" / "t" / "t_b1-1.png") as image:
        assert image.size == (54, 96)
    # now they have stills: only the selected scene is rendered
    assert main([*args, "--scene", "t", "--frames"]) == 0
    assert "rendered 1 scene(s), 2 reused" in capsys.readouterr().out
    # a different count is a different set of stills
    assert main([*args, "--scene", "t", "--frames-per-beat", "2"]) == 0
    assert "rendered 3 scene(s)" in capsys.readouterr().out
    combined = read_json(build / "frames" / "index.json")
    assert combined["variant"] == "vertical" and combined["per_beat"] == 2 and combined["preview"] is True
    assert [len(s["frames"]) for s in combined["scenes"]] == [4, 2, 2]


@pytest.mark.render
def test_frames_json_and_hooks(capture_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = capture_project
    hook = """
from pathlib import Path
from vidgen.api import *

@hook("post_scene")
def _scene(ctx):
    with open(ctx.project.root / "hooks.txt", "a", encoding="utf-8") as f:
        f.write(f"{ctx.data['scene_id']} {ctx.data['frames']}\\n")

@hook("post_render")
def _render(ctx):
    with open(ctx.project.root / "hooks.txt", "a", encoding="utf-8") as f:
        f.write(f"render {ctx.data['frames_index']}\\n")
"""
    (root / "extensions" / "hook_ext.py").write_text(hook, encoding="utf-8")
    code = main(["render", str(root), "--preview", "--json", "--no-audio", "--frames"])
    doc = json.loads(capsys.readouterr().out)
    assert code == 0
    index = root / "build" / "preview" / "frames" / "index.json"
    assert doc["outputs"]["frames"] == str(index.resolve()) and index.is_file()
    documented("frames")
    lines = (root / "hooks.txt").read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"m {root / 'build' / 'preview' / 'frames' / 'm'}"
    assert lines[-1] == f"render {index}"
