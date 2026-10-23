"""Drawings of a bacterium (DESIGN.md §95.9): its envelope — Gram-negative: the inner
(plasma) membrane, the periplasm with a thin peptidoglycan layer, the outer membrane (LPS on its
outer leaflet); Gram-positive: the plasma membrane under a thick peptidoglycan wall — and an
optional capsule; the nucleoid (the chromosome's region, no membrane) with its looped DNA,
plasmids, and a colony of cells round it. Flagella and pili are drawn with the filaments."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from manim import VGroup

from vidgen.cellworld import KINDS, Capsule, Ellipse, Placed, Region
from vidgen.cellworld.catalog import CAPSULE_HUE, CELL_HUES, MEMBRANE_HUE, PERIPLASM, THIN_WALL, WALL_HUE
from vidgen.cellworld.curves import smooth
from vidgen.cellworld.morphology import rng_for

from .base import MEMBRANE_PX, PLASMA_PX

if TYPE_CHECKING:
    from .drawing import CellDrawing

DNA_HUE = "#5A4A9A"


def colony(d: "CellDrawing") -> VGroup:
    """The bacteria round the cell."""
    rods = [n.cell for n in d.world.neighbours]
    body = d.piece(d.path(rods), "neighbours", fill=d.colors.fill(CELL_HUES["bacterium"], 0.36), stroke=d.colors.ink(MEMBRANE_HUE), px=PLASMA_PX * 0.7)
    return VGroup(body)


def cell(d: "CellDrawing") -> VGroup:
    """The envelope and the cytoplasm."""
    world = d.world
    parts = []
    layers = dict(world.envelope)
    if "capsule" in layers:
        parts.append(d.piece(d.path([layers["capsule"]]), None, fill=d.colors.fill(CAPSULE_HUE, 0.35), stroke=d.colors.fill(CAPSULE_HUE, 0.7), px=0.8))
    cytoplasm_hue = CELL_HUES["bacterium"]
    if world.gram == "negative":
        outer = layers["periplasm"]
        parts.append(d.piece(d.path([outer]), None, fill=d.colors.fill(cytoplasm_hue, 0.18)))
        assert isinstance(world.cell, Capsule) and isinstance(outer, Capsule)
        mid = world.cell.inset(-PERIPLASM * 0.62)
        layer = Region.of(mid.inset(-THIN_WALL / 2)).minus(mid.inset(THIN_WALL / 2))
        parts.append(d.piece(d.curves(layer.curves()), None, fill=d.colors.fill(WALL_HUE, 0.8)))
        parts.append(d.piece(d.path([world.cell]), None, fill=d.colors.fill(cytoplasm_hue, 0.32)))
        parts.append(d.membrane([outer], MEMBRANE_HUE, px=MEMBRANE_PX * 1.2))
        parts.append(d.membrane([world.cell], MEMBRANE_HUE, px=MEMBRANE_PX * 1.2))
    else:
        wall = layers["cell_wall"]
        parts.append(d.piece(d.path([wall]), None, fill=d.colors.fill(WALL_HUE, 0.62), stroke=d.colors.ink(WALL_HUE), px=0.8))
        parts.append(d.piece(d.path([world.cell]), None, fill=d.colors.fill(cytoplasm_hue, 0.32)))
        parts.append(d.membrane([world.cell], MEMBRANE_HUE, px=PLASMA_PX))
    return VGroup(*parts)


def nucleoid(d: "CellDrawing", thing: Placed) -> VGroup:
    """The nucleoid: a lobed region (no membrane) where the chromosome's DNA loops."""
    hue = KINDS["nucleoid"].hue
    shape = thing.footprint[0]
    assert isinstance(shape, Ellipse)
    rng = rng_for("nucleoid", thing.key)
    lobes = [shape]
    for k in range(7):
        t = (k + rng.uniform(0, 0.6)) / 7
        p = shape.point(t)
        r = shape.b * rng.uniform(0.35, 0.6)
        lobes.append(Ellipse(p[0] * 0.85 + shape.cx * 0.15, p[1] * 0.85 + shape.cy * 0.15, r, r * rng.uniform(0.7, 1.0), rng.uniform(0, math.pi)))
    region = Region.of(*lobes)
    body = d.piece(d.curves(region.curves()), None, fill=d.colors.fill(hue, 0.28))
    points = []
    p = shape.center()
    for _ in range(90):
        a = rng.uniform(0, 2 * math.pi)
        step = shape.b * 0.32
        q = (p[0] + step * math.cos(a), p[1] + step * math.sin(a))
        if shape.contains(q, -shape.b * 0.08):
            points.append(q)
            p = q
    dna = d.piece(d.curves(smooth(points, closed=True)), None, stroke=d.colors.ink(DNA_HUE), px=0.9, true_um=0.002)
    return VGroup(body, dna)


def plasmids(d: "CellDrawing", things: list[Placed]) -> VGroup:
    """Plasmids: small closed DNA circles, supercoiled (a twisted loop)."""
    curves = []
    for t in things:
        r = t.size / 2
        pts = []
        for k in range(16):
            a = 2 * math.pi * k / 16
            wobble = 1 + 0.35 * math.sin(3 * a)
            pts.append((t.center[0] + r * wobble * math.cos(a + t.angle), t.center[1] + r * 0.55 * wobble * math.sin(a + t.angle) * math.cos(a)))
        curves += smooth(pts, closed=True)
    hue = KINDS["plasmid"].hue
    dot = d.piece(d.path([Ellipse(t.center[0], t.center[1], t.size / 2, t.size / 3) for t in things]), "!fine", fill=d.colors.fill(hue, 0.6))
    loop = d.piece(d.curves(curves), "fine", stroke=d.colors.ink(hue), px=1.0, true_um=0.002)
    return VGroup(dot, loop)


__all__ = ["cell", "colony", "nucleoid", "plasmids"]
