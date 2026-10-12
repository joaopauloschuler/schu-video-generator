"""Camera geometry shared by the camera actions (``zoom``, ``pan``, ``follow``) and scenes that
move the camera themselves (DESIGN.md §69.7). No manim.

A camera *view* is the part of the scene the frame shows: its centre and its width and height in
Manim units. *Bounds* are ``(left, right, bottom, top)``: the box a view stays inside
(:meth:`NarratedScene.camera_bounds <vidgen.scene.NarratedScene.camera_bounds>`; the frame, or a
``stage`` wider than the frame).
"""

from __future__ import annotations

from collections.abc import Sequence

#: ``(left, right, bottom, top)`` in Manim units.
Bounds = tuple[float, float, float, float]


def view_center_within(bounds: Bounds, center: Sequence[float], width: float, height: float) -> tuple[float, float]:
    """The centre nearest to ``center`` (x, y) for a view ``width`` x ``height`` that keeps it
    inside ``bounds``; on an axis where the view is larger than the bounds, the bounds' middle."""
    left, right, bottom, top = bounds
    return (_clamp(center[0], left + width / 2, right - width / 2), _clamp(center[1], bottom + height / 2, top - height / 2))


def _clamp(value: float, low: float, high: float) -> float:
    if low > high:
        return (low + high) / 2
    return min(max(float(value), low), high)


__all__ = ["Bounds", "view_center_within"]
