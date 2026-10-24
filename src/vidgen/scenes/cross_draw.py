"""Flat pictures for the ``cross`` scene (DESIGN.md §96.7): phenotype glyphs (a pea round or
wrinkled, yellow or green; a flower; a fruit fly's eye or the whole fly with its body colour and
wings; an animal's coat; a feather; a squash fruit; a blood drop with its ABO group; a seed
capsule; an affected / unaffected mark; a colour swatch), the ♀ / ♂ symbols, a parent's
homologous chromosomes with their alleles, and gamete chips. Original simple drawings, sized in
scene units. Written against ``vidgen.api``; what to draw comes from ``vidgen.genetics.glyphs``."""

import math
from typing import Any

import numpy as np

from vidgen.api import *

#: Colours used when a glyph has no colour of its own.
NEUTRAL = {"pea": "#D7CB6E", "flower": "#C9A0DC", "fruit": "#E5D49A", "coat": "#8A6B4E", "feather": "#B5651D",
           "capsule": "#7DAF4C", "swatch": "#A9A9A9", "fly_body": "#B89A72", "fly_eye": "#D9433B"}
FLY_EYE_COLOURS = ("red", "white", "sepia", "brown", "scarlet", "cinnabar", "orange", "pink")


def _outline(fill: str, ink: str) -> str:
    return mix_colors(fill, ink, 0.55)


def _blob(radius: float, wobble: float, lobes: int, squash: float = 1.0) -> VMobject:
    pts = []
    for k in range(72):
        a = 2 * math.pi * k / 72
        r = radius * (1 + wobble * math.sin(lobes * a) + 0.5 * wobble * math.sin((2 * lobes + 1) * a + 0.7))
        pts.append(np.array([r * math.cos(a), r * math.sin(a) * squash, 0.0]))
    shape = VMobject().set_points_smoothly([*pts, pts[0]])
    return shape


def _filled(shape: VMobject, fill: str, ink: str, width: float = 1.6, opacity: float = 1.0) -> VMobject:
    return shape.set_fill(fill, opacity=opacity).set_stroke(_outline(fill, ink), width=width)


def _pea(attrs: dict[str, str], s: float, ink: str) -> VGroup:
    fill = attrs.get("colour_hex", NEUTRAL["pea"])
    body = _blob(s * 0.45, 0.07, 7) if attrs.get("shape") == "wrinkled" else Circle(radius=s * 0.45)
    _filled(body, fill, ink)
    shine = Ellipse(width=s * 0.22, height=s * 0.12).set_fill(WHITE, opacity=0.35).set_stroke(width=0)
    shine.rotate(0.6).move_to(np.array([-s * 0.15, s * 0.17, 0.0]))
    parts = [body, shine]
    if attrs.get("shape") == "wrinkled":
        for a in (0.4, 2.3, 4.2):
            crease = ArcBetweenPoints(np.array([math.cos(a), math.sin(a), 0]) * s * 0.28,
                                      np.array([math.cos(a + 0.9), math.sin(a + 0.9), 0]) * s * 0.2, angle=0.8)
            parts.append(crease.set_stroke(_outline(fill, ink), width=1.2, opacity=0.8))
    return VGroup(*parts)


def _flower(attrs: dict[str, str], s: float, ink: str) -> VGroup:
    fill = attrs.get("colour_hex", NEUTRAL["flower"])
    petals = []
    for k in range(5):
        a = math.pi / 2 + 2 * math.pi * k / 5
        p = Ellipse(width=s * 0.3, height=s * 0.44)
        p.rotate(a - math.pi / 2).move_to(np.array([math.cos(a), math.sin(a), 0.0]) * s * 0.24)
        petals.append(_filled(p, fill, ink, 1.4))
    centre_fill = "#8A5A35" if attrs.get("colour") == "yellow" else "#F2C230"
    centre = _filled(Circle(radius=s * 0.11), centre_fill, ink, 1.2)
    return VGroup(*petals, centre)


