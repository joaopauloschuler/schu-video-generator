"""``vidgen export gif|clip`` (DESIGN.md §53): a part of the rendered video as an animated GIF or
an MP4 clip, written to ``<project>/exports/``.

The source is the joined video ``<output>[_<variant>][_preview].mp4`` and its
``build/.../timings.json`` (where each scene starts): with a scene, ``--from`` / ``--to`` count
from the scene's start and default to its whole length; without one they are times in the video.

- **GIF**: one FFmpeg pass with a palette made for the clip (``palettegen``, every frame counted)
  and Sierra dithering (``paletteuse``; only the changed rectangle of each frame is dithered
  again, so still parts do not shimmer). With a size budget (``max_mb``) the frame rate and then
  the width are lowered until the file fits (:func:`next_try`), down to :data:`MIN_GIF_FPS` /
  :data:`MIN_GIF_WIDTH`.
- **Clip**: stream-copied (no quality loss, instant) when it starts on a keyframe of the video
  (scene starts are keyframes in a joined video without transitions) and keeps the size and
  frame rate; else re-encoded (H.264 CRF 18, frame-accurate). Silent unless ``audio``.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.fileio import remove_file, replace_file
from vidgen.project import Project
from vidgen.render import ffmpeg as ff

log = logging.getLogger("vidgen.export")

#: Default GIF width (16:9 and square videos) and height-limited width for 9:16 ones, frame rate.
GIF_WIDTH = 480
GIF_PORTRAIT_WIDTH = 270
GIF_FPS = 12
#: The smallest frame rate and width a size budget lowers a GIF to.
MIN_GIF_FPS = 5
MIN_GIF_WIDTH = 160
#: GIF encodes tried at most to meet a budget.
MAX_ATTEMPTS = 6


@dataclass
class ExportResult:
    """What :func:`export_gif` / :func:`export_clip` wrote: the file, the part of the video
    (``start`` / ``end`` in the video, ``scene`` or ``None``), its size and rate, ``method``
    (``palette`` for a GIF, ``copy`` or ``encode`` for a clip) and, for a GIF with a budget, every
    attempt ``{width, fps, bytes}``."""

    kind: str
    path: Path
    source: Path
    scene: str | None
    start: float
    end: float
    width: int
    height: int
    fps: float
    bytes: int
    method: str
    audio: bool = False
    max_mb: float | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def within_budget(self) -> bool | None:
        """Whether the file is within ``max_mb`` (``None`` without a budget)."""
        return None if self.max_mb is None else self.bytes <= self.max_mb * 1e6


def source_video(project: Project, preview: bool) -> tuple[Path, dict[str, Any]]:
    """The joined video and its combined timings; a :class:`VidgenError` when there is none."""
    video = project.output_path(preview)
    timings_file = project.render_dir(preview) / "timings.json"
    if not video.is_file() or not timings_file.is_file():
        hint = " (or add --preview to export from the preview render)" if not preview and project.output_path(True).is_file() else ""
        raise VidgenError(f"no rendered video {video.name} to export from; run `vidgen render{' --preview' if preview else ''}` first{hint}")
    timings = json.loads(timings_file.read_text(encoding="utf-8"))
    duration = ff.probe(video).duration
    if abs(duration - float(timings["duration"])) > 0.1:
        raise VidgenError(f"{timings_file} does not describe {video.name} (another render?); render it again")
    return video, timings


def resolve_range(timings: dict[str, Any], scene: str | None, start: float | None, end: float | None) -> tuple[float, float]:
    """``(start, end)`` in the video: ``start`` / ``end`` from the scene's start (default its
    whole length; ``end`` is kept within the scene), or video times without a scene."""
    total = float(timings["duration"])
    base, limit = 0.0, total
    if scene is not None:
        entries = {s["id"]: s for s in timings["scenes"]}
        if scene not in entries:
            raise VidgenError(f"unknown scene '{scene}'; scenes: {', '.join(entries)}")
        base = float(entries[scene]["start"])
        limit = min(total, base + float(entries[scene]["duration"]))
    first = base + (start or 0.0)
    last = min(limit, base + end) if end is not None else limit
    where = f"scene '{scene}' ({limit - base:.2f} s)" if scene is not None else f"the video ({total:.2f} s)"
    if start is not None and start < 0:
        raise VidgenError("--from must not be negative")
    if first >= last:
        raise VidgenError(f"nothing to export: --from {start or 0:g} to --to {end if end is not None else limit - base:g} is empty in {where}")
    return round(first, 6), round(last, 6)


def default_path(project: Project, preview: bool, kind: str, scene: str | None, start: float | None, end: float | None) -> Path:
    """``exports/<output>[_<variant>][_preview]_<scene or video>[_<from>-<to>s].<gif|mp4>``."""
    name = f"{project.export_stem(preview)}_{scene or 'video'}"
    if start is not None or end is not None:
        name += f"_{start or 0:g}-{'end' if end is None else f'{end:g}'}s"
    return project.exports_dir / f"{name}.{'gif' if kind == 'gif' else 'mp4'}"


def next_try(width: int, fps: float, size: int, budget: float) -> tuple[int, float]:
    """Width and frame rate for the next GIF encode when ``size`` bytes exceed ``budget``: a
    GIF's size grows about with ``width² x fps``, so the needed factor (with 10 % room) is
    split between them — first the frame rate (down to :data:`MIN_GIF_FPS`), the width takes
    the rest (down to :data:`MIN_GIF_WIDTH`)."""
    needed = budget / size * 0.9
    new_fps = min(fps, max(float(MIN_GIF_FPS), round(fps * needed ** (1 / 3), 2)))
    new_width = math.floor(width * math.sqrt(needed * fps / new_fps))
    return min(width, max(MIN_GIF_WIDTH, new_width)), new_fps


def _gif_graph(width: int, fps: float, colors: int = 256, dither: str = "sierra2_4a", hold: float = 0.0) -> str:
    pad = f",tpad=stop_mode=clone:stop_duration={hold:g}" if hold > 0 else ""
    return (
        f"[0:v]fps={fps:g},scale={width}:-1:flags=lanczos{pad},split[a][b];"
        f"[a]palettegen=max_colors={colors}:stats_mode=full[p];[b][p]paletteuse=dither={dither}:diff_mode=rectangle"
    )


def write_gif(
    ffmpeg: str,
    video: Path,
    path: Path,
    width: int,
    fps: float,
    start: float = 0.0,
    end: float | None = None,
    *,
    colors: int = 256,
    dither: str = "sierra2_4a",
    hold: float = 0.0,
) -> int:
    """Encode ``video`` (from ``start`` to ``end`` seconds, default its end) as a looping palette
    GIF ``width`` px wide at ``fps`` into ``path``, with a palette of ``colors`` (2-256),
    FFmpeg's ``dither`` method (``none`` for the smallest files of flat pictures) and the last
    frame held ``hold`` seconds; returns the file's size in bytes."""
    span = [] if end is None else ["-t", f"{end - start:.6f}"]
    graph = _gif_graph(width, fps, colors, dither, hold)
    ff.run_ffmpeg(
        ffmpeg,
        ["-ss", f"{start:.6f}", *span, "-i", str(video), "-filter_complex", graph, "-loop", "0", str(path)],
        f"writing {path.name}",
    )
    return path.stat().st_size


