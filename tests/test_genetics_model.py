"""The genetics model and the exact cross engine (Step 213, DESIGN §96): textbook ratios computed
exactly, notation, validation with reasons, modes of inheritance. No rendering."""

from __future__ import annotations

import subprocess
import sys
from fractions import Fraction as F

import pytest

from vidgen.errors import VidgenError
from vidgen.genetics import (
    PRESETS, build_system, cross, gamete_text, gametes, genotype_text, mode_of, parse_genotype, parse_mode, ratio, ratio_text,
    reciprocal, symbol_markup, symbol_text, test_cross, make_tester,
)
from vidgen.genetics.model import as_fraction


def preset(name: str):
    return build_system({"preset": name})


def shares(result) -> dict[str, F]:
    return {ph.text: p for ph, p in result.phenotypes.items()}


def two_loci(**extra):
    spec = {"loci": [{"gene": "A", "alleles": {"A": "A-shape", "a": "a-shape"}},
                     {"gene": "B", "alleles": {"B": "B-colour", "b": "b-colour"}}]}
    spec.update(extra)
    return build_system(spec)


def test_model_imports_without_manim() -> None:
    code = "import sys, vidgen.genetics; print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ----- Mendelian ratios -----------------------------------------------------------------------------


def test_monohybrid_three_to_one_and_one_two_one() -> None:
    s = preset("pea_seed_shape")
    r = cross(s, "Rr", "Rr")
    assert r.phenotype_ratio == (3, 1) and shares(r) == {"round": F(3, 4), "wrinkled": F(1, 4)}
    assert r.genotype_ratio == (1, 2, 1)
    assert [genotype_text(s, g) for g in r.genotypes] == ["RR", "Rr", "rr"]


def test_dihybrid_nine_three_three_one_and_gametes() -> None:
    s = preset("pea_dihybrid")
    r = cross(s, "RrYy", "R/r Y/y")
    assert r.phenotype_ratio == (9, 3, 3, 1)
    assert [ph.text for ph in r.phenotypes] == ["round, yellow", "round, green", "wrinkled, yellow", "wrinkled, green"]
    assert r.genotype_ratio == (1, 2, 1, 2, 4, 2, 1, 2, 1)
    assert sorted(gamete_text(s, g) for g in r.eggs) == ["RY", "Ry", "rY", "ry"]
    assert set(r.eggs.values()) == {F(1, 4)}


def test_trihybrid_twenty_seven_nine() -> None:
    s = build_system({"loci": [{"gene": g, "alleles": {g: f"{g} dominant", g.lower(): f"{g} recessive"}} for g in "ABC"]})
    assert cross(s, "AaBbCc", "AaBbCc").phenotype_ratio == (27, 9, 9, 3, 9, 3, 3, 1)


def test_test_cross_one_one_one_one() -> None:
    s = preset("pea_dihybrid")
    assert genotype_text(s, make_tester(s, "RrYy")) == "rryy"
    r = test_cross(s, "RrYy")
    assert r.phenotype_ratio == (1, 1, 1, 1)
    assert test_cross(s, "RRYy").phenotype_ratio == (1, 1)


def test_incomplete_dominance_one_two_one() -> None:
    s = preset("snapdragon")
    r = cross(s, "C^R C^W", "C^{R}C^W")
    assert [ph.text for ph in r.phenotypes] == ["red", "pink", "white"] and r.phenotype_ratio == (1, 2, 1)
    assert cross(s, "C^RC^R", "C^WC^W").phenotype_ratio == (1,)


def test_abo_codominance_and_multiple_alleles() -> None:
    s = preset("abo")
    r = cross(s, "I^A i", "I^B i")
    assert shares(r) == {"A": F(1, 4), "B": F(1, 4), "AB": F(1, 4), "O": F(1, 4)}
    r = cross(s, "I^AI^B", "I^AI^B")
    assert [ph.text for ph in r.phenotypes] == ["A", "B", "AB"] and r.phenotype_ratio == (1, 1, 2)
    assert shares(cross(s, "I^A I^B", "ii")) == {"A": F(1, 2), "B": F(1, 2)}
    assert genotype_text(s, parse_genotype(s, "I^A i")) == "Iᴬi"


