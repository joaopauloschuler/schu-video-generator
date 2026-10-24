"""The shapes molecules are drawn with, as plain geometry in nanometres (DESIGN.md §95.9): the
DNA double helix (two antiparallel backbones round base pairs, major and minor grooves, 5′/3′
ends), RNAs, the nucleosome, chromatin, proteins and membrane proteins, small molecules and
ions, modification markers. A :class:`Glyph` is a list of primitives (filled or stroked Bézier
outlines, texts in Pango markup) in a local frame — for a membrane protein x along the membrane,
y towards its exoplasmic side, the bilayer's mid-plane at y = 0 — with named anchors (the
points labels name) and facts (what the tests check: the strands' directions, the side F₁ is
on). Renderers place and turn glyphs; the model never imports manim."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache

from vidgen.errors import VidgenError

from .curves import Cubic, arc, line, polygon, shape_curves, smooth, transform
from .geometry import Capsule, Ellipse, Point, RoundedBox
from .model import did_you_mean
from .molecules import (
    BILAYER_NM, C_RING, CARRIER_MODES, DNA_RISE, DNA_WIDTH, GATINGS, ION_HUES, IONS, MOLECULES, NUCLEOSOME_BP, NUCLEOSOME_TURNS, RRNA_TYPES,
    TRANSPORTERS, molecule_kind, pitch, protein_size, pump_type,
)
from .names import MODIFICATIONS, check_modification, histone_mark
from .notation import chem_markup
from .sequences import AMINO_ACIDS, check_sequence, check_trna, complement

#: Base colours (a common textbook scheme).
BASE_HUES = {"A": "#4FA35E", "T": "#D9534F", "U": "#E07A5F", "G": "#3F6FC0", "C": "#E8B730"}
HISTONE_HUES = {"H2A": "#E0A030", "H2B": "#D9734F", "H3": "#5E7FC0", "H4": "#4FA38E"}
PHOSPHATE_HUE, SUGAR_HUE, GLYCAN_HUE, LIPID_HUE = "#E8B730", "#C9A86A", "#4FA35E", "#B08A5A"
#: Text colours: the theme's text colour, and a dark ink for text on a filled shape.
TEXT, ON = "text", "on"


@dataclass(frozen=True)
class Prim:
    """A piece of a glyph: Bézier ``curves`` (nm, local frame) filled with ``fill`` (a hue;
    ``None``: not filled) at ``tone`` (``solid``, ``fill``: lighter, ``light``) and outlined
    with the ink of ``stroke`` ``px`` pixels wide (or ``nm`` wide when wider on screen); or a
    ``text`` (Pango markup) of ``height`` nm centred at ``at`` in ``fill`` (``text``: the
    theme's text colour). ``detail``: drawn only when the glyph is large on screen; ``z``: its
    order within the glyph."""

    curves: tuple[Cubic, ...] = ()
    fill: str | None = None
    tone: str = "solid"
    stroke: str | None = None
    px: float = 0.0
    nm: float = 0.0
    text: str = ""
    at: Point = (0.0, 0.0)
    height: float = 0.0
    detail: bool = False
    z: float = 0.0


@dataclass(frozen=True)
class Glyph:
    """A molecule's drawing in its local frame (nm): ``prims``, ``anchors`` (``name: (label
    markup, point)``), ``bounds``, the ``sites`` where modification markers may go (point,
    outward normal) and ``facts`` about it."""

    kind: str
    prims: tuple[Prim, ...]
    anchors: dict[str, tuple[str, Point]]
    bounds: tuple[float, float, float, float]
    sites: tuple[tuple[Point, Point], ...] = ()
    facts: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MoleculeSpec:
    """One molecule as the model reads it (both scenes give these): its ``kind`` and options —
    ``state``; DNA ``bp``, ``sequence`` (5′→3′ of the top strand; mRNA: its sequence),
    ``letters``; tRNA ``anticodon`` (5′→3′), ``amino_acid``, ``style`` (cloverleaf or
    l_shape); rRNA ``rrna`` (18S…); nucleosome ``marks`` (histone marks: H3K4me3);
    chromatin ``nucleosomes``; protein ``domains``, ``mass`` (kDa); receptors' ``ligand``;
    channels' ``gating`` and ``ion``; carriers' ``mode``, ``substrates``, ``moves`` (in /
    out); ATP synthase ``c_subunits``; mRNA ``cap`` and ``tail``; an ion's ``ion``;
    ``modifications`` ((mark, residue or None), …); the ``membrane`` it is in (for defaults);
    ``where`` names it in errors; a carrier's ``ratio`` (how many of each substrate per cycle)
    or a named ``transporter`` (``sglt1``: its mode, substrates, moves and ratio); ``bare``: the
    protein alone, without its bound solutes, flow arrows and stoichiometry (a transport
    animation moves those itself)."""

    kind: str
    state: str | None = None
    bp: int | None = None
    sequence: str | None = None
    letters: bool | None = None
    anticodon: str | None = None
    amino_acid: str | None = None
    style: str | None = None
    rrna: str | None = None
    marks: tuple[str, ...] = ()
    nucleosomes: int | None = None
    domains: tuple[str, ...] = ()
    mass: float | None = None
    ligand: bool | None = None
    gating: str | None = None
    ion: str | None = None
    mode: str | None = None
    substrates: tuple[str, ...] = ()
    moves: tuple[str, ...] = ()
    c_subunits: int | None = None
    cap: bool | None = None
    tail: bool | None = None
    modifications: tuple[tuple[str, ...], ...] = ()
    membrane: str | None = None
    where: str = ""
    ratio: tuple[int, ...] = ()
    transporter: str | None = None
    bare: bool = False


#: Which kinds take each option (others refuse it).
OPTION_KINDS: dict[str, tuple[str, ...]] = {
    "bp": ("dna",), "sequence": ("dna", "mrna"), "letters": ("dna", "mrna"), "anticodon": ("trna",), "amino_acid": ("trna",),
    "style": ("trna",), "rrna": ("rrna",), "marks": ("nucleosome", "chromatin"), "nucleosomes": ("chromatin",),
    "domains": ("protein",), "mass": ("protein",), "ligand": ("gpcr", "ion_channel"), "gating": ("ion_channel",),
    "ion": ("ion_channel", "ion"), "mode": ("carrier",), "substrates": ("carrier", "abc_transporter"), "moves": ("carrier", "abc_transporter"),
    "c_subunits": ("atp_synthase",), "cap": ("mrna",), "tail": ("mrna",), "ratio": ("carrier",), "transporter": ("carrier",),
}
#: Ions move this way through channels by their usual gradients (in: to the cytosolic side).
ION_FLOW = {"K+": "out", "Na+": "in", "Ca2+": "in", "Cl-": "in", "H+": "in", "Mg2+": "in"}


def check_molecule(spec: MoleculeSpec) -> MoleculeSpec:
    """``spec`` with its options checked for its kind (an option of another kind, a state the
    kind has not, a sequence with a wrong base, an anticodon that does not read the amino
    acid's codons, a modification on a residue it never goes on, a symport whose solutes move
    opposite ways…). Raises :class:`VidgenError` naming ``spec.where``."""
    where = spec.where or f"molecule {spec.kind}"
    kind = molecule_kind(spec.kind, where)
    for name, kinds in OPTION_KINDS.items():
        value = getattr(spec, name)
        if value not in (None, ()) and spec.kind not in kinds:
            raise VidgenError(f"{where}: {name} is for {' and '.join(kinds)}, not {kind.plain}")
    if spec.state is not None and spec.state not in kind.states:
        states = ", ".join(kind.states) if kind.states else "none (it has one look)"
        raise VidgenError(f"{where}: state '{spec.state}' of {kind.plain}: use {states}{did_you_mean(spec.state, list(kind.states))}")
    if spec.sequence is not None:
        check_sequence(spec.sequence, "dna" if spec.kind == "dna" else "rna", where)
    if spec.bp is not None and not 4 <= spec.bp <= 200:
        raise VidgenError(f"{where}: bp {spec.bp}: draw 4 to 200 base pairs")
    if spec.bp is not None and spec.sequence is not None and spec.bp != len(spec.sequence.replace(" ", "")):
        raise VidgenError(f"{where}: bp {spec.bp} but the sequence has {len(spec.sequence.replace(' ', ''))} bases; give one of them")
    if spec.anticodon is not None or spec.amino_acid is not None:
        check_trna(spec.anticodon or "CAU", spec.amino_acid, where)
    if spec.style is not None and spec.style not in ("cloverleaf", "l_shape"):
        raise VidgenError(f"{where}: style '{spec.style}' of a tRNA: use cloverleaf (its secondary structure) or l_shape (its 3-D shape)")
    if spec.rrna is not None and spec.rrna not in RRNA_TYPES:
        raise VidgenError(f"{where}: rrna '{spec.rrna}': use {', '.join(RRNA_TYPES)}{did_you_mean(spec.rrna, list(RRNA_TYPES))}")
    for mark in spec.marks:
        histone_mark(mark, where)
    if spec.gating is not None and spec.gating not in GATINGS:
        raise VidgenError(f"{where}: gating '{spec.gating}': use {', '.join(GATINGS)}{did_you_mean(spec.gating, list(GATINGS))}")
    if spec.ion is not None and spec.ion not in IONS:
        raise VidgenError(f"{where}: ion '{spec.ion}': use {', '.join(IONS)}{did_you_mean(spec.ion, list(IONS))}")
    if spec.kind == "ion" and spec.ion is None:
        raise VidgenError(f"{where}: an ion needs ion: one of {', '.join(IONS)}")
    if spec.state == "inactivated" and (spec.gating or "voltage") != "voltage":
        raise VidgenError(f"{where}: state inactivated: only voltage-gated channels inactivate (the inactivation gate of Na⁺ channels); "
                          f"a {spec.gating}-gated channel is closed or open")
    if spec.kind == "h_atpase" and spec.state is not None and pump_type(spec.membrane) == "v":
        raise VidgenError(f"{where}: state '{spec.state}': the V-type H⁺-ATPase of this membrane is a rotary pump (like ATP synthase run "
                          f"backwards) without E1/E2 states; those belong to the P-type pump of the plasma membrane")
    spec = _with_transporter(spec, where)
    _check_carrier(spec, where)
    _check_abc(spec, where)
    if spec.c_subunits is not None and not 8 <= spec.c_subunits <= 17:
        raise VidgenError(f"{where}: c_subunits {spec.c_subunits}: c-rings have 8 (animal mitochondria) to 17 subunits (14 in chloroplasts)")
    if spec.mass is not None and not 5 <= spec.mass <= 3000:
        raise VidgenError(f"{where}: mass {spec.mass:g} kDa: give 5 to 3000 kDa")
    for mod in spec.modifications:
        check_modification(mod[0], mod[1], where)
        domain = mod[2] if len(mod) > 2 else None
        if domain is not None and domain not in spec.domains:
            raise VidgenError(f"{where}: modification on domain '{domain}': not one of its domains{did_you_mean(domain, list(spec.domains))}"
                              f" ({', '.join(spec.domains) or 'none given'})")
    return spec


def _with_transporter(spec: MoleculeSpec, where: str) -> MoleculeSpec:
    """A carrier named by ``transporter`` (``sglt1``) gets that carrier's mode, substrates, moves
    and ratio (written ones must agree)."""
    if spec.transporter is None:
        return spec
    name = spec.transporter.lower()
    if name not in TRANSPORTERS:
        raise VidgenError(f"{where}: transporter '{spec.transporter}': use {', '.join(TRANSPORTERS)}{did_you_mean(name, list(TRANSPORTERS))}")
    t = TRANSPORTERS[name]
    for option, value, wanted in (("mode", spec.mode, t.mode), ("substrates", spec.substrates, t.substrates), ("moves", spec.moves, t.moves),
                                  ("ratio", spec.ratio, t.ratio)):
        if value not in (None, ()) and value != wanted:
            written = f"[{_listed(value)}]" if isinstance(value, tuple) else str(value)
            raise VidgenError(f"{where}: {option} {written} does not match transporter {t.label} ({_listed(wanted)}); leave it out")
    return replace(spec, mode=t.mode, substrates=t.substrates, moves=t.moves, ratio=t.ratio, transporter=name)


def _listed(value: object) -> str:
    return ", ".join(str(v) for v in value) if isinstance(value, tuple) else str(value)


def carrier_parts(spec: MoleculeSpec) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[int, ...]]:
    """A carrier's ``(mode, substrates, moves, ratio)`` with the defaults filled in."""
    mode = spec.mode or "uniport"
    solutes = spec.substrates or CARRIER_MODES[mode][0]
    moves = spec.moves or (CARRIER_MODES[mode][1] if not spec.substrates else tuple("in" for _ in solutes) if mode != "antiport"
                           else ("in", "out")[: len(solutes)])
    ratio = spec.ratio or tuple(1 for _ in solutes)
    return mode, tuple(solutes), tuple(moves), tuple(ratio)


