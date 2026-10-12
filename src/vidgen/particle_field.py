"""Drawing particles (DESIGN.md §69.9): :class:`ParticleField`, a group of small shapes that
moves on every frame as :func:`vidgen.particles.particle_states` says, over the part of the frame
the camera shows (so they stay on screen through a zoom or a pan).

:class:`ParticleSettings` holds the options shared by the ``particles`` beat action and the
``stage`` scene's ``particles`` param; :func:`particle_field` builds a field for a running scene.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
from manim import Animation, Circle, Mobject, Polygon, Rectangle, VGroup, VMobject
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vidgen.helpers import resolve_color
from vidgen.particles import PARTICLE_KINDS, ParticleSeeds, Shape, check_area, particle_count, particle_kind, particle_seeds, particle_states
from vidgen.scene import ThemeColor

if TYPE_CHECKING:
    from vidgen.scene import NarratedScene
    from vidgen.theme import Theme

#: Seconds a field takes to fade in when it starts.
FADE_IN = 0.5
#: Line width of a bubble's ring.
RING_WIDTH = 1.5

ParticleKindName = Literal[PARTICLE_KINDS]  # type: ignore[valid-type]
#: ``(left, bottom, right, top)`` of the part of the scene the camera shows, in Manim units.
View = tuple[float, float, float, float]
#: A scene's wind for particles (DESIGN.md §69.32): ``(start, now)`` scene seconds -> (its force
#: added up from ``start`` to ``now``, its force at ``now``).
ParticleWind = Callable[[float, float], tuple[float, float]]


class ParticleSettings(BaseModel):
    """Options of a particle field besides its kind (shared by the action and the stage)."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    density: float = Field(1.0, gt=0.0, le=4.0)
    """How many: 1 = the kind's usual amount for a whole frame, 2 = twice as many (at most 300 in all; half at preview quality)."""
    area: list[float] | None = None
    """Where they are: [x, y, w, h] fractions 0-1 of the visible frame from its top-left corner; default the whole frame."""
    color: ThemeColor | list[ThemeColor] | None = None
    """A colour or a list (each particle picks one); default per kind (rain light blue, snow white, sparkles highlight, confetti the theme's colours...)."""
    seed: int = Field(1, ge=0)
    """Another number gives other positions; the same number gives the same particles in every render."""

    @field_validator("area")
    @classmethod
    def _area(cls, value: list[float] | None) -> list[float] | None:
        return None if value is None else check_area(value)


def particle_shape(shape: Shape) -> VMobject:
    """The shape of one particle at size 1 (a dot's radius, a streak's half length), centred."""
    if shape == "streak":
        return Rectangle(width=0.08, height=2.0)
    if shape == "chip":
        return Rectangle(width=2.0, height=1.2)
    if shape == "star":
        corners = [(math.cos(a), math.sin(a)) for a in np.linspace(math.pi / 2, math.pi / 2 + 2 * math.pi, 9)[:-1]]
        return Polygon(*[[x * (1.0 if k % 2 == 0 else 0.3), y * (1.0 if k % 2 == 0 else 0.3), 0.0] for k, (x, y) in enumerate(corners)])
    return Circle(radius=1.0, num_components=9)


