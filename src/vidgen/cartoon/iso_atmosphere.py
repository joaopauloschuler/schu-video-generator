"""Weather on an iso place, drawn (DESIGN.md §105.4): the lights mirrored in its puddles at night
(:class:`IsoReflections`), fog lying over it in bands by depth (:class:`IsoFog`) and its plants
and balloons swaying in the wind (:class:`IsoSwayer`). The rules are in
:mod:`vidgen.cartoon.iso_weather` and :mod:`vidgen.cartoon.fog`.

Each is one of the stage's things that move by themselves (``update_to``, ``changing``,
``done``, ``movers``, ``region``): drawn again only while something changes (it rains, the light
or a light changes, the fog drifts, the wind blows), so a still night costs nothing.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from manim import Group, ImageMobject, Mobject, VGroup, VMobject

from vidgen.cartoon.fog import (
    FOG_DEPTHS,
    FOG_FEATHER,
    FOG_LAYERS,
    ISO_FOG_LAYER_SHARES,
    ISO_FOG_SCALE,
    ISO_FOG_THICKER,
    band_opacities,
    fog_shift,
    iso_band_outlines,
)
from vidgen.cartoon.iso_drawing import Shape, mix
from vidgen.cartoon.iso_driving import draw_sprite
from vidgen.cartoon.iso_pictures import IsoPuddles
from vidgen.cartoon.iso_stage import IsoView, canvas_center, detail_for
from vidgen.cartoon.iso_weather import (
    ISO_SWAYS,
    REFLECTION_HALO,
    REFLECTION_HALO_SHARE,
    REFLECTION_OPACITY,
    REFLECTION_WHITEN,
    IsoPuddle,
    Light,
    iso_sway_degrees,
    puddle_lights,
    puddle_outline,
    shimmered,
    still_reflection,
    sway_rows,
)
from vidgen.cartoon.shading import LIT
from vidgen.cartoon.weather_drawing import FogBand
from vidgen.world.iso_view import ISO_RISE, Box3, iso_point

Box = tuple[float, float, float, float]
_NOTHING = np.zeros((1, 1, 4), dtype=np.uint8)
#: The puddles' size (0..1) in steps this big for the reflections cut to them (each cut once).
SIZE_STEP = 0.02


class IsoReflections(VGroup):
    """The place's lights mirrored in ``puddles`` (an :class:`IsoPuddles`) at night: for each
    puddle the mirror image of each of ``lights`` (:func:`~vidgen.cartoon.iso_weather.glow_outlines`
    of the objects ``owners`` names, one per light) that falls in it, cut to it, as strong as
    the light is dark (``night()``: 0 by day .. 1 at night) and its object is lit (``lit(owner,
    now)``: 0..1), wobbling while it rains. ``busy(start, end)``: whether the light or a lit
    object may change then. Never graded by the stage's light (it is light)."""

    def __init__(self, puddles: IsoPuddles, lights: Sequence[Light], owners: Sequence[str], view: IsoView, *,
                 night: Callable[[], float], lit: Callable[[str, float], float], busy: Callable[[float, float], bool]) -> None:
        super().__init__()
        self.name = "iso_reflections"
        self.puddles, self.lights, self.owners, self.view = puddles, list(lights), list(owners), view
        self.night, self.lit, self.busy = night, lit, busy
        #: each reflection cut to its puddle, by (pair, glow's widening, the puddles' size in steps)
        self._outlines: dict[tuple[int, float, float], np.ndarray] = {}
        #: (puddle, light index, its glow, its piece)
        self.pairs: list[tuple[IsoPuddle, int, VMobject, VMobject]] = []
        for puddle in puddles.puddles:
            for k in puddle_lights(puddle, self.lights):
                color = self.lights[k][1]
                halo = VMobject().set_fill(color, opacity=0.0).set_stroke(width=0.0, opacity=0.0)
                piece = VMobject().set_fill(mix(color, "#FFFFFF", REFLECTION_WHITEN), opacity=0.0).set_stroke(width=0.0, opacity=0.0)
                self.pairs.append((puddle, k, halo, piece))
                self.add(halo, piece)
        boxes = [puddle_outline(p) for p in puddles.puddles] or [np.zeros((1, 2))]
        corners = np.concatenate(boxes)
        (u0, v0), (u1, v1) = corners.min(axis=0), corners.max(axis=0)
        pad = view.unit * 0.2
        self.box: Box = ((u0 - view.u0) * view.unit - pad, -(v1 - view.v0) * view.unit - pad,
                         (u1 - view.u0) * view.unit + pad, -(v0 - view.v0) * view.unit + pad)
        self.update_to(puddles.clock())

    def update_to(self, now: float) -> None:
        """Draw every reflection as it is at scene time ``now``."""
        night = self.night()
        size = self.puddles.size_at(now)
        rain = 1.0 if self.puddles.raining(now) else 0.0
        view = self.view
        grown = round(size / SIZE_STEP) * SIZE_STEP
        for j, (puddle, k, halo, piece) in enumerate(self.pairs):
            opacity = REFLECTION_OPACITY * night * self.lit(self.owners[k], now) if size > 0 else 0.0
            for member, widen, share in ((halo, REFLECTION_HALO, REFLECTION_HALO_SHARE), (piece, 0.0, 1.0)):
                outline = np.zeros((0, 2))
                if opacity > 0.01:
                    key = (j, widen, grown)
                    if key not in self._outlines:
                        self._outlines[key] = still_reflection(puddle, self.lights[k], size=grown, widen=widen)
                    outline = shimmered(self._outlines[key], now, rain, phase=puddle.seed % 628 / 100.0)
                if len(outline) < 3:
                    member.points = np.zeros((0, 3))
                    continue
                corners = np.zeros((len(outline) + 1, 3))
                corners[:-1, 0] = (outline[:, 0] - view.u0) * view.unit
                corners[:-1, 1] = -(outline[:, 1] - view.v0) * view.unit
                corners[-1] = corners[0]
                member.set_points_as_corners(corners)
                member.set_fill(opacity=opacity * share)

    def changing(self, start: float, end: float) -> bool:
        if not self.pairs:
            return False
        ended = self.puddles.ended()
        return ended is None or ended > start or self.busy(start, end) or self.puddles.size_at(start) != self.puddles.size_at(end)

    def done(self, now: float) -> bool:
        return not self.changing(now, math.inf)

    def movers(self) -> list[Mobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        return self.box


class IsoFog:
    """Fog over an iso place (DESIGN.md §105.4): a :class:`~vidgen.cartoon.weather_drawing.FogBand`
    per share of :data:`~vidgen.cartoon.fog.FOG_DEPTHS` (``bands``, back to front), each lying
    along the ground line of its depth (``depths``: ``x + y``; ``bases``: those lines' y on
    screen) from ``left`` to ``right``, its haze up to ``top`` (Manim units; ``unit``: a tile's
    width), at ``density``, drifting at ``drift`` and pushed by ``blown(now)`` (the stage's wind
    force added up; ``None``: calm). The stage draws each band right before the first body
    standing at its depth or nearer (each band's ``iso_depth``)."""

    def __init__(self, *, density: float, color: str, depths: Sequence[float], bases: Sequence[float], left: float, right: float, top: float,
                 unit: float, drift: float, seed: int, blown: Callable[[float], float] | None = None) -> None:
        self.bases, self.left, self.right, self.top, self.unit = list(bases), left, right, top, unit
        self.drift, self.seed, self.blown = drift, seed, blown
        self.bands = [FogBand(share, color, opacity, ISO_FOG_LAYER_SHARES)
                      for share, opacity in zip(FOG_DEPTHS, band_opacities(density * ISO_FOG_THICKER))]
        for band, depth in zip(self.bands, depths):
            band.iso_depth = depth
            band.name = f"iso_fog_{band.stage_depth:g}"
        self.update(0.0)

    @property
    def moves(self) -> bool:
        """Whether its waves drift (it drifts, or a wind may push it)."""
        return self.drift > 0 or self.blown is not None

    def update(self, now: float) -> None:
        """Draw every band for scene time ``now``."""
        blown = self.blown(now) if self.blown is not None else 0.0
        for index, (band, base) in enumerate(zip(self.bands, self.bases)):
            shift = fog_shift(now, blown, band.stage_depth, self.drift)
            band.show(iso_band_outlines(index, base, self.left, self.right, self.top, self.unit, shift, self.seed))

    def changing(self, start: float, end: float) -> bool:
        return self.moves and end > start

    def done(self, now: float) -> bool:
        return not self.moves

    def movers(self) -> list[Mobject]:
        return list(self.bands)

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        low = min(self.bases) - (FOG_LAYERS - 1) * FOG_FEATHER * ISO_FOG_SCALE * self.unit
        return (self.left, low, self.right, self.top)


class IsoSwayer(Group):
    """An object of an iso place swaying in the wind (DESIGN.md §105.4), named after it: a picture
    of its ``shapes`` (a *sprite*, at the level of detail the camera's zoom needs, as a driven
    vehicle's) bent each frame (:func:`~vidgen.cartoon.iso_weather.sway_rows`) about its foot,
    the middle of the bottom of its ``box``, by
    :func:`~vidgen.cartoon.iso_weather.iso_sway_degrees` of the wind's force where it stands
    (``force(now)``, signed); ``blowing(start, end)``: whether the wind may blow then."""

    iso_swayer = True

    def __init__(self, name: str, kind: str, shapes: Sequence[Shape], box: Box3, view: IsoView, *, scale: float, density: float,
                 frame_width: float, force: Callable[[float], float], blowing: Callable[[float, float], bool], outline: float = 1.0,
                 phase: float = 0.0) -> None:
        super().__init__()
        self.name, self.kind, self.shapes, self.iso_box, self.view = name, kind, list(shapes), box, view
        self.scale, self.density, self.frame_width, self.outline = scale, density, frame_width, outline
        self.force, self.blowing, self.phase = force, blowing, phase
        self.level = 0
        self.degrees = 0.0
        self._now = 0.0
        self._sprites: dict[int, tuple[np.ndarray, float, float, Box]] = {}
        self.slot = ImageMobject(_NOTHING.copy())
        self.slot.iso_tile = True   # drawn by the place's tile drawing (draw_tile)
        self.slot.scenery = True
        self.slot.name = name
        self.add(self.slot)
        self._show(0.0, force=True)

    def _sprite(self) -> tuple[np.ndarray, float, float, Box]:
        """Its picture at the level of detail now, padded each side for the lean: (pixels, foot
        row, height in pixels, where it goes on screen: left, bottom, right, top)."""
        if self.level not in self._sprites:
            sprite = draw_sprite(self.shapes, self.scale * 2**self.level, outline=self.outline)
            c, pixels = sprite.canvas, sprite.pixels[0]
            assert pixels is not None
            box = self.iso_box
            foot = (iso_point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2, box.z0)[1] - c.top) * c.scale
            drawn = np.flatnonzero(pixels[..., 3].max(axis=1) > 0)   # up to the top of its picture (balloons over their box)
            height = max((box.z1 - box.z0) * ISO_RISE * c.scale, foot - (float(drawn[0]) if len(drawn) else foot))
            sway = ISO_SWAYS[self.kind]
            most = min(iso_sway_degrees(self.kind, 1.0, 0.0, math.pi / 2), 60.0)
            pad = math.ceil(math.tan(math.radians(most)) * (1.0 - sway.bend_from) * height) + 2
            padded = np.zeros((pixels.shape[0], pixels.shape[1] + 2 * pad, 4), dtype=np.uint8)
            padded[:, pad:pad + pixels.shape[1]] = pixels
            cx, cy = canvas_center(c, self.view)
            width = padded.shape[1] / c.scale * self.view.unit
            tall = c.height / c.scale * self.view.unit
            self._sprites[self.level] = (padded, foot, height, (cx - width / 2, cy - tall / 2, cx + width / 2, cy + tall / 2))
        return self._sprites[self.level]

    def _show(self, now: float, force: bool = False) -> None:
        degrees = iso_sway_degrees(self.kind, self.force(now), now, self.phase)
        if not force and abs(degrees - self.degrees) < 0.05:
            return
        self.degrees = degrees
        pixels, foot, height, (left, bottom, right, top) = self._sprite()
        slot = self.slot
        slot.pixel_array = sway_rows(pixels, foot, height, degrees, ISO_SWAYS[self.kind].bend_from)
        slot.orig_alpha_pixel_array = slot.pixel_array[:, :, 3].copy()
        slot.points = np.array([[left, top, 0.0], [right, top, 0.0], [left, bottom, 0.0], [right, bottom, 0.0]])
        slot.iso_pieces = ((self.name, (left, bottom, right, top)),)
        if getattr(self, LIT, False):
            setattr(slot, LIT, True)

    def show_view(self, frame: Mobject) -> None:
        """Draw it at the level of detail the camera's view ``frame`` needs."""
        level = detail_for(self.frame_width / max(float(frame.width), 1e-9), self.density)
        if level != self.level:
            self.level = level
            self._show(self._now, force=True)

    def update_to(self, now: float) -> None:
        self._now = now
        self._show(now)

    def changing(self, start: float, end: float) -> bool:
        return self.blowing(start, end)

    def done(self, now: float) -> bool:
        return not self.blowing(now, math.inf)

    def movers(self) -> list[Mobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        return self._sprite()[3]


__all__ = ["IsoFog", "IsoReflections", "IsoSwayer"]
