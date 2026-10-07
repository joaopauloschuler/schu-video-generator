"""``bar_chart``: labelled bars that grow while their value labels count up (no LaTeX)."""

from typing import Any, Literal

import numpy as np

from vidgen.api import *


@scene("bar_chart")
class BarChart(NarratedScene):
    """``horizontal`` defaults to vertical bars, or horizontal ones in a portrait frame with more
    than 5 bars. ``reveal: all`` (default) grows every bar in beat 1; ``per_beat`` grows bar *i* at beat
    *i* (spread evenly when there are more bars than beats). With ``highlight`` set, one more
    step dims the other bars (it gets its own beat when there is one left).

    Action targets: ``title``, ``bar<N>`` (1-based) and ``bar:<label>`` (a bar with its value and
    category labels).
    """

    outro = 0.5
    target_patterns = ("title", "bar<N>", "bar:<label>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), then ``bar<N>`` and ``bar:<label>`` per bar."""
        names = ["title"] if params.title else []
        for i, label in enumerate(params.labels, start=1):
            names += [f"bar{i}", f"bar:{label}"]
        return names

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Chart title (in the header band at the top)."""
        labels: list[TranslatableStr] = Field(min_length=1)
        """Bar labels."""
        values: list[float] = Field(min_length=1)
        """One value per label; negatives allowed."""
        unit: TranslatableStr = ""
        """Appended to every value label, e.g. '%' or ' ms'."""
        value_format: str | None = None
        """Python format for value labels, e.g. '{:.1f}'; default: the decimals the values need."""
        colors: Literal["palette"] | ThemeColor | list[ThemeColor] = "primary"
        """One color, one color per bar, or 'palette' (theme.palette)."""
        highlight: int | TextRef | None = None
        """Bar to highlight: 0-based index or label."""
        highlight_color: ThemeColor = "highlight"
        """Color of the highlighted bar's value label."""
        horizontal: bool | None = None
        """Horizontal bars; default: vertical, horizontal in a portrait frame with more than 5 bars."""
        reveal: Literal["all", "per_beat"] = "all"
        """all: every bar grows in beat 1; per_beat: bar i grows at beat i."""
        baseline: float = 0.0
        """Value the bars start from (e.g. 1.0 for losses)."""
        caption: TranslatableStr = ""
        """Note under the chart (e.g. the data source)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption color."""
        title_size: ThemeSize = "heading"
        """Title size (1.3x in a portrait frame)."""
        title_color: ThemeColor = "text"
        """Title color."""
        label_size: ThemeSize = "caption"
        """Category label size (never below the readable minimum)."""
        value_size: ThemeSize | None = None
        """Value label size; default body (caption with more than 6 bars). Labels too wide for their bar shrink towards the readable minimum, a word unit (' min') may move under the number, and in a portrait frame the bars turn horizontal when even that does not fit."""

        @field_validator("value_format")
        @classmethod
        def _format(cls, v: str | None) -> str | None:
            return None if v is None else check_format(v)

        @model_validator(mode="after")
        def _consistent(self) -> SceneParams:
            n = len(self.values)
            if len(self.labels) != n:
                raise ValueError(f"labels has {len(self.labels)} entries but values has {n}")
            if isinstance(self.colors, list) and len(self.colors) != n:
                raise ValueError(f"colors has {len(self.colors)} entries but values has {n}")
            if isinstance(self.highlight, int) and not 0 <= self.highlight < n:
                raise ValueError(f"highlight index {self.highlight} out of range (0..{n - 1})")
            if isinstance(self.highlight, str) and self.highlight not in self.labels:
                raise ValueError(f"highlight {self.highlight!r} is not one of the labels")
            return self

        def highlight_index(self) -> int | None:
            """Index of the highlighted bar, or ``None``."""
            if isinstance(self.highlight, str):
                return self.labels.index(self.highlight)
            return self.highlight

    def bar_colors(self) -> list[str]:
        """One resolved color per bar."""
        p = self.params
        n = len(p.values)
        if p.colors == "palette":
            return [self.theme.palette_color(i) for i in range(n)]
        if isinstance(p.colors, list):
            return [self.theme.color(c) for c in p.colors]
        return [self.theme.color(p.colors)] * n

    def construct(self) -> None:
        p = self.params
        n = len(p.values)
        hi_index = p.highlight_index()
        fmt = p.value_format or auto_format(p.values)
        colors = self.bar_colors()
        body = self.safe_area
        title_target = None
        cap = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            title_target = self.target("title", title)
            body = body.below(title, gap=0.45)
        if p.caption:
            cap = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            body = body.above(cap, gap=0.3)

        negative = any(v < p.baseline for v in p.values)
        floor = readable_size()
        wanted = max(float(self.theme.size(p.value_size or ("body" if n <= 6 else "caption"))), floor)
        horizontal = p.horizontal
        style: tuple[float, bool] | None = (wanted, False)
        if horizontal is not True:
            style = self._value_style(fmt, body.width * self._plot_share() / n * 0.92, wanted, floor)
            if horizontal is None:
                horizontal = self.is_portrait and (n > 5 or style is None)
        if horizontal:
            style = (wanted, False)
        value_size, split = style or (floor, False)
        label_scale = 1.0

        def value_label(v: float, i: int) -> Mobject:
            strong = i == hi_index
            color, weight = (p.highlight_color if strong else "text"), (BOLD if strong else NORMAL)
            number = self.text(format_value(v, fmt, "" if split else p.unit), size=value_size, color=color, weight=weight)
            if split:
                unit = self.text(p.unit.strip(), size=value_size * self.unit_ratio, color=color, weight=weight)
                return VGroup(number, unit).arrange(DOWN, buff=0.06).scale(label_scale)
            return number.scale(label_scale)

        finals = [value_label(v, i) for i, v in enumerate(p.values)]
        if style is None:  # nothing fits a vertical slot even at the readable size: scale down
            label_scale = body.width * self._plot_share() / n * 0.92 / max(f.width for f in finals)
            finals = [value_label(v, i) for i, v in enumerate(p.values)]
        label_size = chart_label_size(p.label_size)
        if horizontal:
            geo = self._horizontal(body, finals, negative, label_size)
        else:
            geo = self._vertical(body, finals, negative, label_size)
        cats, bar_rects, base_line, place = geo["labels"], geo["bars"], geo["axis"], geo["place"]
        for rect, color in zip(bar_rects, colors):
            rect.set_fill(color, opacity=0.92).set_stroke(width=0)
        start_labels = [place(value_label(p.baseline, i), i, p.baseline) for i in range(n)]

        def grow(i: int) -> list[Animation]:
            v = p.values[i]
            label = start_labels[i]
            edge = (LEFT if v >= p.baseline else RIGHT) if horizontal else (DOWN if v >= p.baseline else UP)

            def count(m: Mobject, a: float, i: int = i, v: float = v) -> None:
                value = p.baseline + a * (v - p.baseline)
                label = place(value_label(value, i), i, value)
                m.become(label)
                for old, new in zip(_texts(m), _texts(label)):
                    old.original_text = new.original_text  # become() keeps the old string (layout dump)

            seed = bar_rects[i].copy().stretch(1e-3, 0 if horizontal else 1, about_edge=edge)
            return [ReplacementTransform(seed, bar_rects[i]), UpdateFromAlphaFunc(label, count), FadeIn(cats[i])]

        bars = [
            self.target(
                [f"bar{i + 1}", f"bar:{lab}"],
                VGroup(bar_rects[i], start_labels[i], cats[i]),
                entrance=lambda i=i: grow(i),
                outline=self._outline(bar_rects[i], place(finals[i].copy(), i, p.values[i]), p.values[i] >= p.baseline, horizontal),
            )
            for i, lab in enumerate(p.labels)
        ]

        def frame() -> list[Animation]:  # entrance() skips what an action revealed already
            anims = self.entrance(title_target) if title_target is not None else []
            return anims + ([FadeIn(cap)] if cap is not None else []) + [Create(base_line)]

        def grow_all() -> list[Animation]:
            entrances = [AnimationGroup(*self.entrance(b)) for b in bars if not self.is_shown(b)]
            return [LaggedStart(*entrances, lag_ratio=0.12)] if entrances else []

        steps: list = []
        if p.reveal == "all":
            steps.append(lambda: frame() + grow_all())
        else:
            steps.append(lambda: frame() + self.entrance(bars[0]))
            steps.extend((lambda i=i: self.entrance(bars[i])) for i in range(1, n))
        if hi_index is not None:

            def focus() -> list[Animation]:
                others = [m for i in range(n) if i != hi_index and self.is_shown(bars[i]) for m in (bar_rects[i], start_labels[i])]
                return [m.animate.set_opacity(0.4) for m in others] + [
                    Indicate(start_labels[hi_index], color=self.theme.color(p.highlight_color), scale_factor=1.15)
                ]

            steps.append(focus)
        self.reveal(steps, fraction=0.75, cap=1.6)
        self.finish()

    #: A unit under its number (``value_size`` too wide for a slot) is this share of the size.
    unit_ratio = 0.8

    def _plot_share(self) -> float:
        """Share of the body width vertical bars use."""
        return 1.0 if self.is_portrait else 0.9

    def _value_style(self, fmt: str, width: float, size: float, floor: float) -> tuple[float, bool] | None:
        """``(size, unit below the number)`` for vertical value labels no wider than ``width``:
        the requested size (or 10 % less) on one line, else with the unit (a word, as ``' min'``)
        under the number, then the same at smaller sizes down to ``floor``; ``None`` if nothing
        fits."""
        p = self.params
        texts = [format_value(v, fmt, p.unit) for v in p.values]
        numbers = [format_value(v, fmt) for v in p.values]
        splittable = p.unit.startswith(" ") and bool(p.unit.strip())
        bold = p.highlight_index()

        def wide(strings: list[str], s: float) -> float:
            return max(self.text(t, size=s, weight=BOLD if i == bold else NORMAL).width for i, t in enumerate(strings))

        def fits(s: float, split: bool) -> bool:
            if not split:
                return wide(texts, s) <= width
            return max(wide(numbers, s), self.text(p.unit.strip(), size=s * self.unit_ratio, weight=BOLD).width) <= width

        steps = [[size * f for f in group if size * f >= floor] for group in ((1.0, 0.9), (0.8,), (0.7, 0.6))]
        steps.append([floor])
        for group in steps:
            for split in ((False, True) if splittable else (False,)):
                for s in group:
                    if fits(s, split):
                        return s, split
        return None

    #: Space between the axis and a highlight box around a bar (box buff 0.12 + a little).
    outline_gap = 0.15

    def _outline(self, bar: Mobject, label: Mobject, up: bool, horizontal: bool) -> Rectangle:
        """What a highlight box surrounds: the bar and its final value label, stopping short of the
        axis, so the box sits on the axis instead of crossing it (category labels stay outside)."""
        group = VGroup(bar, label)
        x0, y0 = group.get_corner(DL)[:2]
        x1, y1 = group.get_corner(UR)[:2]
        gap = self.outline_gap
        if horizontal:
            x0, x1 = (bar.get_left()[0] + gap, x1) if up else (x0, bar.get_right()[0] - gap)
        else:
            y0, y1 = (bar.get_bottom()[1] + gap, y1) if up else (y0, bar.get_top()[1] - gap)
        width, height = max(x1 - x0, 0.05), max(y1 - y0, 0.05)
        return Rectangle(width=width, height=height, stroke_width=0).move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])

    # ----- layouts ---------------------------------------------------------------------------

    def _vertical(self, body: Region, finals: list[Mobject], negative: bool, label_size: float) -> dict:
        p = self.params
        n = len(p.values)
        plot_w = body.width * self._plot_share()
        slot = plot_w / n
        bar_w = min(slot * 0.62, 1.8)
        cats = [fit_text(lab, slot * 0.94, body.height * 0.14, size=label_size, min_size=readable_size(), color="text") for lab in p.labels]
        cat_h = max(c.height for c in cats)
        val_h = max(f.height for f in finals)
        bottom, top = body.y0, body.y1
        y_lo = bottom + cat_h + 0.25 + (val_h + 0.12 if negative else 0)
        y_hi = top - val_h - 0.15
        lo, hi = min(p.baseline, *p.values), max(p.baseline, *p.values)
        scale = (y_hi - y_lo) / ((hi - lo) or 1.0)

        def y(v: float) -> float:
            return y_lo + (v - lo) * scale

        left = body.center[0] - plot_w / 2
        xs = [left + slot * (i + 0.5) for i in range(n)]
        bars = []
        for x, v in zip(xs, p.values):
            h = max(abs(v - p.baseline) * scale, 1e-3)
            bars.append(Rectangle(width=bar_w, height=h).move_to([x, (y(v) + y(p.baseline)) / 2, 0]))
        for c, x in zip(cats, xs):
            c.move_to([x, bottom + cat_h - c.height / 2, 0])
        axis = Line([left, y(p.baseline), 0], [left + plot_w, y(p.baseline), 0], color=self.theme.color("dim"), stroke_width=2)

        def place(label: Mobject, i: int, v: float) -> Mobject:
            end = y(v)
            if v >= p.baseline:
                return label.move_to([xs[i], end + 0.12 + label.height / 2, 0])
            return label.move_to([xs[i], end - 0.12 - label.height / 2, 0])

        return {"labels": cats, "bars": bars, "axis": axis, "place": place}

    def _horizontal(self, body: Region, finals: list[Mobject], negative: bool, label_size: float) -> dict:
        p = self.params
        n = len(p.values)
        cats = [fit_text(lab, body.width * 0.3, size=label_size, min_size=readable_size(), color="text", align="right") for lab in p.labels]
        cat_w = max(c.width for c in cats)
        val_w = max(f.width for f in finals)
        left, right = body.x0, body.x1
        x_lo = left + cat_w + 0.35 + (val_w + 0.3 if negative else 0)
        x_hi = right - val_w - 0.15
        lo, hi = min(p.baseline, *p.values), max(p.baseline, *p.values)
        scale = (x_hi - x_lo) / ((hi - lo) or 1.0)
        tallest = max(c.height for c in cats)
        plot_h = min(body.height, n * max(self.slot_height[self.is_portrait], tallest + 0.3))
        slot = plot_h / n
        y0 = body.center[1] + plot_h / 2

        def x(v: float) -> float:
            return x_lo + (v - lo) * scale

        ys = [y0 - slot * (i + 0.5) for i in range(n)]
        thick = min(slot * 0.62, 0.9)
        bars = []
        for yy, v in zip(ys, p.values):
            w = max(abs(v - p.baseline) * scale, 1e-3)
            bars.append(Rectangle(width=w, height=thick).move_to([(x(v) + x(p.baseline)) / 2, yy, 0]))
        for c, yy in zip(cats, ys):
            c.move_to(np.array([left + cat_w - c.width / 2, yy, 0]))
        axis = Line([x(p.baseline), y0, 0], [x(p.baseline), y0 - plot_h, 0], color=self.theme.color("dim"), stroke_width=2)

        def place(label: Mobject, i: int, v: float) -> Mobject:
            end = x(v)
            if v >= p.baseline:
                return label.move_to([end + 0.15 + label.width / 2, ys[i], 0])
            return label.move_to([end - 0.15 - label.width / 2, ys[i], 0])

        return {"labels": cats, "bars": bars, "axis": axis, "place": place}

    #: Height of a horizontal bar's slot (landscape, portrait), unless its label needs more.
    slot_height = (1.1, 1.5)


def _texts(mob: Mobject) -> list[Mobject]:
    """The ``Text`` parts of a value label (itself, or the number and unit lines)."""
    return [mob] if isinstance(mob, Text) else [m for m in mob.submobjects if isinstance(m, Text)]
