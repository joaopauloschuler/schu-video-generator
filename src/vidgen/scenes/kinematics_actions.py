"""The beat action of the ``kinematics`` scene type (Phase Y, Step 239; DESIGN §99.8): ``boost``
moves a frame continuously — the arrows of the decay products (or of the particles) change as
the frame speeds up, the sum grows from zero, β and γ count up, and the frame's numbers morph
into the new frame's. Written against ``vidgen.api``; the scene draws
(``scenes/kinematics.py``)."""

import math
from typing import Any

from vidgen.api import *


@action("boost")
class BoostAction(Action):
    """Boost the picture's last frame (``- action: boost``): from the rest frame to the lab (or
    back), or to any speed (``to: 0.9`` for β = 0.9). The arrows change continuously — the
    products of a decay swing forward and close up as the parent speeds up — while the
    invariant mass stays the same. ``until:`` boosts back."""

    class Options(ActionOptions):
        to: str | float | None = None
        """lab, rest or a speed β (0 ≤ β < 1); default: the lab from the rest frame, else the rest frame."""

    run_time = 2.5
    needs_target = False
    reversible = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "kinematics_actions", False):
            return [("action", "boost is an action of kinematics scenes (type: kinematics)")]
        to = self.options.to
        if isinstance(to, str) and to not in ("lab", "rest"):
            try:
                to = float(to)
            except ValueError:
                return [("to", f"to: '{to}' is not lab, rest or a speed β (0.9)")]
        if isinstance(to, (int, float)) and not 0 <= float(to) < 1:
            return [("to", f"to: β = {to} is not in [0, 1): nothing massive moves at or faster than light")]
        if to == "lab" and params.decay and all(getattr(params, k) is None for k in ("momentum", "energy", "kinetic", "beta", "gamma")):
            return [("to", "to: lab needs the decaying particle's momentum (momentum: 10 GeV/c), energy, kinetic, beta or gamma")]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        to = self.options.to
        anims, self.before = scene.boost(float(to) if isinstance(to, str) and to not in ("lab", "rest") else to)  # type: ignore[attr-defined]
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.boost(math.tanh(self.before))[0]  # type: ignore[attr-defined]
