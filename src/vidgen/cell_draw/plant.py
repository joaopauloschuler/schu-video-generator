"""Drawings of a plant cell (DESIGN.md §95.9): its wall (with the middle lamella where it meets
the next cell's) crossed by plasmodesmata — the plasma membrane lining each channel round a
desmotubule of appressed ER —, the central vacuole and its tonoplast, chloroplasts with their
envelope, grana of stacked thylakoids joined by stroma lamellae, starch and plastoglobuli; and
the tissue of walled cells round it."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from manim import VGroup

from vidgen.cellworld import BILAYER, KINDS, Capsule, Ellipse, Placed, RoundedBox
from vidgen.cellworld.catalog import CELL_HUES, CHLOROPLAST_GAP, DESMOTUBULE, MEMBRANE_HUE, WALL_HUE
from vidgen.cellworld.curves import line, polygon

from . import closeup
from .base import MEMBRANE_PX, PLASMA_PX
from .organelles import highlight

if TYPE_CHECKING:
    from .drawing import CellDrawing


def tissue(d: "CellDrawing") -> VGroup:
    """Neighbouring plant cells: walls against walls (their faces meet at the middle lamella),
    each protoplast with its nucleus."""
    walls = [n.wall for n in d.world.neighbours if n.wall is not None]
    cells = [n.cell for n in d.world.neighbours]
    nuclei = [n.nucleus for n in d.world.neighbours if n.nucleus is not None]
    # plant cells always lie in a tissue, wall against wall: the neighbours are always drawn
    wall = d.piece(d.path(walls), None, fill=d.colors.fill(WALL_HUE, 0.42), stroke=d.colors.ink(WALL_HUE), px=1.1)
    body = d.piece(d.path(cells), None, fill=d.colors.fill(CELL_HUES["plant"], 0.3))
    vacuoles = [RoundedBox(c.cx + c.width * 0.1, c.cy, c.width * 0.62, c.height * 0.66, c.height * 0.2) for c in cells if isinstance(c, RoundedBox)]
    sap = d.piece(d.path(vacuoles), "neighbours", fill=d.colors.fill(KINDS["vacuole"].hue, 0.22))
    nuc = d.piece(d.path(nuclei), "neighbours", fill=d.colors.fill(KINDS["nucleus"].hue, 0.4), stroke=d.colors.ink(KINDS["nucleus"].hue), px=MEMBRANE_PX)
    line = d.piece(d.path(cells), None, stroke=d.colors.ink(MEMBRANE_HUE), px=PLASMA_PX * 0.7)
    return VGroup(wall, body, sap, nuc, line)


def cell(d: "CellDrawing") -> VGroup:
    """The wall (cellulose; its outer face the middle lamella), the cytosol, the plasma
    membrane, and the plasmodesmata: channels through both cells' walls lined by the plasma
    membrane (continuous from cell to cell) round a desmotubule of appressed ER."""
    world = d.world
    wall_shape = world.envelope[0][1]
    wall = d.piece(d.path([wall_shape]), None, fill=d.colors.fill(WALL_HUE, 0.42))
    lamella = d.piece(d.path([wall_shape]), None, stroke=d.colors.ink(WALL_HUE), px=1.1)
    cytosol_hue = d.colors.fill(CELL_HUES["plant"], 0.3)
    cytosol = d.piece(d.path([world.cell]), None, fill=cytosol_hue)
    plasma = d.membrane([world.cell], MEMBRANE_HUE, px=PLASMA_PX)
    mouths, tubes = [], []
    linings: list = []
    for channel in world.channels:
        assert isinstance(channel, Capsule)
        n = (math.cos(channel.angle), math.sin(channel.angle))
        across = (-n[1], n[0])
        reach = channel.length / 2
        half = channel.width / 2

        def at(u: float, v: float) -> tuple[float, float]:
            return (channel.cx + n[0] * u + across[0] * v, channel.cy + n[1] * u + across[1] * v)

        inner = half - BILAYER / 2
        mouths.append(polygon([at(-reach - 0.012, -inner), at(reach + 0.012, -inner), at(reach + 0.012, inner), at(-reach - 0.012, inner)]))
        linings += [line(at(-reach, -half), at(reach, -half)), line(at(-reach, half), at(reach, half))]
        tubes.append(Capsule(channel.cx, channel.cy, 2 * reach - 0.01, DESMOTUBULE, channel.angle))
    er = KINDS["rough_er"].hue
    parts = [wall, lamella, cytosol, plasma]
    if world.channels:
        parts.append(d.piece(d.curves([c for m in mouths for c in m]), None, fill=cytosol_hue))
        parts.append(d.membrane(linings, MEMBRANE_HUE, px=PLASMA_PX * 0.8, lipids=False))
        parts.append(d.piece(d.path(tubes), None, fill=d.colors.fill(er, 0.6), stroke=d.colors.ink(er), px=0.8, true_um=BILAYER))
    return VGroup(*parts)


def vacuole(d: "CellDrawing", thing: Placed) -> VGroup:
    """The central vacuole: cell sap inside the tonoplast."""
    hue = KINDS["vacuole"].hue
    shape = thing.footprint[0]
    sap = d.piece(d.path([shape]), None, fill=d.colors.fill(hue, 0.26))
    if d.style_of(thing) == "surface":
        return VGroup(sap, highlight(d, shape, hue), closeup.surface(d, thing, shape), d.membrane([shape], hue, lipids=False))
    return VGroup(sap, d.membrane([shape], hue))


def chloroplast(d: "CellDrawing", thing: Placed) -> VGroup:
    """Section: the envelope's two membranes (one line until they part on screen), the stroma,
    grana as blocks until single thylakoids show, then the thylakoid membranes round one
    continuous lumen; starch grains and plastoglobuli. Surface: the whole lens-shaped body."""
    hue = KINDS["chloroplast"].hue
    outer = thing.footprint[0]
    assert isinstance(outer, Ellipse)
    if d.style_of(thing) == "surface":
        return VGroup(d.piece(d.path([outer]), None, fill=d.colors.fill(hue, 0.55)), highlight(d, outer, hue), closeup.surface(d, thing, outer),
                      d.membrane([outer], hue, px=MEMBRANE_PX * 1.2, lipids=False))
    inner = outer.inset(CHLOROPLAST_GAP + BILAYER)
    discs = list(thing.option("discs", ()))
    lamellae = list(thing.option("lamellae", ()))
    ims = d.piece(d.path([outer]), None, fill=d.colors.fill(hue, 0.45))
    stroma = d.piece(d.path([inner]), None, fill=d.colors.fill(hue, 0.22))
    blocks = _grana_blocks(discs)
    grana = d.piece(d.path(blocks), "!thylakoids", fill=d.colors.fill(hue, 0.75))
    lamella_lines = d.piece(d.path(lamellae), "!thylakoids", fill=d.colors.fill(hue, 0.6))
    region = thing.parts[1].membranes[0][1]
    lumen = d.piece(d.curves(region.curves()), "thylakoids", fill=d.colors.fill(hue, 0.62))  # type: ignore[attr-defined]
    membranes = d.membrane(region.curves(), hue, "thylakoids", px=MEMBRANE_PX * 0.6)  # type: ignore[attr-defined]
    starch = d.piece(d.path(thing.option("starch", ())), None, fill=d.colors.light("#F2EBD3", 0.2), stroke=d.colors.ink("#C9B98A"), px=0.8)
    rng_dots = [Ellipse(inner.cx + inner.a * f * math.cos(inner.angle) - inner.b * g * math.sin(inner.angle),
                        inner.cy + inner.a * f * math.sin(inner.angle) + inner.b * g * math.cos(inner.angle), 0.03, 0.03)
                for f, g in ((-0.55, -0.55), (0.12, 0.62), (0.62, -0.4), (-0.18, -0.68))]
    globuli = d.piece(d.path(rng_dots), None, fill=d.colors.ink(hue))
    single = d.membrane([outer], hue, "!plastid_double", px=MEMBRANE_PX * 1.2, lipids=False)
    both = VGroup(d.membrane([outer], hue, "plastid_double"), d.membrane([inner], hue, "plastid_double"))
    return VGroup(ims, stroma, grana, lamella_lines, lumen, membranes, starch, globuli, single, both)


def _grana_blocks(discs: list[Capsule]) -> list[RoundedBox]:
    """One block per granum (its stacked discs) for the view from afar."""
    stacks: list[list[Capsule]] = []
    for disc in discs:
        if stacks and math.dist(stacks[-1][-1].center(), disc.center()) < 0.05:
            stacks[-1].append(disc)
        else:
            stacks.append([disc])
    out = []
    for stack in stacks:
        a, b = stack[0], stack[-1]
        height = math.dist(a.center(), b.center()) + a.width
        mid = ((a.cx + b.cx) / 2, (a.cy + b.cy) / 2)
        out.append(RoundedBox(mid[0], mid[1], a.length, height, a.width / 2, a.angle))
    return out


__all__ = ["cell", "chloroplast", "tissue", "vacuole"]
