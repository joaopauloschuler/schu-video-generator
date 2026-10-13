"""The ``drop_fruit`` and ``birds`` beat actions (DESIGN.md §69.55) on a ``stage``: a fruit falls
from a tree with ``fruit: true`` (on a character's head too), and a flock of birds crosses the sky.
Written against ``vidgen.api`` only, like project actions (the flock's settings are the stage's
``birds`` param's)."""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *

from .acting import is_part_target
from .stage import FlockSettings


@action("drop_fruit")
class DropFruit(Action):
    """A fruit falls from the target tree (`- drop_fruit: tree`; the tree needs `fruit: true`):
    faster and faster, it hits the ground with a thud, bounces once and lies there. `to: <character>`
    aims it at a character standing under the tree: it falls on its head (stars circle the head)
    and bounces off beside it. A tree has 4 fruits. Stage scenes only."""

    class Options(ActionOptions):
        to: str | None = None
        """The character it falls on (on the stage, standing under the tree); default: the ground under the tree."""

    run_time = 0.9

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """Targets are trees with fruit; ``to`` a character on the stage."""
        if not hasattr(scene_cls, "drop_fruit"):
            return [("action", "drop_fruit is for the trees of a stage")]
        props = dict(zip(params.prop_names(), params.stage_props()))
        problems: list[tuple[str, str]] = []
        for pattern in self.config.targets():
            for name in [n for n in scene_cls.target_names(params) if fnmatchcase(n, pattern) and not is_part_target(n)]:
                prop = props.get(name)
                if prop is None or prop.prop != "tree":
                    problems.append(("target", f"'{name}' is not a tree; drop_fruit lets a fruit fall from a tree (- drop_fruit: <tree>)"))
                elif not prop.fruit:
                    problems.append(("target", f"tree '{name}' has no fruit: give it fruit: true in the stage's props"))
        names = [c.name for c in getattr(params, "characters", [])]
        if self.options.to is not None and self.options.to not in names:
            problems.append(("to", f"'{self.options.to}' is not a character on the stage (characters: {', '.join(names) or 'none'})"))
        return problems

    def _trees(self, targets: list[Target]) -> list[str]:
        return [t.name for t in targets if isinstance(t.mobject, Prop) and t.mobject.kind == "tree"]

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """The fall and the bounce (higher trees take longer)."""
        times = [scene.fruit_drop_seconds(name, self.options.to) for name in self._trees(targets)]
        return max((t for t in times if t is not None), default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """One fruit falls from each target tree."""
        return [anim for name in self._trees(targets) for anim in scene.drop_fruit(name, self.options.to)]


@action("birds")
class Birds(Action):
    """A flock of birds crosses the sky from `at` of the beat, flapping (`- birds: 6`: six birds;
    `{birds: 4, direction: left, height: 0.85}`). Outdoors only (not in a room). The stage's
    `birds` param sends one from the start."""

    class Options(FlockSettings, ActionOptions):
        pass

    run_time = 0.1
    needs_target = False
    needs_visible = False
    scene_targets = False
    animates = False
    number_target = True

    def count(self) -> int:
        """How many birds: the action's number, else ``count``."""
        names = self.config.targets()
        try:
            return int(names[0]) if names else self.options.count
        except ValueError:
            return self.options.count

    def problems(self) -> list[tuple[str, str]]:
        """At most one number, a whole one from 1 to :data:`MAX_BIRDS`."""
        names = self.config.targets()
        if len(names) > 1:
            return [("target", "one flock per action: write `- birds: 5` (how many birds)")]
        if names and not (names[0].isdigit() and 1 <= int(names[0]) <= MAX_BIRDS):
            return [("target", f"how many birds? a whole number from 1 to {MAX_BIRDS}, e.g. `- birds: 5`")]
        return []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "add_flock"):
            return [("action", f"birds is for stage scenes; a {scene_cls.__name__} scene has no sky for them")]
        if getattr(params, "room", None) is not None:
            return [("action", "birds fly outdoors, not in a room (the stage has room:)")]
        return []

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Send the flock off at scene ``time``."""
        scene.add_flock(self.options.model_copy(update={"count": self.count()}), time)
