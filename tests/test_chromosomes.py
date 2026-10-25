"""Step 216 (DESIGN.md §96.9–96.11): genetic maps (map functions, two- and three-point test crosses
worked out from counts), human karyotypes (ISCN parsing and checks, derivatives, schematic
bands) and non-disjunction in ``cell_cycle`` meiosis; the ``linkage_map`` and ``karyotype``
scenes validated and rendered in 16:9 and 9:16."""

from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_actions import project_with, render
from vidgen.cellworld import division as dv
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.genetics import karyotype as kt
from vidgen.genetics import mapping as mp
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}
#: Griffiths' Drosophila three-point test cross (v vermilion, cv crossveinless, ct cut), as a
#: textbook table: the heterozygous female's gametes, read from the offspring.
VCVCT = {"v cv+ ct+": 580, "v+ cv ct": 592, "v cv ct+": 45, "v+ cv+ ct": 40, "v cv ct": 89, "v+ cv+ ct+": 94, "v cv+ ct": 3,
         "v+ cv ct+": 5}


# ----- map functions -------------------------------------------------------------------------------------


def test_map_functions_and_their_inverses() -> None:
    assert mp.rf_to_cm(Fraction(1, 10)) == pytest.approx(10.0)
    assert mp.rf_to_cm(0.2, "haldane") == pytest.approx(-50 * math.log(0.6))          # 25.54 cM
    assert mp.rf_to_cm(0.2, "kosambi") == pytest.approx(25 * math.log(1.4 / 0.6))     # 21.18 cM
    assert mp.rf_to_cm(0.5, "haldane") == math.inf and mp.rf_to_cm(0.5) == 50.0
    for f in ("haldane", "kosambi"):
        for r in (0.01, 0.1, 0.25, 0.4):
            assert mp.cm_to_rf(mp.rf_to_cm(r, f), f) == pytest.approx(r)
        assert mp.rf_to_cm(0.01, f) == pytest.approx(1.0, abs=0.02)                     # all agree for short distances
        assert mp.cm_to_rf(500, f) == pytest.approx(0.5, abs=1e-4)                       # far apart: independent assortment
    assert mp.cm_to_rf(70) == 0.5 and mp.map_function_key("Plain") == "none"
    with pytest.raises(VidgenError, match="cannot exceed 50 %"):
        mp.rf_to_cm(0.6)
    with pytest.raises(VidgenError, match="did you mean 'kosambi'"):
        mp.map_function_key("kosambbi")


# ----- test crosses ------------------------------------------------------------------------------------------


def test_three_point_cross_worked_out_by_hand() -> None:
    m = mp.analyse(["v", "cv", "ct"], VCVCT)
    n = 580 + 592 + 45 + 40 + 89 + 94 + 3 + 5
    assert m.total == n == 1448
    # parentals: the largest reciprocal pair; double crossovers: the smallest
    assert {mp.class_text(f, m.loci) for f in m.parental} == {"v + +", "+ cv ct"}
    assert {mp.class_text(f, m.loci) for f in m.double} == {"v + ct", "+ cv +"}
    # v + + (parental) and v + ct (double crossover) differ at ct only: ct is in the middle
    assert m.middle == "ct" and m.ordered == ("v", "ct", "cv")
    v_ct = 89 + 94 + 3 + 5          # v and ct recombined: v ct, + +, and both double crossovers
    ct_cv = 45 + 40 + 3 + 5
    assert [(iv.left, iv.right, iv.recombinants, iv.rf) for iv in m.intervals] == [("v", "ct", v_ct, Fraction(v_ct, n)),
                                                                                    ("ct", "cv", ct_cv, Fraction(ct_cv, n))]
    assert [round(iv.cm, 1) for iv in m.intervals] == [13.2, 6.4]
    assert m.outer_rf == Fraction(v_ct + ct_cv - 2 * 8, n)          # v–cv counted directly misses the double crossovers
    expected = Fraction(v_ct, n) * Fraction(ct_cv, n) * n
    assert m.expected_double == expected and m.observed_double == 8
    assert m.coincidence == 8 / expected and m.interference == 1 - 8 / expected
    assert round(float(m.coincidence), 2) == 0.65 and round(float(m.interference), 2) == 0.35
    assert m.positions() == pytest.approx({"v": 0.0, "ct": 100 * v_ct / n, "cv": 100 * (v_ct + ct_cv) / n})
    kinds = {mp.class_text(c.flags, m.loci, m.order): (c.kind, c.interval) for c in m.classes}
    assert kinds["v ct cv"] == ("single", 0) and kinds["v + cv"] == ("single", 1) and kinds["v ct +"] == ("double", None)
    # named alleles in any order, and positional ones, read the same
    again = mp.analyse(["cv", "ct", "v"], {"+ + v": 580, "cv ct +": 592, "cv + v": 45, "+ ct +": 40, "cv ct v": 89, "+ + +": 94,
                                           "ct v cv+": 3, "cv + +": 5})
    assert again.middle == "ct" and [iv.recombinants for iv in again.intervals] == [ct_cv, v_ct]
    # with Haldane's map function the intervals are longer
    assert mp.analyse(["v", "cv", "ct"], VCVCT, "haldane").intervals[0].cm > 13.2


