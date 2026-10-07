"""Drawing overlays into a scene's frames (DESIGN.md §41).

:class:`OverlayLayer` sits between Manim's renderer and the frames it writes: it wraps
``renderer.add_frame`` (outside :class:`vidgen.capture.FrameCapture`, so stills, the layout dump
and the motion signal see the overlays) and composites every overlay onto each frame at that
frame's time in the video. Overlays are never in ``scene.mobjects``: the scene's camera moves
(``zoom``) and ``clear_all`` fades do not touch them, and they are drawn with a camera of their
own that always shows the whole frame.

A frozen wait reaches the renderer as one frame written N times; when the overlays change during
it (a lower third sliding in), the layer splits it into runs of frames with equal overlay
states. Each combination of states is drawn once (twice, over black and over white, which gives
exact colours and alpha for both Cairo's vector drawing and Manim's image drawing) and cached as
a premultiplied RGBA patch; compositing a frame is then a numpy blend of that patch's box.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.overlays import Overlay

if TYPE_CHECKING:
    from manim import Camera, Mobject

    from vidgen.scene import NarratedScene

#: Distinct state combinations kept drawn (a lower third's slide is ~15 frames per edge).
CACHE_SIZE = 64


@dataclass
class _Patch:
    """Overlays drawn for one combination of states: premultiplied RGB and ``255 - alpha``
    (uint16) inside ``box`` = (y0, y1, x0, x1); ``None`` box when nothing is visible."""

    box: tuple[int, int, int, int] | None
    color: np.ndarray | None = None
    keep: np.ndarray | None = None


class OverlayLayer:
    """The overlays of one scene render, composited into every frame its renderer writes."""

    def __init__(self, scene: NarratedScene, overlays: list[Overlay]) -> None:
        from manim import config

        self.scene = scene
        self.overlays = overlays
        self.mobjects: list[Mobject | None] = [overlay.build() for overlay in overlays]
        self.fps = int(config.frame_rate)
        self.written = 0
        self._offset: float | None = None
        self._intervals = [o.interval() for o in overlays]
        self._cache: dict[tuple[Hashable | None, ...], _Patch] = {}
        self._cameras: tuple[Camera, Camera] | None = None

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
        """Every overlay's state at the scene's frame ``frame`` (``None``: not shown)."""
        t = self.video_time(frame)
        out: list[Hashable | None] = []
        for overlay, mob, (start, end) in zip(self.overlays, self.mobjects, self._intervals):
            out.append(overlay.state(t) if mob is not None and start <= t + 1e-9 and t < end - 1e-9 else None)
        return tuple(out)

    def posed(self, frame: int) -> list[tuple[Overlay, Mobject, bool]]:
        """The overlays shown at the scene's frame ``frame``: each with its mobject as drawn then
        and whether it is settled (not in a transition)."""
        out = []
        for overlay, mob, state in zip(self.overlays, self.mobjects, self.states(frame)):
            if mob is not None and state is not None:
                out.append((overlay, overlay.pose(mob, state), overlay.settled(state)))
        return out

    # ----- drawing -----------------------------------------------------------------------------

    @property
    def camera(self) -> Camera:
        """A camera showing the whole frame (what overlays are drawn and measured with)."""
        return self._camera_pair()[0]

    def _camera_pair(self) -> tuple[Camera, Camera]:
        if self._cameras is None:
            from manim import Camera

            self._cameras = (Camera(background_color="#000000"), Camera(background_color="#FFFFFF"))
        return self._cameras

    def _patch(self, states: tuple[Hashable | None, ...]) -> _Patch:
        patch = self._cache.get(states)
        if patch is not None:
            return patch
        mobs = [overlay.pose(mob, state) for overlay, mob, state in zip(self.overlays, self.mobjects, states) if mob is not None and state is not None]
        black, white = self._camera_pair()
        drawn = []
        for camera in (black, white):
            camera.reset()
            if mobs:
                camera.capture_mobjects(mobs)
            drawn.append(np.asarray(camera.pixel_array[:, :, :3], dtype=np.int16))
        on_black, on_white = drawn
        # over black: colour x alpha; over white: that + (255 - alpha)
        keep = np.clip(np.mean(on_white - on_black, axis=2), 0, 255)
        visible = keep < 255
        if not visible.any():
            patch = _Patch(None)
        else:
            rows, cols = np.nonzero(visible.any(axis=1))[0], np.nonzero(visible.any(axis=0))[0]
            y0, y1, x0, x1 = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
            patch = _Patch(
                (y0, y1, x0, x1),
                np.clip(on_black[y0:y1, x0:x1], 0, 255).astype(np.uint16),
                np.rint(keep[y0:y1, x0:x1]).astype(np.uint16)[:, :, None],
            )
        if len(self._cache) >= CACHE_SIZE:
            self._cache.pop(next(iter(self._cache)))
        self._cache[states] = patch
        return patch

    def composite(self, frame: np.ndarray, states: tuple[Hashable | None, ...]) -> np.ndarray:
        """``frame`` (H x W x 4 RGBA) with the overlays drawn in ``states`` on top (a copy; the
        frame itself is returned when nothing is shown)."""
        if all(s is None for s in states):
            return frame
        patch = self._patch(states)
        if patch.box is None:
            return frame
        y0, y1, x0, x1 = patch.box
        out = np.array(frame, copy=True)
        under = out[y0:y1, x0:x1, :3].astype(np.uint16)
        out[y0:y1, x0:x1, :3] = (patch.color + (under * patch.keep + 127) // 255).clip(0, 255).astype(np.uint8)
        return out

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
            start = self.written
            run_start, run_states = 0, self.states(start)
            for k in range(1, num_frames + 1):
                states = self.states(start + k) if k < num_frames else None
                if states != run_states:
                    original(self.composite(frame, run_states), k - run_start)
                    run_start, run_states = k, states  # type: ignore[assignment]
            self.written = start + num_frames

        renderer.add_frame = add_frame
