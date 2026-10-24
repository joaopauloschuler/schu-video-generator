"""Gene expression as actions, Step 206 (DESIGN.md §95.11): the genetic code, genes written,
generated and checked (introns, reading frames, signal peptides, sequons), the order of the steps,
the close-up stage's geometry (bubble, hybrid, codon–anticodon pairing, the chain N→C), the route
through a cell, validation in projects, and tiny renders."""

from __future__ import annotations

import math
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_actions import project_with, render
from vidgen.cellworld import CellSpec, build_cell_world
from vidgen.cellworld.expression import (
    BUBBLE, HYBRID, TUNNEL, ExpressionState, GeneSpec, advance, build_gene, cell_step_problem, signal_peptide_length, step_problem,
)
from vidgen.cellworld.expression_cyto import display_anticodon
from vidgen.cellworld.expression_route import RoutePlanner, route_problem
from vidgen.cellworld.expression_stage import ExpressionStage
from vidgen.cellworld.sequences import AMINO_ACIDS, CODONS, check_trna
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}
#: Preproinsulin (human INS, UniProt P01308): its signal peptide is residues 1–24.
PREPROINSULIN = ("MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVEALYLVCGERGFFYTPKTRREAEDLQVGQVELGGGPGAGSLQPLALEGSLQKRGIVEQCCTSICSLYQLENYCN")


