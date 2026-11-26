"""The ``comfyui`` video provider: vidgen's own ComfyUI workflows (DESIGN.md §113.20).

A workflow (:class:`Workflow`, :data:`WORKFLOWS`) is a model id kept with vidgen: its inputs
(a control video from the shot's ``guide``, an optional first frame, the prompt), its shape rules
(width and height in multiples of 64, ``8k+1`` frames, at most 121 of them, made at 24 fps or at
12 fps and then doubled to 24 fps by RIFE in the same job) and its graph (:mod:`.ltx_graph`). It shows in the model list (:meth:`Workflow.record`) and costs $0.

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

A finished job reports its GPU seconds and compute units (``usage``), kept in the take. The
first job of a provider (one ``vidgen generate run``) unloads the models first (``POST /free``), so
no picture model is left in the GPU's memory; the jobs after it keep the video model loaded.

A request with a ``sheet`` (a shot's ``sheet:``) is the base video + stylesheet graph of
:mod:`.ltx_graph`; it runs only on a ComfyUI started with ``--disable-comfy-compiler``
(:meth:`ComfyUIVideoProvider.check_compiler`, never a restart from here).

:func:`restyle_picture` (``first_frame: restyled``, DESIGN.md §113.21) sends a picture job the
same way: Qwen-Image-Edit-2511 (:mod:`.qwen_graph`) makes a photoreal version of the render's
first frame at the workflow's size, then the models are unloaded for the video job.
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
    frames up to ``max_frames``, generated at one of ``fps_choices``; the clip vidgen stores is at
    ``fps``: a clip generated at a lower rate is doubled to it by RIFE in the same job)."""

    id: str
    name: str
    description: str
    controls: tuple[str, ...]
    fps: int = 24
    fps_choices: tuple[int, ...] = (12, 24)
    short_side: int = 512
    size_step: int = 64
    frame_step: int = 8
    max_frames: int = 121
    seed: int = 42
    takes_sheet: bool = False

    @property
    def controls_text(self) -> str:
        """:attr:`controls` as messages name them (``canny, final or depth``)."""
        return " or ".join([", ".join(self.controls[:-1]), self.controls[-1]] if len(self.controls) > 1 else self.controls)

    @property
    def resolution(self) -> str:
        """The one resolution tier it makes (``512p``)."""
        return f"{self.short_side}p"

    @property
    def max_seconds(self) -> int:
        """The longest whole-second clip it makes at :attr:`fps`."""
        return self.max_seconds_at(self.fps)

    def max_seconds_at(self, fps: int | None) -> int:
        """The longest whole-second clip it generates at ``fps`` (``None``: :attr:`fps`)."""
        return (self.max_frames - 1) // (fps or self.fps)

    def durations(self, fps: int | None = None) -> tuple[int, ...]:
        """The whole-second lengths it makes at ``fps`` (``None``: :attr:`fps`): ``seconds x fps + 1``
        frames must be ``frame_step * k + 1`` and at most :attr:`max_frames` (24 fps: 1-5 s; 12 fps: 2, 4, 6, 8, 10 s)."""
        rate = fps or self.fps
        return tuple(d for d in range(1, self.max_seconds_at(rate) + 1) if (d * rate) % self.frame_step == 0)

    def lengths_text(self, fps: int | None = None) -> str:
        """:meth:`durations` as messages show them (``1-5``; ``2, 4, 6, 8, 10``)."""
        lengths = self.durations(fps)
        if len(lengths) > 2 and lengths == tuple(range(lengths[0], lengths[-1] + 1)):
            return f"{lengths[0]}-{lengths[-1]}"
        return ", ".join(map(str, lengths))

    def fps_problem(self, fps: int | None) -> str | None:
        """Why ``fps`` is no frame rate it generates at (``None``: it is, or none was given)."""
        if fps is None or fps in self.fps_choices:
            return None
        return f"{self.id} generates at {' or '.join(map(str, self.fps_choices))} fps, not {fps}"

    def duration_problem(self, seconds: int | None, fps: int | None) -> str | None:
        """Why a clip of ``seconds`` at ``fps`` cannot be made (``None``: it can, or no length was given)."""
        rate = fps or self.fps
        if seconds is None or seconds in self.durations(rate):
            return None
        frames = seconds * rate + 1
        allowed = self.lengths_text(rate)
        if frames > self.max_frames:
            why = f"{frames} frames, over its {self.max_frames}"
        else:
            why = f"{frames} frames, not {self.frame_step}k+1"
        return f"{self.id} makes clips of {allowed} s at {rate} fps, not {seconds} s ({why})"

    def record(self) -> VideoModel:
        """Its entry in the model list."""
        from vidgen.videogen.models import VideoModel

        return VideoModel(
            id=self.id, name=self.name, description=self.description, durations=self.durations(),
            resolutions=(self.resolution,), frame_types=("first_frame",), generate_audio=True, seed=True, provider=COMFYUI_PROVIDER,
        )

    def size(self, aspect_ratio: str | None, size: str | None = None) -> tuple[int, int]:
        """Width and height: ``size`` (``WIDTHxHEIGHT``, a shot's ``size:``) when given, else for
        ``aspect_ratio`` (``W:H``; 16:9 when none) the short side :attr:`short_side` and the long
        side rounded up to :attr:`size_step` (16:9 -> 960x512)."""
        if size is not None:
            width, _, height = size.partition("x")
            return int(width), int(height)
        a, _, b = (aspect_ratio or "16:9").partition(":")
        try:
            ratio = float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            ratio = 16 / 9
        long = self.size_step * math.ceil(self.short_side * max(ratio, 1 / ratio) / self.size_step - 1e-9)
        return (long, self.short_side) if ratio >= 1 else (self.short_side, long)

    def frames(self, seconds: float, fps: int | None = None) -> int:
        """The frame count generated for ``seconds`` at ``fps`` (``None``: :attr:`fps`): at least that
        long, ``frame_step * k + 1``, at most :attr:`max_frames`."""
        rate = fps or self.fps
        steps = math.ceil(max(seconds, 1 / rate) * rate / self.frame_step - 1e-9)
        return min(self.max_frames, steps * self.frame_step + 1)

    def stored_frames(self, frames: int, fps: int | None = None) -> int:
        """The frames of the clip vidgen stores for ``frames`` generated at ``fps``: the same at
        :attr:`fps`; doubled by RIFE (``2n - 1``: one made-up frame between each two) below it."""
        multiplier = self.fps // (fps or self.fps)
        return (frames - 1) * multiplier + 1

    def graph(self, *, control: str, first_frame: str | None, placeholder: str, prompt: str, width: int, height: int,
              frames: int, seed: int | None, prefix: str, with_audio: bool, sheet: str | None = None,
              text_encoder: str = "cpu", fps: int | None = None) -> dict[str, Any]:
        """The API-format graph (``control`` / ``first_frame`` / ``sheet`` are names in ComfyUI's
        input folder; ``placeholder`` is loaded and bypassed when there is no first frame;
        ``text_encoder``: ``videogen.comfyui.text_encoder``, cpu or gpu; ``fps``: the rate it
        generates at, ``None`` for :attr:`fps`; below it the graph doubles the clip to :attr:`fps`)."""
        from vidgen.videogen import ltx_graph

        return ltx_graph.graph(
            control_file=control, prefix=prefix, use_first_frame=first_frame is not None, prompt=prompt or ltx_graph.PROMPT,
            width=width, height=height, frames=frames, fps=fps or self.fps, seed=self.seed if seed is None else seed,
            first_frame_file=first_frame or placeholder, with_audio=with_audio, sheet_file=sheet, text_encoder=text_encoder,
            out_fps=self.fps,
        )


