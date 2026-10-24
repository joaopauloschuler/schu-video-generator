"""``karyotype``: a human karyotype from its ISCN notation (DESIGN.md §96.10). ``show:
karyogram`` arranges the chromosomes in pairs 1–22, X, Y by the Denver groups A–G (centromeres on
one line per row, numbers under the pairs) with schematic G-band ideograms; the changes the
notation names are highlighted (an extra copy boxed, a missing one as a dashed ghost, a derivative
with its changed stretch marked). ``show: ideogram`` draws the chromosomes involved large with
their p and q arms and the bands named, and plays each structural change as an edit of the
normal chromosomes: a deletion's segment falls away, a duplication's is copied in, an
inversion's turns round, a reciprocal translocation's distal segments swap, a Robertsonian
translocation's long arms join while the short arms are lost. A card writes the notation and
reads it (count, sex chromosomes, each change, the condition when it is a classic one). The
model is ``vidgen.genetics.karyotype``; the drawing ``scenes/karyotype_draw.py``; the action
``rearrange`` is in ``scenes/karyotype_actions.py``."""

from functools import lru_cache
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import small_size, text_block
from .karyotype_draw import WIDTH_SHARE, ChromosomeDrawing, segment_piece

kt = genetics.karyotype

#: Karyogram rows: the X with group C (its size), the Y with group G (as in the Denver groups).
ROWS_WIDE = (("1", "2", "3", "4", "5"), ("6", "7", "8", "9", "10", "11", "12", "X"), ("13", "14", "15", "16", "17", "18"),
             ("19", "20", "21", "22", "Y"))
ROWS_TALL = (("1", "2", "3"), ("4", "5", "6", "7"), ("8", "9", "10", "11", "12", "X"), ("13", "14", "15", "16", "17", "18"),
             ("19", "20", "21", "22", "Y"))
#: Chromosome width as a share of chromosome 1's length when the width allows (a metaphase
#: chromosome is about a seventh as wide as long; ideograms are drawn a little slimmer).
WIDE_SHARE = 0.125
#: Seconds: one structural edit; a highlight.
EDIT_SECONDS, MARK_SECONDS = 2.6, 1.2
STRUCTURAL = ("del", "dup", "inv", "t", "rob")


@lru_cache(maxsize=32)
def _parsed(text: str) -> Any:
    return kt.parse_karyotype(text)


