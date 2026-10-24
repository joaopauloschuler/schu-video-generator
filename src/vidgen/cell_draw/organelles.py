"""Drawings of an animal cell's structures and complexes (DESIGN.md §95.9): the nucleus with
its envelope (one lumen with the ER), pores, heterochromatin and nucleolus; the rough ER joined
to the envelope, with exit sites; the smooth-ER network; Golgi cisternae cis to trans with rims,
buds and coats; mitochondria with cristae and their junctions; lysosomes, peroxisomes,
endosomes, vesicles with clathrin / COPI / COPII coats; the centrosome's centrioles; ribosomes,
proteasomes and nuclear pore complexes. Each in section (cut open) or as a surface (whole)."""

from __future__ import annotations

import math
import zlib
from typing import TYPE_CHECKING

import numpy as np
from manim import VGroup, VMobject

from vidgen.cellworld import BILAYER, KINDS, Capsule, Ellipse, Placed, Region, RoundedBox
from vidgen.cellworld.catalog import CELL_HUES, COAT_HUES, COATS, MITO_GAP, PERINUCLEAR_GAP, PORES_PER_UM2
from vidgen.cellworld.curves import Cubic, arc, line, polygon, shape_curves, smooth
from vidgen.cellworld.morphology import centrioles, envelope, heterochromatin, nucleolus_parts, rng_for, segment, surface_pores

from . import closeup
from .base import MEMBRANE_PX, RIM_PX

if TYPE_CHECKING:
    from .drawing import CellDrawing

ER_HUE = KINDS["rough_er"].hue


def _rng(key: str) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(key.encode("utf-8")))


def highlight(d: "CellDrawing", shape: object, hue: str, feature: str | None = None) -> VMobject:
    """A soft light patch up and left on a whole body (the surface style's flat shading)."""
    x0, y0, x1, y1 = shape.bounds()  # type: ignore[attr-defined]
    w, h = x1 - x0, y1 - y0
    patch = Ellipse(x0 + w * 0.36, y0 + h * 0.66, w * 0.16, h * 0.09, -0.35)
    return d.piece(d.path([patch]), feature, fill=d.colors.light(hue, 0.18))


# ----- nucleus ---------------------------------------------------------------------------------------


def nucleus(d: "CellDrawing", thing: Placed) -> VGroup:
    """Section: nucleoplasm with heterochromatin lining the inner membrane (open at the pores)
    and round the nucleolus; the perinuclear space coloured as the ER lumen it is continuous
    with; one line for the envelope until its two membranes part on screen. Surface: the whole
    nucleus with its pores as rings."""
    hue = KINDS["nucleus"].hue
    outer = thing.footprint[0]
    assert isinstance(outer, Ellipse)
    inner = outer.inset(PERINUCLEAR_GAP + BILAYER)
    pores = list(thing.option("pores", ()))
    if d.style_of(thing) == "surface":
        body = d.piece(d.path([outer]), None, fill=d.colors.fill(hue, 0.42))
        rings = _surface_pores(d, outer, thing.key)
        line_ = d.membrane([outer], hue, px=MEMBRANE_PX * 1.2, lipids=False)
        return VGroup(body, closeup.surface(d, thing, outer), rings, line_)
    nucleoli = [p.footprint[0] for p in d.world.placed if p.kind == "nucleolus" and p.host == f"{thing.key}.nucleoplasm"]
    plasm = d.piece(d.path([inner]), None, fill=d.colors.fill(hue, 0.3))
    chromatin = heterochromatin(inner, pores, [n for n in nucleoli if isinstance(n, Ellipse)], thing.key)
    dark = d.piece(d.curves(chromatin.curves()), None, fill=d.colors.fill(hue, 0.6))
    ring = envelope(outer, inner, pores)
    lumen = d.piece(d.curves(ring.curves()), None, fill=d.colors.fill(ER_HUE, 0.45))
    single = d.membrane([outer], hue, "!double_membrane", px=MEMBRANE_PX * 1.2, lipids=False)
    both = d.membrane(ring.curves(), hue, "double_membrane")
    return VGroup(plasm, dark, lumen, single, both)


