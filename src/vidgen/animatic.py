"""``vidgen animatic``: the storyboard's stills timed to the narration, as an MP4 (DESIGN.md §75).

:func:`make_animatic` makes sure every scene has current stills (rendering, like ``vidgen
storyboard``, only the scenes whose stills are missing or stale; current stills at any count per
beat are reused), then joins them with ffmpeg alone, no Manim:

- :func:`hold_plan`: each still is shown from its time in the video until the next still's
  (beat-end stills from their beat's end, mid-action stills from half-way through their action);
  a scene's first still from the scene's start, the video's first from 0;
- :func:`with_captions`: the holds cut where the subtitle cues start and end, each piece with the
  cue texts shown then, drawn onto the still by :func:`draw_captions` (Pillow);
- the audio of the video as ``vidgen render`` makes it (:func:`vidgen.render.pipeline.prepare_join`:
  narration, sound effects, music, ambience, mixed and normalised);
- :func:`vidgen.render.ffmpeg.join_stills`: the concat demuxer with a duration per still.
"""

from __future__ import annotations

import io
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from vidgen.config import FormatConfig
from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic
from vidgen.project import Project
from vidgen.subtitles import Cue


@dataclass(frozen=True)
class AnimaticStill:
    """A storyboard still: its scene, beat (``None`` for a silent scene), ``time`` in the video,
    PNG ``path`` and, for a mid-action still, the actions it shows half-way (``mid``)."""

    scene_id: str
    beat_id: str | None
    time: float
    path: Path
    mid: str | None = None


@dataclass(frozen=True)
class Hold:
    """A still shown from frame ``start`` up to (not including) frame ``end``, with the caption
    texts drawn on it (``()``: none)."""

    still: AnimaticStill
    start: int
    end: int
    captions: tuple[str, ...] = ()


def hold_plan(scenes: Sequence[tuple[float, Sequence[AnimaticStill]]], frames: int, fps: int) -> list[Hold]:
    """The holds of a video of ``frames`` frames at ``fps`` whose scenes (config order) start at
    the given times (seconds in the video) with the given stills.

    Each still is held from its time until the next still's; a scene's first still from the
    scene's start (so a scene never opens on the scene before it), the video's first from frame
    0, the last until the end. A still of a scene at or after the next scene's start (it can only
    happen where scenes overlap, DESIGN.md §49) is left out. Times are rounded to frames; a still
    that would be held no frame is left out.
    """
    if fps <= 0:
        raise ValueError("fps must be positive")
    starts: list[tuple[int, int, int, AnimaticStill]] = []
    for i, (scene_start, stills) in enumerate(scenes):
        next_start = scenes[i + 1][0] if i + 1 < len(scenes) else math.inf
        for j, still in enumerate(sorted(stills, key=lambda s: s.time)):
            if j and still.time >= next_start:
                continue
            frame = min(max(round((scene_start if j == 0 else still.time) * fps), 0), frames)
            starts.append((frame, i, j, still))
    starts.sort(key=lambda entry: entry[:3])
    holds: list[Hold] = []
    for k, (frame, _, _, still) in enumerate(starts):
        start = 0 if k == 0 else frame
        end = starts[k + 1][0] if k + 1 < len(starts) else frames
        if end > start:
            holds.append(Hold(still, start, end))
    return holds


def with_captions(holds: Sequence[Hold], cues: Sequence[Cue], fps: int) -> list[Hold]:
    """``holds`` cut at the frames where ``cues`` start and end, each piece with the texts of the
    cues shown during it (in cue order: overlapping beats' cues stack); neighbouring pieces of
    the same still with the same texts are merged."""
    spans = [(round(c.start * fps), round(c.end * fps), c.text) for c in cues]
    spans = [(a, b, text) for a, b, text in spans if b > a]
    cuts = sorted({frame for a, b, _ in spans for frame in (a, b)})
    pieces: list[Hold] = []
    for hold in holds:
        points = [hold.start, *(c for c in cuts if hold.start < c < hold.end), hold.end]
        for a, b in zip(points, points[1:]):
            texts = tuple(text for start, end, text in spans if start <= a < end)
            last = pieces[-1] if pieces else None
            if last is not None and last.still == hold.still and last.captions == texts and last.end == a:
                pieces[-1] = replace(last, end=b)
            else:
                pieces.append(Hold(hold.still, a, b, texts))
    return pieces


#: Caption text height as a share of the frame's shorter side, and the plate's opacity (0-255).
CAPTION_SIZE = 0.055
CAPTION_PLATE_ALPHA = 170


def draw_captions(image: Image.Image, texts: Sequence[str]) -> Image.Image:
    """``image`` (RGB) with ``texts`` (cue texts, lines split by ``\\n``) drawn white on a dark
    plate near the bottom, centred, wrapped to 90 % of the width."""
    from vidgen.sheets import load_font, wrap_text

    width, height = image.size
    font = load_font(max(round(min(width, height) * CAPTION_SIZE), 9), bold=True)
    lines = [wrapped for text in texts for line in text.split("\n") for wrapped in wrap_text(font, line, width * 0.9, 3)]
    if not lines:
        return image
    _, glyph_top, _, glyph_bottom = font.getbbox("Ag")
    line_height = max(round((glyph_bottom - glyph_top) * 1.45), 1)
    pad = max(round(line_height * 0.3), 2)
    block_w = max(font.getlength(line) for line in lines)
    block_h = line_height * len(lines)
    bottom = height - round(height * 0.05)
    top = bottom - block_h - 2 * pad
    left = (width - block_w) / 2 - pad
    plate = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(plate)
    draw.rectangle((left, top, left + block_w + 2 * pad, bottom), fill=(0, 0, 0, CAPTION_PLATE_ALPHA))
    for k, line in enumerate(lines):
        x = (width - font.getlength(line)) / 2
        draw.text((x, top + pad + k * line_height), line, font=font, fill=(255, 255, 255, 255))
    return Image.alpha_composite(image.convert("RGBA"), plate).convert("RGB")


