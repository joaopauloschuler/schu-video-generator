"""Genetics (DESIGN.md §96): loci, alleles and their notation, genotypes, phenotypes with
dominance, penetrance and epistasis, modes of inheritance, and an exact cross engine (fractions,
independent assortment, linkage with recombination, sex chromosomes, mtDNA). Plain data and
rules, no manim imports (a test checks): ``vidgen validate`` and lint use it without rendering;
the genetics scene types (Steps 214–218) draw it."""

from .cross import CrossResult, cross, fertilize, gametes, genotype_key, haplotype_gametes, ratio, ratio_text, reciprocal, test_cross, make_tester
from .genotype import Gamete, Genotype, SexChromosome, alleles_at, gamete_text, genotype_text, make_genotype, parse_genotype
from .model import (
    CHROMOSOMES, EPISTASIS_KINDS, Allele, Epistasis, GeneticSystem, LinkageGroup, Locus, Trait, as_fraction, build_locus, build_system,
)
from .modes import MODES, Mode, mode_of, parse_mode
from .notation import canonical_symbol, symbol_ascii, symbol_markup, symbol_text
from .phenotype import Phenotype, is_lethal, locus_phenotypes, phenotypes_of
from .presets import PRESETS, Preset

__all__ = [
    "CHROMOSOMES", "EPISTASIS_KINDS", "MODES", "PRESETS", "Allele", "CrossResult", "Epistasis", "Gamete", "GeneticSystem", "Genotype",
    "LinkageGroup", "Locus", "Mode", "Phenotype", "Preset", "SexChromosome", "Trait", "alleles_at", "as_fraction", "build_locus",
    "build_system", "canonical_symbol", "cross", "fertilize", "gamete_text", "gametes", "genotype_key", "genotype_text",
    "haplotype_gametes", "is_lethal", "locus_phenotypes", "make_genotype", "mode_of", "parse_genotype", "parse_mode", "phenotypes_of",
    "ratio", "ratio_text", "reciprocal", "symbol_ascii", "symbol_markup", "symbol_text", "test_cross", "make_tester",
]
