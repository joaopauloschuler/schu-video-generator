"""The gene-expression close-up as data (DESIGN.md §95.11): what a ``molecule`` scene with a
``gene`` draws at each moment of each step, without manim. A schematic in *slots* (one slot is
one nucleotide along the DNA, about a ribosome's 1/12): letters must be legible, so DNA and RNA
are stretched about six times against the proteins; the scene says "not to scale".

Every drawn thing is a :class:`Look` (a base, a protein, a tRNA, an amino acid, a label…) with a
key; a :class:`Pose` gives each key a place and an opacity, the backbones as chains of keys and
the camera. A step (:meth:`ExpressionStage.play`) is a :class:`Clip` of captioned phases, each a
function from its progress (0–1) to a pose, built from the pose the step before left. The
renderer (``cell_draw/expression.py``) only draws poses.

Layout (slots, y up): the DNA at y = 0, its coding strand above (5′→3′ left to right) and the
template strand below (3′→5′), so RNA polymerase moves right reading the template 3′→5′ and the
RNA grows 5′→3′; the nascent RNA lies above its DNA; the nuclear envelope above that; the
cytosol above the envelope; the ER membrane above the ribosome once it is targeted (the ER lumen
on top). This module holds the layout and the steps in the nucleus; the cytoplasm's are in
:mod:`vidgen.cellworld.expression_cyto`."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace

from .expression import BUBBLE, CAP_AT, HYBRID, TAIL_DRAWN, TAIL_REAL, ExpressionState, Gene, advance, rna, side_chain
from .glyphs import BASE_HUES

#: Rows of the DNA's strands, the RNA above them (slots).
Y_CODING, Y_TEMPLATE, Y_RNA = 0.55, -0.55, 3.6
#: The nuclear envelope's middle and the mRNA's row in the cytosol.
Y_ENVELOPE, Y_CYTOSOL = 8.8, 14.0
#: A base's tile (slots) and an RNA's backbone offset from its bases.
TILE, BACKBONE = 0.82, 0.52
#: How far the bubble's strands part (slots) and the polymerase's size.
BUBBLE_UP, BUBBLE_DOWN = 1.7, 1.0
POL_W, POL_H = 15.0, 6.6
#: Hues of the proteins and complexes (a hue each; the renderer mixes them into the theme).
HUES = {
    "pol": "#7E6BC4", "tfiid": "#5E9FD6", "tfiia": "#7FB7D9", "tfiib": "#62B6A8", "tfiif": "#9C8BD8", "tfiie": "#C98FD0", "tfiih": "#D98C5F",
    "sigma": "#5E9FD6", "capping": "#C9A86A", "u1": "#E07A5F", "u2": "#3F9F8F", "u2af": "#8FB04F", "tri": "#B07AC0", "spliceosome": "#9C7AC0",
    "cpsf": "#D9734F", "cstf": "#C9A030", "pap": "#4F8FD9", "pabpn1": "#8AB0E0", "xrn2": "#A0A0A0", "cbc": "#E8B730", "ejc": "#9F6FB0",
    "nxf1": "#4FA38E", "dbp5": "#C07A9F", "eif4e": "#E8B730", "pabpc1": "#6FA0D8", "eif4f": "#D9A040", "small": "#9DBFD6", "large": "#7FA3C6",
    "eef1a": "#4FA35E", "eef2": "#D96F5F", "erf1": "#D9534F", "abce1": "#A08060", "srp": "#E08A3C", "sr": "#C98A5F", "sec61": "#5E7FC0",
    "ost": "#6FA86F", "spc": "#B05F7A", "hsp70": "#E0A030", "chaperonin": "#7FA8C0", "bip": "#E0A030", "calnexin": "#8FC08F",
    "glucosidase": "#B0B060", "pdi": "#C0A0D0", "cap": "#D9534F", "trna": "#C9A86A", "membrane": "#B08A5A", "npc": "#8A8FB0",
}
#: Amino-acid colours by side chain.
RESIDUE_HUES = {"hydrophobic": "#E0A030", "polar": "#4FA35E", "acidic": "#D9534F", "basic": "#3F6FC0", "special": "#9A9A9A"}
#: SNFG colours of the sugars of the N-glycan (Varki et al. 2015): glucose and GlcNAc blue, mannose green.
SNFG = {"Glc": "#0072BC", "Man": "#00A651", "GlcNAc": "#0072BC"}

Point = tuple[float, float]


@dataclass(frozen=True)
class Look:
    """One drawn thing: ``kind`` — ``base`` (a nucleotide's tile with its letter), ``blob`` (a
    protein or complex: ``shape``, ``w`` × ``h`` slots, its name), ``bead`` (an amino acid with
    its code), ``dot`` (an amino acid in the exit tunnel), ``trna`` (a tRNA with its anticodon
    letters in ``text``), ``cap`` (m⁷G), ``glycan`` (Glc₃Man₉GlcNAc₂ in SNFG symbols), ``label``
    (text), ``tag`` (a text on a plate), ``box`` (an outline ``w`` × ``h``), ``bracket``,
    ``bar`` (a filled band ``w`` × ``h``), ``arrow`` (the +1 bent arrow), ``membrane`` (a bilayer
    ``w`` long with gaps in ``data``), ``pore`` (a nuclear pore complex)."""

    key: str
    kind: str
    text: str = ""
    hue: str = "#888888"
    w: float = 0.0
    h: float = 0.0
    shape: str = "ellipse"
    z: float = 0.0
    data: tuple = ()


@dataclass
class Pose:
    """One moment: each key's ``(x, y, opacity)``, the chains drawn through keys (``lines``:
    name → ``(keys, dy, hue, opacity)``), pairing rungs (name → ``(key a, key b, opacity)``) and
    the camera's centre (slots)."""

    els: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    lines: dict[str, tuple[tuple[str, ...], float, str, float]] = field(default_factory=dict)
    rungs: dict[str, tuple[str, str, float]] = field(default_factory=dict)
    cam: Point = (0.0, 0.0)
    chain: tuple[str, ...] = ()            # the RNA's keys 5′→3′ (its ends are labelled)
    readout: tuple[float, float] | None = None   # the protein written out: residues made, finished (0–1)
    loose: tuple[str, ...] = ()                  # glycans on their way to their Asn (not yet riding on it)

    def copy(self) -> "Pose":
        return Pose(dict(self.els), dict(self.lines), dict(self.rungs), self.cam, self.chain, self.readout, self.loose)

    def at(self, key: str) -> Point:
        x, y, _ = self.els[key]
        return (x, y)

    def put(self, key: str, x: float, y: float, o: float | None = None) -> None:
        old = self.els.get(key)
        self.els[key] = (x, y, (old[2] if old else 0.0) if o is None else o)

    def fade(self, key: str, o: float) -> None:
        x, y, _ = self.els[key]
        self.els[key] = (x, y, o)

    def opacity(self, key: str) -> float:
        return self.els[key][2] if key in self.els else 0.0


Phase = tuple[float, str, Callable[[float], Pose]]


@dataclass
class Clip:
    """A step as captioned phases: ``(weight, caption, pose of progress 0–1)``; ``end``: its last
    pose, ``state``: the expression state after it."""

    phases: list[Phase]
    end: Pose
    state: ExpressionState

    def edges(self) -> list[float]:
        total = sum(w for w, _, _ in self.phases) or 1.0
        out = [0.0]
        for w, _, _ in self.phases:
            out.append(out[-1] + w / total)
        return out

    def at(self, alpha: float) -> Pose:
        """The pose ``alpha`` (0–1) into the step."""
        edges = self.edges()
        for k, (_, _, fn) in enumerate(self.phases):
            a, b = edges[k], edges[k + 1]
            if alpha <= b or k == len(self.phases) - 1:
                return fn(min(1.0, max(0.0, (alpha - a) / (b - a))) if b > a else 1.0)
        return self.end


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def window(t: float, a: float, b: float) -> float:
    """0 before ``a``, 1 after ``b``, eased between."""
    return ease((t - a) / (b - a)) if b > a else float(t >= b)


