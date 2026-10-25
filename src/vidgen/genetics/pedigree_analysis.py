"""The analysis of a pedigree (DESIGN.md §96.8): for each mode of inheritance (AD, AR, XD, XR,
Y-linked, mitochondrial) whether some assignment of genotypes fits every phenotype on the chart —
exact, by summing over all assignments with variable elimination — with the reason when none does;
the genotypes the chart forces (obligate carriers); each person's posterior genotype
probabilities by Bayes' rule on the whole chart (2/3 for an unaffected sibling of an affected
child under AR, lowered by unaffected children where they tell something); and the risk for a
proposed child, with the factors of the textbook product when the parents are independent
(2/3 × 1/25 × 1/4 = 1/150).

The model: one locus, two alleles, the disease allele rare. Founders' genotypes follow
Hardy–Weinberg with allele frequency q; without ``carrier_frequency`` q → 0 and the results are
the limit (the explanation that needs the fewest copies of the allele entering the family wins,
ties weighted by their probabilities), so an unaffected founder is a carrier only when the chart
needs it. With ``rare`` (the textbook assumption "the trait is rare"), people who married into the
family carry no disease allele beyond what their own phenotype shows. ``carrier_frequency`` c (an
unaffected person's chance of being a heterozygote, e.g. 1/25 for CF) sets q = c / (2 − c) for the
recessive modes. Penetrance P(affected | disease genotype) is ``penetrance`` (1 by default); there
are no phenocopies, no new mutations, no manifesting heterozygotes under XR and no heteroplasmy
(mtDNA is homoplasmic: mutant or not). No manim."""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from functools import reduce
from math import comb
from typing import Any, Callable, Iterable

from .notation import chromosome_markup, chromosome_text, symbol_markup, symbol_text
from .pedigree import Couple, Pedigree

MODE_ORDER = ("AD", "AR", "XD", "XR", "YL", "MT")
#: A genotype: sex letter ("f" / "m", or "" where the sex does not matter) and the number of
#: copies of the disease allele (0, 1, 2; 0 or 1 on one X, the Y or the mtDNA).
State = tuple[str, int]
#: A weight in the limit q → 0: (power of q, coefficient), ``None`` for zero.
W = tuple[int, Fraction] | None


def _add(a: W, b: W) -> W:
    if a is None:
        return b
    if b is None:
        return a
    if a[0] != b[0]:
        return a if a[0] < b[0] else b
    return (a[0], a[1] + b[1])


def _mul(a: W, b: W) -> W:
    if a is None or b is None:
        return None
    c = a[1] * b[1]
    return None if c == 0 else (a[0] + b[0], c)


@dataclass(frozen=True)
class Options:
    """The analysis' assumptions: penetrance, rarity of the allele, carrier frequency."""

    penetrance: Fraction = Fraction(1)
    rare: bool = True
    carrier_frequency: Fraction | None = None


# ----- the genetics of each mode ------------------------------------------------------------------


def domain(mode: str, sex: str) -> list[State]:
    """The genotypes a person of ``sex`` can have under ``mode``."""
    if mode in ("AD", "AR"):
        return [("", 0), ("", 1), ("", 2)]
    if mode == "MT":
        return [("", 0), ("", 1)]
    female = [("f", 0), ("f", 1), ("f", 2)] if mode in ("XD", "XR") else [("f", 0)]
    male = [("m", 0), ("m", 1)]
    return female if sex == "female" else male if sex == "male" else female + male


def at_risk(mode: str, s: State) -> bool:
    """Whether the genotype causes the condition (with probability ``penetrance``)."""
    sex, n = s
    if mode == "AD":
        return n >= 1
    if mode == "AR":
        return n == 2
    if mode == "XD":
        return n >= 1
    if mode == "XR":
        return n == 2 or (sex == "m" and n == 1)
    if mode == "YL":
        return sex == "m" and n == 1
    return n == 1


def _diploid(mode: str, s: State) -> bool:
    return mode in ("AD", "AR") or (mode in ("XD", "XR") and s[0] == "f")


