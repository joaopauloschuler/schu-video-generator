"""The calculation and plot lint's knowledge (DESIGN.md §97.11): numbers with units as narration
and screen text write them — digits (``29.8 km/s``, ``3.7 × 10⁻¹⁹ J``, ``1/150``, ``25 %``) and
words (``thirty kilometres per second``, ``eleven point two``, ``three point seven times ten to
the minus nineteen joules``, ``one in a hundred and fifty``, ``three halves``) — and how they
compare with a computed value (the written resolution, "about" rounding to one or two
significant figures, a power-of-1000 unit mix-up, significant figures beyond the inputs). Also
the dimension a word names ("a speed of 30 kilometres"), what a fitted parameter is called in
words ("a half-life of eight days", "exponent three halves") and what error bars are said to
mean. Like :mod:`vidgen.cellworld.accuracy` and :mod:`vidgen.genetics.accuracy` (whose sentence
helpers it reuses) every check is narrow: a negation, a question, a hypothetical, a bound
("more than") or a range ("400 to 700 nm") leaves a number alone. No manim."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from vidgen.cellworld.accuracy import Claim, plain
from vidgen.errors import VidgenError
from vidgen.genetics.accuracy import HYPOTHETICAL

from .quantity import decimal_text, round_sig
from .units import DIMENSIONLESS, Dim, Unit, describe_dim, dim, parse_unit

# ----- text -------------------------------------------------------------------------------------------

_CLEAN = str.maketrans({"’": "'", "‘": "'", "–": "-", "−": "-", " ": " ", " ": " "})


def clean(text: str) -> str:
    """``text`` with typographic quotes, en dashes and the minus sign as ASCII (superscripts,
    ``µ``, ``°`` and ``×`` kept: units and powers of ten need them)."""
    return text.translate(_CLEAN).replace("—", " - ")


def statements(text: str) -> list[str]:
    """The plain statements of ``text`` (no negation, contrast, question or hypothetical), split
    at sentence ends and semicolons but not at decimal points."""
    parts = re.split(r"(?<=[.!?;])\s+", clean(str(text)).strip())
    return [p.strip() for p in parts if p.strip() and plain(p) and HYPOTHETICAL.search(p) is None]


def quote(sentence: str, limit: int = 90) -> str:
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


# ----- numbers in words and digits --------------------------------------------------------------------

_ONES = {w: k for k, w in enumerate("zero one two three four five six seven eight nine".split())}
_TEENS = {w: 10 + k for k, w in enumerate("ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * k for k, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if k >= 2}
_SCALES = {"thousand": 10**3, "million": 10**6, "billion": 10**9}
_DIGIT_WORDS = {**_ONES, "oh": 0, "o": 0, "nought": 0}
_NW = "|".join(sorted([*_ONES, *_TEENS, *_TENS, "hundred", *_SCALES], key=len, reverse=True))
_WSEQ = rf"(?:(?:a|an)\s+(?=(?:hundred|thousand|million|billion)\b))?(?:{_NW})(?:(?:-|\s+and\s+|\s+)(?:{_NW})\b)*"
_DW = "|".join(sorted(_DIGIT_WORDS, key=len, reverse=True))
#: Ordinal words as denominators, with the cardinal word they stand for (``fiftieth`` -> fifty).
_ORDINAL_CARDINAL = {
    "half": "two", "third": "three", "quarter": "four", "fourth": "four", "fifth": "five", "sixth": "six", "seventh": "seven", "eighth": "eight",
    "ninth": "nine", "tenth": "ten", "eleventh": "eleven", "twelfth": "twelve", "thirteenth": "thirteen", "fourteenth": "fourteen",
    "fifteenth": "fifteen", "sixteenth": "sixteen", "seventeenth": "seventeen", "eighteenth": "eighteen", "nineteenth": "nineteen",
    "twentieth": "twenty", "thirtieth": "thirty", "fortieth": "forty", "fiftieth": "fifty", "sixtieth": "sixty", "seventieth": "seventy",
    "eightieth": "eighty", "ninetieth": "ninety", "hundredth": "hundred", "thousandth": "thousand", "millionth": "million",
}
_ORD = "|".join(sorted([*_ORDINAL_CARDINAL, "halves"], key=len, reverse=True))
_SCI_WORDS = (rf"(?:,?\s+(?:times|x|×)\s+ten\s+to\s+the(?:\s+power(?:\s+of)?)?\s+(?P<neg>minus\s+|negative\s+)?"
              rf"(?P<wexp>{_WSEQ}|\d+)(?:th|st|nd|rd)?(?:\s+power)?)")
_NUMBER = re.compile(
    rf"(?P<dig>(?<![\w.,/^])-?(?:\d{{1,3}}(?:,\d{{3}})+(?![\d,])|\d+)(?:\.\d+)?|(?<![\w.])\.\d+)"
    rf"(?:\s*[×x*·]\s*10\s*(?:\^|\*\*)?\s*\(?(?P<e1>[-+]?\d+)\)?(?![\d.])|\s*[×x*·]\s*10(?P<e2>[⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)|(?P<e3>[eE][-+]?\d+)(?![\w]))?"
    rf"(?:\s+(?P<dscale>thousand|million|billion)\b)?"
    rf"|(?P<words>\b{_WSEQ}\b)(?P<point>\s+point(?:\s+(?:{_DW})\b)+)?(?:\s+(?P<wscale>thousand|million|billion)\b)?",
    re.IGNORECASE,
)
_SCI_AFTER = re.compile(_SCI_WORDS, re.IGNORECASE)
_SUPER_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_FRACTION_AFTER = re.compile(rf"[\s-]+(?P<den>(?:(?:{_NW})(?:[\s-]+|\s+and\s+))*(?:{_ORD}))s?\b(?!-)", re.IGNORECASE)
_HALF_AFTER = re.compile(r"\s+and\s+a\s+half\b", re.IGNORECASE)
_SCALE_AFTER = re.compile(r"\s+(?P<s>thousand|million|billion)\b", re.IGNORECASE)
_SLASH_AFTER = re.compile(r"\s*/\s*(?P<b>\d+)(?![\d.])")
_APPROX = re.compile(r"(?:\b(?:about|approximately|around|roughly|nearly|near|almost|close\s+to|some|circa|ca\.?|just\s+(?:over|under)|"
                     r"of\s+order|order\s+of)|[≈~∼])\s*$", re.IGNORECASE)
_BOUND = re.compile(r"\b(?:more\s+than|less\s+than|fewer\s+than|over|under|above|below|at\s+least|at\s+most|up\s+to|exceeds?|exceeding|"
                    r"beyond|within|greater\s+than|smaller\s+than|larger\s+than|lower\s+than|higher\s+than)\s*$|[<>≤≥]\s*$", re.IGNORECASE)
_NEGATIVE = re.compile(r"\b(?:minus|negative)\s+$", re.IGNORECASE)
_RANGE_GAP = re.compile(r"^\s*(?:to|-|–|or|and)\s*$", re.IGNORECASE)
_RANGE_START = re.compile(r"\b(?:between|from)\s+(?:about\s+|roughly\s+|around\s+)?$", re.IGNORECASE)
_SHARE_GAP = re.compile(r"(?:\s+[a-z]+){0,2}?\s+(?:in|out\s+of)\s+(?:every\s+)?", re.IGNORECASE)


def is_number_word(word: str) -> bool:
    """Whether ``word`` is part of a number in words (``two``, ``hundred``, ``thirds``)."""
    w = word.lower()
    return w in _ONES or w in _TEENS or w in _TENS or w in _SCALES or w in ("hundred", "halves", "point") or w in _ORDINAL_CARDINAL or \
        (w.endswith("s") and w[:-1] in _ORDINAL_CARDINAL)


def words_value(text: str) -> int | None:
    """A whole number in English words (``three hundred sixty-five``, ``a hundred and fifty``,
    ``two thousand five hundred``), or ``None`` when the words are not one number (``two
    three``, ``two and three``)."""
    tokens = [t for t in re.split(r"[\s-]+", text.strip().lower()) if t]
    if tokens and tokens[0] in ("a", "an"):
        tokens[0] = "one"
    total = group = 0
    last = None
    for t in tokens:
        if t == "and":
            if last not in ("hundred", "scale"):
                return None
            continue
        if t in _ONES:
            if last in ("unit", "teen") or last == "ten" and group % 10:
                return None
            group += _ONES[t]
            last = "unit"
        elif t in _TEENS:
            if last in ("unit", "teen", "ten"):
                return None
            group += _TEENS[t]
            last = "teen"
        elif t in _TENS:
            if last in ("unit", "teen", "ten"):
                return None
            group += _TENS[t]
            last = "ten"
        elif t == "hundred":
            if last != "unit" or group % 100 == 0 or group >= 10:
                return None
            group *= 100
            last = "hundred"
        elif t in _SCALES:
            if group == 0 or last == "scale":
                return None
            total += group * _SCALES[t]
            group = 0
            last = "scale"
        else:
            return None
    return total + group


def _denominator(text: str) -> int | None:
    """The denominator an ordinal phrase names: ``quarters`` 4, ``fiftieths`` 50,
    ``twenty-fifth`` 25, ``hundred and fiftieth`` 150."""
    tokens = [t for t in re.split(r"[\s-]+", text.strip().lower()) if t]
    last = tokens[-1]
    last = "half" if last == "halves" else last
    if last not in _ORDINAL_CARDINAL:
        last = last[:-1]
    if last not in _ORDINAL_CARDINAL:
        return None
    rest = tokens[:-1]
    if _ORDINAL_CARDINAL[last] in ("hundred", "thousand", "million") and not rest:
        rest = ["one"]
    value = words_value(" ".join([*rest, _ORDINAL_CARDINAL[last]]))
    return value if value else None


def _half_place(digits: str) -> float:
    """Half the last written place of a decimal (``29.8`` -> 0.05; ``30`` -> 3, ``150`` -> 5,
    ``1500`` -> 50: trailing zeros of a whole number are taken as not significant, but the
    rounding they allow is at most a tenth of the number — "two hundred" is not 150)."""
    if "." in digits:
        return 0.5 * 10 ** (-len(digits.split(".")[1]))
    whole = digits.lstrip("-").lstrip("0") or "0"
    zeros = len(whole) - len(whole.rstrip("0")) if whole != "0" else 0
    return 0.5 if zeros == 0 else min(0.5 * 10**zeros, 0.1 * int(whole))


def _sig_of(digits: str) -> tuple[int, bool]:
    """Significant figures of a decimal as written and whether the count is sure (a whole
    number ending in zeros may have more)."""
    d = digits.lstrip("-")
    if "." in d:
        body = d.replace(".", "").lstrip("0")
        return max(1, len(body) if body else len(d.split(".")[1])), True
    body = d.lstrip("0")
    stripped = body.rstrip("0")
    return max(1, len(stripped)), stripped == body


@dataclass(frozen=True)
class SaidValue:
    """A number written in a sentence: where (``start`` .. ``end``, the unit included), as
    written, its ``value`` in its ``unit`` (``None``: no unit; ``%`` is a unit), the
    ``resolution`` it was written to (half its last place, in its unit; 0 for an exact
    fraction), its significant figures (``sig``; ``sig_sure`` false when a whole number's trailing
    zeros leave it open, ``None`` for words without a point and fractions), and how it was said:
    ``approx`` ("about"), ``bound`` ("more than"), ``in_range`` ("400 to 700"). A share "1 in
    150" has ``per`` = 150 and ``per_resolution``."""

    start: int
    end: int
    text: str
    value: float
    resolution: float
    sig: int | None = None
    sig_sure: bool = False
    unit: Unit | None = None
    unit_text: str = ""
    approx: bool = False
    bound: bool = False
    in_range: bool = False
    per: float | None = None
    per_resolution: float = 0.0
    words: bool = False

    @property
    def dim(self) -> Dim:
        return self.unit.dim if self.unit is not None else DIMENSIONLESS

    @property
    def si(self) -> float:
        """The value in SI units (a share: its fraction)."""
        return float(self.unit.to_si(self.value)) if self.unit is not None else self.value

    @property
    def si_resolution(self) -> float:
        return self.resolution * float(self.unit.factor) if self.unit is not None else self.resolution

    @property
    def checkable(self) -> bool:
        """Said as a value (not a bound or one end of a range)."""
        return not self.bound and not self.in_range


