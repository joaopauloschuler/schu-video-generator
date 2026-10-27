"""The beat actions of ``linkage_map`` scenes (DESIGN.md §96.9): ``cross_over`` (non-sister
chromatids join at a chiasma in an interval and swap the segments beyond it, giving recombinant
chromatids) and ``measure`` (a distance on the map with the RF its map function gives). Timed like
any action (``at: "@word"``); the built-in ``reveal`` plays the steps of a worked test cross.
Written against ``vidgen.api``; the scene draws (``scenes/linkage_map.py``)."""

from typing import Any

from vidgen.api import *

mp = genetics.mapping


def _check(scene_cls: type[NarratedScene], name: str) -> list[tuple[str, str]]:
    if not getattr(scene_cls, "linkage_actions", False):
        return [("action", f"{name} is an action of linkage_map scenes (type: linkage_map)")]
    return []


def _intervals(plan: Any, targets: list[str]) -> tuple[int, ...]:
    out: set[int] = set()
    for t in targets:
        if t in ("double", "both"):
            out.update(range(len(plan.ordered) - 1))
        else:
            out.add(mp.crossover_index(t.split(":", 1)[-1], plan.ordered, "cross_over"))
    return tuple(sorted(out))


@action("cross_over")
class CrossOver(Action):
    """Crossing over in the heterozygote's homologue pair (``cross_over: interval:v-ct``, or
    ``double`` for one in each interval of three loci): the two inner, non-sister chromatids
    meet at a chiasma, exchange the segments beyond it and part again — two recombinant and two
    parental chromatids, each with its alleles written beside it in the colours of the homologue
    they came from. A second ``cross_over`` starts from the pair as it was."""

    run_time = 2.4
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _check(scene_cls, "cross_over")
        if problems:
            return problems
        if not params.chromosomes:
            return [("action", "cross_over draws on the chromosomes: leave chromosomes: true")]
        plan = params.plan()
        for t in self.config.targets():
            if t in ("double", "both"):
                if len(plan.ordered) < 3:
                    return [("target", "double needs three loci (a crossover in each interval)")]
                continue
            if not t.startswith("interval:"):
                return [("target", f"cross_over acts on interval:<a>-<b> (neighbouring loci) or double, not '{t}'")]
            try:
                mp.crossover_index(t[9:], plan.ordered, "cross_over")
            except VidgenError as error:
                return [("target", str(error))]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.cross_seconds()  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        scene.seg_owner = [[0 if c < 2 else 1 for _ in row] for c, row in enumerate(scene.seg_owner)]  # type: ignore[attr-defined]
        return scene.run_cross(_intervals(scene.plan, self.config.targets()))  # type: ignore[attr-defined]


@action("measure")
class Measure(Action):
    """A distance on the map (``measure: interval:w-v``): a bracket over it and a card with the
    distance in cM and the recombination frequency it gives with the scene's map function (none:
    RF = d/100, at most 50 %; Haldane; Kosambi), with a warning when d/100 is used beyond short
    distances."""

    run_time = 1.6
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _check(scene_cls, "measure")
        if problems:
            return problems
        plan = params.plan()
        targets = self.config.targets()
        if len(targets) != 1 or not targets[0].startswith("interval:"):
            return [("target", f"measure names one interval: interval:{plan.ordered[0]}-{plan.ordered[-1]}")]
        try:
            mp.measure_interval(plan, targets[0][9:])
        except VidgenError as error:
            return [("target", str(error))]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.measure_seconds()  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.run_measure(self.config.targets()[0][9:])  # type: ignore[attr-defined]
