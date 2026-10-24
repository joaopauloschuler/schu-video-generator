"""Ready-made genetic systems for the textbook crosses (DESIGN.md §96.3): ``preset: abo`` and
so on, so authors do not retype the classic loci (and cannot get their dominance wrong). Each
is plain YAML-shaped data that :func:`~vidgen.genetics.model.build_system` checks like an
author's. No manim."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Preset:
    """A named system: its spec, what it shows, and a typical cross (the parents' genotypes)."""

    spec: dict[str, Any]
    note: str
    example: tuple[str, str]


PRESETS: dict[str, Preset] = {
    "pea_seed_shape": Preset(
        {"loci": [{"gene": "R", "trait": "seed shape", "alleles": {"R": "round", "r": "wrinkled"}}]},
        "Mendel's monohybrid cross: round is completely dominant over wrinkled (F2 3 : 1).", ("Rr", "Rr")),
    "pea_dihybrid": Preset(
        {"loci": [{"gene": "R", "trait": "seed shape", "alleles": {"R": "round", "r": "wrinkled"}},
                  {"gene": "Y", "trait": "seed colour", "alleles": {"Y": "yellow", "y": "green"}}]},
        "Mendel's dihybrid cross: independent assortment (F2 9 : 3 : 3 : 1).", ("RrYy", "RrYy")),
    "snapdragon": Preset(
        {"loci": [{"gene": "C", "trait": "flower colour", "alleles": {"C^R": "red", "C^W": "white"}, "dominance": "incomplete",
                   "heterozygotes": {"C^R/C^W": "pink"}}]},
        "Incomplete dominance in snapdragon flowers: red × white gives pink (F2 1 : 2 : 1).", ("C^R C^W", "C^R C^W")),
    "abo": Preset(
        {"loci": [{"gene": "I", "trait": "ABO blood group", "alleles": {"I^A": "A", "I^B": "B", "i": "O"},
                   "dominance": "I^A = I^B > i", "heterozygotes": {"I^A/I^B": "AB"}}]},
        "Multiple alleles with codominance: Iᴬ and Iᴮ codominant, both dominant over i.", ("I^A i", "I^B i")),
    "rabbit_coat": Preset(
        {"loci": [{"gene": "C", "trait": "coat colour", "dominance": "C > c^ch > c^h > c",
                   "alleles": {"C": "full colour", "c^ch": "chinchilla", "c^h": "himalayan", "c": "albino"}}]},
        "A dominance series of four alleles at the rabbit C locus.", ("C c^h", "c^ch c")),
    "labrador": Preset(
        {"loci": [{"gene": "B", "trait": "coat colour", "alleles": {"B": "black", "b": "brown"}},
                  {"gene": "E", "trait": "pigment deposition", "alleles": {"E": "pigmented", "e": "yellow"}}],
         "epistasis": [{"kind": "recessive", "epistatic": "E", "hypostatic": "B"}]},
        "Recessive epistasis in Labrador retrievers: ee is yellow whatever B (F2 9 black : 3 brown : 4 yellow).", ("BbEe", "BbEe")),
    "squash_colour": Preset(
        {"loci": [{"gene": "W", "trait": "white fruit", "alleles": {"W": "white", "w": "coloured"}},
                  {"gene": "Y", "trait": "fruit colour", "alleles": {"Y": "yellow", "y": "green"}}],
         "epistasis": [{"kind": "dominant", "epistatic": "W", "hypostatic": "Y"}]},
        "Dominant epistasis in summer squash: W_ is white (F2 12 white : 3 yellow : 1 green).", ("WwYy", "WwYy")),
    "chicken_feathers": Preset(
        {"loci": [{"gene": "I", "trait": "colour inhibitor", "alleles": {"I": "inhibited", "i": "not inhibited"}},
                  {"gene": "C", "trait": "plumage", "alleles": {"C": "coloured", "c": "white"}}],
         "epistasis": [{"kind": "suppression", "epistatic": "I", "hypostatic": "C"}]},
        "Dominant suppression in chickens (White Leghorn × White Wyandotte): F2 13 white : 3 coloured.", ("IiCc", "IiCc")),
    "shepherds_purse": Preset(
        {"loci": [{"gene": "A", "trait": "capsule shape", "alleles": {"A": "triangular", "a": "ovoid"}},
                  {"gene": "B", "trait": "capsule shape", "alleles": {"B": "triangular", "b": "ovoid"}}],
         "epistasis": [{"kind": "duplicate", "loci": ["A", "B"]}]},
        "Duplicate genes in shepherd's purse capsules: F2 15 triangular : 1 ovoid.", ("AaBb", "AaBb")),
    "sweet_pea": Preset(
        {"loci": [{"gene": "C", "trait": "flower colour", "alleles": {"C": "purple", "c": "white"}},
                  {"gene": "P", "trait": "flower colour", "alleles": {"P": "purple", "p": "white"}}],
         "epistasis": [{"kind": "complementary", "loci": ["C", "P"]}]},
        "Complementary genes in sweet pea flowers (Bateson and Punnett): F2 9 purple : 7 white.", ("CcPp", "CcPp")),
    "squash_shape": Preset(
        {"loci": [{"gene": "A", "trait": "fruit shape", "alleles": ["A", "a"]},
                  {"gene": "B", "trait": "fruit shape", "alleles": ["B", "b"]}],
         "epistasis": [{"kind": "cumulative", "loci": ["A", "B"], "phenotypes": ["disc", "sphere", "long"]}]},
        "Duplicate genes with cumulative effect in summer squash fruit shape: F2 9 disc : 6 sphere : 1 long.", ("AaBb", "AaBb")),
    "yellow_mouse": Preset(
        {"loci": [{"gene": "A", "trait": "coat colour", "alleles": [{"symbol": "A^Y", "phenotype": "yellow", "lethal": "recessive"},
                                                                     {"symbol": "A", "phenotype": "agouti"}]}]},
        "A recessive lethal allele that is dominant for coat colour (Cuénot's yellow mice): 2 yellow : 1 agouti.", ("A^Y A", "A^Y A")),
    "drosophila_white": Preset(
        {"loci": [{"gene": "w", "trait": "eye colour", "chromosome": "X", "alleles": {"w^+": "red", "w": "white"}}]},
        "X-linked recessive white eyes in Drosophila (Morgan): the reciprocal crosses differ.", ("X^w X^w", "X^{w^+} Y")),
    "hemophilia_a": Preset(
        {"loci": [{"gene": "H", "trait": "blood clotting", "chromosome": "X",
                   "alleles": {"H": "normal clotting", "h": "hemophilia A"}}]},
        "X-linked recessive hemophilia A (F8): a carrier mother's sons are affected with probability 1/2.", ("X^H X^h", "X^H Y")),
    "drosophila_b_vg": Preset(
        {"loci": [{"gene": "b", "trait": "body colour", "alleles": {"b^+": "grey body", "b": "black body"}},
                  {"gene": "vg", "trait": "wings", "alleles": {"vg^+": "normal wings", "vg": "vestigial wings"}}],
         "linkage": [{"loci": ["b", "vg"], "rf": 0.17, "rf_male": 0}]},
        "Linked genes on Drosophila chromosome 2 (Morgan's test cross: 17% recombinants); no crossing over in males.",
        ("b^+vg^+/bvg", "bvg/bvg")),
}


__all__ = ["PRESETS", "Preset"]
