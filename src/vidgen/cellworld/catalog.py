"""What a cell world is made of (DESIGN.md §95.2): compartments, membranes, the kinds of things
placed in them with their real sizes, and where each kind may be (the location rules' data).
Plain data, no manim. Sizes are textbook-consensus values (Alberts, Molecular Biology of the
Cell; Lodish, Molecular Cell Biology) in micrometres; a drawing may stylise shapes, never sizes
or places, unless it says it is not to scale (the accuracy lint of Step 209)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Topology = Literal["cytosolic", "lumenal", "extracellular", "mitochondrial", "peroxisomal", "plastid"]
Category = Literal["structure", "complex"]

#: Thickness of a lipid bilayer (µm): about 4–5 nm.
BILAYER = 0.005
#: Space between the outer and the inner nuclear membrane (the perinuclear space, 20–40 nm).
PERINUCLEAR_GAP = 0.03
#: Space between the outer and the inner mitochondrial membrane (the intermembrane space).
MITO_GAP = 0.02
#: Lumen of a rough-ER sheet, membrane to membrane (about 30–60 nm).
ER_LUMEN = 0.05
#: Diameter of a smooth-ER tubule (about 50 nm).
ER_TUBULE = 0.05
#: A Golgi cisterna's lumen and the distance from one cisterna to the next.
GOLGI_LUMEN, GOLGI_PERIOD = 0.03, 0.09
#: Nuclear pores met per µm of nuclear envelope in a thin section (pore complexes are about
#: 120 nm across, about 10 per µm² of envelope).
PORES_PER_UM = 1.0
#: Ribosomes per µm along each cytosolic face of a rough-ER sheet in the drawing.
ER_RIBOSOMES_PER_UM = 6.0


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
    """A membrane between two compartments (``inside`` / ``outside`` are compartment names)."""

    name: str
    label: str
    outside: str
    inside: str


COMPARTMENTS: dict[str, Compartment] = {c.name: c for c in (
    Compartment("extracellular", "Extracellular space", "extracellular", "outside the plasma membrane"),
    Compartment("cytosol", "Cytosol", "cytosolic", "the fluid of the cytoplasm, around the organelles"),
    Compartment("nucleoplasm", "Nucleoplasm", "cytosolic", "inside the nucleus; joined to the cytosol through the nuclear pores"),
    Compartment("perinuclear_space", "Perinuclear space", "lumenal", "between the two nuclear membranes; continuous with the ER lumen"),
    Compartment("er_lumen", "ER lumen", "lumenal", "inside the endoplasmic reticulum"),
    Compartment("golgi_lumen", "Golgi lumen", "lumenal", "inside the Golgi cisternae"),
    Compartment("lysosome_lumen", "Lysosome lumen", "lumenal", "acidic (pH about 4.5–5), full of hydrolases"),
    Compartment("endosome_lumen", "Endosome lumen", "lumenal", "inside an endosome"),
    Compartment("vesicle_lumen", "Vesicle lumen", "lumenal", "inside a transport vesicle"),
    Compartment("intermembrane_space", "Intermembrane space", "mitochondrial", "between the outer and the inner mitochondrial membrane"),
    Compartment("matrix", "Mitochondrial matrix", "mitochondrial", "inside the inner mitochondrial membrane"),
    Compartment("peroxisome_matrix", "Peroxisomal matrix", "peroxisomal", "inside a peroxisome"),
)}

MEMBRANES: dict[str, Membrane] = {m.name: m for m in (
    Membrane("plasma_membrane", "Plasma membrane", "extracellular", "cytosol"),
    Membrane("outer_nuclear_membrane", "Outer nuclear membrane", "cytosol", "perinuclear_space"),
    Membrane("inner_nuclear_membrane", "Inner nuclear membrane", "perinuclear_space", "nucleoplasm"),
    Membrane("er_membrane", "ER membrane", "cytosol", "er_lumen"),
    Membrane("golgi_membrane", "Golgi membrane", "cytosol", "golgi_lumen"),
    Membrane("outer_mitochondrial_membrane", "Outer mitochondrial membrane", "cytosol", "intermembrane_space"),
    Membrane("inner_mitochondrial_membrane", "Inner mitochondrial membrane", "intermembrane_space", "matrix"),
    Membrane("lysosomal_membrane", "Lysosomal membrane", "cytosol", "lysosome_lumen"),
    Membrane("endosomal_membrane", "Endosomal membrane", "cytosol", "endosome_lumen"),
    Membrane("vesicle_membrane", "Vesicle membrane", "cytosol", "vesicle_lumen"),
    Membrane("peroxisomal_membrane", "Peroxisomal membrane", "cytosol", "peroxisome_matrix"),
)}

Shape = Literal["ellipse", "capsule", "sheets", "tubules", "stack", "region", "particle"]


@dataclass(frozen=True)
class Kind:
    """A kind of thing in a cell world.

    ``size`` is its default length (the long axis, µm) and ``width`` its default short axis
    (``None``: round); ``size_range`` the textbook range of the length. ``membranes`` are its own
    membranes from the outside in, ``interior`` the compartments they enclose (outermost first;
    the last is its main inside, what ``in: <id>`` means). ``places`` are the compartments it
    may be in and ``surfaces`` the kinds whose membrane it may sit on (``on:``, the cytosolic
    face); ``why`` is the textbook reason the location rules quote."""

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


def _kind(name: str, label: str, plural: str, category: Category, shape: Shape, size: float, size_range: tuple[float, float],
          width: float | None, membranes: tuple[str, ...], interior: tuple[str, ...], places: tuple[str, ...], why: str, hue: str,
          surfaces: tuple[str, ...] = ()) -> Kind:
    return Kind(name, label, plural, category, shape, size, size_range, width, membranes, interior, frozenset(places), frozenset(surfaces), why, hue)


KINDS: dict[str, Kind] = {k.name: k for k in (
    _kind("nucleus", "Nucleus", "Nuclei", "structure", "ellipse", 7.0, (5.0, 10.0), 6.0,
          ("outer_nuclear_membrane", "inner_nuclear_membrane"), ("perinuclear_space", "nucleoplasm"), ("cytosol",),
          "the nucleus lies in the cytoplasm, surrounded by cytosol", "#8E7CC3"),
    _kind("nucleolus", "Nucleolus", "Nucleoli", "structure", "region", 1.8, (1.0, 3.0), None, (), (), ("nucleoplasm",),
          "the nucleolus is a region of the nucleoplasm (it has no membrane) where ribosomal RNA is made and ribosomal subunits are assembled",
          "#5E4B9C"),
    _kind("rough_er", "Rough ER", "Rough ER", "structure", "sheets", 6.0, (2.0, 20.0), None, ("er_membrane",), ("er_lumen",), ("cytosol",),
          "rough-ER sheets spread through the cytosol from the nuclear envelope (the ER lumen is continuous with the perinuclear space)",
          "#3F8FC0"),
    _kind("smooth_er", "Smooth ER", "Smooth ER", "structure", "tubules", 3.0, (1.0, 10.0), None, ("er_membrane",), ("er_lumen",), ("cytosol",),
          "smooth-ER tubules spread through the cytosol (no ribosomes on them)", "#5FB0C8"),
    _kind("golgi", "Golgi apparatus", "Golgi stacks", "structure", "stack", 2.0, (1.0, 3.0), None, ("golgi_membrane",), ("golgi_lumen",),
          ("cytosol",), "the Golgi stack lies in the cytosol near the nucleus and the centrosome, its cis face towards the ER", "#E0A33A"),
    _kind("mitochondrion", "Mitochondrion", "Mitochondria", "structure", "capsule", 2.0, (0.5, 4.0), 0.7,
          ("outer_mitochondrial_membrane", "inner_mitochondrial_membrane"), ("intermembrane_space", "matrix"), ("cytosol",),
          "mitochondria lie in the cytosol", "#E06D4E"),
    _kind("lysosome", "Lysosome", "Lysosomes", "structure", "ellipse", 0.5, (0.1, 1.2), None, ("lysosomal_membrane",), ("lysosome_lumen",),
          ("cytosol",), "lysosomes lie in the cytosol", "#4FA35E"),
    _kind("peroxisome", "Peroxisome", "Peroxisomes", "structure", "ellipse", 0.5, (0.1, 1.0), None, ("peroxisomal_membrane",),
          ("peroxisome_matrix",), ("cytosol",), "peroxisomes lie in the cytosol", "#A3A83C"),
    _kind("endosome", "Endosome", "Endosomes", "structure", "ellipse", 0.4, (0.1, 0.8), None, ("endosomal_membrane",), ("endosome_lumen",),
          ("cytosol",), "endosomes lie in the cytosol", "#3BA8A0"),
    _kind("vesicle", "Vesicle", "Vesicles", "structure", "ellipse", 0.08, (0.04, 0.2), None, ("vesicle_membrane",), ("vesicle_lumen",),
          ("cytosol",), "transport vesicles travel through the cytosol",
          "#C77DB0"),
    _kind("centrosome", "Centrosome", "Centrosomes", "structure", "region", 1.0, (0.5, 2.0), None, (), (), ("cytosol",),
          "the centrosome (two centrioles in pericentriolar material) lies in the cytosol next to the nucleus", "#7A8BA6"),
    _kind("ribosome", "Ribosome", "Ribosomes", "complex", "particle", 0.025, (0.02, 0.03), None, (), (), ("cytosol", "matrix"),
          "ribosomes translate in the cytosol (free, or on the cytosolic face of the rough ER and the outer nuclear membrane) and, as "
          "mitochondria's own ribosomes, in the matrix; never in the nucleoplasm: their subunits are assembled in the nucleolus and leave "
          "through the nuclear pores, and translation starts only in the cytoplasm", "#3E4A9E", surfaces=("rough_er", "nucleus")),
    _kind("proteasome", "Proteasome", "Proteasomes", "complex", "particle", 0.045, (0.03, 0.05), 0.02, (), (), ("cytosol", "nucleoplasm"),
          "proteasomes break down ubiquitin-tagged proteins in the cytosol and the nucleoplasm, never inside a membrane-bounded lumen",
          "#B0574F"),
    _kind("nuclear_pore", "Nuclear pore", "Nuclear pores", "complex", "particle", 0.12, (0.1, 0.13), 0.06, (), (), (),
          "nuclear pore complexes span both membranes of the nuclear envelope, nowhere else", "#6B5AA8", surfaces=("nucleus",)),
)}

#: Cell kinds drawn so far (plant and prokaryotic cells come with the structure library).
CELL_KINDS: tuple[str, ...] = ("animal",)
#: A typical animal cell's long axis (µm) and its long over its short axis.
CELL_SIZE, CELL_ASPECT = 20.0, 1.25
CELL_SIZE_RANGE = (5.0, 100.0)
CELL_HUE = "#E7A977"
MEMBRANE_HUE = "#8A5A44"

#: The textbook animal cell (``contents: typical``): entry ids, kinds and how many.
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
    ("vesicles", "vesicle", 6),
    ("ribosomes", "ribosome", 90),
)


def main_interior(kind: Kind) -> str | None:
    """What ``in: <an entry of this kind>`` means: its innermost compartment (the nucleoplasm of
    a nucleus, the matrix of a mitochondrion), or ``None`` when it encloses none."""
    return kind.interior[-1] if kind.interior else None
