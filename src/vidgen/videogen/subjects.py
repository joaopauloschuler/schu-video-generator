"""Sheet panels of the generated shots' subjects (``subjects:``, DESIGN.md §113.24): ``vidgen generate subjects``.

Each view of a subject is a still of vidgen's own render (``from: {scene, at}``: the frame of the
scene's finished render without overlays or takes) or a picture file (``image:``), cropped
(``crop:``) and placed on a :data:`PANEL_SIZE` picture (an object fitted whole on black, a
location filled). Qwen-Image-Edit-2511 (:mod:`.qwen_graph`, the restyled first frame's model)
makes it a clean picture on the ComfyUI server: the object alone on plain black, product-style, or
the place itself; no text. A panel is never taken from a video model's frames.

All panels to make go in **one batch**: the models are unloaded before the first job (a video model
left in the GPU), the image model stays loaded between the jobs, and it is unloaded once after the
last one. Each panel is ``sheets/<subject>/<view>.png`` with a record ``<view>.json`` beside it
(:func:`panel_record`); a panel is made again only when its source changed (the scene, its time
or crop, the picture file, the look, the text or the seed: :class:`PanelSources`, free and offline)
or with ``force``. When only the scene's fingerprint changed and its still is the same picture,
the record is updated and nothing is sent.

A shot's ``subjects:`` composes its sheet from these panels (:mod:`.sheet_layout`, when its inputs
are made); a shot whose panels are missing or out of date is blocked.
"""

from __future__ import annotations

import json
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen.config import Subject, SubjectView
from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic
from vidgen.project import Project
from vidgen.soundfont import file_sha256

#: Where the panels are kept, relative to the project.
SUBJECTS_DIR = Path("sheets")
#: The size of every panel picture (the image model's input and output; multiples of 16).
PANEL_SIZE = (1440, 768)
#: The panel record's format version.
RECORD_VERSION = 1
#: The image model's seed when a subject gives none.
DEFAULT_SEED = 42
#: The image model of the panels, as records and the plan name it.
PANEL_MODEL = "Qwen-Image-Edit-2511 (GGUF Q4_K_M, Lightning 4 steps)"

OBJECT_PROMPT = (
    "Make this a clean product-style photograph of {look}, {text}. Show it alone, whole and centred, on a plain "
    "pure black background: remove everything else (sky, water, ground, clouds, other objects). Keep its shape, "
    "proportions, colours and markings as in the picture; real materials with panel lines and subtle wear, soft "
    "even studio light. No text, letters, numbers or logos. Real photograph, not CGI.")
LOCATION_PROMPT = (
    "Turn this computer-graphics render into a real photograph of {look}, {text}. Show only the place itself: "
    "remove every aircraft, vehicle, person and other object. Replace regular, repeating computer-generated "
    "patterns with real, irregular natural detail; real light and haze. No text, letters or logos. "
    "Real 35 mm photograph, natural colours, not CGI.")


@dataclass(frozen=True)
class Panel:
    """One view of a subject: its names, settings and files."""

    subject: str
    view: str
    spec: Subject
    source: SubjectView
    path: Path

    @property
    def record_path(self) -> Path:
        """``<view>.json`` beside the panel."""
        return self.path.with_suffix(".json")

    @property
    def label(self) -> str:
        """``subject/view``."""
        return f"{self.subject}/{self.view}"

    @property
    def prompt(self) -> str:
        """The image model's instruction (from the subject's ``look`` and the view's ``text``)."""
        template = LOCATION_PROMPT if self.spec.location else OBJECT_PROMPT
        return template.format(look=self.spec.look.strip().rstrip("."), text=self.source.text.strip().rstrip("."))

    @property
    def seed(self) -> int:
        """The subject's ``seed``, else :data:`DEFAULT_SEED`."""
        return DEFAULT_SEED if self.spec.seed is None else self.spec.seed

    def words(self, first: bool) -> str:
        """What the panel shows in a sheet prompt: the look on the subject's ``first`` panel, then "the same <name>"."""
        text = self.source.text.strip().rstrip(".")
        if self.spec.location or first:
            return f"{self.spec.look.strip().rstrip('.')}, {text}"
        return f"the same {self.subject.replace('_', ' ')}, {text}"


