"""Chromosome ideograms drawn (DESIGN.md §96.10): a chromosome is a column of G-bands from pter
(top) to qter, each arm a capsule (the centromere a constriction between them), dark bands in
four shades, heterochromatin grey, the stalks of the acrocentrics' short arms as two thin lines
and their satellites as small knobs. Derivative chromosomes are drawn from their segments, each
segment a separate group of bands so an edit can move it. The bands use fixed neutral greys in
every theme (G-banding is dark on light), the outline the theme's ink. Written against
``vidgen.api``; the band data are ``vidgen.genetics.karyotype``'s."""

from typing import Any

import numpy as np

from vidgen.api import *

kt = genetics.karyotype

PAPER = "#F2F0EA"
STAIN = "#232323"
GVAR = "#8E8E8E"
#: Width of a chromosome as a share of chromosome 1's drawn length.
WIDTH_SHARE = 0.105
#: Samples along a capsule's round end.
CAP_STEPS = 6


def stain_color(stain: str, tint: str | None = None) -> str:
    """The fill of a band (``tint``: material from another chromosome, mixed into pale bands)."""
    if stain.startswith("gpos"):
        share = int(stain[4:] or 100) / 100
        return mix_colors(STAIN, PAPER, 0.25 + 0.75 * share)
    if stain == "gvar":
        return GVAR
    if stain == "satellite":
        return mix_colors(STAIN, PAPER, 0.45)
    base = PAPER
    return mix_colors(tint, base, 0.42) if tint else base


class Runs:
    """The body runs of a drawn chromosome (stretches between a telomere / centromere / stalk),
    each a capsule: its top, bottom (scene y) and whether each end is round."""

    def __init__(self, runs: list[tuple[float, float]], half: float) -> None:
        self.runs = runs
        self.half = half

    def half_width(self, y: float) -> float:
        for top, bottom in self.runs:
            if bottom - 1e-9 <= y <= top + 1e-9:
                r = min(self.half, (top - bottom) / 2)
                if y > top - r:
                    d = y - (top - r)
                    return float(np.sqrt(max(0.0, r * r - d * d)) + (self.half - r))
                if y < bottom + r:
                    d = (bottom + r) - y
                    return float(np.sqrt(max(0.0, r * r - d * d)) + (self.half - r))
                return self.half
        return self.half

    def slice(self, x: float, y0: float, y1: float) -> list[np.ndarray]:
        """The outline of the capsule between heights ``y0`` > ``y1`` (a band)."""
        ys = list(np.linspace(y0, y1, CAP_STEPS + 2))
        left = [np.array([x - self.half_width(y), y, 0.0]) for y in ys]
        right = [np.array([x + self.half_width(y), y, 0.0]) for y in reversed(ys)]
        return left + right

    def outline(self, x: float, top: float, bottom: float) -> list[np.ndarray]:
        steps = 14
        ys = list(np.linspace(top, bottom, steps * 3))
        left = [np.array([x - self.half_width(y), y, 0.0]) for y in ys]
        right = [np.array([x + self.half_width(y), y, 0.0]) for y in reversed(ys)]
        return left + right + [left[0]]


def drawn_bands(copy: Any) -> list[tuple[int, Any, float, float]]:
    """The bands of a copy, top to bottom: (segment index, band, from, to) in Mb along the copy."""
    out = []
    at = 0.0
    for k, seg in enumerate(copy.segments):
        lo, hi = sorted((seg.a, seg.b))
        rev = seg.a > seg.b
        for band in kt.bands(seg.chrom):
            a, b = max(band.start, lo), min(band.end, hi)
            if b - a <= 1e-6:
                continue
            if rev:
                f, t = at + (seg.a - b), at + (seg.a - a)
            else:
                f, t = at + (a - seg.a), at + (b - seg.a)
            out.append((k, band, f, t))
        at += seg.length
    return sorted(out, key=lambda x: x[2])


