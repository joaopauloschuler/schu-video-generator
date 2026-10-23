"""Drawings of filaments and motors (DESIGN.md §95.9): microtubules (25 nm, their − end at the
centrosome and + end out, marked when large enough), actin (7 nm: the cortex under the plasma
membrane, stress fibers between focal adhesions with myosin II along them, single filaments),
intermediate filaments (10 nm), a bacterium's flagella (with the basal body and hook in its
envelope) and pili; kinesin, dynein and myosin on their tracks, facing the way they walk."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from manim import VGroup, VMobject

from vidgen.cellworld import KINDS, Capsule, Ellipse, Placed, Polyline, Region
from vidgen.cellworld.curves import Cubic, arc, line, smooth

from .base import RIM_PX
from .closeup import filament_detail

if TYPE_CHECKING:
    from .drawing import CellDrawing

#: The level-of-detail feature that shows each kind as a line, and its least width (px).
LINE_FEATURE = {"microtubule": ("mt_lines", 0.7), "actin_filament": ("actin_lines", 0.5), "actin_cortex": ("actin_lines", 0.45),
                "stress_fiber": ("actin_lines", 0.5), "intermediate_filament": ("if_lines", 0.6), "pilus": ("actin_lines", 0.6),
                "flagellum": (None, 1.0)}


def _curves(line_: Polyline) -> list[Cubic]:
    pts = list(line_.points)
    return smooth(pts) if len(pts) > 2 else [line(pts[0], pts[1])]


def filaments(d: "CellDrawing", kind: str, things: list[Placed]) -> VGroup:
    """The filaments of an entry."""
    hue = KINDS[kind].hue
    lines = [s for t in things for s in t.footprint if isinstance(s, Polyline)]
    feature, least = LINE_FEATURE.get(kind, ("mt_lines", 0.6))
    parts: list[VMobject] = []
    if kind == "actin_cortex":
        thickness = things[0].option("thickness", 0.3)
        band = Region.of(d.world.cell).minus(d.world.cell.inset(thickness))  # type: ignore[attr-defined]
        parts.append(d.piece(d.curves(band.curves()), None, fill=d.colors.fill(hue, 0.16)))
    if kind == "stress_fiber":
        parts += _stress_fibers(d, lines, hue)
    else:
        width = lines[0].width if lines else 0.01
        curves = [c for l in lines for c in _curves(l)]
        parts.append(d.piece(d.curves(curves), feature, stroke=d.colors.solid(hue), px=least, true_um=width))
    if kind == "microtubule":
        parts.append(_ends(d, things, hue))
    if kind == "flagellum":
        parts.append(_basal_bodies(d, things, hue))
    if d.closeups:
        parts.append(filament_detail(d, kind, lines, hue))
    return VGroup(*parts)


def _ends(d: "CellDrawing", things: list[Placed], hue: str) -> VMobject:
    """``+`` beyond each microtubule's plus end and ``−`` beside its minus end."""
    bars: list[object] = []
    for t in things:
        line_ = t.footprint[0]
        assert isinstance(line_, Polyline)
        for end, sign in ((line_.points[-1], 1), (line_.points[0], -1)):
            p, (dx, dy) = line_.at(line_.length if sign > 0 else 0.0)
            c = (end[0] + dx * 0.09 * sign - dy * (0.0 if sign > 0 else 0.07), end[1] + dy * 0.09 * sign + dx * (0.0 if sign > 0 else 0.07))
            bars.append(Capsule(c[0], c[1], 0.07, 0.016, 0.0))
            if sign > 0:
                bars.append(Capsule(c[0], c[1], 0.07, 0.016, math.pi / 2))
    return d.piece(d.path(bars), "fine", fill=d.colors.ink(hue))


