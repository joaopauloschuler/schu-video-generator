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
  when the scene fades in from black); always the normal render, also with a guide pass;
- ``guide[.<pass>].opening.mp4`` (``first_frame_in: guide``): that guide with the shot's starting
  picture as its first frame, dissolving into it over ``videogen.first_frame_dissolve`` seconds,
  same length, size and frame rate (DESIGN.md §113.13). This one is sent, not the plain guide;
- ``last_of.<source>.<take>.png`` (``first_frame: last_of:``): the last decoded frame of the take
  the source shot shows (no ``--guide`` needed);
- ``overlay.png``: the shot's starting picture blended over the first frame of its plain guide,
  to check the fit of the 3D figures before paying. Never sent;
- ``overlay.last.png``: the same picture over the plain guide's last frame: an object that appears
  only later in the shot is where the guide puts it, and everything that moved or appeared between
  the guide's first and last frames is drawn at full strength with a magenta outline. Never sent;
- ``layout.png`` (``vidgen generate frames``, not this module's run): the first frame of the beat's
  draft render, the picture a painted starting picture keeps the composition of (:func:`layout_picture`).

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
from typing import Any

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


#: H.264 quality of a guide with its starting picture (CRF; the picture must survive the cut).
OPENING_CRF = 16


def make_opening_guide(ffmpeg: str, picture: Path, guide: Path, dest: Path, dissolve_seconds: float) -> None:
    """``dest``: the guide video ``guide`` with ``picture`` (cropped to fill) as its first frame,
    dissolving into the guide over ``dissolve_seconds`` (at most the guide's length); same length,
    size and frame rate as ``guide``, never longer, silent."""
    from vidgen.render.ffmpeg import probe, run_ffmpeg

    info = probe(guide)
    fade = min(dissolve_seconds, info.duration)
    size = f"{info.width}:{info.height}"
    graph = (
        f"[0:v]scale={size}:force_original_aspect_ratio=increase,crop={size},setsar=1,format=yuv420p,fps={info.fps},settb=AVTB[p];"
        f"[1:v]setsar=1,format=yuv420p,fps={info.fps},settb=AVTB[g];"
        f"[p][g]xfade=transition=fade:duration={fade:.6f}:offset=0,format=yuv420p[v]"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        ffmpeg,
        ["-loop", "1", "-framerate", str(info.fps), "-t", f"{fade:.6f}", "-i", str(picture), "-i", str(guide), "-filter_complex", graph, "-map", "[v]",
         "-t", f"{info.duration:.6f}", "-an", "-c:v", "libx264", "-crf", str(OPENING_CRF), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)],
        f"putting the starting picture into the guide for {dest.parent.name}",
    )


#: The files that show the starting picture over the plain guide's first and last frame, in the shot's folder.
OVERLAY_NAME = "overlay.png"
OVERLAY_LAST_NAME = "overlay.last.png"
#: Seconds before a take's end decoded to find its last frame (a shorter seek can write no file).
LAST_FRAME_SEEK = 0.5


def last_frame(ffmpeg: str, source: Path, dest: Path) -> None:
    """``dest``: the last decoded frame of the video ``source`` (PNG)."""
    from vidgen.render.ffmpeg import run_ffmpeg

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    run_ffmpeg(ffmpeg, ["-sseof", f"-{LAST_FRAME_SEEK:g}", "-i", str(source), "-update", "1", "-vsync", "0", str(dest)], f"taking the last frame of {source.name}")
    if not dest.is_file():
        raise VidgenError(f"could not take the last frame of {source}: ffmpeg wrote no picture")


#: The longer side of the overlays, in pixels (the guide is only a draft: small objects need room).
OVERLAY_LONG_SIDE = 1600
#: Grey levels a guide pixel must change by between the first and last frame to count as moved.
CHANGE_LEVELS = 6
#: Above this share of the picture changed, the whole frame moved (a camera move or a fade): nothing is outlined.
MAX_CHANGED_SHARE = 0.6
#: The outline of what moved or appeared on ``overlay.last.png``, and its reach around it in guide pixels (odd).
OUTLINE_COLOR = (255, 0, 255)
OUTLINE_REACH = 7


