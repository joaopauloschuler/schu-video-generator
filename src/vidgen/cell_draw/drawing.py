"""Drawing a cell world with Manim (DESIGN.md §95.6, §95.9): the renderer of the three-layer
design (the world and its rules are in :mod:`vidgen.cellworld`, without manim). Shapes become
exact cubic Bézier paths in scene units (``unit`` scene units per µm), so the camera can zoom
from a tissue down to the lipids of one membrane and every outline stays true. Each drawn piece
belongs to a level-of-detail feature; :meth:`CellDrawing.update` sets what is seen and the
stroke widths for the camera's current scale (strokes keep their width on screen). Molecular
detail (lipids, tubulin, actin subunits, a membrane's surface) is drawn only round the
``closeups``: the views the scene will show at the complex level."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np
from manim import VGroup, VMobject

from vidgen.cellworld import BILAYER, KINDS, MOLECULES, CellWorld, Placed, lod_weights
from vidgen.cellworld.catalog import CELL_HUES, MEMBRANE_HUE
from vidgen.cellworld.curves import Cubic, shape_curves

from . import bacteria, closeup, cytoskeleton, molecules, organelles, plant
from .base import MEMBRANE_PX, PLASMA_PX, CellColors, Pieces, curves_array, path_mobject

#: Drawing layers (z index) by kind: what lies over what.
LAYERS = {"vacuole": 0.0, "microtubule": 1.0, "actin_filament": 1.0, "actin_cortex": 1.0, "stress_fiber": 1.0,
          "intermediate_filament": 1.0, "nucleus": 2.0, "nucleoid": 2.0, "nucleolus": 2.2, "rough_er": 3.0, "smooth_er": 4.0, "golgi": 5.0,
          "vesicle": 7.0, "flagellum": 6.5, "pilus": 6.4}
#: Complexes lie over structures; those bound to a membrane over the joined ER (pores, ribosomes).
COMPLEX_LAYER, BOUND_LAYER, OTHER_LAYER = 8.0, 3.5, 6.0
#: Closeups: molecular detail is drawn within this many view spans of a close-up's centre.
CLOSEUP_REACH = 1.6
#: A view is a close-up (molecular detail drawn round it) when it spans at most this (µm).
CLOSEUP_SPAN = 0.45


class CellDrawing:
    """The drawing of a :class:`CellWorld` at ``unit`` scene units per µm with the world's
    origin at ``origin`` (scene units): ``tissue`` (the neighbouring cells), ``cell`` (its
    envelope, cytosol and plasma membrane) and ``groups[entry id]`` for each structure (with the
    complexes bound to it: pores, ribosomes, buds' vesicles), each entry of filaments and each
    entry of free complexes, in the entries' order (``order``). ``closeups`` are ``(centre,
    span)`` of the views the scene will show close up; ``style`` is the default drawing of
    structures (``section``: cut open, as in a thin section; ``surface``: whole, seen from
    outside), which an object's ``style`` option overrides."""

    def __init__(self, world: CellWorld, colors: CellColors, unit: float, origin: Sequence[float],
                 closeups: Sequence[tuple[tuple[float, float], float]] = (), style: str = "section") -> None:
        self.world, self.colors, self.unit = world, colors, unit
        self.origin = np.array([origin[0], origin[1], 0.0])
        self.style = style
        self.closeups = [(c, s) for c, s in closeups if s <= CLOSEUP_SPAN]
        self.lod = Pieces()
        self.groups: dict[str, VGroup] = {}
        self.order: list[str] = []
        self.lod.owner = "tissue"
        self.tissue = self._layer(self._tissue(), -2.0)
        self.lod.owner = "cell"
        self.cell = self._layer(self._cell(), -1.0)
        for entry in world.entries:
            category = KINDS[entry.kind].category
            self.lod.owner = entry.owner or entry.id         # pieces belong to the thing an action targets
            if category == "structure" and entry.owner is None:
                things = [world.thing(k) for k in entry.keys]
                self.groups[entry.id] = self._layer(VGroup(*[self.structure(t) for t in things]), LAYERS.get(entry.kind, OTHER_LAYER))
                self.order.append(entry.id)
            elif category == "filament":
                things = [world.thing(k) for k in entry.keys]
                self.groups[entry.id] = self._layer(cytoskeleton.filaments(self, entry.kind, things), LAYERS.get(entry.kind, OTHER_LAYER))
                self.order.append(entry.id)
        for entry in world.entries:
            things = [world.thing(k) for k in entry.keys]
            self.lod.owner = entry.owner or entry.id
            if KINDS[entry.kind].category == "structure" and entry.owner is not None:
                drawn = self._layer(VGroup(*[self.structure(t) for t in things]), LAYERS.get(entry.kind, OTHER_LAYER))
                self.groups[entry.owner].add(drawn)
            elif KINDS[entry.kind].category == "complex":
                drawn = self.complexes(entry.kind, things)
                if entry.owner is not None:      # pores and bound ribosomes belong to their structure
                    self.groups[entry.owner].add(self._layer(drawn, BOUND_LAYER))
                else:
                    self.groups[entry.id] = self._layer(drawn, COMPLEX_LAYER)
                    self.order.append(entry.id)
        self.lod.owner = None

    @property
    def pieces(self) -> list:
        return self.lod.pieces

    def all_groups(self) -> list[VGroup]:
        """Everything, back to front."""
        return [self.tissue, self.cell, *(self.groups[e] for e in self.order)]

    @staticmethod
    def _layer(mob: VGroup, z: float) -> VGroup:
        for m in mob.get_family():
            m.z_index = z + (m.z_index if m.z_index and abs(m.z_index) < 0.5 else 0.0)
        return mob

    # ----- helpers --------------------------------------------------------------------------

    def path(self, shapes: Iterable[object], grow: float = 0.0) -> VMobject:
        return path_mobject((cv for s in shapes for cv in curves_array(shape_curves(s, grow))), self.unit, self.origin)

    def curves(self, curves: Iterable[Cubic]) -> VMobject:
        return path_mobject(curves_array(curves), self.unit, self.origin)

    def piece(self, mob: VMobject, feature: str | None, *, fill: str | None = None, stroke: str | None = None, px: float = 0.0,
              true_um: float | None = None, z: float = 0.0) -> VMobject:
        """Register a drawn piece: shown by ``feature`` (an expression of
        :func:`~.base.feature_weight`), filled with ``fill``, outlined with ``stroke`` ``px``
        pixels wide (or ``true_um`` µm when wider on screen); ``z`` lifts it within its group."""
        mob.set_fill(fill or self.colors.background, opacity=1.0 if fill else 0.0)
        mob.set_stroke(stroke or self.colors.text, width=0.0, opacity=1.0 if stroke else 0.0)
        if z:
            mob.z_index = z
        self.lod.add(mob, feature, 1.0 if fill else 0.0, 1.0 if stroke else 0.0, px, true_um)
        return mob

    def membrane(self, outline: Sequence[object] | list[Cubic], hue: str, feature: str | None = None, px: float = MEMBRANE_PX,
                 lipids: bool = True) -> VGroup:
        """A membrane (``outline``: shapes or Bézier pieces of bilayer middles): a line ``px``
        wide that becomes its true 5 nm bilayer (two leaflets either side of a thin midplane)
        when that is wider on screen, and its lipids round the close-ups (``lipids``).
        ``feature`` adds a condition (``!double_membrane``)."""
        curves = list(outline) if outline and isinstance(outline[0], tuple) else [cv for s in outline for cv in shape_curves(s)]
        ink = self.colors.ink(hue)
        base = f"{feature}&" if feature else ""
        line = self.piece(self.curves(curves), base + "!bilayer", stroke=ink, px=px)
        band = self.piece(self.curves(curves), base + "bilayer&!lipids", stroke=ink, true_um=BILAYER)
        tails = self.piece(self.curves(curves), base + "bilayer&lipids", stroke=self.colors.fill(closeup.TAIL_HUE, 0.35), true_um=BILAYER)
        midplane = self.piece(self.curves(curves), base + "bilayer&!lipids", stroke=self.colors.fill(hue, 0.3), px=1.6)
        if lipids and self.closeups:
            under, over = closeup.lipids(self, curves, feature)
            return VGroup(under, line, band, tails, midplane, over)
        return VGroup(line, band, tails, midplane)

    def near_closeup(self, bounds: tuple[float, float, float, float]) -> list[tuple[tuple[float, float], float]]:
        """The close-ups (centre, reach) whose reach meets ``bounds`` (µm)."""
        x0, y0, x1, y1 = bounds
        out = []
        for (cx, cy), span in self.closeups:
            reach = span * CLOSEUP_REACH
            if x0 - reach <= cx <= x1 + reach and y0 - reach <= cy <= y1 + reach:
                out.append(((cx, cy), reach))
        return out

    def style_of(self, thing: Placed) -> str:
        return thing.option("style") or self.style

    # ----- tissue and cell ------------------------------------------------------------------

    def _tissue(self) -> VGroup:
        if self.world.kind == "plant":
            return plant.tissue(self)
        if self.world.kind == "bacterium":
            return bacteria.colony(self)
        if not self.world.neighbours:
            return VGroup()
        cells = [n.cell for n in self.world.neighbours]
        nuclei = [n.nucleus for n in self.world.neighbours if n.nucleus is not None]
        fill = self.piece(self.path(cells), "neighbours", fill=self.colors.fill(CELL_HUES["animal"], 0.28))
        nuc = self.piece(self.path(nuclei), "neighbours", fill=self.colors.fill(KINDS["nucleus"].hue, 0.4),
                         stroke=self.colors.ink(KINDS["nucleus"].hue), px=MEMBRANE_PX)
        line = self.piece(self.path(cells), "neighbours", stroke=self.colors.ink(MEMBRANE_HUE), px=PLASMA_PX * 0.8)
        return VGroup(fill, nuc, line)

    def _cell(self) -> VGroup:
        if self.world.kind == "plant":
            return plant.cell(self)
        if self.world.kind == "bacterium":
            return bacteria.cell(self)
        cytosol = self.piece(self.path([self.world.cell]), None, fill=self.colors.fill(CELL_HUES["animal"], 0.32))
        plasma = self.membrane([self.world.cell], MEMBRANE_HUE, px=PLASMA_PX)
        extra = closeup.glycocalyx(self, shape_curves(self.world.cell)) if self.closeups else VGroup()
        return VGroup(cytosol, plasma, extra)

    # ----- structures and complexes -----------------------------------------------------------

    def structure(self, thing: Placed) -> VGroup:
        """A structure's drawing (by its kind and style)."""
        draw = {"nucleus": organelles.nucleus, "nucleolus": organelles.nucleolus, "rough_er": organelles.rough_er,
                "smooth_er": organelles.smooth_er, "golgi": organelles.golgi, "mitochondrion": organelles.mitochondrion,
                "centrosome": organelles.centrosome, "chloroplast": plant.chloroplast, "vacuole": plant.vacuole,
                "nucleoid": bacteria.nucleoid}.get(thing.kind, organelles.small)
        return draw(self, thing)

    def complexes(self, kind_name: str, things: list[Placed]) -> VGroup:
        if kind_name == "nuclear_pore":
            return organelles.pores(self, things)
        if kind_name in ("kinesin", "dynein", "myosin"):
            return cytoskeleton.motors(self, kind_name, things)
        if kind_name == "plasmid":
            return bacteria.plasmids(self, things)
        if kind_name in MOLECULES:
            return molecules.cell_molecules(self, kind_name, things)
        return organelles.particles(self, kind_name, things)

    # ----- level of detail ------------------------------------------------------------------

    def weights(self, px_per_um: float, span: float) -> dict[str, float]:
        return lod_weights(px_per_um, self.world.size, span)

    def update(self, px_per_um: float, span: float, stroke_unit: float, extra: dict[str, float] | None = None) -> None:
        """Show each piece by its feature's weight at ``px_per_um`` and ``span`` (µm across the
        body), with stroke widths in pixels (``stroke_unit``: Manim stroke width per pixel at the
        camera's current zoom). Pixels are those of a 1080-pixel shorter side whatever the
        resolution, so a preview shows what the final video shows. ``extra`` gives the weights of
        the scene's own features (``@…``: its labels)."""
        self.lod.apply({**self.weights(px_per_um, span), **(extra or {})}, px_per_um, stroke_unit)

    def sync(self) -> None:
        """Keep what an action did to the pieces' opacity (a dim, a highlight) as their emphasis
        (call every frame)."""
        self.lod.sync()


def ring_angle(p: tuple[float, float], q: tuple[float, float]) -> float:
    return math.atan2(q[1] - p[1], q[0] - p[0])


__all__ = ["CellDrawing", "LAYERS"]
