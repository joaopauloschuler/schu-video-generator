"""The gene-expression close-up in the cytoplasm (DESIGN.md §95.11), without manim: translation
(initiation by scanning from the cap to the AUG — in bacteria at the Shine–Dalgarno sequence —,
the 80S ribosome with its E, P and A sites, elongation cycle by cycle: the aminoacyl-tRNA whose
anticodon pairs with the codon, the peptide bond made at the peptidyl transferase centre so the
chain grows N→C, translocation by one codon; the stop codon read by a release factor), the chain
in the ribosome's exit tunnel (~30 residues, drawn compressed), targeting to the ER (SRP, its
receptor, the Sec61 translocon, the signal peptide in the lateral gate as a loop, signal
peptidase), N-glycosylation by the oligosaccharyltransferase, folding with chaperones.

Positions are slots (see :mod:`vidgen.cellworld.expression_stage`). The ribosome is drawn in its
own frame round the P site's codon: on a free mRNA the ribosome moves along the mRNA; once docked
on the ER it stays on the translocon and the mRNA slides through it (the same relative motion)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from dataclasses import replace

from .expression import TAIL_DRAWN, TUNNEL, anticodon_of, er_entry, glyco_reach, side_chain
from .expression_stage import HUES, RESIDUE_HUES, SNFG, Builder, ExpressionStage, Look, Point, Pose, Y_CYTOSOL, along, ease, mix, window
from .sequences import AMINO_ACIDS, CODONS

#: The ribosome round its P site (slots, from the P codon's middle base on the mRNA's row).
SITE = 3.0                                       # one codon
SMALL_AT, SMALL_W, SMALL_H = (1.5, -1.8), 14.0, 2.6
LARGE_AT, LARGE_W, LARGE_H = (1.5, 3.75), 14.6, 6.3
TRNA_AT, TRNA_W, TRNA_H = 2.5, 2.9, 3.9           # a tRNA's middle above its codon
AA_Y = 4.85                                      # the amino acid on a tRNA's 3′ end
PTC = (1.5, 5.8)                                 # where the tunnel starts, above the tRNAs' 3′ ends
TUNNEL_PATH = [(1.5, 5.8), (2.7, 6.25), (3.7, 6.55), (4.5, 6.95)]
EXIT = TUNNEL_PATH[-1]
#: Beads (slots) and the serpentine the chain takes outside the ribosome: rows apart.
PITCH, ROW_GAP = 1.0, 1.15
#: The ER membrane above a docked ribosome (its middle, from the mRNA's row) and its thickness.
ER_Y, ER_THICK = 8.3, 2.4
#: Codons elongated in detail (captioned cycles) before the rest run fast, and the most time
#: (weights ≈ seconds) the fast ones take together.
DETAIL, FAST_TOTAL = 2, 7.0


def cam_y(stage: ExpressionStage, y: float, docked: bool = False) -> float:
    """The camera's height for a ribosome on the mRNA row ``y``: the mRNA low in the view, the
    chain (or the ER membrane and lumen when docked) above it."""
    return y + max(6.0 if docked else 3.0, (0.25 if docked else 0.18) * stage.height)


def code(stage: ExpressionStage, aa: str) -> str:
    return AMINO_ACIDS[aa] if stage.codes == "three" else aa


def display_anticodon(codon: str) -> str:
    """The anticodon (5′→3′) of the tRNA that reads ``codon`` in human cells: its Watson–Crick
    partner, except that the eight four-codon boxes whose tRNA has inosine at the wobble place
    (Ala, Arg CGN, Ile, Leu CUN, Pro, Ser UCN, Thr, Val) read NNU with I."""
    inosine = {"GC", "CG", "AU", "CU", "CC", "UC", "AC", "GU"}
    if codon[2] == "U" and codon[:2] in inosine and CODONS[codon] != "*":
        return "I" + anticodon_of(codon)[1:]
    return anticodon_of(codon)


def make_cyto_looks(stage: ExpressionStage) -> None:
    """The looks of the cytoplasm's steps."""
    g = stage.gene
    euk = stage.euk
    add = stage._add
    n = len(g.codons) - 1
    stage.blob("eif4e", "eIF4E", "eif4e", 2.2, 1.5, z=3.6)
    for k in range(3):
        stage.blob(f"pabpc1_{k}", "PABPC1", "pabpc1", 2.8, 1.3, z=3.6)
    stage.blob("eif4f", "eIF4G·4A" if euk else "", "eif4f", 3.6, 1.6, z=3.6)
    stage.blob("eif2", "eIF2·GTP" if euk else "IF2·GTP", "eef1a", 3.4, 1.5, z=4.2)
    stage.blob("eif3", "eIF3" if euk else "IF3", "eif4f", 2.6, 1.6, z=4.2)
    stage._add(Look("small", "blob", "40S" if euk else "30S", HUES["small"], SMALL_W, SMALL_H, "round", 0.6, (("label_at", -5.6, -0.6),)))
    stage._add(Look("large", "blob", "60S" if euk else "50S", HUES["large"], LARGE_W, LARGE_H, "round", 0.6, (("label_at", -5.7, 2.4),)))
    for site in "EPA":
        stage.label(f"site{site}", site, 0.6, "dim", z=2.5)
    stage.label("ptc", "peptidyl transferase centre", 0.5, "dim", z=6.5)
    stage.label("tunnel", "exit tunnel (~30 residues)", 0.5, "dim", z=6.5)
    for site, hue in (("A", "#E07A5F"), ("P", "#4F8FD9"), ("E", "#9A9A9A")):
        add(Look(f"hl{site}", "box", "", hue, 2.95, 1.05, z=3.8))
    add(Look("start_mark", "box", "start codon", "#4FA35E", 2.95, 1.05, z=3.7))
    add(Look("stop_mark", "box", "stop codon", "#D9534F", 2.95, 1.05, z=3.7))
    if not euk and g.sd is not None:
        add(Look("sd_mark", "box", "Shine–Dalgarno", "#5E9FD6", 5.95, 1.05, z=3.7))
    for k, codon in enumerate(g.codons[:-1]):
        aa = CODONS[codon]
        anti = display_anticodon(codon)
        text = "".join(reversed(anti))                    # left to right under the codon: 3′→5′
        add(Look(f"tr{k}", "trna", text, HUES["trna"], TRNA_W, TRNA_H, z=3.0))
        hue = RESIDUE_HUES[side_chain(aa)]
        label = code(stage, aa) if not (k == 0 and not euk) else ("fMet" if stage.codes == "three" else "fM")
        add(Look(f"aa{k}", "bead", label, hue, 0.98, 0.98, z=5.0))
        add(Look(f"dt{k}", "dot", "", hue, 0.24, 0.24, z=4.9))
        add(Look(f"pep{k}", "label", label, hue, h=0.62, z=7.0))
    stage.label("pepN", "N–" if stage.codes == "three" else "N–", 0.62, "", z=7.0)
    stage.label("pepC", "–C", 0.62, "", z=7.0)
    stage.label("pepmore", "…", 0.62, "", z=7.0)
    stage.label("nterm", "N", 0.55, "", z=6.5)
    stage.label("cterm", "C", 0.55, "", z=6.5)
    stage.blob("eef1a", "eEF1A·GTP" if euk else "EF-Tu·GTP", "eef1a", 3.6, 1.5, z=4.3)
    stage.blob("eef2", "eEF2·GTP" if euk else "EF-G·GTP", "eef2", 3.4, 1.6, z=4.3)
    add(Look("erf", "blob", "eRF1·eRF3" if euk else "RF1", HUES["erf1"], TRNA_W, TRNA_H * 0.9, "round", 3.0))
    stage.blob("abce1", "ABCE1" if euk else "RRF·EF-G", "abce1", 3.0, 1.5, z=4.3)
    # the ER
    add(Look("er", "membrane", "", HUES["membrane"], 400.0, ER_THICK, z=0.2, data=(("gap", 0.0, 3.0), ("gap", 4.4, 2.8))))
    # its name beside it in the membrane (the chain threads through the middle)
    add(Look("sec61", "blob", "Sec61", HUES["sec61"], 3.0, ER_THICK + 0.8, "channel", 0.8, (("label_at", -3.1, 0.0),)))
    stage.blob("srp", "SRP", "srp", 8.0, 2.0, "rod", z=4.4)
    stage.blob("sr", "SRP receptor", "sr", 4.6, 1.8, z=0.9)
    stage.blob("ost", "OST", "ost", 2.8, ER_THICK + 1.4, "round", z=0.9)
    stage.blob("spc", "signal peptidase", "spc", 4.6, 1.6, z=4.5)
    for name, text in (("lab_er_lumen", "ER lumen"), ("lab_er_cytosol", "cytosol"), ("lab_er", "ER membrane")):
        stage.label(name, text, 0.6, "dim")
    for k, _ in enumerate(g.sequons):
        for glc, name in ((3, f"gly{k}"), (1, f"gly1_{k}"), (0, f"gly0_{k}")):
            add(Look(name, "glycan", "", SNFG["Man"], 3.2, 4.4, z=5.5, data=(("glc", glc),)))
    stage.label("dol", "dolichol-PP", 0.5, "dim")
    # folding
    for k in range(3):
        stage.blob(f"hsp70_{k}", "Hsp70" if euk else "DnaK", "hsp70", 3.0, 1.8, z=5.6)
        stage.blob(f"bip_{k}", "BiP", "bip", 2.6, 1.7, z=5.6)
    stage._add(Look("cct", "blob", "TRiC (CCT)" if euk else "GroEL", HUES["chaperonin"], 11.0, 10.0, "barrel", 4.0, (("label_at", 0.0, -5.8),)))
    stage.blob("calnexin", "calnexin", "calnexin", 3.4, 2.0, z=5.6)
    # calnexin is a type I membrane protein: its lectin domain in the lumen, on a stalk (the P
    # domain) from its transmembrane helix in the ER membrane
    stage.blob("calnexin_tm", "", "calnexin", 1.0, ER_THICK + 0.6, "channel", z=0.8)
    stage.line_names.append("cnx_arm")
    stage.blob("glucosidase", "glucosidase II", "glucosidase", 4.6, 1.6, z=5.7)
    stage.blob("pdi", "PDI", "pdi", 2.2, 1.5, z=5.7)
    for k in range(4):
        add(Look(f"ss{k}", "label", "S–S", "#C9A030", h=0.5, z=6.0))
    stage.line_names += ["chain"]
    for k, codon in enumerate(g.codons[:-1]):
        for j in range(3):
            stage.rung_names.append(f"ac{k}_{j}")


