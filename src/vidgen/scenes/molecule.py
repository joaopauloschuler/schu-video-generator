"""``molecule``: a molecular close-up in physical scale (DESIGN.md §95.9, §95.10): molecules,
drawn from the shared catalog and glyphs of ``vidgen.cellworld`` (DNA, RNAs, nucleosomes, chromatin,
proteins, receptors, channels, carriers, pumps, ATP synthase, G proteins, small molecules and
ions) in a solution or a membrane (a lipid bilayer between its two compartments), with
correctly typeset names (gene symbols italic, protein names roman, charges as superscripts),
modification markers, labels of their parts and a scale bar in nm. Every placement and
orientation is checked: a GPCR's N-terminus is extracellular, ATP synthase's F₁ faces the
matrix (stroma, cytoplasm), the Na⁺/K⁺ pump is in an animal cell's plasma membrane.

Processes are actions (``scenes/molecule_actions.py``): states change with a morph, solutes
(``solutes``: particles at their concentrations on each side) diffuse, water follows osmosis,
channels, carriers and pumps transport, an action potential runs with a voltage readout and an
inset trace. Several membrane proteins in a tall frame are laid out on membrane rows."""

import math
import random
from dataclasses import replace
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .cell import PLATE_OPACITY, _spread
from .math_axes import ChainedTargets
from .molecule_gene import CELL_ONLY, GENE_ACTIONS, GeneExpression, GeneParams
from .molecule_process import Digits, Live
from .molecule_runtime import NOTE_Z, PARTICLE_Z, MoleculeRuntime, _ap_channels, _concentration, _end_state

tr = cell_transport
Length = float | str

#: Short names of membranes (``plasma`` for ``plasma_membrane``…).
MEMBRANE_ALIASES = {"plasma": "plasma_membrane", "inner_mitochondrial": "inner_mitochondrial_membrane", "thylakoid": "thylakoid_membrane",
                    "er": "er_membrane", "bacterial": "bacterial_inner_membrane", "endosomal": "endosomal_membrane",
                    "lysosomal": "lysosomal_membrane", "golgi": "golgi_membrane", "outer_mitochondrial": "outer_mitochondrial_membrane",
                    "vesicle": "vesicle_membrane"}
#: Membranes only one kind of cell has.
MEMBRANE_CELLS = {"thylakoid_membrane": "plant", "outer_envelope_membrane": "plant", "inner_envelope_membrane": "plant", "tonoplast": "plant",
                  "bacterial_inner_membrane": "bacterium", "bacterial_outer_membrane": "bacterium"}
#: Gaps between molecules laid out automatically, and the room round the drawing (nm).
GAP, GAP_SMALL, MARGIN = 3.0, 1.2, 2.5
LEADER_WIDTH = 1.6
#: Membrane rows (a tall frame): the room between two rows for their particles (nm).
ROW_ROOM = 7.0
#: Default target names of solutes.
SOLUTE_IDS = {"Na+": "sodium", "K+": "potassium", "Ca2+": "calcium", "Cl-": "chloride", "H+": "protons", "Mg2+": "magnesium"}
#: The kinds that move solutes (``transport``).
TRANSPORTERS_KINDS = ("ion_channel", "carrier", "na_k_atpase", "h_atpase", "abc_transporter", "aquaporin")
#: Process actions of this scene.
PROCESS_ACTIONS = ("set_state", "transport", "diffuse", "osmosis", "action_potential")


def membrane_name(text: str | None) -> str | None:
    """The catalog name of a membrane written in full or short (``plasma``)."""
    if text in (None, "none"):
        return None
    return MEMBRANE_ALIASES.get(text, text)  # type: ignore[arg-type]


