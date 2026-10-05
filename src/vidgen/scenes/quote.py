"""``quote``: a pull quote with a large typographic quote mark and an attribution."""

from vidgen.api import *

QUOTE_CHARS = "\"'“”„«»‘’"


@scene("quote")
class Quote(NarratedScene):
    """Beat 1 reveals the quote, beat 2 the attribution (both in beat 1 if there is only one).

    Quote characters around ``text`` are removed (the scene draws its own).
    """

    outro = 0.5

    class Params(SceneParams):
        text: str = Field(min_length=1)
        author: str = ""
        source: str = ""
        size: ThemeSize = "subtitle"
        color: ThemeColor = "text"
        mark_color: ThemeColor = "primary"
        mark_font: str = "Georgia,DejaVu Serif,serif"
        author_color: ThemeColor = "text"
        source_color: ThemeColor = "dim"

    def construct(self) -> None:
        p = self.params
        width = self.safe_width * (1.0 if self.is_portrait else 0.78)
        body_text = p.text.strip().strip(QUOTE_CHARS).strip() or p.text
        mark = self.text("“", size=float(self.theme.size(p.size)) * 4, color=p.mark_color, weight=BOLD, font=p.mark_font)
        body = fit_text(body_text, width, self.safe_height * 0.55, size=p.size, color=p.color)
        attribution = VGroup()
        if p.author:
            attribution.add(fit_text(f"— {p.author}", width, size="body", color=p.author_color, weight=BOLD))
        if p.source:
            attribution.add(fit_text(p.source, width, size="caption", color=p.source_color))
        attribution.arrange(DOWN, buff=0.14)

        card = VGroup(mark, body)
        mark.next_to(body, UP, buff=0.3)
        if len(attribution):
            attribution.next_to(body, DOWN, buff=0.6)
            card.add(attribution)
        shrink_to_fit(card, self.safe_width, self.safe_height).move_to(ORIGIN)

        steps: list = [[FadeIn(mark, scale=0.85), FadeIn(body, shift=UP * 0.15)]]
        if len(attribution):
            steps.append(FadeIn(attribution, shift=UP * 0.12))
        self.reveal(steps, fraction=0.6, cap=1.2)
        self.finish()