# ----- where things are ------------------------------------------------------------------------------


def mature_key(stage: ExpressionStage, index: int) -> str:
    """The key of the mature mRNA's base ``index`` (past its end: a tail A)."""
    if index < len(stage.mature_keys):
        return stage.mature_keys[index]
    return f"a{min(TAIL_DRAWN - 1, index - len(stage.mature_keys))}"


def codon_x(stage: ExpressionStage, p: Pose, k: int) -> float:
    """The x of codon ``k``'s middle base as the pose has the mRNA."""
    at, _ = stage.gene.codon_at(k)
    return p.at(mature_key(stage, at + 1))[0]


def cytosol_mrna(stage: ExpressionStage, p: Pose) -> None:
    """A mature mRNA lying in the cytosol (the scene starts with it): cap, mature bases, tail."""
    keys = stage.chain_order(stage.state)
    x = -float(stage.gene.orf_start) - 2.0
    euk = stage.euk
    if euk:
        p.els["cap"] = (x - 1.35, Y_CYTOSOL, 1.0)
        p.els["eif4e"] = (x - 1.35, Y_CYTOSOL - 1.7, 1.0)
    for k, key in enumerate(keys):
        p.els[key] = (x + k, Y_CYTOSOL, 1.0)
    if euk:
        tail0 = len(stage.mature_keys)
        for k in range(3):
            ax = x + tail0 + 1 + k * 4
            p.els[f"pabpc1_{k}"] = (ax + 0.2, Y_CYTOSOL - 1.75, 1.0)
    p.lines["rna"] = (tuple(keys), -0.52, "rna", 1.0)
    p.chain = tuple(keys)
    p.cam = (x + stage.window * 0.4, Y_CYTOSOL + 1.5)
    stage.rna_y = Y_CYTOSOL


@dataclass
class Ribosome:
    """The translating ribosome at a moment: the P site's codon (``k``, fractional while it
    translocates), its place (the P codon's middle base, slots), how many residues are made, which
    tRNAs are where."""

    xp: float
    y: float
    on: float = 1.0                       # the subunits shown
    large: float = 1.0                    # the large subunit joined
    trnas: dict[int, tuple[Point, float]] = field(default_factory=dict)   # codon -> (place, opacity)
    pairs: dict[int, float] = field(default_factory=dict)                  # codon -> codon–anticodon pairing shown


class Chain:
    """Where each residue of the growing chain is: the newest (C-terminal) on its tRNA, the ones
    before it through the peptidyl transferase centre and the exit tunnel (compressed), then out
    of the ribosome along a serpentine (cytosol), or through the translocon into the ER lumen —
    as a loop while the signal peptide sits in the membrane, free once it is cut."""

    def __init__(self, stage: ExpressionStage) -> None:
        self.stage = stage

    def path_out(self, mode: str, ribo: Point, made: int, er_y: float) -> Callable[[float], Point]:
        """The chain's way out beyond the tunnel exit, by distance ``s`` (slots) from the exit:
        ``cytosol``: a serpentine above the ribosome running left; ``er``: through the
        translocon and a serpentine in the lumen."""
        x0, y0 = ribo[0] + EXIT[0], ribo[1] + EXIT[1]
        if mode == "er":
            start = (x0, er_y + ER_THICK / 2 + 0.6)
            lead = [(x0, y0), start, (x0, start[1] + 0.6)]
        else:
            start = (x0, y0 + 1.0)
            lead = [(x0, y0), start]
        lead_len = sum(math.dist(a, b) for a, b in zip(lead, lead[1:]))
        ROW = self.stage.row

        def at(s: float) -> Point:
            if s <= lead_len:
                return along(lead, s)
            s -= lead_len
            row_f, col = divmod(s, ROW * PITCH)
            row = int(row_f)
            bx, by = lead[-1]
            straight = (ROW - 1) * PITCH
            even = row % 2 == 0
            if col > straight:                       # the turn up to the next row
                frac = (col - straight) / PITCH
                return (bx - straight if even else bx, by + (row + frac) * ROW_GAP)
            return (bx - col if even else bx - straight + col, by + row * ROW_GAP)
        return at


def _tunnel_point(ribo: Point, d: float) -> Point:
    """The point ``d`` (0–1) of the way along the exit tunnel."""
    pts =[(ribo[0] + x, ribo[1] + y) for x, y in TUNNEL_PATH]
    total = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    return along(pts, d * total)


