"""Manoeuvres for the ``orbit`` scene (Phase X, Step 231, DESIGN §98.5): impulsive burns (a
velocity change Δv at an instant, written in the local frame prograde / radial / normal), the
trajectory they make (a chain of Kepler arcs, each from the state after a burn, checked for an
arc that would hit the body orbited), and the classic transfers between circular coplanar orbits
— Hohmann (Δv₁, Δv₂, the transfer time, the phase angle the target must lead by at departure, the
synodic period between launch windows), bi-elliptic (and the ratios r₂/r₁ beyond which it beats
Hohmann, computed: 11.94 and 15.58), plane changes (Δv = 2 v sin(Δi/2)) and phasing for a
rendezvous. Impulsive burns and two-body motion are the approximation throughout (a real burn
lasts minutes; patched conics for interplanetary transfers). SI units. No manim."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vidgen.errors import VidgenError

from .elements import Elements, circular_speed, vis_viva

#: The directions of the local frame a burn is written in: along the velocity (prograde) or
#: against it, radial (in the orbit's plane, perpendicular to the velocity, outwards) or inwards,
#: normal (along the angular momentum, out of the plane) or against it.
BURN_DIRECTIONS = ("prograde", "retrograde", "radial", "anti_radial", "normal", "anti_normal")
#: Each direction as a (component, sign) of the frame (prograde, radial, normal).
_AXES = {"prograde": (0, 1.0), "retrograde": (0, -1.0), "radial": (1, 1.0), "anti_radial": (1, -1.0), "normal": (2, 1.0), "anti_normal": (2, -1.0)}
#: An orbit within this eccentricity counts as circular for a transfer between circular orbits.
CIRCULAR_E = 1e-6
#: Two orbits whose planes differ by less than this (rad) are coplanar for a transfer.
COPLANAR = 1e-6


def local_frame(r: Any, v: Any) -> np.ndarray:
    """The unit vectors (rows) prograde (along v), radial (in the plane, perpendicular to v,
    away from the centre: prograde × normal) and normal (along r × v) of a body at ``r``
    moving at ``v``."""
    r = np.asarray(r, dtype=float)
    v = np.asarray(v, dtype=float)
    t = v / np.linalg.norm(v)
    h = np.cross(r, v)
    hn = float(np.linalg.norm(h))
    if hn == 0:
        raise VidgenError("a burn's frame needs a body moving sideways (not straight towards or away from the centre)")
    n = h / hn
    return np.array([t, np.cross(t, n), n])


def burn_vector(r: Any, v: Any, components: dict[str, float]) -> np.ndarray:
    """The Δv vector (m/s, reference frame) of a burn written as speeds along the local
    directions (:data:`BURN_DIRECTIONS`, e.g. ``{"prograde": 2400.0}``)."""
    frame = local_frame(r, v)
    local = np.zeros(3)
    for name, speed in components.items():
        if name not in _AXES:
            raise VidgenError(f"a burn direction is one of {', '.join(BURN_DIRECTIONS)} (got '{name}')")
        k, sign = _AXES[name]
        local[k] += sign * float(speed)
    return local @ frame


def burn_components(r: Any, v: Any, dv: Any) -> np.ndarray:
    """A Δv vector's (prograde, radial, normal) components at ``r``, ``v``."""
    return local_frame(r, v) @ np.asarray(dv, dtype=float)


def direction_name(components: Any) -> str:
    """The direction a burn mostly points (``prograde``, ``retrograde``, ``radial``...), or a
    combination (``prograde + normal``) when no component dominates (less than 90 % of Δv)."""
    c = np.asarray(components, dtype=float)
    total = float(np.linalg.norm(c))
    if total == 0:
        return "none"
    names = (("prograde", "retrograde"), ("radial", "anti_radial"), ("normal", "anti_normal"))
    parts = [(abs(c[k]), names[k][0 if c[k] > 0 else 1]) for k in range(3) if abs(c[k]) > 1e-9 * total]
    parts.sort(reverse=True)
    if parts[0][0] >= 0.9 * total:
        return parts[0][1].replace("_", "-")
    return " + ".join(name.replace("_", "-") for _, name in parts[:2])