def changed_mask(first: Any, last: Any) -> Any:
    """The ``L`` mask (255: changed) of what moved or appeared between the frames ``first`` and
    ``last`` of a guide (same size), specks left by compression removed; ``None`` when nothing
    changed or when the whole frame did (:data:`MAX_CHANGED_SHARE`)."""
    import numpy as np
    from PIL import Image, ImageFilter

    a, b = (np.asarray(frame.convert("L"), dtype=np.int16) for frame in (first, last))
    changed = (np.abs(a - b) >= CHANGE_LEVELS).astype(np.uint8) * 255
    mask = Image.fromarray(changed).filter(ImageFilter.MedianFilter(3))
    share = float(np.asarray(mask).mean()) / 255
    return mask if 0 < share <= MAX_CHANGED_SHARE else None


def make_overlay(ffmpeg: str, picture: Path, guide: Path, dest: Path, *, past_fade: bool, at_end: bool = False) -> None:
    """``dest``: ``picture`` (cropped to fill) blended half and half over the first frame of the
    plain ``guide`` (``past_fade``: the first frame past a fade in from black), or over its last
    frame (``at_end``, with what moved or appeared since the first frame at full strength and
    ringed: :func:`changed_mask`), scaled so its longer side is :data:`OVERLAY_LONG_SIDE`."""
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps

    from vidgen.render.ffmpeg import run_ffmpeg

    with tempfile.TemporaryDirectory(prefix="vidgen-overlay-") as scratch:
        start_path = Path(scratch) / "first.png"
        run_ffmpeg(ffmpeg, ["-i", str(guide), "-frames:v", "1", str(start_path)], f"taking the guide's first frame for {dest.parent.name}")
        with Image.open(start_path) as opened:
            start = opened.convert("RGB")
        if at_end:
            frame = Path(scratch) / "last.png"
            last_frame(ffmpeg, guide, frame)
        elif past_fade:
            frame = Path(scratch) / "faded.png"
            first_frame(ffmpeg, guide, frame)
        else:
            frame = start_path
        with Image.open(frame) as opened:
            base = opened.convert("RGB")
    size = _overlay_size(base.size)
    enlarged = base.resize(size, Image.BICUBIC)
    with Image.open(picture) as opened:
        top = ImageOps.fit(opened.convert("RGB"), size, Image.LANCZOS)
    blended = Image.blend(enlarged, top, 0.5)
    mask = changed_mask(start, base) if at_end else None
    if mask is not None:
        blended.paste(enlarged, mask=mask.resize(size, Image.NEAREST))   # the late object in the guide, full strength
        grown = mask.filter(ImageFilter.MaxFilter(OUTLINE_REACH))        # the ring is drawn at the guide's scale
        ring = Image.fromarray(np.where(np.asarray(mask) > 0, 0, np.asarray(grown)).astype(np.uint8)).resize(size, Image.NEAREST)
        blended.paste(OUTLINE_COLOR, mask=ring)
    dest.parent.mkdir(parents=True, exist_ok=True)
    blended.save(dest)


def _overlay_size(guide_size: tuple[int, int]) -> tuple[int, int]:
    """The guide's shape with its longer side :data:`OVERLAY_LONG_SIDE` (never below the guide's size)."""
    width, height = guide_size
    scale = max(1.0, OVERLAY_LONG_SIDE / max(width, height))
    return round(width * scale), round(height * scale)


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


def _write_opening_guide(ffmpeg: str, project: Project, shot: Shot, plain: Path, source: dict[str, Any], written: list[Path], out: Callable[[str], None]) -> None:
    """Make and record the guide ``plain`` with ``shot``'s starting picture (``source``: what
    ``plain`` was cut from). Nothing for a shot with no starting picture to put in."""
    from vidgen.videogen.freshness import opening_source, record_input

    picture, kind = shot.opening_picture, shot.spec.guide_source
    if picture is None or kind is None:   # a shot with no guide has a problem of its own in the plan
        return
    if not picture.is_file():
        raise VidgenError(f"shot {shot.id}: the starting picture {picture.name} does not exist yet (first_frame_in: guide needs it: make the sheet, or check first_frame:)")
    dest = plain.with_name(guide_name(kind, opening=True))
    make_opening_guide(ffmpeg, picture, plain, dest, shot.opening_dissolve_seconds)
    record_input(dest, {**source, **opening_source(shot)})
    written.append(dest)
    out(f"{shot.id}: guide with its starting picture {dest.relative_to(project.root).as_posix()} ({shot.opening_dissolve_seconds:g} s dissolve)")


