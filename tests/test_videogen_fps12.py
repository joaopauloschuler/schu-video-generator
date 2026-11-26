"""A ComfyUI workflow shot generated at 12 fps (``fps: 12``) and doubled to 24 fps by RIFE in the
same job: the frame rules and limits, the graph, the config and request checks, the cache key, the
plan's frames line and the rule that splits a long beat."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_videogen_comfyui import no_ffmpeg  # noqa: F401  (a fixture)

from vidgen.config import GeneratedShot
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen import MediaInput, VideoRequest, canonical_request, comfyui, ltx_graph, request_hash
from vidgen.videogen.comfyui import WORKFLOWS, missing_weights_hint
from vidgen.videogen.models import check_request

LTX = "ltx-2.3-union-control"
WF = WORKFLOWS[LTX]


def test_frames_and_lengths_at_both_rates() -> None:
    assert WF.durations() == WF.durations(24) == (1, 2, 3, 4, 5) and WF.record().durations == (1, 2, 3, 4, 5)
    assert WF.durations(12) == (2, 4, 6, 8, 10) and WF.max_seconds_at(12) == 10 and WF.max_seconds == 5
    assert [WF.frames(s, 12) for s in (2, 4, 8, 10)] == [25, 49, 97, 121]
    assert WF.frames(4) == 97 and WF.frames(20, 12) == 121
    assert WF.stored_frames(49, 12) == 97 and WF.stored_frames(97, 12) == 193 and WF.stored_frames(97) == 97
    assert WF.lengths_text(24) == "1-5" and WF.lengths_text(12) == "2, 4, 6, 8, 10"


def _graph(fps: int | None, **kw: Any) -> dict[str, Any]:
    return WF.graph(control="c.mp4", first_frame=None, placeholder="f.png", prompt="", width=768, height=448, frames=97, seed=None,
                    prefix="vidgen_k", with_audio=True, fps=fps, **kw)


def test_the_graph_at_12_fps_runs_at_12_and_doubles_the_decoded_frames_to_24() -> None:
    for kw in ({}, {"sheet": "s.png"}):
        g = _graph(12, **kw)
        assert g["6"]["inputs"]["frame_rate"] == 12.0 and g["15"]["inputs"]["frame_rate"] == 12
        assert g["12"]["inputs"]["length"] == 97 and g["15"]["inputs"]["frames_number"] == 97
        assert g["50"] == {"class_type": "FrameInterpolationModelLoader", "inputs": {"model_name": ltx_graph.RIFE_MODEL}}
        assert g["51"] == {"class_type": "FrameInterpolate", "inputs": {"interp_model": ["50", 0], "images": ["24", 0], "multiplier": 2}}
        assert g["26"]["inputs"]["images"] == ["51", 0] and g["26"]["inputs"]["frame_rate"] == 24.0 and g["26"]["inputs"]["audio"] == ["25", 0]
        plain = _graph(None, **kw)
        assert plain == _graph(24, **kw) and "50" not in plain and "51" not in plain and plain["26"]["inputs"]["images"] == ["24", 0]
        assert plain["6"]["inputs"]["frame_rate"] == 24.0 and plain["26"]["inputs"]["frame_rate"] == 24.0
    assert _graph(12, sheet="s.png")["41"]["inputs"]["amount"] == 97
    with pytest.raises(ValueError, match="out_fps"):
        ltx_graph.graph(control_file="c", prefix="p", use_first_frame=False, fps=24, out_fps=36)


def _spec(**kw: Any) -> GeneratedShot:
    return GeneratedShot(**{"kind": "establishing", "model": LTX, "guide": "canny", **kw})


def test_the_config_takes_12_or_24_and_lengths_that_fit_the_rate() -> None:
    assert _spec(fps=12, duration=8).fps == 12 and _spec(fps=24, duration=5).duration == 5 and _spec().fps is None
    bad = [
        ({"fps": 30}, "generates at 12 or 24 fps, not 30"),
        ({"fps": 12, "duration": 5}, "2, 4, 6, 8, 10 s at 12 fps, not 5 s \\(61 frames, not 8k\\+1\\)"),
        ({"fps": 12, "duration": 12}, "not 12 s \\(145 frames, over its 121\\)"),
        ({"duration": 6}, "1-5 s at 24 fps, not 6 s"),
        ({"model": "bytedance/seedance-2.0-fast", "fps": 12}, "fps: is for vidgen's ComfyUI workflows"),
    ]
    for kw, match in bad:
        with pytest.raises(ValidationError, match=match):
            _spec(**kw)


def test_the_request_check_and_the_cache_key(tmp_path: Path) -> None:
    (tmp_path / "g.mp4").write_bytes(b"g")
    plain = VideoRequest(model=LTX, prompt="p", duration=8, references=(MediaInput("video", path=tmp_path / "g.mp4"),))
    assert "fps" not in canonical_request(plain) and "fps" not in canonical_request(replace(plain, duration=4))
    assert canonical_request(replace(plain, fps=12))["fps"] == 12 and request_hash(replace(plain, fps=12)) != request_hash(plain)
    model = WF.record()
    assert not check_request(replace(plain, fps=12), model).problems
    assert check_request(plain, model).problems == [f"{LTX} makes clips of 1-5 s at 24 fps, not 8 s (193 frames, over its 121)"]
    assert "generates at 12 or 24 fps, not 25" in check_request(replace(plain, fps=25), model).problems[0]
    assert "not 3 s" in check_request(replace(plain, fps=12, duration=3), model).problems[0]
    from vidgen.videogen.models import VideoModel

    other = VideoModel(id="a/b", name="b", durations=(5, 10))
    assert any("fps: is for vidgen's ComfyUI workflows" in p for p in check_request(VideoRequest(model="a/b", duration=5, fps=12), other).problems)
    with pytest.raises(VidgenError, match="fps must be"):
        VideoRequest(model=LTX, fps=0)


def test_prepare_job_fits_the_guide_at_12_fps(tmp_path: Path, no_ffmpeg: list[tuple[str, Path]]) -> None:  # noqa: F811
    (tmp_path / "guide.canny.mp4").write_bytes(b"canny")
    request = VideoRequest(model=LTX, duration=8, size="768x448", fps=12, references=(MediaInput("video", path=tmp_path / "guide.canny.mp4"),))
    job = comfyui.prepare_job(request, tmp_path, "k")
    assert json.loads(job.uploads["vidgen_k_control.mp4"].read_bytes()[7:]) == {"width": 768, "height": 448, "frames": 97, "fps": 12}
    assert job.graph["51"]["inputs"]["multiplier"] == 2 and job.graph["12"]["inputs"]["length"] == 97
    with pytest.raises(VidgenError, match="not 30"):
        comfyui.prepare_job(replace(request, fps=30), tmp_path, "k")


def test_a_missing_rife_file_gets_the_setup_hint() -> None:
    error = "ComfyUI refused the graph: Value not in list: model_name: 'rife_v4.26.safetensors' not in []"
    assert "setup_session.py NAME` again" in missing_weights_hint(error) and missing_weights_hint("boom") == "boom"


# ----- the shot and the plan ------------------------------------------------------------------


def _project(make_project: Any, pause: float, folder: str = "proj", **shot: Any) -> Path:
    from conftest import minimal_config

    spec = {"kind": "establishing", "model": LTX, "guide": "canny", "first_frame": "none", "size": "768x448", "line": False,
            "audio": "none", "prompt": "an escapement ticks", **shot}
    data = minimal_config(
        videogen={"provider": "comfyui", "comfyui": {"url": "http://127.0.0.1:8188"}},
        scenes=[{"id": "s1", "type": "text_card", "params": {"text": "x"},
                 "beats": [{"id": "tick", "text": "Tick.", "pause": pause, "generated_shot": spec}]}],
    )
    return make_project(data, folder=folder)


def _plan(root: Path) -> list[Any]:
    """The shots' plan entries without the plan's checks of inputs and the cache (cheap)."""
    from vidgen.videogen.models import Catalog
    from vidgen.videogen.shots import ShotPlan, project_shots

    return [ShotPlan(shot, shot.request()) for shot in project_shots(Project.load(root), Catalog((), 0.0, "cache"))]


def test_an_8_s_beat_is_one_clip_at_12_fps_and_two_at_24(make_project: Any) -> None:
    (at12,) = _plan(_project(make_project, 7.6, fps=12))
    shot = at12.shot
    assert abs(shot.length - 8.0) < 1e-6 and shot.duration == 8 and shot.parts == 1 and at12.request.fps == 12
    lines = at12.lines(Path("/"))
    assert "  length: 8 s" in lines
    assert ("  frames: 97 generated at 12 fps (at most 121: 2, 4, 6, 8, 10 s at 12 fps), doubled by RIFE in the same ComfyUI job "
            "to 193 at 24 fps") in lines
    at24 = _plan(_project(make_project, 7.6, folder="p24"))
    assert [p.shot.duration for p in at24] == [4, 4] and at24[0].request.fps is None
    assert "  frames: 97 at 24 fps (at most 121: 1-5 s at 24 fps)" in at24[0].lines(Path("/"))
    assert any("longest clip (5 s): split into 2 parts" in n for n in at24[0].shot.notes)
    long = _plan(_project(make_project, 11.6, folder="p12", fps=12))
    assert [p.shot.duration for p in long] == [6, 6] and any("longest clip at 12 fps (10 s): split into 2 parts" in n for n in long[0].shot.notes)


def test_fps_24_keeps_the_key_of_a_shot_without_it(make_project: Any) -> None:
    def request(folder: str, **shot: Any) -> VideoRequest:
        root = _project(make_project, 3.6, folder=folder, duration=4, **shot)
        guide = root / "build" / "videogen" / "tick" / "guide.canny.mp4"
        guide.parent.mkdir(parents=True)
        guide.write_bytes(b"canny")
        (entry,) = _plan(root)
        return entry.request

    plain, same, half = request("proj"), request("p24", fps=24), request("p12", fps=12)
    assert canonical_request(plain) == canonical_request(same)
    assert canonical_request(half) == {**canonical_request(plain), "fps": 12}