class Modification(SceneParams):
    """A modification marker: ``{mark, at}`` (``{mark: P, at: Ser15}``) or a mark alone (``P``)."""

    also_accepts = (str,)

    mark: Literal["P", "Ub", "Ac", "Me"]
    """P (phosphorylation: Ser, Thr, Tyr), Ub (ubiquitin: Lys), Ac (acetyl: Lys), Me (methyl: Lys, Arg)."""
    at: str | None = None
    """The residue: Ser15 or S15 (checked: phosphate never on Lys)."""
    domain: str | None = None
    """A protein's domain the marker sits on (one of its domains), e.g. kinase."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"mark": data} if isinstance(data, str) else data


class MoleculeItem(SceneParams):
    """One molecule: ``{kind, id, at, ...}`` and the options of its kind; a kind alone (``atp``)
    is one of it, placed automatically."""

    also_accepts = (str,)

    kind: str
    """dna, mrna, trna, rrna, nucleosome, chromatin, protein, kinase, phosphatase, g_protein, gpcr, rtk, ion_channel, carrier, na_k_atpase, h_atpase, abc_transporter, aquaporin, atp_synthase, atp, adp, pi, gtp, gdp, camp, glucose, ligand, ion, water, o2, co2, drug."""
    id: str | None = None
    """Its name for actions (default: the kind, kind_2 for a second)."""
    at: float | tuple[float, float] | None = None
    """Where its middle is, in nm from the view's middle: a membrane protein x along the membrane; others [x, y] (y up: the membrane's exoplasmic side); default laid out in a row."""
    angle: float | None = None
    """Turn in degrees (not membrane proteins: they keep their orientation)."""
    inside: str | None = Field(None, alias="in")
    """A soluble molecule's compartment (extracellular, cytosol, matrix…): the side of the membrane it is on (checked: DNA in the nucleoplasm, cAMP in the cytosol)."""
    faces: str | None = None
    """A membrane protein: the compartment its oriented part faces (ATP synthase F₁: matrix; a GPCR's N-terminus: extracellular); checked."""
    state: str | None = None
    """Its state at the start (set_state changes it): gpcr / g_protein: inactive or active; rtk: monomer or dimer; ion_channel: closed, open or inactivated; carrier: outward, occluded or inward; na_k_atpase and h_atpase: e1, e1p, e2p or e2; abc_transporter: inward or outward; atp_synthase: synthesis or hydrolysis; kinase: active or inactive; chromatin: 10nm or compact."""
    label: TranslatableStr | bool | None = None
    """Its name under it (default: the kind's, or the gene / protein given); false for none. Pango markup: <i>, <sup>, <sub>."""
    gene: str | None = None
    """A gene symbol (italic, checked against the species' nomenclature: human TP53, mouse Trp53, yeast CDC28)."""
    protein: str | None = None
    """A protein name (roman: TP53 or p53; mouse TRP53; yeast Cdc28)."""
    species: str | None = None
    """For gene and protein: human (default: the scene's), mouse, rat, yeast, fission_yeast, fly, zebrafish, e_coli, arabidopsis."""
    parts: bool | list[str] | None = None
    """Name its parts with leader lines (true, false or names); default true when it is the only molecule."""
    bp: int | None = None
    """DNA: base pairs (default 21, two turns)."""
    sequence: str | None = None
    """DNA: the top strand 5′→3′ (its partner is drawn antiparallel); mRNA: its sequence (ACGU)."""
    letters: bool | None = None
    """DNA, mRNA: write the bases (default when a sequence is given)."""
    anticodon: str | None = None
    """tRNA: its anticodon 5′→3′ (CAU reads the codon AUG); checked against amino_acid."""
    amino_acid: str | None = None
    """tRNA: the amino acid on its 3′ CCA end (Met, Phe…)."""
    style: Literal["cloverleaf", "l_shape"] | None = None
    """tRNA: cloverleaf (secondary structure, default) or l_shape (3-D shape)."""
    rrna: str | None = None
    """rRNA: 18S, 28S, 5.8S, 5S, 16S, 23S, 12S."""
    marks: list[str] = Field(default_factory=list)
    """Nucleosome: histone marks (H3K4me3, H3K27ac, H3K9me3, H4K16ac, H2AK119ub, H3S10ph), checked against the histone sequences."""
    nucleosomes: int | None = Field(None, ge=2, le=24)
    """Chromatin: how many nucleosomes."""
    domains: list[str] = Field(default_factory=list)
    """Protein: its domains' names (SH2, kinase…), one lobe each."""
    mass: float | None = None
    """Protein: its mass in kDa (sets its size; 50 kDa is about 5 nm)."""
    ligand: bool | None = None
    """gpcr: a ligand in its pocket; ion_channel with ligand gating: bound when open."""
    gating: Literal["voltage", "ligand", "mechanical"] | None = None
    """ion_channel: what opens it (default voltage)."""
    ion: str | None = None
    """ion_channel: the ion it passes (K+, Na+, Ca2+, Cl-); ion: which ion (Na+, K+, Ca2+, Cl-, H+, Mg2+)."""
    mode: Literal["uniport", "symport", "antiport"] | None = None
    """carrier: one solute, two the same way, two opposite ways."""
    transporter: str | None = None
    """carrier: a named carrier that sets mode, substrates, moves and ratio: glut1, glut4, sglt1 (2 Na⁺ + glucose in), sglt2, ncx (3 Na⁺ in, Ca²⁺ out), nhe1, nkcc1, kcc2."""
    substrates: list[str] = Field(default_factory=list)
    """carrier: its solutes (Na+, glucose, H+, Ca2+…); abc_transporter: its one substrate (default drug)."""
    moves: list[Literal["in", "out"]] = Field(default_factory=list)
    """carrier: the way each solute moves (in: into the cytosol); abc_transporter: out (export, default) or in (bacterial importers only)."""
    ratio: list[int] = Field(default_factory=list)
    """carrier: how many of each substrate per cycle ([2, 1]: 2 Na⁺ per glucose)."""
    c_subunits: int | None = None
    """atp_synthase: c subunits in its ring (default by membrane: 8 mitochondria, 14 chloroplasts, 10 bacteria)."""
    cap: bool | None = None
    """mRNA: the 5′ cap (default true)."""
    tail: bool | None = None
    """mRNA: the poly(A) tail (default true)."""
    modifications: list[Modification] = Field(default_factory=list)
    """Markers on a protein: P, Ub, Ac, Me, each with its residue ({mark: P, at: Ser15})."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"kind": data} if isinstance(data, str) else data

    @field_validator("at", mode="before")
    @classmethod
    def _at(cls, value: Any) -> Any:
        if value is None or isinstance(value, (int, float)):
            return value
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return (parse_length(value[0], "at x") * 1000 if isinstance(value[0], str) else float(value[0]),
                    parse_length(value[1], "at y") * 1000 if isinstance(value[1], str) else float(value[1]))
        raise ValueError("at is a number (nm along the membrane) or [x, y] in nm")

    def spec(self, where: str, membrane: str | None) -> MoleculeSpec:
        return MoleculeSpec(self.kind, self.state, self.bp, self.sequence, self.letters, self.anticodon, self.amino_acid, self.style, self.rrna,
                            tuple(self.marks), self.nucleosomes, tuple(self.domains), self.mass, self.ligand, self.gating, self.ion, self.mode,
                            tuple(self.substrates), tuple(self.moves), self.c_subunits, self.cap, self.tail,
                            tuple((m.mark, m.at, m.domain) for m in self.modifications), membrane, where, tuple(self.ratio), self.transporter)


class Solute(SceneParams):
    """Free particles of one solute at its concentration on each side: ``{solute, mM, id, count}``;
    a name alone (``K+``) takes the typical plasma-membrane values."""

    also_accepts = (str,)

    solute: str
    """An ion (Na+, K+, Ca2+, Cl-, H+, Mg2+) or a small molecule (glucose, water, o2, co2, atp, drug…)."""
    id: str | None = None
    """Its name for actions (default: sodium, potassium, calcium, chloride, protons, magnesium, or the molecule's name)."""
    mM: dict[str, float] = Field(default_factory=dict)
    """Concentration (mM) on each side: the membrane's two compartments ({extracellular: 5, cytosol: 140}), or left and right without a membrane; default: the typical values of a mammalian cell's plasma membrane."""
    count: int = Field(12, ge=1, le=40)
    """Particles drawn on the more concentrated side (the other side in proportion; none below 1 % of it)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"solute": data} if isinstance(data, str) else data

    @property
    def name(self) -> str:
        return self.id or SOLUTE_IDS.get(self.solute, self.solute)


class Placed:
    """A molecule of the scene placed (nm): its id, item, kind, glyph, centre, angle and the
    membrane row it is in (``None``: not in a membrane)."""

    def __init__(self, entry_id: str, item: MoleculeItem, glyph: MoleculeGlyph, center: tuple[float, float], angle: float, where: str,
                 spec: MoleculeSpec | None = None) -> None:
        self.id, self.item, self.glyph, self.center, self.angle, self.where = entry_id, item, glyph, center, angle, where
        self.kind = MOLECULE_KINDS[item.kind]
        self.spec = spec
        self.row: int | None = None

    def bounds(self) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = self.glyph.bounds
        pts = [(x, y) for x in (x0, x1) for y in (y0, y1)]
        c, s = math.cos(self.angle), math.sin(self.angle)
        xs = [self.center[0] + x * c - y * s for x, y in pts]
        ys = [self.center[1] + x * s + y * c for x, y in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def point(self, p: tuple[float, float]) -> tuple[float, float]:
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (self.center[0] + p[0] * c - p[1] * s, self.center[1] + p[0] * s + p[1] * c)


def layout(items: list[MoleculeItem], membrane: str | None, scene_compartment: str, cell: str, species: str) -> list[Placed]:
    """Check and place the molecules: ids, options (:func:`check_molecule`), names, membranes
    and orientations, compartments; written ``at`` first, the others in a row (membrane proteins
    along the membrane, the rest below it on the cytosolic side, or above for an exoplasmic
    ``in``). Raises :class:`VidgenError` naming the molecule."""
    placed: list[Placed] = []
    ids: set[str] = set()
    counts: dict[str, int] = {}
    exo, cyto = membrane_sides(membrane) if membrane else (None, None)
    for k, item in enumerate(items):
        where = f"molecules[{k}] ({item.kind})"
        if item.kind not in MOLECULE_KINDS:
            raise VidgenError(f"{where}: unknown molecule '{item.kind}'{did_you_mean(item.kind, list(MOLECULE_KINDS))} (molecules: {', '.join(MOLECULE_KINDS)})")
        kind = MOLECULE_KINDS[item.kind]
        counts[item.kind] = counts.get(item.kind, 0) + 1
        entry_id = item.id or (item.kind if counts[item.kind] == 1 else f"{item.kind}_{counts[item.kind]}")
        if entry_id in ids or entry_id in ("title", "membrane", "scale_bar", "potential"):
            raise VidgenError(f"{where}: id '{entry_id}' is taken; give it another id")
        ids.add(entry_id)
        where = f"molecules[{k}] ({kind.plain} '{entry_id}')"
        cells = MEMBRANE_CELLS.get(membrane or "", cell)
        if cells not in kind.cells:
            raise VidgenError(f"{where}: not in a{'n' if cells[0] in 'aeiou' else ''} {cells} cell: {kind.cells_why}")
        spec = check_molecule(item.spec(where, membrane))
        _names(item, species, where)
        if kind.bound:
            if membrane is None:
                raise VidgenError(f"{where}: a {kind.plain} sits {'on' if kind.family == 'peripheral' else 'in'} a membrane: give the scene a "
                                  f"membrane (plasma, inner_mitochondrial, thylakoid…)")
            check_molecule_membrane(kind, membrane, where)
            check_molecule_faces(kind, membrane, item.faces, where)
            if item.angle is not None:
                raise VidgenError(f"{where}: a membrane protein keeps its orientation; leave out angle (faces: names its sides)")
            if item.inside is not None:
                raise VidgenError(f"{where}: in is for soluble molecules; a membrane protein is in the membrane")
        else:
            if item.faces is not None:
                raise VidgenError(f"{where}: faces is for membrane proteins")
            compartment = item.inside or (cyto if membrane else scene_compartment)
            if membrane and compartment not in (exo, cyto):
                raise VidgenError(f"{where}: in '{compartment}': this membrane lies between the {exo} and the {cyto}")
            if compartment not in CELL_COMPARTMENTS:
                raise VidgenError(f"{where}: in '{compartment}'{did_you_mean(compartment, list(CELL_COMPARTMENTS))}")
            check_molecule_place(kind, compartment, where)
        glyph = molecule_glyph(spec)
        angle = math.radians(item.angle or 0.0)
        placed.append(Placed(entry_id, item, glyph, (0.0, 0.0), angle, where, spec))
    _arrange(placed, membrane)
    return placed


def _names(item: MoleculeItem, species: str, where: str) -> None:
    sp = item.species or species
    if item.gene is not None:
        gene_markup(item.gene, sp, f"{where}: gene")
    if item.protein is not None:
        check_protein(item.protein, sp, f"{where}: protein", item.gene)
    if isinstance(item.label, str):
        check_markup(str(item.label), f"{where}: label")


def _arrange(placed: list[Placed], membrane: str | None, slots: dict[str, float] | None = None, aspect: float = 16 / 9,
             names: float = 0.0) -> list[float]:
    """Centres: written ``at`` as given; the rest in rows by lane — in the membrane, then the
    cytosolic and the exoplasmic side — each row centred, molecules ``GAP`` apart, each taking
    at least its ``slots`` width (nm: room for its name under it), rows ``names`` nm further
    apart for the names. Several membrane proteins in a tall frame (``aspect`` < 1) go on
    membrane rows, one under the other. Returns the membrane rows' y (nm)."""
    lanes: dict[str, list[Placed]] = {"membrane": [], "below": [], "above": []}
    exo = membrane_sides(membrane)[0] if membrane else None
    for p in placed:
        p.row = 0 if p.kind.bound else None
        if p.item.at is not None:
            at = p.item.at
            p.center = (float(at), 0.0) if not isinstance(at, tuple) else at
            if p.kind.bound and isinstance(at, tuple):
                raise VidgenError(f"{p.where}: a membrane protein's at is one number, x along the membrane (nm)")
            continue
        lane = "membrane" if p.kind.bound else ("above" if membrane and p.item.inside == exo else "below")
        lanes[lane].append(p)
    widths = {id(p): max(p.glyph.bounds[2] - p.glyph.bounds[0], (slots or {}).get(p.id, 0.0)) for p in placed}

    def gap(a: Placed, b: Placed) -> float:
        return GAP_SMALL if a.kind.family == "small" and b.kind.family == "small" else GAP

    rows_y = [0.0]
    in_membrane = lanes["membrane"]
    membrane_rows = [in_membrane]
    written = any(p.kind.bound and p.item.at is not None for p in placed)
    if (aspect < 1.0 and len(in_membrane) > 1 or len(in_membrane) > 2) and not written:
        # several rows when that frames them larger (a tall frame; a wide one narrowed by a panel)
        tall = max(p.glyph.bounds[3] - p.glyph.bounds[1] for p in in_membrane) + names + ROW_ROOM
        membrane_rows = _rows(in_membrane, widths, aspect, gap, tall)
        rows_y = [0.0]
        for upper, lower in zip(membrane_rows, membrane_rows[1:]):
            # room between two rows: the upper row's names, its cytosol's and the lower row's
            # exoplasmic side's names, particles
            drop = max(-p.glyph.bounds[1] for p in upper) + 2.6 * names + ROW_ROOM + max(p.glyph.bounds[3] for p in lower)
            rows_y.append(rows_y[-1] - drop)
    for k, row in enumerate(membrane_rows):
        _place_row(row, widths, gap, lambda p, k=k: rows_y[k])
        for p in row:
            p.row = k
    bound = [p for p in placed if p.kind.bound]
    bottom = min((p.center[1] + p.glyph.bounds[1] for p in bound), default=-BILAYER_NM / 2)
    top = max((p.center[1] + p.glyph.bounds[3] for p in bound), default=BILAYER_NM / 2)
    for lane in ("below", "above"):
        rows = _rows(lanes[lane], widths, aspect, gap)
        level = 0.0
        for row in rows:
            tall = max((p.glyph.bounds[3] - p.glyph.bounds[1] for p in row), default=0.0)

            def y_of(p: Placed, level: float = level) -> float:
                y0, y1 = p.glyph.bounds[1], p.glyph.bounds[3]
                if membrane is None:
                    return -(y0 + y1) / 2 - level
                if lane == "below":
                    return min(bottom, rows_y[-1] - BILAYER_NM / 2) - GAP - y1 - level
                return max(top, BILAYER_NM / 2) + GAP - y0 + level

            _place_row(row, widths, gap, y_of)
            level += tall + GAP + names
    return rows_y


def _place_row(row: list[Placed], widths: dict[int, float], gap: Any, y_of: Any) -> None:
    """One row of molecules centred on x = 0, each in its slot, at the height ``y_of`` gives."""
    gaps = [gap(a, b) for a, b in zip(row, row[1:])] + [0.0]
    total = sum(widths[id(p)] for p in row) + sum(gaps)
    x = -total / 2
    for p, after in zip(row, gaps):
        x0, x1 = p.glyph.bounds[0], p.glyph.bounds[2]
        p.center = (x + (widths[id(p)] - (x1 - x0)) / 2 - x0, y_of(p))
        x += widths[id(p)] + after


def _rows(row: list[Placed], widths: dict[int, float], aspect: float, gap: Any, tall: float | None = None) -> list[list[Placed]]:
    """``row`` cut into the number of rows that frames them largest in a body of ``aspect``
    (each row ``tall`` nm, default the tallest molecule's height)."""
    if len(row) < 2:
        return [row]
    total = sum(widths[id(p)] for p in row) + sum(gap(a, b) for a, b in zip(row, row[1:]))
    tall = tall if tall is not None else max(p.glyph.bounds[3] - p.glyph.bounds[1] for p in row) + GAP
    best = min(range(1, len(row) + 1), key=lambda n: max(total / n / aspect, n * tall))
    size = math.ceil(len(row) / best)
    return [row[k:k + size] for k in range(0, len(row), size)]


# ----- solutes, gradients ---------------------------------------------------------------------------


def solute_problem(s: Solute, membrane: str | None, where: str) -> str | None:
    """Why a ``solutes`` entry is wrong (an unknown solute, a side the membrane has not, no
    concentrations where none are typical), or ``None``."""
    known = [*SOLUTE_IDS, *(k for k, m in MOLECULE_KINDS.items() if m.family == "small" and k != "ion")]
    if s.solute not in known:
        return f"{where}: solute '{s.solute}'{did_you_mean(s.solute, known)} (ions: {', '.join(SOLUTE_IDS)}; or glucose, water, o2, co2, atp, drug…)"
    sides = list(membrane_sides(membrane)) if membrane else ["left", "right"]
    for side, value in s.mM.items():
        if side not in sides:
            return f"{where}: mM side '{side}'{did_you_mean(side, sides)}: give {' and '.join(sides)}"
        if value < 0:
            return f"{where}: mM {side}: a concentration is 0 or more"
    if not s.mM and not (membrane == "plasma_membrane" and s.solute in TYPICAL_CONCENTRATIONS) and s.solute != "water":
        return f"{where}: give its concentrations, mM: {{{sides[0]}: …, {sides[1]}: …}} (typical values are known only for ions and glucose at the plasma membrane)"
    if s.mM and len(s.mM) != 2:
        return f"{where}: mM: give both sides, {{{sides[0]}: …, {sides[1]}: …}}"
    return None


def solute_levels(s: Solute, membrane: str | None) -> dict[str, float]:
    """A solute's concentrations (mM) by side name: the written ones, else the typical
    plasma-membrane values; water: 55 M on both sides."""
    if s.mM:
        return dict(s.mM)
    if s.solute == "water":
        sides = list(membrane_sides(membrane)) if membrane else ["left", "right"]
        return {side: 55000.0 for side in sides}
    cyto, exo = TYPICAL_CONCENTRATIONS[s.solute]
    exo_name, cyto_name = membrane_sides(membrane)  # type: ignore[arg-type]
    return {exo_name: exo, cyto_name: cyto}


@scene("molecule")
class Molecule(MoleculeRuntime, GeneExpression, NarratedScene):
    """A molecular close-up in nm: molecules in a solution or a membrane (the lipid bilayer
    with its two compartments named), each drawn to its textbook size — the DNA double helix
    with its 5′/3′ ends, base pairs and grooves; mRNA, tRNA, rRNA; a nucleosome, chromatin;
    proteins with domains; GPCRs, RTKs, gated channels, carriers, the Na⁺/K⁺ pump, H⁺ pumps, ABC
    transporters, aquaporins, ATP synthase; G proteins, kinases; ATP, GTP, cAMP, Pᵢ, glucose,
    water, O₂, CO₂, ions — with gene symbols in italics, protein names in roman type, charges as
    superscripts, modification markers (P, Ub, Ac, Me), labels of their parts and a scale bar.
    Orientations and places are checked. Solutes are drawn as particles at their concentrations;
    the actions set_state, transport, diffuse, osmosis and action_potential animate processes.

    With a ``gene`` the scene is a close-up of its expression (``scenes/molecule_gene.py``): the
    steps transcribe, cap, splice, polyadenylate, export, translate, target_er, glycosylate and
    fold are actions on the gene's id.

    Action targets: ``title``, ``membrane``, ``scale_bar``, ``potential`` (with a membrane
    potential), each molecule's id and each solute's id; with a gene: ``title`` and the gene's id."""

    outro = 0.5
    target_patterns = ("title", "membrane", "scale_bar", "potential", "<id>", "<solute>")
    #: The process actions that act on this scene type.
    process_actions = PROCESS_ACTIONS + GENE_ACTIONS + CELL_ONLY
    mid_still_actions = frozenset(GENE_ACTIONS)

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        membrane: str = "none"
        """none (a solution) or the membrane across the view: plasma, inner_mitochondrial, thylakoid, er, bacterial, endosomal, lysosomal, golgi, vesicle, outer_mitochondrial (or a full name: plasma_membrane…)."""
        compartment: str = "cytosol"
        """Without a membrane: the compartment the molecules are in (cytosol, nucleoplasm, matrix…), checked for each."""
        cell: Literal["animal", "plant", "bacterium"] = "animal"
        """The kind of cell (checked: no Na⁺/K⁺ pump in a plant, no nucleosomes in a bacterium); a thylakoid or bacterial membrane sets it."""
        species: str = "human"
        """Nomenclature for gene and protein names: human, mouse, rat, yeast, fission_yeast, fly, zebrafish, e_coli, arabidopsis."""
        molecules: list[MoleculeItem] = Field(default_factory=list, max_length=40)
        """The molecules: a kind, or {kind, id, at, state, label, gene, protein, parts, ...}."""
        solutes: list[Solute] = Field(default_factory=list, max_length=8)
        """Free particles at their concentrations on each side: a solute (K+) or {solute, mM: {extracellular: 5, cytosol: 140}, id, count}."""
        potential: float | None = None
        """The membrane potential (mV, the cytosolic side relative to the other: −70 for a resting neuron): a live readout and the membrane's charges; default: none (−70 assumed at the plasma membrane for gradients)."""
        bars: bool = True
        """With solutes: their concentrations on each side as bars with values (they change with diffuse and osmosis)."""
        width: Length | None = None
        """What the view spans across the body's shorter side ('30 nm'); default: fits the molecules."""
        sides: bool = True
        """Name the compartments on either side of the membrane."""
        labels: bool = True
        """Name the molecules (under each) and their parts (see parts)."""
        scale_bar: bool = True
        """A scale bar in nm."""
        reveal: Literal["all", "per_beat"] = "all"
        """all: everything in the first beat; per_beat: the membrane, then one molecule per beat."""
        seed: int = 1
        """Changes where particles start and the random walks they take."""
        title_size: ThemeSize = "heading"
        """Title size."""
        label_size: ThemeSize = "caption"
        """Size of the labels and the scale bar's text."""
        gene: GeneParams | None = None
        """A gene whose expression the scene shows (then no molecules, solutes or membrane): {codons, introns, signal_peptide, glycosylation, seed} or {sequence, introns: [[start, end]]} or {protein}; its steps are actions (transcribe: gene)."""

        @field_validator("width", mode="before")
        @classmethod
        def _width(cls, value: Any) -> float | None:
            return None if value is None else parse_length(value, "width") * 1000.0

        def placed(self) -> list[Placed]:
            membrane = membrane_name(self.membrane)
            return layout(self.molecules, membrane, self.compartment, self.cell, self.species)

        @model_validator(mode="after")
        def _check(self) -> "Molecule.Params":
            try:
                membrane = membrane_name(self.membrane)
                if membrane is not None and membrane not in CELL_MEMBRANES:
                    names = [*MEMBRANE_ALIASES, *CELL_MEMBRANES]
                    raise VidgenError(f"membrane '{self.membrane}'{did_you_mean(self.membrane, names)} (none, {', '.join(MEMBRANE_ALIASES)})")
                if self.compartment not in CELL_COMPARTMENTS:
                    raise VidgenError(f"compartment '{self.compartment}'{did_you_mean(self.compartment, list(CELL_COMPARTMENTS))}")
                nomenclature_species(self.species, "species")
                placed = self.placed()
                taken = {p.id for p in placed} | {"title", "membrane", "scale_bar", "potential"}
                for k, s in enumerate(self.solutes):
                    problem = solute_problem(s, membrane, f"solutes[{k}] ({s.solute})")
                    if problem:
                        raise VidgenError(problem)
                    if s.name in taken:
                        raise VidgenError(f"solutes[{k}] ({s.solute}): id '{s.name}' is taken; give it another id")
                    taken.add(s.name)
                if self.potential is not None and membrane is None:
                    raise VidgenError("potential: a membrane potential is across a membrane; give the scene a membrane")
                if self.gene is not None:
                    taken = [k for k, v in (("molecules", self.molecules), ("solutes", self.solutes), ("membrane", membrane),
                                            ("potential", self.potential)) if v]
                    if taken:
                        raise VidgenError(f"gene: a gene close-up draws its own DNA, RNAs, ribosomes and membranes; leave out "
                                          f"{', '.join(taken)} (put other molecules in another molecule scene)")
                    self.gene.gene(self.cell, self.species)
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

        def gradients(self) -> Any:
            """What drives transport here: concentrations by species (cytosolic side, other side)
            and the membrane potential."""
            membrane = membrane_name(self.membrane)
            levels: dict[str, tuple[float, float]] = {}
            if membrane is not None:
                exo, cyto = membrane_sides(membrane)
                for s in self.solutes:
                    if s.mM:
                        values = solute_levels(s, membrane)
                        levels[s.solute] = (values.get(cyto, 0.0), values.get(exo, 0.0))
            return tr.Gradients.typical(membrane, levels, self.potential)

    @classmethod
    def gene_symbols(cls, params: Any) -> list[str]:
        """The gene symbols the scene declares (its gene's ``name``, its molecules' ``gene``):
        set in italics where the captions show them."""
        names = [params.gene.name] if params.gene is not None and params.gene.name else []
        return names + [m.gene for m in params.molecules if m.gene]

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        if params.gene is not None:
            return (["title"] if params.title else []) + [params.gene.id]
        names = (["title"] if params.title else []) + (["membrane"] if membrane_name(params.membrane) else [])
        names += [p.id for p in params.placed()] + [s.name for s in params.solutes]
        names += ["potential"] if params.potential is not None else []
        return names + (["scale_bar"] if params.scale_bar else [])

    # ----- validation of the process actions ---------------------------------------------------

    @classmethod
    def process_problem(cls, params: Any, name: str, target: str, options: Any) -> str | None:
        """Why a process action ``name`` cannot act on ``target`` with ``options`` (whatever the
        state at its time: :meth:`action_sequence_problems` replays those), or ``None``."""
        if name in GENE_ACTIONS or name in CELL_ONLY:
            return cls.gene_problem(params, name, target, options)
        if params.gene is not None:
            return f"{name} needs membranes, molecules or solutes; this scene is a gene close-up (its steps: {', '.join(GENE_ACTIONS)})"
        membrane = membrane_name(params.membrane)
        placed = {p.id: p for p in params.placed()}
        solutes = {s.name: s for s in params.solutes}
        if name in ("osmosis", "action_potential"):
            if target != "membrane":
                return f"{name} acts on the membrane: {name}: membrane"
            if membrane is None:
                return f"{name} needs a membrane (membrane: plasma…)"
        if name == "set_state":
            if target not in placed:
                return f"set_state acts on a molecule{did_you_mean(target, list(placed))}"
            p = placed[target]
            if not p.kind.states:
                return f"'{target}' ({p.kind.plain}) has one look: no states to change"
            try:
                check_molecule(replace(p.spec, state=options.state, where=f"set_state '{target}'"))  # type: ignore[arg-type]
            except VidgenError as error:
                return str(error)
            return None
        if name == "transport":
            if target not in placed:
                return f"transport acts on a membrane protein that moves solutes{did_you_mean(target, list(placed))}"
            p = placed[target]
            if p.item.kind not in TRANSPORTERS_KINDS:
                return (f"'{target}' ({p.kind.plain}) does not move solutes across the membrane; transport works on "
                        f"{', '.join(TRANSPORTERS_KINDS)}")
            return _transport_problem(p, options, params.gradients())
        if name == "diffuse":
            if target not in solutes:
                return f"diffuse acts on a solute of the scene (solutes:){did_you_mean(target, list(solutes))}"
            s = solutes[target]
            problem = tr.diffusion_problem(s.solute, membrane)
            if problem:
                return problem
            levels = solute_levels(s, membrane)
            if len(set(levels.values())) < 2:
                return f"{s.solute} has the same concentration on both sides ({next(iter(levels.values())):g} mM): no gradient, no net diffusion"
            return None
        if name == "osmosis":
            exo, cyto = membrane_sides(membrane)  # type: ignore[arg-type]
            sides = {cyto: {}, exo: {}}  # type: ignore[var-annotation]
            for s in params.solutes:
                for side, value in solute_levels(s, membrane).items():
                    sides[side][s.solute] = value
            if not any(s.solute != "water" for s in params.solutes):
                return "osmosis needs solutes that cannot cross the membrane, at different concentrations on its two sides (solutes:)"
            return tr.osmosis_problem(sides[cyto], sides[exo])
        if name == "action_potential":
            if membrane != "plasma_membrane":
                return "an action potential runs along a plasma membrane (membrane: plasma)"
            found = _ap_channels(list(placed.values()))
            if not found[0] or not found[1]:
                missing = " and ".join(n for n, f in (("Na⁺", found[0]), ("K⁺", found[1])) if not f)
                return (f"an action potential needs voltage-gated {missing} channels in the membrane "
                        f"({{kind: ion_channel, ion: Na+}} and {{kind: ion_channel, ion: K+}}; gating: voltage is the default)")
        return None

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """The molecules' states replayed in beat and ``at`` order: a channel must be open when
        ions pass it, an action potential starts from closed channels; ``set_state`` and the
        transport cycles change the states. With a gene: its steps in order."""
        if params.gene is not None:
            return cls.gene_sequence_problems(spec, params, uses)
        placed = {p.id: p for p in params.placed()}
        states = {k: (p.spec.state or (p.kind.states[0] if p.kind.states else None)) for k, p in placed.items()}  # type: ignore[union-attr]
        beats = [b.id for b in spec.beats]
        order = sorted(range(len(uses)), key=lambda i: (beats.index(uses[i].beat) if uses[i].beat in beats else 0,
                                                         uses[i].config.fraction, i))
        problems: list[tuple[str, str]] = []
        for i in order:
            use = uses[i]
            name = use.kind.name
            if name not in PROCESS_ACTIONS:
                continue
            target = use.config.targets()[0] if use.config.targets() else ""
            if name == "set_state" and target in states:
                states[target] = use.action.options.state
            elif name == "transport" and target in placed:
                p = placed[target]
                if p.item.kind == "ion_channel":
                    ion = use.action.options.ion or p.spec.ion or "K+"  # type: ignore[union-attr]
                    problem = tr.channel_problem(p.spec, ion, states[target] or "closed")  # type: ignore[arg-type]
                    if problem:
                        problems.append((f"{use.location}.target", f"'{target}': {problem}"))
                else:
                    states[target] = _end_state(p, states[target])
            elif name == "action_potential":
                na, k = _ap_channels(list(placed.values()))
                for p in na + k:
                    if states[p.id] != "closed":
                        problems.append((f"{use.location}.target", f"an action potential starts at rest: channel '{p.id}' is "
                                                                     f"{states[p.id]} at this point (its state must be closed)"))
                for p in na + k:
                    states[p.id] = "closed"
        return problems

    # ----- building -----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        if p.gene is not None:
            self.construct_gene()
            return
        self.membrane = membrane_name(p.membrane)
        self.placed = p.placed()
        self.gradients = p.gradients()
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.3)
        self.full_body = body
        colors = CellColors(self.theme.background, self.theme.color("text"))
        self.colors = colors
        self._ap_uses = [a for a in self.action_uses("action_potential")]
        self.has_osmosis = bool(self.action_uses("osmosis"))
        self.panel, body = self._panel(body)
        # room at the top for the captions of the process steps (two lines)
        self.caption_top = body.y1
        if self._processes():
            lines = 2 if self.frame_width >= self.frame_height else 3
            body = Region(body.x0, body.y0, body.x1, body.y1 - lines * (self.markup("Xg", size=chart_label_size(p.label_size)).height + 0.08) - 0.3)
        self.body = body
        bounds = self._bounds()
        span = p.width or self._fit_span(bounds)
        self.rows_y = [0.0]
        if p.labels:
            # room for each name under its molecule: lay out again with slots as wide as the names
            names = {pl.id: self.markup(self._name(pl), size=p.label_size).width + 0.25 for pl in self.placed if self._name(pl)}
            for _ in range(4):           # the names' room depends on the span it gives: until they agree
                unit = min(body.width, body.height) / span
                self.rows_y = _arrange(self.placed, self.membrane, {k: w / unit for k, w in names.items()}, body.width / body.height, 0.5 / unit)
                bounds = self._bounds()
                span = p.width or self._fit_span(bounds)
        else:
            self.rows_y = _arrange(self.placed, self.membrane, None, body.width / body.height)
            bounds = self._bounds()
            span = p.width or self._fit_span(bounds)
        self.span = span
        self.unit = min(body.width, body.height) / span                        # scene units per nm
        mid = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
        lift = 0.25 if p.labels else 0.0                        # room for the names under the molecules
        self.origin = np.array([body.center[0] - mid[0] * self.unit, body.center[1] + lift - mid[1] * self.unit, 0.0])
        self.px_width = 100.0 / (1080.0 / min(self.frame_width, self.frame_height))
        self._ref = self.markup("X", size=p.label_size, color="text").height
        self.specs: dict[str, MoleculeSpec] = {pl.id: pl.spec for pl in self.placed}  # type: ignore[misc]
        self.live: dict[str, Live] = {}
        self.groups: dict[str, VGroup] = {}
        self.rng = random.Random(f"{p.seed}:{self.spec.id}")
        labels = self._labels()
        self._names: list[Mobject] = []
        chain = ChainedTargets(self)
        base: list[Target] = []
        if title is not None:
            base.append(chain.add("title", title, lambda: [FadeIn(title)], []))
        if self.membrane is not None:
            membrane = VGroup(self._membrane(), *labels.get("membrane", []))
            self.charges = self._charges()
            membrane.add(self.charges)
            base.append(chain.add("membrane", membrane, lambda: [FadeIn(membrane)], list(base)))
        else:
            self.charges = VGroup()
        if p.scale_bar:
            bar = self._scale_bar()
            base.append(chain.add("scale_bar", bar, lambda: [FadeIn(bar)], list(base)))
        items = []
        molecules = []
        for placed in self.placed:
            drawing = self._molecule(placed)
            group = VGroup(drawing, *labels.get(placed.id, []))
            molecules.append(group)
            items.append(chain.add(placed.id, group, lambda g=group: [FadeIn(g)], list(base)))
        self._settle_side_names()
        # the particles of the solutes, the readouts beside them
        self.particles = VGroup().set_z_index(PARTICLE_Z)
        self.particle_mobs: dict[str, Mobject] = {}
        self.pools = self._pools()
        self.levels: dict[str, dict[str, float]] = {s.name: solute_levels(s, self.membrane) for s in p.solutes}
        fields = self._fields()
        self.readout = self._readout()
        self.bars = self._bars()
        for s in p.solutes:
            group = VGroup(*fields.get(s.name, []), *self.bars.get(s.name, VGroup()))
            items.append(chain.add(s.name, group, lambda g=group: [FadeIn(g)], list(base)))
        if self.readout is not None:
            base.append(chain.add("potential", self.readout, lambda: [FadeIn(self.readout)], list(base)))
        self.add(self.particles)
        self.notes_layer = VGroup().set_z_index(NOTE_Z)
        self.add(self.notes_layer)
        self.plot = self._ap_plot()
        if self.plot is not None:
            self.add(self.plot[0])
        chain.reveal(base, items, p.reveal == "all")
        self.finish()

    def _panel(self, body: Region) -> tuple[Region | None, Region]:
        """The room beside the molecules for an action potential's plot, the voltage readout and
        the concentrations (at the right of a wide body, under a tall one), and the body left."""
        p = self.params
        plot = any(u.options.plot for u in self._ap_uses)
        readout = p.potential is not None or bool(self._ap_uses)
        bars = p.bars and bool(p.solutes)
        if not (plot or readout or bars):
            return None, body
        wide = self.frame_width >= self.frame_height   # by the frame (a tall frame's body can be wider than tall)
        if wide:
            w = body.width * (0.36 if plot else 0.24 if bars else 0.2)
            return Region(body.x1 - w, body.y0, body.x1, body.y1), Region(body.x0, body.y0, body.x1 - w - 0.2, body.y1)
        line = self.markup("[X]", size=p.label_size).height + 0.14
        if plot:
            # a tall frame: the readout, the plot across the panel, the two sides' lists side by side
            lines = 1 + len(p.solutes)
            if bars and 2 * max(self.markup("Extracellular space", size=p.label_size).width,
                                self.markup("[Na⁺] 000 mM", size=p.label_size).width + 1.6) > body.width - 0.3:
                lines *= 2              # the two sides' lists one under the other (as _bars decides)
            lists = lines * line + 0.45 if bars else 0.0
            h = (0.75 if readout else 0.1) + self._tall_plot_height(body) + 0.3 + lists
            return Region(body.x0, body.y0, body.x1, body.y0 + h), Region(body.x0, body.y0 + h + 0.2, body.x1, body.y1)
        lists = (2 + 2 * len(p.solutes)) * line + (0.75 if readout else 0.1) + 0.2 if bars else 0.0
        h = max(body.height * 0.08, lists)
        return Region(body.x0, body.y0, body.x1, body.y0 + h), Region(body.x0, body.y0 + h + 0.2, body.x1, body.y1)

    @staticmethod
    def _tall_plot_height(body: Region) -> float:
        """The action-potential plot's height under a tall frame's molecules."""
        return min(body.height * 0.2, body.width * 0.5)

    def _bounds(self) -> tuple[float, float, float, float]:
        boxes = [p.bounds() for p in self.placed] or [(-10.0, -6.0, 10.0, 6.0)]
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        if self.membrane is not None:
            rows = getattr(self, "rows_y", [0.0])
            y0, y1 = min(y0, rows[-1] - BILAYER_NM), max(y1, BILAYER_NM)
            if self.params.solutes or self.has_osmosis or self._ap_uses:
                # room for particles on both sides
                y0, y1 = min(y0, rows[-1] - BILAYER_NM - 6.0), max(y1, BILAYER_NM + 6.0)
        pad = MARGIN * max(x1 - x0, y1 - y0) / 30.0             # a little room round the drawing, by its size
        return (x0 - pad, y0 - pad, x1 + pad, y1 + pad)

    def _fit_span(self, bounds: tuple[float, float, float, float]) -> float:
        """The span (nm across the body's shorter side) that fits ``bounds`` and the labels
        beside them (a column each side in a wide frame, rows above and below in a tall one)."""
        body = self.body
        short = min(body.width, body.height)
        w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
        texts = [self.markup(t, size=self.params.label_size) for t in self._label_texts()]
        # labels in a column at each side or in rows above and below: whichever leaves the
        # drawing larger (a long DNA in a wide frame takes rows)
        names = 0.5 if self.params.labels else 0.0             # the names under the molecules (screen units)
        widest = max((t.width for t in texts), default=0.0)
        room_x = body.width - 2 * (widest + 0.35) if texts else body.width * 0.92
        columns = max(w / (room_x / short), h / ((body.height * 0.92 - names) / short)) if room_x > body.width * 0.25 else math.inf
        count = math.ceil(sum(t.width + 0.2 for t in texts) / 2 / max(body.width - 0.2, 1.0)) if texts else 0
        tall = max((t.height for t in texts), default=0.0)
        room_y = max(body.height * 0.25, body.height - 2 * count * (tall + 0.14) - 0.9 - names) if texts else body.height * 0.92 - names
        rows = max(w / (body.width * 0.92 / short), h / (room_y / short))
        self.label_axis = 0 if columns <= rows else 1
        return min(columns, rows)

    def _label_texts(self) -> list[str]:
        """The texts of the part labels at the edges (none when no molecule names its parts)."""
        if not self._has_parts():
            return []
        texts = [p.glyph.anchors[name][0] for p in self.placed for name in self._parts(p)]
        if self.membrane is not None and self.params.sides:
            texts += [CELL_COMPARTMENTS[name].label for name in membrane_sides(self.membrane)]
        return texts

    def _has_parts(self) -> bool:
        return self.params.labels and any(self._parts(p) for p in self.placed)

    def _processes(self) -> bool:
        """Whether a process action (transport, diffusion…) plays in this scene."""
        return any(self.action_uses(name) for name in PROCESS_ACTIONS if name != "set_state")

    def to_scene(self, p: tuple[float, float]) -> np.ndarray:
        return self.origin + np.array([p[0] * self.unit, p[1] * self.unit, 0.0])

    def to_nm(self, q: np.ndarray) -> tuple[float, float]:
        return (float((q[0] - self.origin[0]) / self.unit), float((q[1] - self.origin[1]) / self.unit))

    def _text(self, markup: str, height: float) -> Mobject:
        mob = self.markup(markup, size=self.params.label_size, color="text")
        return mob.scale(height / self._ref) if self._ref > 0 else mob

    # ----- the membrane -----------------------------------------------------------------------

    def _x_range(self) -> tuple[float, float]:
        """The membrane's ends (nm): the body's edges and a little beyond."""
        return (self.body.x0 - self.origin[0]) / self.unit - 2.0, (self.body.x1 - self.origin[0]) / self.unit + 2.0

    def _membrane(self) -> VGroup:
        """The bilayer across the body (one strip per membrane row): head groups of both leaflets,
        their tails, gaps where membrane proteins span it; the two compartments named."""
        unit = self.unit
        left, right = self._x_range()
        if self.panel is not None and self.body.width < self.full_body.width - 0.1:
            right = (self.body.x1 - self.origin[0]) / unit
        colors = self.colors
        r = 0.36
        step = 0.8
        group = VGroup()
        for row, y in enumerate(self.rows_y):
            spans = [(b[0] + 0.4, b[2] - 0.4) for p in self.placed if p.kind.family == "membrane" and p.row == row for b in [self._membrane_span(p)]]
            head_pts, tail_lines = [], []
            x = left
            while x <= right:
                if not any(a <= x <= b for a, b in spans):
                    for sign in (1, -1):
                        head_pts.append((x, y + sign * (BILAYER_NM / 2 - r)))
                        tail_lines.append(((x - 0.12, y + sign * (BILAYER_NM / 2 - 2 * r)), (x - 0.12, y + sign * 0.15)))
                        tail_lines.append(((x + 0.12, y + sign * (BILAYER_NM / 2 - 2 * r)), (x + 0.12, y + sign * 0.15)))
                x += step
            band = Rectangle(width=(right - left) * unit, height=BILAYER_NM * unit, stroke_width=0, fill_color=colors.fill(LIPID_TAIL_HUE, 0.35),
                             fill_opacity=1.0).move_to(self.to_scene(((left + right) / 2, y)))
            tails = VGroup(*[Line(self.to_scene(a), self.to_scene(b), stroke_width=max(0.6 * self.px_width, 0.18 * unit * 100),
                                  color=colors.solid(LIPID_TAIL_HUE)) for a, b in tail_lines])
            heads = VGroup(*[Circle(radius=r * unit, stroke_width=0, fill_color=colors.solid(LIPID_HEAD_HUE), fill_opacity=1.0).move_to(self.to_scene(q))
                             for q in head_pts])
            group.add(band, tails, heads)
        group.set_z_index(-2)
        if len(self.rows_y) > 1:
            group.add(self._row_rules())
        if self.params.sides and not self._has_parts():
            for row in range(len(self.rows_y)):
                group.add(*self._side_names(row))
        return group

    def _row_rules(self) -> VGroup:
        """Dashed rules between membrane rows: each row is a strip of its own membrane."""
        out = VGroup()
        for k in range(len(self.rows_y) - 1):
            above = [p.bounds()[1] for p in self.placed if p.row == k] + [self.rows_y[k] - BILAYER_NM]
            below = [p.bounds()[3] for p in self.placed if p.row == k + 1] + [self.rows_y[k + 1] + BILAYER_NM]
            y = (min(above) - 0.35 / self.unit + max(below)) / 2
            a, b = self.to_scene((0.0, y)), self.to_scene((0.0, y))
            line = DashedLine([self.body.x0, a[1], 0.0], [self.body.x1, b[1], 0.0], stroke_width=1.2, color=self.theme.color("dim"),
                              dash_length=0.08)
            line.set_stroke(opacity=0.6)
            out.add(line)
        return out

    def _side_names(self, row: int) -> list[Mobject]:
        """The two compartments' names by a membrane row where no molecule is (else at the left,
        beyond the molecules and their names)."""
        body, unit = self.body, self.unit
        y_row = self.rows_y[row]
        free, room = self._free_x(row)
        x = float(self.to_scene((free, 0.0))[0])
        boxes = [p.bounds() for p in self.placed if p.row == row or (p.row is None and row in (0, len(self.rows_y) - 1))]
        out = []
        for name, sign in zip(membrane_sides(self.membrane), (1, -1)):  # type: ignore[arg-type]
            words = self.markup(CELL_COMPARTMENTS[name].label, size=self.params.label_size, color="dim")
            y = self.to_scene((0.0, y_row + sign * (BILAYER_NM / 2 + 0.6)))[1] + sign * words.height / 2
            x_at = x
            if boxes and (room * unit < words.width + 0.2 or (sign < 0 and self.params.labels)):
                # no free stretch of membrane wide enough: at the left, beyond the molecules
                # (and, below, their names)
                reach = max(b[3] for b in boxes) if sign > 0 else min(b[1] for b in boxes)
                names = words.height * 2 + 0.25 if sign < 0 and self.params.labels else 0.0
                y = self.to_scene((0.0, reach))[1] + sign * (words.height / 2 + 0.12 + names)
                x_at = body.x0 + words.width / 2 + 0.1
                y = max(y, body.y0 + (0.75 if self.params.scale_bar else 0.0) + words.height / 2)   # clear of the scale bar
            y = min(max(y, body.y0 + words.height), body.y1 - words.height)
            words.move_to([min(max(x_at, body.x0 + words.width / 2 + 0.1), body.x1 - words.width / 2 - 0.1), y, 0.0])
            taken = [m for m in getattr(self, "_side_mobs", []) + out + list(getattr(self, "_names", []))]
            if any(_overlap(words, m, 0.06) for m in taken):
                # the row above's cytosol name (rows close together): the other end of the row
                for x_try in (body.x1 - words.width / 2 - 0.1, body.x0 + words.width / 2 + 0.1):
                    words.move_to([x_try, y, 0.0])
                    if not any(_overlap(words, m, 0.06) for m in taken):
                        break
            out.append(words)
        self._side_mobs = getattr(self, "_side_mobs", []) + out
        return out

    def _settle_side_names(self) -> None:
        """A compartment's name that a molecule's name (made after it, possibly dropped a line)
        covers moves to a free end of its row, else a line further from the membrane."""
        body = self.body
        names = list(getattr(self, "_names", []))
        sides = list(getattr(self, "_side_mobs", []))
        for words in sides:
            if not any(_overlap(words, n, 0.04) for n in names):
                continue
            y = float(words.get_center()[1])
            others = [m for m in sides if m is not words] + names
            for x, dy in ((body.x1 - words.width / 2 - 0.1, 0.0), (body.x0 + words.width / 2 + 0.1, 0.0),
                          (float(words.get_center()[0]), -words.height - 0.06), (float(words.get_center()[0]), words.height + 0.06)):
                words.move_to([x, y + dy, 0.0])
                if not any(_overlap(words, m, 0.04) for m in others):
                    break

    def _membrane_span(self, p: Placed) -> tuple[float, float, float, float]:
        """A membrane protein's extent within the bilayer (where no lipids are drawn)."""
        x0, y0, x1, y1 = p.bounds()
        inner = [q for prim in p.glyph.prims if prim.fill and not prim.text for cv in prim.curves for q in cv if abs(q[1]) < BILAYER_NM / 2]
        if inner:
            xs = [p.point(q)[0] for q in inner]
            return (min(xs), -BILAYER_NM / 2, max(xs), BILAYER_NM / 2)
        return (x0, y0, x1, y1)

    def _charges(self) -> VGroup:
        """The membrane's charges where it is free of proteins: + outside and − inside at rest,
        the other way round when the membrane potential is positive (shown with a potential)."""
        self.charge_sets: dict[str, list[Mobject]] = {"rest": [], "reversed": []}
        if self.params.potential is None and not self._ap_uses:
            return VGroup()
        left, right = self._x_range()
        out = VGroup()
        h = 1.0 * self.unit
        for row, y in enumerate(self.rows_y):
            spans = [(b[0] - 0.8, b[2] + 0.8) for p in self.placed if p.row == row for b in [p.bounds()]]
            x = left + 2.5
            while x < right - 2.0:
                if not any(a <= x <= b for a, b in spans):
                    for key, outside, inside in (("rest", "+", "−"), ("reversed", "−", "+")):
                        for sign, mark in ((1, outside), (-1, inside)):
                            m = self._text(mark, h).move_to(self.to_scene((x, y + sign * (BILAYER_NM / 2 + 0.75))))
                            m.set_color("#D9534F" if mark == "+" else "#3F6FC0")
                            self.charge_sets[key].append(m)
                            out.add(m)
                x += 3.2
        self.show_charges(self.params.potential if self.params.potential is not None else tr.AP_REST)
        return out

    def show_charges(self, mv: float) -> None:
        """The charges' opacity for a membrane potential of ``mv``."""
        rest = min(1.0, max(0.0, -mv / 70.0))
        flipped = min(1.0, max(0.0, mv / 35.0))
        for key, value in (("rest", rest), ("reversed", flipped)):
            for m in self.charge_sets.get(key, []):
                m.set_opacity(value)

    # ----- molecules ---------------------------------------------------------------------------

    def _prims(self, placed: Placed, spec: MoleculeSpec) -> list[MoleculePrim]:
        return list(place_glyph(molecule_glyph(spec), placed.center, placed.angle))

    def _make(self, prims: Any) -> list[Mobject]:
        """One mobject per prim (in order), each at its prim's depth."""
        out = []
        for prim in prims:
            drawn = glyph_mobjects([prim], self.colors, self.unit, self.origin, self.px_width, self._text)
            mob = drawn[0] if len(drawn) else VMobject()
            mob.set_z_index(0.1 * prim.z)
            out.append(mob)
        return out

    def _molecule(self, placed: Placed) -> VGroup:
        prims = self._prims(placed, placed.spec)  # type: ignore[arg-type]
        mobs = self._make(prims)
        drawing = VGroup(*mobs)
        self.live[placed.id] = Live(prims, mobs)
        self.groups[placed.id] = drawing
        group = VGroup(drawing)
        if self.params.labels:
            name = self._name(placed)
            if name:
                group.add(self._name_label(placed, name))
        return group

    def _name(self, placed: Placed) -> str:
        item = placed.item
        if item.label is False:
            return ""
        if isinstance(item.label, str) and item.label:
            return str(item.label)
        species = item.species or self.params.species
        bits = []
        if item.gene:
            bits.append(gene_markup(item.gene, species, placed.where))
        if item.protein:
            bits.append(protein_markup(item.protein, species, placed.where, item.gene))
        if bits:
            return " / ".join(bits) if len(bits) > 1 else bits[0]
        if item.kind == "ion" and item.ion:
            return ""                                  # the ion's symbol already names it
        if item.kind == "carrier" and placed.spec is not None and placed.spec.transporter:
            return MOLECULE_TRANSPORTERS[placed.spec.transporter].label
        if item.kind == "h_atpase" and molecule_pump_type(self.membrane) == "v":
            return "V-ATPase"
        if item.kind == "ion_channel" and placed.spec is not None and placed.spec.ion:
            return f"{chem_markup(placed.spec.ion)} channel"          # which ion it passes: Na⁺ channel
        return placed.kind.label

    def _name_label(self, placed: Placed, name: str) -> Mobject:
        words = self.markup(name, size=self.params.label_size, color="text")
        x0, y0, x1, y1 = placed.bounds()
        below = self.to_scene(((x0 + x1) / 2, y0))
        words.move_to(below + DOWN * (words.height / 2 + 0.08))
        words.set_z_index(5)
        # a name that would overlap its left neighbour's (a narrow frame) drops a line
        def clashes() -> bool:
            return any(abs(o.get_center()[1] - words.get_center()[1]) < (o.height + words.height) / 2 + 0.02 and
                       abs(o.get_center()[0] - words.get_center()[0]) < (o.width + words.width) / 2 + 0.08 for o in self._names)

        for _ in range(3):
            if not clashes():
                break
            words.shift(DOWN * (words.height + 0.06))
        self._names.append(words)
        return words

    def _parts(self, placed: Placed) -> list[str]:
        wanted = placed.item.parts
        if wanted is None:
            # one molecule names its parts, unless a process will move things round it
            wanted = len(self.placed) == 1 and not self.params.solutes and not self._processes()
        if wanted is False:
            return []
        names = list(placed.glyph.anchors)
        if isinstance(wanted, list):
            for name in wanted:
                if name not in names:
                    raise VidgenError(f"{placed.where}: parts: '{name}' is not a part of it{did_you_mean(name, names)} (parts: {', '.join(names)})")
            return list(wanted)
        return names[:8]

    def _labels(self) -> dict[str, list[Mobject]]:
        """The part labels of every molecule that names its parts and, with them, the two
        compartments of the membrane, laid out together at the body's edges; by owner (a
        molecule's id, ``membrane``)."""
        if not self._has_parts():
            return {}
        wanted: list[tuple[str, np.ndarray, str]] = []
        for placed in self.placed:
            for name in self._parts(placed):
                text, point = placed.glyph.anchors[name]
                wanted.append((placed.id, self.to_scene(placed.point(point)), text))
        if self.membrane is not None and self.params.sides:
            free = self._free_x(0)[0]
            for name, sign in zip(membrane_sides(self.membrane), (1, -1)):
                wanted.append(("membrane", self.to_scene((free, sign * (BILAYER_NM / 2 + 1.5))), CELL_COMPARTMENTS[name].label))
        out: dict[str, list[Mobject]] = {}
        for owner, group in zip([w[0] for w in wanted], self._part_labels([(a, t) for _, a, t in wanted])):
            out.setdefault(owner, []).append(group)
        return out

    def _free_x(self, row: int = 0) -> tuple[float, float]:
        """The middle (nm) of the widest stretch by membrane row ``row`` clear of the molecules
        there, and its width."""
        y = self.rows_y[row] if hasattr(self, "rows_y") else 0.0
        spans = sorted((b[0], b[2]) for p in self.placed for b in [p.bounds()] if b[1] < y + BILAYER_NM * 1.5 and b[3] > y - BILAYER_NM * 1.5)
        left = (self.body.x0 - self.origin[0]) / self.unit
        right = (self.body.x1 - self.origin[0]) / self.unit
        gaps, x = [], left
        for a, b in spans:
            if a > x:
                gaps.append((x, a))
            x = max(x, b)
        if right > x:
            gaps.append((x, right))
        if not gaps:
            return left + 2.0, 0.0
        a, b = max(gaps, key=lambda g: g[1] - g[0])          # the widest free stretch: room for the names
        return (a + b) / 2, b - a

    def _part_labels(self, wanted: list[tuple[np.ndarray, str]]) -> list[Mobject]:
        """Labels on plates at the body's edges (columns in a wide frame, rows in a tall one),
        each with a leader line to its anchor; in the order given."""
        body = self.body
        made = []
        for anchor, text in wanted:
            words = self.markup(text, size=self.params.label_size, color="text")
            plate = RoundedRectangle(width=words.width + 0.16, height=words.height + 0.1, corner_radius=0.06, stroke_width=0,
                                     fill_color=self.theme.background, fill_opacity=PLATE_OPACITY)
            words.move_to(plate.get_center())
            made.append((anchor, VGroup(plate, words)))
        groups: dict[int, Mobject] = {}
        axis = getattr(self, "label_axis", 0 if body.width >= body.height else 1)
        wide = axis == 0
        middle = body.center[axis]
        sides: dict[int, list[tuple[np.ndarray, VGroup]]] = {s: [m for m in made if (m[0][axis] >= middle) == (s > 0)] for s in (-1, 1)}
        while abs(len(sides[1]) - len(sides[-1])) > 1:     # balance the sides: the labels nearest the middle cross
            full = 1 if len(sides[1]) > len(sides[-1]) else -1
            mover = min(sides[full], key=lambda m: abs(float(m[0][axis]) - middle))
            sides[full] = [m for m in sides[full] if m is not mover]
            sides[-full].append(mover)
        for side in (-1, 1):
            mine = sides[side]
            if not mine:
                continue
            if wide:
                ys = _spread([float(a[1]) for a, _ in mine], [float(b.height) for _, b in mine], 0.08, body.y0 + 0.75, body.y1 - 0.05)
                for (a, box), y in zip(mine, ys):
                    x = body.x0 + 0.1 + box.width / 2 if side < 0 else body.x1 - 0.1 - box.width / 2
                    box.move_to([x, y, 0.0])
            else:
                rows: list[list[tuple[np.ndarray, VGroup]]] = [[]]
                for a, box in sorted(mine, key=lambda m: float(m[0][0])):
                    if sum(b.width + 0.14 for _, b in rows[-1]) + box.width > body.width - 0.2:
                        rows.append([])
                    rows[-1].append((a, box))
                tall = max(float(b.height) for _, b in mine)
                for k, row in enumerate(rows):
                    y = body.y1 - 0.08 - tall / 2 - k * (tall + 0.1) if side > 0 else body.y0 + 0.75 + tall / 2 + k * (tall + 0.1)
                    xs = _spread([float(a[0]) for a, _ in row], [float(b.width) for _, b in row], 0.14, body.x0 + 0.05, body.x1 - 0.05)
                    for (a, box), x in zip(row, xs):
                        box.move_to([x, y, 0.0])
            for a, box in mine:
                c = box.get_center()
                half = np.array([box.width / 2, box.height / 2, 0.0])
                end = np.clip(a, c - half, c + half)
                leader = Line(a, end, stroke_width=LEADER_WIDTH, color=self.theme.color("dim"))
                group = VGroup(leader, box)
                group.set_z_index(6)
                groups[id(box)] = group
        return [groups[id(box)] for _, box in made]

    def _scale_bar(self) -> VGroup:
        length_um, text = cell_scale_bar(self.span / 1000.0)
        width = length_um * 1000.0 * self.unit
        corner = np.array([self.body.x0 + 0.15, self.body.y0 + 0.15, 0.0])
        bar = Rectangle(width=width, height=0.07, stroke_width=0, fill_color=self.theme.color("text"), fill_opacity=1.0)
        bar.move_to(corner + np.array([width / 2, 0.035, 0.0]))
        words = self.markup(text, size=self.params.label_size, color="text")
        words.next_to(bar, UP, buff=0.08, aligned_edge=LEFT)
        group = VGroup(bar, words)
        group.set_z_index(7)
        self.bar_box = (float(group.get_left()[0]), float(group.get_bottom()[1]), float(group.get_right()[0]), float(group.get_top()[1]))
        return group

    # ----- solutes: particles and readouts ----------------------------------------------------------

    def _side_boxes(self, row: int) -> dict[str, tuple[float, float, float, float]]:
        """Where a membrane row's free particles may be (nm): its exoplasmic side ``p`` above it
        and its cytosolic side ``n`` below, each up to the next row's rule or the body's edge;
        without a membrane the ``left`` and ``right`` halves."""
        body = self.body
        x0 = (body.x0 - self.origin[0]) / self.unit + 0.8
        x1 = (body.x1 - self.origin[0]) / self.unit - 0.8
        top = (body.y1 - self.origin[1]) / self.unit - 0.8
        bottom = (body.y0 + (0.8 if self.params.scale_bar else 0.1) - self.origin[1]) / self.unit
        if self.membrane is None:
            return {"left": (x0, bottom, -0.8, top), "right": (0.8, bottom, x1, top)}
        y = self.rows_y[row]
        upper = top if row == 0 else (self.rows_y[row - 1] + y) / 2 - 0.5
        lower = bottom if row == len(self.rows_y) - 1 else (self.rows_y[row + 1] + y) / 2 + 0.5
        reach = BILAYER_NM / 2 + 1.0
        return {"p": (x0, y + reach, x1, upper), "n": (x0, lower, x1, y - reach)}

    def _avoid(self) -> list[tuple[float, float, float, float]]:
        """Boxes (nm) particles keep off: the molecules, their names and the labels."""
        out = [(b[0] - 0.5, b[1] - 0.5, b[2] + 0.5, b[3] + 0.5) for p in self.placed for b in [p.bounds()]]
        for m in list(getattr(self, "_names", [])) + list(getattr(self, "_side_mobs", [])):
            a, b = self.to_nm(m.get_corner(DL)), self.to_nm(m.get_corner(UR))
            out.append((a[0] - 0.3, a[1] - 0.3, b[0] + 0.3, b[1] + 0.3))
        if hasattr(self, "bar_box"):
            a, b = self.to_nm(np.array(self.bar_box[:2] + (0.0,))), self.to_nm(np.array(self.bar_box[2:] + (0.0,)))
            out.append((a[0] - 0.5, a[1] - 0.5, b[0] + 0.5, b[1] + 0.5))
        return out

    def _side_key(self, compartment: str) -> str:
        if self.membrane is None:
            return compartment
        exo, _ = membrane_sides(self.membrane)
        return "p" if compartment == exo else "n"

    def _pools(self) -> list[Any]:
        return [tr.Pool({}, self._side_boxes(row)) for row in range(len(self.rows_y))]

    def _particle(self, species: str, at: tuple[float, float], pid: str, shown: bool = True, layer: bool = True) -> Mobject:
        """A particle's mobject (a small molecule's or an ion's symbol) at ``at`` (nm), in the
        particles' layer (``layer``; a solute's own particles belong to its target instead)."""
        if species in MOLECULE_ION_RADII:
            prims = molecule_small_prims("ion", at, species)
        else:
            prims = molecule_small_prims(species, at)
        mob = glyph_mobjects(prims, self.colors, self.unit, self.origin, self.px_width, self._text)
        mob.set_z_index(PARTICLE_Z)
        if not shown:
            for m in mob.get_family():
                if isinstance(m, VMobject):
                    m.set_fill(opacity=0.0, family=False)
                    m.set_stroke(opacity=0.0, family=False)
        if layer:
            self.particles.add(mob)
        self.particle_mobs[pid] = mob
        return mob

    def _fields(self) -> dict[str, list[Mobject]]:
        """The solutes' particles on each side of each membrane row (or each half of a
        solution), in proportion to their concentrations; a water field for osmosis."""
        p = self.params
        avoid = self._avoid()
        out: dict[str, list[Mobject]] = {}
        solutes = list(p.solutes)
        if self.has_osmosis and not any(s.solute == "water" for s in solutes):
            solutes.append(Solute(solute="water", count=14))
        taken: dict[int, list[tuple[float, float]]] = {}
        for s in solutes:
            levels = solute_levels(s, self.membrane)
            high = max(levels.values()) if levels else 0.0
            rng = random.Random(f"{p.seed}:{self.spec.id}:{s.name}")
            for row, pool in enumerate(self.pools):
                for compartment, value in levels.items():
                    side = self._side_key(compartment)
                    share = value / high if high > 0 else 0.0
                    count = 0 if share < 0.01 else max(1, round(s.count * share))
                    box = pool.boxes[side]
                    if box[2] <= box[0] or box[3] <= box[1]:
                        continue
                    gap = 1.1 if s.solute != "water" else 0.8
                    spots = tr.scatter(rng, box, count, gap, avoid, taken.get(row, []))
                    taken.setdefault(row, []).extend(spots)
                    for k, q in enumerate(spots):
                        pid = f"{s.name}.{row}.{side}.{k}"
                        mob = self._particle(s.solute, q, pid, layer=s not in p.solutes)
                        pool.give(s.solute, side, pid, q)
                        out.setdefault(s.name, []).append(mob)
        return out

    def _readout(self) -> VGroup | None:
        """The membrane potential written out (Vm = −70 mV) at the panel's top."""
        if self.panel is None or (self.params.potential is None and not self._ap_uses):
            return None
        digits = Digits(self, "V<sub>m</sub> =", "mV", 2, self.params.label_size)
        panel = self.panel
        digits.place(np.array([panel.x0 + 0.15, panel.y1 - 0.25, 0.0]))
        plate = RoundedRectangle(width=digits.width() + 0.25, height=digits.head.height + 0.22, corner_radius=0.06, stroke_width=0,
                                 fill_color=self.theme.background, fill_opacity=PLATE_OPACITY)
        plate.move_to([panel.x0 + 0.15 + digits.width() / 2, panel.y1 - 0.25, 0.0])
        self.digits = digits
        digits.show(self.params.potential if self.params.potential is not None else tr.AP_REST)
        group = VGroup(plate, digits.group).set_z_index(NOTE_Z)
        return group

    def _bars(self) -> dict[str, VGroup]:
        """Each solute's concentration on each side: a bar (as long as its share of the larger)
        and its value, grouped by side in the panel."""
        p = self.params
        self.bar_items: dict[tuple[str, str], tuple[Rectangle, Mobject, float]] = {}
        if self.panel is None or not (p.bars and p.solutes):
            return {}
        panel = self.panel
        sides = list(membrane_sides(self.membrane)) if self.membrane else ["left", "right"]
        size = p.label_size
        out: dict[str, VGroup] = {}
        heads = [self.markup(CELL_COMPARTMENTS[s].label if s in CELL_COMPARTMENTS else s.capitalize(), size=size, color="dim") for s in sides]
        names = {s.name: self.markup(f"[{chem_markup(s.solute) if s.solute in MOLECULE_ION_RADII else MOLECULE_KINDS[s.solute].label}]",
                                     size=size, color="text") for s in p.solutes}
        name_w = max(m.width for m in names.values())
        line_h = max(m.height for m in names.values()) + 0.12
        plot = any(u.options.plot for u in self._ap_uses)
        column = self.frame_width >= self.frame_height        # the panel is a column at the right
        top = panel.y1 - (0.75 if self.readout is not None else 0.1)
        if plot and column:
            top -= self._plot_height() + 0.35
        elif plot:
            top -= self._tall_plot_height(self.full_body) + 0.3
        value_w = max(self.markup("000 mM", size=size).width, 0.9)
        # two columns side by side under a tall frame's molecules when both sides' lists fit
        single = column or 2 * max(max(h.width for h in heads), name_w + value_w + 1.4) > panel.width - 0.3
        room = panel.width if single else panel.width * 0.5
        bar_w = max(0.5, min(1.6, room - name_w - value_w - 0.6))
        self.bar_full = bar_w
        columns = [(panel.x0 + 0.15, top)] if single else [(panel.x0 + 0.15, top), (panel.center[0] + 0.1, top)]
        y = top
        x = columns[0][0]
        for k, side in enumerate(sides):
            if not single:
                x, y = columns[k]
            head = heads[k].move_to([x + heads[k].width / 2, y - heads[k].height / 2, 0.0])
            y -= heads[k].height + 0.1
            for s in p.solutes:
                levels = self.levels[s.name]
                value = levels.get(side, 0.0)
                high = max(levels.values()) or 1.0
                label = names[s.name].copy().move_to([x + name_w - names[s.name].width / 2, y - line_h / 2, 0.0])
                rect = Rectangle(width=max(bar_w * value / high, 0.02), height=0.14, stroke_width=0, fill_color=self._solute_hue(s.solute), fill_opacity=0.9)
                rect.move_to([x + name_w + 0.12 + rect.width / 2, y - line_h / 2, 0.0])
                text = self.markup(_concentration(value), size=size, color="text")
                text.move_to([x + name_w + 0.24 + bar_w + text.width / 2, y - line_h / 2, 0.0])
                self.bar_items[(s.name, side)] = (rect, text, high)
                out.setdefault(s.name, VGroup()).add(label, rect, text)
                y -= line_h
            out.setdefault(p.solutes[0].name, VGroup()).add(head)
            y -= 0.15
        for g in out.values():
            g.set_z_index(NOTE_Z)
        return out

    def _solute_hue(self, solute: str) -> str:
        return self.colors.solid(MOLECULE_ION_HUES.get(solute, MOLECULE_KINDS[solute].hue if solute in MOLECULE_KINDS else "#888888"))

    def _plot_height(self) -> float:
        """The inset plot's height in a panel at the right: half the panel, less when the
        concentration bars need the room under it."""
        p = self.params
        lists = 0.0
        if p.bars and p.solutes:
            line = self.markup("[X]", size=p.label_size).height + 0.12
            lists = (2 + 2 * len(p.solutes)) * line + 0.6
        return max(self.panel.height * 0.3, min(self.panel.height * 0.5, self.panel.height - 0.75 - lists - 0.35))  # type: ignore[union-attr]

    def _ap_plot(self) -> tuple[VGroup, Any, VMobject, Dot] | None:
        """The inset plot of the membrane potential (mV against ms) an action potential traces."""
        if self.panel is None or not any(u.options.plot for u in self._ap_uses):
            return None
        panel = self.panel
        wide = self.frame_width >= self.frame_height
        if wide:
            area = Region(panel.x0 + 0.1, panel.y1 - 0.75 - self._plot_height(), panel.x1 - 0.1, panel.y1 - 0.75)
        else:
            top = panel.y1 - (0.75 if self.readout is not None else 0.1)
            area = Region(panel.x0 + 0.1, top - self._tall_plot_height(self.full_body), panel.x1 - 0.1, top)
        axes = _ApAxes(self, area)
        trace = tr.ap_trace(181)
        points = [axes.point(t, v) for t, v in trace]
        full = VMobject().set_points_as_corners(points)
        full.set_stroke(self.theme.color("accent"), width=4)
        live = full.copy()
        live.pointwise_become_partial(full, 0.0, 0.0)
        dot = Dot(axes.point(0.0, tr.AP_REST), radius=0.06, color=self.theme.color("accent"))
        group = VGroup(axes.group, live, dot).set_z_index(NOTE_Z)
        self.ap_full = full
        return group, axes, live, dot

