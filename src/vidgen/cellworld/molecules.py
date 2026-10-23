"""Molecules as data (DESIGN.md §95.9): nucleic acids, chromatin, proteins, membrane proteins
and small molecules with their textbook sizes (nm), names typeset (Pango markup), the
compartments and membranes they belong in with the reason, how a membrane protein is oriented
(which part faces which side) and the states it can be drawn in. The location and orientation
rules here are shared by the ``cell`` scene (molecules as complexes of the world) and the
``molecule`` scene (standalone close-ups). No manim.

Sizes: Alberts (Molecular Biology of the Cell), Lodish (Molecular Cell Biology), Luger et al.
1997 (the nucleosome core particle), Erickson 2009 (protein size from mass)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vidgen.errors import VidgenError

from .catalog import COMPARTMENTS, KIND_OPTIONS, KINDS, MEMBRANES, Kind
from .model import did_you_mean, noun
from .notation import chem_markup, chem_plain

Family = Literal["nucleic_acid", "chromatin", "protein", "membrane", "peripheral", "small"]
Side = Literal["n", "p"]

#: B-DNA: 2 nm across, 0.34 nm rise per base pair, 10.5 base pairs per turn.
DNA_WIDTH, DNA_RISE, DNA_BP_PER_TURN = 2.0, 0.34, 10.5
#: Nucleosome core particle: 147 bp in 1.65 left-handed superhelical turns round the histone
#: octamer; a disc about 11 nm across and 5.7 nm thick; linker DNA 20–80 bp.
NUCLEOSOME_BP, NUCLEOSOME_TURNS, NUCLEOSOME_DIAMETER, NUCLEOSOME_HEIGHT = 147, 1.65, 11.0, 5.7
#: The lipid bilayer (nm): 5 nm, its hydrophobic core about 3 nm.
BILAYER_NM, CORE_NM = 5.0, 3.0
#: Ions: hydrated radii (nm), the size a water shell gives them in solution (Nightingale 1959).
IONS: dict[str, float] = {"Na+": 0.358, "K+": 0.331, "Ca2+": 0.412, "Cl-": 0.332, "H+": 0.282, "Mg2+": 0.428}
ION_HUES = {"Na+": "#E0A030", "K+": "#8E6BD0", "Ca2+": "#3FA7A0", "Cl-": "#5FAE4E", "H+": "#D9534F", "Mg2+": "#7FA6C9"}


@dataclass(frozen=True)
class MoleculeKind:
    """A kind of molecule: ``name`` (YAML), ``label`` (Pango markup) and ``plain`` (Unicode),
    ``family``, its drawn ``size`` (nm, its longest extent at the default options) and the
    textbook ``size_range``, a ``note`` (what it is, the numbers), the compartments a soluble
    one may be in (``places``; empty: any) or the membranes a membrane or peripheral one may be
    in or on (``membranes``) with the reason (``why``); for an oriented membrane protein the
    part ``faces:`` names (``faces_part``), the side it must face (``faces_side``: ``n`` the
    cytosolic side — matrix, stroma, a bacterium's cytoplasm —, ``p`` the exoplasmic side) and
    why; the ``states`` it can be drawn in (the first is the default); the cells it occurs in;
    its hue."""

    name: str
    label: str
    plain: str
    family: Family
    size: float
    size_range: tuple[float, float]
    note: str
    hue: str
    places: tuple[str, ...] = ()
    membranes: tuple[str, ...] = ()
    why: str = ""
    faces_part: str = ""
    faces_side: Side | None = None
    faces_why: str = ""
    states: tuple[str, ...] = ()
    cells: tuple[str, ...] = ("animal", "plant", "bacterium")
    cells_why: str = ""

    @property
    def bound(self) -> bool:
        """In or on a membrane (``on:`` places it there)."""
        return self.family in ("membrane", "peripheral")


_NUCLEAR = ("nucleoplasm", "matrix", "stroma")
_AQUEOUS = ("cytosol", "nucleoplasm", "matrix", "stroma")
_ANY_MEMBRANE = tuple(MEMBRANES)

MOLECULES: dict[str, MoleculeKind] = {m.name: m for m in (
    MoleculeKind("dna", "DNA", "DNA", "nucleic_acid", 7.1, (2.0, 2.0e6),
                 "B-DNA: two antiparallel strands, 2 nm across, 0.34 nm and 10.5 base pairs per turn (3.6 nm); A pairs with T, G with C; "
                 "major and minor grooves", "#4F7FD0", places=_NUCLEAR,
                 why="DNA is in the nucleus (and in mitochondria and chloroplasts; a bacterium's in its cytoplasm, the nucleoid)"),
    MoleculeKind("mrna", "mRNA", "mRNA", "nucleic_acid", 18.0, (0.5, 3.0e4),
                 "messenger RNA: one strand read 5′→3′, a 5′ cap (m⁷G) and a 3′ poly(A) tail in eukaryotes", "#D0613E",
                 places=_AQUEOUS, why="mRNA is made in the nucleus and translated in the cytosol (and in mitochondria and chloroplasts)"),
    MoleculeKind("trna", "tRNA", "tRNA", "nucleic_acid", 7.5, (6.0, 8.0),
                 "transfer RNA: about 76 nucleotides, a cloverleaf in two dimensions and an L about 7 nm along each arm in three; the "
                 "anticodon at one end, the amino acid on the 3′ CCA end at the other", "#C2569B", places=_AQUEOUS,
                 why="tRNAs work in the cytosol (and in mitochondria and chloroplasts); they are made in the nucleus"),
    MoleculeKind("rrna", "rRNA", "rRNA", "nucleic_acid", 10.0, (3.0, 30.0),
                 "ribosomal RNA: the ribosome's core and its catalyst (the peptidyl transferase is RNA); 18S, 28S, 5.8S and 5S in "
                 "eukaryotes, 16S, 23S and 5S in bacteria", "#B07A3C", places=("cytosol", "nucleoplasm", "matrix", "stroma"),
                 why="rRNA is made in the nucleolus and works in ribosomes in the cytosol (and in mitochondria and chloroplasts)"),
    MoleculeKind("nucleosome", "Nucleosome", "Nucleosome", "chromatin", NUCLEOSOME_DIAMETER, (10.0, 12.0),
                 "147 bp of DNA in 1.65 left-handed turns round a histone octamer (two each of H2A, H2B, H3, H4): a disc 11 nm across",
                 "#8E7CC3", places=("nucleoplasm",), cells=("animal", "plant"),
                 why="nucleosomes package the DNA of the eukaryotic nucleus (not mitochondrial or chloroplast DNA)",
                 cells_why="bacteria have no histones (their DNA is packed by other proteins)"),
    MoleculeKind("chromatin", "Chromatin", "Chromatin", "chromatin", 60.0, (11.0, 1.0e4),
                 "the 10 nm fibre: nucleosomes on linker DNA like beads on a string, about one per 200 bp; folded further (the "
                 "'30 nm fibre' of the textbooks, loops and domains) — drawn as a schematic", "#8E7CC3", places=("nucleoplasm",),
                 states=("10nm", "compact"), cells=("animal", "plant"),
                 why="chromatin is the DNA and protein of the eukaryotic nucleus",
                 cells_why="bacteria have no histones (their DNA is packed by other proteins)"),
    MoleculeKind("protein", "Protein", "Protein", "protein", 5.0, (2.0, 30.0),
                 "a globular protein, its domains folded on their own (about 4–5 nm for a 50 kDa protein)", "#D08A3A"),
    MoleculeKind("kinase", "Protein kinase", "Protein kinase", "protein", 5.5, (4.0, 10.0),
                 "the kinase fold: a smaller N-lobe and a larger C-lobe with ATP in the cleft between; it moves the γ-phosphate of ATP "
                 "onto Ser, Thr or Tyr of its substrates", "#C9703A", places=_AQUEOUS, states=("active", "inactive"),
                 why="protein kinases work in the cytosol and the nucleus (and organelles)"),
    MoleculeKind("phosphatase", "Protein phosphatase", "Protein phosphatase", "protein", 5.0, (3.5, 10.0),
                 "removes phosphate from Ser, Thr or Tyr (hydrolysis: the phosphate leaves as Pᵢ)", "#5E9F8F", places=_AQUEOUS,
                 why="protein phosphatases work in the cytosol and the nucleus (and organelles)"),
    MoleculeKind("g_protein", "Heterotrimeric G protein", "Heterotrimeric G protein", "peripheral", 8.0, (6.0, 10.0),
                 "Gα (GDP bound when inactive, GTP when active) with Gβγ, held on the cytosolic face of the plasma membrane by lipid "
                 "anchors on Gα and Gγ; an active receptor makes Gα swap GDP for GTP and part from Gβγ", "#4FA35E",
                 membranes=("plasma_membrane", "endosomal_membrane", "golgi_membrane"), faces_part="Gα and Gβγ", faces_side="n",
                 faces_why="heterotrimeric G proteins are anchored by lipids in the cytosolic leaflet, where receptors pass the signal on",
                 why="heterotrimeric G proteins sit on the cytosolic face of the plasma membrane (and of endosomes and the Golgi)",
                 states=("inactive", "active"), cells=("animal", "plant")),
    MoleculeKind("gpcr", "G-protein-coupled receptor", "G-protein-coupled receptor", "membrane", 7.0, (5.0, 12.0),
                 "seven transmembrane α-helices (TM1–TM7), the N-terminus outside the cell and the C-terminus in the cytosol; the "
                 "ligand binds from outside, the G protein on the cytosolic side (ICL2, ICL3, TM6 swings out when active)", "#E06D4E",
                 membranes=("plasma_membrane", "endosomal_membrane"), faces_part="N-terminus", faces_side="p",
                 faces_why="the N-terminus and the ligand-binding pocket face out of the cell; the C-terminus and the G-protein site face "
                           "the cytosol",
                 why="GPCRs sit in the plasma membrane (and, once internalised, in endosomes)", states=("inactive", "active"),
                 cells=("animal", "plant"), cells_why="bacteria have no GPCRs"),
    MoleculeKind("rtk", "Receptor tyrosine kinase", "Receptor tyrosine kinase", "membrane", 20.0, (14.0, 30.0),
                 "one transmembrane helix between an extracellular ligand-binding domain and a cytosolic tyrosine kinase domain; the "
                 "ligand brings two together (a dimer) and each phosphorylates the other's tyrosines", "#3F8FC0",
                 membranes=("plasma_membrane", "endosomal_membrane"), faces_part="ligand-binding domain", faces_side="p",
                 faces_why="the ligand-binding domain is outside the cell; the kinase domain is in the cytosol",
                 why="receptor tyrosine kinases sit in the plasma membrane (and, internalised, in endosomes)", states=("monomer", "dimer"),
                 cells=("animal",), cells_why="receptor tyrosine kinases are animal proteins"),
    MoleculeKind("ion_channel", "Ion channel", "Ion channel", "membrane", 10.0, (5.0, 20.0),
                 "a gated pore: ions flow down their electrochemical gradient when the gate is open (10⁷–10⁸ ions per second); a "
                 "selectivity filter near the outer mouth, the gate at the inner end; gated by voltage, a ligand or stretch", "#3FA7A0",
                 membranes=_ANY_MEMBRANE, faces_part="cytoplasmic gate", faces_side="n",
                 faces_why="the gate and the voltage sensor's charges sit as in the textbook channel: gate to the cytosolic side",
                 why="ion channels sit in membranes", states=("closed", "open")),
    MoleculeKind("carrier", "Carrier (transporter)", "Carrier (transporter)", "membrane", 6.0, (4.0, 10.0),
                 "binds its solutes and changes shape (alternating access: open to one side, then the other), never open to both "
                 "at once; uniport (one solute), symport (two the same way), antiport (two opposite ways)", "#7B6BB0",
                 membranes=_ANY_MEMBRANE, why="carriers sit in membranes", states=("outward", "inward")),
    MoleculeKind("na_k_atpase", "Na<sup>+</sup>/K<sup>+</sup>-ATPase", "Na⁺/K⁺-ATPase", "membrane", 15.0, (12.0, 18.0),
                 "the sodium pump (a P-type ATPase): per ATP it pumps 3 Na⁺ out of the cell and 2 K⁺ in; α subunit (10 TM helices, "
                 "the ATP site on its cytosolic domains) and a glycosylated β subunit", "#E0A030",
                 membranes=("plasma_membrane",), faces_part="ATP-binding domains", faces_side="n",
                 faces_why="ATP is bound and hydrolysed on the cytosolic side; Na⁺ leaves to the outside, K⁺ comes in",
                 why="the Na⁺/K⁺ pump is in the plasma membrane of animal cells", states=("e1", "e2"),
                 cells=("animal",), cells_why="plant and fungal cells use H⁺-ATPases in their plasma membrane instead"),
    MoleculeKind("atp_synthase", "ATP synthase", "ATP synthase", "membrane", 22.0, (18.0, 26.0),
                 "F-type ATP synthase: Fₒ in the membrane (the c-ring: 8 c subunits in animal mitochondria, 10 in yeast and E. coli, "
                 "14 in chloroplasts) turned by protons flowing down their gradient; F₁ (α₃β₃, about 10 nm) makes ATP from ADP and Pᵢ "
                 "on the N side; about 3 ATP per turn", "#D9534F",
                 membranes=("inner_mitochondrial_membrane", "thylakoid_membrane", "bacterial_inner_membrane"),
                 faces_part="F<sub>1</sub>", faces_side="n",
                 faces_why="F₁ makes ATP where ADP and Pᵢ are — the matrix, the stroma or a bacterium's cytoplasm (the N side); protons "
                           "reach Fₒ from the intermembrane space, the thylakoid lumen or the periplasm",
                 why="ATP synthase sits in the inner mitochondrial membrane (on the cristae), the thylakoid membrane and a bacterium's "
                     "plasma membrane", states=("synthesis", "hydrolysis")),
    MoleculeKind("atp", "ATP", "ATP", "small", 1.6, (1.2, 1.8), "adenosine triphosphate (507 Da): adenine, ribose, three phosphates",
                 "#E05A5A"),
    MoleculeKind("adp", "ADP", "ADP", "small", 1.3, (1.0, 1.5), "adenosine diphosphate", "#E08A5A"),
    MoleculeKind("pi", "P<sub>i</sub>", "Pᵢ", "small", 0.5, (0.4, 0.6), "inorganic phosphate (HPO₄²⁻ / H₂PO₄⁻ at cellular pH)", "#E8B730"),
    MoleculeKind("gtp", "GTP", "GTP", "small", 1.6, (1.2, 1.8), "guanosine triphosphate", "#4FA35E"),
    MoleculeKind("gdp", "GDP", "GDP", "small", 1.3, (1.0, 1.5), "guanosine diphosphate", "#7FB36A"),
    MoleculeKind("camp", "cAMP", "cAMP", "small", 1.0, (0.8, 1.2), "cyclic AMP (3′,5′-cyclic adenosine monophosphate), a second messenger made "
                 "from ATP by adenylyl cyclase", "#C2569B", places=("cytosol", "nucleoplasm"),
                 why="cAMP is a second messenger in the cytosol (made at the plasma membrane by adenylyl cyclase)"),
    MoleculeKind("glucose", "Glucose", "Glucose", "small", 0.9, (0.7, 1.0), "D-glucose (180 Da), a six-membered ring in solution", "#5FAE4E"),
    MoleculeKind("ligand", "Ligand", "Ligand", "small", 1.2, (0.3, 10.0), "a signal molecule that binds a receptor (a hormone, a "
                 "neurotransmitter, a growth factor)", "#E39B32"),
    MoleculeKind("ion", "Ion", "Ion", "small", 0.7, (0.5, 0.9), "an ion with its water shell (hydrated radius 0.28–0.43 nm)", "#E0A030"),
)}

#: ATP synthase c-ring sizes by where it is (c subunits; protons per turn).
C_RING = {"inner_mitochondrial_membrane": 8, "thylakoid_membrane": 14, "bacterial_inner_membrane": 10}
#: Carrier modes and their defaults: solutes and the way each moves (in: into the cytosol).
CARRIER_MODES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "uniport": (("glucose",), ("in",)),
    "symport": (("Na+", "glucose"), ("in", "in")),
    "antiport": (("Na+", "H+"), ("in", "out")),
}
GATINGS = ("voltage", "ligand", "mechanical")
RRNA_TYPES = {"5S": "both", "5.8S": "eukaryote", "18S": "eukaryote", "28S": "eukaryote", "25S": "eukaryote", "16S": "prokaryote",
              "23S": "prokaryote", "12S": "mitochondrion"}


def molecule_kind(name: str, where: str) -> MoleculeKind:
    """The molecule kind ``name``, or a :class:`VidgenError` with did-you-mean."""
    if name not in MOLECULES:
        raise VidgenError(f"{where}: unknown molecule '{name}'{did_you_mean(name, list(MOLECULES))} (molecules: {', '.join(MOLECULES)})")
    return MOLECULES[name]


def membrane_sides(membrane: str) -> tuple[str, str]:
    """``(exoplasmic side, cytosolic side)`` of a membrane, as compartments: the plasma membrane
    ``(extracellular, cytosol)``, the inner mitochondrial membrane ``(intermembrane_space,
    matrix)``, the thylakoid membrane ``(thylakoid_lumen, stroma)`` — the P and N sides of an
    energy-transducing membrane."""
    m = MEMBRANES[membrane]
    return (m.outside, m.inside) if m.exo == "outside" else (m.inside, m.outside)


def check_membrane(kind: MoleculeKind, membrane: str, where: str) -> None:
    """Refuse a membrane protein in a membrane it does not occur in (with the reason)."""
    if membrane not in MEMBRANES:
        raise VidgenError(f"{where}: membrane '{membrane}'{did_you_mean(membrane, list(MEMBRANES))} (membranes: {', '.join(MEMBRANES)})")
    if not kind.bound:
        raise VidgenError(f"{where}: a {kind.plain} is not a membrane protein; place it in a compartment")
    if membrane not in kind.membranes:
        label = MEMBRANES[membrane].label.lower()
        raise VidgenError(f"{where}: a {kind.plain} is not in the {label}: {kind.why}")


def check_faces(kind: MoleculeKind, membrane: str, faces: str | None, where: str) -> None:
    """Refuse an orientation the protein never has: ``faces`` names the compartment its
    ``faces_part`` faces (``ATP synthase F₁ must face the matrix``)."""
    if faces is None:
        return
    if faces not in COMPARTMENTS:
        raise VidgenError(f"{where}: faces '{faces}'{did_you_mean(faces, list(COMPARTMENTS))}: name the compartment its "
                          f"{chem_plain(kind.faces_part) or 'main part'} faces")
    exo, cyto = membrane_sides(membrane)
    if faces not in (exo, cyto):
        raise VidgenError(f"{where}: faces '{faces}': the {MEMBRANES[membrane].label.lower()} lies between the "
                          f"{COMPARTMENTS[exo].label.lower()} and the {COMPARTMENTS[cyto].label.lower()}")
    if kind.faces_side is None:
        return
    right = cyto if kind.faces_side == "n" else exo
    if faces != right:
        part = _plain_part(kind)
        raise VidgenError(f"{where}: {kind.plain} {part} must face the {_compartment_words(right)}, not the "
                          f"{_compartment_words(faces)}: {kind.faces_why}")


def _plain_part(kind: MoleculeKind) -> str:
    return kind.faces_part.replace("<sub>1</sub>", "₁").replace("<sub>o</sub>", "ₒ")


def _compartment_words(name: str) -> str:
    """``mitochondrial matrix``, ``intermembrane space``, ``extracellular space``."""
    return noun(COMPARTMENTS[name].label)


def check_place(kind: MoleculeKind, compartment: str, where: str) -> None:
    """Refuse a soluble molecule in a compartment it is not found in (DNA outside the nucleus
    and the DNA-holding organelles, cAMP outside the cytosol)."""
    if kind.bound or not kind.places or compartment in kind.places:
        return
    raise VidgenError(f"{where}: {kind.plain} in the {_compartment_words(compartment)}: {kind.why}")


def protein_size(mass_kda: float) -> float:
    """The diameter (nm) of a compact globular protein of ``mass_kda`` (Erickson 2009: the
    minimal radius is 0.066 nm × (mass in Da)^⅓)."""
    return 2 * 0.066 * (mass_kda * 1000.0) ** (1.0 / 3.0)


def ion_markup(name: str, where: str) -> str:
    """An ion of :data:`IONS` (``Na+``, ``Ca2+``…) as markup, or an error listing them."""
    if name not in IONS:
        raise VidgenError(f"{where}: ion '{name}': use {', '.join(IONS)}{did_you_mean(name, list(IONS))}")
    return chem_markup(name)


def bp_length(bp: int) -> float:
    """The length (nm) of ``bp`` base pairs of B-DNA."""
    return bp * DNA_RISE


def pitch() -> float:
    """One helical turn of B-DNA (nm): 10.5 × 0.34 = 3.57 nm."""
    return DNA_BP_PER_TURN * DNA_RISE


def _plural(m: MoleculeKind) -> str:
    if m.name == "carrier":
        return "Carriers (transporters)"
    if m.name == "chromatin" or (m.family in ("nucleic_acid", "small") and m.name not in ("ligand", "ion")):
        return m.plain                       # DNA, mRNA, ATP, glucose: the same word for several
    return m.plain + "s"


def _as_kind(m: MoleculeKind) -> Kind:
    """The cell world's kind of a molecule (a complex, in nm; placed ``in:`` its compartments,
    or ``on:`` a membrane by :mod:`.placing`)."""
    places = () if m.bound else (m.places or tuple(c for c in COMPARTMENTS if c not in ("cell_wall", "capsule")))
    return Kind(m.name, m.plain, _plural(m), "complex", "molecule", m.size / 1000.0, (m.size_range[0] / 1000.0, m.size_range[1] / 1000.0), None,
                (), (), frozenset(places), frozenset(), m.why or m.note, m.hue, frozenset(m.cells), m.cells_why)


# molecules are kinds of the cell world too (complexes placed in or on its compartments and membranes)
KINDS.update({m.name: _as_kind(m) for m in MOLECULES.values()})
KIND_OPTIONS.update({"state": tuple(m.name for m in MOLECULES.values() if m.states),
                     "faces": tuple(m.name for m in MOLECULES.values() if m.bound),
                     "membrane": tuple(m.name for m in MOLECULES.values() if m.bound)})


__all__ = ["BILAYER_NM", "CARRIER_MODES", "CORE_NM", "C_RING", "DNA_BP_PER_TURN", "DNA_RISE", "DNA_WIDTH", "GATINGS", "IONS", "ION_HUES",
           "MOLECULES", "MoleculeKind", "NUCLEOSOME_BP", "NUCLEOSOME_DIAMETER", "NUCLEOSOME_HEIGHT", "NUCLEOSOME_TURNS", "RRNA_TYPES",
           "bp_length", "check_faces", "check_membrane", "check_place", "ion_markup", "membrane_sides", "molecule_kind", "pitch",
           "protein_size"]