def test_two_point_cross_phase_and_errors() -> None:
    rep = mp.analyse(["pr", "vg"], {"pr vg+": 1195, "pr+ vg": 1339, "pr vg": 151, "+ +": 154})
    assert rep.phase == "repulsion" and rep.intervals[0].rf == Fraction(305, 2839) and rep.middle is None
    cis = mp.analyse(["b", "vg"], {"b vg": 405, "+ +": 415, "b +": 85, "+ vg": 95})
    assert cis.phase == "coupling" and cis.intervals[0].rf == Fraction(180, 1000)
    with pytest.raises(VidgenError, match=r"1 class\(es\) missing: '\+ \+'"):
        mp.analyse(["b", "vg"], {"b vg": 405, "b +": 85, "+ vg": 95})
    loose = mp.analyse(["b", "vg"], {"b vg": 24, "+ +": 24, "b +": 26, "+ vg": 26})
    assert loose.intervals[0].rf == Fraction(48, 100) and any("near 50 %" in n for n in loose.notes())
    with pytest.raises(VidgenError, match="equally large"):
        mp.analyse(["b", "vg"], {"b vg": 25, "+ +": 25, "b +": 25, "+ vg": 25})
    with pytest.raises(VidgenError, match="did you mean 'vg'"):
        mp.analyse(["b", "vg"], {"b vgg": 405, "+ +": 415, "b +": 85, "+ vg": 95})
    with pytest.raises(VidgenError, match="listed twice"):
        mp.analyse(["b", "vg"], {"b vg": 1, "vg b": 2, "+ +": 415, "b +": 85, "+ vg": 95})
    with pytest.raises(VidgenError, match="equally small"):
        mp.analyse(["a", "b", "c"], {"a + +": 100, "+ b c": 100, "a b +": 5, "+ + c": 5, "a b c": 5, "+ + +": 5, "a + c": 20, "+ b +": 20})


def test_linkage_plans() -> None:
    plan = mp.build_linkage_plan({"loci": ["v", "cv", "ct"], "counts": VCVCT, "crossover": "double"})
    assert plan.mode == "counts" and plan.ordered == ("v", "ct", "cv") and plan.crossovers == (0, 1)
    assert "v-cv" in plan.interval_names()
    x = mp.build_linkage_plan({"map": {"w": 1.0, "y": 0, "v": 30.7}, "map_function": "haldane", "phase": "repulsion"})
    assert x.ordered == ("y", "w", "v") and x.homologues == ((False, True, False), (True, False, True))
    assert mp.measure_interval(x, "y-v")[2:] == pytest.approx((30.7, mp.cm_to_rf(30.7, "haldane")))
    for data, message in [({"map": {"y": 0, "w": 0}}, "both at 0 cM"), ({"loci": ["a", "b"]}, "one of them"),
                          ({"map": {"y": 0, "w": 1}, "loci": ["y"]}, "leave loci out"),
                          ({"loci": ["v", "cv", "ct"], "counts": VCVCT, "crossover": "v-cv"}, "not neighbours"),
                          ({"loci": ["v", "cv", "ct"], "counts": VCVCT, "phase": "coupling"}, "the counts show the phase")]:
        with pytest.raises(VidgenError, match=message):
            mp.build_linkage_plan(data)


