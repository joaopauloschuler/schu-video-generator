"""The animations of the ``iso_diagram`` scene and its actions (DESIGN.md §90.9): a block or
label moved up the picture (points only), a shadow's fade, a block growing up from its ground, dots
or packets running along a connector, and a label's new text taking the old one's place when its
morph ends. Written against ``vidgen.api`` only."""

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from vidgen.api import *


class LiftMove(Animation):
    """Moves ``mobject`` by ``vector`` (points only: colours animated meanwhile are left alone)."""

    def __init__(self, mobject: Mobject, vector: np.ndarray, **kwargs: Any) -> None:
        super().__init__(mobject, **kwargs)
        self.vector = np.asarray(vector, dtype=float)
        self._done = 0.0

    def create_starting_mobject(self) -> Mobject:
        return Mobject()

    def interpolate_mobject(self, alpha: float) -> None:
        t = self.rate_func(alpha)
        self.mobject.shift(self.vector * (t - self._done))
        self._done = t


class FillFade(Animation):
    """Fades ``mobject``'s fill from its opacity now to ``to``."""

    def __init__(self, mobject: VMobject, to: float, **kwargs: Any) -> None:
        super().__init__(mobject, **kwargs)
        self.to = to

    def create_starting_mobject(self) -> Mobject:
        return Mobject()

    def begin(self) -> None:
        self.start = float(self.mobject.get_fill_opacity())
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        self.mobject.set_fill(opacity=self.start + (self.to - self.start) * self.rate_func(alpha))


class GrowBlock(Animation):
    """A block growing up from its ground: ``build(t)`` draws it ``t`` of its height (its points
    are taken, its colours left as they are); the text on its top (``riders``) rides up with the
    top, and its other labels (``labels``) fade in at the end."""

    def __init__(self, group: Mobject, block: Mobject, build: Callable[[float], Mobject], rise: np.ndarray,
                 riders: Sequence[Mobject], labels: Sequence[Mobject], **kwargs: Any) -> None:
        super().__init__(group, **kwargs)
        self.block, self.build, self.rise = block, build, np.asarray(rise, dtype=float)
        self.riders, self.labels = list(riders), [m for label in labels for m in label.get_family() if isinstance(m, VMobject)]

    def create_starting_mobject(self) -> Mobject:
        return Mobject()

    def begin(self) -> None:
        self.full = {id(m): m.points.copy() for m in self.block.get_family()}
        self.homes = [r.get_center() for r in self.riders]
        self.paints = [(m, m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in self.labels]
        self.looks = [(m, m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in self.block.get_family() if isinstance(m, VMobject)]
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        t = self.rate_func(alpha)
        for m, fill, stroke in self.looks:   # unseen until it starts (in a lagged group it waits its turn)
            f, s = fill.copy(), stroke.copy()
            if t <= 1e-6:
                f[:, 3], s[:, 3] = 0.0, 0.0
            m.fill_rgbas, m.stroke_rgbas = f, s
        if t >= 1 - 1e-9:
            for m in self.block.get_family():
                m.points = self.full[id(m)].copy()
        else:
            for m, made in zip(self.block.get_family(), self.build(max(t, 1e-3)).get_family()):
                if len(m.points) == len(made.points):
                    m.points = made.points.copy()
        for rider, home in zip(self.riders, self.homes):
            rider.move_to(home - self.rise * (1 - t))
        shown = min(max((t - 0.6) / 0.4, 0.0), 1.0)
        for m, fill, stroke in self.paints:
            f, s = fill.copy(), stroke.copy()
            f[:, 3] *= shown
            s[:, 3] *= shown
            m.fill_rgbas, m.stroke_rgbas = f, s


class FlowDots(Animation):
    """Dots (or small packets) moving along a connector: ``path(s)`` is the scene point at share
    ``s`` of the way, ``depth(s)`` the z-index there; the dots follow one another ``spacing``
    apart and fade in and out at the ends. Removed when it ends."""

    def __init__(self, dots: VGroup, path: Callable[[float], np.ndarray], depth: Callable[[float], float], spacing: float, **kwargs: Any) -> None:
        super().__init__(dots, remover=True, introducer=True, **kwargs)
        self.path, self.depth, self.spacing = path, depth, spacing
        self.looks = [[(m, m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in dot.get_family() if isinstance(m, VMobject)] for dot in dots]
        dots.set_opacity(0.0)   # unseen until it sets off (a chain adds every connector's dots at once)

    def create_starting_mobject(self) -> Mobject:
        return Mobject()

    def interpolate_mobject(self, alpha: float) -> None:
        count = len(self.mobject.submobjects)
        t = self.rate_func(alpha) * (1 + (count - 1) * self.spacing)
        for i, (dot, looks) in enumerate(zip(self.mobject.submobjects, self.looks)):
            s = t - i * self.spacing
            shown = 0.0 if s <= 0 or s >= 1 else min(1.0, s / 0.08, (1 - s) / 0.08)
            at = min(max(s, 0.0), 1.0)
            dot.move_to(self.path(at))
            dot.set_z_index(self.depth(at))
            for m, fill, stroke in looks:
                f, k = fill.copy(), stroke.copy()
                f[:, 3] *= shown
                k[:, 3] *= shown
                m.fill_rgbas, m.stroke_rgbas = f, k


class SwapAtEnd(Animation):
    """Changes nothing while it plays; when it ends, ``new`` takes ``old``'s place in ``holder``
    (a label's group on screen; not removed from the scene, which would break up the groups
    holding it)."""

    def __init__(self, holder: Mobject, old: Mobject, new: Mobject, **kwargs: Any) -> None:
        super().__init__(holder, **kwargs)
        self.old, self.new = old, new

    def create_starting_mobject(self) -> Mobject:
        return Mobject()

    def interpolate_mobject(self, alpha: float) -> None:
        pass

    def clean_up_from_scene(self, scene: Scene) -> None:
        super().clean_up_from_scene(scene)
        self.mobject.remove(self.old)
        self.mobject.add(self.new)


__all__ = ["FillFade", "FlowDots", "GrowBlock", "LiftMove", "SwapAtEnd"]
