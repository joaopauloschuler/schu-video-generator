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

from vidgen.fonts import register_bundled_fonts
from vidgen.runtime import current_theme
from vidgen.theme import Theme

register_bundled_fonts()  # Pango only sees fonts registered before the first text is laid out

M = TypeVar("M", Text, MarkupText)


def resolve_color(color: Any, theme: Theme | None = None) -> Any:
    """Theme token or ``#hex`` string -> hex string; other values (``ManimColor``) pass through."""
    if isinstance(color, str):
        return (theme or current_theme()).color(color)
    return color


def styled(
    cls: type[M], theme: Theme, s: str, size: str | float, color: Any, weight: str, *, role: str | None = None, **kwargs: Any
) -> M:
    """Build ``cls`` (``Text`` or ``MarkupText``) with the theme's font, size and color tokens.

    The font is ``font`` if given, else the theme's family for the font ``role`` (``heading``,
    ``quote``, ``code``...; :meth:`Theme.font_for`), else the theme font."""
    if not kwargs.get("font"):
        kwargs["font"] = theme.font_for(role) if role else theme.font
    return cls(s, font_size=theme.size(size), color=resolve_color(color, theme), weight=weight, **kwargs)


def T(
    s: str, size: str | float = "body", color: Any = "text", weight: str = NORMAL, *, role: str | None = None, **kwargs: Any
) -> Text:
    """``Text`` in the current theme: ``T("Hello", "title", "accent", weight=BOLD)``;
    ``role="heading"`` uses the theme's heading family (``font=`` names a family directly)."""
    return styled(Text, current_theme(), s, size, color, weight, role=role, **kwargs)


def MT(
    s: str, size: str | float = "body", color: Any = "text", weight: str = NORMAL, *, role: str | None = None, **kwargs: Any
) -> MarkupText:
    """``MarkupText`` (Pango markup) in the current theme: ``MT("10<sup>22</sup>", 96)``;
    ``role`` as for :func:`T`."""
    return styled(MarkupText, current_theme(), s, size, color, weight, role=role, **kwargs)


def column(
    n: int,
    x: float,
    gap: float,
    y0: float = 0.0,
    r: float = 0.08,
    color: Any = "text",
    *,
    horizontal: bool = False,
    skip: int | None = None,
) -> VGroup:
    """``n`` dots stacked vertically at ``x``, ``gap`` apart, centered on ``y0`` (a layer of a net).

    With ``horizontal`` the dots run left to right along ``y0``, centered on ``x``. ``skip``
    leaves an empty slot at that position (``n`` dots over ``n + 1`` slots), e.g. for an
    ellipsis in a layer that shows only some of its units."""
    c = resolve_color(color)
    slots = [k for k in range(n + (skip is not None)) if k != skip]
    middle = (len(slots) + (skip is not None) - 1) / 2
    if horizontal:
        points = [[x + (k - middle) * gap, y0, 0] for k in slots]
    else:
        points = [[x, y0 + (middle - k) * gap, 0] for k in slots]
    return VGroup(*[Dot(point, radius=r, color=c) for point in points]).set_z_index(3)


def edges(
    a: Sequence[Mobject],
    b: Sequence[Mobject],
    pairs: Sequence[tuple[int, int]],
    color: Any = "primary",
    width: float = 1.6,
    opacity: float = 0.65,
    *,
    colors: Sequence[Any] | None = None,
    shorten: float = 0.0,
) -> VGroup:
    """Lines from ``a[i]`` to ``b[j]`` for each ``(i, j)`` in ``pairs``.

    ``colors`` gives each line its own colour (one per pair; default ``color`` for all);
    ``shorten`` trims that much off both ends (lines from the rim of dots of that radius)."""
    lines = []
    for k, (i, j) in enumerate(pairs):
        start, end = np.array(a[i].get_center()), np.array(b[j].get_center())
        if shorten > 0:
            length = float(np.linalg.norm(end - start))
            if length > 2 * shorten:
                step = (end - start) / length * shorten
                start, end = start + step, end - step
        c = resolve_color(colors[k] if colors is not None else color)
        lines.append(Line(start, end, stroke_width=width, color=c, stroke_opacity=opacity))
    return VGroup(*lines)


def dense_pairs(n: int, m: int) -> list[tuple[int, int]]:
    """All ``(i, j)`` pairs: a fully connected ``n``-to-``m`` layer."""
    return [(i, j) for i in range(n) for j in range(m)]


def group_bounds(n: int, groups: int) -> list[int]:
    """Where each of ``groups`` near-equal blocks of ``n`` units starts, plus ``n`` at the end."""
    groups = max(1, min(groups, n))
    return [round(g * n / groups) for g in range(groups + 1)]


def grouped_pairs(n: int, groups: int, m: int | None = None) -> list[tuple[int, int]]:
    """Pairs of a grouped layer: ``n`` units split into ``groups`` fully connected blocks.

    With ``m`` the second layer has ``m`` units (split into as many blocks; block ``g`` of the
    first layer connects to block ``g`` of the second). Blocks are near-equal when ``groups``
    does not divide a layer."""
    a = group_bounds(n, groups)
    b = group_bounds(n if m is None else m, groups)
    return [(i, j) for g in range(len(a) - 1) for i in range(a[g], a[g + 1]) for j in range(b[g], b[g + 1])]


def sparse_pairs(n: int, m: int, ratio: float, seed: int = 0) -> list[tuple[int, int]]:
    """About ``ratio`` of all ``n x m`` pairs, chosen pseudo-randomly but reproducibly
    (``seed``), with every unit of both layers keeping at least one connection. Sorted."""
    rng = np.random.default_rng(seed)
    chosen = {(i, j) for i in range(n) for j in range(m) if rng.random() < ratio}
    for i in range(n):
        if not any((i, j) in chosen for j in range(m)):
            chosen.add((i, int(rng.integers(m))))
    for j in range(m):
        if not any((i, j) in chosen for i in range(n)):
            chosen.add((int(rng.integers(n)), j))
    return sorted(chosen)


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
