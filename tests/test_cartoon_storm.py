"""Step 127: lightning (flash timing, the bolt, thunder after a delay), rainbows and the sun and
moon moving across the sky with the shadows turning (DESIGN.md §69.61)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from test_cartoon_living import frames_of, room_project
from test_cartoon_stage import stage_params
from vidgen import sfx
from vidgen.cartoon.lighting import LightGrade, ShadowEllipse, light_grade
from vidgen.cartoon.room import WindowSky, flash_sky
from vidgen.cartoon.shading import ShadowCaster, StageShadows
from vidgen.cartoon.storm import (
    FLASH_PULSES,
    FLASH_SHARE,
    FLASH_TAIL,
    RAINBOW_COLORS,
    SOUND_KM_PER_SECOND,
    RainStorm,
    Strike,
    bolt_paths,
    flash_grade,
    flash_level,
    flash_strength,
    flashing,
    rainbow_bands,
    rainbow_level,
    RainbowChange,
    storm_strikes,
    strike_pulses,
    thunder_cue,
    thunder_delay,
    thunder_pan,
)
from vidgen.cartoon.sun_path import (
    MAX_SHADOW_STRETCH,
    PATH_HIDDEN,
    PathMove,
    cast_shadow,
    path_blend,
    path_point,
    path_share_at,
    place_for,
    shadow_cast,
    wrap_share,
)
from vidgen.cli import check_project


# ----- lightning (no manim) ------------------------------------------------------------------------------


def test_a_strike_flashes_in_quick_pulses_and_is_over_after_its_tail() -> None:
    strike = Strike(2.0, 0.5, distance=0.5, seed=7)
    full = flash_strength(0.5)
    assert full == 1.0 and flash_strength(5.0) < flash_strength(2.0) < full and flash_strength(50.0) == 0.4
    assert strike.level(1.99) == 0.0 and strike.level(2.0) == strike.level(2.09) == full   # the first pulse, held
    first, *later = strike.pulses
    assert first == FLASH_PULSES[0] and len(later) in (1, 2) and strike.pulses == strike_pulses(7)
    between = later[0][0] - 0.01   # dying away before the second pulse
    assert 0.0 < strike.level(2.0 + between) < full
    assert strike.level(2.0 + later[0][0] + 0.01) == pytest.approx(later[0][2])
    last_start, last_length, _ = strike.pulses[-1]
    assert strike.end == pytest.approx(2.0 + last_start + last_length + FLASH_TAIL)
    assert strike.level(strike.end + 0.01) == 0.0
    counts = {len(strike_pulses(seed)) for seed in range(40)}
    assert counts == {2, 3}   # seeded: two or three pulses
    far = Strike(2.0, 0.5, distance=4.0, seed=7)
    assert far.level(2.05) == pytest.approx(flash_strength(4.0)) and far.level(2.05) < strike.level(2.05)
    assert flash_level([strike, far], 2.05) == full and flash_level([], 2.05) == 0.0
    assert flashing([strike], 1.0, 2.01) and flashing([strike], 2.3, 3.0) and not flashing([strike], 0.0, 2.0) and not flashing([strike], strike.end, 9.0)


def test_a_flash_takes_the_grade_towards_white() -> None:
    night = light_grade("night")
    assert flash_grade(night, 0.0) is night
    lit = flash_grade(night, 1.0)
    f = FLASH_SHARE
    assert lit.multiply == pytest.approx(tuple(m * (1 - f) for m in night.multiply))
    assert lit.stars == pytest.approx(night.stars * (1 - f)) and lit.shadow == pytest.approx(night.shadow * (1 - f))
    rgb = np.array([[0.2, 0.3, 0.4, 1.0]])
    from vidgen.cartoon.lighting import grade_rgbas

    dark, bright = grade_rgbas(rgb, night)[0], grade_rgbas(rgb, lit)[0]
    assert np.all(bright[:3] > dark[:3]) and bright[3] == 1.0
    assert flash_grade(LightGrade(), 0.5).changes_colors   # a day scene flashes too


def test_thunder_comes_later_quieter_longer_and_lower_the_farther_the_strike() -> None:
    assert thunder_delay(1.0) == pytest.approx(1.0 / SOUND_KM_PER_SECOND) == pytest.approx(2.915, abs=0.001)
    assert thunder_delay(0.0) == 0.0
    near, far = thunder_cue(0.3), thunder_cue(3.0)
    assert near.delay < far.delay and near.gain > far.gain and near.duration < far.duration
    assert near.intensity > far.intensity and near.pitch > far.pitch
    assert thunder_cue(100.0).gain == -18.0 and thunder_cue(100.0).duration <= 7.0
    assert Strike(1.0, 0.2, distance=2.0).thunder == thunder_cue(2.0)
    assert thunder_pan(0.5) == 0.0 and thunder_pan(0.0) == -0.8 and thunder_pan(1.0) == 0.8 and thunder_pan(0.75) == pytest.approx(0.4)
    lo, hi = sfx.BUILTIN_SOUNDS["thunder"].duration_range
    assert lo <= near.duration and far.duration <= hi


def test_the_thunder_sound_is_generated_the_same_every_time() -> None:
    samples = sfx.synthesize("thunder", duration=2.0, intensity=0.8)
    assert len(samples) == round(2.0 * sfx.RATE) and np.all(np.isfinite(samples)) and samples[0] == samples[-1] == 0.0
    assert np.array_equal(samples, sfx.synthesize("thunder", duration=2.0, intensity=0.8))
    crack = float(np.abs(samples[: sfx.RATE // 20]).max())
    soft = float(np.abs(sfx.synthesize("thunder", duration=2.0, intensity=0.2)[: sfx.RATE // 20]).max())
    assert crack > soft   # a near strike cracks


def test_a_rain_storm_strikes_at_seeded_times_until_the_rain_stops() -> None:
    strikes = storm_strikes(1.0, 60.0, every=8.0, seed=3)
    times = [s.time for s in strikes]
    assert times == sorted(times) and 1.0 + 8.0 * 0.3 <= times[0] <= 1.0 + 8.0
    assert all(4.0 - 1e-9 <= b - a <= 12.0 + 1e-9 for a, b in zip(times, times[1:]))
    assert strikes[:3] == storm_strikes(1.0, times[2] + 0.01, every=8.0, seed=3)   # a prefix, whatever the end
    assert storm_strikes(1.0, 60.0, every=8.0, seed=4) != strikes
    assert all(0.12 <= s.x <= 0.88 and 0.6 <= s.distance <= 4.0 for s in strikes) and {s.bolt for s in strikes} == {True, False}
    assert storm_strikes(1.0, 60.0, every=8.0, seed=3, stop=times[1]) == strikes[:1]
    stopped: list[float | None] = [None]
    storm = RainStorm(1.0, 8.0, 3, lambda: stopped[0])
    assert storm.strikes(60.0) == strikes and not storm.over(100.0)   # still raining: more to come
    stopped[0] = times[1]
    assert storm.strikes(60.0) == strikes[:1] and not storm.over(strikes[0].time) and storm.over(strikes[0].end)


def test_a_bolt_zigzags_down_to_where_it_strikes_and_forks() -> None:
    paths = bolt_paths(5, 2.0, 4.0, -1.0, 0.8)
    main, *branches = paths
    assert main[0][1] == 4.0 and tuple(main[-1]) == (2.0, -1.0) and np.all(np.diff(main[:, 1]) < 0)
    assert np.all(np.abs(main[:, 0] - 2.0) <= 0.8) and 1 <= len(branches) <= 3
    assert all(any(np.allclose(b[0], p) for p in main) and np.all(np.diff(b[:, 1]) < 0) for b in branches)
    assert all(np.array_equal(a, b) for a, b in zip(paths, bolt_paths(5, 2.0, 4.0, -1.0, 0.8)))


# ----- rainbows (no manim) ---------------------------------------------------------------------------------


def test_a_rainbow_fades_in_and_out() -> None:
    changes = [RainbowChange(2.0, 3.0, 1.0)]
    assert rainbow_level(changes, 1.0) == 0.0 and rainbow_level(changes, 3.5) == pytest.approx(0.5) and rainbow_level(changes, 6.0) == 1.0
    changes.append(RainbowChange(8.0, 2.0, 0.0))
    assert rainbow_level(changes, 7.0) == 1.0 and 0.0 < rainbow_level(changes, 9.0) < 1.0 and rainbow_level(changes, 11.0) == 0.0
    bands = rainbow_bands(1.0, -2.0, 4.0)
    assert len(bands) == len(RAINBOW_COLORS)
    radii = [np.hypot(b[:, 0] - 1.0, b[:, 1] + 2.0) for b in bands]
    assert radii[0].max() == pytest.approx(4.0) and all(r.min() > 0 for r in radii)
    assert all(b[:, 1].min() == pytest.approx(-2.0) for b in bands)   # standing on the horizon
    assert all(r_out.min() == pytest.approx(r_in.max()) for r_out, r_in in zip(radii, radii[1:]))   # bands touch, outside in


# ----- the sun's path and the shadows (no manim) --------------------------------------------------------


def test_the_sun_and_moon_go_round_the_sky() -> None:
    x, height, shown = path_point(0.5)
    assert (x, height, shown) == pytest.approx((0.5, 1.0, 1.0))
    left, right = path_point(0.0), path_point(1.0)
    assert left[0] < 0.5 < right[0] and left[1] == pytest.approx(0.0) and left[2] == 0.0 and right[2] == pytest.approx(0.0)
    assert path_point(-PATH_HIDDEN)[1] < 0 and path_point(1.0 + PATH_HIDDEN / 2)[2] == 0.0
    assert 0.0 < path_point(0.02)[2] < 1.0   # rising: fading in
    assert place_for("sun", "morning") < place_for("sun", "day") == 0.5 < place_for("sun", "sunset") < 1.0 < place_for("sun", "night")
    assert place_for("moon", "night") == 0.5 and place_for("moon", "day") < 0
    assert wrap_share(1.0 + PATH_HIDDEN) == pytest.approx(-PATH_HIDDEN) and wrap_share(0.3) == 0.3
    assert path_blend(0.5, 0.9, 0.5) == pytest.approx(0.7)
    # from set (night) on to morning: forward round the hidden part, never back across the sky
    night, morning = place_for("sun", "night"), place_for("sun", "morning")
    steps = [path_blend(night, morning, s / 10) for s in range(11)]
    assert all(path_point(s)[2] == 0.0 for s in steps[:3]) and steps[-1] == pytest.approx(morning)
    assert all(wrap_share(b - a) < 0.5 for a, b in zip(steps, steps[1:]))


def test_a_sun_move_eases_with_the_light() -> None:
    moves = [PathMove(2.0, 4.0, place_for("sun", "sunset"))]
    assert path_share_at(0.5, moves, 1.0) == 0.5 and path_share_at(0.5, moves, 4.0) == pytest.approx(0.5 + 0.4 / 2)
    assert path_share_at(0.5, moves, 9.0) == pytest.approx(place_for("sun", "sunset"))
    later = [*moves, PathMove(10.0, 2.0, place_for("sun", "night"))]
    assert path_share_at(0.5, later, 13.0) == pytest.approx(wrap_share(place_for("sun", "night")))
    assert path_point(path_share_at(0.5, later, 13.0))[2] == 0.0   # set


def test_shadows_point_away_from_a_low_sun_and_shorten_at_noon() -> None:
    assert shadow_cast(None) == (0.0, 0.0)
    noon_stretch, noon_side = shadow_cast(0.5)
    assert noon_side == 0.0 and noon_stretch == pytest.approx(1 / math.tan(math.radians(65.0)))
    morning, evening = shadow_cast(place_for("sun", "morning")), shadow_cast(place_for("sun", "sunset"))
    assert morning[1] == 1.0 and evening[1] == -1.0   # away from the sun: east in the morning, west at sunset
    assert morning[0] > noon_stretch and evening[0] > noon_stretch and shadow_cast(0.3)[0] < evening[0]
    assert shadow_cast(1.05)[0] == MAX_SHADOW_STRETCH
    ellipse = ShadowEllipse(1.0, -2.0, 0.8, 0.13, 0.3)
    assert cast_shadow(ellipse, 0.0, 1.0) is ellipse and cast_shadow(ellipse, 2.0, 0.0) is ellipse
    east, west = cast_shadow(ellipse, 2.0, 1.0), cast_shadow(ellipse, 2.0, -1.0)
    assert east.width == west.width > ellipse.width and east.x > ellipse.x > west.x
    assert east.x - east.width / 2 == pytest.approx(ellipse.x - ellipse.width / 2)   # its foot stays under the caster
    assert east.opacity < ellipse.opacity and east.y == ellipse.y and east.height == ellipse.height


def test_stage_shadows_turn_with_the_cast() -> None:
    class Thing:
        def __init__(self) -> None:
            self.standing_height = 1.0

        def feet(self) -> np.ndarray:
            return np.array([0.5, -2.0, 0.0])

    shadows = StageShadows([ShadowCaster(Thing(), -2.0, 0.6, 1.0)])
    before = [m.points.copy() for m in shadows.submobjects[0].submobjects]
    shadows.set_cast(0.0, 0.0)
    assert all(np.array_equal(a, m.points) for a, m in zip(before, shadows.submobjects[0].submobjects))
    shadows.set_cast(2.0, -1.0)
    ring = shadows.submobjects[0].submobjects[0]
    assert ring.get_left()[0] < before[0][:, 0].min() and ring.get_right()[0] == pytest.approx(before[0][:, 0].max(), abs=1e-6)


def test_the_windows_flash_white() -> None:
    sky = WindowSky("#203050", "#405070", 1.0)
    assert flash_sky(sky, 0.0) is sky
    lit = flash_sky(sky, 1.0)
    assert lit.top != sky.top and lit.stars < sky.stars


# ----- validation -------------------------------------------------------------------------------------------


def test_storm_options_validate(make_project) -> None:
    assert stage_params(particles=[{"kind": "rain", "lightning": True}]).particles[0].lightning is True
    assert stage_params(particles=[{"kind": "rain", "lightning": 5}]).particles[0].lightning == 5
    with pytest.raises(ValidationError, match="lightning flashes in rain only, not snow"):
        stage_params(particles=[{"kind": "snow", "lightning": True}])
    with pytest.raises(ValidationError):
        stage_params(particles=[{"kind": "rain", "lightning": 1.5}])   # at least 2 s apart
    outdoors = {"props": ["sun", "moon", "tree"], "characters": ["pip"]}
    good = [
        {"text": "A storm comes.", "actions": [{"lightning": "left", "distance": 2}, {"lightning": 0.8, "at": 0.5, "bolt": False}]},
        {"text": "It passes.", "actions": [{"rainbow": "centre", "width": 0.6}, {"light": "sunset", "move_sun": True}]},
        {"text": "And the rainbow goes.", "actions": [{"rainbow": None, "hide": True}, {"particles": "rain", "lightning": 4}]},
    ]
    assert check_project(room_project(make_project, outdoors, good)) == []
    bad = [{"text": "Hm.", "actions": [
        {"lightning": "behind"}, {"lightning": 1.5}, {"rainbow": "left", "hide": True}, {"light": "night", "tint": "#223344", "move_sun": True},
        {"particles": "snow", "lightning": True},
    ]}]
    problems = check_project(room_project(make_project, outdoors, bad))
    assert any("unknown mark 'behind'" in p for p in problems), problems
    assert any("outside the frame" in p for p in problems), problems
    assert any("hide: true fades the rainbows out; it takes no place" in p for p in problems), problems
    assert any("give a preset (- light: sunset), not a tint" in p for p in problems), problems
    assert any("lightning flashes in rain only, not snow" in p for p in problems), problems
    sunless = check_project(room_project(make_project, {"props": ["tree"]}, [{"text": "Dusk.", "actions": [{"light": "sunset", "move_sun": True}]}]))
    assert any("add a sun or a moon prop" in p for p in sunless), sunless
    room = {"room": {"windows": [0.3]}, "characters": ["pip"]}
    inside = [{"text": "Flash.", "actions": [{"lightning": "centre"}, {"rainbow": "centre"}]}]
    problems = check_project(room_project(make_project, room, inside))
    assert problems and all("rainbow" in p for p in problems), problems   # lightning works in a room: the windows flash
    other = [{"id": "card", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Hi.", "actions": [{"lightning": "left"}]}]}]
    from conftest import minimal_config
    from vidgen.project import Project

    problems = check_project(Project.load(make_project(minimal_config(scenes=other), folder="card")))
    assert any("lightning is for stage scenes" in p for p in problems), problems


# ----- renders ---------------------------------------------------------------------------------------------


def drawn_before_the_outro(monkeypatch) -> list[Any]:
    """A list that gets the stage's draw order when its outro starts (the scene ends empty)."""
    from vidgen.scenes.stage import Stage

    drawn: list[Any] = []
    finish = Stage.finish

    def keeping(self: Any) -> None:
        drawn[:] = list(self.mobjects)
        finish(self)

    monkeypatch.setattr(Stage, "finish", keeping)
    return drawn


