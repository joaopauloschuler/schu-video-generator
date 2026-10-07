"""``vidgen render``: render scenes in worker processes, pad, join, write SRT and timings.

Steps of :func:`render_project`:

1. activate the project's extensions (hooks, scene types) and check every scene's type/params;
2. find ffmpeg; warn about missing/stale narration audio (``vidgen tts`` fixes it);
3. decide which scenes to render (all, or ``--scene`` ones plus any without a usable render),
   dispatch ``pre_render``;
4. render each scene with ``python -m vidgen.render.worker`` (``jobs`` at a time), dispatching
   ``post_scene`` in this process after each successful scene;
5. pad every scene's audio to its exact video length, concatenate in config order, write the
   final MP4, ``timings.json``, the SRT (and with ``frames``, ``frames/index.json``), dispatch
   ``post_render``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vidgen import __version__, carry, chapter_export, hooks, mix, sfx, transitions
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render import ffmpeg as ff
from vidgen.fileio import remove_file
from vidgen.render.worker import (
    scene_activity_path,
    scene_audio_path,
    scene_frames_dir,
    scene_layout_path,
    scene_overlay_path,
    scene_timings_path,
    scene_video_path,
    write_json,
)
from vidgen.languages import language_rules
from vidgen.subtitles import write_srt
from vidgen.tts.elevenlabs import API_KEY_ENV

if TYPE_CHECKING:
    from vidgen.thumbnail import ThumbnailResult

log = logging.getLogger("vidgen.render")

#: Lines of a failed worker's output shown in the error.
TAIL_LINES = 60


@dataclass
class RenderResult:
    """What :func:`render_project` produced.

    ``timings`` is the content of ``timings_file``; ``render_seconds`` the wall time of each
    scene rendered in this run; ``warnings`` the ``(scene_id, message)`` warnings printed by
    the workers of this run, in config order. ``frames_index`` is ``build/.../frames/index.json``
    when stills were requested, else ``None``; ``chapters`` the YouTube chapter list
    ``<output>_chapters.txt`` when one was written (the video has chapters and
    ``chapters.youtube``), else ``None``; ``thumbnail`` the thumbnail written after the join
    (with a ``thumbnail:`` config and ``auto``, DESIGN.md §53), else ``None``.
    """

    output: Path
    srt: Path
    timings_file: Path
    duration: float
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    timings: dict[str, Any] = field(default_factory=dict)
    render_seconds: dict[str, float] = field(default_factory=dict)
    warnings: list[tuple[str, str]] = field(default_factory=list)
    frames_index: Path | None = None
    chapters: Path | None = None
    thumbnail: ThumbnailResult | None = None


@dataclass
class SceneRuns:
    """What :func:`render_scenes` did, in config order: scenes rendered, failures
    (``{scene, exit_code, output_tail}``), wall seconds per scene and ``(scene_id, message)``
    worker warnings."""

    rendered: list[str] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    seconds: dict[str, float] = field(default_factory=dict)
    warnings: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class _WorkerRun:
    scene_id: str
    returncode: int
    output: str
    seconds: float


def _check_scenes(project: Project) -> None:
    """Every scene's type is registered, its params validate, its beat count fits, its beat
    actions are valid and so are the overlays (fast, before any rendering)."""
    from vidgen import registry, runtime
    from vidgen.actions import plan_actions
    from vidgen.overlays import check_overlays

    for spec in project.config.scenes:
        cls = registry.get(spec.type).cls
        params = cls.parse_params(spec.params, scene_id=spec.id)
        problem = cls.check_beat_count(len(spec.beats))
        if problem is not None:
            raise VidgenError(f"scene '{spec.id}' (type {spec.type}): {problem}")
        plan_actions(spec.type, cls, spec, params, runtime.current_theme())
    check_overlays(project, runtime.current_theme())
    carried = carry.carry_problems(project.config)
    if carried:
        raise VidgenError("\n".join(["invalid carry", *(f"  {p.location}: {p.message}" for p in carried)]))
    problems = sfx.config_problems(project.config, project.root)
    if problems:
        raise VidgenError("\n".join(["invalid sound effects", *(f"  {loc}: {message}" for loc, message in problems)]))
    from vidgen.music import config_problems as music_problems

    problems = music_problems(project.config, project.root)
    if problems:
        raise VidgenError("\n".join(["invalid music", *(f"  {loc}: {message}" for loc, message in problems)]))
    from vidgen.thumbnail import thumbnail_problems

    thumb = thumbnail_problems(project, runtime.current_theme())
    if thumb:
        raise VidgenError("\n".join(["invalid thumbnail", *(f"  {p.location}: {p.message}" for p in thumb)]))


def warn_audio(project: Project) -> None:
    """Log a warning naming beats whose narration audio is missing or stale."""
    from vidgen import tts

    statuses = tts.audio_status(project)
    parts = []
    for state in ("stale", "missing"):
        ids = [s.beat_id for s in statuses if s.state == state]
        if ids:
            shown = ", ".join(ids[:8]) + (f" (+{len(ids) - 8} more)" if len(ids) > 8 else "")
            parts.append(f"{state} for {shown}")
    if parts:
        log.warning(
            "audio %s; those beats are timed from their text (or old audio) - run `vidgen tts` first",
            "; ".join(parts),
        )


def _usable_render(project: Project, preview: bool, scene_id: str, no_audio: bool, frames: int = 0) -> bool:
    """True if a previous render of the scene exists and matches the current format/audio mode
    (and, when ``frames`` stills per beat are requested, was made with them)."""
    video = scene_video_path(project, preview, scene_id)
    timings_file = scene_timings_path(project, preview, scene_id)
    if not (video.is_file() and timings_file.is_file()):
        return False
    try:
        meta = json.loads(timings_file.read_text(encoding="utf-8")).get("render", {})
    except (OSError, ValueError):
        return False
    fmt = project.render_format(preview)
    return (
        meta.get("width") == fmt.width
        and meta.get("height") == fmt.height
        and meta.get("fps") == fmt.fps
        and (no_audio or meta.get("audio") is True)
        and (not frames or (meta.get("frames") == frames and _has_stills(project, preview, scene_id)))
    )


def _has_stills(project: Project, preview: bool, scene_id: str) -> bool:
    return all(
        path.is_file()
        for path in (
            scene_frames_dir(project, preview, scene_id) / "index.json",
            scene_layout_path(project, preview, scene_id),
            scene_activity_path(project, preview, scene_id),
        )
    )


def _tail(text: str, lines: int = TAIL_LINES) -> str:
    """The last ``lines`` lines of worker output, progress-bar carriage returns resolved."""
    cleaned = [line.rsplit("\r", 1)[-1] for line in text.replace("\r\n", "\n").split("\n")]
    cleaned = [line for line in cleaned if line.strip()]
    return "\n".join(cleaned[-lines:])


def _run_worker(project: Project, preview: bool, scene_id: str, no_audio: bool, live: bool, frames: int = 0) -> _WorkerRun:
    """Run the worker for one scene; its output is captured (and echoed to stderr if ``live``)."""
    cmd = [
        sys.executable, "-m", "vidgen.render.worker", str(project.config_file), scene_id,
        "--quality", "preview" if preview else "final",
    ]
    if project.variant:
        cmd += ["--variant", project.variant]
    if no_audio:
        cmd.append("--no-audio")
    if live:
        cmd.append("--progress")
    if frames:
        cmd += ["--frames", str(frames)]
    if project.bare:
        cmd.append("--bare")
    # Scenes never need the ElevenLabs key: keep it out of the processes that run scene code.
    env = {k: v for k, v in os.environ.items() if k != API_KEY_ENV}
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    started = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=project.root)
    assert proc.stdout is not None
    chunks: list[bytes] = []
    while chunk := proc.stdout.read1(4096):
        chunks.append(chunk)
        if live:
            sys.stderr.buffer.write(chunk)
            sys.stderr.flush()
    returncode = proc.wait()
    output = b"".join(chunks).decode("utf-8", errors="replace")
    return _WorkerRun(scene_id, returncode, output, time.monotonic() - started)


def _failure_details(run: _WorkerRun) -> dict[str, Any]:
    """A failed worker as JSON data: ``{scene, exit_code, output_tail}``."""
    return {"scene": run.scene_id, "exit_code": run.returncode, "output_tail": _tail(run.output)}


def _failure_message(run: _WorkerRun, live: bool) -> str:
    head = f"scene '{run.scene_id}' failed (worker exit code {run.returncode})"
    if live:
        return f"{head}; see the output above"
    return f"{head}:\n{_tail(run.output) or '(no output)'}"


def _runs(
    task: Callable[[int, str], _WorkerRun], scene_ids: list[str], jobs: int, after: Mapping[str, str] | None = None
) -> Iterator[_WorkerRun]:
    """Run ``task(index, scene_id)`` for every scene and yield results as they complete.

    ``jobs == 1`` runs them one after the other in this thread. Otherwise a thread pool runs
    ``jobs`` workers at once; if the consumer stops early, queued scenes are cancelled and the
    running ones are waited for. ``after``: ``{scene: scene it must start after}`` (a carry,
    DESIGN.md §50); the earlier scene must come first in ``scene_ids``, so it has started (the
    pool starts tasks in order) before the later one waits for it.
    """
    if jobs == 1:
        for i, sid in enumerate(scene_ids, start=1):
            yield task(i, sid)
        return
    done = {sid: threading.Event() for sid in scene_ids}
    waits = {sid: done[before] for sid, before in (after or {}).items() if sid in done and before in done}

    def ordered(i: int, sid: str) -> _WorkerRun:
        try:
            if sid in waits:
                waits[sid].wait()
            return task(i, sid)
        finally:
            done[sid].set()

    pool = ThreadPoolExecutor(max_workers=jobs)
    try:
        futures = [pool.submit(ordered, i, sid) for i, sid in enumerate(scene_ids, start=1)]
        for future in as_completed(futures):
            yield future.result()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _carry_from_current(project: Project, preview: bool, scene_id: str, before: str) -> bool:
    """Whether ``scene_id``'s render carried objects from the render ``before`` has now (same
    fingerprint)."""
    from vidgen.render.fingerprint import scene_fingerprint

    try:
        meta = json.loads(scene_timings_path(project, preview, scene_id).read_text(encoding="utf-8")).get("render", {})
    except (OSError, ValueError):
        return False
    return meta.get("carry_from") == scene_fingerprint(project, before)


def with_carried(project: Project, preview: bool, scene_ids: list[str]) -> list[str]:
    """``scene_ids`` (in config order) plus what continuity needs rendered with them (DESIGN.md
    §50): the scene before a scene that carries objects, when its record of them is missing or
    was made from other inputs; and a scene carrying objects from a scene in the list, when its
    render did not start from that scene's current end."""
    deps = carry.carried_from(project.config)
    ids = set(scene_ids)
    changed = bool(deps)
    while changed:
        changed = False
        for after, before in deps.items():
            if after in ids and before not in ids and not carry.record_current(project, preview, before):
                ids.add(before)
                changed = True
            if before in ids and after not in ids and not _carry_from_current(project, preview, after, before):
                ids.add(after)
                changed = True
    return [s.id for s in project.config.scenes if s.id in ids]


