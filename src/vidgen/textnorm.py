"""Text normalisation for comparing what was written with what was heard (DESIGN.md §57).

``vidgen readback`` compares a beat's spoken text with a speech-to-text transcript of its MP3.
Both go through :func:`normalize_words` so that differences in *writing* do not count as
differences in *speech*: case, punctuation, accents (``você`` = ``voce``), hyphenation
(``one-by-one`` = ``one by one``), numbers (``2.58`` = ``two point five eight``, ``77%`` =
``seventy seven percent``; English and Portuguese number words, digits kept for other
languages), symbols (``&`` = ``and``) and spelled-out acronyms (``G.P.U.`` = ``G P U`` =
``GPU``).

Every normalised token remembers the index of the word it came from (:class:`Token.source`),
so a difference can be reported in terms of the original words. No manim import.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from typing import NamedTuple

from vidgen.languages import primary_language


class Token(NamedTuple):
    """A normalised word and the index of the input word it comes from."""

    text: str
    source: int


# ----- numbers ----------------------------------------------------------------------------------

_EN_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen"
).split()
_EN_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_EN_SCALES = ((10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand"))

_PT_ONES = (
    "zero um dois três quatro cinco seis sete oito nove dez onze doze treze catorze quinze dezesseis "
    "dezessete dezoito dezenove"
).split()
_PT_TENS = "_ _ vinte trinta quarenta cinquenta sessenta setenta oitenta noventa".split()
_PT_HUNDREDS = "_ cento duzentos trezentos quatrocentos quinhentos seiscentos setecentos oitocentos novecentos".split()
_PT_SCALES = ((10**12, "trilhão", "trilhões"), (10**9, "bilhão", "bilhões"), (10**6, "milhão", "milhões"))

#: Largest number spelled out; longer digit runs are read digit by digit.
_MAX_NUMBER = 10**15 - 1


def _en_below_1000(n: int) -> list[str]:
    words: list[str] = []
    if n >= 100:
        words += [_EN_ONES[n // 100], "hundred"]
        n %= 100
        if n == 0:
            return words
    if n < 20:
        words.append(_EN_ONES[n])
    else:
        words.append(_EN_TENS[n // 10])
        if n % 10:
            words.append(_EN_ONES[n % 10])
    return words


def english_number(n: int) -> list[str]:
    """The English words of a whole number ``0 <= n < 10**15`` (``227``: two hundred twenty
    seven; no "and", no hyphens)."""
    if n < 1000:
        return _en_below_1000(n)
    words: list[str] = []
    for scale, name in _EN_SCALES:
        if n >= scale:
            words += [*english_number(n // scale), name]
            n %= scale
    if n:
        words += _en_below_1000(n)
    return words


def _pt_below_1000(n: int) -> list[str]:
    if n == 100:
        return ["cem"]
    words: list[str] = []
    if n >= 100:
        words.append(_PT_HUNDREDS[n // 100])
        n %= 100
        if n == 0:
            return words
        words.append("e")
    if n < 20:
        words.append(_PT_ONES[n])
    else:
        words.append(_PT_TENS[n // 10])
        if n % 10:
            words += ["e", _PT_ONES[n % 10]]
    return words


def portuguese_number(n: int) -> list[str]:
    """The Portuguese (Brazilian) words of a whole number ``0 <= n < 10**15`` (``227``:
    duzentos e vinte e sete; ``1000``: mil; ``2,5 milhões``-style scales)."""
    if n < 1000:
        return _pt_below_1000(n)
    words: list[str] = []
    rest = n
    for scale, one, many in _PT_SCALES:
        if rest >= scale:
            count = rest // scale
            words += [*portuguese_number(count), one if count == 1 else many]
            rest %= scale
    if rest >= 1000:
        thousands = rest // 1000
        words += (["mil"] if thousands == 1 else [*portuguese_number(thousands), "mil"])
        rest %= 1000
    if rest:
        # "e" before a last group below 100 or a round hundred: "dois mil e vinte", "mil e cem"
        if rest < 100 or rest % 100 == 0:
            words.append("e")
        words += _pt_below_1000(rest)
    return words


_EN_ORDINAL = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}


def _english_ordinal(words: list[str]) -> list[str]:
    last = words[-1]
    if last in _EN_ORDINAL:
        last = _EN_ORDINAL[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return [*words[:-1], last]


class _NumberWords(NamedTuple):
    cardinal: Callable[[int], list[str]]
    point: str
    percent: tuple[str, ...]
    decimal_mark: str
    group_mark: str
    digit_by_digit: bool  # decimals read digit by digit (en) or as a whole number (pt)


_NUMBERS: dict[str, _NumberWords] = {
    "en": _NumberWords(english_number, "point", ("percent",), ".", ",", True),
    "pt": _NumberWords(portuguese_number, "vírgula", ("por", "cento"), ",", ".", False),
}
#: Decimal marks of languages without number words (their numbers stay digits): a comma, except
#: in these languages.
_POINT_DECIMAL = frozenset({"en", "zh", "ja", "ko", "th", "he", "hi"})

#: Symbols read as words, per language (the language's primary subtag; ``en`` the fallback).
_SYMBOL_WORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {"&": ("and",), "+": ("plus",), "=": ("equals",), "×": ("times",), "%": ("percent",), "@": ("at",)},
    "pt": {"&": ("e",), "+": ("mais",), "=": ("igual",), "×": ("vezes",), "%": ("por", "cento"), "@": ("arroba",)},
}
_CURRENCY = {"$": "dollars", "€": "euros", "£": "pounds"}
_PT_CURRENCY = {"$": "dólares", "€": "euros", "£": "libras"}

_NUMBER = re.compile(r"(?P<cur>[$€£])?(?P<num>\d+(?:[.,]\d+)*)(?P<ord>st|nd|rd|th)?(?P<pct>%)?", re.IGNORECASE)


def number_words(number: str, language: str | None = None, *, ordinal: bool = False) -> list[str]:
    """The words of a number as written (``2.58``, ``1,000``, ``1,57`` in Portuguese) in
    ``language`` (English when ``None``). Languages without number words keep digits: the whole
    part without group marks, then the decimals (``1.000,5`` → ``1000`` ``5`` in German)."""
    code = primary_language(language)
    rules = _NUMBERS.get(code)
    decimal = rules.decimal_mark if rules else ("." if code in _POINT_DECIMAL else ",")
    group = rules.group_mark if rules else ("," if decimal == "." else ".")
    grouped = rf"\d{{1,3}}(?:{re.escape(group)}\d{{3}})+"
    match = re.fullmatch(rf"(?P<whole>{grouped}|\d+)(?:{re.escape(decimal)}(?P<frac>\d+))?", number)
    if match is None:
        # marks that fit no reading ("1.2.3", a version, "1,57" in English): each digit run
        return [w for run in re.findall(r"\d+", number) for w in number_words(run, language)]
    whole, frac = match.group("whole").replace(group, ""), match.group("frac") or ""
    if rules is None:
        return [str(int(whole))] + ([frac] if frac else [])
    value = int(whole)
    out = rules.cardinal(value) if value <= _MAX_NUMBER else [w for d in whole for w in rules.cardinal(int(d))]
    if frac:
        out.append(rules.point)
        if rules.digit_by_digit or frac.startswith("0") or len(frac) > 3:
            out += [w for d in frac for w in rules.cardinal(int(d))]
        else:
            out += rules.cardinal(int(frac))
    if ordinal and code == "en" and not frac:
        out = _english_ordinal(out)
    return out


# ----- words ------------------------------------------------------------------------------------

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'"})
_SPLIT = re.compile(r"[-‐‑–—/\\_]+")
_DOTTED_ACRONYM = re.compile(r"(?:[A-Za-z]\.){2,}[A-Za-z]?")
_PIECE = re.compile(
    r"(?P<number>[$€£]?\d+(?:[.,]\d+)*(?:st|nd|rd|th)?%?)|(?P<word>[^\W\d_]+(?:'[^\W\d_]+)*)|(?P<symbol>[&+=×%@])",
    re.IGNORECASE,
)


def fold(word: str) -> str:
    """``word`` in lower case without accents (``Você`` → ``voce``, ``Gómez`` → ``gomez``,
    ``ç`` → ``c``)."""
    decomposed = unicodedata.normalize("NFKD", word.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).replace("ß", "ss")


def _word_tokens(word: str, language: str | None) -> list[tuple[str, bool]]:
    """The normalised tokens of one input word: ``(token, is_letter)``, ``is_letter`` for a single
    letter written as a capital or with a dot (a letter of a spelled-out acronym)."""
    code = primary_language(language)
    symbols = _SYMBOL_WORDS.get(code, _SYMBOL_WORDS["en"])
    currency = _PT_CURRENCY if code == "pt" else _CURRENCY
    word = unicodedata.normalize("NFC", word).translate(_APOSTROPHES)
    core = word.strip(".,;:!?\"'()[]{}…“”«»¿¡")
    if _DOTTED_ACRONYM.fullmatch(core) or _DOTTED_ACRONYM.fullmatch(core + "."):
        letters = core.replace(".", "")
        return [(fold(letters), False)] if len(letters) > 1 else [(fold(letters), True)]
    out: list[tuple[str, bool]] = []
    for piece in _SPLIT.split(word):
        for match in _PIECE.finditer(piece):
            if match.group("number"):
                m = _NUMBER.fullmatch(match.group("number"))
                if m is None:  # pragma: no cover - the piece pattern is the number pattern
                    continue
                words = number_words(m.group("num"), language, ordinal=bool(m.group("ord")))
                if m.group("pct"):
                    words += list(symbols["%"])
                if m.group("cur"):
                    words.append(currency[m.group("cur")])
                out += [(fold(w), False) for w in words]
            elif match.group("word"):
                text = match.group("word")
                letter = len(text) == 1 and (text.isupper() or piece[match.end() : match.end() + 1] == ".")
                out.append((fold(text.replace("'", "")), letter))
            else:
                out += [(fold(w), False) for w in symbols[match.group("symbol")]]
    return out


def normalize_words(words: Sequence[str], language: str | None = None) -> list[Token]:
    """The normalised tokens of ``words`` (a text split at spaces, or a transcript's words), each
    with the index of its word. Runs of two or more single capital or dotted letters are joined
    (``G P U`` → ``gpu``, the way ``GPU`` is written)."""
    raw: list[tuple[str, bool, int]] = []
    for index, word in enumerate(words):
        raw += [(text, letter, index) for text, letter in _word_tokens(word, language) if text]
    out: list[Token] = []
    i = 0
    while i < len(raw):
        j = i
        while j < len(raw) and raw[j][1]:
            j += 1
        if j - i >= 2:
            out.append(Token("".join(t for t, _, _ in raw[i:j]), raw[i][2]))
            i = j
            continue
        out.append(Token(raw[i][0], raw[i][2]))
        i += 1
    return out


def normalize_text(text: str, language: str | None = None) -> list[str]:
    """The normalised words of ``text`` (:func:`normalize_words` of its space-separated words)."""
    return [t.text for t in normalize_words(text.split(), language)]
