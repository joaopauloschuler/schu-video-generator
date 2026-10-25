"""``crispr``: the Cas9 editing scene (DESIGN.md §96.14). The target DNA is drawn flat (top strand
5′→3′ over its partner, every base), with the PAM and protospacer the model found; the enzyme with
its sgRNA binds, the spacer pairs with the target strand (R-loop), both strands break 3 bp 5′ of
the PAM, and the break is resolved by NHEJ (an indel) or HDR (a donor's edit), written in HGVS when
the target is a coding sequence. The model is ``vidgen.genetics.crispr``; the actions are in
``scenes/molecular_actions.py``."""

from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import small_size, text_block
from .molecular_draw import Letters, base_tile, esc

cr = genetics.crispr
hg = genetics.hgvs

#: Seconds per step.
SCAN_SECONDS, CLEAVE_SECONDS, REPAIR_SECONDS = 3.0, 1.6, 2.8
STEPS = ("dna", "scan", "cleave", "repair")


def _complement(b: str) -> str:
    return {"A": "T", "T": "A", "G": "C", "C": "G"}[b]


@scene("crispr")
class CrisprScene(NarratedScene):
    """CRISPR–Cas9 editing of a target sequence: both DNA strands with every base, the PAM
    (5′-NGG-3′ for SpCas9, NNGRRT for SaCas9) right after the protospacer's 3′ end on the
    non-target strand, the sgRNA's 20-nt spacer paired with the target strand (R-loop), the blunt
    double-strand break 3 bp upstream of the PAM, and its outcome: NHEJ with a small indel (a
    frameshift knockout on a coding sequence) or HDR copying a donor's edit — both written in
    HGVS with their protein change when ``coding_first`` says where the reading frame is. vidgen
    finds every guide with a PAM in the target; a spacer without a PAM, with another enzyme's PAM
    or of the wrong length is refused with the guides that would work.

    Action targets: ``title``, ``dna``, ``pam``, ``protospacer``, ``cas9``, ``sgrna``, ``cut``,
    ``repair``, ``card``."""

    outro = 0.5
    target_patterns = ("title", "dna", "pam", "protospacer", "cas9", "sgrna", "cut", "repair", "card")
    #: The actions scan, cleave and repair act on this scene type.
    crispr_actions = True
    mid_still_actions = frozenset({"scan", "cleave", "repair"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        target: str = "GACTGCATCAGCTGAAGGTCACCATGGTGCATCTGACTCCTGAGGAGAAG"
        """The target DNA's top strand 5′→3′ (26–80 bp)."""
        cas: Literal["SpCas9", "SaCas9"] = "SpCas9"
        """The nuclease: SpCas9 (PAM NGG, 20-nt spacer) or SaCas9 (PAM NNGRRT, 21–23 nt)."""
        spacer: str | None = None
        """The sgRNA's spacer 5′→3′ (U or T): it repeats the protospacer on the non-target strand, and its PAM is checked. Default: a guide vidgen finds."""
        guide: int | None = None
        """Instead of spacer: the n-th guide vidgen finds in the target (by cut position, from 1)."""
        repair: Literal["nhej", "hdr", "none"] = "nhej"
        """What follows the break: nhej (a small indel), hdr (a donor template's edit) or none (the break only)."""
        indel: int | None = None
        """NHEJ: the indel at the cut (+1 default, the commonest; −4, +2…)."""
        edit: str | None = None
        """HDR: the donor's change, at target positions (25A>T, 24_26del) or in c. numbers with coding_first."""
        coding_first: int | None = None
        """The c. number of the target's first base when the top strand is coding: outcomes in HGVS with their protein change."""
        symbol: str | None = None
        """The gene's symbol (italic), for the card."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def spec(self) -> dict[str, Any]:
            data: dict[str, Any] = {"target": self.target, "cas": self.cas, "repair": self.repair}
            for key in ("spacer", "guide", "indel", "edit", "coding_first", "symbol"):
                if getattr(self, key) is not None:
                    data[key] = getattr(self, key)
            return data

        def plan(self) -> Any:
            return cr.plan_crispr(self.spec())

        @model_validator(mode="after")
        def _check(self) -> "CrisprScene.Params":
            try:
                self.plan()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        names = ["title"] if params.title else []
        names += ["dna", "pam", "protospacer", "cas9", "sgrna", "cut"]
        if params.repair != "none":
            names.append("repair")
        return names + ["card"]

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.plan = p.plan()
        self.ink, self.dim_ink = th.color("text"), th.color("dim")
        self.hi, self.bad, self.good = th.color("highlight"), th.color("accent"), th.color("tertiary")
        self.cas_color, self.rna_color = th.color("primary"), th.color("secondary")
        self.small = small_size(self, p.size)
        self.tiny = max(readable_size() * 1.02, self.small * 0.85)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.25)
        self.title_mob = title
        self.done: set[str] = set()
        # The picture is drawn from the strand that carries the PAM (the non-target strand): with a
        # guide on the bottom strand the same DNA is shown as its reverse complement, so the
        # protospacer and PAM always read 5′→3′ along the top row. Display indices are the model's
        # target indices mapped by _at / _range; HGVS and positions on the cards stay in the
        # target's own numbering.
        g = self.plan.guide
        self.flip = g.strand == "-"
        self.disp = reverse_complement(self.plan.target) if self.flip else self.plan.target
        self.g_start, self.g_end = self._range(g.start, g.end)
        self.g_pam0, self.g_pam1 = self._range(g.pam_start, g.pam_end)
        self.g_cut = len(self.disp) - g.cut if self.flip else g.cut
        self._layout(body)
        self._build_dna()
        self._build_enzyme()
        self.card_mob: Mobject | None = None
        self.card_holder = VGroup()       # the card on screen now (an action target)
        self._register()

    def _at(self, i: int, length: int | None = None) -> int:
        """A target index as a display index."""
        n = length if length is not None else len(self.plan.target)
        return n - 1 - i if self.flip else i

    def _range(self, a: int, b: int, length: int | None = None) -> tuple[int, int]:
        """A target range ``[a, b)`` as a display range."""
        n = length if length is not None else len(self.plan.target)
        return (n - b, n - a) if self.flip else (a, b)

    def _layout(self, body: Any) -> None:
        n = len(self.disp)
        u_min = self.markup("<b>A</b>", size=readable_size() * 1.02).height / 0.6
        lo, hi = min(self.g_start, self.g_pam0), max(self.g_end, self.g_pam1)
        pad = 2.6
        fit = max(hi - lo + 2, int(body.width / u_min - pad))
        if n <= fit:
            a, b = 0, n
        else:
            a = max(0, min(lo - (fit - (hi - lo)) // 2, n - fit))
            b = min(n, a + fit)
        self.view = (a, b)
        self.u = u = max(u_min, min(body.width / ((b - a) + pad), 0.5))
        self.letters = Letters(self, u * 0.6, self.small)
        self.lab_h = self.markup("5′", size=self.small).height
        dna_h = max(u * 9.5, body.height * (0.52 if not self.is_portrait else 0.4))
        self.dna_area = Region(body.x0, body.y1 - dna_h, body.x1, body.y1)
        self.card_area = Region(body.x0, body.y0, body.x1, self.dna_area.y0 - 0.3)
        mid = self.dna_area.y0 + dna_h * 0.5
        self.y_top, self.y_bot = mid + u * 0.62, mid - u * 0.62
        self.x0 = body.center[0] - (b - a) * u / 2

    def x_of(self, i: float) -> float:
        return self.x0 + (i - self.view[0] + 0.5) * self.u

    def _ends(self, y_top: float, y_bot: float, left: float, right: float) -> VGroup:
        s = self.tiny
        self.end_left: list[Mobject] = []
        self.end_right: list[Mobject] = []
        for y, l, r in ((y_top, "5′", "3′"), (y_bot, "3′", "5′")):
            a = self.markup(l, size=s, color=self.dim_ink)
            a.move_to(np.array([left - self.u * 0.4 - a.width / 2, y, 0]))
            b = self.markup(r, size=s, color=self.dim_ink)
            b.move_to(np.array([right + self.u * 0.4 + b.width / 2, y, 0]))
            self.end_left.append(a)
            self.end_right.append(b)
        return VGroup(*self.end_left, *self.end_right)

    def _build_dna(self) -> None:
        plan = self.plan
        g = plan.guide
        u = self.u
        a, b = self.view
        seq = self.disp
        self.top = {i: base_tile(self.letters, seq[i], u).move_to(np.array([self.x_of(i), self.y_top, 0])) for i in range(a, b)}
        self.bot = {i: base_tile(self.letters, _complement(seq[i]), u).move_to(np.array([self.x_of(i), self.y_bot, 0])) for i in range(a, b)}
        left, right = self.x_of(a) - u / 2, self.x_of(b - 1) + u / 2
        self.ends = self._ends(self.y_top, self.y_bot, left, right)
        self.more = VGroup()
        mid_y = (self.y_top + self.y_bot) / 2
        if a > 0:
            dots = self.markup("…", size=self.small, color=self.dim_ink)
            x = max(self.dna_area.x0 + dots.width / 2, left - u * 1.5 - dots.width / 2)
            self.more.add(dots.move_to(np.array([x, mid_y, 0])))
        if b < len(seq):
            dots = self.markup("…", size=self.small, color=self.dim_ink)
            x = min(self.dna_area.x1 - dots.width / 2, right + u * 1.5 + dots.width / 2)
            self.more.add(dots.move_to(np.array([x, mid_y, 0])))
        self.dna = VGroup(*self.top.values(), *self.bot.values(), self.ends, self.more)
        self.nt_tiles, self.t_tiles = self.top, self.bot      # the top row carries the PAM (see construct)
        pam_tiles = VGroup(*[self.top[i] for i in range(self.g_pam0, self.g_pam1) if i in self.top])
        self.pam_box = SurroundingRectangle(pam_tiles, buff=u * 0.08, corner_radius=u * 0.15).set_stroke(self.bad, width=4)
        # the sgRNA comes in above, so the marks go under the DNA
        lab = self.markup(f"<b>PAM</b> {g.pam}", size=self.small, color=self.bad)
        lane = self.y_bot - u * 0.62 - 0.22
        lab.move_to(np.array([pam_tiles.get_center()[0], lane - lab.height / 2, 0]))
        lab.set_x(min(lab.get_x(), self.dna_area.x1 - lab.width / 2))
        self.pam_mark = VGroup(self.pam_box, lab)
        ps = [self.top[i] for i in range(self.g_start, self.g_end) if i in self.top]
        x0, x1 = ps[0].get_left()[0], ps[-1].get_right()[0]
        yb = lab.get_bottom()[1] - 0.12
        bracket = VGroup(Line(np.array([x0, yb, 0]), np.array([x1, yb, 0])), Line(np.array([x0, yb, 0]), np.array([x0, yb + 0.1, 0])),
                         Line(np.array([x1, yb, 0]), np.array([x1, yb + 0.1, 0]))).set_stroke(self.hi, width=2.5)
        plab = self.markup(f"protospacer ({len(g.spacer)} nt)", size=self.tiny, color=self.hi)
        plab.next_to(bracket, DOWN, buff=0.06)
        self.proto_mark = VGroup(bracket, plab)

    def _build_enzyme(self) -> None:
        """The enzyme as two lobes over the protospacer and PAM, and the sgRNA: the spacer's bases
        in a row over the target strand's and a scaffold hairpin beyond its 3′ end."""
        plan = self.plan
        g = plan.guide
        u = self.u
        lo = max(min(self.g_start, self.g_pam0), self.view[0])
        hi = min(max(self.g_end, self.g_pam1), self.view[1])
        xa, xb = self.x_of(lo) - u * 1.1, self.x_of(hi - 1) + u * 1.1
        d = 1
        yc = (self.y_top + self.y_bot) / 2
        w, h = xb - xa, u * 5.6
        near = Ellipse(width=w * 0.60, height=h)
        far = Ellipse(width=w * 0.52, height=h * 0.82)
        near.move_to(np.array([xa + w * 0.32, yc, 0]))
        far.move_to(np.array([xa + w * 0.72, yc, 0]))
        shape = Union(near, far).set_fill(self.cas_color, opacity=0.14).set_stroke(self.cas_color, width=3)
        shape.set_z_index(-2)
        name = self.markup(f"<b>{plan.cas.name}</b>", size=self.small, color=self.cas_color)
        name.move_to(np.array([self.dna_area.x0 + name.width / 2, self.dna_area.y1 - name.height / 2, 0]))
        self.cas_body = VGroup(shape, name)
        self.cas_h = h
        y_sp = self.y_top
        self.spacer_tiles: dict[int, VGroup] = {}
        for k, base in enumerate(g.rna):
            i = self.g_start + k
            if not self.view[0] <= i < self.view[1]:
                continue
            t = base_tile(self.letters, base, u).move_to(np.array([self.x_of(i), y_sp, 0]))
            t[0].set_stroke(self.rna_color, width=2.5)
            self.spacer_tiles[i] = t
        end_i = self.g_end - 1
        x_end = self.x_of(end_i) + d * u * 0.5
        hx = d * u
        pts = [np.array([x_end, y_sp, 0]), np.array([x_end + hx * 0.6, y_sp + d * u * 0.4, 0]),
               np.array([x_end + hx * 0.6, y_sp + d * u * 1.4, 0]), np.array([x_end + hx * 0.15, y_sp + d * u * 1.9, 0]),
               np.array([x_end + hx * 1.05, y_sp + d * u * 1.9, 0]), np.array([x_end + hx * 0.9, y_sp + d * u * 1.3, 0]),
               np.array([x_end + hx * 0.9, y_sp + d * u * 0.5, 0])]
        scaffold = VMobject().set_points_smoothly(pts).set_stroke(self.rna_color, width=4)
        sglab = self.markup("sgRNA: spacer + scaffold", size=self.tiny, color=self.rna_color)
        sglab.move_to(np.array([self.x_of((self.g_start + self.g_end) / 2), y_sp + d * (u * 2.4 + sglab.height / 2), 0]))
        sglab.set_x(min(max(sglab.get_x(), self.dna_area.x0 + sglab.width / 2), self.dna_area.x1 - sglab.width / 2))
        # no 5′ / 3′ marks on the spacer row: the DNA's are right beside it (the card writes the
        # spacer 5′→3′)
        self.sgrna = VGroup(*self.spacer_tiles.values(), scaffold, sglab)
        self.complex = VGroup(self.cas_body, self.sgrna)
        self.cut_x = self.x_of(self.g_cut) - u / 2

    # ----- cards ---------------------------------------------------------------------------------

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
        title = self.markup(f"<b>{head}</b>", size=size * 1.15, color=self.ink)
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
        self.card_holder.remove(*self.card_holder.submobjects)
        self.card_holder.add(card)
        anims.append(FadeIn(card, shift=UP * 0.06))
        return [AnimationGroup(*anims, lag_ratio=0.4)]

    # ----- targets and steps ---------------------------------------------------------------------

    def _register(self) -> None:
        p = self.params
        title = self.title_mob
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        self.target("dna", self.dna, entrance=lambda: self.run_step("dna"))
        self.target("pam", self.pam_mark, entrance=lambda: [Create(self.pam_box), FadeIn(self.pam_mark[1])])
        self.target("protospacer", self.proto_mark)
        self.target("cas9", self.cas_body, entrance=lambda: self.run_step("scan"))
        self.target("sgrna", self.sgrna, entrance=lambda: self.run_step("scan"))
        cut = Line(np.array([self.cut_x, self.y_top + self.u * 0.6, 0]), np.array([self.cut_x, self.y_bot - self.u * 0.6, 0]))
        self.cut_mark = cut.set_stroke(self.bad, width=4)
        self.target("cut", self.cut_mark, entrance=lambda: self.run_step("cleave"))
        if p.repair != "none":
            self.target("repair", self.dna, entrance=lambda: self.run_step("repair"))
        self.target("card", self.card_holder)
        held: set[str] = set()
        for use in self.action_uses("reveal"):
            held.update(use.config.targets())
        manual = any(self.action_uses(a) for a in ("scan", "cleave", "repair")) or bool(held & {"cas9", "sgrna", "cut", "repair"})

        def first() -> list[Animation]:
            anims: list[Animation] = [FadeIn(title)] if title is not None else []
            if "dna" not in held:
                anims += self.run_step("dna")
            return anims

        steps: list[Any] = [first]
        if not manual:
            steps += [lambda: self.run_step("scan"), lambda: self.run_step("cleave")]
            if p.repair != "none":
                steps.append(lambda: self.run_step("repair"))
        self.reveal(steps, fraction=0.88, cap=SCAN_SECONDS + 0.8)
        self.finish()

    def step_seconds(self, name: str) -> float:
        times = {"dna": 0.0, "scan": SCAN_SECONDS, "cleave": CLEAVE_SECONDS, "repair": REPAIR_SECONDS}
        need = [s for s in STEPS[:STEPS.index(name) + 1] if s not in self.done]
        return max(1.0, sum(times[s] for s in need))

    def run_step(self, name: str) -> list[Animation]:
        """Play a step, and first the earlier ones that have not played."""
        if name in self.done:
            return []
        anims: list[Animation] = []
        for before in STEPS[:STEPS.index(name)]:
            if before not in self.done:
                anims += self.run_step(before)
        self.done.add(name)
        part = getattr(self, f"_step_{name}")()
        return [Succession(*anims, *part)] if anims else part

    def _step_dna(self) -> list[Animation]:
        lines = [f"the target: {len(self.plan.target)} bp of double-stranded DNA, each strand written 5′→3′"]
        if self.flip:
            lines.append("shown from the strand that carries the PAM, so the protospacer reads 5′→3′ on top: it is the reverse "
                         "complement of the sequence written in target:")
        if self.plan.coding_first is not None:
            lines.append(f"the strand given is coding from c.{self.plan.coding_first}" + (" (the lower one here)" if self.flip else ""))
        return [AnimationGroup(FadeIn(VGroup(*self.top.values()), shift=DOWN * 0.08), FadeIn(VGroup(*self.bot.values()), shift=UP * 0.08),
                               FadeIn(self.ends), FadeIn(self.more), *self._swap(self._card(lines, "The target")))]

    def _step_scan(self) -> list[Animation]:
        """The complex comes in, looks at PAMs on its way, settles on the right one; the DNA opens
        and the spacer pairs with the target strand (the R-loop)."""
        plan = self.plan
        g = plan.guide
        u = self.u
        d = 1
        shape, name = self.cas_body
        shape_w = shape.width
        home_x = shape.get_center()[0]
        shape.set_x(self.dna_area.x0 - shape_w * 0.6)
        moving = shape
        steps: list[Animation] = [AnimationGroup(FadeIn(moving, shift=RIGHT * 0.2), FadeIn(name))]
        pam_n = len(g.pam)
        tries = []
        for i, s in plan.pam_sites:
            if s != g.strand or i == g.pam_start:
                continue
            a, b = self._range(i, i + pam_n)
            if self.view[0] <= a and b <= self.view[1] and a < self.g_pam0:
                tries.append((a, b))
        for a, b in sorted(tries)[:2]:
            box = SurroundingRectangle(VGroup(*[self.top[j] for j in range(a, b) if j in self.top]),
                                       buff=u * 0.06, corner_radius=u * 0.12).set_stroke(self.dim_ink, width=3)
            steps.append(AnimationGroup(moving.animate.set_x(self.x_of((a + b) / 2)), FadeIn(box, rate_func=there_and_back)))
            steps.append(FadeOut(box, run_time=0.01))
        steps.append(AnimationGroup(moving.animate.set_x(home_x), FadeIn(self.pam_mark)))
        steps.append(FadeIn(self.proto_mark))
        # the R-loop: the non-target strand's bases lift away, the spacer takes their place over the
        # target strand it pairs with
        lift = [self.top[i].animate.shift(UP * u * 1.15) for i in range(self.g_start, self.g_end) if i in self.top]
        rloop = self.markup("displaced strand (R-loop)", size=self.tiny, color=self.dim_ink)
        rloop.move_to(np.array([self.dna_area.x0 + rloop.width / 2, self.cas_body[1].get_bottom()[1] - 0.06 - rloop.height / 2, 0]))
        steps.append(AnimationGroup(*lift, FadeIn(rloop)))
        self.rloop_lab = rloop
        steps.append(FadeIn(VGroup(*self.sgrna), shift=DOWN * d * u * 0.6))
        steps.append(AnimationGroup(*self._swap(self._card(self._guide_lines(), "The guide"))))
        return [Succession(*steps)]

    def _guide_lines(self) -> list[str]:
        plan = self.plan
        g = plan.guide
        cas = plan.cas
        lines = [f"{cas.name} (<i>{esc(cas.organism)}</i>) needs the PAM 5′-{cas.pam}-3′ next to the protospacer's 3′ end: here {g.pam}",
                 f"spacer 5′-{g.rna}-3′ ({len(g.spacer)} nt, GC {g.gc * 100:.0f} %) pairs with the target strand; the other strand is "
                 f"displaced"]
        if g in plan.candidates:
            k = plan.candidates.index(g) + 1
            lines.append(f"{len(plan.candidates)} guide{'s' if len(plan.candidates) != 1 else ''} with a PAM in this target; this is "
                         f"no. {k}, on the {g.strand} strand")
        return lines

    def _step_cleave(self) -> list[Animation]:
        """Both strands break 3 bp upstream of the PAM: blunt ends, drawn as a gap."""
        g = self.plan.guide
        u = self.u
        cas = self.plan.cas
        cut = self.g_cut
        shift = u * 0.45
        left = [t for i, t in list(self.top.items()) + list(self.bot.items()) + list(self.spacer_tiles.items()) if i < cut]
        right = [t for i, t in list(self.top.items()) + list(self.bot.items()) + list(self.spacer_tiles.items()) if i >= cut]
        left += self.end_left           # the 5′ / 3′ marks follow their ends (the … stay put)
        right += self.end_right
        flash = self.cut_mark.copy()
        moves = [VGroup(*left).animate.shift(LEFT * shift), VGroup(*right).animate.shift(RIGHT * shift)]
        lines = [f"both strands are cut {cas.cut} bp upstream (5′) of the PAM, inside the protospacer: a blunt double-strand break",
                 f"on this guide it falls between positions {g.cut} and {g.cut + 1} of the {len(self.plan.target)}-bp target as written"]
        return [Succession(AnimationGroup(Create(flash), FadeIn(self.cut_mark)), AnimationGroup(*moves, FadeOut(flash)),
                           AnimationGroup(*self._swap(self._card(lines, "The double-strand break"))))]

    def _step_repair(self) -> list[Animation]:
        """The enzyme leaves and the ends are joined: NHEJ with its indel, or HDR with a donor."""
        rep = self.plan.repair
        if rep is None:
            return []
        u = self.u
        g = self.plan.guide
        out: list[Animation] = [AnimationGroup(FadeOut(self.complex), FadeOut(self.cut_mark), FadeOut(self.pam_mark),
                                               FadeOut(self.proto_mark), FadeOut(getattr(self, "rloop_lab", VGroup())))]
        donor = None
        if rep.kind == "hdr":
            donor = self._donor()
            out.append(FadeIn(donor, shift=UP * u * 0.4))
        # the repaired allele is drawn as a new row of tiles where the DNA was
        new = self._repaired_row(rep)
        old = VGroup(*self.top.values(), *self.bot.values())
        out.append(AnimationGroup(FadeOut(old), FadeIn(new)))   # the donor stays on screen beside the allele
        head = "Non-homologous end joining" if rep.kind == "nhej" else "Homology-directed repair"
        lines = [rep.description] + list(rep.notes)
        out.append(AnimationGroup(*self._swap(self._card(lines, head))))
        return [Succession(*out)]

    def _repaired_row(self, rep: Any) -> VGroup:
        """The repaired top and bottom strands, the changed bases ringed, in the DNA's place."""
        u = self.u
        e = rep.edit
        length = len(rep.result)
        seq = reverse_complement(rep.result) if self.flip else rep.result
        a, b = self.view
        n_new = len(e.alt) if e is not None else 0
        new0, new1 = self._range(e.start, e.start + n_new, length) if e is not None else (0, 0)
        lo = max(a, 0)
        hi = min(length, b + max(0, length - len(self.plan.target)))
        tiles: list[Mobject] = []
        rings: list[Mobject] = []
        for i in range(lo, hi):
            x = self.x_of(i)
            if x < self.dna_area.x0 or x > self.dna_area.x1:
                continue
            t = base_tile(self.letters, seq[i], u).move_to(np.array([x, self.y_top, 0]))
            bt = base_tile(self.letters, _complement(seq[i]), u).move_to(np.array([x, self.y_bot, 0]))
            tiles += [t, bt]
            if e is not None and new0 <= i < new1:
                rings.append(SurroundingRectangle(VGroup(t, bt), buff=u * 0.06, corner_radius=u * 0.14).set_stroke(self.hi, width=4))
        if e is not None and not e.alt and lo <= new0 < hi:
            x = self.x_of(new0) - u / 2
            rings.append(Line(np.array([x, self.y_bot - u * 0.7, 0]), np.array([x, self.y_top + u * 0.7, 0])).set_stroke(self.bad, width=4))
        lab = self.markup("repaired allele", size=self.tiny, color=self.good)
        lab.move_to(np.array([self.dna_area.x0 + lab.width / 2, self.y_top + u * 1.4, 0]))
        return VGroup(*tiles, *rings, lab)

    def _donor(self) -> VGroup:
        """The donor template: the repaired stretch with homology arms, above the break."""
        u = self.u
        rep = self.plan.repair
        e = rep.edit
        length = len(rep.result)
        seq = reverse_complement(rep.result) if self.flip else rep.result
        new0, new1 = self._range(e.start, e.start + len(e.alt), length) if e is not None else (0, 0)
        arm = max(4, int(min(10, (self.view[1] - self.view[0]) // 3)))
        lo = max(0, new0 - arm)
        hi = min(length, max(new1, new0 + 1) + arm)
        y = self.y_top + u * 3.4
        tiles = []
        for k, i in enumerate(range(lo, hi)):
            x = self.x_of(lo) + k * u
            t = base_tile(self.letters, seq[i], u).move_to(np.array([x, y, 0]))
            if new0 <= i < new1:
                t[0].set_stroke(self.hi, width=3)
            tiles.append(t)
        group = VGroup(*tiles)
        if group.get_right()[0] > self.dna_area.x1:
            group.shift(LEFT * (group.get_right()[0] - self.dna_area.x1))
        if group.get_left()[0] < self.dna_area.x0:
            group.shift(RIGHT * (self.dna_area.x0 - group.get_left()[0]))
        lab = self.markup("donor template", size=self.tiny, color=self.dim_ink).next_to(group, UP, buff=0.06)
        return VGroup(group, lab)
