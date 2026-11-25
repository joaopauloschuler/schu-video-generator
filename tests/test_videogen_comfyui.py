"""The comfyui video provider (vidgen.videogen.comfyui, comfyui_client, ltx_graph): config, the
workflow's shape rules, the HTTP client against a fake server, both transports, cost and usage."""
from __future__ import annotations

import io
import json
import tarfile
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from vidgen.config import ComfyuiSettings, GeneratedShot, VideogenConfig
from vidgen.errors import VidgenError
from vidgen.videogen import JobState, MediaInput, VideoRequest, request_hash
from vidgen.videogen import comfyui, comfyui_client, ltx_graph
from vidgen.videogen.comfyui import WORKFLOWS, ColabTransport, ComfyUIVideoProvider, HttpTransport, PreparedJob, guide_problem
from vidgen.videogen.comfyui_client import ComfyClient, ComfyError, job_outcome, run_job
from vidgen.videogen.ledger import BudgetState, refusal
from vidgen.videogen.models import Catalog, check_request, estimate, model_line
from vidgen.videogen.run import ledger_path

LTX = "ltx-2.3-union-control"
WF = WORKFLOWS[LTX]


def _history(status: str = "success", *, error: str | None = None) -> dict[str, Any]:
    messages: list[Any] = [["execution_start", {"timestamp": 1_000_000}]]
    if status == "success":
        messages.append(["execution_success", {"timestamp": 1_266_200}])
        outputs = {"10": {"images": [{"filename": "c.mp4", "subfolder": "", "type": "input"}]},
                   "26": {"gifs": [{"filename": "vidgen_k_00001.mp4", "subfolder": "", "type": "output"}]}}
        return {"status": {"status_str": "success", "completed": True, "messages": messages}, "outputs": outputs}
    messages.append(["execution_error", {"timestamp": 1_010_000, "node_type": "LoadVideo", "exception_message": error or "boom\n"}])
    return {"status": {"status_str": "error", "completed": False, "messages": messages}, "outputs": {}}


# ----- config ------------------------------------------------------------------------------------


def test_config_takes_exactly_one_server_and_needs_it_for_comfyui() -> None:
    assert VideogenConfig(provider="comfyui", comfyui={"colab": "ltx"}).comfyui.units_per_hour == 1.94
    assert VideogenConfig(provider="comfyui", comfyui={"url": "http://127.0.0.1:8188"}).comfyui.url
    with pytest.raises(ValidationError, match="exactly one of colab"):
        ComfyuiSettings(colab="ltx", url="http://x:1")
    with pytest.raises(ValidationError, match="exactly one of colab"):
        ComfyuiSettings()
    with pytest.raises(ValidationError, match="needs videogen.comfyui"):
        VideogenConfig(provider="comfyui")
    with pytest.raises(ValidationError, match="url"):
        ComfyuiSettings(url="127.0.0.1:8188")


def test_a_workflow_is_a_model_id_of_a_shot_and_of_videogen_models() -> None:
    assert GeneratedShot(kind="establishing", model=LTX, guide="depth").model == LTX
    assert LTX in VideogenConfig(models={LTX: {}}).models
    with pytest.raises(ValidationError, match="ltx-2.3-union-control"):
        GeneratedShot(kind="establishing", model="ltx-9")


# ----- the workflow ------------------------------------------------------------------------------


def test_shape_rules_sizes_and_frames() -> None:
    assert WF.size("16:9") == (960, 512) and WF.size("9:16") == (512, 960) and WF.size("1:1") == (512, 512)
    assert WF.size(None) == (960, 512)
    assert [WF.frames(s) for s in (1, 3, 5, 9)] == [25, 73, 121, 121]
    assert all((f - 1) % 8 == 0 for f in (WF.frames(s / 10) for s in range(1, 60)))


def test_workflow_record_lists_free_and_is_found_in_any_catalog() -> None:
    catalog = Catalog((), 0.0, "cache")
    model = catalog.find(LTX)
    assert model.provider == "comfyui" and model.durations == (1, 2, 3, 4, 5) and model.resolutions == ("512p",)
    assert "$0" in model_line(model)
    with pytest.raises(VidgenError, match="no workflow"):
        catalog.find("ltx-9")


