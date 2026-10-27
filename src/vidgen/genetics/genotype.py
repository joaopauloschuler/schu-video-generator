"""Genotypes and gametes (DESIGN.md §96.3): parsing what authors write (``AaBb``, ``A/a B/b``,
``I^A i``, ``AB/ab`` for linked loci in coupling, ``X^H X^h``, ``X^h Y``, ``X^{H,b} Y``) into
canonical genotypes of a :class:`~vidgen.genetics.model.GeneticSystem`, and writing them back as
plain text, Pango markup or YAML. No manim."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from vidgen.cellworld.model import did_you_mean
from vidgen.errors import VidgenError

from .model import GeneticSystem
from .notation import (
    canonical_symbol, chromosome_ascii, chromosome_markup, chromosome_text, split_symbol, symbol_ascii, symbol_markup, symbol_text,
)

SEXES = ("female", "male")
Haplotype = tuple[str, ...]


class SexChromosome(NamedTuple):
    """An X or a Y with the alleles of the system's X-linked (or Y-linked) loci, in map order."""

    letter: str
    alleles: Haplotype


@dataclass(frozen=True)
class Genotype:
    """A diploid genotype: for each autosomal group of the system (an unlinked locus or linked
    loci in map order) the two homologous haplotypes, the sex chromosomes (``None`` without
    them), and one allele per mitochondrial locus. Canonical: the dominant haplotype first
    (``Aa``, ``AB/ab``), X before Y."""

    autosomes: tuple[tuple[Haplotype, Haplotype], ...]
    sex_chromosomes: tuple[SexChromosome, SexChromosome] | None
    mito: Haplotype = ()

    @property
    def sex(self) -> str | None:
        if self.sex_chromosomes is None:
            return None
        return "male" if self.sex_chromosomes[1].letter == "Y" else "female"


@dataclass(frozen=True)
class Gamete:
    """A haploid gamete: one haplotype per autosomal group, one sex chromosome, and the mtDNA an
    egg carries (sperm and pollen pass on none: ``mito`` is empty)."""

    autosomes: tuple[Haplotype, ...]
    sex_chromosome: SexChromosome | None
    mito: Haplotype = ()


def _hap_key(system: GeneticSystem, loci: tuple[str, ...], hap: Haplotype) -> tuple[tuple[int, int], ...]:
    return tuple(system.locus(n).rank(a) for n, a in zip(loci, hap))


def make_genotype(system: GeneticSystem, autosomes: list[tuple[Haplotype, Haplotype]],
                  sex_chromosomes: tuple[SexChromosome, SexChromosome] | None, mito: Haplotype) -> Genotype:
    """The canonical genotype of these chromosomes (homologues sorted dominant first)."""
    pairs = []
    for group, (h1, h2) in zip(system.groups, autosomes):
        pairs.append(tuple(sorted((h1, h2), key=lambda h: _hap_key(system, group.loci, h))))
    sex = None
    if sex_chromosomes is not None:
        a, b = sex_chromosomes
        if a.letter == "Y" or (b.letter == "X" and a.letter == "X" and system.x_group is not None
                               and _hap_key(system, system.x_loci, b.alleles) < _hap_key(system, system.x_loci, a.alleles)):
            a, b = b, a
        sex = (a, b)
    return Genotype(tuple(pairs), sex, tuple(mito))  # type: ignore[arg-type]


def alleles_at(system: GeneticSystem, genotype: Genotype, locus: str) -> tuple[str, ...]:
    """The alleles an individual has at ``locus``: two (autosomes, X in females), one (X in males,
    Y in males, mtDNA) or none (Y in females)."""
    lo = system.locus(locus)
    if lo.chromosome == "autosome":
        for group, (h1, h2) in zip(system.groups, genotype.autosomes):
            if locus in group.loci:
                i = group.loci.index(locus)
                return h1[i], h2[i]
    if lo.chromosome == "mt":
        return (genotype.mito[system.mt_loci.index(locus)],)
    assert genotype.sex_chromosomes is not None
    letter, names = ("X", system.x_loci) if lo.chromosome == "X" else ("Y", system.y_loci)
    return tuple(c.alleles[names.index(locus)] for c in genotype.sex_chromosomes if c.letter == letter)


