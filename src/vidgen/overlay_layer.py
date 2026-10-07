"""Drawing overlays into a scene's frames (DESIGN.md §41).

:class:`OverlayLayer` sits between Manim's renderer and the frames it writes: it wraps
``renderer.add_frame`` (outside :class:`vidgen.capture.FrameCapture`, so stills, the layout dump
and the motion signal see the overlays) and composites every overlay onto each frame at that
frame's time in the video. Overlays are never in ``scene.mobjects``: the scene's camera moves
(``zoom``) and ``clear_all`` fades do not touch them, and they are drawn with a camera of their
own that always shows the whole frame.

A frozen wait reaches the renderer as one frame written N times; when the overlays change during
it (a lower third sliding in), the layer splits it into runs of frames with equal overlay
states. Each overlay is drawn once per state (twice, over black and over white, which gives
exact colours and alpha for both Cairo's vector drawing and Manim's image drawing) by a camera
cropped to its pixel box (a thin progress bar costs a thin strip, not a whole frame), and cached
as a premultiplied RGBA patch; compositing a frame blends the shown overlays' patches in order.

A push or wipe into the scene (DESIGN.md §50) moves the pictures, so overlays must not be in
them: :meth:`OverlayLayer.split_head` leaves the scene's first frames bare and writes the
overlays of those frames into a separate RGBA clip, which the join draws over the moving
pictures.
"""

from __future__ import annotations

import math
from collections.abc import Hashable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import av
import numpy as np

from vidgen.overlays import Overlay, build_overlays

if TYPE_CHECKING:
    from manim import Camera, Mobject

    from vidgen.scene import NarratedScene

#: Distinct states kept drawn per overlay (a lower third's slide is ~15 frames per edge).
CACHE_SIZE = 64
#: Pixels added around an overlay's box when it is drawn (antialiasing).
PAD = 3


@dataclass
class _Patch:
    """An overlay drawn in one state: premultiplied RGB and ``255 - alpha`` (uint16) inside
    ``box`` = (y0, y1, x0, x1) of the frame; ``None`` box when nothing is visible."""

    box: tuple[int, int, int, int] | None
    color: np.ndarray | None = None
    keep: np.ndarray | None = None


class RgbaClip:
    """A video of RGBA frames with straight alpha (QuickTime, PNG codec: lossless, small when
    mostly transparent), for ffmpeg's ``overlay`` filter.

    :meth:`close` appends one fully transparent frame: ``overlay`` stops drawing a clip at its
    last frame's time, so without it the last real frame would never be shown.
    """

    def __init__(self, path: Path, width: int, height: int, fps: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.width, self.height = width, height
        self.frames = 0
        self._box = av.open(str(path), "w", format="mov")
        self._stream = self._box.add_stream("png", rate=fps)
        self._stream.width, self._stream.height, self._stream.pix_fmt = width, height, "rgba"

    def write(self, rgba: np.ndarray, count: int = 1) -> None:
        """Append ``rgba`` (H x W x 4, uint8, straight alpha) ``count`` times."""
        for _ in range(count):
            for packet in self._stream.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(rgba), format="rgba")):
                self._box.mux(packet)
        self.frames += count

    def close(self) -> None:
        """Write the transparent end frame and finish the file."""
        blank = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        for packet in self._stream.encode(av.VideoFrame.from_ndarray(blank, format="rgba")):
            self._box.mux(packet)
        for packet in self._stream.encode():
            self._box.mux(packet)
        self._box.close()


