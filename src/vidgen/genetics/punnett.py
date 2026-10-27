"""What a ``cross`` scene shows, worked out without drawing (DESIGN.md §96.7): the parents (as
written, or the F1 of a P cross, a test cross's tester, a reciprocal cross), each parent's gametes
in textbook order with their exact frequencies and which homologue each allele came from
(parental or recombinant), the Punnett square's cells (each ``fertilize(egg, sperm)``), the
genotype and phenotype classes with fractions, whole-number ratios and percentages, the branch
(forked-line) diagram as a probability tree, the notes a cross needs (linkage, lethality, test
and reciprocal crosses, epistasis) and the observed counts of a chi-square test matched to the
classes. Everything comes from :func:`~vidgen.genetics.cross.cross`, so nothing drawn can disagree
with it. No manim."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Any

from vidgen.cellworld.model import did_you_mean
from vidgen.errors import VidgenError

from .cross import CrossResult, cross, fertilize, make_tester, ratio, reciprocal
from .genotype import Gamete, Genotype, _simple, alleles_at, genotype_text, parse_genotype
from .glyphs import GlyphSpec, animal_of, class_glyphs
from .model import GeneticSystem, as_fraction, build_system
from .notation import chromosome_markup, chromosome_text, symbol_ascii, symbol_markup, symbol_text
from .phenotype import Phenotype, is_lethal, phenotypes_of

#: How the cross is drawn: a Punnett square, a branch (forked-line) diagram, or ``auto`` (a
#: square up to 4 × 4 gametes, a branch diagram beyond).
SHOWS = ("auto", "punnett", "branch")
KINDS = ("cross", "test", "reciprocal")
BRANCH_BY = ("phenotypes", "genotypes")
#: The largest Punnett square drawn (8 × 8: a trihybrid) and the most leaves of a branch diagram.
MAX_SIDE = 8
MAX_LEAVES = 16
AUTO_SIDE = 4
_SYSTEM_KEYS = ("preset", "loci", "linkage", "epistasis", "sex")


# ----- text -----------------------------------------------------------------------------------------


def fraction_text(f: Fraction) -> str:
    """``9/16``, ``1``, ``0``."""
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def percent_text(f: Fraction) -> str:
    """Exact when it has at most two decimals (``56.25 %``, ``25 %``), else ``≈ 66.7 %`` (with
    no-break spaces, so a line never breaks before the sign)."""
    value = f * 100
    for places in (0, 1, 2):
        scaled = value * 10 ** places
        if scaled.denominator == 1:
            text = f"{float(value):.{places}f}"
            return f"{text} %"
    return f"≈ {float(value):.1f} %"


def ratio_text(numbers: Sequence[int]) -> str:
    """``9 : 3 : 3 : 1``."""
    return " : ".join(str(n) for n in numbers)


def normalize_label(text: str) -> tuple[str, ...]:
    """A class label as sorted words (commas, colons and case ignored): ``"Yellow round"`` and
    ``"round, yellow"`` match."""
    return tuple(sorted(w for w in re.split(r"[\s,;:]+", str(text).lower()) if w))


# ----- the plan -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Allele:
    """One allele (or sex chromosome) of a gamete as drawn: markup, plain text and the parent's
    homologue it came from (0, 1, or ``None`` when both carry it)."""

    markup: str
    text: str
    source: int | None


@dataclass(frozen=True)
class GameteView:
    """A gamete of one parent: the gamete, its exact frequency, its alleles as drawn, its text
    and whether it is a recombinant (linked loci crossed over)."""

    gamete: Gamete
    frequency: Fraction
    alleles: tuple[Allele, ...]
    markup: str
    text: str
    recombinant: bool


@dataclass(frozen=True)
class Cell:
    """A Punnett cell: row (egg) and column (sperm) from 1, the zygote, its probability, whether
    it dies, and its phenotype distribution (one class unless penetrance is below 1)."""

    row: int
    col: int
    genotype: Genotype
    probability: Fraction
    lethal: bool
    phenotypes: tuple[tuple[Phenotype, Fraction], ...]
    markup: str
    ascii: str


@dataclass(frozen=True)
class PhenotypeClass:
    """A phenotype class of the survivors: label (``round, yellow``), the phenotype, its exact
    share, its whole number of the ratio, the cells showing it, the cell count when every cell
    is equally likely, and its pictures."""

    index: int
    label: str
    phenotype: Phenotype
    share: Fraction
    ratio: int
    cells: tuple[tuple[int, int], ...]
    count: int | None
    glyphs: tuple[GlyphSpec, ...]


@dataclass(frozen=True)
class GenotypeClass:
    """A genotype class of the zygotes: its YAML form (``RrYy``), markup, its share of the
    zygotes and of the survivors, its whole number of the ratio, whether it dies, its cells."""

    index: int
    ascii: str
    markup: str
    genotype: Genotype
    share: Fraction
    survivors: Fraction
    ratio: int
    lethal: bool
    cells: tuple[tuple[int, int], ...]
    count: int | None


@dataclass(frozen=True)
class Branch:
    """A node of the branch diagram: its level (from 0), the values chosen so far (``path``),
    its own value as markup, its conditional probability and the product along the path."""

    level: int
    path: tuple[str, ...]
    markup: str
    conditional: Fraction
    probability: Fraction


@dataclass(frozen=True)
class Tree:
    """A branch (forked-line) diagram: the factor of each level (``sex``, a trait, a locus) and
    the nodes, leaves last in class order."""

    levels: tuple[str, ...]
    nodes: tuple[Branch, ...]

    @property
    def leaves(self) -> tuple[Branch, ...]:
        return tuple(n for n in self.nodes if n.level == len(self.levels) - 1)


@dataclass(frozen=True)
class CrossPlan:
    """Everything a ``cross`` scene draws."""

    system: GeneticSystem
    mother: Genotype
    father: Genotype
    kind: str
    roles: tuple[str, str]
    sexed: bool
    p_line: str | None
    offspring: str
    result: CrossResult
    eggs: tuple[GameteView, ...]
    sperm: tuple[GameteView, ...]
    cells: tuple[Cell, ...]
    uniform: bool
    phenotypes: tuple[PhenotypeClass, ...]
    genotypes: tuple[GenotypeClass, ...]
    show: str
    tree: Tree | None
    notes: tuple[str, ...]

    @property
    def lethal(self) -> Fraction:
        return self.result.lethal

    def cell(self, row: int, col: int) -> Cell:
        return self.cells[(row - 1) * len(self.sperm) + col - 1]

    @property
    def phenotype_ratio(self) -> tuple[int, ...]:
        return tuple(c.ratio for c in self.phenotypes)

    @property
    def genotype_ratio(self) -> tuple[int, ...]:
        return tuple(c.ratio for c in self.genotypes)


def genotype_key(system: GeneticSystem, genotype: Genotype) -> str:
    """The YAML form of a genotype as targets name it: ``RrYy`` (one-letter alleles run
    together), ``I^A i``, ``X^H X^h``, ``b^+vg^+/bvg``."""
    text = genotype_text(system, genotype, "ascii")
    simple = all(len(s) == 1 for lo in system.loci for s in lo.symbols) and "^" not in text
    return text.replace(" ", "") if simple else text


def class_label(ph: Phenotype) -> str:
    """``round, yellow``; with the sex last: ``white, male``."""
    return ", ".join([*ph.traits, *([ph.sex] if ph.sex else [])])


def _gamete_key(system: GeneticSystem, g: Gamete) -> tuple:
    keys: list = []
    for group, hap in zip(system.groups, g.autosomes):
        keys.append(tuple(system.locus(n).rank(a) for n, a in zip(group.loci, hap)))
    if g.sex_chromosome is not None:
        c = g.sex_chromosome
        names = system.x_loci if c.letter == "X" else system.y_loci
        keys.append((0 if c.letter == "X" else 1, tuple(system.locus(n).rank(a) for n, a in zip(names, c.alleles))))
    return tuple(keys)


def gamete_view(system: GeneticSystem, parent: Genotype, gamete: Gamete, frequency: Fraction) -> GameteView:
    """How one gamete is drawn: each allele with the homologue it came from."""
    alleles: list[Allele] = []
    recombinant = False
    for (h1, h2), hap in zip(parent.autosomes, gamete.autosomes):
        if len(hap) > 1 and hap not in (h1, h2):
            recombinant = True
        for j, a in enumerate(hap):
            source = None if h1[j] == h2[j] else (0 if a == h1[j] else 1)
            alleles.append(Allele(symbol_markup(a), symbol_text(a), source))
    if gamete.sex_chromosome is not None and parent.sex_chromosomes is not None:
        c = gamete.sex_chromosome
        a, b = parent.sex_chromosomes
        if a == b:
            source = None
        elif c == a:
            source = 0
        elif c == b:
            source = 1
        else:
            source, recombinant = None, True
        alleles.append(Allele(chromosome_markup(c.letter, c.alleles), chromosome_text(c.letter, c.alleles), source))
    for m in gamete.mito:
        alleles.append(Allele(symbol_markup(m), symbol_text(m), None))
    sep = "" if _simple([s for lo in system.loci for s in lo.symbols]) else " "
    return GameteView(gamete, frequency, tuple(alleles), sep.join(a.markup for a in alleles) or "—",
                      sep.join(a.text for a in alleles) or "—", recombinant)


def _views(system: GeneticSystem, parent: Genotype, gametes: Mapping[Gamete, Fraction]) -> tuple[GameteView, ...]:
    ordered = sorted(gametes.items(), key=lambda kv: (-kv[1], _gamete_key(system, kv[0])))
    return tuple(gamete_view(system, parent, g, p) for g, p in ordered)


def _system_spec(data: Mapping[str, Any]) -> dict[str, Any]:
    return {k: data[k] for k in _SYSTEM_KEYS if data.get(k) is not None}


def _roles(system: GeneticSystem, first: Genotype, second: Genotype, where: str) -> tuple[Genotype, Genotype]:
    """Mother and father of two genotypes written in any order (their sex chromosomes say)."""
    if first.sex is None:
        return first, second
    if first.sex == second.sex:
        raise VidgenError(f"{where}: both parents are {first.sex}s; a cross takes a female (XX) and a male (XY)")
    return (first, second) if first.sex == "female" else (second, first)


def _two(value: Any, where: str, what: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str) or len(value) != 2:
        raise VidgenError(f"{where}: {what} lists the two parents' genotypes, e.g. [RrYy, RrYy]")
    return [str(v) for v in value]


def _parse(system: GeneticSystem, text: Any, where: str, sex: str | None = None) -> Genotype:
    return parse_genotype(system, str(text), where, sex if system.sex_chromosomes else None)


def _parents(system: GeneticSystem, data: Mapping[str, Any], where: str) -> tuple[Genotype, Genotype, str, tuple[str, str], str | None, str]:
    """Mother, father, kind, the parents' roles, the P line and the offspring's name."""
    kind = str(data.get("kind") or "cross")
    if kind not in KINDS:
        raise VidgenError(f"{where}.kind: '{kind}': use {', '.join(KINDS)}{did_you_mean(kind, list(KINDS))}")
    parents, mother, father, p_gen = data.get("parents"), data.get("mother"), data.get("father"), data.get("P")
    mt_only = system.needs_sexes and not system.sex_chromosomes
    if p_gen is not None:
        if kind != "cross":
            raise VidgenError(f"{where}.P: a P generation is crossed to an F1 and the F1 intercrossed: leave out kind: {kind}")
        if parents is not None or mother is not None or father is not None:
            raise VidgenError(f"{where}.P: the P generation gives the parents (their F1): leave out parents, mother and father")
        texts = _two(p_gen, f"{where}.P", "P")
        if mt_only:
            raise VidgenError(f"{where}.P: this system has mitochondrial loci: write the F1 cross with mother: and father:")
        pm, pf = _roles(system, _parse(system, texts[0], f"{where}.P[0]"), _parse(system, texts[1], f"{where}.P[1]"), f"{where}.P")
        f1 = cross(system, pm, pf, f"{where}.P")
        by_sex: dict[str | None, list[Genotype]] = {}
        for g in f1.genotypes:
            by_sex.setdefault(g.sex, []).append(g)
        if any(len(v) != 1 for v in by_sex.values()):
            many = ", ".join(genotype_text(system, g, "ascii") for v in by_sex.values() for g in v)
            raise VidgenError(f"{where}.P: the P cross gives more than one F1 genotype ({many}): the P parents must be true-breeding "
                              f"(homozygous), or write the cross you mean with parents:")
        if system.sex_chromosomes:
            mother, father = by_sex["female"][0], by_sex["male"][0]
            f1_text = f"{genotype_text(system, mother, 'markup')} and {genotype_text(system, father, 'markup')}"
        else:
            mother = father = next(iter(by_sex.values()))[0]
            f1_text = f"all {genotype_text(system, mother, 'markup')}"
        line = (f"P: {genotype_text(system, pm, 'markup')} × {genotype_text(system, pf, 'markup')}  →  "
                f"F<sub>1</sub>: {f1_text}")
        return mother, father, "cross", ("F<sub>1</sub>", "F<sub>1</sub>"), line, "F<sub>2</sub>"
    if kind == "test":
        given = [v for v in (mother, father) if v is not None]
        if parents is not None:
            if not isinstance(parents, Sequence) or isinstance(parents, str):
                parents = [parents]
            given += list(parents)
        if len(given) != 1:
            raise VidgenError(f"{where}: a test cross takes one parent (parents: [RrYy]); the tester, homozygous recessive, is made for it")
        sex = "female" if mother is not None else "male" if father is not None else None
        g = _parse(system, given[0], f"{where}.{'mother' if mother is not None else 'father' if father is not None else 'parents[0]'}", sex)
        if mt_only and sex is None:
            raise VidgenError(f"{where}: this system has mitochondrial loci: write the parent as mother: or father:")
        tester = make_tester(system, g, where)
        if g.sex == "male" or sex == "male":
            return tester, g, "test", ("tester", ""), None, "offspring"
        return g, tester, "test", ("", "tester"), None, "offspring"
    if parents is not None:
        if mother is not None or father is not None:
            raise VidgenError(f"{where}: give parents or mother and father, not both")
        texts = _two(parents, f"{where}.parents", "parents")
        if mt_only:
            raise VidgenError(f"{where}.parents: this system has mitochondrial loci (inherited from the mother): write mother: and father:")
        m, f = _roles(system, _parse(system, texts[0], f"{where}.parents[0]"), _parse(system, texts[1], f"{where}.parents[1]"),
                      f"{where}.parents")
    else:
        if mother is None or father is None:
            missing = "parents: [RrYy, RrYy]" if not system.needs_sexes else "mother: and father:"
            raise VidgenError(f"{where}: write the two parents, {missing}")
        m = _parse(system, mother, f"{where}.mother", "female")
        f = _parse(system, father, f"{where}.father", "male")
    if kind == "reciprocal":
        m, f = reciprocal(system, m, f, where)
    return m, f, kind, ("", ""), None, "offspring"


def _tree(system: GeneticSystem, result: CrossResult, by: str) -> Tree:
    """The probability tree of the survivors: phenotypes by sex then trait, or genotypes by locus
    (the X and Y together), each node's conditional probability given the path."""
    dist: dict[tuple[tuple[str, str], ...], Fraction] = {}
    if by == "phenotypes":
        sexed = any(ph.sex for ph in result.phenotypes)
        levels = (["sex"] if sexed else []) + [t.name for t in system.traits]
        for ph, p in result.phenotypes.items():
            key = ([(ph.sex or "", ph.sex or "")] if sexed else []) + [(v, v) for v in ph.traits]
            dist[tuple(key)] = dist.get(tuple(key), Fraction(0)) + p
    else:
        names = [lo.symbol for lo in system.loci if lo.chromosome in ("autosome", "mt")]
        sex_part = bool(system.sex_chromosomes)
        levels = names + (["X / Y"] if sex_part else [])
        for g, p in result.genotypes.items():
            key: list[tuple[str, str]] = []
            for n in names:
                al = alleles_at(system, g, n)
                key.append(("".join(symbol_ascii(a) for a in al), "".join(symbol_markup(a) for a in al)))
            if sex_part and g.sex_chromosomes is not None:
                a, b = g.sex_chromosomes
                key.append((f"{a}{b}", chromosome_markup(a.letter, a.alleles) + chromosome_markup(b.letter, b.alleles)))
            dist[tuple(key)] = dist.get(tuple(key), Fraction(0)) + p
    order = list(dist)
    nodes: list[Branch] = []
    for level in range(len(levels)):
        seen: list[tuple] = []
        for key in order:
            prefix = key[:level + 1]
            if prefix in seen:
                continue
            seen.append(prefix)
            total = sum((p for k, p in dist.items() if k[:level + 1] == prefix), Fraction(0))
            parent = sum((p for k, p in dist.items() if k[:level] == prefix[:level]), Fraction(0))
            nodes.append(Branch(level, tuple(v[0] for v in prefix), prefix[-1][1], total / parent, total))
    return Tree(tuple(levels), tuple(nodes))


