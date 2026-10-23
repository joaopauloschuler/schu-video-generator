"""The ``cell`` beat actions (DESIGN.md §95.6): ``zoom_to`` moves the physical-scale camera
between levels (tissue, cell, organelle, molecular complex), timed like any action (``at: 0.5``,
``at: "@word"``). Written against ``vidgen.api`` only, like project actions; the scene does the
drawing (``Cell.cell_zoom``)."""

from typing import Any, Literal

from vidgen.api import *

from .actions import camera_view


@action("zoom_to")
class ZoomTo(Action):
    """Move a cell scene's camera to a level on a target and stay there: ``- zoom_to:
    mitochondria`` (the organelle level), ``{zoom_to: rough_er, level: complex}`` (a ribosome on
    it), ``zoom_to: cell`` / ``tissue`` back out; ``width`` sets what the view spans ('2 um').
    The zoom runs at an even pace on a log scale and details appear as they grow on screen; the
    parts the view shows are named when it arrives (``labels``); ``until: <beat>`` goes back to
    the view before."""

    class Options(ActionOptions):
        level: Literal["tissue", "cell", "organelle", "complex"] | None = None
        """tissue, cell, organelle or complex (molecular); default: the target's own (organelle for a structure, complex for ribosomes)."""
        width: float | str | None = None
        """What the view spans across the body's shorter side ('3 um', '150 nm'; a number is µm); default: the level's."""
        labels: bool | list[str] = True
        """Name the parts the view shows (organelle and complex levels; with the scene's labels on): true, false, or the part names to show (e.g. [crista, matrix])."""

        @field_validator("width", mode="before")
        @classmethod
        def _width(cls, value: Any) -> float | None:
            return None if value is None else parse_length(value, "width")

    run_time = 2.0
    reversible = True
    moves_camera = True
    alters_targets = False
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """It needs a ``cell`` scene, one target, and a view the level can give on it."""
        if not getattr(scene_cls, "cell_actions", False):
            return [("action", "zoom_to is a cell action; this scene is not a cell (use zoom elsewhere)")]
        targets = self.config.targets()
        if len(targets) != 1 or any(ch in targets[0] for ch in "*?["):
            return [("target", "zoom_to goes to one target: the cell, the tissue or one object's id")]
        problem = scene_cls.zoom_problem(params, targets[0], self.options.level, self.options.width, self.options.labels)  # type: ignore[attr-defined]
        return [("target", problem)] if problem else []

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Move the camera to the target's view."""
        self.before = camera_view(scene)
        view = scene.cell_view_for(targets[0].name, self.options.level, self.options.width)  # type: ignore[attr-defined]
        return scene.cell_zoom(view)  # type: ignore[attr-defined]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to the view before, at the same even pace."""
        before = getattr(self, "before", None)
        if before is None:
            return []
        width, center = before
        return scene.cell_camera(width, center)  # type: ignore[attr-defined]
