"""``vidgen motion check``: watch a rendered video for motion faults (DESIGN.md §121.3).

The video (a file, a project's rendered video, or its rendered scene clips) is decoded once by
ffmpeg at low resolution (:attr:`Thresholds.width`, 160 px wide) and piped as raw RGB frames; each
frame becomes a few numbers (mean luma and its spread, the colour means, a 16-bin luma histogram,
10 x 10 px block means and the blocks' change from the last three frames) and is dropped, so the
memory is about 1 KB a frame and the time is the decode's. The checks then read those series:

- ``blank``: near-uniform frames (black, or one flat colour) entered or left abruptly, the NaN
  shader bug of Parallel Space v7 (error inside a scene; info at a cut); a long dark stretch
  reached by a fade is info.
- ``flash``: one or two frames much brighter (flash) or darker (drop-out) than both neighbours
  (warning; info when it starts on a drum hit or a note of the project's score: a reaction to the music).
- ``flicker``: the luma (of the frame, or of a few blocks) going up and down every frame or two
  for a stretch (warning; info when its peaks fall on the score's hits and notes: beat-locked pulses).
- ``pop``: a region that changes for one or two frames and comes back while the blocks around
  it stay still (warning).
- ``strobe``: many blocks alternating between two pictures frame by frame for a stretch, the
  temporal aliasing of a fast rotation or a pattern moving half its period a frame (warning).
- ``frozen``: frames without visible change for long inside a scene (info).
- ``cut_jump``: a large change of brightness or of the luma histogram across a cut (info).

Dark frames (DESIGN.md §122.5) are also decoded at :attr:`Thresholds.detail_width` (640 px) in
the same ffmpeg run, where star points, a subject, clipped white, flat steps and the stars'
frame-to-frame brightness can be seen; a frame with many small bright points on black is a star
field, not a blank frame. The checks of dark pictures:

- ``blank`` also covers stars or a subject that vanish in one frame and come back (error).
- ``clipped``: a large area clipped to flat white in a dark frame, an over-exposed sun or planet (warning).
- ``shimmer``: stars whose brightness jumps from frame to frame, the sub-pixel aliasing of
  small point stars (warning). A star is followed across the frames after taking out the
  shift most bright stars share (a pan); streaks (a warp) are not point stars and do not count.
- ``banding``: dark gradients (nebula glow, an atmosphere's limb) in flat steps (info).
- ``empty``: a long stretch with no star field and only a tiny subject (info).
- ``lost``: in the scenes named with ``subject=`` (``--subject``), a stretch of dark frames
  with no subject, only stars or black (warning).

Each finding has its time, frame, scene and severity and a contact strip PNG of the frames
around it (decoded again, at :attr:`Thresholds.strip_width`).
"""

from __future__ import annotations

import dataclasses
import difflib
import math
import subprocess
import tempfile
import time
from collections import deque
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from vidgen.errors import VidgenError

Severity = Literal["error", "warning", "info"]
#: Findings whose contact strip shows the middle of the frame at full size (stars are lost when it is scaled down).
CROP_KINDS: tuple[str, ...] = ("shimmer",)
SEVERITIES: tuple[Severity, ...] = ("error", "warning", "info")
#: Block side in pixels of the decoded frame.
BLOCK = 10
#: Luma weights (Rec. 709).
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


