"""A stylesheet for a shot (``sheet:``, ``sheet_prompt:``) with the base video in one LTX run, and
the clip keys ``size:`` / ``duration:`` of vidgen's ComfyUI workflow: the config, the graph of
trial run T2c, the prompt head, the compiler check, the models unloaded once per run, the
cache key and the take's record."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image
from pydantic import ValidationError
from test_videogen_comfyui import FakeColab, FakeServer, no_ffmpeg  # noqa: F401  (a fixture)

from vidgen.config import GeneratedShot
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen import MediaInput, VideoRequest, canonical_request, comfyui, ltx_graph, request_hash
from vidgen.videogen.comfyui import WORKFLOWS, ColabTransport, ComfyUIVideoProvider, HttpTransport
from vidgen.videogen.comfyui_client import ComfyClient

LTX = "ltx-2.3-union-control"
DATA = Path(__file__).parent / "data" / "ltx_graph"
URL = "http://127.0.0.1:8188"
PANELS = "top left, a grey glider from behind; bottom right, a rough open sea"


# ----- the graph ---------------------------------------------------------------------------------


def test_without_a_sheet_the_graph_is_what_it_was() -> None:
    """The graphs of Step 424's builder (saved in tests/data/ltx_graph/no_sheet.json, text encoder on
    ComfyUI's default device), byte for byte."""
    saved = json.loads((DATA / "no_sheet.json").read_text(encoding="utf-8"))
    wf = WORKFLOWS[LTX]
    now = {
        "default": ltx_graph.graph(control_file="c.mp4", prefix="p", use_first_frame=True, text_encoder="gpu"),
        "workflow_silent_no_first": wf.graph(control="vidgen_k_control.mp4", first_frame=None, placeholder="vidgen_k_first.png", prompt="a glider",
                                             width=768, height=448, frames=121, seed=7, prefix="vidgen_k", with_audio=False, text_encoder="gpu"),
        "workflow_first_audio": wf.graph(control="vidgen_k_control.mp4", first_frame="vidgen_k_first.png", placeholder="vidgen_k_first.png", prompt="",
                                         width=960, height=512, frames=73, seed=None, prefix="vidgen_k", with_audio=True, text_encoder="gpu"),
    }
    for name, graph in now.items():
        assert json.dumps(graph) == json.dumps(saved[name]), name


def test_with_a_sheet_the_graph_is_the_one_of_trial_run_T2c() -> None:
    """The graph sent in run T2c (trial2/graphs/T2c_multi_nocompiler_768_25.json), node for node."""
    t2c = json.loads((DATA / "T2c_multi_nocompiler_768_25.json").read_text(encoding="utf-8"))
    graph = ltx_graph.graph(control_file="trial2_canny_25_768x448.mp4", prefix="t2_T2c_multi_nocompiler_768_25", use_first_frame=False,
                            prompt=t2c["4"]["inputs"]["text"], width=768, height=448, frames=25, seed=42,
                            first_frame_file="trial2_first_768x448.png", with_audio=False, sheet_file="trial2_sheet_768x448.png",
                            text_encoder="gpu")
    assert graph == t2c
    assert t2c["2"]["class_type"] == "LTXMultiICLoRA" and t2c["41"]["inputs"]["amount"] == 25
    with pytest.raises(ValueError, match="one control video"):
        ltx_graph.graph(control_file="c.mp4", prefix="p", use_first_frame=False, second_control_file="d.mp4", sheet_file="s.png")


# ----- the config --------------------------------------------------------------------------------


def _spec(**kw: Any) -> GeneratedShot:
    return GeneratedShot(**{"kind": "establishing", "model": LTX, "guide": "canny", **kw})


