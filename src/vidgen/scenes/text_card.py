"""``text_card``: one centered line (or paragraph) of text for the whole scene."""

from vidgen.api import *


@scene("text_card")
class TextCard(NarratedScene):
    """Fades in ``text`` (wrapped to fit the frame) and keeps it on screen while the beats are
    narrated; no fade-out at the end.

    Silent scenes (no beats, ``duration`` set) are held for their duration.
    """

    class Params(SceneParams):
        text: str
        """The text, wrapped to fit the frame."""
        size: ThemeSize = "title"
        """Text size."""
        color: ThemeColor = "text"
        """Text color."""

    def construct(self) -> None:
        p = self.params
        width = self.safe_width * (1.0 if self.is_portrait else 0.86)
        card = fit_text(p.text, width, self.safe_height * 0.8, size=p.size, color=p.color)
        if not self.beats:
            self.play(FadeIn(card), run_time=min(0.8, self.spec.duration or 0.8))
            return
        for i, (_, d) in enumerate(self.narrate_all()):
            if i == 0:
                self.play(FadeIn(card), run_time=min(0.8, d))
