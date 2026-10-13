"""Transitions between scenes (DESIGN.md §49, §50): which transition leads into a scene, how many
frames it takes, how much of the scenes it may overlap, and the narration track of a video
whose scenes overlap. No manim: used by the planned timeline, the render pipeline, validation.

The timing contract: a ``crossfade``, ``push`` or ``wipe`` **overlaps** the two scenes (the next
one starts while the previous one's last frames are still on screen, so the video gets shorter by
the overlap); a ``fade_color`` does not (the previous scene's last frames fade to the colour, the
next scene's first frames fade in from it), nor does an ``iris_out`` / ``iris_in`` (a circle
closes over the previous scene's last frames and opens over the next one's first, drawn in the
renders like the fade, so the join sees a cut). Each one only covers the **silent tail** of the scene
before (the frames after its last narration ends): when that tail is shorter than the transition,
the scene before is held longer (``hold``) so no two narrations ever sound at once.
"""

from __future__ import annotations

import math
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from vidgen.cartoon.motion import smoothstep
from vidgen.config import DIRECTED_TRANSITIONS, IRIS_TRANSITIONS, TransitionConfig, VideoConfig
from vidgen.errors import Problem, VidgenError

if TYPE_CHECKING:
    from vidgen.project import Project
    from vidgen.theme import Theme

