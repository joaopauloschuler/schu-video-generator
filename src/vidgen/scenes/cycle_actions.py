"""The beat actions of the ``cell_cycle`` and ``metabolism`` scenes (DESIGN.md §95.13):
``advance`` (the cell moves round the cycle or through the stages of a division; a pathway's
token moves through its steps; electrons run along a chain, pumping protons, or the gradient
drives ATP synthase) and ``checkpoint`` (a checkpoint passes or arrests the cell, with its
regulators). Timed like any action (``at: "@word"``); ``vidgen validate`` replays them in beat
and ``at`` order. Written against ``vidgen.api``; the scenes draw."""

from typing import Any, Literal

from vidgen.api import *

cy = cell_cycle_model
dv = cell_division
en = cell_energy

CYCLE_ACTIONS = ("advance", "checkpoint")


def _main_target(params: Any) -> str:
    if hasattr(params, "process"):
        return en.process_key(params.process)
    return "cycle" if params.mode == "cycle" else "cell"


def _beat_order(spec: Any, uses: list[Any]) -> list[int]:
    beats = [b.id for b in spec.beats]
    return sorted(range(len(uses)), key=lambda i: (beats.index(uses[i].beat) if uses[i].beat in beats else 0, uses[i].config.fraction, i))


@action("advance")
class Advance(Action):
    """Move the process on. ``cell_cycle`` with ``mode: cycle`` (``advance: cycle``): the cell
    goes round the cycle to a point (``to: s``, ``g2_m``, ``metaphase``, ``g0``…; ``into: 0.5``
    half-way through that phase), the marker moving on the ring and the plot together.
    ``mode: mitosis`` / ``meiosis`` (``advance: cell``): the division runs to the end of a stage
    (``to: metaphase``, ``anaphase_i``…), keyframe by keyframe; ``expect: {chromosomes: 2,
    chromatids: 4}`` states the counts per cell there and is checked. ``metabolism``
    (``advance: glycolysis``, ``tca``…): the token runs to a metabolite or enzyme (``to:
    pyruvate``), cofactors appear and the tallies count; on a chain (``advance: etc``) electrons
    run to a component (``to: complex_iv``; ``from: fadh2``) pumping protons across, and ``to:
    atp_synthase`` lets the gradient drive ATP synthesis. Its length follows what it shows
    (``run_time`` overrides it)."""

    class Options(ActionOptions):
        to: str | None = None
        """Where to: a point or phase of the cycle, a stage of the division, a metabolite or enzyme, a chain's component (default: the end)."""
        into: float = Field(0.0, ge=0.0, lt=1.0)
        """cycle: how far into that phase or stage (0 its start)."""
        expect: dict[str, int | str] = Field(default_factory=dict)
        """mitosis / meiosis: the counts per cell after that stage, checked (chromosomes, chromatids, cells, ploidy n / 2n, dna 1C / 2C / 4C)."""
        source: str | None = Field(None, alias="from")
        """etc: where the electrons come from (nadh, default; fadh2 enters at complex II); light_reactions: water."""

    run_time = 3.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        cyc = getattr(scene_cls, "cycle_actions", False)
        met = getattr(scene_cls, "metabolism_actions", False)
        if not (cyc or met):
            return [("action", "advance is an action of cell_cycle and metabolism scenes")]
        targets = self.config.targets()
        main = _main_target(params)
        if targets != [main]:
            return [("target", f"advance acts on '{main}' in this scene (advance: {main})")]
        o = self.options
        if cyc:
            if params.mode == "cycle":
                if o.expect or o.source:
                    return [("expect" if o.expect else "from", "expect and from belong to divisions and chains")]
                if o.to is not None:
                    try:
                        cy.point_key(o.to)
                    except VidgenError as error:
                        return [("to", str(error))]
                return []
            if o.into or o.source:
                return [("into" if o.into else "from", "into belongs to mode: cycle; from to the chains of metabolism")]
            try:
                stage = dv.stage_key(params.mode, o.to or dv.stages_of(params.mode)[-1])
            except VidgenError as error:
                return [("to", str(error))]
            if o.expect:
                problem = dv.expect_problem(params.mode, stage, params.chromosomes, o.expect, params.nd())
                if problem:
                    return [("expect", problem)]
            return []
        if o.into or o.expect:
            return [("into" if o.into else "expect", "into belongs to the cell cycle, expect to divisions")]
        setting = params.setting()
        if setting.process in ("etc", "light_reactions"):
            problem = en.chain_advance_problem(setting, en.FlowState(gradient=1), o.to, o.source)
            return [("to", problem)] if problem else []
        if o.source is not None:
            return [("from", "from belongs to the chains (etc, light_reactions)")]
        if o.to is not None:
            try:
                en.step_index(params.pathway(), o.to)
            except VidgenError as error:
                return [("to", str(error))]
        return []

    def _to(self, scene: NarratedScene) -> str | None:
        o = self.options
        if getattr(scene, "metabolism_actions", False) or o.to is not None:
            return o.to
        mode = scene.params.mode  # type: ignore[attr-defined]
        return "end" if mode == "cycle" else dv.stages_of(mode)[-1]

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        o = self.options
        extra = o.source if getattr(scene, "metabolism_actions", False) else o.into
        return scene.advance_seconds(self._to(scene), extra)  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        o = self.options
        extra = o.source if getattr(scene, "metabolism_actions", False) else o.into
        return scene.run_advance(self._to(scene), extra)  # type: ignore[attr-defined]


