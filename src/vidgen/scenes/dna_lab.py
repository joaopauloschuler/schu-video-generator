"""``dna_lab``: the techniques of a genetics laboratory (DESIGN.md §96.15), one per ``method``.

- ``pcr``: the template with its primers, the three temperatures of a cycle as a trace, the
  molecules doubling cycle by cycle (the product of defined length first appears in cycle 3) and
  the counts 2ⁿ / 2ⁿ − 2n.
- ``gel``: an agarose gel with its wells at the cathode, a size ladder and the samples' bands
  migrating towards the anode, log-linear in size, with a size read off the ladder.
- ``sanger``: chain termination with ddNTPs, the fragments sorted by length and the trace with
  its called bases (a heterozygous position as two half-height peaks).
- ``ngs``: reads aligned to a reference, the coverage under it and a variant call from the share
  of alt reads.

The model is ``vidgen.genetics.dna_lab``; the action ``run`` is in ``scenes/molecular_actions.py``."""

from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import small_size, text_block
from .molecular_draw import BASE_HUES, Letters, base_ink, base_tile, esc, plot_axes


def BASE_HUE(base: str) -> str:
    return BASE_HUES.get(base.upper(), "#9A9A9A")

lab = genetics.dna_lab

#: Seconds per step of each method.
STEP_SECONDS = 2.2
#: The steps of each method, in order.
METHOD_STEPS = {
    "pcr": ("setup", "cycle", "count"),
    "gel": ("setup", "run", "read"),
    "sanger": ("setup", "separate", "trace"),
    "ngs": ("setup", "align", "call"),
}


