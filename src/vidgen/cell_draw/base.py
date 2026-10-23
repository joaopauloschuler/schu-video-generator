"""The drawing toolkit of a cell world (DESIGN.md §95.6): Bézier paths in scene units from the
world's µm shapes and regions, theme-aware colours, and drawn pieces with a level-of-detail
feature each, whose opacity and stroke width the camera sets — keeping any dimming or
highlighting an action applied meanwhile (an action's change is measured against what the level
of detail last set and kept as an emphasis factor)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np
from manim import VGroup, VMobject

from vidgen.cellworld.curves import Cubic, shape_curves

#: Stroke widths on screen (pixels): membranes, the plasma membrane, particles' rims.
MEMBRANE_PX, PLASMA_PX, RIM_PX = 1.6, 2.4, 0.8


# ----- colours -----------------------------------------------------------------------------------


def _rgb(color: str) -> tuple[float, float, float]:
    c = color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb: Sequence[float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02X}" for v in rgb)


def blend(a: str, b: str, t: float) -> str:
    """``a`` at opacity ``t`` over ``b``."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex([x * t + y * (1 - t) for x, y in zip(ra, rb)])


def luminance(color: str) -> float:
    r, g, b = _rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@dataclass(frozen=True)
class CellColors:
    """The colours of a cell drawing for a theme: ``background`` and ``text`` (theme hex);
    fills are the kinds' hues mixed into the background, outlines darker (light themes) or
    lighter (dark themes) versions of the hues."""

    background: str
    text: str

    @property
    def dark(self) -> bool:
        return luminance(self.background) < 0.4

    def fill(self, hue: str, strength: float = 0.35) -> str:
        return blend(hue, self.background, min(1.0, strength * (1.5 if self.dark else 1.0)))

    def ink(self, hue: str) -> str:
        return blend(hue, "#FFFFFF", 0.78) if self.dark else blend(hue, "#000000", 0.62)

    def solid(self, hue: str) -> str:
        return blend(hue, self.background, 0.85)

    def light(self, hue: str, t: float = 0.5) -> str:
        """``hue`` lightened (dark themes: towards white as well, so it reads on the dark)."""
        return blend("#FFFFFF", self.solid(hue), t)


# ----- Bézier paths ------------------------------------------------------------------------------


def curves_array(curves: Iterable[Cubic]) -> list[np.ndarray]:
    """World Bézier pieces as numpy arrays (z = 0)."""
    return [np.array([[p[0], p[1], 0.0] for p in cv]) for cv in curves]


def path_mobject(curves: Iterable[np.ndarray], unit: float, origin: np.ndarray) -> VMobject:
    """A VMobject of Bézier pieces given in µm (several closed paths are several subpaths)."""
    pieces = list(curves)
    mob = VMobject()
    if pieces:
        mob.set_points(np.concatenate(pieces) * unit + origin)
    return mob


def shape_arrays(shape: object, grow: float = 0.0) -> list[np.ndarray]:
    """One closed path round ``shape`` (µm) as numpy pieces, grown by ``grow`` µm."""
    return curves_array(shape_curves(shape, grow))


# ----- level-of-detail pieces ----------------------------------------------------------------------


@dataclass
class Piece:
    """A drawn piece and how level of detail treats it: shown with ``feature``'s weight (an
    expression of :func:`feature_weight`; ``None``: always), its full fill and stroke opacity,
    its stroke width in pixels — at least ``px``, or its true width ``true_um`` (µm) when that
    is wider on screen. ``emphasis`` is what actions made of it (a dim: below 1), ``written`` the
    opacity last set, ``points`` its outline while hidden (a hidden piece has no points, so it
    costs nothing to draw)."""

    mobject: VMobject
    feature: str | None
    fill: float
    stroke: float
    px: float
    true_um: float | None = None
    lod: float = -1.0
    emphasis: tuple[float, float] = (1.0, 1.0)
    written: tuple[float, float] = (-1.0, -1.0)
    width: float = -1.0
    points: np.ndarray | None = field(default=None, repr=False)
    play_lod: float = 1.0
    keep: bool = False
    owner: str | None = None
    play_alpha: tuple[float, float] = (0.0, 0.0)
    shown: int = -10


def feature_weight(feature: str | None, weights: dict[str, float]) -> float:
    """The weight of a feature expression: ``None`` 1; ``a&b`` the product; ``!a`` one minus."""
    if feature is None:
        return 1.0
    total = 1.0
    for term in feature.split("&"):
        value = weights[term.lstrip("!")]
        total *= 1.0 - value if term.startswith("!") else value
    return total