def _surface_pores(d: "CellDrawing", outer: Ellipse, key: str) -> VGroup:
    """Nuclear pores seen on the nucleus's surface: about 10 per µm², foreshortened towards the
    rim of the projected body; up close each pore complex's eightfold ring of spokes round its
    central channel."""
    rings, holes, spokes = [], [], []
    for center, fore, radial in surface_pores(outer, key, PORES_PER_UM2):
        rings.append(Ellipse(center[0], center[1], 0.06 * fore, 0.06, radial))
        holes.append(Ellipse(center[0], center[1], 0.022 * fore, 0.022, radial))
        if fore > 0.5:
            c, s = math.cos(radial), math.sin(radial)
            for k in range(8):
                a = 2 * math.pi * k / 8
                u, v = 0.04 * math.cos(a) * fore, 0.04 * math.sin(a)
                spokes.append(Ellipse(center[0] + u * c - v * s, center[1] + u * s + v * c, 0.0115 * fore, 0.0115, radial))
    hue = KINDS["nuclear_pore"].hue
    return VGroup(d.piece(d.path(rings), "pores", fill=d.colors.fill(hue, 0.6)),
                  d.piece(d.path(spokes), "pore_detail", fill=d.colors.solid(hue), stroke=d.colors.ink(hue), px=0.8),
                  d.piece(d.path(holes), "pores", fill=d.colors.fill(KINDS["nucleus"].hue, 0.25)))


def pores(d: "CellDrawing", things: list[Placed]) -> VGroup:
    """Nuclear pore complexes in section: a channel through both membranes (outer and inner
    joined at its rim) lined by the spoke ring, with the cytoplasmic and nuclear rings; up close
    the cytoplasmic filaments, the nuclear basket and the FG-repeat mesh of the central
    channel."""
    hue = KINDS["nuclear_pore"].hue
    gaps, rims, spokes, rings, mesh = [], [], [], [], []
    filaments: list[Cubic] = []
    across = PERINUCLEAR_GAP + 2 * BILAYER
    for t in things:
        nx, ny = t.normal or (1.0, 0.0)
        tx, ty = -ny, nx
        along = math.atan2(ny, nx)
        cx, cy = t.center
        gaps.append(Capsule(cx, cy, across + 0.01, t.size * 0.62, along))
        for side in (-1, 1):
            ox, oy = tx * side * t.size * 0.36, ty * side * t.size * 0.36
            rims.append(Capsule(cx + ox, cy + oy, across + 0.02, 0.026, along))
            sx, sy = tx * side * 0.042, ty * side * 0.042
            spokes.append(Capsule(cx + sx, cy + sy, across + 0.006, 0.022, along))
            for out in (1, -1):                         # cytoplasmic ring (out) and nuclear ring (in)
                rx, ry = cx + tx * side * 0.038 + nx * out * (across / 2 + 0.008), cy + ty * side * 0.038 + ny * out * (across / 2 + 0.008)
                rings.append(Ellipse(rx, ry, 0.02, 0.011, along + math.pi / 2))
            base = (cx + tx * side * 0.04 + nx * (across / 2 + 0.014), cy + ty * side * 0.04 + ny * (across / 2 + 0.014))
            for k, bend in enumerate((0.3, -0.25)):
                tip = (base[0] + nx * (0.05 - 0.01 * k) + tx * side * bend * 0.05, base[1] + ny * (0.05 - 0.01 * k) + ty * side * bend * 0.05)
                mid = ((base[0] + tip[0]) / 2 + tx * side * 0.008, (base[1] + tip[1]) / 2 + ty * side * 0.008)
                filaments += smooth([base, mid, tip])
            low = (cx + tx * side * 0.04 - nx * (across / 2 + 0.014), cy + ty * side * 0.04 - ny * (across / 2 + 0.014))
            ring_pt = (cx + tx * side * 0.016 - nx * 0.075, cy + ty * side * 0.016 - ny * 0.075)
            mid = ((low[0] + ring_pt[0]) / 2 + tx * side * 0.012, (low[1] + ring_pt[1]) / 2 + ty * side * 0.012)
            filaments += smooth([low, mid, ring_pt])
        rings.append(Ellipse(cx - nx * 0.075, cy - ny * 0.075, 0.018, 0.006, along + math.pi / 2))     # the basket's distal ring
        rng = rng_for("fg", t.key)
        for _ in range(9):
            u, v = rng.uniform(-0.028, 0.028), rng.uniform(-across / 2, across / 2)
            mesh.append(Ellipse(cx + tx * u + nx * v, cy + ty * u + ny * v, 0.004, 0.004))
    gap = d.piece(d.path(gaps), "pores", fill=d.colors.fill(KINDS["nucleus"].hue, 0.3))
    simple = d.piece(d.path(rims), "pores&!pore_detail", fill=d.colors.solid(hue), stroke=d.colors.ink(hue), px=RIM_PX)
    detail = VGroup(
        d.piece(d.path(spokes), "pores&pore_detail", fill=d.colors.solid(hue), stroke=d.colors.ink(hue), px=RIM_PX),
        d.piece(d.path(rings), "pores&pore_detail", fill=d.colors.fill(hue, 0.75), stroke=d.colors.ink(hue), px=RIM_PX),
        d.piece(d.curves(filaments), "pore_detail", stroke=d.colors.ink(hue), px=1.2, true_um=0.004),
        d.piece(d.path(mesh), "pore_detail", fill=d.colors.fill(hue, 0.5)),
    )
    return VGroup(gap, simple, detail)


