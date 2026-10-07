"""Built-in per-beat actions: ``reveal``, ``dim``, ``highlight``, ``zoom`` and ``transform``
(DESIGN.md §26, §27).

Written against ``vidgen.api`` only, like project actions. ``dim`` and ``highlight`` change only
opacity resp. colour, so they combine and undo (``until:``) independently; both also work on
images (their pixels). ``zoom`` moves the scene's camera and brings it back by the end of the
beat; ``transform`` morphs targets into another target that is not on screen yet.
"""

import logging
from collections.abc import Callable
from typing import Any, Literal

import numpy as np

from vidgen.api import *

log = logging.getLogger("vidgen.actions")

Paint = Callable[[Any, np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]
PaintImage = Callable[[Any, np.ndarray], np.ndarray]


def _is_image(m: Mobject) -> bool:
    return isinstance(m, ImageMobject)


class Repaint(Animation):
    """Animate the fill/stroke RGBA of every vectorized mobject in ``mobject``'s family to
    ``paint(member, fill, stroke) -> (fill, stroke)``, and the pixels of every image to
    ``paint_image(member, rgba) -> rgba`` (float arrays, 0-255), computed from the arrays when it
    begins. Points are untouched, so it combines with anything that moves the mobject later."""

    def __init__(self, mobject: Mobject, paint: Paint, paint_image: PaintImage | None = None, **kwargs: Any) -> None:
        super().__init__(mobject, **kwargs)
        self.paint = paint
        self.paint_image = paint_image
        self._members: list[VMobject] = []
        self._start: list[tuple[np.ndarray, np.ndarray]] = []
        self._end: list[tuple[np.ndarray, np.ndarray]] = []
        self._images: list[tuple[Mobject, np.ndarray, np.ndarray]] = []

    def create_starting_mobject(self) -> Mobject:
        """No copy (the base class copies the mobject; colours are read in :meth:`begin`)."""
        return Mobject()

    def begin(self) -> None:
        """Read the start colours and compute the end colours."""
        family = self.mobject.get_family()
        self._members = [m for m in family if isinstance(m, VMobject)]
        self._start = [(m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in self._members]
        self._end = [self.paint(m, f.copy(), s.copy()) for m, (f, s) in zip(self._members, self._start)]
        if self.paint_image is not None:
            for m in family:
                if _is_image(m):
                    start = m.pixel_array.astype(float)
                    self._images.append((m, start, self.paint_image(m, start.copy())))
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        """Blend every member's colours."""
        a = self.rate_func(alpha)
        for m, (f0, s0), (f1, s1) in zip(self._members, self._start, self._end):
            m.fill_rgbas = f0 + (f1 - f0) * a
            m.stroke_rgbas = s0 + (s1 - s0) * a
        for m, p0, p1 in self._images:
            m.pixel_array = np.clip(np.rint(p0 + (p1 - p0) * a), 0, 255).astype(np.uint8)


def _fit(saved: np.ndarray, current: np.ndarray) -> np.ndarray:
    """``saved`` with the shape of ``current`` (a member rebuilt meanwhile: repeat its first row)."""
    return saved if saved.shape == current.shape else np.resize(saved[:1], current.shape)


def _scale_alpha(alpha: np.ndarray, limit: float, raise_to: bool = False) -> None:
    """Scale ``alpha`` (in place) so its largest value is at most ``limit`` (``raise_to``: exactly
    ``limit``, also upwards). Ratios between the values (gradients, transparent pixels) stay."""
    top = float(alpha.max()) if alpha.size else 0.0
    if top > 1e-9 and (top > limit or raise_to):
        alpha *= limit / top


class _Memory:
    """The colours of every member of some parts (vector RGBA arrays, image pixels), to restore
    part of them later."""

    def __init__(self, parts: list[Mobject]) -> None:
        self.parts = parts
        family = [m for p in parts for m in p.get_family()]
        self.saved = {id(m): (m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in family if isinstance(m, VMobject)}
        self.pixels = {id(m): m.pixel_array.astype(float) for m in family if _is_image(m)}

    def restore(
        self, rgb: bool | set[int], alpha: Literal["saved", "lower", "keep"], cap: Callable[[Mobject], tuple[float, float] | None] | None = None
    ) -> list[Animation]:
        """Animations putting back the saved colours (``rgb``: all, or the members with these
        ids) and opacity: ``saved`` as it was, ``lower`` the lower of saved and current (undo a
        raise, keep later dimming), ``keep`` as it is now. ``cap(member)`` may give a highest
        ``(fill, stroke)`` opacity to keep (a scene's own dimming since)."""

        def mix(m: Mobject, old: np.ndarray, new: np.ndarray, which: int) -> np.ndarray:
            old = _fit(old, new)
            if rgb is True or (rgb and id(m) in rgb):
                new[..., :3] = old[..., :3]
            if alpha == "saved":
                new[..., 3] = old[..., 3]
            elif alpha == "lower":
                new[..., 3] = np.minimum(new[..., 3], old[..., 3])
            limit = cap(m) if cap is not None else None
            if limit is not None:
                new[..., 3] = np.minimum(new[..., 3], limit[which] * (255 if new.ndim == 3 else 1))
            return new

        def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            if id(m) in self.saved:
                old_fill, old_stroke = self.saved[id(m)]
                return mix(m, old_fill, fill, 0), mix(m, old_stroke, stroke, 1)
            return fill, stroke

        def paint_image(m: Mobject, pixels: np.ndarray) -> np.ndarray:
            return mix(m, self.pixels[id(m)], pixels, 0) if id(m) in self.pixels else pixels

        return [Repaint(part, paint, paint_image) for part in self.parts]


def _parts(scene: NarratedScene, targets: list[Target]) -> list[tuple[Target, Mobject]]:
    """Every on-screen part of the targets, with its target."""
    return [(t, part) for t in targets for part in scene.on_screen_parts(t)]


@action("reveal")
class Reveal(Action):
    """Bring a target on screen with the scene's own entrance animation, e.g. an item before its
    turn. A target already on screen is left alone, and the scene does not reveal it again."""

    run_time = 0.8
    needs_visible = False

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The entrances of the targets not on screen yet."""
        return [anim for target in targets for anim in scene.entrance(target)]


#: Opacity (of its full opacity) of text on a dimmed filled shape: it is recoloured for the
#: dimmed shape, so it may stay stronger than the shape and still look dimmed.
TEXT_ON_FILL_DIM = 0.7


def _fill_of(shape: Mobject) -> tuple[str, float] | None:
    """The fill colour (hex) and opacity of ``shape``, or ``None`` when it has no fill."""
    if not isinstance(shape, VMobject) or not len(shape.fill_rgbas):
        return None
    opacity = float(np.max(shape.fill_rgbas[:, 3]))
    return (rgb_to_hex(shape.fill_rgbas[0, :3]), opacity) if opacity > 0.05 else None


def _inks(target: Target, part: Mobject, look: Callable[[Mobject, str, float], str]) -> dict[int, np.ndarray]:
    """For the text of ``target``'s ``on_fill`` pairs inside ``part``: the colour that reads on
    its shape's new look (``look(shape, fill_hex, fill_opacity)`` -> the colour the shape will
    show), by member id."""
    family = {id(m) for m in part.get_family()}
    inks: dict[int, np.ndarray] = {}
    for text, shape in target.on_fill:
        fill = _fill_of(shape)
        if fill is None or not any(id(m) in family for m in text.get_family()):
            continue
        rgb = np.array(ManimColor(text_color_on(look(shape, *fill))).to_rgb())
        inks.update({id(m): rgb for m in text.get_family()})
    return inks


def dim_to(target: Target, part: Mobject, factor: float, *, own: bool = True, **kwargs: Any) -> Animation:
    """Fade ``part`` (of ``target``) to at most ``factor`` x the target's full opacity; parts
    already that dim stay as they are (dimming never compounds). Text on a filled shape of the
    target (``Target.on_fill``) is recoloured for the dimmed shape instead and kept at
    :data:`TEXT_ON_FILL_DIM`. Used by the ``dim`` action (``own=False``) and by scenes that dim
    on their own (``bullets`` ``dim_previous``), whose dimming is recorded on the target
    (``Target.scene_dim``) so that undoing a ``dim`` action keeps it."""
    if own:
        target.scene_dim = factor if target.scene_dim is None else min(target.scene_dim, factor)
    background = current_theme().background

    def dimmed(shape: Mobject, fill: str, opacity: float) -> str:
        return mix_colors(fill, background, min(opacity, factor * target.rest_opacity(shape)[0]))

    inks = _inks(target, part, dimmed)

    def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        full_fill, full_stroke = target.rest_opacity(m)
        limit = factor
        if id(m) in inks:
            fill[:, :3] = inks[id(m)]
            stroke[:, :3] = inks[id(m)]
            limit = max(factor, TEXT_ON_FILL_DIM)
        _scale_alpha(fill[:, 3], full_fill * limit)
        _scale_alpha(stroke[:, 3], full_stroke * limit)
        return fill, stroke

    def paint_image(m: Mobject, pixels: np.ndarray) -> np.ndarray:
        _scale_alpha(pixels[..., 3], 255 * target.rest_opacity(m)[0] * factor)
        return pixels

    return Repaint(part, paint, paint_image, **kwargs)


@action("dim")
class Dim(Action):
    """Fade targets to ``opacity`` of their full opacity, e.g. finished points (a target that is
    already dimmer, e.g. by bullets' dim_previous, stays as it is); ``until: <beat>`` brings them
    back. Images fade too."""

    class Options(ActionOptions):
        opacity: float = Field(default=0.45, ge=0, le=1)
        """Opacity relative to the target's full opacity (0.45 keeps dimmed text readable for lint)."""

    reversible = True

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Lower the alpha of every part on screen to at most ``opacity`` x its full alpha (text
        on a filled shape is recoloured for the dimmed shape instead)."""
        pairs = _parts(scene, targets)
        self.memory = _Memory([part for _, part in pairs])
        self.inked = {id(m) for t in targets for text, _ in t.on_fill for m in text.get_family()}
        return [dim_to(target, part, self.options.opacity, own=False) for target, part in pairs]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Restore the opacities from before (and the colours of recoloured text; other colours
        keep what happened since). Dimming the scene did meanwhile (``bullets``
        ``dim_previous``, a highlight step) stays."""
        owners = {id(m): t for t in targets for m in t.mobject.get_family()}

        def cap(m: Mobject) -> tuple[float, float] | None:
            t = owners.get(id(m))
            if t is None or t.scene_dim is None:
                return None
            fill, stroke = t.rest_opacity(m)
            return fill * t.scene_dim, stroke * t.scene_dim

        return self.memory.restore(rgb=self.inked, alpha="saved", cap=cap)


HighlightStyle = Literal["color", "box", "underline", "fill", "flash"]


@action("highlight")
class Highlight(Action):
    """Make targets stand out in ``color``: recolour them (``style: color``, default; a dimmed
    target is brought back to full opacity while highlighted; an image is tinted), draw a
    rounded ``box`` around or a line ``underline`` under them, lay a translucent ``fill`` of the
    colour behind them, or ``flash`` the colour once (there and back, leaving no trace). Styles
    combine as a list; ``until: <beat>`` undoes ``color``/``box``/``underline``/``fill``."""

    class Options(ActionOptions):
        color: ThemeColor = "highlight"
        """Highlight colour (theme token or hex)."""
        style: HighlightStyle | list[HighlightStyle] = Field(default="color", min_length=1)
        """color, box, underline, fill or flash, or a list of them."""

        @field_validator("style")
        @classmethod
        def _combinable(cls, value: Any) -> Any:
            if isinstance(value, list) and "flash" in value and "color" in value:
                raise ValueError("flash and color both change the colour; combine either with box or underline")
            return value

    reversible = True
    #: Gap between a target and its box / underline (Manim units) and their stroke width.
    box_buff = 0.12
    underline_buff = 0.08
    stroke_width = 4.0
    #: How far an image's pixels are tinted towards the colour (0-1).
    image_tint = 0.3
    #: Opacity of the ``fill`` plate (below lint's 0.3 for shapes that hide text).
    fill_opacity = 0.22

    def _styles(self) -> list[str]:
        return [self.options.style] if isinstance(self.options.style, str) else list(dict.fromkeys(self.options.style))

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Recolour / draw the decorations / flash, per the chosen styles."""
        styles = self._styles()
        color = scene.theme.color(self.options.color)
        pairs = _parts(scene, targets)
        self.memory = _Memory([part for _, part in pairs])
        self.inked: set[int] = set()
        self.decorations: list[Mobject] = []
        anims: list[Animation] = []
        if "color" in styles or "flash" in styles:
            rate = there_and_back if "flash" in styles else smooth
            # text on a filled shape takes the colour that reads on the recoloured shape
            for target, part in pairs:
                inks = _inks(target, part, lambda shape, fill, opacity: mix_colors(color, scene.theme.background, opacity))
                anims.append(self._repaint(target, part, color, undim="color" in styles, rate=rate, inks=inks))
        elif "fill" in styles:
            # the plate tints the shapes under text: recolour that text for the tinted shape
            for target, part in pairs:
                inks = _inks(target, part, lambda shape, fill, opacity: mix_colors(color, fill, self.fill_opacity))
                if inks:
                    self.inked |= set(inks)
                    anims.append(Repaint(part, _ink_paint(inks)))
        for target in targets:
            around = target.outline if target.outline is not None else target.mobject
            if "box" in styles:
                box = SurroundingRectangle(around, color=color, buff=self.box_buff, corner_radius=0.1, stroke_width=self.stroke_width)
                self.decorations.append(_follow(scene, box, around))
                anims.append(Create(box))
            if "underline" in styles:
                line = Underline(target.mobject, color=color, buff=self.underline_buff, stroke_width=self.stroke_width)
                self.decorations.append(_follow(scene, line, target.mobject))
                anims.append(Create(line))
            if "fill" in styles:
                anims.append(self._plate(scene, target, [part for t, part in pairs if t is target], color))
        return anims

    def _plate(self, scene: NarratedScene, target: Target, parts: list[Mobject], color: str) -> Animation:
        """A translucent rounded plate around the target's outline, drawn just below its parts
        (fading in), so a backdrop such as a table stripe stays below it."""
        around = target.outline if target.outline is not None else target.mobject
        plate = SurroundingRectangle(around, buff=self.box_buff, corner_radius=0.1, stroke_width=0)
        plate.set_fill(color, opacity=0)
        plate.set_z_index(min((p.z_index for p in parts), default=0))
        tops = [next((i for i, m in enumerate(scene.mobjects) if part in m.get_family()), len(scene.mobjects)) for part in parts]
        whole = bool(parts) and all(scene.mobjects[i] is part for i, part in zip(tops, parts) if i < len(scene.mobjects))
        # below the parts when they were added on their own; over the group holding them otherwise
        # (its backdrop would hide the plate; the plate is faint, so text under it stays readable)
        scene.mobjects.insert(min(tops, default=len(scene.mobjects)) if whole else max(tops, default=len(scene.mobjects) - 1) + 1, plate)
        self.decorations.append(plate)
        grown = plate.copy().set_fill(color, opacity=self.fill_opacity)
        _follow(scene, plate, around, fill=self.fill_opacity)
        return Transform(plate, grown)

    def _repaint(
        self, target: Target, part: Mobject, color: str, undim: bool, rate: Callable[[float], float], inks: dict[int, np.ndarray] | None = None
    ) -> Animation:
        rgb = np.array(ManimColor(color).to_rgb())
        tint = self.image_tint
        inks = inks or {}

        def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            ink = inks.get(id(m), rgb)
            fill[:, :3] = ink
            stroke[:, :3] = ink
            if undim:
                full_fill, full_stroke = target.rest_opacity(m)
                _scale_alpha(fill[:, 3], full_fill, raise_to=True)
                _scale_alpha(stroke[:, 3], full_stroke, raise_to=True)
            return fill, stroke

        def paint_image(m: Mobject, pixels: np.ndarray) -> np.ndarray:
            pixels[..., :3] = pixels[..., :3] * (1 - tint) + rgb * 255 * tint
            if undim:
                _scale_alpha(pixels[..., 3], 255 * target.rest_opacity(m)[0], raise_to=True)
            return pixels

        return Repaint(part, paint, paint_image, rate_func=rate)

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Restore the colours and the opacity a ``color`` highlight raised (dimming applied
        since stays), and remove the decorations."""
        styles = self._styles()
        anims = self.memory.restore(rgb=True, alpha="lower") if "color" in styles else []
        if self.inked and "color" not in styles:
            anims += self.memory.restore(rgb=self.inked, alpha="keep")
        for d in self.decorations:
            d.clear_updaters()
        return anims + [FadeOut(d) for d in self.decorations if d in scene.mobjects]


def _ink_paint(inks: dict[int, np.ndarray]) -> Paint:
    """A ``Repaint`` function giving the members in ``inks`` their colour (opacity unchanged)."""

    def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if id(m) in inks:
            fill[:, :3] = inks[id(m)]
            stroke[:, :3] = inks[id(m)]
        return fill, stroke

    return paint


def _alpha(m: Mobject) -> float:
    """Largest fill / stroke opacity in ``m``'s family (0 when nothing shows)."""
    best = 0.0
    for member in m.get_family():
        if isinstance(member, VMobject):
            for rgbas in (member.fill_rgbas, member.stroke_rgbas):
                if len(rgbas):
                    best = max(best, float(np.max(rgbas[:, 3])))
    return best


def _follow(scene: NarratedScene, decoration: VMobject, anchor: Mobject, fill: float | None = None) -> VMobject:
    """Keep ``decoration`` (a highlight box, underline or plate) with ``anchor`` when the scene
    moves it later (a code listing scrolling, a pie slice pulled out), fading it while the
    anchor fades and hiding it while the anchor is off screen (rows scrolled out of a window).
    ``fill`` is its fill opacity once drawn (default: as now). Waits stay frozen frames."""
    offset = decoration.get_center() - anchor.get_center()
    full = _alpha(anchor)
    look = (decoration.get_stroke_opacity(), decoration.get_fill_opacity() if fill is None else fill)
    # a guide shape the scene never draws (a table cell's outline): follow it, never fade
    guide = full <= 0.01 or not scene.on_screen_parts(anchor)

    def update(m: Mobject) -> None:
        m.move_to(anchor.get_center() + offset)
        share = 1.0 if guide else (min(1.0, _alpha(anchor) / full) if scene.on_screen_parts(anchor) else 0.0)
        m.set_stroke(opacity=look[0] * share)
        m.set_fill(opacity=look[1] * share)

    decoration.add_updater(update)
    return decoration


@action("zoom")
class Zoom(Action):
    """Move the camera in on targets and back: by the end of the beat, or with ``until: <beat>``
    by the time that beat starts. Without ``scale`` the view is as close as fits the targets
    with ``padding`` around them (at most 3x; a target that fills the frame is not zoomed); the
    view never leaves the frame."""

    class Options(ActionOptions):
        scale: float | None = Field(default=None, gt=1, le=8)
        """Magnification (2 = twice as large); default: as close as the targets fit with padding."""
        padding: float = Field(default=0.15, ge=0, lt=0.5)
        """Share of the zoomed view kept free on each side of the targets."""

    run_time = 1.0
    reversible = True
    temporary = True
    moves_camera = True
    #: Largest magnification chosen automatically (``scale`` may ask for more).
    max_scale = 3.0

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Move and narrow the camera frame onto the targets' parts on screen."""
        parts = [part for _, part in _parts(scene, targets)] or [t.mobject for t in targets]
        group = Group(*parts)
        fw, fh = scene.frame_width, scene.frame_height
        if self.options.scale is not None:
            factor = self.options.scale
        else:
            room = 1 - 2 * self.options.padding
            factor = min(self.max_scale, room * fw / max(group.width, 1e-6), room * fh / max(group.height, 1e-6))
        if factor <= 1.01:
            names = ", ".join(t.name for t in targets)
            log.warning("scene '%s': zoom on %s: the targets already fill the frame; the camera stays (use scale)", scene.spec.id, names)
            return []
        width, height = fw / factor, fh / factor
        x, y = group.get_center()[:2]
        center = np.array([np.clip(x, (width - fw) / 2, (fw - width) / 2), np.clip(y, (height - fh) / 2, (fh - height) / 2), 0.0])
        return [MoveCamera(scene, width, center)]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to the whole frame (nothing to do when the camera is there)."""
        frame = scene.camera.frame
        if abs(frame.width - scene.frame_width) < 1e-6 and np.allclose(frame.get_center(), ORIGIN, atol=1e-6):
            return []
        return [MoveCamera(scene, scene.frame_width, ORIGIN)]


class MoveCamera(Transform):
    """Move the scene's camera frame to show ``width`` units around ``center`` (the height
    follows the frame's aspect ratio)."""

    def __init__(self, scene: NarratedScene, width: float, center: np.ndarray, **kwargs: Any) -> None:
        frame = scene.camera.frame
        super().__init__(frame, frame.copy().set_width(width).move_to(center), **kwargs)


TransformStyle = Literal["auto", "replace", "shapes", "tex", "fade"]
_TEXT_KINDS = (Text, MarkupText, Paragraph, SingleStringMathTex)


def _texty(mob: Mobject) -> bool:
    """Whether ``mob`` is (made of) text or formulas only."""
    return isinstance(mob, _TEXT_KINDS) or (bool(mob.submobjects) and all(_texty(m) for m in mob.submobjects))


@action("transform")
class TransformAction(Action):
    """Morph targets into the target ``into`` (one not on screen yet, e.g. a later equation
    step), which then stays on screen in its own place. ``style``: ``auto`` (matching shapes
    for text and formulas, else ``replace``), ``replace`` (point-by-point morph), ``shapes``
    (moves matching glyphs), ``tex`` (matching TeX parts; formulas only), ``fade`` (cross-fade)."""

    class Options(ActionOptions):
        into: str = Field(min_length=1)
        """The target they become (a target name of the scene, not on screen yet)."""
        style: TransformStyle = "auto"
        """auto, replace, shapes, tex or fade."""

    run_time = 1.0
    target_options = ("into",)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Swap the targets' on-screen parts for a copy and morph that into ``into``."""
        found = scene.find_targets(self.options.into)
        if not found:
            raise VidgenError(f"scene '{scene.spec.id}': transform into unknown target '{self.options.into}'")
        hidden = [t for t in found if not scene.is_shown(t)]
        parts = [part for _, part in _parts(scene, targets)]
        if not parts:
            return []
        dest_mobs = [t.mobject for t in hidden]
        destination = dest_mobs[0] if len(dest_mobs) == 1 else Group(*dest_mobs)
        if not hidden:  # already on screen: nothing to morph into, fade the sources there
            log.warning("scene '%s': transform into '%s', which is already on screen; fading out instead", scene.spec.id, self.options.into)
            point = found[0].mobject.get_center()
            return [FadeOut(part, target_position=point) for part in parts]
        copies = [part.copy() for part in parts]
        vector = all(isinstance(m, VMobject) for m in copies) and isinstance(destination, VMobject)
        source = copies[0] if len(copies) == 1 else (VGroup(*copies) if vector else Group(*copies))
        scene.remove(*parts)
        scene.add(source)
        return [self._morph(scene, source, destination, vector)]

    def _morph(self, scene: NarratedScene, source: Mobject, destination: Mobject, vector: bool) -> Animation:
        style = self.options.style
        if style == "tex" and not (isinstance(source, MathTex) and isinstance(destination, MathTex)):
            log.warning("scene '%s': transform style 'tex' needs formulas on both sides; using 'shapes'", scene.spec.id)
            style = "shapes"
        if style in ("shapes", "auto") and not vector:
            style = "fade"
        if style == "auto":
            style = "shapes" if _texty(source) and _texty(destination) else "replace"
        if style == "tex":
            return TransformMatchingTex(source, destination)
        if style == "shapes":
            return TransformMatchingShapes(source, destination)
        if style == "fade":
            return FadeTransform(source, destination)
        return ReplacementTransform(source, destination)
