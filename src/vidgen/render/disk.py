"""Disk use of a render: the frames clips ``web`` and ``3d`` scenes keep until
they play them are by far the largest files of a build folder (about 1 byte per pixel and
frame lossless for a detailed WebGL page, 26 MB per second at 720p30), so ``vidgen render``
estimates them before it starts and warns when the disk has less room, reports the build
folder's size after the join, and with ``render.keep_intermediates: false`` deletes them once
they are no longer needed.

- :func:`expected_bytes` estimates the frames clips the scenes to render will write.
- :func:`room_warning` is the warning when the free disk is lower than that.
- :func:`remove_frames_clips` deletes scenes' frames clips (and Manim's partial movie files).
- :func:`build_usage` measures the build folder.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from vidgen.project import Project

log = logging.getLogger("vidgen.render")

#: Bytes per pixel and frame of a frames clip, measured on Escapement's WebGL frames:
#: FFV1 0.92-1.01 (26-28 MB/s at 1280x720x30, 57.6 MB/s at 1920x1080x30), compact 0.20-0.22.
#: A flat page (text, slides) compresses far better; these are the upper end.
BYTES_PER_PIXEL = {"lossless": 1.0, "compact": 0.22}
#: The folders of a build folder that hold frames clips (``<scene_id>.mkv``).
CLIP_FOLDERS = ("web", "three_d")


def draws_frames(type_name: str) -> bool:
    """True for a scene type whose frames are drawn into a frames clip first: ``web``, ``3d``
    and extension types subclassing them."""
    from vidgen import registry
    from vidgen.web.entry import is_web_type

    if is_web_type(type_name):
        return True
    entry = registry.find(type_name)
    if entry is None:
        return type_name == "3d"
    return any(base.__module__ == "vidgen.scenes.scene_3d" and base.__name__ == "Scene3D" for base in entry.cls.__mro__)


def frames_clip_paths(project: Project, preview: bool, scene_id: str) -> list[Path]:
    """Where a scene's frames clip is kept (one of them exists for a ``web`` or ``3d`` scene)."""
    render_dir = project.render_dir(preview)
    return [render_dir / folder / f"{scene_id}.mkv" for folder in CLIP_FOLDERS]


def _scene_seconds(project: Project, preview: bool, scene_id: str) -> float:
    """A scene's length: its last render's, else its ``duration``, else its narration estimated
    from the word count (with the beats' padding)."""
    from vidgen.render.worker import scene_timings_path

    try:
        return float(json.loads(scene_timings_path(project, preview, scene_id).read_text(encoding="utf-8"))["duration"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    spec = project.scene(scene_id)
    if spec.duration:
        return float(spec.duration)
    narration = project.config.narration
    return sum(b.estimated_duration(narration.words_per_second) + (narration.pad if b.pause is None else b.pause) for b in spec.beats)


def expected_bytes(project: Project, preview: bool, scene_ids: Iterable[str], at_once: int | None = None) -> int:
    """About how many bytes the frames clips of ``scene_ids`` will take (scenes whose clip is
    already kept are left out: it is reused or replaced in place), drawn at the full frame
    size (a page in the body region is smaller) in the way ``render.intermediate`` asks.
    ``at_once``: only that many clips are kept at a time (``keep_intermediates: false``: the
    jobs running), so the largest ``at_once`` count."""
    fmt = project.render_format(preview)
    per_second = fmt.width * fmt.height * fmt.fps * BYTES_PER_PIXEL[project.config.render.intermediate]
    sizes = sorted((round(_scene_seconds(project, preview, sid) * per_second) for sid in scene_ids
                    if draws_frames(project.scene(sid).type)
                    and not any(p.is_file() for p in frames_clip_paths(project, preview, sid))), reverse=True)
    return sum(sizes if at_once is None else sizes[:at_once])


def free_bytes(path: Path) -> int:
    """Free bytes on the disk of ``path`` (its nearest existing folder)."""
    for folder in (path, *path.parents):
        if folder.exists():
            return shutil.disk_usage(folder).free
    return shutil.disk_usage(Path.cwd()).free


def size_text(n: int) -> str:
    """``n`` bytes as ``"12 KB"``, ``"160 MB"`` or ``"4.7 GB"`` (powers of 1000)."""
    if n >= 10**9:
        return f"{n / 1e9:.1f} GB"
    if n >= 10**6:
        return f"{n / 1e6:.0f} MB"
    return f"{max(n, 0) / 1e3:.0f} KB"


def room_warning(needed: int, free: int, compact: bool, cleaning: bool) -> str | None:
    """The warning when ``free`` bytes are fewer than the ``needed`` ones (``None`` otherwise),
    naming what would help."""
    if needed <= free:
        return None
    helps = [hint for hint, given in (
        ("render.intermediate: compact (--intermediate compact, about 4.6 times smaller)", compact),
        ("render.keep_intermediates: false (--clean-intermediates: each scene's clip is deleted once the scene is rendered)", cleaning),
    ) if not given] + ["--max-scenes N to render in steps"]
    return (f"the scenes to render may draw up to about {size_text(needed)} of frames clips (a detailed WebGL page; a flat one far less) "
            f"but the disk has {size_text(free)} free; "
            f"try {'; '.join(helps)}")


def remove_frames_clips(project: Project, preview: bool, scene_ids: Iterable[str]) -> int:
    """Delete the frames clips of ``scene_ids`` (their records stay, so the render fingerprint
    still knows what the pages loaded) and Manim's partial movie files of those scenes; returns
    the bytes freed. A scene rendered again later draws its frames again. A clip that cannot be
    deleted (Windows: open in a player) is left, with a warning."""
    media = project.render_dir(preview) / "media" / "videos"
    freed = 0
    for scene_id in scene_ids:
        for path in frames_clip_paths(project, preview, scene_id):
            if path.is_file():
                size = path.stat().st_size
                try:
                    path.unlink()
                except OSError as exc:
                    log.warning("could not delete %s (%s); it is kept", path, exc.strerror or exc)
                    continue
                freed += size
        partial = media / scene_id
        if partial.is_dir():
            freed += sum(p.stat().st_size for p in partial.rglob("*") if p.is_file())
            shutil.rmtree(partial, ignore_errors=True)
    return freed


@dataclass(frozen=True)
class BuildUsage:
    """Bytes in a build folder (``total``), of them in frames clips (``frames_clips``), and free
    on its disk (``free``)."""

    total: int
    frames_clips: int
    free: int


def build_usage(project: Project, preview: bool) -> BuildUsage:
    """What :class:`BuildUsage` says about ``project``'s build folder of this quality."""
    render_dir = project.render_dir(preview)
    total = clips = 0
    if render_dir.is_dir():
        for path in render_dir.rglob("*"):
            if path.is_file():
                size = path.stat().st_size
                total += size
                if path.suffix == ".mkv" and path.parent.name in CLIP_FOLDERS and path.parent.parent == render_dir:
                    clips += size
    return BuildUsage(total, clips, free_bytes(render_dir))


__all__ = ["BYTES_PER_PIXEL", "BuildUsage", "CLIP_FOLDERS", "build_usage", "draws_frames", "expected_bytes", "frames_clip_paths",
           "free_bytes", "remove_frames_clips", "room_warning", "size_text"]
