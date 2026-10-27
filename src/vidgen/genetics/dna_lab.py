"""Laboratory techniques of molecular genetics as data and rules (DESIGN.md §96.15). No manim.

- **PCR** (:func:`plan_pcr`): primers written 5′→3′ — the forward primer's sequence is on the top
  strand (it anneals to the bottom strand and is extended rightwards), the reverse primer's is the
  reverse complement of the top strand downstream (it anneals to the top strand and is extended
  leftwards); the product runs from the forward primer's 5′ end to the reverse primer's. Primer
  Tm by the Wallace rule (2 °C per A/T, 4 °C per G/C) below 14 nt, else 64.9 + 41 (G + C − 16.4)
  / N; annealing ~5 °C below the lower Tm (50–65 °C typical), denaturation 94–98 °C, extension
  72 °C (Taq polymerase, ~1 kb per minute). The strands of the first cycles are simulated exactly
  (each primer extends to the end of its template), so the defined-length product first appears
  in cycle 3; from one double-stranded template, after n cycles there are 2ⁿ molecules, 2ⁿ − 2n of
  exactly the target length (ideal doubling; real reactions plateau after ~25–35 cycles).
- **Agarose gel electrophoresis** (:func:`migration`): DNA (negative phosphate backbone) runs from
  the wells at the cathode (−) to the anode (+); within a gel's resolving range the distance is
  linear in log₁₀ of the size (larger fragments slower), compressed smoothly outside it; the range
  depends on the agarose percentage (0.5 %: ~1–30 kb … 2 %: ~50 bp–2 kb). A band's size is read
  from the ladder by log-linear interpolation between the bands around it.
- **Sanger sequencing** (:func:`sanger_trace`): a primer extended on the template with dNTPs and
  fluorescent ddNTPs (no 3′-OH: the chain stops), one fragment per position, separated by size in a
  capillary, read as a four-colour trace whose peaks give the bases 5′→3′ of the new strand; a
  heterozygous site is two overlapping peaks of about half height, called with its IUPAC code.
- **NGS** (:func:`plan_ngs`): seeded short reads from the two alleles aligned to a reference (the
  reference is a window of a longer sequence, so reads may run past its ends and are clipped to it:
  the coverage is even up to the edges), coverage per position, and a variant call from the share
  of alt reads among those covering the site (heterozygous ~50 %, homozygous ~100 %; thresholds,
  not a likelihood model). The variant is a substitution (``31C>T``) or a deletion (``6_8del``,
  ``6_8delCTT``, ``12del``): an alt read carries gaps (``-``) where the bases are missing, and only
  reads spanning the whole deleted stretch count for the call."""

from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from vidgen.errors import VidgenError

from ..cellworld.model import did_you_mean
from ..cellworld.sequences import reverse_complement

METHODS = ("pcr", "gel", "sanger", "ngs")
IUPAC_OF = {frozenset("AG"): "R", frozenset("CT"): "Y", frozenset("CG"): "S", frozenset("AT"): "W", frozenset("GT"): "K",
            frozenset("AC"): "M"}


def _dna(text: Any, where: str, lo: int = 1, hi: int = 100000) -> str:
    seq = re.sub(r"\s+", "", str(text or "")).upper()
    if not seq:
        raise VidgenError(f"{where}: give a DNA sequence (A, C, G, T)")
    for k, b in enumerate(seq):
        if b not in "ACGT":
            raise VidgenError(f"{where}: '{b}' at {k + 1} is not a DNA base (A, C, G, T)")
    if not lo <= len(seq) <= hi:
        raise VidgenError(f"{where}: {len(seq)} nt; give {lo}–{hi}")
    return seq


# ----- PCR ------------------------------------------------------------------------------------------------


def tm(primer: str) -> float:
    """Melting temperature (°C) of a primer: Wallace rule below 14 nt, else the GC formula."""
    gc = primer.count("G") + primer.count("C")
    at = len(primer) - gc
    if len(primer) < 14:
        return float(2 * at + 4 * gc)
    return 64.9 + 41.0 * (gc - 16.4) / len(primer)


