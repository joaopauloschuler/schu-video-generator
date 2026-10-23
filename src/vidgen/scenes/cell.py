"""``cell``: a cell in physical scale (DESIGN.md §95): its compartments, membranes and contents
drawn from the cell world (``vidgen.cellworld``: the model and its location rules, no manim)
by ``vidgen.cell_vector``, with a camera that zooms from a tissue to the lipids of one membrane
(``zoom_to``, ``scenes/cell_actions.py``), level-of-detail switching as it goes, screen-sized
labels (for the start view and for each zoomed view) and an automatic scale bar."""

import math
from functools import lru_cache
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .math_axes import ChainedTargets

Length = float | str
CellLevel = Literal["tissue", "cell", "organelle", "complex"]
#: Labels: gap between a structure and its label (screen units), the leader line's width, the
#: opacity of the plates under labels, the title and the scale bar.
LABEL_GAP, LEADER_WIDTH, PLATE_OPACITY = 0.12, 1.6, 0.82
#: The scale bar's height (screen units) and its distance from the body's corner; the room
#: labels leave above the body's lower edge on its side.
BAR_HEIGHT, BAR_MARGIN, BAR_ROOM, BAR_WIDTH = 0.07, 0.15, 0.75, 1.3
#: Labels fade out as the camera zooms away from the start view: from this log zoom to this one.
LABEL_ZOOM = (math.log(1.2), math.log(1.6))
#: A zoomed view's labels show while the camera is this close to it (log zoom; share of its
#: width off its centre).
VIEW_ZOOM, VIEW_SHIFT = (math.log(1.06), math.log(1.3)), (0.03, 0.12)
#: Labels, the title and the scale bar are drawn over the cell.
OVERLAY_Z = 50
#: Level of detail is measured in pixels of a frame whose shorter side is this many pixels, so
#: a preview shows the details the final video shows.
REF_PIXELS = 1080.0
#: The shortest scale bar any view gets (µm): a view spanning a few nanometres.
BAR_SMALLEST = 0.004


def _length(value: Any, what: str) -> float | None:
    return None if value is None else parse_length(value, what)


