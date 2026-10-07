"""Scene 3: a pointwise convolution and a dense layer are the same operation (was S3Equivalence)."""

import random

from vidgen.api import *

from .common import BROWN, NAVY, TOKEN_FILL


@scene("kphi_equivalence")
class KphiEquivalence(NarratedScene):
    """Beat 1: 1x1 convolution on an image. Beat 2: the image becomes a token sequence and the
    same weights act as a dense layer. Beat 3: "Dense layer = Pointwise convolution"."""

    beat_count = 3

    def construct(self) -> None:
        rng = random.Random(11)
        base, k2, dim, txt, gold = (resolve_color(c) for c in ("base", "k2", "dim", "text", "highlight"))
        channels = 6
        side = 0.48
        # image: 5x5 pixels
        grid = VGroup(*[Square(side, stroke_width=1, stroke_color=dim, fill_opacity=1,
                               fill_color=interpolate_color(ManimColor(NAVY), ManimColor(base), rng.random()))
                        for _ in range(25)]).arrange_in_grid(5, 5, buff=0)
        grid.move_to([-4.8, 0, 0])
        img_lbl = T("image  H × W × C", 26, "dim").next_to(grid, UP, buff=0.35)

        in_vec = VGroup(*[Square(0.4, stroke_width=1.5, stroke_color=txt, fill_opacity=0.9,
                                 fill_color=interpolate_color(ManimColor(NAVY), ManimColor(base), (i + 1) / channels))
                          for i in range(channels)]).arrange(DOWN, buff=0.06).move_to([-1.6, 0, 0])
        out_vec = VGroup(*[Square(0.4, stroke_width=1.5, stroke_color=txt, fill_opacity=0.9,
                                  fill_color=interpolate_color(ManimColor(BROWN), ManimColor(k2), (i + 1) / channels))
                           for i in range(channels)]).arrange(DOWN, buff=0.06).move_to([3.0, 0, 0])
        w_edges = VGroup(*[Line(in_vec[i].get_right(), out_vec[j].get_left(), stroke_width=1.3,
                                color=txt, stroke_opacity=0.35)
                           for i in range(channels) for j in range(channels)])
        w_lbl = T("same weights W", 26).move_to([0.7, 2.0, 0])
        in_lbl = T("C channels in", 22, "dim").next_to(in_vec, DOWN, buff=0.3)
        out_lbl = T("F channels out", 22, "dim").next_to(out_vec, DOWN, buff=0.3)
        op_name = T("pointwise (1×1) convolution", 34, "base", weight=BOLD).to_edge(DOWN, buff=0.55)

        def pulse() -> Animation:
            return ShowPassingFlash(w_edges.copy().set_stroke(gold, width=3, opacity=1), time_width=0.5)

        with self.narrate(0):
            self.play(FadeIn(grid, lag_ratio=0.02), FadeIn(img_lbl), run_time=1.0)
            hl = SurroundingRectangle(grid[12], color=gold, buff=0, stroke_width=4)
            self.play(Create(hl), run_time=0.5)
            self.play(TransformFromCopy(VGroup(*[grid[12].copy() for _ in range(channels)]), in_vec),
                      FadeIn(in_lbl), run_time=1.0)
            self.play(Create(w_edges, lag_ratio=0.01), FadeIn(w_lbl), run_time=1.0)
            self.play(pulse(), FadeIn(out_vec, lag_ratio=0.15), FadeIn(out_lbl), run_time=1.2)
            for k in (6, 18):
                self.play(hl.animate.move_to(grid[k]), run_time=0.4)
                self.play(pulse(), Indicate(out_vec, color=gold, scale_factor=1.05), run_time=0.7)
            self.play(Write(op_name), run_time=0.8)

        # sequence = image with width 1
        words = ["Large", "language", "models", "are", "sparse"]
        col = VGroup(*[Rectangle(width=1.9, height=0.62, stroke_color=dim, stroke_width=1.2,
                                 fill_color=TOKEN_FILL, fill_opacity=1) for _ in words]
                     ).arrange(DOWN, buff=0).move_to([-4.7, 0, 0])
        toks = VGroup(*[T(w, 24).move_to(col[i]) for i, w in enumerate(words)])
        seq_lbl = T("sequence  length × 1 × C", 26, "dim").next_to(col, UP, buff=0.35)
        seq_lbl.shift(RIGHT * max(0.0, self.safe_area.x0 - seq_lbl.get_left()[0]))  # not in the margin
        h_brace = Brace(col, LEFT, color=dim)
        h_txt = T("H = length", 22, "dim").next_to(h_brace, LEFT, buff=0.1).rotate(PI / 2)
        h_txt.next_to(h_brace, LEFT, buff=0.1)
        op2 = T("dense (linear) layer", 34, "k2", weight=BOLD).move_to(op_name)

        with self.narrate(1) as d:
            rows = VGroup(*[VGroup(*grid[r * 5:(r + 1) * 5]) for r in range(5)])
            self.play(FadeOut(hl), ReplacementTransform(rows, col), Transform(img_lbl, seq_lbl), run_time=1.4)
            self.play(FadeIn(toks, lag_ratio=0.15), GrowFromCenter(h_brace), FadeIn(h_txt),
                      Transform(op_name, op2), run_time=1.2)
            hl2 = SurroundingRectangle(col[0], color=gold, buff=0, stroke_width=4)
            self.play(Create(hl2), run_time=0.3)
            per = max(0.5, (d - 3.6) / len(words))
            for i in range(len(words)):
                self.play(hl2.animate.move_to(col[i]), pulse(),
                          Indicate(out_vec, color=gold, scale_factor=1.04), run_time=per)

        with self.narrate(2):
            self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.6)
            lhs = T("Dense layer", 52, "k2", weight=BOLD)
            eq = T("=", 64, weight=BOLD)
            rhs = T("Pointwise convolution", 52, "base", weight=BOLD)
            line = VGroup(lhs, eq, rhs).arrange(RIGHT, buff=0.45)
            self.play(FadeIn(lhs, shift=RIGHT * 0.3), run_time=0.6)
            self.play(FadeIn(eq, scale=1.5), run_time=0.4)
            self.play(FadeIn(rhs, shift=LEFT * 0.3), run_time=0.6)
            note = T("a trick for one is a trick for the other", 28, "dim").next_to(line, DOWN, buff=0.6)
            self.play(FadeIn(note), run_time=0.8)
        self.clear_all()