@dataclass(frozen=True)
class Strand:
    """A strand in template coordinates: ``top`` (5′ at ``a``) or bottom (5′ at ``b``), covering
    ``[a, b)``; ``made`` the cycle that synthesized it (0: the original template)."""

    top: bool
    a: int
    b: int
    made: int


@dataclass(frozen=True)
class PcrPlan:
    template: str
    forward: str
    reverse: str
    f_at: int                  # top index where the forward primer's sequence starts
    r_end: int                 # top index after the reverse primer's binding site
    product: int               # bp
    tm_forward: float
    tm_reverse: float
    denature: float
    anneal: float
    extend: float
    cycles: int
    extension_seconds: float
    notes: tuple[str, ...]

    def counts(self, n: int) -> tuple[int, int]:
        """(all double-stranded molecules, those of exactly the product's length) after ``n``
        cycles from one double-stranded template molecule, counted by simulating the strands (a
        strand that covers a primer's site is copied from that primer to its own 5′ end). With
        primers inside the template this is 2ⁿ and 2ⁿ − 2n; a primer site at the template's edge
        gives the defined-length product a cycle earlier, and the counts follow."""
        exact = (self.f_at, self.r_end)
        pairs: dict[tuple[tuple[int, int], tuple[int, int]], int] = {((0, len(self.template)), (0, len(self.template))): 1}
        for _ in range(n):
            new: dict[tuple[tuple[int, int], tuple[int, int]], int] = {}
            for (top, bot), count in pairs.items():
                for key in (((top[0], top[1]), (top[0], self.r_end) if top[0] <= self.r_end - len(self.reverse) and self.r_end <= top[1] else None),
                            ((self.f_at, bot[1]) if bot[0] <= self.f_at and self.f_at + len(self.forward) <= bot[1] else None, (bot[0], bot[1]))):
                    a, b = key
                    if a is None or b is None:
                        continue
                    new[(a, b)] = new.get((a, b), 0) + count
            pairs = new
        return sum(pairs.values()), sum(c for (a, b), c in pairs.items() if a == exact and b == exact)


def pcr_strands(plan: PcrPlan, cycles: int) -> list[list[tuple[Strand, Strand]]]:
    """The double-stranded molecules after each of cycles 0…``cycles`` (exact: every strand that
    covers a primer's site is copied from that primer to its own end)."""
    n = len(plan.template)
    f0, r1 = plan.f_at, plan.r_end
    lf, lr = len(plan.forward), len(plan.reverse)
    mols: list[tuple[Strand, Strand]] = [(Strand(True, 0, n, 0), Strand(False, 0, n, 0))]
    out = [list(mols)]
    for c in range(1, cycles + 1):
        new: list[tuple[Strand, Strand]] = []
        for pair in mols:
            for s in pair:
                if s.top:      # the reverse primer anneals to a top strand covering its site; extends to the top strand's 5′ end (a)
                    if s.a <= r1 - lr and r1 <= s.b:
                        new.append((s, Strand(False, s.a, r1, c)))
                else:          # the forward primer anneals to a bottom strand covering its site; extends to its 5′ end (b)
                    if s.a <= f0 and f0 + lf <= s.b:
                        new.append((Strand(True, f0, s.b, c), s))
        mols = new
        out.append(list(mols))
    return out


