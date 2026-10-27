"""``linkage_map``: linked loci on a chromosome, crossing over and genetic maps (DESIGN.md §96.9).
A homologue pair of the heterozygous parent (two sister chromatids each, in the maternal and
paternal colours of ``cell_cycle``'s meiosis) with its alleles; crossing over between non-sister
chromatids in an interval gives recombinant chromatids. With ``counts`` a two- or three-point test
cross is worked out step by step — the table of offspring classes, the parental and
double-crossover classes, the gene order, the interval distances, the coefficient of
coincidence and interference, the map — all computed by ``vidgen.genetics.mapping``. With
``map`` the loci stand at their cM positions; ``measure`` gives a distance and the RF a map
function expects. Actions (``scenes/linkage_actions.py``): ``cross_over``, ``measure``; the
built-in ``reveal`` plays the steps (``table``, ``classes``, ``order``, ``distances``,
``interference``, ``map``) on words."""

from fractions import Fraction
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import driven, small_size, text_block
from .cross_draw import homologue_colors

mp = genetics.mapping

#: The steps of a worked test cross, in order.
STEPS = ("table", "classes", "order", "distances", "interference", "map")
#: Seconds: a crossing over; a measurement.
CROSS_SECONDS, MEASURE_SECONDS = 2.4, 1.6
#: Points along a drawn chromatid.
POINTS = 72


def pct(f: Fraction | float) -> str:
    return f"{float(f) * 100:.1f} %"


