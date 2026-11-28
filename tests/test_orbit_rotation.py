"""Body rotation data (Step 367) and the third dimension of the orbit model:
periods and tilts against the published values, frames and quaternions, 3D state
round trips, burns out of the plane, transfers in an inclined plane, the n-body angular momentum."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vidgen import orbits
from vidgen.errors import VidgenError
from vidgen.orbits import rotation as rot
from vidgen.orbits.elements import Elements

PLANETS = ["mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune"]


def _orbit_normal(key: str) -> np.ndarray:
    _, _, inc, _, _, node = orbits.TABLE1[key][0]
    i, o = math.radians(inc), math.radians(node)
    return np.array([math.sin(i) * math.sin(o), -math.sin(i) * math.cos(o), math.cos(i)])


def test_every_body_of_the_brief_has_rotation_data_with_a_source() -> None:
    assert set(rot.ROTATIONS) == {"sun", *PLANETS, "moon", "io", "europa", "ganymede", "callisto"}
    for m in rot.ROTATIONS.values():
        assert m.source and m.mean_radius > 0 and len(m.radii) == 3 and m.radii[0] >= m.radii[2]


@pytest.mark.parametrize("key", sorted(rot.ROTATIONS))
def test_the_period_from_the_formula_is_the_published_sidereal_period(key: str) -> None:
    m = rot.ROTATIONS[key]
    assert m.period / 3600 == pytest.approx(m.period_published_h, rel=2e-4)
    assert m.retrograde == (key in ("venus", "uranus"))


@pytest.mark.parametrize("key", PLANETS)
def test_the_tilt_from_the_pole_and_the_orbit_is_the_published_obliquity(key: str) -> None:
    m = rot.ROTATIONS[key]
    assert rot.obliquity(m, _orbit_normal(key)) == pytest.approx(m.obliquity_published, abs=0.05)


def test_the_sun_the_moon_and_the_galilean_moons() -> None:
    assert rot.obliquity(rot.ROTATIONS["sun"], [0, 0, 1]) == pytest.approx(7.25, abs=0.01)
    assert rot.obliquity(rot.ROTATIONS["moon"], [0, 0, 1]) == pytest.approx(1.54, abs=0.01)   # Cassini's laws: the equator 1.54° to the ecliptic
    assert rot.ROTATIONS["moon"].period / 86400 == pytest.approx(27.321661, rel=1e-6)   # once per sidereal month
    jupiter = rot.ROTATIONS["jupiter"].pole(rot.J2000_JD)
    for key, days in orbits.GALILEAN_PERIODS.items():
        m = rot.ROTATIONS[key]
        assert m.synchronous and m.period / 86400 == pytest.approx(days, rel=1e-6)
        assert math.degrees(math.acos(m.pole(rot.J2000_JD) @ jupiter)) < 0.5   # in Jupiter's equator


def test_frames_are_rotations_and_quaternions_match_them() -> None:
    jds = rot.J2000_JD + np.array([0.0, 1234.5, -9000.25])
    for m in rot.ROTATIONS.values():
        frames = m.frame(jds)
        assert np.allclose(np.einsum("nji,njk->nik", frames, frames), np.eye(3), atol=1e-14)
        assert np.allclose(np.linalg.det(frames), 1.0)
        assert np.allclose(frames[:, :, 2], m.pole(jds), atol=1e-14)   # z is the north pole
        for f, q in zip(frames, rot.quaternions(frames)):
            x, y, z, w = q
            back = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                             [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                             [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            assert np.allclose(back, f, atol=1e-14) and w >= 0


def test_the_earths_pole_is_the_ecliptic_pole_tilted_by_the_obliquity() -> None:
    eps = math.radians(rot.OBLIQUITY_J2000_DEG)
    assert np.allclose(rot.ROTATIONS["earth"].pole(rot.J2000_JD), [0.0, math.sin(eps), math.cos(eps)], atol=1e-15)
    turn = rot.equator_frame(rot.ROTATIONS["earth"], rot.J2000_JD)
    assert np.allclose(turn, [[1, 0, 0], [0, math.cos(eps), math.sin(eps)], [0, -math.sin(eps), math.cos(eps)]], atol=1e-15)   # the equatorial frame


def test_the_prime_meridian_turns_at_the_rate_of_the_period() -> None:
    m = rot.ROTATIONS["mars"]
    w0, w1 = m.prime_meridian(rot.J2000_JD), m.prime_meridian(rot.J2000_JD + m.period / 86400)
    assert (w1 - w0 + 180) % 360 - 180 == pytest.approx(0.0, abs=1e-6)


def test_unknown_body_gets_did_you_mean() -> None:
    with pytest.raises(VidgenError, match="did you mean 'europa'"):
        rot.rotation_model("europe")


# ----- the third dimension of the orbit model (Step 367 audit) -----------------------------------------


def test_state_vectors_and_elements_round_trip_in_three_dimensions() -> None:
    rng = np.random.default_rng(7)
    for _ in range(300):
        e = float(rng.choice([0.0, rng.uniform(0, 0.95), rng.uniform(1.05, 3.0)]))
        i = float(rng.choice([0.0, math.pi, math.pi / 2, rng.uniform(0, math.pi)]))
        limit = math.acos(-1 / e) if e > 1 else math.pi
        el = Elements(3.986e14, 7e6 * (1 + e), e, i, rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi), 0.9 * rng.uniform(-1, 1) * limit)
        back = Elements.from_state(el.mu, *el.state())
        for t in (0.0, 5e3, 9e4):
            (r1, v1), (r2, v2) = el.states(t), back.states(t)
            assert np.linalg.norm(r1 - r2) <= 1e-11 * np.linalg.norm(r1) and np.linalg.norm(v1 - v2) <= 1e-11 * np.linalg.norm(v1)


def test_a_normal_burn_tilts_the_plane() -> None:
    el = Elements(orbits.GM_EARTH, 7e6, 0.0)
    v = float(np.linalg.norm(el.state()[1]))
    after = orbits.fly(el, [orbits.BurnPlan(0.0, {"normal": 1000.0})]).burns[0].orbit_after
    assert after.i == pytest.approx(math.atan2(1000.0, v), abs=1e-14)


@pytest.mark.parametrize("inc", [0.0, 30.0, 60.0, 89.0, 150.0])
def test_a_transfer_between_orbits_in_an_inclined_plane_meets_its_target(inc: float) -> None:
    from vidgen.scenes.orbit_parts import OrbitBody, OrbitTransfer, resolve_model

    bodies = [OrbitBody(name="Ship", altitude="400 km", i=inc, raan=20), OrbitBody(name="Target", altitude="2000 km", i=inc, raan=20, nu=80)]
    model = resolve_model("earth", bodies, span=None, orbit_count=None, dynamics="kepler", method="leapfrog", step=None, follow=None,
                          transfer=OrbitTransfer(ship="Ship", to="Target"))
    assert model.transfer.miss < 1.0   # m; before Step 367 the lead angle was measured in the x-y plane: 221 km off at 30°, 10 125 km at 89°
    assert model.transfer.phase_at_depart == pytest.approx(model.transfer.phase_needed, abs=1e-9)


def test_the_lead_angle_in_the_reference_plane_is_the_old_arithmetic() -> None:
    from vidgen.scenes.orbit_parts import OrbitBody, build_system, lead_angle

    system = build_system("sun", [OrbitBody(preset="earth", e=0, i=0, raan=0, argp=0), OrbitBody(preset="mars", e=0, i=0, raan=0, argp=0, nu=95)])
    r_s, r_t = system.orbiter("Earth").positions(1e6), system.orbiter("Mars").positions(1e6)
    old = (math.atan2(r_t[1], r_t[0]) - math.atan2(r_s[1], r_s[0]) + math.pi) % (2 * math.pi) - math.pi
    assert lead_angle(system, "Earth", "Mars", 1e6) == old


def test_the_n_body_angular_momentum_check_covers_the_whole_vector() -> None:
    sun = orbits.BODIES["sun"]
    tilted = orbits.System(sun, (orbits.Orbiter("P", orbits.Body("P", 1e18), Elements.from_a(sun.gm, 1.5e11, 0.3, i=math.radians(40), raan=1.0)),
                                  orbits.Orbiter("Q", orbits.Body("Q", 1e18), Elements.from_a(sun.gm, 2.5e11, 0.1, i=math.radians(10))),))
    run = orbits.simulate(tilted, 3e7, samples=50)
    assert np.max(np.abs(run.angular_xy)) > 1e10 * np.finfo(float).eps * run.angular_scale   # the x and y parts are there
    assert run.angular_drift < 1e-10
    flat = orbits.System(sun, (orbits.Orbiter("P", orbits.Body("P", 1e18), Elements.from_a(sun.gm, 1.5e11, 0.3)),))
    flat_run = orbits.simulate(flat, 3e7, samples=50)
    assert not np.any(flat_run.angular_xy)   # exactly zero: a flat system's check is its z part alone, as before
    assert flat_run.angular_drift == max(abs(flat_run.angular_error(k)) for k in range(len(flat_run.times)))


def test_equatorial_presets_are_marked() -> None:
    planes = {k: p.plane for k, p in orbits.ORBITS.items()}
    assert {k for k, v in planes.items() if v == "equator"} == {"iss", "geo", "io", "europa", "ganymede", "callisto"}
