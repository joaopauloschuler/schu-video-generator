"""A flashback's look on a stage (DESIGN.md §100.12): faded, warm colours and a soft dark frame.

``flashback: true`` on a stage grades the set and the characters like an old photograph
(:func:`flashback_grade`: :data:`FLASHBACK_SATURATION` of their saturation kept, multiplied
towards a warm sepia tint, the blacks lifted a little, a dreamy haze) and lays a soft vignette
over the frame (:class:`CameraVignette`: darker towards the edges and corners, in a warm dark
colour), which stays on the camera's view while it moves. Speech bubbles, name tags and captions
are drawn over it, ungraded.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from manim import ImageMobject

from vidgen.cartoon.lighting import LightGrade, tint_grade
from vidgen.lint.color import hex_rgb

#: The default warm tint, its strength, the saturation kept and the lift of the blacks (a share
#: of the tint added to every colour).
FLASHBACK_TINT = "#E8C08A"
FLASHBACK_STRENGTH = 0.45
FLASHBACK_SATURATION = 0.4
FLASHBACK_LIFT = 0.06
#: The vignette: its colour, its opacity in the corners, where it starts (a share of the way
#: from the middle to the edge) and the picture's size (pixels; it is stretched to the view).
VIGNETTE_COLOR = "#2A1C12"
VIGNETTE_OPACITY = 0.7
VIGNETTE_INNER = 0.45
VIGNETTE_PIXELS = (320, 180)


def flashback_grade(base: LightGrade, *, tint: str = FLASHBACK_TINT, strength: float = FLASHBACK_STRENGTH,
                    saturation: float = FLASHBACK_SATURATION) -> LightGrade:
    """``base`` (a stage's light) as a flashback: its colours faded to ``saturation``, multiplied
    towards ``tint`` at ``strength``, the blacks lifted by :data:`FLASHBACK_LIFT` of the tint."""
    sepia = tint_grade(tint, strength)
    lift = tuple(FLASHBACK_LIFT * c for c in hex_rgb(tint))
    multiply = tuple(a * b for a, b in zip(base.multiply, sepia.multiply))
    glow = tuple(min(a + b, 1.0) for a, b in zip(base.glow, lift))
    return LightGrade(multiply, glow, base.stars, base.shadow, base.saturation * saturation)  # type: ignore[arg-type]


def vignette_pixels(width: int, height: int, *, color: str = VIGNETTE_COLOR, opacity: float = VIGNETTE_OPACITY,
                    inner: float = VIGNETTE_INNER) -> np.ndarray:
    """An RGBA picture ``width`` x ``height`` (uint8) of a soft vignette: ``color``, clear inside
    ``inner`` of the way to the edge (an ellipse filling the frame) and rising smoothly to
    ``opacity`` at the corners."""
    ys, xs = np.mgrid[0:height, 0:width]
    u = (xs + 0.5) / width * 2.0 - 1.0
    v = (ys + 0.5) / height * 2.0 - 1.0
    r = np.sqrt(u * u + v * v) / np.sqrt(2.0)   # 0 the middle, 1 a corner
    share = np.clip((r - inner * 0.75) / (1.0 - inner * 0.75), 0.0, 1.0)
    alpha = opacity * share * share * (3.0 - 2.0 * share)
    out = np.zeros((height, width, 4), dtype=np.uint8)
    out[..., :3] = np.array([round(255 * c) for c in hex_rgb(color)], dtype=np.uint8)
    out[..., 3] = np.clip(np.rint(alpha * 255), 0, 255).astype(np.uint8)
    return out


class CameraVignette(ImageMobject):
    """A vignette picture kept over the camera's ``frame`` (its size and place on every frame)."""

    def __init__(self, frame: Any, *, color: str = VIGNETTE_COLOR, opacity: float = VIGNETTE_OPACITY, **kwargs: Any) -> None:
        super().__init__(vignette_pixels(*VIGNETTE_PIXELS, color=color, opacity=opacity), **kwargs)
        self.name = "vignette"
        self.frame = frame
        self.follow()
        self.add_updater(lambda m: m.follow())

    def follow(self) -> CameraVignette:
        """Cover the camera's view now."""
        self.stretch_to_fit_width(float(self.frame.width))
        self.stretch_to_fit_height(float(self.frame.height))
        self.move_to(self.frame.get_center())
        return self


__all__ = [
    "FLASHBACK_SATURATION",
    "FLASHBACK_STRENGTH",
    "FLASHBACK_TINT",
    "VIGNETTE_COLOR",
    "VIGNETTE_OPACITY",
    "CameraVignette",
    "flashback_grade",
    "vignette_pixels",
]