def _eye(attrs: dict[str, str], s: float, ink: str) -> VGroup:
    colour = attrs.get("colour", "")
    fill = attrs.get("colour_hex", NEUTRAL["fly_eye"])
    if colour in FLY_EYE_COLOURS:            # a fruit fly's head with its compound eye
        head = _filled(Circle(radius=s * 0.42), NEUTRAL["fly_body"], ink)
        eye = _filled(Ellipse(width=s * 0.46, height=s * 0.56), fill, ink, 1.4).shift(RIGHT * s * 0.1)
        facets = VGroup(*[Dot(radius=s * 0.018, color=mix_colors(fill, WHITE, 0.5)).move_to(eye.get_center() + np.array([dx, dy, 0]) * s)
                          for dx in (-0.1, 0.0, 0.1) for dy in (-0.13, 0.0, 0.13)])
        return VGroup(head, eye, facets)
    white = _filled(Ellipse(width=s * 0.9, height=s * 0.48), "#F4F1EA", ink, 1.4)
    iris = _filled(Circle(radius=s * 0.17), fill, ink, 1.2)
    pupil = Dot(radius=s * 0.07, color="#1E1C1A")
    return VGroup(white, iris, pupil)


def _fly(attrs: dict[str, str], s: float, ink: str) -> VGroup:
    body_fill = attrs.get("body_hex", NEUTRAL["fly_body"])
    eye_fill = attrs.get("eye_hex", NEUTRAL["fly_eye"])
    wing_parts = []
    for side in (1, -1):
        if attrs.get("wings") == "vestigial":
            w = _blob(s * 0.08, 0.25, 3).set_fill(WHITE, opacity=0.6).set_stroke(ink, width=1, opacity=0.6)
            w.move_to(np.array([side * s * 0.14, s * 0.02, 0.0]))
        else:
            w = Ellipse(width=s * 0.24, height=s * 0.62).set_fill(WHITE, opacity=0.45).set_stroke(ink, width=1, opacity=0.6)
            w.rotate(-side * 0.35).move_to(np.array([side * s * 0.17, -s * 0.12, 0.0]))
        wing_parts.append(w)
    abdomen = _filled(Ellipse(width=s * 0.3, height=s * 0.46), body_fill, ink, 1.3).move_to(np.array([0, -s * 0.16, 0]))
    stripes = VGroup(*[Line(np.array([-s * 0.13, y, 0]), np.array([s * 0.13, y, 0])).set_stroke(_outline(body_fill, ink), width=1.2, opacity=0.7)
                       for y in (-s * 0.2, -s * 0.28)])
    thorax = _filled(Circle(radius=s * 0.13), body_fill, ink, 1.3).move_to(np.array([0, s * 0.12, 0]))
    head = _filled(Circle(radius=s * 0.1), body_fill, ink, 1.3).move_to(np.array([0, s * 0.31, 0]))
    eyes = VGroup(*[_filled(Circle(radius=s * 0.055), eye_fill, ink, 1.0).move_to(np.array([side * s * 0.08, s * 0.33, 0])) for side in (1, -1)])
    return VGroup(*wing_parts, abdomen, stripes, thorax, head, eyes)


def _coat(attrs: dict[str, str], s: float, ink: str) -> VGroup:
    colour = attrs.get("colour", "")
    fill = attrs.get("colour_hex", NEUTRAL["coat"])
    points = "#4A3B33" if colour == "himalayan" else fill
    ears = VGroup(*[_filled(Circle(radius=s * 0.16), points, ink, 1.3).move_to(np.array([side * s * 0.27, s * 0.3, 0])) for side in (1, -1)])
    inner = VGroup(*[Circle(radius=s * 0.08).set_fill("#E8A3A0", opacity=0.8).set_stroke(width=0).move_to(e) for e in ears])
    face = _filled(Ellipse(width=s * 0.74, height=s * 0.66), fill, ink, 1.5).shift(DOWN * s * 0.05)
    if colour == "agouti":
        ticks = VGroup(*[Line(np.array([x, -s * 0.05, 0]), np.array([x + s * 0.04, s * 0.12, 0])).set_stroke("#5C452D", width=1.2, opacity=0.7)
                         for x in (-s * 0.2, -s * 0.06, s * 0.08, s * 0.2)])
    else:
        ticks = VGroup()
    eye_fill = "#D9433B" if colour in ("albino",) else ("#F4F1EA" if colour in ("black", "full colour", "full color", "ebony", "chocolate") else "#1E1C1A")
    eyes = VGroup(*[Dot(radius=s * 0.045, color=eye_fill).move_to(np.array([side * s * 0.14, s * 0.0, 0])) for side in (1, -1)])
    nose = Dot(radius=s * 0.05, color=points if colour == "himalayan" else "#B5666A").move_to(np.array([0, -s * 0.15, 0]))
    return VGroup(ears, inner, face, ticks, eyes, nose)


