"""Characters drawn as holograms (DESIGN.md §100.3): a translucent figure in one glowing colour.

Every part keeps its shape; its colours are mapped through the hologram's colour by their
lightness (:func:`hologram_fill`): light cloth and skin glow in it, dark ink (eyes, brows, mouth)
becomes a deep shade of it, so the face still reads. Fills become translucent (``opacity``),
outlines a bright, nearly white tint of the colour. The stage leaves a hologram out of its light
grade (:func:`unmark_lit`): it shines the same by day and at night.
"""

from __future__ import annotations

from manim import ManimColor, Mobject, VMobject

from vidgen.cartoon.shading import LIT

#: The default colour and opacity (``hologram: true``).
HOLOGRAM_COLOR = "#5FD8FF"
HOLOGRAM_OPACITY = 0.6
#: The darkest and brightest share of the colour a part's lightness maps to.
DARK_SHARE = 0.28
BRIGHT_SHARE = 1.15
#: How far the outlines go towards white.
EDGE_WHITE = 0.55
#: The outlines' opacity (a share of the drawn one).
EDGE_OPACITY = 0.95
#: The attribute a hologram character carries: its (colour, opacity).
HOLOGRAM_ATTRIBUTE = "hologram"


def _rgb(color: str) -> tuple[float, float, float]:
    r, g, b = ManimColor(color).to_rgb()[:3]
    return float(r), float(g), float(b)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(min(max(c, 0.0), 1.0) * 255):02X}" for c in rgb)


def lightness(color: str) -> float:
    """Relative lightness of ``color`` (0 black .. 1 white; Rec. 709 weights)."""
    r, g, b = _rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hologram_fill(original: str, tint: str) -> str:
    """``original`` seen through a hologram of colour ``tint``: the tint scaled by the original's
    lightness, from :data:`DARK_SHARE` (black) to :data:`BRIGHT_SHARE` (white), clipped."""
    share = DARK_SHARE + (BRIGHT_SHARE - DARK_SHARE) * lightness(original)
    return _hex(tuple(c * share for c in _rgb(tint)))   # type: ignore[arg-type]


def hologram_edge(tint: str) -> str:
    """The outline colour of a hologram of colour ``tint``: the tint :data:`EDGE_WHITE` of the
    way to white."""
    return _hex(tuple(c + (1.0 - c) * EDGE_WHITE for c in _rgb(tint)))   # type: ignore[arg-type]


def apply_hologram(figure: Mobject, color: str = HOLOGRAM_COLOR, opacity: float = HOLOGRAM_OPACITY) -> Mobject:
    """Draw ``figure`` (a character, every shape it may show) as a hologram of ``color`` (a hex)
    and fill ``opacity``; marks it with :data:`HOLOGRAM_ATTRIBUTE`. Returns it."""
    edge = hologram_edge(color)
    for member in figure.get_family():
        if not isinstance(member, VMobject):
            continue
        fill_opacity = float(member.get_fill_opacity())
        if fill_opacity > 0:
            member.set_fill(hologram_fill(member.get_fill_color().to_hex(), color), opacity=fill_opacity * opacity, family=False)
        stroke_opacity = float(member.get_stroke_opacity())
        if stroke_opacity > 0 and member.get_stroke_width() > 0:
            member.set_stroke(edge, opacity=stroke_opacity * EDGE_OPACITY, family=False)
    setattr(figure, HOLOGRAM_ATTRIBUTE, (color, opacity))
    return figure


def is_hologram(figure: Mobject) -> bool:
    """Whether ``figure`` was drawn by :func:`apply_hologram`."""
    return getattr(figure, HOLOGRAM_ATTRIBUTE, None) is not None


def unmark_lit(figure: Mobject) -> None:
    """Leave ``figure`` out of the stage's light grade (it glows the same in any light)."""
    for member in figure.get_family():
        setattr(member, LIT, False)


__all__ = [
    "BRIGHT_SHARE",
    "DARK_SHARE",
    "EDGE_OPACITY",
    "EDGE_WHITE",
    "HOLOGRAM_ATTRIBUTE",
    "HOLOGRAM_COLOR",
    "HOLOGRAM_OPACITY",
    "apply_hologram",
    "hologram_edge",
    "hologram_fill",
    "is_hologram",
    "lightness",
    "unmark_lit",
]
