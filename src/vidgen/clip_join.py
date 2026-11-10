"""The join between two clips where the second continues the first (DESIGN.md §117): two takes
of a video model, the second generated from the last frame of the first, shown by consecutive
``video_clip`` scenes with a plain cut.

A video model draws the picture it starts from a little darker or with another tint, so the cut
flickers. :class:`ClipJoin` is the one place that knows the previous clip's last shown frame
(:meth:`ClipJoin.reference`) and this clip's first (:meth:`ClipJoin.opening`); from them it makes
the *treatment* of this clip's opening frames (a :class:`vidgen.clips.FrameTreatment`), which
``ClipMobject`` applies to each decoded frame. :class:`GainMatch` is a gain per colour channel
that makes the first frame's mean colour the reference's, eased back to 1. :class:`JoinTreatment`
adds the dissolve asked for with ``match_previous: {dissolve: N}``: the first N frames are
blended with the reference, held still.

Nothing here reads a rendered scene: the previous clip's last shown frame is decoded from its
file at the time the planned timeline gives, so scenes still render in any order.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import Field, StrictInt, ValidationError, model_validator

from vidgen.clips import ClipReader, ClipTiming, FrameTreatment, clip_timing, cover_crop, probe_clip
from vidgen.errors import Problem
from vidgen.scene import SceneParams
from vidgen.transitions import effective
from vidgen.videoplan import VideoPlan

#: The scene type whose clips can be joined.
CLIP_SCENE = "video_clip"

#: Smallest and largest gain of a colour channel between the two frames as decoded that is still
#: a continuation; outside it nothing is corrected.
GAIN_RANGE = (0.8, 1.25)
#: Limits of the gain applied to a channel. Only a chain of held corrections reaches them (each
#: adds its own to the one before); the cut then keeps the step that is left.
APPLIED_RANGE = (0.67, 1.5)
#: Largest :func:`picture_difference` of the two frames (after the gain) that is still a
#: continuation.
MAX_DIFFERENCE = 0.04
#: A channel whose mean is below this (of 255) in either frame is too dark to measure a gain.
MIN_LEVEL = 4.0
#: Size (width, height) in pixels the two frames are measured at.
MEASURE_PIXELS = (64, 64)
#: Most frames a dissolve at the cut may take (``match_previous: {dissolve: N}``).
MAX_DISSOLVE = 12
#: Largest relative difference between the shapes (width / height) of the two pictures shown
#: that a dissolve accepts: it blends them pixel on pixel.
SHAPE_TOLERANCE = 0.01

Gains = tuple[float, float, float]
Size = tuple[int, int]


class MatchPrevious(SceneParams):
    """How ``match_previous`` treats the clip: ``{seconds, hold, dissolve, level}``."""

    seconds: float = Field(default=1.0, gt=0.0, le=30.0)
    """Seconds after the cut over which the correction eases away (the clip shows its own pixels from then on)."""
    hold: bool = False
    """Keep the full correction for the whole clip (the next clip then matches this clip's corrected last frame)."""
    dissolve: StrictInt = Field(default=0, ge=0, le=MAX_DISSOLVE)
    """Frames of the render being made (preview or final) that are blended with the previous clip's last shown frame, held still (0: none)."""
    level: bool = True
    """false: no correction of brightness and colour, only the dissolve."""

    @model_validator(mode="after")
    def _level_checks(self) -> MatchPrevious:
        if not self.level:
            if self.dissolve == 0:
                raise ValueError("level: false leaves nothing to do without a dissolve (give dissolve: 1 or more, or leave match_previous out)")
            given = sorted(self.model_fields_set & {"seconds", "hold"})
            if given:
                raise ValueError(f"{given[0]}: sets the correction of brightness and colour, which level: false switches off")
        return self


@dataclass(frozen=True)
class ShownClip:
    """A clip as its ``video_clip`` scene shows it: the file, the part that plays and how, the
    ``crop`` of the picture shown (``(x, y, w, h)`` fractions) and ``last_played``, the seconds
    the clip has played at the scene's last frame."""

    path: Path
    timing: ClipTiming
    crop: tuple[float, float, float, float]
    last_played: float

    def frame(self, played: float, size: Size) -> np.ndarray:
        """The picture shown ``played`` seconds after the clip started, as RGBA of ``size``
        pixels (the crop stretched to it)."""
        reader = ClipReader(self.path, size, self.crop)
        try:
            return reader.frame(self.timing.source_time(played)).copy()
        finally:
            reader.close()


def channel_gains(reference: np.ndarray, opening: np.ndarray) -> Gains | None:
    """The gain per colour channel (R, G, B) that gives ``opening`` the mean colour of
    ``reference`` (both RGB or RGBA, uint8); ``None`` when a channel is too dark to measure
    (:data:`MIN_LEVEL`)."""
    wanted = reference[..., :3].reshape(-1, 3).mean(axis=0)
    found = opening[..., :3].reshape(-1, 3).mean(axis=0)
    if min(wanted.min(), found.min()) < MIN_LEVEL:
        return None
    r, g, b = (float(v) for v in wanted / found)
    return (r, g, b)


def apply_gains(frame: np.ndarray, gains: Gains) -> np.ndarray:
    """``frame`` (RGB or RGBA, uint8) with each colour channel multiplied by its gain (rounded,
    cut off at 255), as a new array; alpha is kept."""
    out = frame.copy()
    levels = np.arange(256, dtype=np.float64)
    for channel, gain in enumerate(gains):
        table = np.clip(np.rint(levels * gain), 0, 255).astype(np.uint8)
        out[..., channel] = table[frame[..., channel]]
    return out


def picture_difference(reference: np.ndarray, opening: np.ndarray) -> float:
    """How much two pictures of the same size differ: the mean absolute difference of their grey
    levels as a fraction of full scale (0: the same picture, 1: black against white)."""
    grey = [picture[..., :3].astype(np.float64).mean(axis=-1) for picture in (reference, opening)]
    return float(np.abs(grey[0] - grey[1]).mean() / 255.0)


def correction_left(played: float, seconds: float) -> float:
    """The share of the correction still applied ``played`` seconds after the cut: 1 at the cut,
    0 from ``seconds`` on, a smooth step between (no jump in brightness or in its rate)."""
    u = min(max(played / seconds, 0.0), 1.0)
    return 1.0 - u * u * (3.0 - 2.0 * u)


@dataclass(frozen=True)
class GainMatch:
    """The colour match as a :class:`vidgen.clips.FrameTreatment`: ``gains`` at the cut, eased
    to 1 over ``seconds``, or kept for the whole clip with ``hold``."""

    gains: Gains
    seconds: float = 1.0
    hold: bool = False

    def state(self, played: float) -> Gains | None:
        """The gains ``played`` seconds after the cut (4 decimals; ``None`` once they are 1)."""
        left = 1.0 if self.hold else correction_left(played, self.seconds)
        r, g, b = (round(1.0 + (gain - 1.0) * left, 4) for gain in self.gains)
        return None if r == g == b == 1.0 else (r, g, b)

    def apply(self, frame: np.ndarray, state: Gains) -> np.ndarray:
        return apply_gains(frame, state)


def dissolve_weight(frame: int, frames: int) -> float:
    """The weight of the previous clip's last frame in frame ``frame`` (0 = the first after the
    cut) of a dissolve of ``frames`` frames: equal steps of ``1 / (frames + 1)`` from that frame
    (weight 1, the frame before the cut) down to 0 at frame ``frames``. Three frames: 0.75, 0.5,
    0.25, so the first frame after the cut is already a quarter this clip's."""
    return max(frames - max(frame, 0), 0) / (frames + 1)


def blend(frame: np.ndarray, reference: np.ndarray, weight: float) -> np.ndarray:
    """``frame`` with its colour channels mixed with ``reference``'s (same size, RGB or RGBA,
    uint8): ``weight`` of the reference, the rest of the frame, rounded; a new array, the
    frame's alpha kept."""
    out = frame.copy()
    mixed = frame[..., :3].astype(np.float32) * (1.0 - weight) + reference[..., :3].astype(np.float32) * weight
    out[..., :3] = np.clip(np.rint(mixed), 0, 255).astype(np.uint8)
    return out


#: What a :class:`JoinTreatment` does to one frame: the gains (``None``: none) and the weight of
#: the previous clip's last frame.
JoinState = tuple[Gains | None, float]


class JoinTreatment:
    """The gain and the dissolve of one join as a :class:`vidgen.clips.FrameTreatment`: each of
    the first ``dissolve`` frames (of a render at ``fps`` frames per second) gets its gain
    (``gain``; ``None``: none) and is then blended with ``reference(size)``, the previous clip's
    last shown frame at the frame's size (width, height), by :func:`dissolve_weight`. Later
    frames get the gain alone."""

    def __init__(self, gain: GainMatch | None, dissolve: int, fps: float, reference: Callable[[Size], np.ndarray]) -> None:
        self.gain = gain
        self.dissolve = dissolve
        self.fps = fps
        self._reference = reference
        self._held: tuple[Size, np.ndarray] | None = None

    def state(self, played: float) -> JoinState | None:
        """The gains and the reference's weight ``played`` seconds after the cut (``None`` once
        both do nothing)."""
        gains = self.gain.state(played) if self.gain is not None else None
        weight = round(dissolve_weight(round(played * self.fps), self.dissolve), 4)
        return None if gains is None and weight == 0.0 else (gains, weight)

    def apply(self, frame: np.ndarray, state: JoinState) -> np.ndarray:
        gains, weight = state
        if gains is not None:
            frame = apply_gains(frame, gains)
        if weight == 0.0:
            return frame
        size = (frame.shape[1], frame.shape[0])
        if self._held is None or self._held[0] != size:
            self._held = (size, self._reference(size))
        return blend(frame, self._held[1], weight)


def measure_match(
    reference: np.ndarray, opening: np.ndarray, settings: MatchPrevious, shown_reference: np.ndarray | None = None
) -> tuple[GainMatch | None, str]:
    """The :class:`GainMatch` that makes ``opening`` (this clip's first frame) match the previous
    clip's last frame, and a line saying what was measured. ``reference`` is that frame as
    decoded: no match, and the reason, when the two are not a continuation (a gain outside
    :data:`GAIN_RANGE`, pictures differing by more than :data:`MAX_DIFFERENCE` after the gain, a
    frame too dark to measure). ``shown_reference`` is that frame as the film shows it when the
    previous scene corrects its own clip there (default: as decoded); the gains applied lead to
    it, kept within :data:`APPLIED_RANGE`."""
    gains = channel_gains(reference, opening)
    if gains is None:
        return None, "a frame at the cut is too dark to measure its colour"
    text = "gains R {:.3f} G {:.3f} B {:.3f}".format(*gains)
    low, high = GAIN_RANGE
    if min(gains) < low or max(gains) > high:
        return None, f"{text}: outside {low}-{high}, so this clip does not continue the one before"
    difference = picture_difference(reference, apply_gains(opening, gains))
    text += f", pictures differ by {difference:.3f}"
    if difference > MAX_DIFFERENCE:
        return None, f"{text}: more than {MAX_DIFFERENCE}, so this clip does not continue the one before"
    if shown_reference is not None:
        gains = channel_gains(shown_reference, opening) or gains
        low, high = APPLIED_RANGE
        wanted = gains
        r, g, b = (min(max(gain, low), high) for gain in wanted)
        gains = (r, g, b)
        text += "; with the correction held before it R {:.3f} G {:.3f} B {:.3f}".format(*gains)
        if gains != wanted:
            text += f" (limited to {low}-{high}: a step stays at this cut)"
    return GainMatch(gains, settings.seconds, settings.hold), text


class ClipJoin:
    """Where the clip ``current`` continues the clip ``previous`` at a cut. ``previous_treatment``
    is what the previous scene does to its own clip (``None``: nothing), so that
    :meth:`reference` is the frame the film shows before the cut."""

    def __init__(self, previous: ShownClip, current: ShownClip, previous_treatment: FrameTreatment | None = None) -> None:
        self.previous = previous
        self.current = current
        self.previous_treatment = previous_treatment

    def reference(self, size: Size, treated: bool = True) -> np.ndarray:
        """The previous clip's last shown frame (RGBA, ``size`` pixels) as the film shows it:
        treated as its scene treats it (``treated=False``: as decoded)."""
        frame = self.previous.frame(self.previous.last_played, size)
        treatment = self.previous_treatment if treated else None
        state = treatment.state(self.previous.last_played) if treatment is not None else None
        return frame if treatment is None or state is None else treatment.apply(frame, state)

    def opening(self, size: Size) -> np.ndarray:
        """This clip's first shown frame (RGBA, ``size`` pixels), untreated."""
        return self.current.frame(0.0, size)

    def gain_match(self, settings: MatchPrevious) -> tuple[GainMatch | None, str]:
        """:func:`measure_match` of the two frames at the cut."""
        decoded = self.reference(MEASURE_PIXELS, treated=False)
        shown = self.reference(MEASURE_PIXELS) if self.previous_treatment is not None else None
        return measure_match(decoded, self.opening(MEASURE_PIXELS), settings, shown)

    def shape_problem(self) -> str | None:
        """Why the two pictures cannot be blended pixel on pixel (``None``: they can): the parts
        of the two clips shown do not have the same shape."""
        before, after = (_shown_aspect(clip) for clip in (self.previous, self.current))
        if abs(before / after - 1.0) <= SHAPE_TOLERANCE:
            return None
        return f"the previous clip shows a picture {before:.3f} times as wide as high and this one {after:.3f}, so a dissolve cannot lay one on the other (use the same fit on both scenes)"

    def treatment(self, settings: MatchPrevious, fps: float) -> tuple[FrameTreatment | None, str]:
        """What ``settings`` does to this clip's frames in a render at ``fps`` frames per second,
        and a line saying what was measured; ``None`` and the reason when the clip does not
        continue the one before (:func:`measure_match`, also for a dissolve alone)."""
        problem = self.shape_problem() if settings.dissolve else None
        if problem is not None:
            return None, problem
        gain, text = self.gain_match(settings)
        if gain is None or not settings.dissolve:
            return gain, text
        weights = ", ".join(f"{dissolve_weight(k, settings.dissolve):.2f}" for k in range(settings.dissolve))
        text += f"; dissolve over {settings.dissolve} frames (the previous frame's weights {weights})"
        if not settings.level:
            text += ", brightness and colour left as they are"
        return JoinTreatment(gain if settings.level else None, settings.dissolve, fps, self.reference), text


def _shown_aspect(clip: ShownClip) -> float:
    """Width / height of the part of ``clip`` its scene shows."""
    return probe_clip(clip.path).aspect * clip.crop[2] / clip.crop[3]


# ----- the two scenes of a join --------------------------------------------------------------------


def _clip_params(spec: Any) -> Any:
    """The validated params of the ``video_clip`` scene ``spec``; ``None`` for another scene
    type or params that do not validate (reported by the params check)."""
    from vidgen import registry

    entry = registry.find(CLIP_SCENE) if spec.type == CLIP_SCENE else None
    if entry is None:
        return None
    try:
        return entry.cls.validate_params(spec.params)
    except ValidationError:
        return None


def match_previous_problem(config: Any, index: int) -> str | None:
    """Why scene ``index``, which asks for ``match_previous``, cannot match the scene before
    (``None``: it can)."""
    if index == 0:
        return "the first scene has no scene before it to match"
    before = config.scenes[index - 1]
    if before.type != CLIP_SCENE:
        return f"the scene before ('{before.id}') is a {before.type}, not a video_clip"
    transition = effective(config, index)
    if transition.type != "cut":
        return f"needs a cut from the scene before; the transition here is {transition.type}"
    for spec in (before, config.scenes[index]):
        params = _clip_params(spec)
        if params is not None and (params.fade or params.region != "bleed"):
            return f"scene '{spec.id}' needs fade: false and region: bleed (the two clips must meet at a plain cut, each filling the frame)"
    return None


def match_previous_problems(config: Any) -> list[Problem]:
    """``match_previous`` on scenes that cannot match the scene before (the first scene, after a
    scene that is not a ``video_clip``, with a transition, a fade or a region)."""
    problems: list[Problem] = []
    for index, spec in enumerate(config.scenes):
        params = _clip_params(spec)
        if params is None or not params.match_previous:
            continue
        problem = match_previous_problem(config, index)
        if problem is not None:
            problems.append(Problem(f"scenes[{index}].params.match_previous", problem))
    return problems


def _match_settings(params: Any) -> MatchPrevious | None:
    """``params.match_previous`` as settings (``true``: the defaults; ``None``: off)."""
    value = getattr(params, "match_previous", False)
    if isinstance(value, MatchPrevious):
        return value
    return MatchPrevious() if value else None


def shown_clip(project: Any, plan: VideoPlan, index: int, frame_aspect: float) -> ShownClip:
    """The clip of the ``video_clip`` scene ``index`` (``region: bleed``, ``fade: false``) as the
    scene shows it in a frame of ``frame_aspect`` (width / height), timed by the planned
    timeline ``plan``."""
    spec = project.config.scenes[index]
    params = _clip_params(spec)
    path = project.asset(params.path)
    info = probe_clip(path)
    seconds = plan.scene_duration(index)
    crop = cover_crop(info.aspect, frame_aspect) if params.fit == "cover" else (0.0, 0.0, 1.0, 1.0)
    return ShownClip(path, clip_timing(params, info, seconds), crop, max(seconds - 1.0 / plan.fps, 0.0))


def opening_treatment(project: Any, plan: VideoPlan, index: int, frame_aspect: float) -> tuple[FrameTreatment | None, str]:
    """What scene ``index`` does to its clip's opening frames to continue the clip of the scene
    before (``match_previous``), and a line saying what was measured or why nothing is done.
    The scene before is asked the same first when its own treatment still shows at its last
    frame (``hold``, or a scene shorter than the easing or the dissolve), so held corrections do
    not drift. A dissolve counts frames at ``plan.fps``."""
    settings = _match_settings(_clip_params(project.config.scenes[index]))
    if settings is None or match_previous_problem(project.config, index) is not None:
        return None, "match_previous is off or cannot apply here"
    previous = shown_clip(project, plan, index - 1, frame_aspect)
    before = _match_settings(_clip_params(project.config.scenes[index - 1]))
    previous_treatment = None
    if before is not None and _shows_at(before, previous.last_played, plan.fps):
        previous_treatment, _ = opening_treatment(project, plan, index - 1, frame_aspect)
    join = ClipJoin(previous, shown_clip(project, plan, index, frame_aspect), previous_treatment)
    return join.treatment(settings, plan.fps)


def _shows_at(settings: MatchPrevious, played: float, fps: float) -> bool:
    """Whether a clip treated by ``settings`` may still be treated ``played`` seconds after its
    cut."""
    levelled = settings.level and (settings.hold or played < settings.seconds)
    return levelled or round(played * fps) < settings.dissolve