def _stress_fibers(d: "CellDrawing", lines: list[Polyline], hue: str) -> list[VMobject]:
    """A bundle (its parallel actin filaments up close), myosin II along it, a focal adhesion at
    each end."""
    bands, threads, myosin, plaques = [], [], [], []
    for l in lines:
        a, b = l.points[0], l.points[-1]
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        length = math.dist(a, b)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        bands.append(Capsule(mid[0], mid[1], length, l.width, angle))
        nx, ny = -math.sin(angle), math.cos(angle)
        for k in range(7):
            off = (k - 3) / 3 * l.width * 0.4
            threads.append(line((a[0] + nx * off, a[1] + ny * off), (b[0] + nx * off, b[1] + ny * off)))
        steps = int(length / 0.8)
        for k in range(1, steps):
            p = (a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps)
            myosin.append(Capsule(p[0], p[1], 0.3, 0.05, angle))
        for end in (a, b):
            plaques.append(Ellipse(end[0], end[1], 0.22, 0.09, angle + math.pi / 2))
    purple = KINDS["myosin"].hue
    return [d.piece(d.path(bands), None, fill=d.colors.fill(hue, 0.45)),
            d.piece(d.curves(threads), "actin_lines", stroke=d.colors.solid(hue), px=0.5, true_um=0.007),
            d.piece(d.path(myosin), "fine", fill=d.colors.fill(purple, 0.7)),
            d.piece(d.path(plaques), None, fill=d.colors.fill("#7C6A5A", 0.75))]


def _basal_bodies(d: "CellDrawing", things: list[Placed], hue: str) -> VGroup:
    """Each flagellum's basal body (a rotary motor: rings in the membranes, a rod through) and
    its hook."""
    rings, rods = [], []
    hooks: list[Cubic] = []
    depth = 0.0
    if d.world.envelope:
        depth = d.world.envelope[0][1].bounds()[3] - d.world.cell.bounds()[3]
    for t in things:
        base = t.option("base", t.center)
        nx, ny = t.option("normal", (1.0, 0.0))
        angle = math.atan2(ny, nx)
        rods.append(Capsule(base[0] - nx * depth / 2, base[1] - ny * depth / 2, depth + 0.035, 0.009, angle))
        # C ring (cytoplasm), MS ring (inner membrane); a Gram-negative's P ring (peptidoglycan) and L ring (outer membrane)
        levels = ((-depth - 0.014, 0.045), (-depth, 0.028)) + (((-depth * 0.38, 0.022), (0.0, 0.022)) if d.world.gram == "negative" else ())
        for f, w in levels:
            rings.append(Capsule(base[0] + nx * f, base[1] + ny * f, w, 0.008, angle + math.pi / 2))
        line_ = t.footprint[0]
        assert isinstance(line_, Polyline)
        hooks += smooth([line_.at(s)[0] for s in (0.0, 0.02, 0.04, 0.055)])
    ink = d.colors.ink(hue)
    return VGroup(d.piece(d.path(rods), "fine", fill=d.colors.solid(hue)),
                  d.piece(d.path(rings), "fine", fill=d.colors.fill(hue, 0.8), stroke=ink, px=0.6),
                  d.piece(d.curves(hooks), "fine", stroke=ink, px=1.0, true_um=0.018))


