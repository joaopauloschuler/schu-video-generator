"""Callouts: marks that point at a part of an image or of any mobject (exported by ``vidgen.api``).

Every helper takes the part it points at as an **area**: a mobject (its bounding box), a
:class:`~vidgen.regions.Region`, or coordinates relative to a reference ``within`` (a mobject,
e.g. an ``ImageMobject``, or a region; default: the frame) — ``[x, y]`` (a point) or ``[x, y, w,
h]`` (a rectangle), with ``x, y`` the top-left corner, as fractions 0–1 of the reference
(``units="fraction"``, origin top left as in image editors) or as pixels of the source image
(``units="px"``; ``within`` must then be an image). :func:`callout_area` does that conversion.

- :func:`callout_box` — a rounded rectangle around the area, with an optional label tag.
- :func:`callout_circle` — an ellipse around the area (a ring around a point).
- :func:`callout_arrow` — a label with an arrow to the area; the label is placed away from it,
  inside ``bounds`` and clear of ``avoid`` (straight or ``curved``).
- :func:`callout_magnifier` — a zoomed inset of an image's area (cropped from the image's own
  pixels with Pillow, so it is sharper than a camera zoom) joined to the area by two lines.
- :func:`callout_spotlight` — dims everything of ``within`` (or the frame) but the area.
- :func:`callout_label` — the label itself: text on a plate in the callout colour, the text in
  whichever theme colour reads best on it (≥ 4.5:1 contrast; never below the readable size).

Each returns a :class:`Callout` (a ``Group``) whose :meth:`Callout.draw` gives the animations
that bring it on screen, and :meth:`Callout.extent` the box it covers (pass it in ``avoid`` of
the next callout so labels do not land on each other). ``scale`` builds a callout smaller (strokes,
label, gaps) for a camera zoomed in by ``1 / scale``, so it reads at its normal size there.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Union

import numpy as np
from manim import (
    BOLD,
    UP,
    Animation,
    Arrow,
    Create,
    CurvedArrow,
    Cutout,
    Ellipse,
    FadeIn,
    GrowArrow,
    Group,
    ImageMobject,
    Line,
    Mobject,
    Rectangle,
    RoundedRectangle,
    VGroup,
    config,
    smooth,
)
from PIL import Image as PILImage

from vidgen.charts import text_color_on
from vidgen.errors import VidgenError
from vidgen.helpers import resolve_color
from vidgen.regions import Region, frame_region, orientation, readable_text, safe_area
from vidgen.runtime import current_theme
from vidgen.theme import Theme

log = logging.getLogger("vidgen.callouts")

#: An area a callout points at: a mobject, a region, or ``[x, y]`` / ``[x, y, w, h]``.
CalloutArea = Union[Mobject, Region, Sequence[float]]
Units = Literal["fraction", "px"]
Side = Literal["auto", "top", "bottom", "left", "right"]

#: Kinds of callouts (the helper of each is ``callout_<kind>``).
CALLOUT_KINDS: tuple[str, ...] = ("box", "circle", "arrow", "magnifier", "spotlight")
#: Stroke width of boxes, circles and arrows; of the magnifier's frames and connectors.
STROKE = 4.0
#: Space between an area and a box / circle around it (units).
PAD = 0.08
#: Distances (units) tried between an arrow's label and its area, shortest first.
ARROW_GAPS = (0.75, 1.1, 1.5, 2.0)
#: Room (units) a box's or circle's tag keeps from other text where it can (lint's
#: ``label_spacing``).
TAG_CLEARANCE = 0.2
#: Distances tried between a magnifier's inset and its area.
INSET_GAPS = (0.35, 0.7, 1.1, 1.6)


# ----- areas -----------------------------------------------------------------------------------


def mobject_region(mob: Mobject) -> Region:
    """The bounding box of ``mob`` as a :class:`Region`."""
    return Region(float(mob.get_left()[0]), float(mob.get_bottom()[1]), float(mob.get_right()[0]), float(mob.get_top()[1]))


def pixel_size(mob: Mobject) -> tuple[int, int]:
    """``(width, height)`` in pixels of an image mobject's own picture."""
    if not isinstance(mob, ImageMobject):
        raise VidgenError("pixel coordinates (units: px) need an image to measure them against")
    h, w = mob.pixel_array.shape[:2]
    return int(w), int(h)


