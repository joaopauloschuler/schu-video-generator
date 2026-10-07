"""Transitions between scenes (DESIGN.md §49, §50): which transition leads into a scene, how many
frames it takes, how much of the scenes it may overlap, and the narration track of a video
whose scenes overlap. No manim: used by the planned timeline, the render pipeline, validation.

The timing contract: a ``crossfade``, ``push`` or ``wipe`` **overlaps** the two scenes (the next
one starts while the previous one's last frames are still on screen, so the video gets shorter by
the overlap); a ``fade_color`` does not (the previous scene's last frames fade to the colour, the
next scene's first frames fade in from it). Each one only covers the **silent tail** of the scene
before (the frames after its last narration ends): when that tail is shorter than the transition,
the scene before is held longer (``hold``) so no two narrations ever sound at once.
"""

from __future__ import annotations

import math
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from vidgen.config import DIRECTED_TRANSITIONS, TransitionConfig, VideoConfig
from vidgen.errors import Problem, VidgenError

if TYPE_CHECKING:
    from vidgen.project import Project
    from vidgen.theme import Theme

#: The transition of a scene nothing else sets.
CUT = TransitionConfig()
#: ``color`` naming the theme's background (also the default of ``fade_color``).
BACKGROUND = "background"


def effective(config: VideoConfig, index: int) -> TransitionConfig:
    """The transition into scene ``index``: its own ``transition``, else the video's (not for the
    first scene: there is nothing before it), else a cut."""
    spec = config.scenes[index]
    if spec.transition is not None:
        return spec.transition
    if index > 0 and config.transition is not None:
        return config.transition
    return CUT


def has_transitions(config: VideoConfig) -> bool:
    """Whether any scene starts with something other than a cut."""
    return any(effective(config, i).type != "cut" for i in range(len(config.scenes)))


def requested_frames(transition: TransitionConfig, fps: int) -> int:
    """Frames a transition asks for: the overlap of a crossfade / push / wipe, a fade_color's
    frames on *each* side (half its duration); 0 for a cut."""
    if transition.overlaps:
        return max(1, round(transition.seconds * fps))
    if transition.type == "fade_color":
        return max(1, round(transition.seconds * fps / 2))
    return 0


def silent_tail(frames: int, speech_end: float | None, head: int, fps: int) -> int:
    """Frames at the end of a scene of ``frames`` frames that a transition out of it may cover:
    after its narration ends (``speech_end``, seconds; ``None`` for a silent scene) and after the
    ``head`` frames its own incoming transition uses."""
    spoken = math.ceil(speech_end * fps - 1e-6) if speech_end else 0
    return max(0, frames - max(spoken, head))


def join_overlaps(config: VideoConfig, fps: int, frames: Sequence[int], speech_ends: Sequence[float | None]) -> list[int]:
    """The frames each scene overlaps the one before it when the rendered scenes (``frames``
    long, narrated until ``speech_ends``) are joined: the frames of a crossfade / push / wipe,
    limited to the silent tail of the scene before and the scene's own length (0 for every other
    transition and the first scene). The planned hold makes the tail long enough, so this equals
    the plan unless a render differs from it."""
    out = [0] * len(frames)
    for i in range(1, len(frames)):
        t = effective(config, i)
        if not t.overlaps:
            continue
        tail = silent_tail(frames[i - 1], speech_ends[i - 1], head_frames(config, i - 1, fps, frames[i - 1], out[i - 1]), fps)
        out[i] = max(0, min(requested_frames(t, fps), tail, frames[i]))
    return out


def head_frames(config: VideoConfig, index: int, fps: int, frames: int, overlap: int) -> int:
    """Frames at the start of scene ``index`` (``frames`` long) its incoming transition uses: the
    ``overlap`` of a crossfade / push / wipe, the fade-in of a fade_color."""
    t = effective(config, index)
    if t.overlaps:
        return overlap
    if t.type == "fade_color":
        return min(requested_frames(t, fps), frames)
    return 0