def _children(mode: str, m: State, f: State) -> dict[str, dict[State, Fraction]]:
    """The child's genotype distribution per sex ("f", "m"; "" when the sex does not matter)."""
    if mode in ("AD", "AR"):
        pm, pf = Fraction(m[1], 2), Fraction(f[1], 2)
        out: dict[State, Fraction] = {}
        for a, wa in ((0, 1 - pm), (1, pm)):
            for b, wb in ((0, 1 - pf), (1, pf)):
                if wa * wb:
                    out[("", a + b)] = out.get(("", a + b), Fraction(0)) + wa * wb
        return {"": out}
    if mode == "MT":
        return {"": {("", m[1]): Fraction(1)}}
    if mode == "YL":
        return {"f": {("f", 0): Fraction(1)}, "m": {("m", f[1]): Fraction(1)}}
    pm = Fraction(m[1], 2)
    daughters: dict[State, Fraction] = {}
    sons: dict[State, Fraction] = {}
    for x, wx in ((0, 1 - pm), (1, pm)):
        if wx:
            daughters[("f", x + f[1])] = daughters.get(("f", x + f[1]), Fraction(0)) + wx
            sons[("m", x)] = sons.get(("m", x), Fraction(0)) + wx
    return {"f": daughters, "m": sons}


def transmission(mode: str, m: State, f: State, sex: str) -> dict[State, Fraction]:
    """P(child genotype | mother, father) for a child of ``sex`` (unknown: either, 1/2 each)."""
    by = _children(mode, m, f)
    if "" in by:
        return by[""]
    if sex == "female":
        return by["f"]
    if sex == "male":
        return by["m"]
    out = {s: p / 2 for s, p in by["f"].items()}
    for s, p in by["m"].items():
        out[s] = out.get(s, Fraction(0)) + p / 2
    return out


def phenotype_weight(mode: str, s: State, affected: bool, carrier: bool, pen: Fraction) -> Fraction:
    """P(the phenotype on the chart | genotype); a carrier must be a heterozygote."""
    if carrier and not (_diploid(mode, s) and s[1] == 1):
        return Fraction(0)
    p = pen if at_risk(mode, s) else Fraction(0)
    return p if affected else 1 - p


def founder_prior(mode: str, s: State, sex: str, opts: Options) -> W:
    """Hardy–Weinberg in the limit q → 0 (power of q, coefficient), or exact with the carrier
    frequency (recessive modes)."""
    diploid = _diploid(mode, s)
    share = Fraction(1, 2) if sex == "unknown" and mode in ("XD", "XR", "YL") else Fraction(1)
    if opts.carrier_frequency is not None and mode in ("AR", "XR"):
        c = opts.carrier_frequency
        q = c / (2 - c)
        p = 1 - q
        if diploid:
            w = (p * p, 2 * p * q, q * q)[s[1]]
        elif s[0] == "m":
            w = (p, q)[s[1]]
        else:
            w = Fraction(1)
        return (0, w * share) if w else None
    if mode == "YL" and s[0] == "f":
        return (0, share)
    return (s[1], Fraction(comb(2, s[1]) if diploid else 1) * share)


# ----- the model as factors, and variable elimination ---------------------------------------------


@dataclass
class _Factor:
    vars: tuple[str, ...]
    table: dict[tuple[State, ...], W]


