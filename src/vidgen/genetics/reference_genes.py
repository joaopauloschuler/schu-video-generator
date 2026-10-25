"""Real human coding sequences for the ``mutation`` scene (DESIGN.md §96.13), with the textbook
variants that lie in them. Each is a window of the reference coding sequence (c. numbering of the
RefSeq transcript named), its coding exons as c. ranges (around the window), the CDS length, and
known variants in HGVS form with their legacy names. A test translates every window and checks it
against the protein. No manim.

- **HBB** (β-globin, NM_000518.5; 147 residues with the initiator Met, CDS 444 nt; exons c.1–92,
  c.93–315, c.316–444): c.1–150 (codons 1–50). Sickle-cell haemoglobin HbS c.20A>T p.(Glu7Val) —
  legacy Glu6Val (β6, the mature globin numbered without Met); HbC c.19G>A p.(Glu7Lys); HbE c.79G>A
  p.(Glu27Lys); β⁰-thalassaemia codon 39 nonsense c.118C>T p.(Gln40*); IVS-I-1 c.92+1G>A.
- **CFTR** (NM_000492.4; 1480 residues, CDS 4443 nt): c.1516–1680 (codons 506–560) in exons 11
  (c.1393–1584), 12 (c.1585–1679) and 13 (c.1680–1766). F508del c.1521_1523del p.(Phe508del)
  (legacy ΔF508; the CTT removed spans codons 507 and 508, ATC TTT → ATT: Ile507 stays), G542X
  c.1624G>T p.(Gly542*), G551D c.1652G>A p.(Gly551Asp), R553X c.1657C>T p.(Arg553*), 1717-1G>A
  c.1585-1G>A (acceptor of intron 11).
- **GJB2** (connexin 26, NM_004004.6; 226 residues, CDS 681 nt, all in exon 2): c.1–66. The
  common deafness allele c.35del p.(Gly12Valfs*2) (legacy 35delG; one G of the six at c.30–35,
  written at the 3′-most)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .hgvs import CodingSequence, coding_sequence


@dataclass(frozen=True)
class KnownVariant:
    c: str
    p: str
    legacy: str
    note: str = ""


@dataclass(frozen=True)
class ReferenceGene:
    symbol: str
    product: str
    transcript: str
    seq: str
    first: int
    exons: tuple[tuple[int, int], ...]
    first_exon: int
    length: int
    protein: str            # the window's residues (one-letter), for the test
    variants: tuple[KnownVariant, ...]

    def coding(self, where: str = "gene") -> CodingSequence:
        return coding_sequence(self.seq, where, self.first, [list(e) for e in self.exons], self.length, self.symbol,
                               first_exon=self.first_exon)


_HBB = ("ATGGTGCATCTGACTCCTGAGGAGAAGTCTGCCGTTACTGCCCTGTGGGGCAAGGTGAACGTGGATGAAGTTGGTGGTGAGGCCCTGGGCAGG"
        "CTGCTGGTGGTCTACCCTTGGACCCAGAGGTTCTTTGAGTCCTTTGGGGATCTGTCC")
_CFTR = ("ATCATCTTTGGTGTTTCCTATGATGAATATAGATACAGAAGCGTCATCAAAGCATGCCAACTAGAAGAGGACATCTCCAAGTTTGCAGAGAAAGACAATATAGTTCTT"
         "GGAGAAGGTGGAATCACACTGAGTGGAGGTCAACGAGCAAGAATTTCTTTAGCAAGA")
_GJB2 = "ATGGATTGGGGCACGCTGCAGACGATCCTGGGGGGTGTGAACAAACACTCCACCAGCATTGGAAAG"

REFERENCE_GENES: dict[str, ReferenceGene] = {
    "HBB": ReferenceGene(
        "HBB", "β-globin", "NM_000518.5", _HBB, 1, ((1, 92), (93, 315), (316, 444)), 1, 444,
        "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLS",
        (KnownVariant("c.20A>T", "p.(Glu7Val)", "HbS, β6 Glu→Val (Glu6Val)", "sickle-cell anaemia (homozygous)"),
         KnownVariant("c.19G>A", "p.(Glu7Lys)", "HbC, Glu6Lys"),
         KnownVariant("c.79G>A", "p.(Glu27Lys)", "HbE, Glu26Lys"),
         KnownVariant("c.118C>T", "p.(Gln40*)", "codon 39 C>T (Gln39Ter), β⁰-thalassaemia"),
         KnownVariant("c.92+1G>A", "p.?", "IVS-I-1 (G>A), β⁰-thalassaemia"))),
    "CFTR": ReferenceGene(
        "CFTR", "CFTR", "NM_000492.4", _CFTR, 1516, ((1393, 1584), (1585, 1679), (1680, 1766)), 11, 4443,
        "IIFGVSYDEYRYRSVIKACQLEEDISKFAEKDNIVLGEGGITLSGGQRARISLAR",
        (KnownVariant("c.1521_1523del", "p.(Phe508del)", "ΔF508", "the commonest cystic fibrosis allele"),
         KnownVariant("c.1624G>T", "p.(Gly542*)", "G542X"),
         KnownVariant("c.1652G>A", "p.(Gly551Asp)", "G551D", "a gating variant"),
         KnownVariant("c.1657C>T", "p.(Arg553*)", "R553X"),
         KnownVariant("c.1585-1G>A", "p.?", "1717-1G>A"))),
    "GJB2": ReferenceGene(
        "GJB2", "connexin 26", "NM_004004.6", _GJB2, 1, ((1, 681),), 2, 681,
        "MDWGTLQTILGGVNKHSTSIGK",
        (KnownVariant("c.35del", "p.(Gly12Valfs*2)", "35delG", "the commonest recessive deafness allele in Europe"),)),
}


def known_variant(symbol: str, c: str) -> KnownVariant | None:
    """The textbook variant of ``symbol`` written ``c`` (deleted bases after del ignored)."""
    gene = REFERENCE_GENES.get(symbol)
    if gene is None:
        return None
    key = _bare(c)
    return next((v for v in gene.variants if _bare(v.c) == key), None)


def _bare(c: str) -> str:
    return re.sub(r"(del|dup)[ACGT]+$", r"\1", c.strip())


__all__ = ["REFERENCE_GENES", "KnownVariant", "ReferenceGene", "known_variant"]
