"""``molecule``: a molecular close-up in physical scale (DESIGN.md §95.9): molecules drawn from
the shared catalog and glyphs of ``vidgen.cellworld`` (DNA, RNAs, nucleosomes and chromatin,
proteins, receptors, channels, carriers, pumps, ATP synthase, G proteins, small molecules and
ions) in a solution or a membrane (a lipid bilayer between its two compartments), with
correctly typeset names (gene symbols italic, protein names roman, charges as superscripts),
modification markers, labels of their parts and a scale bar in nm. Every placement and
orientation is checked: a GPCR's N-terminus is extracellular, ATP synthase's F₁ faces the
matrix (stroma, cytoplasm), the Na⁺/K⁺ pump is in an animal cell's plasma membrane."""

import math
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .cell import PLATE_OPACITY, _spread
from .math_axes import ChainedTargets

Length = float | str

#: Short names of membranes (``plasma`` for ``plasma_membrane``…).
MEMBRANE_ALIASES = {"plasma": "plasma_membrane", "inner_mitochondrial": "inner_mitochondrial_membrane", "thylakoid": "thylakoid_membrane",
                    "er": "er_membrane", "bacterial": "bacterial_inner_membrane", "endosomal": "endosomal_membrane",
                    "lysosomal": "lysosomal_membrane", "golgi": "golgi_membrane", "outer_mitochondrial": "outer_mitochondrial_membrane"}
#: Membranes only one kind of cell has.
MEMBRANE_CELLS = {"thylakoid_membrane": "plant", "outer_envelope_membrane": "plant", "inner_envelope_membrane": "plant", "tonoplast": "plant",
                  "bacterial_inner_membrane": "bacterium", "bacterial_outer_membrane": "bacterium"}
#: Gaps between molecules laid out automatically, and the room round the drawing (nm).
GAP, GAP_SMALL, MARGIN = 3.0, 1.2, 2.5
LEADER_WIDTH = 1.6


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
    """dna, mrna, trna, rrna, nucleosome, chromatin, protein, kinase, phosphatase, g_protein, gpcr, rtk, ion_channel, carrier, na_k_atpase, atp_synthase, atp, adp, pi, gtp, gdp, camp, glucose, ligand, ion."""
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
    """gpcr / g_protein: inactive or active; rtk: monomer or dimer; ion_channel: closed or open; carrier: outward or inward; na_k_atpase: e1 or e2; atp_synthase: synthesis or hydrolysis; kinase: active or inactive; chromatin: 10nm or compact."""
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
    substrates: list[str] = Field(default_factory=list)
    """carrier: its solutes (Na+, glucose, H+, Ca2+…)."""
    moves: list[Literal["in", "out"]] = Field(default_factory=list)
    """carrier: the way each solute moves (in: into the cytosol)."""
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
                            tuple((m.mark, m.at, m.domain) for m in self.modifications), membrane, where)


