"""Drawing the gene-expression close-up (DESIGN.md §95.11): one mobject per :class:`Look` of an
:class:`~vidgen.cellworld.expression_stage.ExpressionStage` — nucleotide tiles with their
letters, proteins and complexes with their names, tRNAs with their anticodons, amino acids with
their codes, the cap, N-glycans in SNFG symbols, membranes with their lipids, a nuclear pore —
the backbones drawn through them and the pairing rungs, all made once; :meth:`apply` puts a
pose on them every frame (places, opacities, the camera). Things off the view lose their points
(they cost nothing to draw); things at the view's edge fade."""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
from manim import Circle, Line, Mobject, Polygon, Rectangle, RoundedRectangle, VGroup, VMobject

from vidgen.cellworld.expression_stage import TILE, ExpressionStage, Look, Pose

from .base import CellColors, blend, luminance

#: Glycan symbols (SNFG): the sugars of Glc₃Man₉GlcNAc₂ (kind, x, y, linked to) in slots round
#: the glyph's middle, its root GlcNAc at the bottom (the one on the Asn).
GLYCAN = (
    ("GlcNAc", 0.0, -1.85, None), ("GlcNAc", 0.0, -1.4, 0), ("Man", 0.0, -0.95, 1),                    # chitobiose core, β-Man
    ("Man", -0.5, -0.5, 2), ("Man", -0.5, -0.05, 3), ("Man", -0.5, 0.4, 4),                              # α1-3 arm (D1)
    ("Man", 0.5, -0.5, 2), ("Man", 0.2, -0.05, 6), ("Man", 0.2, 0.4, 7), ("Man", 0.8, -0.05, 6), ("Man", 0.8, 0.4, 9),   # α1-6 arm (D2, D3)
    ("Glc", -0.5, 0.85, 5), ("Glc", -0.5, 1.3, 11), ("Glc", -0.5, 1.75, 12),                             # Glc₃ on the D1 arm
)
#: Backbone widths by line kind (slots).
LINE_WIDTH = {"dna": 0.16, "rna": 0.16, "chain": 0.14}
#: Keys drawn where the stage puts them even at or beyond the view's edge (the strands' end
#: labels, the legend and the protein's readout under the view).
PINNED = ("end_", "legend", "pep")