#: The workflows kept with vidgen, by model id.
WORKFLOWS: dict[str, Workflow] = {
    "ltx-2.3-union-control": Workflow(
        id="ltx-2.3-union-control", name="LTX-2.3 IC-LoRA Union Control (ComfyUI)",
        description="LTX-2.3 distilled-1.1 GGUF Q5_K_M + IC-LoRA union-control ref0.5: restyles a control video (the shot's canny, final or depth guide), "
                    "optionally from a first frame and with a stylesheet (sheet:, Ingredients IC-LoRA); 8 steps, cfg 1",
        controls=("canny", "final", "depth"), takes_sheet=True,
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
        check.problems.append(f"{model.id} needs one control video: guide: {workflow.controls_text} (it has {len(videos)})")
    if any(f.frame_type != "first_frame" for f in request.frame_images):
        check.problems.append(f"{model.id} takes a first frame only, not a last frame")
    if request.resolution is not None and request.resolution.lower() != workflow.resolution:
        check.problems.append(f"{model.id} makes {workflow.resolution} only, not {request.resolution}")
    left_out = [r.kind for r in request.references if r.kind != "video"]
    if left_out:
        check.notes.append(f"{model.id} takes no reference pictures or sound: {len(left_out)} reference(s) are not sent")
    if (wrong_fps := workflow.fps_problem(request.fps)) is not None:
        check.problems.append(wrong_fps)
    elif (wrong_length := workflow.duration_problem(request.duration, request.fps)) is not None:
        check.problems.append(wrong_length)
    if request.sheet is not None and not workflow.takes_sheet:
        check.problems.append(f"{model.id} takes no sheet")
    if request.size is not None:
        width, height = workflow.size(None, request.size)
        if width % workflow.size_step or height % workflow.size_step:
            check.problems.append(f"{model.id} makes sizes in multiples of {workflow.size_step}, not {request.size}")
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
    return f"{model} takes guide: {workflow.controls_text} as its control video, not {guide or 'no guide'}"


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


def fit_picture(source: Path, dest: Path, *, width: int, height: int, lanczos: bool = False) -> Path:
    """The first picture of ``source`` (a picture or a video) at ``width`` x ``height`` (cover, centre crop), as PNG."""
    from vidgen.render.ffmpeg import find_ffmpeg, run_ffmpeg

    cover = _cover(width, height).replace("increase", "increase:flags=lanczos") if lanczos else _cover(width, height)
    run_ffmpeg(find_ffmpeg(), ["-i", str(source), "-vf", cover, "-frames:v", "1", str(dest)], "fit the first frame to the workflow")
    return dest


@dataclass(frozen=True)
class PreparedJob:
    """A job ready to send: the graph, the files it loads (name in ComfyUI's input folder -> local
    file), the name of its output file and whether the models are unloaded before / after it."""

    graph: dict[str, Any]
    uploads: dict[str, Path]
    output: str = client_module.OUTPUT_NAME
    free_after: bool = False
    free_before: bool = False


def prepare_job(request: VideoRequest, folder: Path, key: str, *, text_encoder: str = "cpu") -> PreparedJob:
    """Fit ``request``'s inputs into ``folder`` and build its graph (``key``: names its files in ComfyUI;
    ``text_encoder``: where the graph runs the text encoder, cpu or gpu)."""
    workflow = find_workflow(request.model)
    if workflow is None:
        raise VidgenError(f"{request.model} is no ComfyUI workflow kept with vidgen; workflows: {', '.join(WORKFLOWS)}")
    videos = [r for r in request.references if r.kind == "video" and r.path is not None]
    if len(videos) != 1:
        raise VidgenError(f"{request.model} needs one local control video (the shot's guide)")
    if (wrong_fps := workflow.fps_problem(request.fps)) is not None:
        raise VidgenError(wrong_fps)
    fps = request.fps or workflow.fps
    width, height = workflow.size(request.aspect_ratio, request.size)
    frames = workflow.frames(float(request.duration or workflow.max_seconds_at(fps)), fps)
    assert videos[0].path is not None
    control = fit_control(videos[0].path, folder / f"vidgen_{key}_control.mp4", width=width, height=height, frames=frames, fps=fps)
    uploads = {control.name: control}
    first = next((f.path for f in request.frame_images if f.frame_type == "first_frame" and f.path is not None), None)
    picture = fit_picture(first or control, folder / f"vidgen_{key}_first.png", width=width, height=height)
    uploads[picture.name] = picture
    sheet = None
    if request.sheet is not None and request.sheet.path is not None:   # the shot's plan checked its aspect ratio
        sheet = fit_picture(request.sheet.path, folder / f"vidgen_{key}_sheet.png", width=width, height=height, lanczos=True)
        uploads[sheet.name] = sheet
    graph = workflow.graph(
        control=control.name, first_frame=picture.name if first is not None else None, placeholder=picture.name, prompt=request.prompt,
        width=width, height=height, frames=frames, seed=request.seed, prefix=f"vidgen_{key}", with_audio=request.generate_audio,
        sheet=sheet.name if sheet is not None else None, text_encoder=text_encoder, fps=fps,
    )
    return PreparedJob(graph, uploads)


# ----- transports ------------------------------------------------------------------------------


class Transport(Protocol):
    """How jobs reach a ComfyUI server."""

    where: str
    #: How to start the server's ComfyUI with ``--disable-comfy-compiler``.
    compiler_fix: str

    def check(self) -> None: ...
    def compiler_off(self) -> bool | None: ...
    def submit(self, job: PreparedJob) -> str: ...
    def outcome(self, job_id: str) -> dict[str, Any]: ...
    def download(self, job_id: str, dest: Path) -> int: ...


class HttpTransport:
    """ComfyUI over HTTP at ``url`` (the job id is ComfyUI's prompt id). ``comfy_args`` reads the
    arguments the server was started with (on the Colab VM itself: :func:`vidgen.colab_vm.comfy_args`,
    from ``/proc``); without it they come from ``/system_stats``."""

    def __init__(self, url: str, client: ComfyClient | None = None, *, comfy_args: Callable[[], list[str] | None] | None = None,
                 compiler_fix: str = "start ComfyUI there with --disable-comfy-compiler") -> None:
        self.client = client or ComfyClient(url)
        self.where = self.client.url
        self.free_after: set[str] = set()
        self.comfy_args = comfy_args
        self.compiler_fix = compiler_fix

    def check(self) -> None:
        try:
            self.client.system_stats()
        except ComfyError as exc:
            raise VidgenError(f"{exc}: start ComfyUI there, or fix videogen.comfyui.url") from None

    def compiler_off(self) -> bool | None:
        """Whether the server's ComfyUI runs with ``--disable-comfy-compiler`` (None: none runs, or
        ``/system_stats`` does not list its ``argv``)."""
        from vidgen.colab import NO_COMPILER_FLAG

        if self.comfy_args is not None:
            argv = self.comfy_args()
        else:
            try:
                argv = (self.client.system_stats().get("system") or {}).get("argv")
            except ComfyError as exc:
                raise VidgenError(str(exc)) from None
        return NO_COMPILER_FLAG in argv if isinstance(argv, list) else None

    def submit(self, job: PreparedJob) -> str:
        try:
            if job.free_before:
                self.client.free()
            for name, path in job.uploads.items():
                self.client.upload(path, name)
            job_id = self.client.submit(job.graph)
        except ComfyError as exc:
            raise VidgenError(str(exc)) from None
        if job.free_after:
            self.free_after.add(job_id)
        return job_id

    def outcome(self, job_id: str) -> dict[str, Any]:
        try:
            result = job_outcome(self.client.history(job_id))
            if result["status"] != "running" and job_id in self.free_after:
                self.free_after.discard(job_id)
                self.client.free()
            return result
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
        self.outputs: dict[str, str] = {}
        self.compiler_fix = f"run `python tools/colab/setup_session.py {colab.session} --no-comfy-compiler` (it restarts ComfyUI on the VM)"

    def check(self) -> None:
        from vidgen.colab import ColabError
        from vidgen.remote import setup_command

        if self.colab.session not in self.colab.sessions():
            raise ColabError(f"no Colab session {self.colab.session!r} (colab sessions); create and set it up: {setup_command(self.colab.session)}")

    def compiler_off(self) -> bool | None:
        """Whether the VM's ComfyUI runs with ``--disable-comfy-compiler`` (None: none runs)."""
        from vidgen.colab import comfy_compiler_off

        return comfy_compiler_off(self.colab)

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
            spec = {"url": VM_URL, "graph": job.graph, "uploads": names, "poll_seconds": self.poll_seconds, "timeout": self.timeout,
                    "output": job.output, "free_after": job.free_after, "free_before": job.free_before}
            (folder / "job.json").write_text(json.dumps(spec), encoding="utf-8")
            shutil.copyfile(client_module.__file__, folder / "comfyui_client.py")
            files = ["job.json", "comfyui_client.py", *names.values()]
            archive = files_archive(folder, files, folder / f"vidgen-comfyui-{job_id}.tar.gz")
            self.colab.upload(archive, f"/content/{archive.name}")
        self.colab.vm("begin", VIDGEN_PROJECT=remote, VIDGEN_RUN=job_id, VIDGEN_BIN="python3",
                      VIDGEN_ARCHIVE=f"/content/{archive.name}", VIDGEN_ARGS=json.dumps(["comfyui_client.py", "job.json"]))
        self.outputs[job_id] = job.output
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
        self.colab.download(f"{VM_JOBS}/{job_id}/{self.outputs.get(job_id, client_module.OUTPUT_NAME)}", dest)
        return dest.stat().st_size


def on_colab_vm() -> bool:
    """Whether vidgen runs on a Colab VM it was set up on (tools/colab/setup_session.py)."""
    return VM_MARKER.is_file()


def make_transport(settings: ComfyuiSettings, *, poll_timeout: float, say: Callable[[str], None] | None = None) -> Transport:
    """The transport ``videogen.comfyui`` names (``colab:`` on that VM itself: its own ComfyUI over HTTP)."""
    if settings.url is not None:
        return HttpTransport(settings.url)
    if on_colab_vm():
        from vidgen.colab_vm import comfy_args

        fix = f"run `python tools/colab/setup_session.py {settings.colab} --no-comfy-compiler` on your computer (it restarts ComfyUI on the VM)"
        return HttpTransport(VM_URL, comfy_args=comfy_args, compiler_fix=fix)
    from vidgen.colab import Colab, say_now

    assert settings.colab is not None
    return ColabTransport(Colab(settings.colab, say=say or say_now, via=settings.via), timeout=poll_timeout)


# ----- the provider ----------------------------------------------------------------------------


def missing_weights_hint(error: str) -> str:
    """``error`` with how to get the RIFE weights when ComfyUI's message names them (a 12 fps shot
    on a ComfyUI set up before the weights were part of tools/colab/setup.sh)."""
    from vidgen.videogen.ltx_graph import RIFE_MODEL

    if RIFE_MODEL not in error:
        return error
    return (f"{error} -- a 12 fps shot doubles its clip with RIFE: ComfyUI needs models/frame_interpolation/{RIFE_MODEL} "
            "(run `python tools/colab/setup_session.py NAME` again: setup.sh downloads it; elsewhere get it from "
            "huggingface.co/Comfy-Org/Frame-Interpolation, no login)")


class ComfyUIVideoProvider:
    """The ``comfyui`` provider (the OpenRouter provider's interface; see the module docstring)."""

    name = COMFYUI_PROVIDER

    def __init__(self, transport: Transport, *, units_per_hour: float = 1.94, poll_timeout: float = 900.0,
                 poll_seconds: float = 15.0, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 text_encoder: str = "cpu") -> None:
        self.transport = transport
        self.units_per_hour = units_per_hour
        self.text_encoder = text_encoder   # videogen.comfyui.text_encoder: where the LTX graph runs the text encoder
        self.poll_timeout = poll_timeout
        self.poll_seconds = poll_seconds
        self.sleep = sleep
        self.clock = clock
        self.uploader: Callable[[Path], str] | None = None   # unused: inputs go to ComfyUI itself
        self.freed = False   # the models were unloaded before this provider's first job

    def check_compiler(self) -> None:
        """Refuse (:class:`VidgenError`) unless the server's ComfyUI runs with ``--disable-comfy-compiler``
        (a shot with a sheet: LTX Multi IC-LoRA never finishes a step with the model compiler on)."""
        off = self.transport.compiler_off()
        if off is True:
            return
        state = "no ComfyUI runs there, or it does not report its arguments" if off is None else "its ComfyUI runs with the model compiler on"
        raise VidgenError(f"{self.transport.where}: {state}; a shot with sheet: needs ComfyUI started with --disable-comfy-compiler "
                          f"(with the compiler on, LTX Multi IC-LoRA never finishes a step): {self.transport.compiler_fix}")

    def check_credentials(self) -> None:
        """Whether the server is there (no key is needed)."""
        self.transport.check()

    def submit(self, request: VideoRequest, drop: set[str] | frozenset[str] = frozenset(), *, on_sending: Callable[[], None] | None = None) -> JobState:
        """Fit the inputs, build the graph and queue it; a failure before ComfyUI queued it is a refused
        submit. A request with a sheet is checked first (:meth:`check_compiler`); the first job unloads the models before it."""
        from dataclasses import replace

        from vidgen.videogen import request_hash
        from vidgen.videogen.openrouter import SubmitRefused

        if request.sheet is not None:
            self.check_compiler()
        with tempfile.TemporaryDirectory() as tmp:
            job = replace(prepare_job(request, Path(tmp), request_hash(request), text_encoder=self.text_encoder), free_before=not self.freed)
            if on_sending is not None:
                on_sending()
            try:
                job_id = self.transport.submit(job)
            except VidgenError as exc:
                raise SubmitRefused(f"{self.transport.where}: {missing_weights_hint(str(exc))}") from None
            self.freed = True
        log.info("ComfyUI job %s queued on %s", job_id, self.transport.where)
        return JobState(job_id, "pending", cost=0.0)

    def status(self, job_id: str) -> JobState:
        """The job as the server reports it (``usage``: GPU seconds and compute units once it ended)."""
        result = self.transport.outcome(job_id)
        status = {"running": "in_progress", "completed": "completed"}.get(result["status"], "failed")
        usage = self.usage(result.get("seconds")) if status != "in_progress" else None
        error = result.get("error")
        return JobState(job_id, status, cost=0.0, error=missing_weights_hint(error) if error else error, usage=usage)

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


# ----- the restyled first frame ---------------------------------------------------------------


#: The model that restyles a first frame (``first_frame: restyled``), as the plan names it.
RESTYLE_MODEL = "Qwen-Image-Edit-2511 (GGUF Q4_K_M, Lightning 4 steps)"


def restyle_picture(settings: ComfyuiSettings, source: Path, dest: Path, *, width: int, height: int, prompt: str, seed: int,
                    poll_timeout: float = 900.0, say: Callable[[str], None] | None = None,
                    transport: Transport | None = None, sleep: Callable[[float], None] = time.sleep) -> Mapping[str, Any]:
    """Write ``dest``: a photoreal version of the picture ``source`` at ``width`` x ``height``
    (cover, centre crop) made by Qwen-Image-Edit-2511 with ``prompt`` on the ComfyUI server of
    ``settings`` (``transport`` replaces it in tests); the models are unloaded afterwards. Returns
    the job's usage (GPU seconds, compute units)."""
    import hashlib

    from vidgen.videogen import qwen_graph

    server = transport or make_transport(settings, poll_timeout=poll_timeout, say=say)
    provider = ComfyUIVideoProvider(server, units_per_hour=settings.units_per_hour, poll_timeout=poll_timeout, poll_seconds=5.0, sleep=sleep)
    provider.check_credentials()
    key = hashlib.sha256(source.read_bytes() + f"|{prompt}|{seed}|{width}x{height}".encode("utf-8")).hexdigest()[:16]
    with tempfile.TemporaryDirectory() as tmp:
        up = fit_picture(source, Path(tmp) / f"vidgen_{key}_restyle_in.png", width=round(width * qwen_graph.UPSCALE),
                         height=round(height * qwen_graph.UPSCALE), lanczos=True)
        graph = qwen_graph.qwen_graph(f"vidgen_{key}_restyled", prompt, seed, width=width, height=height, image=up.name, full=False)
        try:
            job_id = server.submit(PreparedJob(graph, {up.name: up}, output="output.png", free_after=True))
        except VidgenError as exc:
            raise VidgenError(f"{server.where}: could not queue the restyle of {source.name}: {exc}") from None
    done = provider.wait(JobState(job_id, "pending", cost=0.0))
    if done.status != "completed":
        raise VidgenError(f"{server.where}: the restyle of {source.name} failed: {done.error or done.status}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    provider.download(job_id, dest)
    return dict(done.usage or provider.usage(None))


__all__ = [
    "RESTYLE_MODEL", "restyle_picture",
    "ColabTransport", "ComfyUIVideoProvider", "HttpTransport", "PreparedJob", "VM_URL", "WORKFLOWS", "Workflow",
    "check_workflow_request", "find_workflow", "fit_control", "fit_picture", "guide_problem", "make_transport", "missing_weights_hint", "on_colab_vm",
    "prepare_job", "workflow_estimate", "workflow_records",
]