@dataclass
class _Raw:
    start: int
    end: int
    value: float
    resolution: float
    sig: int | None
    sig_sure: bool
    exact: bool = False
    words: bool = False
    per: float | None = None
    per_resolution: float = 0.0


def _scan_number(sentence: str, m: re.Match[str]) -> _Raw | None:
    if m.group("dig") is not None:
        digits = m.group("dig").replace(",", "")
        try:
            value = float(digits)
        except ValueError:
            return None
        res = _half_place(digits)
        sig, sure = _sig_of(digits)
        exp = m.group("e1") or (m.group("e2").translate(_SUPER_DIGITS) if m.group("e2") else None) or (m.group("e3")[1:] if m.group("e3") else None)
        scale = 10.0 ** int(exp) if exp else 1.0
        if m.group("dscale"):
            scale *= _SCALES[m.group("dscale").lower()]
        if exp or m.group("dscale"):
            sure = sure or "." in digits
        raw = _Raw(m.start(), m.end(), value * scale, res * scale, sig, sure)
    else:
        n = words_value(m.group("words"))
        if n is None:
            # the longest start that is one number ("one twenty-fifth": "one", then a denominator)
            tokens = list(re.finditer(r"[A-Za-z]+", m.group("words")))
            for k in range(len(tokens) - 1, 0, -1):
                n = words_value(m.group("words")[: tokens[k - 1].end()])
                if n is not None:
                    return _Raw(m.start(), m.start() + tokens[k - 1].end(), float(n), _half_place(str(n)), None, False, words=True)
            return None
        text = str(n)
        if m.group("point"):
            decimals = "".join(str(_DIGIT_WORDS[w.lower()]) for w in m.group("point").split()[1:])
            text = f"{n}.{decimals}"
        value = float(text)
        res = _half_place(text)
        sig, sure = _sig_of(text) if m.group("point") else (None, False)
        scale = _SCALES[m.group("wscale").lower()] if m.group("wscale") else 1.0
        raw = _Raw(m.start(), m.end(), value * scale, res * scale, sig, sure, words=True)
    sci = _SCI_AFTER.match(sentence, raw.end)
    if sci is not None:
        e = words_value(sci.group("wexp")) if not sci.group("wexp").isdigit() else int(sci.group("wexp"))
        if e is not None:
            p = 10.0 ** (-e if sci.group("neg") else e)
            raw.value *= p
            raw.resolution *= p
            raw.end = sci.end()
            raw.sig_sure = raw.sig is not None
    return raw


