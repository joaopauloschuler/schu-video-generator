"""Ambient life on an isometric place, drawn (DESIGN.md §105.7): background walkers, birds, a cat,
ducks, butterflies, fireflies and a fly, each moving as its plan says
(:class:`~vidgen.world.iso_ambient.AmbientPlan`).

A creature is an :class:`IsoCritter`: a body of the place like a character (a box for the draw
order, a front picture of what stands in front of it) drawn as a small picture (a *sprite*, as a
driven vehicle is, §105.1) of simple shapes in the place's style, made once per pose, frame of its
step or wing beat, facing and level of detail, and moved across the place. The stage says how
much of it shows (``seen(now)``: none in a close shot, butterflies by day, fireflies at night).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from manim import Group, ImageMobject, Mobject

from vidgen.cartoon.iso_drawing import Blobs, Disc, Poly, Shape, mix
from vidgen.cartoon.iso_driving import Sprite, draw_sprite
from vidgen.cartoon.iso_pictures import GlowTile, PoolTile
from vidgen.cartoon.iso_scenery import WATER_DEPTH
from vidgen.cartoon.iso_stage import IsoView, canvas_center, detail_for
from vidgen.cartoon.shading import LIT
from vidgen.world.iso_ambient import AmbientPlan, AmbientPose
from vidgen.world.iso_view import ISO_RISE, Box3, iso_point

Point3 = tuple[float, float, float]
Box = tuple[float, float, float, float]

#: How much smaller and greyer a ``muted`` background walker is (a main character stands about
#: 1.22 tile widths tall on the picture, a walker 1.02).
MUTED_SCALE = 0.86
MUTED_GREY = "#A3AAB3"
MUTED_SHARE = 0.45
#: Each kind's box for the draw order (tile units: half its width, its height).
CRITTER_SIZES: dict[str, tuple[float, float]] = {"walker": (0.2, 1.7), "bird": (0.1, 0.25), "cat": (0.18, 0.5), "duck": (0.15, 0.3),
                                                 "butterfly": (0.08, 0.12), "firefly": (0.05, 0.08), "fly": (0.04, 0.05)}
#: How far each kind's picture reaches round its point (tile widths: left / right, below, above).
CRITTER_REACH: dict[str, tuple[float, float, float]] = {"walker": (0.32, 0.08, 1.12), "bird": (0.2, 0.06, 0.24), "cat": (0.36, 0.08, 0.44),
                                                        "duck": (0.22, 0.08, 0.22), "butterfly": (0.12, 0.08, 0.12), "firefly": (0.4, 0.2, 0.2),
                                                        "fly": (0.06, 0.04, 0.06)}
#: Frames of a walker's stride (per two steps, every :data:`STRIDE` tiles walked), a cat's walk,
#: a bird's or a butterfly's wing beat; how many shades of a fading or blinking creature are drawn.
WALK_FRAMES = 6
STRIDE = 0.55
WING_FRAMES = 4
ALPHA_STEPS = 8

SHIRTS = ("#C8553D", "#3D6FC8", "#5BA36B", "#E0A040", "#8E5BB8", "#D97AA0", "#4AA8B0", "#7A7F8C")
TROUSERS = ("#3B4256", "#5B4636", "#2F3A4A", "#6A6F78", "#47566B")
SKINS = ("#F2C9A8", "#E3A982", "#C88B62", "#9C6440", "#6E4529")
HAIRS = ("#2A2220", "#5A3A22", "#A8702E", "#D9B36A", "#8A8A8A", "#1F1A17")
BIRDS = (("#8A6A4A", "#D9C4A0"), ("#7F8794", "#C9CED6"), ("#2B2B30", "#E6A33A"), ("#A9784E", "#E8D6B8"))
CATS = (("#E08A3C", "#F6D2A2"), ("#3A3A40", "#7A7A82"), ("#8E9096", "#D8DADF"), ("#F2EEE8", "#C9A27A"))
WINGS = (("#F2A93B", "#5A3A1A"), ("#5FA8E8", "#1E3A5A"), ("#F4E36A", "#4A4020"), ("#E86FA3", "#5A1E3A"), ("#FFFFFF", "#8A9AA8"))
INK = "#2B2B2B"
FIREFLY = "#F4FF8C"
FIREFLY_HALO = "#C8FF5A"


@dataclass(frozen=True)
class CritterLook:
    """A creature's colours (its body, a second colour, a third) and how big it is drawn."""

    main: str
    second: str
    third: str = INK
    fourth: str = INK
    scale: float = 1.0


