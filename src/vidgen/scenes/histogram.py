"""``histogram``: a distribution as bars over value bins, from raw values or given counts."""

import math
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .actions import dim_to

#: Most bins a histogram draws.
MAX_BINS = 60
_RULES = ("auto", "sturges", "sqrt", "fd")


def nice_width(raw: float) -> float:
    """The round bin width (1, 2, 2.5 or 5 x 10^k) nearest to ``raw`` (on a log scale)."""
    if raw <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(raw))
    return min((m * magnitude for m in (1, 2, 2.5, 5, 10)), key=lambda w: abs(math.log(w / raw)))


def aligned_edges(lo: float, hi: float, width: float, start: float | None = None) -> list[float]:
    """Edges ``width`` apart from ``start`` (default: ``lo`` rounded down to a multiple of
    ``width``) to the first edge at or past ``hi``."""
    first = math.floor(lo / width + 1e-9) * width if start is None else start
    count = max(1, math.ceil((hi - first) / width - 1e-9))
    return [float(f"{first + k * width:.12g}") for k in range(count + 1)]


def _counts(values: list[float], edges: list[float]) -> list[float]:
    return [float(c) for c in np.histogram(np.asarray(values, dtype=float), bins=np.asarray(edges, dtype=float))[0]]


class HistogramCompare(SceneParams):
    """A second distribution drawn as an outline over the same bins: ``{name, values}`` or
    ``{name, counts}``."""

    name: TranslatableStr = ""
    """Its legend name."""
    values: list[float] = Field(default_factory=list)
    """Raw values (binned like the main ones; values outside the bins are left out)."""
    counts: list[float] = Field(default_factory=list)
    """Counts per bin instead of values (one per bin)."""
    color: ThemeColor = "secondary"
    """Outline color."""

    @model_validator(mode="after")
    def _source(self) -> SceneParams:
        if bool(self.values) == bool(self.counts):
            raise ValueError("compare needs either values or counts")
        if any(c < 0 for c in self.counts):
            raise ValueError("compare counts must not be negative")
        return self


