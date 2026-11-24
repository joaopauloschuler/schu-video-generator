"""``guide: canny`` and ``first_frame: restyled`` (DESIGN.md §113.21): the edges, the config, the
restyle job over a fake ComfyUI, and the inputs with their freshness."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from vidgen.config import ComfyuiSettings, GeneratedShot
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen import canny, comfyui, comfyui_client, qwen_graph
from vidgen.videogen.comfyui import HttpTransport, restyle_picture
from vidgen.videogen.comfyui_client import ComfyClient, job_outcome, run_job

LTX = "ltx-2.3-union-control"


# ----- the edges ---------------------------------------------------------------------------------


def _square(bright: int = 200) -> np.ndarray:
    gray = np.full((40, 120), 20, dtype=np.uint8)
    gray[10:30, 10:25] = bright   # a grey square on the left
    gray[:, 40:] = 250            # a bright (glint) band on the right, with a dark notch
    gray[18:22, 88:92] = 60
    return gray


def test_edges_find_outlines_with_hysteresis() -> None:
    e = canny.edges(_square())
    assert set(np.unique(e)) <= {0, 255}
    assert e[10:30, 9:11].any() and e[10:30, 24:26].any()   # the square's left and right sides
    assert not e[15:25, 14:21].any() and not e[0:5, 0:5].any()   # inside and far away: nothing
    assert not canny.edges(np.full((10, 10), 90, dtype=np.uint8)).any()


def test_the_glint_mask_removes_edges_in_bright_areas_only() -> None:
    gray = _square()
    plain, masked = canny.edges(gray), canny.glint_edges(gray)
    assert plain[16:24, 86:94].any() and not masked[16:24, 86:94].any()   # the notch inside the bright band
    assert (masked[10:30, 9:11] == plain[10:30, 9:11]).all()              # the square is kept
    assert (canny.glint_edges(gray, glint=None) == plain).all()


def test_rgb_to_gray_uses_opencvs_weights() -> None:
    frame = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]], dtype=np.uint8)
    assert canny.rgb_to_gray(frame).tolist() == [[76, 150, 29, 255]]


# ----- the config --------------------------------------------------------------------------------


def _shot(**kw: Any) -> GeneratedShot:
    return GeneratedShot(kind="establishing", model=LTX, **kw)


def test_canny_and_restyled_config() -> None:
    shot = _shot(guide="canny", first_frame="restyled", canny={"glint": False}, first_frame_prompt="make it real")
    assert shot.guide_source == "canny" and shot.canny_settings.glint is False and shot.canny_settings.low == 92
    assert _shot(guide="canny").canny_settings.glint == 150
    for bad, match in [({"guide": "final", "canny": {}}, "no guide: canny"), ({"first_frame": "render", "first_frame_prompt": "x"}, "restyled"),
                       ({"guide": "canny", "canny": {"glint": 300}}, "0-255"), ({"guide": "canny", "canny": {"glint": True}}, "0-255"),
                       ({"guide": "canny", "canny": {"low": 250}}, "not be above"), ({"guide": "cany"}, "did you mean canny")]:
        with pytest.raises(ValidationError, match=match):
            _shot(**bad)


# ----- the graph and the client ------------------------------------------------------------------


def test_qwen_graph_loads_the_named_picture_and_saves_one() -> None:
    g = qwen_graph.qwen_graph("vidgen_k_restyled", "p", 7, width=960, height=512, image="in.png", full=False)
    saves = [n for n in g.values() if n["class_type"] == "SaveImage"]
    assert [s["inputs"]["filename_prefix"] for s in saves] == ["vidgen_k_restyled"]
    assert g["7"]["inputs"]["image"] == "in.png" and g["15"]["inputs"]["seed"] == 7 and g["21"]["inputs"]["width"] == 960
    assert len([n for n in qwen_graph.qwen_graph("r").values() if n["class_type"] == "SaveImage"]) == 2


def _picture_history() -> dict[str, Any]:
    messages = [["execution_start", {"timestamp": 1000}], ["execution_success", {"timestamp": 26000}]]
    outputs = {"22": {"images": [{"filename": "vidgen_k_restyled_00001_.png", "subfolder": "", "type": "output"}]}}
    return {"status": {"status_str": "success", "completed": True, "messages": messages}, "outputs": outputs}


class PictureServer:
    """urlopen for a ComfyUI that makes one picture."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.prompts: list[dict[str, Any]] = []

    def __call__(self, request: Any, timeout: float) -> io.BytesIO:
        path = request.full_url.split("8188", 1)[1]
        self.calls.append(path.split("?")[0])
        if path == "/system_stats":
            return io.BytesIO(b"{}")
        if path == "/upload/image":
            return io.BytesIO(b'{"name": "x"}')
        if path == "/prompt":
            self.prompts.append(json.loads(request.data)["prompt"])
            return io.BytesIO(b'{"prompt_id": "p-1"}')
        if path.startswith("/history/"):
            return io.BytesIO(json.dumps({"p-1": _picture_history()}).encode())
        if path == "/free":
            assert json.loads(request.data) == {"unload_models": True, "free_memory": True}
            return io.BytesIO(b"")
        if path.startswith("/view?"):
            return io.BytesIO(b"PNGDATA")
        raise AssertionError(path)