# ----- parsing --------------------------------------------------------------------------------------


@dataclass
class _Token:
    kind: str            # "allele", "sex", "slash", "x_bare", "y_bare"
    text: str
    allele: str = ""
    chromosome: SexChromosome | None = None


def _forms(symbol: str) -> tuple[str, ...]:
    base, sup = split_symbol(symbol)
    return (symbol, f"{base}^{{{sup}}}") if sup else (symbol,)


class _Reader:
    def __init__(self, system: GeneticSystem, text: str, where: str) -> None:
        self.system, self.text, self.where = system, text, where
        self.table: dict[str, tuple[str, str]] = {}
        for lo in system.loci:
            kind = {"X": "x_bare", "Y": "y_bare"}.get(lo.chromosome, "allele")
            for a in lo.symbols:
                for form in _forms(a):
                    self.table[form] = (kind, a)
        self.longest = sorted(self.table, key=len, reverse=True)

    def fail(self, message: str) -> VidgenError:
        return VidgenError(f"{self.where}: genotype '{self.text}': {message}")

    def _match(self, chunk: str, i: int, forms: list[str]) -> str | None:
        return next((f for f in forms if chunk.startswith(f, i)), None)

    def _sex(self, chunk: str, i: int) -> tuple[_Token, int]:
        letter = chunk[i]
        names = self.system.x_loci if letter == "X" else self.system.y_loci
        i += 1
        if i >= len(chunk) or chunk[i] != "^":
            return _Token("sex", letter, chromosome=SexChromosome(letter, ())), i
        i += 1
        symbols = [s for n in names for s in self.system.locus(n).symbols]
        if i < len(chunk) and chunk[i] == "{":
            end = chunk.find("}", i)
            if end < 0:
                raise self.fail(f"'{chunk[i - 2:]}' has no closing brace")
            inner = chunk[i + 1:end]
            parts = [canonical_symbol(p, self.where) for p in inner.split(",")] if "," in inner else \
                [canonical_symbol(inner, self.where)]
            i = end + 1
        else:
            forms = sorted((f for s in symbols for f in _forms(s)), key=len, reverse=True)
            found = self._match(chunk, i, forms)
            if found is None:
                rest = chunk[i:i + 4] or "(nothing)"
                where = "X-linked" if letter == "X" else "Y-linked"
                if not names:
                    raise self.fail(f"{letter}^{rest}: this system has no {where} locus; write {letter} alone")
                raise self.fail(f"{letter}^{rest}: not an allele of the {where} loci ({', '.join(symbol_ascii(s) for s in symbols)})"
                                f"{did_you_mean(rest[:1], symbols)}")
            parts = [canonical_symbol(found.replace("{", "").replace("}", ""), self.where)]
            i += len(found)
        for p in parts:
            if p not in symbols:
                other = next((lo for lo in self.system.loci if p in lo.symbols), None)
                if other is not None:
                    raise self.fail(f"{symbol_ascii(p)} is an allele of locus {other.symbol}, which is "
                                    f"{'autosomal' if other.chromosome == 'autosome' else other.chromosome + '-linked'}, not on the {letter}")
                raise self.fail(f"{symbol_ascii(p)} is not an allele of the {letter}-linked loci{did_you_mean(p, symbols)}")
        by_locus = {self.system.owner(p).symbol: p for p in parts}
        if len(by_locus) != len(parts) or set(by_locus) != set(names):
            want = ", ".join(names)
            raise self.fail(f"each {letter} carries one allele of each {letter}-linked locus ({want}): "
                            f"write {letter}^{{{','.join(symbol_ascii(self.system.locus(n).symbols[0]) for n in names)}}}"
                            if len(names) > 1 else f"each {letter} carries one allele of locus {want}")
        alleles = tuple(by_locus[n] for n in names)
        return _Token("sex", chunk, chromosome=SexChromosome(letter, alleles)), i

    def tokens(self, chunk: str) -> list[_Token]:
        out: list[_Token] = []
        i = 0
        while i < len(chunk):
            if chunk[i] == "/":
                out.append(_Token("slash", "/"))
                i += 1
                continue
            found = self._match(chunk, i, self.longest)
            if chunk[i] in "XY" and (found is None or (len(found) == 1 and self.system.sex_chromosomes)):
                token, i = self._sex(chunk, i)
                out.append(token)
                continue
            if found is None:
                rest = chunk[i:].split("/")[0][:6]
                known = sorted({symbol_ascii(a) for _, a in self.table.values()})
                hint = next((h for k in range(len(rest), 0, -1) if (h := did_you_mean(rest[:k], known))), "")
                raise self.fail(f"'{rest}' is not an allele of any locus (alleles: {', '.join(known)}){hint}")
            kind, allele = self.table[found]
            if kind != "allele":
                letter = "X" if kind == "x_bare" else "Y"
                raise self.fail(f"{symbol_ascii(allele)} is {letter}-linked: write it on its chromosome, "
                                + (f"{letter}^{symbol_ascii(allele)} X^... (female) or {letter}^{symbol_ascii(allele)} Y (male)" if letter == "X"
                                   else f"X Y^{symbol_ascii(allele)} (males only)"))
            out.append(_Token("allele", found, allele=allele))
            i += len(found)
        return out