def place_chain(stage: ExpressionStage, p: Pose, made: int, anchor: Point, ribo: Point, mode: str = "cytosol", er_y: float = 0.0,
                signal: str = "none", loop_from: Point | None = None) -> None:
    """Put residues ``0 … made-1``: the newest at ``anchor`` (its tRNA's 3′ end), the ones
    before it through the tunnel (dots) and out (beads); ``signal``: ``inserted`` (the signal
    peptide in the membrane, the rest as a loop), ``cut`` or ``none``."""
    g = stage.gene
    n_total = len(g.codons) - 1
    if made <= 0:
        for k in range(n_total):
            p.els[f"aa{k}"] = (anchor[0], anchor[1], 0.0)
            p.els[f"dt{k}"] = (anchor[0], anchor[1], 0.0)
        return
    out = Chain(stage).path_out(mode, ribo, made, er_y)
    positions: dict[int, tuple[Point, bool]] = {}
    for k in range(made):
        positions[k] = chain_point(anchor, ribo, out, float(made - 1 - k))
    sig = g.signal
    if signal == "inserted" and mode == "er":
        outside = [k for k in range(made) if made - 1 - k > TUNNEL]
        x_gate = ribo[0] + EXIT[0] - 2.1                      # Sec61's lateral gate
        top, bottom = er_y + ER_THICK / 2, er_y - ER_THICK / 2
        # the signal peptide: n-region in the cytosol (its N-terminus there), the hydrophobic
        # h-region across the membrane in the lateral gate, the c-region with the cleavage site in the lumen
        n_reg, c_reg = 3, 3
        h = list(range(n_reg, sig - c_reg))
        for k in range(sig):
            if k < n_reg:
                positions[k] = ((x_gate - 0.95 * (n_reg - k), bottom - 0.65), False)
            elif k >= sig - c_reg:
                positions[k] = ((x_gate, top + 0.6 + 0.95 * (k - (sig - c_reg))), False)
            else:
                positions[k] = ((x_gate, bottom + (top - bottom) * (h.index(k) + 0.5) / len(h)), True)
        # the mature part between the c-region and the translocon's lumenal mouth: a loop
        mid = [k for k in outside if k >= sig]
        if mid:
            mouth = (ribo[0] + EXIT[0], top + 0.6)
            gate_top = positions[sig - 1][0]
            length = (len(mid) + 1) * PITCH
            span = mouth[0] - gate_top[0]
            y_top = max(max(gate_top[1], mouth[1]) + 0.6, (length - span + gate_top[1] + mouth[1]) / 2)
            loop = [gate_top, (gate_top[0], y_top), (mouth[0], y_top), mouth]
            total = sum(math.dist(a, b) for a, b in zip(loop, loop[1:]))
            for j, k in enumerate(mid):
                positions[k] = (along(loop, total * (j + 1) / (len(mid) + 1)), False)
    if signal == "cut":
        for k in range(min(sig, made)):
            positions.pop(k, None)
    for k in range(n_total):
        if k in positions:
            (x, y), dot = positions[k]
            p.els[f"aa{k}"] = (x, y, 0.0 if dot else 1.0)
            p.els[f"dt{k}"] = (x, y, 1.0 if dot else 0.0)
        else:
            p.els[f"aa{k}"] = (anchor[0], anchor[1], 0.0)
            p.els[f"dt{k}"] = (anchor[0], anchor[1], 0.0)
    p.lines["chain"] = (tuple(f"aa{k}" if positions[k][1] is False else f"dt{k}" for k in range(made) if k in positions), 0.0, "chain", 1.0)


def place_ribosome(stage: ExpressionStage, p: Pose, r: Ribosome) -> None:
    """The subunits, site letters and highlights round the P site at ``r.xp``, and the tRNAs."""
    x, y = r.xp, r.y
    p.els["small"] = (x + SMALL_AT[0], y + SMALL_AT[1], r.on)
    p.els["large"] = (x + LARGE_AT[0], y + LARGE_AT[1] + 6.0 * (1.0 - r.large), r.on * r.large)
    for dx, site in ((-SITE, "E"), (0.0, "P"), (SITE, "A")):
        p.els[f"site{site}"] = (x + dx, y + LARGE_AT[1] + LARGE_H / 2 - 0.8 + 6.0 * (1.0 - r.large), r.on * r.large)
        p.els[f"hl{site}"] = (x + dx, y, r.on * r.large * (0.0 if site == "E" else 1.0))
    g = stage.gene
    for k in range(len(g.codons) - 1):
        key = f"tr{k}"
        if k in r.trnas:
            (tx, ty), o = r.trnas[k]
            p.els[key] = (tx, ty, o)
        else:
            p.fade(key, 0.0)
        pair = r.pairs.get(k, 0.0)
        at, _ = g.codon_at(k)
        for j in range(3):
            base = mature_key(stage, at + j)
            p.rungs[f"ac{k}_{j}"] = (base, f"tr{k}#{j}", pair)


def peptide_readout(stage: ExpressionStage, p: Pose, made: float, finished: float = 0.0) -> None:
    """Record how much of the protein the readout shows (placed by :func:`place_readout`)."""
    p.readout = (made, finished)


def place_readout(stage: ExpressionStage, p: Pose) -> None:
    """The protein so far written along the bottom of the view: N–, the residues (the last
    ones when they do not fit), –C once it is finished."""
    if p.readout is None:
        return
    made, finished = p.readout
    g = stage.gene
    n_total = len(g.codons) - 1
    cx, cy = p.cam
    y = cy - stage.height / 2 - stage.strip / 2
    step = 1.75 if stage.codes == "three" else 0.9
    room = stage.window * (0.62 if stage.wide else 1.0) - 2.0
    fit = max(3, int(room / step))
    shown = int(math.floor(made + 1e-9))
    first = max(0, shown - fit)
    x = cx - stage.window / 2 + 1.6
    p.els["pepN"] = (x, y, 1.0 if shown > 0 and first == 0 else 0.0)
    p.els["pepmore"] = (x, y, 1.0 if first > 0 else 0.0)
    for k in range(n_total):
        if first <= k < shown:
            p.els[f"pep{k}"] = (x + 1.1 + (k - first) * step, y, min(1.0, (made - k) * 2.0))
        else:
            p.fade(f"pep{k}", 0.0)
    p.els["pepC"] = (x + 1.1 + (shown - first) * step - 0.2, y, finished)


def chain_ends(p: Pose, made: int, first: int = 0) -> None:
    """``N`` beside the first residue (when it is out of the tunnel)."""
    if made > first and p.opacity(f"aa{first}") > 0.5:
        x, y = p.at(f"aa{first}")
        p.els["nterm"] = (x - 0.95, y + 0.55, 1.0)
    else:
        p.fade("nterm", 0.0)


def chain_point(anchor: Point, ribo: Point, out: Callable[[float], Point], sigma: float) -> tuple[Point, bool]:
    """A residue ``sigma`` residues back from the peptidyl tRNA's 3′ end: at the anchor (0), in
    the tunnel (1 … ``TUNNEL``, drawn as a dot), then out of it; ``(place, in the tunnel)``."""
    if sigma <= 1.0:
        return mix(anchor, _tunnel_point(ribo, 0.0), max(0.0, sigma)), False
    if sigma <= TUNNEL:
        return _tunnel_point(ribo, (sigma - 1) / max(1, TUNNEL - 1)), True
    return out((sigma - TUNNEL) * PITCH), False


# ----- translation -----------------------------------------------------------------------------------


