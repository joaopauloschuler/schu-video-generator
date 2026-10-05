"""Theme-aware text helpers and generic drawing utilities (exported by ``vidgen.api``).

Colors and sizes accept theme token names (``"primary"``, ``"body"``) or literal values
(``"#FF0000"``, ``32``, a ``ManimColor``); tokens resolve against the current theme when the
function is called. These are generalised from the kphi3 video's ``common.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import numpy as np
from manim import NORMAL, Dot, Line, MarkupText, Mobject, Text, ValueTracker, VGroup, always_redraw

from vidgen.runtime import current_theme
from vidgen.theme import Theme

M = TypeVar("M", Text, MarkupText)


def resolve_color(color: Any, theme: Theme | None = None) -> Any:
    """Theme token or ``#hex`` string -> hex string; other values (``ManimColor``) pass through."""
    if isinstance(color, str):
        return (theme or current_theme()).color(color)
    return color


def styled(cls: type[M], theme: Theme, s: str, size: str | float, color: Any, weight: str, **kwargs: Any) -> M:
    """Build ``cls`` (``Text`` or ``MarkupText``) with the theme's font, size and color tokens."""
    kwargs.setdefault("font", theme.font)
    return cls(s, font_size=theme.size(size), color=resolve_color(color, theme), weight=weight, **kwargs)


def T(s: str, size: str | float = "body", color: Any = "text", weight: str = NORMAL, **kwargs: Any) -> Text:
    """``Text`` in the current theme: ``T("Hello", "title", "accent", weight=BOLD)``."""
    return styled(Text, current_theme(), s, size, color, weight, **kwargs)


def MT(s: str, size: str | float = "body", color: Any = "text", weight: str = NORMAL, **kwargs: Any) -> MarkupText:
    """``MarkupText`` (Pango markup) in the current theme: ``MT("10<sup>22</sup>", 96)``."""
    return styled(MarkupText, current_theme(), s, size, color, weight, **kwargs)


def column(n: int, x: float, gap: float, y0: float = 0.0, r: float = 0.08, color: Any = "text") -> VGroup:
    """``n`` dots stacked vertically at ``x``, ``gap`` apart, centered on ``y0`` (a layer of a net)."""
    c = resolve_color(color)
    dots = [Dot([x, y0 + ((n - 1) / 2 - i) * gap, 0], radius=r, color=c) for i in range(n)]
    return VGroup(*dots).set_z_index(3)


def edges(
    a: Sequence[Mobject],
    b: Sequence[Mobject],
    pairs: Sequence[tuple[int, int]],
    color: Any = "primary",
    width: float = 1.6,
    opacity: float = 0.65,
) -> VGroup:
    """Lines from ``a[i]`` to ``b[j]`` for each ``(i, j)`` in ``pairs``."""
    c = resolve_color(color)
    return VGroup(
        *[
            Line(a[i].get_center(), b[j].get_center(), stroke_width=width, color=c, stroke_opacity=opacity)
            for i, j in pairs
        ]
    )


def dense_pairs(n: int, m: int) -> list[tuple[int, int]]:
    """All ``(i, j)`` pairs: a fully connected ``n``-to-``m`` layer."""
    return [(i, j) for i in range(n) for j in range(m)]


def grouped_pairs(n: int, groups: int) -> list[tuple[int, int]]:
    """Pairs of a grouped layer: ``n`` units split into ``groups`` fully connected blocks."""
    s = n // groups
    return [(g * s + i, g * s + j) for g in range(groups) for i in range(s) for j in range(s)]


def counter(
    tracker: ValueTracker,
    fmt: str,
    size: str | float = "body",
    color: Any = "text",
    weight: str = NORMAL,
    anchor: Mobject | np.ndarray | Callable[[], Any] | None = None,
    edge: np.ndarray | None = None,
    buff: float = 0.15,
) -> Mobject:
    """Text redrawn from a ``ValueTracker`` every frame (no LaTeX needed).

    ``fmt`` is a ``str.format`` pattern (``"{:.0f}%"``). With ``anchor`` (a mobject, point or a
    callable returning one) the text is moved onto it, or placed next to it on ``edge``.
    """
    theme = current_theme()

    def make() -> Text:
        m = styled(Text, theme, fmt.format(tracker.get_value()), size, color, weight)
        if anchor is not None:
            target = anchor() if callable(anchor) else anchor
            if edge is None:
                m.move_to(target)
            else:
                m.next_to(target, edge, buff=buff)
        return m

    return always_redraw(make)
