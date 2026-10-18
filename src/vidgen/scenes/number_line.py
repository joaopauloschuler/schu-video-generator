"""``number_line``: one axis across the frame with points, intervals (open or closed ends,
shaded, to infinity) and jumps (arcs from a to b with a label such as ``+3``); the ``trace``
action moves a point along the line (DESIGN §87.7)."""

import re
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .math_axes import TICK, ChainedTargets, LiveLabel, fill_label, label_problem, thinned_labels, tick_label, ticks_within
from .plane_geometry import POINT_RADIUS, name_problem

#: The fields of a point's, an interval's and a jump's label.
POINT_FIELDS = ("x", "name")
JUMP_FIELDS = ("from", "to", "by")
#: Stroke width of an interval's band; how far apart stacked intervals sit (units).
BAND_WIDTH, LANE_GAP = 9.0, 0.34
#: A jump's arc rises this share of its length, at most :data:`JUMP_MAX` units, plus
#: :data:`JUMP_STACK` for each earlier jump it overlaps.
JUMP_RISE, JUMP_MAX, JUMP_STACK = 0.42, 1.1, 0.32
_INTERVAL = re.compile(r"^\s*([\[(])\s*([^,]+?)\s*,\s*([^\])]+?)\s*([\])])\s*$")


def _end_value(text: str) -> float:
    """A bound of interval notation: a number, ``inf``, ``-inf``, ``∞`` or ``-∞``."""
    cleaned = text.replace("−", "-").replace("∞", "inf").replace("+", "")
    try:
        return float(cleaned)
    except ValueError:
        raise ValueError(f"interval bound {text!r}: write a number, inf or -inf") from None


class LinePoint(SceneParams):
    """A point on the line: ``{at, name, label, color, decimals}``; a number alone is where it is."""

    also_accepts = (float,)

    at: float
    """Where it is; the trace action moves it."""
    name: str | None = None
    """Its name (its label by default; target point:<name>)."""
    label: TranslatableStr | None = None
    """Its label: {x} and {name} are filled in as it moves; default: its name; '' for none."""
    color: ThemeColor | None = None
    """Dot colour; default: the colour of the first term its label says, else highlight."""
    decimals: int = Field(1, ge=0, le=4)
    """Decimal places of {x}."""

    @model_validator(mode="before")
    @classmethod
    def _from_number(cls, data: Any) -> Any:
        return {"at": data} if isinstance(data, (int, float)) and not isinstance(data, bool) else data

    @model_validator(mode="after")
    def _check(self) -> "LinePoint":
        problem = (name_problem(self.name) if self.name else None) or (label_problem(self.label, POINT_FIELDS) if self.label else None)
        if problem:
            raise ValueError(problem)
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A number alone is also a point (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "number"}, handler(core_schema)]}


class LineInterval(SceneParams):
    """An interval: ``"[-1, 3)"`` (interval notation; ``inf``, ``-inf``) or ``{from, to, ends,
    label, color}``."""

    also_accepts = (str,)

    start: float | str = Field(alias="from")
    """Its left end (-inf, as text too: to the left end of the line)."""
    to: float | str
    """Its right end (inf, as text too: to the right end of the line)."""
    ends: Literal["[]", "[)", "(]", "()"] = "[]"
    """Which ends belong to it: [ ] closed (a filled dot), ( ) open (a ring); an infinite end is always open."""
    label: TranslatableStr = ""
    """Text above it (e.g. 'x ≥ −1')."""
    color: ThemeColor | None = None
    """Its colour; default: the colour of the first term its label says, else the theme palette in order."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if not isinstance(data, str):
            return data
        match = _INTERVAL.match(data)
        if not match:
            raise ValueError(f"interval {data!r}: write it like '[-1, 3)', '(0, inf)' or {{from: -1, to: 3, ends: '[)'}}")
        return {"from": _end_value(match.group(2)), "to": _end_value(match.group(3)), "ends": match.group(1) + match.group(4)}

    @field_validator("start", "to", mode="before")
    @classmethod
    def _bound(cls, v: Any) -> Any:
        return _end_value(v) if isinstance(v, str) else v

    @model_validator(mode="after")
    def _check(self) -> "LineInterval":
        if self.to <= self.start:
            raise ValueError(f"interval from {self.start:g} to {self.to:g}: the right end must be greater than the left")
        if np.isinf(self.start) and self.start > 0 or np.isinf(self.to) and self.to < 0:
            raise ValueError("an interval runs from -inf or a number to a number or inf")
        return self

    @property
    def closed(self) -> tuple[bool, bool]:
        """Whether each end belongs to it (an infinite one never does)."""
        return (self.ends[0] == "[" and np.isfinite(self.start), self.ends[1] == "]" and np.isfinite(self.to))

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """Interval notation (a string) is also an interval (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}


