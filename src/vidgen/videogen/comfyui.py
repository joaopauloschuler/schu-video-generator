"""The ``comfyui`` video provider: vidgen's own ComfyUI workflows (DESIGN.md §113.20).

A workflow (:class:`Workflow`, :data:`WORKFLOWS`) is a model id kept with vidgen: its inputs
(a control video from the shot's ``guide``, an optional first frame, the prompt), its shape rules
(width and height in multiples of 64, ``8k+1`` frames, 24 fps) and its graph
(:mod:`.ltx_graph`). It shows in the model list (:meth:`Workflow.record`) and costs $0.

:class:`ComfyUIVideoProvider` has the OpenRouter provider's interface (submit, status, wait,
download), so :func:`vidgen.videogen.run.generate_clip` caches, records and keeps its clips the
same way. On submit it fits the inputs to the workflow (the guide scaled to cover and cropped,
its frames cut or the last one held; the first frame the same), builds the graph and hands it
to a transport:

- :class:`HttpTransport` (``videogen.comfyui.url``, or ``colab:`` when vidgen itself runs on
  that Colab VM): ComfyUI's HTTP API through :mod:`.comfyui_client`;
- :class:`ColabTransport` (``videogen.comfyui.colab``): the inputs, the graph and
  :mod:`.comfyui_client` go up with the colab CLI, the client runs on the VM against
  127.0.0.1:8188, detached (:mod:`vidgen.colab_vm`), and the clip comes back with ``colab download``.

A finished job reports its GPU seconds and compute units (``usage``), kept in the take.
"""

from __future__ import annotations

import json
import logging
import math
import secrets
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from vidgen.errors import VidgenError
from vidgen.videogen import COMFYUI_PROVIDER, JobState, VideoRequest
from vidgen.videogen import comfyui_client as client_module
from vidgen.videogen.comfyui_client import ComfyClient, ComfyError, job_outcome

if TYPE_CHECKING:
    from vidgen.colab import Colab
    from vidgen.config import ComfyuiSettings
    from vidgen.videogen.models import Estimate, RequestCheck, VideoModel

log = logging.getLogger("vidgen.videogen")

#: ComfyUI on a Colab VM (tools/colab/setup_session.py starts it there).
VM_URL = "http://127.0.0.1:8188"
#: Written on a Colab VM by vidgen's setup (:mod:`vidgen.colab_vm`): vidgen runs on that VM.
VM_MARKER = Path("/content/.vidgen_setup_vidgen_done")
#: Where the Colab transport keeps each job on the VM (``<folder>/<job id>``).
VM_JOBS = "/content/vidgen-comfyui"


@dataclass(frozen=True)
class Workflow:
    """A ComfyUI workflow kept with vidgen: its id, the guides it takes as its control video, and
    its shape rules (``short_side`` and sizes in multiples of ``size_step``; ``frame_step * k + 1``
    frames up to ``max_frames`` at ``fps``)."""

    id: str
    name: str
    description: str
    controls: tuple[str, ...]
    fps: int = 24
    short_side: int = 512
    size_step: int = 64
    frame_step: int = 8
    max_frames: int = 121
    seed: int = 42

    @property
    def resolution(self) -> str:
        """The one resolution tier it makes (``512p``)."""
        return f"{self.short_side}p"

    @property
    def max_seconds(self) -> int:
        """The longest whole-second clip it makes."""
        return (self.max_frames - 1) // self.fps

    def record(self) -> VideoModel:
        """Its entry in the model list."""
        from vidgen.videogen.models import VideoModel

        return VideoModel(
            id=self.id, name=self.name, description=self.description, durations=tuple(range(1, self.max_seconds + 1)),
            resolutions=(self.resolution,), frame_types=("first_frame",), generate_audio=True, seed=True, provider=COMFYUI_PROVIDER,
        )

    def size(self, aspect_ratio: str | None) -> tuple[int, int]:
        """Width and height for ``aspect_ratio`` (``W:H``; 16:9 when none): the short side
        :attr:`short_side`, the long side rounded up to :attr:`size_step` (16:9 -> 960x512)."""
        a, _, b = (aspect_ratio or "16:9").partition(":")
        try:
            ratio = float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            ratio = 16 / 9
        long = self.size_step * math.ceil(self.short_side * max(ratio, 1 / ratio) / self.size_step - 1e-9)
        return (long, self.short_side) if ratio >= 1 else (self.short_side, long)

    def frames(self, seconds: float) -> int:
        """The frame count for ``seconds``: at least that long, ``frame_step * k + 1``, at most :attr:`max_frames`."""
        steps = math.ceil(max(seconds, 1 / self.fps) * self.fps / self.frame_step - 1e-9)
        return min(self.max_frames, steps * self.frame_step + 1)

    def graph(self, *, control: str, first_frame: str | None, placeholder: str, prompt: str, width: int, height: int,
              frames: int, seed: int | None, prefix: str, with_audio: bool) -> dict[str, Any]:
        """The API-format graph (``control`` / ``first_frame`` are names in ComfyUI's input
        folder; ``placeholder`` is loaded and bypassed when there is no first frame)."""
        from vidgen.videogen import ltx_graph

        return ltx_graph.graph(
            control_file=control, prefix=prefix, use_first_frame=first_frame is not None, prompt=prompt or ltx_graph.PROMPT,
            width=width, height=height, frames=frames, fps=self.fps, seed=self.seed if seed is None else seed,
            first_frame_file=first_frame or placeholder, with_audio=with_audio,
        )