@dataclass(frozen=True)
class BurnPlan:
    """A burn as an author writes it: ``at`` a time (s after the start) or the next
    ``"periapsis"`` / ``"apoapsis"`` after the previous burn, ``components`` speeds along
    :data:`BURN_DIRECTIONS` (m/s), and a ``label``."""

    at: float | str
    components: dict[str, float]
    label: str = ""


@dataclass(frozen=True)
class Burn:
    """A burn done: its ``time`` (s), the ``position`` and the velocity ``before`` and
    ``after`` it (relative to the body orbited), the Δv vector ``dv`` and its (prograde, radial,
    normal) ``components``, the orbit before and after (``orbit_before``, ``orbit_after``,
    their epoch at the burn), and its ``label``."""

    number: int
    time: float
    position: np.ndarray
    before: np.ndarray
    after: np.ndarray
    dv: np.ndarray
    components: np.ndarray
    orbit_before: Elements
    orbit_after: Elements
    label: str = ""

    @property
    def magnitude(self) -> float:
        return float(np.linalg.norm(self.dv))

    @property
    def direction(self) -> str:
        return direction_name(self.components)


@dataclass(frozen=True)
class Arc:
    """A stretch of coasting on one Kepler orbit (``elements``, epoch at ``start``) from
    ``start`` to ``end`` (s; ``math.inf`` for the last)."""

    start: float
    end: float
    elements: Elements


@dataclass(frozen=True)
class Trajectory:
    """A body's path through its burns: the ``arcs`` between them and the ``burns``."""

    arcs: tuple[Arc, ...]
    burns: tuple[Burn, ...] = field(default=())

    def arc_index(self, t: Any) -> Any:
        """The index of the arc each time ``t`` lies on (a burn's own instant: the arc after)."""
        starts = np.array([a.start for a in self.arcs[1:]])
        return np.searchsorted(starts, np.asarray(t, dtype=float), side="right")

    def elements_at(self, t: float) -> Elements:
        """The orbit at time ``t`` (its epoch at the arc's start)."""
        return self.arcs[int(self.arc_index(float(t)))].elements

    def states(self, t: Any) -> tuple[np.ndarray, np.ndarray]:
        """Positions and velocities at time(s) ``t`` (s)."""
        tt = np.asarray(t, dtype=float)
        if tt.ndim == 0:
            arc = self.arcs[int(self.arc_index(float(tt)))]
            return arc.elements.states(float(tt) - arc.start)
        idx = self.arc_index(tt)
        pos, vel = np.zeros((len(tt), 3)), np.zeros((len(tt), 3))
        for k in np.unique(idx):
            arc = self.arcs[int(k)]
            sel = idx == k
            p, v = arc.elements.states(tt[sel] - arc.start)
            pos[sel], vel[sel] = p, v
        return pos, vel

    def positions(self, t: Any) -> np.ndarray:
        return self.states(t)[0]

    @property
    def total_dv(self) -> float:
        return float(sum(b.magnitude for b in self.burns))


def _apsis_time(el: Elements, which: str, after: float, strictly: bool, where: str) -> float:
    """Seconds from the epoch of ``el`` to its next periapsis or apoapsis (at or ``strictly``
    after ``after`` seconds)."""
    if el.e < CIRCULAR_E:
        raise VidgenError(f"{where}: the orbit is circular, it has no {which}; give the burn a time ('45 min')")
    if which == "apoapsis" and not el.closed:
        raise VidgenError(f"{where}: the orbit is a {el.kind} (e = {el.e:g}): it has no apoapsis")
    target = 0.0 if which == "periapsis" else math.pi
    t = el.time_of_flight(el.nu, target) if el.closed else -el.time_since_periapsis()
    if not el.closed and t < 0:
        raise VidgenError(f"{where}: the body has passed its periapsis on this open orbit; give the burn a time")
    period = el.period
    while t < after - 1e-9 * (period or 1.0) or (strictly and t <= after + 1e-9 * (period or 1.0)):
        if period is None:
            raise VidgenError(f"{where}: the body has passed its periapsis on this open orbit; give the burn a time")
        t += period
    return t


