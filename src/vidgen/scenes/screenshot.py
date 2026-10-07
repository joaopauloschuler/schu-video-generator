"""``screenshot``: a picture of an app or a web page, optionally in a browser / window / phone
frame, with callouts (boxes, circles, arrows with labels, magnified insets, a spotlight) revealed
step by step, and an optional camera move onto a step's callouts.

Callout areas are ``[x, y, w, h]`` (or ``[x, y]`` for a point) from the image's top-left corner,
as fractions 0–1 of the image (``units: fraction``) or in the image's pixels (``units: px``).
The callouts are drawn by the public helpers of ``vidgen.api`` (``callout_box``, ...).
"""

import logging
from collections.abc import Callable
from typing import Any, ClassVar, Literal

import numpy as np
from PIL import Image as PILImage

from vidgen.api import *

from .actions import MoveCamera
from .image import check_image, load_image

log = logging.getLogger("vidgen.scenes")

CalloutKind = Literal["box", "circle", "arrow", "magnifier", "spotlight"]
KINDS: tuple[str, ...] = ("box", "circle", "arrow", "magnifier", "spotlight")
#: Kinds that need a rectangle ([x, y, w, h]); box, circle and arrow also take a point.
NEED_SIZE = ("magnifier", "spotlight")
#: Opacity of the marks of earlier steps with ``previous: dim``.
DIMMED = 0.35
#: Gap between the title and the picture.
TITLE_GAP = 0.45
#: Gap between the picture and its caption.
CAPTION_GAP = 0.3


class CalloutSpec(SceneParams):
    """A callout: ``{kind, area, label, ...}``, or the shorthand ``{box: [x, y, w, h], label: ...}``
    (the kind as the key of the area)."""

    kind: CalloutKind
    """box (frame around the area), circle (ellipse around it), arrow (a label pointing at it), magnifier (an enlarged inset of it), spotlight (everything else dimmed)."""
    area: list[float]
    """[x, y, w, h] from the image's top-left corner (fractions 0-1 of the image, or pixels with units: px), or [x, y] for a point (box, circle and arrow)."""
    label: str = ""
    """Short text on a plate in the callout's colour (beside the mark, or at the arrow's tail)."""
    color: ThemeColor | None = None
    """Colour of the mark and the label plate; default: the scene's color."""
    side: Literal["auto", "top", "bottom", "left", "right"] = "auto"
    """Where the label (or the magnifier's inset) goes relative to the area; auto: where there is room."""
    curved: bool = False
    """arrow: a curved arrow instead of a straight one."""
    zoom: float = Field(default=2.0, gt=1.0, le=8.0)
    """magnifier: how much larger the inset shows the area (less when it would not fit)."""

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, data: Any) -> Any:
        if isinstance(data, dict) and "kind" not in data:
            keys = [k for k in data if k in KINDS]
            if len(keys) == 1:
                rest = {k: v for k, v in data.items() if k != keys[0]}
                return {"kind": keys[0], "area": data[keys[0]], **rest}
        return data

    @model_validator(mode="after")
    def _check(self) -> "CalloutSpec":
        if len(self.area) not in (2, 4):
            raise ValueError(f"area is [x, y, w, h] or [x, y], got {len(self.area)} numbers")
        if any(v < 0 for v in self.area):
            raise ValueError("area: coordinates cannot be negative")
        if len(self.area) == 4 and (self.area[2] <= 0 or self.area[3] <= 0):
            raise ValueError("area: the width and height must be more than 0")
        if self.kind in NEED_SIZE and len(self.area) != 4:
            raise ValueError(f"a {self.kind} needs an area with a size: [x, y, w, h]")
        if self.curved and self.kind != "arrow":
            raise ValueError("curved: only arrows can be curved")
        if "zoom" in self.model_fields_set and self.kind != "magnifier":
            raise ValueError("zoom: only for a magnifier")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """The shorthand ``{KIND: area, ...}`` is also a callout (JSON Schema ``anyOf``)."""
        full = handler(core_schema)
        obj = handler.resolve_ref_schema(full)
        props = {k: v for k, v in obj["properties"].items() if k not in ("kind", "area")}
        shorts = [
            {"type": "object", "properties": {kind: obj["properties"]["area"], **props}, "required": [kind], "additionalProperties": False}
            for kind in KINDS
        ]
        return {"anyOf": [full, *shorts]}


