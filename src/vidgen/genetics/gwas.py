"""Genome-wide association studies (DESIGN.md §96.17): the data of a Manhattan plot, a QQ plot and
a regional plot for the ``gwas`` scene. No manim.

- **Data**: author-given variants (a CSV in the project or inline ``variants``) or a seeded
  synthetic study — a null background (p uniform; optionally inflated by λ) over the autosomes in
  proportion to their GRCh38 lengths, and the author's ``peaks``, each a lead variant with the
  variants around it in linkage disequilibrium: r² falls with distance, and a neighbour's test
  statistic follows the lead's, z_i = r_i z_lead + √(1 − r_i²) ε (so its expected χ² is about
  r² χ²_lead). Synthetic data is labelled as such on screen.
- **p-values** are kept as −log₁₀ p (from numbers or strings: ``5e-8``, ``"3e-450"`` beyond
  floating point, via ``decimal``); 0 < p ≤ 1.
- **Thresholds**: genome-wide significance 5 × 10⁻⁸ (−log₁₀ = 7.30), suggestive 1 × 10⁻⁵ (5).
- **λ_GC** = median of the χ²₁ statistics / 0.4549 (the χ²₁ median); the QQ plot's expected
  −log₁₀ p of the i-th smallest p of n is −log₁₀((i − 0.5)/n).
- **Peaks** of author data: lead variants clumped greedily (the smallest p, then nothing else as a
  lead within ``clump_kb``), the significant ones labelled with their gene / id."""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any, Mapping, Sequence

import numpy as np

from vidgen.cellworld.model import did_you_mean
from vidgen.errors import VidgenError

from .karyotype import AUTOSOMES, LENGTH_MB

#: Genome-wide significance and the suggestive line (p).
SIGNIFICANCE, SUGGESTIVE = 5e-8, 1e-5
#: The median of the χ² distribution with one degree of freedom.
CHI2_MEDIAN = 0.454936423119572
#: Chromosomes a Manhattan plot can show (autosomes and X).
CHROMOSOMES = AUTOSOMES + ("X",)
#: Synthetic study: background variants; variants around each peak; the peak's window (Mb each side).
BACKGROUND, PEAK_VARIANTS, WINDOW_MB = 2400, 48, 0.4
#: Synthetic LD: r² with the lead falls as exp(−distance / this) (times a seeded factor 0.55–1).
LD_DECAY_MB = 0.15
#: Most points drawn on a Manhattan plot (the rest of the null background thinned).
MAX_DRAWN = 4000
#: The r² bins of a regional plot.
R2_BINS = (0.2, 0.4, 0.6, 0.8)


def mlog10(value: Any, where: str = "p") -> float:
    """−log₁₀ p from a number or a string (``5e-8``, ``"3e-450"``); 0 < p ≤ 1."""
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        d = Decimal(str(value).strip().replace("×10^", "e").replace("x10^", "e"))
    except (InvalidOperation, ValueError):
        raise VidgenError(f"{where}: p-value '{value}' is not a number (write 5e-8 or 0.00001)") from None
    if not d.is_finite() or d <= 0 or d > 1:
        raise VidgenError(f"{where}: p-value {value} is out of range: a p-value lies in (0, 1]")
    return float(-d.log10())


def mlog10_of_z(z: float) -> float:
    """−log₁₀ of the two-sided p of a z score (asymptotic beyond the float range)."""
    z = abs(z)
    if z < 37.0:
        p = math.erfc(z / math.sqrt(2.0))
        return -math.log10(p) if p > 0 else 0.0
    x = z / math.sqrt(2.0)
    ln_erfc = -x * x - math.log(x * math.sqrt(math.pi)) + math.log1p(-1 / (2 * x * x))
    return -ln_erfc / math.log(10)