def test_sheet_size_and_duration_config() -> None:
    spec = _spec(sheet="sheets/glider.png", sheet_prompt=PANELS, size="768x448", duration=5, first_frame="none")
    assert spec.sheet == "sheets/glider.png" and WORKFLOWS[LTX].size("16:9", spec.size) == (768, 448)
    assert WORKFLOWS[LTX].size("16:9") == (960, 512) and WORKFLOWS[LTX].frames(5) == 121 and WORKFLOWS[LTX].frames(1) == 25
    bad = [
        ({"sheet_prompt": PANELS}, "no sheet:"),
        ({"sheet": "s.png"}, "needs sheet_prompt"),
        ({"model": "bytedance/seedance-2.0-fast", "sheet": "s.png", "sheet_prompt": PANELS}, "ltx-2.3-union-control"),
        ({"size": "770x448"}, "multiples of 64"),
        ({"size": "768x448", "resolution": "512p"}, "not both"),
        ({"model": "a/b", "size": "768x448"}, "ComfyUI workflows"),
        ({"model": "a/b", "duration": 2}, "ComfyUI workflows"),
        ({"duration": 6}, "1-5 s"),
    ]
    for kw, match in bad:
        with pytest.raises(ValidationError, match=match):
            _spec(**kw)


# ----- the shot ----------------------------------------------------------------------------------


def _project(make_project: Any, size: tuple[int, int] = (768, 448), folder: str = "proj", **shot: Any) -> Path:
    from conftest import minimal_config

    spec = {"kind": "establishing", "model": LTX, "guide": "canny", "first_frame": "none", "size": "768x448", "line": False,
            "sheet": "sheets/glider.png", "sheet_prompt": PANELS, "prompt": "a grey glider flies low over the sea", **shot}
    data = minimal_config(
        videogen={"provider": "comfyui", "comfyui": {"url": URL}},
        scenes=[{"id": "s1", "type": "text_card", "params": {"text": "x"},
                 "beats": [{"id": "sea", "text": "Low over the open sea.", "generated_shot": spec}]}],
    )
    root = make_project(data, folder=folder)
    (root / "sheets").mkdir()
    Image.new("RGB", size, (40, 60, 90)).save(root / "sheets" / "glider.png")
    return root


def _shot(root: Path) -> Any:
    from vidgen.videogen.models import Catalog
    from vidgen.videogen.shots import project_shots

    (shot,) = project_shots(Project.load(root), Catalog((), 0.0, "cache"))
    return shot


def test_a_shot_with_a_sheet_sends_it_and_starts_its_prompt_with_the_panels(make_project: Any) -> None:
    root = _project(make_project, duration=1)
    shot = _shot(root)
    assert not shot.problems and shot.sheet == root / "sheets" / "glider.png"
    assert shot.prompt.startswith(f"Reference sheet: {PANELS}. Generated video: Establishing shot: a grey glider flies low over the sea.")
    guide = root / "build" / "videogen" / "sea" / "guide.canny.mp4"
    guide.parent.mkdir(parents=True)
    guide.write_bytes(b"canny")
    request = shot.request()
    assert request.sheet == MediaInput("image", path=shot.sheet) and request.size == "768x448" and request.resolution is None
    assert request.duration == 1 and not request.frame_images and [r.kind for r in request.references] == ["video"]
    key = request_hash(request)
    Image.new("RGB", (768, 448), (90, 60, 40)).save(root / "sheets" / "glider.png")   # another sheet: another clip
    assert request_hash(_shot(root).request()) != key
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["scenes"][0]["beats"][0]["generated_shot"]["sheet_prompt"] = "the glider from above"
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert "Reference sheet: the glider from above. Generated" in _shot(root).prompt


def test_a_sheet_must_exist_and_have_the_clips_aspect_ratio(make_project: Any) -> None:
    assert any("glider.png is 960x512, the clip 768x448" in p for p in _shot(_project(make_project, size=(960, 512))).problems)
    missing = _project(make_project, folder="missing", sheet="sheets/none.png")
    assert any(".sheet: no picture sheets/none.png" in p for p in _shot(missing).problems)


