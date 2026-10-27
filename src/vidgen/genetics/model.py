"""The genetic system of a cross or a pedigree (DESIGN.md §96.3): loci with their alleles, the
dominance between them, lethal alleles, penetrance and expressivity, the chromosome each locus
is on, linkage groups with recombination frequencies, and epistasis between two loci. Built from
plain YAML data by :func:`build_system`, which refuses mistakes with the reason and a
did-you-mean. Probabilities are exact (:class:`fractions.Fraction`). No manim."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any

from vidgen.cellworld.model import did_you_mean
from vidgen.errors import VidgenError

from .notation import canonical_symbol, is_wild_type_symbol, symbol_ascii

#: Where a locus is: an autosome, the X or Y chromosome, or the mitochondrial genome.
CHROMOSOMES = ("autosome", "X", "Y", "mt")
_CHROMOSOME_ALIASES = {"autosome": "autosome", "autosomal": "autosome", "x": "X", "x_linked": "X", "y": "Y", "y_linked": "Y",
                       "mt": "mt", "mito": "mt", "mitochondrial": "mt", "mtdna": "mt"}
DOMINANCE_WORDS = ("complete", "incomplete", "codominant")
LETHAL_KINDS = ("recessive", "dominant")
EXPRESSIVITY = ("constant", "variable")
#: Epistasis between two loci, with the F2 ratio each gives from a dihybrid AaBb × AaBb.
EPISTASIS_KINDS: dict[str, str] = {
    "recessive": "9:3:4 — the epistatic locus' homozygous recessive masks the other locus",
    "dominant": "12:3:1 — a dominant allele at the epistatic locus masks the other locus",
    "suppression": "13:3 — a dominant suppressor at the epistatic locus gives the other locus' recessive phenotype",
    "duplicate": "15:1 — a dominant allele at either locus gives the phenotype (duplicate genes)",
    "complementary": "9:7 — the phenotype needs a dominant allele at both loci (complementary genes)",
    "cumulative": "9:6:1 — a dominant allele at each locus adds to the phenotype (duplicate genes with cumulative effect)",
}
_SYMMETRIC = ("duplicate", "complementary", "cumulative")
_LOCUS_KEYS = ("gene", "trait", "alleles", "dominance", "heterozygotes", "chromosome", "penetrance", "normal", "expressivity", "lethal")
_SYSTEM_KEYS = ("preset", "loci", "linkage", "epistasis", "sex")
_LINKAGE_KEYS = ("loci", "rf", "rf_male", "coincidence", "interference")
_EPISTASIS_KEYS = ("kind", "epistatic", "hypostatic", "loci", "phenotypes", "trait")
HALF = Fraction(1, 2)


@dataclass(frozen=True)
class Allele:
    """An allele: its canonical ``symbol`` (``I^A``), the phenotype of its homozygote (or
    hemizygote), whether it is the wild type, and ``lethal`` (``recessive``: homozygotes and
    hemizygotes die; ``dominant``: every carrier dies)."""

    symbol: str
    phenotype: str | None
    wild_type: bool = False
    lethal: str | None = None


@dataclass(frozen=True)
class Locus:
    """A gene locus: its symbol (``A``, ``I``, ``w``), the trait it affects, its chromosome, its
    alleles, the dominance hierarchy (``levels``: most dominant first; alleles of one level are
    ``codominant`` or show ``incomplete`` dominance, ``level_kinds``), the heterozygotes' own
    phenotypes, penetrance per phenotype, the phenotype a non-penetrant individual shows
    (``normal``) and the expressivity."""

    symbol: str
    trait: str
    chromosome: str
    alleles: tuple[Allele, ...]
    levels: tuple[tuple[str, ...], ...]
    level_kinds: tuple[str, ...]
    heterozygotes: Mapping[frozenset[str], str] = field(default_factory=dict)
    penetrance: Mapping[str, Fraction] = field(default_factory=dict)
    normal: str | None = None
    expressivity: str = "constant"

    def allele(self, symbol: str) -> Allele:
        return next(a for a in self.alleles if a.symbol == symbol)

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(a.symbol for a in self.alleles)

    def level_of(self, symbol: str) -> int:
        return next(i for i, level in enumerate(self.levels) if symbol in level)

    def rank(self, symbol: str) -> tuple[int, int]:
        """Sort key: the dominance level, then the order the alleles were listed in."""
        return self.level_of(symbol), self.symbols.index(symbol)

    def phenotype(self, alleles: Sequence[str]) -> str | None:
        """The phenotype of one (hemizygous) or two alleles, before penetrance."""
        if len(alleles) == 1 or alleles[0] == alleles[1]:
            return self.allele(alleles[0]).phenotype
        a, b = sorted(alleles, key=self.rank)
        if self.level_of(a) != self.level_of(b):
            return self.allele(a).phenotype
        return self.heterozygotes.get(frozenset((a, b))) or f"{self.allele(a).phenotype} and {self.allele(b).phenotype}"

    @property
    def phenotypes(self) -> tuple[str, ...]:
        """Every phenotype the locus can show, in dominance order (a level's heterozygotes after
        its alleles' own phenotypes: red, pink, white; A, B, AB, O)."""
        out: list[str] = []

        def add(p: str | None) -> None:
            if p is not None and p not in out:
                out.append(p)

        for level, kind in zip(self.levels, self.level_kinds):
            if kind == "incomplete":                   # the intermediate between its parents: red, pink, white
                for i, a in enumerate(level):
                    add(self.allele(a).phenotype)
                    for b in level[i + 1:]:
                        add(self.phenotype((a, b)))
                continue
            for s in level:
                add(self.allele(s).phenotype)
            for i, a in enumerate(level):
                for b in level[i + 1:]:
                    add(self.phenotype((a, b)))
        if self.normal is not None and self.normal not in out:
            out.append(self.normal)
        return tuple(out)

    @property
    def is_simple(self) -> bool:
        """Two alleles, one completely dominant over the other."""
        return len(self.alleles) == 2 and len(self.levels) == 2

    @property
    def dominant_phenotype(self) -> str | None:
        return self.allele(self.levels[0][0]).phenotype

    @property
    def recessive_phenotype(self) -> str | None:
        return self.allele(self.levels[-1][0]).phenotype

    @property
    def recessive_allele(self) -> str | None:
        """The allele a tester is homozygous for: the one allele of the lowest level."""
        return self.levels[-1][0] if len(self.levels[-1]) == 1 else None


@dataclass(frozen=True)
class LinkageGroup:
    """Loci on one chromosome, in map order, with the recombination frequency of each adjacent
    interval (``rf``; ``rf_male`` when male meiosis differs: none in Drosophila males), and the
    coefficient of coincidence for three loci (double crossovers observed / expected). A single
    unlinked locus is a group of one."""

    loci: tuple[str, ...]
    chromosome: str
    rf: tuple[Fraction, ...] = ()
    rf_male: tuple[Fraction, ...] | None = None
    coincidence: Fraction = Fraction(1)

    def rates(self, sex: str | None) -> tuple[Fraction, ...]:
        return self.rf_male if sex == "male" and self.rf_male is not None else self.rf


@dataclass(frozen=True)
class Epistasis:
    """Epistasis between two loci: ``kind`` (:data:`EPISTASIS_KINDS`), the epistatic and the
    hypostatic locus (in that order in ``loci``; any order for the symmetric kinds), the combined
    trait's name and its phenotypes in the textbook order of the ratio."""

    kind: str
    loci: tuple[str, str]
    trait: str
    phenotypes: tuple[str, ...]


@dataclass(frozen=True)
class Trait:
    """One phenotype column: an independent locus, or two loci in epistasis."""

    name: str
    loci: tuple[str, ...]
    phenotypes: tuple[str, ...]
    epistasis: Epistasis | None = None


@dataclass(frozen=True)
class GeneticSystem:
    """Everything a cross needs to know about the loci (built by :func:`build_system`)."""

    loci: tuple[Locus, ...]
    groups: tuple[LinkageGroup, ...]
    x_group: LinkageGroup | None
    y_loci: tuple[str, ...]
    mt_loci: tuple[str, ...]
    epistasis: tuple[Epistasis, ...]
    traits: tuple[Trait, ...]
    sex_chromosomes: bool

    def locus(self, symbol: str) -> Locus:
        return next(lo for lo in self.loci if lo.symbol == symbol)

    @property
    def locus_symbols(self) -> tuple[str, ...]:
        return tuple(lo.symbol for lo in self.loci)

    @property
    def x_loci(self) -> tuple[str, ...]:
        return self.x_group.loci if self.x_group is not None else ()

    @property
    def needs_sexes(self) -> bool:
        """Whether a cross must say which parent is the mother: sex chromosomes or mtDNA."""
        return self.sex_chromosomes or bool(self.mt_loci)

    def owner(self, allele: str) -> Locus:
        """The locus an allele symbol belongs to (symbols are unique within a system)."""
        return next(lo for lo in self.loci if allele in lo.symbols)


# ----- building ------------------------------------------------------------------------------------


def as_fraction(value: Any, where: str, what: str) -> Fraction:
    """An exact fraction from ``0.17``, ``"17%"``, ``"1/6"`` or ``1`` (floats through their
    decimal text, so 0.1 is exactly 1/10)."""
    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, (int, Fraction)):
            return Fraction(value)
        if isinstance(value, float):
            return Fraction(repr(value))
        text = str(value).strip()
        if text.endswith("%"):
            return Fraction(text[:-1].strip()) / 100
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        raise VidgenError(f"{where}: {what} '{value}': write a number, a fraction such as 1/6 or a percentage such as 17%") from None


