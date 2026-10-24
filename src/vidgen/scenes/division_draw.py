"""Mitosis and meiosis drawn (DESIGN.md §95.13): the keyframes of
``vidgen.cellworld.division`` as mobjects — chromatids as round-capped strokes in segments
coloured by origin (maternal and paternal hues, a shade per pair; exchanged segments in the
partner's colour), kinetochores, spindle microtubules, cell outlines with the contractile ring
or the plant cell's wall and cell plate, nuclear envelopes breaking down and reforming,
centrosomes, the synaptonemal complex — and interpolated item by item between keyframes.
Written against ``vidgen.api``."""

from collections.abc import Callable
from typing import Any

import numpy as np

from vidgen.api import *

#: Room round the cells in a view (local units), and how much larger than the last view a view
#: may draw (one cell at the start is not drawn huge).
VIEW_PAD, MAX_ZOOM = 0.35, 1.45


def _mix(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _box_size(division: Any, k: int, portrait: bool) -> tuple[tuple[float, float], float, float]:
    x0, y0, x1, y1 = division.extent(k)
    w, h = (y1 - y0, x1 - x0) if portrait else (x1 - x0, y1 - y0)
    return ((x0 + x1) / 2, (y0 + y1) / 2), w + VIEW_PAD, h + VIEW_PAD


def division_views(division: Any, area: Any, portrait: bool) -> list[tuple[tuple[float, float], float]]:
    """Each keyframe's view: the centre of its cells and the scene units per local unit that
    fit them in ``area`` (at most :data:`MAX_ZOOM` times the last keyframe's)."""
    views = []
    for k in range(len(division.keyframes)):
        mid, w, h = _box_size(division, k, portrait)
        views.append((mid, min(area.width / w, area.height / h)))
    final = views[-1][1]
    return [(mid, min(unit, final * MAX_ZOOM)) for mid, unit in views]


def division_height(division: Any, area: Any, portrait: bool) -> float:
    """The height the drawing takes at most in ``area`` (its tallest view)."""
    views = division_views(division, area, portrait)
    return max(_box_size(division, k, portrait)[2] * unit for k, (_, unit) in enumerate(views))


class DivisionDrawing:
    """Mobjects for every item of a planned division; :meth:`show` draws the state between two
    keyframes. Each keyframe has its own view (the cells it shows fill ``area``; turned a
    quarter for a portrait frame), interpolated with the items, so one cell at the start is drawn
    larger than the four at the end."""

    def __init__(self, scene: Any, division: Any, area: Any, portrait: bool, colors: dict[str, str], label_size: float) -> None:
        self.scene = scene
        self.division = division
        self.area = area
        self.portrait = portrait
        self.views = division_views(division, area, portrait)
        self.view = self.views[0]
        self.colors = colors
        self.mobs: dict[str, VMobject] = {}
        first = division.keyframes[0].items
        groups: dict[str, list[Mobject]] = {"cell": [], "under": [], "mt": [], "chrom": [], "over": [], "label": []}
        for key, item in first.items():
            mob = self._make(key, item, label_size)
            self.mobs[key] = mob
            groups[self._layer(item.kind)].append(mob)
        self.layers = {name: VGroup(*mobs) for name, mobs in groups.items()}
        self.group = VGroup(*self.layers.values())
        self.chromatid_ids = [ch.id for ch in division.chromatids]

    @property
    def unit(self) -> float:
        """Scene units per local unit in the view drawn now."""
        return self.view[1]

    def to_scene(self, pt: tuple[float, float]) -> np.ndarray:
        mid, unit = self.view
        x, y = pt[0] - mid[0], pt[1] - mid[1]
        if self.portrait:
            x, y = y, -x
        return self.area.center + unit * np.array([x, y, 0.0])

    @staticmethod
    def _layer(kind: str) -> str:
        return {"cell": "cell", "ring": "over", "plate": "over", "envelope": "under", "nucleolus": "under", "mt": "mt",
                "chromatid": "chrom", "kinetochore": "chrom", "sc": "chrom", "centrosome": "over", "ppb": "over",
                "label": "label"}.get(kind, "over")

    # ----- making ------------------------------------------------------------------------------

    def _make(self, key: str, item: Any, label_size: float) -> VMobject:
        c = self.colors
        kind = item.kind
        if kind == "chromatid":
            segs = VGroup(*[VMobject() for _ in range(len(item.points) - 1)])
            for s in segs:
                s.set_cap_style(CapStyleType.ROUND)
            return segs
        if kind == "cell":
            m = VMobject()
            m.set_fill(c["cytoplasm"], opacity=1).set_stroke(c["membrane"], width=6 if self.division.spec.cell == "plant" else 3)
            return m
        if kind == "envelope":
            return VGroup(*[VMobject().set_stroke(c["envelope"], width=2.6) for _ in range(12)])
        if kind == "mt":
            tone = c["mt_astral"] if item.colors and item.colors[0] == "astral" else c["mt"]
            m = VMobject().set_stroke(tone, width=1.6)
            return m
        if kind == "label":
            t = self.scene.markup(str(item.extra), size=label_size, color=c["ink"])
            return VGroup(plate_behind(t, c["bg"]), t)
        if kind == "centrosome":
            a = Rectangle(width=0.5, height=0.16).set_fill(c["centriole"], opacity=1).set_stroke(width=0)
            b = Rectangle(width=0.5, height=0.16).set_fill(c["centriole"], opacity=1).set_stroke(width=0).rotate(PI / 2)
            halo = Circle(radius=0.6).set_fill(c["centriole"], opacity=0.18).set_stroke(width=0)
            return VGroup(halo, a, b)
        if kind == "sc":
            return VMobject().set_stroke(c["sc"], width=2.0)
        if kind == "plate":
            return VMobject().set_stroke(c["plate"], width=5)
        dot = Circle(radius=1.0).set_stroke(width=0)
        dot.set_fill({"kinetochore": c["kinetochore"], "nucleolus": c["nucleolus"], "ring": c["ring"], "ppb": c["mt"]}.get(kind, c["ink"]),
                     opacity=1)
        return dot

    # ----- drawing a state ---------------------------------------------------------------------

    def show(self, ka: int, kb: int, t: float) -> None:
        """Draw the state ``t`` (0–1) of the way from keyframe ``ka`` to ``kb``."""
        a, b = self.division.keyframes[ka], self.division.keyframes[kb]
        (ma, ua), (mb, ub) = self.views[ka], self.views[kb]
        self.view = (_mix(ma, mb, t), ua + (ub - ua) * t)
        for key, mob in self.mobs.items():
            ia, ib = a.items[key], b.items[key]
            op = ia.opacity + (ib.opacity - ia.opacity) * t
            pts = [_mix(p, q, t) for p, q in zip(ia.points, ib.points)]
            width = ia.width + (ib.width - ia.width) * t
            self._paint(key, mob, ia, ib, t, pts, width, op)

    def _paint(self, key: str, mob: VMobject, ia: Any, ib: Any, t: float, pts: list[tuple[float, float]], width: float, op: float) -> None:
        c = self.colors
        kind = ia.kind
        to = self.to_scene
        if kind == "chromatid":
            sw = max(1.2, width * self.unit * 100)
            for j, seg in enumerate(mob):
                seg.set_points_as_corners([to(pts[j]), to(pts[j + 1])])
                ca, cb = c[ia.colors[j]], c[ib.colors[j]]
                seg.set_stroke(interpolate_color(ManimColor(ca), ManimColor(cb), t) if ca != cb else ca, width=sw, opacity=op)
            return
        if kind == "cell":
            mob.set_points_as_corners([to(p) for p in pts] + [to(pts[0])])
            mob.set_fill(opacity=op).set_stroke(opacity=op)
            return
        if kind == "envelope":
            broken = float(ia.extra) + (float(ib.extra) - float(ia.extra)) * t
            n = len(pts) - 1
            per = n // 12
            keep = 1.0 - 0.65 * broken
            for j, arc in enumerate(mob):
                seg = pts[j * per: j * per + per + 1]
                cut = max(2, int(round(len(seg) * keep)))
                arc.set_points_smoothly([to(p) for p in seg[:cut]])
                arc.set_stroke(opacity=op * (1 - 0.5 * broken))
            return
        if kind in ("mt", "sc", "plate"):
            if len(pts) >= 2 and np.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 1e-6:
                mob.set_points_as_corners([to(pts[0]), to(pts[0]) + RIGHT * 1e-4])
                mob.set_stroke(opacity=0)
                return
            mob.set_points_as_corners([to(p) for p in pts])
            mob.set_stroke(opacity=op * (0.8 if kind == "mt" else 1.0))
            return
        if kind == "label":     # below its cell's centre on screen, whichever way the frame turns
            mob.move_to(to(pts[0]) + DOWN * width * self.unit)
            mob[0].set_fill(opacity=0.8 * op)
            mob[1].set_fill(opacity=op)
            return
        if kind == "centrosome":
            size = 0.05 * self.unit
            mob.scale_to_fit_width(2.4 * size)
            mob.move_to(to(pts[0]))
            mob[0].set_fill(opacity=0.18 * op)
            mob[1].set_fill(opacity=op)
            mob[2].set_fill(opacity=op)
            return
        r = max(width * self.unit, 0.012)
        mob.scale_to_fit_width(2 * r)
        mob.move_to(to(pts[0]))
        mob.set_fill(opacity=op)


def plate_behind(text: Mobject, bg: str) -> RoundedRectangle:
    p = RoundedRectangle(width=text.width + 0.16, height=text.height + 0.12, corner_radius=0.06)
    return p.set_fill(bg, opacity=0.8).set_stroke(width=0).move_to(text)