def crash_time(el: Elements, radius: float, duration: float = math.inf) -> float | None:
    """Seconds after the epoch at which a body on ``el`` reaches distance ``radius`` moving
    inwards, if within ``duration``; ``None`` when it does not."""
    if radius <= 0 or el.periapsis > radius:
        return None
    r0 = float(el.radius_at(el.nu))
    if r0 <= radius * (1 + 1e-12):
        return 0.0
    cos_c = (el.p / radius - 1.0) / el.e if el.e > 0 else 2.0
    if cos_c >= 1.0:   # a circle inside: already handled; numerically the periapsis grazes
        return None
    nu_c = math.acos(max(-1.0, cos_c))
    if el.closed:
        t = el.time_of_flight(el.nu, -nu_c)
    else:
        if el.nu >= -nu_c:   # outbound already past the inbound crossing
            return None
        t = el.time_of_flight(el.nu, -nu_c)
    return t if t <= duration else None


def fly(start: Elements, plans: list[BurnPlan], *, radius: float = 0.0, body: str = "the body", horizon: float = math.inf) -> Trajectory:
    """The trajectory of a body starting on ``start`` (epoch t = 0) through the burns
    ``plans`` in order, each from the state there: Δv added to the velocity, the new orbit
    from the state (:meth:`Elements.from_state`). Raises :class:`VidgenError` for a burn before
    the one before it, a burn below the surface of ``body`` (``radius``), or an arc that would
    hit it before the next burn (the last arc up to ``horizon``)."""
    arcs: list[Arc] = []
    burns: list[Burn] = []
    el, t0 = start, 0.0
    for n, plan in enumerate(plans, start=1):
        where = f"burns[{n}]"
        if isinstance(plan.at, str):
            t = t0 + _apsis_time(el, plan.at, 0.0, strictly=n > 1, where=where)
        else:
            t = float(plan.at)
            if t < t0 - 1e-9 or (n > 1 and t <= t0):
                raise VidgenError(f"{where}: at {t:g} s comes before the burn before it ({t0:g} s); list the burns in time order")
        hit = crash_time(el, radius, t - t0)
        if hit is not None:
            raise VidgenError(_crash_message(n - 1, el, radius, body, t0 + hit, before=f"burns[{n}]"))
        r, v = el.states(t - t0)
        dv = burn_vector(r, v, plan.components)
        after_v = v + dv
        try:
            new = Elements.from_state(el.mu, r, after_v)
        except VidgenError as error:
            raise VidgenError(f"{where}: {error}") from None
        arcs.append(Arc(t0, t, el))
        burns.append(Burn(n, t, r, v, after_v, dv, burn_components(r, v, dv), el.at(t - t0), new, plan.label))
        el, t0 = new, t
    hit = crash_time(el, radius, horizon - t0)
    if hit is not None:
        raise VidgenError(_crash_message(len(plans), el, radius, body, t0 + hit))
    arcs.append(Arc(t0, math.inf, el))
    return Trajectory(tuple(arcs), tuple(burns))


def _crash_message(after: int, el: Elements, radius: float, body: str, when: float, before: str = "") -> str:
    """Why the arc after burn number ``after`` (0: the starting orbit) is refused."""
    where = f"burns[{after}]: the orbit after it" if after else "the starting orbit"
    if when <= 0 or el.radius_at(el.nu) <= radius:
        return f"{where} starts below the surface of {body} (radius {radius / 1000:,.0f} km): a burn cannot happen underground"
    q = el.periapsis
    text = (f"{where} has its periapsis {q / 1000:,.0f} km from the centre of {body}, inside it (radius {radius / 1000:,.0f} km): "
            f"the body would hit {body} {_duration(when)} after the start")
    if before:
        text += f", before {before}"
    return text + "; raise the periapsis (a smaller retrograde burn) or burn again earlier"


def _duration(seconds: float) -> str:
    for unit, size in (("d", 86400.0), ("h", 3600.0), ("min", 60.0)):
        if seconds >= size:
            return f"{seconds / size:.3g} {unit}"
    return f"{seconds:.3g} s"


