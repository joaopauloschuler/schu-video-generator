"""Step 281: many crossfaded scenes are blended a batch at a time with the same frames (DESIGN.md §110)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.render import ffmpeg as ff

FPS, W, H = 10, 32, 18
COLORS = ["red", "green", "blue", "yellow", "white"]


def _clips(tmp_path: Path) -> tuple[list[Path], list[Path], list[int]]:
    exe = ff.find_ffmpeg()
    videos, audios, frames = [], [], []
    for k, color in enumerate(COLORS):
        video, audio, n = tmp_path / f"v{k}.mp4", tmp_path / f"a{k}.wav", 10 + k
        subprocess.run([exe, "-y", "-v", "error", "-f", "lavfi", "-i", f"color={color}:s={W}x{H}:r={FPS}:d={n / FPS}",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True)
        subprocess.run([exe, "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{n / FPS}", str(audio)], check=True)
        videos.append(video)
        audios.append(audio)
        frames.append(n)
    return videos, audios, frames


def _decoded(path: Path) -> np.ndarray:
    raw = subprocess.run([ff.find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, H, W, 3)


@pytest.mark.slow
def test_batched_blends_give_the_frames_of_one_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    videos, audios, frames = _clips(tmp_path)
    crossfades = [3, 0, 4, 2]   # a cut between the second and third
    outs = []
    for batch in (100, 2):
        monkeypatch.setattr(ff, "BLEND_BATCH", batch)
        work = tmp_path / f"work{batch}"
        work.mkdir()
        out = tmp_path / f"joined{batch}.mp4"
        ff.join(ff.find_ffmpeg(), videos, audios, out, work, crossfades=crossfades, frames=frames, fps=FPS)
        assert not list(work.glob("blend_*.mp4"))   # the intermediate videos are gone
        outs.append(_decoded(out))
    one, batched = outs
    assert len(one) == sum(frames) - sum(crossfades) == len(batched)
    assert int(np.abs(one.astype(int) - batched.astype(int)).max()) <= 2


@pytest.mark.slow
@pytest.mark.render
def test_a_crossfade_between_stage_scenes_does_not_dip_to_the_background(tmp_path: Path) -> None:
    """The set no longer fades in from its background colour after a crossfade: the frames
    across the boundary stay as bright as the scenes (a black background would show)."""
    import contextlib
    import io

    import yaml

    from vidgen import runtime
    from vidgen.cli import main
    from vidgen import registry

    root = tmp_path / "proj"
    root.mkdir()
    stage = {"background": "#000000", "ground_color": "#FFFFFF", "ground": 0.6, "characters": [{"name": "pip"}]}
    data = {
        "title": "t", "output": "out", "format": {"width": 160, "height": 90, "fps": FPS},
        "preview": {"width": 160, "height": 90, "fps": FPS}, "transition": "crossfade",
        "characters": [{"name": "pip", "look": {"body": "bean"}}],
        "scenes": [{"id": f"s{k}", "type": "stage", "params": stage, "duration": 1.5} for k in range(2)],
    }
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with registry.isolated(), contextlib.redirect_stdout(io.StringIO()):
        assert main(["render", str(root), "--preview", "--no-audio"]) == 0
    runtime.clear_context()
    frames = _decoded_size(root / "output" / "out_preview.mp4", 160, 90)
    means = frames.reshape(len(frames), -1).mean(axis=1)
    middle = means[len(means) // 2 - 4: len(means) // 2 + 4]
    assert middle.min() > 0.9 * means[len(means) // 2 - 6]


def _decoded_size(path: Path, width: int, height: int) -> np.ndarray:
    raw = subprocess.run([ff.find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width)