class Model:
    """The chart under one mode as factors over each person's genotype."""

    def __init__(self, ped: Pedigree, mode: str, opts: Options) -> None:
        self.ped, self.mode, self.opts = ped, mode, opts
        self.domains = {pid: domain(mode, p.sex) for pid, p in ped.people.items()}
        self.factors: list[_Factor] = []
        pen = opts.penetrance
        for pid, p in ped.people.items():
            dom = self.domains[pid]
            pheno = {s: (phenotype_weight(mode, s, p.affected, p.carrier, pen) if p.phenotyped else Fraction(1)) for s in dom}
            mf = ped.mother_father(pid)
            if mf is None:
                prior = {s: founder_prior(mode, s, p.sex, opts) for s in dom}
                if pid in ped.married_in and opts.rare and opts.carrier_frequency is None:
                    allowed = [s for s in dom if pheno[s] != 0]
                    least = min((s[1] for s in allowed), default=0)
                    prior = {s: ((0, prior[s][1]) if prior[s] is not None and s[1] == least else None) for s in dom}
                table = {(s,): _mul(prior[s], (0, pheno[s]) if pheno[s] else None) for s in dom}
                self.factors.append(_Factor((pid,), table))
            else:
                mo, fa = mf
                t: dict[tuple[State, ...], W] = {}
                for sm in self.domains[mo]:
                    for sf in self.domains[fa]:
                        dist = transmission(mode, sm, sf, p.sex)
                        for s in dom:
                            v = dist.get(s, Fraction(0)) * pheno[s]
                            t[(s, sm, sf)] = (0, v) if v else None
                self.factors.append(_Factor((pid, mo, fa), t))
            if p.twin is not None and p.zygosity == "MZ" and p.id < p.twin:
                other = p.twin
                eq = {(a, b): ((0, Fraction(1)) if a == b else None) for a in dom for b in self.domains[other]}
                self.factors.append(_Factor((pid, other), eq))

    def marginal(self, keep: tuple[str, ...]) -> dict[tuple[State, ...], W]:
        """The unnormalized weights of each joint genotype of ``keep`` (all others summed out)."""
        factors = [_Factor(f.vars, dict(f.table)) for f in self.factors]
        todo = [v for v in self.ped.people if v not in keep]
        while todo:
            def cost(v: str) -> int:
                vs = set().union(*[set(f.vars) for f in factors if v in f.vars]) if any(v in f.vars for f in factors) else set()
                return reduce(lambda a, b: a * b, (len(self.domains[x]) for x in vs), 1)
            v = min(todo, key=lambda x: (cost(x), list(self.ped.people).index(x)))
            todo.remove(v)
            touching = [f for f in factors if v in f.vars]
            if not touching:
                continue
            factors = [f for f in factors if v not in f.vars]
            factors.append(_sum_out(_product(touching, self.domains), v))
        whole = _product(factors, self.domains) if factors else _Factor((), {(): (0, Fraction(1))})
        out: dict[tuple[State, ...], W] = {}
        for key, w in whole.table.items():
            assign = dict(zip(whole.vars, key))
            k = tuple(assign[v] for v in keep)
            out[k] = _add(out.get(k), w)
        return out

    def total(self) -> W:
        return reduce(_add, self.marginal(()).values(), None)


def _product(factors: list[_Factor], domains: dict[str, list[State]]) -> _Factor:
    vars_: list[str] = []
    for f in factors:
        vars_ += [v for v in f.vars if v not in vars_]
    table: dict[tuple[State, ...], W] = {}

    def rec(i: int, assign: dict[str, State]) -> None:
        if i == len(vars_):
            w: W = (0, Fraction(1))
            for f in factors:
                w = _mul(w, f.table.get(tuple(assign[v] for v in f.vars)))
                if w is None:
                    return
            table[tuple(assign[v] for v in vars_)] = w
            return
        for s in domains[vars_[i]]:
            assign[vars_[i]] = s
            rec(i + 1, assign)
        del assign[vars_[i]]

    rec(0, {})
    return _Factor(tuple(vars_), table)


def _sum_out(f: _Factor, v: str) -> _Factor:
    i = f.vars.index(v)
    rest = f.vars[:i] + f.vars[i + 1:]
    table: dict[tuple[State, ...], W] = {}
    for key, w in f.table.items():
        k = key[:i] + key[i + 1:]
        table[k] = _add(table.get(k), w)
    return _Factor(rest, table)


def _normalize(weights: dict[Any, W]) -> dict[Any, Fraction]:
    total = reduce(_add, weights.values(), None)
    if total is None:
        return {}
    return {k: (w[1] / total[1] if w is not None and w[0] == total[0] else Fraction(0)) for k, w in weights.items()}


# ----- results ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    """A mode tried on the chart: whether it fits, why not (or what it needs), and the people
    the reason names."""

    mode: str
    consistent: bool
    reason: str
    people: tuple[str, ...] = ()
    reduced_penetrance: bool = False


@dataclass(frozen=True)
class Risk:
    """The risk for the proposed child: P(affected) (sex unknown: either sex), per sex for the
    sex-linked modes, P(heterozygous carrier), and the factors of the textbook product when the
    parents' genotypes are independent (``kind`` carrier / transmit / sex / penetrance)."""

    child: str
    mother: str
    father: str
    affected: Fraction
    by_sex: dict[str, Fraction]
    carrier: Fraction
    factors: tuple[tuple[str, str, Fraction], ...]


