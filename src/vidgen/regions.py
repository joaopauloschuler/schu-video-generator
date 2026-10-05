"""Layout regions: the safe area, named regions, grids and ``place()`` (exported by ``vidgen.api``).

A :class:`Region` is an axis-aligned rectangle in Manim units, computed from the active frame
(``config.frame_width/height``: the shorter side is 8 units, DESIGN.md §5.2). Named regions
adapt to the frame's orientation: in a vertical (9:16) frame ``left``/``right`` become the
upper/lower half, so a two-column layout written for 16:9 turns into two rows. The safe area
(frame minus :data:`MARGIN_X`/:data:`MARGIN_Y`, or a scene's ``margin_x``/``margin_y``) is the
same rectangle the layout dump records and ``vidgen lint``'s ``safe_area`` rule checks.

:func:`readable_size` is the smallest font size ``vidgen lint``'s ``min_font`` rule accepts for
the current frame, and :func:`readable_text` wraps text into a region without going below it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import numpy as np
from manim import DOWN, LEFT, ORIGIN, RIGHT, UP, Mobject, Paragraph, Rectangle, Text, config

from vidgen.errors import VidgenError
from vidgen.fonts import register_bundled_fonts
from vidgen.runtime import current_theme, has_context
from vidgen.scales import Orientation, frame_orientation
from vidgen.theme import Theme

register_bundled_fonts()  # Pango only sees fonts registered before the first text is laid out

log = logging.getLogger(__name__)

#: Default distance (Manim units) between the frame's left/right edges and the safe area.
MARGIN_X = 0.6
#: Default distance (Manim units) between the frame's top/bottom edges and the safe area.
MARGIN_Y = 0.5
#: Default gap (Manim units) between neighbouring regions and grid cells.
GAP = 0.3

Fit = Literal["contain", "width", "height", "none"]

#: Names accepted by :func:`region`.
REGION_NAMES: tuple[str, ...] = (
    "full", "header", "body", "hero", "caption", "top", "bottom", "left", "right", "center",
)

#: Alignment names accepted by :func:`place` (or pass a Manim direction such as ``UL``).
ALIGNMENTS: Mapping[str, np.ndarray] = {
    "center": ORIGIN,
    "top": UP,
    "bottom": DOWN,
    "left": LEFT,
    "right": RIGHT,
    "top_left": UP + LEFT,
    "top_right": UP + RIGHT,
    "bottom_left": DOWN + LEFT,
    "bottom_right": DOWN + RIGHT,
}

# Shares of the safe area's height (landscape, square, portrait) for the bands of named regions.
_HEADER = {"landscape": 0.16, "square": 0.15, "portrait": 0.12}
_CAPTION = {"landscape": 0.12, "square": 0.11, "portrait": 0.09}
# Size of ``center`` as shares of the safe area's (width, height).
_CENTER = {"landscape": (0.72, 0.72), "square": (0.86, 0.72), "portrait": (1.0, 0.6)}


def orientation(width: float | None = None, height: float | None = None) -> Orientation:
    """``"landscape"`` (wider than 1.2:1), ``"portrait"`` (taller than 1:1.2) or ``"square"``.

    Defaults to the active frame.
    """
    w = float(config.frame_width if width is None else width)
    h = float(config.frame_height if height is None else height)
    return frame_orientation(w, h)


@dataclass(frozen=True)
class Region:
    """A rectangle in Manim units: ``x0 < x1`` (left to right), ``y0 < y1`` (bottom to top)."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise VidgenError(f"region has a negative size: {self}")

    # ----- geometry --------------------------------------------------------------------------

    @property
    def width(self) -> float:
        """Width in Manim units."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Height in Manim units."""
        return self.y1 - self.y0

    @property
    def center(self) -> np.ndarray:
        """Center point ``[x, y, 0]``."""
        return np.array([(self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2, 0.0])

    @property
    def orientation(self) -> Orientation:
        """Orientation of this rectangle (see :func:`orientation`)."""
        return orientation(self.width, self.height)

    def point(self, align: str | Sequence[float] = "center") -> np.ndarray:
        """The point of the region for an alignment: ``"top_left"`` -> its top-left corner."""
        d = _direction(align)
        return self.center + np.array([d[0] * self.width / 2, d[1] * self.height / 2, 0.0])

    def contains(self, mob: Mobject, tolerance: float = 1e-6) -> bool:
        """True if ``mob``'s bounding box lies inside the region."""
        return bool(
            mob.get_left()[0] >= self.x0 - tolerance
            and mob.get_right()[0] <= self.x1 + tolerance
            and mob.get_bottom()[1] >= self.y0 - tolerance
            and mob.get_top()[1] <= self.y1 + tolerance
        )

    # ----- derived regions -------------------------------------------------------------------

    def inset(self, x: float, y: float | None = None) -> Region:
        """The region shrunk by ``x`` on the left/right and ``y`` (default ``x``) top/bottom."""
        y = x if y is None else y
        x = min(x, self.width / 2)
        y = min(y, self.height / 2)
        return Region(self.x0 + x, self.y0 + y, self.x1 - x, self.y1 - y)

    def below(self, edge: float | Mobject, gap: float = 0.0) -> Region:
        """The part of the region below ``edge`` (a y value or a mobject's bottom) minus ``gap``."""
        y = float(edge.get_bottom()[1]) if isinstance(edge, Mobject) else float(edge)
        top = max(self.y0, min(self.y1, y - gap))
        return Region(self.x0, self.y0, self.x1, top)

    def above(self, edge: float | Mobject, gap: float = 0.0) -> Region:
        """The part of the region above ``edge`` (a y value or a mobject's top) plus ``gap``."""
        y = float(edge.get_top()[1]) if isinstance(edge, Mobject) else float(edge)
        bottom = min(self.y1, max(self.y0, y + gap))
        return Region(self.x0, bottom, self.x1, self.y1)

    def rows(self, count: int | Sequence[float], gap: float = GAP) -> list[Region]:
        """Split into stacked rows, top to bottom: ``count`` equal ones or by relative weights."""
        heights = _shares(count, self.height, gap)
        out, top = [], self.y1
        for h in heights:
            out.append(Region(self.x0, top - h, self.x1, top))
            top -= h + gap
        return out

    def columns(self, count: int | Sequence[float], gap: float = GAP) -> list[Region]:
        """Split into side-by-side columns, left to right: ``count`` equal ones or by weights."""
        widths = _shares(count, self.width, gap)
        out, left = [], self.x0
        for w in widths:
            out.append(Region(left, self.y0, left + w, self.y1))
            left += w + gap
        return out

    def split(self, count: int | Sequence[float], gap: float = GAP) -> list[Region]:
        """Orientation-aware split: :meth:`columns` in a landscape or square frame, :meth:`rows`
        in a portrait frame (the active frame's orientation, not this region's)."""
        return self.rows(count, gap) if orientation() == "portrait" else self.columns(count, gap)

    def grid(self, rows: int, cols: int, gap: float = GAP, gap_y: float | None = None) -> list[Region]:
        """``rows x cols`` cells (row-major: left to right, then top to bottom), ``gap`` between
        columns and ``gap_y`` (default ``gap``) between rows."""
        if rows < 1 or cols < 1:
            raise VidgenError(f"grid needs at least 1 row and 1 column, got {rows} x {cols}")
        return [cell for row in self.rows(rows, gap if gap_y is None else gap_y) for cell in row.columns(cols, gap)]

    def to_rectangle(self, **kwargs: Any) -> Rectangle:
        """A Manim ``Rectangle`` outlining the region (handy to debug a layout)."""
        kwargs.setdefault("stroke_width", 2)
        return Rectangle(width=self.width, height=self.height, **kwargs).move_to(self.center)


def _shares(count: int | Sequence[float], total: float, gap: float) -> list[float]:
    """Sizes of ``count`` parts (or parts weighted by ``count``) of ``total`` minus the gaps."""
    weights = [1.0] * count if isinstance(count, int) else [float(w) for w in count]
    if not weights or any(w <= 0 for w in weights):
        raise VidgenError(f"a split needs at least one part and positive weights, got {count!r}")
    room = max(0.0, total - gap * (len(weights) - 1))
    return [room * w / sum(weights) for w in weights]


def _direction(align: str | Sequence[float]) -> np.ndarray:
    if isinstance(align, str):
        key = align.strip().lower().replace(" ", "_").replace("-", "_")
        if key not in ALIGNMENTS:
            raise VidgenError(f"unknown alignment {align!r}; use one of: {', '.join(ALIGNMENTS)} or a direction like UL")
        return np.array(ALIGNMENTS[key], dtype=float)
    d = np.array(align, dtype=float)[:3]
    return np.sign(np.pad(d, (0, 3 - len(d))))


# ----- frame, safe area and named regions -----------------------------------------------------


def frame_region() -> Region:
    """The whole visible frame (``config.frame_width x frame_height``, centered on the origin)."""
    w, h = float(config.frame_width), float(config.frame_height)
    return Region(-w / 2, -h / 2, w / 2, h / 2)


def safe_area(margin_x: float = MARGIN_X, margin_y: float = MARGIN_Y) -> Region:
    """The frame minus the margins: where content (text above all) should stay.

    ``NarratedScene.safe_area`` uses the scene's ``margin_x``/``margin_y``; the layout dump and
    ``vidgen lint`` use the same rectangle.
    """
    return frame_region().inset(margin_x, margin_y)


def region(name: str, area: Region | None = None, gap: float = GAP) -> Region:
    """A named region of ``area`` (default: :func:`safe_area`), adapted to the frame's orientation.

    - ``full``: the whole area.
    - ``header``: a band at the top for a title (16 % of the height; 12 % in portrait).
    - ``caption``: a band at the bottom (12 %; 9 % in portrait).
    - ``body``: everything below the header; ``hero``: between header and caption.
    - ``top`` / ``bottom``: the upper / lower half.
    - ``left`` / ``right``: the left / right half; **in portrait the upper / lower half**, so a
      two-column layout becomes two rows (use ``Region.columns(2)`` for literal halves).
    - ``center``: a centered box (72 % x 72 %; full width x 60 % in portrait).
    """
    a = area if area is not None else safe_area()
    o = orientation()
    header_h = a.height * _HEADER[o]
    caption_h = a.height * _CAPTION[o]
    if name == "full":
        return a
    if name == "header":
        return Region(a.x0, a.y1 - header_h, a.x1, a.y1)
    if name == "caption":
        return Region(a.x0, a.y0, a.x1, a.y0 + caption_h)
    if name == "body":
        return a.below(a.y1 - header_h, gap)
    if name == "hero":
        return Region(a.x0, min(a.y0 + caption_h + gap, a.y1 - header_h - gap), a.x1, a.y1 - header_h - gap)
    if name in ("top", "bottom"):
        upper, lower = a.rows(2, gap)
        return upper if name == "top" else lower
    if name in ("left", "right"):
        first, second = a.split(2, gap)
        return first if name == "left" else second
    if name == "center":
        fw, fh = _CENTER[o]
        return a.inset(a.width * (1 - fw) / 2, a.height * (1 - fh) / 2)
    raise VidgenError(f"unknown region {name!r}; use one of: {', '.join(REGION_NAMES)}")


def grid(
    rows: int, cols: int, area: str | Region = "full", gap: float = GAP, gap_y: float | None = None
) -> list[Region]:
    """``rows x cols`` cells of a named region or :class:`Region` (row-major); see
    :meth:`Region.grid`."""
    return _resolve(area).grid(rows, cols, gap, gap_y)


def _resolve(area: str | Region) -> Region:
    return region(area) if isinstance(area, str) else area


# ----- placing mobjects -------------------------------------------------------------------------


def place(
    mob: Mobject,
    area: str | Region,
    fit: Fit = "contain",
    align: str | Sequence[float] = "center",
    *,
    max_scale: float | None = None,
    buff: float = 0.0,
) -> Mobject:
    """Scale ``mob`` into a region and move it there; returns ``mob``.

    ``area`` is a region name (of the default safe area) or a :class:`Region`; ``buff`` insets
    it. ``fit``: ``contain`` scales (up or down) to the largest size that fits both ways,
    ``width``/``height`` match that side only (the other may overflow), ``none`` keeps the
    size. ``max_scale`` caps the scale factor (e.g. ``1.0``: shrink only, never enlarge).
    ``align`` (``"center"``, ``"top"``, ``"bottom_left"``, ... or a Manim direction such as
    ``UL``) puts that edge/corner of ``mob`` on the same edge/corner of the region.
    """
    target = _resolve(area)
    if buff:
        target = target.inset(buff)
    if fit not in ("contain", "width", "height", "none"):
        raise VidgenError(f"unknown fit {fit!r}; use contain, width, height or none")
    if fit != "none":
        factors = []
        if fit in ("contain", "width") and mob.width > 1e-9:
            factors.append(target.width / mob.width)
        if fit in ("contain", "height") and mob.height > 1e-9:
            factors.append(target.height / mob.height)
        if factors:
            factor = min(factors)
            if max_scale is not None:
                factor = min(factor, max_scale)
            mob.scale(factor)
    direction = _direction(align)
    mob.move_to(target.point(direction), aligned_edge=direction)
    return mob


# ----- readable text ----------------------------------------------------------------------------

#: Default smallest cap height (fraction of the frame's shorter side), as ``vidgen lint``'s
#: ``min_font`` rule (``lint.rules.min_font.min_size``).
MIN_TEXT_FRACTION = 0.025


@lru_cache(maxsize=64)
def _cap_height_per_point(font: str) -> float:
    """Height of a capital letter of ``font`` in Manim units per point of font size."""
    return float(Text("H", font=font, font_size=48).height) / 48


def min_text_fraction() -> float:
    """The cap-height fraction :func:`readable_size` aims for: the active project's
    ``lint.rules.min_font.min_size`` (default :data:`MIN_TEXT_FRACTION`)."""
    if has_context():
        from vidgen.runtime import current_project

        return float(current_project().config.lint.rules.min_font.min_size)
    return MIN_TEXT_FRACTION


def readable_size(font: str | None = None, *, fraction: float | None = None, margin: float = 1.05) -> float:
    """Smallest font size (points, as for ``Text(font_size=...)``) whose capital letters are
    at least ``fraction`` (default :func:`min_text_fraction`) of the frame's shorter side, times
    ``margin`` (lint measures sizes within a few percent). ``font`` defaults to the theme font.

    For the defaults this is about 21 points whatever the resolution (the frame is always 8
    units on its shorter side). A mobject scaled after it was built counts with that scale.
    """
    font = font or current_theme().font
    fraction = min_text_fraction() if fraction is None else fraction
    short = min(float(config.frame_width), float(config.frame_height))
    return fraction * short / _cap_height_per_point(font) * margin


def readable_text(
    text: str,
    area: str | Region,
    *,
    size: str | float = "body",
    min_size: str | float | None = None,
    theme: Theme | None = None,
    **kwargs: Any,
) -> Paragraph:
    """Text wrapped to fit a region without going below a readable size.

    Like :func:`vidgen.layout.fit_text` with the region's width and height, but the font is
    never reduced below ``max(min_size, readable_size())``: long text wraps onto more lines
    instead. If it still does not fit the region's height at that size, it is scaled down to
    fit and a warning is logged (``vidgen lint`` then reports ``min_font``). Other keyword
    arguments (``color``, ``weight``, ``align``, ``highlights``...) go to ``fit_text``. The
    result is not moved: use :func:`place` (``fit="none"``) to position it.
    """
    from vidgen.layout import fit_text_sized

    theme = theme or current_theme()
    floor = readable_size(kwargs.get("font") or theme.font)
    if min_size is not None:
        floor = max(floor, float(theme.size(min_size)))
    start = max(float(theme.size(size)), floor)
    target = _resolve(area)
    block, used = fit_text_sized(text, target.width, target.height, size=start, min_size=floor, theme=theme, **kwargs)
    if used < floor * 0.999:
        log.warning(
            "text %r does not fit a %.2f x %.2f region at the readable size %.0f; scaled to %.0f",
            _short(text), target.width, target.height, floor, used,
        )
    return block


def _short(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
