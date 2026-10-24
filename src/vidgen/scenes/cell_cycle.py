"""``cell_cycle``: the eukaryotic cell cycle and cell division at university level (DESIGN.md
§95.13). ``mode: cycle`` draws the cycle as a ring (G1 → S → G2 → M, the exit to G0, the
restriction point, the G1/S, G2/M and spindle assembly checkpoints) beside the levels of the
four cyclin–CDK complexes over the cycle, with a "now" marker on both; ``advance`` moves the
cell round the cycle and ``checkpoint`` shows what a checkpoint checks and the regulators that
pass it (cyclin D–CDK4/6 ⊣ Rb ⊣ E2F…) or arrest it (p53 → p21 ⊣ CDK2…). ``mode: mitosis`` and
``mode: meiosis`` draw a dividing cell with a chosen 2n (homologues coloured maternal /
paternal, sisters joined at the centromere): ``advance`` runs it to a stage (prophase …
cytokinesis; meiosis I and II with synapsis, crossing over and independent assortment), with
captions and the counts per cell. The model and rules are ``vidgen.cellworld.cycle`` and
``division`` (no manim); the actions are in ``scenes/cycle_actions.py``."""

import math
from functools import lru_cache
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import driven, plate, regulation_row, small_size, text_block
from .division_draw import DivisionDrawing, division_height

cy = cell_cycle_model
dv = cell_division

#: The ring's look: arcs as wide as this share of its radius; the cyclin curves' stroke.
RING_WIDTH = 0.2
CURVE_STROKE = 4.0
#: Seconds an advance takes: per full turn of the cycle (at least / at most), per keyframe of a division.
TURN_SECONDS, MIN_SECONDS, MAX_SECONDS, KEYFRAME_SECONDS = 6.0, 1.2, 8.0, 1.5
#: Colours of the cyclins: by the phase each drives (palette indices), cyclin E (G1/S) in the
#: theme's highlight.
CYCLIN_PALETTE = {"d": 0, "e": "highlight", "a": 2, "b": 3}


@lru_cache(maxsize=16)
def _division(spec: Any) -> Any:
    return dv.plan_division(spec)


