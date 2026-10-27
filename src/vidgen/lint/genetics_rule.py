"""The genetics accuracy lint rules (DESIGN.md §96.18): each genetics scene's model is rebuilt from
its params (validated by its scene type, no render) and its narration and on-screen text are
checked against it; the text checks that need no scene (a dominant trait skipping a generation,
RF over 50 %, Hardy–Weinberg formulas, Cas9 facts, karyotype notation, HGVS) read every scene.

``genetics_ratio`` (ratios and shares that do not follow from a ``cross``), ``genetics_pedigree``
(a chart against its stated mode; skipped generations, father → son for X-linked traits; carrier
and risk probabilities against the chart), ``genetics_linkage`` (cM and RF against the map, RF
over 50 %, close loci called unlinked), ``genetics_hwe`` (Hardy–Weinberg arithmetic),
``genetics_crispr`` (PAM, cut site, blunt ends, spacer length), ``genetics_karyotype`` (ISCN
notation and order, the sex and the conditions a karyotype has) and ``genetics_hgvs`` (HGVS
against the scene's variant, legacy numbering and shorthand). The knowledge is in
:mod:`vidgen.genetics.accuracy`; the runner adds :func:`genetics_issues` to
:attr:`SceneContext.science`, and the findings are reported like the ``science_*`` rules'.
"""

from __future__ import annotations

from collections.abc import Iterator
from fractions import Fraction
from itertools import combinations
from typing import TYPE_CHECKING, Any

from vidgen.genetics import accuracy as gacc
from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.lint.science_rule import ScienceIssue, _issues, _params, _said

if TYPE_CHECKING:
    from vidgen.config import LintRules
    from vidgen.project import Project

#: The rules of this module, in :data:`vidgen.config.LINT_RULES` order.
GENETICS_RULES: tuple[str, ...] = (
    "genetics_ratio", "genetics_pedigree", "genetics_linkage", "genetics_hwe", "genetics_crispr", "genetics_karyotype", "genetics_hgvs",
)
#: The scene types whose model the rules rebuild.
GENETICS_TYPES = frozenset({"cross", "pedigree", "linkage_map", "karyotype", "mutation", "crispr", "dna_lab", "population", "gwas"})


def _plan(params: Any) -> Any:
    try:
        return params.plan()
    except Exception:  # noqa: BLE001 - validation reports a plan that cannot be built
        return None


def cross_pairs(system: Any) -> tuple[dict[frozenset[str], gacc.PairData], list[str]]:
    """Every two loci of a cross's system: linked ones with their map distance (100 × RF summed
    over the intervals) and RF (adjacent: the interval's; three loci: r₁ + r₂ − 2·C·r₁·r₂), the
    others unlinked (RF ½)."""
    pairs: dict[frozenset[str], gacc.PairData] = {}
    groups = list(system.groups) + ([system.x_group] if system.x_group is not None else [])
    where = {lo: k for k, g in enumerate(groups) for lo in g.loci}
    for g in groups:
        rf = [float(r) for r in g.rf]
        for i, j in combinations(range(len(g.loci)), 2):
            cm = 100 * sum(rf[i:j])
            if j == i + 1:
                rates: tuple[float, ...] = (rf[i],)
            else:
                r1, r2 = rf[i], rf[j - 1]
                rates = (r1 + r2 - 2 * float(g.coincidence) * r1 * r2,)
            pairs[frozenset((g.loci[i], g.loci[j]))] = gacc.PairData(cm, rates)
    for a, b in combinations(system.locus_symbols, 2):
        if where.get(a) != where.get(b) and system.locus(a).chromosome == system.locus(b).chromosome == "autosome":
            pairs[frozenset((a, b))] = gacc.PairData(float("inf"), (0.5,), linked=False)
    return pairs, list(system.locus_symbols)