def test_check_estimate_and_guide_rules(tmp_path: Path) -> None:
    model = WF.record()
    guide = MediaInput("video", path=tmp_path / "g.mp4")
    ok = VideoRequest(model=LTX, duration=3, resolution="512p", references=(guide, MediaInput("image", path=tmp_path / "r.png")))
    check = check_request(ok, model)
    assert not check.problems and "not sent" in check.notes[0]
    bad = check_request(VideoRequest(model=LTX, duration=7, resolution="480p"), model)
    assert len(bad.problems) == 3
    assert estimate(ok, model).cost == 0.0
    assert guide_problem(LTX, "depth") is None and guide_problem(LTX, "canny") is None
    assert "guide: canny or depth" in (guide_problem(LTX, "final") or "")
    assert guide_problem("bytedance/seedance-2.0-fast", "final") is None


def test_a_free_job_needs_no_budget_a_paid_one_does() -> None:
    assert refusal(BudgetState(None, 0.0), 0.0, LTX) is None
    assert "needs a budget" in (refusal(BudgetState(None, 0.0), 0.1, "a/b") or "")


def test_graph_shape_checks_and_silent_output() -> None:
    graph = ltx_graph.graph(control_file="c.mp4", prefix="p", use_first_frame=True)
    assert graph["26"]["inputs"]["audio"] == ["25", 0] and graph["12"]["inputs"]["length"] == 121
    silent = WF.graph(control="c.mp4", first_frame=None, placeholder="f.png", prompt="", width=896, height=512, frames=49, seed=None,
                      prefix="vidgen_k", with_audio=False)
    assert "25" not in silent and "audio" not in silent["26"]["inputs"]
    assert silent["13"]["inputs"]["bypass"] is True and silent["9"]["inputs"]["image"] == "f.png"
    assert silent["17"]["inputs"]["noise_seed"] == 42 and silent["4"]["inputs"]["text"] == ltx_graph.PROMPT
    with pytest.raises(ValueError, match="multiples of 64"):
        ltx_graph.graph(control_file="c", prefix="p", use_first_frame=False, width=900)
    with pytest.raises(ValueError, match="8k\\+1"):
        ltx_graph.graph(control_file="c", prefix="p", use_first_frame=False, frames=120)


def test_ledger_of_comfyui_is_its_own(tmp_path: Path) -> None:
    assert ledger_path(tmp_path, "comfyui").name == "videogen-ledger.comfyui.jsonl"
    assert ledger_path(tmp_path, "openrouter").name == "videogen-ledger.jsonl"


# ----- the HTTP client ---------------------------------------------------------------------------


class FakeServer:
    """urlopen for a ComfyUI that queues one prompt and finishes it after ``polls`` history calls."""

    def __init__(self, polls: int = 1, outcome: dict[str, Any] | None = None, argv: list[str] | None = None) -> None:
        self.polls = polls
        self.outcome = outcome or _history()
        self.uploads: dict[str, bytes] = {}
        self.prompts: list[dict[str, Any]] = []
        self.down = False
        self.argv = argv
        self.calls: list[str] = []

    def __call__(self, request: Any, timeout: float) -> io.BytesIO:
        if self.down:
            raise urllib.error.URLError("connection refused")
        path = request.full_url.split("8188", 1)[1]
        self.calls.append(path.split("?")[0])
        if path == "/system_stats":
            return io.BytesIO(json.dumps({"system": {} if self.argv is None else {"argv": self.argv}}).encode())
        if path == "/free":
            return io.BytesIO(b"")
        if path == "/upload/image":
            body = request.data
            name = body.split(b'filename="', 1)[1].split(b'"', 1)[0].decode()
            self.uploads[name] = body.split(b"\r\n\r\n")[2].rsplit(b"\r\n--", 1)[0]
            return io.BytesIO(json.dumps({"name": name, "subfolder": "", "type": "input"}).encode())
        if path == "/prompt":
            self.prompts.append(json.loads(request.data)["prompt"])
            return io.BytesIO(b'{"prompt_id": "p-1", "number": 0}')
        if path.startswith("/history/"):
            if self.polls > 0:
                self.polls -= 1
                return io.BytesIO(b"{}")
            return io.BytesIO(json.dumps({"p-1": self.outcome}).encode())
        if path.startswith("/view?"):
            assert "filename=vidgen_k_00001.mp4" in path and "type=output" in path
            return io.BytesIO(b"MP4DATA")
        raise AssertionError(path)