def z_of_mlog10(m: float) -> float:
    """The |z| whose two-sided p has −log₁₀ p = ``m`` (bisection)."""
    if m <= 0:
        return 0.0
    lo, hi = 0.0, 5.0
    while mlog10_of_z(hi) < m:
        hi *= 2
    for _ in range(80):
        mid = (lo + hi) / 2
        if mlog10_of_z(mid) < m:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def chromosome(value: Any, where: str) -> str:
    """``1``–``22`` or ``X`` (``chr7``, ``23`` for X)."""
    text = str(value).strip()
    key = text[3:] if text.lower().startswith("chr") else text
    key = "X" if key.upper() in ("X", "23") else key
    if key not in CHROMOSOMES:
        extra = " (Y and mitochondrial variants are not drawn on this Manhattan plot)" if key.upper() in ("Y", "24", "M", "MT") else ""
        raise VidgenError(f"{where}: unknown chromosome '{text}': use 1–22 or X{extra}{did_you_mean(key, list(CHROMOSOMES))}")
    return key


def position(value: Any, chrom: str, where: str) -> float:
    """A position in Mb from base pairs (``53800000``) or text (``"53.8 Mb"``, ``"420 kb"``); within
    the chromosome's GRCh38 length."""
    text = str(value).strip().replace("_", "").replace(",", "")
    scale = 1e-6
    for unit, s in (("mb", 1.0), ("kb", 1e-3), ("bp", 1e-6)):
        if text.lower().endswith(unit):
            text, scale = text[: -len(unit)].strip(), s
            break
    try:
        v = float(text)
    except ValueError:
        raise VidgenError(f"{where}: position '{value}' is not a number (base pairs, or '53.8 Mb')") from None
    if scale == 1e-6 and 0 < v < 1000:
        raise VidgenError(f"{where}: position {value}: positions are in base pairs; write {int(v * 1e6)} or '{v:g} Mb'")
    mb = v * scale
    if not 0 <= mb <= LENGTH_MB[chrom] + 0.01:
        raise VidgenError(f"{where}: position {mb:.2f} Mb is beyond the end of chromosome {chrom} ({LENGTH_MB[chrom]:.1f} Mb in GRCh38)")
    return mb


@dataclass(frozen=True)
class Variant:
    """A tested variant: chromosome, position (Mb), −log₁₀ p, its id, r² with its peak's lead,
    the peak it belongs to (index) and whether it is the lead."""

    chrom: str
    pos: float
    mlog10p: float
    id: str = ""
    r2: float | None = None
    peak: int | None = None
    lead: bool = False


@dataclass(frozen=True)
class Peak:
    """A labelled association: its lead variant, label (the gene, else the id), gene, the window."""

    label: str
    lead: Variant
    gene: str = ""
    start: float = 0.0
    end: float = 0.0

    @property
    def significant(self) -> bool:
        return self.lead.mlog10p >= -math.log10(SIGNIFICANCE)

    @property
    def target(self) -> str:
        return f"peak:{self.label}"


@dataclass(frozen=True)
class GwasPlan:
    """A study: its variants (in genome order), peaks, chromosomes shown and their start on the
    genome axis (Mb, with a gap between chromosomes), whether the data is synthetic, λ_GC, the
    QQ points (expected, observed −log₁₀ p, largest first) and the counts."""

    variants: tuple[Variant, ...]
    peaks: tuple[Peak, ...]
    chromosomes: tuple[str, ...]
    offsets: dict[str, float]
    genome: float
    synthetic: bool
    lambda_gc: float
    qq: tuple[tuple[float, float], ...]
    n_significant: int
    n_suggestive: int
    trait: str = ""
    notes: tuple[str, ...] = ()

    def x(self, v: Variant) -> float:
        return self.offsets[v.chrom] + v.pos

    def centre(self, chrom: str) -> float:
        return self.offsets[chrom] + LENGTH_MB[chrom] / 2

    def peak(self, label: str) -> Peak | None:
        return next((p for p in self.peaks if p.label == label), None)

    def regional(self, peak: Peak) -> list[Variant]:
        return [v for v in self.variants if v.chrom == peak.lead.chrom and peak.start <= v.pos <= peak.end]

    def drawn(self) -> list[Variant]:
        """The points drawn on the Manhattan plot: all, or the null background thinned to
        :data:`MAX_DRAWN` (every variant with p < 0.01 kept)."""
        if len(self.variants) <= MAX_DRAWN:
            return list(self.variants)
        keep = [v for v in self.variants if v.mlog10p >= 2 or v.peak is not None]
        rest = [v for v in self.variants if not (v.mlog10p >= 2 or v.peak is not None)]
        room = max(0, MAX_DRAWN - len(keep))
        stride = max(1, math.ceil(len(rest) / room)) if room else len(rest) + 1
        chosen = keep + rest[::stride]
        return sorted(chosen, key=lambda v: (CHROMOSOMES.index(v.chrom), v.pos))