class Translation:
    """The ribosome's progress over a ``translate`` (and the elongation inside ``target_er`` and
    ``glycosylate``): the frame (moving ribosome on a free mRNA, or a docked one and a sliding
    mRNA), the chain, the readout."""

    def __init__(self, stage: ExpressionStage, start: Pose) -> None:
        self.stage = stage
        self.g = stage.gene
        self.y = Y_CYTOSOL if stage.euk else stage.rna_y
        self.docked = stage.state.in_er
        self.er_y = getattr(stage, "er_y", self.y + ER_Y)
        self.signal = "cut" if stage.state.signal_cut else ("inserted" if self.docked else "none")

    def frame(self, start: Pose, k: float) -> tuple[float, float]:
        """``(xp, mrna shift)`` with the P site on codon ``k``: a free ribosome moves (shift 0),
        a docked one stays at its translocon and the mRNA slides left."""
        if not self.docked:
            return self._codon_x(start, k), 0.0
        return self.stage.dock_x, self.stage.dock_x - self._codon_x(start, k)

    def _codon_x(self, start: Pose, k: float) -> float:
        lo = int(math.floor(k))
        a = codon_x(self.stage, start, lo)
        b = codon_x(self.stage, start, lo + 1) if lo + 1 < len(self.g.codons) else a + SITE
        return a + (b - a) * (k - lo)

    def slide(self, p: Pose, start: Pose, shift: float) -> None:
        """The mRNA (and what rides on it) shifted by ``shift`` from where ``start`` has it."""
        if abs(shift) < 1e-12:
            return
        keys = ["cap", "eif4e"] + list(start.chain) + [f"pabpc1_{k}" for k in range(3)] + [f"hl{s}" for s in "EPA"] + ["start_mark", "stop_mark"]
        for key in keys:
            if key in start.els:
                x, y, o = start.els[key]
                p.els[key] = (x + shift, y, o)

    def pose(self, start: Pose, k: float, made: float, trnas: dict[int, tuple[float, float]], pairs: dict[int, float], bond: float = 0.0,
             large: float = 1.0, on: float = 1.0, readout: bool = True) -> Pose:
        """The ribosome with its P site at codon ``k``, ``made`` residues, the tRNAs at their
        codons (``trnas``: codon → (rise above its place, opacity)), the chain on the peptidyl
        tRNA (or, ``bond`` of the way, moving to the aminoacyl-tRNA in the A site)."""
        p = start.copy()
        xp, shift = self.frame(start, k)
        self.slide(p, start, shift)
        r = Ribosome(xp, self.y, on, large)
        for j, (rise, o) in trnas.items():
            cx = codon_x(self.stage, start, j) + shift
            r.trnas[j] = ((cx, self.y + TRNA_AT + rise), o)
        r.pairs = dict(pairs)
        place_ribosome(self.stage, p, r)
        whole = int(math.floor(made + 1e-9))
        if whole > 0:
            last = whole - 1
            on_trna = r.trnas.get(last, ((xp, self.y + TRNA_AT), 1.0))[0]
            anchor = (on_trna[0], on_trna[1] - TRNA_AT + AA_Y)
            if bond > 0 and (last + 1) in r.trnas:
                nxt = r.trnas[last + 1][0]
                anchor_next = (nxt[0], nxt[1] - TRNA_AT + AA_Y)
                place_chain(self.stage, p, whole + 1, anchor_next, (xp, self.y), "er" if self.docked else "cytosol", self.er_y, self.signal)
                before = p.copy()
                place_chain(self.stage, before, whole, anchor, (xp, self.y), "er" if self.docked else "cytosol", self.er_y, self.signal)
                t = ease(bond)
                for i in range(whole):
                    for pre in ("aa", "dt"):
                        key = f"{pre}{i}"
                        ax, ay, ao = before.els[key]
                        bx, by, bo = p.els[key]
                        p.els[key] = (ax + (bx - ax) * t, ay + (by - ay) * t, ao + (bo - ao) * t)
            else:
                place_chain(self.stage, p, whole, anchor, (xp, self.y), "er" if self.docked else "cytosol", self.er_y, self.signal)
        # amino acids waiting on their tRNAs (not yet in the chain)
        for j, ((tx, ty), o) in r.trnas.items():
            if j >= whole + (1 if bond > 0 else 0):
                p.els[f"aa{j}"] = (tx, ty - TRNA_AT + AA_Y, o)
                p.els[f"dt{j}"] = (tx, ty, 0.0)
        if readout:
            peptide_readout(self.stage, p, made + (bond if bond > 0 else 0.0))
        chain_ends(p, whole)
        p.cam = (xp + 1.0 + (0.0 if self.stage.wide else 0.5), cam_y(self.stage, self.y, self.docked))
        return p


def translate(b: Builder, options: dict[str, object]) -> None:
    """``translate``: initiation (when nothing is made yet), elongation cycles (the first
    ``DETAIL`` captioned, the rest fast), termination when the stop codon is reached."""
    stage = b.stage
    g = stage.gene
    total = len(g.codons) - 1
    made0 = stage.state.translated
    n = options.get("codons")
    upto = total if not isinstance(n, int) else min(total, made0 + n)
    t = Translation(stage, b.pose)
    if made0 == 0:
        initiate(b, t)
    elongate(b, t, max(made0, 1), upto, detail=made0 <= 1)
    if upto >= total:
        terminate(b, t)


def initiate(b: Builder, t: Translation) -> None:
    stage, g = t.stage, t.g
    euk = stage.euk
    y = t.y
    first = b.pose
    x5 = first.at("cap")[0] if euk else first.at(first.chain[0])[0]
    xa = codon_x(stage, first, 0)
    mark_start = (xa, y)
    stop_k = len(g.codons) - 1

    def marks(p: Pose, o: float) -> None:
        p.els["start_mark"] = (mark_start[0], y, o)
        p.els["stop_mark"] = (codon_x(stage, first, stop_k), y, o * 0.0)
        if "sd_mark" in stage.looks and g.sd is not None:
            p.els["sd_mark"] = (first.at(mature_key(stage, g.sd + 2))[0] + 0.5, y, o)

    def bind(s: Pose, u: float) -> Pose:
        start_x = x5 + 4.0 if euk else xa
        p = t.pose(s, 0, 0, {0: (0.0, window(u, 0.3, 0.7))}, {}, large=0.0, on=window(u, 0.25, 0.6))
        dx = start_x - xa
        for key in ("small", "tr0", "aa0", "siteE", "siteP", "siteA", "hlE", "hlP", "hlA"):
            x, yy, o = p.els[key]
            p.els[key] = (x + dx, yy, o)
        for key in ("hlE", "hlP", "hlA"):
            p.fade(key, 0.0)
        if euk:
            p.els["eif4f"] = (x5 + 1.6, y - 1.7, window(u, 0.0, 0.3))
            p.els["eif2"] = (start_x + 0.2, y + 6.9, window(u, 0.3, 0.6))
            p.els["eif3"] = (start_x + 5.6, y - 4.4, window(u, 0.3, 0.6))
        else:
            p.els["eif2"] = (start_x + 0.2, y + 6.9, window(u, 0.3, 0.6))
            p.els["eif3"] = (start_x + 5.6, y - 4.4, window(u, 0.3, 0.6))
        marks(p, window(u, 0.6, 1.0))
        for j in range(3):
            p.rungs[f"ac0_{j}"] = (p.rungs[f"ac0_{j}"][0], p.rungs[f"ac0_{j}"][1], 0.0)
        peptide_readout(stage, p, 0.0)
        p.cam = mix(s.cam, (start_x + 4.0, cam_y(stage, y)), ease(u))
        return p

    def scan(s: Pose, u: float) -> Pose:
        start_x = x5 + 4.0
        x = start_x + (xa - start_x) * ease(u)
        p = t.pose(s, 0, 0, {0: (0.0, 1.0)}, {0: window(u, 0.85, 1.0)}, large=0.0)
        dx = x - xa
        for key in ("small", "tr0", "aa0", "siteE", "siteP", "siteA"):
            xx, yy, o = p.els[key]
            p.els[key] = (xx + dx, yy, o)
        for key in ("hlE", "hlP", "hlA"):
            p.fade(key, 0.0)
        p.els["eif2"] = (x + 0.2, y + 6.9, 1.0)
        p.els["eif3"] = (x + 5.6, y - 4.4, 1.0)
        p.els["eif4f"] = (x5 + 1.6, y - 1.7, 1.0 - window(u, 0.5, 1.0))
        marks(p, 1.0)
        peptide_readout(stage, p, 0.0)
        p.cam = mix(s.cam, (xa + 1.0, cam_y(stage, y)), ease(u))
        return p

    def join(s: Pose, u: float) -> Pose:
        p = t.pose(s, 0, window(u, 0.4, 1.0), {0: (0.0, 1.0)}, {0: 1.0}, large=window(u, 0.3, 0.9))
        for key in ("hlE", "hlA"):
            p.fade(key, p.opacity(key) * window(u, 0.8, 1.0))
        p.els["eif2"] = (xa + 0.2, y + 6.9 + 3 * u, 1.0 - window(u, 0.0, 0.4))
        p.els["eif3"] = (xa + 5.6, y - 4.4 - 2 * u, 1.0 - window(u, 0.0, 0.4))
        p.fade("eif4f", 0.0)
        marks(p, 1.0)
        return p

    if euk:
        b.phase(1.0, "eIF4F (eIF4E on the cap, eIF4G, eIF4A) recruits the 43S complex: the 40S subunit with eIF3, eIF1, eIF1A and "
                     "eIF2·GTP carrying the initiator Met-tRNA<sub>i</sub>", bind)
        b.phase(1.2, "The 43S complex scans the 5′ UTR, 5′→3′, to the first AUG in a good context (GCCACC<b>AUG</b>G: Kozak)", scan)
        b.phase(1.2, "The anticodon CAU pairs with AUG in the P site; eIF2 hydrolyses its GTP and the factors leave; the 60S subunit "
                     "joins (eIF5B): the 80S ribosome", join)
    else:
        b.phase(1.0, "The 30S subunit binds the Shine–Dalgarno sequence (it pairs with the 3′ end of the 16S rRNA) with IF1, IF3 and "
                     "IF2·GTP carrying fMet-tRNA<sup>fMet</sup> on the AUG", bind)
        b.phase(1.0, "IF2 hydrolyses GTP, the factors leave and the 50S subunit joins: the 70S ribosome, fMet-tRNA in the P site", join)


