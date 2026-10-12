"""Drawing a stage's light (DESIGN.md §69.31): :class:`StageLight` grades what the stage marks lit
(:func:`mark_lit`) as the camera draws it, :class:`StarField` shows the night's stars and
:class:`StageShadows` the soft shadows on the ground. The maths is in
:mod:`vidgen.cartoon.lighting`.

The grade is applied when Manim draws, not to the mobjects' colours: nothing is recoloured, so
actions that change colours (``dim``, ``highlight``, an expression) keep working, and whatever
the stage does not mark (speech bubbles, callouts, particles, captions) keeps the theme's
colours and its contrast.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from manim import Ellipse, Mobject, VGroup, VMobject
from pydantic import BaseModel, ConfigDict, Field

from vidgen.cartoon.lighting import (
    DEFAULT_STRENGTH,
    LIGHT_PRESETS,
    LightChange,
    LightGrade,
    ShadowEllipse,
    Stars,
    grade_pixels,
    grade_rgbas,
    light_at,
    light_changing,
    light_grade,
    shadow_ellipse,
    tint_grade,
)
from vidgen.config import CHARACTER_INK
from vidgen.helpers import resolve_color
from vidgen.particle_field import particle_shape
from vidgen.scene import ThemeColor
from vidgen.theme import Theme

#: The attribute :func:`mark_lit` sets on what the light grades.
LIT = "light_graded"
#: Colour of the stars (no theme token is light in every preset).
STAR_COLOR = "#FFF6DA"
#: A shadow's rings, from the outside in: size as a share of the shadow, share of its opacity.
SHADOW_RINGS: tuple[tuple[float, float], ...] = ((1.0, 0.4), (0.78, 0.4), (0.55, 0.45))

LightPresetName = Literal[LIGHT_PRESETS]  # type: ignore[valid-type]


class CustomLight(BaseModel):
    """A light of its own colour instead of a preset."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    tint: ThemeColor
    """The light's colour (a theme token or #hex): the set's colours are multiplied towards it."""
    strength: float = Field(DEFAULT_STRENGTH, ge=0.0, le=1.0)
    """How strongly: 0 = no change, 1 = the colours multiplied by the tint."""


LightSetting = LightPresetName | CustomLight  # type: ignore[valid-type]


def resolve_light(setting: str | CustomLight, theme: Theme | None = None) -> LightGrade:
    """The grade of a preset name or a :class:`CustomLight` (its tint resolved with ``theme``)."""
    if isinstance(setting, CustomLight):
        return tint_grade(resolve_color(setting.tint, theme), setting.strength)
    return light_grade(setting)


def mark_lit(*mobjects: Mobject) -> None:
    """Mark ``mobjects`` and everything in them as graded by the stage's light."""
    for mob in mobjects:
        for member in mob.get_family():
            setattr(member, LIT, True)


class StageLight:
    """A stage's light: ``base`` from the start, then the :class:`LightChange`\\s the ``light``
    action schedules. Wraps ``camera`` (a Manim Cairo camera) so the fill and stroke colours and
    the pictures of lit mobjects are drawn graded by :attr:`grade`; :meth:`update` sets the grade
    for a scene time and tells the listeners (stars, shadows) when it changed."""

    def __init__(self, camera: Any, base: LightGrade) -> None:
        self.base = base
        self.grade = base
        self.changes: list[LightChange] = []
        self._listeners: list[Callable[[LightGrade], None]] = []
        fill, stroke, image = camera.get_fill_rgbas, camera.get_stroke_rgbas, camera.display_image_mobject
        camera.get_fill_rgbas = lambda vmobject: self._graded(vmobject, fill(vmobject))
        camera.get_stroke_rgbas = lambda vmobject, *args, **kwargs: self._graded(vmobject, stroke(vmobject, *args, **kwargs))
        camera.display_image_mobject = lambda image_mobject, pixel_array: self._draw_image(image, image_mobject, pixel_array)

    def _graded(self, mob: Any, rgbas: np.ndarray) -> np.ndarray:
        if not self.grade.changes_colors or not getattr(mob, LIT, False):
            return rgbas
        return grade_rgbas(rgbas, self.grade)

    def _draw_image(self, draw: Callable[[Any, Any], Any], image: Any, pixel_array: Any) -> Any:
        """Draw a picture, graded while it is drawn when it is lit."""
        if not self.grade.changes_colors or not getattr(image, LIT, False):
            return draw(image, pixel_array)
        original = image.pixel_array
        image.pixel_array = grade_pixels(original, self.grade)
        try:
            return draw(image, pixel_array)
        finally:
            image.pixel_array = original

    def on_change(self, listener: Callable[[LightGrade], None]) -> None:
        """Call ``listener(grade)`` now and whenever the grade changes."""
        self._listeners.append(listener)
        listener(self.grade)

    def change(self, grade: LightGrade, start: float, seconds: float) -> None:
        """Fade to ``grade`` from scene time ``start`` over ``seconds`` (0: at once)."""
        self.changes.append(LightChange(float(start), max(float(seconds), 0.0), grade))

    def update(self, now: float) -> None:
        """Set the grade for scene time ``now``."""
        grade = light_at(self.base, self.changes, now)
        if grade != self.grade:
            self.grade = grade
            for listener in self._listeners:
                listener(grade)

    def changing(self, start: float, end: float) -> bool:
        """Whether the light changes between scene times ``start`` and ``end``."""
        return light_changing(self.changes, start, end)

    def settled(self, now: float) -> bool:
        """Whether every change is over at scene time ``now``."""
        return all(change.end <= now and (change.seconds > 0 or change.start < now) for change in self.changes)


