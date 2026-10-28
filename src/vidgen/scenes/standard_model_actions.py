"""The beat actions of the ``standard_model`` scene type (Phase Y, Step 237; DESIGN §99.4):
``antiparticles`` turns quark and lepton cells into their antiparticles (charge reversed, the
symbol barred, the name changed; mass and spin stay) and ``couplings`` shows which particles a
boson couples to. Written against ``vidgen.api``; the scene draws
(``scenes/standard_model.py``)."""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *


def _problems(action: str, scene_cls: type[NarratedScene]) -> list[tuple[str, str]]:
    if not getattr(scene_cls, "standard_model_actions", False):
        return [("action", f"{action} is an action of standard_model scenes (type: standard_model)")]
    return []


@action("antiparticles")
class Antiparticles(Action):
    """Turn quark and lepton cells into their antiparticles (``- action: antiparticles`` for
    all of them, or a target: ``antiparticles: "group:quarks"``, ``"particle:e"``): the charge
    is reversed, the symbol gets its bar (ū, e⁺, ν̄ₑ) and the name changes; mass and spin stay.
    The bosons are their own antiparticles (W⁺ and W⁻ share a cell). ``until: <beat>`` turns
    them back."""

    run_time = 1.0
    reversible = True
    needs_target = False
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _problems("antiparticles", scene_cls)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        self.cells = scene.fermion_cells(targets)  # type: ignore[attr-defined]
        self.before = {t for t in self.cells if t in scene._anti}  # type: ignore[attr-defined]
        return scene.flip(self.cells, anti=True)  # type: ignore[attr-defined]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.flip([t for t in self.cells if t not in self.before], anti=False)  # type: ignore[attr-defined]


@action("couplings")
class Couplings(Action):
    """Show which particles a boson couples to (``couplings: "particle:photon"``): an outline in
    ``color`` around the quarks and leptons it acts on, rings around the bosons it meets (dashed),
    the other cells dimmed (``dim``) and the reason in words (``note``: "γ couples to electric
    charge: quarks, charged leptons and the W"). Gluon: colour (quarks, gluons); photon: charge;
    Z and W: every quark and lepton (the W changes flavour); Higgs: mass. Undone when the next
    beat starts (or at ``until``)."""

    class Options(ActionOptions):
        color: ThemeColor = "highlight"
        """Colour of the outlines."""
        dim: bool = True
        """Dim the cells the boson does not couple to."""
        note: bool = True
        """Say why, in words, under the chart (wide: beside it)."""

    run_time = 1.0
    reversible = True
    until_next_beat = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _problems("couplings", scene_cls)
        if problems:
            return problems
        bosons = [f"particle:{c.target}" for c in particle_physics.CELLS if not c.is_fermion]
        names = [n for n in scene_cls.target_names(params) if n.startswith("particle:")]
        for pattern in self.config.targets():
            matched = [n for n in names if fnmatchcase(n, pattern)]
            resolved = {particle_physics.cell(n.partition(":")[2]).target for n in matched}
            if not matched or not all(f"particle:{t}" in bosons for t in resolved):
                return [("target", f"couplings acts on a boson: {', '.join(bosons)}; '{pattern}' is not one")]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        bosons = []
        for t in targets:
            for name in t.names:
                label = name.partition(":")[2]
                if name.startswith("particle:") and label in particle_physics.COUPLINGS and label not in bosons:
                    bosons.append(label)
        o = self.options
        anims, self.state = scene.couple(bosons, scene.theme.color(o.color), o.dim, o.note)  # type: ignore[attr-defined]
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.uncouple(self.state)  # type: ignore[attr-defined]