def _numbers(sentence: str) -> list[_Raw]:
    """The numbers of a sentence, fractions (``three halves``, ``1/25``, ``one and a half``)
    and shares (``1 in 150``) combined."""
    out: list[_Raw] = []
    pos = 0
    while True:
        m = _NUMBER.search(sentence, pos)
        if m is None:
            break
        pos = m.end()
        raw = _scan_number(sentence, m)
        if raw is None:
            continue
        neg = _NEGATIVE.search(sentence[max(0, raw.start - 12):raw.start])
        if neg is not None:
            raw.value = -raw.value
        whole = raw.value.is_integer() and raw.sig is None or raw.resolution == 0.5
        half = _HALF_AFTER.match(sentence, raw.end)
        frac = _FRACTION_AFTER.match(sentence, raw.end)
        slash = _SLASH_AFTER.match(sentence, raw.end) if not raw.words else None
        if whole and half is not None:
            raw.value += 0.5 if raw.value >= 0 else -0.5
            raw.end, raw.resolution, raw.exact, raw.sig = half.end(), 0.0, True, None
            scale = _SCALE_AFTER.match(sentence, raw.end)
            if scale is not None:   # "one and a half million kilometres": said to a quarter of the scale
                factor = _SCALES[scale.group("s").lower()]
                raw.value *= factor
                raw.end, raw.resolution, raw.exact = scale.end(), 0.25 * factor, False
        elif whole and frac is not None and raw.value > 0 and _denominator(frac.group("den")):
            raw.value /= _denominator(frac.group("den")) or 1
            raw.end, raw.resolution, raw.exact, raw.sig = frac.end(), 0.0, True, None
        elif whole and slash is not None and int(slash.group("b")) > 0:
            raw.value /= int(slash.group("b"))
            raw.end, raw.resolution, raw.exact, raw.sig = slash.end(), 0.0, True, None
        pos = max(pos, raw.end)
        out.append(raw)
    merged: list[_Raw] = []
    k = 0
    while k < len(out):
        a = out[k]
        b = out[k + 1] if k + 1 < len(out) else None
        if b is not None and not a.exact and a.value.is_integer() and a.value > 0 and b.value >= a.value:
            gap = _SHARE_GAP.match(sentence, a.end)
            if gap is not None and gap.end() == b.start:
                merged.append(_Raw(a.start, b.end, a.value / b.value, 0.0, None, False, True, True, b.value / a.value, b.resolution / a.value))
                k += 2
                continue
        merged.append(a)
        k += 1
    return merged


