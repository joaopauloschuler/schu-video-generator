"""``comparison``: two or three columns side by side (A vs B, before / after), point by point."""

import logging
from collections.abc import Callable
from typing import Any, Literal

import numpy as np

from vidgen.api import *

log = logging.getLogger("vidgen.scenes")

Tone = Literal["positive", "negative", "neutral"]


class ComparisonPoint(SceneParams):
    """A point of a column: its text, or ``{text, icon}`` (a plain string is ``{text: ...}``)."""

    also_accepts = (str,)

    text: str = Field(min_length=1)
    """The point's text."""
    icon: IconName | None = None
    """Icon in place of the column's marker, in the column's tone colour."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"text": data} if isinstance(data, str) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A plain string is also a point (JSON Schema ``anyOf`` string | object)."""
        return {"anyOf": [{"type": "string", "minLength": 1}, handler(core_schema)]}


class ComparisonColumn(SceneParams):
    """One column: ``{heading, icon?, tone?, points}``."""

    heading: str = Field(min_length=1)
    """The column's heading ('Before', 'Option A')."""
    icon: IconName | None = None
    """Optional icon left of the heading, in the tone colour."""
    tone: Tone = "neutral"
    """positive (check marks, positive_color), negative (crosses, negative_color) or neutral (dots, neutral_color)."""
    points: list[ComparisonPoint] = Field(default_factory=list, max_length=8)
    """The column's points (up to 8): text, or {text, icon}."""


