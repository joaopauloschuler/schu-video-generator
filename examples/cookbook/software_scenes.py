"""Example custom scenes from a software-showcase video (16:9). Needs fx.py in the same
extensions/ folder.

- ``dataflow_hook``: cold open; an image flows through glowing convolution stacks and is classified,
  then a provocative question, then a struck-through misconception (3 beats).
- ``stack_collapse``: a wobbling tower of dependencies collapses into one glowing binary (2 beats).
- ``orbit_arch``: a glowing core with feature chips orbiting it (1 beat).
- ``finale``: a two-line verdict, then the project URL in a glowing pill, facts and credits (2 beats).

The layouts are tuned for 16:9; for 9:16 see vertical.py / vertical_scenes.py.
Every on-screen string is a param; the defaults are placeholders, set your own in video.yaml.
"""
import math
import random

import numpy as np

from vidgen.api import *

from .fx import AMBER, CYAN, DEEP, MINT, PANEL, PINK, VIOLET, dust, glow, glow_dot, heading, light, neuron, picture, pill, run, stack

def _looping_particles(paths, color, per_path=2, speed=0.45, seed=1):
    """Particles that keep travelling along the given paths forever (an updater)."""
    rng = random.Random(seed)
    dots = VGroup()
    meta = []
    for p in paths:
        for k in range(per_path):
            d = glow_dot(color, radius=0.045, layers=3, strength=0.55)
            dots.add(d)
            meta.append((p, rng.uniform(0, 1), speed * rng.uniform(0.8, 1.25)))
    clock = {"t": 0.0}

    def upd(m, dt):
        clock["t"] += dt
        for d, (p, off, sp) in zip(m, meta, strict=False):
            a = (off + sp * clock["t"]) % 1.0
            d.move_to(p.point_from_proportion(a))
            d.set_opacity(min(1.0, 4 * min(a, 1 - a) + 0.05))
    dots.add_updater(upd)
    return dots