@dataclass
class AnimaticResult:
    """What :func:`make_animatic` made: the MP4 ``output``, its length, format, whether it has
    audio and drawn captions, the ``holds`` (without the caption cuts), the scenes rendered for
    their stills and those reused, the workers' ``(scene_id, message)`` warnings and the mix
    report (``None`` without audio)."""

    output: Path
    duration: float
    format: FormatConfig
    audio: bool
    captions: bool
    holds: list[Hold] = field(default_factory=list)
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)
    mix: dict[str, Any] | None = None


def animatic_dir(project: Project) -> Path:
    """``<preview render_dir>/animatic``: the animatic's captioned stills, tracks and lists."""
    return project.render_dir(True) / "animatic"


def captions_default(project: Project) -> bool:
    """Whether the animatic draws captions when not told: yes unless the video burns in a
    ``captions`` overlay (then the stills show them already)."""
    return not any(overlay.type == "captions" for overlay in project.config.overlays)


def _scene_stills(project: Project, scene_id: str, scene_start: float) -> list[AnimaticStill]:
    from vidgen.render.worker import scene_frames_dir

    folder = scene_frames_dir(project, True, scene_id)
    try:
        index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise VidgenError(f"scene '{scene_id}' has no stills in {folder}; run `vidgen animatic` again") from None
    return [
        AnimaticStill(scene_id, s["beat"], round(scene_start + s["time"], 6), folder / s["path"], s.get("mid"))
        for s in index["frames"]
    ]


def _write_pictures(holds: Sequence[Hold], folder: Path) -> list[Path]:
    """The picture of each hold: its still, or (with captions) the still with them drawn, written
    once per still and texts into ``folder``."""
    from vidgen.render.worker import remove_tree

    remove_tree(folder)
    made: dict[tuple[Path, tuple[str, ...]], Path] = {}
    pictures = []
    for hold in holds:
        if not hold.captions:
            pictures.append(hold.still.path)
            continue
        key = (hold.still.path, hold.captions)
        if key not in made:
            with Image.open(hold.still.path) as still:
                picture = draw_captions(still.convert("RGB"), hold.captions)
            buffer = io.BytesIO()
            picture.save(buffer, format="PNG", compress_level=3)
            made[key] = folder / f"{len(made) + 1:04d}.png"
            write_bytes_atomic(made[key], buffer.getvalue())
        pictures.append(made[key])
    return pictures


def make_animatic(project: Project, *, no_audio: bool = False, captions: bool | None = None, jobs: int = 1) -> AnimaticResult:
    """Make ``project``'s animatic (loaded with its variant) from the preview's storyboard stills.

    Scenes without current stills are rendered first (with one still per beat, ``jobs`` at a
    time). ``no_audio``: a silent track; ``captions``: draw the subtitle cues (``None``:
    :func:`captions_default`). Writes :meth:`Project.animatic_path`.
    """
    from vidgen import extensions
    from vidgen.render import ffmpeg as ff
    from vidgen.render.pipeline import SceneRuns, audio_language, prepare_join, render_scenes, video_cues
    from vidgen.storyboard import stills_current

    if jobs < 1:
        raise VidgenError("--jobs must be at least 1")
    known = [s.id for s in project.config.scenes]
    to_render = [sid for sid in known if not stills_current(project, True, sid, None)]
    # current stills mean the scenes were checked when they were rendered from this config
    runs = render_scenes(project, True, to_render, jobs=jobs, frames=1) if to_render else SceneRuns()
    ffmpeg = ff.find_ffmpeg()
    fmt = project.render_format(True)
    work = animatic_dir(project)
    draw = captions_default(project) if captions is None else captions
    with extensions.project_session(project):
        parts = prepare_join(project, True, no_audio, ffmpeg, work / "audio")
        timings = parts.timings
        frames = round(timings["duration"] * fmt.fps)
        scenes = [(scene["start"], _scene_stills(project, scene["id"], scene["start"])) for scene in timings["scenes"]]
        holds = hold_plan(scenes, frames, fmt.fps)
        if not holds:
            raise VidgenError("the video has no stills to show")
        shown = with_captions(holds, video_cues(project, timings), fmt.fps) if draw else holds
        pictures = _write_pictures(shown, work / "stills")
        output = project.animatic_path()
        output.parent.mkdir(parents=True, exist_ok=True)
        ff.join_stills(
            ffmpeg,
            pictures,
            [(h.end - h.start) / fmt.fps for h in shown],
            frames,
            fmt.fps,
            parts.audios,
            output,
            work,
            sfx=parts.sfx,
            mix=parts.mix,
            language=audio_language(project),
        )
    return AnimaticResult(
        output=output,
        duration=timings["duration"],
        format=fmt,
        audio=not no_audio,
        captions=draw,
        holds=holds,
        rendered=runs.rendered,
        reused=[sid for sid in known if sid not in runs.rendered],
        warnings=runs.warnings,
        mix=timings.get("mix"),
    )