def map_pairs(plan: Any) -> tuple[dict[frozenset[str], gacc.PairData], list[str]]:
    """Every two loci of a ``linkage_map`` plan: their distance on its map and the RF that is right
    for them (a test cross's interval RF; for the outer pair of three loci the direct count too)."""
    from vidgen.genetics.mapping import cm_to_rf

    names = list(plan.ordered)
    pos = plan.positions
    pairs: dict[frozenset[str], gacc.PairData] = {}
    an = plan.analysis
    for a, b in combinations(names, 2):
        d = abs(pos[a] - pos[b])
        rates: list[float] = []
        if an is not None:
            for iv in an.intervals:
                if {iv.left, iv.right} == {a, b}:
                    rates.append(float(iv.rf))
            if not rates and an.outer_rf is not None:
                rates += [float(an.outer_rf), sum(float(iv.rf) for iv in an.intervals)]
        else:
            rates.append(cm_to_rf(d, plan.function))
        pairs[frozenset((a, b))] = gacc.PairData(d, tuple(rates))
    return pairs, names


def _screen_texts(spec: Any, params: Any) -> list[tuple[str, str]]:
    """``(where, text)`` of the scene's own words on screen: its title, callout labels."""
    out: list[tuple[str, str]] = []
    title = getattr(params, "title", "") if params is not None else spec.params.get("title", "")
    if isinstance(title, str) and title:
        out.append(("title", title))
    for beat in spec.beats:
        for act in beat.actions:
            label = act.options.get("label")
            if isinstance(label, str):
                out.append((f"beat '{beat.id}' {act.action} label", label))
    return out


def genetics_issues(project: Project, scene_id: str, rules: LintRules) -> list[ScienceIssue]:
    """Every genetics finding of scene ``scene_id`` (rules turned off are skipped)."""
    spec = project.scene(scene_id)
    on = {name for name in GENETICS_RULES if getattr(rules, name).severity != "off"}
    if not on:
        return []
    params = _params(spec) if spec.type in GENETICS_TYPES else None
    plan = _plan(params) if params is not None and spec.type != "karyotype" else None
    first = spec.beats[0].id if spec.beats else None
    out: list[ScienceIssue] = []

    def add(rule_name: str, beat: str | None, claims: list[Any], severity: str | None = None, where: str | None = None) -> None:
        for c in claims:
            text = f"{where} '{c.quote}': {c.message}" if where else f"{_said(c.quote)}: {c.message}"
            out.append(ScienceIssue(rule_name, beat, text, severity))

    mode = None
    penetrance: Fraction | None = None
    pairs: dict[frozenset[str], gacc.PairData] = {}
    symbols: list[str] = []
    hw = None
    cas = None
    scene_kt = None
    mutation_plan = None
    if plan is not None and spec.type == "cross":
        mode = "XR" if plan.system.x_loci else None
        pens = [p for lo in plan.system.loci for p in lo.penetrance.values()]
        penetrance = min(pens) if pens else None
        pairs, symbols = cross_pairs(plan.system)
    elif plan is not None and spec.type == "pedigree":
        mode = plan.mode or plan.declared
        penetrance = plan.opts.penetrance
    elif plan is not None and spec.type == "linkage_map":
        pairs, symbols = map_pairs(plan)
    elif plan is not None and spec.type == "population":
        hw = plan.hw
    elif plan is not None and spec.type == "crispr":
        cas = plan.cas.name
    elif plan is not None and spec.type == "mutation":
        mutation_plan = plan
    if params is not None and spec.type == "karyotype":
        try:
            scene_kt = params.parsed()
        except Exception:  # noqa: BLE001 - validation reports it
            scene_kt = None
    tol = rules.genetics_hwe.tolerance
    for beat in spec.beats:
        text = str(beat.text)
        if "genetics_ratio" in on and plan is not None and spec.type == "cross":
            observed = None
            if isinstance(getattr(params, "observed", None), (dict, list)):
                try:
                    from vidgen.genetics.punnett import match_observed

                    observed = list(match_observed(plan, params.observed, "observed"))
                except Exception:  # noqa: BLE001 - validation reports it
                    observed = None
            add("genetics_ratio", beat.id, gacc.cross_claims(text, plan, observed, rules.genetics_ratio.tolerance))
        if "genetics_pedigree" in on:
            add("genetics_pedigree", beat.id, gacc.pedigree_text_claims(text, mode, penetrance))
            if plan is not None and spec.type == "pedigree":
                add("genetics_pedigree", beat.id, gacc.pedigree_claims(text, plan))
        if "genetics_linkage" in on:
            add("genetics_linkage", beat.id, gacc.linkage_claims(text, pairs, symbols, rules.genetics_linkage.tolerance))
        if "genetics_hwe" in on:
            add("genetics_hwe", beat.id, gacc.hw_claims(text, hw, tol))
        if "genetics_crispr" in on:
            add("genetics_crispr", beat.id, gacc.crispr_claims(text, cas))
        if "genetics_karyotype" in on:
            add("genetics_karyotype", beat.id, gacc.karyotype_claims(text, scene_kt))
        if "genetics_hgvs" in on:
            for claim, severity in gacc.hgvs_claims(text, mutation_plan, spec.type in GENETICS_TYPES):
                add("genetics_hgvs", beat.id, [claim], severity)
    if "genetics_pedigree" in on and plan is not None and spec.type == "pedigree":
        from vidgen.genetics.modes import MODES
        from vidgen.genetics.pedigree_plan import declared_mode_problem

        problem = declared_mode_problem(plan)
        if problem is not None:
            fits = list(plan.fitting)
            fix = (f"fix the chart (affected, carrier, parents) or state a mode that fits ({', '.join(f'{m}, {MODES[m].name}' for m in fits)})"
                   if fits else "no mode tried fits the chart as drawn: fix the chart (affected, carrier, parents), or give penetrance: "
                                "when the reason says it is excluded unless someone is non-penetrant")
            out.append(ScienceIssue("genetics_pedigree", first, f"the chart does not fit the stated mode {plan.declared} "
                                                                 f"({MODES[plan.declared].name}): {problem.split(': ', 1)[-1]}; {fix}", "error"))
    if "genetics_karyotype" in on and scene_kt is not None:
        fixed = gacc.iscn_order_problem(scene_kt)
        if fixed:
            out.append(ScienceIssue("genetics_karyotype", first, f"karyotype '{scene_kt.text}': ISCN lists the changes by chromosome (sex "
                                                                  f"chromosomes, then 1–22; numerical before structural): write {fixed}"))
    for where, text in _screen_texts(spec, params):
        if "genetics_karyotype" in on:
            add("genetics_karyotype", first, gacc.karyotype_claims(text, None, on_screen=True), where=where)
        if "genetics_hgvs" in on:
            for claim, severity in gacc.hgvs_claims(text, mutation_plan, spec.type in GENETICS_TYPES, on_screen=True):
                add("genetics_hgvs", first, [claim], severity, where=where)
    return out


