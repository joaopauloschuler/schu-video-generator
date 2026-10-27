"""The genetics lint's knowledge (DESIGN.md §96.18): the narration and on-screen text of a genetics
scene checked against what its model computes — ratios, fractions and probabilities of a cross, a
pedigree's stated mode and its carrier and risk values, map distances and recombination
frequencies, Hardy–Weinberg arithmetic, CRISPR facts (the PAM, where Cas9 cuts, blunt ends),
karyotype notation and the conditions it names, HGVS variants and legacy names. Like
:mod:`vidgen.cellworld.accuracy` (whose sentence helpers it reuses) each check is narrow on
purpose: a sentence with a negation, a contrast, a question or a hypothetical is left alone, a
number is only read next to the words that say what it is, so correct material gives no
findings. Every function returns :class:`~vidgen.cellworld.accuracy.Claim` objects (the quoted
sentence and the fix); the lint rules (:mod:`vidgen.lint.genetics_rule`) say which scene and beat.
No manim."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from vidgen.cellworld.accuracy import Claim, normal_text, plain, sentences
from vidgen.errors import VidgenError

# ----- numbers and fractions in words ------------------------------------------------------------------

_UNITS = {w: k for k, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                                     "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * k for k, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if k >= 2}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
_NUMBER_WORD = "|".join(sorted([*_UNITS, *_TENS, *_SCALES], key=len, reverse=True))
#: A number written in digits (``2,500``, ``0.17``) or in English words (``two thousand five hundred``).
NUM = (rf"(?:\d{{1,3}}(?:,\d{{3}})+(?!\d|,\d)|\d+(?:\.\d+)?|(?:{_NUMBER_WORD})(?:(?:[- ]|\s+and\s+)(?:{_NUMBER_WORD}))*)")
_NUM_RE = re.compile(rf"\b{NUM}\b", re.IGNORECASE)


def number(text: str) -> float | None:
    """The value of a number in digits or English words (``2,500``, ``twenty-one``, ``two thousand
    five hundred``), or ``None``."""
    t = text.strip().lower()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", t):
        return float(t.replace(",", ""))
    total = current = 0
    words = [w for w in re.split(r"[- ]+|\s+and\s+", t) if w and w != "and"]
    if not words:
        return None
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = (current or 1) * 100
        elif w in _SCALES:
            total += (current or 1) * _SCALES[w]
            current = 0
        else:
            return None
    return float(total + current)


def _exact(value: float) -> Fraction:
    return Fraction(str(value)) if not float(value).is_integer() else Fraction(int(value))


#: Fraction words: their denominators.
ORDINALS: dict[str, int] = {
    "half": 2, "halves": 2, "third": 3, "thirds": 3, "quarter": 4, "quarters": 4, "fourth": 4, "fourths": 4, "fifth": 5, "fifths": 5,
    "sixth": 6, "sixths": 6, "seventh": 7, "sevenths": 7, "eighth": 8, "eighths": 8, "ninth": 9, "ninths": 9, "tenth": 10,
    "tenths": 10, "twelfth": 12, "twelfths": 12, "sixteenth": 16, "sixteenths": 16, "thirty-second": 32, "thirty-seconds": 32,
    "sixty-fourth": 64, "sixty-fourths": 64,
}
_ORD = "|".join(sorted(ORDINALS, key=len, reverse=True))
_FRACTION_RE = re.compile(
    rf"(?P<a>\b{NUM})(?:\s*/\s*|\s+in\s+|\s+out\s+of\s+|-in-)(?P<b>{NUM}\b)"
    rf"|(?P<pc>\b{NUM})\s*(?:%|\s+percent\b|\s+per\s+cent\b)"
    rf"|(?:\b(?P<num>{NUM}|an?)[\s-]+)?\b(?P<ord>{_ORD})\b(?!-)"
    r"|\b(?P<all>all)(?=\s+(?:of\s+)?(?:the\s+|their\s+|her\s+|his\s+)?(?:offspring|progeny|children|sons|daughters|males|females|boys|"
    r"girls|plants|seeds|peas|flies|mice|kittens|puppies|pups|dogs|chicks|F2)\b)",
    re.IGNORECASE)
_APPROX = re.compile(r"\b(?:about|approximately|around|roughly|nearly|almost|close\s+to|some|circa|ca\.?)\s*$|[~≈]\s*$", re.IGNORECASE)
_BOUND = re.compile(r"\b(?:more\s+than|less\s+than|fewer\s+than|over|under|above|below|at\s+least|at\s+most|up\s+to|exceeds?|"
                    r"exceeding|maximum|max(?:imum)?\s+of|never\s+(?:more|above))\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Said:
    """A share written in a sentence: where, as written, its value, whether it was said as an
    approximation (``about 25 %``) or a bound (``more than 50 %``), and how finely it was written
    (``17 %``: ±0.5 percentage points; ``1/4``: exactly)."""

    start: int
    end: int
    text: str
    value: Fraction
    approx: bool = False
    bound: bool = False
    resolution: float = 0.0

    def matches(self, actual: Fraction | float, tolerance: float = 0.0) -> bool:
        """Whether the share written is ``actual`` (within its rounding, and ``tolerance`` relative
        when said as an approximation)."""
        slack = self.resolution + (tolerance * float(actual) if self.approx else 0.0) + 1e-12
        return abs(float(self.value) - float(actual)) <= slack


def _resolution(written: str, scale: float) -> float:
    m = re.search(r"\.(\d+)", written)
    return 0.5 * 10 ** (-(len(m.group(1)) if m else 0)) * scale


def shares_in(sentence: str) -> list[Said]:
    """The shares a sentence writes: ``1/4``, ``1 in 2,500``, ``one in four``, ``2 out of 3``,
    ``25 %``, ``twenty-five percent``, ``half``, ``a quarter``, ``three quarters``, ``two thirds``
    (an ordinal is a share only with a numerator other than "a", or before "of": "a third of",
    not "a third child")."""
    out: list[Said] = []
    for m in _FRACTION_RE.finditer(sentence):
        before = sentence[max(0, m.start() - 24):m.start()]
        approx, bound = _APPROX.search(before) is not None, _BOUND.search(before) is not None
        if m.group("a") is not None:
            a, b = number(m.group("a")), number(m.group("b"))
            if a is None or b is None or b < 2 or a <= 0 or a >= b or not a.is_integer() or not b.is_integer():
                continue
            value, res = Fraction(int(a), int(b)), 0.0
        elif m.group("all") is not None:
            value, res = Fraction(1), 0.0
        elif m.group("pc") is not None:
            v = number(m.group("pc"))
            if v is None or v > 100:
                continue
            value, res = _exact(v) / 100, _resolution(m.group("pc"), 0.01)
        else:
            word = m.group("ord").lower()
            num = (m.group("num") or "").lower()
            after = sentence[m.end():m.end() + 4].lower()
            ambiguous = word not in ("half", "halves", "quarter", "quarters")
            if ambiguous and num in ("", "a", "an") and not after.startswith(" of"):
                continue
            if word.endswith("s") and word not in ("halves",) and num in ("", "a", "an"):
                continue
            n = 1.0 if num in ("", "a", "an") else number(num)
            if n is None or not n.is_integer() or n <= 0:
                continue
            value, res = Fraction(int(n), ORDINALS[word]), 0.0
            if value >= 1:
                continue
        out.append(Said(m.start(), m.end(), m.group(0), value, approx, bound, res))
    return out


def share_text(f: Fraction | float) -> str:
    """``1/4 (25 %)``; ``49/1250 (≈ 1 in 25.5)`` for small shares; floats as ``≈ 3.9 %``."""
    if isinstance(f, float):
        return f"≈ {f * 100:.3g} %" if f >= 0.01 else f"≈ 1 in {1 / f:.3g}" if f > 0 else "0"
    if f == 0:
        return "0"
    pct = f * 100
    frac = f"{f.numerator}/{f.denominator}" if f.denominator != 1 else str(f.numerator)
    if f < Fraction(1, 20):
        inv = 1 / f
        tail = f"1 in {inv.numerator}" if inv.denominator == 1 else f"≈ 1 in {float(inv):.3g}"
        return f"{frac} ({tail})"
    tail = f"{float(pct):g} %" if (pct * 100).denominator == 1 else f"≈ {float(pct):.1f} %"
    return f"{frac} ({tail})"


def _quote(sentence: str, limit: int = 90) -> str:
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


#: Words that make a sentence about another case than the scene's: a hypothetical, a comparison.
HYPOTHETICAL = re.compile(r"\b(?:would|could|might|suppose\w*|imagine|instead|modif\w*|becom\w*|in\s+place\s+of|than|usual(?:ly)?|"
                          r"classic(?:al)?|familiar|expect\w*\s+(?:if|for|from|under|without|with)|underl\w*|otherwise|another|unlike|"
                          r"compar\w*|versus|vs|if\s+(?:it|they|the\s+(?:genes?|loci|trait)|these)\s+were)\b", re.IGNORECASE)


def _statements(text: str) -> Iterable[str]:
    """The plain statements of ``text`` (no negation, contrast, question or hypothetical)."""
    for s in sentences(text):
        if plain(s) and HYPOTHETICAL.search(s) is None:
            yield s


# ----- crosses: ratios and shares -----------------------------------------------------------------------

_GROUP = (r"offspring|progeny|children|child|kids|sons?|daughters?|males?|females?|boys?|girls?|men|women|man|woman|plants?|seeds?|peas|"
          r"flies|fly|mice|mouse|kittens?|puppies|pups?|dogs?|chicks?|chickens?|birds?|flowers?|individuals?|zygotes?|embryos?|babies|"
          r"baby|f2|fruits?|squash(?:es)?|rabbits?|animals?|population|survivors?")
_GROUP_RE = re.compile(rf"\b(?:{_GROUP})\b", re.IGNORECASE)
#: The group a share is of, right after it: "half (of) the sons", "a quarter of their surviving offspring".
_GROUP_AFTER = re.compile(rf"\s+(?:of\s+)?(?:the\s+|their\s+|her\s+|his\s+|these\s+|all\s+)?(?:[a-z0-9-]+\s+){{0,2}}?\b({_GROUP})\b",
                          re.IGNORECASE)
_CHANCE_RE = re.compile(r"\b(?:chances?|probability|probabilities|risks?|likelihood|odds)\b", re.IGNORECASE)
_MALE_RE = re.compile(r"\b(?:sons?|males?|boys?|men|man)\b", re.IGNORECASE)
_FEMALE_RE = re.compile(r"\b(?:daughters?|females?|girls?|women|woman)\b", re.IGNORECASE)
_GAMETES_RE = re.compile(r"\b(?:gametes?|pollen|eggs?|ova|ovules?|sperm|spermatozoa|alleles?|haplotypes?|chromosomes?|chromatids?)\b",
                         re.IGNORECASE)
_F1_RE = re.compile(r"\bF1\b|\bfirst\s+(?:filial\s+)?generation\b|\bhybrids?\b", re.IGNORECASE)
_F2_RE = re.compile(r"\bF2\b|\bsecond\s+(?:filial\s+)?generation\b", re.IGNORECASE)
_TEST_RE = re.compile(r"\b(?:test\s*-?\s*cross\w*|testcross\w*|back\s*-?\s*cross\w*)\b", re.IGNORECASE)
_RATIO_CONTEXT = re.compile(r"\b(?:ratios?|proportions?|segregat\w*|splits?|classes)\b", re.IGNORECASE)
_MARGINAL = re.compile(r"\b(?:each|separately|alone|individually|single|monohybrid|on\s+its\s+own|per\s+trait|one\s+trait|one\s+gene|"
                       r"either\s+trait|each\s+gene)\b", re.IGNORECASE)
_EPISTASIS_CONTEXT = re.compile(r"\b(?:epista\w*|mask\w*|classes|merg\w*|combin\w*|collaps\w*|pool\w*|group\w*|genotypic)\b", re.IGNORECASE)
_CARRIER_RE = re.compile(r"\b(?:carriers?|heterozygous|heterozygotes?)\b", re.IGNORECASE)
_NORMAL_PREFIX = ("normal", "unaffected", "wild type", "wild-type", "healthy")


@dataclass(frozen=True)
class Term:
    """A phenotype word found in a sentence: the trait (index) and the phenotype it names, or the
    heterozygotes (``trait`` -1, ``phenotype`` ``carrier``)."""

    start: int
    end: int
    trait: int
    phenotype: str


class CrossVocabulary:
    """How a cross's phenotypes are said: each phenotype's full name, the words that name only it
    (``wrinkled``, ``white``), *affected* / *unaffected* for a condition with a normal phenotype,
    short names (blood groups ``A``, ``AB``) only after *type* / *group*."""

    def __init__(self, plan: Any) -> None:
        self.plan = plan
        system = plan.system
        self.traits = system.traits
        entries: list[tuple[str, int, str]] = []
        words: dict[str, set[tuple[int, str]]] = {}
        for t, trait in enumerate(self.traits):
            for ph in trait.phenotypes:
                entries.append((ph.lower(), t, ph))
                for w in re.findall(r"[a-z]{3,}", ph.lower()):
                    words.setdefault(w, set()).add((t, ph))
        for w, owners in words.items():
            if len(owners) == 1 and w not in ("and", "the", "type", "group", "body", "wings", "eyes", "colour", "color", "coat"):
                t, ph = next(iter(owners))
                entries.append((w, t, ph))
        for t, trait in enumerate(self.traits):
            if len(trait.phenotypes) == 2:
                normal = [ph for ph in trait.phenotypes if ph.lower().startswith(_NORMAL_PREFIX)]
                if len(normal) == 1:
                    other = next(ph for ph in trait.phenotypes if ph != normal[0])
                    entries += [("unaffected", t, normal[0]), ("healthy", t, normal[0]), ("affected", t, other)]
        self.entries = sorted({e for e in entries}, key=lambda e: -len(e[0]))
        lo = system.loci[0]
        self.carrier_locus = lo.symbol if len(system.loci) == 1 and len(lo.symbols) == 2 and len(lo.levels) == 2 else None
        self.words = {w for w, _, _ in self.entries}

    def terms(self, text: str) -> list[Term]:
        """The phenotype words of ``text``, longest first, not overlapping."""
        found: list[Term] = []
        taken: list[tuple[int, int]] = []
        low = text.lower()
        for word, t, ph in self.entries:
            short = len(word) <= 2
            pattern = rf"(?:\b(?:type|group|blood\s+group)\s+)({re.escape(word)})\b" if short else rf"(?<![\w-]){re.escape(word)}(?![\w])"
            for m in re.finditer(pattern, low):
                a, b = (m.start(1), m.end(1)) if short else (m.start(), m.end())
                if any(a < y and x < b for x, y in taken):
                    continue
                if word == "affected" and low[max(0, a - 2):a] == "un":
                    continue
                taken.append((a, b))
                found.append(Term(a, b, t, ph))
        if self.carrier_locus is not None:
            for m in _CARRIER_RE.finditer(text):
                if not any(m.start() < y and x < m.end() for x, y in taken):
                    found.append(Term(m.start(), m.end(), -1, "carrier"))
        return sorted(found, key=lambda x: x.start)


def _sex_of(text: str) -> str | None:
    male, female = _MALE_RE.search(text) is not None, _FEMALE_RE.search(text) is not None
    return "male" if male and not female else "female" if female and not male else None


def _class_share(plan: Any, wanted: dict[int, str], carrier: bool, sex: str | None, joint: bool = False) -> Fraction | None:
    """The share of the cross's survivors (of ``sex``, when the cross follows the sexes) that show
    every ``wanted`` phenotype (trait index → phenotype), or that are heterozygous carriers;
    ``joint``: the share of all survivors that are of ``sex`` and show them ("a quarter of the
    children are affected sons")."""
    from .genotype import alleles_at

    result, system = plan.result, plan.system
    if not system.sex_chromosomes:
        sex = None
    if carrier:
        locus = system.loci[0].symbol
        total = sum((p for g, p in result.genotypes.items() if joint or sex is None or g.sex == sex), Fraction(0))
        het = sum((p for g, p in result.genotypes.items() if (sex is None or g.sex == sex) and len(set(alleles_at(system, g, locus))) == 2),
                  Fraction(0))
        return het / total if total else None
    total = sum((p for ph, p in result.phenotypes.items() if joint or sex is None or ph.sex == sex), Fraction(0))
    if not total:
        return None
    hit = sum((p for ph, p in result.phenotypes.items() if (sex is None or ph.sex == sex) and all(ph.traits[t] == name for t, name in wanted.items())),
              Fraction(0))
    return hit / total


def _ratio_of(values: Iterable[Fraction]) -> tuple[int, ...]:
    from .cross import ratio

    vals = [v for v in values if v]
    return tuple(ratio(vals)) if vals else ()


def _key(numbers: Sequence[int]) -> tuple[int, ...]:
    g = 0
    for n in numbers:
        g = math.gcd(g, n)
    return tuple(sorted((n // g for n in numbers), reverse=True)) if g else ()


def cross_ratios(plan: Any, observed: Sequence[int] | None = None) -> dict[str, tuple[int, ...]]:
    """The whole-number ratios a cross gives, by what they count: ``phenotypes``, ``genotypes``,
    ``zygotes`` (lethal genotypes included), by sex, sexes pooled, per trait (``trait:<name>``),
    without the epistasis (each locus' own phenotypes), each parent's gametes, the observed counts."""
    from .phenotype import locus_phenotypes

    result, system = plan.result, plan.system
    out: dict[str, tuple[int, ...]] = {"phenotypes": _ratio_of(result.phenotypes.values()),
                                       "genotypes": _ratio_of(result.genotypes.values()),
                                       "zygotes": _ratio_of(result.zygotes.values())}
    if system.sex_chromosomes:
        pooled: dict[tuple[str, ...], Fraction] = {}
        for ph, p in result.phenotypes.items():
            pooled[ph.traits] = pooled.get(ph.traits, Fraction(0)) + p
        out["phenotypes, sexes pooled"] = _ratio_of(pooled.values())
        for sex, name in (("male", "sons"), ("female", "daughters")):
            out[name] = _ratio_of(p for ph, p in result.phenotypes.items() if ph.sex == sex)
        out["sexes"] = (1, 1)
    for t, trait in enumerate(system.traits):
        marginal: dict[str, Fraction] = {}
        for ph, p in result.phenotypes.items():
            marginal[ph.traits[t]] = marginal.get(ph.traits[t], Fraction(0)) + p
        out[f"trait:{trait.name}"] = _ratio_of(marginal.values())
    if system.epistasis:
        own: dict[tuple[str, ...], Fraction] = {}
        for g, p in result.genotypes.items():
            combos: list[tuple[tuple[str, ...], Fraction]] = [((), p)]
            for lo in system.loci:
                combos = [(c + (name,), q * share) for c, q in combos for name, share in locus_phenotypes(system, g, lo).items()]
            for c, q in combos:
                own[c] = own.get(c, Fraction(0)) + q
        out["without the epistasis"] = _ratio_of(own.values())
    out["gametes:" + plan.roles[0]] = _ratio_of(g.frequency for g in plan.eggs)
    out["gametes:" + plan.roles[1]] = _ratio_of(g.frequency for g in plan.sperm)
    if observed:
        out["observed"] = tuple(int(x) for x in observed)
    return {k: v for k, v in out.items() if len(v) >= 1}


def ratios_said(sentence: str, words: Iterable[str]) -> list[tuple[str, tuple[int, ...], bool]]:
    """The ratios a sentence writes, ``(text, numbers, with phenotype words)``: ``9:3:3:1``, ``a 3 to
    1 ratio``, ``nine to three to three to one``, ``three round to one wrinkled``, ``9 purple : 7
    white`` (only the cross's phenotype words may stand between the numbers)."""
    names = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) or r"(?!x)x"
    tail = rf"(?:[\s,-]+(?:{names})){{0,3}}"
    colon = rf"\b{NUM}{tail}(?:\s*[:∶]\s*{NUM}{tail})+"
    to = rf"\b{NUM}{tail}(?:(?:\s+|-)to(?:\s+|-){NUM}{tail})+"
    out: list[tuple[str, tuple[int, ...], bool]] = []
    taken: list[tuple[int, int]] = []
    for pattern in (colon, to):
        for m in re.finditer(pattern, sentence, re.IGNORECASE):
            if any(m.start() < y and x < m.end() for x, y in taken):
                continue
            span = m.group(0)
            stripped = re.sub(rf"(?<![\w-])(?:{names})(?![\w])", " ", span, flags=re.IGNORECASE)
            values = [number(x) for x in _NUM_RE.findall(stripped)]
            if len(values) < 2 or any(v is None or not v.is_integer() or v <= 0 or v > 1000 for v in values):
                continue
            taken.append((m.start(), m.end()))
            with_words = stripped != span
            out.append((span.strip(" ,-"), tuple(int(v) for v in values if v is not None), with_words))
    return out


def cross_claims(text: str, plan: Any, observed: Sequence[int] | None = None, tolerance: float = 0.05) -> list[Claim]:
    """Ratios and shares in ``text`` that do not follow from the cross ``plan``
    (:class:`~vidgen.genetics.punnett.CrossPlan`): a ratio that is none of :func:`cross_ratios`
    (a per-trait ratio only when the sentence says it is about one trait), and a share of a named
    phenotype (or of the carriers) among the offspring, sons or daughters, or a child's chance of
    it, that differs from the cross's."""
    vocab = CrossVocabulary(plan)
    ratios = cross_ratios(plan, observed)
    pheno = ratios["phenotypes"]
    out: list[Claim] = []
    for s in _statements(text):
        if plan.p_line and _F1_RE.search(s) and not _F2_RE.search(s):
            continue                          # the F1 of a P cross, not the cross shown
        if plan.kind != "test" and _TEST_RE.search(s):
            continue                          # another cross
        q = _quote(s)
        gametes = _GAMETES_RE.search(s) is not None
        traits_named = {t for t, trait in enumerate(plan.system.traits) if trait.name.lower() in s.lower()}
        for said, numbers, with_words in ratios_said(s, vocab.words):
            if not with_words and _RATIO_CONTEXT.search(s) is None and ":" not in said and "∶" not in said:
                continue
            key = _key(numbers)
            allowed = [name for name, r in ratios.items()
                       if not name.startswith(("trait:", "gametes:", "sexes", "without")) or
                       (name.startswith("without") and _EPISTASIS_CONTEXT.search(s)) or
                       (name.startswith("gametes:") and gametes) or
                       (name == "sexes" and (_MALE_RE.search(s) or _FEMALE_RE.search(s))) or
                       (name.startswith("trait:") and (_MARGINAL.search(s) or traits_named or len({t.trait for t in vocab.terms(s)}) == 1
                                                         or len(plan.system.traits) == 1))]
            if any(_key(ratios[name]) == key for name in allowed):
                continue
            genotypes = ratios["genotypes"]
            hint = ""
            if any(_key(r) == key for name, r in ratios.items() if name.startswith("trait:")):
                hint = " (each trait alone gives that: say it is one trait's ratio)"
            from .punnett import ratio_text
            out.append(Claim(q, f"'{said}' does not follow from this cross: its phenotypes are {ratio_text(pheno)} and its genotypes "
                                f"{ratio_text(genotypes)}{hint}; say the ratio the cross gives, or change the cross"))
        if gametes:
            continue
        shares = [x for x in shares_in(s) if not x.bound]
        if not shares or (_GROUP_RE.search(s) is None and _CHANCE_RE.search(s) is None):
            continue
        terms = vocab.terms(s)
        group_sex = None
        for k, said in enumerate(shares):
            stop = shares[k + 1].start if k + 1 < len(shares) else len(s)
            segment = [t for t in terms if said.end <= t.start < stop]
            if not segment and k == 0:
                segment = [t for t in terms if t.end <= said.start]
            if not segment:
                continue
            wanted: dict[int, str] = {}
            carrier = any(t.trait < 0 for t in segment)
            clash = False
            for t in segment:
                if t.trait >= 0:
                    if wanted.get(t.trait, t.phenotype) != t.phenotype:
                        clash = True
                    wanted[t.trait] = t.phenotype
            if clash or (carrier and wanted):
                continue
            g = _GROUP_AFTER.match(s, said.end)
            joint = False
            if g is not None and _sex_of(g.group(1)) is not None:
                sex = _sex_of(g.group(1))                   # "half the sons": among the sons
            elif g is not None:
                sex = _sex_of(s[g.end():stop])              # "a quarter of the children are affected sons": both at once
                joint = sex is not None
            else:
                sex = group_sex or _sex_of(s)               # "each son has a 50 % chance", or the group said before
            group_sex = None if joint else sex
            actual = _class_share(plan, wanted, carrier, sex, joint)
            if actual is None or said.matches(actual, tolerance):
                continue
            who = {"male": "sons (males)", "female": "daughters (females)"}.get(sex or "", "offspring") if plan.system.sex_chromosomes \
                and not joint else "offspring"
            if joint and plan.system.sex_chromosomes:
                wanted = {**wanted, -2: f"{'male' if sex == 'male' else 'female'}"}
            what = "carriers (heterozygous)" if carrier else ", ".join(wanted.values())
            out.append(Claim(q, f"'{said.text}': in this cross {share_text(actual)} of the {who} are {what}, not {share_text(said.value)}: "
                                f"say what the cross gives, or change the cross"))
    return out


# ----- pedigrees -----------------------------------------------------------------------------------------

_SKIP_GEN = re.compile(r"\bskip(?:s|ped|ping)?\s+(?:a\s+|one\s+|the\s+next\s+|some\s+)?generations?\b", re.IGNORECASE)
_DOMINANT = re.compile(r"\bdominant\b|\bAD\b", re.IGNORECASE)
_PENETRANCE = re.compile(r"\b(?:penetran\w*|non-?penetrant|incomplete|recessive|carriers?|new\s+mutation|de\s+novo|germline\s+mosaic\w*)\b",
                         re.IGNORECASE)
_X_LINKED = re.compile(r"\b(?:x-linked|x\s+linked|sex-linked|on\s+the\s+x(?:\s+chromosome)?)\b|\bX[RD]\b", re.IGNORECASE)
_NOT_X = re.compile(r"\b(?:y-linked|y\s+chromosome|holandric|autosom\w*|mitochondri\w*|rules?\s+out|ruled\s+out|exclud\w*|impossible)\b|\bY\b",
                    re.IGNORECASE)
_FATHER_SON = re.compile(r"\bfathers?\b[^.;]*?\b(?:pass\w*|transmit\w*|gives?|gave|hand\w*|inherit\w*)\b[^.;]*?\bsons?\b"
                         r"|\bsons?\b[^.;]*?\binherit\w*\b[^.;]*?\bfrom\s+(?:his|their|the|a)\s+(?:affected\s+)?fathers?\b"
                         r"|\bmale[- ]to[- ]male\s+transmission\b|\bfather[- ]to[- ]son\b", re.IGNORECASE)


def pedigree_text_claims(text: str, mode: str | None = None, penetrance: Fraction | None = None) -> list[Claim]:
    """Mode-of-inheritance statements against the textbook: a dominant trait that skips a
    generation without reduced penetrance being said (or set: ``penetrance`` below 1), and
    father-to-son transmission of an X-linked trait (said X-linked, or ``mode`` XR / XD)."""
    out: list[Claim] = []
    for s in _statements(text):
        q = _quote(s)
        if _SKIP_GEN.search(s) and _DOMINANT.search(s) and _PENETRANCE.search(s) is None and not (penetrance is not None and penetrance < 1):
            out.append(Claim(q, "a dominant trait at full penetrance does not skip a generation: every affected person has an affected "
                                "parent; a skipped generation needs reduced penetrance (say so, and set penetrance:) or a recessive mode"))
        x_context = _X_LINKED.search(s) is not None or (mode in ("XR", "XD") and _NOT_X.search(s) is None)
        if x_context and _NOT_X.search(s) is None and _FATHER_SON.search(s):
            out.append(Claim(q, "an X-linked allele never passes from father to son: a father gives his sons his Y and his daughters "
                                "his X (male-to-male transmission rules X-linked inheritance out)"))
    return out


_PERSON = re.compile(r"\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X)-\d{1,2}\b")
_SIBLING = re.compile(r"\b(?:sib\w*|sisters?|brothers?)\b", re.IGNORECASE)
_CHILD = re.compile(r"\b(?:child|children|baby|babies|pregnancy|fetus|foetus|offspring|sons?|daughters?|boys?|girls?|next\s+one)\b",
                    re.IGNORECASE)
_CONDITIONAL = re.compile(r"\b(?:if|given|assuming|when\s+both|provided)\b", re.IGNORECASE)


def _diploid(mode: str, state: tuple[str, int]) -> bool:
    return mode in ("AD", "AR") or (mode in ("XD", "XR") and state[0] == "f")


def pedigree_values(plan: Any) -> tuple[dict[str, Fraction], Any] | None:
    """Each person's (label → carrier probability, unaffected heterozygotes only where a
    heterozygote is a carrier) and the proposed child's :class:`Risk`, under the plan's mode."""
    inf = plan.inference
    if inf is None:
        return None
    carriers: dict[str, Fraction] = {}
    for pid, post in inf.posterior.items():
        person = plan.ped.people[pid]
        if person.affected:
            continue
        share = sum((p for st, p in post.items() if _diploid(inf.mode, st) and st[1] == 1), Fraction(0))
        carriers[plan.label(pid)] = share
    return carriers, inf.risk


def pedigree_claims(text: str, plan: Any) -> list[Claim]:
    """Probabilities in a pedigree scene's narration against the chart's computed values: a named
    person's (``II-3``) or an unaffected sibling's carrier probability, and the proposed child's
    risk (per sex when a son or a daughter is said)."""
    values = pedigree_values(plan)
    if values is None:
        return []
    carriers, risk = values
    out: list[Claim] = []
    for s in _statements(text):
        shares = [x for x in shares_in(s) if not x.bound]
        if not shares or _CONDITIONAL.search(s):
            continue
        q = _quote(s)
        said = shares[0]
        if _CARRIER_RE.search(s):
            people = [p for p in _PERSON.findall(s) if p in carriers]
            if len(people) == 1:
                actual = carriers[people[0]]
                if not said.matches(actual):
                    out.append(Claim(q, f"'{said.text}': in this chart {people[0]} is a carrier with probability {share_text(actual)} "
                                        f"(under {plan.mode}), not {share_text(said.value)}"))
            elif not people and _SIBLING.search(s) and re.search(r"\bunaffected\b|\bhealthy\b", s, re.IGNORECASE):
                if carriers and not any(said.matches(v) for v in carriers.values()):
                    found = sorted({share_text(v) for v in carriers.values() if v})
                    out.append(Claim(q, f"'{said.text}': no unaffected person in this chart has that carrier probability (under {plan.mode}: "
                                        f"{', '.join(found) or 'none'})"))
            continue
        if risk is None or _CHANCE_RE.search(s) is None or _CHILD.search(s) is None:
            continue
        sex = _sex_of(s)
        key = {"male": "son", "female": "daughter"}.get(sex or "")
        actual = risk.by_sex.get(key, risk.affected) if key else risk.affected
        if not said.matches(actual):
            whom = f"a {key}" if key and key in risk.by_sex else "the proposed child"
            out.append(Claim(q, f"'{said.text}': the chart gives {whom} a risk of {share_text(actual)} (under {plan.mode}), not "
                                f"{share_text(said.value)}"))
    return out


# ----- linkage --------------------------------------------------------------------------------------------

_CM = re.compile(rf"(?P<n>\b{NUM})\s*(?:cM\b|centi-?morgans?\b|map\s+units?\b|m\.u\.)", re.IGNORECASE)
_RF_WORDS = re.compile(r"\b(?:recombination\s+(?:frequency|frequencies|fraction|rate)|RF|recombinants?|recombinant\s+(?:offspring|progeny|gametes)|"
                       r"crossover\s+(?:frequency|rate))\b", re.IGNORECASE)
_UNLINKED = re.compile(r"\bunlinked\b|\bassort\w*\s+independently\b|\bindependent(?:ly)?\s+assort\w*|\bon\s+different\s+chromosomes\b",
                       re.IGNORECASE)
_LINKED = re.compile(r"(?<![-\w])(?<!x )(?<!y )linked\b|\blinkage\b", re.IGNORECASE)


@dataclass(frozen=True)
class PairData:
    """Two loci of a scene: the map distance (cM) and the recombination frequencies that are right
    for them (the interval's, or a three-point cross's direct count of the outer pair)."""

    cm: float
    rf: tuple[float, ...]
    linked: bool = True


def mentions(sentence: str, symbols: Iterable[str]) -> list[str]:
    """The locus symbols a sentence names (case as written; a one-letter capital only beside
    *locus*, *gene*, *and* or a dash, so the article "A" is not a locus)."""
    found: dict[str, int] = {}
    for sym in sorted(set(symbols), key=len, reverse=True):
        for m in re.finditer(rf"(?<![\w^+]){re.escape(sym)}(?![\w+^])", sentence):
            if len(sym) == 1 and sym.isupper():
                after, before = sentence[m.end():m.end() + 10], sentence[max(0, m.start() - 8):m.start()]
                if not (re.match(r"\s*(?:and\b|,|locus|loci|gene|[-–])", after) or re.search(r"(?:genes?|loci|locus|and|[-–])\s*$", before)):
                    continue
            found.setdefault(sym, m.start())
            break
    return sorted(found, key=found.__getitem__)


def linkage_claims(text: str, pairs: Mapping[frozenset[str], PairData], symbols: Sequence[str], tolerance: float = 0.05) -> list[Claim]:
    """Map distances, recombination frequencies and (un)linked claims in ``text`` against the
    scene's loci (``pairs``: every two loci of the scene; ``symbols`` how they are written), and
    in any scene a recombination frequency said to be above 50 %."""
    out: list[Claim] = []
    linked_pairs = {k: v for k, v in pairs.items() if v.linked}
    for s in _statements(text):
        q = _quote(s)
        named = mentions(s, symbols) if symbols else []
        pair = pairs.get(frozenset(named)) if len(named) == 2 else None
        rf_said = [x for x in shares_in(s) if _RF_WORDS.search(s) and not _CM.search(s[x.start:x.end + 12])]
        for said in rf_said:
            if said.value > Fraction(1, 2) and not said.bound:
                out.append(Claim(q, f"'{said.text}': a recombination frequency cannot exceed 50 %: loci far apart assort independently "
                                    f"(50 % recombinants); map distances over 50 cM are sums of shorter intervals"))
        if not pairs:
            continue
        for m in _CM.finditer(s):
            value = number(m.group("n"))
            if value is None or _BOUND.search(s[max(0, m.start() - 24):m.start()]):
                continue
            approx = _APPROX.search(s[max(0, m.start() - 24):m.start()]) is not None
            slack = _resolution(m.group("n"), 1.0) + (tolerance * value if approx else 0.0) + 1e-9
            candidates = [pair] if pair is not None else list(linked_pairs.values())
            options = [c.cm for c in candidates if c is not None and c.linked] + \
                      [r * 100 for c in candidates if c is not None for r in c.rf]
            if options and not any(abs(value - o) <= slack for o in options):
                where = f"{named[0]}–{named[1]} is {pair.cm:.1f} cM" if pair is not None else \
                    "the scene's loci are " + ", ".join(f"{'–'.join(sorted(k))} {v.cm:.1f} cM" for k, v in linked_pairs.items())
                out.append(Claim(q, f"'{m.group(0)}': {where} in this scene, not {value:g} cM"))
        for said in rf_said:
            if said.value > Fraction(1, 2) or said.bound:
                continue
            candidates = [pair] if pair is not None else list(linked_pairs.values())
            options = [r for c in candidates if c is not None for r in c.rf]
            if options and not any(said.matches(r, tolerance) for r in options):
                where = f"{named[0]}–{named[1]}: RF {', '.join(f'{r * 100:.3g} %' for r in pair.rf)}" if pair is not None else \
                    "RF " + ", ".join(f"{'–'.join(sorted(k))} {v.rf[0] * 100:.3g} %" for k, v in linked_pairs.items())
                out.append(Claim(q, f"'{said.text}': the scene's loci give {where}, not {share_text(said.value)}"))
        if pair is not None and _UNLINKED.search(s) and pair.linked and pair.rf and min(pair.rf) < 0.4:
            out.append(Claim(q, f"{named[0]} and {named[1]} are linked in this scene ({pair.cm:.1f} cM, RF {min(pair.rf) * 100:.3g} %): "
                                f"unlinked loci give 50 % recombinants"))
        elif pair is not None and not pair.linked and _LINKED.search(s) and _UNLINKED.search(s) is None and _X_LINKED.search(s) is None:
            out.append(Claim(q, f"{named[0]} and {named[1]} assort independently in this scene (50 % recombinants): give them a linkage "
                                f"group (linkage:) if they are linked"))
    return out


# ----- Hardy–Weinberg -------------------------------------------------------------------------------------

_Q_SAID = re.compile(rf"(?:\bq\b\s*(?:=|is|equals|of|,)?\s*|\bfrequency\s+of\s+(?:the\s+)?(?:recessive|disease|mutant|rare|a|q)\s+alleles?\s*"
                     rf",?\s*(?:=|is|of)?\s*(?:about\s+|approximately\s+|around\s+|roughly\s+)?|\ballele\s+frequency\s*(?:=|is|of|,)?\s*"
                     rf"(?:about\s+|approximately\s+|around\s+|roughly\s+)?)(?P<v>(?:{NUM})(?:\s*/\s*{NUM}|\s+in\s+{NUM})?|0\.\d+)", re.IGNORECASE)
_CARRIER_FREQ = re.compile(r"\b(?:carrier\s+(?:frequency|rate)|carriers?|heterozygotes?|heterozygous|2pq)\b", re.IGNORECASE)
_INCIDENCE = re.compile(r"\b(?:incidence|prevalence|affected|homozygous\s+recessive|q\s*(?:2|squared)|births?|newborns?|babies)\b", re.IGNORECASE)
_POPULATION = re.compile(r"\b(?:population|people|persons|individuals|newborns?|births?|europeans?|frequency|in\s+every|descent|ancestry)\b",
                         re.IGNORECASE)
_QSQ = re.compile(r"\b(?:q\s*\^?\s*2|q²|q\s+squared|p\s*\^?\s*2|p²|p\s+squared)\b", re.IGNORECASE)
_TWO_PQ = re.compile(r"\b(?:2\s*pq|2\s*p\s*q|two\s+p\s+q|2\s*×\s*p\s*×\s*q)\b", re.IGNORECASE)
_HW_SUM = re.compile(r"\bp\s*(?:\^?2|²|\s+squared)\s*\+\s*q\s*(?:\^?2|²|\s+squared)\s*=\s*1\b", re.IGNORECASE)


def _decimal(text: str) -> Fraction | None:
    t = text.strip()
    if re.fullmatch(r"0\.\d+", t):
        return Fraction(t)
    said = shares_in(t)
    if said:
        return said[0].value
    v = number(t)
    return _exact(v) if v is not None and 0 < v < 1 else None


def _population_share(s: str, start: int = 0) -> Said | None:
    """The first share in ``s`` (from ``start``) said as a population frequency: ``1 in 25``,
    ``4 %``, ``1/2500`` (not a probability like 2/3)."""
    for said in shares_in(s[start:]):
        if said.bound:
            continue
        if said.value <= Fraction(1, 5) or _POPULATION.search(s):
            return said
    return None


def hw_claims(text: str, hw: Any = None, tolerance: float = 0.1) -> list[Claim]:
    """Hardy–Weinberg arithmetic in ``text``: the formulas mixed up (carriers called q² or p²,
    the incidence called 2pq, p² + q² = 1), and the numbers said together in one beat that do not
    agree — q against the incidence (q² = incidence), the carrier frequency against q (2pq, or ≈
    2q for a rare allele); with ``hw`` (a population scene's :class:`HardyWeinberg`) each against
    the scene's computed q, incidence and 2pq."""
    out: list[Claim] = []
    q_said: tuple[str, Fraction, str] | None = None
    inc_said: tuple[str, Fraction, str] | None = None
    car_said: tuple[str, Fraction, str] | None = None
    for s in _statements(text):
        quote = _quote(s)
        if _HW_SUM.search(s) and not _TWO_PQ.search(s):
            out.append(Claim(quote, "the Hardy–Weinberg genotype frequencies are p² + 2pq + q² = 1 (the heterozygotes 2pq are part of it)"))
        if _CARRIER_RE.search(s) and _QSQ.search(s) and not _TWO_PQ.search(s) and \
                not re.search(r"\b(?:homozyg\w*|incidence|prevalence|affected)\b", s, re.IGNORECASE):
            out.append(Claim(quote, "heterozygotes (carriers) are 2pq; q² is the frequency of the affected homozygotes, p² of the "
                                    "unaffected homozygotes"))
        if _TWO_PQ.search(s) and re.search(r"\b(?:incidence|affected|homozygous\s+recessive)\b", s, re.IGNORECASE) and \
                not _CARRIER_RE.search(s) and not _QSQ.search(s):
            out.append(Claim(quote, "2pq is the heterozygote (carrier) frequency; the affected (homozygous recessive) frequency is q²"))
        m = _Q_SAID.search(s)
        q_here = False
        if m:
            v = _decimal(m.group("v"))
            if v is not None and 0 < v < 1:
                q_said = (m.group(0).strip(), v, quote)
                q_here = True
        for match in _CARRIER_FREQ.finditer(s):
            said = _population_share(s, match.end())
            if said is not None:
                car_said = (said.text, said.value, quote)
                break
        if _INCIDENCE.search(s) and not _CARRIER_FREQ.search(s):
            said = _population_share(s)
            if q_here and said is not None and q_said is not None and said.value == q_said[1]:
                said = None                   # "the incidence is q squared, so q is 1 in 50": the number is q's
            if said is not None and said.value < Fraction(1, 5):
                inc_said = (said.text, said.value, quote)

    def close(a: float, b: float) -> bool:
        return b > 0 and abs(a - b) <= tolerance * b

    q_value = float(q_said[1]) if q_said else (float(hw.q) if hw is not None else None)
    if q_said and inc_said and not close(float(q_said[1]) ** 2, float(inc_said[1])):
        out.append(Claim(inc_said[2], f"q = √(incidence): an incidence of {share_text(inc_said[1])} gives q ≈ {math.sqrt(float(inc_said[1])):.3g}, "
                                      f"not {q_said[0]} (q² = {float(q_said[1]) ** 2:.3g})"))
    elif inc_said and not q_said and q_value is None:
        q_value = math.sqrt(float(inc_said[1]))
    if q_value is None and inc_said:
        q_value = math.sqrt(float(inc_said[1]))
    if car_said and q_value is not None and 0 < q_value < 1:
        two_pq = 2 * q_value * (1 - q_value)
        if not (close(float(car_said[1]), two_pq) or close(float(car_said[1]), 2 * q_value)):
            out.append(Claim(car_said[2], f"'{car_said[0]}': with q ≈ {q_value:.3g} the carriers are 2pq ≈ {two_pq:.3g} (1 in {1 / two_pq:.3g}; "
                                          f"≈ 2q for a rare allele), not {share_text(car_said[1])}"))
    if hw is not None:
        q = float(hw.q)
        if q_said and not close(float(q_said[1]), q) and not close(float(q_said[1]), float(hw.p)):
            out.append(Claim(q_said[2], f"'{q_said[0]}': the scene's q is {q:.4g}"))
        incidence = float(hw.incidence) if getattr(hw, "incidence", None) is not None else float(hw.expected[2])
        if inc_said and not close(float(inc_said[1]), incidence):
            out.append(Claim(inc_said[2], f"'{inc_said[0]}': the scene's incidence (q²) is {share_text(incidence)}"))
    return _unique(out)


def _unique(claims: list[Claim]) -> list[Claim]:
    seen: set[tuple[str, str]] = set()
    out = []
    for c in claims:
        if (c.quote, c.message) not in seen:
            seen.add((c.quote, c.message))
            out.append(c)
    return out


# ----- CRISPR -------------------------------------------------------------------------------------------

#: The PAMs of the nucleases narration names (5′→3′ on the non-target strand): SpCas9 NGG 3′ of the
#: protospacer, SaCas9 NNGRRT, Cas12a (Cpf1) TTTV 5′ of it.
PAMS: dict[str, tuple[str, ...]] = {"SpCas9": ("NGG",), "SaCas9": ("NNGRRT", "NNGRR"), "Cas12a": ("TTTV", "TTTN")}
_ENZYME = re.compile(r"\b(?P<sa>SaCas9|S\.?\s*aureus\s+Cas9)\b|\b(?P<cas12>(?:As|Lb|Fn)?Cas12a|Cpf1)\b|\b(?P<sp>SpCas9|Cas9)\b", re.IGNORECASE)
_PAM_WORD = re.compile(r"\bPAMs?\b|protospacer[- ]adjacent\s+motifs?", re.IGNORECASE)
_PAM_TOKEN = re.compile(r"(?<![\w-])((?:[ACGTNRYV]-){2,7}[ACGTNRYV]|[ACGTNRYV]{3,8})(?![\w-])")
_CUT = re.compile(r"\b(?:cut\w*|cleav\w*|breaks?|snips?|nick\w*)\b", re.IGNORECASE)
_CUT_PLACE = re.compile(rf"(?P<n>\b{NUM})\s*-?\s*(?:bp|base[- ]pairs?|bases?|nucleotides?|nt)\s+(?P<dir>upstream|downstream|5'|3'|before|after|"
                        rf"in\s+front|beyond|away|from)\s*(?:of|from)?\s*(?:the\s+)?(?:NGG\s+)?PAM\b", re.IGNORECASE)
_CUT_WRONG_SIDE = re.compile(r"\b(?:cut\w*|cleav\w*|breaks?)\b[^.;]*?\b(?:downstream\s+of|3'\s+(?:of|to)|after|inside|within|in)\s+the\s+"
                             r"(?:NGG\s+)?PAM\b", re.IGNORECASE)
_STICKY = re.compile(r"\b(?:sticky|staggered|cohesive)\b|\boverhangs?\b|\boverhanging\b", re.IGNORECASE)
_STICKY_OK = re.compile(r"\b(?:Cas12a|Cpf1|nickases?|paired\s+nick\w*|restriction|EcoRI|BamHI|HindIII|Cas9n|D10A)\b", re.IGNORECASE)
_PAM_BEFORE = re.compile(r"\bPAM\b[^.;]*?\b(?:upstream\s+of|5'\s+(?:of|to)|before|in\s+front\s+of)\s+the\s+(?:protospacer|spacer|target\s+sequence|"
                         r"guide(?:\s+sequence)?)\b", re.IGNORECASE)
_PAM_TARGET_STRAND = re.compile(r"\bPAM\b[^.;]*?\b(?:on|in)\s+the\s+(?<!non-)(?<!non )target\s+strand\b", re.IGNORECASE)
_SPACER_LEN = re.compile(rf"(?P<n>\b{NUM})[- ](?:nt|nucleotides?|bases?|base|bp)(?:[- ]long)?\s+(?:spacer|guide|protospacer|guide\s+sequence|"
                         rf"targeting\s+sequence)\b|\b(?:spacer|guide\s+sequence|protospacer)\s+(?:of|is)\s+(?P<m>{NUM})\s+(?:nt|nucleotides?|bases?)\b",
                         re.IGNORECASE)
SPACER_RANGES = {"SpCas9": (17, 24), "SaCas9": (21, 24), "Cas12a": (18, 25)}
_IUPAC = {"A": "A", "C": "C", "G": "G", "T": "T", "R": "AG", "Y": "CT", "V": "ACG", "N": "ACGT"}


def _pam_fits(token: str, pams: Sequence[str]) -> bool:
    """Whether a PAM as written (``NGG``, ``AGG``, ``N-G-G``) is one of ``pams`` or an instance of it."""
    t = token.replace("-", "").upper()
    for pam in pams:
        if t == pam:
            return True
        if len(t) == len(pam) and all(c in "ACGT" and c in _IUPAC.get(p, p) for c, p in zip(t, pam)):
            return True
    return False


def crispr_claims(text: str, cas: str | None = None) -> list[Claim]:
    """CRISPR statements against the enzymes' facts: a PAM written for the wrong nuclease (SpCas9
    NGG, SaCas9 NNGRRT, Cas12a TTTV), a cut placed downstream of (3′ of, inside) the PAM or not 3 bp
    upstream of it, sticky or staggered ends for Cas9 (its break is blunt), the PAM before the
    protospacer or on the target strand, a spacer length the enzyme does not use. ``cas``: the
    scene's nuclease (a ``crispr`` scene), else the one the sentence names."""
    out: list[Claim] = []
    for s in _statements(text):
        q = _quote(s)
        m = _ENZYME.search(s)
        enzyme = ("SaCas9" if m.group("sa") else "Cas12a" if m.group("cas12") else "SpCas9") if m else cas
        if enzyme is None:
            continue
        if _PAM_WORD.search(s):
            for token in _PAM_TOKEN.findall(s):
                t = token.replace("-", "").upper()
                if t in ("RNA", "DNA", "CAN", "AND", "ACT", "TAG", "TGA", "TAA") or not re.search(r"GG|N|TTT|GR", t):
                    continue
                if not _pam_fits(t, PAMS[enzyme]):
                    owner = next((name for name, pams in PAMS.items() if _pam_fits(t, pams)), None)
                    hint = f" ({t} is {owner}'s)" if owner else ""
                    out.append(Claim(q, f"'{token}': the {enzyme} PAM is 5′-{PAMS[enzyme][0]}-3′{hint}"))
        if enzyme == "Cas12a":
            continue
        cm = _CUT_PLACE.search(s)
        if cm and _CUT.search(s):
            n = number(cm.group("n"))
            direction = cm.group("dir").lower()
            if direction in ("downstream", "3'", "after", "beyond"):
                out.append(Claim(q, f"{enzyme} cuts both strands 3 bp upstream (5′) of the PAM, inside the protospacer, not "
                                    f"{direction} of it"))
            elif n is not None and n != 3:
                out.append(Claim(q, f"{enzyme} cuts 3 bp upstream (5′) of the PAM, not {cm.group('n')}"))
        elif _CUT_WRONG_SIDE.search(s):
            out.append(Claim(q, f"{enzyme} cuts 3 bp upstream (5′) of the PAM, inside the protospacer (between its 17th and 18th "
                                f"nucleotides), not downstream of or inside the PAM"))
        if _STICKY.search(s) and (_CUT.search(s) or re.search(r"\bends?\b", s, re.IGNORECASE)) and _STICKY_OK.search(s) is None:
            out.append(Claim(q, f"{enzyme} leaves blunt ends: its HNH and RuvC domains cut the two strands at the same place (staggered "
                                f"ends are Cas12a's)"))
        if _PAM_BEFORE.search(s):
            out.append(Claim(q, f"the {enzyme} PAM lies right after the protospacer's 3′ end (on the non-target strand), not before it"))
        if _PAM_TARGET_STRAND.search(s):
            out.append(Claim(q, "the PAM is on the non-target strand (the one the spacer repeats); the spacer pairs with the target strand"))
        for sm in _SPACER_LEN.finditer(s):
            n = number(sm.group("n") or sm.group("m"))
            lo, hi = SPACER_RANGES[enzyme]
            if n is not None and not lo <= n <= hi:
                out.append(Claim(q, f"a {enzyme} spacer is {'20' if enzyme == 'SpCas9' else '21–23'} nt ({lo}–{hi} in use), not {n:g}"))
    return out


# ----- karyotypes ---------------------------------------------------------------------------------------

_ISCN = re.compile(r"(?<![\w,])(\d{2},[XYxy]{1,5}(?:,[A-Za-z0-9+\-();.?]+)*)")
_MALE_WORDS = re.compile(r"\b(?:male|males|man|men|boys?|sons?|fathers?|he|his|him)\b", re.IGNORECASE)
_FEMALE_WORDS = re.compile(r"\b(?:female|females|woman|women|girls?|daughters?|mothers?|she|her|hers)\b", re.IGNORECASE)
_SRY = re.compile(r"\bSRY\b|\bsex\s+reversal\b", re.IGNORECASE)
_COMPARE = re.compile(r"\b(?:like|such\s+as|for\s+example|e\.g\.|other|another|examples?)\b", re.IGNORECASE)


def iscn_order_problem(kt: Any) -> str | None:
    """The reordered notation when a karyotype's changes are not in ISCN order (after the sex
    chromosomes, the changes by chromosome — sex chromosomes first, then 1 to 22 —, a numerical
    change before a structural one of the same chromosome), else ``None``."""
    from .karyotype import NAMES

    order = ["X", "Y"] + [n for n in NAMES if n not in ("X", "Y")]

    def key(a: Any) -> tuple[int, int]:
        return order.index(a.chroms[0]) if a.chroms and a.chroms[0] in order else 99, 0 if a.kind in ("gain", "loss") else 1

    keys = [key(a) for a in kt.abnormalities]
    if keys == sorted(keys):
        return None
    ordered = sorted(kt.abnormalities, key=key)
    return ",".join([str(kt.count), kt.sex] + [a.text for a in ordered])


def _conditions(kt: Any) -> set[str]:
    """The condition keys a karyotype has: ``trisomy:N``, ``monosomy:N``, ``down``, ``edwards``,
    ``patau``, ``turner``, ``klinefelter``, ``triple_x``, ``xyy``, ``cri_du_chat``, ``philadelphia``."""
    out: set[str] = set()
    for a in kt.abnormalities:
        if a.kind == "gain":
            out.add(f"trisomy:{a.chroms[0]}")
        if a.kind == "loss":
            out.add(f"monosomy:{a.chroms[0]}")
        if a.kind == "del" and a.chroms == ("5",) and a.bands and a.bands[0].arm == "p":
            out.add("cri_du_chat")
        if a.kind == "t" and a.chroms == ("9", "22"):
            out.add("philadelphia")
    robs21 = [a for a in kt.abnormalities if a.kind == "rob" and "21" in a.chroms]
    if robs21 and len(kt.copies["21"]) + len(robs21) >= 3:
        out.add("trisomy:21")
    for c, name in (("21", "down"), ("18", "edwards"), ("13", "patau")):
        if f"trisomy:{c}" in out:
            out.add(name)
    sex = kt.sex
    if sex == "X":
        out |= {"turner", "monosomy:X"}
    if "Y" in sex and sex.count("X") >= 2:
        out.add("klinefelter")
    if sex == "XXX":
        out |= {"triple_x", "trisomy:X"}
    if sex == "XYY":
        out.add("xyy")
    return out


_CONDITION_SAID = re.compile(rf"\b(?:(?P<tri>trisomy|monosomy)\s+(?P<n>X|{NUM})\b|(?P<name>Down|Edwards|Patau|Turner|Klinefelter|cri[- ]du[- ]chat)"
                             rf"(?:'s)?\s+syndrome|(?P<ph>Philadelphia)\s+chromosome|(?P<tx>triple\s+X))", re.IGNORECASE)
CONDITION_NAMES = {"down": "Down syndrome (trisomy 21)", "edwards": "Edwards syndrome (trisomy 18)", "patau": "Patau syndrome (trisomy 13)",
                   "turner": "Turner syndrome (45,X)", "klinefelter": "Klinefelter syndrome (47,XXY)", "triple_x": "triple X (47,XXX)",
                   "cri_du_chat": "cri-du-chat syndrome (a 5p deletion)", "philadelphia": "the Philadelphia chromosome (t(9;22))"}


def _condition_key(m: re.Match[str]) -> tuple[str, str]:
    if m.group("tri"):
        n = m.group("n")
        v = number(n) if n.upper() != "X" else None
        chrom = "X" if n.upper() == "X" else (str(int(v)) if v is not None else n)
        return f"{m.group('tri').lower()}:{chrom}", f"{m.group('tri').lower()} {chrom}"
    if m.group("ph"):
        return "philadelphia", "the Philadelphia chromosome"
    if m.group("tx"):
        return "triple_x", "triple X"
    name = m.group("name").lower().replace(" ", "-")
    key = {"cri-du-chat": "cri_du_chat"}.get(name, name)
    return key, f"{m.group('name')} syndrome"


def karyotype_claims(text: str, scene_karyotype: Any = None, on_screen: bool = False) -> list[Claim]:
    """Karyotype notation and statements: an ISCN karyotype written in the text that does not parse
    (the reason and fix), one whose changes are out of ISCN order, a karyotype or a sex-chromosome
    syndrome given the wrong sex (45,X or Turner syndrome male; 47,XXY or Klinefelter female), and
    in a ``karyotype`` scene (``scene_karyotype``) a condition the scene's karyotype does not have
    ("trisomy 21" for 47,XY,+18)."""
    from .karyotype import parse_karyotype

    out: list[Claim] = []
    parts = [normal_text(text)] if on_screen else list(_statements(text))
    for s in parts:
        q = _quote(s)
        tokens = []
        for m in _ISCN.finditer(s):
            token = _strip_token(m.group(1))
            try:
                kt = parse_karyotype(token, "karyotype")
            except VidgenError as error:
                out.append(Claim(q, _token_message(token, error, "karyotype: ")))
                continue
            tokens.append(kt)
            fixed = iscn_order_problem(kt)
            if fixed:
                out.append(Claim(q, f"'{token}': ISCN lists the changes by chromosome (sex chromosomes, then 1–22; numerical before "
                                    f"structural): {fixed}"))
        if on_screen or _SRY.search(s):
            continue
        male, female = _MALE_WORDS.search(s) is not None, _FEMALE_WORDS.search(s) is not None
        for kt in tokens:
            if kt.is_female and male and not female:
                out.append(Claim(q, f"{kt.text} has no Y chromosome: female (no SRY, so ovaries develop)"))
            elif not kt.is_female and female and not male:
                out.append(Claim(q, f"{kt.text} has a Y chromosome: male (SRY makes the gonads testes)"))
        if not tokens:
            if re.search(r"\bTurner\b", s) and male and not female:
                out.append(Claim(q, "Turner syndrome (45,X) is female: there is no Y chromosome"))
            if re.search(r"\bKlinefelter\b", s) and female and not male:
                out.append(Claim(q, "Klinefelter syndrome (47,XXY) is male: the Y chromosome's SRY makes testes"))
        reference = tokens[0] if len(tokens) == 1 else (scene_karyotype if not tokens else None)
        if reference is None or (not tokens and _COMPARE.search(s)):
            continue
        have = _conditions(reference)
        claimed = [_condition_key(m) for m in _CONDITION_SAID.finditer(s)]
        if any(k in have for k, _ in claimed):
            continue
        for key, said in claimed[:1]:
            names = [CONDITION_NAMES[k] for k in sorted(have) if k in CONDITION_NAMES] or \
                    [k.replace(":", " ") for k in sorted(have)] or ["no aneuploidy or named syndrome"]
            out.append(Claim(q, f"'{said}': the karyotype {reference.text} shows {', '.join(names)}; say what it shows, or change "
                                f"karyotype:"))
    return _unique(out)


# ----- HGVS ---------------------------------------------------------------------------------------------

_C_TOKEN = re.compile(r"(?<![\w.])c\.(?:[0-9A-Z*\-][^\s,;]*)")
_P_TOKEN = re.compile(r"(?<![\w.])p\.(?:\([^\s,;]*?\)|[A-Z?=*][^\s,;]*)")
_LEGACY_OK = re.compile(r"\b(?:legacy|traditional(?:ly)?|historic\w*|old(?:er)?\s+name|formerly|known\s+as|also\s+called|commonly\s+called|"
                        r"often\s+called|called|shorthand|informal\w*|nickname\w*|classic\s+name|mature\s+protein|without\s+the\s+(?:initiator\s+)?"
                        r"methionine)\b", re.IGNORECASE)
_DELTA_F508 = re.compile(r"(?:Δ|\bdelta\s?)F\s?508\b|\bdeltaF508\b", re.IGNORECASE)
_ONE_LETTER = re.compile(r"(?<![\w.(])([ACDEFGHIKLMNPQRSTVWY])(\d{1,4})([ACDEFGHIKLMNPQRSTVWYX])(?![\w)])")
_THREE_TOKEN = re.compile(r"(?<![\w.(])([A-Z][a-z]{2})(\d{1,4})([A-Z][a-z]{2}|Ter|\*)(?![\w)])")
_VARIANT_CONTEXT = re.compile(r"\b(?:mutations?|variants?|alleles?|substitutions?|missense|nonsense|codons?|residues?|amino\s+acids?|"
                              r"HGVS|change[sd]?|sickle|cystic|fibrosis|CFTR|HBB|globin)\b", re.IGNORECASE)


def _strip_token(token: str) -> str:
    t = token.rstrip(".,:;")
    while t.endswith(")") and t.count(")") > t.count("("):
        t = t[:-1]
    return t


def _three(code: str) -> str:
    from .hgvs import aa3

    return "*" if code in ("X", "*") else aa3(code)


def _token_message(token: str, error: VidgenError, prefix: str) -> str:
    """An HGVS error for ``token``, without repeating it when the error already starts with it."""
    message = str(error).removeprefix(prefix)
    return message if message.startswith(f"'{token}'") else f"'{token}': {message}"


def _reference_genes_named(s: str, plan: Any) -> list[Any]:
    """The reference genes a sentence is about: named (HBB, CFTR, GJB2), by their disease or protein
    (sickle cell, haemoglobin, cystic fibrosis), or the mutation scene's."""
    from .reference_genes import REFERENCE_GENES

    return [g for sym, g in REFERENCE_GENES.items() if re.search(rf"\b{sym}\b", s) or (plan is not None and plan.symbol == sym)
            or (sym == "HBB" and re.search(r"\b(?:sickle|haemoglobin|hemoglobin|[βb]eta-?globin)\b", s, re.IGNORECASE))
            or (sym == "CFTR" and re.search(r"\bcystic\s+fibrosis\b", s, re.IGNORECASE))]


def _legacy_numbering(stated: Any, genes: Sequence[Any]) -> tuple[Any, Any] | None:
    """``(gene, known variant)`` whose protein change ``stated`` writes one residue too low (the
    mature protein's numbering, without the initiator Met: HbS as Glu6Val)."""
    from . import hgvs

    for gene in genes:
        for known in gene.variants:
            try:
                computed = hgvs.parse_p(known.p, "p")
            except VidgenError:
                continue
            if computed.start is not None and stated.start == computed.start - 1 and stated.ref == computed.ref and \
                    stated.alt == computed.alt and stated.kind == computed.kind:
                return gene, known
    return None


def hgvs_claims(text: str, plan: Any = None, genetics_scene: bool = False, on_screen: bool = False) -> list[tuple[Claim, str | None]]:
    """HGVS in ``text``: a ``c.`` or ``p.`` description that is not valid HGVS, or (``plan``: a
    ``mutation`` scene's :class:`MutationPlan`) that is not the scene's variant; a protein change
    in the legacy numbering without the initiator Met (``p.Glu6Val``, ``Glu6Val`` for HbS, against
    the scene's variant or the reference genes' textbook variants) unless the sentence says it is a
    legacy name; legacy shorthand (``ΔF508``, ``R553X``) as ``info`` unless called legacy. Returns
    ``(claim, severity)`` (``None``: the rule's)."""
    from . import hgvs

    out: list[tuple[Claim, str | None]] = []
    parts = [normal_text(text)] if on_screen else [s for s in sentences(text) if not s.rstrip().endswith("?")]
    for s in parts:
        q = _quote(s)
        legacy_ok = _LEGACY_OK.search(s) is not None
        genes = _reference_genes_named(s, plan)
        for raw in _C_TOKEN.findall(s):
            token = _strip_token(raw)
            try:
                if plan is None:
                    hgvs.parse_c(token, "c")
                    continue
                cons = hgvs.consequence(plan.cds, token, "c")
            except VidgenError as error:
                out.append((Claim(q, _token_message(token, error, "c: ")), None))
                continue
            if cons.dna.text() not in [v.consequence.dna.text() for v in plan.variants]:
                out.append((Claim(q, f"'{token}' is not the scene's variant ({', '.join(v.c_text for v in plan.variants)})"), None))
        for raw in _P_TOKEN.findall(s):
            token = _strip_token(raw)
            if "(" in token and not token.endswith(")"):
                token += ")"
            try:
                stated = hgvs.parse_p(token, "p")
            except VidgenError as error:
                out.append((Claim(q, _token_message(token, error, "p: ")), None))
                continue
            if plan is None:
                legacy = None if legacy_ok else _legacy_numbering(stated, genes)
                if legacy is not None:
                    gene, known = legacy
                    out.append((Claim(q, f"'{token}' is {gene.symbol}'s legacy numbering (the mature protein, without the initiator "
                                         f"Met): HGVS writes {known.c} {known.p}; say it is the legacy name if you mean the old one"), None))
                continue
            problems: list[str] = []
            for v in plan.variants:
                cons = v.consequence
                try:
                    hgvs.check_stated(stated, cons.protein, token, cons.protein.text(plan.style, plan.stop), cons.wt_protein,
                                      cons_first_codon(plan), "p")
                    problems = []
                    break
                except VidgenError as error:
                    problems.append(str(error).removeprefix("p: "))
            if problems and not ("legacy numbering" in problems[0] and legacy_ok):
                out.append((Claim(q, problems[0].replace("(put it in legacy:)", "(say it is the legacy name if you mean the old one)")),
                            None))
        if not (genetics_scene or (not on_screen and _VARIANT_CONTEXT.search(s))) or legacy_ok:
            continue
        for m in _DELTA_F508.finditer(s):
            out.append((Claim(q, f"'{m.group(0)}' is the legacy name: HGVS writes CFTR c.1521_1523del p.(Phe508del) (say 'legacy "
                                 f"name ΔF508' if you keep it)"), "info"))
        for m in _ONE_LETTER.finditer(s):
            ref, pos, alt = m.groups()
            if ref == alt:
                continue
            out.append((Claim(q, f"'{m.group(0)}' is informal shorthand: HGVS writes p.({_three(ref)}{pos}{_three(alt)}) (say it is the "
                                 f"legacy name if you keep it)"), "info"))
        for m in _THREE_TOKEN.finditer(s):
            ref3, pos, alt3 = m.groups()
            try:
                stated = hgvs.parse_p(f"p.({ref3}{pos}{alt3})", "p")
            except VidgenError:
                continue
            legacy = _legacy_numbering(stated, genes)
            if legacy is not None:
                gene, known = legacy
                out.append((Claim(q, f"'{m.group(0)}' is {gene.symbol}'s legacy numbering (the mature protein, without the initiator "
                                     f"Met): HGVS writes {known.c} {known.p}; say it is the legacy name if you mean the old one"), None))
    return _unique_pairs(out)


def cons_first_codon(plan: Any) -> int:
    """The number of the first whole codon of a mutation plan's window."""
    return plan.cds.codon_number(plan.cds.first + plan.cds.frame_start)


def _unique_pairs(items: list[tuple[Claim, str | None]]) -> list[tuple[Claim, str | None]]:
    seen: set[tuple[str, str]] = set()
    out = []
    for c, sev in items:
        if (c.quote, c.message) not in seen:
            seen.add((c.quote, c.message))
            out.append((c, sev))
    return out


__all__ = [
    "CONDITION_NAMES", "CrossVocabulary", "HYPOTHETICAL", "NUM", "ORDINALS", "PAMS", "PairData", "SPACER_RANGES", "Said", "Term",
    "cons_first_codon", "crispr_claims", "cross_claims", "cross_ratios", "hgvs_claims", "hw_claims", "iscn_order_problem", "karyotype_claims",
    "linkage_claims", "mentions", "number", "pedigree_claims", "pedigree_text_claims", "pedigree_values", "ratios_said", "share_text",
    "shares_in",
]
