"""Checks of a generated clip before it goes into the film, and its contact sheet (DESIGN.md
§113.4). Nothing here pays or sends anything.

:func:`check_clip` decodes the clip small (64 px wide, grey, at its own frame rate up to 30 fps)
and reports:

- **duration**: shorter than the shot (its last frame would hold) is a warning;
- **size**: an aspect ratio other than the video's (``cover`` cuts part of the picture off) and a
  picture much smaller than the video (scaled up) are warnings;
- **black**: a black clip is an error, a black stretch of 0.5 s or more a warning;
- **frozen**: a still clip is an error, a stretch of 1 s or more without movement a warning;
- **flicker**: the mean jump of each frame's brightness against its neighbours' average
  (0-255 levels): over :data:`FLICKER_LIMIT` a warning;
- **cuts**: a frame-to-frame change far above the clip's usual one (a cut inside the clip, which
  the beat did not ask for) is a warning;
- **sound**: the clip's own sound is noted, with where it is heard (a shot with ``sound: mix`` never
  uses it; ``sound: model`` keeps it for a ``video_clip`` scene). ``sound: model`` with a silent
  clip is a warning.

:func:`contact_sheet` writes a PNG of evenly spaced frames with their times and the checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from vidgen.errors import VidgenError

#: Mean brightness (0-255) under which a frame counts as black (with its brightest parts dark too).
BLACK_MEAN, BLACK_PEAK = 16.0, 40.0
#: Mean absolute change between frames (0-255) under which a frame counts as frozen.
FROZEN_CHANGE = 0.6
#: Flicker metric (0-255 levels) over which a clip is reported.
FLICKER_LIMIT = 3.0
#: A change between two frames this many times the clip's median change (and at least
#: :data:`CUT_MIN`) is an abrupt cut.
CUT_FACTOR, CUT_MIN = 6.0, 30.0
#: Longest black / frozen stretches (seconds) that pass.
BLACK_RUN, FROZEN_RUN = 0.5, 1.0
#: Width (px) the clip is decoded at for the checks.
CHECK_WIDTH = 64

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class QACheck:
    """One finding: its check's ``name``, ``severity`` and message."""

    name: str
    severity: Severity
    message: str

    def to_json(self) -> dict[str, Any]:
        """The finding as JSON."""
        return {"check": self.name, "severity": self.severity, "message": self.message}


@dataclass
class QAReport:
    """What :func:`check_clip` found in one clip, with the measured ``metrics``."""

    path: Path
    width: int
    height: int
    fps: float
    duration: float
    audio: bool
    checks: list[QACheck] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def errors(self) -> list[QACheck]:
        """The findings that keep the take from being placed unless picked by hand."""
        return [c for c in self.checks if c.severity == "error"]

    @property
    def warnings(self) -> list[QACheck]:
        """The findings worth a look."""
        return [c for c in self.checks if c.severity == "warning"]

    def summary(self) -> str:
        """``ok`` or ``2 warnings, 1 error``."""
        e, w = len(self.errors), len(self.warnings)
        if not e and not w:
            return "QA ok"
        parts = ([f"{e} error{'s' * (e != 1)}"] if e else []) + ([f"{w} warning{'s' * (w != 1)}"] if w else [])
        return "QA " + ", ".join(parts)

    def lines(self) -> list[str]:
        """The report as text (a header, then one line per finding)."""
        m = self.metrics
        head = (
            f"{self.width}x{self.height}, {self.fps:g} fps, {self.duration:.2f} s; {self.summary()} "
            f"(flicker {m.get('flicker', 0):.1f}, longest frozen {m.get('frozen_run', 0):.1f} s, black {m.get('black_share', 0) * 100:.0f}%)"
        )
        return [head, *(f"  {c.severity}: {c.message}" for c in self.checks)]

    def to_json(self) -> dict[str, Any]:
        """The report as JSON."""
        return {
            "width": self.width, "height": self.height, "fps": self.fps, "duration": round(self.duration, 3), "audio": self.audio,
            "summary": self.summary(), "checks": [c.to_json() for c in self.checks],
            "metrics": {k: round(v, 3) for k, v in self.metrics.items()},
        }


def probe(path: Path) -> tuple[int, int, float, float, bool]:
    """``(width, height, fps, duration, has_sound)`` of a clip (PyAV; nothing decoded)."""
    import av

    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                raise VidgenError(f"{path.name} has no video stream")
            stream = container.streams.video[0]
            rate = stream.average_rate or stream.guessed_rate or 0
            fps = float(rate) if rate else 25.0
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                duration = container.duration / av.time_base
            else:
                duration = 0.0
            return stream.codec_context.width, stream.codec_context.height, fps, duration, bool(container.streams.audio)
    except av.error.FFmpegError as exc:
        raise VidgenError(f"cannot read video {path.name}: {exc}") from None
    except OSError as exc:
        raise VidgenError(f"cannot read video {path}: {exc}") from None


def _runs(mask: np.ndarray) -> int:
    """The longest run of ``True`` in ``mask``."""
    best = run = 0
    for value in mask:
        run = run + 1 if value else 0
        best = max(best, run)
    return best


