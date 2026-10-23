"""The camera of a cell world in physical scale (DESIGN.md §95.4): named zoom levels (tissue →
cell → organelle → molecular complex), the view each gives on a target, the level of detail at
a view (what is drawn, from the size things take on screen) and the automatic scale bar. No
manim: the scene turns a :class:`CellView` into a camera frame, lint reads the same numbers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .catalog import BILAYER, KINDS, MITO_GAP, PERINUCLEAR_GAP
from .geometry import ArcBand, Ellipse, Point
from .model import CellWorld, Placed
from .units import format_length, nice_length

Level = Literal["tissue", "cell", "organelle", "complex"]
LEVELS: tuple[Level, ...] = ("tissue", "cell", "organelle", "complex")
#: How much of the body's shorter side a level's subject fills (the rest is margin).
FILL = {"tissue": 1.0, "cell": 0.93, "organelle": 0.62, "complex": 0.2}
#: The tissue view shows this many cell lengths across the body's shorter side.
TISSUE_CELLS = 3.2
#: An organelle-level view of a sheet or a tubule network shows this much of it (µm).
SHEET_VIEW = 2.6
#: A complex-level view on a membrane (no complex to centre on) shows this much (µm).
MEMBRANE_VIEW = 0.16

#: Level of detail: each feature is drawn when its size on screen (pixels) passes the first
#: number and fully from the second (faded between, on a log scale). See :func:`lod_weights`.
LOD: dict[str, tuple[float, float]] = {
    "particles": (0.5, 1.2),          # a complex as a dot (its real size)
    "particle_detail": (9.0, 16.0),   # a complex's subunits (ribosome: large and small)
    "double_membrane": (1.6, 3.2),    # the two membranes of an envelope apart (their gap)
    "bilayer": (2.5, 5.0),            # a membrane drawn as its bilayer (its thickness)
    "pores": (1.5, 3.0),              # nuclear pores (their diameter)
    "cristae": (18.0, 32.0),          # a mitochondrion's cristae (its width)
    "labels": (8.0, 14.0),            # a structure's label (its length)
}
#: Neighbouring cells fade in as the view grows from 1.25 to 1.7 cell lengths.
NEIGHBOURS = (1.25, 1.7)
#: The scale bar is about this share of the body's shorter side.
SCALE_BAR_SHARE = 0.22


@dataclass(frozen=True)
class CellView:
    """What the camera shows: the world point at the body's centre and the length (µm) that
    spans the body's shorter side; ``level`` names it."""

    center: Point
    span: float
    level: Level


def fit_span(width: float, height: float, body_aspect: float, fill: float) -> float:
    """The span (µm across the body's shorter side) at which a box ``width`` × ``height`` µm
    fills ``fill`` of a body whose width over height is ``body_aspect``."""
    short_is_width = body_aspect <= 1.0
    body_w = 1.0 if short_is_width else body_aspect
    body_h = 1.0 / body_aspect if short_is_width else 1.0
    scale = min(body_w * fill / width, body_h * fill / height)   # body units per µm, the short side being 1
    return 1.0 / scale


