"""A heads-up display over the frame (DESIGN.md §102.5), the maths without manim: what an implant,
a helmet's visor or a robot's eye shows — readout lines appearing one by one, a blinking alert, a
heart monitor (a scrolling trace, the rate rising, beats skipped) and a scanner's meter (a live
wave that can spike off its scale). :mod:`vidgen.scenes.hud` draws it as the ``hud`` overlay.

Times are seconds since the HUD came on (its ``at``). Every value is a pure function of that
time, so the overlay looks the same on both sides of a cut.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

#: The HUD's colours by default: a cool cyan for readouts, a hot red for warnings.
HUD_COLOR = "#5FFFE0"
HUD_WARNING = "#FF3B5C"
#: An alert blinks: on for this share of each period (seconds).
ALERT_PERIOD = 0.8
ALERT_ON = 0.68
#: Seconds between readout lines appearing (the first at the HUD's start), and how long one
#: flickers in.
HUD_LINE_SECONDS = 0.6
LINE_FLICKER = 0.25
#: A heart rate change takes this long (seconds, eased).
HEART_RISE = 1.6
#: The heart trace shows this many seconds, scrolling left.
HEART_WINDOW = 3.0
#: A scan level change takes this long (seconds, eased); above 1 the meter is off its scale.
SCAN_RISE = 0.7


def _ease(share: float) -> float:
    share = min(max(share, 0.0), 1.0)
    return share * share * (3.0 - 2.0 * share)


def alert_on(t: float, period: float = ALERT_PERIOD) -> bool:
    """Whether a blinking alert shows at ``t`` (on for :data:`ALERT_ON` of each period, from on)."""
    return t < 0 or (t % period) / period < ALERT_ON


def lines_shown(t: float, count: int, every: float = HUD_LINE_SECONDS) -> list[float]:
    """How much each of ``count`` readout lines shows at ``t`` (0 .. 1): line ``k`` comes at
    ``k * every``, flickering in over :data:`LINE_FLICKER` seconds."""
    out: list[float] = []
    for k in range(count):
        since = t - k * every
        if since <= 0:
            out.append(0.0)
        elif since >= LINE_FLICKER:
            out.append(1.0)
        else:   # a few quick flashes while it comes
            out.append(1.0 if int(since / LINE_FLICKER * 5) % 2 == 0 else 0.35)
    return out


def changing_value(t: float, start: float, end: float | None, at: float, rise: float) -> float:
    """A value that starts at ``start`` and eases to ``end`` from ``at`` over ``rise`` seconds
    (``end`` ``None``: stays at ``start``)."""
    if end is None or t <= at:
        return start
    return start + (end - start) * _ease((t - at) / rise)


@dataclass(frozen=True)
class HeartMonitor:
    """A heart monitor's settings: the rate (``bpm``), the one it rises (or falls) to from ``at``
    seconds (``to``; ``None``: steady), and ``skips`` beats left out right at ``at`` (a heart that
    skips three beats)."""

    bpm: float = 72.0
    to: float | None = None
    at: float = 0.0
    skips: int = 0


def heart_rate(t: float, heart: HeartMonitor) -> float:
    """The heart rate (beats a minute) at ``t``."""
    return changing_value(t, heart.bpm, heart.to, heart.at, HEART_RISE)


def heart_beats(until: float, heart: HeartMonitor, since: float = -HEART_WINDOW) -> list[float]:
    """The times of the beats from ``since`` to ``until``: one every 60 / rate seconds (the rate
    then), counted from time 0 (and back from it before), leaving out the ``skips`` beats that
    would come first from ``at`` (the gap a skipped beat leaves)."""
    beats: list[float] = []
    t = 0.0
    while t > since:   # before the start: steady at the first rate
        t -= 60.0 / heart.bpm
    skipped = 0
    while t <= until:
        if t >= heart.at and skipped < heart.skips:
            skipped += 1
        elif t >= since:
            beats.append(t)
        t += 60.0 / max(heart_rate(t, heart), 20.0)
    return beats


def ecg(phase: float) -> float:
    """A heartbeat's trace at ``phase`` seconds after the beat (-1 .. 1, 0 flat): a small bump,
    the sharp spike and its dip, a slow wave after."""
    if phase < 0.0 or phase > 0.42:
        return 0.0
    if phase < 0.06:   # P
        return 0.12 * math.sin(math.pi * phase / 0.06)
    if phase < 0.09:
        return 0.0
    if phase < 0.11:   # Q
        return -0.15 * math.sin(math.pi * (phase - 0.09) / 0.02)
    if phase < 0.15:   # R
        return 1.0 * math.sin(math.pi * (phase - 0.11) / 0.04)
    if phase < 0.18:   # S
        return -0.35 * math.sin(math.pi * (phase - 0.15) / 0.03)
    if phase < 0.24:
        return 0.0
    return 0.22 * math.sin(math.pi * (phase - 0.24) / 0.18)   # T


def heart_trace(t: float, heart: HeartMonitor, samples: int = 90, window: float = HEART_WINDOW) -> list[float]:
    """The heart monitor's trace at ``t``: ``samples`` values (-1 .. 1) from ``window`` seconds
    ago (left) to now (right)."""
    beats = heart_beats(t, heart, since=t - window - 0.5)
    out: list[float] = []
    for k in range(samples):
        when = t - window + window * k / max(samples - 1, 1)
        out.append(max((ecg(when - b) for b in beats if b <= when), key=abs, default=0.0))
    return out


@dataclass(frozen=True)
class ScanMeter:
    """A scanner meter's settings: its ``level`` (0 .. 1 of its scale), the one it moves to from
    ``at`` seconds (``to``; above 1: off the scale; ``None``: steady), and its wave
    (``organic``: a living, irregular wave; ``steady``: a regular one)."""

    level: float = 0.35
    to: float | None = None
    at: float = 0.0
    wave: str = "organic"


def scan_level(t: float, scan: ScanMeter) -> float:
    """The scan level at ``t`` (may pass 1: off the scale)."""
    return changing_value(t, scan.level, scan.to, scan.at, SCAN_RISE)


#: Placing the HUD's texts clear of faces (DESIGN.md §102.8): a face's box is grown by this share
#: of its size on each side; a place covering at most :data:`FACE_COVER` of the faces keeps its
#: texts there, another must be better by :data:`FACE_SWITCH` for them to move.
FACE_GROW = 0.12
FACE_COVER = 0.02
FACE_SWITCH = 0.05

#: A box on screen: left, bottom, right, top (frame units, y up).
Box = tuple[float, float, float, float]


def _overlap(a: Box, b: Box) -> float:
    """The area ``a`` and ``b`` share."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def grown(face: Box, share: float = FACE_GROW) -> Box:
    """``face`` grown by ``share`` of its width and height on each side."""
    dx, dy = (face[2] - face[0]) * share, (face[3] - face[1]) * share
    return (face[0] - dx, face[1] - dy, face[2] + dx, face[3] + dy)


