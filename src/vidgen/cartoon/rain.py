"""Rain on a stage's ground (DESIGN.md §69.39). No manim.

On a ``stage``, each rain drop ends on the ground instead of falling past it: it gets a *landing
line* (seeded once per drop) in the stage's landing band, from :data:`LANDING_FRONT` frame
heights in front of the ground line up to the top of the ground area (``ground_top``), so drops
land at different depths. A *shelter* (an open umbrella, held or standing, or a tree's crown)
is a simple box: a drop over it that would land at or behind it stops at its top edge. Where a
drop's tip reaches its floor it vanishes and a small splash (seeded droplets) shows there for
:data:`SPLASH_SECONDS`. With ``puddles: true`` flat puddles grow on the ground while it rains.

Everything is in Manim units of the scene (``y`` up), as numpy arrays of one value per drop, so
it is tested without rendering; :mod:`vidgen.particle_field` draws it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from vidgen.cartoon.stage import FAR_RISE, depth_scale

#: How far in front of the ground line (a fraction of the frame height) drops still land.
LANDING_FRONT = 0.05
#: A shelter keeps dry the drops that land behind its front edge: this far (a fraction of the
#: frame height) in front of the ground line where it stands, and everything behind. Twice the
#: landing band's front, so a shelter up to a depth of about 0.4 keeps its whole column dry (rain
#: passing in front of a crown read as rain through it).
SHELTER_REACH = 0.1
#: Props that shelter from the rain: kind -> the shape that does (``None``: any shape).
SHELTER_PROPS: dict[str, str | None] = {"tree": None, "pine": None, "umbrella": "open", "beach_umbrella": None}
#: Seconds a splash shows after a drop lands.
SPLASH_SECONDS = 0.3
#: A splash's flat ring: its half width at the start and at the end (shorter sides of the frame).
SPLASH_RING = (0.008, 0.024)
#: How high a splash's droplets jump (shorter sides) and their radius at the start.
SPLASH_JUMP = 0.022
SPLASH_DROPLET = 0.0045
#: How opaque splashes are (a drop's own opacity is fainter: splashes are small).
SPLASH_OPACITY = 0.85
#: Puddles: how many per frame width of the stage, their half widths (shorter sides, at depth 0),
#: height over width, and the seconds of rain they take to grow to full size.
PUDDLES_PER_FRAME = 4
PUDDLE_SIZE = (0.05, 0.1)
PUDDLE_FLAT = 0.22
PUDDLE_GROW_SECONDS = 10.0


@dataclass(frozen=True)
class ShelterBox:
    """A box rain does not fall through: ``left`` to ``right`` (x), its ``top`` edge, where drops
    stop, and ``feet``, the y of the ground line where it stands (a held umbrella: its holder's)."""

    left: float
    right: float
    top: float
    feet: float

    def covers(self, x: np.ndarray, landing: np.ndarray, reach: float) -> np.ndarray:
        """Which drops at ``x`` landing on the lines ``landing`` it keeps dry: over it, landing at
        most ``reach`` in front of its feet, and below its top."""
        return (x >= self.left) & (x <= self.right) & (landing >= self.feet - reach) & (landing < self.top)


@dataclass(frozen=True)
class RainGround:
    """Where rain ends on a stage now (Manim units): the ground line ``ground``, the landing band
    ``front`` .. ``back`` (``back`` is the top of the ground area), the frame's height and the
    shelters."""

    ground: float
    front: float
    back: float
    frame_height: float
    shelters: tuple[ShelterBox, ...] = ()

    @property
    def rise(self) -> float:
        """Manim units from depth 0 to depth 1 (:data:`~vidgen.cartoon.stage.FAR_RISE`)."""
        return FAR_RISE * self.frame_height

    def depth(self, y: np.ndarray) -> np.ndarray:
        """The depth of a line at height ``y`` (negative in front of the ground line)."""
        return (y - self.ground) / self.rise

    def landing(self, shares: np.ndarray, x: np.ndarray) -> np.ndarray:
        """The y of each drop's landing line (drops at ``x``; the band is the same everywhere)."""
        return landing_lines(shares, self)


#: Where a drop that misses an iso place ends: far under the frame (it falls through).
NO_FLOOR = -1e9


@dataclass(frozen=True)
class IsoRainGround(RainGround):
    """Where rain ends on an iso place (DESIGN.md §89.11): seen from above, its whole ground is a
    landing band, so a drop at ``x`` lands between the front and the back edge of the place's
    picture there (``xs`` sorted, ``fronts`` and ``backs`` their y), within the camera's view
    (``ground`` its bottom, ``back`` its top); a drop beside the place, or landing on one of
    the ``bodies`` (boxes ``(left, bottom, right, top)``: the characters, so no splash shows on a
    face), falls through. No depth: a splash is the same size everywhere (no perspective).
    ``lift(x, y)``: how much higher (Manim units) a drop that would land on the ground at
    (``x``, ``y``) lands, on what keeps the rain off there (a roof, a crown, a bridge's deck;
    DESIGN.md §90.2; ``None``: nothing does)."""

    xs: tuple[float, ...] = ()
    fronts: tuple[float, ...] = ()
    backs: tuple[float, ...] = ()
    bodies: tuple[tuple[float, float, float, float], ...] = ()
    lift: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = field(default=None, compare=False)

    def depth(self, y: np.ndarray) -> np.ndarray:
        return np.zeros_like(np.asarray(y, dtype=float))

    def landing(self, shares: np.ndarray, x: np.ndarray) -> np.ndarray:
        xs = np.asarray(self.xs)
        if len(xs) < 2:
            return np.full(len(shares), NO_FLOOR)
        front = np.maximum(np.interp(x, xs, self.fronts), self.ground)
        back = np.minimum(np.interp(x, xs, self.backs), self.back)
        lines = front + shares * (back - front)
        missed = (x < xs[0]) | (x > xs[-1]) | (back <= front)
        if self.lift is not None:
            lines = lines + self.lift(np.asarray(x, dtype=float), lines)
        for left, bottom, right, top in self.bodies:
            missed |= (x >= left) & (x <= right) & (lines >= bottom) & (lines <= top)
        return np.where(missed, NO_FLOOR, lines)


def rain_ground(ground: float, top: float, frame_height: float, shelters: Sequence[ShelterBox] = ()) -> RainGround:
    """The :class:`RainGround` of a stage whose ground line is ``ground`` and ground area reaches
    up to ``top`` (both fractions of the frame height above its bottom edge, as the stage's
    ``ground`` and ``ground_top``), in a frame ``frame_height`` units tall centred on 0."""
    front = max(ground - LANDING_FRONT, 0.0)
    ys = [(share - 0.5) * frame_height for share in (ground, front, max(top, ground))]
    return RainGround(ys[0], ys[1], ys[2], frame_height, tuple(shelters))


def prop_shelter(kind: str, shape: str | None, box: tuple[float, float, float], feet: float) -> ShelterBox | None:
    """The shelter of a prop of ``kind`` showing ``shape`` whose drawing spans ``box`` (left,
    right, top) and stands on the ground line ``feet``: a tree's crown or an open umbrella; ``None``
    for any other prop (a closed umbrella too)."""
    if kind not in SHELTER_PROPS:
        return None
    wanted = SHELTER_PROPS[kind]
    if wanted is not None and shape != wanted:
        return None
    left, right, top = box
    return ShelterBox(left, right, top, feet)


def landing_shares(count: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Each drop's landing line as a share of the landing band (0 front, 1 back) and its splash's
    spread (0..1, how far its droplets fly sideways), drawn from ``seed`` (a stream of its own,
    so the drops' positions stay those of Step 76)."""
    rng = np.random.default_rng([seed, 105])
    return rng.uniform(0.0, 1.0, count), rng.uniform(0.0, 1.0, count)


def landing_lines(shares: np.ndarray, ground: RainGround) -> np.ndarray:
    """The y of each drop's landing line in the band of ``ground``."""
    return ground.front + shares * (ground.back - ground.front)


def drop_floors(x: np.ndarray, landing: np.ndarray, ground: RainGround) -> np.ndarray:
    """Where each drop at ``x`` ends: its landing line, or the top of the highest shelter that
    keeps it dry (:meth:`ShelterBox.covers`)."""
    floor = landing.copy()
    reach = SHELTER_REACH * ground.frame_height
    for box in ground.shelters:
        under = box.covers(x, landing, reach)
        floor = np.where(under, np.maximum(floor, box.top), floor)
    return floor


@dataclass(frozen=True)
class Landings:
    """Drops against their floors at one time: ``falling`` (still above the floor: drawn),
    ``splashing`` (landed less than :data:`SPLASH_SECONDS` ago), ``age`` (seconds since it
    landed; 0 where not splashing) and ``back`` (how far right it moved since it landed, Manim
    units: the splash is that far to its left)."""

    falling: np.ndarray
    splashing: np.ndarray
    age: np.ndarray
    back: np.ndarray


def drop_landings(tip: np.ndarray, floor: np.ndarray, speed: np.ndarray, slant: float) -> Landings:
    """Which drops still fall and which splash, from their lower tips' y ``tip``, floors, fall
    ``speed`` (Manim units per second, above 0) and ``slant`` (sideways units per unit of fall)."""
    below = np.maximum(floor - tip, 0.0)
    falling = tip > floor
    age = below / np.maximum(speed, 1e-9)
    splashing = ~falling & (age < SPLASH_SECONDS)
    return Landings(falling, splashing, np.where(splashing, age, 0.0), below * slant)


def splash_shapes(age: np.ndarray, spread: np.ndarray, scale: np.ndarray) -> np.ndarray:
    """Ellipses of each splash at ``age`` seconds: an array ``(splashes, 3, 4)`` of ``(dx, dy,
    rx, ry)`` from the landing point, in shorter sides of the frame: a flat ring widening and
    thinning out, and two droplets thrown up and out (left and right, ``spread`` 0..1) falling
    back, shrinking to nothing at :data:`SPLASH_SECONDS`. ``scale``: the depth scale."""
    u = np.clip(age / SPLASH_SECONDS, 0.0, 1.0)
    rest = 1.0 - u
    ring = SPLASH_RING[0] + (SPLASH_RING[1] - SPLASH_RING[0]) * u
    side = (0.6 + 0.8 * spread) * SPLASH_RING[1] * u
    jump = 4.0 * SPLASH_JUMP * u * rest  # up and back down: highest half-way
    out = np.zeros((len(u), 3, 4))
    out[:, 0] = np.stack([np.zeros_like(u), np.zeros_like(u), ring, 0.22 * ring * rest], axis=1)
    droplet = SPLASH_DROPLET * rest
    for k, sign in ((1, -1.0), (2, 1.0)):
        out[:, k] = np.stack([sign * side, jump + droplet, droplet, droplet], axis=1)
    return out * scale[:, None, None]


def puddle_spots(
    count: int, seed: int, left: float, right: float, ground: RainGround, short_side: float
) -> list[tuple[float, float, float]]:
    """``count`` puddles ``(x, y, half width)`` on the landing band of ``ground`` between ``left``
    and ``right`` (Manim units), drawn from ``seed``, none under a shelter, sized by their depth
    (:data:`PUDDLE_SIZE` in shorter sides ``short_side`` at depth 0). Fewer when the shelters
    leave no room."""
    rng = np.random.default_rng([seed, 1105])
    reach = SHELTER_REACH * ground.frame_height
    spots: list[tuple[float, float, float]] = []
    for _ in range(count * 8):
        if len(spots) == count:
            break
        x = rng.uniform(left, right)
        y = rng.uniform(ground.front, ground.back)
        half = rng.uniform(*PUDDLE_SIZE) * short_side * depth_scale(min(max((y - ground.ground) / ground.rise, 0.0), 1.0))
        xs, ys = np.array([x - half, x, x + half]), np.full(3, y)
        if any(box.covers(xs, ys, reach).any() for box in ground.shelters):
            continue
        spots.append((float(x), float(y), float(half)))
    return spots


def puddle_count(stage_frames: float) -> int:
    """How many puddles a stage ``stage_frames`` frame widths wide gets."""
    return max(1, round(PUDDLES_PER_FRAME * stage_frames))


def puddle_growth(rained: float) -> float:
    """A puddle's size (0..1 of its full size) after ``rained`` seconds of rain: easing out to
    full at :data:`PUDDLE_GROW_SECONDS`."""
    u = min(max(rained / PUDDLE_GROW_SECONDS, 0.0), 1.0)
    return 1.0 - (1.0 - u) ** 2


def splash_depth_scale(floor: np.ndarray, ground: RainGround) -> np.ndarray:
    """How big a splash on the line ``floor`` is drawn: the depth scale of that line, between
    the back of the stage and a little larger in front."""
    return depth_scale(np.clip(ground.depth(floor), -0.5, 1.0))  # type: ignore[arg-type]


__all__ = [
    "NO_FLOOR",
    "IsoRainGround",
    "LANDING_FRONT",
    "PUDDLE_GROW_SECONDS",
    "SHELTER_PROPS",
    "SHELTER_REACH",
    "SPLASH_SECONDS",
    "Landings",
    "RainGround",
    "ShelterBox",
    "drop_floors",
    "drop_landings",
    "landing_lines",
    "landing_shares",
    "prop_shelter",
    "puddle_count",
    "puddle_growth",
    "puddle_spots",
    "rain_ground",
    "splash_depth_scale",
    "splash_shapes",
]
