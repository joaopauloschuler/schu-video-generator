"""``icon_grid``: icons with labels in a grid, revealed beat by beat."""

import math
from collections.abc import Callable
from typing import Literal, NamedTuple

import numpy as np

from vidgen.api import *


class _Plan(NamedTuple):
    """Sizes of one candidate grid (see ``IconGrid._plan``)."""

    rows: int
    cols: int
    cell_w: float
    col_gap: float
    row_gap: float
    labels: list[Mobject]
    subs: list[Mobject | None]
    block: float
    label_size: float
    sub_size: float
    icon_h: float
    score: tuple[bool, float]


class GridItem(SceneParams):
    """One cell of the grid: ``{icon, label, sublabel?}``."""

    icon: IconName
    """The icon (name or alias, see `vidgen list-icons`)."""
    label: str
    """Short label under the icon (wrapped to the cell)."""
    sublabel: str = ""
    """Optional second line, smaller and dimmer."""


@scene("icon_grid")
class IconGrid(NarratedScene):
    """``reveal: per_beat`` (default): item *i* appears at beat *i* (the heading with the first);
    with more items than beats they are spread evenly. ``groups`` reveals several items per
    step instead; ``reveal: all`` shows every item in beat 1. A ``highlight`` adds a last step
    that dims the other items and enlarges the highlighted one.
    """

    outro = 0.5

    class Params(SceneParams):
        items: list[GridItem] = Field(min_length=1, max_length=16)
        """The cells, {icon, label, sublabel?}, in reading order (2-12 look best)."""
        heading: str = ""
        """Optional heading, shown with the first step."""
        columns: int | None = Field(default=None, ge=1, le=16)
        """Number of columns; default: chosen for the frame (grid_shape)."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: one item per beat; all: every item in beat 1."""
        groups: list[list[int | str]] | None = None
        """Reveal steps as lists of items (0-based index or label); each item exactly once."""
        highlight: int | str | None = None
        """Item (0-based index or label) emphasised in a last step."""
        badge: bool = True
        """Draw each icon on a soft disc in its color."""
        icon_color: Literal["palette"] | ThemeColor = "primary"
        """One color for every icon, or 'palette' (theme.palette, one per item)."""
        color: ThemeColor = "text"
        """Label color."""
        sublabel_color: ThemeColor = "dim"
        """Sublabel color."""
        heading_color: ThemeColor = "text"
        """Heading color."""
        highlight_color: ThemeColor = "highlight"
        """Color of the highlighted item's icon."""
        size: ThemeSize = "body"
        """Label text size (reduced, not below the readable minimum, when space is short)."""
        sublabel_size: ThemeSize = "caption"
        """Sublabel text size."""
        heading_size: ThemeSize = "heading"
        """Heading text size."""

        @model_validator(mode="after")
        def _references(self) -> SceneParams:
            if self.groups is not None:
                seen = [self.item_index(ref, "groups") for group in self.groups for ref in group]
                if any(not group for group in self.groups):
                    raise ValueError("groups: every group needs at least one item")
                missing = sorted(set(range(len(self.items))) - set(seen))
                repeated = sorted({i for i in seen if seen.count(i) > 1})
                if missing or repeated:
                    parts = ([f"missing items {missing}"] if missing else []) + ([f"items listed twice {repeated}"] if repeated else [])
                    raise ValueError(f"groups must list every item exactly once: {'; '.join(parts)}")
            if self.highlight is not None:
                self.item_index(self.highlight, "highlight")
            return self

        def item_index(self, ref: int | str, where: str = "item") -> int:
            """Index of the item ``ref`` names (0-based index or label)."""
            n = len(self.items)
            if isinstance(ref, int):
                if not 0 <= ref < n:
                    raise ValueError(f"{where}: index {ref} out of range (0..{n - 1})")
                return ref
            matches = [i for i, item in enumerate(self.items) if item.label == ref]
            if len(matches) != 1:
                problem = "is not one of the labels" if not matches else "names several items; use an index"
                raise ValueError(f"{where}: {ref!r} {problem}")
            return matches[0]

    #: Cell proportions (width / height) tried with :func:`grid_shape`: narrow cells for short
    #: labels, wide ones for long words; the shape whose layout keeps text and icons largest wins.
    cell_aspects = (0.7, 0.9, 1.2, 1.6, 2.2)
    #: Largest icon (or disc) height, Manim units (the frame's shorter side is 8).
    max_icon = 1.9
    #: Smallest icon (or disc) height before the whole grid is shrunk instead.
    min_icon = 0.5
    #: Widest cell, Manim units, so a few items do not drift apart in a wide frame.
    max_cell_width = 4.2
    #: Space between an icon (or disc) and its label, Manim units.
    icon_gap = 0.2
    #: Icon height inside its disc, as a share of the disc's diameter.
    icon_in_badge = 0.54
    #: Opacity of the other items when one is highlighted (0.55 keeps a ``dim`` sublabel above
    #: lint's 2:1 for de-emphasised text on every built-in preset; 0.45 did not on light ones).
    dimmed_opacity = 0.55
    #: In a vertical frame the heading grows by this factor (as in ``bullets``).
    portrait_growth = 1.3

    def construct(self) -> None:
        p = self.params
        body = self.safe_area
        heading = None
        if p.heading:
            header = self.region("header")
            grow = self.portrait_growth if self.is_portrait else 1.0
            size = float(self.theme.size(p.heading_size)) * grow
            heading = fit_text(p.heading, header.width, header.height, size=size, color=p.heading_color, weight=BOLD, font=self.theme.font_for("heading"))
            place(heading, header, fit="none", align="center")
            body = body.below(heading, gap=0.6 if self.is_portrait else 0.5)
        n = len(p.items)
        if p.columns:
            cols = min(p.columns, n)
            shapes = {(math.ceil(n / cols), cols)}
        else:  # grid_shape's choice for a few cell proportions; the best resulting layout wins
            shapes = {grid_shape(n, body, cell_aspect=a) for a in self.cell_aspects}
        plan = max((self._plan(body, rows, cols) for rows, cols in sorted(shapes)), key=lambda pl: pl.score)
        cells = self._layout(body, plan)

        def reveal_items(indices: list[int], first: bool) -> Callable[[], list[Animation]]:
            def build() -> list[Animation]:
                # cells join the scene whole (an animation of a part would add the part alone,
                # dissolving its cell); every part starts invisible, so nothing flashes
                self.add(*[cells[i] for i in indices])
                anims: list[Animation] = [LaggedStart(*[self._entrance(cells[i]) for i in indices], lag_ratio=0.25)]
                if first and heading is not None:
                    anims.insert(0, FadeIn(heading, shift=DOWN * 0.15))
                return anims

            return build

        if p.groups is not None:
            order = [[p.item_index(ref) for ref in group] for group in p.groups]
        elif p.reveal == "all":
            order = [list(range(n))]
        else:
            order = [[i] for i in range(n)]
        steps: list = [reveal_items(group, k == 0) for k, group in enumerate(order)]
        if p.highlight is not None:
            steps.append(self._focus(cells, p.item_index(p.highlight)))
        self.reveal(steps, fraction=0.7, cap=1.2)
        self.finish()

    def item_colors(self) -> list[str]:
        """One resolved icon colour per item."""
        p = self.params
        if p.icon_color == "palette":
            return [self.theme.palette_color(i) for i in range(len(p.items))]
        return [self.theme.color(p.icon_color)] * len(p.items)

    # ----- layout --------------------------------------------------------------------------------

    def _labels(self, width: float, room: float) -> tuple[list[Mobject], list[Mobject | None], float, float, float]:
        """Labels and sublabels wrapped to ``width``, all at one size, reduced (not below the
        readable size) until the tallest label block takes at most ``room`` and every word fits
        the width; returns them, that block height and the label and sublabel font sizes."""
        p = self.params
        size = float(self.theme.size(p.size))
        sub_size = float(self.theme.size(p.sublabel_size))
        floor = readable_size()
        while True:
            labels = [fit_text(item.label, width, size=size, color=p.color, weight=BOLD) for item in p.items]
            subs = [fit_text(item.sublabel, width, size=sub_size, color=p.sublabel_color) if item.sublabel else None for item in p.items]
            block = max(lab.height + (sub.height + self._sub_gap(size) if sub is not None else 0.0) for lab, sub in zip(labels, subs)) + size / 32 * 0.1
            # a word wider than the cell would be scaled down on its own: shrink every label instead
            fits = self._widest_word(size) <= width and self._widest_word(sub_size, sub=True) <= width
            if (block <= room and fits) or (size <= floor and sub_size <= floor):
                return labels, subs, block, size, sub_size
            size, sub_size = min(size, max(floor, size * 0.9)), min(sub_size, max(floor, sub_size * 0.9))

    def _widest_word(self, size: float, sub: bool = False) -> float:
        """Width of the widest word of the labels (or sublabels) at font ``size``."""
        p = self.params
        words = {w for item in p.items for w in (item.sublabel if sub else item.label).split()}
        return max((self.text(w, size=size, weight=NORMAL if sub else BOLD).width for w in words), default=0.0)

    @staticmethod
    def _sub_gap(size: float) -> float:
        """Space between a label's baseline and the top of its sublabel's capitals."""
        return size / 32 * 0.17

    def _visual(self, index: int, height: float, color: str) -> VGroup:
        """The icon (on its disc with ``badge``), ``height`` units high, centred on the origin."""
        p = self.params
        name = p.items[index].icon
        if not p.badge:
            return VGroup(icon(name, color=color, height=height, theme=self.theme))
        disc = Circle(radius=height / 2).set_fill(color, opacity=0.14).set_stroke(color, width=2.5, opacity=0.45)
        return VGroup(disc, icon(name, color=color, height=height * self.icon_in_badge, theme=self.theme))

    def _plan(self, body: Region, rows: int, cols: int) -> _Plan:
        """Sizes for a ``rows x cols`` grid in ``body``: column width (at most
        :attr:`max_cell_width`), labels at one size, icon height from the height left."""
        col_gap = 0.4
        row_gap = 0.5 if self.is_portrait else 0.4
        cell_w = min((body.width - (cols - 1) * col_gap) / cols, self.max_cell_width)
        row_room = (body.height - (rows - 1) * row_gap) / rows
        labels, subs, block, label_size, sub_size = self._labels(cell_w, row_room * 0.45)
        free = min(cell_w * 0.6, (row_room - block - self.icon_gap) * 0.85, self.max_icon)
        icon_h = max(free, self.min_icon)
        fits = bool(free >= self.min_icon) and self._widest_word(label_size) <= cell_w and self._widest_word(sub_size, sub=True) <= cell_w
        requested = float(self.theme.size(self.params.size))
        score = (fits, float(icon_h * min(1.0, label_size / requested) ** 2))
        return _Plan(rows, cols, cell_w, col_gap, row_gap, labels, subs, block, label_size, sub_size, icon_h, score)

    def _layout(self, body: Region, plan: _Plan) -> list[VGroup]:
        """One ``VGroup(visual, label, sublabel?)`` per item, positioned by ``plan``.

        Every row is as tall as the icon plus the tallest label block, rows are spread over
        spare height, a last row with fewer items is centred, and labels and sublabels sit on
        common baselines. A grid that still does not fit is shrunk as a whole.
        """
        p = self.params
        rows, cols, cell_w, size = plan.rows, plan.cols, plan.cell_w, plan.icon_h
        label_cap = self.text("H", size=plan.label_size, weight=BOLD).height
        sub_cap = self.text("H", size=plan.sub_size).height
        row_h = size + self.icon_gap + plan.block
        spare = max(0.0, body.height - rows * row_h - (rows - 1) * plan.row_gap)
        row_gap = plan.row_gap + min(spare / (rows + 1), 1.0)
        total_w = cols * cell_w + (cols - 1) * plan.col_gap
        total_h = rows * row_h + (rows - 1) * row_gap
        colors = self.item_colors()
        cells: list[VGroup] = []
        for i in range(len(p.items)):
            r, c = divmod(i, cols)
            in_row = min(cols, len(p.items) - r * cols)
            x = body.center[0] - total_w / 2 + cell_w / 2 + (c + (cols - in_row) / 2) * (cell_w + plan.col_gap)
            top = body.center[1] + total_h / 2 - r * (row_h + row_gap)
            visual = self._visual(i, size, colors[i]).move_to(np.array([x, top - size / 2, 0.0]))
            label = plan.labels[i]
            # by baselines, so labels and sublabels line up across a row whatever letters they have
            label.shift(np.array([x - label.get_x(), top - size - self.icon_gap - label_cap - _baseline(label[0]), 0.0]))
            cell = VGroup(visual, label)
            sub = plan.subs[i]
            if sub is not None:
                target = _baseline(label[-1]) - self._sub_gap(plan.label_size) - sub_cap
                sub.shift(np.array([x - sub.get_x(), target - _baseline(sub[0]), 0.0]))
                cell.add(sub)
            cells.append(cell)
        grid_group = VGroup(*cells)
        if grid_group.height > body.height or grid_group.width > body.width:
            shrink_to_fit(grid_group, body.width, body.height).move_to(body.center)
        return cells

    # ----- animation -----------------------------------------------------------------------------

    def _entrance(self, cell: VGroup) -> Animation:
        visual, *texts = cell
        parts: list[Animation] = []
        if self.params.badge:
            parts += [GrowFromCenter(visual[0]), FadeIn(visual[1], scale=0.6)]
        else:
            parts.append(FadeIn(visual[0], scale=0.6))
        parts += [FadeIn(t, shift=UP * 0.15) for t in texts]
        return LaggedStart(*parts, lag_ratio=0.2)

    def _focus(self, cells: list[VGroup], chosen: int) -> Callable[[], list[Animation]]:
        """The highlight step: other items fade to :attr:`dimmed_opacity`, the chosen icon (and
        disc) turns ``highlight_color`` and grows a little."""
        p = self.params
        color = self.theme.color(p.highlight_color)

        def build() -> list[Animation]:
            anims: list[Animation] = [cell.animate.fade(1 - self.dimmed_opacity) for i, cell in enumerate(cells) if i != chosen]
            visual = cells[chosen][0]
            center = visual.get_center()
            target = visual.copy()
            for part in target:
                part.scale(1.15, about_point=center)
            if p.badge:
                target[0].set_fill(color, opacity=0.2).set_stroke(color, opacity=0.8)
            target[-1].set_color(color)
            anims.append(Transform(visual, target))
            return anims

        return build


def _baseline(line: Mobject) -> float:
    """Approximate baseline of a line of text: the median bottom of its glyphs."""
    glyphs = [g for g in line.submobjects if g.has_points()] or [line]
    return float(np.median([g.get_bottom()[1] for g in glyphs]))
