"""Light on a stage (DESIGN.md §69.31): the colour grade of a ``light`` preset or tint, fades
between grades over time (:func:`fade_at`, also the wind's, §69.32), the night's stars and the soft shadows under what stands on the
ground. No manim: :mod:`vidgen.cartoon.shading` draws them.

A *grade* multiplies each colour channel of what the stage draws (its background, layers,
props and characters; never speech bubbles, captions or other text) by a factor and adds a
small *glow*: a tint ``t`` at ``strength`` ``s`` gives the factor ``1 - s * (1 - t)`` per
channel (white or ``s`` 0: no change); morning and sunset add a warm glow, since a factor alone
turns a blue sky grey instead of warm. It also says how bright the stars are (0 = none) and how
dark the shadows are (a factor of :data:`SHADOW_OPACITY`). Colours are sRGB components in 0..1.
"""

from __future__ import annotations

import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from functools import cached_property
from typing import Any, Protocol, TypeVar

import numpy as np

from vidgen.lint.color import hex_rgb
from vidgen.particles import particle_count, particle_seeds

#: The light presets, in the order the docs list them.
LIGHT_PRESETS = ("day", "morning", "sunset", "night", "indoor", "blue_hour")
#: Each preset: tint, strength, glow, star brightness, shadow factor. ``day`` changes nothing.
#: ``blue_hour`` (DESIGN.md §107, §108) is a crisp, clean night: a cool indigo multiply with no
#: lift in the blacks, colours made more saturated before the tint (they keep their own hues, not a
#: lavender haze), mid tones darkened and the tones stretched (contrast), dark enough for lamps,
#: windows and neon to glow and pool.
PRESET_LIGHTS: dict[str, tuple[str, float, tuple[float, float, float], float, float]] = {
    "day": ("#FFFFFF", 0.0, (0.0, 0.0, 0.0), 0.0, 1.0),
    "morning": ("#FFE4CC", 0.3, (0.05, 0.035, 0.02), 0.0, 0.8),
    "sunset": ("#FF8A5C", 0.55, (0.13, 0.04, 0.03), 0.0, 0.9),
    "night": ("#2A3C78", 0.72, (0.0, 0.0, 0.0), 1.0, 0.45),
    "indoor": ("#E6BC7E", 0.4, (0.0, 0.0, 0.0), 0.0, 0.75),
    "blue_hour": ("#3555B8", 0.56, (0.0, 0.0, 0.0), 0.7, 0.6),
}
#: The presets that keep more (or less) than all of each colour's saturation (before the tint).
PRESET_SATURATION: dict[str, float] = {"blue_hour": 1.6}
#: The presets that bend the tones: (gamma, contrast, vivid) (:class:`LightGrade`, DESIGN.md §108).
PRESET_TONES: dict[str, tuple[float, float, float]] = {"blue_hour": (1.2, 1.3, 1.15)}
#: The tone a ``contrast`` stretches about (0..1): below it darker, above it brighter.
CONTRAST_PIVOT = 0.35
#: Strength of a ``{tint}`` light that gives none.
DEFAULT_STRENGTH = 0.5
#: Seconds a ``light`` beat action fades over by default.
LIGHT_FADE_SECONDS = 2.0

#: Stars: the share of a frame's usual sparkles, their size as a share of a sparkle's, and the
#: share of the sky (from its top) they are scattered over, and the free band (a share of the frame
#: height) kept between them and the highest character's head at the start.
STAR_DENSITY = 1.0
STAR_SIZE = 0.7
STAR_SKY = 0.75
STAR_HEAD_ROOM = 0.04

#: Shadows: opacity in daylight on the ground, width under a character (its heights), width under
#: a prop (its widths), height as a share of the width, and how fast one shrinks as its owner
#: rises (per owner height above the ground).
SHADOW_OPACITY = 0.3
SHADOW_WIDTH = 0.55
PROP_SHADOW_WIDTH = 0.9
SHADOW_FLATNESS = 0.16
SHADOW_SHRINK = 1.5