#: The workflows kept with vidgen, by model id.
WORKFLOWS: dict[str, Workflow] = {
    "ltx-2.3-union-control": Workflow(
        id="ltx-2.3-union-control", name="LTX-2.3 IC-LoRA Union Control (ComfyUI)",
        description="LTX-2.3 distilled-1.1 GGUF Q5_K_M + IC-LoRA union-control ref0.5: restyles a control video (the shot's depth guide), "
                    "optionally from a first frame; 8 steps, cfg 1",
        controls=("depth",),
    ),
}


def find_workflow(model: str) -> Workflow | None:
    """The workflow of model id ``model`` (``None``: not a workflow)."""
    return WORKFLOWS.get(model)


def workflow_records() -> list[VideoModel]:
    """The model-list entries of every workflow."""
    return [w.record() for w in WORKFLOWS.values()]


def check_workflow_request(request: VideoRequest, model: VideoModel) -> RequestCheck:
    """``request`` against workflow ``model``: one control video, no last frame, its one resolution."""
    from vidgen.videogen.models import RequestCheck

    workflow = find_workflow(model.id)
    assert workflow is not None
    check = RequestCheck()
    videos = [r for r in request.references if r.kind == "video"]
    if len(videos) != 1:
        check.problems.append(f"{model.id} needs one control video: guide: {' or '.join(workflow.controls)} (it has {len(videos)})")
    if any(f.frame_type != "first_frame" for f in request.frame_images):
        check.problems.append(f"{model.id} takes a first frame only, not a last frame")
    if request.resolution is not None and request.resolution.lower() != workflow.resolution:
        check.problems.append(f"{model.id} makes {workflow.resolution} only, not {request.resolution}")
    left_out = [r.kind for r in request.references if r.kind != "video"]
    if left_out:
        check.notes.append(f"{model.id} takes no reference pictures or sound: {len(left_out)} reference(s) are not sent")
    if request.duration is not None and request.duration > workflow.max_seconds:
        check.problems.append(f"{model.id} makes clips of 1-{workflow.max_seconds} s, not {request.duration}")
    return check


def workflow_estimate() -> Estimate:
    """A workflow's price: $0 (the GPU time is recorded in the take instead)."""
    from vidgen.videogen.models import Estimate

    return Estimate(0.0, "no money: runs on your ComfyUI server; the take records the GPU time and compute units")


def guide_problem(model: str, guide: str | None) -> str | None:
    """Why a shot with ``guide`` cannot use workflow ``model`` (``None``: it can, or ``model`` is no workflow)."""
    workflow = find_workflow(model)
    if workflow is None or guide in workflow.controls:
        return None
    return f"{model} takes guide: {' or '.join(workflow.controls)} as its control video, not {guide or 'no guide'}"


