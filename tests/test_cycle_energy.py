"""Step 208: the cell cycle, cell division and energy metabolism — the models checked against the
textbook (phase order and lengths, the order in which the cyclins rise and fall, the restriction
point and G0, the checkpoints; chromosome and chromatid counts through mitosis and meiosis,
crossing over and independent assortment; glycolysis and citric acid cycle tallies, protons per
two electrons along the chains), the rules with their messages, the actions' replay in
projects, and tiny renders in 16:9 and 9:16."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_actions import project_with, render
from vidgen.cellworld import cycle as cy
from vidgen.cellworld import division as dv
from vidgen.cellworld import energy as en
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}


# ----- the cell cycle --------------------------------------------------------------------------------


def test_phases_in_order_with_their_lengths() -> None:
    geo = cy.cycle_geometry()
    starts = [geo.bounds[k][0] for k in cy.PHASE_KEYS]
    assert starts == sorted(starts) and geo.bounds["m"][1] == 1.0
    assert geo.bounds["m"][1] - geo.bounds["m"][0] == pytest.approx(cy.M_MIN_SHARE)      # M widened to be seen
    g1, s, g2 = (geo.bounds[k][1] - geo.bounds[k][0] for k in ("g1", "s", "g2"))
    assert g1 / s == pytest.approx(11 / 8) and s / g2 == pytest.approx(8 / 4)            # the others keep their proportions
    assert 0 < geo.points["restriction_point"] < geo.points["g1_s"]
    names = [n for n, _ in cy.M_STAGES]
    assert [geo.points[n] for n in names] == sorted(geo.points[n] for n in names)
    assert geo.stage_at(geo.points["metaphase"] + 1e-4) == "metaphase" and geo.stage_at(0.5) == "s"
    long_g1 = cy.cycle_geometry({"g1": 30})
    assert long_g1.bounds["g1"][1] > geo.bounds["g1"][1]
    with pytest.raises(VidgenError, match="unknown phase 'g3'"):
        cy.cycle_geometry({"g3": 2})


def test_cyclins_rise_and_fall_in_textbook_order() -> None:
    geo = cy.cycle_geometry()
    c = cy.cyclins(geo)

    def peak(key: str) -> float:
        return max((k / 400 for k in range(400)), key=lambda t: c[key].level(t))

    assert peak("e") == pytest.approx(geo.points["g1_s"], abs=0.02)            # cyclin E at G1/S
    assert geo.bounds["s"][1] < peak("a") <= geo.points["prometaphase"] + 0.01  # A peaks at G2/M, gone by metaphase
    assert geo.points["metaphase"] <= peak("b") < geo.points["anaphase"]          # B peaks at metaphase…
    assert c["b"].level(geo.points["telophase"]) < 0.2 < c["b"].level(geo.points["anaphase"] - 0.003)   # …and falls at anaphase
    assert c["e"].level(geo.bounds["s"][0] + 0.6 * (geo.bounds["s"][1] - geo.bounds["s"][0])) < 0.1     # E degraded in early S
    assert c["a"].level(geo.points["metaphase"] + 0.002) < 0.1
    assert c["d"].level(0.6) > 0.4 and c["d"].level(0.02) < 0.2                   # D up with mitogens through the cycle
    for key in cy.CYCLIN_KEYS:
        assert c[key].level(0.0) == pytest.approx(c[key].level(0.99999), abs=0.02)   # continuous round the cycle
        assert all(0.0 <= c[key].level(k / 200) <= 1.0 for k in range(200))


def test_advance_and_checkpoint_rules() -> None:
    geo = cy.cycle_geometry()
    st = cy.CycleState()
    assert cy.advance_problem(geo, st, "g0", 0) is None
    in_s = cy.advance(geo, st, "s", 0.5)
    assert in_s.t == pytest.approx(geo.bounds["s"][0] + 0.5 * (geo.bounds["s"][1] - geo.bounds["s"][0]))
    assert "before the restriction point" in cy.advance_problem(geo, in_s, "g0", 0)
    late = cy.advance(geo, st, "restriction_point", 0)
    late.t += 0.01
    assert "past the restriction point" in cy.advance_problem(geo, late, "g0", 0)
    assert "did you mean 'metaphase'" in cy.advance_problem(geo, st, "metaphse", 0)
    wrapped = cy.advance(geo, in_s, "g1", 0)          # round to the next cycle's G1
    assert wrapped.t == pytest.approx(1.0)
    held = cy.CycleState(in_s.t, arrests={"g2_m": "beat 2"})
    assert "held at the G2/M checkpoint" in cy.advance_problem(geo, held, "metaphase", 0)
    assert cy.advance_problem(geo, held, "g2_m", 0) is None       # up to it is fine
    assert cy.checkpoint_key("SAC") == "spindle" and cy.checkpoint_key("restriction_point") == "g1_s"
    with pytest.raises(VidgenError, match="did you mean 'spindle'"):
        cy.checkpoint_key("spindel")
    assert "arrests on unattached_kinetochore" in cy.checkpoint_problem(geo, st, "spindle", "arrest", "dna_damage")
    assert "is already arrested" in cy.checkpoint_problem(geo, held, "g2_m", "arrest", None)
    # the regulators: an arrest at G1/S goes through p53 and p21 to cyclin E–CDK2
    rows = cy.CHECKPOINTS["g1_s"].arrest["dna_damage"]
    assert rows[0].nodes[2:5] == ("p53", "p21", cy.CYC_E) and rows[0].arcs[-1].kind == "-|"
    assert any("securin" in r.nodes and "separase" in r.nodes for r in cy.CHECKPOINTS["spindle"].go)


# ----- division --------------------------------------------------------------------------------------


@pytest.mark.parametrize("two_n", [2, 4, 6, 8])
def test_counts_through_mitosis_and_meiosis(two_n: int) -> None:
    n = two_n // 2
    c = dv.stage_counts
    assert c("mitosis", "metaphase", two_n) == dv.Counts(1, two_n, 2 * two_n, "2n", "4C")
    assert c("mitosis", "anaphase", two_n).chromosomes == 2 * two_n         # separated sisters count as chromosomes
    assert c("mitosis", "cytokinesis", two_n) == dv.Counts(2, two_n, two_n, "2n", "2C")
    assert c("meiosis", "metaphase_i", two_n) == dv.Counts(1, two_n, 2 * two_n, "2n", "4C")
    assert c("meiosis", "cytokinesis_i", two_n) == dv.Counts(2, n, 2 * n, "n", "2C")   # reductional
    assert c("meiosis", "cytokinesis_ii", two_n) == dv.Counts(4, n, n, "n", "1C")      # equational
    assert dv.expect_problem("meiosis", "cytokinesis_ii", two_n, {"chromosomes": n, "chromatids": n, "cells": 4, "dna": "1C"}) is None
    problem = dv.expect_problem("meiosis", "cytokinesis_ii", two_n, {"chromosomes": two_n})
    assert problem is not None and f"each with {n} chromosomes" in problem


def test_division_spec_rules() -> None:
    with pytest.raises(VidgenError, match="2n is even"):
        dv.check_spec(dv.DivisionSpec("mitosis", 5))
    with pytest.raises(VidgenError, match="obligate chiasma"):
        dv.check_spec(dv.DivisionSpec("meiosis", 4, crossovers=((0.7,), ())))
    with pytest.raises(VidgenError, match="at the centromere"):
        dv.check_spec(dv.DivisionSpec("meiosis", 4, crossovers=((0.45,), (0.6,))))
    with pytest.raises(VidgenError, match="belong to meiosis"):
        dv.check_spec(dv.DivisionSpec("mitosis", 4, assortment=("m", "p")))
    with pytest.raises(VidgenError, match="mitosis only"):
        dv.check_spec(dv.DivisionSpec("meiosis", 4, "plant"))
    with pytest.raises(VidgenError, match="did you mean 'metaphase_i' or 'metaphase_ii'"):
        dv.stage_key("meiosis", "metaphase")
    assert dv.stage_key("meiosis", "Prophase 1") == "prophase_i" and dv.stage_key("meiosis", "anaphase-2") == "anaphase_ii"
    spec = dv.check_spec(dv.DivisionSpec("meiosis", 6, seed=3))
    assert spec.crossovers is not None and len(spec.crossovers) == 3 and all(len(x) == 1 for x in spec.crossovers)
    assert spec.assortment is not None and set(spec.assortment) <= {"m", "p"}


def test_keyframes_show_segregation_correctly() -> None:
    mit = dv.plan_division(dv.DivisionSpec("mitosis", 4))
    ids = set(mit.keyframes[0].items)
    assert all(set(kf.items) == ids for kf in mit.keyframes)
    meta = mit.keyframes[mit.stage_end["metaphase"]].items
    for ch in mit.chromatids:          # bi-orientation: sisters' kinetochores face opposite poles
        if ch.sister == 0:
            a = meta[f"kt:{ch.id}"].points[0][0]
            b = meta[f"kt:{ch.id[:-1]}1"].points[0][0]
            assert a * b < 0
    ana = mit.keyframes[mit.stage_end["anaphase"]].items
    for ch in mit.chromatids:          # each pair of sisters ends at opposite poles
        if ch.sister == 0:
            assert ana[ch.id].points[12][0] * ana[ch.id[:-1] + "1"].points[12][0] < 0

    mei = dv.plan_division(dv.DivisionSpec("meiosis", 4, assortment=("m", "p"), crossovers=((0.75,), (0.6,))))
    ana1 = mei.keyframes[mei.stage_end["anaphase_i"]].items
    side = {ch.id: ana1[ch.id].points[dv.SAMPLES // 2][0] for ch in mei.chromatids}
    assert side["c0m0"] * side["c0m1"] > 0 and side["c0m0"] * side["c0p0"] < 0     # homologues part, sisters stay together
    assert side["c0m0"] < 0 < side["c1m0"]                                         # pair 0: maternal left; pair 1: paternal left
    end = mei.keyframes[-1].items
    recombinant = [ch.id for ch in mei.chromatids if len(set(end[ch.id].colors)) > 1]
    assert sorted(recombinant) == ["c0m1", "c0p0", "c1m1", "c1p0"]                 # the non-sister chromatids that crossed over
    colors = end["c0m1"].colors
    s_x = 0.75
    assert colors[0] == "m0" and colors[-1] == "p0" and all(c == "m0" for j, c in enumerate(colors) if (j + 1) / (dv.SAMPLES - 1) < s_x)
    labels = [it for k, it in end.items() if k.startswith("label:") and it.opacity > 0]
    assert len(labels) == 4 and all(it.extra == "n = 2" for it in labels)


# ----- energy ----------------------------------------------------------------------------------------


def test_pathway_tallies() -> None:
    gly = en.pathway("glycolysis")
    assert en.tallies(gly, len(gly.steps) - 1) == {"ATP": 2, "NADH": 2, "H2O": 2}
    assert en.tallies(gly, 4) == {"ATP": -2}                          # the investment phase
    link = en.pathway("glycolysis", link=True)
    assert en.tallies(link, len(link.steps) - 1) == {"ATP": 2, "NADH": 4, "H2O": 2, "CO2": 2}
    tca = en.pathway("tca")
    assert en.tallies(tca, len(tca.steps) - 1) == en.TCA_TOTALS == {"NADH": 3, "FADH2": 1, "GTP": 1, "CO2": 2}
    assert [n.carbons for n in tca.nodes] == [4, 6, 6, 5, 4, 4, 4, 4]   # 2 C in, 2 CO₂ out per turn
    assert en.step_index(tca, "fumarate") == 5 and en.step_index(tca, "idh") == 2 and en.step_index(tca, "oxaloacetate") == 7
    with pytest.raises(VidgenError, match="did you mean 'citrate'"):
        en.step_index(tca, "citrat")
    state = en.FlowState(step=9)
    assert "runs one way" in en.pathway_advance_problem(gly, state, "g6p")
    assert en.pathway_advance_problem(tca, en.FlowState(step=6), "citrate") is None      # a cycle turns on


def test_chains_move_protons_correctly() -> None:
    etc = en.check_setting("etc")
    assert (etc.membrane, etc.p_side, etc.n_side) == ("inner_mitochondrial_membrane", "intermembrane_space", "matrix")
    assert en.chain_effects(etc, en.electron_path(etc, "nadh"))["given"] == 10          # 4 + 4 + 2 per NADH
    assert en.chain_effects(etc, en.electron_path(etc, "fadh2"))["given"] == 6
    assert en.electron_path(etc, "fadh2")[0] == "complex_ii"
    light = en.check_setting("light_reactions")
    assert (light.cell, light.p_side, light.n_side) == ("plant", "thylakoid_lumen", "stroma")
    fx = en.chain_effects(light, en.electron_path(light, "water"))
    assert fx["given"] == 6 and fx["consumed"] == 1          # 12 H⁺ per O₂ into the lumen; one H⁺ per NADPH
    bact = en.check_setting("etc", "bacterium")
    assert (bact.membrane, bact.p_side) == ("bacterial_inner_membrane", "periplasm")
    assert en.H_PER_ATP["inner_mitochondrial_membrane"] == pytest.approx(8 / 3) and en.H_PER_ATP["thylakoid_membrane"] == pytest.approx(14 / 3)


def test_setting_rules_explain_themselves() -> None:
    with pytest.raises(VidgenError, match="inner mitochondrial membrane"):
        en.check_setting("etc", membrane="plasma")
    with pytest.raises(VidgenError, match="out of the matrix into the intermembrane space"):
        en.check_setting("etc", protons_to="matrix")
    with pytest.raises(VidgenError, match="into the thylakoid lumen"):
        en.check_setting("light_reactions", protons_to="stroma")
    with pytest.raises(VidgenError, match="no chloroplasts"):
        en.check_setting("light_reactions", "animal")
    with pytest.raises(VidgenError, match="glycolysis runs in the cytosol"):
        en.check_setting("glycolysis", compartment="matrix")
    with pytest.raises(VidgenError, match="comes before"):
        en.check_setting("etc", chain=("complex_iv", "complex_iii"))
    with pytest.raises(VidgenError, match="only through cytochrome c"):
        en.check_setting("etc", chain=("complex_iii", "complex_iv"))
    with pytest.raises(VidgenError, match="sits in the thylakoid membrane"):
        en.check_setting("etc", chain=("complex_i", "psii"))
    with pytest.raises(VidgenError, match="did you mean 'tca'"):
        en.process_key("tcaa")
    assert en.process_key("Krebs cycle") == "tca"
    s = en.check_setting("etc", chain=("complex_iii", "cyt_c", "complex_iv", "atp_synthase"))
    assert "no proton gradient yet" in en.chain_advance_problem(s, en.FlowState(), "atp_synthase", None)
    assert "enters at complex II" in en.chain_advance_problem(s, en.FlowState(), None, "fadh2")


# ----- in projects -----------------------------------------------------------------------------------


def scene(kind: str, actions: list[list[dict[str, Any]]], **params: Any) -> dict[str, Any]:
    texts = ["the cell grows", "it copies its DNA", "it divides in two", "four cells"]
    return {"id": "s", "type": kind, "params": params,
            "beats": [{"id": f"b{k}", "text": texts[k % 4], "actions": a} for k, a in enumerate(actions)]}


def problems_of(make_project: Any, scenes: list[dict[str, Any]]) -> list[str]:
    return [p.message for p in project_problems(project_with(make_project, scenes, narration=NARRATION))]


def test_cell_cycle_scenes_are_validated(make_project) -> None:
    def found(actions: list[list[dict[str, Any]]], **params: Any) -> list[str]:
        return problems_of(make_project, [scene("cell_cycle", actions, **params)])

    assert found([[{"advance": "cycle", "to": "s"}], [{"checkpoint": "g2_m", "outcome": "arrest", "until": "b3"}],
                  [{"advance": "cycle", "to": "g2_m"}], [{"advance": "cycle", "to": "anaphase"}, {"checkpoint": "spindle"}]]) == []
    assert any("held at the G2/M checkpoint" in m
               for m in found([[{"checkpoint": "g2_m", "outcome": "arrest"}], [{"advance": "cycle", "to": "metaphase"}]]))
    assert any("past the restriction point" in m or "before the restriction point" in m
               for m in found([[{"advance": "cycle", "to": "s"}], [{"advance": "cycle", "to": "g0"}]]))
    assert any("advance acts on 'cycle'" in m for m in found([[{"advance": "cell"}]]))
    assert any("did you mean 'prophase' or 'prometaphase'" in m for m in found([[{"advance": "cycle", "to": "prophse"}]]))
    assert found([[{"advance": "cell", "to": "metaphase_i"}], [{"advance": "cell", "to": "cytokinesis_ii", "expect": {"chromosomes": 2}}]],
                 mode="meiosis") == []
    assert any("each with 2 chromosomes" in m for m in found([[{"advance": "cell", "to": "cytokinesis_ii", "expect": {"chromosomes": 4}}]],
                                                             mode="meiosis"))
    assert any("runs one way" in m for m in found([[{"advance": "cell", "to": "anaphase"}], [{"advance": "cell", "to": "metaphase"}]],
                                                  mode="mitosis"))
    assert any("obligate chiasma" in m for m in found([[]], mode="meiosis", crossovers=[[0.7], []]))
    assert any("chromosomes: belongs to mode: mitosis or meiosis" in m for m in found([[]], chromosomes=6))
    assert any("checkpoint is an action of cell_cycle scenes with mode: cycle" in m
               for m in found([[{"checkpoint": "g1_s"}]], mode="mitosis"))


def test_metabolism_scenes_are_validated(make_project) -> None:
    def found(actions: list[list[dict[str, Any]]], **params: Any) -> list[str]:
        return problems_of(make_project, [scene("metabolism", actions, **params)])

    assert found([[{"advance": "etc", "to": "complex_iv"}], [{"advance": "etc", "from": "fadh2"}], [{"advance": "etc", "to": "atp_synthase"}]],
                 process="etc") == []
    assert any("no proton gradient yet" in m for m in found([[{"advance": "etc", "to": "atp_synthase"}]], process="etc"))
    assert any("into the intermembrane space" in m for m in found([[]], process="etc", protons_to="matrix"))
    assert any("inner mitochondrial membrane" in m for m in found([[]], process="etc", membrane="thylakoid"))
    assert any("runs one way" in m
               for m in found([[{"advance": "glycolysis", "to": "pyruvate"}], [{"advance": "glycolysis", "to": "f6p"}]], process="glycolysis"))
    assert found([[{"advance": "tca", "to": "succinate"}], [{"advance": "tca", "to": "citrate"}]], process="tca") == []
    assert any("advance acts on 'tca'" in m for m in found([[{"advance": "etc"}]], process="tca"))
    assert any("from belongs to the chains" in m for m in found([[{"advance": "tca", "from": "nadh"}]], process="tca"))
    assert any("advance is an action of cell_cycle and metabolism scenes" in m
               for m in problems_of(make_project, [{"id": "t", "type": "title", "params": {"title": "x"},
                                                    "beats": [{"text": "a", "actions": [{"advance": "title"}]}]}]))


# ----- renders ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_cell_cycle_renders(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [{"id": "c", "type": "cell_cycle", "params": {"title": "The cycle"},
               "beats": [{"text": "the cell grows and copies its DNA", "actions": [{"advance": "cycle", "to": "s", "into": 0.5}]},
                         {"text": "damage stops it", "actions": [{"checkpoint": "g2_m", "outcome": "arrest"}]}]},
              {"id": "m", "type": "cell_cycle", "params": {"mode": "meiosis", "chromosomes": 2},
               "beats": [{"text": "homologues pair and cross over", "actions": [{"advance": "cell", "to": "metaphase_i"}]},
                         {"text": "four haploid cells", "actions": [{"advance": "cell"}]}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 3.0})))
    cycle = render(project, "c", media, size)
    assert cycle.state.t == pytest.approx(cycle.geo.bounds["s"][0] + 0.5 * (cycle.geo.bounds["s"][1] - cycle.geo.bounds["s"][0]))
    assert cycle.panel is not None
    meiosis = render(project, "m", media, size)
    assert meiosis.stage == "cytokinesis_ii" and meiosis.kf == len(meiosis.div.keyframes) - 1


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_metabolism_renders(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [{"id": "e", "type": "metabolism", "params": {"process": "etc"},
               "beats": [{"text": "electrons run down the chain", "actions": [{"advance": "etc"}]},
                         {"text": "protons drive the synthase", "actions": [{"advance": "etc", "to": "atp_synthase"}]}]},
              {"id": "g", "type": "metabolism", "params": {"process": "glycolysis", "link": True},
               "beats": [{"text": "glucose is split", "actions": [{"advance": "glycolysis", "to": "acetyl_coa"}]}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 3.0})))
    etc = render(project, "e", media, size)
    assert etc.tally_values["H"] == 10 and etc.tally_values["H2O"] == 1 and etc.tally_values["ATP"] == 3
    gly = render(project, "g", media, size)
    assert gly.tally_values == {"ATP": 2, "NADH": 4, "pyruvate": 2, "CO2": 2, "acetyl": 2}