def _offsets(chroms: Sequence[str]) -> tuple[dict[str, float], float]:
    gap = 12.0
    out: dict[str, float] = {}
    x = 0.0
    for c in chroms:
        out[c] = x
        x += LENGTH_MB[c] + gap
    return out, x - gap


def _peak_specs(value: Any, where: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise VidgenError(f"{where}: a list of peaks, e.g. [{{chromosome: 16, position: 53.8 Mb, p: 1e-40, gene: FTO, variant: rs9939609}}]")
    out = []
    allowed = ("chromosome", "position", "p", "gene", "variant", "label")
    for k, raw in enumerate(value):
        w = f"{where}[{k}]"
        if not isinstance(raw, Mapping):
            raise VidgenError(f"{w}: a peak is a mapping with chromosome, position, p and gene or variant")
        for key in raw:
            if key not in allowed:
                raise VidgenError(f"{w}: unknown key '{key}': use {', '.join(allowed)}{did_you_mean(str(key), list(allowed))}")
        for key in ("chromosome", "position", "p"):
            if raw.get(key) is None:
                raise VidgenError(f"{w}: {key} is needed")
        c = chromosome(raw["chromosome"], f"{w}.chromosome")
        out.append({"chrom": c, "pos": position(raw["position"], c, f"{w}.position"), "m": mlog10(raw["p"], f"{w}.p"),
                    "gene": str(raw.get("gene") or ""), "id": str(raw.get("variant") or ""), "label": str(raw.get("label") or "")})
    return out


def _label(gene: str, vid: str, chrom: str, pos: float, explicit: str = "") -> str:
    return explicit or gene or vid or f"chr{chrom}:{pos:.1f}Mb"


def synthetic(spec: Mapping[str, Any], where: str = "params") -> tuple[list[Variant], list[Peak], tuple[str, ...]]:
    """A seeded synthetic study: a null background and the author's peaks with LD around them."""
    seed = int(spec.get("seed", 1))
    rng = np.random.default_rng(seed)
    chroms = CHROMOSOMES if spec.get("x_chromosome") else AUTOSOMES
    n_bg = int(spec.get("background") or BACKGROUND)
    if not 200 <= n_bg <= 20000:
        raise VidgenError(f"{where}.background: {n_bg}: between 200 and 20000 background variants")
    lam = float(spec.get("inflation") or 1.0)
    if not 0.5 <= lam <= 3.0:
        raise VidgenError(f"{where}.inflation: {lam:g}: λ between 0.5 and 3 (1 = no inflation)")
    lengths = np.array([LENGTH_MB[c] for c in chroms])
    counts = np.floor(lengths / lengths.sum() * n_bg).astype(int)
    counts[: n_bg - counts.sum()] += 1
    variants: list[Variant] = []
    for c, n in zip(chroms, counts):
        pos = np.sort(rng.uniform(0.5, LENGTH_MB[c] - 0.5, n))
        u = rng.uniform(1e-12, 1.0, n)
        for x, pu in zip(pos, u):
            m = -math.log10(pu)
            if lam != 1.0:
                m = mlog10_of_z(z_of_mlog10(m) * math.sqrt(lam))
            variants.append(Variant(c, float(x), m))
    peaks: list[Peak] = []
    for k, ps in enumerate(_peak_specs(spec.get("peaks"), f"{where}.peaks")):
        if ps["chrom"] not in chroms:
            raise VidgenError(f"{where}.peaks[{k}]: chromosome X is not on this plot: set x_chromosome: true")
        z0 = z_of_mlog10(ps["m"])
        start, end = max(0.0, ps["pos"] - WINDOW_MB), min(LENGTH_MB[ps["chrom"]], ps["pos"] + WINDOW_MB)
        lead = Variant(ps["chrom"], ps["pos"], ps["m"], ps["id"] or f"chr{ps['chrom']}:{round(ps['pos'] * 1e6)}", 1.0, k, True)
        variants.append(lead)
        # half the variants in the lead's LD block (±80 kb), half across the window
        offs = np.concatenate([rng.uniform(-0.08, 0.08, PEAK_VARIANTS // 2), rng.uniform(-WINDOW_MB, WINDOW_MB, PEAK_VARIANTS // 2)])
        for d in offs:
            x = ps["pos"] + float(d)
            if not start <= x <= end or abs(d) < 1e-4:
                continue
            r2 = float(min(1.0, math.exp(-abs(d) / LD_DECAY_MB) * rng.uniform(0.55, 1.0)))
            z = math.sqrt(r2) * z0 + math.sqrt(1 - r2) * float(rng.standard_normal())
            variants.append(Variant(ps["chrom"], x, mlog10_of_z(z), "", r2, k))
        peaks.append(Peak(_label(ps["gene"], ps["id"], ps["chrom"], ps["pos"], ps["label"]), lead, ps["gene"], start, end))
    _unique_labels(peaks, where)
    # background variants inside a peak's window: weak LD with its lead
    out = []
    for v in variants:
        if v.peak is None:
            for k, pk in enumerate(peaks):
                if v.chrom == pk.lead.chrom and pk.start <= v.pos <= pk.end:
                    v = Variant(v.chrom, v.pos, v.mlog10p, v.id, float(rng.uniform(0.0, 0.12)), None)
                    break
        out.append(v)
    out.sort(key=lambda v: (CHROMOSOMES.index(v.chrom), v.pos))
    return out, peaks, chroms


def _unique_labels(peaks: list[Peak], where: str) -> None:
    seen: set[str] = set()
    for pk in peaks:
        if pk.label in seen:
            raise VidgenError(f"{where}.peaks: two peaks are labelled '{pk.label}'; give one a label: (e.g. {pk.label}-2)")
        seen.add(pk.label)


COLUMNS = {
    "chrom": ("chromosome", "chrom", "chr", "#chrom"),
    "pos": ("position", "pos", "bp", "base_pair_location"),
    "p": ("p", "pval", "p_value", "pvalue", "p-value"),
    "id": ("variant", "snp", "rsid", "id", "variant_id", "marker"),
    "gene": ("gene", "nearest_gene"),
    "r2": ("r2", "ld", "r²"),
}


def read_rows(text: str, where: str) -> list[dict[str, Any]]:
    """Rows of a CSV (or TSV) with columns chromosome, position (bp), p and optionally variant,
    gene, r2 (several usual names each: CHR, BP, P, SNP …)."""
    sample = text[:2000]
    delim = "\t" if sample.count("\t") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        header = next(reader)
    except StopIteration:
        raise VidgenError(f"{where}: the file is empty") from None
    cols: dict[str, int] = {}
    for i, name in enumerate(header):
        key = name.strip().lower()
        for field, names in COLUMNS.items():
            if key in names and field not in cols:
                cols[field] = i
    for need in ("chrom", "pos", "p"):
        if need not in cols:
            raise VidgenError(f"{where}: no {COLUMNS[need][0]} column (the header has {', '.join(header)}; "
                              f"use one of {', '.join(COLUMNS[need])})")
    rows = []
    for n, row in enumerate(reader, start=2):
        if not row or all(not c.strip() for c in row):
            continue
        rows.append({f: row[i].strip() if i < len(row) else "" for f, i in cols.items()} | {"line": n})
    return rows


def author_variants(rows: Sequence[Mapping[str, Any]], where: str) -> list[Variant]:
    out = []
    for k, r in enumerate(rows):
        w = f"{where}, line {r['line']}" if "line" in r else f"{where}[{k}]"
        for need in ("chrom", "pos", "p"):
            if r.get(need) in (None, ""):
                raise VidgenError(f"{w}: {('chromosome', 'position', 'p')[('chrom', 'pos', 'p').index(need)]} is needed")
        c = chromosome(r["chrom"], w)
        r2 = None
        if r.get("r2") not in (None, ""):
            try:
                r2 = float(r["r2"])
            except ValueError:
                raise VidgenError(f"{w}: r2 '{r['r2']}' is not a number") from None
            if not 0 <= r2 <= 1:
                raise VidgenError(f"{w}: r2 {r2:g} is outside [0, 1]")
        out.append(Variant(c, position(r["pos"], c, w), mlog10(r["p"], w), str(r.get("id") or ""), r2))
    if len(out) < 3:
        raise VidgenError(f"{where}: at least 3 variants are needed for a plot")
    if len(out) > 2_000_000:
        raise VidgenError(f"{where}: {len(out)} variants; keep at most 2 000 000 (thin the null background first)")
    out.sort(key=lambda v: (CHROMOSOMES.index(v.chrom), v.pos))
    return out


def clump(variants: list[Variant], labels: Mapping[str, str], clump_kb: float, threshold: float) -> tuple[list[Variant], list[Peak]]:
    """Lead variants: the smallest p first, nothing within ``clump_kb`` of a lead becomes another."""
    order = sorted(range(len(variants)), key=lambda i: -variants[i].mlog10p)
    leads: list[int] = []
    for i in order:
        v = variants[i]
        if v.mlog10p < threshold:
            break
        if any(variants[j].chrom == v.chrom and abs(variants[j].pos - v.pos) * 1000 <= clump_kb for j in leads):
            continue
        leads.append(i)
    peaks = []
    out = list(variants)
    for k, i in enumerate(leads):
        v = variants[i]
        gene = labels.get(v.id, "")
        win = clump_kb / 1000
        start, end = max(0.0, v.pos - win), min(LENGTH_MB[v.chrom], v.pos + win)
        lead = Variant(v.chrom, v.pos, v.mlog10p, v.id, v.r2 if v.r2 is not None else 1.0, k, True)
        out[i] = lead
        peaks.append(Peak(_label(gene, v.id, v.chrom, v.pos), lead, gene, start, end))
    for j, v in enumerate(out):
        if v.lead:
            continue
        for k, pk in enumerate(peaks):
            if v.chrom == pk.lead.chrom and pk.start <= v.pos <= pk.end:
                out[j] = Variant(v.chrom, v.pos, v.mlog10p, v.id, v.r2, k)
                break
    return out, peaks


def lambda_gc(variants: Sequence[Variant]) -> float:
    """Genomic inflation: the median χ²₁ over the χ²₁ median (from the median −log₁₀ p)."""
    ms = sorted(v.mlog10p for v in variants)
    mid = len(ms) // 2
    med = ms[mid] if len(ms) % 2 else (ms[mid - 1] + ms[mid]) / 2
    return z_of_mlog10(med) ** 2 / CHI2_MEDIAN


def qq_points(variants: Sequence[Variant], most: int = 600) -> tuple[tuple[float, float], ...]:
    """(expected, observed) −log₁₀ p, largest first; the low end thinned to about ``most``."""
    obs = sorted((v.mlog10p for v in variants), reverse=True)
    n = len(obs)
    pts = [(-math.log10((i + 0.5) / n), o) for i, o in enumerate(obs)]
    keep = [pt for pt in pts if pt[0] >= 1.0]
    rest = [pt for pt in pts if pt[0] < 1.0]
    stride = max(1, math.ceil(len(rest) / max(1, most - len(keep))))
    return tuple(keep + rest[::stride] + ([rest[-1]] if rest and (len(rest) - 1) % stride else []))


def build_gwas_plan(spec: Mapping[str, Any], where: str = "params") -> GwasPlan:
    """The study from ``rows`` (read from a CSV or ``variants``) or a synthetic one with ``peaks``."""
    rows = spec.get("rows")
    if rows is None and spec.get("variants") is not None:
        raw = spec["variants"]
        if not isinstance(raw, list):
            raise VidgenError(f"{where}.variants: a list of {{chromosome, position, p, variant?, gene?, r2?}}")
        rows = []
        for k, r in enumerate(raw):
            if not isinstance(r, Mapping):
                raise VidgenError(f"{where}.variants[{k}]: a mapping with chromosome, position and p")
            rows.append({"chrom": r.get("chromosome"), "pos": r.get("position"), "p": r.get("p"), "id": r.get("variant", ""),
                         "gene": r.get("gene", ""), "r2": r.get("r2")})
    labels = dict(spec.get("labels") or {})
    synth = rows is None
    if synth:
        variants, peaks, chroms = synthetic(spec, where)
    else:
        if spec.get("peaks"):
            raise VidgenError(f"{where}.peaks: peaks make a synthetic study; with your own data label the leads with labels: {{rs9939609: FTO}}")
        variants = author_variants(rows, where if spec.get("data") is None else str(spec["data"]))
        for r in rows:
            if r.get("gene") and r.get("id"):
                labels.setdefault(str(r["id"]), str(r["gene"]))
        threshold = -math.log10(float(spec.get("label_p") or SIGNIFICANCE))
        variants, peaks = clump(variants, labels, float(spec.get("clump_kb") or 500), threshold)
        chroms = CHROMOSOMES if any(v.chrom == "X" for v in variants) or spec.get("x_chromosome") else AUTOSOMES
    offsets, genome = _offsets(chroms)
    sig = -math.log10(SIGNIFICANCE)
    sug = -math.log10(SUGGESTIVE)
    # a synthetic study shows a few thousand variants where a real one tests millions, so its peaks'
    # variants would be a far larger share than they are: λ comes from its null background
    lam = lambda_gc([v for v in variants if v.peak is None] if synth else variants)
    notes = []
    if synth:
        notes.append(f"simulated data: {len(variants):,} variants (a real GWAS tests millions)".replace(",", " "))
    if lam > 1.1:
        notes.append(f"λ_GC = {lam:.2f}: inflation beyond what a few true signals give — population stratification or relatedness?")
    return GwasPlan(tuple(variants), tuple(peaks), tuple(chroms), offsets, genome, synth, lam, qq_points(variants),
                    sum(1 for v in variants if v.mlog10p >= sig), sum(1 for v in variants if sug <= v.mlog10p < sig),
                    str(spec.get("trait") or ""), tuple(notes))


@lru_cache(maxsize=16)
def _cached(key: str) -> GwasPlan:
    return build_gwas_plan(json.loads(key))


def plan_gwas(spec: Mapping[str, Any]) -> GwasPlan:
    """:func:`build_gwas_plan`, cached by the spec's JSON."""
    return _cached(json.dumps(dict(spec), sort_keys=True, default=str))


def r2_bin(r2: float | None) -> int:
    """0–4: r² < 0.2, 0.2–0.4, 0.4–0.6, 0.6–0.8, ≥ 0.8; −1 when unknown."""
    if r2 is None:
        return -1
    return sum(1 for b in R2_BINS if r2 >= b)


__all__ = ["BACKGROUND", "CHI2_MEDIAN", "CHROMOSOMES", "GwasPlan", "MAX_DRAWN", "Peak", "R2_BINS", "SIGNIFICANCE", "SUGGESTIVE", "Variant",
           "author_variants", "build_gwas_plan", "chromosome", "clump", "lambda_gc", "mlog10", "mlog10_of_z", "plan_gwas", "position",
           "qq_points", "r2_bin", "read_rows", "synthetic", "z_of_mlog10"]
