"""``pedigree``: a family chart in standard human pedigree nomenclature (DESIGN.md §96.8; NSGC
recommendations, Bennett et al. 2008) with its genetic analysis. Generations are rows (Roman
numerals at the left, individuals numbered left to right: II-3), sibships in birth order under
their parents' mating line, partners from outside beside the relative; the symbols, marks and
lines are drawn in ``scenes/pedigree_draw.py``. The analysis is computed by ``vidgen.genetics.pedigree_plan``:
which modes of inheritance fit (each excluded one with its reason), the genotypes the chart
forces (obligate carriers), carrier probabilities and the risk for a proposed child. Actions
(``scenes/pedigree_actions.py``): ``deduce`` (genotypes), ``analyse`` (the modes one by one),
``risk``; the built-in ``reveal`` brings in generations or people, ``highlight`` marks them."""

from fractions import Fraction
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import small_size, text_block
from .pedigree_draw import arrow, carrier_mark, mating_line, symbol, tick

pp = genetics.pedigree_plan
pa = genetics.pedigree_analysis

#: The pedigree scene's own actions (any of them puts the scene in manual mode).
PEDIGREE_ACTIONS = ("deduce", "analyse", "risk")
#: Seconds: genotypes appearing; one mode tried; the risk card.
DEDUCE_SECONDS, MODE_SECONDS, RISK_SECONDS = 1.4, 1.0, 2.2
#: Symbol size and the length of a child's line, as shares of the pitch (one symbol and its gap).
SYMBOL, DROP = 0.5, 0.36
MODE_NAMES = {"AD": "autosomal dominant", "AR": "autosomal recessive", "XD": "X-linked dominant", "XR": "X-linked recessive",
              "YL": "Y-linked", "MT": "mitochondrial"}


