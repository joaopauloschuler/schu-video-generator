"""Step 105: rain on a stage's ground (drop floors in a depth band, shelter boxes, seeded splashes
and puddles) and the generated rain sound bed (mixed like music, ducked less)."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from test_particles import fake_scene
from vidgen import mix, sfx
from vidgen.ambience import RAIN_DUCK, RAIN_FADE_IN, RAIN_LEVEL, ambience_spans, merge_spans, rain_loop
from vidgen.cartoon.rain import (
    LANDING_FRONT,
    SHELTER_REACH,
    SPLASH_DROPLET,
    SPLASH_JUMP,
    SPLASH_SECONDS,
    ShelterBox,
    drop_floors,
    drop_landings,
    landing_lines,
    landing_shares,
    prop_shelter,
    puddle_count,
    puddle_growth,
    puddle_spots,
    rain_ground,
    splash_shapes,
)
from vidgen.cartoon.stage import FAR_RISE
from vidgen.cli import check_project
from vidgen.introspect import LayoutRecorder
from vidgen.loudness import integrated_loudness
from vidgen.particle_field import ParticleField, ParticleSettings, Puddles, particle_field
from vidgen.project import Project

RATE = sfx.RATE
FRAME_HEIGHT = 9.0
# ground line 0.2 of the frame up (y -2.7), the ground area up to 0.26 (y -2.16)
GROUND = rain_ground(0.2, 0.26, FRAME_HEIGHT)


# ----- the ground band and shelters (no manim) ------------------------------------------------------------


def test_drops_land_in_the_depth_band() -> None:
    assert (GROUND.ground, GROUND.front, GROUND.back) == pytest.approx((-2.7, -2.7 - LANDING_FRONT * 9, -2.16))
    shares, spread = landing_shares(500, seed=3)
    again, _ = landing_shares(500, seed=3)
    assert np.array_equal(shares, again) and not np.array_equal(shares, landing_shares(500, seed=4)[0])
    assert spread.min() >= 0 and spread.max() <= 1
    lines = landing_lines(shares, GROUND)
    assert lines.min() >= GROUND.front and lines.max() <= GROUND.back
    assert GROUND.depth(np.array([GROUND.back]))[0] == pytest.approx(0.06 / FAR_RISE)   # the deepest thing's depth: 0.5
    flat = rain_ground(0.2, 0.2, FRAME_HEIGHT)   # nothing deep: a strip in front of the ground line
    assert flat.back == flat.ground and flat.front < flat.ground
    assert rain_ground(0.02, 0.02, FRAME_HEIGHT).front == -4.5   # never below the frame's bottom edge


def test_shelters_stop_drops_at_their_top_edge() -> None:
    umbrella = ShelterBox(left=-1.0, right=1.0, top=0.5, feet=GROUND.ground)
    tree = ShelterBox(left=0.5, right=3.0, top=2.0, feet=GROUND.ground + 0.3)
    ground = rain_ground(0.2, 0.26, FRAME_HEIGHT, [umbrella, tree])
    x = np.array([0.0, 0.0, 2.0, 2.0, 0.8, 5.0])
    landing = np.array([-2.7, -3.7, -2.6, -3.5, -2.5, -2.6])
    floors = drop_floors(x, landing, ground)
    reach = SHELTER_REACH * FRAME_HEIGHT
    assert -3.7 < umbrella.feet - reach and -3.5 < tree.feet - reach   # the second and fourth land in front
    assert floors.tolist() == pytest.approx([0.5, -3.7, 2.0, -3.5, 2.0, -2.6])
    # over the umbrella; in front of it; under the tree; in front of the tree; both: the higher; neither


def test_which_props_shelter() -> None:
    box = (-1.0, 1.0, 2.0)
    assert prop_shelter("tree", None, box, -2.7) == ShelterBox(-1.0, 1.0, 2.0, -2.7)
    assert prop_shelter("umbrella", "open", box, -2.5) == ShelterBox(-1.0, 1.0, 2.0, -2.5)
    assert prop_shelter("umbrella", "closed", box, -2.7) is None
    assert prop_shelter("table", None, box, -2.7) is None and prop_shelter("svg", None, box, -2.7) is None


def test_drops_vanish_at_their_floor_and_splash_for_a_moment() -> None:
    tip = np.array([1.0, -0.1, -1.0, -5.0])
    floor = np.zeros(4)
    landed = drop_landings(tip, floor, np.full(4, 10.0), slant=0.2)
    assert landed.falling.tolist() == [True, False, False, False]
    assert landed.splashing.tolist() == [False, True, True, False]   # 0.01 s, 0.1 s ago; 0.5 s ago is over
    assert landed.age.tolist() == pytest.approx([0.0, 0.01, 0.1, 0.0])
    assert landed.back.tolist() == pytest.approx([0.0, 0.02, 0.2, 1.0])   # moved right along the slant since


def test_splash_shapes_are_seeded_and_end_at_nothing() -> None:
    spread = np.array([0.0, 1.0])
    start, middle, end = (splash_shapes(np.full(2, a), spread, np.ones(2)) for a in (0.0, SPLASH_SECONDS / 2, SPLASH_SECONDS))
    assert start.shape == (2, 3, 4)
    assert start[0, 1].tolist() == pytest.approx([0.0, SPLASH_DROPLET, SPLASH_DROPLET, SPLASH_DROPLET])   # droplets start at the drop
    assert middle[0, 1, 1] == pytest.approx(SPLASH_JUMP + SPLASH_DROPLET / 2)   # highest half-way
    assert middle[0, 1, 0] == pytest.approx(-middle[0, 2, 0]) and middle[0, 1, 0] < 0   # left and right
    assert abs(middle[1, 1, 0]) > abs(middle[0, 1, 0])   # a larger spread throws them further
    assert np.allclose(end[:, :, 3], 0.0)   # flat: gone
    assert np.allclose(splash_shapes(np.full(2, 0.1), spread, np.full(2, 0.5)), splash_shapes(np.full(2, 0.1), spread, np.ones(2)) / 2)


def test_puddles_are_seeded_never_under_a_shelter_and_grow() -> None:
    umbrella = ShelterBox(left=-1.0, right=1.0, top=0.5, feet=GROUND.ground)
    ground = rain_ground(0.2, 0.26, FRAME_HEIGHT, [umbrella])
    spots = puddle_spots(12, 7, -8.0, 8.0, ground, 9.0)
    assert spots == puddle_spots(12, 7, -8.0, 8.0, ground, 9.0) != puddle_spots(12, 8, -8.0, 8.0, ground, 9.0)
    assert len(spots) == 12
    for x, y, half in spots:
        assert -8.0 <= x <= 8.0 and ground.front <= y <= ground.back and 0 < half < 1.0
        assert not (x + half >= -1.0 and x - half <= 1.0)   # clear of the umbrella's box
    assert puddle_count(1.0) == 4 and puddle_count(2.5) == 10
    assert puddle_growth(0.0) == 0.0 and puddle_growth(1e6) == 1.0
    sizes = [puddle_growth(t) for t in np.linspace(0, 12, 25)]
    assert sizes == sorted(sizes)


# ----- the field (manim objects, no render) -----------------------------------------------------------------


def test_rain_field_hides_landed_drops_and_draws_their_splashes() -> None:
    scene = fake_scene(time=0.0)
    shelter = ShelterBox(left=-2.0, right=2.0, top=1.0, feet=GROUND.ground)
    scene.rain_ground = lambda: rain_ground(0.2, 0.26, FRAME_HEIGHT, [shelter])
    field = particle_field(scene, "rain", ParticleSettings(seed=2))
    snow = particle_field(scene, "snow", ParticleSettings())
    assert snow.splashes is None and len(snow) == len(snow.drops)   # only rain ends on a ground
    assert field.splashes is not None and len(field) == len(field.drops) + 1
    for now in np.linspace(1.0, 3.0, 9):
        scene.renderer.time = float(now)
        field.update(0.1)
        for drop in field.drops:
            x, bottom = drop.get_bottom()[:2]
            if drop.get_fill_opacity() > 0 and abs(abs(x) - 2.0) > 0.2:
                floor = 1.0 if abs(x) < 2.0 else GROUND.front
                assert bottom > floor - 0.05, (now, x, bottom)   # nothing falls through the shelter or the ground
        points = field.splashes.points
        if len(points):
            ys = points[:, 1]
            assert ys.min() >= GROUND.front - 0.1   # splashes on the ground or the shelter
    assert len(field.splashes.points) > 0


def test_puddles_grow_with_the_rain_and_stay() -> None:
    clock = SimpleNamespace(now=0.0)
    field = SimpleNamespace(start=0.0, ended=None)
    puddles = Puddles([(0.0, -2.7, 0.5), (3.0, -2.5, 0.4)], start=0.0, ended=lambda: field.ended, clock=lambda: clock.now)
    assert puddles.copy() is not puddles   # Manim copies what it fades in
    assert puddles[0].width == pytest.approx(0.0, abs=1e-9)
    clock.now = 5.0
    puddles.update(0.1)
    assert puddles[0].width == pytest.approx(puddle_growth(5.0), rel=1e-3) and puddles[0].get_center()[0] == pytest.approx(0.0)
    field.ended = 6.0
    clock.now = 20.0
    puddles.update(0.1)
    assert puddles[0].width == pytest.approx(puddle_growth(6.0), rel=1e-3) and not puddles.updaters   # stays, stops updating


# ----- validation -------------------------------------------------------------------------------------------


def test_puddles_are_for_rain(make_project) -> None:
    assert stage_params(particles=[{"kind": "rain", "puddles": True}]).particles[0].puddles
    with pytest.raises(Exception, match="puddles grow under rain only"):
        stage_params(particles=[{"kind": "snow", "puddles": True}])
    scenes = [{"id": "card", "type": "text_card", "params": {"text": "Hi"},
               "beats": [{"text": "Snow.", "actions": [{"particles": "snow", "puddles": True}]}]}]
    problems = check_project(Project.load(make_project(minimal_config(scenes=scenes))))
    assert len(problems) == 1 and "puddles grow under rain only" in problems[0]


# ----- the rain sound bed (no render) ------------------------------------------------------------------------


def test_spans_join_across_scenes() -> None:
    assert merge_spans([(5.0, 7.0), (0.0, 2.0), (2.1, 3.0), (6.0, 8.0), (9.0, 9.0)]) == [(0.0, 3.0), (5.0, 8.0)]
    timings = {"scenes": [{"ambience": [{"bed": "rain", "start": 1.0, "end": 4.0}]}, {}, {"ambience": [{"bed": "rain", "start": 4.05, "end": 6.0}]}]}
    assert ambience_spans(timings, "rain") == [(1.0, 6.0)]


def test_rain_loop_is_seamless_wide_and_at_its_level() -> None:
    loop = rain_loop()
    assert loop.shape == (int(8 * RATE), 2) and loop.dtype == np.float32 and not loop.flags.writeable
    assert integrated_loudness(loop) == pytest.approx(RAIN_LEVEL, abs=0.1)
    steps = np.abs(np.diff(loop, axis=0))
    assert (np.abs(loop[0] - loop[-1]) <= np.quantile(steps, 0.99, axis=0)).all()   # no click where it repeats
    assert abs(np.corrcoef(loop[:, 0], loop[:, 1])[0, 1]) < 0.2   # the channels differ: wide
    assert sfx.peak_db(loop) < -6.0


def rain_timings() -> dict[str, Any]:
    return {"scenes": [{"beats": [{"id": "nothing_here", "start": 3.0, "end": 4.0}], "ambience": [{"bed": "rain", "start": 1.0, "end": 9.0}]}]}


def test_the_bed_fades_with_the_rain_and_ducks_less_than_music(make_project) -> None:
    project = Project.load(make_project(minimal_config()))
    [bed] = mix.plan_ambience(project, rain_timings(), 10 * RATE)
    assert (bed.bed, bed.start, bed.end, bed.duck) == ("rain", RATE, 9 * RATE, RAIN_DUCK.depth)
    gain = 20 * np.log10(np.maximum(bed.gain, 1e-12))

    def at(seconds: float) -> float:
        return float(gain[round(seconds * 100)])

    assert at(0.5) < -100 and at(9.5) < -100   # silent before and after the rain
    assert at(1.0 + RAIN_FADE_IN / 2) == pytest.approx(20 * math.log10(0.5), abs=0.5)   # half-way through its fade in
    assert at(3.5) == pytest.approx(-RAIN_DUCK.depth, abs=0.01) and RAIN_DUCK.depth < mix.DuckConfig().depth   # under speech
    assert at(6.0) == pytest.approx(0.0, abs=0.01)
    assert mix.plan_ambience(project, {"scenes": [{"beats": []}]}, 10 * RATE) == []


def test_the_mix_carries_the_bed(make_project, tmp_path: Path) -> None:
    project = Project.load(make_project(minimal_config()))
    voice = tmp_path / "voice.wav"
    sfx.write_wav(voice, np.zeros((10 * RATE, 2), dtype=np.float32))
    report = mix.mix_audio(project, rain_timings(), [voice], None, tmp_path / "mix.wav")
    assert report.mixed and not report.normalized and (tmp_path / "mix.wav").is_file()
    assert report.to_json()["ambience"] == [{"bed": "rain", "start": 1.0, "end": 9.0, "duck": RAIN_DUCK.depth}]
    assert RAIN_LEVEL - 3.0 < report.integrated_lufs < RAIN_LEVEL + 0.5   # the bed alone, partly ducked
    assert "ambience" not in mix.MixReport(False, False, None, None, 0.0, -30.0, -10.0, 0.0).to_json()


# ----- a stage (tiny renders) ---------------------------------------------------------------------------------


class OrderRecorder(LayoutRecorder):
    """The layout dump, and the scene's mobjects in draw order at each still."""

    def __init__(self) -> None:
        super().__init__()
        self.orders: list[list[Any]] = []

    def __call__(self, scene: Any, captured: Any) -> None:
        super().__call__(scene, captured)
        self.orders.append(list(scene.mobjects))