def _feather(attrs: dict[str, str], s: float, ink: str) -> VGroup:
    fill = attrs.get("colour_hex", NEUTRAL["feather"])
    vane = _filled(Ellipse(width=s * 0.36, height=s * 0.9), fill, ink, 1.4)
    shaft = Line(np.array([0, -s * 0.5, 0]), np.array([0, s * 0.42, 0])).set_stroke(_outline(fill, ink), width=1.6)
    barbs = VGroup(*[Line(np.array([0, y, 0]), np.array([side * s * 0.14, y + s * 0.08, 0])).set_stroke(_outline(fill, ink), width=1, opacity=0.7)
                     for y in (-s * 0.2, 0.0, s * 0.2) for side in (1, -1)])
    return VGroup(vane, shaft, barbs).rotate(-0.5)


def _fruit(attrs: dict[str, str], s: float, ink: str) -> VGroup:
    fill = attrs.get("colour_hex", NEUTRAL["fruit"])
    shape = attrs.get("shape", "sphere")
    if shape == "disc":
        body: VMobject = _blob(s * 0.47, 0.06, 10, squash=0.55)
    elif shape == "long":
        body = Ellipse(width=s * 0.38, height=s * 0.95)
    else:
        body = Circle(radius=s * 0.4)
    _filled(body, fill, ink)
    stem = Rectangle(width=s * 0.07, height=s * 0.14).set_fill("#6B7F3A", opacity=1).set_stroke(width=0)
    stem.next_to(body, UP, buff=-s * 0.03)
    return VGroup(body, stem)


def _blood(attrs: dict[str, str], s: float, ink: str, scene: Any) -> VGroup:
    r = s * 0.32
    pts = [np.array([0, s * 0.48, 0])]
    for k in range(0, 37):
        a = math.radians(20 - 220 * k / 36)
        pts.append(np.array([r * math.cos(a), -s * 0.12 + r * math.sin(a), 0]))
    drop = VMobject().set_points_smoothly([*pts, pts[0]])
    drop.make_smooth()
    _filled(drop, "#C62F3A", ink)
    group = attrs.get("group", "")
    letter = scene.markup(f"<b>{group}</b>", size=48, color="#FFFFFF")
    letter.scale_to_fit_height(s * (0.26 if len(group) == 1 else 0.22)).move_to(np.array([0, -s * 0.13, 0]))
    return VGroup(drop, letter)


def _capsule(attrs: dict[str, str], s: float, ink: str) -> VGroup:
    fill = NEUTRAL["capsule"]
    if attrs.get("shape") == "triangular":
        body: VMobject = VMobject().set_points_as_corners([np.array([-s * 0.4, s * 0.32, 0]), np.array([0, s * 0.18, 0]),
                                                           np.array([s * 0.4, s * 0.32, 0]), np.array([0, -s * 0.42, 0]),
                                                           np.array([-s * 0.4, s * 0.32, 0])])
    else:
        body = Ellipse(width=s * 0.46, height=s * 0.72).shift(UP * s * 0.04)
    _filled(body, fill, ink)
    stalk = Line(body.get_bottom(), body.get_bottom() + DOWN * s * 0.12).set_stroke(_outline(fill, ink), width=1.6)
    return VGroup(body, stalk)


