"""Nucleic-acid sequences (DESIGN.md §95.9): alphabets of DNA and RNA, complements (the
partner strand runs antiparallel: written 5′→3′ it is the reverse complement), the standard
genetic code and how a tRNA's anticodon reads codons (Crick's wobble at the anticodon's first,
5′ base). No manim."""

from __future__ import annotations

from vidgen.errors import VidgenError

from .model import did_you_mean

DNA_BASES, RNA_BASES = "ACGT", "ACGU"
_PAIR = {"A": "T", "T": "A", "G": "C", "C": "G", "U": "A"}
_RNA_PAIR = {"A": "U", "U": "A", "G": "C", "C": "G"}
#: The standard genetic code (NCBI table 1), codons in TCAG order.
_CODE = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODONS: dict[str, str] = {a + b + c: _CODE[16 * i + 4 * j + k] for i, a in enumerate("UCAG") for j, b in enumerate("UCAG") for k, c in enumerate("UCAG")}
AMINO_ACIDS: dict[str, str] = {"A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "Q": "Gln", "E": "Glu", "G": "Gly", "H": "His",
                               "I": "Ile", "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro", "S": "Ser", "T": "Thr", "W": "Trp",
                               "Y": "Tyr", "V": "Val"}
_THREE_TO_ONE = {v.lower(): k for k, v in AMINO_ACIDS.items()}
#: What an anticodon's first (wobble) base reads at a codon's third position (Crick 1966; I is
#: inosine, made from A in many tRNAs).
WOBBLE = {"G": "CU", "U": "AG", "I": "UCA", "C": "G", "A": "U"}


def check_sequence(seq: str, kind: str, where: str) -> str:
    """``seq`` upper-cased, when it is DNA (``ACGT``) or RNA (``ACGU``) as ``kind`` says; a
    :class:`VidgenError` names the first wrong letter (U in DNA, T in RNA)."""
    alphabet = DNA_BASES if kind == "dna" else RNA_BASES
    text = seq.replace(" ", "").upper()
    for k, base in enumerate(text):
        if base not in alphabet:
            hint = " (DNA has T where RNA has U)" if base in "TU" else ""
            raise VidgenError(f"{where}: sequence '{seq}': '{base}' at {k + 1} is not a {kind.upper()} base ({', '.join(alphabet)}){hint}")
    if not text:
        raise VidgenError(f"{where}: sequence is empty")
    return text


def complement(seq: str) -> str:
    """The partner of each DNA base, in the same order (read 3′→5′ under ``seq``)."""
    return "".join(_PAIR[b] for b in seq)


def reverse_complement(seq: str) -> str:
    """The partner strand written 5′→3′."""
    return complement(seq)[::-1]


def amino_acid(text: str, where: str) -> str:
    """An amino acid written ``Met``, ``met`` or ``M``: its one-letter code."""
    t = text.strip()
    if len(t) == 1 and t.upper() in AMINO_ACIDS:
        return t.upper()
    if t.lower() in _THREE_TO_ONE:
        return _THREE_TO_ONE[t.lower()]
    raise VidgenError(f"{where}: amino acid '{text}': write a three-letter code (Met, Phe, Gly…)"
                      f"{did_you_mean(t.capitalize(), list(AMINO_ACIDS.values()))}")


def codons_read(anticodon: str) -> list[str]:
    """The codons (5′→3′) an anticodon (5′→3′, ``ACGUI``) reads: its 3′ base pairs with the
    codon's first, its middle with the middle, its 5′ (wobble) base with the codon's third as
    :data:`WOBBLE` allows."""
    a1, a2, a3 = anticodon
    first, second = _RNA_PAIR[a3], _RNA_PAIR[a2]
    return [first + second + third for third in WOBBLE[a1]]


def check_trna(anticodon: str, amino: str | None, where: str) -> tuple[str, str | None]:
    """A tRNA's anticodon (three of ``ACGUI``, 5′→3′) and the amino acid it carries, checked
    against the genetic code: the anticodon must read a codon of that amino acid (``CAU`` reads
    AUG, Met). ``(anticodon, one-letter amino acid)``."""
    text = anticodon.replace(" ", "").upper()
    if len(text) != 3 or any(b not in "ACGUI" for b in text) or "I" in text[1:]:
        raise VidgenError(f"{where}: anticodon '{anticodon}': three RNA bases written 5′→3′ (A, C, G, U; I only at the first, wobble place)")
    if amino is None:
        return text, None
    code = amino_acid(amino, where)
    read = codons_read(text)
    coded = {c: CODONS[c] for c in read}
    if code not in coded.values():
        shown = ", ".join(f"{c} ({AMINO_ACIDS.get(a, 'stop') if a != '*' else 'stop'})" for c, a in coded.items())
        raise VidgenError(f"{where}: anticodon 5′-{text}-3′ reads the codons {shown}, none of them {AMINO_ACIDS[code]}; "
                          f"the anticodon pairs antiparallel with its codon (its 3′ base with the codon's 5′ base)")
    return text, code


__all__ = ["AMINO_ACIDS", "CODONS", "DNA_BASES", "RNA_BASES", "WOBBLE", "amino_acid", "check_sequence", "check_trna", "codons_read",
           "complement", "reverse_complement"]
