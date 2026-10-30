"""Visual helpers for custom schu-video-generator scenes: a dark-tech palette, glow halos, glowing dots,
neurons, depth planes and stacks, drifting dust, pills, a header heading and run().

Copy into <project>/extensions/ and import with ``from .fx import ...``."""
import math
import random

import numpy as np
from PIL import Image as PILImage

from vidgen.api import *

CYAN = "#4CC9F0"
VIOLET = "#A78BFA"
AMBER = "#FFD166"
MINT = "#5EEAD4"
PINK = "#F472B6"
DEEP = "#0B0F1A"
PANEL = "#121829"


def run(d, frac=0.6, cap=2.0, lo=0.3):
    return max(lo, min(cap, frac * d))


def picture(path, height=None, width=None):
    with PILImage.open(path) as im:
        m = ImageMobject(np.array(im.convert("RGBA")))
    if height:
        m.height = height
    if width:
        m.width = width
    return m


def glow(mob, color, layers=6, width=10, opacity=0.5):
    """Soft halo behind a vector mobject: wide, faint copies of its outline."""
    g = VGroup()
    for i in range(layers, 0, -1):
        c = mob.copy().set_fill(opacity=0).set_stroke(color, width=width * i / layers * 2.2, opacity=opacity / (i * 1.6))
        g.add(c)
    return g


def glow_dot(color, radius=0.08, layers=5, strength=0.4):
    g = VGroup()
    for i in range(layers, 0, -1):
        g.add(Circle(radius=radius * (1 + 1.2 * i), stroke_width=0).set_fill(color, opacity=strength / (i + 0.6)))
    g.add(Circle(radius=radius, stroke_width=0).set_fill(WHITE, opacity=1.0))
    return g


def neuron(color, radius=0.16):
    core = Circle(radius=radius, stroke_color=color, stroke_width=3).set_fill(color, 0.18)
    halo = VGroup(*[Circle(radius=radius * (1 + 0.45 * i), stroke_width=0).set_fill(color, 0.10 / i) for i in range(1, 4)])
    return VGroup(halo, core)


def light(n, color, on=True):
    """Animate a neuron() lighting up (or back down)."""
    halo, core = n
    if on:
        return AnimationGroup(core.animate.set_fill(color, 0.95), halo.animate.set_opacity(1.0))
    return AnimationGroup(core.animate.set_fill(color, 0.18), halo.animate.set_opacity(0.35))


def plane(w, h, color, skew=0.45, grid=4, fill=0.10):
    """A feature map seen in perspective: a slanted parallelogram with a faint grid."""
    sx = skew * h
    pts = [[-w / 2, -h / 2, 0], [w / 2 - sx, -h / 2, 0], [w / 2, h / 2, 0], [-w / 2 + sx, h / 2, 0]]
    pts = [[x + 0, y, 0] for x, y, _ in pts]
    poly = Polygon(*pts, stroke_color=color, stroke_width=2).set_fill(color, fill)
    lines = VGroup()
    for k in range(1, grid):
        t = k / grid
        a = np.array(pts[0]) * (1 - t) + np.array(pts[3]) * t
        b = np.array(pts[1]) * (1 - t) + np.array(pts[2]) * t
        lines.add(Line(a, b, stroke_color=color, stroke_width=1, stroke_opacity=0.35))
        a = np.array(pts[0]) * (1 - t) + np.array(pts[1]) * t
        b = np.array(pts[3]) * (1 - t) + np.array(pts[2]) * t
        lines.add(Line(a, b, stroke_color=color, stroke_width=1, stroke_opacity=0.35))
    return VGroup(poly, lines)


def stack(n, w, h, color, step=(0.16, 0.11)):
    """n feature-map planes stacked in depth (back to front)."""
    g = VGroup()
    for i in range(n):
        p = plane(w, h, color, fill=0.07 + 0.05 * i)
        p.shift(np.array([-step[0] * (n - 1 - i), step[1] * (n - 1 - i), 0]))
        g.add(p)
    return g


def dust(width, height, n=70, seed=2, color=CYAN):
    """Drifting, twinkling specks that keep the background alive."""
    rng = random.Random(seed)
    g = VGroup()
    data = []
    for _ in range(n):
        d = Dot(radius=rng.uniform(0.008, 0.026), color=color)
        d.move_to([rng.uniform(-width / 2, width / 2), rng.uniform(-height / 2, height / 2), 0])
        base = rng.uniform(0.12, 0.5)
        d.set_opacity(base)
        g.add(d)
        data.append((rng.uniform(0, TAU), rng.uniform(0.5, 1.6), base, rng.uniform(0.03, 0.12)))
    clock = {"t": 0.0}

    def upd(m, dt):
        clock["t"] += dt
        t = clock["t"]
        for d, (ph, sp, b, vy) in zip(m, data, strict=False):
            d.shift(UP * vy * dt)
            if d.get_y() > height / 2:
                d.set_y(-height / 2)
            d.set_opacity(max(0.04, b * (0.6 + 0.4 * math.sin(ph + sp * t))))
    g.add_updater(upd)
    return g


def pill(sc, text, color, icon_name=None, size="caption", fill=PANEL, role=None):
    t = sc.text(text, size=size, color=color, role=role)
    parts = [icon(icon_name, size=size, color=color), t] if icon_name else [t]
    g = VGroup(*parts).arrange(RIGHT, buff=0.16)
    box = RoundedRectangle(width=g.width + 0.5, height=g.height + 0.32, corner_radius=min(0.3, (g.height + 0.32) / 2),
                           stroke_color=color, stroke_width=2).set_fill(fill, 0.92)
    box.move_to(g)
    return VGroup(box, g)


def heading(sc, text):
    h = sc.text(text, size="heading", color="text", weight=BOLD, role="heading")
    place(h, sc.region("header"), fit="none", align="top")
    return h


def flow(path_pts, color, n=1, radius=0.05):
    """A glowing particle travelling along a polyline."""
    path = VMobject().set_points_as_corners([np.array(p) for p in path_pts])
    dots = [glow_dot(color, radius=radius, layers=3, strength=0.5).move_to(path_pts[0]) for _ in range(n)]
    return path, dots