def _write_last_of_picture(ffmpeg: str, project: Project, shot: Shot, written: list[Path], out: Callable[[str], None]) -> None:
    """Cut and record the picture of a ``first_frame: last_of:`` shot, or say what it waits for."""
    from vidgen.videogen.freshness import last_of_source, record_input

    if shot.last_of_picture is None or shot.last_of_take is None:
        out(f"{shot.id}: no starting picture yet (first_frame: last_of:{shot.spec.last_of_shot}; `vidgen generate plan` says why)")
        return
    last_frame(ffmpeg, shot.last_of_take.path, shot.last_of_picture)
    record_input(shot.last_of_picture, last_of_source(shot))
    written.append(shot.last_of_picture)
    out(f"{shot.id}: starting picture {shot.last_of_picture.relative_to(project.root).as_posix()} (last frame of shot {shot.last_of}, take {shot.last_of_take.number})")


def _write_overlay(ffmpeg: str, project: Project, shot: Shot, plain: Path, written: list[Path], out: Callable[[str], None]) -> None:
    """Make the picture that shows ``shot``'s starting picture over its plain guide ``plain``
    (nothing for a shot with no starting picture; a note when the picture does not exist yet)."""
    picture = shot.starting_picture
    if picture is None:
        return
    if not picture.is_file():
        out(f"{shot.id}: no overlay yet: the starting picture {picture.name} does not exist")
        return
    dest = plain.with_name(OVERLAY_NAME)
    make_overlay(ffmpeg, picture, plain, dest, past_fade=shot.spec.guide_source == "render")
    written.append(dest)
    out(f"{shot.id}: starting picture over the plain guide's first frame {dest.relative_to(project.root).as_posix()} (check that the 3D figures fit before paying)")
    last = plain.with_name(OVERLAY_LAST_NAME)
    make_overlay(ffmpeg, picture, plain, last, past_fade=False, at_end=True)
    written.append(last)
    out(f"{shot.id}: starting picture over the plain guide's last frame {last.relative_to(project.root).as_posix()} (what moved or appeared by the end is outlined in magenta; check where it ends up)")


def layout_picture(project: Project, shot: Shot, *, render: Callable[[Project, str, tuple[str, ...]], SceneRender] | None = None) -> Path:
    """Write and return ``build/videogen/<shot>/layout.png``: the first frame of the part of the
    draft render of ``shot``'s scene (made once, reused while current; ``render`` replaces it in tests)."""
    from vidgen.render.ffmpeg import find_ffmpeg

    ffmpeg = find_ffmpeg()
    scene = (render or _render_scene)(project, shot.scene_id, ())
    if shot.beat.id not in scene.starts:
        raise VidgenError(f"shot {shot.id}: the render of scene {shot.scene_id} has no beat {shot.beat.id}")
    dest = project.root / INPUTS_DIR / shot.id / "layout.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vidgen-frame-") as scratch:
        part = Path(scratch) / "render.mp4"
        cut_video(ffmpeg, scene.video, part, scene.starts[shot.beat.id] + shot.offset, shot.length)
        first_frame(ffmpeg, part, dest)
    return dest


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
        if shot.spec.last_of_shot is not None:
            _write_last_of_picture(ffmpeg, project, shot, written, out)
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
            _write_opening_guide(ffmpeg, project, shot, clip, made_from, written, out)
            _write_overlay(ffmpeg, project, shot, clip, written, out)
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
        _write_opening_guide(ffmpeg, project, shot, clip, sources.render(shot, kind, scene.fingerprint), written, out)
        _write_overlay(ffmpeg, project, shot, clip, written, out)
    return written


__all__ = ["CHANGE_LEVELS", "OVERLAY_LAST_NAME", "OVERLAY_LONG_SIDE", "OVERLAY_NAME", "SceneRender", "changed_mask", "layout_picture", "cut_audio", "cut_pass", "cut_video", "first_frame", "last_frame", "make_inputs", "make_opening_guide", "make_overlay"]
