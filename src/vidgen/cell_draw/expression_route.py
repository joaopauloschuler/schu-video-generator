"""Drawing a gene's route through a cell (DESIGN.md §95.11): its markers — mRNAs (a short strand
with its cap), ribosomes, protein chains, a COPII vesicle, a secretory vesicle, a clathrin-coated
vesicle — kept a few pixels across at any zoom (their real sizes, 5–100 nm, would vanish at the
scale of organelles) and placed each frame at their world points."""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
from manim import Circle, Dot, Mobject, RegularPolygon, VGroup, VMobject

from vidgen.cellworld.expression_route import MARKER_PX, RoutePlanner, RoutePose

from .base import CellColors

#: Marker hues: mRNA, ribosome, protein, vesicle coats.
HUES = {"mrna": "#E07A5F", "ribosome": "#5E7FC0", "protein": "#4FA35E", "vesicle": "#C9A86A", "copii": "#E08A3C", "coated": "#7A6FB0"}


class RouteDrawing:
    """The markers of a :class:`RoutePlanner` as mobjects, one per marker, made at the size they
    have on screen when the camera is not zoomed (scene units of ``ref_pixels`` per unit)."""

    def __init__(self, planner: RoutePlanner, colors: CellColors, ref_pixels: float, z: float) -> None:
        self.planner, self.colors, self.ref = planner, colors, ref_pixels
        self.mobs: dict[str, Mobject] = {}
        self.rest: dict[str, list[tuple[VMobject, float, float]]] = {}
        self.applied: dict[str, float] = {}
        for m in planner.markers:
            mob = self._make(m.kind)
            mob.set_z_index(z)
            self.mobs[m.key] = mob
            self.rest[m.key] = [(v, float(v.get_fill_opacity()), float(v.get_stroke_opacity())) for v in mob.get_family()
                                if isinstance(v, VMobject) and len(v.points)]
            self.applied[m.key] = 1.0
        self.group = VGroup(*self.mobs.values())
        self.hidden: dict[str, list[tuple[VMobject, np.ndarray]]] = {}
        for key in self.mobs:
            self._hide(key, True)

    def _px(self, px: float) -> float:
        return px / self.ref

    def _make(self, kind: str) -> Mobject:
        c = self.colors
        size = self._px(MARKER_PX[kind])
        hue = HUES[kind]
        if kind == "mrna":
            pts = [np.array([size * (k / 24 - 0.5), size * 0.12 * math.sin(k / 24 * 4 * math.pi), 0.0]) for k in range(25)]
            strand = VMobject(stroke_color=c.solid(hue), stroke_width=self._stroke(5.0))
            strand.set_points_smoothly(pts)
            cap = Dot(pts[0], radius=size * 0.1, color=c.ink("#D9534F"))
            return VGroup(strand, cap)
        if kind == "ribosome":
            large = Circle(radius=size * 0.5, stroke_width=0, fill_color=c.solid(hue), fill_opacity=1.0)
            small = Circle(radius=size * 0.36, stroke_width=0, fill_color=c.solid("#9DBFD6"), fill_opacity=1.0).shift(np.array([0, -size * 0.45, 0]))
            return VGroup(small, large)
        if kind == "protein":
            return Circle(radius=size * 0.5, stroke_width=self._stroke(1.0), stroke_color=c.ink(hue), fill_color=c.solid(hue), fill_opacity=1.0)
        body = Circle(radius=size * 0.5, stroke_width=self._stroke(2.0), stroke_color=c.ink("#C9A86A"), fill_color=c.fill("#C9A86A", 0.4),
                      fill_opacity=0.9)
        if kind == "vesicle":
            return body
        coat = VGroup()
        n = 10 if kind == "copii" else 7
        for k in range(n):
            a = 2 * math.pi * k / n
            spot = np.array([size * 0.62 * math.cos(a), size * 0.62 * math.sin(a), 0.0])
            piece: Mobject = (Dot(spot, radius=size * 0.09, color=c.solid(hue)) if kind == "copii" else
                              RegularPolygon(6, radius=size * 0.13, stroke_width=self._stroke(1.2), stroke_color=c.solid(hue), fill_opacity=0.0).move_to(spot))
            coat.add(piece)
        return VGroup(body, coat)

    def _stroke(self, px: float) -> float:
        """A stroke width (Manim's units) of ``px`` pixels when the camera is not zoomed."""
        return px * 100 / self.ref

    def _hide(self, key: str, hidden: bool) -> None:
        if hidden == (key in self.hidden):
            return
        mob = self.mobs[key]
        if hidden:
            self.hidden[key] = [(m, m.points.copy()) for m in mob.get_family() if len(m.points)]
            for m, _ in self.hidden[key]:
                m.clear_points()
        else:
            for m, points in self.hidden.pop(key):
                m.set_points(points)

    def apply(self, pose: RoutePose, to_scene: Callable[[tuple[float, float]], np.ndarray], s: float) -> None:
        """Put the markers where ``pose`` has them, ``s`` times their unzoomed size (the camera's
        scale now), so they keep their size on screen."""
        for key, (x, y, o) in pose.els.items():
            mob = self.mobs[key]
            if o <= 0.01:
                self._hide(key, True)
                continue
            self._hide(key, False)
            if abs(s / self.applied[key] - 1) > 1e-9:
                mob.scale(s / self.applied[key])
                for m in mob.get_family():
                    if isinstance(m, VMobject) and m.get_stroke_width() > 0:
                        m.set_stroke(width=m.get_stroke_width() * s / self.applied[key], family=False)
                self.applied[key] = s
            mob.move_to(to_scene((x, y)))
            for m, fill, stroke in self.rest[key]:
                m.set_fill(opacity=fill * o, family=False)
                m.set_stroke(opacity=stroke * o, family=False)


__all__ = ["HUES", "RouteDrawing"]