# ============================================================================================
@scene("dataflow_hook")
class DataflowHook(NarratedScene):
    """Cold open: an image flows through glowing convolution stacks and is classified; then the
    twist. Beats: 1 classification, 2 the twist (line1 + line2a + highlighted line2b),
    3 the misconception (``says`` + ``dead``), struck through."""

    beat_count = 3
    outro = 0.4

    class Params(SceneParams):
        image: str
        labels: list[str] = ["bird", "cat", "ship"]   # three output classes, the first one wins
        line1: TranslatableStr = "A deep learning library…"
        line2a: TranslatableStr = "written in"
        line2b: TranslatableStr = "<surprise>?"
        says: TranslatableStr = "everyone says"
        dead: TranslatableStr = "“<the misconception>.”"
        credit: TranslatableStr = ""

    def construct(self):
        p = self.params
        FW, FH = self.frame_width, self.frame_height
        bg = dust(FW, FH, n=80, seed=4)
        self.add(bg)

        img = picture(self.project.asset(p.image), height=1.9)
        img.move_to([-5.2, 0, 0])
        frame = RoundedRectangle(width=2.05, height=2.05, corner_radius=0.08, stroke_color=CYAN, stroke_width=2.5).move_to(img)
        fglow = glow(frame, CYAN, layers=5, width=8, opacity=0.45)

        s1 = stack(4, 1.9, 1.9, CYAN).move_to([-2.65, 0, 0])
        s2 = stack(5, 1.4, 1.4, VIOLET).move_to([-0.55, 0, 0])
        s3 = stack(6, 0.95, 0.95, PINK).move_to([1.3, 0, 0])
        dense = VGroup(*[neuron(MINT, 0.14) for _ in range(6)]).arrange(DOWN, buff=0.34).move_to([3.15, 0, 0])
        outs = VGroup(*[neuron(AMBER, 0.17) for _ in range(3)]).arrange(DOWN, buff=0.75).move_to([4.75, 0, 0])
        o_lbls = VGroup(*[self.text(t, size="body", color="dim").next_to(o, RIGHT, buff=0.25) for t, o in zip(p.labels, outs, strict=False)])
        e1 = VGroup(*[Line(s3.get_right(), n.get_center(), stroke_color=MINT, stroke_width=1.2, stroke_opacity=0.25) for n in dense])
        e2 = VGroup(*[Line(a.get_center(), b.get_center(), stroke_color=AMBER, stroke_width=1.2, stroke_opacity=0.22) for a in dense for b in outs])
        for e in e1:
            e.set_z_index(-1)
        for e in e2:
            e.set_z_index(-1)

        paths = []
        rng = random.Random(7)
        for k in range(6):
            dy = rng.uniform(-0.5, 0.5)
            pts = [img.get_center() + np.array([0, dy, 0]), s1.get_center() + np.array([0, dy * 0.8, 0]),
                   s2.get_center() + np.array([0, dy * 0.6, 0]), s3.get_center() + np.array([0, dy * 0.4, 0]),
                   dense[k].get_center(), outs[0].get_center()]
            paths.append(VMobject().set_points_as_corners(pts))
        parts = _looping_particles(paths, AMBER, per_path=2, speed=0.38)

        net = Group(fglow, frame, img, s1, s2, s3, e1, e2, dense, outs, o_lbls)
        credit = self.text(p.credit or " ", size="small", color="dim")
        credit.move_to([self.safe_area.x1 - credit.width / 2, self.safe_area.y0 + credit.height / 2, 0])

        with self.narrate(0) as d:
            self.play(FadeIn(img, scale=1.15), FadeIn(frame), FadeIn(fglow), FadeIn(credit),
                      LaggedStart(*[FadeIn(s, shift=RIGHT * 0.3) for s in (s1, s2, s3)], lag_ratio=0.25),
                      run_time=0.7)
            self.add(parts)
            self.sfx("whoosh", gain=-4)
            self.play(LaggedStart(*[Create(e) for e in e1], lag_ratio=0.05), FadeIn(dense, lag_ratio=0.1),
                      LaggedStart(*[Create(e) for e in e2], lag_ratio=0.03), FadeIn(outs), FadeIn(o_lbls), run_time=0.8)
            for s, col in ((s1, CYAN), (s2, VIOLET), (s3, PINK)):
                self.play(*[pl[0].animate.set_fill(col, 0.45) for pl in s], run_time=0.22)
                self.play(*[pl[0].animate.set_fill(col, 0.12) for pl in s], run_time=0.18)
            self.play(LaggedStart(*[light(n, MINT) for n in dense], lag_ratio=0.12), run_time=0.8)
            self.wait(max(0.1, d - 4.1))
            self.sfx("chime", gain=-6)
            self.play(light(outs[0], AMBER), o_lbls[0].animate.set_color(AMBER).scale(1.25, about_edge=LEFT),
                      Flash(outs[0].get_center(), color=AMBER, flash_radius=0.45), run_time=0.5)

        l1 = self.text(p.line1, size=64, color="text", weight=BOLD).move_to([0, 0.75, 0])
        l2a = self.text(p.line2a, size=64, color="text", weight=BOLD)
        l2b = self.text(p.line2b, size=78, color=AMBER, weight=BOLD)
        VGroup(l2a, l2b).arrange(RIGHT, buff=0.3, aligned_edge=DOWN).move_to([0, -0.55, 0])
        l2glow = glow(l2b, AMBER, layers=6, width=6, opacity=0.35)
        with self.narrate(1) as d:
            plate = Rectangle(width=FW, height=FH, stroke_width=0).set_fill(DEEP, 0.86)
            self.play(net.animate.scale(0.85), FadeOut(o_lbls), parts.animate.set_opacity(0.6), FadeIn(plate), FadeOut(credit), run_time=0.45)
            self.play(FadeIn(l1, shift=UP * 0.25), run_time=0.5)
            self.wait(max(0.1, d * 0.45 - 0.95))
            self.sfx("thud", gain=-3)
            self.play(FadeIn(l2a, shift=UP * 0.2), FadeIn(l2b, scale=1.8), FadeIn(l2glow), run_time=0.45)

        says = self.text(p.says, size="body", color="dim").move_to([0, 1.0, 0])
        dead = self.text(p.dead, size=60, color="text", weight=BOLD).move_to([0, 0.1, 0])
        strike = Line(dead.get_left() + LEFT * 0.15, dead.get_right() + RIGHT * 0.15, stroke_color=self.theme.color("accent"), stroke_width=7)
        with self.narrate(2) as d:
            self.play(FadeOut(VGroup(l1, l2a, l2b), shift=UP * 0.3), FadeOut(l2glow), run_time=0.45)
            self.play(FadeIn(says), FadeIn(dead, shift=UP * 0.2), run_time=0.5)
            self.wait(max(0.1, d - 1.6))
            self.sfx("swoosh", gain=-4)
            self.play(Create(strike), run_time=0.45)
        self.finish()


