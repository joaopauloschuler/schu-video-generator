"""The exact cross engine (DESIGN.md §96.4): gametes by Mendel's segregation and independent
assortment, crossing over between linked loci at their recombination frequencies (coupling or
repulsion as written, interference for three loci, none where ``rf_male`` says so), X and Y
segregating in males, mtDNA in eggs only; offspring genotype and phenotype distributions as
exact fractions, lethal classes removed; ratios in lowest terms; test and reciprocal crosses.
No manim."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from functools import reduce
from itertools import product
from math import gcd, lcm

from vidgen.errors import VidgenError

from .genotype import Gamete, Genotype, Haplotype, SexChromosome, make_genotype, parse_genotype
from .model import HALF, GeneticSystem, LinkageGroup
from .phenotype import Phenotype, is_lethal, phenotype_key, phenotypes_of


def crossover_patterns(group: LinkageGroup, sex: str | None) -> list[tuple[tuple[bool, ...], Fraction]]:
    """Each pattern of crossovers in the group's intervals with its probability: independent
    intervals, except that for three loci the double crossovers are ``coincidence × r1 × r2``."""
    rates = group.rates(sex)
    out: list[tuple[tuple[bool, ...], Fraction]] = []
    for pattern in product((False, True), repeat=len(rates)):
        if len(rates) == 2:
            r1, r2 = rates
            double = group.coincidence * r1 * r2
            p = {(True, True): double, (True, False): r1 - double, (False, True): r2 - double,
                 (False, False): 1 - r1 - r2 + double}[pattern]
        else:
            p = reduce(lambda acc, rc: acc * (rc[0] if rc[1] else 1 - rc[0]), zip(rates, pattern), Fraction(1))
        if p:
            out.append((pattern, p))
    return out


def haplotype_gametes(group: LinkageGroup, h1: Haplotype, h2: Haplotype, sex: str | None) -> dict[Haplotype, Fraction]:
    """The haplotypes a parent with homologues ``h1`` / ``h2`` passes on, with their exact
    frequencies (parental classes ``(1 − r)/2`` each, recombinant ``r/2`` each, for two loci)."""
    out: dict[Haplotype, Fraction] = {}
    for pattern, p in crossover_patterns(group, sex):
        for start, other in ((h1, h2), (h2, h1)):
            current, hap = start, [start[0]]
            for j, crossed in enumerate(pattern, start=1):
                if crossed:
                    current = other if current is start else start
                hap.append(current[j])
            key = tuple(hap)
            out[key] = out.get(key, Fraction(0)) + HALF * p
    return out


def gametes(system: GeneticSystem, genotype: Genotype, sex: str | None = None) -> dict[Gamete, Fraction]:
    """The gametes of an individual and their exact frequencies. ``sex`` gives the parent's role
    where the genotype does not show it (no sex chromosomes): male meiosis uses ``rf_male``, and
    only eggs carry the mtDNA (an individual of unknown sex is taken as the mother)."""
    sex = genotype.sex or sex
    is_egg = sex != "male"
    parts: list[list[tuple[object, Fraction]]] = []
    for group, (h1, h2) in zip(system.groups, genotype.autosomes):
        parts.append(list(haplotype_gametes(group, h1, h2, sex).items()))
    if genotype.sex_chromosomes is not None:
        a, b = genotype.sex_chromosomes
        if b.letter == "Y" or system.x_group is None:
            parts.append([(a, HALF), (b, HALF)] if a != b else [(a, Fraction(1))])
        else:
            haps = haplotype_gametes(system.x_group, a.alleles, b.alleles, "female")
            parts.append([(SexChromosome("X", h), p) for h, p in haps.items()])
    out: dict[Gamete, Fraction] = {}
    for combo in product(*parts):
        p = reduce(lambda acc, c: acc * c[1], combo, Fraction(1))
        autosomes = tuple(c[0] for c in combo[:len(system.groups)])
        chrom = combo[len(system.groups)][0] if genotype.sex_chromosomes is not None else None
        g = Gamete(autosomes, chrom, genotype.mito if is_egg else ())  # type: ignore[arg-type]
        out[g] = out.get(g, Fraction(0)) + p
    return out


def fertilize(system: GeneticSystem, egg: Gamete, sperm: Gamete) -> Genotype:
    """The zygote of an egg and a sperm (or pollen): mtDNA from the egg only."""
    autosomes = list(zip(egg.autosomes, sperm.autosomes))
    sex = None
    if egg.sex_chromosome is not None and sperm.sex_chromosome is not None:
        sex = (egg.sex_chromosome, sperm.sex_chromosome)
    return make_genotype(system, autosomes, sex, egg.mito if system.mt_loci else ())


def genotype_key(system: GeneticSystem, genotype: Genotype) -> tuple:
    """Sort key: females first, then dominant alleles first locus by locus (AA, Aa, aa)."""
    keys: list = [0 if genotype.sex in (None, "female") else 1]
    for group, pair in zip(system.groups, genotype.autosomes):
        keys.append(tuple(tuple(system.locus(n).rank(a) for n, a in zip(group.loci, hap)) for hap in pair))
    if genotype.sex_chromosomes is not None:
        keys.append(tuple(tuple(system.locus(n).rank(a) for n, a in zip(system.x_loci if c.letter == "X" else system.y_loci, c.alleles))
                          for c in genotype.sex_chromosomes))
    keys.append(tuple(system.locus(n).rank(a) for n, a in zip(system.mt_loci, genotype.mito)))
    return tuple(keys)


def ratio(values: Iterable[Fraction]) -> tuple[int, ...]:
    """Exact frequencies as the smallest whole-number ratio: (9/16, 3/16, 4/16) → (9, 3, 4)."""
    fractions = [Fraction(v) for v in values]
    if not fractions:
        return ()
    scale = reduce(lcm, (f.denominator for f in fractions), 1)
    whole = [int(f * scale) for f in fractions]
    common = reduce(gcd, whole, 0) or 1
    return tuple(w // common for w in whole)


def ratio_text(numbers: Iterable[int]) -> str:
    """``9 : 3 : 3 : 1``."""
    return " : ".join(str(n) for n in numbers)


@dataclass(frozen=True)
class CrossResult:
    """A cross worked out exactly: the parents, their gametes, every zygote (lethal ones too),
    the share that dies (``lethal``), and the survivors' genotype and phenotype distributions
    (each summing to 1), in textbook order."""

    system: GeneticSystem
    mother: Genotype
    father: Genotype
    eggs: dict[Gamete, Fraction]
    sperm: dict[Gamete, Fraction]
    zygotes: dict[Genotype, Fraction]
    lethal: Fraction
    genotypes: dict[Genotype, Fraction]
    phenotypes: dict[Phenotype, Fraction]

    @property
    def genotype_ratio(self) -> tuple[int, ...]:
        return ratio(self.genotypes.values())

    @property
    def phenotype_ratio(self) -> tuple[int, ...]:
        return ratio(self.phenotypes.values())

    def phenotype_share(self, *traits: str, sex: str | None = None) -> Fraction:
        """The share of survivors showing all of ``traits`` (and of ``sex`` when given)."""
        return sum((p for ph, p in self.phenotypes.items() if all(t in ph.traits for t in traits) and (sex is None or ph.sex == sex)),
                   Fraction(0))


def _as_genotype(system: GeneticSystem, value: Genotype | str, sex: str | None, where: str) -> Genotype:
    if isinstance(value, Genotype):
        if sex is not None and value.sex is not None and value.sex != sex:
            raise VidgenError(f"{where}: this genotype is {value.sex}, not {sex}")
        return value
    return parse_genotype(system, value, where, sex if system.sex_chromosomes else None)


def cross(system: GeneticSystem, mother: Genotype | str, father: Genotype | str, where: str = "params",
          by_sex: bool | None = None) -> CrossResult:
    """Cross ``mother`` × ``father`` (genotypes or their written form). Without sex chromosomes
    or mtDNA the two roles are the same (a plant's seed and pollen parents). ``by_sex`` splits
    the phenotype classes by sex (default: when the system has sex chromosomes)."""
    m = _as_genotype(system, mother, "female", f"{where}.mother")
    f = _as_genotype(system, father, "male", f"{where}.father")
    eggs = gametes(system, m, "female")
    sperm = gametes(system, f, "male")
    zygotes: dict[Genotype, Fraction] = {}
    for (e, pe), (s, ps) in product(eggs.items(), sperm.items()):
        z = fertilize(system, e, s)
        zygotes[z] = zygotes.get(z, Fraction(0)) + pe * ps
    lethal = sum((p for z, p in zygotes.items() if is_lethal(system, z)), Fraction(0))
    if lethal == 1:
        raise VidgenError(f"{where}: every offspring of this cross carries a lethal genotype")
    alive = {z: p / (1 - lethal) for z, p in zygotes.items() if not is_lethal(system, z)}
    genotypes = dict(sorted(alive.items(), key=lambda kv: genotype_key(system, kv[0])))
    phenotypes: dict[Phenotype, Fraction] = {}
    for z, p in genotypes.items():
        for ph, share in phenotypes_of(system, z, by_sex).items():
            phenotypes[ph] = phenotypes.get(ph, Fraction(0)) + p * share
    ordered = dict(sorted(phenotypes.items(), key=lambda kv: phenotype_key(system, kv[0])))
    return CrossResult(system, m, f, eggs, sperm, dict(sorted(zygotes.items(), key=lambda kv: genotype_key(system, kv[0]))),
                       lethal, genotypes, ordered)


def make_tester(system: GeneticSystem, genotype: Genotype | str, where: str = "params") -> Genotype:
    """The test-cross partner of an individual: homozygous (or hemizygous) for the recessive
    allele of every locus, of the other sex when the system has sex chromosomes."""
    g = _as_genotype(system, genotype, None, where)
    recessive: dict[str, str] = {}
    for lo in system.loci:
        if lo.recessive_allele is None:
            raise VidgenError(f"{where}: locus {lo.symbol} has no single recessive allele (its lowest level is "
                              f"{' / '.join(lo.levels[-1])}), so there is no tester for a test cross")
        recessive[lo.symbol] = lo.recessive_allele
    autosomes = [(tuple(recessive[n] for n in grp.loci),) * 2 for grp in system.groups]
    sex = None
    if g.sex_chromosomes is not None:
        x = SexChromosome("X", tuple(recessive[n] for n in system.x_loci))
        y = SexChromosome("Y", tuple(recessive[n] for n in system.y_loci))
        sex = (x, y) if g.sex == "female" else (x, x)
    return make_genotype(system, autosomes, sex, tuple(recessive[n] for n in system.mt_loci))  # type: ignore[arg-type]


def test_cross(system: GeneticSystem, genotype: Genotype | str, where: str = "params") -> CrossResult:
    """Cross an individual with its :func:`make_tester`: the offspring classes show its gametes."""
    g = _as_genotype(system, genotype, None, where)
    t = make_tester(system, g, where)
    return cross(system, t, g, where) if g.sex == "male" else cross(system, g, t, where)


test_cross.__test__ = False  # type: ignore[attr-defined]  # not a pytest test


def reciprocal(system: GeneticSystem, mother: Genotype | str, father: Genotype | str, where: str = "params") -> tuple[Genotype, Genotype]:
    """The reciprocal cross's parents: the father's line as the mother, the mother's line as the
    father (X-linked loci need a true-breeding mother; the new father keeps the old father's Y;
    the mtDNA goes with its line)."""
    m = _as_genotype(system, mother, "female", f"{where}.mother")
    f = _as_genotype(system, father, "male", f"{where}.father")
    if m.sex_chromosomes is None or f.sex_chromosomes is None:
        return make_genotype(system, list(f.autosomes), None, f.mito), make_genotype(system, list(m.autosomes), None, m.mito)
    x1, x2 = m.sex_chromosomes
    if x1 != x2:
        raise VidgenError(f"{where}: a reciprocal cross swaps the sexes of two lines: the mother must be true-breeding "
                          f"(homozygous) at the X-linked loci")
    fx, fy = f.sex_chromosomes
    new_mother = make_genotype(system, list(f.autosomes), (fx, fx), f.mito)
    new_father = make_genotype(system, list(m.autosomes), (x1, fy), m.mito)
    return new_mother, new_father


__all__ = ["CrossResult", "crossover_patterns", "cross", "fertilize", "gametes", "genotype_key", "haplotype_gametes", "ratio",
           "ratio_text", "reciprocal", "test_cross", "make_tester"]