def check_clip(path: Path, *, length: float, width: int, height: int, sound: str = "mix") -> QAReport:
    """Check the clip ``path`` meant for a shot of ``length`` seconds in a ``width`` x ``height``
    video, its ``sound`` setting being ``mix`` or ``model`` (see the module docstring)."""
    from vidgen.render.ffmpeg import decode_gray_frames

    w, h, fps, duration, audio = probe(path)
    report = QAReport(path, w, h, fps, duration, audio)
    checks = report.checks
    rate = min(fps, 30.0)
    frames = decode_gray_frames(path, CHECK_WIDTH, rate, duration + 1.0).astype(np.float32)
    if not len(frames):
        checks.append(QACheck("frames", "error", "no frames could be decoded"))
        return report
    duration = duration or len(frames) / rate
    report.duration = duration
    # duration
    if duration < length - 1.0 / fps:
        checks.append(QACheck("duration", "warning", f"{duration:.2f} s, shorter than the shot ({length:.2f} s): its last frame holds for {length - duration:.2f} s"))
    # size and aspect ratio
    want, have = width / height, w / h
    if abs(np.log(have / want)) > 0.02:
        kept = min(want / have, have / want)
        checks.append(QACheck("aspect", "warning", f"aspect ratio {have:.3f} (video {want:.3f}): cover cuts off {100 * (1 - kept):.0f}% of the picture"))
    scale = max(width / w, height / h)
    if scale > 2.0:
        checks.append(QACheck("size", "warning", f"{w}x{h} is scaled up {scale:.1f}x to fill the {width}x{height} frame (soft)"))
    # black
    means = frames.mean(axis=(1, 2))
    peaks = np.percentile(frames.reshape(len(frames), -1), 99, axis=1)
    black = (means < BLACK_MEAN) & (peaks < BLACK_PEAK)
    report.metrics["black_share"] = float(black.mean())
    black_run = _runs(black) / rate
    if black.all():
        checks.append(QACheck("black", "error", "the clip is black"))
    elif black_run >= BLACK_RUN:
        checks.append(QACheck("black", "warning", f"black for {black_run:.1f} s"))
    # frozen
    if len(frames) > 1:
        changes = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
        frozen = changes < FROZEN_CHANGE
        frozen_run = _runs(frozen) / rate
        report.metrics["frozen_run"] = frozen_run
        if frozen.all() and not black.all():
            checks.append(QACheck("frozen", "error", "the clip is a still picture: nothing moves"))
        elif frozen_run >= FROZEN_RUN and not black.all():
            checks.append(QACheck("frozen", "warning", f"nothing moves for {frozen_run:.1f} s"))
        # flicker: brightness jumping against its neighbours' average
        flicker = float(np.abs(means[1:-1] - (means[:-2] + means[2:]) / 2).mean()) if len(means) > 2 else 0.0
        report.metrics["flicker"] = flicker
        if flicker > FLICKER_LIMIT:
            checks.append(QACheck("flicker", "warning", f"the brightness flickers ({flicker:.1f} levels from frame to frame; limit {FLICKER_LIMIT:g})"))
        # abrupt cuts
        usual = float(np.median(changes))
        limit = max(CUT_MIN, CUT_FACTOR * usual)
        cuts = [(k + 1) / rate for k, c in enumerate(changes) if c > limit and not (black[k] or black[k + 1])]
        report.metrics["cuts"] = float(len(cuts))
        if cuts and flicker <= FLICKER_LIMIT:
            times = ", ".join(f"{t:.2f} s" for t in cuts[:5])
            checks.append(QACheck("cuts", "warning", f"abrupt change at {times} (a cut inside the clip?)"))
    if sound == "model" and not audio:
        checks.append(QACheck("sound", "warning", "sound: model, but the clip has no sound of its own"))
    elif sound == "model":
        checks.append(QACheck("sound", "info", "the clip has its own sound (sound: model): a video_clip scene plays it; a placed take plays vidgen's mix instead"))
    elif audio:
        checks.append(QACheck("sound", "info", "the clip has its own sound: never used (vidgen's mix is)"))
    return report


def contact_sheet(path: Path, out: Path, *, title: str = "", report: QAReport | None = None, count: int = 8, columns: int = 4, thumb: int = 200) -> Path:
    """A PNG of ``count`` evenly spaced frames of ``path`` (``columns`` across, ``thumb`` px
    on their long side) with their times, under ``title`` and the QA report's lines."""
    import av
    from PIL import Image, ImageDraw, ImageFont

    w, h, fps, duration, _ = probe(path)
    scale = thumb / max(w, h)
    tw, th = max(2, round(w * scale)), max(2, round(h * scale))
    times = [duration * (k + 0.5) / count for k in range(count)]
    shots: list[tuple[float, Any]] = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        wanted = iter(times)
        target = next(wanted, None)
        for frame in container.decode(stream):
            if target is None:
                break
            t = float(frame.time or 0.0)
            if t + 0.5 / fps >= target:
                shots.append((t, frame.to_image().resize((tw, th))))
                target = next(wanted, None)
    font = ImageFont.load_default()
    lines = ([title] if title else []) + (report.lines() if report is not None else [])
    header = 16 * len(lines) + 8
    rows = max(1, -(-len(shots) // columns))
    pad, label = 6, 14
    sheet = Image.new("RGB", (columns * (tw + pad) + pad, header + rows * (th + label + pad) + pad), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    for k, line in enumerate(lines):
        draw.text((pad, 4 + 16 * k), line, fill=(235, 235, 235), font=font)
    for k, (t, image) in enumerate(shots):
        x = pad + (k % columns) * (tw + pad)
        y = header + (k // columns) * (th + label + pad)
        sheet.paste(image, (x, y))
        draw.text((x, y + th + 1), f"{t:.2f} s", fill=(200, 200, 200), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


__all__ = ["QACheck", "QAReport", "check_clip", "contact_sheet"]
