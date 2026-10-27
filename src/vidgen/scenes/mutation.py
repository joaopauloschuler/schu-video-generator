"""``mutation``: a sequence variant on a real coding sequence (DESIGN.md §96.13). The reference
coding strand in codons (base tiles in the reading frame from the ATG, the amino acid under each
codon with its residue number), the variant row made from it by the change — a base swapped, bases
deleted or inserted with the rest sliding through the fixed codon frame (so a frameshift visibly
regroups every codon after it and reaches a premature stop) —, the changed bases and residues
highlighted, and a card with the HGVS ``c.`` and ``p.`` notation, the class (silent, missense,
nonsense, frameshift, in-frame indel, splice site), the amino-acid properties, nonsense-mediated
decay and a legacy name. With exons, a strip of the gene (exons, introns with GT…AG, the window,
the variant) and for a splice-site change the predicted mRNA (exon skipped or intron retained).
The model is ``vidgen.genetics.hgvs`` / ``genetics.mutation``; the action ``mutate`` is in
``scenes/molecular_actions.py``."""

from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import small_size, text_block
from .molecular_draw import Letters, aa_chip, base_tile, codon_box, esc

hg = genetics.hgvs
mu = genetics.mutation

#: Seconds: a variant made; the card.
MUTATE_SECONDS = 3.0
#: Gap between codons, in tile widths.
GAP = 0.42


class _Row:
    """A drawn row: base tiles by window index, codon boxes by slot, chips by slot."""

    def __init__(self) -> None:
        self.tiles: dict[int, VGroup] = {}
        self.boxes: dict[int, Mobject] = {}
        self.chips: dict[int, VGroup] = {}
        self.extra: list[Mobject] = []

    def group(self) -> VGroup:
        return VGroup(*self.boxes.values(), *self.tiles.values(), *self.chips.values(), *self.extra)


