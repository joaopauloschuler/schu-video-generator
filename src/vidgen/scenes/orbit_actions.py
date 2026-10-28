"""The beat actions of the ``orbit`` scene type (Phase X, Step 230, DESIGN §98.4): ``sweep``
starts a body's equal-time sectors on a word (``sweep: "sectors:Comet"``, ``at: "@equal"``) and
``launch`` fires Newton's cannon (``launch: "shot:3"``). Both happen at the moment they fall due
on the scene's clock (the bodies keep moving; nothing pauses). ``reveal`` shows the geometry
(``foci:Comet``, ``axes:Comet``, ``periapsis:Comet``...) or the velocity arrows
(``velocity:Comet``), ``highlight`` marks them. Step 231 adds the clock actions ``burn`` (a burn
on its word), ``flyby`` (the closest approach on its word), ``pause`` and ``coast``: the scene
plans its clock through their words when the motion starts. Step 232 adds ``corotate`` and
``inertial``: the view of a three-body pair turned on a word. Written against ``vidgen.api``; the
scene draws (``scenes/orbit.py``, ``scenes/orbit_overlays.py``, ``scenes/orbit_manoeuvres.py``)."""

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


@action("burn")
class BurnAction(_OrbitCue):
    """Time a burn to a word (``burn: "burn:2"``, ``at: "@fire"``): the scene's clock runs so that
    the burn happens on that word — one speed-up before it and another after, both shown in the
    panel (the burn's simulated time stays where the orbit puts it: an apoapsis, a launch
    window). Burns on words keep their order."""

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _orbit_problems("burn", "burn:", "a body with burns: or a transfer:", scene_cls, params, self.config.targets())

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Nothing at the cue: the scene planned its clock through this word when the motion started."""


class _ClockCue(_OrbitCue):
    """An orbit action on the scene's clock, without a target."""

    needs_target = False
    scene_targets = False
    #: What the scene must have for it (an attribute of the params), and the hint when it does not.
    needs: tuple[str, str] | None = None

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        name = type(self).__name__.removesuffix("Action").lower()
        if not getattr(scene_cls, "orbit_actions", False):
            return [("action", f"{name} is an action of orbit scenes (type: orbit)")]
        if self.config.targets():
            return [("target", f"{name} takes no target (write `- action: {name}` with at:)")]
        if self.needs is not None and getattr(params, self.needs[0], None) is None:
            return [("action", f"{name} needs {self.needs[1]}")]
        return []

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Nothing at the cue: the scene planned its clock through this word when the motion started."""


@action("flyby")
class FlybyAction(_ClockCue):
    """Time a flyby's closest approach to a word (``- action: flyby``, ``at: "@closest"``): the
    clock runs so that the probe passes periapsis on that word."""

    needs = ("flyby", "a flyby: ({v_inf: '5.6 km/s', altitude: '200000 km'})")


@action("pause")
class PauseAction(_ClockCue):
    """Hold the scene's clock still from a word (``- action: pause``, ``at: "@look"``) until a
    ``coast`` (or the end of the beat): the bodies stop, the panel says "clock paused", and the
    motion before and after keeps its own speed-up."""


@action("coast")
class CoastAction(_ClockCue):
    """Run the clock again from a word after a ``pause`` (``- action: coast``, ``at: "@on"``)."""


class _FrameCue(_ClockCue):
    """Switch the view of a three-body pair on a word (Step 232)."""

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        out = super().scene_problems(scene_cls, params)
        if out:
            return out
        name = type(self).__name__.removesuffix("Action").lower()
        try:
            many = params.model().many
        except VidgenError:
            return []
        if many is None or many.restricted is None:
            return [("action", f"{name} turns the view of a three-body pair; it needs system: earth_moon, sun_earth, sun_jupiter or {{primary, secondary}}")]
        return []


@action("corotate")
class CorotateAction(_FrameCue):
    """Turn the view into the frame rotating with a three-body pair (``- action: corotate``,
    ``at: "@rotating"``, ``run_time: 2``): over the run time the view turns until both primaries
    stand still, the Lagrange points with them; trails redraw in that frame (a Trojan's tadpole).
    The panel says which frame is shown."""


@action("inertial")
class InertialAction(_FrameCue):
    """Turn the view back to the inertial frame (the fixed stars): the pair goes round again."""


@action("launch")
class Launch(_OrbitCue):
    """Fire shots of Newton's cannon on a word (``launch: "shot:2"``, ``launch: "shot:*"``):
    each flies from that moment (without a ``launch`` every shot flies from the start)."""

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _orbit_problems("launch", "shot:", "a cannonball: (cannonball: {speeds: [0.8, 1, 1.2]})", scene_cls, params, self.config.targets())

    def cue(self, scene: NarratedScene, time: float) -> None:
        shots = sorted({int(n.partition(":")[2]) - 1 for n in self._names(scene) if n.startswith("shot:")})
        scene.launch(shots, time)  # type: ignore[attr-defined]
