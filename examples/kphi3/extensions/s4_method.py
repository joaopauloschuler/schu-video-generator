"""Scene 4: replacing a dense layer by the grouped subnetwork K, interleave, L, sum (was S4Method)."""

from vidgen.api import *

from .common import GOLD_FILL, group_color


@scene("kphi_method")
class KphiMethod(NarratedScene):
    """Five beats building the subnetwork step by step, then the weight-count formulas."""

    beat_count = 5

    class Params(SceneParams):
        result: str = "Vision models: ~80% fewer parameters, same accuracy"

    def construct(self) -> None:
        n, groups, gap, y0 = 9, 3, 0.48, -0.35
        per_group = n // groups
        base, k3, gold, txt = (resolve_color(c) for c in ("base", "k3", "highlight", "text"))

        def gcol(i: int) -> str:
            return group_color(i // per_group)

        def title(s: str) -> Text:
            return T(s, 30, weight=BOLD).to_edge(UP, buff=0.45)

        def hdr(s: str, x: float) -> Text:
            return T(s, 22, "dim").move_to([x, 2.35, 0])

        # --- monolithic layer M
        m_in = column(n, -2.4, gap, y0)
        m_out = column(n, 2.4, gap, y0)
        m_edges = edges(m_in, m_out, dense_pairs(n, n), "base", 1.3, 0.55)
        t1 = title("Monolithic dense layer M")
        w_cnt = T(f"{n * n} weights", 28, "base").to_edge(DOWN, buff=0.45)

        with self.narrate(0) as d:
            self.play(FadeIn(t1), FadeIn(m_in), FadeIn(m_out), run_time=0.8)
            self.play(Create(m_edges, lag_ratio=0.005), FadeIn(w_cnt), run_time=0.45 * d)
            self.play(Indicate(m_edges, color=gold, scale_factor=1.0), run_time=1.0)

        # --- K grouped convolution
        X_IN, X_K, X_I, X_L, X_S, X_O = -6.0, -3.6, -1.2, 1.2, 3.35, 5.6
        inp = column(n, X_IN, gap, y0)
        for i, dot in enumerate(inp):
            dot.set_color(gcol(i))
        k_out = column(n, X_K, gap, y0)
        for i, dot in enumerate(k_out):
            dot.set_color(gcol(i))
        k_edges = VGroup(*[Line(inp[i].get_center(), k_out[j].get_center(), stroke_width=1.8,
                                color=gcol(i), stroke_opacity=0.8)
                           for i, j in grouped_pairs(n, groups)])
        in_boxes = VGroup(*[SurroundingRectangle(VGroup(*inp[g * per_group:(g + 1) * per_group]),
                                                 color=group_color(g), buff=0.12, corner_radius=0.12, stroke_width=2)
                            for g in range(groups)])
        t2 = title(f"K: grouped pointwise convolution  (N = {groups} groups)")
        w_cnt2 = T(f"{n * n // groups} weights", 28, "k3").move_to(w_cnt)
        h_in, h_k = hdr("input", X_IN), hdr("K", X_K)

        with self.narrate(1) as d:
            self.play(FadeOut(m_edges), Transform(t1, t2), run_time=0.8)
            self.play(Transform(m_in, inp), Transform(m_out, k_out), run_time=1.2)
            self.play(Create(in_boxes), FadeIn(h_in), FadeIn(h_k), run_time=0.8)
            self.play(Create(k_edges, lag_ratio=0.02), Transform(w_cnt, w_cnt2), run_time=0.35 * d)

        # --- interleave
        perm = [(q % per_group) * groups + q // per_group for q in range(n)]   # q=g*3+k -> k*3+g
        il = column(n, X_I, gap, y0)
        il_dots = VGroup(*[Dot(il[perm[q]].get_center(), radius=0.08, color=gcol(q)) for q in range(n)]
                         ).set_z_index(3)
        il_lines = VGroup(*[Line(k_out[q].get_center(), il[perm[q]].get_center(), stroke_width=2,
                                 color=gcol(q), stroke_opacity=0.8) for q in range(n)])
        il_boxes = VGroup(*[SurroundingRectangle(VGroup(*il[h * per_group:(h + 1) * per_group]), color=txt,
                                                 buff=0.12, corner_radius=0.12, stroke_width=2)
                            for h in range(groups)])
        t3 = title("Interleaving: every new group mixes all groups")
        h_i = hdr("interleave", X_I)

        with self.narrate(2) as d:
            self.play(Transform(t1, t3), FadeIn(h_i), run_time=0.8)
            self.play(LaggedStart(*[TransformFromCopy(m_out[q], il_dots[q]) for q in range(n)], lag_ratio=0.1),
                      Create(il_lines, lag_ratio=0.1), run_time=0.4 * d)
            self.play(Create(il_boxes), run_time=0.8)
            self.play(LaggedStart(*[Indicate(VGroup(*[il_dots[q] for q in range(n) if perm[q] // per_group == h]),
                                             color=gold) for h in range(groups)], lag_ratio=0.4),
                      run_time=1.6)

        # --- L grouped + summation
        l_out = column(n, X_L, gap, y0, color="k3")
        l_edges = edges(il, l_out, grouped_pairs(n, groups), "k3", 1.8, 0.8)
        sigma = RoundedRectangle(width=0.8, height=n * gap + 0.2, corner_radius=0.2, stroke_color=gold,
                                 fill_color=GOLD_FILL, fill_opacity=1).move_to([X_S, y0, 0])
        sig_t = T("+", 48, "highlight", weight=BOLD).move_to(sigma)
        l_to_s = VGroup(*[Line(l_out[i].get_center(), [X_S - 0.4, l_out[i].get_y(), 0], stroke_width=1.6,
                               color=k3, stroke_opacity=0.7) for i in range(n)])
        skip = CurvedArrow(k_out[0].get_center() + UP * 0.25, sigma.get_top() + UP * 0.05,
                           angle=-PI / 3.2, color=gold, stroke_width=3, tip_length=0.2)
        out = column(n, X_O, gap, y0)
        s_to_o = VGroup(*[Line([X_S + 0.4, out[i].get_y(), 0], out[i].get_center(), stroke_width=1.6,
                               color=txt, stroke_opacity=0.7) for i in range(n)])
        t4 = title("L: grouped convolution, then sum both paths")
        h_l, h_s, h_o = hdr("L", X_L), hdr("sum", X_S), hdr("output", X_O)
        for h in (h_l, h_s, h_o):
            h.set_y(-2.85)

        with self.narrate(3) as d:
            self.play(Transform(t1, t4), h_in.animate.set_y(-2.85), h_k.animate.set_y(-2.85),
                      h_i.animate.set_y(-2.85), FadeOut(w_cnt), run_time=0.8)
            self.play(Create(l_edges, lag_ratio=0.02), FadeIn(l_out), FadeIn(h_l), run_time=0.3 * d)
            self.play(Create(l_to_s), FadeIn(sigma), FadeIn(sig_t), FadeIn(h_s), run_time=0.8)
            self.play(Create(skip), run_time=0.8)
            self.play(Create(s_to_o), FadeIn(out), FadeIn(h_o), run_time=0.8)

        with self.narrate(4) as d:
            diagram = Group(*[m for m in self.mobjects if m is not t1])
            # zoom out to 0.55 (as diagram.animate.scale(0.55).to_edge(UP)); the column labels
            # keep their 22 pt size (22 pt * 0.55 would be below lint's min_font)
            factor, center = 0.55, diagram.get_center()
            lift = (config.frame_height / 2 - 0.35) - (center[1] + (diagram.get_top()[1] - center[1]) * factor)
            labels = (h_in, h_k, h_i, h_l, h_s, h_o)

            def zoom(m: Mobject) -> Animation:
                target = m.animate.scale(factor, about_point=center).shift(UP * lift)
                return target.scale(1 / factor) if m in labels else target

            self.play(FadeOut(t1), *[zoom(m) for m in diagram], run_time=1.0)
            r1 = MT(f'Dense layer:   <span foreground="{base}">C × F</span> weights', 34)
            r2 = MT(f'Subnetwork:   <span foreground="{k3}">2 × C × F / N</span> weights', 34)
            rows = VGroup(r1, r2).arrange(DOWN, buff=0.35, aligned_edge=LEFT).shift(DOWN * 1.3)
            self.play(FadeIn(r1, shift=UP * 0.2), run_time=0.8)
            self.play(FadeIn(r2, shift=UP * 0.2), run_time=0.8)
            res = T(self.params.result, 30, "highlight", weight=BOLD).next_to(rows, DOWN, buff=0.55)
            self.wait(max(0.1, 0.35 * d - 2.6))
            self.play(Write(res), run_time=1.2)
        self.clear_all()
