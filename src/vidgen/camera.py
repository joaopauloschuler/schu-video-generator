"""Camera geometry shared by the camera actions (``zoom``, ``pan``, ``follow``) and scenes that
move the camera themselves (DESIGN.md §69.7). No manim.

A camera *view* is the part of the scene the frame shows: its centre and its width and height in
Manim units. *Bounds* are ``(left, right, bottom, top)``: the box a view stays inside
(:meth:`NarratedScene.camera_bounds <vidgen.scene.NarratedScene.camera_bounds>`; the frame, or a
``stage`` wider than the frame).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

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


#: A :class:`SmoothFollow` camera (a platform level's, DESIGN.md §86.10): the followed character
#: may move this share of the view's width either side of its centre before the camera moves...
FOLLOW_DEAD_ZONE = 0.08
#: ... and never more than this share of it, however fast it moves.
FOLLOW_MAX_OFFSET = 0.3
#: Seconds the camera takes to catch up (the smoothing time of :func:`smooth_damp`).
FOLLOW_SECONDS = 0.45
#: Shares of the view's height kept above the followed character's head and below its feet
#: (the camera moves up or down only to keep them, inside the bounds)...
FOLLOW_HEAD_ROOM = 0.08
FOLLOW_FEET_ROOM = 0.2
#: ... and above its head whatever the smoothing (the head never leaves the frame).
FOLLOW_MIN_HEAD_ROOM = 0.02


def smooth_damp(current: float, target: float, velocity: float, seconds: float, dt: float) -> tuple[float, float]:
    """``(value, velocity)`` after ``dt`` seconds of easing from ``current`` (moving at
    ``velocity``) towards ``target`` like a critically damped spring that takes about
    ``seconds`` to get there: no overshoot, no jerk, stable for any ``dt`` (a skipped animation
    gives one long step)."""
    omega = 2.0 / max(seconds, 1e-6)
    x = omega * dt
    decay = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)
    change = current - target
    pull = (velocity + omega * change) * dt
    return target + (change + pull) * decay, (velocity - omega * pull) * decay


class SmoothFollow:
    """A camera following a character gently: it moves only when the character leaves a dead
    zone round the view's centre (:data:`FOLLOW_DEAD_ZONE`), eases after it
    (:func:`smooth_damp`), never lets it get further than :data:`FOLLOW_MAX_OFFSET` from the
    centre, and with ``span_of`` (the character's feet and head-top y) moves up and down to keep
    room above its head and below its feet. Called, it gives the character's x (as the plain
    follow's function does); ``followed`` is the character (an ``exit`` stops following it)."""

    def __init__(self, x_of: Callable[[], float], span_of: Callable[[], tuple[float, float]] | None = None, followed: Any = None) -> None:
        self.x_of = x_of
        self.span_of = span_of
        self.followed = followed
        self.velocity = (0.0, 0.0)

    def __call__(self) -> float:
        return self.x_of()

    def restart(self) -> None:
        """Start from rest (the camera was moved by something else meanwhile)."""
        self.velocity = (0.0, 0.0)

    def view_center(self, center: Sequence[float], dt: float, width: float, height: float, bounds: Bounds) -> tuple[float, float]:
        """The view's centre ``dt`` seconds after ``center`` for a view ``width`` x ``height``
        inside ``bounds``."""
        x, (cx, cy) = self.x_of(), (float(center[0]), float(center[1]))
        reach = FOLLOW_DEAD_ZONE * width
        target_x, target_y = min(max(cx, x - reach), x + reach), cy
        head = None
        if self.span_of is not None:
            feet, head = self.span_of()
            low = head - height / 2 + FOLLOW_HEAD_ROOM * height
            high = feet + height / 2 - FOLLOW_FEET_ROOM * height
            target_y = low if low > high else min(max(cy, low), high)
        target_x, target_y = view_center_within(bounds, (target_x, target_y), width, height)
        new_x, vx = smooth_damp(cx, target_x, self.velocity[0], FOLLOW_SECONDS, dt)
        new_y, vy = smooth_damp(cy, target_y, self.velocity[1], FOLLOW_SECONDS, dt)
        self.velocity = (vx, vy)
        far = FOLLOW_MAX_OFFSET * width
        new_x = min(max(new_x, x - far), x + far)
        if head is not None:
            new_y = max(new_y, head - height / 2 + FOLLOW_MIN_HEAD_ROOM * height)
        return view_center_within(bounds, (new_x, new_y), width, height)


__all__ = [
    "FOLLOW_DEAD_ZONE",
    "FOLLOW_FEET_ROOM",
    "FOLLOW_HEAD_ROOM",
    "FOLLOW_MAX_OFFSET",
    "FOLLOW_MIN_HEAD_ROOM",
    "FOLLOW_SECONDS",
    "Bounds",
    "SmoothFollow",
    "smooth_damp",
    "view_center_within",
]