@dataclass
class Thresholds:
    """What the checks count as a fault. Luma and changes are 0..1 (1 = white, or a change from
    black to white); ``--threshold NAME=VALUE`` sets one."""

    width: int = 160
    """Width the video is decoded at (pixels; the height keeps the aspect ratio)."""
    blank_std: float = 0.012
    """A frame whose luma spread (standard deviation) is under this is near-uniform (3/255)."""
    blank_jump: float = 0.06
    """A uniform run entered or left by a luma step of at least this is abrupt (a fault, not a fade)."""
    dark_seconds: float = 1.0
    """A uniform run reached by a fade is reported (info) when at least this long and inside the video."""
    flash: float = 0.08
    """A frame's luma step (to it and back) that makes a flash or a drop-out."""
    flash_revert: float = 0.35
    """...when the frame after comes back to within this share of the step."""
    flicker: float = 0.02
    """A frame-to-frame luma step counted in an oscillation (the whole frame)."""
    flicker_block: float = 0.05
    """The same for one 10 x 10 block (local flicker)."""
    flicker_blocks: int = 3
    """Blocks that must oscillate together for local flicker."""
    flicker_window: int = 12
    """Frames of the sliding window an oscillation is counted in."""
    flicker_share: float = 0.6
    """Share of the window's frames that must reverse direction (up, down, up...)."""
    pop: float = 0.12
    """A block's mean change that makes it pop (when it comes back one or two frames later)."""
    pop_revert: float = 0.35
    """...to within this share of the change."""
    pop_quiet: float = 0.04
    """Three in four blocks around a popping region change less than this, and none by ``pop`` (else it is something moving)."""
    pop_area: float = 0.5
    """A pop covering more than this share of the frame is a flash, not a pop."""
    pop_blocks: int = 2
    """A pop of fewer blocks than this is info (a glint or a spark more often than a fault)."""
    strobe: float = 0.06
    """A block's change that counts as alternating (when two frames back it is almost the same)."""
    strobe_blocks: int = 4
    """Blocks alternating in one frame for the frame to strobe."""
    strobe_share: float = 0.5
    """Share of a second's frames that strobe for a strobing stretch."""
    frozen: float = 0.0015
    """Mean change under which two frames are the same (encoder noise stays under it)."""
    frozen_seconds: float = 1.5
    """Unchanging frames at least this long inside a scene are a frozen stretch."""
    cut_luma: float = 0.2
    """A luma step across a cut that is a jump."""
    cut_hist: float = 0.8
    """A luma-histogram distance across a cut (L1 of the 16-bin shares, 0..2) that is a jump."""
    beat_frames: float = 1.5
    """A flash or pulse that starts this many frames or less after a drum hit or a note start follows the music."""
    beat_share: float = 0.7
    """Share of a flicker's peaks on hits and notes that makes it beat-locked pulses (info)."""
    group_seconds: float = 0.5
    """Findings of one kind closer than this are one finding."""
    strip_width: int = 240
    """Width of each frame in the contact strips (pixels)."""
    max_strips: int = 40
    """Contact strips written at most (the most severe findings first)."""
    detail_width: int = 640
    """Width of the finer picture dark frames are measured at, decoded in the same ffmpeg run (0: none; the checks of dark pictures are left out)."""
    dark_level: float = 0.05
    """A pixel of the 160 px frame under this luma is dark..."""
    dark_share: float = 0.3
    """...and a frame with at least this share of dark pixels is measured in detail."""
    star_contrast: float = 0.04
    """A star point: a pixel that is the brightest of its 3 x 3 and at least this much brighter than the ring around it (the 5 x 5 border)..."""
    star_ring: float = 0.35
    """...and that ring at most this share of its brightness (a point, not an edge or a gradient)."""
    star_field: int = 12
    """A frame that looks blank at 160 px but has at least this many star points is a star field, not a blank frame."""
    subject_level: float = 0.06
    """A detail pixel brighter than this, away from star points, is part of a subject (a planet, a craft, a glow)."""
    subject_area: float = 0.0005
    """A subject covers at least this share of the frame (115 px at 640 x 360)."""
    vanish_area: float = 0.01
    """A subject this large (share of the frame) that is gone in the next frame, and back within ``vanish_seconds``, vanished (error)."""
    vanish_seconds: float = 1.0
    """...the longest gap of such a vanish."""
    still_level: float = 0.016
    """A detail pixel that changes by this much (4/255) has changed (encoder noise stays under it)..."""
    still_pixels: float = 0.0003
    """...and a dark frame with fewer changed pixels than this share, against the first frame of its still stretch, is unchanged (slow drift adds up)."""
    clip_level: float = 0.985
    """A detail pixel at or over this luma is clipped white..."""
    clip_area: float = 0.03
    """...and a dark frame with this share of clipped pixels is over-exposed (a disc of 94 px radius at 1280 x 720)."""
    shimmer: float = 0.2
    """A frame's stars shimmer when the median star's light (3 x 3 px, found again within 4 px) differs from the mean of the frames before and after by this share..."""
    shimmer_stars: int = 20
    """...measured on at least this many stars, half of them found again in a neighbouring frame..."""
    shimmer_share: float = 0.5
    """...on this share of a second's frames."""
    shimmer_reach: int = 48
    """A pan is found up to this many detail pixels a frame: the shift most of the brightest stars share is taken out before a star is looked for again..."""
    shimmer_point: float = 0.6
    """...and only point-like stars count: at least this share of the light within 3 px of the peak lies within 1 px (a streak of a warp does not)."""
    band_run: int = 6
    """A flat step of a dark gradient (luma codes 3 to 90) at least this many detail pixels long, in a staircase of three steps of 1 or 2 codes the same way..."""
    band_share: float = 0.15
    """...covering this share of the frame makes it banded..."""
    band_seconds: float = 1.0
    """...for at least this long."""
    empty_area: float = 0.002
    """A dark frame with fewer than ``star_field`` stars and a subject under this share of the frame is nearly empty..."""
    empty_seconds: float = 2.0
    """...reported (info) when it lasts at least this long."""
    lost_seconds: float = 1.0
    """In a scene named with ``--subject``, dark frames without a subject for at least this long: the subject is lost (warning)."""

    def with_overrides(self, pairs: Sequence[str]) -> Thresholds:
        """A copy with ``NAME=VALUE`` pairs applied; :class:`VidgenError` for an unknown name or a bad value."""
        names = {f.name: f for f in dataclasses.fields(self)}
        changes: dict[str, Any] = {}
        for pair in pairs:
            name, sep, value = pair.partition("=")
            name = name.strip().replace("-", "_")
            if not sep or name not in names:
                close = difflib.get_close_matches(name, list(names), n=1)
                hint = f" (did you mean '{close[0]}'?)" if close else ""
                raise VidgenError(f"--threshold {pair}: expected NAME=VALUE with a known name{hint}; names: {', '.join(names)}")
            kind = int if names[name].type in (int, "int") else float
            try:
                number = kind(value)
            except ValueError:
                raise VidgenError(f"--threshold {pair}: {value!r} is not a {'whole ' if kind is int else ''}number") from None
            if number < 0 or (kind is int and number == 0 and name in ("width", "strip_width", "flicker_window")):
                raise VidgenError(f"--threshold {pair}: must be positive")
            changes[name] = number
        return dataclasses.replace(self, **changes)

    def to_json(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# ----- the input ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """One file to decode, placed at ``first`` (its frame 0 in the whole timeline)."""

    path: Path
    first: int = 0


@dataclass(frozen=True)
class SceneSpan:
    """A scene's frames ``start`` to ``end`` (exclusive) in the timeline."""

    id: str
    start: int
    end: int


@dataclass
class Source:
    """What to watch: the files (one video, or a project's scene clips in order), the frame
    rate, the scenes (empty when unknown) and the music's events: drum hits and note starts
    (timeline frames, may be fractional)."""

    label: str
    segments: list[Segment]
    fps: float
    scenes: list[SceneSpan] = field(default_factory=list)
    hits: np.ndarray = field(default_factory=lambda: np.zeros(0))
    hit_source: str | None = None
    notes: list[str] = field(default_factory=list)
    clips: bool = False
    """One segment per scene (a project's scene clips): the scenes follow the decoded clips."""


def probe(path: Path) -> tuple[int, int, float]:
    """``(width, height, fps)`` of a video file's first video stream; :class:`VidgenError` if it has none."""
    import av

    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                raise VidgenError(f"{path}: no video stream")
            stream = container.streams.video[0]
            rate = stream.average_rate or stream.guessed_rate or 30
            return stream.codec_context.width, stream.codec_context.height, float(rate)
    except av.error.FFmpegError as exc:
        raise VidgenError(f"{path}: cannot read it as a video ({exc})") from None


def _decoded_size(width: int, height: int, target: int) -> tuple[int, int]:
    w = min(target, width)
    w -= w % 2
    h = max(2, round(height * w / width / 2) * 2)
    return w, h


def decode_frames(path: Path, width: int, ffmpeg: str | None = None, detail: int = 0) -> Iterator[Any]:
    """The video's frames as ``uint8`` RGB arrays ``(h, w, 3)``, scaled to ``width`` by ffmpeg
    (area filter) and read from a pipe one at a time. With ``detail`` wider than that (and the
    video wider still), each item is ``(frame, finer)``: the same frame scaled to ``detail`` too,
    both from one ffmpeg run (the small picture's bytes are the same as without it)."""
    from vidgen.render.ffmpeg import find_ffmpeg

    src_w, src_h, _ = probe(path)
    w, h = _decoded_size(src_w, src_h, width)
    dw, dh = _decoded_size(src_w, src_h, detail) if detail else (0, 0)
    head = [ffmpeg or find_ffmpeg(), "-v", "error", "-nostdin", "-i", str(path)]
    if dw > w:
        # one picture holds both: the small frame (padded to the finer width) above the finer one
        graph = (f"[0:v:0]split[a][b];[a]scale={w}:{h}:flags=area,format=rgb24,pad={dw}:{h}[s];"
                 f"[b]scale={dw}:{dh}:flags=area,format=rgb24[d];[s][d]vstack")
        command = [*head, "-filter_complex", graph, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    else:
        dw = 0
        command = [*head, "-map", "0:v:0", "-vf", f"scale={w}:{h}:flags=area", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    size = (dw * (h + dh) if dw else w * h) * 3
    # ffmpeg's messages go to a file, not a second pipe: a damaged file can log more than a pipe holds
    # (4 KB on Windows) while the frames are read, and both programs would wait for each other
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log)
        assert proc.stdout is not None
        try:
            while True:
                data = proc.stdout.read(size)
                if len(data) < size:
                    break
                if dw:
                    both = np.frombuffer(data, dtype=np.uint8).reshape(h + dh, dw, 3)
                    yield both[:h, :w], both[h:]
                else:
                    yield np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)
        finally:
            proc.stdout.close()
            code = proc.wait()
            log.seek(0)
            err = log.read().decode("utf-8", "replace")
    if code != 0:
        raise VidgenError(f"ffmpeg could not decode {path}: {err.strip()[-400:]}")


# ----- the features ------------------------------------------------------------------------------------


@dataclass
class Features:
    """Per frame of the timeline: ``luma`` mean and ``spread`` (std), ``rgb`` means, ``hist``
    (16 luma bins, shares), ``mad`` mean absolute change from the frame before (NaN at a file's
    first frame), ``blocks`` the block means and ``d1``/``d2``/``d3`` each block's mean absolute
    change from 1, 2 and 3 frames before (NaN where there is none), ``starts`` the frames where a
    file starts. Dark frames measured in the finer picture (``detail`` True; NaN or False
    elsewhere): ``stars`` (star points), ``subject``, ``clipped`` and ``banded`` (shares of the
    frame), ``shimmer`` (the stars' mean jump in brightness against the frames around), ``still``
    (unchanged since the first frame of its still stretch)."""

    luma: np.ndarray
    spread: np.ndarray
    rgb: np.ndarray
    hist: np.ndarray
    mad: np.ndarray
    blocks: np.ndarray
    d1: np.ndarray
    d2: np.ndarray
    d3: np.ndarray
    starts: list[int]
    size: tuple[int, int]
    detail: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    stars: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))
    subject: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))
    clipped: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))
    banded: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))
    shimmer: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))
    still: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    detail_size: tuple[int, int] = (0, 0)

    @property
    def count(self) -> int:
        return len(self.luma)


