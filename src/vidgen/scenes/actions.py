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

    def restore(self, rgb: bool, alpha: Literal["saved", "lower", "keep"]) -> list[Animation]:
        """Animations putting back the saved colours (``rgb``) and opacity: ``saved`` as it was,
        ``lower`` the lower of saved and current (undo a raise, keep later dimming), ``keep`` as
        it is now."""

        def mix(old: np.ndarray, new: np.ndarray) -> np.ndarray:
            old = _fit(old, new)
            if rgb:
                new[..., :3] = old[..., :3]
            if alpha == "saved":
                new[..., 3] = old[..., 3]
            elif alpha == "lower":
                new[..., 3] = np.minimum(new[..., 3], old[..., 3])
            return new

        def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            if id(m) in self.saved:
                old_fill, old_stroke = self.saved[id(m)]
                return mix(old_fill, fill), mix(old_stroke, stroke)
            return fill, stroke

        def paint_image(m: Mobject, pixels: np.ndarray) -> np.ndarray:
            return mix(self.pixels[id(m)], pixels) if id(m) in self.pixels else pixels

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


def dim_to(target: Target, part: Mobject, factor: float, **kwargs: Any) -> Animation:
    """Fade ``part`` (of ``target``) to at most ``factor`` x the target's full opacity; parts
    already that dim stay as they are (dimming never compounds). Used by ``dim`` and by scenes
    that dim on their own (``bullets`` ``dim_previous``)."""

    def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        full_fill, full_stroke = target.rest_opacity(m)
        _scale_alpha(fill[:, 3], full_fill * factor)
        _scale_alpha(stroke[:, 3], full_stroke * factor)
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
        """Lower the alpha of every part on screen to at most ``opacity`` x its full alpha."""
        pairs = _parts(scene, targets)
        self.memory = _Memory([part for _, part in pairs])
        return [dim_to(target, part, self.options.opacity) for target, part in pairs]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Restore the opacities from before (colours keep what happened since)."""
        return self.memory.restore(rgb=False, alpha="saved")


HighlightStyle = Literal["color", "box", "underline", "flash"]


@action("highlight")
class Highlight(Action):
    """Make targets stand out in ``color``: recolour them (``style: color``, default; a dimmed
    target is brought back to full opacity while highlighted; an image is tinted), draw a
    rounded ``box`` around or a line ``underline`` under them, or ``flash`` the colour once
    (there and back, leaving no trace). Styles combine as a list; ``until: <beat>`` undoes
    ``color``/``box``/``underline``."""

    class Options(ActionOptions):
        color: ThemeColor = "highlight"
        """Highlight colour (theme token or hex)."""
        style: HighlightStyle | list[HighlightStyle] = Field(default="color", min_length=1)
        """color, box, underline or flash, or a list of them."""

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

    def _styles(self) -> list[str]:
        return [self.options.style] if isinstance(self.options.style, str) else list(dict.fromkeys(self.options.style))

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Recolour / draw the decorations / flash, per the chosen styles."""
        styles = self._styles()
        color = scene.theme.color(self.options.color)
        pairs = _parts(scene, targets)
        self.memory = _Memory([part for _, part in pairs])
        self.decorations: list[Mobject] = []
        anims: list[Animation] = []
        if "color" in styles or "flash" in styles:
            rate = there_and_back if "flash" in styles else smooth
            anims += [self._repaint(target, part, color, undim="color" in styles, rate=rate) for target, part in pairs]
        for target in targets:
            if "box" in styles:
                around = target.outline if target.outline is not None else target.mobject
                box = SurroundingRectangle(around, color=color, buff=self.box_buff, corner_radius=0.1, stroke_width=self.stroke_width)
                self.decorations.append(box)
                anims.append(Create(box))
            if "underline" in styles:
                line = Underline(target.mobject, color=color, buff=self.underline_buff, stroke_width=self.stroke_width)
                self.decorations.append(line)
                anims.append(Create(line))
        return anims

    def _repaint(self, target: Target, part: Mobject, color: str, undim: bool, rate: Callable[[float], float]) -> Animation:
        rgb = np.array(ManimColor(color).to_rgb())
        tint = self.image_tint

        def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            fill[:, :3] = rgb
            stroke[:, :3] = rgb
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
        anims = self.memory.restore(rgb=True, alpha="lower") if "color" in self._styles() else []
        return anims + [FadeOut(d) for d in self.decorations if d in scene.mobjects]


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