def nucleolus(d: "CellDrawing", thing: Placed) -> VGroup:
    """A nucleolus (no membrane): its granular component with fibrillar centres, each in a rim
    of dense fibrillar component (where rRNA is made)."""
    hue = KINDS["nucleolus"].hue
    shape = thing.footprint[0]
    assert isinstance(shape, Ellipse)
    body = d.piece(d.path([shape]), None, fill=d.colors.fill(hue, 0.62))
    centres, rims = nucleolus_parts(shape, thing.key)
    rng = _rng(f"granules:{thing.key}")
    grains = []
    for _ in range(int(shape.a * shape.b * 140)):
        r, t = shape.a * 0.92 * math.sqrt(rng.uniform()), rng.uniform(0, 2 * math.pi)
        p = (shape.cx + r * math.cos(t), shape.cy + r * math.sin(t) * shape.b / shape.a)
        if any(c.contains(p, 0.03) for c in rims):
            continue
        grains.append(Ellipse(p[0], p[1], 0.012, 0.012))
    return VGroup(body,
                  d.piece(d.path(grains), "fine", fill=d.colors.fill(hue, 0.85)),
                  d.piece(d.path(rims), "fine", fill=d.colors.fill(hue, 0.9)),
                  d.piece(d.path(centres), "fine", fill=d.colors.fill(hue, 0.3)))


# ----- endoplasmic reticulum ---------------------------------------------------------------------------


def rough_er(d: "CellDrawing", thing: Placed) -> VGroup:
    """The rough ER: its sheets as one lumen with the perinuclear space (joined to the outer
    nuclear membrane, and sheet to sheet), with COPII-coated buds at exit sites."""
    hue = KINDS["rough_er"].hue
    region: Region = thing.parts[0].membranes[0][1]  # type: ignore[assignment]
    joined = _joined_envelope(d, thing)
    whole = region.plus(joined) if joined is not None else region
    fill = d.piece(d.curves(whole.curves()), None, fill=d.colors.fill(hue, 0.45))
    far = d.membrane(region.curves(), hue, "!double_membrane", lipids=False)
    near = d.membrane(whole.curves(), hue, "double_membrane")
    coats = _bud_coats(d, thing, thing.option("buds", ()))
    return VGroup(fill, far, near, coats)


def _joined_envelope(d: "CellDrawing", thing: Placed) -> Region | None:
    for key in thing.joined:
        other = d.world.thing(key)
        if other.kind == "nucleus":
            outer = other.footprint[0]
            assert isinstance(outer, Ellipse)
            return envelope(outer, outer.inset(PERINUCLEAR_GAP + BILAYER), list(other.option("pores", ())))
    return None


