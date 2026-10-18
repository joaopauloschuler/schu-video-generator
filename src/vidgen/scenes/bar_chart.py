"""``bar_chart``: labelled bars that grow while their value labels count up (no LaTeX); with
``changes`` they grow / shrink to new values between beats and, with ``sort``, re-sort."""

from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .chart_changes import ChangingChart, keep_opacity, lerp
from .math_axes import Moved


#: How much a bar's labels fade (at most, half way) while it moves to another slot.
SWAP_FADE = 0.75


@scene("bar_chart")
class BarChart(ChangingChart, NarratedScene):
    """``horizontal`` defaults to vertical bars, or horizontal ones in a portrait frame with more
    than 5 bars. ``reveal: all`` (default) grows every bar in beat 1; ``per_beat`` grows bar *i* at beat
    *i* (spread evenly when there are more bars than beats). Each of ``changes`` is a step of
    its own: the bars grow or shrink to its values (and re-sort with ``sort``), or on a word
    with ``{reveal: change<N>, at: "@word"}``. With ``highlight`` set, one more step dims the
    other bars (it gets its own beat when there is one left).

    Action targets: ``title``, ``bar<N>`` (1-based) and ``bar:<label>`` (a bar with its value and
    category labels), ``change<N>`` (the bars; revealing it plays change N).
    """

    outro = 0.5
    target_patterns = ("title", "bar<N>", "bar:<label>", "change<N>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), then ``bar<N>`` and ``bar:<label>`` per bar, ``change<N>`` per change."""
        names = ["title"] if params.title else []
        for i, label in enumerate(params.labels, start=1):
            names += [f"bar{i}", f"bar:{label}"]
        return names + [f"change{k}" for k in range(1, len(params.changes) + 1)]

    @classmethod
    def reveal_steps(cls, params: Any) -> list[RevealStep]:
        """``reveal: all``: one step, the last bar, rising or falling as the values do from first
        to last; ``per_beat``: one per bar, rising or falling from the bar before; then the
        highlighted bar's step."""
        values = params.values
        if params.reveal == "all":
            steps = [RevealStep(f"bar{len(values)}", value_trend(values))]
        else:
            steps = [RevealStep(f"bar{i + 1}", value_trend(values[i - 1 : i + 1]) if i else None) for i in range(len(values))]
        states = params.states()
        steps += [RevealStep(f"change{k}", value_trend([sum(states[k - 1]), sum(states[k])])) for k in range(1, len(states))]
        hi = params.highlight_index()
        return steps + ([RevealStep(f"bar{hi + 1}")] if hi is not None else [])

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Chart title (in the header band at the top)."""
        labels: list[TranslatableStr] = Field(min_length=1)
        """Bar labels."""
        values: list[float] = Field(min_length=1)
        """One value per label; negatives allowed."""
        changes: list[list[float]] = Field(default_factory=list)
        """Values the bars change to, one list per change (one value per label): change N plays in its own step after the bars grow (before the highlight), or on a word with {reveal: changeN, at: '@word'}. One scale for every change, so heights compare."""
        sort: bool = False
        """Order the bars by value, largest first (at the top when horizontal); they re-sort at each change."""
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
            for k, change in enumerate(self.changes):
                if len(change) != n:
                    raise ValueError(f"changes[{k}] has {len(change)} values but there are {n} bars (one value per label, in the order of labels)")
            if isinstance(self.colors, list) and len(self.colors) != n:
                raise ValueError(f"colors has {len(self.colors)} entries but values has {n}")
            if isinstance(self.highlight, int) and not 0 <= self.highlight < n:
                raise ValueError(f"highlight index {self.highlight} out of range (0..{n - 1})")
            if isinstance(self.highlight, str) and self.highlight not in self.labels:
                raise ValueError(f"highlight {self.highlight!r} is not one of the labels")
            return self

        def states(self) -> list[list[float]]:
            """The values of every state: ``values``, then each change's."""
            return [list(self.values), *(list(c) for c in self.changes)]

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
        states = p.states()
        every = [v for state in states for v in state]
        hi_index = p.highlight_index()
        fmt = p.value_format or auto_format(every)
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

        negative = any(v < p.baseline for v in every)
        floor = readable_size()
        wanted = max(float(self.theme.size(p.value_size or ("body" if n <= 6 else "caption"))), floor)
        horizontal = p.horizontal
        style: tuple[float, bool] | None = (wanted, False)
        if horizontal is not True:
            style = self._value_style(fmt, body.width * self._plot_share() / n * 0.92, wanted, floor, every)
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

        def every_label() -> list[Mobject]:   # each bar's label at each state's value: the room they need
            return [value_label(v, i) for state in states for i, v in enumerate(state)]

        finals = every_label()
        if style is None:  # nothing fits a vertical slot even at the readable size: scale down
            label_scale = body.width * self._plot_share() / n * 0.92 / max(f.width for f in finals)
            finals = every_label()
        label_size = chart_label_size(p.label_size)
        layout = self._horizontal if horizontal else self._vertical
        geo = layout(body, finals, negative, label_size, every)
        cats, base_line, box, place, put_cat = geo["labels"], geo["axis"], geo["box"], geo["place"], geo["cat"]
        self._values, self._slots = list(p.values), self._order(p.values)
        bar_rects = []
        for i, color in enumerate(colors):
            center, width, height = box(self._slots[i], p.values[i])
            bar_rects.append(Rectangle(width=width, height=height).move_to(center).set_fill(color, opacity=0.92).set_stroke(width=0))
            put_cat(cats[i], self._slots[i])
        start_labels = [place(value_label(p.baseline, i), self._slots[i], p.baseline) for i in range(n)]
        outlines = [Rectangle(stroke_width=0) for _ in range(n)]

        def set_label(i: int, value: float, slot: float) -> None:
            label = start_labels[i]
            new = keep_opacity(place(value_label(value, i), slot, value), label)
            label.become(new)
            for old, text in zip(_texts(label), _texts(new)):
                old.original_text = text.original_text  # become() keeps the old string (layout dump)

        def set_bar(i: int, value: float, slot: float, label_value: float | None = None) -> None:
            """Bar ``i`` at ``value`` in ``slot`` (a fraction while it moves), its value label
            at ``label_value`` (default: ``value``) and the box a highlight draws round them."""
            center, width, height = box(slot, value)
            bar_rects[i].stretch_to_fit_width(width).stretch_to_fit_height(height).move_to(center)
            put_cat(cats[i], slot)
            set_label(i, value if label_value is None else label_value, slot)
            final = start_labels[i] if label_value is None else place(value_label(value, i), slot, value)
            outlines[i].become(self._outline(bar_rects[i], final, value >= p.baseline, horizontal))

        for i in range(n):
            set_bar(i, p.values[i], self._slots[i], p.baseline)

        def grow(i: int) -> list[Animation]:
            v, slot = self._values[i], self._slots[i]
            edge = (LEFT if v >= p.baseline else RIGHT) if horizontal else (DOWN if v >= p.baseline else UP)

            def count(m: Mobject, a: float) -> None:
                set_label(i, p.baseline + a * (v - p.baseline), slot)

            seed = bar_rects[i].copy().stretch(1e-3, 0 if horizontal else 1, about_edge=edge)
            return [ReplacementTransform(seed, bar_rects[i]), UpdateFromAlphaFunc(start_labels[i], count), FadeIn(cats[i])]

        bars = [
            self.target(
                [f"bar{i + 1}", f"bar:{lab}"],
                VGroup(bar_rects[i], start_labels[i], cats[i]),
                entrance=lambda i=i: grow(i),
                outline=outlines[i],
            )
            for i, lab in enumerate(p.labels)
        ]
        self._bars, self._rects, self._labels, self._cats, self._set_bar = bars, bar_rects, start_labels, cats, set_bar
        self.setup_changes(len(p.changes), VGroup(*[b.mobject for b in bars]))

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
        steps += self.change_steps()
        if hi_index is not None:

            def focus() -> list[Animation]:
                others = [m for i in range(n) if i != hi_index and self.is_shown(bars[i]) for m in (bar_rects[i], start_labels[i])]
                return [m.animate.set_opacity(0.4) for m in others] + [
                    Indicate(start_labels[hi_index], color=self.theme.color(p.highlight_color), scale_factor=1.15)
                ]

            steps.append(focus)
        self.reveal(steps, fraction=0.75, cap=1.6)
        self.finish()

    def _order(self, values: list[float]) -> list[int]:
        """Each bar's slot: its position, or with ``sort`` its rank, largest first (ties keep
        the order of the labels)."""
        if not self.params.sort:
            return list(range(len(values)))
        ranked = sorted(range(len(values)), key=lambda i: (-values[i], i))
        slots = [0] * len(values)
        for slot, i in enumerate(ranked):
            slots[i] = slot
        return slots

    def play_change(self, old: int, new: int) -> list[Animation]:
        """Every bar grows or shrinks to state ``new``'s value while its label counts and, with
        ``sort``, slides to its new slot; bars not on screen yet take their new place at once."""
        values = self.params.states()[new]
        slots = self._order(values)
        start_values, start_slots = self._values, self._slots
        self._values, self._slots = list(values), slots
        anims: list[Animation] = []
        for i, (v0, v1, s0, s1) in enumerate(zip(start_values, values, start_slots, slots)):
            if not self.is_shown(self._bars[i]):
                self._set_bar(i, v1, s1, self.params.baseline)
                continue

            texts = [(m, _seen(m)) for m in (self._cats[i], self._labels[i])]

            def move(m: Mobject, a: float, i: int = i, v0: float = v0, v1: float = v1, s0: float = s0, s1: float = s1, texts: list = texts) -> None:
                self._set_bar(i, lerp(v0, v1, a), lerp(s0, s1, a))
                if s0 != s1:   # labels passing others fade on the way, so two never read as one
                    for text, seen in texts:
                        text.set_fill(opacity=seen * (1 - SWAP_FADE * np.sin(np.pi * a)))

            anims += [UpdateFromAlphaFunc(self._rects[i], move), Moved(self._labels[i]), Moved(self._cats[i])]
        return anims

    #: A unit under its number (``value_size`` too wide for a slot) is this share of the size.
    unit_ratio = 0.8

    def _plot_share(self) -> float:
        """Share of the body width vertical bars use."""
        return 1.0 if self.is_portrait else 0.9

    def _value_style(self, fmt: str, width: float, size: float, floor: float, values: list[float]) -> tuple[float, bool] | None:
        """``(size, unit below the number)`` for vertical value labels of ``values`` no wider than ``width``:
        the requested size (or 10 % less) on one line, else with the unit (a word, as ``' min'``)
        under the number, then the same at smaller sizes down to ``floor``; ``None`` if nothing
        fits."""
        p = self.params
        texts = [format_value(v, fmt, p.unit) for v in values]
        numbers = [format_value(v, fmt) for v in values]
        splittable = p.unit.startswith(" ") and bool(p.unit.strip())
        bold = p.highlight_index()

        def wide(strings: list[str], s: float) -> float:
            n = len(p.labels)
            return max(self.text(t, size=s, weight=BOLD if i % n == bold else NORMAL).width for i, t in enumerate(strings))

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

    def _vertical(self, body: Region, finals: list[Mobject], negative: bool, label_size: float, values: list[float]) -> dict:
        """The layout of vertical bars for ``values`` (every state's): category labels, the
        axis, and functions of a slot (a fraction while a bar moves) and a value: ``box`` (a
        bar's centre, width, height), ``place`` (a value label), ``cat`` (a category label)."""
        p = self.params
        n = len(p.values)
        plot_w = body.width * self._plot_share()
        slot_w = plot_w / n
        bar_w = min(slot_w * 0.62, 1.8)
        cats = [fit_text(lab, slot_w * 0.94, body.height * 0.14, size=label_size, min_size=readable_size(), color="text") for lab in p.labels]
        cat_h = max(c.height for c in cats)
        val_h = max(f.height for f in finals)
        bottom, top = body.y0, body.y1
        y_lo = bottom + cat_h + 0.25 + (val_h + 0.12 if negative else 0)
        y_hi = top - val_h - 0.15
        lo, hi = min(p.baseline, *values), max(p.baseline, *values)
        scale = (y_hi - y_lo) / ((hi - lo) or 1.0)

        def y(v: float) -> float:
            return y_lo + (v - lo) * scale

        left = body.center[0] - plot_w / 2

        def x(slot: float) -> float:
            return left + slot_w * (slot + 0.5)

        def box(slot: float, v: float) -> tuple[np.ndarray, float, float]:
            return np.array([x(slot), (y(v) + y(p.baseline)) / 2, 0]), bar_w, max(abs(v - p.baseline) * scale, 1e-3)

        def cat(label: Mobject, slot: float) -> None:
            label.move_to([x(slot), bottom + cat_h - label.height / 2, 0])

        axis = Line([left, y(p.baseline), 0], [left + plot_w, y(p.baseline), 0], color=self.theme.color("dim"), stroke_width=2)

        def place(label: Mobject, slot: float, v: float) -> Mobject:
            end = y(v)
            if v >= p.baseline:
                return label.move_to([x(slot), end + 0.12 + label.height / 2, 0])
            return label.move_to([x(slot), end - 0.12 - label.height / 2, 0])

        return {"labels": cats, "axis": axis, "box": box, "place": place, "cat": cat}

    def _horizontal(self, body: Region, finals: list[Mobject], negative: bool, label_size: float, values: list[float]) -> dict:
        """As :meth:`_vertical`, for horizontal bars (slot 0 at the top)."""
        p = self.params
        n = len(p.values)
        cats = [fit_text(lab, body.width * 0.3, size=label_size, min_size=readable_size(), color="text", align="right") for lab in p.labels]
        cat_w = max(c.width for c in cats)
        val_w = max(f.width for f in finals)
        left, right = body.x0, body.x1
        x_lo = left + cat_w + 0.35 + (val_w + 0.3 if negative else 0)
        x_hi = right - val_w - 0.15
        lo, hi = min(p.baseline, *values), max(p.baseline, *values)
        scale = (x_hi - x_lo) / ((hi - lo) or 1.0)
        tallest = max(c.height for c in cats)
        plot_h = min(body.height, n * max(self.slot_height[self.is_portrait], tallest + 0.3))
        slot_h = plot_h / n
        y0 = body.center[1] + plot_h / 2

        def x(v: float) -> float:
            return x_lo + (v - lo) * scale

        def y(slot: float) -> float:
            return y0 - slot_h * (slot + 0.5)

        thick = min(slot_h * 0.62, 0.9)

        def box(slot: float, v: float) -> tuple[np.ndarray, float, float]:
            return np.array([(x(v) + x(p.baseline)) / 2, y(slot), 0]), max(abs(v - p.baseline) * scale, 1e-3), thick

        def cat(label: Mobject, slot: float) -> None:
            label.move_to(np.array([left + cat_w - label.width / 2, y(slot), 0]))

        axis = Line([x(p.baseline), y0, 0], [x(p.baseline), y0 - plot_h, 0], color=self.theme.color("dim"), stroke_width=2)

        def place(label: Mobject, slot: float, v: float) -> Mobject:
            end = x(v)
            if v >= p.baseline:
                return label.move_to([end + 0.15 + label.width / 2, y(slot), 0])
            return label.move_to([end - 0.15 - label.width / 2, y(slot), 0])

        return {"labels": cats, "axis": axis, "box": box, "place": place, "cat": cat}

    #: Height of a horizontal bar's slot (landscape, portrait), unless its label needs more.
    slot_height = (1.1, 1.5)


def _texts(mob: Mobject) -> list[Mobject]:
    """The ``Text`` parts of a value label (itself, or the number and unit lines)."""
    return [mob] if isinstance(mob, Text) else [m for m in mob.submobjects if isinstance(m, Text)]


def _seen(mob: Mobject) -> float:
    """The fill opacity ``mob`` shows (its most opaque part)."""
    return max((float(m.get_fill_opacity()) for m in mob.family_members_with_points()), default=1.0)
