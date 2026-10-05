"""Render one scene in its own process (DESIGN.md §5.2)::

    python -m vidgen.render.worker <project_dir> <scene_id> --quality final|preview
        [--variant NAME] [--no-audio] [--progress]

Writes ``<render_dir>/scenes/<scene_id>.mp4`` and ``<render_dir>/timings/<scene_id>.json``
(``render_dir`` = ``build/<final|preview>[_<variant>]``). Exit code 0 on success, 1 for a
:class:`VidgenError` (message on stderr as ``error: ...``), 2 for any other exception (full
traceback on stderr, so extension authors see where their scene code failed).

Manim's global config is not re-entrant, which is why every scene gets a fresh process.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from vidgen import __version__
from vidgen.errors import VidgenError
from vidgen.project import Project

#: Manim's units on the shorter side of the frame (Manim's default frame height).
FRAME_SHORT_SIDE = 8.0

#: Characters that break Manim's own file handling (str.format templates, unescaped concat lists).
_UNSAFE_FOR_MANIM = ("'", "{", "}")


def scene_video_path(project: Project, preview: bool, scene_id: str) -> Path:
    """``<render_dir>/scenes/<scene_id>.mp4``: the rendered scene, before audio padding."""
    return project.render_dir(preview) / "scenes" / f"{scene_id}.mp4"


def scene_timings_path(project: Project, preview: bool, scene_id: str) -> Path:
    """``<render_dir>/timings/<scene_id>.json``: the scene's beat timings and render settings."""
    return project.render_dir(preview) / "timings" / f"{scene_id}.json"


def scene_audio_path(project: Project, preview: bool, scene_id: str) -> Path:
    """``<render_dir>/scenes/<scene_id>.wav``: Manim's uncompressed mix of the scene's sounds
    (only exists if the scene added any sound)."""
    return project.render_dir(preview) / "scenes" / f"{scene_id}.wav"


def frame_size(width: int, height: int) -> tuple[float, float]:
    """Manim frame size (units) for a pixel size: the shorter side is 8 units, square pixels.

    Landscape 1920x1080 -> 14.22 x 8 (Manim's default); portrait 1080x1920 -> 8 x 14.22.
    """
    if width >= height:
        return FRAME_SHORT_SIDE * width / height, FRAME_SHORT_SIDE
    return FRAME_SHORT_SIDE, FRAME_SHORT_SIDE * height / width


def configure_manim(
    project: Project, preview: bool, background: str, media_dir: Path, scene_id: str, progress: bool
) -> None:
    """Set Manim's global config for rendering ``scene_id`` of ``project``."""
    from manim import config

    fmt = project.render_format(preview)
    config.pixel_width = fmt.width
    config.pixel_height = fmt.height
    config.frame_rate = fmt.fps
    # Manim does not recompute the frame size when pixel sizes are set programmatically.
    config.frame_width, config.frame_height = frame_size(fmt.width, fmt.height)
    config.background_color = background
    config.disable_caching = True  # a cache hit would desynchronise beat timings from frames
    config.write_to_movie = True
    config.save_last_frame = False
    config.preview = False
    config.format = "mp4"
    config.media_dir = str(media_dir)
    config.video_dir = str(media_dir / "videos" / scene_id)
    config.partial_movie_dir = str(media_dir / "videos" / scene_id / "partial")
    config.output_file = scene_id
    config.progress_bar = "display" if progress else "none"
    config.verbosity = "WARNING"


def _manim_media_dir(render_dir: Path) -> tuple[Path, bool]:
    """Where Manim writes its intermediate files; ``(dir, is_temporary)``.

    Normally ``<render_dir>/media``. Manim cannot cope with ``'``, ``{`` or ``}`` in its paths,
    so for such project paths a temporary folder is used instead.
    """
    media = render_dir / "media"
    if not any(c in str(media.resolve()) for c in _UNSAFE_FOR_MANIM):
        return media, False
    tmp = Path(tempfile.mkdtemp(prefix="vidgen_"))
    if any(c in str(tmp) for c in _UNSAFE_FOR_MANIM):
        shutil.rmtree(tmp, ignore_errors=True)
        raise VidgenError(
            f"Manim cannot render in a folder whose path contains ' {{ or }}: {render_dir}; "
            "move the project or set TEMP/TMPDIR to a folder without these characters"
        )
    return tmp, True


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    return value


def write_json(path: Path, data: Any) -> None:
    """Write ``data`` as UTF-8 JSON atomically (temp file + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def render_scene(
    project_path: str | Path,
    scene_id: str,
    preview: bool,
    variant: str | None = None,
    audio: bool = True,
    progress: bool = False,
) -> Path:
    """Render one scene in this process (Manim's global config is modified); returns its video.

    Call it only in a fresh process: this is the body of the worker.
    """
    from vidgen import extensions, registry

    project = Project.load(project_path, variant=variant)
    theme = extensions.activate(project)
    spec = project.scene(scene_id)
    cls = registry.get(spec.type).cls
    render_dir = project.render_dir(preview)
    # A failed render must not leave the previous render behind to be reused by `--scene`.
    for stale in (scene_video_path, scene_audio_path, scene_timings_path):
        stale(project, preview, scene_id).unlink(missing_ok=True)
    media_dir, temporary = _manim_media_dir(render_dir)
    shutil.rmtree(media_dir / "videos" / scene_id, ignore_errors=True)  # no stale .wav from a previous run
    try:
        configure_manim(project, preview, theme.background, media_dir, scene_id, progress)
        scene = cls(spec, project, theme, audio=audio)
        scene.render()
        movie = Path(scene.renderer.file_writer.movie_file_path)
        if not movie.is_file():
            raise VidgenError(f"scene '{scene_id}' produced no video (does construct() animate or wait?)")
        target = scene_video_path(project, preview, scene_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(movie), str(target))
        wav = movie.with_suffix(".wav")  # written by Manim when the scene has sound
        if wav.is_file():
            shutil.move(str(wav), str(scene_audio_path(project, preview, scene_id)))
    finally:
        if temporary:
            shutil.rmtree(media_dir, ignore_errors=True)
    fmt = project.render_format(preview)
    timings = _round(scene.timings())
    timings["render"] = {
        "width": fmt.width,
        "height": fmt.height,
        "fps": fmt.fps,
        "audio": audio,
        "vidgen": __version__,
    }
    write_json(scene_timings_path(project, preview, scene_id), timings)
    return target


class _LevelFormatter(logging.Formatter):
    """``warning: <message>``, like the CLI (the parent re-prints these lines)."""

    def format(self, record: logging.LogRecord) -> str:
        return f"{record.levelname.lower()}: {record.getMessage()}"


def build_parser() -> argparse.ArgumentParser:
    """Arguments of ``python -m vidgen.render.worker``."""
    parser = argparse.ArgumentParser(prog="python -m vidgen.render.worker", description="Render one vidgen scene.")
    parser.add_argument("project", help="project directory or config file")
    parser.add_argument("scene_id")
    parser.add_argument("--quality", choices=("final", "preview"), default="final")
    parser.add_argument("--variant", metavar="NAME")
    parser.add_argument("--no-audio", action="store_true", help="do not add narration sounds")
    parser.add_argument("--progress", action="store_true", help="show Manim's progress bars")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Worker entry point; returns the exit code."""
    args = build_parser().parse_args(argv)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_LevelFormatter())
    logger = logging.getLogger("vidgen")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        render_scene(args.project, args.scene_id, args.quality == "preview", args.variant, not args.no_audio, args.progress)
    except VidgenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception:
        traceback.print_exc()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
