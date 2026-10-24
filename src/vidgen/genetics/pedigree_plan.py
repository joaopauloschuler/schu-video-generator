"""What a ``pedigree`` scene shows, worked out from its params (DESIGN.md §96.8): the checked chart
(``pedigree``), its layout and NSGC numbering (``pedigree_layout``), the analysis of the modes
(``pedigree_analysis``), the mode used for genotypes and risk (declared, from a locus, or the only
one that fits), the allele symbols and the warnings for the lint. Cached by the params' JSON. No
manim."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Any, Mapping

from vidgen.errors import VidgenError

from .model import as_fraction, build_system
from .modes import MODES, mode_of, parse_mode
from .notation import canonical_symbol
from .pedigree import Pedigree, parse_pedigree
from .pedigree_analysis import MODE_ORDER, Inference, Options, Verdict, analyse, consistent, infer
from .pedigree_layout import Layout, layout_pedigree

PLAN_KEYS = ("individuals", "couples", "condition", "mode", "analyse", "penetrance", "rare", "carrier_frequency", "alleles", "preset",
             "loci")


@dataclass
class PedigreePlan:
    """The chart, its layout, the assumptions, the verdict for each mode tried, the mode for
    genotypes (``None`` when the chart fits several and none is declared) and its inference."""

    ped: Pedigree
    layout: Layout
    condition: str
    opts: Options
    alleles: tuple[str, str]
    modes_tried: tuple[str, ...]
    declared: str | None
    mode: str | None
    warnings: tuple[str, ...]
    _verdicts: tuple[Verdict, ...] | None = None
    _inference: Inference | None = None
    _inferred: bool = False

    @property
    def verdicts(self) -> tuple[Verdict, ...]:
        if self._verdicts is None:
            self._verdicts = analyse(self.ped, self.opts, self.modes_tried, self.ped.label)
        return self._verdicts

    @property
    def inference(self) -> Inference | None:
        if not self._inferred:
            self._inferred = True
            self._inference = infer(self.ped, self.mode, self.opts) if self.mode else None
        return self._inference

    def label(self, pid: str) -> str:
        return self.ped.label(pid)

    @property
    def fitting(self) -> tuple[str, ...]:
        return tuple(v.mode for v in self.verdicts if v.consistent)


def _alleles(value: Any, where: str) -> tuple[str, str]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise VidgenError(f"{where}: alleles: two symbols, the dominant first ([A, a], [H, h])")
    a, b = (canonical_symbol(str(x), where) for x in value)
    if a == b:
        raise VidgenError(f"{where}: alleles: two different symbols")
    return a, b


def _from_locus(data: Mapping[str, Any], condition: str, where: str) -> tuple[str, tuple[str, str], str, Fraction | None]:
    """The mode, alleles, condition and penetrance from a ``preset`` or one ``loci`` entry."""
    spec: dict[str, Any] = {k: data[k] for k in ("preset", "loci") if data.get(k) is not None}
    system = build_system(spec, where)
    if len(system.loci) != 1:
        raise VidgenError(f"{where}: a pedigree follows one locus ({len(system.loci)} given)")
    lo = system.loci[0]
    phenos = list(lo.phenotypes)
    if condition and condition in phenos:
        affected = condition
    elif lo.normal is not None and len(phenos) == 2:
        affected = next(p for p in phenos if p != lo.normal)
    elif len(phenos) == 2 and sum(p.lower().startswith(("normal", "unaffected", "wild type")) for p in phenos) == 1:
        affected = next(p for p in phenos if not p.lower().startswith(("normal", "unaffected", "wild type")))
    elif lo.chromosome in ("autosome", "X") and lo.is_simple and lo.recessive_phenotype and lo.dominant_phenotype:
        raise VidgenError(f"{where}: say which phenotype is the condition: condition: {lo.recessive_phenotype} (or {lo.dominant_phenotype})")
    else:
        raise VidgenError(f"{where}: say which phenotype is the condition ({', '.join(phenos)})")
    mode = mode_of(system, lo.symbol, affected, where).code
    symbols = lo.symbols
    if len(symbols) != 2:
        raise VidgenError(f"{where}: a pedigree locus has two alleles ({len(symbols)} given)")
    pen = lo.penetrance.get(affected)
    return mode, (symbols[0], symbols[1]), affected, pen


def build_pedigree_plan(data: Mapping[str, Any], where: str = "params") -> PedigreePlan:
    """The plan from the scene's params (only :data:`PLAN_KEYS` matter)."""
    ped = parse_pedigree(data.get("individuals"), data.get("couples"), where)
    lay = layout_pedigree(ped, f"{where}.individuals")
    ped.labels = dict(lay.labels)
    condition = str(data.get("condition") or "")
    declared = parse_mode(data["mode"], f"{where}.mode").code if data.get("mode") else None
    alleles = _alleles(data["alleles"], f"{where}.alleles") if data.get("alleles") is not None else ("A", "a")
    pen = as_fraction(data["penetrance"], f"{where}.penetrance", "penetrance") if data.get("penetrance") is not None else None
    if data.get("preset") or data.get("loci"):
        if data.get("alleles") is not None:
            raise VidgenError(f"{where}: alleles come from the locus ({'preset' if data.get('preset') else 'loci'}): leave out alleles")
        locus_mode, alleles, affected, locus_pen = _from_locus(data, condition, where)
        if declared is not None and declared != locus_mode:
            raise VidgenError(f"{where}.mode: {declared} but the locus makes '{affected}' {MODES[locus_mode].name} ({locus_mode})")
        declared = locus_mode
        condition = condition or affected
        if pen is None and locus_pen is not None:
            pen = locus_pen
    if pen is None:
        pen = Fraction(1)
    if not 0 < pen <= 1:
        raise VidgenError(f"{where}.penetrance: between 0 (excluded) and 1, not {pen}")
    cf = None
    if data.get("carrier_frequency") is not None:
        cf = as_fraction(data["carrier_frequency"], f"{where}.carrier_frequency", "carrier frequency")
        if not 0 < cf < 1:
            raise VidgenError(f"{where}.carrier_frequency: between 0 and 1 (1/25 for cystic fibrosis in Northern Europeans), not {cf}")
    rare = data.get("rare", True)
    if not isinstance(rare, bool):
        raise VidgenError(f"{where}.rare: true or false")
    opts = Options(pen, rare, cf)
    tried = data.get("analyse", True)
    if tried is True or tried is False or tried is None:
        modes = MODE_ORDER
    else:
        if not isinstance(tried, (list, tuple)) or not tried:
            raise VidgenError(f"{where}.analyse: true, false or a list of modes ([AD, AR, XR])")
        modes = tuple(dict.fromkeys(parse_mode(m, f"{where}.analyse").code for m in tried))
    if declared in ("XD", "XR"):
        for p in ped.people.values():
            if p.carrier and p.sex == "male":
                raise VidgenError(f"{where}.individuals ({p.id}): a male carrier under {MODES[declared].name} inheritance: a male has "
                                  f"one X (hemizygous), so with the allele he is affected, without it he is not — remove carrier")
    if declared in ("YL", "MT"):
        for p in ped.people.values():
            if p.carrier:
                raise VidgenError(f"{where}.individuals ({p.id}): carrier under {MODES[declared].name} inheritance: the "
                                  f"{'Y' if declared == 'YL' else 'mtDNA'} is single, there are no heterozygous carriers — remove carrier")
    warnings: list[str] = []
    mode = declared
    if declared is not None and not consistent(ped, declared, opts):
        warnings.append(f"the chart does not fit the stated mode {declared} ({MODES[declared].name})")
        mode = None
    plan = PedigreePlan(ped, lay, condition, opts, alleles, modes, declared, mode, tuple(warnings))
    if mode is None and declared is None:
        fits = plan.fitting if set(modes) == set(MODE_ORDER) else tuple(m for m in MODE_ORDER if consistent(ped, m, opts))
        if len(fits) == 1:
            plan.mode = fits[0]
    return plan


@lru_cache(maxsize=64)
def _cached(key: str) -> PedigreePlan:
    return build_pedigree_plan(json.loads(key))


def plan_pedigree(data: Mapping[str, Any]) -> PedigreePlan:
    """:func:`build_pedigree_plan`, cached by the params' JSON (validation and the scene share it)."""
    key = json.dumps({k: data[k] for k in PLAN_KEYS if k in data}, sort_keys=True, default=str)
    return _cached(key)


def declared_mode_problem(plan: PedigreePlan) -> str | None:
    """For the genetics lint (Step 219): the reason the chart does not fit the stated mode."""
    if plan.declared is None or consistent(plan.ped, plan.declared, plan.opts):
        return None
    v = analyse(plan.ped, plan.opts, (plan.declared,), plan.ped.label)[0]
    return f"{plan.declared} excluded: {v.reason}"


__all__ = ["PLAN_KEYS", "PedigreePlan", "build_pedigree_plan", "declared_mode_problem", "plan_pedigree"]