STORM: dict[str, Any] = {
    "idle": False,
    "background": ["#5F6F86", "#9AA6B4"],
    "props": [{"prop": "house", "at": 0.2, "depth": 0.5}, {"prop": "tree", "at": 0.85, "depth": 0.3}],
    "characters": [{"name": "pip", "at": 0.5}],
}


@pytest.mark.render
def test_lightning_flashes_the_set_with_a_bolt_then_a_rainbow_fades_in(make_project, tmp_path: Path, monkeypatch) -> None:
    """The same scene without the lightning and the rainbow gives the same pixels until the strike;
    the strike's frames are brighter, with the bolt where it struck; its thunder comes after the
    delay; the rainbow then shows in the sky, behind the house."""
    beats = [
        {"text": "Pip looks at the sky."},
        {"text": "Lightning strikes far off.", "actions": [{"lightning": "right", "distance": 1.0, "seed": 4}]},
        {"text": "Then a rainbow comes out.", "actions": [{"rainbow": "centre", "run_time": 0.6}]},
    ]
    plain = [{"text": b["text"]} for b in beats]
    shown = drawn_before_the_outro(monkeypatch)
    scene, frames = frames_of(room_project(make_project, STORM, beats), tmp_path / "storm", monkeypatch)
    drawn = list(shown)   # before the plain render overwrites it
    _, still = frames_of(room_project(make_project, STORM, plain, title="Plain"), tmp_path / "plain", monkeypatch)
    strike = scene.light.strikes[0]
    first = math.ceil(strike.time * 5 - 1e-9)   # the first frame at or after it (5 fps)
    assert len(frames) == len(still) and first > 3
    assert all(np.array_equal(a, b) for a, b in zip(frames[:first], still[:first]))
    assert frames[first].mean() > still[first].mean() + 20   # the whole set flashes
    assert strike.x == 0.75 and strike.bolt and scene.bolt is not None
    paths = scene._bolt_paths[strike.seed]
    assert paths[0][-1][0] == pytest.approx((0.75 - 0.5) * scene.stage_width)
    thunder = [e for e in scene.sfx_log if e.sound == "thunder"]
    assert len(thunder) == 1 and thunder[0].time == pytest.approx(strike.time + thunder_delay(1.0), abs=1e-5)
    assert thunder[0].pan == pytest.approx(thunder_pan(0.75)) and thunder[0].params["duration"] == pytest.approx(thunder_cue(1.0).duration)
    after = math.ceil(strike.end * 5)
    rainbow = scene.rainbows[0].rainbow
    assert scene.rainbows[0].level == 1.0 and rainbow.box[1] == pytest.approx(scene._horizon_y())
    last = len(frames) - round(scene.outro * 5) - 1   # the last frame before the fade out
    sky = frames[last][5:30].astype(int) - still[last][5:30].astype(int)
    assert np.abs(sky).max() > 30   # the rainbow in the sky
    assert all(np.array_equal(a, b) for a, b in zip(frames[after:after + 2], still[after:after + 2]))   # the flash is over
    order = [m for m in drawn if m is rainbow or m is scene.props["house"]]
    assert order == [rainbow, scene.props["house"]]   # behind the house


