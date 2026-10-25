"""Step 219 (DESIGN.md §96.18): the genetics accuracy lint rules.

Each text check is run on wrong statements (each must be found) and on correct textbook ones
(none may be); the scene checks on small projects built from the genetics scene types (no render)."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import minimal_config
from vidgen.config import LINT_RULES, LintRules
from vidgen.genetics import accuracy as gacc
from vidgen.genetics.karyotype import parse_karyotype
from vidgen.genetics.mutation import plan_mutation
from vidgen.genetics.pedigree_plan import plan_pedigree
from vidgen.genetics.punnett import plan_cross
from vidgen.lint import RULES
from vidgen.lint.genetics_rule import GENETICS_RULES, genetics_issues
from vidgen.lint.science_rule import science_issues
from vidgen.project import Project

DIHYBRID = {"preset": "pea_dihybrid", "parents": ["RrYy", "RrYy"]}
HEMOPHILIA = {"preset": "hemophilia_a", "parents": ["X^H X^h", "X^H Y"]}
CF_FAMILY = {"condition": "cystic fibrosis", "mode": "AR", "carrier_frequency": "1/25",
             "individuals": ["I-1: male", "I-2: female", "II-1: male of I-1 + I-2", "II-2: female affected proband of I-1 + I-2",
                             "II-3: male of I-1 + I-2", "II-4: female", "III-1: unknown proposed of II-3 + II-4"]}


# ----- numbers and shares ------------------------------------------------------------------------------


def test_shares_and_numbers() -> None:
    said = {s.text: s.value for s in gacc.shares_in("Half the sons, a quarter of them, three quarters, two thirds, 1 in 2,500, one in "
                                                     "four, 25%, a third child, 2 out of 3, about 17 percent, all the daughters")}
    F = gacc.Fraction
    assert said == {"Half": F(1, 2), "a quarter": F(1, 4), "three quarters": F(3, 4), "two thirds": F(2, 3), "1 in 2,500": F(1, 2500),
                    "one in four": F(1, 4), "25%": F(1, 4), "2 out of 3": F(2, 3), "17 percent": F(17, 100), "all": 1}
    assert gacc.number("two thousand five hundred") == 2500 and gacc.number("twenty-one") == 21
    about = gacc.shares_in("about 42 percent")[0]
    assert about.approx and about.matches(0.415, 0.05) and gacc.shares_in("42 percent")[0].matches(0.415)     # rounded
    assert gacc.shares_in("about 43 percent")[0].matches(0.415, 0.05) and not gacc.shares_in("43 percent")[0].matches(0.415)
    assert gacc.shares_in("more than 50 percent")[0].bound
    assert gacc.ratios_said("three round to one wrinkled and 9 purple : 7 white", {"round", "wrinkled", "purple", "white"}) == [
        ("9 purple : 7 white", (9, 7), True), ("three round to one wrinkled", (3, 1), True)]


# ----- crosses -----------------------------------------------------------------------------------------

CROSS_WRONG = [
    (DIHYBRID, "The offspring show a 3:1 ratio.", "9 : 3 : 3 : 1"),
    (DIHYBRID, "Half of the offspring are wrinkled.", "1/4 (25 %) of the offspring are wrinkled"),
    (DIHYBRID, "Nine sixteenths of the offspring are green.", "1/4 (25 %) of the offspring are green"),
    (HEMOPHILIA, "Half the daughters have hemophilia A.", "0 of the daughters"),
    (HEMOPHILIA, "All the daughters are carriers.", "1/2 (50 %) of the daughters (females) are carriers"),
    (HEMOPHILIA, "A quarter of the sons are affected.", "1/2 (50 %) of the sons"),
    ({"preset": "labrador", "parents": ["BbEe", "BbEe"]}, "The puppies come in a 9:3:3:1 ratio.", "9 : 3 : 4"),
    ({"preset": "yellow_mouse", "parents": ["A^Y A", "A^Y A"]}, "Three quarters of the mice are yellow.", "2/3"),
]
CROSS_RIGHT = [
    (DIHYBRID, "The F2 shows a nine to three to three to one ratio of phenotypes."),
    (DIHYBRID, "Nine sixteenths of the offspring are round and yellow, one sixteenth wrinkled and green."),
    (DIHYBRID, "Each trait alone segregates three to one."),
    (DIHYBRID, "Seed shape segregates three round to one wrinkled."),
    (DIHYBRID, "A quarter of the offspring are green."),
    (DIHYBRID, "Each parent makes four kinds of gametes in a 1:1:1:1 ratio."),
    (DIHYBRID, "A test cross would give a 1:1:1:1 ratio."),
    (DIHYBRID, "The genotypes come in a 1:2:1:2:4:2:1:2:1 ratio."),
    (HEMOPHILIA, "Half the sons have hemophilia A, and half the daughters are carriers."),
    (HEMOPHILIA, "Each son has a one in two chance of hemophilia."),
    (HEMOPHILIA, "A quarter of the children are affected sons."),
    (HEMOPHILIA, "Normal clotting to hemophilia is three to one."),
    ({"preset": "snapdragon", "parents": ["C^R C^W", "C^R C^W"]}, "The F2 is one red to two pink to one white."),
    ({"preset": "yellow_mouse", "parents": ["A^Y A", "A^Y A"]}, "Two thirds of the surviving mice are yellow; a quarter of the embryos die."),
    ({"preset": "abo", "parents": ["I^A i", "I^B i"]}, "A quarter of the children have blood group AB."),
    ({"preset": "labrador", "parents": ["BbEe", "BbEe"]}, "Four sixteenths of the puppies are yellow: 9 black : 3 brown : 4 yellow."),
    ({"preset": "labrador", "parents": ["BbEe", "BbEe"]}, "The nine to three to three to one classes merge into 9:3:4."),
    ({"preset": "pea_seed_shape", "P": ["RR", "rr"]}, "All F1 plants are round, and the F2 shows three round to one wrinkled."),
    ({"preset": "drosophila_b_vg", "parents": ["b^+vg^+/bvg", "bvg/bvg"]}, "41.5% of the flies have grey bodies and normal wings."),
]


@pytest.mark.parametrize(("spec", "text", "says"), CROSS_WRONG)
def test_cross_claims_found(spec: dict[str, Any], text: str, says: str) -> None:
    found = gacc.cross_claims(text, plan_cross(spec))
    assert len(found) == 1 and says in found[0].message, found


@pytest.mark.parametrize(("spec", "text"), CROSS_RIGHT)
def test_cross_claims_right(spec: dict[str, Any], text: str) -> None:
    assert gacc.cross_claims(text, plan_cross(spec)) == []


# ----- pedigrees ---------------------------------------------------------------------------------------


def test_pedigree_text_claims() -> None:
    wrong = ["This dominant trait skips a generation.", "The father passes the X-linked allele to his son.",
             "The family shows male-to-male transmission of this X-linked trait."]
    for text in wrong:
        assert len(gacc.pedigree_text_claims(text)) == 1, text
    assert len(gacc.pedigree_text_claims("The affected father passes it to his son.", "XR")) == 1     # the scene's mode is X-linked
    right = ["A dominant trait with reduced penetrance can seem to skip a generation.", "Recessive traits often skip generations.",
             "X-linked recessive traits are never passed from father to son.", "Affected fathers pass the X-linked allele to all their daughters.",
             "Fathers pass their Y chromosome to their sons.", "Autosomal dominant traits appear in every generation.",
             "Male-to-male transmission rules out X-linked inheritance."]
    assert [t for t in right if gacc.pedigree_text_claims(t, "XR")] == []
    assert gacc.pedigree_text_claims("This dominant trait skips a generation.", "AD", penetrance=gacc.Fraction(4, 5)) == []


def test_pedigree_probabilities() -> None:
    plan = plan_pedigree(CF_FAMILY)
    wrong = {"II-3 is a carrier with probability one half.": "2/3", "The risk for their baby is one in four.": "1/150",
             "An unaffected sister of an affected child is a carrier with probability one half.": "no unaffected person"}
    for text, says in wrong.items():
        found = gacc.pedigree_claims(text, plan)
        assert len(found) == 1 and says in found[0].message, (text, found)
    right = ["II-3 is a carrier with probability two thirds.", "Their child's risk is 1 in 150.",
             "If both parents are carriers, each child has a one in four chance of being affected.",
             "Two carriers have a one in four chance of an affected child with each pregnancy.",
             "An unaffected brother of an affected child is a carrier with probability two thirds."]
    assert [t for t in right if gacc.pedigree_claims(t, plan)] == []


# ----- linkage -----------------------------------------------------------------------------------------


def test_linkage_claims() -> None:
    from vidgen.genetics.mapping import plan_linkage
    from vidgen.lint.genetics_rule import cross_pairs, map_pairs

    pairs, symbols = map_pairs(plan_linkage({"loci": ["b", "vg"], "counts": {"b vg": 405, "+ +": 415, "b +": 85, "+ vg": 95}}))
    wrong = {"The recombination frequency is sixty percent.": "cannot exceed 50 %", "So b and vg are 25 cM apart.": "18.0 cM",
             "b and vg show 30% recombinants.": "18 %", "b and vg are unlinked.": "linked in this scene"}
    for text, says in wrong.items():
        found = gacc.linkage_claims(text, pairs, symbols)
        assert len(found) == 1 and says in found[0].message, (text, found)
    right = ["Eighteen percent of the offspring are recombinant: the genes are eighteen centimorgans apart.",
             "b and vg are about 18 cM apart.", "The recombination frequency never exceeds 50 percent.",
             "Genes on different chromosomes assort independently.", "Loci more than 50 cM apart show 50% recombinants."]
    assert [t for t in right if gacc.linkage_claims(t, pairs, symbols)] == []
    pairs, symbols = cross_pairs(plan_cross(DIHYBRID).system)
    assert "assort independently" in gacc.linkage_claims("R and Y are linked.", pairs, symbols)[0].message
    assert gacc.linkage_claims("A sentence about X-linked genes and R and Y.", pairs, symbols) == []
    # three linked loci: the outer pair's distance is the sum, its RF the direct count or the sum
    pairs, symbols = map_pairs(plan_linkage({"loci": ["v", "cv", "ct"], "counts": {
        "v cv+ ct+": 580, "v+ cv ct": 592, "v cv ct+": 45, "v+ cv+ ct": 40, "v cv ct": 89, "v+ cv+ ct+": 94, "v cv+ ct": 3, "v+ cv ct+": 5}}))
    assert gacc.linkage_claims("v and cv are 19.6 cM apart, and ct lies 13.2 cM from v.", pairs, symbols) == []
    assert gacc.linkage_claims("v and ct are 6.4 cM apart.", pairs, symbols)


# ----- Hardy–Weinberg ----------------------------------------------------------------------------------


def test_hw_claims() -> None:
    wrong = {"Carriers are q squared.": "2pq", "Affected people are 2pq.": "q²", "p² + q² = 1.": "p² + 2pq + q²",
             "With an incidence of 1 in 2,500, q is 1 in 50 and the carriers are 1 in 50.": "1 in 25.5",
             "The incidence is 1 in 2500 and q is 1 in 100.": "q ≈ 0.02"}
    for text, says in wrong.items():
        found = gacc.hw_claims(text)
        assert len(found) == 1 and says in found[0].message, (text, found)
    right = ["If q is one in fifty, carriers are about one in twenty-five.", "Carriers are 2pq, about 1 in 25.",
             "Affected people are q squared: 1 in 2,500, so q is 1/50.", "p² + 2pq + q² = 1.",
             "About 1 in 25 Northern Europeans carries a cystic fibrosis allele.", "Affected people are q squared and carriers 2pq."]
    assert [t for t in right if gacc.hw_claims(t)] == []
    from vidgen.genetics.population import plan_population

    hw = plan_population({"incidence": "1/2500"}).hw
    assert gacc.hw_claims("The incidence here is 1 in 900.", hw)
    assert gacc.hw_claims("The incidence here is 1 in 2,500, and about 1 in 25 people are carriers.", hw) == []


# ----- CRISPR, karyotypes, HGVS ------------------------------------------------------------------------

CRISPR_WRONG = ["Cas9 needs the PAM TTTV.", "Cas9 cuts three base pairs downstream of the PAM.", "Cas9 cuts 5 bp upstream of the PAM.",
                "Cas9 leaves sticky ends.", "Cas9 cuts within the PAM.", "Cas9 uses a 30-nucleotide spacer.",
                "For Cas9, the PAM lies upstream of the protospacer.", "With Cas9 the PAM is on the target strand.",
                "Cas12a needs an NGG PAM."]
CRISPR_RIGHT = ["SpCas9 needs an NGG PAM right after the protospacer.", "Cas9 cuts both strands three base pairs upstream of the PAM, "
                "leaving blunt ends.", "Cas12a recognises a TTTV PAM and makes a staggered cut.", "The 20-nucleotide spacer pairs with "
                "the target strand.", "The Cas9 PAM, here TGG, sits on the non-target strand.", "SaCas9 uses the longer PAM NNGRRT.",
                "Restriction enzymes leave sticky ends, but Cas9 cuts bluntly.", "The guide RNA's spacer is 20 nucleotides long."]


@pytest.mark.parametrize("text", CRISPR_WRONG)
def test_crispr_wrong(text: str) -> None:
    assert len(gacc.crispr_claims(text)) == 1, gacc.crispr_claims(text)


def test_crispr_right() -> None:
    assert [t for t in CRISPR_RIGHT if gacc.crispr_claims(t)] == []
    assert gacc.crispr_claims("The enzyme cuts three base pairs downstream of the PAM.") == []      # no Cas named, no crispr scene
    assert gacc.crispr_claims("The enzyme cuts three base pairs downstream of the PAM.", "SpCas9")


def test_karyotype_claims() -> None:
    wrong = {"45,X is male.": "female", "A girl with 47,XXY.": "male", "Write 47,xy,+21.": "capitals",
             "The karyotype is 47,XX,+21,del(5)(p15.2).": "47,XX,del(5)(p15.2),+21", "Turner syndrome affects boys.": "female",
             "The child is 46,XY,+21.": "says 46 chromosomes but lists 47"}
    for text, says in wrong.items():
        found = gacc.karyotype_claims(text)
        assert len(found) == 1 and says in found[0].message, (text, found)
    edwards = parse_karyotype("47,XY,+18")
    assert "Edwards syndrome" in gacc.karyotype_claims("This is trisomy 21, Down syndrome.", edwards)[0].message
    right = [("47,XX,+21 is a girl with trisomy 21.", None), ("45,X is Turner syndrome, in a woman.", None),
             ("47,XXY is Klinefelter syndrome in a man.", None), ("Three copies of chromosome twenty-one: Down syndrome.", parse_karyotype("47,XY,+21")),
             ("Like Down syndrome, trisomy 18 is a trisomy.", edwards), ("This is translocation Down syndrome.",
                                                                       parse_karyotype("46,XX,rob(14;21)(q10;q10),+21")),
             ("The notation 47,XY,+8,t(9;22)(q34;q11.2) lists chromosome 8 first.", None)]
    assert [t for t, k in right if gacc.karyotype_claims(t, k)] == []
    assert gacc.iscn_order_problem(parse_karyotype("46,XY,inv(9)(p12q13),del(5)(p15.2)")) == "46,XY,del(5)(p15.2),inv(9)(p12q13)"


def test_hgvs_claims() -> None:
    hbb = plan_mutation({"gene": "HBB", "variant": {"c": "c.20A>T", "p": "p.(Glu7Val)"}})
    wrong = {"The variant c.20A>G.": ("not the scene's variant", None), "Sickle-cell disease is p.Glu6Val.": ("legacy numbering", None),
             "Glu6Val changes the protein.": ("legacy numbering", None), "We write c.A20T.": ("position first", None),
             "The R553X variant.": ("p.(Arg553*)", "info"), "In cystic fibrosis, ΔF508 is the commonest allele.": ("p.(Phe508del)", "info")}
    for text, (says, severity) in wrong.items():
        found = gacc.hgvs_claims(text, hbb, True)
        assert len(found) == 1 and says in found[0][0].message and found[0][1] == severity, (text, found)
    right = ["c.20A>T changes codon 7: p.(Glu7Val).", "Its legacy name is Glu6Val, numbered without the initiator methionine.",
             "This is p.(Glu6Val) in the legacy numbering.", "The legacy R553X allele.", "The commonest allele is F508del."]
    assert [t for t in right if gacc.hgvs_claims(t, hbb, True)] == []
    assert gacc.hgvs_claims("HbS is HBB p.Glu6Val.")                         # any scene: the reference genes' legacy numbering
    assert gacc.hgvs_claims("The S1P receptor binds its ligand.") == []      # not a variant: no shorthand outside genetics


# ----- the rules on projects ---------------------------------------------------------------------------


def _project(make_project, scenes: list[dict[str, Any]], **extra: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, **extra)))


def _found(project: Project, scene_id: str) -> list[tuple[str, str | None, str, str | None]]:
    import vidgen.scenes  # noqa: F401 - registers the built-in scene types

    return [(f.rule, f.beat, f.message, f.severity) for f in genetics_issues(project, scene_id, project.config.lint.rules)]


def test_rules_are_registered_in_config_order() -> None:
    assert list(LINT_RULES[-len(GENETICS_RULES):]) == list(GENETICS_RULES)
    for name in GENETICS_RULES:
        assert RULES[name].scope == "scene" and RULES[name].default == "warning"
    assert LintRules().genetics_hwe.tolerance == 0.1


def test_scene_rules(make_project) -> None:
    scenes = [
        {"id": "x", "type": "cross", "params": DIHYBRID, "beats": [{"text": "The offspring show a three to one ratio."}]},
        {"id": "p", "type": "pedigree", "params": {"mode": "AD", "individuals": [
            "I-1: male affected", "I-2: female", "II-1: male of I-1 + I-2", "II-2: female", "III-1: female affected of II-1 + II-2"]},
         "beats": [{"text": "A family."}]},
        {"id": "k", "type": "karyotype", "params": {"karyotype": "46,XY,inv(9)(p12q13),del(5)(p15.2)", "title": "47,xx,+21"},
         "beats": [{"text": "Two changes."}]},
        {"id": "m", "type": "mutation", "params": {"gene": "HBB", "variant": "c.20A>T", "title": "HBB p.(Glu6Val)"},
         "beats": [{"text": "The hbb gene changes."}]},
    ]
    p = _project(make_project, scenes)
    assert [(f[0], f[1]) for f in _found(p, "x")] == [("genetics_ratio", "x_b1")]
    [(rule, beat, message, severity)] = _found(p, "p")
    assert (rule, beat, severity) == ("genetics_pedigree", "p_b1", "error") and "does not fit the stated mode AD" in message
    found = _found(p, "k")
    assert sorted(f[0] for f in found) == ["genetics_karyotype"] * 2, found
    assert any(f[2].startswith("title '47,xx,+21'") for f in found) and any("write 46,XY,del(5)(p15.2),inv(9)(p12q13)" in f[2] for f in found)
    assert [f[0] for f in _found(p, "m")] == ["genetics_hgvs"] and "legacy numbering" in _found(p, "m")[0][2]
    naming = science_issues(p, "m", LintRules())
    assert [f.rule for f in naming] == ["science_naming"] and "'hbb'" in naming[0].message


def test_rules_off_and_severity(make_project) -> None:
    scenes = [{"id": "b", "type": "bullets", "params": {"items": ["x"]},
               "beats": [{"text": "Cas9 leaves sticky ends."}, {"text": "The R553X variant of CFTR."}]}]
    p = _project(make_project, scenes, lint={"rules": {"genetics_crispr": {"severity": "off"}}})
    assert [(f[0], f[3]) for f in _found(p, "b")] == [("genetics_hgvs", "info")]
    p = _project(make_project, scenes)
    assert sorted(f[0] for f in _found(p, "b")) == ["genetics_crispr", "genetics_hgvs"]


def test_gallery_genetics_scenes_are_clean() -> None:
    from pathlib import Path

    import vidgen.scenes  # noqa: F401

    project = Project.load(Path(__file__).resolve().parent.parent / "examples" / "gallery")
    for spec in project.config.scenes:
        assert genetics_issues(project, spec.id, LintRules()) == [], spec.id


def test_narration_rules_know_the_genetics_targets(make_project) -> None:
    from vidgen import registry
    from vidgen.lint.narration_rule import SHOWING_ACTIONS, target_texts

    import vidgen.scenes  # noqa: F401

    names = {a.name for a in registry.all_actions()}
    genetics = {"form_gametes", "fill", "count", "ratio", "chi_square", "deduce", "analyse", "risk", "cross_over", "measure", "rearrange",
                "mutate", "scan", "cleave", "repair", "run", "simulate", "resample", "regional"}
    assert genetics <= SHOWING_ACTIONS and genetics <= names
    p = _project(make_project, [
        {"id": "g", "type": "gwas", "params": {"peaks": [{"chromosome": 16, "position": "53.8 Mb", "p": 1e-40, "gene": "FTO"}]},
         "beats": [{"text": "x"}]},
        {"id": "k", "type": "karyotype", "params": {"karyotype": "46,XX", "bands": {"7q31.2": "CFTR"}}, "beats": [{"text": "x"}]}])
    assert target_texts(p, "g")("peak:FTO") == "FTO" and target_texts(p, "k")("band:7q31.2") == "CFTR"
    from vidgen.scenes.captions import video_gene_symbols

    assert {"FTO", "CFTR"} <= video_gene_symbols(p)