def _overlap(a: Mobject, b: Mobject, pad: float = 0.0) -> bool:
    """Whether two mobjects' boxes overlap (``pad`` apart at least otherwise)."""
    return bool(abs(a.get_center()[0] - b.get_center()[0]) < (a.width + b.width) / 2 + pad and
                abs(a.get_center()[1] - b.get_center()[1]) < (a.height + b.height) / 2 + pad)


def _transport_problem(p: Placed, options: Any, gradients: Any) -> str | None:
    """Why ``transport`` cannot run on ``p`` as written (whatever its state then)."""
    kind = p.item.kind
    spec = p.spec
    if kind in ("ion_channel", "aquaporin"):
        if options.cycles != 1:
            return f"cycles is for carriers and pumps; a {p.kind.plain} passes count ions or molecules"
    elif options.ion is not None or options.direction is not None:
        return f"ion and direction are for channels and aquaporins; a {p.kind.plain} moves its solutes its own way"
    if kind == "ion_channel":
        own = spec.ion or "K+"  # type: ignore[union-attr]
        ion = options.ion or own
        if ion not in MOLECULE_ION_RADII:
            return f"ion '{ion}': use {', '.join(MOLECULE_ION_RADII)}{did_you_mean(ion, list(MOLECULE_ION_RADII))}"
        if ion != own:
            return tr.channel_problem(spec, ion, "open")
        way = gradients.passive_way(ion)
        if options.direction is not None and way is not None and options.direction != way:
            return (f"{chem_plain(ion)} flows {way} through an open channel here ({gradients.describe(ion)}): ions in a channel only move "
                    f"down their electrochemical gradient; moving them {options.direction} needs an energy source: ATP or an ion gradient")
        return None
    if kind == "aquaporin":
        return None
    if kind == "carrier":
        return tr.carrier_problem(spec, gradients)
    return None