def critter_look(kind: str, seed: int, *, muted: bool = False) -> CritterLook:
    """The look of a creature of ``kind`` from its ``seed``: a walker's shirt, trousers, skin and
    hair (``muted``: smaller, the colours greyer), a bird's, a cat's, a butterfly's colours."""
    def pick(options: Sequence[Any], salt: int) -> Any:
        return options[(seed // (salt * 7 + 1) + salt) % len(options)]

    if kind == "walker":
        colors = [pick(SHIRTS, 1), pick(TROUSERS, 2), pick(SKINS, 3), pick(HAIRS, 4)]
        if muted:
            colors = [mix(color, MUTED_GREY, MUTED_SHARE) for color in colors]
        return CritterLook(*colors, scale=MUTED_SCALE if muted else 1.0)
    if kind == "bird":
        return CritterLook(*pick(BIRDS, 1))
    if kind == "cat":
        return CritterLook(*pick(CATS, 1))
    if kind == "duck":
        return CritterLook("#8A6A4A", "#2E7A4A", "#E8A030")
    if kind == "butterfly":
        return CritterLook(*pick(WINGS, 1))
    if kind == "fly":
        return CritterLook("#2A2A30", "#C8D2DC")
    return CritterLook(FIREFLY, FIREFLY_HALO)


def _b(u: float, v: float, facing: int = 1, scale: float = 1.0) -> Point3:
    """A point ``u`` tile widths across (towards ``facing``) and ``v`` up the picture from a
    creature's point: drawn upright in the picture's plane."""
    u *= facing * scale
    h = v * scale / ISO_RISE
    return (u, -u, h)


def _quad(a: tuple[float, float], b: tuple[float, float], width: float, color: str, facing: int, scale: float, ink: bool = True) -> Poly:
    """A limb from ``a`` to ``b`` (picture offsets), ``width`` wide."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length * width / 2, dx / length * width / 2
    corners = [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]
    return Poly(tuple(_b(u, v, facing, scale) for u, v in corners), color, ink, holds_snow=False)


def _round(cx: float, cy: float, r: float, color: str, facing: int, scale: float, *, ink: bool = True) -> Blobs:
    return Blobs((_b(cx, cy, facing, scale),), (r * scale,), color, ink)


def _shadow(radius: float, scale: float = 1.0) -> Disc:
    return Disc((0.0, 0.0, 0.002), radius * scale, "#000000", False, 0.2, holds_snow=False)


def walker_shapes(look: CritterLook, *, facing: int, swing: float) -> list[Shape]:
    """A background walker side-on, ``swing`` (-1..1) through its stride."""
    s, f = look.scale, facing
    shirt, trousers, skin, hair = look.main, look.second, look.third, look.fourth
    leg = 0.1 * swing
    arm = 0.08 * swing
    out: list[Shape] = [_shadow(0.32, s)]
    out.append(_quad((-0.02, 0.8), (-0.02 - arm, 0.52), 0.06, mix(shirt, "#000000", 0.18), f, s))   # the far arm
    out.append(_quad((-0.03, 0.5), (-0.03 + leg, 0.02), 0.08, mix(trousers, "#000000", 0.15), f, s))
    out.append(_quad((0.03, 0.5), (0.03 - leg, 0.02), 0.08, trousers, f, s))
    out.append(Poly(tuple(_b(u, v, f, s) for u, v in ((-0.12, 0.46), (0.12, 0.46), (0.1, 0.84), (-0.1, 0.84))), shirt, holds_snow=False))
    out.append(_quad((0.02, 0.8), (0.02 + arm, 0.52), 0.06, shirt, f, s))   # the near arm
    out.append(_round(0.01, 0.93, 0.115, skin, f, s))
    cap = [(0.01 + 0.122 * math.cos(a), 0.935 + 0.122 * math.sin(a)) for a in np.linspace(0.15, math.pi + 0.35, 9)]
    out.append(Poly(tuple(_b(u, v, f, s) for u, v in [*cap, (-0.08, 0.9)]), hair, holds_snow=False))
    return out


def bird_shapes(look: CritterLook, *, facing: int, action: str, frame: int) -> list[Shape]:
    """A small bird: on the ground (``peck`` with its head down every other ``frame``, ``hop``,
    ``stand``) or flying (its wings up and down through the ``frame``s)."""
    f = facing
    body, belly = look.main, look.second
    flying = action == "fly"
    out: list[Shape] = [] if flying else [_shadow(0.1)]
    if not flying:
        out += [_quad((-0.01, 0.05), (-0.02, 0.0), 0.012, "#C77A3A", f, 1.0, False), _quad((0.02, 0.05), (0.03, 0.0), 0.012, "#C77A3A", f, 1.0, False)]
    out.append(Poly(tuple(_b(u, v, f) for u, v in ((-0.06, 0.08), (-0.15, 0.12), (-0.14, 0.07))), mix(body, "#000000", 0.2), holds_snow=False))
    out.append(Blobs((_b(-0.01, 0.075, f), _b(0.02, 0.07, f)), (0.055, 0.045), body))
    down = action == "peck" and frame % 2 == 1
    hx, hy = (0.075, 0.05) if down else (0.06, 0.125)
    out.append(_round(hx, hy, 0.04, body, f, 1.0))
    out.append(Poly(tuple(_b(u, v, f) for u, v in ((hx + 0.03, hy + 0.012), (hx + 0.075, hy - 0.006), (hx + 0.03, hy - 0.014))), "#E6A33A", holds_snow=False))
    out.append(_round(0.02, 0.06, 0.025, belly, f, 1.0, ink=False))
    if flying:
        lift = (0.12, 0.05, -0.05, 0.05)[frame % WING_FRAMES]
        out.append(Poly(tuple(_b(u, v, f) for u, v in ((-0.04, 0.09), (0.04, 0.09), (-0.02, 0.09 + lift + 0.04), (-0.1, 0.09 + lift))),
                        mix(body, "#000000", 0.25), holds_snow=False))
    return out


def cat_shapes(look: CritterLook, *, facing: int, action: str, frame: int) -> list[Shape]:
    """A cat: walking side-on (its legs through the ``frame``s), sitting (its tail swishing) or
    grooming (sitting, a paw to its face)."""
    f = facing
    fur, light = look.main, look.second
    dark = mix(fur, "#000000", 0.25)
    out: list[Shape] = [_shadow(0.22)]
    if action == "walk" or action == "stand":
        swing = math.sin(2 * math.pi * frame / WALK_FRAMES) if action == "walk" else 0.0
        for x, sign, color in ((-0.1, 1, dark), (0.1, -1, dark), (-0.08, -1, fur), (0.12, 1, fur)):
            out.append(_quad((x, 0.1), (x + 0.04 * sign * swing, 0.0), 0.035, color, f, 1.0))
        out.append(_quad((-0.15, 0.15), (-0.26, 0.24 + 0.03 * swing), 0.035, fur, f, 1.0))
        out.append(_quad((-0.26, 0.24 + 0.03 * swing), (-0.25, 0.33), 0.035, fur, f, 1.0))
        out.append(Blobs((_b(-0.09, 0.14, f), _b(0.0, 0.145, f), _b(0.09, 0.14, f)), (0.065, 0.07, 0.065), fur))
        head = (0.17, 0.2)
    else:
        tail = (0.0, 0.03, 0.05, 0.03)[frame % 4] if action == "sit" else 0.0
        out.append(_quad((-0.08, 0.04), (-0.2, 0.03 + tail), 0.035, fur, f, 1.0))
        out.append(Blobs((_b(-0.02, 0.09, f), _b(0.01, 0.17, f)), (0.09, 0.07), fur))
        out.append(_round(0.04, 0.12, 0.04, light, f, 1.0, ink=False))
        head = (0.04, 0.29) if action == "sit" else (0.06, 0.26)
    hx, hy = head
    for dx in (-0.035, 0.03):
        out.append(Poly(tuple(_b(u, v, f) for u, v in ((hx + dx - 0.022, hy + 0.035), (hx + dx + 0.005, hy + 0.1), (hx + dx + 0.03, hy + 0.035))),
                        fur, holds_snow=False))
    out.append(_round(hx, hy, 0.06, fur, f, 1.0))
    out.append(_round(hx + 0.045, hy - 0.005, 0.012, INK, f, 1.0, ink=False))
    if action == "groom":
        lift = (0.0, 0.025, 0.05)[frame % 3]
        out.append(_round(hx + 0.07, hy - 0.05 + lift, 0.026, light, f, 1.0))
    return out


def duck_shapes(look: CritterLook, *, facing: int, action: str) -> list[Shape]:
    """A duck on the water: swimming, gliding or dipping its head under (its tail up)."""
    f = facing
    ring = Disc((0.0, 0.0, 0.004), 0.32, "#FFFFFF", False, 0.22, holds_snow=False)
    if action == "dip":
        return [ring, Blobs((_b(0.02, 0.03, f), _b(-0.05, 0.06, f)), (0.06, 0.045), look.main),
                Poly(tuple(_b(u, v, f) for u, v in ((-0.06, 0.07), (-0.13, 0.16), (-0.02, 0.09))), mix(look.main, "#000000", 0.2), holds_snow=False)]
    out: list[Shape] = [ring, Blobs((_b(-0.05, 0.05, f), _b(0.03, 0.045, f)), (0.06, 0.065), look.main)]
    out.append(_round(0.08, 0.13, 0.045, look.second, f, 1.0))
    out.append(Poly(tuple(_b(u, v, f) for u, v in ((0.11, 0.135), (0.17, 0.12), (0.11, 0.115))), look.third, holds_snow=False))
    out.append(_round(-0.04, 0.07, 0.03, mix(look.main, "#FFFFFF", 0.3), f, 1.0, ink=False))
    return out


def butterfly_shapes(look: CritterLook, *, frame: int, flying: bool) -> list[Shape]:
    """A butterfly seen from the front: its wings open and closing through the ``frame``s (slowly
    while it rests)."""
    open_ = (1.0, 0.65, 0.25, 0.65)[frame % WING_FRAMES] if flying else (1.0, 0.8)[frame % 2]
    out: list[Shape] = []
    for side in (-1, 1):
        upper = ((0.0, 0.0), (0.075 * open_ * side, 0.065), (0.09 * open_ * side, 0.02))
        lower = ((0.0, -0.005), (0.06 * open_ * side, -0.04), (0.025 * open_ * side, -0.055))
        out.append(Poly(tuple(_b(u, v) for u, v in upper), look.main, holds_snow=False))
        out.append(Poly(tuple(_b(u, v) for u, v in lower), mix(look.main, look.second, 0.3), holds_snow=False))
    out.append(_quad((0.0, 0.03), (0.0, -0.04), 0.014, look.second, 1, 1.0, False))
    return out


def fly_shapes(look: CritterLook, *, frame: int) -> list[Shape]:
    """A house fly: a dark speck with blurred wings beating."""
    up = 0.02 if frame % 2 else 0.008
    return [Blobs((_b(-0.02, up), _b(0.02, up)), (0.016, 0.016), mix(look.second, "#FFFFFF", 0.4), False),
            _round(0.0, 0.0, 0.016, look.main, 1, 1.0, ink=False)]


def firefly_shapes(look: CritterLook) -> list[Shape]:
    """A firefly's light: a bright speck (a light the stage's dark does not dim) in a soft halo
    (a pool of light, as strong as the night is dark)."""
    halo = [Disc((0.0, 0.0, -0.001 * k), 0.5 * share, look.second, False, opacity, holds_snow=False, pool=True)
            for k, (share, opacity) in enumerate(((1.0, 0.2), (0.6, 0.3), (0.3, 0.5)))]
    speck = Poly(tuple(_b(0.04 * math.cos(a), 0.04 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 9)[:-1]), look.main, False, glow=True,
                 holds_snow=False)
    return [*halo, speck]


def critter_shapes(kind: str, look: CritterLook, pose: AmbientPose, frame: int) -> list[Shape]:
    """The shapes of a creature of ``kind`` in ``pose`` at its ``frame`` (:func:`frame_of`),
    with its point at the world's origin."""
    if kind == "walker":
        swing = math.sin(2 * math.pi * frame / WALK_FRAMES) if pose.action == "walk" else 0.0
        return walker_shapes(look, facing=pose.facing, swing=swing)
    if kind == "bird":
        return bird_shapes(look, facing=pose.facing, action=pose.action, frame=frame)
    if kind == "cat":
        return cat_shapes(look, facing=pose.facing, action=pose.action, frame=frame)
    if kind == "duck":
        return duck_shapes(look, facing=pose.facing, action=pose.action)
    if kind == "butterfly":
        return butterfly_shapes(look, frame=frame, flying=pose.action == "flutter")
    if kind == "fly":
        return fly_shapes(look, frame=frame)
    return firefly_shapes(look)


def frame_of(kind: str, pose: AmbientPose) -> int:
    """Which frame of its stride, step or wing beat a creature in ``pose`` shows."""
    if kind in ("walker", "cat") and pose.action == "walk":
        return math.floor(pose.phase / (STRIDE if kind == "walker" else 0.35) * WALK_FRAMES) % WALK_FRAMES
    rates = {"peck": 3.0, "fly": 9.0, "sit": 1.2, "groom": 3.0, "flutter": 11.0, "rest": 1.5}
    if kind == "fly":
        return math.floor(pose.phase * 24) % 2
    rate = rates.get(pose.action)
    return 0 if rate is None else math.floor(pose.phase * rate) % (WING_FRAMES if pose.action in ("fly", "flutter") else 4)


_NOTHING = np.zeros((1, 1, 4), dtype=np.uint8)


def _faded(pixels: np.ndarray | None, share: float) -> np.ndarray | None:
    """``pixels`` with their alpha times ``share``."""
    if pixels is None or share >= 1.0:
        return pixels
    out = pixels.copy()
    out[..., 3] = np.rint(out[..., 3] * share).astype(np.uint8)
    return out


class IsoCritter(Group):
    """A creature of a place's ambient life (DESIGN.md §105.7), named after its plan: its sprite
    where its ``plan`` (:class:`~vidgen.world.iso_ambient.AmbientPlan`) puts it at the scene time
    of :meth:`update_to`, shown ``seen(now)`` (0..1, the stage's say: hidden in close shots,
    butterflies by day, fireflies at night) times its own fading in and out; at the level of
    detail of the camera's zoom. It is a body of the place (``iso_feet``, :meth:`box`) and one of
    the stage's things that move by themselves (``update_to``, ``changing``, ``done``,
    ``movers``, ``region``)."""

    iso_ambient = True

    def __init__(self, plan: AmbientPlan, look: CritterLook, view: IsoView, *, scale: float, density: float, frame_width: float,
                 seen: Callable[[float], float], outline: float = 1.0) -> None:
        super().__init__()
        self.plan, self.kind, self.name, self.look, self.view = plan, plan.kind, plan.name, look, view
        self.scale, self.density, self.frame_width, self.outline, self.seen = scale, density, frame_width, outline, seen
        self.level = 0
        self.pose: AmbientPose = plan.at(0.0) or AmbientPose((0.0, 0.0, 0.0), 1, "stand", 0.0, 0.0)
        self.shown = 1.0
        self._now = 0.0
        self._sprites: dict[tuple[Any, ...], Sprite] = {}
        self._faded: dict[tuple[Any, ...], tuple[np.ndarray | None, ...]] = {}
        self._regions: dict[tuple[float, float], Box] = {}
        self._rect: Box | None = None
        self.slots: tuple[ImageMobject, ...] = tuple(kind(_NOTHING.copy()) for kind in (ImageMobject, PoolTile, GlowTile))
        for slot in self.slots:
            slot.iso_tile = True   # drawn by the place's tile drawing (draw_tile)
            slot.scenery = True    # a thing of the place: the camera may cut it, lint leaves it be
            slot.name = self.name
        self.add(*self.slots)
        self.refresh(0.0)

    # ----- where it is -------------------------------------------------------------------------------

    @property
    def iso_feet(self) -> Point3:
        return self.pose.point

    def box(self) -> Box3:
        """The box it is in now, for the draw order (tile units): inside the cell it is in."""
        half, height = CRITTER_SIZES[self.kind]
        x, y, z = self.pose.point
        if self.kind == "walker":
            height *= self.look.scale
        column, row = math.floor(x), math.floor(y)
        return Box3(max(x - half, column), max(y - half, row), z, min(x + half, column + 1), min(y + half, row + 1), z + height)

    def cell(self) -> tuple[int, int]:
        return (math.floor(self.pose.point[0]), math.floor(self.pose.point[1]))

    # ----- drawn ----------------------------------------------------------------------------------------

    def show_view(self, frame: Mobject) -> None:
        """Draw it at the level of detail the camera's view ``frame`` needs."""
        level = detail_for(self.frame_width / max(float(frame.width), 1e-9), self.density)
        if level != self.level:
            self.level = level
            self.refresh(self._now)

    def _sprite(self, pose: AmbientPose) -> tuple[tuple[Any, ...], Sprite]:
        frame = frame_of(self.kind, pose)
        action = "stand" if self.kind == "walker" and pose.action != "walk" else pose.action
        key = (action, frame, pose.facing if self.kind not in ("butterfly", "firefly", "fly") else 1, self.level)
        if key not in self._sprites:
            shapes = critter_shapes(self.kind, self.look, replace(pose, action=action), frame)
            self._sprites[key] = draw_sprite(shapes, self.scale * 2**self.level, outline=self.outline)
        return key, self._sprites[key]

    def refresh(self, now: float | None = None) -> None:
        """Show it as its plan has it at scene time ``now`` (default: the last time shown)."""
        now = self._now if now is None else float(now)
        self._now = now
        pose = self.plan.at(now)
        self.shown = 0.0 if pose is None else pose.shown * self.seen(now)
        if pose is not None:
            self.pose = pose
        if self.shown <= 0.02:
            for slot in self.slots:
                self._empty(slot)
            return
        key, sprite = self._sprite(self.pose)
        glow = self.pose.glow if self.kind == "firefly" else 1.0
        steps = (round(self.shown * ALPHA_STEPS), round(glow * ALPHA_STEPS))
        fkey = (*key, *steps)
        if fkey not in self._faded:
            share, light = steps[0] / ALPHA_STEPS, steps[1] / ALPHA_STEPS
            self._faded[fkey] = tuple(_faded(pixels, share * (light if k else 1.0)) for k, pixels in enumerate(sprite.pixels))
        x, y, z = self.pose.point
        if self.kind == "duck":
            z -= WATER_DEPTH
        cx, cy = canvas_center(sprite.canvas, self.view)
        du, dv = iso_point(x, y, z)
        centre = (cx + du * self.view.unit, cy - dv * self.view.unit)
        width = sprite.canvas.width / sprite.canvas.scale * self.view.unit
        height = sprite.canvas.height / sprite.canvas.scale * self.view.unit
        left, bottom = centre[0] - width / 2, centre[1] - height / 2
        self._rect = (left, bottom, left + width, bottom + height)
        for slot, pixels in zip(self.slots, self._faded[fkey]):
            if pixels is None:
                self._empty(slot)
                continue
            slot.pixel_array = pixels
            slot.orig_alpha_pixel_array = pixels[:, :, 3].copy()
            slot.points = np.array([[left, bottom + height, 0.0], [left + width, bottom + height, 0.0], [left, bottom, 0.0], [left + width, bottom, 0.0]])
            slot.iso_pieces = ((self.name, (left, bottom, left + width, bottom + height)),)
        if getattr(self, LIT, False):
            setattr(self.slots[0], LIT, True)

    def rect(self) -> Box | None:
        """Where its picture is on screen now (Manim units: left, bottom, right, top; ``None``:
        not shown): its front picture is drawn only there."""
        return self._rect if self.shown > 0.02 else None

    @staticmethod
    def _empty(slot: ImageMobject) -> None:
        """Nothing in ``slot``, on no pixel (the tile drawing skips it)."""
        slot.pixel_array = _NOTHING
        slot.orig_alpha_pixel_array = _NOTHING[:, :, 3].copy()
        middle = slot.points.mean(axis=0) if len(slot.points) else np.zeros(3)
        slot.points = np.array([middle] * 4)
        slot.iso_pieces = ()

    def screen_box(self, point: Point3) -> Box:
        """Where its picture may lie on screen with its point at ``point`` (Manim units: left,
        bottom, right, top)."""
        side, below, above = CRITTER_REACH[self.kind]
        u, v = iso_point(*point)
        view = self.view
        x, y = (u - view.u0) * view.unit, -(v - view.v0) * view.unit
        return (x - side * view.unit, y - below * view.unit, x + side * view.unit, y + above * view.unit)

    # ----- a thing that moves by itself (the stage's living things) -----------------------------------------

    def update_to(self, now: float) -> None:
        self.refresh(now)

    def changing(self, start: float, end: float) -> bool:
        return True

    def done(self, now: float) -> bool:
        return False

    def movers(self) -> list[Mobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        """Where it goes on screen between scene times ``start`` and ``end`` (at most a minute on)."""
        key = (round(start, 3), round(min(end, start + 60.0), 3))
        if key not in self._regions:
            boxes = [self.screen_box(pose.point) for pose in self.plan.samples(*key)] or [self.screen_box(self.pose.point)]
            self._regions[key] = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        return self._regions[key]


__all__ = ["ALPHA_STEPS", "CRITTER_REACH", "CRITTER_SIZES", "MUTED_SCALE", "STRIDE", "WALK_FRAMES", "WING_FRAMES", "CritterLook",
           "IsoCritter", "bird_shapes", "butterfly_shapes", "cat_shapes", "critter_look", "critter_shapes", "duck_shapes", "firefly_shapes",
           "fly_shapes", "frame_of", "walker_shapes"]
