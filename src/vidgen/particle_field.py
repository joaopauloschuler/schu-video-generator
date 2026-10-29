"""Drawing particles (DESIGN.md §69.9): :class:`ParticleField`, a group of small shapes that
moves on every frame as :func:`vidgen.particles.particle_states` says, over the part of the frame
the camera shows (so they stay on screen through a zoom or a pan).

:class:`ParticleSettings` holds the options shared by the ``particles`` beat action and the
``stage`` scene's ``particles`` param; :func:`particle_field` builds a field for a running scene.
Rain on a stage ends on its ground with splashes, and :class:`Puddles` grow there
(DESIGN.md §69.39, the model in :mod:`vidgen.cartoon.rain`); snow with ``settle`` lands there and
on the props (§69.60, :mod:`vidgen.cartoon.snow`).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Annotated, Any, Literal

import numpy as np
from manim import Animation, Circle, Ellipse, Mobject, Polygon, Rectangle, VGroup, VMobject
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vidgen.cartoon.rain import (
    PUDDLE_FLAT,
    SPLASH_OPACITY,
    IsoRainGround,
    RainGround,
    drop_floors,
    drop_landings,
    landing_shares,
    puddle_growth,
    splash_depth_scale,
    splash_shapes,
)
from vidgen.cartoon.snow import flake_floors, rest_flakes
from vidgen.cartoon.storm import STORM_EVERY
from vidgen.helpers import resolve_color
from vidgen.particles import (
    PARTICLE_KINDS,
    ParticleSeeds,
    ParticleStates,
    Shape,
    check_area,
    particle_count,
    particle_kind,
    particle_seeds,
    particle_states,
)
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
#: A stage's ground for its rain (DESIGN.md §69.39): where drops end now, shelters included.
RainGroundSource = Callable[[], RainGround]
#: Fill of a puddle (a grey blue, half seen through).
PUDDLE_COLOR = "#7393B8"
PUDDLE_OPACITY = 0.55
#: Glowing particles (``glow: true``, DESIGN.md §102.4): the core is the colour this far towards
#: white, the halo an outline of this width in the colour at this opacity, and the kind's opacity
#: is raised this many times (at most 1).
GLOW_CORE = 0.45
GLOW_HALO_WIDTH = 3.0
GLOW_HALO_OPACITY = 0.4
GLOW_BOOST = 1.6


def glow_colors(color: str) -> tuple[str, str]:
    """``(core, halo)`` of a glowing particle of ``color`` (a hex): its core towards white, its
    halo the colour itself."""
    from manim import ManimColor

    core = ManimColor(color).interpolate(ManimColor("#FFFFFF"), GLOW_CORE)
    return core.to_hex(), ManimColor(color).to_hex()


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
    puddles: bool = False
    """Rain on a stage: true lets puddles grow on the ground while it rains."""
    settle: bool = False
    """Snow on a stage: true lands it on the ground and on the props, where a white layer grows while it snows (only thinly under a tree or an open umbrella)."""
    settled: float = Field(0.0, ge=0.0, le=600.0)
    """With settle: seconds of snowfall already lying when it starts (24 or more: the full layer at density 1)."""
    lightning: bool | Annotated[float, Field(ge=2.0, le=120.0)] = False
    """Rain on a stage: true flashes lightning while it rains, about every 8 s at seeded times and places, mostly with a bolt, thunder following by the distance (with foley); a number is the seconds between strikes on average."""
    glow: bool = False
    """true: the particles shine: a bright core and a soft halo in their colour, more opaque (neon rain at night, glowing motes)."""

    @field_validator("area")
    @classmethod
    def _area(cls, value: list[float] | None) -> list[float] | None:
        return None if value is None else check_area(value)


def particle_shape(shape: Shape) -> VMobject:
    """The shape of one particle at size 1 (a dot's radius, a streak's or leaf's half length), centred."""
    if shape == "streak":
        return Rectangle(width=0.08, height=2.0)
    if shape == "chip":
        return Rectangle(width=2.0, height=1.2)
    if shape == "leaf":  # a lens with pointed tips, 2 long
        angles = np.linspace(0.0, 2 * math.pi, 13)[:-1]
        return Polygon(*[[math.cos(a), 0.45 * math.sin(a) * abs(math.sin(a)) ** 0.5, 0.0] for a in angles])
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
        ground: RainGroundSource | None = None,
        seed: int = 1,
        drawn: bool = True,
        glow: bool = False,
    ) -> None:
        super().__init__()
        #: whether they shine: a light core, a halo in their colour, more opaque (§102.4)
        self.glow = glow
        #: the camera's zoom the halos' width was set for
        self._halo_zoom = 1.0
        #: False for a draft's field (DESIGN.md §74): no particles and no updater; it keeps its
        #: start, its fade out and its end (a rain bed and storms follow them)
        self.drawn = drawn
        self.seeds = seeds
        self.clock = clock
        self.view = view
        self.area = area
        self.short_side = short_side
        self.frame_width = frame_width
        self.wind = wind
        self.ground = ground
        self.name = name or seeds.kind
        self.start = clock()
        #: Scene time its fade out ended (``None``: still shown).
        self.ended: float | None = None
        #: 1 while shown; its fade out takes it to 0.
        self.level = 1.0
        spec = particle_kind(seeds.kind)
        unit = particle_shape(spec.shape)
        self._unit = unit.points.copy()
        ring = spec.shape == "ring"
        #: how much more opaque glowing particles are than the kind's own (1: as the kind)
        self._boost = min(GLOW_BOOST, 1.0 / max(spec.opacity, 1e-9)) if glow else 1.0
        for k in range(len(seeds)):
            particle = VMobject()
            particle.points = self._unit.copy()
            color = colors[int(seeds.color[k]) % len(colors)]
            if glow:   # a light core with a halo of the colour round it (§102.4)
                core, halo = glow_colors(color)
                particle.set_fill(core, opacity=0.15 if ring else 1.0)
                particle.set_stroke(halo, width=max(GLOW_HALO_WIDTH, RING_WIDTH if ring else 0.0), opacity=GLOW_HALO_OPACITY)
            else:
                particle.set_fill(color, opacity=0.15 if ring else 1.0)
                particle.set_stroke(color, width=RING_WIDTH if ring else 0.0, opacity=1.0 if ring else 0.0)
            self.add(particle)
        #: the particles, one per seed (the field may also hold its splashes)
        self.drops: list[VMobject] = list(self.submobjects)
        self._fill = [p.fill_rgbas[:, 3].copy() for p in self.drops]
        self._stroke = [p.stroke_rgbas[:, 3].copy() for p in self.drops]
        #: rain on a stage's ground (DESIGN.md §69.39): each drop's landing share and splash spread
        self.splashes: VMobject | None = None
        if ground is not None:   # rain splashes; snow settling on a stage's ground lies still for a moment (§69.60)
            self._landing, self._spread = landing_shares(len(seeds), seed)
        if ground is not None and seeds.kind == "rain":
            self._circle = Circle(radius=1.0, num_components=9).points.copy()
            self.splashes = VMobject()
            self.splashes.points = np.zeros((0, 3))
            if glow:
                core, halo = glow_colors(colors[0])
                self.splashes.set_fill(core, opacity=1.0)
                self.splashes.set_stroke(halo, width=GLOW_HALO_WIDTH * 0.6, opacity=0.0)
            else:
                self.splashes.set_fill(colors[0], opacity=1.0)
                self.splashes.set_stroke(colors[0], width=0.0, opacity=0.0)
            self.add(self.splashes)
        self.draw_at(self.start)
        if drawn:
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
        shown = np.minimum(states.opacity * self._boost, 1.0) * level
        ground = self.ground() if self.ground is not None else None
        if ground is not None and self.splashes is not None:
            shown = shown * self._draw_splashes(ground, xs, ys, states, short, level)
        elif ground is not None:
            size = states.size * short
            floor = flake_floors(xs, ground.landing(self._landing, xs), ground)
            seen, lift = rest_flakes(ys - size, floor, particle_kind(self.seeds.kind).fall * np.abs(self.seeds.speed) * short)
            shown, ys = shown * seen, ys + lift
        unit = self._unit
        if self.glow and abs(zoom - self._halo_zoom) > 1e-6:   # a halo as wide on screen through a zoom (strokes scale with the view)
            self._halo_zoom = zoom
            for particle in self.drops:
                particle.stroke_width = GLOW_HALO_WIDTH * zoom
            if self.splashes is not None:
                self.splashes.stroke_width = GLOW_HALO_WIDTH * 0.6 * zoom
        for k, particle in enumerate(self.drops):
            size = states.size[k] * short
            px = unit[:, 0] * size * states.flip[k]
            py = unit[:, 1] * size
            points = np.empty_like(unit)
            points[:, 0] = xs[k] + px * cos[k] - py * sin[k]
            points[:, 1] = ys[k] + px * sin[k] + py * cos[k]
            points[:, 2] = 0.0
            particle.points = points
            particle.fill_rgbas[:, 3] = self._fill[k] * shown[k]
            particle.stroke_rgbas[:, 3] = self._stroke[k] * shown[k]

    def _draw_splashes(
        self, ground: RainGround, xs: np.ndarray, ys: np.ndarray, states: ParticleStates, short: float, level: float
    ) -> np.ndarray:
        """Rain on a stage (DESIGN.md §69.39): the splashes of the drops that reached their floor
        (the ground, or a shelter's top) in the last moments; returns 1 for each drop still
        falling, 0 for one that landed (not drawn until it starts again at the top)."""
        assert self.splashes is not None
        spec = particle_kind(self.seeds.kind)
        size = states.size * short
        tip_x = xs + size * np.sin(states.angle)
        tip_y = ys - size * np.cos(states.angle)
        floor = drop_floors(tip_x, ground.landing(self._landing, tip_x), ground)
        slant = float(np.tan(states.angle[0])) if len(states.angle) else 0.0
        landed = drop_landings(tip_y, floor, spec.fall * self.seeds.speed * short, slant)
        idx = np.nonzero(landed.splashing)[0]
        shapes = splash_shapes(landed.age[idx], self._spread[idx], splash_depth_scale(floor[idx], ground)) * short
        if isinstance(ground, IsoRainGround):   # plain rings: two droplets over a ring read as a tiny face close up (§102.9)
            shapes = shapes[:, :1]
        centres = np.stack([tip_x[idx] - landed.back[idx], floor[idx]], axis=1)[:, None, :] + shapes[:, :, :2]
        circle = self._circle[None, None, :, :2] * shapes[:, :, None, 2:] + centres[:, :, None, :]
        points = np.zeros((circle.shape[0] * circle.shape[1] * circle.shape[2], 3))
        points[:, :2] = circle.reshape(-1, 2)
        self.splashes.points = points
        self.splashes.fill_rgbas[:, 3] = min(SPLASH_OPACITY * self._boost, 1.0) * level
        if self.glow:
            self.splashes.stroke_rgbas[:, 3] = GLOW_HALO_OPACITY * level
        return landed.falling.astype(float)

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
        """Remove the field (its level stays 0) and note when it ended."""
        super().clean_up_from_scene(scene)
        self.field.level = 0.0
        self.field.ended = self.field.clock()


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