def abc_parts(spec: MoleculeSpec) -> tuple[str, str]:
    """An ABC transporter's ``(substrate, way)``: a drug pumped out by default."""
    return (spec.substrates[0] if spec.substrates else "drug"), (spec.moves[0] if spec.moves else "out")


def _check_abc(spec: MoleculeSpec, where: str) -> None:
    if spec.kind != "abc_transporter":
        return
    if len(spec.substrates) > 1 or len(spec.moves) > 1:
        raise VidgenError(f"{where}: an ABC transporter moves one substrate (one of substrates, one of moves)")
    substrate, way = abc_parts(spec)
    if substrate not in IONS and substrate not in MOLECULES:
        raise VidgenError(f"{where}: substrate '{substrate}': an ion or a small molecule (drug, glucose…){did_you_mean(substrate, [*IONS, *MOLECULES])}")
    if way not in ("in", "out"):
        raise VidgenError(f"{where}: moves: in or out")
    if way == "in" and spec.membrane not in (None, "bacterial_inner_membrane"):
        raise VidgenError(f"{where}: moves: in: ABC importers (with a periplasmic binding protein) are bacterial; eukaryotic ABC transporters "
                          f"export from the cytosol (P-glycoprotein pumps drugs out, TAP moves peptides into the ER)")


def _check_carrier(spec: MoleculeSpec, where: str) -> None:
    if spec.kind != "carrier":
        return
    mode = spec.mode or "uniport"
    if mode not in CARRIER_MODES:
        raise VidgenError(f"{where}: mode '{mode}': use {', '.join(CARRIER_MODES)}{did_you_mean(mode, list(CARRIER_MODES))}")
    _, solutes, moves, ratio = carrier_parts(spec)
    if len(ratio) != len(solutes) or any(not 1 <= r <= 4 for r in ratio):
        raise VidgenError(f"{where}: ratio: one count (1 to 4) per substrate ({len(solutes)}), e.g. [2, 1] for 2 Na⁺ per glucose")
    if mode == "uniport" and ratio != (1,):
        raise VidgenError(f"{where}: ratio {list(ratio)}: a uniporter moves one solute per cycle (alternating access with one binding site)")
    for s in solutes:
        if s not in IONS and s not in MOLECULES:
            raise VidgenError(f"{where}: substrate '{s}': an ion ({', '.join(IONS)}) or a small molecule (glucose, atp…)"
                              f"{did_you_mean(s, [*IONS, *MOLECULES])}")
    if len(moves) != len(solutes) or any(m not in ("in", "out") for m in moves):
        raise VidgenError(f"{where}: moves: one of in / out per substrate ({len(solutes)})")
    if mode == "uniport" and len(solutes) != 1:
        raise VidgenError(f"{where}: a uniporter moves one solute; for two use symport (same way) or antiport (opposite ways)")
    if mode in ("symport", "antiport") and len(solutes) < 2:
        raise VidgenError(f"{where}: a {mode}er moves two solutes (one usually down its gradient, driving the other)")
    if mode == "symport" and len(set(moves)) != 1:
        raise VidgenError(f"{where}: a symporter moves its solutes the same way; opposite ways is antiport")
    if mode == "antiport" and len(set(moves)) != 2:
        raise VidgenError(f"{where}: an antiporter moves its solutes opposite ways; the same way is symport")


# ----- small helpers -------------------------------------------------------------------------------


def _shape(shape: object, fill: str | None, tone: str = "solid", stroke: str | None = None, px: float = 0.8, z: float = 0.0,
           detail: bool = False) -> Prim:
    return Prim(tuple(shape_curves(shape)), fill, tone, stroke if stroke is not None else fill, px if (stroke or fill) else 0.0, z=z,
                detail=detail)


def _line(points: Sequence[Point], hue: str, nm: float, px: float = 1.0, z: float = 0.0, closed: bool = False, detail: bool = False) -> Prim:
    pts = list(points)
    curves = smooth(pts, closed=closed) if len(pts) > 2 else [line(pts[0], pts[1])]
    return Prim(tuple(curves), None, "solid", hue, px, nm, z=z, detail=detail)


def _poly(points: Sequence[Point], hue: str, tone: str = "solid", z: float = 0.0, rounded: bool = True, detail: bool = False) -> Prim:
    curves = smooth(list(points), closed=True, tension=0.6) if rounded else polygon(list(points))
    return Prim(tuple(curves), hue, tone, hue, 0.8, z=z, detail=detail)


def _text(markup: str, at: Point, height: float, hue: str = TEXT, z: float = 2.0, detail: bool = True) -> Prim:
    return Prim(text=markup, at=at, height=height, fill=hue, z=z, detail=detail)


def _arrow(points: Sequence[Point], hue: str, nm: float = 0.18, head: float = 0.5, z: float = 1.5) -> list[Prim]:
    """A line through ``points`` with a filled head at its end."""
    pts = list(points)
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    d = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    base = (x1 - ux * head, y1 - uy * head)
    shaft = pts[:-1] + [base]
    tip = [(x1, y1), (base[0] - uy * head * 0.45, base[1] + ux * head * 0.45), (base[0] + uy * head * 0.45, base[1] - ux * head * 0.45)]
    return [_line(shaft, hue, nm, 1.4, z), Prim(tuple(polygon(tip)), hue, "solid", hue, 0.6, z=z)]


def _bounds(prims: Sequence[Prim], pad: float = 0.3) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for p in prims:
        if p.text:
            w = p.height * 0.6 * max(1, len(_strip(p.text)))
            xs += [p.at[0] - w / 2, p.at[0] + w / 2]
            ys += [p.at[1] - p.height / 2, p.at[1] + p.height / 2]
        for cv in p.curves:
            xs += [q[0] for q in cv]
            ys += [q[1] for q in cv]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad) if xs else (-1.0, -1.0, 1.0, 1.0)


def _strip(markup: str) -> str:
    return re.sub(r"<[^>]+>", "", markup)


def _ring(cx: float, cy: float, r: float, n: int, start: float = math.pi / 2) -> list[Point]:
    return [(cx + r * math.cos(start + 2 * math.pi * k / n), cy + r * math.sin(start + 2 * math.pi * k / n)) for k in range(n)]


# ----- nucleic acids --------------------------------------------------------------------------------

_DEFAULT_DNA = "ATGCGTACCGGATCGTTAGCAATGCCGTA"


def dna(spec: MoleculeSpec) -> Glyph:
    """B-DNA along x: two backbones (the sugar–phosphate chains) winding round the axis 2 nm
    across, 0.34 nm per base pair and 10.5 per turn; the strands are offset round the axis so
    the grooves between them alternate wide (major, about 2.2 nm) and narrow (minor, about
    1.2 nm); base pairs as rungs, each half the colour of its base (A–T, G–C); the top strand
    runs 5′→3′ left to right, its partner 3′→5′ (antiparallel); with ``letters`` the two
    sequences above and below, each with its ends."""
    seq = (spec.sequence or "").replace(" ", "").upper() or (_DEFAULT_DNA * 8)[: spec.bp or 21]
    n = len(seq)
    other = complement(seq)
    length = n * DNA_RISE
    x0 = -length / 2
    r = DNA_WIDTH / 2
    p = pitch()
    phase = 0.35 * 2 * math.pi            # the minor groove's share of a turn: 0.35 × 3.57 nm ≈ 1.25 nm
    hue = MOLECULES["dna"].hue
    prims: list[Prim] = []

    def at(strand: int, x: float) -> tuple[float, float]:
        a = 2 * math.pi * (x - x0) / p + strand * phase
        return r * math.sin(a), math.cos(a)            # y, depth (>0: in front)

    runs: dict[tuple[int, bool], list[list[Point]]] = {(s, f): [] for s in (0, 1) for f in (True, False)}
    for s in (0, 1):
        current: list[Point] = []
        front_now: bool | None = None
        steps = max(8, int(length / 0.05))
        for k in range(steps + 1):
            x = x0 + length * k / steps
            y, depth = at(s, x)
            front = depth > 0
            if front_now is not None and front != front_now:
                current.append((x, y))
                runs[(s, front_now)].append(current)
                current = [(x, y)]
            current.append((x, y))
            front_now = front
        runs[(s, bool(front_now))].append(current)
    strand_hues = ("#3F6FC0", "#C9703A")
    for s in (0, 1):
        for pts in runs[(s, False)]:
            if len(pts) > 1:
                prims.append(_line(pts, strand_hues[s], 0.36, 1.6, z=0.0))
                prims[-1] = replace(prims[-1], tone="fill")
    for k, (b1, b2) in enumerate(zip(seq, other)):
        x = x0 + (k + 0.5) * DNA_RISE
        ya, _ = at(0, x)
        yb, _ = at(1, x)
        mid = (ya + yb) / 2
        if abs(ya - yb) > 0.12:
            prims.append(_line([(x, ya), (x, mid)], BASE_HUES[b1], 0.17, 1.2, z=0.5))
            prims.append(_line([(x, mid), (x, yb)], BASE_HUES[b2], 0.17, 1.2, z=0.5))
    for s in (0, 1):
        for pts in runs[(s, True)]:
            if len(pts) > 1:
                prims.append(_line(pts, strand_hues[s], 0.4, 2.0, z=1.0))
    # ends: the top strand 5′ at the left, its partner 5′ at the right (antiparallel)
    end_h = 0.42
    ya0, _ = at(0, x0)
    yb0, _ = at(1, x0)
    ya1, _ = at(0, x0 + length)
    yb1, _ = at(1, x0 + length)
    show_letters = spec.letters if spec.letters is not None else (spec.sequence is not None and n <= 60)
    anchors: dict[str, tuple[str, Point]] = {}
    if show_letters:
        row = r + 0.55
        for k, (b1, b2) in enumerate(zip(seq, other)):
            x = x0 + (k + 0.5) * DNA_RISE
            prims.append(_text(b1, (x, row), 0.3, BASE_HUES[b1], detail=True))
            prims.append(_text(b2, (x, -row), 0.3, BASE_HUES[b2], detail=True))
        # each sequence written with its own ends: the top strand 5′→3′, its partner 3′→5′
        prims += [_text("5′", (x0 - 0.7, row), end_h, strand_hues[0], detail=False), _text("3′", (x0 + length + 0.7, row), end_h, strand_hues[0], detail=False),
                  _text("3′", (x0 - 0.7, -row), end_h, strand_hues[1], detail=False), _text("5′", (x0 + length + 0.7, -row), end_h, strand_hues[1], detail=False)]
    else:
        # the ends at the backbones themselves, each in its strand's colour
        prims += [_text("5′", (x0 - 0.45, ya0), end_h, strand_hues[0], detail=False), _text("3′", (x0 + length + 0.45, ya1), end_h, strand_hues[0], detail=False),
                  _text("3′", (x0 - 0.45, yb0 - (0.45 if abs(yb0 - ya0) < 0.5 else 0.0)), end_h, strand_hues[1], detail=False),
                  _text("5′", (x0 + length + 0.45, yb1 - (0.45 if abs(yb1 - ya1) < 0.5 else 0.0)), end_h, strand_hues[1], detail=False)]
    # grooves: along the helix's upper edge the two backbones come up in turn; the stretches
    # between them alternate narrow (the minor groove, 0.35 of a turn) and wide (the major groove)
    tops = sorted(x0 + p * ((0.25 - s * phase / (2 * math.pi)) % 1.0 + k) for s in (0, 1) for k in range(-1, int(length / p) + 2))
    tops = [x for x in tops if x0 <= x <= x0 + length]
    gaps = [(b - a, (a + b) / 2) for a, b in zip(tops, tops[1:])]
    if gaps:
        major = min((g for g in gaps if g[0] > p / 2), key=lambda g: abs(g[1]), default=gaps[0])
        minor = min((g for g in gaps if g[0] < p / 2), key=lambda g: abs(g[1]), default=gaps[0])
        anchors["major_groove"] = ("Major groove", (major[1], r * 0.72))
        anchors["minor_groove"] = ("Minor groove", (minor[1], r * 0.72))
    middle = min(range(n), key=lambda i: abs(x0 + (i + 0.5) * DNA_RISE))
    xm = x0 + (middle + 0.5) * DNA_RISE
    pair = f"{seq[middle]}–{other[middle]} base pair"
    anchors.update({
        "base_pair": (pair, (xm, (at(0, xm)[0] + at(1, xm)[0]) / 2)),
        "backbone": ("Sugar–phosphate backbone", _front_point(at, 0, x0, length)),
        "five_prime": ("5′ end", (x0, ya0)), "three_prime": ("3′ end", (x0 + length, ya1)),
    })
    facts = {"bp": n, "length": length, "strands": (("5′", "3′", 1), ("3′", "5′", -1)), "sequence": seq, "partner": other,
             "gaps": [round(g[0], 3) for g in gaps]}
    return Glyph("dna", tuple(prims), anchors, _bounds(prims), facts=facts)