# ----- fitting the inputs ------------------------------------------------------------------------


def _cover(width: int, height: int) -> str:
    return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"


def fit_control(source: Path, dest: Path, *, width: int, height: int, frames: int, fps: int) -> Path:
    """``source`` at ``width`` x ``height`` (scaled to cover, centre-cropped), ``fps``, exactly
    ``frames`` frames (cut, or the last frame held), silent H.264."""
    from vidgen.render.ffmpeg import find_ffmpeg, run_ffmpeg

    run_ffmpeg(find_ffmpeg(), ["-i", str(source), "-vf", f"fps={fps},{_cover(width, height)},tpad=stop_mode=clone:stop={frames}",
                               "-frames:v", str(frames), "-an", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(dest)],
               "fit the control video to the workflow")
    return dest


def fit_picture(source: Path, dest: Path, *, width: int, height: int) -> Path:
    """The first picture of ``source`` (a picture or a video) at ``width`` x ``height`` (cover, centre crop), as PNG."""
    from vidgen.render.ffmpeg import find_ffmpeg, run_ffmpeg

    run_ffmpeg(find_ffmpeg(), ["-i", str(source), "-vf", _cover(width, height), "-frames:v", "1", str(dest)], "fit the first frame to the workflow")
    return dest


@dataclass(frozen=True)
class PreparedJob:
    """A job ready to send: the graph and the files it loads (name in ComfyUI's input folder -> local file)."""

    graph: dict[str, Any]
    uploads: dict[str, Path]


def prepare_job(request: VideoRequest, folder: Path, key: str) -> PreparedJob:
    """Fit ``request``'s inputs into ``folder`` and build its graph (``key``: names its files in ComfyUI)."""
    workflow = find_workflow(request.model)
    if workflow is None:
        raise VidgenError(f"{request.model} is no ComfyUI workflow kept with vidgen; workflows: {', '.join(WORKFLOWS)}")
    videos = [r for r in request.references if r.kind == "video" and r.path is not None]
    if len(videos) != 1:
        raise VidgenError(f"{request.model} needs one local control video (the shot's guide)")
    width, height = workflow.size(request.aspect_ratio)
    frames = workflow.frames(float(request.duration or workflow.max_seconds))
    assert videos[0].path is not None
    control = fit_control(videos[0].path, folder / f"vidgen_{key}_control.mp4", width=width, height=height, frames=frames, fps=workflow.fps)
    uploads = {control.name: control}
    first = next((f.path for f in request.frame_images if f.frame_type == "first_frame" and f.path is not None), None)
    picture = fit_picture(first or control, folder / f"vidgen_{key}_first.png", width=width, height=height)
    uploads[picture.name] = picture
    graph = workflow.graph(
        control=control.name, first_frame=picture.name if first is not None else None, placeholder=picture.name, prompt=request.prompt,
        width=width, height=height, frames=frames, seed=request.seed, prefix=f"vidgen_{key}", with_audio=request.generate_audio,
    )
    return PreparedJob(graph, uploads)


# ----- transports ------------------------------------------------------------------------------


class Transport(Protocol):
    """How jobs reach a ComfyUI server."""

    where: str

    def check(self) -> None: ...
    def submit(self, job: PreparedJob) -> str: ...
    def outcome(self, job_id: str) -> dict[str, Any]: ...
    def download(self, job_id: str, dest: Path) -> int: ...


class HttpTransport:
    """ComfyUI over HTTP at ``url`` (the job id is ComfyUI's prompt id)."""

    def __init__(self, url: str, client: ComfyClient | None = None) -> None:
        self.client = client or ComfyClient(url)
        self.where = self.client.url

    def check(self) -> None:
        try:
            self.client.system_stats()
        except ComfyError as exc:
            raise VidgenError(f"{exc}: start ComfyUI there, or fix videogen.comfyui.url") from None

    def submit(self, job: PreparedJob) -> str:
        try:
            for name, path in job.uploads.items():
                self.client.upload(path, name)
            return self.client.submit(job.graph)
        except ComfyError as exc:
            raise VidgenError(str(exc)) from None

    def outcome(self, job_id: str) -> dict[str, Any]:
        try:
            return job_outcome(self.client.history(job_id))
        except ComfyError as exc:
            raise VidgenError(str(exc)) from None

    def download(self, job_id: str, dest: Path) -> int:
        result = self.outcome(job_id)
        if result["status"] != "completed":
            raise VidgenError(f"ComfyUI job {job_id} is {result['status']}: nothing to download")
        try:
            return self.client.view(result["output"], dest)
        except ComfyError as exc:
            raise VidgenError(str(exc)) from None