def _notes(system: GeneticSystem, m: Genotype, f: Genotype, kind: str, roles: tuple[str, str], result: CrossResult,
           eggs: tuple[GameteView, ...], sperm: tuple[GameteView, ...], same: bool) -> list[str]:
    notes: list[str] = []
    for views, g in ((eggs, m), (sperm, f))[:1 if same else 2]:
        linked = [grp for grp in system.groups if len(grp.loci) > 1]
        x_linked = system.x_group is not None and len(system.x_group.loci) > 1 and g.sex == "female"
        if not linked and not x_linked:
            continue
        rec = sum((v.frequency for v in views if v.recombinant), Fraction(0))
        parental = [v for v in views if not v.recombinant]
        name = genotype_text(system, g, "markup")
        if len(views) == 1:
            continue
        if rec == 0:
            if len(parental) > 1 and any(len(set(pair)) > 1 for grp, pair in zip(system.groups, g.autosomes) if len(grp.loci) > 1):
                notes.append(f"{name}: no crossing over in this sex, so no recombinant gametes")
            continue
        each_p = parental[0].frequency if parental else Fraction(0)
        each_r = next(v.frequency for v in views if v.recombinant)
        notes.append(f"{name}: parental gametes {percent_text(each_p)} each, recombinant {percent_text(each_r)} each "
                     f"(recombination frequency {percent_text(rec)})")
    if result.lethal:
        dead = [z for z in result.zygotes if is_lethal(system, z)]
        names = ", ".join(genotype_text(system, z, "markup") for z in dead)
        notes.append(f"{names} dies before birth ({fraction_text(result.lethal)} of zygotes): the survivors show "
                     f"{ratio_text(result.phenotype_ratio)}")
    if kind == "test":
        tester = f if roles[1] == "tester" else m
        notes.append(f"test cross: the tester {genotype_text(system, tester, 'markup')} makes only recessive gametes, so the offspring "
                     f"show the other parent's gametes and their frequencies")
    if kind == "reciprocal":
        same = "" if system.needs_sexes else " (no sex-linked or mitochondrial locus here, so the offspring are the same)"
        notes.append(f"reciprocal cross: the same two lines with the sexes swapped{same}")
    for e in system.epistasis:
        notes.append(epistasis_note(system, e))
    return notes