def test_dominance_series() -> None:
    s = preset("rabbit_coat")
    r = cross(s, "c^{ch} c^h", "c^h c")
    assert shares(r) == {"chinchilla": F(1, 2), "himalayan": F(1, 2)}
    assert cross(s, "Cc", "c^{ch}c").phenotype_ratio == (2, 1, 1)


# ----- epistasis --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name, ratio_, classes", [
    ("labrador", (9, 3, 4), ["black", "brown", "yellow"]),
    ("squash_colour", (12, 3, 1), ["white", "yellow", "green"]),
    ("chicken_feathers", (13, 3), ["white", "coloured"]),
    ("shepherds_purse", (15, 1), ["triangular", "ovoid"]),
    ("sweet_pea", (9, 7), ["purple", "white"]),
    ("squash_shape", (9, 6, 1), ["disc", "sphere", "long"]),
])
def test_epistasis_ratios(name: str, ratio_: tuple[int, ...], classes: list[str]) -> None:
    s = preset(name)
    r = cross(s, *PRESETS[name].example)
    assert r.phenotype_ratio == ratio_
    assert [ph.text for ph in r.phenotypes] == classes


def test_epistasis_test_cross_ratios() -> None:
    assert test_cross(preset("labrador"), "BbEe").phenotype_ratio == (1, 1, 2)
    assert test_cross(preset("sweet_pea"), "CcPp").phenotype_ratio == (1, 3)
    assert test_cross(preset("shepherds_purse"), "AaBb").phenotype_ratio == (3, 1)


# ----- lethal alleles, penetrance --------------------------------------------------------------------


def test_recessive_lethal_two_to_one() -> None:
    s = preset("yellow_mouse")
    r = cross(s, "A^Y A", "A^Y/A")
    assert r.lethal == F(1, 4)
    assert shares(r) == {"yellow": F(2, 3), "agouti": F(1, 3)} and r.phenotype_ratio == (2, 1)
    assert sum(r.genotypes.values()) == 1 and sum(r.zygotes.values()) == 1
    assert genotype_text(s, next(iter(r.genotypes))) == "A^Y/A"


def test_penetrance_is_exact() -> None:
    s = build_system({"loci": [{"gene": "P", "trait": "digits", "alleles": {"P": "polydactyly", "p": "five digits"},
                                "penetrance": "4/5", "normal": "five digits"}]})
    r = cross(s, "Pp", "pp")
    assert shares(r) == {"polydactyly": F(2, 5), "five digits": F(3, 5)}
    s2 = build_system({"loci": [{"gene": "P", "alleles": {"P": "polydactyly", "p": "five digits"},
                                 "penetrance": {"polydactyly": 0.8}, "normal": "five digits"}]})
    assert shares(cross(s2, "Pp", "Pp"))["polydactyly"] == F(3, 4) * F(4, 5)


# ----- sex chromosomes, Y, mtDNA ------------------------------------------------------------------------


def test_x_linked_recessive_both_directions() -> None:
    s = preset("drosophila_white")
    white_mother = cross(s, "X^w X^w", "X^{w^+} Y")
    assert shares(white_mother) == {"female: red": F(1, 2), "male: white": F(1, 2)}
    m, f = reciprocal(s, "X^w X^w", "X^{w^+} Y")
    assert genotype_text(s, m, "ascii") == "X^{w^+} X^{w^+}" and genotype_text(s, f, "ascii") == "X^w Y"
    red_mother = cross(s, m, f)
    assert shares(red_mother) == {"female: red": F(1, 2), "male: red": F(1, 2)}
    f1 = list(red_mother.genotypes)
    f2 = cross(s, f1[0], f1[1])
    assert f2.phenotype_share("white") == F(1, 4) and f2.phenotype_share("white", sex="female") == 0
    assert f2.phenotype_share("white", sex="male") == F(1, 4)


