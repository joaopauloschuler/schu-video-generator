"""Reframing: on a stage wider than the frame, the camera keeps the speaker in view
(``reframe:``; DESIGN.md §69.30). No manim.

A frame narrower than a landscape one (9:16, 1:1) shows a stage laid out as wide as the 16:9
frame of the same short side (:func:`stage_base_width`), so a vertical variant keeps the
characters where the landscape video has them, and the camera crops that wider stage.
:func:`reframe_needed` says whether the characters fit in one view at all; when they do not,
``reframe: speaker`` (the default then) moves the camera to whoever speaks.

:func:`reframe_path` is a pure function from a scene's beats (who speaks and for how long, where
each character stands, the camera moves written in the beat) to the camera's moves. The camera
moves only when it must: when a speaker with a line of at least :data:`REPLY_HOLD_SECONDS` is not
wholly in view. Then it eases (:data:`REFRAME_SECONDS`) to a view with the speaker in it, some
room in front of its face, and no other character cut by the frame's edge; it cuts instead in the
first beat (the set fades in) and in a beat with a speech bubble (built for the view as the beat
starts). A short reply holds the
view on the one before. A beat with a written ``pan``, ``follow``, ``zoom`` or ``shot`` is left to
it; after a ``follow`` the camera is the followed one's until a written ``pan`` places it again.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from vidgen.cartoon.stage import facing_sign

#: ``reframe:`` values: ``speaker`` (the camera keeps the speaker in view), ``none`` (it moves only
#: as the beats' own camera actions say).
REFRAME_MODES: tuple[str, ...] = ("speaker", "none")
#: The aspect ratio of the stage a narrower frame crops: the 16:9 frame of the same short side.
LANDSCAPE_ASPECT = 16 / 9
#: A line shorter than this (seconds of narration) does not move the camera: the reply is heard
#: over the view of the line before (about four words at the default speed).
REPLY_HOLD_SECONDS = 1.5
#: Seconds the camera eases from one speaker to the next (fits in 80 % of the shortest line that
#: moves it, :data:`REPLY_HOLD_SECONDS`).
REFRAME_SECONDS = 1.0
#: Share of the view's width kept in front of the speaker's face (as a one-character shot's).
REFRAME_LOOK_ROOM = 0.1
#: Share of a character's width the frame's edge may cut before it counts as cut (lint
#: ``off_stage`` reports 5 % of its box).
CUT_TOLERANCE = 0.02

CameraMode = Literal["free", "held", "pan", "follow"]


@dataclass(frozen=True)
class ReframeFigure:
    """A character on stage during a beat (Manim units): its feet's ``x`` at the end of the beat's
    written moves, half its width, its ``facing`` and, when it moves in the beat, its ``start_x``."""

    name: str
    x: float
    half_width: float
    facing: str = "right"
    start_x: float | None = None

    def box(self) -> tuple[float, float]:
        """``(left, right)`` of the figure where it ends the beat."""
        return (self.x - self.half_width, self.x + self.half_width)

    def span(self) -> tuple[float, float]:
        """``(left, right)`` of everywhere the figure stands in the beat (start and end)."""
        start = self.x if self.start_x is None else self.start_x
        return (min(self.x, start) - self.half_width, max(self.x, start) + self.half_width)


@dataclass(frozen=True)
class ReframeBeat:
    """One beat as reframing sees it: its id, who says it, its narration's length, the characters
    on stage whose place is known, its written camera: ``free`` (none), ``held`` (a ``zoom`` or
    ``shot``: the view comes back after it), ``pan`` (to ``camera_x``, the view's centre after it;
    ``None``: not known) or ``follow``, and whether a written ``say`` draws a speech ``bubble``."""

    id: str
    speakers: tuple[str, ...]
    seconds: float
    figures: tuple[ReframeFigure, ...]
    camera: CameraMode = "free"
    camera_x: float | None = None
    bubble: bool = False


@dataclass(frozen=True)
class CameraMove:
    """A move of the camera reframing adds: in ``beat``, from its start, to a view centred on
    ``x`` (Manim units), in ``seconds`` (0: a cut)."""

    beat: str
    x: float
    seconds: float


def stage_base_width(frame_width: float, frame_height: float, reframing: bool) -> float:
    """The width (Manim units) of a stage of ``width: 1``: the frame's, or, while ``reframing`` in
    a frame narrower than a landscape one, :data:`LANDSCAPE_ASPECT` times the short side."""
    if not reframing:
        return frame_width
    return max(frame_width, LANDSCAPE_ASPECT * min(frame_width, frame_height))


def reframe_needed(boxes: Sequence[tuple[float, float]], frame_width: float) -> bool:
    """Whether the characters' ``(left, right)`` boxes are wider together than one view."""
    if not boxes:
        return False
    return max(b[1] for b in boxes) - min(b[0] for b in boxes) > frame_width