class ChromosomeDrawing:
    """A copy (``vidgen.genetics.karyotype.Copy``) drawn with its top at ``top`` and its axis at
    ``x``: ``pieces`` (a VGroup of band polygons per segment), ``outline`` (the arms'
    capsules, stalks, satellite rings), ``mb_y`` (scene y of a position in Mb)."""

    def __init__(self, scene: Any, copy: Any, x: float, top: float, unit: float, width: float, ink: str,
                 tints: dict[str, str] | None = None, stroke: float = 2.0) -> None:
        self.copy = copy
        self.x, self.top, self.unit, self.width = x, top, unit, width
        half = width / 2
        bands = drawn_bands(copy)
        cen = copy.centromere
        stalk = {i for i, (_, b, _, _) in enumerate(bands) if b.stain == "stalk"}
        sat = {i for i, (_, b, _, _) in enumerate(bands) if b.stain == "satellite"}
        # body runs: split at the centromere and around stalks / satellites
        cuts = sorted({0.0, cen, copy.length} | {f for i, (_, _, f, t) in enumerate(bands) if i in stalk | sat}
                      | {t for i, (_, _, f, t) in enumerate(bands) if i in stalk | sat})
        runs = []
        for a, b in zip(cuts, cuts[1:]):
            if b - a < 1e-6:
                continue
            inside = [i for i, (_, _, f, t) in enumerate(bands) if f < b - 1e-6 and t > a + 1e-6]
            if inside and all(i in stalk | sat for i in inside):
                continue
            runs.append((self.mb_y(a), self.mb_y(b)))
        self.runs = Runs(runs, half)
        sat_runs = Runs([(self.mb_y(bands[i][2]), self.mb_y(bands[i][3])) for i in sorted(sat)], half * 0.78)
        # each segment's bands in the order of its source chromosome (pter first), so a moved or
        # inverted segment morphs band to band
        pieces: dict[int, list[tuple[float, Mobject]]] = {k: [] for k in range(len(copy.segments))}
        marks: list[Mobject] = []
        for i, (k, band, f, t) in enumerate(bands):
            y0, y1 = self.mb_y(f), self.mb_y(t)
            seg = copy.segments[k]
            tint = (tints or {}).get(seg.chrom) if seg.chrom != copy.slot else None
            if i in stalk:
                body = VGroup(*[Line(np.array([x + s * half * 0.28, y0, 0]), np.array([x + s * half * 0.28, y1, 0])) for s in (-1, 1)])
                body.set_stroke(ink, width=stroke * 0.8)
                pieces[k].append((band.start, body))
                continue
            src = sat_runs if i in sat else self.runs
            poly = Polygon(*src.slice(x, y0, y1)).set_stroke(width=0).set_fill(stain_color(band.stain, tint), opacity=1)
            pieces[k].append((band.start, poly))
        self.pieces = VGroup(*[VGroup(*[m for _, m in sorted(pieces[k], key=lambda p: p[0])]) for k in range(len(copy.segments))])
        for top_y, bottom_y in self.runs.runs:
            marks.append(VMobject().set_points_as_corners(self.runs.outline(x, top_y, bottom_y)).set_stroke(ink, width=stroke).set_fill(opacity=0))
        for top_y, bottom_y in sat_runs.runs:
            marks.append(VMobject().set_points_as_corners(sat_runs.outline(x, top_y, bottom_y)).set_stroke(ink, width=stroke * 0.9)
                         .set_fill(opacity=0))
        self.outline = VGroup(*marks)
        self.group = VGroup(self.pieces, self.outline)

    def mb_y(self, mb: float) -> float:
        return self.top - mb * self.unit

    @property
    def bottom(self) -> float:
        return self.mb_y(self.copy.length)

    def arm_middle(self, arm: str) -> float:
        cen = self.copy.centromere
        return self.mb_y(cen / 2) if arm == "p" else self.mb_y((cen + self.copy.length) / 2)


def segment_piece(scene: Any, chrom: str, lo: float, hi: float, x: float, top: float, unit: float, width: float, ink: str,
                  stroke: float = 2.0) -> VGroup:
    """The bands of ``chrom`` between ``lo`` and ``hi`` Mb drawn where they are on a normal
    ``chrom`` whose top is at ``top`` (the "before" place of a segment that moves), pter first."""
    normal = kt.normal_copy(chrom)
    drawing = ChromosomeDrawing(scene, normal, x, top, unit, width, ink, stroke=stroke)
    keep = []
    for (k, band, f, t), mob in zip(drawn_bands(normal), drawing.pieces[0]):
        if f >= lo - 1e-6 and t <= hi + 1e-6:
            keep.append(mob)
        elif t > lo + 1e-6 and f < hi - 1e-6:       # a band cut by the breakpoint: its part inside
            a, b = max(f, lo), min(t, hi)
            if band.stain == "stalk":
                keep.append(VGroup(*[Line(np.array([x + s * width * 0.14, drawing.mb_y(a), 0]), np.array([x + s * width * 0.14, drawing.mb_y(b), 0]))
                                     for s in (-1, 1)]).set_stroke(ink, width=stroke * 0.8))
                continue
            keep.append(Polygon(*drawing.runs.slice(x, drawing.mb_y(a), drawing.mb_y(b))).set_stroke(width=0)
                        .set_fill(stain_color(band.stain), opacity=1))
    return VGroup(*keep)
