"""Step 72: automatic life (blinking, breathing, head sway) and how it composes with poses and lip sync."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from conftest import minimal_config
from vidgen.cartoon.character import Character, build_character
from vidgen.cartoon.generator import generate_parts
from vidgen.cartoon.idle import (
    BLINK_GAP_SECONDS,
    BLINK_SECONDS,
    BREATH_SCALE,
    SWAY_DEGREES,
    IdleClock,
    blink_times,
    breath_scale,
    idle_seed,
    sway_angle,
)
from vidgen.cartoon.transition import PoseChange
from vidgen.cartoon.visemes import VisemeCue, VisemeTrack
from vidgen.config import CharacterEntry, CharacterLook, parse_config
from vidgen.errors import VidgenError
from vidgen.theme import Theme

FPS = 30
FRAME = 1.0 / FPS


def pip(**entry) -> Character:
    return build_character(CharacterEntry(name="pip", **entry), theme=Theme())


def points(c: Character) -> np.ndarray:
    return np.concatenate([m.points for m in c.family_members_with_points()])


# ----- the schedule (no manim) ---------------------------------------------------------------


def test_blink_times_are_deterministic_for_a_seed() -> None:
    assert blink_times(7, 60.0) == blink_times(7, 60.0)
    assert blink_times(7, 60.0) != blink_times(8, 60.0)
    assert blink_times(7, 30.0) == [b for b in blink_times(7, 60.0) if b[0] < 30.0]


@pytest.mark.parametrize("seed", [0, 1, 42, idle_seed("pip")])
def test_blinks_are_two_to_six_seconds_apart(seed: int) -> None:
    blinks = blink_times(seed, 120.0)
    starts = [start for start, _ in blinks]
    low, high = BLINK_GAP_SECONDS
    assert low <= starts[0] <= high
    assert all(low <= b - a <= high for a, b in zip(starts, starts[1:]))
    assert all(end - start == pytest.approx(BLINK_SECONDS) for start, end in blinks)
    assert 120.0 / high <= len(blinks) <= 120.0 / low


@pytest.mark.parametrize("seed", range(20))
def test_no_blink_overlaps_a_pose_change(seed: int) -> None:
    changes = [(1.0, 1.8), (3.0, 3.5), (5.2, 9.0), (12.4, 12.9), (12.8, 13.6), (20.0, 20.6)]
    blinks = blink_times(seed, 30.0, pose_changes=changes)
    assert blinks
    for start, end in blinks:
        assert start < end
        assert all(end <= a or start >= b for a, b in changes), (start, end)


def test_pose_changes_pause_the_idle_clock_and_cut_a_running_blink() -> None:
    free = blink_times(3, 40.0)
    first, second = free[0], free[1]
    change = (first[0] + 0.05, first[0] + 1.05)  # starts during the first blink, lasts 1 s
    paused = blink_times(3, 40.0, pose_changes=[change])
    assert paused[0] == (first[0], change[0])
    assert paused[1] == pytest.approx((second[0] + 1.0, second[1] + 1.0))
    early = blink_times(3, 40.0, pose_changes=[(first[0] - 1.0, first[0] - 0.5)])
    assert early[0] == pytest.approx((first[0] + 0.5, first[1] + 0.5))


def test_a_bad_pose_change_window_is_an_error() -> None:
    with pytest.raises(VidgenError, match="must end after it starts"):
        blink_times(1, 10.0, pose_changes=[(2.0, 2.0)])


def test_idle_clock_follows_blink_times_frame_by_frame() -> None:
    clock = IdleClock(5)
    starts, was_blinking = [], False
    for frame in range(1, 30 * FPS):
        clock.advance(FRAME)
        if clock.is_blinking and not was_blinking:
            starts.append(frame * FRAME)
        was_blinking = clock.is_blinking
    expected = [start for start, _ in blink_times(5, 30.0)]
    assert len(starts) == len(expected)
    assert all(0 <= s - e < FRAME + 1e-9 for s, e in zip(starts, expected))


def test_breathing_and_sway_start_at_rest_and_stay_small() -> None:
    seed = idle_seed("pip")
    assert breath_scale(0.0, seed) == pytest.approx((1.0, 1.0))
    assert sway_angle(0.0, seed) == pytest.approx(0.0)
    for t in np.linspace(0.0, 20.0, 201):
        sx, sy = breath_scale(float(t), seed)
        assert abs(sx - 1.0) <= BREATH_SCALE[0] + 1e-12 and abs(sy - 1.0) <= BREATH_SCALE[1] + 1e-12
        assert abs(sway_angle(float(t), seed)) <= 2 * SWAY_DEGREES + 1e-12
    assert idle_seed("pip") == idle_seed("pip") != idle_seed("rex")


# ----- the character (manim objects, nothing rendered) ----------------------------------------


def test_config_characters_idle_unless_idle_false() -> None:
    assert pip().is_idle
    assert not pip(idle=False).is_idle
    config = parse_config(minimal_config(characters=[{"name": "pip", "idle": False}]))
    assert config.characters[0].idle is False


def test_idle_motion_is_a_layer_the_poses_never_see() -> None:
    c = pip(idle=False)
    rest_points, rest_state = points(c), c.state()
    c.start_idle(seed=1)
    for _ in range(40):
        c.update(FRAME)
    assert c.state() == rest_state
    assert not np.allclose(points(c), rest_points)
    c.stop_idle()
    assert not c.is_idle and not c.updaters
    assert np.allclose(points(c), rest_points)


def test_blinks_show_closed_eyes_without_changing_the_eyes_pose() -> None:
    c = pip(idle=False).start_idle(seed=2)
    first_start, first_end = blink_times(2, 10.0)[0]
    while c._idle.seconds + FRAME < first_start:
        c.update(FRAME)
        assert c.shown_shape("eyes") == "open"
    c.update(FRAME)
    assert c.shown_shape("eyes") == "closed" and c.pose_of("eyes").shape is None
    c.set_part("eyes", scale=1.2)  # an expression may change the eyes during a blink
    assert c.shown_shape("eyes") == "closed"
    c.end_blink()
    assert c.shown_shape("eyes") == "open" and c.pose_of("eyes").scale == (1.2, 1.2)


def test_a_character_without_closed_eyes_breathes_but_never_blinks() -> None:
    parts = generate_parts(CharacterLook(), {k: "#888888" for k in ("skin", "clothes", "outline", "features", "hair", "accessory")})
    parts = [replace(p, shapes={"open": p.shapes["open"]}) if p.name == "eyes" else p for p in parts]
    c = Character(parts, name="pip").start_idle(seed=2)
    for _ in range(10 * FPS):
        c.update(FRAME)
        assert c.shown_shape("eyes") == "open"


def test_pose_changes_stop_the_clock_and_never_show_a_blink() -> None:
    c = pip(idle=False).start_idle(seed=4)
    changes = [(1.0, 1.8), (2.5, 4.5), (6.0, 6.9)]
    seen_closed: list[float] = []
    animation = None
    for frame in range(1, 12 * FPS):
        t = frame * FRAME
        window = next((w for w in changes if w[0] <= t < w[1]), None)
        if window is not None and animation is None:
            animation = PoseChange(c, pose="waving" if changes.index(window) % 2 == 0 else "stand")
            animation.begin()
        if animation is not None:
            if window is None:
                animation.finish()
                animation = None
            else:
                animation.interpolate((t - window[0]) / (window[1] - window[0]))
                assert c.shown_shape("eyes") == "open", t
        c.update(FRAME)
        if c.shown_shape("eyes") == "closed":
            seen_closed.append(t)
    expected = blink_times(4, 12.0, pose_changes=changes)
    assert seen_closed and all(not (a <= t < b) for t in seen_closed for a, b in changes)
    assert all(any(s - FRAME <= t <= e + FRAME for s, e in expected) for t in seen_closed)


def test_a_pose_change_ends_a_running_blink() -> None:
    c = pip(idle=False).start_idle(seed=2)
    start, _ = blink_times(2, 10.0)[0]
    while c.shown_shape("eyes") != "closed":
        c.update(FRAME)
    assert c._idle.seconds >= start
    PoseChange(c, pose="pointing").begin()
    assert c.shown_shape("eyes") == "open"


def test_idle_and_lip_sync_drive_different_parts_together() -> None:
    track = VisemeTrack((VisemeCue(0.0, 3.0, "rest"), VisemeCue(3.0, 3.5, "O"), VisemeCue(3.5, 8.0, "A")))
    c = pip(idle=False).start_idle(seed=2)
    c.lip_sync(track)
    mouths, eyes = set(), set()
    for _ in range(8 * FPS):
        c.update(FRAME)
        mouths.add(c.shown_shape("mouth"))
        eyes.add(c.shown_shape("eyes"))
    assert mouths == {"smile", "O", "A"} and eyes == {"open", "closed"}
    c.stop_lip_sync()
    assert c.is_idle and c.shown_shape("mouth") == "smile" and c.pose_of("mouth").shape is None


def test_a_copy_idles_on_its_own_clock() -> None:
    c = pip(idle=False).start_idle(seed=2)
    c.update(1.0)
    twin = c.copy()
    twin.update(1.0)
    assert c._idle.seconds == pytest.approx(1.0) and twin._idle.seconds == pytest.approx(2.0)