def _status(attrs: dict[str, str], s: float, ink: str, accent: str) -> VGroup:
    square = Square(side_length=s * 0.7)
    if attrs.get("affected") == "yes":
        return VGroup(square.set_fill(accent, opacity=1).set_stroke(ink, width=2))
    return VGroup(square.set_fill(opacity=0).set_stroke(ink, width=2))


def _swatch(attrs: dict[str, str], s: float, ink: str, fallback: str) -> VGroup:
    fill = attrs.get("colour_hex", fallback)
    return VGroup(_filled(RoundedRectangle(width=s * 0.7, height=s * 0.7, corner_radius=s * 0.12), fill, ink))


def glyph(scene: Any, spec: Any, size: float, fallback: str) -> VGroup:
    """One phenotype picture about ``size`` units high (``spec``: a ``GlyphSpec``)."""
    ink = scene.theme.color("text")
    a, s = spec.attrs, size
    subject = spec.subject
    if subject == "pea":
        g = _pea(a, s, ink)
    elif subject == "flower":
        g = _flower(a, s, ink)
    elif subject == "eye":
        g = _eye(a, s, ink)
    elif subject == "fly":
        g = _fly(a, s, ink)
    elif subject == "coat":
        g = _coat(a, s, ink)
    elif subject == "feather":
        g = _feather(a, s, ink)
    elif subject == "fruit":
        g = _fruit(a, s, ink)
    elif subject == "blood":
        g = _blood(a, s, ink, scene)
    elif subject == "capsule":
        g = _capsule(a, s, ink)
    elif subject == "status":
        g = _status(a, s, ink, scene.theme.color("accent"))
    else:
        g = _swatch(a, s, ink, fallback)
    if g.height > size:
        g.scale(size / g.height)
    return g


def glyph_row(scene: Any, specs: Any, size: float, fallback: str) -> VGroup:
    """The pictures of one class side by side."""
    return VGroup(*[glyph(scene, spec, size, fallback) for spec in specs]).arrange(RIGHT, buff=size * 0.12)


def sex_symbol(sex: str, size: float, color: str) -> VGroup:
    """♀ (a circle over a cross) or ♂ (a circle with an arrow), drawn, ``size`` units high."""
    r = size * 0.3
    width = max(1.5, size * 5)
    if sex == "female":
        ring = Circle(radius=r).set_stroke(color, width=width).move_to(np.array([0, size * 0.2, 0]))
        stem = Line(np.array([0, size * 0.2 - r, 0]), np.array([0, -size * 0.5, 0])).set_stroke(color, width=width)
        bar = Line(np.array([-size * 0.18, -size * 0.3, 0]), np.array([size * 0.18, -size * 0.3, 0])).set_stroke(color, width=width)
        return VGroup(ring, stem, bar)
    c = np.array([-size * 0.12, -size * 0.12, 0])
    ring = Circle(radius=r).set_stroke(color, width=width).move_to(c)
    d = np.array([1, 1, 0]) / math.sqrt(2)
    start = c + d * r
    tip = c + d * size * 0.72
    shaft = Line(start, tip).set_stroke(color, width=width)
    head = VGroup(Line(tip, tip - np.array([size * 0.24, 0, 0])), Line(tip, tip - np.array([0, size * 0.24, 0]))).set_stroke(color, width=width)
    return VGroup(ring, shaft, head)


def homologue_colors(scene: Any) -> tuple[str, str]:
    """The colours of a parent's two homologues (and of the alleles coming from each)."""
    return scene.theme.color("primary"), scene.theme.color("accent")


def colored_markup(alleles: Any, colors: tuple[str, str], ink: str, sep: str) -> str:
    """A gamete's alleles as markup, each in the colour of the homologue it came from."""
    parts = []
    for a in alleles:
        color = ink if a.source is None else colors[a.source]
        parts.append(f'<span foreground="{color}">{a.markup}</span>')
    return sep.join(parts)