@scene("dna_lab")
class DnaLabScene(NarratedScene):
    """A laboratory technique of molecular genetics. ``method: pcr``: the primers checked against
    the template (a forward primer repeats the top strand, a reverse primer is the reverse
    complement downstream), the product's length, melting temperatures and the annealing
    temperature, a temperature trace of the cycles and the molecules counted (2ⁿ after n cycles,
    2ⁿ − 2n of them exactly the product's length; the first appear in cycle 3). ``method: gel``:
    an agarose gel, DNA running from the wells (cathode, −) to the anode (+), the distance
    log-linear in the fragment size within the gel's resolving range, a ladder, and a band's size
    read off it. ``method: sanger``: chain termination with ddNTPs, the fragments sorted by
    length and a chromatogram with the called bases (a heterozygous position: two half-height
    peaks and its IUPAC code). ``method: ngs``: seeded reads aligned to a reference with their
    coverage and a variant call (≈50 % alt reads: heterozygous).

    Action targets: ``title``, and per method ``template``, ``primers``, ``product``, ``trace``,
    ``cycle:<n>``, ``counts`` (pcr); ``gel``, ``ladder``, ``lane:<label>``, ``sizes`` (gel);
    ``sequence``, ``fragments``, ``chromatogram`` (sanger); ``reference``, ``reads``,
    ``coverage``, ``call`` (ngs)."""

    outro = 0.5
    target_patterns = ("title", "template", "primers", "product", "trace", "cycle:<n>", "counts", "gel", "ladder", "lane:<label>",
                       "sizes", "sequence", "fragments", "chromatogram", "reference", "reads", "coverage", "call")
    #: The action run acts on this scene type.
    lab_actions = True
    mid_still_actions = frozenset({"run"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        method: Literal["pcr", "gel", "sanger", "ngs"] = "pcr"
        """pcr: cycles and copies; gel: agarose electrophoresis; sanger: chain termination and a chromatogram; ngs: reads, coverage and a variant call."""
        template: str | None = None
        """pcr: the template's top strand 5′→3′ (40–5000 bp)."""
        primers: dict[str, str] | None = None
        """pcr: {forward: …, reverse: …}, both 5′→3′ (15–35 nt); checked against the template (the reverse primer is the reverse complement of the top strand)."""
        temperatures: dict[str, float] | None = None
        """pcr: {denature: 95, anneal: 58, extend: 72} °C; the annealing default is ~5 °C below the lower primer Tm."""
        cycles: int | None = Field(None, ge=1, le=40)
        """pcr: how many cycles (default 30; 25–35 typical)."""
        agarose: float | None = Field(None, ge=0.5, le=3.0)
        """gel: the agarose percentage (0.5–3 %): it sets the sizes the gel resolves."""
        ladder: str | list[float] | None = None
        """gel: 1kb, 100bp, 50bp or a list of sizes in bp."""
        lanes: dict[str, list[float] | float] | list[dict[str, Any]] | None = None
        """gel: the samples, {PCR: [450], digest: [300, 150]} (bp)."""
        sequence: str | None = None
        """sanger: the new strand's bases 5′→3′ as the trace reads them (8–40 nt)."""
        heterozygous: str | list[str] | None = None
        """sanger: positions read as two bases, '12A>G' (one or a list)."""
        primer: str | None = None
        """sanger: the sequencing primer (15–35 nt), shown before the read."""
        reference: str | None = None
        """ngs: the reference sequence the reads align to (30–120 bp)."""
        variant: str | None = None
        """ngs: the variant in the sample, '31C>T' (a position in the reference)."""
        zygosity: Literal["heterozygous", "homozygous", "absent"] | None = None
        """ngs: whether the sample carries the variant on one allele (≈50 % of reads), both, or none."""
        read_length: int | None = None
        """ngs: the reads' length (default 25)."""
        depth: int | None = None
        """ngs: the expected coverage (default 20; a clinical call wants ≥ 20)."""
        error_rate: float | None = None
        """ngs: the per-base sequencing error rate (default 0.005)."""
        seed: int = 1
        """Changes the seeded reads or peak heights."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def spec(self) -> dict[str, Any]:
            data: dict[str, Any] = {"method": self.method, "seed": self.seed}
            keys = ("template", "primers", "temperatures", "cycles", "agarose", "ladder", "lanes", "sequence", "heterozygous", "primer",
                    "reference", "variant", "zygosity", "read_length", "depth", "error_rate")
            for key in keys:
                if getattr(self, key) is not None:
                    data[key] = getattr(self, key)
            return data

        def plan(self) -> Any:
            return lab.plan_lab(self.spec())

        @model_validator(mode="after")
        def _check(self) -> "DnaLabScene.Params":
            try:
                self.plan()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        plan = params.plan()
        names = ["title"] if params.title else []
        if plan.method == "pcr":
            names += ["template", "primers", "product", "trace", "counts"]
            names += [f"cycle:{k + 1}" for k in range(plan.pcr.cycles)]
        elif plan.method == "gel":
            names += ["gel", "ladder", "sizes"] + [f"lane:{lane.label}" for lane in plan.gel.lanes[1:]]
        elif plan.method == "sanger":
            names += ["sequence", "fragments", "chromatogram"]
        else:
            names += ["reference", "reads", "coverage", "call"]
        return names

    @property
    def steps(self) -> tuple[str, ...]:
        return METHOD_STEPS[self.params.method]

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.plan = p.plan()
        self.ink, self.dim_ink = th.color("text"), th.color("dim")
        self.hi, self.bad, self.good = th.color("highlight"), th.color("accent"), th.color("tertiary")
        self.cold, self.warm = th.color("primary"), th.color("secondary")
        self.small = small_size(self, p.size)
        self.tiny = max(readable_size() * 1.02, self.small * 0.85)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.25)
        self.title_mob = title
        self.done: set[str] = set()
        self.card_mob: Mobject | None = None
        if not self.is_portrait:
            self.main_area, self.card_area = body.rows([0.72, 0.28], gap=0.3)
        else:
            self.main_area, self.card_area = body.rows([0.74, 0.26], gap=0.3)
        getattr(self, f"_build_{p.method}")()
        self._register()

    # ----- cards -----------------------------------------------------------------------------------

    def _card(self, lines: list[str], head: str) -> VGroup:
        """The card, dropping its last lines rather than shrinking the text below the readable
        size (the first lines say what the step is; the later ones are notes)."""
        area = self.card_area
        items = list(lines)
        while True:
            card = self._card_body(items, head)
            if card.height <= area.height or len(items) <= 1:
                break
            items = items[:-1]
        if card.height > area.height:
            card.scale(area.height / card.height)
        y = area.y1 - card.height / 2 if not self.is_portrait else max(area.center[1], area.y1 - card.height / 2 - 0.4)
        return card.move_to(np.array([area.x0 + card.width / 2, y, 0]))

    def _card_body(self, lines: list[str], head: str) -> VGroup:
        area = self.card_area
        size = self.small
        title = self.markup(f"<b>{esc(head)}</b>", size=size * 1.15, color=self.ink)
        cols = 1 if self.is_portrait or len(lines) <= 2 else 2
        width = area.width if cols == 1 else area.width / 2 - 0.3
        blocks = [text_block(self, line, width, size, color=self.ink) for line in lines]
        if cols == 1:
            body = VGroup(*blocks).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
        else:
            half = (len(blocks) + 1) // 2
            c1 = VGroup(*blocks[:half]).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
            c2 = VGroup(*blocks[half:]).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
            c2.next_to(c1, RIGHT, buff=0.5, aligned_edge=UP)
            body = VGroup(c1, c2)
        card = VGroup(title, body).arrange(DOWN, buff=0.16, aligned_edge=LEFT)
        if card.width > area.width:
            card.scale(area.width / card.width)
        return card

    def _swap(self, card: Mobject) -> list[Animation]:
        anims: list[Animation] = []
        if self.card_mob is not None:
            anims.append(FadeOut(self.card_mob))
        self.card_mob = card
        anims.append(FadeIn(card, shift=UP * 0.06))
        return [AnimationGroup(*anims, lag_ratio=0.4)]

    # ----- PCR -------------------------------------------------------------------------------------

    def _build_pcr(self) -> None:
        """The template with its primers over it, the temperature trace and the molecules."""
        p = self.plan.pcr
        area = self.main_area
        rows = area.rows([0.46, 0.54], gap=0.25) if not self.is_portrait else area.rows([0.4, 0.6], gap=0.25)
        self.dna_area, low = rows
        if not self.is_portrait:
            self.trace_area = Region(low.x0, low.y0, low.x0 + low.width * 0.52, low.y1)
            self.mol_area = Region(self.trace_area.x1 + 0.4, low.y0, low.x1, low.y1)
        else:
            self.trace_area, self.mol_area = low.rows([0.5, 0.5], gap=0.2)
        self._pcr_template()
        self._pcr_trace()
        self._pcr_molecules()

    def _pcr_x(self, i: float) -> float:
        a = self.dna_area
        return a.x0 + 0.55 + (a.width - 1.1) * i / len(self.plan.pcr.template)

    def _pcr_template(self) -> None:
        p = self.plan.pcr
        area = self.dna_area
        y = area.y1 - area.height * 0.3
        h = min(0.16, area.height * 0.12)
        self.pcr_y, self.pcr_h = y, h
        x0, x1 = self._pcr_x(0), self._pcr_x(len(p.template))
        top = Rectangle(width=x1 - x0, height=h).move_to(np.array([(x0 + x1) / 2, y + h * 0.75, 0]))
        bot = Rectangle(width=x1 - x0, height=h).move_to(np.array([(x0 + x1) / 2, y - h * 0.75, 0]))
        for r in (top, bot):
            r.set_fill(self.dim_ink, opacity=0.35).set_stroke(self.dim_ink, width=1.5)
        size = self.tiny
        ends = VGroup(self.markup("5′", size=size, color=self.dim_ink).next_to(top, LEFT, buff=0.08),
                      self.markup("3′", size=size, color=self.dim_ink).next_to(top, RIGHT, buff=0.08),
                      self.markup("3′", size=size, color=self.dim_ink).next_to(bot, LEFT, buff=0.08),
                      self.markup("5′", size=size, color=self.dim_ink).next_to(bot, RIGHT, buff=0.08))
        lab_t = self.markup(f"template  {len(p.template)} bp", size=size, color=self.dim_ink)
        lab_t.next_to(top, UP, buff=0.12).align_to(top, LEFT)
        self.pcr_template = VGroup(top, bot, ends, lab_t)
        # the primers: the forward one on the top strand's sequence, the reverse one on the bottom
        fx0, fx1 = self._pcr_x(p.f_at), self._pcr_x(p.f_at + len(p.forward))
        rx0, rx1 = self._pcr_x(p.r_end - len(p.reverse)), self._pcr_x(p.r_end)
        fwd = self._arrow_bar(fx0, fx1, y + h * 0.75, 1, self.good)
        rev = self._arrow_bar(rx0, rx1, y - h * 0.75, -1, self.warm)
        # the forward primer's label over the top strand, the reverse primer's under the bottom one
        fl = self.markup("forward primer 5′→3′", size=size, color=self.good)
        fl.move_to(np.array([(fx0 + fx1) / 2, lab_t.get_center()[1], 0]))
        rl = self.markup("reverse primer 5′→3′", size=size, color=self.warm).next_to(rev, DOWN, buff=0.12)
        for lab in (fl, rl):
            lab.set_x(min(max(lab.get_x(), area.x0 + lab.width / 2), area.x1 - lab.width / 2))
        if fl.get_left()[0] < lab_t.get_right()[0] + 0.15:      # the template's own label is in that lane
            fl.shift(UP * (fl.height + 0.06))
        self.pcr_primers = VGroup(fwd, fl, rev, rl)
        # the product
        py = rl.get_bottom()[1] - 0.22
        bar = Line(np.array([fx0, py, 0]), np.array([rx1, py, 0])).set_stroke(self.hi, width=4)
        ticks = VGroup(Line(np.array([fx0, py - 0.07, 0]), np.array([fx0, py + 0.07, 0])),
                       Line(np.array([rx1, py - 0.07, 0]), np.array([rx1, py + 0.07, 0]))).set_stroke(self.hi, width=3)
        plab = self.markup(f"<b>product {p.product} bp</b>", size=self.tiny, color=self.hi)
        plab.move_to(np.array([(fx0 + rx1) / 2, py - 0.1 - plab.height / 2, 0]))
        self.pcr_product = VGroup(bar, ticks, plab)

    def _arrow_bar(self, x0: float, x1: float, y: float, direction: int, color: str) -> VGroup:
        """A primer: a bar with an arrow head at its 3′ end, in ``direction``."""
        h = self.pcr_h * 0.8
        bar = Rectangle(width=x1 - x0, height=h).move_to(np.array([(x0 + x1) / 2, y, 0]))
        bar.set_fill(color, opacity=0.9).set_stroke(width=0)
        tip = np.array([x1 + h * 0.7 if direction > 0 else x0 - h * 0.7, y, 0])
        base = np.array([x1 if direction > 0 else x0, y, 0])
        head = Polygon(tip, base + UP * h * 0.75, base + DOWN * h * 0.75).set_fill(color, opacity=1).set_stroke(width=0)
        return VGroup(bar, head)

    def _pcr_trace(self) -> None:
        """The temperature trace of three cycles: denature, anneal, extend."""
        p = self.plan.pcr
        area = self.trace_area
        lo, hi = 45.0, max(100.0, p.denature + 4)
        shown = min(3, p.cycles)
        ticks_y = [(p.anneal, f"{p.anneal:g}"), (p.extend, f"{p.extend:g}"), (p.denature, f"{p.denature:g}")]
        axes, to_point = plot_axes(self, area, (0.0, shown * 3.0), (lo, hi), "cycles", "°C", self.ink, self.dim_ink, self.tiny,
                                   [(3 * k + 1.5, str(k + 1)) for k in range(shown)], ticks_y)
        self.trace_axes = axes
        self.to_trace = to_point
        pts: list[np.ndarray] = [to_point(0.0, p.anneal)]
        self.cycle_paths: list[VMobject] = []
        for k in range(shown):
            x = 3.0 * k
            seg = [to_point(x, p.denature), to_point(x + 0.9, p.denature), to_point(x + 1.1, p.anneal), to_point(x + 1.9, p.anneal),
                   to_point(x + 2.1, p.extend), to_point(x + 2.9, p.extend), to_point(x + 3.0, p.denature if k < shown - 1 else p.extend)]
            path = VMobject().set_points_as_corners([pts[-1]] + seg).set_stroke(self.bad, width=3)
            self.cycle_paths.append(path)
            pts += seg
        marks = VGroup()
        for text, temp, dx, up in (("denature", p.denature, 0.5, -1), ("anneal", p.anneal, 1.55, 1), ("extend", p.extend, 2.5, 1)):
            t = self.markup(text, size=self.tiny, color=self.dim_ink)
            t.move_to(to_point(dx, temp) + UP * up * t.height * 0.85)
            if t.get_top()[1] > area.y1:
                t.shift(DOWN * (t.get_top()[1] - area.y1))
            marks.add(t)
        self.trace_marks = marks
        self.trace_group = VGroup(axes, *self.cycle_paths, marks)

    def _pcr_molecules(self) -> None:
        """The molecules after each cycle: a row per cycle of short bars, the ones of the product's
        length in the highlight colour."""
        p = self.plan.pcr
        area = self.mol_area
        shown = min(4, p.cycles)
        self.mol_shown = shown
        states = lab.pcr_strands(p, shown)
        rows: list[VGroup] = []
        size = self.tiny
        lab_w = max(self.markup(f"cycle {shown}", size=size).width, self.markup("start", size=size).width) + 0.15
        row_h = min(0.42, (area.height - 0.1) / (shown + 1))
        bar_h = row_h * 0.3
        x0 = area.x0 + lab_w + 0.1
        width = area.x1 - x0
        for k, mols in enumerate(states):
            y = area.y1 - row_h * (k + 0.5)
            name = "start" if k == 0 else f"cycle {k}"
            t = self.markup(name, size=size, color=self.dim_ink)
            t.move_to(np.array([area.x0 + lab_w / 2, y, 0]))
            parts: list[Mobject] = [t]
            n = len(mols)
            per = width / max(n, 1)
            for j, (a, b) in enumerate(mols):
                exact = (a.a, a.b) == (p.f_at, p.r_end) and (b.a, b.b) == (p.f_at, p.r_end)
                length = max(a.b - a.a, b.b - b.a) / len(p.template)
                w = min(per * 0.8, per * 0.8 * max(0.25, length))
                cx = x0 + per * (j + 0.5)
                bar = Rectangle(width=max(w, 0.03), height=bar_h).move_to(np.array([cx, y, 0]))
                color = self.hi if exact else self.dim_ink
                bar.set_fill(color, opacity=0.95 if exact else 0.5).set_stroke(width=0)
                parts.append(bar)
            count = self.markup(f"{len(mols)}", size=size * 0.9, color=self.dim_ink)
            rows.append(VGroup(*parts))
        self.mol_rows = rows
        self.mol_group = VGroup(*rows)

    # ----- the gel ---------------------------------------------------------------------------------

    def _build_gel(self) -> None:
        """The gel: wells at the top (cathode), lanes across, bands at their migration distances."""
        g = self.plan.gel
        area = self.main_area
        size = self.tiny
        n = len(g.lanes)
        lab_h = self.markup("ladder", size=size).height
        pole_h = self.markup("− cathode", size=size).height
        top = area.y1 - lab_h - 0.12
        bottom = area.y0 + pole_h + 0.3
        plate_w = min(area.width - 2.6, n * 1.5)
        x0 = area.center[0] - plate_w / 2 + 0.5
        self.gel_x0, self.gel_w = x0, plate_w
        self.gel_top, self.gel_bottom = top - 0.12, bottom
        plate = Rectangle(width=plate_w, height=self.gel_top - bottom)
        plate.move_to(np.array([area.center[0], (self.gel_top + bottom) / 2, 0]))
        plate.set_fill(self.dim_ink, opacity=0.1).set_stroke(self.dim_ink, width=2)
        self.lane_x = [x0 + plate_w * (k + 0.5) / n for k in range(n)]
        lane_w = plate_w / n * 0.62
        self.lane_w = lane_w
        wells = VGroup()
        labels = VGroup()
        for k, lane in enumerate(g.lanes):
            well = Rectangle(width=lane_w, height=0.1).move_to(np.array([self.lane_x[k], self.gel_top - 0.07, 0]))
            well.set_fill(self.bg_color(), opacity=1).set_stroke(self.dim_ink, width=1.5)
            wells.add(well)
            t = self.markup(lane.label, size=size, color=self.ink if not lane.ladder else self.dim_ink)
            if t.width > plate_w / n * 0.95:
                t.scale(plate_w / n * 0.95 / t.width)
            t.move_to(np.array([self.lane_x[k], top + t.height / 2, 0]))
            labels.add(t)
        minus = self.markup("− cathode", size=size, color=self.dim_ink)
        plus = self.markup("+ anode", size=size, color=self.dim_ink)
        minus.move_to(np.array([x0 - 0.1 - minus.width / 2, self.gel_top - 0.1, 0])) if x0 - minus.width - 0.2 > area.x0 else \
            minus.move_to(np.array([area.center[0], self.gel_top + 0.0, 0]))
        minus.move_to(np.array([max(area.x0 + minus.width / 2, x0 - 0.15 - minus.width / 2), self.gel_top - 0.12, 0]))
        plus.move_to(np.array([max(area.x0 + plus.width / 2, x0 - 0.15 - plus.width / 2), bottom + 0.05 + plus.height / 2, 0]))
        arrow = Arrow(np.array([x0 - 0.3, self.gel_top - 0.3, 0]), np.array([x0 - 0.3, bottom + 0.3, 0]), buff=0,
                      stroke_width=3, max_tip_length_to_length_ratio=0.08).set_color(self.dim_ink)
        if x0 - 0.45 < area.x0:
            arrow = VGroup()
        self.gel_plate = VGroup(plate, wells, labels, minus, plus, arrow)
        self.gel_bands: dict[int, list[tuple[Mobject, float]]] = {}
        for k, lane in enumerate(g.lanes):
            items = []
            for s in lane.sizes:
                d = lab.migration(s, g.agarose)
                y = self.gel_top - 0.12 - d * (self.gel_top - 0.12 - bottom - 0.1)
                band = Rectangle(width=lane_w, height=0.07).move_to(np.array([self.lane_x[k], y, 0]))
                color = self.dim_ink if lane.ladder else self.hi
                band.set_fill(color, opacity=0.95 if not lane.ladder else 0.7).set_stroke(width=0)
                items.append((band, s))
            self.gel_bands[k] = items
        self.ladder_labels = VGroup()
        last_y = None
        for band, s in self.gel_bands[0]:
            y = band.get_center()[1]
            t = self.markup(f"{s:g}", size=self.tiny, color=self.dim_ink)
            if last_y is not None and abs(y - last_y) < t.height * 1.1:
                continue                      # the ladder's close bands are not all labelled
            last_y = y
            t.next_to(band, LEFT, buff=0.06)
            if t.get_left()[0] < area.x0:
                t.next_to(band, RIGHT, buff=0.06)
            self.ladder_labels.add(t)
        self.gel_group = VGroup(self.gel_plate, self.ladder_labels, *[b for items in self.gel_bands.values() for b, _ in items])

    def bg_color(self) -> str:
        return self.theme.background

    def _build_sanger(self) -> None:
        """The template with the primer, the fragments sorted by length, and the trace."""
        s = self.plan.sanger
        area = self.main_area
        rows = area.rows([0.3, 0.7], gap=0.25)
        self.seq_area, self.trace_area = rows
        u = min((self.seq_area.width - 0.6) / (len(s.read) + 2), 0.5, self.seq_area.height * 0.4)
        self.u = u
        self.letters = Letters(self, u * 0.6, self.small)
        y = self.seq_area.y1 - u * 0.8
        x0 = self.seq_area.center[0] - len(s.read) * u / 2
        self.sanger_x0 = x0
        tiles = []
        for k, b in enumerate(s.read):
            t = base_tile(self.letters, b, u).move_to(np.array([x0 + (k + 0.5) * u, y - u * 1.3, 0]))
            tiles.append(t)
        self.template_tiles = tiles
        temp = []
        for k, b in enumerate(s.template):
            t = self.markup(b, size=self.tiny, color=self.dim_ink)
            t.move_to(np.array([x0 + (k + 0.5) * u, y, 0]))
            temp.append(t)
        ends = VGroup(self.markup("3′", size=self.tiny, color=self.dim_ink).move_to(np.array([x0 - u * 0.6, y, 0])),
                      self.markup("5′", size=self.tiny, color=self.dim_ink).move_to(np.array([x0 + (len(s.read) + 0.6) * u, y, 0])),
                      self.markup("5′", size=self.tiny, color=self.dim_ink).move_to(np.array([x0 - u * 0.6, y - u * 1.3, 0])),
                      self.markup("3′", size=self.tiny, color=self.dim_ink).move_to(np.array([x0 + (len(s.read) + 0.6) * u, y - u * 1.3, 0])))
        cap = self.markup("template strand 3′→5′, new strand 5′→3′", size=self.tiny, color=self.dim_ink)
        cap.move_to(np.array([self.seq_area.x0 + cap.width / 2, y - u * 2.2 - cap.height / 2, 0]))
        self.sanger_seq = VGroup(*temp, *tiles, ends, cap)
        self._sanger_trace()

    def _sanger_trace(self) -> None:
        """Peaks: one per base, in the base's colour, half height at a heterozygous position."""
        s = self.plan.sanger
        area = self.trace_area
        call_h = self.markup("<b>A</b>", size=self.tiny).height
        base_y = area.y0 + call_h * 1.6
        top = area.y1 - 0.1
        n = len(s.read)
        x0 = area.x0 + 0.3
        step = (area.width - 0.6) / n
        self.peak_step, self.peak_x0, self.peak_base = step, x0, base_y
        axis = Line(np.array([x0 - 0.1, base_y, 0]), np.array([x0 + n * step + 0.1, base_y, 0])).set_stroke(self.dim_ink, width=2)
        peaks = VGroup()
        calls = VGroup()
        self.peak_groups: list[VGroup] = []
        for k, b in enumerate(s.read):
            cx = x0 + (k + 0.5) * step
            height = (top - base_y) * s.heights[k]
            group = VGroup()
            bases = [(b, 1.0)] if k not in s.het else [(b, 0.55), (s.het[k], 0.55)]
            for j, (base, scale) in enumerate(bases):
                h = height * scale
                dx = step * (0.12 * (j - (len(bases) - 1) / 2))
                curve = VMobject().set_points_smoothly([np.array([cx - step * 0.42 + dx, base_y, 0]),
                                                        np.array([cx - step * 0.18 + dx, base_y + h * 0.75, 0]),
                                                        np.array([cx + dx, base_y + h, 0]),
                                                        np.array([cx + step * 0.18 + dx, base_y + h * 0.75, 0]),
                                                        np.array([cx + step * 0.42 + dx, base_y, 0])])
                curve.set_stroke(base_ink(self.theme.background, base), width=3)
                group.add(curve)
            t = self.markup(f"<b>{s.calls[k]}</b>", size=self.tiny,
                            color=self.hi if k in s.het else base_ink(self.theme.background, s.calls[k]))
            t.move_to(np.array([cx, base_y - 0.08 - t.height / 2, 0]))
            calls.add(t)
            peaks.add(group)
            self.peak_groups.append(VGroup(group, t))
        self.trace_group = VGroup(axis, peaks, calls)
        self.trace_axis = axis

    def _build_ngs(self) -> None:
        """The reference, the reads stacked under it and the coverage bars."""
        n = self.plan.ngs
        area = self.main_area
        u = min((area.width - 0.6) / (len(n.reference) + 1), 0.42)
        self.u = u
        h_min = self.markup("<b>A</b>", size=readable_size() * 1.02).height
        self.letters = Letters(self, max(u * 0.58, h_min), self.small)
        x0 = area.center[0] - len(n.reference) * u / 2
        self.ngs_x0 = x0
        y_ref = area.y1 - u * 0.7
        self.ngs_ref = VGroup(*[base_tile(self.letters, b, u).move_to(np.array([x0 + (k + 0.5) * u, y_ref, 0]))
                                for k, b in enumerate(n.reference)])
        rows = lab.pack_rows(n.reads)
        n_rows = max(rows) + 1
        cov_h = min(0.9, area.height * 0.22)
        room = area.height - u * 1.6 - cov_h - 0.5
        row_h = min(u * 0.52, room / max(1, n_rows))
        self.read_mobs: list[Mobject] = []
        y0 = y_ref - u * 1.1
        for read, r in zip(n.reads, rows):
            y = y0 - (r + 0.5) * row_h
            bar = Rectangle(width=len(read.seq) * u * 0.96, height=row_h * 0.62)
            bar.move_to(np.array([x0 + (read.start + len(read.seq) / 2) * u, y, 0]))
            color = self.hi if read.alt else self.cold
            bar.set_fill(color, opacity=0.45).set_stroke(color, width=1)
            parts: list[Mobject] = [bar]
            i = n.position
            if read.start <= i < read.start + len(read.seq):
                base = read.seq[i - read.start]
                dot = Rectangle(width=u * 0.9, height=row_h * 0.62).move_to(np.array([x0 + (i + 0.5) * u, y, 0]))
                dot.set_fill(BASE_HUE(base), opacity=0.95).set_stroke(width=0)
                parts.append(dot)
            for k in read.errors:
                if read.start + k == i:
                    continue
                err = Rectangle(width=u * 0.5, height=row_h * 0.4).move_to(np.array([x0 + (read.start + k + 0.5) * u, y, 0]))
                err.set_fill(self.bad, opacity=0.8).set_stroke(width=0)
                parts.append(err)
            self.read_mobs.append(VGroup(*parts))
        self.ngs_reads = VGroup(*self.read_mobs)
        bottom = y0 - n_rows * row_h - 0.25
        self.ngs_cov = VGroup()
        top_cov = max(n.depth) or 1
        for k, d in enumerate(n.depth):
            h = cov_h * d / top_cov
            bar = Rectangle(width=u * 0.9, height=max(h, 0.01))
            bar.move_to(np.array([x0 + (k + 0.5) * u, bottom - cov_h + h / 2, 0]))
            bar.set_fill(self.cold, opacity=0.5).set_stroke(width=0)
            self.ngs_cov.add(bar)
        cov_lab = self.markup(f"coverage (max {top_cov}×)", size=self.tiny, color=self.dim_ink)
        cov_lab.move_to(np.array([area.x0 + cov_lab.width / 2, bottom - cov_h - 0.02 - cov_lab.height / 2, 0]))
        self.ngs_cov.add(cov_lab)
        x = x0 + (n.position + 0.5) * u
        self.ngs_line = DashedLine(np.array([x, y_ref - u * 0.6, 0]), np.array([x, bottom - cov_h, 0]), dash_length=0.08)
        self.ngs_line.set_stroke(self.hi, width=2)

    # ----- targets and steps -----------------------------------------------------------------------

    def _register(self) -> None:
        p = self.params
        title = self.title_mob
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        getattr(self, f"_targets_{p.method}")()
        held: set[str] = set()
        for use in self.action_uses("reveal"):
            held.update(use.config.targets())
        manual = bool(self.action_uses("run")) or bool(held & self._late_targets())

        def first() -> list[Animation]:
            anims: list[Animation] = [FadeIn(title)] if title is not None else []
            if not held & {"template", "gel", "sequence", "reference"}:
                anims += self.run_step("setup")
            return anims

        steps: list[Any] = [first]
        if not manual:
            steps += [lambda s=s: self.run_step(s) for s in self.steps[1:]]
        self.reveal(steps, fraction=0.88, cap=STEP_SECONDS + 0.8)
        self.finish()

    def _late_targets(self) -> set[str]:
        return {"trace", "counts", "sizes", "fragments", "chromatogram", "reads", "coverage", "call", "product", "primers"}

    def _targets_pcr(self) -> None:
        self.target("template", self.pcr_template, entrance=lambda: self.run_step("setup"))
        self.target("primers", self.pcr_primers, entrance=lambda: self.run_step("setup"))
        self.target("product", self.pcr_product, entrance=lambda: self.run_step("setup"))
        self.target("trace", self.trace_group, entrance=lambda: self.run_step("cycle"))
        for k in range(self.plan.pcr.cycles):
            mob = self.cycle_paths[k] if k < len(self.cycle_paths) else self.trace_group
            self.target(f"cycle:{k + 1}", mob, entrance=lambda: self.run_step("cycle"))
        self.target("counts", self.mol_group, entrance=lambda: self.run_step("count"))

    def _targets_gel(self) -> None:
        self.target("gel", self.gel_plate, entrance=lambda: self.run_step("setup"))
        self.target("ladder", VGroup(*[b for b, _ in self.gel_bands[0]], self.ladder_labels), entrance=lambda: self.run_step("run"))
        for k, lane in enumerate(self.plan.gel.lanes[1:], start=1):
            self.target(f"lane:{lane.label}", VGroup(*[b for b, _ in self.gel_bands[k]]), entrance=lambda: self.run_step("run"))
        self.target("sizes", self.gel_group, entrance=lambda: self.run_step("read"))

    def _targets_sanger(self) -> None:
        self.target("sequence", self.sanger_seq, entrance=lambda: self.run_step("setup"))
        self.target("fragments", self.sanger_seq, entrance=lambda: self.run_step("separate"))
        self.target("chromatogram", self.trace_group, entrance=lambda: self.run_step("trace"))

    def _targets_ngs(self) -> None:
        self.target("reference", self.ngs_ref, entrance=lambda: self.run_step("setup"))
        self.target("reads", self.ngs_reads, entrance=lambda: self.run_step("align"))
        self.target("coverage", self.ngs_cov, entrance=lambda: self.run_step("align"))
        self.target("call", self.ngs_line, entrance=lambda: self.run_step("call"))

    def step_seconds(self, name: str) -> float:
        need = [s for s in self.steps[:self.steps.index(name) + 1] if s not in self.done]
        return max(1.0, STEP_SECONDS * len(need))

    def run_step(self, name: str) -> list[Animation]:
        if name in self.done:
            return []
        anims: list[Animation] = []
        for before in self.steps[:self.steps.index(name)]:
            if before not in self.done:
                anims += self.run_step(before)
        self.done.add(name)
        part = getattr(self, f"_step_{self.params.method}_{name}")()
        return [Succession(*anims, *part)] if anims else part

    # ----- PCR steps -------------------------------------------------------------------------------

    def _step_pcr_setup(self) -> list[Animation]:
        p = self.plan.pcr
        lines = [f"the primers bind {p.product} bp apart: the forward primer repeats the top strand, the reverse primer is the reverse "
                 f"complement of the top strand downstream", *p.notes,
                 f"denature {p.denature:g} °C · anneal {p.anneal:g} °C · extend {p.extend:g} °C (Taq, ~1 kb per minute: "
                 f"{p.extension_seconds:.0f} s here)"]
        return [Succession(FadeIn(self.pcr_template), AnimationGroup(FadeIn(self.pcr_primers, shift=UP * 0.06)),
                           AnimationGroup(FadeIn(self.pcr_product), *self._swap(self._card(lines, "The reaction"))))]

    def _step_pcr_cycle(self) -> list[Animation]:
        p = self.plan.pcr
        lines = [f"each cycle: the strands separate at {p.denature:g} °C, the primers anneal at {p.anneal:g} °C and Taq polymerase "
                 f"extends them at {p.extend:g} °C",
                 "every strand is copied, so the number of molecules doubles each cycle"]
        anims: list[Animation] = [FadeIn(self.trace_axes)]
        for path in self.cycle_paths:
            anims.append(Create(path))
        anims.append(AnimationGroup(FadeIn(self.trace_marks), *self._swap(self._card(lines, "The cycle"))))
        return [Succession(*anims)]

    def _step_pcr_count(self) -> list[Animation]:
        p = self.plan.pcr
        n = p.cycles
        all_n, exact = p.counts(n)
        lines = [f"from one template molecule: 2ⁿ = {all_n:,} molecules after {n} cycles".replace(",", " "),
                 f"the first molecules of exactly {p.product} bp appear in cycle 3; after n cycles there are 2ⁿ − 2n of them "
                 f"({exact:,} here)".replace(",", " "),
                 "the rest are longer strands that start at a primer and run to the end of their template"]
        rows = [LaggedStart(*[FadeIn(m, shift=RIGHT * 0.06) for m in row], lag_ratio=0.05) for row in self.mol_rows]
        return [Succession(*rows, AnimationGroup(*self._swap(self._card(lines, "The copies"))))]

    # ----- gel steps -------------------------------------------------------------------------------

    def _step_gel_setup(self) -> list[Animation]:
        g = self.plan.gel
        lo, hi = lab.resolving_range(g.agarose)
        lines = [f"a {g.agarose:g} % agarose gel resolves about {lo:.0f}–{hi:.0f} bp",
                 "DNA's backbone is negatively charged: it runs from the wells at the cathode (−) to the anode (+)"]
        return [AnimationGroup(FadeIn(self.gel_plate), *self._swap(self._card(lines, "The gel")))]

    def _step_gel_run(self) -> list[Animation]:
        """The bands move from the wells to their distances: small fragments run furthest."""
        anims: list[Animation] = []
        moving: list[Animation] = []
        for k, items in self.gel_bands.items():
            for band, _ in items:
                home = band.get_center()
                band.move_to(np.array([home[0], self.gel_top - 0.07, 0]))
                moving.append(band.animate.move_to(home))
                self.add(band)
        anims.append(AnimationGroup(*moving, run_time=1.0))
        anims.append(FadeIn(self.ladder_labels))
        lines = ["the distance is linear in log₁₀ of the size within the gel's range: small fragments run furthest",
                 "the ladder's known sizes turn a distance into a size"]
        anims.append(AnimationGroup(*self._swap(self._card(lines, "The run"))))
        return [Succession(*anims)]

    def _step_gel_read(self) -> list[Animation]:
        """A band's size read off the ladder, with a dashed line to the ladder."""
        g = self.plan.gel
        marks: list[Mobject] = []
        lines: list[str] = []
        led: set[float] = set()          # one leader line per size (the leftmost lane that has it)
        for k, lane in enumerate(g.lanes):
            if lane.ladder:
                continue
            for band, s in self.gel_bands[k]:
                read = lab.size_from_distance(lab.migration(s, g.agarose), g.ladder, g.agarose)
                t = self.markup(f"{read:.0f} bp", size=self.tiny, color=self.hi)
                t.next_to(band, RIGHT, buff=0.08)
                if t.get_right()[0] > self.main_area.x1:
                    t.next_to(band, LEFT, buff=0.08)
                marks.append(t)
                if s not in led:
                    led.add(s)
                    line = DashedLine(np.array([self.lane_x[0], band.get_center()[1], 0]), band.get_left(), dash_length=0.06)
                    marks.append(line.set_stroke(self.hi, width=1.5))
            lines.append(f"{lane.label}: " + ", ".join(f"{s:g} bp" for s in lane.sizes))
        lines += list(g.notes)
        return [Succession(AnimationGroup(*[FadeIn(m) for m in marks]), AnimationGroup(*self._swap(self._card(lines, "Sizes"))))]

    # ----- Sanger steps -----------------------------------------------------------------------------

    def _step_sanger_setup(self) -> list[Animation]:
        s = self.plan.sanger
        lines = ["a primer on the template is extended with the four dNTPs and a little of each fluorescent ddNTP",
                 "a ddNTP has no 3′-OH: wherever one is added the chain stops, so every length occurs"]
        return [AnimationGroup(FadeIn(self.sanger_seq), *self._swap(self._card(lines, "Chain termination")))]

    def _step_sanger_separate(self) -> list[Animation]:
        """The fragments: each tile flashes in turn (one fragment per position, sorted by length)."""
        lines = ["capillary electrophoresis sorts the fragments by length, one base apart",
                 "the colour of the last base — its ddNTP — is read as each fragment passes the detector"]
        flashes = [Indicate(t, color=self.hi, scale_factor=1.15) for t in self.template_tiles]
        return [Succession(LaggedStart(*flashes, lag_ratio=0.12), AnimationGroup(*self._swap(self._card(lines, "Separation"))))]

    def _step_sanger_trace(self) -> list[Animation]:
        s = self.plan.sanger
        lines = [f"the trace reads 5′→3′: {s.calls}"]
        if s.het:
            pos = ", ".join(f"position {i + 1} ({s.read[i]}/{s.het[i]}, {s.calls[i]})" for i in sorted(s.het))
            lines.append(f"two peaks of about half height at {pos}: a heterozygous site")
        else:
            lines.append("one peak per position: every molecule has the same base there")
        anims = [FadeIn(self.trace_axis), LaggedStart(*[FadeIn(g, shift=UP * 0.05) for g in self.peak_groups], lag_ratio=0.08)]
        return [Succession(*anims, AnimationGroup(*self._swap(self._card(lines, "The chromatogram"))))]

    # ----- NGS steps --------------------------------------------------------------------------------

    def _step_ngs_setup(self) -> list[Animation]:
        n = self.plan.ngs
        lines = [f"a reference of {len(n.reference)} bp; the sample is sequenced as short reads of {n.read_length} bp",
                 "each read is aligned to the reference where it matches best"]
        return [AnimationGroup(FadeIn(self.ngs_ref), *self._swap(self._card(lines, "Short reads")))]

    def _step_ngs_align(self) -> list[Animation]:
        n = self.plan.ngs
        lines = [f"{len(n.reads)} reads; coverage at the site {n.depth[n.position]}×",
                 "a base that differs in one read only is usually a sequencing error (red): real variants are in many reads"]
        return [Succession(LaggedStart(*[FadeIn(m, shift=LEFT * 0.08) for m in self.read_mobs], lag_ratio=0.03),
                           AnimationGroup(FadeIn(self.ngs_cov), *self._swap(self._card(lines, "Alignment"))))]

    def _step_ngs_call(self) -> list[Animation]:
        n = self.plan.ngs
        d = n.depth[n.position]
        pct = n.vaf * 100
        lines = [f"position {n.position + 1}: {n.ref} → {n.alt} in {n.alt_reads} of {d} reads ({pct:.0f} %)"]
        if n.call == "heterozygous":
            lines.append("about half the reads carry the alternative allele: heterozygous (one of the two copies)")
        elif n.call == "homozygous":
            lines.append("nearly every read carries it: homozygous")
        elif n.call == "none":
            lines.append("too few reads carry it: no variant called (the reference allele)")
        else:
            lines.append("fewer than 10 reads cover the site: too little to call")
        return [Succession(Create(self.ngs_line), AnimationGroup(*self._swap(self._card(lines, "The variant call"))))]