def _cuts(box: tuple[float, float], center: float, view_width: float) -> bool:
    """Whether a view centred on ``center`` cuts ``box`` (an edge inside it, past the tolerance)."""
    left, right = box
    margin = CUT_TOLERANCE * (right - left)
    return any(left + margin < edge < right - margin for edge in (center - view_width / 2, center + view_width / 2))


def _shows(box: tuple[float, float], center: float, view_width: float) -> bool:
    """Whether ``box`` is wholly in a view centred on ``center`` (up to the tolerance)."""
    left, right = box
    margin = CUT_TOLERANCE * (right - left)
    return left + margin >= center - view_width / 2 and right - margin <= center + view_width / 2


def _view_for(
    speaker: ReframeFigure, figures: Sequence[ReframeFigure], view_width: float, low: float, high: float,
) -> float:
    """The view's centre (between ``low`` and ``high``) nearest the speaker's framing (its span, or
    its end box when the span is wider than the view, with :data:`REFRAME_LOOK_ROOM` in front of
    it) that shows it wholly and cuts no other figure; without one, the framing kept in range."""
    left, right = speaker.span()
    if right - left > view_width:
        left, right = speaker.box()
    ideal = (left + right) / 2 + facing_sign(speaker.facing, front=0.0) * REFRAME_LOOK_ROOM * view_width
    lo, hi = max(low, right - view_width / 2), min(high, left + view_width / 2)
    if lo > hi:
        return min(max(ideal, low), high)
    candidates = {min(max(ideal, lo), hi), lo, hi}
    for figure in figures:   # views with an edge just at a figure's tolerance: the nearest that cut nothing
        a, b = figure.box()
        margin = CUT_TOLERANCE * (b - a)
        candidates |= {edge + side * view_width / 2 for edge in (a + margin, b - margin) for side in (-1.0, 1.0)}
    allowed = [c for c in candidates if lo - 1e-9 <= c <= hi + 1e-9 and not any(_cuts(f.box(), c, view_width) for f in figures)]
    if not allowed:
        return min(max(ideal, lo), hi)
    return min(allowed, key=lambda c: (abs(c - ideal), c))


def _first_speaker(beat: ReframeBeat) -> ReframeFigure | None:
    """The beat's first speaker on stage whose place is known, when its line is long enough."""
    if beat.seconds < REPLY_HOLD_SECONDS:
        return None
    on_stage = {f.name: f for f in beat.figures}
    return next((on_stage[s] for s in beat.speakers if s in on_stage), None)


def _upcoming_speaker(beats: Sequence[ReframeBeat], first: ReframeBeat) -> ReframeFigure | None:
    """The scene's first speaker (before any written camera move) as it stands in the ``first``
    beat; ``None``: no one speaks before then, or it is not on stage yet."""
    for beat in beats:
        if beat.camera != "free":
            return None
        speaker = _first_speaker(beat)
        if speaker is not None:
            return next((f for f in first.figures if f.name == speaker.name), None)
    return None


def reframe_path(
    beats: Sequence[ReframeBeat], *, frame_width: float, bounds: tuple[float, float], start_x: float, following: bool = False,
) -> list[CameraMove]:
    """The camera's moves that keep each speaker in view (DESIGN.md §69.30), from the view
    centred on ``start_x`` on a stage from ``bounds`` (left, right), the view ``frame_width`` wide.
    In a ``free`` beat whose speaker (:func:`_first_speaker`) is not wholly in view the camera
    eases to it at the beat's start (a cut in the first beat and in a beat with a speech
    bubble); before the first line, the first beat cuts to the scene's first speaker when the start
    view does not show it. Beats with a written camera move get nothing, and a ``follow`` leaves
    the camera alone until a ``pan`` whose view is known; ``following``: the camera follows a
    character from the start (a level's hero, DESIGN.md §86.10), as after a ``follow``."""
    low, high = bounds[0] + frame_width / 2, bounds[1] - frame_width / 2
    if low > high:
        return []
    camera: float | None = None if following else min(max(start_x, low), high)
    moves: list[CameraMove] = []
    for k, beat in enumerate(beats):
        if beat.camera == "pan":
            camera = None if beat.camera_x is None else min(max(beat.camera_x, low), high)
            continue
        if beat.camera == "follow":
            camera = None
            continue
        if beat.camera == "held" or camera is None:
            continue
        speaker = _first_speaker(beat)
        if speaker is None and k == 0:
            speaker = _upcoming_speaker(beats, beat)
        if speaker is None or _shows(speaker.span(), camera, frame_width):
            continue
        camera = _view_for(speaker, beat.figures, frame_width, low, high)
        moves.append(CameraMove(beat.id, camera, REFRAME_SECONDS if k > 0 and not beat.bubble else 0.0))
    return moves


__all__ = [
    "CUT_TOLERANCE",
    "LANDSCAPE_ASPECT",
    "REFRAME_LOOK_ROOM",
    "REFRAME_MODES",
    "REFRAME_SECONDS",
    "REPLY_HOLD_SECONDS",
    "CameraMove",
    "ReframeBeat",
    "ReframeFigure",
    "reframe_needed",
    "reframe_path",
    "stage_base_width",
]
