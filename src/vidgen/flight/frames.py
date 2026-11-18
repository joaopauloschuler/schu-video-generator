"""The frames a flight is told in (Step 385, DESIGN.md §123.7): the scene's local frame, the
world-fixed frame and the orbit bridge's ecliptic frame, with conversions both ways.

**Planet-fixed frame** (PF): origin the world's centre, z the IAU north pole, x the prime meridian
on the equator, y = z × x (90° east) — :meth:`vidgen.orbits.rotation.RotationModel.frame`'s
body-fixed frame. A place at planetocentric latitude φ, east longitude λ and height h over the
sphere of radius R is (R + h)(cos φ cos λ, cos φ sin λ, sin φ). ``vidgen/space-bodies`` draws the
same frame in three.js's axes (its +y the pole, +x the prime meridian: ``onGlobe``).

**Local frame** (L; the scene's axes of ``vidgen/space-air``, ``space-sea``, ``space-clouds`` and
``space-land`` at their defaults ``unit: 1``, ``center: null``): metres, origin on the sphere
under the anchor ``at = [φ₀, λ₀]``, x east, y up, z south (three.js's y-up axes, −z north); the
world's centre at (0, −R, 0). Its axes in PF are ``placeFrame(at)`` of ``vidgen/space-land``:
east = (−sin λ₀, cos λ₀, 0), up = (cos φ₀ cos λ₀, cos φ₀ sin λ₀, sin φ₀),
south = (sin φ₀ cos λ₀, sin φ₀ sin λ₀, −cos φ₀). So PF = R·up + M·L with M = [east | up | south],
and L = Mᵀ(PF − R·up). The sphere drops away from the plane y = 0: the point at (x, z) on the
sphere has y = √(R² − x² − z²) − R (3.45 m at 6.6 km on the Earth). A height is always the
distance over the sphere, |L − (0, −R, 0)| − R; ``space-land``'s ground at (x, z) is the point
(x, √((R + g)² − x² − z²) − R, z), g = ``heightAt(x, z)`` (its chart), so a craft at L stands
``h − heightAt(L.x, L.z)`` over the ground (``Land.above``).

**Ecliptic frame** (E; the orbit bridge's, :mod:`vidgen.scenes.orbit_data`): mean ecliptic and
equinox of J2000, origin the world's centre. E = F(jd)·PF with F the body-fixed frame of
:mod:`vidgen.orbits.rotation` on that Julian date; velocities v_E = F·v_PF + ω × r_E, ω the
turning rate along the spin axis (the slow motion of the pole is left out). A flight's velocity is
the velocity over the ground (PF); in the air at rest with the ground it is also the air speed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from vidgen.errors import VidgenError

from .worlds import World

RAD = math.pi / 180.0


@dataclass(frozen=True)
class LocalFrame:
    """The scene's local frame on a world of ``radius`` metres at the anchor ``lat``, ``lon``
    (degrees, planetocentric, east positive). See the module docstring."""

    lat: float
    lon: float
    radius: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.lat <= 90.0:
            raise VidgenError(f"at: the latitude must be from -90 to 90 degrees, got {self.lat}")
        if not -360.0 <= self.lon <= 360.0:
            raise VidgenError(f"at: the longitude must be from -360 to 360 degrees, got {self.lon}")

    @property
    def axes(self) -> np.ndarray:
        """M: the local axes (east, up, south) in the planet-fixed frame, as columns."""
        a, o = self.lat * RAD, self.lon * RAD
        east = [-math.sin(o), math.cos(o), 0.0]
        up = [math.cos(a) * math.cos(o), math.cos(a) * math.sin(o), math.sin(a)]
        south = [math.sin(a) * math.cos(o), math.sin(a) * math.sin(o), -math.cos(a)]
        return np.column_stack([east, up, south])

    @property
    def centre(self) -> np.ndarray:
        """The world's centre in the local frame: (0, −R, 0)."""
        return np.array([0.0, -self.radius, 0.0])

    @property
    def pole(self) -> np.ndarray:
        """The world's north pole (a unit direction) in the local frame."""
        return self.axes.T @ np.array([0.0, 0.0, 1.0])

    # ---- local <-> planet-fixed
    def to_fixed(self, local: Any) -> np.ndarray:
        """Local points (…, 3) as planet-fixed points (m from the centre)."""
        m = self.axes
        return np.asarray(local, dtype=float) @ m.T + self.radius * m[:, 1]

    def from_fixed(self, fixed: Any) -> np.ndarray:
        """Planet-fixed points (…, 3) as local points."""
        m = self.axes
        return (np.asarray(fixed, dtype=float) - self.radius * m[:, 1]) @ m

    def vector_to_fixed(self, local: Any) -> np.ndarray:
        """Local directions or velocities (…, 3) in the planet-fixed axes."""
        return np.asarray(local, dtype=float) @ self.axes.T

    def vector_from_fixed(self, fixed: Any) -> np.ndarray:
        return np.asarray(fixed, dtype=float) @ self.axes

    # ---- places
    def place(self, lat: Any, lon: Any, height: Any = 0.0) -> np.ndarray:
        """The local point at latitude, longitude (degrees) and height over the sphere (m)."""
        a, o = np.radians(np.asarray(lat, dtype=float)), np.radians(np.asarray(lon, dtype=float))
        r = self.radius + np.asarray(height, dtype=float)
        fixed = np.stack(np.broadcast_arrays(r * np.cos(a) * np.cos(o), r * np.cos(a) * np.sin(o), r * np.sin(a)), axis=-1)
        return self.from_fixed(fixed)

    def geodetic(self, local: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Latitude and longitude (degrees, planetocentric) and height over the sphere (m) of local points."""
        f = self.to_fixed(local)
        r = np.linalg.norm(f, axis=-1)
        return np.degrees(np.arcsin(np.clip(f[..., 2] / r, -1, 1))), np.degrees(np.arctan2(f[..., 1], f[..., 0])), r - self.radius

    def height(self, local: Any) -> np.ndarray:
        """Height over the sphere (m) of local points: |L − (0, −R, 0)| − R."""
        return np.linalg.norm(np.asarray(local, dtype=float) - self.centre, axis=-1) - self.radius

    def chart(self, x: Any, z: Any, height: Any = 0.0) -> np.ndarray:
        """The local point at (x, z) and ``height`` over the sphere: (x, √((R + h)² − x² − z²) − R, z),
        ``vidgen/space-land``'s ``pointAt`` (its ground is this point with h = ``heightAt(x, z)``)."""
        x, z, h = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(z, dtype=float), np.asarray(height, dtype=float))
        r = self.radius + h
        d2 = x * x + z * z
        if np.any(d2 >= r * r):
            raise VidgenError("a place is beyond the world's edge as the scene's frame sees it (x² + z² ≥ R²)")
        return np.stack([x, np.sqrt(r * r - d2) - self.radius, z], axis=-1)

    def north_east(self, local: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """At local points: the unit up, north and east directions (local axes) of the place."""
        p = np.asarray(local, dtype=float)
        up = p - self.centre
        up = up / np.linalg.norm(up, axis=-1, keepdims=True)
        pole = self.pole
        north = pole - np.sum(pole * up, axis=-1, keepdims=True) * up
        n = np.linalg.norm(north, axis=-1, keepdims=True)
        if np.any(n < 1e-9):
            raise VidgenError("a flight over a pole has no heading (north is everywhere): move the place off the pole")
        north = north / n
        return up, north, np.cross(north, up)

    def heading_vector(self, local: Any, heading_deg: Any) -> np.ndarray:
        """The level unit direction of a compass heading (degrees: 0 north, 90 east) at local points."""
        _, north, east = self.north_east(local)
        h = np.radians(np.asarray(heading_deg, dtype=float))[..., None]
        return np.cos(h) * north + np.sin(h) * east

    def heading_of(self, local: Any, direction: Any) -> np.ndarray:
        """The compass heading (degrees, 0 to 360) of directions at local points."""
        _, north, east = self.north_east(local)
        d = np.asarray(direction, dtype=float)
        return np.mod(np.degrees(np.arctan2(np.sum(d * east, axis=-1), np.sum(d * north, axis=-1))), 360.0)

    # ---- planet-fixed <-> ecliptic J2000 (the orbit bridge)
    def ecliptic_axes(self, world: World, jd: Any) -> np.ndarray:
        """The local axes (east, up, south) in ecliptic J2000 on Julian date(s) ``jd``: F(jd)·M, (3, 3) or (N, 3, 3)."""
        return _body_frame(world, jd) @ self.axes

    def to_ecliptic(self, world: World, local: Any, velocity: Any, jd: Any) -> tuple[np.ndarray, np.ndarray]:
        """Local points and their velocities over the ground as positions and velocities in ecliptic
        J2000 (origin the world's centre; m, m/s) on Julian date(s) ``jd`` (one per point, or one)."""
        f = _body_frame(world, jd)
        r = _apply(f, self.to_fixed(local))
        v = _apply(f, self.vector_to_fixed(velocity)) + np.cross(spin_vector(world, jd), r)
        return r, v

    def from_ecliptic(self, world: World, position: Any, velocity: Any, jd: Any) -> tuple[np.ndarray, np.ndarray]:
        """Ecliptic J2000 positions and velocities (origin the world's centre) as local points and
        velocities over the ground: the inverse of :meth:`to_ecliptic`."""
        f = _body_frame(world, jd)
        r = np.asarray(position, dtype=float)
        v = np.asarray(velocity, dtype=float) - np.cross(spin_vector(world, jd), r)
        ft = np.swapaxes(f, -1, -2)
        return self.from_fixed(_apply(ft, r)), self.vector_from_fixed(_apply(ft, v))


def _apply(matrices: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    """Each matrix times its vector (or one matrix times all vectors)."""
    if matrices.ndim == 2:
        return vectors @ matrices.T
    return np.einsum("nij,nj->ni", matrices, np.broadcast_to(vectors, (len(matrices), 3)))


def _body_frame(world: World, jd: Any) -> np.ndarray:
    if world.rotation is None:
        raise VidgenError(f"the world '{world.name}' has no rotation data (an invented world): it has no place in the orbit bridge's ecliptic frame")
    from vidgen.orbits.rotation import ROTATIONS

    return ROTATIONS[world.rotation].frame(jd)


def spin_vector(world: World, jd: Any) -> np.ndarray:
    """The world's angular velocity (rad/s) in ecliptic J2000: the spin rate along its north pole."""
    from vidgen.orbits.rotation import ROTATIONS

    if world.rotation is None:
        return np.zeros(3)
    return ROTATIONS[world.rotation].pole(jd) * world.spin_rate


def spin_local(world: World, frame: LocalFrame) -> np.ndarray:
    """The world's angular velocity (rad/s) in the local axes (the pole's slow motion left out)."""
    return frame.pole * world.spin_rate


__all__ = ["LocalFrame", "spin_local", "spin_vector"]
