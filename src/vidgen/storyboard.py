"""``vidgen storyboard``: contact sheets of a video's frame stills (DESIGN.md §14).

:func:`make_storyboard` makes sure every selected scene has current stills (rendering with
frame capture only the scenes whose stills are missing, made at another count/format, or stale
by :func:`~vidgen.render.fingerprint.scene_fingerprint`), then composes with
:mod:`vidgen.sheets`:

- ``<render_dir>/storyboard/video-<p>.png``: the whole video (only without ``scenes``);
- ``<render_dir>/storyboard/scenes/<scene>-<p>.png``: one sheet per scene, larger stills.

``<p>`` is the page number (1, 2, ...): long videos are split into pages of bounded size.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vidgen.config import FormatConfig
from vidgen.errors import VidgenError
from vidgen.fileio import remove_file, write_bytes_atomic
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.render.worker import (
    remove_tree,
    scene_activity_path,
    scene_frames_dir,
    scene_layout_path,
    scene_timings_path,
)
from vidgen.sheets import DEFAULT_WIDTH, MAX_WIDTH, MIN_WIDTH, SheetPage, SheetScene, SheetStill, compose_pages
from vidgen.transitions import join_overlaps


@dataclass(frozen=True)
class Sheet:
    """One written page: ``kind`` ``video`` (the whole video) or ``scene`` (``scene`` is its id)."""

    kind: Literal["video", "scene"]
    scene: str | None
    page: int
    pages: int
    path: Path
    width: int
    height: int
    stills: tuple[SheetStill, ...]


@dataclass
class StoryboardResult:
    """What :func:`make_storyboard` did: the sheets (video pages first, then scenes in config
    order), the scenes rendered for it and those whose stills were reused, and the
    ``(scene_id, message)`` warnings of the workers."""

    folder: Path
    format: FormatConfig
    preview: bool
    per_beat: int
    sheets: list[Sheet] = field(default_factory=list)
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)


def storyboard_dir(project: Project, preview: bool) -> Path:
    """``<render_dir>/storyboard``."""
    return project.render_dir(preview) / "storyboard"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _matches_format(timings: dict[str, Any], fmt: FormatConfig) -> bool:
    meta = timings.get("render", {})
    return (meta.get("width"), meta.get("height"), meta.get("fps")) == (fmt.width, fmt.height, fmt.fps)


def stills_current(project: Project, preview: bool, scene_id: str, per_beat: int | None) -> bool:
    """True if the scene's stills and layout dump exist at ``per_beat`` per beat (``None``: any
    count), were made at the current format and nothing the scene depends on changed since (its
    render fingerprint matches)."""
    timings = _read_json(scene_timings_path(project, preview, scene_id))
    folder = scene_frames_dir(project, preview, scene_id)
    index = _read_json(folder / "index.json")
    if timings is None or index is None or not _matches_format(timings, project.render_format(preview)):
        return False
    meta = timings.get("render", {})
    count = meta.get("frames")
    if not count or index.get("per_beat") != count or per_beat not in (None, count):
        return False
    if not scene_layout_path(project, preview, scene_id).is_file():
        return False
    if not scene_activity_path(project, preview, scene_id).is_file():
        return False
    if not all((folder / still["path"]).is_file() for still in index.get("frames", [])):
        return False
    return meta.get("fingerprint") == scene_fingerprint(project, scene_id)


def scene_starts(project: Project, preview: bool) -> dict[str, float | None]:
    """Each scene's start in the video, from the rendered scenes' durations (all ``None`` if a
    scene has no render at the current format)."""
    fmt = project.render_format(preview)
    found = []
    for spec in project.config.scenes:
        timings = _read_json(scene_timings_path(project, preview, spec.id))
        if timings is None or not _matches_format(timings, fmt):
            return {s.id: None for s in project.config.scenes}
        found.append(timings)
    frames = [round(float(t["duration"]) * fmt.fps) for t in found]
    speech = [t["beats"][-1]["end"] if t["beats"] else None for t in found]
    overlaps = join_overlaps(project.config, fmt.fps, frames, speech)  # crossfades (DESIGN.md §49)
    starts: dict[str, float | None] = {}
    offset = 0.0
    for spec, timings, overlap in zip(project.config.scenes, found, overlaps):
        offset -= overlap / fmt.fps
        starts[spec.id] = round(offset, 6)
        offset += float(timings["duration"])
    return starts


def _sheet_scene(project: Project, preview: bool, scene_id: str, start: float | None) -> SheetScene:
    spec = project.scene(scene_id)
    timings = _read_json(scene_timings_path(project, preview, scene_id))
    folder = scene_frames_dir(project, preview, scene_id)
    index = _read_json(folder / "index.json")
    if timings is None or index is None:
        raise VidgenError(f"scene '{scene_id}' has no stills in {folder}; run `vidgen storyboard` again")
    texts = {beat["id"]: beat["text"] for beat in timings["beats"]}
    stills = tuple(
        SheetStill(
            scene_id=scene_id,
            beat_id=still["beat"],
            k=still["k"],
            n=still["n"],
            scene_time=still["time"],
            time=None if start is None else round(start + still["time"], 6),
            path=folder / still["path"],
            text=texts.get(still["beat"]) if still["beat"] is not None else None,
        )
        for still in index["frames"]
    )
    ids = [s.id for s in project.config.scenes]
    return SheetScene(
        id=scene_id,
        type=spec.type,
        number=ids.index(scene_id) + 1,
        total=len(ids),
        start=start,
        duration=float(timings["duration"]),
        beats=len(spec.beats),
        stills=stills,
    )


def _subtitle(project: Project, preview: bool, per_beat: int, video_times: bool) -> str:
    fmt = project.render_format(preview)
    parts = [f"{'preview' if preview else 'final'} {fmt.width}x{fmt.height}"]
    if project.variant:
        parts.append(f"variant {project.variant}")
    if per_beat == 1:
        parts.append("one still per beat: its last frame")
    else:
        parts.append(f"{per_beat} stills per beat, evenly spaced, the last at the beat's end")
    parts.append("times in the video" if video_times else "times from the scene start")
    return "  ·  ".join(parts)


def _write_pages(pages: list[SheetPage], folder: Path, stem: str, kind: Literal["video", "scene"], scene: str | None) -> list[Sheet]:
    sheets = []
    for number, page in enumerate(pages, start=1):
        path = folder / f"{stem}-{number}.png"
        buffer = io.BytesIO()
        page.image.save(buffer, format="PNG", optimize=False, compress_level=6)
        write_bytes_atomic(path, buffer.getvalue())
        sheets.append(
            Sheet(kind, scene, number, len(pages), path, page.image.width, page.image.height, tuple(page.stills))
        )
    return sheets


def _clear_old_sheets(folder: Path, scene_ids: list[str] | None) -> None:
    """Remove sheets that could be stale: everything, or (for ``scene_ids``) the video sheets and
    those scenes' sheets."""
    if scene_ids is None:
        remove_tree(folder)
        return
    old = list(folder.glob("video-*.png"))
    for sid in scene_ids:
        old.extend(p for p in (folder / "scenes").glob(f"{sid}-*.png") if p.stem.rsplit("-", 1)[0] == sid)
    for path in old:
        remove_file(path)