@dataclass(frozen=True)
class Inference:
    """The chart under one mode: each person's posterior genotype probabilities, the forced
    genotypes, the obligate carriers and the proposed child's risk."""

    mode: str
    posterior: dict[str, dict[State, Fraction]]
    forced: dict[str, State]
    obligate: tuple[str, ...]
    risk: Risk | None


def consistent(ped: Pedigree, mode: str, opts: Options) -> bool:
    """Whether some genotypes (with their probabilities above zero) fit every phenotype."""
    return Model(ped, mode, opts).total() is not None


def infer(ped: Pedigree, mode: str, opts: Options) -> Inference | None:
    """Posterior genotypes under ``mode`` (``None`` when the mode does not fit)."""
    model = Model(ped, mode, opts)
    if model.total() is None:
        return None
    post: dict[str, dict[State, Fraction]] = {}
    for pid in ped.people:
        m = _normalize({k[0]: w for k, w in model.marginal((pid,)).items()})
        post[pid] = {s: p for s, p in m.items() if p}
    forced = {pid: next(iter(d)) for pid, d in post.items() if len(d) == 1}
    obligate = tuple(pid for pid, s in forced.items()
                     if not ped.people[pid].affected and ped.people[pid].phenotyped and _diploid(mode, s) and s[1] == 1
                     and not ped.people[pid].carrier)
    risk = _risk(ped, model, post) if ped.proposed else None
    return Inference(mode, post, forced, obligate, risk)


def _risk(ped: Pedigree, model: Model, post: dict[str, dict[State, Fraction]]) -> Risk:
    mode, pen = model.mode, model.opts.penetrance
    child = ped.proposed
    assert child is not None
    mother, father = ped.mother_father(child) or ("", "")
    dist = post[child]
    affected = sum((p * pen for s, p in dist.items() if at_risk(mode, s)), Fraction(0))
    carrier = sum((p for s, p in dist.items() if _diploid(mode, s) and s[1] == 1), Fraction(0))
    by_sex: dict[str, Fraction] = {}
    if mode in ("XD", "XR", "YL"):
        for sex, letter in (("son", "m"), ("daughter", "f")):
            share = sum((p for s, p in dist.items() if s[0] == letter), Fraction(0))
            if share:
                by_sex[sex] = sum((p * pen for s, p in dist.items() if s[0] == letter and at_risk(mode, s)), Fraction(0)) / share
            elif ped.people[child].sex == "unknown":
                by_sex[sex] = _sex_risk(mode, post[mother], post[father], letter, pen)
    joint = _normalize(model.marginal((mother, father)))
    independent = all(joint.get((a, b), Fraction(0)) == post[mother].get(a, Fraction(0)) * post[father].get(b, Fraction(0))
                      for a in model.domains[mother] for b in model.domains[father])
    factors = _factors(mode, ped.people[child].sex, post[mother], post[father], mother, father, pen, affected) if independent else ()
    return Risk(child, mother, father, affected, by_sex, carrier, factors)


def _sex_risk(mode: str, m: dict[State, Fraction], f: dict[State, Fraction], letter: str, pen: Fraction) -> Fraction:
    total = Fraction(0)
    for sm, pm in m.items():
        for sf, pf in f.items():
            for s, p in _children(mode, sm, sf)[letter].items():
                if at_risk(mode, s):
                    total += pm * pf * p * pen
    return total


def _factors(mode: str, sex: str, m: dict[State, Fraction], f: dict[State, Fraction], mother: str, father: str, pen: Fraction,
             affected: Fraction) -> tuple[tuple[str, str, Fraction], ...]:
    """The product a textbook writes for the risk (each factor labelled), when the pattern is a
    standard one and the product is exact; else ()."""
    out: list[tuple[str, str, Fraction]] = []
    tail = [("penetrance", "", pen)] if pen != 1 else []
    if mode == "AR" and set(s[1] for s in m) <= {0, 1} and set(s[1] for s in f) <= {0, 1}:
        out = [("carrier", father, f.get(("", 1), Fraction(0))), ("carrier", mother, m.get(("", 1), Fraction(0))),
               ("transmit", "both", Fraction(1, 4))] + tail
    elif mode == "AD":
        free = [(who, d) for who, d in ((mother, m), (father, f)) if set(s[1] for s in d) != {0}]
        if len(free) == 1 and set(s[1] for s in free[0][1]) <= {0, 1}:
            who, d = free[0]
            out = [("carrier", who, d.get(("", 1), Fraction(0))), ("transmit", who, Fraction(1, 2))] + tail
    elif mode == "XR" and set(f) == {("m", 0)} and set(s[1] for s in m) <= {0, 1}:
        if sex == "female":
            out = []
        else:
            out = [("carrier", mother, m.get(("f", 1), Fraction(0)))] + ([("sex", "son", Fraction(1, 2))] if sex == "unknown" else [])
            out += [("transmit", mother, Fraction(1, 2))] + tail
    if out and reduce(lambda a, b: a * b, (x[2] for x in out), Fraction(1)) != affected:
        return ()
    return tuple(out)