class Pieces:
    """The registered pieces of a drawing and their opacity bookkeeping."""

    def __init__(self) -> None:
        self.pieces: list[Piece] = []
        #: the thing pieces are being registered for (their ``owner``), and the emphasis actions
        #: last gave each owner's pieces (fill 0, stroke 1)
        self.owner: str | None = None
        self.recent: dict[tuple[str | None, int], float] = {}
        #: animations begun so far (a piece's ``shown``: the count when it last came into view)
        self.plays = 0

    def add(self, mob: VMobject, feature: str | None, fill: float, stroke: float, px: float, true_um: float | None, keep: bool = False) -> Piece:
        """Register ``mob``; ``keep``: never take its points away while hidden (a piece the scene
        moves, such as a label)."""
        piece = Piece(mob, feature, fill, stroke, px, true_um, keep=keep, owner=self.owner)
        self.pieces.append(piece)
        return piece

    def apply(self, weights: dict[str, float], px_per_um: float, stroke_unit: float) -> None:
        """Each piece's opacity from its feature's weight (times its emphasis) and its stroke
        width in pixels."""
        for piece in self.pieces:
            self._sync(piece)
            factor = feature_weight(piece.feature, weights)
            px = max(piece.px, piece.true_um * px_per_um) if piece.true_um is not None else piece.px
            width = px * stroke_unit
            if abs(factor - piece.lod) < 1e-4 and abs(width - piece.width) <= 1e-9 * max(1.0, width):
                continue
            if piece.lod <= 0.0 < factor:
                # coming into view: as dimmed (or not) as the rest of its thing is now
                piece.emphasis = (self.recent.get((piece.owner, 0), piece.emphasis[0]), self.recent.get((piece.owner, 1), piece.emphasis[1]))
                piece.shown = self.plays
            piece.lod, piece.width = factor, width
            self._write(piece, width)

    def sync(self) -> None:
        """Take in what actions changed since the last write (every frame)."""
        for piece in self.pieces:
            if self._sync(piece):
                self._write(piece, piece.width)

    def mark_play(self) -> None:
        """Remember each piece's level of detail and opacity when an animation begins: an
        action's colours are computed from them."""
        self.plays += 1
        for piece in self.pieces:
            piece.play_lod = max(piece.lod, 0.0)
            piece.play_alpha = (max(piece.written[0], 0.0), max(piece.written[1], 0.0))

    def _sync(self, piece: Piece) -> bool:
        mob = piece.mobject
        if piece.written[0] < 0:
            return False
        current = (float(mob.get_fill_opacity()) if piece.fill else 0.0, float(mob.get_stroke_opacity()) if piece.stroke else 0.0)
        changed = False
        emphasis = list(piece.emphasis)
        for k, (now, written, full) in enumerate(zip(current, piece.written, (piece.fill, piece.stroke))):
            if full == 0 or abs(now - written) < 1e-4:
                continue
            base = full * piece.play_lod
            known = self.recent.get((piece.owner, k))
            if now < 1e-4 and known is not None and known > 1e-3 and self.plays - piece.shown <= 1:
                # an action still writing colours it read while this piece was hidden (its
                # zoom came meanwhile): as the rest of its thing, not invisible
                emphasis[k] = known
            elif piece.play_alpha[k] > 1e-3 and piece.play_lod >= 0.5:
                emphasis[k] = min(1.0, now / base) if now <= base * 1.0001 else 1.0
                self.recent[(piece.owner, k)] = emphasis[k]
            elif (piece.owner, k) in self.recent:
                # (nearly) hidden when the action began, shown by a zoom since: as the rest of its thing
                emphasis[k] = self.recent[(piece.owner, k)]
            changed = True
        piece.emphasis = (emphasis[0], emphasis[1])
        if piece.lod > 0 and not len(mob.points) and piece.points is not None:
            changed = True
        return changed

    @staticmethod
    def _write(piece: Piece, width: float) -> None:
        mob = piece.mobject
        factor = max(piece.lod, 0.0)
        fill = piece.fill * factor * piece.emphasis[0]
        stroke = piece.stroke * factor * piece.emphasis[1]
        if factor <= 0.0 and not piece.keep:
            if len(mob.points):
                piece.points = mob.points.copy()
                mob.clear_points()
        elif not len(mob.points) and piece.points is not None:
            mob.set_points(piece.points)
        mob.set_fill(opacity=fill)
        mob.set_stroke(width=width, opacity=stroke)
        piece.written = (fill, stroke)

    def rest(self) -> dict[int, tuple[float, float]]:
        """Each piece's full opacity at its current level of detail (an action's ``full``)."""
        return {id(p.mobject): (p.fill * max(p.lod, 0.0), p.stroke * max(p.lod, 0.0)) for p in self.pieces}


def group(*mobs: VMobject) -> VGroup:
    return VGroup(*[m for m in mobs if m is not None])


__all__ = ["CellColors", "MEMBRANE_PX", "PLASMA_PX", "Piece", "Pieces", "RIM_PX", "blend", "curves_array", "feature_weight", "group",
           "luminance", "path_mobject", "shape_arrays"]