# ----- units in words and symbols ----------------------------------------------------------------------

_PREFIX_WORDS = {"pico": "p", "nano": "n", "micro": "µ", "milli": "m", "centi": "c", "kilo": "k", "mega": "M", "giga": "G", "tera": "T"}
#: Unit names as said: (pattern, symbol, prefixable), longest first where they share a start.
UNIT_WORDS: tuple[tuple[str, str, bool], ...] = (
    (r"astronomical\s+units?", "au", False), (r"light[- ]years?", "ly", False), (r"electron[- ]?volts?", "eV", True),
    (r"degrees?\s+(?:celsius|centigrade)", "°C", False), (r"degrees?\s+fahrenheit", "°F", False), (r"per\s*cent", "%", False),
    (r"metres?|meters?", "m", True), (r"grammes?|grams?", "g", True), (r"seconds?", "s", True), (r"minutes?", "min", False),
    (r"hours?", "h", False), (r"days?", "d", False), (r"years?", "yr", True), (r"litres?|liters?", "L", True), (r"moles?", "mol", True),
    (r"kelvins?", "K", True), (r"joules?", "J", True), (r"watts?", "W", True), (r"newtons?", "N", True), (r"pascals?", "Pa", True),
    (r"hertz", "Hz", True), (r"becquerels?", "Bq", True), (r"volts?", "V", True), (r"amperes?|amps?", "A", True),
    (r"coulombs?", "C", True), (r"ohms?", "Ω", True), (r"teslas?", "T", True), (r"sieverts?", "Sv", True), (r"tonnes?", "t", False),
    (r"daltons?", "Da", True), (r"calories?", "cal", True), (r"atmospheres?", "atm", False), (r"parsecs?", "pc", True),
    (r"degrees?", "deg", False), (r"angstroms?|ångströms?", "Å", False), (r"molar", "M", True), (r"radians?", "rad", True),
    (r"percent", "%", False),
)
_UNIT_ALT = "|".join(p for p, _, _ in UNIT_WORDS)
_TERM = re.compile(rf"(?:(?P<pow1>square|cubic)\s+)?(?P<pre>{'|'.join(_PREFIX_WORDS)})?[- ]?(?P<u>{_UNIT_ALT})(?:\s+(?P<pow2>squared|cubed))?\b",
                   re.IGNORECASE)
_PER = re.compile(r"\s+(?P<sep>per|an?|each)\s+", re.IGNORECASE)
_TIME_SYMBOLS = frozenset({"s", "min", "h", "d", "yr"})
#: Symbols after a number that are English words, not units (``5 am``, ``2 as``).
_NOT_UNITS = frozenset({"am", "as", "at", "us", "pm", "eg", "em", "da", "cd", "ha", "hm", "dam", "mas", "pas", "in", "is", "it", "or", "of",
                        "on", "to", "by", "be", "a", "an", "I", "Gy", "bar", "mbar", "ft"})
_SYMBOL = re.compile(r"(?P<tok>(?:[A-Za-zµμΩÅ%]|°[CF]?)[A-Za-z0-9µμΩÅ°%/·^²³⁻⁰¹⁴⁵⁶⁷⁸⁹*()+-]*)")


def _term(text: str, pos: int) -> tuple[str, int] | None:
    m = _TERM.match(text, pos)
    if m is None:
        return None
    word = m.group("u").lower()
    entry = next(((sym, pre) for pat, sym, pre in UNIT_WORDS if re.fullmatch(pat, word, re.IGNORECASE)), None)
    if entry is None:
        return None
    sym, prefixable = entry
    if m.group("pre"):
        if not prefixable:
            return None
        sym = _PREFIX_WORDS[m.group("pre").lower()] + sym
    power = m.group("pow1") or m.group("pow2")
    if power:
        sym += "^2" if power.lower().startswith("squ") else "^3"
    return sym, m.end()


def spoken_unit(text: str, pos: int) -> tuple[Unit, str, int] | None:
    """A unit said in words at ``pos`` (after optional spaces): ``kilometres per second``,
    ``metres per second squared``, ``kilometres an hour``, ``per hour``, ``micrograms per
    litre``, ``degrees Celsius``: ``(unit, as written, end)``."""
    start = pos + len(text[pos:]) - len(text[pos:].lstrip())
    num: list[str] = []
    den: list[str] = []
    at = start
    lead = re.match(r"per\s+", text[at:], re.IGNORECASE)
    if lead is not None:
        t = _term(text, at + lead.end())
        if t is None:
            return None
        den.append(t[0])
        at = t[1]
    else:
        t = _term(text, at)
        if t is None:
            return None
        num.append(t[0])
        at = t[1]
    while True:
        sep = _PER.match(text, at)
        if sep is None:
            break
        t = _term(text, sep.end())
        if t is None:
            break
        if sep.group("sep").lower() != "per" and (t[0] not in _TIME_SYMBOLS or any(n in _TIME_SYMBOLS for n in num)):
            break
        den.append(t[0])
        at = t[1]
    unit_text = ("*".join(num) or "1") + "".join(f"/{d}" for d in den)
    try:
        unit = parse_unit(unit_text)
    except VidgenError:
        return None
    return unit, text[start:at], at


