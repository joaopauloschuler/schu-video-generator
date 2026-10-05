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
        items: list[str] = Field(min_length=1)
        reveal: Literal["per_beat", "all"] = "per_beat"
        numbered: bool = False
        dim_previous: bool = False
        marker: str = "•"
        size: ThemeSize = "body"
        heading_size: ThemeSize = "heading"
        color: ThemeColor = "text"
        heading_color: ThemeColor = "text"
        marker_color: ThemeColor = "primary"

    def construct(self) -> None:
        p = self.params
        top = self.frame_height / 2 - self.margin_y
        bottom = -self.frame_height / 2 + self.margin_y
        heading = None
        if p.heading:
            heading = fit_text(
                p.heading, self.safe_width, self.safe_height * 0.2, size=p.heading_size, color=p.heading_color, weight=BOLD
            )
            heading.move_to([0, top - 0.25 - heading.height / 2, 0])
            top = heading.get_bottom()[1] - (0.6 if self.is_portrait else 0.5)

        width = self.safe_width if self.is_portrait else min(self.safe_width * 0.85, 11.5)
        rows = self._rows(width, top - bottom - 0.2)
        rows.move_to([0, (top + bottom) / 2 + (0.15 if heading is None else 0.1), 0])

        def step(i: int) -> Callable[[], list[Animation]]:
            def build() -> list[Animation]:
                anims: list[Animation] = [FadeIn(rows[i], shift=RIGHT * 0.25)]
                if i == 0 and heading is not None:
                    anims.insert(0, FadeIn(heading, shift=DOWN * 0.15))
                if p.dim_previous:
                    anims += [rows[j].animate.set_opacity(0.4) for j in range(i)]
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
        """Marker + wrapped text per item, shrunk (font size first) to fit ``max_height``.

        Rows are spaced by baseline with a constant line pitch, so the gaps look even whatever
        letters the items contain.
        """
        p = self.params
        size = float(self.theme.size(p.size))
        rows = VGroup()
        for _ in range(4):
            probe = fit_text("x\nx", 100, size=size)
            pitch = probe[0].get_y() - probe[1].get_y()
            x_height = probe[0].height
            gap = pitch * (0.55 if len(p.items) <= 5 else 0.35)
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
            if rows.height <= max_height or size <= 14:
                break
            size = max(14.0, size * max(0.7, (max_height / rows.height) ** 0.5 * 0.97))
        return shrink_to_fit(rows, width, max_height)


def _baseline(line: Mobject) -> float:
    """Approximate baseline of a line of text: the median bottom of its glyphs."""
    glyphs = [g for g in line.submobjects if g.has_points()] or [line]
    return float(np.median([g.get_bottom()[1] for g in glyphs]))
