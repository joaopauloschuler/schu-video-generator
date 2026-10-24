"""Molecules and notation, Step 204 (DESIGN.md §95.9): chemical notation, gene and protein
nomenclature, modification markers and histone marks, sequences and the genetic code, the
molecule catalog's placement and orientation rules, the glyphs' facts (antiparallel DNA, a
GPCR's N-terminus outside, F₁ on the N side), molecules in a cell world, and the ``molecule``
scene (params, errors, tiny renders)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import render
from vidgen import extensions, registry
from vidgen.cellworld import BILAYER, CellSpec, ObjectSpec, build_cell_world, level_view, part_anchors
from vidgen.cellworld.glyphs import MoleculeSpec, check_molecule, membrane_glyph_ok, molecule_glyph
from vidgen.cellworld.molecules import MOLECULES, check_faces, check_membrane, check_place, membrane_sides, protein_size
from vidgen.cellworld.names import check_gene, check_modification, check_protein, gene_markup, histone_mark
from vidgen.cellworld.notation import charge_of, check_markup, chem_markup, chem_plain
from vidgen.cellworld.sequences import check_sequence, check_trna, codons_read, reverse_complement
from vidgen.errors import VidgenError
from vidgen.project import Project

# ----- notation ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("text, markup, plain", [
    ("Ca2+", "Ca<sup>2+</sup>", "Ca²⁺"), ("Na+", "Na<sup>+</sup>", "Na⁺"), ("Cl-", "Cl<sup>−</sup>", "Cl⁻"), ("H+", "H<sup>+</sup>", "H⁺"),
    ("H2O", "H<sub>2</sub>O", "H₂O"), ("HCO3-", "HCO<sub>3</sub><sup>−</sup>", "HCO₃⁻"), ("SO4 2-", "SO<sub>4</sub><sup>2−</sup>", "SO₄²⁻"),
    ("Pi", "P<sub>i</sub>", "Pᵢ"), ("NAD+", "NAD<sup>+</sup>", "NAD⁺"), ("cAMP", "cAMP", "cAMP"), ("F_o", "F<sub>o</sub>", "Fₒ"),
])
def test_chemical_notation(text: str, markup: str, plain: str) -> None:
    assert chem_markup(text) == markup and chem_plain(text) == plain


def test_charges_and_markup_checks() -> None:
    assert charge_of("Ca2+") == 2 and charge_of("Cl-") == -1 and charge_of("HCO3-") == -1 and charge_of("glucose") == 0
    assert check_markup("β<sub>2</sub>-adrenergic <i>ADRB2</i>", "label")
    with pytest.raises(VidgenError, match="<sub> is not closed"):
        check_markup("Ca<sub>2", "label")


# ----- names -------------------------------------------------------------------------------------------


def test_gene_symbols_by_species() -> None:
    assert gene_markup("TP53", "human", "g") == "<i>TP53</i>" and check_gene("Trp53", "mouse", "g") == "Trp53"
    assert check_gene("CDC28", "yeast", "g") and check_gene("lacZ", "e_coli", "g") and check_gene("C9orf72", "human", "g")
    with pytest.raises(VidgenError, match="human gene symbols are italic capitals.*write TP53"):
        check_gene("Tp53", "human", "g")
    with pytest.raises(VidgenError, match="mouse gene symbols.*first letter a capital.*write Trp53"):
        check_gene("TRP53", "mouse", "g")
    with pytest.raises(VidgenError, match="species 'mose'.*did you mean 'mouse'"):
        check_gene("Trp53", "mose", "g")


def test_protein_names_are_not_gene_symbols() -> None:
    assert check_protein("p53", "human", "p") == "p53" and check_protein("TRP53", "mouse", "p", "Trp53") == "TRP53"
    assert check_protein("Cdc28", "yeast", "p") and check_protein("Gαs", "human", "p")
    with pytest.raises(VidgenError, match="written like the mouse gene.*write TRP53"):
        check_protein("Trp53", "mouse", "p", "Trp53")
    with pytest.raises(VidgenError, match="budding-yeast proteins.*write Cdc28"):
        check_protein("CDC28", "yeast", "p")
    with pytest.raises(VidgenError, match="write LacZ"):
        check_protein("lacZ", "e_coli", "p")


def test_modifications_go_on_their_residues() -> None:
    assert check_modification("P", "Ser15", "m")[1] == ("S", 15) and check_modification("Ac", "K382", "m")[1] == ("K", 382)
    assert check_modification("Me", "R3", "m") and check_modification("Ub", None, "m")[1] is None
    with pytest.raises(VidgenError, match=r"phosphorylation \(P\) is on Ser, Thr or Tyr.*not on Lys382"):
        check_modification("P", "K382", "m")
    with pytest.raises(VidgenError, match="modification 'Ph'.*did you mean 'P'"):
        check_modification("Ph", "S1", "m")
    with pytest.raises(VidgenError, match="residue 'Serine15'"):
        check_modification("P", "Serine15", "m")


@pytest.mark.parametrize("mark, ok", [("H3K4me3", True), ("H3K27ac", True), ("H3K9me2", True), ("H4K16ac", True), ("H2AK119ub", True),
                                      ("H3S10ph", True), ("H2BK120ub", True), ("H3S27ph", False), ("H3K10ac", False), ("H3R2me3", False)])
def test_histone_marks_match_the_histone_sequences(mark: str, ok: bool) -> None:
    if ok:
        histone_mark(mark, "marks")
    else:
        with pytest.raises(VidgenError):
            histone_mark(mark, "marks")
    with pytest.raises(VidgenError, match="residue 10 of H3 is Ser"):
        histone_mark("H3K10ac", "marks")


# ----- sequences ---------------------------------------------------------------------------------------


def test_sequences_and_the_genetic_code() -> None:
    assert check_sequence("atg cgt", "dna", "s") == "ATGCGT" and reverse_complement("ATGC") == "GCAT"
    with pytest.raises(VidgenError, match="'U' at 3 is not a DNA base.*DNA has T where RNA has U"):
        check_sequence("ACUG", "dna", "s")
    assert codons_read("CAU") == ["AUG"] and set(codons_read("GAA")) == {"UUC", "UUU"} and set(codons_read("IGC")) == {"GCU", "GCC", "GCA"}
    assert check_trna("CAU", "Met", "t") == ("CAU", "M") and check_trna("GAA", "Phe", "t")[1] == "F"
    with pytest.raises(VidgenError, match=r"anticodon 5′-CAU-3′ reads the codons AUG \(Met\), none of them Phe"):
        check_trna("CAU", "Phe", "t")
    with pytest.raises(VidgenError, match="I only at the first"):
        check_trna("CIU", None, "t")


# ----- the catalog's rules --------------------------------------------------------------------------------


def test_membrane_sides_and_placement_rules() -> None:
    assert membrane_sides("plasma_membrane") == ("extracellular", "cytosol")
    assert membrane_sides("inner_mitochondrial_membrane") == ("intermembrane_space", "matrix")
    assert membrane_sides("thylakoid_membrane") == ("thylakoid_lumen", "stroma")
    assert membrane_sides("bacterial_inner_membrane") == ("periplasm", "cytosol")
    synthase, gpcr = MOLECULES["atp_synthase"], MOLECULES["gpcr"]
    check_membrane(synthase, "thylakoid_membrane", "m")
    with pytest.raises(VidgenError, match="is not in the plasma membrane: ATP synthase sits in the inner mitochondrial membrane"):
        check_membrane(synthase, "plasma_membrane", "m")
    with pytest.raises(VidgenError, match="not in the thylakoid membrane: GPCRs sit in the plasma membrane"):
        check_membrane(gpcr, "thylakoid_membrane", "m")
    check_faces(synthase, "inner_mitochondrial_membrane", "matrix", "m")
    with pytest.raises(VidgenError, match="ATP synthase F₁ must face the mitochondrial matrix, not the intermembrane space"):
        check_faces(synthase, "inner_mitochondrial_membrane", "intermembrane_space", "m")
    with pytest.raises(VidgenError, match="F₁ must face the stroma, not the thylakoid lumen"):
        check_faces(synthase, "thylakoid_membrane", "thylakoid_lumen", "m")
    with pytest.raises(VidgenError, match="N-terminus must face the extracellular space, not the cytosol"):
        check_faces(gpcr, "plasma_membrane", "cytosol", "m")
    with pytest.raises(VidgenError, match="lies between the extracellular space and the cytosol"):
        check_faces(gpcr, "plasma_membrane", "matrix", "m")
    check_place(MOLECULES["dna"], "matrix", "m")
    with pytest.raises(VidgenError, match="DNA in the cytosol: DNA is in the nucleus"):
        check_place(MOLECULES["dna"], "cytosol", "m")
    assert 4.5 < protein_size(50) < 5.5                                   # a 50 kDa protein is about 5 nm across


def test_molecule_options_are_checked() -> None:
    with pytest.raises(VidgenError, match="anticodon is for trna, not DNA"):
        check_molecule(MoleculeSpec("dna", anticodon="CAU"))
    with pytest.raises(VidgenError, match="state 'opened' of Ion channel: use closed, open, inactivated; did you mean 'open'"):
        check_molecule(MoleculeSpec("ion_channel", state="opened"))
    with pytest.raises(VidgenError, match="a symporter moves its solutes the same way"):
        check_molecule(MoleculeSpec("carrier", mode="symport", substrates=("Na+", "glucose"), moves=("in", "out")))
    with pytest.raises(VidgenError, match="a uniporter moves one solute"):
        check_molecule(MoleculeSpec("carrier", mode="uniport", substrates=("Na+", "glucose")))
    with pytest.raises(VidgenError, match="an ion needs ion"):
        check_molecule(MoleculeSpec("ion"))
    with pytest.raises(VidgenError, match="modification on domain 'SH4'"):
        check_molecule(MoleculeSpec("protein", domains=("SH2", "SH3"), modifications=(("P", "Y416", "SH4"),)))


# ----- glyph facts ------------------------------------------------------------------------------------------


def test_dna_is_antiparallel_with_grooves() -> None:
    g = molecule_glyph(check_molecule(MoleculeSpec("dna", sequence="ATGCGTACCGGATCGTTAGCAATG")))
    assert g.facts["strands"] == (("5′", "3′", 1), ("3′", "5′", -1))                    # antiparallel
    assert g.facts["partner"] == "TACGCATGGCCTAGCAATCGTTAC"                          # A–T, G–C under each base
    assert g.facts["length"] == pytest.approx(24 * 0.34)
    gaps = sorted(set(g.facts["gaps"]))
    assert gaps[0] == pytest.approx(1.25, abs=0.02) and gaps[-1] == pytest.approx(2.32, abs=0.02)   # minor and major groove
    five, three = g.anchors["five_prime"][1], g.anchors["three_prime"][1]
    assert five[0] < three[0]
    assert {"major_groove", "minor_groove", "base_pair", "backbone"} <= set(g.anchors)
    texts = [p.text for p in g.prims if p.text]
    assert texts.count("5′") == 2 and texts.count("3′") == 2


def test_membrane_proteins_are_oriented() -> None:
    gpcr = molecule_glyph(check_molecule(MoleculeSpec("gpcr", ligand=True)))
    assert gpcr.facts["n_terminus"][1] > BILAYER * 1000 / 2 and gpcr.facts["c_terminus"][1] < -BILAYER * 1000 / 2   # N out, C in
    assert gpcr.facts["helices"] == 7 and membrane_glyph_ok(gpcr)
    synthase = molecule_glyph(check_molecule(MoleculeSpec("atp_synthase", membrane="thylakoid_membrane")))
    assert synthase.facts["f1_center"][1] < -5 and synthase.facts["c"] == 14                          # F₁ on the N side; c14 in chloroplasts
    assert molecule_glyph(MoleculeSpec("atp_synthase", membrane="inner_mitochondrial_membrane")).facts["c"] == 8
    pump = molecule_glyph(MoleculeSpec("na_k_atpase"))
    assert (pump.facts["na_out"], pump.facts["k_in"], pump.facts["atp"]) == (3, 2, 1)
    closed, opened = molecule_glyph(MoleculeSpec("ion_channel", state="closed")), molecule_glyph(MoleculeSpec("ion_channel", state="open"))
    assert opened.facts["gate_gap"] > 1.0 > closed.facts["gate_gap"] and opened.facts["flow"] == "out"   # K⁺ leaves the cell
    assert molecule_glyph(MoleculeSpec("g_protein", state="active")).facts["nucleotide"] == "GTP"
    assert molecule_glyph(MoleculeSpec("g_protein")).facts["nucleotide"] == "GDP"
    assert molecule_glyph(MoleculeSpec("carrier", mode="antiport")).facts["moves"] == ("in", "out")
    nuc = molecule_glyph(check_molecule(MoleculeSpec("nucleosome", marks=("H3K4me3", "H3K27ac"))))
    assert nuc.facts["bp"] == 147 and nuc.facts["turns"] == 1.65 and nuc.facts["handedness"] == "left"


def test_every_kind_has_a_glyph() -> None:
    for name in MOLECULES:
        spec = check_molecule(MoleculeSpec(name, ion="Ca2+" if name == "ion" else None))
        g = molecule_glyph(spec)
        assert g.prims and g.anchors and g.bounds[2] > g.bounds[0], name
        if MOLECULES[name].family == "membrane":
            assert membrane_glyph_ok(g), name


def test_modification_markers_sit_on_their_domain() -> None:
    spec = check_molecule(MoleculeSpec("protein", domains=("SH3", "SH2", "kinase"), modifications=(("P", "Y419", "kinase"), ("P", "Y530", None))))
    g = molecule_glyph(spec)
    kinase = g.anchors["domain_3"][1]
    marker = g.anchors["mod_1"][1]
    assert abs(marker[0] - kinase[0]) < 0.5 and g.anchors["mod_1"][0] == "Phosphorylation (Y419)"


# ----- molecules in a cell world -------------------------------------------------------------------------


def world(*objects: ObjectSpec, **cell: Any) -> Any:
    return build_cell_world(CellSpec(objects=tuple(objects), **cell))


def test_membrane_proteins_in_a_cell_face_the_right_way() -> None:
    w = world(ObjectSpec("gpcr", id="r", on="cell", count=3), ObjectSpec("atp_synthase", id="s", on="mitochondria", count=4))
    for r in w.members("r"):
        n = r.normal
        assert w.compartment_at((r.center[0] + n[0] * 0.01, r.center[1] + n[1] * 0.01))[0] == "extracellular"   # its exoplasmic side out
        assert r.option("membrane") == "plasma_membrane"
    for s in w.members("s"):
        n = s.normal
        assert s.option("membrane") == "inner_mitochondrial_membrane"
        assert w.compartment_at((s.center[0] - n[0] * 0.008, s.center[1] - n[1] * 0.008))[0] == "matrix"         # F₁ in the matrix
        assert w.compartment_at((s.center[0] + n[0] * 0.008, s.center[1] + n[1] * 0.008))[0] == "intermembrane_space"
    plant = world(ObjectSpec("atp_synthase", id="cf", on="chloroplasts", count=2), kind="plant")
    for s in plant.members("cf"):
        n = s.normal
        assert plant.compartment_at((s.center[0] - n[0] * 0.006, s.center[1] - n[1] * 0.006))[0] == "stroma"
    dna = world(ObjectSpec("dna", id="d", inside="nucleus", count=3))
    assert all(dna.compartment_at(t.center)[0] == "nucleoplasm" for t in dna.members("d"))


@pytest.mark.parametrize("spec, cell, message", [
    (ObjectSpec("atp_synthase", on="mitochondria", faces="intermembrane_space"), "animal", "ATP synthase F₁ must face the mitochondrial matrix"),
    (ObjectSpec("atp_synthase"), "animal", "ATP synthase is not in the plasma membrane"),
    (ObjectSpec("gpcr", on="cell", faces="cytosol"), "animal", "N-terminus must face the extracellular space"),
    (ObjectSpec("na_k_atpase", on="cell"), "plant", "plant and fungal cells use H⁺-ATPases"),
    (ObjectSpec("gpcr", inside="cytosol"), "animal", "sits in a membrane: give on: cell"),
    (ObjectSpec("gpcr", at=(1.0, 1.0)), "animal", "is placed in its membrane with on"),
    (ObjectSpec("dna", inside="cytosol"), "animal", "a DNA cannot be in the cytosol: DNA is in the nucleus"),
    (ObjectSpec("nucleosome", inside="cytosol"), "bacterium", "bacteria have no histones"),
    (ObjectSpec("gpcr", on="mitocondria"), "animal", "on: 'mitocondria' is not an object of this cell; did you mean 'mitochondria'"),
    (ObjectSpec("atp_synthase", on="mitochondria", membrane="middle"), "animal", "membrane 'middle'"),
    (ObjectSpec("gpcr", on="cell", state="open"), "animal", "state 'open' of G-protein-coupled receptor: use inactive, active"),
    (ObjectSpec("dna", faces="matrix"), "animal", "faces is for"),
])
def test_molecule_rules_in_a_cell(spec: ObjectSpec, cell: str, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        world(spec, kind=cell)


def test_a_molecule_view_names_its_parts() -> None:
    w = world(ObjectSpec("atp_synthase", id="s", on="mitochondria"))
    view = level_view(w, "complex", 16 / 9 * 0.8, "s")
    assert 0.03 < view.span < 0.12                                       # about twice the molecule (22 nm)
    anchors = {a.name: a for a in part_anchors(w, "s", view, (view.span, view.span))}
    assert {"f1", "fo", "stalk"} <= set(anchors) and anchors["f1"].label.startswith("F<sub>1</sub>")
    s = w.thing("s")
    f1 = anchors["f1"].point
    assert (f1[0] - s.center[0]) * s.normal[0] + (f1[1] - s.center[1]) * s.normal[1] < -0.005      # F₁ on the matrix side
    assert w.compartment_at(anchors["matrix"].point)[0] == "matrix"


# ----- the molecule scene ----------------------------------------------------------------------------------


def molecule_cls() -> Any:
    extensions.load_builtins()
    return registry.get("molecule").cls


def test_molecule_params_and_targets() -> None:
    cls = molecule_cls()
    p = cls.validate_params({"title": "T", "membrane": "inner_mitochondrial", "molecules": ["atp_synthase", {"kind": "atp", "in": "matrix"},
                                                                                           {"kind": "ion", "ion": "H+", "in": "intermembrane_space"}]})
    placed = p.placed()
    assert [m.id for m in placed] == ["atp_synthase", "atp", "ion"]
    assert placed[1].center[1] < 0 < placed[2].center[1]                 # the matrix below the membrane, the intermembrane space above
    assert cls.target_names(p) == ["title", "membrane", "atp_synthase", "atp", "ion", "scale_bar"]


@pytest.mark.parametrize("params, message", [
    ({"molecules": ["gpcr"]}, "a G-protein-coupled receptor sits in a membrane: give the scene a membrane"),
    ({"membrane": "plasma", "molecules": [{"kind": "atp_synthase"}]}, "is not in the plasma membrane"),
    ({"membrane": "inner_mitochondrial", "molecules": [{"kind": "atp_synthase", "faces": "intermembrane_space"}]}, "F₁ must face the mitochondrial matrix"),
    ({"membrane": "plasma", "molecules": [{"kind": "atp", "in": "matrix"}]}, "this membrane lies between the extracellular and the cytosol"),
    ({"molecules": [{"kind": "dna"}]}, "DNA in the cytosol: DNA is in the nucleus"),
    ({"compartment": "nucleoplasm", "molecules": [{"kind": "dna", "gene": "Tp53"}]}, "write TP53"),
    ({"species": "mouse", "molecules": [{"kind": "protein", "gene": "Trp53", "protein": "Trp53"}]}, "write TRP53"),
    ({"molecules": [{"kind": "trna", "anticodon": "CAU", "amino_acid": "Phe"}]}, "none of them Phe"),
    ({"compartment": "nucleoplasm", "molecules": [{"kind": "nucleosome", "marks": ["H3S27ph"]}]}, "residue 27 of H3 is Lys"),
    ({"molecules": [{"kind": "protein", "modifications": [{"mark": "P", "at": "K12"}]}]}, "phosphorylation"),
    ({"membrane": "plasm"}, "membrane 'plasm'.*did you mean 'plasma'"),
    ({"molecules": [{"kind": "gpcrr"}]}, "unknown molecule 'gpcrr'.*did you mean 'gpcr'"),
    ({"membrane": "plasma", "cell": "plant", "molecules": ["na_k_atpase"]}, "H⁺-ATPases"),
    ({"membrane": "thylakoid", "molecules": ["nucleosome"]}, "Nucleosome in the stroma: nucleosomes package the DNA of the eukaryotic nucleus"),
])
def test_molecule_params_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        molecule_cls().validate_params(params)


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_molecule_scene_renders(size: tuple[int, int], make_project, media: Path) -> None:
    config = {"id": "m", "type": "molecule", "params": {"title": "Pump", "membrane": "plasma",
                                                       "molecules": [{"kind": "na_k_atpase"}, {"kind": "gpcr", "ligand": True, "gene": "ADRB2"}]},
              "beats": [{"text": "The sodium pump moves three sodium ions out"}]}
    project = Project.load(make_project(minimal_config(scenes=[config], narration={"pad": 0.2, "words_per_second": 4.0})))
    scene = render(project, "m", media, size)
    names = {name for t in scene.targets for name in t.names}
    assert {"title", "membrane", "na_k_atpase", "gpcr", "scale_bar"} <= names
    assert scene.unit > 0 and math.isfinite(scene.span)
