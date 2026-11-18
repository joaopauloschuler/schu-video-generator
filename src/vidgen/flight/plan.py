"""A flight's path from its words (Step 385, DESIGN.md §123.7): legs → smooth position, velocity
and attitude on the world's sphere (or a flat world), checked against the ground.

**Kinematics.** A flight is three channels of time (:mod:`vidgen.flight.profiles`): the air speed
V(t), the height over the sphere h(t) and the turn rate ψ̇(t) (heading from north towards east,
positive to the right). The horizontal speed is V_h = √(V² − ḣ²). On a sphere of radius R the
position is r = c + (R + h) n̂ and the velocity ṙ = ḣ n̂ + V_h ê, with the place's up n̂, the
heading's level direction ê and the right r̂ = ê × n̂ turning as dn̂/dt = k V_h ê,
dê/dt = −k V_h n̂ + ψ̇ r̂, dr̂/dt = −ψ̇ ê (k = 1 / (R + h); on a flat world k = 0 and the
position is the integral of the velocity). The frame (n̂, ê, r̂) is integrated by the fourth-order
Magnus method at steps of at most 0.05 s of flight time; the acceleration is analytic:
r̈ = (ḧ − k V_h²) n̂ + (V̇_h + k ḣ V_h) ê + V_h ψ̇ r̂.

**Turns.** A coordinated turn at bank φ turns at ψ̇ = g_eff tan φ / V_h with
g_eff = g(h) − V_h² / (R + h) (gravity less the centrifugal part of flying round the world), so
its radius is V_h² / (g_eff tan φ) — v² / (g tan φ) within 0.1 % at airliner speeds — and the
bank of the attitude equals φ in level flight. The bank rolls in and out by the septic smoothstep
at the flight's roll rate. Curves through waypoints are septic Hermite curves in the tangent plane
of the leg's start (azimuthal-equidistant), with the tangent, curvature and its rate continuous
at every point (geometric continuity of order 3), flown at ψ̇ = −κ ṡ (ṡ the speed over the
ground, κ anticlockwise positive).

**Attitude.** The nose is along the velocity (the air is at rest with the ground), raised by the
angle of attack (a look: ``aoa`` degrees per g of lift; a re-entry's own during the entry); the
bank is that of the specific force (acceleration less gravity, with the turning world's Coriolis
and centrifugal parts): φ = atan(f_side / D), D = ½(f_up + √(f_up² + (0.1 g)²)) — the force's
side over its up part, kept upright through push-overs and free fall. Body axes: x the left wing,
y up, z the nose (three.js's convention for a thing facing +z, ``vidgen/space-craft``'s).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from vidgen.errors import VidgenError

from .frames import LocalFrame, spin_local
from .profiles import BUMP_AREA, BUMP_VARIANCE, PEAK, Channel, bump, constant, linear, ramp, rate_ramp, step, step_integral
from .reentry import EntryProfile, entry_profile, heating
from .spec import Flight, Leg, Place
from .terrain import Ground
from .worlds import World

#: The longest integration step (s of flight time).
MAX_STEP = 0.05
#: The step of terrain samples for terrain following and the clearance check (s), and the sub-samples a sample's interval is read at.
TERRAIN_STEP, TERRAIN_SUB = 0.25, 6
_UP = np.array([0.0, 1.0, 0.0])


@dataclass
class FlightContext:
    """Where flights fly: the ``world``, the scene's local ``frame`` (``None``: a flat world), the
    ``ground``, the ``margin`` (m) a path keeps over it, and ``to_flight`` (a time of the scene,
    seconds or 'bar …', to flight seconds)."""

    world: World
    frame: LocalFrame | None
    ground: Ground
    margin: float = 20.0
    to_flight: Callable[[Any], float] = field(default=lambda t: float(t))

    @property
    def flat(self) -> bool:
        return self.frame is None

    @property
    def spin(self) -> np.ndarray:
        return np.zeros(3) if self.frame is None else spin_local(self.world, self.frame)

    @property
    def centre(self) -> np.ndarray:
        return np.zeros(3) if self.frame is None else self.frame.centre


@dataclass
class LegRecord:
    """What a leg became: its number, kind, start and end (flight seconds) and notes (a curve's misses)."""

    number: int
    kind: str
    start: float
    end: float
    notes: dict[str, Any] = field(default_factory=dict)


class FlightRun:
    """A planned flight: :meth:`sample` gives its state at any flight times; ``legs``, ``warnings``,
    ``approximations``, ``end`` (the last leg's end, s)."""

    def __init__(self, spec: Flight, context: FlightContext, start_state: tuple[np.ndarray, np.ndarray] | None = None) -> None:
        self.spec, self.context = spec, context
        self.name = spec.name
        self.world = context.world
        self.warnings: list[str] = []
        self.legs: list[LegRecord] = []
        self.lift = Channel([(0.0, constant(0.0))])
        self.entry: EntryProfile | None = None
        self.entry_end = 0.0
        self.landed: list[tuple[float, float, float]] = []      # (approach start, stop, touchdown ground): the ground may come near there
        self._start_state = start_state
        self._follows: dict[int, tuple[Callable[[np.ndarray], np.ndarray], float, Callable[[np.ndarray], np.ndarray]]] = {}
        settled = 0
        for _ in range(2 * len(spec.legs) + 4):
            # terrain following reads the track of its whole span: plan, make the spans' profiles from it, plan again; a pass
            # that fails after a span without its profile yet (the height held there) is cut short and tried again
            try:
                self._plan()
                failed = None
            except VidgenError as error:
                failed = error
            known = all(span["first"] in self._follows for span in self._spans)
            if failed is not None and known:
                raise failed
            if failed is None and (not self._spans or (known and settled >= 1)):
                break
            settled += failed is None and known
            self._follows = self._follow_profiles()
        for k in range(4):
            if k:
                self._plan()
            deficit = self._check(raise_error=not spec.lift)
            if deficit is None:
                break
            self._raise_by(deficit)
        else:
            self._check(raise_error=True)
        self._loads()

    # ---------- channels ----------
    def _plan(self) -> None:
        c, spec = self.context, self.spec
        self.speed, self.vertical, self.turn = Channel(), Channel(), Channel()
        self.legs, self.landed, self.entry = [], [], None
        self._spans: list[dict[str, Any]] = []
        p0, v0 = self._initial()
        up0 = _UP if c.flat else (p0 - c.centre) / np.linalg.norm(p0 - c.centre)
        h0 = float(p0[1]) if c.flat else float(np.linalg.norm(p0 - c.centre) - c.world.radius)
        climb0 = float(v0 @ up0)
        horizontal = v0 - climb0 * up0
        speed_h = float(np.linalg.norm(horizontal))
        e0 = horizontal / speed_h if speed_h > 1e-6 else self._level(p0, spec.start.heading)
        self.speed.add(0.0, constant(float(np.linalg.norm(v0))))
        self.vertical.add(0.0, linear(0.0, h0, climb0))
        self.turn.add(0.0, constant(0.0))
        self._frame0 = np.column_stack([up0, e0, np.cross(e0, up0)])
        self._q0 = np.array([p0[0], 0.0, p0[2]]) if c.flat else np.zeros(3)
        self._reset_grid()
        self.end = 0.0
        for i, leg in enumerate(spec.legs):
            self.end = self._leg(i + 1, leg, self.end)

    def _initial(self) -> tuple[np.ndarray, np.ndarray]:
        """The start's position and velocity (local frame)."""
        s, c = self.spec.start, self.context
        if self._start_state is not None:
            return np.asarray(self._start_state[0], dtype=float), np.asarray(self._start_state[1], dtype=float)
        if s.orbit is not None:
            raise VidgenError(f"flight {self.name}: start.orbit needs the scene's orbit data (the position and velocity of '{s.orbit}')")
        x, z = self._xz(Place(x=s.x, z=s.z, lat=s.lat, lon=s.lon))
        height = s.height if s.height is not None else float(c.ground.height(x, z)) + float(s.above_ground)
        p = np.array([x, height, z]) if c.flat else c.frame.chart(x, z, height)
        up = _UP if c.flat else (p - c.centre) / np.linalg.norm(p - c.centre)
        if abs(s.climb) >= s.speed and s.speed > 0:
            raise VidgenError(f"flight {self.name}: start.climb ({s.climb:g} m/s) must be less than the speed ({s.speed:g} m/s)")
        level = math.sqrt(max(s.speed**2 - s.climb**2, 0.0))
        return p, self._level(p, s.heading) * level + up * s.climb

    def _level(self, p: np.ndarray, heading: float) -> np.ndarray:
        if self.context.flat:
            h = math.radians(heading)
            return np.array([math.sin(h), 0.0, -math.cos(h)])
        return self.context.frame.heading_vector(p, heading)

    def _xz(self, place: Place) -> tuple[float, float]:
        """A place's local x and z."""
        if place.x is not None:
            return float(place.x), float(place.z)
        if self.context.flat:
            raise VidgenError(f"flight {self.name}: a flat world has no latitude and longitude: give places as [x, z]")
        p = self.context.frame.place(place.lat, place.lon, 0.0)
        return float(p[0]), float(p[2])

    # quantities from the channels
    def height(self, t: Any) -> np.ndarray:
        return self.vertical(t) + self.lift(t)

    def climb_rate(self, t: Any, order: int = 1) -> np.ndarray:
        return self.vertical.derivative(t, order) + self.lift.derivative(t, order)

    def level_speed(self, t: Any) -> np.ndarray:
        v, c = self.speed(t), self.climb_rate(t)
        sq = v * v - c * c
        if np.any(sq < -1e-6):
            bad = float(np.atleast_1d(t)[np.argmin(np.atleast_1d(sq))])
            raise VidgenError(f"flight {self.name}: at {bad:.1f} s the vertical speed is more than the speed: climb or descend at a lower rate, or fly faster")
        return np.sqrt(np.maximum(sq, 0.0))

    def g_eff(self, t: Any) -> np.ndarray:
        h, vh = self.height(t), self.level_speed(t)
        g = self.world.gravity(h)
        return g if self.context.flat else g - vh * vh / (self.world.radius + h)

    def ground_rate(self, t: Any) -> np.ndarray:
        """Speed over the ground's sphere (m/s)."""
        vh = self.level_speed(t)
        return vh if self.context.flat else vh * self.world.radius / (self.world.radius + self.height(t))

    def _rates(self, t: np.ndarray) -> np.ndarray:
        """Body rates (ψ̇, 0, k V_h) of the frame (n̂, ê, r̂) at times t: (N, 3)."""
        t = np.asarray(t, dtype=float)
        vh = self.level_speed(t)
        k = 0.0 if self.context.flat else 1.0 / (self.world.radius + self.height(t))
        return np.stack([self.turn(t), np.zeros_like(t), k * vh], axis=-1)

    # ---------- integration ----------
    def _magnus(self, ta: np.ndarray, tb: np.ndarray) -> np.ndarray:
        """The frame's turn from ta to tb (arrays): the fourth-order Magnus step, (N, 3, 3)."""
        d = tb - ta
        g = math.sqrt(3) / 6
        a1, a2 = self._rates(ta + d * (0.5 - g)), self._rates(ta + d * (0.5 + g))
        theta = d[:, None] / 2 * (a1 + a2) + (math.sqrt(3) / 12) * (d * d)[:, None] * np.cross(a1, a2)
        return _rodrigues(theta)

    def _integrate(self, t0: float, t1: float) -> None:
        """Extend the integrated frame from the last known time to ``t1`` (the channels must be planned there)."""
        start = self._t_known
        if t1 <= start + 1e-12:
            return
        n = max(1, math.ceil((t1 - start) / MAX_STEP))
        times = np.linspace(start, t1, n + 1)
        f0, q0 = self._grid_f[-1][-1], self._grid_q[-1][-1]
        frames = np.concatenate([f0[None], f0 @ _scan(self._magnus(times[:-1], times[1:]))])
        q = q0 + self._flat_moves(times, frames) if self.context.flat else np.tile(q0, (n + 1, 1))
        self._grid_t.append(times[1:])
        self._grid_f.append(frames[1:])
        self._grid_q.append(q[1:])
        self._t_known = t1

    def _reset_grid(self) -> None:
        self._grid_t, self._grid_f, self._grid_q = [np.zeros(1)], [self._frame0[None]], [self._q0[None]]
        self._t_known = 0.0

    def _flat_moves(self, times: np.ndarray, frames: np.ndarray) -> np.ndarray:
        """On a flat world, the ground moved from times[0] (Gauss-Legendre in each step)."""
        g = math.sqrt(3) / 6
        a, b = times[:-1], times[1:]
        moved = np.zeros((len(times), 3))
        step_sum = np.zeros((len(a), 3))
        for node in (0.5 - g, 0.5 + g):
            tn = a + (b - a) * node
            fn = np.einsum("nij,njk->nik", frames[:-1], self._magnus(a, tn))
            step_sum += 0.5 * (b - a)[:, None] * self.level_speed(tn)[:, None] * fn[:, :, 1]
        moved[1:] = np.cumsum(step_sum, axis=0)
        return moved

    def _grid(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return np.concatenate(self._grid_t), np.concatenate(self._grid_f), np.concatenate(self._grid_q)

    def _frames(self, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The frame (n̂, ê, r̂) and a flat world's ground place at flight times t (within the integrated span)."""
        times, frames, qs = self._grid()
        t = np.clip(np.asarray(t, dtype=float), 0.0, times[-1])
        k = np.clip(np.searchsorted(times, t, side="right") - 1, 0, len(times) - 1)
        f = np.einsum("nij,njk->nik", frames[k], self._magnus(times[k], t))
        q = qs[k]
        if self.context.flat:
            q = q + self._partial_moves(times[k], t, frames[k])
        return f, q

    def _partial_moves(self, a: np.ndarray, b: np.ndarray, fa: np.ndarray) -> np.ndarray:
        g = math.sqrt(3) / 6
        out = np.zeros((len(a), 3))
        for node in (0.5 - g, 0.5 + g):
            tn = a + (b - a) * node
            fn = np.einsum("nij,njk->nik", fa, self._magnus(a, tn))
            out += 0.5 * (b - a)[:, None] * self.level_speed(tn)[:, None] * fn[:, :, 1]
        return out

    def position(self, t: Any) -> np.ndarray:
        t = np.atleast_1d(np.asarray(t, dtype=float))
        f, q = self._frames(t)
        h = self.height(np.maximum(t, 0.0))
        if self.context.flat:
            return q + h[:, None] * _UP
        return self.context.centre + (self.world.radius + h)[:, None] * f[:, :, 0]

    def state_at(self, t: float) -> dict[str, Any]:
        """Position, up, heading direction, heading (degrees), height, vertical rate, speed at flight time t."""
        self._integrate(0.0, t)
        f, _ = self._frames(np.array([t]))
        p = self.position(np.array([t]))[0]
        e = f[0, :, 1]
        heading = math.degrees(math.atan2(e[0], -e[2])) % 360 if self.context.flat else float(self.context.frame.heading_of(p, e))
        tt = np.array([t])
        return {"position": p, "up": f[0, :, 0], "direction": e, "heading": heading, "height": float(self.height(tt)[0]),
                "climb": float(self.climb_rate(tt)[0]), "speed": float(self.speed(tt)[0]), "level_speed": float(self.level_speed(tt)[0])}

    # ---------- legs ----------
    def _leg(self, number: int, leg: Leg, t0: float) -> float:
        spec, c = self.spec, self.context
        where = f"flight {self.name}, leg {number}"
        if leg.reentry is not None:
            if number != 1:
                raise VidgenError(f"{where}: reentry is only the first leg (it starts from the flight's start)")
            return self._reentry(number, leg, t0)
        state = self.state_at(t0)
        explicit = None
        if leg.straight is not None or leg.for_ is not None:
            explicit = float(leg.straight if leg.straight is not None else leg.for_)
        elif leg.until is not None:
            explicit = c.to_flight(leg.until) - t0
            if explicit <= 0:
                raise VidgenError(f"{where}: until {leg.until!r} is at {c.to_flight(leg.until):.2f} s of the flight, not after the leg's start at {t0:.2f} s")
        if leg.land is not None:
            return self._landing(number, leg, t0, state, where)
        needs: list[tuple[str, float]] = []
        if leg.speed is not None:
            needs.append(("speed", self._speed_change(leg, t0, state, where)))
        vertical = leg.climb or leg.descend
        if vertical is not None:
            needs.append(("climb" if leg.climb else "descend", self._vertical(vertical, leg.descend is not None, t0, state, where)))
        elif leg.level:
            needs.append(("level", self._level_off(t0, state)))
        if leg.turn is not None:
            needs.append(("turn", self._turn(leg, t0, state, where)))
        elif leg.waypoints is not None or leg.circle is not None:
            needs.append(("waypoints" if leg.waypoints else "circle", self._curve(leg, number, t0, state, where)))
        need = max([n for _, n in needs], default=0.0)
        if explicit is not None and explicit < need - 1e-6:
            what = max(needs, key=lambda x: x[1])[0]
            raise VidgenError(f"{where}: the {what} needs {need:.1f} s, the leg has {explicit:.1f} s: give the leg more time (or leave out for/until), "
                              + ("a steeper bank or a smaller turn" if what in ("turn", "circle", "waypoints") else "a higher rate"))
        if leg.follow is not None and explicit is None and not needs:
            raise VidgenError(f"{where}: follow needs a length (for: seconds or until: a time) or a turn, circle or waypoints to fly")
        t1 = t0 + (explicit if explicit is not None else max(need, 1e-3))
        if leg.follow is not None:
            self._follow(leg, number, t0, t1, state)
        kind = "+".join(k for k, _ in needs) or ("follow" if leg.follow is not None else "straight")
        if leg.follow is not None and needs:
            kind += "+follow"
        record = LegRecord(number, kind, t0, t1)
        self.legs.append(record)
        self._integrate(t0, t1)
        if leg.waypoints is not None or leg.circle is not None:
            record.notes.update(self._misses(leg, t0, t1))
        return t1

    def _speed_change(self, leg: Leg, t0: float, state: dict[str, Any], where: str) -> float:
        target = leg.speed.to
        if leg.speed.mach is not None:
            sound = self.world.sound_speed
            if sound is None:
                raise VidgenError(f"{where}: speed.mach needs air; the world '{self.world.name}' has none: give speed.to in m/s")
            target = leg.speed.mach * sound
        rate = leg.speed.rate or self.spec.accel
        duration = abs(target - state["speed"]) / rate
        self.speed.add(t0, ramp(t0, duration, state["speed"], target))
        self.speed.add(t0 + duration, constant(target))
        return duration

    def _ramp_time(self, change: float, accel_g: float | None) -> float:
        a = (accel_g or self.spec.vertical_accel) * self.world.g0
        return PEAK * abs(change) / a

    def _vertical(self, climb: Any, down: bool, t0: float, state: dict[str, Any], where: str) -> float:
        h0, r0 = state["height"], state["climb"]
        rate = climb.rate or 10.0
        if climb.to is None and climb.by is None:
            c = -rate if down else rate
            tau = self._ramp_time(c - r0, climb.accel)
            self.vertical.add(t0, rate_ramp(t0, tau, h0, r0, c))
            self.vertical.add(t0 + tau, linear(t0 + tau, float(self.vertical(np.array([t0 + tau]))[0]), c))
            return tau
        target = climb.to if climb.to is not None else h0 + (-climb.by if down else climb.by)
        change = target - h0
        name = "descend" if down else "climb"
        if (change < 0) != down and abs(change) > 1e-6:
            raise VidgenError(f"{where}: {name} to {target:g} m from {h0:.0f} m goes the other way: use {'climb' if down else 'descend'}")
        return self._to_height(t0, h0, r0, target, rate, climb.accel, where)

    def _to_height(self, t0: float, h0: float, r0: float, target: float, rate: float, accel: float | None, where: str, end_ramp: float | None = None) -> float:
        """Plan the vertical channel from (h0, r0) at t0 to ``target`` at rest; returns the time it takes."""
        change = target - h0
        sign = 1.0 if change >= 0 else -1.0

        def shape(c: float) -> tuple[float, float, float]:
            t1 = self._ramp_time(c - r0, accel)
            t2 = end_ramp if end_ramp is not None else self._ramp_time(c, accel)
            gained = t1 * (r0 + c) / 2 + t2 * c / 2
            return t1, t2, gained

        c = sign * rate
        t1, t2, gained = shape(c)
        hold = (change - gained) / c if c != 0 else 0.0
        if hold < 0:
            lo, hi = 1e-6, rate
            if (change - shape(sign * lo)[2]) * sign < 0:
                raise VidgenError(f"{where}: the height {target:g} m is too near for the vertical speed at the start ({r0:.1f} m/s): level off first (a leg with level: true)")
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                if (change - shape(sign * mid)[2]) * sign >= 0:
                    lo = mid
                else:
                    hi = mid
            c = sign * lo
            t1, t2, _ = shape(c)
            hold = 0.0
        self.vertical.add(t0, rate_ramp(t0, t1, h0, r0, c))
        h1 = float(rate_ramp(t0, t1, h0, r0, c)(np.array([t0 + t1]))[0])
        self.vertical.add(t0 + t1, linear(t0 + t1, h1, c))
        h2 = h1 + c * hold
        self.vertical.add(t0 + t1 + hold, rate_ramp(t0 + t1 + hold, t2, h2, c, 0.0))
        self.vertical.add(t0 + t1 + hold + t2, constant(target))
        return t1 + hold + t2

    def _level_off(self, t0: float, state: dict[str, Any]) -> float:
        tau = self._ramp_time(state["climb"], None)
        self.vertical.add(t0, rate_ramp(t0, tau, state["height"], state["climb"], 0.0))
        self.vertical.add(t0 + tau, constant(float(rate_ramp(t0, tau, state["height"], state["climb"], 0.0)(np.array([t0 + tau]))[0])))
        return tau

    # turns
    def _bank_turn(self, t0: float, roll: float, hold: float, bank: float, sign: float) -> Callable[[np.ndarray], np.ndarray]:
        def phi(t: np.ndarray) -> np.ndarray:
            u = np.asarray(t, dtype=float) - t0
            return sign * bank * (step(u / roll) - step((u - roll - hold) / roll))

        def rate(t: np.ndarray) -> np.ndarray:
            return self.g_eff(t) * np.tan(phi(t)) / np.maximum(self.level_speed(t), 1e-6)
        return rate

    def _turn(self, leg: Leg, t0: float, state: dict[str, Any], where: str) -> float:
        turn = leg.turn
        if state["level_speed"] <= 0.5:
            raise VidgenError(f"{where}: a turn needs speed (the flight is at {state['speed']:.1f} m/s)")
        if turn.by is not None:
            wanted = turn.by
        else:
            diff = (turn.to - state["heading"]) % 360.0
            wanted = {"right": diff, "left": diff - 360.0 if diff > 0 else 0.0, "shorter": diff if diff <= 180 else diff - 360.0}[turn.side]
        if abs(wanted) < 1e-9:
            return 0.0
        sign = 1.0 if wanted > 0 else -1.0
        tt = np.array([t0])
        if turn.radius is not None:
            bank = math.atan(state["level_speed"] ** 2 / (float(self.g_eff(tt)[0]) * turn.radius))
        else:
            bank = math.radians(turn.bank or 30.0)
        roll_rate = math.radians(turn.roll_rate or self.spec.roll_rate)
        target = math.radians(abs(wanted))
        for _ in range(3):      # the heading drifts a little on a sphere: aim again at what the integration gives
            duration = self._solve_turn(t0, sign, bank, roll_rate, target, where)
            self._trim(t0)
            self._integrate(t0, t0 + duration)
            got = self.state_at(t0 + duration)["heading"] - state["heading"]
            got = (got + 180.0) % 360.0 - 180.0
            want = (wanted + 180.0) % 360.0 - 180.0
            error = (want - got + 180.0) % 360.0 - 180.0
            if abs(error) < 1e-6:
                break
            target += sign * math.radians(error)
        return duration

    def _solve_turn(self, t0: float, sign: float, bank: float, roll_rate: float, target: float, where: str) -> float:
        """Add the turn's piece so that it turns by ``target`` radians; returns its length."""
        def turned(b: float, hold: float) -> tuple[float, float]:
            roll = PEAK * b / roll_rate
            total = 2 * roll + hold
            n = max(64, math.ceil(total / 0.01))
            t = np.linspace(t0, t0 + total, n + 1)
            rate = self._bank_turn(t0, roll, hold, b, 1.0)(t)
            return float(np.sum((rate[1:] + rate[:-1]) * 0.5 * np.diff(t))), float(rate[len(t) // 2])

        roll = PEAK * bank / roll_rate
        base, _ = turned(bank, 0.0)
        if base > target:
            lo, hi = 0.0, bank
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if turned(mid, 0.0)[0] < target else (lo, mid)
            bank, hold = 0.5 * (lo + hi), 0.0
        else:
            hold = 0.0
            for _ in range(8):
                got, middle = turned(bank, hold)
                if abs(got - target) < 1e-12:
                    break
                hold = max(0.0, hold + (target - got) / max(middle, 1e-9))
        roll = PEAK * bank / roll_rate
        self.turn.add(t0, self._bank_turn(t0, roll, hold, bank, sign))
        self.turn.add(t0 + 2 * roll + hold, constant(0.0))
        return 2 * roll + hold

    def _trim(self, t: float) -> None:
        """Forget the integrated frame after t (the channels changed there)."""
        times, frames, qs = self._grid()
        keep = times <= t + 1e-12
        keep[0] = True
        self._grid_t, self._grid_f, self._grid_q = [times[keep]], [frames[keep]], [qs[keep]]
        self._t_known = float(times[keep][-1])

    # curves: waypoints and circles
    def _plane(self, state: dict[str, Any]) -> tuple[Callable[[Place], np.ndarray], Callable[[np.ndarray], np.ndarray]]:
        """The leg start's tangent plane: a place → (east, north) metres, and local points (N, 3) → (N, 2)
        (azimuthal-equidistant about the start on a sphere; plain offsets on a flat world)."""
        p, c = state["position"], self.context
        if c.flat:
            def project(points: np.ndarray) -> np.ndarray:
                q = np.atleast_2d(points)
                return np.stack([q[:, 0] - p[0], -(q[:, 2] - p[2])], axis=-1)

            def to_plane(place: Place) -> np.ndarray:
                x, z = self._xz(place)
                return project(np.array([x, 0.0, z]))[0]
            return to_plane, project
        up, north, east = (v.reshape(3) for v in c.frame.north_east(p))
        R = self.world.radius

        def project(points: np.ndarray) -> np.ndarray:
            w = np.atleast_2d(points) - c.centre
            w = w / np.linalg.norm(w, axis=-1, keepdims=True)
            angle = np.arctan2(np.linalg.norm(np.cross(up, w), axis=-1), w @ up)
            d = w - (w @ up)[:, None] * up
            n = np.maximum(np.linalg.norm(d, axis=-1), 1e-300)
            return R * (angle / n)[:, None] * np.stack([d @ east, d @ north], axis=-1)

        def to_plane(place: Place) -> np.ndarray:
            x, z = self._xz(place)
            return project(c.frame.chart(x, z, 0.0))[0]
        return to_plane, project

    def _curve(self, leg: Leg, number: int, t0: float, state: dict[str, Any], where: str) -> float:
        if state["level_speed"] <= 0.5:
            raise VidgenError(f"{where}: a curve needs speed")
        to_plane, project = self._plane(state)
        h = math.radians(state["heading"])
        tangent0 = np.array([math.sin(h), math.cos(h)])
        limit = math.radians((leg.waypoints.bank_limit if leg.waypoints is not None and leg.waypoints.bank_limit else None) or self.spec.bank_limit)
        if leg.waypoints is not None:
            points = [np.zeros(2)] + [to_plane(p) for p in leg.waypoints.points]
            path = _CurvePath.through(points, tangent0, where)
        else:
            circle = leg.circle
            centre = to_plane(circle.around)
            kappa = (1.0 if circle.side == "left" else -1.0) / circle.radius
            roll = PEAK * math.atan(state["level_speed"] ** 2 * abs(kappa) / max(float(self.g_eff(np.array([t0]))[0]), 1e-6)) / math.radians(self.spec.roll_rate)
            path = _CurvePath.circling(centre, circle.radius, kappa, circle.turns, tangent0, roll * float(self.ground_rate(np.array([t0]))[0]), where)
        # time along the curve: s(t) from the speed over the ground
        span = path.length / max(float(self.ground_rate(np.array([t0]))[0]), 0.5) * 1.5 + 30.0
        t = np.linspace(t0, t0 + span, max(256, math.ceil(span / 0.01)) + 1)
        rate = self.ground_rate(t)
        s = np.concatenate([[0.0], np.cumsum((rate[1:] + rate[:-1]) * 0.5 * np.diff(t))])
        while s[-1] < path.length:
            span *= 2
            t = np.linspace(t0, t0 + span, max(256, math.ceil(span / 0.01)) + 1)
            rate = self.ground_rate(t)
            s = np.concatenate([[0.0], np.cumsum((rate[1:] + rate[:-1]) * 0.5 * np.diff(t))])
        duration = float(np.interp(path.length, s, t)) - t0
        # the bank the curve needs
        kmax, where_k = path.max_curvature()
        vmax = float(np.max(self.level_speed(t[t <= t0 + duration])))
        g = float(np.min(self.g_eff(t[t <= t0 + duration])))
        need = math.atan(vmax * vmax * kmax / max(g, 1e-6))
        if need > limit:
            what = f"near waypoint {where_k}" if leg.waypoints is not None else "on the way into the circle"
            raise VidgenError(f"{where}: the curve {what} needs a bank of {math.degrees(need):.0f}° at {vmax:.0f} m/s, over the limit of "
                              f"{math.degrees(limit):.0f}°: put the places farther apart, fly slower, or raise bank_limit")

        def turn_rate(tq: np.ndarray) -> np.ndarray:
            tq = np.asarray(tq, dtype=float)
            sq = np.interp(tq, t, s)
            return -path.curvature(np.minimum(sq, path.length)) * self.ground_rate(tq) * (tq <= t0 + duration)
        self.turn.add(t0, turn_rate)
        self.turn.add(t0 + duration, constant(0.0))
        self._curve_data = (path, to_plane, project)
        return duration

    def _misses(self, leg: Leg, t0: float, t1: float) -> dict[str, Any]:
        """How near the flown path came to each waypoint (m along the ground), or the circle's radius as flown (least, most)."""
        path, to_plane, project = self._curve_data
        t = np.linspace(t0, t1, max(64, math.ceil((t1 - t0) / 0.02)) + 1)
        en = project(self.position(t))
        if leg.waypoints is not None:
            return {"misses": [float(np.min(np.linalg.norm(en - w, axis=-1))) for w in path.knots[1:]]}
        r = np.linalg.norm(en - to_plane(leg.circle.around), axis=-1)
        s_flown = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(en, axis=0), axis=-1))])
        on_arc = (s_flown >= path.arc[0] + 0.05 * path.arc[1]) & (s_flown <= path.arc[0] + 0.95 * path.arc[1])
        return {"radius": [float(np.min(r[on_arc])), float(np.max(r[on_arc]))] if np.any(on_arc) else []}

    # terrain following
    def _follow(self, leg: Leg, number: int, t0: float, t1: float, state: dict[str, Any]) -> None:
        """A leg of a span of terrain following (legs one after another that follow): the span's profile
        from the pass before (made by :meth:`_follow_profiles` from the whole span's track), or for now the
        height held."""
        span = self._spans[-1] if self._spans and self._spans[-1]["last"] == number - 1 else None
        if span is None:
            span = {"first": number, "last": number, "start": t0, "end": t1, "clearances": [(t0, leg.follow.clearance)], "follow": leg.follow, "state": state}
            self._spans.append(span)
            if number in self._follows:
                whole, end, after = self._follows[number]
                self.vertical.add(t0, whole)
                self.vertical.add(end, after)
            else:
                self.vertical.add(t0, linear(t0, state["height"], state["climb"]))
        else:
            span.update(last=number, end=t1)
            span["clearances"].append((t0, leg.follow.clearance))

    def _follow_profiles(self) -> dict[int, tuple[Callable[[np.ndarray], np.ndarray], float, Callable[[np.ndarray], np.ndarray]]]:
        """Each span's height over time from the planned track: the lowest curve over the ground and its
        clearance whose push-overs stay over ``push`` g and slopes under ``rate`` (an envelope of parabolas),
        smoothed by the bump of half-width ``smoothing`` with the margin that smoothing can lose added first;
        blended in from the height and rate the span starts with and out to level flight at its end (at the
        highest the profile is over the fade, so the fade never comes under it)."""
        out = {}
        self._integrate(0.0, self.end)
        for span in self._spans:
            f, t0, t1 = span["follow"], span["start"], span["end"]
            width, push = f.smoothing, (1.0 - f.push) * self.world.g0
            ts = np.arange(t0 - width, t1 + width + TERRAIN_STEP, TERRAIN_STEP)
            starts = np.array([a for a, _ in span["clearances"]])
            clearance = np.array([c for _, c in span["clearances"]])[np.clip(np.searchsorted(starts, ts, side="right") - 1, 0, len(starts) - 1)]
            need = self._ground_max(ts, TERRAIN_STEP) + clearance + self.context.margin + self.context.ground.margin_extra
            vmax = f.rate or 0.3 * float(np.max(self.speed(np.clip(ts, t0, t1))))
            smooth = _smoothed(ts, _envelope(ts, need, push, vmax) + 0.5 * push * width * width * BUMP_VARIANCE, width)
            h0, r0 = span["state"]["height"], span["state"]["climb"]
            before = linear(t0, h0, r0)
            gap = abs(float(smooth(np.array([t0]))[0]) - h0)
            blend_in = float(np.clip(1.5 * PEAK * gap / vmax, 2 * width, max(2 * width, 0.5 * (t1 - t0))))

            def profile(t: np.ndarray, smooth: Callable[[np.ndarray], np.ndarray] = smooth, before: Callable[[np.ndarray], np.ndarray] = before,
                        t0: float = t0, blend_in: float = blend_in) -> np.ndarray:
                w = step((np.asarray(t, dtype=float) - t0) / blend_in)
                return (1 - w) * before(t) + w * smooth(t)
            fade = min(2 * width, 0.25 * (t1 - t0))
            after = constant(float(np.max(profile(np.linspace(t1 - fade, t1, 64)))))      # level at the span's end, never under the profile

            def whole(t: np.ndarray, profile: Callable[[np.ndarray], np.ndarray] = profile, after: Callable[[np.ndarray], np.ndarray] = after,
                      t1: float = t1, fade: float = fade) -> np.ndarray:
                w = step((np.asarray(t, dtype=float) - (t1 - fade)) / fade)
                return (1 - w) * profile(t) + w * after(t)
            out[span["first"]] = (whole, t1, after)
        return out

    def _ground_max(self, ts: np.ndarray, spacing: float) -> np.ndarray:
        """The highest ground over each sample's interval [t − spacing/2, t + spacing/2] of the planned track."""
        known = self._t_known
        sub = (np.arange(TERRAIN_SUB) + 0.5) / TERRAIN_SUB - 0.5
        tt = (ts[:, None] + spacing * sub[None, :]).reshape(-1)
        p = self.position(np.clip(tt, 0.0, known))
        return self.context.ground.height(p[:, 0], p[:, 2]).reshape(len(ts), TERRAIN_SUB).max(axis=1)

    # landing
    def _landing(self, number: int, leg: Leg, t0: float, state: dict[str, Any], where: str) -> float:
        land, c = leg.land, self.context
        if state["level_speed"] <= 1.0:
            raise VidgenError(f"{where}: a landing needs speed")
        touch = land.touchdown or 0.8 * state["speed"]
        if touch > state["speed"] + 1e-9:
            raise VidgenError(f"{where}: land.touchdown ({touch:g} m/s) is over the speed when the approach starts ({state['speed']:.0f} m/s)")
        slow = abs(state["speed"] - touch) / self.spec.accel
        self.speed.add(t0, ramp(t0, slow, state["speed"], touch))
        self.speed.add(t0 + slow, constant(touch))
        sink = touch * math.tan(math.radians(land.glide))
        ground = float(c.ground.height(state["position"][0], state["position"][2]))
        if state["height"] - ground < land.flare:
            raise VidgenError(f"{where}: the approach starts {state['height'] - ground:.0f} m over the ground, under the flare height {land.flare:g} m: start it higher")
        for _ in range(3):
            self._trim(t0)
            descent = self._to_height(t0, state["height"], state["climb"], ground, sink, None, where, end_ramp=2 * land.flare / sink)
            touchdown = t0 + descent
            self._integrate(t0, touchdown)
            p = self.position(np.array([touchdown]))[0]
            new = float(c.ground.height(p[0], p[2]))
            if abs(new - ground) < 0.01:
                break
            ground = new
        stop_at = max(touchdown, t0 + slow)
        rolling = touch / land.brake
        self.speed.add(stop_at, ramp(stop_at, rolling, touch, 0.0))
        self.speed.add(stop_at + rolling, constant(0.0))
        end = stop_at + rolling
        self.landed.append((t0, end, ground))
        self.legs.append(LegRecord(number, "land", t0, end, {"touchdown": touchdown, "touchdown_speed": touch, "sink": sink, "ground": ground}))
        self._integrate(t0, end)
        return end

    # re-entry
    def _reentry(self, number: int, leg: Leg, t0: float) -> float:
        c, s = self.context, leg.reentry
        if c.flat:
            raise VidgenError(f"flight {self.name}: a re-entry needs the world's sphere (not a flat world)")
        p0, v0 = self._initial()
        entry = entry_profile(self.world, c.centre, c.spin, p0, v0, s)
        self.entry, self.entry_end = entry, entry.seconds
        self.speed.add(0.0, entry.speed)
        self.speed.add(entry.seconds, constant(float(s.to["speed"])))
        self.vertical.add(0.0, entry.height)
        self.vertical.add(entry.seconds, constant(float(s.to["height"])))

        def turn_rate(t: np.ndarray) -> np.ndarray:
            w = entry.blend_weight(t)
            banked = self.g_eff(t) * np.tan(entry.bank(t)) / np.maximum(self.level_speed(t), 1e-6)
            return (1 - w) * entry.kepler_turn_rate(t) + w * banked
        self.turn.add(0.0, turn_rate)
        self.turn.add(entry.seconds, constant(0.0))
        self.legs.append(LegRecord(number, "reentry", 0.0, entry.seconds, dict(entry.facts)))
        self._integrate(0.0, entry.seconds)
        return entry.seconds

    # ---------- the ground check ----------
    def _check(self, raise_error: bool) -> Callable[[np.ndarray], np.ndarray] | None:
        """The clearance over the ground on a fine grid; an error (or, with lift, the deficit to raise by)."""
        c = self.context
        stop = max(self.end, self._t_known)
        self._integrate(0.0, stop)
        coarse = np.linspace(0.0, stop, max(2, math.ceil(stop / 0.5)) + 1)
        low = self.height(coarse) < c.ground.ceiling + c.margin + 500.0       # under that the ground may be near: checked finely
        near = low | np.concatenate([low[1:], [False]]) | np.concatenate([[False], low[:-1]])
        fine = max(2, math.ceil(0.5 / (TERRAIN_STEP / TERRAIN_SUB)))
        tt = np.unique(np.concatenate([np.linspace(a, b, fine + 1) for a, b, keep in zip(coarse[:-1], coarse[1:], near[:-1] | near[1:]) if keep] or [np.zeros(1)]))
        p = self.position(tt)
        h = p[:, 1] if c.flat else self.height(tt)
        clearance = h - c.ground.height(p[:, 0], p[:, 2])
        wanted = np.full_like(tt, c.margin + c.ground.margin_extra)
        for a, b, level in self.landed:
            sel = (tt >= a) & (tt <= b + 1e-9)
            wanted[sel] = np.minimum(wanted[sel], h[sel] - level) - 0.1
        short = wanted - clearance
        if np.max(short) <= 1e-6:
            return None
        k = int(np.argmax(short))
        if raise_error:
            at = float(tt[k])
            place = f"x = {p[k, 0]:.0f} m, z = {p[k, 2]:.0f} m"
            if not c.flat:
                lat, lon, _ = c.frame.geodetic(p[k])
                place += f" ({float(lat):.4f}°, {float(lon):.4f}°)"
            leg = next((r for r in self.legs if r.start <= at <= r.end + 1e-9), None)
            what = f"leg {leg.number} ({leg.kind})" if leg else "after the last leg"
            raise VidgenError(f"flight {self.name}: at {at:.2f} s of the flight ({what}) the path is {clearance[k]:.1f} m over the ground at {place}, "
                              f"under the {wanted[k]:.0f} m it must keep ({c.margin:g} m margin): climb before it (a leg with climb: {{to: ...}}), "
                              "follow the terrain there (follow: {clearance: 300}), or give the flight lift: true to raise the path where it is too low")
        deficit = np.maximum(short, 0.0)
        for a, b, _ in self.landed:
            deficit[(tt >= a) & (tt <= b + 1e-9)] = 0.0
        return _smoothed_lift(tt, deficit, self.world.g0)

    def _raise_by(self, extra: Callable[[np.ndarray], np.ndarray]) -> None:
        previous = self.lift.pieces[0][1]
        self.lift = Channel([(0.0, lambda t, a=previous, b=extra: a(t) + b(t))])
        self.warnings.append(f"flight {self.name}: the path was raised where it came too near the ground (lift: true)")

    def _loads(self) -> None:
        stop = max(self.end, 1e-3)
        t = np.linspace(0.0, stop, max(64, math.ceil(stop / 0.25)) + 1)
        n = self.sample(t)["load"]
        k = int(np.argmax(np.abs(n)))
        if abs(n[k]) > self.spec.max_load:
            self.warnings.append(f"flight {self.name}: the load factor reaches {n[k]:.1f} g at {t[k]:.1f} s of the flight (more than max_load {self.spec.max_load:g}): "
                                 "a gentler bank, a wider curve or a slower pull-up keeps it lower")

    # ---------- the state at any time ----------
    def sample(self, t: Any) -> dict[str, np.ndarray]:
        """The flight at flight times ``t`` (before 0: the start): position, velocity, acceleration
        (local frame), quaternion (x, y, z, w: body x left, y up, z nose → local axes), speed, mach,
        height (over the sphere; a flat world: over y = 0), above_ground, load, bank, pitch, heading,
        aoa (radians), heating, density, lat, lon."""
        c, w = self.context, self.world
        t = np.atleast_1d(np.asarray(t, dtype=float))
        tc = np.maximum(t, 0.0)
        self._integrate(0.0, float(np.max(tc)))
        f, q = self._frames(tc)
        up, e, right = f[:, :, 0], f[:, :, 1], f[:, :, 2]
        h = self.height(tc)
        hd, hdd = self.climb_rate(tc), self.climb_rate(tc, 2)
        v, vd = self.speed(tc), self.speed.derivative(tc)
        vh = self.level_speed(tc)
        vhd = np.where(vh > 1e-6, (v * vd - hd * hdd) / np.maximum(vh, 1e-6), 0.0)
        turn = self.turn(tc)
        k = 0.0 if c.flat else 1.0 / (w.radius + h)
        pos = (q + h[:, None] * _UP) if c.flat else c.centre + (w.radius + h)[:, None] * up
        vel = hd[:, None] * up + vh[:, None] * e
        acc = (hdd - k * vh * vh)[:, None] * up + (vhd + k * hd * vh)[:, None] * e + (vh * turn)[:, None] * right
        spin = c.spin
        rel = pos - c.centre
        force = acc + 2 * np.cross(spin, vel) + np.cross(spin, np.cross(spin, rel)) + w.gravity(h)[:, None] * up
        fore = vel + 1e-3 * e
        fore /= np.linalg.norm(fore, axis=-1, keepdims=True)
        u0 = up - np.sum(up * fore, axis=-1, keepdims=True) * fore
        u0 /= np.linalg.norm(u0, axis=-1, keepdims=True)
        r0 = np.cross(fore, u0)
        f_up, f_side = np.sum(force * u0, axis=-1), np.sum(force * r0, axis=-1)
        g0 = w.g0
        soft = 0.5 * (f_up + np.sqrt(f_up * f_up + (0.1 * g0) ** 2))
        bank = np.arctan(f_side / soft)
        lift_g = np.hypot(f_up, f_side) / g0
        load = np.where(f_up >= 0, lift_g, -lift_g)
        aoa = np.radians(self.spec.aoa) * np.maximum(load, 0.0)
        if self.entry is not None:
            inside = tc < self.entry_end
            we = np.where(inside, self.entry.entry_weight(tc), 0.0)
            aoa = we * math.radians(self.spec.legs[0].reentry.aoa) + (1 - we) * aoa
            bank = np.where(inside, self.entry.blend_weight(tc) * self.entry.bank(tc), 0.0) + (1 - we) * bank
        body_up = np.cos(bank)[:, None] * u0 + np.sin(bank)[:, None] * r0
        nose = np.cos(aoa)[:, None] * fore + np.sin(aoa)[:, None] * body_up
        body_up = np.cos(aoa)[:, None] * body_up - np.sin(aoa)[:, None] * fore
        left = np.cross(body_up, nose)
        matrices = np.stack([left, body_up, nose], axis=-1)
        if c.flat:
            heading = np.mod(np.degrees(np.arctan2(e[:, 0], -e[:, 2])), 360.0)
            ground = c.ground.height(pos[:, 0], pos[:, 2])
            above = pos[:, 1] - ground
            lat = lon = np.full_like(t, np.nan)
        else:
            heading = c.frame.heading_of(pos, e)
            above = h - c.ground.height(pos[:, 0], pos[:, 2])
            lat, lon, _ = c.frame.geodetic(pos)
        air = w.air
        density = air.density_at(h) if air is not None else np.zeros_like(h)
        sound = w.sound_speed
        return {"time": t, "position": pos, "velocity": vel, "acceleration": acc, "matrix": matrices, "speed": v,
                "mach": v / sound if sound else np.full_like(v, np.nan), "height": h, "above_ground": above, "load": load,
                "bank": bank, "pitch": np.arctan2(hd, vh), "heading": np.radians(heading), "aoa": aoa,
                "heating": heating(density, v), "density": density, "lat": lat, "lon": lon, "climb": hd}

    def path(self, samples: int) -> np.ndarray:
        """``samples`` points of the path over the planned flight (local frame)."""
        return self.position(np.linspace(0.0, max(self.end, 1e-6), samples))


# ---------- helpers ----------
def _rodrigues(theta: np.ndarray) -> np.ndarray:
    """exp([θ]×) for rotation vectors (N, 3)."""
    angle = np.linalg.norm(theta, axis=-1)
    small = angle < 1e-8
    safe = np.where(small, 1.0, angle)
    a = np.where(small, 1 - angle**2 / 6, np.sin(angle) / safe)
    b = np.where(small, 0.5 - angle**2 / 24, (1 - np.cos(angle)) / (safe * safe))
    x, y, z = theta[:, 0], theta[:, 1], theta[:, 2]
    zero = np.zeros_like(x)
    k = np.stack([np.stack([zero, -z, y], -1), np.stack([z, zero, -x], -1), np.stack([-y, x, zero], -1)], -2)
    return np.eye(3) + a[:, None, None] * k + b[:, None, None] * (k @ k)


def _scan(steps: np.ndarray) -> np.ndarray:
    """Running products P_k = S_1 S_2 … S_k (right-multiplied), in log₂ N passes."""
    p = steps.copy()
    d = 1
    while d < len(p):
        p[d:] = p[:-d] @ p[d:]
        d *= 2
    return p


def _envelope(ts: np.ndarray, need: np.ndarray, push: float, vmax: float) -> np.ndarray:
    """The lowest curve over ``need`` whose downward bend is at most ``push`` (m/s²) and slope at most ``vmax``:
    max over samples of need − φ(t − tᵢ), φ a parabola that turns into a line of slope vmax."""
    knee = vmax / max(push, 1e-9)
    d = np.abs(ts[:, None] - ts[None, :])
    drop = np.where(d <= knee, 0.5 * push * d * d, vmax * d - 0.5 * vmax * knee)
    return np.max(need[None, :] - drop, axis=1)


def _smoothed(ts: np.ndarray, values: np.ndarray, width: float) -> Callable[[np.ndarray], np.ndarray]:
    """The samples convolved with the bump of half-width ``width`` (s): a smooth function of time."""
    spacing = float(ts[1] - ts[0]) if len(ts) > 1 else 1.0
    weight = spacing / (width * BUMP_AREA)
    reach = int(math.ceil(width / spacing)) + 1

    def fn(t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=float)
        flat = t.reshape(-1)
        i = np.clip(np.round((flat - ts[0]) / spacing).astype(np.int64), 0, len(ts) - 1)
        out = np.zeros_like(flat)
        for o in range(-reach, reach + 1):
            j = np.clip(i + o, 0, len(ts) - 1)
            inside = (i + o >= 0) & (i + o < len(ts))
            out += np.where(inside, values[j] * bump((flat - ts[j]) / width), 0.0)
        return (out * weight).reshape(t.shape)
    return fn


def _smoothed_lift(ts: np.ndarray, deficit: np.ndarray, g0: float, width: float = 4.0) -> Callable[[np.ndarray], np.ndarray]:
    """A smooth lift at least ``deficit`` (samples at times ts): the deficit and the smoothing's margin, its
    envelope at a push-over of 0.5 g and 30 m/s (with 0: a max of functions bent down at most 0.5 g), smoothed."""
    grid = np.arange(ts[0] - width, ts[-1] + width + TERRAIN_STEP, TERRAIN_STEP)
    cells = np.clip(np.round((ts - grid[0]) / TERRAIN_STEP).astype(np.int64), 0, len(grid) - 1)
    need = np.zeros_like(grid)
    np.maximum.at(need, cells, deficit)
    push = 0.5 * g0
    need = np.where(need > 0, need + 0.5 * push * width * width * BUMP_VARIANCE + 1.0, 0.0)
    return _smoothed(grid, np.maximum(_envelope(grid, need, push, 30.0), 0.0), width)


class _CurvePath:
    """A planar curve (east, north metres) made of septic Hermite pieces, an arc and a roll-out, with its
    curvature as a function of length along it (anticlockwise positive)."""

    def __init__(self, knots: list[np.ndarray], pieces: list[np.ndarray], where: str) -> None:
        self.knots, self.where = knots, where
        self._pieces = pieces
        self._table()
        self.into: tuple[float, float, float] | None = None         # the roll-in, the arc, the roll-out: (from s, length, curvature)
        self.arc: tuple[float, float, float] | None = None
        self.out: tuple[float, float, float] | None = None
        self.length = self._s[-1]

    @staticmethod
    def through(points: list[np.ndarray], tangent0: np.ndarray, where: str) -> "_CurvePath":
        pts = [np.asarray(p, dtype=float) for p in points]
        for i in range(1, len(pts)):
            if np.linalg.norm(pts[i] - pts[i - 1]) < 1.0:
                raise VidgenError(f"{where}: waypoint {i} is where the curve already is (less than 1 m from the place before)")
        n = len(pts)
        tangents, curvatures = [tangent0 / np.linalg.norm(tangent0)], [0.0]
        for i in range(1, n - 1):
            a, b = pts[i] - pts[i - 1], pts[i + 1] - pts[i]
            t = a / np.linalg.norm(a) + b / np.linalg.norm(b)
            t = t / np.linalg.norm(t) if np.linalg.norm(t) > 1e-9 else a / np.linalg.norm(a)
            tangents.append(t)
            curvatures.append(_circle_curvature(pts[i - 1], pts[i], pts[i + 1]))
        if n > 1:
            last = pts[-1] - pts[-2]
            tangents.append(last / np.linalg.norm(last))
            curvatures.append(0.0)
        pieces = [_hermite(pts[i], tangents[i], curvatures[i], pts[i + 1], tangents[i + 1], curvatures[i + 1]) for i in range(n - 1)]
        return _CurvePath(pts, pieces, where)

    @staticmethod
    def circling(centre: np.ndarray, radius: float, kappa: float, turns: float, tangent0: np.ndarray, roll: float, where: str) -> "_CurvePath":
        """In to a circle: a Hermite piece to the place where a roll-in of length ``roll`` (the curvature
        rising by S) must start so that it ends on the circle, the roll-in, ``turns`` times round, a roll-out."""
        roll = max(roll, 1.0)
        u = np.linspace(0.0, 1.0, 2001)
        heading = kappa * roll * step_integral(u)
        x = np.concatenate([[0.0], np.cumsum(0.5 * (np.cos(heading[1:]) + np.cos(heading[:-1])) * roll / 2000)])
        y = np.concatenate([[0.0], np.cumsum(0.5 * (np.sin(heading[1:]) + np.sin(heading[:-1])) * roll / 2000)])
        end = heading[-1]
        local = np.array([x[-1], y[-1]]) + np.array([-math.sin(end), math.cos(end)]) / kappa     # the circle's centre seen from the roll-in's start
        reach = centre - np.zeros(2)
        d = float(np.linalg.norm(reach))
        if d <= abs(local[1]) * 1.05 or d <= radius * 1.05:
            raise VidgenError(f"{where}: the circle's place is {d:.0f} m away, inside its radius {radius:g} m (or too near it): start farther out or give a smaller radius")
        alpha = math.asin(local[1] / d)
        best = None
        for angle in (math.atan2(reach[1], reach[0]) - alpha, math.atan2(reach[1], reach[0]) + alpha - math.pi):
            along = np.array([math.cos(angle), math.sin(angle)])
            turn = np.array([[along[0], -along[1]], [along[1], along[0]]])
            start = centre - turn @ local
            ahead = float(along @ start)
            if abs(along[0] * start[1] - along[1] * start[0]) < 1e-6 * d and ahead > 0 and (best is None or ahead < best[0]):
                best = (ahead, start, along)
        if best is None:
            raise VidgenError(f"{where}: no way into the circle from here: start farther from it")
        _, start, along = best
        path = _CurvePath([np.zeros(2), start], [_hermite(np.zeros(2), tangent0 / np.linalg.norm(tangent0), 0.0, start, along, 0.0)], where)
        path.into = (path.length, roll, kappa)
        path.arc = (path.length + roll, 2 * math.pi * radius * turns, kappa)
        path.out = (path.length + roll + path.arc[1], roll, kappa)
        path.length += 2 * roll + path.arc[1]
        return path

    def _table(self) -> None:
        rows = 4000
        u = np.linspace(0.0, 1.0, rows + 1)
        s_all, u_all, piece_all = [], [], []
        start = 0.0
        for k, c in enumerate(self._pieces):
            d1 = _poly(c, u, 1)
            speed = np.linalg.norm(d1, axis=-1)
            s = start + np.concatenate([[0.0], np.cumsum(_trapezoids(u, speed))])
            s_all.append(s if k == 0 else s[1:])
            u_all.append(u if k == 0 else u[1:])
            piece_all.append(np.full(len(u) if k == 0 else len(u) - 1, k))
            start = s[-1]
        self._s, self._u, self._k = np.concatenate(s_all), np.concatenate(u_all), np.concatenate(piece_all)

    def _hermite_curvature(self, s: np.ndarray) -> np.ndarray:
        s = np.clip(s, 0.0, self._s[-1])
        i = np.clip(np.searchsorted(self._s, s, side="right") - 1, 0, len(self._s) - 2)
        f = (s - self._s[i]) / np.maximum(self._s[i + 1] - self._s[i], 1e-12)
        same = self._k[i] == self._k[i + 1]
        u = np.where(same, self._u[i] + f * (self._u[i + 1] - self._u[i]), self._u[i])
        out = np.zeros_like(s)
        for k, c in enumerate(self._pieces):
            sel = self._k[i] == k
            if np.any(sel):
                d1, d2 = _poly(c, u[sel], 1), _poly(c, u[sel], 2)
                out[sel] = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / np.linalg.norm(d1, axis=-1) ** 3
        return out

    def curvature(self, s: np.ndarray) -> np.ndarray:
        s = np.asarray(s, dtype=float)
        out = self._hermite_curvature(s)
        if self.into is not None:
            i0, length, kappa = self.into
            out = np.where(s >= i0, kappa * step((s - i0) / length), out)
        if self.arc is not None:
            a0, length, kappa = self.arc
            out = np.where(s >= a0, kappa, out)
        if self.out is not None:
            o0, length, kappa = self.out
            out = np.where(s >= o0, kappa * (1 - step((s - o0) / length)), out)
        return out

    def max_curvature(self) -> tuple[float, int]:
        """The greatest |curvature| (1/m) and the number of the waypoint whose piece it lies in (1 the first)."""
        s = np.linspace(0.0, self.length, 20001)
        k = np.abs(self.curvature(s))
        i = int(np.argmax(k))
        row = min(int(np.searchsorted(self._s, min(s[i], self._s[-1]))), len(self._k) - 1)
        return float(k[i]), int(self._k[row]) + 1


def _trapezoids(u: np.ndarray, f: np.ndarray) -> np.ndarray:
    """The integral of f over each step of u by the trapezoid rule (the steps are fine)."""
    return 0.5 * (f[1:] + f[:-1]) * np.diff(u)


def _circle_curvature(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """The signed curvature (anticlockwise positive) of the circle through three points."""
    ab, bc, ac = b - a, c - b, c - a
    cross = ab[0] * ac[1] - ab[1] * ac[0]
    den = np.linalg.norm(ab) * np.linalg.norm(bc) * np.linalg.norm(ac)
    return float(2 * cross / den) if den > 1e-12 else 0.0


_HERMITE: np.ndarray | None = None


def _hermite(p0: np.ndarray, t0: np.ndarray, k0: float, p1: np.ndarray, t1: np.ndarray, k1: float) -> np.ndarray:
    """A septic polynomial piece (8 × 2 coefficients) from p0 to p1 with unit tangents t0, t1 and
    curvatures k0, k1 (anticlockwise), the curvature's rate zero at both ends: derivatives along u of
    a·t, κ a² n, −κ² a³ t (a the chord's length, n the left normal)."""
    global _HERMITE
    if _HERMITE is None:
        rows = []
        for at in (0.0, 1.0):
            for order in range(4):
                row = []
                for power in range(8):
                    coef = math.perm(power, order) if power >= order else 0
                    row.append(coef * at ** (power - order) if power >= order else 0.0)
                rows.append(row)
        _HERMITE = np.linalg.inv(np.array(rows))
    a = float(np.linalg.norm(p1 - p0))

    def ends(p: np.ndarray, t: np.ndarray, k: float) -> list[np.ndarray]:
        n = np.array([-t[1], t[0]])
        return [p, a * t, k * a * a * n, -k * k * a**3 * t]
    b = np.array(ends(p0, t0, k0) + ends(p1, t1, k1))
    return _HERMITE @ b


def _poly(c: np.ndarray, u: np.ndarray, order: int) -> np.ndarray:
    """The ``order``-th derivative along u of the piece (coefficients c, 8 × 2) at u: (N, 2)."""
    u = np.asarray(u, dtype=float)
    out = np.zeros((len(u), 2))
    for power in range(order, 8):
        out += math.perm(power, order) * np.power(u, power - order)[:, None] * c[power]
    return out


__all__ = ["FlightContext", "FlightRun", "LegRecord", "MAX_STEP"]
