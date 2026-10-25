"""CRISPR–Cas9 genome editing as data and rules (DESIGN.md §96.14). No manim.

- **The nucleases** (:data:`CAS`): SpCas9 (*Streptococcus pyogenes*; PAM 5′-NGG-3′, a 20-nt
  spacer) and SaCas9 (*Staphylococcus aureus*; PAM 5′-NNGRRT-3′, 21–23 nt). The PAM lies on the
  non-target strand (the strand whose sequence the spacer repeats, T for U) right after the 3′ end
  of the protospacer; the sgRNA's spacer pairs with the other, target strand. Both enzymes cut
  both strands 3 bp upstream (5′) of the PAM — HNH the target strand, RuvC the non-target strand —
  leaving blunt ends (Jinek et al. 2012 *Science* 337:816; Ran et al. 2015 *Nature* 520:186).
- **Guides** (:func:`find_guides`): every protospacer with a PAM on either strand of a target,
  with its cut position and GC content. :func:`check_guide` places an author's spacer and refuses
  a spacer that is not in the target, one without a PAM after it (naming what is there and the
  guides that would work), the wrong length for the enzyme, a spacer that ends in its PAM, a spacer
  found twice.
- **Repair** (:func:`repair`): non-homologous end joining joins the blunt ends, often with a small
  insertion or deletion — the commonest SpCas9 outcome is a 1-bp insertion copying the base 4 bp
  upstream of the PAM —; on a coding sequence an indel that is not a multiple of 3 shifts the frame
  (a knockout). Homology-directed repair copies a donor template carrying the edit; the edit is
  checked against the target, its distance to the cut is noted (efficiency falls within tens of
  bp), and a repaired allele that still has the protospacer and PAM is flagged (Cas9 would cut it
  again: a silent PAM change in the donor prevents that)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from vidgen.errors import VidgenError

from ..cellworld.model import did_you_mean
from ..cellworld.sequences import reverse_complement
from . import hgvs

IUPAC = {"A": "A", "C": "C", "G": "G", "T": "T", "R": "AG", "Y": "CT", "S": "CG", "W": "AT", "K": "GT", "M": "AC", "B": "CGT",
         "D": "AGT", "H": "ACT", "V": "ACG", "N": "ACGT"}
REPAIRS = ("none", "nhej", "hdr")
#: Target length limits (bp): enough for a protospacer and PAM, few enough to draw letters.
TARGET_RANGE = (26, 80)


@dataclass(frozen=True)
class Cas:
    name: str
    organism: str
    pam: str                       # IUPAC, 5′→3′ on the non-target strand, 3′ of the protospacer
    spacer: tuple[int, int]        # allowed spacer lengths
    cut: int                       # bp upstream (5′) of the PAM where both strands are cut


CAS: dict[str, Cas] = {
    "SpCas9": Cas("SpCas9", "Streptococcus pyogenes", "NGG", (20, 20), 3),
    "SaCas9": Cas("SaCas9", "Staphylococcus aureus", "NNGRRT", (21, 23), 3),
}


def pam_matches(seq: str, pam: str) -> bool:
    return len(seq) == len(pam) and all(b in IUPAC[p] for b, p in zip(seq, pam))


@dataclass(frozen=True)
class Guide:
    """A protospacer with its PAM on the ``strand`` (``+``: the top strand as written; ``-``:
    its complement), in top-strand indices: protospacer ``[start, end)``, PAM ``[pam_start,
    pam_end)``; ``cut`` the gap (between ``cut - 1`` and ``cut``) where both strands are cut."""

    strand: str
    spacer: str
    start: int
    end: int
    pam_start: int
    pam_end: int
    pam: str
    cut: int

    @property
    def rna(self) -> str:
        return self.spacer.replace("T", "U")

    @property
    def gc(self) -> float:
        return (self.spacer.count("G") + self.spacer.count("C")) / len(self.spacer)

    def label(self) -> str:
        return f"{self.spacer} {self.pam} ({self.strand} strand)"


def find_guides(target: str, cas: Cas, length: int | None = None) -> list[Guide]:
    """Every protospacer of ``length`` (the enzyme's default) followed by a PAM, on both strands,
    ordered by cut position."""
    n = len(target)
    L = length or cas.spacer[0]
    P = len(cas.pam)
    out: list[Guide] = []
    for i in range(0, n - L - P + 1):
        if pam_matches(target[i + L:i + L + P], cas.pam):
            out.append(Guide("+", target[i:i + L], i, i + L, i + L, i + L + P, target[i + L:i + L + P], i + L - cas.cut))
    rc = reverse_complement(target)
    for j in range(0, n - L - P + 1):
        if pam_matches(rc[j + L:j + L + P], cas.pam):
            out.append(Guide("-", rc[j:j + L], n - j - L, n - j, n - j - L - P, n - j - L, rc[j + L:j + L + P], n - (j + L - cas.cut)))
    return sorted(out, key=lambda g: (g.cut, g.strand))


def check_target(text: str, where: str = "target") -> str:
    seq = re.sub(r"\s+", "", str(text)).upper()
    for k, b in enumerate(seq):
        if b not in "ACGT":
            raise VidgenError(f"{where}: '{b}' at {k + 1} is not a DNA base (A, C, G, T)")
    lo, hi = TARGET_RANGE
    if not lo <= len(seq) <= hi:
        raise VidgenError(f"{where}: {len(seq)} bp; give {lo}–{hi} bp of the top strand 5′→3′ (room for a protospacer, its PAM and "
                          f"some flank, few enough to draw every base)")
    return seq


def _candidates_text(guides: list[Guide], most: int = 3) -> str:
    if not guides:
        return "there is no PAM for this enzyme in the target"
    shown = "; ".join(f"{g.spacer} + {g.pam} ({g.strand})" for g in guides[:most])
    return f"guides with a PAM here: {shown}" + (f" (and {len(guides) - most} more)" if len(guides) > most else "")


def check_guide(target: str, cas: Cas, spacer: str, where: str = "spacer") -> Guide:
    """The guide an author's spacer makes on ``target``, or a :class:`VidgenError` with the reason
    (and the guides that would work)."""
    s = re.sub(r"\s+", "", str(spacer)).upper().replace("U", "T")
    for k, b in enumerate(s):
        if b not in "ACGT":
            raise VidgenError(f"{where}: '{b}' at {k + 1} is not a base (an sgRNA spacer in A, C, G, U — or T)")
    lo, hi = cas.spacer
    guides_any = find_guides(target, cas, min(max(len(s), lo), hi))
    P = len(cas.pam)
    if len(s) > P and pam_matches(s[-P:], cas.pam) and not lo <= len(s) <= hi and lo <= len(s) - P <= hi:
        raise VidgenError(f"{where}: {len(s)} nt ending {s[-P:]}: the spacer is the {len(s) - P} nt before the PAM; the PAM is in the DNA, "
                          f"not in the sgRNA (write {s[:-P]})")
    if not lo <= len(s) <= hi:
        want = f"{lo}" if lo == hi else f"{lo}–{hi}"
        raise VidgenError(f"{where}: {len(s)} nt; {cas.name} uses a {want}-nt spacer")
    n = len(target)
    rc = reverse_complement(target)
    hits = [(m.start(), "+") for m in re.finditer(f"(?={s})", target)] + [(m.start(), "-") for m in re.finditer(f"(?={s})", rc)]
    if not hits:
        comp = reverse_complement(s)[::-1]
        if s[::-1] in target or s[::-1] in rc:
            hint = " — it is in the target written backwards: write the spacer 5′→3′"
        elif comp in target or comp in rc:
            hint = (" — it is the complement of a protospacer (the target strand, which the sgRNA pairs with); the spacer repeats "
                    "the non-target strand's sequence 5′→3′")
        else:
            hint = ""
        raise VidgenError(f"{where}: {s} is not in the target on either strand{hint}; {_candidates_text(guides_any)}")
    if len(hits) > 1:
        raise VidgenError(f"{where}: {s} occurs {len(hits)} times in the target: the guide would cut at each (choose a unique protospacer)")
    i, strand = hits[0]
    seq = target if strand == "+" else rc
    after = seq[i + len(s):i + len(s) + P]
    if not pam_matches(after, cas.pam):
        others = [name for name, c in CAS.items() if name != cas.name and pam_matches(seq[i + len(s):i + len(s) + len(c.pam)], c.pam)
                  and c.spacer[0] <= len(s) <= c.spacer[1]]
        fits = f" (it fits {others[0]}'s {CAS[others[0]].pam})" if others else ""
        what = f"{after}" if len(after) == P else f"the end of the target ({after or 'nothing'})"
        raise VidgenError(f"{where}: after the protospacer comes {what}{fits}; {cas.name} needs the PAM {cas.pam} right after the "
                          f"protospacer's 3′ end on the same strand, and cannot cut without it; {_candidates_text(guides_any)}")
    for g in guides_any:
        if g.spacer == s and g.strand == strand:
            return g
    raise VidgenError(f"{where}: no guide")   # pragma: no cover (the PAM matched)


# ----- repair -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairResult:
    """A repair: ``kind``; the edit on the target (top-strand indices, ``alt`` replacing
    ``[start, end)``); the repaired top strand; the description (HGVS with ``coding_first``, else
    in words with target positions); the consequence on the protein (coding targets); notes."""

    kind: str
    edit: hgvs.Edit | None
    result: str
    description: str
    consequence: hgvs.Consequence | None
    notes: tuple[str, ...]
    donor: str | None = None


def _coding(target: str, coding_first: int | None) -> hgvs.CodingSequence | None:
    if coding_first is None:
        return None
    return hgvs.coding_sequence(target, "coding_first", coding_first)


def repair(target: str, cas: Cas, guide: Guide, kind: str, indel: int | None = None, edit_text: str | None = None,
           coding_first: int | None = None) -> RepairResult | None:
    """The outcome of ``kind`` (``nhej`` with an ``indel`` of +n / −n bp at the cut, default +1;
    ``hdr`` with an ``edit``); ``None`` for ``none``."""
    if kind == "none":
        return None
    cds = _coding(target, coding_first)
    notes: list[str] = []
    if kind == "nhej":
        n = 1 if indel is None else int(indel)
        if n == 0 or abs(n) > 12:
            raise VidgenError(f"indel: {n}: NHEJ leaves small insertions or deletions (+1 … +12, −1 … −12 bp); 0 is a perfect rejoin "
                              f"(which Cas9 cuts again)")
        g = guide.cut
        if n > 0:      # a templated insertion: the n bases on the PAM-distal side of the cut copied
            ins = target[g - n:g] if guide.strand == "+" else target[g:g + n]
            edit = hgvs.Edit(g, g, ins)
        else:
            m = -n
            a = g - (m + 1) // 2
            edit = hgvs.Edit(max(0, a), min(len(target), a + m), "")
        result = hgvs.apply_edit(target, edit)
        frame = abs(n) % 3 != 0
        words = f"{'+' if n > 0 else '−'}{abs(n)} bp {'insertion' if n > 0 else 'deletion'} at the cut"
        notes.append("NHEJ joins the blunt ends directly, often with a small insertion or deletion (an indel)")
        if n == 1:
            notes.append("the commonest SpCas9 outcome is a 1-bp insertion copying the base 4 bp upstream of the PAM"
                         if cas.name == "SpCas9" else "a 1-bp insertion at the cut")
        cons = None
        if cds is not None:
            cons = hgvs.edit_consequence(cds, edit)
            desc = f"{cons.dna.text()} {cons.protein.text()}"
            if frame:
                notes.append(f"{abs(n)} bp is not a multiple of 3: the reading frame shifts — a knockout allele (premature stop)")
            else:
                notes.append(f"{abs(n)} bp is a multiple of 3: the frame is kept (an in-frame indel; the protein may still work)")
        else:
            desc = words
            if coding_first is None:
                notes.append("in a coding exon an indel that is not a multiple of 3 shifts the reading frame (a knockout)")
        return RepairResult("nhej", edit, result, desc, cons, tuple(notes))
    if kind != "hdr":
        raise VidgenError(f"repair: '{kind}'{did_you_mean(kind, list(REPAIRS))} ({', '.join(REPAIRS)})")
    if not edit_text:
        raise VidgenError("repair: hdr copies a donor template: give the edit it carries (edit: 25A>T, or c.… with coding_first)")
    base_cds = cds or hgvs.CodingSequence(target, 1)
    prefix = "c." if cds is not None else "g."
    if cds is None and str(edit_text).strip().startswith("c."):
        raise VidgenError(f"edit: '{edit_text}': c. numbers need coding_first (the c. number of the target's first base); without it "
                          f"write positions in the target (25A>T)")
    raw = hgvs.parse_c(str(edit_text), "edit", prefix)
    if raw.start.offset or raw.end.offset:
        raise VidgenError("edit: a position in the target (no intronic offsets)")
    written, e = hgvs.resolve(base_cds, raw, "edit")
    assert e is not None
    dna = hgvs.check_written(base_cds, written, e, "edit", prefix)
    result = hgvs.apply_edit(target, e)
    cons = hgvs.explain(cds, dna, e) if cds is not None else None
    if cds is not None:
        desc = f"{dna.shown} {cons.protein.text() if cons else ''}".strip()
    else:
        desc = _words(dna)
    dist = min(abs(e.start - guide.cut), abs(e.end - guide.cut))
    notes.append(f"the edit lies {dist} bp from the cut" + (" — HDR works best within ~10 bp of the cut" if dist > 10 else ""))
    still = [g for g in find_guides(result, cas, len(guide.spacer)) if g.spacer == guide.spacer and g.strand == guide.strand]
    if still:
        notes.append("the repaired allele still has the protospacer and its PAM: Cas9 can cut it again — add a silent change to the PAM "
                     "(or the seed) in the donor")
    else:
        notes.append("the edit changes the protospacer or PAM: the repaired allele is no longer cut")
    notes.append("HDR needs a donor with homology arms and works mainly in dividing cells (S/G2)")
    return RepairResult("hdr", e, result, desc, cons, tuple(notes), donor=result)


def _words(dna: hgvs.DnaVariant) -> str:
    """A target-position description (``g.`` positions are positions in the target written)."""
    return dna.text("") + " (target position)"


# ----- the plan -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CrisprPlan:
    target: str
    cas: Cas
    guide: Guide
    candidates: tuple[Guide, ...]
    repair: RepairResult | None
    coding_first: int | None
    symbol: str | None
    pam_sites: tuple[tuple[int, str], ...]     # PAM starts (top index) and strand, for the search


def build_crispr_plan(spec: dict[str, Any]) -> CrisprPlan:
    """The plan from the scene's params: ``target``, ``cas``, ``spacer`` or ``guide`` (the n-th
    candidate, from 1; default: the candidate nearest the middle, or the edit), ``repair``,
    ``indel``, ``edit``, ``coding_first``."""
    target = check_target(spec.get("target") or "", "target")
    name = str(spec.get("cas") or "SpCas9")
    if name not in CAS:
        raise VidgenError(f"cas: '{name}'{did_you_mean(name, list(CAS))} ({', '.join(CAS)})")
    cas = CAS[name]
    coding_first = spec.get("coding_first")
    if coding_first is not None:
        coding_first = int(coding_first)
        hgvs.coding_sequence(target, "coding_first", coding_first)
    candidates = find_guides(target, cas)
    spacer = spec.get("spacer")
    pick = spec.get("guide")
    if spacer is not None and pick is not None:
        raise VidgenError("give spacer (the sgRNA's 20 nt) or guide (a candidate's number), not both")
    if spacer is not None:
        guide = check_guide(target, cas, str(spacer))
    else:
        if not candidates:
            raise VidgenError(f"target: there is no {cas.pam} PAM on either strand for {cas.name}: no guide can cut here")
        if pick is not None:
            k = int(pick)
            if not 1 <= k <= len(candidates):
                raise VidgenError(f"guide: {k}: the target has {len(candidates)} candidate guides (1–{len(candidates)}): "
                                  + "; ".join(f"{i + 1}: {g.label()}" for i, g in enumerate(candidates[:6])))
            guide = candidates[k - 1]
        else:
            centre = len(target) / 2
            guide = min(candidates, key=lambda g: (abs(g.cut - centre), g.strand))
    kind = str(spec.get("repair") or "nhej")
    if kind not in REPAIRS:
        raise VidgenError(f"repair: '{kind}'{did_you_mean(kind, list(REPAIRS))} ({', '.join(REPAIRS)})")
    if kind != "hdr" and spec.get("edit") is not None:
        raise VidgenError("edit: is the change a donor template carries: it needs repair: hdr")
    if kind != "nhej" and spec.get("indel") is not None:
        raise VidgenError("indel: is an NHEJ outcome: it needs repair: nhej")
    rep = repair(target, cas, guide, kind, spec.get("indel"), spec.get("edit"), coding_first)
    sites = []
    for i in range(len(target) - len(cas.pam) + 1):
        if pam_matches(target[i:i + len(cas.pam)], cas.pam):
            sites.append((i, "+"))
    rc = reverse_complement(target)
    n = len(target)
    for j in range(n - len(cas.pam) + 1):
        if pam_matches(rc[j:j + len(cas.pam)], cas.pam):
            sites.append((n - j - len(cas.pam), "-"))
    return CrisprPlan(target, cas, guide, tuple(candidates), rep, coding_first, spec.get("symbol"), tuple(sorted(sites)))


@lru_cache(maxsize=64)
def _cached(key: str) -> CrisprPlan:
    return build_crispr_plan(json.loads(key))


def plan_crispr(spec: dict[str, Any]) -> CrisprPlan:
    return _cached(json.dumps(spec, sort_keys=True, default=str))


__all__ = ["CAS", "IUPAC", "REPAIRS", "Cas", "CrisprPlan", "Guide", "RepairResult", "build_crispr_plan", "check_guide", "check_target",
           "find_guides", "pam_matches", "plan_crispr", "repair"]
