"""Drawing a cell world with Manim (DESIGN.md §95.5): the renderer of the three-layer design
(the world and its rules are in :mod:`vidgen.cellworld`, without manim). Shapes become exact
cubic Bézier paths in scene units (``unit`` scene units per µm), so the camera can zoom from a
tissue down to one ribosome and every outline stays true. Each drawn piece belongs to a
level-of-detail feature; :meth:`CellDrawing.update` sets what is seen and the stroke widths for
the camera's current scale (strokes are kept at a fixed width on screen)."""

from __future__ import annotations

import math
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np
from manim import VGroup, VMobject

from vidgen.cellworld import BILAYER, KINDS, ArcBand, Capsule, CellWorld, Ellipse, Placed, lod_weights
from vidgen.cellworld.catalog import CELL_HUE, MEMBRANE_HUE, PERINUCLEAR_GAP

Curves = list[np.ndarray]
#: Arc pieces are at most this many radians, so a 20 µm membrane stays within 0.1 nm of its
#: true curve at any zoom.
ARC_STEP = math.pi / 8
#: Stroke widths on screen (pixels): membranes, the plasma membrane, particles' rims.
MEMBRANE_PX, PLASMA_PX, RIM_PX = 1.6, 2.4, 0.8
#: A mitochondrion's cristae: how many per µm of its length, how far across (share of the
#: matrix) and how wide (µm).
CRISTAE_PER_UM, CRISTA_REACH, CRISTA_WIDTH = 4.0, 0.62, 0.022


# ----- Bézier paths ------------------------------------------------------------------------------


def _arc(cx: float, cy: float, r: float, a0: float, a1: float) -> Curves:
    """Cubic Bézier pieces of a circular arc from angle ``a0`` to ``a1`` (either way round)."""
    pieces = max(1, math.ceil(abs(a1 - a0) / ARC_STEP))
    step = (a1 - a0) / pieces
    k = 4 / 3 * math.tan(step / 4) * r
    out = []
    for i in range(pieces):
        a, b = a0 + i * step, a0 + (i + 1) * step
        p0 = np.array([cx + r * math.cos(a), cy + r * math.sin(a), 0.0])
        p3 = np.array([cx + r * math.cos(b), cy + r * math.sin(b), 0.0])
        p1 = p0 + k * np.array([-math.sin(a), math.cos(a), 0.0])
        p2 = p3 - k * np.array([-math.sin(b), math.cos(b), 0.0])
        out.append(np.array([p0, p1, p2, p3]))
    return out


def _line(p: Sequence[float], q: Sequence[float]) -> np.ndarray:
    a, b = np.array([p[0], p[1], 0.0]), np.array([q[0], q[1], 0.0])
    return np.array([a, a + (b - a) / 3, a + 2 * (b - a) / 3, b])


def _transform(curves: Curves, angle: float, dx: float, dy: float) -> Curves:
    c, s = math.cos(angle), math.sin(angle)
    m = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return [cv @ m.T + np.array([dx, dy, 0.0]) for cv in curves]


def shape_curves(shape: object, grow: float = 0.0) -> Curves:
    """One closed path round ``shape`` (µm), grown outwards by ``grow`` µm (negative: inwards)."""
    if isinstance(shape, Ellipse):
        unit = _arc(0.0, 0.0, 1.0, 0.0, 2 * math.pi)
        scale = np.array([shape.a + grow, shape.b + grow, 1.0])
        return _transform([cv * scale for cv in unit], shape.angle, shape.cx, shape.cy)
    if isinstance(shape, Capsule):
        h, r = shape.half, shape.radius + grow
        local = [_line((-h, -r), (h, -r)), *_arc(h, 0.0, r, -math.pi / 2, math.pi / 2), _line((h, r), (-h, r)),
                 *_arc(-h, 0.0, r, math.pi / 2, 3 * math.pi / 2)]
        return _transform(local, shape.angle, shape.cx, shape.cy)
    if isinstance(shape, ArcBand):
        half = shape.thickness / 2 + grow
        (sx, sy), (ex, ey) = shape.ends()
        return [*_arc(shape.cx, shape.cy, shape.radius + half, shape.start, shape.end),
                *_arc(ex, ey, half, shape.end, shape.end + math.pi),
                *_arc(shape.cx, shape.cy, shape.radius - half, shape.end, shape.start),
                *_arc(sx, sy, half, shape.start + math.pi, shape.start + 2 * math.pi)]
    raise TypeError(f"no path for {type(shape).__name__}")