def parse_genotype(system: GeneticSystem, text: str, where: str = "genotype", sex: str | None = None) -> Genotype:
    """The genotype written ``text`` (see the module doc), checked against the system: every
    allele defined, each locus given once (two alleles; one for mtDNA), sex chromosomes XX or XY
    with the X- and Y-linked alleles on them, the phase written for linked loci heterozygous at
    two or more of them; ``sex`` (``female`` / ``male``), when given, must match."""
    reader = _Reader(system, str(text), where)
    pairs: dict[str, list[str]] = {}
    phased: list[tuple[tuple[str, ...], Haplotype, Haplotype]] = []
    sex_chromosomes: list[SexChromosome] = []
    mito: dict[str, str] = {}
    for chunk in str(text).split():
        tokens = reader.tokens(chunk)
        slashes = [i for i, t in enumerate(tokens) if t.kind == "slash"]
        if not slashes:
            for t in tokens:
                if t.kind == "sex":
                    sex_chromosomes.append(t.chromosome)  # type: ignore[arg-type]
                elif system.owner(t.allele).chromosome == "mt":
                    owner = system.owner(t.allele).symbol
                    if owner in mito:
                        raise reader.fail(f"mitochondrial locus {owner} has one allele per individual (maternal inheritance, homoplasmy)")
                    mito[owner] = t.allele
                else:
                    pairs.setdefault(system.owner(t.allele).symbol, []).append(t.allele)
            continue
        if len(slashes) > 1:
            raise reader.fail(f"'{chunk}' has more than one /: write one locus or one linkage group per part, e.g. 'A/a B/b' or 'AB/ab'")
        left, right = tokens[:slashes[0]], tokens[slashes[0] + 1:]
        if not left or not right:
            raise reader.fail(f"'{chunk}': write a homologue on each side of the /")
        kinds = {t.kind for t in left + right}
        if kinds == {"sex"}:
            if len(left) != 1 or len(right) != 1:
                raise reader.fail(f"'{chunk}': write one sex chromosome on each side: X^H/X^h or X^H/Y")
            sex_chromosomes += [left[0].chromosome, right[0].chromosome]  # type: ignore[list-item]
            continue
        if kinds != {"allele"}:
            raise reader.fail(f"'{chunk}': write sex chromosomes and autosomal alleles in separate parts, e.g. 'A/a X^H/Y'")
        loci_l = tuple(system.owner(t.allele).symbol for t in left)
        loci_r = tuple(system.owner(t.allele).symbol for t in right)
        if any(system.locus(n).chromosome == "mt" for n in loci_l + loci_r):
            raise reader.fail("a mitochondrial locus has one allele per individual: write it without a /")
        if loci_l != loci_r or len(set(loci_l)) != len(loci_l):
            raise reader.fail(f"'{chunk}': each homologue lists one allele of the same loci in the same order (AB/ab, Ab/aB)")
        if len(loci_l) == 1:
            pairs.setdefault(loci_l[0], []).extend((left[0].allele, right[0].allele))
        else:
            phased.append((loci_l, tuple(t.allele for t in left), tuple(t.allele for t in right)))
    group_of = {n: g for g in system.groups for n in g.loci}
    phase: dict[tuple[str, ...], tuple[Haplotype, Haplotype]] = {}
    for loci, h1, h2 in phased:
        groups = {group_of[n].loci for n in loci}
        if all(len(g) == 1 for g in groups):          # phase written for unlinked loci: harmless, split it
            for k, n in enumerate(loci):
                if n in pairs:
                    raise reader.fail(f"locus {n} is written twice")
                pairs[n] = [h1[k], h2[k]]
            continue
        group = group_of[loci[0]].loci
        if len(groups) != 1 or set(loci) != set(group):
            linked = next(g for g in groups if len(g) > 1)
            raise reader.fail(f"loci {', '.join(linked)} are linked: write the phase of all of them together, e.g. "
                              f"{_example(system, linked)}")
        if group in phase or any(n in pairs for n in loci):
            raise reader.fail(f"loci {', '.join(group)} are written twice")
        order = [loci.index(n) for n in group]
        phase[group] = (tuple(h1[k] for k in order), tuple(h2[k] for k in order))
    autosomes: list[tuple[Haplotype, Haplotype]] = []
    for group in system.groups:
        if group.loci in phase:
            autosomes.append(phase[group.loci])
            continue
        for n in group.loci:
            if n not in pairs:
                raise reader.fail(f"locus {n} ({system.locus(n).trait}) is missing: write two alleles of it, e.g. "
                                  f"{''.join(symbol_ascii(s) for s in system.locus(n).symbols[:2])}")
            if len(pairs[n]) != 2:
                raise reader.fail(f"locus {n} has {len(pairs[n])} alleles here; a diploid has two (one on each homologue)")
        if len(group.loci) > 1:
            hetero = [n for n in group.loci if pairs[n][0] != pairs[n][1]]
            if len(hetero) > 1:
                raise reader.fail(f"loci {', '.join(group.loci)} are linked and this genotype is heterozygous at {', '.join(hetero)}: "
                                  f"write the phase, {_example(system, group.loci)} (coupling) or "
                                  f"{_example(system, group.loci, repulsion=True)} (repulsion)")
        autosomes.append((tuple(pairs[n][0] for n in group.loci), tuple(pairs[n][1] for n in group.loci)))
    for n in system.mt_loci:
        if n not in mito:
            raise reader.fail(f"mitochondrial locus {n} is missing: write its allele ({', '.join(system.locus(n).symbols)})")
    sex_pair = _sex_pair(system, sex_chromosomes, reader, sex)
    return make_genotype(system, autosomes, sex_pair, tuple(mito[n] for n in system.mt_loci))