def frac(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def allele_markup(locus: str, mutant: bool) -> str:
    return f"<i>{locus}</i>" if mutant else f"<i>{locus}</i><sup>+</sup>"


def _merged(steps: list[Any], most: int) -> list[Any]:
    """At most ``most`` steps: neighbours played one after another as one step (a short video
    with few beats does not get more steps than its beats can play)."""
    if len(steps) <= most:
        return steps
    size = -(-len(steps) // most)
    groups = [steps[k:k + size] for k in range(0, len(steps), size)]

    def joined(group: list[Any]) -> list[Animation]:
        anims = [a for step in group for a in step()]
        return [Succession(*anims)] if len(anims) > 1 else anims

    return [lambda g=g: joined(g) for g in groups]


@scene("linkage_map")
class LinkageMapScene(NarratedScene):
    """Linked loci on a chromosome and genetic mapping. The heterozygous parent's homologue pair
    (sister chromatids joined at the centromere, maternal and paternal colours) carries the
    alleles in coupling or repulsion; crossing over between non-sister chromatids in an interval
    swaps the segments beyond the chiasma and gives recombinant chromatids. ``counts``: a two- or
    three-point test cross worked out step by step — the table of offspring classes, the
    parental (largest) and double-crossover (smallest) classes, the gene order (the locus that
    differs between them is in the middle), each interval's recombinants, RF and map distance,
    the expected and observed double crossovers with the coefficient of coincidence and the
    interference, and the map. ``map``: loci at their positions in cM; ``measure`` shows a
    distance and the RF it gives. Map functions: none (d = 100 × RF, short distances), Haldane,
    Kosambi.

    Action targets: ``title``, ``chromosomes``, ``table``, ``classes``, ``order``, ``distances``,
    ``interference``, ``map``, ``locus:<name>``, ``interval:<a>-<b>``, ``double``."""

    outro = 0.5
    target_patterns = ("title", "chromosomes", "table", "classes", "order", "distances", "interference", "map", "locus:<name>",
                       "interval:<a>-<b>", "double")
    #: The actions cross_over and measure act on this scene type.
    linkage_actions = True
    mid_still_actions = frozenset({"cross_over", "measure"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        loci: list[str] | None = None
        """counts: the loci, named by their mutant alleles' symbols ([v, cv, ct]); the order does not matter (it is worked out)."""
        counts: dict[str, int] | None = None
        """A two- or three-point test cross: each offspring class and its number ({'v cv+ ct+': 580, '+ cv ct': 592, …}; + or v+ the wild type; every class once)."""
        map: dict[str, float] | None = None
        """Instead of counts: loci at their positions in cM ({y: 0, w: 1.5, v: 33, m: 36.1})."""
        map_function: Literal["none", "haldane", "kosambi"] = "none"
        """none: d = 100 × RF (what three-point analyses report; good below ~15 cM); haldane (no interference) or kosambi (with interference) correct for unseen double crossovers."""
        phase: Literal["coupling", "repulsion"] | None = None
        """map: the heterozygote's alleles — coupling (mutant alleles on one homologue) or repulsion (alternating); counts show their own."""
        crossover: str | list[str] | None = "auto"
        """The crossing over drawn: an interval between neighbouring loci (v-ct), a list, double (one in each interval of three loci), none; auto: the first interval."""
        chromosomes: bool = True
        """Draw the homologue pair (with counts it can be left out: the table and the map only)."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def spec(self) -> dict[str, Any]:
            data: dict[str, Any] = {"map_function": self.map_function, "crossover": self.crossover}
            for k in ("loci", "counts", "map", "phase"):
                if getattr(self, k) is not None:
                    data[k] = getattr(self, k)
            return data

        def plan(self) -> Any:
            return mp.plan_linkage(self.spec())

        @model_validator(mode="after")
        def _check(self) -> "LinkageMapScene.Params":
            try:
                self.plan()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        plan = params.plan()
        names = ["title"] if params.title else []
        names += ["chromosomes"] if params.chromosomes else []
        if plan.mode == "counts":
            names += ["table", "classes"] + (["order"] if len(plan.loci) == 3 else []) + ["distances"]
            names += ["interference"] if len(plan.loci) == 3 else []
        names += ["map"]
        names += [f"locus:{x}" for x in plan.loci]
        names += [f"interval:{n}" for n in plan.interval_names()]
        names += ["double"] if params.chromosomes and len(plan.loci) == 3 else []
        return names

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.plan = p.plan()
        self.ink = th.color("text")
        self.dim_ink = th.color("dim")
        self.hi = th.color("highlight")
        self.good = th.color("tertiary")
        self.bg = th.background
        self.colors = homologue_colors(self)
        self.small = small_size(self, p.size)
        self.counts_mode = self.plan.mode == "counts"
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.25)
        self.title_mob = title
        self.done: set[str] = set()
        self.order_now = tuple(range(len(self.plan.loci))) if self.counts_mode else self.plan.order
        self._regions(body)
        self.chrom_group = VGroup()
        if p.chromosomes:
            self._build_chromosomes()
        self.table_group = VGroup()
        if self.counts_mode:
            self._build_table()
        self._build_map()
        self.card_on: Mobject | None = None
        self._register()

    def _regions(self, body: Any) -> None:
        p = self.params
        chrom = p.chromosomes
        if self.counts_mode:
            if not self.is_portrait:
                left_w = body.width * (0.42 if chrom else 0.0)
                right = Region(body.x0 + left_w + (0.4 if chrom else 0.0), body.y0, body.x1, body.y1)
                if chrom:
                    left = Region(body.x0, body.y0, body.x0 + left_w, body.y1)
                    self.chrom_area, self.map_area = left.rows([0.58, 0.42], gap=0.3)
                    self.table_area, self.card_area = right.rows([0.62, 0.38], gap=0.25)
                else:
                    self.chrom_area = None
                    top, self.map_area = body.rows([0.72, 0.28], gap=0.25)
                    self.table_area = Region(top.x0, top.y0, top.x0 + top.width * 0.55, top.y1)
                    self.card_area = Region(self.table_area.x1 + 0.4, top.y0, top.x1, top.y1)
            else:
                shares = [0.25, 0.32, 0.25, 0.18] if chrom else [0.0, 0.45, 0.32, 0.23]
                rows = body.rows([s for s in shares if s > 0], gap=0.25)
                if chrom:
                    self.chrom_area, self.table_area, self.card_area, self.map_area = rows
                else:
                    self.chrom_area = None
                    self.table_area, self.card_area, self.map_area = rows
        else:
            self.table_area = None
            if not self.is_portrait:      # the map and its card side by side under the chromosomes
                if chrom:
                    self.chrom_area, low = body.rows([0.48, 0.52], gap=0.3)
                else:
                    self.chrom_area, low = None, body
                self.map_area = Region(low.x0, low.y0, low.x0 + low.width * 0.62, low.y1)
                self.card_area = Region(self.map_area.x1 + 0.4, low.y0, low.x1, low.y1)
            else:
                shares = [0.36, 0.34, 0.3] if chrom else [0.0, 0.55, 0.45]
                rows = body.rows([s for s in shares if s > 0], gap=0.3)
                if chrom:
                    self.chrom_area, self.map_area, self.card_area = rows
                else:
                    self.chrom_area = None
                    self.map_area, self.card_area = rows

    # ----- the chromosomes ------------------------------------------------------------------------

    def _locus_x(self, order: tuple[int, ...], proportional: bool) -> dict[int, float]:
        """Where each locus (index into loci) is along the rods: evenly in ``order``, or at the
        map's proportions."""
        x0, x1 = self.rod_x0 + self.rod_len * 0.2, self.rod_x0 + self.rod_len * 0.95
        if proportional:
            pos = self.plan.positions
            names = self.plan.ordered
            lo, hi = pos[names[0]], pos[names[-1]]
            span = (hi - lo) or 1.0
            out = {}
            for i in order:
                share = (pos[self.plan.loci[i]] - lo) / span
                out[i] = x0 + (x1 - x0) * (0.08 + 0.84 * share)
            return out
        n = len(order)
        return {i: x0 + (x1 - x0) * (0.08 + 0.84 * (k / max(1, n - 1))) for k, i in enumerate(order)}

    def _build_chromosomes(self) -> None:
        area = self.chrom_area
        plan = self.plan
        size = self.small
        self.tag_size = size
        lab = self.markup("<i>v</i><sup>+</sup>", size=size, color=self.ink)
        self.lab_h = lab.height
        sample = " ".join(allele_markup(x, False) for x in plan.loci)
        tag = self.markup(f"{sample}  recombinant", size=self.tag_size)
        self.tag_room = min(area.width * 0.5, tag.width + 0.3)
        self.rod_len = area.width - self.tag_room - 0.25
        self.rod_x0 = area.x0 + 0.1
        tag_h = tag.height * min(1.0, (self.tag_room - 0.1) / tag.width)
        thick = float(np.clip(area.height * 0.075, 0.12, 0.24))
        thick = max(thick, tag_h * 1.05 / 1.3)          # sister lanes far enough apart for a tag each
        self.thick = thick
        inner, outer = thick * 0.95, thick * 0.95 + thick * 1.3
        # the allele labels: a second row where neighbours would overlap
        self.lx = self._locus_x(plan.order, not self.counts_mode)
        layouts = [self.lx] + ([self._locus_x(plan.order, True)] if self.counts_mode else [])   # where they stand now and on the map
        rows = {i: max(r[i] for r in (self._label_rows(size, lx) for lx in layouts)) for i in self.lx}
        n_rows = 1 + max(rows.values(), default=0)
        label_room = n_rows * (self.lab_h + 0.06) + 0.08
        cap = text_block(self, "the heterozygote's homologue pair", area.width, size * 0.95, color=self.dim_ink)
        need = 2 * outer + thick + 2 * label_room + 0.25 + cap.height
        if need > area.height:            # thinner chromatids rather than overflowing
            thick *= max(0.6, (area.height - 2 * label_room - 0.25 - cap.height) / (2 * outer + thick) * 1.0)
            self.thick = thick
            inner, outer = thick * 0.95, thick * 0.95 + thick * 1.3
            need = 2 * outer + thick + 2 * label_room + 0.25 + cap.height
        cy = area.center[1] + (cap.height + 0.25) / 2
        # chromatids from the top: homologue 0 (sisters 0, 1), homologue 1 (sisters 0, 1)
        self.lanes = [cy + outer, cy + inner, cy - inner, cy - outer]
        self.cen_x = self.rod_x0 + self.rod_len * 0.07
        self.xs = np.linspace(self.rod_x0, self.rod_x0 + self.rod_len, POINTS)
        self.seg_owner = [[0 if c < 2 else 1 for _ in range(POINTS - 1)] for c in range(4)]
        self.chromatids: list[VGroup] = []
        width = thick * 100 * 0.9
        for c in range(4):
            segs = VGroup(*[VMobject().set_cap_style(CapStyleType.ROUND) for _ in range(POINTS - 1)])
            for s in segs:
                s.set_stroke(width=width)
            self.chromatids.append(segs)
        self.pull = 0.0              # how far the inner chromatids are drawn together at the chiasmata
        self.co_x: list[float] = []
        self._draw_rods()
        self.locus_marks: dict[int, VGroup] = {}
        self.allele_labels: dict[int, VGroup] = {}
        for i, name in enumerate(plan.loci):
            x = self.lx[i]
            bands = VGroup(*[Line(np.array([x, y - thick * 0.48, 0]), np.array([x, y + thick * 0.48, 0])).set_stroke(self.bg, width=2.4)
                             for y in self.lanes])
            self.locus_marks[i] = bands
            lift = rows[i] * (self.lab_h + 0.06)
            top = self.markup(allele_markup(name, plan.homologues[0][i]), size=size, color=self.colors[0])
            bot = self.markup(allele_markup(name, plan.homologues[1][i]), size=size, color=self.colors[1])
            top.move_to(np.array([x, self.lanes[0] + thick / 2 + 0.08 + lift + self.lab_h / 2, 0]))
            bot.move_to(np.array([x, self.lanes[3] - thick / 2 - 0.08 - lift - self.lab_h / 2, 0]))
            self.allele_labels[i] = VGroup(top, bot)
        self.kinetochores = VGroup(*[Dot(np.array([self.cen_x, y, 0]), radius=thick * 0.32, color=self.ink) for y in
                                     ((self.lanes[0] + self.lanes[1]) / 2, (self.lanes[2] + self.lanes[3]) / 2)])
        cap.move_to(np.array([area.x0 + cap.width / 2, self.lanes[3] - thick / 2 - label_room - 0.2 - cap.height / 2, 0]))
        self.chrom_caption = cap
        self.result_tags: list[Mobject] = []
        self.rods = VGroup(*self.chromatids, self.kinetochores)
        self.chrom_group = VGroup(self.rods, *self.locus_marks.values(), *self.allele_labels.values(), cap)

    def _label_rows(self, size: float, lx: dict[int, float]) -> dict[int, int]:
        """A row per allele label (0, or 1 above / below it when it would touch its left
        neighbour's) for the loci at ``lx``."""
        rows: dict[int, int] = {}
        last_right = {0: -1e9, 1: -1e9}
        for i in sorted(lx, key=lambda i: lx[i]):
            w = max(self.markup(allele_markup(self.plan.loci[i], f), size=size).width for f in (True, False))
            left = lx[i] - w / 2
            row = 0 if left > last_right[0] + 0.12 else (1 if left > last_right[1] + 0.12 else 0)
            rows[i] = row
            last_right[row] = lx[i] + w / 2
        return rows
    def _lane_y(self, c: int, x: float) -> float:
        """The chromatid ``c``'s height at ``x``: sisters pinched together at the centromere,
        the inner (non-sister) chromatids drawn together at the chiasmata by ``pull``."""
        y = self.lanes[c]
        mid = (self.lanes[0] + self.lanes[1]) / 2 if c < 2 else (self.lanes[2] + self.lanes[3]) / 2
        pinch = np.exp(-((x - self.cen_x) / (self.rod_len * 0.035)) ** 2)
        y = y + (mid - y) * 0.55 * pinch
        if c in (1, 2) and self.pull > 0:
            centre = (self.lanes[1] + self.lanes[2]) / 2
            for xc in self.co_x:
                bump = np.exp(-((x - xc) / (self.rod_len * 0.06)) ** 2)
                y = y + (centre - y) * self.pull * bump
        return float(y)

    def _draw_rods(self) -> None:
        for c, segs in enumerate(self.chromatids):
            pts = [np.array([x, self._lane_y(c, x), 0.0]) for x in self.xs]
            for j, s in enumerate(segs):
                s.set_points_as_corners([pts[j], pts[j + 1]])
                s.set_stroke(self.colors[self.seg_owner[c][j]], opacity=1)

    # ----- the table ------------------------------------------------------------------------------

    def _build_table(self) -> None:
        plan = self.plan
        an = plan.analysis
        area = self.table_area
        loci = plan.loci
        n = len(loci)
        rows = len(an.classes) + 2
        size = self.small
        cs0 = size * 1.1
        row_h0 = cs0 / 48 * 0.75
        row_h = min(area.height / rows, row_h0)
        self.row_h = row_h
        cs = max(readable_size() * 1.02, cs0 * row_h / row_h0)
        counts = self.params.counts or {}
        # the author's order of the classes
        keyed = [mp.class_key(k, loci, "counts") for k in counts]
        by_flags = {c.flags: c for c in an.classes}
        self.table_rows = [by_flags[f] for f in keyed]
        col_w = max(self.markup(allele_markup(x, True), size=cs).width for x in loci) + 0.35
        num_w = self.markup("0000", size=cs).width + 0.3
        widest = max(len(a) + len(b) for a, b in zip(plan.ordered, plan.ordered[1:]))
        tag_w = max(self.markup(f"<b>{w}</b>", size=cs).width for w in ("recombinant", "parental", "SCO " + "m" * (widest + 1))) + 0.3
        width = n * col_w + num_w + tag_w
        scale = min(1.0, area.width / width)
        col_w, num_w, tag_w = col_w * scale, num_w * scale, tag_w * scale
        x0 = area.x0 + max(0.0, (area.width - (n * col_w + num_w + tag_w)) / 2) * 0.0
        y_top = area.y1 - row_h / 2
        self.col_x = {i: x0 + col_w * (k + 0.5) for k, i in enumerate(range(n))}
        self.col_w = col_w
        self.num_x = x0 + n * col_w + num_w * 0.6
        self.tag_x = x0 + n * col_w + num_w + tag_w * 0.5
        self.table_x0, self.table_x1 = x0, x0 + n * col_w + num_w + tag_w
        head_cells: dict[int, Mobject] = {}
        for i, name in enumerate(loci):
            t = self.markup(f"<b><i>{name}</i></b>", size=cs, color=self.dim_ink)
            t.move_to(np.array([self.col_x[i], y_top, 0]))
            head_cells[i] = t
        num_head = self.markup("<b>number</b>", size=cs, color=self.dim_ink).move_to(np.array([self.num_x, y_top, 0]))
        rule = Line(np.array([x0, y_top - row_h / 2, 0]), np.array([self.table_x1, y_top - row_h / 2, 0])).set_stroke(self.dim_ink, width=1.5)
        self.cells: dict[int, dict[int, Mobject]] = {}
        self.nums: dict[int, Mobject] = {}
        self.row_y: dict[int, float] = {}
        self.row_bg: dict[int, Mobject] = {}
        for r, cls in enumerate(self.table_rows):
            y = y_top - row_h * (r + 1)
            self.row_y[r] = y
            self.cells[r] = {}
            for i, name in enumerate(loci):
                t = self.markup(f"<i>{name}</i>" if cls.flags[i] else "+", size=cs, color=self.ink)
                t.move_to(np.array([self.col_x[i], y, 0]))
                self.cells[r][i] = t
            num = self.markup(str(cls.count), size=cs, color=self.ink)
            num.move_to(np.array([self.num_x + num_w * 0.35 - num.width / 2, y, 0]))
            self.nums[r] = num
            bg = Rectangle(width=self.table_x1 - x0 + 0.1, height=row_h * 0.92).move_to(np.array([(x0 + self.table_x1) / 2, y, 0]))
            bg.set_fill(self.hi, opacity=0.0).set_stroke(width=0)
            self.row_bg[r] = bg
        total_y = y_top - row_h * (len(self.table_rows) + 1)
        rule2 = Line(np.array([x0, total_y + row_h / 2, 0]), np.array([self.table_x1, total_y + row_h / 2, 0])).set_stroke(self.dim_ink, width=1.5)
        total = self.markup(f"<b>{an.total}</b>", size=cs, color=self.ink)
        total.move_to(np.array([self.num_x + num_w * 0.35 - total.width / 2, total_y, 0]))
        total_lab = self.markup("total", size=cs, color=self.dim_ink)
        total_lab.move_to(np.array([x0 + total_lab.width / 2 + 0.05, total_y, 0]))
        self.head_cells = head_cells
        self.table_frame = VGroup(num_head, rule, rule2, total, total_lab)
        self.table_group = VGroup(*self.row_bg.values(), *head_cells.values(), self.table_frame,
                                  *[m for row in self.cells.values() for m in row.values()], *self.nums.values())
        # the tags of the classes
        self.tags: dict[int, Mobject] = {}
        self.sco_tags: dict[int, Mobject] = {}
        names = plan.ordered
        for r, cls in enumerate(self.table_rows):
            if cls.kind == "parental":
                text, color = "parental", self.good
            elif cls.kind == "double":
                text, color = "DCO", self.hi
            elif cls.kind == "recombinant":
                text, color = "recombinant", self.hi
            else:
                text, color = "", self.dim_ink
            if text:
                t = self.markup(f"<b>{text}</b>", size=cs, color=color)
                t.move_to(np.array([self.tag_x, self.row_y[r], 0]))
                if t.width > tag_w:
                    t.scale(tag_w / t.width)
                self.tags[r] = t
            elif cls.interval is not None:
                a, b = names[cls.interval], names[cls.interval + 1]
                t = self.markup(f"SCO <i>{a}</i>–<i>{b}</i>", size=cs, color=self.dim_ink)
                if t.width > tag_w:
                    t.scale(tag_w / t.width)
                t.move_to(np.array([self.tag_x, self.row_y[r], 0]))
                self.sco_tags[r] = t

    # ----- the map --------------------------------------------------------------------------------

    def _build_map(self) -> None:
        plan = self.plan
        area = self.map_area
        size = self.small
        names = plan.ordered
        pos = plan.positions
        lo, hi = pos[names[0]], pos[names[-1]]
        span = (hi - lo) or 1.0
        x0, x1 = area.x0 + 0.35, area.x1 - 0.35
        self.map_x = {n: x0 + (x1 - x0) * (pos[n] - lo) / span for n in names}

        def staggered(mobs: list[Mobject]) -> list[int]:
            """Rows (0, 1) for labels in map order, a neighbour that would touch going to the other row."""
            rows, right = [], {0: -1e9, 1: -1e9}
            for n, m in zip(names, mobs):
                left = self.map_x[n] - m.width / 2
                row = 0 if left > right[0] + 0.12 else (1 if left > right[1] + 0.12 else 0)
                rows.append(row)
                right[row] = self.map_x[n] + m.width / 2
            return rows

        name_mobs = [self.markup(f"<i>{n}</i>", size=size * 1.1, color=self.ink) for n in names]
        cm_mobs = [self.markup(f"{pos[n]:g}" if not self.counts_mode else f"{pos[n]:.1f}", size=size * 0.95, color=self.dim_ink)
                   for n in names]
        name_rows, cm_rows = staggered(name_mobs), staggered(cm_mobs)
        nh, ch = name_mobs[0].height, cm_mobs[0].height
        top_room = (1 + max(name_rows)) * (nh + 0.06)
        y = area.y1 - top_room - 0.25          # the bar, under the names
        bar = Line(np.array([x0 - 0.15, y, 0]), np.array([x1 + 0.15, y, 0])).set_stroke(self.ink, width=5)
        ticks = VGroup()
        for n, t, c, rn, rc in zip(names, name_mobs, cm_mobs, name_rows, cm_rows):
            x = self.map_x[n]
            ticks.add(Line(np.array([x, y - 0.14, 0]), np.array([x, y + 0.14, 0])).set_stroke(self.ink, width=3))
            t.move_to(np.array([x, y + 0.2 + rn * (nh + 0.06) + nh / 2, 0]))
            c.move_to(np.array([x, y - 0.2 - rc * (ch + 0.05) - ch / 2, 0]))
        below = y - 0.2 - (1 + max(cm_rows)) * (ch + 0.05)
        dists = VGroup()
        self.interval_marks: dict[str, VGroup] = {}
        labels = [self.markup(f"{pos[b] - pos[a]:.1f} cM", size=size * 0.9, color=self.hi) for a, b in zip(names, names[1:])]
        brace_y = below - 0.12
        lh = labels[0].height if labels else 0.0
        right = {0: -1e9, 1: -1e9}
        for (a, b), t in zip(zip(names, names[1:]), labels):
            xa, xb = self.map_x[a], self.map_x[b]
            br = VGroup(Line(np.array([xa, brace_y, 0]), np.array([xb, brace_y, 0])),
                        Line(np.array([xa, brace_y, 0]), np.array([xa, brace_y + 0.1, 0])),
                        Line(np.array([xb, brace_y, 0]), np.array([xb, brace_y + 0.1, 0]))).set_stroke(self.hi, width=2.4)
            mid = (xa + xb) / 2
            row = 0 if mid - t.width / 2 > right[0] + 0.2 else 1
            right[row] = mid + t.width / 2
            t.move_to(np.array([mid, brace_y - 0.08 - row * (lh + 0.05) - lh / 2, 0]))
            dists.add(VGroup(br, t))
            self.interval_marks[f"{a}-{b}"] = VGroup(br, t)
        bottom = (dists.get_bottom()[1] if len(dists) else below) - 0.12
        unit = self.markup("map position (cM)", size=size * 0.95, color=self.dim_ink)
        unit.move_to(np.array([x0 - 0.15 + unit.width / 2, bottom - unit.height / 2, 0]))
        parts: list[Mobject] = [bar, ticks, VGroup(*name_mobs), VGroup(*cm_mobs), dists, unit]
        if plan.function != "none":
            func = self.markup(mp.MAP_FUNCTIONS[plan.function], size=size * 0.95, color=self.dim_ink)
            if unit.width + func.width + 0.4 < x1 - x0 + 0.3:
                func.move_to(np.array([x1 + 0.15 - func.width / 2, unit.get_center()[1], 0]))
            else:
                func.move_to(np.array([x0 - 0.15 + func.width / 2, unit.get_bottom()[1] - 0.06 - func.height / 2, 0]))
            parts.append(func)
        group = VGroup(*parts)
        if group.height > area.height:
            group.scale(area.height / group.height, about_edge=UP)
        self.map_group = group
        self.map_x = {n: ticks[k].get_center()[0] for k, n in enumerate(names)}
        self.map_bar_y = bar.get_center()[1]
        self.map_name_top = VGroup(*name_mobs).get_top()[1]
    # ----- cards --------------------------------------------------------------------------------

    def _card(self, lines: list[str], head: str | None = None) -> VGroup:
        area = self.card_area
        size = self.small
        parts: list[Mobject] = []
        if head:
            parts.append(self.markup(f"<b>{head}</b>", size=size * 1.05, color=self.ink))
        for line in lines:
            parts.append(text_block(self, line, area.width - 0.1, size, color=self.ink))
        card = VGroup(*parts).arrange(DOWN, buff=0.14, aligned_edge=LEFT)
        if card.height > area.height:
            card.scale(area.height / card.height)
        card.move_to(np.array([area.x0 + card.width / 2, area.y1 - card.height / 2, 0]))
        return card

    def _swap_card(self, card: Mobject) -> list[Animation]:
        anims: list[Animation] = []
        if self.card_on is not None:
            anims.append(FadeOut(self.card_on))
        self.card_on = card
        anims.append(FadeIn(card, shift=UP * 0.08))
        return [AnimationGroup(*anims, lag_ratio=0.4)]

    # ----- targets and steps ------------------------------------------------------------------------

    def _register(self) -> None:
        p = self.params
        title = self.title_mob
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        if p.chromosomes:
            self.target("chromosomes", self.chrom_group, entrance=lambda: self.run_step("chromosomes"))
            if len(self.plan.loci) == 3:
                self.target("double", self.rods)
            for i, name in enumerate(self.plan.loci):
                self.target(f"locus:{name}", VGroup(self.locus_marks[i], self.allele_labels[i]))
        else:
            for i, name in enumerate(self.plan.loci):
                self.target(f"locus:{name}", self.map_group)
        if self.counts_mode:
            names = ["table", "classes"] + (["order"] if len(self.plan.loci) == 3 else []) + ["distances"]
            names += ["interference"] if len(self.plan.loci) == 3 else []
            for n in names:
                mob = self.table_group if n == "table" else VGroup(*self.tags.values()) if n == "classes" else self.table_group
                self.target(n, mob, entrance=lambda n=n: self.run_step(n))
        self.target("map", self.map_group, entrance=lambda: self.run_step("map"))
        for name in self.plan.interval_names():
            a, b = name.split("-")
            mark = self.interval_marks.get(name) or self.interval_marks.get(f"{b}-{a}")
            self.target(f"interval:{name}", mark if mark is not None else self.map_group)
        held: set[str] = set()
        for use in self.action_uses("reveal"):
            held.update(use.config.targets())
        # manual: the steps are played by reveal actions (or measure); cross_over alone only takes the crossing over's place
        manual = bool(self.action_uses("measure")) or bool(held & {*STEPS, "chromosomes"})
        crossing = p.chromosomes and bool(self.plan.crossovers) and not self.action_uses("cross_over")

        def first() -> list[Animation]:
            anims: list[Animation] = [FadeIn(title)] if title is not None else []
            if p.chromosomes and "chromosomes" not in held:
                anims += self.run_step("chromosomes")
            if manual and not self.counts_mode and "map" not in held:
                anims += self.run_step("map")
            return anims

        steps: list[Any] = [first]
        if not manual:
            if crossing:
                steps.append(lambda: self.run_cross(self.plan.crossovers))
            if self.counts_mode:
                names = self.target_names(p)
                steps += [lambda n=n: self.run_step(n) for n in ("table", "classes", "order", "distances", "interference") if n in names]
            steps.append(lambda: self.run_step("map"))
        self.reveal(_merged(steps, 2 * max(1, len(self.beats))), fraction=0.85, cap=3.0)
        self.finish()

    def run_step(self, name: str) -> list[Animation]:
        """Play a step (and the earlier ones it needs, in one go)."""
        if name in self.done:
            return []
        anims: list[Animation] = []
        if self.counts_mode and name in STEPS:
            k = STEPS.index(name)
            for before in STEPS[:k]:
                if before in ("order", "interference") and len(self.plan.loci) == 2:
                    continue
                if before != "map" and before not in self.done:
                    anims += self.run_step(before)
        self.done.add(name)
        if name == "chromosomes":
            return [FadeIn(self.chrom_group)]
        part = getattr(self, f"_step_{name}")()
        return [Succession(*anims, *part)] if anims else part

    def _step_table(self) -> list[Animation]:
        rows = [VGroup(*self.cells[r].values(), self.nums[r]) for r in self.cells]
        head = VGroup(*self.head_cells.values(), self.table_frame)
        return [Succession(FadeIn(head), LaggedStart(*[FadeIn(r, shift=LEFT * 0.08) for r in rows], lag_ratio=0.12))]

    def _step_classes(self) -> list[Animation]:
        an = self.plan.analysis
        flash = []
        for r, t in self.tags.items():
            flash.append(FadeIn(t, scale=1.2))
            self.row_bg[r].set_fill(self.good if self.table_rows[r].kind == "parental" else self.hi, opacity=0.0)
            flash.append(self.row_bg[r].animate.set_fill(opacity=0.14))
        p1, p2 = (mp.class_text(f, an.loci) for f in an.parental)
        if len(an.loci) == 2:
            phase = "coupling (cis)" if an.phase == "coupling" else "repulsion (trans)"
            lines = [f"Parental (largest): <i>{p1}</i> and <i>{p2}</i> — the heterozygote was <i>{p1}</i> / <i>{p2}</i>: {phase}",
                     f"Recombinants: {an.total - sum(c.count for c in an.classes if c.kind == 'parental')} of {an.total}"]
        else:
            d1, d2 = (mp.class_text(f, an.loci) for f in an.double)
            lines = [f"Parental classes (the largest pair): <i>{p1}</i> and <i>{p2}</i>",
                     f"Double crossovers (the smallest pair): <i>{d1}</i> and <i>{d2}</i>"]
        return [AnimationGroup(*flash, *self._swap_card(self._card(lines, "Classes")))]

    def _step_order(self) -> list[Animation]:
        an = self.plan.analysis
        mid = an.middle
        p1 = mp.class_text(an.parental[0], an.loci)
        d = next(f for f in an.double if sum(a != b for a, b in zip(f, an.parental[0])) == 1) if any(
            sum(a != b for a, b in zip(f, an.parental[0])) == 1 for f in an.double) else an.double[0]
        dt = mp.class_text(d, an.loci)
        order = " – ".join(f"<i>{x}</i>" for x in an.ordered)
        lines = [f"A double crossover swaps only the middle locus: <i>{p1}</i> → <i>{dt}</i> differ at <i>{mid}</i>",
                 f"Gene order: {order}"]
        anims: list[Animation] = list(self._swap_card(self._card(lines, "Gene order")))
        new = self.plan.order
        moves: list[Animation] = []
        if new != self.order_now:          # the table's columns in map order (the chromosome is drawn in it)
            for k, i in enumerate(new):
                x = self.table_x0 + self.col_w * (k + 0.5)
                cells = [self.cells[r][i] for r in self.cells] + [self.head_cells[i]]
                moves += [m.animate.set_x(x) for m in cells]
            self.order_now = new
        mid_i = self.plan.loci.index(mid)
        ring = Indicate(VGroup(self.head_cells[mid_i], *[self.cells[r][mid_i] for r in self.cells]), color=self.hi, scale_factor=1.15)
        return [Succession(AnimationGroup(*anims), *([AnimationGroup(*moves)] if moves else []), ring)]

    def _step_distances(self) -> list[Animation]:
        an = self.plan.analysis
        names = an.ordered
        lines = []
        flashes: list[Animation] = []
        for k, iv in enumerate(an.intervals):
            rows = [r for r, c in enumerate(self.table_rows) if self._recombinant(c.flags, an.loci.index(iv.left), an.loci.index(iv.right))]
            terms = " + ".join(str(self.table_rows[r].count) for r in rows)
            unit = f"{iv.cm:.1f} cM" + ("" if an.function == "none" else f" ({an.function.capitalize()})")
            lines.append(f"<i>{iv.left}</i>–<i>{iv.right}</i>: {terms} = {iv.recombinants}; {iv.recombinants}/{an.total} = "
                         f"{pct(iv.rf)} → <b>{unit}</b>")
            flashes.append(AnimationGroup(*[Indicate(self.nums[r], color=self.hi, scale_factor=1.15) for r in rows]))
        if len(names) == 3:
            outer = an.intervals[0].cm + an.intervals[1].cm
            lines.append(f"<i>{names[0]}</i>–<i>{names[2]}</i>: {outer:.1f} cM, the sum (a double crossover counts in both intervals)")
        tags = [FadeIn(t) for t in self.sco_tags.values()]
        return [Succession(AnimationGroup(*self._swap_card(self._card(lines, "Map distances")), *tags), *flashes)]

    def _recombinant(self, flags: tuple[bool, ...], i: int, j: int) -> bool:
        p = self.plan.analysis.parental[0]
        return (flags[i] == flags[j]) != (p[i] == p[j])

    def _step_interference(self) -> list[Animation]:
        an = self.plan.analysis
        r1, r2 = an.intervals[0].rf, an.intervals[1].rf
        exp = an.expected_double
        if an.coincidence is None:
            lines = ["An interval without recombinants: no double crossovers are expected; coincidence is undefined"]
        else:
            lines = [f"Expected DCO = RF₁ × RF₂ × N = {float(r1):.3f} × {float(r2):.3f} × {an.total} = {float(exp):.1f}",
                     f"Observed {an.observed_double}: coincidence c = {an.observed_double}/{float(exp):.1f} = {float(an.coincidence):.2f}",
                     f"Interference I = 1 − c = <b>{float(an.interference):.2f}</b>"
                     + (" (a crossover hinders another nearby)" if an.interference > 0 else "")]
        rows = [r for r, c in enumerate(self.table_rows) if c.kind == "double"]
        flash = [Indicate(self.nums[r], color=self.hi, scale_factor=1.2) for r in rows]
        return [Succession(AnimationGroup(*self._swap_card(self._card(lines, "Interference"))), AnimationGroup(*flash))]

    def _step_map(self) -> list[Animation]:
        anims: list[Animation] = [Create(self.map_group[0]), LaggedStart(*[FadeIn(m) for m in self.map_group[1:]], lag_ratio=0.15)]
        if self.params.chromosomes and self.counts_mode:   # loci move to their map proportions
            lx = self._locus_x(self.plan.order, True)
            moves = []
            for i in range(len(self.plan.loci)):
                dx = lx[i] - self.lx[i]
                if abs(dx) > 1e-6:
                    moves.append(VGroup(self.locus_marks[i], self.allele_labels[i]).animate.shift(RIGHT * dx))
            self.lx = lx
            if moves:
                anims.append(AnimationGroup(*moves))
        return [Succession(*anims)]

    # ----- crossing over and measuring -------------------------------------------------------------

    def cross_seconds(self) -> float:
        return CROSS_SECONDS

    def run_cross(self, intervals: tuple[int, ...]) -> list[Animation]:
        """The inner (non-sister) chromatids come together at a chiasma in each interval, swap
        the segments beyond it and part: two recombinant chromatids, two parental ones; each
        chromatid's alleles are written beside it."""
        if not self.params.chromosomes:
            return []
        pre: list[Animation] = [] if "chromosomes" in self.done else self.run_step("chromosomes")
        order = self.plan.order
        lx = self.lx
        cos = []
        for k in intervals:
            a, b = order[k], order[k + 1]
            cos.append((lx[a] + lx[b]) / 2)
        self.co_x = cos
        swap = [j for j in range(POINTS - 1) if sum(1 for x in cos if x < (self.xs[j] + self.xs[j + 1]) / 2) % 2 == 1]
        before = [list(row) for row in self.seg_owner]
        after = [list(row) for row in before]
        for j in swap:
            after[1][j], after[2][j] = before[2][j], before[1][j]
        state = {"swapped": False}

        def frame(alpha: float) -> None:
            self.pull = float(np.sin(np.pi * min(1.0, alpha / 0.9)) ** 2) * 0.9 if alpha < 0.9 else 0.0
            if alpha >= 0.45 and not state["swapped"]:
                self.seg_owner = after
                state["swapped"] = True
            elif alpha < 0.45 and state["swapped"]:
                self.seg_owner = before
                state["swapped"] = False
            self._draw_rods()

        tags = self._result_tags(after)
        old = list(self.result_tags)
        self.result_tags = tags
        moving = VGroup(*self.chromatids)
        main = [driven(moving, frame, rate_func=linear, run_time=CROSS_SECONDS * 0.75)]
        out = [FadeOut(t) for t in old]
        show = [LaggedStart(*[FadeIn(t, shift=LEFT * 0.1) for t in tags], lag_ratio=0.2)]
        return [Succession(*pre, *([AnimationGroup(*out)] if out else []), *main, *show)]

    def _result_tags(self, owner: list[list[int]]) -> list[Mobject]:
        """Each chromatid's alleles after crossing over (coloured by the homologue they came
        from) with parental or recombinant."""
        out = []
        size = self.tag_size
        gap = min(abs(self.lanes[k] - self.lanes[k + 1]) for k in range(3))
        for c in range(4):
            parts = []
            origin = []
            for i in self.plan.order:
                x = self.lx[i]
                j = int(np.clip(np.searchsorted(self.xs, x) - 1, 0, POINTS - 2))
                h = owner[c][j]
                origin.append(h)
                color = self.colors[h]
                parts.append(f'<span foreground="{color}">{allele_markup(self.plan.loci[i], self.plan.homologues[h][i])}</span>')
            rec = len(set(origin)) > 1
            kind = "recombinant" if rec else "parental"
            t = self.markup(" ".join(parts) + f"  <span foreground=\"{self.hi if rec else self.dim_ink}\">{kind}</span>", size=size,
                            color=self.ink)
            room = self.tag_room - 0.1
            if t.width > room:
                t.scale(room / t.width)
            if t.height > gap * 0.95:
                t.scale(gap * 0.95 / t.height)
            t.move_to(np.array([self.rod_x0 + self.rod_len + 0.2 + t.width / 2, self.lanes[c], 0]))
            out.append(t)
        return out

    def measure_seconds(self) -> float:
        return MEASURE_SECONDS

    def run_measure(self, text: str) -> list[Animation]:
        """A bracket over the interval on the map and its distance and RF on the card."""
        a, b, d, rf = mp.measure_interval(self.plan, text)
        pre = self.run_step("map") if "map" not in self.done else []
        xa, xb = sorted((self.map_x[a], self.map_x[b]))
        y = self.map_name_top + 0.15
        br = VGroup(Line(np.array([xa, y, 0]), np.array([xb, y, 0])), Line(np.array([xa, y, 0]), np.array([xa, y - 0.1, 0])),
                    Line(np.array([xb, y, 0]), np.array([xb, y - 0.1, 0]))).set_stroke(self.hi, width=3)
        func = self.plan.function
        lines = [f"<i>{a}</i>–<i>{b}</i>: {d:.1f} cM"]
        if func == "none":
            lines.append(f"RF ≈ {d:.1f} / 100 = {pct(rf)}" + (" (50 %: they assort independently)" if rf >= 0.5 else "")
                         + (f" — over {mp.SHORT_CM:g} cM the plain RF overestimates it; Haldane gives {pct(mp.cm_to_rf(d, 'haldane'))}"
                            if d > mp.SHORT_CM and rf < 0.5 else ""))
        else:
            lines.append(f"{mp.MAP_FUNCTIONS[func]} → RF = {pct(rf)}")
        old = getattr(self, "measure_mark", None)
        self.measure_mark = br
        anims: list[Animation] = list(pre)
        if old is not None:
            anims.append(FadeOut(old))
        anims += [Create(br)] + self._swap_card(self._card(lines, "Distance"))
        return [Succession(*anims)]