class Placed:
    """A molecule of the scene placed (nm): its id, item, kind, glyph, centre and angle."""

    def __init__(self, entry_id: str, item: MoleculeItem, glyph: MoleculeGlyph, center: tuple[float, float], angle: float, where: str) -> None:
        self.id, self.item, self.glyph, self.center, self.angle, self.where = entry_id, item, glyph, center, angle, where
        self.kind = MOLECULE_KINDS[item.kind]

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
        if entry_id in ids or entry_id in ("title", "membrane", "scale_bar"):
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
        placed.append(Placed(entry_id, item, glyph, (0.0, 0.0), angle, where))
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
             names: float = 0.0) -> None:
    """Centres: written ``at`` as given; the rest in rows by lane — in the membrane, then the
    cytosolic and the exoplasmic side — each row centred, molecules ``GAP`` apart, each taking
    at least its ``slots`` width (nm: room for its name under it), rows ``names`` nm further
    apart for the names."""
    exo = membrane_sides(membrane)[0] if membrane else None
    lanes: dict[str, list[Placed]] = {"membrane": [], "below": [], "above": []}
    for p in placed:
        if p.item.at is not None:
            at = p.item.at
            p.center = (float(at), 0.0) if not isinstance(at, tuple) else at
            if p.kind.bound and isinstance(at, tuple):
                raise VidgenError(f"{p.where}: a membrane protein's at is one number, x along the membrane (nm)")
            continue
        lane = "membrane" if p.kind.bound else ("above" if membrane and p.item.inside == exo else "below")
        lanes[lane].append(p)
    widths = {id(p): max(p.glyph.bounds[2] - p.glyph.bounds[0], (slots or {}).get(p.id, 0.0)) for p in placed}
    bottom = min((p.glyph.bounds[1] for p in lanes["membrane"]), default=-BILAYER_NM / 2)
    top = max((p.glyph.bounds[3] for p in lanes["membrane"]), default=BILAYER_NM / 2)
    def gap(a: Placed, b: Placed) -> float:
        return GAP_SMALL if a.kind.family == "small" and b.kind.family == "small" else GAP

    for lane, everything in lanes.items():
        # soluble molecules wrap into rows when one row would be much wider than the frame
        rows = [everything] if lane == "membrane" else _rows(everything, widths, aspect, gap)
        level = 0.0
        for row in rows:
            gaps = [gap(a, b) for a, b in zip(row, row[1:])] + [0.0]
            total = sum(widths[id(p)] for p in row) + sum(gaps)
            tall = max((p.glyph.bounds[3] - p.glyph.bounds[1] for p in row), default=0.0)
            x = -total / 2
            for p, after in zip(row, gaps):
                x0, y0, x1, y1 = p.glyph.bounds
                if lane == "membrane":
                    y = 0.0
                elif membrane is None:
                    y = -(y0 + y1) / 2 - level
                elif lane == "below":
                    y = min(bottom, -BILAYER_NM / 2) - GAP - y1 - level
                else:
                    y = max(top, BILAYER_NM / 2) + GAP - y0 + level
                p.center = (x + (widths[id(p)] - (x1 - x0)) / 2 - x0, y)
                x += widths[id(p)] + after
            level += tall + GAP + names


def _rows(row: list[Placed], widths: dict[int, float], aspect: float, gap: Any) -> list[list[Placed]]:
    """``row`` cut into the number of rows that frames them largest in a body of ``aspect``."""
    if len(row) < 2:
        return [row]
    total = sum(widths[id(p)] for p in row) + sum(gap(a, b) for a, b in zip(row, row[1:]))
    tall = max(p.glyph.bounds[3] - p.glyph.bounds[1] for p in row) + GAP
    best = min(range(1, len(row) + 1), key=lambda n: max(total / n / aspect, n * tall))
    size = math.ceil(len(row) / best)
    return [row[k:k + size] for k in range(0, len(row), size)]


