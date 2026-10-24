"""``cross``: a genetic cross at university level (DESIGN.md §96.7). The parents (genotypes in
standard notation, their homologous chromosomes with the alleles, their phenotype pictures; the
P generation and its F1 when asked), their gametes formed by segregation and independent
assortment (linked loci: parental and recombinant gametes at their exact frequencies), a Punnett
square filling cell by cell (or a branch, forked-line, diagram for larger crosses), the offspring
counted into genotype and phenotype classes with exact fractions, whole-number ratios and
percentages, lethal classes crossed out, X / Y crosses split by sex, and a chi-square test of
observed counts. Everything shown comes from ``vidgen.genetics`` (``punnett.plan_cross``,
``stats.chi_square``); the actions are in ``scenes/cross_actions.py``, the pictures in
``scenes/cross_draw.py``."""

import math
from fractions import Fraction
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import small_size, text_block
from .cross_draw import chip_text, chromosome_pairs, gamete_chip, glyph_row, sex_symbol

pn = genetics.punnett
st = genetics.stats

#: The cross scene's own actions (any of them puts the scene in manual mode: it then shows only
#: the parents and the empty square, and the actions do the rest).
CROSS_ACTIONS = ("form_gametes", "fill", "count", "ratio", "chi_square")
#: Seconds: forming the gametes; filling one cell (at least / at most for a fill); counting one
#: class; the ratio; the chi-square table.
FORM_SECONDS, CELL_SECONDS, MIN_FILL, MAX_FILL = 2.2, 0.22, 1.0, 6.0
CLASS_SECONDS, RATIO_SECONDS, CHI_SECONDS = 0.45, 1.2, 2.4
#: Opacity of a filled cell's tint (its class colour).
TINT = 0.22
#: The most genotype classes a table shows (a trihybrid's 27 do not fit: count phenotypes).
GENOTYPE_ROWS_MAX = 12


def genotype_table_fits(plan: Any) -> bool:
    """Whether the genotype classes fit in a table (at most :data:`GENOTYPE_ROWS_MAX`)."""
    return len(plan.genotypes) <= GENOTYPE_ROWS_MAX