def _blocks(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    bh, bw = h // BLOCK, w // BLOCK
    return gray[: bh * BLOCK, : bw * BLOCK].reshape(bh, BLOCK, bw, BLOCK).mean(axis=(1, 3))


def _shift_max(a: np.ndarray, r: int) -> np.ndarray:
    """The largest value within ``r`` pixels (a square), by shifted maxima."""
    out = a.copy()
    for d in range(1, r + 1):
        np.maximum(out[:, d:], a[:, :-d], out=out[:, d:])
        np.maximum(out[:, :-d], a[:, d:], out=out[:, :-d])
    rows = out.copy()
    for d in range(1, r + 1):
        np.maximum(out[d:], rows[:-d], out=out[d:])
        np.maximum(out[:-d], rows[d:], out=out[:-d])
    return out


def _shared_shift(y0: np.ndarray, x0: np.ndarray, v0: np.ndarray, y1: np.ndarray, x1: np.ndarray, v1: np.ndarray,
                  reach: int, keep: int = 300) -> tuple[int, int]:
    """The shift ``(dy, dx)`` from one frame's star peaks to the next's that most of the brightest
    stars share (a pan), within ``reach`` px; ``(0, 0)`` when no shift is shared by enough of them
    (stars standing still, or each moving its own way: a zoom, a warp)."""
    a, b = np.argsort(-v0)[:keep], np.argsort(-v1)[:keep]
    if len(a) < 8 or len(b) < 8:
        return (0, 0)
    dy = (y1[b][None, :] - y0[a][:, None]).ravel()
    dx = (x1[b][None, :] - x0[a][:, None]).ravel()
    m = (np.abs(dy) <= reach) & (np.abs(dx) <= reach)
    side = 2 * reach + 1
    hist = np.bincount((dy[m] + reach) * side + dx[m] + reach, minlength=side * side).reshape(side, side).astype(np.float32)
    votes = _box_sum(hist, 1)  # a shift of a fraction of a pixel falls into neighbouring bins
    iy, ix = np.unravel_index(int(np.argmax(votes)), votes.shape)
    if votes[iy, ix] < max(8.0, 0.2 * min(len(a), len(b))):
        return (0, 0)
    return (int(iy) - reach, int(ix) - reach)


def _box_sum(a: np.ndarray, r: int) -> np.ndarray:
    """The sum over each pixel's ``(2r + 1)`` square (zeros outside the picture)."""
    h, w = a.shape
    p = np.pad(a, r)
    cols = sum(p[k : k + h] for k in range(2 * r + 1))
    return sum(cols[:, k : k + w] for k in range(2 * r + 1))


def _banded(q: np.ndarray, ok: np.ndarray, run: int) -> float:
    """Share of the frame in flat steps along x: runs of at least ``run`` pixels between steps of
    1 or 2 codes inside ``ok``, where three steps in a row go the same way (a staircase; grain
    on a flat background goes up and down)."""
    d = np.diff(q, axis=1)
    r, c = np.nonzero((d != 0) & ok[:, 1:] & ok[:, :-1])
    if len(r) < 3:
        return 0.0
    step = d[r, c]
    small = np.abs(step) <= 2
    pair = (r[1:] == r[:-1]) & (np.sign(step[1:]) == np.sign(step[:-1])) & small[1:] & small[:-1]  # step j and j + 1 alike
    stair = pair & np.concatenate([[False], pair[:-1]])  # and step j - 1 too
    gap = c[1:] - c[:-1]
    return float(gap[stair & (gap >= run)].sum() / q.size)


class _DarkMeter:
    """The finer picture's numbers of dark frames, one frame after the other (a file at a time):
    star points, subject, clipped and banded shares, the stars' shimmer (of the frame before,
    once the next is known) and whether the frame is unchanged since its still stretch began."""

    def __init__(self, th: Thresholds) -> None:
        self.th = th
        self.reset()

    def reset(self) -> None:
        self.recent: deque[tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray, tuple[int, int], np.ndarray]] = deque(maxlen=2)
        self.anchor: np.ndarray | None = None
        self.points = np.zeros(0, bool)

    def frame(self, k: int, rgb: np.ndarray) -> tuple[dict[str, float], tuple[int, float] | None]:
        """The numbers of frame ``k`` and, when it can now be judged, ``(k - 1, shimmer)``."""
        th = self.th
        g = (rgb.astype(np.float32) / 255.0) @ _LUMA
        s3 = _box_sum(g, 1)
        ring = (_box_sum(g, 2) - s3) / 16
        peaks = (g >= _shift_max(g, 1)) & (g - ring >= th.star_contrast) & (ring <= th.star_ring * g)
        ys, xs = np.nonzero(peaks)
        near_star = _shift_max(peaks.view(np.uint8), 2).astype(bool)
        q = np.round(g * 255).astype(np.int16)
        ok = (q >= 3) & (q <= 90) & ~near_star
        values = {
            "stars": float(len(ys)),
            "subject": float(((g >= th.subject_level) & ~near_star).mean()),
            "clipped": float((g >= th.clip_level).mean()),
            # every other row (then column): the share is the same, the work half
            "banded": max(_banded(q[::2], ok[::2], th.band_run),
                          _banded(np.ascontiguousarray(q[:, ::2].T), np.ascontiguousarray(ok[:, ::2].T), th.band_run)),
        }
        if self.anchor is None or self.anchor.shape != g.shape:
            values["still"] = 0.0
            self.anchor = g
        else:
            values["still"] = float((np.abs(g - self.anchor) >= th.still_level).mean() < th.still_pixels)
            if not values["still"]:
                self.anchor = g
        near = _shift_max(s3, 4)  # each star's light, found again within 4 px in the frames around
        # point stars only: a streak's light runs on beyond 1 px (background: the ring from 3 to 4 px)
        s7, s9 = _box_sum(g, 3), _box_sum(g, 4)
        bg = (s9[ys, xs] - s7[ys, xs]) / 32
        point = (s3[ys, xs] - 9 * bg) >= th.shimmer_point * np.maximum(s7[ys, xs] - 49 * bg, 1e-6)
        light = g[ys, xs]
        shift = (0, 0)
        if self.recent and self.recent[-1][0] == k - 1:
            _, _, qy, qx, qv, _, _ = self.recent[-1]
            shift = _shared_shift(qy, qx, qv, ys, xs, light, th.shimmer_reach)
        judged = None
        if len(self.recent) == 2 and self.recent[0][0] == k - 2 and self.recent[1][0] == k - 1:
            (_, before, _, _, _, (ay, ax), seen_before), (_, here, py, px, _, _, _) = self.recent
            keep = self.points
            py, px = py[keep], px[keep]
            h, w = g.shape
            # the star a frame before and after, where the shared shift (a pan) has taken it
            inside = (py - ay >= 0) & (py - ay < h) & (px - ax >= 0) & (px - ax < w) & (py + shift[0] >= 0) & (py + shift[0] < h) & (px + shift[1] >= 0) & (px + shift[1] < w)
            py, px = py[inside], px[inside]
            if len(py) >= th.shimmer_stars:
                f = here[py, px]
                a, b = before[py - ay, px - ax], near[py + shift[0], px + shift[1]]
                gone = (a < 0.2 * f) & (b < 0.2 * f)
                # most stars found again within 4 px of where the shift takes them, and most of them as a
                # star within 2 px there (in a dense field of stars that each move their own way, a zoom or a
                # warp, the 4 px maximum would find another star's light)
                again = (seen_before[py - ay, px - ax] & near_star[py + shift[0], px + shift[1]]).mean()
                if gone.mean() < 0.5 and again >= 0.5:
                    # the median star: lines and glows passing over a few stars do not count
                    judged = (k - 1, float(np.median(np.minimum(np.abs(f - (a + b) / 2) / np.maximum(f, 1e-6), 1.0))))
        self.recent.append((k, near, ys, xs, light, shift, near_star))
        self.points = point
        return values, judged