def test_hemophilia_carrier_mother() -> None:
    s = preset("hemophilia_a")
    r = cross(s, "X^H X^h", "X^H Y")
    assert r.phenotype_share("hemophilia A") == F(1, 4)
    sons = sum(p for ph, p in r.phenotypes.items() if ph.sex == "male")
    assert r.phenotype_share("hemophilia A", sex="male") / sons == F(1, 2)
    affected_father = cross(s, "X^H X^H", "X^hY")
    daughters = [g for g in affected_father.genotypes if g.sex == "female"]
    assert [genotype_text(s, g) for g in daughters] == ["XᴴXʰ"]
    assert mode_of(s, "H", "hemophilia A").code == "XR" and mode_of(s, "H", "normal clotting").code == "XD"


def test_y_linked_and_mitochondrial() -> None:
    s = build_system({"loci": [{"gene": "T", "chromosome": "Y", "alleles": {"T^+": "unaffected", "T": "hairy ears"}}]})
    r = cross(s, "X X", "X Y^T")
    assert shares(r) == {"female: unaffected": F(1, 2), "male: hairy ears": F(1, 2)}
    assert mode_of(s, "T", "hairy ears").code == "YL"
    mt = build_system({"loci": [{"gene": "m", "chromosome": "mitochondrial", "alleles": {"m^+": "normal vision", "m": "optic neuropathy"}}]})
    assert shares(cross(mt, "m", "m^+")) == {"optic neuropathy": F(1)}
    assert shares(cross(mt, "m^+", "m")) == {"normal vision": F(1)}
    assert mode_of(mt, "m", "optic neuropathy").code == "MT"


def test_sex_option_follows_sexes_of_autosomal_cross() -> None:
    s = build_system({"loci": [{"gene": "A", "alleles": {"A": "tall", "a": "short"}}], "sex": "XY"})
    r = cross(s, "Aa X X", "Aa XY")
    assert ratio(r.phenotypes.values()) == (3, 1, 3, 1)


# ----- linkage ---------------------------------------------------------------------------------------------


def test_linkage_coupling_and_repulsion_test_crosses() -> None:
    s = two_loci(linkage=[{"loci": ["A", "B"], "rf": 0.2}])
    coupling = gametes(s, parse_genotype(s, "AB/ab"))
    assert {gamete_text(s, g): p for g, p in coupling.items()} == {"AB": F(2, 5), "ab": F(2, 5), "Ab": F(1, 10), "aB": F(1, 10)}
    r = test_cross(s, "AB/ab")
    assert shares(r) == {"A-shape, B-colour": F(2, 5), "A-shape, b-colour": F(1, 10), "a-shape, B-colour": F(1, 10),
                         "a-shape, b-colour": F(2, 5)}
    repulsion = shares(test_cross(s, "Ab/aB"))
    assert repulsion["A-shape, b-colour"] == F(2, 5) and repulsion["A-shape, B-colour"] == F(1, 10)
    f2 = cross(s, "AB/ab", "AB/ab")
    assert f2.phenotype_share("a-shape", "b-colour") == (F(4, 5) / 2) ** 2


def test_unlinked_is_rf_half() -> None:
    s = two_loci(linkage=[{"loci": ["A", "B"], "rf": "50%"}])
    assert test_cross(s, "AB/ab").phenotype_ratio == (1, 1, 1, 1)


def test_morgan_b_vg_and_no_crossing_over_in_males() -> None:
    s = preset("drosophila_b_vg")
    female = test_cross(s, "b^+vg^+/bvg")
    assert female.phenotype_share("grey body", "vestigial wings") + female.phenotype_share("black body", "normal wings") == F(17, 100)
    male = cross(s, "bvg/bvg", "b^+vg^+/bvg")
    assert male.phenotype_ratio == (1, 1)
    assert genotype_text(s, parse_genotype(s, "b^+vg^+/bvg")) == "b⁺ vg⁺/b vg"