def elongate(b: Builder, t: Translation, lo: int, hi: int, detail: bool = True, note: str | None = None) -> None:
    """Elongation cycles bringing codons ``lo … hi-1`` into the A site: made goes from ``lo``
    to ``hi`` (the first ``DETAIL`` captioned in three steps when ``detail``)."""
    stage, g = t.stage, t.g
    euk = stage.euk
    y = t.y
    ef1, ef2 = ("eEF1A·GTP", "eEF2·GTP") if euk else ("EF-Tu·GTP", "EF-G·GTP")

    def cycle(k: int, part: str) -> Callable[[Pose, float], Pose]:
        def fn(s: Pose, u: float) -> Pose:
            uu = ease(u)
            if part in ("deliver", "all"):
                d = uu if part == "deliver" else window(u, 0.0, 0.35)
                p = t.pose(s, k - 1, k, {k - 2: (0.0, 1.0 - d), k - 1: (0.0, 1.0), k: (6.0 * (1.0 - d), d)},
                           {k - 1: 1.0, k: window(d, 0.7, 1.0)}) if k >= 2 else \
                    t.pose(s, k - 1, k, {k - 1: (0.0, 1.0), k: (6.0 * (1.0 - d), d)}, {k - 1: 1.0, k: window(d, 0.7, 1.0)})
                tx, ty = p.at(f"tr{k}")
                p.els["eef1a"] = (tx + 2.4, ty + 1.3, d * (1.0 - window(u, 0.75, 1.0)) if part == "deliver" else window(u, 0.0, 0.1) * (1 - window(u, 0.25, 0.35)))
                if part == "all" and u > 0.35:
                    p = _bond_and_move(t, s, k, (u - 0.35) / 0.65)
                return p
            if part == "bond":
                p = t.pose(s, k - 1, k, {k - 1: (0.0, 1.0), k: (0.0, 1.0)}, {k - 1: 1.0, k: 1.0}, bond=uu)
                xp = t.frame(s, k - 1)[0]
                p.els["ptc"] = (xp - LARGE_W / 2 - 2.6, y + PTC[1], window(u, 0.0, 0.2) * (1 - window(u, 0.85, 1.0)))
                return p
            return _translocate(t, s, k, uu, u)
        return fn

    n_fast = sum(1 for k in range(lo, hi) if not (detail and k - lo < DETAIL))
    fast_weight = min(0.42, max(0.12, FAST_TOTAL / max(1, n_fast)))
    for k in range(lo, hi):
        fast = not (detail and k - lo < DETAIL)
        if fast:
            notes = note or (f"Elongation goes on, one codon per cycle (2–6 per second in human cells): each amino acid is added to the "
                             f"chain's C-terminus" if euk else "Elongation goes on (~15–20 amino acids per second in bacteria)")
            b.phase(fast_weight, notes, cycle(k, "all"))
        else:
            codon = g.codons[k]
            aa = AMINO_ACIDS[CODONS[codon]]
            anti = display_anticodon(codon)
            b.phase(1.0, f"{ef1} brings the aminoacyl-tRNA whose anticodon (5′-{anti}-3′) pairs with the codon {codon} in the A site: "
                         f"{aa}", cycle(k, "deliver"))
            b.phase(0.9, "Peptide bond: the peptidyl transferase centre (rRNA, a ribozyme) moves the chain from the P-site tRNA onto the "
                         "A-site amino acid — the chain grows at its C-terminus, N→C", cycle(k, "bond"))
            b.phase(0.9, f"{ef2} translocates the ribosome one codon (3 nt) towards the 3′ end: the tRNAs move from A and P to P and "
                         f"E; the empty tRNA leaves", cycle(k, "move"))


def _bond_and_move(t: Translation, s: Pose, k: int, u: float) -> Pose:
    if u < 0.4:
        return t.pose(s, k - 1, k, {k - 1: (0.0, 1.0), k: (0.0, 1.0)}, {k - 1: 1.0, k: 1.0}, bond=ease(u / 0.4))
    return _translocate(t, s, k, ease((u - 0.4) / 0.6), (u - 0.4) / 0.6)


def _translocate(t: Translation, s: Pose, k: int, uu: float, u: float) -> Pose:
    p = t.pose(s, k - 1 + uu, k + 1, {k - 1: (0.0, 1.0 - window(u, 0.6, 1.0)), k: (0.0, 1.0)}, {k - 1: 1.0 - window(u, 0.5, 0.9), k: 1.0})
    if (k - 1) in range(len(t.g.codons)):
        x, y, o = p.els[f"tr{k - 1}"]
        p.els[f"tr{k - 1}"] = (x - 1.5 * window(u, 0.6, 1.0), y + 3.0 * window(u, 0.6, 1.0), o)
    xp = t.frame(s, k - 1 + uu)[0]
    p.els["eef2"] = (xp + SITE + 0.4, t.y + 2.4, window(u, 0.0, 0.2) * (1.0 - window(u, 0.75, 1.0)))
    return p


