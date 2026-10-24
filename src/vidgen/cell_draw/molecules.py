"""Drawing molecule glyphs with Manim (DESIGN.md §95.9): the renderer of
:mod:`vidgen.cellworld.glyphs` (whose geometry is in nm, without manim). Filled and stroked
Bézier outlines become ``VMobject``s, texts Pango ``MarkupText`` scaled to their height in nm;
colours come from the theme through :class:`~.base.CellColors`. The ``molecule`` scene draws
glyphs as they are (a fixed camera); the ``cell`` scene registers them as level-of-detail pieces
of its drawing (strokes kept in pixels as the camera zooms, details shown up close)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from manim import Mobject, VGroup, VMobject

from vidgen.cellworld import MOLECULES, Ellipse, molecule_glyph
from vidgen.cellworld.glyphs import ON, TEXT, Prim, place

from .base import RIM_PX, CellColors, curves_array, path_mobject

#: A text in markup and its height in scene units → a mobject (the scene's themed text).
TextMaker = Callable[[str, float], Mobject]
#: Dark ink for text on filled shapes (discs, helices) whatever the theme.
ON_INK = "#1E1E1E"


def fill_colour(colors: CellColors, hue: str, tone: str) -> str:
    """A prim's fill: ``solid`` the hue itself, ``fill`` paler, ``light`` paler still."""
    if tone == "fill":
        return colors.fill(hue, 0.6)
    if tone == "light":
        return colors.light(hue, 0.45)
    if tone == "ink":
        return colors.ink(hue)
    return colors.solid(hue)


def text_colour(colors: CellColors, hue: str | None) -> str:
    if hue in (None, TEXT):
        return colors.text
    if hue == ON:
        return ON_INK
    return colors.ink(hue) if not colors.dark else colors.light(hue, 0.25)


def prim_mobject(p: Prim, unit: float, origin: np.ndarray) -> VMobject:
    """The outline of a (non-text) prim in scene units: nm × ``unit`` from ``origin``."""
    return path_mobject(curves_array(p.curves), unit, origin)


def glyph_mobjects(prims: Sequence[Prim], colors: CellColors, unit: float, origin: np.ndarray, px_width: float,
                   make_text: TextMaker | None = None) -> VGroup:
    """A static drawing of ``prims`` (nm, already placed) at ``unit`` scene units per nm:
    strokes ``px`` pixels wide (``px_width``: Manim stroke width per pixel) or their true width
    in nm when wider; texts by ``make_text`` (left out without one). Back to front by ``z``."""
    out = VGroup()
    for p in sorted(prims, key=lambda q: q.z):
        if p.text:
            if make_text is None:
                continue
            mob = make_text(p.text, p.height * unit)
            mob.set_color(text_colour(colors, p.fill))
            mob.move_to(np.array([p.at[0] * unit, p.at[1] * unit, 0.0]) + origin)
            out.add(mob)
            continue
        mob = prim_mobject(p, unit, origin)
        mob.set_fill(fill_colour(colors, p.fill, p.tone) if p.fill else colors.background, opacity=1.0 if p.fill else 0.0)
        width = max(p.px * px_width, p.nm * unit * 100.0)
        stroke = colors.ink(p.stroke) if p.fill and p.stroke else fill_colour(colors, p.stroke, p.tone) if p.stroke else colors.text
        mob.set_stroke(stroke, width=width if p.stroke else 0.0, opacity=1.0 if p.stroke else 0.0)
        out.add(mob)
    return out


def glyph_pieces(d: object, prims: Sequence[Prim], feature: str, detail_feature: str) -> VGroup:
    """``prims`` (µm, placed in the world: of one or many molecules) as level-of-detail pieces
    of a cell drawing ``d``: shown with ``feature``, details with ``detail_feature`` as well;
    prims of one look are one piece (a hundred receptors are a few dozen mobjects); texts are
    left out (the view's labels name the parts)."""
    colors = d.colors  # type: ignore[attr-defined]
    looks: dict[tuple[object, ...], list[Prim]] = {}
    for p in prims:
        if not p.text:
            looks.setdefault((p.z, p.fill, p.tone, p.stroke, p.px, round(p.nm, 9), p.detail), []).append(p)
    out = VGroup()
    for (z, fill_hue, tone, stroke_hue, px, nm, detail), same in sorted(looks.items(), key=lambda item: item[0][0]):
        mob = d.curves([cv for p in same for cv in p.curves])  # type: ignore[attr-defined]
        which = f"{feature}&{detail_feature}" if detail else feature
        fill = fill_colour(colors, fill_hue, tone) if fill_hue else None   # type: ignore[arg-type]
        stroke = (colors.ink(stroke_hue) if fill_hue else fill_colour(colors, stroke_hue, tone)) if stroke_hue else None  # type: ignore[arg-type]
        out.add(d.piece(mob, which, fill=fill, stroke=stroke, px=px, true_um=nm or None))  # type: ignore[attr-defined]
    return out


def cell_molecules(d: object, kind_name: str, things: Sequence[object]) -> VGroup:
    """Molecules of one entry in a cell drawing: dots at their real size from afar, their glyphs
    (oriented in their membrane) once they are a few pixels across, details up close."""
    hue = MOLECULES[kind_name].hue
    colors = d.colors  # type: ignore[attr-defined]
    dots = d.piece(d.path([Ellipse(t.center[0], t.center[1], t.size / 2, t.size / 2) for t in things]),  # type: ignore[attr-defined]
                   "particles&!molecules", fill=colors.solid(hue), stroke=colors.solid(hue), px=RIM_PX)
    prims: list[Prim] = []
    glyphs: dict[object, object] = {}
    for t in things:
        spec = t.option("molecule")  # type: ignore[attr-defined]
        if spec not in glyphs:
            glyphs[spec] = molecule_glyph(spec)
        prims += place(glyphs[spec], t.center, t.angle, 0.001)  # type: ignore[arg-type,attr-defined]
    return VGroup(dots, glyph_pieces(d, prims, "molecules", "molecule_detail"))


__all__ = ["ON_INK", "TextMaker", "cell_molecules", "fill_colour", "glyph_mobjects", "glyph_pieces", "prim_mobject", "text_colour"]