def _render_scenes(
    project: Project, preview: bool, scene_ids: list[str], no_audio: bool, keep_going: bool, jobs: int, frames: int = 0
) -> SceneRuns:
    """Render ``scene_ids`` with up to ``jobs`` workers (and what their carries need,
    :func:`with_carried`; a scene that carries objects starts after the scene before it).

    Without ``keep_going`` the first failure raises (with ``jobs > 1``, scenes already running
    finish first). ``post_scene`` is dispatched here, in the parent, after each success.
    """
    live = jobs == 1 and sys.stderr.isatty()
    scene_ids = with_carried(project, preview, scene_ids)
    total = len(scene_ids)
    order = {sid: i for i, sid in enumerate(scene_ids)}
    runs = SceneRuns()
    print_lock = threading.Lock()

    def say(message: str, err: bool = False) -> None:
        with print_lock:
            print(message, file=sys.stderr if err else sys.stdout, flush=True)

    def task(index: int, scene_id: str) -> _WorkerRun:
        say(f"[{index}/{total}] {scene_id}: rendering")
        return _run_worker(project, preview, scene_id, no_audio, live, frames)

    for run in _runs(task, scene_ids, jobs, carry.carried_from(project.config)):
        if run.returncode != 0:
            runs.failed.append(_failure_details(run))
            message = _failure_message(run, live)
            if not keep_going:
                rendered = sorted(runs.rendered, key=order.__getitem__)
                raise VidgenError(message, details={"failed": runs.failed, "rendered": rendered})
            say(f"error: {message}", err=True)
            continue
        for line in run.output.splitlines():
            if line.startswith("warning: "):
                runs.warnings.append((run.scene_id, line.removeprefix("warning: ")))
                if not live:  # re-print the worker's warnings (live output has shown them already)
                    say(line, err=True)
        timings = json.loads(scene_timings_path(project, preview, run.scene_id).read_text(encoding="utf-8"))
        say(
            f"[{order[run.scene_id] + 1}/{total}] {run.scene_id}: done, "
            f"{timings['duration']:.2f} s of video in {run.seconds:.1f} s"
        )
        hooks.dispatch(
            "post_scene",
            project,
            scene_id=run.scene_id,
            video=scene_video_path(project, preview, run.scene_id),
            timings=timings,
            frames=scene_frames_dir(project, preview, run.scene_id) if frames else None,
            preview=preview,
            variant=project.variant,
        )
        runs.rendered.append(run.scene_id)
        runs.seconds[run.scene_id] = round(run.seconds, 3)
    runs.rendered.sort(key=order.__getitem__)
    runs.failed.sort(key=lambda f: order[f["scene"]])
    runs.warnings.sort(key=lambda w: order[w[0]])  # stable: a scene's warnings keep their order
    return runs