def plan_pcr(spec: dict[str, Any]) -> PcrPlan:
    template = _dna(spec.get("template"), "template", 40, 5000)
    primers = spec.get("primers") or {}
    if not isinstance(primers, dict) or set(primers) - {"forward", "reverse"} or len(primers) != 2:
        raise VidgenError("primers: give {forward: 5′-…-3′, reverse: 5′-…-3′} (both written 5′→3′)")
    fwd = _dna(primers["forward"], "primers.forward")
    rev = _dna(primers["reverse"], "primers.reverse")
    for name, p in (("forward", fwd), ("reverse", rev)):
        if not 15 <= len(p) <= 35:
            raise VidgenError(f"primers.{name}: {len(p)} nt; PCR primers are 15–35 nt (18–25 typical): shorter ones bind elsewhere too")
    f_hits = [m.start() for m in re.finditer(f"(?={fwd})", template)]
    rc_f = reverse_complement(fwd)
    if not f_hits:
        if rc_f in template:
            raise VidgenError("primers.forward: it matches the bottom strand: it would anneal to the top strand and extend leftwards, away "
                              "from the region (the forward primer's sequence is the top strand's; swap the primers?)")
        raise VidgenError(f"primers.forward: {fwd} is not in the template's top strand (a forward primer repeats the top strand 5′→3′)")
    if len(f_hits) > 1:
        raise VidgenError(f"primers.forward: binds {len(f_hits)} places: the product would not be unique")
    r_site = reverse_complement(rev)
    r_hits = [m.start() for m in re.finditer(f"(?={r_site})", template)]
    if not r_hits:
        if rev in template:
            raise VidgenError(f"primers.reverse: written as the top strand; a reverse primer is the reverse complement of the top strand "
                              f"(it anneals to the top strand): write {r_site}")
        if rev[::-1] in template:
            raise VidgenError("primers.reverse: written 3′→5′ along the top strand; write the reverse complement 5′→3′")
        raise VidgenError(f"primers.reverse: its reverse complement {r_site} is not in the template's top strand")
    if len(r_hits) > 1:
        raise VidgenError(f"primers.reverse: binds {len(r_hits)} places: the product would not be unique")
    f_at, r_at = f_hits[0], r_hits[0]
    r_end = r_at + len(rev)
    if r_at < f_at + len(fwd):
        raise VidgenError("primers: the reverse primer's site is not downstream of the forward primer's: they point away from each other "
                          "(or overlap), no product")
    product = r_end - f_at
    tf, tr = tm(fwd), tm(rev)
    temps = spec.get("temperatures") or {}
    for key in temps:
        if key not in ("denature", "anneal", "extend"):
            raise VidgenError(f"temperatures: unknown key '{key}'{did_you_mean(key, ['denature', 'anneal', 'extend'])}")
    den = float(temps.get("denature", 95))
    ext = float(temps.get("extend", 72))
    suggested = round(max(50.0, min(65.0, min(tf, tr) - 5)))
    ann = float(temps.get("anneal", suggested))
    if not 90 <= den <= 99:
        raise VidgenError(f"temperatures.denature: {den:g} °C; the strands separate at 94–98 °C")
    if not 68 <= ext <= 74:
        raise VidgenError(f"temperatures.extend: {ext:g} °C; Taq polymerase extends at ~72 °C (68–74)")
    if not 40 <= ann <= 72:
        raise VidgenError(f"temperatures.anneal: {ann:g} °C; annealing is ~5 °C below the primers' Tm (50–65 °C typical)")
    low = min(tf, tr)
    if ann >= low:
        raise VidgenError(f"temperatures.anneal: {ann:g} °C is at or above a primer's Tm ({low:.0f} °C): it would not stay bound; "
                          f"anneal at ~{suggested} °C")
    cycles = int(spec.get("cycles") or 30)
    if not 1 <= cycles <= 40:
        raise VidgenError(f"cycles: {cycles}; give 1–40 (25–35 typical: the reaction plateaus)")
    notes = [f"Tm forward {tf:.0f} °C, reverse {tr:.0f} °C"]
    if abs(tf - tr) > 5:
        notes.append(f"the primers' Tm differ by {abs(tf - tr):.0f} °C (> 5): one binds less specifically")
    if ann < low - 12:
        notes.append(f"annealing far below the Tm: primers may bind mismatched sites (extra bands)")
    if product > 3000:
        notes.append(f"a {product}-bp product is long for Taq (best below ~3 kb)")
    secs = max(15.0, product / 1000 * 60)
    return PcrPlan(template, fwd, rev, f_at, r_end, product, tf, tr, den, ann, ext, cycles, secs, tuple(notes))


# ----- gel -------------------------------------------------------------------------------------------------


#: Generic DNA size ladders (bp).
LADDERS = {
    "1kb": (10000, 8000, 6000, 5000, 4000, 3000, 2000, 1500, 1000, 500),
    "100bp": (1500, 1200, 1000, 900, 800, 700, 600, 500, 400, 300, 200, 100),
    "50bp": (1000, 750, 500, 400, 300, 250, 200, 150, 100, 50),
}
#: Resolving range (bp) of an agarose percentage (standard tables).
RANGES = ((0.5, 1000, 30000), (0.7, 800, 12000), (1.0, 500, 10000), (1.2, 400, 7000), (1.5, 200, 3000), (2.0, 50, 2000),
          (3.0, 20, 1000))