@scene("histogram")
class Histogram(NarratedScene):
    """Step 1 draws the axes and grows the bars from left to right; then (each a step of its
    own, so one per beat when there are enough) the ``compare`` outline, the ``mean`` and
    ``median`` markers, and the ``highlight`` of chosen bins (the others dim).

    Bins come from raw ``values`` (``bins`` as a count or a rule, or ``bin_width``; rules give
    round edges such as 10, 20, 30) or from ``counts`` with their ``edges``.

    Action targets: ``title``, ``axes``, ``legend`` (with ``compare``), ``bin<N>`` (1-based),
    ``bin:<range>`` (``bin:10-20``, the edges as the axis writes them), ``compare``, ``mean``
    and ``median``.
    """

    outro = 0.5
    target_patterns = ("title", "axes", "legend", "bin<N>", "bin:<range>", "compare", "mean", "median")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title``, ``axes``, ``legend`` (those present), ``bin<N>`` and ``bin:<range>`` per
        bin, then ``compare``, ``mean``, ``median`` (those present)."""
        names = (["title"] if params.title else []) + ["axes"] + (["legend"] if params.compare else [])
        for i, label in enumerate(params.bin_labels(), start=1):
            names += [f"bin{i}", f"bin:{label}"]
        return names + [n for n in ("compare", "mean", "median") if getattr(params, n)]

    class Params(SceneParams):
        values: list[float] = Field(default_factory=list)
        """Raw values to bin (or give counts and edges)."""
        bins: int | Literal["auto", "sturges", "sqrt", "fd"] = "auto"
        """Number of equal bins over the range, or a rule (auto, sturges, sqrt, fd: Freedman-Diaconis) whose bin width is rounded to 1, 2, 2.5 or 5 x 10^k with edges on its multiples."""
        bin_width: float | None = Field(default=None, gt=0)
        """Bin width (edges on its multiples, or from bin_range's start); overrides bins."""
        bin_range: list[float] | None = Field(default=None, min_length=2, max_length=2)
        """[low, high] of the bins; default: the values' range. Values outside are left out."""
        counts: list[float] = Field(default_factory=list)
        """Counts per bin, instead of values (with edges)."""
        edges: list[float] = Field(default_factory=list)
        """Bin edges for counts: one more than counts, increasing."""
        name: TranslatableStr = ""
        """Legend name of the distribution (shown with compare)."""
        compare: HistogramCompare | None = None
        """A second distribution over the same bins, drawn as an outline: {name, values or counts, color}."""
        percent: bool = False
        """Show each bin's share of the total (%) instead of counts."""
        mean: bool = False
        """Mark the mean with a dashed line and its value (in a step of its own)."""
        median: bool = False
        """Mark the median likewise."""
        highlight: one_or_many(int | str) = Field(default_factory=list)
        """Bins emphasised in a last step: 0-based index or range ('10-20'); the others dim."""
        title: TranslatableStr = ""
        """Chart title (in the header band at the top)."""
        x_label: TranslatableStr = ""
        """X axis label (what was measured)."""
        y_label: TranslatableStr = ""
        """Y axis label (e.g. 'count')."""
        x_format: str | None = None
        """Python format for the bin edges on the axis and in bin:<range> names; default: automatic."""
        x_unit: TranslatableStr = ""
        """Appended to x tick labels and the mean / median values."""
        y_format: str | None = None
        """Python format for y tick labels; default: automatic."""
        color: ThemeColor = "primary"
        """Bar color."""
        mean_color: ThemeColor = "accent"
        """Mean marker color."""
        median_color: ThemeColor = "tertiary"
        """Median marker color."""
        highlight_color: ThemeColor = "highlight"
        """Fill of highlighted bins."""
        label_size: ThemeSize = "caption"
        """Size of tick labels, axis labels, marker labels and the legend (never below the readable minimum)."""
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

        @field_validator("x_format", "y_format")
        @classmethod
        def _format(cls, v: str | None) -> str | None:
            return None if v is None else check_format(v)

        @field_validator("bins")
        @classmethod
        def _bins(cls, v: int | str) -> int | str:
            if isinstance(v, int) and not 1 <= v <= MAX_BINS:
                raise ValueError(f"bins must be 1..{MAX_BINS}")
            return v

        @model_validator(mode="after")
        def _consistent(self) -> SceneParams:
            if bool(self.values) == bool(self.counts):
                raise ValueError("give either values (raw data) or counts with edges")
            if self.counts:
                if len(self.edges) != len(self.counts) + 1:
                    raise ValueError(f"edges needs one more entry than counts: {len(self.counts)} counts, {len(self.edges)} edges")
                if any(b <= a for a, b in zip(self.edges, self.edges[1:])):
                    raise ValueError("edges must be increasing")
                if any(c < 0 for c in self.counts):
                    raise ValueError("counts must not be negative")
                if self.bin_width is not None or self.bin_range is not None or self.bins != "auto":
                    raise ValueError("bins, bin_width and bin_range are for values; counts come with their edges")
                if len(self.counts) > MAX_BINS:
                    raise ValueError(f"at most {MAX_BINS} bins, got {len(self.counts)}")
            else:
                if self.edges:
                    raise ValueError("edges go with counts; for values use bins, bin_width or bin_range")
                if self.bin_range is not None and self.bin_range[1] <= self.bin_range[0]:
                    raise ValueError("bin_range must be [low, high] with high > low")
                n = len(self.bin_edges()) - 1
                if n > MAX_BINS:
                    raise ValueError(f"these bins make {n} bins (at most {MAX_BINS}); use a larger bin_width or fewer bins")
            if sum(self.bin_counts()) <= 0:
                raise ValueError("the histogram is empty: no value falls into the bins")
            if self.compare is not None and self.compare.counts and len(self.compare.counts) != len(self.bin_edges()) - 1:
                raise ValueError(f"compare counts needs one count per bin ({len(self.bin_edges()) - 1}), got {len(self.compare.counts)}")
            for ref in self.highlight:
                self.bin_index(ref)
            return self

        def bin_edges(self) -> list[float]:
            """The bin edges (``edges``, or computed from the values)."""
            if self.counts:
                return [float(e) for e in self.edges]
            lo, hi = self.bin_range or (min(self.values), max(self.values))
            if hi <= lo:
                lo, hi = lo - 0.5, hi + 0.5
            start = lo if self.bin_range else None
            if self.bin_width is not None:
                return aligned_edges(lo, hi, self.bin_width, start)
            if isinstance(self.bins, int):
                return [float(e) for e in np.linspace(lo, hi, self.bins + 1)]
            inside = [v for v in self.values if lo <= v <= hi] or [lo, hi]
            rule = "auto" if self.bins == "auto" else self.bins
            count = max(1, len(np.histogram_bin_edges(np.asarray(inside, dtype=float), bins=rule, range=(lo, hi))) - 1)
            return aligned_edges(lo, hi, nice_width((hi - lo) / count), start)

        def bin_counts(self) -> list[float]:
            """Count per bin (values outside the bins are left out)."""
            return list(self.counts) if self.counts else _counts(self.values, self.bin_edges())

        def compare_counts(self) -> list[float]:
            """Count per bin of ``compare`` (empty without it)."""
            if self.compare is None:
                return []
            return list(self.compare.counts) if self.compare.counts else _counts(self.compare.values, self.bin_edges())

        def edge_texts(self) -> list[str]:
            """The edges as the axis writes them (without the unit)."""
            return tick_texts(self.bin_edges(), self.x_format)

        def bin_labels(self) -> list[str]:
            """Range labels per bin: ``"10-20"``."""
            t = self.edge_texts()
            return [f"{a}-{b}" for a, b in zip(t, t[1:])]

        def bin_index(self, ref: int | str) -> int:
            """The bin ``ref`` names: a 0-based index or a range label."""
            labels = self.bin_labels()
            if isinstance(ref, int):
                if 0 <= ref < len(labels):
                    return ref
                raise ValueError(f"highlight: bin index {ref} out of range (0..{len(labels) - 1})")
            if ref in labels:
                return labels.index(ref)
            raise ValueError(f"highlight: {ref!r} is not a bin; bins: {', '.join(labels[:12])}{', ...' if len(labels) > 12 else ''}")

        def stats(self) -> tuple[float, float]:
            """``(mean, median)``: exact from values, estimated from counts (bin middles;
            the median interpolated in its bin)."""
            if self.values:
                return float(np.mean(self.values)), float(np.median(self.values))
            edges, counts = self.bin_edges(), self.bin_counts()
            total = sum(counts)
            mean = sum((a + b) / 2 * c for a, b, c in zip(edges, edges[1:], counts)) / total
            seen = 0.0
            for a, b, c in zip(edges, edges[1:], counts):
                if c > 0 and seen + c >= total / 2:
                    return mean, a + (b - a) * (total / 2 - seen) / c
                seen += c
            return mean, edges[-1]

    #: Opacity of the other bins when some are highlighted.
    dimmed_opacity = 0.35

    def construct(self) -> None:
        p = self.params
        edges, counts, other = p.bin_edges(), p.bin_counts(), p.compare_counts()
        total, other_total = sum(counts), sum(other)
        if p.percent:
            counts = [100 * c / total for c in counts]
            other = [100 * c / other_total for c in other] if other_total else other
        body = self.safe_area
        frame: list[Mobject] = []
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            frame.append(title)
            body = body.below(title, gap=0.45)
        if p.caption:
            cap = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            frame.append(cap)
            body = body.above(cap, gap=0.3)
        size = chart_label_size(p.label_size)

        x_axis = self._x_axis(edges)
        y_axis = value_axis(counts + other, max_ticks=7 if self.is_portrait else 6, include_zero=True, fmt=p.y_format, unit="%" if p.percent else "", title=p.y_label)
        line_h = self.text("0", size=size).height
        lines = int(p.mean) + int(p.median)   # marker labels stand above the plot (two may stack)
        room = lines * (line_h + 0.2) + 0.1 if lines else 0.0

        def layout(top: float = 0.0) -> ChartAxes:
            return chart_axes(body, x_axis, y_axis, size=size, top=top + room)

        axes = layout()
        legend = None
        if p.compare is not None:
            entries = [(p.name or "data", p.color, "box"), (p.compare.name or "compare", p.compare.color, "line")]
            legend, spot = auto_legend(entries, axes.plot, self._samples(axes, edges, counts, other), body.width, size=size)
            if spot is None:
                axes = layout(top=legend.height + 0.3)
                legend.move_to([body.center[0], body.y1 - legend.height / 2, 0])
            frame.append(legend)
        self._axes = axes

        bars = []
        for a, b, c in zip(edges, edges[1:], counts):
            x0, x1 = axes.x_pos(a), axes.x_pos(b)
            gap = min(0.03, (x1 - x0) * 0.08)
            height = max(axes.y_pos(c) - axes.plot.y0, 1e-3)
            rect = Rectangle(width=max(x1 - x0 - 2 * gap, 1e-3), height=height).move_to([(x0 + x1) / 2, axes.plot.y0 + height / 2, 0])
            bars.append(rect.set_fill(self.theme.color(p.color), opacity=0.9).set_stroke(width=0))
        overlay = self._overlay(axes, edges, other) if p.compare is not None else None
        markers = self._markers(axes, size)
        self._bars = bars
        self._steps(title, frame, axes, legend, bars, overlay, markers)

    # ----- geometry --------------------------------------------------------------------------

    def _x_axis(self, edges: list[float]) -> ChartAxis:
        """Ticks at the edges when the bins are round (equal widths of 1, 2, 2.5 or 5 x 10^k,
        edges on their multiples), else round ticks inside the range."""
        p = self.params
        widths = [b - a for a, b in zip(edges, edges[1:])]
        w = widths[0]
        regular = all(abs(x - w) <= 1e-9 * max(1.0, abs(w)) for x in widths)
        round_edges = regular and abs(nice_width(w) - w) <= 1e-9 * w and all(abs(e / w - round(e / w)) < 1e-6 for e in edges)
        if round_edges or p.x_format:
            ticks = edges
        else:
            ticks = [t for t in axis_ticks(edges[0], edges[-1], 7) if edges[0] - 1e-9 <= t <= edges[-1] + 1e-9]
        return ChartAxis(edges[0], edges[-1], tuple(ticks), tuple(tick_texts(ticks, p.x_format, p.x_unit)), title=p.x_label)

    @staticmethod
    def _step_points(axes: ChartAxes, edges: list[float], counts: list[float]) -> list[np.ndarray]:
        """The outline of a histogram: up, across each bin's top, down."""
        pts = [axes.point(edges[0], 0.0)]
        for a, b, c in zip(edges, edges[1:], counts):
            pts += [axes.point(a, c), axes.point(b, c)]
        pts.append(axes.point(edges[-1], 0.0))
        return pts

    def _samples(self, axes: ChartAxes, edges: list[float], counts: list[float], other: list[float]) -> np.ndarray:
        """Frame points the legend must not cover: the outlines and verticals through the bars."""
        pts = [sample_path(self._step_points(axes, edges, counts))]
        if other:
            pts.append(sample_path(self._step_points(axes, edges, other)))
        for a, b, c in zip(edges, edges[1:], counts):
            for x in (a, (a + b) / 2, b):
                pts.append(sample_path([axes.point(x, 0.0), axes.point(x, c)]))
        return np.vstack(pts)

    def _overlay(self, axes: ChartAxes, edges: list[float], other: list[float]) -> VGroup:
        """The compare distribution: its outline over a faint fill."""
        color = self.theme.color(self.params.compare.color)  # type: ignore[union-attr]
        pts = self._step_points(axes, edges, other)
        area = Polygon(*pts).set_fill(color, opacity=0.1).set_stroke(width=0)
        line = VMobject(stroke_color=color, stroke_width=4).set_points_as_corners(pts)
        return VGroup(area, line)

    def _markers(self, axes: ChartAxes, size: float) -> dict[str, VGroup]:
        """``mean`` / ``median``: a dashed line up from the axis and its labelled value above
        the plot (the second label one line higher when the two would touch)."""
        p = self.params
        mean, median = p.stats()
        out: dict[str, VGroup] = {}
        placed: list[Mobject] = []
        for key, value, color in (("mean", mean, p.mean_color), ("median", median, p.median_color)):
            if not getattr(p, key):
                continue
            c = self.theme.color(color)
            label = self.text(f"{key} {self._number(value)}{p.x_unit}", size=size, color=c, weight=BOLD)
            x = axes.x_pos(value)
            base = axes.y_title.get_top()[1] if axes.y_title is not None else axes.plot.y1   # above the y axis label
            y = base + 0.2 + label.height / 2
            if placed and abs(placed[0].get_x() - x) < (placed[0].width + label.width) / 2 + 0.2:
                y = placed[0].get_top()[1] + 0.2 + label.height / 2
            label.move_to([x, y, 0])
            label.set_x(min(max(label.get_x(), axes.plot.x0 + label.width / 2), axes.plot.x1 - label.width / 2))
            line = DashedLine([x, axes.plot.y0, 0], [x, label.get_bottom()[1] - 0.1, 0], color=c, stroke_width=3, dash_length=0.12)
            out[key] = VGroup(line, label)
            placed.append(label)
        return out

    @staticmethod
    def _number(value: float) -> str:
        """A marker value: 2 decimals below 10, 1 below 100, else none (thousands separated)."""
        decimals = 2 if abs(value) < 10 else 1 if abs(value) < 100 else 0
        return f"{value:,.{decimals}f}"

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, title, frame, axes, legend, bars, overlay, markers) -> None:  # noqa: ANN001
        p = self.params
        pieces = [m for m in frame if m is not legend]

        def intro() -> list[Animation]:
            anims = [FadeIn(m) for m in pieces if not self.on_screen_parts(m)]
            if not self.on_screen_parts(axes.lines):
                anims += [Create(axes.lines), FadeIn(VGroup(*[m for m in axes.group if m is not axes.lines]))]
            if legend is not None and not self.on_screen_parts(legend):
                anims.append(FadeIn(legend))
            return anims

        chart = self.target("axes", axes.group, entrance=intro)
        if title is not None:
            self.target("title", title, entrance=intro)
        if legend is not None:
            self.target("legend", legend, entrance=lambda: [FadeIn(legend)])

        def grow(i: int) -> Animation:
            seed = bars[i].copy().stretch(1e-3, 1, about_edge=DOWN)
            return ReplacementTransform(seed, bars[i])

        labels = p.bin_labels()
        bins = [
            self.target([f"bin{i + 1}", f"bin:{label}"], bars[i], entrance=lambda i=i: self.entrance(chart) + [grow(i)])
            for i, label in enumerate(labels)
        ]
        self._bins = bins

        def grow_all() -> list[Animation]:
            hidden = [grow(i) for i, t in enumerate(bins) if not self.is_shown(t)]
            lag = min(0.15, 2.0 / max(len(hidden), 1))
            return self.entrance(chart) + ([LaggedStart(*hidden, lag_ratio=lag)] if hidden else [])

        steps: list[Any] = [grow_all]
        if overlay is not None:
            area, line = overlay
            compare = self.target("compare", overlay, entrance=lambda: self.entrance(chart) + [AnimationGroup(Create(line, rate_func=linear), FadeIn(area), lag_ratio=0.3)])
            steps.append(lambda: self.entrance(compare))
        for key, group in markers.items():
            line, label = group
            target = self.target(key, group, entrance=lambda line=line, label=label: self.entrance(chart) + [Succession(Create(line), FadeIn(label, shift=DOWN * 0.1))])
            steps.append(lambda target=target: self.entrance(target))
        if p.highlight:
            chosen = sorted({p.bin_index(ref) for ref in p.highlight})
            steps.append(lambda: self._focus(chosen))
        self.reveal(steps, fraction=0.8, cap=2.0)
        self.finish()

    def _focus(self, chosen: list[int]) -> list[Animation]:
        """The highlight step: chosen bins turn ``highlight_color``, the others dim."""
        color = self.theme.color(self.params.highlight_color)
        anims: list[Animation] = [
            dim_to(t, part, self.dimmed_opacity) for i, t in enumerate(self._bins) if i not in chosen for part in self.on_screen_parts(t)
        ]
        anims += [self._bars[i].animate.set_fill(color) for i in chosen if self.on_screen_parts(self._bins[i])]
        return anims