class ExpressionDrawing:
    """The mobjects of a stage in a body of the scene: ``unit`` scene units per slot, ``center``
    the body's middle (the camera's point lands there), ``half`` the body's half size; ``text``
    makes a markup text of a height (scene units) and colour."""

    def __init__(self, stage: ExpressionStage, colors: CellColors, unit: float, center: np.ndarray, half: tuple[float, float],
                 text: Callable[[str, float, str], Mobject], dim: str) -> None:
        self.stage, self.colors, self.unit, self.center, self.half = stage, colors, unit, center, half
        self.text, self.dim = text, dim
        self.mobs: dict[str, Mobject] = {}
        self.rest: dict[str, list[tuple[VMobject, float, float]]] = {}
        self.radius: dict[str, float] = {}
        self.anchors: dict[str, list[np.ndarray]] = {}       # tRNA anticodon tiles (offsets, scene units)
        self.state: dict[str, tuple[float, float, float]] = {}
        self.stash: dict[str, list[tuple[VMobject, np.ndarray]]] = {}
        self.fade = 1.0
        self.origin: dict[str, np.ndarray] = {}                # where each glyph's own (0, 0) is now
        for key in stage.looks:
            self.origin[key] = np.zeros(3)
        for key, look in stage.looks.items():
            mob = self._make(look)
            mob.set_z_index(look.z)
            self.mobs[key] = mob
            self.rest[key] = [(m, float(m.get_fill_opacity()), float(m.get_stroke_opacity())) for m in mob.get_family()
                              if isinstance(m, VMobject) and len(m.points)]
            self.radius[key] = max(look.w, look.h, 1.0) / 2 + 0.6 if look.kind not in ("membrane",) else 1e9
        backbone = blend(colors.text, colors.background, 0.55)
        self.line_color = {"dna": backbone, "rna": blend("#C07A50", colors.background, 0.8), "chain": blend("#9A7A5A", colors.text, 0.6)}
        self.lines = {name: VMobject(stroke_width=self._px(LINE_WIDTH["rna"]), stroke_color=backbone).set_z_index(1.5) for name in stage.line_names}
        self.lines["chain"].set_z_index(4.8)
        self.rungs = {name: VMobject(stroke_width=self._px(0.09), stroke_color=self.dim).set_z_index(1.8) for name in stage.rung_names}
        self.group = VGroup(*self.lines.values(), *self.rungs.values(), *self.mobs.values())
        for key in self.mobs:
            self._hide(key, True)
        for mob in [*self.lines.values(), *self.rungs.values()]:
            mob.clear_points()

    # ----- making ---------------------------------------------------------------------------------

    def _px(self, slots: float) -> float:
        """A stroke width (Manim's units, ~1/100 of a scene unit) of ``slots``."""
        return max(0.8, slots * self.unit * 100)

    def _tile(self, letter: str, hue: str, size: float = TILE) -> VGroup:
        u = self.unit
        fill = self.colors.solid(hue) if letter != "I" else self.colors.solid("#9A9A9A")
        box = RoundedRectangle(width=size * u, height=size * u, corner_radius=0.14 * u, stroke_width=0, fill_color=fill, fill_opacity=1.0)
        ink = "#FFFFFF" if luminance(fill) < 0.5 else "#1A1A1A"
        letter_mob = self.text(letter, 0.5 * u, ink).move_to(box.get_center())
        return VGroup(box, letter_mob)

    def _make(self, look: Look) -> Mobject:
        u, c = self.unit, self.colors
        kind = look.kind
        if kind == "base":
            return self._tile(look.text, look.hue, look.w)
        if kind == "blob":
            return self._blob(look)
        if kind == "bead":
            fill = c.solid(look.hue)
            disc = Circle(radius=look.w / 2 * u, stroke_width=self._px(0.05), stroke_color=c.ink(look.hue), fill_color=fill, fill_opacity=1.0)
            ink = "#FFFFFF" if luminance(fill) < 0.5 else "#1A1A1A"
            height = 0.34 * u if len(look.text) > 1 else 0.48 * u
            words = self.text(look.text, height, ink)
            if words.width > look.w * u * 0.86:
                words.scale_to_fit_width(look.w * u * 0.86)
            return VGroup(disc, words.move_to(disc.get_center()))
        if kind == "dot":
            return Circle(radius=look.w / 2 * u, stroke_width=0, fill_color=c.solid(look.hue), fill_opacity=1.0)
        if kind == "trna":
            return self._trna(look)
        if kind == "cap":
            body = RoundedRectangle(width=look.w * u, height=look.h * u, corner_radius=0.3 * u, stroke_width=self._px(0.05),
                                    stroke_color=c.ink(look.hue), fill_color=c.solid(look.hue), fill_opacity=1.0)
            words = self.text(look.text, 0.46 * u, "#FFFFFF" if luminance(c.solid(look.hue)) < 0.5 else "#1A1A1A").move_to(body.get_center())
            link = Line(body.get_right(), body.get_right() + np.array([0.45 * u, 0.0, 0.0]), stroke_width=self._px(0.16),
                        color=blend("#C07A50", c.background, 0.8))
            ppp = self.text("ppp", 0.32 * u, self.dim).next_to(link, np.array([0.0, -1.0, 0.0]), buff=0.06 * u)
            return VGroup(link, body, words, ppp)
        if kind == "glycan":
            return self._glycan(look)
        if kind == "label":
            color = self.dim if look.hue == "dim" else (c.text if not look.hue else c.ink(look.hue))
            words = self.text(look.text, look.h * u, color)
            if dict(look.data).get("anchor") == "left":
                words.shift(np.array([words.width / 2 - words.get_center()[0], 0.0, 0.0]))
            return words
        if kind == "box":
            box = Rectangle(width=look.w * u, height=look.h * u, stroke_width=self._px(0.11), stroke_color=c.ink(look.hue), fill_opacity=0.0)
            if look.text:
                words = self.text(look.text, 0.46 * u, c.ink(look.hue)).next_to(box, np.array([0.0, -1.0, 0.0]), buff=0.12 * u)
                return VGroup(box, words)
            return box
        if kind == "bracket":
            w = look.w * u
            s = -1.0 if dict(look.data).get("below") else 1.0
            line = VMobject(stroke_width=self._px(0.09), stroke_color=c.ink(look.hue))
            line.set_points_as_corners([[-w / 2, -0.25 * u * s, 0], [-w / 2, 0, 0], [w / 2, 0, 0], [w / 2, -0.25 * u * s, 0]])
            words = self.text(look.text, 0.5 * u, c.ink(look.hue)).next_to(line, np.array([0.0, s, 0.0]), buff=0.1 * u)
            return VGroup(line, words)
        if kind == "bar":
            bar = RoundedRectangle(width=max(look.w - 0.15, 0.3) * u, height=look.h * u, corner_radius=look.h * u / 2, stroke_width=0,
                                   fill_color=c.solid(look.hue), fill_opacity=0.9)
            words = self.text(look.text, 0.46 * u, c.ink(look.hue)).next_to(bar, np.array([0.0, -1.0, 0.0]), buff=0.08 * u)
            return VGroup(bar, words)
        if kind == "arrow":
            ink = c.ink(look.hue)
            stem = VMobject(stroke_width=self._px(0.11), stroke_color=ink)
            stem.set_points_as_corners([[-0.6 * u, -0.5 * u, 0], [-0.6 * u, 0.3 * u, 0], [0.5 * u, 0.3 * u, 0]])
            tip = Polygon([0.85 * u, 0.3 * u, 0], [0.45 * u, 0.52 * u, 0], [0.45 * u, 0.08 * u, 0], stroke_width=0, fill_color=ink, fill_opacity=1.0)
            words = self.text(look.text, 0.5 * u, ink).next_to(stem, np.array([-1.0, 0.0, 0.0]), buff=0.08 * u)
            return VGroup(stem, tip, words)
        if kind == "membrane":
            return self._membrane(look)
        if kind == "pore":
            return self._pore(look)
        raise ValueError(f"unknown look kind {kind}")

    def _blob(self, look: Look) -> Mobject:
        u, c = self.unit, self.colors
        w, h = look.w * u, look.h * u
        fill, ink = c.fill(look.hue, 0.6), c.ink(look.hue)
        style = {"stroke_width": self._px(0.06), "stroke_color": ink, "fill_color": fill, "fill_opacity": 0.82}
        if look.shape == "ellipse":
            from manim import Ellipse
            shape: Mobject = Ellipse(width=w, height=h, **style)
        elif look.shape == "channel":
            half = (w - 0.5 * u) / 2
            shape = VGroup(*[RoundedRectangle(width=half, height=h, corner_radius=0.3 * u, **style).shift(np.array([s * (half / 2 + 0.25 * u), 0, 0]))
                             for s in (-1, 1)])
        elif look.shape == "barrel":
            wall = 1.4 * u
            shape = VGroup(*[RoundedRectangle(width=wall, height=h, corner_radius=0.5 * u, **style).shift(np.array([s * (w / 2 - wall / 2), 0, 0]))
                             for s in (-1, 1)],
                           RoundedRectangle(width=w, height=1.0 * u, corner_radius=0.4 * u, **style).shift(np.array([0, -h / 2 + 0.5 * u, 0])))
        else:
            radius = min(w, h) * (0.5 if look.shape == "rod" else 0.3)
            shape = RoundedRectangle(width=w, height=h, corner_radius=radius, **style)
        if look.key in ("pol", "small", "large", "sp_0", "sp_1", "sp_2", "cct"):
            for m in shape.get_family():
                if isinstance(m, VMobject):
                    m.set_fill(opacity=0.5)
        if not look.text:
            return shape
        dx, dy = 0.0, 0.0
        for item in look.data:
            if item[0] == "label_at":
                dx, dy = item[1], item[2]
        size = 0.5 if min(look.w, look.h) < 2.0 or len(look.text) > 14 else 0.6
        words = self.text(look.text, size * u, c.text)
        if dx == 0 and dy == 0 and words.width > w * 0.92:
            words.scale_to_fit_width(w * 0.92)
        words.move_to(np.array([dx * u, dy * u, 0.0]))
        if look.key == "pol":
            words.move_to(np.array([0.0, h / 2 - 0.55 * u, 0.0]))
        return VGroup(shape, words)

    def _trna(self, look: Look) -> Mobject:
        u, c = self.unit, self.colors
        h = look.h
        fill, ink = c.fill(look.hue, 0.7), c.ink(look.hue)
        style = {"stroke_width": self._px(0.05), "stroke_color": ink, "fill_color": fill, "fill_opacity": 0.95}
        bottom = -h / 2
        loop = RoundedRectangle(width=2.95 * u, height=1.05 * u, corner_radius=0.3 * u, **style).move_to(np.array([0, (bottom + 0.48) * u, 0]))
        stem = RoundedRectangle(width=1.0 * u, height=(h - 1.2) * u, corner_radius=0.35 * u, **style).move_to(np.array([0.15 * u, (bottom + 1.0 + (h - 1.2) / 2) * u, 0]))
        elbow = RoundedRectangle(width=1.7 * u, height=0.8 * u, corner_radius=0.3 * u, **style).move_to(np.array([-0.55 * u, (h / 2 - 0.9) * u, 0]))
        parts: list[Mobject] = [stem, elbow, loop]
        offsets = []
        for j, letter in enumerate(look.text):
            tile = self._tile(letter, _hue(letter), 0.82)
            off = np.array([(j - 1) * 0.92 * u, (bottom + 0.48) * u, 0.0])
            tile.move_to(off)
            offsets.append(off)
            parts.append(tile)
        self.anchors[look.key] = offsets
        return VGroup(*parts)

    def _glycan(self, look: Look) -> Mobject:
        u, c = self.unit, self.colors
        glc = dict(look.data).get("glc", 3)
        keep = [k for k, s in enumerate(GLYCAN) if s[0] != "Glc" or k < len(GLYCAN) - 3 + glc]
        r = 0.18 * u
        links, symbols = [], []
        for k in keep:
            kind, x, y, parent = GLYCAN[k]
            at = np.array([x * u, y * u, 0.0])
            if parent is not None:
                _, px, py, _ = GLYCAN[parent]
                links.append(Line(np.array([px * u, py * u, 0.0]), at, stroke_width=self._px(0.05), color=self.dim))
            colour = {"Glc": "#0072BC", "Man": "#00A651", "GlcNAc": "#0072BC"}[kind]
            if kind == "GlcNAc":
                sym: Mobject = Rectangle(width=2 * r, height=2 * r, stroke_width=self._px(0.03), stroke_color=c.text, fill_color=colour, fill_opacity=1.0)
            else:
                sym = Circle(radius=r, stroke_width=self._px(0.03), stroke_color=c.text, fill_color=colour, fill_opacity=1.0)
            symbols.append(sym.move_to(at))
        stalk = Line(np.array([0.0, -2.05 * u, 0.0]), np.array([-1.0 * u, -2.5 * u, 0.0]), stroke_width=self._px(0.05), color=self.dim)
        return VGroup(stalk, *links, *symbols)

    def _membrane(self, look: Look) -> Mobject:
        u, c = self.unit, self.colors
        reach = 46.0
        gaps = [(item[1] - item[2] / 2, item[1] + item[2] / 2) for item in look.data if item[0] == "gap"]
        h = look.h
        band = Rectangle(width=2 * reach * u, height=h * u, stroke_width=0, fill_color=c.fill("#E8C77A", 0.45), fill_opacity=1.0)
        heads = VGroup()
        x = -reach
        while x <= reach:
            if not any(a - 0.3 <= x <= b + 0.3 for a, b in gaps):
                for s in (1, -1):
                    heads.add(Circle(radius=0.3 * u, stroke_width=0, fill_color=c.solid("#C9A86A"), fill_opacity=1.0).move_to(np.array([x * u, s * (h / 2 - 0.3) * u, 0.0])))
            x += 0.75
        cuts = VGroup()
        for a, b in gaps:
            cuts.add(Rectangle(width=(b - a) * u, height=h * u * 1.02, stroke_width=0, fill_color=c.background, fill_opacity=1.0).move_to(np.array([(a + b) / 2 * u, 0, 0])))
        return VGroup(band, cuts, heads)

    def _pore(self, look: Look) -> Mobject:
        u, c = self.unit, self.colors
        fill, ink = c.fill(look.hue, 0.7), c.ink(look.hue)
        style = {"stroke_width": self._px(0.05), "stroke_color": ink, "fill_color": fill, "fill_opacity": 0.95}
        gap = look.w
        pillars = [RoundedRectangle(width=1.1 * u, height=4.2 * u, corner_radius=0.4 * u, **style).move_to(np.array([s * (gap / 2 + 0.3) * u, 0, 0]))
                   for s in (-1, 1)]
        basket = VMobject(stroke_width=self._px(0.07), stroke_color=ink)
        basket.set_points_as_corners([[-(gap / 2) * u, -2.1 * u, 0], [-0.7 * u, -3.3 * u, 0], [0.7 * u, -3.3 * u, 0], [(gap / 2) * u, -2.1 * u, 0]])
        fils = [Line(np.array([s * (gap / 2 + 0.3) * u, 2.1 * u, 0]), np.array([s * (gap / 2 + 1.3) * u, 3.1 * u, 0]), stroke_width=self._px(0.07), color=ink)
                for s in (-1, 1)]
        words = self.text(look.text, 0.5 * u, self.dim).move_to(np.array([-(gap / 2 + 1.2) * u, 3.6 * u, 0.0]))
        words.shift(np.array([-words.width / 2 + 1.0 * u, 0, 0]))
        return VGroup(*pillars, basket, *fils, words)

    # ----- applying a pose --------------------------------------------------------------------------

    def to_scene(self, x: float, y: float, cam: tuple[float, float]) -> np.ndarray:
        return np.array([self.center[0] + (x - cam[0]) * self.unit, self.center[1] + (y - cam[1]) * self.unit, 0.0])

    def _hide(self, key: str, hidden: bool) -> None:
        if hidden == (key in self.stash):
            return
        mob = self.mobs[key]
        if hidden:
            self.stash[key] = [(m, m.points.copy()) for m in mob.get_family() if len(m.points)]
            for m, _ in self.stash[key]:
                m.clear_points()
        else:
            for m, points in self.stash.pop(key):
                m.set_points(points)

    def _edge(self, x: float, y: float, cam: tuple[float, float], r: float) -> float:
        """How much of a thing at ``(x, y)`` shows at the view's edge (1 well inside, 0 at the
        edge's last slot: the strands' end labels sit there)."""
        hx, hy = self.half[0] / self.unit, self.half[1] / self.unit
        dx = hx - abs(x - cam[0])
        dy = hy - abs(y - cam[1])
        return max(0.0, min(1.0, (dx - 0.9) / 1.0, (dy - 0.2) / 1.0))

    def apply(self, pose: Pose, fade: float = 1.0) -> None:
        """Put ``pose`` on the mobjects (all of it at ``fade`` of its opacity: an entrance)."""
        self.fade = fade
        cam = pose.cam
        hx, hy = self.half[0] / self.unit, self.half[1] / self.unit
        for key, (x, y, o) in pose.els.items():
            mob = self.mobs.get(key)
            if mob is None:
                continue
            r = self.radius[key]
            look = self.stage.looks[key]
            pinned = key.startswith(PINNED)
            far = not pinned and (abs(x - cam[0]) > hx + r or abs(y - cam[1]) > hy + r)
            if pinned:
                edge = 1.0
            elif look.kind in ("membrane", "pore"):              # long things fade only at the top and bottom
                edge = max(0.0, min(1.0, (hy - abs(y - cam[1]) - look.h / 2 + 0.6) / 1.0))
            elif look.kind == "blob" and max(look.w, look.h) > 6.0:
                # a large complex (a ribosomal subunit, the polymerase) stays while any of it shows
                edge = max(0.0, min(1.0, (hx - abs(x - cam[0]) + look.w / 2 - 1.0) / 1.0, (hy - abs(y - cam[1]) + look.h / 2 - 1.0) / 1.0))
            else:
                edge = self._edge(x, y, cam, r)
            alpha = o * edge * fade
            if alpha <= 0.004 or (far and look.kind != "membrane"):
                self._hide(key, True)
                self.state[key] = (x, y, 0.0)
                continue
            self._hide(key, False)
            old = self.state.get(key)
            target = self.to_scene(x, y, cam)
            origin = self.origin[key]
            if abs(target[0] - origin[0]) > 1e-7 or abs(target[1] - origin[1]) > 1e-7:
                mob.shift(target - origin)
                self.origin[key] = target
            if old is None or abs(old[2] - alpha) > 0.003:
                for m, fill, stroke in self.rest[key]:
                    m.set_fill(opacity=fill * alpha, family=False)
                    m.set_stroke(opacity=stroke * alpha, family=False)
            self.state[key] = (x, y, alpha)
        self._lines(pose)
        self._rungs(pose)

    def point(self, key: str, pose: Pose) -> np.ndarray | None:
        """The scene point of a key (``tr3#1``: a tRNA's anticodon tile)."""
        sub = None
        if "#" in key:
            key, sub = key.split("#")
        if key not in pose.els:
            return None
        x, y, _ = pose.els[key]
        q = self.to_scene(x, y, pose.cam)
        if sub is not None:
            q = q + self.anchors[key][int(sub)]
        return q

    def _lines(self, pose: Pose) -> None:
        for name, mob in self.lines.items():
            keys, dy, hue, alpha = pose.lines.get(name, ((), 0.0, "rna", 0.0))
            pts = [self.to_scene(pose.els[k][0], pose.els[k][1] + dy, pose.cam) for k in keys
                   if k in pose.els and pose.els[k][2] > 0.05 and self.state.get(k, (0, 0, 0))[2] > 0.0]
            if alpha <= 0.01 or len(pts) < 2:
                mob.clear_points()
                continue
            mob.set_points_as_corners(pts)
            mob.set_stroke(color=self.line_color.get(hue, self.line_color["rna"]), width=self._px(LINE_WIDTH.get(hue, 0.16)), opacity=alpha * self.fade)

    def _rungs(self, pose: Pose) -> None:
        half = TILE / 2 * self.unit
        for name, mob in self.rungs.items():
            a, b, alpha = pose.rungs.get(name, ("", "", 0.0))
            if alpha <= 0.02 or not a:
                if len(mob.points):
                    mob.clear_points()
                continue
            pa, pb = self.point(a, pose), self.point(b, pose)
            ka, kb = a.split("#")[0], b.split("#")[0]
            if pa is None or pb is None or self.state.get(ka, (0, 0, 0))[2] <= 0 or self.state.get(kb, (0, 0, 0))[2] <= 0:
                if len(mob.points):
                    mob.clear_points()
                continue
            d = pb - pa
            n = float(np.linalg.norm(d))
            if n <= 2 * half + 1e-6:
                if len(mob.points):
                    mob.clear_points()
                continue
            v = d / n
            mob.set_points_as_corners([pa + v * half, pb - v * half])
            mob.set_stroke(opacity=alpha * min(self.state[ka][2], self.state[kb][2]))


def _hue(letter: str) -> str:
    from vidgen.cellworld.glyphs import BASE_HUES
    return BASE_HUES.get(letter, "#9A9A9A")


__all__ = ["ExpressionDrawing", "GLYCAN"]