class ParticleField(VGroup):
    """Particles of one kind over ``area`` of the view, moving with the scene's time.

    ``clock()`` gives the scene's time in seconds and ``view()`` the part of the scene the camera
    shows; ``short_side`` is the frame's shorter side and ``frame_width`` its width (Manim units);
    ``wind`` (a stage's, :data:`ParticleWind`) makes them drift with it.
    The field fades in over :data:`FADE_IN` seconds and keeps moving while other animations play
    (its updating is never suspended); its fade out (:meth:`fade_out_animation`, used by
    :func:`vidgen.helpers.fade_out`) keeps it moving too and removes it.
    """

    def __init__(
        self,
        seeds: ParticleSeeds,
        colors: list[str],
        *,
        clock: Callable[[], float],
        view: Callable[[], View],
        area: list[float],
        short_side: float,
        frame_width: float,
        name: str | None = None,
        wind: ParticleWind | None = None,
    ) -> None:
        super().__init__()
        self.seeds = seeds
        self.clock = clock
        self.view = view
        self.area = area
        self.short_side = short_side
        self.frame_width = frame_width
        self.wind = wind
        self.name = name or seeds.kind
        self.start = clock()
        #: 1 while shown; its fade out takes it to 0.
        self.level = 1.0
        spec = particle_kind(seeds.kind)
        unit = particle_shape(spec.shape)
        self._unit = unit.points.copy()
        ring = spec.shape == "ring"
        for k in range(len(seeds)):
            particle = VMobject()
            particle.points = self._unit.copy()
            color = colors[int(seeds.color[k]) % len(colors)]
            particle.set_fill(color, opacity=0.15 if ring else 1.0)
            particle.set_stroke(color, width=RING_WIDTH if ring else 0.0, opacity=1.0 if ring else 0.0)
            self.add(particle)
        self._fill = [p.fill_rgbas[:, 3].copy() for p in self.submobjects]
        self._stroke = [p.stroke_rgbas[:, 3].copy() for p in self.submobjects]
        self.draw_at(self.start)
        self.add_updater(self._step)

    def _step(self, mob: Mobject, dt: float) -> None:
        """Updater (time based, so waits draw every frame): place the particles for now."""
        self.draw_at(self.clock())

    def suspend_updating(self, recursive: bool = True) -> ParticleField:
        """Never suspended: particles keep moving while an animation (a fade) plays on them."""
        return self

    def elapsed(self, now: float) -> float:
        """Seconds the field has been running at scene time ``now``."""
        return max(now - self.start, 0.0)

    def draw_at(self, now: float) -> None:
        """Put every particle where it is at scene time ``now``, sized and faded for the view."""
        left, bottom, right, top = self.view()
        view_width, view_height = right - left, top - bottom
        x, y, w, h = self.area
        zoom = view_width / self.frame_width  # < 1 when zoomed in: the particles stay as large on screen
        short = self.short_side * zoom
        t = self.elapsed(now)
        blown, force = self.wind(self.start, now) if self.wind is not None else (0.0, 0.0)
        states = particle_states(self.seeds, t, width=w * view_width / short, height=h * view_height / short, blown=blown, wind=force)
        level = self.level * min(t / FADE_IN, 1.0)
        xs = left + (x + states.x * w) * view_width
        ys = top - (y + states.y * h) * view_height
        cos, sin = np.cos(states.angle), np.sin(states.angle)
        unit = self._unit
        for k, particle in enumerate(self.submobjects):
            size = states.size[k] * short
            px = unit[:, 0] * size * states.flip[k]
            py = unit[:, 1] * size
            points = np.empty_like(unit)
            points[:, 0] = xs[k] + px * cos[k] - py * sin[k]
            points[:, 1] = ys[k] + px * sin[k] + py * cos[k]
            points[:, 2] = 0.0
            particle.points = points
            seen = states.opacity[k] * level
            particle.fill_rgbas[:, 3] = self._fill[k] * seen
            particle.stroke_rgbas[:, 3] = self._stroke[k] * seen

    def fade_out_animation(self, **kwargs: Any) -> Animation:
        """An animation that fades the field out (still moving) and removes it."""
        return _FieldFadeOut(self, **kwargs)


class _FieldFadeOut(Animation):
    """Takes a :class:`ParticleField`'s level from where it is to 0, then removes the field."""

    def __init__(self, field: ParticleField, **kwargs: Any) -> None:
        kwargs.setdefault("remover", True)
        super().__init__(field, **kwargs)
        self.field = field
        self._from = field.level

    def create_starting_mobject(self) -> Mobject:
        """No copy (the base class copies the mobject; nothing here reads it)."""
        return Mobject()

    def interpolate_mobject(self, alpha: float) -> None:
        """The level, then the particles redrawn with it."""
        self.field.level = self._from * (1.0 - self.rate_func(alpha))
        self.field.draw_at(self.field.clock())

    def clean_up_from_scene(self, scene: Any) -> None:
        """Remove the field (its level stays 0)."""
        super().clean_up_from_scene(scene)
        self.field.level = 0.0


def scene_view(scene: NarratedScene) -> View:
    """``(left, bottom, right, top)`` of what the scene's camera shows now."""
    frame = getattr(scene.camera, "frame", None)
    if frame is None:
        half_w, half_h = scene.frame_width / 2, scene.frame_height / 2
        return (-half_w, -half_h, half_w, half_h)
    cx, cy = (float(v) for v in frame.get_center()[:2])
    half_w, half_h = float(frame.width) / 2, float(frame.height) / 2
    return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def particle_colors(kind: str, color: str | list[str] | None, theme: Theme) -> list[str]:
    """The hex colours of a field: ``color`` (one or a list of tokens / hex), else the kind's."""
    tokens = particle_kind(kind).colors if color is None else ([color] if isinstance(color, str) else color)
    return [resolve_color(c, theme) for c in tokens]


def particle_field(scene: NarratedScene, kind: str, settings: ParticleSettings) -> ParticleField:
    """A field of ``kind`` particles for ``scene``, starting now, drawn above everything on screen
    (not added to the scene). Fewer particles when the scene renders at preview quality
    (:attr:`NarratedScene.is_preview`). They drift with the scene's ``particle_wind`` when it has
    one (a windy stage, DESIGN.md §69.32)."""
    area = settings.area or [0.0, 0.0, 1.0, 1.0]
    colors = particle_colors(kind, settings.color, scene.theme)
    count = particle_count(kind, settings.density, area[2] * area[3], preview=scene.is_preview)
    seeds = particle_seeds(kind, count, settings.seed, colors=len(colors))
    field = ParticleField(
        seeds,
        colors,
        clock=lambda: float(scene.renderer.time),
        view=lambda: scene_view(scene),
        area=area,
        short_side=min(scene.frame_width, scene.frame_height),
        frame_width=scene.frame_width,
        wind=getattr(scene, "particle_wind", None),
    )
    top = max((m.z_index for m in scene.get_mobject_family_members()), default=0)
    field.set_z_index(top + 1)
    return field