def test_three_point_with_coincidence() -> None:
    spec = {"loci": [{"gene": g, "alleles": {g: g, g.lower(): g.lower()}} for g in "ABC"],
            "linkage": [{"loci": ["A", "B", "C"], "rf": [0.1, 0.2], "coincidence": 0.5}]}
    s = build_system(spec)
    g = {gamete_text(s, k): p for k, p in gametes(s, parse_genotype(s, "ABC/abc")).items()}
    double = F(1, 2) * F(1, 10) * F(1, 5)
    assert g["AbC"] == g["aBc"] == double / 2
    assert g["Abc"] == (F(1, 10) - double) / 2 and g["ABc"] == (F(1, 5) - double) / 2
    assert g["ABC"] == (1 - F(1, 10) - F(1, 5) + double) / 2
    assert sum(g.values()) == 1


def test_x_linked_loci_recombine_in_females_only() -> None:
    s = build_system({"loci": [{"gene": "w", "chromosome": "X", "alleles": {"w^+": "red", "w": "white"}},
                               {"gene": "y", "chromosome": "X", "alleles": {"y^+": "grey", "y": "yellow"}}],
                      "linkage": [{"loci": ["w", "y"], "rf": 0.01}]})
    eggs = {gamete_text(s, k): p for k, p in gametes(s, parse_genotype(s, "X^{w^+,y^+} X^{w,y}")).items()}
    assert eggs["X^(w⁺,y)"] == F(1, 200)
    sperm = gametes(s, parse_genotype(s, "X^{w,y} Y"))
    assert sorted(sperm.values()) == [F(1, 2), F(1, 2)]


# ----- notation --------------------------------------------------------------------------------------------


def test_notation() -> None:
    assert symbol_text("I^A") == "Iᴬ" and symbol_text("w^+") == "w⁺" and symbol_text("c^ch") == "cᶜʰ"
    assert symbol_markup("I^A") == "<i>I<sup>A</sup></i>"
    assert symbol_text("A^Y") == "A^Y"                 # no superscript capital Y in Unicode
    s = preset("hemophilia_a")
    g = parse_genotype(s, "X^H/X^h")
    assert genotype_text(s, g) == "XᴴXʰ" and genotype_text(s, g, "markup") == "X<sup><i>H</i></sup>X<sup><i>h</i></sup>"


@pytest.mark.parametrize("name", list(PRESETS))
def test_written_forms_read_back(name: str) -> None:
    s = preset(name)
    r = cross(s, *PRESETS[name].example)
    for g in r.genotypes:
        assert parse_genotype(s, genotype_text(s, g, "ascii")) == g


def test_ratio_and_fractions() -> None:
    assert ratio([F(9, 16), F(3, 16), F(1, 4)]) == (9, 3, 4) and ratio_text((9, 3, 4)) == "9 : 3 : 4"
    assert as_fraction(0.1, "w", "rf") == F(1, 10) and as_fraction("17%", "w", "rf") == F(17, 100)
    assert as_fraction("1/6", "w", "p") == F(1, 6)


def test_modes() -> None:
    assert parse_mode("autosomal recessive", "w").code == "AR" and parse_mode("X-linked dominant", "w").code == "XD"
    s = preset("pea_seed_shape")
    assert mode_of(s, "R", "round").code == "AD" and mode_of(s, "R", "wrinkled").code == "AR"
    with pytest.raises(VidgenError, match="did you mean"):
        parse_mode("autosomal recesive", "w")
    with pytest.raises(VidgenError, match="complete dominance"):
        mode_of(preset("abo"), "I", "O")


