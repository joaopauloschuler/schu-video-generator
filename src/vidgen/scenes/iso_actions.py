"""The ``iso_diagram`` beat actions (DESIGN.md §90.9): ``build``, ``raise``, ``lower``,
``explode``, ``collapse``, ``flow``, ``focus`` and ``relabel``, timed like any action (``at: 0.5``,
``at: "@word"``). Written against ``vidgen.api`` only, like project actions; the scene does the
drawing (``IsoDiagram.iso_*``)."""

from fnmatch import fnmatchcase
from typing import Any, ClassVar, Literal

from vidgen.api import *

from .actions import camera_view, move_camera_back

KIND_WORDS = {"block": "blocks and layers (block:<id>)", "stack": "stacks (stack:<id>)", "group": "groups (group:<id>)",
              "edge": "connectors (edge:<from>-><to>)", "diagram": "the whole diagram (diagram)", "heading": "the heading"}


class _IsoAction(Action):
    """An action of ``iso_diagram`` scenes: its targets must be of :attr:`kinds`."""

    #: Kinds of target it acts on (``IsoDiagram.target_kind``).
    kinds: ClassVar[tuple[str, ...]] = ("block", "stack", "group", "edge", "diagram")

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """It needs an ``iso_diagram`` scene and targets of its kinds."""
        action = self.config.action
        if not getattr(scene_cls, "iso_diagram_actions", False):
            return [("action", f"{action} is an iso_diagram action; this scene is not an iso_diagram")]
        problems: list[tuple[str, str]] = []
        names = scene_cls.target_names(params)
        for pattern in self.config.targets():
            for name in [n for n in names if fnmatchcase(n, pattern)]:
                kind = scene_cls.target_kind(name)  # type: ignore[attr-defined]
                if kind not in self.kinds:
                    wanted = ", ".join(KIND_WORDS[k] for k in self.kinds)
                    problems.append(("target", f"{action} acts on {wanted}; '{name}' is not one"))
                    break
        return problems


@action("build")
class Build(_IsoAction):
    """Bring iso_diagram targets in on the beat or a word, in a ``style``: ``grow`` (up from the
    floor; a stack layer by layer, default), ``drop`` (in from above) or ``fade``. The scene's own
    steps leave them to it (as for ``reveal``, which uses the scene's ``entrance``); a connector
    comes in once both its ends are there."""

    class Options(ActionOptions):
        style: Literal["grow", "drop", "fade"] = "grow"
        """grow (up from the floor), drop (in from above) or fade."""

    run_time = 1.0
    needs_visible = False
    kinds = ("block", "stack", "group", "edge", "diagram", "heading")

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """A little longer for several blocks (they come one after another)."""
        count = len([b for b in scene.iso_blocks_of([t for t in targets if not scene.is_shown(t)])])  # type: ignore[attr-defined]
        return min(3.0, 0.8 + 0.3 * max(count - 1, 0)) if count else None

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The targets not shown yet come in."""
        return scene.iso_build([t for t in targets if not scene.is_shown(t)], self.options.style)  # type: ignore[attr-defined]


@action("raise")
class Raise(_IsoAction):
    """Lift iso_diagram blocks, layers, stacks or groups ``by`` cells off their ground (a shadow
    shows under them; a raised layer lifts the layers above it, a group its plate too); ``until:
    <beat>`` sets them down again."""

    class Options(ActionOptions):
        by: float = Field(default=0.5, gt=0, le=4)
        """How high (cells)."""

    run_time = 0.8
    reversible = True
    kinds = ("block", "stack", "group")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.iso_raise(targets, self.options.by)  # type: ignore[attr-defined]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.iso_raise(targets, self.options.by, down=True)  # type: ignore[attr-defined]


@action("lower")
class Lower(_IsoAction):
    """Set raised iso_diagram blocks, layers, stacks or groups down: back onto their ground, or
    ``by`` cells lower (never below it); ``until: <beat>`` raises them again."""

    class Options(ActionOptions):
        by: float | None = Field(default=None, gt=0, le=4)
        """How much lower (cells); default: back onto the ground."""

    run_time = 0.8
    reversible = True
    kinds = ("block", "stack", "group")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        self.before = scene.iso_lift_state()  # type: ignore[attr-defined]
        return scene.iso_raise(targets, self.options.by, down=True)  # type: ignore[attr-defined]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        own, plates, _gaps = self.before
        return scene.iso_restore(targets, own, plates)  # type: ignore[attr-defined]


@action("explode")
class Explode(_IsoAction):
    """Pull an iso_diagram stack's layers apart, ``gap`` cells between them (their labels go
    with them), to show what it is made of; ``collapse`` or ``until: <beat>`` puts them back."""

    class Options(ActionOptions):
        gap: float = Field(default=0.6, gt=0, le=3)
        """Space between the layers (cells)."""

    run_time = 1.0
    reversible = True
    kinds = ("stack",)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        self.before = scene.iso_lift_state()[2]  # type: ignore[attr-defined]
        return scene.iso_explode(targets, self.options.gap)  # type: ignore[attr-defined]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.iso_explode(targets, None, gaps=self.before)  # type: ignore[attr-defined]


@action("collapse")
class Collapse(_IsoAction):
    """Put an exploded iso_diagram stack's layers back together (its own ``gap``); ``until:
    <beat>`` pulls them apart again."""

    run_time = 0.8
    reversible = True
    kinds = ("stack",)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        self.before = scene.iso_lift_state()[2]  # type: ignore[attr-defined]
        return scene.iso_explode(targets, None)  # type: ignore[attr-defined]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.iso_explode(targets, None, gaps=self.before)  # type: ignore[attr-defined]


@action("flow")
class Flow(_IsoAction):
    """Send ``count`` dots (or small ``packets``) along iso_diagram connectors, from their start
    to their tip (``back``: the other way), on top of a pipe; ``chain``: the connectors one
    after another, in the order matched (a request passing through)."""

    class Options(ActionOptions):
        count: int = Field(default=3, ge=1, le=12)
        """How many dots, one after another."""
        style: Literal["dots", "packets"] = "dots"
        """dots, or packets (small cubes)."""
        color: ThemeColor = "highlight"
        """Their colour."""
        back: bool = False
        """From the connector's tip to its start."""
        chain: bool = False
        """The targets one after another (each its share of run_time) instead of together."""

    run_time = 1.6
    kinds = ("edge",)

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """A chain takes 1.2 s per connector (at most 6 s)."""
        return min(6.0, 1.2 * len(targets)) if self.options.chain and len(targets) > 1 else None

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        o = self.options
        return scene.iso_flow(targets, count=o.count, style=o.style, color=scene.theme.color(o.color), back=o.back, chain=o.chain)  # type: ignore[attr-defined]


