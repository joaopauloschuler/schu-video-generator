"""Fast live text for the ``orbit`` scene (Step 236): a readout such as ``t = 82.2 d`` changes on
almost every frame, and building a manim ``Text`` for each new string (Pango → SVG → parse) cost
tens of milliseconds and about 0.3 MB that the panel's caches kept — a 47 s scene at 1080p ran out
of memory. :class:`LiveText` lays out a string once per *shape* (its digits written as 0: ``t =
00.0 d``) with ``Text`` and draws the real digits into it from glyphs rendered once, moving the
following glyphs by the digits' advances and kerning (measured once per pair). Glyphs outside the
digits keep the shape's own (contextual forms included); the result matches ``Text`` to well
under a pixel (tested). A string the shape cannot carry (a glyph count that differs from its
characters) is drawn by ``Text`` itself."""

from __future__ import annotations

from typing import Any

import numpy as np
from manim import VGroup, VMobject

from vidgen.api import *

DIGITS = "0123456789"
#: A capital on each side isolates a glyph or a pair when measuring (its left edge is a fixed
#: distance from its pen position).
_SEP = "H"
#: Shapes and plain texts kept per size (oldest dropped first).
CACHE_LIMIT = 400


def _left(m: Any) -> float:
    return float(np.min(m.points[:, 0]))


def _bottom(m: Any) -> float:
    return float(np.min(m.points[:, 1]))


class LiveText:
    """Texts of one size and colour in the theme's chart font, built from cached glyphs.
    ``text(s)`` gives a fresh ``VGroup`` of glyphs (like ``plot_draw.label_text(s)``, centred at
    the origin); ``size_of(s)`` its width and height without building it."""

    def __init__(self, theme: Any, size: float, color: Any) -> None:
        self.theme, self.size, self.color = theme, size, color
        self._shapes: dict[str, tuple[Any, list[int]] | None] = {}
        self._digits: dict[str, tuple[np.ndarray, float, float, float]] = {}   # points (pen origin at 0), advance, left bearing, bottom
        self._kern: dict[tuple[str, str], float] = {}
        self._advances: dict[str, float] = {}
        self._sep_advance: float | None = None

    def _render(self, s: str) -> Any:
        return plot_draw.label_text(s, size=self.size, color=self.color, theme=self.theme)

    # ----- measuring -----------------------------------------------------------------------------

    def _sep(self) -> float:
        if self._sep_advance is None:
            m = self._render(_SEP * 2)
            self._sep_advance = _left(m[1]) - _left(m[0])
        return self._sep_advance

    def _digit(self, d: str) -> tuple[np.ndarray, float, float, float]:
        if d not in self._digits:
            m = self._render(_SEP + d + _SEP)
            first, glyph, last = m.submobjects
            origin = _left(first) + self._sep()
            pts = glyph.points - np.array([origin, _bottom(first), 0.0])
            self._digits[d] = (pts, _left(last) - _left(first) - self._sep(), _left(glyph) - origin, _bottom(glyph) - _bottom(first))
        return self._digits[d]

    def _pair(self, a: str, b: str) -> float:
        """The kerning between ``a`` and ``b`` (0 for most pairs)."""
        if (a, b) not in self._kern:
            # a digit's pairs are measured ten at a time: H a 0 H a 1 H ... (each H-to-H step is
            # the separator, the two advances and the pair's kerning)
            pairs = [(a, d) for d in DIGITS] if b in DIGITS else [(d, b) for d in DIGITS] if a in DIGITS else [(a, b)]
            pairs = [p for p in pairs if p not in self._kern] or [(a, b)]
            s = _SEP + "".join(x + y + _SEP for x, y in pairs)
            m = self._render(s)
            seps, k = [], 0
            for c in s:
                if c.isspace():
                    continue
                if c == _SEP:
                    seps.append(k)
                k += 1
            if len(m.submobjects) != k or len(seps) != len(pairs) + 1:   # glyphs not one per character: one pair alone
                m = self._render(_SEP + a + b + _SEP)
                pairs, seps = [(a, b)], [0, len(m.submobjects) - 1]
            for n, (x, y) in enumerate(pairs):
                step = _left(m[seps[n + 1]]) - _left(m[seps[n]])
                self._kern[x, y] = step - self._sep() - self._advance(x) - self._advance(y)
        return self._kern[a, b]

    def _advance(self, c: str) -> float:
        if c in DIGITS:
            return self._digit(c)[1]
        if c not in self._advances:
            m = self._render(_SEP + c + _SEP)
            self._advances[c] = _left(m[-1]) - _left(m[0]) - self._sep()
        return self._advances[c]

    # ----- building ------------------------------------------------------------------------------

    def _shape(self, s: str) -> tuple[Any, list[int]] | None:
        """The text laid out with its digits as 0 and, per character, the index of its glyph
        (-1: a space); ``None`` when glyphs and characters do not pair up."""
        key = "".join("0" if c in DIGITS else c for c in s)
        if key not in self._shapes:
            if len(self._shapes) >= CACHE_LIMIT:
                del self._shapes[next(iter(self._shapes))]
            m = self._render(key)
            index, k = [], 0
            for c in key:
                if c.isspace():
                    index.append(-1)
                else:
                    index.append(k)
                    k += 1
            self._shapes[key] = (m, index) if k == len(m.submobjects) else None
        return self._shapes[key]

    def text(self, s: str) -> VGroup:
        """``s`` as glyphs, centred at the origin (as ``Text``)."""
        shape = self._shape(s)
        if shape is None or not any(c in DIGITS for c in s):
            m = self._render(s) if shape is None else shape[0]
            return VGroup(*[_bare(g, g.points) for g in m.submobjects]).move_to([0.0, 0.0, 0.0])
        m, index = shape
        t = "".join("0" if c in DIGITS else c for c in s)
        glyphs = []
        shift = 0.0   # how far this glyph moves from its place in the shape
        zero = self._digit("0")
        for j, c in enumerate(s):
            k = index[j]
            if k >= 0:
                g = m.submobjects[k]
                if c != t[j]:   # a digit drawn where the shape has its 0 (same pen position and baseline)
                    pts = self._digit(c)[0]
                    glyphs.append(_bare(g, pts + np.array([_left(g) - zero[2] + shift, _bottom(g) - zero[3], 0.0])))
                else:
                    glyphs.append(_bare(g, g.points + np.array([shift, 0.0, 0.0])))
            if j + 1 < len(s) and (c != t[j] or s[j + 1] != t[j + 1]):   # the pen step to the next character changes
                shift += self._advance(c) - self._advance(t[j]) + self._pair(c, s[j + 1]) - self._pair(t[j], t[j + 1])
        return VGroup(*glyphs).move_to([0.0, 0.0, 0.0])

    def size_of(self, s: str) -> tuple[float, float]:
        """Width and height of :meth:`text` ``(s)``."""
        g = self.text(s)
        return float(g.width), float(g.height)


def _bare(glyph: Any, points: np.ndarray) -> VMobject:
    """A plain ``VMobject`` with ``glyph``'s style and ``points`` (no SVG path kept: light to
    copy and to hold)."""
    out = VMobject()
    out.points = np.array(points, dtype=float)
    out.fill_rgbas = glyph.fill_rgbas.copy()
    out.stroke_rgbas = glyph.stroke_rgbas.copy()
    out.background_stroke_rgbas = glyph.background_stroke_rgbas.copy()
    out.stroke_width = glyph.stroke_width
    out.background_stroke_width = glyph.background_stroke_width
    return out


__all__ = ["LiveText"]
