"""The beat actions of the ``feynman`` scene type (Phase Y, Step 238; DESIGN §99.6): ``travel``
(a particle dot runs along lines in time order), ``vertex_rule`` (ring a vertex and state its
rule: the vertex type, the coupling, the conservation checks) and ``swap_channel`` (morph into
another diagram of the same reaction: s ↔ t, γ ↔ Z, top ↔ W loop). ``highlight`` and ``dim``
work on ``line:<id>`` and ``vertex:<id>`` as on any target. Timed like any action (``at:
"@word"``). Written against ``vidgen.api``; the scene draws (``scenes/feynman.py``)."""

from fnmatch import fnmatchcase
from typing import Any, Literal

from vidgen.api import *

RuleShown = Literal["rule", "coupling", "checks"]


def _problems(action: str, scene_cls: type[NarratedScene]) -> list[tuple[str, str]]:
    if not getattr(scene_cls, "feynman_actions", False):
        return [("action", f"{action} is an action of feynman scenes (type: feynman)")]
    return []


@action("travel")
class Travel(Action):
    """A particle dot runs along lines in time order: ``travel: "line:mu"`` (one line),
    ``travel: ["line:e_minus", "line:photon", "line:mu_minus"]`` (one after another on one
    clock) or ``travel: diagram`` (a dot on every line at once, the whole reaction flowing from
    left to right). A line drawn across at one time (a t-channel exchange) is crossed in a
    moment. The dot is gone when it arrives."""

    class Options(ActionOptions):
        color: ThemeColor = "highlight"
        """Colour of the dot."""

    run_time = 2.0
    needs_target = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _problems("travel", scene_cls)
        if problems:
            return problems
        for pattern in self.config.targets():
            if pattern != "diagram" and not _matched_one(scene_cls, params, pattern, "line:"):
                return [("target", f"travel runs along lines: line:<id> or diagram; '{pattern}' is neither")]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        ids = scene.line_ids(targets)  # type: ignore[attr-defined]
        return scene.travel(ids, scene.theme.color(self.options.color))  # type: ignore[attr-defined]


def _matched_one(scene_cls: type[NarratedScene], params: Any, pattern: str, prefix: str) -> bool:
    names = [n for n in scene_cls.target_names(params) if n.startswith(prefix)]
    return any(fnmatchcase(n, pattern) for n in names)


@action("vertex_rule")
class VertexRuleAction(Action):
    """Ring a vertex and state its rule under the diagram (``vertex_rule: "vertex:v1"``): the
    vertex type with the lines meeting there ("electromagnetic vertex (QED): e⁻ e⁺ → γ"), the
    coupling ("coupling Q·e; α ≈ 1/137"; the W's g ≈ 0.65 and CKM element; the Higgs coupling
    ∝ mass) and, with ``show: [rule, coupling, checks]``, the conservation checks ("Q: −1 + +1 →
    0 ✓"). Undone when the next beat starts (or at ``until``)."""

    class Options(ActionOptions):
        show: list[RuleShown] = Field(default_factory=lambda: ["rule", "coupling"], min_length=1)
        """What to state: rule (vertex type and lines), coupling, checks (charge, baryon and lepton numbers)."""
        color: ThemeColor = "highlight"
        """Colour of the ring."""

    run_time = 0.8
    reversible = True
    until_next_beat = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _problems("vertex_rule", scene_cls)
        if problems:
            return problems
        targets = self.config.targets()
        if len(targets) != 1 or not _matched_one(scene_cls, params, targets[0], "vertex:") or any(c in targets[0] for c in "*?["):
            vertices = [n for n in scene_cls.target_names(params) if n.startswith("vertex:")]
            return [("target", f"vertex_rule names one vertex ({', '.join(vertices)})")]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        vertex = next((n[7:] for t in targets for n in t.names if n.startswith("vertex:")), "")
        anims, self.state = scene.show_rule(vertex, list(self.options.show), scene.theme.color(self.options.color))  # type: ignore[attr-defined]
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.hide_rule(self.state)  # type: ignore[attr-defined]


@action("swap_channel")
class SwapChannel(Action):
    """Morph the diagram into another of the scene's diagrams (``- action: swap_channel``: the
    next one; ``to: t``): Bhabha's s- into its t-channel, e⁺e⁻ → μ⁺μ⁻ through a photon into
    through a Z, H → γγ's top loop into its W loop. Lines and vertices with the same id move to
    their new places, the others are drawn or fade, and the reaction line takes the new label.
    ``until:`` swaps back."""

    class Options(ActionOptions):
        to: str | None = None
        """The diagram to show (its name: s, t, u, photon, Z, top, W, leptonic…); default the next one."""

    run_time = 1.2
    needs_target = False
    reversible = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _problems("swap_channel", scene_cls)
        if problems:
            return problems
        names = [d.name for d in scene_cls.diagram_list(params)]  # type: ignore[attr-defined]
        if len(names) < 2:
            return [("action", f"swap_channel needs a scene with two or more diagrams (this one has {', '.join(names)})")]
        if self.options.to is not None and self.options.to not in names:
            return [("to", f"no diagram '{self.options.to}' (diagrams: {', '.join(names)}){did_you_mean(self.options.to, names)}")]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        self.before = scene.current.name  # type: ignore[attr-defined]
        return scene.swap(self.options.to)  # type: ignore[attr-defined]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.swap(self.before)  # type: ignore[attr-defined]