RGB = tuple[float, float, float]
T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


@dataclass(frozen=True)
class LightGrade:
    """How a light changes the stage: each RGB channel ``c`` becomes ``c * multiply + glow``
    (clipped to 0..1); ``stars`` is their brightness (0 = none), ``shadow`` a factor of the
    shadows' opacity."""

    multiply: RGB = (1.0, 1.0, 1.0)
    glow: RGB = (0.0, 0.0, 0.0)
    stars: float = 0.0
    shadow: float = 1.0
    #: How much of each colour's saturation is kept before the multiply (1: all; a flashback's
    #: faded colours less, DESIGN.md §100.12).
    saturation: float = 1.0
    #: The saturation scaled after the multiply and glow (1: unchanged; above 1 the tinted colours
    #: get their hues back, DESIGN.md §108).
    vivid: float = 1.0
    #: A power on each channel before the multiply (1: none; above 1 the mid tones darken while
    #: whites stay, a crisper night, DESIGN.md §108).
    gamma: float = 1.0
    #: A contrast stretch about :data:`CONTRAST_PIVOT` after the multiply and glow (1: none).
    contrast: float = 1.0

    @property
    def curved(self) -> bool:
        """Whether it bends the tones (``gamma`` or ``contrast`` not 1)."""
        return abs(self.gamma - 1.0) > 1e-9 or abs(self.contrast - 1.0) > 1e-9

    @property
    def changes_colors(self) -> bool:
        """Whether it changes any colour (``day`` does not)."""
        return (any(abs(m - 1.0) > 1e-9 for m in self.multiply) or any(abs(g) > 1e-9 for g in self.glow)
                or abs(self.saturation - 1.0) > 1e-9 or abs(self.vivid - 1.0) > 1e-9 or self.curved)

    @cached_property
    def arrays(self) -> tuple[np.ndarray, np.ndarray | None]:
        """``multiply`` and ``glow`` as arrays (``glow`` ``None`` when it adds nothing), made once:
        the camera grades every lit shape on every frame it draws."""
        glow = np.asarray(self.glow, dtype=float) if any(self.glow) else None
        return np.asarray(self.multiply, dtype=float), glow


def tint_grade(
    tint: str, strength: float, *, glow: RGB = (0.0, 0.0, 0.0), stars: float = 0.0, shadow: float = 1.0,
) -> LightGrade:
    """The grade of a ``#hex`` ``tint`` at ``strength`` 0..1 (0: no change, 1: multiply by the
    tint), plus ``glow`` added to every colour."""
    strength = min(max(float(strength), 0.0), 1.0)
    multiply = tuple(1.0 - strength * (1.0 - c) for c in hex_rgb(tint))
    return LightGrade(multiply, tuple(glow), stars, shadow)  # type: ignore[arg-type]


def light_grade(light: str | tuple[str, float]) -> LightGrade:
    """The grade of a preset (:data:`LIGHT_PRESETS`) or of ``(#hex tint, strength)``;
    ``ValueError`` for an unknown preset."""
    if isinstance(light, tuple):
        return tint_grade(*light)
    if light not in PRESET_LIGHTS:
        raise ValueError(f"unknown light {light!r}; presets: {', '.join(LIGHT_PRESETS)}")
    tint, strength, glow, stars, shadow = PRESET_LIGHTS[light]
    grade = tint_grade(tint, strength, glow=glow, stars=stars, shadow=shadow)
    if light in PRESET_SATURATION or light in PRESET_TONES:
        gamma, contrast, vivid = PRESET_TONES.get(light, (1.0, 1.0, 1.0))
        grade = replace(grade, saturation=PRESET_SATURATION.get(light, 1.0), gamma=gamma, contrast=contrast, vivid=vivid)
    return grade


