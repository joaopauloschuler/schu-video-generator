"""Example evidence scenes from a paper-explainer video (16:9). Needs science_helpers.py in the
same extensions/ folder. Each scene animates one line of a paper's evidence; the defaults are the
worked example's numbers, with their source in ``caption``. Replace them with your paper's
values and keep the source tag on screen.

- ``edx_probe``: an X-ray (EDX/EDS) probe reads the elements at two points, a structure and the rock
  beside it, as animated bars; a "not detected" chip (3 beats).
- ``nitrogen_clock``: a log-age axis with a "detectable" and a "below detection" band; recent and old
  reference samples drop in, then the studied sample lands (4 beats).
- ``isotope_range``: a number line; a reference group drops in, the sample's value lands among it,
  then a second group, a note and a short quote (3 beats).
"""
import math
import random

import numpy as np

from vidgen.api import *

from .science_helpers import rough_blob, run

GREEN_HOT = "#7dff8a"
STONE = "#2e323a"
STONE_EDGE = "#6b7380"
MATRIX = "#59616d"


def _grains(rng, center, w, h, n, colors=(MATRIX, "#4a515c", "#6c7480", "#2a2e35"), rmin=0.02, rmax=0.07):
    g = VGroup()
    for _ in range(n):
        x = rng.uniform(-w / 2 + 0.1, w / 2 - 0.1); y = rng.uniform(-h / 2 + 0.1, h / 2 - 0.1)
        g.add(Dot(radius=rng.uniform(rmin, rmax), color=rng.choice(colors)).move_to(center + np.array([x, y, 0])))
    return g


def _heading(sc, text):
    head = sc.text(text, size="heading", color="text", weight=BOLD, role="heading")
    place(head, sc.region("header"), fit="none", align="top")
    return head


def _chip(sc, text, color, icon_name=None):
    t = sc.text(text, size="caption", color=color)
    parts = [icon(icon_name, size="caption", color=color), t] if icon_name else [t]
    g = VGroup(*parts).arrange(RIGHT, buff=0.15)
    box = SurroundingRectangle(g, buff=0.14, corner_radius=0.12, color=color, stroke_width=2.5)
    box.set_fill("#14171c", 0.9)
    return VGroup(box, g)



