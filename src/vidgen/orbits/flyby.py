"""Gravity assists by patched conics (Phase X, Step 231, DESIGN §98.5). In the planet's frame a
probe passing by follows a hyperbola: it arrives and leaves at the same speed v∞ (the hyperbolic
excess speed), its direction turned by δ, with sin(δ/2) = 1/e and e = 1 + r_p v∞²/μ (r_p the
periapsis distance). In the Sun's frame its velocity is the planet's plus v∞ before and after;
the turn changes the sum's length: a pass behind the planet (its periapsis on the side the
planet comes from) turns v∞ towards the planet's motion and the probe gains speed and energy, a
pass in front loses them. Patched conics: the planet's gravity alone near it, the Sun's alone
far from it, the planet's velocity constant during the pass. No manim."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from vidgen.errors import VidgenError

from .elements import Elements

#: Which side of the planet a probe passes: behind (it gains speed in the Sun's frame) or in
#: front (it loses speed).
SIDES = ("behind", "in_front")


def turning_angle(mu: float, v_inf: float, rp: float) -> float:
    """The angle δ (rad) a hyperbolic pass turns the velocity by: 2 asin(1 / (1 + r_p v∞²/μ))."""
    if not (mu > 0 and v_inf > 0 and rp > 0):
        raise VidgenError("a flyby needs a positive GM, a positive v∞ and a positive periapsis distance")
    return 2 * math.asin(1.0 / (1.0 + rp * v_inf * v_inf / mu))


def _rotate(v: np.ndarray, angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1], v[2]])


def _unit(angle: float) -> np.ndarray:
    return np.array([math.cos(angle), math.sin(angle), 0.0])


@dataclass(frozen=True)
class Flyby:
    """A hyperbolic pass by a planet of gravitational parameter ``mu`` (``radius``, an
    ``atmosphere`` above it), in the planet's frame: excess speed ``v_inf``, periapsis distance
    ``rp``, eccentricity ``e``, turning angle ``delta``, the speed at periapsis ``v_periapsis``,
    the semi-major axis ``a`` (negative), the aiming distance ``b`` (the asymptote's distance
    from the planet's centre), the incoming direction ``direction`` (rad, of v∞ in), whether it
    goes round ``clockwise``, and its ``elements`` (periapsis at t = 0)."""

    mu: float
    v_inf: float
    rp: float
    radius: float
    atmosphere: float
    e: float
    delta: float
    v_periapsis: float
    a: float
    b: float
    direction: float
    clockwise: bool
    elements: Elements

    @property
    def v_in(self) -> np.ndarray:
        """v∞ before (3-vector, m/s, the planet's frame)."""
        return self.v_inf * _unit(self.direction)

    @property
    def v_out(self) -> np.ndarray:
        """v∞ after: turned by δ (clockwise passes turn clockwise)."""
        return self.v_inf * _unit(self.direction + (-self.delta if self.clockwise else self.delta))

    @property
    def periapsis_point(self) -> np.ndarray:
        return self.elements.state_at_anomaly(0.0)[0]

    @property
    def centre(self) -> np.ndarray:
        """The hyperbola's centre, where its asymptotes cross (|a| e from the focus, beyond the
        periapsis)."""
        p = self.periapsis_point
        return p / np.linalg.norm(p) * abs(self.a) * self.e

    @property
    def altitude(self) -> float:
        return self.rp - self.radius


def flyby(mu: float, v_inf: float, rp: float, *, radius: float = 0.0, atmosphere: float = 0.0, direction: float = 0.0, clockwise: bool = False,
          body: str = "the planet") -> Flyby:
    """The hyperbolic pass of a probe arriving at ``v_inf`` (m/s) along ``direction`` (rad) with
    periapsis ``rp`` (m) from the centre of a planet (``mu``, ``radius``, ``atmosphere`` m).
    Raises when the periapsis lies inside the planet or its atmosphere."""
    if radius > 0 and rp <= radius:
        raise VidgenError(f"the flyby's periapsis ({rp / 1000:,.0f} km from the centre of {body}) lies inside {body} "
                          f"(radius {radius / 1000:,.0f} km): the probe would crash; raise the periapsis")
    if atmosphere > 0 and rp <= radius + atmosphere:
        raise VidgenError(f"the flyby's periapsis ({(rp - radius) / 1000:,.0f} km up) lies inside the atmosphere of {body} "
                          f"(its top {atmosphere / 1000:,.0f} km up): drag would slow or burn the probe; raise the periapsis")
    delta = turning_angle(mu, v_inf, rp)
    e = 1.0 + rp * v_inf * v_inf / mu
    a = -mu / (v_inf * v_inf)
    half = math.pi / 2 - delta / 2   # the incoming velocity's angle from the periapsis direction (counterclockwise pass)
    omega = direction + half if clockwise else direction - half
    v_p = math.sqrt(v_inf * v_inf + 2 * mu / rp)
    r = rp * _unit(omega)
    v = v_p * _unit(omega - math.pi / 2 if clockwise else omega + math.pi / 2)
    el = Elements.from_state(mu, r, v)
    b = abs(a) * math.sqrt(e * e - 1)
    return Flyby(mu, v_inf, rp, radius, atmosphere, e, delta, v_p, a, b, direction, clockwise, el)


@dataclass(frozen=True)
class GravityAssist:
    """A gravity assist in the Sun's frame: the planet's velocity ``v_planet``, the pass
    (:class:`Flyby` in the planet's frame) and the probe's heliocentric velocities before and
    after (``v_before`` = v_planet + v∞ in, ``v_after`` = v_planet + v∞ out); ``side``."""

    v_planet: np.ndarray
    flyby: Flyby
    side: str

    @property
    def v_before(self) -> np.ndarray:
        return self.v_planet + self.flyby.v_in

    @property
    def v_after(self) -> np.ndarray:
        return self.v_planet + self.flyby.v_out

    @property
    def speed_before(self) -> float:
        return float(np.linalg.norm(self.v_before))

    @property
    def speed_after(self) -> float:
        return float(np.linalg.norm(self.v_after))

    @property
    def gain(self) -> float:
        """The heliocentric speed gained (negative: lost), m/s."""
        return self.speed_after - self.speed_before

    @property
    def energy_change(self) -> float:
        """The change of the probe's specific kinetic energy in the Sun's frame (J/kg) during the
        pass, ½(v_after² − v_before²) = v_planet · (v∞ out − v∞ in): the work of the moving
        planet's pull."""
        return float(self.v_planet @ (self.flyby.v_out - self.flyby.v_in))


def gravity_assist(mu: float, v_planet: Any, v_inf_in: Any, rp: float, *, side: str = "behind", radius: float = 0.0, atmosphere: float = 0.0,
                   body: str = "the planet") -> GravityAssist:
    """A gravity assist past a planet of ``mu`` moving at ``v_planet`` (m/s, 2 or 3 components,
    in the Sun's frame) by a probe arriving with ``v_inf_in`` (its velocity relative to the
    planet, far away) and passing at periapsis distance ``rp`` on ``side`` (``behind``: the
    pass that turns v∞ towards the planet's motion, a gain; ``in_front``: a loss)."""
    if side not in SIDES:
        raise VidgenError(f"side: '{side}' is not one of {', '.join(SIDES)}")
    vp = np.asarray(v_planet, dtype=float).ravel()
    vi = np.asarray(v_inf_in, dtype=float).ravel()
    vp = np.append(vp, 0.0) if vp.size == 2 else vp
    vi = np.append(vi, 0.0) if vi.size == 2 else vi
    if vp.size != 3 or vi.size != 3 or abs(vp[2]) > 0 or abs(vi[2]) > 0:
        raise VidgenError("a gravity assist here is drawn in one plane: give the velocities as [x, y]")
    v_inf = float(np.linalg.norm(vi))
    if v_inf == 0:
        raise VidgenError("v∞ must be positive: a probe at rest relative to the planet is not passing by it")
    direction = math.atan2(vi[1], vi[0])
    options = [flyby(mu, v_inf, rp, radius=radius, atmosphere=atmosphere, direction=direction, clockwise=cw, body=body) for cw in (False, True)]
    # the pull turns v∞ by Δv∞ pointing from the periapsis to the planet, so the energy change
    # v_planet · Δv∞ is positive exactly when the periapsis lies behind (opposite the planet's motion)
    fitting = [f for f in options if (side == "behind") == (float(vp @ f.periapsis_point) < 0)]
    if not fitting:
        other = "in front of" if side == "behind" else "behind"
        rel = (math.degrees(direction - math.atan2(vp[1], vp[0])) + 180) % 360 - 180
        raise VidgenError(f"side: {side.replace('_', ' ')}: arriving with v∞ at {rel:.0f}° to {body}'s motion, both ways past it "
                          f"go {other} it (the periapsis on its {'leading' if side == 'behind' else 'trailing'} side); change the direction of v∞ in "
                          f"or pass {other} it")
    gains = [float(vp @ (f.v_out - f.v_in)) for f in fitting]
    pick = int(np.argmax(gains)) if side == "behind" else int(np.argmin(gains))
    return GravityAssist(vp, fitting[pick], side)


__all__ = ["SIDES", "Flyby", "GravityAssist", "flyby", "gravity_assist", "turning_angle"]