class Puddles(VGroup):
    """Flat puddles on a stage's ground (DESIGN.md §69.39): one ellipse per spot ``(x, y, half
    width)``, growing from nothing with the seconds of rain (:func:`puddle_growth`) from scene
    time ``start`` until ``ended()`` (``None`` while it rains), and staying when it stops.
    ``clock()`` gives the scene's time. (Plain functions, not the field or the scene: Manim
    deep-copies a mobject it fades in.)"""

    def __init__(
        self, spots: Sequence[tuple[float, float, float]], *, start: float, ended: Callable[[], float | None], clock: Callable[[], float]
    ) -> None:
        super().__init__()
        self.start = start
        self.ended = ended
        self.clock = clock
        self._shapes: list[tuple[np.ndarray, np.ndarray]] = []
        for x, y, half in spots:
            puddle = Ellipse(width=2 * half, height=2 * half * PUDDLE_FLAT, stroke_width=0)
            puddle.set_fill(PUDDLE_COLOR, opacity=PUDDLE_OPACITY)
            puddle.move_to([x, y, 0.0])
            self._shapes.append((puddle.points - np.array([x, y, 0.0]), np.array([x, y, 0.0])))
            self.add(puddle)
        self._grow()
        self.add_updater(lambda mob, dt: self._grow())

    def _grow(self) -> None:
        """Size every puddle for the rain so far; stops updating once they can grow no more."""
        now = self.clock()
        ended = self.ended()
        growth = puddle_growth((now if ended is None else min(now, ended)) - self.start)
        for puddle, (shape, centre) in zip(self.submobjects, self._shapes):
            puddle.points = shape * growth + centre
        if growth >= 1.0 or ended is not None:
            self.clear_updaters()