# --------------------------------------------------------------------------------------------
@scene("edx_probe")
class EdxProbe(NarratedScene):
    """An EDX probe reads the elements at two points (example data: Wallis et al. 2013, Table 3).
    Beats: 1 the method, 2 point on the structure, 3 point on the matrix."""

    beat_count = 3
    outro = 0.5

    class Params(SceneParams):
        heading: TranslatableStr
        elements: list[str] = ["C", "N", "O", "Si", "Al"]
        structure: list[float] = [59.81, 0.0, 31.3, 3.55, 2.11]
        matrix: list[float] = [0.0, 0.0, 60.53, 20.91, 12.15]
        s_label: TranslatableStr = "carbon-rich structure (S1)"
        m_label: TranslatableStr = "rock beside it (S3)"
        probe_label: TranslatableStr = "X-ray detector (EDX)"
        nd_label: TranslatableStr = "N not detected"
        caption: TranslatableStr = "EDX abundances, Wallis et al. 2013 (arXiv:1303.1845), Table 3"

    def construct(self):
        p = self.params
        acc = self.theme.color("accent")
        head = _heading(self, p.heading)
        rng = random.Random(8)
        panel = RoundedRectangle(width=5.4, height=4.4, corner_radius=0.25, stroke_color=STONE_EDGE, stroke_width=3).set_fill("#3a3f48", 1).move_to([-3.6, -0.4, 0])
        grains = _grains(rng, panel.get_center(), 5.4, 4.4, 120)
        blob = rough_blob(0.9, seed=5, squash=0.7).set_fill("#15171b", 1).set_stroke("#8a6d3b", 3).move_to(panel.get_center() + np.array([-0.6, 0.5, 0]))
        s1 = blob.get_center()
        s3 = panel.get_center() + np.array([1.4, -1.2, 0])
        cross = VGroup(Circle(radius=0.22, stroke_color=GREEN_HOT, stroke_width=3), Line(LEFT * 0.35, RIGHT * 0.35, stroke_color=GREEN_HOT, stroke_width=2),
                       Line(UP * 0.35, DOWN * 0.35, stroke_color=GREEN_HOT, stroke_width=2)).move_to(panel.get_corner(UR) + np.array([-0.6, -0.6, 0]))
        probe_lbl = self.text(p.probe_label, size="caption", color=GREEN_HOT).next_to(panel, UP, buff=0.12).align_to(panel, LEFT)
        cap = self.text(p.caption, size="caption", color="dim")
        cap.move_to([0, self.safe_area.y0 + cap.height / 2, 0])

        # bar chart on the right
        base_y, x0, step, scale = -2.2, 1.2, 1.15, 0.062
        axis = Line([x0 - 0.5, base_y, 0], [x0 + step * len(p.elements) - 0.4, base_y, 0], stroke_color="#6b7380", stroke_width=2)
        names = VGroup(*[self.text(e, size="body", color="text").move_to([x0 + i * step, base_y - 0.35, 0]) for i, e in enumerate(p.elements)])

        def bars_for(vals, color):
            g = VGroup()
            for i, v in enumerate(vals):
                h = max(0.02, v * scale)
                g.add(Rectangle(width=0.62, height=h, stroke_width=0).set_fill(color, 0.95).move_to([x0 + i * step, base_y + h / 2, 0]))
            return g

        def labels_for(vals, bars):
            return VGroup(*[self.text(f"{v:.1f}" if v else "0", size="caption", color="text").next_to(b, UP, buff=0.08) for v, b in zip(vals, bars)])

        with self.narrate(0) as d:
            self.play(FadeIn(head), FadeIn(panel), FadeIn(grains), FadeIn(cap), run_time=run(d, 0.15, 0.7))
            self.play(DrawBorderThenFill(blob), run_time=run(d, 0.15, 0.7))
            self.play(FadeIn(cross, scale=1.6), FadeIn(probe_lbl), Create(axis), FadeIn(names), run_time=run(d, 0.2, 0.9))
            self.play(Flash(cross.get_center(), color=GREEN_HOT, flash_radius=0.4), run_time=0.5)

        sb = bars_for(p.structure, "#c9a35a")
        sl = labels_for(p.structure, sb)
        s_lbl = self.text(p.s_label, size="caption", color="#c9a35a").move_to([x0 + step * 2, 2.0, 0])
        nd = _chip(self, p.nd_label, acc, "x").move_to([x0 + step * 3.4, 0.55, 0])
        with self.narrate(1) as d:
            self.play(cross.animate.move_to(s1), run_time=run(d, 0.15, 0.8))
            self.play(Flash(s1, color=GREEN_HOT, flash_radius=0.4), FadeIn(s_lbl), run_time=0.45)
            self.play(LaggedStart(*[GrowFromEdge(b, DOWN) for b in sb], lag_ratio=0.15), run_time=run(d, 0.25, 1.2))
            self.play(FadeIn(sl), run_time=0.3)
            self.play(FadeIn(nd, scale=1.3), Indicate(names[1], color=acc), run_time=run(d, 0.15, 0.8))

        mb = bars_for(p.matrix, "#aab2bd")
        ml = labels_for(p.matrix, mb)
        m_lbl = self.text(p.m_label, size="caption", color="#aab2bd").move_to([x0 + step * 2, 2.5, 0])
        with self.narrate(2) as d:
            self.play(FadeOut(nd), cross.animate.move_to(s3), run_time=run(d, 0.15, 0.8))
            self.play(Flash(s3, color=GREEN_HOT, flash_radius=0.4), FadeOut(s_lbl), FadeOut(sl), run_time=0.45)
            self.play(Transform(sb, mb), run_time=run(d, 0.3, 1.3))
            self.play(FadeIn(ml), FadeIn(m_lbl), run_time=0.4)
        self.finish()



