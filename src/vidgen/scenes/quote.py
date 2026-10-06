"""``quote``: a pull quote with a large typographic quote mark and an attribution."""

from vidgen.api import *

QUOTE_CHARS = "\"'“”„«»‘’"


@scene("quote")
class Quote(NarratedScene):
    """Beat 1 reveals the quote, beat 2 the attribution (both in beat 1 if there is only one).

    Quote characters around ``text`` are removed (the scene draws its own).
    """

    outro = 0.5
    #: In a vertical frame the quote, its mark and the author grow by this factor.
    portrait_growth = 1.25

    class Params(SceneParams):
        text: str = Field(min_length=1)
        """The quote."""
        author: str = ""
        """Shown as '- author'."""
        source: str = ""
        """Shown smaller under the author."""
        size: ThemeSize = "subtitle"
        """Quote text size (shrunk if long)."""
        color: ThemeColor = "text"
        """Quote text color."""
        mark_color: ThemeColor = "primary"
        """Color of the large quote mark."""
        mark_font: str | None = None
        """Font of the quote mark; default: the theme's font for the `quote_mark` role (font_serif, Source Serif 4)."""
        author_color: ThemeColor = "text"
        """Author color."""
        source_color: ThemeColor = "dim"
        """Source color."""

    def construct(self) -> None:
        p = self.params
        area = self.safe_area
        grow = self.portrait_growth if self.is_portrait else 1.0
        width = area.width * (1.0 if self.is_portrait else 0.78)
        size = float(self.theme.size(p.size)) * grow
        body_text = p.text.strip().strip(QUOTE_CHARS).strip() or p.text
        mark = self.text("“", size=size * 4, color=p.mark_color, weight=BOLD, font=p.mark_font or self.theme.font_for("quote_mark"))
        body = fit_text(body_text, width, area.height * 0.55, size=size, color=p.color, role="quote")
        attribution = VGroup()
        if p.author:
            attribution.add(fit_text(f"— {p.author}", width, size=float(self.theme.size("body")) * grow, color=p.author_color, weight=BOLD))
        if p.source:
            attribution.add(fit_text(p.source, width, size="caption", color=p.source_color))
        attribution.arrange(DOWN, buff=0.14)

        card = VGroup(mark, body)
        mark.next_to(body, UP, buff=0.3)
        if len(attribution):
            attribution.next_to(body, DOWN, buff=0.6)
            card.add(attribution)
        place(card, area, max_scale=1.0)

        steps: list = [[FadeIn(mark, scale=0.85), FadeIn(body, shift=UP * 0.15)]]
        if len(attribution):
            steps.append(FadeIn(attribution, shift=UP * 0.12))
        self.reveal(steps, fraction=0.6, cap=1.2)
        self.finish()
