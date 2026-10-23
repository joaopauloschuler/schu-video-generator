"""The molecular close-up of a membrane (DESIGN.md §95.9): which membrane a stretch of outline
is (from the compartments on its two sides), which side is its exoplasmic leaflet, and the
lipids along it — phospholipids, sterols (cholesterol; phytosterols in plants; none in
bacteria or the inner mitochondrial membrane), glycolipids only on the exoplasmic leaflet,
cardiolipin, galactolipids, LPS, rafts. Deterministic from the outline and a seed, so the
renderer and the labels agree. No manim."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .catalog import (
    BACTERIAL_PLASMA_LIPIDS, BILAYER, LIPID_HEAD, LIPID_SPACING, MEMBRANE_LIPIDS, MEMBRANES, PLANT_PLASMA_LIPIDS, Lipids,
)
from .curves import Cubic
from .geometry import Point
from .model import CellWorld
from .morphology import rng_for

#: Compartments that count as another for naming the membrane between two.
_ALIASES = {"cis_golgi_lumen": "golgi_lumen", "medial_golgi_lumen": "golgi_lumen", "trans_golgi_lumen": "golgi_lumen",
            "cell_wall": "extracellular", "capsule": "extracellular"}
_BY_PAIR = {(m.outside, m.inside): m for m in MEMBRANES.values()}
#: How far either side of a membrane's mid-line its compartments are asked (µm).
_PROBE = 0.0042
#: A lipid raft's width along the membrane (rafts are 10–200 nm nanodomains).
RAFT_WIDTH = 0.045
#: A face-on membrane's lipids are drawn this far round a close-up's centre at most (µm).
MOSAIC_REACH = 0.066


@dataclass(frozen=True)
class Lipid:
    """One lipid of a close-up: ``kind`` (``phospholipid``, ``sterol``, ``glycolipid``,
    ``cardiolipin``, ``galactolipid``, ``lps``), its head's centre, the unit vector from the
    bilayer's middle out through its head (``out``), its ``leaflet`` (``exo`` or ``cyto``), the
    ``membrane`` and whether it is in a ``raft``."""

    kind: str
    head: Point
    out: Point
    leaflet: str
    membrane: str
    raft: bool = False


def membrane_between(world: CellWorld, a: str, b: str) -> tuple[str, int] | None:
    """The membrane between compartments ``a`` (one side) and ``b`` (the other) and the side its
    exoplasmic leaflet faces (``1``: towards ``a``, ``-1``: towards ``b``)."""
    if world.gram == "negative":
        if {a, b} == {"periplasm", "cytosol"}:
            return ("bacterial_inner_membrane", 1 if a == "periplasm" else -1)
    ka, kb = _ALIASES.get(a, a), _ALIASES.get(b, b)
    for (outside, inside), membrane in _BY_PAIR.items():
        if (ka, kb) == (outside, inside):
            return (membrane.name, 1 if membrane.exo == "outside" else -1)
        if (kb, ka) == (outside, inside):
            return (membrane.name, -1 if membrane.exo == "outside" else 1)
    return None


def lipids_of(world: CellWorld, membrane: str) -> Lipids:
    """What ``membrane``'s lipids are in this cell."""
    if membrane == "plasma_membrane":
        if world.kind == "plant":
            return PLANT_PLASMA_LIPIDS
        if world.kind == "bacterium":
            return BACTERIAL_PLASMA_LIPIDS
    return MEMBRANE_LIPIDS.get(membrane, Lipids())


def samples(curves: Sequence[Cubic], center: Point, radius: float, spacing: float) -> list[tuple[Point, Point]]:
    """Points every ``spacing`` µm along ``curves`` within ``radius`` of ``center``, each with
    the unit normal to the right of the way the outline runs (out of a region's area)."""
    out: list[tuple[Point, Point]] = []
    carry = 0.0
    for p0, p1, p2, p3 in curves:
        xs = (p0[0], p1[0], p2[0], p3[0])
        ys = (p0[1], p1[1], p2[1], p3[1])
        if min(xs) > center[0] + radius or max(xs) < center[0] - radius or min(ys) > center[1] + radius or max(ys) < center[1] - radius:
            carry = 0.0
            continue
        chord = math.dist(p0, p3) + math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
        steps = max(8, int(chord / 2 / (spacing / 4)))
        prev = p0
        for k in range(1, steps + 1):
            t = k / steps
            u = 1 - t
            q = (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                 u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])
            d = math.dist(prev, q)
            carry += d
            if carry >= spacing and d > 0:
                carry -= spacing
                if math.dist(q, center) <= radius:
                    tx, ty = (q[0] - prev[0]) / d, (q[1] - prev[1]) / d
                    out.append((q, (ty, -tx)))
            prev = q
    return out