# ----- the rules -----------------------------------------------------------------------------------------


@rule("genetics_ratio", scope="scene")
def genetics_ratio(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A ratio, fraction or percentage in a cross scene's narration that does not follow from its cross."""
    yield from _issues(ctx, "genetics_ratio")


@rule("genetics_pedigree", scope="scene")
def genetics_pedigree(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A pedigree that does not fit its stated mode; a dominant trait skipping a generation, an X-linked one passed father to son, or a carrier or risk probability against the chart."""
    yield from _issues(ctx, "genetics_pedigree")


@rule("genetics_linkage", scope="scene")
def genetics_linkage(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A recombination frequency over 50 %, a distance or RF against the scene's map, or close loci called unlinked."""
    yield from _issues(ctx, "genetics_linkage")


@rule("genetics_hwe", scope="scene")
def genetics_hwe(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Hardy–Weinberg arithmetic in the narration: q against the incidence, carriers against 2pq, the formulas mixed up."""
    yield from _issues(ctx, "genetics_hwe")


@rule("genetics_crispr", scope="scene")
def genetics_crispr(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A wrong PAM for the Cas, a cut placed other than 3 bp upstream of the PAM, sticky ends for Cas9, a wrong spacer length."""
    yield from _issues(ctx, "genetics_crispr")


@rule("genetics_karyotype", scope="scene")
def genetics_karyotype(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Karyotype notation that does not parse or is out of ISCN order, the wrong sex for a karyotype, a condition the scene's karyotype does not have."""
    yield from _issues(ctx, "genetics_karyotype")


@rule("genetics_hgvs", scope="scene")
def genetics_hgvs(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """HGVS that is invalid or not the scene's variant, legacy numbering without saying so, legacy shorthand (info)."""
    yield from _issues(ctx, "genetics_hgvs")
