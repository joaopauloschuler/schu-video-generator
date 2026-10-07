"""ffmpeg and media helpers for the render pipeline: discovery, audio padding, concatenation and
reading stream information with PyAV.

Every ffmpeg call uses a list of arguments (no shell), so paths with spaces, quotes or non-ASCII
characters are passed through unchanged.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av

from vidgen.errors import VidgenError
from vidgen.fileio import replace_file

#: Audio of every padded scene (and so of the final video): AAC, 48 kHz, stereo.
AUDIO_RATE = 48000
AUDIO_BITRATE = "192k"
#: Quality of the video when the join has to encode it (crossfades, DESIGN.md §49): visually
#: lossless next to the scenes' own encoding (Manim: CRF 23).
VIDEO_CRF = "18"


def find_ffmpeg() -> str:
    """Path of the ``ffmpeg`` executable on PATH; :class:`VidgenError` with install hints if absent."""
    exe = shutil.which("ffmpeg")
    if exe is None:
        if sys.platform == "win32":
            hint = "install it with `winget install ffmpeg` (then open a new terminal)"
        elif sys.platform == "darwin":
            hint = "install it with `brew install ffmpeg`"
        else:
            hint = "install it with your package manager, e.g. `sudo apt install ffmpeg`"
        raise VidgenError(f"ffmpeg not found on PATH; {hint}. See https://ffmpeg.org/download.html")
    return exe


def run_ffmpeg(ffmpeg: str, args: list[str], what: str) -> None:
    """Run ``ffmpeg -y -v error <args>``; a failure becomes a :class:`VidgenError` with stderr."""
    result = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-nostdin", "-v", "error", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        details = result.stderr.strip()[-2000:] or f"exit code {result.returncode}"
        raise VidgenError(f"ffmpeg failed while {what}:\n{details}")


@dataclass(frozen=True)
class VideoInfo:
    """What the pipeline needs to know about a rendered scene file."""

    width: int
    height: int
    fps: Fraction
    duration: float  # of the video stream, in seconds


def probe(path: Path) -> VideoInfo:
    """Read the resolution, frame rate and video-stream duration of ``path``.

    The rate is the stream's nominal one (``r_frame_rate``): Manim joins a scene from partial
    movies whose timestamps make the *average* rate drift (15.0003 for 15 fps), which put the
    duration a fraction of a millisecond off ``frames / fps`` per scene."""
    try:
        with av.open(str(path)) as container:
            video = container.streams.video[0]
            fps = Fraction(video.guessed_rate or video.average_rate or 0)
            if video.frames and fps:
                duration = float(video.frames / fps)
            elif video.duration is not None and video.time_base is not None:
                duration = float(video.duration * video.time_base)
            elif container.duration is not None:
                duration = container.duration / av.time_base
            else:
                raise ValueError("no duration information")
            return VideoInfo(
                width=video.codec_context.width,
                height=video.codec_context.height,
                fps=fps,
                duration=duration,
            )
    except (OSError, ValueError, IndexError, av.error.FFmpegError) as exc:
        raise VidgenError(f"cannot read video file {path}: {exc}") from None


def pad_audio(ffmpeg: str, src: Path | None, dst: Path, samples: int) -> None:
    """Write ``dst``: a 48 kHz stereo PCM WAV of exactly ``samples`` samples.

    It holds ``src`` (Manim's uncompressed mix of the scene's sounds) padded with silence or
    trimmed to that length, or pure silence when ``src`` is ``None``. PCM keeps every sample, so
    concatenating these files cannot drift (AAC segments would each add encoder priming).
    """
    fmt = f"aformat=sample_fmts=s16:sample_rates={AUDIO_RATE}:channel_layouts=stereo"
    trim = f"apad=whole_len={samples},atrim=end_sample={samples}"
    if src is not None:
        inputs = ["-i", str(src)]
        graph = f"aresample={AUDIO_RATE},{fmt},{trim}"
    else:
        inputs = ["-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo"]
        graph = f"{fmt},{trim}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(ffmpeg, [*inputs, "-af", graph, "-c:a", "pcm_s16le", str(dst)], f"padding the audio for {dst.name}")


def concat_quote(path: str) -> str:
    """Quote a path for an ffmpeg concat list: ``'...'`` with each ``'`` written as ``'\\''``."""
    return "'" + path.replace("'", "'\\''") + "'"


def write_concat_list(files: list[Path], list_file: Path) -> None:
    """Write an ffmpeg concat list (UTF-8). Paths are relative to the list's folder when
    possible (ffmpeg resolves them that way), otherwise absolute; both are quoted."""
    lines = []
    for f in files:
        try:
            entry = f.relative_to(list_file.parent).as_posix()
        except ValueError:
            entry = f.resolve().as_posix()
        lines.append(f"file {concat_quote(entry)}\n")
    list_file.parent.mkdir(parents=True, exist_ok=True)
    list_file.write_text("".join(lines), encoding="utf-8")


def crossfade_graph(runs: list[int], crossfades: list[int], fps: int, kinds: list[str] | None = None) -> tuple[list[str], str]:
    """The filter graph blending video inputs ``0 .. len(runs) - 1`` (``runs[k]`` frames each)
    with a transition of ``crossfades[k - 1]`` frames between input ``k - 1`` and ``k``: its
    filters and the output label. ``kinds[k - 1]`` is the ``xfade`` transition (default ``fade``;
    ``slideleft``, ``wipeup``... for a push or wipe, DESIGN.md §50). Each transition starts half
    a frame before its first shared frame, so the progress at shared frame ``j`` is ``(j + 0.5) /
    n`` (symmetric; the middle frame of an odd crossfade is 50/50) and the output has exactly
    ``sum(runs) - sum(crossfades)`` frames."""
    graph = [f"[{k}:v]settb=AVTB,setpts=PTS-STARTPTS[r{k}]" for k in range(len(runs))]
    label, length = "r0", runs[0]
    for k in range(1, len(runs)):
        n = crossfades[k - 1]
        kind = kinds[k - 1] if kinds else "fade"
        graph.append(f"[{label}][r{k}]xfade=transition={kind}:duration={n / fps:.6f}:offset={(length - n - 0.5) / fps:.6f}[x{k}]")
        label, length = f"x{k}", length + runs[k] - n
    return graph, label


def overlay_graph(label: str, clips: list[tuple[int, int]], fps: int) -> tuple[list[str], str]:
    """Filters drawing RGBA clips over the video labelled ``label``: ``clips`` are ``(input
    index, first output frame)``; each clip's frame ``j`` lands exactly on output frame
    ``start + j`` (shifted half a frame early, so rounding cannot move it), and the video passes
    unchanged outside the clips (the clips end with a transparent frame,
    :class:`vidgen.overlay_layer.RgbaClip`)."""
    graph = []
    for k, (index, start) in enumerate(clips):
        graph.append(f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS+{(start - 0.5) / fps:.6f}/TB[c{k}]")
        graph.append(f"[{label}][c{k}]overlay=eof_action=pass:format=yuv444[o{k}]")
        label = f"o{k}"
    return graph, label


def join(
    ffmpeg: str,
    videos: list[Path],
    audios: list[Path],
    dst: Path,
    work_dir: Path,
    sfx: Path | None = None,
    mix: Path | None = None,
    crossfades: list[int] | None = None,
    frames: list[int] | None = None,
    fps: int | None = None,
    kinds: list[str] | None = None,
    overlays: list[tuple[Path, int]] | None = None,
    metadata: Path | None = None,
) -> None:
    """Concatenate ``videos`` (stream copy, video only) and ``audios`` (PCM, encoded once to AAC)
    into ``dst`` with the concat demuxer.

    ``sfx``: a WAV as long as the whole video (the sound effects track, DESIGN.md §47), added
    sample for sample to the concatenated audio (``amix`` without normalising: both keep their
    levels) before encoding. ``mix``: the finished mix of the whole video (DESIGN.md §48), used
    as the audio instead of ``audios`` and ``sfx``.

    ``crossfades`` (DESIGN.md §49): per boundary between ``videos[i]`` and ``videos[i + 1]``,
    the frames they overlap (0: a cut), with ``frames`` (each video's frame count) and ``fps``.
    With any crossfade, the scenes joined by cuts are concatenated into runs and the runs blended
    with ffmpeg's ``xfade``, so the video is encoded once (H.264, CRF :data:`VIDEO_CRF`) instead
    of stream-copied. ``kinds``: the ``xfade`` transition per boundary (default ``fade``; a push
    / wipe slides or wipes, DESIGN.md §50). ``overlays``: RGBA clips ``(path, first output
    frame)`` drawn over the joined pictures (the overlays of frames a push / wipe moves).

    ``metadata``: an FFMETADATA file whose global tags and chapters become the output's
    (DESIGN.md §52; the MP4 muxer stores the chapters as a chapter track plus a Nero ``chpl``
    list); without it the output keeps FFmpeg's defaults.

    ``dst`` is written via a temporary file next to it and replaced at the end, so a failed join
    never leaves a truncated output. If ``dst`` cannot be replaced (on Windows: it is open in a
    video player), the joined video is kept as ``<name>.partial.mp4`` and the error says so.
    """
    audio_list = work_dir / "audio_concat.txt"
    write_concat_list(audios, audio_list)
    tmp = dst.with_name(f"{dst.stem}.partial{dst.suffix}")
    graph: list[str] = []
    if (crossfades and any(crossfades)) or overlays:
        crossfades = crossfades or [0] * (len(videos) - 1)
        if frames is None or fps is None or len(frames) != len(videos) or len(crossfades) != len(videos) - 1:
            raise VidgenError("joining with crossfades needs every video's frame count and the frame rate")
        groups: list[list[int]] = [[0]]
        for i in range(1, len(videos)):
            if crossfades[i - 1]:
                groups.append([i])
            else:
                groups[-1].append(i)
        inputs: list[str] = []
        for k, group in enumerate(groups):
            run_list = work_dir / f"video_concat_{k}.txt"
            write_concat_list([videos[i] for i in group], run_list)
            inputs += ["-f", "concat", "-safe", "0", "-i", str(run_list)]
        blends, label = crossfade_graph(
            [sum(frames[i] for i in group) for group in groups],
            [crossfades[g[0] - 1] for g in groups[1:]],
            fps,
            [kinds[g[0] - 1] for g in groups[1:]] if kinds else None,
        )
        graph += blends
        for clip, _ in overlays or []:
            inputs += ["-i", str(clip)]
        drawn, label = overlay_graph(label, [(len(groups) + k, start) for k, (_, start) in enumerate(overlays or [])], fps)
        graph += drawn
        video_map, video_codec = f"[{label}]", ["-c:v", "libx264", "-crf", VIDEO_CRF, "-pix_fmt", "yuv420p"]
        first_audio = len(groups) + len(overlays or [])
    else:
        video_list = work_dir / "video_concat.txt"
        write_concat_list(videos, video_list)
        inputs = ["-f", "concat", "-safe", "0", "-i", str(video_list)]
        video_map, video_codec, first_audio = "0:v:0", ["-c:v", "copy"], 1
    if mix is not None:
        inputs += ["-i", str(mix)]
        audio_map = f"{first_audio}:a:0"
    elif sfx is None:
        inputs += ["-f", "concat", "-safe", "0", "-i", str(audio_list)]
        audio_map = f"{first_audio}:a:0"
    else:
        inputs += ["-f", "concat", "-safe", "0", "-i", str(audio_list), "-i", str(sfx)]
        graph.append(f"[{first_audio}:a][{first_audio + 1}:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix]")
        audio_map = "[mix]"
    tagging: list[str] = []
    if metadata is not None:
        index = inputs.count("-i")
        inputs += ["-f", "ffmetadata", "-i", str(metadata)]
        tagging = ["-map_metadata", str(index), "-map_chapters", str(index)]
    filters = ["-filter_complex", ";".join(graph)] if graph else []
    try:
        run_ffmpeg(
            ffmpeg,
            [
                *inputs,
                *filters,
                "-map", video_map, "-map", audio_map,
                *video_codec, "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(AUDIO_RATE),
                *tagging,
                "-movflags", "+faststart",
                str(tmp),
            ],
            f"joining the scenes into {dst.name}",
        )
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:
        replace_file(tmp, dst)
    except VidgenError as exc:
        raise VidgenError(f"{exc}\nthe new video was saved as {tmp}") from None
