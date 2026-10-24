"""Step 211 (review of Phase U): short step captions, context-aware SNAREs, gene symbols in italics
in the captions, the pathway templates' inhibitory phosphorylations, fusion framing, the
untangled label rows. Logic only, no rendering."""

from __future__ import annotations

import numpy as np
import pytest

from vidgen.cellworld import CellSpec, build_cell_world, level_view
from vidgen.cellworld.captions import note_text, short_note
from vidgen.cellworld.expression_route import curve
from vidgen.cellworld.names import gene_spans
from vidgen.cellworld.pathway import build_pathway, signal_waves
from vidgen.cellworld.pathway_templates import TEMPLATES
from vidgen.cellworld.traffic import EXO_STEPS, exocytosis_steps


# ----- captions -------------------------------------------------------------------------------------


def test_short_note_keeps_the_statement() -> None:
    full = ("TFIIH unwinds the DNA at the start site (+1): a transcription bubble of ~13 bp; TFIIH's kinase "
            "phosphorylates Ser5 of the polymerase's C-terminal domain (CTD)")
    assert short_note(full) == "TFIIH unwinds the DNA at the start site (+1)"
    # a break inside parentheses or markup is not a clause break
    assert short_note("Glc<sub>3</sub>: sugars (a: b) here") == "Glc<sub>3</sub>: sugars (a: b) here"
    # a very short first clause takes the next one with it
    assert short_note("First transesterification: the branch-point A attacks the 5′ splice site — a lariat") \
        == "First transesterification: the branch-point A attacks the 5′ splice site"
    assert short_note("No break here at all") == "No break here at all"


@pytest.mark.parametrize("mode, tall, short", [("auto", True, True), ("auto", False, False), (True, True, False),
                                               ("full", True, False), ("short", False, True)])
def test_note_modes(mode: object, tall: bool, short: bool) -> None:
    note = "Dynamin hydrolyses GTP and pinches the vesicle off: scission; the coat comes away"
    out = note_text(note, mode, tall)  # type: ignore[arg-type]
    assert out == (short_note(note) if short else note)
    assert note_text(note, False, tall) is None
    assert note_text("", "auto", tall) is None


# ----- SNAREs ---------------------------------------------------------------------------------------


def test_exocytosis_names_the_snares_of_its_context() -> None:
    generic = " ".join(t for _, t in exocytosis_steps())
    assert "synaptobrevin" not in generic and "SNAP-25" not in generic and "v-SNARE" in generic
    assert EXO_STEPS == exocytosis_steps("generic")
    constitutive = " ".join(t for _, t in exocytosis_steps("constitutive"))
    assert "syntaxin-4" in constitutive and "SNAP-23" in constitutive and "SNAP-25" not in constitutive
    neuronal = " ".join(t for _, t in exocytosis_steps("neuronal"))
    assert "synaptobrevin" in neuronal and "syntaxin-1" in neuronal and "synaptotagmin" in neuronal and "Ca²⁺" in neuronal


def test_exocytosis_snares_option_is_checked() -> None:
    from vidgen.scenes.cell_actions import Exocytosis

    assert Exocytosis.Options(snares="constitutive").snares == "constitutive"
    assert Exocytosis.Options().snares == "generic" and Exocytosis.Options().notes == "auto"
    with pytest.raises(ValueError):
        Exocytosis.Options(snares="hepatic")


# ----- gene symbols ---------------------------------------------------------------------------------


def test_gene_spans_italic_genes_not_proteins() -> None:
    text = "transcription of SERPINA1. The SERPINA1 protein; Serpina1 is the mouse gene"
    spans = gene_spans(text, {"SERPINA1"})
    assert [text[a:b] for a, b in spans] == ["SERPINA1"] and spans[0][0] == text.index("SERPINA1")
    assert gene_spans("EGFR kinase and EGFR", {"EGFR"}) == [(16, 20)]
    assert gene_spans("TP53TG and TP53", {"TP53"}) == [(11, 15)]       # whole words only
    assert gene_spans("nothing here", set()) == []


def test_scene_types_declare_their_genes() -> None:
    from vidgen.scenes.cell import Cell
    from vidgen.scenes.molecule import Molecule
    from vidgen.scenes.pathway import PathwayScene

    pathway = PathwayScene.parse_params({"template": "pi3k_akt"}, "p")
    assert PathwayScene.gene_symbols(pathway) == ["BCL2L11"]
    cell = Cell.parse_params({"gene": {"name": "SERPINA1", "signal_peptide": True}}, "c")
    assert Cell.gene_symbols(cell) == ["SERPINA1"]
    mol = Molecule.parse_params({"molecules": [{"kind": "protein", "gene": "TP53", "protein": "p53"}]}, "m")
    assert Molecule.gene_symbols(mol) == ["TP53"]