# ----- why a mode does not fit --------------------------------------------------------------------


def _nuclear(ped: Pedigree) -> Iterable[tuple[str, str, list[str]]]:
    """(mother, father, biological children) of each couple."""
    for c in ped.couples:
        kids = [k for k in c.children if ped.bio_parents(k) is not None and not ped.people[k].proposed]
        if not kids:
            continue
        mo, fa = ped.mother_father(kids[0]) or (c.b, c.a)
        yield mo, fa, kids


def _rules(ped: Pedigree, mode: str, opts: Options, lab: Callable[[str], str]) -> list[tuple[str, tuple[str, ...]]]:
    """Every textbook reason the mode fails on this chart (the first is shown)."""
    P = ped.people
    full = opts.penetrance == 1
    rare = opts.rare and opts.carrier_frequency is None
    mi = ped.married_in
    out: list[tuple[str, tuple[str, ...]]] = []
    aff = lambda x: P[x].affected  # noqa: E731
    sound = lambda x: not P[x].affected and P[x].phenotyped  # noqa: E731

    for p in P.values():                       # carriers where nobody is heterozygous
        if not p.carrier:
            continue
        if mode in ("XD", "XR") and p.sex == "male":
            out.append((f"{lab(p.id)} is marked carrier, but a male has one X (hemizygous): he has the allele or not", (p.id,)))
        elif mode == "YL":
            out.append((f"{lab(p.id)} is marked carrier, but the Y is single: there are no heterozygous carriers", (p.id,)))
        elif mode == "MT":
            out.append((f"{lab(p.id)} is marked carrier, but mtDNA is not paired: there are no heterozygous carriers", (p.id,)))
        elif mode in ("AD", "XD") and full:
            out.append((f"{lab(p.id)} is a heterozygous carrier yet unaffected: a dominant allele shows in every heterozygote "
                        f"(at full penetrance)", (p.id,)))
    if mode == "YL":
        for p in P.values():
            if p.affected and p.sex == "female":
                out.append((f"{lab(p.id)} is an affected female: females have no Y", (p.id,)))
    for p in P.values():
        if full and p.twin is not None and p.zygosity == "MZ" and p.id < p.twin and p.phenotyped and P[p.twin].phenotyped \
                and (p.affected != P[p.twin].affected or p.carrier != P[p.twin].carrier):
            out.append((f"MZ twins {lab(p.id)} and {lab(p.twin)} differ: identical twins share their genotype", (p.id, p.twin)))
    for mo, fa, kids in _nuclear(ped):
        sons = [k for k in kids if P[k].sex == "male"]
        daughters = [k for k in kids if P[k].sex == "female"]
        for k in kids:
            if not P[k].phenotyped:
                continue
            if mode == "AD" and full and aff(k) and sound(mo) and sound(fa):
                out.append((f"{lab(k)} is affected but neither parent ({lab(fa)}, {lab(mo)}) is: a dominant trait does not "
                            f"skip a generation", (k, fa, mo)))
            if mode == "AR" and full and sound(k) and aff(mo) and aff(fa):
                out.append((f"affected parents {lab(fa)} and {lab(mo)} (both aa) have an unaffected child {lab(k)}", (fa, mo, k)))
            if mode == "AR" and rare and (aff(k) or P[k].carrier):
                for par in (fa, mo):
                    if par in mi and not aff(par) and not P[par].carrier:
                        what = "affected (aa)" if aff(k) else "a carrier"
                        out.append((f"{lab(k)} is {what}, so {lab(par)} would carry the allele, but married in "
                                    f"(rare allele: not a carrier)", (k, par)))
            if mode == "MT":
                if full and aff(k) and sound(mo):
                    extra = " (an affected father passes no mtDNA)" if aff(fa) else ""
                    out.append((f"{lab(k)} is affected but the mother {lab(mo)} is not: mtDNA comes from the mother{extra}", (k, mo)))
                if full and aff(mo) and sound(k):
                    out.append((f"affected mother {lab(mo)} has an unaffected child {lab(k)}: her mtDNA goes to every child", (mo, k)))
                if rare and not full and aff(k) and mo in mi and sound(mo):
                    out.append((f"{lab(k)} is affected, so the mother {lab(mo)} would carry the mutant mtDNA, but married in "
                                f"(rare: not a carrier)", (k, mo)))
        for s in sons:
            if not P[s].phenotyped:
                continue
            if mode == "XR" and full and aff(mo) and sound(s):
                out.append((f"affected mother {lab(mo)} has an unaffected son {lab(s)}: she gives an Xᵃ to every son", (mo, s)))
            if mode == "XR" and rare and aff(s) and mo in mi and sound(mo) and not P[mo].carrier:
                if aff(fa):
                    out.append((f"father-to-son: affected father {lab(fa)} has an affected son {lab(s)}, but a son's X comes "
                                f"from his mother {lab(mo)} (married in, not a carrier)", (fa, s, mo)))
                else:
                    out.append((f"affected son {lab(s)}'s X comes from his mother {lab(mo)}, who married in (rare allele: "
                                f"not a carrier)", (s, mo)))
            if mode == "XD" and full and aff(s) and sound(mo):
                extra = f" — no father-to-son transmission from {lab(fa)}" if aff(fa) else ""
                out.append((f"affected son {lab(s)} has an unaffected mother {lab(mo)}: a son's X comes from his mother{extra}",
                            (s, mo) + ((fa,) if aff(fa) else ())))
            if mode == "XD" and rare and not full and aff(s) and mo in mi and sound(mo):
                out.append((f"affected son {lab(s)}'s X comes from his mother {lab(mo)}, who married in (rare allele: "
                            f"not a carrier)", (s, mo)))
            if mode == "YL" and full and aff(fa) and sound(s):
                out.append((f"affected father {lab(fa)} has an unaffected son {lab(s)}: every son gets his father's Y", (fa, s)))
            if mode == "YL" and full and aff(s) and sound(fa):
                out.append((f"affected son {lab(s)} has an unaffected father {lab(fa)}: a son's Y is his father's", (s, fa)))
            if mode == "YL" and rare and not full and aff(s) and fa in mi and sound(fa):
                out.append((f"affected son {lab(s)}'s Y comes from his father {lab(fa)}, who married in (rare: not a carrier)", (s, fa)))
        for d in daughters:
            if not P[d].phenotyped:
                continue
            if mode == "XR" and full and aff(d) and sound(fa):
                out.append((f"affected daughter {lab(d)} needs an Xᵃ from her unaffected father {lab(fa)}", (d, fa)))
            if mode == "XR" and rare and aff(d) and mo in mi and sound(mo) and not P[mo].carrier:
                out.append((f"affected daughter {lab(d)} needs an Xᵃ from her mother {lab(mo)}, who married in (rare allele: "
                            f"not a carrier)", (d, mo)))
            if mode == "XD" and full and aff(fa) and sound(d):
                out.append((f"affected father {lab(fa)} has an unaffected daughter {lab(d)}: a father gives his X to every daughter",
                            (fa, d)))
            if mode == "XD" and full and aff(d) and sound(fa) and sound(mo):
                out.append((f"{lab(d)} is affected but neither parent is: a dominant trait does not skip a generation", (d, fa, mo)))
    return out