# ----- karyotypes -------------------------------------------------------------------------------------------


def test_chromosome_data_and_bands() -> None:
    assert len(kt.NAMES) == 24 and sum(len(v) for v in kt.GROUPS.values()) == 24
    assert kt.LENGTH_MB["21"] < kt.LENGTH_MB["22"] and kt.chromosome_class("13") == "acrocentric"
    for c in kt.NAMES:
        bands = kt.bands(c)
        assert bands[0].start == 0 and bands[-1].end == pytest.approx(kt.LENGTH_MB[c])
        assert all(a.end == pytest.approx(b.start) for a, b in zip(bands, bands[1:]))
        assert bands[0].stain in ("gneg", "satellite") and bands[-1].stain in ("gneg", "gvar")     # pale ends (or a satellite / Yq12)
        cen = kt.CENTROMERE_MB[c]
        assert all(b.end <= cen + 1e-6 for b in bands if b.name.startswith("p"))
    assert {b.stain for b in kt.bands("21") if b.name in ("p12", "p13")} == {"stalk", "satellite"}
    assert next(b for b in kt.bands("9") if b.name == "q12").stain == "gvar"
    ref = kt.parse_band_label("7q31.2", "x")
    assert ref.chrom == "7" and ref.arm == "q" and kt.CENTROMERE_MB["7"] < ref.mid < kt.LENGTH_MB["7"]
    assert kt.parse_band_label("Xq28", "x").end == pytest.approx(kt.LENGTH_MB["X"])
    assert kt.parse_band_label("5p15.2", "x").mid < kt.parse_band_label("5p14", "x").mid          # p bands count outwards from the centromere
    for bad, message in [("5p16", "5p ends at band 5p15"), ("Xq29", "Xq ends at band Xq28"), ("7r31", "not a band"), ("23q11", "not a human chromosome")]:
        with pytest.raises(VidgenError, match=message):
            kt.parse_band_label(bad, "x")


@pytest.mark.parametrize("text, count, sex, slots, condition", [
    ("46,XX", 46, "XX", {}, None),
    ("47,XY,+21", 47, "XY", {"21": 3}, "Down syndrome (trisomy 21)"),
    ("47,XX,+18", 47, "XX", {"18": 3}, "Edwards syndrome (trisomy 18)"),
    ("45,X", 45, "X", {"X": 1, "Y": 0}, "Turner syndrome (monosomy X)"),
    ("47,XXY", 47, "XXY", {"X": 2, "Y": 1}, "Klinefelter syndrome"),
    ("46,XY,del(5)(p15.2)", 46, "XY", {"5": 2}, "cri-du-chat syndrome (5p deletion)"),
    ("46,XX,t(9;22)(q34;q11.2)", 46, "XX", {"9": 2, "22": 2}, "der(22) is the Philadelphia chromosome"),
    ("45,XX,rob(14;21)(q10;q10)", 45, "XX", {"14": 2, "21": 1}, "balanced carrier"),
    ("46,XY,rob(14;21)(q10;q10),+21", 46, "XY", {"14": 2, "21": 2}, "translocation Down syndrome"),
    ("46,XX,der(13;14)(q10;q10),+13", 46, "XX", {"13": 3, "14": 1}, "Patau syndrome (trisomy 13)"),   # translocation Patau
    ("46,XX,inv(9)(p12q13)", 46, "XX", {"9": 2}, None),
])
def test_iscn_karyotypes(text: str, count: int, sex: str, slots: dict[str, int], condition: str | None) -> None:
    k = kt.parse_karyotype(text)
    assert k.count == count == sum(len(v) for v in k.copies.values()) and k.sex == sex
    for s, n in slots.items():
        assert len(k.copies[s]) == n, s
    if condition is None:
        assert not any("syndrome" in c for c in k.conditions)
    else:
        assert any(c.startswith(condition) for c in k.conditions), k.conditions


