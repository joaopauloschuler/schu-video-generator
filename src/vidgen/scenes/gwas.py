"""``gwas``: a genome-wide association study (DESIGN.md §96.17), computed by
``vidgen.genetics.gwas``: a Manhattan plot (−log₁₀ p along the genome, the 22 autosomes (and X) in
alternating colours, the genome-wide significance line at 5 × 10⁻⁸ and the suggestive line at
1 × 10⁻⁵, peaks labelled with their gene or lead variant), a QQ plot with λ_GC, and a regional
plot of one locus with its variants coloured by r² with the lead. Data from a CSV in the project,
inline ``variants``, or a seeded synthetic study with the author's ``peaks`` (labelled "simulated
data" on screen). Action ``regional`` (``scenes/population_actions.py``)."""

import math
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import small_size

gw = genetics.gwas

#: r² colours of a regional plot (low to high) and the lead variant's: fixed in every theme.
R2_COLORS = ("#3B5BA9", "#6CB4E0", "#4DAA57", "#EE9A2E", "#D63B3B")
LEAD_COLOR = "#8A4FB8"
#: Seconds: the points; a regional plot.
POINTS_SECONDS, REGIONAL_SECONDS = 2.4, 2.6


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _sup(n: int) -> str:
    return str(n).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))


def p_label(m: float) -> str:
    """``p = 3 × 10⁻⁴⁰`` from −log₁₀ p."""
    e = math.floor(-m)
    mant = 10 ** (-m - e)
    if mant >= 9.95:
        mant, e = 1.0, e + 1
    return f"p = {mant:.1f} × 10{_sup(e)}".replace(".0 ×", " ×")


