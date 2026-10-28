"""Manoeuvres and gravity assists (Phase X, Step 231; DESIGN §98.5): burns in the local frame,
trajectories through burns with crash checks, Hohmann (LEO → GEO, Earth → Mars), bi-elliptic
thresholds, plane changes, phasing, the turning angle of a flyby and the sign of a gravity
assist's energy change, and the piecewise clock. Values are checked against formulas written out
here independently of the module."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vidgen import orbits
from vidgen.errors import VidgenError

MU_E = orbits.GM_EARTH
R_E = orbits.R_EARTH
DAY = 86400.0


def test_local_frame_and_burn_vectors() -> None:
    r, v = np.array([7e6, 0, 0]), np.array([0, 7.5e3, 0])
    frame = orbits.local_frame(r, v)
    assert frame == pytest.approx(np.array([[0, 1, 0], [1, 0, 0], [0, 0, 1]]))   # prograde, radial (out), normal
    dv = orbits.burn_vector(r, v, {"prograde": 100.0, "radial": 20.0, "anti_normal": 5.0})
    assert dv == pytest.approx([20.0, 100.0, -5.0])
    assert orbits.burn_components(r, v, dv) == pytest.approx([100.0, 20.0, -5.0])
    assert orbits.direction_name([-3.0, 0.1, 0]) == "retrograde" and orbits.direction_name([1.0, 0, 1.0]) == "prograde + normal"
    with pytest.raises(VidgenError, match="one of prograde"):
        orbits.burn_vector(r, v, {"forward": 1.0})


def test_leo_to_geo_hohmann() -> None:
    r1 = R_E + 300e3
    r2 = (MU_E * orbits.SIDEREAL_DAY**2 / (4 * math.pi**2)) ** (1 / 3)
    h = orbits.hohmann(MU_E, r1, r2)
    v1, v2 = math.sqrt(MU_E / r1), math.sqrt(MU_E / r2)
    dv1 = v1 * (math.sqrt(2 * r2 / (r1 + r2)) - 1)
    dv2 = v2 * (1 - math.sqrt(2 * r1 / (r1 + r2)))
    assert h.dv1 == pytest.approx(dv1, rel=1e-12) and h.dv2 == pytest.approx(dv2, rel=1e-12)
    assert h.dv1 / 1000 == pytest.approx(2.426, abs=0.001) and h.dv2 / 1000 == pytest.approx(1.467, abs=0.001)
    assert h.total / 1000 == pytest.approx(3.893, abs=0.001)
    assert h.time / 3600 == pytest.approx(math.pi * math.sqrt(((r1 + r2) / 2) ** 3 / MU_E) / 3600) and 5.2 < h.time / 3600 < 5.4
    # flown as two burns: prograde dv1 at the start, prograde dv2 at the transfer's apoapsis -> circular at r2
    start = orbits.Elements.from_a(MU_E, r1, 0.0)
    path = orbits.fly(start, [orbits.BurnPlan(0.0, {"prograde": h.dv1}), orbits.BurnPlan("apoapsis", {"prograde": h.dv2})], radius=R_E, body="Earth")
    final = path.arcs[-1].elements
    assert final.e < 1e-9 and final.a == pytest.approx(r2, rel=1e-10)
    assert path.burns[1].time == pytest.approx(h.time, rel=1e-10) and path.total_dv == pytest.approx(h.total)
    assert path.burns[0].direction == "prograde" and path.burns[1].orbit_before.e == pytest.approx(h.e)
    # the trajectory is continuous at the burn (the position does not jump)
    t = path.burns[1].time
    assert path.positions(t - 1e-3) == pytest.approx(path.positions(t + 1e-3), abs=20.0)
    # lowering: retrograde, with the same numbers in reverse
    down = orbits.hohmann(MU_E, r2, r1)
    assert down.dv1 == pytest.approx(h.dv2) and down.dv2 == pytest.approx(h.dv1) and not down.raising


def test_earth_to_mars_hohmann_in_the_circular_coplanar_approximation() -> None:
    earth, mars = orbits.ORBITS["earth"], orbits.ORBITS["mars"]
    mu = orbits.GM_SUN
    mu_e, mu_m = mu + earth.body.gm, mu + mars.body.gm
    h = orbits.hohmann(mu, earth.a, mars.a, mu_target=mu_m, mu_from=mu_e)
    assert h.dv1 / 1000 == pytest.approx(2.94, abs=0.01) and h.dv2 / 1000 == pytest.approx(2.65, abs=0.01)
    assert h.time / DAY == pytest.approx(258.9, abs=0.3)
    t_mars = 2 * math.pi * math.sqrt(mars.a**3 / mu_m)
    assert math.degrees(h.phase) == pytest.approx(180 - 360 * h.time / t_mars, abs=1e-9) and math.degrees(h.phase) == pytest.approx(44.3, abs=0.2)
    t_earth = 2 * math.pi * math.sqrt(earth.a**3 / mu_e)
    assert h.synodic / DAY == pytest.approx(1 / (1 / (t_earth / DAY) - 1 / (t_mars / DAY))) and h.synodic / DAY == pytest.approx(780, abs=1)
    assert orbits.synodic_period(t_earth, t_mars) == pytest.approx(h.synodic)
    # the wait for the window: Mars 60° ahead now closes to 44.3° at the rate n_E - n_M
    n_e, n_m = 2 * math.pi / t_earth, 2 * math.pi / t_mars
    wait = orbits.window_wait(math.radians(60), h.phase, n_e, n_m)
    assert wait == pytest.approx((math.radians(60) - h.phase) / (n_e - n_m)) and 30 * DAY < wait < 40 * DAY
    assert orbits.window_wait(h.phase, h.phase, n_e, n_m) == 0.0
    # inward (Earth -> Venus) the target trails at departure
    venus = orbits.ORBITS["venus"]
    assert math.degrees(orbits.hohmann(mu, earth.a, venus.a, mu_target=mu + venus.body.gm).phase) == pytest.approx(-54, abs=1)


def test_bielliptic_and_its_thresholds() -> None:
    first, second = orbits.bielliptic_thresholds()
    assert first == pytest.approx(11.9387654, abs=1e-6) and second == pytest.approx(15.58172, abs=1e-4)
    r1 = 7000e3
    for ratio, wins in ((10.0, False), (20.0, True)):
        r2 = ratio * r1
        hoh = orbits.hohmann(MU_E, r1, r2).total
        far = orbits.bielliptic(MU_E, r1, r2, 1000 * r2).total
        assert (far < hoh) is wins
    b = orbits.bielliptic(MU_E, r1, 15 * r1, 40 * r1)
    v1 = math.sqrt(MU_E / r1)
    a1 = (r1 + 40 * r1) / 2
    assert b.dv1 == pytest.approx(math.sqrt(MU_E * (2 / r1 - 1 / a1)) - v1)
    assert b.time == pytest.approx(math.pi * (math.sqrt(a1**3 / MU_E) + math.sqrt(((15 * r1 + 40 * r1) / 2) ** 3 / MU_E)))
    with pytest.raises(VidgenError, match="must lie beyond both orbits"):
        orbits.bielliptic(MU_E, r1, 2 * r1, 1.5 * r1)
    with pytest.raises(VidgenError, match="the same: no transfer"):
        orbits.hohmann(MU_E, r1, r1)


def test_plane_change() -> None:
    v = 7.7e3
    assert orbits.plane_change(v, math.radians(28.5)) == pytest.approx(2 * v * math.sin(math.radians(14.25)))
    assert orbits.combined_plane_change(v, v, math.radians(30)) == pytest.approx(orbits.plane_change(v, math.radians(30)))
    assert orbits.combined_plane_change(1600.0, 3070.0, 0.0) == pytest.approx(1470.0)
    # the burn that turns the plane by 30° without changing the speed: |Δv| = 2 v sin(15°)
    start = orbits.Elements.from_a(MU_E, 7000e3, 0.0)
    v = math.sqrt(MU_E / 7000e3)
    di = math.radians(30)
    path = orbits.fly(start, [orbits.BurnPlan(0.0, {"prograde": -v * (1 - math.cos(di)), "normal": v * math.sin(di)})])
    after = path.arcs[-1].elements
    assert math.degrees(after.i) == pytest.approx(30) and after.e < 1e-9 and path.burns[0].magnitude == pytest.approx(orbits.plane_change(v, di))
    with pytest.raises(VidgenError, match="0° to 180°"):
        orbits.plane_change(v, 4.0)


def test_phasing() -> None:
    r = R_E + 400e3
    with pytest.raises(VidgenError, match="dip to 6,271 km .* inside it .* more revolutions"):   # 20° in one turn from 400 km: too low
        orbits.phasing(MU_E, r, math.radians(20), radius=R_E, body="Earth")
    ph = orbits.phasing(MU_E, r, math.radians(20), 3, radius=R_E, body="Earth")
    period = 2 * math.pi * math.sqrt(r**3 / MU_E)
    assert ph.period == pytest.approx(period * (1 - 20 / (3 * 360))) and ph.lower and R_E < ph.other_apsis < r
    # after three phasing turns the chaser is back where it burned, and the target (20° ahead) is there too
    assert (2 * math.pi * ph.time / period) % (2 * math.pi) == pytest.approx(2 * math.pi - math.radians(20))
    assert ph.total == pytest.approx(2 * abs(math.sqrt(MU_E * (2 / r - 1 / ph.a)) - math.sqrt(MU_E / r)))
    assert not orbits.phasing(MU_E, r, math.radians(-20)).lower
    with pytest.raises(VidgenError, match="dip to .* inside it .* more revolutions"):
        orbits.phasing(MU_E, r, math.radians(170), radius=R_E, body="Earth")


def test_trajectory_crash_and_apsis_errors() -> None:
    start = orbits.Elements.from_a(MU_E, R_E + 300e3, 0.0)
    with pytest.raises(VidgenError, match=r"burns\[1\]: the orbit after it has its periapsis .* inside it .* would hit Earth"):
        orbits.fly(start, [orbits.BurnPlan(60.0, {"retrograde": 500.0})], radius=R_E, body="Earth")
    with pytest.raises(VidgenError, match="circular, it has no apoapsis"):
        orbits.fly(start, [orbits.BurnPlan("apoapsis", {"prograde": 100.0})])
    with pytest.raises(VidgenError, match="in time order"):
        orbits.fly(start, [orbits.BurnPlan(600.0, {"prograde": 10.0}), orbits.BurnPlan(300.0, {"prograde": 10.0})])
    # a small retrograde burn whose new periapsis stays above the ground is fine; a later burn may circularise
    path = orbits.fly(start, [orbits.BurnPlan(0.0, {"retrograde": 30.0}), orbits.BurnPlan("periapsis", {"retrograde": 30.0})], radius=R_E, body="Earth")
    assert path.arcs[1].elements.periapsis > R_E and path.burns[1].time == pytest.approx(path.arcs[1].elements.period / 2, rel=1e-9)
    # a crash after the scene's horizon is still a crash when the last arc reaches it
    assert orbits.crash_time(orbits.Elements.from_periapsis(MU_E, R_E - 1e5, 0.3, nu=1.0), R_E) is not None


def test_turning_angle_and_flyby_geometry() -> None:
    mu_j = orbits.BODIES["jupiter"].gm
    v_inf, rp = 5.6e3, 6 * 71_492e3
    fb = orbits.flyby(mu_j, v_inf, rp, radius=71_492e3, direction=math.radians(150))
    e = 1 + rp * v_inf**2 / mu_j
    assert fb.e == pytest.approx(e) and math.sin(fb.delta / 2) == pytest.approx(1 / e)
    assert fb.elements.e == pytest.approx(e, rel=1e-9) and fb.elements.periapsis == pytest.approx(rp, rel=1e-9)
    # far before and after: the speed tends to v∞ and the direction turns by δ
    far = 1e5 * 86400.0
    _, v_before = fb.elements.states(-far)
    _, v_after = fb.elements.states(far)
    assert np.linalg.norm(v_before) == pytest.approx(v_inf, rel=2e-4) and np.linalg.norm(v_after) == pytest.approx(v_inf, rel=2e-4)
    turn = math.atan2(np.cross(v_before, v_after)[2], v_before @ v_after)
    assert turn == pytest.approx(fb.delta, abs=2e-3)
    assert math.atan2(v_before[1], v_before[0]) == pytest.approx(math.radians(150), abs=2e-3)
    assert fb.v_periapsis == pytest.approx(math.sqrt(v_inf**2 + 2 * mu_j / rp))
    assert fb.b == pytest.approx(rp * math.sqrt(1 + 2 * mu_j / (rp * v_inf**2)))   # the aiming distance
    with pytest.raises(VidgenError, match="lies inside Jupiter .* would crash"):
        orbits.flyby(mu_j, v_inf, 60_000e3, radius=71_492e3, body="Jupiter")
    with pytest.raises(VidgenError, match="inside the atmosphere of Earth"):
        orbits.flyby(MU_E, 9e3, R_E + 80e3, radius=R_E, atmosphere=100e3, body="Earth")
    assert orbits.turning_angle(MU_E, 1e3, R_E + 300e3) > math.radians(150)   # slow and close: turned almost back


def test_gravity_assist_gains_behind_and_loses_in_front() -> None:
    mu_j = orbits.BODIES["jupiter"].gm
    v_planet = [13.06e3, 0.0]
    v_inf_in = 5.6e3 * np.array([math.cos(math.radians(100)), math.sin(math.radians(100))])
    rp = 5 * 71_492e3
    behind = orbits.gravity_assist(mu_j, v_planet, v_inf_in, rp, side="behind", radius=71_492e3)
    front = orbits.gravity_assist(mu_j, v_planet, v_inf_in, rp, side="in_front", radius=71_492e3)
    assert behind.gain > 0 > front.gain and behind.energy_change > 0 > front.energy_change
    for ga in (behind, front):
        assert ga.energy_change == pytest.approx((ga.speed_after**2 - ga.speed_before**2) / 2, rel=1e-9)
        assert np.linalg.norm(ga.flyby.v_out) == pytest.approx(5.6e3)   # v∞ out = v∞ in in size
    # behind: the periapsis lies on the side the planet comes from (opposite its velocity)
    assert behind.flyby.periapsis_point @ np.array([1.0, 0, 0]) < 0 < front.flyby.periapsis_point @ np.array([1.0, 0, 0])
    with pytest.raises(VidgenError, match="not one of behind"):
        orbits.gravity_assist(mu_j, v_planet, v_inf_in, rp, side="above")
    # arriving from ahead-left at 150°: both ways past go behind (both gain); in front is impossible
    late = 5.6e3 * np.array([math.cos(math.radians(150)), math.sin(math.radians(150))])
    assert orbits.gravity_assist(mu_j, v_planet, late, rp, side="behind", body="Jupiter").gain > 0
    with pytest.raises(VidgenError, match="at 150° to Jupiter's motion, both ways past it go behind it"):
        orbits.gravity_assist(mu_j, v_planet, late, rp, side="in_front", body="Jupiter")


def test_playback_through_events_and_holds() -> None:
    plain = orbits.Playback(1.0, 10.0, 100.0)
    assert plain.rate(3.0) == pytest.approx(10.0) and plain.rates() == pytest.approx([10.0])
    pb = orbits.Playback.timed(1.0, 10.0, 100.0, [(6.0, 80.0, "burn:1")], [(2.0, 3.0, "pause")])
    assert pb.sim_time(1.0) == 0 and pb.sim_time(6.0) == pytest.approx(80.0) and pb.sim_time(11.0) == pytest.approx(100.0)
    assert pb.sim_time(2.0) == pytest.approx(pb.sim_time(3.0)) and pb.rate(2.5) == 0.0
    assert pb.rate(4.0) == pytest.approx(80.0 / 4.0) and pb.rate(8.0) == pytest.approx(20.0 / 5.0)
    times = np.linspace(1.0, 11.0, 200)
    sims = [pb.sim_time(t) for t in times]
    assert all(b >= a for a, b in zip(sims, sims[1:]))   # never backwards
    with pytest.raises(VidgenError, match="before the motion starts"):
        orbits.Playback.timed(1.0, 10.0, 100.0, [(0.5, 10.0, "burn:1")], [])
    with pytest.raises(VidgenError, match="same order"):
        orbits.Playback.timed(1.0, 10.0, 100.0, [(3.0, 50.0, "burn:2"), (6.0, 20.0, "burn:1")], [])
    with pytest.raises(VidgenError, match="over the word of burn:1"):
        orbits.Playback.timed(1.0, 10.0, 100.0, [(6.0, 50.0, "burn:1")], [(5.0, 7.0, "pause")])