def drawn_between(order: list[Any], back: Any, mobject: Any, front: Any) -> bool:
    """Whether ``mobject`` is drawn after ``back`` and before ``front`` in ``order``."""
    ids = [id(m) for m in order]
    return id(mobject) in ids and ids.index(id(back)) < ids.index(id(mobject)) < ids.index(id(front))


def rain_stage(make_project, params: dict[str, Any], beats: list[dict[str, Any]] | None = None) -> Project:
    params = {"idle": False, "characters": ["pip"], "props": [{"prop": "umbrella", "open": True, "at": "left"}, {"prop": "tree", "at": "right"}], **params}
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": beats or [{"text": "It rains on the park."}]}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


@pytest.mark.render
def test_a_rainy_stage_shelters_grows_puddles_and_plays_the_bed(make_project, tmp_path: Path) -> None:
    project = rain_stage(make_project, {"particles": [{"kind": "rain", "puddles": True}]})
    recorder = OrderRecorder()
    scene, objects = render_with_layout(project, "park", tmp_path / "media", recorder)
    assert [(b.top > -2.0) for b in scene.rain_ground().shelters] == [True, True]   # the open umbrella and the tree
    [field] = scene.particles
    assert isinstance(field, ParticleField) and field.splashes is not None
    [puddles] = scene.puddles
    band = next(m for m in scene._backdrop if getattr(m, "name", None) == "ground")
    assert drawn_between(recorder.orders[-1], band, puddles, scene.cast["pip"])   # on the ground, under the characters
    assert puddles[0].width > 0 and not any(obj["class"] == "Puddles" for obj in objects)
    assert scene.timings()["ambience"] == [{"bed": "rain", "start": 0.0, "end": round(float(scene.renderer.time), 6)}]

    quiet = rain_stage(make_project, {"particles": ["rain"], "foley": False})
    scene, _ = render_with_layout(quiet, "park", tmp_path / "media2")
    assert "ambience" not in scene.timings() and scene.puddles == []


@pytest.mark.render
def test_a_rain_action_plays_the_bed_while_it_lasts(make_project, tmp_path: Path) -> None:
    beats = [{"text": "Then it starts to rain.", "actions": [{"particles": "rain", "at": 0.3, "puddles": True}]}, {"text": "And it stops."}]
    recorder = OrderRecorder()
    scene, _ = render_with_layout(rain_stage(make_project, {}, beats), "park", tmp_path / "media", recorder)
    [bed] = [b for b in scene.timings()["ambience"] if b["bed"] == "rain"]   # birdsong around it since Step 128
    second = scene.beat_log[1].start
    assert 0.0 < bed["start"] < second < bed["end"] <= second + 1.0   # from the action to the end of its fade out
    [puddles] = scene.puddles
    band = next(m for m in scene._backdrop if getattr(m, "name", None) == "ground")
    assert drawn_between(recorder.orders[-1], band, puddles, scene.cast["pip"])   # stays after the rain, under pip
    assert not puddles.updaters and puddles[0].width > 0
