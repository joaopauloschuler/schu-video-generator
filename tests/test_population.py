"""Step 218 (DESIGN.md §96.16–96.17): population genetics — Hardy–Weinberg worked exactly (allele
frequencies, p² + 2pq + q², carriers from an incidence, the chi-square test with df = 1, inbreeding),
seeded Wright–Fisher simulations (deterministic per seed; fixation in proportion to p₀ and
heterozygosity falling as H₀(1 − 1/2N)^t over many seeds; selection, migration and mutation
recursions against their closed forms; a bottleneck's expected heterozygosity) and a GWAS
(p-values as −log₁₀ p, chromosomes and positions checked, the thresholds, a synthetic study with
LD around its peaks, λ_GC, clumping of author data); the ``population`` and ``gwas`` scenes
validated and rendered in 16:9 and 9:16."""

from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_actions import project_with, render
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.genetics import gwas as gw
from vidgen.genetics import population as pg
from vidgen.genetics.stats import chi_square_p
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}


# ----- Hardy–Weinberg --------------------------------------------------------------------------------


def test_carrier_frequency_from_incidence_is_exact() -> None:
    hw = pg.hardy_weinberg({"incidence": "1/2500"})
    assert (hw.q, hw.p) == (Fraction(1, 50), Fraction(49, 50))
    assert hw.expected == (Fraction(2401, 2500), Fraction(49, 1250), Fraction(1, 2500))
    assert hw.carrier == Fraction(49, 1250) and pg.one_in(hw.carrier) == "1 in 25.5"
    assert sum(hw.expected) == 1
    assert "1 in 25" in hw.notes[0]                       # 2pq ≈ 2q for a rare allele
    odd = pg.hardy_weinberg({"incidence": "1/3000"})       # not a square: q is a float
    assert isinstance(odd.q, float) and odd.q == pytest.approx(1 / math.sqrt(3000))


def test_allele_frequencies_from_counts_and_the_chi_square_test() -> None:
    hw = pg.hardy_weinberg({"counts": {"MM": 298, "MN": 489, "NN": 213}, "alleles": ["M", "N"]})
    assert hw.p == Fraction(2 * 298 + 489, 2000) and hw.q == 1 - hw.p
    t = hw.test
    n = 1000
    expected = (n * hw.p ** 2, 2 * n * hw.p * hw.q, n * hw.q ** 2)
    assert t.expected == expected and t.df == 1
    stat = sum((o - e) ** 2 / e for o, e in zip((298, 489, 213), expected))
    assert t.statistic == stat
    assert t.p_value == pytest.approx(math.erfc(math.sqrt(float(stat) / 2)), abs=1e-12)    # χ²₁ upper tail
    assert t.critical == pytest.approx(3.841, abs=1e-3) and not t.rejected
    deficit = pg.hardy_weinberg({"counts": {"AA": 400, "Aa": 200, "aa": 400}})
    assert deficit.test.rejected and deficit.f_hat == Fraction(1) - Fraction(200, 1000) / Fraction(1, 2)
    small = pg.hardy_weinberg({"counts": {"AA": 90, "Aa": 9, "aa": 1}})
    assert small.test.small == ("aa",)


def test_frequencies_p_and_inbreeding() -> None:
    hw = pg.hardy_weinberg({"frequencies": {"AA": 0.36, "Aa": 0.48, "aa": 0.16}})
    assert hw.p == Fraction(3, 5) and hw.expected == (Fraction(9, 25), Fraction(12, 25), Fraction(4, 25))
    assert hw.f_hat == 0
    inbred = pg.hardy_weinberg({"p": 0.6, "inbreeding": 0.25})
    p, q, F = Fraction(3, 5), Fraction(2, 5), Fraction(1, 4)
    assert inbred.expected == (p * p + F * p * q, 2 * p * q * (1 - F), q * q + F * p * q)
    selfed = pg.hardy_weinberg({"p": "3/5", "inbreeding": 1})
    assert selfed.expected == (Fraction(3, 5), 0, Fraction(2, 5))