# ============================================================================================
@scene("stack_collapse")
class StackCollapse(NarratedScene):
    """A wobbling tower of dependencies collapses into one glowing native binary."""

    beat_count = 2
    outro = 0.4

    class Params(SceneParams):
        heading: TranslatableStr
        blocks: list[str]
        binary: TranslatableStr = "one native binary"
        badges: list[str] = []
        note: TranslatableStr = ""

    def construct(self):
        p = self.params
        acc = self.theme.color("accent")
        head = heading(self, p.heading)
        tower = VGroup()
        for k, t in enumerate(p.blocks):
            top = k == len(p.blocks) - 1
            col = acc if top else "#5b6478"
            r = RoundedRectangle(width=5.2, height=0.66, corner_radius=0.1, stroke_color=col, stroke_width=2).set_fill("#1a2133", 0.95)
            lab = self.text(t, size="caption", color=acc if top else "text")
            tower.add(VGroup(r, lab))
        tower.arrange(UP, buff=0.08).move_to([-3.3, -0.35, 0])
        base_pt = tower.get_bottom()
        note = self.text(p.note, size="small", color="dim") if p.note else VMobject()
        if p.note:
            note.move_to([0, self.safe_area.y0 + note.height / 2, 0])
        with self.narrate(0) as d:
            self.play(FadeIn(head), FadeIn(note), run_time=0.4)
            for k, b in enumerate(tower):
                self.sfx("pop", gain=-7)
                self.play(FadeIn(b, shift=DOWN * 0.5), run_time=min(0.35, run(d, 0.07, 0.35, 0.15)))
            for ang in (0.035, -0.06, 0.04, -0.02):
                self.play(Rotate(tower, ang, about_point=base_pt), run_time=0.28, rate_func=rate_functions.ease_in_out_sine)

        chip = RoundedRectangle(width=2.4, height=2.4, corner_radius=0.2, stroke_color=CYAN, stroke_width=3).set_fill(PANEL, 1).move_to([3.3, 0.35, 0])
        pins = VGroup()
        for k in range(5):
            o = -0.8 + 0.4 * k
            for a, b in (((-1.2, o), (-1.5, o)), ((1.2, o), (1.5, o)), ((o, 1.2), (o, 1.5)), ((o, -1.2), (o, -1.5))):
                pins.add(Line(chip.get_center() + np.array([a[0], a[1], 0]), chip.get_center() + np.array([b[0], b[1], 0]), stroke_color=CYAN, stroke_width=3))
        cico = icon("cpu", height=1.0, color=CYAN).move_to(chip)
        cglow = glow(chip, CYAN, layers=7, width=12, opacity=0.6)
        clab = self.text(p.binary, size="body", color="text", weight=BOLD).next_to(chip, DOWN, buff=0.5)
        badges = VGroup(*[pill(self, b, MINT) for b in p.badges]).arrange(RIGHT, buff=0.2).next_to(clab, DOWN, buff=0.3)
        if badges.width and badges.get_right()[0] > self.safe_area.x1:
            badges.shift(LEFT * (badges.get_right()[0] - self.safe_area.x1))
        with self.narrate(1) as d:
            self.sfx("swoosh", gain=-3)
            self.play(LaggedStart(*[b.animate.move_to(chip.get_center()).scale(0.05).set_opacity(0) for b in reversed(tower)], lag_ratio=0.1),
                      run_time=run(d, 0.25, 1.1))
            self.sfx("thud", gain=-4)
            self.play(FadeIn(chip, scale=0.5), Create(pins), FadeIn(cico), FadeIn(cglow), run_time=0.5)
            self.play(Flash(chip.get_center(), color=CYAN, flash_radius=1.9, line_length=0.4), FadeIn(clab, shift=UP * 0.2), run_time=0.6)
            self.play(LaggedStart(*[FadeIn(b, scale=1.2) for b in badges], lag_ratio=0.2), run_time=0.6)
            self.play(cglow.animate.set_opacity(0.35), run_time=0.6, rate_func=there_and_back)
        self.finish()