def test_without_a_sheet_the_request_and_its_key_are_as_before(tmp_path: Path) -> None:
    (tmp_path / "g.mp4").write_bytes(b"g")
    plain = VideoRequest(model=LTX, prompt="p", duration=3, references=(MediaInput("video", path=tmp_path / "g.mp4"),))
    (tmp_path / "s.png").write_bytes(b"png")
    assert "sheet" not in canonical_request(plain)
    assert canonical_request(replace(plain, sheet=MediaInput("image", path=tmp_path / "s.png")))["sheet"]["bytes"] == 3


# ----- the job -----------------------------------------------------------------------------------


def _request(tmp_path: Path) -> VideoRequest:
    (tmp_path / "guide.canny.mp4").write_bytes(b"canny")
    Image.new("RGB", (768, 448)).save(tmp_path / "sheet.png")
    return VideoRequest(model=LTX, prompt="Reference sheet: x. Generated video: y", duration=5, size="768x448", aspect_ratio="16:9",
                        references=(MediaInput("video", path=tmp_path / "guide.canny.mp4"),), sheet=MediaInput("image", path=tmp_path / "sheet.png"))


def test_prepare_job_sends_the_sheet_at_the_clips_size(tmp_path: Path, no_ffmpeg: list[tuple[str, Path]]) -> None:  # noqa: F811
    job = comfyui.prepare_job(_request(tmp_path), tmp_path, "k")
    assert set(job.uploads) == {"vidgen_k_control.mp4", "vidgen_k_first.png", "vidgen_k_sheet.png"}
    assert json.loads(job.uploads["vidgen_k_control.mp4"].read_bytes()[7:]) == {"width": 768, "height": 448, "frames": 121, "fps": 24}
    g = job.graph
    assert g["40"]["inputs"]["image"] == "vidgen_k_sheet.png" and g["41"]["inputs"]["amount"] == 121 and g["12"]["inputs"]["length"] == 121
    assert g["13"]["inputs"]["bypass"] is True and g["2"]["class_type"] == "LTXMultiICLoRA"


def _provider(server: FakeServer) -> ComfyUIVideoProvider:
    return ComfyUIVideoProvider(HttpTransport(URL, ComfyClient(URL, opener=server)), poll_seconds=0, sleep=lambda s: None)


def test_a_sheet_runs_only_with_the_model_compiler_off(tmp_path: Path, no_ffmpeg: list[tuple[str, Path]]) -> None:  # noqa: F811
    for argv in (["main.py", "--listen", "127.0.0.1"], None):
        server = FakeServer(argv=argv)
        with pytest.raises(VidgenError, match="--disable-comfy-compiler") as err:
            _provider(server).submit(_request(tmp_path))
        assert not server.prompts and "/free" not in server.calls
        assert ("runs with the model compiler on" in str(err.value)) == (argv is not None)
    server = FakeServer(argv=["main.py", "--disable-comfy-compiler"])
    assert _provider(server).submit(_request(tmp_path)).status == "pending" and len(server.prompts) == 1
    plain = VideoRequest(model=LTX, duration=1, references=(MediaInput("video", path=tmp_path / "guide.canny.mp4"),))
    server = FakeServer()   # no sheet: whatever the compiler setting, not even asked
    _provider(server).submit(plain)
    assert "/system_stats" not in server.calls and len(server.prompts) == 1


def test_over_colab_the_check_names_the_setup_command(tmp_path: Path, no_ffmpeg: list[tuple[str, Path]]) -> None:  # noqa: F811
    class StateColab(FakeColab):
        args: list[str] | None = ["--listen", "127.0.0.1", "--port", "8188"]

        def vm(self, action: str, **env: str) -> dict[str, Any]:
            if action == "state":
                self.actions.append((action, env))
                return {"comfy": {"args": self.args}}
            return super().vm(action, **env)

    fake = StateColab([])
    provider = ComfyUIVideoProvider(ColabTransport(fake))  # type: ignore[arg-type]
    with pytest.raises(VidgenError, match="setup_session.py ltx --no-comfy-compiler` \\(it restarts ComfyUI"):
        provider.submit(_request(tmp_path))
    assert [a for a, _ in fake.actions] == ["state"]
    fake.args = [*fake.args, "--disable-comfy-compiler"]
    provider.submit(_request(tmp_path))
    assert [a for a, _ in fake.actions] == ["state", "state", "begin"] and json.loads(fake.archive["job.json"])["free_before"] is True