def _front_point(at: object, strand: int, x0: float, length: float) -> Point:
    for k in range(200):
        x = x0 + length * (0.5 + (k // 2) * 0.005 * (1 if k % 2 else -1))
        y, depth = at(strand, x)  # type: ignore[operator]
        if depth > 0.8:
            return (x, y)
    return (x0 + length / 2, at(strand, x0 + length / 2)[0])  # type: ignore[operator]


_DEFAULT_MRNA = "AUGGCCAAGUUCGGAUAA"


def mrna(spec: MoleculeSpec) -> Glyph:
    """mRNA along x, 5′ at the left: a 5′ cap (7-methylguanosine joined 5′–5′ by three
    phosphates), the bases as ticks (letters below when the sequence is given), codons marked
    from the first AUG (start green, stop red), a 3′ poly(A) tail."""
    seq = (spec.sequence or _DEFAULT_MRNA).replace(" ", "").upper()
    step = 0.6
    n = len(seq)
    hue = MOLECULES["mrna"].hue
    cap, tail = spec.cap is not False, spec.tail is not False
    tail_n = 10 if tail else 0
    total = (n + tail_n) * step
    x0 = -total / 2
    prims: list[Prim] = []
    xs = [x0 + (k + 0.5) * step for k in range(n + tail_n)]
    backbone = [(x, 0.12 * math.sin(k * 1.1)) for k, x in enumerate(xs)]
    prims.append(_line(backbone, hue, 0.3, 1.8, z=1.0))
    letters = spec.letters if spec.letters is not None else n <= 60
    bases = seq + "A" * tail_n
    for k, (x, y) in enumerate(backbone):
        b = bases[k]
        prims.append(_line([(x, y), (x, y - 0.7)], BASE_HUES[b], 0.2, 1.2, z=0.5))
        if letters:
            prims.append(_text(b, (x, y - 1.05), 0.34, BASE_HUES[b]))
    anchors: dict[str, tuple[str, Point]] = {"five_prime": ("5′ end", backbone[0]), "three_prime": ("3′ end", backbone[-1])}
    start = seq.find("AUG")
    if start >= 0:
        for c in range(start, n - 2, 3):
            codon = seq[c:c + 3]
            colour = "#4FA35E" if c == start else ("#D9534F" if codon in ("UAA", "UAG", "UGA") else "#9A9A9A")
            a, b = xs[c] - step * 0.4, xs[c + 2] + step * 0.4
            prims.append(_line([(a, -1.5), (b, -1.5)], colour, 0.12, 1.4, z=0.5, detail=True))
            if c == start:
                anchors["start_codon"] = ("Start codon (AUG)", ((a + b) / 2, -1.5))
            if codon in ("UAA", "UAG", "UGA"):
                anchors["stop_codon"] = (f"Stop codon ({codon})", ((a + b) / 2, -1.5))
                break
        if start + 5 < n:
            anchors["codon"] = ("Codon", ((xs[start + 3] + xs[start + 5]) / 2, -1.5))
    if cap:
        cx = x0 - 1.0
        prims += [_line([(cx + 0.35, 0.0), (x0 + step * 0.5, backbone[0][1])], PHOSPHATE_HUE, 0.16, 1.2),
                  _shape(Ellipse(cx, 0.0, 0.45, 0.45), "#3F6FC0", "fill", z=1.2), _text("m<sup>7</sup>G", (cx, 0.0), 0.3, ON, z=2.2)]
        for j in range(3):
            prims.append(_shape(Ellipse(cx + 0.55 + j * 0.17, 0.32, 0.09, 0.09), PHOSPHATE_HUE, z=1.3, detail=True))
        anchors["cap"] = ("5′ cap (m<sup>7</sup>G)", (cx, 0.0))
        prims.append(_text("5′", (cx - 0.8, 0.0), 0.42, hue, detail=False))
    else:
        prims.append(_text("5′", (x0 - 0.3, 0.0), 0.42, hue, detail=False))
    prims.append(_text("3′", (x0 + total + 0.35, backbone[-1][1]), 0.42, hue, detail=False))
    if tail:
        anchors["tail"] = ("Poly(A) tail", backbone[n + tail_n // 2])
    return Glyph("mrna", tuple(prims), anchors, _bounds(prims), facts={"five_prime_x": x0, "three_prime_x": x0 + total, "sequence": seq})


def trna(spec: MoleculeSpec) -> Glyph:
    """A tRNA: as a cloverleaf (its secondary structure: acceptor stem with the 3′ CCA end and
    its amino acid, D arm, anticodon arm with the anticodon at the bottom of its loop, variable
    loop, TψC arm) or as the L of its 3-D shape (about 7 nm along each arm; the anticodon at one
    end, the amino acid at the other)."""
    anticodon, aa = check_trna(spec.anticodon or "CAU", spec.amino_acid or ("Met" if not spec.anticodon else None), spec.where or "trna")
    aa_name = AMINO_ACIDS[aa] if aa else ""
    hue = MOLECULES["trna"].hue
    prims: list[Prim] = []
    anchors: dict[str, tuple[str, Point]] = {}
    if spec.style == "l_shape":
        # the 3-D L: the acceptor stem stacked on the TψC arm (one limb), the D arm on the
        # anticodon arm (the other), meeting at the elbow where the D and TψC loops touch
        elbow = (-2.6, 2.4)
        acceptor_end = (3.4, 2.4)
        anticodon_end = (-1.7, -3.9)
        for a, b, colour in ((elbow, acceptor_end, hue), (elbow, anticodon_end, "#9B5FB0")):
            d = math.dist(a, b)
            prims.append(_shape(Capsule((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, d + 1.9, 1.9, math.atan2(b[1] - a[1], b[0] - a[0])), colour, z=0.5))
        prims.append(_shape(Ellipse(elbow[0], elbow[1], 1.25, 1.25), "#B04E8C", z=0.6))
        down = (anticodon_end[0] - elbow[0], anticodon_end[1] - elbow[1])
        dl = math.hypot(*down)
        tip = (anticodon_end[0] + down[0] / dl * 1.2, anticodon_end[1] + down[1] / dl * 1.2)
        across = (-down[1] / dl, down[0] / dl)
        for j, b in enumerate(anticodon):
            p = (tip[0] + across[0] * (j - 1) * 0.62, tip[1] + across[1] * (j - 1) * 0.62)   # read 5′→3′ left to right
            prims += [_shape(Ellipse(p[0], p[1], 0.3, 0.3), BASE_HUES.get(b, "#888888"), z=1.0), _text(b, p, 0.32, ON, z=2.0)]
        cca = [(acceptor_end[0] + 1.1 + 0.42 * k, acceptor_end[1] + 0.15 * k) for k in range(4)]
        prims.append(_line([(acceptor_end[0] + 0.8, acceptor_end[1])] + cca, hue, 0.16, 1.2, z=0.5))
        for q, b in zip(cca, "ACCA"):
            prims.append(_shape(Ellipse(q[0], q[1], 0.16, 0.16), BASE_HUES[b], z=0.9))
        prims.append(_text("3′", (cca[-1][0], cca[-1][1] - 0.55), 0.4, hue, detail=False))
        anchors.update({"anticodon": (f"Anticodon 5′-{anticodon}-3′", tip), "elbow": ("Elbow (D and TψC loops)", elbow),
                        "acceptor": ("Acceptor stem", (acceptor_end[0] - 1.0, acceptor_end[1])), "cca": ("3′ CCA end", cca[1])})
        end = (cca[-1][0] + 0.55, cca[-1][1] - 0.35)
    else:
        u = 0.42
        stems = []

        def stem(a: Point, b: Point, pairs: int) -> None:
            dx, dy = b[0] - a[0], b[1] - a[1]
            d = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / d * 0.32, dx / d * 0.32
            prims.append(_line([(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny)], hue, 0.2, 1.4, z=0.6))
            prims.append(_line([(a[0] - nx, a[1] - ny), (b[0] - nx, b[1] - ny)], hue, 0.2, 1.4, z=0.6))
            for k in range(pairs):
                t = (k + 0.5) / pairs
                c = (a[0] + dx * t, a[1] + dy * t)
                prims.append(_line([(c[0] + nx, c[1] + ny), (c[0] - nx, c[1] - ny)], "#B9A0C9", 0.08, 0.8, z=0.4, detail=True))
            stems.append((a, b))

        def loop(c: Point, r: float, count: int, start: float, hue_: str = hue) -> list[Point]:
            pts = _ring(c[0], c[1], r, count, start)
            prims.append(_line(pts + [pts[0]], hue_, 0.16, 1.2, z=0.5))
            for q in pts:
                prims.append(_shape(Ellipse(q[0], q[1], 0.13, 0.13), hue_, z=0.7, detail=True))
            return pts

        top = (0.0, 0.6)
        stem(top, (0.0, 0.6 + 7 * u), 7)                                  # acceptor stem
        stem((-0.7, 0.0), (-0.7 - 4 * u, 0.0), 4)                         # D stem
        loop((-0.7 - 4 * u - 0.85, 0.0), 0.85, 8, 0.0)
        stem((0.7, 0.0), (0.7 + 5 * u, 0.0), 5)                            # TψC stem
        loop((0.7 + 5 * u + 0.8, 0.0), 0.8, 7, math.pi)
        stem((0.0, -0.6), (0.0, -0.6 - 5 * u), 5)                         # anticodon stem
        centre = (0.0, -0.6 - 5 * u - 0.85)
        pts = loop(centre, 0.85, 7, -math.pi / 2)              # one nucleotide at the very bottom
        # the anticodon: the loop's middle three, read 5′→3′ left to right along its bottom
        bottom = sorted(pts, key=lambda q: q[1])[:3]
        bottom.sort(key=lambda q: q[0])
        for q, b in zip(bottom, anticodon):
            prims += [_shape(Ellipse(q[0], q[1], 0.3, 0.3), BASE_HUES.get(b, "#888888"), z=1.0), _text(b, q, 0.32, ON, z=2.0)]
        prims.append(_line([(0.9, -0.5), (1.4, -1.2), (1.2, -1.6)], hue, 0.16, 1.2, z=0.5))   # variable loop
        five = (-0.32, 0.6 + 7 * u)
        prims.append(_text("5′", (five[0] - 0.45, five[1] + 0.35), 0.4, hue, detail=False))
        cca = [(0.32, 0.6 + 7 * u + 0.4 * (k + 1)) for k in range(4)]
        for q, b in zip(cca, "ACCA"):
            prims += [_shape(Ellipse(q[0], q[1], 0.15, 0.15), BASE_HUES[b], z=0.9)]
        prims.append(_line([(0.32, 0.6 + 7 * u)] + cca, hue, 0.16, 1.2, z=0.5))
        prims.append(_text("3′", (0.85, cca[-1][1]), 0.4, hue, detail=False))
        end = (cca[-1][0], cca[-1][1] + 0.55)
        anchors.update({"anticodon": (f"Anticodon 5′-{anticodon}-3′", ((bottom[0][0] + bottom[-1][0]) / 2, bottom[0][1])),
                        "anticodon_loop": ("Anticodon loop", (centre[0] - 0.85, centre[1])),
                        "acceptor": ("Acceptor stem", (0.0, 0.6 + 3.5 * u)), "cca": ("3′ CCA end", cca[2]),
                        "d_loop": ("D loop", (-0.7 - 4 * u - 0.85, 0.0)), "t_loop": ("TψC loop", (0.7 + 5 * u + 0.8, 0.0))})
    if aa:
        prims += [_shape(Ellipse(end[0], end[1] + 0.35, 0.55, 0.42), "#E39B32", z=1.2), _text(aa_name, (end[0], end[1] + 0.35), 0.32, ON, z=2.2)]
        anchors["amino_acid"] = (f"Amino acid ({aa_name})", (end[0], end[1] + 0.35))
    return Glyph("trna", tuple(prims), anchors, _bounds(prims), facts={"anticodon": anticodon, "amino_acid": aa})


def rrna(spec: MoleculeSpec) -> Glyph:
    """A stylised rRNA: hairpins of paired stems round a central loop (its secondary
    structure), named (18S rRNA…)."""
    hue = MOLECULES["rrna"].hue
    prims: list[Prim] = []
    arms = [(0.0, 3.0), (60.0, 2.2), (125.0, 3.4), (190.0, 2.6), (250.0, 2.0), (305.0, 2.8)]
    hub = 1.2
    for angle, length in arms:
        a = math.radians(angle)
        d = (math.cos(a), math.sin(a))
        nrm = (-d[1] * 0.3, d[0] * 0.3)
        p0 = (d[0] * hub, d[1] * hub)
        p1 = (d[0] * (hub + length), d[1] * (hub + length))
        prims += [_line([(p0[0] + nrm[0], p0[1] + nrm[1]), (p1[0] + nrm[0], p1[1] + nrm[1])], hue, 0.18, 1.3, z=0.5),
                  _line([(p0[0] - nrm[0], p0[1] - nrm[1]), (p1[0] - nrm[0], p1[1] - nrm[1])], hue, 0.18, 1.3, z=0.5)]
        tip = (p1[0] + d[0] * 0.5, p1[1] + d[1] * 0.5)
        prims.append(_line(_ring(tip[0], tip[1], 0.5, 8) + [_ring(tip[0], tip[1], 0.5, 8)[0]], hue, 0.18, 1.3, z=0.5))
        for k in range(int(length / 0.4)):
            c = (p0[0] + d[0] * (k + 0.5) * 0.4, p0[1] + d[1] * (k + 0.5) * 0.4)
            prims.append(_line([(c[0] + nrm[0], c[1] + nrm[1]), (c[0] - nrm[0], c[1] - nrm[1])], "#D8B98A", 0.08, 0.8, z=0.4, detail=True))
    hub_pts = _ring(0.0, 0.0, hub, 24)
    prims.append(_line(hub_pts + [hub_pts[0]], hue, 0.18, 1.3, z=0.5))
    name = f"{spec.rrna} rRNA" if spec.rrna else "rRNA"
    prims.append(_text(name, (0.0, 0.0), 0.5, detail=False))
    anchors = {"helix": ("Helix (paired stem)", (math.cos(math.radians(125)) * 2.8, math.sin(math.radians(125)) * 2.8)),
               "loop": ("Hairpin loop", (math.cos(0.0) * 4.7, 0.0))}
    return Glyph("rrna", tuple(prims), anchors, _bounds(prims), facts={"type": spec.rrna})


# ----- chromatin -----------------------------------------------------------------------------------


def _octamer(cx: float, cy: float, r: float, detail: bool = True) -> list[Prim]:
    """The histone octamer seen down its superhelical axis: two each of H3, H4, H2A, H2B."""
    out = []
    order = ["H3", "H4", "H2B", "H2A", "H3", "H4", "H2B", "H2A"]
    for k, name in enumerate(order):
        a0, a1 = 2 * math.pi * k / 8 + 0.03, 2 * math.pi * (k + 1) / 8 - 0.03
        pts = [(cx, cy)] + [(cx + r * math.cos(a0 + (a1 - a0) * j / 6), cy + r * math.sin(a0 + (a1 - a0) * j / 6)) for j in range(7)]
        out.append(Prim(tuple(polygon(pts)), HISTONE_HUES[name], "solid", HISTONE_HUES[name], 0.6, z=0.5, detail=detail))
    out.append(_shape(Ellipse(cx, cy, r, r), HISTONE_HUES["H3"], "fill", z=0.4))
    return out


def nucleosome(spec: MoleculeSpec, center: Point = (0.0, 0.0), linker: float = 4.0, marks: Sequence[str] = ()) -> Glyph:
    """A nucleosome seen down its superhelical axis: the histone octamer (H2A, H2B, H3, H4,
    two of each), 147 bp of DNA in 1.65 left-handed turns round it (11 nm across; the second
    gyre drawn behind), linker DNA leaving at both ends, the histones' N-terminal tails and
    their marks (H3K4me3, H3K27ac…)."""
    cx, cy = center
    hue = MOLECULES["dna"].hue
    tails = []
    # the histones' N-terminal tails reach out between the DNA gyres (drawn first: behind the DNA)
    prims: list[Prim] = []
    for name, a in (("H3", 2.55), ("H4", 3.35), ("H2A", 4.35), ("H2B", 5.25), ("H3", 0.75), ("H2B", 1.45)):
        base = (cx + 3.0 * math.cos(a), cy + 3.0 * math.sin(a))
        mid = (cx + 6.0 * math.cos(a - 0.12), cy + 6.0 * math.sin(a - 0.12))
        tip = (cx + 8.2 * math.cos(a + 0.05), cy + 8.2 * math.sin(a + 0.05))
        prims.append(_line([base, mid, tip], HISTONE_HUES[name], 0.32, 1.4, z=0.2))
        tails.append((name, tip, a))
    prims += _octamer(cx, cy, 3.1)
    dyad = math.pi / 2
    half = NUCLEOSOME_TURNS * math.pi                    # 0.825 turns either side of the dyad
    path = []
    steps = 160
    for k in range(steps + 1):
        t = k / steps
        a = dyad + half - 2 * half * t                   # left-handed superhelix: clockwise seen from here
        rr = 4.05 + 0.7 * t                              # the second gyre drawn a little outside the first
        path.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    ends = []
    for q, prev in ((path[0], path[1]), (path[-1], path[-2])):
        d = math.dist(q, prev) or 1.0
        out = (q[0] + (q[0] - prev[0]) / d * linker, q[1] + (q[1] - prev[1]) / d * linker)
        ends.append(out)
    full = [ends[0]] + path + [ends[1]]
    first = full[: len(full) * 5 // 8]
    second = full[len(full) * 5 // 8 - 1:]
    # a tube: a dark edge under each gyre, so where the near gyre crosses the far one its edge shows
    for pts, z, tone in ((second, 0.8, "fill"), (first, 1.0, "solid")):
        prims.append(replace(_line(pts, hue, DNA_WIDTH + 0.35, 2.4, z=z), tone="ink"))
        prims.append(replace(_line(pts, hue, DNA_WIDTH - 0.2, 1.6, z=z + 0.05), tone=tone))
    on_tail: dict[str, int] = {}
    for text in marks:
        histone, code, pos, mod, count = histone_mark(text, spec.where or "nucleosome")
        mine = [t for t in tails if t[0] == histone] or tails[:1]
        j = on_tail.get(histone, 0)
        on_tail[histone] = j + 1
        name, tip, a = mine[j % len(mine)]                  # each copy of the histone has its own tail
        j //= len(mine)
        d = (math.cos(a + 0.05), math.sin(a + 0.05))
        p = (tip[0] + d[0] * (0.7 + 1.4 * j), tip[1] + d[1] * (0.7 + 1.4 * j))
        mark = f"{mod.mark}{count if mod.mark == 'Me' and count > 1 else ''}"
        side = (-d[1], d[0])
        prims += [_shape(Ellipse(p[0], p[1], 0.8, 0.8), mod.hue, z=1.5), _text(mark, p, 0.55, ON, z=2.5),
                  _text(f"{histone}{code}{pos}", (p[0] + side[0] * 1.9, p[1] + side[1] * 1.9), 0.55)]
    anchors = {"octamer": ("Histone octamer", (cx + 1.2, cy - 0.6)),
               "dna": ("DNA: 147 bp in 1.65 turns", path[steps // 4]), "linker": ("Linker DNA", ends[0]), "tail": ("Histone tail", tails[0][1])}
    return Glyph("nucleosome", tuple(prims), anchors, _bounds(prims), facts={"bp": NUCLEOSOME_BP, "turns": NUCLEOSOME_TURNS, "handedness": "left"})


def chromatin(spec: MoleculeSpec) -> Glyph:
    """Chromatin: the 10 nm fibre (nucleosomes on linker DNA, beads on a string) or a compact
    schematic of further folding (nucleosomes stacked in a zigzag about 30 nm across)."""
    count = spec.nucleosomes or (5 if spec.state != "compact" else 12)
    prims: list[Prim] = []
    hue = MOLECULES["dna"].hue
    anchors: dict[str, tuple[str, Point]] = {}
    if spec.state == "compact":
        centres = [((k - (count - 1) / 2) * 5.5, 9.5 * (1 if k % 2 else -1)) for k in range(count)]
        prims.append(_line(centres, hue, 1.0, 1.6, z=0.3))
        for c in centres:
            prims += [_shape(Ellipse(c[0], c[1], 5.5, 5.5), hue, "fill", z=0.5), *[replace(p, detail=False) for p in _octamer(c[0], c[1], 3.2)]]
        prims.append(_text("schematic: higher-order folding", (0.0, -17.5), 2.0, detail=False))
        anchors = {"nucleosome": ("Nucleosome", centres[count // 2]), "fibre": ("Compacted fibre (~30 nm)", (centres[0][0], 0.0))}
        return Glyph("chromatin", tuple(prims), anchors, _bounds(prims), facts={"nucleosomes": count, "width": 30.0})
    linker = 17.0                                      # about 50 bp between nucleosomes (a 200 bp repeat)
    step = 11.0 + linker
    xs = [(k - (count - 1) / 2) * step for k in range(count)]
    path = [(xs[0] - step / 2, 0.0)] + [(x, 3.0 * math.sin(k * 1.3)) for k, x in enumerate(xs)] + [(xs[-1] + step / 2, 0.0)]
    prims.append(_line(path, hue, DNA_WIDTH, 1.6, z=0.3))
    for (x, y) in path[1:-1]:
        prims += [_shape(Ellipse(x, y, 5.5, 5.5), hue, "fill", z=0.5), *[replace(p, detail=False) for p in _octamer(x, y, 3.2)]]
    anchors = {"nucleosome": ("Nucleosome (11 nm)", path[1 + count // 2]),
               "linker": ("Linker DNA (~50 bp)", ((path[1][0] + path[2][0]) / 2, (path[1][1] + path[2][1]) / 2))}
    return Glyph("chromatin", tuple(prims), anchors, _bounds(prims), facts={"nucleosomes": count, "repeat_bp": 200})


# ----- proteins --------------------------------------------------------------------------------------


def protein(spec: MoleculeSpec) -> Glyph:
    """A globular protein: its domains as lobes (each the size its share of the mass gives,
    Erickson 2009) joined by linkers, N- and C-terminus marked."""
    names = spec.domains or ("",)
    mass = spec.mass or 50.0
    hue = MOLECULES["protein"].hue
    size = protein_size(mass / len(names))
    prims: list[Prim] = []
    anchors: dict[str, tuple[str, Point]] = {}
    centres = [((k - (len(names) - 1) / 2) * size * 1.15, 0.25 * size * (1 if k % 2 else -1) * (len(names) > 1)) for k in range(len(names))]
    shades = ("solid", "fill")
    for k, (c, name) in enumerate(zip(centres, names)):
        prims.append(_shape(Ellipse(c[0], c[1], size / 2, size / 2 * 0.85, 0.3 * k), hue, shades[k % 2], z=0.5))
        if name:
            prims.append(_text(name, c, size * 0.22, ON))
            anchors[f"domain_{k + 1}"] = (f"{name} domain", c)
    if len(centres) > 1:
        prims.append(_line(centres, hue, 0.35, 1.6, z=0.3))
    n_end = (centres[0][0] - size * 0.75, centres[0][1] - size * 0.25)
    c_end = (centres[-1][0] + size * 0.75, centres[-1][1] - size * 0.25)
    prims += [_line([(centres[0][0] - size * 0.4, centres[0][1]), n_end], hue, 0.3, 1.4, z=0.4), _text("N", (n_end[0] - 0.4, n_end[1]), 0.5),
              _line([(centres[-1][0] + size * 0.4, centres[-1][1]), c_end], hue, 0.3, 1.4, z=0.4), _text("C", (c_end[0] + 0.4, c_end[1]), 0.5)]
    anchors.update({"n_terminus": ("N-terminus", n_end), "c_terminus": ("C-terminus", c_end)})
    sites = tuple(((c[0], c[1] + size * 0.42), (0.0, 1.0)) for c in centres) + tuple(((c[0], c[1] - size * 0.42), (0.0, -1.0)) for c in centres)
    facts = {"mass_kda": mass, "domain_size": size, "domain_sites": {name: k for k, name in enumerate(names) if name}}
    return Glyph("protein", tuple(prims), anchors, _bounds(prims), sites=sites, facts=facts)


def kinase(spec: MoleculeSpec) -> Glyph:
    """The protein-kinase fold: a smaller N-lobe and a larger C-lobe with ATP bound in the cleft
    between; the activation loop phosphorylated when active."""
    hue = MOLECULES["kinase"].hue
    prims = [_shape(Ellipse(-0.3, 1.45, 1.8, 1.25, 0.15), hue, "fill", z=0.5), _shape(Ellipse(0.0, -1.3, 2.4, 1.75, -0.1), hue, z=0.5)]
    prims += _small("atp", (0.4, 0.1), 0.62)
    anchors: dict[str, tuple[str, Point]] = {"n_lobe": ("N-lobe", (-0.6, 2.0)), "c_lobe": ("C-lobe", (-0.6, -1.6)), "atp": ("ATP in the cleft", (0.4, 0.1))}
    loop = [(1.7, -0.6), (2.6, -0.9), (2.9, -1.8)]
    prims.append(_line(loop, hue, 0.3, 1.4, z=0.6))
    anchors["activation_loop"] = ("Activation loop", loop[1])
    if spec.state != "inactive":
        prims += _marker("P", (3.3, -2.2))
    sites = (((0.0, 3.0), (0.0, 1.0)), ((-2.4, -1.3), (-1.0, 0.0)), ((0.0, -3.1), (0.0, -1.0)))
    return Glyph("kinase", tuple(prims), anchors, _bounds(prims), sites=sites, facts={"active": spec.state != "inactive"})


def phosphatase(spec: MoleculeSpec) -> Glyph:
    """A protein phosphatase: a globular enzyme with its active-site cleft."""
    hue = MOLECULES["phosphatase"].hue
    prims = [_shape(Ellipse(0.0, 0.0, 2.5, 2.2), hue, z=0.5), _shape(Ellipse(1.6, 0.9, 0.7, 0.45, 0.6), hue, "light", z=0.6)]
    anchors = {"active_site": ("Active site", (1.6, 0.9))}
    sites = (((0.0, -2.2), (0.0, -1.0)), ((-2.5, 0.0), (-1.0, 0.0)))
    return Glyph("phosphatase", tuple(prims), anchors, _bounds(prims), sites=sites)


def g_protein(spec: MoleculeSpec) -> Glyph:
    """A heterotrimeric G protein on the cytosolic face (y < 0): Gα (Ras-like and helical
    domains, GDP between them when inactive, GTP when active) and Gβγ (Gβ's seven-bladed
    propeller, Gγ along it), each held in the cytosolic leaflet by a lipid anchor; when active,
    Gα–GTP has left Gβγ."""
    active = spec.state == "active"
    hue = MOLECULES["g_protein"].hue
    shift = -2.6 if active else 0.0
    prims: list[Prim] = []
    ax = -1.9 + shift
    prims += [_shape(Ellipse(ax, -5.0, 2.2, 1.7, 0.2), hue, z=0.5), _shape(Ellipse(ax - 1.4, -7.2, 1.6, 1.3, -0.3), hue, "fill", z=0.45)]
    nucleotide = "GTP" if active else "GDP"
    prims += _small(nucleotide.lower(), (ax - 0.6, -6.1), 0.55)
    bx = 2.0
    blades = []
    for k in range(7):
        a = 2 * math.pi * k / 7
        blades.append(line((bx + 0.6 * math.cos(a), -6.2 + 0.6 * math.sin(a)), (bx + 2.0 * math.cos(a), -6.2 + 2.0 * math.sin(a))))
    prims += [_shape(Ellipse(bx, -6.2, 2.1, 2.1), "#5E7FC0", z=0.5), Prim(tuple(blades), None, "solid", "#5E7FC0", 0.8, z=0.6, detail=True),
              _shape(Capsule(bx + 0.4, -3.6, 3.6, 0.7, -0.15), "#8E6BD0", z=0.55)]
    anchors_ = [(ax + 0.6, -3.4), (bx + 2.0, -3.9)]
    for x, y in anchors_:
        prims.append(_line([(x, y), (x + 0.2, -2.6), (x, -1.2)], LIPID_HUE, 0.22, 1.2, z=0.7))
    prims += [_text("Gα", (ax + 0.4, -4.6), 0.7, ON), _text("Gβ", (bx, -6.2), 0.7, ON), _text("Gγ", (bx + 2.6, -3.0), 0.5)]
    anchors = {"g_alpha": (f"Gα ({nucleotide})", (ax, -5.0)), "g_beta": ("Gβ", (bx, -6.2)), "g_gamma": ("Gγ", (bx + 0.4, -3.6)),
               "nucleotide": (nucleotide, (ax - 0.6, -6.1)), "anchor": ("Lipid anchor", (ax + 0.6, -1.8))}
    return Glyph("g_protein", tuple(prims), anchors, _bounds(prims), facts={"nucleotide": nucleotide, "side": "n"})


def gpcr(spec: MoleculeSpec) -> Glyph:
    """A GPCR in the membrane: seven TM α-helices, the N-terminus up on the exoplasmic side,
    extracellular loops ECL1–3 over even-odd helix pairs, intracellular loops ICL1–3 under
    odd-even pairs (ICL3 the longest), helix 8 and the C-terminus on the cytosolic side; when
    active TM6 swings out at its cytosolic end; a ligand in the pocket among the helices."""
    hue = MOLECULES["gpcr"].hue
    active = spec.state == "active"
    prims: list[Prim] = []
    half = 2.15
    tops, bottoms = [], []
    for i in range(7):
        # active: TM6's cytosolic end swings out (about 1 nm here; TM7 and helix 8 make room)
        x = (i - 3) * 1.05 + (0.9 if active and i == 6 else 0.0)
        tilt = 0.12 * (1 if i % 2 else -1)
        top = (x + math.sin(tilt) * half, half)
        bottom = (x - math.sin(tilt) * half, -half)
        if active and i == 5:
            top, bottom = (x - 0.1, half), (x + 1.1, -half)
        tops.append(top)
        bottoms.append(bottom)
        c = ((top[0] + bottom[0]) / 2, 0.0)
        angle = math.atan2(top[1] - bottom[1], top[0] - bottom[0])
        prims.append(_shape(Capsule(c[0], c[1], math.dist(top, bottom) + 0.9, 0.9, angle), hue, "solid" if i % 2 == 0 else "fill", z=0.6))
        prims.append(_text(str(i + 1), c, 0.55, ON))
    loop_hue = hue

    def loop(a: Point, b: Point, depth: float) -> None:
        # a rounded loop bulging a little beyond its two helices' ends
        mid = ((a[0] + b[0]) / 2, a[1] + depth)
        spread = 0.25 + 0.12 * abs(depth)
        prims.append(_line([a, (a[0] - spread * 0.4, a[1] + depth * 0.55), (mid[0] - spread * 0.5, a[1] + depth * 0.95), mid,
                            (mid[0] + spread * 0.5, b[1] + depth * 0.95), (b[0] + spread * 0.4, b[1] + depth * 0.55), b], loop_hue, 0.3, 1.4, z=0.4))

    for i in (1, 3, 5):
        loop(tops[i], tops[i + 1], 0.9 if i != 3 else 1.5)              # ECL1-3 (ECL2 the largest, over the pocket)
    for i in (0, 2, 4):
        loop(bottoms[i], bottoms[i + 1], -(0.9 if i != 4 else 2.2))     # ICL1-3 (ICL3 the longest)
    n_tail = [tops[0], (tops[0][0] - 0.6, 3.4), (tops[0][0] - 1.6, 3.9), (tops[0][0] - 2.4, 4.8)]
    prims.append(_line(n_tail, loop_hue, 0.3, 1.4, z=0.4))
    h8 = (bottoms[6][0] + 1.4, -3.0)
    c_tail = [bottoms[6], (bottoms[6][0] + 0.3, -2.8), h8, (h8[0] + 1.4, -3.4), (h8[0] + 1.9, -4.6)]
    prims += [_line(c_tail, loop_hue, 0.3, 1.4, z=0.4), _shape(Capsule(h8[0] + 0.1, h8[1], 1.9, 0.7, -0.1), hue, "fill", z=0.5)]
    prims += [_text("N", (n_tail[-1][0] - 0.45, n_tail[-1][1] + 0.3), 0.55), _text("C", (c_tail[-1][0] + 0.45, c_tail[-1][1] - 0.2), 0.55)]
    anchors: dict[str, tuple[str, Point]] = {
        "n_terminus": ("N-terminus (extracellular)", n_tail[-1]), "c_terminus": ("C-terminus (cytosolic)", c_tail[-1]),
        "tm_helices": ("7 TM helices", ((tops[3][0] + bottoms[3][0]) / 2, 0.8)), "ecl2": ("ECL2", (0.0, half + 1.5)),
        "icl3": ("ICL3", ((bottoms[4][0] + bottoms[5][0]) / 2, -half - 2.2)), "helix_8": ("Helix 8", h8),
    }
    if spec.ligand:
        prims += _small("ligand", (0.5, 1.15), 1.0)
        anchors["ligand"] = ("Ligand", (0.5, 1.15))
    else:
        anchors["pocket"] = ("Ligand-binding pocket", (0.5, 1.15))
    if active:
        anchors["tm6"] = ("TM6 swung out (active)", bottoms[5])
    sites = tuple(((x, -3.9), (0.0, -1.0)) for x in (h8[0] + 1.6, h8[0] + 0.6, bottoms[5][0]))
    facts = {"n_terminus": n_tail[-1], "c_terminus": c_tail[-1], "helices": 7, "tm6_out": active}
    return Glyph("gpcr", tuple(prims), anchors, _bounds(prims), sites=sites, facts=facts)


def _rtk_monomer(x: float, mirror: float, hue: str, prims: list[Prim]) -> dict[str, Point]:
    prims.append(_shape(Capsule(x, 0.0, 5.2, 0.9, math.pi / 2), hue, z=0.6))
    ecd = [(x + mirror * 0.3, 3.9), (x - mirror * 0.5, 6.6), (x + mirror * 0.2, 9.3)]
    for k, c in enumerate(ecd):
        prims.append(_shape(Ellipse(c[0], c[1], 1.4, 1.2, 0.3 * mirror), hue, "fill" if k % 2 else "solid", z=0.5))
    prims.append(_line([(x, 2.5), ecd[0]], hue, 0.3, 1.4, z=0.4))
    prims.append(_line([(x, -2.5), (x + mirror * 0.4, -3.6)], hue, 0.3, 1.4, z=0.4))
    n_lobe, c_lobe = (x + mirror * 0.5, -4.8), (x + mirror * 0.3, -7.4)
    prims += [_shape(Ellipse(n_lobe[0], n_lobe[1], 1.2, 0.9), "#2E6F99", "fill", z=0.5), _shape(Ellipse(c_lobe[0], c_lobe[1], 1.5, 1.2), "#2E6F99", z=0.5)]
    tail = [(c_lobe[0] - mirror * 0.6, -8.4), (c_lobe[0] - mirror * 1.0, -9.6), (c_lobe[0] - mirror * 0.6, -10.8)]
    prims.append(_line([c_lobe] + tail, hue, 0.25, 1.2, z=0.4))
    return {"ecd": ecd[1], "tm": (x, 0.0), "kinase": c_lobe, "tail": tail[1], "tail_end": tail[2]}


def rtk(spec: MoleculeSpec) -> Glyph:
    """A receptor tyrosine kinase: an extracellular ligand-binding domain, one transmembrane
    helix, a cytosolic tyrosine-kinase domain; as a ligand-bound dimer each kinase phosphorylates
    tyrosines on its partner's tail (trans-autophosphorylation)."""
    hue = MOLECULES["rtk"].hue
    prims: list[Prim] = []
    if spec.state == "dimer":
        left = _rtk_monomer(-1.6, -1.0, hue, prims)
        right = _rtk_monomer(1.6, 1.0, hue, prims)
        prims += _small("ligand", (0.0, 8.0), 1.2)
        for side in (left, right):
            for dy in (0.0, -0.9):
                prims += _marker("P", (side["tail"][0] + (0.65 if side is right else -0.65), side["tail"][1] + dy), 0.4)
        prims += _arrow([left["kinase"], (0.0, -9.2), (right["tail"][0] - 0.5, right["tail"][1] + 0.2)], "#E8B730", 0.1, 0.4)
        anchors = {"ligand": ("Ligand", (0.0, 8.0)), "ecd": ("Ligand-binding domain", right["ecd"]), "tm": ("TM helix", right["tm"]),
                   "kinase": ("Kinase domain", right["kinase"]), "ptyr": ("Phosphotyrosines", (right["tail"][0] + 0.65, right["tail"][1]))}
        sites: tuple[tuple[Point, Point], ...] = ()
    else:
        mono = _rtk_monomer(0.0, 1.0, hue, prims)
        anchors = {"ecd": ("Ligand-binding domain", mono["ecd"]), "tm": ("TM helix", mono["tm"]), "kinase": ("Kinase domain", mono["kinase"])}
        sites = ((mono["tail"], (-1.0, 0.0)), (mono["tail_end"], (-1.0, 0.0)))
    return Glyph("rtk", tuple(prims), anchors, _bounds(prims), sites=sites, facts={"dimer": spec.state == "dimer", "kinase_side": "n"})


def ion_channel(spec: MoleculeSpec) -> Glyph:
    """An ion channel cut through its pore: two of its subunits round the pore, the selectivity
    filter at the outer mouth, the activation gate at the inner end (closed: the helices meet;
    open: apart); a voltage sensor with its + charges (moved outwards when open or inactivated),
    a ligand-binding domain or a tether to the cytoskeleton by ``gating``; a voltage-gated Na⁺
    channel's inactivation gate (a plug on a tether that closes the inner mouth while the
    activation gate is still open); the ion and the way it flows."""
    hue = MOLECULES["ion_channel"].hue
    state = spec.state or "closed"
    open_ = state in ("open", "inactivated")             # the activation gate
    gate = 0.75 if open_ else 0.06
    prims: list[Prim] = []
    for sign in (-1.0, 1.0):
        pts = [(sign * 3.3, 3.0), (sign * 0.75, 3.0), (sign * 0.3, 2.2), (sign * 0.3, 1.4), (sign * 0.9, 0.4), (sign * gate, -2.7), (sign * 1.6, -3.3),
               (sign * 3.0, -2.9)]
        prims.append(_poly(pts, hue, "solid" if sign < 0 else "fill", z=0.6))
    gate_name = "Activation gate" if (spec.gating or "voltage") == "voltage" and (spec.ion == "Na+" or state == "inactivated") else "Gate"
    anchors: dict[str, tuple[str, Point]] = {"filter": ("Selectivity filter", (0.0, 1.8)), "pore": ("Pore", (0.0, 0.0)),
                                             "gate": (gate_name, (0.0, -2.6))}
    gating = spec.gating or "voltage"
    ion = spec.ion or "K+"
    if gating == "voltage":
        lift = 0.9 if open_ else -0.6
        for sign in (-1.0, 1.0):
            c = (sign * 4.6, lift)
            prims.append(_shape(Ellipse(c[0], c[1], 1.0, 2.0), hue, "light", z=0.55))
            for k in range(3):
                prims.append(_text("+", (c[0], c[1] - 1.0 + k), 0.6, "#D9534F", z=2.0))
        anchors["sensor"] = ("Voltage sensor (S4)", (4.6, lift))
        if ion == "Na+" or state == "inactivated":
            # the inactivation gate: a plug tethered to the channel's cytosolic side
            tether = (-2.3, -3.4)
            plug = (0.0, -3.45) if state == "inactivated" else (-3.3, -5.6)
            bend = ((tether[0] + plug[0]) / 2 - 0.4, min(tether[1], plug[1]) - 0.9)
            prims.append(_line([tether, bend, plug], "#2E7F79", 0.2, 1.3, z=0.65))
            prims.append(_shape(Ellipse(plug[0], plug[1], 0.68, 0.6), "#2E7F79", z=0.7))
            anchors["inactivation"] = ("Inactivation gate" + (" (closed)" if state == "inactivated" else ""), plug)
    elif gating == "ligand":
        for sign in (-1.0, 1.0):
            prims.append(_shape(Ellipse(sign * 2.4, 4.4, 1.5, 1.2), hue, "light", z=0.55))
            if open_ and not spec.bare:
                prims += _small("ligand", (sign * 2.4, 5.2), 0.9)
        anchors["binding"] = ("Ligand-binding domain", (2.4, 4.4))
    else:
        for sign in (-1.0, 1.0):
            prims.append(_line([(sign * 2.6, -3.1), (sign * 3.6, -4.5), (sign * 4.4, -5.6)], "#8C6D4F", 0.25, 1.4, z=0.4))
        if not spec.bare:
            prims += _arrow([(-5.6, 0.0), (-7.4, 0.0)], "#8C6D4F", 0.15, 0.5) + _arrow([(5.6, 0.0), (7.4, 0.0)], "#8C6D4F", 0.15, 0.5)
        anchors["tension"] = ("Membrane tension", (6.5, 0.4))
    flow = ION_FLOW.get(ion, "in")
    if not spec.bare:
        if state == "open":
            ys = (3.9, 0.3, -3.9) if flow == "out" else (-3.9, 0.3, 3.9)
            for y in ys:
                prims += _small("ion", (0.0, y), 0.0, ion)
            y0, y1 = (-4.4, 4.6) if flow == "out" else (4.6, -4.4)
            prims += _arrow([(0.0 - 1.3, y0), (-1.3, y1)], ION_HUES.get(ion, "#888888"), 0.12, 0.45)
        else:
            prims += _small("ion", (0.0, -3.9 if flow == "out" else 3.9), 0.0, ion)
    if state == "open":
        anchors["ion"] = (f"{chem_markup(ion)} flows {'out' if flow == 'out' else 'in'}", (0.0, 0.3))
    path = ((0.0, 4.9), (0.0, 1.8), (0.0, 0.3), (0.0, -2.7), (0.0, -4.9))      # outside → cytosol
    return Glyph("ion_channel", tuple(prims), anchors, _bounds(prims), sites=(((-1.6, -3.4), (0.0, -1.0)), ((1.6, -3.4), (0.0, -1.0))),
                 facts={"open": state == "open", "state": state, "gate_gap": 2 * gate, "ion": ion, "flow": flow, "gating": gating, "path": path})


#: The two halves of an alternating-access transporter (x > 0 side; the other is mirrored), as
#: five points from the outer top corner round its inner edge: open to the outside, occluded
#: (a closed cavity round the binding site) or open to the inside.
_ACCESS = {
    "outward": [(1.0, 1.0), (0.36, 1.0), (0.17, 0.2), (0.016, -0.93), (0.84, -0.97)],
    "occluded": [(0.91, 0.98), (0.016, 0.97), (0.19, 0.0), (0.016, -0.97), (0.91, -0.98)],
    "inward": [(0.84, 0.97), (0.016, 0.93), (0.17, -0.2), (0.36, -1.0), (1.0, -1.0)],
}
#: Where an alternating-access transporter's binding site is (share of its half height).
_SITE_Y = {"outward": 0.3, "occluded": 0.0, "inward": -0.3}


def _halves(access: str, half_w: float, half_h: float, cx: float = 0.0) -> list[list[Point]]:
    return [[(cx + sign * x * half_w, y * half_h) for x, y in _ACCESS[access]] for sign in (-1.0, 1.0)]


def bound_positions(center: Point, n: int, step: float = 0.72) -> list[Point]:
    """Where ``n`` bound solutes sit round a binding site: in a row, or two rows for 3 or 4."""
    cx, cy = center
    if n <= 2:
        return [(cx + (k - (n - 1) / 2) * step, cy) for k in range(n)]
    top = (n + 1) // 2
    out = [(cx + (k - (top - 1) / 2) * step, cy + step * 0.45) for k in range(top)]
    return out + [(cx + (k - (n - top - 1) / 2) * step, cy - step * 0.45) for k in range(n - top)]


def _solute_markup(s: str) -> str:
    return chem_markup(s) if s in IONS else MOLECULES[s].label


def carrier(spec: MoleculeSpec) -> Glyph:
    """A carrier in alternating access: its two halves round a central binding site, open to the
    outside (``outward``), closed round its solutes (``occluded``) or open to the inside
    (``inward``) — never open to both — with its solutes bound (``ratio`` of each) and arrows the
    way each moves (symport: the same way; antiport: opposite ways)."""
    hue = MOLECULES["carrier"].hue
    mode, solutes, moves, ratio = carrier_parts(spec)
    state = spec.state or "outward"
    prims: list[Prim] = []
    for sign, pts in zip((-1.0, 1.0), _halves(state, 3.2, 3.0)):
        prims.append(_poly(pts, hue, "solid" if sign < 0 else "fill", z=0.6))
    site = (0.0, _SITE_Y[state] * 3.0)
    words = {"outward": "Outward-open", "occluded": "Occluded", "inward": "Inward-open"}[state]
    anchors: dict[str, tuple[str, Point]] = {"state": (words, (0.0, 2.7 if state == "outward" else -2.7 if state == "inward" else 0.9)),
                                             "site": ("Binding site", site)}
    copies = [s for s, r in zip(solutes, ratio) for _ in range(r)]
    if not spec.bare:
        for s, p in zip(copies, bound_positions(site, len(copies))):
            prims += _small("ion" if s in IONS else s, p, 0.6, s if s in IONS else None)
    for k, (s, way, r) in enumerate(zip(solutes, moves, ratio)):
        x = (-4.6 - 1.4 * (k // 2)) if k % 2 == 0 else (4.6 + 1.4 * (k // 2))
        colour = ION_HUES.get(s, MOLECULES[s].hue if s in MOLECULES else "#888888")
        name = f"{r} {_solute_markup(s)}" if r > 1 else _solute_markup(s)
        if not spec.bare:
            y0, y1 = (3.6, -3.6) if way == "in" else (-3.6, 3.6)
            prims += _arrow([(x, y0), (x, y1)], colour, 0.13, 0.5)
            prims.append(_text(name, (x, y0 + (0.6 if y0 > 0 else -0.6)), 0.55, colour, detail=False))
        anchors[f"solute_{k + 1}"] = (f"{name} ({way})", (x, 0.0))
    facts = {"mode": mode, "solutes": solutes, "moves": moves, "ratio": ratio, "outward": state == "outward", "state": state, "site": site,
             "sites": {a: (0.0, _SITE_Y[a] * 3.0) for a in _SITE_Y}, "mouth_out": (0.0, 3.9), "mouth_in": (0.0, -3.9)}
    return Glyph("carrier", tuple(prims), anchors, _bounds(prims), sites=(((-2.7, -3.1), (0.0, -1.0)),), facts=facts)


#: A P-type pump's four states: which way it is open, its cytosolic domains (A, N: where they
#: are), and whether its P domain carries the phosphate.
_P_STATES = {
    "e1": ("inward", (-3.9, -4.0), (2.2, -6.4), False),
    "e1p": ("occluded", (-3.6, -4.3), (0.9, -6.7), True),
    "e2p": ("outward", (-1.9, -5.4), (1.9, -6.5), True),
    "e2": ("occluded", (-2.6, -4.6), (2.1, -6.4), False),
}


def _p_type(spec: MoleculeSpec, hue: str, beta: bool) -> tuple[list[Prim], dict[str, tuple[str, Point]], dict[str, object]]:
    """The common drawing of a P-type pump: the α subunit's transmembrane domain open to one
    side round its ion sites, its A (actuator), P (phosphorylation) and N (nucleotide-binding)
    domains in the cytosol, the phosphate on the P domain's Asp in E1P and E2P; with ``beta``
    the glycosylated β subunit of the Na⁺/K⁺ pump."""
    state = spec.state or "e1"
    access, a_dom, n_dom, phospho = _P_STATES[state]
    cx = -0.8
    prims: list[Prim] = []
    for sign, pts in zip((-1.0, 1.0), _halves(access, 2.9, 3.0, cx)):
        prims.append(_poly(pts, hue, "solid" if sign < 0 else "fill", z=0.5))
    p_dom = (cx + 0.5, -4.7)
    prims += [_shape(Ellipse(a_dom[0], a_dom[1], 1.35, 1.15), hue, "fill", z=0.52), _shape(Ellipse(p_dom[0], p_dom[1], 1.6, 1.2), hue, "fill", z=0.55),
              _shape(Ellipse(n_dom[0], n_dom[1], 1.45, 1.35), hue, "light", z=0.5)]
    asp = (p_dom[0] + 0.55, p_dom[1] - 1.05)
    if phospho:
        prims += _marker("P", asp, 0.42)
    anchors: dict[str, tuple[str, Point]] = {
        "alpha": ("α subunit", (cx - 1.9, 0.8)), "n_domain": ("N domain (ATP)", n_dom), "p_domain": ("P domain (Asp)", p_dom),
        "a_domain": ("A domain", a_dom), "state": ({"e1": "E1 (open to the cytosol)", "e1p": "E1P (occluded)", "e2p": "E2P (open outside)",
                                                  "e2": "E2 (occluded)"}[state], (cx, 2.4 if access == "outward" else -2.4 if access == "inward" else 0.0))}
    if beta:
        prims += [_shape(Capsule(cx + 3.6, 0.0, 5.0, 0.8, math.pi / 2), "#C98A3A", z=0.55), _shape(Ellipse(cx + 3.9, 3.7, 1.5, 1.1), "#C98A3A", "fill", z=0.5)]
        for k in range(4):
            prims.append(_shape(Ellipse(cx + 4.5 + 0.35 * k, 4.9 + 0.25 * k, 0.17, 0.17), GLYCAN_HUE, z=0.7, detail=True))
        anchors["beta"] = ("β subunit (glycan)", (cx + 3.9, 3.7))
    site = (cx, _SITE_Y[access] * 3.0)
    facts = {"state": state, "access": access, "phosphorylated": phospho, "site": site, "sites": {a: (cx, _SITE_Y[a] * 3.0) for a in _SITE_Y},
             "mouth_out": (cx, 3.9), "mouth_in": (cx - 0.2, -3.5), "atp_site": (n_dom[0] + 0.2, n_dom[1] - 1.75), "asp": asp,
             "n_domains": {k: v[2] for k, v in _P_STATES.items()}, "atp_side": "n"}
    return prims, anchors, facts


def na_k_atpase(spec: MoleculeSpec) -> Glyph:
    """The Na⁺/K⁺ pump in one of the four states of its Post–Albers cycle: E1 (open to the
    cytosol, 3 Na⁺ bound), E1P (phosphorylated, Na⁺ occluded), E2P (open outside, K⁺ bound),
    E2 (dephosphorylated, K⁺ occluded); α subunit with its A, P and N domains, the glycosylated
    β subunit; per ATP 3 Na⁺ out and 2 K⁺ in."""
    hue = MOLECULES["na_k_atpase"].hue
    prims, anchors, facts = _p_type(spec, hue, beta=True)
    state = facts["state"]
    bound = ("Na+", "Na+", "Na+") if state in ("e1", "e1p") else ("K+", "K+")
    if not spec.bare:
        for ion, p in zip(bound, bound_positions(facts["site"], len(bound), 0.75)):  # type: ignore[arg-type]
            prims += _small("ion", p, 0.0, ion)
        if state == "e1":
            prims += _small("atp", facts["atp_site"], 0.6)  # type: ignore[arg-type]
        prims += _arrow([(-5.3, -3.4), (-5.3, 4.4)], ION_HUES["Na+"], 0.15, 0.55) + _arrow([(5.4, 4.4), (5.4, -3.4)], ION_HUES["K+"], 0.15, 0.55)
        prims += [_text("3 Na<sup>+</sup>", (-5.3, 5.1), 0.6, ION_HUES["Na+"], detail=False), _text("2 K<sup>+</sup>", (5.4, -4.1), 0.6, ION_HUES["K+"], detail=False),
                  _text("ATP → ADP + P<sub>i</sub>", (1.2, -9.0), 0.5, detail=False)]
    anchors.update({"sodium": ("3 Na<sup>+</sup> out", (-5.3, 0.5)), "potassium": ("2 K<sup>+</sup> in", (5.4, 0.5))})
    facts.update({"na_out": 3, "k_in": 2, "atp": 1})
    return Glyph("na_k_atpase", tuple(prims), anchors, _bounds(prims), sites=(((-0.3, -5.9), (0.0, -1.0)),), facts=facts)


def h_atpase(spec: MoleculeSpec) -> Glyph:
    """An H⁺ pump: in the plasma membrane the P-type pump (like the Na⁺/K⁺ pump: E1 binds H⁺ in
    the cytosol, is phosphorylated, opens outside as E2P), elsewhere the rotary V-type pump (V₁
    in the cytosol hydrolyses ATP, Vₒ moves H⁺ into the lumen)."""
    if pump_type(spec.membrane) == "v":
        return _v_type(spec)
    hue = MOLECULES["h_atpase"].hue
    prims, anchors, facts = _p_type(spec, hue, beta=False)
    state = facts["state"]
    if not spec.bare:
        if state in ("e1", "e1p"):
            prims += _small("ion", facts["site"], 0.0, "H+")  # type: ignore[arg-type]
        if state == "e1":
            prims += _small("atp", facts["atp_site"], 0.6)  # type: ignore[arg-type]
        prims += _arrow([(-4.6, -3.4), (-4.6, 4.4)], ION_HUES["H+"], 0.15, 0.55)
        prims += [_text("H<sup>+</sup>", (-4.6, 5.1), 0.6, ION_HUES["H+"], detail=False), _text("ATP → ADP + P<sub>i</sub>", (1.2, -9.0), 0.5, detail=False)]
    anchors["proton"] = ("H<sup>+</sup> out of the cytosol", (-4.6, 0.5))
    facts.update({"type": "p", "h_out": 1, "atp": 1})
    return Glyph("h_atpase", tuple(prims), anchors, _bounds(prims), sites=(((-0.3, -5.9), (0.0, -1.0)),), facts=facts)


def _v_type(spec: MoleculeSpec) -> Glyph:
    """The V-ATPase: ATP synthase's architecture run as a pump (V₁ = A₃B₃ in the cytosol, Vₒ with
    its c-ring in the membrane), H⁺ moved from the cytosol into the lumen."""
    base = atp_synthase(MoleculeSpec("atp_synthase", "hydrolysis", c_subunits=10, membrane="inner_mitochondrial_membrane", bare=spec.bare))
    swap = {"α": "A", "β": "B"}
    prims = tuple(replace(p, text=swap.get(p.text, p.text)) for p in base.prims)
    anchors = {"v1": ("V<sub>1</sub> (A<sub>3</sub>B<sub>3</sub>)", base.anchors["f1"][1]), "vo": ("V<sub>o</sub> (c-ring)", base.anchors["fo"][1]),
               "stalk": ("Central stalk", base.anchors["stalk"][1]), "peripheral": ("Peripheral stalks", base.anchors["peripheral"][1]),
               "proton": ("H<sup>+</sup> into the lumen", base.anchors["proton"][1])}
    facts = dict(base.facts, type="v", path=((2.75, -4.9), (2.75, 0.0), (2.75, 4.9)), atp_site=(2.6, -12.6))
    return Glyph("h_atpase", prims, anchors, base.bounds, facts=facts)


#: An ABC transporter's two states: its transmembrane halves (x > 0 side, five points) and how far
#: apart its nucleotide-binding domains are.
_ABC = {
    "inward": ([(0.15, 3.2), (2.6, 3.2), (3.3, -4.0), (1.6, -4.4), (0.9, -0.9)], 2.75),
    "outward": ([(1.25, 3.4), (3.0, 3.2), (2.25, -4.1), (0.55, -4.3), (0.15, -1.1)], 1.32),
}


def abc_transporter(spec: MoleculeSpec) -> Glyph:
    """An ABC transporter: two transmembrane domains round the substrate site and two
    nucleotide-binding domains (NBDs) in the cytosol. Inward-facing: open to the cytosol, NBDs
    apart; with 2 ATP bound the NBDs close on them and the pump turns outward-facing (open to
    the other side); hydrolysis (2 ATP → 2 ADP + 2 Pᵢ) resets it."""
    hue = MOLECULES["abc_transporter"].hue
    state = spec.state or "inward"
    shape, nbd_x = _ABC[state]
    prims: list[Prim] = []
    for sign in (-1.0, 1.0):
        prims.append(_poly([(sign * x, y) for x, y in shape], hue, "solid" if sign < 0 else "fill", z=0.6))
        prims.append(_shape(Ellipse(sign * nbd_x, -5.7, 1.45, 1.2), hue, "light", z=0.55))
    substrate, way = abc_parts(spec)
    site = (0.0, -1.7) if state == "inward" else (0.0, 1.9)
    if not spec.bare:
        if state == "outward":
            prims += _small("atp", (0.0, -5.2), 0.55) + _small("atp", (0.0, -6.2), 0.55)
        prims += _small("ion" if substrate in IONS else substrate, site, 0.8, substrate if substrate in IONS else None)
        colour = ION_HUES.get(substrate, MOLECULES[substrate].hue if substrate in MOLECULES else "#888888")
        y0, y1 = (-3.6, 3.6) if way == "out" else (3.6, -3.6)
        prims += _arrow([(-4.8, y0), (-4.8, y1)], colour, 0.13, 0.5)
        prims += [_text(_solute_markup(substrate), (-4.8, y1 + (0.6 if y1 > 0 else -0.6)), 0.55, colour, detail=False),
                  _text("2 ATP → 2 ADP + 2 P<sub>i</sub>", (0.0, -8.0), 0.5, detail=False)]
    anchors: dict[str, tuple[str, Point]] = {
        "tmd": ("Transmembrane domains", (-2.0, 0.6)), "nbd": ("Nucleotide-binding domains", (nbd_x, -5.7)),
        "state": ("Inward-facing" if state == "inward" else "Outward-facing (NBDs closed on 2 ATP)", (0.0, -3.0 if state == "inward" else 2.9)),
        "substrate": (f"{_solute_markup(substrate)} ({way})", site)}
    facts = {"state": state, "substrate": substrate, "way": way, "site": site, "sites": {"inward": (0.0, -1.7), "outward": (0.0, 1.9)},
             "mouth_out": (0.0, 4.2), "mouth_in": (0.0, -4.6), "nbd_x": {k: v[1] for k, v in _ABC.items()}, "atp_sites": ((0.0, -5.2), (0.0, -6.2))}
    return Glyph("abc_transporter", tuple(prims), anchors, _bounds(prims), facts=facts)


def aquaporin(spec: MoleculeSpec) -> Glyph:
    """An aquaporin subunit cut through its pore: an hourglass narrowing to about 0.3 nm at its
    NPA motifs, water molecules in single file (either way, as the osmotic gradient drives them)."""
    hue = MOLECULES["aquaporin"].hue
    prims: list[Prim] = []
    for sign in (-1.0, 1.0):
        pts = [(sign * 2.9, 3.0), (sign * 0.95, 3.0), (sign * 0.21, 0.0), (sign * 0.95, -3.0), (sign * 2.9, -3.0)]
        prims.append(_poly(pts, hue, "solid" if sign < 0 else "fill", z=0.6))
        prims.append(_text("NPA", (sign * 1.35, 0.0), 0.42, ON, z=2.0))
    if not spec.bare:
        for y in (2.3, 1.15, 0.0, -1.15, -2.3):
            prims += _small("water", (0.0, y), 0.28)
    anchors = {"pore": ("Water pore (single file)", (0.0, 1.6)), "npa": ("NPA motifs (constriction)", (0.0, 0.0))}
    return Glyph("aquaporin", tuple(prims), anchors, _bounds(prims), facts={"path": ((0.0, 4.2), (0.0, 0.0), (0.0, -4.2)), "passes": "water"})


def atp_synthase(spec: MoleculeSpec) -> Glyph:
    """ATP synthase: Fₒ in the membrane (the c-ring, the a subunit beside it), the central stalk
    (γ, ε) from the c-ring into F₁ (α₃β₃, alternating) on the N side (y < 0: matrix, stroma,
    cytoplasm), the peripheral stalk from the a subunit to the top of F₁; protons flow from the
    P side through Fₒ, turning the ring and γ; F₁ makes ATP from ADP and Pᵢ (or, in reverse,
    hydrolyses it)."""
    hue = MOLECULES["atp_synthase"].hue
    c = spec.c_subunits or C_RING.get(spec.membrane or "", 8)
    prims = [_shape(RoundedBox(0.0, 0.0, 5.4, 4.6, 1.0), "#B04A4A", "fill", z=0.5)]
    stripes = []
    visible = c // 2
    for k in range(1, visible):
        x = -2.7 + 5.4 * (1 - math.cos(math.pi * k / visible)) / 2
        stripes.append(line((x, -2.2), (x, 2.2)))
    prims.append(Prim(tuple(stripes), None, "solid", "#B04A4A", 0.8, z=0.6, detail=True))
    prims += [_shape(RoundedBox(3.8, 0.0, 1.8, 4.4, 0.6), "#8C3A3A", z=0.55),
              _shape(Capsule(0.0, -5.4, 6.4, 1.2, math.pi / 2), "#E08A5A", z=0.45),
              _shape(Capsule(4.6, -8.6, 13.0, 0.8, math.pi / 2 + 0.09), "#8C3A3A", "fill", z=0.4)]
    f1 = (0.0, -12.6)
    prims.append(_shape(Ellipse(f1[0], f1[1], 5.0, 4.1), hue, "fill", z=0.5))
    for k, x in enumerate((-3.1, 0.0, 3.1)):
        prims.append(_shape(Ellipse(x, f1[1], 1.75, 3.7), "#D9534F" if k % 2 else "#E89A6A", z=0.6))
        prims.append(_text("β" if k % 2 else "α", (x, f1[1]), 0.8, ON))
    prims.append(_shape(Ellipse(1.6, -16.9, 1.4, 0.8), "#8C3A3A", z=0.55))
    up = spec.state != "hydrolysis"
    path = [(2.75, 4.2), (2.75, 1.0), (2.75, -1.0), (2.75, -4.2)] if up else [(2.75, -4.2), (2.75, -1.0), (2.75, 1.0), (2.75, 4.2)]
    if not spec.bare:
        prims += _arrow(path, ION_HUES["H+"], 0.15, 0.55)
        prims.append(_text("H<sup>+</sup>", (2.75, 4.9 if up else -4.9), 0.6, ION_HUES["H+"], detail=False))
        spin = [(-1.6 * math.cos(a), -5.2 - 0.5 * math.sin(a)) for a in [math.pi * 0.15 + k * 0.2 for k in range(8)]]
        prims += _arrow(spin if up else spin[::-1], "#555555", 0.1, 0.4)
        reaction = "ADP + P<sub>i</sub> → ATP" if up else "ATP → ADP + P<sub>i</sub>"
        prims.append(_text(reaction, (-8.6, f1[1] - 0.2), 0.6, detail=False))
    anchors = {"f1": ("F<sub>1</sub> (α<sub>3</sub>β<sub>3</sub>)", (3.1, f1[1] - 1.5)),
               "fo": (f"F<sub>o</sub> (c<sub>{c}</sub> ring)", (-1.2, 0.0)), "stalk": ("Central stalk (γ)", (0.0, -6.0)),
               "peripheral": ("Peripheral stalk", (4.6, -8.6)), "a_subunit": ("a subunit", (3.8, 0.0)), "proton": ("H<sup>+</sup> path", (2.75, 2.6))}
    return Glyph("atp_synthase", tuple(prims), anchors, _bounds(prims), facts={"f1_center": f1, "c": c, "protons_from": "p" if up else "n"})


# ----- small molecules and markers ---------------------------------------------------------------------


def _small(kind: str, at: Point, size: float, ion: str | None = None) -> list[Prim]:
    """A small molecule's symbol ``size`` nm across at ``at`` (an ion: its hydrated size)."""
    x, y = at
    if kind == "ion":
        name = ion or "Na+"
        r = IONS.get(name, 0.35)
        hue = ION_HUES.get(name, "#888888")
        return [_shape(Ellipse(x, y, r, r), hue, "solid", z=1.4), _text(chem_markup(name), (x, y), r * 0.95, ON, z=2.6, detail=False)]
    if kind == "pi":
        return [_shape(Ellipse(x, y, size / 2, size / 2), PHOSPHATE_HUE, z=1.4), _text("P<sub>i</sub>", (x, y), size * 0.5, ON, z=2.6, detail=False)]
    if kind == "glucose":
        r = size / 2
        hexagon = [(x + r * math.cos(math.pi / 6 + k * math.pi / 3), y + r * math.sin(math.pi / 6 + k * math.pi / 3)) for k in range(6)]
        return [Prim(tuple(polygon(hexagon)), MOLECULES["glucose"].hue, "solid", MOLECULES["glucose"].hue, 0.8, z=1.4),
                _shape(Ellipse(hexagon[1][0], hexagon[1][1], r * 0.18, r * 0.18), "#D9534F", z=1.5, detail=True)]
    if kind == "ligand":
        r = size / 2
        return [Prim(tuple(polygon([(x, y + r), (x + r * 0.8, y), (x, y - r), (x - r * 0.8, y)])), MOLECULES["ligand"].hue, "solid",
                     MOLECULES["ligand"].hue, 0.8, z=1.4)]
    if kind == "water":
        # O with its two H at 104.5°
        out = [_shape(Ellipse(x, y, 0.15, 0.15), "#E06D6D", z=1.4)]
        for a in (math.radians(90 + 52.25), math.radians(90 - 52.25)):
            out.append(_shape(Ellipse(x + 0.17 * math.cos(a), y + 0.17 * math.sin(a), 0.085, 0.085), "#EDEDED", z=1.45))
        return out
    if kind == "o2":
        return [_shape(Ellipse(x - 0.09, y, 0.13, 0.13), "#E06D6D", z=1.4), _shape(Ellipse(x + 0.09, y, 0.13, 0.13), "#E06D6D", z=1.45)]
    if kind == "co2":
        return [_shape(Ellipse(x - 0.17, y, 0.12, 0.12), "#E06D6D", z=1.4), _shape(Ellipse(x + 0.17, y, 0.12, 0.12), "#E06D6D", z=1.4),
                _shape(Ellipse(x, y, 0.12, 0.12), "#6F6F6F", z=1.45)]
    if kind == "drug":
        r = size / 4
        out = []
        for dx in (-r * 0.87, r * 0.87):
            ring = [(x + dx + r * math.cos(math.pi / 6 + k * math.pi / 3), y + r * math.sin(math.pi / 6 + k * math.pi / 3)) for k in range(6)]
            out.append(Prim(tuple(polygon(ring)), MOLECULES["drug"].hue, "solid", MOLECULES["drug"].hue, 0.8, z=1.4))
        return out
    phosphates = {"atp": 3, "adp": 2, "gtp": 3, "gdp": 2, "camp": 1}.get(kind, 0)
    base = "G" if kind in ("gtp", "gdp") else "A"
    scale = size / 1.6
    out: list[Prim] = []
    rp, rr, rb = 0.17 * scale, 0.24 * scale, 0.26 * scale
    xb = x + 0.55 * scale
    out.append(_shape(Ellipse(xb, y, rb * 1.3, rb), BASE_HUES[base], z=1.4))
    out.append(_text(base, (xb, y), rb * 1.1, ON, z=2.6))
    pent = _ring(x, y, rr, 5)
    out.append(Prim(tuple(polygon(pent)), SUGAR_HUE, "solid", SUGAR_HUE, 0.6, z=1.4))
    if kind == "camp":
        out.append(_shape(Ellipse(x, y - 0.42 * scale, rp, rp), PHOSPHATE_HUE, z=1.45))
        out.append(_line([(x - rr * 0.7, y - rr * 0.6), (x - rp * 0.8, y - 0.42 * scale)], PHOSPHATE_HUE, 0.05 * scale, 0.8, z=1.3))
        out.append(_line([(x + rr * 0.7, y - rr * 0.6), (x + rp * 0.8, y - 0.42 * scale)], PHOSPHATE_HUE, 0.05 * scale, 0.8, z=1.3))
        return out
    for k in range(phosphates):
        px = x - rr - rp - k * 2.1 * rp
        out.append(_shape(Ellipse(px, y, rp, rp), PHOSPHATE_HUE, z=1.4))
    return out


def small_molecule(spec: MoleculeSpec) -> Glyph:
    """A small molecule or ion as its symbol (ATP: adenine, ribose and three phosphates;
    GTP / GDP; cAMP with its cyclic phosphate; Pᵢ; glucose's ring; a generic ligand; an ion
    with its charge)."""
    kind = MOLECULES[spec.kind]
    prims = _small(spec.kind, (0.0, 0.0), kind.size, spec.ion)
    name = chem_markup(spec.ion) if spec.kind == "ion" and spec.ion else kind.label
    return Glyph(spec.kind, tuple(prims), {"molecule": (name, (0.0, 0.0))}, _bounds(prims, 0.1))


def _marker(mark: str, at: Point, r: float = 0.45) -> list[Prim]:
    mod = MODIFICATIONS[mark]
    return [_shape(Ellipse(at[0], at[1], r, r), mod.hue, z=1.8), _text(mark, at, r * (1.0 if len(mark) == 1 else 0.8), ON, z=2.8, detail=False)]


def with_modifications(glyph: Glyph, mods: Sequence[tuple[str, ...]], where: str) -> Glyph:
    """``glyph`` with a marker for each modification ((mark, residue[, domain])) at its sites
    (the cytosolic side of a membrane protein; a protein's named domain), the residue written
    beside it."""
    if not mods:
        return glyph
    sites = list(glyph.sites) or [((glyph.bounds[2] - 0.3, glyph.bounds[1] + 0.3), (1.0, 0.0))]
    on_domain = dict(glyph.facts.get("domain_sites", {}))  # type: ignore[call-overload]
    used: dict[int, int] = {}
    prims = list(glyph.prims)
    anchors = dict(glyph.anchors)
    for k, entry in enumerate(mods):
        mark, at = entry[0], entry[1]
        domain = entry[2] if len(entry) > 2 else None  # type: ignore[misc]
        mod, res = check_modification(mark, at, where)
        index = on_domain[domain] if domain in on_domain else k % len(sites)
        (sx, sy), (nx, ny) = sites[index]
        extra = used.get(index, 0) * 1.1                  # a second marker on one site sits further out
        used[index] = used.get(index, 0) + 1
        c = (sx + nx * (0.5 + extra), sy + ny * (0.5 + extra))
        prims += _marker(mark, c)
        if res is not None:
            prims.append(_text(f"{res[0]}{res[1]}", (c[0] + 0.85, c[1] + 0.35), 0.38, detail=False))
        anchors[f"mod_{k + 1}"] = (f"{mod.name.capitalize()}" + (f" ({res[0]}{res[1]})" if res else ""), c)
    return replace(glyph, prims=tuple(prims), anchors=anchors, bounds=_bounds(prims))


_BUILDERS = {"dna": dna, "mrna": mrna, "trna": trna, "rrna": rrna, "nucleosome": lambda s: nucleosome(s, marks=s.marks), "chromatin": chromatin,
             "protein": protein, "kinase": kinase, "phosphatase": phosphatase, "g_protein": g_protein, "gpcr": gpcr, "rtk": rtk,
             "ion_channel": ion_channel, "carrier": carrier, "na_k_atpase": na_k_atpase, "atp_synthase": atp_synthase, "h_atpase": h_atpase,
             "abc_transporter": abc_transporter, "aquaporin": aquaporin}


@lru_cache(maxsize=256)
def molecule_glyph(spec: MoleculeSpec) -> Glyph:
    """The glyph of a checked molecule spec (:func:`check_molecule`), with its modification
    markers (cached: one glyph per spec; do not change it)."""
    build = _BUILDERS.get(spec.kind, small_molecule)
    glyph = build(spec)
    return with_modifications(glyph, spec.modifications, spec.where or spec.kind)


def place(glyph: Glyph, center: Point, angle: float, scale: float = 1.0) -> list[Prim]:
    """The glyph's prims turned by ``angle`` (radians), scaled and moved to ``center`` (texts
    keep reading upright)."""
    out = []
    c, s = math.cos(angle), math.sin(angle)
    for p in glyph.prims:
        curves = tuple(transform(p.curves, angle, center[0], center[1], scale, scale)) if p.curves else ()
        at = (center[0] + scale * (p.at[0] * c - p.at[1] * s), center[1] + scale * (p.at[0] * s + p.at[1] * c))
        out.append(replace(p, curves=curves, at=at, height=p.height * scale, nm=p.nm * scale))
    return out


def anchor_point(glyph: Glyph, name: str, center: Point, angle: float, scale: float = 1.0) -> Point:
    """Where the glyph's anchor ``name`` is once placed."""
    x, y = glyph.anchors[name][1]
    c, s = math.cos(angle), math.sin(angle)
    return (center[0] + scale * (x * c - y * s), center[1] + scale * (x * s + y * c))


def bilayer_span(glyph: Glyph) -> tuple[float, float]:
    """Where a membrane protein's glyph fills the bilayer, along the membrane (nm, local x):
    the lipids give way there."""
    xs = [q[0] for p in glyph.prims if p.fill and not p.text for cv in p.curves for q in cv if abs(q[1]) < BILAYER_NM / 2]
    return (min(xs), max(xs)) if xs else (0.0, 0.0)


def membrane_glyph_ok(glyph: Glyph) -> bool:
    """Whether a membrane protein's glyph spans the bilayer (its outline reaches both faces)."""
    x0, y0, x1, y1 = glyph.bounds
    return y0 < -BILAYER_NM / 2 and y1 > BILAYER_NM / 2


__all__ = ["BASE_HUES", "Glyph", "HISTONE_HUES", "ION_FLOW", "MoleculeSpec", "OPTION_KINDS", "Prim", "abc_parts", "anchor_point", "bilayer_span",
           "bound_positions",
           "carrier_parts", "check_molecule", "membrane_glyph_ok", "molecule_glyph", "place", "small_prims", "with_modifications"]


def small_prims(kind: str, at: Point, ion: str | None = None) -> list[Prim]:
    """The symbol of a small molecule or ion ``kind`` (an ion: ``ion`` names it) at ``at``, at
    its catalog size (a moving particle of a transport animation)."""
    return _small(kind, at, MOLECULES[kind].size if kind in MOLECULES else 0.7, ion)
