"""Layout rules: checks of one still's layout dump (DESIGN.md §16).

Sizes are measured against the frame's shorter side (:attr:`StillContext.short_side`), so the
same thresholds hold for a 480p preview and the 1080p video, and for 16:9 and 9:16.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import combinations
from typing import Any

import numpy as np

from vidgen.config import (
    ContrastRule,
    CoveredTextRule,
    MaxWordsRule,
    MinFontRule,
    OffFrameRule,
    SafeAreaRule,
    TextOverlapRule,
)
from vidgen.lint.color import blend, contrast_ratio, hex_rgb, rgb_hex
from vidgen.lint.rules import Bbox, Issue, StillContext, rule

TEXT_KINDS = frozenset({"text", "code", "math", "number"})

# Glyph heights in em (Inter-like proportions) by character, to turn ``font_px`` (a percentile
# of the glyph heights) into a cap height whatever the letters: "sparse" (x-height glyphs) and
# "Baseline" (ascenders) at the same font size measure 11 and 15 px, but have the same size.
_CAP = 0.73
_X_HEIGHT = 0.55
_DESCENDER = 0.76
_SMALL = 0.15
_GLYPH_EM: dict[str, float] = {
    **dict.fromkeys("acemnorsuvwxz", _X_HEIGHT),
    **dict.fromkeys("gpqy", _DESCENDER),
    "j": 0.95,
    **dict.fromkeys(".,:;·•-–—_'\"`‘’“”", _SMALL),
}


def is_text(obj: dict[str, Any]) -> bool:
    """True for text kinds (``text``, ``code``, ``math``, ``number``)."""
    return obj["kind"] in TEXT_KINDS


def cap_height(obj: dict[str, Any]) -> float:
    """The text's size as a cap height in px: ``font_px`` corrected for which glyphs it has.

    ``font_px`` is the 75th percentile of the glyph heights; the same percentile of typical
    glyph heights for the object's characters (in em) gives the correction. Math (LaTeX source,
    not the drawn glyphs) is taken as measured.
    """
    font_px = float(obj.get("font_px") or 0.0)
    if obj["kind"] == "math":
        return font_px
    heights = [_GLYPH_EM.get(ch, _CAP) for ch in str(obj.get("text", "")) if not ch.isspace()]
    if not heights:
        return font_px
    return font_px * _CAP / float(np.percentile(heights, 75))


def has_letters_or_digits(obj: dict[str, Any]) -> bool:
    """True if the text has a letter or digit (a lone symbol has no meaningful size)."""
    return obj["kind"] == "math" or any(ch.isalnum() for ch in str(obj.get("text", "")))


def describe(obj: dict[str, Any]) -> str:
    """A short human label: ``text 'Hello world'``, ``icon 'cpu'`` or
    ``shape Rectangle 'Group[0]/Rectangle[1]'``."""
    if is_text(obj):
        text = " / ".join(line.strip() for line in str(obj.get("text", "")).splitlines() if line.strip())
        if len(text) > 40:
            text = text[:39] + "…"
        return f"{obj['kind']} '{text}'"
    if obj["kind"] == "icon":
        return f"icon '{obj.get('icon')}'"
    return f"{obj['kind']} {obj['class']} '{obj.get('name') or obj['path']}'"


def area(box: Bbox | list[float]) -> float:
    """Area of ``[x0, y0, x1, y1]`` (0 for an empty box)."""
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def intersection(a: Bbox | list[float], b: Bbox | list[float]) -> Bbox | None:
    """The overlap of two boxes, or ``None`` when they do not overlap."""
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return box if box[2] > box[0] and box[3] > box[1] else None


def _bbox(obj: dict[str, Any]) -> Bbox:
    x0, y0, x1, y1 = obj["bbox"]
    return (float(x0), float(y0), float(x1), float(y1))


def _is_ancestor(path: str, of: str) -> bool:
    return of.startswith(path + "/")


# ----- rules -----------------------------------------------------------------------------------


@rule("off_frame", default="error")
def off_frame(ctx: StillContext, settings: OffFrameRule) -> Iterator[Issue]:
    """An object is cut off by the frame edge."""
    width, height = ctx.width, ctx.height
    tolerance = settings.tolerance * ctx.short_side
    for obj in ctx.objects:
        x0, y0, x1, y1 = _bbox(obj)
        if x1 <= 0 or y1 <= 0 or x0 >= width or y0 >= height:
            continue  # wholly outside: not seen at all (e.g. waiting to slide in)
        outside = {"left": -x0, "top": -y0, "right": x1 - width, "bottom": y1 - height}
        if not is_text(obj):
            # Intentional bleeds: a full-frame image (fit: cover, Ken Burns), a background, a
            # band or divider running from edge to edge cross both edges of that axis.
            if x0 <= tolerance and x1 >= width - tolerance:
                outside["left"] = outside["right"] = 0.0
            if y0 <= tolerance and y1 >= height - tolerance:
                outside["top"] = outside["bottom"] = 0.0
        sides = [side for side, px in outside.items() if px > tolerance]
        if not sides:
            continue
        worst = max(outside[side] for side in sides)
        hidden = 1 - area(intersection(_bbox(obj), (0, 0, width, height)) or (0, 0, 0, 0)) / max(area(_bbox(obj)), 1e-9)
        yield Issue(
            f"{describe(obj)} is cut off at the {' and '.join(sides)} edge of the frame "
            f"({worst:.0f} px outside, {hidden:.0%} of its box hidden)",
            _bbox(obj),
            (obj,),
            severity="error" if is_text(obj) else "warning",
            value=round(worst, 1),
            limit=round(tolerance, 1),
        )


@rule("safe_area")
def safe_area(ctx: StillContext, settings: SafeAreaRule) -> Iterator[Issue]:
    """Text lies outside the safe area (the scene's margins), though inside the frame."""
    sx0, sy0, sx1, sy1 = ctx.layout["safe_area"]
    tolerance = settings.tolerance * ctx.short_side
    for obj in ctx.objects:
        if not is_text(obj):
            continue
        x0, y0, x1, y1 = _bbox(obj)
        if x0 < -0.5 or y0 < -0.5 or x1 > ctx.width + 0.5 or y1 > ctx.height + 0.5:
            continue  # off the frame: off_frame's finding
        outside = {"left": sx0 - x0, "top": sy0 - y0, "right": x1 - sx1, "bottom": y1 - sy1}
        sides = [side for side, px in outside.items() if px > tolerance]
        if not sides:
            continue
        worst = max(outside[side] for side in sides)
        yield Issue(
            f"{describe(obj)} is outside the safe area at the {' and '.join(sides)} "
            f"({worst:.0f} px into the {', '.join(sides)} margin)",
            _bbox(obj),
            (obj,),
            value=round(worst, 1),
            limit=round(tolerance, 1),
        )


@rule("text_overlap", default="error")
def text_overlap(ctx: StillContext, settings: TextOverlapRule) -> Iterator[Issue]:
    """Two texts overlap."""
    texts = [obj for obj in ctx.objects if is_text(obj)]
    for a, b in combinations(texts, 2):
        box = intersection(_bbox(a), _bbox(b))
        if box is None:
            continue
        smaller = min(area(_bbox(a)), area(_bbox(b)))
        fraction = area(box) / max(smaller, 1e-9)
        if fraction < settings.min_overlap:
            continue
        union = area(_bbox(a)) + area(_bbox(b)) - area(box)
        if a.get("text") == b.get("text") and area(box) / union > 0.9:
            continue  # the same text drawn twice in the same place looks like one
        first, second = sorted((a, b), key=lambda o: o["order"])
        yield Issue(
            f"{describe(second)} overlaps {describe(first)} ({fraction:.0%} of the smaller box)",
            box,
            (second, first),
            value=round(fraction, 3),
            limit=settings.min_overlap,
        )


#: RGB distance (0..255 scale) under which a pixel shows a given colour.
_COLOR_DISTANCE = 40.0
#: Shapes fainter than this on top of text do not hide it (a faint decoration).
_COVER_OPACITY = 0.3


def _core(box: Bbox) -> Bbox:
    """The middle of a text box (half its height, 60 % of its width): what a shape must reach to
    hide the text, rather than touch its edge."""
    x0, y0, x1, y1 = box
    mx, my = 0.2 * (x1 - x0), 0.25 * (y1 - y0)
    return (x0 + mx, y0 + my, x1 - mx, y1 - my)


def _shape_colors(shape: dict[str, Any], behind: str) -> list[np.ndarray]:
    """The colours (0..255) the shape's fill and stroke show over ``behind``."""
    colors = []
    for paint in (shape.get("fill"), shape.get("stroke")):
        if paint is not None and paint["opacity"] >= _COVER_OPACITY:
            seen = blend(hex_rgb(paint["color"]), hex_rgb(behind), min(float(paint["opacity"]), 1.0))
            colors.append(np.array(seen) * 255)
    return colors


def _covered(ctx: StillContext, shape: dict[str, Any], text: dict[str, Any]) -> float | None:
    """Fraction of the middle of ``text``'s box where ``shape`` (drawn later) shows, or ``None``.

    Boxes of groups and curves are much larger than what they draw, so this looks at the still's
    pixels: how many in the text's middle show the shape's colour (and not the text's own). A
    shape in the text's own colour (a strike-through) or the backdrop's cannot be told apart and
    is not reported. Images are opaque rectangles: their box is what they cover.
    """
    if _is_ancestor(shape["path"], text["path"]) or shape["opacity"] < _COVER_OPACITY:
        return None  # the text's own container (a label's box, a Code's background), a faint shape
    core = _core(_bbox(text))
    box = intersection(_bbox(shape), core)
    if box is None:
        return None
    if shape["kind"] == "image":
        return area(box) / max(area(core), 1e-9)
    behind = text.get("backdrop") or ctx.layout["background"]
    alpha = min(float(text["opacity"]), 1.0)
    ink = [np.array(blend(hex_rgb(c), hex_rgb(behind), alpha)) * 255 for c in text.get("colors", [])]
    back = np.array(hex_rgb(behind)) * 255
    paints = [p for p in _shape_colors(shape, behind) if _distance(p, [*ink, back]).min() >= _COLOR_DISTANCE]
    pixels = ctx.region(core)
    if not paints or pixels is None or not pixels.size:
        return None
    rgb = pixels.reshape(-1, 3).astype(np.float64)
    shows_shape = _distance(rgb, paints) < _COLOR_DISTANCE
    shows_text = _distance(rgb, ink) < _COLOR_DISTANCE if ink else np.zeros(len(rgb), dtype=bool)
    return float(np.mean(shows_shape & ~shows_text))


def _distance(rgb: np.ndarray, colors: list[np.ndarray]) -> np.ndarray:
    """RGB distance of each colour in ``rgb`` (N x 3, or one colour) to the nearest of ``colors``."""
    points = np.atleast_2d(rgb)
    return np.min(np.stack([np.linalg.norm(points - c, axis=1) for c in colors]), axis=0)


@rule("covered_text")
def covered_text(ctx: StillContext, settings: CoveredTextRule) -> Iterator[Issue]:
    """A shape or image is drawn on top of text."""
    texts = [obj for obj in ctx.objects if is_text(obj)]
    others = [obj for obj in ctx.objects if not is_text(obj)]
    for text in texts:
        for shape in others:
            if shape["order"] <= text["order"]:
                continue  # drawn first: a backdrop, plate or highlight band
            fraction = _covered(ctx, shape, text)
            if fraction is None or fraction < settings.min_covered:
                continue
            yield Issue(
                f"{describe(shape)} is drawn over {describe(text)} "
                f"({fraction:.0%} of the middle of the text's box shows it)",
                intersection(_bbox(shape), _bbox(text)),
                (text, shape),
                value=round(fraction, 3),
                limit=settings.min_covered,
            )


@rule("min_font")
def min_font(ctx: StillContext, settings: MinFontRule) -> Iterator[Issue]:
    """Text is too small for the output height."""
    short = ctx.short_side
    for obj in ctx.objects:
        if not is_text(obj) or not has_letters_or_digits(obj):
            continue
        size = cap_height(obj)
        if size <= 0 or size >= settings.min_size * short:
            continue
        error = size < settings.error_size * short
        limit = settings.error_size if error else settings.min_size
        yield Issue(
            f"{describe(obj)} is {size:.1f} px tall (cap height, {size / short:.2%} of the frame's "
            f"shorter side; minimum {limit:.2%} = {limit * short:.1f} px)",
            _bbox(obj),
            (obj,),
            severity="error" if error else "warning",
            value=round(size / short, 4),
            limit=limit,
        )


@rule("contrast")
def contrast(ctx: StillContext, settings: ContrastRule) -> Iterator[Issue]:
    """Text has too little contrast with what is behind it (WCAG ratio)."""
    for obj in ctx.objects:
        backdrop = obj.get("backdrop")
        if not is_text(obj) or not backdrop or not obj.get("colors") or not has_letters_or_digits(obj):
            continue
        if obj["kind"] == "code" and str(obj.get("text", "")).replace("\n", "").strip().isdigit():
            continue  # a listing's line numbers: dimmed on purpose, incidental (WCAG)
        behind = hex_rgb(backdrop)
        opacity = float(obj["opacity"])
        ratio, color = min(
            (contrast_ratio(blend(hex_rgb(c), behind, opacity), behind), c) for c in obj["colors"]
        )
        if opacity < 0.95:
            required, what = settings.dimmed_ratio, f"dimmed text (opacity {opacity:.2f})"
        elif cap_height(obj) >= settings.large_size * ctx.short_side:
            required, what = settings.large_ratio, "large text"
        else:
            required, what = settings.min_ratio, "text"
        if ratio >= required:
            continue
        seen = color if opacity >= 0.95 else f"{color} at {opacity:.2f} = {rgb_hex(blend(hex_rgb(color), behind, opacity))}"
        yield Issue(
            f"{describe(obj)} has contrast {ratio:.2f}:1 ({seen} on {backdrop}); "
            f"{what} needs {required:g}:1",
            _bbox(obj),
            (obj,),
            value=round(ratio, 2),
            limit=required,
            group=("colors", color, backdrop, round(opacity, 2)),
        )


def _words(text: str) -> int:
    return sum(1 for token in text.split() if any(ch.isalpha() for ch in token))


@rule("max_words")
def max_words(ctx: StillContext, settings: MaxWordsRule) -> Iterator[Issue]:
    """Too many words are on screen at once."""
    counted = [obj for obj in ctx.objects if obj["kind"] == "text" and _words(str(obj.get("text", "")))]
    total = sum(_words(str(obj["text"])) for obj in counted)
    if total <= settings.max_words:
        return
    boxes = np.array([_bbox(obj) for obj in counted])
    box = (float(boxes[:, 0].min()), float(boxes[:, 1].min()), float(boxes[:, 2].max()), float(boxes[:, 3].max()))
    yield Issue(
        f"{total} words on screen in {len(counted)} texts (at most {settings.max_words}); "
        "the narration should carry the detail",
        box,
        value=total,
        limit=settings.max_words,
    )
