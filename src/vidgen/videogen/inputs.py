"""The inputs vidgen cuts for generated shots (DESIGN.md §113.3), into ``build/videogen/<shot>/``:

- ``audio.mp3``: the beat's own voice (its narration MP3, no music or effects), from the part's
  start for exactly its length, padded with silence (the pad after the line is in the beat's
  window): what a talking model lip-syncs to, timed like the film;
- ``guide.mp4``: the part of the beat from a draft render of its scene (the draft format: low
  resolution, the video's shape, few frames a second), without sound;
- ``first_frame.png``: the first frame of that render (the first one not dark, when the scene
  fades in from black).

Free and local (ffmpeg and vidgen's own renderer); rebuilt on every run.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen.shots import INPUTS_DIR, Shot

#: The cut voice: MP3 (small enough to send inline), mono, 44.1 kHz.
AUDIO_ARGS = ["-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k"]


def cut_audio(ffmpeg: str, source: Path, dest: Path, offset: float, length: float) -> None:
    """``dest``: ``source`` from ``offset`` for exactly ``length`` seconds, padded with silence."""
    from vidgen.render.ffmpeg import run_ffmpeg

    end = offset + length
    graph = f"apad=whole_dur={end:.6f},atrim=start={offset:.6f}:end={end:.6f},asetpts=PTS-STARTPTS"
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(ffmpeg, ["-i", str(source), "-vn", "-af", graph, *AUDIO_ARGS, str(dest)], f"cutting the voice for {dest.parent.name}")


def cut_video(ffmpeg: str, source: Path, dest: Path, start: float, length: float) -> None:
    """``dest``: ``source`` from ``start`` for ``length`` seconds, silent (H.264)."""
    from vidgen.render.ffmpeg import run_ffmpeg

    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        ffmpeg, ["-ss", f"{start:.6f}", "-i", str(source), "-t", f"{length:.6f}", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest)],
        f"cutting the guide render for {dest.parent.name}",
    )


#: A frame below this share of the brightest frame's mean grey (in the first
#: :data:`FADE_SEARCH` seconds) is taken for part of a fade in.
FADED = 0.7
#: How far into the clip a fade in is looked for (seconds).
FADE_SEARCH = 1.5


def first_frame(ffmpeg: str, source: Path, dest: Path) -> float:
    """``dest``: the first frame of the video ``source`` (PNG) past a fade in from black (the
    first at least :data:`FADED` as bright as the brightest of its first :data:`FADE_SEARCH`
    seconds; a clip without a fade: its first frame). Returns its time in seconds."""
    from vidgen.render.ffmpeg import decode_gray_frames, run_ffmpeg

    fps = 10.0
    means = [float(frame.mean()) for frame in decode_gray_frames(source, 32, fps, FADE_SEARCH)]
    lit = next((k for k, mean in enumerate(means) if mean >= FADED * max(means)), 0) if means else 0
    at = lit / fps
    run_ffmpeg(ffmpeg, ["-ss", f"{at:.3f}", "-i", str(source), "-frames:v", "1", str(dest)], f"taking the first frame for {dest.parent.name}")
    return at


def _render_scene(project: Project, scene_id: str) -> tuple[Path, dict[str, float]]:
    """A draft render of ``scene_id`` (reused while current) and its beats' real starts."""
    from vidgen.render.pipeline import render_scenes
    from vidgen.render.worker import scene_timings_path, scene_video_path

    draft = Project.load(project.config_file, variant=project.variant, draft=True)
    render_scenes(draft, False, [scene_id])
    timings = json.loads(scene_timings_path(draft, False, scene_id).read_text(encoding="utf-8"))
    return scene_video_path(draft, False, scene_id), {b["id"]: float(b["start"]) for b in timings["beats"]}


def make_inputs(
    project: Project, shots: Sequence[Shot], *, guide: bool = False, out: Callable[[str], None] = print,
    render: Callable[[Project, str], tuple[Path, dict[str, float]]] | None = None,
) -> list[Path]:
    """Cut the inputs of ``shots``: the voice of each shot that takes it (needs the beat's MP3:
    `vidgen tts`), and with ``guide`` the renders of shots with ``guide: true`` or
    ``first_frame: render`` (``render`` replaces the draft render in tests). Returns the files
    written."""
    from vidgen.render.ffmpeg import find_ffmpeg

    ffmpeg = find_ffmpeg()
    written: list[Path] = []
    renders: dict[str, tuple[Path, dict[str, float]]] = {}
    for shot in shots:
        folder = project.root / INPUTS_DIR / shot.id
        if shot.spec.wants_audio:
            source = project.audio_dir / f"{shot.beat.id}.mp3"
            if not source.is_file():
                raise VidgenError(f"shot {shot.id}: the beat has no voice yet ({source.name}): run `vidgen tts` first")
            dest = folder / "audio.mp3"
            cut_audio(ffmpeg, source, dest, shot.offset, shot.length)
            written.append(dest)
            out(f"{shot.id}: voice {dest.relative_to(project.root).as_posix()} ({shot.length:.2f} s)")
        wants_render = shot.spec.guide or shot.spec.first_frame_source == "render"
        if not wants_render:
            continue
        if not guide:
            out(f"{shot.id}: the render of the beat is skipped (add --guide: renders the scene as a draft)")
            continue
        if shot.scene_id not in renders:
            renders[shot.scene_id] = (render or _render_scene)(project, shot.scene_id)
        video, starts = renders[shot.scene_id]
        if shot.beat.id not in starts:
            raise VidgenError(f"shot {shot.id}: the render of scene {shot.scene_id} has no beat {shot.beat.id}")
        clip = folder / "guide.mp4"
        cut_video(ffmpeg, video, clip, starts[shot.beat.id] + shot.offset, shot.length)
        frame = folder / "first_frame.png"
        first_frame(ffmpeg, clip, frame)
        written += [clip, frame]
        out(f"{shot.id}: guide {clip.relative_to(project.root).as_posix()} and its first frame ({shot.length:.2f} s, silent)")
    return written


__all__ = ["cut_audio", "cut_video", "first_frame", "make_inputs"]