def test_job_outcome_reads_success_error_and_running() -> None:
    done = job_outcome(_history())
    assert done["status"] == "completed" and done["seconds"] == 266.2 and done["output"]["filename"] == "vidgen_k_00001.mp4"
    failed = job_outcome(_history("error", error="no file c.mp4"))
    assert failed["status"] == "failed" and failed["error"] == "LoadVideo: no file c.mp4"
    assert job_outcome(None)["status"] == "running"
    assert job_outcome({"status": {"status_str": "success", "messages": []}, "outputs": {}})["status"] == "failed"


def test_run_job_uploads_submits_polls_and_downloads(tmp_path: Path) -> None:
    server = FakeServer(polls=2)
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "c.mp4").write_bytes(b"control")
    job = {"url": "http://127.0.0.1:8188", "graph": {"1": {}}, "uploads": {"c.mp4": "inputs/c.mp4"}, "poll_seconds": 0}
    (tmp_path / "job.json").write_text(json.dumps(job), encoding="utf-8")
    lines: list[str] = []
    result = run_job(tmp_path / "job.json", client=ComfyClient(job["url"], opener=server), sleep=lambda s: None, say=lines.append)
    assert result["status"] == "completed" and result["prompt_id"] == "p-1"
    assert server.uploads == {"c.mp4": b"control"} and server.prompts == [{"1": {}}]
    assert (tmp_path / comfyui_client.OUTPUT_NAME).read_bytes() == b"MP4DATA"
    assert any("done in 266.2 s" in line for line in lines)


def test_client_errors_are_clear() -> None:
    server = FakeServer()
    server.down = True
    with pytest.raises(ComfyError, match="no ComfyUI at http://127.0.0.1:8188"):
        ComfyClient("http://127.0.0.1:8188", opener=server).system_stats()
    with pytest.raises(VidgenError, match="start ComfyUI there"):
        HttpTransport("http://127.0.0.1:8188", ComfyClient("http://127.0.0.1:8188", opener=server)).check()


# ----- the provider through both transports ------------------------------------------------------


@pytest.fixture()
def no_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Path]]:
    """Fitting writes marker files instead of running FFmpeg."""
    fitted: list[tuple[str, Path]] = []

    def fake_control(source: Path, dest: Path, **kw: Any) -> Path:
        fitted.append(("control", source))
        dest.write_bytes(b"fitted " + json.dumps(kw).encode())
        return dest

    def fake_picture(source: Path, dest: Path, **kw: Any) -> Path:
        fitted.append(("picture", source))
        dest.write_bytes(b"png")
        return dest

    monkeypatch.setattr(comfyui, "fit_control", fake_control)
    monkeypatch.setattr(comfyui, "fit_picture", fake_picture)
    return fitted


def _request(tmp_path: Path, *, first: bool = True) -> VideoRequest:
    (tmp_path / "guide.depth.mp4").write_bytes(b"depth")
    (tmp_path / "first.png").write_bytes(b"first")
    frames = (MediaInput("image", path=tmp_path / "first.png", frame_type="first_frame"),) if first else ()
    return VideoRequest(model=LTX, prompt="a glider", duration=3, resolution="512p", aspect_ratio="16:9", seed=7,
                        frame_images=frames, references=(MediaInput("video", path=tmp_path / "guide.depth.mp4"),))


def test_prepare_job_fits_inputs_and_names_them_by_key(tmp_path: Path, no_ffmpeg: list[tuple[str, Path]]) -> None:
    job = comfyui.prepare_job(_request(tmp_path), tmp_path, "k")
    assert set(job.uploads) == {"vidgen_k_control.mp4", "vidgen_k_first.png"}
    assert json.loads(job.uploads["vidgen_k_control.mp4"].read_bytes()[7:]) == {"width": 960, "height": 512, "frames": 73, "fps": 24}
    g = job.graph
    assert g["10"]["inputs"]["file"] == "vidgen_k_control.mp4" and g["13"]["inputs"]["bypass"] is False
    assert g["17"]["inputs"]["noise_seed"] == 7 and g["26"]["inputs"]["filename_prefix"] == "vidgen_k" and "25" not in g
    no_first = comfyui.prepare_job(_request(tmp_path, first=False), tmp_path, "k")
    assert no_first.graph["13"]["inputs"]["bypass"] is True and no_ffmpeg[-1] == ("picture", no_first.uploads["vidgen_k_control.mp4"])


