"""The beat actions of molecular processes (DESIGN.md §95.10): ``set_state`` (a molecule morphs
to another state: a channel opens, a carrier turns, a pump is phosphorylated), ``transport`` (a
channel, carrier, pump or aquaporin moves its solutes, cycle by cycle), ``diffuse`` (simple
diffusion down a concentration gradient), ``osmosis`` (water towards the side with more
solute) and ``action_potential`` (channels open and close with a live voltage readout and
trace). Timed like any action (``at: "@word"``). Written against ``vidgen.api``; the scene
plans with the rules of ``vidgen.cellworld.transport`` and draws."""

from typing import Any, Literal

from vidgen.api import *


def _one_target(action: Action, name: str) -> list[tuple[str, str]]:
    targets = action.config.targets()
    if len(targets) != 1 or any(ch in targets[0] for ch in "*?["):
        return [("target", f"{name} acts on one target (one id, no wildcards)")]
    return []


def _process_problem(action: Action, scene_cls: type[NarratedScene], params: Any, name: str) -> list[tuple[str, str]]:
    """The checks every process action shares: a scene that has them, one target, then the
    scene's own check of this use (``process_problem``)."""
    if not getattr(scene_cls, "process_actions", ()) or name not in scene_cls.process_actions:  # type: ignore[attr-defined]
        return [("action", f"{name} is an action of molecule scenes (a cell scene has motor_walk, endocytosis and exocytosis)")]
    problems = _one_target(action, name)
    if problems:
        return problems
    problem = scene_cls.process_problem(params, name, action.config.targets()[0], action.options)  # type: ignore[attr-defined]
    return [("target", problem)] if problem else []


@action("set_state")
class SetState(Action):
    """Change a molecule's state with a smooth morph: ``{set_state: kchan, state: open}`` — an
    ion channel closed / open / inactivated, a carrier outward / occluded / inward, the Na⁺/K⁺
    pump e1 / e1p / e2p / e2, a GPCR or G protein inactive / active, an RTK monomer / dimer, an
    ABC transporter inward / outward. ``until: <beat>`` returns it to the state before."""

    class Options(ActionOptions):
        state: str
        """The state to take (the molecule kind's states; checked)."""

    run_time = 1.2
    reversible = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _process_problem(self, scene_cls, params, "set_state")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Morph the molecule to the new state."""
        self.before = scene.molecule_state(targets[0].name)  # type: ignore[attr-defined]
        return scene.morph_molecule(targets[0].name, self.options.state)  # type: ignore[attr-defined]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to the state before."""
        before = getattr(self, "before", None)
        return [] if before is None else scene.morph_molecule(targets[0].name, before)  # type: ignore[attr-defined]


@action("transport")
class Transport(Action):
    """A membrane protein moves its solutes: an open ion channel passes ions one after another
    down their electrochemical gradient (``count``; only its own ion: ``ion: Na+`` on a K⁺
    channel is refused); a carrier runs its alternating-access cycle (``cycles``: one solute per
    cycle for a uniporter, its ratio for a symporter or an exchanger such as NCX: 3 Na⁺ in, 1
    Ca²⁺ out); the Na⁺/K⁺ pump its Post–Albers cycle (3 Na⁺ out, 2 K⁺ in, ATP → ADP + Pᵢ, the
    phosphorylated E1P and E2P shown); an H⁺ pump, an ABC transporter (2 ATP per substrate) or
    an aquaporin (water in single file) theirs. Each step is captioned."""

    class Options(ActionOptions):
        cycles: int = Field(1, ge=1, le=4)
        """Carriers and pumps: how many transport cycles."""
        count: int = Field(4, ge=1, le=12)
        """Channels and aquaporins: how many ions or water molecules pass."""
        ion: str | None = None
        """Channels: the ion that passes (default: the channel's own; another is refused with the reason)."""
        direction: Literal["in", "out"] | None = None
        """Channels and aquaporins: which way (in: into the cytosol); default and checked: down the gradient."""
        notes: bool = True
        """Caption each step (E1P: ATP → ADP…)."""

    run_time = 5.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _process_problem(self, scene_cls, params, "transport")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Plan the transport on the molecule as it is now and play it."""
        return scene.run_transport(targets[0].name, self.options, self.config.describe())  # type: ignore[attr-defined]


@action("diffuse")
class Diffuse(Action):
    """Simple diffusion of a solute of the scene (``diffuse: oxygen``): every particle wanders at
    random, and more cross from the crowded side than back, so the net flux runs down the
    concentration gradient; across a membrane only what the bilayer lets through (O₂, CO₂,
    slowly water) — ions and glucose are refused (they need a channel or a carrier: transport).
    The concentrations shown change to match."""

    class Options(ActionOptions):
        share: float = Field(0.6, gt=0.0, le=1.0)
        """How far towards equal concentrations it gets (1: all the way)."""

    run_time = 4.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _process_problem(self, scene_cls, params, "diffuse")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Plan and play the random walks."""
        return scene.run_diffusion(targets[0].name, self.options.share, self.config.describe())  # type: ignore[attr-defined]


@action("osmosis")
class Osmosis(Action):
    """Water crosses the membrane towards the side with more solute (the higher osmolarity),
    through aquaporins when the membrane has them (else slowly through the bilayer): ``osmosis:
    membrane``. Equal osmolarities on both sides (isotonic) are refused: no net flow."""

    class Options(ActionOptions):
        count: int = Field(6, ge=1, le=20)
        """How many water molecules cross (net)."""

    run_time = 4.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _process_problem(self, scene_cls, params, "osmosis")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Plan and play the water flow."""
        return scene.run_osmosis(self.options.count, self.config.describe())  # type: ignore[attr-defined]


@action("action_potential")
class ActionPotential(Action):
    """An action potential at the membrane (``action_potential: membrane``): a stimulus brings it
    to threshold (−55 mV), voltage-gated Na⁺ channels open (Na⁺ in, up to +35 mV), inactivate as
    the K⁺ channels open (K⁺ out, repolarisation), the undershoot (−80 mV) while the K⁺ channels
    stay open and the Na⁺ channels recover, back to rest (−70 mV) — with a live readout of the
    membrane potential, the membrane's charges and (``plot``) its trace in an inset plot. The
    scene needs voltage-gated Na⁺ and K⁺ channels in a plasma membrane, closed at the start."""

    class Options(ActionOptions):
        plot: bool = True
        """Draw the voltage trace in an inset plot (mV against ms) as it happens."""
        ions: int = Field(3, ge=1, le=8)
        """Ions through each channel."""
        notes: bool = True
        """Caption each phase."""

    run_time = 7.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _process_problem(self, scene_cls, params, "action_potential")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Plan and play the action potential."""
        return scene.run_action_potential(self.options, self.config.describe())  # type: ignore[attr-defined]
