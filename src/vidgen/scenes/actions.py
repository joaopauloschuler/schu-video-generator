"""Built-in per-beat actions: ``reveal``, ``dim`` and ``highlight`` (DESIGN.md §26).

Written against ``vidgen.api`` only, like project actions. ``dim`` and ``highlight`` change only
opacity resp. colour, so they combine and undo (``until:``) independently.
"""

from collections.abc import Callable
from typing import Any, Literal

import numpy as np

from vidgen.api import *

Paint = Callable[[Any, np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]


class Repaint(Animation):
    """Animate the fill/stroke RGBA of every vectorized mobject in ``mobject``'s family to
    ``paint(member, fill, stroke) -> (fill, stroke)``, computed from the arrays when it begins.
    Points are untouched, so it combines with anything that moves the mobject later."""

    def __init__(self, mobject: Mobject, paint: Paint, **kwargs: Any) -> None:
        super().__init__(mobject, **kwargs)
        self.paint = paint
        self._members: list[VMobject] = []
        self._start: list[tuple[np.ndarray, np.ndarray]] = []
        self._end: list[tuple[np.ndarray, np.ndarray]] = []

    def begin(self) -> None:
        """Read the start colours and compute the end colours."""
        self._members = [m for m in self.mobject.get_family() if isinstance(m, VMobject)]
        self._start = [(m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in self._members]
        self._end = [self.paint(m, f.copy(), s.copy()) for m, (f, s) in zip(self._members, self._start)]
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        """Blend every member's colours."""
        a = self.rate_func(alpha)
        for m, (f0, s0), (f1, s1) in zip(self._members, self._start, self._end):
            m.fill_rgbas = f0 + (f1 - f0) * a
            m.stroke_rgbas = s0 + (s1 - s0) * a


def _fit(saved: np.ndarray, current: np.ndarray) -> np.ndarray:
    """``saved`` with the shape of ``current`` (a member rebuilt meanwhile: repeat its first row)."""
    return saved if saved.shape == current.shape else np.resize(saved[:1], current.shape)


class _Memory:
    """The colours of every vectorized member of some parts, to restore part of them later."""

    def __init__(self, parts: list[Mobject]) -> None:
        self.parts = parts
        self.saved = {id(m): (m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for p in parts for m in p.get_family() if isinstance(m, VMobject)}

    def restore(self, channels: slice) -> list[Animation]:
        """Animations putting the saved ``channels`` (``slice(0, 3)`` RGB, ``slice(3, 4)``
        alpha) back on the parts; the other channels keep their current values."""

        def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            if id(m) in self.saved:
                old_fill, old_stroke = self.saved[id(m)]
                fill[:, channels] = _fit(old_fill, fill)[:, channels]
                stroke[:, channels] = _fit(old_stroke, stroke)[:, channels]
            return fill, stroke

        return [Repaint(part, paint) for part in self.parts]


def _rgb(color: str, scene: NarratedScene) -> np.ndarray:
    return np.array(ManimColor(scene.theme.color(color)).to_rgb())


@action("reveal")
class Reveal(Action):
    """Bring a target on screen with the scene's own entrance animation, e.g. an item before its
    turn. A target already on screen is left alone, and the scene does not reveal it again."""

    run_time = 0.8
    needs_visible = False

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """The entrances of the targets not on screen yet."""
        return [anim for target in targets for anim in scene.entrance(target)]


@action("dim")
class Dim(Action):
    """Fade targets to ``opacity`` (of their current opacity), e.g. finished points;
    ``until: <beat>`` brings them back."""

    class Options(ActionOptions):
        opacity: float = Field(default=0.45, ge=0, le=1)
        """Opacity relative to the current one (0.45 keeps dimmed text readable for lint)."""

    reversible = True

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Multiply the alpha of every part on screen by ``opacity``."""
        parts = [p for t in targets for p in scene.on_screen_parts(t)]
        self.memory = _Memory(parts)
        factor = self.options.opacity

        def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            fill[:, 3] *= factor
            stroke[:, 3] *= factor
            return fill, stroke

        return [Repaint(part, paint) for part in parts]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Restore the opacities from before (colours keep what happened since)."""
        return self.memory.restore(slice(3, 4))


HighlightStyle = Literal["color", "box", "underline", "flash"]


@action("highlight")
class Highlight(Action):
    """Make targets stand out in ``color``: recolour them (``style: color``, default), draw a
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

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Recolour / draw the decorations / flash, per the chosen styles."""
        styles = [self.options.style] if isinstance(self.options.style, str) else list(dict.fromkeys(self.options.style))
        color = scene.theme.color(self.options.color)
        parts = [p for t in targets for p in scene.on_screen_parts(t)]
        self.memory = _Memory(parts)
        self.decorations: list[Mobject] = []
        anims: list[Animation] = []
        if "color" in styles or "flash" in styles:
            rgb = _rgb(self.options.color, scene)

            def paint(m: VMobject, fill: np.ndarray, stroke: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
                fill[:, :3] = rgb
                stroke[:, :3] = rgb
                return fill, stroke

            rate = there_and_back if "flash" in styles else smooth
            anims += [Repaint(part, paint, rate_func=rate) for part in parts]
        for target in targets:
            if "box" in styles:
                box = SurroundingRectangle(target.mobject, color=color, buff=self.box_buff, corner_radius=0.1, stroke_width=self.stroke_width)
                self.decorations.append(box)
                anims.append(Create(box))
            if "underline" in styles:
                line = Underline(target.mobject, color=color, buff=self.underline_buff, stroke_width=self.stroke_width)
                self.decorations.append(line)
                anims.append(Create(line))
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Restore the colours (opacity keeps what happened since) and remove decorations."""
        styles = [self.options.style] if isinstance(self.options.style, str) else self.options.style
        anims = self.memory.restore(slice(0, 3)) if "color" in styles else []
        return anims + [FadeOut(d) for d in self.decorations if d in scene.mobjects]