def smooth_er(d: "CellDrawing", thing: Placed) -> VGroup:
    """The smooth ER: a network of tubules between three-way junctions, joined to the end of a
    rough-ER sheet."""
    hue = KINDS["smooth_er"].hue
    region: Region = thing.parts[0].membranes[0][1]  # type: ignore[assignment]
    whole = region
    for key in thing.joined:
        er = d.world.thing(key)
        sheets = er.option("sheets", ())
        link = thing.footprint[-1].center()
        if sheets:
            band = min(sheets, key=lambda b: min(math.dist(e, link) for e in b.ends()))
            whole = region.plus(band)
    fill = d.piece(d.curves(whole.curves()), None, fill=d.colors.fill(hue, 0.45))
    edge = d.membrane(whole.curves(), hue)
    return VGroup(fill, edge)


# ----- Golgi ---------------------------------------------------------------------------------------------


def golgi(d: "CellDrawing", thing: Placed) -> VGroup:
    """A Golgi stack in section: cisternae from cis (paler, fenestrated, facing the ER) to trans
    (stronger, swollen), each with dilated rims and vesicles budding there (COPI coats on the
    cis and medial ones, clathrin on the trans)."""
    hue = KINDS["golgi"].hue
    count = len(thing.parts)
    fills, lines = [], []
    for k, part in enumerate(thing.parts):
        region = part.membranes[0][1]
        strength = 0.3 + 0.32 * k / max(count - 1, 1)
        fills.append(d.piece(d.curves(region.curves()), None, fill=d.colors.fill(hue, strength)))  # type: ignore[attr-defined]
        lines.append(d.membrane(region.curves(), hue))  # type: ignore[attr-defined]
    coats = _bud_coats(d, thing, thing.option("buds", ()))
    return VGroup(*fills, *lines, coats)


def _bud_coats(d: "CellDrawing", thing: Placed, buds: object) -> VGroup:
    """Coats on the free side of budding vesicles."""
    out = []
    for center, radius, coat, k in buds:  # type: ignore[attr-defined]
        if thing.kind == "golgi":
            band = thing.option("bands")[k]
            end = min(band.ends(), key=lambda e: math.dist(e, center))
            away = math.atan2(center[1] - end[1], center[0] - end[0])
        else:
            sheet = thing.option("sheets")[k]
            away = math.atan2(center[1] - sheet.cy, center[0] - sheet.cx)
        out.append(coat_drawing(d, center, radius, coat, away - 2.2, away + 2.2))
    return VGroup(*out)


# ----- vesicles and coats ---------------------------------------------------------------------------------


