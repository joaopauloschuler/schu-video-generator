"""The ``shot`` beat action (DESIGN.md §69.29): the camera framing of a ``stage``'s beat, which the
``shot:`` beat key writes. Written against ``vidgen.api`` only, like project actions.

A shot cuts the camera to a framing of characters (``wide``, ``two_shot``, ``medium``,
``over_shoulder``, ``closeup``) computed where they stand when it starts
(:func:`frame_shot`); ``move: true`` eases there. It holds for the beat; the action runner adds a
shot without a ``kind`` at the start of the next beat that has no shot of its own, which goes
back to the view before the shots (and to following what the camera followed then).
"""

from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .acting import _Acting
from .actions import MoveCamera, _MoveThenFollow, camera_view


def _set_view(scene: NarratedScene, width: float, center: np.ndarray) -> None:
    """Cut: the camera shows ``width`` units around ``center`` from the next frame on."""
    frame = scene.camera.frame
    frame.scale(width / frame.width).move_to(center)


@action("shot")
class ShotAction(_Acting):
    """Frame characters of a stage (the ``shot:`` beat key): ``kind`` wide, two_shot, medium,
    over_shoulder or closeup of the targets (see :data:`~vidgen.config.SHOT_NAMES` for how many),
    as a cut or, with ``move``, an eased move; held until the next beat."""

    class Options(ActionOptions):
        kind: Literal["wide", "two_shot", "medium", "over_shoulder", "closeup"] | None = None
        """The framing; none: back to the view before the shots (the runner adds that after a shot's beat)."""
        move: bool = False
        """Ease to the framing instead of cutting."""

    run_time = SHOT_MOVE_SECONDS
    needs_target = False
    needs_visible = False
    moves_camera = True
    alters_targets = False

    def problems(self) -> list[tuple[str, str]]:
        kind, count = self.options.kind, len(self.config.targets())
        if kind is None:
            return [("target", "a shot back to the view before takes no target")] if count else []
        fewest, most = SHOT_NAMES[kind]
        if not fewest <= count <= most:
            wanted = "no character" if most == 0 else f"{fewest} to {most} characters" if fewest != most else f"{most} character"
            return [("target", f"a {kind} shot names {wanted}, got {count}")]
        return []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "shot_framing"):
            return [("kind", f"shots are for stage scenes; a {scene_cls.__name__} scene moves its camera with zoom or pan")]
        return self._target_characters(scene_cls, params)[1]

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return None if self.options.move else 0.0

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Cut (or move) to the framing; without a ``kind``, back to the view before the shots."""
        if self.options.kind is None:
            return self._back(scene)
        names = [t.name for t in targets if isinstance(t.mobject, Character)]
        view, shot = scene.shot_framing(self.options.kind, names)
        if scene.shot_home is None:
            scene.shot_home = (camera_view(scene), scene.camera_following)
        scene.follow_with_camera(None)
        scene.camera_shot = shot.layout()
        width = scene.frame_width / view.scale
        center = np.array([view.center_x, view.center_y, 0.0])
        if self.options.move:
            return [MoveCamera(scene, width, center)]
        _set_view(scene, width, center)
        return []

    def _back(self, scene: NarratedScene) -> list[Animation]:
        home, scene.shot_home, scene.camera_shot = scene.shot_home, None, None
        if home is None:
            return []
        (width, center), followed = home
        if self.options.move:
            return [_MoveThenFollow(scene, width, center, followed) if followed is not None else MoveCamera(scene, width, center)]
        _set_view(scene, width, center)
        if followed is not None:
            scene.follow_with_camera(followed)
        return []