def callout_area(
    area: CalloutArea, within: Mobject | Region | None = None, *, units: Units = "fraction", pixels: tuple[int, int] | None = None
) -> Region:
    """The rectangle (in Manim units) an area means; a point is a rectangle of size 0.

    ``area`` is a mobject (its bounding box), a :class:`Region`, or ``[x, y]`` / ``[x, y, w, h]``
    relative to ``within`` (a mobject or region; default: the frame) with ``x, y`` the top-left
    corner: fractions 0–1 of it (``units="fraction"``) or pixels (``units="px"``) of the source
    picture of ``within`` (an ``ImageMobject``) or of a picture ``pixels = (width, height)``.
    """
    if isinstance(area, Region):
        return area
    if isinstance(area, Mobject):
        return mobject_region(area)
    values = [float(v) for v in area]
    if len(values) not in (2, 4):
        raise VidgenError(f"a callout area is [x, y] or [x, y, w, h], got {list(area)!r}")
    ref = frame_region() if within is None else within if isinstance(within, Region) else mobject_region(within)
    if units == "px":
        if pixels is None:
            if not isinstance(within, Mobject):
                raise VidgenError("pixel coordinates (units: px) need an image to measure them against")
            pixels = pixel_size(within)
        values = [v / pixels[k % 2] for k, v in enumerate(values)]
    elif units != "fraction":
        raise VidgenError(f"unknown units {units!r}; use fraction or px")
    x, y = values[:2]
    w, h = values[2:] if len(values) == 4 else (0.0, 0.0)
    if w < 0 or h < 0:
        raise VidgenError(f"a callout area needs a positive width and height, got {list(area)!r}")
    x0, y1 = ref.x0 + x * ref.width, ref.y1 - y * ref.height
    return Region(x0, y1 - h * ref.height, x0 + w * ref.width, y1)


def _grow(r: Region, d: float) -> Region:
    return Region(r.x0 - d, r.y0 - d, r.x1 + d, r.y1 + d)


def _overlap(a: Region, b: Region) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return max(0.0, w) * max(0.0, h)


def _box(cx: float, cy: float, w: float, h: float) -> Region:
    return Region(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _clamp(r: Region, bounds: Region) -> Region:
    """``r`` moved (not resized) to lie inside ``bounds`` as far as its size allows."""
    dx = max(0.0, bounds.x0 - r.x0) - max(0.0, r.x1 - bounds.x1) if r.width <= bounds.width else bounds.center[0] - r.center[0]
    dy = max(0.0, bounds.y0 - r.y0) - max(0.0, r.y1 - bounds.y1) if r.height <= bounds.height else bounds.center[1] - r.center[1]
    return Region(r.x0 + dx, r.y0 + dy, r.x1 + dx, r.y1 + dy)


#: Directions tried for an arrow's label / a magnifier's inset, in order of preference.
_AROUND = [(1, 1), (-1, 1), (1, -1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)]
#: The same for a label without a mark: straight above, below or beside what it labels first.
_STRAIGHT = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1)]


def _allowed(direction: tuple[int, int], side: str) -> bool:
    """Whether ``direction`` goes to ``side`` (also ``vertical``: above or below, ``horizontal``)."""
    dx, dy = direction
    return {"auto": True, "top": dy > 0, "bottom": dy < 0, "left": dx < 0, "right": dx > 0, "vertical": dy != 0, "horizontal": dx != 0}[side]


def _distance(a: Region, b: Region) -> float:
    """The gap between two rectangles (0 when they touch or overlap)."""
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return math.hypot(dx, dy)


def _misleading(spot: Region, anchor: Region, rivals: Sequence[Region]) -> bool:
    """Whether a label at ``spot`` stands clearly nearer one of ``rivals`` (a neighbour's bar or
    value, a title) than the ``anchor`` it labels: it would read as theirs."""
    own = _distance(spot, anchor)
    return any(_distance(spot, r) < 0.75 * own - 1e-6 for r in rivals)