def test_job_outcome_takes_a_picture_when_there_is_no_video() -> None:
    assert job_outcome(_picture_history())["output"]["filename"].endswith(".png")


def test_run_job_writes_the_named_output_and_frees_the_models(tmp_path: Path) -> None:
    server = PictureServer()
    job = {"url": "http://127.0.0.1:8188", "graph": {"1": {}}, "uploads": {}, "poll_seconds": 0, "output": "output.png", "free_after": True}
    (tmp_path / "job.json").write_text(json.dumps(job), encoding="utf-8")
    assert run_job(tmp_path / "job.json", client=ComfyClient(job["url"], opener=server), sleep=lambda s: None, say=lambda line: None)["status"] == "completed"
    assert (tmp_path / "output.png").read_bytes() == b"PNGDATA" and "/free" in server.calls


def test_restyle_picture_over_http_records_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sizes: list[tuple[int, int, bool]] = []

    def fake_fit(source: Path, dest: Path, *, width: int, height: int, lanczos: bool = False) -> Path:
        sizes.append((width, height, lanczos))
        dest.write_bytes(b"up")
        return dest

    monkeypatch.setattr(comfyui, "fit_picture", fake_fit)
    (tmp_path / "f.png").write_bytes(b"frame")
    server = PictureServer()
    transport = HttpTransport("http://127.0.0.1:8188", ComfyClient("http://127.0.0.1:8188", opener=server))
    usage = restyle_picture(ComfyuiSettings(url="http://127.0.0.1:8188"), tmp_path / "f.png", tmp_path / "out" / "r.png",
                            width=960, height=512, prompt="real", seed=42, transport=transport, sleep=lambda s: None)
    assert (tmp_path / "out" / "r.png").read_bytes() == b"PNGDATA" and sizes == [(1440, 768, True)]
    assert usage["gpu_seconds"] == 25.0 and usage["compute_units"] == round(25 * 1.94 / 3600, 4)
    assert server.calls.count("/free") == 1
    graph = server.prompts[0]
    assert graph["9"]["inputs"]["prompt"] == "real" and graph["21"]["inputs"]["height"] == 512


def test_colab_transport_downloads_the_jobs_own_output(tmp_path: Path) -> None:
    from test_videogen_comfyui import FakeColab

    class PictureColab(FakeColab):
        def download(self, remote: str, local: Path) -> None:
            assert remote.endswith("/output.png")
            local.write_bytes(b"PNG")

    fake = PictureColab([])
    transport = comfyui.ColabTransport(fake)  # type: ignore[arg-type]
    (tmp_path / "in.png").write_bytes(b"x")
    job_id = transport.submit(comfyui.PreparedJob({"1": {}}, {"in.png": tmp_path / "in.png"}, output="output.png", free_after=True))
    spec = json.loads(fake.archive["job.json"])
    assert spec["output"] == "output.png" and spec["free_after"] is True
    assert transport.download(job_id, tmp_path / "r.png") == 3
    assert comfyui_client.OUTPUT_NAME == "output.mp4"


# ----- the inputs and their freshness ------------------------------------------------------------


def _project(make_project, **shot: Any) -> Path:
    from conftest import minimal_config

    spec = {"kind": "establishing", "model": LTX, "guide": "canny", "first_frame": "restyled", **shot}
    data = minimal_config(
        videogen={"provider": "comfyui", "comfyui": {"url": "http://127.0.0.1:8188"}},
        scenes=[{"id": "s1", "type": "text_card", "params": {"text": "x"},
                 "beats": [{"id": "sea", "text": "Low over the open sea.", "generated_shot": spec}]}],
    )
    return make_project(data)


def _catalog() -> Any:
    from vidgen.videogen.models import Catalog

    return Catalog((), 0.0, "cache")