def terminate(b: Builder, t: Translation) -> None:
    stage, g = t.stage, t.g
    euk = stage.euk
    stop_k = len(g.codons) - 1
    made = stop_k
    y = t.y

    def arrive(s: Pose, u: float) -> Pose:
        p = t.pose(s, stop_k - 1, made, {stop_k - 2: (0.0, 1.0 - window(u, 0.0, 0.4)), stop_k - 1: (0.0, 1.0)}, {stop_k - 1: 1.0})
        xa = codon_x(stage, s, stop_k) + t.frame(s, stop_k - 1)[1]
        p.els["erf"] = (xa, y + TRNA_AT + 6.0 * (1.0 - ease(u)), ease(u))
        p.els["stop_mark"] = (xa, y, 1.0)
        return p

    def release(s: Pose, u: float) -> Pose:
        p = t.pose(s, stop_k - 1, made, {stop_k - 1: (0.0, 1.0)}, {stop_k - 1: 1.0})
        xa = codon_x(stage, s, stop_k) + t.frame(s, stop_k - 1)[1]
        p.els["erf"] = (xa, y + TRNA_AT, 1.0)
        p.els["stop_mark"] = (xa, y, 1.0)
        # the chain slides out of the tunnel: every residue moves on along its way by the tunnel's length
        xp = t.frame(s, stop_k - 1)[0]
        ribo = (xp, y)
        out = Chain(stage).path_out("er" if t.docked else "cytosol", ribo, made, t.er_y)
        anchor = (p.at(f"tr{stop_k - 1}")[0], p.at(f"tr{stop_k - 1}")[1] - TRNA_AT + AA_Y)
        sig = g.signal if (t.docked and t.signal == "cut") else 0
        q = ease(u)
        for k in range(sig, made):
            sigma = (made - 1 - k) + q * (TUNNEL + 1)
            (x, yy), dot = chain_point(anchor, ribo, out, sigma)
            p.els[f"aa{k}"] = (x, yy, 0.0 if dot else 1.0)
            p.els[f"dt{k}"] = (x, yy, 1.0 if dot else 0.0)
        p.lines["chain"] = (tuple(f"dt{k}" if p.opacity(f"dt{k}") > 0.5 else f"aa{k}" for k in range(sig, made)), 0.0, "chain", 1.0)
        peptide_readout(stage, p, made, window(u, 0.5, 1.0))
        chain_ends(p, made, sig)
        x, yy = p.at(f"aa{made - 1}")
        p.els["cterm"] = (x + 0.95, yy + 0.55, window(u, 0.6, 1.0))
        # the camera rises to keep the released chain in view
        ys = [p.at(f"aa{k}")[1] for k in range(sig, made)]
        top = max(ys) + 1.5
        goal = max(s.cam[1], top - stage.height / 2)
        p.cam = (s.cam[0], s.cam[1] + (goal - s.cam[1]) * q)
        return p

    def recycle(s: Pose, u: float) -> Pose:
        p = s.copy()
        q = ease(u)
        # the subunits part in the cytosol: on the ER the large one cannot rise (the membrane is
        # over it), it moves aside
        rise = (6.0, -2.0) if t.docked else (3.0, 7.0)
        for key, dx, dy in (("small", -2.0, -5.0), ("large", *rise), ("erf", rise[0] - 1.0, rise[1] - 1.0),
                            (f"tr{stop_k - 1}", -2.0, -3.0 if t.docked else 6.0), ("siteE", *rise), ("siteP", *rise), ("siteA", *rise)):
            x, yy, o = s.els[key]
            p.els[key] = (x + dx * q, yy + dy * q, o * (1.0 - window(u, 0.2, 0.9)))
        for site in "EPA":
            p.fade(f"hl{site}", s.opacity(f"hl{site}") * (1.0 - q))
        for j in range(3):
            a, bb, o = s.rungs[f"ac{stop_k - 1}_{j}"]
            p.rungs[f"ac{stop_k - 1}_{j}"] = (a, bb, o * (1.0 - window(u, 0.0, 0.3)))
        p.fade("stop_mark", 1.0 - window(u, 0.6, 1.0))
        p.fade("start_mark", s.opacity("start_mark") * (1.0 - window(u, 0.6, 1.0)))
        xa = s.at("abce1")[0] if s.opacity("abce1") > 0 else p.at("small")[0]
        p.els["abce1"] = (s.at("large")[0] + 5.0, t.y + 0.9, window(u, 0.0, 0.2) * (1.0 - window(u, 0.7, 1.0)))
        if t.docked:
            p.fade("srp", 0.0)
        return p

    rf = "eRF1 (with eRF3·GTP)" if euk else "RF1 or RF2"
    b.phase(1.0, f"A stop codon ({g.stop}) has no tRNA: the release factor {rf} — shaped like a tRNA — binds it in the A site", arrive)
    b.phase(1.2, "The release factor makes the peptidyl transferase centre hydrolyse the bond to the P-site tRNA: the protein is released, "
                 "N-terminus first out of the tunnel" + (" into the ER lumen" if t.docked else ""), release)
    b.phase(1.0, "ABCE1 splits the ribosome; the subunits, the tRNA and the mRNA part (recycling) — the mRNA can be translated again"
            if euk else "RRF and EF-G split the ribosome (recycling)", recycle)


# ----- the ER ------------------------------------------------------------------------------------------


def target_er(b: Builder, options: dict[str, object]) -> None:
    """``target_er``: elongation until the signal peptide is out of the tunnel, SRP binds it and
    the ribosome (elongation pauses), docks on the SRP receptor, hands the ribosome to Sec61,
    elongation resumes into the lumen with the signal in the lateral gate, signal peptidase cuts."""
    stage = b.stage
    g = stage.gene
    t = Translation(stage, b.pose)
    made0 = stage.state.translated
    need = g.signal + TUNNEL
    if made0 < need:
        elongate(b, t, made0, need, detail=False, note="Elongation goes on; the signal peptide comes out of the exit tunnel")
    y = t.y
    k_now = need - 1
    s0 = b.pose
    xp = t.frame(s0, k_now)[0]
    stage.dock_x = xp
    er_y = y + ER_Y
    stage.er_y = er_y
    sec_x = xp + EXIT[0]
    trnas = {k_now: (0.0, 1.0)}
    pairs = {k_now: 1.0}

    def srp_bind(s: Pose, u: float) -> Pose:
        p = t.pose(s, k_now, need, trnas, pairs)
        signal = [p.at(f"aa{k}") for k in range(g.signal)]
        sx = sum(q[0] for q in signal) / len(signal)
        sy = max(q[1] for q in signal)
        p.els["srp"] = (sx + 4.0 * (1 - ease(u)), sy + 1.3 + 4.0 * (1 - ease(u)), window(u, 0.0, 0.4))
        p.cam = mix(s.cam, (xp + 1.0, cam_y(stage, y) + 1.5), ease(u))
        return p

    def dock(s: Pose, u: float) -> Pose:
        p = s.copy()
        q = ease(u)
        lift = 9.0 * (1.0 - q)
        p.els["er"] = (sec_x, er_y + lift, window(u, 0.0, 0.4))
        p.els["sr"] = (xp - LARGE_W / 2 - 1.0, er_y - ER_THICK / 2 - 0.5 + lift, window(u, 0.2, 0.6))
        p.els["sec61"] = (sec_x, er_y + lift, window(u, 0.0, 0.4))
        p.els["ost"] = (sec_x + 4.4, er_y + lift, window(u, 0.0, 0.4))
        for name, dy in (("lab_er_lumen", ER_THICK / 2 + 1.0), ("lab_er_cytosol", -ER_THICK / 2 - 1.0)):
            p.els[name] = (sec_x + 13.0, er_y + dy + lift, window(u, 0.0, 0.5))
        p.cam = mix(s.cam, (xp + 1.0, cam_y(stage, y, True)), q)
        return p

    docked = Translation(stage, s0)
    docked.docked, docked.signal, docked.er_y = True, "inserted", er_y

    def handover(s: Pose, u: float) -> Pose:
        target = docked.pose(s, k_now, need, trnas, pairs)
        p = s.copy()
        q = ease(u)
        for k in range(need):
            for pre in ("aa", "dt"):
                key = f"{pre}{k}"
                ax, ay, ao = s.els[key]
                bx, by, bo = target.els[key]
                p.els[key] = (ax + (bx - ax) * q, ay + (by - ay) * q, ao + (bo - ao) * q)
        if u > 0.5:
            p.lines["chain"] = target.lines["chain"]
        sx, sy, so = s.els["srp"]
        p.els["srp"] = (sx - 2.0 * u, sy - 1.0 * u, 1.0 - window(u, 0.2, 0.7))
        x, yy, o = s.els["sr"]
        p.els["sr"] = (x, yy, 1.0 - window(u, 0.5, 1.0) * 0.6)
        p.els["sec61"] = (sec_x, er_y, 1.0)
        chain_ends(p, need)
        return p

    b.phase(1.2, "The signal peptide's hydrophobic core leaves the exit tunnel: the signal recognition particle (SRP) binds it and "
                 "the ribosome, and elongation slows", srp_bind)
    b.phase(1.2, "SRP·GTP docks on the SRP receptor (SRα·GTP, anchored by SRβ) in the ER membrane", dock)
    b.phase(1.0, "The ribosome is handed to the Sec61 translocon, its tunnel over the channel; SRP and its receptor hydrolyse their GTP "
                 "and let go", handover)
    # elongation resumes, docked: the chain threads into the lumen, the signal opens the lateral gate
    stage.state = replace(stage.state, in_er=True, translated=need)
    t2 = Translation(stage, b.pose)
    t2.signal = "inserted"
    end = er_entry(g)
    if end > need:
        elongate(b, t2, need, end, detail=False,
                 note="Elongation resumes: the chain threads through Sec61 into the ER lumen; the signal peptide opens the channel's "
                      "lateral gate and sits in the membrane, its N-terminus in the cytosol (a loop)")
    cut_at = g.signal

    def cleave(s: Pose, u: float) -> Pose:
        p = s.copy()
        x, yy = s.at(f"aa{cut_at - 1}")
        p.els["spc"] = (x + 1.4, yy + 1.4, window(u, 0.0, 0.3) * (1.0 - window(u, 0.8, 1.0)))
        for k in range(cut_at):
            for pre in ("aa", "dt"):
                key = f"{pre}{k}"
                p.fade(key, s.opacity(key) * (1.0 - window(u, 0.45, 0.95)))
        keys, dy, hue, o = s.lines["chain"]
        mature = tuple(k for k in keys if int(k[2:]) >= cut_at)
        p.lines["chain"] = (mature if u > 0.45 else keys, dy, hue, o)
        p.fade("nterm", 0.0)
        return p

    b.phase(1.2, f"Signal peptidase cuts the signal peptide off after residue {cut_at} (small residues at −1 and −3) on the lumenal "
                 "side; signal peptide peptidase degrades it in the membrane", cleave)

    def settle(s: Pose, u: float) -> Pose:
        stage_t = Translation(stage, s)
        stage_t.docked, stage_t.signal = True, "cut"
        made = end
        trn = {made - 1: (0.0, 1.0)}
        target = stage_t.pose(s, made - 1, made, trn, {made - 1: 1.0})
        p = s.copy()
        q = ease(u)
        for k in range(cut_at, made):
            for pre in ("aa", "dt"):
                key = f"{pre}{k}"
                ax, ay, ao = s.els[key]
                bx, by, bo = target.els[key]
                p.els[key] = (ax + (bx - ax) * q, ay + (by - ay) * q, ao + (bo - ao) * q)
        p.lines["chain"] = (target.lines["chain"][0], 0.0, "chain", 1.0)
        p.cam = s.cam
        return p

    b.phase(0.6, "The mature N-terminus is free in the lumen; the chain goes on growing into it", settle)