# ----- transfers between circular orbits ----------------------------------------------------------


@dataclass(frozen=True)
class Hohmann:
    """A Hohmann transfer between circular coplanar orbits of radii ``r1`` → ``r2`` around a
    body of gravitational parameter ``mu``: the transfer ellipse (``a``, ``e``) touching both,
    the circular speeds ``v1``, ``v2``, the transfer orbit's speeds where it leaves and arrives
    (``v_depart``, ``v_arrive``), the burns ``dv1`` and ``dv2`` (magnitudes; prograde when
    raising, retrograde when lowering) and the ``time`` of flight, half the ellipse's period.
    With the target's gravitational parameter ``mu_target`` (its orbit's μ, default ``mu``): the
    ``phase`` angle the target must lead the departing craft by (rad, negative: trail), and the
    ``synodic`` period between launch windows (``mu_from``: the departure orbit's μ)."""

    mu: float
    r1: float
    r2: float
    a: float
    e: float
    v1: float
    v2: float
    v_depart: float
    v_arrive: float
    dv1: float
    dv2: float
    time: float
    phase: float
    synodic: float

    @property
    def total(self) -> float:
        return self.dv1 + self.dv2

    @property
    def raising(self) -> bool:
        return self.r2 > self.r1

    @property
    def transfer(self) -> Elements:
        """The transfer ellipse (its periapsis at +x for a raise, apoapsis at +x for a lowering;
        the body leaving at ν = 0 or π)."""
        q = min(self.r1, self.r2)
        return Elements.from_apsides(self.mu, q, max(self.r1, self.r2), nu=0.0 if self.raising else math.pi)


def hohmann(mu: float, r1: float, r2: float, *, mu_target: float | None = None, mu_from: float | None = None) -> Hohmann:
    """The Hohmann transfer from a circular orbit of radius ``r1`` to one of ``r2`` (m)."""
    if not (r1 > 0 and r2 > 0):
        raise VidgenError("a Hohmann transfer needs two positive orbit radii")
    if math.isclose(r1, r2, rel_tol=1e-12):
        raise VidgenError("the two orbits are the same: no transfer is needed (a phasing manoeuvre changes only the position along it)")
    a = (r1 + r2) / 2
    e = abs(r2 - r1) / (r1 + r2)
    v1, v2 = circular_speed(mu, r1), circular_speed(mu, r2)
    vd, va = vis_viva(mu, r1, a), vis_viva(mu, r2, a)
    time = math.pi * math.sqrt(a**3 / mu)
    n2 = math.sqrt((mu_target or mu) / r2**3)
    n1 = math.sqrt((mu_from or mu) / r1**3)
    phase = _wrap(math.pi - n2 * time)
    synodic = 2 * math.pi / abs(n1 - n2)
    return Hohmann(mu, r1, r2, a, e, v1, v2, vd, va, abs(vd - v1), abs(v2 - va), time, phase, synodic)


def _wrap(angle: float) -> float:
    """``angle`` in (−π, π]."""
    out = (angle + math.pi) % (2 * math.pi) - math.pi
    return math.pi if out == -math.pi else out


def window_wait(phase_now: float, phase_needed: float, n_from: float, n_to: float) -> float:
    """Seconds until the target's lead angle over the craft, ``phase_now`` (rad) now, changing
    at n_to − n_from (rad/s), next equals ``phase_needed``: the wait for the launch window
    (0 when it is now). Raises when the two orbits have the same period (the angle never
    changes)."""
    rate = n_to - n_from
    if rate == 0:
        raise VidgenError("both orbits have the same period: the phase angle never changes, so a window comes never or always")
    period = 2 * math.pi / abs(rate)
    wait = ((phase_needed - phase_now) / rate) % period
    return 0.0 if math.isclose(wait, period, rel_tol=1e-12) else wait


