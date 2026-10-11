"""Helpers for science / paper-explainer scenes: pictures, glow dots, star fields, twinkle,
rough blobs (rocks, cells), diatom shapes and run().

Copy into <project>/extensions/ and import with ``from .science_helpers import ...``."""
import math
import random

import numpy as np
from PIL import Image as PILImage

from vidgen.api import *


def load_picture(path):
    with PILImage.open(path) as im:
        return ImageMobject(np.array(im.convert("RGBA")))


def glow_dot(color, radius=0.09, layers=5, strength=0.35):
    """A bright dot with soft halo rings."""
    g = VGroup()
    for i in range(layers, 0, -1):
        r = radius * (1 + 1.1 * i)
        g.add(Circle(radius=r, stroke_width=0).set_fill(color, opacity=strength / (i + 0.6)))
    g.add(Circle(radius=radius, stroke_width=0).set_fill(WHITE, opacity=1.0))
    return g


def star_field(width, height, n=120, seed=3, color=WHITE):
    rng = random.Random(seed)
    stars = VGroup()
    for _ in range(n):
        r = rng.uniform(0.008, 0.028)
        s = Dot(radius=r, color=color).move_to([rng.uniform(-width / 2, width / 2), rng.uniform(-height / 2, height / 2), 0])
        s.set_opacity(rng.uniform(0.25, 0.9))
        stars.add(s)
    return stars


def twinkle(stars, seed=5):
    """Updater making a star field shimmer slowly (keeps the picture alive)."""
    rng = random.Random(seed)
    phases = [rng.uniform(0, TAU) for _ in stars]
    speeds = [rng.uniform(0.6, 1.8) for _ in stars]
    base = [s.get_fill_opacity() for s in stars]
    clock = {"t": 0.0}

    def upd(m, dt):
        clock["t"] += dt
        t = clock["t"]
        for s, p, v, b in zip(m, phases, speeds, base):
            s.set_opacity(max(0.05, min(1.0, b * (0.65 + 0.35 * math.sin(p + v * t)))))
    return upd


def rough_blob(radius=1.5, n=14, jitter=0.22, seed=1, squash=0.8):
    rng = random.Random(seed)
    pts = []
    for k in range(n):
        a = TAU * k / n
        r = radius * (1 + rng.uniform(-jitter, jitter))
        pts.append([r * math.cos(a), r * math.sin(a) * squash, 0])
    shape = Polygon(*pts)
    return shape.round_corners(radius * 0.12)


def centric_diatom(radius=1.0, rings=4, spokes=24, color="#8fe3ff", dot=0.035):
    """Top view of a centric diatom valve: outline, rings, radial rows of pores."""
    g = VGroup()
    outline = Circle(radius=radius, stroke_color=color, stroke_width=3)
    g.add(outline)
    pores = VGroup()
    for i in range(1, rings + 1):
        r = radius * i / (rings + 0.6)
        n = max(6, int(spokes * i / rings))
        for k in range(n):
            a = TAU * k / n + (i % 2) * PI / n
            pores.add(Dot(radius=dot * (0.7 + 0.3 * i / rings), color=color).move_to([r * math.cos(a), r * math.sin(a), 0]))
    g.add(pores)
    g.add(Dot(radius=dot * 1.6, color=color))
    return g


def pennate_diatom(length=1.4, width=0.38, color="#a7f3c0", ribs=11):
    g = VGroup()
    body = Ellipse(width=length, height=width, stroke_color=color, stroke_width=3)
    g.add(body)
    raphe = Line([-length * 0.42, 0, 0], [length * 0.42, 0, 0], stroke_color=color, stroke_width=2)
    g.add(raphe)
    for k in range(ribs):
        x = -length * 0.4 + length * 0.8 * k / (ribs - 1)
        h = width * 0.42 * math.sqrt(max(0.0, 1 - (x / (length / 2)) ** 2))
        g.add(Line([x, -h, 0], [x, h, 0], stroke_color=color, stroke_width=1.5, stroke_opacity=0.7))
    return g


def run(d, frac=0.6, cap=2.0, lo=0.3):
    return max(lo, min(cap, frac * d))
