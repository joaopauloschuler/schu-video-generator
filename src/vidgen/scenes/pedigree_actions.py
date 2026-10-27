"""The beat actions of ``pedigree`` scenes (DESIGN.md §96.8): ``deduce`` (the genotypes the chart
forces, carrier probabilities, obligate carriers' marks), ``analyse`` (the modes of inheritance
tried one by one: fits, or excluded with the reason while the people it names are ringed) and
``risk`` (the proposed child and its risk with the factors of the product). Timed like any
action (``at: "@word"``); the built-in ``reveal`` brings in generations or people,
``highlight`` / ``dim`` mark them. Written against ``vidgen.api``; the scene draws
(``scenes/pedigree.py``)."""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *


def _check(action: Action, scene_cls: type[NarratedScene], name: str) -> list[tuple[str, str]]:
    if not getattr(scene_cls, "pedigree_actions", False):
        return [("action", f"{name} is an action of pedigree scenes (type: pedigree)")]
    return []


def _matching(pattern: str, names: list[str]) -> list[str]:
    if "*" not in pattern and "?" not in pattern:
        return [pattern] if pattern in names else []
    return [n for n in names if fnmatchcase(n, pattern)]


def _people(scene: Any, targets: list[str]) -> list[str]:
    """The people the targets stand for (everyone, a generation, a person, the carriers)."""
    ped = scene.ped
    out: list[str] = []
    names = [n for t in scene.targets for n in t.names]
    for pattern in targets:
        for name in _matching(pattern, names):
            if name in ("genotypes", "all", "chart"):
                ids = list(ped.people)
            elif name == "carriers":
                obligate = scene.inference.obligate if scene.inference is not None else ()
                ids = [x for x in ped.people if ped.people[x].carrier or x in obligate]
            elif name.startswith("generation:"):
                g = genetics.pedigree.roman_value(name[11:]) - 1
                ids = [x for x in ped.people if ped.generation[x] == g]
            elif name.startswith("person:"):
                key = name[7:]
                ids = [x for x in ped.people if x == key or ped.label(x) == key]
            else:
                ids = []
            out += [x for x in ids if x not in out]
    return out


@action("deduce")
class Deduce(Action):
    """Show the genotypes the chart gives (``deduce: genotypes``, ``carriers``,
    ``generation:II``, ``person:II-3``): under each symbol the forced genotype (``Aa``,
    ``XᴴXʰ``) or the most telling one with its exact probability (``2/3 Aa``), worked out by
    Bayes' rule on the whole chart under the scene's mode; obligate carriers get the carrier
    mark and the highlight colour. People not shown yet appear first."""

    run_time = 1.4
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _check(self, scene_cls, "deduce")
        if problems:
            return problems
        plan = params.plan()
        if plan.mode is None:
            return [("action", params.no_mode_message(plan, "deduce"))]
        for t in self.config.targets():
            if not (t in ("genotypes", "all", "carriers") or t.startswith(("generation:", "person:"))):
                return [("target", f"deduce acts on genotypes, carriers, generation:<R> or person:<id>, not '{t}'")]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.deduce_seconds()  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.run_deduce(_people(scene, self.config.targets()))  # type: ignore[attr-defined]


@action("analyse")
class Analyse(Action):
    """Try the modes of inheritance on the chart (``analyse: modes`` for all in turn, or
    ``mode:XR`` for one): each row says whether the mode fits, or why it is excluded ("affected
    father II-1 has an affected son III-1, but a son's X comes from his mother…") while the
    people the reason names are ringed; after the last one, the modes that fit. Exact: a mode
    fits when some genotypes explain every phenotype (with the scene's penetrance and the rare
    allele assumption)."""

    run_time = 1.0
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _check(self, scene_cls, "analyse")
        if problems:
            return problems
        for t in self.config.targets():
            if not (t in ("modes", "analysis") or t.startswith("mode:")):
                return [("target", f"analyse acts on modes (all in turn) or mode:<AD, AR, XD, XR, YL, MT>, not '{t}'")]
        return []

    def _codes(self, scene: Any) -> list[str]:
        out: list[str] = []
        names = [f"mode:{c}" for c in scene.mode_rows] + ["modes", "analysis"]
        for pattern in self.config.targets():
            for name in _matching(pattern, names):
                codes = list(scene.mode_rows) if name in ("modes", "analysis") else [name[5:]]
                out += [c for c in codes if c not in out]
        return out

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.analyse_seconds(self._codes(scene))  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.run_analyse(self._codes(scene))  # type: ignore[attr-defined]


@action("risk")
class RiskAction(Action):
    """The risk for the proposed child (``risk: risk``): its dashed symbol with a question mark
    appears, then the card with the factors of the product (``P(II-3 is Aa) = 2/3``, ``both
    pass a: 1/4``…) and the exact risk, which is also written under the child."""

    run_time = 2.2
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _check(self, scene_cls, "risk")
        if problems:
            return problems
        plan = params.plan()
        if plan.ped.proposed is None:
            return [("action", "risk needs a proposed child: an individual with proposed: true and its parents")]
        if plan.mode is None:
            return [("action", params.no_mode_message(plan, "risk"))]
        for t in self.config.targets():
            if t not in ("risk", "child"):
                return [("target", f"risk acts on risk, not '{t}'")]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.risk_seconds()  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.run_risk()  # type: ignore[attr-defined]