def synodic_period(period1: float, period2: float) -> float:
    """The synodic period (s) of two bodies of orbital periods ``period1`` and ``period2``:
    1 / |1/T₁ − 1/T₂|, the time between repeats of their relative position (launch windows)."""
    if period1 <= 0 or period2 <= 0:
        raise VidgenError("periods must be positive")
    if math.isclose(period1, period2, rel_tol=1e-15):
        raise VidgenError("equal periods: the two bodies keep their relative position (no synodic period)")
    return 1.0 / abs(1.0 / period1 - 1.0 / period2)


@dataclass(frozen=True)
class BiElliptic:
    """A bi-elliptic transfer ``r1`` → ``rb`` → ``r2`` between circular coplanar orbits: a first
    ellipse out to ``rb``, a burn there, a second ellipse down (or up) to ``r2``. The three burns
    ``dv1``, ``dv2``, ``dv3`` (magnitudes), the semi-major axes ``a1``, ``a2``, the ``time`` (two
    half periods)."""

    mu: float
    r1: float
    r2: float
    rb: float
    a1: float
    a2: float
    dv1: float
    dv2: float
    dv3: float
    time: float

    @property
    def total(self) -> float:
        return self.dv1 + self.dv2 + self.dv3


def bielliptic(mu: float, r1: float, r2: float, rb: float) -> BiElliptic:
    """The bi-elliptic transfer from radius ``r1`` to ``r2`` through the apoapsis ``rb`` (m)."""
    if not (r1 > 0 and r2 > 0):
        raise VidgenError("a transfer needs two positive orbit radii")
    if math.isclose(r1, r2, rel_tol=1e-12):
        raise VidgenError("the two orbits are the same: no transfer is needed")
    if rb < max(r1, r2) * (1 - 1e-12):
        raise VidgenError(f"a bi-elliptic transfer's intermediate apoapsis ({rb / 1000:,.0f} km) must lie beyond both orbits "
                          f"({max(r1, r2) / 1000:,.0f} km); with it at the outer orbit it is a Hohmann transfer")
    a1, a2 = (r1 + rb) / 2, (r2 + rb) / 2
    dv1 = vis_viva(mu, r1, a1) - circular_speed(mu, r1)
    dv2 = abs(vis_viva(mu, rb, a2) - vis_viva(mu, rb, a1))
    dv3 = abs(vis_viva(mu, r2, a2) - circular_speed(mu, r2))
    time = math.pi * (math.sqrt(a1**3 / mu) + math.sqrt(a2**3 / mu))
    return BiElliptic(mu, r1, r2, rb, a1, a2, abs(dv1), dv2, dv3, time)


def _hohmann_total(ratio: float) -> float:
    """Hohmann's total Δv in units of the inner circular speed, for r₂/r₁ = ``ratio``."""
    return math.sqrt(2 * ratio / (1 + ratio)) - 1 + (1 - math.sqrt(2 / (1 + ratio))) / math.sqrt(ratio)


def _bielliptic_total(ratio: float, rb: float) -> float:
    """The bi-elliptic total Δv (inner circular speed = 1, r₁ = 1) through ``rb`` (math.inf: the
    limit of a far apoapsis)."""
    if math.isinf(rb):
        return (math.sqrt(2) - 1) * (1 + 1 / math.sqrt(ratio))
    return bielliptic(1.0, 1.0, ratio, rb).total


def _bisect(f: Any, lo: float, hi: float) -> float:
    flo = f(lo)
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
        if hi - lo < 1e-13 * hi:
            break
    return (lo + hi) / 2


def bielliptic_thresholds() -> tuple[float, float]:
    """The ratios r₂/r₁ (outward) where a bi-elliptic transfer starts to beat Hohmann: above
    the first (≈ 11.94) with its apoapsis far enough out (the limit rb → ∞ costs less than
    Hohmann), above the second (≈ 15.58) for any apoapsis beyond r₂ (the total falls as rb grows
    from r₂). Both computed here by bisection."""
    first = _bisect(lambda x: _hohmann_total(x) - _bielliptic_total(x, math.inf), 2.0, 40.0)

    def slope(x: float) -> float:   # d(total)/d(rb) at rb just beyond r₂ (negative: a farther apoapsis saves)
        h = 1e-6 * x
        return (_bielliptic_total(x, x + 2 * h) - _bielliptic_total(x, x + h)) / h

    second = _bisect(slope, 12.0, 40.0)
    return first, second


