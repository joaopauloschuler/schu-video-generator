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


def _cell_problem(action: Action, scene_cls: type[NarratedScene], params: Any, name: str) -> list[tuple[str, str]]:
    """A cell scene, one target, then the scene's own check of this use."""
    if not getattr(scene_cls, "cell_actions", False):
        return [("action", f"{name} is a cell action; this scene is not a cell")]
    targets = action.config.targets()
    if len(targets) != 1 or any(ch in targets[0] for ch in "*?["):
        return [("target", f"{name} acts on one target (one id, no wildcards)")]
    problem = scene_cls.traffic_problem(params, name, targets[0], action.options)  # type: ignore[attr-defined]
    return [("target", problem)] if problem else []


@action("motor_walk")
class MotorWalk(Action):
    """Motor proteins walk along their filament, hand over hand, carrying their cargo:
    ``{motor_walk: kin, distance: 1 um}`` — kinesin-1 in 8 nm steps to the microtubule's + end
    (out to the cell's edge), dynein in 8 nm steps to its − end (in to the centrosome), myosin V
    in 36 nm steps to the actin filament's barbed end; ``toward: minus`` on a kinesin is refused
    with the reason. Up close each step shows; from afar the motor glides."""

    class Options(ActionOptions):
        distance: float | str | None = None
        """How far ('500 nm', '1.2 um'; a number is µm); default: as far as its filament allows, at most 1 µm."""
        toward: Literal["plus", "minus"] | None = None
        """The end it walks to (checked: kinesin plus, dynein minus, myosin V plus)."""

        @field_validator("distance", mode="before")
        @classmethod
        def _distance(cls, value: Any) -> float | None:
            return None if value is None else parse_length(value, "distance")

    run_time = 2.5

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _cell_problem(self, scene_cls, params, "motor_walk")

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """At the motor's real speed (kinesin about 0.8 µm/s), between 1.5 and 8 s."""
        return scene.walk_time(targets[0].name, self.options.distance)  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Walk the motors."""
        return scene.run_motor_walk(targets[0].name, self.options.distance)  # type: ignore[attr-defined]


@action("endocytosis")
class Endocytosis(Action):
    """Clathrin-mediated endocytosis at the plasma membrane (``endocytosis: cell``): receptors
    with their ligands gather where AP2 and clathrin assemble a coated pit, the pit invaginates,
    dynamin pinches the vesicle off and the coat comes away; each step captioned. ``site``
    chooses the place (default: the plasma membrane nearest the middle of the view)."""

    class Options(ActionOptions):
        site: tuple[float | str, float | str] | None = None
        """A point near the plasma membrane ([x, y] µm from the cell's centre); default: the membrane nearest the view's middle."""
        receptors: int = Field(6, ge=0, le=12)
        """Receptor–ligand complexes taken in."""
        notes: CellNoteMode = "auto"
        """Caption each step: auto (the full caption in a wide frame, its first clause in a tall one), full (or true), short (the first clause), false (none)."""

        @field_validator("site", mode="before")
        @classmethod
        def _site(cls, value: Any) -> Any:
            if value is None:
                return None
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError("site is [x, y] in µm from the cell's centre")
            return (parse_coordinate(value[0], "site x"), parse_coordinate(value[1], "site y"))

    run_time = 6.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _cell_problem(self, scene_cls, params, "endocytosis")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Play the endocytosis."""
        return scene.run_endocytosis(self.options)  # type: ignore[attr-defined]


@action("exocytosis")
class Exocytosis(Action):
    """A vesicle fuses with the plasma membrane (``exocytosis: secretory``): it docks as its
    v-SNARE zippers with the membrane's t-SNAREs, a fusion pore opens and its cargo leaves the
    cell, and its membrane flattens into the plasma membrane. Only an uncoated vesicle in the
    cytosol fuses (a coated one is refused: it sheds its coat first)."""

    class Options(ActionOptions):
        cargo: int = Field(10, ge=0, le=30)
        """Cargo molecules released."""
        notes: CellNoteMode = "auto"
        """Caption each step: auto (the full caption in a wide frame, its first clause in a tall one), full (or true), short (the first clause), false (none)."""
        snares: Literal["generic", "constitutive", "neuronal"] = "generic"
        """Which SNAREs the captions name: generic (v-SNARE, t-SNAREs: any cell), constitutive (a VAMP, syntaxin-4, SNAP-23: constitutive secretion of non-neuronal cells), neuronal (synaptobrevin/VAMP2, syntaxin-1, SNAP-25; Ca²⁺ on synaptotagmin triggers fusion)."""

    run_time = 5.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _cell_problem(self, scene_cls, params, "exocytosis")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Play the fusion."""
        return scene.run_exocytosis(targets[0].name, self.options)  # type: ignore[attr-defined]