# ----- pathways -------------------------------------------------------------------------------------


def test_inhibitory_phosphorylations_are_drawn_and_played_as_inhibition() -> None:
    p = build_pathway(TEMPLATES["pi3k_akt"])
    arcs = {(e.source, e.target): e for e in p.edges}
    for pair in (("akt", "gsk3b"), ("akt", "tsc2"), ("akt", "foxo")):
        e = arcs[pair]
        assert e.type.name == "phosphorylates" and e.type.mark == "P" and e.sign < 0      # a T-bar with a P on it
    assert arcs[("pdk1", "akt")].sign > 0 and arcs[("mtorc2", "akt")].sign > 0               # Thr308, Ser473 activate
    assert arcs[("pten", "pip3")].sign < 0 and arcs[("tsc2", "rheb")].sign < 0
    effect = {(s.edge.source, s.edge.target): s.effect for wave in signal_waves(p, ["gf"]) for s in wave}
    assert effect[("akt", "gsk3b")] == -1 and effect[("akt", "foxo")] == -1
    assert effect[("tsc2", "rheb")] == 1 and effect[("rheb", "mtorc1")] == 1          # Akt ⊣ TSC2 ⊣ Rheb → mTORC1 on
    assert effect[("foxo", "bcl2l11")] == -1                                           # FOXO off: BCL2L11 falls
    mapk = {(e.source, e.target): e for e in build_pathway(TEMPLATES["rtk_ras_mapk"]).edges}
    assert mapk[("erk", "sos")].sign < 0 and mapk[("erk", "sos")].feedback and mapk[("rasgap", "ras")].sign < 0
    camp = {(e.source, e.target): e for e in build_pathway(TEMPLATES["gpcr_camp_pka"]).edges}
    assert camp[("pka", "pde")].sign > 0 and camp[("pka", "pde")].feedback and camp[("pde", "camp")].sign < 0


# ----- framing and paths ----------------------------------------------------------------------------


def test_a_vesicle_by_the_membrane_is_framed_with_it() -> None:
    from vidgen.cellworld.model import ObjectSpec as Obj

    world = build_cell_world(CellSpec(objects=(Obj(kind="vesicle", id="sv", at=(0.0, 7.7), size=0.1),)))
    wide = level_view(world, "complex", 16 / 9, "sv")
    tall = level_view(world, "complex", 9 / 16, "sv")
    # centred between the vesicle and just outside the membrane (y = 8 at the top of the cell)
    assert 7.7 < wide.center[1] < 8.05 and abs(wide.center[0]) < 0.01
    assert tall.span < wide.span * 1.2 and wide.span < 1.0       # both frame the event, not the cell


def test_products_take_gentle_curves() -> None:
    a, b = (0.0, 0.0), (4.0, 0.0)
    assert curve(a, b, 0.0) == a and np.allclose(curve(a, b, 1.0), b)
    mid = curve(a, b, 0.5, 0.1)
    assert mid[0] == pytest.approx(2.0) and mid[1] == pytest.approx(0.4)


def test_label_rows_untangle() -> None:
    from vidgen.scenes.cell import _leader_x, _untangle

    # an inner wide label over the anchor of an outer label's leader: they change rows, then the
    # narrow one steps aside
    inner = (1, np.array([0.0, 0.0, 0.0]), 6.0, 0.4)
    outer = (2, np.array([-0.5, 0.0, 0.0]), 2.0, 0.4)
    spots = {1: np.array([0.0, 1.0, 0.0]), 2: np.array([-0.5, 1.6, 0.0])}
    _untangle([[inner], [outer]], spots, -3.6, 3.6)

    def crosses(k_in: int, k_out: int, w_in: float, w_out: float, a_out: np.ndarray) -> bool:
        x = _leader_x(a_out, spots[k_out], w_out, 0.4, float(spots[k_in][1]))
        return x is not None and abs(x - spots[k_in][0]) < w_in / 2

    lower, upper = sorted((1, 2), key=lambda k: spots[k][1])
    widths, anchors = {1: 6.0, 2: 2.0}, {1: inner[1], 2: outer[1]}
    assert not crosses(lower, upper, widths[lower], widths[upper], anchors[upper])