def _sex_pair(system: GeneticSystem, chromosomes: list[SexChromosome], reader: _Reader,
              sex: str | None) -> tuple[SexChromosome, SexChromosome] | None:
    if not system.sex_chromosomes:
        if chromosomes:
            raise reader.fail("this system has no X- or Y-linked locus: leave out X and Y, or set sex: XY to follow the sexes")
        return None
    letters = "".join(sorted(c.letter for c in chromosomes))
    if letters not in ("XX", "XY"):
        if not chromosomes:
            raise reader.fail(f"write the sex chromosomes: {_sex_example(system, 'female')} (female) or {_sex_example(system, 'male')} (male)")
        raise reader.fail(f"the sex chromosomes are {letters or 'missing'}: a cross takes XX (female) or XY (male); "
                          f"aneuploidies such as XXY or X0 are karyotypes (Step 216)")
    if system.x_loci and any(c.letter == "X" and not c.alleles for c in chromosomes):
        raise reader.fail(f"each X carries the allele of the X-linked locus: {_sex_example(system, 'female')}")
    if system.y_loci and any(c.letter == "Y" and not c.alleles for c in chromosomes):
        raise reader.fail(f"the Y carries the allele of the Y-linked locus: {_sex_example(system, 'male')}")
    found = "male" if letters == "XY" else "female"
    if sex is not None and sex != found:
        reason = "has a Y chromosome: a female is XX" if found == "male" else "has two X chromosomes and no Y: a male is XY"
        raise reader.fail(f"{reason}")
    xs = [c for c in chromosomes if c.letter == "X"]
    ys = [c for c in chromosomes if c.letter == "Y"]
    pair = (xs[0], xs[1]) if found == "female" else (xs[0], ys[0])
    return pair  # type: ignore[return-value]


