"""Gene expression as data and rules (DESIGN.md §95.11): a gene (promoter, transcribed region with
exons and introns, poly(A) signal), what each step of its expression makes of it and the order
those steps must come in. No manim.

- **The gene.** Written as the coding strand of its transcribed region (5′→3′ from the
  transcription start site, +1), or generated from a seed for a protein (``protein:``, one- or
  three-letter codes) or a number of codons; generated genes get a TATA box (−31 to −24) and an
  initiator round +1 (a bacterium: −35 TTGACA and −10 TATAAT boxes), a 5′ UTR ending in a Kozak
  context (GCCACC AUG G; a bacterium: a Shine–Dalgarno sequence AGGAGG 7 nt before the AUG),
  introns with GU…branch-point A…polypyrimidine tract…AG, a 3′ UTR with the poly(A) signal
  AAUAAA, a cleavage site (CA) 10–30 nt after it and a GU-rich downstream element.
- **Its products.** The pre-mRNA (U for T, cut at the cleavage site), the mature mRNA (exons
  joined), the open reading frame from the first AUG to the first in-frame stop (UAA, UAG, UGA)
  read with the standard genetic code (:data:`~vidgen.cellworld.sequences.CODONS`), the protein
  (N→C), a cleavable signal peptide (an N-terminal hydrophobic h-region of 7 or more residues
  and a cleavage site with small residues at −1 and −3; von Heijne 1983, 1986), N-glycosylation
  sequons (N-X-S/T, X not Pro).
- **The checks** (``VidgenError`` naming the place): bases, introns that do not start GU or end
  AG, lack a branch-point A 18–40 nt upstream of their 3′ end or are shorter than 30 nt, no
  start codon, no stop codon in frame, a stop codon before the end of the protein written, a
  premature stop more than 50 nt upstream of the last exon–exon junction (nonsense-mediated
  decay), introns in a bacterium.
- **The order of the steps** (:func:`step_problem`, :func:`advance`): transcribe → cap / splice
  / polyadenylate (on the pre-mRNA) → export (a capped, spliced, polyadenylated mRNA through a
  nuclear pore) → translate (only in the cytoplasm) → target_er (co-translational: SRP binds the
  signal peptide as it leaves the ribosome's exit tunnel) → glycosylate (in the ER lumen) →
  fold → to_golgi (only a folded protein leaves the ER) → secrete. Each refusal says why.

Numbers: Alberts (7th ed.) ch. 6 and 12, Lodish (9th ed.) ch. 5, 8 and 13: the transcription
bubble ~13 bp, the RNA–DNA hybrid 8–9 bp, RNA polymerase II 20–70 nt/s, capping at ~25 nt,
the exit tunnel ~30–40 residues long, ribosomes 2–6 residues per second (eukaryotes), the
oligosaccharide Glc₃Man₉GlcNAc₂ (14 sugars), a poly(A) tail of ~200 A (mammals)."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from functools import cached_property

from vidgen.errors import VidgenError

from .model import did_you_mean
from .sequences import AMINO_ACIDS, CODONS, amino_acid, check_sequence

#: Stop codons and the start codon.
STOP_CODONS, START_CODON = ("UAA", "UAG", "UGA"), "AUG"
#: Residues the ribosome's exit tunnel holds (~30–40): a signal peptide is free for SRP only
#: once this many residues follow it.
TUNNEL = 30
#: Residues from the ribosome's peptidyl transferase centre to the OST's active site in the ER
#: lumen (~65): a sequon's Asn is glycosylated co-translationally once it is this far out.
OST_REACH = 65
#: Capping happens when the nascent RNA is about this long (nt).
CAP_AT = 25
#: The transcription bubble (bp) and the RNA–DNA hybrid (bp).
BUBBLE, HYBRID = 13, 8
#: The shortest intron (nt) the spliceosome removes here, the branch point's window (nt from the
#: intron's 3′ end).
MIN_INTRON, BRANCH_WINDOW = 30, (18, 40)
#: A premature stop codon this far (nt) or more upstream of the last exon–exon junction makes
#: the mRNA a target of nonsense-mediated decay.
NMD_DISTANCE = 50
#: A poly(A) tail drawn (nt; ~200 in mammals) and the real length written beside it.
TAIL_DRAWN, TAIL_REAL = 12, 200
#: Gene lengths written by ``codons``.
CODONS_RANGE = (3, 160)
#: DNA drawn past the transcribed region (bp): room for the polymerase at its end.
DOWNSTREAM = 16
#: Amino acids by side chain (for colours and folding: the hydrophobic ones pack inside).
HYDROPHOBIC, POLAR, ACIDIC, BASIC, SPECIAL = set("AVLIMFWC"), set("STNQY"), set("DE"), set("KRH"), set("GP")
#: The steps, in the order they may come (a step may be left out).
STEPS = ("transcribe", "cap", "splice", "polyadenylate", "export", "translate", "target_er", "glycosylate", "fold", "to_golgi", "secrete")
#: Where a protein may end up (``secrete: to``).
DESTINATIONS = ("outside", "lysosome", "membrane")
#: Chaperones and the compartment each works in.
CHAPERONES = {"hsp70": "cytosol", "chaperonin": "cytosol", "bip": "er_lumen", "calnexin": "er_lumen"}

#: Codons used to write a protein back as a gene (frequent human codons, two per amino acid).
_BACK = {"A": ("GCC", "GCT"), "R": ("CGG", "AGG"), "N": ("AAC", "AAT"), "D": ("GAC", "GAT"), "C": ("TGC", "TGT"), "Q": ("CAG", "CAA"),
         "E": ("GAG", "GAA"), "G": ("GGC", "GGA"), "H": ("CAC", "CAT"), "I": ("ATC", "ATT"), "L": ("CTG", "CTC"), "K": ("AAG", "AAA"),
         "M": ("ATG", "ATG"), "F": ("TTC", "TTT"), "P": ("CCC", "CCT"), "S": ("AGC", "TCC"), "T": ("ACC", "ACA"), "W": ("TGG", "TGG"),
         "Y": ("TAC", "TAT"), "V": ("GTG", "GTC")}
#: Residues a generated protein draws from (no Asn or Cys: sequons and disulfides only where asked).
_POOL = "LLLAAAGGVVEESSIKKRDTTPQFYH"
#: Filler for generated non-coding DNA (no ATG, AATAAA or GT-AG traps can form from it: only C, A, T runs checked below).
_FILL = "CATCCACTCCAC"


def rna(dna: str) -> str:
    return dna.replace("T", "U")


@dataclass(frozen=True)
class GeneSpec:
    """A gene as written: a ``sequence`` (the coding strand of the transcribed region, 5′→3′
    from +1, DNA) with ``introns`` (1-based inclusive ``(start, end)`` positions in it), or a
    ``protein`` (one- or three-letter codes) or a number of ``codons`` (generated with ``seed``,
    ``introns`` then a count); ``signal_peptide`` and ``glycosylation`` ask a generated protein
    for a signal peptide and an N-X-S/T sequon (and check a written one has them); ``cell``:
    ``animal``, ``plant`` or ``bacterium``."""

    name: str | None = None
    sequence: str | None = None
    introns: int | tuple[tuple[int, int], ...] | None = None
    protein: str | None = None
    codons: int | None = None
    signal_peptide: bool | None = None
    glycosylation: bool | None = None
    seed: int = 1
    cell: str = "animal"
    where: str = "gene"


@dataclass(frozen=True)
class Intron:
    """An intron of the transcribed region (0-based, ``start`` inclusive, ``end`` exclusive) and
    its branch-point A (an index of the region)."""

    start: int
    end: int
    branch: int

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Gene:
    """A built gene. ``promoter``: the coding strand upstream of +1 (DNA, its last base is −1);
    ``region``: the coding strand of the transcribed region from +1 (DNA, with introns and the
    stretch the polymerase transcribes past the cleavage site); ``downstream``: DNA after it.
    Positions are 0-based indices of ``region`` unless named otherwise; ``boxes``: promoter
    elements as ``(name, start, end)`` indices of ``promoter``."""

    name: str | None
    cell: str
    promoter: str
    region: str
    downstream: str
    introns: tuple[Intron, ...]
    cleavage: int                  # the pre-mRNA ends before this index
    polya_signal: int | None       # index of AATAAA
    boxes: tuple[tuple[str, int, int], ...]
    orf_start: int                 # index of the A of the AUG in the mature mRNA
    codons: tuple[str, ...]        # the ORF's codons (RNA), the stop codon last
    signal: int                    # residues of the signal peptide (0: none)
    sequons: tuple[int, ...]       # 0-based residue indices of sequon asparagines in the mature part
    sd: int | None = None          # Shine–Dalgarno start in the mature mRNA (bacteria)

    @property
    def eukaryote(self) -> bool:
        return self.cell != "bacterium"

    @cached_property
    def pre_mrna(self) -> str:
        """The primary transcript (RNA) up to the cleavage site, introns included."""
        return rna(self.region[: self.cleavage])

    def exons(self) -> list[tuple[int, int]]:
        """The exons as ``(start, end)`` region indices."""
        out, x = [], 0
        for intron in self.introns:
            out.append((x, intron.start))
            x = intron.end
        out.append((x, self.cleavage))
        return out

    @cached_property
    def mature(self) -> str:
        """The mature mRNA (exons joined; no cap or tail)."""
        return "".join(self.pre_mrna[a:b] for a, b in self.exons())

    def mature_index(self, region_index: int) -> int | None:
        """The mature-mRNA index of a region index (``None``: in an intron or past the end)."""
        offset = 0
        for a, b in self.exons():
            if a <= region_index < b:
                return offset + region_index - a
            offset += b - a
        return None

    def junctions(self) -> list[int]:
        """Exon–exon junctions in the mature mRNA (the index of the first base after each)."""
        out, offset = [], 0
        for a, b in self.exons()[:-1]:
            offset += b - a
            out.append(offset)
        return out

    @cached_property
    def protein(self) -> str:
        """The protein (one-letter codes, N→C; the stop codon not included)."""
        return "".join(CODONS[c] for c in self.codons[:-1])

    @property
    def mature_protein(self) -> str:
        """The protein after its signal peptide is cleaved off."""
        return self.protein[self.signal:]

    @property
    def stop(self) -> str:
        return self.codons[-1]

    @property
    def orf_end(self) -> int:
        """The mature-mRNA index just after the stop codon."""
        return self.orf_start + 3 * len(self.codons)

    def codon_at(self, k: int) -> tuple[int, str]:
        """Codon ``k`` (0: the AUG): its mature-mRNA index and its bases."""
        return self.orf_start + 3 * k, self.codons[k]


# ----- building --------------------------------------------------------------------------------------


def build_gene(spec: GeneSpec) -> Gene:
    """The gene ``spec`` describes, checked (a :class:`VidgenError` names what is wrong)."""
    where = spec.where
    given = [k for k, v in (("sequence", spec.sequence), ("protein", spec.protein), ("codons", spec.codons)) if v is not None]
    if len(given) > 1 and given != ["sequence", "protein"]:
        raise VidgenError(f"{where}: give one of sequence, protein or codons (got {' and '.join(given)})")
    if spec.cell == "bacterium" and spec.introns not in (None, 0, ()):
        raise VidgenError(f"{where}: introns: bacteria have no spliceosomal introns (their genes are continuous and their "
                          f"mRNAs are translated as they are made)")
    rng = random.Random(f"gene:{spec.seed}:{spec.name}")
    if spec.sequence is not None:
        gene = _from_sequence(spec, rng)
    else:
        if isinstance(spec.introns, tuple):
            raise VidgenError(f"{where}: introns as positions need a sequence; with protein or codons, introns is a count (introns: 1)")
        protein = _protein_of(spec, rng)
        gene = _generated(spec, protein, rng)
    _check_protein_features(spec, gene)
    return gene


def _protein_of(spec: GeneSpec, rng: random.Random) -> str:
    """The protein to write as a gene: ``protein`` as written (checked), else a seeded one of
    ``codons`` codons (with a signal peptide and a sequon when asked)."""
    where = spec.where
    if spec.protein is not None:
        return parse_protein(spec.protein, f"{where}: protein")
    n = spec.codons if spec.codons is not None else (72 if spec.signal_peptide else 12)
    lo, hi = CODONS_RANGE
    if not lo <= n <= hi:
        raise VidgenError(f"{where}: codons: {n}: give {lo} to {hi} (the start codon included, the stop codon not)")
    head = "M"
    if spec.signal_peptide:
        n_region = "MA" + rng.choice("KR") + rng.choice("KRS")
        h_region = "".join(rng.choice("LLLAVIF") for _ in range(9))
        head = n_region + h_region + "G" + rng.choice("SQT") + "A"
        if n < len(head) + 4:
            raise VidgenError(f"{where}: codons: {n}: a signal peptide alone is {len(head)} residues; give more codons")
    body = []
    while len(head) + len(body) < n:
        aa = rng.choice(_POOL)
        if not body and aa == "P":
            continue          # no Pro right after a signal peptidase site
        body.append(aa)
    if spec.glycosylation:
        if len(body) < 6:
            raise VidgenError(f"{where}: codons: {n}: too short for an N-X-S/T sequon after the signal peptide")
        k = min(len(body) - 4, max(2, len(body) // 3))
        body[k:k + 3] = ["N", rng.choice("AEGKLV"), rng.choice("ST")]
    return head + "".join(body)


def parse_protein(text: str, where: str) -> str:
    """A protein written in one-letter codes (``MALW…``) or three-letter codes joined by ``-``
    or spaces (``Met-Ala-Leu``): its one-letter sequence, starting with Met."""
    t = text.strip()
    if any(ch in t for ch in "- ") or (len(t) >= 3 and t[:3].lower() == "met" and not t.isupper()):
        parts = [p for p in t.replace("-", " ").split() if p]
        out = "".join(amino_acid(p, where) for p in parts)
    else:
        out = t.upper()
        for k, ch in enumerate(out):
            if ch not in AMINO_ACIDS:
                hint = " (* or a stop: the gene's stop codon is added after the last residue)" if ch == "*" else ""
                raise VidgenError(f"{where}: '{ch}' at {k + 1} is not an amino acid's one-letter code{hint}")
    if not out:
        raise VidgenError(f"{where}: empty")
    if out[0] != "M":
        raise VidgenError(f"{where}: a protein starts with Met (M): translation starts at the start codon AUG, which codes Met "
                          f"(fMet in bacteria); it starts with {AMINO_ACIDS[out[0]]}")
    return out


def _fill(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(_FILL) for _ in range(n))


def _promoter(spec: GeneSpec, rng: random.Random) -> tuple[str, tuple[tuple[str, int, int], ...]]:
    """38 bp upstream of +1: a TATA box at −31 to −24 and an initiator's −2/−1 (eukaryotes), or
    the −35 and −10 boxes (bacteria). Boxes as promoter indices."""
    length = 38
    if spec.cell == "bacterium":
        # -35 TTGACA at -35..-30, 17 bp spacer, -10 TATAAT at -12..-7, then 6 bp to +1
        left = _fill(rng, length - 35)
        seq = left + "TTGACA" + _fill(rng, 17) + "TATAAT" + _fill(rng, 6)
        return seq, (("−35 box", length - 35, length - 29), ("−10 box", length - 12, length - 6))
    seq = _fill(rng, length - 31) + "TATAAAAG" + _fill(rng, 21) + "TC"
    return seq, (("TATA box", length - 31, length - 23),)


def _intron(rng: random.Random) -> str:
    """A generated intron (coding strand, DNA): 5′ splice site GTAAGT, a branch point in CTAAC
    (its A 19 nt from the 3′ end), a polypyrimidine tract and the 3′ splice site CAG."""
    return "GTAAGT" + "".join(rng.choice("CATC") for _ in range(8)) + "CTAAC" + "T" + "".join(rng.choice("CTTC") for _ in range(12)) + "TCAG"


def _generated(spec: GeneSpec, protein: str, rng: random.Random) -> Gene:
    """A gene for ``protein``: promoter, 5′ UTR, the ORF (back-translated with frequent codons)
    with ``introns`` between codons, the stop codon, a 3′ UTR with the poly(A) signal and the
    cleavage site (bacteria: a terminator)."""
    bacterium = spec.cell == "bacterium"
    promoter, boxes = _promoter(spec, rng)
    orf = "".join(rng.choice(_BACK[aa]) for aa in protein) + ("TAA" if bacterium else rng.choice(("TGA", "TAA")))
    if bacterium:
        utr5 = "A" + _fill(rng, 4) + "AGGAGG" + "TAACAC"      # SD 7 nt before the AUG
        utr3 = _fill(rng, 4) + "AAAGCCCGCCTAATGAGCGGGCTTTTTTTT"
        region = utr5 + orf + utr3
        cleavage, signal_at = len(region), None
        downstream = _fill(rng, DOWNSTREAM)
        introns: tuple[Intron, ...] = ()
    else:
        utr5 = "AGTCC" + _fill(rng, 3) + "C" + "GCCACC"      # initiator (A at +1) … Kozak (no AUG before the start)
        tail = "GCGGCC" + "AATAAA" + "GCTTCCTGCCCCA"           # poly(A) signal, cleavage after the CA
        dse = "TGTGTTGTGTTG"                                    # GU-rich downstream element
        count = spec.introns if isinstance(spec.introns, int) else 0
        n = len(protein)
        cuts = sorted({max(1, min(n - 1, round(n * (j + 1) / (count + 1)))) for j in range(count)})
        pieces, last, introns_list = [], 0, []
        pos = len(utr5)
        for cut in cuts:
            exon = orf[3 * last: 3 * cut]
            pieces.append(exon)
            pos += len(exon)
            intron = _intron(rng)
            introns_list.append(Intron(pos, pos + len(intron), pos + len(intron) - 19))
            pieces.append(intron)
            pos += len(intron)
            last = cut
        pieces.append(orf[3 * last:])
        region = utr5 + "".join(pieces) + tail + dse
        cleavage = len(utr5) + sum(len(p) for p in pieces) + len(tail)
        signal_at = cleavage - 19
        downstream = _fill(rng, DOWNSTREAM)
        introns = tuple(introns_list)
    return _finish(spec, promoter, boxes, region, downstream, introns, cleavage, signal_at)


def _from_sequence(spec: GeneSpec, rng: random.Random) -> Gene:
    """A written gene: the transcribed region as given, introns checked, the poly(A) signal and
    cleavage site found (bacteria: the region ends where transcription ends)."""
    where = spec.where
    region = check_sequence(spec.sequence or "", "dna", f"{where}: sequence")
    promoter, boxes = _promoter(spec, rng)
    introns = _written_introns(spec, region)
    polya, cleavage = None, len(region)
    if spec.cell != "bacterium":
        last = introns[-1].end if introns else 0
        found = region.find("AATAAA", last)
        if found < 0:
            found = region.find("ATTAAA", last)
        if found >= 0:
            polya = found
            window = region[found + 16: found + 36]
            ca = window.find("CA")
            cleavage = min(len(region), found + 16 + ca + 2 if ca >= 0 else found + 6 + 18)
    gene = _finish(spec, promoter, boxes, region, _fill(rng, DOWNSTREAM), introns, cleavage, polya)
    return gene


def _written_introns(spec: GeneSpec, region: str) -> tuple[Intron, ...]:
    """The introns at their written positions, each checked: within the region, in order, at
    least 30 nt, GU at the 5′ end, AG at the 3′ end, a branch-point A 18–40 nt from the 3′ end."""
    where = spec.where
    if spec.introns is None or spec.introns == 0:
        return ()
    if isinstance(spec.introns, int):
        raise VidgenError(f"{where}: introns: with a sequence, give their positions ([[start, end], …], 1-based, in the sequence)")
    out: list[Intron] = []
    for k, (a, b) in enumerate(spec.introns):
        at = f"{where}: introns[{k}] ({a}–{b})"
        if not 1 < a < b <= len(region):
            raise VidgenError(f"{at}: positions run from 2 to {len(region)} (1-based, start < end; position 1 is the transcription start)")
        start, end = a - 1, b
        if out and start < out[-1].end:
            raise VidgenError(f"{at}: overlaps or comes before the intron before it; list introns in order")
        seq = rna(region[start:end])
        if end - start < MIN_INTRON:
            raise VidgenError(f"{at}: {end - start} nt is too short: the spliceosome needs at least ~{MIN_INTRON} nt for the 5′ splice "
                              f"site, the branch point and the 3′ splice site")
        if not seq.startswith("GU"):
            raise VidgenError(f"{at}: an intron starts with GU (GT in the DNA: the 5′ splice site U1 snRNP pairs with); this one "
                              f"starts {seq[:2]}")
        if not seq.endswith("AG"):
            raise VidgenError(f"{at}: an intron ends with AG (the 3′ splice site U2AF binds); this one ends {seq[-2:]}")
        lo, hi = BRANCH_WINDOW
        window = [i for i in range(max(start, end - hi), end - lo + 1) if region[i] == "A"]
        if not window:
            raise VidgenError(f"{at}: no branch-point A {lo}–{hi} nt upstream of the 3′ end: the branch-point adenosine's 2′-OH "
                              f"attacks the 5′ splice site to form the lariat")
        # prefer the A of a yUnAy branch-point motif, else the A nearest the 3′ end
        motif = [i for i in window if region[i - 2: i - 1] == "T" and region[i + 1: i + 2] in ("C", "T")]
        branch = (motif or window)[-1]
        out.append(Intron(start, end, branch))
    return tuple(out)


def _finish(spec: GeneSpec, promoter: str, boxes: tuple[tuple[str, int, int], ...], region: str, downstream: str, introns: tuple[Intron, ...],
            cleavage: int, polya: int | None) -> Gene:
    """The gene with its reading frame found and checked."""
    where = spec.where
    if introns and introns[-1].end > cleavage:
        raise VidgenError(f"{where}: introns[{len(introns) - 1}] runs past the 3′ end of the pre-mRNA (the cleavage site at {cleavage}); "
                          f"an intron lies between two exons")
    gene = Gene(spec.name, spec.cell, promoter, region, downstream, introns, cleavage, polya, boxes, 0, (), 0, ())
    mature = gene.mature
    start = mature.find(START_CODON)
    if start < 0:
        raise VidgenError(f"{where}: the mature mRNA has no start codon (AUG): the ribosome scans from the 5′ cap to the first AUG")
    codons = []
    for i in range(start, len(mature) - 2, 3):
        codon = mature[i:i + 3]
        codons.append(codon)
        if codon in STOP_CODONS:
            break
    else:
        raise VidgenError(f"{where}: no stop codon (UAA, UAG, UGA) in frame after the AUG at mRNA position {start + 1}: the reading "
                          f"frame runs off the 3′ end (a ribosome stalls there: non-stop decay)")
    if len(codons) < 2:
        raise VidgenError(f"{where}: the AUG at mRNA position {start + 1} is followed at once by a stop codon: no protein")
    sd = None
    if not gene.eukaryote:
        sd_at = mature.rfind("AGGAGG", 0, start)
        sd = sd_at if sd_at >= 0 and 4 <= start - (sd_at + 6) <= 10 else None
    gene = replace(gene, orf_start=start, codons=tuple(codons), sd=sd)
    stop_end = start + 3 * len(codons)
    junctions = gene.junctions()
    if junctions and junctions[-1] - stop_end >= NMD_DISTANCE:
        raise VidgenError(f"{where}: the stop codon {codons[-1]} (codon {len(codons)}) lies {junctions[-1] - stop_end} nt upstream of the "
                          f"last exon–exon junction: a premature termination codon (more than ~{NMD_DISTANCE} nt before a junction) "
                          f"leaves an exon junction complex on the mRNA, and nonsense-mediated decay destroys it")
    protein = gene.protein
    signal = signal_peptide_length(protein) if gene.eukaryote else 0
    sequons = tuple(i for i in range(signal, len(protein) - 2) if protein[i] == "N" and protein[i + 1] != "P" and protein[i + 2] in "ST")
    return replace(gene, signal=signal, sequons=sequons)


def _check_protein_features(spec: GeneSpec, gene: Gene) -> None:
    """What the author wrote about the protein holds: its sequence, a signal peptide, a sequon."""
    where = spec.where
    if spec.protein is not None and spec.sequence is not None:
        wanted = parse_protein(spec.protein, f"{where}: protein")
        made = gene.protein
        for k, (a, b) in enumerate(zip(wanted, made)):
            if a != b:
                at, codon = gene.codon_at(k)
                raise VidgenError(f"{where}: codon {k + 1} ({codon}, mRNA position {at + 1}) codes {AMINO_ACIDS[b]}, not "
                                  f"{AMINO_ACIDS[a]} as protein says")
        if len(made) < len(wanted):
            at, codon = gene.codon_at(len(made))
            raise VidgenError(f"{where}: a stop codon {codon} in frame at codon {len(made) + 1} (mRNA position {at + 1}) ends the "
                              f"protein after {len(made)} residues, before the end of the {len(wanted)} written")
        if len(made) > len(wanted):
            raise VidgenError(f"{where}: the reading frame goes on past the {len(wanted)} residues written (to {len(made)}): "
                              f"no stop codon where the protein ends")
    if spec.signal_peptide and not gene.signal:
        raise VidgenError(f"{where}: signal_peptide: the protein has none: a signal peptide is an N-terminal stretch with a "
                          f"hydrophobic core of 7–15 residues (L, A, V, I, F…) and a cleavage site with small residues (A, G, S) "
                          f"at −1 and −3 (protein starts {gene.protein[:20]}…)" if gene.eukaryote else
                          f"{where}: signal_peptide: shown here for eukaryotes (SRP to the ER); bacteria send them to SecYEG in "
                          f"their plasma membrane")
    if spec.glycosylation and not gene.sequons:
        raise VidgenError(f"{where}: glycosylation: the protein has no N-glycosylation sequon (Asn-X-Ser/Thr, X not Pro) after "
                          f"its signal peptide")


def signal_peptide_length(protein: str) -> int:
    """The length of a cleavable N-terminal signal peptide (0: none): a hydrophobic h-region of
    7 or more residues starting within the first 12, then a cleavage site 3–8 residues after
    it with small residues at −1 (A, G, S, C, T) and −3 (also V, I, L) and no Pro at +1."""
    h_end = None
    for start in range(1, 13):
        run = 0
        while start + run < len(protein) and protein[start + run] in HYDROPHOBIC:
            run += 1
        if run >= 7:
            h_end = start + run
            break
    if h_end is None:
        return 0
    for c in range(h_end + 3, h_end + 9):
        if c >= len(protein):
            break
        if protein[c - 1] in "AGSCT" and protein[c - 3] in "AGSCTVIL" and protein[c] != "P":
            return c
    return 0


def side_chain(aa: str) -> str:
    """``hydrophobic``, ``polar``, ``acidic``, ``basic`` or ``special`` (Gly, Pro)."""
    for name, members in (("hydrophobic", HYDROPHOBIC), ("acidic", ACIDIC), ("basic", BASIC), ("special", SPECIAL)):
        if aa in members:
            return name
    return "polar"


def anticodon_of(codon: str) -> str:
    """The anticodon (5′→3′) that pairs with ``codon`` by Watson–Crick rules (wobble aside)."""
    pair = {"A": "U", "U": "A", "G": "C", "C": "G"}
    return "".join(pair[b] for b in reversed(codon))


# ----- the order of the steps --------------------------------------------------------------------


@dataclass(frozen=True)
class ExpressionState:
    """How far a gene's expression has come: ``rna`` (the polymerase has transcribed the gene
    and waits past the poly(A) site), ``capped``, ``spliced``, ``tailed`` (cleaved and
    polyadenylated), ``exported``, ``translated`` (codons read so far), ``released`` (at the stop
    codon), ``in_er`` (the ribosome on the translocon), ``signal_cut``, ``glycosylated``,
    ``folded``, ``place``: where the protein is (``cytosol``, ``er_lumen``, ``golgi``,
    ``outside``, ``lysosome``, ``membrane``)."""

    rna: bool = False
    capped: bool = False
    spliced: bool = False
    tailed: bool = False
    exported: bool = False
    translated: int = 0
    released: bool = False
    in_er: bool = False
    signal_cut: bool = False
    glycosylated: bool = False
    folded: bool = False
    place: str = "nucleus"

    @classmethod
    def at_start(cls, gene: Gene, start: str) -> "ExpressionState":
        """The state a scene starts in: ``dna`` (the gene in the nucleus) or ``mrna`` (a
        mature mRNA in the cytosol, ready to be translated)."""
        if start == "mrna":
            return cls(True, gene.eukaryote, True, gene.eukaryote, gene.eukaryote, place="cytosol")
        return cls()

    @property
    def growing(self) -> bool:
        """A ribosome is on the mRNA with a growing chain."""
        return self.translated > 0 and not self.released


def step_problem(gene: Gene, state: ExpressionState, step: str, options: dict[str, object] | None = None) -> str | None:
    """Why ``step`` cannot come now (``None``: it can), with the reason."""
    options = options or {}
    euk = gene.eukaryote
    if step in ("cap", "splice", "polyadenylate", "export") and not euk:
        return {"cap": "bacterial mRNAs have no 5′ cap (a triphosphate stays on their 5′ end; ribosomes find the Shine–Dalgarno sequence)",
                "splice": "bacteria have no spliceosome: their genes have no introns",
                "polyadenylate": "bacterial mRNAs get no protective poly(A) tail (a short one marks them for decay); transcription ends at a terminator",
                "export": "bacteria have no nucleus: ribosomes translate the mRNA while it is still being transcribed"}[step]
    if step == "transcribe":
        return "the gene is transcribed already" if state.rna else None
    if step in ("cap", "splice", "polyadenylate") and not state.rna:
        return f"{step} works on the pre-mRNA: transcribe the gene first"
    if step == "cap":
        return "the 5′ end is capped already (transcribe caps it at ~25 nt unless the scene has its own cap step)" if state.capped else None
    if step == "splice":
        if not gene.introns:
            return "this gene has no introns (introns: 1 adds one)"
        return "the introns are spliced out already" if state.spliced else None
    if step == "polyadenylate":
        if gene.polya_signal is None:
            return "the gene has no poly(A) signal (AATAAA) after its stop codon: CPSF has nothing to bind, so there is no cleavage site"
        return "the 3′ end is cleaved and polyadenylated already" if state.tailed else None
    if step == "export":
        if state.exported:
            return "the mRNA is in the cytosol already"
        missing = [w for w, ok in (("transcribed", state.rna), ("capped", state.capped), ("spliced", state.spliced or not gene.introns),
                                   ("polyadenylated", state.tailed)) if not ok]
        if missing:
            return (f"only a mature mRNA leaves the nucleus: this one is not {', '.join(missing)} yet (export follows the cap, "
                    f"splicing and the poly(A) tail; unspliced or uncapped RNAs are held back and degraded)")
        return None
    if step == "translate":
        if euk and not state.exported:
            return ("translation starts only in the cytoplasm: ribosomes are assembled in the nucleolus but join an mRNA only after "
                    "export; export the mRNA through a nuclear pore first")
        if not euk and not state.rna:
            return "transcribe the gene first (in bacteria ribosomes start on the mRNA while it is being made)"
        if state.released:
            return "the protein is finished and released already (its ribosome came apart at the stop codon)"
        n = options.get("codons")
        left = len(gene.codons) - 1 - state.translated
        if isinstance(n, int) and n > left:
            return f"codons: {n}: only {left} codon{'s' if left != 1 else ''} are left before the stop codon {gene.stop}"
        return None
    if step == "target_er":
        if not euk:
            return "bacteria have no ER: SRP takes signal peptides to SecYEG in the plasma membrane"
        if not gene.signal:
            return ("the protein has no signal peptide: SRP binds an N-terminal hydrophobic signal sequence as it leaves the ribosome "
                    "(signal_peptide: true writes one); proteins without one are made in the cytosol")
        if state.in_er:
            return "the ribosome is on the ER already"
        if not state.growing:
            if state.released:
                return ("the protein is finished and released already: SRP targets co-translationally, while the signal peptide "
                        f"comes out of the ribosome; translate with codons: {gene.signal + 2} or so, then target_er")
            return "translation has not started: translate (codons: a few) first, then target_er while the chain grows"
        need = gene.signal + TUNNEL
        if len(gene.codons) - 1 < need + 4:
            return (f"the protein ({len(gene.codons) - 1} residues) is released before its signal peptide ({gene.signal}) leaves the "
                    f"~{TUNNEL}-residue exit tunnel: SRP targets only chains long enough; give the gene at least {need + 8} codons")
        if state.translated > need + 6:
            return (f"the signal peptide left the exit tunnel {state.translated - need} residues ago: SRP binds it as it emerges "
                    f"(translate fewer codons before target_er, at most {need})")
        return None
    if step == "glycosylate":
        if not gene.sequons:
            return "the protein has no N-glycosylation sequon (Asn-X-Ser/Thr, X not Pro) after its signal peptide"
        if not state.in_er:
            return ("N-linked glycosylation happens in the ER lumen: the oligosaccharyltransferase beside the translocon adds the "
                    "glycan to the Asn of a sequon as it enters the lumen (target_er first)")
        if state.glycosylated:
            return "the protein is glycosylated already"
        return None
    if step == "fold":
        chaperone = options.get("chaperone")
        place = "er_lumen" if state.in_er or state.place == "er_lumen" else "cytosol"
        if state.folded:
            return "the protein is folded already"
        if not state.released:
            return "fold works on the finished chain: translate to the stop codon first"
        if isinstance(chaperone, str) and chaperone in CHAPERONES and CHAPERONES[chaperone] != place:
            where = "the ER lumen" if place == "er_lumen" else "the cytosol"
            other = "bip or calnexin (the ER's Hsp70 and lectin chaperone)" if place == "er_lumen" else "hsp70 or chaperonin (TRiC)"
            return f"{chaperone} does not work in {where}, where this protein is: use {other}"
        return None
    if step == "to_golgi":
        if not state.in_er:
            return ("only proteins made into the ER enter the secretory pathway: this one is in the cytosol (it has no signal "
                    "peptide, or target_er was not played)")
        if not state.released:
            return "the protein is still being made on the ER: translate to the stop codon first"
        if not state.folded:
            return ("ER quality control keeps unfolded proteins in the ER (BiP and calnexin hold them; ERAD degrades those that "
                    "never fold): fold first")
        if state.place != "er_lumen":
            return f"the protein has left the ER already (it is in the {state.place.replace('_', ' ')})"
        return None
    if step == "secrete":
        if state.place != "golgi":
            return ("proteins leave for the plasma membrane, lysosomes or outside the cell from the trans-Golgi network: to_golgi "
                    "first" if state.place in ("er_lumen", "cytosol", "nucleus") else f"the protein is in the {state.place} already")
        to = options.get("to", "outside")
        if to not in DESTINATIONS:
            return f"to: '{to}'{did_you_mean(str(to), list(DESTINATIONS))} ({', '.join(DESTINATIONS)})"
        return None
    return f"'{step}' is not a step of gene expression{did_you_mean(step, list(STEPS))}"


def advance(gene: Gene, state: ExpressionState, step: str, options: dict[str, object] | None = None) -> ExpressionState:
    """The state after ``step`` (assumed allowed)."""
    options = options or {}
    total = len(gene.codons) - 1
    if step == "transcribe":
        later_cap = bool(options.get("cap_later"))
        return replace(state, rna=True, capped=gene.eukaryote and not later_cap, place="nucleus" if gene.eukaryote else "cytosol")
    if step == "cap":
        return replace(state, capped=True)
    if step == "splice":
        return replace(state, spliced=True)
    if step == "polyadenylate":
        return replace(state, tailed=True)
    if step == "export":
        return replace(state, exported=True, place="cytosol")
    if step == "translate":
        n = options.get("codons")
        upto = total if not isinstance(n, int) else min(total, state.translated + n)
        done = upto >= total
        return replace(state, translated=upto, released=done, place="er_lumen" if state.in_er else "cytosol")
    if step == "target_er":
        return replace(state, in_er=True, signal_cut=True, translated=max(state.translated, er_entry(gene)))
    if step == "glycosylate":
        return replace(state, glycosylated=True, translated=max(state.translated, min(total - 1, glyco_reach(gene)) if not state.released else state.translated))
    if step == "fold":
        return replace(state, folded=True)
    if step == "to_golgi":
        return replace(state, place="golgi")
    if step == "secrete":
        return replace(state, place=str(options.get("to", "outside")))
    return state


#: The steps a ``cell`` scene shows (at the scale of the cell, transcribe includes the RNA's
#: processing and translate the protein's way into the ER, its glycosylation and folding).
CELL_STEPS = ("transcribe", "export", "translate", "to_golgi", "secrete")


def cell_steps(gene: Gene, step: str) -> list[tuple[str, dict[str, object]]]:
    """The molecular steps (with their options) a cell scene's ``step`` stands for."""
    if step == "transcribe":
        return [("transcribe", {})] + ([("splice", {})] if gene.introns else []) + ([("polyadenylate", {})] if gene.eukaryote else [])
    if step == "translate":
        if gene.eukaryote and gene.signal:
            first = max(1, min(gene.signal + TUNNEL, len(gene.codons) - 2))
            return ([("translate", {"codons": first}), ("target_er", {}), ("translate", {})]
                    + ([("glycosylate", {})] if gene.sequons else []) + [("fold", {})])
        return [("translate", {}), ("fold", {})]
    return [(step, {})]


