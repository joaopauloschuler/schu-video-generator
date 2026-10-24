"""Step 214: the ``cross`` scene type (DESIGN.md §96.7): the plan worked out from the cross engine
(gametes in textbook order with their homologue of origin, Punnett cells, genotype and phenotype
classes with exact fractions, ratios and percentages, P → F1 → F2, test and reciprocal crosses,
lethal classes, X / Y crosses, linkage, the branch diagram as a probability tree), the
chi-square test (own regularized gamma function), phenotype pictures, validation with reasons,
and renders in 16:9 and 9:16."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_actions import project_with, render
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.genetics import glyphs, punnett as pn, stats
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}
TRI = {"loci": [{"gene": "A", "trait": "seed shape", "alleles": {"A": "round", "a": "wrinkled"}},
                {"gene": "B", "trait": "seed colour", "alleles": {"B": "yellow", "b": "green"}},
                {"gene": "C", "trait": "flower colour", "alleles": {"C": "purple", "c": "white"}}]}


def plan(**data: Any) -> pn.CrossPlan:
    return pn.build_plan(data)


# ----- the chi-square test ---------------------------------------------------------------------------


def test_regularized_gamma_and_chi_square_p_values() -> None:
    scipy_special = pytest.importorskip("scipy.special")
    for a, x in [(0.5, 0.1), (0.5, 3.0), (1.0, 1.0), (1.5, 20.0), (5.0, 2.0), (10.0, 30.0), (20.0, 5.0)]:
        assert stats.regularized_gamma_q(a, x) == pytest.approx(float(scipy_special.gammaincc(a, x)), rel=1e-9, abs=1e-15)
    assert stats.regularized_gamma_q(2.0, 0.0) == 1.0
    assert stats.critical_value(1, 0.05) == pytest.approx(3.841, abs=1e-3)
    assert stats.critical_value(3, 0.05) == pytest.approx(7.815, abs=1e-3)
    assert stats.critical_value(2, 0.01) == pytest.approx(9.210, abs=1e-3)


def test_mendels_dihybrid_counts_fit_9_3_3_1() -> None:
    p = plan(preset="pea_dihybrid", parents=["RrYy", "RrYy"])
    counts = pn.match_observed(p, {"round yellow": 315, "Round, green": 108, "yellow wrinkled": 101, "wrinkled green": 32})
    chi = stats.chi_square([c.label for c in p.phenotypes], counts, [c.share for c in p.phenotypes])
    assert chi.total == 556 and chi.df == 3
    assert [r.expected for r in chi.rows] == [Fraction(1251, 4), Fraction(417, 4), Fraction(417, 4), Fraction(139, 4)]
    assert float(chi.statistic) == pytest.approx(0.470024, abs=1e-6)
    assert chi.p == pytest.approx(0.9254, abs=1e-4) and not chi.rejected and stats.p_text(chi.p) == "p = 0.925"
    bad = stats.chi_square(["a", "b"], [60, 40], [Fraction(3, 4), Fraction(1, 4)])
    assert bad.rejected and bad.p < 0.001 and stats.p_text(bad.p) == "p < 0.001"
    small = stats.chi_square(["a", "b"], [9, 1], [Fraction(3, 4), Fraction(1, 4)])
    assert small.small == ("b",)
    with pytest.raises(VidgenError, match="add up to 0"):
        stats.chi_square(["a", "b"], [0, 0], [Fraction(1, 2), Fraction(1, 2)])


def test_observed_counts_are_matched_to_the_classes() -> None:
    p = plan(preset="pea_dihybrid", parents=["RrYy", "RrYy"])
    assert pn.match_observed(p, [315, 108, 101, 32]) == [315, 108, 101, 32]
    with pytest.raises(VidgenError, match="missing: wrinkled, green"):
        pn.match_observed(p, {"round yellow": 1, "round green": 1, "wrinkled yellow": 1})
    with pytest.raises(VidgenError, match="did you mean 'round, green'"):
        pn.match_observed(p, {"round gren": 1})
    with pytest.raises(VidgenError, match="3 counts for 4 classes"):
        pn.match_observed(p, [1, 2, 3])
    with pytest.raises(VidgenError, match="not a count"):
        pn.match_observed(p, [1, 2, 3, -4])


# ----- the plan -----------------------------------------------------------------------------------


def test_text_helpers() -> None:
    assert pn.fraction_text(Fraction(9, 16)) == "9/16" and pn.fraction_text(Fraction(1)) == "1"
    assert pn.percent_text(Fraction(9, 16)) == "56.25 %" and pn.percent_text(Fraction(1, 4)) == "25 %"
    assert pn.percent_text(Fraction(2, 3)) == "≈ 66.7 %" and pn.percent_text(Fraction(83, 200)) == "41.5 %"
    assert pn.normalize_label("Yellow round") == pn.normalize_label("round, yellow")


def test_monohybrid_from_the_p_generation() -> None:
    p = plan(preset="pea_seed_shape", P=["RR", "rr"])
    assert p.p_line is not None and "all" in p.p_line and p.offspring == "F<sub>2</sub>"
    assert [v.text for v in p.eggs] == ["R", "r"] and [v.frequency for v in p.eggs] == [Fraction(1, 2)] * 2
    assert [c.ascii for c in p.cells] == ["RR", "Rr", "Rr", "rr"] and p.uniform and p.show == "punnett"
    assert p.genotype_ratio == (1, 2, 1) and p.phenotype_ratio == (3, 1)
    assert [(c.label, c.share, c.count, c.cells) for c in p.phenotypes] == [
        ("round", Fraction(3, 4), 3, ((1, 1), (1, 2), (2, 1))), ("wrinkled", Fraction(1, 4), 1, ((2, 2),))]
    with pytest.raises(VidgenError, match="more than one F1 genotype"):
        plan(preset="pea_seed_shape", P=["Rr", "rr"])
    with pytest.raises(VidgenError, match="leave out parents"):
        plan(preset="pea_seed_shape", P=["RR", "rr"], parents=["Rr", "Rr"])


def test_dihybrid_square_counts_9_3_3_1_and_alleles_keep_their_homologue() -> None:
    p = plan(preset="pea_dihybrid", parents=["RrYy", "RrYy"])
    assert [v.text for v in p.eggs] == ["RY", "Ry", "rY", "ry"]
    assert [a.source for a in p.eggs[1].alleles] == [0, 1]        # R from the first homologue, y from the second
    assert len(p.cells) == 16 and p.cell(4, 4).ascii == "rryy"
    assert [c.count for c in p.phenotypes] == [9, 3, 3, 1] and p.phenotype_ratio == (9, 3, 3, 1)
    assert len(p.genotypes) == 9 and p.genotype_ratio == (1, 2, 1, 2, 4, 2, 1, 2, 1)
    assert p.notes == ()


def test_test_and_reciprocal_crosses() -> None:
    p = plan(preset="pea_dihybrid", parents=["RrYy"], kind="test")
    assert p.roles == ("", "tester") and pn.genotype_key(p.system, p.father) == "rryy"
    assert len(p.sperm) == 1 and p.phenotype_ratio == (1, 1, 1, 1) and "test cross" in p.notes[0]
    with pytest.raises(VidgenError, match="takes one parent"):
        plan(preset="pea_dihybrid", parents=["RrYy", "RrYy"], kind="test")
    forward = plan(preset="drosophila_white", mother="X^w X^w", father="X^{w^+} Y")
    back = plan(preset="drosophila_white", mother="X^w X^w", father="X^{w^+} Y", kind="reciprocal")
    assert [c.label for c in forward.phenotypes] == ["red, female", "white, male"]
    assert [c.label for c in back.phenotypes] == ["red, female", "red, male"] and "reciprocal" in back.notes[0]
    f2 = plan(preset="drosophila_white", P=["X^w X^w", "X^{w^+} Y"])
    assert f2.phenotype_ratio == (1, 1, 1, 1) and len(f2.eggs) == 2 and [v.text for v in f2.sperm] == ["Xʷ", "Y"]


def test_sex_linked_and_lethal_crosses() -> None:
    p = plan(preset="hemophilia_a", parents=["X^H Y", "X^H X^h"])     # any order: the sex chromosomes say
    assert p.mother.sex == "female" and [v.text for v in p.sperm] == ["Xᴴ", "Y"]
    assert [(c.label, c.share) for c in p.phenotypes] == [("normal clotting, female", Fraction(1, 2)), ("normal clotting, male", Fraction(1, 4)),
                                                         ("hemophilia A, male", Fraction(1, 4))]
    with pytest.raises(VidgenError, match="both parents are females"):
        plan(preset="hemophilia_a", parents=["X^H X^h", "X^H X^H"])
    mice = plan(preset="yellow_mouse", parents=["A^Y A", "A^Y A"])
    assert mice.lethal == Fraction(1, 4) and mice.phenotype_ratio == (2, 1) and mice.genotype_ratio == (1, 2, 1)
    assert mice.cell(1, 1).lethal and mice.genotypes[0].lethal and mice.genotypes[0].survivors == 0
    assert [c.count for c in mice.phenotypes] == [2, 1] and "dies before birth" in mice.notes[0]


def test_epistasis_and_linkage() -> None:
    labs = plan(preset="labrador", parents=["BbEe", "BbEe"])
    assert labs.phenotype_ratio == (9, 3, 4) and [c.count for c in labs.phenotypes] == [9, 3, 4] and "recessive epistasis" in labs.notes[0]
    flies = plan(preset="drosophila_b_vg", mother="b^+vg^+/bvg", father="bvg/bvg")
    assert [(v.text, v.frequency, v.recombinant) for v in flies.eggs] == [
        ("b⁺ vg⁺", Fraction(83, 200), False), ("b vg", Fraction(83, 200), False), ("b⁺ vg", Fraction(17, 200), True),
        ("b vg⁺", Fraction(17, 200), True)]
    assert not flies.uniform and flies.phenotype_ratio == (83, 17, 17, 83) and all(c.count is None for c in flies.phenotypes)
    assert "recombination frequency 17 %" in flies.notes[0]
    males = plan(preset="drosophila_b_vg", mother="bvg/bvg", father="b^+vg^+/bvg")
    assert males.phenotype_ratio == (1, 1) and "no crossing over" in males.notes[0]


def test_branch_diagrams_and_size_limits() -> None:
    tri = plan(**TRI, parents=["AaBbCc", "AaBbCc"])
    assert tri.show == "branch" and tri.tree is not None and tri.tree.levels == ("seed shape", "seed colour", "flower colour")
    leaves = tri.tree.leaves
    assert len(leaves) == 8 and leaves[0].probability == Fraction(27, 64) and leaves[0].conditional == Fraction(3, 4)
    assert tri.phenotype_ratio == (27, 9, 9, 3, 9, 3, 3, 1)
    assert len(plan(**TRI, parents=["AaBbCc", "AaBbCc"], show="punnett").cells) == 64
    with pytest.raises(VidgenError, match="27 classes"):
        plan(**TRI, parents=["AaBbCc", "AaBbCc"], branch="genotypes")
    gt = plan(preset="pea_dihybrid", parents=["RrYy", "RrYy"], show="branch", branch="genotypes")
    assert gt.tree.levels == ("R", "Y") and [n.markup for n in gt.tree.nodes[:3]] == ["<i>R</i><i>R</i>", "<i>R</i><i>r</i>", "<i>r</i><i>r</i>"]
    sexed = plan(preset="hemophilia_a", parents=["X^H X^h", "X^H Y"], show="branch")
    assert sexed.tree.levels == ("sex", "blood clotting") and sexed.tree.nodes[0].conditional == Fraction(1, 2)
    four = {"loci": [*TRI["loci"], {"gene": "D", "trait": "height", "alleles": {"D": "tall", "d": "dwarf"}}]}
    with pytest.raises(VidgenError, match="more than 8 × 8 is unreadable"):
        plan(**four, parents=["AaBbCcDd", "AaBbCcDd"], show="punnett")


def test_phenotype_pictures() -> None:
    p = plan(preset="pea_dihybrid", parents=["RrYy", "RrYy"])
    assert [(g.subject, g.attrs["shape"], g.attrs["colour"]) for c in p.phenotypes for g in c.glyphs] == [
        ("pea", "round", "yellow"), ("pea", "round", "green"), ("pea", "wrinkled", "yellow"), ("pea", "wrinkled", "green")]
    fly = plan(preset="drosophila_b_vg", mother="b^+vg^+/bvg", father="bvg/bvg").phenotypes[1].glyphs
    assert [(g.subject, g.attrs["body"], g.attrs["wings"]) for g in fly] == [("fly", "grey", "vestigial")]
    assert [g.attrs["group"] for c in plan(preset="abo", parents=["I^A i", "I^B i"]).phenotypes for g in c.glyphs] == ["A", "B", "AB", "O"]
    assert [g.attrs["affected"] for c in plan(preset="hemophilia_a", parents=["X^H X^h", "X^H Y"]).phenotypes for g in c.glyphs] == ["no", "no", "yes"]
    assert glyphs.class_glyphs(["eye colour", "body colour"], ["white", "black"], [None, None])[0].attrs == {
        "body": "black", "eye": "white", "body_hex": glyphs.COLOURS["black"], "eye_hex": glyphs.COLOURS["white"]}
    assert glyphs.trait_attr("fur", "chinchilla") == ("coat", "colour", "chinchilla")


# ----- in projects --------------------------------------------------------------------------------


def scene(params: dict[str, Any], actions: list[list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    acts = actions or [[]]
    return {"id": "x", "type": "cross", "params": params,
            "beats": [{"id": f"b{k}", "text": "each parent makes gametes and the square fills", "actions": a} for k, a in enumerate(acts)]}


def problems(make_project: Any, params: dict[str, Any], actions: list[list[dict[str, Any]]] | None = None) -> list[str]:
    return [p.message for p in project_problems(project_with(make_project, [scene(params, actions)], narration=NARRATION))]


def test_cross_scenes_are_validated(make_project) -> None:
    di = {"preset": "pea_dihybrid", "parents": ["RrYy", "RrYy"]}
    ok = [[{"form_gametes": "both"}], [{"fill": "row1", "by": "cell"}, {"fill": "row*"}], [{"count": "phenotypes"}, {"ratio": "phenotypes"}],
          [{"highlight": "cells:wrinkled, green", "style": "box"}, {"dim": "class:round, yellow"}]]
    assert problems(make_project, di, ok) == []
    assert any("did you mean 'pea_dihybrid'" in m for m in problems(make_project, {"preset": "pea_dihybrd", "parents": ["Rr", "Rr"]}))
    assert any("'RrYx'" in m for m in problems(make_project, {"preset": "pea_dihybrid", "parents": ["RrYx", "RrYy"]}))
    assert any("cell1.1 is filled already" in m for m in problems(make_project, di, [[{"fill": "cell1.1"}], [{"fill": "cell1.1"}]]))
    assert any("formed already" in m for m in problems(make_project, di, [[{"fill": "square"}], [{"form_gametes": "parent1"}]]))
    assert any("counted already" in m for m in problems(make_project, di, [[{"count": "phenotypes"}], [{"count": "phenotypes"}]]))
    assert any("fill: tree" in m for m in problems(make_project, {**TRI, "parents": ["AaBbCc", "AaBbCc"]}, [[{"fill": "all"}, {"fill": "row1"}]]))
    assert any("unknown target 'genotypes'" in m for m in problems(make_project, {**TRI, "parents": ["AaBbCc", "AaBbCc"]}, [[{"count": "genotypes"}]]))
    assert any("needs the observed counts" in m or "unknown target 'test'" in m for m in problems(make_project, di, [[{"chi_square": "test"}]]))
    assert any("alpha: belongs to the chi-square test" in m for m in problems(make_project, {**di, "alpha": 0.01}))
    assert any("form_gametes is an action of cross scenes" in m
               for m in [p.message for p in project_problems(project_with(make_project, [{"id": "t", "type": "title", "params": {"title": "x"},
                                                                                           "beats": [{"text": "a", "actions": [{"form_gametes": "title"}]}]}],
                                                                       narration=NARRATION))])
    assert problems(make_project, {**di, "observed": {"round yellow": 315, "round green": 108, "wrinkled yellow": 101, "wrinkled green": 32}},
                    [[{"chi_square": "test"}]]) == []


# ----- renders ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_cross_scenes_render(size: tuple[int, int], make_project, media: Path) -> None:
    observed = {"round yellow": 315, "round green": 108, "wrinkled yellow": 101, "wrinkled green": 32}
    scenes = [
        {"id": "auto", "type": "cross", "params": {"title": "F2", "preset": "pea_seed_shape", "P": ["RR", "rr"]},
         "beats": [{"text": "gametes form and the square fills"}, {"text": "three to one"}]},
        {"id": "words", "type": "cross", "params": {"preset": "pea_dihybrid", "parents": ["RrYy", "RrYy"], "observed": observed},
         "beats": [{"text": "four kinds of gametes fill the square", "actions": [{"form_gametes": "both"}, {"fill": "square", "by": "row", "at": "@fill"}]},
                   {"text": "nine three three one and the test", "actions": [{"ratio": "phenotypes"}, {"chi_square": "test", "at": "@test"}]}]},
        {"id": "tree", "type": "cross", "params": {**TRI, "parents": ["AaBbCc", "AaBbCc"]},
         "beats": [{"text": "eight gametes and a branch diagram"}, {"text": "twenty seven to one"}]},
        {"id": "dies", "type": "cross", "params": {"preset": "yellow_mouse", "parents": ["A^Y A", "A^Y A"]},
         "beats": [{"text": "two to one"}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 3.0})))
    auto = render(project, "auto", media, size)
    assert len(auto.filled) == 4 and auto.counted == {"genotypes", "phenotypes"} and auto.ratios == {"genotypes", "phenotypes"}
    hidden = [t.name for t in auto.targets if not auto.is_shown(t)]
    # 16:9: both tables fit the panel; 9:16: the phenotypes replace the genotypes
    assert hidden == ([] if size[0] > size[1] else ["genotypes", "genotype:RR", "genotype:Rr", "genotype:rr"])
    words = render(project, "words", media, size)
    assert len(words.filled) == 16 and words.counted == {"phenotypes"} and words.chi_shown and words.manual
    assert words.is_shown("chi_square") and not words.is_shown("genotypes")
    tree = render(project, "tree", media, size)
    assert tree.grown == 3 and tree.is_shown("phenotypes") and tree.is_shown("class:wrinkled, green, white")
    dies = render(project, "dies", media, size)
    assert dies.is_shown("cell1.1") and dies.is_shown("notes")