def export_gif(
    project: Project,
    preview: bool = False,
    scene: str | None = None,
    start: float | None = None,
    end: float | None = None,
    width: int | None = None,
    fps: float | None = None,
    max_mb: float | None = None,
    output: Path | None = None,
) -> ExportResult:
    """Write a palette GIF of a part of the rendered video (see the module docs)."""
    from PIL import Image

    if max_mb is not None and max_mb <= 0:
        raise VidgenError("--max-mb must be positive")
    video, timings = source_video(project, preview)
    first, last = resolve_range(timings, scene, start, end)
    fmt = timings["format"]
    width = width or min(fmt["width"], GIF_PORTRAIT_WIDTH if fmt["height"] > 1.2 * fmt["width"] else GIF_WIDTH)
    fps = min(float(fps or GIF_FPS), float(fmt["fps"]))
    if width < 16 or fps <= 0:
        raise VidgenError("--width must be at least 16 px and --fps positive")
    path = output or default_path(project, preview, "gif", scene, start, end)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.partial.gif")
    ffmpeg = ff.find_ffmpeg()
    attempts: list[dict[str, Any]] = []
    while True:
        size = write_gif(ffmpeg, video, tmp, width, fps, first, last)
        attempts.append({"width": width, "fps": fps, "bytes": size})
        if max_mb is None or size <= max_mb * 1e6 or len(attempts) >= MAX_ATTEMPTS:
            break
        lower = next_try(width, fps, size, max_mb * 1e6)
        if lower == (width, fps):  # at the smallest width and frame rate already
            break
        width, fps = lower
    try:
        replace_file(tmp, path)
    finally:
        remove_file(tmp)
    with Image.open(path) as gif:
        height = gif.size[1]
    result = ExportResult(
        "gif", path, video, scene, first, last, width, height, fps, path.stat().st_size, "palette",
        max_mb=max_mb, attempts=attempts if max_mb is not None else [],
    )
    if result.within_budget is False:
        log.warning(
            "%s is %.2f MB, over --max-mb %g even at %d px and %g fps; export a shorter part (--from / --to)",
            path.name, result.bytes / 1e6, max_mb, width, fps,
        )
    return result