def cell_step_problem(gene: Gene, state: ExpressionState, step: str, options: dict[str, object] | None = None) -> str | None:
    """Why a cell scene's ``step`` cannot come now (the first of its molecular steps that
    cannot), or ``None``."""
    if step not in CELL_STEPS:
        return (f"{step} is shown up close in a molecule scene with the gene; at the scale of a cell, transcribe includes capping, "
                f"splicing and the poly(A) tail, and translate the way into the ER, glycosylation and folding "
                f"(cell steps: {', '.join(CELL_STEPS)})")
    for sub, extra in cell_steps(gene, step):
        problem = step_problem(gene, state, sub, {**(options or {}), **extra})
        if problem:
            return problem
        state = advance(gene, state, sub, {**(options or {}), **extra})
    return None


def cell_advance(gene: Gene, state: ExpressionState, step: str, options: dict[str, object] | None = None) -> ExpressionState:
    """The state after a cell scene's ``step`` (assumed allowed)."""
    for sub, extra in cell_steps(gene, step):
        state = advance(gene, state, sub, {**(options or {}), **extra})
    return state


def er_entry(gene: Gene) -> int:
    """Codons translated when ``target_er`` ends: the signal peptide out of the tunnel, SRP's
    detour, the chain on into the lumen until signal peptidase can cut."""
    return min(len(gene.codons) - 2, gene.signal + TUNNEL + 10)


def glyco_reach(gene: Gene) -> int:
    """Codons translated when the first sequon's Asn reaches the oligosaccharyltransferase."""
    return gene.sequons[0] + 1 + OST_REACH if gene.sequons else 0


__all__ = [
    "BUBBLE", "CAP_AT", "CELL_STEPS", "CHAPERONES", "DESTINATIONS", "ExpressionState", "Gene", "GeneSpec", "HYBRID", "Intron", "OST_REACH", "START_CODON", "STEPS",
    "STOP_CODONS", "TAIL_DRAWN", "TAIL_REAL", "TUNNEL", "advance", "anticodon_of", "build_gene", "cell_advance", "cell_step_problem", "cell_steps", "er_entry", "glyco_reach", "parse_protein", "rna",
    "side_chain", "signal_peptide_length", "step_problem",
]