# ============================================================================================
@scene("orbit_arch")
class OrbitArch(NarratedScene):
    """A glowing core with modern architectures orbiting it."""

    beat_count = 1
    outro = 0.4

    class Params(SceneParams):
        heading: TranslatableStr
        core: TranslatableStr = "CORE"
        items: list[str] = []

    def construct(self):
        p = self.params
        FW, FH = self.frame_width, self.frame_height
        self.add(dust(FW, FH, n=60, seed=21, color=VIOLET))
        head = heading(self, p.heading)
        c0 = np.array([0, -0.4, 0])
        core = Circle(radius=0.85, stroke_color=AMBER, stroke_width=4).set_fill(PANEL, 1).move_to(c0)
        cg = glow(core, AMBER, layers=7, width=12, opacity=0.6)
        ct = self.text(p.core, size=44, color=AMBER, weight=BOLD).move_to(c0)
        orbit = Ellipse(width=9.6, height=4.0, stroke_color="#3a4560", stroke_width=1.5).move_to(c0)
        pal = [CYAN, VIOLET, PINK, MINT, AMBER, CYAN]
        chips = [pill(self, t, pal[i % len(pal)], size="caption") for i, t in enumerate(p.items)]
        ang = ValueTracker(0.0)
        n = len(chips)

        def pos(i):
            a = ang.get_value() + TAU * i / n + PI / 2
            return c0 + np.array([4.8 * math.cos(a), 2.0 * math.sin(a), 0])
        for i, ch in enumerate(chips):
            ch.move_to(pos(i))
        spokes = always_redraw(lambda: VGroup(*[DashedLine(c0, pos(i), stroke_color="#5b6478", stroke_width=1.5, dash_length=0.08).set_opacity(0.6)
                                                for i in range(n)]))
        spokes.set_z_index(-2)
        with self.narrate(0) as d:
            self.play(FadeIn(head), FadeIn(core, scale=0.4), FadeIn(cg), Write(ct), Create(orbit), run_time=0.6)
            for i, ch in enumerate(chips):
                ch.add_updater(lambda m, i=i: m.move_to(pos(i)))
            self.add(spokes)
            self.play(LaggedStart(*[FadeIn(ch, scale=0.6) for ch in chips], lag_ratio=max(0.1, min(0.6, (d * 0.55) / n / 0.6))),
                      ang.animate.increment_value(0.25), run_time=max(1.2, d * 0.6), rate_func=linear)
            self.play(ang.animate.increment_value(0.18 * max(0.5, d * 0.4 - 0.8)), run_time=max(0.5, d * 0.4 - 0.8), rate_func=linear)
            for ch in chips:
                ch.clear_updaters()
        self.finish()



# ============================================================================================
@scene("finale")
class Finale(NarratedScene):
    """A two-line verdict, then the project URL in a glowing pill, facts and credits.
    Beats: 1 the two lines, 2 URL + facts + credits."""

    beat_count = 2
    outro = 0.8

    class Params(SceneParams):
        line1: TranslatableStr = "<The verdict.>"
        line2: TranslatableStr = "<The payoff line.>"
        url: str = "github.com/<user>/<repo>"
        facts: list[str] = []
        credits: TranslatableStr = ""

    def construct(self):
        p = self.params
        FW, FH = self.frame_width, self.frame_height
        self.add(dust(FW, FH, n=100, seed=41))
        rings = VGroup(*[DashedVMobject(Circle(radius=r, stroke_color=c, stroke_width=1.5, stroke_opacity=0.35), num_dashes=n)
                         for r, c, n in ((3.2, CYAN, 70), (3.8, VIOLET, 90))]).move_to([0, 0.3, 0])
        rings[0].add_updater(lambda m, dt: m.rotate(0.12 * dt))
        rings[1].add_updater(lambda m, dt: m.rotate(-0.08 * dt))
        self.add(rings)
        l1 = self.text(p.line1, size=72, color="text", weight=BOLD).move_to([0, 0.9, 0])
        l2 = self.text(p.line2, size=60, color=AMBER, weight=BOLD).next_to(l1, DOWN, buff=0.35)
        g2 = glow(l2, AMBER, layers=5, width=5, opacity=0.3)
        with self.narrate(0) as d:
            self.play(FadeIn(l1, shift=UP * 0.3), run_time=0.6)
            self.wait(max(0.1, d * 0.4 - 0.6))
            self.sfx("chime", gain=-6)
            self.play(FadeIn(l2, scale=1.3), FadeIn(g2), run_time=0.6)
        urlp = pill(self, p.url, CYAN, "star", size="subtitle", role="code")
        ug = glow(urlp[0], CYAN, layers=6, width=10, opacity=0.5)
        url = VGroup(ug, urlp).move_to([0, -0.85, 0])
        if url.width > self.safe_area.x1 - self.safe_area.x0:
            url.scale_to_fit_width(self.safe_area.x1 - self.safe_area.x0)
        facts = VGroup(*[pill(self, f, MINT, size="caption") for f in p.facts]).arrange(RIGHT, buff=0.25).next_to(url, DOWN, buff=0.4)
        cr = self.text(p.credits or " ", size="small", color="dim")
        cr.move_to([0, self.safe_area.y0 + cr.height / 2, 0])
        with self.narrate(1) as d:
            self.play(VGroup(l1, l2, g2).animate.shift(UP * 0.8).scale(0.85), run_time=0.45)
            self.sfx("whoosh", gain=-5)
            self.play(FadeIn(url, shift=UP * 0.3), run_time=0.55)
            self.play(LaggedStart(*[FadeIn(f, shift=UP * 0.15) for f in facts], lag_ratio=0.2), FadeIn(cr), run_time=0.8)
            self.play(ug.animate.set_opacity(0.2), run_time=max(0.5, d - 1.9), rate_func=there_and_back)
        self.finish()

