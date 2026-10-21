"""The ``hide`` beat action (DESIGN.md §89.10): an object of a ``stage``'s iso place goes away at
``at`` of the beat (it fades out; ``reveal`` brings it back). Written against ``vidgen.api`` only,
like project actions. Like ``switch_on`` it draws nothing itself (``animates = False``): the
stage fades the object's picture by its clock."""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *

from .acting import is_part_target


@action("hide")
class Hide(Action):
    """The target object of an iso place goes away at `at` of the beat (`- hide: rock`): it fades
    out over `run_time`, and nobody walks into it any more (a bridge gone cannot be crossed). The
    `reveal` action brings it back, and brings an object that starts `shown: false`. Stage scenes
    on an iso place only."""

    run_time = 0.8
    needs_visible = False
    animates = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """Targets are objects of an iso place (or its doors)."""
        if getattr(params, "iso", None) is None:
            return [("action", "hide is for the objects of an iso place (a stage with iso:); elsewhere a character exits")]
        objects = params.iso.changeable_names()
        problems: list[tuple[str, str]] = []
        for pattern in self.config.targets():
            for name in [n for n in scene_cls.target_names(params) if fnmatchcase(n, pattern) and not is_part_target(n)]:
                if name not in objects:
                    problems.append(("target", f"'{name}' is not an object of the place; hide acts on its objects "
                                     f"({', '.join(objects) or 'none'}); a character exits"))
        return problems

    def cue(self, scene: NarratedScene, time: float) -> None:
        """The targets fade out from scene ``time``."""
        scene.iso_hide(self.config.targets(), time, float(self.config.run_time or self.run_time))
