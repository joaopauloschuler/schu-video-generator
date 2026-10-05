"""``title``: opening card with optional kicker, highlighted words, subtitle and authors."""

from vidgen.api import *


@scene("title")
class Title(NarratedScene):
    """Beat 1 reveals the kicker, title and subtitle; beat 2 reveals the authors (if any).

    With a single beat everything appears in it; further beats hold the card.
    """

    outro = 0.5

    class Params(SceneParams):
        title: str
        subtitle: str = ""
        kicker: str = ""
        authors: list[str] = []
        highlight: str = ""
        color: ThemeColor = "text"
        highlight_color: ThemeColor = "highlight"
        subtitle_color: ThemeColor = "text"
        kicker_color: ThemeColor = "primary"
        authors_color: ThemeColor = "dim"

        @model_validator(mode="after")
        def _highlight_in_title(self) -> SceneParams:
            if self.highlight and normalize_text(self.highlight) not in normalize_text(self.title).replace("\n", " "):
                raise ValueError(f"highlight {self.highlight!r} is not part of the title")
            return self

    def construct(self) -> None:
        p = self.params
        width = self.safe_width * (1.0 if self.is_portrait else 0.86)
        tall = self.safe_height
        head = VGroup()
        if p.kicker:
            head.add(fit_text(p.kicker, width, size="caption", color=p.kicker_color, weight=BOLD))
        title = fit_text(
            p.title,
            width,
            tall * 0.42,
            size="title",
            color=p.color,
            weight=BOLD,
            highlights={p.highlight: p.highlight_color} if p.highlight else None,
        )
        head.add(title)
        if p.subtitle:
            head.add(fit_text(p.subtitle, width, tall * 0.2, size="subtitle", color=p.subtitle_color))
        head.arrange(DOWN, buff=0.32)

        card = VGroup(head)
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
            if p.subtitle:
                parts.append(FadeIn(head[-1], shift=UP * 0.15))
            return LaggedStart(*parts, lag_ratio=0.35)

        steps: list = [reveal_head]
        if p.authors:
            steps.append(FadeIn(authors, shift=UP * 0.15, lag_ratio=0.3))
        self.reveal(steps, fraction=0.75, cap=2.0)
        self.finish()
