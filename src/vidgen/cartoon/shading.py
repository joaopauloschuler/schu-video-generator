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

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
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
    lamp_lit,
    light_at,
    light_changing,
    light_grade,
    shadow_ellipse,
    tint_grade,
)
from vidgen.cartoon.storm import FLASH_SHARE, RainStorm, Strike, flash_grade, flash_level, flashing
from vidgen.cartoon.sun_path import cast_shadow
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


#: The attribute holding a :class:`LampLit` on what a lamp can light (DESIGN.md §89.13).
LAMP_LIT = "lamp_lit"


class LampLit:
    """How much lamplight falls on a character: ``share()`` (0..1) is asked when it is drawn
    (once per scene time, :class:`StageLight` asks for each of its shapes); :meth:`grade` is the
    stage's light with it (:func:`~vidgen.cartoon.lighting.lamp_lit`), made once per light and
    share."""

    def __init__(self, share: Callable[[], float]) -> None:
        self.share = share
        self._made: tuple[LightGrade, float, LightGrade] | None = None

    def grade(self, base: LightGrade) -> LightGrade:
        share = round(float(self.share()), 3)
        if self._made is not None and self._made[1] == share and self._made[0] is base:
            return self._made[2]
        grade = lamp_lit(base, share)
        self._made = (base, share, grade)
        return grade


def mark_lamp_lit(mobject: Mobject, lamp: LampLit) -> None:
    """Let a lamp light ``mobject`` and everything in it (where :func:`mark_lit` grades it)."""
    for member in mobject.get_family():
        setattr(member, LAMP_LIT, lamp)


def mark_lit(*mobjects: Mobject) -> None:
    """Mark ``mobjects`` and everything in them as graded by the stage's light."""
    for mob in mobjects:
        for member in mob.get_family():
            setattr(member, LIT, True)


