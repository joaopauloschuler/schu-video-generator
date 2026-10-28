"""The beat action of the ``detector`` scene type (Phase Y, Step 240; DESIGN §99.10):
``switch_view`` turns the transverse (x–y) view into the longitudinal (r–z) one or back — the
rings flatten into the barrel and endcaps, every track, tower and hit morphs into its
counterpart; the missing transverse momentum shows only in x–y. ``highlight``, ``dim`` and
``reveal`` work on the scene's targets (``particle:mu+``, ``missing_pt``, ``legend``) as on any.
Written against ``vidgen.api``; the scene draws (``scenes/detector.py``)."""

from typing import Any, Literal

from vidgen.api import *


@action("switch_view")
class SwitchView(Action):
    """Switch a detector display between its views (``- action: switch_view``: the other one;
    ``to: rz`` or ``to: xy``): the transverse view across the beam (x–y, the field out of the
    screen) and the longitudinal view along it (r–z, the beam horizontal). Each part morphs into
    its counterpart. ``until:`` switches back."""

    class Options(ActionOptions):
        to: Literal["xy", "rz"] | None = None
        """xy (across the beam) or rz (along it); default: the other view."""

    run_time = 1.6
    needs_target = False
    reversible = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "detector_actions", False):
            return [("action", "switch_view is an action of detector scenes (type: detector)")]
        return []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        self.before = scene.current_view()  # type: ignore[attr-defined]
        return scene.switch_view(self.options.to)  # type: ignore[attr-defined]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.switch_view(self.before)  # type: ignore[attr-defined]