def blend_grades(a: LightGrade, b: LightGrade, share: float) -> LightGrade:
    """``share`` 0..1 of the way from ``a`` to ``b`` (every field linearly)."""
    s = min(max(float(share), 0.0), 1.0)
    def mix(x: float, y: float) -> float:
        return x * (1.0 - s) + y * s   # exactly ``a`` at 0 and ``b`` at 1

    multiply = tuple(mix(x, y) for x, y in zip(a.multiply, b.multiply))
    glow = tuple(mix(x, y) for x, y in zip(a.glow, b.glow))
    def keep(x: float, y: float) -> float:
        return x if x == y else mix(x, y)

    return LightGrade(multiply, glow, mix(a.stars, b.stars), mix(a.shadow, b.shadow), keep(a.saturation, b.saturation),  # type: ignore[arg-type]
                      keep(a.vivid, b.vivid), keep(a.gamma, b.gamma), keep(a.contrast, b.contrast))


#: A lamp's light on what stands near it (an iso place's lamp at night, DESIGN.md §89.13): its
#: colour and strength as a light, the share of the way from the stage's light to it where it
#: falls fully, and how dark the stage's light must be (one minus its mean ``multiply``) for the
#: lamp to show fully (less in a lighter one; by day nothing).
LAMP_LIGHT = ("#FFD98A", 0.3)
LAMP_LIFT = 0.6
LAMP_DARK = 0.45


def lamp_lit(base: LightGrade, share: float) -> LightGrade:
    """``base`` (the stage's light now) with a lamp's light falling at ``share`` 0..1 on what it
    grades: :data:`LAMP_LIFT` of the way to :data:`LAMP_LIGHT` at full share in the dark; ``base``
    itself by day or out of the light."""
    dark = min(max((1.0 - sum(base.multiply) / 3) / LAMP_DARK, 0.0), 1.0)
    lift = min(max(float(share), 0.0), 1.0) * dark * LAMP_LIFT
    if lift <= 1e-6:
        return base
    return blend_grades(base, tint_grade(*LAMP_LIGHT), lift)


#: A lamp's pool of light on the ground (an iso place's, DESIGN.md §104): how much of it shows by
#: day, and the curve from there to full as the light darkens (:data:`LAMP_DARK` dark: full),
#: so it is strong at night, gentle at sunset or indoors and barely seen by day.
POOL_DAY = 0.1
POOL_CURVE = 0.7


def pool_strength(grade: LightGrade) -> float:
    """How strongly (0..1) a lamp's pool of light shows under ``grade`` (the stage's light now):
    :data:`POOL_DAY` by day, 1 in the dark."""
    dark = min(max((1.0 - sum(grade.multiply) / 3) / LAMP_DARK, 0.0), 1.0)
    return POOL_DAY + (1.0 - POOL_DAY) * dark ** POOL_CURVE


#: A day passing (the ``time_of_day`` action, DESIGN.md §105.3): its fade by default (seconds),
#: how dark (:func:`darkness`) the light is where lamps switch on as it darkens (dusk; the
#: ``sunset`` preset is past it) and off as it brightens (dawn), how long each light takes to
#: come on or go out, and the most a light is early or late (seconds; a share of the fade at
#: most), so a street's lamps come on one after another, never in one frame.
TIME_OF_DAY_SECONDS = 6.0
DUSK_DARK = 0.35
AUTO_SWITCH_SECONDS = 1.2
AUTO_SPREAD = 0.9
AUTO_SPREAD_SHARE = 0.2


#: A day passing from daylight straight to night goes through a sunset, and from night to full day
#: through a morning: the share of the fade spent reaching it, and how dark the light it starts
#: from must be (:func:`darkness`) at most (to night) or at least (to day).
TWILIGHT_SHARE = 0.5
TWILIGHT_FROM_DAY = 0.2
TWILIGHT_FROM_NIGHT = 0.9


