"""``title``: opening card with optional icon, kicker, highlighted words, subtitle and authors."""

from typing import Literal

from vidgen.api import *


@scene("title")
class Title(NarratedScene):
    """Beat 1 reveals the icon, kicker, title and subtitle; beat 2 reveals the authors (if any).

    With a single beat everything appears in it; further beats hold the card.
    """

    outro = 0.5

    class Params(SceneParams):
        title: str
        """Main title; wrapped to fit, may contain line breaks."""
        subtitle: str = ""
        """Line under the title."""
        kicker: str = ""
        """Small label above the title."""
        authors: list[str] = []
        """One line each, revealed in beat 2."""
        highlight: str = ""
        """Part of the title drawn in highlight_color."""
        color: ThemeColor = "text"
        """Title color."""
        highlight_color: ThemeColor = "highlight"
        """Color of the highlighted part of the title."""
        subtitle_color: ThemeColor = "text"
        """Subtitle color."""
        kicker_color: ThemeColor = "primary"
        """Kicker color."""
        authors_color: ThemeColor = "dim"
        """Authors color."""
        icon: IconName | None = None
        """Optional icon above (or left of) the title."""
        icon_color: ThemeColor = "primary"
        """Icon color."""
        icon_position: Literal["above", "left"] = "above"
        """above the kicker/title, or left of the title block (above in a vertical frame)."""

        @model_validator(mode="after")
        def _highlight_in_title(self) -> SceneParams:
            if self.highlight and normalize_text(self.highlight) not in normalize_text(self.title).replace("\n", " "):
                raise ValueError(f"highlight {self.highlight!r} is not part of the title")
            return self

    #: Height of the title's icon in Manim units (the frame's shorter side is 8).
    icon_height = 1.25
    #: Gap between the icon and the title block when ``icon_position: left``.
    icon_gap = 0.5

    def construct(self) -> None:
        p = self.params
        beside = p.icon is not None and p.icon_position == "left" and not self.is_portrait
        mark = icon(p.icon, color=p.icon_color, height=self.icon_height, theme=self.theme) if p.icon else None
        width = self.safe_width * (1.0 if self.is_portrait else 0.86)
        if beside and mark is not None:
            width -= mark.width + self.icon_gap
        tall = self.safe_height
        head = VGroup()
        if p.kicker:
            head.add(fit_text(p.kicker, width, size="caption", color=p.kicker_color, weight=BOLD))
        title = fit_text(
            p.title,
            width,
            tall * (0.36 if mark is not None and not beside else 0.42),
            size="title",
            color=p.color,
            weight=BOLD,
            font=self.theme.font_for("heading"),
            highlights={p.highlight: p.highlight_color} if p.highlight else None,
        )
        head.add(title)
        if p.subtitle:
            head.add(fit_text(p.subtitle, width, tall * 0.2, size="subtitle", color=p.subtitle_color))
        head.arrange(DOWN, buff=0.32)
        top = VGroup(head)
        if mark is not None:
            if beside:
                mark.scale(min(1.0, max(head.height, 0.5) / mark.height * 1.1))
                top = VGroup(mark, head).arrange(RIGHT, buff=self.icon_gap)
            else:
                top = VGroup(mark, head).arrange(DOWN, buff=0.4)

        card = VGroup(top)
        authors = VGroup(*[fit_text(a, width, size="caption", color=p.authors_color) for a in p.authors])
        if p.authors:
            authors.arrange(DOWN, buff=0.16)
            card.add(authors)
        card.arrange(DOWN, buff=0.75)
        shrink_to_fit(card, self.safe_width, self.safe_height).move_to(ORIGIN)

        def reveal_head() -> Animation:
            parts = [Write(title)]
            if p.kicker:
                parts.insert(0, FadeIn(head[0], shift=DOWN * 0.15))
            if mark is not None:
                parts.insert(0, FadeIn(mark, scale=0.6))
            if p.subtitle:
                parts.append(FadeIn(head[-1], shift=UP * 0.15))
            return LaggedStart(*parts, lag_ratio=0.35)

        steps: list = [reveal_head]
        if p.authors:
            steps.append(FadeIn(authors, shift=UP * 0.15, lag_ratio=0.3))
        self.reveal(steps, fraction=0.75, cap=2.0)
        self.finish()