class StageLight:
    """A stage's light: ``base`` from the start, then the :class:`LightChange`\\s the ``light``
    action schedules, lit up by lightning (``strikes`` of the ``lightning`` action and the
    ``storms`` of rain fields with ``lightning``, DESIGN.md §69.61; ``flash_share`` of a flash:
    less in a room). Wraps ``camera`` (a Manim Cairo camera) so the fill and stroke colours and
    the pictures of lit mobjects are drawn graded by :attr:`grade`; :meth:`update` sets the grade
    for a scene time and tells the listeners (stars, shadows) when it changed. ``flat`` (a draft,
    DESIGN.md §74): nothing is graded and lightning never flashes; the changes keep their times."""

    def __init__(self, camera: Any, base: LightGrade, *, flat: bool = False) -> None:
        self.base = base
        self.grade = base
        self.flat = flat
        self.changes: list[LightChange] = []
        self.strikes: list[Strike] = []
        self.storms: list[RainStorm] = []
        self.flash_share = FLASH_SHARE
        #: how bright the lightning lights the set now (0..1)
        self.flash = 0.0
        self._listeners: list[Callable[[LightGrade], None]] = []
        if flat:
            return
        fill, stroke, image = camera.get_fill_rgbas, camera.get_stroke_rgbas, camera.display_image_mobject
        camera.get_fill_rgbas = lambda vmobject: self._graded(vmobject, fill(vmobject))
        camera.get_stroke_rgbas = lambda vmobject, *args, **kwargs: self._graded(vmobject, stroke(vmobject, *args, **kwargs))
        camera.display_image_mobject = lambda image_mobject, pixel_array: self._draw_image(image, image_mobject, pixel_array)

    def _grade_of(self, mob: Any) -> LightGrade:
        """The grade of a lit ``mob``: the light's, with a lamp's light on it (§89.13)."""
        lamp = getattr(mob, LAMP_LIT, None)
        return self.grade if lamp is None else lamp.grade(self.grade)

    def _graded(self, mob: Any, rgbas: np.ndarray) -> np.ndarray:
        if not self.grade.changes_colors or not getattr(mob, LIT, False):
            return rgbas
        return grade_rgbas(rgbas, self._grade_of(mob))

    def _draw_image(self, draw: Callable[[Any, Any], Any], image: Any, pixel_array: Any) -> Any:
        """Draw a picture, graded while it is drawn when it is lit."""
        if not self.grade.changes_colors or not getattr(image, LIT, False):
            return draw(image, pixel_array)
        original = image.pixel_array
        image.pixel_array = grade_pixels(original, self._grade_of(image))
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

    def strikes_until(self, until: float) -> list[Strike]:
        """The lightning strikes before scene time ``until``: the actions' and the storms'."""
        return [*self.strikes, *(s for storm in self.storms for s in storm.strikes(until))]

    def update(self, now: float) -> None:
        """Set the grade for scene time ``now`` (with a flash while lightning lights the set)."""
        grade = light_at(self.base, self.changes, now)
        self.flash = flash_level(self.strikes_until(now), now) if (self.strikes or self.storms) and not self.flat else 0.0
        if self.flash > 0:
            grade = flash_grade(grade, self.flash, share=self.flash_share)
        if grade != self.grade:
            self.grade = grade
            for listener in self._listeners:
                listener(grade)

    def changing(self, start: float, end: float) -> bool:
        """Whether the light changes (or lightning flashes) between scene times ``start`` and
        ``end``."""
        return light_changing(self.changes, start, end) or (not self.flat and flashing(self.strikes_until(end), start, end))

    def settled(self, now: float) -> bool:
        """Whether every change and every flash is over at scene time ``now`` (and no rain field
        with lightning still falls)."""
        changes = all(change.end <= now and (change.seconds > 0 or change.start < now) for change in self.changes)
        if self.flat:
            return changes
        return changes and all(s.end <= now for s in self.strikes) and all(storm.over(now) for storm in self.storms)


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
    """What casts a shadow: ``mobject`` (with ``feet()``; a prop with ``held_by`` set casts none,
    nor does a character ``riding`` a vehicle, DESIGN.md §69.52),
    the y of its ``ground`` line (a character's own ``ground_y`` wins: it walks in depth), its
    shadow's ``width`` and its ``size`` (height, the unit of how high it is off the ground).
    ``widths``: the shadow's width per shape a prop with shapes shows (an umbrella closed or open;
    a shape not listed: ``width``). ``grows``: width and size follow the caster's
    ``standing_height`` (a character growing or shrinking as it walks in depth, DESIGN.md §69.44)."""

    mobject: Any
    ground: float
    width: float
    size: float
    widths: Mapping[str, float] = field(default_factory=dict)
    grows: bool = False

    def ellipse(self, strength: float) -> ShadowEllipse:
        """Its shadow now (:func:`~vidgen.cartoon.lighting.shadow_ellipse`), as faint as its caster
        shows (``shown``: fading through a door)."""
        x, y = (float(v) for v in self.mobject.feet()[:2])
        held = getattr(self.mobject, "held_by", None) is not None or getattr(self.mobject, "riding", None) is not None   # its vehicle's shadow covers a rider's
        width = self.widths.get(getattr(self.mobject, "shape", None) or "", self.width)
        shown = float(getattr(self.mobject, "shown", 1.0))
        own = getattr(self.mobject, "ground_y", None)
        ground = self.ground if own is None else float(own)
        factor = float(self.mobject.standing_height) / self.size if self.grows and self.size > 0 else 1.0
        return shadow_ellipse(
            x, ground, width * factor, above=y - ground, size=self.size * factor, strength=0.0 if held else strength * shown,
        )


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
    each under its caster as it is now (an updater calls it for things that move), cast by a low
    sun or moon (:meth:`set_cast`, DESIGN.md §69.61)."""

    def __init__(self, casters: Sequence[ShadowCaster], strength: float = 1.0) -> None:
        super().__init__()
        self.casters = list(casters)
        self.strength = strength
        #: how long the shadows stretch and which way (:func:`~vidgen.cartoon.sun_path.shadow_cast`)
        self.cast = (0.0, 0.0)
        self.name = "shadows"
        for _ in self.casters:
            self.add(Shadow())
        self.follow()

    def follow(self) -> StageShadows:
        """Place every shadow under its caster now."""
        for shadow, caster in zip(self.submobjects, self.casters):
            shadow.place(cast_shadow(caster.ellipse(self.strength), *self.cast))
        return self

    def set_cast(self, stretch: float, side: float) -> StageShadows:
        """Stretch the shadows ``stretch`` (0: under their casters) towards ``side`` (+1 right, -1
        left), away from the sun."""
        if (stretch, side) != self.cast:
            self.cast = (float(stretch), float(side))
            self.follow()
        return self

    def set_strength(self, strength: float) -> StageShadows:
        """Darken or lighten the shadows (the light's ``shadow`` factor)."""
        self.strength = strength
        return self.follow()