def _choose(
    candidates: list[tuple[Region, float]],
    anchor: Region,
    bounds: Region,
    avoid: Sequence[Region],
    *,
    near: float = 0.0,
    prefer_off: Region | None = None,
    clearance: float = 0.0,
    rivals: Sequence[Region] = (),
) -> Region:
    """The best of ``(rect, preference)`` candidates: inside ``bounds`` (moved in when they stick
    out), off the ``anchor``, clear of ``avoid`` (and preferably ``clearance`` away from it), at
    least ``near`` from the anchor, preferably off ``prefer_off`` and not nearer any of
    ``rivals`` than the anchor; ties go to the preferred one."""
    best, best_score = None, math.inf
    for rect, preference in candidates:
        moved = _clamp(rect, bounds)
        size = max(moved.width * moved.height, 1e-6)
        shift = math.hypot(*(moved.center - rect.center)[:2])
        score = 10 * _overlap(moved, _grow(anchor, 0.04)) / size
        score += 4 * sum(_overlap(moved, a) for a in avoid) / size
        if clearance > 0:
            score += 2 * sum(_overlap(moved, _grow(a, clearance)) for a in avoid) / size
        if _misleading(moved, anchor, rivals):
            score += 3
        score += 0.6 * shift + preference
        if near > 0:
            score += 6 * max(0.0, near - _distance(moved, anchor))
        if prefer_off is not None:
            score += 0.8 * _overlap(moved, prefer_off) / size
        if score < best_score - 1e-9:
            best, best_score = moved, score
    assert best is not None
    return best


def label_spot(
    size: tuple[float, float],
    anchor: Region,
    *,
    bounds: Region | None = None,
    avoid: Sequence[Region] = (),
    gaps: Sequence[float] = ARROW_GAPS,
    side: Side = "auto",
    prefer_off: Region | None = None,
    clearance: float = 0.0,
    rivals: Sequence[Region] = (),
    straight: bool = False,
) -> Region:
    """Where a box of ``size`` (width, height) goes near ``anchor`` without covering it: one of
    eight directions around it (``straight``: above, below and beside it before the corners)
    at one of ``gaps`` (not much closer than the first, even when
    moved inside ``bounds``, default: the safe area), clear of ``avoid`` (preferably by
    ``clearance``), preferably off ``prefer_off`` and not nearer one of ``rivals`` than
    ``anchor`` (a label without a mark would read as theirs). ``side`` restricts the directions
    (``top``: above it...) as long as one of them is clear of ``avoid`` (and of ``rivals``);
    when none is and another side is, that one is used (a label on a neighbour's value or bar
    would point at the wrong thing)."""
    bounds = bounds or safe_area()
    w, h = size
    cx, cy = anchor.center[:2]

    def best(allowed: str) -> Region:
        candidates = []
        for n, (dx, dy) in enumerate(d for d in (_STRAIGHT if straight else _AROUND) if _allowed(d, allowed)):
            for k, gap in enumerate(gaps):
                x = cx + dx * (anchor.width / 2 + gap * (0.75 if dy else 1.0) + w / 2)
                y = cy + dy * (anchor.height / 2 + gap * (0.75 if dx else 1.0) + h / 2)
                candidates.append((_box(x, y, w, h), 0.03 * n + 0.08 * k))
        return _choose(candidates, anchor, bounds, avoid, near=0.7 * min(gaps), prefer_off=prefer_off, clearance=clearance, rivals=rivals)

    def blocked(spot: Region) -> bool:
        return any(_overlap(spot, a) > 1e-9 for a in avoid) or _overlap(spot, anchor) > 1e-9 or _misleading(spot, anchor, rivals)

    spot = best(side)
    if side != "auto" and blocked(spot):
        anywhere = best("auto")
        if not blocked(anywhere):
            return anywhere
    return spot