def glycosylate(b: Builder, options: dict[str, object]) -> None:
    """``glycosylate``: (elongation until the first sequon's Asn reaches the OST,) then OST
    transfers the 14-sugar oligosaccharide en bloc from dolichol-PP onto each sequon's Asn."""
    stage = b.stage
    g = stage.gene
    state = stage.state
    total = len(g.codons) - 1
    if not state.released:
        reach = min(total - 1, glyco_reach(g))
        t = Translation(stage, b.pose)
        if reach > state.translated:
            elongate(b, t, state.translated, reach, detail=False,
                     note="Elongation goes on until the sequon's Asn reaches the oligosaccharyltransferase (OST) beside Sec61: "
                          "~65 residues from the peptidyl transferase centre")
    s0 = b.pose
    made_now = stage.state.translated if stage.state.released else min(total - 1, max(stage.state.translated, glyco_reach(g)))
    sites = [k for k in g.sequons if k < made_now]
    ost = s0.at("ost") if s0.opacity("ost") > 0 else s0.at("sec61")

    def transfer(s: Pose, u: float) -> Pose:
        p = s.copy()
        q = ease(u)
        loose = []
        for k in sites:
            j = g.sequons.index(k)
            dest = glycan_place(s, k)
            donor = (ost[0] + 0.4, ost[1] + ER_THICK / 2 + 2.6)
            p.els[f"gly{j}"] = (*mix(donor, dest, window(u, 0.3, 0.95)), window(u, 0.0, 0.25))
            if u < 0.95:
                loose.append(f"gly{j}")
        p.loose = tuple(loose)
        p.els["dol"] = (ost[0] + 2.4, ost[1] + 0.2, window(u, 0.0, 0.2) * (1.0 - window(u, 0.6, 0.9)))
        # the camera rises until the glycans' tops are in view (not past the ER membrane)
        tops = [glycan_place(s, k)[1] + 2.6 for k in sites]
        goal = min(max([s.cam[1]] + [t - stage.height / 2 for t in tops]), ost[1] + stage.height / 2 - 1.0)
        p.cam = mix(s.cam, (s.cam[0], max(s.cam[1], goal)), q)
        return p

    asn = ", ".join(f"Asn{k + 1}" for k in sites) or "the sequon's Asn"
    b.phase(1.6, f"The oligosaccharyltransferase (OST) transfers Glc<sub>3</sub>Man<sub>9</sub>GlcNAc<sub>2</sub> — 14 sugars, "
                 f"built on dolichol-PP — en bloc onto {asn} of Asn-X-Ser/Thr", transfer)


# ----- folding -----------------------------------------------------------------------------------------


def globule(stage: ExpressionStage, keys: list[int], center: Point) -> dict[int, Point]:
    """Places for the residues ``keys`` packed round ``center``: the hydrophobic ones inside,
    polar and charged ones outside (a 2-D cut through a folded domain)."""
    g = stage.gene
    spots: list[Point] = []
    ring = 0
    while len(spots) < len(keys):
        if ring == 0:
            spots.append(center)
        else:
            count = 6 * ring
            for j in range(count):
                a = 2 * math.pi * j / count + ring * 0.3
                spots.append((center[0] + ring * 1.02 * math.cos(a), center[1] + ring * 1.02 * math.sin(a)))
        ring += 1
    spots = spots[:len(keys)]
    protein = g.protein
    rank = sorted(keys, key=lambda k: (0 if side_chain(protein[k]) == "hydrophobic" else 1 if side_chain(protein[k]) == "special" else 2, k))
    ordered = sorted(spots, key=lambda q: math.dist(q, center))
    return {k: ordered[j] for j, k in enumerate(rank)}


