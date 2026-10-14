"""How cartoons are drawn (DESIGN.md §79): the ``drawing:`` setting's outline weight, shading and
texture.

Like the stage's light (§69.31), the style is applied when Manim draws, never to the mobjects:
:func:`style_camera` wraps a scene camera's ``apply_stroke`` (stroke widths times the outline
factor) and ``apply_fill`` (a soft top-to-bottom gradient on what :func:`mark_shaded` marked),
and :func:`attach_texture` wraps the renderer's ``add_frame`` (a still grain multiplied into each
frame written, under the overlays). The drawings, their pinned digests and the layout dump are
unchanged, and a plain style (``normal`` / ``flat`` / ``none``) installs nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any

import numpy as np

from vidgen.config import DrawingConfig

#: Stroke width factor of each ``outline``.
OUTLINE_FACTORS: dict[str, float] = {"thin": 0.6, "normal": 1.0, "bold": 1.7}
#: ``soft`` shading: the share towards white at a shape's top and towards black at its bottom.
SOFT_LIGHT = 0.14
SOFT_SHADE = 0.16
#: The attributes :func:`mark_shaded` / :func:`mark_outlined` set on what they mark.
SHADED = "drawing_shaded"
OUTLINED = "drawing_outlined"


@dataclass(frozen=True)
class TextureRecipe:
    """A texture's grain: the darkening (0..1) of its per-pixel ``grain`` (``grain_pixels`` large),
    of its soft ``blotches`` (``cells`` across the frame's short side) and towards the
    ``corners``."""

    grain: float
    grain_pixels: int
    blotches: float
    cells: int
    corners: float


#: The textures besides ``none``.
TEXTURES: dict[str, TextureRecipe] = {
    "paper": TextureRecipe(grain=0.04, grain_pixels=1, blotches=0.03, cells=48, corners=0.0),
    "storybook": TextureRecipe(grain=0.05, grain_pixels=2, blotches=0.07, cells=12, corners=0.12),
}


@dataclass(frozen=True)
class DrawingStyle:
    """A resolved ``drawing:`` setting (every key set)."""

    outline: str = "normal"
    shading: str = "flat"
    texture: str = "none"
    seed: int = 0

    @property
    def outline_factor(self) -> float:
        """The factor stroke widths are drawn with."""
        return OUTLINE_FACTORS[self.outline]

    @property
    def is_plain(self) -> bool:
        """Whether the style draws everything as drawn (nothing to install)."""
        return self.outline == "normal" and self.shading == "flat" and self.texture == "none"

    def for_draft(self) -> DrawingStyle:
        """The style of a draft (DESIGN.md §74): the outline kept, no shading, no texture."""
        return replace(self, shading="flat", texture="none")


def resolve_drawing(*settings: DrawingConfig | None) -> DrawingStyle:
    """The style of ``settings`` (the video's, then a scene's), a later setting's keys winning."""
    values: dict[str, Any] = {}
    for setting in settings:
        if setting is not None:
            values.update(setting.model_dump(exclude_none=True))
    return DrawingStyle(**values)


def soft_stops(rgb: Sequence[float]) -> list[tuple[float, tuple[float, float, float]]]:
    """The gradient of a ``soft`` shaded fill of colour ``rgb`` (0..1): (offset from the top,
    colour) stops, lighter at the top, the colour itself half-way, darker at the bottom."""
    base = np.clip(np.asarray(rgb[:3], dtype=float), 0.0, 1.0)
    light = base + (1.0 - base) * SOFT_LIGHT
    dark = base * (1.0 - SOFT_SHADE)
    return [(0.0, tuple(map(float, light))), (0.5, tuple(map(float, base))), (1.0, tuple(map(float, dark)))]  # type: ignore[misc]


@lru_cache(maxsize=4)
def texture_shade(texture: str, seed: int, width: int, height: int) -> np.ndarray:
    """The ``texture``'s multiplier for a ``width`` x ``height`` RGBA frame (H x W x 4, uint16; 256
    leaves a channel unchanged, as it leaves alpha), the same for the same arguments."""
    from PIL import Image

    recipe = TEXTURES[texture]
    rng = np.random.default_rng([seed, list(TEXTURES).index(texture)])
    step = recipe.grain_pixels
    grain = rng.random((-(-height // step), -(-width // step)), dtype=np.float32)
    grain = np.repeat(np.repeat(grain, step, axis=0), step, axis=1)[:height, :width]
    short = min(width, height)
    cells = (max(2, round(recipe.cells * width / short)), max(2, round(recipe.cells * height / short)))
    coarse = rng.random((cells[1], cells[0]), dtype=np.float32)
    blotches = np.clip(np.asarray(Image.fromarray(coarse).resize((width, height), Image.Resampling.BICUBIC)), 0.0, 1.0)
    darkness = recipe.grain * grain + recipe.blotches * blotches
    if recipe.corners:
        y, x = np.ogrid[0:height, 0:width]
        reach = ((x + 0.5) / width - 0.5) ** 2 + ((y + 0.5) / height - 0.5) ** 2   # 0 in the middle, 0.5 in a corner
        darkness = darkness + recipe.corners * (2.0 * reach) ** 1.5
    shade = np.full((height, width, 4), 256, dtype=np.uint16)
    shade[:, :, :3] = np.rint(256.0 * (1.0 - darkness)).clip(0, 256).astype(np.uint16)[:, :, None]
    shade.setflags(write=False)
    return shade


def apply_texture(frame: np.ndarray, shade: np.ndarray) -> np.ndarray:
    """A copy of ``frame`` (H x W x 4, uint8) with its colour multiplied by ``shade``
    (:func:`texture_shade`), its alpha kept."""
    product = np.multiply(frame, shade, dtype=np.uint16)   # all four channels at once: 8x faster than a colour slice
    np.right_shift(product, 8, out=product)
    return product.astype(np.uint8)


def attach_texture(renderer: Any, style: DrawingStyle) -> None:
    """Multiply ``style``'s texture into every frame ``renderer`` writes (wraps its ``add_frame``:
    call after the overlays attach and before the colour fade, so overlays and captions stay
    clean and the fade's colour is textured too). One multiply per write: a frozen wait costs one."""
    original = renderer.add_frame

    def add_frame(frame: np.ndarray, num_frames: int = 1) -> None:
        if getattr(renderer, "skip_animations", False) or num_frames <= 0:
            original(frame, num_frames)
            return
        shade = texture_shade(style.texture, style.seed, int(frame.shape[1]), int(frame.shape[0]))
        original(apply_texture(frame, shade), num_frames)

    renderer.add_frame = add_frame


def mark_shaded(*mobjects: Any) -> None:
    """Mark ``mobjects`` and everything in them as shaded by a ``soft`` style."""
    _mark(mobjects, SHADED)


def mark_outlined(*mobjects: Any) -> None:
    """Mark ``mobjects`` and everything in them as outlined by the style on a camera that does not
    style every stroke (a host's, :func:`style_camera`)."""
    _mark(mobjects, OUTLINED)


def _mark(mobjects: Iterable[Any], attribute: str) -> None:
    for mob in mobjects:
        for member in mob.get_family():
            setattr(member, attribute, True)


def style_camera(camera: Any, style: DrawingStyle, *, every_stroke: bool) -> None:
    """Draw with ``camera`` (a Manim Cairo camera) in ``style``: stroke widths times the outline
    factor (every stroke, or only what :func:`mark_outlined` marked; a thinned stroke stays at
    least one pixel wide unless it was thinner), and the fills :func:`mark_shaded` marked with a
    ``soft`` gradient. A plain part of the style installs nothing."""
    factor = style.outline_factor
    if factor != 1.0:
        from vidgen.cartoon.character import one_pixel_stroke

        stroke, floor = camera.apply_stroke, one_pixel_stroke()

        def apply_stroke(ctx: Any, vmobject: Any, background: bool = False) -> Any:
            width = float(vmobject.get_stroke_width(background))
            if width <= 0 or not (every_stroke or getattr(vmobject, OUTLINED, False)):
                return stroke(ctx, vmobject, background)
            base = camera.cairo_line_width_multiple
            camera.cairo_line_width_multiple = base * max(width * factor, min(width, floor)) / width
            try:
                return stroke(ctx, vmobject, background)
            finally:
                camera.cairo_line_width_multiple = base

        camera.apply_stroke = apply_stroke
    if style.shading == "soft":
        fill = camera.apply_fill

        def apply_fill(ctx: Any, vmobject: Any) -> Any:
            if not getattr(vmobject, SHADED, False) or len(vmobject.points) == 0:
                return fill(ctx, vmobject)
            rgbas = camera.get_fill_rgbas(vmobject)   # graded by the light when it is wrapped too
            if len(rgbas) != 1 or rgbas[0][3] <= 0:
                return fill(ctx, vmobject)
            ys = camera.transform_points_pre_display(vmobject, vmobject.points)[:, 1]
            top, bottom = float(np.max(ys)), float(np.min(ys))
            if top <= bottom:
                return fill(ctx, vmobject)
            return _fill_gradient(camera, ctx, rgbas[0], top, bottom)

        camera.apply_fill = apply_fill


def _fill_gradient(camera: Any, ctx: Any, rgba: Sequence[float], top: float, bottom: float) -> Any:
    """Fill the path set on ``ctx`` with the :func:`soft_stops` of ``rgba`` from ``top`` to
    ``bottom`` (the camera's drawing units)."""
    import cairo

    gradient = cairo.LinearGradient(0.0, top, 0.0, bottom)
    for offset, (r, g, b) in soft_stops(rgba):
        gradient.add_color_stop_rgba(offset, b, g, r, float(rgba[3]))   # Cairo's surface is BGRA, as Manim's own colours
    ctx.set_source(gradient)
    ctx.fill_preserve()
    return camera