def path_mobject(curves: Iterable[np.ndarray], unit: float, origin: np.ndarray) -> VMobject:
    """A VMobject of Bézier pieces given in µm (several closed paths are several subpaths)."""
    pieces = list(curves)
    mob = VMobject()
    if pieces:
        mob.set_points(np.concatenate(pieces) * unit + origin)
    return mob


# ----- colours -----------------------------------------------------------------------------------


def _rgb(color: str) -> tuple[float, float, float]:
    c = color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb: Sequence[float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02X}" for v in rgb)


def blend(a: str, b: str, t: float) -> str:
    """``a`` at opacity ``t`` over ``b``."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex([x * t + y * (1 - t) for x, y in zip(ra, rb)])


def luminance(color: str) -> float:
    r, g, b = _rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@dataclass(frozen=True)
class CellColors:
    """The colours of a cell drawing for a theme: ``background`` and ``text`` (theme hex);
    fills are the kinds' hues mixed into the background, outlines darker (light themes) or
    lighter (dark themes) versions of the hues."""

    background: str
    text: str

    @property
    def dark(self) -> bool:
        return luminance(self.background) < 0.4

    def fill(self, hue: str, strength: float = 0.35) -> str:
        return blend(hue, self.background, strength * (1.5 if self.dark else 1.0))

    def ink(self, hue: str) -> str:
        return blend(hue, "#FFFFFF", 0.78) if self.dark else blend(hue, "#000000", 0.62)

    def solid(self, hue: str) -> str:
        return blend(hue, self.background, 0.85)


# ----- level-of-detail pieces --------------------------------------------------------------------


@dataclass
class Piece:
    """A drawn piece and how level of detail treats it: shown with ``feature``'s weight
    (``invert``: one minus it; ``None``: always), its full fill and stroke opacity, its stroke
    width in pixels (``bilayer``: the true 5 nm when that is wider) and, for labels, the
    length that decides it (``size``)."""

    mobject: VMobject
    feature: str | None
    fill: float
    stroke: float
    px: float
    true_width: bool = False
    shown: tuple[float, float] = field(default=(-1.0, -1.0))


class CellDrawing:
    """The drawing of a :class:`CellWorld` at ``unit`` scene units per µm with the world's
    origin at ``origin`` (scene units): ``tissue`` (the neighbouring cells), ``cell`` (cytosol
    and plasma membrane) and ``groups[entry id]`` for each structure (with the complexes bound
    to it: pores, ribosomes) and each entry of free complexes, in drawing order (``order``)."""

    def __init__(self, world: CellWorld, colors: CellColors, unit: float, origin: Sequence[float]) -> None:
        self.world, self.colors, self.unit = world, colors, unit
        self.origin = np.array([origin[0], origin[1], 0.0])
        self.pieces: list[Piece] = []
        self.groups: dict[str, VGroup] = {}
        self.order: list[str] = []
        self.tissue = self._tissue()
        self.cell = self._cell()
        for entry in world.entries:
            if KINDS[entry.kind].category == "structure":
                self.groups[entry.id] = VGroup(*[self._structure(world.thing(k)) for k in entry.keys])
                self.order.append(entry.id)
        for entry in world.entries:
            if KINDS[entry.kind].category == "complex":
                group = self._complexes(entry.kind, [world.thing(k) for k in entry.keys])
                if entry.owner is not None:      # pores and bound ribosomes belong to their structure
                    self.groups[entry.owner].add(group)
                else:
                    self.groups[entry.id] = group
                    self.order.append(entry.id)

    def all_groups(self) -> list[VGroup]:
        """Everything, back to front."""
        return [self.tissue, self.cell, *(self.groups[e] for e in self.order)]

    # ----- helpers --------------------------------------------------------------------------

    def path(self, shapes: Iterable[object], grow: float = 0.0) -> VMobject:
        return path_mobject((cv for s in shapes for cv in shape_curves(s, grow)), self.unit, self.origin)

    def piece(self, mob: VMobject, feature: str | None, *, fill: str | None = None, stroke: str | None = None, px: float = 0.0,
              true_width: bool = False) -> VMobject:
        """Register a drawn piece: shown by ``feature`` (an expression of :func:`feature_weight`),
        filled with ``fill``, outlined with ``stroke`` ``px`` pixels wide (``true_width``: the
        bilayer's true width on screen)."""
        mob.set_fill(fill or self.colors.background, opacity=1.0 if fill else 0.0)
        mob.set_stroke(stroke or self.colors.text, width=0.0, opacity=1.0 if stroke else 0.0)
        self.pieces.append(Piece(mob, feature, 1.0 if fill else 0.0, 1.0 if stroke else 0.0, px, true_width))
        return mob

    def membrane(self, shapes: Sequence[object], hue: str, feature: str | None = None, px: float = MEMBRANE_PX) -> VGroup:
        """A membrane (``shapes`` are bilayer middles): a line ``px`` wide that becomes its true
        5 nm bilayer when that is wider on screen (its two leaflets either side of a thin
        midplane). ``feature`` adds a condition (``!double_membrane``)."""
        ink = self.colors.ink(hue)
        base = f"{feature}&" if feature else ""
        line = self.piece(self.path(shapes), base + "!bilayer", stroke=ink, px=px)
        band = self.piece(self.path(shapes), base + "bilayer", stroke=ink, true_width=True)
        midplane = self.piece(self.path(shapes), base + "bilayer", stroke=self.colors.fill(hue, 0.3), px=1.6)
        return VGroup(line, band, midplane)

    # ----- tissue and cell ------------------------------------------------------------------

    def _tissue(self) -> VGroup:
        if not self.world.neighbours:
            return VGroup()
        cells = [n.cell for n in self.world.neighbours]
        nuclei = [n.nucleus for n in self.world.neighbours]
        fill = self.piece(self.path(cells), "neighbours", fill=self.colors.fill(CELL_HUE, 0.28))
        nuc = self.piece(self.path(nuclei), "neighbours", fill=self.colors.fill(KINDS["nucleus"].hue, 0.4),
                         stroke=self.colors.ink(KINDS["nucleus"].hue), px=MEMBRANE_PX)
        line = self.piece(self.path(cells), "neighbours", stroke=self.colors.ink(MEMBRANE_HUE), px=PLASMA_PX * 0.8)
        return VGroup(fill, nuc, line)

    def _cell(self) -> VGroup:
        cytosol = self.piece(self.path([self.world.cell]), None, fill=self.colors.fill(CELL_HUE, 0.32))
        plasma = self.membrane([self.world.cell], MEMBRANE_HUE, px=PLASMA_PX)
        return VGroup(cytosol, plasma)

    # ----- structures -----------------------------------------------------------------------

    def _structure(self, thing: Placed) -> VGroup:
        kind = KINDS[thing.kind]
        hue = kind.hue
        if thing.kind == "nucleolus":
            return VGroup(self.piece(self.path(thing.footprint), None, fill=self.colors.fill(hue, 0.62)))
        if thing.kind == "centrosome":
            return self._centrosome(thing)
        if not thing.parts:
            return VGroup(self.piece(self.path(thing.footprint), None, fill=self.colors.fill(hue)))
        if len(thing.parts[0].membranes) == 2:
            return self._double(thing)
        fills, lines = [], []
        strengths = _golgi_strengths(len(thing.parts)) if thing.kind == "golgi" else [0.45 if kind.shape in ("sheets", "tubules") else 0.4] * len(thing.parts)
        for part, strength in zip(thing.parts, strengths):
            fills.append(self.piece(self.path([part.outer]), None, fill=self.colors.fill(hue, strength)))
        lines.append(self.membrane([p.outer for p in thing.parts], hue))
        if thing.kind == "lysosome":
            fills.append(self._granules(thing, hue))
        return VGroup(*fills, *lines)

    def _double(self, thing: Placed) -> VGroup:
        """A nucleus or a mitochondrion: the space between the membranes, the inside, and the two
        membranes, drawn as one line until they are apart on screen."""
        kind = KINDS[thing.kind]
        hue = kind.hue
        outer, inner = (m[1] for m in thing.parts[0].membranes)
        feature = "double_membrane" if thing.kind == "nucleus" else "mito_double"
        between = self.piece(self.path([outer]), None, fill=self.colors.fill(hue, 0.55 if thing.kind == "nucleus" else 0.5))
        inside = self.piece(self.path([inner]), None, fill=self.colors.fill(hue, 0.3 if thing.kind == "nucleus" else 0.38))
        parts: list[VMobject] = [between, inside]
        if thing.kind == "mitochondrion":
            parts.append(self._cristae(thing, inner, hue))
        single = self.membrane([outer], hue, "!" + feature, px=MEMBRANE_PX * 1.2)
        both = VGroup(self.membrane([outer], hue, feature), self.membrane([inner], hue, feature))
        return VGroup(*parts, single, both)

    def _cristae(self, thing: Placed, inner: object, hue: str) -> VGroup:
        """Lamellar cristae: folds of the inner membrane reaching into the matrix from either
        side, across the mitochondrion's long axis (a stylised section)."""
        assert isinstance(inner, Capsule)
        count = max(2, round(inner.length * CRISTAE_PER_UM))
        reach = inner.width * CRISTA_REACH
        folds = []
        for k in range(count):
            t = (k + 0.5) / count
            x = -inner.half - inner.radius * 0.3 + (2 * inner.half + inner.radius * 0.6) * t
            side = 1 if k % 2 == 0 else -1
            edge = inner.radius * math.sqrt(max(0.0, 1 - (max(abs(x) - inner.half, 0) / inner.radius) ** 2))
            y0, y1 = side * edge, side * (edge - reach)
            band = Capsule(0.0, 0.0, abs(y0 - y1) + CRISTA_WIDTH, CRISTA_WIDTH, math.pi / 2)
            local = shape_curves(band)
            folds.append(_transform(local, inner.angle, *_rotated(x, (y0 + y1) / 2 + side * CRISTA_WIDTH / 2, inner)))
        mob = path_mobject((cv for fold in folds for cv in fold), self.unit, self.origin)
        return VGroup(self.piece(mob, "cristae", fill=self.colors.fill(hue, 0.5), stroke=self.colors.ink(hue), px=MEMBRANE_PX * 0.8))

    def _granules(self, thing: Placed, hue: str) -> VMobject:
        shape = thing.footprint[0]
        assert isinstance(shape, Ellipse)
        rng = np.random.default_rng(zlib.crc32(thing.key.encode("utf-8")))
        dots = []
        for _ in range(5):
            r = shape.a * 0.55 * math.sqrt(rng.uniform())
            a = rng.uniform(0, 2 * math.pi)
            dots.append(Ellipse(shape.cx + r * math.cos(a), shape.cy + r * math.sin(a), shape.a * 0.12, shape.a * 0.12))
        return self.piece(self.path(dots), None, fill=self.colors.fill(hue, 0.75))

    def _centrosome(self, thing: Placed) -> VGroup:
        """Pericentriolar material round two centrioles at right angles (about 0.2 × 0.4 µm)."""
        hue = KINDS["centrosome"].hue
        halo = self.piece(self.path(thing.footprint), None, fill=self.colors.fill(hue, 0.22))
        cx, cy = thing.center
        one = Capsule(cx - 0.12, cy, 0.4, 0.2, thing.angle)
        two = Capsule(cx + 0.14, cy + 0.08, 0.4, 0.2, thing.angle + math.pi / 2)
        barrels = self.piece(self.path([one, two]), None, fill=self.colors.fill(hue, 0.7), stroke=self.colors.ink(hue), px=MEMBRANE_PX * 0.8)
        return VGroup(halo, barrels)

    # ----- complexes ------------------------------------------------------------------------

    def _complexes(self, kind_name: str, things: list[Placed]) -> VGroup:
        hue = KINDS[kind_name].hue
        if kind_name == "nuclear_pore":
            return self._pores(things)
        # dots give way to the detail: the large (60S) subunit against the membrane, the small (40S) on it
        dots = self.piece(self.path([Ellipse(t.center[0], t.center[1], t.size / 2, t.width / 2, t.angle) for t in things]),
                          "particles&!particle_detail", fill=self.colors.solid(hue), stroke=self.colors.solid(hue), px=RIM_PX)
        large, small = [], []
        for t in things:
            nx, ny = t.normal if t.normal is not None else (math.cos(t.angle), math.sin(t.angle))
            angle = math.atan2(ny, nx) + math.pi / 2
            if kind_name == "ribosome":
                large.append(Ellipse(t.center[0] - nx * 0.004, t.center[1] - ny * 0.004, 0.0125, 0.0085, angle))
                small.append(Ellipse(t.center[0] + nx * 0.0085, t.center[1] + ny * 0.0085, 0.0095, 0.0052, angle))
            else:
                large.append(Ellipse(t.center[0], t.center[1], t.size / 2, t.width / 2, t.angle))
        detail = [self.piece(self.path(large), "particle_detail", fill=self.colors.solid(hue), stroke=self.colors.ink(hue), px=RIM_PX)]
        if small:
            detail.append(self.piece(self.path(small), "particle_detail", fill=self.colors.fill(hue, 0.6), stroke=self.colors.ink(hue), px=RIM_PX))
        return VGroup(dots, *detail)

    def _pores(self, things: list[Placed]) -> VGroup:
        """Nuclear pores: a gap through both membranes (nucleoplasm meets cytosol) with the pore
        complex's rings at its rims."""
        hue = KINDS["nuclear_pore"].hue
        gaps, rims = [], []
        across = PERINUCLEAR_GAP + 2 * BILAYER + 0.01     # through both membranes
        for t in things:
            nx, ny = t.normal or (1.0, 0.0)
            along = math.atan2(ny, nx) + math.pi / 2
            gaps.append(Capsule(t.center[0], t.center[1], t.size * 0.62, across, along))
            for side in (-1, 1):
                ox, oy = -ny * side * t.size * 0.36, nx * side * t.size * 0.36
                rims.append(Capsule(t.center[0] + ox, t.center[1] + oy, across + 0.02, 0.026, along - math.pi / 2))
        gap = self.piece(self.path(gaps), "pores", fill=self.colors.fill(KINDS["nucleus"].hue, 0.3))
        rim = self.piece(self.path(rims), "pores", fill=self.colors.solid(hue), stroke=self.colors.ink(hue), px=RIM_PX)
        return VGroup(gap, rim)

    # ----- level of detail ------------------------------------------------------------------

    def weights(self, px_per_um: float, span: float) -> dict[str, float]:
        return lod_weights(px_per_um, self.world.size, span)

    def update(self, px_per_um: float, span: float, stroke_unit: float) -> None:
        """Show each piece by its feature's weight at ``px_per_um`` and ``span`` (µm across the
        body), with stroke widths in pixels (``stroke_unit``: Manim stroke width per pixel at the
        camera's current zoom). Pixels are those of a 1080-pixel shorter side whatever the
        resolution, so a preview shows what the final video shows."""
        weights = self.weights(px_per_um, span)
        bilayer_px = BILAYER * px_per_um
        for piece in self.pieces:
            factor = feature_weight(piece.feature, weights)
            px = bilayer_px if piece.true_width else piece.px
            state = (round(factor, 4), round(px * stroke_unit, 6))
            if state == piece.shown:
                continue
            piece.shown = state
            piece.mobject.set_fill(opacity=piece.fill * factor)
            piece.mobject.set_stroke(width=px * stroke_unit, opacity=piece.stroke * factor)


def feature_weight(feature: str | None, weights: dict[str, float]) -> float:
    """The weight of a feature expression: ``None`` 1; ``a&b`` the product; ``!a`` one minus."""
    if feature is None:
        return 1.0
    total = 1.0
    for term in feature.split("&"):
        value = weights[term.lstrip("!")]
        total *= 1.0 - value if term.startswith("!") else value
    return total


def _golgi_strengths(count: int) -> list[float]:
    """Cis (paler) to trans (stronger) cisternae."""
    return [0.32 + 0.3 * k / max(count - 1, 1) for k in range(count)]


def _rotated(x: float, y: float, capsule: Capsule) -> tuple[float, float]:
    c, s = math.cos(capsule.angle), math.sin(capsule.angle)
    return (capsule.cx + x * c - y * s, capsule.cy + x * s + y * c)


__all__ = ["CellColors", "CellDrawing", "Piece", "blend", "feature_weight", "path_mobject", "shape_curves"]