def lipid_layout(world: CellWorld, curves: Sequence[Cubic], center: Point, radius: float, key: str, rafts: Sequence[Point] = ()) -> list[Lipid]:
    """The lipids along ``curves`` within ``radius`` of ``center``: two per place (one per
    leaflet), each leaflet's kinds drawn from its membrane's composition; ``rafts`` are points
    of the plasma membrane where a raft is (more sterol and glycolipid there)."""
    rng = rng_for("lipids", key, round(center[0], 4), round(center[1], 4))
    out: list[Lipid] = []
    cached: tuple[Point, tuple[str, int] | None] | None = None
    for p, n in samples(curves, center, radius, LIPID_SPACING):
        if cached is None or math.dist(cached[0], p) > 0.012:
            a = world.compartment_at((p[0] + n[0] * _PROBE, p[1] + n[1] * _PROBE))[0]
            b = world.compartment_at((p[0] - n[0] * _PROBE, p[1] - n[1] * _PROBE))[0]
            cached = (p, membrane_between(world, a, b))
        found = cached[1]
        if found is None:
            continue
        membrane, exo = found
        lipids = lipids_of(world, membrane)
        raft = lipids.rafts and any(math.dist(p, r) < RAFT_WIDTH / 2 for r in rafts)
        for sign in (1, -1):
            out_dir = (n[0] * sign, n[1] * sign)
            head = (p[0] + out_dir[0] * (BILAYER / 2 - LIPID_HEAD / 2), p[1] + out_dir[1] * (BILAYER / 2 - LIPID_HEAD / 2))
            leaflet = "exo" if sign == exo else "cyto"
            out.append(Lipid(_pick(rng, lipids, leaflet, raft), head, out_dir, leaflet, membrane, raft))
    return out


def _pick(rng: object, lipids: Lipids, leaflet: str, raft: bool) -> str:
    r = rng.random()  # type: ignore[attr-defined]
    if lipids.lps and leaflet == "exo":
        return "lps"
    sterol = min(0.5, lipids.sterol * (1.5 if raft else 1.0))
    glyco = lipids.glycolipid * (3.0 if raft else 1.0) if leaflet == "exo" else 0.0
    for kind, share in (("sterol", sterol), ("glycolipid", glyco), ("cardiolipin", lipids.cardiolipin), ("galactolipid", lipids.galactolipid)):
        if r < share:
            return kind
        r -= share
    return "phospholipid"


def mosaic(center: Point, radius: float, inside: Callable[[Point], bool], lipids: Lipids, leaflet: str, key: str) -> list[tuple[str, Point]]:
    """A membrane seen face on round ``center``: the head groups of one leaflet packed about
    0.8 nm apart (a hexagonal packing), each ``(kind, point)``, only where ``inside`` says the
    membrane is."""
    rng = rng_for("mosaic", key, round(center[0], 4), round(center[1], 4))
    step = LIPID_SPACING * 1.06
    rows = int(radius / (step * 0.866)) + 1
    cols = int(radius / step) + 1
    out = []
    for j in range(-rows, rows + 1):
        for i in range(-cols, cols + 1):
            p = (center[0] + (i + 0.5 * (j % 2)) * step, center[1] + j * step * 0.866)
            if math.dist(p, center) <= radius and inside(p):
                out.append((_pick(rng, lipids, leaflet, False), p))
    return out


def plasma_rafts(world: CellWorld) -> list[Point]:
    """Where the plasma membrane has a lipid raft in the drawing: at the point its complex-level
    view looks at, and a few more round the cell."""
    from .view import membrane_focus

    focus, _ = membrane_focus(world)
    cell = world.cell
    return [focus] + [cell.point(t) for t in (0.31, 0.57, 0.83)]  # type: ignore[attr-defined]