class ColabTransport:
    """ComfyUI on a Colab session, driven with the colab CLI (the job id names its folder on the VM)."""

    def __init__(self, colab: Colab, *, poll_seconds: float = 5.0, timeout: float = 3600.0) -> None:
        self.colab = colab
        self.where = f"Colab session {colab.session}"
        self.poll_seconds = poll_seconds
        self.timeout = timeout
        self.offsets: dict[str, int] = {}

    def check(self) -> None:
        from vidgen.colab import ColabError
        from vidgen.remote import setup_command

        if self.colab.session not in self.colab.sessions():
            raise ColabError(f"no Colab session {self.colab.session!r} (colab sessions); create and set it up: {setup_command(self.colab.session)}")

    def submit(self, job: PreparedJob) -> str:
        from vidgen.colab import files_archive

        job_id = f"{int(time.time())}-{secrets.token_hex(3)}"
        remote = f"{VM_JOBS}/{job_id}"
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            names = {name: f"inputs/{name}" for name in job.uploads}
            (folder / "inputs").mkdir()
            for name, path in job.uploads.items():
                shutil.copyfile(path, folder / names[name])
            spec = {"url": VM_URL, "graph": job.graph, "uploads": names, "poll_seconds": self.poll_seconds, "timeout": self.timeout}
            (folder / "job.json").write_text(json.dumps(spec), encoding="utf-8")
            shutil.copyfile(client_module.__file__, folder / "comfyui_client.py")
            files = ["job.json", "comfyui_client.py", *names.values()]
            archive = files_archive(folder, files, folder / f"vidgen-comfyui-{job_id}.tar.gz")
            self.colab.upload(archive, f"/content/{archive.name}")
        self.colab.vm("unpack", VIDGEN_ARCHIVE=f"/content/{archive.name}", VIDGEN_DEST=remote)
        self.colab.vm("start", VIDGEN_PROJECT=remote, VIDGEN_RUN=job_id, VIDGEN_BIN="python3",
                      VIDGEN_ARGS=json.dumps(["comfyui_client.py", "job.json"]))
        return job_id

    def outcome(self, job_id: str) -> dict[str, Any]:
        reply = self.colab.vm("poll", VIDGEN_PROJECT=f"{VM_JOBS}/{job_id}", VIDGEN_OFFSET=str(self.offsets.get(job_id, 0)))
        if reply["run"]["id"] != job_id:
            raise VidgenError(f"ComfyUI job {job_id} is not on {self.colab.session} (the session was restarted?)")
        for line in reply["log"].splitlines():
            if line.strip():
                self.colab.say(f"   {line.strip()}")
        self.offsets[job_id] = reply["offset"]
        if not reply["done"]:
            return {"status": "running", "seconds": None, "error": None, "output": None}
        try:
            result = json.loads((reply.get("out") or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"status": "failed", "seconds": None, "error": f"the job on the VM ended (exit code {reply['run']['rc']}) without an outcome", "output": None}
        return result if isinstance(result, dict) else {"status": "failed", "seconds": None, "error": "unreadable outcome", "output": None}

    def download(self, job_id: str, dest: Path) -> int:
        self.colab.download(f"{VM_JOBS}/{job_id}/{client_module.OUTPUT_NAME}", dest)
        return dest.stat().st_size


def on_colab_vm() -> bool:
    """Whether vidgen runs on a Colab VM it was set up on (tools/colab/setup_session.py)."""
    return VM_MARKER.is_file()


def make_transport(settings: ComfyuiSettings, *, poll_timeout: float, say: Callable[[str], None] | None = None) -> Transport:
    """The transport ``videogen.comfyui`` names (``colab:`` on that VM itself: its own ComfyUI over HTTP)."""
    if settings.url is not None:
        return HttpTransport(settings.url)
    if on_colab_vm():
        return HttpTransport(VM_URL)
    from vidgen.colab import Colab, say_now

    assert settings.colab is not None
    return ColabTransport(Colab(settings.colab, say=say or say_now), timeout=poll_timeout)


# ----- the provider ----------------------------------------------------------------------------


class ComfyUIVideoProvider:
    """The ``comfyui`` provider (the OpenRouter provider's interface; see the module docstring)."""

    name = COMFYUI_PROVIDER

    def __init__(self, transport: Transport, *, units_per_hour: float = 1.94, poll_timeout: float = 900.0,
                 poll_seconds: float = 15.0, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        self.transport = transport
        self.units_per_hour = units_per_hour
        self.poll_timeout = poll_timeout
        self.poll_seconds = poll_seconds
        self.sleep = sleep
        self.clock = clock
        self.uploader: Callable[[Path], str] | None = None   # unused: inputs go to ComfyUI itself

    def check_credentials(self) -> None:
        """Whether the server is there (no key is needed)."""
        self.transport.check()

    def submit(self, request: VideoRequest, drop: set[str] | frozenset[str] = frozenset(), *, on_sending: Callable[[], None] | None = None) -> JobState:
        """Fit the inputs, build the graph and queue it; a failure before ComfyUI queued it is a refused submit."""
        from vidgen.videogen import request_hash
        from vidgen.videogen.openrouter import SubmitRefused

        with tempfile.TemporaryDirectory() as tmp:
            job = prepare_job(request, Path(tmp), request_hash(request))
            if on_sending is not None:
                on_sending()
            try:
                job_id = self.transport.submit(job)
            except VidgenError as exc:
                raise SubmitRefused(f"{self.transport.where}: {exc}") from None
        log.info("ComfyUI job %s queued on %s", job_id, self.transport.where)
        return JobState(job_id, "pending", cost=0.0)

    def status(self, job_id: str) -> JobState:
        """The job as the server reports it (``usage``: GPU seconds and compute units once it ended)."""
        result = self.transport.outcome(job_id)
        status = {"running": "in_progress", "completed": "completed"}.get(result["status"], "failed")
        usage = self.usage(result.get("seconds")) if status != "in_progress" else None
        return JobState(job_id, status, cost=0.0, error=result.get("error"), usage=usage)

    def usage(self, seconds: float | None) -> Mapping[str, Any]:
        """What a job of ``seconds`` GPU time used."""
        units = round(seconds * self.units_per_hour / 3600.0, 4) if seconds is not None else None
        return {"gpu_seconds": seconds, "compute_units": units, "units_per_hour": self.units_per_hour, "server": self.transport.where}

    def wait(self, job: JobState, *, on_status: Callable[[JobState], None] | None = None) -> JobState:
        """Poll ``job`` until it ends; after ``poll_timeout`` s a :class:`VidgenError` (the job goes on; a later run polls it again)."""
        begin = self.clock()
        while not job.done:
            if self.clock() - begin > self.poll_timeout:
                raise VidgenError(f"ComfyUI job {job.id} still runs after {self.poll_timeout:.0f} s on {self.transport.where}; "
                                  "it goes on there: run the same command again later to fetch it")
            self.sleep(self.poll_seconds)
            job = self.status(job.id)
            if on_status is not None:
                on_status(job)
        return job

    def download(self, job_id: str, dest: Path) -> int:
        """Fetch the clip of a completed job to ``dest``."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        return self.transport.download(job_id, dest)


__all__ = [
    "ColabTransport", "ComfyUIVideoProvider", "HttpTransport", "PreparedJob", "VM_URL", "WORKFLOWS", "Workflow",
    "check_workflow_request", "find_workflow", "fit_control", "fit_picture", "guide_problem", "make_transport", "on_colab_vm",
    "prepare_job", "workflow_estimate", "workflow_records",
]
