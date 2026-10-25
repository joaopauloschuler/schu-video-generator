"""The plan of a ``mutation`` scene (DESIGN.md §96.13): the coding sequence (a reference gene's
window, an author's sequence, or a gene built by ``cellworld.expression`` from the ``gene:`` param
of the molecule scene) and each variant worked out by :mod:`vidgen.genetics.hgvs` — its HGVS ``c.``
form checked, the protein consequence computed, an author's ``p.`` checked against it, a legacy
name. No manim."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from vidgen.errors import VidgenError

from ..cellworld.expression import GeneSpec, build_gene
from ..cellworld.model import did_you_mean
from ..cellworld.names import check_gene
from . import hgvs
from .reference_genes import REFERENCE_GENES, known_variant

SPLICE_MODES = ("auto", "skip", "retain")
#: The longest coding sequence drawn from a generated gene (codons).
MAX_CODONS = 200


@dataclass(frozen=True)
class VariantView:
    """A variant of the scene: its consequence, the ``p.`` text shown, a legacy name, a note."""

    consequence: hgvs.Consequence
    p_text: str
    legacy: str | None
    note: str | None

    @property
    def c_text(self) -> str:
        return self.consequence.dna.shown


@dataclass(frozen=True)
class MutationPlan:
    cds: hgvs.CodingSequence
    symbol: str | None
    species: str
    product: str | None
    transcript: str | None
    variants: tuple[VariantView, ...]
    style: str
    stop: str

    def touched_codons(self) -> list[int]:
        """The codon numbers the variants change (an action target each): the residues of the
        protein change, or the codon the DNA change lies in."""
        out: set[int] = set()
        for v in self.variants:
            pc = v.consequence.protein
            edit = v.consequence.edit
            if pc.start is not None and pc.kind not in ("splice_donor", "splice_acceptor", "intronic", "unknown"):
                out.update(range(pc.start, (pc.end or pc.start) + 1))
            elif edit is not None:
                out.add(self.cds.codon_number(self.cds.first + edit.start))
        lo, hi = self.codon_range()
        return sorted(n for n in out if lo <= n <= hi)

    def codon_range(self) -> tuple[int, int]:
        """The first and last whole codon of the window."""
        a = self.cds.codon_number(self.cds.first + self.cds.frame_start)
        n = (len(self.cds.seq) - self.cds.frame_start) // 3
        return a, a + n - 1


def _coding_from_gene(spec: dict[str, Any], where: str) -> tuple[hgvs.CodingSequence, str | None]:
    """The CDS of a gene written as the molecule scene's ``gene:`` (sequence with intron positions,
    or a protein / number of codons generated), with its coding exons and introns in c. numbers."""
    allowed = ("name", "sequence", "introns", "protein", "codons", "seed", "cell")
    for key in spec:
        if key not in allowed:
            raise VidgenError(f"{where}: unknown key '{key}'{did_you_mean(key, list(allowed))} (keys: {', '.join(allowed)})")
    introns = spec.get("introns")
    if isinstance(introns, list):
        introns = tuple((int(a), int(b)) for a, b in introns)
    gene = build_gene(GeneSpec(spec.get("name"), spec.get("sequence"), introns, spec.get("protein"), spec.get("codons"), None, None,
                               int(spec.get("seed", 1)), str(spec.get("cell", "animal")), where))
    orf0 = gene.orf_start
    cds = gene.mature[orf0:gene.orf_end].replace("U", "T")
    if len(cds) > 3 * MAX_CODONS:
        raise VidgenError(f"{where}: the coding sequence has {len(cds) // 3} codons; a mutation scene draws at most {MAX_CODONS}")
    exons: list[list[int]] = []
    numbers: list[int] = []
    introns_seq: list[str] = []
    offset = 0
    regions = gene.exons()
    for k, (a, b) in enumerate(regions):
        lo, hi = offset, offset + (b - a)          # mature indices [lo, hi)
        offset = hi
        c_lo, c_hi = max(lo, orf0) - orf0 + 1, min(hi, gene.orf_end) - orf0
        if c_lo <= c_hi:
            if exons:
                intr = gene.introns[k - 1]
                introns_seq.append(gene.region[intr.start:intr.end])
            exons.append([c_lo, c_hi])
            numbers.append(k + 1)
    return hgvs.coding_sequence(cds, where, 1, exons, len(cds), spec.get("name"), tuple(introns_seq), numbers[0] if numbers else 1), \
        spec.get("name")


def _variant_items(value: Any, where: str) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else [value]
    out = []
    for k, item in enumerate(items):
        at = f"{where}[{k}]" if isinstance(value, list) else where
        if isinstance(item, str):
            parts = item.split()
            entry: dict[str, Any] = {"c": parts[0]}
            if len(parts) == 2 and parts[1].startswith("p."):
                entry["p"] = parts[1]
            elif len(parts) > 1:
                raise VidgenError(f"{at}: '{item}': write the DNA change, optionally followed by its protein change "
                                  f"('c.20A>T p.(Glu7Val)')")
            out.append(entry)
        elif isinstance(item, dict):
            for key in item:
                if key not in ("c", "p", "legacy", "note", "splice"):
                    raise VidgenError(f"{at}: unknown key '{key}'{did_you_mean(key, ['c', 'p', 'legacy', 'note', 'splice'])} "
                                      f"(c, p, legacy, note, splice)")
            if "c" not in item:
                raise VidgenError(f"{at}: give the DNA change as c: (c: c.20A>T)")
            out.append(dict(item))
        else:
            raise VidgenError(f"{at}: give 'c.20A>T' or {{c: c.20A>T, p: p.(Glu7Val), legacy: Glu6Val}}")
    if not out:
        raise VidgenError(f"{where}: give at least one variant")
    if len(out) > 6:
        raise VidgenError(f"{where}: {len(out)} variants; a scene shows at most 6 (one after another on the same sequence)")
    return out


def build_mutation_plan(spec: dict[str, Any]) -> MutationPlan:
    """The plan from the scene's params (``gene`` a reference symbol or a gene mapping, or
    ``sequence`` with ``first`` / ``exons`` / ``length``; ``variant``; ``splice``; ``codes``;
    ``stop``; ``symbol``; ``species``)."""
    species = str(spec.get("species") or "human")
    gene = spec.get("gene")
    seq = spec.get("sequence")
    reference = None
    transcript = product = None
    if gene is not None and seq is not None:
        raise VidgenError("give gene (a reference gene or a gene mapping) or sequence, not both")
    if isinstance(gene, str):
        reference = REFERENCE_GENES.get(gene)
        if reference is None:
            raise VidgenError(f"gene: '{gene}' is not a reference sequence here{did_you_mean(gene, list(REFERENCE_GENES))} "
                              f"({', '.join(REFERENCE_GENES)}); give your own coding sequence with sequence: (and first:, exons:)")
        for key in ("first", "exons", "length", "first_exon"):
            if spec.get(key) is not None:
                raise VidgenError(f"{key}: the reference gene {gene} brings its own window and exons; leave {key} out")
        cds = reference.coding("gene")
        symbol: str | None = reference.symbol
        transcript, product = reference.transcript, reference.product
    elif isinstance(gene, dict):
        cds, symbol = _coding_from_gene(gene, "gene")
    elif seq is not None:
        cds = hgvs.coding_sequence(str(seq), "sequence", int(spec.get("first") or 1), spec.get("exons"), spec.get("length"),
                                   spec.get("symbol"), first_exon=int(spec.get("first_exon") or 1))
        symbol = spec.get("symbol")
    else:
        raise VidgenError("give the coding sequence: gene: HBB (a reference window: " + ", ".join(REFERENCE_GENES)
                          + "), sequence: ATGGTG… (coding DNA from c.1, or from first:), or gene: {protein: MVHLTPEEK…, introns: 1}")
    if spec.get("symbol") is not None:
        symbol = str(spec["symbol"])
    if symbol is not None:
        check_gene(symbol, species, "symbol")
    first_codon = cds.codon_number(cds.first + cds.frame_start)
    if (len(cds.seq) - cds.frame_start) // 3 < 2:
        raise VidgenError("sequence: give at least two whole codons")
    style = str(spec.get("codes") or "three")
    stop = str(spec.get("stop") or "*")
    default_splice = str(spec.get("splice") or "auto")
    if default_splice not in SPLICE_MODES:
        raise VidgenError(f"splice: '{default_splice}'{did_you_mean(default_splice, list(SPLICE_MODES))} ({', '.join(SPLICE_MODES)})")
    if spec.get("variant") is None:
        raise VidgenError("variant: give the change in HGVS form (variant: c.20A>T, or a list of them)")
    views = []
    items = _variant_items(spec["variant"], "variant")
    for k, item in enumerate(items):
        where = f"variant[{k}]" if len(items) > 1 else "variant"
        mode = str(item.get("splice", default_splice))
        if mode not in SPLICE_MODES:
            raise VidgenError(f"{where}: splice: '{mode}' ({', '.join(SPLICE_MODES)})")
        try:
            cons = hgvs.consequence(cds, str(item["c"]), where, mode)
        except VidgenError as error:
            raise VidgenError(str(error) if str(error).startswith(where) else f"{where}: {error}") from None
        stated = item.get("p")
        p_style, p_stop = style, stop
        if stated is not None:
            parsed = hgvs.parse_p(str(stated), f"{where}: p")
            computed_text = cons.protein.text(style, stop)
            hgvs.check_stated(parsed, cons.protein, str(stated), computed_text, cons.wt_protein, first_codon, f"{where}: p")
            if "Ter" in str(stated):
                p_stop = "Ter"
            if not any(c.islower() for c in str(stated)[2:]) and cons.protein.kind not in ("splice_donor", "splice_acceptor", "intronic"):
                p_style = "one"
        legacy = item.get("legacy")
        if legacy is None and reference is not None:
            known = known_variant(reference.symbol, str(item["c"]))
            legacy = known.legacy if known is not None else None
        views.append(VariantView(cons, cons.protein.text(p_style, p_stop), legacy, item.get("note")))
    seen = [v.consequence.dna.text() for v in views]
    for k, t in enumerate(seen):
        if t in seen[:k]:
            raise VidgenError(f"variant[{k}]: {t} is listed twice")
    return MutationPlan(cds, symbol, species, product, transcript, tuple(views), style, stop)


@lru_cache(maxsize=64)
def _cached(key: str) -> MutationPlan:
    return build_mutation_plan(json.loads(key))


def plan_mutation(spec: dict[str, Any]) -> MutationPlan:
    """:func:`build_mutation_plan`, cached by the params' JSON."""
    return _cached(json.dumps(spec, sort_keys=True, default=str))


__all__ = ["MAX_CODONS", "SPLICE_MODES", "MutationPlan", "VariantView", "build_mutation_plan", "plan_mutation"]
