"""Drawing the notation of Feynman diagrams (Phase Y, Step 238; DESIGN §99.6): lines along a
path (straight or a gentle arc) — fermions solid with an arrow on the fermion-number flow,
photons and W / Z wavy, gluons as coils, the Higgs boson dashed — vertex dots, particle labels
(antiparticle bars drawn as lines), hadron brackets. Used by ``scenes/feynman.py``."""

import math
from collections.abc import Callable
from typing import Any

import numpy as np

from vidgen.api import *

#: Wave of photon, W and Z lines: amplitude and wavelength (scene units); gluon coils: radius and
#: pitch; dashes of the Higgs line; the fermion arrowhead's length and width.
WAVE_AMPLITUDE = 0.075
WAVE_LENGTH = 0.3
COIL_RADIUS = 0.14
COIL_PITCH = 0.3
DASH_LENGTH = 0.16
ARROW_LENGTH = 0.24
ARROW_WIDTH = 0.2
LINE_WIDTH = 4.5
DOT_RADIUS = 0.08
#: Length of a hadron bracket's ticks.
BRACKET_TICK = 0.12
#: How far a line's decoration reaches out from its path (labels keep clear of it).
REACH = {"fermion": ARROW_WIDTH / 2, "photon": WAVE_AMPLITUDE, "W": WAVE_AMPLITUDE, "Z": WAVE_AMPLITUDE, "gluon": 2 * COIL_RADIUS, "higgs": 0.02}
MACRONS = ("̄", "̅")

Path = Callable[[float], np.ndarray]


def straight_or_arc(p0: np.ndarray, p1: np.ndarray, bend: float = 0.0) -> Path:
    """The path from ``p0`` to ``p1`` (parameter 0 … 1): straight, or bowed to the left by
    ``bend`` × the chord (a parabola close to an arc)."""
    d = p1 - p0
    left = np.array([-d[1], d[0], 0.0])

    def path(s: float) -> np.ndarray:
        return p0 + d * s + left * (4 * bend * s * (1 - s))

    return path


def reversed_path(path: Path) -> Path:
    return lambda s: path(1.0 - s)


def path_length(path: Path, n: int = 24) -> float:
    pts = [path(k / n) for k in range(n + 1)]
    return float(sum(np.linalg.norm(pts[k + 1] - pts[k]) for k in range(n)))


def tangent(path: Path, s: float) -> np.ndarray:
    h = 1e-3
    a, b = path(max(0.0, s - h)), path(min(1.0, s + h))
    d = b - a
    n = np.linalg.norm(d)
    return d / n if n else np.array([1.0, 0.0, 0.0])


def _normal(path: Path, s: float) -> np.ndarray:
    t = tangent(path, s)
    return np.array([-t[1], t[0], 0.0])


def _curve(points: list[np.ndarray], color: str, width: float) -> VMobject:
    curve = VMobject()
    curve.set_points_smoothly([np.asarray(p, dtype=float) for p in points])
    return curve.set_stroke(color, width=width).set_fill(opacity=0)


def path_mobject(path: Path, kind: str, color: str, width: float = LINE_WIDTH) -> VMobject:
    """The line itself, drawn from ``path(0)`` to ``path(1)`` (so ``Create`` draws it that way)."""
    length = path_length(path)
    if kind in ("photon", "W", "Z"):
        waves = max(2, round(length / WAVE_LENGTH))
        n = waves * 14
        pts = [path(k / n) + _normal(path, k / n) * WAVE_AMPLITUDE * math.sin(2 * math.pi * waves * k / n) for k in range(n + 1)]
        return _curve(pts, color, width)
    if kind == "gluon":
        loops = max(3, round(length / COIL_PITCH))
        n = loops * 18
        r = min(COIL_RADIUS, length / (2 * loops) * 2.2)
        # each turn swings back by more than the pitch, so every turn closes into a loop (a coil
        # reads as a coil, not as a wave, even in a thumbnail)
        squash = 1.0
        pts = []
        for k in range(n + 1):
            s = k / n
            phi = math.pi + s * (2 * math.pi * loops - math.pi)
            along = squash * r + s * (length - 2 * squash * r) + squash * r * math.cos(phi)
            u = min(1.0, max(0.0, along / length))
            pts.append(path(u) + _normal(path, u) * r * math.sin(phi))
        return _curve(pts, color, width * 0.8)
    line = VMobject()
    if _bent(path):
        line.set_points_smoothly([path(k / 24) for k in range(25)])
    else:
        line.set_points_as_corners([path(0.0), path(1.0)])
    line.set_stroke(color, width=width).set_fill(opacity=0)
    if kind == "higgs":
        return DashedVMobject(line, num_dashes=max(4, round(length / (2 * DASH_LENGTH))), dashed_ratio=0.55)
    return line