def tag_spot(
    size: tuple[float, float], anchor: Region, *, bounds: Region | None = None, avoid: Sequence[Region] = (), gap: float = 0.08,
    side: Side = "auto", clearance: float = 0.0,
) -> Region:
    """Where a label tag of ``size`` goes on the edge of a mark ``anchor`` (a box): just above it
    at its left or right end, or just below it, else inside its top-left corner; preferably
    ``clearance`` away from ``avoid``."""
    bounds = bounds or safe_area()
    w, h = size
    left, right = anchor.x0 + w / 2, anchor.x1 - w / 2
    candidates = []
    # with a clearance, the same spots a little further out too (when text crowds the edge)
    for k, g in enumerate((gap, gap + clearance) if clearance > 0 else (gap,)):
        above, below = anchor.y1 + g + h / 2, anchor.y0 - g - h / 2
        options = [((0, 1), left, above), ((0, 1), right, above), ((0, -1), left, below), ((0, -1), right, below),
                   ((-1, 0), anchor.x0 - g - w / 2, anchor.y1 - h / 2), ((1, 0), anchor.x1 + g + w / 2, anchor.y1 - h / 2)]
        candidates += [(_box(x, y, w, h), 0.05 * n + 0.15 * k) for n, (d, x, y) in enumerate(options) if _allowed(d, side)]
    best = _choose(candidates, anchor, bounds, avoid, clearance=clearance)
    inside = _box(anchor.x0 + gap + w / 2, anchor.y1 - gap - h / 2, w, h)
    covers = _overlap(best, _grow(anchor, 0.04)) + sum(_overlap(best, a) for a in avoid)
    return inside if covers > 0.2 * w * h and anchor.width > w + 2 * gap and anchor.height > h + 2 * gap else best


# ----- the callout mobject -----------------------------------------------------------------------


class Callout(Group):
    """A callout: its ``mark`` (box, ellipse, arrow, inset with its frames, shade) and its
    ``tag`` (label, or ``None``), drawn in that order. ``kind`` is one of :data:`CALLOUT_KINDS`;
    ``area`` the rectangle it points at."""

    def __init__(self, kind: str, area: Region, mark: Mobject, tag: Mobject | None = None, *, steps: Sequence[Mobject] | None = None) -> None:
        super().__init__(mark, *([tag] if tag is not None else []))
        self.kind, self.area, self.mark, self.tag = kind, area, mark, tag
        #: The parts in the order they are drawn (a magnifier: source frame, lines, inset).
        self.steps = list(steps) if steps is not None else [mark]

    def extent(self, pad: float = 0.05) -> Region:
        """The box the callout covers (its mark and tag; a spotlight's shade only by its hole),
        grown by ``pad``."""
        parts = [self.tag] if self.kind == "spotlight" else [p for p in (self.mark, self.tag) if p is not None]
        boxes = [mobject_region(p) for p in parts if p is not None]
        if self.kind == "spotlight":
            boxes.append(self.area)
        return _grow(Region(min(b.x0 for b in boxes), min(b.y0 for b in boxes), max(b.x1 for b in boxes), max(b.y1 for b in boxes)), pad)

    def draw(self, start: float = 0.0) -> list[Animation]:
        """Animations that bring the callout on screen, staggered within one run time (the
        mark, then the tag; an arrow's label before its arrow), to be played together:
        ``scene.play(*callout.draw())``. With ``start`` (0–1) they wait for that share of the
        run time first (e.g. while something else leaves)."""
        parts = [*self.steps, *([self.tag] if self.tag is not None else [])]
        if self.kind == "arrow" and self.tag is not None:
            parts = [self.tag, *self.steps]  # the label first, then the arrow grows from it
        n = len(parts)
        anims = []
        for k, part in enumerate(parts):
            lo, hi = (k / (n + 0.6), (k + 1.6) / (n + 0.6)) if n > 1 else (0.0, 1.0)
            anims.append(_appear(part, _window(start + (1 - start) * lo, start + (1 - start) * hi)))
        return anims


def _window(lo: float, hi: float) -> Any:
    def rate(t: float) -> float:
        return smooth(min(1.0, max(0.0, (t - lo) / (hi - lo))))

    return rate


def _appear(part: Mobject, rate: Any) -> Animation:
    if isinstance(part, Arrow):
        return GrowArrow(part, rate_func=rate)
    if isinstance(part, (ImageMobject, Group)) or getattr(part, "callout_fade", False):
        return FadeIn(part, rate_func=rate, scale=0.92)
    if isinstance(part, VGroup) and getattr(part, "is_label", False):
        return FadeIn(part, rate_func=rate, shift=UP * 0.06)
    return Create(part, rate_func=rate)


# ----- the label -----------------------------------------------------------------------------------


