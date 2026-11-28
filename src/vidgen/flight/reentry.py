"""From orbit down to flight (Step 385): a shaped descent, not a simulation of
aerodynamics.

**What is physical.** (1) The start: the orbit's own two-body motion (Kepler, the world's GM),
seen from the turning world (Coriolis and centrifugal parts included), so position and velocity —
and their next derivatives — are the orbit's where the descent takes over. (2) The glide: the
equilibrium glide of a lifting body in the isothermal exponential air of
:mod:`vidgen.flight.worlds` — lift holds the weight less the centrifugal part,
L = m g (1 − v²/v_c²) with v_c = √(g₀ R), and drag is lift over ``E`` (lift over drag), so
dv/dt = −(g₀ / E)(1 − v²/v_c²) and the height for a speed is where the air is dense enough:
ρ(h) = 2 β g₀ (1 − v²/v_c²) / v², β = m / (C_L S) (``loading``): h_eq(v) = H ln(ρ₀ / ρ). The
speed then has a closed form, v = v_c tanh(atanh(v₀ / v_c) − g₀ W(t) / (E v_c)), W the integral
of the drag's weight below. (3) The heating indicator, ∝ √ρ v³ (the stagnation-point heating's
dependence, Sutton and Graves), given relative to √(10⁻⁴ kg/m³)·(7 km/s)³.

**What is a look.** The descent from the orbit's height into the glide: over ``blend`` seconds
the orbit's height, speed and turn rate turn into the glide's by the septic smoothstep, and the
drag's weight grows with it (a deorbit burn and the coast to the air are not modelled). The
S-turns: bank reversals between ±``bank`` (the heading's weave follows the coordinated-turn
relation of :mod:`vidgen.flight.plan`; the glide's height does not answer to the bank). The end:
over ``end`` seconds the glide's height turns into the level state's and the drag's weight falls
to zero exactly as the speed reaches the level state's (no braking manoeuvre); it starts where the
glide's own sink rate, 2 H g₀ / (E v) at low speeds, is a tenth of the speed (or at 1.5 times the end
speed) and lasts at least as long as a descent at 30 % of the end speed needs. The attitude's bank
during the entry is the S-turns' (not the shaped descent's specific force). The angle of attack
(``aoa`` during the entry, the cruise's after) and the glide's heights follow the page's air, whose
scale height is the page's (8.9 km for the Earth-like air), so the glide is higher than a real
entry's (about 75 km at 7 km/s).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from vidgen.errors import VidgenError

from .profiles import PEAK, step, step_integral
from .worlds import World

#: The heating indicator's reference: 1 is √ρ v³ at ρ = 10⁻⁴ kg/m³ and v = 7 km/s (about a returning orbiter's peak).
HEAT_DENSITY, HEAT_SPEED = 1e-4, 7000.0


def heating(density: np.ndarray, speed: np.ndarray) -> np.ndarray:
    """The heating indicator √(ρ / ρ_ref)·(v / v_ref)³ (see the module docstring)."""
    return np.sqrt(np.maximum(density, 0.0) / HEAT_DENSITY) * (np.asarray(speed) / HEAT_SPEED) ** 3


@dataclass
class EntryProfile:
    """The descent's functions of flight time (0 at its start): ``height``, ``speed``, ``turn_rate``
    (ψ̇, rad/s, given the horizontal speed and height as functions), ``entry_weight`` (1 during the
    entry, falling to 0 over the last part: the angle of attack's), its length ``seconds`` and the
    numbers it was made with (``facts``)."""

    height: Callable[[np.ndarray], np.ndarray]
    speed: Callable[[np.ndarray], np.ndarray]
    bank: Callable[[np.ndarray], np.ndarray]
    kepler_turn_rate: Callable[[np.ndarray], np.ndarray]
    blend_weight: Callable[[np.ndarray], np.ndarray]
    entry_weight: Callable[[np.ndarray], np.ndarray]
    seconds: float
    facts: dict[str, float]


def entry_profile(world: World, centre: np.ndarray, spin: np.ndarray, position: np.ndarray, velocity: np.ndarray, settings: object) -> EntryProfile:
    """The descent from the state ``position``, ``velocity`` (local frame, velocity over the ground)
    on ``world`` (``centre``: its centre in the local frame, ``spin``: its angular velocity there)
    with the :class:`vidgen.flight.spec.Reentry` ``settings``."""
    from vidgen.orbits.elements import Elements

    s = settings
    if world.air is None:
        raise VidgenError(f"reentry: the world '{world.name}' has no air to glide in")
    air, R, g0 = world.air, world.radius, world.g0
    r0 = np.asarray(position, dtype=float) - centre
    v_inertial = np.asarray(velocity, dtype=float) + np.cross(spin, r0)
    if np.linalg.norm(r0) - R < 0:
        raise VidgenError("reentry: the start is under the world's sphere")
    orbit = Elements.from_state(world.gm, r0, v_inertial)
    omega = float(np.linalg.norm(spin))
    axis = spin / omega if omega > 0 else np.array([0.0, 1.0, 0.0])

    def turned(t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The orbit's position, velocity and acceleration seen from the turning world (relative to the centre)."""
        t = np.atleast_1d(np.asarray(t, dtype=float))
        r, v = orbit.states(t)
        r, v = np.atleast_2d(r), np.atleast_2d(v)
        angle = -omega * t
        rot = _about(axis, angle)
        rr = np.einsum("nij,nj->ni", rot, r)
        vr = np.einsum("nij,nj->ni", rot, v - np.cross(spin, r))
        a = -world.gm * rr / np.linalg.norm(rr, axis=-1, keepdims=True) ** 3 - 2 * np.cross(spin, vr) - np.cross(spin, np.cross(spin, rr))
        return rr, vr, a

    def kepler_height(t: np.ndarray) -> np.ndarray:
        rr, _, _ = turned(t)
        return (np.linalg.norm(rr, axis=-1) - R).reshape(np.shape(t))

    def kepler_speed(t: np.ndarray) -> np.ndarray:
        _, vr, _ = turned(t)
        return np.linalg.norm(vr, axis=-1).reshape(np.shape(t))

    def kepler_turn_rate(t: np.ndarray) -> np.ndarray:
        rr, vr, a = turned(t)
        up = rr / np.linalg.norm(rr, axis=-1, keepdims=True)
        vh = vr - np.sum(vr * up, axis=-1, keepdims=True) * up
        speed_h = np.linalg.norm(vh, axis=-1)
        e = vh / np.maximum(speed_h, 1e-9)[:, None]
        right = np.cross(e, up)
        return (np.sum(a * right, axis=-1) / np.maximum(speed_h, 1e-9)).reshape(np.shape(t))

    def before_glide(fn: Callable[[np.ndarray], np.ndarray], t: np.ndarray) -> np.ndarray:
        """``fn`` where the orbit's motion still counts (t under ``blend``), 0 elsewhere (not evaluated there)."""
        t = np.asarray(t, dtype=float)
        out = np.zeros(t.shape)
        early = t < s.blend
        if np.any(early):
            out[early] = fn(t[early])
        return out

    vc = math.sqrt(g0 * R)
    v0 = float(kepler_speed(np.zeros(1))[0])
    end_speed, end_height = float(s.to["speed"]), float(s.to["height"])
    if end_speed >= v0:
        raise VidgenError(f"reentry.to.speed ({end_speed:g} m/s) must be under the speed at the start ({v0:.0f} m/s over the ground)")
    a0 = math.atanh(min(v0, 0.999 * vc) / vc)
    k = g0 / (s.lift_to_drag * vc)
    beta = s.loading

    def equilibrium_height(v: np.ndarray) -> np.ndarray:
        v = np.asarray(v, dtype=float)
        share = np.maximum(1 - (v / vc) ** 2, 1e-9)
        return air.scale_height * np.log(air.density * v * v / (2 * beta * g0 * share))

    blend = float(s.blend)
    # the last part starts where the glide's own sink, 2 H g₀ / (E v) at low speeds, is a tenth of the speed (or at 1.5 times the end speed)
    hand = min(max(1.5 * end_speed, math.sqrt(20 * air.scale_height * g0 / s.lift_to_drag)), 0.95 * v0)
    from_speed = 2 * (math.atanh(min(hand, 0.999 * vc) / vc) - math.atanh(end_speed / vc)) / k
    drop = float(equilibrium_height(np.array([hand]))[0]) - end_height
    end = float(s.end) if s.end is not None else max(60.0, from_speed, PEAK * max(drop, 0.0) / (0.3 * end_speed))
    total_weight = (a0 - math.atanh(end_speed / vc)) / k
    glide_end = total_weight + blend / 2 - end / 2
    if glide_end < blend:
        raise VidgenError(f"reentry: the speed falls to {end_speed:g} m/s before the descent into the glide ends (blend {blend:g} s, end {end:g} s): "
                          "give a shorter blend or end, a higher lift_to_drag, or a lower end speed")

    def weight_integral(t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=float)
        return blend * step_integral(t / blend) - end * step_integral((t - glide_end) / end)

    def glide_speed(t: np.ndarray) -> np.ndarray:
        return vc * np.tanh(a0 - k * weight_integral(t))

    def blend_weight(t: np.ndarray) -> np.ndarray:
        return step(np.asarray(t, dtype=float) / blend)

    def end_weight(t: np.ndarray) -> np.ndarray:
        return step((np.asarray(t, dtype=float) - glide_end) / end)

    def height(t: np.ndarray) -> np.ndarray:
        wb, we = blend_weight(t), end_weight(t)
        glide = (1 - we) * equilibrium_height(glide_speed(t)) + we * end_height
        return (1 - wb) * before_glide(kepler_height, t) + wb * glide

    def speed(t: np.ndarray) -> np.ndarray:
        wb = blend_weight(t)
        return (1 - wb) * before_glide(kepler_speed, t) + wb * glide_speed(t)

    reversals = int(s.reversals)
    span = glide_end - blend
    times = [blend + (i + 0.5) * span / reversals for i in range(reversals)] if reversals else []
    bank0 = math.radians(s.bank)

    def bank(t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=float)
        sign = np.ones_like(t)
        for i, at in enumerate(times):
            sign = sign - 2 * (1 if i % 2 == 0 else -1) * step((t - (at - s.reversal / 2)) / s.reversal)
        return bank0 * sign * (1 - end_weight(t))

    facts = {"circular_speed": vc, "start_speed": v0, "glide_start": blend, "glide_end": glide_end, "end": end,
             "end_drop": drop, "lift_to_drag": float(s.lift_to_drag), "loading": float(beta)}
    return EntryProfile(height=height, speed=speed, bank=bank, kepler_turn_rate=lambda t: before_glide(kepler_turn_rate, t), blend_weight=blend_weight,
                        entry_weight=lambda t: 1 - end_weight(t), seconds=glide_end + end, facts=facts)


def _about(axis: np.ndarray, angle: np.ndarray) -> np.ndarray:
    """Rotation matrices (N, 3, 3) by ``angle`` (N,) about the unit ``axis``."""
    x, y, z = axis
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    c, s = np.cos(angle)[:, None, None], np.sin(angle)[:, None, None]
    return np.eye(3) + s * k + (1 - c) * (k @ k)


__all__ = ["EntryProfile", "HEAT_DENSITY", "HEAT_SPEED", "entry_profile", "heating"]