def resolving_range(agarose: float) -> tuple[float, float]:
    """The sizes (bp) a gel of ``agarose`` % separates well, interpolated in the standard table."""
    pts = RANGES
    if agarose <= pts[0][0]:
        return float(pts[0][1]), float(pts[0][2])
    for (p0, a0, b0), (p1, a1, b1) in zip(pts, pts[1:]):
        if agarose <= p1:
            t = (agarose - p0) / (p1 - p0)
            return math.exp(math.log(a0) + t * (math.log(a1) - math.log(a0))), math.exp(math.log(b0) + t * (math.log(b1) - math.log(b0)))
    return float(pts[-1][1]), float(pts[-1][2])


def migration(size: float, agarose: float) -> float:
    """Where a fragment ends (0 the well, 1 the gel's end) after a full run: linear in log₁₀(size)
    over the resolving range (0.1–0.9), compressed smoothly beyond it; strictly decreasing in size."""
    lo, hi = resolving_range(agarose)
    x = (math.log10(hi) - math.log10(size)) / (math.log10(hi) - math.log10(lo))
    u = 0.1 + 0.8 * x
    if u > 0.9:
        return 0.9 + 0.08 * (1 - math.exp(-(u - 0.9) / 0.08))
    if u < 0.1:
        return 0.1 - 0.08 * (1 - math.exp(-(0.1 - u) / 0.08))
    return u


def size_from_distance(d: float, ladder: tuple[float, ...], agarose: float) -> float:
    """A band's size read from the ladder: log-linear interpolation between the two ladder bands
    around distance ``d`` (extrapolated from the nearest two outside the ladder)."""
    pts = sorted((migration(s, agarose), s) for s in ladder)
    for (d0, s0), (d1, s1) in zip(pts, pts[1:]):
        if d0 <= d <= d1:
            t = (d - d0) / (d1 - d0)
            return 10 ** (math.log10(s0) + t * (math.log10(s1) - math.log10(s0)))
    (d0, s0), (d1, s1) = (pts[0], pts[1]) if d < pts[0][0] else (pts[-2], pts[-1])
    t = (d - d0) / (d1 - d0)
    return 10 ** (math.log10(s0) + t * (math.log10(s1) - math.log10(s0)))


@dataclass(frozen=True)
class Lane:
    label: str
    sizes: tuple[float, ...]
    ladder: bool = False


@dataclass(frozen=True)
class GelPlan:
    lanes: tuple[Lane, ...]
    agarose: float
    ladder: tuple[float, ...]
    ladder_name: str
    notes: tuple[str, ...]


