"""``quote``: a pull quote with a large typographic quote mark and an attribution."""

from typing import Any

from vidgen.api import *

QUOTE_CHARS = "\"'“”„«»‘’"


@scene("quote")
class Quote(NarratedScene):
    """Beat 1 reveals the quote, beat 2 the attribution (both in beat 1 if there is only one).

    Quote characters around ``text`` are removed (the scene draws its own).

    Action targets: ``mark`` (the quote mark), ``quote``, ``author``, ``source`` (those present).
    """

    outro = 0.5
    target_patterns = ("mark", "quote", "author", "source")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``mark``, ``quote``, then ``author`` and ``source`` when given."""
        return ["mark", "quote"] + (["author"] if params.author else []) + (["source"] if params.source else [])
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
        author = source = None
        if p.author:
            author = fit_text(f"— {p.author}", width, size=float(self.theme.size("body")) * grow, color=p.author_color, weight=BOLD)
            attribution.add(author)
        if p.source:
            source = fit_text(p.source, width, size="caption", color=p.source_color)
            attribution.add(source)
        attribution.arrange(DOWN, buff=0.14)

        card = VGroup(mark, body)
        mark.next_to(body, UP, buff=0.3)
        if len(attribution):
            attribution.next_to(body, DOWN, buff=0.6)
            card.add(attribution)
        place(card, area, max_scale=1.0)

        first = [
            self.target("mark", mark, entrance=lambda: [FadeIn(mark, scale=0.85)]),
            self.target("quote", body, entrance=lambda: [FadeIn(body, shift=UP * 0.15)]),
        ]
        second = [
            self.target(name, m, entrance=lambda m=m: [FadeIn(m, shift=UP * 0.12)])
            for name, m in (("author", author), ("source", source))
            if m is not None
        ]
        steps: list = [lambda: [a for t in first for a in self.entrance(t)]]  # entrance(): never twice
        if second:
            steps.append(lambda: [a for t in second for a in self.entrance(t)])
        self.reveal(steps, fraction=0.6, cap=1.2)
        self.finish()
