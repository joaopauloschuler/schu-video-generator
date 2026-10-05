"""``vidgen render``: render scenes in worker processes, pad, join, write SRT and timings.

Steps of :func:`render_project`:

1. activate the project's extensions (hooks, scene types) and check every scene's type/params;
2. find ffmpeg; warn about missing/stale narration audio (``vidgen tts`` fixes it);
3. decide which scenes to render (all, or ``--scene`` ones plus any without a usable render),
   dispatch ``pre_render``;
4. render each scene with ``python -m vidgen.render.worker`` (``jobs`` at a time), dispatching
   ``post_scene`` in this process after each successful scene;
5. pad every scene's audio to its exact video length, concatenate in config order, write the
   final MP4, ``timings.json`` and the SRT, dispatch ``post_render``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen import __version__, hooks
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render import ffmpeg as ff
from vidgen.render.worker import scene_audio_path, scene_timings_path, scene_video_path, write_json
from vidgen.subtitles import write_srt
from vidgen.tts.elevenlabs import API_KEY_ENV

log = logging.getLogger("vidgen.render")

#: Lines of a failed worker's output shown in the error.
TAIL_LINES = 60


@dataclass
class RenderResult:
    """What :func:`render_project` produced."""

    output: Path
    srt: Path
    timings_file: Path
    duration: float
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)


@dataclass
class _WorkerRun:
    scene_id: str
    returncode: int
    output: str
    seconds: float


def _check_scenes(project: Project) -> None:
    """Every scene's type is registered, its params validate and its beat count fits (fast,
    before any rendering)."""
    from vidgen import registry

    for spec in project.config.scenes:
        cls = registry.get(spec.type).cls
        cls.parse_params(spec.params, scene_id=spec.id)
        problem = cls.check_beat_count(len(spec.beats))
        if problem is not None:
            raise VidgenError(f"scene '{spec.id}' (type {spec.type}): {problem}")


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


def _usable_render(project: Project, preview: bool, scene_id: str, no_audio: bool) -> bool:
    """True if a previous render of the scene exists and matches the current format/audio mode."""
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
    )


def _tail(text: str, lines: int = TAIL_LINES) -> str:
    """The last ``lines`` lines of worker output, progress-bar carriage returns resolved."""
    cleaned = [line.rsplit("\r", 1)[-1] for line in text.replace("\r\n", "\n").split("\n")]
    cleaned = [line for line in cleaned if line.strip()]
    return "\n".join(cleaned[-lines:])


def _run_worker(project: Project, preview: bool, scene_id: str, no_audio: bool, live: bool) -> _WorkerRun:
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


def _failure_message(run: _WorkerRun, live: bool) -> str:
    head = f"scene '{run.scene_id}' failed (worker exit code {run.returncode})"
    if live:
        return f"{head}; see the output above"
    return f"{head}:\n{_tail(run.output) or '(no output)'}"


def _runs(task: Callable[[int, str], _WorkerRun], scene_ids: list[str], jobs: int) -> Iterator[_WorkerRun]:
    """Run ``task(index, scene_id)`` for every scene and yield results as they complete.

    ``jobs == 1`` runs them one after the other in this thread. Otherwise a thread pool runs
    ``jobs`` workers at once; if the consumer stops early, queued scenes are cancelled and the
    running ones are waited for.
    """
    if jobs == 1:
        for i, sid in enumerate(scene_ids, start=1):
            yield task(i, sid)
        return
    pool = ThreadPoolExecutor(max_workers=jobs)
    try:
        futures = [pool.submit(task, i, sid) for i, sid in enumerate(scene_ids, start=1)]
        for future in as_completed(futures):
            yield future.result()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _render_scenes(
    project: Project, preview: bool, scene_ids: list[str], no_audio: bool, keep_going: bool, jobs: int
) -> tuple[list[str], list[str]]:
    """Render ``scene_ids`` with up to ``jobs`` workers; returns (rendered, failed) in config order.

    Without ``keep_going`` the first failure raises (with ``jobs > 1``, scenes already running
    finish first). ``post_scene`` is dispatched here, in the parent, after each success.
    """
    live = jobs == 1 and sys.stderr.isatty()
    total = len(scene_ids)
    order = {sid: i for i, sid in enumerate(scene_ids)}
    rendered: list[str] = []
    failed: list[str] = []
    print_lock = threading.Lock()

    def say(message: str, err: bool = False) -> None:
        with print_lock:
            print(message, file=sys.stderr if err else sys.stdout, flush=True)

    def task(index: int, scene_id: str) -> _WorkerRun:
        say(f"[{index}/{total}] {scene_id}: rendering")
        return _run_worker(project, preview, scene_id, no_audio, live)

    for run in _runs(task, scene_ids, jobs):
        if run.returncode != 0:
            failed.append(run.scene_id)
            message = _failure_message(run, live)
            if not keep_going:
                raise VidgenError(message)
            say(f"error: {message}", err=True)
            continue
        if not live:  # re-print the worker's warnings (live output has shown them already)
            for line in run.output.splitlines():
                if line.startswith("warning: "):
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
            preview=preview,
            variant=project.variant,
        )
        rendered.append(run.scene_id)
    return sorted(rendered, key=order.__getitem__), sorted(failed, key=order.__getitem__)


def join_scenes(project: Project, preview: bool, no_audio: bool, ffmpeg: str) -> tuple[Path, dict[str, Any]]:
    """Join every scene's render (config order) into the final video; returns it and the
    combined timings mapping.

    Each scene's audio (Manim's WAV, or silence for silent scenes and ``no_audio``) is padded to
    the exact length of its video. Lengths are measured from the rendered videos; the sample
    count of each scene is taken from the cumulative time, so rounding never accumulates.
    """
    render_dir = project.render_dir(preview)
    padded_dir = render_dir / "padded"
    fmt = project.render_format(preview)
    videos: list[Path] = []
    audios: list[Path] = []
    scenes: list[dict[str, Any]] = []
    offset = 0.0
    for spec in project.config.scenes:
        video = scene_video_path(project, preview, spec.id)
        timings_file = scene_timings_path(project, preview, spec.id)
        if not (video.is_file() and timings_file.is_file()):
            raise VidgenError(f"scene '{spec.id}' has no render in {render_dir}; render it first")
        timings = json.loads(timings_file.read_text(encoding="utf-8"))
        duration = ff.probe(video).duration
        samples = round((offset + duration) * ff.AUDIO_RATE) - round(offset * ff.AUDIO_RATE)
        wav = scene_audio_path(project, preview, spec.id)
        audio = padded_dir / f"{spec.id}.wav"
        ff.pad_audio(ffmpeg, wav if wav.is_file() and not no_audio else None, audio, samples)
        scenes.append(
            {
                "id": spec.id,
                "type": spec.type,
                "start": round(offset, 6),
                "duration": round(duration, 6),
                "beats": [
                    {**beat, "start": round(offset + beat["start"], 6), "end": round(offset + beat["end"], 6)}
                    for beat in timings["beats"]
                ],
            }
        )
        videos.append(video)
        audios.append(audio)
        offset += duration
    output = project.output_path(preview)
    ff.join(ffmpeg, videos, audios, output, padded_dir)
    combined = {
        "title": project.config.title,
        "variant": project.variant,
        "preview": preview,
        "format": {"width": fmt.width, "height": fmt.height, "fps": fmt.fps},
        "audio": not no_audio,
        "duration": round(offset, 6),
        "vidgen": __version__,
        "scenes": scenes,
    }
    return output, combined


def render_project(
    project: Project,
    preview: bool = False,
    scenes: list[str] | None = None,
    no_audio: bool = False,
    keep_going: bool = False,
    jobs: int = 1,
) -> RenderResult:
    """Render ``project`` (already loaded with its variant) and write the final MP4 + SRT.

    ``scenes``: render only these ids and reuse existing renders of the others (scenes without a
    usable render, e.g. never rendered or rendered at another format, are rendered too).
    ``keep_going``: render the remaining scenes after a failure; the video is then not joined and
    a :class:`VidgenError` listing the failed scenes is raised at the end.
    """
    from vidgen import extensions

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
            if not selected or sid in selected or not _usable_render(project, preview, sid, no_audio)
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
        rendered, failed = _render_scenes(project, preview, to_render, no_audio, keep_going, jobs)
        if failed:
            raise VidgenError(
                f"{len(failed)} scene(s) failed: {', '.join(failed)}; the video was not joined "
                f"({len(rendered)} scene(s) rendered)"
            )
        print("joining scenes", flush=True)
        output, timings = join_scenes(project, preview, no_audio, ffmpeg)
        timings_file = project.render_dir(preview) / "timings.json"
        write_json(timings_file, timings)
        srt = project.srt_path(preview)
        write_srt(srt, timings)
        hooks.dispatch(
            "post_render",
            project,
            output=output,
            srt=srt,
            timings=timings,
            timings_file=timings_file,
            preview=preview,
            variant=project.variant,
        )
        return RenderResult(
            output=output,
            srt=srt,
            timings_file=timings_file,
            duration=timings["duration"],
            rendered=rendered,
            reused=[sid for sid in known if sid not in rendered],
        )