@scene("comparison")
class Comparison(NarratedScene):
    """``reveal: columns`` (default): column *i* (card, heading and its points) appears at beat
    *i*; ``rows``: beat 1 shows the column headings, then each beat adds the next point of every
    column; ``all``: everything in beat 1. A ``verdict`` comes in a last step. The heading
    comes with the first step.

    Action targets: ``heading``, ``col<N>``, ``col:<heading>``, ``col<N>.item<M>`` (1-based)
    and ``verdict``.
    """

    outro = 0.5
    target_patterns = ("heading", "col<N>", "col:<heading>", "col<N>.item<M>", "verdict")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``heading`` (if any), per column ``col<N>``, ``col:<heading>`` and ``col<N>.item<M>``
        per point, then ``verdict`` (if any)."""
        names = ["heading"] if params.heading else []
        for i, column in enumerate(params.columns, start=1):
            names += [f"col{i}", f"col:{column.heading}"] + [f"col{i}.item{m}" for m in range(1, len(column.points) + 1)]
        return names + (["verdict"] if params.verdict else [])

    class Params(SceneParams):
        columns: list[ComparisonColumn] = Field(min_length=2, max_length=3)
        """Two or three columns, {heading, icon?, tone?, points}, left to right (top to bottom in 9:16)."""
        heading: str = ""
        """Optional heading above the columns."""
        verdict: str = ""
        """Optional conclusion under the columns, shown in a last step."""
        reveal: Literal["columns", "rows", "all"] = "columns"
        """columns: one column per beat; rows: headings, then one point of every column per beat; all: everything in beat 1."""
        markers: bool = True
        """Mark points by tone: check (positive), cross (negative), dot (neutral)."""
        cards: bool = True
        """Draw each column on a card in the theme's surface colour."""
        vs: str = ""
        """Text in a badge between the columns, e.g. 'vs'; empty for none."""
        positive_color: ThemeColor = "tertiary"
        """Tone colour of positive columns (heading, icon, markers)."""
        negative_color: ThemeColor = "accent"
        """Tone colour of negative columns."""
        neutral_color: ThemeColor = "primary"
        """Tone colour of neutral columns (markers and icon; the heading stays heading_color)."""
        color: ThemeColor = "text"
        """Point text colour."""
        heading_color: ThemeColor = "text"
        """Colour of the scene heading and of neutral column headings."""
        verdict_color: ThemeColor = "highlight"
        """Verdict colour."""
        size: ThemeSize = "body"
        """Point text size (reduced, not below the readable minimum, when space is short)."""
        column_size: ThemeSize = "subtitle"
        """Column heading size (reduced with the points)."""
        heading_size: ThemeSize = "heading"
        """Scene heading size."""
        verdict_size: ThemeSize = "body"
        """Verdict size."""

    #: In a vertical frame the scene heading, the columns and the verdict grow by this factor
    #: when they fit (as in ``bullets``): the stacked cards would otherwise leave the tall frame
    #: half empty.
    portrait_growth = 1.3
    #: Space between columns (Manim units); with a ``vs`` badge it is wider.
    column_gap = 0.45
    vs_gap = 1.0
    #: Padding inside a card (Manim units).
    pad_x = 0.35
    pad_y = 0.3
    #: Marker (icon) size relative to the point text size.
    marker_scale = 0.9

    # ----- colours ---------------------------------------------------------------------------

    def tone_color(self, column: ComparisonColumn) -> str:
        """The column's tone colour token."""
        p = self.params
        return {"positive": p.positive_color, "negative": p.negative_color, "neutral": p.neutral_color}[column.tone]

    # ----- layout ----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        body = self.safe_area
        heading = None
        if p.heading:
            header = self.region("header")
            grow = self.portrait_growth if self.is_portrait else 1.0
            size = float(self.theme.size(p.heading_size)) * grow
            heading = fit_text(p.heading, header.width, header.height, size=size, color=p.heading_color, weight=BOLD, role="heading")
            place(heading, header, fit="none", align="center")
            body = body.below(heading, gap=0.5)
        verdict = None
        if p.verdict:
            width = body.width if self.is_portrait else min(body.width * 0.85, 11.5)
            size = float(self.theme.size(p.verdict_size)) * (self.portrait_growth if self.is_portrait else 1.0)
            verdict = fit_text(p.verdict, width, body.height * 0.2, size=size, color=p.verdict_color, weight=BOLD)
            place(verdict, body, fit="none", align="bottom")
            body = body.above(verdict, gap=0.45)
        gap = self.vs_gap if p.vs else self.column_gap
        slots = body.split(len(p.columns), gap)
        columns = self._columns(slots)
        self._arrange(columns, body, gap)
        badges = self._badges(columns) if p.vs else []
        self._steps(columns, heading, verdict, badges)

    def _columns(self, slots: list[Region]) -> list[dict[str, Any]]:
        """The content of every column at one common text size: the largest up to ``size`` (x
        :attr:`portrait_growth` in a vertical frame; not below the readable minimum) at which
        each fits its slot; scaled down as a whole (with a
        warning) when even that is too tall."""
        p = self.params
        wanted = float(self.theme.size(p.size))
        floor = min(wanted, readable_size())
        inner_w = min(s.width for s in slots) - 2 * self.pad_x
        room = min(s.height for s in slots) - 2 * self.pad_y
        size = wanted * (self.portrait_growth if self.is_portrait else 1.0)
        while True:
            built = self._contents(inner_w, size, wanted)
            tallest = max(-c["content"].get_bottom()[1] for c in built)
            if tallest <= room or size <= floor:
                break
            size = max(floor, size * min(0.95, (room / tallest) ** 0.5))
        if tallest > room:
            log.warning("scene '%s': the comparison's %d columns do not fit this frame at the readable size; shorten or remove points", self.spec.id, len(p.columns))
            for c in built:  # about the top-left corner, which _arrange puts in the card's
                c["content"].scale(room / tallest, about_point=ORIGIN)
            tallest = room
        for c in built:
            c["size"] = (inner_w + 2 * self.pad_x, tallest + 2 * self.pad_y)
        return built

    def _contents(self, width: float, size: float, wanted: float) -> list[dict[str, Any]]:
        """``{content, head, rule, points}`` per column at point size ``size`` (headings shrink
        with it), each with its top-left corner at the origin. Side by side, the rules line up,
        and with ``reveal: rows`` the *m*-th points of every column too (a row is revealed
        across the columns)."""
        p = self.params
        shared = orientation() != "portrait"
        rows_shared = shared and p.reveal == "rows"
        heads = [self._head(column, width, size, wanted) for column in p.columns]
        rows = [self._points(column, width, size) for column in p.columns]
        cap = self.text("H", size=size).height
        probe = fit_text("x\nx", 100, size=size)
        pitch = probe[0].get_y() - probe[1].get_y()
        lowest = min(h.get_bottom()[1] for h in heads)
        out = []
        for i, column in enumerate(p.columns):
            rule_y = (lowest if shared else heads[i].get_bottom()[1]) - 0.2
            rule = Line(np.array([0.0, rule_y, 0.0]), np.array([width, rule_y, 0.0]), stroke_width=3)
            rule.set_stroke(self.theme.color(self.tone_color(column)), opacity=0.7)
            y = rule_y - 0.28 - cap
            for m, row in enumerate(rows[i]):
                row.shift(UP * y)
                lines = max(len(x[m][-1]) for x in rows if m < len(x)) if rows_shared else len(row[-1])
                y -= (lines - 1) * pitch + pitch * 1.45
            out.append({"content": VGroup(heads[i], rule, *rows[i]), "head": heads[i], "rule": rule, "points": rows[i]})
        return out

    def _head(self, column: ComparisonColumn, width: float, size: float, wanted: float) -> VGroup:
        """Icon and heading of a column, top-left at the origin; the heading in the tone colour
        (``heading_color`` for neutral columns), at ``column_size`` scaled like the points."""
        p = self.params
        tone = self.tone_color(column)
        head_size = float(self.theme.size(p.column_size)) * size / wanted
        parts: list[Mobject] = []
        lead = 0.0
        if column.icon:
            mark = icon(column.icon, size=head_size, color=tone, theme=self.theme)
            lead = mark.width + head_size / 32 * 0.2
            parts.append(mark)
        color = p.heading_color if column.tone == "neutral" else tone
        title = fit_text(column.heading, width - lead, size=head_size, color=color, weight=BOLD, align="left", role="heading")
        title.move_to(np.array([lead, 0.0, 0.0]), aligned_edge=UL)
        if parts:
            parts[0].move_to(np.array([parts[0].width / 2, _cap_middle(title[0]), 0.0]))
        head = VGroup(*parts, title)
        return head.shift(DOWN * head.get_top()[1])

    def _points(self, column: ComparisonColumn, width: float, size: float) -> list[VGroup]:
        """One ``VGroup(marker?, text)`` per point with the text's first baseline at y = 0;
        markers centred in a lane left of the text, on the capitals of the first line."""
        p = self.params
        tone = self.tone_color(column)
        cap = self.text("H", size=size).height
        markers: list[Mobject | None] = []
        for point in column.points:
            name = point.icon or ({"positive": "check", "negative": "x"}.get(column.tone) if p.markers else None)
            if name:
                markers.append(icon(name, size=size * self.marker_scale, color=tone, theme=self.theme))
            elif p.markers:
                markers.append(Dot(radius=cap * 0.17, color=self.theme.color(tone)))
            else:
                markers.append(None)
        lane = max((m.width for m in markers if m is not None), default=0.0)
        lead = lane + (size / 32 * 0.3 if lane else 0.0)
        rows: list[VGroup] = []
        for point, marker in zip(column.points, markers):
            text = fit_text(point.text, width - lead, size=size, color=p.color, align="left")
            text.shift(np.array([lead - text.get_left()[0], -_baseline(text[0]), 0.0]))
            parts: list[Mobject] = []
            if marker is not None:
                marker.move_to(np.array([lane / 2, cap / 2, 0.0]))
                parts.append(marker)
            rows.append(VGroup(*parts, text))
        return rows

    def _arrange(self, columns: list[dict[str, Any]], body: Region, gap: float) -> None:
        """Cards of one size side by side (stacked in a vertical frame), centred in ``body``;
        each column's content at the top left of its card."""
        p = self.params
        w, h = columns[0]["size"]
        portrait = orientation() == "portrait"
        n = len(columns)
        total = n * (h if portrait else w) + (n - 1) * gap
        for i, c in enumerate(columns):
            offset = -total / 2 + i * ((h if portrait else w) + gap) + (h if portrait else w) / 2
            center = body.center + (np.array([0.0, -offset, 0.0]) if portrait else np.array([offset, 0.0, 0.0]))
            card = RoundedRectangle(width=w, height=h, corner_radius=0.18)
            column = p.columns[i]
            if p.cards:
                card.set_fill(self.theme.color("surface"), opacity=1).set_stroke(self.theme.color(self.tone_color(column)), width=2, opacity=0.45)
            else:
                card.set_fill(opacity=0).set_stroke(opacity=0)
            card.move_to(center).set_z_index(-1)
            c["content"].shift(card.get_corner(UL) + np.array([self.pad_x, -self.pad_y, 0.0]))  # its top left is the origin
            c["card"] = card

    def _badges(self, columns: list[dict[str, Any]]) -> list[VGroup]:
        """A ``vs`` badge (text in a disc) between each pair of neighbouring cards."""
        p = self.params
        badges = []
        for a, b in zip(columns, columns[1:]):
            label = self.text(p.vs, size="caption", color="dim", weight=BOLD)
            disc = Circle(radius=max(label.width, label.height) / 2 + 0.16)
            disc.set_fill(self.theme.background, opacity=1).set_stroke(self.theme.color("dim"), width=2, opacity=0.6)
            center = (a["card"].get_center() + b["card"].get_center()) / 2
            badges.append(VGroup(disc.move_to(center), label.move_to(center)))
        return badges

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, columns: list[dict[str, Any]], heading: Mobject | None, verdict: Mobject | None, badges: list[VGroup]) -> None:
        p = self.params
        top = self.target("heading", heading, entrance=lambda: [FadeIn(heading, shift=DOWN * 0.15)]) if heading is not None else None
        frames: list[VGroup] = []
        items: list[list[Target]] = []
        for i, (column, c) in enumerate(zip(p.columns, columns), start=1):
            frame = VGroup(c["card"], c["head"], c["rule"])
            frames.append(frame)
            # a highlight box (0.12 outside the outline) lands on the card's edge
            outline = Rectangle(width=max(c["card"].width - 0.24, 0.1), height=max(c["card"].height - 0.24, 0.1)).move_to(c["card"])
            col_items = [
                self.target(f"col{i}.item{m}", row, entrance=lambda row=row, frame=frame: self._frame_entrance(frame) + [FadeIn(row, shift=RIGHT * 0.2)])
                for m, row in enumerate(c["points"], start=1)
            ]
            items.append(col_items)
            mob = VGroup(c["head"], c["rule"], *c["points"])
            self.target([f"col{i}", f"col:{column.heading}"], mob, outline=outline, entrance=lambda frame=frame, col_items=col_items: self._column_entrance(frame, col_items))
        last = self.target("verdict", verdict, entrance=lambda: [FadeIn(verdict, shift=UP * 0.15)]) if verdict is not None else None

        def first(anims: list[Animation]) -> list[Animation]:
            return (self.entrance(top) if top is not None else []) + anims

        def lagged(anims: list[Animation], lag: float = 0.2) -> list[Animation]:
            return [LaggedStart(*anims, lag_ratio=lag)] if anims else []

        def badges_in() -> list[Animation]:
            shown = {id(m) for m in self.mobjects}
            return [FadeIn(b, scale=0.8) for b in badges if id(b) not in shown]

        steps: list[Callable[[], list[Animation]]] = []
        if p.reveal == "columns":
            for k in range(len(p.columns)):
                def step(k: int = k) -> list[Animation]:
                    anims = self._column_entrance(frames[k], items[k])
                    if k == 1:
                        anims = badges_in() + anims
                    return first(anims) if k == 0 else anims

                steps.append(step)
        elif p.reveal == "rows":
            steps.append(lambda: first(lagged([AnimationGroup(*self._frame_entrance(f)) for f in frames], 0.15) + badges_in()))
            for m in range(max(len(c.points) for c in p.columns)):
                def row_step(m: int = m) -> list[Animation]:
                    return lagged([AnimationGroup(*self.entrance(col_items[m])) for col_items in items if m < len(col_items) and not self.is_shown(col_items[m])], 0.25)

                steps.append(row_step)
        else:
            def everything() -> list[Animation]:
                built = [self._column_entrance(f, i) for f, i in zip(frames, items)]
                return first(lagged([AnimationGroup(*anims) for anims in built if anims], 0.3) + badges_in())

            steps.append(everything)
        if last is not None:
            steps.append(lambda: self.entrance(last))
        self.reveal(steps, fraction=0.7, cap=1.4)
        self.finish()

    def _frame_entrance(self, frame: VGroup) -> list[Animation]:
        """Card, heading and rule of a column, unless on screen already."""
        card, head, rule = frame
        if self.on_screen_parts(head):
            return []
        anims: list[Animation] = [FadeIn(card, scale=0.97)] if card.get_fill_opacity() > 0 else [FadeIn(card)]
        return [AnimationGroup(*anims, FadeIn(head, shift=DOWN * 0.12), Create(rule), lag_ratio=0.25)]

    def _column_entrance(self, frame: VGroup, items: list[Target]) -> list[Animation]:
        """A column: its frame, then its points one after another (those not on screen yet)."""
        points: list[Animation] = [FadeIn(t.mobject, shift=RIGHT * 0.2) for t in items if not self.is_shown(t)]
        anims = self._frame_entrance(frame)
        if points:
            flow = LaggedStart(*points, lag_ratio=0.3)
            anims = [LaggedStart(*anims, flow, lag_ratio=0.45)] if anims else [flow]
        return anims


def _baseline(line: Mobject) -> float:
    """Approximate baseline of a line of text: the median bottom of its glyphs."""
    glyphs = [g for g in line.submobjects if g.has_points()] or [line]
    return float(np.median([g.get_bottom()[1] for g in glyphs]))


def _cap_middle(line: Mobject) -> float:
    """Middle of a line's capital letters: halfway between its baseline and its top."""
    return (_baseline(line) + float(line.get_top()[1])) / 2
