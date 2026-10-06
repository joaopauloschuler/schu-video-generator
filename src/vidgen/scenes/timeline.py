"""``timeline``: dated events along an axis, revealed one per beat while a progress line grows."""

import datetime
import logging
import re
from typing import Any, Literal, NamedTuple

import numpy as np

from vidgen.api import *

from .actions import dim_to

log = logging.getLogger("vidgen.scenes")

_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_ISO_DATE = re.compile(r"^(\d{1,4})-(\d{1,2})(?:-(\d{1,2}))?$")


def date_position(date: str | int | float) -> float | None:
    """A number for a date, for proportional spacing: a number as is, ``"1969"`` -> 1969.0,
    ``"2024-07"`` -> 2024.5, ``"2024-03-15"`` -> 2024 + day of year / days in year; ``None``
    for anything else (``"Q3"``, ``"500 BC"``: give the event an ``at`` instead)."""
    if isinstance(date, (int, float)):
        return float(date)
    text = date.strip()
    if _NUMBER.match(text):
        return float(text)
    found = _ISO_DATE.match(text)
    if not found:
        return None
    year, month, day = int(found[1]), int(found[2]), int(found[3] or 1)
    try:
        when = datetime.date(year, month, day)
    except ValueError:
        return None
    days = 366 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 365
    return year + (when.timetuple().tm_yday - 1) / days


