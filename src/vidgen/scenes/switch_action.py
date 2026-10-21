"""The ``switch_on`` / ``switch_off`` beat actions (DESIGN.md §69.54): a ``stage``'s television or
lamp goes on or off at ``at`` of the beat; written against ``vidgen.api`` only, like project
actions. They draw nothing themselves (``animates = False``, like ``light``): the runner cues them
when their beat starts, and the stage shows the picture or the glow from then on (with a click,
foley)."""

from fnmatch import fnmatchcase
from typing import Any, ClassVar

from vidgen.api import *

from .acting import is_part_target


class _Switch(Action):
    """``switch_on`` / ``switch_off``: the target props (by name) go on or off at once."""

    #: Whether it switches on.
    on: ClassVar[bool]
    run_time = 0.1
    needs_visible = False
    animates = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """Targets are props that switch on (a tv or a lamp)."""
        action = self.config.action
        if not hasattr(scene_cls, "switch_props"):
            return [("action", f"{action} is for the props of a stage")]
        kinds = dict(zip(params.prop_names(), (p.prop for p in params.stage_props())))
        able = ", ".join(SWITCHED_PROPS)
        objects = params.iso.object_kinds() if getattr(params, "iso", None) is not None else {}   # an iso place's (§89.10)
        problems: list[tuple[str, str]] = []
        for pattern in self.config.targets():
            for name in [n for n in scene_cls.target_names(params) if fnmatchcase(n, pattern) and not is_part_target(n)]:
                if name in objects:
                    if objects[name] not in SWITCHED_KINDS:
                        problems.append(("target", f"'{name}' (a {objects[name]}) cannot be switched on or off; on an iso place a lamp "
                                         "and a house (its windows) can"))
                elif name not in kinds:
                    problems.append(("target", f"'{name}' is not a prop; {action} acts on props (- {action}: <prop>)"))
                elif kinds[name] not in SWITCHED_PROPS:
                    problems.append(("target", f"'{name}' cannot be switched on or off (props that can: {able})"))
        return problems

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Switch the targets at scene ``time``."""
        scene.switch_props(self.config.targets(), self.on, time)


@action("switch_on")
class SwitchOn(_Switch):
    """The target tv or lamp switches on at `at` of the beat (`- switch_on: tv`): a tv's
    picture changes and flickers, a lamp glows (with a click); on an iso place a lamp lights and a
    house's windows glow. A prop can also start on (`on: true` in the stage's props or iso
    objects). Stage scenes only."""

    on = True


@action("switch_off")
class SwitchOff(_Switch):
    """The target tv or lamp switches off at `at` of the beat (`- switch_off: lamp`), with a
    click. Stage scenes only."""

    on = False