@action("checkpoint")
class Checkpoint(Action):
    """A checkpoint of the cell cycle acts (``checkpoint: g1_s``, ``g2_m`` or ``spindle``; on a
    ``cell_cycle`` with ``mode: cycle``): a panel shows what it checks and its regulators lit
    one after another — ``outcome: pass`` (default) the way through (cyclin D–CDK4/6 ⊣ Rb ⊣ E2F
    → cyclin E–CDK2; Cdc25 → cyclin B–CDK1; APC/C–Cdc20 ⊣ securin ⊣ separase ⊣ cohesin) or
    ``outcome: arrest`` what holds the cell (``cause: dna_damage``: p53 → p21 ⊣ CDK2, or Chk1 ⊣
    Cdc25; ``unattached_kinetochore``: the MCC holds APC/C–Cdc20; ``no_mitogens``). While an
    arrest lasts (until its ``until`` beat) ``advance`` cannot take the cell past it."""

    class Options(ActionOptions):
        outcome: Literal["pass", "arrest"] = "pass"
        """pass: the cell may go on; arrest: it is held there."""
        cause: str | None = None
        """arrest: why (g1_s: dna_damage or no_mitogens; g2_m: dna_damage; spindle: unattached_kinetochore)."""

    run_time = 2.6
    reversible = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "cycle_actions", False) or params.mode != "cycle":
            return [("action", "checkpoint is an action of cell_cycle scenes with mode: cycle")]
        targets = self.config.targets()
        if len(targets) != 1:
            return [("target", "checkpoint names one checkpoint (g1_s, g2_m, spindle)")]
        name = targets[0].split(":", 1)[-1]
        problem = cy.checkpoint_problem(params.geometry(), cy.CycleState(), name, self.options.outcome, self.options.cause)
        if problem is None and self.options.cause is not None and self.options.outcome == "pass":
            problem = "cause belongs to outcome: arrest"
        return [("target", problem)] if problem else []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        name = self.config.targets()[0].split(":", 1)[-1]
        anims, self._undo = scene.run_checkpoint(name, self.options.outcome, self.options.cause)  # type: ignore[attr-defined]
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        undo = getattr(self, "_undo", None)
        self._undo = None
        return undo() if undo is not None else []


def cycle_sequence_problems(spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
    """``advance`` and ``checkpoint`` in beat and ``at`` order on a ``cell_cycle`` scene."""
    beats = [b.id for b in spec.beats]
    problems: list[tuple[str, str]] = []
    if params.mode == "cycle":
        geo = params.geometry()
        state = cy.start_state(geo, params.start or "g1")
        arrests: list[tuple[str, str, int]] = []      # (checkpoint, why, until beat index)
        for i in _beat_order(spec, uses):
            use = uses[i]
            name = use.kind.name
            b = beats.index(use.beat) if use.beat in beats else 0
            state.arrests = {k: why for k, why, end in arrests if end > b}
            if name == "advance":
                o = use.action.options
                to = o.to or "end"
                problem = cy.advance_problem(geo, state, to, o.into)
                if problem:
                    problems.append((f"{use.location}.to", problem))
                    continue
                state = cy.advance(geo, state, to, o.into)
            elif name == "checkpoint":
                o = use.action.options
                ck = use.config.targets()[0].split(":", 1)[-1]
                problem = cy.checkpoint_problem(geo, state, ck, o.outcome, o.cause)
                if problem:
                    problems.append((f"{use.location}.target", problem))
                    continue
                if o.outcome == "arrest":
                    until = use.config.until
                    end = beats.index(until) if until in beats else len(beats) + 1
                    arrests.append((cy.checkpoint_key(ck), f"arrested in beat {b + 1}", end))
        return problems
    stages = dv.stages_of(params.mode)
    at = stages.index(params.start_key())
    for i in _beat_order(spec, uses):
        use = uses[i]
        if use.kind.name != "advance":
            continue
        o = use.action.options
        stage = dv.stage_key(params.mode, o.to or stages[-1])
        k = stages.index(stage)
        if k <= at:
            problems.append((f"{use.location}.to", f"the division is at {stages[at]} already; it runs one way (advance to a stage after it)"))
            continue
        at = k
    return problems
