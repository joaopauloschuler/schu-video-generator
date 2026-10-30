"""Wavy hair (DESIGN.md §102.17): long waving locks past the jaw that leave the face, the chin
and the chest clear, trailing in the wind like long hair."""

from __future__ import annotations

import numpy as np
import pytest

from vidgen.cartoon.character import TRAIL_ATTRIBUTE
from vidgen.cartoon.generator import WAVY_LENGTH, Frame, _wavy_outline, generate_parts, resolve_proportions
from vidgen.config import CharacterEntry, CharacterLook

COLORS = {"skin": "#F0D2B4", "clothes": "#3C6E71", "trim": "#1E2233", "outline": "#1F2430", "features": "#1F2430",
          "hair": "#2A1810", "accessory": "#5FFFE0"}


def frame(front: bool) -> Frame:
    return Frame.of(resolve_proportions(CharacterLook(hair="wavy")), front)


def head_points(look: CharacterLook, front: bool) -> np.ndarray:
    head = next(p for p in generate_parts(look, COLORS, front=front) if p.name == "head")
    return np.concatenate([m.points for m in head.shapes["default"].family_members_with_points()])


def test_the_config_takes_wavy_hair() -> None:
    assert CharacterEntry(name="a", look={"hair": "wavy"}).look.hair == "wavy"


@pytest.mark.parametrize("front", [False, True])
def test_the_locks_fall_past_the_jaw_lower_than_long_hair(front: bool) -> None:
    f = frame(front)
    r, cy = f.p.head_radius, f.head_y
    lowest = min(y for _, y in _wavy_outline(f))
    assert lowest == pytest.approx(cy - (WAVY_LENGTH + 0.1) * r, abs=0.02 * r)
    wavy, long = (head_points(CharacterLook(hair=h), front)[:, 1].min() for h in ("wavy", "long"))
    assert wavy < long - 0.3 * r


def test_from_the_front_both_sides_wave_and_the_chin_stays_clear() -> None:
    f = frame(True)
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    points = _wavy_outline(f)
    xs = [x - cx for x, _ in points]
    assert min(xs) == pytest.approx(-max(xs))   # symmetric
    left = [(x - cx, y - cy) for x, y in points if x < cx - 1.05 * r and y < cy]
    steps = np.sign(np.diff([x for x, _ in left]))
    assert np.count_nonzero(np.diff(steps[steps != 0])) >= 3   # in and out: waves, not a straight edge
    # nothing of the hair hangs below the chin in the middle (the chest and a pendant show)
    below_chin = [(x, y) for x, y in points if y < cy - 1.05 * r]
    assert all(abs(x - cx) > 0.5 * r for x, _ in below_chin)


def test_from_the_side_the_hair_hangs_down_the_back() -> None:
    f = frame(False)
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    below = [(x, y) for x, y in _wavy_outline(f) if y < cy - 1.0 * r]
    assert below and all(x < cx - 0.3 * r for x, _ in below)   # behind the head (it faces right)


def test_wavy_hair_trails_in_the_wind_and_draws_the_same_twice() -> None:
    look = CharacterLook(hair="wavy")
    head = next(p for p in generate_parts(look, COLORS) if p.name == "head")
    assert any(getattr(m, TRAIL_ATTRIBUTE, None) is not None for m in head.shapes["default"].get_family())
    assert np.array_equal(head_points(look, False), head_points(look, False))
