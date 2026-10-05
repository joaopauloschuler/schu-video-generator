"""``text_card``: one centered line (or paragraph) of text for the whole scene."""

from vidgen.api import *


@scene("text_card")
class TextCard(NarratedScene):
    """Fades in ``text`` and keeps it on screen while the beats are narrated.

    Silent scenes (no beats, ``duration`` set) are held for their duration.
    """

    class Params(SceneParams):
        text: str
        size: str | float = "title"
        color: str = "text"

    def construct(self) -> None:
        card = self.text(self.params.text, size=self.params.size, color=self.params.color)
        max_width = self.frame_width * 0.9
        if card.width > max_width:
            card.scale_to_fit_width(max_width)
        if not self.beats:
            self.play(FadeIn(card), run_time=min(0.8, self.spec.duration or 0.8))
            return
        for i, (_, d) in enumerate(self.narrate_all()):
            if i == 0:
                self.play(FadeIn(card), run_time=min(0.8, d))