def epistasis_note(system: GeneticSystem, e: Any) -> str:
    """What the epistasis does, in the loci's own symbols: ``ee masks the B locus …``."""
    first, second = (system.locus(n) for n in e.loci)
    dom1, rec1 = symbol_markup(first.levels[0][0]), symbol_markup(first.levels[-1][0])
    dom2, rec2 = symbol_markup(second.levels[0][0]), symbol_markup(second.levels[-1][0])
    locus1, locus2 = f"<i>{first.symbol}</i>", f"<i>{second.symbol}</i>"
    p = e.phenotypes
    if e.kind == "recessive":
        return f"recessive epistasis: {rec1}{rec1} masks the {locus2} locus ({rec1}{rec1} is {p[-1]} whatever {locus2})"
    if e.kind == "dominant":
        return f"dominant epistasis: {dom1}_ masks the {locus2} locus ({dom1}_ is {p[0]} whatever {locus2})"
    if e.kind == "suppression":
        return f"dominant suppression: {dom1}_ suppresses {dom2} ({dom1}_ is {p[0]}; only {rec1}{rec1} {dom2}_ is {p[1]})"
    if e.kind == "duplicate":
        return f"duplicate genes: a dominant allele at {locus1} or {locus2} gives {p[0]}; only {rec1}{rec1} {rec2}{rec2} is {p[1]}"
    if e.kind == "complementary":
        return f"complementary genes: {p[0]} needs a dominant allele at both {locus1} and {locus2} ({dom1}_ {dom2}_); otherwise {p[1]}"
    return f"cumulative effect: {dom1}_ {dom2}_ {p[0]}, a dominant allele at one locus {p[1]}, none {p[2]}"