def subject_panels(project: Project, name: str) -> list[Panel]:
    """The panels of subject ``name`` (an unknown name is a :class:`VidgenError`)."""
    from vidgen.videogen import did_you_mean

    subjects = project.config.subjects
    if name not in subjects:
        raise VidgenError(f"no subject {name!r}{did_you_mean(name, list(subjects))}; subjects: {', '.join(subjects) or 'none (add subjects: to video.yaml)'}")
    spec = subjects[name]
    folder = project.root / SUBJECTS_DIR / name
    return [Panel(name, view, spec, source, folder / f"{view}.png") for view, source in zip(spec.view_names, spec.views)]


def shot_panels(project: Project, names: Sequence[str]) -> list[Panel]:
    """The panels of the subjects ``names``, in order (a shot's sheet)."""
    return [panel for name in names for panel in subject_panels(project, name)]


def sheet_panels(panels: Sequence[Panel]) -> list[Any]:
    """``panels`` as :class:`~vidgen.videogen.sheet_layout.SheetPanel` (the words of each)."""
    from vidgen.videogen.sheet_layout import SheetPanel

    return [SheetPanel(p.path, p.words(k == 0 or panels[k - 1].subject != p.subject)) for k, p in enumerate(panels)]


def shot_sheet_prompt(panels: Sequence[Panel], width: int, height: int) -> str:
    """The ``sheet_prompt`` of a sheet of ``panels`` at ``width`` x ``height``."""
    from vidgen.videogen.sheet_layout import choose_grid, sheet_prompt

    columns, rows = choose_grid(width, height, [PANEL_SIZE] * len(panels))
    return sheet_prompt(sheet_panels(panels), columns, rows)


def read_record(panel: Panel) -> dict[str, Any]:
    """The panel's record (``{}`` when missing, unreadable or of another version)."""
    try:
        doc = json.loads(panel.record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) and doc.get("version") == RECORD_VERSION else {}


def panel_record(panel: Panel, source: dict[str, Any], still_sha256: str, *, seconds: float | None, usage: dict[str, Any] | None,
                 made: str) -> dict[str, Any]:
    """The record written beside a panel. ``source`` is what decides whether it is current; a later
    ``approved`` flag goes beside it at the top level (not in ``source``), so approving changes nothing else."""
    return {
        "version": RECORD_VERSION, "subject": panel.subject, "view": panel.view, "model": PANEL_MODEL, "prompt": panel.prompt,
        "seed": panel.seed, "size": list(PANEL_SIZE), "source": source, "still_sha256": still_sha256,
        "sha256": file_sha256(panel.path), "seconds": seconds, "usage": usage, "made": made,
    }


def _write_record(panel: Panel, record: dict[str, Any]) -> None:
    write_text_atomic(panel.record_path, json.dumps(record, indent=1, sort_keys=True, ensure_ascii=True) + "\n")


@dataclass
class PanelSources:
    """What each panel of ``project`` is made from now (free and offline: no render, no network):
    the still (the scene's fingerprint without overlays or takes, the time and crop; or the picture
    file's SHA-256) and the edit (prompt, seed, model, size)."""

    project: Project
    _scenes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _still_project: Project | None = None

    @property
    def still_project(self) -> Project:
        """The project the stills are rendered by: the finished render without overlays or takes."""
        if self._still_project is None:
            self._still_project = Project.load(self.project.config_file, variant=self.project.variant).without_takes()
        return self._still_project

    def _scene(self, scene_id: str) -> dict[str, Any]:
        if scene_id not in self._scenes:
            from vidgen import extensions
            from vidgen.render.fingerprint import scene_fingerprint

            source = self.still_project
            size = source.render_format(False)
            with extensions.project_session(source):
                digest = scene_fingerprint(source, scene_id)
            self._scenes[scene_id] = {"scene_fingerprint": digest, "render": [size.width, size.height, size.fps]}
        return self._scenes[scene_id]

    def source(self, panel: Panel) -> dict[str, Any]:
        """The panel's current source (a missing picture file: its SHA-256 is ``None``)."""
        view = panel.source
        if view.from_ is not None:
            still: dict[str, Any] = {"scene": view.from_.scene, "at": view.from_.at, **self._scene(view.from_.scene)}
        else:
            assert view.image is not None
            picture = self.project.root / view.image
            still = {"image": view.image, "image_sha256": file_sha256(picture) if picture.is_file() else None}
        still["crop"] = view.crop
        edit = {"prompt": panel.prompt, "seed": panel.seed, "model": PANEL_MODEL, "size": list(PANEL_SIZE)}
        return {"still": still, "edit": edit, **({"location": True} if panel.spec.location else {})}

    def state(self, panel: Panel) -> str | None:
        """Why ``panel`` must be made (again), ``None`` when it is current."""
        record = read_record(panel)
        if not panel.path.is_file() or not record:
            return "not made yet"
        current, wrote = self.source(panel), record.get("source") or {}
        if current["still"].get("image_sha256", "") is None:
            return f"the picture {panel.source.image} is missing"
        if wrote.get("edit") != current["edit"] or wrote.get("location") != current.get("location"):
            return "its look, text or seed changed"
        if wrote.get("still") != current["still"]:
            return "its still changed (the scene, its time or crop, or the picture)"
        if record.get("sha256") != file_sha256(panel.path):
            return "the panel file was changed after it was made"
        return None


