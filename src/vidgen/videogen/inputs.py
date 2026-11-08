"""The inputs vidgen cuts for generated shots (DESIGN.md §113.3, §113.8), into ``build/videogen/<shot>/``:

- ``audio.mp3``: the beat's own voice (its narration MP3, no music or effects), from the part's
  start for exactly its length, padded with silence (the pad after the line is in the beat's
  window): what a talking model lip-syncs to, timed like the film;
- ``guide.mp4``: the part of the beat from a draft render of its scene (the draft format: low
  resolution, the video's shape, few frames a second), without sound;
- ``guide.<pass>.mp4`` (``guide: depth | outline | mask`` on a ``3d`` scene): the same part of
  that guide pass of the draft render (the lossless ``.mkv`` beside the 3D clip, drawn when
  missing), as H.264 / yuv420p at the draft's size and frame rate;
- ``first_frame.png``: the first frame of the draft render of the part (the first one not dark,
  when the scene fades in from black); always the normal render, also with a guide pass.

Free and local (ffmpeg and vidgen's own renderer); the cuts are made again on every run, the
draft render is reused while current. ``inputs.json`` beside them records what each file was cut
from (:mod:`vidgen.videogen.freshness`), so the plan can tell when it no longer matches.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen.shots import INPUTS_DIR, Shot, guide_name

#: The cut voice: MP3 (small enough to send inline), mono, 44.1 kHz.
AUDIO_ARGS = ["-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k"]
#: H.264 quality of a converted guide pass (CRF; lower is closer to the lossless pass). Flat
#: greys, thin white lines and flat mask colours show compression more than a render does.
PASS_CRF = 12
#: RGB -> YUV as BT.709 limited range, tagged so players and models convert it back the same way.
PASS_COLOR_ARGS = [
    "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
]


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


def cut_pass(ffmpeg: str, source: Path, dest: Path, start: float, length: float) -> None:
    """``dest``: the lossless guide pass ``source`` from ``start`` for ``length`` seconds as the
    MP4 a provider takes (H.264, yuv420p, BT.709, :data:`PASS_CRF`), silent."""
    from vidgen.render.ffmpeg import run_ffmpeg

    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        ffmpeg,
        ["-ss", f"{start:.6f}", "-i", str(source), "-t", f"{length:.6f}", "-an", *PASS_COLOR_ARGS,
         "-c:v", "libx264", "-crf", str(PASS_CRF), "-pix_fmt", "yuv420p", str(dest)],
        f"converting the guide pass for {dest.parent.name}",
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


@dataclass(frozen=True)
class SceneRender:
    """A draft render of one scene: its ``video``, its beats' real ``starts`` (seconds on the
    scene's clock), the lossless clips of the guide ``passes`` drawn with it (pass -> file) and
    the render's recorded scene ``fingerprint`` (``None``: unknown, computed when it is cut)."""

    video: Path
    starts: dict[str, float]
    passes: dict[str, Path] = field(default_factory=dict)
    fingerprint: str | None = None


def _render_scene(project: Project, scene_id: str, passes: tuple[str, ...]) -> SceneRender:
    """A draft render of ``scene_id`` with guide ``passes`` (reused while current; a render
    without the passes is made again, reusing the 3D frames, DESIGN.md §114.14)."""
    from vidgen import extensions
    from vidgen.render.pipeline import current_render, render_scenes
    from vidgen.render.worker import scene_timings_path, scene_video_path
    from vidgen.three_d.passes import pass_clip

    draft = Project.load(project.config_file, variant=project.variant, draft=True)
    with extensions.project_session(draft):
        current = current_render(draft, False, scene_id, False, guide_passes=passes)
    if not current:
        render_scenes(draft, False, [scene_id], guide_passes=passes)
    timings = json.loads(scene_timings_path(draft, False, scene_id).read_text(encoding="utf-8"))
    folder = draft.render_dir(False) / "three_d"
    return SceneRender(
        scene_video_path(draft, False, scene_id), {b["id"]: float(b["start"]) for b in timings["beats"]},
        {mode: pass_clip(folder, scene_id, mode) for mode in passes}, timings.get("render", {}).get("fingerprint"),
    )