# ----- validation --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("system, text, sex, message", [
    ("pea_dihybrid", "RrYx", None, "'x' is not an allele of any locus \\(alleles: R, Y, r, y\\)"),
    ("drosophila_b_vg", "b^+vg^+/bvf", None, "'vf' is not an allele of any locus.*did you mean 'vg'"),
    ("pea_dihybrid", "Rr", None, "locus Y .* is missing"),
    ("pea_dihybrid", "RrrYy", None, "locus R has 3 alleles"),
    ("hemophilia_a", "Hh", None, "H is X-linked: write it on its chromosome"),
    ("hemophilia_a", "X^H Y", "female", "has a Y chromosome: a female is XX"),
    ("hemophilia_a", "X^H X^h", "male", "a male is XY"),
    ("hemophilia_a", "X^H X^h Y", None, "XXY"),
    ("hemophilia_a", "X^H X^q", None, "not an allele of the X-linked loci"),
    ("drosophila_b_vg", "b^+/b vg^+/vg", None, "linked .* write the phase"),
    ("pea_seed_shape", "X^R X^r", None, "no X-linked locus"),
    ("abo", "I^A I^C", None, "'I\\^C' is not an allele"),
])
def test_genotype_errors(system: str, text: str, sex: str | None, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        parse_genotype(preset(system), text, "parents[0]", sex)


def test_cross_checks_the_sexes() -> None:
    with pytest.raises(VidgenError, match="mother.*a female is XX"):
        cross(preset("hemophilia_a"), "X^H Y", "X^H Y")


@pytest.mark.parametrize("spec, message", [
    ({"loci": [{"gene": "A", "alleles": {"A": "x", "a": "y"}}, {"gene": "B", "alleles": {"B": "x", "b": "y"}}],
      "linkage": [{"loci": ["A", "B"], "rf": 0.6}]}, "cannot exceed 0.5"),
    ({"loci": [{"gene": "A", "alleles": {"A": "x", "a": "y"}}, {"gene": "B", "alleles": {"B": "x", "b": "y"}}],
      "linkage": [{"loci": ["A", "C"], "rf": 0.1}]}, "locus C is not defined"),
    ({"loci": [{"gene": "A", "alleles": {"A": "x", "a": "y"}, "dominance": "A > aa"}]}, "aa is not an allele.*did you mean 'a'"),
    ({"loci": [{"gene": "A", "alleles": {"A": "x", "a": "y"}, "heterozygotes": {"A/a": "z"}}]}, "completely dominant"),
    ({"loci": [{"gene": "C", "alleles": {"C^R": "red", "C^W": "white"}, "dominance": "incomplete"}]}, "name the heterozygote"),
    ({"loci": [{"gene": "w", "chromosome": "X", "alleles": {"X^w": "white", "w^+": "red"}}]}, "write the allele alone"),
    ({"loci": [{"gene": "w", "chromosome": "X", "alleles": {"w^+": "red", "w": "white"}},
               {"gene": "y", "chromosome": "X", "alleles": {"y^+": "grey", "y": "yellow"}}]}, "all X-linked"),
    ({"loci": [{"gene": "b", "alleles": {"+": "grey", "b": "black"}}, {"gene": "vg", "alleles": {"+": "normal", "vg": "vestigial"}}]},
     "allele symbols must differ"),
    ({"loci": [{"gene": "A", "alleles": {"A": "x", "a": "y"}}], "epistasis": [{"kind": "recesive", "epistatic": "A", "hypostatic": "A"}]},
     "did you mean 'recessive'"),
    ({"loci": [{"gene": "A", "alleles": {"A": "x", "a": "y"}, "chromosme": "X"}]}, "unknown key 'chromosme'.*did you mean 'chromosome'"),
    ({"loci": [{"gene": "A", "alleles": {"A": "x", "a": "y"}, "chromosome": "x-link"}]}, "chromosome 'x-link'"),
    ({"preset": "labrdor"}, "did you mean 'labrador'"),
    ({"loci": [{"gene": "A", "alleles": {"A": "x", "a": "y"}}, {"gene": "B", "alleles": {"B": "x", "b": "y"}}],
      "linkage": [{"loci": ["A", "B"], "rf": 0.1, "coincidence": 0.5}]}, "three linked loci"),
    ({"loci": [{"gene": "P", "alleles": {"P": "poly", "p": "five"}, "penetrance": 0.8}]}, "name the phenotype"),
    ({"loci": [{"gene": "Y", "alleles": {"Y": "yellow", "y": "green"}}], "sex": "XY"}, "X and Y name"),
])
def test_system_errors(spec: dict, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        build_system(spec)


def test_tester_needs_a_single_recessive_allele() -> None:
    with pytest.raises(VidgenError, match="no single recessive allele"):
        make_tester(preset("snapdragon"), "C^RC^W")


def test_reciprocal_needs_true_breeding_mother() -> None:
    with pytest.raises(VidgenError, match="true-breeding"):
        reciprocal(preset("hemophilia_a"), "X^H X^h", "X^H Y")