def build_plan(data: Mapping[str, Any], where: str = "params") -> CrossPlan:
    """The plan of a ``cross`` scene from its params (the genetic system, the parents, ``kind``,
    ``P``, ``show``, ``branch``)."""
    system = build_system(_system_spec(data), where)
    m, f, kind, roles, p_line, offspring = _parents(system, data, where)
    result = cross(system, m, f, where)
    same = not system.needs_sexes and m == f
    eggs = _views(system, m, result.eggs)
    sperm = _views(system, f, result.sperm)
    cells: list[Cell] = []
    for i, e in enumerate(eggs, start=1):
        for j, s in enumerate(sperm, start=1):
            z = fertilize(system, e.gamete, s.gamete)
            dead = is_lethal(system, z)
            phs = () if dead else tuple(phenotypes_of(system, z).items())
            cells.append(Cell(i, j, z, e.frequency * s.frequency, dead, phs, genotype_text(system, z, "markup"),
                              genotype_key(system, z)))
    uniform = len({c.probability for c in cells}) == 1
    single = all(len(c.phenotypes) == 1 for c in cells if not c.lethal)
    survivors_ratio = result.phenotype_ratio
    animal = animal_of(data.get("animal"), data.get("preset"), [str(data.get("title") or "")] + [t.name for t in system.traits])
    phenotypes: list[PhenotypeClass] = []
    for k, ((ph, share), n) in enumerate(zip(result.phenotypes.items(), survivors_ratio), start=1):
        where_cells = tuple((c.row, c.col) for c in cells if any(p == ph for p, _ in c.phenotypes))
        count = len(where_cells) if uniform and single else None
        traits = [t.name for t in system.traits]
        normals = [system.locus(t.loci[0]).normal if t.epistasis is None else None for t in system.traits]
        phenotypes.append(PhenotypeClass(k, class_label(ph), ph, share, n, where_cells, count,
                                         tuple(class_glyphs(traits, list(ph.traits), normals, animal))))
    zygote_ratio = ratio(result.zygotes.values())
    genotypes: list[GenotypeClass] = []
    for k, ((z, share), n) in enumerate(zip(result.zygotes.items(), zygote_ratio), start=1):
        where_cells = tuple((c.row, c.col) for c in cells if c.genotype == z)
        genotypes.append(GenotypeClass(k, genotype_key(system, z), genotype_text(system, z, "markup"), z, share,
                                       result.genotypes.get(z, Fraction(0)), n, is_lethal(system, z), where_cells,
                                       len(where_cells) if uniform else None))
    show = str(data.get("show") or "auto")
    if show not in SHOWS:
        raise VidgenError(f"{where}.show: '{show}': use {', '.join(SHOWS)}{did_you_mean(show, list(SHOWS))}")
    side = max(len(eggs), len(sperm))
    if show == "auto":
        show = "punnett" if side <= AUTO_SIDE else "branch"
    if show == "punnett" and side > MAX_SIDE:
        raise VidgenError(f"{where}.show: a parent makes {side} kinds of gametes: a Punnett square of more than {MAX_SIDE} × {MAX_SIDE} "
                          f"is unreadable; use show: branch (the branch diagram)")
    by = str(data.get("branch") or "phenotypes")
    if by not in BRANCH_BY:
        raise VidgenError(f"{where}.branch: '{by}': use {', '.join(BRANCH_BY)}{did_you_mean(by, list(BRANCH_BY))}")
    tree = None
    if show == "branch":
        tree = _tree(system, result, by)
        if len(tree.leaves) > MAX_LEAVES:
            raise VidgenError(f"{where}.branch: the {by} branch diagram has {len(tree.leaves)} classes; at most {MAX_LEAVES} fit — "
                              f"use branch: phenotypes" + (" or fewer loci" if by == "phenotypes" else ""))
    notes = _notes(system, m, f, kind, roles, result, eggs, sperm, same)
    return CrossPlan(system, m, f, kind, roles, system.sex_chromosomes, p_line, offspring, result, eggs, sperm, tuple(cells), uniform,
                     tuple(phenotypes), tuple(genotypes), show, tree, tuple(notes))