def fold(b: Builder, options: dict[str, object]) -> None:
    """``fold``: chaperones hold the new chain (Hsp70 with ATP, or the chaperonin's chamber in
    the cytosol; BiP or calnexin with glucose trimming in the ER lumen) and it folds: hydrophobic
    side chains pack inside, polar and charged ones face the water."""
    stage = b.stage
    g = stage.gene
    state = stage.state
    in_er = state.in_er
    chaperone = options.get("chaperone")
    if chaperone is None:
        chaperone = ("calnexin" if state.glycosylated else "bip") if in_er else "hsp70"
    first = g.signal if in_er else 0
    made = len(g.codons) - 1
    keys = list(range(first, made))
    s0 = b.pose
    xs = [s0.at(f"aa{k}") for k in keys]
    cx = sum(x for x, _ in xs) / len(xs)
    cy = sum(y for _, y in xs) / len(xs) + (2.0 if not in_er else 0.0)
    radius = 1.02 * math.sqrt(len(keys) / 3.0)                     # the globule's rings
    if in_er:
        # in the lumen, clear of the ER membrane
        cy = max(cy, getattr(stage, "er_y", cy) + ER_THICK / 2 + radius + 1.0)
    er_y = getattr(stage, "er_y", None)
    anchored = in_er and chaperone == "calnexin" and er_y is not None
    cam_at = (cx, cy + 0.5)
    if anchored:
        # calnexin's lectin domain stands on its stalk over the membrane: the globule just over
        # it, the camera between the membrane and the glycans' tops, when the view is tall
        # enough for both (a tall frame); else (a wide one) as without the anchor, the stalk
        # running down out of the view
        low = er_y + ER_THICK / 2 + radius + 2.5                          # type: ignore[operator]
        top, bottom = low + radius + 4.0, er_y - ER_THICK / 2 - 0.5       # type: ignore[operator]
        if top - bottom <= stage.height - 0.5:
            cy = low
            cam_at = (cx, (top + bottom) / 2)
        else:
            cam_at = (cx, cy + 0.5)
    places = globule(stage, keys, (cx, cy))
    hydro = [k for k in keys if side_chain(g.protein[k]) == "hydrophobic"]
    holds = [hydro[j * len(hydro) // 3] for j in range(3)] if len(hydro) >= 3 else hydro

    def collapse(s: Pose, u: float, pull: float = 1.0) -> Pose:
        p = s.copy()
        q = ease(u) * pull
        for k in keys:
            ax, ay = s.at(f"aa{k}")
            bx, by = places[k]
            p.els[f"aa{k}"] = (ax + (bx - ax) * q, ay + (by - ay) * q, 1.0)
        _ends(p, keys)
        p.cam = mix(s.cam, cam_at, ease(u))
        return p

    def hold(name: str) -> Callable[[Pose, float], Pose]:
        def fn(s: Pose, u: float) -> Pose:
            p = s.copy()
            for j, k in enumerate(holds):
                x, y = s.at(f"aa{k}")
                p.els[f"{name}_{j}"] = (x + 0.2, y + 1.2, window(u, 0.1 * j, 0.3 + 0.1 * j))
            p.cam = mix(s.cam, (cx, cy + 0.5), ease(u))
            return p
        return fn

    def let_go(name: str) -> Callable[[Pose, float], Pose]:
        def fn(s: Pose, u: float) -> Pose:
            p = collapse(s, u)
            for j in range(len(holds)):
                x, y, o = s.els[f"{name}_{j}"]
                p.els[f"{name}_{j}"] = (x + (j - 1) * 3.0 * u, y + 3.0 * u, o * (1.0 - window(u, 0.0, 0.6)))
            return p
        return fn

    if chaperone in ("hsp70", "bip"):
        name = "hsp70" if chaperone == "hsp70" else "bip"
        who = ("Hsp70·ATP (with its Hsp40 partner)" if stage.euk else "DnaK·ATP (with DnaJ)") if name == "hsp70" else "BiP·ATP, the ER's Hsp70,"
        b.phase(1.2, f"{who} binds exposed hydrophobic stretches of the chain; ATP hydrolysis closes its lid on them", hold(name))
        b.phase(1.6, "Nucleotide exchange releases the chain, which folds: hydrophobic side chains pack inside, polar and charged ones "
                     "face the water" + (" (PDI forms its disulfide bonds)" if in_er and g.protein.count("C") >= 2 else ""), let_go(name))
    elif chaperone == "chaperonin":
        def enter(s: Pose, u: float) -> Pose:
            p = collapse(s, u, 0.6)
            p.els["cct"] = (cx, cy, window(u, 0.0, 0.3))
            return p

        def inside(s: Pose, u: float) -> Pose:
            p = collapse(s, u)
            p.els["cct"] = (cx, cy, 1.0)
            return p

        def leave(s: Pose, u: float) -> Pose:
            p = s.copy()
            p.els["cct"] = (cx, cy - 3.0 * ease(u), 1.0 - window(u, 0.2, 0.9))
            return p

        who = "The chaperonin TRiC (CCT)" if stage.euk else "GroEL"
        b.phase(1.2, f"{who} takes the chain into its chamber; ATP binding closes the lid" + ("" if stage.euk else " (GroES)"), enter)
        b.phase(1.4, "Inside the closed chamber the chain folds on its own, shielded from other proteins", inside)
        b.phase(0.8, "ATP hydrolysis opens the lid and the folded protein leaves", leave)
    else:   # calnexin
        shown = _glycans(stage, s0)
        lead = shown[0][1] if shown else 0

        def trim(s: Pose, u: float) -> Pose:
            p = s.copy()
            for _, j in shown:
                p.fade(f"gly{j}", 1.0 - window(u, 0.3, 0.7))
                p.fade(f"gly1_{j}", window(u, 0.3, 0.7))
            if shown:
                x, y = glycan_place(p, g.sequons[lead])
                p.els["glucosidase"] = (x + 3.2, y + 1.2, window(u, 0.0, 0.3) * (1.0 - window(u, 0.8, 1.0)))
            p.cam = mix(s.cam, cam_at, ease(u))
            return p

        def anchor(p: Pose, x: float, y: float, o: float) -> None:
            """Calnexin's domain at (x, y), its helix in the membrane under it, the stalk between."""
            p.els["calnexin"] = (x, y, o)
            if anchored:     # its helix beside the globule: the stalk reaches up past it
                p.els["calnexin_tm"] = (max(x, cx + radius + 1.6), er_y, o)  # type: ignore[assignment]
                p.lines["cnx_arm"] = (("calnexin_tm", "calnexin"), 0.0, "chain", o)

        def bind_cnx(s: Pose, u: float) -> Pose:
            p = collapse(s, u)
            if shown:
                x, y = glycan_place(p, g.sequons[lead])
                anchor(p, x + 2.8, y + 1.2, window(u, 0.0, 0.3))
            return p

        def free(s: Pose, u: float) -> Pose:
            p = s.copy()
            x, y, o = s.els["calnexin"]
            if anchored:     # it stays in the membrane; its domain lets go of the glycan
                anchor(p, x + 1.5 * u, y - 1.5 * u, o)
            else:
                p.els["calnexin"] = (x + 3.0 * u, y + 2.0 * u, o * (1.0 - window(u, 0.4, 0.9)))
            for _, j in shown:
                p.fade(f"gly1_{j}", 1.0 - window(u, 0.0, 0.4))
                p.fade(f"gly0_{j}", window(u, 0.0, 0.4))
            return p

        b.phase(1.2, "Glucosidases I and II trim two of the three glucoses: the monoglucosylated glycan", trim)
        b.phase(1.6, "Calnexin, a lectin chaperone in the ER membrane, binds it and holds the chain while it folds"
                     + (" (ERp57 forms disulfide bonds)" if g.protein.count("C") >= 2 else ""), bind_cnx)
        b.phase(1.0, "Glucosidase II removes the last glucose and calnexin lets go; a still unfolded protein would be re-glucosylated "
                     "by UGGT and bound again (the calnexin cycle)", free)


def _glycans(stage: ExpressionStage, p: Pose) -> list[tuple[int, int]]:
    """The glycans shown and their Asn: ``(residue, sequon number)``."""
    return [(k, j) for j, k in enumerate(stage.gene.sequons)
            if max(p.opacity(f"gly{j}"), p.opacity(f"gly1_{j}"), p.opacity(f"gly0_{j}")) > 0.5]


def glycan_place(p: Pose, asn: int) -> Point:
    """Where a glycan on residue ``asn`` is drawn (its middle; its GlcNAc on the Asn)."""
    x, y = p.at(f"aa{asn}")
    return (x + 1.6, y + 2.5)


def glycans_follow(stage: ExpressionStage, p: Pose) -> None:
    """Glycans stay on their Asn as the chain moves (all three trimming states), except one
    being transferred (``p.loose``)."""
    for j, k in enumerate(stage.gene.sequons):
        if f"gly{j}" in p.loose:
            continue
        x, y = glycan_place(p, k)
        for name in (f"gly{j}", f"gly1_{j}", f"gly0_{j}"):
            p.els[name] = (x, y, p.opacity(name))


def _ends(p: Pose, keys: list[int]) -> None:
    x, y = p.at(f"aa{keys[0]}")
    p.els["nterm"] = (x - 0.95, y + 0.55, 1.0)
    x, y = p.at(f"aa{keys[-1]}")
    p.els["cterm"] = (x + 0.95, y + 0.55, 1.0)


__all__ = ["DETAIL", "Translation", "cytosol_mrna", "display_anticodon", "elongate", "fold", "globule", "glycosylate", "make_cyto_looks",
           "target_er", "translate"]
