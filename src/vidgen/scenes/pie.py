"""``pie``: shares of a whole as slices of a circle, or of a ring (``donut: true``)."""

import logging
import math
from typing import Any, Literal, NamedTuple

import numpy as np

from vidgen.api import *

from .actions import dim_to

log = logging.getLogger("vidgen.scenes")

#: Most slices a pie draws (after grouping small ones into "Other").
MAX_SLICES = 24
#: With ``legend`` unset, a pie with more slices than this names them in a legend.
LEGEND_AFTER = 6
#: Gap between a slice and its outside label column, and the leader's radial part (units).
LEAD = 0.5
ELBOW = 0.2


def window(a: float, b: float, rate: Any = smooth) -> Any:
    """A rate function that runs ``rate`` between ``a`` and ``b`` of an animation (0 before, 1 after)."""

    def f(t: float) -> float:
        return rate(min(max((t - a) / ((b - a) or 1.0), 0.0), 1.0))

    return f


class PieSlice(NamedTuple):
    """A slice as drawn (after sorting and grouping): its label, value, colour token or hex
    (``None``: the palette by position), and whether it groups small slices."""

    label: str
    value: float
    color: str | None = None
    other: bool = False


@scene("pie")
class Pie(NarratedScene):
    """A pie (or, with ``donut: true``, a ring with the total in its hole). ``reveal: all``
    (default) sweeps every slice round in beat 1, then writes their labels; ``per_beat`` sweeps
    slice *i* in at beat *i*. With ``highlight`` set, a last step pulls that slice out of the
    pie and dims the others.

    Labels stand inside a slice when they fit there, else outside with a leader line, stacked
    so they never overlap; with many slices (or ``legend: true``) the names go into a legend
    and the slices keep only their values. ``other_below`` / ``max_slices`` group small
    slices into one "Other" slice.

    Action targets: ``title``, ``slice<N>`` (1-based, as drawn), ``slice:<label>`` (a slice
    with its label and leader line), ``center`` (a donut's centre text) and ``legend``.
    """

    outro = 0.5
    target_patterns = ("title", "slice<N>", "slice:<label>", "center", "legend")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``slice<N>`` and ``slice:<label>`` per slice drawn, ``center``
        (a donut with centre text) and ``legend`` (when the names are in a legend)."""
        names = ["title"] if params.title else []
        for i, s in enumerate(params.slices(), start=1):
            names += [f"slice{i}", f"slice:{s.label}"]
        if params.donut and params.center_text():
            names.append("center")
        return names + (["legend"] if params.uses_legend() else [])

    class Params(SceneParams):
        labels: list[str] = Field(min_length=1)
        """Slice names (unique)."""
        values: list[float] = Field(min_length=1)
        """One value per label (0 or more); each slice's share is its value / the total."""
        title: str = ""
        """Chart title (in the header band at the top)."""
        donut: bool = False
        """Draw a ring instead of a full pie, with the total (or center) in the hole."""
        hole: float = Field(default=0.58, ge=0.3, le=0.85)
        """Donut hole radius as a share of the outer radius."""
        center: str | None = None
        """Text in the donut hole; default: the total (value_format and unit); "" leaves it empty."""
        center_label: str = ""
        """A smaller line under the centre text (e.g. 'visits')."""
        show_values: Literal["percent", "value", "both", "none"] = "percent"
        """What each label shows under its name: the share (42%), the value, both (42% · 1,200) or nothing."""
        value_format: str | None = None
        """Python format for values (and the total), e.g. '{:,.0f}'; default: the decimals they need."""
        unit: str = ""
        """Appended to values (and the total), e.g. ' GB'."""
        percent_decimals: int | None = Field(default=None, ge=0, le=3)
        """Decimals of the shares; default 0, or 1 when a slice is under 1 %."""
        colors: Literal["palette"] | ThemeColor | list[ThemeColor] = "palette"
        """'palette' (theme.palette in order, lighter shades when there are more slices than colours), one color, or one per label."""
        sort: bool = False
        """Draw the slices from largest to smallest (else in the order written)."""
        other_below: float | None = Field(default=None, gt=0, lt=50)
        """Group slices smaller than this share (%) into one other_label slice, drawn last."""
        max_slices: int | None = Field(default=None, ge=2, le=MAX_SLICES)
        """Keep the largest max_slices - 1 slices and group the rest into one other_label slice."""
        other_label: str = "Other"
        """Name of the grouped slice."""
        other_color: ThemeColor = "dim"
        """Color of the grouped slice."""
        label_position: Literal["auto", "outside"] = "auto"
        """auto: inside a slice when the label fits there, else outside with a leader line; outside: always outside."""
        legend: bool | None = None
        """Names in a legend beside the pie (below it in 9:16) instead of at the slices; default: with more than 6 slices."""
        reveal: Literal["all", "per_beat"] = "all"
        """all: every slice sweeps in during beat 1; per_beat: slice i at beat i."""
        highlight: int | str | None = None
        """Slice pulled out in a last step (0-based index or label, as drawn); the others dim."""
        explode: float = Field(default=0.1, ge=0, le=0.3)
        """How far the highlighted slice moves out, as a share of the radius."""
        start_angle: float = 90
        """Where the first slice starts, in degrees (90: at the top; 0: at the right)."""
        clockwise: bool = True
        """Slices follow each other clockwise."""
        label_size: ThemeSize = "caption"
        """Size of slice labels and the legend (never below the readable minimum; shrinks towards it when labels do not fit)."""
        center_size: ThemeSize = "title"
        """Size of the donut's centre text (fitted into the hole)."""
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
            n = len(self.values)
            if len(self.labels) != n:
                raise ValueError(f"labels has {len(self.labels)} entries but values has {n}")
            if len(set(self.labels)) != n:
                dup = next(x for x in self.labels if self.labels.count(x) > 1)
                raise ValueError(f"labels must be unique; {dup!r} appears twice")
            if any(v < 0 for v in self.values):
                raise ValueError("values must not be negative (a pie shows parts of a whole)")
            if sum(self.values) <= 0:
                raise ValueError("the values add up to 0: nothing to draw")
            if isinstance(self.colors, list) and len(self.colors) != n:
                raise ValueError(f"colors has {len(self.colors)} entries but values has {n}")
            if self.center and not self.donut:
                raise ValueError("center is the text in a donut's hole; set donut: true")
            drawn = self.slices()
            if len(drawn) > MAX_SLICES:
                raise ValueError(f"{len(drawn)} slices (at most {MAX_SLICES}); group small ones with other_below or max_slices")
            if self.other_label in self.labels and any(s.other for s in drawn):
                raise ValueError(f"other_label {self.other_label!r} is also a label; choose another name")
            if self.highlight is not None:
                self.highlight_index()
            return self

        def slices(self) -> list[PieSlice]:
            """The slices as drawn: sorted (``sort``), small ones grouped (``other_below``,
            ``max_slices``) into one last slice."""
            colors = self.colors if isinstance(self.colors, list) else [None] * len(self.values)
            if isinstance(self.colors, str) and self.colors != "palette":
                colors = [self.colors] * len(self.values)
            items = [PieSlice(label=l, value=v, color=c) for l, v, c in zip(self.labels, self.values, colors)]
            if self.sort:
                items.sort(key=lambda s: -s.value)
            total = sum(self.values)
            small: set[int] = set()
            if self.other_below is not None:
                small |= {i for i, s in enumerate(items) if s.value / total * 100 < self.other_below}
            if self.max_slices is not None and len(items) > self.max_slices:
                ranked = sorted(range(len(items)), key=lambda i: -items[i].value)
                small |= set(ranked[self.max_slices - 1 :])
            if len(small) < 2:   # grouping one slice alone hides its name for nothing
                return items
            other = PieSlice(label=self.other_label, value=sum(items[i].value for i in small), color=self.other_color, other=True)
            return [s for i, s in enumerate(items) if i not in small] + [other]

        def uses_legend(self) -> bool:
            """Whether the names go into a legend (``legend``, default: more than 6 slices)."""
            return self.legend if self.legend is not None else len(self.slices()) > LEGEND_AFTER

        def highlight_index(self) -> int:
            """The highlighted slice's index as drawn."""
            drawn = [s.label for s in self.slices()]
            ref = self.highlight
            if isinstance(ref, int) and not isinstance(ref, bool):
                if 0 <= ref < len(drawn):
                    return ref
                raise ValueError(f"highlight index {ref} out of range (0..{len(drawn) - 1})")
            if ref in drawn:
                return drawn.index(ref)
            grouped = " (it is grouped into " + repr(self.other_label) + ")" if ref in self.labels else ""
            raise ValueError(f"highlight {ref!r} is not a slice{grouped}; slices: {', '.join(drawn)}")

        def number(self, value: float) -> str:
            """A value as written (``value_format`` or the decimals the values need, ``unit``)."""
            return format_value(value, self.value_format or auto_format(self.values), self.unit)

        def percents(self) -> list[str]:
            """Each drawn slice's share, written (``42%``)."""
            drawn = self.slices()
            total = sum(s.value for s in drawn)
            shares = [100 * s.value / total for s in drawn]
            decimals = self.percent_decimals
            if decimals is None:
                decimals = 1 if any(0 < p < 1 for p in shares) else 0
            return [f"{p:.{decimals}f}%" for p in shares]

        def center_text(self) -> str:
            """The donut's centre text (the total unless ``center`` is set)."""
            return self.number(sum(self.values)) if self.center is None else self.center

    #: Text shrunk to fit stops this much above the readable minimum (lint measures lowercase-only
    #: labels a little smaller than the capital H the minimum is based on).
    floor_margin = 1.05
    #: Opacity of the other slices while one is highlighted.
    dimmed_opacity = 0.3

    def construct(self) -> None:
        p = self.params
        slices = p.slices()
        colors = self._colors(slices)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color)
            body = body.below(title, gap=0.45)
        cap = None
        if p.caption:
            cap = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            body = body.above(cap, gap=0.3)

        total = sum(s.value for s in slices)
        sign = -1.0 if p.clockwise else 1.0
        angles, start = [], math.radians(p.start_angle)
        for s in slices:
            sweep = 2 * math.pi * s.value / total
            angles.append((start, sign * sweep))
            start += sign * sweep
        self._angles = angles
        plan = self._plan(slices, colors, angles, body)
        center, radius, inner = plan["center"], plan["radius"], plan["inner"]
        self._center, self._radius, self._inner = center, radius, inner

        wedges = [self._wedge(a, sweep, color) for (a, sweep), color in zip(angles, colors)]
        self._wedges = wedges
        hole = self._hole_text(inner) if p.donut and p.center_text() else None
        self._place_parts(plan, hole)
        self._steps(title, cap, slices, plan, wedges, hole)

    # ----- colours and parts -----------------------------------------------------------------

    def _colors(self, slices: list[PieSlice]) -> list[str]:
        """One colour per slice: its own, or the palette in order; past the palette's length
        the palette repeats in lighter shades (mixed with the background), and the last slice
        never takes the first slice's colour (they touch)."""
        palette = self.theme.palette
        out, k = [], 0
        for s in slices:
            if s.color is not None:
                out.append(self.theme.color(s.color))
                continue
            base, cycle = palette[k % len(palette)], k // len(palette)
            out.append(base if cycle == 0 else mix_colors(base, self.theme.background, max(0.4, 1 - 0.3 * cycle)))
            k += 1
        if len(out) > 2 and out[-1] == out[0] and slices[-1].color is None:
            out[-1] = mix_colors(out[-1], self.theme.background, 0.7)
        return out

    def _wedge(self, start: float, sweep: float, color: str) -> VMobject:
        """A slice from ``start`` over ``sweep`` radians at the planned centre and radii (a thin
        background-coloured edge keeps neighbours apart)."""
        sweep = sweep if abs(sweep) > 1e-4 else math.copysign(1e-4, sweep or 1.0)
        wedge = AnnularSector(inner_radius=self._inner or 0.0, outer_radius=self._radius, angle=sweep, start_angle=start, fill_opacity=1, color=color)
        wedge.shift(self._center)
        edge = 0.0 if abs(abs(sweep) - 2 * math.pi) < 1e-6 else 2.0
        return wedge.set_stroke(self.theme.background, width=edge)

    def _label_texts(self, slices: list[PieSlice]) -> list[tuple[str, str]]:
        """``(name, value)`` lines per slice ("" for a line not shown)."""
        p = self.params
        shares = p.percents()
        names = [s.label for s in slices]
        values = []
        for s, share in zip(slices, shares):
            if p.show_values == "percent":
                values.append(share)
            elif p.show_values == "value":
                values.append(p.number(s.value))
            elif p.show_values == "both":
                values.append(f"{share} · {p.number(s.value)}")
            else:
                values.append("")
        return list(zip(names, values))

    def _label(self, name: str, value: str, size: float, color: str, align: str, width: float) -> VGroup:
        """A slice label: the name (wrapped to ``width``) over the value (bold)."""
        lines = VGroup()
        if name:
            lines.add(fit_text(name, width, size=size, min_size=size, color=color, align=align))
        if value:
            lines.add(self.text(value, size=size, color=color, weight=BOLD))
        edge = {"left": LEFT, "right": RIGHT}.get(align, ORIGIN)
        return lines.arrange(DOWN, buff=size / 160, aligned_edge=edge)

    def _hole_text(self, inner: float) -> VGroup:
        """The donut's centre: the total (or ``center``) and ``center_label``, fitted in the hole."""
        p = self.params
        room = inner * 2 * 0.78
        floor = readable_size() * self.floor_margin
        size = max(float(self.theme.size(p.center_size)), floor)
        big = fit_text(p.center_text(), room, inner * 0.8, size=size, min_size=floor, weight=BOLD, role="heading")
        group = VGroup(big)
        if p.center_label:
            group.add(fit_text(p.center_label, room * 0.9, inner * 0.45, size=chart_label_size(p.label_size), min_size=floor, color="dim"))
        group.arrange(DOWN, buff=0.12)
        if group.height > inner * 1.5:
            group.scale(inner * 1.5 / group.height)
        return group

    # ----- layout ----------------------------------------------------------------------------

    def _plan(self, slices: list[PieSlice], colors: list[str], angles: list[tuple[float, float]], body: Region) -> dict[str, Any]:
        """Radius, centre and every label's place. Labels go inside their slice where they fit;
        the others stand beside the pie with leader lines (``sides``), stacked so they never
        overlap, or, when that leaves the pie too small (narrow 9:16 frames) or does not hold
        them, in a key of colour swatches below / beside the pie (``keys``); with ``legend``
        every label is in that key (``legend``). Tried from
        ``label_size`` down to the readable minimum, the first layout that holds every label
        with a useful radius wins; else the one that drops fewest labels (with a warning)."""
        p = self.params
        floor = readable_size() * self.floor_margin
        wanted = chart_label_size(p.label_size)
        texts = self._label_texts(slices)
        sizes = [wanted * f for f in (1.0, 0.9, 0.8, 0.7, 0.6) if wanted * f >= floor] + [floor]
        modes = ("legend",) if p.uses_legend() else ("sides",) if p.label_position == "outside" else ("sides", "keys")
        best = None
        for size in dict.fromkeys(sizes):
            for mode in modes:
                plan = self._try(slices, colors, angles, body, texts, size, mode)
                if best is None or (len(plan["dropped"]), -plan["radius"]) < (len(best["dropped"]), -best["radius"]):
                    best = plan
                if not plan["dropped"] and plan["radius"] >= plan["min_radius"]:
                    return plan
        assert best is not None
        if best["dropped"]:
            names = ", ".join(slices[i].label for i in best["dropped"])
            log.warning("scene '%s': the pie's labels do not all fit; left out: %s (use other_below or max_slices to group small slices, or legend: true)", self.spec.id, names)
        return best

    def _try(self, slices, colors, angles, body: Region, texts, size: float, mode: str) -> dict[str, Any]:  # noqa: ANN001
        """One layout attempt at label ``size`` in ``mode`` (see :meth:`_plan`)."""
        p = self.params
        explode = p.explode if p.highlight is not None else 0.0
        gap = 0.5
        side_block = None   # a block beside (16:9) or below (9:16) the pie: the key
        has_text = [bool(name or value) for name, value in texts]
        mids = [a + s / 2 for a, s in angles]
        side_w = min(body.width * (0.3 if self.is_portrait else 0.24), 3.2)
        outside = [i for i in range(len(slices)) if has_text[i]]
        inside: dict[int, VGroup] = {}
        keys: VGroup | None = None
        reach = 0.0
        for _ in range(4):
            if mode in ("keys", "legend"):
                keys = self._keys(outside, slices, colors, texts, size, body) if outside else None
                side_block = keys
            area = body
            if side_block is not None:
                if self.is_portrait:
                    area = Region(body.x0, body.y0 + side_block.height + gap, body.x1, body.y1)
                else:
                    area = Region(body.x0, body.y0, body.x1 - side_block.width - gap, body.y1)
            reach = {"left": 0.0, "right": 0.0}   # room the side labels need beyond the pie
            if mode == "sides":
                for i in outside:
                    side = "left" if math.cos(mids[i]) < -1e-9 else "right"
                    width = self._label(*texts[i], size, "text", "right" if side == "left" else "left", side_w).width
                    reach[side] = max(reach[side], width + LEAD + ELBOW)
            room_x = (area.width - reach["left"] - reach["right"]) / 2
            radius = max(min(area.height / 2 * 0.94, room_x) / (1 + explode), 0.4)
            inner = radius * p.hole if p.donut else 0.0
            inside, new_outside = {}, []
            for i in range(len(slices)):
                if not has_text[i]:
                    continue
                fit = None if p.label_position == "outside" or mode == "legend" else self._fits_inside(texts[i], size, angles[i], radius, inner, side_w)
                if fit is None:
                    new_outside.append(i)
                else:
                    inside[i] = fit
            if new_outside == outside:
                break
            outside = new_outside
        # the pie (with its side labels) and the block beside / below it, centred together
        center = area.center.copy()
        center[0] = area.x0 + reach["left"] + (area.width - reach["left"] - reach["right"]) / 2
        block_at = None
        if side_block is not None:
            if self.is_portrait:
                pie_h = 2 * radius * (1 + explode)
                top = body.center[1] + (pie_h + gap + side_block.height) / 2
                center[1] = min(top, body.y1) - pie_h / 2
                block_at = np.array([body.center[0], center[1] - pie_h / 2 - gap - side_block.height / 2, 0.0])
            else:
                used = 2 * radius * (1 + explode)
                left = body.center[0] - (used + gap + side_block.width) / 2
                center[0] = left + used / 2
                block_at = np.array([left + used + gap + side_block.width / 2, center[1], 0.0])
        placed: dict[int, tuple[VGroup, list[np.ndarray] | None]] = {}
        dropped: list[int] = []
        if mode == "sides":
            placed, dropped = self._outside(outside, texts, size, angles, radius, radius * (1 + explode), center, area, side_w)
        elif keys is not None:   # keys / legend
            tall = body.height * (0.6 if self.is_portrait else 1.0)
            if keys.height > tall + 1e-6 or keys.width > body.width + 1e-6:
                if mode == "keys":
                    dropped = list(outside)
                else:   # a legend that cannot fit is scaled (vidgen lint reports text too small)
                    keys.scale(min(tall / keys.height, body.width / keys.width))
            keys.move_to(block_at)
            items = [item for row in keys for item in row]
            placed = {i: (item, None) for i, item in zip(outside, items)}
        return {
            "center": center, "radius": radius, "inner": inner, "size": size, "inside": inside, "outside": placed,
            "dropped": dropped, "keys": keys, "min_radius": 0.3 * min(body.width, body.height), "mode": mode,
        }

    def _keys(self, order: list[int], slices: list[PieSlice], colors: list[str], texts, size: float, body: Region) -> VGroup:  # noqa: ANN001
        """The key for labels that do not fit inside their slice: a colour swatch and the label
        ("Tablet 7%") per slice, in rows below the pie (9:16) or stacked beside it."""
        entries = [(" ".join(t for t in texts[i] if t), colors[i], "box") for i in order]
        if self.is_portrait:
            return chart_legend(entries, body.width, size=size)
        stacked = chart_legend(entries, body.width * 0.4, size=size, stack=True)
        return stacked if stacked.height <= body.height else chart_legend(entries, body.width * 0.45, size=size)

    def _fits_inside(self, text: tuple[str, str], size: float, angle: tuple[float, float], radius: float, inner: float, width: float) -> VGroup | None:
        """The label built for inside the slice, if its box fits in the slice (``None`` if not)."""
        start, sweep = angle
        mid = start + sweep / 2
        lo, hi = sorted((start, start + sweep))
        whole = abs(sweep) >= 2 * math.pi - 1e-6

        def inside(x: float, y: float) -> bool:
            rho = math.hypot(x, y)
            if rho > radius - 0.06 or rho < (inner + 0.06 if inner else 0.0):
                return False
            if whole or rho < 1e-6:
                return whole or not inner
            phi = lo + (math.atan2(y, x) - lo) % (2 * math.pi)
            return lo + 0.06 / rho <= phi <= hi - 0.06 / rho

        spots = [(inner + radius) / 2] if inner else [radius * f for f in (0.6, 0.5, 0.68, 0.4)]
        if whole:
            spots = [(inner + radius) / 2 if inner else 0.0]
        for wrap in dict.fromkeys(min(width, radius * f) for f in (1.2, 0.8, 0.5)):
            label = self._label(*text, size, "text", "center", wrap)
            w, h = label.width / 2 + 0.06, label.height / 2 + 0.06
            for r_mid in spots:
                cx, cy = r_mid * math.cos(mid), r_mid * math.sin(mid)
                if all(inside(cx + dx, cy + dy) for dx in (-w, 0, w) for dy in (-h, 0, h)):
                    return label.move_to([cx, cy, 0])   # relative to the centre; shifted in _place_parts
        return None

    def _outside(self, order: list[int], texts, size: float, angles, radius: float, rim: float, center: np.ndarray, area: Region, width: float) -> tuple[dict[int, tuple[VGroup, list[np.ndarray]]], list[int]]:  # noqa: ANN001
        """Outside labels in two columns, stacked without overlaps near their slice's height,
        and their leader points (on the slice's edge at ``radius``, the elbow beyond ``rim``,
        the label). Returns ``({index: (label, points)},
        dropped)``; when a side does not hold its labels, the smallest slices' are dropped."""
        values = [s.value for s in self.params.slices()]
        sides: dict[str, list[int]] = {"left": [], "right": []}
        mids = {i: angles[i][0] + angles[i][1] / 2 for i in order}
        for i in order:
            sides["right" if math.cos(mids[i]) >= -1e-9 else "left"].append(i)
        placed: dict[int, tuple[VGroup, list[np.ndarray]]] = {}
        dropped: list[int] = []
        gap = 0.12
        for side, members in sides.items():
            align = "left" if side == "right" else "right"
            built = {i: self._label(*texts[i], size, "text", align, width) for i in members}
            keep = list(members)
            while keep and sum(built[i].height for i in keep) + gap * (len(keep) - 1) > area.height:
                smallest = min(keep, key=lambda i: values[i])
                keep.remove(smallest)
                dropped.append(smallest)
            wanted = {i: center[1] + (rim + ELBOW) * math.sin(mids[i]) for i in keep}
            ordered = sorted(keep, key=lambda i: -wanted[i])
            ys = self._stack([wanted[i] for i in ordered], [built[i].height for i in ordered], gap, area.y0, area.y1)
            x_col = center[0] + (rim + ELBOW + LEAD) * (1 if side == "right" else -1)
            for i, y in zip(ordered, ys):
                lab = built[i]
                lab.move_to([x_col + (lab.width / 2 if side == "right" else -lab.width / 2), y, 0])
                d = np.array([math.cos(mids[i]), math.sin(mids[i]), 0.0])
                rim_pt = center + d * (radius + 0.04)
                elbow = center + d * (rim + ELBOW)
                end = np.array([x_col - (0.1 if side == "right" else -0.1), y, 0.0])
                placed[i] = (lab, [rim_pt, elbow, end])
        return placed, sorted(dropped)

    @staticmethod
    def _stack(wanted: list[float], heights: list[float], gap: float, lo: float, hi: float) -> list[float]:
        """Centres for boxes (top to bottom) as close to ``wanted`` as possible, ``gap`` apart,
        within ``lo..hi``."""
        ys: list[float] = []
        for w, h in zip(wanted, heights):
            y = min(w, hi - h / 2)
            if ys:
                y = min(y, ys[-1] - heights[len(ys) - 1] / 2 - gap - h / 2)
            ys.append(y)
        # push back up from the bottom where the stack overflowed
        for k in range(len(ys) - 1, -1, -1):
            floor = lo + heights[k] / 2 if k == len(ys) - 1 else ys[k + 1] + heights[k + 1] / 2 + gap + heights[k] / 2
            ys[k] = max(ys[k], floor)
        return ys

    def _place_parts(self, plan: dict[str, Any], hole: VGroup | None) -> None:
        center = plan["center"]
        for label in plan["inside"].values():
            label.shift(center)
        if hole is not None:
            hole.move_to(center)

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, title, cap, slices, plan, wedges, hole) -> None:  # noqa: ANN001
        p = self.params
        dim = self.theme.color("dim")
        labels: list[VGroup | None] = []
        leaders: list[VMobject | None] = []
        for i in range(len(slices)):
            if i in plan["inside"]:
                lab = plan["inside"][i]
                lab.set_color(text_color_on(wedges[i].get_fill_color().to_hex()))
                labels.append(lab)
                leaders.append(None)
            elif i in plan["outside"]:
                lab, pts = plan["outside"][i]
                labels.append(lab)
                leaders.append(None if pts is None else VMobject(stroke_color=dim, stroke_width=1.5).set_points_as_corners(pts))
            else:
                labels.append(None)
                leaders.append(None)
        self._labels, self._leaders = labels, leaders
        self._inside = set(plan["inside"])

        frame_parts = [m for m in (cap,) if m is not None]
        title_t = self.target("title", title) if title is not None else None

        def sweep(i: int, rate: Any) -> Animation:
            a, s = self._angles[i]
            color = wedges[i].get_fill_color().to_hex()
            final = wedges[i].copy()

            def grow(m: Mobject, alpha: float) -> None:
                if alpha >= 1.0:
                    m.become(final)
                elif alpha <= 0.0:
                    m.become(self._wedge(a, s * 1e-3, color)).set_opacity(0)
                else:
                    m.become(self._wedge(a, s * alpha, color))

            return UpdateFromAlphaFunc(wedges[i], grow, rate_func=rate)

        def extras(i: int, rate: Any) -> list[Animation]:
            out: list[Animation] = []
            if leaders[i] is not None:
                out.append(Create(leaders[i], rate_func=rate))
            if labels[i] is not None:
                out.append(FadeIn(labels[i], rate_func=rate))
            return out

        def parts(i: int) -> VGroup:
            return VGroup(*[m for m in (wedges[i], labels[i], leaders[i]) if m is not None])

        targets = [
            self.target(
                [f"slice{i + 1}", f"slice:{s.label}"], parts(i), entrance=lambda i=i: [sweep(i, window(0, 0.65)), *extras(i, window(0.55, 1.0))],
                outline=wedges[i], on_fill=[(labels[i], wedges[i])] if i in self._inside else [],
            )
            for i, s in enumerate(slices)
        ]
        self._slice_targets = targets
        if plan["mode"] == "legend" and plan["keys"] is not None:   # revealing the legend reveals every slice
            self.target("legend", plan["keys"], entrance=lambda: [a for t in targets for a in self.entrance(t)])
        hole_t = self.target("center", hole, entrance=lambda: [FadeIn(hole, scale=0.8)]) if hole is not None else None

        def frame() -> list[Animation]:
            anims: list[Animation] = [FadeIn(m) for m in frame_parts if not self.on_screen_parts(m)]
            if title_t is not None:
                anims += self.entrance(title_t)
            return anims

        def sweep_all() -> list[Animation]:
            hidden = [i for i, t in enumerate(targets) if not self.is_shown(t)]
            total = sum(abs(self._angles[i][1]) for i in hidden) or 1.0
            anims: list[Animation] = []
            start = 0.0
            for i in hidden:
                share = abs(self._angles[i][1]) / total

                def rate(t: float, a: float = start, b: float = start + share) -> float:
                    pos = smooth(min(t / 0.7, 1.0))
                    return min(max((pos - a) / ((b - a) or 1.0), 0.0), 1.0)

                anims.append(sweep(i, rate))
                anims += extras(i, window(0.65, 1.0))
                start += share
            return anims

        def first() -> list[Animation]:
            anims = frame()
            anims += sweep_all() if p.reveal == "all" else self.entrance(targets[0])
            if hole_t is not None:
                anims += self.entrance(hole_t)
            return anims

        steps: list[Any] = [first]
        if p.reveal == "per_beat":
            steps += [(lambda i=i: self.entrance(targets[i])) for i in range(1, len(slices))]
        if p.highlight is not None:
            k = p.highlight_index()
            steps.append(lambda: self._focus(k))
        self.reveal(steps, fraction=0.75, cap=2.0)
        self.finish()

    def _focus(self, k: int) -> list[Animation]:
        """The highlight step: slice ``k`` moves out along its middle, the others dim (labels
        inside them switch to a colour readable on the dimmed slice)."""
        p = self.params
        a, s = self._angles[k]
        d = np.array([math.cos(a + s / 2), math.sin(a + s / 2), 0.0]) * p.explode * self._radius
        anims: list[Animation] = []
        targets = self._slice_targets
        if self.is_shown(targets[k]):
            anims.append(self._wedges[k].animate.shift(d))
            if k in self._inside:
                anims.append(self._labels[k].animate.shift(d))
            elif self._leaders[k] is not None:   # the leader keeps its label; only its start moves
                corners = self._corner_points(self._leaders[k])
                moved = self._leaders[k].copy().set_points_as_corners([corners[0] + d, *corners[1:]])
                anims.append(Transform(self._leaders[k], moved))
        for i, t in enumerate(targets):
            if i == k or not self.is_shown(t):
                continue
            anims.append(dim_to(t, self._wedges[i], self.dimmed_opacity))
            if self._leaders[i] is not None:
                anims.append(dim_to(t, self._leaders[i], 0.45))
            if self._labels[i] is not None:   # an inside label is recoloured for its dimmed slice (on_fill)
                anims.append(dim_to(t, self._labels[i], self.dimmed_opacity if i in self._inside else 0.45))
        return anims

    @staticmethod
    def _corner_points(path: VMobject) -> list[np.ndarray]:
        """The corners of a polyline made with ``set_points_as_corners``."""
        pts = path.points
        return [pts[0]] + [pts[j] for j in range(3, len(pts), 4)]