def fraction_text(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def percent_text(f: Fraction) -> str:
    """Two significant digits for small shares (0.67 %), else one decimal (16.7 %); exact when it is."""
    v = float(f) * 100
    for places in (0, 1, 2):
        if (f * 100 * 10 ** places).denominator == 1:
            return f"{v:.{places}f} %"
    if v < 1:
        return f"≈ {v:.2g} %"
    return f"≈ {v:.1f} %"


@scene("pedigree")
class PedigreeScene(NarratedScene):
    """A family chart in NSGC notation (squares, circles, diamonds; affected filled, carriers
    dotted, deceased struck, proband arrowed, consanguinity double lines, twins, adoption) laid
    out by generation, with its genetic analysis: which modes of inheritance fit and why the
    others are excluded, the genotypes the chart forces, carrier probabilities and the risk for a
    proposed child, all computed exactly. Without pedigree actions it plays itself generation by
    generation (then the analysis, genotypes and risk when asked); the actions deduce, analyse
    and risk put each step on a word, reveal brings in generations or people.

    Action targets: ``title``, ``chart``, ``legend``, ``generation:<I, II…>``, ``person:<id>``
    (also ``person:<II-3>``), ``proband``, ``consultand``, ``affected``, ``carriers``, ``child``,
    ``genotypes``, ``modes`` (``analysis``), ``mode:<AD…>``, ``risk``."""

    outro = 0.5
    target_patterns = ("title", "chart", "legend", "generation:<R>", "person:<id>", "proband", "consultand", "affected", "carriers",
                       "child", "genotypes", "modes", "analysis", "mode:<code>", "risk")
    #: The actions deduce, analyse and risk act on this scene type.
    pedigree_actions = True
    mid_still_actions = frozenset(PEDIGREE_ACTIONS)

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        individuals: list[dict[str, Any] | str]
        """The people: {id, sex (female, male, unknown), affected, carrier, deceased, proband, consultand, adopted (in, out), loss (miscarriage, stillbirth), proposed, parents: [I-1, I-2], spouse, twin: {with, kind: MZ | DZ}, age, label}, or a line "II-3: female affected of I-1 + I-2"."""
        couples: list[dict[str, Any] | str] | None = None
        """Couples without children, or with marks: [{partners: [II-1, II-2], consanguineous: true, separated: true}] (shared ancestors are found by themselves)."""
        condition: TranslatableStr = ""
        """The condition's name (the legend's 'affected')."""
        mode: str | None = None
        """The mode of inheritance for genotypes and risk (AD, AR, XD, XR, YL, MT or their names); default: the only one that fits."""
        analyse: bool | list[str] = False
        """Show the analysis of the modes (true: all six; or a list: [AD, AR, XR])."""
        genotypes: bool = False
        """Show the deduced genotypes (and carrier probabilities) when the scene plays itself."""
        penetrance: float | str | None = None
        """P(affected | disease genotype), e.g. 0.8 (reduced penetrance); default 1."""
        rare: bool = True
        """The allele is rare: people marrying into the family do not carry it (unless the chart shows it)."""
        carrier_frequency: float | str | None = None
        """An unaffected person's chance of carrying a recessive allele (1/25 for cystic fibrosis): for people marrying in."""
        alleles: list[str] | None = None
        """Allele symbols, dominant first ([A, a], [H, h])."""
        preset: str | None = None
        """A one-locus preset for the alleles and mode (hemophilia_a, drosophila_white…)."""
        loci: list[dict[str, Any]] | None = None
        """One locus ({gene, trait, alleles, chromosome}) for the alleles and mode."""
        carrier_style: Literal["dot", "half"] = "dot"
        """dot: a dot in the centre (NSGC carrier); half: the half-shaded heterozygote of many textbooks."""
        numbers: bool = True
        """Number the individuals under their symbols (Roman generation numerals at the left)."""
        legend: bool = True
        """A legend of the marks used."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def spec(self) -> dict[str, Any]:
            data: dict[str, Any] = {k: getattr(self, k) for k in ("individuals", "couples", "mode", "penetrance", "rare",
                                                                    "carrier_frequency", "alleles", "preset", "loci")
                                    if getattr(self, k) is not None}
            data["condition"] = str(self.condition)
            if isinstance(self.analyse, list):
                data["analyse"] = self.analyse
            return data

        def plan(self) -> Any:
            return pp.plan_pedigree(self.spec())

        @model_validator(mode="after")
        def _check(self) -> "PedigreeScene.Params":
            try:
                plan = self.plan()
                if self.genotypes and plan.mode is None:
                    raise VidgenError(self.no_mode_message(plan, "genotypes: true"))
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

        def no_mode_message(self, plan: Any, what: str) -> str:
            if plan.declared is not None:
                return f"{what}: the chart does not fit the stated mode {plan.declared}: {pp.declared_mode_problem(plan)}"
            fits = ", ".join(plan.fitting) or "none"
            return f"{what} needs one mode: the chart fits {fits} — say which with mode: (e.g. mode: {plan.fitting[0] if plan.fitting else 'AR'})"

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        plan = params.plan()
        ped = plan.ped
        names = ["title"] if params.title else []
        names += ["chart"] + (["legend"] if params.legend else [])
        names += [f"generation:{genetics.pedigree.roman(g + 1)}" for g in range(ped.rows)]
        for pid in ped.people:
            names.append(f"person:{pid}")
            if ped.label(pid) != pid and ped.label(pid) != "?":
                names.append(f"person:{ped.label(pid)}")
        names += [n for n, flag in (("proband", "proband"), ("consultand", "consultand")) if any(getattr(p, flag) for p in ped.people.values())]
        names += ["affected"] if any(p.affected for p in ped.people.values()) else []
        names += ["carriers"]
        names += ["child"] if ped.proposed else []
        if plan.mode is not None:
            names += ["genotypes", "all"]
        names += ["modes", "analysis"] + [f"mode:{m}" for m in plan.modes_tried]
        if ped.proposed and plan.mode is not None:
            names += ["risk"]
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        if name.startswith("person:"):
            return params.plan().ped.label(name[7:])
        if name.startswith("mode:"):
            return MODE_NAMES.get(name[5:])
        return None

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.plan = p.plan()
        self.ped = self.plan.ped
        self.bg = th.background
        self.ink = th.color("text")
        self.dim_ink = th.color("dim")
        self.hi = th.color("highlight")
        self.bad = th.color("accent")
        self.good = th.color("tertiary")
        self.small = small_size(self, p.size)
        self.manual = any(self.action_uses(n) for n in PEDIGREE_ACTIONS)
        held = set()
        for use in self.action_uses("reveal"):
            held.update(use.config.targets())
        self.held_names = held
        self.manual = self.manual or any(n.startswith(("generation:", "person:", "proband", "consultand", "child", "chart")) for n in held)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.25)
        self.title_mob = title
        self.inference = self.plan.inference
        named = {t for n in ("reveal", "highlight", "dim", "callout", "hide", "zoom") for u in self.action_uses(n) for t in u.config.targets()}
        uses_analysis = bool(p.analyse) or bool(self.action_uses("analyse")) or any(t.startswith(("mode", "analysis")) for t in named)
        uses_risk = self.ped.proposed is not None and self.inference is not None and self.inference.risk is not None
        self.has_panel = uses_analysis or uses_risk
        self.show_genotype_line = self.plan.mode is not None and (p.genotypes or bool(self.action_uses("deduce")) or uses_risk
                                                                  or any(t in ("genotypes", "all", "carriers") for t in named))
        self._regions(body)
        self._build_chart()
        self._build_legend()
        self.card_mobs: dict[str, VGroup] = {}
        self.cards_on: list[str] = []
        self._build_analysis()            # registered always (its target can be named); placed in the panel when used
        if uses_risk:
            self._build_risk()
        self._register()

    # ----- regions and scale ----------------------------------------------------------------------

    def _line_h(self) -> float:
        return self._lh

    def _regions(self, body: Any) -> None:
        p = self.params
        ped = self.ped
        lay = self.plan.layout
        self.label_size = max(readable_size() * 1.02, self.small * 0.85)
        self._lh = self.markup("Ag2", size=self.label_size).height * 1.25
        people = list(ped.people.values())
        extra = max((bool(x.age) + bool(x.label) + (x.loss == "stillbirth") for x in people), default=0)
        self.text_lines = int(self.show_genotype_line) + extra
        legend_h = self.markup("Ag", size=self.small * 0.85).height * 2.0 if p.legend else 0.0
        if not self.has_panel:
            chart = body
            self.panel = None
        elif not self.is_portrait:
            split = body.x0 + body.width * 0.6
            chart = Region(body.x0, body.y0, split, body.y1)
            self.panel = Region(split + 0.4, body.y0, body.x1, body.y1)
        else:
            chart = body
            self.panel = None
        self.roman_w = self.markup("<b>III</b>", size=self.small).width + 0.25
        rows = ped.rows
        lh = self._lh
        top_room = lh if p.numbers else 0.0
        widest = 0.0
        if self.show_genotype_line and self.inference is not None:
            widest = max((self.markup(" ".join(x for x in self._genotype_text(pid)[:2] if x), size=self.label_size).width
                          for pid in ped.people if not ped.people[pid].proposed), default=0.0)
        self.stacked = False

        def lines() -> int:
            return self.text_lines + int(self.stacked)

        def text_h() -> float:
            return lines() * lh + (0.06 if lines() else 0.0)

        def drop(P: float) -> float:          # the child's line: room for the number beside it
            return max(DROP * P, top_room * 1.1)

        def step(P: float) -> float:
            return SYMBOL * P + text_h() + 0.1 + drop(P)

        def height(P: float) -> float:
            arrow_room = P * 0.3 if any(x.proband or x.consultand for x in people) else 0.0
            return top_room + (rows - 1) * step(P) + SYMBOL * P + max(text_h(), arrow_room)

        avail_h = chart.height - legend_h
        cap = 1.5 if not self.is_portrait else 1.9
        def fit() -> float:
            P = min(cap, (chart.width - self.roman_w - 0.1) / max(lay.width, 1.0))
            while P > 0.25 and height(P) > avail_h * (0.56 if self.is_portrait and self.has_panel else 1.0):
                P *= 0.97
            return P

        P = fit()
        if widest > 0.9 * P:                  # "2/3 Aa" wider than the pitch: on two lines, when that costs little height
            self.stacked = True
            stacked = fit()
            if stacked < 0.92 * P:
                self.stacked = False
            else:
                P = stacked
        T = text_h()
        self.P = P
        self.s = SYMBOL * P
        self.T = T
        self.drop = drop(P)
        H = height(P)
        if self.is_portrait and self.has_panel:
            top = chart.y1
            self.chart = Region(chart.x0, top - H - legend_h - 0.1, chart.x1, top)
            self.panel = Region(body.x0, body.y0, body.x1, self.chart.y0 - 0.35)
        else:
            self.chart = chart
        width = self.roman_w + lay.width * P
        self.x_left = self.chart.center[0] - width / 2 + self.roman_w
        free = self.chart.height - legend_h - H
        self.y_top = self.chart.y1 - max(0.0, free) * 0.4 - top_room - self.s / 2
        self.row_step = step(P)
        self.legend_y = self.chart.y0 + legend_h / 2

    def xy(self, pid: str) -> np.ndarray:
        lay = self.plan.layout
        return np.array([self.x_left + lay.x[pid] * self.P, self.y_top - lay.row[pid] * self.row_step, 0.0])

    # ----- the chart ---------------------------------------------------------------------------------

    def _build_chart(self) -> None:
        p = self.params
        ped = self.ped
        s = self.s
        self.stroke = max(2.0, min(4.0, s * 6))
        fill = self.ink
        self.person_mobs: dict[str, VGroup] = {}
        self.shapes: dict[str, Mobject] = {}
        self.arrows: dict[str, VGroup] = {}
        self.genotype_mobs: dict[str, Mobject] = {}
        self.deduced_marks: dict[str, Mobject] = {}
        self.genotype_slot: dict[str, np.ndarray] = {}
        width = self.P * 0.92
        for pid, person in ped.people.items():
            c = self.xy(pid)
            sym = symbol(self, person, s, self.ink, self.bg, fill, p.carrier_style, self.stroke).move_to(c)
            self.shapes[pid] = sym[0]
            parts: list[Mobject] = [sym]
            if person.proband or person.consultand:
                a = arrow(self, s, self.ink, "P" if person.proband else "", self.stroke, self.label_size)
                a.shift(c)
                self.arrows[pid] = a
                parts.append(a)
            lines = []
            if p.numbers and not person.proposed:
                num = self.markup(ped.label(pid).split("-")[-1], size=self.label_size, color=self.dim_ink)
                top = c[1] + self._half_height(pid)
                twin = ped.people.get(person.twin) if person.twin else None
                side = 1 if twin is not None and self.plan.layout.x[twin.id] < self.plan.layout.x[pid] else -1   # away from the twin line
                num.move_to(np.array([c[0] + side * (self._half_width(pid) * 0.55 + num.width / 2 + 0.03), top + num.height / 2 + 0.04, 0.0]))
                parts.append(num)
            if self.show_genotype_line:
                lines.append(None)                    # the genotype's slot
                if self.stacked:
                    lines.append(None)
            if person.loss == "stillbirth":
                lines.append(self.markup("SB", size=self.label_size, color=self.ink))
            for text in (person.age, person.label):
                if text:
                    lines.append(self.markup(text, size=self.label_size, color=self.ink))
            y = c[1] - s / 2 - 0.04 - (0.08 if person.adopted else 0.0) - (s * 0.18 if person.deceased else 0.0)
            gslot = None
            for m in lines:
                if m is None:
                    if gslot is None:
                        gslot = y            # the top of the genotype's slot
                    y -= self._line_h()
                    continue
                if m.width > width:
                    m.scale(width / m.width)
                m.move_to(np.array([c[0], y - self._line_h() / 2, 0.0]))
                parts.append(m)
                y -= self._line_h()
            self.person_mobs[pid] = VGroup(*parts)
            if gslot is not None:
                self.genotype_slot[pid] = np.array([c[0], gslot, 0.0])
        self._build_lines()
        self.romans: list[Mobject] = []
        for g in range(ped.rows):
            t = self.markup(f"<b>{genetics.pedigree.roman(g + 1)}</b>", size=self.small, color=self.ink)
            t.move_to(np.array([self.x_left - self.roman_w / 2 - 0.15, self.y_top - g * self.row_step, 0.0]))
            self.romans.append(t)
        if self.inference is not None:
            self._build_genotypes()

    def _build_lines(self) -> None:
        ped = self.ped
        s = self.s
        ink = self.ink
        st = self.stroke * 0.8
        self.mating: dict[frozenset[str], VGroup] = {}
        self.descent: dict[frozenset[str], Mobject] = {}
        self.child_line: dict[str, VGroup] = {}
        self.twin_bars: dict[frozenset[str], Mobject] = {}
        for c in ped.couples:
            a, b = sorted(c.partners, key=lambda x: self.xy(x)[0])
            pa_, pb = self.xy(a), self.xy(b)
            left = pa_ + np.array([self._half_width(a), 0, 0])
            right = pb - np.array([self._half_width(b), 0, 0])
            self.mating[frozenset(c.partners)] = mating_line(left, right, ink, st, c.consanguineous, c.separated, s)
            kids = [k for k in c.children]
            if not kids:
                continue
            mid = (pa_ + pb) / 2
            kid_top = self.xy(kids[0])[1] + s / 2
            sib_y = kid_top + self.drop
            self.descent[frozenset(c.partners)] = Line(mid, np.array([mid[0], sib_y, 0])).set_stroke(ink, width=st)
            done: set[str] = set()
            for k in kids:
                if k in done:
                    continue
                person = ped.people[k]
                twin = person.twin if person.twin in kids else None
                group = [k] + ([twin] if twin else [])
                done.update(group)
                xs = [self.xy(x)[0] for x in group]
                apex_x = sum(xs) / len(xs)
                horiz = Line(np.array([mid[0], sib_y, 0]), np.array([apex_x, sib_y, 0]))
                verts: list[Mobject] = []
                for x in group:
                    top = self.xy(x) + np.array([0, self._half_height(x), 0])
                    start = np.array([apex_x, sib_y, 0])
                    seg = Line(start, top)
                    if ped.people[x].adopted == "in":
                        seg = DashedLine(start, top, dash_length=s * 0.12)
                    verts.append(seg)
                pieces = VGroup(horiz, *verts).set_stroke(ink, width=st)
                for x in group:
                    self.child_line[x] = pieces
                if twin:
                    key = frozenset(group)
                    y = sib_y - (sib_y - (self.xy(k)[1] + s / 2)) * 0.5
                    t = 0.5
                    pa0 = np.array([apex_x + (xs[0] - apex_x) * t, y, 0])
                    pb0 = np.array([apex_x + (xs[1] - apex_x) * t, y, 0])
                    if person.zygosity == "MZ":
                        self.twin_bars[key] = Line(pa0, pb0).set_stroke(ink, width=st)
                    elif person.zygosity == "unknown":
                        q = self.markup("?", size=self.label_size, color=ink)
                        q.move_to(np.array([apex_x, y - q.height * 0.2, 0]))
                        self.twin_bars[key] = q

    def _half_width(self, pid: str) -> float:
        person = self.ped.people[pid]
        if person.loss == "miscarriage":
            return self.s * 0.33
        return self.s * (0.62 if person.sex == "unknown" else 0.5)

    def _half_height(self, pid: str) -> float:
        person = self.ped.people[pid]
        if person.loss == "miscarriage":
            return self.s * 0.275
        return self.s * (0.62 if person.sex == "unknown" else 0.5)

    def _genotype_text(self, pid: str) -> tuple[str, str, Any]:
        """The genotype under a person — (probability, genotype markup, colour): the forced
        genotype, or the most telling one with its exact probability (2/3, Aa); obligate carriers
        in the highlight colour."""
        inf = self.inference
        assert inf is not None
        mode = inf.mode
        alleles = self.plan.alleles
        dist = inf.posterior[pid]
        person = self.ped.people[pid]
        if len(dist) == 1:
            return "", pa.genotype_markup(mode, next(iter(dist)), alleles), (self.hi if pid in inf.obligate else self.ink)
        if person.affected:
            best = max(dist.items(), key=lambda kv: kv[1])
            return fraction_text(best[1]), pa.genotype_markup(mode, best[0], alleles), self.ink
        p, s = max(((p, s) for s, p in dist.items() if s[1] >= 1), key=lambda ps: (ps[0], -ps[1][1]))
        return fraction_text(p), pa.genotype_markup(mode, s, alleles), self.ink

    def _build_genotypes(self) -> None:
        inf = self.inference
        width = self.P * 0.9
        lh = self._line_h()
        for pid, person in self.ped.people.items():
            if person.proposed:
                continue
            prob, geno, color = self._genotype_text(pid)
            top = self.genotype_slot.get(pid, self.xy(pid) - np.array([0, self._half_height(pid) + 0.04, 0]))
            if self.stacked and prob:
                m = VGroup(self.markup(prob, size=self.label_size, color=color), self.markup(geno, size=self.label_size, color=color))
                m.arrange(DOWN, buff=lh * 0.2)
                for part in m:
                    if part.width > width:
                        part.scale(width / part.width)
                m.move_to(top - np.array([0, m.height / 2 + lh * 0.1, 0]))
            else:
                m = self.markup(f"{prob} {geno}" if prob else geno, size=self.label_size, color=color)
                if m.width > width:
                    m.scale(width / m.width)
                m.move_to(top - np.array([0, lh / 2, 0]))
            self.genotype_mobs[pid] = m
            if pid in inf.obligate:
                self.deduced_marks[pid] = carrier_mark(person.sex, self.s, self.ink, self.params.carrier_style).shift(self.xy(pid))

    # ----- legend ------------------------------------------------------------------------------------

    def _build_legend(self) -> None:
        self.legend_mob = None
        if not self.params.legend:
            return
        ped = self.ped
        s = self.small / 48 * 0.55
        items: list[Mobject] = []
        people = list(ped.people.values())
        cond = str(self.params.condition) or self.plan.condition or "affected"

        def entry(mark: Mobject, text: str) -> VGroup:
            return VGroup(mark, self.markup(text, size=self.small * 0.85, color=self.dim_ink)).arrange(RIGHT, buff=0.1)

        sq = Square(side_length=s).set_stroke(self.ink, width=2).set_fill(self.ink, opacity=1)
        items.append(entry(sq, cond if cond != "affected" else "affected"))
        obligate = self.inference is not None and bool(self.inference.obligate) and self.show_genotype_line
        if any(p.carrier for p in people) or obligate:
            c = Circle(radius=s / 2).set_stroke(self.ink, width=2).set_fill(self.bg, opacity=1)
            mark = carrier_mark("female", s, self.ink, self.params.carrier_style).shift(c.get_center())
            items.append(entry(VGroup(c, mark), "carrier"))
        if any(p.deceased for p in people):
            sq2 = Square(side_length=s).set_stroke(self.ink, width=2).set_fill(self.bg, opacity=1)
            sl = Line(np.array([-s * 0.75, -s * 0.75, 0]), np.array([s * 0.75, s * 0.75, 0])).set_stroke(self.ink, width=2)
            items.append(entry(VGroup(sq2, sl), "deceased"))
        if any(p.proband for p in people):
            items.append(entry(arrow(self, s * 1.2, self.ink, "", 2.5), "proband"))
        legend = VGroup(*items).arrange(RIGHT, buff=0.35)
        room = self.chart.width
        if legend.width > room:
            legend.scale(room / legend.width)
        legend.move_to(np.array([self.chart.center[0], self.legend_y, 0.0]))
        self.legend_mob = legend

    # ----- the analysis and risk cards ---------------------------------------------------------------

    def _panel_width(self) -> float:
        return self.panel.width if self.panel is not None else 4.0

    def _build_analysis(self) -> None:
        width = self._panel_width()
        size = self.small
        head = self.markup("<b>Mode of inheritance</b>", size=size * 1.1, color=self.ink)
        self.mode_rows: dict[str, VGroup] = {}
        self.mode_people: dict[str, tuple[str, ...]] = {}
        rows: list[VGroup] = []
        for v in self.plan.verdicts:
            color = self.good if v.consistent else self.bad
            mark = tick(size / 48 * 0.42, color, v.consistent)
            name = self.markup(f"<b>{v.mode}</b>  {MODE_NAMES[v.mode]}", size=size, color=self.ink)
            line = VGroup(mark, name).arrange(RIGHT, buff=0.15)
            parts: list[Mobject] = [line]
            note = v.reason if (not v.consistent or v.reason != "fits") else ""
            if note:
                block = text_block(self, note.replace("&", "&amp;").replace("<", "&lt;"), width - 0.35, size * 0.95, color=self.dim_ink)
                parts.append(block)
            row = VGroup(*parts).arrange(DOWN, buff=0.05, aligned_edge=LEFT)
            if len(parts) > 1:
                parts[1].shift(RIGHT * 0.35)
            if row.width > width:
                row.scale(width / row.width, about_edge=LEFT)
            self.mode_rows[v.mode] = row
            self.mode_people[v.mode] = v.people
            rows.append(row)
        fits = [v.mode for v in self.plan.verdicts if v.consistent]
        summary = "fits: " + (", ".join(fits) if fits else "none of these")
        concl = self.markup(f"<b>{summary}</b>", size=size * 1.05, color=self.hi)
        card = VGroup(head, *rows, concl).arrange(DOWN, buff=0.14, aligned_edge=LEFT)
        room = self.panel.height if self.panel is not None else 6.0
        self.compact = card.height > room
        self.reason_on: Mobject | None = None
        if self.compact:
            card = self._compact_analysis(head, concl, width, size)
        if card.height > room:
            card.scale(room / card.height, about_edge=UP)
        self.analysis_head, self.analysis_concl = head, concl
        self.card_mobs["modes"] = card
        self.analysed: set[str] = set()

    def _compact_analysis(self, head: Mobject, concl: Mobject, width: float, size: float) -> VGroup:
        """When the full list does not fit (9:16): a strip of the modes with their marks, and
        one reason at a time under it (each mode's replaces the one before)."""
        chips: list[VGroup] = []
        self.mode_reasons: dict[str, Mobject] = {}
        for v in self.plan.verdicts:
            color = self.good if v.consistent else self.bad
            chips.append(VGroup(tick(size / 48 * 0.42, color, v.consistent), self.markup(f"<b>{v.mode}</b>", size=size * 1.05, color=self.ink))
                         .arrange(RIGHT, buff=0.1))
        strip = VGroup(*chips).arrange(RIGHT, buff=0.45)
        if strip.width > width:
            strip = VGroup(*chips).arrange_in_grid(cols=3, buff=(0.45, 0.15), cell_alignment=LEFT)
        for v in self.plan.verdicts:
            note = v.reason if (not v.consistent or v.reason != "fits") else "fits the chart"
            text = f"<b>{v.mode}</b> ({MODE_NAMES[v.mode]}): " + note.replace("&", "&amp;").replace("<", "&lt;")
            self.mode_reasons[v.mode] = text_block(self, text, width, size * 0.95, color=self.ink if not v.consistent else self.good)
        tallest = max(m.height for m in self.mode_reasons.values())
        top = VGroup(head, strip).arrange(DOWN, buff=0.2, aligned_edge=LEFT)
        slot_top = top.get_bottom()[1] - 0.25
        for m in self.mode_reasons.values():
            m.move_to(np.array([top.get_left()[0] + m.width / 2, slot_top - m.height / 2, 0.0]))
        concl.move_to(np.array([top.get_left()[0] + concl.width / 2, slot_top - tallest - 0.25 - concl.height / 2, 0.0]))
        for v, chip in zip(self.plan.verdicts, chips):
            self.mode_rows[v.mode] = VGroup(chip, self.mode_reasons[v.mode])
        return VGroup(top, *self.mode_reasons.values(), concl)

    def _build_risk(self) -> None:
        inf = self.inference
        risk = inf.risk
        ped = self.ped
        width = self._panel_width()
        size = self.small
        mode = inf.mode
        lab = ped.label
        alleles = self.plan.alleles
        het = {"AR": ("", 1), "AD": ("", 1), "XR": ("f", 1), "XD": ("f", 1)}.get(mode)
        head = self.markup(f"<b>Risk for the child of {lab(risk.father)} and {lab(risk.mother)}</b>", size=size * 1.05, color=self.ink)
        lines: list[Mobject] = [head]
        nums: list[str] = []
        for kind, who, f in risk.factors:
            if kind == "carrier" and het is not None:
                g = pa.genotype_markup(mode, het, alleles)
                text = f"P({lab(who)} is {g}) = {fraction_text(f)}"
            elif kind == "transmit" and who == "both":
                text = f"both pass {genetics.symbol_markup(alleles[1])}: 1/4"
            elif kind == "transmit":
                text = f"{lab(who)} passes it on: {fraction_text(f)}"
            elif kind == "sex":
                text = f"a son: {fraction_text(f)}"
            else:
                text = f"penetrance: {fraction_text(f)}"
            lines.append(self.markup(text, size=size, color=self.ink))
            nums.append(fraction_text(f))
        if nums:
            lines.append(self.markup(f"risk = {' × '.join(nums)}", size=size, color=self.ink))
        lines.append(self.markup(f"<b>{'= ' if nums else 'risk = '}{fraction_text(risk.affected)}</b>  ({percent_text(risk.affected)})",
                                 size=size * 1.15, color=self.hi))
        if risk.by_sex and ped.people[risk.child].sex == "unknown":
            parts = ", ".join(f"a {k}: {fraction_text(v)}" for k, v in risk.by_sex.items())
            lines.append(self.markup(parts, size=size * 0.9, color=self.dim_ink))
        if not nums:
            lines.append(self.markup("from the whole chart (Bayes)", size=size * 0.85, color=self.dim_ink))
        if self.plan.opts.carrier_frequency is None and any(k == "carrier" and f == 0 for k, _, f in risk.factors):
            lines.append(text_block(self, "people from outside the family are assumed not to carry the rare allele: "
                                    "give carrier_frequency for a common one", width, size * 0.8, color=self.dim_ink))
        for m in lines:
            if m.width > width:
                m.scale(width / m.width)
        card = VGroup(*lines).arrange(DOWN, buff=0.14, aligned_edge=LEFT)
        self.card_mobs["risk"] = card
        self.risk_lines = lines
        child = risk.child
        label = self.markup(f"<b>{fraction_text(risk.affected)}</b>", size=self.label_size * 1.05, color=self.hi)
        slot = self.genotype_slot.get(child)
        slot = (slot if slot is not None else self.xy(child) - np.array([0, self.s * 0.62 + 0.04, 0])) - np.array([0, self._line_h() / 2, 0])
        if label.width > self.P * 0.96:
            label.scale(self.P * 0.96 / label.width)
        label.move_to(slot)
        self.risk_label = label
        self.risk_shown = False

    # ----- targets and the reveal -----------------------------------------------------------------

    def _register(self) -> None:
        p = self.params
        ped = self.ped
        title = self.title_mob
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        self.visible: set[str] = set()
        self.lines_on: set[int] = set()
        self.romans_on: set[int] = set()
        every = list(ped.people)
        chart = VGroup(*self.romans, *self.person_mobs.values(), *self.mating.values(), *self.descent.values(),
                       *{id(v): v for v in self.child_line.values()}.values(), *self.twin_bars.values())
        self.target("chart", chart, entrance=lambda: self.run_reveal(every))
        if self.legend_mob is not None:
            self.target("legend", self.legend_mob)
        for g in range(ped.rows):
            ids = [x for x in ped.people if ped.generation[x] == g]
            self.target(f"generation:{genetics.pedigree.roman(g + 1)}", VGroup(self.romans[g], *[self.person_mobs[x] for x in ids]),
                        entrance=lambda ids=ids: self.run_reveal(ids))
        for pid in ped.people:
            names = [f"person:{pid}"]
            if ped.label(pid) not in (pid, "?"):
                names.append(f"person:{ped.label(pid)}")
            if ped.people[pid].proposed:
                names.append("child")
            self.target(names, self.person_mobs[pid], outline=self.shapes[pid], entrance=lambda pid=pid: self.run_reveal([pid]))
        for pid, a in self.arrows.items():
            name = "proband" if ped.people[pid].proband else "consultand"
            self.target(name, a, entrance=lambda pid=pid: self.run_reveal([pid]))
        affected = [x for x in ped.people if ped.people[x].affected]
        if affected:
            self.target("affected", VGroup(*[self.person_mobs[x] for x in affected]), entrance=lambda: self.run_reveal(affected))
        obligate = list(self.inference.obligate) if self.inference is not None else []
        carriers = [x for x in ped.people if ped.people[x].carrier or x in obligate]
        self.target("carriers", VGroup(*[self.person_mobs[x] for x in carriers], *[self.deduced_marks[x] for x in carriers if x in self.deduced_marks]),
                    entrance=lambda: self.run_deduce(carriers))
        if self.genotype_mobs:
            self.target(("genotypes", "all"), VGroup(*self.genotype_mobs.values(), *self.deduced_marks.values()),
                        entrance=lambda: self.run_deduce(list(ped.people)))
        if "modes" in self.card_mobs:
            self.target(("modes", "analysis"), self.card_mobs["modes"], entrance=lambda: self.run_analyse(list(self.mode_rows)))
            for code, row in self.mode_rows.items():
                self.target(f"mode:{code}", row, entrance=lambda code=code: self.run_analyse([code]))
        if "risk" in self.card_mobs:
            self.target("risk", VGroup(self.card_mobs["risk"], self.risk_label), entrance=lambda: self.run_risk())
        # what is held back for actions: people named by reveal actions, the proposed child for risk
        held: list[str] = []
        for name in self.held_names:
            for t in self.find_targets(name):
                family = {id(m) for m in t.mobject.get_family()}
                held += [x for x in ped.people if id(self.person_mobs[x]) in family or id(self.arrows.get(x)) in family]
        if self.action_uses("risk") and ped.proposed:
            held.append(ped.proposed)
        start = [x for x in ped.people if x not in held]

        def first() -> list[Animation]:
            anims: list[Animation] = [FadeIn(title)] if title is not None else []
            if self.legend_mob is not None:
                anims.append(FadeIn(self.legend_mob))
            if self.manual:
                anims += self.run_reveal(start)
            else:
                anims += self.run_reveal([x for x in start if ped.generation[x] == 0])
            return anims

        steps: list[Any] = [first]
        if not self.manual:
            for g in range(1, ped.rows):
                ids = [x for x in ped.people if ped.generation[x] == g and not (ped.people[x].proposed and "risk" in self.card_mobs)]
                steps.append(lambda ids=ids: self.run_reveal(ids))
            if p.analyse:
                steps.append(lambda: self.run_analyse(list(self.mode_rows)))
            if p.genotypes and self.genotype_mobs:
                steps.append(lambda: self.run_deduce(list(ped.people)))
            if "risk" in self.card_mobs:
                steps.append(lambda: self.run_risk())
        self.reveal(steps, fraction=0.85, cap=3.0)
        self.finish()

    # ----- what the actions play ------------------------------------------------------------------

    def run_reveal(self, ids: list[str]) -> list[Animation]:
        """People appear with their Roman numeral and every line that is complete now."""
        new = [x for x in ids if x not in self.visible]
        if not new:
            return []
        self.visible.update(new)
        anims: list[Animation] = []
        for g in sorted({self.ped.generation[x] for x in new}):
            if g not in self.romans_on:
                self.romans_on.add(g)
                anims.append(FadeIn(self.romans[g]))
        anims += [FadeIn(self.person_mobs[x], scale=0.9) for x in new]
        lines: list[Mobject] = []
        for c in self.ped.couples:
            key = frozenset(c.partners)
            if c.a in self.visible and c.b in self.visible:
                m = self.mating[key]
                if id(m) not in self.lines_on:
                    self.lines_on.add(id(m))
                    lines.append(m)
                kids = [k for k in c.children if k in self.visible]
                if kids and key in self.descent and id(self.descent[key]) not in self.lines_on:
                    self.lines_on.add(id(self.descent[key]))
                    lines.append(self.descent[key])
                for k in kids:
                    seg = self.child_line.get(k)
                    if seg is not None and id(seg) not in self.lines_on:
                        self.lines_on.add(id(seg))
                        lines.append(seg)
        for key, bar in self.twin_bars.items():
            if key <= self.visible and id(bar) not in self.lines_on:
                self.lines_on.add(id(bar))
                lines.append(bar)
        anims += [Create(m) for m in lines]
        return [AnimationGroup(*anims)]

    def deduce_seconds(self) -> float:
        return DEDUCE_SECONDS

    def run_deduce(self, ids: list[str]) -> list[Animation]:
        """The genotypes of ``ids`` appear under their symbols (people not shown yet appear
        first); obligate carriers get their carrier mark."""
        anims: list[Animation] = list(self.run_reveal([x for x in ids if not self.ped.people[x].proposed]))
        shown = getattr(self, "deduced", set())
        self.deduced = shown
        todo = [x for x in ids if x in self.genotype_mobs and x not in shown]
        shown.update(todo)
        parts = [FadeIn(self.genotype_mobs[x], shift=UP * 0.05) for x in todo]
        parts += [FadeIn(self.deduced_marks[x], scale=0.5) for x in todo if x in self.deduced_marks]
        if parts:
            anims.append(LaggedStart(*parts, lag_ratio=0.08))
        return [Succession(*anims)] if len(anims) > 1 else anims

    def analyse_seconds(self, codes: list[str]) -> float:
        return MODE_SECONDS * max(1, len([c for c in codes if c not in getattr(self, "analysed", set())])) + 0.4

    def run_analyse(self, codes: list[str]) -> list[Animation]:
        """Each mode in turn: its row (fits, or excluded with the reason) while the people the
        reason names are ringed; after the last one, which modes fit."""
        if "modes" not in self.card_mobs:
            return []
        anims: list[Animation] = list(self._place_card("modes"))
        if not self.analysed:
            anims.append(FadeIn(self.analysis_head))
        for code in codes:
            if code in self.analysed or code not in self.mode_rows:
                continue
            self.analysed.add(code)
            row = self.mode_rows[code]
            rings = []
            for pid in self.mode_people.get(code, ()):
                if pid in self.visible:
                    r = Circle(radius=self.s * 0.85).move_to(self.shapes[pid].get_center()).set_stroke(self.hi, width=4)
                    rings.append(Succession(Create(r, run_time=0.5), FadeOut(r, run_time=0.5)))
            if self.compact:               # the chip, and this mode's reason in place of the last one
                chip, reason = row
                swap: list[Animation] = [FadeOut(self.reason_on)] if self.reason_on is not None else []
                self.reason_on = reason
                anims.append(AnimationGroup(FadeIn(chip, scale=1.2), *swap, FadeIn(reason, shift=UP * 0.1), *rings))
            else:
                anims.append(AnimationGroup(FadeIn(row, shift=LEFT * 0.1), *rings))
        if len(self.analysed) == len(self.mode_rows):
            anims.append(FadeIn(self.analysis_concl))
        return [Succession(*anims)] if len(anims) > 1 else anims

    def risk_seconds(self) -> float:
        return RISK_SECONDS

    def run_risk(self) -> list[Animation]:
        """The proposed child appears (dashed, ?) and the risk card: the factors, the product
        and the risk under the child's symbol."""
        if "risk" not in self.card_mobs or self.risk_shown:
            return []
        self.risk_shown = True
        child = self.ped.proposed
        anims: list[Animation] = list(self.run_reveal([child])) if child else []
        anims += self._place_card("risk")
        anims.append(LaggedStart(*[FadeIn(m, shift=LEFT * 0.1) for m in self.risk_lines], lag_ratio=0.25))
        anims.append(FadeIn(self.risk_label, scale=1.3))
        return [Succession(*anims)]

    def _place_card(self, name: str) -> list[Animation]:
        """A card in the panel under those shown, or alone at the top when it does not fit (the
        others fade out). Without a panel (no room), at the chart's bottom right."""
        card = self.card_mobs[name]
        if name in self.cards_on:
            return []
        area = self.panel or Region(self.chart.x0, self.chart.y0, self.chart.x1, self.chart.y1)
        anims: list[Animation] = []
        shown = [self.card_mobs[n] for n in self.cards_on]
        top = min((m.get_bottom()[1] for m in shown), default=area.y1 + 0.35) - 0.35
        if card.height > area.height:
            card.scale(area.height / card.height)
        if shown and top - card.height < area.y0:
            anims.append(AnimationGroup(*[FadeOut(part) for m in shown for part in (self.on_screen_parts(m) or [m])]))
            self.cards_on = []
            top = area.y1
        card.move_to(np.array([area.x0 + card.width / 2, top - card.height / 2, 0.0]))
        self.cards_on.append(name)
        return anims