def plan_gel(spec: dict[str, Any]) -> GelPlan:
    agarose = float(spec.get("agarose") or 1.0)
    if not 0.5 <= agarose <= 3.0:
        raise VidgenError(f"agarose: {agarose:g} %; agarose gels are 0.5–3 %")
    ladder_spec = spec.get("ladder", "100bp")
    if isinstance(ladder_spec, str):
        if ladder_spec not in LADDERS:
            raise VidgenError(f"ladder: '{ladder_spec}'{did_you_mean(ladder_spec, list(LADDERS))} ({', '.join(LADDERS)}, or a list of sizes)")
        ladder = LADDERS[ladder_spec]
        name = ladder_spec.replace("kb", " kb").replace("bp", " bp")
    else:
        ladder = tuple(sorted((float(s) for s in ladder_spec), reverse=True))
        if len(ladder) < 3:
            raise VidgenError("ladder: give at least three sizes")
        name = "ladder"
    lanes_spec = spec.get("lanes")
    if not lanes_spec:
        raise VidgenError("lanes: give the samples ({PCR: [450], digest: [300, 150]} or [{label: PCR, sizes: [450]}])")
    items = list(lanes_spec.items()) if isinstance(lanes_spec, dict) else [(d.get("label", f"lane {k + 1}"), d.get("sizes")) for k, d in
                                                                           enumerate(lanes_spec)]
    lanes = [Lane(name, ladder, True)]
    for label, sizes in items:
        vals = sizes if isinstance(sizes, list) else [sizes]
        try:
            fs = tuple(float(s) for s in vals)
        except (TypeError, ValueError):
            raise VidgenError(f"lanes: '{label}': give fragment sizes in bp ([450] or [300, 150])") from None
        if not fs or any(s < 10 or s > 50000 for s in fs):
            raise VidgenError(f"lanes: '{label}': sizes from 10 bp to 50 kb")
        lanes.append(Lane(str(label), fs))
    if len(lanes) > 10:
        raise VidgenError(f"lanes: {len(lanes) - 1} samples; a gel here has room for 9 beside the ladder")
    lo, hi = resolving_range(agarose)
    notes = []
    for lane in lanes[1:]:
        out = [s for s in lane.sizes if not lo <= s <= hi]
        if out:
            notes.append(f"{lane.label}: {', '.join(f'{s:g}' for s in out)} bp lies outside a {agarose:g} % gel's range "
                         f"(~{lo:.0f}–{hi:.0f} bp): poorly resolved")
        close = [(a, b) for a in lane.sizes for b in lane.sizes if a > b and abs(migration(a, agarose) - migration(b, agarose)) < 0.02]
        if close:
            notes.append(f"{lane.label}: {close[0][0]:g} and {close[0][1]:g} bp run as one band at {agarose:g} %")
    if not any(min(ladder) <= s <= max(ladder) for lane in lanes[1:] for s in lane.sizes):
        notes.append("no sample band lies within the ladder's sizes: sizes are extrapolated")
    return GelPlan(tuple(lanes), agarose, ladder, name, tuple(notes))


# ----- Sanger -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SangerPlan:
    read: str                         # the new strand's bases 5′→3′ (reference)
    calls: str                        # called bases (IUPAC code at a heterozygous site)
    het: dict[int, str]               # index → the second base at a heterozygous site
    heights: tuple[float, ...]
    primer: str
    template: str                     # the template strand 3′→5′ under the read


def plan_sanger(spec: dict[str, Any]) -> SangerPlan:
    read = _dna(spec.get("sequence"), "sequence", 8, 40)
    het: dict[int, str] = {}
    hz = spec.get("heterozygous")
    if hz:
        items = hz if isinstance(hz, list) else [hz]
        for k, item in enumerate(items):
            m = re.fullmatch(r"(\d+)([ACGT])>([ACGT])", str(item).strip())
            if not m:
                raise VidgenError(f"heterozygous: '{item}': write a position in the read and its two bases: 12A>G")
            pos, ref, alt = int(m.group(1)), m.group(2), m.group(3)
            if not 1 <= pos <= len(read):
                raise VidgenError(f"heterozygous: '{item}': the read has positions 1–{len(read)}")
            if read[pos - 1] != ref:
                raise VidgenError(f"heterozygous: '{item}': position {pos} of the read is {read[pos - 1]}, not {ref}")
            if ref == alt:
                raise VidgenError(f"heterozygous: '{item}': the two bases are the same")
            het[pos - 1] = alt
    rng = random.Random(f"sanger:{spec.get('seed', 1)}")
    heights = tuple(0.62 + 0.38 * rng.random() for _ in read)
    calls = "".join(IUPAC_OF[frozenset((b, het[i]))] if i in het else b for i, b in enumerate(read))
    primer = _dna(spec.get("primer"), "primer", 15, 35) if spec.get("primer") else ""
    template = reverse_complement(read)[::-1]
    return SangerPlan(read, calls, het, heights, primer, template)


# ----- NGS ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Read:
    start: int
    seq: str                          # aligned to the reference: '-' where a deletion removed a base
    alt: bool                         # from the alt allele
    reverse: bool                     # mapped to the reverse strand
    errors: tuple[int, ...]           # indices (in the read) of sequencing errors


