"""``population``: population genetics (DESIGN.md §96.16), computed by
``vidgen.genetics.population``.

- ``model: hardy_weinberg``: a population of dots coloured by genotype (half and half for a
  heterozygote) and the working, step by step — the allele frequencies p and q (from counts,
  genotype frequencies, p or the incidence of a recessive condition), the expected genotype
  frequencies p², 2pq, q² (with F: p² + Fpq, 2pq(1 − F), q² + Fpq), the carrier frequency, and from
  counts the chi-square test of HWE (df = 1).
- ``model: drift | selection | mutation | migration | bottleneck | founder``: seeded Wright–Fisher
  lines of the allele frequency over generations (fixation and loss marked), the deterministic
  recursion where forces act, the first line's individuals as dots, and for a bottleneck or a
  founder event the heterozygosity with its expectation H_t = H₀ Π(1 − 1/2N_t).

Actions (``scenes/population_actions.py``): ``simulate`` (generations on a word), ``resample``
(the next generation's individuals, or a new sample of a Hardy–Weinberg population); the
built-in ``reveal`` plays the Hardy–Weinberg steps, ``highlight`` marks ``fixed`` / ``lost`` lines."""

from fractions import Fraction
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import driven, small_size, text_block
from .population_actions import target_generation

pg = genetics.population