def face_cover(box: Box, faces: Sequence[Box]) -> float:
    """How much of the ``faces`` (each grown by :data:`FACE_GROW`) ``box`` covers: the sum of the
    shares of each face's box under it (0: clear of every face)."""
    total = 0.0
    for face in faces:
        big = grown(face)
        size = max((big[2] - big[0]) * (big[3] - big[1]), 1e-9)
        total += _overlap(box, big) / size
    return total


def pick_place(places: Sequence[Box], faces: Sequence[Box], current: int | None = None, avoid: Sequence[Box] = ()) -> int:
    """Which of ``places`` (boxes a text block could stand in, in order of preference) to put it
    in: the one covering the least of the ``faces`` (:func:`face_cover`), the first of equals; a
    place overlapping one of ``avoid`` (another block of the HUD) only when every one does. The
    ``current`` place is kept while it covers at most :data:`FACE_COVER` or is within
    :data:`FACE_SWITCH` of the best, so the texts do not hop about."""
    scores = [face_cover(box, faces) + (10.0 if any(_overlap(box, other) > 1e-9 for other in avoid) else 0.0) for box in places]
    best = min(range(len(places)), key=lambda k: (round(scores[k], 6), k))
    if current is not None and 0 <= current < len(places):
        if scores[current] <= FACE_COVER or scores[current] <= scores[best] + FACE_SWITCH:
            return current
    return best


def scan_wave(t: float, scan: ScanMeter, samples: int = 60) -> list[float]:
    """The scanner's wave at ``t``: ``samples`` values (about -1 .. 1, scaled by the level, at
    most 1.6) across its window, moving left; ``organic`` mixes drifting partials, ``steady`` is
    one sine."""
    level = min(scan_level(t, scan), 1.6)
    out: list[float] = []
    for k in range(samples):
        x = k / max(samples - 1, 1)
        if scan.wave == "steady":
            value = math.sin(2 * math.pi * (3 * x - 1.2 * t))
        else:
            value = (0.55 * math.sin(2 * math.pi * (2.3 * x - 0.9 * t))
                     + 0.3 * math.sin(2 * math.pi * (5.1 * x - 1.7 * t) + 1.3 * math.sin(0.7 * t))
                     + 0.15 * math.sin(2 * math.pi * (11.7 * x - 3.1 * t) + 2.0))
        out.append(value * level)
    return out


__all__ = [
    "ALERT_ON",
    "ALERT_PERIOD",
    "FACE_COVER",
    "FACE_GROW",
    "FACE_SWITCH",
    "HEART_RISE",
    "HEART_WINDOW",
    "HUD_COLOR",
    "HUD_WARNING",
    "LINE_FLICKER",
    "HUD_LINE_SECONDS",
    "SCAN_RISE",
    "HeartMonitor",
    "ScanMeter",
    "alert_on",
    "changing_value",
    "ecg",
    "face_cover",
    "grown",
    "heart_beats",
    "heart_rate",
    "heart_trace",
    "lines_shown",
    "pick_place",
    "scan_level",
    "scan_wave",
]