def settle_problem(kind: str, settings: ParticleSettings) -> tuple[str, str] | None:
    """``(option, message)`` when ``settle`` / ``settled`` do not fit ``kind`` (DESIGN.md §69.60)."""
    if settings.settle and kind != "snow":
        return "settle", f"only snow settles, not {kind}"
    if settings.settled and not settings.settle:
        return "settled", "settled is for snow that settles: add settle: true"
    return None


def storm_problem(kind: str, settings: ParticleSettings) -> tuple[str, str] | None:
    """``(option, message)`` when ``lightning`` is given to particles that are not rain (DESIGN.md §69.61)."""
    if settings.lightning is not False and kind != "rain":
        return "lightning", f"lightning flashes in rain only, not {kind} (or use the lightning action)"
    return None


def storm_every(settings: ParticleSettings) -> float | None:
    """Seconds between a rain field's strikes on average (``None``: no lightning)."""
    if settings.lightning is False:
        return None
    return STORM_EVERY if settings.lightning is True else float(settings.lightning)


def _ground_of(scene: NarratedScene, kind: str, settings: ParticleSettings) -> RainGroundSource | None:
    """Where the field's particles end: rain on the scene's ``rain_ground``, snow with ``settle`` on
    its ``snow_ground`` (a stage's, DESIGN.md §69.39, §69.60); ``None``: they fall through."""
    if kind == "rain":
        return getattr(scene, "rain_ground", None)
    if kind == "snow" and settings.settle:
        return getattr(scene, "snow_ground", None)
    return None