@scene("cross")
class CrossScene(NarratedScene):
    """A genetic cross: parents, gametes, a Punnett square or branch diagram, the offspring's
    genotype and phenotype classes with exact ratios, and an optional chi-square test. Built
    from a genetic system (``preset`` or ``loci`` / ``linkage`` / ``epistasis`` / ``sex``) and
    the parents' genotypes; ``kind: test`` makes the tester, ``kind: reciprocal`` swaps the
    sexes of the lines, ``P`` crosses a P generation to its F1 and shows the F2. Without cross
    actions it plays itself beat by beat (gametes, the square, the counts with their ratios, the
    test); the actions form_gametes, fill, count, ratio and chi_square put each step on a word.

    Action targets: ``title``, ``generations``, ``parents`` (``both``), ``parent1``,
    ``parent2`` (``mother`` / ``father`` with sexes), ``gametes``, ``gametes1``, ``gametes2``,
    ``square`` / ``tree`` (``all``), ``row<N>``, ``col<N>``, ``cell<R>.<C>``, ``cells:<class or
    genotype>``, ``phenotypes``, ``genotypes``, ``class<N>``, ``class:<label>``,
    ``genotype:<genotype>``, ``chi_square``, ``notes``."""

    outro = 0.5
    target_patterns = ("title", "generations", "parents", "parent<N>", "mother", "father", "gametes", "gametes<N>", "square", "tree",
                       "row<N>", "col<N>", "cell<R>.<C>", "cells:<class>", "phenotypes", "genotypes", "class<N>", "class:<label>",
                       "genotype:<genotype>", "chi_square", "notes")
    #: The actions form_gametes, fill, count, ratio and chi_square act on this scene type.
    cross_actions = True
    mid_still_actions = frozenset(CROSS_ACTIONS)

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        preset: str | None = None
        """A textbook system: pea_seed_shape, pea_dihybrid, snapdragon, abo, rabbit_coat, labrador, squash_colour, chicken_feathers, shepherds_purse, sweet_pea, squash_shape, yellow_mouse, drosophila_white, hemophilia_a, drosophila_b_vg."""
        loci: list[dict[str, Any]] | None = None
        """The loci: {gene, trait, alleles (most dominant first), dominance, heterozygotes, chromosome, lethal, penetrance, normal, expressivity}."""
        linkage: list[dict[str, Any]] | None = None
        """Linked loci in map order with the recombination frequency of each interval: [{loci: [A, B], rf: 0.17, rf_male: 0}]."""
        epistasis: list[dict[str, Any]] | None = None
        """Epistasis between two loci: [{kind: recessive, epistatic: E, hypostatic: B}] (recessive, dominant, suppression, duplicate, complementary, cumulative)."""
        sex: Literal["XY"] | None = None
        """XY: follow the sexes (females XX, males XY) without sex-linked loci."""
        parents: list[str] | str | None = None
        """The two parents' genotypes ([RrYy, RrYy]; with sex chromosomes in any order); kind: test takes one."""
        mother: str | None = None
        """The mother's (egg / seed parent's) genotype (needed with mitochondrial loci)."""
        father: str | None = None
        """The father's (sperm / pollen parent's) genotype."""
        P: list[str] | None = None
        """A true-breeding P generation ([RRYY, rryy]): its F1 is worked out and intercrossed (the F2 is shown)."""
        kind: Literal["cross", "test", "reciprocal"] = "cross"
        """cross; test (one parent with the homozygous recessive tester); reciprocal (the sexes of the two lines swapped)."""
        show: Literal["auto", "punnett", "branch"] = "auto"
        """punnett: a Punnett square (up to 8 × 8); branch: a branch (forked-line) diagram; auto: a square up to 4 × 4 gametes, branches beyond."""
        branch: Literal["phenotypes", "genotypes"] = "phenotypes"
        """branch diagram: of the phenotypes (by sex, then trait) or of the genotypes (locus by locus)."""
        observed: dict[str, int] | list[int] | None = None
        """Counts of the phenotype classes for a chi-square test ({round yellow: 315, ...}, or a list in class order)."""
        alpha: float | str = 0.05
        """The chi-square test's significance level."""
        notes: bool = True
        """Show the notes the cross needs (recombinant gametes, a lethal class, the tester, epistasis)."""
        pictures: bool = True
        """Draw the phenotype pictures (peas, flowers, eyes, flies, coats, blood groups…)."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def spec(self) -> dict[str, Any]:
            data = {k: getattr(self, k) for k in ("preset", "loci", "linkage", "epistasis", "sex", "parents", "mother", "father", "P",
                                                 "kind", "show", "branch") if getattr(self, k) is not None}
            if isinstance(data.get("parents"), str):
                data["parents"] = [data["parents"]]
            return data

        def plan(self) -> Any:
            return pn.plan_cross(self.spec())

        def chi(self) -> Any:
            plan = self.plan()
            counts = pn.match_observed(plan, self.observed, "observed")
            return st.chi_square([c.label for c in plan.phenotypes], counts, [c.share for c in plan.phenotypes],
                                 pn.significance(self.alpha, "alpha"), "observed")

        @model_validator(mode="after")
        def _check(self) -> "CrossScene.Params":
            if self.preset is None and not self.loci:
                raise ValueError("give a preset (pea_dihybrid, abo, drosophila_white…) or the loci")
            try:
                self.plan()
                if self.observed is not None:
                    self.chi()
                elif "alpha" in self.model_fields_set:
                    raise VidgenError("alpha: belongs to the chi-square test (give observed counts)")
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        plan = params.plan()
        tree = params.branch if plan.show == "branch" else None
        names = ["title"] if params.title else []
        names += ["generations"] if plan.p_line else []
        names += ["parents", "both", "parent1", "mother", "parent2", "father"]
        names += ["gametes", "gametes1", "gametes2"]
        if plan.show == "punnett":
            names += ["square", "all"] + [f"row{i + 1}" for i in range(len(plan.eggs))] + [f"col{j + 1}" for j in range(len(plan.sperm))]
            names += [f"cell{c.row}.{c.col}" for c in plan.cells]
            names += [f"cells:{c.label}" for c in plan.phenotypes]
            names += [f"cells:{g.ascii}" for g in plan.genotypes if f"cells:{g.ascii}" not in names]
        else:
            names += ["tree", "all"]
            names += [f"cells:{c.label}" for c in plan.phenotypes] if tree == "phenotypes" else []
        names += ["phenotypes"]
        for c in plan.phenotypes:
            names += [f"class{c.index}", f"class:{c.label}"]
        if tree == "genotypes":
            names += ["genotypes"]
        elif genotype_table_fits(plan):
            names += ["genotypes"] + [f"genotype:{g.ascii}" for g in plan.genotypes]
        names += ["chi_square", "test"] if params.observed is not None else []
        names += ["notes"] if params.notes and plan.notes else []
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """What a class target is called on screen (its label), for the narration lint rules."""
        for prefix in ("class:", "cells:", "genotype:"):
            if name.startswith(prefix):
                return name[len(prefix):]
        return None

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """The cross actions replayed in beat and ``at`` order: a cell filled twice, gametes
        formed twice, a table counted twice."""
        from .cross_actions import cross_sequence_problems

        return cross_sequence_problems(spec, params, uses)

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.plan = p.plan()
        self.bg = th.background
        self.ink = th.color("text")
        self.dim_ink = th.color("dim")
        self.soft_ink = mix_colors(self.ink, self.bg, 0.72)     # secondary numbers: readable on tinted rows
        self.hi = th.color("highlight")
        self.bad = th.color("accent")
        self.small = small_size(self, p.size)
        self.table_size = self.small * 1.15
        symbols = [s for lo in self.plan.system.loci for s in lo.symbols]
        self.sep = "" if genetics.genotype._simple(symbols) else " "
        self.class_color = {c.index: th.palette_color(c.index - 1) for c in self.plan.phenotypes}
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.25)
        self.title_mob = title
        self.manual = any(self.action_uses(n) for n in CROSS_ACTIONS)
        #: A branch diagram's leaves are the table of its kind (phenotypes or genotypes); the
        #: panel holds the other tables (and the chi-square test) when there are any.
        self.tree_kind = p.branch if self.plan.show == "branch" else None
        self.ph_in_panel = self.tree_kind != "phenotypes"
        self.ge_in_panel = self.tree_kind != "genotypes" and genotype_table_fits(self.plan)
        self.has_panel = self.ph_in_panel or self.ge_in_panel or p.observed is not None
        self.formed: set[int] = set()
        self.filled: set[tuple[int, int]] = set()
        self.grown = 0
        self.counted: set[str] = set()
        self.ratios: set[str] = set()
        self.chi_shown = False
        self.notes_shown = False
        self.cards_on: list[str] = []
        # the tables first (they need only the panel's width): a 9:16 panel is as tall as they are
        self.panel_w = body.width if self.is_portrait else body.width * 0.42 - 0.35
        self._build_cards()
        self._layout(body)
        self._build_parents()
        if self.plan.show == "punnett":
            self._build_square()
        else:
            self._build_tree()
        self._build_notes()
        self._register()

    # ----- layout -----------------------------------------------------------------------------

    def _layout(self, body: Any) -> None:
        """The panel (tables: right in 16:9, below in 9:16), the notes under the drawing, the P
        line on top and ``main``: where the parents and the square or tree go."""
        plan = self.plan
        line = self.small / 48 * 1.25
        width = body.width if (self.is_portrait or not self.has_panel) else body.width * 0.58
        self.notes_mob = None
        if self.params.notes and plan.notes:
            lines = [text_block(self, note, width, self.small * 0.9, color=self.dim_ink) for note in plan.notes]
            self.notes_mob = VGroup(*lines).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        notes_h = self.notes_mob.height + 0.1 if self.notes_mob is not None else 0.0
        if not self.has_panel:
            main = body
            self.panel = body
        elif not self.is_portrait:
            split = body.x0 + body.width * 0.58
            main = Region(body.x0, body.y0, split, body.y1)
            self.panel = Region(split + 0.35, body.y0, body.x1, body.y1)
        else:
            tallest = max((c.height for c in self.card_mobs.values()), default=0.0)
            panel_h = min(max(tallest + 0.1, body.height * 0.2), body.height * 0.42)
            main = Region(body.x0, body.y0 + panel_h + 0.25, body.x1, body.y1)
            self.panel = Region(body.x0, body.y0, body.x1, body.y0 + panel_h)
        self.notes_area = Region(main.x0, main.y0, main.x1, main.y0 + notes_h) if notes_h else None
        top = main.y1
        self.p_line_y = top - line / 2
        if plan.p_line:
            top -= line + 0.15
        lower = main.y0 + notes_h + (0.12 if notes_h else 0.0)
        self.main = Region(main.x0, lower, main.x1, top)
        #: 16:9: parent 1 beside the square's rows, parent 2 over its columns; beside a branch
        #: diagram the parents and their gametes in a column. 9:16: the parents in a row on top.
        self.side = not self.is_portrait

    # ----- parents ----------------------------------------------------------------------------

    def _parent_card(self, k: int) -> VGroup:
        plan = self.plan
        g = plan.mother if k == 0 else plan.father
        size = self.small
        chroms = chromosome_pairs(self, plan.system, g, 1.0 if self.is_portrait else 0.85, size)
        label = self.markup(genetics.genotype_text(plan.system, g, "markup"), size=size * 1.3, color=self.ink)
        row: list[Mobject] = []
        if plan.system.needs_sexes:
            row.append(sex_symbol("female" if k == 0 else "male", size / 48 * 0.8, self.ink))
        role = plan.roles[k]
        if role:
            row.append(self.markup(role, size=size, color=self.soft_ink))
        row.append(label)
        cls = self._phenotype_of(g)
        if self.params.pictures and cls is not None:
            row.append(glyph_row(self, cls.glyphs, size / 48 * 1.3, self.class_color.get(cls.index, self.dim_ink)))
        line = VGroup(*row).arrange(RIGHT, buff=0.12)
        return VGroup(chroms, line).arrange(DOWN, buff=0.14)

    def _phenotype_of(self, g: Any) -> Any:
        """The phenotype class a parent shows (one of the offspring's, or one of its own)."""
        plan = self.plan
        if genetics.is_lethal(plan.system, g):
            return None
        dist = genetics.phenotypes_of(plan.system, g)
        ph = max(dist, key=lambda x: dist[x])
        for c in plan.phenotypes:
            if c.phenotype == ph:
                return c
        traits = [t.name for t in plan.system.traits]
        normals = [plan.system.locus(t.loci[0]).normal if t.epistasis is None else None for t in plan.system.traits]
        pictures = tuple(genetics.glyphs.class_glyphs(traits, list(ph.traits), normals))
        return pn.PhenotypeClass(0, pn.class_label(ph), ph, Fraction(0), 0, (), None, pictures)

    def _build_parents(self) -> None:
        main = self.main
        plan = self.plan
        cards = [self._parent_card(0), self._parent_card(1)]
        times = self.markup("×", size=self.small * 1.8, color=self.ink)
        self.parent_cards, self.times = cards, times
        self.parents_group = VGroup(cards[0], times, cards[1])
        self.gamete_rows = self._gamete_rows() if plan.show == "branch" else None
        if self.side and plan.show == "punnett":           # placed with the square
            for card in cards:
                card.scale(min(1.0, main.width * 0.3 / card.width, main.height * 0.26 / card.height))
            self.grid_area = main
        elif self.side and not self.has_panel:            # 16:9 branch diagram: a column left of the tree
            rows = self.gamete_rows or []
            stack = VGroup(cards[0], rows[0], times, cards[1], rows[1]).arrange(DOWN, buff=0.22)
            stack.scale(min(1.0, main.width * 0.34 / stack.width, main.height / stack.height))
            stack.move_to(np.array([main.x0 + stack.width / 2, main.center[1], 0.0]))
            self.grid_area = Region(stack.get_right()[0] + 0.5, main.y0, main.x1, main.y1)
        else:                                    # 9:16 and branch diagrams beside a panel: a row on top, gametes under each parent
            row = VGroup(cards[0], times, cards[1]).arrange(RIGHT, buff=0.6)
            tall = 2.4 if self.is_portrait else (1.3 if plan.show == "branch" else 1.45)
            row.scale(min(1.25, main.width / row.width, min(tall, main.height * 0.27) / row.height))
            row.move_to(np.array([main.center[0], main.y1 - row.height / 2, 0.0]))
            y = row.get_bottom()[1] - 0.25
            if self.gamete_rows:
                for k, grid in enumerate(self.gamete_rows):
                    grid.scale(min(1.0, (main.width / 2 - 0.15) / grid.width, (1.0 if self.has_panel else 1.4) / grid.height))
                    x = min(max(cards[k].get_center()[0], main.x0 + grid.width / 2), main.x1 - grid.width / 2)
                    grid.move_to(np.array([x, y - grid.height / 2, 0.0]))
                y = min(g.get_bottom()[1] for g in self.gamete_rows) - 0.25
            self.grid_area = Region(main.x0, main.y0, main.x1, y)
        self.p_line_mob = None
        if plan.p_line:
            t = self.markup(plan.p_line, size=self.small, color=self.dim_ink)
            if t.width > main.width:
                t.scale(main.width / t.width)
            t.move_to(np.array([main.center[0], self.p_line_y, 0.0]))
            self.p_line_mob = t

    def _gamete_rows(self) -> list[VGroup]:
        """Branch diagrams: each parent's gametes as a grid of chips (placed with the parents)."""
        out = []
        for views in (self.plan.eggs, self.plan.sperm):
            chips = []
            for view in views:
                ring = self.hi if view.recombinant else mix_colors(self.ink, self.bg, 0.45)
                f = self.markup(self._freq_text(view.frequency), size=self.small * 0.9, color=self.soft_ink)
                chips.append(VGroup(gamete_chip(self, view, 0.3, self.small, ring, self.sep), f).arrange(DOWN, buff=0.03))
            cols = len(chips) if len(chips) <= 4 else math.ceil(len(chips) / 2)
            out.append(VGroup(*chips).arrange_in_grid(cols=cols, buff=(0.1, 0.08)))
        return out

    # ----- the Punnett square -----------------------------------------------------------------

    def _build_square(self) -> None:
        plan = self.plan
        rows, cols = len(plan.eggs), len(plan.sperm)
        area = self.grid_area
        size = self.small * 1.15
        texts = {(c.row, c.col): self.markup(c.markup, size=size, color=self.ink) for c in plan.cells}
        text_w = max(t.width for t in texts.values())
        egg_t = [chip_text(self, v, self.small, self.sep) for v in plan.eggs]
        sperm_t = [chip_text(self, v, self.small, self.sep) for v in plan.sperm]

        def pill(ts: list[Mobject], r: float) -> float:
            return max(max(2 * r, t.width * min(1.0, r * 1.25 / t.height) + 0.9 * r) for t in ts)

        c1, c2 = self.parent_cards
        show_freq = max(rows, cols) <= 4 or not plan.uniform
        left, over = (c1.width + 0.35, c2.height + 0.3) if self.side else (0.0, 0.0)
        room_w, room_h = area.width - left, area.height - over
        ch = min(room_h / (rows + 0.85), 2.0)
        for _ in range(4):           # cells as tall as the height allows, as wide as their genotypes
            hh = 0.85 * ch
            r = min(0.4 * hh, 0.48)
            shares = [self.markup(self._freq_text(v.frequency), size=self.small * 0.95) for v in plan.eggs] if show_freq else []
            low = bool(shares) and 2 * r + max(t.height for t in shares) + 0.04 > ch * 0.96   # the share goes beside the gamete
            hw = max(hh, pill(egg_t, r) + 0.15 + (max(t.width for t in shares) + 0.1 if low else 0.0))
            need = max(ch, text_w / 0.86 + 0.05, pill(sperm_t, r) + 0.12)
            cw = min(need, (room_w - hw) / cols, 2.8)
            if cw < ch - 1e-6:
                ch = cw
                continue
            break
        self.cell_w, self.cell_h = cw, ch
        width, height = hw + cols * cw, hh + rows * ch
        x_start = area.center[0] - (left + width) / 2
        x0 = x_start + left
        y1 = area.center[1] + (over + height) / 2 - over
        if self.side:
            c2.move_to(np.array([x0 + hw + cols * cw / 2, y1 + 0.3 + c2.height / 2, 0.0]))
            c1.move_to(np.array([x_start + c1.width / 2, y1 - hh - rows * ch / 2, 0.0]))
        self.cell_centers: dict[tuple[int, int], np.ndarray] = {}
        squares = VGroup()
        line = mix_colors(self.ink, self.bg, 0.4)
        for i in range(rows):
            for j in range(cols):
                c = np.array([x0 + hw + (j + 0.5) * cw, y1 - hh - (i + 0.5) * ch, 0.0])
                self.cell_centers[(i + 1, j + 1)] = c
                squares.add(Rectangle(width=cw, height=ch).move_to(c).set_stroke(line, width=2).set_fill(self.bg, opacity=0))
        row_slots = [np.array([x0 + hw / 2, y1 - hh - (i + 0.5) * ch, 0.0]) for i in range(rows)]
        col_slots = [np.array([x0 + hw + (j + 0.5) * cw, y1 - hh / 2, 0.0]) for j in range(cols)]
        corner = VGroup()
        cx, cy = x0 + hw / 2, y1 - hh / 2
        if plan.system.needs_sexes:
            s = min(hh * 0.32, 0.34)
            corner.add(sex_symbol("female", s, self.dim_ink).move_to(np.array([cx - hw * 0.2, cy - hh * 0.2, 0])))
            corner.add(sex_symbol("male", s, self.dim_ink).move_to(np.array([cx + hw * 0.22, cy + hh * 0.2, 0])))
            corner.add(Line(np.array([cx - hw * 0.4, cy + hh * 0.4, 0]), np.array([cx + hw * 0.4, cy - hh * 0.4, 0])).set_stroke(line, width=1.5))
            if self.side:
                self.times.set_opacity(0).move_to(np.array([cx, cy, 0.0]))
        elif self.side:
            self.times.scale(min(1.0, hh * 0.6 / self.times.height)).move_to(np.array([cx, cy, 0.0]))
        self.grid_frame = VGroup(squares, corner)
        # the gametes, in the headers: the mother's (eggs) down the side, the father's across the top
        self.headers: list[list[VGroup]] = [[], []]
        for k, (views, slots, room) in enumerate(((plan.eggs, row_slots, hw), (plan.sperm, col_slots, cw))):
            for view, slot in zip(views, slots):
                ring = self.hi if view.recombinant else mix_colors(self.ink, self.bg, 0.45)
                parts: list[Mobject] = [gamete_chip(self, view, r, self.small, ring, self.sep, max_width=room * 0.94)]
                if show_freq:
                    f = self.markup(self._freq_text(view.frequency), size=self.small * 0.95, color=self.soft_ink)
                    if f.width > room * 0.94:
                        f.scale(room * 0.94 / f.width)
                    parts.append(f)
                group = VGroup(*parts).arrange(DOWN, buff=0.04)
                limit = hh if k == 1 else ch
                if k == 0 and group.height > limit * 0.96 and len(parts) == 2:     # a low row: the share beside its gamete
                    group = VGroup(parts[1], parts[0]).arrange(RIGHT, buff=0.08)
                if group.height > limit * 0.98:
                    group.scale(limit * 0.98 / group.height)
                if group.width > room * 0.98:
                    group.scale(room * 0.98 / group.width)
                self.headers[k].append(group.move_to(slot))
        self.cell_mobs: dict[tuple[int, int], VGroup] = {}
        self.cell_texts: dict[tuple[int, int], Mobject] = {}
        self.cell_tints: dict[tuple[int, int], Mobject] = {}
        for c in plan.cells:
            self.cell_mobs[(c.row, c.col)] = self._cell(c, cw, ch, texts[(c.row, c.col)])

    def _freq_text(self, f: Fraction) -> str:
        if self.plan.uniform and f.denominator <= 64:
            return pn.fraction_text(f)
        return pn.percent_text(f).replace("≈ ", "")

    def _cell(self, c: Any, cw: float, ch: float, text: Mobject) -> VGroup:
        center = self.cell_centers[(c.row, c.col)]
        cls = self._class_of_cell(c)
        color = self.class_color.get(cls.index, self.dim_ink) if cls is not None else self.dim_ink
        tint = Rectangle(width=cw - 0.06 * ch, height=ch * 0.94).move_to(center).set_stroke(width=0)
        tint.set_fill(color, opacity=TINT if not c.lethal else 0.08)
        size = ch
        room = cw - 0.14 * ch
        if text.width > room:
            text.scale(room / text.width)
        parts: list[Mobject] = [tint, text]
        extras: list[Mobject] = []
        has_pic = self.params.pictures and cls is not None and ch >= 0.8
        if has_pic:
            extras.append(glyph_row(self, cls.glyphs, size * 0.36, color))
        if c.genotype.sex is not None and size >= 0.6:
            extras.append(sex_symbol(c.genotype.sex, size * (0.26 if has_pic else 0.3), self.dim_ink))
        if extras:
            row = VGroup(*extras).arrange(RIGHT, buff=size * 0.08)
            if row.width > room:
                row.scale(room / row.width)
            stack = VGroup(text, row).arrange(DOWN, buff=size * 0.06)
            if stack.height > size * 0.88:
                stack.scale(size * 0.88 / stack.height)
            stack.move_to(center)
            parts.append(row)
        else:
            text.move_to(center)
        if c.lethal:                  # crossed out behind its genotype, which stays readable
            half = min(cw, ch) * 0.4
            cross = VGroup(Line(center + np.array([-half, -half, 0]), center + np.array([half, half, 0])),
                           Line(center + np.array([-half, half, 0]), center + np.array([half, -half, 0]))).set_stroke(self.bad, width=5, opacity=0.8)
            parts.insert(1, cross)
        self.cell_texts[(c.row, c.col)] = text
        self.cell_tints[(c.row, c.col)] = tint
        return VGroup(*parts)

    def _class_of_cell(self, c: Any) -> Any:
        if c.lethal or not c.phenotypes:
            return None
        ph = max(c.phenotypes, key=lambda x: x[1])[0]
        return next((k for k in self.plan.phenotypes if k.phenotype == ph), None)

    # ----- the branch diagram -----------------------------------------------------------------

    def _build_tree(self) -> None:
        """The branch (forked-line) diagram: a column per level (sex, then each trait; or each
        locus), each node its conditional probability and value; at each leaf (shown by the
        counting) its product, its share in per cent (16:9), its pictures and its number of the
        ratio, and the ratio under the tree — the leaves are the class table. Columns as wide
        as their labels, the whole fitted to the area."""
        plan = self.plan
        tree = plan.tree
        area = self.grid_area
        levels = len(tree.levels)
        leaves = tree.leaves
        size = self.small
        heads = [self.markup(f"<b>{name}</b>", size=size * 0.9, color=self.dim_ink) for name in tree.levels]
        labels: list[VGroup] = []
        for node in tree.nodes:
            frac = self.markup(pn.fraction_text(node.conditional), size=size * 0.95, color=self.soft_ink)
            value = self.markup(node.markup, size=size, color=self.ink)
            labels.append(VGroup(frac, value).arrange(RIGHT, buff=0.1, aligned_edge=DOWN))
        numbers = genetics.ratio([leaf.probability for leaf in leaves])
        marks: list[VGroup] = []
        rats: list[Mobject] = []
        for leaf, n in zip(leaves, numbers):
            cls = self._leaf_class(leaf)
            color = self.class_color.get(cls.index, self.dim_ink) if cls is not None else self.dim_ink
            parts: list[Mobject] = [self.markup(f"= {pn.fraction_text(leaf.probability)}", size=size, color=self.ink)]
            if self._leaf_percent(labels, leaves, area):
                parts.append(self.markup(f"({pn.percent_text(leaf.probability)})", size=size * 0.9, color=self.soft_ink))
            if self.params.pictures and cls is not None:
                parts.append(glyph_row(self, cls.glyphs, size / 48 * 0.95, color))
            rat = self.markup(f"<b>{n}</b>", size=size * 1.1, color=self.hi)
            parts.append(rat)
            marks.append(VGroup(*parts).arrange(RIGHT, buff=0.16))
            rats.append(rat)
        kind = "phenotypic" if self.tree_kind == "phenotypes" else "genotypic"
        ratio_line = self._ratio_line(numbers, f"{kind} ratio", size)
        gap_x, root_gap = 0.5, 0.4
        widths = [max(max((labels[i].width for i, n in enumerate(tree.nodes) if n.level == lv), default=0.0), heads[lv].width)
                  for lv in range(levels)]
        mark_w = max(m.width for m in marks)
        head_h = max(h.height for h in heads) + 0.2
        row_h = max(max(lb.height for lb in labels), max(m.height for m in marks)) * 1.08
        if ratio_line.width > area.width:             # the ratio line fits on its own; the tree gets the rest
            ratio_line.scale(area.width / ratio_line.width)
        line_h = ratio_line.height + 0.3
        total_w = root_gap + sum(widths) + gap_x * levels + mark_w
        total_h = head_h + row_h * len(leaves)
        scale = min(1.0, area.width / total_w, (area.height - line_h) / total_h)
        for m in [*heads, *labels, *marks]:
            m.scale(scale)
        widths = [w * scale for w in widths]
        mark_w, head_h = mark_w * scale, head_h * scale
        row_h = min((area.height - head_h - line_h) / len(leaves), row_h * scale * (2.0 if self.is_portrait else 1.5))
        total_w = (root_gap + gap_x * levels) + sum(widths) + mark_w
        x = area.center[0] - min(total_w, area.width) / 2 + root_gap
        xs = []
        for w in widths:
            xs.append(x + w / 2)
            x += w + gap_x
        x_marks = x - gap_x + 0.15
        top = area.y1                                   # under the parents and their gametes
        for k, h in enumerate(heads):
            h.move_to(np.array([xs[k], top - h.height / 2, 0.0]))
        rows_top = top - head_h
        y_of: dict[tuple[str, ...], float] = {leaf.path: rows_top - row_h * (k + 0.5) for k, leaf in enumerate(leaves)}
        for level in range(levels - 2, -1, -1):
            for node in tree.nodes:
                if node.level == level:
                    ys = [y for path, y in y_of.items() if len(path) == level + 2 and path[:level + 1] == node.path]
                    y_of[node.path] = sum(ys) / len(ys)
        self.tree_heads = VGroup(*heads)
        self.tree_nodes: list[VGroup] = []
        self.tree_levels: list[list[int]] = [[] for _ in range(levels)]
        self.node_label: dict[tuple[str, ...], VGroup] = {}
        for idx, (node, label) in enumerate(zip(tree.nodes, labels)):
            label.move_to(np.array([xs[node.level], y_of[node.path], 0.0]))
            self.tree_nodes.append(label)
            self.tree_levels[node.level].append(idx)
            self.node_label[node.path] = label
        line = mix_colors(self.ink, self.bg, 0.45)
        self.tree_edges: list[list[Mobject]] = [[] for _ in range(levels)]
        bottom = rows_top - row_h * len(leaves)
        root = Dot(radius=0.06, color=line).move_to(np.array([xs[0] - widths[0] / 2 - root_gap + 0.06, (rows_top + bottom) / 2, 0.0]))
        self.tree_root = root
        for node in tree.nodes:
            end = self.node_label[node.path].get_left() + LEFT * 0.06
            start = root.get_center() if node.level == 0 else self.node_label[node.path[:-1]].get_right() + RIGHT * 0.06
            self.tree_edges[node.level].append(Line(start, end).set_stroke(line, width=2))
        for leaf, mark in zip(leaves, marks):
            mark.move_to(np.array([x_marks + mark.width / 2, y_of[leaf.path], 0.0]))
        for mark, rat in zip(marks, rats):
            mark.remove(rat)                         # shown by the ratio
        ratio_line.move_to(np.array([area.center[0], bottom - line_h / 2, 0.0]))
        self.leaf_marks, self.leaf_ratio_cells, self.tree_ratio_line = marks, rats, ratio_line
        self.leaf_rows = [VGroup(self.node_label[leaf.path], mark, rat) for leaf, mark, rat in zip(leaves, marks, rats)]
        self.tree_group = VGroup(self.tree_heads, root, *self.tree_nodes, *[e for lv in self.tree_edges for e in lv])
        self.tree_card = VGroup(*marks, *rats, ratio_line)

    def _leaf_percent(self, labels: list[VGroup], leaves: Any, area: Any) -> bool:
        """Whether the leaves have room for their percentages: in 16:9, when the tree with them
        keeps nine tenths of its size."""
        if self.is_portrait:
            return False
        if not hasattr(self, "_with_percent"):
            levels = len(self.plan.tree.levels)
            widths = [max(lb.width for lb, n in zip(labels, self.plan.tree.nodes) if n.level == lv) for lv in range(levels)]
            sample = self.markup("= 27/64 (≈ 42.2 %) 27", size=self.small)
            pictures = 0.55 * len(self.plan.system.traits) if self.params.pictures else 0.0
            need = 0.4 + sum(widths) + 0.5 * levels + sample.width + pictures
            self._with_percent = need * 0.9 <= area.width
        return self._with_percent

    def _count_leaves(self) -> list[Animation]:
        """The tree's leaves counted: each leaf's product (and share), pictures appear."""
        steps = []
        for row, mark in zip(self.leaf_rows, self.leaf_marks):
            box = SurroundingRectangle(VGroup(row[0], mark), buff=0.06, corner_radius=0.08).set_stroke(self.hi, width=3).set_fill(opacity=0)
            steps.append(AnimationGroup(FadeIn(mark, shift=LEFT * 0.1), Succession(FadeIn(box, run_time=0.4), FadeOut(box, run_time=0.4))))
        return [LaggedStart(*steps, lag_ratio=0.35)]

    def _leaf_class(self, leaf: Any) -> Any:
        if self.params.branch != "phenotypes":
            return None
        for c in self.plan.phenotypes:
            key = ([c.phenotype.sex] if c.phenotype.sex else []) + list(c.phenotype.traits)
            if tuple(key) == leaf.path:
                return c
        return None

    # ----- cards: the class tables and the chi-square test ------------------------------------

    def _table(self, header: str, rows: list[list[Mobject]], aligns: list[str], width: float, row_colors: list[str | None],
               struck: list[bool], head_width: float | None = None) -> tuple[VGroup, list[VGroup], list[VGroup]]:
        """A small table: a bold header, rows of cells aligned per column. Returns the table,
        each row (its band and cells) and each row's cells."""
        size = self.table_size
        head = self.markup(f"<b>{header}</b>", size=size, color=self.ink)
        ncols = max(len(r) for r in rows)
        widths = [max((r[k].width for r in rows if k < len(r)), default=0.0) for k in range(ncols)]
        gap = 0.26
        total = sum(widths) + gap * (ncols - 1) + 0.3
        row_h = max(max(c.height for c in r) for r in rows) + 0.16
        row_mobs: list[VGroup] = []
        cell_groups: list[VGroup] = []
        y = -head.height / 2 - 0.16
        for r, color, dead in zip(rows, row_colors, struck):
            x = 0.15
            cells = VGroup()
            for k, c in enumerate(r):
                cy = y - row_h / 2
                if aligns[k] == "r":
                    c.move_to(np.array([x + widths[k] - c.width / 2, cy, 0.0]))
                elif aligns[k] == "c":
                    c.move_to(np.array([x + widths[k] / 2, cy, 0.0]))
                else:
                    c.move_to(np.array([x + c.width / 2, cy, 0.0]))
                cells.add(c)
                x += widths[k] + gap
            back = Rectangle(width=total, height=row_h - 0.04).move_to(np.array([total / 2, y - row_h / 2, 0.0]))
            back.set_stroke(width=0).set_fill(color or self.bg, opacity=0.16 if color else 0.0)
            if dead:                  # a class that dies: a red band (its text says "dies")
                back.set_fill(self.bad, opacity=0.14)
            row_mobs.append(VGroup(back, cells))
            cell_groups.append(cells)
            y -= row_h
        if head.width > (head_width or width):
            head.scale((head_width or width) / head.width)
        head.move_to(np.array([head.width / 2 + 0.05, 0.0, 0.0]))
        table = VGroup(head, *row_mobs)
        self._natural_width = total
        if total > width:             # the rows fitted (the header was fitted to its own room)
            table.scale(width / total, about_point=np.array([0.0, 0.0, 0.0]))
        return table, row_mobs, cell_groups

    def _build_cards(self) -> None:
        plan = self.plan
        width = self.panel_w
        offspring = plan.offspring
        self.ph_card = self.ge_card = None
        self.ph_count_nums: dict[int, list[Mobject]] = {}
        if self.ph_in_panel:
            self._phenotype_card(width, offspring)
        if self.ge_in_panel:
            self._genotype_card(width, offspring)
        self.chi_card = self._chi_card() if self.params.observed is not None else None
        self.card_mobs: dict[str, VGroup] = {}
        for name, card in (("phenotypes", self.ph_card), ("genotypes", self.ge_card), ("chi_square", self.chi_card)):
            if card is not None:
                self.card_mobs[name] = card

    def _phenotype_card(self, width: float, offspring: str) -> None:
        """The phenotype table: picture, name, fraction, percentage (left out when the panel is
        too narrow for it), ratio number; a lethal class's row; the ratio line."""
        plan = self.plan
        size = self.table_size
        rows, colors, struck = [], [], []
        uniform = plan.uniform and all(c.count is not None for c in plan.phenotypes)
        total_cells = sum(1 for c in plan.cells if not c.lethal) if uniform else 0
        for c in plan.phenotypes:
            color = self.class_color[c.index]
            pic = (glyph_row(self, c.glyphs, size / 48 * 0.95, color) if self.params.pictures
                   else Square(side_length=size / 48 * 0.5).set_fill(color, 1).set_stroke(width=0))
            frac = pn.fraction_text(c.share)
            if uniform and c.count is not None and Fraction(c.count, total_cells) != c.share:
                frac = f"{c.count}/{total_cells}"
            rows.append([pic, self.markup(self._label_markup(c), size=size, color=self.ink), self.markup(frac, size=size, color=self.ink),
                         self.markup(pn.percent_text(c.share), size=size * 0.9, color=self.soft_ink),
                         self.markup(f"<b>{c.ratio}</b>", size=size * 1.1, color=self.hi)])
            colors.append(color)
            struck.append(False)
        if plan.lethal:
            dead = ", ".join(g.markup for g in plan.genotypes if g.lethal)
            rows.append([Square(side_length=size / 48 * 0.45).set_stroke(self.bad, width=2).set_fill(opacity=0),
                         self.markup(f"{dead} dies", size=size, color=self.bad),
                         self.markup(pn.fraction_text(plan.lethal), size=size, color=self.bad),
                         self.markup("of zygotes", size=size * 0.9, color=self.dim_ink), self.markup(" ", size=size)])
            colors.append(None)
            struck.append(False)
        header = f"{offspring} phenotypes" + (" (survivors)" if plan.lethal else "")
        table, self.ph_rows, cells = self._table(header, rows, ["c", "l", "r", "r", "c"], width, colors, struck)
        if width < self._natural_width * 0.85:             # too narrow: without the percentages
            for r in rows[:len(plan.phenotypes)]:
                r[3] = self.markup(" ", size=size * 0.3)
            table, self.ph_rows, cells = self._table(header, rows, ["c", "l", "r", "r", "c"], width, colors, struck)
        self.ph_head = [table[0]]
        n = len(plan.phenotypes)
        self.ph_ratio_cells = [cells[k][4] for k in range(n)]
        self.ph_frac_cells = [cells[k][2] for k in range(n)]
        for k in range(n):
            cells[k].remove(self.ph_ratio_cells[k])
        if plan.lethal:
            cells[n].remove(cells[n][4])
        # counting: the fraction counts up cell by cell when the cells are equally likely
        if uniform and total_cells:
            for k, c in enumerate(plan.phenotypes):
                cell = self.ph_frac_cells[k]
                cells[k].remove(cell)
                nums = []
                for m in range(1, (c.count or 0) + 1):
                    t = self.markup(f"{m}/{total_cells}", size=size, color=self.ink)
                    t.match_height(cell).move_to(cell.get_right() - np.array([t.width / 2, 0, 0]))
                    nums.append(t)
                self.ph_count_nums[k] = nums
        self.ph_ratio_line = self._ratio_line(plan.phenotype_ratio, "phenotypic ratio")
        self.ph_table = table
        counting = [*(self.ph_frac_cells if self.ph_count_nums else []), *[t for nums in self.ph_count_nums.values() for t in nums]]
        self.ph_card = self._card(table, self.ph_ratio_line, [*self.ph_ratio_cells, *counting])

    def _genotype_card(self, width: float, offspring: str) -> None:
        """The genotype table (two columns beyond six classes): genotype, fraction of the
        zygotes, percentage, ratio number; lethal ones struck through; the ratio line."""
        plan = self.plan
        size = self.table_size
        rows, colors, struck = [], [], []
        for g in plan.genotypes:
            rows.append([self.markup(g.markup, size=size, color=self.bad if g.lethal else self.ink),
                         self.markup(pn.fraction_text(g.share), size=size, color=self.ink),
                         self.markup("dies" if g.lethal else pn.percent_text(g.share), size=size * 0.9,
                                     color=self.bad if g.lethal else self.soft_ink),
                         self.markup(f"<b>{g.ratio}</b>", size=size * 1.1, color=self.hi)])
            colors.append(None)
            struck.append(g.lethal)
        header = f"{offspring} genotypes" + (" (zygotes)" if plan.lethal else "")
        if len(rows) > 6:
            half = math.ceil(len(rows) / 2)
            left, lr, lc = self._table(header, rows[:half], ["l", "r", "r", "c"], width / 2 - 0.1, colors[:half], struck[:half], width)
            right, rr, rc = self._table(" ", rows[half:], ["l", "r", "r", "c"], width / 2 - 0.1, colors[half:], struck[half:])
            right.next_to(left, RIGHT, buff=0.2, aligned_edge=UP)
            table = VGroup(left, right)
            self.ge_rows, cells, self.ge_head = lr + rr, lc + rc, [left[0], right[0]]
        else:
            table, self.ge_rows, cells = self._table(header, rows, ["l", "r", "r", "c"], width, colors, struck)
            self.ge_head = [table[0]]
        if table.width > width:
            table.scale(width / table.width)
        self.ge_ratio_cells = [c[3] for c in cells]
        for c in cells:
            c.remove(c[3])
        what = "genotypic ratio" + (" at fertilization" if plan.lethal else "")
        self.ge_ratio_line = self._ratio_line(plan.genotype_ratio, what)
        self.ge_table = table
        self.ge_card = self._card(table, self.ge_ratio_line, self.ge_ratio_cells)

    def _label_markup(self, c: Any) -> str:
        text = ", ".join(c.phenotype.traits)
        return f"{c.phenotype.sex}s: {text}" if c.phenotype.sex else text

    def _ratio_line(self, numbers: tuple[int, ...], what: str, size: float | None = None) -> VGroup:
        size = size or self.table_size
        big = self.markup(f"<b>{pn.ratio_text(numbers)}</b>", size=size * 1.35, color=self.hi)
        name = self.markup(what, size=size * 0.9, color=self.dim_ink)
        return VGroup(big, name).arrange(RIGHT, buff=0.2, aligned_edge=DOWN)

    def _card(self, table: VGroup, ratio: VGroup, loose: list[Mobject]) -> VGroup:
        """A table with its ratio line under it; ``loose`` are cells shown by actions later
        (the ratio numbers, the counted fractions)."""
        ratio.next_to(table, DOWN, buff=0.2, aligned_edge=LEFT)
        if ratio.width > self.panel_w:
            ratio.scale(self.panel_w / ratio.width, about_edge=LEFT)
        return VGroup(table, ratio, VGroup(*loose))

    def _chi_card(self) -> VGroup:
        chi = self.params.chi()
        plan = self.plan
        size = self.table_size
        width = self.panel_w
        head_color = self.dim_ink
        rows = [[self.markup("<b>class</b>", size=size * 0.9, color=head_color), self.markup("<b>O</b>", size=size * 0.9, color=head_color),
                 self.markup("<b>E</b>", size=size * 0.9, color=head_color), self.markup("<b>(O − E)²/E</b>", size=size * 0.9, color=head_color)]]
        colors: list[str | None] = [None]
        for r, c in zip(chi.rows, plan.phenotypes):
            e = r.expected
            e_text = str(e.numerator) if e.denominator == 1 else f"{float(e):.1f}"
            rows.append([self.markup(self._label_markup(c), size=size, color=self.ink), self.markup(str(r.observed), size=size, color=self.ink),
                         self.markup(e_text, size=size, color=self.ink), self.markup(f"{float(r.contribution):.3f}", size=size, color=self.ink)])
            colors.append(self.class_color[c.index])
        table, self.chi_rows, _ = self._table(f"χ² goodness of fit (n = {chi.total})", rows, ["l", "r", "r", "r"], width, colors,
                                              [False] * len(rows))
        stat = self.markup(f"<b>χ² = {float(chi.statistic):.3f}</b>   df = {chi.df}   <b>{st.p_text(chi.p)}</b>", size=size * 1.05, color=self.ink)
        crit = self.markup(f"critical value {chi.critical:.3f} at α = {float(chi.alpha):g}", size=size * 0.9, color=self.dim_ink)
        ratio = pn.ratio_text(plan.phenotype_ratio)
        if chi.rejected:
            verdict, color = f"p &lt; α: reject {ratio}", self.bad
        else:
            verdict, color = f"p ≥ α: consistent with {ratio}", self.theme.color("tertiary")
        lines = [stat, crit, self.markup(f"<b>{verdict}</b>", size=size, color=color)]
        if chi.small:
            lines.append(self.markup(f"an expected count is below {st.SMALL_EXPECTED}: the test is approximate", size=size * 0.85, color=self.dim_ink))
        foot = VGroup(*lines).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
        for item in foot:
            if item.width > width:
                item.scale(width / item.width, about_edge=LEFT)
        foot.next_to(table, DOWN, buff=0.2, aligned_edge=LEFT)
        self.chi_head = table[0]
        self.chi_foot = foot
        return VGroup(table, foot)

    def _build_notes(self) -> None:
        """The notes (made with the layout, which keeps room for them) at the bottom of the drawing."""
        if self.notes_mob is None or self.notes_area is None:
            self.notes_mob = None
            return
        area = self.notes_area
        group = self.notes_mob
        if group.height > area.height or group.width > area.width:
            group.scale(min(area.height / group.height, area.width / group.width))
        group.move_to(np.array([area.x0 + group.width / 2, area.y0 + group.height / 2, 0.0]))

    # ----- targets and the reveal -------------------------------------------------------------

    def _register(self) -> None:
        plan = self.plan
        title = self.title_mob
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        if self.p_line_mob is not None:
            self.target("generations", self.p_line_mob)
        self.target(("parents", "both"), self.parents_group)
        self.target(("parent1", "mother"), self.parent_cards[0])
        self.target(("parent2", "father"), self.parent_cards[1])
        if plan.show == "punnett":
            self.gamete_groups = [VGroup(*self.headers[0]), VGroup(*self.headers[1])]
        else:
            self.gamete_groups = list(self.gamete_rows or [])
        self.target("gametes", VGroup(*self.gamete_groups), entrance=lambda: self.run_form([0, 1]))
        self.target("gametes1", self.gamete_groups[0], entrance=lambda: self.run_form([0]))
        self.target("gametes2", self.gamete_groups[1], entrance=lambda: self.run_form([1]))
        if plan.show == "punnett":
            self._register_square()
        else:
            self.target(("tree", "all"), self.tree_group, entrance=lambda: self.run_fill(None))
            kind = self.tree_kind
            self.target(kind, self.tree_card, entrance=lambda: self.run_count(kind))
            if kind == "phenotypes":
                for c in plan.phenotypes:
                    rows = [row for row, leaf in zip(self.leaf_rows, plan.tree.leaves) if self._leaf_class(leaf) is c]
                    self.target((f"class{c.index}", f"class:{c.label}", f"cells:{c.label}"), VGroup(*rows), entrance=lambda: self.run_count("phenotypes"))
        if self.ph_card is not None:
            self.target("phenotypes", self.ph_card, entrance=lambda: self.run_count("phenotypes"))
            for k, c in enumerate(plan.phenotypes):
                row = self.ph_rows[k]
                self.target((f"class{c.index}", f"class:{c.label}"), row, outline=row[0], entrance=lambda: self.run_count("phenotypes"))
        if self.ge_card is not None:
            self.target("genotypes", self.ge_card, entrance=lambda: self.run_count("genotypes"))
            for k, g in enumerate(plan.genotypes):
                row = self.ge_rows[k]
                self.target(f"genotype:{g.ascii}", row, outline=row[0], entrance=lambda: self.run_count("genotypes"))
        if self.chi_card is not None:
            self.target(("chi_square", "test"), self.chi_card, entrance=lambda: self.run_chi())
        if self.notes_mob is not None:
            self.target("notes", self.notes_mob, entrance=lambda: self._show_notes())

        def first() -> list[Animation]:
            anims: list[Animation] = [FadeIn(title)] if title is not None else []
            if self.p_line_mob is not None:
                anims.append(FadeIn(self.p_line_mob))
            anims.append(FadeIn(self.parents_group))
            anims.append(FadeIn(self.grid_frame) if plan.show == "punnett" else FadeIn(VGroup(self.tree_heads, self.tree_root)))
            return anims

        for nums in self.ph_count_nums.values():     # shown by the counting (after the targets took their full look)
            for t in nums:
                t.set_opacity(0)
        if self.ph_count_nums:
            for t in self.ph_frac_cells:
                t.set_opacity(0)
        steps: list[Any] = [first]
        if not self.manual:
            steps.append(lambda: self.run_form([0, 1]))
            steps.append(lambda: self.run_fill(list(self.cell_mobs) if plan.show == "punnett" else None))
            tables = ["genotypes"] if self.tree_kind == "genotypes" or (self.ge_card is not None and plan.show == "punnett") else []
            tables.append("phenotypes")
            for table in tables:
                steps.append(lambda t=table: self._chain(self.run_count(t) + self.run_ratio(t)))
            if self.chi_card is not None:
                steps.append(lambda: self.run_chi())
        self.reveal(steps, fraction=0.9, cap=MAX_FILL)
        self.finish()

    def _register_square(self) -> None:
        plan = self.plan
        every = list(self.cell_mobs)
        whole = VGroup(self.grid_frame, *self.headers[0], *self.headers[1], *self.cell_mobs.values())
        self.target(("square", "all"), whole, entrance=lambda: self.run_fill(every))
        for i in range(len(plan.eggs)):
            cells = [k for k in every if k[0] == i + 1]
            self.target(f"row{i + 1}", VGroup(self.headers[0][i], *[self.cell_mobs[k] for k in cells]), entrance=lambda c=cells: self.run_fill(c))
        for j in range(len(plan.sperm)):
            cells = [k for k in every if k[1] == j + 1]
            self.target(f"col{j + 1}", VGroup(self.headers[1][j], *[self.cell_mobs[k] for k in cells]), entrance=lambda c=cells: self.run_fill(c))
        for k in every:
            self.target(f"cell{k[0]}.{k[1]}", self.cell_mobs[k], outline=self.cell_tints[k], on_fill=[(self.cell_texts[k], self.cell_tints[k])],
                        entrance=lambda c=k: self.run_fill([c]))
        seen: set[str] = set()
        groups = [(f"cells:{c.label}", list(c.cells)) for c in plan.phenotypes] + [(f"cells:{g.ascii}", list(g.cells)) for g in plan.genotypes]
        for name, cells in groups:
            if name in seen:
                continue
            seen.add(name)
            self.target(name, VGroup(*[self.cell_mobs[k] for k in cells]), on_fill=[(self.cell_texts[k], self.cell_tints[k]) for k in cells],
                        entrance=lambda c=cells: self.run_fill(c))

    def _chain(self, anims: list[Animation]) -> list[Animation]:
        return [Succession(*anims)] if len(anims) > 1 else anims

    # ----- what the actions play ----------------------------------------------------------------

    def form_seconds(self, which: list[int]) -> float:
        return FORM_SECONDS * (1.0 if len(which) == 1 else 1.3)

    def run_form(self, which: list[int]) -> list[Animation]:
        """Each parent's homologues part (segregation) and its gametes fly out of the parent to
        their places (the square's headers, or a row under the parent)."""
        anims: list[Animation] = []
        for k in which:
            if k in self.formed:
                continue
            self.formed.add(k)
            chroms = self.parent_cards[k][0]
            apart = []
            for pair in chroms:
                if len(pair) == 2:
                    gap = pair[0].height * 0.07         # the homologues part a little (segregation) and come back
                    apart.append(pair[0].animate(rate_func=there_and_back).shift(LEFT * gap))
                    apart.append(pair[1].animate(rate_func=there_and_back).shift(RIGHT * gap))
            start = chroms.get_center()
            flights = [FadeIn(chip, target_position=start, scale=0.4) for chip in self.gamete_groups[k]]
            anims.append(Succession(AnimationGroup(*apart), LaggedStart(*flights, lag_ratio=0.25)) if apart else LaggedStart(*flights, lag_ratio=0.25))
        return [AnimationGroup(*anims)] if anims else []

    def fill_seconds(self, cells: list[tuple[int, int]] | None) -> float:
        extra = 0.0 if len(self.formed) == 2 else FORM_SECONDS * 0.6
        if self.plan.show != "punnett":
            return min(MAX_FILL, 1.1 * len(self.plan.tree.levels) + 0.6 + extra)
        todo = [c for c in (cells or list(self.cell_mobs)) if c not in self.filled]
        return min(MAX_FILL, max(MIN_FILL, CELL_SECONDS * len(todo) + 0.6) + extra)

    def run_fill(self, cells: list[tuple[int, int]] | None, by: str = "cell") -> list[Animation]:
        """Fill Punnett cells (the gametes of their row and column moving in) or grow the
        branch diagram level by level; gametes not formed yet are formed first."""
        anims: list[Animation] = list(self.run_form([k for k in (0, 1) if k not in self.formed]))
        if self.plan.show != "punnett":
            grow = self._grow_tree()
            if grow is not None:
                anims.append(grow)
        else:
            todo = [c for c in (cells if cells is not None else list(self.cell_mobs)) if c not in self.filled]
            if todo:
                self.filled.update(todo)
                steps = [(c, self._fill_cell(c)) for c in todo]
                if by in ("row", "column"):
                    groups: dict[int, list[Animation]] = {}
                    for c, a in steps:
                        groups.setdefault(c[0] if by == "row" else c[1], []).append(a)
                    anims.append(LaggedStart(*[AnimationGroup(*g) for g in groups.values()], lag_ratio=0.6))
                else:
                    anims.append(LaggedStart(*[a for _, a in steps], lag_ratio=0.35 if len(steps) > 4 else 0.6))
        if self._complete():
            anims += self._show_notes()
        return self._chain(anims)

    def _complete(self) -> bool:
        if self.plan.show == "punnett":
            return len(self.filled) == len(self.cell_mobs)
        return self.grown >= len(self.plan.tree.levels)

    def _fill_cell(self, c: tuple[int, int]) -> Animation:
        i, j = c
        center = self.cell_centers[c]
        moving = [FadeOut(header[0][1].copy(), target_position=center, scale=0.8) for header in (self.headers[0][i - 1], self.headers[1][j - 1])]
        return AnimationGroup(*moving, FadeIn(self.cell_mobs[c], scale=0.85))

    def _grow_tree(self) -> Animation | None:
        levels = len(self.plan.tree.levels)
        steps = []
        while self.grown < levels:
            lv = self.grown
            self.grown += 1
            group: list[Animation] = [LaggedStart(*[Create(e) for e in self.tree_edges[lv]], lag_ratio=0.1),
                                      LaggedStart(*[FadeIn(self.tree_nodes[i], shift=RIGHT * 0.1) for i in self.tree_levels[lv]], lag_ratio=0.15)]
            steps.append(AnimationGroup(*group))
        return Succession(*steps) if steps else None

    def _show_notes(self) -> list[Animation]:
        if self.notes_mob is None or self.notes_shown:
            return []
        self.notes_shown = True
        return [FadeIn(self.notes_mob)]

    def _place_card(self, name: str) -> list[Animation]:
        """Put a card in the panel under those shown, or alone at the top when it does not fit
        (the others fade out)."""
        card = self.card_mobs[name]
        area = self.panel
        anims: list[Animation] = []
        shown = [self.card_mobs[n] for n in self.cards_on]
        top = min((m.get_bottom()[1] for m in shown), default=area.y1 + 0.35) - 0.35
        if card.height > area.height:
            card.scale(area.height / card.height)
        if shown and top - card.height < area.y0:
            anims.append(AnimationGroup(*[FadeOut(part) for m in shown for part in self.on_screen_parts(m)]))
            self.cards_on = []
            top = area.y1
        card.move_to(np.array([area.x0 + card.width / 2, top - card.height / 2, 0.0]))
        self.cards_on.append(name)
        return anims

    def count_seconds(self, table: str) -> float:
        n = len(self.plan.phenotypes) if table == "phenotypes" else len(self.plan.genotypes)
        if table == self.tree_kind:
            n = len(self.plan.tree.leaves)
        return min(MAX_FILL, 0.6 + CLASS_SECONDS * n)

    def run_count(self, table: str) -> list[Animation]:
        """Count the offspring into the classes: each class's cells flash and its row appears
        (equally likely cells: its fraction counts up cell by cell). Cells not filled yet are
        filled first."""
        if table in self.counted:
            return []
        anims: list[Animation] = []
        if not self._complete():
            anims += self.run_fill(list(self.cell_mobs) if self.plan.show == "punnett" else None)
        self.counted.add(table)
        if table == self.tree_kind:
            return self._chain(anims + self._count_leaves())
        anims += self._place_card(table)
        heads = self.ph_head if table == "phenotypes" else self.ge_head
        rows = self.ph_rows if table == "phenotypes" else self.ge_rows
        classes = self.plan.phenotypes if table == "phenotypes" else self.plan.genotypes
        steps: list[Animation] = [FadeIn(VGroup(*heads))]
        for k, row in enumerate(rows):
            cls = classes[k] if k < len(classes) else None
            parts: list[Animation] = [*self._flash(cls.cells if cls is not None else ()), FadeIn(row, shift=LEFT * 0.1)]
            if table == "phenotypes" and self.ph_count_nums.get(k):
                parts.append(self._ticker(k))
            steps.append(AnimationGroup(*parts))
        anims.append(Succession(*steps))
        return self._chain(anims)

    def _ticker(self, k: int) -> Animation:
        """The class's fraction counting up, one cell at a time, then the final fraction."""
        nums = self.ph_count_nums[k]
        final = self.ph_frac_cells[k]
        holder = VGroup(*nums, final)

        def frame(_: Mobject, alpha: float) -> None:
            idx = min(len(nums) - 1, int(alpha * len(nums)))
            for m, t in enumerate(nums):
                t.set_opacity(1.0 if m == idx and alpha < 1.0 else 0.0)
            final.set_opacity(1.0 if alpha >= 1.0 else 0.0)

        return UpdateFromAlphaFunc(holder, frame, rate_func=linear)

    def _flash(self, cells: Any) -> list[Animation]:
        if self.plan.show != "punnett" or not cells:
            return []
        flashes = []
        for c in cells:      # a frame lit round each cell (animating the tint would draw it over the text)
            box = Rectangle(width=self.cell_w * 0.9, height=self.cell_h * 0.9).move_to(self.cell_centers[c])
            box.set_stroke(self.hi, width=4).set_fill(opacity=0)
            flashes.append(Succession(FadeIn(box, run_time=0.5), FadeOut(box, run_time=0.5)))
        return [LaggedStart(*flashes, lag_ratio=0.1)]

    def ratio_seconds(self, table: str) -> float:
        return RATIO_SECONDS

    def run_ratio(self, table: str) -> list[Animation]:
        """The whole-number ratio: each class's number and the ratio line (the table is
        counted first when it was not)."""
        if table in self.ratios:
            return []
        anims: list[Animation] = list(self.run_count(table)) if table not in self.counted else []
        self.ratios.add(table)
        if table == self.tree_kind:
            cells, line = self.leaf_ratio_cells, self.tree_ratio_line
        else:
            cells = self.ph_ratio_cells if table == "phenotypes" else self.ge_ratio_cells
            line = self.ph_ratio_line if table == "phenotypes" else self.ge_ratio_line
        anims.append(AnimationGroup(LaggedStart(*[FadeIn(c, scale=1.3) for c in cells], lag_ratio=0.15), FadeIn(line, shift=UP * 0.1)))
        return self._chain(anims)

    def chi_seconds(self) -> float:
        return CHI_SECONDS

    def run_chi(self) -> list[Animation]:
        """The chi-square table: observed and expected counts class by class, then χ², df, p,
        the critical value and the verdict."""
        if self.chi_shown or self.chi_card is None:
            return []
        self.chi_shown = True
        anims = self._place_card("chi_square")
        rows = [FadeIn(self.chi_head)] + [FadeIn(r, shift=LEFT * 0.1) for r in self.chi_rows]
        anims.append(Succession(LaggedStart(*rows, lag_ratio=0.3), LaggedStart(*[FadeIn(x) for x in self.chi_foot], lag_ratio=0.4)))
        return self._chain(anims)