def keyframe_times(video: Path) -> list[float]:
    """Times of the video stream's keyframes (packets only, nothing decoded)."""
    import av

    times = []
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        for packet in container.demux(stream):
            if packet.is_keyframe and packet.pts is not None and packet.time_base is not None:
                times.append(float(packet.pts * packet.time_base))
    return sorted(times)


def export_clip(
    project: Project,
    preview: bool = False,
    scene: str | None = None,
    start: float | None = None,
    end: float | None = None,
    width: int | None = None,
    fps: float | None = None,
    audio: bool = False,
    output: Path | None = None,
) -> ExportResult:
    """Write an MP4 clip of a part of the rendered video (see the module docs)."""
    video, timings = source_video(project, preview)
    first, last = resolve_range(timings, scene, start, end)
    fmt = timings["format"]
    if width is not None and width < 16:
        raise VidgenError("--width must be at least 16 px")
    if fps is not None and fps <= 0:
        raise VidgenError("--fps must be positive")
    resize = width is not None and width != fmt["width"]
    retime = fps is not None and fps != fmt["fps"]
    keyframe = None
    if not resize and not retime:
        tolerance = 0.5 / fmt["fps"]
        keyframe = next((k for k in keyframe_times(video) if abs(k - first) <= tolerance), None)
    path = output or default_path(project, preview, "clip", scene, start, end)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.partial.mp4")
    if keyframe is not None:
        method, first = "copy", round(keyframe, 6)
        # the sound is decoded from a second, sample-accurate seek (copied AAC packets would start
        # up to a packet early); `-frames:v` because `-t` alone lets a copy run a few frames long
        inputs = ["-ss", f"{first:.6f}", "-i", str(video)] + (["-ss", f"{first:.6f}", "-i", str(video)] if audio else [])
        streams = ["-map", "0:v:0"] + (["-map", "1:a:0?"] if audio else ["-an"])
        codecs = ["-c:v", "copy", "-frames:v", str(round((last - first) * fmt["fps"])), "-avoid_negative_ts", "make_zero"]
    else:
        method = "encode"
        inputs = ["-ss", f"{first:.6f}", "-i", str(video)]
        streams = ["-map", "0:v:0"] + (["-map", "0:a:0?"] if audio else ["-an"])
        filters = ([f"scale={width}:-2:flags=lanczos"] if resize else []) + ([f"fps={fps:g}"] if retime else [])
        codecs = (["-vf", ",".join(filters)] if filters else []) + ["-c:v", "libx264", "-crf", ff.VIDEO_CRF, "-pix_fmt", "yuv420p"]
    codecs += ["-c:a", "aac", "-b:a", ff.AUDIO_BITRATE] if audio else []
    try:
        ff.run_ffmpeg(
            ff.find_ffmpeg(),
            [
                *inputs, "-t", f"{last - first:.6f}", *streams, *codecs,
                "-map_chapters", "-1", "-movflags", "+faststart", str(tmp),
            ],
            f"writing {path.name}",
        )
        replace_file(tmp, path)
    finally:
        remove_file(tmp)
    info = ff.probe(path)
    return ExportResult(
        "clip", path, video, scene, first, last, info.width, info.height, float(info.fps), path.stat().st_size, method, audio=audio
    )