@dataclass(frozen=True)
class NgsPlan:
    reference: str
    position: int                     # 0-based index of the variant
    ref: str
    alt: str
    zygosity: str
    reads: tuple[Read, ...]
    depth: tuple[int, ...]            # coverage per position
    alt_reads: int
    call: str                         # heterozygous, homozygous, none, low coverage
    vaf: float
    read_length: int
    end: int = -1                     # 0-based index past the variant (a deletion's last base + 1)
    kind: str = "substitution"        # or "deletion" (alt is "")
    site_depth: int = 0               # reads covering the whole site (the call's denominator)

    @property
    def site(self) -> str:
        """The variant in the reference's numbering: ``26G>T``, ``6_8delCTT``."""
        if self.kind == "deletion":
            span = f"{self.position + 1}" if self.end - self.position == 1 else f"{self.position + 1}_{self.end}"
            return f"{span}del{self.ref}"
        return f"{self.position + 1}{self.ref}>{self.alt}"


#: The least a clipped read overlaps the reference (bases).
MIN_OVERLAP = 5


def _ngs_variant(v: str, ref_seq: str) -> tuple[int, int, str, str, str]:
    """(0-based start, end, ref bases, alt bases, kind) of an NGS variant."""
    n = len(ref_seq)
    sub = re.fullmatch(r"(\d+)([ACGT])>([ACGT])", v)
    dele = re.fullmatch(r"(\d+)(?:_(\d+))?del([ACGT]*)", v)
    if sub:
        pos, ref, alt = int(sub.group(1)), sub.group(2), sub.group(3)
        if not 1 <= pos <= n:
            raise VidgenError(f"variant: '{v}': the reference has positions 1–{n}")
        if ref_seq[pos - 1] != ref:
            raise VidgenError(f"variant: '{v}': position {pos} of the reference is {ref_seq[pos - 1]}, not {ref}")
        if ref == alt:
            raise VidgenError(f"variant: '{v}': no change")
        return pos - 1, pos, ref, alt, "substitution"
    if dele:
        a = int(dele.group(1))
        b = int(dele.group(2)) if dele.group(2) else a
        if b < a:
            raise VidgenError(f"variant: '{v}': write the range low to high ({b}_{a}del)")
        if a < 1 or b > n:
            raise VidgenError(f"variant: '{v}': the reference has positions 1–{n}")
        if b - a + 1 > 12:
            raise VidgenError(f"variant: '{v}': {b - a + 1} bases; deletions here are 1–12 bp (a short-read call)")
        if a == 1 or b == n:
            raise VidgenError(f"variant: '{v}': keep a base of the reference on both sides of the deletion")
        ref = ref_seq[a - 1:b]
        if dele.group(3) and dele.group(3) != ref:
            raise VidgenError(f"variant: '{v}': positions {a}–{b} of the reference are {ref}, not {dele.group(3)}")
        return a - 1, b, ref, "", "deletion"
    raise VidgenError(f"variant: '{v}': write a position in the reference and the change: 31C>T, or a deletion: 6_8del")


def plan_ngs(spec: dict[str, Any]) -> NgsPlan:
    ref_seq = _dna(spec.get("reference"), "reference", 30, 120)
    v = str(spec.get("variant") or "").strip()
    i, end, ref, alt, kind = _ngs_variant(v, ref_seq)
    zyg = str(spec.get("zygosity") or "heterozygous")
    shares = {"heterozygous": 0.5, "homozygous": 1.0, "absent": 0.0}
    if zyg not in shares:
        raise VidgenError(f"zygosity: '{zyg}'{did_you_mean(zyg, list(shares))} ({', '.join(shares)})")
    L = int(spec.get("read_length") or 25)
    if not 10 <= L <= len(ref_seq) - 5:
        raise VidgenError(f"read_length: {L}; give 10 to {len(ref_seq) - 5} (reads shorter than the reference)")
    depth_goal = int(spec.get("depth") or 20)
    if not 4 <= depth_goal <= 40:
        raise VidgenError(f"depth: {depth_goal}; give 4–40 (the expected reads over the middle of the reference; a clinical call "
                          f"wants ≥ 20)")
    err = float(spec.get("error_rate", 0.005))
    if not 0 <= err <= 0.05:
        raise VidgenError(f"error_rate: {err:g}; give 0–0.05 (per base; Illumina ~0.001–0.01)")
    rng = random.Random(f"ngs:{spec.get('seed', 1)}")
    n = len(ref_seq)
    lo, hi = MIN_OVERLAP - L, n - MIN_OVERLAP     # a read's first base (it may start before the window)
    n_reads = max(1, round(depth_goal * (hi - lo + 1) / L))
    alt_seq = ref_seq[:i] + (alt or "-" * (end - i)) + ref_seq[end:]   # aligned: a deletion as gaps
    reads = []
    for _ in range(n_reads):
        s = rng.randint(lo, hi)
        is_alt = rng.random() < shares[zyg]
        a, b = max(0, s), min(n, s + L)
        src = alt_seq if is_alt else ref_seq
        bases = list(src[a:b])
        errs = []
        for k in range(len(bases)):
            if rng.random() < err and bases[k] != "-":
                bases[k] = rng.choice([c for c in "ACGT" if c != bases[k]])
                errs.append(k)
        reads.append(Read(a, "".join(bases), is_alt, rng.random() < 0.5, tuple(errs)))
    reads.sort(key=lambda r: (r.start, r.reverse))
    depth = [0] * n
    for r in reads:
        for k in range(len(r.seq)):
            depth[r.start + k] += 1
    covering = [r for r in reads if r.start <= i and end <= r.start + len(r.seq)]
    if kind == "deletion":
        alt_n = sum(1 for r in covering if r.seq[i - r.start] == "-")
    else:
        alt_n = sum(1 for r in covering if r.seq[i - r.start] == alt)
    d = len(covering)
    vaf = alt_n / d if d else 0.0
    if d < 10:
        call = "low coverage"
    elif vaf >= 0.85:
        call = "homozygous"
    elif vaf >= 0.15:
        call = "heterozygous"
    else:
        call = "none"
    return NgsPlan(ref_seq, i, ref, alt, zyg, tuple(reads), tuple(depth), alt_n, call, vaf, L, end, kind, d)