def test_generate_clip_over_http_records_usage_and_costs_nothing(tmp_path: Path, no_ffmpeg: list[tuple[str, Path]]) -> None:
    from vidgen.videogen.run import generate_clip

    server = FakeServer(polls=1)
    transport = HttpTransport("http://127.0.0.1:8188", ComfyClient("http://127.0.0.1:8188", opener=server))
    provider = ComfyUIVideoProvider(transport, units_per_hour=2.0, poll_seconds=0, sleep=lambda s: None)
    settings = VideogenConfig(provider="comfyui", comfyui={"url": "http://127.0.0.1:8188"})
    request = _request(tmp_path)
    result = generate_clip(tmp_path, settings, request, pay=True, provider=provider, catalog=Catalog((), 0.0, "cache"))
    assert result.path is not None and result.path.read_bytes() == b"MP4DATA" and result.cost == 0.0
    assert result.job is not None and result.job.usage == {"gpu_seconds": 266.2, "compute_units": 0.1479, "units_per_hour": 2.0,
                                                           "server": "http://127.0.0.1:8188"}
    sidecar = json.loads(result.path.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["provider"] == "comfyui" and sidecar["usage"]["gpu_seconds"] == 266.2 and sidecar["key"] == request_hash(request)
    assert set(server.uploads) == {f"vidgen_{request_hash(request)}_control.mp4", f"vidgen_{request_hash(request)}_first.png"}
    ledger = (tmp_path / "videogen-ledger.comfyui.jsonl").read_text(encoding="utf-8")
    assert '"event": "submit"' in ledger and '"cost_usd": 0.0' in ledger
    # the same request again is the cached clip: nothing is sent
    again = generate_clip(tmp_path, settings, request, pay=True, provider=provider, catalog=Catalog((), 0.0, "cache"))
    assert again.plan.cached and len(server.prompts) == 1
    assert server.calls.count("/free") == 1 and server.calls.index("/free") < server.calls.index("/upload/image")   # unloaded before the first job


def test_a_failed_server_refuses_the_submit_and_leaves_no_open_intent(tmp_path: Path, no_ffmpeg: list[tuple[str, Path]]) -> None:
    from vidgen.videogen.ledger import Ledger
    from vidgen.videogen.run import generate_clip

    server = FakeServer()
    server.down = True
    provider = ComfyUIVideoProvider(HttpTransport("http://127.0.0.1:8188", ComfyClient("http://127.0.0.1:8188", opener=server)))
    provider.check_credentials = lambda: None  # type: ignore[method-assign]
    settings = VideogenConfig(provider="comfyui", comfyui={"url": "http://127.0.0.1:8188"})
    with pytest.raises(VidgenError, match="no ComfyUI"):
        generate_clip(tmp_path, settings, _request(tmp_path), pay=True, provider=provider, catalog=Catalog((), 0.0, "cache"))
    assert not Ledger(tmp_path / "videogen-ledger.comfyui.jsonl").unresolved_intents()


def test_an_openrouter_model_on_comfyui_is_a_problem(tmp_path: Path) -> None:
    from vidgen.videogen.models import VideoModel
    from vidgen.videogen.run import plan_clip

    settings = VideogenConfig(provider="comfyui", comfyui={"colab": "ltx"})
    catalog = Catalog((VideoModel("a/b"),), 0.0, "cache")
    plan = plan_clip(tmp_path, settings, VideoRequest(model="a/b"), catalog=catalog)
    assert "runs vidgen's ComfyUI workflows only" in plan.check.problems[0]
    plan = plan_clip(tmp_path, VideogenConfig(), _request(tmp_path), catalog=catalog)
    assert "is a ComfyUI workflow" in plan.check.problems[0]


class FakeColab:
    """The Colab helper's calls for ColabTransport: uploads, vm actions, downloads."""

    session = "ltx"

    def __init__(self, polls: list[dict[str, Any]]) -> None:
        self.polls = polls
        self.archive: dict[str, bytes] = {}
        self.actions: list[tuple[str, dict[str, str]]] = []
        self.lines: list[str] = []

    def sessions(self) -> dict[str, str]:
        return {"ltx": "L4"}

    def say(self, line: str) -> None:
        self.lines.append(line)

    def upload(self, local: Path, remote: str) -> None:
        with tarfile.open(local, "r:gz") as tar:
            self.archive = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}  # type: ignore[union-attr]

    def vm(self, action: str, **env: str) -> dict[str, Any]:
        self.actions.append((action, env))
        return self.polls.pop(0) if action == "poll" else {}

    def download(self, remote: str, local: Path) -> None:
        assert remote.endswith("/output.mp4")
        local.write_bytes(b"MP4")