def coat_drawing(d: "CellDrawing", center: tuple[float, float], radius: float, coat: str, a0: float = 0.0, a1: float = 2 * math.pi) -> VGroup:
    """A vesicle's coat outside its membrane (from angle ``a0`` to ``a1``): a band at low zoom;
    up close clathrin as a bristly cage of triskelion legs, COPI as a dense layer of coatomer,
    COPII as an inner Sec23/24 layer under an outer Sec13/31 cage."""
    hue = COAT_HUES[coat]
    thick = COATS[coat]
    cx, cy = center
    r0, r1 = radius + BILAYER / 2 + 0.001, radius + BILAYER / 2 + thick
    full = abs(a1 - a0) >= 2 * math.pi - 1e-9
    if full:
        band = Region.of(Ellipse(cx, cy, r1, r1)).minus(Ellipse(cx, cy, r0, r0))
        band_curves = band.curves()
    else:
        band_curves = [*arc(cx, cy, r1, a0, a1), *arc(cx + (r1 + r0) / 2 * math.cos(a1), cy + (r1 + r0) / 2 * math.sin(a1), (r1 - r0) / 2, a1, a1 + math.pi),
                       *arc(cx, cy, r0, a1, a0), *arc(cx + (r1 + r0) / 2 * math.cos(a0), cy + (r1 + r0) / 2 * math.sin(a0), (r1 - r0) / 2, a0 + math.pi, a0 + 2 * math.pi)]
    simple = d.piece(d.curves(band_curves), "!coat_detail", fill=d.colors.fill(hue, 0.75))
    span = a1 - a0
    detail: list[VMobject] = []
    if coat == "clathrin":
        n = max(6, int(abs(span) * r1 / 0.011))
        outer = [(cx + r1 * math.cos(a0 + span * k / n), cy + r1 * math.sin(a0 + span * k / n)) for k in range(n + 1)]
        cage: list[Cubic] = [line(p, q) for p, q in zip(outer, outer[1:])]
        for k in range(n + 1):
            a = a0 + span * k / n
            cage.append(line((cx + r0 * math.cos(a + 0.12), cy + r0 * math.sin(a + 0.12)), outer[k]))
        detail.append(d.piece(d.curves(cage), "coat_detail", stroke=d.colors.solid(hue), px=1.2, true_um=0.0025))
    elif coat == "copi":
        n = max(6, int(abs(span) * (r0 + r1) / 2 / 0.0065))
        beads = [Ellipse(cx + (r0 + r1) / 2 * math.cos(a0 + span * (k + 0.5) / n), cy + (r0 + r1) / 2 * math.sin(a0 + span * (k + 0.5) / n),
                         thick * 0.42, thick * 0.32, a0 + span * (k + 0.5) / n) for k in range(n)]
        detail.append(d.piece(d.path(beads), "coat_detail", fill=d.colors.solid(hue)))
    else:
        rin = r0 + thick * 0.28
        n = max(6, int(abs(span) * rin / 0.006))
        inner = [Ellipse(cx + rin * math.cos(a0 + span * (k + 0.5) / n), cy + rin * math.sin(a0 + span * (k + 0.5) / n), thick * 0.24, thick * 0.24)
                 for k in range(n)]
        m = max(4, int(abs(span) * r1 / 0.014))
        outer = [(cx + r1 * math.cos(a0 + span * k / m), cy + r1 * math.sin(a0 + span * k / m)) for k in range(m + 1)]
        mid_r = r0 + thick * 0.6
        lattice: list[Cubic] = []
        for k in range(m):
            a = a0 + span * (k + 0.5) / m
            mid = (cx + mid_r * math.cos(a), cy + mid_r * math.sin(a))
            lattice += [line(outer[k], mid), line(mid, outer[k + 1])]
        lattice += [line(p, q) for p, q in zip(outer, outer[1:])]
        detail.append(d.piece(d.path(inner), "coat_detail", fill=d.colors.fill(hue, 0.7)))
        detail.append(d.piece(d.curves(lattice), "coat_detail", stroke=d.colors.solid(hue), px=1.0, true_um=0.002))
    return VGroup(simple, *detail)


def _surface_coat(d: "CellDrawing", shape: Ellipse, coat: str) -> VGroup:
    """A coated vesicle seen whole: clathrin's lattice of hexagons and pentagons, COPII's
    diamond cage, COPI's dense coatomer."""
    hue = COAT_HUES[coat]
    r = shape.a
    cx, cy = shape.cx, shape.cy
    ball = d.piece(d.path([Ellipse(cx, cy, r, r)]), None, fill=d.colors.fill(hue, 0.55))
    curves: list[Cubic] = []
    if coat == "copi":
        rng = _rng(f"copi:{cx:.5f}:{cy:.5f}")
        dots = [Ellipse(cx + rr * math.cos(t), cy + rr * math.sin(t), r * 0.08, r * 0.08)
                for rr, t in ((r * 0.88 * math.sqrt(rng.uniform()), rng.uniform(0, 2 * math.pi)) for _ in range(40))]
        return VGroup(ball, d.piece(d.path(dots), "coat_detail", fill=d.colors.ink(hue)))
    step = r * (0.42 if coat == "clathrin" else 0.36)
    pts = []
    rows = int(2 * r / step) + 3
    for j in range(-rows, rows + 1):
        for i in range(-rows, rows + 1):
            x = (i + (0.5 if j % 2 else 0.0)) * step
            y = j * step * (0.866 if coat == "clathrin" else 1.0)
            if x * x + y * y < (r - step * 0.5) ** 2:          # whole polygons only, inside the ball
                pts.append((x, y))
    for x, y in pts:
        if coat == "clathrin":
            hexagon = [(cx + x + step * 0.5 * math.cos(math.pi / 6 + k * math.pi / 3), cy + y + step * 0.5 * math.sin(math.pi / 6 + k * math.pi / 3)) for k in range(6)]
            curves += polygon(hexagon)
        else:
            diamond = [(cx + x + step * 0.5, cy + y), (cx + x, cy + y + step * 0.5), (cx + x - step * 0.5, cy + y), (cx + x, cy + y - step * 0.5)]
            curves += polygon(diamond)
    return VGroup(ball, d.piece(d.curves(curves), "coat_detail", stroke=d.colors.ink(hue), px=1.2, true_um=0.002))