def render_scenes(project: Project, preview: bool, scene_ids: list[str], jobs: int = 1, frames: int = 0) -> SceneRuns:
    """Render only ``scene_ids`` (with narration sounds, ``frames`` stills per beat), without
    joining the video; used by ``vidgen storyboard``.

    Checks the scenes and (if any is rendered) warns about missing/stale audio like
    :func:`render_project`, then runs
    the workers (``jobs`` at a time; the first failure raises :class:`VidgenError`) and
    dispatches ``post_scene`` after each. ``pre_render``/``post_render`` are not dispatched (no
    video is made). The combined ``frames/index.json`` is removed when a scene is rendered, as
    it no longer matches the scenes' stills.
    """
    from vidgen import extensions

    if frames < 0:
        raise VidgenError("frames per beat must not be negative")
    with extensions.project_session(project):
        _check_scenes(project)
        if not scene_ids:
            return SceneRuns()
        warn_audio(project)
        remove_file(project.render_dir(preview) / "frames" / "index.json")
        return _render_scenes(project, preview, scene_ids, no_audio=False, keep_going=False, jobs=jobs, frames=frames)


def join_scenes(project: Project, preview: bool, no_audio: bool, ffmpeg: str) -> tuple[Path, dict[str, Any]]:
    """Join every scene's render (config order) into the final video; returns it and the
    combined timings mapping.

    Each scene's audio (Manim's WAV, or silence for silent scenes and ``no_audio``) is padded to
    the exact length of its video. Lengths are measured from the rendered videos; the sample
    count of each scene is taken from the cumulative time, so rounding never accumulates.

    The scenes' sound effects (their timings' ``sfx``, scene times) are placed at video times on
    one track for the whole video, ``padded/sfx.wav`` (none without effects or with
    ``no_audio``), which the final mux adds to the narration track (DESIGN.md §47). Unless
    ``no_audio``, :func:`vidgen.mix.mix_audio` then adds the music, ducks and normalises it into
    ``padded/mix.wav`` (with music or ``audio.normalize``; else it only measures the loudness)
    and the combined timings gain ``mix``, its report (§48).

    Crossfades (§49) start a scene before the one before it ends: every later time (beats, SRT,
    effects, music, chapters) follows the overlapped starts, the scenes' sound is summed into
    ``padded/voice.wav`` (the earlier scene's silent tail fading out) and the pictures are
    blended by :func:`vidgen.render.ffmpeg.join` (the video is then encoded once instead of
    stream-copied). Scenes with a transition get ``transition: {type, duration, overlap}`` in the
    combined timings.

    The published chapters (§52: starting at the joined scenes' starts, from 0:00) go into the
    combined timings' ``chapters`` and, with ``chapters.metadata``, into the MP4 with its tags
    (``padded/metadata.txt``, FFMETADATA).
    """
    render_dir = project.render_dir(preview)
    padded_dir = render_dir / "padded"
    fmt = project.render_format(preview)
    videos: list[Path] = []
    audios: list[Path] = []
    scenes: list[dict[str, Any]] = []
    shifted: list[str] = []
    events: list[sfx.SfxEvent] = []
    renders = _scene_renders(project, preview)
    overlaps = _overlaps(project, fmt.fps, renders)
    sample_overlaps: list[int] = []
    offset = 0.0
    end_sample = 0
    portrait = fmt.height > fmt.width
    kinds: list[str] = []  # xfade transition into each scene
    clips: list[tuple[Path, int]] = []  # overlays of frames a push / wipe moves, at output frames
    start_frame = 0
    for i, (spec, (video, timings, duration)) in enumerate(zip(project.config.scenes, renders)):
        offset -= overlaps[i] / fmt.fps
        sample_overlaps.append(end_sample - round(offset * ff.AUDIO_RATE) if i else 0)
        drawn = timings.get("render", {}).get("overlays") or {}
        if drawn.get("timed") and drawn.get("start") is not None and abs(drawn["start"] - offset) > 1.5 / fmt.fps:
            shifted.append(f"'{spec.id}' starts at {offset:.2f} s, planned {drawn['start']:.2f} s")
        samples = round((offset + duration) * ff.AUDIO_RATE) - round(offset * ff.AUDIO_RATE)
        wav = scene_audio_path(project, preview, spec.id)
        audio = padded_dir / f"{spec.id}.wav"
        ff.pad_audio(ffmpeg, wav if wav.is_file() and not no_audio else None, audio, samples)
        scene_sfx = [sfx.SfxEvent.from_json(e).shifted(offset) for e in timings.get("sfx", [])]
        events += scene_sfx
        entry: dict[str, Any] = {
            "id": spec.id,
            "type": spec.type,
            "start": round(offset, 6),
            "duration": round(duration, 6),
            "beats": [
                {**beat, "start": round(offset + beat["start"], 6), "end": round(offset + beat["end"], 6)}
                for beat in timings["beats"]
            ],
        }
        if scene_sfx:
            entry["sfx"] = [e.to_json() for e in scene_sfx]
        transition = transitions.effective(project.config, i)
        if transition.type != "cut":
            entry["transition"] = {"type": transition.type, "duration": transition.seconds, "overlap": round(overlaps[i] / fmt.fps, 6)}
            way = transitions.direction(transition, portrait)
            if way is not None:
                entry["transition"]["direction"] = way
        kinds.append(transitions.xfade_name(transition, portrait))
        clip = scene_overlay_path(project, preview, spec.id)
        if transitions.moves_pictures(transition) and clip.is_file():  # its moving frames' overlays (§50)
            clips.append((clip, start_frame))
        start_frame += round(duration * fmt.fps) - (overlaps[i + 1] if i + 1 < len(overlaps) else 0)
        scenes.append(entry)
        videos.append(video)
        audios.append(audio)
        offset += duration
        end_sample = round(offset * ff.AUDIO_RATE)
    if shifted:
        log.warning(
            "overlays timed in the video are off where a scene does not start where it was planned "
            "(an earlier scene ran longer or shorter than its narration; DESIGN.md §41): %s", "; ".join(shifted)
        )
    voice = padded_dir / "voice.wav"
    remove_file(voice)
    if any(overlaps):  # crossfades: the scenes' sound overlaps too, summed into one track
        transitions.write_voice_track(audios, sample_overlaps, voice, ff.AUDIO_RATE)
        audios = [voice]
    track = padded_dir / "sfx.wav"
    remove_file(track)
    if events and not no_audio:
        sfx.write_track(track, events, round(offset * ff.AUDIO_RATE), sfx.SoundLibrary(project.root), project.config.sfx.gain)
    combined: dict[str, Any] = {
        "title": project.config.title,
        "variant": project.variant,
        "language": project.config.language,
        "preview": preview,
        "format": {"width": fmt.width, "height": fmt.height, "fps": fmt.fps},
        "audio": not no_audio,
        "duration": round(offset, 6),
        "vidgen": __version__,
        "scenes": scenes,
    }
    chapters = chapter_export.joined_chapters(project.config, scenes, offset)
    combined["chapters"] = [chapter_export.chapter_json(c) for c in chapters]
    metadata = padded_dir / "metadata.txt"
    padded_dir.mkdir(parents=True, exist_ok=True)
    metadata.write_text(
        chapter_export.ffmetadata(chapter_export.video_tags(project.config), chapters if project.config.chapters.metadata else ()),
        encoding="utf-8",
    )
    mixed = padded_dir / "mix.wav"
    remove_file(mixed)
    if not no_audio:
        report = mix.mix_audio(project, combined, audios, track if track.is_file() else None, mixed)
        combined["mix"] = report.to_json()
    output = project.output_path(preview)
    ff.join(
        ffmpeg, videos, audios, output, padded_dir,
        sfx=track if track.is_file() else None,
        mix=mixed if mixed.is_file() else None,
        crossfades=overlaps[1:] if any(overlaps) else None,
        frames=[round(d * fmt.fps) for _, _, d in renders],
        fps=fmt.fps,
        kinds=kinds[1:],
        overlays=clips or None,
        metadata=metadata,
        language=language_rules(project.config.language).iso639_2 if project.config.language else None,
    )
    return output, combined


