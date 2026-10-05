"""``bullets``: an optional heading and a list of items revealed beat by beat."""

from collections.abc import Callable
from typing import Literal

import numpy as np

from vidgen.api import *


@scene("bullets")
class Bullets(NarratedScene):
    """``reveal: per_beat`` (default): item *i* appears at beat *i* (with the heading at beat 1);
    with more items than beats they are spread evenly, with fewer the remaining beats hold.
    ``reveal: all``: every item appears during the first beat.
    """

    outro = 0.5

    class Params(SceneParams):
        heading: str = ""
        """Optional heading, shown with the first item."""
        items: list[str] = Field(min_length=1)
        """The list items (at least one); item i appears at beat i."""
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
        """Bullet/number color."""

    #: In a vertical frame the heading grows by this factor, and a short list up to it, to use
    #: the taller frame.
    portrait_growth = 1.3
    #: Opacity of earlier items with ``dim_previous`` (0.45 keeps a dimmed ``primary`` marker
    #: above lint's 2:1 for de-emphasised text on light themes too).
    dimmed_opacity = 0.45

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

        def step(i: int) -> Callable[[], list[Animation]]:
            def build() -> list[Animation]:
                anims: list[Animation] = [FadeIn(rows[i], shift=RIGHT * 0.25)]
                if i == 0 and heading is not None:
                    anims.insert(0, FadeIn(heading, shift=DOWN * 0.15))
                if p.dim_previous:
                    anims += [rows[j].animate.set_opacity(self.dimmed_opacity) for j in range(i)]
                return anims

            return build

        steps = [step(i) for i in range(len(rows))]
        if p.reveal == "all":
            everything = [rows[i] for i in range(len(rows))]

            def all_at_once() -> list[Animation]:
                anims: list[Animation] = [LaggedStart(*[FadeIn(r, shift=RIGHT * 0.25) for r in everything], lag_ratio=0.25)]
                if heading is not None:
                    anims.insert(0, FadeIn(heading, shift=DOWN * 0.15))
                return anims

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
        """The rows at font ``size``: gaps between items are ``spread`` x the line pitch."""
        p = self.params
        probe = fit_text("x\nx", 100, size=size)
        pitch = probe[0].get_y() - probe[1].get_y()
        x_height = probe[0].height
        gap = pitch * spread
        markers = [self.text(f"{i + 1}." if p.numbered else p.marker, size=size, color=p.marker_color, weight=BOLD) for i in range(len(p.items))]
        marker_w = max(m.width for m in markers)
        pad = size / 32 * 0.3
        rows, y = VGroup(), 0.0
        for marker, item in zip(markers, p.items):
            body = fit_text(item, width - marker_w - pad, size=size, color=p.color, align="left")
            body.shift(UP * (y - _baseline(body[0])))
            body.align_to(np.array([0.0, 0.0, 0.0]), LEFT)
            # markers share one column (numbers right-aligned against the text)
            marker.next_to(body, LEFT, buff=pad)
            if p.numbered:
                marker.shift(UP * (y - _baseline(marker)))
            else:
                marker.set_y(y + x_height / 2)
            rows.add(VGroup(marker, body))
            y = _baseline(body[-1]) - pitch - gap
        return rows


def _baseline(line: Mobject) -> float:
    """Approximate baseline of a line of text: the median bottom of its glyphs."""
    glyphs = [g for g in line.submobjects if g.has_points()] or [line]
    return float(np.median([g.get_bottom()[1] for g in glyphs]))