#: The Hardy–Weinberg steps, in order.
HW_STEPS = ("alleles", "expected", "carriers", "chi_square")
#: Seconds of a whole simulation (simulate scales it by the generations covered).
RUN_SECONDS = 3.2


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@scene("population")
class PopulationScene(NarratedScene):
    """Population genetics. ``model: hardy_weinberg``: the population as dots by genotype and the
    working — p and q from genotype ``counts`` (p = (2n_AA + n_Aa) / 2N), genotype
    ``frequencies``, ``p`` or the ``incidence`` of a recessive condition (q = √incidence: 1/2500
    gives q = 1/50 and carriers 2pq = 49/1250 ≈ 1 in 25.5), the expected p², 2pq, q² (with
    ``inbreeding`` F), and from counts the chi-square test of Hardy–Weinberg proportions with
    df = 1. ``model: drift`` (and ``selection``, ``mutation``, ``migration``, ``bottleneck``,
    ``founder``): seeded Wright–Fisher simulations of N diploids — several replicate lines of the
    allele frequency over generations (smaller N drifts faster; fixation and loss marked), the
    deterministic recursion of selection (``fitness`` or ``s`` and ``h``), mutation (``mu``,
    ``nu``) or migration (``m`` between two ``populations``), the individuals of the first line as
    dots, and the heterozygosity through a bottleneck or after a founder event.

    Action targets: ``title``, ``population``, and ``alleles``, ``expected``, ``carriers``,
    ``chi_square`` (hardy_weinberg); ``plot``, ``lines``, ``line:<n>``, ``deterministic``,
    ``fixed``, ``lost``, ``heterozygosity``, ``generation:<t>`` (simulations)."""

    outro = 0.5
    target_patterns = ("title", "population", "alleles", "expected", "carriers", "chi_square", "plot", "lines", "line:<n>",
                       "deterministic", "fixed", "lost", "heterozygosity", "generation:<t>")
    #: The actions simulate and resample act on this scene type.
    population_actions = True
    mid_still_actions = frozenset({"simulate", "resample"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        model: Literal["hardy_weinberg", "drift", "selection", "mutation", "migration", "bottleneck", "founder"] = "hardy_weinberg"
        """hardy_weinberg (worked numbers) or a seeded simulation: drift, selection, mutation, migration, bottleneck, founder."""
        alleles: list[str] | None = None
        """The two alleles, [A, a] by default; p is the frequency of the first."""
        counts: dict[str, int] | None = None
        """hardy_weinberg: genotype counts {AA: 360, Aa: 480, aa: 160} (gives the chi-square test of HWE)."""
        frequencies: dict[str, Any] | None = None
        """hardy_weinberg: genotype frequencies {AA: 0.36, Aa: 0.48, aa: 0.16} (adding up to 1)."""
        p: Any = None
        """hardy_weinberg: the frequency of the first allele (0–1, 0.6, '3/5', '60%')."""
        incidence: Any = None
        """hardy_weinberg: the incidence of the recessive condition (q² = incidence: 1/2500)."""
        condition: TranslatableStr = ""
        """hardy_weinberg: the condition's name for the incidence (cystic fibrosis)."""
        inbreeding: Any = None
        """hardy_weinberg: the inbreeding coefficient F (genotypes p² + Fpq, 2pq(1 − F), q² + Fpq)."""
        total: int | None = None
        """hardy_weinberg: the number sampled, checked against the counts' sum."""
        N: int | None = None
        """Simulations: the population size (diploid individuals: 2N gene copies); needed for drift, bottleneck, founder."""
        p0: Any = None
        """Simulations: the starting frequency of the first allele."""
        generations: int | None = None
        """Simulations: how many generations (default 100)."""
        replicates: int | None = None
        """Simulations with N: how many independent lines (default 6, at most 20)."""
        fitness: dict[str, float] | None = None
        """selection: relative fitnesses {AA: 1, Aa: 1, aa: 0.8} (none negative)."""
        s: Any = None
        """selection: the selection coefficient against the second allele's homozygote (w = 1, 1 − hs, 1 − s)."""
        h: Any = None
        """selection: the dominance coefficient (0 recessive, 0.5 additive, 1 dominant; default 0.5)."""
        mu: Any = None
        """The mutation rate from the first allele to the second, per copy per generation."""
        nu: Any = None
        """The back-mutation rate (second to first)."""
        populations: list[Any] | None = None
        """migration: two populations [{name: mainland, p0: 0.9}, {name: island, p0: 0.1}]."""
        m: Any = None
        """migration: the share of each generation's parents that are migrants (0–1)."""
        direction: Literal["both", "one_way"] | None = None
        """migration: both (the populations exchange migrants) or one_way (from the first to the second: continent → island)."""
        bottleneck: dict[str, int] | None = None
        """bottleneck: {at: 20, N: 10, generations: 5} — when it starts, its size, how long it lasts."""
        founders: int | None = None
        """founder: how many individuals found the new population (from a source at p0); it then has N."""
        heterozygosity: bool | None = None
        """Draw the heterozygosity under the allele frequencies (drift, bottleneck, founder; default: bottleneck and founder)."""
        seed: int = 1
        """The random seed: the same seed gives the same lines and dots."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def spec(self) -> dict[str, Any]:
            data: dict[str, Any] = {"model": self.model, "seed": self.seed}
            keys = ("alleles", "counts", "frequencies", "p", "incidence", "inbreeding", "total", "N", "p0", "generations", "replicates",
                    "fitness", "s", "h", "mu", "nu", "populations", "m", "direction", "bottleneck", "founders")
            for key in keys:
                if getattr(self, key) is not None:
                    data[key] = getattr(self, key)
            if self.condition:
                data["condition"] = str(self.condition)
            return data

        def plan(self) -> Any:
            return pg.plan_population(self.spec())

        def shows_h(self) -> bool:
            """Whether the heterozygosity panel is drawn."""
            sim = self.plan().sim
            if sim is None or not sim.h_expected:
                return False
            return self.heterozygosity if self.heterozygosity is not None else sim.model in ("bottleneck", "founder")

        @model_validator(mode="after")
        def _check(self) -> "PopulationScene.Params":
            try:
                plan = self.plan()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            if self.heterozygosity and not (plan.sim is not None and plan.sim.h_expected):
                raise ValueError("heterozygosity: drawn for drift, bottleneck and founder simulations with N (and no mutation), "
                                 "where it falls as H₀ Π(1 − 1/2N)")
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        plan = params.plan()
        names = ["title"] if params.title else []
        names.append("population")
        if plan.hw is not None:
            hw = plan.hw
            names += ["alleles", "expected"]
            names += ["carriers"] if hw.source == "incidence" else []
            names += ["chi_square"] if hw.test is not None else []
            return names
        sim = plan.sim
        names += ["plot", "lines"] if sim.lines else ["plot"]
        names += [f"line:{k + 1}" for k in range(len(sim.lines))]
        names += ["deterministic"] if sim.deterministic else []
        names += ["fixed"] if sim.fixed() else []
        names += ["lost"] if sim.lost() else []
        names += ["heterozygosity"] if params.shows_h() else []
        names += [f"generation:{t}" for t in range(1, sim.generations + 1)]
        return names

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """``simulate`` in beat and ``at`` order must go forward in generations."""
        plan = params.plan()
        if plan.sim is None:
            return []
        beats = [b.id for b in spec.beats]
        order = sorted(range(len(uses)), key=lambda i: (beats.index(uses[i].beat) if uses[i].beat in beats else 0, uses[i].config.fraction, i))
        reached = 0
        problems: list[tuple[str, str]] = []
        for i in order:
            use = uses[i]
            if use.kind.name == "resample":
                reached += 1
            elif use.kind.name == "simulate":
                t = target_generation(params, use.config.targets())
                if t <= reached:
                    problems.append((f"{use.location}.target", f"the simulation is at generation {reached} already; "
                                     f"simulate goes forward (a later generation than {reached})"))
                reached = max(reached, t)
        return problems

    @classmethod
    def hw_steps(cls, params: Any) -> list[str]:
        names = cls.target_names(params)
        return [s for s in HW_STEPS if s in names]

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.plan = p.plan()
        self.show_h = p.shows_h()
        self.ink, self.dim_ink, self.bg = th.color("text"), th.color("dim"), th.background
        self.hi, self.bad, self.good = th.color("highlight"), th.color("accent"), th.color("tertiary")
        self.col_a, self.col_b = th.color("primary"), th.color("secondary")
        self.small = small_size(self, p.size)
        self.tiny = max(readable_size() * 1.02, self.small * 0.9)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.25)
        self.title_mob = title
        self.done: set[str] = set()
        self.card_mob: Mobject | None = None
        self.blocks: list[Mobject] = []
        self.dot_scale = ""
        self.legend_counts: tuple[int, int, int] | None = None
        if self.plan.hw is not None:
            self._build_hw(body)
        else:
            self._build_sim(body)
        self._register()

    # ----- dots -------------------------------------------------------------------------------------

    def _dot(self, r: float) -> VGroup:
        """An individual: a disc in the first allele's colour with its right half in the
        second's (one colour for a homozygote, half and half for a heterozygote)."""
        disc = Circle(radius=r).set_stroke(width=0)
        right = Sector(radius=r, angle=PI, start_angle=-PI / 2).set_stroke(width=0)
        ring = Circle(radius=r).set_fill(opacity=0).set_stroke(self.ink, width=1.2, opacity=0.6)
        return VGroup(disc, right, ring)

    def _colors(self, g: int) -> tuple[str, str]:
        return (self.col_a, self.col_a) if g == 0 else (self.col_a, self.col_b) if g == 1 else (self.col_b, self.col_b)

    def _paint(self, dot: VGroup, g: int, visible: bool = True) -> None:
        a, b = self._colors(g)
        dot[0].set_fill(a, opacity=1.0 if visible else 0.0)
        dot[1].set_fill(b, opacity=1.0 if visible else 0.0)
        dot[2].set_stroke(opacity=0.6 if visible else 0.0)

    def _build_dots(self, area: Region, count: int, genotypes: list[int]) -> None:
        """A grid of ``count`` dots in the upper part of ``area`` and the genotype legend under it."""
        legend_h = self.markup("Aa", size=self.small).height * 1.2 + self.markup("Aa", size=self.tiny).height * 2.5 + 0.25
        grid = Region(area.x0, area.y0 + legend_h, area.x1, area.y1)
        cols = int(np.ceil(np.sqrt(count * grid.width / max(grid.height, 0.1))))
        cols = max(1, min(count, cols))
        rows = int(np.ceil(count / cols))
        cols = int(np.ceil(count / rows))
        pitch = min(grid.width / cols, grid.height / rows, 0.42)
        r = pitch * 0.38
        x0 = grid.center[0] - pitch * (cols - 1) / 2
        y0 = grid.y1 - pitch / 2 - (grid.height - pitch * rows) / 2
        self.dots: list[VGroup] = []
        for k in range(count):
            d = self._dot(r).move_to(np.array([x0 + (k % cols) * pitch, y0 - (k // cols) * pitch, 0]))
            self._paint(d, genotypes[k] if k < len(genotypes) else 0, k < len(genotypes))
            self.dots.append(d)
        self.dot_group = VGroup(*self.dots)
        self.legend_area = Region(area.x0, area.y0, area.x1, area.y0 + legend_h)
        self.legend_mob = self._legend(genotypes, self.dot_scale, self.legend_counts)

    def _legend(self, genotypes: list[int], extra: str = "", counts: tuple[int, int, int] | None = None) -> VGroup:
        """The genotypes with their numbers (the dots', or ``counts`` when one dot stands for
        several people) and a note: how many, p, ``extra``."""
        names = pg.genotype_names(self.plan.alleles)
        shown = list(counts) if counts is not None else [genotypes.count(g) for g in range(3)]
        items = []
        for g in range(3):
            sw = self._dot(self.markup("A", size=self.small).height * 0.6)
            self._paint(sw, g)
            t = self.markup(f"<i>{_esc(names[g])}</i> {shown[g]}", size=self.small, color=self.ink)
            items.append(VGroup(sw, t).arrange(RIGHT, buff=0.1))
        row = VGroup(*items).arrange(RIGHT, buff=0.4)
        if row.width > self.legend_area.width:
            row.arrange(RIGHT, buff=0.18)
        n = sum(shown)
        a = self.plan.alleles[0]
        note = f"{n} individuals · p({a}) = {(2 * shown[0] + shown[1]) / (2 * n):.2f}" if n else ""
        width = self.legend_area.width
        lines = [row] + ([text_block(self, _esc(note + extra), width, self.tiny, color=self.dim_ink, align=ORIGIN)] if note else [])
        for line in lines:
            if line.width > self.legend_area.width:
                line.scale(self.legend_area.width / line.width)
        legend = VGroup(*lines).arrange(DOWN, buff=0.12)
        return legend.move_to(self.legend_area.center)

    # ----- Hardy–Weinberg ---------------------------------------------------------------------------

    def _build_hw(self, body: Region) -> None:
        hw = self.plan.hw
        if not self.is_portrait:
            left, right = body.columns([0.36, 0.64], gap=0.5)
        else:
            left, right = body.rows([0.42, 0.58], gap=0.3)
        self.card_area = right
        if hw.counts is not None:
            n = sum(hw.counts)
            exact = n <= pg.DOTS
            gen = [g for g in range(3) for _ in range(hw.counts[g])] if exact else pg.proportional_dots(hw.counts, pg.DOTS, self.plan.seed)
            if exact:
                np.random.default_rng(self.plan.seed).shuffle(gen)
            else:
                self.legend_counts = hw.counts
                self.dot_scale = f" · a dot ≈ {n / pg.DOTS:.3g} people"
        else:
            gen = pg.proportional_dots(tuple(float(x) for x in hw.expected), pg.DOTS, self.plan.seed)
            self.dot_scale = " · the expected shares"
        self._build_dots(left, len(gen), gen)
        self.resamples = 0

    def _block(self, head: str, lines: list[str]) -> VGroup:
        area = self.card_area
        parts: list[Mobject] = [self.markup(f"<b>{_esc(head)}</b>", size=self.small * 1.08, color=self.ink)]
        for line in lines:
            parts.append(text_block(self, line, area.width - 0.1, self.small, color=self.ink))
        block = VGroup(*parts).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
        if block.width > area.width:
            block.scale(area.width / block.width)
        if block.height > area.height:
            block.scale(area.height / block.height)
        return block

    def _stack(self, block: Mobject) -> list[Animation]:
        """Put ``block`` under the blocks shown; when it does not fit, the earlier ones leave and
        it goes to the top."""
        area = self.card_area
        anims: list[Animation] = []
        top = self.blocks[-1].get_bottom()[1] - 0.28 if self.blocks else area.y1
        if top - block.height < area.y0 - 1e-6 and self.blocks:
            anims.append(AnimationGroup(*[FadeOut(b) for b in self.blocks]))
            self.blocks = []
            top = area.y1
        block.move_to(np.array([area.x0 + block.width / 2, top - block.height / 2, 0]))
        self.blocks.append(block)
        anims.append(FadeIn(block, shift=UP * 0.06))
        return [Succession(*anims)] if len(anims) > 1 else anims

    def _hw_lines(self, name: str) -> tuple[str, list[str]]:
        hw = self.plan.hw
        a, b = (f"<i>{_esc(x)}</i>" for x in hw.alleles)
        g = [f"<i>{_esc(x)}</i>" for x in hw.genotypes]
        ft, dec = pg.frac_text, pg.dec

        def num(x: Any) -> str:
            if isinstance(x, Fraction) and x.denominator not in (1,) and x.denominator <= 5000 and dec(x) != ft(x):
                return f"{ft(x)} = {dec(x)}"
            return dec(x)

        if name == "alleles":
            if hw.source == "counts":
                n = sum(hw.counts)
                lines = [f"p = f({a}) = (2 × n<sub>{g[0]}</sub> + n<sub>{g[1]}</sub>) / 2N = (2 × {hw.counts[0]} + {hw.counts[1]}) / {2 * n} = {num(hw.p)}",
                         f"q = f({b}) = 1 − p = {num(hw.q)}"]
            elif hw.source == "frequencies":
                f = hw.observed_freq
                lines = [f"p = f({g[0]}) + ½ f({g[1]}) = {dec(f[0])} + {dec(f[1] / 2)} = {num(hw.p)}", f"q = 1 − p = {num(hw.q)}"]
            elif hw.source == "p":
                lines = [f"p = f({a}) = {num(hw.p)}", f"q = f({b}) = 1 − p = {num(hw.q)}"]
            else:
                cond = _esc(hw.condition) if hw.condition else "the recessive condition"
                q_text = f"√({ft(hw.incidence)}) = {num(hw.q)}" if hw.exact else f"√{dec(hw.incidence)} ≈ {dec(hw.q)}"
                lines = [f"{cond}: incidence = f({g[2]}) = q² = {ft(hw.incidence)}",
                         f"q = {q_text}", f"p = 1 − q = {num(hw.p)}"]
            return "Allele frequencies", lines
        if name == "expected":
            e = hw.expected
            F = hw.inbreeding
            if F:
                lines = [f"with inbreeding F = {dec(F)}: {g[0]} = p² + Fpq, {g[1]} = 2pq(1 − F), {g[2]} = q² + Fpq",
                         f"{g[0]} {dec(e[0])} · {g[1]} {dec(e[1])} · {g[2]} {dec(e[2])}"]
            else:
                lines = ["p² + 2pq + q² = 1 under random mating",
                         f"{g[0]}: p² = {num(e[0])} · {g[1]}: 2pq = {num(e[1])} · {g[2]}: q² = {num(e[2])}"]
            if hw.counts is not None:
                n = sum(hw.counts)
                lines.append(f"expected of {n}: " + ", ".join(f"{g[i]} {float(e[i]) * n:.1f}" for i in range(3))
                             + " · observed: " + ", ".join(str(c) for c in hw.counts))
            return "Expected genotype frequencies", lines
        if name == "carriers":
            c = hw.carrier
            ratio = float(c) / float(hw.expected[2])
            lines = [f"carriers ({g[1]}): 2pq = 2 × {ft(hw.p) if hw.exact else dec(hw.p)} × {ft(hw.q) if hw.exact else dec(hw.q)} = "
                     f"{num(c)} ≈ {pg.one_in(c)}",
                     *hw.notes,
                     f"about {ratio:.0f} carriers for every affected person: most copies of a rare recessive allele are in carriers"]
            return "Carrier frequency", lines
        t = hw.test
        parts = " + ".join(f"{float(x):.3f}" for x in t.contributions)
        pt = _esc(genetics.stats.p_text(t.p_value))
        verdict = (f"{pt} &lt; 0.05: the genotypes depart from Hardy–Weinberg proportions"
                   if t.rejected else f"{pt} ≥ 0.05: consistent with Hardy–Weinberg proportions")
        lines = [f"χ² = Σ (O − E)² / E = {parts} = {float(t.statistic):.3f}",
                 f"df = 3 genotypes − 1 − 1 estimated allele frequency = 1 (critical value {t.critical:.2f} at α = 0.05)",
                 verdict]
        if hw.f_hat is not None and abs(float(hw.f_hat)) >= 0.05:
            kind = "deficit" if hw.f_hat > 0 else "excess"
            lines.append(f"heterozygote {kind}: F̂ = 1 − H_obs / H_exp = {float(hw.f_hat):.3f}")
        if t.small:
            lines.append(f"expected count below 5 for {', '.join(t.small)}: an exact test is better here")
        return "Chi-square test of HWE", lines

    # ----- simulations -----------------------------------------------------------------------------

    def _build_sim(self, body: Region) -> None:
        sim = self.plan.sim
        two = self.show_h
        if not self.is_portrait:
            left, right = body.columns([0.62, 0.38], gap=0.45)
            plots = left.rows([0.6, 0.4], gap=0.3) if two else [left]
            dots_area, self.card_area = right.rows([0.46, 0.54], gap=0.3)
        else:
            shares = [0.38, 0.2, 0.17, 0.25] if two else [0.46, 0.22, 0.32]
            regions = body.rows(shares, gap=0.25)
            plots = regions[:2] if two else regions[:1]
            dots_area, self.card_area = regions[-2], regions[-1]
        T = sim.generations
        a = self.plan.alleles[0]
        x_axis = value_axis([0, T], lo=0, hi=T, max_ticks=5 if self.is_portrait else 6, title="generation")
        y_axis = ChartAxis(0.0, 1.0, (0.0, 0.25, 0.5, 0.75, 1.0), ("0", "0.25", "0.5", "0.75", "1"), False, f"frequency of {a}")
        self.axes = chart_axes(plots[0], x_axis, y_axis, size=self.params.size)
        self.plot_group = VGroup(self.axes.group)
        self.palette = [self.theme.palette_color(k) for k in range(max(1, len(sim.lines)))]
        self.line_mobs: list[VMobject] = []
        self.ends: dict[int, Mobject] = {}
        for k, line in enumerate(sim.lines):
            color = (self.col_a, self.col_b)[line.population] if len(sim.populations) == 2 else self.palette[k % len(self.palette)]
            mob = VMobject().set_stroke(color, width=3 if len(sim.lines) > 6 else 3.5, opacity=0.9)
            mob.set_points_as_corners([self.axes.point(0, line.values[0]), self.axes.point(0, line.values[0]) + RIGHT * 1e-3])
            self.line_mobs.append(mob)
            t_end = line.fixed_at if line.fixed_at is not None else line.lost_at
            if t_end is not None:
                mark = Dot(self.axes.point(t_end, line.values[t_end]), radius=0.06, color=color).set_stroke(self.bg, width=2)
                self.ends[k] = mark.set_z_index(3)
        self.det_mobs: list[VMobject] = []
        if sim.deterministic:
            for k, curve in enumerate(sim.deterministic):
                color = self.ink if sim.lines else ((self.col_a, self.col_b)[k] if len(sim.deterministic) == 2 else self.col_a)
                mob = VMobject().set_stroke(color, width=5 if not sim.lines else 6, opacity=1.0)
                mob.set_points_as_corners([self.axes.point(0, curve[0]), self.axes.point(0, curve[0]) + RIGHT * 1e-3])
                self.det_mobs.append(mob.set_z_index(2))
        self.extras = VGroup()
        size = self.tiny
        if sim.bottleneck is not None:
            at, nb, dur = sim.bottleneck
            self.band_mobs = [self._band(ax, at, at + dur, nb) for ax in [self.axes]]
            self.extras.add(*self.band_mobs)
        if sim.source_p is not None:
            y = self.axes.y_pos(sim.source_p)
            line = DashedLine(np.array([self.axes.plot.x0, y, 0]), np.array([self.axes.plot.x1, y, 0]), dash_length=0.1)
            line.set_stroke(self.dim_ink, width=2)
            lab = self.markup(f"source p = {pg.dec(sim.source_p)}", size=size, color=self.dim_ink)
            lab.next_to(np.array([self.axes.plot.x1, y, 0]), UP, buff=0.06).align_to(np.array([self.axes.plot.x1, 0, 0]), RIGHT)
            self.extras.add(line, lab)
        self.h_group = VGroup()
        if two:
            hx = value_axis([0, T], lo=0, hi=T, max_ticks=5 if self.is_portrait else 6, title="")
            top = max(sim.h_expected[0], max(sim.h_mean)) if sim.h_mean else sim.h_expected[0]
            hi = 0.5 if top > 0.3 else 0.3 if top > 0.2 else 0.2
            hy = value_axis([0, hi], lo=0, hi=hi, max_ticks=3, title="H" if self.is_portrait else "heterozygosity H")
            self.h_axes = chart_axes(plots[1], hx, hy, size=self.params.size)
            self.h_exp = VMobject().set_stroke(self.ink, width=3)
            self.h_obs = VMobject().set_stroke(self.hi, width=3.5)
            for mob, vals in ((self.h_exp, sim.h_expected), (self.h_obs, sim.h_mean)):
                mob.set_points_as_corners([self.h_axes.point(0, vals[0]), self.h_axes.point(0, vals[0]) + RIGHT * 1e-3])
            key = VGroup(
                VGroup(Line(ORIGIN, RIGHT * 0.4).set_stroke(self.ink, width=3), self.markup("expected", size=size, color=self.dim_ink)).arrange(RIGHT, buff=0.1),
                VGroup(Line(ORIGIN, RIGHT * 0.4).set_stroke(self.hi, width=3.5), self.markup("mean of lines", size=size, color=self.dim_ink)).arrange(RIGHT, buff=0.1),
            ).arrange(RIGHT, buff=0.3)
            self._title_row(key, self.h_axes)
            self.h_key = key
            self.h_group = VGroup(self.h_axes.group, self.h_key)
            if sim.bottleneck is not None:
                at, nb, dur = sim.bottleneck
                band = self._band(self.h_axes, at, at + dur, None)
                self.band_mobs.append(band)
                self.h_group.add(band)
        # the generation counter, at the plot's top right
        self.gen_now = 0
        self.gen_label = self._gen_label(0)
        # dots: the first line's individuals
        count = min(pg.DOTS, max(sim.sizes)) if sim.sizes else pg.DOTS
        self.dot_count = count
        self._build_dots(dots_area, count, sim.individuals(0, count))

    def _band(self, axes: Any, t0: int, t1: int, nb: int | None) -> VGroup:
        x0, x1 = axes.x_pos(t0), axes.x_pos(min(t1, axes.x.hi))
        rect = Rectangle(width=max(x1 - x0, 0.04), height=axes.plot.height).move_to(np.array([(x0 + x1) / 2, axes.plot.center[1], 0]))
        rect.set_fill(self.bad, opacity=0.14).set_stroke(width=0)
        rect.set_z_index(-1)
        group = VGroup(rect)
        if nb is not None:
            # the size on a plate over the lines, at the top of the band
            t = self.markup(f"N = {nb}", size=self.tiny, color=self.bad)
            t.move_to(np.array([(x0 + x1) / 2, axes.plot.y1 - t.height / 2 - 0.06, 0]))
            t.set_x(min(max(t.get_x(), axes.plot.x0 + t.width / 2 + 0.06), axes.plot.x1 - t.width / 2 - 0.06))
            back = BackgroundRectangle(t, color=self.bg, fill_opacity=0.85, buff=0.05)
            group.add(VGroup(back, t).set_z_index(5))
        return group

    def _gen_label(self, t: int) -> Mobject:
        sim = self.plan.sim
        text = f"generation {t}"
        if sim.sizes is not None and (len(set(sim.sizes)) > 1 or not self.is_portrait):
            text += f" · N = {sim.sizes[t]}"
        return self._title_row(self.markup(text, size=self.tiny, color=self.dim_ink), self.axes)

    @staticmethod
    def _title_row(mob: Mobject, axes: Any) -> Mobject:
        """``mob`` right-aligned in the row of the axes' y title (above the plot), narrowed to
        the room the title leaves."""
        plot = axes.plot
        left = axes.y_title.get_right()[0] + 0.3 if axes.y_title is not None else plot.x0
        room = plot.x1 - left
        if mob.width > room > 0:
            mob.scale(room / mob.width)
        y = axes.y_title.get_y() if axes.y_title is not None else plot.y1 + mob.height / 2 + 0.06
        return mob.move_to(np.array([plot.x1 - mob.width / 2, y, 0]))

    # ----- cards ------------------------------------------------------------------------------------

    def _card(self, head: str, lines: list[str]) -> VGroup:
        """The card, dropping its last lines rather than shrinking the text below the readable size."""
        area = self.card_area
        items = list(lines)
        while True:
            parts: list[Mobject] = [self.markup(f"<b>{_esc(head)}</b>", size=self.small * 1.08, color=self.ink)]
            parts += [text_block(self, line, area.width - 0.1, self.small, color=self.ink) for line in items]
            card = VGroup(*parts).arrange(DOWN, buff=0.12, aligned_edge=LEFT)
            if card.height <= area.height or len(items) <= 1:
                break
            items = items[:-1]
        if card.height > area.height:
            card.scale(area.height / card.height)
        return card.move_to(np.array([area.x0 + card.width / 2, area.y1 - card.height / 2, 0]))

    def _swap(self, card: Mobject) -> list[Animation]:
        anims: list[Animation] = []
        if self.card_mob is not None:
            anims.append(FadeOut(self.card_mob))
        self.card_mob = card
        anims.append(FadeIn(card, shift=UP * 0.06))
        return [AnimationGroup(*anims, lag_ratio=0.4)]

    def _intro_lines(self) -> tuple[str, list[str]]:
        sim = self.plan.sim
        heads = {"drift": "Genetic drift", "selection": "Natural selection", "mutation": "Mutation", "migration": "Migration",
                 "bottleneck": "A bottleneck", "founder": "A founder effect"}
        lines = []
        nbsp = "\u00a0"     # a population's name stays in one piece when the line wraps
        names = ['<span\tforeground="' + c + '"><b>' + _esc(n).replace(" ", nbsp) + "</b></span>"
                 for n, c in zip(sim.populations, (self.col_a, self.col_b))]
        if sim.sizes is not None:
            n = sim.N
            lines.append(f"Wright–Fisher: N = {n} diploids, {2 * n} gene copies drawn at random each generation; "
                         f"{len(sim.lines)} independent line{'s' if len(sim.lines) != 1 else ''} from p₀ = {pg.dec(sim.p0[0])}"
                         if len(sim.populations) == 1 else
                         f"Wright–Fisher: N = {n} in each population; {names[0]} p₀ = {pg.dec(sim.p0[0])}, "
                         f"{names[1]} p₀ = {pg.dec(sim.p0[1])}")
        elif len(sim.populations) == 2:
            lines.append(f"{names[0]} p₀ = {pg.dec(sim.p0[0])}, {names[1]} p₀ = {pg.dec(sim.p0[1])}; "
                         f"m = {pg.dec(sim.m)} (no drift: an infinite population)")
        else:
            lines.append(f"the deterministic recursion (an infinite population) from p₀ = {pg.dec(sim.p0[0])}")
        if sim.lines and sim.deterministic:
            lines.append("the thick line: the expected course without drift")
        lines += [_esc(x) for x in sim.notes if self.show_h or not x.startswith("heterozygosity falls")]
        return heads[sim.model], lines

    def _summary_lines(self) -> tuple[str, list[str]]:
        sim = self.plan.sim
        a = self.plan.alleles[0]
        lines: list[str] = []
        if sim.lines:
            fixed, lost = len(sim.fixed()), len(sim.lost())
            rest = len(sim.lines) - fixed - lost
            lines.append(f"after {sim.generations} generations: {a} fixed in {fixed}, lost in {lost}, still segregating in {rest} "
                         f"of {len(sim.lines)} lines")
        if sim.deterministic:
            ends = ", ".join(f"{name} {pg.dec(curve[-1], 3)}" if len(sim.deterministic) == 2 else pg.dec(curve[-1], 3)
                             for name, curve in zip(sim.populations, sim.deterministic))
            lines.append(f"deterministic p after {sim.generations} generations: {ends}")
        if self.show_h:
            h0, ht = sim.h_expected[0], sim.h_expected[-1]
            lines.append(f"H: expected {ht:.3f} (from {h0:.3f}), mean of the lines {sim.h_mean[-1]:.3f}")
        if sim.model == "drift" and sim.N is not None:
            lines.append("smaller N drifts faster: each generation is a sample of only 2N gene copies")
        return "The outcome", lines

    # ----- targets and steps ------------------------------------------------------------------------

    def _register(self) -> None:
        p = self.params
        title = self.title_mob
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        pop = VGroup(self.dot_group, self.legend_mob)
        self.target("population", pop, entrance=lambda: [FadeIn(self.dot_group), FadeIn(self.legend_mob)])
        held: set[str] = set()
        for use in self.action_uses("reveal"):
            held.update(use.config.targets())
        acted = bool(self.action_uses("simulate")) or bool(self.action_uses("resample"))
        if self.plan.hw is not None:
            steps_here = self.hw_steps(p)
            self.hw_targets = {n: self.target(n, VGroup(), entrance=lambda n=n: self.run_step(n)) for n in steps_here}
            manual = bool(held & set(steps_here))

            def first() -> list[Animation]:
                anims: list[Animation] = [FadeIn(title)] if title is not None else []
                if "population" not in held:
                    anims += [FadeIn(self.dot_group, lag_ratio=0.01), FadeIn(self.legend_mob)]
                return anims

            steps: list[Any] = [first]
            if not manual:
                steps += [lambda n=n: self.run_step(n) for n in steps_here]
        else:
            sim = self.plan.sim
            self.target("plot", self.plot_group, entrance=lambda: self._show_plot())
            if sim.lines:
                self.target("lines", VGroup(*self.line_mobs, *self.ends.values()))
            for k, mob in enumerate(self.line_mobs):
                self.target(f"line:{k + 1}", VGroup(mob, *([self.ends[k]] if k in self.ends else [])))
            if sim.deterministic:
                self.target("deterministic", VGroup(*self.det_mobs))
            if sim.fixed():
                self.target("fixed", VGroup(*[VGroup(self.line_mobs[k], self.ends[k]) for k in sim.fixed()]))
            if sim.lost():
                self.target("lost", VGroup(*[VGroup(self.line_mobs[k], self.ends[k]) for k in sim.lost()]))
            if self.show_h:
                self.target("heterozygosity", VGroup(self.h_group, self.h_exp, self.h_obs), entrance=lambda: [FadeIn(self.h_group)])
            for t in range(1, sim.generations + 1):
                self.target(f"generation:{t}", self.gen_label, entrance=lambda t=t: self.advance_to(t))
            manual = acted or bool(held & {f"generation:{t}" for t in range(1, sim.generations + 1)})

            def first() -> list[Animation]:
                anims: list[Animation] = [FadeIn(title)] if title is not None else []
                if "plot" not in held:
                    anims += self._show_plot()
                if "population" not in held:
                    anims += [FadeIn(self.dot_group, lag_ratio=0.01), FadeIn(self.legend_mob)]
                return anims

            T = sim.generations
            steps = [first]
            if not manual:
                stops = sorted({max(1, round(T * 0.35)), T})
                steps += [lambda t=t: self.advance_to(t) for t in stops]
        self.reveal(steps, fraction=0.88, cap=RUN_SECONDS + 0.6)
        self.finish()

    def _show_plot(self) -> list[Animation]:
        if "plot" in self.done:
            return []
        self.done.add("plot")
        head, lines = self._intro_lines()
        parts: list[Animation] = [FadeIn(self.plot_group), FadeIn(self.extras), FadeIn(self.gen_label)]
        if self.show_h:
            parts.append(FadeIn(self.h_group))
        return [AnimationGroup(*parts, *self._swap(self._card(head, lines)))]

    # ----- Hardy–Weinberg steps ----------------------------------------------------------------------

    def run_step(self, name: str) -> list[Animation]:
        """A Hardy–Weinberg step's block (and the steps before it that have not played)."""
        if name in self.done:
            return []
        steps = self.hw_steps(self.params)
        anims: list[Animation] = []
        for before in steps[:steps.index(name)]:
            if before not in self.done:
                anims += self.run_step(before)
        self.done.add(name)
        head, lines = self._hw_lines(name)
        block = self._block(head, lines)
        self.hw_targets[name].mobject.add(block)
        part = self._stack(block)
        return [Succession(*anims, *part)] if anims else part

    # ----- simulation steps ---------------------------------------------------------------------------

    def simulate_seconds(self, t: int) -> float:
        sim = self.plan.sim
        span = max(0, t - self.gen_now) / sim.generations
        return max(1.0, 1.0 + (RUN_SECONDS - 1.0) * span)

    def advance_to(self, t: int, pulse: bool = False) -> list[Animation]:
        """Grow every line (and the deterministic curves and heterozygosity) to generation ``t``,
        update the counter and the dots; at the last generation the outcome card."""
        sim = self.plan.sim
        t = min(t, sim.generations)
        pre = self._show_plot()
        start = self.gen_now
        if t <= start:
            return pre
        self.gen_now = t
        axes = self.axes
        series: list[tuple[VMobject, Any, tuple[float, ...]]] = []
        for mob, line in zip(self.line_mobs, sim.lines):
            series.append((mob, axes, line.values))
        for mob, curve in zip(self.det_mobs, sim.deterministic or ()):
            series.append((mob, axes, curve))
        if self.show_h:
            series += [(self.h_exp, self.h_axes, sim.h_expected), (self.h_obs, self.h_axes, sim.h_mean)]
        pts = {id(mob): [ax.point(g, v) for g, v in enumerate(vals)] for mob, ax, vals in series}

        def frame(alpha: float) -> None:
            g = start + (t - start) * alpha
            k = int(np.floor(g))
            for mob, ax, vals in series:
                ps = pts[id(mob)]
                head = list(ps[: k + 1])
                if k < t:
                    f = g - k
                    head.append(ps[k] + (ps[k + 1] - ps[k]) * f)
                if len(head) < 2:
                    head = [ps[0], ps[0] + RIGHT * 1e-3]
                mob.set_points_as_corners(head)
            if k != shown[0]:                       # the counter follows the lines
                shown[0] = k
                self.gen_label.become(self._gen_label(k))

        shown = [start]
        group = VGroup(*[m for m, _, _ in series], self.gen_label)
        grow = driven(group, frame, rate_func=linear)
        marks = [FadeIn(self.ends[k], scale=1.6) for k, line in enumerate(sim.lines)
                 if k in self.ends and start < (line.fixed_at if line.fixed_at is not None else line.lost_at) <= t]
        anims: list[Animation] = [*pre, grow]
        after: list[Animation] = [*self._redot(sim.individuals(t, self.dot_count), pulse)]
        if marks:
            after += marks
        if t == sim.generations:
            head, lines = self._summary_lines()
            after += self._swap(self._card(head, lines))
        anims.append(AnimationGroup(*after))
        return [Succession(*anims)]

    def _redot(self, genotypes: list[int], pulse: bool) -> list[Animation]:
        anims: list[Animation] = []
        for k, d in enumerate(self.dots):
            visible = k < len(genotypes)
            g = genotypes[k] if visible else 0
            a, b = self._colors(g)
            o = 1.0 if visible else 0.0
            anims.append(d[0].animate.set_fill(a, opacity=o))
            anims.append(d[1].animate.set_fill(b, opacity=o))
            anims.append(d[2].animate.set_stroke(opacity=0.6 if visible else 0.0))
        legend = self._legend(genotypes, self.dot_scale)
        old = self.legend_mob.copy()
        self.legend_mob.become(legend)
        anims += [FadeOut(old), FadeIn(self.legend_mob)]
        if pulse:
            return [Succession(AnimationGroup(*[d.animate.scale(0.6) for d in self.dots], run_time=0.4),
                               AnimationGroup(*[d.animate.scale(1 / 0.6) for d in self.dots], *anims))]
        return [AnimationGroup(*anims)]

    def resample(self) -> list[Animation]:
        """A new generation: the next generation of the first line, or a new random sample of a
        Hardy–Weinberg population."""
        if self.plan.hw is not None:
            hw = self.plan.hw
            self.resamples += 1
            gen = pg.sample_genotypes(tuple(float(x) for x in hw.expected), len(self.dots), self.plan.seed * 31 + self.resamples)
            self.dot_scale = " · a random sample"
            anims = self._redot(gen, True)
            pre = [FadeIn(self.dot_group), FadeIn(self.legend_mob)] if not self.is_shown("population") else []
            return [Succession(*pre, *anims)] if pre else anims
        return self.advance_to(self.gen_now + 1, pulse=True)