def _scene_renders(project: Project, preview: bool) -> list[tuple[Path, dict[str, Any], float]]:
    """Every scene's rendered video, timings and measured length (config order)."""
    out = []
    render_dir = project.render_dir(preview)
    for spec in project.config.scenes:
        video = scene_video_path(project, preview, spec.id)
        timings_file = scene_timings_path(project, preview, spec.id)
        if not (video.is_file() and timings_file.is_file()):
            raise VidgenError(f"scene '{spec.id}' has no render in {render_dir}; render it first")
        out.append((video, json.loads(timings_file.read_text(encoding="utf-8")), ff.probe(video).duration))
    return out


def _overlaps(project: Project, fps: int, renders: list[tuple[Path, dict[str, Any], float]]) -> list[int]:
    """Frames each scene overlaps the one before (crossfades, pushes, wipes; DESIGN.md §49), from
    the renders; warns where one had to be shortened (a reused render ends with less silence
    than the plan gave it)."""
    config = project.config
    if not transitions.has_transitions(config):
        return [0] * len(renders)
    frames = [round(duration * fps) for _, _, duration in renders]
    speech = [timings["beats"][-1]["end"] if timings["beats"] else None for _, timings, _ in renders]
    overlaps = transitions.join_overlaps(config, fps, frames, speech)
    for i, spec in enumerate(config.scenes):
        t = transitions.effective(config, i)
        wanted = min(transitions.requested_frames(t, fps), frames[i]) if t.overlaps else 0
        if overlaps[i] < wanted:
            log.warning(
                "the %s into '%s' is %.2f s instead of %.2f s: '%s' ends with only that much silence "
                "(render it again so it is held for the transition; DESIGN.md §49)",
                t.type, spec.id, overlaps[i] / fps, wanted / fps, config.scenes[i - 1].id,
            )
    return overlaps