def symbol_unit(text: str, pos: int) -> tuple[Unit, str, int] | None:
    """A unit written in symbols at ``pos`` (``km/s``, ``m/s²``, ``GeV/c²``, ``µg/L``, ``°C``,
    ``h⁻¹``, ``%``), or ``None`` (an English word such as ``am``, a symbol the units do not
    know)."""
    m = re.compile(r"[ \t]?").match(text, pos)
    start = m.end() if m else pos
    sm = _SYMBOL.match(text, start)
    if sm is None:
        return None
    tok = sm.group("tok")
    while tok and tok[-1] in ".,;:)-+" and not (tok[-1] == ")" and tok.count("(") >= tok.count(")")):
        tok = tok[:-1]
    if not tok or tok in _NOT_UNITS or tok.lower() in ("in", "is", "it", "or", "of", "on", "to", "by", "be", "a", "an"):
        return None
    if re.fullmatch(r"[A-Za-z]{3,}", tok) and tok.lower() not in ("min", "mol", "atm", "ppm", "cal", "kcal", "mmol", "kpc", "yr", "kyr", "eV"):
        if not any(c.isupper() for c in tok[1:]):
            return None   # a word, not a unit (``5 days``, ``8 seedlings``)
    try:
        unit = parse_unit(tok)
    except VidgenError:
        return None
    return unit, tok, start + len(tok)


def _unit_at(sentence: str, pos: int, glued_ok: bool) -> tuple[Unit, str, int] | None:
    spoken = spoken_unit(sentence, pos)
    if spoken is not None and sentence[pos:spoken[2]][:1].isspace():
        return spoken
    if not glued_ok:
        return None
    return symbol_unit(sentence, pos)


def default_unit(sentence: str) -> Unit | None:
    """A unit the sentence says its numbers are in: "In kilograms, ...", "measured in days"."""
    for m in re.finditer(r"\bin\s+", sentence, re.IGNORECASE):
        found = spoken_unit(sentence, m.end())
        if found is not None and not re.match(r"\s*\d", sentence[m.end():]):
            return found[0]
    return None


def said_values(sentence: str) -> list[SaidValue]:
    """Every number of ``sentence`` with its unit (spoken or in symbols; a number without one
    takes the sentence's "in <unit>"), how finely it was written and how it was said."""
    raws = _numbers(sentence)
    fallback = default_unit(sentence)
    out: list[SaidValue] = []
    for r in raws:
        unit_found = None if r.per is not None else _unit_at(sentence, r.end, not r.words)
        unit, unit_text, end = (unit_found if unit_found is not None else (None, "", r.end))
        if unit is None and r.per is None and fallback is not None and not r.exact:
            unit = fallback
        before = sentence[max(0, r.start - 30):r.start]
        if _NEGATIVE.search(before):
            before = before[: _NEGATIVE.search(before).start()]
        out.append(SaidValue(r.start, end, sentence[r.start:end], r.value, r.resolution, r.sig, r.sig_sure, unit, unit_text,
                             _APPROX.search(before) is not None, _BOUND.search(before) is not None, False, r.per, r.per_resolution, r.words))
    ranged = set()
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        gap = sentence[a.end:b.start]
        if _RANGE_GAP.match(gap) and (gap.strip().lower() != "and" or _RANGE_START.search(sentence[max(0, a.start - 30):a.start])):
            ranged |= {i, i + 1}   # "400 to 700 nm", "two or three", "between 3 and 5 days"
    return [SaidValue(**{**v.__dict__, "in_range": True}) if i in ranged else v for i, v in enumerate(out)]


# ----- comparing ---------------------------------------------------------------------------------------


def _rounded_to(value: float, actual: float, figures: Iterable[int]) -> bool:
    for f in figures:
        if actual != 0 and math.isclose(value, float(round_sig(actual, f)), rel_tol=1e-9, abs_tol=1e-300):
            return True
    return False


def agrees(said: SaidValue, actual_si: float, tolerance: float = 0.05, sigma_si: float = 0.0) -> bool:
    """Whether ``said`` is ``actual_si`` (an SI value) as it was written: within its resolution
    (and ``sigma_si``, an uncertainty of the actual value); said with "about", also when it is
    the value rounded to one or two significant figures or within ``tolerance`` (relative).
    A share "1 in N" is compared on N."""
    if said.per is not None:
        if actual_si <= 0:
            return False
        inv = 1.0 / actual_si
        slack = said.per_resolution + (sigma_si * inv * inv) + 1e-9 * inv
        if abs(said.per - inv) <= slack:
            return True
        return said.approx and (_rounded_to(said.per, inv, (1, 2)) or abs(said.per - inv) <= tolerance * inv)
    unit = said.unit
    value_si = said.si
    slack = said.si_resolution + sigma_si + 1e-9 * max(abs(actual_si), abs(value_si))
    if abs(value_si - actual_si) <= slack:
        return True
    if not said.approx:
        return False
    actual = float(unit.from_si(actual_si)) if unit is not None else actual_si
    return _rounded_to(said.value, actual, (1, 2)) or abs(value_si - actual_si) <= tolerance * abs(actual_si) + sigma_si