# --------------------------------------------------------------------------------------------
@scene("nitrogen_clock")
class NitrogenClock(NarratedScene):
    """Nitrogen as a clock (example data as cited in Wallis et al. 2013, after Hoover 2007): log-age
    axis; recent remains in the 'detectable' band, old fossils below detection; the studied sample
    joins the lower band. Beats: 1 axis + bands, 2 recent remains, 3 old fossils, 4 the sample."""

    beat_count = 4
    outro = 0.5

    class Params(SceneParams):
        heading: TranslatableStr
        hi_band: TranslatableStr = "nitrogen detectable: 2-18%"
        lo_band: TranslatableStr = "below detection: N < 0.5%"
        axis_label: TranslatableStr = "age"
        sample_label: TranslatableStr = "the studied sample"
        recent: list[list] = [[2e3, "Peru mummy", 0.25, "down"], [5e3, "Egypt mummy", 0.95, "right"], [3.6e4, "mammoth", 0.25, "right"]]
        old: list[list] = [[8.4e6, "amber insect", -1.2], [1e8, "ammonite", -1.75], [5.05e8, "trilobite", -1.2], [2.7e9, "cyanobacteria", -1.75]]
        caption: TranslatableStr = "Data as cited in Wallis et al. 2013 (arXiv:1303.1845), after Hoover 2007"

    def construct(self):
        p = self.params
        cyan, hl, acc = self.theme.color("primary"), self.theme.color("highlight"), self.theme.color("accent")
        head = _heading(self, p.heading)
        x_left, x_right = -5.6, 4.0
        lo_e, hi_e = 3, 10   # 1e3 .. 1e10 years

        def X(years):
            return x_left + (math.log10(years) - lo_e) / (hi_e - lo_e) * (x_right - x_left)

        y_axis = -2.55
        axis = Arrow([x_left - 0.2, y_axis, 0], [x_right + 0.4, y_axis, 0], buff=0, stroke_width=3, color="#6b7380", max_tip_length_to_length_ratio=0.03)
        ticks = VGroup()
        for yrs, lab in [(1e3, "1,000 years"), (1e6, "1 million years"), (1e9, "1 billion years")]:
            ticks.add(VGroup(Line([X(yrs), y_axis - 0.08, 0], [X(yrs), y_axis + 0.08, 0], stroke_color="#6b7380", stroke_width=2),
                             self.text(lab, size="caption", color="dim").move_to([X(yrs), y_axis - 0.4, 0])))
        ax_lbl = self.text(p.axis_label, size="caption", color="dim").next_to(axis, RIGHT, buff=0.12)
        hi = Rectangle(width=x_right - x_left + 0.4, height=2.0, stroke_width=0).set_fill(cyan, 0.13).move_to([(x_left + x_right) / 2 + 0.1, 0.9, 0])
        lo = Rectangle(width=x_right - x_left + 0.4, height=1.6, stroke_width=0).set_fill(acc, 0.13).move_to([(x_left + x_right) / 2 + 0.1, -1.25, 0])
        hi_t = self.text(p.hi_band, size="caption", color=cyan).next_to(hi.get_corner(UL), DR, buff=0.12)
        lo_t = self.text(p.lo_band, size="caption", color=acc).next_to(lo.get_corner(UL), DR, buff=0.12)
        cap = self.text(p.caption, size="caption", color="dim")
        cap.move_to([0, self.safe_area.y0 + cap.height / 2, 0])
        with self.narrate(0) as d:
            self.play(FadeIn(head), GrowArrow(axis), FadeIn(ticks), FadeIn(ax_lbl), FadeIn(cap), run_time=run(d, 0.25, 1.1))
            self.play(GrowFromEdge(hi, LEFT), FadeIn(hi_t), run_time=run(d, 0.2, 0.8))
            self.play(GrowFromEdge(lo, LEFT), FadeIn(lo_t), run_time=run(d, 0.2, 0.8))

        sides = {"down": DOWN, "up": UP, "right": RIGHT, "left": LEFT}
        r_mobs = VGroup()
        for yrs, name, y, side in p.recent:
            yrs, side = float(yrs), sides[side]
            dot = Dot([X(yrs), y, 0], radius=0.11, color=cyan)
            lab = self.text(name, size="caption", color="text").next_to(dot, side, buff=0.12)
            r_mobs.add(VGroup(dot, lab))
        with self.narrate(1) as d:
            self.play(LaggedStart(*[FadeIn(m, shift=DOWN * 0.5) for m in r_mobs], lag_ratio=0.35), run_time=run(d, 0.45, 2.0))
            self.play(Indicate(hi_t, color=cyan), run_time=run(d, 0.15, 0.8))

        o_mobs = VGroup()
        for yrs, name, y in p.old:
            yrs = float(yrs)
            dot = Dot([X(yrs), y, 0], radius=0.11, color=acc)
            lab = self.text(name, size="caption", color="text")
            lab.next_to(dot, RIGHT, buff=0.12)
            o_mobs.add(VGroup(dot, lab))
        with self.narrate(2) as d:
            self.play(LaggedStart(*[FadeIn(m, shift=DOWN * 0.5) for m in o_mobs], lag_ratio=0.3), run_time=run(d, 0.5, 2.2))
            self.play(Indicate(lo_t, color=acc), run_time=run(d, 0.15, 0.8))

        star = Star(n=5, outer_radius=0.28, inner_radius=0.12, color=hl, fill_opacity=1, stroke_width=0).move_to([x_right + 1.6, 2.4, 0])
        landing = np.array([x_right + 1.75, -0.95, 0])
        sample_t = self.text(p.sample_label, size="caption", color="highlight")
        with self.narrate(3) as d:
            self.play(FadeIn(star, scale=0.5), run_time=0.3)
            self.play(star.animate.move_to(landing), run_time=run(d, 0.25, 1.0), rate_func=rate_functions.ease_in_quad)
            sample_t.next_to(star, UP, buff=0.2)
            if sample_t.get_right()[0] > self.safe_area.x1:
                sample_t.shift(LEFT * (sample_t.get_right()[0] - self.safe_area.x1))
            self.sfx("pop", gain=-6)
            self.play(Flash(landing, color=hl, flash_radius=0.45), FadeIn(sample_t, shift=UP * 0.1), run_time=run(d, 0.2, 0.8))
            self.play(Indicate(VGroup(lo, lo_t), color=hl, scale_factor=1.02), run_time=run(d, 0.2, 1.0))
        self.finish()