def write_chapter_list(project: Project, preview: bool, timings: dict[str, Any]) -> Path | None:
    """Write the YouTube chapter list ``<output>_chapters.txt`` from the combined timings'
    ``chapters`` (DESIGN.md §52) and log why YouTube would ignore it; returns its path, or
    ``None`` (and removes an old list) when the video has no chapters or ``chapters.youtube`` is
    false."""
    path = project.chapters_path(preview)
    chapters = [chapter_export.chapter_from_json(c) for c in timings.get("chapters", [])]
    if not chapters or not project.config.chapters.youtube:
        remove_file(path)
        return None
    for problem in chapter_export.write_youtube_list(path, chapters):
        log.warning("%s", problem)
    return path


def write_frames_index(project: Project, preview: bool, timings: dict[str, Any], frames: int) -> Path:
    """Combine the scenes' ``frames/<id>/index.json`` into ``frames/index.json`` (config order).

    Each still gets ``time`` in the video (scene start + its time in the scene), ``scene_time``
    and ``path`` relative to the ``frames`` folder; each scene its ``layout`` and ``activity``
    files (relative to the ``frames`` folder). A scene without stills of this ``frames``
    count (a ``pre_render`` hook kept it from rendering) gets none, with a warning.
    """
    root = project.render_dir(preview) / "frames"
    scenes = []
    for scene in timings["scenes"]:
        index_file = scene_frames_dir(project, preview, scene["id"]) / "index.json"
        index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.is_file() else {}
        if index.get("per_beat") != frames:  # only if a pre_render hook kept a scene from rendering
            log.warning("scene '%s' has no stills at %d per beat; render it again to get them", scene["id"], frames)
            index = {"frames": []}
        stills = [
            {
                **still,
                "time": round(scene["start"] + still["time"], 6),
                "scene_time": still["time"],
                "path": f"{scene['id']}/{still['path']}",
            }
            for still in index["frames"]
        ]
        layout = scene_layout_path(project, preview, scene["id"])
        activity = scene_activity_path(project, preview, scene["id"])
        scenes.append(
            {
                "id": scene["id"],
                "start": scene["start"],
                "duration": scene["duration"],
                "layout": f"../layout/{layout.name}" if stills and layout.is_file() else None,
                "activity": f"../activity/{activity.name}" if stills and activity.is_file() else None,
                "frames": stills,
            }
        )
    combined = {
        "title": timings["title"],
        "variant": timings["variant"],
        "preview": timings["preview"],
        "format": timings["format"],
        "per_beat": frames,
        "vidgen": __version__,
        "scenes": scenes,
    }
    target = root / "index.json"
    write_json(target, combined)
    return target