def test_the_models_are_unloaded_once_before_the_first_job(tmp_path: Path, no_ffmpeg: list[tuple[str, Path]]) -> None:  # noqa: F811
    from vidgen.videogen.comfyui_client import run_job

    server = FakeServer(argv=["--disable-comfy-compiler"])
    provider = _provider(server)
    provider.submit(_request(tmp_path))
    provider.submit(_request(tmp_path))
    assert server.calls.count("/free") == 1 and server.calls.index("/free") < server.calls.index("/upload/image")
    (tmp_path / "job.json").write_text(json.dumps({"url": URL, "graph": {}, "poll_seconds": 0, "free_before": True}), encoding="utf-8")
    server = FakeServer(polls=0)
    lines: list[str] = []
    run_job(tmp_path / "job.json", client=ComfyClient(URL, opener=server), sleep=lambda s: None, say=lines.append)
    assert server.calls[0] == "/free" and "unloaded the models (POST /free)" in lines


def test_the_take_names_its_sheet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.videogen import qa
    from vidgen.videogen.takes import add_take

    class Report:
        def to_json(self) -> dict[str, Any]:
            return {"summary": "QA ok"}

    monkeypatch.setattr(qa, "check_clip", lambda *a, **k: Report())
    monkeypatch.setattr(qa, "contact_sheet", lambda *a, **k: None)
    (tmp_path / "clip.mp4").write_bytes(b"mp4")
    take, new = add_take(tmp_path, "sea", tmp_path / "clip.mp4", key="k", model=LTX, provider="comfyui", job_id="j", cost=0.0,
                         length=5.0, width=768, height=448, sheet=tmp_path / "sheets" / "glider.png")
    assert new and take.info["sheet"] == "sheets/glider.png"
    assert json.loads(take.path.with_suffix(".json").read_text(encoding="utf-8"))["sheet"] == "sheets/glider.png"


def test_a_paid_run_on_comfyui_uses_one_provider(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """One provider for the whole run: the models are unloaded before its first job only."""
    from vidgen.videogen import run
    from vidgen.videogen.models import Catalog
    from vidgen.videogen.workflow import run_shots

    made: list[Any] = []
    monkeypatch.setattr(run, "get_provider", lambda settings: made.append(settings) or object())
    report = run_shots(Project.load(_project(make_project)), pay=True, catalog=Catalog((), 0.0, "cache"), out=lambda line: None)
    assert [s.status for s in report.shots] == ["blocked"] and len(made) == 1


def test_on_the_colab_vm_the_check_reads_what_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from vidgen import colab_vm
    from vidgen.config import ComfyuiSettings

    monkeypatch.setattr(comfyui, "VM_MARKER", tmp_path / "marker")
    (tmp_path / "marker").write_text("x", encoding="utf-8")
    args: list[list[str] | None] = [["--listen", "127.0.0.1", "--port", "8188"]]
    monkeypatch.setattr(colab_vm, "comfy_args", lambda: args[0])
    transport = comfyui.make_transport(ComfyuiSettings(colab="g4"), poll_timeout=9)
    assert isinstance(transport, HttpTransport) and transport.compiler_off() is False
    assert "setup_session.py g4 --no-comfy-compiler` on your computer" in transport.compiler_fix
    args[0] = [*args[0][:4], "--disable-comfy-compiler"]
    assert transport.compiler_off() is True
    args[0] = None
    assert transport.compiler_off() is None
