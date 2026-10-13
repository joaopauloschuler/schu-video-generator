"""Drawing snow that settles and fog on a stage (DESIGN.md §69.60; the maths in
:mod:`vidgen.cartoon.snow` and :mod:`vidgen.cartoon.fog`).

:class:`SettledSnow` grows a :class:`SnowBlanket` on the ground and a :class:`SnowCap` on each
prop that holds snow while a settling snow field falls; :class:`StageFog` drifts the
:class:`FogBand` s a stage draws between its things by depth. Both are what the stage calls a thing
that moves by itself (DESIGN.md §69.54): ``update(now)``, ``changing(start, end)``, ``movers()``
and ``region(start, end)``, so only what changes leaves Manim's static image.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from manim import Mobject, VGroup, VMobject

from vidgen.cartoon.fog import FOG_DEPTHS, FOG_LAYER_SHARES, band_box, band_opacities, band_outlines, fog_shift, layer_opacity
from vidgen.cartoon.living import Box, union_box
from vidgen.cartoon.snow import (
    BLANKET_OPACITY,
    BLANKET_RISE,
    CAP_COLUMNS,
    THIN_SNOW,
    blanket_cover,
    blanket_outline,
    cap_outlines,
    cap_thickness,
    curve_segments,
    settle_amount,
    settled_seconds,
    top_line,
)


def polygon_points(corners: np.ndarray) -> np.ndarray:
    """A closed path through ``corners`` (``(n, 2)``) with straight sides, as Manim's cubic points
    (four per side)."""
    start = np.asarray(corners, dtype=float)
    end = np.roll(start, -1, axis=0)
    thirds = [start, start + (end - start) / 3, start + 2 * (end - start) / 3, end]
    points = np.zeros((len(start) * 4, 3))
    points[:, :2] = np.stack(thirds, axis=1).reshape(-1, 2)
    return points


def paths_points(outlines: Sequence[np.ndarray]) -> np.ndarray:
    """Several closed paths in one mobject's points (counter-clockwise ones fill, clockwise ones
    inside them are holes: Cairo fills by winding)."""
    parts = [polygon_points(o) for o in outlines if len(o) >= 3]
    return np.concatenate(parts) if parts else np.zeros((0, 3))


def _filled(mobject: VMobject, color: str, opacity: float) -> VMobject:
    mobject.set_fill(color, opacity=opacity)
    mobject.set_stroke(color, width=0.0, opacity=0.0)
    return mobject


def prop_top_line(prop: Mobject, columns: int = CAP_COLUMNS) -> tuple[np.ndarray, np.ndarray] | None:
    """The upper edge of what ``prop`` draws now (its members with points that show), as
    :func:`~vidgen.cartoon.snow.top_line` columns (``None``: it draws nothing)."""
    shown = [
        m.points for m in prop.family_members_with_points()
        if isinstance(m, VMobject) and (m.get_fill_opacity() > 0.01 or (m.get_stroke_opacity() > 0.01 and m.get_stroke_width() > 0))
    ]
    segments = [curve_segments(points) for points in shown]
    segments = [s for s in segments if len(s)]
    if not segments:
        return None
    return top_line(np.concatenate(segments), columns)


class SnowBlanket(VGroup):
    """The settled snow on a stage's ground: the blanket (holes under the shelters) and, in the
    holes, a thinner layer (:data:`~vidgen.cartoon.snow.THIN_SNOW` of its opacity), whose outlines
    and opacity :class:`SettledSnow` sets."""

    def __init__(self, color: str) -> None:
        super().__init__(_filled(VMobject(), color, 0.0), _filled(VMobject(), color, 0.0))
        for part in self.submobjects:
            part.points = np.zeros((0, 3))

    def show(self, outline: np.ndarray, bare: Sequence[np.ndarray], opacity: float) -> None:
        """Draw the blanket ``outline`` with holes ``bare`` (clockwise) at ``opacity``, and the
        holes thinly covered."""
        cover, thin = self.submobjects
        cover.points = paths_points([outline, *bare]) if opacity > 0 else np.zeros((0, 3))
        cover.set_fill(opacity=opacity)
        thin.points = paths_points([b[::-1] for b in bare]) if opacity > 0 and bare else np.zeros((0, 3))
        thin.set_fill(opacity=opacity * THIN_SNOW)


class SnowCap(VMobject):
    """The snow on a prop's top line ``xs``, ``ys``: ``full`` thick (Manim units) at the full
    layer; ``cap_of`` is the prop's name."""

    def __init__(self, xs: np.ndarray, ys: np.ndarray, full: float, color: str, cap_of: str) -> None:
        super().__init__()
        self.xs, self.ys, self.full = xs, ys, full
        self.cap_of = cap_of
        self.points = np.zeros((0, 3))
        _filled(self, color, 1.0)

    def show(self, amount: float) -> None:
        """The cap for ``amount`` (0..1) of the full layer."""
        self.points = paths_points(cap_outlines(self.xs, self.ys, cap_thickness(self.xs, self.ys, self.full, amount)))

    def box(self) -> Box:
        """Where the full cap lies (left, bottom, right, top)."""
        return (float(self.xs[0]), float(self.ys.min() - self.full), float(self.xs[-1]), float(self.ys.max() + self.full))