class CellBody(SceneParams):
    """The cell: ``{kind, size, aspect, ...}``; a kind alone (``animal``) is the cell."""

    also_accepts = (str,)

    kind: Literal["animal", "plant", "bacterium"] = "animal"
    """The kind of cell: animal (20 µm), plant (32 µm, a wall, a central vacuole, chloroplasts) or bacterium (a 2 µm rod)."""
    size: Length | None = None
    """Its long axis: a number of µm or a length ('20 um'); default by kind (animal 20, plant 32, bacterium 2 µm)."""
    aspect: float | None = Field(None, ge=1.0, le=4.0)
    """Its long axis over its short axis (1: round); default by kind (1.25, 1.6, 2.5)."""
    gram: Literal["negative", "positive"] | None = None
    """Bacterium: negative (an inner and an outer membrane with the periplasm between; default) or positive (a thick peptidoglycan wall)."""
    capsule: bool | None = None
    """Bacterium: a polysaccharide capsule outside the wall (default false)."""
    wall: Length | None = None
    """Plant: the cell wall's thickness (default 250 nm; a primary wall is 0.1–1 µm)."""
    plasmodesmata: bool | None = None
    """Plant: channels through the wall to the neighbouring cells (default true)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"kind": data} if isinstance(data, str) else data

    @field_validator("size", "wall", mode="before")
    @classmethod
    def _size(cls, value: Any) -> float | None:
        return _length(value, "cell size")

    @model_validator(mode="after")
    def _options(self) -> "CellBody":
        for name, kind in (("gram", "bacterium"), ("capsule", "bacterium"), ("wall", "plant"), ("plasmodesmata", "plant")):
            if getattr(self, name) is not None and self.kind != kind:
                raise ValueError(f"cell {name} is for a {kind}, not an {self.kind} cell" if self.kind == "animal" else
                                 f"cell {name} is for a {kind}, not a {self.kind}")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A kind alone is also a cell (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}


class CellObject(SceneParams):
    """Something in the cell: ``{kind, id, at, size, width, angle, in, on, count, label}`` plus
    options of some kinds; a kind alone (``mitochondrion``) is one of it, placed automatically."""

    also_accepts = (str,)

    kind: str
    """What it is: nucleus, nucleolus, rough_er, smooth_er, golgi, mitochondrion, lysosome, peroxisome, endosome, early_endosome, late_endosome, vesicle, centrosome, chloroplast, vacuole, nucleoid, ribosome, proteasome, nuclear_pore, plasmid, microtubule, actin_filament, actin_cortex, stress_fiber, intermediate_filament, flagellum, pilus, kinesin, dynein, myosin; molecules (drawn up close): dna, mrna, trna, rrna, nucleosome, chromatin, protein, kinase, phosphatase, g_protein, gpcr, rtk, ion_channel, carrier, na_k_atpase, atp_synthase, atp, adp, pi, gtp, gdp, camp, glucose, ligand, ion."""
    id: str | None = None
    """Its name for actions and labels (default: the kind; an object with the id of a typical one replaces it)."""
    at: tuple[Length, Length] | None = None
    """Where its middle is (a filament: its minus end): [x, y] in µm from the cell's centre (x right, y up), or lengths ['2 um', '-500 nm']; default: placed automatically."""
    size: Length | None = None
    """Its length (µm or '1.5 um'); default: a typical size of its kind (the cortex: its thickness)."""
    width: Length | None = None
    """Its width for elongated kinds (a mitochondrion: about 0.5–1 µm)."""
    angle: float | None = None
    """Turn in degrees (a Golgi stack: the direction its cis face looks, default towards the nucleus; a filament: its direction; a flagellum or pilus: where round the cell it is anchored, 0 = the right pole)."""
    inside: str | None = Field(None, alias="in")
    """For complexes: the compartment they float in: cytosol (default), nucleoplasm, matrix, stroma, an object's id (its inside) or '<id>.<compartment>'."""
    on: str | None = None
    """For complexes: the object whose membrane they sit on (ribosomes: rough_er or the nucleus; membrane proteins: cell for the plasma membrane, a mitochondrion, a chloroplast…) or the filament a motor walks on (kinesin, dynein: a microtubule object; myosin: actin)."""
    count: int = Field(1, ge=1, le=400)
    """How many, scattered where they may be (no at); microtubules radiate from the centrosome."""
    label: TranslatableStr | bool | None = None
    """Its label (default: its kind's name, when the scene's labels are on); false for none."""
    sheets: int | None = Field(None, ge=1, le=8)
    """Rough ER: how many sheets round the nucleus (default 4)."""
    span: float | None = Field(None, gt=0, le=330)
    """Rough ER: how far round the nucleus the sheets reach (degrees, default 200)."""
    side: float | None = None
    """Rough ER: the direction of the sheets' middle from the nucleus (degrees; default away from the Golgi)."""
    cisternae: int | None = Field(None, ge=3, le=8)
    """Golgi: how many cisternae in the stack (default 5), cis to trans."""
    tubules: int | None = Field(None, ge=2, le=40)
    """Smooth ER: about how many tubules in its network (default 10)."""
    pores: bool | None = None
    """Nucleus: draw the nuclear pores (default true)."""
    ribosomes: bool | None = None
    """Nucleus and rough ER: ribosomes on the cytosolic face (default true)."""
    coat: Literal["none", "clathrin", "copi", "copii"] | None = None
    """Vesicle: its coat (default none): clathrin (from the plasma membrane and the trans-Golgi), copi (Golgi → ER and within the Golgi), copii (ER → Golgi)."""
    cargo: bool | None = None
    """Kinesin, dynein, myosin: carry a cargo vesicle (default false)."""
    grana: int | None = Field(None, ge=1, le=12)
    """Chloroplast: how many grana (stacks of thylakoids; default about one per µm of length)."""
    style: Literal["section", "surface"] | None = None
    """Its drawing: section (cut open, as in a thin section) or surface (whole, seen from outside); default the scene's style."""
    state: str | None = None
    """A molecule's state (gpcr: inactive / active; ion_channel: closed / open; carrier: outward / inward; rtk: monomer / dimer…)."""
    faces: str | None = None
    """A membrane protein: the compartment its oriented part faces (ATP synthase F₁: matrix; a GPCR's N-terminus: extracellular); checked."""
    membrane: str | None = None
    """A membrane protein on an object: which of its membranes (inner, outer, thylakoid, or a full name); default the first it occurs in."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"kind": data}
        if isinstance(data, dict) and True in data and "on" not in data:
            # YAML 1.1 reads the key `on` as true: `{kind: ribosome, on: rough_er}` arrives as {True: 'rough_er'}
            data = {("on" if k is True else k): v for k, v in data.items()}
        return data

    @field_validator("size", "width", mode="before")
    @classmethod
    def _lengths(cls, value: Any) -> float | None:
        return _length(value, "size")

    @field_validator("at", mode="before")
    @classmethod
    def _at(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("at is [x, y] in µm from the cell's centre, e.g. [3, -1.5]")
        return (parse_coordinate(value[0], "at x"), parse_coordinate(value[1], "at y"))

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A kind alone is also an object (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}

    def spec(self, where: str) -> CellObjectSpec:
        return CellObjectSpec(self.kind, self.id, self.at, self.size, self.width, self.angle, self.inside, self.on, self.count,  # type: ignore[arg-type]
                              self.sheets, self.span, self.side, self.cisternae, self.tubules, self.pores, self.ribosomes, where,
                              self.coat, self.cargo, self.grana, self.style, self.state, self.faces, self.membrane)


class CellViewSpec(SceneParams):
    """Where the camera starts: a level (``cell``) or ``{level, on, width}``."""

    also_accepts = (str,)

    level: CellLevel = "cell"
    """tissue, cell, organelle or complex (molecular)."""
    on: str | None = None
    """The object to centre on (organelle and complex levels; default the nucleus; complex on the cell: its plasma membrane)."""
    width: Length | None = None
    """What the view spans across the frame's body, shorter side (e.g. '3 um'); default: the level's."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if isinstance(data, dict) and True in data and "on" not in data:   # YAML 1.1 reads the key `on` as true
            data = {("on" if k is True else k): v for k, v in data.items()}
        return {"level": data} if isinstance(data, str) else data

    @field_validator("width", mode="before")
    @classmethod
    def _width(cls, value: Any) -> float | None:
        return _length(value, "width")

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A level alone is also a view (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "string", "enum": list(CELL_LEVELS)}, handler(core_schema)]}


@lru_cache(maxsize=32)
def _world(spec: CellSpec) -> CellWorld:
    return build_cell_world(spec)