def particle_field(scene: NarratedScene, kind: str, settings: ParticleSettings) -> ParticleField:
    """A field of ``kind`` particles for ``scene``, starting now, drawn above everything on screen
    (not added to the scene). Fewer particles when the scene renders at preview quality
    (:attr:`NarratedScene.is_preview`). They drift with the scene's ``particle_wind`` when it has
    one (a windy stage, DESIGN.md §69.32); rain ends on the scene's ``rain_ground`` when it has
    one (a stage, §69.39), snow with ``settle`` on its ``snow_ground`` (§69.60). The scene's
    :meth:`~vidgen.scene.NarratedScene.particles_started` hears of the new field. A draft's field
    (:attr:`NarratedScene.is_draft`) has no particles and does not move (DESIGN.md §74)."""
    area = settings.area or [0.0, 0.0, 1.0, 1.0]
    colors = particle_colors(kind, settings.color, scene.theme)
    drawn = not getattr(scene, "is_draft", False)
    count = particle_count(kind, settings.density, area[2] * area[3], preview=scene.is_preview) if drawn else 0
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
        ground=_ground_of(scene, kind, settings) if drawn else None,
        seed=settings.seed,
        drawn=drawn,
        glow=settings.glow,
    )
    top = max((m.z_index for m in scene.get_mobject_family_members()), default=0)
    field.set_z_index(top + 1)
    started = getattr(scene, "particles_started", None)
    if started is not None:
        started(field, settings)
    return field