class LineJump(SceneParams):
    """A jump (an arc from one number to another): ``{from, to, label, color}``; ``[from, to]`` alone."""

    also_accepts = (list,)

    start: float = Field(alias="from")
    """Where it starts."""
    to: float
    """Where it lands."""
    label: TranslatableStr | None = None
    """Text above the arc: {by} (the step, signed: +3, −2), {from} and {to} are filled in; default '{by}'; '' for none."""
    color: ThemeColor | None = None
    """Arc colour; default: the colour of the first term its label says, else accent."""

    @model_validator(mode="before")
    @classmethod
    def _from_list(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)):
            if len(data) != 2:
                raise ValueError("a jump [from, to] has two numbers")
            return {"from": data[0], "to": data[1]}
        return data

    @model_validator(mode="after")
    def _check(self) -> "LineJump":
        if self.start == self.to:
            raise ValueError(f"jump from {self.start:g} to {self.to:g}: the ends are the same")
        problem = label_problem(self.label, JUMP_FIELDS) if self.label else None
        if self.label and "{by:" in self.label:
            problem = f"label {self.label!r}: write {{by}} without a format (it is written +3, −2.5)"
        if problem:
            raise ValueError(problem)
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """``[from, to]`` alone is also a jump (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, handler(core_schema)]}


def ends_places(*values: float, most: int = 3) -> int:
    """The decimal places (up to ``most``) that show ``values`` exactly: 2 for 2.25."""
    return max(len(f"{abs(float(v)):.{most}f}".rstrip("0").partition(".")[2]) for v in values)


def signed(value: float, decimals: int = 1) -> str:
    """``+3``, ``−2``, ``+0.5``: a step with its sign (whole numbers without decimals; trailing
    zeros dropped)."""
    text = f"{abs(value):.0f}" if float(value).is_integer() else f"{abs(value):.{decimals}f}".rstrip("0").rstrip(".")
    return ("+" if value > 0 else "−") + text


def jump_heights(spans: list[tuple[float, float]], lengths: list[float]) -> list[float]:
    """The rise of each jump's arc (units): :data:`JUMP_RISE` of its frame length up to
    :data:`JUMP_MAX`, higher by :data:`JUMP_STACK` for each earlier jump whose span overlaps its own."""
    out = []
    for k, ((a, b), length) in enumerate(zip(spans, lengths)):
        lo, hi = min(a, b), max(a, b)
        stacked = sum(1 for c, d in spans[:k] if min(c, d) < hi - 1e-9 and lo < max(c, d) - 1e-9)
        out.append(min(JUMP_MAX, JUMP_RISE * length) + JUMP_STACK * stacked)
    return out


def interval_lanes(intervals: list[tuple[float, float]]) -> list[int]:
    """Each interval's lane: 0 (on the line) unless it overlaps one already in that lane."""
    lanes: list[int] = []
    for k, (a, b) in enumerate(intervals):
        lane = 0
        while any(lanes[i] == lane and intervals[i][0] < b and a < intervals[i][1] for i in range(k)):
            lane += 1
        lanes.append(lane)
    return lanes


