"""Scene 7: training vs validation loss panels, then the information bottleneck (was S7Loss)."""

import random

from vidgen.api import *

from .common import group_color, loss_panel


@scene("kphi_loss")
class KphiLoss(NarratedScene):
    """Beat 1: training-loss panel. Beat 2: validation-loss panel, bars in the order 2, 1, 3,
    the best one marked. Beat 3: dots squeezed through a funnel."""

    beat_count = 3

    class Params(SceneParams):
        models: list[str] = Field(min_length=3, max_length=3)
        colors: list[ThemeColor] = Field(default=["base", "k2", "k3"], min_length=3, max_length=3)
        training: list[float] = Field(min_length=3, max_length=3)
        validation: list[float] = Field(min_length=3, max_length=3)
        note: str = "lower is better · axis starts at 1.0"

        @field_validator("training", "validation")
        @classmethod
        def _in_axis_range(cls, values: list[float]) -> list[float]:
            if any(not 1.0 < v <= 1.7 for v in values):
                raise ValueError("losses must be in (1.0, 1.7] (the axis range)")
            return values

    def construct(self) -> None:
        p = self.params
        gold = resolve_color("highlight")
        t_best = min(range(3), key=lambda i: p.training[i])
        v_best = min(range(3), key=lambda i: p.validation[i])
        tf, tb, tv = loss_panel("Training loss", p.training, p.models, p.colors, -3.4, t_best)
        vf, vb, vv = loss_panel("Validation loss", p.validation, p.models, p.colors, 3.6, v_best)
        note = T(p.note, 22, "dim").to_edge(DOWN, buff=self.margin_y)  # inside the safe area

        with self.narrate(0):
            self.play(FadeIn(tf), FadeIn(note), run_time=0.8)
            self.play(LaggedStart(*[GrowFromEdge(b, DOWN) for b in tb], lag_ratio=0.3), run_time=1.5)
            self.play(FadeIn(tv, lag_ratio=0.2), run_time=0.8)
            self.play(Indicate(tv[t_best], color=gold, scale_factor=1.3), run_time=0.9)

        with self.narrate(1) as d:
            self.play(FadeIn(vf), tf.animate.set_opacity(0.45), tb.animate.set_opacity(0.45),
                      tv.animate.set_opacity(0.45), run_time=0.8)
            self.wait(max(0.1, 0.18 * d - 0.8))
            self.play(GrowFromEdge(vb[1], DOWN), FadeIn(vv[1]), run_time=1.0)
            self.play(GrowFromEdge(vb[0], DOWN), FadeIn(vv[0]), run_time=1.0)
            self.wait(max(0.1, 0.25 * d - 2.0))
            self.play(GrowFromEdge(vb[2], DOWN), FadeIn(vv[2]), run_time=1.0)
            star = T("best", 22, "highlight", weight=BOLD).next_to(vv[v_best], UP, buff=0.12)
            self.play(FadeIn(star, shift=DOWN * 0.2), Circumscribe(VGroup(vb[v_best], vv[v_best]), color=gold),
                      run_time=1.2)

        with self.narrate(2) as d:
            self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.6)
            funnel = Polygon([-4.6, 2.0, 0], [-0.7, 0.45, 0], [0.7, 0.45, 0], [4.6, 2.0, 0],
                             [4.6, -2.0, 0], [0.7, -0.45, 0], [-0.7, -0.45, 0], [-4.6, -2.0, 0],
                             stroke_color=resolve_color("dim"), fill_color=resolve_color("surface"), fill_opacity=1).shift(UP * 0.2)
            lbl = T("information bottleneck", 26, "dim").next_to(funnel, UP, buff=0.25)
            rng = random.Random(5)
            dots = VGroup(*[Dot([rng.uniform(-6.3, -4.9), rng.uniform(-1.6, 2.0), 0], radius=0.07,
                                color=group_color(k % 3)) for k in range(24)]).set_z_index(5)
            self.play(FadeIn(funnel), FadeIn(lbl), FadeIn(dots, lag_ratio=0.03), run_time=1.0)
            mid = [Dot([rng.uniform(-0.6, 0.6), rng.uniform(-0.15, 0.55), 0]) for _ in dots]
            self.play(*[dot.animate.move_to(m) for dot, m in zip(dots, mid)], run_time=0.25 * d)
            targets = [[5.6, 1.2, 0], [5.6, 0.2, 0], [5.6, -0.8, 0]]
            self.play(*[dot.animate.move_to(np.array(targets[k % 3]) +
                                            np.array([rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), 0]))
                        for k, dot in enumerate(dots)], run_time=0.2 * d)
            gen = T("generalize ✓", 30, "k3", weight=BOLD).move_to([0, -2.6, 0]).shift(RIGHT * 2.2)
            mem = T("memorize ✗", 30, "accent", weight=BOLD).move_to([0, -2.6, 0]).shift(LEFT * 2.2)
            self.play(FadeIn(mem), run_time=0.4)
            self.play(FadeIn(gen), run_time=0.4)
        self.clear_all()