def _keys(data: Mapping[str, Any], allowed: Sequence[str], where: str) -> None:
    for key in data:
        if key not in allowed:
            raise VidgenError(f"{where}: unknown key '{key}': use {', '.join(allowed)}{did_you_mean(str(key), list(allowed))}")


def _mapping(value: Any, where: str, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VidgenError(f"{where}: {what} must be a mapping")
    return value


def chromosome_name(value: Any, where: str) -> str:
    """``autosome``, ``X``, ``Y`` or ``mt`` from what an author writes (``x_linked``, ``mitochondrial``…)."""
    text = str(value).strip()
    key = text.lower().replace("-", "_").replace(" ", "_")
    if key not in _CHROMOSOME_ALIASES:
        raise VidgenError(f"{where}: chromosome '{text}': use {', '.join(CHROMOSOMES)}{did_you_mean(key, list(_CHROMOSOME_ALIASES))}")
    return _CHROMOSOME_ALIASES[key]


def _alleles(value: Any, where: str) -> list[Allele]:
    """Alleles from ``{A: round, a: wrinkled}`` (most dominant first), ``[A, a]`` or a list of
    ``{symbol, phenotype, wild_type, lethal}``."""
    out: list[Allele] = []
    if isinstance(value, Mapping):
        items: list[tuple[Any, Any]] = list(value.items())
        entries = [{"symbol": k, "phenotype": v} for k, v in items]
    elif isinstance(value, Sequence) and not isinstance(value, str):
        entries = [e if isinstance(e, Mapping) else {"symbol": e} for e in value]
    else:
        raise VidgenError(f"{where}: alleles: write them most dominant first, {{A: round, a: wrinkled}}")
    for i, entry in enumerate(entries):
        here = f"{where}.alleles[{i}]"
        _keys(entry, ("symbol", "phenotype", "wild_type", "lethal"), here)
        if "symbol" not in entry:
            raise VidgenError(f"{here}: an allele needs its symbol")
        symbol = canonical_symbol(entry["symbol"], here)
        phenotype = entry.get("phenotype")
        lethal = entry.get("lethal")
        if lethal is not None and lethal not in LETHAL_KINDS:
            raise VidgenError(f"{here}: lethal '{lethal}': use {' or '.join(LETHAL_KINDS)}")
        wild = bool(entry.get("wild_type", is_wild_type_symbol(symbol)))
        out.append(Allele(symbol, None if phenotype is None else str(phenotype), wild, lethal))
    if len(out) < 2:
        raise VidgenError(f"{where}: a locus needs at least two alleles")
    seen: set[str] = set()
    for a in out:
        if a.symbol in seen:
            raise VidgenError(f"{where}: allele {symbol_ascii(a.symbol)} is listed twice")
        seen.add(a.symbol)
    return out


def _levels(value: Any, symbols: list[str], where: str) -> tuple[tuple[tuple[str, ...], ...], tuple[str, ...]]:
    """The dominance hierarchy from ``complete`` (the order listed), ``incomplete`` /
    ``codominant`` (two alleles) or a written hierarchy ``"I^A = I^B > i"`` (``>`` complete
    dominance, ``=`` codominance, ``~`` incomplete dominance)."""
    if value is None or value == "complete":
        return tuple((s,) for s in symbols), tuple("single" for _ in symbols)
    text = str(value).strip()
    if text in ("incomplete", "codominant"):
        if len(symbols) != 2:
            raise VidgenError(f"{where}: dominance: {text} needs two alleles; with {len(symbols)} write the hierarchy, "
                              f"e.g. 'I^A = I^B > i' (> complete, = codominant, ~ incomplete)")
        return (tuple(symbols),), ("codominant" if text == "codominant" else "incomplete",)
    if not any(op in text for op in "><=~"):
        raise VidgenError(f"{where}: dominance '{text}': use {', '.join(DOMINANCE_WORDS)} or a hierarchy such as 'I^A = I^B > i'"
                          f"{did_you_mean(text, list(DOMINANCE_WORDS))}")
    if "<" in text:
        raise VidgenError(f"{where}: dominance '{text}': write the hierarchy most dominant first with >, e.g. 'C > c^{{ch}} > c^h > c'")
    levels: list[tuple[str, ...]] = []
    kinds: list[str] = []
    for part in text.split(">"):
        has_eq, has_tilde = "=" in part, "~" in part
        if has_eq and has_tilde:
            raise VidgenError(f"{where}: dominance '{text}': one level is either codominant (=) or incomplete (~), not both")
        members = [canonical_symbol(s, where) for s in part.replace("=", "~").split("~")]
        for s in members:
            if s not in symbols:
                raise VidgenError(f"{where}: dominance '{text}': {symbol_ascii(s)} is not an allele of this locus "
                                  f"(alleles: {', '.join(symbol_ascii(x) for x in symbols)}){did_you_mean(s, symbols)}")
        levels.append(tuple(members))
        kinds.append("codominant" if has_eq else "incomplete" if has_tilde else "single")
    flat = [s for level in levels for s in level]
    for s in symbols:
        if flat.count(s) != 1:
            word = "is missing from" if s not in flat else "appears twice in"
            raise VidgenError(f"{where}: dominance '{text}': {symbol_ascii(s)} {word} the hierarchy")
    return tuple(levels), tuple(kinds)


def _pair(text: Any, symbols: Sequence[str], where: str) -> frozenset[str]:
    parts = [canonical_symbol(p, where) for p in str(text).split("/")]
    if len(parts) != 2 or parts[0] == parts[1]:
        raise VidgenError(f"{where}: heterozygote '{text}': write two different alleles, e.g. C^R/C^W")
    for s in parts:
        if s not in symbols:
            raise VidgenError(f"{where}: heterozygote '{text}': {symbol_ascii(s)} is not an allele of this locus{did_you_mean(s, list(symbols))}")
    return frozenset(parts)


def build_locus(data: Mapping[str, Any], where: str) -> Locus:
    """One locus from its YAML mapping (keys :data:`_LOCUS_KEYS`), checked."""
    _keys(data, _LOCUS_KEYS, where)
    if "gene" not in data:
        raise VidgenError(f"{where}: a locus needs its gene symbol: gene: A")
    gene = canonical_symbol(data["gene"], f"{where}.gene")
    if "alleles" not in data:
        raise VidgenError(f"{where}: locus {gene} needs its alleles, most dominant first: alleles: {{A: round, a: wrinkled}}")
    alleles = _alleles(data["alleles"], where)
    symbols = [a.symbol for a in alleles]
    lethal = _mapping(data.get("lethal", {}), where, "lethal")
    for raw, kind in lethal.items():
        s = canonical_symbol(raw, f"{where}.lethal")
        if s not in symbols:
            raise VidgenError(f"{where}.lethal: {symbol_ascii(s)} is not an allele of locus {gene}{did_you_mean(s, symbols)}")
        if kind not in LETHAL_KINDS:
            raise VidgenError(f"{where}.lethal: {symbol_ascii(s)}: '{kind}': use {' or '.join(LETHAL_KINDS)}")
        alleles = [Allele(a.symbol, a.phenotype, a.wild_type, kind) if a.symbol == s else a for a in alleles]
    chromosome = chromosome_name(data.get("chromosome", "autosome"), f"{where}.chromosome")
    levels, kinds = _levels(data.get("dominance"), symbols, f"{where}.dominance")
    heterozygotes: dict[frozenset[str], str] = {}
    for raw, phenotype in _mapping(data.get("heterozygotes", {}), where, "heterozygotes").items():
        pair = _pair(raw, symbols, f"{where}.heterozygotes")
        a, b = sorted(pair, key=symbols.index)
        level_a = next(i for i, lv in enumerate(levels) if a in lv)
        level_b = next(i for i, lv in enumerate(levels) if b in lv)
        if level_a != level_b:
            top, low = (a, b) if level_a < level_b else (b, a)
            raise VidgenError(f"{where}.heterozygotes: {symbol_ascii(top)} is completely dominant over {symbol_ascii(low)}, so "
                              f"{symbol_ascii(top)}/{symbol_ascii(low)} shows {symbol_ascii(top)}'s phenotype; for a phenotype of its own "
                              f"write {symbol_ascii(top)} ~ {symbol_ascii(low)} (incomplete) or {symbol_ascii(top)} = {symbol_ascii(low)} "
                              f"(codominant) in dominance")
        heterozygotes[pair] = str(phenotype)
    for level, kind in zip(levels, kinds):
        if kind != "incomplete":
            continue
        for i, a in enumerate(level):
            for b in level[i + 1:]:
                if frozenset((a, b)) not in heterozygotes:
                    raise VidgenError(f"{where}: incomplete dominance between {symbol_ascii(a)} and {symbol_ascii(b)}: name the "
                                      f"heterozygote's phenotype, heterozygotes: {{{symbol_ascii(a)}/{symbol_ascii(b)}: pink}}")
    expressivity = str(data.get("expressivity", "constant"))
    if expressivity not in EXPRESSIVITY:
        raise VidgenError(f"{where}: expressivity '{expressivity}': use {' or '.join(EXPRESSIVITY)}")
    locus = Locus(gene, str(data.get("trait", gene)), chromosome, tuple(alleles), levels, kinds, heterozygotes)
    normal = data.get("normal")
    wild = [a for a in alleles if a.wild_type]
    if normal is None and len(wild) == 1:
        normal = wild[0].phenotype
    phenotypes = locus.phenotypes
    if normal is not None and str(normal) not in phenotypes:
        raise VidgenError(f"{where}: normal '{normal}' is not a phenotype of locus {gene} ({', '.join(phenotypes)})"
                          f"{did_you_mean(str(normal), list(phenotypes))}")
    penetrance = _penetrance(data.get("penetrance"), phenotypes, None if normal is None else str(normal), gene, where)
    if penetrance and normal is None:
        raise VidgenError(f"{where}: penetrance below 1 needs the phenotype non-penetrant individuals show: normal: "
                          f"{phenotypes[-1] if len(phenotypes) > 1 else 'unaffected'}")
    if chromosome == "Y" and normal is None:
        raise VidgenError(f"{where}: a Y-linked locus needs the phenotype of individuals without a Y (females): normal: unaffected, "
                          f"or mark the wild-type allele")
    for a in alleles:
        if a.phenotype is None and chromosome in ("Y", "mt"):
            raise VidgenError(f"{where}: allele {symbol_ascii(a.symbol)} needs its phenotype")
    return Locus(gene, locus.trait, chromosome, tuple(alleles), levels, kinds, heterozygotes, penetrance,
                 None if normal is None else str(normal), expressivity)


def _penetrance(value: Any, phenotypes: tuple[str, ...], normal: str | None, gene: str, where: str) -> dict[str, Fraction]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        others = [p for p in phenotypes if p != normal]
        if normal is None or len(others) != 1:
            raise VidgenError(f"{where}: penetrance {value}: name the phenotype it applies to, penetrance: {{{others[0] if others else 'affected'}: 0.8}}"
                              + ("" if normal is not None else ", and the phenotype otherwise shown: normal: ..."))
        value = {others[0]: value}
    out: dict[str, Fraction] = {}
    for phenotype, raw in value.items():
        p = as_fraction(raw, f"{where}.penetrance", "penetrance")
        if str(phenotype) not in phenotypes:
            raise VidgenError(f"{where}.penetrance: '{phenotype}' is not a phenotype of locus {gene} ({', '.join(phenotypes)})"
                              f"{did_you_mean(str(phenotype), list(phenotypes))}")
        if str(phenotype) == normal:
            raise VidgenError(f"{where}.penetrance: '{phenotype}' is the normal phenotype; penetrance is the share of the "
                              f"genotype's carriers that show the trait")
        if not 0 <= p <= 1:
            raise VidgenError(f"{where}.penetrance: {phenotype}: {raw} is not between 0 and 1")
        if p != 1:
            out[str(phenotype)] = p
    return out


def _rf_list(value: Any, count: int, where: str, what: str) -> tuple[Fraction, ...]:
    raw = list(value) if isinstance(value, Sequence) and not isinstance(value, str) else [value]
    if len(raw) != count:
        raise VidgenError(f"{where}: {what}: {count + 1} loci have {count} interval{'s' if count > 1 else ''}: write "
                          f"{count} recombination frequenc{'ies' if count > 1 else 'y'}, one per adjacent pair in map order")
    out = []
    for r in raw:
        f = as_fraction(r, where, what)
        if f < 0:
            raise VidgenError(f"{where}: {what} {r}: a recombination frequency cannot be negative")
        if f > HALF:
            raise VidgenError(f"{where}: {what} {r}: a recombination frequency cannot exceed 0.5 (50%): loci far apart on one "
                              f"chromosome assort independently (RF = 0.5); map distances over 50 cM add up shorter intervals")
        out.append(f)
    return tuple(out)


def _linkage(data: Mapping[str, Any], loci: dict[str, Locus], where: str) -> LinkageGroup:
    _keys(data, _LINKAGE_KEYS, where)
    names = [canonical_symbol(s, where) for s in data.get("loci", [])]
    if len(names) < 2:
        raise VidgenError(f"{where}: a linkage group lists two or more loci in map order: loci: [A, B]")
    for n in names:
        if n not in loci:
            raise VidgenError(f"{where}: locus {symbol_ascii(n)} is not defined{did_you_mean(n, list(loci))}")
    if len(set(names)) != len(names):
        raise VidgenError(f"{where}: a locus is listed twice in loci")
    chromosomes = {loci[n].chromosome for n in names}
    if len(chromosomes) > 1:
        raise VidgenError(f"{where}: loci {', '.join(names)} are on different chromosomes ({', '.join(sorted(chromosomes))}): "
                          f"linked loci share one chromosome")
    chromosome = chromosomes.pop()
    if chromosome in ("Y", "mt"):
        what = "Y-linked loci are inherited as one block (no crossing over outside the pseudoautosomal regions)" if chromosome == "Y" \
            else "the mitochondrial genome is inherited whole from the mother (no meiotic recombination)"
        raise VidgenError(f"{where}: {what}: no linkage group is needed")
    if "rf" not in data:
        raise VidgenError(f"{where}: give the recombination frequency of each interval: rf: 0.17 (or 17%)")
    rf = _rf_list(data["rf"], len(names) - 1, where, "rf")
    rf_male = None
    if "rf_male" in data:
        if chromosome == "X":
            raise VidgenError(f"{where}: rf_male: males have one X, so X-linked loci do not recombine in males")
        rf_male = _rf_list(data["rf_male"], len(names) - 1, where, "rf_male")
    coincidence = Fraction(1)
    if "coincidence" in data and "interference" in data:
        raise VidgenError(f"{where}: give coincidence or interference (= 1 − coincidence), not both")
    if "coincidence" in data or "interference" in data:
        if len(names) != 3:
            raise VidgenError(f"{where}: the coefficient of coincidence is for three linked loci (two adjacent intervals)")
        key = "coincidence" if "coincidence" in data else "interference"
        value = as_fraction(data[key], where, key)
        coincidence = value if key == "coincidence" else 1 - value
        if coincidence < 0:
            raise VidgenError(f"{where}: interference {data[key]} is above 1: the coefficient of coincidence (1 − interference) cannot be negative")
        for rates in (rf, rf_male or rf):
            double = coincidence * rates[0] * rates[1]
            if double > min(rates) or 1 - rates[0] - rates[1] + double < 0:
                raise VidgenError(f"{where}: coincidence {coincidence} with rf {', '.join(str(r) for r in rates)} gives more double "
                                  f"crossovers than single ones: lower the coincidence")
    return LinkageGroup(tuple(names), chromosome, rf, rf_male, coincidence)


def _locus_ref(value: Any, loci: dict[str, Locus], where: str, what: str) -> str:
    name = canonical_symbol(value, where)
    if name not in loci:
        raise VidgenError(f"{where}: {what} {symbol_ascii(name)} is not a defined locus{did_you_mean(name, list(loci))}")
    return name


def _epistasis(data: Mapping[str, Any], loci: dict[str, Locus], where: str) -> Epistasis:
    _keys(data, _EPISTASIS_KEYS, where)
    kind = str(data.get("kind", ""))
    if kind not in EPISTASIS_KINDS:
        raise VidgenError(f"{where}: kind '{kind}': use one of {', '.join(EPISTASIS_KINDS)}{did_you_mean(kind, list(EPISTASIS_KINDS))}")
    if kind in _SYMMETRIC:
        if "epistatic" in data or "hypostatic" in data:
            raise VidgenError(f"{where}: in {kind} epistasis neither locus masks the other: write loci: [A, B]")
        pair = [_locus_ref(v, loci, where, "locus") for v in data.get("loci", [])]
        if len(pair) != 2:
            raise VidgenError(f"{where}: {kind} epistasis is between two loci: loci: [A, B]")
    else:
        if "loci" in data:
            raise VidgenError(f"{where}: {kind} epistasis names the masking locus and the masked one: epistatic: E, hypostatic: B")
        for key in ("epistatic", "hypostatic"):
            if key not in data:
                raise VidgenError(f"{where}: {kind} epistasis needs {key}: <locus>")
        pair = [_locus_ref(data["epistatic"], loci, where, "epistatic locus"), _locus_ref(data["hypostatic"], loci, where, "hypostatic locus")]
    if pair[0] == pair[1]:
        raise VidgenError(f"{where}: epistasis is between two different loci (interaction of alleles at one locus is dominance)")
    first, second = loci[pair[0]], loci[pair[1]]
    needs_simple = (first, second) if kind != "recessive" and kind != "dominant" else (first,)
    for lo in needs_simple:
        if not lo.is_simple:
            raise VidgenError(f"{where}: {kind} epistasis needs locus {lo.symbol} with two alleles, one completely dominant")
        if lo.chromosome in ("Y", "mt"):
            raise VidgenError(f"{where}: locus {lo.symbol} is {lo.chromosome}-linked (one copy): epistasis here uses dominant / recessive phenotypes")
    named = data.get("phenotypes")
    count = {"cumulative": 3}.get(kind, 2)
    if kind in ("recessive", "dominant"):
        if named is not None:
            raise VidgenError(f"{where}: {kind} epistasis shows the loci's own phenotypes; rename them on the alleles")
        hyp = list(second.phenotypes)
        mask = first.recessive_phenotype if kind == "recessive" else first.dominant_phenotype
        if mask is None or any(p is None for p in hyp):
            raise VidgenError(f"{where}: the alleles of {first.symbol} and {second.symbol} need phenotypes")
        phenotypes = tuple(hyp + [mask]) if kind == "recessive" else tuple([mask] + hyp)
    elif kind == "suppression":
        if named is not None:
            raise VidgenError(f"{where}: suppression shows the hypostatic locus' phenotypes; rename them on its alleles")
        dom, rec = second.dominant_phenotype, second.recessive_phenotype
        if dom is None or rec is None:
            raise VidgenError(f"{where}: the alleles of {second.symbol} need phenotypes")
        phenotypes = (rec, dom)
    else:
        if named is None:
            same = first.phenotypes == second.phenotypes and None not in (first.dominant_phenotype, first.recessive_phenotype)
            if kind == "cumulative" or not same:
                example = "[disc, sphere, long]" if kind == "cumulative" else "[purple, white]"
                order = "both dominant, one dominant, none" if kind == "cumulative" else (
                    "a dominant allele at both loci, otherwise" if kind == "complementary" else "a dominant allele at either locus, none")
                raise VidgenError(f"{where}: name the {count} phenotypes ({order}): phenotypes: {example}")
            phenotypes = (first.dominant_phenotype, first.recessive_phenotype)  # type: ignore[assignment]
        else:
            if not isinstance(named, Sequence) or isinstance(named, str) or len(named) != count:
                raise VidgenError(f"{where}: phenotypes: {kind} epistasis has {count} phenotypes, in ratio order")
            phenotypes = tuple(str(p) for p in named)
            if len(set(phenotypes)) != count:
                raise VidgenError(f"{where}: phenotypes: the {count} phenotypes must differ")
    trait = str(data.get("trait", second.trait if kind not in _SYMMETRIC else first.trait))
    return Epistasis(kind, (pair[0], pair[1]), trait, phenotypes)


def build_system(spec: Mapping[str, Any], where: str = "params") -> GeneticSystem:
    """The genetic system of a ``cross`` / ``pedigree`` from its YAML: ``loci`` (or a ``preset``),
    ``linkage``, ``epistasis`` and ``sex: XY`` (sex chromosomes even without X-linked loci)."""
    from .presets import PRESETS

    spec = _mapping(spec, where, "the genetic system")
    _keys(spec, _SYSTEM_KEYS, where)
    if "preset" in spec:
        name = str(spec["preset"])
        if name not in PRESETS:
            raise VidgenError(f"{where}: preset '{name}': use one of {', '.join(PRESETS)}{did_you_mean(name, list(PRESETS))}")
        extra = [k for k in spec if k != "preset"]
        if extra:
            raise VidgenError(f"{where}: preset '{name}' defines the loci; leave out {', '.join(extra)} or write the loci yourself")
        return build_system(PRESETS[name].spec, f"{where} (preset '{name}')")
    raw_loci = spec.get("loci")
    if not isinstance(raw_loci, Sequence) or isinstance(raw_loci, str) or not raw_loci:
        raise VidgenError(f"{where}: loci: list the loci, e.g. loci: [{{gene: A, alleles: {{A: round, a: wrinkled}}}}], or use a preset")
    loci: dict[str, Locus] = {}
    owner: dict[str, str] = {}
    for i, raw in enumerate(raw_loci):
        here = f"{where}.loci[{i}]"
        locus = build_locus(_mapping(raw, here, "a locus"), here)
        if locus.symbol in loci:
            raise VidgenError(f"{here}: locus {locus.symbol} is defined twice")
        for s in locus.symbols:
            if s in owner:
                raise VidgenError(f"{here}: allele {symbol_ascii(s)} is also an allele of locus {owner[s]}: allele symbols must differ "
                                  f"between loci so genotypes read unambiguously (write vg^+ and b^+, not + twice)")
            owner[s] = locus.symbol
        loci[locus.symbol] = locus
    sex = spec.get("sex")
    if sex is not None and str(sex) != "XY":
        raise VidgenError(f"{where}: sex '{sex}': use XY (female XX, male XY)")
    if sex is not None or any(lo.chromosome in ("X", "Y") for lo in loci.values()):
        clash = [s for s in owner if s in ("X", "Y")]
        if clash:
            raise VidgenError(f"{where}: allele {clash[0]} of locus {owner[clash[0]]}: with sex chromosomes in the cross, X and Y name "
                              f"them; give the allele another symbol")
    groups: dict[str, LinkageGroup] = {}
    for i, raw in enumerate(spec.get("linkage", []) or []):
        group = _linkage(_mapping(raw, f"{where}.linkage[{i}]", "a linkage group"), loci, f"{where}.linkage[{i}]")
        for n in group.loci:
            if n in groups:
                raise VidgenError(f"{where}.linkage[{i}]: locus {n} is already in another linkage group: list all the loci of one "
                                  f"chromosome in one group, in map order")
            groups[n] = group
    x_loci = [n for n, lo in loci.items() if lo.chromosome == "X"]
    x_groups = {id(groups[n]) for n in x_loci if n in groups}
    if len(x_loci) > 1 and (len(x_groups) != 1 or any(n not in groups for n in x_loci)):
        raise VidgenError(f"{where}: loci {', '.join(x_loci)} are all X-linked: give their map order and recombination frequencies "
                          f"in one group, linkage: [{{loci: [{', '.join(x_loci)}], rf: ...}}]")
    x_group = groups[x_loci[0]] if len(x_loci) > 1 else LinkageGroup((x_loci[0],), "X") if x_loci else None
    autosomal: list[LinkageGroup] = []
    for n, lo in loci.items():
        if lo.chromosome != "autosome":
            continue
        group = groups.get(n, LinkageGroup((n,), "autosome"))
        if group not in autosomal:
            autosomal.append(group)
    epistasis: list[Epistasis] = []
    in_epistasis: set[str] = set()
    for i, raw in enumerate(spec.get("epistasis", []) or []):
        here = f"{where}.epistasis[{i}]"
        e = _epistasis(_mapping(raw, here, "an epistasis entry"), loci, here)
        for n in e.loci:
            if n in in_epistasis:
                raise VidgenError(f"{here}: locus {n} is already in another epistasis entry")
            in_epistasis.add(n)
        epistasis.append(e)
        for n in e.loci:             # unnamed alleles (cumulative etc.): A_ and aa, never shown
            lo = loci[n]
            if any(a.phenotype is None for a in lo.alleles):
                top, low = lo.levels[0][0], lo.levels[-1][0]
                names = {top: f"{top}_", low: f"{low}{low}"}
                loci[n] = replace(lo, alleles=tuple(replace(a, phenotype=a.phenotype or names[a.symbol]) for a in lo.alleles))
    traits: list[Trait] = []
    for n, lo in loci.items():
        e = next((x for x in epistasis if n in x.loci), None)
        if e is not None:
            if n == e.loci[0]:
                traits.append(Trait(e.trait, e.loci, e.phenotypes, e))
            continue
        missing = [a.symbol for a in lo.alleles if a.phenotype is None]
        if missing:
            raise VidgenError(f"{where}: allele {symbol_ascii(missing[0])} of locus {n} needs its phenotype: alleles: "
                              f"{{{', '.join(f'{symbol_ascii(s)}: ...' for s in lo.symbols)}}}")
        traits.append(Trait(lo.trait, (n,), lo.phenotypes))
    return GeneticSystem(
        loci=tuple(loci.values()), groups=tuple(autosomal), x_group=x_group,
        y_loci=tuple(n for n, lo in loci.items() if lo.chromosome == "Y"),
        mt_loci=tuple(n for n, lo in loci.items() if lo.chromosome == "mt"),
        epistasis=tuple(epistasis), traits=tuple(traits),
        sex_chromosomes=bool(x_loci) or any(lo.chromosome == "Y" for lo in loci.values()) or sex is not None,
    )


__all__ = [
    "CHROMOSOMES", "DOMINANCE_WORDS", "EPISTASIS_KINDS", "EXPRESSIVITY", "LETHAL_KINDS", "Allele", "Epistasis", "GeneticSystem",
    "LinkageGroup", "Locus", "Trait", "as_fraction", "build_locus", "build_system", "chromosome_name",
]