def _box(thing: Placed) -> tuple[float, float, float, float]:
    boxes = [s.bounds() for s in thing.footprint]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def focus_point(world: CellWorld, entry_id: str, level: Level) -> tuple[Point, float]:
    """Where a view of ``entry_id`` at ``level`` centres and the size (µm) it frames: a
    structure's middle and length; a rough ER's or smooth ER's middle sheet; at the complex level
    a complex bound to the structure (a ribosome on the rough ER, a pore of a nucleus) or a point
    on its outer membrane. An entry of several things takes its first."""
    things = world.members(entry_id)
    first = things[0]
    kind = KINDS[first.kind]
    if kind.category == "complex":
        return first.center, first.size
    if level == "complex":
        bound = [p for p in world.placed if p.surface == first.key]
        preferred = [p for p in bound if p.kind == "nuclear_pore"] or [p for p in bound if p.kind == "ribosome"] or bound
        if preferred:
            mx, my = first.center
            near = min(preferred, key=lambda p: (p.center[0] - mx) ** 2 + (p.center[1] - my) ** 2)
            return near.center, near.size
        shape = first.footprint[0]
        if isinstance(shape, Ellipse):
            return shape.point(0.12), MEMBRANE_VIEW * FILL["complex"]
        outline = shape.outline(16)
        return outline[len(outline) // 3], MEMBRANE_VIEW * FILL["complex"]
    if kind.shape in ("sheets", "tubules") and level == "organelle":
        band = first.footprint[len(first.footprint) // 2]
        return (band.center() if isinstance(band, ArcBand) else first.center), SHEET_VIEW * FILL["organelle"]
    x0, y0, x1, y1 = _box(first)
    return ((x0 + x1) / 2, (y0 + y1) / 2), max(x1 - x0, y1 - y0)


def default_level(world: CellWorld, entry_id: str) -> Level:
    """The level a view of ``entry_id`` takes when none is given: ``cell`` for the cell,
    ``tissue`` for the tissue, ``complex`` for a complex, else ``organelle``."""
    if entry_id == "cell":
        return "cell"
    if entry_id == "tissue":
        return "tissue"
    return "complex" if KINDS[world.members(entry_id)[0].kind].category == "complex" else "organelle"


def level_view(world: CellWorld, level: Level, body_aspect: float, entry_id: str | None = None, span: float | None = None) -> CellView:
    """The view at ``level`` on ``entry_id`` (``None``, ``cell`` or ``tissue``: the cell) for a
    body of aspect ``body_aspect`` (width over height); ``span`` (µm) overrides the level's."""
    middle = (world.cell.cx, world.cell.cy)
    if level == "tissue":                   # the wide levels always show the cell in the middle
        return CellView(middle, span or TISSUE_CELLS * world.size, level)
    if level == "cell":
        return CellView(middle, span or fit_span(2 * world.cell.a, 2 * world.cell.b, body_aspect, FILL["cell"]), level)
    if entry_id in (None, "cell", "tissue"):
        entry_id = next((e.id for e in world.entries if e.kind == "nucleus"), None)
        if entry_id is None:
            return CellView(middle, span or (world.size / 4 if level == "organelle" else MEMBRANE_VIEW), level)
    center, size = focus_point(world, entry_id, level)
    auto = size / FILL[level]
    if level == "organelle":
        things = world.members(entry_id)
        if KINDS[things[0].kind].shape not in ("sheets", "tubules"):
            x0, y0, x1, y1 = _box(things[0])
            auto = fit_span(max(x1 - x0, 1e-3), max(y1 - y0, 1e-3), body_aspect, FILL["organelle"])
    return CellView(center, span or max(auto, 0.05), level)


#: The zoom path's trade-off between zooming and panning (van Wijk and Nuij's ρ; √2 is their
#: recommended value): higher zooms out further to travel.
ZOOM_RHO = 1.4


def zoom_path(c0: Point, w0: float, c1: Point, w1: float, t: float) -> tuple[Point, float]:
    """Where a camera going from centre ``c0`` / width ``w0`` to ``c1`` / ``w1`` is at ``t``
    (0..1): the smooth and efficient zoom-and-pan path of van Wijk and Nuij (2003), which zooms
    out on the way when the targets are far apart for their widths (two ribosomes 5 µm apart
    are not travelled to at 100 nm wide) and changes the width at an even pace on a log scale
    when they are not."""
    ux, uy = c1[0] - c0[0], c1[1] - c0[1]
    u1 = math.hypot(ux, uy)
    rho = ZOOM_RHO
    if u1 < 1e-9 * max(w0, w1):
        w = math.exp(math.log(w0) + (math.log(w1) - math.log(w0)) * t)
        return (c0[0] + ux * t, c0[1] + uy * t), w

    def r(i: int) -> float:
        w = w1 if i else w0
        b = (w1 * w1 - w0 * w0 + (-1) ** i * rho ** 4 * u1 * u1) / (2 * w * rho * rho * u1)
        return math.log(-b + math.sqrt(b * b + 1))

    r0, r1 = r(0), r(1)
    s = t * (r1 - r0) / rho
    u = w0 / rho ** 2 * (math.cosh(r0) * math.tanh(rho * s + r0) - math.sinh(r0))
    w = w0 * math.cosh(r0) / math.cosh(rho * s + r0)
    if t >= 1.0:
        u, w = u1, w1
    return (c0[0] + ux / u1 * u, c0[1] + uy / u1 * u), w


def smooth_fade(value: float, lo: float, hi: float) -> float:
    """0 below ``lo``, 1 above ``hi``, a smoothstep between on a log scale."""
    if value <= lo:
        return 0.0
    if value >= hi:
        return 1.0
    t = (math.log(value) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return t * t * (3 - 2 * t)


def lod_weights(px_per_um: float, cell_size: float, span: float) -> dict[str, float]:
    """How much of each level-of-detail feature is drawn at ``px_per_um`` (pixels per µm on
    screen) with ``span`` µm across the body: ``particles`` (ribosomes as dots, at their 25 nm),
    ``ribosome_detail``, ``double_membrane`` (an envelope's two membranes apart at their 30 nm
    gap; a mitochondrion's at 20 nm: ``mito_double``), ``bilayer`` (5 nm), ``pores`` (120 nm),
    ``cristae`` (at a 0.7 µm mitochondrion's width), ``labels`` (per structure length: see
    :func:`label_weight`), ``neighbours`` (the tissue)."""
    ribosome = KINDS["ribosome"].size * px_per_um
    return {
        "particles": smooth_fade(ribosome, *LOD["particles"]),
        "particle_detail": smooth_fade(ribosome, *LOD["particle_detail"]),
        "double_membrane": smooth_fade((PERINUCLEAR_GAP + BILAYER) * px_per_um, *LOD["double_membrane"]),
        "mito_double": smooth_fade((MITO_GAP + BILAYER) * px_per_um, *LOD["double_membrane"]),
        "bilayer": smooth_fade(BILAYER * px_per_um, *LOD["bilayer"]),
        "pores": smooth_fade(KINDS["nuclear_pore"].size * px_per_um, *LOD["pores"]),
        "cristae": smooth_fade((KINDS["mitochondrion"].width or 0.7) * px_per_um, *LOD["cristae"]),
        "neighbours": smooth_fade(span / cell_size, *NEIGHBOURS),
    }


def label_weight(size_um: float, px_per_um: float) -> float:
    """How visible a structure's label is when the structure is ``size_um`` long."""
    return smooth_fade(size_um * px_per_um, *LOD["labels"])


def scale_bar(span: float, share: float = SCALE_BAR_SHARE) -> tuple[float, str]:
    """The scale bar for a view spanning ``span`` µm: its length (µm, a 1-2-5 value near
    ``share`` of the span) and its text (``5 µm``, ``100 nm``)."""
    length = nice_length(span * share)
    return length, format_length(length)