# ----- mitochondria -----------------------------------------------------------------------------------------


def mitochondrion(d: "CellDrawing", thing: Placed) -> VGroup:
    """Section: the outer membrane, the inner one folded into lamellar cristae opening into the
    intermembrane space through narrow crista junctions (one line for both membranes until they
    part on screen); the matrix with a few granules. Surface: the smooth outer membrane."""
    hue = KINDS["mitochondrion"].hue
    outer = thing.footprint[0]
    assert isinstance(outer, Capsule)
    if d.style_of(thing) == "surface":
        return VGroup(d.piece(d.path([outer]), None, fill=d.colors.fill(hue, 0.5)), highlight(d, outer, hue), closeup.surface(d, thing, outer),
                      d.membrane([outer], hue, px=MEMBRANE_PX * 1.2, lipids=False))
    inner = outer.inset(MITO_GAP + BILAYER)
    folded = thing.parts[0].membranes[1][1]
    ims = d.piece(d.path([outer]), None, fill=d.colors.fill(hue, 0.5))
    matrix = d.piece(d.curves(folded.curves()), "cristae", fill=d.colors.fill(hue, 0.36))  # type: ignore[attr-defined]
    plain = d.piece(d.path([inner]), "!cristae", fill=d.colors.fill(hue, 0.36))
    rng = _rng(f"granules:{thing.key}")
    grains = [Ellipse(outer.cx + float(rng.uniform(-0.35, 0.35)) * outer.half * math.cos(outer.angle),
                      outer.cy + float(rng.uniform(-0.35, 0.35)) * outer.half * math.sin(outer.angle), 0.018, 0.018) for _ in range(2)]
    granules = d.piece(d.path(grains), "fine", fill=d.colors.fill(hue, 0.8))
    single = d.membrane([outer], hue, "!mito_double", px=MEMBRANE_PX * 1.2, lipids=False)
    cristae_line = d.piece(d.curves(_crista_lines(folded, inner)), "cristae&!mito_double", stroke=d.colors.ink(hue), px=MEMBRANE_PX * 0.8)
    both = VGroup(d.membrane([outer], hue, "mito_double"), d.membrane(folded.curves(), hue, "mito_double&cristae"),  # type: ignore[attr-defined]
                  d.membrane([inner], hue, "mito_double&!cristae", lipids=False))
    return VGroup(ims, matrix, plain, granules, single, cristae_line, both)


def _crista_lines(folded: object, inner: Capsule) -> list[Cubic]:
    """The cristae as lines (before the two membranes part on screen): each fold's middle."""
    out: list[Cubic] = []
    for contour in folded.contours():  # type: ignore[attr-defined]
        out += contour
    return out


def small(d: "CellDrawing", thing: Placed) -> VGroup:
    """Lysosomes, peroxisomes, endosomes and vesicles."""
    kind = KINDS[thing.kind]
    hue = kind.hue
    part = thing.parts[0]
    shape = part.membranes[0][1]
    surface = d.style_of(thing) == "surface"
    coat = thing.option("coat")
    if surface and isinstance(shape, Ellipse):
        if coat:
            return _surface_coat(d, Ellipse(shape.cx, shape.cy, shape.a + COATS[coat], shape.b + COATS[coat]), coat)
        return VGroup(d.piece(d.path([shape]), None, fill=d.colors.fill(hue, 0.45)), highlight(d, shape, hue), closeup.surface(d, thing, shape),
                      d.membrane([shape], hue, lipids=False))
    strength = 0.4
    pieces: list[VMobject] = [d.piece(d.curves(shape_curves(shape)), None, fill=d.colors.fill(hue, strength))]
    if thing.kind == "lysosome":
        pieces.append(_granules(d, thing, hue))
    if thing.kind == "peroxisome":
        pieces.append(_granules(d, thing, hue, count=14, size=0.035, feature="fine", strength=0.62))
    if thing.kind == "late_endosome":
        ilvs = [p.membranes[0][1] for p in thing.parts[1:]]
        pieces.append(d.piece(d.path(ilvs), None, fill=d.colors.fill(CELL_HUES["animal"], 0.32)))   # their inside is cytosol
        pieces.append(d.membrane(ilvs, hue, px=MEMBRANE_PX * 0.7))
    pieces.append(d.membrane(shape_curves(shape), hue))
    if coat and isinstance(shape, Ellipse):
        pieces.append(coat_drawing(d, shape.center(), shape.a, coat))
    return VGroup(*pieces)


