"""The beat actions of ``pathway`` scenes (DESIGN.md §95.12): ``signal`` (the signal runs from a
node along the arcs, wave by wave: nodes light up, GDP is swapped for GTP, phosphorylation marks
appear; an inhibitor of an inhibitor turns its target on), ``inhibit`` (an inhibitor engages: its
targets are held and what depends on them dims), ``knockout`` and ``drug`` (a node is removed or
blocked; the effects downstream, computed from the graph, are shown as ↑ / ↓ on each node that
changes), ``amplify`` (one enzyme, many messengers). ``focus`` (``iso_actions``) moves the camera
onto nodes and ``highlight`` marks them. Timed like any action (``at: "@word"``); ``until:``
undoes them. Written against ``vidgen.api``; the scene draws (``scenes/pathway_play.py``)."""

from typing import Any

from vidgen.api import *

PATHWAY_ACTIONS = ("signal", "inhibit", "knockout", "drug", "amplify")


def _scene_check(action: Action, scene_cls: type[NarratedScene], params: Any, name: str, *, one: bool = True) -> tuple[list[tuple[str, str]], Any]:
    """The checks every pathway action shares: a pathway scene, node targets (one unless
    ``one`` is false), no wildcards. Returns the problems and the pathway."""
    if not getattr(scene_cls, "pathway_actions", False):
        return [("action", f"{name} is an action of pathway scenes (type: pathway)")], None
    targets = action.config.targets()
    if any(ch in t for t in targets for ch in "*?["):
        return [("target", f"{name} names nodes one by one (no wildcards)")], None
    if one and len(targets) != 1:
        return [("target", f"{name} acts on one node")], None
    pathway = params.pathway()
    for t in targets:
        if t not in pathway.nodes:
            return [("target", f"{name} acts on nodes; '{t}' is not one{did_you_mean(t, list(pathway.nodes))}")], None
    return [], pathway


class _PathwayAction(Action):
    """An action of pathway scenes that ``until:`` undoes."""

    reversible = True

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        undo = getattr(self, "_undo", None)
        self._undo = None
        return undo() if undo is not None else []


@action("signal")
class Signal(_PathwayAction):
    """A signal runs through the pathway from a node (``signal: egf``): wave by wave along the
    arcs, each arc lit as it passes, each node it reaches lit (a G protein or GTPase swaps GDP
    for GTP, a phosphorylated site appears: pS133); an inhibitory arc turns its target off and an
    inhibitor of an inhibitor turns its target on (Akt ⊣ TSC2 ⊣ Rheb → mTORC1). ``to: creb``
    follows only the shortest activating path there; ``signal: [gcgr, gas, ac]`` runs along that
    path. A knocked-out, drug-blocked or inhibited node stops it there (it flashes). Feedback
    arcs fire last (``feedback: false`` leaves them out). About 0.75 s per step."""

    class Options(ActionOptions):
        to: str | None = None
        """Only the shortest activating path to this node."""
        feedback: bool = True
        """Show the feedback arcs firing after the rest."""

    run_time = 4.0
    target_options = ("to",)

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems, pathway = _scene_check(self, scene_cls, params, "signal", one=False)
        if problems:
            return problems
        problem = cell_pathway.signal_problem(pathway, self.config.targets(), self.options.to)
        return [("target", problem)] if problem else []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        self._waves = scene.signal_plan(self.config.targets(), self.options.to, self.options.feedback)  # type: ignore[attr-defined]
        return scene.signal_seconds(self._waves)  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        waves = getattr(self, "_waves", None)
        if waves is None:
            waves = scene.signal_plan(self.config.targets(), self.options.to, self.options.feedback)  # type: ignore[attr-defined]
        anims, self._undo = scene.run_signal(self.config.targets(), waves)  # type: ignore[attr-defined]
        return anims


@action("inhibit")
class Inhibit(_PathwayAction):
    """An inhibitor engages (``inhibit: pten``): it lights, its T-bars flash, its targets are
    held (dimmed, red outline) and the nodes downstream that change are marked ↑ or ↓ (computed
    from the graph). ``on: [pip3]`` engages only some of its arcs. A signal stops at a held node."""

    class Options(ActionOptions):
        on: list[str] = Field(default_factory=list)
        """Only these targets of its inhibitory arcs (default: all)."""
        effects: bool = True
        """Mark the nodes downstream that change (↑ / ↓)."""

    run_time = 2.5

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems, pathway = _scene_check(self, scene_cls, params, "inhibit")
        if problems:
            return problems
        node = self.config.targets()[0]
        arcs = cell_pathway.inhibitor_arcs(pathway, node)
        if not arcs:
            return [("target", f"inhibit: '{node}' has no inhibitory arc (a -| b, or type: inhibits / effect: inhibits) to engage")]
        known = [e.target for e in arcs]
        for t in self.options.on:
            if t not in known:
                return [("on", f"'{node}' does not inhibit '{t}'{did_you_mean(t, known)} (it inhibits {', '.join(known)})")]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims, self._undo = scene.run_inhibit(self.config.targets()[0], list(self.options.on), self.options.effects)  # type: ignore[attr-defined]
        return anims