def mixup_power(said: SaidValue, actual_si: float, tolerance: float = 0.05) -> int:
    """The power of ten (a multiple of 3: a prefix, km for m, mg for µg) by which ``said`` is
    off from ``actual_si`` while it would agree after it; 0 when there is none."""
    if said.unit is None or said.per is not None or actual_si == 0 or said.si == 0 or (said.si > 0) != (actual_si > 0):
        return 0
    k = round(math.log10(abs(said.si / actual_si)) / 3) * 3
    if k == 0:
        return 0
    scaled = SaidValue(**{**said.__dict__, "value": said.value / 10**k, "resolution": said.resolution / 10**k})
    return k if agrees(scaled, actual_si, tolerance) else 0


def in_unit_text(actual_si: float, unit: Unit | None, sig: int | None) -> str:
    """``actual_si`` written in ``unit`` with ``sig`` figures (3 when exact or unknown)."""
    value = float(unit.from_si(actual_si)) if unit is not None else actual_si
    text = decimal_text(value, sig or 3).plain
    if unit is not None and unit.text:
        text += ("" if unit.text in ("%", "°") else " ") + unit.text
    return text


def said_name(said: SaidValue) -> str:
    return f'"{said.text.strip()}"'


# ----- dimension words -------------------------------------------------------------------------------------

_ENERGY = dim(kg=1, m=2, s=-2)
#: Words naming a quantity and the dimensions a value said for it may have (masses and momenta
#: in eV are natural units; a frequency may be a share, as an allele frequency).
DIMENSION_WORDS: tuple[tuple[str, tuple[Dim, ...], str], ...] = (
    (r"speeds?|velocity|velocities", (dim(m=1, s=-1),), "a speed"),
    (r"distances?|lengths?|heights?|radius|radii|diameters?|depths?|altitudes?|wavelengths?|semi-major\s+axis", (dim(m=1),), "a length"),
    (r"masses|mass", (dim(kg=1), _ENERGY), "a mass"),
    (r"momentum|momenta", (dim(kg=1, m=1, s=-1), _ENERGY), "a momentum"),
    (r"energy|energies", (_ENERGY,), "an energy"),
    (r"half-lives|half-life|half\s+life|periods?|lifetimes?|durations?|doubling\s+time", (dim(s=1),), "a time"),
    (r"temperatures?", (dim(K=1),), "a temperature"),
    (r"pressures?", (dim(kg=1, m=-1, s=-2),), "a pressure"),
    (r"forces?", (dim(kg=1, m=1, s=-2),), "a force"),
    (r"accelerations?", (dim(m=1, s=-2),), "an acceleration"),
    (r"frequency|frequencies", (dim(s=-1), DIMENSIONLESS), "a frequency"),
    (r"voltages?", (dim(kg=1, m=2, s=-3, A=-1),), "a voltage"),
    (r"volumes?", (dim(m=3),), "a volume"),
)
_DIM_WORD = re.compile(rf"\b(?P<w>{'|'.join(p for p, _, _ in DIMENSION_WORDS)})\b", re.IGNORECASE)
_LINK = re.compile(r"^\s*(?:(?:of|is|was|are|were|equals?|=|≈|reaches|reached|comes\s+out\s+(?:at|as)|stays\s+at|of\s+just|only|just|"
                   r"about|around|roughly|nearly|almost|approximately|close\s+to|some)\s*)+$", re.IGNORECASE)
_EXAMPLE_UNITS = {
    dim(m=1, s=-1): "m/s, km/s, km/h", dim(m=1): "m, km, nm, au", dim(kg=1): "kg, g, mg, GeV/c²", dim(kg=1, m=1, s=-1): "kg·m/s, GeV/c",
    _ENERGY: "J, eV, kJ", dim(s=1): "s, min, h, d, yr", dim(K=1): "K, °C", dim(kg=1, m=-1, s=-2): "Pa, kPa, atm, bar",
    dim(kg=1, m=1, s=-2): "N", dim(m=1, s=-2): "m/s²", dim(s=-1): "Hz, 1/s", dim(kg=1, m=2, s=-3, A=-1): "V, mV", dim(m=3): "m³, L, mL",
}


def dimension_claims(text: str) -> list[Claim]:
    """A value said for a quantity in a unit of another dimension: "a speed of 30 kilometres",
    "a half-life of 8 metres", "an energy of 5 kilograms"."""
    out: list[Claim] = []
    for s in statements(text):
        values = said_values(s)
        for m in _DIM_WORD.finditer(s):
            entry = next(e for e in DIMENSION_WORDS if re.fullmatch(e[0], m.group("w"), re.IGNORECASE))
            nxt = next((v for v in values if v.start >= m.end()), None)
            if nxt is None or nxt.unit is None or nxt.per is not None or not _LINK.match(s[m.end():nxt.start]):
                continue
            ok = entry[1]
            if nxt.dim in ok or (nxt.unit.text == "°" and dim(K=1) in ok):
                continue
            examples = _EXAMPLE_UNITS.get(ok[0], describe_dim(ok[0]))
            out.append(Claim(quote(s), f"{said_name(nxt)} is {describe_dim(nxt.dim)}, but {entry[2]} is measured in {examples}: "
                                       f"give it the unit of {entry[2]}, or the right quantity"))
    return out


# ----- what fitted parameters are called ---------------------------------------------------------------------