def day_stages(before: LightGrade, preset: str) -> list[tuple[str, float]]:
    """The presets a ``time_of_day`` fade from ``before`` to ``preset`` passes through, each with
    the share of the fade at which it is reached: ``[("sunset", 0.5), ("night", 1.0)]`` from a
    light day to night, ``[("morning", 0.5), ("day", 1.0)]`` from night to day, else
    ``[(preset, 1.0)]``."""
    dark = darkness(before)
    if preset in ("night", "blue_hour") and dark <= TWILIGHT_FROM_DAY:
        return [("sunset", TWILIGHT_SHARE), ("night", 1.0)]
    if preset == "day" and dark >= TWILIGHT_FROM_NIGHT:
        return [("morning", TWILIGHT_SHARE), ("day", 1.0)]
    return [(preset, 1.0)]


def darkness(grade: LightGrade) -> float:
    """How dark ``grade`` is, 0 (day) .. 1 (night and darker): one minus its mean ``multiply``
    over :data:`LAMP_DARK` (the measure of :func:`lamp_lit` and :func:`pool_strength`)."""
    return min(max((1.0 - sum(grade.multiply) / 3) / LAMP_DARK, 0.0), 1.0)


def _unsmooth(value: float) -> float:
    """The share ``s`` 0..1 where smoothstep(``s``) is ``value`` (bisection)."""
    low, high = 0.0, 1.0
    for _ in range(40):
        mid = (low + high) / 2
        if _smooth(mid) < value:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def dusk_crossing(before: LightGrade, after: LightGrade, start: float, seconds: float) -> tuple[float, bool] | None:
    """When a fade from ``before`` to ``after`` (from scene time ``start`` over ``seconds``,
    eased as :func:`fade_at` eases it) crosses :data:`DUSK_DARK`, and whether the lights then go
    on (dusk) or off (dawn); ``None`` when it does not cross."""
    a, b = darkness(before), darkness(after)
    if (a < DUSK_DARK) == (b < DUSK_DARK) or abs(b - a) < 1e-9:
        return None
    if seconds <= 0:
        return float(start), b >= DUSK_DARK
    share = _unsmooth((DUSK_DARK - a) / (b - a))
    return float(start) + share * float(seconds), b >= DUSK_DARK


def auto_switch_time(name: str, crossing: float, start: float, seconds: float) -> float:
    """When the light ``name`` starts to switch for a dusk or dawn at scene time ``crossing``
    during a fade from ``start`` over ``seconds``: early or late by up to :data:`AUTO_SPREAD`
    (at most :data:`AUTO_SPREAD_SHARE` of the fade), the same for a name in every render, and
    inside the fade."""
    spread = min(AUTO_SPREAD, AUTO_SPREAD_SHARE * max(float(seconds), 0.0))
    offset = (zlib.crc32(name.encode("utf-8")) % 1000 / 999 * 2 - 1) * spread
    return min(max(crossing + offset, float(start)), float(start) + max(float(seconds), 0.0))


def lifted(grade: LightGrade, share: float, toward: RGB = (1.0, 1.0, 1.0)) -> LightGrade:
    """``grade`` lifted ``share`` 0..1 of the way back to the colours as drawn: a fill light on
    what it grades (a stage's ``fill_light`` on its characters, a visitor's own ``glow``,
    DESIGN.md §100.15). ``toward`` is the multiply it lifts to (a coloured fill light, e.g. a
    warm key, ``fill_color``, DESIGN.md §108; white: the colours as drawn). Its stars, shadows and
    saturation are kept, but a boost above 1 (``saturation``, ``vivid``) and the tone curve
    (``gamma``, ``contrast``) relax as far towards 1; 0 returns ``grade`` itself."""
    s = min(max(float(share), 0.0), 1.0)
    if s <= 1e-9:
        return grade

    def relax(value: float) -> float:
        return value + (1.0 - value) * s

    multiply = tuple(m + (t - m) * s for m, t in zip(grade.multiply, toward))
    glow = tuple(g * (1.0 - s) for g in grade.glow)
    saturation = grade.saturation if grade.saturation <= 1.0 else relax(grade.saturation)
    return replace(grade, multiply=multiply, glow=glow, saturation=saturation, vivid=relax(grade.vivid), gamma=relax(grade.gamma),
                   contrast=relax(grade.contrast))