def callout_label(
    text: str,
    *,
    color: Any = "highlight",
    size: str | float = "caption",
    max_width: float | None = None,
    scale: float = 1.0,
    theme: Theme | None = None,
) -> VGroup:
    """A callout's label: ``text`` (bold, wrapped to ``max_width``, default about a third of a
    16:9 frame's width, more in portrait; never below the readable size) on a rounded plate
    filled with ``color``, written in the theme colour that reads best on it. ``scale`` shrinks
    it for a zoomed-in camera. Its parts: ``.plate`` and ``.text``."""
    theme = theme or current_theme()
    fill = resolve_color(color, theme)
    ink = text_color_on(fill, theme=theme)
    frame = frame_region()
    if max_width is None:
        max_width = frame.width * (0.6 if orientation() == "portrait" else 0.3)
    words = readable_text(" ".join(text.split()), Region(0, 0, max_width, frame.height * 0.3), size=size, color=ink, weight=BOLD, theme=theme)
    pad_x, pad_y = 0.16, 0.1
    plate = RoundedRectangle(width=words.width + 2 * pad_x, height=words.height + 2 * pad_y, corner_radius=min(0.14, (words.height + 2 * pad_y) / 2))
    plate.set_fill(fill, opacity=1).set_stroke(width=0).move_to(words)
    label = VGroup(plate, words).scale(scale)
    label.plate, label.text, label.is_label = plate, words, True
    return label


def _tag(label: str, color: Any, size: str | float, scale: float, theme: Theme | None) -> VGroup | None:
    return callout_label(label, color=color, size=size, scale=scale, theme=theme) if label.strip() else None


def _place_tag(tag: VGroup | None, anchor: Region, bounds: Region | None, avoid: Sequence[Region], side: Side, scale: float) -> None:
    if tag is not None:
        spot = tag_spot((tag.width, tag.height), anchor, bounds=bounds, avoid=avoid, gap=0.08 * scale, side=side, clearance=TAG_CLEARANCE * scale)
        tag.move_to(spot.center)


# ----- the helpers -----------------------------------------------------------------------------------


def callout_box(
    area: CalloutArea,
    label: str = "",
    *,
    within: Mobject | Region | None = None,
    units: Units = "fraction",
    color: Any = "highlight",
    label_size: str | float = "caption",
    side: Side = "auto",
    bounds: Region | None = None,
    avoid: Sequence[Region] = (),
    padding: float = PAD,
    scale: float = 1.0,
    theme: Theme | None = None,
) -> Callout:
    """A rounded rectangle in ``color`` around ``area`` (``padding`` outside it), with ``label``
    as a tag on its edge (above it, else below, inside ``bounds``, clear of ``avoid``; ``side``
    picks the edge). See the module docs for ``area`` / ``within`` / ``units`` / ``scale``."""
    theme = theme or current_theme()
    r = _grow(callout_area(area, within, units=units), padding * scale)
    stroke = resolve_color(color, theme)
    mark = RoundedRectangle(width=max(r.width, 0.05), height=max(r.height, 0.05), corner_radius=min(0.12 * scale, r.height / 3, r.width / 3) or 0.01)
    mark.set_stroke(stroke, width=STROKE * scale).set_fill(opacity=0).move_to(r.center)
    tag = _tag(label, color, label_size, scale, theme)
    _place_tag(tag, mobject_region(mark), bounds, avoid, side, scale)
    return Callout("box", callout_area(area, within, units=units), mark, tag)


def callout_circle(
    area: CalloutArea,
    label: str = "",
    *,
    within: Mobject | Region | None = None,
    units: Units = "fraction",
    color: Any = "highlight",
    label_size: str | float = "caption",
    side: Side = "auto",
    bounds: Region | None = None,
    avoid: Sequence[Region] = (),
    padding: float = PAD,
    radius: float = 0.3,
    scale: float = 1.0,
    theme: Theme | None = None,
) -> Callout:
    """An ellipse in ``color`` around ``area`` (through its corners, ``padding`` further out; a
    ring of ``radius`` around a point), with ``label`` as a tag beside it. Options as for
    :func:`callout_box`."""
    theme = theme or current_theme()
    r = callout_area(area, within, units=units)
    if r.width < 1e-6 and r.height < 1e-6:
        w = h = 2 * radius * scale
    else:
        w = r.width * math.sqrt(2) + 2 * padding * scale
        h = r.height * math.sqrt(2) + 2 * padding * scale
        w, h = max(w, h * 0.45), max(h, w * 0.18)  # a very flat area still gets a visible ring
    mark = Ellipse(width=w, height=h).set_stroke(resolve_color(color, theme), width=STROKE * scale).set_fill(opacity=0).move_to(r.center)
    tag = _tag(label, color, label_size, scale, theme)
    _place_tag(tag, mobject_region(mark), bounds, avoid, side, scale)
    return Callout("circle", r, mark, tag)