#: Words for a fitted quantity (keys of :func:`fit_quantities`).
FIT_WORDS: dict[str, str] = {
    "half_life": r"half-lives|half-life|half\s+life|t½|t_?1/2",
    "doubling": r"doubling\s+time",
    "lifetime": r"time\s+constant|mean\s+life(?:time)?|lifetime|e-folding\s+time|τ",
    "rate": r"decay\s+constant|decay\s+rate|rate\s+constant|elimination\s+rate(?:\s+constant)?",
    "growth": r"growth\s+rate",
    "exponent": r"exponent|power-law\s+index|power\s+law\s+index|index",
    "slope": r"slope|gradient",
    "intercept": r"intercept",
    "centre": r"mean|average|centre|center|peaks?\s+at|peak\s+position|position\s+of\s+the\s+peak",
    "sigma": r"standard\s+deviation|σ|sigma",
    "width": r"full\s+width\s+at\s+half\s+maximum|fwhm|width",
    "capacity": r"carrying\s+capacity|plateau",
    "midpoint": r"midpoint|inflection\s+point",
    "mass": r"mass",
}
_FIT_WORD = re.compile(rf"(?<![\w-])(?P<w>{'|'.join(FIT_WORDS.values())})(?![\w-])", re.IGNORECASE)
_FIT_LINK = re.compile(r"^\s*(?:(?:,\s*)?(?:of|is|was|are|=|≈|equals?|at|comes\s+out\s+(?:at|as)|close\s+to|near|about|around|roughly|nearly|"
                       r"approximately|almost|just\s+(?:over|under)|:|the\s+fit\s+gives|fitted|fits?|gives?|from\s+the\s+fit)\s*)*$", re.IGNORECASE)


@dataclass(frozen=True)
class FitQuantity:
    """A quantity a fit determines: what it is called (a :data:`FIT_WORDS` key, or a custom
    parameter's name), its value and standard error in ``unit`` (text, may be empty), the fit."""

    key: str
    value: float
    error: float
    unit: str
    fit: str


def fit_quantities(fit: str, kind: str, names: Sequence[str], params: Sequence[float], errors: Sequence[float], units: Sequence[str],
                   x_unit: str = "") -> list[FitQuantity]:
    """The quantities a fit of ``kind`` gives, with errors propagated: an exponential decay's
    half-life, lifetime and rate (growth: doubling time, growth rate), a power law's exponent, a
    line's slope and intercept, a peak's centre, σ and FWHM (a Breit–Wigner: M and Γ), a
    logistic's capacity, midpoint and rate, a distribution's mean (and an exponential's
    lifetime), a custom model's parameters by name."""
    p = {n: (float(v), float(e), u) for n, v, e, u in zip(names, params, errors, units)}
    out: list[FitQuantity] = []

    def add(key: str, value: float, error: float, unit: str) -> None:
        if math.isfinite(value) and math.isfinite(error):
            out.append(FitQuantity(key, value, abs(error), unit, fit))

    inverse = x_unit
    if kind == "exponential" and "k" in p:
        k, ek, ku = p["k"]
        if k < 0:
            add("half_life", math.log(2) / -k, math.log(2) * ek / k**2, inverse)
            add("lifetime", 1 / -k, ek / k**2, inverse)
            add("rate", -k, ek, ku)
        elif k > 0:
            add("doubling", math.log(2) / k, math.log(2) * ek / k**2, inverse)
            add("growth", k, ek, ku)
            add("rate", k, ek, ku)
    elif kind == "exponential" and "lambda" in p:      # the distribution
        lam, el, _ = p["lambda"]
        if lam > 0:
            add("rate", lam, el, f"1/{x_unit}" if x_unit else "")
            add("lifetime", 1 / lam, el / lam**2, x_unit)
            add("centre", 1 / lam, el / lam**2, x_unit)
            add("half_life", math.log(2) / lam, math.log(2) * el / lam**2, x_unit)
    elif kind == "power" and "k" in p:
        add("exponent", *p["k"])
    elif kind == "linear":
        add("slope", *p["b"])
        add("intercept", *p["a"])
    elif kind in ("gaussian", "normal"):
        add("centre", *p["mu"])
        add("sigma", *p["sigma"])
        add("width", 2 * math.sqrt(2 * math.log(2)) * abs(p["sigma"][0]), 2 * math.sqrt(2 * math.log(2)) * p["sigma"][1], p["sigma"][2])
        add("width", abs(p["sigma"][0]), p["sigma"][1], p["sigma"][2])
        add("mass", *p["mu"])
    elif kind == "breit_wigner":
        add("centre", *p["M"])
        add("mass", *p["M"])
        add("width", *p["Gamma"])
    elif kind == "logistic":
        add("capacity", *p["L"])
        add("midpoint", *p["x0"])
        add("growth", *p["k"])
    elif kind == "poisson":
        add("centre", *p["mu"])
    elif kind == "custom":
        for n, (v, e, u) in p.items():
            if len(n) >= 2:
                add(n, v, e, u)
    return out