# --------------------------------------------------------------------------------------------
@scene("isotope_range")
class IsotopeRange(NarratedScene):
    """A number line (example: δ17O): a reference group drops in, the sample's value lands among it,
    then a second group, a note and a quote (example data: Wallis et al. 2013, fig. 2; reference
    data Clayton & Mayeda). Beats: 1 reference group, 2 the sample, 3 second group + note + quote.
    ``lo`` / ``hi`` set the axis range."""

    beat_count = 3
    outro = 0.5

    class Params(SceneParams):
        heading: TranslatableStr
        ci: list[list] = [["Alais", 8.60], ["Orgueil", 8.79], ["Ivuna", 9.23]]
        meta: list[list] = [["B-7904", 10.91], ["Y-86789", 10.94], ["Y-86720", 11.58], ["Y-82162", 11.59]]
        sample: float = 8.978
        lo: float = 8.0
        hi: float = 12.0
        ci_label: TranslatableStr = "CI chondrites"
        meta_label: TranslatableStr = "CI-like (Meta-C)"
        sample_label: TranslatableStr = "sample"
        note: TranslatableStr = "δ18O 17.8‰: high, but within range"
        quote: TranslatableStr = "\"unequivocally meteorites\""
        caption: TranslatableStr = "δ17O (‰ rel. SMOW). Wallis et al. 2013 (arXiv:1303.1845); CI and Meta-C data: Clayton & Mayeda"

    def construct(self):
        p = self.params
        cyan, hl = self.theme.color("primary"), self.theme.color("highlight")
        tert = self.theme.color("tertiary")
        head = _heading(self, p.heading)
        lo, hi, xl, xr, y0 = p.lo, p.hi, -5.6, 5.6, -0.9

        def X(v):
            return xl + (v - lo) / (hi - lo) * (xr - xl)

        line = NumberLine(x_range=[lo, hi, 0.5], length=xr - xl, include_numbers=False, color="#6b7380", stroke_width=3).move_to([0, y0, 0])
        nums = VGroup(*[self.text(f"{v:g}", size="caption", color="dim").move_to([X(v), y0 - 0.4, 0]) for v in range(math.ceil(lo), math.floor(hi) + 1)])
        cap = self.text(p.caption, size="caption", color="dim")
        shrink_to_fit(cap, self.safe_width, 1)
        cap.move_to([0, self.safe_area.y0 + cap.height / 2, 0])

        def group(items, color, up=True):
            g = VGroup()
            for k, (name, v) in enumerate(items):
                dot = Dot([X(v), y0, 0], radius=0.12, color=color)
                lab = self.text(str(name), size="caption", color="text")
                off = 0.55 + 0.45 * (k % 2)
                lab.move_to([X(v), y0 + (off if up else -off - 0.45), 0])
                g.add(VGroup(dot, lab))
            return g

        ci = group(p.ci, cyan)
        ci_vals = [v for _, v in p.ci]
        ci_band = Rectangle(width=X(max(ci_vals)) - X(min(ci_vals)) + 0.5, height=2.4, stroke_width=0).set_fill(cyan, 0.12)
        ci_band.move_to([(X(max(ci_vals)) + X(min(ci_vals))) / 2, y0 + 0.5, 0])
        ci_t = self.text(p.ci_label, size="body", color=cyan, weight=BOLD).next_to(ci_band, UP, buff=0.12)
        with self.narrate(0) as d:
            self.play(FadeIn(head), Create(line), FadeIn(nums), FadeIn(cap), run_time=run(d, 0.2, 0.9))
            self.play(LaggedStart(*[FadeIn(m, shift=DOWN * 0.6) for m in ci], lag_ratio=0.3), run_time=run(d, 0.35, 1.4))
            self.play(FadeIn(ci_band), FadeIn(ci_t), run_time=run(d, 0.15, 0.6))

        star = Star(n=5, outer_radius=0.3, inner_radius=0.13, color=hl, fill_opacity=1, stroke_width=0).move_to([X(p.sample), 2.6, 0])
        sample_t = self.text(f"{p.sample_label} {p.sample:.2f}", size="body", color="highlight", weight=BOLD).move_to([X(p.sample), y0 - 1.3, 0])
        with self.narrate(1) as d:
            self.play(FadeIn(star, scale=0.5), run_time=0.3)
            self.play(star.animate.move_to([X(p.sample), y0, 0]), run_time=run(d, 0.3, 1.0), rate_func=rate_functions.ease_in_quad)
            self.sfx("pop", gain=-6)
            self.play(Flash([X(p.sample), y0, 0], color=hl, flash_radius=0.5), FadeIn(sample_t, shift=UP * 0.15), run_time=run(d, 0.2, 0.7))
            self.play(Indicate(ci_band, color=hl, scale_factor=1.03), run_time=run(d, 0.2, 0.8))

        meta = group(p.meta, tert)
        m_vals = [v for _, v in p.meta]
        m_band = Rectangle(width=X(max(m_vals)) - X(min(m_vals)) + 0.5, height=2.4, stroke_width=0).set_fill(tert, 0.12)
        m_band.move_to([(X(max(m_vals)) + X(min(m_vals))) / 2, y0 + 0.5, 0])
        m_t = self.text(p.meta_label, size="body", color=tert, weight=BOLD).next_to(m_band, UP, buff=0.12)
        note = self.text(p.note, size="caption", color="text")
        note.move_to([self.safe_area.x1 - note.width / 2, y0 - 1.3, 0])
        quote = self.text(p.quote, size="body", color="highlight").next_to(note, DOWN, buff=0.25).align_to(note, RIGHT)
        with self.narrate(2) as d:
            self.play(LaggedStart(*[FadeIn(m, shift=DOWN * 0.6) for m in meta], lag_ratio=0.2), FadeIn(m_band), FadeIn(m_t), run_time=run(d, 0.3, 1.4))
            self.play(FadeIn(note), run_time=run(d, 0.12, 0.5))
            self.play(Write(quote), run_time=run(d, 0.2, 1.0))
        self.finish()