def _passes_by_scene(shots: Sequence[Shot]) -> dict[str, tuple[str, ...]]:
    """The guide passes each scene's draft render must draw for ``shots`` (in drawing order)."""
    from vidgen.three_d.spec import GUIDE_PASSES

    wanted: dict[str, set[str]] = {}
    for shot in shots:
        source = shot.spec.guide_source
        if source not in (None, "render"):
            wanted.setdefault(shot.scene_id, set()).add(source)
    return {scene: tuple(p for p in GUIDE_PASSES if p in modes) for scene, modes in wanted.items()}


def make_inputs(
    project: Project, shots: Sequence[Shot], *, guide: bool = False, out: Callable[[str], None] = print,
    render: Callable[[Project, str, tuple[str, ...]], SceneRender] | None = None,
) -> list[Path]:
    """Cut the inputs of ``shots``: the voice of each shot that takes it (needs the beat's MP3:
    `vidgen tts`), and with ``guide`` the renders of shots with a ``guide:`` or ``first_frame:
    render`` (a guide pass converted from the scene's lossless pass; ``render(project, scene,
    passes)`` replaces the draft render in tests). Each cut file is noted in the shot's
    ``inputs.json``. Returns the files written (the cut inputs, not ``inputs.json``)."""
    from vidgen.render.ffmpeg import find_ffmpeg
    from vidgen.videogen.freshness import InputSources, record_input, voice_source

    ffmpeg = find_ffmpeg()
    sources = InputSources(project)
    written: list[Path] = []
    renders: dict[str, SceneRender] = {}
    passes = _passes_by_scene(shots)
    for shot in shots:
        folder = project.root / INPUTS_DIR / shot.id
        if shot.spec.wants_audio:
            source = project.audio_dir / f"{shot.beat.id}.mp3"
            if not source.is_file():
                raise VidgenError(f"shot {shot.id}: the beat has no voice yet ({source.name}): run `vidgen tts` first")
            dest = folder / "audio.mp3"
            cut_audio(ffmpeg, source, dest, shot.offset, shot.length)
            record_input(dest, voice_source(source, shot))
            written.append(dest)
            out(f"{shot.id}: voice {dest.relative_to(project.root).as_posix()} ({shot.length:.2f} s)")
        kind = shot.spec.guide_source
        wants_frame = shot.spec.first_frame_source == "render"
        if kind is None and not wants_frame:
            continue
        if not guide:
            out(f"{shot.id}: the render of the beat is skipped (add --guide: renders the scene as a draft)")
            continue
        if shot.scene_id not in renders:
            renders[shot.scene_id] = (render or _render_scene)(project, shot.scene_id, passes.get(shot.scene_id, ()))
        scene = renders[shot.scene_id]
        if shot.beat.id not in scene.starts:
            raise VidgenError(f"shot {shot.id}: the render of scene {shot.scene_id} has no beat {shot.beat.id}")
        start = scene.starts[shot.beat.id] + shot.offset
        frame = folder / "first_frame.png"
        if kind in (None, "render"):
            clip = folder / "guide.mp4"
            cut_video(ffmpeg, scene.video, clip, start, shot.length)
            first_frame(ffmpeg, clip, frame)
            made_from = sources.render(shot, "render", scene.fingerprint)
            record_input(clip, made_from)
            record_input(frame, made_from)
            written += [clip, frame]
            out(f"{shot.id}: guide {clip.relative_to(project.root).as_posix()} and its first frame ({shot.length:.2f} s, silent)")
            continue
        lossless = scene.passes.get(kind)
        if lossless is None or not lossless.is_file():
            raise VidgenError(f"shot {shot.id}: the draft render of scene {shot.scene_id} drew no {kind} pass")
        clip = folder / guide_name(kind)
        cut_pass(ffmpeg, lossless, clip, start, shot.length)
        record_input(clip, sources.render(shot, kind, scene.fingerprint))
        written.append(clip)
        out(f"{shot.id}: guide {clip.relative_to(project.root).as_posix()} (the {kind} pass, {shot.length:.2f} s, silent)")
        if wants_frame:   # the first frame stays the normal render's, not the pass's
            with tempfile.TemporaryDirectory(prefix="vidgen-frame-") as scratch:
                part = Path(scratch) / "render.mp4"
                cut_video(ffmpeg, scene.video, part, start, shot.length)
                first_frame(ffmpeg, part, frame)
            record_input(frame, sources.render(shot, "render", scene.fingerprint))
            written.append(frame)
            out(f"{shot.id}: first frame {frame.relative_to(project.root).as_posix()} (from the normal render)")
    return written


__all__ = ["SceneRender", "cut_audio", "cut_pass", "cut_video", "first_frame", "make_inputs"]