@action("focus")
class Focus(_IsoAction):
    """Move the camera onto iso_diagram targets (no rotation): as close as they fit with
    ``padding`` around them (or ``scale``), and stay there; ``focus: diagram`` or ``until:
    <beat>`` goes back to the whole view."""

    class Options(ActionOptions):
        padding: float = Field(default=0.12, ge=0, lt=0.45)
        """Share of the view kept free on each side of the targets."""
        scale: float | None = Field(default=None, gt=1, le=6)
        """Magnification (2 = twice as large); default: as close as they fit (at most 3x)."""

    run_time = 1.2
    reversible = True
    moves_camera = True
    alters_targets = False
    kinds = ("block", "stack", "group", "edge", "diagram", "heading")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Move the view onto the targets."""
        self.before = camera_view(scene)
        width, centre = scene.iso_focus_view(targets, self.options.padding, self.options.scale)  # type: ignore[attr-defined]
        return move_camera_back(scene, (width, centre))

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to the view before."""
        return move_camera_back(scene, getattr(self, "before", None))


@action("relabel")
class Relabel(_IsoAction):
    """Change the label of an iso_diagram block, layer, stack, group or connector to ``text`` (a
    new value, a new name): the old text morphs into the new one in place (the scene keeps room
    for it); ``until: <beat>`` brings the old text back."""

    class Options(ActionOptions):
        text: TranslatableStr = Field(min_length=1)
        """The new label."""

    run_time = 0.8
    reversible = True
    kinds = ("block", "stack", "group", "edge")

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """Its targets must have a label."""
        problems = super().scene_problems(scene_cls, params)
        if problems:
            return problems
        for pattern in self.config.targets():
            for name in [n for n in scene_cls.target_names(params) if fnmatchcase(n, pattern)]:
                if not scene_cls.has_label(params, name):  # type: ignore[attr-defined]
                    problems.append(("target", f"'{name}' has no label to change; give it a label"))
        return problems

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims: list[Animation] = []
        self.before: dict[int, str] = {}
        for t in targets:
            made, old = scene.iso_relabel(t, str(self.options.text))  # type: ignore[attr-defined]
            if old is not None:
                self.before[id(t)] = old
            anims += made
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims: list[Animation] = []
        for t in targets:
            if id(t) in getattr(self, "before", {}):
                anims += scene.iso_relabel(t, self.before[id(t)])[0]  # type: ignore[attr-defined]
        return anims


__all__ = ["Build", "Collapse", "Explode", "Flow", "Focus", "Lower", "Raise", "Relabel"]