def panel_lines(project: Project, sources: PanelSources) -> list[str]:
    """The plan's lines about the subjects' panels."""
    lines = ["subjects (sheet panels; `vidgen generate subjects` makes them with the image model on the ComfyUI server):"]
    for name in project.config.subjects:
        for panel in subject_panels(project, name):
            why = sources.state(panel)
            shown = panel.path.relative_to(project.root).as_posix()
            lines.append(f"  {panel.label}: {shown} " + ("(current)" if why is None else f"- {why}"))
    return lines


# ----- the stills ----------------------------------------------------------------------------------


def place_still(picture: Any, crop: list[int] | None, location: bool) -> Any:
    """The image model's input: ``picture`` cropped to ``crop``, then on :data:`PANEL_SIZE`: a
    location fills it (cover, centre crop), an object is fitted whole on black."""
    from PIL import Image, ImageOps

    picture = picture.convert("RGB")
    if crop is not None:
        x, y, w, h = crop
        if x + w > picture.width or y + h > picture.height:
            raise VidgenError(f"crop {crop} goes past the still's {picture.width}x{picture.height} pixels")
        picture = picture.crop((x, y, x + w, y + h))
    if location:
        return ImageOps.fit(picture, PANEL_SIZE, Image.LANCZOS)
    scale = min(PANEL_SIZE[0] / picture.width, PANEL_SIZE[1] / picture.height)
    size = (max(1, round(picture.width * scale)), max(1, round(picture.height * scale)))
    canvas = Image.new("RGB", PANEL_SIZE, (0, 0, 0))
    canvas.paste(picture.resize(size, Image.LANCZOS), ((PANEL_SIZE[0] - size[0]) // 2, (PANEL_SIZE[1] - size[1]) // 2))
    return canvas


def write_still(project: Project, sources: PanelSources, panel: Panel, dest: Path,
                render: Callable[[Project, str], Path] | None = None) -> None:
    """Write ``dest``: the image model's input of ``panel`` (``render(project, scene)`` returns a
    scene's finished video without overlays or takes; it replaces the render in tests)."""
    from PIL import Image

    view = panel.source
    with tempfile.TemporaryDirectory(prefix="vidgen-still-") as scratch:
        if view.from_ is not None:
            from vidgen.render.ffmpeg import find_ffmpeg
            from vidgen.videogen.inputs import frame_at

            video = (render or _rendered_scene)(sources.still_project, view.from_.scene)
            frame = Path(scratch) / "frame.png"
            frame_at(find_ffmpeg(), video, frame, view.from_.at)
        else:
            assert view.image is not None
            frame = project.root / view.image
            if not frame.is_file():
                raise VidgenError(f"subjects.{panel.subject}: the picture {view.image} of view {panel.view} does not exist")
        try:
            with Image.open(frame) as opened:
                placed = place_still(opened, view.crop, panel.spec.location)
        except OSError as exc:
            raise VidgenError(f"subjects.{panel.subject}: cannot read the still of view {panel.view}: {exc}") from None
    dest.parent.mkdir(parents=True, exist_ok=True)
    placed.save(dest, format="PNG")


def _rendered_scene(still_project: Project, scene_id: str) -> Path:
    """The finished render of ``scene_id`` without overlays or takes (rendered when not current)."""
    from vidgen.videogen.inputs import scene_render

    return scene_render(still_project, scene_id).video


# ----- the batch -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class PanelOutcome:
    """What happened to a panel: ``kept`` (current), ``recorded`` (same still, record updated) or
    ``made`` (with the job's GPU ``usage`` and its ``seconds`` door to door)."""

    panel: Panel
    action: str
    usage: dict[str, Any] | None = None
    seconds: float | None = None


@dataclass
class PanelsResult:
    """What :func:`make_panels` did; ``batch_seconds``: the image model's batch, door to door."""

    outcomes: list[PanelOutcome] = field(default_factory=list)
    batch_seconds: float | None = None


def select_panels(project: Project, names: Sequence[str]) -> list[Panel]:
    """The panels of the subjects ``names`` (all subjects when empty)."""
    chosen = list(names) or list(project.config.subjects)
    if not chosen:
        raise VidgenError("this video has no subjects: (add them to video.yaml, see `vidgen guide` / docs/CONFIG.md)")
    return shot_panels(project, list(dict.fromkeys(chosen)))


def make_panels(
    project: Project, names: Sequence[str] = (), *, force: bool = False, out: Callable[[str], None] = print,
    transport: Any = None, render: Callable[[Project, str], Path] | None = None, sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> PanelsResult:
    """Make the panels of the subjects ``names`` (all when empty) that are not current (all with
    ``force``) in one batch on the ComfyUI server (``transport`` replaces it in tests): unload the
    models, run every panel's job, unload the image model once after the last."""
    panels = select_panels(project, names)
    settings = project.config.videogen.comfyui
    sources = PanelSources(project)
    result = PanelsResult()
    todo: list[tuple[Panel, Path]] = []
    with tempfile.TemporaryDirectory(prefix="vidgen-panels-") as scratch:
        for panel in panels:
            why = "made again (--force)" if force else sources.state(panel)
            if why is None:
                result.outcomes.append(PanelOutcome(panel, "kept"))
                out(f"{panel.label}: {panel.path.relative_to(project.root).as_posix()} is current (kept, no GPU time)")
                continue
            if settings is None:
                raise VidgenError("the panels are made on the ComfyUI server: set videogen.provider: comfyui and videogen.comfyui (url: or colab:)")
            still = Path(scratch) / f"vidgen_{panel.subject}_{panel.view}_still.png"
            write_still(project, sources, panel, still, render)
            record = read_record(panel)
            source = sources.source(panel)
            same = (record.get("still_sha256") == file_sha256(still) and (record.get("source") or {}).get("edit") == source["edit"]
                    and panel.path.is_file() and record.get("sha256") == file_sha256(panel.path))
            if same and not force:
                _write_record(panel, {**record, "source": source})
                result.outcomes.append(PanelOutcome(panel, "recorded"))
                out(f"{panel.label}: {why}, but its still is the same picture: kept, record updated (no GPU time)")
                continue
            out(f"{panel.label}: {why}: to make")
            todo.append((panel, still))
        if todo:
            assert settings is not None
            begin = clock()
            result.outcomes += _run_batch(project, settings, sources, todo, out=out, transport=transport, sleep=sleep, clock=clock)
            result.batch_seconds = round(clock() - begin, 1)
            out(f"{len(todo)} panel(s) made in one batch in {result.batch_seconds:g} s; the image model was unloaded after the last one")
    return result


def _run_batch(project: Project, settings: Any, sources: PanelSources, todo: Sequence[tuple[Panel, Path]], *, out: Callable[[str], None],
               transport: Any, sleep: Callable[[float], None], clock: Callable[[], float]) -> list[PanelOutcome]:
    """Run ``todo`` (panel, its still) one job after another; the first unloads the models before
    it, the last unloads them after it."""
    import hashlib
    from datetime import datetime, timezone

    from vidgen.videogen import JobState
    from vidgen.videogen.comfyui import ComfyUIVideoProvider, PreparedJob, make_transport
    from vidgen.videogen.qwen_graph import qwen_graph

    poll_timeout = project.config.videogen.poll_timeout
    server = transport or make_transport(settings, poll_timeout=poll_timeout, say=out)
    provider = ComfyUIVideoProvider(server, units_per_hour=settings.units_per_hour, poll_timeout=poll_timeout, poll_seconds=5.0, sleep=sleep, clock=clock)
    provider.check_credentials()
    out(f"making {len(todo)} panel(s) on {server.where} with {PANEL_MODEL}, {PANEL_SIZE[0]}x{PANEL_SIZE[1]}, in one batch")
    outcomes = []
    for k, (panel, still) in enumerate(todo):
        begin = clock()
        key = hashlib.sha256(still.read_bytes() + f"|{panel.prompt}|{panel.seed}".encode("utf-8")).hexdigest()[:16]
        upload = still.with_name(f"vidgen_{key}_panel_in.png")
        still.replace(upload)
        graph = qwen_graph(f"vidgen_{key}_panel", panel.prompt, panel.seed, width=PANEL_SIZE[0], height=PANEL_SIZE[1], image=upload.name, full=False)
        last = k == len(todo) - 1
        job = PreparedJob(graph, {upload.name: upload}, output="output.png", free_before=k == 0, free_after=last)
        try:
            job_id = server.submit(job)
        except VidgenError as exc:
            raise VidgenError(f"{server.where}: could not queue panel {panel.label}: {exc}{_left_loaded(k > 0)}") from None
        done = provider.wait(JobState(job_id, "pending", cost=0.0))
        if done.status != "completed":
            raise VidgenError(f"{server.where}: panel {panel.label} failed: {done.error or done.status}{_left_loaded(not last)}")
        panel.path.parent.mkdir(parents=True, exist_ok=True)
        provider.download(job_id, panel.path)
        usage = dict(done.usage or provider.usage(None))
        seconds = round(clock() - begin, 1)
        made = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_record(panel, panel_record(panel, sources.source(panel), file_sha256(upload), seconds=seconds, usage=usage, made=made))
        gpu = usage.get("gpu_seconds")
        out(f"{panel.label}: {panel.path.relative_to(project.root).as_posix()} ({'GPU time not reported' if gpu is None else f'{gpu:g} s GPU'}, {seconds:g} s door to door)")
        outcomes.append(PanelOutcome(panel, "made", usage, seconds))
    return outcomes


def _left_loaded(loaded: bool) -> str:
    """What a failed job leaves in the GPU's memory (``loaded``: the image model may be there)."""
    if not loaded:
        return ""
    return "; the image model may still be loaded: the next `vidgen generate run` unloads the models before its first job"


# ----- a shot's sheet ------------------------------------------------------------------------------


#: A shot's composed sheet, in its inputs folder.
SHEET_NAME = "sheet.png"


def sheet_source(panels: Sequence[Panel], width: int, height: int) -> dict[str, Any]:
    """What a shot's composed sheet is made from (the panels must exist)."""
    return {"sheet_panels": [[p.subject, p.view, file_sha256(p.path)] for p in panels], "sheet_size": [width, height]}


def compose_shot_sheet(panels: Sequence[Panel], width: int, height: int, dest: Path) -> None:
    """Write ``dest``: the shot's sheet of ``panels`` at ``width`` x ``height``, and record it in the shot's ``inputs.json``."""
    from vidgen.videogen.freshness import record_input
    from vidgen.videogen.sheet_layout import compose_sheet

    compose_sheet(sheet_panels(panels), width, height, dest)
    record_input(dest, sheet_source(panels, width, height))


__all__ = [
    "DEFAULT_SEED", "LOCATION_PROMPT", "OBJECT_PROMPT", "PANEL_MODEL", "PANEL_SIZE", "RECORD_VERSION", "SHEET_NAME", "SUBJECTS_DIR",
    "Panel", "PanelOutcome", "PanelSources", "PanelsResult", "compose_shot_sheet", "make_panels", "panel_lines", "panel_record",
    "place_still", "read_record", "select_panels", "sheet_panels", "sheet_source", "shot_panels", "shot_sheet_prompt", "subject_panels",
    "write_still",
]