def test_derivatives_are_made_of_segments() -> None:
    t = kt.parse_karyotype("46,XX,t(9;22)(q34;q11.2)")
    der9 = next(c for c in t.copies["9"] if not c.normal)
    der22 = next(c for c in t.copies["22"] if not c.normal)
    assert der9.name == "der(9)" and der22.name == "der(22)"
    assert der9.length + der22.length == pytest.approx(kt.LENGTH_MB["9"] + kt.LENGTH_MB["22"])     # balanced
    assert der22.length < kt.LENGTH_MB["22"] and [s.chrom for s in der22.segments] == ["22", "9"]
    assert der9.centromere == kt.CENTROMERE_MB["9"] and der22.centromere == kt.CENTROMERE_MB["22"]
    inv = next(c for c in kt.parse_karyotype("46,XY,inv(9)(p12q13)").copies["9"] if not c.normal)
    assert inv.segments[1].a > inv.segments[1].b and inv.length == pytest.approx(kt.LENGTH_MB["9"])
    assert inv.centromere != pytest.approx(kt.CENTROMERE_MB["9"])                 # pericentric: the arm ratio changes
    para = kt.parse_karyotype("46,XY,inv(3)(q21q26)")
    assert "paracentric" in para.abnormalities[0].reading and next(c for c in para.copies["3"] if not c.normal).centromere == kt.CENTROMERE_MB["3"]
    dup = next(c for c in kt.parse_karyotype("46,XY,dup(1)(q21q32)").copies["1"] if not c.normal)
    deleted = next(c for c in kt.parse_karyotype("46,XY,del(1)(q21q32)").copies["1"] if not c.normal)
    assert dup.length - kt.LENGTH_MB["1"] == pytest.approx(kt.LENGTH_MB["1"] - deleted.length)
    rob = next(c for c in kt.parse_karyotype("45,XX,rob(14;21)(q10;q10)").copies["14"] if not c.normal)
    assert rob.length == pytest.approx(kt.LENGTH_MB["14"] - kt.CENTROMERE_MB["14"] + kt.LENGTH_MB["21"] - kt.CENTROMERE_MB["21"])
    term = next(c for c in kt.parse_karyotype("46,XY,del(5)(p15.2)").copies["5"] if not c.normal)
    assert term.centromere < kt.CENTROMERE_MB["5"] and term.segments[0].a > 0