class _ApAxes:
    """The axes of an action potential's inset plot in ``area``: membrane potential (−90 to
    +50 mV, ticks every 40 from −80) against time (0–6 ms) along the bottom, 0 mV and the
    threshold (−55 mV) as faint dashed lines."""

    Y_RANGE, Y_TICKS = (-90.0, 50.0), (-80.0, -40.0, 0.0, 40.0)

    def __init__(self, scene: NarratedScene, area: Region) -> None:
        dim = scene.theme.color("dim")
        label = lambda s: scene.text(s, size="caption", color="dim")  # noqa: E731
        values = self.Y_TICKS if area.height > 2.2 else (-80.0, 0.0)        # a short plot: fewer ticks
        ticks = {v: label(f"{v:+.0f}".replace("-", "−").replace("+0", "0")) for v in values}
        left = area.x0 + max(t.width for t in ticks.values()) + 0.15
        bottom = area.y0 + ticks[0.0].height + 0.2
        self.plot = Region(left, bottom, area.x1 - 0.2 - label("ms").width - 0.3, area.y1 - 0.35)
        lo, hi = self.Y_RANGE
        x_axis = Line([left, bottom, 0.0], [self.plot.x1 + 0.2, bottom, 0.0], color=dim, stroke_width=2)
        y_axis = Line([left, bottom, 0.0], [left, self.plot.y1 + 0.2, 0.0], color=dim, stroke_width=2)
        parts: list[Mobject] = [x_axis, y_axis]
        for v, t in ticks.items():
            y = self.point(0.0, v)[1]
            parts += [Line([left - 0.06, y, 0.0], [left + 0.06, y, 0.0], color=dim, stroke_width=2), t.move_to([left - 0.12 - t.width / 2, y, 0.0])]
        for ms in range(0, int(tr.AP_DURATION) + 1, 2):
            x = self.point(float(ms), lo)[0]
            t = label(str(ms))
            parts += [Line([x, bottom - 0.06, 0.0], [x, bottom + 0.06, 0.0], color=dim, stroke_width=2), t.move_to([x, bottom - 0.12 - t.height / 2, 0.0])]
        for v, words in ((0.0, None), (tr.AP_THRESHOLD, "threshold")):
            a, b = self.point(0.0, v), self.point(tr.AP_DURATION, v)
            line = DashedLine(a, b, stroke_width=1.4, color=dim, dash_length=0.06)
            line.set_stroke(opacity=0.7)
            parts.append(line)
            if words:
                text = label(words).scale(0.8)
                parts.append(text.move_to([b[0] - text.width / 2, b[1] + text.height / 2 + 0.04, 0.0]))
        units_y = scene.markup("mV", size="caption", color="dim")
        units_x = label("ms")
        parts += [units_y.move_to([left + 0.12 + units_y.width / 2, self.plot.y1 + 0.2, 0.0]),
                  units_x.move_to([self.plot.x1 + 0.3 + units_x.width / 2, bottom, 0.0])]
        self.group = VGroup(*parts)

    def point(self, ms: float, mv: float) -> np.ndarray:
        lo, hi = self.Y_RANGE
        return np.array([self.plot.x0 + ms / tr.AP_DURATION * self.plot.width, self.plot.y0 + (mv - lo) / (hi - lo) * self.plot.height, 0.0])


__all__ = ["Molecule", "MoleculeItem", "Solute", "layout", "membrane_name"]
