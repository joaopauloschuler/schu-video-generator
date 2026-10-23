"""Drawing membrane traffic in a cell (DESIGN.md §95.10): the renderer of the plans of
:mod:`vidgen.cellworld.traffic`. A membrane event (endocytosis, exocytosis) is an overlay at its
site of the plasma membrane: a cover hides the still drawing there and the membrane is drawn
anew each frame from the planned shape — its bilayer at its true 5 nm (head groups up close),
the clathrin coat, dynamin round the neck, receptors with their ligands, SNAREs, the vesicle and
its cargo — with strokes kept in pixels and details shown by level of detail like the rest."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import numpy as np
from manim import VGroup, VMobject

from vidgen.cellworld import BILAYER, KINDS
from vidgen.cellworld.catalog import CELL_HUES, COAT_HUES, MEMBRANE_HUE, WALL_HUE
from vidgen.cellworld.traffic import PIT_HALF, Shape, Site, coat_thickness

from .base import PLASMA_PX
from .closeup import HEAD_HUE, TAIL_HUE

if TYPE_CHECKING:
    from .drawing import CellDrawing

Point = tuple[float, float]
#: Dynamin's colour, a receptor's and its ligand's, the cargo's.
DYNAMIN_HUE, RECEPTOR_HUE, LIGAND_HUE, CARGO_HUE, SNARE_HUE = "#5E7FC0", "#7B6BB0", "#E39B32", "#D9A13B", "#C2569B"
#: How far the cover reaches out of and into the cell from the membrane (nm).
COVER_OUT, COVER_IN = 26.0, 250.0
#: A circle as four cubic pieces (unit radius).
_K = 0.5522847498
_CIRCLE = np.array([[[1, 0], [1, _K], [_K, 1], [0, 1]], [[0, 1], [-_K, 1], [-1, _K], [-1, 0]],
                    [[-1, 0], [-1, -_K], [-_K, -1], [0, -1]], [[0, -1], [_K, -1], [1, -_K], [1, 0]]], dtype=float)


def normals(pts: np.ndarray, closed: bool = False) -> np.ndarray:
    """Unit left normals of a polyline (to the left of the way it runs)."""
    if closed:
        d = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
    else:
        d = np.gradient(pts, axis=0)
    length = np.linalg.norm(d, axis=1, keepdims=True)
    length[length == 0] = 1.0
    d = d / length
    return np.column_stack([-d[:, 1], d[:, 0]])


def polyline_points(pts: np.ndarray) -> np.ndarray:
    """Manim points (cubic pieces, straight) of a polyline given as (n, 3) scene points."""
    a, b = pts[:-1], pts[1:]
    return np.stack([a, a + (b - a) / 3, a + 2 * (b - a) / 3, b], axis=1).reshape(-1, 3)


def dots_points(centers: np.ndarray, r: float) -> np.ndarray:
    """Manim points of circles of radius ``r`` round ``centers`` ((n, 3) scene points)."""
    if not len(centers):
        return np.zeros((0, 3))
    shape = _CIRCLE.reshape(-1, 2) * r
    out = centers[:, None, :2] + shape[None, :, :]
    flat = out.reshape(-1, 2)
    return np.column_stack([flat, np.zeros(len(flat))])


class EventDrawing:
    """The overlay of one membrane event at ``site`` of a cell drawing ``d``: its mobjects (in
    ``group``, unseen until it plays) and how to draw a :class:`~vidgen.cellworld.traffic.Shape`."""

    def __init__(self, d: CellDrawing, site: Site, kind: str, receptors: int = 0, cargo: Sequence[Point] = (), vesicle_hue: str | None = None) -> None:
        self.d, self.site, self.kind = d, site, kind
        c = d.colors
        cell_kind = d.world.kind
        self.outside_color = c.fill(WALL_HUE, 0.42) if cell_kind == "plant" else c.background
        self.cytosol_color = c.fill(CELL_HUES[cell_kind], 0.3 if cell_kind == "plant" else 0.32)
        self.ink = c.ink(MEMBRANE_HUE)

        def mob(fill: str | None = None, stroke: str | None = None) -> VMobject:
            m = VMobject()
            m.set_fill(fill or c.background, opacity=1.0 if fill else 0.0)
            m.set_stroke(stroke or c.text, width=0.0, opacity=1.0 if stroke else 0.0)
            return m

        self.cover_out = mob(self.outside_color)
        self.cover_in = mob(self.cytosol_color)
        self.lumen = mob(self.outside_color)
        self.vesicle_lumen = mob(c.fill(vesicle_hue, 0.45) if vesicle_hue else self.outside_color)
        self.coat_band = mob(c.fill(COAT_HUES["clathrin"], 0.75))
        self.line = mob(stroke=self.ink)
        self.band = mob(stroke=self.ink)
        self.tails = mob(stroke=c.fill(TAIL_HUE, 0.35))
        self.midplane = mob(stroke=c.fill(MEMBRANE_HUE, 0.3))
        self.heads = mob(c.solid(HEAD_HUE))
        self.cage = mob(stroke=c.solid(COAT_HUES["clathrin"]))
        self.dynamin = mob(stroke=c.solid(DYNAMIN_HUE))
        self.receptors = mob(stroke=c.solid(RECEPTOR_HUE))
        self.ligands = mob(c.solid(LIGAND_HUE), c.ink(LIGAND_HUE))
        self.snares = mob(stroke=c.solid(SNARE_HUE))
        self.cargo_mob = mob(c.solid(CARGO_HUE), c.ink(CARGO_HUE))
        self.group = VGroup(self.cover_out, self.cover_in, self.lumen, self.vesicle_lumen, self.coat_band, self.line, self.tails, self.band,
                            self.midplane, self.heads, self.cage, self.dynamin, self.receptors, self.ligands, self.snares, self.cargo_mob)
        for k, m in enumerate(self.group):
            m.z_index = 7.4 + k * 0.001
        self.receptor_count = receptors
        self.cargo = list(cargo)
        self.visible = 0.0
        self._cover()

    # ----- geometry ------------------------------------------------------------------------------

    def scene(self, uv: np.ndarray) -> np.ndarray:
        """Scene points of local ``(u, v)`` points (nm), along the membrane's own curve."""
        s = self.site
        u, v = uv[:, 0] / 1000.0, uv[:, 1] / 1000.0
        bend = s.curvature * u * u / 2
        x = s.point[0] + s.tangent[0] * u + s.normal[0] * (v - bend)
        y = s.point[1] + s.tangent[1] * u + s.normal[1] * (v - bend)
        world = np.column_stack([x, y, np.zeros(len(x))])
        return world * self.d.unit + self.d.origin

    def _cover(self) -> None:
        half = PIT_HALF - 6.0                  # the drawn membrane reaches a little beyond: no seam
        us = np.linspace(-half, half, 41)
        line = np.column_stack([us, np.zeros_like(us)])
        out = np.column_stack([us[::-1], np.full_like(us, COVER_OUT)])
        deep = np.column_stack([us[::-1], np.full_like(us, -COVER_IN)])
        self.cover_out.set_points_as_corners(self.scene(np.vstack([line, out, line[:1]])))
        self.cover_in.set_points_as_corners(self.scene(np.vstack([line, deep, line[:1]])))

    # ----- drawing ----------------------------------------------------------------------------------

    def draw(self, shape: Shape, weights: dict[str, float], px_per_um: float, stroke_unit: float, alpha: float = 1.0, receptors: float = 1.0,
             cargo_out: float = 0.0, cargo_at: Sequence[Point] | None = None) -> None:
        """Draw ``shape`` with the camera's level-of-detail ``weights`` (pixels per µm,
        ``stroke_unit``: Manim stroke width per pixel); ``alpha`` fades the whole overlay,
        ``receptors`` the receptors and ligands; ``cargo_at``: where the cargo is (nm)."""
        self.last = (shape, alpha, receptors, cargo_out, cargo_at)
        bilayer, lipids = weights.get("bilayer", 0.0), weights.get("lipids", 0.0)
        nm_px = px_per_um / 1000.0                     # pixels per nm

        def width(nm: float, least: float = 0.0) -> float:
            return max(least, nm * nm_px) * stroke_unit

        mem = np.array(shape.membrane)
        pts = self.scene(mem)
        closed = np.vstack([pts, pts[:1]])
        self.lumen.set_points_as_corners(closed)
        lines = [pts]
        normal_mem = normals(mem)
        rings = []
        if shape.vesicle is not None:
            depth, r = shape.vesicle
            k = np.linspace(0.0, 2 * math.pi, 181)
            circle = np.column_stack([r * np.cos(k), -depth + r * np.sin(k)])
            rings.append(circle)
            self.vesicle_lumen.set_points_as_corners(self.scene(circle))
        else:
            self.vesicle_lumen.clear_points()
        membrane_points = np.vstack([polyline_points(self.scene(np.asarray(m))) for m in [mem, *rings]])
        for m in (self.line, self.band, self.tails, self.midplane):
            m.set_points(membrane_points)
        self.line.set_stroke(width=PLASMA_PX * stroke_unit, opacity=alpha * (1 - bilayer))
        self.band.set_stroke(width=width(BILAYER * 1000), opacity=alpha * bilayer * (1 - lipids))
        self.tails.set_stroke(width=width(BILAYER * 1000), opacity=alpha * bilayer * lipids)
        self.midplane.set_stroke(width=1.6 * stroke_unit, opacity=alpha * bilayer * (1 - lipids))
        # head groups of both leaflets, up close
        if lipids > 0.01:
            heads = []
            for curve, closed_ in [(mem, False), *[(ring, True) for ring in rings]]:
                dense = _even(curve, 0.8, closed_)
                nl = normals(dense, closed_)
                for sign in (1, -1):
                    heads.append(dense + nl * sign * (BILAYER * 1000 / 2 - 0.4))
            centers = self.scene(np.vstack(heads))
            self.heads.set_points(dots_points(centers, 0.4 / 1000 * self.d.unit))
            self.heads.set_fill(opacity=alpha * lipids)
        else:
            self.heads.clear_points()
        self._coat(shape, mem, normal_mem, rings, alpha, width)
        self._dynamin(shape, alpha, width)
        self._receptors(shape, mem, normal_mem, rings, alpha * receptors, width)
        self._snares(shape, alpha, width)
        self._cargo(shape, alpha, cargo_at)
        for m in (self.cover_out, self.cover_in, self.lumen):
            m.set_fill(opacity=alpha)
        self.vesicle_lumen.set_fill(opacity=alpha * (0.9 if shape.vesicle is not None else 0.0))

    def redraw(self, weights: dict[str, float], px_per_um: float, stroke_unit: float) -> None:
        """Draw the last shape again for a new camera (strokes in pixels, level of detail)."""
        last = getattr(self, "last", None)
        if last is not None:
            shape, alpha, receptors, cargo_out, cargo_at = last
            self.draw(shape, weights, px_per_um, stroke_unit, alpha, receptors, cargo_out, cargo_at)

    def _coat(self, shape: Shape, mem: np.ndarray, normal_mem: np.ndarray, rings: list[np.ndarray], alpha: float, width: Any) -> None:
        """The clathrin coat on the cytosolic face of the pit (or round the vesicle): a band from
        afar; up close a bristly cage of triskelion legs about 18 nm deep."""
        thick = coat_thickness()
        pieces: list[np.ndarray] = []
        cage: list[np.ndarray] = []
        strength = 0.0
        if shape.coat is not None:
            a, b = shape.coat
            seg = mem[a:b + 1]
            nl = normal_mem[a:b + 1]
            inner, outer = seg - nl * (BILAYER * 1000 / 2 + 1.0), seg - nl * (BILAYER * 1000 / 2 + thick)
            pieces.append(np.vstack([inner, outer[::-1], inner[:1]]))
            cage += self._cage(inner, outer)
            strength = 1.0
        elif shape.vesicle is not None and shape.coat_on_vesicle > 0 and rings:
            ring = rings[0]
            depth, r = shape.vesicle
            center = np.array([0.0, -depth])
            d = (ring - center) / r
            inner, outer = center + d * (r + BILAYER * 1000 / 2 + 1.0), center + d * (r + BILAYER * 1000 / 2 + thick)
            pieces.append(np.vstack([inner, outer[::-1], inner[:1]]))
            cage += self._cage(inner, outer)
            strength = shape.coat_on_vesicle
        if pieces:
            self.coat_band.set_points_as_corners(self.scene(pieces[0]))
            self.cage.set_points(np.vstack([polyline_points(self.scene(c)) for c in cage]))
        else:
            self.coat_band.clear_points()
            self.cage.clear_points()
        self.coat_band.set_fill(opacity=alpha * strength * 0.6)
        self.cage.set_stroke(width=width(2.5, 1.0), opacity=alpha * strength)

    @staticmethod
    def _cage(inner: np.ndarray, outer: np.ndarray) -> list[np.ndarray]:
        """The coat's outer edge and its legs (one every ~11 nm, leaning a little)."""
        out = [outer]
        lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(outer, axis=0), axis=1))]
        total = lengths[-1]
        count = max(2, int(total / 11.0))
        for k in range(count + 1):
            j = int(np.searchsorted(lengths, total * k / count).clip(0, len(outer) - 1))
            lean = min(len(inner) - 1, j + 2)
            out.append(np.vstack([inner[lean], outer[j]]))
        return out

    def _dynamin(self, shape: Shape, alpha: float, width: Any) -> None:
        """Dynamin's helix round the neck: rings across it, tighter as it constricts."""
        if shape.neck is None:
            self.dynamin.clear_points()
            return
        w, top, bottom = shape.neck
        reach = w + BILAYER * 1000 / 2 + 7.0
        count = max(2, min(6, int(abs(bottom - top) / 7.0)))
        bars = []
        for k in range(count):
            v = top + (bottom - top) * (k + 0.5) / count
            bars.append(np.array([[-reach, v + 1.5], [reach, v - 1.5]]))      # the helix's turns lean a little
        self.dynamin.set_points(np.vstack([polyline_points(self.scene(b)) for b in bars]))
        self.dynamin.set_stroke(width=width(4.5, 1.6), opacity=alpha)

    def _receptors(self, shape: Shape, mem: np.ndarray, normal_mem: np.ndarray, rings: list[np.ndarray], alpha: float, width: Any) -> None:
        """Receptors across the bilayer with their ligands outside (in the pit's lumen)."""
        n = self.receptor_count
        if n == 0 or alpha <= 0:
            self.receptors.clear_points()
            self.ligands.clear_points()
            return
        spots: list[tuple[np.ndarray, np.ndarray]] = []
        if shape.vesicle is None:
            gather = self._gather
            lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(mem, axis=0), axis=1))]
            total = lengths[-1]
            # spread along the membrane, gathered into the middle of the pit as it forms
            deep = [k for k, p in enumerate(mem) if p[1] < -4.0]
            middle = lengths[(deep[0] + deep[-1]) // 2] if deep else total / 2
            reach = (lengths[deep[-1]] - lengths[deep[0]]) * 0.32 if deep else total * 0.06
            for k in range(n):
                spread = (k - (n - 1) / 2) / max(1, n - 1)
                loose = total / 2 + spread * total * 0.75
                tight = middle + spread * 2 * max(reach, total * 0.06)
                s = loose + (tight - loose) * gather
                j = int(np.searchsorted(lengths, s).clip(1, len(mem) - 1))
                spots.append((mem[j], normal_mem[j]))
        else:
            depth, r = shape.vesicle
            for k in range(n):
                a = -math.pi / 2 + (k - (n - 1) / 2) * 0.42
                p = np.array([r * math.cos(a), -depth + r * math.sin(a)])
                spots.append((p, -np.array([math.cos(a), math.sin(a)])))      # its lumen is inside
        rods, diamonds = [], []
        for p, nl in spots:
            rods.append(np.vstack([p - nl * 4.0, p + nl * 5.5]))
            c = p + nl * 8.5
            t = np.array([-nl[1], nl[0]])
            diamonds.append(np.vstack([c + nl * 2.6, c + t * 2.0, c - nl * 2.6, c - t * 2.0, c + nl * 2.6]))
        self.receptors.set_points(np.vstack([polyline_points(self.scene(r)) for r in rods]))
        self.receptors.set_stroke(width=width(2.2, 1.2), opacity=alpha)
        self.ligands.set_points(np.vstack([polyline_points(self.scene(dm)) for dm in diamonds]))
        self.ligands.set_fill(opacity=alpha)
        self.ligands.set_stroke(width=0.6 * width(0.0, 1.0), opacity=alpha)

    _gather = 0.0

    def _snares(self, shape: Shape, alpha: float, width: Any) -> None:
        """Trans-SNARE complexes: coiled bridges from the vesicle to the plasma membrane."""
        if not shape.snares:
            self.snares.clear_points()
            return
        coils = []
        for a, b in shape.snares:
            pa, pb = np.array(a), np.array(b)
            d = pb - pa
            length = float(np.linalg.norm(d)) or 1.0
            t = np.array([-d[1], d[0]]) / length
            k = np.linspace(0.0, 1.0, 25)
            coils.append(pa + np.outer(k, d) + np.outer(np.sin(k * 6 * math.pi) * 1.2, t))
        self.snares.set_points(np.vstack([polyline_points(self.scene(c)) for c in coils]))
        self.snares.set_stroke(width=width(1.6, 1.0), opacity=alpha)

    def _cargo(self, shape: Shape, alpha: float, cargo_at: Sequence[Point] | None) -> None:
        if not cargo_at:
            self.cargo_mob.clear_points()
            return
        centers = self.scene(np.array(cargo_at))
        self.cargo_mob.set_points(dots_points(centers, 3.0 / 1000 * self.d.unit))
        self.cargo_mob.set_fill(opacity=alpha)
        self.cargo_mob.set_stroke(width=0.0)


def _even(curve: np.ndarray, spacing: float, closed: bool) -> np.ndarray:
    """Points every ``spacing`` nm along a polyline."""
    pts = np.vstack([curve, curve[:1]]) if closed else curve
    lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    total = lengths[-1]
    count = max(2, int(total / spacing))
    s = np.linspace(0.0, total, count, endpoint=not closed)
    x = np.interp(s, lengths, pts[:, 0])
    y = np.interp(s, lengths, pts[:, 1])
    return np.column_stack([x, y])


def vesicle_hue() -> str:
    return KINDS["vesicle"].hue


__all__ = ["EventDrawing", "dots_points", "normals", "polyline_points", "vesicle_hue"]