def _custom_word(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")


def fit_claims(text: str, quantities: Sequence[FitQuantity], sigmas: float = 2.0, tolerance: float = 0.05) -> list[Claim]:
    """A value said for a fitted quantity ("a half-life of eight days", "exponent three halves",
    "the peak at 126 GeV") that the fit does not give: off by more than ``sigmas`` standard
    errors and the said value's own rounding ("about": also rounding to 1–2 figures or
    ``tolerance``)."""
    keys = {q.key for q in quantities}
    if not keys:
        return []
    out: list[Claim] = []
    customs = [k for k in keys if k not in FIT_WORDS]
    for s in statements(text):
        values = said_values(s)
        found: list[tuple[str, re.Match[str]]] = []
        for m in _FIT_WORD.finditer(s):
            key = next((k for k, pat in FIT_WORDS.items() if re.fullmatch(pat, m.group("w"), re.IGNORECASE)), None)
            if key is not None and key in keys:
                found.append((key, m))
        for name in customs:
            found += [(name, m) for m in _custom_word(name).finditer(s)]
        for key, m in found:
            nxt = next((v for v in values if v.start >= m.end()), None)
            if nxt is None or not nxt.checkable or not _FIT_LINK.match(s[m.end():nxt.start]):
                continue
            mine = [q for q in quantities if q.key == key]
            if any(_fit_agrees(nxt, q, sigmas, tolerance) for q in mine):
                continue
            q = mine[0]
            if q.unit and nxt.unit is not None:
                try:
                    if parse_unit(q.unit).dim != nxt.dim:
                        continue    # another quantity (a width in time, a peak's height): not this parameter
                except VidgenError:
                    continue
            shown = f"{decimal_text(q.value, 3).plain} ± {decimal_text(q.error, 2).plain}" + (f" {q.unit}" if q.unit else "")
            out.append(Claim(quote(s), f"{said_name(nxt)}, but the fit '{q.fit}' gives {_KEY_NAMES.get(key, key + ' =')} {shown}: say "
                                       f"what the fit found, or fit what you say"))
    return out


_KEY_NAMES = {"half_life": "a half-life of", "doubling": "a doubling time of", "lifetime": "a lifetime (time constant) of",
              "rate": "a rate constant of", "growth": "a growth rate of", "exponent": "an exponent of", "slope": "a slope of",
              "intercept": "an intercept of", "centre": "a centre (mean) at", "sigma": "σ =", "width": "a width of",
              "capacity": "a carrying capacity of", "midpoint": "a midpoint at", "mass": "a mass of"}


def _fit_agrees(said: SaidValue, q: FitQuantity, sigmas: float, tolerance: float) -> bool:
    if said.unit is not None and q.unit:
        try:
            target = parse_unit(q.unit)
        except VidgenError:
            return True     # a unit the engine cannot read: nothing to compare
        if target.dim != said.dim:
            return True
        actual_si = float(target.to_si(q.value))
        sigma_si = sigmas * q.error * float(target.factor)
        return agrees(said, actual_si, tolerance, sigma_si)
    plain_said = SaidValue(**{**said.__dict__, "unit": None})
    return agrees(plain_said, q.value, tolerance, sigmas * q.error)


# ----- error bars --------------------------------------------------------------------------------------------

#: What error bars are said to be, and the ``error`` value that means it.
ERROR_WORDS: tuple[tuple[str, str], ...] = (
    (r"standard\s+errors?(?:\s+of\s+the\s+mean)?|\bSEM\b|\bs\.e\.m\.", "sem"),
    (r"standard\s+deviations?|\bSD\b|\bs\.d\.", "sd"),
    (r"(?:95|ninety-five)\s*(?:%|percent|per\s+cent)?\s*confidence\s+intervals?|confidence\s+intervals?|\bCI\b", "ci95"),
    (r"(?:full\s+)?range\b|minimum\s+(?:to|and)\s+maximum|min(?:imum)?\s*(?:-|–|to)\s*max(?:imum)?", "range"),
    (r"poisson|square\s+roots?\s+of\s+the\s+counts?|√N|root\s+N\b|counting\s+errors?", "poisson"),
)
_BAR_WORDS = re.compile(r"\b(?:error\s*bars?|bars|whiskers|uncertaint(?:y|ies)|errors?)\b", re.IGNORECASE)
ERROR_NAMES = {"sd": "standard deviations", "sem": "standard errors of the mean", "ci95": "95 % confidence intervals", "range": "the range (min to max)",
               "poisson": "Poisson errors (√N)", "other": "another error"}


def error_meaning_claims(text: str, declared: set[str]) -> list[Claim]:
    """Error bars called something they are not declared to be ("standard deviation" for bars
    declared ``error: sem``)."""
    if not declared or "other" in declared:
        return []
    out: list[Claim] = []
    for s in statements(text):
        if _BAR_WORDS.search(s) is None:
            continue
        for pattern, meaning in ERROR_WORDS:
            m = re.search(pattern, s, re.IGNORECASE)
            if m is None or meaning in declared:
                continue
            if meaning == "range" and not re.search(r"\b(?:bars?|whiskers|errors?)\s+(?:show|span|give|cover|mark)\w*\s+(?:the\s+)?(?:full\s+)?range",
                                                     s, re.IGNORECASE):
                continue    # "range" is an everyday word; only "the bars show the range" is a claim
            names = " and ".join(ERROR_NAMES[d] for d in sorted(declared))
            out.append(Claim(quote(s), f"\"{m.group(0)}\": the error bars are declared as {names} (error: {', '.join(sorted(declared))}): "
                                       f"say that, or fix the series' error"))
            break
    return out


@dataclass
class Candidate:
    """A value of a calculation a number may refer to: a symbol or a result, its name, meaning,
    SI value, significant figures (``None``: exact), how it is shown, the scene."""

    name: str
    meaning: str
    value: float
    dim: Dim
    sig: int | None
    shown: str
    unit: Unit | None
    result: bool
    scene: str
    stems: frozenset[str] = field(default_factory=frozenset)


__all__ = [
    "Candidate",
    "DIMENSION_WORDS",
    "ERROR_NAMES",
    "ERROR_WORDS",
    "FIT_WORDS",
    "FitQuantity",
    "SaidValue",
    "UNIT_WORDS",
    "agrees",
    "clean",
    "default_unit",
    "dimension_claims",
    "error_meaning_claims",
    "fit_claims",
    "fit_quantities",
    "in_unit_text",
    "mixup_power",
    "quote",
    "said_name",
    "said_values",
    "spoken_unit",
    "statements",
    "symbol_unit",
    "words_value",
]
