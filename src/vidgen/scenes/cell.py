"""``cell``: a cell in physical scale (DESIGN.md §95): its compartments, membranes and contents
drawn from the cell world (``vidgen.cellworld``: the model and its location rules, no manim)
by ``vidgen.cell_vector``, with a camera that zooms from a tissue to a single ribosome
(``zoom_to``, ``scenes/cell_actions.py``), level-of-detail switching as it goes, screen-sized
labels and an automatic scale bar."""

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
#: The scale bar's height (screen units) and its distance from the body's corner.
BAR_HEIGHT, BAR_MARGIN = 0.07, 0.15
#: Labels fade out as the camera zooms away from the start view: from this log zoom to this one.
LABEL_ZOOM = (math.log(1.2), math.log(1.6))
#: Labels, the title and the scale bar are drawn over the cell.
OVERLAY_Z = 50
#: Level of detail is measured in pixels of a frame whose shorter side is this many pixels, so
#: a preview shows the details the final video shows.
REF_PIXELS = 1080.0


def _length(value: Any, what: str) -> float | None:
    return None if value is None else parse_length(value, what)


class CellBody(SceneParams):
    """The cell: ``{kind, size, aspect}``; a kind alone (``animal``) is the cell."""

    also_accepts = (str,)

    kind: Literal["animal"] = "animal"
    """The kind of cell (animal; plant and bacterial cells come with the structure library)."""
    size: Length = 20.0
    """Its long axis: a number of µm or a length ('20 um'); a typical animal cell is 10–30 µm."""
    aspect: float = Field(1.25, ge=1.0, le=2.5)
    """Its long axis over its short axis (1: round)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"kind": data} if isinstance(data, str) else data

    @field_validator("size", mode="before")
    @classmethod
    def _size(cls, value: Any) -> float:
        return parse_length(value, "cell size")

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A kind alone is also a cell (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}


class CellObject(SceneParams):
    """Something in the cell: ``{kind, id, at, size, width, angle, in, on, count, label}`` plus
    options of some kinds; a kind alone (``mitochondrion``) is one of it, placed automatically."""

    also_accepts = (str,)

    kind: str
    """What it is: nucleus, nucleolus, rough_er, smooth_er, golgi, mitochondrion, lysosome, peroxisome, endosome, vesicle, centrosome, ribosome, proteasome, nuclear_pore."""
    id: str | None = None
    """Its name for actions and labels (default: the kind; an object with the id of a typical one replaces it)."""
    at: tuple[Length, Length] | None = None
    """Where its middle is: [x, y] in µm from the cell's centre (x right, y up), or lengths ['2 um', '-500 nm']; default: placed automatically."""
    size: Length | None = None
    """Its length (µm or '1.5 um'); default: a typical size of its kind."""
    width: Length | None = None
    """Its width for elongated kinds (a mitochondrion: about 0.5–1 µm)."""
    angle: float | None = None
    """Turn in degrees (a Golgi stack: the direction its cis face looks; default towards the nucleus)."""
    inside: str | None = Field(None, alias="in")
    """For complexes: the compartment they float in: cytosol (default), nucleoplasm, matrix, an object's id (its inside) or '<id>.<compartment>'."""
    on: str | None = None
    """For complexes: the object whose membrane they sit on (ribosomes: rough_er or the nucleus; nuclear pores: the nucleus)."""
    count: int = Field(1, ge=1, le=400)
    """How many, scattered where they may be (no at)."""
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
    tubules: int | None = Field(None, ge=1, le=12)
    """Smooth ER: how many tubules (default 6)."""
    pores: bool | None = None
    """Nucleus: draw the nuclear pores (default true)."""
    ribosomes: bool | None = None
    """Nucleus and rough ER: ribosomes on the cytosolic face (default true)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"kind": data} if isinstance(data, str) else data

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
                              self.sheets, self.span, self.side, self.cisternae, self.tubules, self.pores, self.ribosomes, where)


class CellViewSpec(SceneParams):
    """Where the camera starts: a level (``cell``) or ``{level, on, width}``."""

    also_accepts = (str,)

    level: CellLevel = "cell"
    """tissue (the cell among its neighbours), cell, organelle or complex (molecular)."""
    on: str | None = None
    """The object to centre on (organelle and complex levels; default the nucleus)."""
    width: Length | None = None
    """What the view spans across the frame's body, shorter side (e.g. '3 um'); default: the level's."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
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
    """A cell drawn in physical scale: a cross-section of an animal cell with its compartments
    (cytosol, nucleoplasm, ER and Golgi lumens, mitochondrial matrix and intermembrane space…),
    the membranes between them and what is in them, at textbook sizes (``contents: typical`` is
    the textbook cell; ``objects`` add or replace things). Every place is checked: a ribosome in
    the nucleoplasm or a mitochondrion inside the nucleus is refused with the reason. The camera
    is in µm: ``view`` sets the start level (tissue, cell, organelle, complex) and the
    ``zoom_to`` action moves between levels; details appear as they grow on screen (double
    membranes, cristae, nuclear pores, ribosome subunits, lipid bilayers). A scale bar and
    labels keep their size on screen.

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
        """The cell: 'animal' or {kind, size (µm or '20 um'), aspect}."""
        contents: Literal["typical", "none"] = "typical"
        """typical: the textbook cell (nucleus with nucleolus and pores, rough and smooth ER, Golgi, centrosome, 8 mitochondria, lysosomes, peroxisomes, vesicles, ribosomes); none: only the objects listed."""
        objects: list[CellObject] = Field(default_factory=list, max_length=60)
        """Things in the cell: a kind, or {kind, id, at, size, width, angle, in, on, count, label}; an id of a typical object replaces it."""
        view: CellViewSpec = Field(default_factory=CellViewSpec)
        """Where the camera starts: tissue, cell (default), organelle or complex, or {level, on, width}."""
        labels: bool = True
        """Name the structures (screen-sized; shown once a structure is large enough on screen)."""
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
            return CellSpec(self.cell.kind, float(self.cell.size), self.cell.aspect, self.contents, objects, self.seed)  # type: ignore[arg-type]

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
    def zoom_problem(cls, params: Any, name: str, level: str | None, width: float | None) -> str | None:
        """Why ``zoom_to`` cannot go to ``name`` (``None``: it can)."""
        if name in ("title", "scale_bar"):
            return f"zoom_to goes to the cell, the tissue or an object, not '{name}'"
        world = params.world()
        try:
            cell_level_view(world, level or cell_default_level(world, name), 16 / 9, name, width)
        except (VidgenError, KeyError) as error:
            return str(error)
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
        self.start = cell_level_view(self.world, p.view.level, aspect, p.view.on, p.view.width)
        self.unit = self.body_short / self.start.span
        self.aspect = aspect
        colors = CellColors(self.theme.background, self.theme.color("text"))
        self.drawing = CellDrawing(self.world, colors, self.unit, self.to_scene((0.0, 0.0)))
        self._pinned: list[list[Any]] = []
        self._labels: list[_CellLabel] = []
        self._camera_state: tuple[float, float, float] | None = None
        self._bar: Mobject | None = None
        if title is not None:
            plate = RoundedRectangle(width=title.width + 0.4, height=title.height + 0.2, corner_radius=0.08, stroke_width=0,
                                     fill_color=self.theme.background, fill_opacity=PLATE_OPACITY).move_to(title.get_center())
            title = VGroup(plate, title)    # readable over the tissue when the camera zooms out
            self.pin(title, title.get_center())
        bar = self._scale_bar() if p.scale_bar else None
        labels = self._make_labels() if p.labels else {}
        self._place_view(self.start)
        self.on_camera()

        chain = ChainedTargets(self)
        base: list[Target] = []
        if title is not None:
            base.append(chain.add("title", title, lambda: [FadeIn(title)], []))
        tissue = self.drawing.tissue
        base.append(chain.add("tissue", tissue, lambda: [FadeIn(tissue)], list(base)))
        cell_group = VGroup(self.drawing.cell)
        base.append(chain.add("cell", cell_group, lambda: [FadeIn(cell_group)], list(base)))
        if bar is not None:
            base.append(chain.add("scale_bar", bar, lambda: [FadeIn(bar)], list(base)))
        items = []
        for entry_id in self.drawing.order:
            group = VGroup(self.drawing.groups[entry_id], *labels.get(entry_id, []))
            items.append(chain.add(entry_id, group, lambda g=group: [FadeIn(g)], list(base)))
        self.add_camera_listener(self.on_camera)
        chain.reveal(base, items, p.reveal == "all")
        self.finish()

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
        """Every frame the camera moved: pinned things keep their place and size on screen, the
        drawing its level of detail, labels show by their structure's size and whether it is in
        view, the scale bar its length."""
        frame = self.camera.frame
        center = np.array(frame.get_center())
        state = (round(float(frame.width), 9), round(float(center[0]), 9), round(float(center[1]), 9))
        if state == self._camera_state:
            return
        self._camera_state = state
        s, px_per_um, span = self.screen_scale()
        stroke_unit = s * 100 / self.ref_pixels           # Manim stroke width per (1080-p) pixel now
        self.drawing.update(px_per_um, span, stroke_unit)
        if self._bar is not None:
            self._update_bar(span, s, center)
        for item in self._pinned:
            mob, screen, world, offset, applied = item
            if abs(s / applied - 1) > 1e-9:
                mob.scale(s / applied)
                item[4] = s
            mob.move_to(center + screen * s if screen is not None else world + offset * s)
        # labels are laid out for the start view: they give way to the tissue and fade out as the
        # camera zooms away from that view (and back in as it returns)
        crowd = (1.0 - self.drawing.weights(px_per_um, span)["neighbours"]) * (1.0 - smooth_step(abs(math.log(s)), *LABEL_ZOOM))
        half_w, half_h = float(frame.width) / 2, float(frame.height) / 2
        for label in self._labels:
            anchor = label.anchor
            seen = abs(anchor[0] - center[0]) < half_w * 0.97 and abs(anchor[1] - center[1]) < half_h * 0.97
            weight = cell_label_weight(label.size, px_per_um) * crowd if seen else 0.0
            label.show(weight, s, center)

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
        # during a zoom would not be drawn (and the one swapped out would stay)
        spans = [self.start.span] + [self._zoom_span(use) for use in self.action_uses("zoom_to")]
        self._bar_texts: dict[str, Mobject] = {}
        for length in _bar_lengths(min(spans) / 4, max(spans) * 2):
            text = self.text(format_length(length), size=self.params.label_size, color="text").set_z_index(OVERLAY_Z + 1)
            text.set_fill(opacity=0.0)
            text.applied = 1.0  # type: ignore[attr-defined]
            self._bar_texts[format_length(length)] = text
        self._bar_label = VGroup(*self._bar_texts.values()).set_z_index(OVERLAY_Z + 1)
        self._bar_corner = np.array([self.body.x0 + BAR_MARGIN, self.body.y0 + BAR_MARGIN, 0.0])
        return VGroup(self._bar_plate, self._bar, self._bar_label)

    def _zoom_span(self, use: Any) -> float:
        """The span of the view a ``zoom_to`` action goes to (µm)."""
        try:
            return self.cell_view_for(use.config.targets()[0], use.options.level, use.options.width).span
        except (VidgenError, KeyError, IndexError):
            return self.start.span

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
        return kind.plural if len(entry.keys) > 1 else kind.label

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
                made.append(_CellLabel(self, entry_id, words))
        if not made:
            return {}
        x0, y0, x1, y1 = self.world.cell.bounds()
        a, b = self.to_scene((x0, y0)), self.to_scene((x1, y1))
        cell_box = (float(a[0]), float(a[1]), float(b[0]), float(b[1]))
        widest = max(lab.width for lab in made)
        columns = cell_box[0] - self.body.x0 >= widest + 0.3 and self.body.x1 - cell_box[2] >= widest + 0.3
        if not (columns and self._columns(made, cell_box)) and not self._rows(made, cell_box):
            for lab in made:
                lab.beside()
        self._labels = made
        return {lab.entry_id: [lab.group] for lab in made}

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
        if any(sum(lab.height + 0.1 for lab in labs) > self.body.height for labs in sides.values()):
            return False
        for side, labs in sides.items():
            edge = cell_box[0] - LABEL_GAP * 2 if side < 0 else cell_box[2] + LABEL_GAP * 2
            ys = _spread([lab.anchor[1] for lab in labs], [lab.height for lab in labs], 0.1, self.body.y0, self.body.y1)
            for lab, y in zip(labs, ys):
                lab.put(np.array([edge + side * lab.width / 2, y, 0.0]))
        return True

    def _rows(self, made: list["_CellLabel"], cell_box: tuple[float, float, float, float]) -> bool:
        """Labels in rows above and below the cell (as many rows as they need, those of a thing
        further out further out); ``False`` when they do not fit."""
        sides = self._sides(made, 1, (cell_box[1] + cell_box[3]) / 2)
        room = self.body.x1 - self.body.x0
        plans = []
        for side, labs in sides.items():
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
                xs = _spread([lab.anchor[0] for lab in row], [lab.width for lab in row], 0.14, self.body.x0, self.body.x1)
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


class _CellLabel:
    """A label of a cell scene: its text on a plate, pinned beside the thing it names (its size
    kept on screen) with a leader line from the thing's outline to the plate's nearest edge."""

    def __init__(self, scene: Cell, entry_id: str, words: Mobject) -> None:
        self.scene, self.entry_id = scene, entry_id
        plate = RoundedRectangle(width=words.width + 0.16, height=words.height + 0.1, corner_radius=0.06, stroke_width=0,
                                 fill_color=scene.theme.background, fill_opacity=PLATE_OPACITY)
        words.move_to(plate.get_center())
        self.plate, self.words = plate, words
        self.box = VGroup(plate, words)
        self.leader = Line(ORIGIN, RIGHT * 0.1, stroke_width=LEADER_WIDTH, color=scene.theme.color("dim")).set_z_index(OVERLAY_Z - 1)
        self.group = VGroup(self.leader, self.box)
        self.members = scene.world.members(entry_id)
        self.thing = self.members[0]
        self.size = self.thing.size
        self.width, self.height = float(self.box.width), float(self.box.height)
        self.anchor = scene.to_scene(self.thing.center)
        self.offset = np.zeros(3)

    def _outline(self, thing: Any) -> list[np.ndarray]:
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
        middle = self.scene.to_scene((self.scene.world.cell.cx, self.scene.world.cell.cy))
        center = self.scene.to_scene(self.thing.center)
        d = center - middle
        d = d / float(np.linalg.norm(d)) if float(np.linalg.norm(d)) > 1e-9 else np.array([1.0, 0.0, 0.0])
        outline = self._outline(self.thing)
        self.anchor = max(outline, key=lambda q: float(np.dot(q - center, d)))
        self.put(self.anchor + d * (LABEL_GAP + abs(d[0]) * self.width / 2 + abs(d[1]) * self.height / 2))

    def put(self, center: np.ndarray) -> None:
        """Place the plate's middle at ``center`` (unzoomed): it keeps that offset from the
        anchor on screen at any zoom."""
        self.box.move_to(center).set_z_index(OVERLAY_Z)
        self.offset = np.array(center, dtype=float) - self.anchor
        self.applied = 1.0

    def show(self, weight: float, s: float, center: np.ndarray) -> None:
        """Its size, place (kept in the body, under the title), opacity (``weight``) and leader
        with the camera at scale ``s`` round ``center``."""
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
        self.leader.set_stroke(width=LEADER_WIDTH * s, opacity=weight if long else 0.0)
        self.plate.set_fill(opacity=PLATE_OPACITY * weight)
        self.words.set_fill(opacity=weight)


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
