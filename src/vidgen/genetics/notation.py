"""Allele and genotype notation (DESIGN.md §96.3): allele symbols as authors write them in YAML
(``A``, ``a``, ``I^A``, ``i``, ``c^{ch}``, ``w^+``, ``+``), their canonical form, and the three
ways they are shown: plain text with Unicode superscripts (``Iᴬ``, ``w⁺``), Pango markup for
drawings (gene and allele symbols italic, chromosome letters X and Y roman) and the ASCII form.
No manim."""

from __future__ import annotations

import re
from html import escape

from vidgen.errors import VidgenError

#: An allele symbol: a base (letters and digits, or ``+``) and an optional superscript after
#: ``^`` (one run of letters, digits or ``+``, or any of those in braces: ``c^{ch}``).
SYMBOL_RE = re.compile(r"^(?:([A-Za-z][A-Za-z0-9]*)(?:\^(?:\{([A-Za-z0-9+-]+)\}|([A-Za-z0-9+-]+)))?|\+)$")

_SUPERSCRIPT = dict(zip(
    "ABDEGHIJKLMNOPRTUVWabcdefghijklmnoprstuvwxyz0123456789+-",
    "ᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻",
))

#: Letters that name the sex chromosomes (alleles only in systems without them: Mendel's Y / y).
CHROMOSOME_LETTERS = ("X", "Y")


def canonical_symbol(text: str, where: str) -> str:
    """The canonical form of an allele symbol (``c^{ch}`` → ``c^ch``; ``A`` stays ``A``), or a
    :class:`VidgenError` explaining the notation."""
    raw = str(text).strip()
    m = SYMBOL_RE.match(raw)
    if m is None:
        raise VidgenError(f"{where}: allele '{raw}': write a symbol such as A, a, I^A, c^{{ch}}, w^+ or + "
                          "(letters and digits, then an optional superscript after ^)")
    if raw == "+":
        return "+"
    base, sup = m.group(1), m.group(2) or m.group(3)
    if base in CHROMOSOME_LETTERS and sup:
        raise VidgenError(f"{where}: allele '{raw}': {base} names the {base} chromosome; write the allele alone ({sup}) and "
                          f"chromosome: {base} on its locus; genotypes then write it on its chromosome, {base}^{sup}")
    return f"{base}^{sup}" if sup else base


def split_symbol(symbol: str) -> tuple[str, str]:
    """``(base, superscript)`` of a canonical symbol: ``I^A`` → ``("I", "A")``, ``+`` → ``("+", "")``."""
    base, _, sup = symbol.partition("^")
    return base, sup


def is_wild_type_symbol(symbol: str) -> bool:
    """``+`` alone or a ``+`` superscript (``w^+``): the wild-type allele by convention."""
    return symbol == "+" or split_symbol(symbol)[1] == "+"


def superscript_text(text: str) -> str:
    """``text`` in Unicode superscript letters, or ``^text`` when one of its characters has none
    (C, F, Q, S, X, Y, Z and q have no superscript capital or letter in Unicode)."""
    if all(c in _SUPERSCRIPT for c in text):
        return "".join(_SUPERSCRIPT[c] for c in text)
    return f"^{text}" if len(text) == 1 else f"^({text})"


def symbol_text(symbol: str) -> str:
    """The allele as plain text with Unicode superscripts: ``Iᴬ``, ``w⁺``, ``cᶜʰ``, ``a``."""
    base, sup = split_symbol(symbol)
    return base + superscript_text(sup) if sup else base


def symbol_markup(symbol: str) -> str:
    """The allele in Pango markup, italic with its superscript: ``<i>I<sup>A</sup></i>``."""
    base, sup = split_symbol(symbol)
    sup_markup = f"<sup>{escape(sup, quote=False)}</sup>" if sup else ""
    return f"<i>{escape(base, quote=False)}{sup_markup}</i>"


def symbol_ascii(symbol: str) -> str:
    """The allele in the YAML form: ``I^A``, ``c^{ch}`` (braces around a superscript of several
    characters, so it reads back unambiguously)."""
    base, sup = split_symbol(symbol)
    if not sup:
        return base
    return f"{base}^{sup}" if len(sup) == 1 else f"{base}^{{{sup}}}"


def chromosome_text(letter: str, alleles: tuple[str, ...]) -> str:
    """A sex chromosome with the alleles it carries, as plain text: ``Xᴴ``, ``Y``, ``X^(H,b)``."""
    if not alleles:
        return letter
    if len(alleles) == 1:
        flat = alleles[0].replace("^", "")
        if all(c in _SUPERSCRIPT for c in flat):
            return letter + superscript_text(flat)
        return f"{letter}^{symbol_text(alleles[0])}"
    return f"{letter}^({','.join(symbol_text(a) for a in alleles)})"


def chromosome_markup(letter: str, alleles: tuple[str, ...]) -> str:
    """A sex chromosome in Pango markup: roman X or Y with the alleles as an italic superscript."""
    if not alleles:
        return letter
    inner = ",".join(symbol_markup(a) for a in alleles)
    return f"{letter}<sup>{inner}</sup>"


def chromosome_ascii(letter: str, alleles: tuple[str, ...]) -> str:
    """A sex chromosome in the YAML form: ``X^H``, ``X^{H,b}``, ``Y``."""
    if not alleles:
        return letter
    if len(alleles) == 1 and "^" not in alleles[0] and len(alleles[0]) == 1:
        return f"{letter}^{alleles[0]}"
    return f"{letter}^{{{','.join(symbol_ascii(a) for a in alleles)}}}"


__all__ = [
    "CHROMOSOME_LETTERS", "SYMBOL_RE", "canonical_symbol", "chromosome_ascii", "chromosome_markup", "chromosome_text",
    "is_wild_type_symbol", "split_symbol", "superscript_text", "symbol_ascii", "symbol_markup", "symbol_text",
]