def explain(ped: Pedigree, mode: str, opts: Options, lab: Callable[[str], str]) -> tuple[str, tuple[str, ...]]:
    """Why ``mode`` does not fit: the first textbook reason that applies, else the smallest
    family on the chart that no genotypes fit."""
    rules = _rules(ped, mode, opts, lab)
    if rules:
        return rules[0]
    for mo, fa, kids in _nuclear(ped):
        sub = _subchart(ped, [mo, fa, *kids])
        if not consistent(sub, mode, opts):
            names = ", ".join(lab(x) for x in [fa, mo, *kids])
            return f"no genotypes fit the family of {lab(fa)} and {lab(mo)} ({names})", (fa, mo, *kids)
    return "no genotypes fit the whole chart at once (each family alone fits)", ()


def _subchart(ped: Pedigree, ids: list[str]) -> Pedigree:
    """The people ``ids`` alone (parents become founders who keep whether they married in)."""
    people = {}
    for pid in ped.people:
        if pid in ids:
            p = ped.people[pid]
            keep = p.parents is not None and all(x in ids for x in p.parents)
            twin = p.twin if p.twin in ids else None
            people[pid] = replace(p, parents=p.parents if keep else None, twin=twin, zygosity=p.zygosity if twin else None,
                                  adopted=p.adopted if keep else None)
    couples = tuple(Couple(c.a, c.b, tuple(k for k in c.children if k in ids), c.consanguineous, c.separated)
                    for c in ped.couples if c.a in ids and c.b in ids)
    return Pedigree(people, couples, {k: v for k, v in ped.generation.items() if k in ids},
                    frozenset(x for x in ped.married_in if x in ids), ped.nsgc_ids, ped.labels)