def direction(transition: TransitionConfig, portrait: bool) -> str | None:
    """Where a push / wipe moves: its ``direction``, else ``up`` in a tall frame and ``left``
    otherwise (the next scene comes in from below / from the right); ``None`` for other types."""
    if transition.type not in DIRECTED_TRANSITIONS:
        return None
    return transition.direction or ("up" if portrait else "left")


def xfade_name(transition: TransitionConfig, portrait: bool) -> str:
    """ffmpeg ``xfade`` transition blending into a scene with ``transition`` (an overlapping
    one): ``fade`` for a crossfade, ``slide<dir>`` for a push, ``wipe<dir>`` (``smooth<dir>``
    when ``soft``) for a wipe. ``<dir>`` is the way the pictures / the edge move."""
    way = direction(transition, portrait)
    if transition.type == "push":
        return f"slide{way}"
    if transition.type == "wipe":
        return f"{'smooth' if transition.soft else 'wipe'}{way}"
    return "fade"


def moves_pictures(transition: TransitionConfig) -> bool:
    """Whether the transition moves the pictures or an edge across them (push, wipe): unlike a
    fade it is not linear per pixel, so overlays are drawn once on top of it at the join instead
    of in both scenes (DESIGN.md §50)."""
    return transition.type in DIRECTED_TRANSITIONS


def resolve_color(color: str | None, theme: Theme) -> str:
    """The hex colour a ``fade_color`` fades through: ``color`` as written (a theme token or
    hex; ``background`` or ``None``: the theme's background)."""
    if color in (None, BACKGROUND):
        return theme.background
    return theme.color(color)


def color_problems(config: VideoConfig, theme: Theme) -> list[Problem]:
    """``transition.color`` values (video and scenes) that are not theme colours."""
    entries = [("transition.color", config.transition)]
    entries += [(f"scenes[{i}].transition.color", s.transition) for i, s in enumerate(config.scenes)]
    problems = []
    for where, transition in entries:
        if transition is not None and transition.color not in (None, BACKGROUND):
            try:
                theme.color(transition.color)
            except VidgenError as exc:
                problems.append(Problem(where, f"{exc} (or {BACKGROUND})"))
    return problems


def transition_warnings(project: Project) -> list[str]:
    """Transitions longer than the silence at the end of the scene before them: that scene is
    held longer so no narration overlaps (``vidgen validate`` says by how much)."""
    from vidgen import extensions, registry
    from vidgen.videoplan import VideoPlan

    config = project.config
    if not has_transitions(config):
        return []

    def collect() -> list[str]:
        plan = VideoPlan(project, config.format.fps)
        out = []
        for i in range(1, len(config.scenes)):
            slot = plan.transition(i)
            if slot.hold:
                before, spec = config.scenes[i - 1], config.scenes[i]
                out.append(
                    f"scenes[{i}].transition: the {slot.type} into '{spec.id}' ({slot.seconds:g} s) is longer than the "
                    f"silence at the end of '{before.id}'; '{before.id}' is held {slot.hold / plan.fps:.2f} s longer "
                    "so no narration overlaps (shorten the transition or raise narration.pad to avoid it)"
                )
        return out

    if all(registry.find(spec.type) is not None for spec in config.scenes):
        return collect()
    try:
        with extensions.project_session(project):
            return collect()
    except VidgenError:
        return []  # reported as problems elsewhere


# ----- fade_color inside a scene's render ----------------------------------------------------------------


def hex_rgb(color: str) -> tuple[int, int, int]:
    """``#RGB`` / ``#RRGGBB`` / ``#RRGGBBAA`` as an RGB triple (alpha ignored)."""
    digits = color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