@pytest.mark.parametrize("text, message", [
    ("47,XX", "says 47 chromosomes but lists 46 .*write 46,XX"),
    ("46,XX,+21", "lists 47 .*write 47,XX,\\+21"),
    ("45,XX,rob(14;21)(q10;q10),+21", "lists 46"),
    ("46,xx", "letters in capitals"),
    ("46,YY", "no X chromosome"),
    ("XX,46", "starts with the chromosome count"),
    ("46,XY,5p-", "old short notation"),
    ("45,X/46,XX", "mosaic"),
    ("47,XX,+X", "written in the sex chromosomes"),
    ("46,XY,del(5)(p16)", "5p16 does not exist"),
    ("46,XX,t(22;9)(q11.2;q34)", "lower-numbered chromosome first"),
    ("46,XX,t(9;22)(q34)", "one band per chromosome"),
    ("46,XX,rob(9;21)", "not an acrocentric"),
    ("46,XX,rob(14;21)(q11;q11)", "q10;q10"),
    ("46,XX,del(Y)(q11)", "no chromosome Y"),
    ("46,XX,inv(9)(p12)", "takes 2 band"),
    ("46,XX,del(1)(p21q21)", "different arms"),
    ("46,XX,dell(1)(q21)", "did you mean 'del'"),
    ("46,XX,+23", "not a human chromosome"),
])
def test_iscn_errors(text: str, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        kt.parse_karyotype(text)


# ----- non-disjunction ----------------------------------------------------------------------------------------


def _labels(nd: tuple[str, int] | None, two_n: int = 4) -> list[str]:
    d = dv.plan_division(dv.DivisionSpec("meiosis", two_n, "animal", None, None, 1, nd))
    return sorted(str(it.extra) for it in d.keyframes[-1].items.values() if it.kind == "label")


def test_nondisjunction_in_meiosis_i_and_ii() -> None:
    assert _labels(None) == ["n = 2"] * 4
    assert _labels(("I", 0)) == sorted(["n + 1 = 3", "n + 1 = 3", "n − 1 = 1", "n − 1 = 1"])          # every gamete aneuploid
    assert _labels(("II", 1)) == sorted(["n + 1 = 3", "n − 1 = 1", "n = 2", "n = 2"])                 # half the gametes normal
    assert _labels(("I", 2), 6) == sorted(["n + 1 = 4", "n + 1 = 4", "n − 1 = 2", "n − 1 = 2"])
    assert dv.nondisjunction_cells("metaphase_i", 4, ("I", 0)) is None
    assert dv.nondisjunction_cells("cytokinesis_i", 4, ("I", 0)) == [(3, 6), (1, 2)]
    assert dv.nondisjunction_cells("anaphase_ii", 4, ("II", 0)) == [(3, 4), (4, 4)]           # the unsplit chromosome counts once
    assert dv.nondisjunction_cells("cytokinesis_ii", 4, ("II", 0)) == [(1, 1), (3, 3), (2, 2), (2, 2)]
    for nd in (("I", 0), ("II", 0)):
        shares = [Fraction(s) for s, _, _ in dv.gamete_outcomes(nd)]
        assert sum(shares) == 1
    assert dv.gamete_outcomes(("II", 0))[0] == ("1/2", "n", "2n (euploid)")
    assert "Non-disjunction" in dv.stage_captions("meiosis", "animal", 2, ("I", 0))["anaphase_i"][0]
    assert dv.expect_problem("meiosis", "telophase_i", 4, {"chromosomes": 2}, ("I", 0)) is not None
    assert dv.expect_problem("meiosis", "telophase_i", 4, {"cells": 2}, ("I", 0)) is None
    with pytest.raises(VidgenError, match="drawn for meiosis"):
        dv.check_spec(dv.DivisionSpec("mitosis", 4, nondisjunction=("I", 0)))
    with pytest.raises(VidgenError, match="pairs 1–2"):
        dv.check_spec(dv.DivisionSpec("meiosis", 4, nondisjunction=("I", 2)))


# ----- in projects ------------------------------------------------------------------------------------------


def problems(make_project: Any, scene: dict[str, Any]) -> list[str]:
    return [p.message for p in project_problems(project_with(make_project, [scene], narration=NARRATION))]


def one(kind: str, params: dict[str, Any], actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": "x", "type": kind, "params": params, "beats": [{"id": "b0", "text": "the chromosomes", "actions": actions or []}]}


def test_scenes_are_validated(make_project) -> None:
    three = {"loci": ["v", "cv", "ct"], "counts": VCVCT}
    assert problems(make_project, one("linkage_map", three, [{"reveal": "order"}, {"cross_over": "interval:v-ct"}])) == []
    assert problems(make_project, one("linkage_map", {"map": {"y": 0, "w": 1.5, "v": 33}}, [{"measure": "interval:y-v"}])) == []
    assert any("not neighbours" in m for m in problems(make_project, one("linkage_map", three, [{"cross_over": "interval:v-cv"}])))
    assert any("measure names one interval" in m for m in problems(make_project, one("linkage_map", three, [{"measure": "map"}])))
    assert any("class(es) missing" in m for m in problems(make_project, one("linkage_map", {"loci": ["a", "b"], "counts": {"a b": 3}})))
    assert problems(make_project, one("karyotype", {"karyotype": "46,XX,t(9;22)(q34;q11.2)"}, [{"rearrange": "change:1"}])) == []
    assert any("says 47 chromosomes" in m for m in problems(make_project, one("karyotype", {"karyotype": "47,XX"})))
    assert any("change:1…change:1" in m for m in problems(make_project, one("karyotype", {"karyotype": "47,XX,+21"}, [{"rearrange": "change:2"}])))
    assert any("has none" in m for m in problems(make_project, one("karyotype", {"karyotype": "46,XX"}, [{"rearrange": "changes"}])))
    assert any("Xq ends at band Xq28" in m for m in problems(make_project, one("karyotype", {"bands": {"Xq29": "F8"}})))
    meiosis = {"mode": "meiosis", "chromosomes": 4, "nondisjunction": {"division": "II", "pair": 2}}
    assert problems(make_project, one("cell_cycle", meiosis, [{"advance": "cell", "to": "cytokinesis_ii", "expect": {"cells": 4}}])) == []
    assert any("cells differ" in m for m in problems(make_project, one("cell_cycle", meiosis,
                                                                         [{"advance": "cell", "to": "cytokinesis_ii", "expect": {"chromosomes": 2}}])))
    assert any("belong" in m for m in problems(make_project, one("cell_cycle", {"nondisjunction": {"division": "I"}})))
    assert any("drawn for meiosis" in m for m in problems(make_project, one("cell_cycle", {"mode": "mitosis", "nondisjunction": {"division": "I"}})))
    assert any("I (homologues" in m for m in problems(make_project, one("cell_cycle", {**meiosis, "nondisjunction": {"division": "III"}})))


# ----- renders ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_chromosome_scenes_render(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [
        {"id": "three", "type": "linkage_map", "params": {"title": "Map", "loci": ["v", "cv", "ct"], "counts": VCVCT},
         "beats": [{"text": "chromosomes"}, {"text": "classes and order"}, {"text": "distances and the map"}]},
        {"id": "xmap", "type": "linkage_map", "params": {"map": {"y": 0, "w": 1.5, "v": 33}, "map_function": "kosambi", "crossover": "none"},
         "beats": [{"text": "a crossover", "actions": [{"cross_over": "interval:w-v"}]}, {"text": "a distance", "actions": [{"measure": "interval:y-v"}]}]},
        {"id": "kgram", "type": "karyotype", "params": {"karyotype": "47,XY,+21"}, "beats": [{"text": "trisomy"}, {"text": "reading"}]},
        {"id": "ideo", "type": "karyotype", "params": {"karyotype": "46,XX,t(9;22)(q34;q11.2)", "bands": {"9q34": "ABL1"}},
         "beats": [{"text": "nine and twenty-two", "actions": [{"rearrange": "change:1", "at": 0.5}]}, {"text": "the reading"}]},
        {"id": "seven", "type": "karyotype", "params": {"karyotype": "46,XY", "chromosomes": [7], "bands": {"7q31.2": "CFTR"}, "notation": False},
         "beats": [{"text": "the gene", "actions": [{"highlight": "band:7q31.2"}]}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 3.0})))
    three = render(project, "three", media, size)
    assert {"table", "classes", "order", "distances", "interference", "map"} <= three.done and three.order_now == three.plan.order
    assert any(len(set(row)) > 1 for row in three.seg_owner)          # recombinant chromatids
    xmap = render(project, "xmap", media, size)
    assert xmap.is_shown("map") and xmap.card_on is not None and xmap.measure_mark is not None
    kgram = render(project, "kgram", media, size)
    assert kgram.view == "karyogram" and 0 in kgram.marked and kgram.read_done
    ideo = render(project, "ideo", media, size)
    assert ideo.view == "ideogram" and 0 in ideo.marked and ideo.is_shown("change:1") and ideo.is_shown("band:9q34")
    # Step 221: normal chromosomes in 16:9 lie across the frame (pter at the left), labelled bands above
    seven = render(project, "seven", media, size)
    landscape = size[0] > size[1]
    assert seven.is_shown("band:7q31.2")
    seven_7 = seven.slot_groups["7"]
    assert (seven_7.width > seven_7.height) == landscape
