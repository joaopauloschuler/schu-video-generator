"""Modes of inheritance (DESIGN.md §96.3): autosomal dominant and recessive, X-linked dominant
and recessive, Y-linked and mitochondrial, with their textbook hallmarks as data, so the
pedigree analysis (Step 215) and the genetics lint (Step 219) use one table. No manim."""

from __future__ import annotations

from dataclasses import dataclass

from vidgen.cellworld.model import did_you_mean
from vidgen.errors import VidgenError

from .model import GeneticSystem
from .notation import symbol_ascii


@dataclass(frozen=True)
class Mode:
    """A mode of inheritance: its code (``AR``), name, chromosome, whether the trait shows in
    heterozygotes (``None`` for hemizygous / maternal modes) and its hallmarks in a pedigree."""

    code: str
    name: str
    chromosome: str
    dominant: bool | None
    hallmarks: tuple[str, ...]


MODES: dict[str, Mode] = {m.code: m for m in (
    Mode("AD", "autosomal dominant", "autosome", True, (
        "affected individuals usually have an affected parent (vertical transmission; no skipped generations at full penetrance)",
        "males and females are affected and transmit equally, including father to son",
        "an affected heterozygote and an unaffected partner have a 1/2 chance of an affected child",
    )),
    Mode("AR", "autosomal recessive", "autosome", False, (
        "affected individuals usually have unaffected carrier parents (horizontal pattern; generations skipped)",
        "males and females are affected equally",
        "two carrier parents have a 1/4 chance of an affected child; an unaffected sibling of an affected child is a carrier with probability 2/3",
        "consanguinity raises the risk",
    )),
    Mode("XD", "X-linked dominant", "X", True, (
        "an affected father passes the trait to all his daughters and none of his sons",
        "an affected heterozygous mother passes it to half her children of either sex",
        "more females than males are affected",
    )),
    Mode("XR", "X-linked recessive", "X", False, (
        "mostly males are affected",
        "never passed from father to son (a father gives his son the Y)",
        "affected males' daughters are obligate carriers; a carrier mother's sons are affected with probability 1/2",
    )),
    Mode("YL", "Y-linked", "Y", None, (
        "only males are affected",
        "passed from father to every son, never to daughters",
    )),
    Mode("MT", "mitochondrial", "mt", None, (
        "passed from a mother to all her children; never from a father",
        "both sexes affected; heteroplasmy can make expression variable",
    )),
)}
_ALIASES = {
    "ad": "AD", "autosomal_dominant": "AD", "ar": "AR", "autosomal_recessive": "AR", "xd": "XD", "x_linked_dominant": "XD",
    "xr": "XR", "x_linked_recessive": "XR", "xl": "XR", "yl": "YL", "y_linked": "YL", "holandric": "YL", "mt": "MT",
    "mitochondrial": "MT", "maternal": "MT",
}


def parse_mode(text: str, where: str) -> Mode:
    """A mode from ``AR``, ``autosomal recessive``, ``x-linked recessive``…"""
    key = str(text).strip().lower().replace("-", "_").replace(" ", "_")
    if key not in _ALIASES:
        raise VidgenError(f"{where}: inheritance '{text}': use {', '.join(MODES)} or their names "
                          f"({', '.join(m.name for m in MODES.values())}){did_you_mean(key, list(_ALIASES))}")
    return MODES[_ALIASES[key]]


def mode_of(system: GeneticSystem, locus: str, phenotype: str, where: str = "params") -> Mode:
    """The mode by which ``phenotype`` of ``locus`` is inherited: its chromosome, and on an
    autosome or the X whether it shows in heterozygotes (the phenotype of the dominant allele of
    a two-allele locus with complete dominance)."""
    lo = system.locus(locus)
    if phenotype not in lo.phenotypes:
        raise VidgenError(f"{where}: '{phenotype}' is not a phenotype of locus {locus} ({', '.join(lo.phenotypes)})"
                          f"{did_you_mean(phenotype, list(lo.phenotypes))}")
    if lo.chromosome == "Y":
        return MODES["YL"]
    if lo.chromosome == "mt":
        return MODES["MT"]
    if not lo.is_simple:
        raise VidgenError(f"{where}: locus {locus} is not two alleles with complete dominance "
                          f"({' > '.join(' = '.join(symbol_ascii(s) for s in lv) for lv in lo.levels)}): "
                          f"a dominant / recessive mode needs one")
    dominant = phenotype == lo.dominant_phenotype
    return MODES[("A" if lo.chromosome == "autosome" else "X") + ("D" if dominant else "R")]


__all__ = ["MODES", "Mode", "mode_of", "parse_mode"]