def _graded_colors(colors: np.ndarray, grade: LightGrade, scale: float) -> None:
    """Grade ``colors`` (rows of RGB in 0..``scale``) in place, except the final clip: saturation,
    gamma, multiply, glow, contrast, vivid."""
    if grade.saturation != 1.0:
        _desaturate(colors, grade.saturation)
    if grade.gamma != 1.0:
        np.clip(colors, 0.0, scale, out=colors)
        colors /= scale
        np.power(colors, grade.gamma, out=colors)
        colors *= scale
    colors *= np.asarray(grade.multiply, dtype=colors.dtype)
    if any(grade.glow):
        colors += scale * np.asarray(grade.glow, dtype=colors.dtype)
    if grade.contrast != 1.0:
        pivot = scale * CONTRAST_PIVOT
        colors -= pivot
        colors *= grade.contrast
        colors += pivot
    if grade.vivid != 1.0:
        _desaturate(colors, grade.vivid)


def grade_rgbas(rgbas: np.ndarray, grade: LightGrade) -> np.ndarray:
    """RGBA rows (components 0..1) with the grade applied; alpha unchanged; a new array."""
    graded = np.array(rgbas, dtype=float, copy=True)
    colors = graded[..., :3]
    if not grade.curved and grade.vivid == 1.0:   # the plain path, as before §108
        multiply, glow = grade.arrays
        if grade.saturation != 1.0:
            _desaturate(colors, grade.saturation)
        colors *= multiply
        if glow is not None:
            colors += glow
        if glow is not None or grade.saturation > 1.0:   # more saturated colours may leave 0..1
            np.clip(colors, 0.0, 1.0, out=colors)
        return graded
    _graded_colors(colors, grade, 1.0)
    np.clip(colors, 0.0, 1.0, out=colors)
    return graded


def grade_pixels(pixels: np.ndarray, grade: LightGrade) -> np.ndarray:
    """An 8-bit RGB or RGBA picture with the grade applied; alpha unchanged; a new array."""
    graded = pixels.astype(np.float32)
    if not grade.curved and grade.vivid == 1.0:   # the plain path, as before §108
        if grade.saturation != 1.0:
            _desaturate(graded[..., :3], grade.saturation)
        graded[..., :3] = graded[..., :3] * np.asarray(grade.multiply, dtype=np.float32) + 255 * np.asarray(grade.glow, dtype=np.float32)
        return np.clip(np.rint(graded), 0, 255).astype(pixels.dtype)
    colors = graded[..., :3].copy()
    _graded_colors(colors, grade, 255.0)
    graded[..., :3] = colors
    return np.clip(np.rint(graded), 0, 255).astype(pixels.dtype)


#: Rec. 709 luma weights (a colour's grey, for :attr:`LightGrade.saturation`).
LUMA = (0.2126, 0.7152, 0.0722)


def _desaturate(colors: np.ndarray, keep: float) -> None:
    """Move ``colors`` (rows of RGB, in place) towards their grey, keeping ``keep`` of their
    saturation."""
    grey = colors @ np.asarray(LUMA, dtype=colors.dtype)
    colors *= keep
    colors += (1.0 - keep) * grey[..., None]


@dataclass(frozen=True)
class LightChange:
    """A change of light: from whatever it is at ``start`` (scene seconds) to ``grade`` over
    ``seconds`` (0: at once)."""

    start: float
    seconds: float
    grade: LightGrade

    @property
    def end(self) -> float:
        """When it is over."""
        return self.start + max(self.seconds, 0.0)

    @property
    def value(self) -> LightGrade:
        """What it fades to (its ``grade``; :func:`fade_at`)."""
        return self.grade


class Fading(Protocol[T_co]):
    """A change of a stage setting that fades (:class:`LightChange`, the wind's
    :class:`~vidgen.cartoon.wind.WindChange`): from ``start`` (scene seconds) to ``value`` over
    ``seconds`` (0: at once), over at ``end``."""

    @property
    def start(self) -> float: ...
    @property
    def seconds(self) -> float: ...
    @property
    def end(self) -> float: ...
    @property
    def value(self) -> T_co: ...


