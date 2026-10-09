"""Vector pictures as Manim shapes: :func:`load_vector` and :class:`VectorPicture` (DESIGN.md §65).

A generated SVG (``generate: {format: svg}``) or an ``.svg`` file of the ``image`` scene is
sanitised (:func:`vidgen.svgclean.sanitize_svg`: no scripts, filters, rasters, text; gradients
flattened; shapes and points capped), parsed with Manim's ``SVGMobject`` and normalised like an
icon (§22): an invisible first part spans the ``viewBox`` (the picture's box), SVG stroke widths
become Manim's for the picture's height and scale with it, and ``recolor="theme"`` maps every
colour to the nearest theme colour (:func:`vidgen.svgclean.theme_color`).

Parts that only fill get an outline in their fill colour at zero width, so ``DrawBorderThenFill``
(the ``image`` scene's ``draw: true``) traces them before filling.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from manim import ORIGIN, SVGMobject, VGroup, VMobject

from vidgen.errors import VidgenError
from vidgen.icon_mobject import _STROKE_UNIT, SvgDrawing, work_copy
from vidgen.svgclean import CleanSvg, sanitize_svg, theme_color
from vidgen.theme import Theme

log = logging.getLogger("vidgen.scenes")


class VectorPicture(SvgDrawing):
    """A picture drawn from an SVG: an invisible box (``submobjects[0]``) and the drawn parts.

    ``source`` names the file; ``report`` is what the sanitiser changed. The layout dump
    reports it as one object of kind ``vector`` (not one per path)."""

    def __init__(self, *parts: VMobject, source: str, report: CleanSvg) -> None:
        super().__init__(*parts)
        self.source = source
        self.report = report


def _recolor(part: VMobject, theme: Theme, cache: dict[str, str]) -> None:
    def mapped(color: Any) -> str:
        key = color.to_hex().upper()
        if key not in cache:
            cache[key] = theme_color(key, theme)
        return cache[key]

    if part.get_fill_opacity() > 0:
        part.set_fill(color=mapped(part.get_fill_color()))
    if part.get_stroke_width() > 0 and part.get_stroke_opacity() > 0:
        part.set_stroke(color=mapped(part.get_stroke_color()))


def load_vector(
    path: Path,
    *,
    height: float = 1.0,
    recolor: str = "none",
    theme: Theme | None = None,
    simplify: bool | float | None = False,
    where: str | None = None,
) -> VectorPicture:
    """The :class:`VectorPicture` of the SVG file ``path``, its box ``height`` units high and
    centred on the origin. ``recolor``: ``none`` keeps the SVG's colours, ``theme`` maps them to
    ``theme``'s. ``simplify`` drops small shapes (see :func:`~vidgen.svgclean.sanitize_svg`).
    Sanitiser warnings are logged. Raises :class:`VidgenError` for an unusable SVG."""
    name = where or path.name
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise VidgenError(f"cannot read {name}: {exc}") from None
    report = sanitize_svg(data, where=name, simplify=simplify, current="#000000")
    for message in report.warnings:
        log.warning("%s", message)
    svg = SVGMobject(str(work_copy(report.data)), height=None, should_center=False)
    box, *parts = svg.submobjects
    box.set_fill(opacity=0).set_stroke(width=0, opacity=0)
    if not parts:
        raise VidgenError(f"{name}: the SVG draws nothing")
    factor = height / report.view_box[3]
    cache: dict[str, str] = {}
    if recolor == "theme" and theme is None:
        from vidgen.runtime import current_theme

        theme = current_theme()
    for part in parts:
        if recolor == "theme" and theme is not None:
            _recolor(part, theme, cache)
        width = float(part.get_stroke_width())
        if width > 0 and part.get_stroke_opacity() > 0:
            part.set_stroke(width=width * factor / _STROKE_UNIT)
        else:  # fill only: a zero-width outline in the fill colour, traced by DrawBorderThenFill
            part.set_stroke(color=part.get_fill_color(), width=0, opacity=1)
    result = VectorPicture(box, *parts, source=name, report=report)
    VGroup.scale(result, factor)  # strokes were already set for the final size
    return result.move_to(ORIGIN)


__all__ = ["VectorPicture", "load_vector"]
