"""Step 215: the ``pedigree`` scene type (DESIGN.md §96.8): the chart parsed and checked (compact
lines, two fathers, cycles, twins, NSGC ids), the deterministic layout by generation (sibships in
birth order, partners beside, consanguineous lines meeting in the middle, NSGC numbering), the
exact analysis of the six modes of inheritance on textbook pedigrees with the reason a mode is
excluded, obligate carriers, carrier probabilities (2/3; Bayesian conditioning on unaffected
sons), risks for a proposed child (1/150 with a carrier frequency), reduced penetrance, and the
scene validated and rendered in 16:9 and 9:16."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_actions import project_with, render
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.genetics.pedigree import parse_pedigree
from vidgen.genetics.pedigree_analysis import Options, analyse, genotype_plain, infer
from vidgen.genetics.pedigree_layout import layout_pedigree
from vidgen.genetics.pedigree_plan import build_pedigree_plan, declared_mode_problem
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}

#: Autosomal recessive (cystic fibrosis-like): unaffected parents, an affected daughter.
AR = ["I-1: male", "I-2: female", "II-1: male of I-1 + I-2", "II-2: female affected of I-1 + I-2", "II-3: male of I-1 + I-2",
      "II-4: female", "III-1: unknown proposed of II-3 + II-4"]
#: Autosomal dominant: vertical, father to son.
AD = ["I-1: male affected", "I-2: female", "II-1: male affected of I-1 + I-2", "II-2: female", "II-3: female of I-1 + I-2",
      "II-4: male of I-1 + I-2", "III-1: male affected of II-1 + II-2", "III-2: female of II-1 + II-2"]
#: X-linked recessive: affected males through carrier females.
XR = ["I-1: male", "I-2: female", "II-1: male affected of I-1 + I-2", "II-2: female of I-1 + I-2", "II-3: male",
      "III-1: male affected of II-3 + II-2", "III-2: female of II-3 + II-2"]
#: X-linked dominant: an affected father's daughters all affected, sons not.
XD = ["I-1: male affected", "I-2: female", "II-1: male", "II-2: female affected of I-1 + I-2", "II-3: male of I-1 + I-2",
      "II-4: female affected of I-1 + I-2", "III-1: male affected of II-1 + II-2", "III-2: female of II-1 + II-2",
      "III-3: male of II-1 + II-2"]
#: Y-linked: father to every son.
YL = ["I-1: male affected", "I-2: female", "II-1: male affected of I-1 + I-2", "II-2: female", "II-3: female of I-1 + I-2",
      "II-4: male affected of I-1 + I-2", "III-1: male affected of II-1 + II-2", "III-2: female of II-1 + II-2"]
#: Mitochondrial: a mother to all her children, a father to none.
MT = ["I-1: male", "I-2: female affected", "II-1: male", "II-2: female affected of I-1 + I-2", "II-3: male affected of I-1 + I-2",
      "II-4: female", "III-1: male affected of II-1 + II-2", "III-2: female affected of II-1 + II-2",
      "III-3: female of II-3 + II-4", "III-4: male of II-3 + II-4"]


def ped(lines: list[Any], couples: Any = None) -> Any:
    p = parse_pedigree(lines, couples)
    p.labels = layout_pedigree(p).labels
    return p


def fits(lines: list[Any], **opts: Any) -> dict[str, bool]:
    return {v.mode: v.consistent for v in analyse(ped(lines), Options(**opts))}


def reasons(lines: list[Any], **opts: Any) -> dict[str, str]:
    return {v.mode: v.reason for v in analyse(ped(lines), Options(**opts))}


# ----- the analysis of the modes ---------------------------------------------------------------------


def test_textbook_pedigrees_fit_their_modes_and_others_are_excluded_with_reasons() -> None:
    assert fits(AR) == {"AD": False, "AR": True, "XD": False, "XR": False, "YL": False, "MT": False}
    r = reasons(AR)
    assert r["AD"] == ("II-2 is affected but neither parent (I-1, I-2) is: a dominant trait does not skip a generation "
                       "(fits with reduced penetrance)")
    assert "affected daughter II-2 needs an Xᵃ from her father I-1, who is unaffected" in r["XR"]
    assert "females have no Y" in r["YL"] and "mtDNA comes from the mother" in r["MT"]
    assert fits(AD) == {"AD": True, "AR": False, "XD": False, "XR": False, "YL": False, "MT": False}
    r = reasons(AD)
    assert r["XR"] == ("father-to-son: affected father II-1 has an affected son III-1, but a son's X comes from his mother II-2 "
                       "(married in, not a carrier)")
    assert "married in (rare allele: not a carrier)" in r["AR"] and "every son gets his father's Y" in r["YL"]
    assert fits(XR) == {"AD": False, "AR": False, "XD": False, "XR": True, "YL": False, "MT": False}
    assert fits(XD) == {"AD": True, "AR": False, "XD": True, "XR": False, "YL": False, "MT": False}
    assert "has an unaffected son III-3" in reasons(XD)["XR"]
    assert fits(YL) == {"AD": True, "AR": False, "XD": False, "XR": False, "YL": True, "MT": False}
    assert fits(MT) == {"AD": True, "AR": False, "XD": False, "XR": False, "YL": False, "MT": True}
    assert "unaffected daughter III-3" in reasons(MT)["XD"]


def test_rare_allele_assumption_and_carrier_frequency() -> None:
    assert fits(AD, rare=False)["XR"] and fits(AD, rare=False)["AR"]        # a carrier marrying in explains it
    v = {x.mode: x for x in analyse(ped(AD), Options(rare=False))}
    assert v["XR"].reason == "fits if II-2 (married in) is a carrier" and v["XR"].people == ("II-2",)
    assert fits(XR, carrier_frequency=Fraction(1, 25))["AR"]


def test_reduced_penetrance_lets_a_dominant_trait_skip_a_generation() -> None:
    skip = ["I-1: male affected", "I-2: female", "II-1: female of I-1 + I-2", "II-2: male", "III-1: male affected of II-2 + II-1"]
    r = reasons(skip)
    assert r["AD"].endswith("a dominant trait does not skip a generation (fits with reduced penetrance)")
    v = {x.mode: x for x in analyse(ped(skip), Options(penetrance=Fraction(4, 5)))}
    assert v["AD"].consistent and v["AD"].reduced_penetrance and v["AD"].reason == "fits with reduced penetrance: II-1 is a non-penetrant carrier"
    inf = infer(ped(skip), "AD", Options(penetrance=Fraction(4, 5)))
    assert inf is not None and inf.forced["II-1"] == ("", 1)


def test_mz_twins_carriers_and_other_reasons() -> None:
    twins = ["I-1: male", "I-2: female", "II-1: female affected of I-1 + I-2 twin II-2 MZ", "II-2: female of I-1 + I-2 twin II-1 MZ"]
    assert not any(fits(twins).values())
    assert reasons(twins)["AR"].startswith("MZ twins II-1 and II-2 differ")
    carrier_male = ["I-1: male carrier", "I-2: female", "II-1: male affected of I-1 + I-2"]
    assert not fits(carrier_male)["XR"] and "a male has one X (hemizygous)" in reasons(carrier_male)["XR"]
    assert fits(carrier_male)["AR"]


# ----- genotypes and probabilities -------------------------------------------------------------------------


def test_obligate_carriers_and_the_two_thirds_rule() -> None:
    p = ped(AR)
    inf = infer(p, "AR", Options())
    assert inf is not None and set(inf.obligate) == {"I-1", "I-2"}
    assert inf.posterior["II-1"] == {("", 0): Fraction(1, 3), ("", 1): Fraction(2, 3)}
    assert inf.forced["II-2"] == ("", 2) and inf.forced["II-4"] == ("", 0)        # married in, the allele rare
    assert genotype_plain("AR", ("", 1)) == "Aa" and genotype_plain("XR", ("f", 1), ("H", "h")) == "XᴴXʰ"
    assert genotype_plain("XR", ("m", 1), ("H", "h")) == "XʰY" and genotype_plain("AD", ("", 1)) == "Aa"


def test_risk_for_a_proposed_child() -> None:
    p = ped(AR)
    risk = infer(p, "AR", Options(carrier_frequency=Fraction(1, 25))).risk
    assert risk is not None and risk.affected == Fraction(1, 150)
    assert [(k, who, f) for k, who, f in risk.factors] == [("carrier", "II-3", Fraction(2, 3)), ("carrier", "II-4", Fraction(1, 25)),
                                                          ("transmit", "both", Fraction(1, 4))]
    assert infer(p, "AR", Options()).risk.affected == 0                              # no carrier marrying in
    family = ["gp: male affected", "gm: female", "son: male affected of gp + gm", "wife: female", "daughter: female of gp + gm",
              "husband: male"]
    r = infer(ped(family + ["kid: unknown proposed of son + wife"]), "AD", Options()).risk
    assert r.affected == Fraction(1, 2) and [f[2] for f in r.factors] == [Fraction(1), Fraction(1, 2)]
    assert infer(ped(family + ["kid: unknown proposed of husband + daughter"]), "AD", Options()).risk.affected == 0
    r = infer(ped(family + ["kid: unknown proposed of husband + daughter"]), "AD", Options(penetrance=Fraction(4, 5))).risk
    assert r.affected == Fraction(4, 5) * Fraction(1, 2) * Fraction(1, 6)       # daughter Aa with 1/6 = (1/2·1/5)/(1/2·1/5 + 1/2)


def test_bayesian_conditioning_on_unaffected_sons() -> None:
    lines = ["I-1: male", "I-2: female", "II-1: male affected of I-1 + I-2", "II-2: female of I-1 + I-2", "II-3: male",
             "III-1: male of II-3 + II-2", "III-2: male of II-3 + II-2", "III-3: male of II-3 + II-2"]
    inf = infer(ped(lines), "XR", Options())
    assert "I-2" in inf.obligate
    assert inf.posterior["II-2"][("f", 1)] == Fraction(1, 9)                 # prior 1/2, three unaffected sons: (1/16)/(1/16 + 1/2)
    without = infer(ped(lines[:5] + ["III-1: unknown proposed of II-3 + II-2"]), "XR", Options())
    assert without.posterior["II-2"][("f", 1)] == Fraction(1, 2)
    assert without.risk.affected == Fraction(1, 8) and without.risk.by_sex == {"son": Fraction(1, 4), "daughter": Fraction(0)}
    assert [f[0] for f in without.risk.factors] == ["carrier", "sex", "transmit"]


def test_consanguinity_is_found_and_risk_is_exact() -> None:
    cousins = ["I-1: male", "I-2: female", "II-1: male of I-1 + I-2", "II-2: female", "II-3: female of I-1 + I-2", "II-4: male",
               "III-1: male of II-1 + II-2", "III-2: female of II-4 + II-3", "IV-1: female affected of III-1 + III-2",
               "IV-2: unknown proposed of III-1 + III-2"]
    p = ped(cousins)
    c = next(x for x in p.couples if set(x.partners) == {"III-1", "III-2"})
    assert c.consanguineous
    lay = layout_pedigree(p)
    row = list(lay.order[2])
    assert abs(row.index("III-1") - row.index("III-2")) == 1          # the cousins stand side by side
    assert fits(cousins)["AR"] and infer(p, "AR", Options()).risk.affected == Fraction(1, 4)


# ----- layout -------------------------------------------------------------------------------------------


def test_layout_is_deterministic_by_generation() -> None:
    names = ["grandpa: male", "grandma: female", "dad: male of grandpa + grandma", "mum: female", "aunt: female affected of grandpa + grandma",
             "kid1: male of dad + mum", "kid2: female affected of dad + mum", "kid3: male of dad + mum twin kid4 MZ",
             "kid4: male of dad + mum twin kid3 MZ"]
    a, b = layout_pedigree(parse_pedigree(names)), layout_pedigree(parse_pedigree(names))
    assert a == b
    assert a.order == (("grandpa", "grandma"), ("dad", "mum", "aunt"), ("kid1", "kid2", "kid3", "kid4"))
    assert a.labels["aunt"] == "II-3" and a.labels["kid4"] == "III-4"
    assert a.x["grandpa"] < a.x["grandma"] and a.x["kid4"] - a.x["kid3"] == pytest.approx(1.0)
    for r in a.order:
        assert all(a.x[q] - a.x[p] >= 0.999 for p, q in zip(r, r[1:]))
    mid = (a.x["dad"] + a.x["mum"]) / 2
    kids = [a.x[k] for k in ("kid1", "kid2", "kid3", "kid4")]
    assert (min(kids) + max(kids)) / 2 == pytest.approx(mid)                 # the sibship hangs under its parents
    wrong = ["I-1: male", "I-2: female", "II-1: female of I-2 + I-1", "II-2: male of I-1 + I-2", "II-3: male spouse II-1"]
    with pytest.raises(VidgenError, match="generation II is drawn II-1, II-3, II-2"):
        build_pedigree_plan({"individuals": wrong})
    right = ["I-1: male", "I-2: female", "II-1: male spouse II-2", "II-2: female of I-1 + I-2", "II-3: male of I-1 + I-2"]
    assert build_pedigree_plan({"individuals": right}).layout.order[1] == ("II-1", "II-2", "II-3")


# ----- validation ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("lines, message", [
    (["a: male", "b: male", "c: female of a + b"], "has two fathers"),
    (["a: male of c + d", "b: female", "c: male of a + b", "d: female"], "a cycle in the parents"),
    (["a: male", "b: female", "c: male of a + b twin d MZ", "d: female twin c"], "must have the same parents"),
    (["a: male", "b: female", "c: male of a + b twin d MZ", "d: female of a + b twin c MZ"], "monozygotic"),
    (["a: male", "b: female", "c: female affected carrier of a + b"], "affected and carrier"),
    (["a: male", "b: female", "c: female of a + z"], "'z' is not an individual"),
    (["a: male", "b: female", "c: female afected of a + b"], "did you mean 'affected'"),
    (["I-1: male", "I-2: female", "III-1: male of I-1 + I-2"], "does not fit its parent"),
    (["I-1: male", "x: female"], "some ids are in NSGC form"),
])
def test_pedigree_errors(lines: list[str], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        parse_pedigree(lines)


def test_plan_checks_the_declared_mode_and_locus() -> None:
    with pytest.raises(VidgenError, match="a male carrier under X-linked recessive"):
        build_pedigree_plan({"individuals": XR[:2] + ["II-1: male carrier of I-1 + I-2"], "mode": "XR"})
    plan = build_pedigree_plan({"individuals": AD, "mode": "AR"})
    assert plan.warnings and plan.mode is None
    assert declared_mode_problem(plan).startswith("AR excluded: III-1 is affected (aa), so II-2 would carry the allele")
    hemo = build_pedigree_plan({"individuals": XR, "preset": "hemophilia_a"})
    assert hemo.mode == "XR" and hemo.alleles == ("H", "h") and hemo.condition == "hemophilia A"
    assert build_pedigree_plan({"individuals": AR}).mode == "AR"                 # the only mode that fits
    assert build_pedigree_plan({"individuals": XD}).mode is None                   # AD and XD both fit
    dicts = [{"id": "dad", "sex": "male"}, {"id": "mum", "sex": "female", "spouse": "dad"}]
    assert len(parse_pedigree(dicts).couples) == 1


# ----- in projects --------------------------------------------------------------------------------------


def scene(params: dict[str, Any], actions: list[list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    acts = actions or [[]]
    return {"id": "x", "type": "pedigree", "params": params,
            "beats": [{"id": f"b{k}", "text": "the family chart and its analysis", "actions": a} for k, a in enumerate(acts)]}


def problems(make_project: Any, params: dict[str, Any], actions: list[list[dict[str, Any]]] | None = None) -> list[str]:
    return [p.message for p in project_problems(project_with(make_project, [scene(params, actions)], narration=NARRATION))]


def test_pedigree_scenes_are_validated(make_project) -> None:
    ar = {"individuals": AR, "carrier_frequency": "1/25"}
    ok = [[{"reveal": "generation:II"}, {"highlight": "person:II-2", "style": "box"}], [{"analyse": "modes"}],
          [{"deduce": "genotypes"}, {"analyse": "mode:XR"}], [{"risk": "risk"}]]
    assert problems(make_project, ar, ok) == []
    assert any("did you mean 'affected'" in m for m in problems(make_project, {"individuals": ["a: male afected"]}))
    assert any("has two fathers" in m for m in problems(make_project, {"individuals": ["a: male", "b: male", "c: male of a + b"]}))
    xd = {"individuals": XD}
    assert any("the chart fits AD, XD — say which with mode:" in m for m in problems(make_project, xd, [[{"deduce": "genotypes"}]]))
    assert problems(make_project, {**xd, "mode": "XD"}, [[{"deduce": "carriers"}]]) == []
    assert any("risk needs a proposed child" in m for m in problems(make_project, {**xd, "mode": "XD"}, [[{"risk": "risk"}]]))
    assert any("analyse acts on modes" in m for m in problems(make_project, ar, [[{"analyse": "genotypes"}]]))
    assert any("deduce is an action of pedigree scenes" in m
               for m in [p.message for p in project_problems(project_with(make_project, [{"id": "t", "type": "title", "params": {"title": "x"},
                                                                                           "beats": [{"text": "a", "actions": [{"deduce": "title"}]}]}],
                                                                       narration=NARRATION))])


# ----- renders ------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_pedigree_scenes_render(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [
        {"id": "auto", "type": "pedigree", "params": {"title": "XR", "individuals": XR + ["III-3: male", "IV-1: unknown proposed of III-3 + III-2"],
                                                       "analyse": True, "genotypes": True, "preset": "hemophilia_a"},
         "beats": [{"text": "grandparents"}, {"text": "children"}, {"text": "grandchildren"}, {"text": "the analysis and the risk"}]},
        {"id": "words", "type": "pedigree", "params": {"individuals": AR, "carrier_frequency": "1/25"},
         "beats": [{"text": "a daughter is affected", "actions": [{"reveal": "generation:II", "at": "@daughter"}]},
                   {"text": "two thirds and the risk", "actions": [{"deduce": "genotypes"}, {"analyse": "modes", "at": "@risk"},
                                                                  {"risk": "risk", "at": "@risk"}]}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 3.0})))
    auto = render(project, "auto", media, size)
    assert auto.visible == set(auto.ped.people) and auto.risk_shown and auto.analysed == set(auto.mode_rows)
    assert auto.is_shown("genotypes") and auto.is_shown("risk")
    words = render(project, "words", media, size)
    assert words.manual and words.risk_shown and words.deduced and words.is_shown("person:II-2") and words.is_shown("child")