def _exit(r: Region, toward: np.ndarray, buff: float) -> np.ndarray:
    """Where the ray from ``r``'s centre towards ``toward`` leaves ``r``, ``buff`` further on."""
    c = r.center
    d = np.asarray(toward, dtype=float) - c
    d[2] = 0.0
    length = float(np.linalg.norm(d))
    if length < 1e-9:
        return c
    d /= length
    tx = (r.width / 2) / abs(d[0]) if abs(d[0]) > 1e-9 else math.inf
    ty = (r.height / 2) / abs(d[1]) if abs(d[1]) > 1e-9 else math.inf
    t = min(tx, ty)
    t = 0.0 if math.isinf(t) else t
    return c + d * (t + buff)


def callout_arrow(
    area: CalloutArea,
    label: str = "",
    *,
    within: Mobject | Region | None = None,
    units: Units = "fraction",
    color: Any = "highlight",
    label_size: str | float = "caption",
    side: Side = "auto",
    curved: bool = False,
    bounds: Region | None = None,
    avoid: Sequence[Region] = (),
    prefer_off: Mobject | Region | None = None,
    scale: float = 1.0,
    theme: Theme | None = None,
) -> Callout:
    """``label`` placed near ``area`` (away from it, inside ``bounds``, clear of ``avoid`` and,
    where there is room, off ``prefer_off``, e.g. the picture; ``side`` picks the direction)
    with an arrow in ``color`` from the label to the area's edge (to the point itself for a
    point), straight or ``curved``. Without a label the arrow comes from the preferred
    direction. Options as for :func:`callout_box`."""
    theme = theme or current_theme()
    r = callout_area(area, within, units=units)
    bounds = bounds or safe_area()
    tag = _tag(label, color, label_size, scale, theme)
    w, h = (tag.width, tag.height) if tag is not None else (0.01, 0.01)
    off = prefer_off if prefer_off is None or isinstance(prefer_off, Region) else mobject_region(prefer_off)
    spot = label_spot((w, h), r, bounds=bounds, avoid=avoid, gaps=[g * scale for g in ARROW_GAPS], side=side, prefer_off=off)
    if tag is not None:
        tag.move_to(spot.center)
    end = _exit(r, spot.center, 0.06 * scale)
    start = _exit(spot, end, 0.06 * scale) if tag is not None else spot.center
    stroke = resolve_color(color, theme)
    if curved:
        cx, cy = bounds.center[:2]
        mid = (start + end) / 2
        cross = (end - start)[0] * (cy - mid[1]) - (end - start)[1] * (cx - mid[0])
        mark: Mobject = CurvedArrow(start, end, angle=(-1 if cross > 0 else 1) * math.pi / 4, tip_length=0.22 * scale)
        mark.set_stroke(stroke, width=STROKE * scale)
        mark.get_tip().set_fill(stroke, opacity=1).set_stroke(stroke, width=0)
    else:
        mark = Arrow(start, end, buff=0, stroke_width=STROKE * scale * 1.2, tip_length=0.22 * scale, max_tip_length_to_length_ratio=0.4, color=stroke)
    return Callout("arrow", r, mark, tag)


def _crop(pixels: np.ndarray, frac: tuple[float, float, float, float], out: tuple[int, int]) -> np.ndarray:
    """The part ``frac`` = (left, top, right, bottom) fractions of an RGBA ``pixels`` array,
    resampled (Lanczos) to ``out`` = (width, height) pixels."""
    h, w = pixels.shape[:2]
    box = (frac[0] * w, frac[1] * h, frac[2] * w, frac[3] * h)
    image = PILImage.fromarray(np.ascontiguousarray(pixels[..., :4] if pixels.shape[-1] >= 4 else pixels)).convert("RGBA")
    return np.array(image.resize(out, PILImage.Resampling.LANCZOS, box=box))