def measure(frames_by_file: Sequence[Iterator[Any]], th: Thresholds | None = None) -> Features:
    """The :class:`Features` of the files' frames, one file after the other. A frame is an RGB
    array, or ``(frame, finer)`` from :func:`decode_frames` with ``detail``: then dark frames
    are measured in the finer picture too (``th``'s star, subject, clip and band settings)."""
    th = th or Thresholds()
    cols: dict[str, list[Any]] = {k: [] for k in ("luma", "spread", "rgb", "hist", "mad", "blocks", "d1", "d2", "d3")}
    dark: dict[str, list[float]] = {k: [] for k in ("detail", "stars", "subject", "clipped", "banded", "shimmer", "still")}
    meter = _DarkMeter(th)
    starts: list[int] = []
    size = (0, 0)
    detail_size = (0, 0)
    nan_blocks: np.ndarray | None = None
    for frames in frames_by_file:
        starts.append(len(cols["luma"]))
        recent: deque[np.ndarray] = deque(maxlen=3)
        meter.reset()
        for item in frames:
            rgb, finer = item if isinstance(item, tuple) else (item, None)
            f = rgb.astype(np.float32) / 255.0
            gray = f @ _LUMA
            size = (gray.shape[1], gray.shape[0])
            cols["luma"].append(float(gray.mean()))
            cols["spread"].append(float(gray.std()))
            cols["rgb"].append(f.reshape(-1, 3).mean(axis=0))
            cols["hist"].append(np.histogram(gray, bins=16, range=(0.0, 1.0))[0] / gray.size)
            cols["blocks"].append(_blocks(gray).astype(np.float16))
            if nan_blocks is None:
                nan_blocks = np.full(cols["blocks"][-1].shape, np.nan, dtype=np.float16)
            for k, name in ((1, "d1"), (2, "d2"), (3, "d3")):
                cols[name].append(_blocks(np.abs(gray - recent[-k])).astype(np.float16) if len(recent) >= k else nan_blocks)
            cols["mad"].append(float(np.abs(gray - recent[-1]).mean()) if recent else math.nan)
            recent.append(gray)
            for name in dark:
                dark[name].append(0.0 if name in ("detail", "still") else math.nan)
            if finer is not None and (gray < th.dark_level).mean() >= th.dark_share:
                k = len(cols["luma"]) - 1
                values, judged = meter.frame(k, finer)
                detail_size = (finer.shape[1], finer.shape[0])
                dark["detail"][k] = 1.0
                for name, value in values.items():
                    dark[name][k] = value
                if judged is not None:
                    dark["shimmer"][judged[0]] = judged[1]
            else:
                meter.reset()
    if not cols["luma"]:
        raise VidgenError("motion check: the video has no frames")
    arrays = {k: np.array(v, dtype=np.float16 if k in ("blocks", "d1", "d2", "d3") else np.float32) for k, v in cols.items()}
    flags = {k: np.array(v, dtype=bool if k in ("detail", "still") else np.float32) for k, v in dark.items()}
    return Features(starts=starts, size=size, detail_size=detail_size, **arrays, **flags)


# ----- the checks --------------------------------------------------------------------------------------


@dataclass
class Finding:
    """One fault: ``kind``, ``severity``, timeline frames ``frame`` to ``end`` (inclusive), the
    scene, a sentence and the value that tripped it; ``strip`` the contact strip once written."""

    kind: str
    severity: Severity
    frame: int
    end: int
    message: str
    value: float
    scene: str | None = None
    time: float = 0.0
    strip: Path | None = None
    box: tuple[float, float, float, float] | None = None
    """Where in the frame (shares ``x0, y0, x1, y1``), for a local finding."""

    def to_json(self, fps: float) -> dict[str, Any]:
        return {"kind": self.kind, "severity": self.severity, "frame": self.frame, "end_frame": self.end,
                "time": round(self.frame / fps, 3), "end_time": round((self.end + 1) / fps, 3), "scene": self.scene,
                "message": self.message, "value": round(self.value, 4), "strip": str(self.strip) if self.strip else None,
                "box": [round(v, 3) for v in self.box] if self.box else None}


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """``(first, last)`` of each run of True."""
    if not mask.any():
        return []
    padded = np.concatenate([[False], mask, [False]]).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [(int(a), int(b) - 1) for a, b in zip(edges[::2], edges[1::2])]


def _cuts(source: Source, feats: Features) -> list[int]:
    """Frames where a new shot starts: scene starts (and file starts) after frame 0."""
    cuts = {s.start for s in source.scenes} | set(feats.starts)
    return sorted(c for c in cuts if 0 < c < feats.count)


def _on_beat(frames: np.ndarray, hits: np.ndarray, th: Thresholds) -> np.ndarray:
    """For each frame, whether a music event falls ``0.5`` frame after to ``beat_frames`` before it."""
    if not len(hits) or not len(frames):
        return np.zeros(len(frames), dtype=bool)
    k = np.searchsorted(hits, frames + 0.5, side="right") - 1
    ok = k >= 0
    gap = np.where(ok, frames - hits[np.clip(k, 0, None)], np.inf)
    return ok & (gap <= th.beat_frames)


def _content(feats: Features, th: Thresholds) -> np.ndarray:
    """Dark frames whose finer picture shows a star field or a subject: not blank, however even
    they look at 160 px."""
    if len(feats.detail) != feats.count:
        return np.zeros(feats.count, bool)
    return feats.detail & ((np.nan_to_num(feats.stars) >= th.star_field) | (np.nan_to_num(feats.subject) >= th.subject_area))


def _picture(feats: Features, k: int, th: Thresholds) -> str | None:
    """What dark frame ``k`` shows clearly enough that losing it in one frame is abrupt: words, or ``None``."""
    if not (0 <= k < feats.count) or len(feats.detail) != feats.count or not feats.detail[k]:
        return None
    stars, subject = float(np.nan_to_num(feats.stars[k])), float(np.nan_to_num(feats.subject[k]))
    if subject >= th.vanish_area:
        return f"a subject over {subject:.1%} of the frame"
    if stars >= 4 * th.star_field:
        return f"a star field of {stars:.0f} points"
    return None


def check_blank(feats: Features, cuts: Sequence[int], th: Thresholds, fps: float) -> list[Finding]:
    n = feats.count
    out = []
    for a, b in _runs(_blank_mask(feats, th)):
        if a == 0 or b == n - 1:
            continue  # the video starts or ends on black
        entry = abs(float(feats.luma[a] - feats.luma[a - 1]))
        leave = abs(float(feats.luma[b + 1] - feats.luma[b]))
        mean = float(feats.luma[a : b + 1].mean())
        what = "black" if mean < 0.04 else "white" if mean > 0.9 else f"uniform (luma {mean:.2f})"
        count = b - a + 1
        at_cut = any(a - 1 <= c <= b + 2 for c in cuts)
        frames = f"{count} {what} frame{'s' if count > 1 else ''}"
        before, after = _picture(feats, a - 1, th), _picture(feats, b + 1, th)
        if max(entry, leave) >= th.blank_jump:
            how = f"entered by a step of {entry:.2f}, left by {leave:.2f}"
        elif before or after:  # a dark picture lost in one frame: the luma barely moves
            how = ", ".join(([f"entered from {before}"] if before else []) + ([f"left to {after}"] if after else []))
        else:
            how = ""
        if how:
            if at_cut:
                out.append(Finding("blank", "info", a, b, f"{frames} at a cut ({how})", max(entry, leave)))
            else:
                out.append(Finding("blank", "error", a, b, f"{frames} inside the scene ({how}): a frame failed to draw?", max(entry, leave)))
        elif count >= th.dark_seconds * fps:
            out.append(Finding("blank", "info", a, b, f"{frames} ({count / fps:.1f} s) reached by a fade", mean))
    return out + _check_vanish(feats, cuts, th, fps)


def _check_vanish(feats: Features, cuts: Sequence[int], th: Thresholds, fps: float) -> list[Finding]:
    """A subject over :attr:`Thresholds.vanish_area` of a dark frame gone in one frame and back
    within :attr:`Thresholds.vanish_seconds` while the stars stay: a part failed to draw (error)."""
    if len(feats.detail) != feats.count or not feats.detail.any():
        return []
    subject = np.nan_to_num(feats.subject)
    gone = feats.detail & (subject < th.subject_area) & ~_blank_mask(feats, th)
    out = []
    for a, b in _runs(gone):
        if a == 0 or b == feats.count - 1 or b - a + 1 > th.vanish_seconds * fps:
            continue
        if not (feats.detail[a - 1] and feats.detail[b + 1]) or min(subject[a - 1], subject[b + 1]) < th.vanish_area:
            continue
        if any(a - 1 <= c <= b + 2 for c in cuts):
            continue  # a cut to a shot of stars and back
        count = b - a + 1
        out.append(Finding("blank", "error", a, b, f"{count} frame{'s' if count > 1 else ''} of stars only inside the scene: a subject over "
                           f"{subject[a - 1]:.1%} of the frame vanished in one frame and came back: a part failed to draw?", float(subject[a - 1])))
    return out


def _blank_mask(feats: Features, th: Thresholds) -> np.ndarray:
    """Near-uniform frames at 160 px, star fields and dark frames with a subject left out."""
    return (feats.spread < th.blank_std) & ~_content(feats, th)


