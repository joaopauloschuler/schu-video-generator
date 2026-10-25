"""The beat actions of the molecular genetics scenes (DESIGN.md §96.13–96.15): ``mutate`` (a
``mutation`` scene's variant made from the reference), ``scan``, ``cleave``, ``repair`` (a
``crispr`` scene's Cas9: PAM search and R-loop, the double-strand break, NHEJ or HDR) and ``run``
(a ``dna_lab`` scene's step: PCR cycles, the gel running, Sanger synthesis / capillary / trace, NGS
reads / coverage / call). Timed like any action (``at: "@word"``). Written against
``vidgen.api``; the scenes draw (``scenes/mutation.py``, ``scenes/crispr.py``,
``scenes/dna_lab.py``)."""

from typing import Any

from vidgen.api import *


def _variant_indices(params: Any, targets: list[str]) -> list[int]:
    n = len(params.plan().variants)
    out: list[int] = []
    for t in targets:
        ids = list(range(n)) if t in ("variants", "all") else [0] if t == "variant" else [int(t.split(":", 1)[1]) - 1]
        out += [i for i in ids if i not in out]
    return out


@action("mutate")
class Mutate(Action):
    """Make a variant of a ``mutation`` scene (``mutate: variant`` — the first —, ``variant:2``,
    or ``variants`` for all in turn): a copy of the reference row drops into the variant row and
    changes — a base swaps, bases leave or come in and the rest slide through the fixed codon
    frame (a frameshift regroups every codon after it) —, the amino acids follow (the changed ones
    highlighted, a stop in red), and the card gives the HGVS c. and p. notation, the class and the
    notes."""

    run_time = 3.0
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "mutation_actions", False):
            return [("action", "mutate is an action of mutation scenes (type: mutation)")]
        n = len(params.plan().variants)
        for t in self.config.targets():
            if t in ("variant", "variants", "all"):
                continue
            if not t.startswith("variant:") or not t[8:].isdigit() or not 1 <= int(t[8:]) <= n:
                return [("target", f"mutate acts on variant, variant:1…variant:{n} (the changes in the order listed) or variants, not '{t}'")]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.mutate_seconds() * len(_variant_indices(scene.params, self.config.targets()))  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims: list[Animation] = []
        for k in _variant_indices(scene.params, self.config.targets()):
            anims += scene.run_mutate(k)  # type: ignore[attr-defined]
        return [Succession(*anims)] if len(anims) > 1 else anims


class _CrisprStep(Action):
    """A step of a crispr scene; the steps before it play first."""

    step = ""
    targets_allowed: tuple[str, ...] = ()
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "crispr_actions", False):
            return [("action", f"{self.step} is an action of crispr scenes (type: crispr)")]
        if self.step == "repair" and params.repair == "none":
            return [("action", "repair: the scene is set to repair: none (the break only); choose repair: nhej or hdr")]
        for t in self.config.targets():
            if t not in self.targets_allowed:
                return [("target", f"{self.step} acts on {', '.join(self.targets_allowed)}, not '{t}'"
                         + did_you_mean(t, list(self.targets_allowed)))]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.step_seconds(self.step)  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.run_step(self.step)  # type: ignore[attr-defined]


@action("scan")
class Scan(_CrisprStep):
    """The nuclease searches the DNA (``scan: dna``, or ``cas9`` / ``pam``): it looks at the PAMs
    it passes, settles on the protospacer's own PAM, the DNA opens and the sgRNA's spacer pairs
    with the target strand while the other strand is displaced (the R-loop). The card names the
    enzyme, its PAM, the spacer and the guides the target offers."""

    run_time = 3.0
    step = "scan"
    targets_allowed = ("dna", "cas9", "sgrna", "pam")


@action("cleave")
class Cleave(_CrisprStep):
    """The double-strand break (``cleave: dna``, or ``cut``): both strands are cut 3 bp upstream
    (5′) of the PAM and the blunt ends part. The scan plays first when it has not."""

    run_time = 1.6
    step = "cleave"
    targets_allowed = ("dna", "cut")


@action("repair")
class Repair(_CrisprStep):
    """The repair of the break (``repair: repair``, or ``dna``), as the scene's ``repair:`` param
    says: the enzyme leaves and the ends are joined — with a small indel (NHEJ) or from a donor
    template (HDR) — and the card gives the repaired allele's change in HGVS with its protein
    consequence, whether the frame is kept and whether the allele can be cut again."""

    run_time = 2.8
    step = "repair"
    targets_allowed = ("dna", "repair")


@action("run")
class Run(Action):
    """A step of a ``dna_lab`` scene, named by what it shows: ``run: cycle`` (PCR cycles and
    their temperature trace), ``counts``, ``gel`` / ``ladder`` / ``lane:<label>`` (the samples
    running), ``sizes`` (read off the ladder), ``fragments``, ``chromatogram``, ``reads``,
    ``coverage``, ``call``. The steps before it play first, so one action can carry a whole
    method."""

    run_time = 2.2
    needs_visible = False

    #: Which step of each method a target belongs to.
    OF_TARGET = {"template": "setup", "primers": "setup", "product": "setup", "trace": "cycle", "counts": "count",
                 "gel": "setup", "ladder": "run", "sizes": "read", "sequence": "setup", "fragments": "separate",
                 "chromatogram": "trace", "reference": "setup", "reads": "align", "coverage": "align", "call": "call"}

    def _steps(self, params: Any) -> list[str]:
        out: list[str] = []
        for t in self.config.targets():
            step = self.OF_TARGET.get(t) or ("cycle" if t.startswith("cycle:") else "run" if t.startswith("lane:") else None)
            if step is not None and step not in out:
                out.append(step)
        return out

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "lab_actions", False):
            return [("action", "run is an action of dna_lab scenes (type: dna_lab)")]
        names = scene_cls.target_names(params)
        for t in self.config.targets():
            if t == "title" or t not in names:
                allowed = [n for n in names if n != "title"]
                return [("target", f"run plays a step of this method: {', '.join(allowed)}; '{t}' is not one"
                         + did_you_mean(t, allowed))]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        steps = self._steps(scene.params)
        return max([scene.step_seconds(s) for s in steps] or [None])  # type: ignore[attr-defined,list-item]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims: list[Animation] = []
        for s in self._steps(scene.params):
            anims += scene.run_step(s)  # type: ignore[attr-defined]
        return [Succession(*anims)] if len(anims) > 1 else anims