def motors(d: "CellDrawing", kind: str, things: list[Placed]) -> VGroup:
    """Motor proteins: a dot from afar; up close kinesin's two heads on the microtubule with
    its stalk, dynein's two ring-shaped motor domains on their stalks, myosin V's two heads
    36 nm apart on actin with their lever arms; an arrow the way it walks; a cargo vesicle."""
    hue = KINDS[kind].hue
    dots = d.piece(d.path([Ellipse(t.center[0], t.center[1], t.size / 2, t.size * 0.22, t.angle) for t in things]),
                   "particles&!particle_detail", fill=d.colors.solid(hue))
    heads, rings, cargo = [], [], []
    stalks: list[Cubic] = []
    arrows: list[Cubic] = []
    for t in things:
        base = t.option("base", t.center)
        rf = t.option("filament_width", 0.025) / 2
        fx, fy = math.cos(t.facing or 0.0), math.sin(t.facing or 0.0)
        nx, ny = t.normal or (-fy, fx)

        def at(a: float, b: float) -> tuple[float, float]:
            return (base[0] + fx * a + nx * (rf + b), base[1] + fy * a + ny * (rf + b))

        angle = math.atan2(fy, fx)
        top = 0.06 if kind == "kinesin" else 0.045 if kind == "dynein" else 0.032
        if kind == "kinesin":
            for a in (-0.0045, 0.0045):
                heads.append(Ellipse(*at(a, 0.003), 0.0042, 0.0028, angle))
            stalks += smooth([at(-0.0045, 0.006), at(0.0, 0.012), at(-0.004, 0.03), at(-0.01, top)])
            stalks += [line(at(0.0045, 0.006), at(0.0, 0.012))]
            heads.append(Ellipse(*at(-0.011, top + 0.004), 0.004, 0.0055, angle))
        elif kind == "dynein":
            for a in (-0.006, 0.006):
                rings.append(Ellipse(*at(a, 0.019), 0.0068, 0.0068))
                stalks.append(line(at(a * 1.4, 0.0005), at(a, 0.0125)))
            stalks += smooth([at(-0.006, 0.026), at(-0.002, 0.034), at(0.004, top)])
            stalks += [line(at(0.006, 0.026), at(-0.002, 0.034))]
        else:
            for a in (-0.018, 0.018):
                heads.append(Ellipse(*at(a, 0.003), 0.0045, 0.003, angle + 0.4 * (1 if a > 0 else -1)))
                stalks.append(line(at(a, 0.006), at(0.0, 0.022)))
            stalks.append(line(at(0.0, 0.022), at(0.0, top)))
        # an arrow along the track, ahead of the heads: the way the motor walks
        lead = 0.03 if kind == "myosin" else 0.016
        a, b = at(lead, 0.008), at(lead + 0.014, 0.008)
        arrows += [line(a, b), line(b, (b[0] - fx * 0.005 + nx * 0.004, b[1] - fy * 0.005 + ny * 0.004)),
                   line(b, (b[0] - fx * 0.005 - nx * 0.004, b[1] - fy * 0.005 - ny * 0.004))]
        if t.option("cargo"):
            r = 0.03
            cargo.append(Ellipse(*at(-0.012, top + r + 0.004), r, r))
    ink = d.colors.ink(hue)
    parts: list[VMobject] = [dots]
    if heads:
        parts.append(d.piece(d.path(heads), "particle_detail", fill=d.colors.solid(hue), stroke=ink, px=RIM_PX))
    if rings:
        spokes: list[Cubic] = []
        for r in rings:
            for k in range(6):
                a = 2 * math.pi * k / 6
                spokes.append(line((r.cx + 0.002 * math.cos(a), r.cy + 0.002 * math.sin(a)), (r.cx + r.a * math.cos(a), r.cy + r.a * math.sin(a))))
        parts.append(d.piece(d.path(rings), "particle_detail", fill=d.colors.solid(hue), stroke=ink, px=RIM_PX))
        parts.append(d.piece(d.curves(spokes), "particle_detail", stroke=ink, px=0.7))
    parts.append(d.piece(d.curves(stalks), "particle_detail", stroke=d.colors.solid(hue), px=1.2, true_um=0.002))
    parts.append(d.piece(d.curves(arrows), "particle_detail", stroke=d.colors.text, px=1.6, true_um=0.0012))
    if cargo:
        vesicle = KINDS["vesicle"].hue
        parts.append(d.piece(d.path(cargo), "particle_detail", fill=d.colors.fill(vesicle, 0.45), stroke=d.colors.ink(vesicle), px=1.0,
                             true_um=0.005))
        parts.append(d.piece(d.curves([c for e in cargo for c in arc(e.cx, e.cy, e.a, 0, 2 * math.pi)]), "!particle_detail&particles",
                             stroke=d.colors.ink(vesicle), px=0.6))
    return VGroup(*parts)


__all__ = ["filaments", "motors"]