def make_storyboard(
    project: Project,
    *,
    preview: bool = True,
    scenes: list[str] | None = None,
    per_beat: int = 1,
    width: int = DEFAULT_WIDTH,
    jobs: int = 1,
    force: bool = False,
) -> StoryboardResult:
    """Render what is needed and write the contact sheets of ``project`` (loaded with its variant).

    ``scenes``: only these scenes' sheets (no whole-video sheet); ``per_beat``: stills per beat;
    ``width``: page width in px; ``jobs``: scenes rendered in parallel; ``force``: render the
    selected scenes even if their stills are current.
    """
    from vidgen.render.pipeline import render_scenes

    if per_beat < 1:
        raise VidgenError("--per-beat must be at least 1")
    if not MIN_WIDTH <= width <= MAX_WIDTH:
        raise VidgenError(f"--width must be between {MIN_WIDTH} and {MAX_WIDTH} pixels")
    if jobs < 1:
        raise VidgenError("--jobs must be at least 1")
    known = [s.id for s in project.config.scenes]
    unknown = [sid for sid in scenes or [] if sid not in known]
    if unknown:
        raise VidgenError(f"unknown scene(s): {', '.join(unknown)}; scenes: {', '.join(known)}")
    selected = [sid for sid in known if not scenes or sid in scenes]

    to_render = [sid for sid in selected if force or not stills_current(project, preview, sid, per_beat)]
    runs = render_scenes(project, preview, to_render, jobs=jobs, frames=per_beat)
    fmt = project.render_format(preview)
    folder = storyboard_dir(project, preview)
    result = StoryboardResult(
        folder=folder,
        format=fmt,
        preview=preview,
        per_beat=per_beat,
        rendered=runs.rendered,
        reused=[sid for sid in selected if sid not in runs.rendered],
        warnings=runs.warnings,
    )

    starts = scene_starts(project, preview)
    sections = [_sheet_scene(project, preview, sid, starts[sid]) for sid in selected]
    frame_size = (fmt.width, fmt.height)
    title = f"{project.config.title} — storyboard"
    _clear_old_sheets(folder, scenes or None)
    if not scenes:
        pages = compose_pages(
            title, _subtitle(project, preview, per_beat, True), sections, frame_size, width=width
        )
        result.sheets.extend(_write_pages(pages, folder, "video", "video", None))
    for section in sections:
        pages = compose_pages(
            title,
            _subtitle(project, preview, per_beat, False),
            [section],
            frame_size,
            width=width,
            detail=True,
            video_times=False,
        )
        result.sheets.extend(_write_pages(pages, folder / "scenes", section.id, "scene", section.id))
    return result
