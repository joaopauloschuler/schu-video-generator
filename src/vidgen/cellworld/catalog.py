"""What a cell world is made of (DESIGN.md §95.2, §95.9): compartments, membranes, the kinds of
things placed in them with their real sizes, which cells have them and where each may be (the
location rules' data), and what each membrane's lipids are. Plain data, no manim. Sizes are
textbook-consensus values (Alberts, Molecular Biology of the Cell; Lodish, Molecular Cell
Biology) in micrometres; a drawing may stylise shapes, never sizes or places, unless it says it
is not to scale (the accuracy lint of Step 209)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Topology = Literal["cytosolic", "lumenal", "extracellular", "mitochondrial", "peroxisomal", "plastid", "periplasmic"]
Category = Literal["structure", "complex", "filament"]

#: Thickness of a lipid bilayer (µm): about 4–5 nm.
BILAYER = 0.005
#: Space between the outer and the inner nuclear membrane (the perinuclear space, 20–40 nm).
PERINUCLEAR_GAP = 0.03
#: Space between the outer and the inner mitochondrial membrane (the intermembrane space).
MITO_GAP = 0.02
#: A crista's lumen (the intracristal space) and its junction with the inner boundary membrane.
CRISTA_LUMEN, CRISTA_JUNCTION = 0.025, 0.013
#: Lumen of a rough-ER sheet, membrane to membrane (about 30–60 nm).
ER_LUMEN = 0.05
#: Diameter of a smooth-ER tubule (about 50 nm).
ER_TUBULE = 0.05
#: A Golgi cisterna's lumen, the distance from one cisterna to the next (a stack is tight: 10–20
#: nm between cisternae), and its dilated rims.
GOLGI_LUMEN, GOLGI_PERIOD, GOLGI_RIM = 0.03, 0.06, 0.055
#: Nuclear pores met per µm of nuclear envelope in a thin section (pore complexes are about
#: 120 nm across, about 10 per µm² of envelope).
PORES_PER_UM = 1.0
#: Nuclear pores per µm² of envelope (a surface view).
PORES_PER_UM2 = 10.0
#: Ribosomes per µm along each cytosolic face of a rough-ER sheet in the drawing.
ER_RIBOSOMES_PER_UM = 6.0
#: The chloroplast envelope's two membranes (10–20 nm apart); a thylakoid (membrane to membrane)
#: and the stacking period of a granum; a granum's diameter.
CHLOROPLAST_GAP, THYLAKOID_LUMEN, GRANUM_PERIOD, GRANUM_WIDTH = 0.015, 0.008, 0.018, 0.45
#: A plant cell wall (primary wall 0.1–1 µm) and a plasmodesma (40–60 nm across, with its
#: desmotubule of appressed ER, about 15 nm).
CELL_WALL, PLASMODESMA, DESMOTUBULE = 0.25, 0.05, 0.015
#: A Gram-negative bacterium's periplasm (outer to inner membrane, about 20–30 nm) and
#: peptidoglycan (one or a few layers, about 7 nm); a Gram-positive wall (20–80 nm).
PERIPLASM, THIN_WALL, THICK_WALL = 0.025, 0.007, 0.04
#: A bacterial capsule (0.1 µm to over 1 µm).
CAPSULE = 0.2
#: Filament diameters: actin 7 nm, intermediate filaments 10 nm, microtubules 25 nm (lumen
#: 15 nm), a bacterial flagellum 20 nm, a pilus (fimbria) 7 nm.
ACTIN, INTERMEDIATE, MICROTUBULE, FLAGELLUM, PILUS = 0.007, 0.010, 0.025, 0.020, 0.007
#: The actin cortex under the plasma membrane (0.1–1 µm thick).
CORTEX = 0.3
#: A lipid in a bilayer: about 0.8 nm apart (0.65 nm² each); its head group about 0.8 nm.
LIPID_SPACING, LIPID_HEAD = 0.0008, 0.0008
#: Coats of transport vesicles (thickness outside the vesicle membrane).
COATS: dict[str, float] = {"clathrin": 0.018, "copi": 0.012, "copii": 0.014}
COAT_LABELS = {"clathrin": "Clathrin", "copi": "COPI", "copii": "COPII"}
COAT_HUES = {"clathrin": "#E39B32", "copi": "#2FA3B3", "copii": "#C2569B"}


@dataclass(frozen=True)
class Compartment:
    """A space of the cell: its name, label and topology ("lumenal" spaces are topologically
    outside the cell: their contents reach the extracellular space by exocytosis)."""

    name: str
    label: str
    topology: Topology
    note: str


@dataclass(frozen=True)
class Membrane:
    """A membrane between two compartments (``inside`` / ``outside`` are compartment names);
    ``exo`` is the side its exoplasmic leaflet faces (the non-cytosolic side, where glycolipids
    are)."""

    name: str
    label: str
    outside: str
    inside: str
    exo: Literal["outside", "inside"] = "inside"


COMPARTMENTS: dict[str, Compartment] = {c.name: c for c in (
    Compartment("extracellular", "Extracellular space", "extracellular", "outside the plasma membrane"),
    Compartment("cytosol", "Cytosol", "cytosolic", "the fluid of the cytoplasm, around the organelles"),
    Compartment("nucleoplasm", "Nucleoplasm", "cytosolic", "inside the nucleus; joined to the cytosol through the nuclear pores"),
    Compartment("perinuclear_space", "Perinuclear space", "lumenal", "between the two nuclear membranes; continuous with the ER lumen"),
    Compartment("er_lumen", "ER lumen", "lumenal", "inside the endoplasmic reticulum"),
    Compartment("golgi_lumen", "Golgi lumen", "lumenal", "inside the Golgi cisternae"),
    Compartment("cis_golgi_lumen", "cis-Golgi lumen", "lumenal", "inside a cis cisterna (it faces the ER and receives its cargo)"),
    Compartment("medial_golgi_lumen", "Medial-Golgi lumen", "lumenal", "inside a medial cisterna"),
    Compartment("trans_golgi_lumen", "trans-Golgi lumen", "lumenal", "inside a trans cisterna (it sorts cargo out of the Golgi)"),
    Compartment("lysosome_lumen", "Lysosome lumen", "lumenal", "acidic (pH about 4.5–5), full of hydrolases"),
    Compartment("endosome_lumen", "Endosome lumen", "lumenal", "inside an endosome (early: pH about 6.2; late: about 5.5)"),
    Compartment("intraluminal_vesicle", "Inside an intraluminal vesicle", "cytosolic",
                "inside a vesicle that budded into a late endosome: cytosol taken in"),
    Compartment("vesicle_lumen", "Vesicle lumen", "lumenal", "inside a transport vesicle"),
    Compartment("intermembrane_space", "Intermembrane space", "mitochondrial",
                "between the outer and the inner mitochondrial membrane; continuous with the intracristal space"),
    Compartment("matrix", "Mitochondrial matrix", "mitochondrial", "inside the inner mitochondrial membrane"),
    Compartment("peroxisome_matrix", "Peroxisomal matrix", "peroxisomal", "inside a peroxisome"),
    Compartment("vacuole_lumen", "Vacuole lumen (cell sap)", "lumenal", "inside the central vacuole: water, ions, sugars, pigments; acidic"),
    Compartment("chloroplast_intermembrane_space", "Chloroplast intermembrane space", "plastid",
                "between the outer and the inner envelope membrane"),
    Compartment("stroma", "Stroma", "plastid", "inside a chloroplast's inner envelope, round the thylakoids (the Calvin cycle runs here)"),
    Compartment("thylakoid_lumen", "Thylakoid lumen", "plastid", "inside the thylakoids (protons are pumped into it in the light)"),
    Compartment("cell_wall", "Cell wall", "extracellular", "outside the plasma membrane: cellulose (plants) or peptidoglycan (bacteria)"),
    Compartment("periplasm", "Periplasm", "periplasmic", "between a Gram-negative bacterium's inner and outer membrane, with its peptidoglycan"),
    Compartment("capsule", "Capsule", "extracellular", "a polysaccharide layer outside a bacterium's wall"),
)}

MEMBRANES: dict[str, Membrane] = {m.name: m for m in (
    Membrane("plasma_membrane", "Plasma membrane", "extracellular", "cytosol", "outside"),
    Membrane("outer_nuclear_membrane", "Outer nuclear membrane", "cytosol", "perinuclear_space"),
    Membrane("inner_nuclear_membrane", "Inner nuclear membrane", "perinuclear_space", "nucleoplasm", "outside"),
    Membrane("er_membrane", "ER membrane", "cytosol", "er_lumen"),
    Membrane("golgi_membrane", "Golgi membrane", "cytosol", "golgi_lumen"),
    Membrane("outer_mitochondrial_membrane", "Outer mitochondrial membrane", "cytosol", "intermembrane_space"),
    Membrane("inner_mitochondrial_membrane", "Inner mitochondrial membrane", "intermembrane_space", "matrix", "outside"),
    Membrane("lysosomal_membrane", "Lysosomal membrane", "cytosol", "lysosome_lumen"),
    Membrane("endosomal_membrane", "Endosomal membrane", "cytosol", "endosome_lumen"),
    Membrane("intraluminal_vesicle_membrane", "Intraluminal vesicle membrane", "endosome_lumen", "intraluminal_vesicle", "outside"),
    Membrane("vesicle_membrane", "Vesicle membrane", "cytosol", "vesicle_lumen"),
    Membrane("peroxisomal_membrane", "Peroxisomal membrane", "cytosol", "peroxisome_matrix"),
    Membrane("tonoplast", "Tonoplast (vacuolar membrane)", "cytosol", "vacuole_lumen"),
    Membrane("outer_envelope_membrane", "Outer envelope membrane", "cytosol", "chloroplast_intermembrane_space"),
    Membrane("inner_envelope_membrane", "Inner envelope membrane", "chloroplast_intermembrane_space", "stroma", "outside"),
    Membrane("thylakoid_membrane", "Thylakoid membrane", "stroma", "thylakoid_lumen"),
    Membrane("bacterial_inner_membrane", "Inner (plasma) membrane", "periplasm", "cytosol", "outside"),
    Membrane("bacterial_outer_membrane", "Outer membrane", "extracellular", "periplasm", "outside"),
)}


@dataclass(frozen=True)
class Lipids:
    """What a membrane's lipids are, as drawn in a close-up: the share of sterols (cholesterol in
    animals, phytosterols in plants; none in bacteria or the inner mitochondrial membrane), of
    glycolipids (exoplasmic leaflet only), of cardiolipin (inner mitochondrial and bacterial
    membranes) and galactolipids (chloroplast membranes), LPS on the outer leaflet of a
    Gram-negative outer membrane, a glycocalyx outside, lipid rafts."""

    sterol: float = 0.0
    glycolipid: float = 0.0
    cardiolipin: float = 0.0
    galactolipid: float = 0.0
    lps: bool = False
    glycocalyx: bool = False
    rafts: bool = False


#: Lipids of each membrane (Alberts Table 10–1; Lodish): the plasma membrane is rich in
#: cholesterol (about a third of its lipids) with glycolipids on the outer leaflet, the ER poor in
#: it; the inner mitochondrial membrane has no cholesterol and much cardiolipin; thylakoids are
#: mostly galactolipids.
MEMBRANE_LIPIDS: dict[str, Lipids] = {
    "plasma_membrane": Lipids(sterol=0.33, glycolipid=0.08, glycocalyx=True, rafts=True),
    "outer_nuclear_membrane": Lipids(sterol=0.06),
    "inner_nuclear_membrane": Lipids(sterol=0.06),
    "er_membrane": Lipids(sterol=0.06),
    "golgi_membrane": Lipids(sterol=0.15, glycolipid=0.04),
    "outer_mitochondrial_membrane": Lipids(sterol=0.04),
    "inner_mitochondrial_membrane": Lipids(cardiolipin=0.18),
    "lysosomal_membrane": Lipids(sterol=0.2),
    "endosomal_membrane": Lipids(sterol=0.25, glycolipid=0.05),
    "intraluminal_vesicle_membrane": Lipids(sterol=0.15),
    "vesicle_membrane": Lipids(sterol=0.25, glycolipid=0.04),
    "peroxisomal_membrane": Lipids(sterol=0.05),
    "tonoplast": Lipids(sterol=0.1),
    "outer_envelope_membrane": Lipids(galactolipid=0.5),
    "inner_envelope_membrane": Lipids(galactolipid=0.75),
    "thylakoid_membrane": Lipids(galactolipid=0.8),
    "bacterial_inner_membrane": Lipids(cardiolipin=0.08),
    "bacterial_outer_membrane": Lipids(lps=True),
}
#: Plant plasma membranes: phytosterols, no glycocalyx (the wall is outside); bacteria: no sterols.
PLANT_PLASMA_LIPIDS = Lipids(sterol=0.3, glycolipid=0.08, rafts=True)
BACTERIAL_PLASMA_LIPIDS = Lipids(cardiolipin=0.08)

Shape = Literal["ellipse", "capsule", "sheets", "tubules", "stack", "region", "particle", "box", "lens", "filament", "motor", "appendage"]
CellKind = Literal["animal", "plant", "bacterium"]
EUKARYOTES = ("animal", "plant")


@dataclass(frozen=True)
class Kind:
    """A kind of thing in a cell world.

    ``size`` is its default length (the long axis, µm) and ``width`` its default short axis
    (``None``: round); ``size_range`` the textbook range of the length. ``membranes`` are its own
    membranes from the outside in, ``interior`` the compartments they enclose (outermost first;
    the last is its main inside, what ``in: <id>`` means). ``places`` are the compartments it
    may be in and ``surfaces`` the kinds whose membrane (or filament) it may sit on (``on:``);
    ``why`` is the textbook reason the location rules quote. ``cells`` are the kinds of cell
    that have it and ``cells_why`` says why the others do not; ``sizes`` overrides ``size`` per
    cell kind (a bacterium's 70S ribosome)."""

    name: str
    label: str
    plural: str
    category: Category
    shape: Shape
    size: float
    size_range: tuple[float, float]
    width: float | None
    membranes: tuple[str, ...]
    interior: tuple[str, ...]
    places: frozenset[str]
    surfaces: frozenset[str]
    why: str
    hue: str
    cells: frozenset[str] = frozenset(EUKARYOTES)
    cells_why: str = ""
    sizes: tuple[tuple[str, float], ...] = field(default=())

    def size_in(self, cell: str) -> float:
        """Its default length in a cell of kind ``cell``."""
        return dict(self.sizes).get(cell, self.size)


def _kind(name: str, label: str, plural: str, category: Category, shape: Shape, size: float, size_range: tuple[float, float],
          width: float | None, membranes: tuple[str, ...], interior: tuple[str, ...], places: tuple[str, ...], why: str, hue: str,
          surfaces: tuple[str, ...] = (), cells: tuple[str, ...] = EUKARYOTES, cells_why: str = "",
          sizes: tuple[tuple[str, float], ...] = ()) -> Kind:
    return Kind(name, label, plural, category, shape, size, size_range, width, membranes, interior, frozenset(places), frozenset(surfaces), why, hue,
                frozenset(cells), cells_why, sizes)


_NO_ORGANELLES = "prokaryotes have no nucleus and no membrane-bounded organelles"
_ACTIN_KINDS = ("actin_cortex", "stress_fiber", "actin_filament")

KINDS: dict[str, Kind] = {k.name: k for k in (
    _kind("nucleus", "Nucleus", "Nuclei", "structure", "ellipse", 7.0, (5.0, 10.0), 6.0,
          ("outer_nuclear_membrane", "inner_nuclear_membrane"), ("perinuclear_space", "nucleoplasm"), ("cytosol",),
          "the nucleus lies in the cytoplasm, surrounded by cytosol", "#8E7CC3", cells_why=_NO_ORGANELLES + " (their DNA is a nucleoid)"),
    _kind("nucleolus", "Nucleolus", "Nucleoli", "structure", "region", 1.8, (1.0, 3.0), None, (), (), ("nucleoplasm",),
          "the nucleolus is a region of the nucleoplasm (it has no membrane) where ribosomal RNA is made and ribosomal subunits are assembled",
          "#5E4B9C", cells_why=_NO_ORGANELLES),
    _kind("rough_er", "Rough ER", "Rough ER", "structure", "sheets", 6.0, (2.0, 20.0), None, ("er_membrane",), ("er_lumen",), ("cytosol",),
          "rough-ER sheets spread through the cytosol from the nuclear envelope (the ER lumen is continuous with the perinuclear space)",
          "#3F8FC0", cells_why=_NO_ORGANELLES),
    _kind("smooth_er", "Smooth ER", "Smooth ER", "structure", "tubules", 3.0, (1.0, 10.0), None, ("er_membrane",), ("er_lumen",), ("cytosol",),
          "smooth-ER tubules spread through the cytosol as a network joined to the rough ER (no ribosomes on them)", "#5FB0C8",
          cells_why=_NO_ORGANELLES),
    _kind("golgi", "Golgi apparatus", "Golgi stacks", "structure", "stack", 2.0, (0.5, 3.0), None, ("golgi_membrane",), ("golgi_lumen",),
          ("cytosol",), "the Golgi stack lies in the cytosol (in animal cells next to the nucleus and the centrosome), its cis face towards the ER",
          "#E0A33A", cells_why=_NO_ORGANELLES),
    _kind("mitochondrion", "Mitochondrion", "Mitochondria", "structure", "capsule", 2.0, (0.5, 4.0), 0.7,
          ("outer_mitochondrial_membrane", "inner_mitochondrial_membrane"), ("intermembrane_space", "matrix"), ("cytosol",),
          "mitochondria lie in the cytosol", "#E06D4E", cells_why=_NO_ORGANELLES + " (their respiratory chain is in the plasma membrane)"),
    _kind("lysosome", "Lysosome", "Lysosomes", "structure", "ellipse", 0.5, (0.1, 1.2), None, ("lysosomal_membrane",), ("lysosome_lumen",),
          ("cytosol",), "lysosomes lie in the cytosol", "#4FA35E", cells=("animal",),
          cells_why="plant cells digest in their lytic vacuole instead of lysosomes; prokaryotes have no organelles"),
    _kind("peroxisome", "Peroxisome", "Peroxisomes", "structure", "ellipse", 0.5, (0.1, 1.0), None, ("peroxisomal_membrane",),
          ("peroxisome_matrix",), ("cytosol",), "peroxisomes lie in the cytosol", "#A3A83C", cells_why=_NO_ORGANELLES),
    _kind("endosome", "Endosome", "Endosomes", "structure", "ellipse", 0.4, (0.1, 0.8), None, ("endosomal_membrane",), ("endosome_lumen",),
          ("cytosol",), "endosomes lie in the cytosol", "#3BA8A0", cells_why=_NO_ORGANELLES),
    _kind("early_endosome", "Early endosome", "Early endosomes", "structure", "ellipse", 0.35, (0.1, 0.5), None, ("endosomal_membrane",),
          ("endosome_lumen",), ("cytosol",),
          "early endosomes lie in the cytosol near the plasma membrane: a vacuole with tubules where endocytosed cargo is sorted", "#3BA8A0",
          cells_why=_NO_ORGANELLES),
    _kind("late_endosome", "Late endosome", "Late endosomes", "structure", "ellipse", 0.45, (0.25, 0.6), None,
          ("endosomal_membrane",), ("endosome_lumen",), ("cytosol",),
          "late endosomes (multivesicular bodies) lie in the cytosol, nearer the nucleus, full of intraluminal vesicles", "#2E8C86",
          cells_why=_NO_ORGANELLES),
    _kind("vesicle", "Vesicle", "Vesicles", "structure", "ellipse", 0.08, (0.04, 0.2), None, ("vesicle_membrane",), ("vesicle_lumen",),
          ("cytosol",), "transport vesicles travel through the cytosol", "#C77DB0", cells_why=_NO_ORGANELLES),
    _kind("centrosome", "Centrosome", "Centrosomes", "structure", "region", 1.0, (0.5, 2.0), None, (), (), ("cytosol",),
          "the centrosome (two centrioles in pericentriolar material) lies in the cytosol next to the nucleus", "#7A8BA6", cells=("animal",),
          cells_why="flowering-plant cells have no centrioles: their microtubules grow from many nucleation sites (the nuclear surface, the "
                    "cortex); prokaryotes have no centrosome"),
    _kind("chloroplast", "Chloroplast", "Chloroplasts", "structure", "lens", 5.0, (3.0, 10.0), 2.2,
          ("outer_envelope_membrane", "inner_envelope_membrane"), ("chloroplast_intermembrane_space", "stroma"), ("cytosol",),
          "chloroplasts lie in the cytosol, usually in the thin layer between the plasma membrane and the vacuole", "#4E9F3D",
          cells=("plant",), cells_why="only plant (and algal) cells have chloroplasts; cyanobacteria photosynthesise on thylakoids of their own"),
    _kind("vacuole", "Central vacuole", "Vacuoles", "structure", "box", 18.0, (5.0, 90.0), 14.0, ("tonoplast",), ("vacuole_lumen",), ("cytosol",),
          "the central vacuole fills most of a plant cell, the cytoplasm pressed into a thin layer round it", "#8DBBD6", cells=("plant",),
          cells_why="a large central vacuole is a plant (and fungal) feature; animal cells have small vacuoles and lysosomes"),
    _kind("nucleoid", "Nucleoid", "Nucleoids", "structure", "region", 1.0, (0.3, 2.0), 0.45, (), (), ("cytosol",),
          "the nucleoid is the region of a prokaryote's cytoplasm that holds its chromosome (no membrane)", "#7B6BB0", cells=("bacterium",),
          cells_why="eukaryotes keep their chromosomes in a nucleus (add a nucleus)"),
    _kind("ribosome", "Ribosome", "Ribosomes", "complex", "particle", 0.025, (0.02, 0.03), None, (), (), ("cytosol", "matrix", "stroma"),
          "ribosomes translate in the cytosol (free, or on the cytosolic face of the rough ER and the outer nuclear membrane) and, as "
          "mitochondria's and chloroplasts' own ribosomes, in the matrix and the stroma; never in the nucleoplasm: their subunits are assembled "
          "in the nucleolus and leave through the nuclear pores, and translation starts only in the cytoplasm", "#3E4A9E",
          surfaces=("rough_er", "nucleus"), cells=("animal", "plant", "bacterium"), sizes=(("bacterium", 0.021),)),
    _kind("proteasome", "Proteasome", "Proteasomes", "complex", "particle", 0.045, (0.03, 0.05), 0.02, (), (), ("cytosol", "nucleoplasm"),
          "proteasomes break down ubiquitin-tagged proteins in the cytosol and the nucleoplasm, never inside a membrane-bounded lumen",
          "#B0574F", cells_why="most bacteria have no 26S proteasome (they use other proteases)"),
    _kind("nuclear_pore", "Nuclear pore", "Nuclear pores", "complex", "particle", 0.12, (0.1, 0.13), 0.06, (), (), (),
          "nuclear pore complexes span both membranes of the nuclear envelope, nowhere else", "#6B5AA8", surfaces=("nucleus",),
          cells_why=_NO_ORGANELLES),
    _kind("plasmid", "Plasmid", "Plasmids", "complex", "particle", 0.12, (0.05, 0.3), None, (), (), ("cytosol",),
          "plasmids are small circular DNA molecules in a bacterium's cytoplasm", "#9B5FB0", cells=("bacterium",),
          cells_why="plasmids are drawn in bacteria here (eukaryotic DNA is in the nucleus)"),
    _kind("flagellum", "Flagellum", "Flagella", "filament", "appendage", 6.0, (3.0, 15.0), FLAGELLUM, (), (), ("extracellular",),
          "a bacterial flagellum is anchored in the cell envelope by its basal body (a rotary motor) and its filament reaches outside",
          "#8C6D4F", cells=("bacterium",),
          cells_why="a eukaryotic flagellum or cilium is a different structure (9+2 microtubules in a membrane); this one is the bacterial kind"),
    _kind("pilus", "Pilus", "Pili", "filament", "appendage", 1.0, (0.2, 2.0), PILUS, (), (), ("extracellular",),
          "pili (fimbriae) reach out from a bacterium's envelope", "#A88A62", cells=("bacterium",), cells_why="pili are bacterial"),
    _kind("microtubule", "Microtubule", "Microtubules", "filament", "filament", 8.0, (0.5, 50.0), MICROTUBULE, (), (), ("cytosol",),
          "microtubules grow through the cytosol: in animal cells from the centrosome (their minus ends) out to the periphery (plus ends)",
          "#2E9C62", cells_why="bacteria have tubulin-like FtsZ but no microtubules"),
    _kind("actin_filament", "Actin filament", "Actin filaments", "filament", "filament", 2.0, (0.1, 20.0), ACTIN, (), (), ("cytosol",),
          "actin filaments lie in the cytosol", "#D2455B", cells_why="bacteria have actin-like MreB but no actin filaments"),
    _kind("actin_cortex", "Actin cortex", "Actin cortex", "filament", "filament", CORTEX, (0.1, 1.0), ACTIN, (), (), ("cytosol",),
          "the actin cortex is a meshwork just under the plasma membrane", "#D2455B",
          cells=("animal",), cells_why="plant cells have no animal-type cortex (the wall gives their shape); bacteria have no actin"),
    _kind("stress_fiber", "Stress fiber", "Stress fibers", "filament", "filament", 10.0, (2.0, 30.0), 0.2, (), (), ("cytosol",),
          "stress fibers are bundles of actin and myosin II running across the cell between focal adhesions", "#C23B53", cells=("animal",),
          cells_why="stress fibers belong to animal cells crawling on a surface"),
    _kind("intermediate_filament", "Intermediate filament", "Intermediate filaments", "filament", "filament", 6.0, (0.5, 30.0), INTERMEDIATE,
          (), (), ("cytosol",), "intermediate filaments (vimentin, keratins) run through the cytosol from the nucleus to the cell's edge", "#5B6FD1",
          cells=("animal",), cells_why="plants and bacteria have no cytoplasmic intermediate filaments (nuclear lamins aside)"),
    _kind("kinesin", "Kinesin", "Kinesins", "complex", "motor", 0.07, (0.05, 0.08), None, (), (), (),
          "kinesin-1 walks along microtubules towards their plus end (out from the centrosome)", "#E08A2E", surfaces=("microtubule",)),
    _kind("dynein", "Dynein", "Dyneins", "complex", "motor", 0.05, (0.04, 0.06), None, (), (), (),
          "cytoplasmic dynein walks along microtubules towards their minus end (in to the centrosome)", "#B5487F", surfaces=("microtubule",),
          cells=("animal",), cells_why="flowering plants have no cytoplasmic dynein (minus-end-directed kinesins do its work)"),
    _kind("myosin", "Myosin", "Myosins", "complex", "motor", 0.035, (0.02, 0.05), None, (), (), (),
          "myosins (here myosin V) walk along actin filaments, most of them towards the plus (barbed) end", "#7E57C2",
          surfaces=_ACTIN_KINDS),
)}

#: Kind options of objects: which kinds take each.
KIND_OPTIONS: dict[str, tuple[str, ...]] = {
    "sheets": ("rough_er",), "span": ("rough_er",), "side": ("rough_er",), "cisternae": ("golgi",), "tubules": ("smooth_er",),
    "pores": ("nucleus",), "ribosomes": ("nucleus", "rough_er"), "coat": ("vesicle",),
    "cargo": ("kinesin", "dynein", "myosin"), "grana": ("chloroplast",),
}
#: Vesicle coats (``coat:``): none, or clathrin / COPI / COPII.
COAT_NAMES = ("none", "clathrin", "copi", "copii")

#: Cell kinds drawn: animal, plant and a bacterium (a rod).
CELL_KINDS: tuple[str, ...] = ("animal", "plant", "bacterium")
#: Each cell kind's long axis (µm), its long over its short axis, the sizes allowed.
CELL_SIZES: dict[str, tuple[float, float, tuple[float, float]]] = {
    "animal": (20.0, 1.25, (5.0, 100.0)),
    "plant": (32.0, 1.6, (10.0, 120.0)),
    "bacterium": (2.0, 2.5, (0.5, 10.0)),
}
CELL_SIZE, CELL_ASPECT = CELL_SIZES["animal"][:2]
CELL_SIZE_RANGE = CELL_SIZES["animal"][2]
CELL_HUE = "#E7A977"
CELL_HUES = {"animal": CELL_HUE, "plant": "#BBD08A", "bacterium": "#D9BE8C"}
MEMBRANE_HUE = "#8A5A44"
WALL_HUE = "#B9A15F"
CAPSULE_HUE = "#D8CBA4"
CELL_LABELS = {"animal": "Animal cell", "plant": "Plant cell", "bacterium": "Bacterium"}

#: The textbook cells (``contents: typical``): entry ids, kinds and how many.
TYPICAL_ANIMAL: tuple[tuple[str, str, int], ...] = (
    ("nucleus", "nucleus", 1),
    ("nucleolus", "nucleolus", 1),
    ("rough_er", "rough_er", 1),
    ("smooth_er", "smooth_er", 1),
    ("golgi", "golgi", 1),
    ("centrosome", "centrosome", 1),
    ("mitochondria", "mitochondrion", 8),
    ("lysosomes", "lysosome", 3),
    ("peroxisomes", "peroxisome", 3),
    ("early_endosomes", "early_endosome", 2),
    ("late_endosome", "late_endosome", 1),
    ("vesicles", "vesicle", 6),
    ("ribosomes", "ribosome", 90),
)
TYPICAL_PLANT: tuple[tuple[str, str, int], ...] = (
    ("vacuole", "vacuole", 1),
    ("nucleus", "nucleus", 1),
    ("nucleolus", "nucleolus", 1),
    ("rough_er", "rough_er", 1),
    ("smooth_er", "smooth_er", 1),
    ("golgi", "golgi", 1),
    ("chloroplasts", "chloroplast", 9),
    ("mitochondria", "mitochondrion", 6),
    ("peroxisomes", "peroxisome", 3),
    ("vesicles", "vesicle", 4),
    ("ribosomes", "ribosome", 80),
)
TYPICAL_BACTERIUM: tuple[tuple[str, str, int], ...] = (
    ("nucleoid", "nucleoid", 1),
    ("ribosomes", "ribosome", 260),
    ("plasmids", "plasmid", 2),
    ("flagella", "flagellum", 4),
    ("pili", "pilus", 14),
)
TYPICAL: dict[str, tuple[tuple[str, str, int], ...]] = {"animal": TYPICAL_ANIMAL, "plant": TYPICAL_PLANT, "bacterium": TYPICAL_BACTERIUM}


def main_interior(kind: Kind) -> str | None:
    """What ``in: <an entry of this kind>`` means: its innermost compartment (the nucleoplasm of
    a nucleus, the matrix of a mitochondrion), or ``None`` when it encloses none."""
    return kind.interior[-1] if kind.interior else None