@scene("number_line")
class NumberLine(NarratedScene):
    """One number line across the frame (horizontal in 16:9 and 9:16, fewer ticks in a vertical
    frame) with ``points``, ``intervals`` (closed or open ends, shaded, to infinity) and
    ``jumps`` (arcs with a label such as +3). ``reveal: per_beat`` (default): the line with the
    first item at beat 1, then points, intervals and jumps, one per beat; ``all``: everything in
    beat 1. ``trace`` moves a point along the line (its label's {x} follows).

    Action targets: ``title``, ``line``, ``point<N>`` / ``point:<name>``, ``interval<N>``, ``jump<N>``.
    """

    outro = 0.5
    target_patterns = ("title", "line", "point<N>", "point:<name>", "interval<N>", "jump<N>")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        range: tuple[float, float]
        """[from, to]: the numbers the line shows."""
        step: float | None = Field(None, gt=0)
        """Distance between ticks (1: every whole number); default: a round step for the frame."""
        points: list[LinePoint] = []
        """Points: a number or {at, name, label, color}; moved by the trace action."""
        intervals: list[LineInterval] = []
        """Intervals: '[-1, 3)', '(2, inf)' or {from, to, ends, label, color}."""
        jumps: list[LineJump] = []
        """Jumps: [from, to] or {from, to, label, color}: an arc with '+3' above it."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: the line with the first item at beat 1, then one point, interval or jump per beat; all: everything in beat 1."""
        title_size: ThemeSize = "heading"
        """Title size (1.3x in a portrait frame)."""
        title_color: ThemeColor = "text"
        """Title colour."""
        label_size: ThemeSize = "caption"
        """Size of the numbers and labels (never below the readable minimum)."""

        @model_validator(mode="after")
        def _check(self) -> "NumberLine.Params":
            lo, hi = self.range
            if hi <= lo:
                raise ValueError(f"range [{lo:g}, {hi:g}]: the second end must be greater than the first")
            if self.step is not None and (hi - lo) / self.step > 60:
                raise ValueError(f"step {self.step:g} gives {int((hi - lo) / self.step)} ticks; use a larger step (at most 60 ticks)")
            names = [p.name for p in self.points if p.name]
            if len(set(names)) < len(names):
                raise ValueError("points: two points have the same name")
            for where, values in (
                *((f"points[{k}].at", [p.at]) for k, p in enumerate(self.points)),
                *((f"intervals[{k}]", [v for v in (i.start, i.to) if np.isfinite(v)]) for k, i in enumerate(self.intervals)),
                *((f"jumps[{k}]", [j.start, j.to]) for k, j in enumerate(self.jumps)),
            ):
                for v in values:
                    if not lo - 1e-9 <= v <= hi + 1e-9:
                        raise ValueError(f"{where}: {v:g} is outside the range [{lo:g}, {hi:g}]")
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``line``, ``point<N>`` (and ``point:<name>``), ``interval<N>``, ``jump<N>``."""
        names = (["title"] if params.title else []) + ["line"]
        for k, point in enumerate(params.points, start=1):
            names += [f"point{k}"] + ([f"point:{point.name}"] if point.name else [])
        return names + [f"interval{k}" for k in range(1, len(params.intervals) + 1)] + [f"jump{k}" for k in range(1, len(params.jumps) + 1)]

    @classmethod
    def reveal_steps(cls, params: Any) -> list[RevealStep]:
        """The line (with the first item), then one step per point, interval and jump."""
        items = ([f"point{k}" for k in range(1, len(params.points) + 1)] + [f"interval{k}" for k in range(1, len(params.intervals) + 1)]
                 + [f"jump{k}" for k in range(1, len(params.jumps) + 1)]) or ["line"]
        steps = [RevealStep(name) for name in items]
        return steps[:1] if params.reveal == "all" else steps

    @classmethod
    def trace_problem(cls, params: Any, name: str, options: Any) -> tuple[str, str] | None:
        """``trace`` moves a point to a number inside the range."""
        if not name.startswith("point"):
            return ("target", f"{name}: trace moves a point<N> of a number_line")
        if options.scale is not None:
            return ("scale", f"{name}: scale is for a function_plot's vector; move a point with to")
        if not isinstance(options.to, float):
            return ("to", f"{name}: to is a number on the line, e.g. to: 3")
        lo, hi = params.range
        if not lo - 1e-9 <= options.to <= hi + 1e-9:
            return ("to", f"{name}: {options.to:g} is outside the range [{lo:g}, {hi:g}]")
        return None

    def traced_item(self, target: Target) -> Any:
        """The point the ``trace`` action moves for ``target`` (``None``: nothing)."""
        return next((point for own, point in zip(self._point_targets, self.points) if own is target), None)

    # ----- building -----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            body = body.below(title, gap=0.45)
        size = chart_label_size(p.label_size)
        lo, hi = p.range
        self.line_ends = (body.x0 + 0.45, body.x1 - 0.45)
        ticks = self._ticks()
        tick_texts = {t: tick_label(t, lambda s: self.text(s, size=size, color="dim")) for t in ticks}
        keep = thinned_labels([self.x_of(t) for t in ticks], [tick_texts[t].width for t in ticks], 0.25, self.x_of(0.0) if 0.0 in ticks else None)
        number_h = max((m.height for m in tick_texts.values()), default=0.3)

        jump_frames = [(self.x_of(j.start), self.x_of(j.to)) for j in p.jumps]
        rises = jump_heights([(j.start, j.to) for j in p.jumps], [abs(b - a) for a, b in jump_frames])
        lanes = interval_lanes([(i.start, i.to) for i in p.intervals])
        jump_labels = [self._jump_text(j, size) for j in p.jumps]
        interval_colors = [self._item_color(i.color, i.label, self.theme.palette_color(k)) for k, i in enumerate(p.intervals)]
        interval_labels = [self.text(i.label, size=size, color=c) if i.label else None for i, c in zip(p.intervals, interval_colors)]
        above = max([0.35, *(r + (lbl.height + 0.2 if lbl is not None else 0) for r, lbl in zip(rises, jump_labels)),
                     *(lane * LANE_GAP + (lbl.height + 0.3 if lbl is not None else 0.1) for lane, lbl in zip(lanes, interval_labels))])
        spans = [(min(j.start, j.to), max(j.start, j.to)) for j in p.jumps]
        under = [lane == 0 and lbl is not None and any(a < i.to and i.start < b for a, b in spans)   # clear of the arcs
                 for i, lane, lbl in zip(p.intervals, lanes, interval_labels)]
        point_row = number_h + 0.25   # point labels under the numbers; interval labels below them
        below = TICK + 0.14 + number_h + 0.35 + point_row + (max((lbl.height for lbl, u in zip(interval_labels, under) if u), default=0.0) + 0.1 if any(under) else 0.0)
        y = (body.y0 + body.y1) / 2 + (below - above) / 2
        y = min(max(y, body.y0 + below), body.y1 - above)
        self.line_y = y

        dim = self.theme.color("dim")
        tip = dict(tip_length=0.18, tip_width=0.16)
        line = Line([body.x0 + 0.1, y, 0], [body.x1 - 0.1, y, 0], color=dim, stroke_width=3)
        line.add_tip(**tip)
        line.add_tip(at_start=True, **tip)
        marks = VGroup(*[Line([self.x_of(t), y - TICK * 1.4, 0], [self.x_of(t), y + TICK * 1.4, 0], color=dim, stroke_width=2) for t in ticks])
        numbers = [tick_texts[ticks[i]].move_to([self.x_of(ticks[i]), y - TICK * 1.4 - 0.14 - tick_texts[ticks[i]].height / 2, 0]) for i in keep]
        line_group = VGroup(line, marks, *numbers)

        low_y = y - TICK * 1.4 - 0.2 - number_h
        bands = [self._interval(spec, lane, interval_labels[k], interval_colors[k], low_y - point_row if under[k] else None)
                 for k, (spec, lane) in enumerate(zip(p.intervals, lanes))]
        jumps = [self._jump(spec, jump_frames[k], rises[k], jump_labels[k]) for k, spec in enumerate(p.jumps)]
        jump_ends = {round(v, 9) for j in p.jumps for v in (j.start, j.to)}
        self.points = [_LinePoint(self, spec, size, round(spec.at, 9) in jump_ends, low_y) for spec in p.points]
        lift_clear([m for m in jump_labels if m is not None], [pt.live.group for pt in self.points if pt.live is not None and not pt.under])

        chain = ChainedTargets(self)
        base: list[Target] = []
        if title is not None:
            base.append(chain.add("title", title, lambda: [FadeIn(title)], []))
        base.append(chain.add("line", line_group, lambda: [AnimationGroup(Create(line), FadeIn(marks), *[FadeIn(n) for n in numbers])], list(base)))
        self._point_targets = [
            chain.add([f"point{k + 1}"] + ([f"point:{pt.spec.name}"] if pt.spec.name else []), pt.group, lambda pt=pt: [pt.entrance()], list(base))
            for k, pt in enumerate(self.points)
        ]
        interval_targets = [chain.add(f"interval{k + 1}", group, lambda own=own: [own()], list(base)) for k, (group, own) in enumerate(bands)]
        jump_targets = [chain.add(f"jump{k + 1}", group, lambda own=own: [own()], list(base)) for k, (group, own) in enumerate(jumps)]
        chain.reveal(base, [*self._point_targets, *interval_targets, *jump_targets], p.reveal == "all")
        self.finish()

    def x_of(self, value: float) -> float:
        """The frame x of a number (kept within the range)."""
        lo, hi = self.params.range
        x0, x1 = self.line_ends
        return x0 + (min(max(value, lo), hi) - lo) / (hi - lo) * (x1 - x0)

    def _ticks(self) -> list[float]:
        lo, hi = self.params.range
        if self.params.step:
            step = self.params.step
            first = np.ceil(lo / step - 1e-9) * step
            return [round(float(v), 10) for v in np.arange(first, hi + step * 1e-6, step)]
        return ticks_within(lo, hi, 13)  # labels are thinned to fit (every 2nd, 5th...)

    def _item_color(self, own: str | None, label: str, default: str) -> str:
        """An item's own colour, else the colour of the first term its label says, else ``default``."""
        if own:
            return self.theme.color(own)
        term = find_term(label, active_terms()) if label else None
        return term.color if term is not None else default

    def _interval(self, spec: LineInterval, lane: int, label: Mobject | None, color: str, low_y: float | None) -> tuple[VGroup, Any]:
        """An interval's band (with its end dots or rings, an arrow tip at an infinite end) and its
        entrance; its label above it, or under the numbers at ``low_y`` (where jumps arc above)."""
        y = self.line_y + lane * LANE_GAP
        a = self.x_of(spec.start) if np.isfinite(spec.start) else self.x_of(self.params.range[0]) - 0.35
        b = self.x_of(spec.to) if np.isfinite(spec.to) else self.x_of(self.params.range[1]) + 0.35
        band = Line([a, y, 0], [b, y, 0], color=color, stroke_width=BAND_WIDTH, stroke_opacity=0.85).set_z_index(1)
        ends = VGroup()
        for x, value, is_closed in ((a, spec.start, spec.closed[0]), (b, spec.to, spec.closed[1])):
            if not np.isfinite(value):
                tip = Triangle(color=color, fill_opacity=1, stroke_width=0).scale(0.11).rotate(-PI / 2 if value > 0 else PI / 2)
                ends.add(tip.move_to([x + (0.06 if value > 0 else -0.06), y, 0]))
            elif is_closed:
                ends.add(Dot([x, y, 0], radius=0.11, color=color))
            else:
                ends.add(Circle(radius=0.1, color=color, stroke_width=4, fill_color=self.theme.background, fill_opacity=1).move_to([x, y, 0]))
        ends.set_z_index(2)
        parts: list[Mobject] = [band, ends]
        if label is not None:
            label_y = low_y - label.height / 2 if low_y is not None else y + 0.16 + label.height / 2
            label.move_to([(max(a, self.x_of(self.params.range[0])) + min(b, self.x_of(self.params.range[1]))) / 2, label_y, 0])
            parts.append(label)
        group = VGroup(*parts)

        def entrance() -> Animation:
            return LaggedStart(Create(band), FadeIn(ends, scale=0.5), *([FadeIn(label)] if label is not None else []), lag_ratio=0.5)

        return group, entrance

    def _jump_text(self, spec: LineJump, size: float) -> Mobject | None:
        template = spec.label if spec.label is not None else "{by}"
        if not template:
            return None
        by = spec.to - spec.start
        places = ends_places(spec.start, spec.to)
        content = fill_label(template, {"by": signed(by, places), "from": float(spec.start), "to": float(spec.to)}, places)
        return self.text(content, size=size, color=self._item_color(spec.color, template, self.theme.color("accent")))

    def _jump(self, spec: LineJump, frames: tuple[float, float], rise: float, label: Mobject | None) -> tuple[VGroup, Any]:
        """A jump's arc (with an arrow tip) above the line and its label; and its entrance."""
        a, b = frames
        y = self.line_y
        chord = abs(b - a)
        angle = -4 * np.arctan(2 * rise / chord) * (1 if b > a else -1)  # clockwise left to right: above the line either way
        color = self._item_color(spec.color, spec.label or "", self.theme.color("accent"))
        arc = ArcBetweenPoints([a, y + 0.06, 0], [b, y + 0.06, 0], angle=angle, color=color, stroke_width=4)
        arc.add_tip(tip_length=0.18, tip_width=0.16)
        parts: list[Mobject] = [arc]
        if label is not None:
            label.move_to([(a + b) / 2, arc.get_top()[1] + 0.1 + label.height / 2, 0])  # the tip tilts the arc a little
            parts.append(label)
        group = VGroup(*parts).set_z_index(1)

        def entrance() -> Animation:
            return LaggedStart(Create(arc), *([FadeIn(label)] if label is not None else []), lag_ratio=0.6)

        return group, entrance