@scene("molecule")
class Molecule(NarratedScene):
    """A molecular close-up in nm: molecules in a solution or a membrane (the lipid bilayer
    with its two compartments named), each drawn to its textbook size — the DNA double helix
    with its 5′/3′ ends, base pairs and grooves; mRNA, tRNA, rRNA; a nucleosome, chromatin;
    proteins with domains; GPCRs, RTKs, gated channels, carriers, the Na⁺/K⁺ pump, ATP synthase;
    G proteins, kinases; ATP, GTP, cAMP, Pᵢ, glucose, ions — with gene symbols in italics,
    protein names in roman type, charges as superscripts, modification markers (P, Ub, Ac,
    Me), labels of their parts and a scale bar. Orientations and places are checked.

    Action targets: ``title``, ``membrane``, ``scale_bar`` and each molecule's id."""

    outro = 0.5
    target_patterns = ("title", "membrane", "scale_bar", "<id>")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        membrane: str = "none"
        """none (a solution) or the membrane across the view: plasma, inner_mitochondrial, thylakoid, er, bacterial, endosomal, lysosomal, golgi, outer_mitochondrial (or a full name: plasma_membrane…)."""
        compartment: str = "cytosol"
        """Without a membrane: the compartment the molecules are in (cytosol, nucleoplasm, matrix…), checked for each."""
        cell: Literal["animal", "plant", "bacterium"] = "animal"
        """The kind of cell (checked: no Na⁺/K⁺ pump in a plant, no nucleosomes in a bacterium); a thylakoid or bacterial membrane sets it."""
        species: str = "human"
        """Nomenclature for gene and protein names: human, mouse, rat, yeast, fission_yeast, fly, zebrafish, e_coli, arabidopsis."""
        molecules: list[MoleculeItem] = Field(default_factory=list, max_length=40)
        """The molecules: a kind, or {kind, id, at, state, label, gene, protein, parts, ...}."""
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
        title_size: ThemeSize = "heading"
        """Title size."""
        label_size: ThemeSize = "caption"
        """Size of the labels and the scale bar's text."""

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
                self.placed()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        names = (["title"] if params.title else []) + (["membrane"] if membrane_name(params.membrane) else [])
        return names + [p.id for p in params.placed()] + (["scale_bar"] if params.scale_bar else [])

    # ----- building -----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self.membrane = membrane_name(p.membrane)
        self.placed = p.placed()
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.3)
        self.body = body
        colors = CellColors(self.theme.background, self.theme.color("text"))
        self.colors = colors
        bounds = self._bounds()
        span = p.width or self._fit_span(bounds)
        if p.labels:
            # room for each name under its molecule: lay out again with slots as wide as the names
            names = {pl.id: self.markup(self._name(pl), size=p.label_size).width + 0.25 for pl in self.placed if self._name(pl)}
            for _ in range(2):
                unit = min(body.width, body.height) / span
                _arrange(self.placed, self.membrane, {k: w / unit for k, w in names.items()}, body.width / body.height, 0.5 / unit)
                bounds = self._bounds()
                span = p.width or self._fit_span(bounds)
        self.span = span
        self.unit = min(body.width, body.height) / span                        # scene units per nm
        mid = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
        lift = 0.25 if p.labels else 0.0                        # room for the names under the molecules
        self.origin = np.array([body.center[0] - mid[0] * self.unit, body.center[1] + lift - mid[1] * self.unit, 0.0])
        self.px_width = 100.0 / (1080.0 / min(self.frame_width, self.frame_height))
        self._ref = self.markup("X", size=p.label_size, color="text").height
        labels = self._labels()
        self._names: list[Mobject] = []
        chain = ChainedTargets(self)
        base: list[Target] = []
        if title is not None:
            base.append(chain.add("title", title, lambda: [FadeIn(title)], []))
        if self.membrane is not None:
            membrane = VGroup(self._membrane(), *labels.get("membrane", []))
            base.append(chain.add("membrane", membrane, lambda: [FadeIn(membrane)], list(base)))
        if p.scale_bar:
            bar = self._scale_bar()
            base.append(chain.add("scale_bar", bar, lambda: [FadeIn(bar)], list(base)))
        items = []
        for placed in self.placed:
            group = VGroup(self._molecule(placed), *labels.get(placed.id, []))
            items.append(chain.add(placed.id, group, lambda g=group: [FadeIn(g)], list(base)))
        chain.reveal(base, items, p.reveal == "all")
        self.finish()

    def _bounds(self) -> tuple[float, float, float, float]:
        boxes = [p.bounds() for p in self.placed] or [(-10.0, -6.0, 10.0, 6.0)]
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        if self.membrane is not None:
            y0, y1 = min(y0, -BILAYER_NM), max(y1, BILAYER_NM)
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

    def to_scene(self, p: tuple[float, float]) -> np.ndarray:
        return self.origin + np.array([p[0] * self.unit, p[1] * self.unit, 0.0])

    def _text(self, markup: str, height: float) -> Mobject:
        mob = self.markup(markup, size=self.params.label_size, color="text")
        return mob.scale(height / self._ref) if self._ref > 0 else mob

    # ----- the membrane -----------------------------------------------------------------------

    def _membrane(self) -> VGroup:
        """The bilayer across the body: head groups of both leaflets, their tails, gaps where
        membrane proteins span it; the two compartments named at the left."""
        body, unit = self.body, self.unit
        left = (body.x0 - self.origin[0]) / unit - 2.0
        right = (body.x1 - self.origin[0]) / unit + 2.0
        spans = [(b[0] + 0.4, b[2] - 0.4) for p in self.placed if p.kind.family == "membrane" for b in [self._membrane_span(p)]]
        heads, tails = VGroup(), VGroup()
        colors = self.colors
        x = left
        step = 0.8
        r = 0.36
        head_pts = []
        tail_lines = []
        while x <= right:
            if not any(a <= x <= b for a, b in spans):
                for sign in (1, -1):
                    head_pts.append((x, sign * (BILAYER_NM / 2 - r)))
                    tail_lines.append(((x - 0.12, sign * (BILAYER_NM / 2 - 2 * r)), (x - 0.12, sign * 0.15)))
                    tail_lines.append(((x + 0.12, sign * (BILAYER_NM / 2 - 2 * r)), (x + 0.12, sign * 0.15)))
            x += step
        band = Rectangle(width=(right - left) * unit, height=BILAYER_NM * unit, stroke_width=0, fill_color=colors.fill(LIPID_TAIL_HUE, 0.35),
                         fill_opacity=1.0).move_to(self.to_scene(((left + right) / 2, 0.0)))
        for a, b in tail_lines:
            tails.add(Line(self.to_scene(a), self.to_scene(b), stroke_width=max(0.6 * self.px_width, 0.18 * unit * 100), color=colors.solid(LIPID_TAIL_HUE)))
        dots = VGroup(*[Circle(radius=r * unit, stroke_width=0, fill_color=colors.solid(LIPID_HEAD_HUE), fill_opacity=1.0).move_to(self.to_scene(q))
                        for q in head_pts])
        heads.add(dots)
        group = VGroup(band, tails, heads)
        group.set_z_index(-2)
        if self.params.sides and not self._has_parts():
            # without part labels at the edges the compartments' names sit by the membrane where
            # no molecule is
            free, room = self._free_x()
            x = float(self.to_scene((free, 0.0))[0])
            boxes = [p.bounds() for p in self.placed]
            for name, sign in zip(membrane_sides(self.membrane), (1, -1)):  # type: ignore[arg-type]
                words = self.markup(CELL_COMPARTMENTS[name].label, size=self.params.label_size, color="dim")
                y = self.to_scene((0.0, sign * (BILAYER_NM / 2 + 0.6)))[1] + sign * words.height / 2
                if boxes and (room * unit < words.width + 0.2 or (sign < 0 and self.params.labels)):
                    # no free stretch of membrane wide enough: at the left, beyond the molecules
                    # (and, below, their names)
                    reach = max(b[3] for b in boxes) if sign > 0 else min(b[1] for b in boxes)
                    names = words.height * 2 + 0.25 if sign < 0 and self.params.labels else 0.0
                    y = self.to_scene((0.0, reach))[1] + sign * (words.height / 2 + 0.12 + names)
                    x = body.x0 + words.width / 2 + 0.1
                    y = max(y, body.y0 + (0.75 if self.params.scale_bar else 0.0) + words.height / 2)   # clear of the scale bar
                y = min(max(y, body.y0 + words.height), body.y1 - words.height)
                words.move_to([min(max(x, body.x0 + words.width / 2 + 0.1), body.x1 - words.width / 2 - 0.1), y, 0.0])
                group.add(words)
        return group

    def _membrane_span(self, p: Placed) -> tuple[float, float, float, float]:
        """A membrane protein's extent within the bilayer (where no lipids are drawn)."""
        x0, y0, x1, y1 = p.bounds()
        inner = [q for prim in p.glyph.prims if prim.fill and not prim.text for cv in prim.curves for q in cv if abs(q[1]) < BILAYER_NM / 2]
        if inner:
            xs = [p.point(q)[0] for q in inner]
            return (min(xs), -BILAYER_NM / 2, max(xs), BILAYER_NM / 2)
        return (x0, y0, x1, y1)

    # ----- molecules ---------------------------------------------------------------------------

    def _molecule(self, placed: Placed) -> VGroup:
        prims = place_glyph(placed.glyph, placed.center, placed.angle)
        drawing = glyph_mobjects(prims, self.colors, self.unit, self.origin, self.px_width, self._text)
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
            wanted = len(self.placed) == 1
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
            free = self._free_x()[0]
            for name, sign in zip(membrane_sides(self.membrane), (1, -1)):
                wanted.append(("membrane", self.to_scene((free, sign * (BILAYER_NM / 2 + 1.5))), CELL_COMPARTMENTS[name].label))
        out: dict[str, list[Mobject]] = {}
        for owner, group in zip([w[0] for w in wanted], self._part_labels([(a, t) for _, a, t in wanted])):
            out.setdefault(owner, []).append(group)
        return out

    def _free_x(self) -> tuple[float, float]:
        """The middle (nm) of the widest stretch by the membrane clear of the molecules there,
        and its width."""
        spans = sorted((b[0], b[2]) for p in self.placed for b in [p.bounds()] if b[1] < BILAYER_NM * 1.5 and b[3] > -BILAYER_NM * 1.5)
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
        return group


__all__ = ["Molecule", "MoleculeItem", "layout", "membrane_name"]
