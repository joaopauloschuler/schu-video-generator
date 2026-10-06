"""``heatmap``: a matrix of values as coloured cells, with a colour-scale legend."""

import logging
import re
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .actions import dim_to
from .pie import window

log = logging.getLogger("vidgen.scenes")

#: Most rows / columns a heatmap draws.
MAX_CELLS = 40
#: Cells smaller than this (Manim units) trigger the "too big for the frame" warning.
MIN_CELL = 0.3
#: Largest cell side (units): a 2 x 2 matrix does not fill the frame with four slabs.
MAX_CELL = 2.2
_REF = re.compile(r"^(?:cell(\d+)\.(\d+)|row(\d+)|col(\d+)|row:(.+)|col:(.+))$")


@scene("heatmap")
class Heatmap(NarratedScene):
    """``reveal: all`` (default) brings the labels and the legend, and the cells in a wave from
    the top left corner, in beat 1; ``rows`` reveals one row per beat (the column labels and
    the legend with the first). With ``highlight`` set, a last step outlines the chosen cells,
    rows or columns and dims the rest.

    Colours come from a ``sequential`` scale (a tint of ``color`` up to ``color``) or a
    ``diverging`` one (``low_color`` below ``center``, ``high_color`` above), interpolated
    perceptually (OKLab) from theme colours; ``auto`` picks diverging when the values have both
    signs. Each cell's value is written in the theme's text or background colour, whichever
    reads better on that cell, and hidden when the cells are too small for readable text.

    Action targets: ``title``, ``legend``, ``row<N>`` / ``row:<label>``, ``col<N>`` /
    ``col:<label>`` (a row / column with its label) and ``cell<R>.<C>`` (1-based).
    """

    outro = 0.5
    target_patterns = ("title", "legend", "row<N>", "row:<label>", "col<N>", "col:<label>", "cell<R>.<C>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title``, ``legend`` (those present), ``row<N>`` (and ``row:<label>``) per row,
        ``col<N>`` (and ``col:<label>``) per column, then ``cell<R>.<C>`` row by row."""
        names = (["title"] if params.title else []) + (["legend"] if params.legend else [])
        n_rows, n_cols = params.shape()
        for r in range(n_rows):
            names += [f"row{r + 1}"] + ([f"row:{params.rows[r]}"] if params.rows else [])
        for c in range(n_cols):
            names += [f"col{c + 1}"] + ([f"col:{params.columns[c]}"] if params.columns else [])
        return names + [f"cell{r + 1}.{c + 1}" for r in range(n_rows) for c in range(n_cols)]

    class Params(SceneParams):
        values: list[list[float | None]] = Field(min_length=1)
        """The matrix, row by row (null: no data, drawn as an empty cell)."""
        rows: list[str] = Field(default_factory=list)
        """Row labels (left of the rows; unique)."""
        columns: list[str] = Field(default_factory=list)
        """Column labels (above the columns; unique)."""
        title: str = ""
        """Chart title (in the header band at the top)."""
        scale: Literal["auto", "sequential", "diverging"] = "auto"
        """Colour scale: sequential (low to high), diverging (two colours either side of center); auto: diverging when the values have both signs around center."""
        color: ThemeColor = "primary"
        """Sequential scale: the colour of the highest values (low values are a faint tint of it)."""
        low_color: ThemeColor = "primary"
        """Diverging scale: the colour below center."""
        high_color: ThemeColor = "accent"
        """Diverging scale: the colour above center."""
        center: float = 0.0
        """Diverging scale: the neutral middle value."""
        scale_min: float | None = None
        """Value at the low end of the scale; default: the data's minimum (diverging: symmetric around center)."""
        scale_max: float | None = None
        """Value at the high end of the scale; default: the data's maximum."""
        show_values: bool | None = None
        """Write each value in its cell; default: when the cells are large enough for readable text."""
        value_format: str | None = None
        """Python format for cell values and legend ticks, e.g. '{:.2f}'; default: the decimals the values need."""
        unit: str = ""
        """Appended to cell values and legend ticks."""
        legend: bool = True
        """Show the colour scale as a bar with ticks (right of the matrix; below it in 9:16)."""
        legend_label: str = ""
        """Title over the legend bar (what the colour means)."""
        reveal: Literal["all", "rows"] = "all"
        """all: every cell in beat 1 (a wave from the top left); rows: row i at beat i."""
        highlight: one_or_many(str) = Field(default_factory=list)
        """Cells, rows or columns outlined in a last step (the rest dims): cell<R>.<C>, row<N>, row:<label>, col<N>, col:<label>."""
        highlight_color: ThemeColor = "highlight"
        """Outline colour of highlighted cells."""
        label_size: ThemeSize = "caption"
        """Size of row / column labels and legend ticks (never below the readable minimum)."""
        value_size: ThemeSize = "caption"
        """Largest size of the values in the cells (they shrink to fit, down to the readable minimum, else they are hidden)."""
        caption: str = ""
        """Note under the chart (e.g. the data source)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption color."""
        title_size: ThemeSize = "heading"
        """Title size (1.3x in a portrait frame)."""
        title_color: ThemeColor = "text"
        """Title color."""

        @field_validator("value_format")
        @classmethod
        def _format(cls, v: str | None) -> str | None:
            return None if v is None else check_format(v)

        @model_validator(mode="after")
        def _consistent(self) -> SceneParams:
            widths = {len(r) for r in self.values}
            if min(widths) == 0:
                raise ValueError("every row needs at least one value")
            if len(widths) > 1:
                raise ValueError(f"every row needs the same number of values; rows have {', '.join(str(len(r)) for r in self.values)}")
            n_rows, n_cols = self.shape()
            if n_rows > MAX_CELLS or n_cols > MAX_CELLS:
                raise ValueError(f"at most {MAX_CELLS} rows and {MAX_CELLS} columns, got {n_rows} x {n_cols}; split the matrix")
            for name, labels, n in (("rows", self.rows, n_rows), ("columns", self.columns, n_cols)):
                if labels and len(labels) != n:
                    raise ValueError(f"{name} has {len(labels)} labels but the matrix has {n} {name}")
                if len(set(labels)) != len(labels):
                    raise ValueError(f"{name} labels must be unique")
            known = self.known()
            if not known:
                raise ValueError("the matrix has no values (only nulls)")
            if self.scale_min is not None and self.scale_max is not None and self.scale_max <= self.scale_min:
                raise ValueError("scale_max must be greater than scale_min")
            if self.kind() == "diverging":
                lo = self.scale_min if self.scale_min is not None else -np.inf
                hi = self.scale_max if self.scale_max is not None else np.inf
                if not lo < self.center < hi:
                    raise ValueError(f"center {self.center:g} must lie between scale_min and scale_max")
            for ref in self.highlight:
                self.cells_of(ref)
            return self

        def shape(self) -> tuple[int, int]:
            """``(rows, columns)``."""
            return len(self.values), len(self.values[0]) if self.values else 0

        def known(self) -> list[float]:
            """Every value that is not null."""
            return [float(v) for row in self.values for v in row if v is not None]

        def kind(self) -> str:
            """``sequential`` or ``diverging`` (``auto`` resolved)."""
            if self.scale != "auto":
                return self.scale
            known = self.known()
            return "diverging" if known and min(known) < self.center < max(known) else "sequential"

        def cells_of(self, ref: str) -> list[tuple[int, int]]:
            """The 0-based ``(row, col)`` cells a highlight ``ref`` names."""
            n_rows, n_cols = self.shape()
            m = _REF.match(ref)
            if m is None:
                raise ValueError(f"highlight {ref!r}: use cell<R>.<C>, row<N>, row:<label>, col<N> or col:<label>")
            cell_r, cell_c, row, col, row_label, col_label = m.groups()
            if cell_r is not None:
                r, c = int(cell_r) - 1, int(cell_c) - 1
                if not (0 <= r < n_rows and 0 <= c < n_cols):
                    raise ValueError(f"highlight {ref!r}: the matrix has {n_rows} rows and {n_cols} columns")
                return [(r, c)]
            if row is not None or row_label is not None:
                r = int(row) - 1 if row is not None else (self.rows.index(row_label) if row_label in self.rows else -1)
                if not 0 <= r < n_rows:
                    raise ValueError(f"highlight {ref!r}: no such row (rows: {', '.join(self.rows) or f'1..{n_rows}'})")
                return [(r, c) for c in range(n_cols)]
            c = int(col) - 1 if col is not None else (self.columns.index(col_label) if col_label in self.columns else -1)
            if not 0 <= c < n_cols:
                raise ValueError(f"highlight {ref!r}: no such column (columns: {', '.join(self.columns) or f'1..{n_cols}'})")
            return [(r, c) for r in range(n_rows)]

        def number(self, value: float) -> str:
            """A value as written in a cell."""
            return format_value(value, self.value_format or auto_format(self.known()), self.unit)

    #: Text shrunk to fit stops this much above the readable minimum (lint measures lowercase-only
    #: labels a little smaller than the capital H the minimum is based on).
    floor_margin = 1.05
    #: Opacity of the cells outside the highlight.
    dimmed_opacity = 0.3

    def construct(self) -> None:
        p = self.params
        n_rows, n_cols = p.shape()
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color)
            body = body.below(title, gap=0.45)
        cap = None
        if p.caption:
            cap = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            body = body.above(cap, gap=0.3)
        known = p.known()
        scale = color_scale(known, kind=p.kind(), color=p.color, low_color=p.low_color, high_color=p.high_color, center=p.center, lo=p.scale_min, hi=p.scale_max)
        self._scale = scale
        size = chart_label_size(p.label_size)
        floor = readable_size() * self.floor_margin

        # legend size first (it takes a side of the body)
        def legend(length: float) -> VGroup:
            return color_bar(scale, length, vertical=not self.is_portrait, size=size, title=p.legend_label, fmt=p.value_format, unit=p.unit)

        bar = None
        if p.legend:
            bar = legend(min(body.height * 0.7, 4.5) if not self.is_portrait else min(body.width * 0.75, 5.0))
        grid_area = body
        if bar is not None:
            if self.is_portrait:
                grid_area = Region(body.x0, body.y0 + bar.height + 0.45, body.x1, body.y1)
            else:
                grid_area = Region(body.x0, body.y0, body.x1 - bar.width - 0.5, body.y1)

        row_labels = [fit_text(t, grid_area.width * (0.3 if self.is_portrait else 0.25), size=size, min_size=floor, align="right") for t in p.rows]
        row_w = max((m.width for m in row_labels), default=0.0)
        left = grid_area.x0 + (row_w + 0.2 if row_labels else 0.0)
        cell_w = min((grid_area.x1 - left) / n_cols, MAX_CELL)
        col_labels = self._column_labels(cell_w, size, floor)
        col_h = max((m.height for m in col_labels), default=0.0)
        top = grid_area.y1 - (col_h + 0.15 if col_labels else 0.0)
        cell_h = min((top - grid_area.y0) / n_rows, MAX_CELL)
        cell_h = min(cell_h, cell_w)            # no cells taller than wide
        cell_w = min(cell_w, cell_h * 2.5)      # nor very wide slabs
        if col_labels and cell_w < max(m.width for m in col_labels) + 0.05:   # narrower than planned: refit
            col_labels = self._column_labels(cell_w, size, floor)
            col_h = max(m.height for m in col_labels)
        if min(cell_w, cell_h) < MIN_CELL:
            log.warning("scene '%s': the heatmap's %d x %d cells do not fit this frame at a readable size (cells %.2f x %.2f units); split the matrix or show fewer rows / columns", self.spec.id, n_rows, n_cols, cell_w, cell_h)

        # centre the block: row labels, grid (with column labels), legend (as long as the grid)
        grid_w, grid_h = cell_w * n_cols, cell_h * n_rows
        if bar is not None:
            bar = legend(min(max(grid_h * 0.9, 2.4), 4.5) if not self.is_portrait else min(max(grid_w * 0.8, 3.0), 5.0, body.width))
        block_w = (row_w + 0.2 if row_labels else 0.0) + grid_w + (bar.width + 0.5 if bar is not None and not self.is_portrait else 0.0)
        block_h = grid_h + (col_h + 0.15 if col_labels else 0.0) + (bar.height + 0.45 if bar is not None and self.is_portrait else 0.0)
        x0 = body.center[0] - block_w / 2 + (row_w + 0.2 if row_labels else 0.0)
        y1 = body.center[1] + block_h / 2 - (col_h + 0.15 if col_labels else 0.0)
        self._grid = Region(x0, y1 - grid_h, x0 + grid_w, y1)

        cells, texts = self._cells(cell_w, cell_h, floor)
        for r, label in enumerate(row_labels):
            label.move_to([x0 - 0.2 - label.width / 2, y1 - cell_h * (r + 0.5), 0])
        for c, label in enumerate(col_labels):
            label.move_to([x0 + cell_w * (c + 0.5), y1 + 0.15 + label.height / 2, 0])
        if bar is not None:
            if self.is_portrait:
                bar.move_to([body.center[0], self._grid.y0 - 0.45 - bar.height / 2, 0])
            else:
                bar.move_to([self._grid.x1 + 0.5 + bar.width / 2, self._grid.center[1], 0])
        self._cells_, self._texts = cells, texts
        self._steps(title, cap, bar, row_labels, col_labels, cells, texts)

    # ----- layout ----------------------------------------------------------------------------

    def _column_labels(self, cell_w: float, size: float, floor: float) -> list[Paragraph]:
        """Column labels wrapped to the cell width; the size shrinks together (to the readable
        minimum) until every word fits (else the labels are scaled and a warning suggests
        shorter ones)."""
        p = self.params
        if not p.columns:
            return []
        room = max(cell_w - 0.08, 0.1)
        for s in dict.fromkeys([size * f for f in (1.0, 0.9, 0.8) if size * f >= floor] + [floor]):
            if all(measure_text(t, room, size=s).fits for t in p.columns):
                return [fit_text(t, room, size=s, min_size=s) for t in p.columns]
        log.warning("scene '%s': heatmap column labels do not fit their columns at a readable size; shorten them", self.spec.id)
        return [fit_text(t, room, size=floor, min_size=floor) for t in p.columns]

    def _cells(self, cell_w: float, cell_h: float, floor: float) -> tuple[list[list[VMobject]], list[list[Mobject | None]]]:
        """The cell rectangles (opaque, coloured by the scale; ``surface`` for null) and their
        value texts (colour chosen per cell for contrast; ``None`` when values are hidden)."""
        p = self.params
        g = self._grid
        gap = min(0.05, 0.06 * min(cell_w, cell_h))
        strings = [[None if v is None else p.number(float(v)) for v in row] for row in p.values]
        size = self._value_size(strings, cell_w - gap, cell_h - gap, floor)
        cells: list[list[VMobject]] = []
        texts: list[list[Mobject | None]] = []
        for r, row in enumerate(p.values):
            cells.append([])
            texts.append([])
            for c, v in enumerate(row):
                center = [g.x0 + cell_w * (c + 0.5), g.y1 - cell_h * (r + 0.5), 0]
                rect = Rectangle(width=cell_w - gap, height=cell_h - gap).move_to(center)
                if v is None:
                    rect.set_fill(self.theme.color("surface"), opacity=1).set_stroke(self.theme.color("dim"), width=1, opacity=0.5)
                else:
                    rect.set_fill(self._scale(float(v)), opacity=1).set_stroke(width=0)
                cells[r].append(rect)
                text = None
                if size is not None and strings[r][c] is not None:
                    text = self.text(strings[r][c], size=size, color=text_color_on(self._scale(float(v)))).move_to(center)
                texts[r].append(text)
        return cells, texts

    def _value_size(self, strings: list[list[str | None]], width: float, height: float, floor: float) -> float | None:
        """The largest size (``value_size`` down to the readable minimum) at which every value
        fits its cell, or ``None`` (values hidden; a warning if ``show_values: true``)."""
        p = self.params
        if p.show_values is False:
            return None
        flat = sorted({s for row in strings for s in row if s is not None}, key=lambda t: (len(t), t))[-4:]   # the longest
        wanted = max(float(self.theme.size(p.value_size)), floor)
        for s in dict.fromkeys([wanted * f for f in (1.0, 0.9, 0.8, 0.7) if wanted * f >= floor] + [floor]):
            probe = [self.text(t, size=s) for t in flat]
            if max(m.width for m in probe) <= width - 0.12 and max(m.height for m in probe) <= height - 0.1:
                return s
        if p.show_values:
            log.warning("scene '%s': the heatmap's cells are too small for readable values; they are hidden (show_values: false silences this)", self.spec.id)
        return None

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, title, cap, bar, row_labels, col_labels, cells, texts) -> None:  # noqa: ANN001
        p = self.params
        n_rows, n_cols = p.shape()

        def cell_group(r: int, c: int) -> VGroup:
            return VGroup(cells[r][c], *([texts[r][c]] if texts[r][c] is not None else []))

        def on_fill(pairs: list[tuple[int, int]]) -> list[tuple[Mobject, Mobject]]:
            """Values written on their cells: dim / highlight recolour them for the cell."""
            return [(texts[r][c], cells[r][c]) for r, c in pairs if texts[r][c] is not None]

        def pop(r: int, c: int, rate: Any = smooth) -> list[Animation]:
            return [FadeIn(cell_group(r, c), scale=0.6, rate_func=rate)]

        title_t = self.target("title", title) if title is not None else None
        legend_t = self.target("legend", bar, entrance=lambda: [FadeIn(bar)]) if bar is not None else None
        cell_t = {}
        g = self._grid
        cw, ch = g.width / n_cols, g.height / n_rows

        def band(x0: float, y0: float, x1: float, y1: float) -> Rectangle:
            return Rectangle(width=x1 - x0, height=y1 - y0, stroke_width=0).move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])

        rows_t = []
        for r in range(n_rows):
            names = [f"row{r + 1}"] + ([f"row:{p.rows[r]}"] if p.rows else [])
            parts = ([row_labels[r]] if row_labels else []) + [m for c in range(n_cols) for m in cell_group(r, c)]
            entrance = (lambda r=r: self._row_entrance(r, row_labels, pop, cell_t))
            outline = band(g.x0, g.y1 - ch * (r + 1), g.x1, g.y1 - ch * r)
            rows_t.append(self.target(names, VGroup(*parts), entrance=entrance, outline=outline, on_fill=on_fill([(r, c) for c in range(n_cols)])))
        for c in range(n_cols):
            names = [f"col{c + 1}"] + ([f"col:{p.columns[c]}"] if p.columns else [])
            parts = ([col_labels[c]] if col_labels else []) + [m for r in range(n_rows) for m in cell_group(r, c)]

            def entrance(c: int = c) -> list[Animation]:
                anims = [a for r in range(n_rows) for a in self.entrance(cell_t[(r, c)])]
                return anims + ([FadeIn(col_labels[c])] if col_labels and not self.on_screen_parts(col_labels[c]) else [])

            outline = band(g.x0 + cw * c, g.y0, g.x0 + cw * (c + 1), g.y1)
            self.target(names, VGroup(*parts), entrance=entrance, outline=outline, on_fill=on_fill([(r, c) for r in range(n_rows)]))
        for r in range(n_rows):
            for c in range(n_cols):
                cell_t[(r, c)] = self.target(
                    f"cell{r + 1}.{c + 1}", cell_group(r, c), entrance=lambda r=r, c=c: pop(r, c), outline=cells[r][c], on_fill=on_fill([(r, c)])
                )
        self._cell_t = cell_t

        def frame() -> list[Animation]:
            anims: list[Animation] = [FadeIn(m) for m in (cap,) if m is not None and not self.on_screen_parts(m)]
            anims += [FadeIn(m) for m in col_labels if not self.on_screen_parts(m)]
            for t in (title_t, legend_t):
                if t is not None:
                    anims += self.entrance(t)
            return anims

        def wave() -> list[Animation]:
            anims = frame() + [FadeIn(m) for m in row_labels if not self.on_screen_parts(m)]
            hidden = [(r, c) for (r, c), t in cell_t.items() if not self.is_shown(t)]
            span = max((r + c for r, c in hidden), default=0) or 1
            for r, c in hidden:
                a = 0.6 * (r + c) / span
                anims += pop(r, c, window(a, a + 0.4))
            return anims

        steps: list[Any] = []
        if p.reveal == "all":
            steps.append(wave)
        else:
            steps.append(lambda: frame() + self._row_entrance(0, row_labels, pop, cell_t))
            steps += [(lambda r=r: self._row_entrance(r, row_labels, pop, cell_t)) for r in range(1, n_rows)]
        if p.highlight:
            steps.append(self._focus)
        self.reveal(steps, fraction=0.75, cap=1.6)
        self.finish()

    def _row_entrance(self, r: int, row_labels: list[Paragraph], pop: Any, cell_t: dict) -> list[Animation]:
        """Row ``r``'s label and its hidden cells, popping in from left to right."""
        n_cols = self.params.shape()[1]
        anims: list[Animation] = [FadeIn(row_labels[r])] if row_labels and not self.on_screen_parts(row_labels[r]) else []
        hidden = [c for c in range(n_cols) if (r, c) in cell_t and not self.is_shown(cell_t[(r, c)])]
        for k, c in enumerate(hidden):
            a = 0.5 * k / max(len(hidden) - 1, 1)
            anims += pop(r, c, window(a, a + 0.5))
        return anims

    def _focus(self) -> list[Animation]:
        """The highlight step: an outline in ``highlight_color`` round each highlighted cell, row
        or column; the other cells dim and their values switch to a colour readable there."""
        p = self.params
        chosen = {cell for ref in p.highlight for cell in p.cells_of(ref)}
        color = self.theme.color(p.highlight_color)
        anims: list[Animation] = []
        for (r, c), t in self._cell_t.items():
            if (r, c) in chosen or not self.is_shown(t):
                continue
            anims.append(dim_to(t, self._cells_[r][c], self.dimmed_opacity))
            if self._texts[r][c] is not None:   # recoloured for the dimmed cell (on_fill)
                anims.append(dim_to(t, self._texts[r][c], self.dimmed_opacity))
        g = self._grid
        n_rows, n_cols = p.shape()
        cw, ch = g.width / n_cols, g.height / n_rows
        for ref in p.highlight:
            cells = p.cells_of(ref)
            rs, cs = [r for r, _ in cells], [c for _, c in cells]
            x0, x1 = g.x0 + cw * min(cs), g.x0 + cw * (max(cs) + 1)
            y1, y0 = g.y1 - ch * min(rs), g.y1 - ch * (max(rs) + 1)
            box = Rectangle(width=x1 - x0, height=y1 - y0, stroke_color=color, stroke_width=4).move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])
            anims.append(Create(box.set_z_index(2)))
        return anims