@pytest.mark.render
def test_the_sun_sets_across_the_sky_and_the_shadows_turn(make_project, tmp_path: Path, monkeypatch) -> None:
    """A light change with move_sun takes the sun from the top of the sky down to the right while
    the light fades; pip's shadow stretches out to the left, away from it."""
    params = {**STORM, "props": [*STORM["props"], "sun", "moon"], "background": "#9CC4E8"}
    beats = [{"text": "The day goes on and the sun sinks low.", "actions": [{"light": "sunset", "move_sun": True, "run_time": 2.0}]}]
    positions: list[tuple[float, float]] = []
    from vidgen.scenes.stage import Stage

    step = Stage._sky_step

    def recording(self: Any, now: float) -> None:
        step(self, now)
        sun = next(b for b in self.sky_bodies if b.kind == "sun")
        positions.append((float(sun.prop.get_center()[0]), float(sun.prop.get_center()[1])))

    monkeypatch.setattr(Stage, "_sky_step", recording)
    drawn = drawn_before_the_outro(monkeypatch)
    scene, _ = frames_of(room_project(make_project, params, beats), tmp_path / "dusk", monkeypatch)
    sun, moon = (next(b for b in scene.sky_bodies if b.kind == kind) for kind in ("sun", "moon"))
    assert sun.share == pytest.approx(place_for("sun", "sunset")) and moon.share == pytest.approx(place_for("moon", "sunset"))
    xs = [x for x, _ in positions]
    assert xs[0] == pytest.approx(0.0, abs=1e-6) and xs == sorted(xs) and xs[-1] > 0.25 * scene.stage_width   # left to right
    assert positions[-1][1] < positions[0][1]   # lower
    assert drawn.index(sun.prop) < drawn.index(scene.props["house"])   # in the sky, behind the house
    group = next(g for g in scene.shadows if any(c.mobject is scene.cast["pip"] for c in g.casters))
    assert group.cast[1] == -1.0 and group.cast[0] > 1.0
    caster = next(c for c in group.casters if c.mobject is scene.cast["pip"])
    plain = caster.ellipse(group.strength)
    shadow = group.submobjects[group.casters.index(caster)].submobjects[0]
    assert shadow.get_left()[0] < plain.x - plain.width / 2 - 0.1   # stretched out to the left
