"""Scene 8: takeaways, then the question and the links (was S8Conclusion)."""

from vidgen.api import *


@scene("kphi_conclusion")
class KphiConclusion(NarratedScene):
    """Beat 1: heading and the first takeaway. Beat 2: the other takeaways, spread over the
    beat. Beat 3: the question and the links; held 1.5 s, then a 1 s fade-out."""

    beat_count = 3

    class Params(SceneParams):
        heading: str = "Takeaways"
        items: list[str] = Field(min_length=2, max_length=5)
        question: str
        links: list[str] = []

    def construct(self) -> None:
        p = self.params

        def item(txt: str) -> VGroup:
            tick = T("✓", 34, "k3", weight=BOLD)
            return VGroup(tick, T(txt, 32)).arrange(RIGHT, buff=0.3)

        head = T(p.heading, 40, weight=BOLD).to_edge(UP, buff=0.7)
        items = VGroup(*[item(t) for t in p.items]).arrange(DOWN, buff=0.45, aligned_edge=LEFT).shift(UP * 0.2)

        with self.narrate(0):
            self.play(FadeIn(head), run_time=0.6)
            self.play(FadeIn(items[0], shift=RIGHT * 0.3), run_time=0.8)
        with self.narrate(1) as d:
            rest = items[1:]
            slot = d / (len(rest) + 1)   # the original: 3 items, d / 4 each
            for it in rest:
                self.play(FadeIn(it, shift=RIGHT * 0.3), run_time=min(1.0, slot))
                self.wait(max(0.0, slot - 1.0))

        with self.narrate(2) as d:
            self.play(*[FadeOut(m, shift=UP * 0.3) for m in self.mobjects], run_time=0.6)
            q = T(p.question, 46, "highlight", weight=BOLD).shift(UP * 1.3)
            links = VGroup(*[T(link, 28) for link in p.links]).arrange(DOWN, buff=0.3).shift(DOWN * 0.6)
            self.play(Write(q), run_time=1.2)
            self.wait(max(0.1, 0.35 * d - 1.8))
            if p.links:
                self.play(FadeIn(links, shift=UP * 0.2, lag_ratio=0.3), run_time=1.0)
        self.wait(1.5)
        self.clear_all(1.0)