def plane_change(v: float, delta_i: float) -> float:
    """Δv (m/s) to turn an orbit's plane by ``delta_i`` (rad) at speed ``v`` without changing the
    speed: 2 v sin(Δi/2) (cheapest where the body is slowest)."""
    if not 0 <= delta_i <= math.pi:
        raise VidgenError(f"a plane change turns by 0° to 180° (got {math.degrees(delta_i):.4g}°)")
    if v < 0:
        raise VidgenError("a speed cannot be negative")
    return 2 * v * math.sin(delta_i / 2)


def combined_plane_change(v1: float, v2: float, delta_i: float) -> float:
    """Δv (m/s) to go from speed ``v1`` to ``v2`` while turning the plane by ``delta_i`` (rad)
    in one burn: √(v₁² + v₂² − 2 v₁ v₂ cos Δi) (the law of cosines)."""
    if not 0 <= delta_i <= math.pi:
        raise VidgenError(f"a plane change turns by 0° to 180° (got {math.degrees(delta_i):.4g}°)")
    return math.sqrt(max(0.0, v1 * v1 + v2 * v2 - 2 * v1 * v2 * math.cos(delta_i)))


@dataclass(frozen=True)
class Phasing:
    """A phasing manoeuvre on a circular orbit of radius ``r``: to close a lead ``angle``
    (rad; positive: the target is ahead) in ``revolutions`` turns, the chaser burns onto a
    phasing orbit of ``period`` (shorter, a lower orbit, to catch up; longer to let the target
    catch up) and back after ``time`` = revolutions × period: two burns of ``dv`` each (the
    first retrograde when ``lower``), ``total`` = 2 dv; the phasing orbit's ``a`` and its other
    apsis ``other_apsis``."""

    mu: float
    r: float
    angle: float
    revolutions: int
    period: float
    a: float
    other_apsis: float
    dv: float
    time: float

    @property
    def total(self) -> float:
        return 2 * self.dv

    @property
    def lower(self) -> bool:
        return self.angle > 0


def phasing(mu: float, r: float, angle: float, revolutions: int = 1, *, radius: float = 0.0, body: str = "the body") -> Phasing:
    """The phasing manoeuvre closing a lead ``angle`` (rad) on a circular orbit of radius ``r``
    in ``revolutions`` turns (the target ahead: positive). Raises when the phasing orbit would
    dip into the body (``radius``) or the angle cannot be closed so."""
    if revolutions < 1:
        raise VidgenError("phasing takes at least one revolution")
    if not -math.pi <= angle <= math.pi:
        raise VidgenError(f"a lead angle lies between −180° and 180° (got {math.degrees(angle):.4g}°)")
    period = 2 * math.pi * math.sqrt(r**3 / mu)
    ph = period * (1 - angle / (2 * math.pi * revolutions))
    a = (mu * ph**2 / (4 * math.pi**2)) ** (1 / 3)
    other = 2 * a - r
    if radius > 0 and other <= radius:
        raise VidgenError(f"the phasing orbit would dip to {other / 1000:,.0f} km from the centre of {body}, inside it "
                          f"(radius {radius / 1000:,.0f} km); take more revolutions to close {math.degrees(angle):.4g}°")
    dv = abs(vis_viva(mu, r, a) - circular_speed(mu, r))
    return Phasing(mu, r, angle, revolutions, ph, a, other, dv, revolutions * ph)


__all__ = [
    "BURN_DIRECTIONS",
    "CIRCULAR_E",
    "COPLANAR",
    "Arc",
    "BiElliptic",
    "Burn",
    "BurnPlan",
    "Hohmann",
    "Phasing",
    "Trajectory",
    "bielliptic",
    "bielliptic_thresholds",
    "burn_components",
    "burn_vector",
    "combined_plane_change",
    "crash_time",
    "direction_name",
    "fly",
    "hohmann",
    "local_frame",
    "phasing",
    "plane_change",
    "synodic_period",
    "window_wait",
]