def _source_pixels(source: Any) -> np.ndarray | None:
    if source is None:
        return None
    if isinstance(source, np.ndarray):
        return source
    if isinstance(source, PILImage.Image):
        return np.array(source.convert("RGBA"))
    with PILImage.open(Path(source)) as im:
        return np.array(im.convert("RGBA"))


def _hull(points: list[tuple[float, float, int]]) -> list[tuple[float, float, int]]:
    """Convex hull (Andrew's monotone chain), counter-clockwise, of ``(x, y, tag)`` points."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: tuple, a: tuple, b: tuple) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 1e-12:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 1e-12:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def connector_lines(a: Region, b: Region) -> list[tuple[np.ndarray, np.ndarray]]:
    """The lines joining two rectangles along the outside of both (the edges of their convex
    hull that run from a corner of one to a corner of the other)."""
    corners = [(x, y, k) for k, r in enumerate((a, b)) for x in (r.x0, r.x1) for y in (r.y0, r.y1)]
    hull = _hull(corners)
    lines = []
    for p, q in zip(hull, hull[1:] + hull[:1]):
        if p[2] != q[2]:
            lines.append((np.array([p[0], p[1], 0.0]), np.array([q[0], q[1], 0.0])))
    return lines


def callout_magnifier(
    area: CalloutArea,
    label: str = "",
    *,
    image: ImageMobject,
    units: Units = "fraction",
    zoom: float = 2.0,
    source: Any = None,
    color: Any = "highlight",
    label_size: str | float = "caption",
    side: Side = "auto",
    bounds: Region | None = None,
    avoid: Sequence[Region] = (),
    scale: float = 1.0,
    theme: Theme | None = None,
) -> Callout:
    """A zoomed inset of ``area`` of ``image`` (``zoom`` times larger; less when the room beside
    the area inside ``bounds`` is smaller: above / below it or left / right of it, whichever
    allows more, unless ``side`` says), framed in ``color`` and joined to a frame
    around the area by two lines; placed beside the area like an arrow's label, with ``label``
    as a tag on the inset. The inset is cut from the image's own pixels (or from ``source``, a
    path / PIL image / array of the same picture at a higher resolution) and resampled with
    Pillow to the output resolution, so it is sharp. ``area`` is relative to ``image``."""
    theme = theme or current_theme()
    r = callout_area(area, image, units=units)
    if r.width < 1e-6 or r.height < 1e-6:
        raise VidgenError("a magnifier needs an area with a width and a height ([x, y, w, h])")
    bounds = bounds or safe_area()
    tag = _tag(label, color, label_size, scale, theme)
    tag_h = tag.height + 0.08 * scale if tag is not None else 0.0
    gap = INSET_GAPS[0] * scale
    # the inset goes above / below the area (as wide as the bounds) or beside it (as tall)
    above, below = bounds.y1 - r.y1 - gap - tag_h, r.y0 - bounds.y0 - gap - tag_h
    left, right = r.x0 - bounds.x0 - gap, bounds.x1 - r.x1 - gap
    fits = {
        "vertical": min(0.95 * bounds.width / r.width, max(above, below) / r.height),
        "horizontal": min(max(left, right) / r.width, (0.95 * bounds.height - tag_h) / r.height),
    }
    if side == "auto":
        side = max(fits, key=lambda k: fits[k])
    factor = min(zoom, fits["vertical" if side in ("top", "bottom", "vertical") else "horizontal"])
    if factor < 1.15:
        log.warning("magnifier: no room to enlarge the area beside it (x%.2f); use a smaller area", max(factor, 0.0))
    factor = max(factor, 1.0)
    iw, ih = r.width * factor, r.height * factor
    ib = mobject_region(image)  # the inset goes beside the picture when there is room
    spot = label_spot((iw, ih + tag_h), r, bounds=bounds, avoid=avoid, gaps=[g * scale for g in INSET_GAPS], side=side, prefer_off=ib)
    inset_box = Region(spot.x0, spot.y0, spot.x1, spot.y1 - tag_h)
    frac = ((r.x0 - ib.x0) / ib.width, (ib.y1 - r.y1) / ib.height, (r.x1 - ib.x0) / ib.width, (ib.y1 - r.y0) / ib.height)
    frac = tuple(min(1.0, max(0.0, f)) for f in frac)
    pixels = _source_pixels(source)
    pixels = pixels if pixels is not None else image.pixel_array
    per_unit = config.pixel_width / config.frame_width / scale
    out = (max(2, min(4096, round(iw * per_unit))), max(2, min(4096, round(ih * per_unit))))
    inset = ImageMobject(_crop(pixels, frac, out))
    inset.stretch_to_fit_width(iw).stretch_to_fit_height(ih).move_to(inset_box.center)
    stroke = resolve_color(color, theme)
    frame = Rectangle(width=iw, height=ih).set_stroke(stroke, width=STROKE * scale).set_fill(opacity=0).move_to(inset_box.center)
    source_frame = Rectangle(width=r.width, height=r.height).set_stroke(stroke, width=STROKE * scale * 0.75).set_fill(opacity=0).move_to(r.center)
    lines = VGroup(*[Line(p, q, stroke_width=STROKE * scale * 0.5, color=stroke, stroke_opacity=0.85) for p, q in connector_lines(r, inset_box)])
    view = Group(inset, frame)
    if tag is not None:
        tag.move_to([inset_box.x0 + tag.width / 2, inset_box.y1 + 0.08 * scale + tag.height / 2, 0])
        tag.move_to(_clamp(mobject_region(tag), bounds).center)
    mark = Group(source_frame, lines, view)
    return Callout("magnifier", r, mark, tag, steps=[source_frame, lines, view])


def callout_spotlight(
    area: CalloutArea,
    label: str = "",
    *,
    within: Mobject | Region | None = None,
    units: Units = "fraction",
    cover: Mobject | Region | None = None,
    color: Any = "highlight",
    shade: Any = None,
    opacity: float = 0.62,
    label_size: str | float = "caption",
    side: Side = "auto",
    bounds: Region | None = None,
    avoid: Sequence[Region] = (),
    padding: float = PAD,
    scale: float = 1.0,
    theme: Theme | None = None,
) -> Callout:
    """Dim everything but ``area``: a ``shade`` (default: the theme's background) at ``opacity`` over ``cover``
    (default ``within``, else the frame) with a rounded hole at the area. ``label`` becomes a tag
    (in ``color``) on the hole's edge. Options as for :func:`callout_box`."""
    theme = theme or current_theme()
    r = callout_area(area, within, units=units)
    hole = _grow(r, padding * scale)
    covered = cover if cover is not None else within
    whole = frame_region() if covered is None else covered if isinstance(covered, Region) else mobject_region(covered)
    hole = Region(max(hole.x0, whole.x0), max(hole.y0, whole.y0), min(hole.x1, whole.x1), min(hole.y1, whole.y1))
    outer = Rectangle(width=whole.width, height=whole.height).move_to(whole.center)
    cut = RoundedRectangle(width=max(hole.width, 0.02), height=max(hole.height, 0.02), corner_radius=min(0.12 * scale, hole.width / 3, hole.height / 3) or 0.01)
    cut.move_to(hole.center)
    mark = Cutout(outer, cut).set_fill(theme.background if shade is None else resolve_color(shade, theme), opacity=opacity).set_stroke(width=0)
    mark.callout_fade = True
    tag = _tag(label, color, label_size, scale, theme)
    _place_tag(tag, hole, bounds, avoid, side, scale)
    return Callout("spotlight", r, mark, tag)


def callout(kind: str, area: CalloutArea, label: str = "", **options: Any) -> Callout:
    """The callout of ``kind`` (one of :data:`CALLOUT_KINDS`) with the options of its helper:
    ``callout("box", area, "Search", within=image)`` is ``callout_box(area, "Search",
    within=image)``; a magnifier takes ``image=``."""
    helpers = {"box": callout_box, "circle": callout_circle, "arrow": callout_arrow, "magnifier": callout_magnifier, "spotlight": callout_spotlight}
    if kind not in helpers:
        raise VidgenError(f"unknown callout kind {kind!r}; use one of: {', '.join(CALLOUT_KINDS)}")
    return helpers[kind](area, label, **options)