@lru_cache(maxsize=32)
def _cached(key: str) -> CrossPlan:
    return build_plan(json.loads(key))


def plan_cross(data: Mapping[str, Any]) -> CrossPlan:
    """:func:`build_plan`, cached by the params' JSON."""
    return _cached(json.dumps(dict(data), sort_keys=True, default=str))


def match_observed(plan: CrossPlan, observed: Any, where: str = "observed") -> list[int]:
    """The observed counts in the phenotype classes' order, from ``{class label: count}`` (words
    in any order: ``yellow round``) or a list in class order; every class once."""
    labels = [c.label for c in plan.phenotypes]
    if isinstance(observed, Sequence) and not isinstance(observed, str):
        if len(observed) != len(labels):
            raise VidgenError(f"{where}: {len(observed)} counts for {len(labels)} classes ({'; '.join(labels)}): one count per class, in this order")
        values = list(observed)
        names = labels
    elif isinstance(observed, Mapping):
        keys = {normalize_label(lb): k for k, lb in enumerate(labels)}
        values = [None] * len(labels)
        names = labels
        for raw, value in observed.items():
            k = keys.get(normalize_label(str(raw)))
            if k is None:
                raise VidgenError(f"{where}: '{raw}' is not a phenotype class of this cross (classes: {'; '.join(labels)})"
                                  f"{did_you_mean(str(raw), labels)}")
            if values[k] is not None:
                raise VidgenError(f"{where}: class '{labels[k]}' is given twice")
            values[k] = value
        missing = [labels[k] for k, v in enumerate(values) if v is None]
        if missing:
            raise VidgenError(f"{where}: give a count for every class; missing: {'; '.join(missing)}")
    else:
        raise VidgenError(f"{where}: write the counts by class, {{{labels[0]}: 315, ...}}, or as a list in class order")
    out = []
    for name, value in zip(names, values):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise VidgenError(f"{where}: '{name}': {value!r} is not a count (a whole number ≥ 0)")
        out.append(value)
    if sum(out) == 0:
        raise VidgenError(f"{where}: the counts add up to 0")
    return out


def significance(value: Any, where: str = "alpha") -> Fraction:
    """α from 0.05, ``"5%"`` or ``1/20``: strictly between 0 and 1."""
    a = as_fraction(value, where, "alpha")
    if not 0 < a < 1:
        raise VidgenError(f"{where}: {value}: a significance level is between 0 and 1 (0.05 is usual)")
    return a


__all__ = [
    "AUTO_SIDE", "BRANCH_BY", "KINDS", "MAX_LEAVES", "MAX_SIDE", "SHOWS", "Allele", "Branch", "Cell", "CrossPlan", "GameteView",
    "GenotypeClass", "PhenotypeClass", "Tree", "build_plan", "class_label", "genotype_key", "fraction_text", "gamete_view", "match_observed",
    "normalize_label", "percent_text", "plan_cross", "ratio_text", "significance",
]
