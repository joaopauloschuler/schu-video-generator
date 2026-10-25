"""The beat actions of the population genetics scenes (DESIGN.md §96.16–96.17): ``simulate`` and
``resample`` (a ``population`` scene's generations and individuals) and ``regional`` (a ``gwas``
scene's zoom into a locus). Timed like any action (``at: "@word"``). Written against
``vidgen.api``; the scenes draw (``scenes/population.py``, ``scenes/gwas.py``)."""

from typing import Any

from vidgen.api import *


#: Targets that run a simulation to its last generation.
TO_END = ("lines", "plot", "deterministic", "heterozygosity")


def target_generation(params: Any, targets: list[str]) -> int:
    """The generation a ``simulate`` reaches (its latest target)."""
    T = params.plan().sim.generations
    out = 0
    for t in targets:
        out = max(out, T if t in TO_END else int(t.split(":", 1)[1]))
    return out


@action("simulate")
class Simulate(Action):
    """Run a ``population`` simulation on a word: ``simulate: "generation:40"`` grows every line
    (and the deterministic curve and the heterozygosity) to generation 40; ``simulate: lines`` (or ``plot``) to
    the last generation. The dots follow the first line; lines that fix or lose the allele get a
    dot where they do; at the last generation the card gives the outcome."""

    run_time = 3.2
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "population_actions", False):
            return [("action", "simulate is an action of population scenes (type: population)")]
        plan = params.plan()
        if plan.sim is None:
            return [("action", "simulate needs a simulation (model: drift, selection, mutation, migration, bottleneck or founder); "
                     "a hardy_weinberg scene uses reveal: alleles / expected / chi_square and resample")]
        T = plan.sim.generations
        for t in self.config.targets():
            if t in TO_END:
                continue
            if not t.startswith("generation:") or not t[11:].isdigit() or not 1 <= int(t[11:]) <= T:
                return [("target", f"simulate acts on generation:1…generation:{T} (up to that generation), lines or plot (to the last generation), not '{t}'")]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.simulate_seconds(target_generation(scene.params, self.config.targets()))  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.advance_to(target_generation(scene.params, self.config.targets()))  # type: ignore[attr-defined]


@action("resample")
class Resample(Action):
    """A new generation of a ``population`` scene's individuals (``resample: population``): in a
    simulation the next generation of the first line (its 2N gene copies drawn from this one's,
    and every line one generation on); in a Hardy–Weinberg scene a new random sample of 100 at the
    expected genotype frequencies."""

    run_time = 1.4
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "population_actions", False):
            return [("action", "resample is an action of population scenes (type: population)")]
        for t in self.config.targets():
            if t not in ("population", "dots"):
                return [("target", f"resample acts on population, not '{t}'" + did_you_mean(t, ["population"]))]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.resample()  # type: ignore[attr-defined]


@action("regional")
class Regional(Action):
    """Zoom into a locus of a ``gwas`` scene (``regional: "peak:FTO"``): the peak's window is
    boxed on the Manhattan plot and its regional plot drawn — each variant at its position
    (Mb), coloured by r² with the lead variant (a diamond), the significance line."""

    run_time = 2.6
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "gwas_actions", False):
            return [("action", "regional is an action of gwas scenes (type: gwas)")]
        if params.plot == "qq":
            return [("action", "regional zooms into a Manhattan plot: use plot: manhattan or both")]
        targets = self.config.targets()
        if len(targets) != 1:
            return [("target", "regional takes one peak (one regional plot per scene)")]
        names = [n for n in scene_cls.target_names(params) if n.startswith("peak:")]
        if names and targets[0] not in names:
            return [("target", f"regional acts on a peak: {', '.join(names)}; '{targets[0]}' is not one" + did_you_mean(targets[0], names))]
        if not targets[0].startswith("peak:"):
            return [("target", f"regional acts on a peak (peak:<label>), not '{targets[0]}'")]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.regional_seconds()  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.run_regional(self.config.targets()[0].split(":", 1)[1])  # type: ignore[attr-defined]
