"""Cartoon title cards (the ``card`` scene, DESIGN.md §69.46) without manim: where the text and
the frame go, the burst's rays, and the colours of the bold outlined text.

Sizes are in Manim units (the frame's shorter side is 8); angles in radians.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from vidgen.config import CHARACTER_INK
from vidgen.lint.color import blend, contrast_ratio, hex_rgb, rgb_hex

#: The looks of a card: rays turning behind the text, a double frame round it, or the colour alone.
CARD_STYLES = ("burst", "frame", "plain")
#: Rays of a burst (half of them in the lighter tone) and how far towards white that tone is.
BURST_RAYS = 18
RAY_LIGHTEN = 0.22
#: How fast a burst turns (radians per second).
BURST_SPIN = 0.12
#: The outlined text's two inks: the fill is the one that reads better on the card, the outline the other.
CARD_WHITE = "#FFFFFF"
CARD_INK = CHARACTER_INK
#: The outline's thickness outside the letters, as a share of the cap height.
OUTLINE_SHARE = 0.09
#: Manim's stroke width per unit of length (Cairo draws a width of ``w`` as ``w / 100`` units).
STROKE_PER_UNIT = 100.0
#: The frame (style ``frame``): inset from the edges and gap between its two lines (shares of the
#: frame's shorter side), its corner radius (share of its inner line's shorter side).
FRAME_INSET = 0.05
FRAME_GAP = 0.025
FRAME_CORNER = 0.08


@dataclass(frozen=True)
class CardLayout:
    """Where a card's parts go in a ``width`` x ``height`` frame (Manim units, centred at the
    origin): the box the text fits in (``text_width`` x ``text_height``), the subtitle's box
    below it after ``gap``, the frame's outer and inner rectangles (``None`` without a frame) and
    the radius of a burst that covers the whole frame."""

    text_width: float
    text_height: float
    subtitle_width: float
    subtitle_height: float
    gap: float
    frame_outer: tuple[float, float] | None
    frame_inner: tuple[float, float] | None
    burst_radius: float


def card_layout(width: float, height: float, *, style: str, subtitle: bool) -> CardLayout:
    """The :class:`CardLayout` of a card of ``style`` (:data:`CARD_STYLES`) in a frame of that
    size, with or without a ``subtitle``. The text gets most of the room; inside a frame it keeps
    clear of the frame's lines."""
    if style not in CARD_STYLES:
        raise ValueError(f"unknown card style {style!r} (styles: {', '.join(CARD_STYLES)})")
    short = min(width, height)
    portrait = height > width
    outer = inner = None
    room_w, room_h = width - 0.16 * short, height - 0.16 * short
    if style == "frame":
        inset, gap = FRAME_INSET * short, FRAME_GAP * short
        outer = (width - 2 * inset, height - 2 * inset)
        inner = (outer[0] - 2 * gap, outer[1] - 2 * gap)
        room_w, room_h = inner[0] - 0.12 * short, inner[1] - 0.12 * short
    text_width = room_w * (0.9 if portrait else 0.8)
    text_height = room_h * (0.36 if subtitle else 0.46)
    return CardLayout(
        text_width=text_width,
        text_height=text_height,
        subtitle_width=text_width,
        subtitle_height=room_h * 0.14 if subtitle else 0.0,
        gap=0.05 * short if subtitle else 0.0,
        frame_outer=outer,
        frame_inner=inner,
        burst_radius=math.hypot(width, height) / 2 * 1.02,
    )


def burst_ray_color(color: str, share: float = RAY_LIGHTEN) -> str:
    """``color`` moved ``share`` of the way towards white (a burst's lighter rays)."""
    return rgb_hex(blend((1.0, 1.0, 1.0), hex_rgb(color), share))


def card_text_inks(*backgrounds: str) -> tuple[str, str]:
    """``(fill, outline)`` of a card's text over ``backgrounds`` (the card's colour and its
    lighter rays): the fill is white or the ink, whichever keeps the higher contrast with every
    background; the outline is the other one."""
    def worst(ink: str) -> float:
        return min(contrast_ratio(hex_rgb(ink), hex_rgb(b)) for b in backgrounds)

    if worst(CARD_WHITE) >= worst(CARD_INK):
        return CARD_WHITE, CARD_INK
    return CARD_INK, CARD_WHITE


def card_outline_width(cap_height: float) -> float:
    """Manim stroke width of the outline drawn behind letters of ``cap_height`` units: the
    stroke is centred on the letters' edge and the fill hides its inner half, so it is twice the
    :data:`OUTLINE_SHARE` that shows."""
    return 2.0 * OUTLINE_SHARE * cap_height * STROKE_PER_UNIT


def burst_rays(radius: float, turn: float = 0.0, count: int = BURST_RAYS) -> list[list[tuple[float, float]]]:
    """The lighter rays of a burst of ``count`` equal rays (every other one) about the origin,
    turned by ``turn``: each a triangle (the centre and two points ``radius`` away)."""
    if count < 4 or count % 2:
        raise ValueError(f"a burst needs an even number of rays, at least 4 (not {count})")
    step = 2.0 * math.pi / count
    rays = []
    for k in range(0, count, 2):
        a0, a1 = turn + k * step, turn + (k + 1) * step
        rays.append([(0.0, 0.0), (radius * math.cos(a0), radius * math.sin(a0)), (radius * math.cos(a1), radius * math.sin(a1))])
    return rays