@scene("gwas")
class GwasScene(NarratedScene):
    """A genome-wide association study. ``plot: manhattan``: −log₁₀ p of every variant along the
    genome, chromosomes 1–22 (and X) in alternating colours, the genome-wide significance line at
    p = 5 × 10⁻⁸ and the suggestive line at 1 × 10⁻⁵, each peak labelled with its gene or lead
    variant; ``qq``: observed against expected −log₁₀ p with the genomic inflation λ_GC; ``both``.
    Data: ``data`` (a CSV in the project: chromosome, position in bp, p, and optionally variant,
    gene, r2), ``variants`` inline, or a seeded synthetic study — a null background with your
    ``peaks``, each with the variants around it in linkage disequilibrium — written "simulated
    data" on the plot. ``regional`` (a param or the action) zooms into a peak: its variants
    coloured by r² with the lead.

    Action targets: ``title``, ``manhattan``, ``points``, ``chromosome:<n>``, ``thresholds``,
    ``significance``, ``suggestive``, ``peaks``, ``peak:<label>``, ``qq``, ``lambda``, ``regional``,
    ``simulated``."""

    outro = 0.5
    target_patterns = ("title", "manhattan", "points", "chromosome:<n>", "thresholds", "significance", "suggestive", "peaks",
                       "peak:<label>", "qq", "lambda", "regional", "simulated")
    #: The action regional acts on this scene type.
    gwas_actions = True
    mid_still_actions = frozenset({"regional"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        trait: TranslatableStr = ""
        """The trait studied (body mass index), written on the plot."""
        plot: Literal["manhattan", "qq", "both"] = "manhattan"
        """manhattan, qq (with λ_GC) or both."""
        data: str | None = None
        """A CSV (or TSV) in the project: columns chromosome (CHR), position in bp (BP), p (P), and optionally variant (SNP), gene, r2."""
        variants: list[dict[str, Any]] | None = None
        """Your variants inline: [{chromosome: 16, position: 53800000, p: 1e-40, variant: rs9939609, gene: FTO}, …]."""
        peaks: list[dict[str, Any]] | None = None
        """A synthetic study's peaks: [{chromosome: 16, position: 53.8 Mb, p: 1e-40, gene: FTO, variant: rs9939609}]."""
        labels: dict[str, str] | None = None
        """Your data: genes for lead variants {rs9939609: FTO} (else the variant id is written)."""
        background: int | None = None
        """Synthetic: how many null variants (default 2400)."""
        inflation: float | None = None
        """Synthetic: λ of the null background (1 = none; 1.2 mimics stratification)."""
        x_chromosome: bool = False
        """Draw chromosome X after 22 (your data with X variants draws it anyway)."""
        clump_kb: float | None = None
        """Your data: no second lead within this distance of a lead (default 500 kb)."""
        regional: str | None = None
        """A peak's label to zoom into in the scene's own steps (or use the action regional)."""
        y_max: float | None = None
        """Top of the −log₁₀ p axis (default: the data's, at most 40; higher points are drawn at the top with their p)."""
        seed: int = 1
        """Synthetic: the random seed."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def spec(self, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
            data: dict[str, Any] = {"seed": self.seed, "x_chromosome": self.x_chromosome}
            for key in ("variants", "peaks", "labels", "background", "inflation", "clump_kb", "data"):
                if getattr(self, key) is not None:
                    data[key] = getattr(self, key)
            if rows is not None:
                data["rows"] = rows
            if self.trait:
                data["trait"] = str(self.trait)
            return data

        def plan(self, project: Any = None) -> Any:
            rows = None
            if self.data is not None:
                proj = project if project is not None else current_project()
                text = proj.asset(self.data).read_text(encoding="utf-8")
                rows = gw.read_rows(text, self.data)
            return gw.plan_gwas(self.spec(rows))

        @model_validator(mode="after")
        def _check(self) -> "GwasScene.Params":
            given = [k for k in ("data", "variants", "peaks") if getattr(self, k) is not None]
            if len(given) > 1:
                raise ValueError(f"give one of data (a CSV), variants (your data inline) or peaks (a synthetic study), not {' and '.join(given)}")
            if self.data is not None and not self.data.lower().endswith((".csv", ".tsv", ".txt")):
                raise ValueError(f"data: '{self.data}': a .csv or .tsv file in the project")
            if self.data is None:
                try:
                    plan = self.plan()
                except VidgenError as error:
                    raise ValueError(str(error)) from None
                if self.regional is not None and plan.peak(self.regional) is None:
                    labels = [pk.label for pk in plan.peaks]
                    raise ValueError(f"regional: no peak '{self.regional}' (peaks: {', '.join(labels) or 'none'})"
                                     + did_you_mean(self.regional, labels))
            if self.y_max is not None and self.y_max < 8:
                raise ValueError(f"y_max: {self.y_max:g} would hide the genome-wide significance line at 7.3; use at least 8")
            return self

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super().validate_project(params, project)
        if params.data is not None:
            try:
                plan = params.plan(project)
            except VidgenError as error:
                return problems + [f"data: {error}"]
            if params.regional is not None and plan.peak(params.regional) is None:
                problems.append(f"regional: no peak '{params.regional}' (peaks: {', '.join(pk.label for pk in plan.peaks) or 'none'})")
        return problems

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """One regional plot per scene (it takes the area under the Manhattan plot)."""
        regional = [u for u in uses if u.kind.name == "regional"]
        if len(regional) > 1:
            return [(f"{regional[1].location}.target", "one regional plot per scene: zoom into a second locus in another gwas scene")]
        if regional and params.regional is not None:
            return [(f"{regional[0].location}.target", "the scene already shows regional: in its params; use one of the two")]
        return []

    @classmethod
    def _safe_plan(cls, params: Any) -> Any:
        try:
            return params.plan()
        except VidgenError:
            return None

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        plan = cls._safe_plan(params)
        names = ["title"] if params.title else []
        if params.plot != "qq":
            names += ["manhattan", "points", "thresholds", "significance", "suggestive", "peaks"]
            chroms = plan.chromosomes if plan is not None else gw.CHROMOSOMES
            names += [f"chromosome:{c}" for c in chroms]
        if params.plot != "manhattan":
            names += ["qq", "lambda"]
        if plan is not None:
            names += [pk.target for pk in plan.peaks]
            names += ["simulated"] if plan.synthetic else []
            names += ["regional"] if params.regional is not None and params.plot != "qq" else []
        return names

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        problems = type(self).validate_project(p, self.project)
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        th = self.theme
        self.plan = p.plan(self.project)
        self.ink, self.dim_ink, self.bg = th.color("text"), th.color("dim"), th.background
        self.hi, self.bad = th.color("highlight"), th.color("accent")
        self.col1 = th.color("primary")
        self.col2 = mix_colors(th.color("primary"), th.background, 0.45)
        self.small = small_size(self, p.size)
        self.tiny = max(readable_size() * 1.02, self.small * 0.9)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.25)
        self.title_mob = title
        self.done: set[str] = set()
        top = max([v.mlog10p for v in self.plan.variants] + [8.0])
        self.y_top = p.y_max if p.y_max is not None else min(max(10.0, math.ceil(top * 1.08)), 40.0)
        wants_regional = p.regional is not None or bool(self.action_uses("regional"))
        self._layout(body, wants_regional)
        if self.man_area is not None:
            self._build_manhattan()
        if self.qq_area is not None:
            self._build_qq()
        self.regional_mob: Mobject | None = None
        self._register()

    def _layout(self, body: Region, regional: bool) -> None:
        plot = self.params.plot
        self.man_area = self.qq_area = self.reg_area = None
        has_m, has_q = plot != "qq", plot != "manhattan"
        regional = regional and has_m
        if not self.is_portrait:
            if has_m and regional:
                left = body
                if has_q:
                    left, self.qq_area = body.columns([0.72, 0.28], gap=0.5)
                self.man_area, self.reg_area = left.rows([0.56, 0.44], gap=0.35)
            elif has_m and has_q:
                self.man_area, self.qq_area = body.columns([0.7, 0.3], gap=0.5)
            elif has_m:
                self.man_area = body
            else:
                w = min(body.width, body.height * 1.2)
                self.qq_area = Region(body.center[0] - w / 2, body.y0, body.center[0] + w / 2, body.y1)
        else:
            parts = [("m", 0.4)] if has_m else []
            parts += [("r", 0.32)] if regional else []
            parts += [("q", 0.28 if has_m else 0.6)] if has_q else []
            regions = body.rows([s for _, s in parts], gap=0.35)
            for (k, _), r in zip(parts, regions):
                if k == "m":
                    self.man_area = r
                elif k == "r":
                    self.reg_area = r
                else:
                    self.qq_area = r if has_m else Region(r.x0, r.y0, r.x1, r.y0 + min(r.height, r.width))

    def _y_axis(self) -> Any:
        ticks = axis_ticks(0, self.y_top, 5)
        ticks = [t for t in ticks if t <= self.y_top + 1e-9]
        return ChartAxis(0.0, self.y_top, tuple(ticks), tuple(tick_texts(ticks)), False, "")

    def _axes(self, area: Region, x_axis: Any, y_axis: Any, y_title: str, **kwargs: Any) -> Any:
        """:func:`chart_axes` with the y title turned along the axis at its left (a plot keeps
        the row a title above it would take)."""
        title = self.markup(y_title, size=chart_label_size(self.params.size), color=self.theme.color("dim")).rotate(PI / 2)
        inner = Region(area.x0 + title.width + 0.12, area.y0, area.x1, area.y1)
        axes = chart_axes(inner, x_axis, y_axis, size=self.params.size, grid="none", lines="xy", **kwargs)
        title.move_to(np.array([area.x0 + title.width / 2, axes.plot.center[1], 0]))
        axes.group.add(title)
        return axes

    def _build_manhattan(self) -> None:
        plan = self.plan
        area = self.man_area
        self.info_row = self._info_row(area)
        plot_area = Region(area.x0, area.y0, area.x1, area.y1 - self.info_row.height - 0.12)
        chroms = plan.chromosomes
        centres = [plan.centre(c) for c in chroms]
        x_axis = ChartAxis(-6.0, plan.genome + 6.0, tuple(centres), tuple(chroms), False, "" if self.reg_area is not None or self.qq_area is not None and self.is_portrait else "chromosome")
        size = self.tiny
        sig_t = self.markup("5 × 10⁻⁸", size=size, color=self.bad)
        sug_t = self.markup("1 × 10⁻⁵", size=size, color=self.dim_ink)
        label_h = self.markup("<i>FTO</i>", size=size).height
        self.m_axes = self._axes(plot_area, x_axis, self._y_axis(), "−log₁₀ p", right=max(sig_t.width, sug_t.width) + 0.15,
                                 top=label_h + 0.12)
        ax = self.m_axes
        r = 0.026 if not self.is_portrait else 0.022
        self.chrom_dots: dict[str, VGroup] = {c: VGroup() for c in chroms}
        for v in plan.drawn():
            k = chroms.index(v.chrom)
            color = self.col1 if k % 2 == 0 else self.col2
            y = min(v.mlog10p, self.y_top)
            if v.mlog10p > self.y_top:            # above the axis: a triangle at the top (its p is in the peak's label)
                mark = Triangle().scale_to_fit_height(r * 4.2).set_fill(color, opacity=1).set_stroke(width=0)
                mark.move_to(ax.point(plan.x(v), y))
            else:
                mark = Dot(ax.point(plan.x(v), y), radius=r, color=color)
            self.chrom_dots[v.chrom].add(mark)
        self.points = VGroup(*self.chrom_dots.values())
        # thresholds, labelled in the margin right of the plot (significance above its line, suggestive below)
        x0, x1 = ax.plot.x0, ax.plot.x1
        ys = ax.y_pos(-math.log10(gw.SIGNIFICANCE))
        sig = Line(np.array([x0, ys, 0]), np.array([x1, ys, 0])).set_stroke(self.bad, width=2.5)
        yg = ax.y_pos(-math.log10(gw.SUGGESTIVE))
        sug = DashedLine(np.array([x0, yg, 0]), np.array([x1, yg, 0]), dash_length=0.1).set_stroke(self.dim_ink, width=2)
        sig_t.move_to(np.array([x1 + 0.1 + sig_t.width / 2, max(ys, yg + sug_t.height + 0.08), 0]))
        sug_t.move_to(np.array([x1 + 0.1 + sug_t.width / 2, min(yg, sig_t.get_bottom()[1] - 0.06 - sug_t.height / 2), 0]))
        self.sig_line, self.sug_line = VGroup(sig, sig_t), VGroup(sug, sug_t)
        self.thresholds = VGroup(self.sig_line, self.sug_line)
        # peak labels
        self.peak_marks: dict[str, VGroup] = {}
        placed: list[Mobject] = []
        for pk in sorted(plan.peaks, key=lambda q: -q.lead.mlog10p):
            v = pk.lead
            y = min(v.mlog10p, self.y_top)
            pt = ax.point(plan.x(v), y)
            ring = Circle(radius=r * 3.2).move_to(pt).set_stroke(self.hi, width=2.5).set_fill(opacity=0)
            name = f"<i>{pk.gene}</i>" if pk.gene and pk.label == pk.gene else pk.label
            text = name + (f"  {p_label(v.mlog10p)}" if v.mlog10p > self.y_top else "")
            lab = self.markup(text, size=size, color=self.ink)
            lab.move_to(pt + UP * (r * 3.2 + 0.06 + lab.height / 2))
            lab.set_x(min(max(lab.get_x(), ax.plot.x0 + lab.width / 2), ax.plot.x1 - lab.width / 2))
            for other in placed:
                if abs(lab.get_x() - other.get_x()) < (lab.width + other.width) / 2 + 0.05 and abs(lab.get_y() - other.get_y()) < lab.height * 1.1:
                    lab.shift(DOWN * (lab.height * 1.25))
            placed.append(lab)
            self.peak_marks[pk.label] = VGroup(ring, lab)
        self.peak_group = VGroup(*self.peak_marks.values())
        self.m_frame = VGroup(ax.group, self.info_row)

    def _info_row(self, area: Region) -> VGroup:
        """The row over the Manhattan plot: [simulated data] trait · variants · hits (two lines
        when one is too wide)."""
        plan = self.plan
        size = self.tiny
        info = ([str(plan.trait)] if plan.trait else []) + [
            f"{len(plan.variants):,} variants · {plan.n_significant} below 5 × 10⁻⁸".replace(",", " ")]
        self.sim_tag = self._sim_tag(size) if plan.synthetic else None
        self.tag = self.markup(_esc(" · ".join(info)), size=size, color=self.dim_ink)
        row = VGroup(*([self.sim_tag] if self.sim_tag is not None else []), self.tag).arrange(RIGHT, buff=0.2)
        if row.width > area.width and len(row) == 2:
            for part in row:
                if part.width > area.width:
                    part.scale(area.width / part.width)
            row.arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        elif row.width > area.width:
            row.scale(area.width / row.width)
        return row.move_to(np.array([area.x0 + row.width / 2, area.y1 - row.height / 2, 0]))

    def _sim_tag(self, size: float) -> VGroup:
        """"simulated data", boxed in the accent colour."""
        t = self.markup("<b>simulated data</b>", size=size, color=self.bad)
        return VGroup(SurroundingRectangle(t, buff=0.06, corner_radius=0.05).set_stroke(self.bad, width=1.5), t)

    def _build_qq(self) -> None:
        plan = self.plan
        area = self.qq_area
        top_e = max(e for e, _ in plan.qq)
        top_o = min(max(o for _, o in plan.qq), self.y_top)
        hi = max(top_e, top_o) * 1.05
        x_axis = value_axis([0, top_e], lo=0, hi=math.ceil(top_e), max_ticks=4, title="expected −log₁₀ p")
        y_axis = value_axis([0, hi], lo=0, hi=max(math.ceil(top_o), math.ceil(top_e)), max_ticks=4)
        lam_h = self.markup("λ", size=self.small).height + 0.15
        plot_area = Region(area.x0, area.y0, area.x1, area.y1 - lam_h)
        self.q_axes = self._axes(plot_area, x_axis, y_axis, "observed")
        ax = self.q_axes
        d = min(ax.x.hi, ax.y.hi)
        diag = DashedLine(ax.point(0, 0), ax.point(d, d), dash_length=0.08).set_stroke(self.dim_ink, width=2)
        dots = VGroup()
        for e, o in plan.qq:
            dots.add(Dot(ax.point(min(e, ax.x.hi), min(o, ax.y.hi)), radius=0.03, color=self.col1))
        lam = self.markup(f"λ<sub>GC</sub> = {plan.lambda_gc:.2f}", size=self.small, color=self.ink)
        lam.move_to(np.array([ax.plot.x0 + lam.width / 2, area.y1 - lam.height / 2, 0]))
        self.qq_frame = VGroup(ax.group, diag)
        if self.man_area is None:
            self.sim_tag = None
            if plan.synthetic:
                self.sim_tag = self._sim_tag(self.tiny)
                self.sim_tag.move_to(np.array([area.x1 - self.sim_tag.width / 2, lam.get_y(), 0]))
                self.qq_frame.add(self.sim_tag)
        self.qq_dots = dots
        self.lam = lam

    # ----- the regional plot ------------------------------------------------------------------------

    def _build_regional(self, label: str) -> VGroup:
        plan = self.plan
        pk = plan.peak(label)
        area = self.reg_area
        vs = plan.regional(pk)
        size = self.tiny
        sw = self.markup("r²", size=size).height
        key_items = [VGroup(Square(side_length=sw).set_fill(c, opacity=1).set_stroke(width=0),
                            self.markup(t, size=size, color=self.dim_ink)).arrange(RIGHT, buff=0.06)
                     for c, t in zip(R2_COLORS, ("&lt; 0.2", "0.2", "0.4", "0.6", "≥ 0.8"))]
        known = any(v.r2 is not None for v in vs)
        where = self.markup(f"chr{pk.lead.chrom}", size=size, color=self.ink)
        key = VGroup(where, *([self.markup("r² with the lead", size=size, color=self.dim_ink), *key_items] if known else []))
        key.arrange(RIGHT, buff=0.18)
        if key.width > area.width and known:
            key = VGroup(where, VGroup(*key[1:]).arrange(RIGHT, buff=0.15)).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        if key.width > area.width:
            key.scale(area.width / key.width)
        key_h = key.height + 0.14
        plot_area = Region(area.x0, area.y0, area.x1, area.y1 - key_h)
        lo, hi = pk.start, pk.end
        top = min(max(v.mlog10p for v in vs), self.y_top)
        ticks = [t for t in axis_ticks(0, max(top * 1.05, 8.0), 4)]
        y_axis = ChartAxis(0.0, ticks[-1], tuple(ticks), tuple(tick_texts(ticks)), False, "")
        x_axis = value_axis([lo, hi], lo=lo, hi=hi, max_ticks=4, fmt="{:.1f}", unit=" Mb")
        lab_h = self.markup("FTO", size=size).height
        ax = self._axes(plot_area, x_axis, y_axis, "−log₁₀ p", top=lab_h + 0.1)
        self.reg_axes = ax
        r = 0.05 if not self.is_portrait else 0.045
        dots = VGroup()
        for v in sorted(vs, key=lambda v: (v.lead, v.r2 or 0)):
            pt = ax.point(v.pos, min(v.mlog10p, ax.y.hi))
            if v.lead:
                mark = Square(side_length=r * 3.4).rotate(PI / 4).move_to(pt).set_fill(LEAD_COLOR, opacity=1).set_stroke(self.bg, width=1.5)
            else:
                c = R2_COLORS[gw.r2_bin(v.r2)] if v.r2 is not None else self.col1
                mark = Dot(pt, radius=r, color=c).set_stroke(self.bg, width=0.8)
            dots.add(mark)
        name = (f"<i>{pk.gene}</i>" if pk.gene else "") + (f"  {pk.lead.id}" if pk.lead.id and pk.lead.id != pk.gene else "")
        lead_lab = self.markup(name.strip() + f"  {p_label(pk.lead.mlog10p)}", size=size, color=self.ink)
        lp = ax.point(pk.lead.pos, min(pk.lead.mlog10p, ax.y.hi))
        lead_lab.move_to(lp + UP * (r * 2 + 0.06 + lead_lab.height / 2))
        lead_lab.set_x(min(max(lead_lab.get_x(), ax.plot.x0 + lead_lab.width / 2), ax.plot.x1 - lead_lab.width / 2))
        key.move_to(np.array([area.x0 + key.width / 2, area.y1 - key.height / 2, 0]))
        ys = ax.y_pos(-math.log10(gw.SIGNIFICANCE))
        sig = Line(np.array([ax.plot.x0, ys, 0]), np.array([ax.plot.x1, ys, 0])).set_stroke(self.bad, width=2)
        self.reg_parts = (VGroup(ax.group, key, sig), dots, lead_lab)
        return VGroup(*self.reg_parts)

    def regional_seconds(self) -> float:
        return REGIONAL_SECONDS

    def run_regional(self, label: str) -> list[Animation]:
        """Box the peak's window on the Manhattan plot, then draw its regional plot."""
        if self.reg_area is None or self.regional_mob is not None:
            return []
        pre = self.run_step("points")
        group = self._build_regional(label)
        self.regional_mob = group
        for target in self.targets:
            if "regional" in target.names:
                target.mobject.add(group)
        plan = self.plan
        pk = plan.peak(label)
        ax = self.m_axes
        x0, x1 = ax.x_pos(plan.offsets[pk.lead.chrom] + pk.start), ax.x_pos(plan.offsets[pk.lead.chrom] + pk.end)
        w = max(x1 - x0, 0.18)
        box = Rectangle(width=w, height=ax.plot.height).move_to(np.array([(x0 + x1) / 2, ax.plot.center[1], 0]))
        box.set_stroke(self.hi, width=2).set_fill(self.hi, opacity=0.08)
        frame, dots, lab = self.reg_parts
        plot = self.reg_axes.plot
        corners = [Line(box.get_corner(DL), np.array([plot.x0, plot.y1, 0]), stroke_width=1.2).set_stroke(self.hi, opacity=0.35),
                   Line(box.get_corner(DR), np.array([plot.x1, plot.y1, 0]), stroke_width=1.2).set_stroke(self.hi, opacity=0.35)]
        for c in corners:
            c.set_z_index(-1)
        group.add(box, *corners)
        return [Succession(*pre, Create(box), AnimationGroup(*[Create(c) for c in corners], FadeIn(frame)),
                           LaggedStart(*[FadeIn(d, scale=0.5) for d in dots], lag_ratio=0.01), FadeIn(lab))]

    # ----- targets and steps ------------------------------------------------------------------------

    def _register(self) -> None:
        p = self.params
        title = self.title_mob
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        plan = self.plan
        if self.man_area is not None:
            self.target("manhattan", VGroup(self.m_frame, self.points), entrance=lambda: self.run_step("points"))
            self.target("points", self.points, entrance=lambda: self.run_step("points"))
            for c, g in self.chrom_dots.items():
                self.target(f"chromosome:{c}", g, entrance=lambda g=g: [FadeIn(self.m_frame), LaggedStart(*[FadeIn(d) for d in g], lag_ratio=0.01)])
            self.target("thresholds", self.thresholds, entrance=lambda: self.run_step("thresholds"))
            self.target("significance", self.sig_line, entrance=lambda: self.run_step("thresholds"))
            self.target("suggestive", self.sug_line, entrance=lambda: self.run_step("thresholds"))
            self.target("peaks", self.peak_group, entrance=lambda: self.run_step("peaks"))
            for label, g in self.peak_marks.items():
                self.target(f"peak:{label}", g, entrance=lambda: self.run_step("peaks"))
            if self.sim_tag is not None:
                self.target("simulated", self.sim_tag)
            if p.regional is not None:
                self.target("regional", VGroup(), entrance=lambda: self.run_regional(p.regional))
        if self.qq_area is not None:
            self.target("qq", VGroup(self.qq_frame, self.qq_dots), entrance=lambda: self.run_step("qq"))
            self.target("lambda", self.lam, entrance=lambda: self.run_step("qq"))
            for pk in plan.peaks if self.man_area is None else ():
                self.target(pk.target, self.qq_dots)
            if self.man_area is None and self.sim_tag is not None:
                self.target("simulated", self.sim_tag)
        held: set[str] = set()
        for use in self.action_uses("reveal"):
            held.update(use.config.targets())
        late = {"points", "thresholds", "significance", "suggestive", "peaks", "qq", "lambda", "regional"} | {pk.target for pk in plan.peaks}
        manual = bool(held & late)

        def first() -> list[Animation]:
            anims: list[Animation] = [FadeIn(title)] if title is not None else []
            if self.man_area is not None and "manhattan" not in held:
                anims.append(FadeIn(self.m_frame))
            if self.man_area is None and "qq" not in held:
                anims += self.run_step("qq")
            return anims

        steps: list[Any] = [first]
        if not manual:
            if self.man_area is not None:
                steps += [lambda: self.run_step("points"), lambda: self.run_step("thresholds"), lambda: self.run_step("peaks")]
            if self.qq_area is not None and self.man_area is not None:
                steps.append(lambda: self.run_step("qq"))
            if p.regional is not None and self.reg_area is not None:
                steps.append(lambda: self.run_regional(p.regional))
        self.reveal(steps, fraction=0.88, cap=POINTS_SECONDS + 0.6)
        self.finish()

    def run_step(self, name: str) -> list[Animation]:
        if name in self.done:
            return []
        order = ("points", "thresholds", "peaks")
        anims: list[Animation] = []
        if name in order:
            for before in order[:order.index(name)]:
                anims += self.run_step(before)
        self.done.add(name)
        if name == "points":
            part: list[Animation] = []
            if not self.is_shown("manhattan"):
                part.append(FadeIn(self.m_frame))
            groups = [g for g in self.chrom_dots.values() if len(g)]
            part.append(LaggedStart(*[FadeIn(g, shift=UP * 0.08) for g in groups], lag_ratio=0.15))
        elif name == "thresholds":
            part = [AnimationGroup(Create(self.sig_line[0]), FadeIn(self.sig_line[1]), Create(self.sug_line[0]), FadeIn(self.sug_line[1]))]
        elif name == "peaks":
            part = [LaggedStart(*[AnimationGroup(Create(g[0]), FadeIn(g[1], shift=DOWN * 0.05)) for g in self.peak_marks.values()],
                                lag_ratio=0.3)] if self.peak_marks else []
        else:
            part = [Succession(FadeIn(self.qq_frame), LaggedStart(*[FadeIn(d) for d in self.qq_dots], lag_ratio=0.004), FadeIn(self.lam))]
        return [Succession(*anims, *part)] if anims else part