def _granules(d: "CellDrawing", thing: Placed, hue: str, count: int = 5, size: float = 0.12, feature: str | None = None,
              strength: float = 0.75) -> VMobject:
    shape = thing.footprint[0]
    assert isinstance(shape, Ellipse)
    rng = _rng(thing.key)
    dots = []
    for _ in range(count):
        r = shape.a * 0.55 * math.sqrt(rng.uniform())
        a = rng.uniform(0, 2 * math.pi)
        dots.append(Ellipse(shape.cx + r * math.cos(a), shape.cy + r * math.sin(a), shape.a * size, shape.a * size))
    return d.piece(d.path(dots), feature, fill=d.colors.fill(hue, strength))


# ----- centrosome ---------------------------------------------------------------------------------------------


def centrosome(d: "CellDrawing", thing: Placed) -> VGroup:
    """Pericentriolar material (with γ-tubulin ring complexes) round two centrioles at right
    angles: in a section the mother is cut lengthwise (its triplet walls, appendages at the
    distal end) and the daughter across (a ring of nine microtubule triplets round a cartwheel)."""
    hue = KINDS["centrosome"].hue
    halo = d.piece(d.path(thing.footprint), None, fill=d.colors.fill(hue, 0.22))
    mother, tip = centrioles(thing.center, thing.angle)
    rng = _rng(f"pcm:{thing.key}")
    turcs = []
    for _ in range(26):
        r = thing.size / 2 * (0.45 + 0.4 * math.sqrt(rng.uniform()))
        a = rng.uniform(0, 2 * math.pi)
        turcs.append(Ellipse(thing.center[0] + r * math.cos(a), thing.center[1] + r * math.sin(a), 0.013, 0.013))
    gamma = d.piece(d.path(turcs), "fine", stroke=d.colors.ink(hue), px=0.8, true_um=0.004)
    # mother, lengthwise: two walls of three microtubules each, appendages at its distal end (the
    # daughter grows at right angles from its proximal end)
    c, s = math.cos(mother.angle), math.sin(mother.angle)
    walls: list[Cubic] = []
    for side in (-1, 1):
        for k in range(3):
            off = side * (0.1 - k * 0.022)
            a = (mother.cx - c * 0.2 - s * off, mother.cy - s * 0.2 + c * off)
            b = (mother.cx + c * 0.2 - s * off, mother.cy + s * 0.2 + c * off)
            walls.append(line(a, b))
        foot = (mother.cx - c * 0.16 - s * side * 0.11, mother.cy - s * 0.16 + c * side * 0.11)
        walls.append(line(foot, (foot[0] - s * side * 0.07 - c * 0.03, foot[1] + c * side * 0.07 - s * 0.03)))
    body = RoundedBox(mother.cx, mother.cy, 0.42, 0.24, 0.02, mother.angle)
    mother_fill = d.piece(d.path([body]), None, fill=d.colors.fill(hue, 0.55))
    mother_low = d.piece(d.path([body]), "!fine", stroke=d.colors.ink(hue), px=MEMBRANE_PX * 0.8)
    mother_walls = d.piece(d.curves(walls), "fine", stroke=d.colors.ink(hue), px=1.0, true_um=0.012)
    # daughter, across: nine triplets (A, B, C tubules) tilted like a pinwheel, a cartwheel inside
    ring = Ellipse(tip[0], tip[1], 0.11, 0.11)
    daughter_fill = d.piece(d.path([ring]), None, fill=d.colors.fill(hue, 0.55))
    daughter_low = d.piece(d.path([ring]), "!fine", stroke=d.colors.ink(hue), px=MEMBRANE_PX * 0.8)
    tubules, spokes = [], []
    for k in range(9):
        a = 2 * math.pi * k / 9
        blade = a + 0.95                                  # each triplet a blade leaning like a pinwheel's
        for j in range(3):                                # the A tubule innermost, then B, then C
            x = tip[0] + 0.074 * math.cos(a) + j * 0.0185 * math.cos(blade)
            y = tip[1] + 0.074 * math.sin(a) + j * 0.0185 * math.sin(blade)
            tubules.append(Ellipse(x, y, 0.0092, 0.0092))
        spokes.append(line((tip[0] + 0.012 * math.cos(a), tip[1] + 0.012 * math.sin(a)), (tip[0] + 0.07 * math.cos(a), tip[1] + 0.07 * math.sin(a))))
    triplets = d.piece(d.path(tubules), "fine", fill=d.colors.fill(hue, 0.25), stroke=d.colors.ink(hue), px=0.8, true_um=0.004)
    cartwheel = d.piece(d.curves(spokes + list(arc(tip[0], tip[1], 0.012, 0, 2 * math.pi))), "fine", stroke=d.colors.ink(hue), px=0.8, true_um=0.003)
    return VGroup(halo, gamma, mother_fill, mother_low, mother_walls, daughter_fill, daughter_low, triplets, cartwheel)


