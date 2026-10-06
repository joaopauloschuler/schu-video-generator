"""``table``: a header and rows of cells, fitted to the frame and revealed row by row."""

import logging
from collections.abc import Callable
from typing import Any, Literal, NamedTuple

import numpy as np

from vidgen.api import *

log = logging.getLogger("vidgen.scenes")

Align = Literal["auto", "left", "center", "right"]
Cell = str | int | float


class _Fit(NamedTuple):
    """A layout of the table at one font size (see ``Table._fit``)."""

    size: float
    widths: list[float]
    fits: bool


def is_number(value: Any) -> bool:
    """Whether a cell holds a number (``True``/``False`` do not count)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@scene("table")
class Table(NarratedScene):
    """``reveal: per_beat`` (default): the header (with title and caption) and row 1 appear at
    beat 1, row *i* at beat *i*; with more rows than beats they are spread evenly, extra beats
    hold. ``reveal: all``: the whole table in beat 1.

    The table is fitted to the space under the title: the largest text size up to ``size``
    at which it fits, wrapping text columns (numbers never wrap) before going below the
    readable minimum; a table that does not fit even then is scaled down (with a warning
    suggesting to split it).

    Action targets: ``title``, ``header``, ``row<N>``, ``row:<first cell>``, ``col<N>``,
    ``col:<header>``, ``cell<R>.<C>`` (1-based; rows count below the header) and ``caption``.
    """

    outro = 0.5
    target_patterns = ("title", "header", "row<N>", "row:<first cell>", "col<N>", "col:<header>", "cell<R>.<C>", "caption")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """The targets in reading order: title, header, rows, columns, cells, caption."""
        names = ["title"] if params.title else []
        names += ["header"] if params.header else []
        texts = params.texts()
        for r, row in enumerate(texts, start=1):
            names += [f"row{r}", f"row:{row[0]}"]
        for c in range(1, params.column_count() + 1):
            names += [f"col{c}"] + ([f"col:{params.header[c - 1]}"] if params.header else [])
        names += [f"cell{r}.{c}" for r in range(1, len(texts) + 1) for c in range(1, params.column_count() + 1)]
        return names + (["caption"] if params.caption else [])

    class Params(SceneParams):
        rows: list[list[Cell]] = Field(min_length=1, max_length=30)
        """The body rows (up to 30), each a list of cells: text or numbers."""
        header: list[str] = Field(default_factory=list)
        """Column headings (optional); sets the number of columns."""
        title: str = ""
        """Title above the table."""
        caption: str = ""
        """Note under the table (e.g. the source)."""
        align: Align | list[Align] = "auto"
        """Alignment of every column or one per column: auto (numbers right, text left), left, center, right."""
        number_format: str | list[str | None] | None = None
        """Python format for numbers ('{:,.1f}', '{:.0%}', '${:,.0f}'), one for all or one per column; default: the decimals each column needs, with thousands separators."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: header and row 1 in beat 1, then one row per beat; all: everything in beat 1."""
        zebra: bool = True
        """Stripe every other row with stripe_color."""
        color: ThemeColor = "text"
        """Cell text colour."""
        header_color: ThemeColor = "primary"
        """Header text and rule colour."""
        stripe_color: ThemeColor = "surface"
        """Colour of the zebra stripes."""
        rule_color: ThemeColor = "dim"
        """Colour of the thin rule under the last row."""
        title_color: ThemeColor = "text"
        """Title colour."""
        caption_color: ThemeColor = "dim"
        """Caption colour."""
        size: ThemeSize = "body"
        """Cell text size (text columns wrap and the size is reduced, not below the readable minimum, to fit)."""
        title_size: ThemeSize = "heading"
        """Title size."""
        caption_size: ThemeSize = "caption"
        """Caption size."""

        @field_validator("rows", mode="before")
        @classmethod
        def _cells(cls, value: Any) -> Any:
            for i, row in enumerate(value if isinstance(value, list) else []):
                for j, cell in enumerate(row if isinstance(row, list) else []):
                    if cell is None or isinstance(cell, bool):
                        raise ValueError(f"rows[{i}][{j}]: {cell!r} is not text or a number (quote it, or use \"\" for an empty cell)")
            return value

        @field_validator("number_format")
        @classmethod
        def _formats(cls, value: Any) -> Any:
            for fmt in value if isinstance(value, list) else [value]:
                if fmt is not None:
                    check_format(fmt)
            return value

        @model_validator(mode="after")
        def _shape(self) -> SceneParams:
            n = self.column_count()
            source = f"the header has {n}" if self.header else f"row 1 has {n}"
            if n < 1:
                raise ValueError("a table needs at least one column")
            if n > 8:
                raise ValueError(f"at most 8 columns ({source}); split the table")
            for i, row in enumerate(self.rows):
                if len(row) != n:
                    raise ValueError(f"rows[{i}] has {len(row)} cells, expected {n} ({source})")
            for name in ("align", "number_format"):
                value = getattr(self, name)
                if isinstance(value, list) and len(value) != n:
                    raise ValueError(f"{name} has {len(value)} entries, expected one per column ({n})")
            return self

        def column_count(self) -> int:
            """Number of columns (from the header, else the first row)."""
            return len(self.header) if self.header else len(self.rows[0])

        def numeric(self, column: int) -> bool:
            """Whether every non-empty cell of a column is a number."""
            cells = [row[column] for row in self.rows if row[column] != ""]
            return bool(cells) and all(is_number(c) for c in cells)

        def alignment(self, column: int) -> str:
            """``left``, ``center`` or ``right`` for a column (``auto``: numbers right)."""
            a = self.align[column] if isinstance(self.align, list) else self.align
            return ("right" if self.numeric(column) else "left") if a == "auto" else a

        def texts(self) -> list[list[str]]:
            """Every body cell as shown: numbers formatted per column."""
            n = self.column_count()
            formats: list[str | None] = self.number_format if isinstance(self.number_format, list) else [self.number_format] * n
            for c in range(n):
                if formats[c] is None:
                    formats[c] = auto_format([row[c] for row in self.rows if is_number(row[c])] or [0])
            return [[format_value(cell, formats[c]) if is_number(cell) else str(cell) for c, cell in enumerate(row)] for row in self.rows]

    #: Cell padding as multiples of the text's cap height (horizontal, vertical).
    pad_x = 0.75
    pad_y = 0.62
    #: Body cells up to this many characters are never wrapped (longer ones wrap at spaces).
    unbroken = 16
    #: In a vertical frame rows get this much more vertical padding (the frame has height to spare).
    portrait_padding = 1.4
    #: Largest share of the safe width a table spreads to when its natural width is smaller.
    spread = 0.8
    #: Font sizes tried, as shares of ``size``, before falling back to the readable minimum.
    shrink_steps = (1.0, 0.92, 0.85, 0.78, 0.72, 0.66, 0.6)

    def construct(self) -> None:
        p = self.params
        area = self.safe_area
        title = None
        if p.title:
            header = self.region("header")
            title = fit_text(p.title, header.width, header.height, size=p.title_size, color=p.title_color, weight=BOLD, role="heading")
            place(title, header, fit="none", align="center")
            area = area.below(title, gap=0.45)
        caption = None
        if p.caption:
            caption = fit_text(p.caption, area.width, area.height * 0.15, size=p.caption_size, color=p.caption_color)
            place(caption, area, fit="none", align="bottom")
            area = area.above(caption, gap=0.3)
        table = self._build(area)
        self._steps(table, title, caption)

    # ----- fitting ---------------------------------------------------------------------------

    def _widths(self, size: float, width: float) -> _Fit:
        """Column widths at font ``size`` within ``width``: natural (one line per cell) when
        that fits; else columns share the width (water-filling: a column that needs less than
        its share keeps its natural width) and wrap, never narrower than their longest word or
        number (headings of number columns wrap too)."""
        p = self.params
        cap = self.text("H", size=size).height
        pad = 2 * self.pad_x * cap
        body = p.texts()
        n = p.column_count()

        def cells(c: int) -> list[tuple[str, bool]]:  # (text, bold) of every cell of a column
            return ([(p.header[c], True)] if p.header else []) + [(row[c], False) for row in body]

        natural = [max(self._line_width(t, size, bold) for t, bold in cells(c)) + pad for c in range(n)]
        if sum(natural) <= width:
            return _Fit(size, natural, True)
        floor = []
        for c in range(n):
            # headings wrap at any space; short body cells ('1920 x 1080') and numbers stay whole
            pieces = [(w, bold) for t, bold in cells(c) for w in (t.split() if bold or len(t) > self.unbroken else [t])]
            floor.append(max(self._line_width(w, size, bold) for w, bold in pieces) + pad)
        widths = list(natural)
        pool, left = set(range(n)), width
        while pool:  # water-filling: a column needing less than a fair share keeps its natural
            share = left / len(pool)  # width, one that cannot go below its floor gets the floor
            settled = {c: natural[c] for c in pool if natural[c] <= share} or {c: floor[c] for c in pool if floor[c] >= share}
            if not settled:
                for c in pool:
                    widths[c] = share
                break
            for c, w in settled.items():
                widths[c] = w
            pool -= set(settled)
            left -= sum(settled.values())
        return _Fit(size, widths, sum(widths) <= width * 1.001)

    def _line_width(self, text: str, size: float, bold: bool = False) -> float:
        """Width of ``text`` on one line at ``size``."""
        return self.text(text, size=size, weight=BOLD if bold else NORMAL).width if text.strip() else 0.0

    def _fit(self, area: Region) -> tuple[_Fit, VGroup, dict[str, Any]]:
        """The largest size (from :attr:`shrink_steps`, then the readable minimum) at which the
        table fits ``area``; below that it is built at the readable size and scaled to fit."""
        wanted = float(self.theme.size(self.params.size))
        floor = min(wanted, readable_size())
        sizes = sorted({max(floor, wanted * f) for f in self.shrink_steps} | {floor}, reverse=True)
        for size in sizes:
            fit = self._widths(size, area.width)
            if fit.fits:
                group, parts = self._layout(fit)
                if group.height <= area.height:
                    return fit, group, parts
        fit = self._widths(floor, area.width)
        group, parts = self._layout(fit)
        before = group.width
        shrink_to_fit(group, area.width, area.height)
        shown = floor * group.width / before if before else floor
        p = self.params
        log.warning(
            "scene '%s': the table (%d rows x %d columns) does not fit this frame at the readable size; text scaled to %.0f pt "
            "(lint min_font): split it into smaller tables or drop columns",
            self.spec.id, len(p.rows), p.column_count(), shown,
        )
        return fit, group, parts

    # ----- building --------------------------------------------------------------------------

    def _build(self, area: Region) -> dict[str, Any]:
        fit, group, parts = self._fit(area)
        natural = group.width
        target = min(area.width * self.spread, area.width)
        if natural < target and not self.is_portrait:  # a narrow table: spread its columns a little
            fit = fit._replace(widths=[w * min(target / natural, 1.25) for w in fit.widths])
            group, parts = self._layout(fit)
            shrink_to_fit(group, area.width, area.height)
        group.move_to(area.center)
        return parts

    def _layout(self, fit: _Fit) -> tuple[VGroup, dict[str, Any]]:
        """Cells, stripes and rules at ``fit``; returns everything in one group (to position it)
        and the parts by role: ``header`` (cells), ``rows`` (cells per row), ``stripes`` (per
        row or ``None``), ``row_boxes``, ``col_boxes``, ``cell_boxes``, ``rules``."""
        p = self.params
        size, widths = fit.size, fit.widths
        cap = self.text("H", size=size).height
        probe = fit_text("x\nx", 100, size=size)
        pitch = probe[0].get_y() - probe[1].get_y()
        descent = cap * 0.32
        pad_x, pad_y = self.pad_x * cap, self.pad_y * cap * (self.portrait_padding if self.is_portrait else 1.0)
        n = len(widths)
        lefts = np.cumsum([0.0, *widths[:-1]])
        total_w = float(sum(widths))

        def row_cells(texts: list[str], top: float, header: bool) -> tuple[list[Mobject | None], float]:
            cells: list[Mobject | None] = []
            lines = 1
            for c, text in enumerate(texts):
                if not text.strip():
                    cells.append(None)
                    continue
                align = p.alignment(c)
                block = fit_text(  # wrapping may use a little of the padding: measured widths differ slightly
                    text, max(widths[c] - 1.8 * pad_x, cap), size=size, align=align,
                    color=p.header_color if header else p.color, weight=BOLD if header else NORMAL,
                )
                baseline = top - pad_y - cap
                block.shift(UP * (baseline - _baseline(block[0])))
                x0, x1 = lefts[c] + pad_x, lefts[c] + widths[c] - pad_x
                if align == "left":
                    block.shift(RIGHT * (x0 - block.get_left()[0]))
                elif align == "right":
                    block.shift(RIGHT * (x1 - block.get_right()[0]))
                else:
                    block.set_x((x0 + x1) / 2)
                lines = max(lines, len(block))
                cells.append(block)
            return cells, top - (2 * pad_y + cap + (lines - 1) * pitch + descent)

        everything = VGroup()
        top = 0.0
        header: list[Mobject | None] = []
        rules: list[Mobject] = []
        if p.header:
            header, bottom = row_cells(p.header, top, header=True)
            rule = Line(np.array([0.0, bottom, 0.0]), np.array([total_w, bottom, 0.0]), stroke_width=2.5)
            rule.set_stroke(self.theme.color(p.header_color), opacity=0.8)
            rules.append(rule)
            everything.add(*[c for c in header if c is not None], rule)
            top = bottom
        rows: list[list[Mobject | None]] = []
        stripes: list[Mobject | None] = []
        row_boxes: list[Mobject] = []
        for r, texts in enumerate(p.texts()):
            cells, bottom = row_cells(texts, top, header=False)
            box = Rectangle(width=total_w, height=top - bottom).move_to(np.array([total_w / 2, (top + bottom) / 2, 0.0]))
            stripe = None
            if p.zebra and r % 2 == 1:
                stripe = box.copy().set_stroke(width=0).set_fill(self.theme.color(p.stripe_color), opacity=1).set_z_index(-1)
                everything.add(stripe)
            rows.append(cells)
            stripes.append(stripe)
            row_boxes.append(box)
            everything.add(*[c for c in cells if c is not None])
            top = bottom
        end = Line(np.array([0.0, top, 0.0]), np.array([total_w, top, 0.0]), stroke_width=1.5).set_stroke(self.theme.color(p.rule_color), opacity=0.6)
        rules.append(end)
        everything.add(end)
        col_boxes = [Rectangle(width=widths[c], height=-top).move_to(np.array([lefts[c] + widths[c] / 2, top / 2, 0.0])) for c in range(n)]
        cell_boxes = [
            [Rectangle(width=widths[c], height=box.height).move_to(np.array([lefts[c] + widths[c] / 2, box.get_y(), 0.0])) for c in range(n)]
            for box in row_boxes
        ]
        boxes = VGroup(*row_boxes, *col_boxes, *[b for row in cell_boxes for b in row])
        for b in boxes:
            b.set_stroke(opacity=0).set_fill(opacity=0)
        everything.add(boxes)  # moved with the table, never drawn
        parts = {"header": header, "rows": rows, "stripes": stripes, "row_boxes": row_boxes, "col_boxes": col_boxes, "cell_boxes": cell_boxes, "rules": rules}
        return everything, parts

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, table: dict[str, Any], title: Mobject | None, caption: Mobject | None) -> None:
        p = self.params
        texts = p.texts()
        n = p.column_count()
        rows, stripes = table["rows"], table["stripes"]
        header_rule = table["rules"][0] if p.header else None
        end_rule = table["rules"][-1]

        def inset(box: Mobject) -> Mobject:  # a highlight box (0.12 outside the outline) lands on the cell edges
            return Rectangle(width=max(box.width - 0.24, 0.05), height=max(box.height - 0.24, 0.05)).move_to(box)

        def cells_in(cells: list[Mobject | None], row_index: int | None = None) -> list[Animation]:
            anims: list[Animation] = []
            if row_index is not None and stripes[row_index] is not None and not self.on_screen_parts(stripes[row_index]):
                anims.append(FadeIn(stripes[row_index]))
            anims += [FadeIn(c, shift=UP * 0.08) for c in cells if c is not None and not self.on_screen_parts(c)]
            return anims

        def closing() -> list[Animation]:  # the rule under the last row comes with it
            return [] if self.on_screen_parts(end_rule) else [Create(end_rule)]

        def row_in(r: int) -> list[Animation]:
            return cells_in(rows[r], r) + (closing() if r == len(rows) - 1 else [])

        def group(cells: list[Mobject | None]) -> VGroup:
            return VGroup(*[c for c in cells if c is not None])

        tops: list[Target] = []
        if title is not None:
            tops.append(self.target("title", title, entrance=lambda: [FadeIn(title, shift=DOWN * 0.15)]))
        if p.header:
            head = table["header"]

            def header_in() -> list[Animation]:
                anims = cells_in(head)
                if header_rule is not None and not self.on_screen_parts(header_rule):
                    anims.append(Create(header_rule))
                return anims

            tops.append(self.target("header", group(head), entrance=header_in))
        if caption is not None:
            tops.append(self.target("caption", caption, entrance=lambda: [FadeIn(caption)]))
        for r, cells in enumerate(rows):
            names = [f"row{r + 1}", f"row:{texts[r][0]}"]
            self.target(names, group(cells), outline=inset(table["row_boxes"][r]), entrance=lambda r=r: row_in(r))
        for c in range(n):
            column = ([table["header"][c]] if p.header else []) + [cells[c] for cells in rows]
            names = [f"col{c + 1}"] + ([f"col:{p.header[c]}"] if p.header else [])

            def column_in(c: int = c) -> list[Animation]:
                return [a for r, cells in enumerate(rows) for a in cells_in([cells[c]], r)] + (cells_in([table["header"][c]]) if p.header else [])

            self.target(names, group(column), outline=inset(table["col_boxes"][c]), entrance=column_in)
        for r, cells in enumerate(rows):
            for c in range(n):
                cell = cells[c] if cells[c] is not None else VGroup().move_to(table["cell_boxes"][r][c])
                self.target(f"cell{r + 1}.{c + 1}", cell, outline=inset(table["cell_boxes"][r][c]), entrance=lambda r=r, c=c: cells_in([rows[r][c]], r))

        def frame() -> list[Animation]:
            return [a for t in tops for a in self.entrance(t)]

        def row_step(r: int) -> Callable[[], list[Animation]]:
            def build() -> list[Animation]:
                anims = row_in(r)
                lead = frame() if r == 0 else []
                return lead + ([LaggedStart(*anims, lag_ratio=0.08)] if anims else [])

            return build

        if p.reveal == "all":

            def everything() -> list[Animation]:
                built = [cells_in(cells, r) for r, cells in enumerate(rows)]
                body = [AnimationGroup(*anims) for anims in built if anims]
                return frame() + ([LaggedStart(*body, lag_ratio=0.12)] if body else []) + closing()

            steps: list[Callable[[], list[Animation]]] = [everything]
        else:
            steps = [row_step(r) for r in range(len(rows))]
        self.reveal(steps, fraction=0.7, cap=1.0)
        self.finish()


def _baseline(line: Mobject) -> float:
    """Approximate baseline of a line of text: the median bottom of its glyphs."""
    glyphs = [g for g in line.submobjects if g.has_points()] or [line]
    return float(np.median([g.get_bottom()[1] for g in glyphs]))
