"""Naming conventions as data (DESIGN.md §95.9), so validation and the accuracy lint (Step 209)
use one table: gene symbols in italics, protein names in roman type, the case each species'
nomenclature committee prescribes (human HGNC: *TP53* / TP53 or p53; mouse MGI: *Trp53* /
TRP53; budding yeast SGD: *CDC28* / Cdc28 or Cdc28p; *E. coli*: *lacZ* / LacZ…); markers of
post-translational modifications (P, Ub, Ac, Me) with the residues they go on; histone marks
(``H3K4me3``) checked against the histone sequences. No manim."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape

from vidgen.errors import VidgenError

from .model import did_you_mean


@dataclass(frozen=True)
class Species:
    """A species' gene and protein nomenclature: regular expressions a gene symbol and a
    protein symbol match, the rule in words, examples, and the committee that sets it."""

    name: str
    label: str
    gene: str
    gene_rule: str
    gene_example: str
    protein: str
    protein_rule: str
    protein_example: str
    source: str


SPECIES: dict[str, Species] = {s.name: s for s in (
    Species("human", "human", r"^[A-Z][A-Z0-9-]*(orf[0-9]+)?$", "human gene symbols are italic capitals", "TP53",
            r"^[A-Z][A-Z0-9-]*$", "human protein symbols are roman capitals (or a common name such as p53)", "TP53", "HGNC"),
    Species("mouse", "mouse", r"^[A-Z][a-z0-9-]*$", "mouse gene symbols are italic with only the first letter a capital", "Trp53",
            r"^[A-Z][A-Z0-9-]*$", "mouse protein symbols are roman capitals (or a common name such as p53)", "TRP53", "MGI"),
    Species("rat", "rat", r"^[A-Z][a-z0-9-]*$", "rat gene symbols are italic with only the first letter a capital", "Tp53",
            r"^[A-Z][A-Z0-9-]*$", "rat protein symbols are roman capitals", "TP53", "RGD"),
    Species("yeast", "budding yeast (S. cerevisiae)", r"^[A-Z]{3}[0-9]+$", "budding-yeast gene symbols are three italic capitals and a number "
            "(a recessive mutant allele is lowercase: cdc28)", "CDC28",
            r"^[A-Z][a-z]{2}[0-9]+p?$", "budding-yeast proteins are roman with a capital first letter, often with a p", "Cdc28", "SGD"),
    Species("fission_yeast", "fission yeast (S. pombe)", r"^[a-z]{3}[0-9]+(\+)?$", "fission-yeast gene symbols are three italic lowercase letters "
            "and a number", "cdc2", r"^[A-Z][a-z]{2}[0-9]+$", "fission-yeast proteins are roman with a capital first letter", "Cdc2", "PomBase"),
    Species("fly", "fruit fly (Drosophila)", r"^[A-Za-z][A-Za-z0-9-]*$", "Drosophila gene symbols are italic (lowercase when named after a "
            "recessive mutant: w, dpp; a capital after a dominant one: N)", "dpp",
            r"^[A-Za-z][A-Za-z0-9-]*$", "Drosophila proteins are roman, usually with a capital first letter", "Dpp", "FlyBase"),
    Species("zebrafish", "zebrafish", r"^[a-z][a-z0-9.-]*$", "zebrafish gene symbols are italic lowercase", "tp53",
            r"^[A-Z][a-z0-9.-]*$", "zebrafish proteins are roman with a capital first letter", "Tp53", "ZFIN"),
    Species("e_coli", "E. coli", r"^[a-z]{3}[A-Z]?$", "E. coli gene symbols are three italic lowercase letters, then a capital for the "
            "gene of an operon", "lacZ", r"^[A-Z][a-z]{2}[A-Z]?$", "E. coli proteins are roman with a capital first letter", "LacZ",
            "Demerec (1966)"),
    Species("arabidopsis", "Arabidopsis", r"^[A-Z][A-Z0-9]*$", "Arabidopsis gene symbols are italic capitals (mutant alleles lowercase)", "AG",
            r"^[A-Z][A-Z0-9]*$", "Arabidopsis protein symbols are roman capitals", "AG", "TAIR"),
)}
def species(name: str, where: str) -> Species:
    """The species ``name`` (``human``, ``mouse``…), or an error naming the known ones."""
    if name not in SPECIES:
        raise VidgenError(f"{where}: species '{name}': use {', '.join(SPECIES)}{did_you_mean(name, list(SPECIES))}")
    return SPECIES[name]


def check_gene(symbol: str, species_name: str, where: str) -> str:
    """``symbol`` when it is a gene symbol of the species' form, else a :class:`VidgenError` with
    the rule and how this symbol is written (``Trp53``, not ``TRP53``)."""
    sp = species(species_name, where)
    if re.match(sp.gene, symbol):
        return symbol
    hint = ""
    if species_name in ("mouse", "rat") and symbol[:1].isalpha():
        hint = f": write {symbol[0].upper()}{symbol[1:].lower()}"
    elif species_name in ("human", "arabidopsis", "yeast"):
        hint = f": write {symbol.upper()}"
    elif species_name in ("zebrafish", "fission_yeast"):
        hint = f": write {symbol.lower()}"
    raise VidgenError(f"{where}: gene '{symbol}': {sp.gene_rule} ({sp.source}; e.g. {sp.gene_example}){hint}")


#: Species whose case alone tells a gene symbol from a protein symbol (yeast CDC28 / Cdc28,
#: E. coli lacZ / LacZ, zebrafish tp53 / Tp53).
_CASE_CODED = ("yeast", "fission_yeast", "zebrafish", "e_coli")


def check_protein(name: str, species_name: str, where: str, gene: str | None = None) -> str:
    """``name`` when it is a protein symbol of the species' form or a common name (``p53``,
    ``cyclin B1``, ``Gαs``); refuses a protein written like its gene: the ``gene`` symbol
    itself where the case differs (mouse gene *Trp53*, protein TRP53), or the gene form in a
    species whose case alone tells them apart (yeast ``CDC28`` is the gene, Cdc28 the protein)."""
    sp = species(species_name, where)
    if re.match(sp.protein, name):
        return name
    like_gene = (gene is not None and name == gene) or (species_name in _CASE_CODED and re.match(sp.gene, name) is not None)
    if like_gene and species_name != "fly":
        fix = {"mouse": name.upper(), "rat": name.upper(), "e_coli": name[:1].upper() + name[1:]}.get(species_name, name[:1].upper() + name[1:].lower())
        raise VidgenError(f"{where}: protein '{name}' is written like the {sp.label} gene (italic {name}); "
                          f"{sp.protein_rule} ({sp.source}): write {fix}")
    return name                          # a common name (p53, cyclin B1, Gαs)


def gene_markup(symbol: str, species_name: str, where: str) -> str:
    """The gene symbol checked and in italics (Pango markup): ``<i>TP53</i>``."""
    return f"<i>{escape(check_gene(symbol, species_name, where), quote=False)}</i>"


def protein_markup(name: str, species_name: str, where: str, gene: str | None = None) -> str:
    """The protein name checked and in roman type (Pango markup, Greek letters kept)."""
    return escape(check_protein(name, species_name, where, gene), quote=False)


#: A symbol followed by one of these words names the protein (the EGFR receptor), not the gene.
PROTEIN_WORDS = frozenset({"protein", "proteins", "kinase", "kinases", "receptor", "receptors", "enzyme", "enzymes", "channel",
                           "channels", "transporter", "transporters", "factor", "factors", "phosphatase", "inhibitor", "inhibitors"})


def gene_spans(text: str, symbols: list[str] | tuple[str, ...] | set[str] | frozenset[str]) -> list[tuple[int, int]]:
    """``(start, end)`` of each place plain ``text`` writes one of the gene ``symbols`` (whole
    word, as written: case matters, *Trp53* is not TRP53), to be set in italics — except where
    the next word makes it the protein (``SERPINA1 protein``, ``EGFR kinase``); in text order,
    longer symbols first where they overlap."""
    taken: list[tuple[int, int]] = []
    for symbol in sorted({s for s in symbols if s}, key=len, reverse=True):
        for m in re.finditer(rf"(?<![\w-]){re.escape(symbol)}(?![\w-])", text):
            after = re.match(r"[’']?s?\s+([A-Za-z]+)", text[m.end():])
            if after is not None and after.group(1).lower() in PROTEIN_WORDS:
                continue
            if all(m.end() <= a or m.start() >= b for a, b in taken):
                taken.append(m.span())
    return sorted(taken)


# ----- modifications ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Modification:
    """A post-translational modification marker: its ``mark`` (drawn in a small disc), name,
    the residues it goes on (one-letter codes) and the histone-mark suffixes that mean it."""

    mark: str
    name: str
    residues: str
    note: str
    hue: str
    suffixes: tuple[str, ...]


MODIFICATIONS: dict[str, Modification] = {m.mark: m for m in (
    Modification("P", "phosphorylation", "STYHD", "on Ser, Thr or Tyr (His and Asp in bacterial two-component systems)", "#E8B730", ("ph",)),
    Modification("Ub", "ubiquitination", "KM", "on Lys (or the N-terminal Met1 of linear chains)", "#5DA35A", ("ub", "ub1")),
    Modification("Ac", "acetylation", "KMSAT", "on Lys (or a protein's N-terminal residue)", "#4A8FD4", ("ac",)),
    Modification("Me", "methylation", "KR", "on Lys (mono-, di- or trimethyl) or Arg (mono- or dimethyl)", "#B5629B", ("me1", "me2", "me3", "me")),
)}
_THREE = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L",
          "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V"}
_ONE_TO_THREE = {v: k for k, v in _THREE.items()}
#: Human histone sequences (the initiator Met removed, as histone numbering counts): H2A type 1,
#: H2B type 1-C, H3.1, H4 (UniProt P0C0S8, P62807, P68431, P62805).
HISTONES: dict[str, str] = {
    "H2A": "SGRGKQGGKARAKAKTRSSRAGLQFPVGRVHRLLRKGNYAERVGAGAPVYLAAVLEYLTAEILELAGNAARDNKKTRIIPRHLQLAIRNDEELNKLLGKVTIAQGGVLPNIQAVLLPKKTESHHKAKGK",
    "H2B": "PEPAKSAPAPKKGSKKAVTKAQKKDGKKRKRSRKESYSIYVYKVLKQVHPDTGISSKAMGIMNSFVNDIFERIAGEASRLAHYNKRSTITSREIQTAVRLLLPGELAKHAVSEGTKAVTKYTSSK",
    "H3": "ARTKQTARKSTGGKAPRKQLATKAARKSAPATGGVKKPHRYRPGTVALREIRRYQKSTELLIRKLPFQRLVREIAQDFKTDLRFQSSAVMALQEASEAYLVGLFEDTNLCAIHAKRVTIMPKDIQLARRIRGERA",
    "H4": "SGRGKGGKGLGKGGAKRHRKVLRDNIQGITKPAIRRLARRGGVKRISGLIYEETRGVLKVFLENVIRDAVTYTEHAKRKTVTAMDVVYALKRQGRTLYGFGG",
}


def residue(text: str, where: str) -> tuple[str, int]:
    """A residue written ``S15``, ``Ser15`` or ``K382``: ``(one-letter code, position)``."""
    m = re.match(r"^([A-Z][a-z]{2}|[A-Z])(\d+)$", text.strip())
    if m is None or (len(m.group(1)) == 3 and m.group(1) not in _THREE) or (len(m.group(1)) == 1 and m.group(1) not in _ONE_TO_THREE):
        raise VidgenError(f"{where}: residue '{text}': write an amino acid and its position, Ser15 or S15")
    code = _THREE.get(m.group(1), m.group(1))
    return code, int(m.group(2))


def check_modification(mark: str, at: str | None, where: str) -> tuple[Modification, tuple[str, int] | None]:
    """The marker ``mark`` (P, Ub, Ac, Me) on residue ``at`` (or on the protein as a whole),
    checked: phosphorylation is on Ser/Thr/Tyr (His/Asp in two-component systems), never on Lys;
    ubiquitin, acetyl on Lys; methyl on Lys or Arg."""
    if mark not in MODIFICATIONS:
        raise VidgenError(f"{where}: modification '{mark}': use {', '.join(MODIFICATIONS)}{did_you_mean(mark, list(MODIFICATIONS))}")
    mod = MODIFICATIONS[mark]
    if at is None:
        return mod, None
    code, position = residue(at, where)
    if code not in mod.residues:
        allowed = ", ".join(_ONE_TO_THREE[c] for c in mod.residues)
        raise VidgenError(f"{where}: {mod.name} ({mark}) is {mod.note}, not on {_ONE_TO_THREE[code]}{position} (residues: {allowed})")
    return mod, (code, position)


def histone_mark(text: str, where: str) -> tuple[str, str, int, Modification, int]:
    """A histone mark ``H3K4me3`` / ``H3K27ac`` / ``H3S10ph`` / ``H2AK119ub``: ``(histone, residue,
    position, modification, count)``, its residue checked against the histone's sequence
    (H3K27 is a lysine; ``H3S27ph`` is refused) and the modification against the residue."""
    m = re.match(r"^(H2A|H2B|H3|H4)([A-Z])(\d+)(me[123]?|ac|ph|ub1?)$", text)
    if m is None:
        raise VidgenError(f"{where}: histone mark '{text}': write histone, residue, position and mark: H3K4me3, H3K27ac, H3S10ph, H2AK119ub")
    histone, code, pos, suffix = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    seq = HISTONES[histone]
    if not 1 <= pos <= len(seq):
        raise VidgenError(f"{where}: histone mark '{text}': {histone} has {len(seq)} residues")
    real = seq[pos - 1]
    if real != code:
        raise VidgenError(f"{where}: histone mark '{text}': residue {pos} of {histone} is {_ONE_TO_THREE[real]} ({real}), not {code}")
    mod = next(mo for mo in MODIFICATIONS.values() if suffix in mo.suffixes)
    if code not in mod.residues:
        raise VidgenError(f"{where}: histone mark '{text}': {mod.name} is {mod.note}")
    count = int(suffix[2]) if suffix.startswith("me") and len(suffix) == 3 else 1
    if code == "R" and count == 3:
        raise VidgenError(f"{where}: histone mark '{text}': arginine is mono- or dimethylated, not trimethylated")
    return histone, code, pos, mod, count


__all__ = ["HISTONES", "MODIFICATIONS", "PROTEIN_WORDS", "SPECIES", "Modification", "Species", "check_gene", "check_modification",
           "check_protein", "gene_markup", "gene_spans", "histone_mark", "protein_markup", "residue", "species"]
