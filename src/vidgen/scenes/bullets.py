"""``bullets``: an optional heading and a list of items revealed beat by beat."""

from collections.abc import Callable
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .actions import dim_to


class BulletItem(SceneParams):
    """A list item: its text, or ``{text, icon}`` (a plain string is read as ``{text: ...}``)."""

    also_accepts = (str,)

    text: str = Field(min_length=1)
    """The item's text."""
    icon: IconName | None = None
    """Icon in the marker column (replaces the bullet; beside the number), in marker_color."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"text": data} if isinstance(data, str) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A plain string is also an item (JSON Schema ``anyOf`` string | object)."""
        return {"anyOf": [{"type": "string", "minLength": 1}, handler(core_schema)]}


@scene("bullets")
class Bullets(NarratedScene):
    """``reveal: per_beat`` (default): item *i* appears at beat *i* (with the heading at beat 1);
    with more items than beats they are spread evenly, with fewer the remaining beats hold.
    ``reveal: all``: every item appears during the first beat.

    Action targets: ``heading``, ``item<N>`` (1-based) and ``item:<text>``.
    """

    outro = 0.5

    class Params(SceneParams):
        heading: str = ""
        """Optional heading, shown with the first item."""
        items: list[BulletItem] = Field(min_length=1)
        """The list items (at least one): text, or {text, icon}; item i appears at beat i."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: one item per beat; all: every item in beat 1."""
        numbered: bool = False
        """Number the items (1. 2. ...) instead of using marker."""
        dim_previous: bool = False
        """Fade earlier items when a new one appears."""
        marker: str = "•"
        """Bullet character."""
        size: ThemeSize = "body"
        """Item text size (shrunk automatically for long lists)."""
        heading_size: ThemeSize = "heading"
        """Heading text size."""
        color: ThemeColor = "text"
        """Item text color."""
        heading_color: ThemeColor = "text"
        """Heading color."""
        marker_color: ThemeColor = "primary"
        """Bullet/number/icon color."""

    #: In a vertical frame the heading grows by this factor, and a short list up to it, to use
    #: the taller frame.
    portrait_growth = 1.3
    #: Opacity of earlier items with ``dim_previous`` (0.45 keeps a dimmed ``primary`` marker
    #: above lint's 2:1 for de-emphasised text on light themes too).
    dimmed_opacity = 0.45
    #: Icon size relative to the item text size (an icon's box is 1.5 em at 1.0).
    icon_scale = 0.95
    target_patterns = ("heading", "item<N>", "item:<text>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``heading`` (if any), then ``item<N>`` and ``item:<text>`` per item."""
        names = ["heading"] if params.heading else []
        for i, item in enumerate(params.items, start=1):
            names += [f"item{i}", f"item:{item.text}"]
        return names

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
        width = body.width if self.is_portrait else min(body.width * 0.85, 11.5)
        rows = self._rows(width, body.height - 0.2)
        place(rows, body, fit="none", align="center")
        head = None
        if heading is not None:
            head = self.target("heading", heading, entrance=lambda: [FadeIn(heading, shift=DOWN * 0.15)])
        items = [
            self.target([f"item{i + 1}", f"item:{item.text}"], row, entrance=lambda row=row: [FadeIn(row, shift=RIGHT * 0.25)])
            for i, (item, row) in enumerate(zip(p.items, rows))
        ]
        dimmed: set[int] = set()

        def step(i: int) -> Callable[[], list[Animation]]:
            def build() -> list[Animation]:  # entrance() skips what an action revealed already
                anims = self.entrance(items[i])
                if i == 0 and head is not None:
                    anims = self.entrance(head) + anims
                if p.dim_previous:  # never below what a dim action already did; an icon's invisible box stays so
                    for j in range(i):
                        if j not in dimmed:
                            anims += [dim_to(items[j], part, self.dimmed_opacity) for part in self.on_screen_parts(items[j])]
                    dimmed.update(range(i))
                return anims

            return build

        steps = [step(i) for i in range(len(rows))]
        if p.reveal == "all":

            def all_at_once() -> list[Animation]:
                entrances = [AnimationGroup(*self.entrance(t)) for t in items if not self.is_shown(t)]
                anims: list[Animation] = [LaggedStart(*entrances, lag_ratio=0.25)] if entrances else []
                return (self.entrance(head) if head is not None else []) + anims

            steps = [all_at_once]
        self.reveal(steps, fraction=0.7, cap=1.0)
        self.finish()

    def _rows(self, width: float, max_height: float) -> VGroup:
        """Marker + wrapped text per item, shrunk (font size first) to fit ``max_height``; in a
        vertical frame a short list grows (up to ``portrait_growth``) and spreads out.

        Rows are spaced by baseline with a constant line pitch, so the gaps look even whatever
        letters the items contain.
        """
        p = self.params
        size = float(self.theme.size(p.size))
        largest = size * (self.portrait_growth if self.is_portrait else 1.0)
        spread = 0.8 if self.is_portrait else 0.55
        rows = VGroup()
        shrunk = False
        for _ in range(5):
            rows = self._layout(size, width, spread if len(p.items) <= 5 else 0.35)
            if rows.height > max_height and size > 14:
                size, shrunk = max(14.0, size * max(0.7, (max_height / rows.height) ** 0.5 * 0.97)), True
            elif not shrunk and size < largest * 0.99 and rows.height < max_height * 0.75:
                size = min(largest, size * (max_height * 0.75 / rows.height) ** 0.5)
            else:
                break
        return shrink_to_fit(rows, width, max_height)

    def _layout(self, size: float, width: float, spread: float) -> VGroup:
        """The rows at font ``size``: gaps between items are ``spread`` x the line pitch.

        Each row is ``VGroup(marker?, icon?, text)``. Without icons, markers form one column
        (numbers right-aligned against the text). With icons, the icons form a column of their
        own next to the text (centred on the first line's capitals), numbers stand left of it,
        and an item without an icon shows its bullet centred in the icon column.
        """
        p = self.params
        items = p.items
        probe = fit_text("x\nx", 100, size=size)
        pitch = probe[0].get_y() - probe[1].get_y()
        x_height = probe[0].height
        cap = self.text("H", size=size).height
        gap = pitch * spread
        icons = [icon(it.icon, size=size * self.icon_scale, color=p.marker_color, theme=self.theme) if it.icon else None for it in items]
        column = max((ic.width for ic in icons if ic is not None), default=0.0)
        markers: list[Mobject | None] = [
            self.text(f"{i + 1}." if p.numbered else p.marker, size=size, color=p.marker_color, weight=BOLD)
            if p.numbered or icons[i] is None
            else None
            for i in range(len(items))
        ]
        pad = size / 32 * 0.3
        numbers_w = max((m.width for m in markers if m is not None), default=0.0) if p.numbered or not column else 0.0
        lead = column + numbers_w + pad + (pad if column and numbers_w else 0.0)
        rows, y = VGroup(), 0.0
        for marker, item, ic in zip(markers, items, icons):
            body = fit_text(item.text, width - lead, size=size, color=p.color, align="left")
            body.shift(UP * (y - _baseline(body[0])))
            body.align_to(np.array([0.0, 0.0, 0.0]), LEFT)
            parts: list[Mobject] = []
            if marker is not None:
                if p.numbered:  # right-aligned against the icon column or the text
                    marker.move_to(np.array([-pad - (column + pad if column else 0.0), 0.0, 0.0]), aligned_edge=RIGHT)
                    marker.shift(UP * (y - _baseline(marker)))
                elif column:  # a bullet among icons: centred in their column
                    marker.move_to(np.array([-pad - column / 2, y + x_height / 2, 0.0]))
                else:
                    marker.next_to(body, LEFT, buff=pad)
                    marker.set_y(y + x_height / 2)
                parts.append(marker)
            if ic is not None:
                ic.move_to(np.array([-pad - column / 2, y + cap / 2, 0.0]))
                parts.append(ic)
            rows.add(VGroup(*parts, body))
            y = _baseline(body[-1]) - pitch - gap
        return rows

def _baseline(line: Mobject) -> float:
    """Approximate baseline of a line of text: the median bottom of its glyphs."""
    glyphs = [g for g in line.submobjects if g.has_points()] or [line]
    return float(np.median([g.get_bottom()[1] for g in glyphs]))