def analyse(ped: Pedigree, opts: Options, modes: Iterable[str] = MODE_ORDER,
            lab: Callable[[str], str] | None = None) -> tuple[Verdict, ...]:
    """Each mode tried on the chart, in ``modes`` order."""
    lab = lab or ped.label
    out = []
    for mode in modes:
        ok = consistent(ped, mode, opts)
        if ok:
            reduced = opts.penetrance != 1 and not consistent(ped, mode, Options(Fraction(1), opts.rare, opts.carrier_frequency))
            note, people = _fit_note(ped, mode, opts, lab, reduced)
            out.append(Verdict(mode, True, note, people, reduced))
        else:
            reason, people = explain(ped, mode, opts, lab)
            if opts.penetrance == 1:
                reason += _unless_non_penetrant(ped, mode, opts, lab, people)
            out.append(Verdict(mode, False, reason, people))
    return tuple(out)


#: What a non-penetrant person would have to be, per mode (and sex for the X-linked modes).
_SILENT = {"AD": "heterozygous", "AR": "aa", "YL": "carrying the Y allele", "MT": "carrying the mutant mtDNA"}
#: How plausible that is: reduced penetrance is a known feature of many dominant conditions, not
#: of recessive ones.
_SILENT_NOTE = {"AR": "; unusual", "XR": "; very unusual"}


def _silent_genotype(mode: str, sex: str) -> str:
    if mode == "XR":
        return "Xᵃ Y" if sex == "male" else "Xᵃ Xᵃ"
    if mode == "XD":
        return "Xᴬ Y" if sex == "male" else "heterozygous"
    return _SILENT[mode]


def _unless_non_penetrant(ped: Pedigree, mode: str, opts: Options, lab: Callable[[str], str], named: tuple[str, ...]) -> str:
    """For a mode excluded at full penetrance that reduced penetrance would allow: the exact
    condition — "excluded unless I-1 is non-penetrant (Xᵃ Y; very unusual)" —
    naming who would have to carry the disease genotype without the condition (everyone forced
    to, else the unaffected people the reason names who might: "I-1 or I-2"). Empty when it
    cannot fit."""
    half = Options(Fraction(1, 2), opts.rare, opts.carrier_frequency)
    inf = infer(ped, mode, half)
    if inf is None:
        return ""
    P = ped.people
    unaffected = [pid for pid in P if P[pid].phenotyped and not P[pid].affected and inf.posterior.get(pid)]
    forced = [pid for pid in unaffected if all(at_risk(mode, s) for s in inf.posterior[pid])]
    maybe = [pid for pid in unaffected if pid in named and any(at_risk(mode, s) for s in inf.posterior[pid])]
    note = _SILENT_NOTE.get(mode, "")
    if forced:
        who, verb, plural = " and ".join(lab(x) for x in forced), ("is" if len(forced) == 1 else "are"), forced
    elif 0 < len(maybe) <= 3:
        who, verb, plural = " or ".join(lab(x) for x in maybe), "is", maybe
    else:
        return f" — excluded unless the condition shows reduced penetrance (someone unaffected has the disease genotype{note})"
    kinds = {_silent_genotype(mode, P[x].sex) for x in plural}
    what = f" ({kinds.pop()}{note})" if len(kinds) == 1 else (f" ({note[2:]})" if note else "")
    return f" — excluded unless {who} {verb} non-penetrant{what}"