@scene("cell")
class Cell(NarratedScene):
    """A cell drawn in physical scale: a cross-section of an animal cell, a plant cell or a
    bacterium with its compartments (cytosol, nucleoplasm, ER and Golgi lumens, mitochondrial
    matrix and intermembrane space, stroma and thylakoid lumen, periplasm…), the membranes
    between them and what is in them, at textbook sizes (``contents: typical`` is the textbook
    cell; ``objects`` add or replace things, the cytoskeleton and motors too). Every place is
    checked: a ribosome in the nucleoplasm, a mitochondrion inside the nucleus or a chloroplast
    in an animal cell is refused with the reason. The camera is in µm: ``view`` sets the start
    level (tissue, cell, organelle, complex) and the ``zoom_to`` action moves between levels;
    details appear as they grow on screen (double membranes, cristae, thylakoids, nuclear pores,
    ribosome subunits, coats, lipid bilayers with their lipids). A scale bar and labels keep
    their size on screen; a zoomed view names the parts it shows.

    Action targets: ``title``, ``cell``, ``tissue``, ``scale_bar`` and each object's id (an
    object of several things is one target)."""

    outro = 0.5
    target_patterns = ("title", "cell", "tissue", "scale_bar", "<id>")
    #: The ``zoom_to`` action acts on this scene type only.
    cell_actions = True
    mid_still_actions = frozenset({"zoom_to"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        cell: CellBody = Field(default_factory=CellBody)
        """The cell: 'animal', 'plant', 'bacterium' or {kind, size (µm or '20 um'), aspect, gram, capsule, wall, plasmodesmata}."""
        contents: Literal["typical", "none"] = "typical"
        """typical: the textbook cell of its kind (animal: nucleus, ER, Golgi, centrosome, mitochondria, lysosomes, peroxisomes, endosomes, vesicles, ribosomes; plant: also a central vacuole and chloroplasts, no centrosome or lysosomes; bacterium: nucleoid, 70S ribosomes, plasmids, flagella, pili); none: only the objects listed."""
        objects: list[CellObject] = Field(default_factory=list, max_length=60)
        """Things in the cell: a kind, or {kind, id, at, size, width, angle, in, on, count, label}; an id of a typical object replaces it."""
        view: CellViewSpec = Field(default_factory=CellViewSpec)
        """Where the camera starts: tissue, cell (default), organelle or complex, or {level, on, width}."""
        style: Literal["section", "surface"] = "section"
        """section: structures cut open, as in a thin section (default); surface: drawn whole, seen from outside (the cell itself stays open)."""
        labels: bool = True
        """Name the structures (screen-sized; shown once a structure is large enough on screen) and the parts a zoom_to view shows."""
        scale_bar: bool = True
        """A scale bar that follows the zoom (1-2-5 lengths: 5 µm, 200 nm…)."""
        reveal: Literal["all", "per_beat"] = "all"
        """all: the whole cell in the first beat; per_beat: the cell, then one object per beat in order."""
        seed: int = 1
        """Changes where things without at are placed."""
        title_size: ThemeSize = "heading"
        """Title size."""
        label_size: ThemeSize = "caption"
        """Size of the labels and the scale bar's text."""

        def spec(self) -> CellSpec:
            objects = tuple(o.spec(f"objects[{k}]") for k, o in enumerate(self.objects))
            body = self.cell
            return CellSpec(body.kind, None if body.size is None else float(body.size), body.aspect, self.contents, objects, self.seed,  # type: ignore[arg-type]
                            body.gram or "negative", bool(body.capsule), None if body.wall is None else float(body.wall),
                            body.plasmodesmata is not False, self.style)

        def world(self) -> CellWorld:
            return _world(self.spec())

        @model_validator(mode="after")
        def _check(self) -> "Cell.Params":
            try:
                world = self.world()
                if self.view.on is not None:
                    _check_target(world, self.view.on, "view.on")
                    cell_level_view(world, self.view.level, 16 / 9, self.view.on)
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``cell``, ``tissue``, each object's id, ``scale_bar`` (if shown)."""
        world = params.world()
        names = (["title"] if params.title else []) + ["cell", "tissue"]
        names += [e.id for e in world.entries if e.owner is None]
        return names + (["scale_bar"] if params.scale_bar else [])

    @classmethod
    def zoom_problem(cls, params: Any, name: str, level: str | None, width: float | None, labels: Any = True) -> str | None:
        """Why ``zoom_to`` cannot go to ``name`` (``None``: it can), or name ``labels``."""
        if name in ("title", "scale_bar"):
            return f"zoom_to goes to the cell, the tissue or an object, not '{name}'"
        world = params.world()
        try:
            view = cell_level_view(world, level or cell_default_level(world, name), 16 / 9, name, width)
        except (VidgenError, KeyError) as error:
            return str(error)
        if isinstance(labels, list):
            parts = [a.name for a in cell_part_anchors(world, name, view, (1e9, 1e9))]
            for wanted in labels:
                if wanted not in parts:
                    shown = ", ".join(parts) or "none"
                    return f"labels: '{wanted}' is not a part this view names{did_you_mean(wanted, parts)} (parts: {shown})"
        return None

    # ----- building -----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self.world = p.world()
        self._frame = (self.frame_width, self.frame_height)     # kept: the camera's scale is measured against it
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.3)
        self.body = body
        self.body_center = np.array([float(body.center[0]), float(body.center[1]), 0.0])
        self.body_short = min(body.width, body.height)
        aspect = body.width / body.height
        self.aspect = aspect
        self.start = cell_level_view(self.world, p.view.level, aspect, p.view.on, p.view.width)
        self.unit = self.body_short / self.start.span
        self._zooms = [(use, self._zoom_view(use)) for use in self.action_uses("zoom_to")]
        closeups = [(v.center, v.span) for v in [self.start, *(view for _, view in self._zooms if view is not None)]]
        colors = CellColors(self.theme.background, self.theme.color("text"))
        self.drawing = CellDrawing(self.world, colors, self.unit, self.to_scene((0.0, 0.0)), closeups, p.style)
        self._pinned: list[list[Any]] = []
        self._labels: list[_CellLabel] = []
        self._view_labels: list[tuple[float, np.ndarray, list[_CellLabel]]] = []
        self._camera_state: tuple[float, float, float] | None = None
        self._bar: Mobject | None = None
        if title is not None:
            plate = RoundedRectangle(width=title.width + 0.4, height=title.height + 0.2, corner_radius=0.08, stroke_width=0,
                                     fill_color=self.theme.background, fill_opacity=PLATE_OPACITY).move_to(title.get_center())
            title = VGroup(plate, title)    # readable over the tissue when the camera zooms out
            self.pin(title, title.get_center())
        bar = self._scale_bar() if p.scale_bar else None
        # a start view on the cell names its objects; a zoomed start view names the parts it shows
        labels = self._make_labels() if p.labels and self.start.level in ("tissue", "cell") else {}
        start_parts, views = self._make_view_labels() if p.labels else (VGroup(), VGroup())
        labels.setdefault("cell", []).append(start_parts)
        self._place_view(self.start)
        self.on_camera()

        chain = ChainedTargets(self)
        base: list[Target] = []
        if title is not None:
            base.append(chain.add("title", title, lambda: [FadeIn(title)], []))
        tissue = self.drawing.tissue
        base.append(chain.add("tissue", tissue, lambda: [FadeIn(tissue)], list(base)))
        cell_group = VGroup(self.drawing.cell, *labels.get("cell", []))
        base.append(chain.add("cell", cell_group, lambda: [FadeIn(cell_group)], list(base)))
        if bar is not None:
            base.append(chain.add("scale_bar", bar, lambda: [FadeIn(bar)], list(base)))
        self.add(views)
        items = []
        for entry_id in self.drawing.order:
            group = VGroup(self.drawing.groups[entry_id], *labels.get(entry_id, []))
            items.append(chain.add(entry_id, group, lambda g=group: [FadeIn(g)], list(base)))
        self.add_camera_listener(self.on_camera)
        chain.reveal(base, items, p.reveal == "all")
        self.finish()

    def play(self, *args: Any, **kwargs: Any) -> None:
        """Manim's ``play``, the drawing's level of detail first given to the targets as their
        full opacity (a ``dim`` or ``highlight`` scales what is shown at this zoom)."""
        drawing = getattr(self, "drawing", None)
        if drawing is not None:
            drawing.lod.mark_play()
            rest = next((t.rest for t in self.targets), None)
            if rest is not None:
                rest.update({k: v for k, v in drawing.lod.rest().items() if k in rest})
        super().play(*args, **kwargs)

    def to_scene(self, p: tuple[float, float]) -> np.ndarray:
        """Scene point of world point ``p`` (µm)."""
        c = self.start.center
        return self.body_center + self.unit * np.array([p[0] - c[0], p[1] - c[1], 0.0])

    def camera_bounds(self) -> tuple[float, float, float, float]:
        """The tissue and some room round it: a zoom or a pan may go anywhere in the world."""
        x0, y0, x1, y1 = self.world.tissue_bounds()
        a, b = self.to_scene((x0, y0)), self.to_scene((x1, y1))
        room = max(self._frame)
        return (float(a[0]) - room, float(b[0]) + room, float(a[1]) - room, float(b[1]) + room)

    def view_camera(self, view: CellView) -> tuple[float, np.ndarray]:
        """The camera width and centre that show ``view`` in the body."""
        s = view.span / self.start.span
        return self._frame[0] * s, self.to_scene(view.center) - s * self.body_center

    def _place_view(self, view: CellView) -> None:
        width, center = self.view_camera(view)
        frame = self.camera.frame
        frame.width = width
        frame.move_to(center)

    def cell_view_for(self, name: str, level: str | None, width: float | None) -> CellView:
        """The view ``zoom_to`` goes to."""
        return cell_level_view(self.world, level or cell_default_level(self.world, name), self.aspect, name, width)

    def _zoom_view(self, use: Any) -> CellView | None:
        """The view a ``zoom_to`` action goes to."""
        try:
            return self.cell_view_for(use.config.targets()[0], use.options.level, use.options.width)
        except (VidgenError, KeyError, IndexError):
            return None

    # ----- pinned (screen-sized) things -----------------------------------------------------

    def pin(self, mob: Mobject, screen: np.ndarray | None = None, world: np.ndarray | None = None, offset: np.ndarray | None = None) -> None:
        """Keep ``mob`` its size on screen and in front of the cell: at ``screen`` (a point of the
        unzoomed frame) or at the scene point ``world`` plus ``offset`` (unzoomed units)."""
        mob.set_z_index(OVERLAY_Z)
        self._pinned.append([mob, screen, world, offset if offset is not None else np.zeros(3), 1.0])

    def screen_scale(self) -> tuple[float, float, float]:
        """``(s, px_per_um, span)`` now: the camera's width over the frame's, pixels per µm (of a
        1080-pixel shorter side, whatever the resolution) and µm across the body."""
        s = float(self.camera.frame.width) / self._frame[0]
        return s, self.unit * self.ref_pixels / s, self.start.span * s

    @property
    def ref_pixels(self) -> float:
        """Reference pixels per scene unit of the unzoomed frame."""
        return REF_PIXELS / min(self._frame)

    def on_camera(self) -> None:
        """Every frame: keep what actions did to the drawing's opacity; when the camera moved,
        pinned things keep their place and size on screen, the drawing its level of detail,
        labels show by their structure's size and how near the camera is to their view, the
        scale bar its length."""
        self.drawing.sync()
        frame = self.camera.frame
        center = np.array(frame.get_center())
        state = (round(float(frame.width), 9), round(float(center[0]), 9), round(float(center[1]), 9))
        if state == self._camera_state:
            return
        self._camera_state = state
        s, px_per_um, span = self.screen_scale()
        stroke_unit = s * 100 / self.ref_pixels           # Manim stroke width per (1080-p) pixel now
        if self._bar is not None:
            self._update_bar(span, s, center)
        for item in self._pinned:
            mob, screen, world, offset, applied = item
            if abs(s / applied - 1) > 1e-9:
                mob.scale(s / applied)
                item[4] = s
            mob.move_to(center + screen * s if screen is not None else world + offset * s)
        extra: dict[str, float] = {}
        # start labels are laid out for the start view: they give way to the tissue and fade out
        # as the camera zooms away from that view (and back in as it returns)
        crowd = (1.0 - self.drawing.weights(px_per_um, span)["neighbours"]) * (1.0 - smooth_step(abs(math.log(s)), *LABEL_ZOOM))
        half_w, half_h = float(frame.width) / 2, float(frame.height) / 2
        for label in self._labels:
            anchor = label.anchor
            seen = abs(anchor[0] - center[0]) < half_w * 0.97 and abs(anchor[1] - center[1]) < half_h * 0.97
            weight = cell_label_weight(label.size, px_per_um) * crowd if seen else 0.0
            extra.update(label.show(weight, s, center))
        # a zoomed view's labels: while the camera is (nearly) at that view
        for width, view_center, labels in self._view_labels:
            near = (1.0 - smooth_step(abs(math.log(float(frame.width) / width)), *VIEW_ZOOM)) * \
                (1.0 - smooth_step(float(np.linalg.norm(center[:2] - view_center[:2])) / width, *VIEW_SHIFT))
            for label in labels:
                extra.update(label.show(near, s, center))
        self.drawing.update(px_per_um, span, stroke_unit, extra)

    # ----- scale bar ------------------------------------------------------------------------

    def _scale_bar(self) -> VGroup:
        """A bar of a 1-2-5 length in the body's lower left corner, its length written above it
        on a plate; the text and the length change as the camera zooms."""
        color = self.theme.color("text")
        self._bar = Rectangle(width=1.0, height=BAR_HEIGHT, stroke_width=0, fill_color=color, fill_opacity=1.0).set_z_index(OVERLAY_Z + 1)
        self._bar_plate = RoundedRectangle(width=1.0, height=0.5, corner_radius=0.06, stroke_width=0, fill_color=self.theme.background,
                                           fill_opacity=PLATE_OPACITY).set_z_index(OVERLAY_Z)
        # every text the bar may show in this scene is made now and only shown or hidden: Manim
        # draws an animation's mobjects as they were when it started, so a text swapped in
        # during a zoom would not be drawn (and the one swapped out would stay); the range runs
        # down to a few nanometres, so a built-in zoom deeper than every zoom_to has its text too
        spans = [self.start.span] + [view.span for _, view in self._zooms if view is not None]
        self._bar_texts: dict[str, Mobject] = {}
        for length in _bar_lengths(BAR_SMALLEST, max(spans) * 2):
            text = self.text(format_length(length), size=self.params.label_size, color="text").set_z_index(OVERLAY_Z + 1)
            text.set_fill(opacity=0.0)
            text.applied = 1.0  # type: ignore[attr-defined]
            self._bar_texts[format_length(length)] = text
        self._bar_label = VGroup(*self._bar_texts.values()).set_z_index(OVERLAY_Z + 1)
        self._bar_corner = np.array([self.body.x0 + BAR_MARGIN, self.body.y0 + BAR_MARGIN, 0.0])
        return VGroup(self._bar_plate, self._bar, self._bar_label)

    def _update_bar(self, span: float, s: float, center: np.ndarray) -> None:
        length, text = cell_scale_bar(span)
        x0, y0 = (center + self._bar_corner * s)[:2]
        bar_w, h = length * self.unit, BAR_HEIGHT * s
        self._bar.set_points_as_corners([[x0, y0, 0], [x0 + bar_w, y0, 0], [x0 + bar_w, y0 + h, 0], [x0, y0 + h, 0], [x0, y0, 0]])
        shown = self._bar.get_fill_opacity()
        label = self._bar_texts.get(text)
        for other in self._bar_texts.values():
            if other.applied != s:  # type: ignore[attr-defined]
                other.scale(s / other.applied)  # type: ignore[attr-defined]
                other.applied = s  # type: ignore[attr-defined]
            other.move_to([x0 + other.width / 2, y0 + h + 0.08 * s + other.height / 2, 0])
            other.set_fill(opacity=shown if other is label else 0.0)
        width = label.width if label is not None else 0.0
        height = label.height if label is not None else 0.0
        pad = 0.1 * s
        right = max(x0 + bar_w, x0 + width)
        top = y0 + h + 0.08 * s + height
        plate = self._bar_plate
        plate.stretch_to_fit_width(right - x0 + 2 * pad)
        plate.stretch_to_fit_height(top - y0 + 2 * pad)
        plate.move_to([(x0 + right) / 2, (y0 + top) / 2, 0])

    # ----- labels ---------------------------------------------------------------------------

    def _label_text(self, entry_id: str) -> str:
        spec = next((o for o in self.params.objects if (o.id or None) == entry_id), None)
        if spec is not None and spec.label is False:
            return ""
        if spec is not None and isinstance(spec.label, str) and spec.label:
            return spec.label
        entry = self.world.entry(entry_id)
        kind = CELL_OBJECT_KINDS[entry.kind]
        text = kind.plural if len(entry.keys) > 1 else kind.label
        if entry.kind == "ribosome" and self.world.kind == "bacterium":
            text += " (70S)"
        return text

    def _cell_parts(self) -> list[tuple[str, Any]]:
        """Parts of the cell itself named in the start view: a plant's wall, a bacterium's outer
        membrane or wall, its capsule; each with a placed-like thing to anchor on."""
        out = []
        layers = dict(self.world.envelope)
        names = {"cell_wall": "Cell wall", "periplasm": "Outer membrane", "capsule": "Capsule"}
        for name, shape in layers.items():
            out.append((names[name], CellPart(shape)))
        return out

    def _make_labels(self) -> dict[str, list[Mobject]]:
        """A label for each object (its own text, else its kind's name, plural for several) with
        a leader line to it: in columns left and right of the cell when the body has room there
        (16:9), else in rows above and below it (9:16), else beside each thing."""
        made: list[_CellLabel] = []
        _s, px_per_um, _span = self.screen_scale()
        for entry_id in self.drawing.order:
            text = self._label_text(entry_id)
            size = self.world.members(entry_id)[0].size
            if text and cell_label_weight(size, px_per_um) > 0.5:   # what is too small to see here is not named
                words = self.text(text, size=self.params.label_size, color="text")
                made.append(_CellLabel(self, entry_id, words, self.world.members(entry_id)))
        for text, part in self._cell_parts():
            if cell_label_weight(part.size, px_per_um) > 0.5:
                made.append(_CellLabel(self, "cell", self.text(text, size=self.params.label_size, color="text"), [part]))
        if not made:
            return {}
        x0, y0, x1, y1 = self.world.outside.bounds()
        a, b = self.to_scene((x0, y0)), self.to_scene((x1, y1))
        cell_box = (float(a[0]), float(a[1]), float(b[0]), float(b[1]))
        # a wide body: columns beside the cell (over its edge when the cell fills the body); a tall
        # one: rows above and below it, else columns
        wide = self.body.width >= self.body.height
        if not (wide and self._columns(made, cell_box)) and not self._rows(made, cell_box) and not self._columns(made, cell_box):
            for lab in made:
                lab.beside()
        self._labels = made
        out: dict[str, list[Mobject]] = {}
        for lab in made:
            out.setdefault(lab.entry_id, []).append(lab.group)
        return out

    def _make_view_labels(self) -> tuple[VGroup, VGroup]:
        """Labels of the parts a zoomed start view and each ``zoom_to`` view show: in columns at
        the body's sides (rows above and below in a tall frame), leader lines to the parts;
        ``(the start view's, the others)``."""
        views: list[tuple[CellView, str | None, Any]] = []
        if self.start.level in ("organelle", "complex"):
            views.append((self.start, self.params.view.on, True))
        for use, view in self._zooms:
            if view is not None and view.level in ("organelle", "complex") and use.options.labels is not False:
                views.append((view, use.config.targets()[0], use.options.labels))
        start, everything = VGroup(), VGroup()
        for view, name, wanted in views:
            short = view.span
            half = (short * self.aspect / 2, short / 2) if self.aspect >= 1 else (short / 2, short / self.aspect / 2)
            anchors = cell_part_anchors(self.world, name, view, half)
            if isinstance(wanted, list):
                anchors = [a for a in anchors if a.name in wanted]
            if not anchors:
                continue
            width, cam = self.view_camera(view)
            s = width / self._frame[0]
            made = [_CellLabel(self, None, (self.markup if "<" in a.label else self.text)(a.label, size=self.params.label_size, color="text"), [],
                               anchor=self.to_scene(a.point)) for a in anchors]
            self._layout_view(made, s, cam)
            self._view_labels.append((width, cam, made))
            (start if view is self.start else everything).add(*[lab.group for lab in made])
        return start, everything

    def _layout_view(self, made: list["_CellLabel"], s: float, cam: np.ndarray) -> None:
        """Place a zoomed view's labels at the body's edges, near the height (or the place
        across) of what they name, clear of the scale bar."""
        body = self.body
        screen = {id(lab): (lab.anchor - cam) / s for lab in made}
        bar_room = BAR_ROOM if self.params.scale_bar else 0.0
        if self.aspect >= 1.0:
            for side in (-1, 1):
                labs = [lab for lab in made if (screen[id(lab)][0] >= body.center[0]) == (side > 0)]
                labs.sort(key=lambda lab: screen[id(lab)][1])
                lo = body.y0 + (bar_room if side < 0 else 0.1)
                ys = _spread([float(screen[id(lab)][1]) for lab in labs], [lab.height for lab in labs], 0.1, lo, body.y1 - 0.05)
                for lab, y in zip(labs, ys):
                    x = body.x0 + 0.1 + lab.width / 2 if side < 0 else body.x1 - 0.1 - lab.width / 2
                    lab.put_screen(np.array([x, y, 0.0]), s, cam)
            return
        sides = {side: [lab for lab in made if (screen[id(lab)][1] >= body.center[1]) == (side > 0)] for side in (-1, 1)}

        def wide(labs: list[_CellLabel]) -> bool:
            return sum(lab.width + 0.14 for lab in labs) > body.width - 0.2

        for side in (-1, 1):
            # a second row's leaders cross the first: move labels to the other edge while it has room
            while wide(sides[side]) and len(sides[side]) > 1:
                mover = min(sides[side], key=lambda lab: abs(float(screen[id(lab)][1]) - body.center[1]))
                if wide(sides[-side] + [mover]):
                    break
                sides[side].remove(mover)
                sides[-side].append(mover)
        for side in (-1, 1):
            labs = sorted(sides[side], key=lambda lab: screen[id(lab)][0])
            count = 1
            while count < len(labs) and any(wide(labs[k::count]) for k in range(count)):
                count += 1
            rows = [labs[k::count] for k in range(count)]
            tall = max((lab.height for lab in labs), default=0.0)
            for k, row in enumerate(rows):
                edge = body.y1 - 0.08 - tall / 2 - k * (tall + 0.1) if side > 0 else body.y0 + bar_room + tall / 2 + k * (tall + 0.1)
                xs = _spread([float(screen[id(lab)][0]) for lab in row], [lab.width for lab in row], 0.14, body.x0 + 0.05, body.x1 - 0.05)
                for lab, x in zip(row, xs):
                    lab.put_screen(np.array([x, edge, 0.0]), s, cam)

    def _sides(self, made: list["_CellLabel"], axis: int, middle: float) -> dict[int, list["_CellLabel"]]:
        """The labels of each side of the cell along ``axis``, balanced: when one side has more
        than one label more than the other, the ones whose things lie nearest the middle cross."""
        sides: dict[int, list[_CellLabel]] = {-1: [], 1: []}
        for lab in made:
            sides[lab.choose_side(middle, axis)].append(lab)
        while abs(len(sides[1]) - len(sides[-1])) > 1:
            full = 1 if len(sides[1]) > len(sides[-1]) else -1
            mover = min(sides[full], key=lambda lab: abs(float(self.to_scene(lab.thing.center)[axis]) - middle))
            sides[full].remove(mover)
            mover.set_side(-full, axis)
            sides[-full].append(mover)
        return sides

    def _columns(self, made: list["_CellLabel"], cell_box: tuple[float, float, float, float]) -> bool:
        """Labels in a column at each side of the cell; ``False`` when a column is too tall."""
        sides = self._sides(made, 0, (cell_box[0] + cell_box[2]) / 2)
        bar_room = BAR_ROOM if self.params.scale_bar else 0.0
        if any(sum(lab.height + 0.06 for lab in labs) > self.body.height - (bar_room if side < 0 else 0.0) for side, labs in sides.items()):
            return False
        for side, labs in sides.items():
            edge = cell_box[0] - LABEL_GAP * 2 if side < 0 else cell_box[2] + LABEL_GAP * 2
            lo = self.body.y0 + (bar_room if side < 0 else 0.0)
            ys = _spread([lab.anchor[1] for lab in labs], [lab.height for lab in labs], 0.06, lo, self.body.y1)
            for lab, y in zip(labs, ys):
                x = edge + side * lab.width / 2
                x = min(max(x, self.body.x0 + lab.width / 2), self.body.x1 - lab.width / 2)   # over the cell's edge when it fills the body
                lab.put(np.array([x, y, 0.0]))
        return True

    def _rows(self, made: list["_CellLabel"], cell_box: tuple[float, float, float, float]) -> bool:
        """Labels in rows above and below the cell (as many rows as they need, those of a thing
        further out further out); ``False`` when they do not fit."""
        sides = self._sides(made, 1, (cell_box[1] + cell_box[3]) / 2)
        bar = BAR_WIDTH if self.params.scale_bar else 0.0
        plans = []
        for side, labs in sides.items():
            room = self.body.x1 - self.body.x0 - (bar if side < 0 else 0.0)
            labs.sort(key=lambda lab: lab.anchor[0])
            count = max(1, math.ceil(sum(lab.width + 0.14 for lab in labs) / room)) if labs else 0
            rows = [labs[k::count] for k in range(count)]
            while any(sum(lab.width + 0.14 for lab in row) > room for row in rows):
                count += 1
                if count > len(labs):
                    return False
                rows = [labs[k::count] for k in range(count)]
            tall = max((lab.height for lab in labs), default=0.0)
            space = cell_box[1] - self.body.y0 if side < 0 else self.body.y1 - cell_box[3]
            if count * (tall + 0.1) + LABEL_GAP * 2 > space:
                return False
            plans.append((side, rows, tall))
        for side, rows, tall in plans:
            for k, row in enumerate(rows):
                edge = (cell_box[1] if side < 0 else cell_box[3]) + side * (LABEL_GAP * 2 + k * (tall + 0.1))
                xs = _spread([lab.anchor[0] for lab in row], [lab.width for lab in row], 0.14, self.body.x0 + (bar if side < 0 else 0.0), self.body.x1)
                for lab, x in zip(row, xs):
                    lab.put(np.array([x, edge + side * tall / 2, 0.0]))
        return True

    # ----- actions --------------------------------------------------------------------------

    def cell_zoom(self, view: CellView) -> list[Animation]:
        """The camera moving to ``view`` (zoom at an even pace on a log scale)."""
        return self.cell_camera(*self.view_camera(view))

    def cell_camera(self, width: float, center: np.ndarray) -> list[Animation]:
        """The camera moving to ``width`` and ``center`` (none when it is there)."""
        frame = self.camera.frame
        if abs(frame.width - width) < 1e-9 and np.allclose(frame.get_center(), center, atol=1e-9):
            return []
        return [CellZoom(self, width, center)]

    def layout_keys(self, beat_id: str | None) -> dict[str, Any]:
        """What the layout dump adds to a still: ``cell`` with the view (µm across the body,
        pixels per µm), the scale bar's text and the level-of-detail weights (lint, Step 209)."""
        if not hasattr(self, "drawing"):
            return {}
        _s, px_per_um, span = self.screen_scale()
        weights = self.drawing.weights(px_per_um, span)
        return {"cell": {"span_um": round(span, 6), "px_per_um": round(px_per_um, 4), "scale_bar": cell_scale_bar(span)[1] if self.params.scale_bar else None,
                         "lod": {k: round(v, 3) for k, v in weights.items()}}}


def _check_target(world: CellWorld, name: str, where: str) -> None:
    names = ["cell", "tissue", *(e.id for e in world.entries if e.owner is None)]
    if name not in names:
        raise VidgenError(f"{where}: '{name}' is not an object of this cell{did_you_mean(name, names)}")


class CellPart:
    """A part of the cell itself to label (its wall, outer membrane, capsule): what a label
    needs of a placed thing."""

    def __init__(self, shape: Any) -> None:
        self.footprint = (shape,)
        self.center = shape.center()
        x0, y0, x1, y1 = shape.bounds()
        self.size = max(x1 - x0, y1 - y0)


class CellZoom(Animation):
    """The camera to ``width`` and ``center`` along :func:`cell_zoom_path`: an even pace on a
    log scale (a 100x zoom does not rush its last part), zooming out on the way between far
    places."""

    def __init__(self, scene: NarratedScene, width: float, center: np.ndarray, **kwargs: Any) -> None:
        frame = scene.camera.frame
        super().__init__(frame, **kwargs)
        self.frame, self.scene = frame, scene
        self.w0, self.c0 = float(frame.width), np.array(frame.get_center())
        self.w1, self.c1 = float(width), np.array(center, dtype=float)

    def begin(self) -> None:
        self.w0, self.c0 = float(self.frame.width), np.array(self.frame.get_center())
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        (x, y), w = cell_zoom_path((self.c0[0], self.c0[1]), self.w0, (self.c1[0], self.c1[1]), self.w1, alpha)
        self.frame.width = w
        self.frame.move_to([x, y, 0.0])
        self.scene.on_camera()      # also when the runner finishes the move without drawing a frame


_LABEL_IDS = iter(range(10 ** 9))


class _CellLabel:
    """A label of a cell scene: its text on a plate, pinned beside the thing it names (its size
    kept on screen) with a leader line from the thing's outline (or ``anchor``) to the plate's
    nearest edge. Its opacity is a level-of-detail piece of the drawing (feature ``@label<n>``),
    so a dim or highlight of its target is kept as the camera moves."""

    def __init__(self, scene: Cell, entry_id: str | None, words: Mobject, members: list[Any], anchor: np.ndarray | None = None) -> None:
        self.scene, self.entry_id = scene, entry_id
        plate = RoundedRectangle(width=words.width + 0.16, height=words.height + 0.1, corner_radius=0.06, stroke_width=0,
                                 fill_color=scene.theme.background, fill_opacity=PLATE_OPACITY)
        words.move_to(plate.get_center())
        self.plate, self.words = plate, words
        self.box = VGroup(plate, words)
        self.leader = Line(ORIGIN, RIGHT * 0.1, stroke_width=LEADER_WIDTH, color=scene.theme.color("dim")).set_z_index(OVERLAY_Z - 1)
        self.group = VGroup(self.leader, self.box)
        self.members = members
        self.thing = members[0] if members else None
        self.size = self.thing.size if self.thing is not None else 1.0
        self.width, self.height = float(self.box.width), float(self.box.height)
        self.anchor = anchor if anchor is not None else scene.to_scene(self.thing.center)
        self.offset = np.zeros(3)
        self.applied = 1.0
        self._stash: list[tuple[Mobject, np.ndarray]] | None = None
        n = next(_LABEL_IDS)
        self.feature, self.lead = f"@label{n}", f"@lead{n}"
        lod = scene.drawing.lod
        px = LEADER_WIDTH * scene.ref_pixels / 100
        lod.add(plate, self.feature, PLATE_OPACITY, 0.0, 0.0, None, keep=True)
        lod.add(words, self.feature, 1.0, 0.0, 0.0, None, keep=True)
        lod.add(self.leader, f"{self.feature}&{self.lead}", 0.0, 1.0, px, None, keep=True)
        self.box.set_z_index(OVERLAY_Z)

    def _outline(self, thing: Any) -> list[np.ndarray]:
        if getattr(thing, "option", lambda name: None)("base") is not None:     # a flagellum or pilus: near the cell
            line = thing.footprint[0]
            return [self.scene.to_scene(line.at(s)[0]) for s in np.linspace(0.0, min(line.length, 0.5), 12)]
        return [self.scene.to_scene(q) for shape in thing.footprint for q in shape.outline(48)]

    def choose_side(self, middle: float, axis: int) -> int:
        """Which side of the cell (``-1`` left / below, ``1`` right / above along ``axis``) the label
        goes to: that of the member furthest from the cell's middle; the anchor is its outline's
        point furthest that way."""
        member = max(self.members[:60], key=lambda m: abs(float(self.scene.to_scene(m.center)[axis]) - middle))
        side = 1 if float(self.scene.to_scene(member.center)[axis]) >= middle else -1
        self.set_side(side, axis)
        return side

    def set_side(self, side: int, axis: int) -> None:
        """Anchor on the member furthest towards ``side`` along ``axis``, at its outline's point
        furthest that way."""
        self.thing = max(self.members[:60], key=lambda m: side * float(self.scene.to_scene(m.center)[axis]))
        self.anchor = max(self._outline(self.thing), key=lambda q: side * float(q[axis]))

    def beside(self) -> None:
        """Next to the thing, away from the cell's middle (when the body has no room round it)."""
        middle = self.scene.to_scene((self.scene.world.cell.center()))
        center = self.scene.to_scene(self.thing.center)
        d = center - middle
        d = d / float(np.linalg.norm(d)) if float(np.linalg.norm(d)) > 1e-9 else np.array([1.0, 0.0, 0.0])
        outline = self._outline(self.thing)
        self.anchor = max(outline, key=lambda q: float(np.dot(q - center, d)))
        self.put(self.anchor + d * (LABEL_GAP + abs(d[0]) * self.width / 2 + abs(d[1]) * self.height / 2))

    def put(self, center: np.ndarray) -> None:
        """Place the plate's middle at ``center`` (unzoomed): it keeps that offset from the
        anchor on screen at any zoom."""
        self.box.move_to(center)
        self.offset = np.array(center, dtype=float) - self.anchor

    def put_screen(self, screen: np.ndarray, s: float, cam: np.ndarray) -> None:
        """Place the plate's middle at ``screen`` (a point of the unzoomed frame) when the camera
        is at scale ``s`` round ``cam``."""
        self.offset = (cam + screen * s - self.anchor) / s

    def _hide(self, hidden: bool) -> None:
        """Take its outlines away while it is not seen (Manim draws a transparent outline at
        full cost each frame), and give them back."""
        if hidden == (self._stash is not None):
            return
        if hidden:
            self._stash = [(m, m.points.copy()) for m in self.group.get_family() if len(m.points)]
            for m, _ in self._stash:
                m.clear_points()
        else:
            for m, points in self._stash or []:
                m.set_points(points)
            self._stash = None

    def show(self, weight: float, s: float, center: np.ndarray) -> dict[str, float]:
        """Its size and place (kept in the body, under the title) with the camera at scale ``s``
        round ``center``, its leader; the weights of its opacity features (``weight``)."""
        self._hide(weight <= 0.0)
        if weight <= 0.0:
            return {self.feature: 0.0, self.lead: 0.0}
        if abs(s / self.applied - 1) > 1e-9:
            self.box.scale(s / self.applied)
            self.applied = s
        body = self.scene.body
        screen = (self.anchor + self.offset * s - center) / s
        screen[0] = min(max(screen[0], body.x0 + self.width / 2), body.x1 - self.width / 2)
        screen[1] = min(max(screen[1], body.y0 + self.height / 2), body.y1 - self.height / 2)
        middle = center + screen * s
        self.box.move_to(middle)
        half = np.array([self.width / 2 * s, self.height / 2 * s, 0.0])
        end = np.clip(self.anchor, middle - half, middle + half)
        long = float(np.linalg.norm(end - self.anchor)) > 0.06 * s
        if long:
            self.leader.put_start_and_end_on(self.anchor, end)
        return {self.feature: weight, self.lead: 1.0 if long else 0.0}


def smooth_step(value: float, lo: float, hi: float) -> float:
    """0 below ``lo``, 1 above ``hi``, smooth between."""
    t = min(max((value - lo) / (hi - lo), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _bar_lengths(low_span: float, high_span: float) -> list[float]:
    """Every 1-2-5 scale-bar length (µm) of views spanning ``low_span`` to ``high_span`` µm."""
    first, last = cell_scale_bar(low_span)[0], cell_scale_bar(high_span)[0]
    out = []
    decade = 10.0 ** math.floor(math.log10(first) + 1e-9)
    while decade <= last * (1 + 1e-9):
        out += [step * decade for step in (1.0, 2.0, 5.0) if first * (1 - 1e-9) <= step * decade <= last * (1 + 1e-9)]
        decade *= 10.0
    return out


def _spread(values: list[float], sizes: list[float], gap: float, lo: float, hi: float) -> list[float]:
    """Positions near ``values`` (in any order) for items of ``sizes`` along one line, at least
    ``gap`` apart, kept within ``lo`` .. ``hi`` when they fit."""
    order = sorted(range(len(values)), key=lambda k: values[k])
    out = {}
    previous = None
    for k in order:
        v = values[k]
        if previous is not None:
            v = max(v, out[previous] + (sizes[previous] + sizes[k]) / 2 + gap)
        out[k] = v
        previous = k
    if order:
        first, last = order[0], order[-1]
        low = out[first] - sizes[first] / 2
        high = out[last] + sizes[last] / 2
        shift = 0.0
        if high > hi:
            shift = hi - high
        if low + shift < lo:
            shift = lo - low
        for k in out:
            out[k] += shift
    return [out[k] for k in range(len(values))]