class ColorFade:
    """A scene's first ``frames_in`` frames faded in from ``color_in`` and its last
    ``frames_out`` frames (of ``total``) faded out to ``color_out`` (DESIGN.md §49).

    Wraps the renderer's ``add_frame`` outermost, so the fade applies to the scene's picture and
    the overlays (drawn by the next wrapper in) stay on top, as they do in a crossfade. The
    colour's weight is 1 on the scene's very first and last frame and falls linearly over the
    fade (``1 - k / frames_in`` in, ``(j + 1) / frames_out`` out).
    """

    def __init__(self, color_in: str | None, frames_in: int, color_out: str | None, frames_out: int, total: int) -> None:
        self.color_in = np.array(hex_rgb(color_in), dtype=np.float32) if color_in else None
        self.color_out = np.array(hex_rgb(color_out), dtype=np.float32) if color_out else None
        self.frames_in = frames_in if color_in else 0
        self.frames_out = frames_out if color_out else 0
        self.total = total
        self.written = 0

    def weight(self, frame: int) -> tuple[float, np.ndarray | None]:
        """The colour and its weight (0..1) at the scene's frame ``frame``."""
        if self.frames_out and frame >= self.total - self.frames_out:
            return min(1.0, (frame - (self.total - self.frames_out) + 1) / self.frames_out), self.color_out
        if self.frames_in and frame < self.frames_in:
            return 1.0 - frame / self.frames_in, self.color_in
        return 0.0, None

    def apply(self, frame: np.ndarray, k: int) -> np.ndarray:
        """``frame`` (H x W x 4, uint8) as written at the scene's frame ``k`` (a copy when faded)."""
        w, color = self.weight(k)
        if color is None or w <= 0:
            return frame
        out = np.array(frame, copy=True)
        out[:, :, :3] = np.rint(frame[:, :, :3] * (1.0 - w) + color * w).clip(0, 255).astype(np.uint8)
        return out

    def attach(self, renderer: object) -> None:
        """Fade the frames ``renderer`` writes (call after every other ``add_frame`` wrapper)."""
        original = renderer.add_frame  # type: ignore[attr-defined]

        def add_frame(frame: np.ndarray, num_frames: int = 1) -> None:
            if getattr(renderer, "skip_animations", False) or num_frames <= 0:
                original(frame, num_frames)
                return
            start = self.written
            run = 0
            for k in range(start, start + num_frames):
                if self.weight(k)[1] is None:
                    run += 1
                    continue
                if run:
                    original(frame, run)
                    run = 0
                original(self.apply(frame, k), 1)
            if run:
                original(frame, run)
            self.written = start + num_frames

        renderer.add_frame = add_frame  # type: ignore[attr-defined]


# ----- the narration track of overlapping scenes ------------------------------------------------------


def _read_pcm(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as src:
        if src.getnchannels() != 2 or src.getsampwidth() != 2:
            raise VidgenError(f"{path}: expected a stereo 16-bit WAV")
        return np.frombuffer(src.readframes(src.getnframes()), dtype="<i2").reshape(-1, 2).astype(np.int32)


def write_voice_track(parts: Sequence[Path], overlaps: Sequence[int], dst: Path, rate: int) -> int:
    """Write ``dst``: the padded scene WAVs ``parts`` one after the other, each overlapping the
    one before by ``overlaps[i]`` samples (``overlaps[0]`` is ignored). In an overlap the scene
    before fades out (raised cosine) under the next one, whose sound keeps its level: that tail
    is narration-free by the timing contract, so only a clip's sound can be there. Returns the
    samples written."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    carry: np.ndarray | None = None
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        for i, path in enumerate(parts):
            data = _read_pcm(path)
            if carry is not None:
                n = min(len(carry), len(data))
                data[:n] += carry[:n]
            nxt = overlaps[i + 1] if i + 1 < len(parts) else 0
            keep = max(0, len(data) - nxt)
            out.writeframes(np.clip(data[:keep], -32768, 32767).astype("<i2").tobytes())
            written += keep
            tail = data[keep:]
            if len(tail):
                fade = 0.5 + 0.5 * np.cos(np.pi * (np.arange(len(tail)) + 0.5) / len(tail))
                carry = np.rint(tail * fade[:, None]).astype(np.int32)
            else:
                carry = None
    return written