def _fit_note(ped: Pedigree, mode: str, opts: Options, lab: Callable[[str], str], reduced: bool) -> tuple[str, tuple[str, ...]]:
    """What a fitting mode needs: reduced penetrance (who must be a non-penetrant carrier), or
    people who married in being carriers."""
    inf = infer(ped, mode, opts)
    assert inf is not None
    P = ped.people
    if reduced:
        silent = [pid for pid, d in inf.posterior.items() if P[pid].phenotyped and not P[pid].affected and d
                  and all(at_risk(mode, s) for s in d)]
        if silent:
            kinds = {_silent_genotype(mode, P[x].sex) for x in silent}
            what = f" ({kinds.pop()})" if len(kinds) == 1 else ""
            return (f"fits with reduced penetrance: {' and '.join(lab(x) for x in silent)} "
                    f"{'is' if len(silent) == 1 else 'are'} non-penetrant{what}", tuple(silent))
        return "fits with reduced penetrance", ()
    outside = [pid for pid in ped.married_in if pid in inf.forced and P[pid].phenotyped and not P[pid].affected
               and not P[pid].carrier and inf.forced[pid][1] >= 1]
    outside.sort(key=lambda x: list(P).index(x))
    if outside:
        return (f"fits if {', '.join(lab(x) for x in outside)} (married in) "
                f"{'is a carrier' if len(outside) == 1 else 'are carriers'}", tuple(outside))
    return "fits", ()


# ----- notation --------------------------------------------------------------------------------------


def genotype_markup(mode: str, s: State, alleles: tuple[str, str] = ("A", "a")) -> str:
    """The genotype in Pango markup: ``Aa``, ``X<sup>A</sup>X<sup>a</sup>``, ``X<sup>a</sup>Y``;
    ``alleles`` is (dominant, recessive) — the disease allele is the dominant one under AD / XD,
    the recessive one under AR / XR; Y-linked and mitochondrial alleles are written on the Y and
    mt."""
    big, small = alleles
    sex, n = s
    if mode in ("AD", "AR"):
        dis, norm = (big, small) if mode == "AD" else (small, big)
        pair = [dis] * n + [norm] * (2 - n)
        pair.sort(key=lambda a: a != big)
        return "".join(symbol_markup(a) for a in pair)
    if mode in ("XD", "XR"):
        dis, norm = (big, small) if mode == "XD" else (small, big)
        if sex == "m":
            return chromosome_markup("X", ((dis if n else norm),)) + "Y"
        pair = [dis] * n + [norm] * (2 - n)
        pair.sort(key=lambda a: a != big)
        return "".join(chromosome_markup("X", (a,)) for a in pair)
    if mode == "YL":
        return "XX" if sex == "f" else "X" + (chromosome_markup("Y", (big,)) if n else "Y")
    return "mt" + (f"<sup>{symbol_markup(big)}</sup>" if n else "<sup>+</sup>")


def genotype_plain(mode: str, s: State, alleles: tuple[str, str] = ("A", "a")) -> str:
    """The genotype as plain text with Unicode superscripts (``XᴬXᵃ``)."""
    big, small = alleles
    sex, n = s
    if mode in ("AD", "AR"):
        dis, norm = (big, small) if mode == "AD" else (small, big)
        pair = sorted([dis] * n + [norm] * (2 - n), key=lambda a: a != big)
        return "".join(symbol_text(a) for a in pair)
    if mode in ("XD", "XR"):
        dis, norm = (big, small) if mode == "XD" else (small, big)
        if sex == "m":
            return chromosome_text("X", ((dis if n else norm),)) + "Y"
        pair = sorted([dis] * n + [norm] * (2 - n), key=lambda a: a != big)
        return "".join(chromosome_text("X", (a,)) for a in pair)
    if mode == "YL":
        return "XX" if sex == "f" else "X" + (chromosome_text("Y", (big,)) if n else "Y")
    return "mt" + (f"^{big}" if n else "⁺")


__all__ = ["Inference", "MODE_ORDER", "Model", "Options", "Risk", "State", "Verdict", "analyse", "at_risk", "consistent", "domain",
           "explain", "founder_prior", "genotype_markup", "genotype_plain", "infer", "phenotype_weight", "transmission"]