@action("knockout")
class Knockout(_PathwayAction):
    """Knock a node out (``knockout: pten``; a gene, a protein): it is crossed out and fades,
    and every node downstream that changes is marked ↑ or ↓ (from the graph: losing PTEN raises
    PIP3, Akt and mTORC1 and lowers GSK3β and FOXO). A signal stops there."""

    class Options(ActionOptions):
        effects: bool = True
        """Mark the nodes downstream that change (↑ / ↓)."""

    run_time = 2.5

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems, pathway = _scene_check(self, scene_cls, params, "knockout")
        return problems

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims, self._undo = scene.run_knockout(self.config.targets()[0], self.options.effects)  # type: ignore[attr-defined]
        return anims


@action("drug")
class Drug(_PathwayAction):
    """A drug blocks a node (``drug: mek, name: trametinib``): a pill with its name appears
    beside it with a T-bar, the node is blocked and the effects downstream are marked ↑ / ↓. A
    known drug on another target is refused (trametinib inhibits MEK, not ERK); genes, small
    molecules and outcomes are not drug targets (knockout a gene; block the enzyme that makes a
    messenger). A signal stops at a blocked node."""

    class Options(ActionOptions):
        name: str = Field("inhibitor", min_length=1, max_length=40)
        """The drug's name (shown in its pill; a known drug is checked against its target)."""
        effects: bool = True
        """Mark the nodes downstream that change (↑ / ↓)."""

    run_time = 2.5

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems, pathway = _scene_check(self, scene_cls, params, "drug")
        if problems:
            return problems
        problem = cell_pathway.drug_problem(pathway, self.config.targets()[0], self.options.name)
        return [("target", problem)] if problem else []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims, self._undo = scene.run_drug(self.config.targets()[0], self.options.name, self.options.effects)  # type: ignore[attr-defined]
        return anims


@action("amplify")
class Amplify(_PathwayAction):
    """Amplification (``amplify: camp, factor: "×100"``): many copies of a node stream out of
    the node that makes or activates it (``from``; default its activating input: adenylyl
    cyclase for cAMP) and gather round it, with the factor written beside it (one receptor
    activates many G proteins; each adenylyl cyclase makes many cAMP)."""

    class Options(ActionOptions):
        source: str | None = Field(None, alias="from")
        """The node they come from (default: its activating input)."""
        count: int = Field(10, ge=2, le=24)
        """How many copies are drawn."""
        factor: str | None = Field(None, max_length=24)
        """The amplification written beside it ("×100", "~10⁴ per receptor")."""

    run_time = 2.4
    target_options = ("source",)

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems, pathway = _scene_check(self, scene_cls, params, "amplify")
        if problems:
            return problems
        node = self.config.targets()[0]
        ins = [e for e in pathway.in_edges(node) if e.sign > 0 and not e.feedback]
        if not ins:
            return [("target", f"amplify: nothing activates or makes '{node}' (no activating arc into it)")]
        if self.options.source is not None and self.options.source not in [e.source for e in ins]:
            known = [e.source for e in ins]
            return [("from", f"'{self.options.source}' does not activate or make '{node}'{did_you_mean(self.options.source, known)} "
                             f"(from: {', '.join(known)})")]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        o = self.options
        factor = None if o.factor is None else str(o.factor)
        anims, self._undo = scene.run_amplify(self.config.targets()[0], o.source, o.count, factor)  # type: ignore[attr-defined]
        return anims


def sequence_problems(spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
    """The pathway actions replayed in beat and ``at`` order, each lasting until its ``until``
    beat: a node knocked out (or drugged) while it already is, a signal from a node that is off,
    an inhibitor that is off engaging."""
    beats = [b.id for b in spec.beats]

    def beat_of(use: Any) -> int:
        return beats.index(use.beat) if use.beat in beats else 0

    order = sorted(range(len(uses)), key=lambda i: (beat_of(uses[i]), uses[i].config.fraction, i))
    active: list[tuple[str, str, int, int]] = []   # (action, node, from beat, until beat)
    problems: list[tuple[str, str]] = []
    for i in order:
        use = uses[i]
        name = use.kind.name
        if name not in PATHWAY_ACTIONS:
            continue
        b = beat_of(use)
        now = [(a, n) for a, n, start, end in active if end > b]
        off = {n: a for a, n in now if a in ("knockout", "drug")}
        targets = use.config.targets()
        where = f"{use.location}.target"
        if name in ("knockout", "drug"):
            node = targets[0] if targets else ""
            if node in off:
                problems.append((where, f"'{node}' is already {'knocked out' if off[node] == 'knockout' else 'blocked by a drug'} "
                                        f"at this point (give the earlier action an until: to undo it first)"))
        elif name == "signal":
            if targets and targets[0] in off:
                problems.append((where, f"the signal starts at '{targets[0]}', which is "
                                        f"{'knocked out' if off[targets[0]] == 'knockout' else 'blocked by a drug'} at this point"))
        elif name == "inhibit":
            if targets and targets[0] in off:
                problems.append((where, f"inhibitor '{targets[0]}' is off at this point (knocked out or blocked by a drug)"))
        until = use.config.until
        end = beats.index(until) if until in beats else len(beats) + 1
        for t in targets[:1]:
            active.append((name, t, b, end))
    return problems
