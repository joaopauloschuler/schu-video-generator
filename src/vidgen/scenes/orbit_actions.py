"""The beat actions of the ``orbit`` scene type (Phase X, Step 230, DESIGN §98.4): ``sweep``
starts a body's equal-time sectors on a word (``sweep: "sectors:Comet"``, ``at: "@equal"``) and
``launch`` fires Newton's cannon (``launch: "shot:3"``). Both happen at the moment they fall due
on the scene's clock (the bodies keep moving; nothing pauses). ``reveal`` shows the geometry
(``foci:Comet``, ``axes:Comet``, ``periapsis:Comet``...) or the velocity arrows
(``velocity:Comet``), ``highlight`` marks them. Written against ``vidgen.api``; the scene draws
(``scenes/orbit.py``, ``scenes/orbit_overlays.py``)."""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *


def _orbit_problems(action: str, prefix: str, what: str, scene_cls: type[NarratedScene], params: Any, targets: list[str]) -> list[tuple[str, str]]:
    if not getattr(scene_cls, "orbit_actions", False):
        return [("action", f"{action} is an action of orbit scenes (type: orbit)")]
    names = [n for n in scene_cls.target_names(params) if n.startswith(prefix)]
    if not names:
        return [("action", f"{action} needs {what}")]
    for t in targets:
        if not any(fnmatchcase(n, t) for n in names):
            return [("target", f"{action} acts on {', '.join(names)}; '{t}' is not one" + did_you_mean(t, names))]
    return []


class _OrbitCue(Action):
    """An orbit action that happens at its time on the scene's clock (no animation of its own)."""

    animates = False
    needs_visible = False

    def _names(self, scene: NarratedScene) -> list[str]:
        return [n for pattern in self.config.targets() for t in scene.find_targets(pattern) for n in t.names]


@action("sweep")
class Sweep(_OrbitCue):
    """Start sweeping a body's equal-time sectors on a word (``sweep: "sectors:Comet"``): from
    that moment each sector fills as the body sweeps it, Δt = period / count each, and its area
    is listed (without a ``sweep`` they start with the motion)."""

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _orbit_problems("sweep", "sectors:", "a body with sectors: (e.g. sectors: 8)", scene_cls, params, self.config.targets())

    def cue(self, scene: NarratedScene, time: float) -> None:
        names = [n.partition(":")[2] for n in self._names(scene) if n.startswith("sectors:")]
        scene.start_sweep(names, time)  # type: ignore[attr-defined]


@action("launch")
class Launch(_OrbitCue):
    """Fire shots of Newton's cannon on a word (``launch: "shot:2"``, ``launch: "shot:*"``):
    each flies from that moment (without a ``launch`` every shot flies from the start)."""

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _orbit_problems("launch", "shot:", "a cannonball: (cannonball: {speeds: [0.8, 1, 1.2]})", scene_cls, params, self.config.targets())

    def cue(self, scene: NarratedScene, time: float) -> None:
        shots = sorted({int(n.partition(":")[2]) - 1 for n in self._names(scene) if n.startswith("shot:")})
        scene.launch(shots, time)  # type: ignore[attr-defined]