def mix(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def along(path: list[Point], s: float) -> Point:
    """The point at arc length ``s`` along a polyline (extended straight past its ends)."""
    if s <= 0:
        (x0, y0), (x1, y1) = path[0], path[1]
        d = math.dist(path[0], path[1]) or 1.0
        return (x0 + (x0 - x1) / d * -s, y0 + (y0 - y1) / d * -s)
    for a, b in zip(path, path[1:]):
        d = math.dist(a, b)
        if s <= d or (a, b) == (path[-2], path[-1]):
            u = s / d if d > 0 else 0.0
            return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        s -= d
    return path[-1]


def path_length(path: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(path, path[1:]))


class Builder:
    """Builds a :class:`Clip` phase by phase, each from the pose the one before left."""

    def __init__(self, stage: "ExpressionStage") -> None:
        self.stage = stage
        self.phases: list[Phase] = []
        self.pose = stage.pose.copy()

    def phase(self, weight: float, note: str, fn: Callable[[Pose, float], Pose]) -> None:
        start = self.pose
        decorate = self.stage.decorate

        def at(u: float, start: Pose = start, fn: Callable[[Pose, float], Pose] = fn) -> Pose:
            return decorate(fn(start, u))

        self.phases.append((weight, note, at))
        self.pose = at(1.0)


class ExpressionStage:
    """The close-up of one gene's expression: its looks, the pose now and the steps that move it
    on. ``window``: the slots the view spans across, ``aspect``: the view's width over its height,
    ``codes``: ``three`` or ``one``-letter amino acids, ``start``: ``dna`` or ``mrna``."""

    def __init__(self, gene: Gene, window: float, aspect: float, codes: str = "three", start: str = "dna", cap_later: bool = False,
                 strip: float = 1.4, wide: bool | None = None) -> None:
        self.gene, self.window, self.aspect, self.codes, self.cap_later = gene, window, aspect, codes, cap_later
        self.height = window / aspect
        self.strip = strip                       # slots under the view for the protein's readout and the legend
        self.wide = aspect >= 1.0 if wide is None else wide  # a wide frame's layout (a tall frame's view can be wider than tall)
        self.row = 12 if self.wide else 7    # beads per row of a chain outside the ribosome
        self.euk = gene.eukaryote
        self.p0 = len(gene.promoter)                    # DNA index of +1
        self.dna = gene.promoter + gene.region + gene.downstream
        self.template = "".join({"A": "T", "T": "A", "G": "C", "C": "G"}[b] for b in self.dna)
        self.rna = rna(gene.region)
        self.mature_keys = [f"m{i}" for a, b in gene.exons() for i in range(a, b)]
        self.looks: dict[str, Look] = {}
        self.line_names: list[str] = []
        self.rung_names: list[str] = []
        self.state = ExpressionState.at_start(gene, start)
        self.rna_y = Y_RNA if start == "dna" else Y_CYTOSOL      # where the free (pre-)mRNA lies now (read while building)
        riser = self._riser(0.0, 1.0)
        self.riser_shift = path_length(riser) - (riser[0][0] - riser[-1][0])
        self.dna_keys = [f"c{j}" for j in range(len(self.dna))] + [f"t{j}" for j in range(len(self.dna))]
        self._make_looks()
        self.dna_keys += [k for k, look in self.looks.items() if k.startswith(("box_", "exon", "intron", "tss"))]
        self.dna_keys += ["pol", "tfiid", "tfiia", "tfiib", "tfiif", "tfiie", "tfiih", "ctd", "sigma", "bubble_note", "capping"]
        self.pose = self._first_pose(start)

    # ----- looks ---------------------------------------------------------------------------------

    def _add(self, look: Look) -> None:
        self.looks[look.key] = look

    def label(self, key: str, text: str, size: float = 0.62, hue: str = "", z: float = 6.0) -> None:
        self._add(Look(key, "label", text, hue, h=size, z=z))

    def blob(self, key: str, text: str, hue_key: str, w: float, h: float, shape: str = "ellipse", z: float = 1.0) -> None:
        self._add(Look(key, "blob", text, HUES[hue_key], w, h, shape, z))

    def _make_looks(self) -> None:
        g = self.gene
        for j, b in enumerate(self.dna):
            self._add(Look(f"c{j}", "base", b, BASE_HUES[b], TILE, TILE, z=2.0))
            self._add(Look(f"t{j}", "base", self.template[j], BASE_HUES[self.template[j]], TILE, TILE, z=2.0))
            self.rung_names.append(f"bp{j}")
        for i, b in enumerate(self.rna):
            self._add(Look(f"m{i}", "base", b, BASE_HUES[b], TILE, TILE, z=3.0))
            self.rung_names.append(f"h{i}")
        for k in range(TAIL_DRAWN):
            self._add(Look(f"a{k}", "base", "A", BASE_HUES["A"], TILE, TILE, z=3.0))
        self._add(Look("cap", "cap", "m<sup>7</sup>G", HUES["cap"], 1.5, 1.0, z=3.5))
        self.label("polya_n", f"(A)<sub>~{TAIL_REAL}</sub>", 0.6)
        self.line_names += ["coding", "template", "rna", "rna_cut", "downstream_rna"]
        for k, _ in enumerate(g.introns):
            self.line_names += [f"loop{k}", f"tail{k}", f"rna{k}"]
        self.label("rna5", "5′", 0.62)
        self.label("rna3", "3′", 0.62)
        for name in ("c5", "c3", "t3", "t5"):
            self.label(f"end_{name}", {"c5": "5′", "c3": "3′", "t3": "3′", "t5": "5′"}[name], 0.62)
        self._add(Look("legend", "label", "DNA: coding strand 5′→3′ above, template strand 3′→5′ below" if self.wide else
                       "coding strand above, template below", "dim", h=0.55, z=7.0, data=(("anchor", "left"),)))
        # promoter and gene features on the DNA
        for name, a, b in g.boxes:
            self._add(Look(f"box_{name}", "bracket", name, "#5E9FD6", b - a, 0.5, z=4.0, data=(("below", True),)))
        self._add(Look("tss", "arrow", "+1", "#4FA35E", 1.6, 1.2, z=4.0))
        for k, (a, b) in enumerate(g.exons()):
            self._add(Look(f"exon{k}", "bar", f"exon {k + 1}", "#4F8FD9", b - a, 0.28, z=1.0))
        for k, intron in enumerate(g.introns):
            self._add(Look(f"intron{k}", "bar", f"intron {k + 1}" if len(g.introns) > 1 else "intron", "#A0A0A0", intron.length, 0.28, z=1.0))
        if g.polya_signal is not None:
            self._add(Look("box_polya", "bracket", "poly(A) signal", "#D9734F", 6, 0.5, z=4.0))
        # the transcription machinery
        self.blob("pol", "RNA polymerase II" if self.euk else "RNA polymerase", "pol", POL_W, POL_H, "round", z=1.0)
        if self.euk:
            self.blob("tfiid", "TFIID (TBP)", "tfiid", 5.0, 2.4)
            self.blob("tfiia", "TFIIA", "tfiia", 2.8, 1.5)
            self.blob("tfiib", "TFIIB", "tfiib", 2.8, 1.6)
            self.blob("tfiif", "TFIIF", "tfiif", 3.0, 1.6)
            self.blob("tfiie", "TFIIE", "tfiie", 3.0, 1.6)
            self.blob("tfiih", "TFIIH", "tfiih", 4.0, 2.0)
            self.label("ctd", "CTD Ser5-P", 0.5, "dim")
            self.blob("capping", "capping enzyme", "capping", 5.2, 1.8)
        else:
            self.blob("sigma", "σ<sup>70</sup>", "sigma", 4.0, 2.0)
        self._add(Look("bubble_note", "label", f"bubble ~{BUBBLE} bp", "dim", h=0.5, z=6.0))
        # splicing
        for k, _ in enumerate(g.introns):
            self.blob(f"u1_{k}", "U1", "u1", 2.2, 1.6)
            self.blob(f"u2_{k}", "U2", "u2", 2.2, 1.6)
            self.blob(f"u2af_{k}", "U2AF", "u2af", 3.0, 1.4)
            self.blob(f"tri_{k}", "U4/U6·U5", "tri", 4.4, 1.8)
            r = (_.branch - _.start + 1) / (2 * math.pi)
            self._add(Look(f"sp_{k}", "blob", "spliceosome", HUES["spliceosome"], 2 * r + 4.0, 2 * r + 2.6, "ellipse", 0.5,
                           (("label_at", 0.0, r + 0.75),)))
            self.blob(f"ejc_{k}", "EJC", "ejc", 2.2, 1.4, z=3.6)
            self.label(f"branch_{k}", "A", 0.5, "dim")
            self.label(f"ss5_{k}", "GU", 0.5, "dim")
            self.label(f"ss3_{k}", "AG", 0.5, "dim")
        # 3′ end
        self.blob("cpsf", "CPSF", "cpsf", 3.6, 1.8)
        self.blob("cstf", "CstF", "cstf", 3.2, 1.6)
        self.blob("pap", "poly(A) polymerase", "pap", 5.6, 1.8)
        self.blob("xrn2", "Xrn2", "xrn2", 2.6, 1.5)
        for k in range(3):
            self.blob(f"pabpn1_{k}", "PABPN1", "pabpn1", 2.8, 1.3, z=3.6)
        # export
        self.blob("cbc", "CBC", "cbc", 2.2, 1.6, z=3.6)
        for k in range(2):
            self.blob(f"nxf1_{k}", "NXF1–NXT1", "nxf1", 4.2, 1.5, z=3.6)
        self.blob("dbp5", "Dbp5", "dbp5", 2.6, 1.5, z=3.6)
        self._add(Look("envelope", "membrane", "", HUES["membrane"], 400.0, 1.6, data=(("gap", 0.0, 3.4),), z=0.0))
        self._add(Look("envelope_in", "membrane", "", HUES["membrane"], 400.0, 1.6, data=(("gap", 0.0, 3.4),), z=0.0))
        self._add(Look("npc", "pore", "nuclear pore complex", HUES["npc"], 3.4, 6.4, z=0.5))
        for name, text in (("lab_nucleoplasm", "nucleoplasm"), ("lab_cytosol", "cytosol"), ("lab_envelope", "nuclear envelope"),
                           ("lab_perinuclear", "perinuclear space (= ER lumen)")):
            self.label(name, text, 0.6, "dim")
        from .expression_cyto import make_cyto_looks
        make_cyto_looks(self)

    # ----- the first pose ------------------------------------------------------------------------

    def x_dna(self, j: int) -> float:
        """The x (slots) of DNA index ``j`` (+1 at 0)."""
        return float(j - self.p0)

    def _first_pose(self, start: str) -> Pose:
        p = Pose()
        for key in self.looks:
            p.els[key] = (0.0, -100.0, 0.0)
        for name in self.line_names:
            p.lines[name] = ((), BACKBONE, "rna", 0.0)
        for name in self.rung_names:
            p.rungs[name] = ("", "", 0.0)
        shown = 1.0 if start == "dna" else 0.0
        self.dna_rows(p, None, 0.0, shown)
        self.rna_flat(p, Y_RNA, 0.0)
        self.dna_features(p, shown)
        p.lines["coding"] = (tuple(f"c{j}" for j in range(len(self.dna))), BACKBONE, "dna", shown)
        p.lines["template"] = (tuple(f"t{j}" for j in range(len(self.dna))), -BACKBONE, "dna", shown)
        p.cam = (-12.5 if self.window >= 34 else -20.0, 1.8)
        if start == "mrna":
            from .expression_cyto import cytosol_mrna
            cytosol_mrna(self, p)
        return self.decorate(p)

    def dna_rows(self, p: Pose, pol: float | None, opened: float, o: float = 1.0) -> None:
        """The DNA's tiles and base-pair rungs, with a bubble round the polymerase's active site
        (region index ``pol``) opened by ``opened`` (0–1)."""
        for j in range(len(self.dna)):
            x = self.x_dna(j)
            up, down = self.bubble(x, pol, opened)
            p.els[f"c{j}"] = (x, Y_CODING + up, o)
            p.els[f"t{j}"] = (x, Y_TEMPLATE - down, o)
            paired = 1.0 - min(1.0, up / 0.35) if up > 0 else 1.0
            p.rungs[f"bp{j}"] = (f"c{j}", f"t{j}", o * paired)

    def bubble(self, x: float, pol: float | None, opened: float) -> tuple[float, float]:
        """How far the coding strand rises and the template strand drops at ``x`` (the bubble's
        13 bp: the 8–9 bp hybrid behind the active site and a few bp ahead of it)."""
        if pol is None or opened <= 0:
            return 0.0, 0.0
        a, b = pol - (BUBBLE - 4), pol + 3.0
        if x < a - 1.5 or x > b + 1.5:
            return 0.0, 0.0
        mid, half = (a + b) / 2, (b - a) / 2 + 1.5
        u = max(0.0, 1.0 - abs(x - mid) / half)
        shape = ease(min(1.0, u * 2.2))
        return BUBBLE_UP * shape * opened, BUBBLE_DOWN * shape * opened

    def dna_features(self, p: Pose, o: float) -> None:
        """Promoter boxes, +1, exon and intron bands, the poly(A) signal."""
        g = self.gene
        for name, a, b in g.boxes:
            p.els[f"box_{name}"] = (self.x_dna(a) + (b - a - 1) / 2, Y_TEMPLATE - 1.0, o)
        p.els["tss"] = (0.6, Y_CODING + 1.2, o)
        for k, (a, b) in enumerate(g.exons()):
            p.els[f"exon{k}"] = (self.x_dna(self.p0 + a) + (b - a - 1) / 2, Y_TEMPLATE - 0.95, o)
        for k, intron in enumerate(g.introns):
            p.els[f"intron{k}"] = (self.x_dna(self.p0 + intron.start) + (intron.length - 1) / 2, Y_TEMPLATE - 0.95, o)
        if g.polya_signal is not None:
            p.els["box_polya"] = (self.x_dna(self.p0 + g.polya_signal) + 2.5, Y_CODING + 1.0, o)

    def rna_flat(self, p: Pose, y: float, o: float, keys: Iterable[str] | None = None) -> None:
        """RNA bases on a straight row at ``y``, each above its own DNA (shifted as the end of
        transcription leaves them)."""
        for i in range(len(self.rna)):
            key = f"m{i}"
            if keys is not None and key not in keys:
                continue
            p.els[key] = (self.flat_x(i), y, o)

    def flat_x(self, i: int) -> float:
        """Where RNA base ``i`` (a region index) lies once off the polymerase (slots)."""
        return float(i) + self.riser_shift

    # ----- decoration: what follows the camera ---------------------------------------------------------

    def decorate(self, p: Pose) -> Pose:
        """Labels pinned to the view's edges (the strands' ends and names, the compartment) and
        the RNA's 5′ / 3′ ends."""
        cx, cy = p.cam
        half = self.window / 2
        left, right = cx - half + EDGE_LABEL, cx + half - EDGE_LABEL
        dna_o = max(p.opacity("c0"), p.opacity(f"c{len(self.dna) - 1}"), p.opacity(f"c{self.p0}"))
        first_x, last_x = self.x_dna(0), self.x_dna(len(self.dna) - 1)
        if dna_o > 0:
            def row_y(prefix: str, x: float) -> float:
                j = int(round(x + self.p0))
                j = max(0, min(len(self.dna) - 1, j))
                return p.els[f"{prefix}{j}"][1]
            lx = max(left, first_x - 1.0)
            rx = min(right, last_x + 1.0)
            # not where the strands leave the view at its top or bottom
            seen = min(1.0, max(0.0, (self.height / 2 - abs(cy) - 1.0) / 0.8))
            for key, x, prefix, dy in (("end_c5", lx, "c", 0.05), ("end_t3", lx, "t", -0.05), ("end_c3", rx, "c", 0.05), ("end_t5", rx, "t", -0.05)):
                p.els[key] = (x, row_y(prefix, x) + dy, dna_o * seen)
        else:
            for key in ("end_c5", "end_t3", "end_c3", "end_t5"):
                p.els[key] = (cx, cy - 100, 0.0)
        strip_y = cy - self.height / 2 - self.strip / 2
        reading = p.readout is not None and p.readout[0] > 0
        p.els["legend"] = (cx - half + 0.3, strip_y, dna_o * (0.0 if reading else 1.0))
        # the RNA's ends: beside the first and last bases shown
        rna_keys = [k for k in p.chain if p.opacity(k) > 0.5]
        if rna_keys:
            first, last = rna_keys[0], rna_keys[-1]
            fx, fy = p.at(first)
            lx, ly = p.at(last)
            if p.opacity("cap") > 0.5:
                fx = p.at("cap")[0] - 0.75
            free = 1.0 if p.opacity("pol") < 0.5 else 0.0          # the 3′ end is inside the polymerase
            level = abs(fy - ly) < 0.3                               # not on its way through a pore
            p.els["rna5"] = (fx - 0.9, fy + 0.05, 1.0 if level or free == 0 else 0.0)
            p.els["rna3"] = (lx + 0.9, ly + 0.05, free if level else 0.0)
        else:
            p.els["rna5"] = (cx, cy - 100, 0.0)
            p.els["rna3"] = (cx, cy - 100, 0.0)
        from .expression_cyto import glycans_follow, place_readout
        place_readout(self, p)
        glycans_follow(self, p)
        return p

    def chain_order(self, state: ExpressionState | None = None) -> list[str]:
        """The RNA's keys in chain order in ``state`` (default: now): the pre-mRNA (with the
        stretch still in the polymerase), or the mature mRNA, and the tail."""
        state = state or self.state
        cut = self.gene.cleavage if state.tailed else len(self.rna)
        keys = [k for k in self.mature_keys] if state.spliced else [f"m{i}" for i in range(self.gene.cleavage)]
        keys += [f"m{i}" for i in range(self.gene.cleavage, cut)]
        if state.tailed:
            keys += [f"a{k}" for k in range(TAIL_DRAWN)]
        return keys

    # ----- playing steps ------------------------------------------------------------------------------

    def play(self, step: str, options: dict[str, object]) -> Clip:
        """The clip of ``step`` from the pose now; the stage moves on to its end."""
        from . import expression_cyto as cyto
        builders: dict[str, Callable[[Builder, dict[str, object]], None]] = {
            "transcribe": self._transcribe, "cap": self._cap, "splice": self._splice, "polyadenylate": self._polyadenylate,
            "export": self._export, "translate": cyto.translate, "target_er": cyto.target_er, "glycosylate": cyto.glycosylate,
            "fold": cyto.fold,
        }
        b = Builder(self)
        builders[step](b, options)
        state = advance(self.gene, self.state, step, {**options, "cap_later": self.cap_later})
        self.state = state
        self.pose = b.pose
        return Clip(b.phases, b.pose, state)

    # ----- transcription ---------------------------------------------------------------------------

    def transcribing(self, p: Pose, length: float, opened: float = 1.0, cap: float = 0.0) -> None:
        """The DNA, the polymerase and the nascent RNA with ``length`` nt made (fractional while
        the next is added): the bubble round the active site, the 8 bp RNA–DNA hybrid on the
        template strand, the RNA leaving the polymerase and lying above its DNA."""
        active = length - 1.0                                          # region index of the 3′ end
        self.dna_rows(p, max(active, 0.0), opened)
        n_made = int(math.floor(length + 1e-9))
        riser = self._riser(active, opened)
        rise_len = path_length(riser)
        for i in range(len(self.rna)):
            key = f"m{i}"
            if i >= n_made + 1 or i > active + 0.999:
                p.els[key] = (float(i), Y_TEMPLATE + 1.05, 0.0)
                p.rungs[f"h{i}"] = (key, f"t{self.p0 + i}", 0.0)
                continue
            appear = min(1.0, max(0.0, (length - i) * 2.0))
            if i > active - HYBRID:
                x = float(i)
                y = p.els[f"t{self.p0 + i}"][1] + 1.05
                p.els[key] = (x, y, appear)
                p.rungs[f"h{i}"] = (key, f"t{self.p0 + i}", appear)
            else:
                s = (active - HYBRID + 0.5 - i)
                if s <= rise_len:
                    x, y = along(riser, s)
                else:
                    x, y = riser[-1][0] - (s - rise_len), Y_RNA
                p.els[key] = (x, y, 1.0)
                p.rungs[f"h{i}"] = (key, f"t{self.p0 + i}", 0.0)
        p.els["pol"] = (max(active, 0.0) - 2.5, 0.5, 1.0)
        if cap > 0:
            fx, fy = p.at("m0")
            p.els["cap"] = (fx - 1.35, fy, cap)
        made = tuple(f"m{i}" for i in range(min(len(self.rna), n_made + 1)) if p.els[f"m{i}"][2] > 0)
        p.lines["rna"] = (made, BACKBONE, "rna", 1.0)
        p.chain = made

    def _follow_pol(self, active: float) -> float:
        """The camera's x while the polymerase transcribes: the RNA's 5′ end (and its cap) in
        view as long as the polymerase is too, then the polymerase, never past the DNA's end."""
        half = self.window / 2
        x5 = self.flat_x(0) - 2.4
        want = max(active + 7.5 - half, min(x5 + half - 1.0, active - 2.0))
        return min(want, self.x_dna(len(self.dna) - 1) + 1.5 - half)

    def _riser(self, active: float, opened: float) -> list[Point]:
        """The RNA's way out of the polymerase: from the hybrid's 5′ end up to the RNA's row."""
        exit_x = active - HYBRID + 0.5
        return [(exit_x, Y_TEMPLATE - BUBBLE_DOWN * opened + 1.05), (exit_x - 0.9, 1.6), (exit_x - 1.6, Y_RNA - 0.5), (exit_x - 2.4, Y_RNA)]

    def _transcribe(self, b: Builder, options: dict[str, object]) -> None:
        g = self.gene
        euk = self.euk
        cap_now = euk and not self.cap_later
        cam_y = 1.8
        tata = g.boxes[0]
        wide = self.window >= 34
        cam_a = -12.5 if wide else self.x_dna(tata[1]) + 4.0         # the promoter (and the start site when it fits)
        cam_b = -12.5 if wide else -3.0                               # the preinitiation complex

        def assemble(start: Pose, u: float) -> Pose:
            p = start.copy()
            p.cam = mix(start.cam, (cam_a, cam_y), ease(u * 1.6))
            if euk:
                x_tbp = self.x_dna(tata[1]) + 3.5
                p.els["tfiid"] = (x_tbp, Y_CODING + 2.6 - 1.2 * window(u, 0.0, 0.3), window(u, 0.0, 0.25))
                p.els["tfiia"] = (x_tbp - 4.0, Y_CODING + 2.0, window(u, 0.3, 0.5))
                p.els["tfiib"] = (x_tbp + 4.2, Y_CODING + 1.7, window(u, 0.45, 0.65))
                p.els["box_TATA box"] = (p.els["box_TATA box"][0], p.els["box_TATA box"][1], 1.0)
            else:
                p.els["sigma"] = (self.x_dna(self.p0) - 22.0, Y_CODING + 3.0, window(u, 0.2, 0.5))
            return p

        def pic(start: Pose, u: float) -> Pose:
            p = start.copy()
            pol_target = (-2.5, 0.5)
            pol_from = (-2.5, 9.0)
            p.els["pol"] = (*mix(pol_from, pol_target, window(u, 0.0, 0.55)), window(u, 0.0, 0.3))
            if euk:
                p.els["tfiif"] = (*mix((pol_from[0] - 6.0, pol_from[1] + 2.0), (pol_target[0] - 6.0, 3.4), window(u, 0.0, 0.55)),
                                  window(u, 0.05, 0.4))
                p.els["tfiie"] = (pol_target[0] + 6.6, 3.0, window(u, 0.5, 0.75))
                p.els["tfiih"] = (pol_target[0] + 7.4, 0.4, window(u, 0.6, 0.85))
            else:
                p.els["sigma"] = (pol_target[0] - 4.5, 3.6, 1.0)
            p.cam = mix(start.cam, (cam_b, cam_y), ease(u))
            return p

        def open_(start: Pose, u: float) -> Pose:
            p = start.copy()
            self.transcribing(p, 0.0 + 2.0 * window(u, 0.5, 1.0), window(u, 0.0, 0.5))
            if euk:
                p.els["ctd"] = (-7.6, -2.15, window(u, 0.45, 0.7))
                p.fade("tfiih", 1.0)
            p.els["bubble_note"] = (3.0, -2.4, window(u, 0.2, 0.4) * (1.0 - window(u, 0.85, 1.0)))
            return p

        total = len(self.rna)
        stops = [CAP_AT, CAP_AT + 12, max(CAP_AT + 13, g.cleavage - 18), total] if cap_now else [CAP_AT, max(CAP_AT + 1, g.cleavage - 18), total]

        def elongate(lo: float, hi: float, leave: bool = False, cap: tuple[float, float] | None = None) -> Callable[[Pose, float], Pose]:
            def fn(start: Pose, u: float) -> Pose:
                p = start.copy()
                length = lo + (hi - lo) * u
                capping = 0.0
                if cap is not None:
                    capping = window(u, 0.25, 0.85)
                elif p.opacity("cap") > 0:
                    capping = 1.0
                self.transcribing(p, length, 1.0, capping)
                active = length - 1
                p.cam = mix(start.cam, (self._follow_pol(active), cam_y), min(1.0, ease(u * 4)))
                if leave and euk:
                    # promoter escape: the general factors stay behind (TFIID on the TATA box)
                    for key in ("tfiia", "tfiib", "tfiif", "tfiie", "tfiih"):
                        p.fade(key, 1.0 - window(u, 0.0, 0.35))
                    p.els["ctd"] = (active - 7.6, -2.15, p.opacity("ctd"))
                elif not euk and leave:
                    sx, sy = start.at("sigma")
                    p.els["sigma"] = (sx - 3 * u, sy + 3 * u, 1.0 - window(u, 0.0, 0.4))
                elif euk:
                    p.els["ctd"] = (active - 7.6, -2.15, p.opacity("ctd"))
                if cap is not None:
                    fx, fy = p.at("m0")
                    p.els["capping"] = (fx + 1.5, fy + 1.9, window(u, 0.0, 0.25) * (1.0 - window(u, 0.85, 1.0)))
                return p
            return fn

        b.phase(1.2, "TFIID's TATA-binding protein (TBP) binds the TATA box (−30) and bends the DNA; TFIIA and TFIIB join" if euk
                else "The σ<sup>70</sup> factor of the RNA polymerase holoenzyme recognises the −35 and −10 boxes of the promoter", assemble)
        b.phase(1.2, "RNA polymerase II joins with TFIIF, then TFIIE and TFIIH: the preinitiation complex at the promoter" if euk
                else "The holoenzyme binds the promoter (closed complex)", pic)
        b.phase(1.0, "TFIIH unwinds the DNA at the start site (+1): a transcription bubble of ~13 bp; TFIIH's kinase phosphorylates "
                     "Ser5 of the polymerase's C-terminal domain (CTD)" if euk else
                     "The polymerase melts the DNA from −10 to +2: the open complex; RNA synthesis starts at +1", open_)
        lo = 2.0
        notes = ["Elongation: the polymerase reads the template strand 3′→5′ and makes RNA 5′→3′ — A pairs with U, G with C; an RNA–DNA "
                 "hybrid of ~8 bp sits in the bubble" if euk else
                 "σ<sup>70</sup> leaves; the core polymerase reads the template strand 3′→5′ and makes RNA 5′→3′ (A pairs with U)"]
        if cap_now:
            notes.append("At ~25 nt the 5′ end leaves the polymerase: the capping enzyme, bound to the Ser5-phosphorylated CTD, adds a "
                         "7-methylguanosine cap (5′–5′ triphosphate)")
        notes.append("Introns are transcribed with the exons: the primary transcript (pre-mRNA) copies the whole gene" if g.introns else
                     "Elongation goes on at 20–70 nt per second")
        notes.append("The polymerase transcribes the poly(A) signal (AAUAAA) and goes on; CPSF and CstF ride on its CTD to the RNA" if euk else
                     "A GC-rich hairpin and a run of U form the terminator: the polymerase lets go of the RNA and the DNA")
        for k, hi in enumerate(stops):
            hi = float(min(hi, total))
            if hi <= lo:
                continue
            fn = elongate(lo, hi, leave=(k == 0), cap=(0.0, 1.0) if cap_now and k == 1 else None)
            b.phase(max(0.6, (hi - lo) * 0.045), notes[min(k, len(notes) - 1)], fn)
            lo = hi
        if not euk:
            def terminate(start: Pose, u: float) -> Pose:
                p = start.copy()
                self.dna_rows(p, None, 0.0)
                px, py = start.at("pol")
                p.els["pol"] = (px + 6 * u, py + 3 * u, 1.0 - window(u, 0.0, 0.6))
                target = self._flat_targets(range(len(self.rna)), Y_RNA + BACTERIAL_LIFT)
                p.cam = mix(start.cam, (start.cam[0] - 8.0, Y_RNA + BACTERIAL_LIFT), ease(u))
                p.lines["rna"] = (start.lines["rna"][0], BACKBONE - 2 * BACKBONE * ease(u), "rna", 1.0)
                for key, (x, y) in target.items():
                    sx, sy, so = start.els[key]
                    p.els[key] = (*mix((sx, sy), (x, y), ease(u)), so)
                for i in range(len(self.rna)):
                    p.rungs[f"h{i}"] = (f"m{i}", f"t{self.p0 + i}", 0.0)
                return p
            b.phase(0.8, "The RNA and the polymerase are released; the next round starts with σ<sup>70</sup> again", terminate)
            self.rna_y = Y_RNA + BACTERIAL_LIFT

    def _flat_targets(self, indices: Iterable[int], y: float) -> dict[str, Point]:
        return {f"m{i}": (self.flat_x(i), y) for i in indices}

    # ----- capping --------------------------------------------------------------------------------

    def _cap(self, b: Builder, options: dict[str, object]) -> None:
        def steps(k: int) -> Callable[[Pose, float], Pose]:
            def fn(start: Pose, u: float) -> Pose:
                p = start.copy()
                fx, fy = p.at("m0")
                p.els["capping"] = (fx + 1.2, fy + 2.0, min(1.0, (window(u, 0.0, 0.3) if k == 0 else 1.0)) * (1.0 - (window(u, 0.7, 1.0) if k == 2 else 0.0)))
                if k >= 1:
                    p.els["cap"] = (fx - 1.35, fy, window(u, 0.2, 0.8) if k == 1 else 1.0)
                p.cam = mix(start.cam, (fx + self.window * 0.25, start.cam[1]), ease(u) if k == 0 else 1.0)
                return p
            return fn

        b.phase(1.0, "RNA triphosphatase removes the γ-phosphate from the 5′ end (pppN → ppN)", steps(0))
        b.phase(1.0, "Guanylyltransferase adds GMP from GTP: G joined to the RNA by a 5′–5′ triphosphate (GpppN)", steps(1))
        b.phase(1.0, "Guanine-N7 methyltransferase methylates the G with S-adenosylmethionine: the m<sup>7</sup>GpppN cap protects the "
                     "5′ end and later recruits the ribosome", steps(2))

    # ----- splicing ---------------------------------------------------------------------------------------

    def _splice(self, b: Builder, options: dict[str, object]) -> None:
        g = self.gene
        introns = list(g.introns)
        y = self.rna_y
        base = b.pose
        # where each exon ends up: the last exon stays (the 3′ end may still be in the polymerase),
        # the ones before it close up to it
        shift: dict[int, float] = {}
        exons = g.exons()
        for k, (a, e) in enumerate(exons):
            later = sum(intron.length for intron in introns[k:])
            for i in range(a, e):
                shift[i] = later
        # the camera on the first intron (its lariat forms left of its branch point)
        mid = base.at(f"m{introns[0].branch}")[0] - (2.0 if self.window < 30 else 0.0)
        after = tuple(f"a{k}" for k in range(TAIL_DRAWN)) if self.state.tailed else tuple(f"m{i}" for i in range(g.cleavage, len(self.rna)))
        junctions = g.junctions()

        def lariat(k: int, i: int, t: float) -> Point:
            """Where intron ``k``'s base ``i`` is ``t`` (0–1) into forming its lariat: the stretch
            from the 5′ G to the branch-point A bends into a closing loop above the RNA (the G ends
            beside the A, joined 2′–5′), lifted a little; the tail to the 3′ AG slopes back down."""
            intron = introns[k]
            n = intron.branch - intron.start + 1
            bx, _ = base.at(f"m{intron.branch}")
            lift = LARIAT_LIFT * t
            if i > intron.branch:
                x3, _ = base.at(f"m{intron.end - 1}")
                f = (i - intron.branch) / max(1, intron.end - 1 - intron.branch)
                return (base.at(f"m{i}")[0], y + lift * (1.0 - f))
            j = intron.branch - i
            # it rolls up from the branch point: the first t·n bases on the final circle, the rest
            # straight on along its tangent
            r = n / (2 * math.pi)
            rolled = t * (n - 1)

            def on_circle(s: float) -> Point:
                phi = s / r
                return (bx - r * math.sin(phi), y + lift + r - r * math.cos(phi))

            if j <= rolled:
                return on_circle(j)
            ex, ey = on_circle(rolled)
            phi = rolled / r
            return (ex - math.cos(phi) * (j - rolled), ey + math.sin(phi) * (j - rolled))

        def assemble(start: Pose, u: float) -> Pose:
            p = start.copy()
            for k, intron in enumerate(introns):
                x5 = p.at(f"m{intron.start}")[0]
                xb = p.at(f"m{intron.branch}")[0]
                x3 = p.at(f"m{intron.end - 1}")[0]
                p.els[f"u1_{k}"] = (x5 + 0.6, y + 1.9, window(u, 0.0, 0.3))
                p.els[f"u2af_{k}"] = (x3 - 3.0, y + 1.8, window(u, 0.2, 0.5))
                p.els[f"u2_{k}"] = (xb, y + 1.9, window(u, 0.4, 0.7))
                p.els[f"ss5_{k}"] = (x5 + 0.5, y - 0.95, window(u, 0.0, 0.3))
                p.els[f"branch_{k}"] = (xb, y - 0.95, window(u, 0.4, 0.7))
                p.els[f"ss3_{k}"] = (x3 - 0.5, y - 0.95, window(u, 0.2, 0.5))
            p.cam = mix(start.cam, (mid, y + 2.6), ease(u))
            return p

        def tri(start: Pose, u: float) -> Pose:
            p = start.copy()
            for k, intron in enumerate(introns):
                xb = p.at(f"m{intron.branch}")[0]
                x5 = p.at(f"m{intron.start}")[0]
                r = (intron.branch - intron.start + 1) / (2 * math.pi)
                p.els[f"tri_{k}"] = ((x5 + xb) / 2, y + 5.0 - 1.6 * window(u, 0.0, 0.4), window(u, 0.0, 0.3) * (1.0 - window(u, 0.55, 0.85)))
                p.els[f"sp_{k}"] = (xb - 0.3, y + LARIAT_LIFT + r, window(u, 0.4, 0.8))
                p.fade(f"u1_{k}", 1.0 - window(u, 0.5, 0.8))
            return p

        def first(start: Pose, u: float) -> Pose:
            p = start.copy()
            t = ease(u)
            for k, intron in enumerate(introns):
                for i in range(intron.start, intron.end):
                    key = f"m{i}"
                    p.els[key] = (*lariat(k, i, t), 1.0)
                xb, yb = p.at(f"m{intron.branch}")
                p.els[f"branch_{k}"] = (xb + 0.85, yb - 0.75, 1.0)
                for name, idx in ((f"ss5_{k}", intron.start), (f"ss3_{k}", intron.end - 1)):
                    x, yy = p.at(f"m{idx}")
                    p.els[name] = (x, yy - 0.95, 1.0 - window(u, 0.4, 0.8))
                ux, uy = start.at(f"u2_{k}")
                p.els[f"u2_{k}"] = (ux, uy, 1.0 - window(u, 0.0, 0.5))
                p.fade(f"u2af_{k}", 1.0 - window(u, 0.0, 0.5))
            self.splice_lines(p, 1 if u > 0.5 else 0, after)
            return p

        def second(start: Pose, u: float) -> Pose:
            p = start.copy()
            t = ease(u)
            for i, s in shift.items():
                key = f"m{i}"
                sx, sy = start.at(key)
                p.els[key] = (sx + s * t, sy, 1.0)
            for k, intron in enumerate(introns):
                for i in range(intron.start, intron.end):
                    key = f"m{i}"
                    sx, sy = start.at(key)
                    p.els[key] = (sx + shift.get(intron.end, 0.0) * t, sy + 2.0 * t, 1.0)
                p.fade(f"branch_{k}", 1.0 - t)
                spx, spy = start.at(f"sp_{k}")
                p.els[f"sp_{k}"] = (spx + shift.get(intron.end, 0.0) * t, spy + 2.0 * t, 1.0)
                for name in (f"u2_{k}", f"u2af_{k}"):
                    p.fade(name, 1.0 - t)
            if p.opacity("cap") > 0:
                cx, cy = start.at("cap")
                p.els["cap"] = (cx + shift.get(0, 0.0) * t, cy, p.opacity("cap"))
            self.splice_lines(p, 2 if u > 0.5 else 1, after)
            p.cam = mix(start.cam, (mid + shift.get(0, 0.0) * 0.5, y + 1.2), t)
            return p

        def degrade(start: Pose, u: float) -> Pose:
            p = start.copy()
            for k, intron in enumerate(introns):
                for i in range(intron.start, intron.end):
                    p.fade(f"m{i}", 1.0 - window(u, 0.0, 0.6))
                p.fade(f"sp_{k}", 1.0 - window(u, 0.0, 0.5))
                p.fade(f"intron{k}", p.opacity(f"intron{k}"))
                # the exon junction complex: ~24 nt upstream of the junction
                x, yy = p.at(self.mature_keys[max(0, junctions[k] - 24)])
                p.els[f"ejc_{k}"] = (x, yy + 1.6, window(u, 0.3, 0.8))
            # the camera on the first junction and its EJC
            jx = p.at(self.mature_keys[junctions[0]])[0]
            p.cam = mix(start.cam, (jx - 8.0 if self.window >= 30 else jx - 4.0, y + 1.6), ease(u))
            self.splice_lines(p, 3, after)
            return p

        b.phase(1.2, "U1 snRNP pairs with the 5′ splice site (GU); U2AF binds the polypyrimidine tract and the 3′ AG; U2 snRNP pairs "
                     "round the branch point, its A bulged out", assemble)
        b.phase(1.0, "The U4/U6·U5 tri-snRNP joins; U1 and U4 leave: the catalytic spliceosome (U2, U5, U6)", tri)
        b.phase(1.4, "First transesterification: the branch-point A's 2′-OH attacks the 5′ splice site — the intron's 5′ G joins the A "
                     "by a 2′–5′ bond: a lariat", first)
        b.phase(1.4, "Second transesterification: the 3′-OH of the freed exon attacks the 3′ splice site — the exons are joined and "
                     "the lariat leaves", second)
        b.phase(1.0, "The lariat is debranched and degraded; an exon junction complex (EJC) stays ~24 nt upstream of each junction", degrade)

    def splice_lines(self, p: Pose, stage: int, after: tuple[str, ...]) -> None:
        """The RNA's backbones while splicing: one chain (0), the lariats parted from the exon
        before them (1), the exons joined (2, 3: the lariats fading); ``after``: the keys after
        the last exon (the tail, or the RNA still in the polymerase)."""
        g = self.gene
        exons = g.exons()
        dy, alpha = p.lines["rna"][1], p.lines["rna"][3]
        for name in self.line_names:
            if name.startswith(("loop", "tail")) or (name.startswith("rna") and name[3:].isdigit()):
                p.lines[name] = ((), dy, "rna", 0.0)
        if stage == 0:
            return
        if stage == 1:
            # exon 1 alone; each lariat's loop; its tail goes on into the exon after it
            pieces: list[tuple[str, ...]] = [tuple(f"m{i}" for i in range(exons[0][0], exons[0][1]))]
            for k, intron in enumerate(g.introns):
                p.lines[f"loop{k}"] = (tuple(f"m{i}" for i in range(intron.start, intron.branch + 1)) + (f"m{intron.start}",), 0.0, "rna", 1.0)
                piece = tuple(f"m{i}" for i in range(intron.branch, exons[k + 1][1]))
                pieces.append(piece + (after if k == len(g.introns) - 1 else ()))
            p.lines["rna"] = (pieces[0], dy, "rna", alpha)
            for k, piece in enumerate(pieces[1:]):
                p.lines[f"rna{k}"] = (piece, dy, "rna", alpha)
            return
        p.lines["rna"] = (tuple(self.mature_keys) + after, dy, "rna", alpha)
        p.chain = tuple(self.mature_keys) + after
        for k, intron in enumerate(g.introns):
            o = 1.0 if stage == 2 else p.opacity(f"m{intron.start}")
            p.lines[f"loop{k}"] = (tuple(f"m{i}" for i in range(intron.start, intron.branch + 1)) + (f"m{intron.start}",), 0.0, "rna", o)
            p.lines[f"tail{k}"] = (tuple(f"m{i}" for i in range(intron.branch, intron.end)), 0.0, "rna", o)

    # ----- the 3′ end ---------------------------------------------------------------------------------

    def _polyadenylate(self, b: Builder, options: dict[str, object]) -> None:
        g = self.gene
        sig = g.polya_signal or 0
        y = self.rna_y
        cut = g.cleavage
        body = tuple(k for k in self.chain_order(self.state) if k.startswith("m") and int(k[1:]) < cut)
        downstream = tuple(f"m{i}" for i in range(cut, len(self.rna)))
        tail_keys = tuple(f"a{k}" for k in range(TAIL_DRAWN))
        dy = b.pose.lines["rna"][1]

        def bind(start: Pose, u: float) -> Pose:
            p = start.copy()
            x, yy = p.at(f"m{sig}")
            p.els["box_polya"] = (x + 2.5, yy + 1.15, window(u, 0.0, 0.3))
            p.els["cpsf"] = (x + 2.5, yy + 3.1 - 0.6 * window(u, 0.0, 0.4), window(u, 0.0, 0.3))
            xd, yd = p.at(f"m{min(len(self.rna) - 1, cut + 4)}")
            p.els["cstf"] = (xd + 0.5, yd + 2.4 - 0.4 * window(u, 0.3, 0.7), window(u, 0.3, 0.6))
            p.cam = mix(start.cam, (x + 6.0, y + 0.5), ease(u))
            return p

        def cleave(start: Pose, u: float) -> Pose:
            p = start.copy()
            t = ease(u)
            for key in downstream:
                sx, sy, so = start.els[key]
                p.els[key] = (sx + 1.2 * t, sy, so)
            p.lines["rna"] = (body, dy, "rna", 1.0)
            p.lines["downstream_rna"] = (downstream, dy, "rna", 1.0)
            p.chain = body
            return p

        def torpedo(start: Pose, u: float) -> Pose:
            p = start.copy()
            t = ease(u)
            n = max(1, len(downstream))
            for k, key in enumerate(downstream):
                p.fade(key, (1.0 - window(u, k / n * 0.6, k / n * 0.6 + 0.2)) * start.opacity(key))
            xs = start.at(downstream[0])
            p.els["xrn2"] = (xs[0] + n * t, xs[1] + 1.6, window(u, 0.0, 0.15) * (1.0 - window(u, 0.85, 1.0)))
            px, py = start.at("pol")
            p.els["pol"] = (px + 5 * window(u, 0.5, 1.0), py - 3 * window(u, 0.5, 1.0), 1.0 - window(u, 0.55, 1.0))
            p.fade("cstf", 1.0 - window(u, 0.4, 0.8))
            p.fade("ctd", start.opacity("ctd") * (1.0 - window(u, 0.4, 0.8)))
            p.fade("box_polya", 1.0 - window(u, 0.6, 1.0))
            self.dna_rows(p, None, 0.0, p.opacity("c0"))
            # the pre-mRNA comes off the polymerase: bases still on the way out go to the RNA's row
            for key in body:
                sx, sy, so = start.els[key]
                if abs(sy - y) > 1e-6 and so > 0:
                    p.els[key] = (*mix((sx, sy), (self.flat_x(int(key[1:])), y), t), so)
            for i in range(len(self.rna)):
                p.rungs[f"h{i}"] = (f"m{i}", f"t{self.p0 + i}", 0.0)
            p.lines["downstream_rna"] = (downstream, dy, "rna", 1.0 - window(u, 0.5, 0.9))
            return p

        def tail(start: Pose, u: float) -> Pose:
            p = start.copy()
            lx, ly = start.at(body[-1])
            n = TAIL_DRAWN * u
            for k in range(TAIL_DRAWN):
                p.els[f"a{k}"] = (lx + 1.0 * (k + 1), ly, min(1.0, max(0.0, (n - k) * 1.5)))
            p.els["pap"] = (lx + 1.0 * (n + 1) + 0.5, ly + 2.0, window(u, 0.0, 0.1) * (1.0 - window(u, 0.9, 1.0)))
            p.els["polya_n"] = (lx + TAIL_DRAWN / 2 + 1.0, ly - 1.3, window(u, 0.8, 1.0))
            for k in range(3):
                p.els[f"pabpn1_{k}"] = (lx + 2.2 + k * 3.6, ly + 1.75, window(u, 0.35 + 0.2 * k, 0.5 + 0.2 * k))
            p.fade("cpsf", 1.0 - window(u, 0.0, 0.3))
            p.lines["rna"] = (body + tail_keys, dy, "rna", 1.0)
            p.lines["downstream_rna"] = ((), dy, "rna", 0.0)
            p.chain = body + tail_keys
            p.cam = mix(start.cam, (lx + 2.0, y + 0.5), ease(u))
            return p

        b.phase(1.0, "CPSF binds the poly(A) signal AAUAAA, CstF the GU-rich element downstream", bind)
        b.phase(0.8, "CPSF73 cleaves the RNA 10–30 nt after AAUAAA (after a CA)", cleave)
        b.phase(1.0, "The exonuclease Xrn2 degrades the RNA still in the polymerase, which then lets go of the DNA (termination, torpedo "
                     "model)", torpedo)
        b.phase(1.4, f"Poly(A) polymerase adds a tail of ~{TAIL_REAL} A without a template; PABPN1 coats it", tail)

    def fade_dna(self, p: Pose, s: Pose, f: float) -> None:
        """The DNA and what is on it faded to ``f`` of its opacity in ``s``."""
        for key in self.dna_keys:
            if key in s.els:
                p.fade(key, s.opacity(key) * f)
        for j in range(len(self.dna)):
            a, b, o = s.rungs.get(f"bp{j}", (f"c{j}", f"t{j}", 0.0))
            p.rungs[f"bp{j}"] = (a, b, o * f)
        for name in ("coding", "template"):
            keys_, dy, hue, o = s.lines[name]
            p.lines[name] = (keys_, dy, hue, o * f)

    # ----- export --------------------------------------------------------------------------------

    def _export(self, b: Builder, options: dict[str, object]) -> None:
        chain = self.chain_order(self.state)
        keys = ["cap"] + chain
        start = b.pose
        xs = {k: start.at(k)[0] for k in keys}
        x_pore = xs["cap"] - 5.0
        y0, y1 = self.rna_y, Y_CYTOSOL
        # the mRNA's way, its 5′ end first: left along its row, up through the pore, left along
        # the cytosol's row
        far = max(xs.values()) + 5.0
        path = [(far, y0), (x_pore, y0), (x_pore, Y_ENVELOPE - 3.0), (x_pore, Y_ENVELOPE + 3.0), (x_pore, y1), (x_pore - 400.0, y1)]
        s0 = {k: far - xs[k] for k in keys}
        travel = path_length(path[:5]) - s0[keys[-1]] + 2.5
        riders = self._riders(start, keys)
        dy0 = start.lines["rna"][1]
        self.pore_x = x_pore

        def load(s: Pose, u: float) -> Pose:
            p = s.copy()
            self.envelope(p, x_pore, window(u, 0.0, 0.5))
            p.els["cbc"] = (xs["cap"] - 0.2, y0 + 1.7, window(u, 0.0, 0.3))
            for key, (anchor, dx, dy) in riders.items():
                if key.startswith("nxf1"):
                    ax, ay = s.at(anchor)
                    k = int(key[-1])
                    p.els[key] = (ax + dx, ay + dy, window(u, 0.4 + 0.2 * k, 0.7 + 0.2 * k))
            self.fade_dna(p, s, 1.0 - window(u, 0.0, 0.8))
            p.cam = mix(s.cam, (x_pore + self.window * 0.25, (y0 + Y_ENVELOPE) / 2 + 0.5), ease(u))
            return p

        def move(s: Pose, u: float) -> Pose:
            p = s.copy()
            d = travel * ease(u)
            for key in keys:
                x, y = along(path, s0[key] + d)
                p.els[key] = (x, y, s.opacity(key))
            for key, (anchor, dx, dy) in riders.items():
                ax, ay = p.at(anchor)
                side = 1.0 if ay < Y_ENVELOPE - 2.5 else -1.0 if ay > Y_ENVELOPE + 2.5 else 0.0
                if side == 0.0:
                    p.els[key] = (ax + 1.0, ay, s.opacity(key))
                else:
                    p.els[key] = (ax + dx, ay + dy * side, s.opacity(key))
            head_x, head_y = p.at("cap")
            p.cam = (max(x_pore - self.window / 2 + 3.0, min(s.cam[0], head_x + self.window * 0.3)),
                     s.cam[1] + (Y_ENVELOPE + 0.3 - s.cam[1]) * min(1.0, ease(u * 3)))
            p.lines["rna"] = (tuple(chain), dy0 - 2.0 * dy0 * window(u, 0.55, 0.95), "rna", 1.0)
            p.chain = tuple(chain)
            return p

        def remodel(s: Pose, u: float) -> Pose:
            p = s.copy()
            hx, hy = s.at("cap")
            p.els["dbp5"] = (x_pore - 2.6, Y_ENVELOPE + 3.6, window(u, 0.0, 0.3) * (1.0 - window(u, 0.8, 1.0)))
            for k in range(2):
                p.fade(f"nxf1_{k}", s.opacity(f"nxf1_{k}") * (1.0 - window(u, 0.2, 0.6)))
            p.fade("cbc", 1.0 - window(u, 0.3, 0.6))
            p.els["eif4e"] = (hx, hy - 1.7, window(u, 0.4, 0.7))
            for k in range(3):
                key = f"pabpn1_{k}"
                if s.opacity(key) > 0:
                    x, y = s.at(key)
                    p.fade(key, s.opacity(key) * (1.0 - window(u, 0.3, 0.6)))
                    p.els[f"pabpc1_{k}"] = (x, y, window(u, 0.5, 0.8))
            for k in range(len(self.gene.introns)):
                p.fade(f"ejc_{k}", s.opacity(f"ejc_{k}"))
            p.cam = mix(s.cam, (hx + self.window * 0.4, y1 + 1.5), ease(u))
            return p

        b.phase(1.0, "The mRNP: the cap-binding complex (CBC) on the cap, EJCs at the junctions, PABPN1 on the tail; TREX loads the "
                     "export receptor NXF1–NXT1", load)
        b.phase(2.2, "NXF1–NXT1 carries the mRNP through a nuclear pore complex, 5′ end first, binding the FG repeats lining its channel",
                move)
        b.phase(1.0, "On the cytoplasmic side the helicase Dbp5 remodels the mRNP and releases NXF1; eIF4E takes the cap from CBC, "
                     "PABPC1 the tail from PABPN1", remodel)
        self.rna_y = Y_CYTOSOL

    def envelope(self, p: Pose, x_pore: float, o: float) -> None:
        """The nuclear envelope (two membranes, the perinuclear space between) with a pore at
        ``x_pore``, and the names of the compartments."""
        p.els["envelope"] = (x_pore, Y_ENVELOPE + 1.3, o)
        p.els["envelope_in"] = (x_pore, Y_ENVELOPE - 1.3, o)
        p.els["npc"] = (x_pore, Y_ENVELOPE, o)
        p.els["lab_nucleoplasm"] = (x_pore + 9.0, Y_ENVELOPE - 3.1, o)
        p.els["lab_cytosol"] = (x_pore + 9.0, Y_ENVELOPE + 3.1, o)
        p.els["lab_envelope"] = (x_pore + 9.0, Y_ENVELOPE + 0.0, o * 0.9)

    def _riders(self, p: Pose, keys: list[str]) -> dict[str, tuple[str, float, float]]:
        """Proteins riding on the mRNA during export: each with the key it is on and its offset
        (above the RNA in the nucleus; mirrored below it in the cytosol)."""
        out: dict[str, tuple[str, float, float]] = {"cbc": ("cap", -0.2, 1.7)}
        for k in range(len(self.gene.introns)):
            key = f"ejc_{k}"
            if p.opacity(key) > 0:
                nearest = min(keys, key=lambda m: abs(p.at(m)[0] - p.at(key)[0]) + abs(p.at(m)[1] - p.at(key)[1]))
                out[key] = (nearest, p.at(key)[0] - p.at(nearest)[0], p.at(key)[1] - p.at(nearest)[1])
        body = [k for k in keys if k.startswith("m")]
        for k in range(2):
            out[f"nxf1_{k}"] = (body[min(len(body) - 1, 10 + k * max(8, len(body) // 2))], 0.0, 1.8)
        for k in range(3):
            key = f"pabpn1_{k}"
            if p.opacity(key) > 0:
                anchor = f"a{min(TAIL_DRAWN - 1, 1 + k * 4)}"
                out[key] = (anchor, p.at(key)[0] - p.at(anchor)[0], p.at(key)[1] - p.at(anchor)[1])
        return out


#: How far a lariat rises above the RNA as it forms (slots).
LARIAT_LIFT = 1.4
#: The strands' 5′ / 3′ labels this far in from the view's edges (slots), where the tiles fade.
EDGE_LABEL = 0.55
#: How far a bacterial mRNA rises off its gene once released, so a ribosome fits under it (slots).
BACTERIAL_LIFT = 5.0


__all__ = ["Builder", "Clip", "ExpressionStage", "HUES", "Look", "Pose", "RESIDUE_HUES", "SNFG", "Y_CYTOSOL", "Y_ENVELOPE", "Y_RNA", "along",
           "ease", "mix", "path_length", "window"]