class StarField(VGroup):
    """The night's stars over ``box`` (``left, bottom, right, top`` in Manim units; ``y`` of the
    stars from its top), each ``size`` × ``short_side`` large; :meth:`set_level` shows them
    (0: hidden, 1: at their brightness)."""

    def __init__(self, stars: Stars, box: tuple[float, float, float, float], short_side: float) -> None:
        super().__init__()
        left, bottom, right, top = box
        unit = particle_shape("star").points
        for x, y, size in zip(stars.x, stars.y, stars.size):
            star = VMobject()
            star.points = unit * (size * short_side) + np.array([left + x * (right - left), top - y * (top - bottom), 0.0])
            star.set_fill(STAR_COLOR, opacity=1.0)
            star.set_stroke(width=0.0, opacity=0.0)
            self.add(star)
        self.name = "stars"
        self._brightness = np.asarray(stars.brightness, dtype=float)
        self.set_level(0.0)

    def set_level(self, level: float) -> StarField:
        """Show the stars at ``level`` (0..1) of their brightness."""
        for star, brightness in zip(self.submobjects, self._brightness):
            star.set_fill(opacity=float(brightness * level))
        return self


@dataclass
class ShadowCaster:
    """What casts a shadow: ``mobject`` (with ``feet()``; a prop with ``held_by`` set casts none),
    the y of its ``ground`` line, its shadow's ``width`` and its ``size`` (height, the unit of how
    high it is off the ground)."""

    mobject: Any
    ground: float
    width: float
    size: float

    def ellipse(self, strength: float) -> ShadowEllipse:
        """Its shadow now (:func:`~vidgen.cartoon.lighting.shadow_ellipse`)."""
        x, y = (float(v) for v in self.mobject.feet()[:2])
        held = getattr(self.mobject, "held_by", None) is not None
        return shadow_ellipse(x, self.ground, self.width, above=y - self.ground, size=self.size, strength=0.0 if held else strength)


class Shadow(VGroup):
    """One soft shadow: :data:`SHADOW_RINGS` ellipses in the characters' ink, darker inside."""

    def __init__(self) -> None:
        super().__init__()
        self._unit = Ellipse(width=1.0, height=1.0).points.copy()
        for _ in SHADOW_RINGS:
            ring = VMobject()
            ring.points = self._unit.copy()
            ring.set_fill(CHARACTER_INK, opacity=0.0)
            ring.set_stroke(width=0.0, opacity=0.0)
            self.add(ring)

    def place(self, ellipse: ShadowEllipse) -> None:
        """Put the shadow where ``ellipse`` says, with its opacity."""
        for ring, (scale, share) in zip(self.submobjects, SHADOW_RINGS):
            ring.points = self._unit * np.array([ellipse.width * scale, ellipse.height * scale, 0.0]) + np.array([ellipse.x, ellipse.y, 0.0])
            ring.set_fill(opacity=ellipse.opacity * share)


class StageShadows(VGroup):
    """The shadows of ``casters``, at ``strength`` (the light's ``shadow``); :meth:`follow` puts
    each under its caster as it is now (an updater calls it for things that move)."""

    def __init__(self, casters: Sequence[ShadowCaster], strength: float = 1.0) -> None:
        super().__init__()
        self.casters = list(casters)
        self.strength = strength
        self.name = "shadows"
        for _ in self.casters:
            self.add(Shadow())
        self.follow()

    def follow(self) -> StageShadows:
        """Place every shadow under its caster now."""
        for shadow, caster in zip(self.submobjects, self.casters):
            shadow.place(caster.ellipse(self.strength))
        return self

    def set_strength(self, strength: float) -> StageShadows:
        """Darken or lighten the shadows (the light's ``shadow`` factor)."""
        self.strength = strength
        return self.follow()