class OverlayLayer:
    """The overlays of one scene render, composited into every frame its renderer writes.

    ``following`` (with ``start`` and ``cut``, video seconds): when a crossfade overlaps the
    scene's end with the next scene's start (DESIGN.md §49), the next scene's overlays, drawn
    instead of the scene's own from ``cut`` (the next scene's start) on. Both scenes then show the
    same overlays in every frame they share, so blending them leaves the overlays unchanged.
    Without ``following`` (a push or wipe out of the scene, DESIGN.md §50) nothing is drawn from
    ``cut`` on: the next scene's render provides those frames' overlays (:meth:`split_head`).
    ``overlays`` / ``mobjects`` are the scene's own (what it reserves room for and avoids).
    """

    def __init__(
        self,
        scene: NarratedScene,
        overlays: list[Overlay],
        following: list[Overlay] | None = None,
        start: float | None = None,
        cut: float = math.inf,
    ) -> None:
        from manim import config

        self.scene = scene
        self.overlays = overlays
        self.mobjects: list[Mobject | None] = build_overlays(overlays)
        self.following = following or []
        self.following_mobjects: list[Mobject | None] = build_overlays(self.following)
        self.cut = cut
        self.fps = int(config.frame_rate)
        self.written = 0
        self._offset = start
        self._intervals = [o.interval() for o in self._all]
        self._cache: dict[tuple[int, Hashable], _Patch] = {}
        self._camera: Camera | None = None
        #: Frames at the scene's start written without overlays, their overlays going to
        #: ``head_path`` instead (:meth:`split_head`).
        self.head = 0
        self.head_path: Path | None = None
        self._clip: RgbaClip | None = None

    @property
    def _all(self) -> list[Overlay]:
        """The scene's own overlays, then the following ones."""
        return [*self.overlays, *self.following]

    @property
    def _all_mobjects(self) -> list[Mobject | None]:
        return [*self.mobjects, *self.following_mobjects]

    # ----- time ---------------------------------------------------------------------------------

    @property
    def offset(self) -> float:
        """Where the scene starts in the video (planned), read when first needed."""
        if self._offset is None:
            timed = any(o.timed for o in self.overlays)
            self._offset = self.overlays[0].context.scene.start if timed and self.overlays else 0.0
        return self._offset

    def video_time(self, frame: int) -> float:
        """The video time of the scene's frame ``frame`` (0-based)."""
        return self.offset + frame / self.fps

    def states(self, frame: int) -> tuple[Hashable | None, ...]:
        """Every overlay's state at the scene's frame ``frame`` (``None``: not shown): the scene's
        own, then the ``following`` ones (each set only on its side of the cut)."""
        t = self.video_time(frame)
        after = t >= self.cut - 1e-9
        own = len(self.overlays)
        out: list[Hashable | None] = []
        for k, (overlay, mob, (start, end)) in enumerate(zip(self._all, self._all_mobjects, self._intervals)):
            shown = mob is not None and start <= t + 1e-9 and t < end - 1e-9 and (k >= own) == after
            out.append(overlay.state(t) if shown else None)
        return tuple(out)

    def posed(self, frame: int) -> list[tuple[Overlay, Mobject, bool]]:
        """The overlays shown at the scene's frame ``frame``: each with its mobject as drawn then
        and whether it is settled (not in a transition)."""
        out = []
        for overlay, mob, state in zip(self._all, self._all_mobjects, self.states(frame)):
            if mob is not None and state is not None:
                out.append((overlay, overlay.pose(mob, state), overlay.settled(state)))
        return out

    # ----- drawing -----------------------------------------------------------------------------

    @property
    def camera(self) -> Camera:
        """A camera showing the whole frame (what overlays are measured with)."""
        if self._camera is None:
            from manim import Camera

            self._camera = Camera()
        return self._camera

    def _pixel_box(self, mobject: Mobject) -> tuple[int, int, int, int] | None:
        """The frame pixels (y0, y1, x0, x1) ``mobject`` may touch: its points' box, its strokes
        and :data:`PAD`, inside the frame; ``None`` when that is empty."""
        from manim import VMobject, config

        family = [m for m in mobject.get_family() if len(m.points)]
        if not family:
            return None
        points = np.concatenate([m.points for m in family])
        width, height = int(config.pixel_width), int(config.pixel_height)
        sx, sy = width / config.frame_width, height / config.frame_height
        stroke = max((float(m.get_stroke_width()) for m in family if isinstance(m, VMobject)), default=0.0)
        pad = PAD + int(np.ceil(stroke * 0.01 * max(sx, sy) / 2))
        x0 = max(int(np.floor(width / 2 + points[:, 0].min() * sx)) - pad, 0)
        x1 = min(int(np.ceil(width / 2 + points[:, 0].max() * sx)) + pad, width)
        y0 = max(int(np.floor(height / 2 - points[:, 1].max() * sy)) - pad, 0)
        y1 = min(int(np.ceil(height / 2 - points[:, 1].min() * sy)) + pad, height)
        return (y0, y1, x0, x1) if x1 > x0 and y1 > y0 else None

    def _draw(self, mobject: Mobject) -> _Patch:
        """``mobject`` drawn by two cameras (over black, over white) cropped to its pixel box."""
        from manim import Camera, config

        box = self._pixel_box(mobject)
        if box is None:
            return _Patch(None)
        y0, y1, x0, x1 = box
        width, height = int(config.pixel_width), int(config.pixel_height)
        sx, sy = width / config.frame_width, height / config.frame_height
        pw, ph = x1 - x0, y1 - y0
        center = np.array([(x0 + pw / 2 - width / 2) / sx, (height / 2 - y0 - ph / 2) / sy, 0.0])
        drawn = []
        for background in ("#000000", "#FFFFFF"):
            camera = Camera(
                background_color=background, pixel_width=pw, pixel_height=ph, frame_width=pw / sx, frame_height=ph / sy, frame_center=center
            )
            camera.capture_mobjects([mobject])
            drawn.append(np.asarray(camera.pixel_array[:, :, :3], dtype=np.int16))
        on_black, on_white = drawn
        # over black: colour x alpha; over white: that + (255 - alpha)
        keep = np.clip(np.mean(on_white - on_black, axis=2), 0, 255)
        visible = keep < 255
        if not visible.any():
            return _Patch(None)
        rows, cols = np.nonzero(visible.any(axis=1))[0], np.nonzero(visible.any(axis=0))[0]
        r0, r1, c0, c1 = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
        return _Patch(
            (y0 + r0, y0 + r1, x0 + c0, x0 + c1),
            np.clip(on_black[r0:r1, c0:c1], 0, 255).astype(np.uint16),
            np.rint(keep[r0:r1, c0:c1]).astype(np.uint16)[:, :, None],
        )

    def _patch(self, k: int, state: Hashable) -> _Patch:
        """Overlay ``k`` drawn in ``state`` (cached)."""
        key = (k, state)
        patch = self._cache.get(key)
        if patch is None:
            mobject = self._all_mobjects[k]
            assert mobject is not None
            patch = self._draw(self._all[k].pose(mobject, state))
            if len(self._cache) >= CACHE_SIZE * len(self._all):
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = patch
        return patch

    def composite(self, frame: np.ndarray, states: tuple[Hashable | None, ...]) -> np.ndarray:
        """``frame`` (H x W x 4 RGBA) with the overlays drawn in ``states`` on top, in order (a
        copy; the frame itself is returned when nothing is shown)."""
        out = frame
        for k, state in enumerate(states):
            if state is None or self._all_mobjects[k] is None:
                continue
            patch = self._patch(k, state)
            if patch.box is None:
                continue
            if out is frame:
                out = np.array(frame, copy=True)
            y0, y1, x0, x1 = patch.box
            under = out[y0:y1, x0:x1, :3].astype(np.uint16)
            out[y0:y1, x0:x1, :3] = (patch.color + (under * patch.keep + 127) // 255).clip(0, 255).astype(np.uint8)
        return out

    def rgba(self, states: tuple[Hashable | None, ...], height: int, width: int) -> np.ndarray:
        """The overlays drawn in ``states`` alone, as an ``height`` x ``width`` RGBA image with
        straight alpha (transparent where none is drawn): composited over any picture it gives
        what :meth:`composite` gives over that picture (up to rounding)."""
        color = np.zeros((height, width, 3), dtype=np.float32)  # premultiplied
        keep = np.full((height, width, 1), 255.0, dtype=np.float32)  # 255 - alpha
        for k, state in enumerate(states):
            if state is None or self._all_mobjects[k] is None:
                continue
            patch = self._patch(k, state)
            if patch.box is None:
                continue
            y0, y1, x0, x1 = patch.box
            assert patch.color is not None and patch.keep is not None
            factor = patch.keep.astype(np.float32) / 255.0
            color[y0:y1, x0:x1] = patch.color + color[y0:y1, x0:x1] * factor
            keep[y0:y1, x0:x1] = keep[y0:y1, x0:x1] * factor
        alpha = 255.0 - keep
        out = np.zeros((height, width, 4), dtype=np.uint8)
        shown = alpha[:, :, 0] > 0
        out[shown, :3] = np.clip(np.rint(color[shown] * 255.0 / alpha[shown]), 0, 255).astype(np.uint8)
        out[:, :, 3] = np.clip(np.rint(alpha[:, :, 0]), 0, 255).astype(np.uint8)
        return out

    # ----- a push / wipe into the scene (DESIGN.md §50) ----------------------------------------

    def split_head(self, frames: int, path: Path) -> None:
        """Write the scene's first ``frames`` frames without overlays and those frames' overlays
        to the RGBA clip ``path`` (one frame each, plus a transparent end frame)."""
        self.head = max(0, frames)
        self.head_path = path

    def _write_head(self, first: int, count: int, height: int, width: int) -> None:
        if self.head_path is None:
            return
        if self._clip is None:
            self._clip = RgbaClip(self.head_path, width, height, self.fps)
        run_start, run_states = first, self.states(first)
        for k in range(first + 1, first + count + 1):
            states = self.states(k) if k < first + count else None
            if states != run_states:
                self._clip.write(self.rgba(run_states, height, width), k - run_start)
                run_start, run_states = k, states  # type: ignore[assignment]

    def close_head(self) -> None:
        """Finish the head clip (when the scene ended before the head did; idempotent)."""
        if self._clip is not None:
            self._clip.close()
            self._clip = None

    # ----- renderer hook -----------------------------------------------------------------------

    def attach(self) -> None:
        """Composite the overlays into every frame the scene's renderer writes (call after any
        other ``add_frame`` wrapper, e.g. the frame capture, so they see the result)."""
        renderer = self.scene.renderer
        original = renderer.add_frame

        def add_frame(frame: Any, num_frames: int = 1) -> None:
            if getattr(renderer, "skip_animations", False) or num_frames <= 0:
                original(frame, num_frames)
                return
            if self.written < self.head and self.head_path is not None:  # bare, overlays to the clip
                bare = min(num_frames, self.head - self.written)
                self._write_head(self.written, bare, frame.shape[0], frame.shape[1])
                original(frame, bare)
                self.written += bare
                num_frames -= bare
                if self.written >= self.head:
                    self.close_head()
                if num_frames <= 0:
                    return
            start = self.written
            run_start, run_states = 0, self.states(start)
            for k in range(1, num_frames + 1):
                states = self.states(start + k) if k < num_frames else None
                if states != run_states:
                    original(self.composite(frame, run_states), k - run_start)
                    run_start, run_states = k, states  # type: ignore[assignment]
            self.written = start + num_frames

        renderer.add_frame = add_frame