def pack_rows(reads: tuple[Read, ...], gap: int = 1) -> list[int]:
    """A row per read so reads in a row do not touch (greedy, in start order)."""
    ends: list[int] = []
    rows = []
    for r in reads:
        for k, e in enumerate(ends):
            if r.start >= e + gap:
                ends[k] = r.start + len(r.seq)
                rows.append(k)
                break
        else:
            ends.append(r.start + len(r.seq))
            rows.append(len(ends) - 1)
    return rows


# ----- the plan -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LabPlan:
    method: str
    pcr: PcrPlan | None = None
    gel: GelPlan | None = None
    sanger: SangerPlan | None = None
    ngs: NgsPlan | None = None


_KEYS = {
    "pcr": ("template", "primers", "temperatures", "cycles"),
    "gel": ("agarose", "ladder", "lanes"),
    "sanger": ("sequence", "heterozygous", "primer"),
    "ngs": ("reference", "variant", "zygosity", "read_length", "depth", "error_rate"),
}


def build_lab_plan(spec: dict[str, Any]) -> LabPlan:
    method = str(spec.get("method") or "pcr")
    if method not in METHODS:
        raise VidgenError(f"method: '{method}'{did_you_mean(method, list(METHODS))} ({', '.join(METHODS)})")
    for other, keys in _KEYS.items():
        if other == method:
            continue
        for k in keys:
            if spec.get(k) is not None and k not in _KEYS[method]:
                raise VidgenError(f"{k}: is a param of method: {other}, not {method}")
    if method == "pcr":
        return LabPlan(method, pcr=plan_pcr(spec))
    if method == "gel":
        return LabPlan(method, gel=plan_gel(spec))
    if method == "sanger":
        return LabPlan(method, sanger=plan_sanger(spec))
    return LabPlan(method, ngs=plan_ngs(spec))


@lru_cache(maxsize=64)
def _cached(key: str) -> LabPlan:
    return build_lab_plan(json.loads(key))


def plan_lab(spec: dict[str, Any]) -> LabPlan:
    # not sort_keys: the lanes of a gel are drawn in the order they are written
    return _cached(json.dumps(spec, default=str))


__all__ = ["IUPAC_OF", "LADDERS", "METHODS", "RANGES", "GelPlan", "LabPlan", "Lane", "NgsPlan", "PcrPlan", "Read", "SangerPlan", "Strand",
           "build_lab_plan", "migration", "pack_rows", "pcr_strands", "plan_gel", "plan_lab", "plan_ngs", "plan_pcr", "plan_sanger",
           "resolving_range", "size_from_distance", "tm"]
