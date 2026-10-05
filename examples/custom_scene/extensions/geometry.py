"""Helpers: draw a gear as a polygon with teeth."""
import numpy as np
from vidgen.api import *


def gear(teeth: int, module: float = 0.09, color="primary", fill_opacity=0.25) -> VGroup:
    """A gear with `teeth` teeth; radius grows with the tooth count (same tooth size)."""
    r = module * teeth / 2
    depth = module * 1.2
    pts = []
    for i in range(teeth):
        a = TAU * i / teeth
        step = TAU / teeth
        for frac, rad in ((0.0, r - depth / 2), (0.15, r + depth / 2), (0.5, r + depth / 2), (0.65, r - depth / 2)):
            ang = a + frac * step
            pts.append([rad * np.cos(ang), rad * np.sin(ang), 0])
    c = resolve_color(color)
    body = Polygon(*pts, color=c, stroke_width=2).set_fill(c, opacity=fill_opacity)
    hub = Circle(radius=max(0.08, r * 0.18), color=c, stroke_width=2)
    spoke = Line(ORIGIN, RIGHT * r * 0.8, color=c, stroke_width=3)
    return VGroup(body, hub, spoke)
