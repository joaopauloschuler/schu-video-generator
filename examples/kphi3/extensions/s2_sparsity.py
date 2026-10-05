"""Scene 2: dense artificial layer vs sparse cortex, synapse counts, the question (was S2Sparsity)."""

import random

from vidgen.api import *


@scene("kphi_sparsity")
class KphiSparsity(NarratedScene):
    """Beat 1: dense layer. Beat 2: sparse cortex with signal flashes. Beat 3: possible vs
    actual synapses (Pango markup, e.g. ``10<sup>22</sup>``). Beat 4: the question."""

    beat_count = 4

    class Params(SceneParams):
        possible: str = "10<sup>22</sup>"
        actual: str = "10<sup>15</sup>"
        ratio: str = "≈ 1 in 10,000,000"
        question: str = "Over-parameterized?"

    def construct(self) -> None:
        p = self.params
        rng = random.Random(3)
        k3 = resolve_color("k3")
        # artificial, dense
        ins = column(6, -5.4, 0.62, y0=-0.2)
        outs = column(6, -2.2, 0.62, y0=-0.2)
        dense = edges(ins, outs, dense_pairs(6, 6), "base", 1.6, 0.6)
        a_title = T("Artificial layer", 32, weight=BOLD).move_to([-3.8, 2.6, 0])
        a_pct = T("100% connected", 28, "base").move_to([-3.8, -2.6, 0])

        with self.narrate(0) as d:
            self.play(FadeIn(a_title), FadeIn(ins), FadeIn(outs), run_time=0.8)
            self.play(Create(dense, lag_ratio=0.02), run_time=0.45 * d)
            self.play(FadeIn(a_pct, shift=UP * 0.2), run_time=0.6)

        # biological, sparse
        pts: list[np.ndarray] = []
        while len(pts) < 16:
            q = np.array([rng.uniform(1.4, 6.2), rng.uniform(-1.9, 1.7), 0])
            if all(np.linalg.norm(q - r) > 0.75 for r in pts):
                pts.append(q)
        neurons = VGroup(*[Dot(q, radius=0.11, color=k3) for q in pts]).set_z_index(3)
        bio_pairs = [(i, j) for i in range(16) for j in range(i + 1, 16)
                     if np.linalg.norm(pts[i] - pts[j]) < 2.2 and rng.random() < 0.28]
        bio = VGroup(*[Line(pts[i], pts[j], stroke_width=2, color=k3, stroke_opacity=0.7) for i, j in bio_pairs])
        b_title = T("Cortex", 32, weight=BOLD).move_to([3.8, 2.6, 0])
        b_pct = T("0–15% connected", 28, "k3").move_to([3.8, -2.6, 0])
        b_note = T("neurons 500 µm apart", 20, "dim").next_to(b_pct, DOWN, buff=0.12)

        with self.narrate(1) as d:
            self.play(FadeIn(b_title), FadeIn(neurons, lag_ratio=0.05), run_time=1.0)
            self.play(Create(bio, lag_ratio=0.1), run_time=0.3 * d)
            self.play(FadeIn(b_pct, shift=UP * 0.2), FadeIn(b_note), run_time=0.6)
            gold = resolve_color("highlight")
            flashes = [ShowPassingFlash(e.copy().set_color(gold).set_stroke(width=5, opacity=1), time_width=0.6)
                       for e in bio]
            self.play(LaggedStart(*flashes, lag_ratio=0.15), run_time=max(1.0, 0.25 * d))

        with self.narrate(2) as d:
            self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.6)
            possible = MT(p.possible, 96, weight=BOLD)
            actual = MT(p.actual, 96, "k3", weight=BOLD)
            VGroup(possible, actual).arrange(RIGHT, buff=3.0).shift(UP * 0.4)
            l1 = T("possible synapses", 28, "dim").next_to(possible, DOWN, buff=0.35)
            l2 = T("actual synapses", 28, "dim").next_to(actual, DOWN, buff=0.35)
            ratio = T(p.ratio, 34, "highlight").to_edge(DOWN, buff=1.0)
            self.play(FadeIn(possible, scale=0.8), FadeIn(l1), run_time=0.25 * d)
            self.play(FadeIn(actual, scale=0.8), FadeIn(l2), run_time=0.25 * d)
            self.play(Write(ratio), run_time=0.2 * d)

        with self.narrate(3) as d:
            question = T(p.question, 64, "accent", weight=BOLD)
            self.play(*[FadeOut(m, shift=UP * 0.3) for m in self.mobjects], run_time=0.5)
            self.play(Write(question), run_time=0.5 * d)
        self.clear_all()
