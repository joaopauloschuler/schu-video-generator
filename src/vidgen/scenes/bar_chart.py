"""``bar_chart``: labelled bars that grow while their value labels count up (no LaTeX)."""

from typing import Literal

import numpy as np

from vidgen.api import *


@scene("bar_chart")
class BarChart(NarratedScene):
    """``horizontal`` defaults to vertical bars, or horizontal ones in a portrait frame with more
    than 5 bars. ``reveal: all`` (default) grows every bar in beat 1; ``per_beat`` grows bar *i* at beat
    *i* (spread evenly when there are more bars than beats). With ``highlight`` set, one more
    step dims the other bars (it gets its own beat when there is one left).
    """

    outro = 0.5

    class Params(SceneParams):
        title: str = ""
        labels: list[str] = Field(min_length=1)
        values: list[float] = Field(min_length=1)
        unit: str = ""
        value_format: str | None = None
        colors: Literal["palette"] | ThemeColor | list[ThemeColor] = "primary"
        highlight: int | str | None = None
        highlight_color: ThemeColor = "highlight"
        horizontal: bool | None = None
        reveal: Literal["all", "per_beat"] = "all"
        baseline: float = 0.0
        caption: str = ""

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
        top = self.frame_height / 2 - self.margin_y
        bottom = -self.frame_height / 2 + self.margin_y
        head = VGroup()
        if p.title:
            title = fit_text(p.title, self.safe_width, self.safe_height * 0.18, size="heading", weight=BOLD)
            head.add(title.move_to([0, top - title.height / 2, 0]))
            top = title.get_bottom()[1] - 0.45
        if p.caption:
            cap = fit_text(p.caption, self.safe_width, size="small", color="dim")
            head.add(cap.move_to([0, bottom + cap.height / 2, 0]))
            bottom = cap.get_top()[1] + 0.3

        lo, hi = min(p.baseline, *p.values), max(p.baseline, *p.values)
        if hi == lo:
            hi = lo + 1.0
        negative = any(v < p.baseline for v in p.values)
        value_size = "body" if n <= 6 else "caption"

        horizontal = p.horizontal if p.horizontal is not None else (self.is_portrait and n > 5)
        label_scale = 1.0

        def value_label(v: float, i: int) -> Text:
            strong = i == hi_index
            return self.text(
                format_value(v, fmt, p.unit), size=value_size, color=p.highlight_color if strong else "text", weight=BOLD if strong else NORMAL
            ).scale(label_scale)

        finals = [value_label(v, i) for i, v in enumerate(p.values)]
        if not horizontal:  # value labels share one scale and fit their bar's slot
            slot = self.safe_width * (1.0 if self.is_portrait else 0.9) / n
            label_scale = min(1.0, slot * 0.92 / max(f.width for f in finals))
            finals = [value_label(v, i) for i, v in enumerate(p.values)]
        if horizontal:
            geo = self._horizontal(top, bottom, finals, negative)
        else:
            geo = self._vertical(top, bottom, finals, negative)
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
                m.become(place(value_label(value, i), i, value))

            seed = bar_rects[i].copy().stretch(1e-3, 0 if horizontal else 1, about_edge=edge)
            return [ReplacementTransform(seed, bar_rects[i]), UpdateFromAlphaFunc(label, count), FadeIn(cats[i])]

        frame = [FadeIn(head), Create(base_line)] if len(head) else [Create(base_line)]
        steps: list = []
        if p.reveal == "all":
            steps.append(lambda: frame + [LaggedStart(*[AnimationGroup(*grow(i)) for i in range(n)], lag_ratio=0.12)])
        else:
            steps.append(lambda: frame + grow(0))
            steps.extend((lambda i=i: grow(i)) for i in range(1, n))
        if hi_index is not None:

            def focus() -> list[Animation]:
                others = [m for i in range(n) if i != hi_index for m in (bar_rects[i], start_labels[i])]
                return [m.animate.set_opacity(0.4) for m in others] + [
                    Indicate(start_labels[hi_index], color=self.theme.color(p.highlight_color), scale_factor=1.15)
                ]

            steps.append(focus)
        self.reveal(steps, fraction=0.75, cap=1.6)
        self.finish()

    # ----- layouts ---------------------------------------------------------------------------

    def _vertical(self, top: float, bottom: float, finals: list[Text], negative: bool) -> dict:
        p = self.params
        n = len(p.values)
        plot_w = self.safe_width * (1.0 if self.is_portrait else 0.9)
        slot = plot_w / n
        bar_w = min(slot * 0.62, 1.8)
        size = "caption" if n <= 6 else "small"
        cats = [fit_text(lab, slot * 0.94, self.safe_height * 0.12, size=size, color="text") for lab in p.labels]
        cat_h = max(c.height for c in cats)
        val_h = max(f.height for f in finals)
        y_lo = bottom + cat_h + 0.25 + (val_h + 0.12 if negative else 0)
        y_hi = top - val_h - 0.15
        lo, hi = min(p.baseline, *p.values), max(p.baseline, *p.values)
        scale = (y_hi - y_lo) / ((hi - lo) or 1.0)

        def y(v: float) -> float:
            return y_lo + (v - lo) * scale

        xs = [-plot_w / 2 + slot * (i + 0.5) for i in range(n)]
        bars = []
        for x, v in zip(xs, p.values):
            h = max(abs(v - p.baseline) * scale, 1e-3)
            bars.append(Rectangle(width=bar_w, height=h).move_to([x, (y(v) + y(p.baseline)) / 2, 0]))
        for c, x in zip(cats, xs):
            c.move_to([x, bottom + cat_h - c.height / 2, 0])
        axis = Line([-plot_w / 2, y(p.baseline), 0], [plot_w / 2, y(p.baseline), 0], color=self.theme.color("dim"), stroke_width=2)

        def place(label: Mobject, i: int, v: float) -> Mobject:
            end = y(v)
            if v >= p.baseline:
                return label.move_to([xs[i], end + 0.12 + label.height / 2, 0])
            return label.move_to([xs[i], end - 0.12 - label.height / 2, 0])

        return {"labels": cats, "bars": bars, "axis": axis, "place": place}

    def _horizontal(self, top: float, bottom: float, finals: list[Text], negative: bool) -> dict:
        p = self.params
        n = len(p.values)
        size = "caption" if n <= 8 else "small"
        cats = [fit_text(lab, self.safe_width * 0.3, size=size, color="text", align="right") for lab in p.labels]
        cat_w = max(c.width for c in cats)
        val_w = max(f.width for f in finals)
        left, right = -self.safe_width / 2, self.safe_width / 2
        x_lo = left + cat_w + 0.35 + (val_w + 0.3 if negative else 0)
        x_hi = right - val_w - 0.15
        lo, hi = min(p.baseline, *p.values), max(p.baseline, *p.values)
        scale = (x_hi - x_lo) / ((hi - lo) or 1.0)
        plot_h = min(top - bottom, n * 1.1)
        slot = plot_h / n
        y0 = (top + bottom) / 2 + plot_h / 2

        def x(v: float) -> float:
            return x_lo + (v - lo) * scale

        ys = [y0 - slot * (i + 0.5) for i in range(n)]
        thick = min(slot * 0.62, 0.8)
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