def test_the_model_never_imports_manim() -> None:
    code = ("import sys, vidgen.cellworld.expression, vidgen.cellworld.expression_stage, vidgen.cellworld.expression_cyto, "
            "vidgen.cellworld.expression_route; print('manim' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout
    assert out.strip() == "False"


# ----- the genetic code ------------------------------------------------------------------------------


def test_the_standard_genetic_code() -> None:
    assert len(CODONS) == 64
    assert sorted(c for c, a in CODONS.items() if a == "*") == ["UAA", "UAG", "UGA"]
    degeneracy = Counter(CODONS.values())
    assert degeneracy == {"L": 6, "S": 6, "R": 6, "A": 4, "G": 4, "P": 4, "T": 4, "V": 4, "I": 3, "*": 3, "F": 2, "Y": 2, "H": 2, "Q": 2,
                          "N": 2, "K": 2, "D": 2, "E": 2, "C": 2, "M": 1, "W": 1}
    known = {"AUG": "M", "UUU": "F", "UGG": "W", "GGG": "G", "CAU": "H", "AAA": "K", "GAU": "D", "GAA": "E", "UGU": "C", "AGA": "R",
             "AGU": "S", "AUA": "I", "CUG": "L", "UAU": "Y", "CAA": "Q", "AAC": "N", "CCC": "P", "ACG": "T", "GUC": "V", "GCA": "A"}
    assert all(CODONS[c] == a for c, a in known.items())


@pytest.mark.parametrize("codon", [c for c, a in CODONS.items() if a != "*"])
def test_every_sense_codon_has_a_tRNA_that_reads_it(codon: str) -> None:
    anticodon = display_anticodon(codon)
    text, aa = check_trna(anticodon, AMINO_ACIDS[CODONS[codon]], "test")
    assert aa == CODONS[codon]
    # the anticodon pairs antiparallel: its 3′ base with the codon's 5′ base
    pair = {"A": "U", "U": "A", "G": "C", "C": "G"}
    assert anticodon[2] == pair[codon[0]] and anticodon[1] == pair[codon[1]]
    if anticodon[0] == "I":
        assert codon[2] == "U"


# ----- genes ------------------------------------------------------------------------------------------


def test_a_generated_gene() -> None:
    g = build_gene(GeneSpec(codons=10, introns=1, seed=2))
    assert g.promoter[-31:-23] == "TATAAAAG" and g.boxes[0][0] == "TATA box"
    assert g.region.startswith("A")                                  # transcription starts at a purine (initiator)
    mature = g.mature
    assert mature[g.orf_start - 6: g.orf_start + 4] == "GCCACCAUGG"[:6] + mature[g.orf_start: g.orf_start + 4]
    assert mature.find("AUG") == g.orf_start                         # the first AUG starts the frame
    assert len(g.codons) == 11 and g.codons[0] == "AUG" and g.codons[-1] in ("UAA", "UAG", "UGA")
    assert all(CODONS[c] != "*" for c in g.codons[:-1])
    (intron,) = g.introns
    seq = g.pre_mrna[intron.start:intron.end]
    assert seq.startswith("GU") and seq.endswith("AG") and g.pre_mrna[intron.branch] == "A"
    assert 18 <= intron.end - intron.branch <= 40
    assert g.pre_mrna[g.polya_signal: g.polya_signal + 6] == "AAUAAA"
    assert 10 <= g.cleavage - (g.polya_signal + 6) <= 30 and g.pre_mrna[g.cleavage - 2: g.cleavage] == "CA"
    assert len(g.mature) == g.cleavage - intron.length


def test_a_written_gene_and_its_protein() -> None:
    g = build_gene(GeneSpec(protein=PREPROINSULIN, introns=2))
    assert g.protein == PREPROINSULIN and g.signal == 24              # preproinsulin's signal peptide: 24 residues
    assert signal_peptide_length(PREPROINSULIN) == 24
    assert g.sequons == ()                                           # insulin is not glycosylated
    gs = build_gene(GeneSpec(signal_peptide=True, glycosylation=True, seed=3))
    assert gs.signal > 0 and gs.sequons and all(gs.protein[k] == "N" and gs.protein[k + 2] in "ST" for k in gs.sequons)
    seq = build_gene(GeneSpec(sequence="AGTCCATGGCCGGATGATAAGCGGCCAATAAAGCTTCCTGCCCCATGTG", protein="Met-Ala-Gly"))
    assert seq.protein == "MAG" and seq.codons[-1] == "UGA"
    b = build_gene(GeneSpec(codons=8, cell="bacterium"))
    assert [n for n, _, _ in b.boxes] == ["−35 box", "−10 box"] and b.sd is not None and not b.introns
    assert b.promoter[b.boxes[0][1]: b.boxes[0][2]] == "TTGACA" and b.promoter[b.boxes[1][1]: b.boxes[1][2]] == "TATAAT"


def with_intron(intron: str) -> GeneSpec:
    """A gene with ``intron`` after its second codon."""
    five, three = "AGTCCATGGCCGCAG", "GCTAAAGCGGCCAATAAAGCTTCCTGCCCCATG"
    return GeneSpec(sequence=five + intron + three, introns=((len(five) + 1, len(five) + len(intron)),))


@pytest.mark.parametrize("spec, message", [
    (with_intron("GCAAGT" + "C" * 8 + "CTAAC" + "T" + "CTTTCCTTCCTT" + "TCAG"), "an intron starts with GU"),
    (with_intron("GTAAGT" + "C" * 8 + "CTAAC" + "T" + "CTTTCCTTCCTT" + "TCAC"), "an intron ends with AG"),
    (with_intron("GTAAGTCTAACTCAG"), "too short"),
    (with_intron("GTCCGT" + "C" * 8 + "CTCCC" + "T" + "CTTTCCTTCCTT" + "TCAG"), "no branch-point A"),
    (GeneSpec(sequence="AGTCCAGGCCTAAGC"), "no start codon"),
    (GeneSpec(sequence="AGTCCATGGCCGCTTGCC"), "no stop codon (UAA, UAG, UGA) in frame"),
    (GeneSpec(sequence="AGTCCATGGCCGGATGATGGTAA", protein="Met-Ala-Gly-Trp"), "a stop codon UGA in frame at codon 4"),
    (GeneSpec(sequence="AGTCCATGGCCGGATGGTAA", protein="Met-Ala-Ala"), "codes Gly, not Ala"),
    (GeneSpec(protein="ALW"), "a protein starts with Met"),
    (GeneSpec(codons=10, introns=1, cell="bacterium"), "bacteria have no spliceosomal introns"),
    (GeneSpec(protein="MKKKKKKKKKKKKKKKKK", signal_peptide=True), "signal_peptide: the protein has none"),
])
def test_gene_problems(spec: GeneSpec, message: str) -> None:
    with pytest.raises(VidgenError, match=message.replace("(", r"\(").replace(")", r"\)")):
        build_gene(spec)


def test_a_premature_stop_codon_before_the_last_junction_is_refused() -> None:
    intron = "GTAAGTCCACCTTACTAACTCCCTTCTCCCTTTCAG"
    exon2 = "GCC" * 30 + "TAAGCGGCCAATAAAGCTTCCTGCCCCATGTG"
    sequence = "AGTCCATGGCCTAAGCC" + "GCC" * 20 + intron + exon2      # stop codon in exon 1, > 50 nt before the junction
    start = len("AGTCCATGGCCTAAGCC" + "GCC" * 20) + 1
    with pytest.raises(VidgenError, match="nonsense-mediated decay"):
        build_gene(GeneSpec(sequence=sequence, introns=((start, start + len(intron) - 1),)))


# ----- the order of the steps ------------------------------------------------------------------------------


def run(g: Any, steps: list[tuple[str, dict[str, object]]], state: ExpressionState | None = None) -> list[str | None]:
    state = state or ExpressionState()
    out = []
    for name, options in steps:
        problem = step_problem(g, state, name, options)
        out.append(problem)
        if problem is None:
            state = advance(g, state, name, options)
    return out


def test_the_order_of_the_steps() -> None:
    g = build_gene(GeneSpec(signal_peptide=True, glycosylation=True, introns=1))
    assert "only in the cytoplasm" in run(g, [("translate", {})])[0]
    assert "not spliced, polyadenylated" in run(g, [("transcribe", {}), ("export", {})])[1]
    whole = [("transcribe", {}), ("splice", {}), ("polyadenylate", {}), ("export", {}), ("translate", {"codons": 3}), ("target_er", {}),
             ("glycosylate", {}), ("translate", {}), ("fold", {}), ("to_golgi", {}), ("secrete", {"to": "lysosome"})]
    assert run(g, whole) == [None] * len(whole)
    assert "glycosylation happens in the ER lumen" in run(g, [*whole[:5], ("glycosylate", {})])[-1]
    assert "released already" in run(g, [*whole[:4], ("translate", {}), ("target_er", {})])[-1]
    assert "does not work in the ER lumen" in run(g, [*whole[:8], ("fold", {"chaperone": "hsp70"})])[-1]
    assert "ER quality control" in run(g, [*whole[:8], ("to_golgi", {})])[-1]
    plain = build_gene(GeneSpec(codons=12))
    assert "no signal peptide" in run(plain, [("translate", {"codons": 2}), ("target_er", {})], ExpressionState.at_start(plain, "mrna"))[1]
    short = build_gene(GeneSpec(codons=24, signal_peptide=True))
    assert "released before its signal peptide" in run(short, [("translate", {"codons": 2}), ("target_er", {})],
                                                       ExpressionState.at_start(short, "mrna"))[1]
    bact = build_gene(GeneSpec(codons=8, cell="bacterium"))
    assert "bacterial mRNAs have no 5′ cap" in run(bact, [("transcribe", {}), ("cap", {})])[1]
    assert run(bact, [("transcribe", {}), ("translate", {}), ("fold", {})]) == [None, None, None]
    # a cell scene's steps stand for the molecular ones
    state = ExpressionState()
    assert "only proteins made into the ER" in cell_step_problem(plain, ExpressionState.at_start(plain, "mrna"), "to_golgi")
    assert "shown up close in a molecule scene" in cell_step_problem(g, state, "splice")


# ----- the close-up ------------------------------------------------------------------------------------


def test_transcription_reads_the_template_and_pairs_the_rna() -> None:
    g = build_gene(GeneSpec(codons=10, introns=1, seed=2))
    stage = ExpressionStage(g, 36.0, 2.7)
    pose = stage.pose.copy()
    length = 40.0
    stage.transcribing(pose, length)
    # the bubble: ~13 bp unpaired round the active site
    unpaired = [j for j in range(len(stage.dna)) if pose.rungs[f"bp{j}"][2] < 0.5]
    assert abs(len(unpaired) - BUBBLE) <= 2
    # the RNA–DNA hybrid: 8 bp, each RNA base the complement of its template base (U for A)
    hybrid = [i for i in range(len(stage.rna)) if pose.rungs[f"h{i}"][2] > 0.5]
    assert len(hybrid) == HYBRID and hybrid[-1] == int(length) - 1
    pair = {"A": "U", "T": "A", "G": "C", "C": "G"}
    for i in hybrid:
        template = stage.template[stage.p0 + i]
        assert stage.rna[i] == pair[template] == g.region[i].replace("T", "U")
        assert pose.at(f"m{i}")[1] > pose.at(f"t{stage.p0 + i}")[1]
    # the polymerase moves right, along the template strand's 3′→5′ direction, and the RNA grows 5′→3′
    later = stage.pose.copy()
    stage.transcribing(later, length + 10)
    assert later.at("pol")[0] > pose.at("pol")[0]
    assert later.chain[0] == "m0" and len(later.chain) > len(pose.chain)


def test_every_step_plays_and_translation_grows_the_chain_n_to_c() -> None:
    g = build_gene(GeneSpec(signal_peptide=True, glycosylation=True, introns=2, seed=3))
    stage = ExpressionStage(g, 18.0, 0.5)
    steps = [("transcribe", {}), ("splice", {}), ("polyadenylate", {}), ("export", {}), ("translate", {"codons": 4}), ("target_er", {}),
             ("glycosylate", {}), ("translate", {}), ("fold", {})]
    for name, options in steps:
        clip = stage.play(name, options)
        for k in range(21):
            pose = clip.at(k / 20)
            assert all(math.isfinite(x) and math.isfinite(y) and 0.0 <= o <= 1.0 + 1e-9 for x, y, o in pose.els.values()), name
        if name == "export":
            # the mRNA is in the cytosol, 5′ (the cap) on the left, above the nuclear envelope
            assert pose.at("cap")[0] < pose.at(stage.mature_keys[-1])[0] and pose.at("cap")[1] > 10
        if name == "translate" and options:
            # the chain on the P-site tRNA; residues read N→C from the codons in order
            assert pose.readout == (4.0, 0.0)
    assert stage.state.released and stage.state.glycosylated and stage.state.folded
    end = stage.pose
    assert end.readout is not None and end.readout[0] == len(g.codons) - 1 and end.readout[1] == 1.0
    assert all(end.opacity(f"aa{k}") == 0 for k in range(g.signal))      # the signal peptide was cut off
    assert end.opacity("gly0") > 0.5 or end.opacity("gly0_0") > 0.5      # the glycan rides on its Asn


def test_codons_and_anticodons_meet_in_the_sites() -> None:
    g = build_gene(GeneSpec(codons=6, seed=4))
    stage = ExpressionStage(g, 36.0, 2.7, start="mrna")
    clip = stage.play("translate", {})
    edges = clip.edges()
    # the end of the first detailed delivery: tRNA 1 stands on codon 1 (the A site), paired
    pose = clip.at(edges[4])
    at, _ = g.codon_at(1)
    codon_mid = pose.at(stage.mature_keys[at + 1])
    assert abs(pose.at("tr1")[0] - codon_mid[0]) < 1e-6 and pose.rungs["ac1_1"][2] > 0.5
    assert stage.looks["tr1"].text == "".join(reversed(display_anticodon(g.codons[1])))


# ----- the route through a cell ------------------------------------------------------------------------


def test_the_route_through_a_cell() -> None:
    world = build_cell_world(CellSpec())
    g = build_gene(GeneSpec(signal_peptide=True, glycosylation=True))
    planner = RoutePlanner(world, g, 1, ((0.0, 0.0), 10.0))
    where = {}
    for step in ("transcribe", "export", "translate", "to_golgi", "secrete"):
        clip = planner.play(step)
        pose = clip.at(1.0)
        where[step] = [world.compartment_at(pose.at(k))[0] for k, (_, _, o) in pose.els.items() if o > 0.5 and k[0] in "mp"]
    assert set(where["transcribe"]) == {"nucleoplasm"}
    assert set(where["export"]) == {"cytosol"}
    assert {c for c in where["translate"]} >= {"er_lumen"} or "perinuclear_space" in where["translate"]
    assert all(c in ("extracellular",) for c in where["secrete"])
    assert route_problem(build_cell_world(CellSpec(contents="none")), g, "export") is not None


# ----- validation in a project ------------------------------------------------------------------------------


def problems_of(make_project: Any, scenes: list[dict[str, Any]]) -> list[str]:
    return [p.message for p in project_problems(project_with(make_project, scenes, narration=NARRATION))]


def scene(type_: str, params: dict[str, Any], actions: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {"id": "s", "type": type_, "params": params, "beats": [{"text": "the gene is expressed step by step", "actions": a} for a in actions]}


def test_gene_actions_are_validated(make_project) -> None:
    gene = {"gene": {"id": "g", "codons": 10, "introns": 1}}
    ok = [[{"transcribe": "g"}], [{"splice": "g"}], [{"polyadenylate": "g"}], [{"export": "g"}], [{"translate": "g"}], [{"fold": "g"}]]
    assert problems_of(make_project, [scene("molecule", gene, ok)]) == []
    assert any("translation starts only in the cytoplasm" in m for m in problems_of(make_project, [scene("molecule", gene, [[{"translate": "g"}]])]))
    assert any("acts on the gene: transcribe: g" in m for m in problems_of(make_project, [scene("molecule", gene, [[{"transcribe": "gene"}]])]))
    assert any("an action of cell scenes" in m for m in problems_of(make_project, [scene("molecule", gene, [[{"to_golgi": "g"}]])]))
    assert any("leave out molecules" in m for m in problems_of(make_project, [scene("molecule", {**gene, "molecules": ["atp"]}, [[]])]))
    assert any("give the scene a gene" in m for m in problems_of(make_project, [scene("molecule", {"molecules": ["atp"]}, [[{"transcribe": "atp"}]])]))
    assert any("this scene is a gene close-up" in m for m in problems_of(make_project, [scene("molecule", gene, [[{"diffuse": "g"}]])]))
    cell = {"gene": {"id": "ins", "signal_peptide": True}, "labels": False}
    route = [[{"transcribe": "ins"}], [{"export": "ins"}], [{"translate": "ins"}], [{"to_golgi": "ins"}], [{"secrete": "ins", "to": "outside"}]]
    assert problems_of(make_project, [scene("cell", cell, route)]) == []
    assert any("ER quality control" not in m and "only proteins made into the ER" in m for m in problems_of(make_project, [
        scene("cell", {"gene": {"id": "ins", "codons": 12}}, route)]))
    assert any("shown up close in a molecule scene" in m for m in problems_of(make_project, [scene("cell", cell, [[{"splice": "ins"}]])]))
    assert any("is a step of gene expression" in m for m in problems_of(make_project, [
        {"id": "b", "type": "bullets", "params": {"items": ["a"]}, "beats": [{"text": "x", "actions": [{"transcribe": "item1"}]}]}]))


# ----- renders ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_gene_close_up_renders(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [{"id": "m", "type": "molecule", "params": {"gene": {"id": "g", "codons": 5, "introns": 1}},
               "beats": [{"text": "the gene is transcribed and spliced", "actions": [{"transcribe": "g", "run_time": 1.0}, {"splice": "g", "at": 0.5, "run_time": 0.6}]},
                         {"text": "its tail is added and it leaves", "actions": [{"polyadenylate": "g", "run_time": 0.6}, {"export": "g", "at": 0.5, "run_time": 0.6}]},
                         {"text": "a ribosome translates it", "actions": [{"translate": "g", "run_time": 1.2}]}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 2.0})))
    scene_ = render(project, "m", media, size)
    assert scene_.stage.state.released and scene_.stage.pose.readout[0] == 5
    assert scene_.drawing.state["aa0"][2] > 0                       # the protein is drawn


@pytest.mark.render
def test_gene_route_renders(make_project, media: Path) -> None:
    scenes = [{"id": "c", "type": "cell", "params": {"labels": False, "gene": {"id": "ins", "signal_peptide": True}},
               "beats": [{"text": "made and exported", "actions": [{"transcribe": "ins", "run_time": 0.6}, {"export": "ins", "at": 0.5, "run_time": 0.6}]},
                         {"text": "translated on the ER and sent to the Golgi", "actions": [{"translate": "ins", "run_time": 0.6}, {"to_golgi": "ins", "at": 0.5, "run_time": 0.6}]},
                         {"text": "secreted", "actions": [{"secrete": "ins", "run_time": 0.8}]}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 2.0})))
    scene_ = render(project, "c", media, (160, 90))
    world = scene_.world
    pose = scene_._planner.pose
    assert all(world.compartment_at(pose.at(k))[0] == "extracellular" for k, (_, _, o) in pose.els.items() if o > 0.5 and k.startswith("p"))