def chromosome_pairs(scene: Any, system: Any, genotype: Any, height: float, size: float) -> VGroup:
    """A parent's homologous chromosomes side by side, pair by pair (each linkage group, then
    the sex chromosomes), each allele as a band with its symbol beside it, the homologues in
    their two colours."""
    ink = scene.theme.color("text")
    colors = homologue_colors(scene)
    bar_w = height * 0.11
    pairs = []
    groups = [(grp.loci, pair) for grp, pair in zip(system.groups, genotype.autosomes)]
    for loci, (h1, h2) in groups:
        pairs.append(_pair(scene, [list(h1), list(h2)], [None, None], height, bar_w, size, colors, ink))
    if genotype.sex_chromosomes is not None:
        a, b = genotype.sex_chromosomes
        pairs.append(_pair(scene, [list(a.alleles), list(b.alleles)], [a.letter, b.letter], height, bar_w, size, colors, ink))
    for m in genotype.mito:
        t = scene.markup(f"mt: {genetics.symbol_markup(m)}", size=size, color=ink)
        pairs.append(VGroup(VGroup(t)))
    group = VGroup(*pairs).arrange(RIGHT, buff=height * 0.28, aligned_edge=DOWN)
    return group


def _pair(scene: Any, alleles: list[list[str]], letters: list[str | None], height: float, bar_w: float, size: float,
          colors: tuple[str, str], ink: str) -> VGroup:
    """Two homologues: ``VGroup(first, second)``, each its bar, bands, allele labels (and X / Y)."""
    homologues = []
    for k, (alls, letter) in enumerate(zip(alleles, letters)):
        parts: list[Mobject] = []
        h = height * (0.62 if letter == "Y" else 1.0)
        bar = RoundedRectangle(width=bar_w, height=h, corner_radius=bar_w / 2).set_fill(colors[k], opacity=0.9).set_stroke(width=0)
        x = (-1 if k == 0 else 1) * bar_w * 1.15
        bar.move_to(np.array([x, h / 2, 0.0]))
        items: list[Mobject] = [bar]
        n = len(alls)
        for j, allele in enumerate(alls):
            y = h * (0.78 - 0.56 * (j / max(1, n - 1))) if n > 1 else h * 0.6
            band = Line(np.array([x - bar_w / 2, y, 0]), np.array([x + bar_w / 2, y, 0])).set_stroke(scene.theme.background, width=2)
            label = scene.markup(genetics.symbol_markup(allele), size=size, color=colors[k])
            label.next_to(np.array([x, y, 0]), LEFT if k == 0 else RIGHT, buff=bar_w * 1.1)
            items += [band, label]
        if letter:
            t = scene.markup(letter, size=size * 0.8, color=ink).next_to(bar, DOWN, buff=bar_w * 0.6)
            items.append(t)
        parts.extend(items)
        homologues.append(VGroup(*parts))
    return VGroup(*homologues)


def chip_text(scene: Any, view: Any, size: float, sep: str) -> Mobject:
    """A gamete's alleles as text, each in the colour of the homologue it came from."""
    ink = scene.theme.color("text")
    return scene.markup(colored_markup(view.alleles, homologue_colors(scene), ink, sep), size=size, color=ink)


def gamete_chip(scene: Any, view: Any, radius: float, size: float, ring: str, sep: str, max_width: float | None = None) -> VGroup:
    """A gamete as a small round cell (a pill when its alleles are long: b⁺ vg⁺) with its
    alleles in their homologues' colours, at most ``max_width`` wide."""
    bg = scene.theme.background
    text = chip_text(scene, view, size, sep)
    if text.height > radius * 1.25:
        text.scale(radius * 1.25 / text.height)
    width = max(2 * radius, text.width + radius * 0.9)
    if max_width is not None and width > max_width:
        text.scale(max(0.2, (max_width - radius * 0.9)) / text.width)
        width = max_width
    disc = RoundedRectangle(width=width, height=2 * radius, corner_radius=radius * 0.999)
    disc.set_fill(mix_colors(ring, bg, 0.12), opacity=1).set_stroke(ring, width=2.2)
    text.move_to(disc)
    return VGroup(disc, text)


__all__ = ["chip_text", "chromosome_pairs", "colored_markup", "gamete_chip", "glyph", "glyph_row", "homologue_colors", "sex_symbol"]
