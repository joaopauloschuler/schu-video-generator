"""Step 82: the damped spring for secondary motion (no manim): closed-form values at fixed times,
settling within its settle time, no overshoot when critically damped, the same result as the
spring's equation stepped finely, and follow-through on it switched off by ``cartoon_motion: none``."""

from __future__ import annotations

import math

import pytest

from test_cartoon_acting import figure
from vidgen import api
from vidgen.cartoon.motion import FOLLOW_SPRING, follow_angles, follow_through
from vidgen.cartoon.spring import Spring
from vidgen.cartoon.transition import Walk

SPRINGS = [Spring.tuned(2.0, 0.5), Spring.tuned(1.0, 0.15), Spring.tuned(3.0, 1.0), Spring.tuned(2.0, 2.5)]


def stepped(spring: Spring, target, seconds: float, dt: float = 2e-5) -> float:
    """``x'' = k (s − x) − c x'`` stepped with semi-implicit Euler: the reference."""
    x, v = target(0.0), 0.0
    for k in range(round(seconds / dt)):
        v += (spring.stiffness * (target(k * dt) - x) - spring.damping * v) * dt
        x += v * dt
    return x


def test_tuned_and_closed_form_values() -> None:
    spring = Spring.tuned(2.0, 0.5)
    assert spring.angular_frequency == pytest.approx(4 * math.pi) and spring.damping_ratio == pytest.approx(0.5)
    assert spring.stiffness == pytest.approx(16 * math.pi**2) and spring.damping == pytest.approx(4 * math.pi)
    assert spring.step_response(0.0) == 0.0 == spring.step_response(-1.0)
    assert spring.step_response(0.1) == pytest.approx(1 - math.exp(-0.2 * math.pi) * (math.cos(0.4 * math.pi * math.sqrt(0.75)) + math.sin(0.4 * math.pi * math.sqrt(0.75)) / math.sqrt(3)))
    assert spring.step_response(0.1) == pytest.approx(0.4796, abs=1e-4)
    peak = math.pi / (4 * math.pi * math.sqrt(0.75))   # first turning point π/ω_d
    assert spring.step_response(peak) == pytest.approx(1 + spring.overshoot()) and spring.overshoot() == pytest.approx(0.1630, abs=1e-4)
    critical = Spring.tuned(3.0, 1.0)
    assert critical.is_critical and critical.step_response(0.1) == pytest.approx(1 - math.exp(-0.6 * math.pi) * (1 + 0.6 * math.pi))
    with pytest.raises(ValueError):
        Spring(1.0, 0.0)   # never settles
    with pytest.raises(ValueError):
        spring.settle_seconds(0.0)


@pytest.mark.parametrize("spring", SPRINGS, ids=lambda s: f"zeta{s.damping_ratio:.2f}")
def test_settles_within_its_settle_time(spring: Spring) -> None:
    for tolerance in (0.05, 0.02, 0.005):
        settle = spring.settle_seconds(tolerance)
        assert abs(1 - spring.step_response(settle - 1e-3)) > tolerance   # not before
        assert max(abs(1 - spring.step_response(settle + k * settle / 500)) for k in range(2000)) <= tolerance + 1e-9


def test_no_overshoot_when_critically_damped() -> None:
    for spring in (Spring.tuned(3.0, 1.0), Spring.tuned(0.5, 1.0), Spring.tuned(2.0, 2.5)):
        assert spring.overshoot() == 0.0
        response = [spring.step_response(k / 200) for k in range(2000)]
        assert all(b >= a for a, b in zip(response, response[1:])) and max(response) <= 1.0   # rises, never past
        step = lambda s: 1.0 if s >= 0.1 else 0.0   # noqa: E731
        assert max(spring.follow(step, k / 100) for k in range(400)) <= 1.0 + 1e-9
    assert Spring.tuned(3.0, 0.99).overshoot() > 0   # just below critical it does


@pytest.mark.parametrize("spring", SPRINGS, ids=lambda s: f"zeta{s.damping_ratio:.2f}")
def test_follow_matches_the_spring_equation(spring: Spring) -> None:
    def target(s: float) -> float:   # smooth, at rest before 0
        s = max(s, 0.0)
        return math.sin(3 * s) + min(s, 0.5)

    for seconds in (0.05, 0.3, 1.2, 3.0):
        assert spring.follow(target, seconds) == pytest.approx(stepped(spring, target, seconds), abs=5e-3)
    assert spring.follow(lambda s: 2.5, 0.7) == pytest.approx(2.5)
    assert spring.follow(target, 0.4) == spring.follow(target, 0.4)   # pure: no state between calls


def test_follow_through_runs_on_the_spring_and_none_turns_it_off() -> None:
    assert follow_through(lambda s: min(max(s, 0.0), 1.0), 1.3, Spring.tuned(2.0, 1.0)) >= -1e-9   # critical: no swing back
    assert follow_through(lambda s: min(max(s, 0.0), 1.0), 1.3, FOLLOW_SPRING) < -0.1   # the default swings back
    assert set(follow_angles(-1.0, 1.0, 0.0).values()) == {0.0}
    def head_angles(motion: str) -> set[float]:
        hero = figure().shift([-3.0, -2.0, 0.0])
        walk = Walk(hero, 2.0, motion=motion)
        walk.begin()
        angles = set()
        for k in range(31):
            walk.interpolate(k / 30)
            angles.add(round(hero.state().parts["head"].angle, 9))
        walk.finish()
        return angles

    assert head_angles("none") == {round(figure().state().parts["head"].angle, 9)}   # no follow-through offset
    assert len(head_angles("lively")) > 5   # the head trails and swings on the spring

def test_spring_is_in_the_api() -> None:
    assert api.Spring is Spring and "Spring" in api.__all__