#: The transition of a scene nothing else sets.
CUT = TransitionConfig()
#: ``color`` naming the theme's background (also the default of ``fade_color``).
BACKGROUND = "background"
#: The colour of an iris without ``color``: the classic cartoon black.
IRIS_COLOR = "#000000"
#: An iris closing on a character pauses around its head: it reaches the head's circle
#: (:data:`IRIS_HEAD_SCALE` x half the head box's diagonal) at the first share of its closing
#: frames and leaves it at the second (opening: the same in reverse).
IRIS_HOLD = (0.55, 0.8)
IRIS_HEAD_SCALE = 1.5


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
    """Frames a transition asks for: the overlap of a crossfade / push / wipe, a fade_color's or
    an iris's frames on *each* side (half its duration); 0 for a cut."""
    if transition.overlaps:
        return max(1, round(transition.seconds * fps))
    if transition.through_color:
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
    ``overlap`` of a crossfade / push / wipe, the fade-in of a fade_color, the opening of an iris."""
    t = effective(config, index)
    if t.overlaps:
        return overlap
    if t.through_color:
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


def resolve_color(color: str | None, theme: Theme, kind: str = "fade_color") -> str:
    """The hex colour a ``fade_color`` or an iris (``kind``) passes through: ``color`` as written
    (a theme token or hex; ``background``: the theme's background); ``None``: the theme's
    background for a fade_color, :data:`IRIS_COLOR` for an iris."""
    if color is None and kind in IRIS_TRANSITIONS:
        return IRIS_COLOR
    if color in (None, BACKGROUND):
        return theme.background
    return theme.color(color)


def iris_scene(index: int, transition: TransitionConfig) -> int:
    """The scene whose character or point an iris into scene ``index`` targets: the scene
    before for ``iris_out`` (it closes on it), the scene itself for ``iris_in`` (it opens on it)."""
    return index - 1 if transition.type == "iris_out" else index


def iris_problems(config: VideoConfig) -> list[Problem]:
    """Irises whose ``character`` is not on the scene they close or open on (scene types that
    declare their targets; skipped where the params do not validate, reported elsewhere)."""
    from pydantic import ValidationError

    from vidgen import registry
    from vidgen.cartoon.cast import character_names

    declared = set(character_names(config))
    problems: list[Problem] = []
    for i, spec in enumerate(config.scenes):
        t = effective(config, i)
        if t.type not in IRIS_TRANSITIONS or t.character is None or iris_scene(i, t) < 0:
            continue
        target = config.scenes[iris_scene(i, t)]
        entry = registry.find(target.type)
        if entry is None or not entry.cls.target_patterns:
            continue
        try:
            names = [n for n in entry.cls.target_names(entry.cls.validate_params(target.params)) if n in declared]
        except ValidationError:
            continue
        if t.character not in names:
            where = f"scenes[{i}].transition.character" if spec.transition is not None else "transition.character"
            on_stage = f"its characters: {', '.join(names)}" if names else "it has no characters"
            side = "closes on" if t.type == "iris_out" else "opens on"
            problems.append(Problem(where, f"the {t.type} into '{spec.id}' {side} '{t.character}', who is not in scene '{target.id}' ({on_stage})"))
    return problems


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


# ----- fade_color and irises inside a scene's render ----------------------------------------------------


def hex_rgb(color: str) -> tuple[int, int, int]:
    """``#RGB`` / ``#RRGGBB`` / ``#RRGGBBAA`` as an RGB triple (alpha ignored)."""
    digits = color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def iris_radius(weight: float, full: float, hold: float | None = None) -> float:
    """Radius (pixels) of an iris whose colour covers ``weight`` of its way (0: open, the circle
    of radius ``full`` clears the frame; 1: closed). It eases from ``full`` to 0; with ``hold``
    (a head's circle) it eases to ``hold``, stays there between the :data:`IRIS_HOLD` shares,
    then closes."""
    w = min(max(weight, 0.0), 1.0)
    if hold is None or hold >= full:
        return full * (1.0 - smoothstep(w))
    reach, leave = IRIS_HOLD
    if w <= reach:
        return full + (hold - full) * smoothstep(w / reach)
    if w <= leave:
        return hold
    return hold * (1.0 - smoothstep((w - leave) / (1.0 - leave)))


def iris_full_radius(width: int, height: int, x: float, y: float) -> float:
    """Radius (pixels) of a circle about ``(x, y)`` that just clears a ``width`` x ``height``
    frame (its farthest corner, plus the soft edge)."""
    return max(math.hypot(cx - x, cy - y) for cx in (0.0, width) for cy in (0.0, height)) + 1.0


def iris_coverage(height: int, width: int, x: float, y: float, radius: float) -> np.ndarray:
    """``height`` x ``width`` weights of the picture inside a circle of ``radius`` pixels about
    pixel point ``(x, y)``: 1 inside, 0 outside, a one-pixel soft edge (pixel centres at +0.5)."""
    ys = np.arange(height, dtype=np.float32)[:, None] + 0.5 - y
    xs = np.arange(width, dtype=np.float32)[None, :] + 0.5 - x
    return np.clip(radius + 0.5 - np.sqrt(xs * xs + ys * ys), 0.0, 1.0)


@dataclass(frozen=True)
class IrisPoint:
    """Where an iris closes or opens, in pixels of the frame (``x`` right, ``y`` down from the
    top-left corner), and the radius it pauses at (a character's head; ``None``: no pause)."""

    x: float
    y: float
    hold: float | None = None


class ColorFade:
    """A scene's first ``frames_in`` frames faded in from ``color_in`` and its last
    ``frames_out`` frames (of ``total``) faded out to ``color_out`` (DESIGN.md §49).

    Wraps the renderer's ``add_frame`` outermost, so the fade applies to the scene's picture and
    the overlays (drawn by the next wrapper in) stay on top, as they do in a crossfade. The
    colour's weight is 1 on the scene's very first and last frame and falls linearly over the
    fade (``1 - k / frames_in`` in, ``(j + 1) / frames_out`` out).

    ``iris_in`` / ``iris_out`` (DESIGN.md §69.45): the colour covers the frame outside a circle
    instead of blending into it: the circle opens over the first frames from the point the
    callable returns (asked on each of those frames, so it follows a moving character) and
    closes over the last ones; its radius is :func:`iris_radius` of the same weight.
    """

    def __init__(
        self,
        color_in: str | None,
        frames_in: int,
        color_out: str | None,
        frames_out: int,
        total: int,
        iris_in: Callable[[int, int], IrisPoint] | None = None,
        iris_out: Callable[[int, int], IrisPoint] | None = None,
    ) -> None:
        self.color_in = np.array(hex_rgb(color_in), dtype=np.float32) if color_in else None
        self.color_out = np.array(hex_rgb(color_out), dtype=np.float32) if color_out else None
        self.frames_in = frames_in if color_in else 0
        self.frames_out = frames_out if color_out else 0
        self.total = total
        self.iris_in = iris_in
        self.iris_out = iris_out
        self.written = 0

    def iris_at(self, frame: int) -> Callable[[int, int], IrisPoint] | None:
        """The iris point callable at the scene's frame ``frame`` (``None``: a plain fade or none)."""
        if self.frames_out and frame >= self.total - self.frames_out:
            return self.iris_out
        if self.frames_in and frame < self.frames_in:
            return self.iris_in
        return None

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
        iris = self.iris_at(k)
        if iris is None:
            out[:, :, :3] = np.rint(frame[:, :, :3] * (1.0 - w) + color * w).clip(0, 255).astype(np.uint8)
            return out
        height, width = frame.shape[:2]
        point = iris(width, height)
        radius = iris_radius(w, iris_full_radius(width, height, point.x, point.y), point.hold)
        inside = iris_coverage(height, width, point.x, point.y, radius)[:, :, None]
        out[:, :, :3] = np.rint(frame[:, :, :3] * inside + color * (1.0 - inside)).clip(0, 255).astype(np.uint8)
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