def _smooth(share: float) -> float:
    s = min(max(share, 0.0), 1.0)
    return s * s * (3.0 - 2.0 * s)


def fade_at(base: T, changes: Sequence[Fading[T]], now: float, blend: Callable[[T, T, float], T]) -> T:
    """A faded setting at scene time ``now``: ``base``, then each change from its ``start`` on (in
    start order; a change that starts during another fades from where that one is then), eased
    (smoothstep) by ``blend(from, to, share)``."""
    ordered = sorted(changes, key=lambda c: c.start)
    value = base
    for k, change in enumerate(ordered):
        if now < change.start:
            break
        start = fade_at(base, ordered[:k], change.start, blend)
        share = 1.0 if change.seconds <= 0 else _smooth((now - change.start) / change.seconds)
        value = blend(start, change.value, share)
    return value


def changing(changes: Sequence[Fading[Any]], start: float, end: float) -> bool:
    """Whether any change is under way between scene times ``start`` and ``end`` (a stage then
    redraws on every frame). A change at once counts when it falls after ``start`` (one at
    ``start`` is drawn by then)."""
    return any(c.start < end and c.end > start if c.seconds > 0 else start < c.start < end for c in changes)


def light_at(base: LightGrade, changes: Sequence[LightChange], now: float) -> LightGrade:
    """The light at scene time ``now`` (:func:`fade_at` with :func:`blend_grades`)."""
    return fade_at(base, changes, now, blend_grades)


def light_changing(changes: Sequence[LightChange], start: float, end: float) -> bool:
    """Whether any light change is under way between scene times ``start`` and ``end``
    (:func:`changing`)."""
    return changing(changes, start, end)


@dataclass(frozen=True)
class Stars:
    """The night's stars: ``x``, ``y`` (fractions of the sky area, ``y`` from its top), ``size``
    (shorter sides of the frame) and ``brightness`` (0..1), one value per star."""

    x: np.ndarray
    y: np.ndarray
    size: np.ndarray
    brightness: np.ndarray

    def __len__(self) -> int:
        return len(self.x)


def night_stars(area_share: float, *, seed: int = 1, preview: bool = False) -> Stars:
    """The stars over a sky ``area_share`` frames large: the sparkles particles' seeded positions
    (:func:`~vidgen.particles.particle_seeds`; :data:`STAR_DENSITY` of their count, fewer at
    preview quality), :data:`STAR_SIZE` of their size, a brightness from each one's speed."""
    count = particle_count("sparkles", STAR_DENSITY, area_share, preview=preview)
    seeds = particle_seeds("sparkles", count, seed)
    brightness = np.clip(0.35 + 0.65 * (seeds.speed - 0.5), 0.0, 1.0)
    return Stars(seeds.x, seeds.y, seeds.size * STAR_SIZE, brightness)


@dataclass(frozen=True)
class ShadowEllipse:
    """A shadow on the ground: its middle (``x``, ``y``), ``width``, ``height`` and ``opacity``."""

    x: float
    y: float
    width: float
    height: float
    opacity: float


def shadow_ellipse(x: float, ground_y: float, width: float, *, above: float = 0.0, size: float = 1.0, strength: float = 1.0) -> ShadowEllipse:
    """The shadow of something ``width`` wide (already scaled for its depth) whose feet are at
    ``x``, ``above`` units over its ground line ``ground_y``: on that line, smaller and fainter the
    higher it is (``size``: its height, the unit of how high), :data:`SHADOW_OPACITY` times
    ``strength`` (the light's ``shadow``) when on the ground."""
    rise = max(float(above), 0.0) / max(float(size), 1e-9)
    shrink = 1.0 / (1.0 + SHADOW_SHRINK * rise)
    w = max(float(width), 0.0) * shrink
    return ShadowEllipse(float(x), float(ground_y), w, w * SHADOW_FLATNESS, SHADOW_OPACITY * max(strength, 0.0) * shrink)