class ScreenshotStep(SceneParams):
    """A step: ``{callouts, focus, previous}``, or just its callouts (a list), or one callout."""

    also_accepts = (list, CalloutSpec)

    callouts: list[CalloutSpec] = []
    """The callouts this step draws (in order; a spotlight is drawn under the others)."""
    focus: bool | float = False
    """Move the camera in on this step's callout areas (labels stay readable: they are built for the zoom); a number is the magnification (more than 1, up to 4), true: as close as fits, up to focus_scale."""
    previous: Literal["fade", "dim", "keep"] | None = None
    """What happens to the callouts of earlier steps when this one starts; default: the scene's previous."""

    @model_validator(mode="before")
    @classmethod
    def _from_callouts(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"callouts": data}
        if isinstance(data, dict) and ("kind" in data or any(k in KINDS for k in data)) and "callouts" not in data:
            return {"callouts": [data]}
        return data

    @field_validator("focus")
    @classmethod
    def _check_focus(cls, value: bool | float) -> bool | float:
        if not isinstance(value, bool) and not 1 < value <= 4:
            raise ValueError("a focus magnification is more than 1 and at most 4 (or true: as close as fits)")
        return value

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A list of callouts, or one callout, is also a step (JSON Schema ``anyOf``)."""
        full = handler(core_schema)
        callouts = handler.resolve_ref_schema(full)["properties"]["callouts"]
        return {"anyOf": [full, {"type": "array", "items": callouts["items"]}, callouts["items"]]}


def chrome_sizes(kind: str, width: float, bar: float) -> tuple[float, float, float, float]:
    """Space a frame adds around a picture ``width`` wide: (left/right, top, bottom, corner radius)."""
    if kind == "phone":
        return 0.05 * width, 0.12 * width, 0.1 * width, 0.1 * width
    if kind in ("browser", "window"):
        return 0.0, bar, 0.0, 0.1
    return 0.0, 0.0, 0.0, 0.0


@scene("screenshot")
class Screenshot(NarratedScene):
    """Beat 1 shows the picture (in its frame) and then step 1's callouts; step *i* (an entry
    of ``steps``) draws its callouts at beat *i*, after the earlier steps' callouts fade
    (``previous: fade``), dim (``dim``: marks faint, labels gone) or stay (``keep``). A step
    with ``focus`` moves the camera in on its callouts' areas (the next step without it moves
    back). More steps than beats are spread evenly; extra beats hold.

    Action targets: ``title``, ``image`` (the picture with its frame), ``caption``,
    ``callout<N>`` (numbered over all steps), ``callout:<label>``, ``step<N>`` (a step's callouts).
    """

    outro = 0.5
    target_patterns = ("title", "image", "caption", "callout<N>", "callout:<label>", "step<N>")
    #: Target name of the picture (with its frame).
    picture_name: ClassVar[str] = "image"
    #: The caption under the picture (with its plate in ``video_clip``), set by ``construct``.
    _caption: Mobject | None = None

    class Params(SceneParams):
        path: str
        """Image file relative to the project folder, e.g. assets/app.png."""
        title: str = ""
        """Heading above the picture."""
        caption: str = ""
        """Line under the picture."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "text"
        """Caption colour."""
        steps: list[ScreenshotStep] = []
        """Step i at beat i: {callouts, focus, previous}, a list of callouts, or one callout."""
        frame: Literal["none", "browser", "window", "phone"] = "none"
        """Draw the picture in a frame: browser (title bar with an address field), window (title bar), phone (rounded body), or none."""
        url: str = ""
        """browser: the text of the address field."""
        units: Literal["fraction", "px"] = "fraction"
        """Callout areas in fractions of the image (0-1) or in its pixels."""
        color: ThemeColor = "highlight"
        """Default colour of the callouts and their label plates."""
        label_size: ThemeSize = "caption"
        """Size of the callout labels (never below the readable size)."""
        previous: Literal["fade", "dim", "keep"] = "fade"
        """What happens to the callouts of a step when the next one starts: fade (go), dim (marks faint, labels gone), keep (stay)."""
        focus_scale: float = Field(default=2.0, gt=1.0, le=4.0)
        """Largest magnification of focus: true."""
        #: What callout areas are fractions of (in messages).
        picture_word: ClassVar[str] = "image"

        @model_validator(mode="after")
        def _fractions(self) -> SceneParams:
            if self.units != "fraction":
                return self
            for k, step in enumerate(self.steps):
                for j, c in enumerate(step.callouts):
                    a = c.area
                    if any(v > 1 for v in a) or (len(a) == 4 and (a[0] + a[2] > 1.0001 or a[1] + a[3] > 1.0001)):
                        raise ValueError(f"steps[{k}].callouts[{j}].area: {a} is not inside the {self.picture_word} (fractions 0-1; use units: px for pixels)")
            return self

        def callouts(self) -> list[tuple[int, CalloutSpec]]:
            """Every callout with the index of its step, in order (``callout<N>`` numbering)."""
            return [(k, c) for k, step in enumerate(self.steps) for c in step.callouts]

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``image``, ``caption`` (if any), ``callout<N>`` (+
        ``callout:<label>``) per callout and ``step<N>`` per step with callouts."""
        names = (["title"] if params.title else []) + [cls.picture_name] + (["caption"] if params.caption else [])
        for n, (_, c) in enumerate(params.callouts(), start=1):
            names += [f"callout{n}"] + ([f"callout:{c.label}"] if c.label.strip() else [])
        return names + [f"step{k + 1}" for k, step in enumerate(params.steps) if step.callouts]

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super().validate_project(params, project) + check_image(project, params.path, "path")
        if problems or params.units != "px":
            return problems
        with PILImage.open(project.root / params.path) as im:
            w, h = im.size
        for k, step in enumerate(params.steps):
            for j, c in enumerate(step.callouts):
                a = c.area
                if a[0] > w or a[1] > h or (len(a) == 4 and (a[0] + a[2] > w or a[1] + a[3] > h)):
                    problems.append(f"steps[{k}].callouts[{j}].area: {a} is not inside the image ({w} x {h} px)")
        return problems

    # ----- construct ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        problems = check_image(self.project, p.path, "path")
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        self._body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size="heading", area=self.safe_area)   # header band, 1.3x in a vertical frame
            self._body = self._body.below(title, gap=TITLE_GAP)
        room = self._body
        caption = None
        if p.caption:
            caption = fit_text(p.caption, room.width, room.height * 0.2, size=p.caption_size, color=p.caption_color)
            room = room.above(room.y0 + caption.height, gap=CAPTION_GAP)
        self._img = load_image(self.project.asset(p.path))
        self._picture = self._layout(room)
        if caption is not None:  # under the picture; callout labels keep off it
            caption.next_to(self._picture, DOWN, buff=CAPTION_GAP).set_x(self._img.get_x())
            self._keep_off = self._keep_off + [callout_area(caption).inset(-0.1)]
        self._caption = caption
        self._cameras = [self._camera(k) for k in range(len(p.steps))]
        self._callouts = self._build()
        self._register(title)
        if caption is not None:
            self.target("caption", caption, entrance=lambda: [FadeIn(caption, shift=UP * 0.1)])
        self._camera_at: tuple[float, tuple[float, float]] | None = None

        def intro() -> list[Animation]:
            anims = self.entrance(self.picture_name) + (self.entrance("title") if title is not None else [])
            return anims + (self.entrance("caption") if caption is not None else [])

        steps: list[Callable[[], list[Animation]]] = [(lambda k=k: self._step(k)) for k in range(len(p.steps))]
        plan = distribute(len(steps), len(self.beats))
        for i, d in self.timeline():
            self.play_steps(d, ([intro] if i == 0 else []) + [steps[k] for k in plan[i]], fraction=0.6, cap=1.5)
        self.finish()

    # ----- layout ------------------------------------------------------------------------------

    def _layout(self, body: Region, fill: bool = False) -> Mobject:
        """Fit the picture (and its frame) into ``body`` with room around it for labels; returns
        the picture's group (frame behind, image, frame outline, title bar parts). ``fill``: the
        picture takes all the room (its aspect ratio changes; the caller crops it to match)."""
        p = self.params
        img = self._img
        aspect = img.width / img.height
        if self.is_portrait:
            room = body.inset(0.0, body.height * 0.1)
        else:
            room = body.inset(0.25, 0.1)
        url = None
        bar = 0.0
        width = room.width
        for _ in range(3):  # the bar's height depends on the width, and the width on the bar
            if p.frame in ("browser", "window"):
                bar = min(0.6, max(0.4, 0.065 * width))
                if p.frame == "browser" and p.url.strip():
                    url = self.text(p.url.strip(), size=readable_size(), color="dim")
                    bar = max(bar, url.height / 0.32)
            side, top, bottom, _ = chrome_sizes(p.frame, width, bar)
            k_side, k_vert = (0.1, 0.22) if p.frame == "phone" else (0.0, 0.0)
            fixed = 0.0 if p.frame == "phone" else top + bottom
            if fill:
                widest = room.width / (1 + k_side)
                aspect = widest / max(room.height - fixed - k_vert * widest, 0.1)
            width = min(room.width / (1 + k_side), (room.height - fixed) / (1 / aspect + k_vert))
        side, top, bottom, radius = chrome_sizes(p.frame, width, bar)
        height = width / aspect
        total_h = height + top + bottom
        cx, cy = room.center[0], room.center[1]
        img.stretch_to_fit_width(width).stretch_to_fit_height(height)
        img.move_to([cx, cy + total_h / 2 - top - height / 2, 0])
        # labels keep off the frame's title bar (its address text) and the title
        self._keep_off = [Region(cx - width / 2, cy + total_h / 2 - top, cx + width / 2, cy + total_h / 2)] if top > 0 and p.frame != "phone" else []
        if p.frame == "none":
            return Group(img)
        surface, line = self.theme.color("surface"), self.theme.color("dim")
        outer = RoundedRectangle(width=width + 2 * side, height=total_h, corner_radius=radius).move_to([cx, cy, 0])
        back = outer.copy().set_fill(surface, opacity=1).set_stroke(width=0)
        edge = outer.copy().set_fill(opacity=0).set_stroke(line, width=1.5 if p.frame != "phone" else 2.5, opacity=0.8)
        extras: list[Mobject] = []
        y_top = cy + total_h / 2
        if p.frame == "phone":
            speaker = RoundedRectangle(width=0.22 * width, height=0.03 * width, corner_radius=0.015 * width)
            speaker.set_fill(line, opacity=0.7).set_stroke(width=0).move_to([cx, y_top - top / 2, 0])
            home = RoundedRectangle(width=0.3 * width, height=0.025 * width, corner_radius=0.0125 * width)
            home.set_fill(line, opacity=0.7).set_stroke(width=0).move_to([cx, cy - total_h / 2 + bottom / 2, 0])
            extras += [speaker, home]
        else:
            x0 = cx - width / 2
            dots = VGroup(*[
                Dot(radius=0.06, color=self.theme.color(token)).move_to([x0 + 0.3 + 0.22 * k, y_top - bar / 2, 0])
                for k, token in enumerate(("accent", "highlight", "tertiary"))
            ])
            extras.append(dots)
            if p.frame == "browser":
                left = x0 + 1.05
                field = RoundedRectangle(width=max(0.5, cx + width / 2 - 0.3 - left), height=bar * 0.56, corner_radius=bar * 0.2)
                field.set_fill(self.theme.background, opacity=1).set_stroke(width=0).move_to([left + field.width / 2, y_top - bar / 2, 0])
                extras.append(field)
                if url is not None:
                    if url.width > field.width - 0.4:
                        url = fit_text(p.url.strip(), field.width - 0.4, field.height, size=readable_size(), color="dim")
                    url.move_to([field.get_left()[0] + 0.2 + url.width / 2, field.get_center()[1], 0])
                    extras.append(url)
        return Group(back, img, edge, *extras)

    def _camera(self, k: int) -> tuple[float, tuple[float, float]] | None:
        """Camera (width, centre) of step ``k``'s focus, or ``None`` (the whole frame)."""
        p = self.params
        step = p.steps[k]
        if not step.focus or not step.callouts:
            return None
        areas = [self._area(c) for c in step.callouts]
        x0, x1 = min(a.x0 for a in areas), max(a.x1 for a in areas)
        y0, y1 = min(a.y0 for a in areas), max(a.y1 for a in areas)
        fw, fh = self.frame_width, self.frame_height
        limit = p.focus_scale if step.focus is True else float(step.focus)
        # room for the labels: the areas take at most half of the view each way
        m = min(limit, 0.5 * fw / max(x1 - x0, 1e-6), 0.5 * fh / max(y1 - y0, 1e-6))
        if m < 1.05:
            log.warning("scene '%s': step %d: the callouts already fill the frame; no focus", self.spec.id, k + 1)
            return None
        w, h = fw / m, fh / m
        x = float(np.clip((x0 + x1) / 2, (w - fw) / 2, (fw - w) / 2))
        y = float(np.clip((y0 + y1) / 2, (h - fh) / 2, (fh - h) / 2))
        return w, (x, y)

    def _spec_area(self, c: CalloutSpec) -> tuple[list[float], str]:
        """A callout's area as written to the callout helpers, with its units."""
        return c.area, self.params.units

    def _area(self, c: CalloutSpec) -> Region:
        area, units = self._spec_area(c)
        return callout_area(area, self._img, units=units)

    def _bounds(self, k: int) -> tuple[Region, float]:
        """Where step ``k``'s labels may go and the scale they are built at (1 / magnification)."""
        camera = self._cameras[k]
        if camera is None:
            return self._body, 1.0
        w, (x, y) = camera
        s = w / self.frame_width
        view = Region(x - w / 2 + self.margin_x * s, y - self.frame_height * s / 2 + self.margin_y * s,
                      x + w / 2 - self.margin_x * s, y + self.frame_height * s / 2 - self.margin_y * s)
        top = min(view.y1, self._body.y1)
        return Region(view.x0, view.y0, view.x1, max(top, view.y0 + 0.1)), s

    def _previous(self, k: int) -> str:
        return self.params.steps[k].previous or self.params.previous

    def _build(self) -> list[list[Callout]]:
        """Every step's callouts (spotlights first, so they lie under the others)."""
        p = self.params
        built: list[list[Callout]] = []
        kept: list[Region] = []
        for k, step in enumerate(p.steps):
            bounds, scale = self._bounds(k)
            if k > 0 and (self._previous(k) == "fade" or self._cameras[k] != self._cameras[k - 1]):
                kept = []
            areas = [self._area(c).inset(-0.05 * scale) for c in step.callouts]
            avoid = self._keep_off + kept + areas
            mine: list[Callout | None] = [None] * len(step.callouts)
            order = sorted(range(len(step.callouts)), key=lambda j: step.callouts[j].kind != "spotlight")
            for j in order:
                c = step.callouts[j]
                area, units = self._spec_area(c)
                options: dict[str, Any] = {
                    "units": units, "color": c.color or p.color, "label_size": p.label_size, "side": c.side,
                    "bounds": bounds, "avoid": avoid, "scale": scale, "theme": self.theme,
                }
                if c.kind == "magnifier":
                    made = callout_magnifier(area, c.label, image=self._img, zoom=c.zoom, **options)
                elif c.kind == "arrow":
                    made = callout_arrow(area, c.label, within=self._img, curved=c.curved, prefer_off=self._picture, **options)
                elif c.kind == "spotlight":
                    made = callout_spotlight(area, c.label, within=self._img, **options)
                else:
                    made = callout(c.kind, area, c.label, within=self._img, **options)
                made.set_z_index(1 if c.kind == "spotlight" else 2)  # over the picture; shades under any callout
                mine[j] = made
                avoid = avoid + [made.extent()]
            built.append([m for m in mine if m is not None])
            kept = kept + [m.extent() for m in built[-1] if m.kind != "spotlight"]
        return built

    # ----- targets -----------------------------------------------------------------------------

    def _register(self, title: Mobject | None) -> None:
        p = self.params
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title, shift=DOWN * 0.1)])
        self.target(self.picture_name, self._picture, entrance=self._picture_entrance)
        self._numbered: list[tuple[int, Callout]] = []
        for k, step in enumerate(p.steps):
            spec_order = list(step.callouts)
            made = self._callouts[k]
            # built in drawing order (spotlights first); number them in the written order
            by_spec = self._match(spec_order, made)
            for c, m in zip(spec_order, by_spec):
                self._numbered.append((k, m))
                names = [f"callout{len(self._numbered)}"] + ([f"callout:{c.label}"] if c.label.strip() else [])
                label = m.tag if getattr(m.tag, "is_label", False) else None
                on_fill = [(label.text, label.plate)] if label is not None else []   # dim / highlight keep it readable
                self.target(names, m, entrance=lambda k=k, m=m: self._callout_entrance(k, m), on_fill=on_fill)
            if made:
                self.target(f"step{k + 1}", Group(*made), entrance=lambda k=k: self._arrive(k))

    def _picture_entrance(self) -> list[Animation]:
        return [FadeIn(self._picture, scale=0.97)]

    @staticmethod
    def _match(specs: list[CalloutSpec], made: list[Callout]) -> list[Callout]:
        """``made`` (spotlights first) back in the order of ``specs``."""
        spots = [m for m in made if m.kind == "spotlight"]
        others = [m for m in made if m.kind != "spotlight"]
        return [spots.pop(0) if c.kind == "spotlight" else others.pop(0) for c in specs]

    def _callout_entrance(self, k: int, made: Callout) -> list[Animation]:
        """A callout alone; one of a focus step comes with its step (the camera, then all)."""
        if self._cameras[k] is not None and self._camera_at != self._cameras[k]:
            return self._arrive(k)
        return made.draw()

    # ----- animation ---------------------------------------------------------------------------

    def _step(self, k: int) -> list[Animation]:
        """Step ``k`` at its beat; nothing when an action revealed all its callouts already."""
        made = self._callouts[k]
        if made and all(self.on_screen_parts(m) for m in made):
            return []
        return self._arrive(k)

    def _arrive(self, k: int) -> list[Animation]:
        """Step ``k``: earlier callouts fade / dim / stay, the camera moves, the step's
        callouts are drawn (after the others moved, when they did)."""
        anims: list[Animation] = []
        for j, made in enumerate(self._callouts[:k]):
            # callouts built for another camera (a focus, or the whole frame) always leave
            mode = self._previous(k) if self._cameras[j] == self._cameras[k] else "fade"
            for m in made:
                anims += self._leave(m, mode)
        camera = self._cameras[k]
        if camera != self._camera_at:
            width, center = camera or (self.frame_width, (0.0, 0.0))
            anims.append(MoveCamera(self, width, np.array([*center, 0.0])))
            anims += self._caption_moves(camera)
            self._camera_at = camera
        start = 0.4 if anims else 0.0
        for m in self._callouts[k]:
            if not self.on_screen_parts(m):
                anims += m.draw(start)
        return anims

    def _caption_moves(self, camera: tuple[float, tuple[float, float]] | None) -> list[Animation]:
        """The caption leaves while the camera is in on a step (it would be enlarged under the
        picture) and comes back with the whole frame."""
        caption = self._caption
        if caption is None:
            return []
        shown = self.on_screen_parts(caption)
        if camera is not None:
            return [fade_out(part) for part in shown]
        return [] if shown else [FadeIn(caption, shift=UP * 0.1)]

    def _leave(self, made: Callout, mode: str) -> list[Animation]:
        """How an earlier step's callout makes way: fades out, or (``dim``) keeps its mark faint
        (labels, insets and shades go)."""
        if mode == "keep":
            return []
        shown = self.on_screen_parts(made)
        if not shown:
            return []
        faint = [made.mark] if made.kind in ("box", "circle", "arrow") else [made.steps[0]] if made.kind == "magnifier" else []
        anims: list[Animation] = []
        for part in shown:
            if mode == "dim" and any(part is f or part in f.get_family() for f in faint):
                anims.append(Transform(part, _faint(part.copy())))
            else:
                anims.append(FadeOut(part))
        return anims


def _faint(mob: Mobject) -> Mobject:
    """``mob`` with its strokes (and filled parts, such as an arrow's tip) at most :data:`DIMMED`
    opaque; transparent fills stay transparent."""
    for m in mob.family_members_with_points():
        m.set_stroke(opacity=min(m.get_stroke_opacity(), DIMMED))
        if m.get_fill_opacity() > 0:
            m.set_fill(opacity=min(m.get_fill_opacity(), DIMMED))
    return mob