def lift_clear(labels: list[Mobject], fixed: list[Mobject], gap: float = 0.06) -> None:
    """Lift each of ``labels`` (in order) just above the ``fixed`` ones and the labels before it
    that it would overlap (short jumps side by side, a point's label beside a jump)."""
    def box(m: Mobject) -> tuple[float, float, float, float]:
        return (m.get_left()[0], m.get_bottom()[1], m.get_right()[0], m.get_top()[1])

    placed = [box(m) for m in fixed]
    for label in labels:
        for _ in range(len(placed) + 1):
            a = box(label)
            hit = [b for b in placed if a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap]
            if not hit:
                break
            label.shift(UP * (max(b[3] for b in hit) + gap - a[1]))
        placed.append(box(label))


class _LinePoint:
    """A point on the number line with its live label (above it, or under the numbers when a jump
    starts or lands there); :meth:`place` moves it."""

    def __init__(self, scene: NumberLine, spec: LinePoint, size: float, under: bool, low_y: float) -> None:
        self.scene, self.spec, self.under, self.low_y = scene, spec, under, low_y
        self.template = spec.label if spec.label is not None else (spec.name or "")
        color = scene._item_color(spec.color, self.template, scene.theme.color("highlight"))
        self.dot = Dot(radius=POINT_RADIUS + 0.02, color=color).set_z_index(3)
        self.live = LiveLabel(scene, size, 3) if self.template else None
        self.group = VGroup(self.dot, *([self.live.group] if self.live else []))
        self.driver = self.dot
        self.x = spec.at
        self.place(spec.at)

    @property
    def state(self) -> float:
        """Where it is (what ``trace`` moves)."""
        return self.x

    @property
    def parts(self) -> list[Mobject]:
        """The dot and its label."""
        return list(self.group)

    def entrance(self) -> Animation:
        """The dot pops in, then its label."""
        return LaggedStart(FadeIn(self.dot, scale=0.4), *([FadeIn(self.live.group, shift=UP * 0.1)] if self.live else []), lag_ratio=0.4)

    def place(self, x: float) -> None:
        """Move it to ``x`` on the line."""
        self.x = float(x)
        frame_x = self.scene.x_of(self.x)
        self.dot.move_to([frame_x, self.scene.line_y, 0])
        if self.live is None:
            return
        self.live.show(fill_label(self.template, {"x": self.x, "name": self.spec.name or ""}, self.spec.decimals))
        label = self.live.group
        y = self.low_y - label.height / 2 if self.under else self.scene.line_y + 0.24 + label.height / 2
        label.move_to([frame_x, y, 0])

