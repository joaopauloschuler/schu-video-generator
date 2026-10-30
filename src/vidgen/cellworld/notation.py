"""Chemical notation for labels (DESIGN.md §95.9): ions and small molecules typeset with their
charges as superscripts and counts as subscripts — ``Ca2+`` is Ca²⁺, ``Cl-`` is Cl⁻, ``H2O`` is
H₂O, ``Pi`` is Pᵢ, ``F_o`` is Fₒ — as Pango markup (what schu-video-generator's text pipeline draws:
``<sup>``, ``<sub>``, ``<i>``) and as plain Unicode for places without markup (the video
description, error messages). No manim."""

from __future__ import annotations

import re
from html import escape

from vidgen.errors import VidgenError

#: Names of ions and small molecules with a fixed typesetting (what ``chem_markup`` gives them).
SPECIAL: dict[str, tuple[str, str]] = {
    "Pi": ("P<sub>i</sub>", "Pᵢ"),
    "PPi": ("PP<sub>i</sub>", "PPᵢ"),
    "F_o": ("F<sub>o</sub>", "Fₒ"),
    "F_1": ("F<sub>1</sub>", "F₁"),
    "NAD+": ("NAD<sup>+</sup>", "NAD⁺"),
    "NADP+": ("NADP<sup>+</sup>", "NADP⁺"),
    "Na+/K+-ATPase": ("Na<sup>+</sup>/K<sup>+</sup>-ATPase", "Na⁺/K⁺-ATPase"),
    "Gbg": ("Gβγ", "Gβγ"),
    "Ga": ("Gα", "Gα"),
}
_SUPER = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
#: An element symbol with its count, then a charge: ``Ca``, ``H2``, ``O``; ``2+``, ``-``.
_FORMULA = re.compile(r"^((?:[A-Z][a-z]?\d*|\((?:[A-Z][a-z]?\d*)+\)\d*)+)(?:\s?(\d*)([+\-−]))?$")
_PART = re.compile(r"([A-Z][a-z]?|\(|\))(\d*)")


def _formula(text: str) -> tuple[str, str] | None:
    m = _FORMULA.match(text)
    if m is None:
        return None
    body, count, sign = m.group(1), m.group(2) or "", m.group(3)
    single = re.match(r"^([A-Z][a-z]?)(\d+)$", body)
    if sign and not count and single:
        # a monatomic ion's digits are its charge (Ca2+, Fe3+); a polyatomic one's are counts
        # (HCO3-), its charge written after a space (SO4 2-)
        body, count = single.group(1), single.group(2)
    markup, plain = "", ""
    for symbol, digits in _PART.findall(body):
        markup += symbol + (f"<sub>{digits}</sub>" if digits else "")
        plain += symbol + digits.translate(_SUB)
    if sign:
        sign = "−" if sign in "-−" else "+"
        number = "" if count in ("", "1") else count
        markup += f"<sup>{number}{sign}</sup>"
        plain += (number + ("-" if sign == "−" else "+")).translate(_SUPER)
    return markup, plain


def chem_markup(text: str) -> str:
    """Pango markup of a chemical name: ions and formulas with sub- and superscripts (``Ca2+``,
    ``Na+``, ``Cl-``, ``H2O``, ``CO2``, ``HCO3-``, ``Fe3+``), the special names (``Pi``,
    ``NAD+``, ``F_o``), anything else escaped as it is (``ATP``, ``cAMP``, ``glucose``)."""
    if text in SPECIAL:
        return SPECIAL[text][0]
    found = _formula(text)
    return found[0] if found is not None else escape(text, quote=False)


def chem_plain(text: str) -> str:
    """The same name in plain Unicode (``Ca²⁺``, ``H₂O``, ``Pᵢ``)."""
    if text in SPECIAL:
        return SPECIAL[text][1]
    found = _formula(text)
    return found[1] if found is not None else text


def charge_of(text: str) -> int:
    """The charge of an ion written ``Ca2+`` / ``Cl-`` (0 for a neutral name)."""
    m = _FORMULA.match(text)
    if m is None or not m.group(3):
        return 0
    count = m.group(2)
    single = re.match(r"^[A-Z][a-z]?(\d+)$", m.group(1))
    if not count and single:
        count = single.group(1)
    number = int(count) if count else 1
    return number if m.group(3) == "+" else -number


def check_markup(text: str, where: str) -> str:
    """``text`` when it is well-formed Pango markup of the tags labels use (``<i>``, ``<b>``,
    ``<sup>``, ``<sub>``, ``<span …>``), else a :class:`VidgenError` saying what is open."""
    stack: list[str] = []
    for m in re.finditer(r"<(/?)([a-z]+)[^>]*>", text):
        closing, tag = m.group(1) == "/", m.group(2)
        if tag not in ("i", "b", "sup", "sub", "span", "u", "small", "big", "tt", "s"):
            raise VidgenError(f"{where}: <{tag}> is not a text tag (use <i>, <b>, <sup>, <sub>, <span>)")
        if closing:
            if not stack or stack[-1] != tag:
                raise VidgenError(f"{where}: </{tag}> closes nothing open in '{text}'")
            stack.pop()
        else:
            stack.append(tag)
    if stack:
        raise VidgenError(f"{where}: <{stack[-1]}> is not closed in '{text}'")
    return text


__all__ = ["SPECIAL", "charge_of", "check_markup", "chem_markup", "chem_plain"]