class TimelineEvent(SceneParams):
    """One event: ``{date, title, text?, icon?, at?}``."""

    date: str | int | float
    """The date or label shown above the title ('1969', 'March 2024', 'Phase 1')."""
    title: str = Field(min_length=1)
    """What happened (wrapped to fit)."""
    text: str = ""
    """Optional detail line under the title, smaller and dimmer."""
    icon: IconName | None = None
    """Optional icon in the event's marker on the axis."""
    at: float | None = None
    """Position for spacing: proportional; default: the date when it is a number, a year, YYYY-MM or YYYY-MM-DD."""

    @field_validator("date", mode="before")
    @classmethod
    def _date(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError(f"{value} is not a date (write it as text or a number)")
        if isinstance(value, datetime.date):  # YAML reads 2024-03-15 as a date
            return value.isoformat()
        if isinstance(value, str) and not value.strip():
            raise ValueError("date must not be empty")
        return value

    def shown(self) -> str:
        """The date as written on screen (``1969.0`` -> ``1969``)."""
        if isinstance(self.date, float) and self.date.is_integer():
            return str(int(self.date))
        return str(self.date).strip()

    def position(self) -> float | None:
        """Where the event sits on a proportional axis: ``at``, else :func:`date_position`."""
        return self.at if self.at is not None else date_position(self.date)


class _Fit(NamedTuple):
    """One planned layout (see ``Timeline._plan``)."""

    sides: list[int]
    along: list[float]
    axis: float
    widths: list[float]
    limits: list[float]
    sizes: dict[str, float]
    factor: float
    fits: bool
    lines: int


@scene("timeline")
class Timeline(NarratedScene):
    """Events along a horizontal axis (16:9, square) or a vertical one (9:16), alternating sides
    of it. Step 1 draws the heading and the axis, then each step reveals the next event while a
    progress line grows to it (one event per beat; with more events than beats they are spread
    evenly). A ``highlight`` adds a last step that dims the other events. ``reveal: all`` shows
    every event in beat 1.

    Action targets: ``heading``, ``axis``, ``event<N>`` (1-based) and ``event:<date>`` (marker,
    stem and text of an event).
    """

    outro = 0.5
    target_patterns = ("heading", "axis", "event<N>", "event:<date>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``heading`` (if any), ``axis``, then ``event<N>`` and ``event:<date>`` per event."""
        names = (["heading"] if params.heading else []) + ["axis"]
        for i, event in enumerate(params.events, start=1):
            names += [f"event{i}", f"event:{event.shown()}"]
        return names

    class Params(SceneParams):
        events: list[TimelineEvent] = Field(min_length=2, max_length=10)
        """The events in time order, {date, title, text?, icon?, at?} (2-10; 3-6 read best)."""
        heading: str = ""
        """Optional heading above the timeline."""
        orientation: Literal["auto", "horizontal", "vertical"] = "auto"
        """auto: a horizontal axis in landscape and square frames, a vertical one in portrait."""
        sides: Literal["auto", "alternate", "one"] = "auto"
        """Events alternate sides of the axis, or all stand on one side (below / right); auto: the layout that keeps text largest."""
        spacing: Literal["even", "proportional"] = "even"
        """even: equal gaps; proportional: gaps follow the dates (numbers, years, YYYY-MM(-DD)) or each event's at."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: one event per beat; all: every event in beat 1."""
        highlight: int | str | None = None
        """Event emphasised in a last step (0-based index, or its date or title); the others dim."""
        now: int | str | None = None
        """The present (0-based index, or date or title): that event gets a now_label tag; later ones are drawn as planned (hollow markers, dashed progress)."""
        now_label: str = Field(default="Now", min_length=1)
        """Text of the tag on the `now` event."""
        color: ThemeColor = "text"
        """Event title colour."""
        date_color: ThemeColor = "primary"
        """Date colour."""
        text_color: ThemeColor = "dim"
        """Detail text colour."""
        marker_color: ThemeColor = "primary"
        """Markers and their icons."""
        axis_color: ThemeColor = "dim"
        """The axis line (drawn faint)."""
        progress_color: ThemeColor = "primary"
        """The progress line that grows to each event."""
        heading_color: ThemeColor = "text"
        """Heading colour."""
        highlight_color: ThemeColor = "highlight"
        """Marker and title colour of the highlighted event."""
        now_color: ThemeColor = "accent"
        """Colour of the now tag and the ring around the now marker."""
        size: ThemeSize = "body"
        """Event title size (up to 1.2x larger when every event has room; reduced together, not below the readable minimum, when space is short)."""
        date_size: ThemeSize = "caption"
        """Date size."""
        text_size: ThemeSize = "caption"
        """Detail text size."""
        heading_size: ThemeSize = "heading"
        """Heading size."""

        @model_validator(mode="after")
        def _references(self) -> SceneParams:
            if self.spacing == "proportional":
                missing = [f"events[{i}] ({e.shown()!r})" for i, e in enumerate(self.events) if e.position() is None]
                if missing:
                    raise ValueError(
                        f"spacing: proportional needs a position for every event: {', '.join(missing)} "
                        "has no number, year or YYYY-MM(-DD) date; give it 'at' (a number) or use spacing: even"
                    )
                values = [e.position() for e in self.events]
                for i in range(1, len(values)):
                    if values[i] < values[i - 1]:  # type: ignore[operator]
                        raise ValueError(f"spacing: proportional needs the events in time order; events[{i}] ({self.events[i].shown()!r}) comes before events[{i - 1}]")
            for where in ("highlight", "now"):
                ref = getattr(self, where)
                if ref is not None:
                    self.event_index(ref, where)
            return self

        def event_index(self, ref: int | str, where: str = "event") -> int:
            """Index of the event ``ref`` names: a 0-based index (an int in range), else the
            date as shown, else the title."""
            n = len(self.events)
            if isinstance(ref, int) and 0 <= ref < n:
                return ref
            text = str(ref).strip()
            for key in (TimelineEvent.shown, lambda e: e.title):
                matches = [i for i, e in enumerate(self.events) if key(e) == text]
                if len(matches) == 1:
                    return matches[0]
                if matches:
                    raise ValueError(f"{where}: {ref!r} names several events; use an index (0..{n - 1})")
            raise ValueError(f"{where}: {ref!r} is not an index (0..{n - 1}), a date or a title of the events")

        def positions(self) -> list[float]:
            """Event positions from 0 (first) to 1 (last): even, or by date (``spacing``)."""
            n = len(self.events)
            even = [i / (n - 1) for i in range(n)]
            if self.spacing == "even":
                return even
            values = [float(e.position()) for e in self.events]  # type: ignore[arg-type]
            span = values[-1] - values[0]
            return [(v - values[0]) / span for v in values] if span > 0 else even

    #: In a vertical frame the heading grows by this factor (as in ``bullets``).
    portrait_growth = 1.3
    #: Marker radius (Manim units) with icons / without.
    icon_radius = 0.3
    dot_radius = 0.12
    #: Gap between a marker and its event's text (the stem), and between neighbouring texts.
    stem = 0.3
    card_gap = 0.3
    #: Widest event text in a horizontal / vertical layout (Manim units).
    max_card_width = (5.2, 5.6)
    #: Smallest gap between neighbouring events as a share of the even gap (proportional spacing).
    min_gap_share = 0.45
    #: Text grows up to this factor over the requested sizes when every event has room.
    growth = 1.2
    #: Opacity of the other events when one is highlighted (as ``icon_grid``).
    dimmed_opacity = 0.55

    # ----- layout ----------------------------------------------------------------------------

    @property
    def horizontal(self) -> bool:
        """Whether the axis runs left to right (else top to bottom)."""
        o = self.params.orientation
        return o == "horizontal" or (o == "auto" and not self.is_portrait)

    @property
    def radius(self) -> float:
        """Marker radius: larger when events have icons."""
        return self.icon_radius if any(e.icon for e in self.params.events) else self.dot_radius

    def construct(self) -> None:
        p = self.params
        body = self.safe_area
        heading = None
        if p.heading:
            header = self.region("header")
            size = float(self.theme.size(p.heading_size)) * (self.portrait_growth if self.is_portrait else 1.0)
            heading = fit_text(p.heading, header.width, header.height, size=size, color=p.heading_color, weight=BOLD, role="heading")
            place(heading, header, fit="none", align="center")
            body = body.below(heading, gap=0.5)
        if p.sides == "auto":
            plans = [self._plan(body, "alternate"), self._plan(body, "one")]
            # growth beyond the requested size does not choose the layout; fewer wrapped lines do
            plan = max(plans, key=lambda f: (f.fits, round(min(f.factor, 1.0), 3), -f.lines, f.factor))
        else:
            plan = self._plan(body, p.sides)
        if not plan.fits:
            log.warning(
                "scene '%s': the timeline's %d events do not fit this frame at the readable size; "
                "split it into two timelines (or shorten titles and texts)", self.spec.id, len(p.events),
            )
        self._steps(heading, self._draw(body, plan))

    def _point(self, along: float, across: float) -> np.ndarray:
        """A point from axis coordinates: ``along`` the axis, ``across`` it."""
        return np.array([along, across, 0.0]) if self.horizontal else np.array([across, along, 0.0])

    def _extent(self, body: Region) -> tuple[float, float, float, float]:
        """``(start, end, low, high)``: where the axis begins and ends along (left to right or
        top to bottom) and the body's bounds across it."""
        if self.horizontal:
            return body.x0, body.x1, body.y0, body.y1
        return body.y1, body.y0, body.x0, body.x1

    def _along(self, body: Region) -> list[float]:
        """Event positions along the axis: a margin of half an even gap at both ends;
        proportional positions are pulled towards even ones until neighbours keep a gap."""
        start, end, _, _ = self._extent(body)
        n = len(self.params.events)
        length = abs(end - start)
        pad = length / (2 * n)
        usable = length - 2 * pad
        even = [i / (n - 1) for i in range(n)]
        wanted = self.params.positions()
        need = max(self.min_gap_share / (n - 1), (2 * self.radius + 0.25) / usable) if usable > 0 else 0.0
        for k in range(21):
            w = k / 20
            q = [(1 - w) * a + w * b for a, b in zip(wanted, even)]
            if min(b - a for a, b in zip(q, q[1:])) >= min(need, 1 / (n - 1)) - 1e-9:
                break
        sign = 1.0 if end > start else -1.0
        return [start + sign * (pad + v * usable) for v in q]

    def _plan(self, body: Region, sides_mode: str) -> _Fit:
        """Cards for every event at one common text size: the largest up to the requested sizes
        (not below the readable minimum) at which each fits its room; scaled down as a whole
        when even that is too big (``fits`` false)."""
        p = self.params
        n = len(p.events)
        start, end, low, high = self._extent(body)
        along = self._along(body)
        r = self.radius
        if sides_mode == "alternate":
            sides = [1 if i % 2 == 0 else -1 for i in range(n)]  # above / right first
            axis = (low + high) / 2
            rooms = {1: high - axis - r - self.stem, -1: axis - low - r - self.stem}
        else:
            # one side: below a horizontal axis, right of a vertical one
            side = -1 if self.horizontal else 1
            sides = [side] * n
            axis = high - r - 0.05 if self.horizontal else low + r + 0.05
            rooms = {side: (high - low) - 2 * r - 0.05 - self.stem}
        intervals = self._intervals(along, sides, start, end)
        cap = self.max_card_width[0 if self.horizontal else 1]
        sizes = {role: float(self.theme.size(getattr(p, f"{role}_size" if role != "title" else "size"))) for role in ("date", "title", "text")}
        floors = {"date": readable_size(), "text": readable_size(), "title": readable_size(self.theme.font_for("heading"))}
        lowest = max(min(1.0, floors[k] / sizes[k]) for k in sizes)
        widths, limits = [], []
        for i in range(n):
            span = abs(intervals[i][1] - intervals[i][0])
            widths.append(min(span, cap) if self.horizontal else min(rooms[sides[i]], cap))
            limits.append(rooms[sides[i]] if self.horizontal else span)

        def attempt(factor: float) -> tuple[dict[str, float], float, bool, int]:
            """Sizes at ``factor``, the tallest card's share of its room, no word too wide, lines."""
            scaled = {k: max(min(sizes[k], floors[k]), sizes[k] * factor) for k in sizes}
            worst, clean, lines = 0.0, True, 0
            for i in range(n):
                height, ok, count = self._measure(i, widths[i], scaled)
                clean = clean and ok
                worst = max(worst, height / limits[i] if limits[i] > 0 else 9.0)
                lines += count
            return scaled, worst, clean, lines

        factor = 1.0
        scaled, worst, clean, lines = attempt(factor)
        if worst <= 1.0 and clean:  # room to spare: grow, as long as no text wraps more
            grown = attempt(self.growth)
            if grown[1] <= 1.0 and grown[2] and grown[3] <= lines:
                factor, (scaled, worst, clean, lines) = self.growth, grown
        while (worst > 1.0 or not clean) and factor > lowest + 1e-9:
            factor = max(lowest, factor * min(0.93, max(0.75, 1 / worst if worst > 1 else 0.93)))
            scaled, worst, clean, lines = attempt(factor)
        fits = worst <= 1.0 + 1e-6 and clean
        return _Fit(sides, along, axis, widths, limits, scaled, factor, fits, lines)

    def _cards(self, plan: _Fit) -> list[VGroup]:
        """The planned cards, built (lines evened out); scaled down alike when one is taller
        than its room (the plan's estimate was short, or nothing fitted)."""
        cards = [self._card(i, plan.widths[i], plan.sizes, plan.sides[i]) for i in range(len(plan.widths))]
        worst = max(c.height / limit if limit > 0 else 9.0 for c, limit in zip(cards, plan.limits))
        if worst > 1.0:
            for card in cards:  # one factor for all, so every event keeps the same text size
                card.scale(1 / worst)
        return cards

    def _intervals(self, along: list[float], sides: list[int], start: float, end: float) -> list[tuple[float, float]]:
        """Per event, the stretch along the axis its text may use: up to halfway to the
        neighbouring events on the same side (less ``card_gap``), or to the end of the body."""
        out = []
        for i, a in enumerate(along):
            same = [j for j in range(len(along)) if sides[j] == sides[i] and j != i]
            before = [j for j in same if j < i]
            after = [j for j in same if j > i]
            step = self.card_gap / 2 * (1.0 if end > start else -1.0)
            lo = (along[before[-1]] + a) / 2 + step if before else start
            hi = (along[after[0]] + a) / 2 - step if after else end
            out.append((lo, hi))
        return out

    def _measure(self, index: int, width: float, sizes: dict[str, float]) -> tuple[float, bool, int]:
        """Estimated height of an event's text at ``sizes`` (``measure_text``, a little
        narrower than ``width`` to stay on the safe side), whether every word fits, lines."""
        p = self.params
        event = p.events[index]
        width *= 0.97
        tag = self._tag_size(sizes["date"]) if self._is_now(index) else (0.0, 0.0)
        texts = [(event.shown(), width - (tag[0] + 0.15 if tag[0] else 0.0), {"size": sizes["date"], "weight": BOLD})]
        texts.append((event.title, width, {"size": sizes["title"], "weight": BOLD, "role": "heading"}))
        if event.text:
            texts.append((event.text, width, {"size": sizes["text"]}))
        measured = [measure_text(text, max(w, 0.1), balance=True, **style) for text, w, style in texts]
        height = max(measured[0].height, tag[1]) + sum(m.height for m in measured[1:]) + (len(measured) - 1) * self._row_gap(sizes)
        return height, all(m.fits for m in measured), sum(len(m.lines) for m in measured)

    @staticmethod
    def _row_gap(sizes: dict[str, float]) -> float:
        """Space between date, title and detail text."""
        return 0.12 * sizes["title"] / 32

    def _is_now(self, index: int) -> bool:
        p = self.params
        return p.now is not None and p.event_index(p.now) == index

    def _card(self, index: int, width: float, sizes: dict[str, float], side: int) -> VGroup:
        """The text of an event, ``VGroup(date row, title, detail?)``, wrapped to ``width`` with
        evened-out lines; centred under/over a horizontal axis, aligned towards a vertical one."""
        p = self.params
        event = p.events[index]
        align = "center" if self.horizontal else ("left" if side > 0 else "right")
        edge = {"center": ORIGIN, "left": LEFT, "right": RIGHT}[align]
        tag = self._now_tag(sizes["date"]) if self._is_now(index) else None
        date = fit_text(event.shown(), max(width - (tag.width + 0.15 if tag is not None else 0.0), 0.1), size=sizes["date"], color=p.date_color, weight=BOLD, align=align, balance=True)
        first: Mobject = date
        if tag is not None:
            first = VGroup(date, tag).arrange(RIGHT, buff=0.15)
            tag.match_y(date[0])
        rows: list[Mobject] = [first, fit_text(event.title, width, size=sizes["title"], color=p.color, weight=BOLD, align=align, role="heading", balance=True)]
        if event.text:
            rows.append(fit_text(event.text, width, size=sizes["text"], color=p.text_color, align=align, balance=True))
        return VGroup(*rows).arrange(DOWN, buff=self._row_gap(sizes), aligned_edge=edge)

    def _tag_size(self, size: float) -> tuple[float, float]:
        """Width and height of the now tag for a date of ``size``."""
        label = measure_text(self.params.now_label, 100.0, size=self._tag_font(size), weight=BOLD)
        return label.width + 0.28, label.height + 0.18

    @staticmethod
    def _tag_font(size: float) -> float:
        """The now tag's font size: a little smaller than the date, not below the readable size."""
        return max(size * 0.85, min(size, readable_size()))

    def _now_tag(self, size: float) -> VGroup:
        """The ``now_label`` in a pill on the theme's surface, outlined in ``now_color``."""
        p = self.params
        label = self.text(p.now_label, size=self._tag_font(size), color=p.now_color, weight=BOLD)
        pill = RoundedRectangle(width=label.width + 0.28, height=label.height + 0.18, corner_radius=(label.height + 0.18) / 2)
        pill.set_fill(self.theme.color("surface"), opacity=1).set_stroke(self.theme.color(p.now_color), width=2.5).move_to(label)
        return VGroup(pill, label)

    # ----- drawing ---------------------------------------------------------------------------

    def _draw(self, body: Region, plan: _Fit) -> "_Drawing":
        """Axis, progress segments, markers, stems and texts in place."""
        p = self.params
        n = len(p.events)
        r = self.radius
        start, end, low, high = self._extent(body)
        direction = 1.0 if end > start else -1.0
        intervals = self._intervals(plan.along, plan.sides, start, end)
        now = p.event_index(p.now) if p.now is not None else None
        cards = self._cards(plan)
        stems = []
        for i, card in enumerate(cards):
            side, a = plan.sides[i], plan.along[i]
            lo, hi = sorted(intervals[i])
            near = plan.axis + side * (r + self.stem)
            if self.horizontal:  # centred over its marker, pushed inwards at the ends
                x = float(np.clip(a, lo + card.width / 2, hi - card.width / 2)) if hi - lo >= card.width else (lo + hi) / 2
                card.move_to(np.array([x, near + side * card.height / 2, 0.0]))
                edge = card.get_bottom()[1] if side > 0 else card.get_top()[1]
            else:  # the date's line level with the marker where there is room
                top = float(np.clip(a + card[0].height / 2, lo + card.height, hi)) if hi - lo >= card.height else hi
                card.move_to(np.array([near + side * card.width / 2, top - card.height / 2, 0.0]))
                edge = card.get_left()[0] if side > 0 else card.get_right()[0]
            stem = Line(self._point(a, plan.axis + side * r), self._point(a, edge - side * 0.08))
            stems.append(stem.set_stroke(self.theme.color(p.axis_color), width=2, opacity=0.7))
        tail = min(abs(end - start) / (2 * n), 0.7)
        first = plan.along[0] - direction * tail
        track = Line(self._point(first, plan.axis), self._point(plan.along[-1] + direction * tail, plan.axis))
        track.set_stroke(self.theme.color(p.axis_color), width=4, opacity=0.55)
        track.add_tip(tip_length=0.2, tip_width=0.2)
        track.tip.set_fill(self.theme.color(p.axis_color), opacity=0.55).set_stroke(width=0)
        markers = [self._marker(i, now).move_to(self._point(a, plan.axis)) for i, a in enumerate(plan.along)]
        segments: list[VMobject] = []
        for i, a in enumerate(plan.along):  # from the previous marker's edge (or the axis start)
            begin = plan.along[i - 1] + direction * r if i else first
            kind = DashedLine if now is not None and i > now else Line
            segment = kind(self._point(begin, plan.axis), self._point(a - direction * r, plan.axis))
            segments.append(segment.set_stroke(self.theme.color(p.progress_color), width=5))
        # centred across the axis (one-sided layouts, sides of different heights)
        everything = VGroup(track, *segments, *markers, *cards, *stems)
        k = 1 if self.horizontal else 0
        everything.shift(((low + high) / 2 - everything.get_center()[k]) * (UP if self.horizontal else RIGHT))
        return _Drawing(track, segments, markers, cards, stems, plan.sides)

    def _marker(self, index: int, now: int | None) -> VGroup:
        """An event's marker, ``VGroup(disc, inner?, ring?)``: with icons in the timeline a
        disc outlined in ``marker_color`` holding the event's icon (or a dot), else a filled
        dot; hollow after ``now``; a ring in ``now_color`` around the now event's."""
        p = self.params
        color = self.theme.color(p.marker_color)
        background = self.theme.background
        future = now is not None and index > now
        event = p.events[index]
        r = self.radius
        disc = Circle(radius=r)
        parts: list[Mobject] = [disc]
        if r == self.icon_radius:
            disc.set_fill(background, opacity=1).set_stroke(color, width=3, opacity=0.6 if future else 1.0)
            if event.icon:
                parts.append(icon(event.icon, color=p.marker_color, height=2 * r * 0.6, theme=self.theme))
            else:
                parts.append(Dot(radius=r * 0.3, color=color))
        elif future:
            disc.set_fill(background, opacity=1).set_stroke(color, width=3)
        else:
            disc.set_fill(color, opacity=1).set_stroke(background, width=3)
        if now is not None and index == now:
            parts.append(Circle(radius=r + 0.1).set_fill(opacity=0).set_stroke(self.theme.color(p.now_color), width=2.5))
        for part in parts[1:]:
            part.move_to(disc)
        return VGroup(*parts)

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, heading: Mobject | None, d: "_Drawing") -> None:
        p = self.params
        n = len(p.events)
        self._drawing = d
        top = self.target("heading", heading, entrance=lambda: [FadeIn(heading, shift=DOWN * 0.15)]) if heading is not None else None
        self._axis = self.target("axis", d.track, entrance=lambda: [Create(d.track)])
        self._events = [
            self.target([f"event{i + 1}", f"event:{e.shown()}"], VGroup(d.markers[i], d.stems[i], d.cards[i]), entrance=lambda i=i: self._reveal([i]))
            for i, e in enumerate(p.events)
        ]

        def step(indices: list[int], first: bool) -> Any:
            def build() -> list[Animation]:  # entrance()/_reveal: nothing an action revealed comes twice
                anims = (self.entrance(top) if first and top is not None else []) + self._reveal(indices)
                return [LaggedStart(*anims, lag_ratio=0.3)] if len(anims) > 1 else anims

            return build

        order = [list(range(n))] if p.reveal == "all" else [[i] for i in range(n)]
        steps: list[Any] = [step(group, k == 0) for k, group in enumerate(order)]
        if p.highlight is not None:
            steps.append(self._focus(p.event_index(p.highlight)))
        self.reveal(steps, fraction=0.7, cap=1.4)
        self.finish()

    def _reveal(self, indices: list[int]) -> list[Animation]:
        """The axis (if not drawn yet), then for each event not on screen the progress line
        growing up to it, its marker, stem and text, one after another."""
        d = self._drawing
        chain: list[Animation] = [] if self.is_shown(self._axis) else [Create(d.track)]
        shown = {id(m) for m in self.get_mobject_family_members()}
        grown: set[int] = set()
        for i in sorted(indices):
            if self.is_shown(self._events[i]):
                continue
            for k in range(i + 1):
                if id(d.segments[k]) not in shown and k not in grown:
                    chain.append(Create(d.segments[k]))
                    grown.add(k)
            toward = (UP if self.horizontal else RIGHT) * d.sides[i] * 0.15
            chain.append(AnimationGroup(GrowFromCenter(d.markers[i]), Create(d.stems[i]), FadeIn(d.cards[i], shift=toward), lag_ratio=0.3))
        return [Succession(*chain)] if len(chain) > 1 else chain

    def _focus(self, chosen: int) -> Any:
        """The highlight step: the other events fade to :attr:`dimmed_opacity`; the chosen
        marker grows a little and turns ``highlight_color``, and so does the event's title."""
        p = self.params
        color = self.theme.color(p.highlight_color)

        def build() -> list[Animation]:
            d = self._drawing
            anims: list[Animation] = [
                dim_to(t, part, self.dimmed_opacity) for i, t in enumerate(self._events) if i != chosen for part in self.on_screen_parts(t)
            ]
            if not self.on_screen_parts(self._events[chosen]):  # transformed away by an action
                return anims
            marker = d.markers[chosen]
            goal = marker.copy().scale(1.2)
            disc = goal[0]
            if self.radius == self.icon_radius:  # outlined disc, icon or dot inside
                disc.set_stroke(color, opacity=1)
                goal[1].set_color(color)
            elif disc.get_fill_color().to_hex().lower() == self.theme.background.lower()[:7]:  # hollow
                disc.set_stroke(color)
            else:
                disc.set_fill(color)
            anims += [Transform(marker, goal), d.cards[chosen][1].animate.set_color(color)]
            return anims

        return build


class _Drawing(NamedTuple):
    """The drawn parts of a timeline, per event in order."""

    track: Line
    segments: list[VMobject]
    markers: list[VGroup]
    cards: list[VGroup]
    stems: list[Line]
    sides: list[int]
