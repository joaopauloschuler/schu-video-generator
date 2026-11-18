"""The worlds a flight flies over (Step 385, DESIGN.md §123.7): radius, gravity, turning and air.

The radius is the one the page's air of ``vidgen/space-air`` uses (its ``RADII``; the airless
worlds' of ``vidgen/space-land``), so that a height here is the height the page draws over the
same sphere. The air's scale height is the page's too (``AIRS[...].height`` of
``vidgen/space-bodies`` times the radius); the sea-level density and the ratio of specific heats
are this module's (the page's air is optical and has neither).

The air model is an **isothermal exponential atmosphere**: density ρ(h) = ρ₀ exp(−h / H), and
the temperature that goes with the scale height, T = g₀ H / R_gas, so the speed of sound is
a = √(γ g₀ H), the same at every height (Earth-like: 350 m/s; the real air's falls to 295 m/s
at 11 km: stated). Gravity g(h) = GM / (R + h)², GM the body's (``vidgen.orbits.BODIES``) or, for
an invented world, the Earth's mean density times its volume.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from vidgen.errors import VidgenError
from vidgen.orbits.bodies import BODIES
from vidgen.plotcore import did_you_mean

#: The Earth's mean density (kg/m³) and the constant of gravitation: an invented world's GM.
EARTH_DENSITY = 5514.0
G = 6.674e-11


@dataclass(frozen=True)
class Air:
    """An isothermal air: ``scale_height`` (m, the page's), ``density`` at height 0 (kg/m³),
    ``gamma`` (the ratio of specific heats) and where its numbers come from (``source``)."""

    scale_height: float
    density: float
    gamma: float
    source: str

    def density_at(self, height: object) -> object:
        """ρ (kg/m³) at ``height`` (m; a number or an array)."""
        import numpy as np

        return self.density * np.exp(-np.asarray(height, dtype=float) / self.scale_height)


@dataclass(frozen=True)
class World:
    """A world: ``name``, ``radius`` (m, the page's sphere), ``gm`` (m³/s²), ``rotation`` (the key of
    :data:`vidgen.orbits.rotation.ROTATIONS`, ``None``: it does not turn in the model), ``air``
    (``None``: airless) and ``invented`` (no real body: its GM from the Earth's density)."""

    name: str
    radius: float
    gm: float
    rotation: str | None
    air: Air | None
    invented: bool = False

    def gravity(self, height: object = 0.0) -> object:
        """g (m/s²) at ``height`` over the sphere (a number or an array)."""
        import numpy as np

        r = self.radius + np.asarray(height, dtype=float)
        return self.gm / (r * r)

    @property
    def g0(self) -> float:
        return self.gm / self.radius**2

    @property
    def sound_speed(self) -> float | None:
        """The isothermal air's speed of sound, √(γ g₀ H) (m/s); ``None`` without air."""
        return None if self.air is None else math.sqrt(self.air.gamma * self.g0 * self.air.scale_height)

    @property
    def spin_rate(self) -> float:
        """The turning rate (rad/s, about the IAU north pole; negative backwards), 0 when it does not turn."""
        if self.rotation is None:
            return 0.0
        from vidgen.orbits.rotation import ROTATIONS

        return 2 * math.pi / ROTATIONS[self.rotation].period


def _invented_gm(radius: float) -> float:
    return G * EARTH_DENSITY * 4.0 / 3.0 * math.pi * radius**3


# the page's scale heights: vidgen/space-bodies' AIRS[...].height (a share of the radius) times vidgen/space-air's radius
_EARTH_R, _MARS_R = 6.371e6, 3.3895e6
AIRS: dict[str, Air] = {
    "earth": Air(0.0014 * _EARTH_R, 1.225, 1.40, "scale height the page's; sea-level density and γ of dry air (ISA)"),
    "mars": Air(0.0032 * _MARS_R, 0.020, 1.29, "scale height the page's; mean surface density and γ of carbon dioxide"),
    "thin": Air(0.0022 * 2.4e6, 0.25, 1.40, "invented: the page's scale height, a quarter of the Earth's density at sea level"),
    "thick": Air(0.0018 * 7.4e6, 4.9, 1.40, "invented: the page's scale height, four times the Earth's density at sea level"),
}

#: The worlds by name: the airs of ``vidgen/space-air``'s ``PRESETS`` and the airless worlds of ``vidgen/space-land``.
WORLDS: dict[str, World] = {
    "earth": World("earth", _EARTH_R, BODIES["earth"].gm, "earth", AIRS["earth"]),
    "mars": World("mars", _MARS_R, BODIES["mars"].gm, "mars", AIRS["mars"]),
    "thin": World("thin", 2.4e6, _invented_gm(2.4e6), None, AIRS["thin"], invented=True),
    "thick": World("thick", 7.4e6, _invented_gm(7.4e6), None, AIRS["thick"], invented=True),
    "moon": World("moon", 1.7374e6, BODIES["moon"].gm, "moon", None),
    "mercury": World("mercury", 2.4397e6, BODIES["mercury"].gm, "mercury", None),
    "io": World("io", 1.8216e6, BODIES["io"].gm, "io", None),
    "europa": World("europa", 1.5608e6, BODIES["europa"].gm, "europa", None),
    "ganymede": World("ganymede", 2.6341e6, BODIES["ganymede"].gm, "ganymede", None),
    "callisto": World("callisto", 2.4103e6, BODIES["callisto"].gm, "callisto", None),
    "cinder": World("cinder", 1.9e6, _invented_gm(1.9e6), None, None, invented=True),
}


def world(name: str, where: str = "world") -> World:
    """The world called ``name`` (see :data:`WORLDS`); a VidgenError with a did-you-mean otherwise."""
    key = str(name).strip().lower()
    if key not in WORLDS:
        raise VidgenError(f"{where}: no world '{name}'{did_you_mean(key, list(WORLDS))}; worlds: {', '.join(WORLDS)}")
    return WORLDS[key]


__all__ = ["AIRS", "Air", "EARTH_DENSITY", "WORLDS", "World", "world"]