def render_project(
    project: Project,
    preview: bool = False,
    scenes: list[str] | None = None,
    no_audio: bool = False,
    keep_going: bool = False,
    jobs: int = 1,
    frames: int = 0,
) -> RenderResult:
    """Render ``project`` (already loaded with its variant) and write the final MP4 + SRT.

    ``scenes``: render only these ids and reuse existing renders of the others (scenes without a
    usable render, e.g. never rendered or rendered at another format, are rendered too).
    ``keep_going``: render the remaining scenes after a failure; the video is then not joined and
    a :class:`VidgenError` listing the failed scenes is raised at the end.
    ``frames``: also save that many PNG stills per beat of every scene (1: the end of each beat)
    under ``build/.../frames/``; reused scenes without such stills are rendered again. 0: none.
    With a ``thumbnail:`` config (and ``auto``), the thumbnail is written last
    (:func:`vidgen.thumbnail.make_thumbnail`; its warnings are logged).
    """
    from vidgen import extensions

    if frames < 0:
        raise VidgenError("frames per beat must not be negative")
    with extensions.project_session(project):
        _check_scenes(project)
        ffmpeg = ff.find_ffmpeg()
        known = [s.id for s in project.config.scenes]
        selected = list(dict.fromkeys(scenes or []))
        unknown = [sid for sid in selected if sid not in known]
        if unknown:
            raise VidgenError(f"unknown scene(s): {', '.join(unknown)}; scenes: {', '.join(known)}")
        warn_audio(project)
        to_render = [
            sid for sid in known
            if not selected or sid in selected or not _usable_render(project, preview, sid, no_audio, frames)
        ]
        ctx = hooks.dispatch(
            "pre_render",
            project,
            scenes=to_render,
            preview=preview,
            variant=project.variant,
            no_audio=no_audio,
            render_dir=project.render_dir(preview),
        )
        to_render = [sid for sid in known if sid in ctx.data["scenes"]]
        frames_index = project.render_dir(preview) / "frames" / "index.json"
        remove_file(frames_index)  # rewritten below when stills are requested; never stale
        runs = _render_scenes(project, preview, to_render, no_audio, keep_going, jobs, frames)
        if runs.failed:
            raise VidgenError(
                f"{len(runs.failed)} scene(s) failed: {', '.join(f['scene'] for f in runs.failed)}; "
                f"the video was not joined ({len(runs.rendered)} scene(s) rendered)",
                details={"failed": runs.failed, "rendered": runs.rendered},
            )
        print("joining scenes", flush=True)
        output, timings = join_scenes(project, preview, no_audio, ffmpeg)
        timings_file = project.render_dir(preview) / "timings.json"
        write_json(timings_file, timings)
        srt = project.srt_path(preview)
        write_srt(srt, timings, project.audio_dir, project.pronunciation, project.speaker_tags(), project.config.language)
        chapters_file = write_chapter_list(project, preview, timings)
        index = write_frames_index(project, preview, timings, frames) if frames else None
        hooks.dispatch(
            "post_render",
            project,
            output=output,
            srt=srt,
            timings=timings,
            timings_file=timings_file,
            frames_index=index,
            chapters=chapters_file,
            preview=preview,
            variant=project.variant,
        )
        result = RenderResult(
            output=output,
            srt=srt,
            timings_file=timings_file,
            duration=timings["duration"],
            rendered=runs.rendered,
            reused=[sid for sid in known if sid not in runs.rendered],
            timings=timings,
            render_seconds=runs.seconds,
            warnings=runs.warnings,
            frames_index=index,
            chapters=chapters_file,
        )
    thumb = project.config.thumbnail
    if thumb is not None and thumb.auto:  # after the session: a frame thumbnail may render a scene
        from vidgen.thumbnail import make_thumbnail

        result.thumbnail = make_thumbnail(project, preview, jobs=jobs)
        for check in result.thumbnail.checks:
            if check.severity == "warning":
                log.warning("thumbnail: %s", check.message)
    return result