@scene("cell_cycle")
class CellCycle(NarratedScene):
    """The cell cycle and cell division. ``mode: cycle`` (default): a ring of the phases G1, S,
    G2 and M (its stages marked) with the exit to G0, the restriction point and the three
    checkpoints, beside the levels of cyclin D–CDK4/6, cyclin E–CDK2, cyclin A–CDK2 and cyclin
    B–CDK1 over the cycle (stylised, in the right order of rise and fall), a "now" marker on
    both. ``mode: mitosis`` / ``meiosis``: a dividing cell with 2n chromosomes (homologues in
    maternal and paternal colours, sister chromatids joined at the centromere, kinetochores,
    the spindle), captions and the counts per cell; meiosis shows synapsis, crossing over with
    the exchanged segments and independent assortment, and ends with four haploid cells. The
    action ``advance`` moves the cell to a point of the cycle or a stage of the division;
    ``checkpoint`` shows a checkpoint's regulators passing or arresting the cell.

    Action targets: ``title``; cycle: ``cycle`` (the ring and marker), ``phase:<g1|s|g2|m|g0>``,
    ``checkpoint:<g1_s|g2_m|spindle>``, ``plot``, ``cyclin:<d|e|a|b>``, ``marker``; division:
    ``cell``, ``chromosomes``, ``pair<N>``, ``spindle``, ``caption``."""

    outro = 0.5
    target_patterns = ("title", "cycle", "phase:<key>", "checkpoint:<key>", "<checkpoint>", "plot", "cyclin:<key>", "marker", "cell",
                       "chromosomes", "pair<N>", "spindle", "caption")
    #: The actions advance and checkpoint act on this scene type.
    cycle_actions = True
    mid_still_actions = frozenset({"advance", "checkpoint"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        mode: Literal["cycle", "mitosis", "meiosis"] = "cycle"
        """cycle: the cell cycle as a ring with the cyclin levels; mitosis or meiosis: a dividing cell."""
        start: str | None = None
        """Where the cell is at the start: a point of the cycle (g1, g0, restriction_point, s, g2, m, prophase …; default g1) or a stage of the division (default interphase)."""
        hours: dict[str, float] = Field(default_factory=dict)
        """cycle: the phases' lengths in hours (default g1: 11, s: 8, g2: 4, m: 1; M is drawn at least 12 % of the ring)."""
        cyclins: bool = True
        """cycle: draw the cyclin–CDK levels beside the ring."""
        chromosomes: int = 4
        """mitosis / meiosis: 2n, the diploid number (2, 4, 6 or 8; homologues in maternal and paternal colours)."""
        cell: Literal["animal", "plant"] = "animal"
        """mitosis: an animal cell (centrosomes, contractile ring) or a plant cell (wall, no centrosomes, preprophase band, cell plate)."""
        crossovers: list[list[float]] | None = None
        """meiosis: per homologous pair, where its crossovers are (0 p telomere … 1 q telomere; one or two each); default one per pair, placed by the seed."""
        assortment: list[Literal["m", "p"]] | None = None
        """meiosis: per pair, the homologue facing the first pole at metaphase I (m maternal, p paternal); default by the seed."""
        nondisjunction: dict[str, Any] | None = None
        """meiosis: {division: I | II, pair: 1}: that pair's homologues (I) or sister chromatids (II, in the first daughter cell) fail to separate; the gametes are labelled n + 1 / n − 1 / n with their shares and the zygotes they make."""
        seed: int = 1
        """Varies the chromosomes' places and, in meiosis, the default crossovers and assortment."""
        captions: bool = True
        """mitosis / meiosis: caption each stage (what happens, in key terms)."""
        counts: bool = True
        """mitosis / meiosis: show the counts per cell (chromosomes, chromatids, n / 2n, DNA content C)."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def nd(self) -> tuple[str, int] | None:
            """``nondisjunction`` as (``I`` / ``II``, pair index from 0), checked."""
            spec = self.nondisjunction
            if spec is None:
                return None
            for key in spec:
                if key not in ("division", "pair"):
                    raise VidgenError(f"nondisjunction: unknown key '{key}': use division (I or II) and pair (1…)")
            division = str(spec.get("division", "I")).strip().upper().replace("MEIOSIS", "").strip()
            division = {"1": "I", "2": "II"}.get(division, division)
            pair = spec.get("pair", 1)
            if isinstance(pair, bool) or not isinstance(pair, int):
                raise VidgenError(f"nondisjunction.pair: {pair!r}: the number of the homologous pair (1 for the first)")
            return division, pair - 1

        def division_spec(self) -> Any:
            return dv.DivisionSpec(self.mode, self.chromosomes, self.cell,
                                   tuple(tuple(x) for x in self.crossovers) if self.crossovers is not None else None,
                                   tuple(self.assortment) if self.assortment is not None else None, self.seed, self.nd())

        def division(self) -> Any:
            return _division(self.division_spec())

        def geometry(self) -> Any:
            return cy.cycle_geometry(self.hours or None)

        def start_key(self) -> str:
            if self.mode == "cycle":
                return cy.point_key(self.start or "g1")
            return dv.stage_key(self.mode, self.start or "interphase")

        @model_validator(mode="after")
        def _check(self) -> "CellCycle.Params":
            try:
                if self.mode == "cycle":
                    extra = [k for k in ("chromosomes", "cell", "crossovers", "assortment", "captions", "counts", "nondisjunction")
                             if k in self.model_fields_set]
                    if extra:
                        raise VidgenError(f"{', '.join(extra)}: belong{'s' if len(extra) == 1 else ''} to mode: mitosis or meiosis")
                    self.geometry()
                else:
                    extra = [k for k in ("hours", "cyclins") if k in self.model_fields_set]
                    if extra:
                        raise VidgenError(f"{', '.join(extra)}: belong{'s' if len(extra) == 1 else ''} to mode: cycle")
                    self.division()
                self.start_key()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        names = ["title"] if params.title else []
        if params.mode == "cycle":
            names += ["cycle", "marker"] + [f"phase:{k}" for k in (*cy.PHASE_KEYS, "g0")] + [f"checkpoint:{k}" for k in cy.CHECKPOINTS]
            names += list(cy.CHECKPOINTS)     # checkpoint: g1_s names its checkpoint:g1_s
            if params.cyclins:
                names += ["plot"] + [f"cyclin:{k}" for k in cy.CYCLIN_KEYS]
            return names
        names += ["cell", "chromosomes", "spindle"] + [f"pair{k + 1}" for k in range(params.chromosomes // 2)]
        return names + (["caption"] if params.captions or params.counts else [])

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """advance and checkpoint replayed in beat and ``at`` order (an arrest lasts until its
        ``until`` beat): no passing an arrested checkpoint, no G0 after the restriction point,
        no stage of a division twice or backwards."""
        from .cycle_actions import cycle_sequence_problems

        return cycle_sequence_problems(spec, params, uses)

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.bg = th.background
        self.ink = th.color("text")
        self.dim_ink = th.color("dim")
        self.hi = th.color("highlight")
        self.bad = th.color("accent")
        self.small = small_size(self, p.size)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.3)
        self.body = body
        self.title_mob = title
        if p.mode == "cycle":
            self._build_cycle(body)
        else:
            self._build_division(body)
        self._register(title)

    def _register(self, title: Mobject | None) -> None:
        steps: list[Any] = []
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        for name, mob in self.parts.items():
            short = name.split(":", 1)[1] if name.startswith("checkpoint:") else None
            self.target((name, short) if short else name, mob)

        def first() -> list[Animation]:
            anims: list[Animation] = [FadeIn(title)] if title is not None else []
            return anims + [FadeIn(self.everything)]

        steps.append(first)
        self.reveal(steps, fraction=0.8, cap=1.2)
        self.finish()

    # ----- the cycle ----------------------------------------------------------------------------

    def _layout_cycle(self, body: Any) -> tuple[Any, Any | None, Any | None]:
        """The regions of the ring, the plot and the checkpoint panel."""
        p = self.params
        panel = bool(self.action_uses("checkpoint"))
        if not self.is_portrait:
            side = min(body.height, body.width * (0.42 if p.cyclins or panel else 1.0))
            cy0 = body.center[1]
            ring = Region(body.x0, cy0 - side / 2, body.x0 + side, cy0 + side / 2)
            if not (p.cyclins or panel):
                ring = Region(body.center[0] - side / 2, ring.y0, body.center[0] + side / 2, ring.y1)
                return ring, None, None
            right = Region(ring.x1 + 0.4, body.y0, body.x1, body.y1)
            if p.cyclins and panel:
                plot, pan = right.rows([0.44, 0.56], gap=0.25)
                return ring, plot, pan
            return ring, (right if p.cyclins else None), (right if panel else None)
        side = min(body.width, body.height * ((0.34 if panel else 0.48) if p.cyclins or panel else 1.0))
        ring = Region(body.center[0] - side / 2, body.y1 - side, body.center[0] + side / 2, body.y1)
        rest = Region(body.x0, body.y0, body.x1, ring.y0 - 0.25)
        if p.cyclins and panel:
            plot, pan = rest.rows([0.5, 0.5], gap=0.25)
            return ring, plot, pan
        return ring, (rest if p.cyclins else None), (rest if panel else None)

    def _angle(self, t: float) -> float:
        return math.pi / 2 - 2 * math.pi * t

    def _on_ring(self, t: float, r: float | None = None) -> np.ndarray:
        r = self.R if r is None else r
        a = self._angle(t)
        return self.C + r * np.array([math.cos(a), math.sin(a), 0.0])

    def _build_cycle(self, body: Any) -> None:
        p = self.params
        th = self.theme
        self.geo = p.geometry()
        ring_area, plot_area, panel_area = self._layout_cycle(body)
        self.panel_area = panel_area
        self.C = ring_area.center
        self.R = ring_area.width / 2 * 0.6
        R = self.R
        geo = self.geo
        self.phase_color = {k: th.palette_color(i) for i, k in enumerate(cy.PHASE_KEYS)}
        width = RING_WIDTH * R
        arcs = {}
        labels = VGroup()
        for ph in cy.PHASES:
            a, b = geo.bounds[ph.key]
            gap = 0.006
            arc = Arc(radius=R, start_angle=self._angle(a + gap), angle=-2 * math.pi * (b - a - 2 * gap), arc_center=self.C)
            arc.set_stroke(self.phase_color[ph.key], width=width * 100, opacity=0.9)
            mid = (a + b) / 2
            t = self.markup(f"<b>{ph.markup}</b>", size=self.small * 1.15, color=self.phase_color[ph.key])
            t.move_to(self._on_ring(mid, R - width / 2 - 0.1 - max(t.width, t.height) / 2))
            arcs[ph.key] = VGroup(arc, t)
            labels.add(t)
        # the direction: an arrowhead at the end of M
        tip = self._on_ring(0.0)
        head = Triangle().set_fill(self.phase_color["m"], opacity=1).set_stroke(width=0).scale(0.6 * width)
        head.rotate(self._angle(0.0) - math.pi - math.pi / 2).move_to(tip + LEFT * 0.02)
        # stages of M: ticks
        ticks = VGroup()
        for name, _ in cy.M_STAGES[1:]:
            t = geo.points[name]
            ticks.add(Line(self._on_ring(t, R - width / 2), self._on_ring(t, R + width / 2)).set_stroke(self.bg, width=1.6))
        # restriction point
        rt = geo.points["restriction_point"]
        r_tick = Line(self._on_ring(rt, R - width * 0.75), self._on_ring(rt, R + width * 0.75)).set_stroke(self.ink, width=2.4)
        r_label = self.markup("R", size=self.small, color=self.ink).move_to(self._on_ring(rt, R + width + 0.2))
        # checkpoints
        self.check_marks: dict[str, VGroup] = {}
        cp_group = VGroup()
        names = {"g1_s": "G<sub>1</sub>/S", "g2_m": "G<sub>2</sub>/M", "spindle": "SAC"}
        for key, ck in cy.CHECKPOINTS.items():
            t = geo.points[ck.at]
            bar = Line(self._on_ring(t, R - width * 0.9), self._on_ring(t, R + width * 0.9)).set_stroke(self.ink, width=6)
            lab = self.markup(names[key], size=self.small, color=self.ink)
            out = R + width / 2 + 0.12 + max(lab.width, lab.height) / 2
            lab.move_to(self._on_ring(t, out))
            mark = VGroup(bar, lab)
            self.check_marks[key] = mark
            cp_group.add(mark)
        # G0
        t0 = 0.05
        g0_at = self._on_ring(t0 + 0.03, R * 1.62)
        g0 = Circle(radius=0.32 * R).set_fill(self.phase_color["g1"], opacity=0.12).set_stroke(self.phase_color["g1"], width=2.4, opacity=0.8)
        g0.move_to(g0_at)
        g0_text = self.markup("G<sub>0</sub>", size=self.small, color=self.ink).move_to(g0)
        out_arrow = CurvedArrow(self._on_ring(t0, R + width / 2 + 0.03), g0.point_at_angle(self._angle(t0) + 2.6), angle=-0.6, tip_length=0.12)
        back_arrow = CurvedArrow(g0.point_at_angle(self._angle(t0 + 0.06) + 3.6), self._on_ring(t0 + 0.07, R + width / 2 + 0.03), angle=-0.6,
                                 tip_length=0.12)
        for arr in (out_arrow, back_arrow):
            arr.set_color(self.dim_ink).set_stroke(width=2)
        g0_group = VGroup(g0, g0_text, out_arrow, back_arrow)
        self.g0_center = g0.get_center()
        # the centre label: one per stage, shown by the marker's position
        self.centre_labels: dict[str, VGroup] = {}
        hours = geo.hours
        for ph in cy.PHASES:
            if ph.key == "m":
                continue
            big = self.markup(f"<b>{ph.markup}</b>", size=self.small * 1.7, color=self.ink)
            sub = self.markup(f"≈ {hours[ph.key]:g} h", size=self.small, color=self.dim_ink)
            self.centre_labels[ph.key] = VGroup(big, sub).arrange(DOWN, buff=0.1).move_to(self.C)
        for name, _ in cy.M_STAGES:
            big = self.markup("<b>M</b>", size=self.small * 1.7, color=self.ink)
            sub = self.markup(name, size=self.small, color=self.dim_ink)
            self.centre_labels[name] = VGroup(big, sub).arrange(DOWN, buff=0.1).move_to(self.C)
        big = self.markup("<b>G<sub>0</sub></b>", size=self.small * 1.7, color=self.ink)
        sub = self.markup("quiescent", size=self.small, color=self.dim_ink)
        self.centre_labels["g0"] = VGroup(big, sub).arrange(DOWN, buff=0.1).move_to(self.C)
        fit = 1.25 * (R - width / 2) / max(max(g.width for g in self.centre_labels.values()), 1e-6)
        if fit < 1:
            for g in self.centre_labels.values():
                g.scale(fit)
        centre = VGroup(*self.centre_labels.values())
        # the marker
        self.marker = VGroup(Circle(radius=0.11 * R).set_fill(self.ink, opacity=1).set_stroke(self.bg, width=3))
        ring_group = VGroup(*[g[0] for g in arcs.values()], head, ticks, r_tick, r_label, labels)
        self.parts: dict[str, Mobject] = {"cycle": VGroup(ring_group, cp_group, g0_group, centre, self.marker), "marker": self.marker}
        for k, g in arcs.items():
            self.parts[f"phase:{k}"] = g
        self.parts["phase:g0"] = g0_group
        for k, g in self.check_marks.items():
            self.parts[f"checkpoint:{k}"] = g
        everything = [ring_group, cp_group, g0_group, centre, self.marker]
        self.plot = None
        if plot_area is not None and p.cyclins:
            self._build_plot(plot_area)
            everything.append(self.plot_group)
        self.everything = VGroup(*everything)
        # the start
        state = cy.start_state(geo, p.start or "g1")
        self.state = state
        self.extra_shown: list[Mobject] = []
        self._place_marker(state.t, state.g0)
        self.panel: VGroup | None = None
        self.arrest_marks: dict[str, Mobject] = {}

    def _build_plot(self, area: Any) -> None:
        th = self.theme
        geo = self.geo
        small = self.small
        title = self.markup("cyclin–CDK levels (a.u.)", size=small, color=self.dim_ink)
        legend = self._legend(area.width) if self.is_portrait else None
        head = title.height + 0.2 + (legend.height + 0.15 if legend is not None else 0.0)
        # room: the phase names under the axis, the curve labels inside
        top = area.y1 - head
        h = min(top - area.y0, area.width * 0.62)
        names_room = small / 48 * 1.3
        x0, x1 = area.x0 + 0.1, area.x1 - 0.1
        y0, y1 = top - h + names_room, top - 0.05
        title.move_to(np.array([x0 + title.width / 2, area.y1 - title.height / 2, 0.0]))
        if legend is not None:
            legend.move_to(np.array([x0 + legend.width / 2, title.get_bottom()[1] - 0.15 - legend.height / 2, 0.0]))
        self.plot_box = (x0, y0, x1, y1)

        def at(t: float, v: float) -> np.ndarray:
            return np.array([x0 + (x1 - x0) * t, y0 + (y1 - y0) * v * 0.9, 0.0])

        self.plot_at = at
        bands = VGroup()
        names = VGroup()
        for ph in cy.PHASES:
            a, b = geo.bounds[ph.key]
            rect = Rectangle(width=(x1 - x0) * (b - a), height=y1 - y0).move_to((at(a, 0) + at(b, 0)) / 2 + UP * (y1 - y0) / 2)
            rect.set_fill(self.phase_color[ph.key], opacity=0.1).set_stroke(width=0)
            bands.add(rect)
            name = self.markup(ph.markup, size=small, color=self.ink).next_to(rect, DOWN, buff=0.08)
            names.add(name)
        axis = VGroup(Line(at(0, 0), at(1, 0) + RIGHT * 0.05), Line(at(0, 0), np.array([x0, y1, 0.0]))).set_stroke(self.dim_ink, width=2)
        self.cyclins = cy.cyclins(geo)
        curves = {}
        labels = VGroup()
        boxes: list[tuple[float, float, float, float]] = []
        for key, c in self.cyclins.items():
            color = self._cyclin_color(key)
            pts = [at(k / 160, c.level(k / 160 if k < 160 else 0.9999)) for k in range(161)]
            curve = VMobject().set_points_smoothly(pts).set_stroke(color, width=CURVE_STROKE)
            if legend is not None:
                curves[key] = VGroup(curve, legend[list(self.cyclins).index(key)])
                self.parts[f"cyclin:{key}"] = curves[key]
                continue
            peak = max(range(161), key=lambda k: c.level(k / 160 if k < 160 else 0.9999))
            text = self.markup(c.markup, size=small * 0.92, color=color)
            spot = pts[peak] + UP * (text.height / 2 + 0.08)
            text.move_to(spot)
            for _ in range(6):
                bx = (text.get_left()[0], text.get_bottom()[1], text.get_right()[0], text.get_top()[1])
                if any(min(bx[2], o[2]) > max(bx[0], o[0]) and min(bx[3], o[3]) > max(bx[1], o[1]) for o in boxes):
                    text.shift(DOWN * (text.height + 0.06) if key == "d" else UP * (text.height + 0.06))
                    continue
                break
            if text.get_right()[0] > x1 + 0.1:
                text.shift(LEFT * (text.get_right()[0] - x1 - 0.1))
            if text.get_left()[0] < x0 + 0.05:
                text.shift(RIGHT * (x0 + 0.05 - text.get_left()[0]))
            boxes.append((text.get_left()[0], text.get_bottom()[1], text.get_right()[0], text.get_top()[1]))
            lab = VGroup(plate(text, self.bg, 0.05, 0.75), text)
            labels.add(lab)
            curves[key] = VGroup(curve, lab)
            self.parts[f"cyclin:{key}"] = curves[key]
        self.now_line = DashedLine(at(0, 0), np.array([x0, y1, 0.0]), dash_length=0.08).set_stroke(self.ink, width=2.4)
        self.now_dots = VGroup(*[Dot(radius=0.06, color=self._cyclin_color(k)) for k in self.cyclins])
        extra = [legend] if legend is not None else [labels]
        self.plot_group = VGroup(bands, axis, names, *[c[0] for c in curves.values()], *extra, title, self.now_line, self.now_dots)
        self.parts["plot"] = self.plot_group

    def _legend(self, width: float) -> VGroup:
        """The cyclins' names with their colours, in two columns (portrait frames)."""
        items = []
        for key in cy.CYCLIN_KEYS:
            color = self._cyclin_color(key)
            swatch = Line(ORIGIN, RIGHT * 0.35).set_stroke(color, width=CURVE_STROKE)
            text = self.markup(cy.CYCLIN_LABELS[key], size=self.small * 0.95, color=color)
            items.append(VGroup(swatch, text).arrange(RIGHT, buff=0.1))
        grid = VGroup(*items).arrange_in_grid(rows=2, cols=2, buff=(0.3, 0.12), col_alignments="ll")
        if grid.width > width - 0.2:
            grid.scale((width - 0.2) / grid.width)
        return grid

    def _cyclin_color(self, key: str) -> str:
        token = CYCLIN_PALETTE[key]
        return self.theme.color(token) if isinstance(token, str) else self.theme.palette_color(token)

    def _place_marker(self, t: float, g0: bool, g0_share: float = 1.0) -> None:
        """Put the marker at cycle position ``t`` (in G0: ``g0_share`` of the way out to the G0
        circle), the centre label and the plot's "now" line with it."""
        on = self._on_ring(t)
        pos = on + (self.g0_center - on) * g0_share if g0 else on
        self.marker.move_to(pos)
        key = "g0" if g0 and g0_share > 0.5 else self.geo.stage_at(t)
        for k, g in self.centre_labels.items():
            g.set_opacity(1.0 if k == key else 0.0)
        if self.params.cyclins and hasattr(self, "now_line"):
            x = t % 1.0
            x0, y0, x1, y1 = self.plot_box
            px = x0 + (x1 - x0) * x
            self.now_line.put_start_and_end_on(np.array([px, y0, 0.0]), np.array([px, y1, 0.0]))
            for dot, c in zip(self.now_dots, self.cyclins.values()):
                dot.move_to(self.plot_at(x, c.level(x)))

    # ----- cycle actions ----------------------------------------------------------------------

    def advance_seconds(self, to: str, into: float) -> float:
        p = self.params
        if p.mode != "cycle":
            return self._division_seconds(to)
        state = self.state
        t, key = cy.target_t(self.geo, state, to, into)
        if key == "g0" or state.g0:
            return max(MIN_SECONDS, 1.6 + TURN_SECONDS * max(0.0, t - state.t))
        return min(MAX_SECONDS, max(MIN_SECONDS, TURN_SECONDS * (t - state.t)))

    def run_advance(self, to: str, into: float) -> list[Animation]:
        if self.params.mode != "cycle":
            return self._division_advance(to)
        state = self.state
        new = cy.advance(self.geo, state, to, into)
        self.state = new
        t0, t1 = state.t, new.t
        leaving = state.g0 and not new.g0
        entering = new.g0 and not state.g0
        total = max(1e-6, t1 - t0) + (0.25 if leaving else 0.0)
        out_share = (0.25 / total) if leaving else 0.0

        def frame(alpha: float) -> None:
            if entering:
                self._place_marker(t0, True, alpha)
            elif leaving and alpha < out_share:
                self._place_marker(t0, True, 1 - alpha / out_share)
            else:
                a = (alpha - out_share) / (1 - out_share) if leaving else alpha
                self._place_marker(t0 + (t1 - t0) * a, False)

        moving = VGroup(self.marker, *self.centre_labels.values())
        if self.params.cyclins and hasattr(self, "now_line"):
            moving.add(self.now_line, self.now_dots)
        return [driven(moving, frame, rate_func=smooth)]

    def run_checkpoint(self, name: str, outcome: str, cause: str | None) -> tuple[list[Animation], Any]:
        key = cy.checkpoint_key(name)
        ck = cy.CHECKPOINTS[key]
        area = self.panel_area
        anims: list[Animation] = []
        old = self.panel
        if old is not None:
            anims.append(FadeOut(old))
        cause = cause or (next(iter(ck.arrest)) if outcome == "arrest" else None)
        rows = ck.go if outcome == "pass" else ck.arrest[cause]
        note = ("passes: " + ck.checks) if outcome == "pass" else ck.stop_note[cause]
        head = self.markup(f"<b>{ck.markup}</b>  {'✓ passes' if outcome == 'pass' else '✕ arrest'}", size=self.small * 1.08,
                           color=self.ink)
        width = area.width - 0.3
        if head.width > width:
            head.scale(width / head.width)
        text = text_block(self, note, width, self.small, color=self.dim_ink)
        drawn = []
        box_color = self.theme.color("tertiary") if outcome == "pass" else self.bad
        size = max(readable_size() * 1.02, self.small * (0.85 if self.is_portrait else 1.0))
        for row in rows:
            drawn.append(regulation_row(self, row, size, width, self.ink, self.bad, self.bg, self.theme.color("primary")))
        parts = [head, *[d.group for d in drawn], text]
        stack = VGroup(*parts).arrange(DOWN, buff=0.22, aligned_edge=LEFT)
        if stack.height > area.height - 0.3:      # the note goes first; then the rest is drawn a little smaller
            stack = VGroup(*parts[:-1]).arrange(DOWN, buff=0.22, aligned_edge=LEFT)
        if stack.height > area.height - 0.3:
            stack.scale((area.height - 0.3) / stack.height)
        stack.move_to(np.array([area.x0 + 0.1 + stack.width / 2, area.y1 - 0.05 - stack.height / 2, 0.0]))
        frame = SurroundingRectangle(stack, buff=0.12, corner_radius=0.12).set_stroke(box_color, width=2.4).set_fill(self.bg, opacity=0.92)
        panel = VGroup(frame, stack)
        panel.set_z_index(5)
        self.panel = panel
        light = []
        lit_color = self.theme.color("tertiary") if outcome == "pass" else self.bad
        for d in drawn:
            for k, node in enumerate(d.nodes):
                goal = node[0].copy().set_fill(lit_color, opacity=0.35).set_stroke(lit_color, width=3)
                light.append(Transform(node[0], goal))
        reveal = Succession(FadeIn(panel, shift=UP * 0.1), LaggedStart(*light, lag_ratio=0.25))
        anims.append(reveal)
        mark = self.check_marks[key]
        bar = mark[0]
        before = bar.copy()
        goal = bar.copy().set_stroke(self.bad if outcome == "arrest" else self.theme.color("tertiary"), width=10 if outcome == "arrest" else 7)
        anims.append(Transform(bar, goal))
        self.add(panel)

        def undo() -> list[Animation]:
            out: list[Animation] = [Transform(bar, before)]
            if self.panel is panel:
                out.append(FadeOut(panel))
                self.panel = None
            return out

        return [Succession(*anims) if old is not None else AnimationGroup(*anims)], undo

    # ----- the division -------------------------------------------------------------------------

    def _division_layout(self, body: Any) -> tuple[Any, Any | None]:
        """The cell's region and the captions': a column on the right in landscape frames, a
        band at the bottom in portrait ones."""
        p = self.params
        if not (p.captions or p.counts):
            return body, None
        if not self.is_portrait:
            split = body.x0 + body.width * 0.6
            return Region(body.x0, body.y0, split, body.y1), Region(split + 0.3, body.y0, body.x1, body.y1)
        lines = 1.4 + (3 if p.captions else 0) + (2 if p.counts else 0)
        h = lines * self.small / 48 * 1.3 + 0.3
        cap = Region(body.x0, body.y0, body.x1, body.y0 + h)
        return Region(body.x0, cap.y1 + 0.2, body.x1, body.y1), cap

    def _build_division(self, body: Any) -> None:
        p = self.params
        th = self.theme
        div = p.division()
        self.div = div
        area, cap = self._division_layout(body)
        if cap is not None and self.is_portrait:   # the drawing and its caption together, centred
            need = division_height(div, area, True)
            if need < area.height - 0.05:
                total = need + 0.2 + cap.height
                top = min(body.y1, body.center[1] + total / 2)
                area = Region(area.x0, top - need, area.x1, top)
                cap = Region(cap.x0, area.y0 - 0.2 - cap.height, cap.x1, area.y0 - 0.2)
        maternal, paternal = th.color("accent"), th.color("primary")
        colors = {"bg": self.bg, "ink": self.ink, "cytoplasm": mix_colors(th.color("secondary"), self.bg, 0.1),
                  "membrane": mix_colors(th.color("secondary"), self.ink, 0.7), "envelope": mix_colors(th.palette_color(2), self.ink, 0.7),
                  "mt": mix_colors(th.color("tertiary"), self.bg, 0.75), "mt_astral": mix_colors(th.color("tertiary"), self.bg, 0.5),
                  "kinetochore": mix_colors(self.ink, self.bg, 0.9), "nucleolus": mix_colors(th.palette_color(2), self.bg, 0.35),
                  "ring": th.color("highlight"), "centriole": mix_colors(self.ink, self.bg, 0.75), "sc": mix_colors(self.ink, self.bg, 0.6),
                  "plate": mix_colors(th.color("secondary"), self.ink, 0.6)}
        for k in range(p.chromosomes // 2):
            shade = 0.22 * (k % 2) + 0.12 * (k // 2)
            colors[f"m{k}"] = mix_colors(maternal, self.ink, 1 - shade)
            colors[f"p{k}"] = mix_colors(paternal, self.ink, 1 - shade)
        self.drawing = DivisionDrawing(self, div, area, self.is_portrait, colors, self.small)
        self.stage = self.params.start_key()
        self.kf = div.stage_end[self.stage]
        self.drawing.show(self.kf, self.kf, 0.0)
        self.parts = {"cell": self.drawing.group, "chromosomes": self.drawing.layers["chrom"], "spindle": self.drawing.layers["mt"]}
        for k in range(p.chromosomes // 2):
            ids = [ch.id for ch in div.chromatids if ch.pair == k]
            self.parts[f"pair{k + 1}"] = VGroup(*[self.drawing.mobs[i] for i in ids])
        everything = [self.drawing.group]
        self.captions: dict[int, VGroup] = {}
        if cap is not None:
            self._build_captions(cap)
            everything.append(self.caption_group)
            self.parts["caption"] = self.caption_group
            self._show_caption(self.kf)
        self.everything = VGroup(*everything)

    def _build_captions(self, cap: Any) -> None:
        """One caption per keyframe (stage name, what happens, the counts), made now and shown
        by opacity (a text made during an animation would not be drawn)."""
        p = self.params
        div = self.div
        width = cap.width - 0.2
        group = VGroup()
        for k, kf in enumerate(div.keyframes):
            rows = [self.markup(f"<b>{dv.STAGE_LABELS[kf.stage]}</b>", size=self.small * 1.3, color=self.ink)]
            if p.captions:
                rows.append(text_block(self, kf.caption, width, self.small, color=self.ink))
            if p.counts:
                c = dv.stage_counts(div.spec.mode, kf.stage, div.spec.two_n)
                differ = dv.nondisjunction_cells(kf.stage, div.spec.two_n, div.spec.nondisjunction) if div.spec.mode == "meiosis" else None
                if differ is not None:
                    n = div.spec.two_n // 2
                    where = "nuclei" if kf.stage.startswith("telophase") else "cells"
                    each = ", ".join(str(ch) for ch, _ in differ)
                    text = f"2n = {div.spec.two_n} · {len(differ)} {where}: {each} chromosomes"
                    if len(differ) == 4 or kf.stage in ("telophase_i", "cytokinesis_i", "prophase_ii", "metaphase_ii"):
                        tags = ", ".join("n" if ch == n else (f"n + {ch - n}" if ch > n else f"n − {n - ch}") for ch, _ in differ)
                        text += f" ({tags})"
                else:
                    each = "per cell" if c.cells == 1 else f"each of {c.cells} {'nuclei' if kf.stage.startswith('telophase') else 'cells'}"
                    text = (f"2n = {div.spec.two_n} · {each}: {c.chromosomes} chromosomes, {c.chromatids} chromatids "
                            f"({c.ploidy}, {c.dna})")
                rows.append(text_block(self, text, width, self.small * 0.92, color=self.dim_ink))
            block = VGroup(*rows).arrange(DOWN, buff=0.16, aligned_edge=LEFT)
            if block.height > cap.height or block.width > cap.width:
                block.scale(min(cap.height / block.height, cap.width / block.width))
            y = cap.y1 - block.height / 2 if self.is_portrait else cap.center[1]
            block.move_to(np.array([cap.x0 + block.width / 2, y, 0.0]))
            self.captions[k] = block
            group.add(block)
        self.caption_group = group

    def _show_caption(self, k: int) -> None:
        for j, block in self.captions.items():
            block.set_opacity(1.0 if j == k else 0.0)

    def _division_seconds(self, to: str) -> float:
        end = self.div.stage_end[dv.stage_key(self.params.mode, to)]
        return max(MIN_SECONDS, KEYFRAME_SECONDS * max(1, end - self.kf))

    def _division_advance(self, to: str) -> list[Animation]:
        end = self.div.stage_end[dv.stage_key(self.params.mode, to)]
        start = self.kf
        frames = self.div.keyframes
        self.kf = end
        self.stage = frames[end].stage
        steps = end - start

        def frame(alpha: float) -> None:
            x = alpha * steps
            k = min(int(x), steps - 1)
            t = x - k
            self.drawing.show(start + k, start + k + 1, smooth(t))
            if self.captions:
                self._show_caption(start + k + 1 if t > 0.15 or k + 1 == steps and t > 0.15 else start + k)

        moving = VGroup(self.drawing.group, *(self.captions.values()))
        return [driven(moving, frame, rate_func=linear)]