@scene("mutation")
class MutationScene(NarratedScene):
    """A sequence variant on a real coding sequence, worked out with the genetic code: the
    reference codons (reading frame from the ATG, amino acids numbered with the initiator Met as
    1) and the variant made from them — substitution (silent, missense, nonsense), deletion,
    duplication, insertion (in frame, or a frameshift with the new codons and the premature stop),
    splice-site change (GT…AG; exon skipping or intron retention, predicted) —, the changed bases and
    amino acids highlighted, and the HGVS notation (c.20A>T p.(Glu7Val); c.1521_1523del
    p.(Phe508del); c.35del p.(Gly12Valfs*2)) checked against the sequence, with the class, notes and
    the legacy name. Reference windows: HBB, CFTR, GJB2; or your own sequence, or a gene: like the
    molecule scene's.

    Action targets: ``title``, ``gene``, ``reference``, ``variant`` (the row), ``variant:<n>``
    (the n-th change made), ``protein``, ``notation``, ``codon:<n>``."""

    outro = 0.5
    target_patterns = ("title", "gene", "reference", "variant", "variant:<n>", "protein", "notation", "codon:<n>")
    #: The action mutate acts on this scene type.
    mutation_actions = True
    mid_still_actions = frozenset({"mutate"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        gene: str | dict[str, Any] | None = None
        """A reference window (HBB, CFTR, GJB2: real coding sequence with its exons), or a gene written like the molecule scene's gene: ({sequence: …, introns: [[a, b]]} or {protein: MVHL…, introns: 1})."""
        sequence: str | None = None
        """Instead of gene: your coding DNA (or mRNA) 5′→3′, from c.1 (the A of the ATG) or from first:."""
        first: int | None = None
        """The c. number of the sequence's first base (a window inside a longer CDS)."""
        exons: list[list[int]] | None = None
        """The coding exons as c. ranges ([[1, 92], [93, 315], [316, 444]]): the gene strip, splice sites, nonsense-mediated decay."""
        first_exon: int | None = None
        """The number of the first exon in exons (11 for a window from exon 11)."""
        length: int | None = None
        """The whole CDS length with its stop codon (judges nonsense-mediated decay)."""
        symbol: str | None = None
        """The gene symbol (italic; checked against the species' nomenclature)."""
        species: str = "human"
        """For the symbol: human, mouse, rat, yeast, fly…"""
        variant: str | dict[str, Any] | list[str | dict[str, Any]] = "c.1A>G"
        """The change in HGVS: c.20A>T, c.1521_1523del, c.35del, c.35dup, c.76_77insT, c.76_77delinsTT, c.92+1G>A; or {c: …, p: p.(Glu7Val) (checked), legacy: Glu6Val, splice: skip}; or a list (made one after another)."""
        splice: Literal["auto", "skip", "retain"] = "auto"
        """A splice-site change's predicted outcome: exon skipping (auto for an internal exon) or intron retention."""
        codes: Literal["three", "one"] = "three"
        """Amino acids as three-letter (Glu) or one-letter (E) codes."""
        stop: Literal["*", "Ter"] = "*"
        """How a stop is written in p. (p.(Arg553*) or p.(Arg553Ter))."""
        codons: int | None = Field(None, ge=3, le=16)
        """Codons shown (default: as many as fit, round the change)."""
        strip: bool = True
        """The gene strip (when exons are known)."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def spec(self) -> dict[str, Any]:
            data: dict[str, Any] = {"variant": self.variant, "splice": self.splice, "codes": self.codes, "stop": self.stop,
                                    "species": self.species}
            for key in ("gene", "sequence", "first", "exons", "first_exon", "length", "symbol"):
                if getattr(self, key) is not None:
                    data[key] = getattr(self, key)
            return data

        def plan(self) -> Any:
            return mu.plan_mutation(self.spec())

        @model_validator(mode="after")
        def _check(self) -> "MutationScene.Params":
            try:
                self.plan()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def gene_symbols(cls, params: Any) -> list[str]:
        """The gene symbol (the reference gene's or ``symbol``): italic in captions, checked by science_naming."""
        symbol = params.plan().symbol
        return [symbol] if symbol else []

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        plan = params.plan()
        names = ["title"] if params.title else []
        if plan.cds.exons and params.strip:
            names.append("gene")
        names += ["reference", "variant"] + [f"variant:{k + 1}" for k in range(len(plan.variants))] + ["protein", "notation"]
        names += [f"codon:{n}" for n in plan.touched_codons()]      # the codons the variants change
        return names

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.plan = p.plan()
        self.ink, self.dim_ink = th.color("text"), th.color("dim")
        self.hi, self.bad, self.good = th.color("highlight"), th.color("accent"), th.color("tertiary")
        self.small = small_size(self, p.size)
        self.tiny = max(readable_size() * 1.02, self.small * 0.85)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.25)
        self.title_mob = title
        cds = self.plan.cds
        self.has_strip = bool(cds.exons) and p.strip
        self.lab_h = self.markup("reference", size=self.small).height
        # rows of a splice-site variant carry no amino-acid chips: they need less height
        self.splice_only = all(v.consequence.edit is None for v in self.plan.variants)
        if self.has_strip:
            spliced = any(v.consequence.edit is None for v in self.plan.variants)
            cap_h = self.markup("c.1", size=self.tiny).height
            strip_h = 0.5 + self.lab_h + cap_h + (0.62 if spliced else 0.0)
            self.strip_area = Region(body.x0, body.y1 - strip_h, body.x1, body.y1)
            body = Region(body.x0, body.y0, body.x1, self.strip_area.y0 - 0.25)
        self._geometry(body)
        if self.side:              # few codons in 16:9: the rows on the left, as large as the height allows, the card beside them
            top = body.y1 - max(0.0, body.height - self.seq_h) * 0.4
            self.seq_area = Region(body.x0, top - self.seq_h, self.side_x, top)
            self.card_area = Region(self.side_x + 0.6, body.y0, body.x1, top)
        else:
            self.seq_area = Region(body.x0, body.y1 - self.seq_h, body.x1, body.y1)
            self.card_area = Region(body.x0, body.y0, body.x1, self.seq_area.y0 - 0.3)
        self._place_rows()
        self.current = -1            # the variant shown
        self.made: set[int] = set()
        self.strip = self._build_strip() if self.has_strip else None
        self._splice_k = 0
        self._splice_ref_index: int | None = None
        self.window = self._window(0)
        self.ref_row = self._build_row(self.window, None, self.ref_y)
        self.ref_label = self._row_label("reference", self.ref_y)
        self.var_row: _Row | None = None
        self.var_label = None
        self.var_holder = VGroup()        # the variant row once it is made (an action target)
        self.card_holder = VGroup()       # the card of the variant shown
        self.card: Mobject | None = None
        self.mrna: Mobject | None = None
        self._register()

    #: A row below its label, in tile widths: tiles 1.08, gap 0.14, chip 0.78, gap 0.06 (the
    #: residue numbers' height is measured: it never falls below the readable size).
    ROW_U = 2.06

    def _geometry(self, body: Any) -> None:
        """Tile size and how many codons fit (letters never below the readable size); the height the
        two rows need (``seq_h``), at most 62 % of the body."""
        h_min = self.markup("<b>A</b>", size=readable_size() * 1.02).height
        lab_h = self.lab_h
        num_h = self.markup("8", size=self.tiny).height * (0.0 if self.splice_only else 1.0)
        self.num_h = num_h
        row_u = (1.5 if self.splice_only else self.ROW_U)
        n = self.params.codons or (12 if not self.is_portrait else 6)
        u_h = (body.height * (0.5 if self.splice_only else 0.56) - 2 * (lab_h + 0.1 + num_h) - 0.3) / (2 * row_u)
        u = min(body.width / (n * (3 + GAP)), u_h, 0.55)
        if u < h_min / 0.62:
            u = h_min / 0.62
            n = max(3, min(n, int(body.width / ((3 + GAP) * u))))
        self.u, self.n_slots = u, n
        self.letters = Letters(self, u * 0.6, self.small)
        ref = self.markup("Glu", size=self.small)
        floor = readable_size() * 1.02 / self.small          # never below the readable size
        self.chip_scale = max(floor, min(1.0, u * 0.78 * 0.62 / ref.height))
        self.row_h = lab_h + 0.1 + row_u * u + num_h
        self.seq_h = 2 * self.row_h + 0.3
        # the card keeps a share of the body: the rows shrink rather than squeeze its notes out
        card_room = max(1.7, body.height * 0.3)
        if self.seq_h > body.height - card_room:
            self.seq_h = max(2 * (lab_h + 0.1 + num_h + row_u * h_min / 0.62) + 0.3, body.height - card_room)
            self.row_h = (self.seq_h - 0.3) / 2
            self.u = u = max(h_min / 0.62, (self.row_h - lab_h - 0.1 - num_h) / row_u)
            self.letters = Letters(self, u * 0.6, self.small)
            self.n_slots = n = max(3, min(n, int(body.width / ((3 + GAP) * u))))
        self.side = False
        self.side_x = body.x1
        if not self.is_portrait:
            # few codons leave most of the width empty: the card beside the rows lets them use the height
            card_w = max(3.8, body.width * 0.37)
            rows_w = body.width - card_w - 0.6
            u_side_h = (body.height - 2 * (lab_h + 0.1 + num_h) - 0.3) / (2 * row_u)
            u_side = min(rows_w / (n * (3 + GAP) - GAP), u_side_h, 0.62)
            if u_side > self.u * 1.15:
                self.side = True
                self.u = u = u_side
                self.letters = Letters(self, u * 0.6, self.small)
                self.chip_scale = max(floor, min(1.0, u * 0.78 * 0.62 / ref.height))
                self.row_h = lab_h + 0.1 + row_u * u + num_h
                self.seq_h = 2 * self.row_h + 0.3
                width = n * (3 + GAP) * u - GAP * u
                self.side_x = body.x0 + max(width, rows_w * 0.8)
                self.x0 = body.x0 + (self.side_x - body.x0 - width) / 2
                return
        width = n * (3 + GAP) * u - GAP * u
        self.x0 = body.center[0] - width / 2

    def _codon_group(self, number: int) -> VGroup:
        """The tiles, box and chip of codon ``number`` in the reference row (its row when it is not
        in the stretch drawn now)."""
        if self.window[0] != "codons":
            return VGroup(self.ref_row.group())
        _, c0, n = self.window
        slot = number - c0
        row = self.ref_row
        if slot not in row.boxes:
            return VGroup(row.group())
        box = row.boxes[slot]
        parts: list[Mobject] = [box] + [t for i, t in row.tiles.items() if box.get_left()[0] <= t.get_x() <= box.get_right()[0]]
        if slot in row.chips:
            parts.append(row.chips[slot])
        return VGroup(*parts)

    def _place_rows(self) -> None:
        top = self.seq_area.y1
        self.ref_y = top - self.lab_h - 0.1 - self.u * 0.54
        self.var_y = self.ref_y - self.row_h - 0.3

    # ----- windows and rows ---------------------------------------------------------------------------

    def _window(self, k: int) -> tuple[str, int, int]:
        """What variant ``k``'s rows show: ``("codons", first codon number, slots)`` or, for a splice
        site, ``("splice", exon border c., slots)``."""
        cons = self.plan.variants[k].consequence
        cds = self.plan.cds
        n = self.n_slots
        a, b = self.plan.codon_range()
        if cons.edit is None:
            return ("splice", cons.dna.start.c, n)
        v = cds.codon_number(cds.first + cons.edit.start)
        span = 1
        pc = cons.protein
        if pc.kind == "frameshift" and pc.fs:
            span = pc.fs + (pc.start or v) - v
        elif pc.kind in ("inframe_del", "inframe_dup", "inframe_delins", "inframe_ins"):
            span = max(1, abs(cons.dna.length_change) // 3 + 1)
        before = 2 if span + 3 <= n else (1 if span + 1 < n else 0)
        start = max(a, min(v - before, b - n + 1))
        return ("codons", start, min(n, b - start + 1))

    def _slot_x(self, slot: int, j: int) -> float:
        u = self.u
        return self.x0 + slot * (3 + GAP) * u + (j + 0.5) * u

    def _row_label(self, text: str, y: float) -> Mobject:
        lab = self.markup(text, size=self.small, color=self.dim_ink)
        return lab.move_to(np.array([self.x0 + lab.width / 2, y + self.u * 0.54 + 0.1 + lab.height / 2, 0]))

    def _chip(self, aa: str, number: int | None, x: float, y: float, changed: bool = False, deleted: bool = False) -> VGroup:
        u = self.u
        if aa == "*":
            text = "Stop" if self.params.codes == "three" else "*"
        else:
            text = hg.aa3(aa) if self.params.codes == "three" else aa
        fill = self.bad if aa == "*" else self.hi
        chip = aa_chip(self, f"<b>{text}</b>" if changed or aa == "*" else text, u * 2.7, u * 0.78, self.small, self.ink,
                       fill, self.hi if changed else self.dim_ink, 0.35 if (changed or aa == "*") else 0.0, self.chip_scale)
        chip.move_to(np.array([x, y - u * 0.54 - u * 0.14 - u * 0.39, 0]))
        parts: list[Mobject] = [chip]
        if number is not None:
            num = self.markup(str(number), size=self.tiny, color=self.dim_ink)
            num.next_to(chip, DOWN, buff=u * 0.06)
            parts.append(num)
        if deleted:
            parts.append(Line(chip.get_left() + RIGHT * 0.05, chip.get_right() + LEFT * 0.05).set_stroke(self.bad, width=3))
        return VGroup(*parts)

    def _build_row(self, window: tuple[str, int, int], k: int | None, y: float) -> _Row:
        """The reference row (``k`` None) or variant ``k``'s row, at height ``y``."""
        if window[0] == "splice":
            return self._splice_row(window, k, y)
        cds = self.plan.cds
        f0 = cds.frame_start
        n0 = cds.codon_number(cds.first + f0)
        _, c0, n = window
        cons = self.plan.variants[k].consequence if k is not None else None
        seq = cons.mut_seq if cons is not None else cds.seq
        prot = cons.mut_protein if cons is not None else hg.translation(cds.seq, f0)
        row = _Row()
        base0 = f0 + 3 * (c0 - n0)
        for slot in range(n):
            for j in range(3):
                i = base0 + 3 * slot + j
                if i >= len(seq):
                    continue
                t = base_tile(self.letters, seq[i], self.u)
                t.move_to(np.array([self._slot_x(slot, j), y, 0]))
                row.tiles[i] = t
            tiles = [row.tiles[i] for i in range(base0 + 3 * slot, base0 + 3 * slot + 3) if i in row.tiles]
            if len(tiles) == 3:
                row.boxes[slot] = codon_box(tiles, self.u, self.dim_ink)
            r = c0 - n0 + slot
            if r < len(prot) and len(tiles) == 3:
                row.chips[slot] = self._chip(prot[r], c0 + slot, self._slot_x(slot, 1), y, *self._chip_flags(k, c0 + slot, prot[r]))
        return row

    def _chip_flags(self, k: int | None, number: int, aa: str) -> tuple[bool, bool]:
        """(changed, deleted) for the chip of residue ``number`` in row ``k``."""
        if k is None:
            return False, False
        pc = self.plan.variants[k].consequence.protein
        s = pc.start or 0
        if pc.kind in ("missense", "nonsense"):
            return number == s, False
        if pc.kind == "frameshift":
            return number >= s, False
        if pc.kind in ("inframe_ins", "inframe_dup"):
            n_new = len(pc.alt)
            lo = (pc.end or s) if pc.kind == "inframe_ins" else (pc.end or s) + 1
            return lo <= number < lo + n_new, False
        if pc.kind == "inframe_delins":
            return s <= number < s + len(pc.alt), False
        if pc.kind == "stop_loss":
            return number >= s, False
        if pc.kind == "start_loss":
            return number == 1, False
        return False, False

    def _ref_marks(self, k: int) -> list[Mobject]:
        """On the reference row: the bases the change replaces or removes, the gap an insertion goes
        into, the residues lost."""
        cons = self.plan.variants[k].consequence
        out: list[Mobject] = []
        row = self.ref_row
        if cons.edit is None:
            idx = self._splice_ref_index
            if idx is not None and idx in row.tiles:
                out.append(SurroundingRectangle(row.tiles[idx], buff=self.u * 0.06, corner_radius=self.u * 0.12).set_stroke(self.hi, width=4))
            return out
        e = cons.edit
        for i in range(e.start, e.end):
            if i in row.tiles:
                out.append(SurroundingRectangle(row.tiles[i], buff=self.u * 0.06, corner_radius=self.u * 0.12).set_stroke(self.bad if not e.alt else self.hi, width=4))
        if e.start == e.end and (e.start in row.tiles or e.start - 1 in row.tiles):
            ref_tile = row.tiles.get(e.start) or row.tiles.get(e.start - 1)
            x = ref_tile.get_left()[0] - self.u * 0.05 if e.start in row.tiles else ref_tile.get_right()[0] + self.u * 0.05
            y = ref_tile.get_top()[1] + self.u * 0.05
            out.append(Triangle().scale(self.u * 0.16).rotate(PI).move_to(np.array([x, y + self.u * 0.12, 0]))
                       .set_fill(self.hi, opacity=1).set_stroke(width=0))
        pc = cons.protein
        if pc.kind in ("inframe_del", "inframe_delins") and pc.start is not None:
            _, c0, n = self.window
            for number in range(pc.start, (pc.end or pc.start) + 1):
                slot = number - c0
                if slot in row.chips:
                    chip = row.chips[slot][0]
                    out.append(Line(chip.get_left() + RIGHT * 0.05, chip.get_right() + LEFT * 0.05).set_stroke(self.bad, width=3))
        return out

    # ----- splice rows ----------------------------------------------------------------------------------

    def _splice_tokens(self, k: int, mutant: bool) -> list[tuple[str, str, int | None]]:
        """(base, 'exon' / 'intron' / 'gap', c. number) left to right round the exon border."""
        cds = self.plan.cds
        cons = self.plan.variants[k].consequence
        pos = cons.dna.start
        donor = pos.offset > 0
        n_ex = max(3, min(9, 3 * self.n_slots - 7))
        intr: list[tuple[str, str, int | None]] = []
        known = [cds.intron_base(pos.c, (o if donor else -o)) for o in range(1, 7)]
        count = 2 + sum(1 for b in known[2:] if b is not None)
        offs = list(range(1, count + 1))
        for o in offs:
            off = o if donor else -o
            b = cds.intron_base(pos.c, off) or {1: "G", 2: "T", -1: "G", -2: "A"}[off]
            if mutant and off == pos.offset:
                b = cons.dna.alt
            intr.append((b, "intron", off))
        if not donor:
            intr.reverse()
        if donor:
            exon = [(cds.base(c), "exon", c) for c in range(max(cds.first, pos.c - n_ex + 1), pos.c + 1)]
            return exon + intr + [("…", "gap", None)]
        exon = [(cds.base(c), "exon", c) for c in range(pos.c, min(cds.last, pos.c + n_ex - 1) + 1)]
        return [("…", "gap", None)] + intr + exon

    def _splice_row(self, window: tuple[str, int, int], k: int | None, y: float) -> _Row:
        kk = k if k is not None else self._splice_k
        tokens = self._splice_tokens(kk, k is not None)
        row = _Row()
        lab_h = self.markup("intron", size=self.tiny).height
        u_min = self.markup("<b>A</b>", size=readable_size() * 1.02).height / 0.6
        room = self.row_h - self.lab_h - 0.14 - lab_h          # tiles and the exon / intron labels fit the row
        u = max(u_min, min(self.u * 1.5, self.seq_area.width / (len(tokens) + 2), room / 1.35))
        buff = min(u * 0.25, max(0.04, room - 1.08 * u))
        if not hasattr(self, "splice_letters"):
            self.splice_letters = Letters(self, u * 0.6, self.small)
        width = len(tokens) * u + u * 0.6
        x = self.seq_area.center[0] - width / 2
        cds = self.plan.cds
        self._splice_ref_index = None
        pos = self.plan.variants[kk].consequence.dna.start
        exon_tiles: list[tuple[int, Mobject]] = []
        for idx, (b, kind, c) in enumerate(tokens):
            if kind == "gap":
                m = self.markup("…", size=self.small * 1.3, color=self.dim_ink).move_to(np.array([x + u / 2, y, 0]))
                row.extra.append(m)
                x += u
                continue
            if kind == "intron" and idx > 0 and tokens[idx - 1][1] == "exon" or kind == "exon" and idx > 0 and tokens[idx - 1][1] == "intron":
                x += u * 0.6
            t = base_tile(self.splice_letters, b, u, lower=kind == "intron", ink=self.ink).move_to(np.array([x + u / 2, y, 0]))
            row.tiles[idx] = t
            if kind == "intron" and c == pos.offset:
                self._splice_ref_index = idx
                if k is not None:
                    row.extra.append(SurroundingRectangle(t, buff=u * 0.06, corner_radius=u * 0.12).set_stroke(self.hi, width=4))
            if kind == "exon":
                exon_tiles.append((c, t))
            x += u
        # codon boxes round the whole codons among the exonic bases (a codon split by the border: a partial box)
        groups: dict[int, list[Mobject]] = {}
        for c, t in exon_tiles:
            groups.setdefault(cds.codon_number(c), []).append(t)
        for num, tiles in groups.items():
            row.boxes[num] = codon_box(tiles, u, self.dim_ink)
            if len(tiles) < 3:
                row.boxes[num] = DashedVMobject(row.boxes[num], num_dashes=10).set_stroke(self.dim_ink, width=1.6)
        intr_tiles = [row.tiles[i] for i, tk in enumerate(tokens) if tk[1] == "intron" and i in row.tiles]
        if intr_tiles:
            lab = self.markup("intron", size=self.tiny, color=self.dim_ink).next_to(VGroup(*intr_tiles), DOWN, buff=buff)
            ex = self.markup(f"exon {cds.first_exon + (cds.exon_of(exon_tiles[0][0]) or 0)}", size=self.tiny, color=self.dim_ink)
            ex.next_to(VGroup(*[t for _, t in exon_tiles]), DOWN, buff=buff)
            row.extra += [lab, ex]
        if k is None:
            first = self.markup(f"c.{exon_tiles[0][0]}", size=self.tiny, color=self.dim_ink)
            first.next_to(exon_tiles[0][1], UP, buff=u * 0.12)
            row.extra.append(first)
        return row

    # ----- the gene strip -------------------------------------------------------------------------------

    def _strip_geometry(self, area: Any) -> tuple[list[tuple[float, float]], float]:
        cds = self.plan.cds
        n = len(cds.exons)
        partial_left = cds.exons[0][0] != 1
        partial_right = cds.length is None or cds.exons[-1][1] < cds.length
        lead = 0.5 if partial_left else 0.0
        tail = 0.5 if partial_right else 0.0
        unit = area.width / (n * 1.0 + (n - 1) * 0.55 + lead + tail + 0.1)
        x = area.x0 + lead * unit
        spans = []
        for _ in range(n):
            spans.append((x, x + unit))
            x += unit * 1.55
        return spans, unit

    def _c_x(self, spans: list[tuple[float, float]], c: int) -> float:
        cds = self.plan.cds
        for (a, b), (x0, x1) in zip(cds.exons, spans):
            if a <= c <= b:
                return x0 + (x1 - x0) * ((c - a + 0.5) / (b - a + 1))
        return spans[0][0]

    def _build_strip(self) -> VGroup:
        area = self.strip_area
        cds = self.plan.cds
        spans, unit = self._strip_geometry(area)
        self.strip_spans = spans
        h = min(0.4, max(0.28, self.lab_h * 1.5))
        y = area.y1 - 0.22 - h / 2
        self.strip_y, self.strip_h = y, h
        parts: list[Mobject] = []
        self.exon_boxes: list[Mobject] = []
        for k, (x0, x1) in enumerate(spans):
            box = RoundedRectangle(width=x1 - x0, height=h, corner_radius=h * 0.2).move_to(np.array([(x0 + x1) / 2, y, 0]))
            box.set_fill(self.theme.color("primary"), opacity=0.35).set_stroke(self.theme.color("primary"), width=2)
            lab = self.markup(f"exon {cds.first_exon + k}", size=self.tiny, color=self.ink)
            if lab.width > (x1 - x0) * 0.9:
                lab.scale((x1 - x0) * 0.9 / lab.width)
            lab.move_to(box)
            self.exon_boxes.append(VGroup(box, lab))
            parts.append(self.exon_boxes[-1])
            if k + 1 < len(spans):
                nx = spans[k + 1][0]
                line = Line(np.array([x1, y, 0]), np.array([nx, y, 0])).set_stroke(self.dim_ink, width=2.5)
                parts.append(line)
                gt = self.markup("GT", size=self.tiny, color=self.dim_ink).next_to(np.array([x1, y, 0]), UR, buff=0.04)
                ag = self.markup("AG", size=self.tiny, color=self.dim_ink).next_to(np.array([nx, y, 0]), UL, buff=0.04)
                if gt.width + ag.width + 0.08 <= nx - x1:      # only where the intron's gap has room
                    parts += [gt, ag]
        if cds.exons[0][0] != 1:
            parts.append(self.markup("…", size=self.small, color=self.dim_ink).next_to(self.exon_boxes[0], LEFT, buff=0.12))
        if cds.length is None or cds.exons[-1][1] < cds.length:
            parts.append(self.markup("…", size=self.small, color=self.dim_ink).next_to(self.exon_boxes[-1], RIGHT, buff=0.12))
        # the window shown
        xa, xb = self._c_x(spans, cds.first), self._c_x(spans, cds.last)
        yb = y - h / 2 - 0.12
        bracket = VGroup(Line(np.array([xa, yb, 0]), np.array([xb, yb, 0])), Line(np.array([xa, yb, 0]), np.array([xa, yb + 0.08, 0])),
                         Line(np.array([xb, yb, 0]), np.array([xb, yb + 0.08, 0]))).set_stroke(self.dim_ink, width=2)
        name = self.plan.symbol
        tx = (f"<i>{esc(name)}</i>  " if name else "") + (self.plan.transcript or "") + f"  c.{cds.first}–{cds.last} shown"
        cap = self.markup(tx.strip(), size=self.tiny, color=self.dim_ink)
        if cap.width > area.width:
            cap.scale(area.width / cap.width)
        cap.next_to(bracket, DOWN, buff=0.06)
        cap.set_x(min(max(cap.get_x(), area.x0 + cap.width / 2), area.x1 - cap.width / 2))
        parts += [bracket, cap]
        self.strip_bottom = cap.get_bottom()[1]
        return VGroup(*parts)

    def _strip_marker(self, k: int) -> Mobject:
        cons = self.plan.variants[k].consequence
        pos = cons.dna.start
        spans = self.strip_spans
        x = self._c_x(spans, pos.c)
        if pos.offset:
            cds = self.plan.cds
            ex = cds.exon_of(pos.c) or 0
            x0, x1 = spans[ex]
            x = x1 + 0.12 if pos.offset > 0 else x0 - 0.12
        tip = np.array([x, self.strip_y + self.strip_h / 2 + 0.02, 0])
        tri = Triangle().scale(0.09).rotate(PI).move_to(tip + UP * 0.1).set_fill(self.hi, opacity=1).set_stroke(width=0)
        return tri

    def _mrna_strip(self, k: int) -> Mobject | None:
        """The predicted mRNA of a splice-site change: the exons joined, one skipped or an intron
        kept."""
        cons = self.plan.variants[k].consequence
        if cons.skipped_exon is None and cons.retained_intron is None:
            return None
        spans = self.strip_spans
        cds = self.plan.cds
        h = self.strip_h * 0.8
        y = self.strip_bottom - 0.2 - h / 2
        parts: list[Mobject] = []
        x = spans[0][0]
        unit = spans[0][1] - spans[0][0]
        for e in range(len(spans)):
            if e == cons.skipped_exon:
                if parts:
                    seam = Line(np.array([x, y - h * 0.65, 0]), np.array([x, y + h * 0.65, 0])).set_stroke(self.bad, width=3)
                    parts.append(seam)
                continue
            box = RoundedRectangle(width=unit, height=h, corner_radius=h * 0.2).move_to(np.array([x + unit / 2, y, 0]))
            box.set_fill(self.theme.color("primary"), opacity=0.35).set_stroke(self.theme.color("primary"), width=2)
            parts.append(VGroup(box, self.markup(str(cds.first_exon + e), size=self.tiny, color=self.ink).move_to(box)))
            x += unit
            if e == cons.retained_intron:
                kept = Rectangle(width=unit * 0.55, height=h * 0.8).move_to(np.array([x + unit * 0.275, y, 0]))
                kept.set_fill(self.bad, opacity=0.3).set_stroke(self.bad, width=2)
                parts.append(VGroup(kept, self.markup("intron", size=self.tiny, color=self.ink).move_to(kept).scale(0.9)))
                x += unit * 0.55
        what = (f"exon {cds.first_exon + cons.skipped_exon} skipped" if cons.skipped_exon is not None
                else f"intron {cds.first_exon + (cons.retained_intron or 0)} retained")
        lab = self.markup(f"mRNA (predicted): {what}", size=self.tiny, color=self.dim_ink)
        lab.next_to(VGroup(*parts), RIGHT, buff=0.2)
        if lab.get_right()[0] > self.strip_area.x1:
            lab.scale(max(0.6, (self.strip_area.x1 - lab.get_left()[0]) / lab.width))
        if lab.get_right()[0] > self.strip_area.x1:
            lab.next_to(VGroup(*parts), DOWN, buff=0.06).align_to(VGroup(*parts), LEFT)
        parts.append(lab)
        return VGroup(*parts)

    # ----- the card ------------------------------------------------------------------------------------

    def _build_card(self, k: int) -> VGroup:
        """The card; its notes are dropped one by one rather than shrunk below the readable size."""
        cons = self.plan.variants[k].consequence
        notes = list(cons.notes) + ([self.plan.variants[k].note] if self.plan.variants[k].note else [])
        extras = ["big", "rna", "legacy"]
        while True:
            card = self._card_body(k, notes, extras)
            if card.height <= self.card_area.height:
                break
            if notes:
                notes = notes[:-1]
            elif extras:
                extras = extras[:-1]
            else:
                break
        area = self.card_area
        if card.height > area.height:
            card.scale(area.height / card.height)
        y = area.y1 - card.height / 2 if not self.is_portrait else max(area.center[1], area.y1 - card.height / 2 - 0.4)
        if self.side:              # level with the reference row's label
            y = area.y1 - card.height / 2
        card.move_to(np.array([area.x0 + card.width / 2, y, 0]))
        return card

    def _card_body(self, k: int, notes: list[str], extras: list[str]) -> VGroup:
        view = self.plan.variants[k]
        cons = view.consequence
        area = self.card_area
        size = self.small
        name = f"<i>{esc(self.plan.symbol)}</i> " if self.plan.symbol else ""
        big = size * (1.5 if "big" in extras else 1.15)
        head = self.markup(f"<b>{name}{esc(view.c_text)}</b>", size=big, color=self.ink)
        if head.width > area.width and big > size * 1.15:          # a narrow column: the notation at the smaller size
            big = size * 1.15
            head = self.markup(f"<b>{name}{esc(view.c_text)}</b>", size=big, color=self.ink)
        ptext = self.markup(f"<b>{esc(view.p_text)}</b>", size=big, color=self.hi if cons.kind != "synonymous" else self.ink)
        kind = cons.label
        tag_color = self.bad if cons.kind in ("nonsense", "frameshift", "start_loss", "splice_donor", "splice_acceptor") else self.hi
        tag = self.markup(f"<b>{esc(kind)}</b>", size=size, color=tag_color)
        left_parts: list[Mobject] = [head, ptext, tag]
        if cons.rna and "rna" in extras:
            left_parts.append(self.markup(esc(cons.rna), size=size, color=self.ink))
        left = VGroup(*left_parts).arrange(DOWN, buff=0.12, aligned_edge=LEFT)
        # the notes (and the legacy name) stand beside the notation, so the card stays shallow
        texts = ([f"legacy: {esc(view.legacy)}"] if view.legacy and "legacy" in extras else []) + [esc(n) for n in notes]
        if self.is_portrait or self.side:
            width = area.width
            right = VGroup(*[text_block(self, t, width, size * 0.92, color=self.ink) for t in texts]).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
            if texts:
                right.next_to(left, DOWN, buff=0.22, aligned_edge=LEFT)
        else:
            lw = max(left.width, area.width * 0.4)
            width = area.width - lw - 0.5
            right = VGroup(*[text_block(self, t, width, size * 0.92, color=self.ink) for t in texts]).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
            if texts:
                right.next_to(left, RIGHT, buff=0.5, aligned_edge=UP)
                right.set_x(left.get_left()[0] + lw + 0.5 + right.width / 2)
        if not texts:
            right = VGroup()
        card = VGroup(left, right)
        if card.width > area.width:
            card.scale(area.width / card.width)
        return card

    # ----- targets and steps --------------------------------------------------------------------------

    def _register(self) -> None:
        title = self.title_mob
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        if self.strip is not None:
            strip = self.strip
            self.target("gene", strip, entrance=lambda: [FadeIn(strip)])
        ref = VGroup(self.ref_row.group(), self.ref_label)
        self.target("reference", ref, entrance=lambda: self.run_reference())
        # the variant row and the card are made as the scene plays: their targets are the holders
        # they are put into
        self.target("variant", self.var_holder, entrance=lambda: self.run_mutate(0))
        for k in range(len(self.plan.variants)):
            self.target(f"variant:{k + 1}", self.var_holder, entrance=lambda k=k: self.run_mutate(k))
        self.target("protein", VGroup(*self.ref_row.chips.values()))
        self.target("notation", self.card_holder, entrance=lambda: self.run_card(max(0, self.current)))
        for number in self.plan.touched_codons():
            self.target(f"codon:{number}", self._codon_group(number))
        held: set[str] = set()
        for use in self.action_uses("reveal"):
            held.update(use.config.targets())
        manual = bool(self.action_uses("mutate")) or any(t.startswith(("variant", "notation")) for t in held)

        def first() -> list[Animation]:
            anims: list[Animation] = [FadeIn(title)] if title is not None else []
            if self.strip is not None and "gene" not in held:
                anims.append(FadeIn(self.strip))
            if "reference" not in held:
                anims += self.run_reference()
            return anims

        steps: list[Any] = [first]
        if not manual:
            for k in range(len(self.plan.variants)):
                steps.append(lambda k=k: self.run_mutate(k))
        self.reveal(steps, fraction=0.88, cap=MUTATE_SECONDS + 1.5)
        self.finish()

    def run_reference(self) -> list[Animation]:
        if getattr(self, "ref_shown", False):
            return []
        self.ref_shown = True
        row = self.ref_row
        anims: list[Animation] = [FadeIn(self.ref_label), FadeIn(VGroup(*row.boxes.values(), *row.tiles.values(), *row.extra))]
        if row.chips:
            anims.append(LaggedStart(*[FadeIn(c, shift=UP * 0.05) for c in row.chips.values()], lag_ratio=0.08))
        return [AnimationGroup(*anims)]

    def mutate_seconds(self) -> float:
        return MUTATE_SECONDS

    def run_mutate(self, k: int) -> list[Animation]:
        """Make variant ``k`` from the reference: the variant row (a copy of the reference) changes
        base by base through the fixed codon frame, the amino acids follow, the card says what it is."""
        if k in self.made:
            return []
        self.made.add(k)
        pre: list[Animation] = list(self.run_reference())
        cons = self.plan.variants[k].consequence
        out: list[Animation] = []
        window = self._window(k)
        if window != self.window:          # another stretch of the sequence: the reference row follows
            old = self.ref_row
            self.window = window
            if window[0] == "splice":
                self._splice_k = k
            self.ref_row = self._build_row(window, None, self.ref_y)
            out.append(AnimationGroup(FadeOut(old.group()), FadeIn(self.ref_row.group())))
        elif window[0] == "splice":
            self._splice_k = k
        # clear what the last variant left
        olds = [m for m in (self.var_row.group() if self.var_row else None, self.card, getattr(self, "ref_marks", None),
                            getattr(self, "marker", None), self.mrna) if m is not None]
        if olds:
            out.append(AnimationGroup(*[FadeOut(m) for m in olds]))
        self.current = k
        new_row = self._build_row(window, k, self.var_y)
        if self.var_label is None:
            self.var_label = self._row_label("variant", self.var_y)
            out.append(FadeIn(self.var_label))
        marks = VGroup(*self._ref_marks(k))
        self.ref_marks = marks
        appear, change = self._change(new_row, cons)
        out.append(AnimationGroup(appear, *([Create(marks)] if len(marks) else [])))
        out.append(change)
        self.var_row = new_row
        self.var_holder.remove(*self.var_holder.submobjects)
        self.var_holder.add(new_row.group())
        if self.strip is not None:
            marker = self._strip_marker(k)
            self.marker = marker
            out.append(FadeIn(marker, shift=DOWN * 0.1))
            mrna = self._mrna_strip(k)
            if mrna is not None:
                self.mrna = mrna
                out.append(FadeIn(mrna, shift=DOWN * 0.1))
        out += self.run_card(k)
        return [Succession(*pre, *out)]

    def _change(self, new_row: _Row, cons: Any) -> tuple[Animation, Animation]:
        """A copy of the reference appears in the variant row (first animation) and becomes the
        variant (second): replaced or removed bases leave, the rest slide to their new places in
        the codon frame, new bases come in; the chips change."""
        u = self.u
        down = DOWN * (self.ref_y - self.var_y)
        if cons.edit is None:              # a splice site: the one base swaps
            copy = self.ref_row.group().copy().shift(down)
            return FadeIn(copy, shift=DOWN * 0.15), AnimationGroup(FadeOut(copy), FadeIn(new_row.group()))
        e = cons.edit
        ref = self.ref_row
        old_tiles = {i: t.copy().shift(down) for i, t in ref.tiles.items()}
        leave, moves, enter = [], [], []
        shift = len(e.alt) - (e.end - e.start)
        targets: dict[int, VGroup] = {}
        for i, t in old_tiles.items():
            if e.start <= i < e.end:
                leave.append(FadeOut(t, shift=DOWN * u * 0.6))
                continue
            m = i if i < e.start else i + shift
            if m in new_row.tiles:
                moves.append(t.animate.move_to(new_row.tiles[m]))
                targets[m] = t
            else:
                leave.append(FadeOut(t))
        for m, t in new_row.tiles.items():
            if m in targets:
                continue
            new = e.start <= m < e.start + len(e.alt)
            enter.append(FadeIn(t, shift=DOWN * u * 0.6 if new else LEFT * u * 0.4, scale=1.3 if new else 1.0))
        rings: list[Mobject] = [SurroundingRectangle(new_row.tiles[m], buff=u * 0.06, corner_radius=u * 0.12).set_stroke(self.hi, width=4)
                                for m in range(e.start, e.start + len(e.alt)) if m in new_row.tiles]
        if not e.alt and e.start in new_row.tiles:          # where the deleted bases were: a tick between the tiles
            t = new_row.tiles[e.start]
            x = t.get_left()[0] - u * 0.05
            rings.append(Line(np.array([x, t.get_bottom()[1] - u * 0.08, 0]), np.array([x, t.get_top()[1] + u * 0.08, 0]))
                         .set_stroke(self.bad, width=4))
        new_row.extra += rings
        boxes = VGroup(*new_row.boxes.values())
        chips_old = VGroup(*[c.copy().shift(down) for c in ref.chips.values()])
        appear = FadeIn(VGroup(boxes, *old_tiles.values(), chips_old), shift=DOWN * 0.15)
        steps: list[Animation] = []
        if leave:
            steps.append(AnimationGroup(*leave))
        steps.append(AnimationGroup(*moves, *enter))
        if rings:
            steps.append(AnimationGroup(*[Create(r) for r in rings]))
        steps.append(AnimationGroup(FadeOut(chips_old), LaggedStart(*[FadeIn(c, scale=1.15) for c in new_row.chips.values()], lag_ratio=0.06)))
        # the moved tiles stand in for the row's tiles from now on
        for m, t in targets.items():
            new_row.tiles[m] = t
        return appear, Succession(*steps)

    def run_card(self, k: int) -> list[Animation]:
        card = self._build_card(k)
        anims: list[Animation] = []
        if self.card is not None and self.card in self.mobjects:
            anims.append(FadeOut(self.card))
        self.card = card
        self.card_holder.remove(*self.card_holder.submobjects)
        self.card_holder.add(card)
        left, right = card.submobjects
        anims.append(LaggedStart(*[FadeIn(m, shift=UP * 0.06) for m in left], *([FadeIn(right)] if len(right) else []), lag_ratio=0.25))
        return anims
