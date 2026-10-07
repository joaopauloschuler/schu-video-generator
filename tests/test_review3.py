"""Review 3 (Step 48): narration level in renders, lower thirds making way for captions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import tempconfig

from test_captions import load, narrated
from test_overlays import FPS
from vidgen import extensions
from vidgen.overlays import build_overlays, mobject_region, scene_overlays
from vidgen.render.worker import frame_size
from vidgen.scene import add_narration
from vidgen.sfx import decode_audio, read_wav
from vidgen.videoplan import VideoPlan

ROOT = Path(__file__).resolve().parents[1]
KPHI3_MP3 = ROOT / "examples" / "kphi3" / "audio" / "s1_b1.mp3"


def _db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64)))))


@pytest.mark.skipif(not KPHI3_MP3.is_file(), reason="no kphi3 audio")
def test_mono_narration_plays_at_its_own_level_on_both_channels() -> None:
    """Manim's own MP3 conversion upmixed mono narration 3 dB down; vidgen hands it a WAV."""

    class Recorder:
        def add_sound(self, path: str) -> None:
            self.data = read_wav(Path(path))
            self.path = Path(path)

    scene = Recorder()
    add_narration(scene, KPHI3_MP3)  # type: ignore[arg-type]
    source = decode_audio(KPHI3_MP3)
    assert source.shape[1] == 1 and scene.data.shape == (len(source), 2)
    assert np.array_equal(scene.data[:, 0], scene.data[:, 1])
    assert _db(scene.data[:, 0]) == pytest.approx(_db(source[:, 0]), abs=0.01)
    assert not scene.path.exists()  # a temporary file


def test_probe_counts_frames_at_the_nominal_rate(tmp_path: Path) -> None:
    """Manim's joined partial movies have timestamps whose average rate is not exactly the fps;
    the join must still see ``frames / fps`` seconds (else starts and audio drift)."""
    import shutil
    import subprocess

    import av

    from vidgen.render.ffmpeg import probe

    clean = tmp_path / "clean.mp4"
    subprocess.run(
        [shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=64x36:r=15:d=2",
         "-c:v", "libx264", "-g", "1", "-bf", "0", "-pix_fmt", "yuv420p", "-video_track_timescale", "15360", str(clean)],
        check=True, capture_output=True,
    )
    path = tmp_path / "irregular.mp4"
    with av.open(str(clean)) as src, av.open(str(path), "w") as out:
        stream = out.add_stream_from_template(src.streams.video[0])
        for k, packet in enumerate(p for p in src.demux(src.streams.video[0]) if p.size):
            if k >= 15:   # a seam 5 ticks short, as between Manim's partial movies
                packet.pts -= 5
                packet.dts -= 5
            packet.stream = stream
            out.mux(packet)
    with av.open(str(path)) as c:
        assert c.streams.video[0].average_rate != 15   # the situation being tested
    assert probe(path).duration == pytest.approx(2.0, abs=1e-9) and probe(path).fps == 15


def _built(project: Any, scene_id: str, size: tuple[int, int]) -> dict[str, Any]:
    w, h = size
    fw, fh = frame_size(w, h)
    with tempconfig({"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": FPS}):
        theme = extensions.activate(project)
        overlays = scene_overlays(project, project.scene(scene_id), theme, VideoPlan(project, FPS))
        mobjects = build_overlays(overlays)
    return {o.id: (o, mobject_region(m)) for o, m in zip(overlays, mobjects)}


@pytest.mark.parametrize("size", [(320, 180), (180, 320)], ids=["16:9", "9:16"])
def test_lower_third_makes_way_for_bottom_captions(make_project, size: tuple[int, int]) -> None:
    lower = {"type": "lower_third", "scene": "a", "name": "Ada Lovelace", "title": "Mathematician", "align": "bottom"}
    project = load(make_project, [narrated("a", "A beat that is long enough to need two lines of captions here.")], [{"type": "captions"}, lower])
    found = _built(project, "a", size)
    (_, band), (third, box) = found["captions"], found["lower_third"]
    assert third.clear_of == [band]   # built after the captions, knowing their band
    assert box.y0 >= band.y1 + 0.2 - 1e-6   # above it, with the reserve gap
    # without captions it sits where it always did (lower in the safe area)
    alone = _built(load(make_project, [narrated("a", "A beat.")], [lower], ), "a", size)["lower_third"][1]
    assert alone.y0 < box.y0


def test_lower_third_stays_put_when_nothing_is_in_the_way(make_project) -> None:
    lower = {"type": "lower_third", "scene": "a", "name": "Ada", "align": "bottom_left"}
    mark = {"type": "watermark", "text": "vidgen", "reserve": True}   # bottom right: not in its way
    project = load(make_project, [narrated("a", "A beat.")], [mark, lower])
    with_mark = _built(project, "a", (320, 180))["lower_third"][1]
    alone = _built(load(make_project, [narrated("a", "A beat.")], [lower]), "a", (320, 180))["lower_third"][1]
    assert with_mark == alone