def test_colab_transport_runs_the_client_on_the_vm(tmp_path: Path) -> None:
    (tmp_path / "c.mp4").write_bytes(b"control")
    done = {"status": "completed", "seconds": 250.0, "error": None, "output": {"filename": "x.mp4"}, "prompt_id": "p"}
    polls = [
        {"run": {"id": None}, "log": "uploaded c.mp4\n", "offset": 15, "done": False},
        {"run": {"id": None}, "log": "done\n", "offset": 20, "done": True, "out": json.dumps(done) + "\n"},
    ]
    fake = FakeColab(polls)
    transport = ColabTransport(fake)  # type: ignore[arg-type]
    job_id = transport.submit(PreparedJob({"1": {}}, {"c.mp4": tmp_path / "c.mp4"}))
    for poll in polls:
        poll["run"]["id"] = job_id
    spec = json.loads(fake.archive["job.json"])
    assert spec["url"] == comfyui.VM_URL and spec["uploads"] == {"c.mp4": "inputs/c.mp4"} and fake.archive["inputs/c.mp4"] == b"control"
    assert b"def run_job" in fake.archive["comfyui_client.py"]
    assert [action for action, _ in fake.actions] == ["begin"]
    start = dict(fake.actions)["begin"]
    assert start["VIDGEN_BIN"] == "python3" and json.loads(start["VIDGEN_ARGS"]) == ["comfyui_client.py", "job.json"]
    assert start["VIDGEN_PROJECT"] == f"{comfyui.VM_JOBS}/{job_id}"
    provider = ComfyUIVideoProvider(transport, poll_seconds=0, sleep=lambda s: None)  # type: ignore[arg-type]
    job = provider.wait(JobState(job_id, "pending"))
    assert job.status == "completed" and job.usage is not None and job.usage["compute_units"] == round(250 * 1.94 / 3600, 4)
    assert dict(fake.actions[-1][1])["VIDGEN_OFFSET"] == "15" and "   uploaded c.mp4" in fake.lines
    assert provider.download(job_id, tmp_path / "out" / "clip.mp4") == 3


def test_colab_transport_without_outcome_is_a_failed_job(tmp_path: Path) -> None:
    fake = FakeColab([{"run": {"id": "j", "rc": 1}, "log": "", "offset": 0, "done": True, "out": ""}])
    assert ColabTransport(fake).outcome("j")["status"] == "failed"  # type: ignore[arg-type]


def test_transport_choice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(comfyui, "VM_MARKER", tmp_path / "marker")
    assert isinstance(comfyui.make_transport(ComfyuiSettings(url="http://h:1"), poll_timeout=9), HttpTransport)
    assert isinstance(comfyui.make_transport(ComfyuiSettings(colab="ltx"), poll_timeout=9), ColabTransport)
    (tmp_path / "marker").write_text("x", encoding="utf-8")
    on_vm = comfyui.make_transport(ComfyuiSettings(colab="ltx"), poll_timeout=9)
    assert isinstance(on_vm, HttpTransport) and on_vm.where == comfyui.VM_URL


def test_generate_via_flag_reaches_the_colab_transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    from vidgen import cli

    monkeypatch.setattr(comfyui, "VM_MARKER", tmp_path / "marker")
    assert cli.build_parser().parse_args(["generate", "run"]).via == "ssh"
    args = cli.build_parser().parse_args(["generate", "run", "--via", "exec"])
    settings = ComfyuiSettings(colab="ltx")
    assert comfyui.make_transport(settings, poll_timeout=9).colab.via == "ssh"  # type: ignore[attr-defined]
    cli._use_route(SimpleNamespace(config=SimpleNamespace(videogen=SimpleNamespace(comfyui=settings))), args.via)  # type: ignore[arg-type]
    assert comfyui.make_transport(settings, poll_timeout=9).colab.via == "exec"  # type: ignore[attr-defined]
    assert "via" not in settings.model_dump() and "_via" not in ComfyuiSettings.model_json_schema()["properties"]
    with pytest.raises(ValidationError):
        ComfyuiSettings(colab="ltx", via="exec")  # type: ignore[call-arg]