def test_plan_names_the_canny_guide_and_restyled_frame(make_project) -> None:
    from vidgen.videogen.shots import plan_shots

    project = Project.load(_project(make_project))
    (plan,) = plan_shots(project, catalog=_catalog()).shots
    names = [i.path.name for i in plan.shot.inputs]
    assert names == ["first_frame.restyled.png", "guide.canny.mp4"] and not plan.shot.problems
    assert any("vidgen generate inputs --guide" in b for b in plan.shot.blocked)
    assert "edge map" in plan.shot.prompt


def test_restyled_needs_the_comfyui_provider(make_project) -> None:
    from vidgen.videogen.shots import project_shots

    root = _project(make_project)
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["videogen"] = {"provider": "mock"}
    data["scenes"][0]["beats"][0]["generated_shot"].update(model="bytedance/seedance-2.0-fast", guide="final")
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (shot,) = project_shots(Project.load(root), _catalog())
    assert any("first_frame: restyled is made on the ComfyUI server" in p for p in shot.problems)


@pytest.mark.slow
def test_make_inputs_writes_canny_and_restyled_and_tracks_them(make_project, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import write_clip

    from vidgen.render.ffmpeg import probe
    from vidgen.videogen.inputs import SceneRender, make_inputs
    from vidgen.videogen.shots import plan_shots, project_shots

    root = _project(make_project)
    calls: list[dict[str, Any]] = []

    def fake_restyle(settings: Any, source: Path, dest: Path, **kw: Any) -> dict[str, Any]:
        calls.append(kw)
        dest.write_bytes(source.read_bytes())
        return {"gpu_seconds": 25.0, "compute_units": 0.0135}

    monkeypatch.setattr(comfyui, "restyle_picture", fake_restyle)
    clip = write_clip(root / "fake" / "s1.mp4", seconds=4.0, size="96x54", audio=False)

    def render(_project: Project, scene_id: str, passes: tuple[str, ...], kind: str = "render") -> SceneRender:
        assert kind == "final" and passes == ()
        return SceneRender(clip, {"sea": 0.0})

    def run(project: Project) -> list[str]:
        return [p.name for p in make_inputs(project, project_shots(project, _catalog()), guide=True, out=lambda line: None, render=render)]

    project = Project.load(root)
    assert run(project) == ["guide.canny.mp4", "first_frame.png", "first_frame.restyled.png", "overlay.png", "overlay.last.png"]
    folder = root / "build" / "videogen" / "sea"
    info = probe(folder / "guide.canny.mp4")
    assert (info.width, info.height) == (960, 512) and calls[0]["width"] == 960 and calls[0]["seed"] == 42
    record = json.loads((folder / "inputs.json").read_text(encoding="utf-8"))["inputs"]
    assert record["first_frame.restyled.png"]["usage"]["gpu_seconds"] == 25.0
    assert record["guide.canny.mp4"]["source"]["canny"] == [92, 200, 150]
    (plan,) = plan_shots(project, catalog=_catalog()).shots
    assert not plan.shot.blocked
    assert "first_frame.restyled.png" not in run(project) and len(calls) == 1   # kept: no second GPU job
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["scenes"][0]["beats"][0]["generated_shot"].update(canny={"glint": False}, first_frame_prompt="another look")
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (plan,) = plan_shots(Project.load(root), catalog=_catalog()).shots
    blocked = " ".join(plan.shot.blocked)
    assert "the canny settings changed" in blocked and "the restyle prompt, seed or size changed" in blocked


def test_a_failed_restyle_is_a_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comfyui, "fit_picture", lambda source, dest, **kw: dest.write_bytes(b"up") and dest)
    server = PictureServer()

    def failing(request: Any, timeout: float) -> io.BytesIO:
        if request.full_url.endswith("/history/p-1"):
            history = {"status": {"status_str": "error", "completed": False, "messages": [["execution_error", {"node_type": "UnetLoaderGGUF", "exception_message": "no file"}]]}}
            return io.BytesIO(json.dumps({"p-1": history}).encode())
        return server(request, timeout)

    (tmp_path / "f.png").write_bytes(b"frame")
    transport = HttpTransport("http://127.0.0.1:8188", ComfyClient("http://127.0.0.1:8188", opener=failing))
    with pytest.raises(VidgenError, match="restyle of f.png failed: UnetLoaderGGUF: no file"):
        restyle_picture(ComfyuiSettings(url="http://127.0.0.1:8188"), tmp_path / "f.png", tmp_path / "r.png",
                        width=960, height=512, prompt="p", seed=1, transport=transport, sleep=lambda s: None)
