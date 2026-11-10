"""Generated video takes laid into a scene's frames (DESIGN.md §113.4).

:class:`GeneratedLayer` wraps the scene renderer's ``add_frame`` inside the overlay layer
(:mod:`vidgen.overlay_layer`), so the overlays, captions and the frame capture see the take: for
every frame in a placement's window (scene seconds, :class:`vidgen.videogen.compose.Placement`)
the scene's own picture is replaced by the take's frame showing then:

- **scale / crop**: ``cover`` scales the take to fill the frame and cuts the overhang off
  (centred), ``contain`` shows all of it on black;
- **frame rate**: the take's frame showing at each render frame's time (decoded in order by
  :class:`vidgen.clips.ClipReader`); a take shorter than its window holds its last frame, a longer
  one is cut (the snapped length is trimmed);
- **light colour matching**: per-channel gains from the take's average colour (grey world) and
  exposure, at ``color_match`` strength, each gain within 0.8-1.25;
- **crossfades**: the take fades in from and out to the scene's picture over ``fade_in`` /
  ``fade_out`` seconds inside its window (the beat's timing stays exact);
- **sound**: never read (the film's mix is vidgen's).

A frozen wait (one frame written N times) is split into single frames inside windows only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from vidgen.clips import ClipReader
    from vidgen.scene import NarratedScene
    from vidgen.videogen.compose import Placement

#: Gains of the colour matching stay within these.
GAIN_RANGE = (0.8, 1.25)
#: Mean brightness (0-255) the exposure matching moves a take towards.
TARGET_LEVEL = 118.0
#: Frames sampled to measure a take's colour.
COLOR_SAMPLES = 8


def color_gains(samples: np.ndarray, strength: float) -> np.ndarray:
    """Per-channel gains (RGB) for pixels ``samples`` (..., 3): the grey-world balance times an
    exposure gain towards :data:`TARGET_LEVEL`, both raised to ``strength`` (0: none)."""
    if strength <= 0:
        return np.ones(3, dtype=np.float32)
    means = samples.reshape(-1, 3).astype(np.float64).mean(axis=0)
    level = float(means.mean())
    if level < 1.0:
        return np.ones(3, dtype=np.float32)
    balance = level / np.maximum(means, 1.0)
    exposure = TARGET_LEVEL / level
    gains = (balance * exposure) ** strength
    return np.clip(gains, *GAIN_RANGE).astype(np.float32)


class _Take:
    """A placement with its frame window (render frames) and, once needed, its reader."""

    def __init__(self, placement: Placement, fps: int) -> None:
        self.placement = placement
        self.first = round(placement.start * fps)
        self.end = max(self.first + 1, round((placement.start + placement.length) * fps))
        self.reader: ClipReader | None = None
        self.box: tuple[int, int, int, int] = (0, 0, 0, 0)   # x0, y0, w, h in the frame
        self.gains = np.ones(3, dtype=np.float32)

    def open(self, width: int, height: int) -> None:
        from vidgen.clips import ClipReader, probe_clip

        p = self.placement
        info = probe_clip(p.take)
        clip_aspect, frame_aspect = info.width / info.height, width / height
        if p.fit == "contain":
            w, h = (width, max(1, round(width / clip_aspect))) if clip_aspect >= frame_aspect else (max(1, round(height * clip_aspect)), height)
            self.box = ((width - w) // 2, (height - h) // 2, w, h)
            self.reader = ClipReader(p.take, (w, h))
        else:
            if clip_aspect > frame_aspect:
                cw = frame_aspect / clip_aspect
                crop = ((1 - cw) / 2, 0.0, cw, 1.0)
            else:
                ch = clip_aspect / frame_aspect
                crop = (0.0, (1 - ch) / 2, 1.0, ch)
            self.box = (0, 0, width, height)
            self.reader = ClipReader(p.take, (width, height), crop)
        if p.color_match > 0:
            probe = ClipReader(p.take, (32, max(1, round(32 / clip_aspect))))
            try:
                samples = np.stack([probe.frame(info.duration * (k + 0.5) / COLOR_SAMPLES)[:, :, :3] for k in range(COLOR_SAMPLES)])
            finally:
                probe.close()
            self.gains = color_gains(samples, p.color_match)

    def alpha(self, frame: int, fps: int) -> float:
        """How much of the take shows at render frame ``frame`` (the fades at its edges)."""
        p = self.placement
        a = 1.0
        if p.fade_in > 0:
            a = min(a, (frame - self.first + 0.5) / fps / p.fade_in)
        if p.fade_out > 0:
            a = min(a, (self.end - frame - 0.5) / fps / p.fade_out)
        return float(max(0.0, a))

    def picture(self, base: np.ndarray, frame: int, fps: int) -> np.ndarray:
        """``base`` (H x W x 4) with the take's frame at render frame ``frame`` laid in."""
        height, width = base.shape[0], base.shape[1]
        if self.reader is None:
            self.open(width, height)
        assert self.reader is not None
        pixels = self.reader.frame((frame - self.first) / fps)[:, :, :3].astype(np.float32)
        if not np.allclose(self.gains, 1.0):
            pixels = pixels * self.gains
        x0, y0, w, h = self.box
        layer = np.zeros((height, width, 3), dtype=np.float32)
        layer[y0:y0 + h, x0:x0 + w] = pixels
        a = self.alpha(frame, fps)
        out = np.array(base, copy=True)
        mixed = layer if a >= 1.0 else base[:, :, :3].astype(np.float32) * (1 - a) + layer * a
        out[:, :, :3] = np.clip(np.rint(mixed), 0, 255).astype(np.uint8)
        out[:, :, 3] = 255
        return out

    def close(self) -> None:
        if self.reader is not None:
            self.reader.close()
            self.reader = None


class GeneratedLayer:
    """The takes shown in one scene render (see the module docstring)."""

    def __init__(self, scene: NarratedScene, placements: list[Placement]) -> None:
        from manim import config

        self.scene = scene
        self.placements = placements
        self.fps = int(config.frame_rate)
        self.takes = [_Take(p, self.fps) for p in placements]
        self.written = 0

    def _at(self, frame: int) -> _Take | None:
        return next((t for t in self.takes if t.first <= frame < t.end), None)

    def _next_start(self, frame: int) -> int | None:
        starts = [t.first for t in self.takes if t.first > frame]
        return min(starts) if starts else None

    def attach(self) -> None:
        """Lay the takes into the frames the renderer writes (call right after the overlay
        layer's ``attach``, so the overlays are drawn over the takes)."""
        renderer = self.scene.renderer
        original = renderer.add_frame

        def add_frame(frame: Any, num_frames: int = 1) -> None:
            if getattr(renderer, "skip_animations", False) or num_frames <= 0:
                original(frame, num_frames)
                return
            start, k = self.written, 0
            while k < num_frames:
                index = start + k
                take = self._at(index)
                if take is None:
                    nxt = self._next_start(index)
                    run = num_frames - k if nxt is None else min(num_frames - k, nxt - index)
                    original(frame, run)
                    k += run
                else:
                    original(take.picture(frame, index, self.fps), 1)
                    k += 1
            self.written = start + num_frames

        renderer.add_frame = add_frame

    def close(self) -> None:
        """Release the take files."""
        for take in self.takes:
            take.close()

    def to_json(self) -> list[dict[str, Any]]:
        """The placements as the scene's timings record them."""
        return [
            {"shot": p.shot, "take": p.number, "model": p.model, "start": round(p.start, 6), "length": round(p.length, 6)}
            for p in self.placements
        ]


__all__ = ["GeneratedLayer", "color_gains"]
