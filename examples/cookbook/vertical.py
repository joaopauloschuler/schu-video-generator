"""Helpers for 9:16 shorts (YouTube Shorts, Reels, TikTok): ``VScene``, a scene base whose content
band keeps clear of the platform UI (the top 12 % of the frame, and the caption band that a
bottom ``captions`` overlay reserves above the bottom 20 %), plus big text, chips, credits, glows,
image helpers and an idle "breathing" push so no frame ever freezes.

Copy into <project>/extensions/ and import with ``from .vertical import VScene, ...``.
Pair it with ``overlays: [{type: captions, style: karaoke, lift: 0.19}]`` (see short.template.yaml)."""
import math
import random
from contextlib import contextmanager

import numpy as np
from PIL import Image as PILImage

from vidgen.api import *

CYAN = "#4CC9F0"
VIOLET = "#A78BFA"
AMBER = "#FFD166"
MINT = "#5EEAD4"
PINK = "#F472B6"
ACCENT = "#FF6B8B"
NBLUE = "#7aa2ff"
GREEN = "#7CFC9A"
ROCK = "#2b303a"
ROCK_EDGE = "#6b7380"
GRAIN = ("#59616d", "#4a515c", "#6c7480", "#2a2e35", "#3d434e")


def run(d, frac=0.6, cap=2.0, lo=0.25):
    return max(lo, min(cap, frac * d))


def load_picture(path):
    with PILImage.open(path) as im:
        return ImageMobject(np.array(im.convert("RGBA")))


def cover(img, fw, fh, extra=1.02):
    img.scale(max(fw / img.width, fh / img.height) * extra)
    return img


def glow(mob, color, layers=5, width=9, opacity=0.45):
    g = VGroup()
    for i in range(layers, 0, -1):
        g.add(mob.copy().set_fill(opacity=0).set_stroke(color, width=width * i / layers * 2.2, opacity=opacity / (i * 1.6)))
    return g


def glow_dot(color, radius=0.08, layers=5, strength=0.4):
    g = VGroup()
    for i in range(layers, 0, -1):
        g.add(Circle(radius=radius * (1 + 1.2 * i), stroke_width=0).set_fill(color, opacity=strength / (i + 0.6)))
    g.add(Circle(radius=radius, stroke_width=0).set_fill(WHITE, opacity=1.0))
    return g


def rough_blob(radius=1.5, n=14, jitter=0.22, seed=1, squash=0.8):
    rng = random.Random(seed)
    pts = []
    for i in range(n):
        a = TAU * i / n
        r = radius * (1 + rng.uniform(-jitter, jitter))
        pts.append([r * math.cos(a), r * math.sin(a) * squash, 0])
    pts.append(pts[0])
    return VMobject().set_points_smoothly([np.array(p) for p in pts])


def star_field(width, height, n=120, seed=3):
    rng = random.Random(seed)
    g = VGroup()
    for _ in range(n):
        g.add(Dot([rng.uniform(-width / 2, width / 2), rng.uniform(-height / 2, height / 2), 0],
                  radius=rng.uniform(0.008, 0.03), color=WHITE).set_opacity(rng.uniform(0.25, 0.9)))
    return g


class VScene(NarratedScene):
    """Portrait scene base. ``top`` / ``bottom`` bound the content band: under the top 12 % of the
    frame, and above the captions (whose band the overlay reserves out of the safe area, which
    itself sits above the bottom 20 %). The idle tail of a beat gets a slow push so no frame
    freezes; mobjects marked ``_static`` or with updaters are left alone."""

    breathe = 1.015

    @property
    def top(self):
        return self.frame_height / 2 - 0.12 * self.frame_height - 0.05

    @property
    def bottom(self):
        return max(self.safe_area.y0, -self.frame_height / 2 + 0.2 * self.frame_height) + 0.05

    @property
    def mid(self):
        return (self.top + self.bottom) / 2

    def big(self, s, color="text", size="title", width=None):
        t = self.text(s, size=size, color=color, weight=BOLD)
        shrink_to_fit(t, width or self.safe_width)
        return t

    def plate(self, mob, opacity=0.6, buff=0.18):
        r = SurroundingRectangle(mob, buff=buff, corner_radius=0.14, stroke_width=0).set_fill(BLACK, opacity)
        return VGroup(r, mob)

    def chip(self, s, color, icon_name=None, size="body"):
        t = self.text(s, size=size, color=color)
        parts = [icon(icon_name, size=size, color=color), t] if icon_name else [t]
        g = VGroup(*parts).arrange(RIGHT, buff=0.15)
        shrink_to_fit(g, self.safe_width - 0.4)
        box = SurroundingRectangle(g, buff=0.16, corner_radius=0.14, color=color, stroke_width=3)
        box.set_fill("#10141f", 0.92)
        return VGroup(box, g)

    def credit(self, s):
        """A small image credit just under the top 12 % band (fades in with the picture)."""
        t = self.text(s, size="small", color="text")
        shrink_to_fit(t, self.safe_width)
        t.move_to([0, self.top - t.height / 2, 0])
        return VGroup(BackgroundRectangle(t, color=BLACK, fill_opacity=0.7, buff=0.07), t)

    @contextmanager
    def narrate(self, beat):
        with super().narrate(beat) as d:
            start = float(self.renderer.time)
            yield d
            rem = d + self.pad - (float(self.renderer.time) - start) - 0.1
            if rem > 0.8:
                mobs = [m for m in self.mobjects if isinstance(m, VMobject) and not getattr(m, "_static", False)
                        and not m.get_updaters() and not isinstance(m, TracedPath)]
                if mobs:
                    self._breath_n = getattr(self, "_breath_n", 0) + 1
                    k = self.breathe if self._breath_n % 2 else 1 / self.breathe
                    self.play(VGroup(*mobs).animate.scale(k), run_time=rem, rate_func=linear)
