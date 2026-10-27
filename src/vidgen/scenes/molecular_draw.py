"""Drawing helpers of the molecular genetics scenes (``mutation``, ``crispr``, ``dna_lab``;
DESIGN.md §96.13–96.15): base tiles in the base colours of Phase U's DNA drawings (A green, T red,
G blue, C yellow, letters dark on every theme), codon groups, amino-acid chips, cards.
Written against ``vidgen.api``."""

from typing import Any

import numpy as np

from vidgen.api import *

BASE_HUES = genetics.hgvs.BASE_HUES
#: Letters on base tiles: dark on the light hues, in every theme.
ON_TILE = "#14171C"


def _lighten(hex_color: str, amount: float) -> str:
    """``hex_color`` mixed with white (0 none, 1 white)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    mix = tuple(round(c + (255 - c) * amount) for c in (r, g, b))
    return "#%02X%02X%02X" % mix


#: Tile fills: the base hues lightened so a dark letter on them keeps 4.5:1 contrast.
TILE_FILLS = {b: _lighten(h, 0.34) for b, h in BASE_HUES.items()}


def _luminance(hex_color: str) -> float:
    def channel(x: int) -> float:
        v = x / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _darken(hex_color: str, amount: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % tuple(round(c * (1 - amount)) for c in (r, g, b))


def base_ink(background: str, base: str) -> str:
    """A base's colour as text on ``background``: its hue, lightened (on a dark background) or
    darkened (on a light one) until it reads at 4.5:1."""
    hue = BASE_HUES.get(base.upper(), "#9A9A9A")
    back = _luminance(background)
    shade = _lighten if back < 0.25 else _darken
    for amount in (0.0, 0.15, 0.3, 0.45, 0.6, 0.7):
        tone = shade(hue, amount)
        lo, hi = sorted((back, _luminance(tone)))
        if (hi + 0.05) / (lo + 0.05) >= 4.5:
            return tone
    return tone


class Letters:
    """Bold letters of one size, rendered once and copied (a sequence has many of the same)."""

    def __init__(self, scene: Any, height: float, size: float) -> None:
        self.scene, self.height, self.size = scene, height, size
        self.cache: dict[tuple[str, str], Mobject] = {}

    def get(self, text: str, color: str = ON_TILE, bold: bool = True) -> Mobject:
        key = (text, color + ("b" if bold else ""))
        if key not in self.cache:
            m = self.scene.markup(f"<b>{text}</b>" if bold else text, size=self.size, color=color)
            ref = self.scene.markup("<b>A</b>", size=self.size)
            m.scale(self.height / ref.height)
            self.cache[key] = m
        return self.cache[key].copy()


def base_tile(letters: Letters, base: str, u: float, lower: bool = False, ink: str | None = None) -> VGroup:
    """A base as a rounded tile in its colour with its letter; an intronic base (``lower``) as a
    pale tile outlined in its colour with a lower-case letter in ``ink`` (the theme's text)."""
    hue = BASE_HUES.get(base.upper(), "#9A9A9A")
    fill = TILE_FILLS.get(base.upper(), "#C9C9C9")
    tile = RoundedRectangle(width=u * 0.9, height=u * 1.08, corner_radius=u * 0.16)
    if lower:
        tile.set_fill(hue, opacity=0.16).set_stroke(hue, width=2)
        letter = letters.get(base.lower(), ink or ON_TILE)
    else:
        tile.set_fill(fill, opacity=1.0).set_stroke(width=0)
        letter = letters.get(base.upper())
    letter.move_to(tile)
    return VGroup(tile, letter)


def codon_box(tiles: list[Mobject], u: float, color: str, width: float = 1.6) -> RoundedRectangle:
    """The outline round a codon's tiles."""
    g = VGroup(*tiles)
    box = RoundedRectangle(width=g.width + u * 0.18, height=g.height + u * 0.18, corner_radius=u * 0.2)
    return box.move_to(g).set_stroke(color, width=width).set_fill(opacity=0)


def aa_chip(scene: Any, text: str, width: float, height: float, size: float, ink: str, fill: str, stroke: str,
            fill_opacity: float = 0.0, scale: float = 1.0) -> VGroup:
    """An amino acid's chip under its codon (three- or one-letter code, or Stop); the text at
    ``size`` × ``scale`` (one scale for every chip), narrower only when it would not fit."""
    chip = RoundedRectangle(width=width, height=height, corner_radius=height * 0.45)
    chip.set_fill(fill, opacity=fill_opacity).set_stroke(stroke, width=1.8)
    t = scene.markup(text, size=size, color=ink).scale(scale)
    if t.width > width * 0.86:
        t.scale(width * 0.86 / t.width)
    return VGroup(chip, t.move_to(chip))


def card_lines(scene: Any, lines: list[str], width: float, size: float, ink: str, head: str | None = None,
               head_size: float | None = None) -> VGroup:
    """A card: a bold head and wrapped lines, left-aligned."""
    from .bio_draw import text_block

    parts: list[Mobject] = []
    if head:
        parts.append(text_block(scene, f"<b>{head}</b>", width, head_size or size * 1.1, color=ink))
    for line in lines:
        parts.append(text_block(scene, line, width, size, color=ink))
    return VGroup(*parts).arrange(DOWN, buff=0.12, aligned_edge=LEFT)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
