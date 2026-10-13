"""The ``knock`` beat action (DESIGN.md §69.62): someone knocks on a ``stage``'s door at ``at`` of the
beat; written against ``vidgen.api`` only, like project actions. It draws nothing (``animates =
False``, like ``switch_on``): nobody needs to stand at the door (a knock from outside); the stage
plays the ``knock`` sound with foley."""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *

from .acting import is_part_target


@action("knock")
class Knock(Action):
    """Someone knocks on the target door at `at` of the beat (`- knock: door`): three raps on the
    wood (foley; a knock from outside, nobody needs to stand there). A room's door or a `door`
    prop; stage scenes only."""

    run_time = 0.75
    needs_visible = False
    animates = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """Targets are doors (a room's or a ``door`` prop)."""
        if not hasattr(scene_cls, "knock_on"):
            return [("action", "knock is for the doors of a stage")]
        kinds = dict(zip(params.prop_names(), (p.prop for p in params.stage_props())))
        problems: list[tuple[str, str]] = []
        for pattern in self.config.targets():
            for name in [n for n in scene_cls.target_names(params) if fnmatchcase(n, pattern) and not is_part_target(n)]:
                if kinds.get(name) != "door":
                    doors = ", ".join(n for n, kind in kinds.items() if kind == "door") or "none"
                    problems.append(("target", f"'{name}' is not a door; knock acts on doors (the stage's doors: {doors})"))
        return problems

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Knock on the targets at scene ``time``."""
        scene.knock_on(self.config.targets(), time)