def check_flash(feats: Features, hits: np.ndarray, th: Thresholds) -> list[Finding]:
    y = feats.luma.astype(np.float64)
    n = len(y)
    blank = _blank_mask(feats, th)
    found: list[tuple[int, int, float]] = []
    t = 1
    while t < n - 1:
        step = y[t] - y[t - 1]
        if abs(step) >= th.flash and not blank[t]:
            for width in (1, 2):
                after = t + width
                if after >= n:
                    break
                inner = y[t : after]
                back = y[after] - y[t - 1]
                same_side = np.all(np.sign(inner - y[t - 1]) == np.sign(step)) and np.all(np.abs(inner - y[t - 1]) >= th.flash)
                if same_side and abs(back) <= th.flash_revert * abs(step):
                    found.append((t, after - 1, float(step)))
                    t = after
                    break
        t += 1
    out = []
    beat = _on_beat(np.array([f[0] for f in found], dtype=float), hits, th)
    for (a, b, step), on in zip(found, beat):
        word = "flash" if step > 0 else "drop-out"
        count = b - a + 1
        sev: Severity = "info" if on else "warning"
        tail = " on a hit or note of the score" if on else ""
        out.append(Finding("flash", sev, a, b, f"{count}-frame {word}{tail}: luma {y[a - 1]:.2f} -> {y[a]:.2f} -> {y[b + 1]:.2f}", abs(step)))
    return out


def _oscillating(series: np.ndarray, step: float, window: int, share: float) -> np.ndarray:
    """Frames inside a window where the series reverses direction with steps of at least ``step``
    on at least ``share`` of the frames; ``series`` is frames x channels, the result too."""
    d = np.diff(series, axis=0)
    d = np.nan_to_num(d)
    rev = (d[:-1] * d[1:] < 0) & (np.abs(d[:-1]) >= step) & (np.abs(d[1:]) >= step)
    rev = np.concatenate([np.zeros((1, *rev.shape[1:]), bool), rev, np.zeros((1, *rev.shape[1:]), bool)])  # at frame t: t-1 -> t -> t+1
    if len(rev) < window:
        return np.zeros_like(rev)
    csum = np.concatenate([np.zeros((1, *rev.shape[1:])), np.cumsum(rev, axis=0)])
    counts = csum[window:] - csum[:-window]  # window starting at k
    hot = counts >= share * window
    out = np.zeros_like(rev)
    for k in np.flatnonzero(hot.any(axis=tuple(range(1, hot.ndim))) if hot.ndim > 1 else hot):
        out[k : k + window] |= hot[k]
    return out & (rev | np.roll(rev, 1, axis=0) | np.roll(rev, -1, axis=0))


def _peaks(y: np.ndarray, a: int, b: int, step: float) -> np.ndarray:
    seg = y[max(a - 1, 0) : b + 2]
    d = np.diff(seg)
    idx = np.flatnonzero((d[:-1] >= step) & (d[1:] < 0)) + 1 + max(a - 1, 0)
    return idx.astype(float)