# ----- complexes ---------------------------------------------------------------------------------------------------


def particles(d: "CellDrawing", kind_name: str, things: list[Placed]) -> VGroup:
    """Ribosomes (a dot at their real size, up close the large subunit against the membrane and
    the small one on it) and proteasomes (a barrel of four rings with a cap at either end)."""
    hue = KINDS[kind_name].hue
    dots = d.piece(d.path([Ellipse(t.center[0], t.center[1], t.size / 2, t.width / 2, t.angle) for t in things]),
                   "particles&!particle_detail", fill=d.colors.solid(hue), stroke=d.colors.solid(hue), px=RIM_PX)
    large, small_, stripes = [], [], []
    for t in things:
        nx, ny = t.normal if t.normal is not None else (math.cos(t.angle), math.sin(t.angle))
        angle = math.atan2(ny, nx) + math.pi / 2
        f = t.size / 0.025
        if kind_name == "ribosome":
            large.append(Ellipse(t.center[0] - nx * 0.004 * f, t.center[1] - ny * 0.004 * f, 0.0125 * f, 0.0085 * f, angle))
            small_.append(Ellipse(t.center[0] + nx * 0.0085 * f, t.center[1] + ny * 0.0085 * f, 0.0095 * f, 0.0052 * f, angle))
        elif kind_name == "proteasome":
            c, s = math.cos(t.angle), math.sin(t.angle)
            large.append(Capsule(t.center[0], t.center[1], t.size * 0.62, t.width * 0.62, t.angle))
            for side in (-1, 1):
                small_.append(Ellipse(t.center[0] + c * side * t.size * 0.38, t.center[1] + s * side * t.size * 0.38, t.size * 0.12, t.width * 0.5, t.angle))
            for k in range(1, 4):
                x = -t.size * 0.31 + t.size * 0.62 * k / 4
                stripes.append(line((t.center[0] + c * x - s * t.width * 0.31, t.center[1] + s * x + c * t.width * 0.31),
                                    (t.center[0] + c * x + s * t.width * 0.31, t.center[1] + s * x - c * t.width * 0.31)))
        else:
            large.append(Ellipse(t.center[0], t.center[1], t.size / 2, t.width / 2, t.angle))
    detail = [d.piece(d.path(large), "particle_detail", fill=d.colors.solid(hue), stroke=d.colors.ink(hue), px=RIM_PX)]
    if small_:
        detail.append(d.piece(d.path(small_), "particle_detail", fill=d.colors.fill(hue, 0.6), stroke=d.colors.ink(hue), px=RIM_PX))
    if stripes:
        detail.append(d.piece(d.curves(stripes), "particle_detail", stroke=d.colors.ink(hue), px=0.8))
    return VGroup(dots, *detail)


__all__ = ["coat_drawing", "golgi", "highlight", "mitochondrion", "nucleolus", "nucleus", "particles", "pores", "rough_er", "small",
           "smooth_er", "centrosome", "segment"]
