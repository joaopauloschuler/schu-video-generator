"""Phenotypes from genotypes (DESIGN.md §96.3): dominance at each locus (complete, incomplete,
codominant, a hierarchy of multiple alleles), penetrance (an exact share of the genotype's
carriers showing the trait), epistasis between two loci, lethal genotypes, and the textbook
order of phenotype classes (so ratios read 9:3:4, 12:3:1, 1:2:1). No manim."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product

from .genotype import Genotype, alleles_at
from .model import Epistasis, GeneticSystem, Locus


@dataclass(frozen=True)
class Phenotype:
    """A phenotype class: one phenotype per trait of the system (an independent locus, or two loci
    in epistasis), and the sex when the cross follows the sexes."""

    traits: tuple[str, ...]
    sex: str | None = None

    @property
    def text(self) -> str:
        body = ", ".join(self.traits)
        return f"{self.sex}: {body}" if self.sex else body


def locus_phenotypes(system: GeneticSystem, genotype: Genotype, locus: Locus) -> dict[str, Fraction]:
    """The phenotype distribution at one locus: its genotype's phenotype with probability equal to
    the penetrance, else the locus' ``normal`` phenotype (Y-linked loci in females: ``normal``)."""
    alleles = alleles_at(system, genotype, locus.symbol)
    if not alleles:
        return {locus.normal or "": Fraction(1)}
    shown = locus.phenotype(alleles) or ""
    p = locus.penetrance.get(shown)
    if p is None or locus.normal is None:
        return {shown: Fraction(1)}
    out: dict[str, Fraction] = {}
    for name, share in ((shown, p), (locus.normal, 1 - p)):
        if share:
            out[name] = out.get(name, Fraction(0)) + share
    return out


def epistatic_phenotype(system: GeneticSystem, e: Epistasis, first_shown: str, second_shown: str) -> str:
    """The combined phenotype of two loci in epistasis, from each locus' own phenotype."""
    first, second = system.locus(e.loci[0]), system.locus(e.loci[1])
    first_dom = first_shown == first.dominant_phenotype
    second_dom = second_shown == second.dominant_phenotype
    if e.kind == "recessive":
        return first_shown if first_shown == first.recessive_phenotype else second_shown
    if e.kind == "dominant":
        return first_shown if first_dom else second_shown
    if e.kind == "suppression":
        return second.recessive_phenotype if first_dom else second_shown  # type: ignore[return-value]
    if e.kind == "duplicate":
        return e.phenotypes[0] if first_dom or second_dom else e.phenotypes[1]
    if e.kind == "complementary":
        return e.phenotypes[0] if first_dom and second_dom else e.phenotypes[1]
    return e.phenotypes[2 - int(first_dom) - int(second_dom)]          # cumulative


def phenotypes_of(system: GeneticSystem, genotype: Genotype, by_sex: bool | None = None) -> dict[Phenotype, Fraction]:
    """The phenotype distribution of one genotype (exact; a single class unless penetrance is
    below 1). ``by_sex`` (default: whenever the system has sex chromosomes) adds the sex."""
    per_locus = {lo.symbol: locus_phenotypes(system, genotype, lo) for lo in system.loci}
    names = [lo.symbol for lo in system.loci]
    sex = genotype.sex if (system.sex_chromosomes if by_sex is None else by_sex) else None
    out: dict[Phenotype, Fraction] = {}
    for combo in product(*(list(per_locus[n].items()) for n in names)):
        shown = {n: c[0] for n, c in zip(names, combo)}
        share = Fraction(1)
        for c in combo:
            share *= c[1]
        traits = []
        for trait in system.traits:
            if trait.epistasis is None:
                traits.append(shown[trait.loci[0]])
            else:
                traits.append(epistatic_phenotype(system, trait.epistasis, shown[trait.loci[0]], shown[trait.loci[1]]))
        key = Phenotype(tuple(traits), sex)
        out[key] = out.get(key, Fraction(0)) + share
    return out


def is_lethal(system: GeneticSystem, genotype: Genotype) -> bool:
    """Whether the genotype dies before it is counted: a dominant lethal allele, or a recessive
    lethal one homozygous or hemizygous (X-linked in a male, Y-linked, mitochondrial)."""
    for lo in system.loci:
        alleles = alleles_at(system, genotype, lo.symbol)
        for a in set(alleles):
            kind = lo.allele(a).lethal
            if kind == "dominant" or (kind == "recessive" and all(x == a for x in alleles)):
                return True
    return False


def phenotype_key(system: GeneticSystem, phenotype: Phenotype) -> tuple[int, ...]:
    """Sort key giving the textbook order of classes: females first, then each trait's phenotypes
    in dominance (or epistasis) order."""
    sex = {"female": 0, "male": 1}.get(phenotype.sex or "", 0)
    keys = [sex]
    for trait, shown in zip(system.traits, phenotype.traits):
        keys.append(trait.phenotypes.index(shown) if shown in trait.phenotypes else len(trait.phenotypes))
    return tuple(keys)


__all__ = ["Phenotype", "epistatic_phenotype", "is_lethal", "locus_phenotypes", "phenotype_key", "phenotypes_of"]