def check_flicker(feats: Features, cuts: Sequence[int], hits: np.ndarray, th: Thresholds) -> list[Finding]:
    y = feats.luma.astype(np.float64)
    whole = _oscillating(y[:, None], th.flicker, th.flicker_window, th.flicker_share)[:, 0]
    blocks = feats.blocks.reshape(feats.count, -1).astype(np.float64)
    local_hot = _oscillating(blocks, th.flicker_block, th.flicker_window, th.flicker_share)
    local = local_hot.sum(axis=1) >= th.flicker_blocks
    mask = whole | local
    for c in cuts:  # a cut is a step, not an oscillation
        mask[c] = mask[c] and (mask[c - 1] if c > 0 else False) and (mask[c + 1] if c + 1 < len(mask) else False)
    out = []
    for a, b in _runs(mask):
        if b - a + 1 < max(4, th.flicker_window // 2):
            continue
        if not whole[a : b + 1].any():
            hot = local_hot[a : b + 1].any(axis=0)
            region_step = np.abs(np.diff(blocks[a : b + 1][:, hot].mean(axis=1))).mean()
            block_step = np.abs(np.diff(blocks[a : b + 1][:, hot], axis=0)).mean()
            if region_step < 0.5 * block_step:
                continue  # blocks swap light and dark, the region's brightness stays: strobing (check_strobe)
        if whole[a : b + 1].any():
            region, series, step = "the whole frame", y, th.flicker
        else:
            k = int(np.argmax(np.abs(np.diff(blocks[a : b + 1], axis=0)).sum(axis=0)))  # the block that swings most
            region, series, step = f"{int(local_hot[a : b + 1].any(axis=0).sum())} blocks", blocks[:, k], th.flicker_block
        swing = float(np.abs(np.diff(series[a : b + 1])).mean())
        peaks = _peaks(series, a, b, step)
        on = _on_beat(peaks, hits, th)
        locked = len(peaks) >= 2 and on.mean() >= th.beat_share
        rate = len(peaks) / max((b - a + 1), 1)
        if locked:
            out.append(Finding("flicker", "info", a, b, f"beat-locked pulses in {region}: {len(peaks)} peaks, {on.sum()} on hits or notes of the score", swing))
        else:
            out.append(Finding("flicker", "warning", a, b, f"flicker in {region}: luma up and down every {1 / rate:.1f} frames"
                               f" ({swing:.3f} a frame)" if rate else f"flicker in {region}", swing))
    return out


def _dilate(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    out[1:, 1:] |= mask[:-1, :-1]
    out[:-1, :-1] |= mask[1:, 1:]
    out[1:, :-1] |= mask[:-1, 1:]
    out[:-1, 1:] |= mask[1:, :-1]
    return out


def _pop_at(feats: Features, t: int, th: Thresholds) -> tuple[int, np.ndarray] | None:
    """``(width, mask)`` of a pop starting at frame ``t`` (1 or 2 frames; ``mask`` its blocks),
    ``None`` if none."""
    n = feats.count
    d1 = feats.d1
    changed = np.nan_to_num(d1[t]) >= th.pop
    if not changed.any():
        return None
    for width in (1, 2):
        back = t + width
        if back >= n:
            return None
        far = feats.d2[back] if width == 1 else feats.d3[back]
        returned = np.nan_to_num(far, nan=np.inf) <= th.pop_revert * np.nan_to_num(d1[t])
        leaving = np.nan_to_num(d1[back]) >= 0.5 * th.pop
        held = True if width == 1 else bool(np.all(np.nan_to_num(d1[t + 1][changed], nan=np.inf) < 0.5 * d1[t][changed]))
        mask = changed & returned & leaving
        if not mask.any() or not held:
            continue
        if mask.mean() > th.pop_area:
            return None
        ring = _dilate(mask) & ~mask
        if ring.any():
            quiet = (np.nan_to_num(d1[t][ring], nan=np.inf) < th.pop_quiet) & (np.nan_to_num(d1[back][ring], nan=np.inf) < th.pop_quiet)
            if quiet.mean() < 0.75 or np.nan_to_num(d1[t][ring]).max() >= th.pop:
                continue  # its neighbours change too: something moving
        return width, mask
    return None


def _box(mask: np.ndarray) -> tuple[float, float, float, float]:
    """The blocks' bounding box as shares of the frame ``(x0, y0, x1, y1)``."""
    rows, cols = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    h, w = mask.shape
    return cols[0] / w, rows[0] / h, (cols[-1] + 1) / w, (rows[-1] + 1) / h


def check_pop(feats: Features, hits: np.ndarray, skip: np.ndarray, th: Thresholds, fps: float) -> list[Finding]:
    candidates = np.flatnonzero(np.nan_to_num(feats.d1.reshape(feats.count, -1)).max(axis=1) >= th.pop)
    pops: list[tuple[int, int, np.ndarray]] = []
    last = -10
    for t in candidates:
        t = int(t)
        if t <= last or skip[t]:
            continue
        found = _pop_at(feats, t, th)
        if found:
            pops.append((t, t + found[0] - 1, found[1]))
            last = t + found[0]
    out = []
    gap = max(1, round(th.group_seconds * fps))
    group: list[tuple[int, int, np.ndarray]] = []
    for pop in [*pops, None]:
        if group and (pop is None or pop[0] - group[-1][1] > gap):
            a, b = group[0][0], group[-1][1]
            on = _on_beat(np.array([g[0] for g in group], float), hits, th)
            most = max(int(g[2].sum()) for g in group)
            frames = "/".join(str(g[1] - g[0] + 1) for g in group[:6])
            words = f"{len(group)} pops" if len(group) > 1 else "a pop"
            small = most < th.pop_blocks
            sev: Severity = "info" if on.all() or small else "warning"
            tail = " on hits or notes of the score" if on.all() else " (small: a glint or spark?)" if small else ""
            union = np.logical_or.reduce([g[2] for g in group])
            out.append(Finding("pop", sev, a, b, f"{words}{tail}: up to {most} block{'s' if most > 1 else ''} appear for {frames} frame(s) and go",
                               float(most), box=_box(union)))
            group = []
        if pop is not None:
            group.append(pop)
    return out


def check_strobe(feats: Features, skip: np.ndarray, th: Thresholds, fps: float) -> list[Finding]:
    n = feats.count
    d1 = np.nan_to_num(feats.d1.reshape(n, -1).astype(np.float64))
    d2 = np.nan_to_num(feats.d2.reshape(n, -1).astype(np.float64), nan=np.inf)
    prev = np.vstack([np.zeros((1, d1.shape[1])), d1[:-1]])
    alt = (d1 >= th.strobe) & (prev >= th.strobe) & (d2 <= 0.5 * d1)
    frames = (alt.sum(axis=1) >= th.strobe_blocks) & ~skip
    window = max(2, round(fps))
    csum = np.concatenate([[0], np.cumsum(frames)])
    hot = np.zeros(n, bool)
    for k in np.flatnonzero(csum[window:] - csum[:-window] >= th.strobe_share * window):
        hot[k : k + window] |= frames[k : k + window]
    out = []
    for a, b in _runs(hot):
        if b - a + 1 < window // 2:
            continue
        most = int(alt[a : b + 1].sum(axis=1).max())
        out.append(Finding("strobe", "warning", a, b, f"strobing for {(b - a + 1) / fps:.1f} s: up to {most} blocks alternate between two pictures "
                           "frame by frame (something turning or moving about half its repeat a frame)", float(most),
                           box=_box((alt[a : b + 1].mean(axis=0) >= 0.3).reshape(feats.blocks.shape[1:]) | (alt[a : b + 1].sum(axis=0) == alt[a : b + 1].sum(axis=0).max()).reshape(feats.blocks.shape[1:]))))
    return out


def check_frozen(feats: Features, cuts: Sequence[int], th: Thresholds, fps: float) -> list[Finding]:
    still = np.nan_to_num(feats.mad, nan=np.inf) < th.frozen
    still &= ~_blank_mask(feats, th)
    if len(feats.detail) == feats.count:  # a dark frame's slow drift shows in the finer picture
        still &= ~feats.detail | feats.still
    for c in cuts:
        still[c] = False
    out = []
    for a, b in _runs(still):
        a -= 1  # the first frame of the stretch is the one the others repeat
        count = b - a + 1
        if count >= th.frozen_seconds * fps:
            out.append(Finding("frozen", "info", a, b, f"{count} frames without visible change ({count / fps:.1f} s)", float(count)))
    return out


def check_cuts(feats: Features, cuts: Sequence[int], th: Thresholds) -> list[Finding]:
    out = []
    blank = _blank_mask(feats, th)
    for c in cuts:
        if blank[c] or blank[c - 1]:
            continue  # a cut to or from a blank frame: check_blank reports it
        step = float(feats.luma[c] - feats.luma[c - 1])
        dist = float(np.abs(feats.hist[c] - feats.hist[c - 1]).sum())
        if abs(step) >= th.cut_luma or dist >= th.cut_hist:
            word = "brighter" if step > 0 else "darker"
            out.append(Finding("cut_jump", "info", c, c, f"cut {abs(step):.2f} {word} (luma {feats.luma[c - 1]:.2f} -> {feats.luma[c]:.2f}, "
                               f"histogram distance {dist:.2f})", max(abs(step), dist)))
    return out


def _stretches(mask: np.ndarray, fps: float, th: Thresholds, seconds: float, share: float = 1.0) -> list[tuple[int, int]]:
    """Runs of ``mask`` at least ``seconds`` long, merged when closer than
    :attr:`Thresholds.group_seconds`; with ``share`` under 1, first the frames of every second-long
    window where at least that share is set (as strobing is found)."""
    if share < 1:
        window = max(2, round(fps))
        csum = np.concatenate([[0], np.cumsum(mask)])
        hot = np.zeros(len(mask), bool)
        for k in np.flatnonzero(csum[window:] - csum[:-window] >= share * window):
            hot[k : k + window] |= mask[k : k + window]
        mask = hot
    gap = max(1, round(th.group_seconds * fps))
    merged: list[tuple[int, int]] = []
    for a, b in _runs(mask):
        if merged and a - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [(a, b) for a, b in merged if b - a + 1 >= max(1, seconds * fps)]


def check_dark(feats: Features, source: Source, th: Thresholds, subject_scenes: Sequence[str] = ()) -> list[Finding]:
    """The checks of dark pictures, in the finer picture: ``clipped``, ``shimmer``, ``banding``,
    ``empty`` and, in ``subject_scenes`` (scene ids, ``all`` for the whole video), ``lost``."""
    if len(feats.detail) != feats.count or not feats.detail.any():
        return []
    fps = source.fps
    detail = feats.detail
    out = []
    clipped = np.nan_to_num(feats.clipped)
    for a, b in _stretches(detail & (clipped >= th.clip_area), fps, th, 0):
        most = float(clipped[a : b + 1].max())
        out.append(Finding("clipped", "warning", a, b, f"over-exposed: up to {most:.1%} of a dark frame clipped to flat white for "
                           f"{(b - a + 1) / fps:.1f} s (a sun or planet burnt out? lower its light or the exposure)", most))
    shimmer = np.nan_to_num(feats.shimmer)
    for a, b in _stretches(shimmer >= th.shimmer, fps, th, 0.5, th.shimmer_share):
        part = feats.shimmer[a : b + 1]
        value = float(np.nanmean(part)) if np.isfinite(part).any() else 0.0
        out.append(Finding("shimmer", "warning", a, b, f"stars shimmer for {(b - a + 1) / fps:.1f} s: the median star's brightness jumps by {value:.0%} "
                           "from frame to frame (small point stars aliasing as they move; draw them soft and at least 2 px wide)", value))
    banded = np.nan_to_num(feats.banded)
    for a, b in _stretches(detail & (banded >= th.band_share), fps, th, th.band_seconds):
        most = float(banded[a : b + 1].max())
        out.append(Finding("banding", "info", a, b, f"up to {most:.0%} of the frame is a dark gradient in flat steps for "
                           f"{(b - a + 1) / fps:.1f} s (a glow or a limb; the encoder flattens dark gradients)", most))
    stars, subject = np.nan_to_num(feats.stars), np.nan_to_num(feats.subject)
    empty = detail & ~_blank_mask(feats, th) & (stars < th.star_field) & (subject < th.empty_area)
    for a, b in _stretches(empty, fps, th, th.empty_seconds):
        out.append(Finding("empty", "info", a, b, f"nearly empty for {(b - a + 1) / fps:.1f} s: no star field and at most "
                           f"{float(subject[a : b + 1].max()):.2%} of the frame lit", float(b - a + 1)))
    if subject_scenes:
        wanted = np.zeros(feats.count, bool)
        if "all" in subject_scenes:
            wanted[:] = True
        for scene in source.scenes:
            if scene.id in subject_scenes:
                wanted[scene.start : scene.end] = True
        for a, b in _stretches(wanted & detail & (subject < th.subject_area), fps, th, th.lost_seconds):
            points = float(np.median(stars[a : b + 1]))
            seen = f"only stars (about {points:.0f} points)" if points >= th.star_field else "black"
            out.append(Finding("lost", "warning", a, b, f"subject lost in the dark for {(b - a + 1) / fps:.1f} s: {seen}, nothing over "
                               f"{th.subject_area:.2%} of the frame lit", float(b - a + 1)))
    return out


def find_faults(feats: Features, source: Source, th: Thresholds, subject: Sequence[str] = ()) -> list[Finding]:
    """Every check's findings, with their scenes and times, most severe first, then by time;
    ``subject``: the scenes (ids, or ``all``) where a subject is expected (the ``lost`` check)."""
    fps = source.fps
    cuts = _cuts(source, feats)
    hits = np.sort(np.asarray(source.hits, dtype=float))
    found = check_blank(feats, cuts, th, fps) + check_flash(feats, hits, th)
    skip = _blank_mask(feats, th)
    for f in found:
        skip[max(0, f.frame - 1) : f.end + 3] = True
    flicker = check_flicker(feats, cuts, hits, th)
    for f in flicker:
        skip[f.frame : f.end + 1] = True
    cut_skip = skip.copy()
    for c in cuts:
        cut_skip[max(0, c - 2) : c + 3] = True
    strobe = check_strobe(feats, cut_skip, th, fps)
    for f in strobe:
        cut_skip[f.frame : f.end + 2] = True
    found += flicker + strobe + check_pop(feats, hits, cut_skip, th, fps)
    found += check_frozen(feats, cuts, th, fps) + check_cuts(feats, cuts, th) + check_dark(feats, source, th, subject)
    for f in found:
        f.time = f.frame / fps
        f.scene = next((s.id for s in source.scenes if s.start <= f.frame < s.end), None)
    found.sort(key=lambda f: (SEVERITIES.index(f.severity), f.frame))
    return found


# ----- contact strips ----------------------------------------------------------------------------------


def _strip_frames(f: Finding, count: int) -> list[int]:
    if f.end - f.frame <= 3:
        frames = list(range(f.frame - 2, f.end + 3))
    else:
        frames = [f.frame - 2, f.frame - 1, f.frame, f.frame + 1, f.end - 1, f.end, f.end + 1, f.end + 2]
    return [k for k in dict.fromkeys(frames) if 0 <= k < count]


def grab_frames(path: Path, fps: float, frames: Sequence[int], width: int, ffmpeg: str | None = None) -> dict[int, np.ndarray]:
    """Frames ``frames`` (file frame numbers) of ``path`` as RGB arrays ``width`` wide: one
    ffmpeg call seeking near the first and selecting by frame number from there."""
    from vidgen.render.ffmpeg import find_ffmpeg

    if not frames:
        return {}
    first, last = min(frames), max(frames)
    seek = max(0.0, first / fps - 1.0)
    skip = round(seek * fps)
    src_w, src_h, _ = probe(path)
    w, h = _decoded_size(src_w, src_h, width)
    command = [ffmpeg or find_ffmpeg(), "-v", "error", "-nostdin", "-ss", f"{seek:.6f}", "-i", str(path), "-map", "0:v:0",
               "-vf", f"select='between(n\\,{first - skip}\\,{last - skip})',scale={w}:{h}", "-fps_mode", "passthrough",
               "-frames:v", str(last - first + 1), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        raise VidgenError(f"ffmpeg could not read frames of {path}: {result.stderr.decode('utf-8', 'replace').strip()[-400:]}")
    size = w * h * 3
    data = result.stdout
    got = {first + k: np.frombuffer(data[k * size : (k + 1) * size], np.uint8).reshape(h, w, 3) for k in range(len(data) // size)}
    return {k: got[k] for k in frames if k in got}


def write_strip(f: Finding, source: Source, count: int, out: Path, index: int, th: Thresholds) -> Path:
    """The contact strip of ``f``: the frames around it side by side, the finding's frames framed
    in red, each labelled with its frame and time."""
    from PIL import Image, ImageDraw

    from vidgen.sheets import load_font

    wanted = _strip_frames(f, count)
    images: dict[int, np.ndarray] = {}
    starts = [s.first for s in source.segments]
    crop = f.kind in CROP_KINDS  # stars vanish when the frame is scaled down: a crop of its middle at full size
    for k, seg in enumerate(source.segments):
        end = starts[k + 1] if k + 1 < len(starts) else count
        local = [t - seg.first for t in wanted if seg.first <= t < end]
        full = probe(seg.path)[0] if crop else th.strip_width
        for t, img in grab_frames(seg.path, source.fps, local, full).items():
            if crop and img.shape[1] > th.strip_width:
                h, w = img.shape[:2]
                ch = max(2, round(th.strip_width * h / w))
                y0, x0 = (h - ch) // 2, (w - th.strip_width) // 2
                img = img[y0 : y0 + ch, x0 : x0 + th.strip_width]
            images[t + seg.first] = img
    tiles = [(t, images[t]) for t in wanted if t in images]
    if not tiles:
        raise VidgenError(f"motion check: could not read the frames around frame {f.frame}")
    h, w = tiles[0][1].shape[:2]
    pad, label = 4, 30
    font = load_font(12)
    sheet = Image.new("RGB", (len(tiles) * (w + pad) + pad, h + label + 2 * pad + 18), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    title = f"{f.severity} {f.kind}{' (the middle of the frame at full size)' if crop else ''}: {f.message}"
    draw.text((pad, pad), title[:160], fill=(235, 235, 235), font=font)
    for k, (t, img) in enumerate(tiles):
        x, y = pad + k * (w + pad), pad + 18
        sheet.paste(Image.fromarray(np.ascontiguousarray(img)), (x, y))
        if f.frame <= t <= f.end:
            draw.rectangle((x - 2, y - 2, x + w + 1, y + h + 1), outline=(230, 40, 40), width=2)
        if f.box is not None and not crop:
            x0, y0, x1, y1 = f.box
            draw.rectangle((x + x0 * w - 1, y + y0 * h - 1, x + x1 * w, y + y1 * h), outline=(250, 210, 40), width=1)
        draw.text((x, y + h + 4), f"f {t}  {t / source.fps:.2f} s", fill=(200, 200, 200), font=font)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{index:02d}_{f.kind}_{f.time:07.2f}s.png"
    sheet.save(path)
    return path


# ----- the whole check ---------------------------------------------------------------------------------


@dataclass
class MotionReport:
    """The result: what was watched, its size, the findings and how long it took."""

    source: Source
    frames: int
    size: tuple[int, int]
    seconds: float
    thresholds: Thresholds
    findings: list[Finding]
    out: Path | None
    dark_frames: int = 0
    """Frames measured in the finer picture (dark ones)."""
    detail_size: tuple[int, int] = (0, 0)
    subject: tuple[str, ...] = ()

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for f in self.findings if f.severity == s) for s in SEVERITIES}

    def fails(self, fail_on: str) -> bool:
        if fail_on == "never":
            return False
        limit = SEVERITIES.index(fail_on)  # type: ignore[arg-type]
        return any(SEVERITIES.index(f.severity) <= limit for f in self.findings)


def run_check(source: Source, th: Thresholds, out: Path | None, subject: Sequence[str] = ()) -> MotionReport:
    """Decode ``source``, run the checks and write a contact strip per finding (the
    :attr:`Thresholds.max_strips` most severe) into ``out`` (none when ``None``); ``subject``:
    scene ids (or ``all``) where a subject is expected, :class:`VidgenError` for an unknown one."""
    known = [s.id for s in source.scenes]
    for name in subject:
        if name != "all" and name not in known:
            close = difflib.get_close_matches(name, known, n=1)
            hint = f" (did you mean '{close[0]}'?)" if close else ""
            choices = f"; scenes: {', '.join(known[:12])}{' ...' if len(known) > 12 else ''}" if known else "; this video has no scenes: use all"
            raise VidgenError(f"--subject {name}: no such scene{hint}{choices}")
    began = time.monotonic()
    feats = measure([decode_frames(seg.path, th.width, detail=th.detail_width) for seg in source.segments], th)
    starts = feats.starts
    source.segments = [dataclasses.replace(seg, first=first) for seg, first in zip(source.segments, starts)]
    if source.clips:
        ends = [*starts[1:], feats.count]
        source.scenes = [SceneSpan(s.id, a, b) for s, a, b in zip(source.scenes, starts, ends)]
    findings = find_faults(feats, source, th, subject)
    if out is not None:
        for old in out.glob("[0-9][0-9]_*s.png") if out.is_dir() else ():
            old.unlink()
        for k, f in enumerate(findings[: th.max_strips], start=1):
            f.strip = write_strip(f, source, feats.count, out, k, th)
    return MotionReport(source, feats.count, feats.size, time.monotonic() - began, th, findings, out,
                        int(feats.detail.sum()), feats.detail_size, tuple(subject))


def report_text(report: MotionReport) -> str:
    """The report in words: what was watched, one line per finding, the totals."""
    src = report.source
    fps = src.fps
    lines = [f"{src.label}: {report.frames} frames at {fps:g} fps ({report.frames / fps:.1f} s), watched at "
             f"{report.size[0]}x{report.size[1]} in {report.seconds:.1f} s"]
    lines.append(f"  scenes: {len(src.scenes)}" if src.scenes else "  scenes: unknown (a plain video file)")
    lines.append(f"  music events: {len(src.hits)} hits and notes of {src.hit_source}" if src.hit_source else "  music events: none (no score file plays)")
    if report.dark_frames:
        lines.append(f"  dark frames: {report.dark_frames}, measured at {report.detail_size[0]}x{report.detail_size[1]} too")
    lines += [f"  note: {n}" for n in src.notes]
    for f in report.findings:
        where = f" {f.scene}" if f.scene else ""
        lines.append(f"{f.severity:<7} {f.time:8.2f} s  frame {f.frame:>6}{where}  {f.kind}: {f.message}")
        if f.strip:
            lines.append(f"        strip: {f.strip}")
    c = report.counts()
    lines.append(f"{c['error']} error(s), {c['warning']} warning(s), {c['info']} info" if report.findings else "no findings")
    return "\n".join(lines)


def report_json(report: MotionReport) -> dict[str, Any]:
    """The report's fields for ``vidgen motion check --json``."""
    src = report.source
    return {
        "source": src.label, "files": [str(s.path) for s in src.segments], "fps": src.fps, "frames": report.frames,
        "duration": round(report.frames / src.fps, 3), "size": list(report.size), "seconds": round(report.seconds, 2),
        "scenes": [{"id": s.id, "start": round(s.start / src.fps, 3), "end": round(s.end / src.fps, 3)} for s in src.scenes],
        "hits": len(src.hits), "hit_source": src.hit_source, "notes": list(src.notes),
        "dark_frames": report.dark_frames, "detail_size": list(report.detail_size), "subject": list(report.subject),
        "counts": report.counts(), "findings": [f.to_json(src.fps) for f in report.findings],
        "out": str(report.out) if report.out else None, "thresholds": report.thresholds.to_json(),
    }


# ----- sources -----------------------------------------------------------------------------------------


def file_source(path: Path) -> Source:
    """A plain video file: no scenes, no music events."""
    if not path.is_file():
        raise VidgenError(f"{path}: no such file")
    _, _, fps = probe(path)
    return Source(str(path), [Segment(path)], fps)


def music_events(project: Any, starts: dict[str, float], ends: dict[str, float]) -> tuple[np.ndarray, str | None, list[str]]:
    """The video seconds of every drum hit and note start (melodic tracks, slurred notes too;
    not pads or chords) of the score files the project's ``music:`` cues play (with the cue's
    ``start``, ``section`` and loop), the scores' names, and notes on what could not be read.
    Scene themes (``score:``) are left out."""
    from vidgen.music import cue_scene_range
    from vidgen.music_pieces import cue_score, section_start
    from vidgen.studio import load_music_score
    from vidgen.studio.events import score_events, track_kind

    order = [s.id for s in project.config.scenes]
    times: list[float] = []
    names: list[str] = []
    notes: list[str] = []
    for cue in project.config.music_cues:
        try:
            path = cue_score(cue, project.root)
            if path is None:
                continue
            first, last = cue_scene_range(cue, order)
            if order[first] not in starts or order[last] not in ends:
                continue
            score = load_music_score(path)
            offset = float(cue.start) + section_start(cue, project.root)
        except (VidgenError, ValueError) as exc:
            notes.append(f"music cue {cue.source}: no music events ({exc})")
            continue
        events = score_events(score)
        song = np.array(sorted(e.time for t in score.tracks if track_kind(t) in ("drum", "note") for e in events[t.name]), dtype=float)
        begin, finish = starts[order[first]], ends[order[last]]
        if score.loop and score.seconds > 0:
            offset %= score.seconds
            passes = range(0, math.ceil((offset + finish - begin) / score.seconds) + 1)
            song = np.concatenate([song + k * score.seconds for k in passes]) if len(song) else song
        placed = begin + song - offset
        times += [float(t) for t in placed if begin - 1e-6 <= t < finish]
        names.append(path.stem)
    return np.array(sorted(times)), (", ".join(dict.fromkeys(names)) or None), notes


def project_source(project: Any, preview: bool, prefer: str = "auto") -> Source:
    """A project's rendered video (with its scenes from the render's ``timings.json``), or, when
    that is missing or ``prefer`` is ``scenes``, its rendered scene clips in order. Nothing is
    rendered: :class:`VidgenError` naming the command when neither exists."""
    import json

    from vidgen.render.worker import scene_timings_path, scene_video_path

    video = project.output_path(preview)
    timings_file = project.render_dir(preview) / "timings.json"
    quality = "draft" if project.draft else "preview" if preview else "final"
    flag = {"draft": " --draft", "preview": " --preview", "final": ""}[quality]
    notes: list[str] = []
    if prefer in ("auto", "video") and video.is_file():
        _, _, fps = probe(video)
        scenes: list[SceneSpan] = []
        starts: dict[str, float] = {}
        ends: dict[str, float] = {}
        if timings_file.is_file():
            data = json.loads(timings_file.read_text(encoding="utf-8"))
            if timings_file.stat().st_mtime + 1 < video.stat().st_mtime:
                notes.append(f"{timings_file.name} is older than the video: scene times may be off")
            for s in data.get("scenes", []):
                starts[s["id"]], ends[s["id"]] = float(s["start"]), float(s["start"]) + float(s["duration"])
                scenes.append(SceneSpan(s["id"], round(starts[s["id"]] * fps), round(ends[s["id"]] * fps)))
        else:
            notes.append("no timings.json beside the render: scenes unknown")
        hits, names, more = music_events(project, starts, ends) if starts else (np.zeros(0), None, [])
        return Source(str(video), [Segment(video)], fps, scenes, hits * fps, names, notes + more)
    if prefer == "video":
        raise VidgenError(f"{video}: not rendered yet (vidgen render {project.root}{flag}); or watch its scene clips: --source scenes")
    clips = [(spec.id, scene_video_path(project, preview, spec.id)) for spec in project.config.scenes]
    found = [(sid, path) for sid, path in clips if path.is_file()]
    if not found:
        raise VidgenError(f"{project.root}: nothing rendered at {quality} quality (no {video.name}, no scene clips in "
                          f"{project.render_dir(preview) / 'scenes'}); render it first (vidgen render {project.root}{flag}) or give a video file")
    missing = [sid for sid, path in clips if not path.is_file()]
    if missing:
        notes.append(f"{len(missing)} scene(s) not rendered, left out: {', '.join(missing[:8])}{' ...' if len(missing) > 8 else ''}")
    _, _, fps = probe(found[0][1])
    scenes, starts, ends = [], {}, {}
    t = 0.0
    frame = 0
    for sid, path in found:
        timing = scene_timings_path(project, preview, sid)
        duration = None
        if timing.is_file():
            duration = float(json.loads(timing.read_text(encoding="utf-8")).get("duration", 0)) or None
        if duration is None:
            import av

            with av.open(str(path)) as c:
                st = c.streams.video[0]
                duration = float(st.frames / fps) if st.frames else float(c.duration or 0) / 1e6
        count = round(duration * fps)
        scenes.append(SceneSpan(sid, frame, frame + count))
        starts[sid], ends[sid] = t, t + duration
        frame += count
        t += duration
    if not missing:
        hits, names, more = music_events(project, starts, ends)
    else:
        hits, names, more = np.zeros(0), None, ["music events left out: scenes are missing, the music's timing is unknown"]
    notes.append("scene clips, cut to cut (no transitions or overlays)")
    return Source(f"{project.root} (scene clips)", [Segment(p) for _, p in found], fps, scenes, hits * fps, names, notes + more, clips=True)