def _bent(path: Path) -> bool:
    a, m, b = path(0.0), path(0.5), path(1.0)
    return bool(np.linalg.norm(m - (a + b) / 2) > 1e-6)


def arrowhead(path: Path, s: float, forward: bool, color: str) -> VMobject:
    """A filled arrowhead on the path at ``s``, pointing along it (``forward``) or back."""
    t = tangent(path, s) * (1 if forward else -1)
    n = np.array([-t[1], t[0], 0.0])
    tip = path(s) + t * ARROW_LENGTH / 2
    back = path(s) - t * ARROW_LENGTH / 2
    head = Polygon(tip, back + n * ARROW_WIDTH / 2, back + t * ARROW_LENGTH * 0.18, back - n * ARROW_WIDTH / 2)
    return head.set_stroke(color, width=1.5).set_fill(color, opacity=1)


def particle_label(scene: Any, particle: Any, star: bool, size: float, color: str) -> VGroup:
    """The particle's symbol (Pango markup) with an antiparticle's bar drawn as a line over the
    first glyph (a combining macron sits off-centre on ν and Σ); ``star`` adds the off-shell ``*``."""
    markup = particle.markup
    barred = any(m in markup for m in MACRONS)
    for m in MACRONS:
        markup = markup.replace(m, "")
    if star:
        markup += "<sup>*</sup>"
    text = scene.markup(markup, size=size, color=color)
    group = VGroup(text)
    if barred:
        glyph = text[0]
        lift = 0.16 * glyph.height + 0.03
        bar = Line(glyph.get_corner(UL) + UP * lift, glyph.get_corner(UR) + UP * lift)
        group.add(bar.set_stroke(color, width=max(2.0, 0.09 * glyph.height * 100)))
    return group


def bracket(p_low: np.ndarray, p_high: np.ndarray, toward: np.ndarray, color: str, tick: float | None = None) -> VMobject:
    """A square bracket from ``p_low`` to ``p_high`` with its ticks pointing ``toward`` (unit)."""
    tick = BRACKET_TICK if tick is None else tick
    br = VMobject()
    br.set_points_as_corners([p_low + toward * tick, p_low, p_high, p_high + toward * tick])
    return br.set_stroke(color, width=3).set_fill(opacity=0)


def time_arrow(scene: Any, start: np.ndarray, direction: np.ndarray, length: float, size: float) -> VGroup:
    """``time →`` (or ``↑``): an arrow from ``start`` along ``direction`` with the word ``time``."""
    end = start + direction * length
    arrow = Arrow(start, end, buff=0, stroke_width=3, max_tip_length_to_length_ratio=0.16)
    arrow.set_color(scene.theme.color("dim"))
    word = scene.text("time", size=size, color="dim")
    if abs(direction[0]) > abs(direction[1]):
        word.next_to(arrow, LEFT, buff=0.12)
    else:
        word.next_to(arrow, RIGHT, buff=0.1)
    return VGroup(arrow, word)


def dot(point: np.ndarray, color: str, radius: float = DOT_RADIUS) -> Dot:
    return Dot(point, radius=radius, color=color)