@pytest.mark.parametrize("spec, message", [
    ({"p": 1.2}, "outside \\[0, 1\\]"),
    ({"frequencies": {"AA": 0.5, "Aa": 0.4, "aa": 0.2}}, "must add up to 1"),
    ({"counts": {"AA": 10, "Aa": 20, "aa": 5}, "total": 40}, "not the total 40"),
    ({"counts": {"AA": 10, "Aa": -2, "aa": 5}}, "is not a count"),
    ({"counts": {"AA": 10, "Ab": 2, "aa": 5}}, "not a genotype of the alleles A and a"),
    ({"counts": {"AA": 10, "Aa": 2}}, "missing aa"),
    ({"p": 0.5, "incidence": "1/2500"}, "give one of counts"),
    ({"incidence": 0}, "between 0 and 1"),
    ({"alleles": ["A", "A"], "p": 0.5}, "two different"),
])
def test_hardy_weinberg_errors(spec: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        pg.hardy_weinberg(spec)


# ----- Wright–Fisher ---------------------------------------------------------------------------------


def test_drift_is_deterministic_for_a_seed() -> None:
    spec = {"model": "drift", "N": 25, "p0": 0.5, "generations": 60, "replicates": 5, "seed": 7}
    a, b = pg.simulate(spec), pg.simulate(spec)
    assert [line.values for line in a.lines] == [line.values for line in b.lines]
    assert a.individuals(30) == b.individuals(30)
    c = pg.simulate({**spec, "seed": 8})
    assert [line.values for line in a.lines] != [line.values for line in c.lines]
    for line in a.lines:                                   # 2N copies: frequencies are multiples of 1/2N
        assert all(abs(v * 50 - round(v * 50)) < 1e-9 for v in line.values)
        if line.fixed_at is not None:
            assert all(v == 1.0 for v in line.values[line.fixed_at:])
    # the dots carry exactly the first line's allele count
    g = a.individuals(30, 100)
    assert len(g) == 25 and (2 * g.count(0) + g.count(1)) / 50 == pytest.approx(a.lines[0].values[30])


def test_drift_fixes_in_proportion_to_p0_and_loses_heterozygosity_at_one_over_2n() -> None:
    fixed = total = 0
    h10: list[float] = []
    N, p0 = 10, 0.3
    for seed in range(1, 11):
        sim = pg.simulate({"model": "drift", "N": N, "p0": p0, "generations": 300, "replicates": 20, "seed": seed})
        fixed += len(sim.fixed())
        total += len(sim.lines)
        assert len(sim.fixed()) + len(sim.lost()) == len(sim.lines)     # all absorbed after 300 generations of N = 10
    assert fixed / total == pytest.approx(p0, abs=0.08)                 # P(fixation) = p₀ under drift alone
    for seed in range(1, 41):
        sim = pg.simulate({"model": "drift", "N": N, "p0": p0, "generations": 10, "replicates": 20, "seed": seed})
        h10 += [2 * line.values[10] * (1 - line.values[10]) for line in sim.lines]
    expected = 2 * p0 * (1 - p0) * (1 - 1 / (2 * N)) ** 10
    assert float(np.mean(h10)) == pytest.approx(expected, rel=0.06)     # E[H_t] = H₀ (1 − 1/2N)^t (800 lines: SE ≈ 2 %)
    assert sim.h_expected[10] == pytest.approx(expected)


def test_smaller_populations_drift_faster() -> None:
    def spread(n: int) -> float:
        sims = [pg.simulate({"model": "drift", "N": n, "p0": 0.5, "generations": 20, "replicates": 20, "seed": s}) for s in (1, 2)]
        return float(np.var([line.values[20] for sim in sims for line in sim.lines]))
    assert spread(10) > 2 * spread(200)


def test_selection_recursion_against_closed_forms() -> None:
    # a recessive lethal: q_t = q₀ / (1 + t q₀)
    sim = pg.simulate({"model": "selection", "p0": 0.8, "fitness": {"AA": 1, "Aa": 1, "aa": 0}, "generations": 30})
    for t in (1, 5, 30):
        assert 1 - sim.deterministic[0][t] == pytest.approx(0.2 / (1 + t * 0.2), rel=1e-12)
    # multiplicative fitnesses: p/q grows by (1 + s) each generation
    s = 0.1
    sim = pg.simulate({"model": "selection", "p0": 0.01, "fitness": {"AA": (1 + s) ** 2, "Aa": 1 + s, "aa": 1}, "generations": 40})
    for t in (1, 10, 40):
        p = sim.deterministic[0][t]
        assert p / (1 - p) == pytest.approx(0.01 / 0.99 * (1 + s) ** t, rel=1e-9)
    # s and h: w = 1, 1 − hs, 1 − s; heterozygote advantage gives a stable polymorphism
    assert pg.simulate({"model": "selection", "p0": 0.5, "s": 0.2, "h": 0.25, "generations": 1}).fitness == (1.0, 0.95, 0.8)
    over = pg.simulate({"model": "selection", "p0": 0.1, "fitness": {"AA": 0.9, "Aa": 1, "aa": 0.7}, "generations": 400})
    assert over.deterministic[0][-1] == pytest.approx(0.3 / (0.1 + 0.3), abs=1e-4)
    assert any("heterozygote advantage" in n for n in over.notes)
    with_drift = pg.simulate({"model": "selection", "N": 500, "p0": 0.1, "s": 0.1, "generations": 50, "replicates": 4})
    assert len(with_drift.lines) == 4 and with_drift.deterministic is not None


def test_migration_and_mutation_closed_forms() -> None:
    m = 0.05
    one_way = pg.simulate({"model": "migration", "populations": [{"name": "continent", "p0": 0.9}, {"name": "island", "p0": 0.1}],
                           "m": m, "direction": "one_way", "generations": 30})
    for t in (1, 10, 30):
        assert one_way.deterministic[1][t] == pytest.approx(0.9 + (0.1 - 0.9) * (1 - m) ** t, rel=1e-12)
        assert one_way.deterministic[0][t] == pytest.approx(0.9)
    both = pg.simulate({"model": "migration", "populations": [0.9, 0.1], "m": m, "generations": 20})
    d = [a - b for a, b in zip(*both.deterministic)]
    assert d[20] == pytest.approx(0.8 * (1 - 2 * m) ** 20, rel=1e-12)
    assert both.populations == ("population 1", "population 2")
    mut = pg.simulate({"model": "mutation", "p0": 1.0, "mu": 0.01, "nu": 0.005, "generations": 2000})
    assert mut.deterministic[0][-1] == pytest.approx(0.005 / 0.015, abs=1e-6)
    assert mut.deterministic[0][1] == pytest.approx(0.99)


def test_bottleneck_and_founder_heterozygosity() -> None:
    sim = pg.simulate({"model": "bottleneck", "N": 500, "p0": 0.5, "generations": 40, "replicates": 20, "seed": 2,
                       "bottleneck": {"at": 10, "N": 5, "generations": 3}})
    assert sim.sizes[9:14] == (500, 5, 5, 5, 500)
    h = 0.5
    for t in range(1, 41):
        h *= 1 - 1 / (2 * sim.sizes[t])
        assert sim.h_expected[t] == pytest.approx(h)
    assert sim.h_expected[12] / sim.h_expected[9] == pytest.approx((1 - 1 / 10) ** 3)
    means = []
    for seed in range(1, 9):
        s = pg.simulate({"model": "bottleneck", "N": 500, "p0": 0.5, "generations": 40, "replicates": 20, "seed": seed,
                         "bottleneck": {"at": 10, "N": 5, "generations": 3}})
        means.append(s.h_mean[-1])
    assert float(np.mean(means)) == pytest.approx(sim.h_expected[-1], rel=0.1)
    founder = pg.simulate({"model": "founder", "N": 400, "founders": 6, "p0": 0.3, "generations": 10, "replicates": 8})
    assert founder.sizes[0] == 6 and founder.source_p == 0.3
    assert founder.h_expected[0] == pytest.approx(2 * 0.3 * 0.7 * (1 - 1 / 12))
    assert all(abs(line.values[0] * 12 - round(line.values[0] * 12)) < 1e-9 for line in founder.lines)   # 12 founding copies
    assert len(founder.individuals(0, 100)) == 6


@pytest.mark.parametrize("spec, message", [
    ({"model": "drift", "p0": 0.5}, "needs N"),
    ({"model": "drift", "N": 20, "p0": 0.5, "s": 0.1}, "s: not a param of model: drift \\(a param of model: selection\\)"),
    ({"model": "selection", "p0": 0.5, "fitness": {"AA": 1, "Aa": -0.1, "aa": 1}}, "is negative"),
    ({"model": "selection", "p0": 0.5}, "needs fitness"),
    ({"model": "bottleneck", "N": 50, "p0": 0.5, "bottleneck": {"at": 5, "N": 80}}, "not smaller than N"),
    ({"model": "migration", "populations": [{"p0": 0.5}], "m": 0.1}, "two populations"),
    ({"model": "drift", "N": 20, "p0": 1.5}, "outside \\[0, 1\\]"),
    ({"model": "drfit", "N": 20, "p0": 0.5}, "did you mean 'drift'"),
])
def test_simulation_errors(spec: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        pg.build_population_plan(spec)


# ----- GWAS --------------------------------------------------------------------------------------------


def test_p_values_chromosomes_and_positions() -> None:
    assert gw.mlog10("5e-8") == pytest.approx(7.30103, abs=1e-5) and gw.mlog10(1e-5) == pytest.approx(5)
    assert gw.mlog10("3e-450") == pytest.approx(450 - math.log10(3))         # beyond floating point
    for bad in (0, 1.5, "-1e-3", "abc", True):
        with pytest.raises(VidgenError, match="p-value"):
            gw.mlog10(bad, "p")
    assert (gw.chromosome("chr7", "c"), gw.chromosome(23, "c"), gw.chromosome("x", "c")) == ("7", "X", "X")
    with pytest.raises(VidgenError, match="unknown chromosome 'Y'.*not drawn"):
        gw.chromosome("Y", "c")
    with pytest.raises(VidgenError, match="unknown chromosome '25'"):
        gw.chromosome(25, "c")
    assert gw.position("53.8 Mb", "16", "p") == pytest.approx(53.8) and gw.position(53_800_000, "16", "p") == pytest.approx(53.8)
    with pytest.raises(VidgenError, match="positions are in base pairs"):
        gw.position(53.8, "16", "p")
    with pytest.raises(VidgenError, match="beyond the end of chromosome 21"):
        gw.position("60 Mb", "21", "p")
    for z in (0.5, 3.0, 5.45, 20.0, 50.0):
        assert gw.z_of_mlog10(gw.mlog10_of_z(z)) == pytest.approx(z, rel=1e-6)


def test_synthetic_study_thresholds_and_lambda() -> None:
    spec = {"peaks": [{"chromosome": 16, "position": "53.8 Mb", "p": "1e-40", "gene": "FTO", "variant": "rs9939609"},
                      {"chromosome": 18, "position": 60_200_000, "p": 2e-14, "gene": "MC4R"}], "seed": 2}
    plan = gw.build_gwas_plan(spec)
    again = gw.build_gwas_plan(spec)
    assert [(v.chrom, v.pos, v.mlog10p) for v in plan.variants] == [(v.chrom, v.pos, v.mlog10p) for v in again.variants]
    assert plan.synthetic and "simulated data" in plan.notes[0] and plan.chromosomes == gw.CHROMOSOMES[:22]
    fto = plan.peak("FTO")
    assert fto.lead.mlog10p == pytest.approx(40) and fto.lead.id == "rs9939609" and fto.significant
    near = [v for v in plan.regional(fto) if v.peak == 0 and not v.lead]
    tight = [v for v in near if v.r2 >= 0.8]
    assert tight and min(v.mlog10p for v in tight) > 20      # variants in strong LD carry most of the lead's signal
    # the genome axis: chromosomes in order with a gap, the thresholds at −log10 of their p
    assert plan.offsets["1"] == 0 and plan.offsets["2"] > 248.9 and plan.genome > 2800
    assert -math.log10(gw.SIGNIFICANCE) == pytest.approx(7.30103, abs=1e-5) and -math.log10(gw.SUGGESTIVE) == 5
    assert plan.n_significant >= 2
    null = gw.build_gwas_plan({"background": 6000, "seed": 3})
    assert null.lambda_gc == pytest.approx(1.0, abs=0.08) and null.peaks == ()
    inflated = gw.build_gwas_plan({"background": 6000, "seed": 3, "inflation": 1.3})
    assert inflated.lambda_gc == pytest.approx(1.3, abs=0.1) and any("stratification" in n for n in inflated.notes)
    qq = null.qq
    assert qq[0][0] == pytest.approx(-math.log10(0.5 / 6000)) and all(a[1] >= b[1] for a, b in zip(qq, qq[1:]))


def test_author_data_from_csv_is_clumped_and_labelled() -> None:
    rows = ["CHR,BP,SNP,P"] + [f"{c},{1_000_000 + 5_000_000 * k},rs{c}_{k},0.{k + 1}" for c in range(1, 23) for k in range(5)]
    rows += ["19,44908684,rs429358,1e-80", "19,44910000,rs7412,1e-30", "6,32600000,rs9272346,2e-9"]
    data = gw.read_rows("\n".join(rows) + "\n", "assoc.csv")
    plan = gw.build_gwas_plan({"rows": data, "labels": {"rs429358": "APOE"}, "data": "assoc.csv"})
    assert not plan.synthetic and [p.label for p in plan.peaks] == ["APOE", "rs9272346"]   # rs7412 is within 500 kb of the lead
    assert plan.peak("APOE").lead.mlog10p == pytest.approx(80)
    with pytest.raises(VidgenError, match="no p column"):
        gw.read_rows("CHR,BP,SNP\n1,100000,rs1\n", "a.csv")
    with pytest.raises(VidgenError, match="line 3: unknown chromosome 'MT'"):
        gw.build_gwas_plan({"rows": gw.read_rows("CHR,BP,P\n1,100000,0.5\nMT,1000,0.1\n2,500000,0.3\n", "a.csv")})
    with pytest.raises(VidgenError, match="peaks make a synthetic study"):
        gw.build_gwas_plan({"rows": data, "peaks": [{"chromosome": 1, "position": "1 Mb", "p": 1e-9}]})


# ----- in projects -------------------------------------------------------------------------------------------


def problems(make_project: Any, scene: dict[str, Any]) -> list[str]:
    return [p.message for p in project_problems(project_with(make_project, [scene], narration=NARRATION))]


def one(kind: str, params: dict[str, Any], actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": "x", "type": kind, "params": params, "beats": [{"id": "b0", "text": "the population", "actions": actions or []}]}


DRIFT = {"model": "drift", "N": 20, "p0": 0.5, "generations": 50, "replicates": 4}
PEAKS = [{"chromosome": 16, "position": "53.8 Mb", "p": 1e-40, "gene": "FTO"}]


def test_scenes_are_validated(make_project) -> None:
    assert problems(make_project, one("population", DRIFT, [{"simulate": "generation:20"}, {"simulate": "lines"},
                                                            {"resample": "population"}])) == []
    assert any("simulate goes forward" in m
               for m in problems(make_project, one("population", DRIFT, [{"simulate": "generation:30"}, {"simulate": "generation:10"}])))
    assert any("generation:80" in m for m in problems(make_project, one("population", DRIFT, [{"simulate": "generation:80"}])))
    assert any("simulate needs a simulation" in m
               for m in problems(make_project, one("population", {"incidence": "1/2500"}, [{"simulate": "population"}])))
    assert problems(make_project, one("population", {"counts": {"AA": 10, "Aa": 20, "aa": 10}}, [{"reveal": "chi_square"}])) == []
    assert any("not a param of model: hardy_weinberg" in m for m in problems(make_project, one("population", {"p": 0.5, "N": 10})))
    assert problems(make_project, one("gwas", {"peaks": PEAKS}, [{"regional": "peak:FTO"}, {"highlight": "peak:FTO"}])) == []
    assert any("did you mean 'peak:FTO'" in m for m in problems(make_project, one("gwas", {"peaks": PEAKS}, [{"regional": "peak:FTOO"}])))
    assert any("p-value" in m for m in problems(make_project, one("gwas", {"peaks": [{**PEAKS[0], "p": 2}]})))
    assert any("is an action of gwas scenes" in m for m in problems(make_project, one("population", DRIFT, [{"regional": "peak:FTO"}])))


def test_a_csv_in_the_project_is_read(make_project) -> None:
    root = make_project(minimal_config(scenes=[one("gwas", {"data": "assoc.csv", "labels": {"rs1": "GENE1"}}, [{"highlight": "peak:GENE1"}])],
                                       narration=NARRATION))
    rows = ["CHR,BP,SNP,P", "1,1000000,rs1,1e-12", "2,5000000,rs2,0.3", "3,7000000,rs3,0.5", "4,9000000,rs4,0.9"]
    (root / "assoc.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert [p.message for p in project_problems(Project.load(root))] == []
    (root / "assoc.csv").write_text("CHR,BP,P\n1,1000000,7\n2,5000000,0.3\n3,6000000,0.2\n", encoding="utf-8")
    assert any("p-value 7 is out of range" in p.message for p in project_problems(Project.load(root)))


# ----- renders -------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_population_scenes_render(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [
        {"id": "hw", "type": "population", "params": {"title": "HWE", "counts": {"MM": 298, "MN": 489, "NN": 213}, "alleles": ["M", "N"]},
         "beats": [{"text": "the population"}, {"text": "the alleles", "actions": [{"reveal": "alleles"}]},
                   {"text": "the test", "actions": [{"reveal": "chi_square"}, {"resample": "population"}]}]},
        {"id": "drift", "type": "population", "params": {**DRIFT, "title": "Drift"},
         "beats": [{"text": "start"}, {"text": "drift", "actions": [{"simulate": "generation:20"}]},
                   {"text": "end", "actions": [{"simulate": "lines"}]}]},
        {"id": "bottle", "type": "population", "params": {"model": "bottleneck", "N": 200, "p0": 0.5, "generations": 30, "replicates": 4,
                                                          "bottleneck": {"at": 10, "N": 4, "generations": 2}},
         "beats": [{"text": "large"}, {"text": "small"}]},
        {"id": "gwas", "type": "gwas", "params": {"title": "GWAS", "plot": "both", "peaks": PEAKS, "background": 400},
         "beats": [{"text": "points"}, {"text": "the locus", "actions": [{"regional": "peak:FTO"}]}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 3.0})))
    hw = render(project, "hw", media, size)
    assert {"alleles", "expected", "chi_square"} <= hw.done and hw.resamples == 1
    drift = render(project, "drift", media, size)
    assert drift.gen_now == 50 and drift.card_mob is not None
    bottle = render(project, "bottle", media, size)
    assert bottle.gen_now == 30
    g = render(project, "gwas", media, size)
    assert {"points", "thresholds", "peaks", "qq"} <= g.done and g.regional_mob is not None