class SettledSnow:
    """The layer a settling snow field leaves (DESIGN.md §69.60): its blanket over the ground area
    (``left`` .. ``right``, from ``bottom`` up to ``back``, Manim units; thin snow in the ``bare``
    patches) and its caps, for snow from scene time ``start`` until ``ended()`` (``None`` while it
    snows) at ``density``, with ``settled`` seconds of snowfall already lying."""

    def __init__(
        self, blanket: SnowBlanket, caps: Sequence[SnowCap], *, area: tuple[float, float, float, float], frame_height: float,
        bare: Sequence[np.ndarray], start: float, ended: Callable[[], float | None], density: float, settled: float, seed: int,
    ) -> None:
        self.blanket = blanket
        self.caps = list(caps)
        self.area = area
        self.frame_height = frame_height
        self.bare = list(bare)
        self.start = start
        self.ended = ended
        self.density = density
        self.settled = settled
        self.seed = seed
        #: the amount drawn now (``None``: not drawn yet)
        self.amount: float | None = None
        self.update(start)

    def amount_at(self, now: float) -> float:
        """The layer's amount (0..1) at scene time ``now``, in steps."""
        return settle_amount(settled_seconds(now, self.start, self.ended(), self.settled), self.density)

    def update(self, now: float) -> None:
        """Draw the layer for scene time ``now`` (only when its step changed)."""
        amount = self.amount_at(now)
        if amount == self.amount:
            return
        self.amount = amount
        left, right, bottom, back = self.area
        outline = blanket_outline(left, right, bottom, back, amount * BLANKET_RISE * self.frame_height, self.frame_height, self.seed)
        self.blanket.show(outline, self.bare, BLANKET_OPACITY * blanket_cover(amount))
        for cap in self.caps:
            cap.show(amount)

    def changing(self, start: float, end: float) -> bool:
        """Whether the layer grows between scene times ``start`` and ``end``."""
        return self.amount_at(start) != self.amount_at(end)

    def done(self, now: float) -> bool:
        """Whether it will not grow any more after scene time ``now``."""
        return self.amount_at(now) == self.amount_at(math.inf)

    def movers(self) -> list[Mobject]:
        """What changes as it grows: the blanket and the caps."""
        return [self.blanket, *self.caps]

    def region(self, start: float, end: float) -> Box:
        """Where it may draw (the full layer's box)."""
        left, right, bottom, back = self.area
        box: Box = (left, bottom, right, back + 2 * BLANKET_RISE * self.frame_height)
        for cap in self.caps:
            box = union_box(box, cap.box())
        return box


class FogBand(VGroup):
    """One band of fog: :data:`~vidgen.cartoon.fog.FOG_LAYERS` shapes in ``color``, ``opacity``
    where all overlap; ``stage_depth`` is where it lies (the stage draws it in front of everything
    deeper)."""

    def __init__(self, depth: float, color: str, opacity: float) -> None:
        super().__init__(*[_filled(VMobject(), color, layer_opacity(opacity, share)) for share in FOG_LAYER_SHARES])
        self.stage_depth = depth
        self.name = f"fog_{depth:g}"

    def show(self, outlines: Sequence[np.ndarray]) -> None:
        """Set each layer's outline."""
        for layer, outline in zip(self.submobjects, outlines):
            layer.points = polygon_points(outline)


class StageFog:
    """A stage's fog (DESIGN.md §69.60): a :class:`FogBand` per depth of
    :data:`~vidgen.cartoon.fog.FOG_DEPTHS` (``bands``, back to front) at ``density`` across
    ``left`` .. ``right`` on the ground line ``ground`` (a fraction of the frame height), drifting
    at ``drift`` and pushed by ``blown(now)`` (the stage's wind force added up; ``None``: calm)."""

    def __init__(
        self, *, density: float, color: str, ground: float, left: float, right: float, frame_height: float,
        drift: float, seed: int, blown: Callable[[float], float] | None = None,
    ) -> None:
        self.density = density
        self.ground, self.left, self.right, self.frame_height = ground, left, right, frame_height
        self.drift = drift
        self.seed = seed
        self.blown = blown
        self.bands = [FogBand(depth, color, opacity) for depth, opacity in zip(FOG_DEPTHS, band_opacities(density))]
        self.update(0.0)

    @property
    def moves(self) -> bool:
        """Whether its waves drift (it drifts, or a wind may push it)."""
        return self.drift > 0 or self.blown is not None

    def update(self, now: float) -> None:
        """Draw every band for scene time ``now``."""
        blown = self.blown(now) if self.blown is not None else 0.0
        for index, band in enumerate(self.bands):
            shift = fog_shift(now, blown, band.stage_depth, self.drift)
            band.show(band_outlines(index, self.ground, self.left, self.right, self.frame_height, shift, self.seed))

    def changing(self, start: float, end: float) -> bool:
        """Whether it changes between scene times ``start`` and ``end`` (always, when it moves)."""
        return self.moves and end > start

    def movers(self) -> list[Mobject]:
        """The bands."""
        return list(self.bands)

    def region(self, start: float, end: float) -> Box:
        """The box the bands stay in."""
        boxes = [band_box(k, self.ground, self.left, self.right, self.frame_height) for k in range(len(self.bands))]
        box = boxes[0]
        for other in boxes[1:]:
            box = union_box(box, other)
        return box


__all__ = ["FogBand", "SettledSnow", "SnowBlanket", "SnowCap", "StageFog", "paths_points", "polygon_points", "prop_top_line"]