def _example(system: GeneticSystem, loci: tuple[str, ...], repulsion: bool = False) -> str:
    tops = [symbol_ascii(system.locus(n).levels[0][0]) for n in loci]
    lows = [symbol_ascii(system.locus(n).levels[-1][0]) for n in loci]
    if repulsion:
        tops[-1], lows[-1] = lows[-1], tops[-1]
    return f"{''.join(tops)}/{''.join(lows)}"


def _sex_example(system: GeneticSystem, sex: str) -> str:
    x = [system.locus(n).levels[0][0] for n in system.x_loci]
    y = [system.locus(n).levels[0][0] for n in system.y_loci]
    xa, ya = chromosome_ascii("X", tuple(x)), chromosome_ascii("Y", tuple(y))
    return f"{xa} {xa}" if sex == "female" else f"{xa} {ya}"


# ----- writing --------------------------------------------------------------------------------------


def _simple(symbols: list[str]) -> bool:
    """Whether alleles can run together unambiguously: one-letter bases with Unicode superscripts."""
    return all(len(split_symbol(s)[0]) == 1 and "^" not in symbol_text(s) for s in symbols)


def genotype_text(system: GeneticSystem, genotype: Genotype, style: str = "text") -> str:
    """The genotype as ``text`` (Unicode superscripts: ``IᴬIᴮ Rr``), ``markup`` (Pango, italic
    alleles) or ``ascii`` (the YAML form, which :func:`parse_genotype` reads back). Single-letter
    alleles run together (``AaBb``, ``XᴴXʰ``); longer ones are joined with ``/`` and loci spaced
    (``vg⁺/vg b⁺/b``); linked loci show their phase (``AB/ab``)."""
    one = {"text": symbol_text, "markup": symbol_markup, "ascii": symbol_ascii}[style]
    chrom = {"text": chromosome_text, "markup": chromosome_markup, "ascii": chromosome_ascii}[style]
    all_symbols = [s for lo in system.loci for s in lo.symbols]
    simple = _simple(all_symbols)
    parts: list[str] = []
    sep = "" if simple or style == "ascii" else " "
    for group, (h1, h2) in zip(system.groups, genotype.autosomes):
        if len(group.loci) > 1:
            parts.append(f"{sep.join(one(a) for a in h1)}/{sep.join(one(a) for a in h2)}")
        else:
            parts.append(f"{one(h1[0])}{one(h2[0])}" if simple else f"{one(h1[0])}/{one(h2[0])}")
    if genotype.sex_chromosomes is not None:
        a, b = genotype.sex_chromosomes
        parts.append(chrom(a.letter, a.alleles) + (" " if style == "ascii" else "") + chrom(b.letter, b.alleles)
                     if simple or style == "ascii" else f"{chrom(a.letter, a.alleles)}/{chrom(b.letter, b.alleles)}")
    parts += [one(m) for m in genotype.mito]
    joined_simple = simple and all(len(g.loci) == 1 for g in system.groups)
    return ("" if joined_simple and style != "ascii" else " ").join(parts)


def gamete_text(system: GeneticSystem, gamete: Gamete, style: str = "text") -> str:
    """A gamete as ``text``, ``markup`` or ``ascii``: ``AB``, ``Aᴮ…``, ``aXʰ``, ``Y``."""
    one = {"text": symbol_text, "markup": symbol_markup, "ascii": symbol_ascii}[style]
    chrom = {"text": chromosome_text, "markup": chromosome_markup, "ascii": chromosome_ascii}[style]
    simple = _simple([s for lo in system.loci for s in lo.symbols])
    parts = [("" if simple or style == "ascii" else " ").join(one(a) for a in hap) for hap in gamete.autosomes]
    if gamete.sex_chromosome is not None:
        parts.append(chrom(gamete.sex_chromosome.letter, gamete.sex_chromosome.alleles))
    parts += [one(m) for m in gamete.mito]
    return ("" if simple and style != "ascii" else " ").join(parts)


__all__ = ["SEXES", "Gamete", "Genotype", "SexChromosome", "alleles_at", "gamete_text", "genotype_text", "make_genotype", "parse_genotype"]