@scene("karyotype")
class KaryotypeScene(NarratedScene):
    """A human karyotype from its ISCN notation (46,XX; 47,XY,+21; 45,X; 47,XXY;
    46,XY,del(5)(p15.2); 46,XX,t(9;22)(q34;q11.2); 45,XX,rob(14;21)(q10;q10)…), parsed and
    checked (the count against the chromosomes listed, the bands against each arm's last band).
    karyogram: the pairs 1–22, X, Y in the Denver groups A–G, schematic G-banded ideograms with
    correct relative lengths and centromere positions (satellites on 13, 14, 15, 21, 22), the
    changes highlighted. ideogram: the chromosomes involved, large, p and q arms and the bands
    named; structural changes play as edits of the normal chromosomes. A card writes the notation
    and reads it. Band positions are schematic (ISCN names, not measured ideogram positions).

    Action targets: ``title``, ``chromosomes``, ``group:<A…G>`` (karyogram), ``chromosome:<1…22,
    X, Y>``, ``change:<n>`` (the n-th change in the notation), ``notation``, ``reading``,
    ``band:<7q31.2>``."""

    outro = 0.5
    target_patterns = ("title", "chromosomes", "group:<A…G>", "chromosome:<name>", "change:<n>", "changes", "notation", "reading",
                       "band:<band>")
    #: The action rearrange acts on this scene type.
    karyotype_actions = True
    mid_still_actions = frozenset({"rearrange"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        karyotype: str = "46,XX"
        """ISCN: count, sex chromosomes, changes — 46,XY; 47,XX,+21; 45,X; 47,XXY; 46,XY,del(5)(p15.2); 46,XX,dup(1)(q21q32); 46,XY,inv(9)(p12q13); 46,XX,t(9;22)(q34;q11.2); 45,XX,rob(14;21)(q10;q10)."""
        show: Literal["auto", "karyogram", "ideogram"] = "auto"
        """karyogram: every chromosome in pairs by group; ideogram: the chromosomes involved (or those in chromosomes:), large, with structural changes played as edits; auto: ideogram when chromosomes is given or every change is structural, else karyogram."""
        chromosomes: list[str | int] | None = None
        """ideogram: which chromosomes to draw (all their copies), e.g. [7] or [9, 22]; default: those the changes involve."""
        bands: dict[str, str] | list[str] | None = None
        """Bands to label (ideogram), with an optional text: {7q31.2: CFTR, Xq28: F8} or [21q22]."""
        notation: bool = True
        """The card with the notation and its reading."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def parsed(self) -> Any:
            return _parsed(self.karyotype.strip())

        def view(self) -> str:
            if self.show != "auto":
                return self.show
            k = self.parsed()
            if self.chromosomes:
                return "ideogram"
            kinds = {a.kind for a in k.abnormalities}
            return "ideogram" if kinds and kinds <= set(STRUCTURAL) else "karyogram"

        def names(self) -> list[str]:
            return [kt.chromosome_name(c, f"chromosomes[{i}]") for i, c in enumerate(self.chromosomes or [])]

        def labels(self) -> list[tuple[Any, str]]:
            return kt.band_labels(self.bands) if self.bands else []

        @model_validator(mode="after")
        def _check(self) -> "KaryotypeScene.Params":
            try:
                self.parsed()
                self.names()
                self.labels()
                if self.chromosomes and self.show == "karyogram":
                    raise VidgenError("chromosomes: picks the chromosomes of show: ideogram (a karyogram shows them all)")
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        k = params.parsed()
        names = ["title"] if params.title else []
        names += ["chromosomes"]
        if params.view() == "karyogram":
            names += [f"group:{g}" for g in kt.GROUPS]
            slots = [c for c in kt.NAMES if k.copies[c]]
        else:
            slots = cls._ideogram_slots(params)
        names += [f"chromosome:{c}" for c in slots]
        names += [f"change:{i + 1}" for i in range(len(k.abnormalities))] + (["changes"] if k.abnormalities else [])
        if params.notation:
            names += ["notation", "reading"]
        names += [f"band:{ref.label}" for ref, _ in params.labels()]
        return names

    @staticmethod
    def _ideogram_slots(params: Any) -> list[str]:
        k = params.parsed()
        if params.chromosomes:
            return params.names()
        out = k.changed_slots()
        for ref, _ in params.labels():
            if ref.chrom not in out:
                out.append(ref.chrom)
        return out or ["1"]

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.k = p.parsed()
        self.view = p.view()
        self.ink = th.color("text")
        self.dim_ink = th.color("dim")
        self.hi = th.color("highlight")
        self.accent = th.color("accent")
        self.bg = th.background
        self.small = small_size(self, p.size)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.25)
        self.title_mob = title
        self._regions(body)
        self.tints = {c: self.accent for c in kt.NAMES}
        self.edited: set[int] = set()
        self.marked: set[int] = set()
        self.change_mobs: dict[int, VGroup] = {i: VGroup() for i in range(len(self.k.abnormalities))}
        if self.view == "karyogram":
            self._build_karyogram()
        else:
            self._build_ideograms()
        self._build_card()
        self._register()

    def _regions(self, body: Any) -> None:
        if not self.params.notation:
            self.draw_area, self.card_area = body, None
            return
        if not self.is_portrait:
            split = body.x0 + body.width * (0.66 if self.view == "karyogram" else 0.6)
            self.draw_area = Region(body.x0, body.y0, split, body.y1)
            self.card_area = Region(split + 0.35, body.y0, body.x1, body.y1)
        else:
            self.draw_area, self.card_area = body.rows([0.64, 0.36] if self.view == "ideogram" else [0.7, 0.3], gap=0.3)

    # ----- the karyogram ------------------------------------------------------------------------

    def _build_karyogram(self) -> None:
        k = self.k
        area = self.draw_area
        rows = tuple(tuple(s for s in r if s != "Y" or k.copies["Y"]) for r in (ROWS_TALL if self.is_portrait else ROWS_WIDE))  # no empty Y slot
        num_h = self.markup("22", size=self.small).height
        lab_gap = 0.08
        self.letter_w = self.markup("G", size=self.small * 0.85).width + 0.18
        n_rows = len(rows)

        def extents(row: tuple[str, ...]) -> tuple[float, float]:
            ups = [c.centromere for s in row for c in k.copies[s]] or [kt.CENTROMERE_MB[row[0]]]
            downs = [c.length - c.centromere for s in row for c in k.copies[s]] or [kt.LENGTH_MB[row[0]] - kt.CENTROMERE_MB[row[0]]]
            return max(ups), max(downs)

        ext = [extents(r) for r in rows]
        fixed = n_rows * (num_h + 2 * lab_gap) + (n_rows - 1) * 0.1
        unit = (area.height - fixed) / sum(u + d for u, d in ext)
        for _ in range(4):
            w = WIDTH_SHARE * 249.0 * unit
            widths = [self._row_width(r, w) for r in rows]
            if max(widths) > area.width:
                unit *= area.width / max(widths) * 0.99
        w = WIDTH_SHARE * 249.0 * unit
        while w < WIDE_SHARE * 249.0 * unit and max(self._row_width(r, w * 1.05) for r in rows) <= area.width:
            w *= 1.05                     # rows shorter than the width: slightly broader chromosomes
        self.unit, self.w = unit, w
        self.stroke = max(1.2, min(2.4, w * 14))
        used = sum((u + d) * unit for u, d in ext) + fixed
        y = area.y1 - max(0.0, area.height - used) / 2
        self.slot_groups: dict[str, VGroup] = {}
        self.slot_copies: dict[str, list[Any]] = {}
        self.row_groups: list[VGroup] = []
        self.group_parts: dict[str, list[Mobject]] = {g: [] for g in kt.GROUPS}
        for r, row in enumerate(rows):
            up, down = ext[r]
            y_c = y - up * unit
            width = self._row_width(row, w)
            x = area.center[0] - width / 2
            row_mobs = []
            last_group = None
            for s in row:
                g = kt.GROUP_OF[s]
                if g != last_group:          # the group's letter at the top of the row, before its first pair
                    x += self._group_gap(w)
                    letter = self.markup(g, size=self.small * 0.85, color=self.dim_ink)
                    letter.move_to(np.array([x - letter.width / 2 - 0.06, y - letter.height / 2, 0]))
                    self.group_parts[g].append(letter)
                    row_mobs.append(letter)
                last_group = g
                copies = k.copies[s]
                n = max(len(copies), 1)
                slot_w = self._slot_width(n, w)
                cx = x + slot_w / 2
                drawings = []
                for j, copy in enumerate(copies):
                    xx = cx + (j - (n - 1) / 2) * w * 1.45
                    d = ChromosomeDrawing(self, copy, xx, y_c + copy.centromere * unit, unit, w, self.ink, self.tints, self.stroke)
                    drawings.append(d)
                num = self.markup(s, size=self.small, color=self.ink)
                if num.width > slot_w * 0.92:
                    num.scale(slot_w * 0.92 / num.width)
                num.move_to(np.array([cx, y_c - down * unit - lab_gap - num_h / 2, 0]))
                slot = VGroup(*[d.group for d in drawings], num)
                self.slot_groups[s] = slot
                self.slot_copies[s] = drawings
                self.group_parts[g].append(slot)
                row_mobs.append(slot)
                x += slot_w
            self.row_groups.append(VGroup(*row_mobs))
            y = y_c - down * unit - lab_gap - num_h - lab_gap - 0.1
        self.all_chromosomes = VGroup(*self.row_groups)
        self._karyogram_changes()

    def _slot_width(self, n: int, w: float) -> float:
        return max(2, n) * w * 1.45 + w * 0.6

    def _group_gap(self, w: float) -> float:
        return max(w * 1.2, self.letter_w)

    def _row_width(self, row: tuple[str, ...], w: float) -> float:
        total = sum(self._slot_width(len(self.k.copies[s]), w) for s in row)
        groups = 1 + sum(1 for a, b in zip(row, row[1:]) if kt.GROUP_OF[a] != kt.GROUP_OF[b])
        return total + groups * self._group_gap(w)

    def _karyogram_changes(self) -> None:
        """Per change: a box round the slot(s), a dashed ghost for a lost chromosome, brackets
        beside a derivative's changed stretch."""
        k = self.k
        for i, abn in enumerate(k.abnormalities):
            parts: list[Mobject] = []
            for s in abn.chroms:
                parts.append(self._slot_box(s))
                for d in self.slot_copies.get(s, []):
                    if d.copy.change == i:
                        parts += self._brackets(d)
            if abn.kind == "loss":
                parts.append(self._ghost(abn.chroms[0]))
            self.change_mobs[i] = VGroup(*parts)
        self.sex_marks = VGroup()
        if k.sex not in ("XX", "XY"):
            marks: list[Mobject] = [self._slot_box(s) for s in ("X", "Y") if self.slot_copies.get(s)]
            if k.sex == "X":
                marks.append(self._ghost("X", label="X or Y"))
            self.sex_marks = VGroup(*marks)

    def _slot_box(self, s: str) -> Mobject:
        drawings = self.slot_copies.get(s, [])
        group = VGroup(*[d.group for d in drawings]) if drawings else self.slot_groups[s]
        box = SurroundingRectangle(group, buff=self.w * 0.45, corner_radius=self.w * 0.4).set_stroke(self.hi, width=3)
        return box

    def _ghost(self, s: str, label: str | None = None) -> Mobject:
        """A dashed outline where a lost chromosome would stand."""
        drawings = self.slot_copies[s]
        ref = drawings[0]
        x = ref.x + self.w * 1.45
        normal = kt.normal_copy(s)
        d = ChromosomeDrawing(self, normal, x, ref.top - (ref.copy.centromere - normal.centromere) * self.unit, self.unit, self.w,
                              self.hi, None, self.stroke)
        dashes = VGroup(*[DashedVMobject(o, num_dashes=max(8, int(o.get_height() / (self.w * 0.5)))) for o in d.outline])
        dashes.set_stroke(self.hi, width=self.stroke)
        parts: list[Mobject] = [dashes]
        if label:
            t = self.markup(label, size=self.small * 0.9, color=self.hi)
            t.next_to(dashes, RIGHT, buff=0.08)
            parts.append(t)
        return VGroup(*parts)

    def _brackets(self, d: ChromosomeDrawing) -> list[Mobject]:
        out: list[Mobject] = []
        x = d.x + d.width / 2 + d.width * 0.35
        for a, b in d.copy.marks:
            ya, yb = d.mb_y(a), d.mb_y(b)
            if abs(ya - yb) < 1e-6:          # a breakpoint: a tick
                out.append(Line(np.array([x - d.width * 0.3, ya, 0]), np.array([x + d.width * 0.3, ya, 0])).set_stroke(self.hi, width=3))
                continue
            out.append(VGroup(Line(np.array([x, ya, 0]), np.array([x, yb, 0])),
                              Line(np.array([x, ya, 0]), np.array([x - d.width * 0.25, ya, 0])),
                              Line(np.array([x, yb, 0]), np.array([x - d.width * 0.25, yb, 0]))).set_stroke(self.hi, width=3))
        return out

    # ----- ideograms ----------------------------------------------------------------------------

    def _build_ideograms(self) -> None:
        """The chromosomes involved, large: per slot its copies (a derivative first shown as the
        normal chromosome it is made from)."""
        p = self.params
        k = self.k
        area = self.draw_area
        slots = self._ideogram_slots(p)
        name_h = self.markup("der(22)", size=self.small).height
        robs = [a for a in k.abnormalities if a.kind == "rob"]
        columns: list[tuple[str, Any, str]] = []        # (slot, copy or None for a ghost, role)
        for s in slots:
            for c in k.copies[s]:
                columns.append((s, c, "copy"))
            for a in robs:
                if a.chroms[0] == s:
                    columns.append((a.chroms[1], None, "ghost"))
            if not k.copies[s]:
                columns.append((s, None, "lost"))
        self.columns = columns
        group_of: list[str] = []                         # the slot each column is drawn with
        for s in slots:
            group_of += [s] * (len(k.copies[s]) + sum(1 for a in robs if a.chroms[0] == s) + (0 if k.copies[s] else 1))
        # rows: one per slot in a portrait frame (when there are several), else all side by side
        rows = [[s] for s in slots] if self.is_portrait and len(slots) > 1 else [slots]
        row_cols = [[ci for ci in range(len(columns)) if group_of[ci] in r] for r in rows]

        def extent(cols: list[int]) -> tuple[float, float]:
            ups = [kt.CENTROMERE_MB[columns[ci][0]] for ci in cols] + [columns[ci][1].centromere for ci in cols if columns[ci][1] is not None]
            downs = [kt.LENGTH_MB[columns[ci][0]] - kt.CENTROMERE_MB[columns[ci][0]] for ci in cols]
            downs += [columns[ci][1].length - columns[ci][1].centromere for ci in cols if columns[ci][1] is not None]
            return max(ups), max(downs)

        ext = [extent(cols) for cols in row_cols]
        name_room = name_h * 1.8 + 0.25
        unit = (area.height - 0.3 - len(rows) * name_room) / sum(u + d for u, d in ext)
        self.col_labels = self._column_labels()
        extra = {ci: max(self.markup(text, size=self.small * 0.9).width for _, text, _ in items) + 0.6
                 for ci, items in self.col_labels.items()}
        names: dict[int, Mobject] = {}
        for ci, (s, copy, role) in enumerate(columns):
            label = copy.name if role == "copy" else s
            names[ci] = self.markup(label, size=self.small, color=self.ink if (role == "copy" and copy.normal) else self.hi)

        def advance(ci: int, w: float) -> float:
            return max(w * 2.6, names[ci].width + 0.2) + extra.get(ci, 0.0)

        def row_width(r: int, w: float) -> float:
            return sum(advance(ci, w) for ci in row_cols[r]) + (len(rows[r]) - 1) * w * 1.6 + w * 1.4

        # the width follows the length (chromosome 1 about ten times as long as wide), unless the
        # columns would not fit: then thinner, and shorter only when very thin
        w = min(WIDTH_SHARE * 249.0 * unit, 0.6)
        while w > 0.03 and max(row_width(r, w) for r in range(len(rows))) > area.width:
            w *= 0.95
        if w < 0.35 * WIDTH_SHARE * 249.0 * unit:      # very thin: shorter instead
            unit = w / (0.35 * WIDTH_SHARE * 249.0)
        self.unit, self.w = unit, w
        self.stroke = max(1.5, min(3.0, w * 10))
        total = sum((u + d) * unit + name_room for u, d in ext)
        y = area.y1 - 0.15 - (max(0.0, area.height - 0.3 - total) / 2 if self.is_portrait else 0.0)
        self.slot_groups = {}
        self.slot_copies: dict[str, list[Any]] = {s: [] for s in slots}
        self.before: dict[int, Any] = {}        # column index -> the normal chromosome shown before an edit
        self.after: dict[int, Any] = {}
        self.ghosts: dict[int, Any] = {}
        self.col_x: dict[int, float] = {}
        for r, cols in enumerate(row_cols):
            up, down = ext[r]
            y_c = y - up * unit
            x = area.x0 + max(0.0, (area.width - row_width(r, w)) / 2) + w * 1.4
            last_slot = None
            for ci in cols:
                s, copy, role = columns[ci]
                if last_slot is not None and group_of[ci] != last_slot:
                    x += w * 1.6
                last_slot = group_of[ci]
                adv = advance(ci, w)
                x_c = x + (max(w * 2.6, names[ci].width + 0.2) - w * 2.6) / 2
                self.col_x[ci] = x_c
                if role == "copy":
                    d = ChromosomeDrawing(self, copy, x_c, y_c + copy.centromere * unit, unit, w, self.ink, self.tints, self.stroke)
                    self.after[ci] = d
                    self.slot_copies[s].append(d)
                    if not copy.normal and copy.change is not None and k.abnormalities[copy.change].kind in STRUCTURAL:
                        normal = kt.normal_copy(copy.slot)
                        self.before[ci] = ChromosomeDrawing(self, normal, x_c, y_c + normal.centromere * unit, unit, w, self.ink, None,
                                                            self.stroke)
                else:
                    normal = kt.normal_copy(s)
                    self.ghosts[ci] = ChromosomeDrawing(self, normal, x_c, y_c + normal.centromere * unit, unit, w, self.ink, None, self.stroke)
                x += adv
            bottom = y_c - down * unit
            for ci in cols:
                names[ci].move_to(np.array([self.col_x[ci], bottom - 0.12 - names[ci].height / 2, 0]))
            y = bottom - name_room
        self.col_names = names
        # p / q beside the first column of each slot
        self.arm_labels = VGroup()
        seen: set[str] = set()
        for ci, (s, copy, role) in enumerate(columns):
            if role != "copy" or s in seen:
                continue
            seen.add(s)
            d = self.before.get(ci) or self.after[ci]
            for arm in ("p", "q"):
                t = self.markup(f"<i>{arm}</i>", size=self.small * 0.95, color=self.dim_ink)
                t.move_to(np.array([d.x - w / 2 - 0.12 - t.width / 2, d.arm_middle(arm), 0]))
                self.arm_labels.add(t)
        for s in slots:
            parts = [self.after[ci].group for ci, (ss, c, role) in enumerate(columns) if ss == s and role == "copy" and ci in self.after]
            parts += [names[ci] for ci, (ss, c, role) in enumerate(columns) if ss == s and role == "copy"]
            self.slot_groups[s] = VGroup(*parts)
        self._band_labels()
        self._ideogram_changes()

    def _column_labels(self) -> dict[int, list[tuple[float, str, int | None]]]:
        """Per column, the labels written to its right: (Mb along that copy, markup, change):
        a derivative's own breakpoints, the bands asked for on the first normal copy."""
        out: dict[int, list[tuple[float, str, int | None]]] = {}
        k = self.k
        firsts: dict[str, int] = {}
        for ci, (s, copy, role) in enumerate(self.columns):
            if role == "copy" and copy.normal and s not in firsts:
                firsts[s] = ci
        for ref, text in self.params.labels():
            ci = firsts.get(ref.chrom)
            if ci is not None:
                out.setdefault(ci, []).append((ref.mid, f"{ref.label}" + (f"  <i>{_esc(text)}</i>" if text else ""), None))
        for ci, (s, copy, role) in enumerate(self.columns):
            if role != "copy" or copy.normal or copy.change is None:
                continue
            abn = k.abnormalities[copy.change]
            if abn.kind not in STRUCTURAL:
                continue
            for ref in abn.bands:
                if ref.chrom != copy.slot or ref.text in ("p10", "q10"):
                    continue
                at = _along(copy, ref.chrom, ref.mid)
                if at is not None:
                    out.setdefault(ci, []).append((at, ref.label, copy.change))
        return out

    def _band_labels(self) -> None:
        """Each column's labels beside it with a leader line to the band (stacked when close)."""
        self.band_mobs: dict[str, VGroup] = {}
        self.break_labels: dict[int, list[Mobject]] = {}
        for ci, items in self.col_labels.items():
            d = self.after[ci]
            used: list[float] = []
            for at, text, change in sorted(items):
                y = d.mb_y(at)
                x0 = d.x + d.width / 2 + (d.width * 0.6 if change is not None else 0.0)
                label = self.markup(text, size=self.small * 0.9, color=self.hi if change is not None else self.ink)
                ly = y
                for other in used:
                    if abs(ly - other) < label.height * 1.15:
                        ly = other - label.height * 1.2
                used.append(ly)
                label.move_to(np.array([x0 + 0.34 + label.width / 2, ly, 0]))
                lead = VMobject().set_points_as_corners([np.array([d.x - d.width * 0.5, y, 0]), np.array([x0 + 0.1, y, 0]),
                                                         np.array([x0 + 0.28, ly, 0])])
                lead.set_stroke(self.hi if change is not None else self.dim_ink, width=2)
                group = VGroup(lead, label)
                if change is None:
                    key = text.split(" ")[0]
                    self.band_mobs[key] = group
                else:
                    self.break_labels.setdefault(change, []).append(group)

    def _ideogram_changes(self) -> None:
        k = self.k
        for i, abn in enumerate(k.abnormalities):
            parts: list[Mobject] = []
            for ci, (s, copy, role) in enumerate(self.columns):
                if role == "copy" and copy.change == i:
                    d = self.after[ci]
                    parts += self._brackets(d)
                    if abn.kind == "gain":
                        parts.append(SurroundingRectangle(d.group, buff=self.w * 0.35, corner_radius=self.w * 0.3).set_stroke(self.hi, width=3))
                if role == "lost" and s in abn.chroms:
                    parts.append(self._ideogram_ghost(ci))
            parts += self.break_labels.get(i, [])
            if abn.kind == "loss":
                cols = [ci for ci, (s, c, r) in enumerate(self.columns) if s == abn.chroms[0] and r == "copy"]
                if cols:
                    parts.append(self._ideogram_ghost(cols[-1], beside=True))
            self.change_mobs[i] = VGroup(*parts)
        self.sex_marks = VGroup()
        if k.sex not in ("XX", "XY"):
            self.sex_marks = VGroup(*[SurroundingRectangle(self.slot_groups[s], buff=self.w * 0.3).set_stroke(self.hi, width=3)
                                      for s in ("X", "Y") if s in self.slot_groups and self.slot_copies.get(s)])

    def _ideogram_ghost(self, ci: int, beside: bool = False) -> Mobject:
        s = self.columns[ci][0]
        normal = kt.normal_copy(s)
        x = self.col_x[ci] + (self.w * 2.0 if beside else 0.0)
        top = self.after[ci].top - (self.after[ci].copy.centromere - normal.centromere) * self.unit if ci in self.after else \
            self.ghosts[ci].top if ci in self.ghosts else self.area_top()
        d = ChromosomeDrawing(self, normal, x, top, self.unit, self.w, self.hi, None, self.stroke)
        return VGroup(*[DashedVMobject(o, num_dashes=24) for o in d.outline]).set_stroke(self.hi, width=self.stroke)

    def area_top(self) -> float:
        return self.draw_area.y1 - 0.2

    # ----- the card ---------------------------------------------------------------------------------

    def _build_card(self) -> None:
        self.card = None
        if not self.params.notation:
            return
        k = self.k
        area = self.card_area
        size = self.small
        width = area.width - 0.05
        head = self.markup(f"<b>{k.text}</b>", size=size * 1.7, color=self.ink)
        if head.width > width:
            head.scale(width / head.width)
        sexes = "female" if k.is_female else "male"
        first = f"{k.count} chromosomes · {k.sex} ({sexes})"
        lines: list[Mobject] = [text_block(self, first, width, size, color=self.ink)]
        self.reading_rows: dict[int, Mobject] = {}
        for i, abn in enumerate(k.abnormalities):
            row = text_block(self, f"<b>{_esc(abn.text)}</b>  {_esc(abn.reading)}", width, size, color=self.ink)
            self.reading_rows[i] = row
            lines.append(row)
        if not k.abnormalities and k.sex in ("XX", "XY"):
            lines.append(text_block(self, f"a normal {sexes} karyotype: 22 pairs of autosomes and {k.sex}", width, size, color=self.ink))
        for c in k.conditions:
            lines.append(text_block(self, f"→ {_esc(c)}", width, size, color=self.hi))
        for n in (k.notes if not self.is_portrait else ()):      # a portrait card keeps to the reading
            lines.append(text_block(self, _esc(n), width, size * 0.9, color=self.dim_ink))
        reading = VGroup(*lines).arrange(DOWN, buff=0.14, aligned_edge=LEFT)
        card = VGroup(head, reading).arrange(DOWN, buff=0.25, aligned_edge=LEFT)
        if card.height > area.height:
            card.scale(area.height / card.height)
        y = area.y1 - card.height / 2 if self.is_portrait else area.center[1]
        card.move_to(np.array([area.x0 + card.width / 2, y, 0]))
        self.card_head, self.card_reading, self.card = head, reading, card

    # ----- targets and steps --------------------------------------------------------------------------

    def _register(self) -> None:
        p = self.params
        k = self.k
        title = self.title_mob
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        ideo = self.view == "ideogram"
        everything = self._shown_first()
        self.target("chromosomes", everything, entrance=lambda: self.run_chromosomes())
        if not ideo:
            for g, parts in self.group_parts.items():
                if parts:
                    self.target(f"group:{g}", VGroup(*parts))
        for s, mob in self.slot_groups.items():
            self.target(f"chromosome:{s}", mob)
        for i in range(len(k.abnormalities)):
            mob = self.change_mobs[i] if len(self.change_mobs[i]) else everything
            self.target(f"change:{i + 1}", mob, entrance=lambda i=i: self.run_change(i))
        if k.abnormalities:
            self.target("changes", VGroup(*self.change_mobs.values()), entrance=lambda: self.run_all_changes())
        if self.card is not None:
            self.target("notation", self.card_head, entrance=lambda: [FadeIn(self.card_head)])
            self.target("reading", self.card_reading, entrance=lambda: self.run_reading())
        for key, mob in getattr(self, "band_mobs", {}).items():
            if key in [ref.label for ref, _ in p.labels()]:
                self.target(f"band:{key}", mob)
        held: set[str] = set()
        for use in self.action_uses("reveal"):
            held.update(use.config.targets())
        manual = bool(self.action_uses("rearrange")) or any(n.startswith(("change:", "reading")) for n in held)

        def first() -> list[Animation]:
            anims: list[Animation] = [FadeIn(title)] if title is not None else []
            if "chromosomes" not in held:
                anims += self.run_chromosomes()
            if self.card is not None and "notation" not in held:
                anims.append(FadeIn(self.card_head))
            return anims

        steps: list[Any] = [first]
        if not manual:
            if k.abnormalities or len(self.sex_marks):
                steps.append(lambda: self.run_all_changes())
            if self.card is not None:
                steps.append(lambda: self.run_reading())
        elif self.card is not None and "reading" not in held:     # the reading on the last beat
            steps += [[] for _ in range(max(0, len(self.beats) - 2))] + [lambda: self.run_reading()]
        self.reveal(steps, fraction=0.85, cap=3.2)
        self.finish()

    def _shown_first(self) -> VGroup:
        if self.view == "karyogram":
            return self.all_chromosomes
        parts: list[Mobject] = []
        for ci, (s, copy, role) in enumerate(self.columns):
            if ci in self.before:
                parts.append(self.before[ci].group)
            elif ci in self.ghosts:
                parts.append(self.ghosts[ci].group)
            elif ci in self.after:
                parts.append(self.after[ci].group)
            if role == "copy" and (copy.normal or ci not in self.before):
                parts.append(self.col_names[ci])
        parts.append(self.arm_labels)
        return VGroup(*parts)

    def run_chromosomes(self) -> list[Animation]:
        if getattr(self, "shown", False):
            return []
        self.shown = True
        if self.view == "karyogram":
            return [LaggedStart(*[FadeIn(r, shift=UP * 0.05) for r in self.row_groups], lag_ratio=0.25)]
        names = [m for key, m in self.band_mobs.items() if key in [ref.label for ref, _ in self.params.labels()]]
        return [AnimationGroup(FadeIn(self._shown_first()), *[FadeIn(m) for m in names])]

    def run_reading(self) -> list[Animation]:
        if self.card is None or getattr(self, "read_done", False):
            return []
        self.read_done = True
        anims: list[Animation] = [] if self.card_head in self.mobjects else [FadeIn(self.card_head)]
        anims.append(LaggedStart(*[FadeIn(m, shift=LEFT * 0.08) for m in self.card_reading], lag_ratio=0.3))
        return [Succession(*anims)] if len(anims) > 1 else anims

    def change_seconds(self, idx: list[int]) -> float:
        k = self.k
        total = 0.0
        for i in idx:
            structural = k.abnormalities[i].kind in STRUCTURAL and self.view == "ideogram"
            total += EDIT_SECONDS if structural else MARK_SECONDS
        return max(MARK_SECONDS, total)

    def run_all_changes(self) -> list[Animation]:
        anims: list[Animation] = []
        for i in range(len(self.k.abnormalities)):
            anims += self.run_change(i)
        if len(self.sex_marks) and not getattr(self, "sex_done", False):
            self.sex_done = True
            anims.append(LaggedStart(*[Create(m) if not isinstance(m, VGroup) else FadeIn(m) for m in self.sex_marks], lag_ratio=0.2))
        return [Succession(*anims)] if len(anims) > 1 else anims

    def run_change(self, i: int) -> list[Animation]:
        """Highlight change ``i`` (karyogram), or play it as an edit (ideogram, structural)."""
        if i in self.marked:
            return []
        self.marked.add(i)
        pre = self.run_chromosomes()
        abn = self.k.abnormalities[i]
        marks = self.change_mobs[i]
        if self.view == "ideogram" and abn.kind in STRUCTURAL:
            return [Succession(*pre, *self._edit(i), *([FadeIn(marks)] if len(marks) else []))]
        show = [Create(m) if isinstance(m, (Rectangle, Line)) else FadeIn(m) for m in marks]
        if self.card is not None and i in self.reading_rows and getattr(self, "read_done", False):
            show.append(Indicate(self.reading_rows[i], color=self.hi, scale_factor=1.05))
        return [Succession(*pre, AnimationGroup(*show))] if pre else [AnimationGroup(*show)]

    def _edit(self, i: int) -> list[Animation]:
        """The normal chromosomes become the derivatives of change ``i``: each derivative's
        segments move from where they were (inverted ones turning round), what no derivative
        keeps fades away, the outlines are redrawn."""
        cols = [ci for ci, (s, c, r) in enumerate(self.columns) if r == "copy" and c.change == i and ci in self.before]
        abn = self.k.abnormalities[i]
        sources: dict[str, int] = {}
        for ci in cols:
            sources.setdefault(self.columns[ci][1].slot, ci)
        ghost_of = {self.columns[ci][0]: ci for ci in self.ghosts}
        moves: list[Animation] = []
        fades: list[Animation] = []
        used: dict[int, list[tuple[float, float]]] = {}
        unit, w = self.unit, self.w
        for ci in cols:
            after = self.after[ci]
            for seg, piece in zip(after.copy.segments, after.pieces):
                src = sources.get(seg.chrom)
                if src is not None:
                    d = self.before[src]
                elif seg.chrom in ghost_of:
                    src = ghost_of[seg.chrom]
                    d = self.ghosts[src]
                else:
                    continue
                lo, hi = sorted((seg.a, seg.b))
                used.setdefault(src, []).append((lo, hi))
                before_piece = segment_piece(self, seg.chrom, lo, hi, d.x, d.top, unit, w, self.ink, self.stroke)
                self.add(before_piece)
                arc = PI if seg.a > seg.b else (0.0 if src == ci else -0.6)
                moves.append(ReplacementTransform(before_piece, piece, path_arc=arc))
        olds: list[Any] = [self.before[ci] for ci in cols] + [self.ghosts[ci] for ci in self.ghosts if ci in used]
        for ci, d in list(self.before.items()) + list(self.ghosts.items()):
            if d not in olds:
                continue
            self.remove(d.pieces)
            fades.append(FadeOut(d.outline))
            chrom = d.copy.slot
            ranges = sorted(used.get(ci, []))
            at = 0.0
            for lo, hi in ranges + [(d.copy.length, d.copy.length)]:
                if lo - at > 1e-6:
                    rest = segment_piece(self, chrom, at, lo, d.x, d.top, unit, w, self.ink, self.stroke)
                    self.add(rest)
                    fades.append(FadeOut(rest, shift=RIGHT * w * 1.2))
                at = max(at, hi)
        names = [self.col_names[ci] for ci in cols]
        outlines = [self.after[ci].outline for ci in cols]
        flash = []
        for ref in abn.bands:
            for ci in cols:
                if self.columns[ci][1].slot == ref.chrom and ci in self.before:
                    y = self.before[ci].mb_y(ref.mid)
                    x = self.before[ci].x
                    flash.append(Line(np.array([x - w, y, 0]), np.array([x + w, y, 0])).set_stroke(self.hi, width=4))
        steps: list[Animation] = []
        if flash:
            steps.append(Succession(AnimationGroup(*[Create(f) for f in flash]), AnimationGroup(*[FadeOut(f) for f in flash])))
        steps.append(AnimationGroup(*fades, *moves))
        steps.append(AnimationGroup(*[FadeIn(o) for o in outlines], *[FadeIn(n) for n in names]))
        return steps


def _along(copy: Any, chrom: str, mb: float) -> float | None:
    """Where position ``mb`` of chromosome ``chrom`` is along ``copy`` (Mb from its top), or
    ``None`` when the copy does not carry it."""
    at = 0.0
    for seg in copy.segments:
        lo, hi = sorted((seg.a, seg.b))
        if seg.chrom == chrom and lo - 1e-6 <= mb <= hi + 1e-6:
            return at + (mb - seg.a if seg.a <= seg.b else seg.a - mb)
        at += seg.length
    return None


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
