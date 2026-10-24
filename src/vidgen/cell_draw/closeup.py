"""Molecular detail drawn round the close-up views (DESIGN.md §95.9): a membrane's lipids in
side view — phospholipids (two tails, some kinked by a cis double bond), cholesterol (a rigid
ring plate, its OH at the head groups), glycolipids with their sugars on the exoplasmic leaflet
only, cardiolipin's four tails, galactolipids, LPS — the plasma membrane's glycocalyx and lipid
rafts; a microtubule's α/β-tubulin dimers, actin's two-stranded helix, an intermediate
filament's twisted strands; a membrane's surface seen face on."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from manim import VGroup, VMobject

from vidgen.cellworld import BILAYER, KINDS, MOLECULES, Capsule, Ellipse, Placed, Polyline, molecule_glyph
from vidgen.cellworld.bilayer import MOSAIC_REACH, RAFT_WIDTH, Lipid, lipid_layout, lipids_of, mosaic, plasma_rafts
from vidgen.cellworld.catalog import LIPID_HEAD
from vidgen.cellworld.glyphs import bilayer_span
from vidgen.cellworld.curves import Cubic, line, polygon, smooth
from vidgen.cellworld.morphology import rng_for

if TYPE_CHECKING:
    from .drawing import CellDrawing

HEAD_HUE, TAIL_HUE, STEROL_HUE, SUGAR_HUE, CARDIO_HUE, RAFT_HUE = "#E07A5F", "#E9B44C", "#8A6BBE", "#4FA35E", "#C44569", "#F2D16B"
#: Lipid tails' width (µm).
TAIL = 0.00035


def _p(o: tuple[float, float], u: tuple[float, float], a: float, v: tuple[float, float], b: float) -> tuple[float, float]:
    return (o[0] + u[0] * a + v[0] * b, o[1] + u[1] * a + v[1] * b)


def lipids(d: "CellDrawing", curves: list[Cubic], feature: str | None) -> tuple[VGroup, VGroup]:
    """The lipids along a membrane's ``curves`` round each close-up it reaches: ``(under,
    over)`` — a raft's glow to draw under the bilayer, the lipids over it."""
    xs = [p[0] for cv in curves for p in cv]
    ys = [p[1] for cv in curves for p in cv]
    if not xs:
        return VGroup(), VGroup()
    found: list[Lipid] = []
    rafts = plasma_rafts(d.world) if d.world.kind != "bacterium" else []
    gaps = protein_gaps(d.world)
    for center, reach in d.near_closeup((min(xs), min(ys), max(xs), max(ys))):
        found += lipid_layout(d.world, curves, center, reach, f"{len(curves)}:{curves[0][0]}", rafts, gaps)
    if not found:
        return VGroup(), VGroup()
    base = f"{feature}&lipids" if feature else "lipids"
    heads, sterols, sugars, cardio, galacto, oh = [], [], [], [], [], []
    tails: list[Cubic] = []
    raft_patch = []
    for lipid in found:
        o = lipid.out
        t = (-o[1], o[0])
        h = lipid.head
        r = LIPID_HEAD / 2
        depth = BILAYER / 2 - LIPID_HEAD * 0.5 + (0.0004 if lipid.raft else 0.0)
        if lipid.kind == "sterol":
            oh.append(Ellipse(*_p(h, o, -0.0002, t, 0.0), 0.00017, 0.00017))
            a, b = _p(h, o, -0.00045, t, 0.0), _p(h, o, -0.0014, t, 0.0)
            sterols.append(Capsule((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, math.dist(a, b) + 0.00042, 0.00042, math.atan2(o[1], o[0])))
            tails.append(line(_p(h, o, -0.0014, t, 0.0), _p(h, o, -0.002, t, 0.0001)))
            continue
        if lipid.kind == "cardiolipin":
            cardio.append(Ellipse(h[0], h[1], r * 1.35, r * 0.9, math.atan2(t[1], t[0])))
            offsets = (-0.00033, -0.00011, 0.00011, 0.00033)
        else:
            offsets = (-0.0002, 0.0002)
            if lipid.kind == "galactolipid":
                galacto.append(polygon([(h[0] + r * 1.1 * math.cos(k * math.pi / 3), h[1] + r * 1.1 * math.sin(k * math.pi / 3)) for k in range(6)]))
            else:
                heads.append(Ellipse(h[0], h[1], r, r))
        kinked = not lipid.raft and (hash((round(h[0], 7), round(h[1], 7))) % 5 < 2)
        for k, off in enumerate(offsets):
            start = _p(h, o, -r * 0.9, t, off)
            end = _p(h, o, -depth - 0.0011, t, off * 1.1)
            if kinked and k == len(offsets) - 1:
                bend = _p(h, o, -r - 0.0008, t, off)
                tails += [line(start, bend), line(bend, _p(end, t, 0.00028, o, 0.0))]
            else:
                tails.append(line(start, end))
        if lipid.kind in ("glycolipid", "lps"):
            count = 3 if lipid.kind == "glycolipid" else 7
            for k in range(count):
                zig = 0.00022 * (1 if k % 2 else -1)
                sugars.append(Ellipse(*_p(h, o, r + 0.0003 + k * 0.00062, t, zig), 0.00029, 0.00029))
        if lipid.raft and lipid.leaflet == "exo":
            # the raft: a glow behind the bilayer where it is (thicker and more ordered there),
            # within the bilayer and its head groups: a raft is a domain of the membrane itself
            raft_patch.append(Ellipse(*_p(h, o, -BILAYER / 2 + r, t, 0.0), BILAYER * 0.75, BILAYER * 0.56, math.atan2(t[1], t[0])))
    c = d.colors
    under = VGroup()
    if raft_patch:
        under.add(d.piece(d.path(raft_patch), base, fill=c.fill(RAFT_HUE, 0.7)))
    parts: list[VMobject] = []
    parts.append(d.piece(d.curves(tails), base, stroke=c.solid(TAIL_HUE), px=0.6, true_um=TAIL))
    for shapes, hue in ((heads, HEAD_HUE), (cardio, CARDIO_HUE), (sterols, STEROL_HUE), (sugars, SUGAR_HUE), (oh, HEAD_HUE)):
        if shapes:
            parts.append(d.piece(d.path(shapes), base, fill=c.solid(hue)))
    if galacto:
        parts.append(d.piece(d.curves([cv for poly in galacto for cv in poly]), base, fill=c.solid(SUGAR_HUE)))
    return under, VGroup(*parts)


def protein_gaps(world: object) -> list[tuple[tuple[float, float], float, float, float]]:
    """Where membrane proteins fill a bilayer of the world: each one's centre, angle and the
    span of its glyph within the bilayer (µm), so the lipids leave room for it."""
    out = []
    for thing in world.placed:  # type: ignore[attr-defined]
        spec = thing.option("molecule")
        if spec is None or thing.option("membrane") is None or MOLECULES[thing.kind].family != "membrane":
            continue
        x0, x1 = bilayer_span(molecule_glyph(spec))
        out.append((thing.center, thing.angle, x0 / 1000.0, x1 / 1000.0))
    return out


def surface(d: "CellDrawing", thing: Placed, shape: object) -> VGroup:
    """A structure drawn whole, its outer membrane seen face on round the close-ups: the
    cytosolic leaflet's head groups packed together, sterols between them (galactolipids on a
    chloroplast)."""
    membrane = KINDS[thing.kind].membranes[0] if KINDS[thing.kind].membranes else None
    if membrane is None:
        return VGroup()
    composition = lipids_of(d.world, membrane)
    heads, sterols, sugars = [], [], []
    for center, reach in d.near_closeup(shape.bounds()):  # type: ignore[attr-defined]
        for kind, p in mosaic(center, min(reach, MOSAIC_REACH), shape.contains, composition, "cyto", thing.key):  # type: ignore[attr-defined]
            if kind == "sterol":
                sterols.append(Ellipse(p[0], p[1], 0.00022, 0.00022))
            elif kind == "galactolipid":
                sugars.append(Ellipse(p[0], p[1], 0.00036, 0.00036))
            else:
                heads.append(Ellipse(p[0], p[1], 0.00038, 0.00038))
    c = d.colors
    parts = []
    for shapes, color in ((heads, c.light(HEAD_HUE, 0.35)), (sugars, c.solid(SUGAR_HUE)), (sterols, c.solid(STEROL_HUE))):
        if shapes:
            parts.append(d.piece(d.path(shapes), "lipids", fill=color))
    return VGroup(*parts)


def glycocalyx(d: "CellDrawing", curves: list[Cubic]) -> VGroup:
    """Branched sugar chains on the outside of the plasma membrane (glycoproteins' and
    glycolipids' oligosaccharides), round the close-ups."""
    from vidgen.cellworld.bilayer import samples

    xs = [p[0] for cv in curves for p in cv]
    ys = [p[1] for cv in curves for p in cv]
    beads = []
    for center, reach in d.near_closeup((min(xs), min(ys), max(xs), max(ys))):
        rng = rng_for("glycocalyx", round(center[0], 4), round(center[1], 4))
        for p, n in samples(curves, center, reach, 0.0045):
            if rng.random() < 0.35:
                continue
            base = _p(p, n, BILAYER / 2 + 0.0004, (0.0, 0.0), 0.0)
            t = (-n[1], n[0])
            length = rng.randint(3, 8)
            lean = rng.uniform(-0.25, 0.25)
            for k in range(length):
                beads.append(Ellipse(*_p(base, n, 0.0005 + k * 0.00064, t, k * 0.00064 * lean), 0.0003, 0.0003))
                if k == length // 2 and rng.random() < 0.6:
                    for j in range(1, rng.randint(2, 4)):
                        beads.append(Ellipse(*_p(base, n, 0.0005 + k * 0.00064 + j * 0.00045, t, k * 0.00064 * lean + j * 0.00048), 0.00028, 0.00028))
    if not beads:
        return VGroup()
    return VGroup(d.piece(d.path(beads), "lipids", fill=d.colors.solid(SUGAR_HUE)))


def filament_detail(d: "CellDrawing", kind: str, lines: list[Polyline], hue: str) -> VGroup:
    """Subunits of the filaments round the close-ups: a microtubule's wall of α- and β-tubulin
    (8 nm dimers; β at the plus end), actin's two strands of 5.5 nm subunits crossing every
    37 nm, an intermediate filament's twisted strands."""
    if kind not in ("microtubule", "actin_filament", "actin_cortex", "stress_fiber", "intermediate_filament"):
        return VGroup()
    alpha, beta = [], []
    strands: list[Cubic] = []
    for l in lines:
        x0, y0, x1, y1 = l.bounds()
        for center, reach in d.near_closeup((x0, y0, x1, y1)):
            if kind == "microtubule":
                _tubulin(l, center, reach, alpha, beta)
            elif kind == "intermediate_filament":
                strands += _twist(l, center, reach)
            else:
                _actin(l, center, reach, alpha, beta)
    if not (alpha or beta or strands):
        return VGroup()
    feature = "filament_detail" if kind == "microtubule" else "actin_detail"
    c = d.colors
    parts = []
    if kind == "microtubule":
        lumen = []
        for l in lines:
            for center, reach in d.near_closeup(l.bounds()):
                pts = [p for p in l.outline(400) if math.dist(p, center) < reach]
                if len(pts) > 1:
                    lumen += smooth(pts)
        parts.append(d.piece(d.curves(lumen), feature, stroke=c.fill(hue, 0.18), true_um=0.015))
    if alpha:
        parts.append(d.piece(d.path(alpha), feature, fill=c.fill(hue, 0.55), stroke=c.ink(hue), px=0.6))
    if beta:
        parts.append(d.piece(d.path(beta), feature, fill=c.solid(hue), stroke=c.ink(hue), px=0.6))
    if strands:
        parts.append(d.piece(d.curves(strands), "actin_detail", stroke=c.solid(hue), true_um=0.0035))
    return VGroup(*parts)


def _tubulin(l: Polyline, center: tuple[float, float], reach: float, alpha: list, beta: list) -> None:
    s = 0.0
    k = 0
    while s < l.length:
        p, (dx, dy) = l.at(s)
        if math.dist(p, center) < reach:
            for side in (-1, 1):
                q = (p[0] - dy * side * 0.0102, p[1] + dx * side * 0.0102)
                (alpha if k % 2 == 0 else beta).append(Ellipse(q[0], q[1], 0.0021, 0.0023, math.atan2(dy, dx)))
        s += 0.004
        k += 1


def _actin(l: Polyline, center: tuple[float, float], reach: float, a_list: list, b_list: list) -> None:
    s = 0.0
    k = 0
    while s < l.length:
        p, (dx, dy) = l.at(s)
        if math.dist(p, center) < reach:
            phase = 2 * math.pi * s / 0.074
            for strand, out in ((0, a_list), (1, b_list)):
                off = 0.0019 * math.cos(phase + strand * math.pi)
                out.append(Ellipse(p[0] - dy * off, p[1] + dx * off, 0.00135, 0.00135))
        s += 0.00275
        k += 1


def _twist(l: Polyline, center: tuple[float, float], reach: float) -> list[Cubic]:
    out: list[Cubic] = []
    for strand in range(2):
        pts = []
        s = 0.0
        while s < l.length:
            p, (dx, dy) = l.at(s)
            if math.dist(p, center) < reach:
                off = 0.003 * math.sin(2 * math.pi * s / 0.046 + strand * math.pi)
                pts.append((p[0] - dy * off, p[1] + dx * off))
            elif len(pts) > 1:
                out += smooth(pts)
                pts = []
            s += 0.003
        if len(pts) > 1:
            out += smooth(pts)
    return out


__all__ = ["HEAD_HUE", "RAFT_WIDTH", "TAIL_HUE", "filament_detail", "glycocalyx", "lipids"]
