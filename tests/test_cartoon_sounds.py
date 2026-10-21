"""Step 128: more sounds (DESIGN.md §69.62): the generated ``creak``, ``knock`` and ``splash``, the
set beds ``birdsong``, ``city`` and ``room_tone``, the rules that choose them (pure), the door,
water and wet-step foley, and the ``knock`` action. Two tiny renders: a room with doors (knock,
creaks, a shut, its room tone) and a day turning to night outdoors (birdsong until then)."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import room_project
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen import ambience, extensions, mix, registry, sfx
from vidgen.ambience import (
    BIRDS_AFTER_RAIN,
    BIRDSONG_DUCK,
    BIRDSONG_LEVEL,
    CITY_LEVEL,
    MIN_BIRDSONG_SECONDS,
    ROOM_TONE_LEVEL,
    SET_BEDS,
    SET_FADE_IN,
    set_ambience,
)
from vidgen.cartoon.foley import (
    BOAT_SPLASH,
    DOOR_OPEN_CREAK,
    POUR_FALL_SECONDS,
    WET_STEP,
    FoleyCue,
    PlayedAction,
    foley_cues,
    wet_steps,
)
from vidgen.cartoon.holding import RESHAPE_SHARE
from vidgen.cartoon.small_props import pour_flow
from vidgen.cli import check_project
from vidgen.loudness import integrated_loudness
from vidgen.project import Project

RATE = sfx.RATE
NEW_SOUNDS = ("creak", "knock", "splash")


# ----- the sounds (no render) ------------------------------------------------------------------------


def band_share(x: np.ndarray, low: float, high: float) -> float:
    """The share of ``x``'s energy between ``low`` and ``high`` Hz."""
    power = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    return float(power[(freqs >= low) & (freqs <= high)].sum() / power.sum())


def test_each_new_sound_generates_deterministically() -> None:
    for name in NEW_SOUNDS:
        assert name in sfx.BUILTIN_SOUNDS
        default = sfx.synthesize(name).copy()
        shaped = sfx.synthesize(name, duration=1.2, pitch=3.0, intensity=0.8).copy()
        sfx._builtin.cache_clear()
        assert np.array_equal(sfx.synthesize(name), default), name
        assert np.array_equal(sfx.synthesize(name, duration=1.2, pitch=3.0, intensity=0.8), shaped), name
        assert len(shaped) == round(1.2 * RATE) and not np.array_equal(shaped[: len(default)], default)


def test_a_knock_is_three_raps_and_a_creak_and_a_splash_sound_as_described() -> None:
    knock = sfx.synthesize("knock")
    window = int(0.02 * RATE)
    envelope = np.convolve(np.abs(knock), np.ones(window) / window, mode="same")
    loud = np.concatenate([[False], envelope > 0.4 * envelope.max()])
    rises = np.nonzero(loud[1:] & ~loud[:-1])[0] / RATE
    onsets = [t for k, t in enumerate(rises) if k == 0 or t - rises[k - 1] > 0.1]
    assert len(onsets) == 3 and np.diff(onsets) == pytest.approx([0.19, 0.19], abs=0.02)
    assert band_share(knock, 100, 600) > 0.5   # a dull wooden thump
    assert band_share(sfx.synthesize("creak"), 300, 3500) > 0.8   # a squeak in the wood's bands
    soft, hard = sfx.synthesize("splash", intensity=0.0), sfx.synthesize("splash", intensity=1.0)
    first = int(0.1 * RATE)
    burst = lambda x: float((x[:first] ** 2).sum() / (x**2).sum())   # noqa: E731
    assert burst(hard) > burst(soft) + 0.1   # at low intensity mostly droplets
    assert band_share(hard, 1000, 6000) > 0.4 and band_share(hard, 150, 700) > 0.05   # bright, with a low plunk


@pytest.mark.parametrize(
    ("bed", "level", "seconds"),
    [("birdsong", BIRDSONG_LEVEL, 20.0), ("city", CITY_LEVEL, 16.0), ("room_tone", ROOM_TONE_LEVEL, 8.0),
     ("crickets", ambience.CRICKETS_LEVEL, ambience.CRICKETS_LOOP_SECONDS)],
)
def test_each_set_bed_is_a_seeded_seamless_loop_at_its_level(bed: str, level: float, seconds: float) -> None:
    make = ambience.BEDS[bed].loop
    loop = make()
    assert loop.shape == (int(seconds * RATE), 2) and loop.dtype == np.float32 and not loop.flags.writeable
    assert loop is make() and np.array_equal(make.__wrapped__(), loop)   # cached, and the same when made again
    assert integrated_loudness(loop) == pytest.approx(level, abs=0.1)
    steps = np.abs(np.diff(loop, axis=0))
    assert (np.abs(loop[0] - loop[-1]) <= np.quantile(steps, 0.99, axis=0)).all()   # no click where it repeats
    assert sfx.peak_db(loop) < -15.0
    assert not np.array_equal(loop[:, 0], loop[:, 1])   # wide


def test_the_beds_sound_like_what_they_are() -> None:
    birds, city, room, crickets = (ambience.BEDS[b].loop()[:, 0] for b in SET_BEDS)
    assert band_share(birds, 1800, 7000) > 0.8   # the songs, high
    assert band_share(city, 20, 1200) > 0.8      # traffic and a murmur, low
    assert band_share(room, 20, 500) > 0.6       # a soft low air (and a faint hiss)
    assert band_share(crickets, 3000, 6500) > 0.6   # the chirps, high (over a faint low night air)
    assert set(SET_BEDS) <= set(ambience.AMBIENCE_BEDS) == set(ambience.BEDS)


# ----- which beds a set plays (pure) ---------------------------------------------------------------------


def test_automatic_ambience_rules() -> None:
    day = [(0.0, "day")]
    assert set_ambience(True, room=True, lights=[(0.0, "night")], rain=[], end=10.0) == [("room_tone", 0.0, 10.0)]
    assert set_ambience(True, room=False, lights=day, rain=[], end=10.0) == [("birdsong", 0.0, 10.0)]
    assert set_ambience(True, room=False, lights=[(0.0, "morning"), (4.0, "day")], rain=[], end=10.0) == [("birdsong", 0.0, 10.0)]
    for light in ("night", "sunset", "indoor", None):   # None: a tint
        assert set_ambience(True, room=False, lights=[(0.0, light)], rain=[], end=10.0) == []
    assert set_ambience(True, room=False, lights=[(0.0, "day"), (6.0, "night")], rain=[], end=10.0) == [("birdsong", 0.0, 6.0)]
    assert set_ambience(True, room=False, lights=[(0.0, "night"), (3.0, "morning")], rain=[], end=10.0) == [("birdsong", 3.0, 10.0)]
    # not while it rains, nor BIRDS_AFTER_RAIN after; too short a span is left out
    assert set_ambience(True, room=False, lights=day, rain=[(4.0, 6.0)], end=12.0) == [("birdsong", 0.0, 4.0), ("birdsong", 6.0 + BIRDS_AFTER_RAIN, 12.0)]
    assert set_ambience(True, room=False, lights=day, rain=[(0.0, 12.0)], end=12.0) == []
    short = set_ambience(True, room=False, lights=day, rain=[(MIN_BIRDSONG_SECONDS - 0.5, 9.0)], end=10.0)
    assert short == []
    # named beds play the whole scene, whatever the set; false plays none
    assert set_ambience(["city"], room=False, lights=[(0.0, "night")], rain=[(0.0, 5.0)], end=8.0) == [("city", 0.0, 8.0)]
    assert set_ambience(["city", "birdsong", "city"], room=True, lights=day, rain=[], end=8.0) == [("city", 0.0, 8.0), ("birdsong", 0.0, 8.0)]
    assert set_ambience(False, room=True, lights=day, rain=[], end=8.0) == []


def test_a_stage_resolves_its_ambience_setting() -> None:
    from vidgen.scenes.stage import Stage

    def beds(given: Any, video: bool = True, foley: bool = True, room: bool = False) -> list[tuple[str, float, float]]:
        params = stage_params(ambience=given, **({"room": True} if room else {})) if given is not None else stage_params(**({"room": True} if room else {}))
        fake = SimpleNamespace(params=params, project=SimpleNamespace(config=SimpleNamespace(ambience=video)), light_marks=[(0.0, "day")], _foley_on=lambda: foley)
        return Stage.set_beds(fake, [], 6.0)   # type: ignore[arg-type]

    assert beds(None) == beds(True) == beds("auto") == [("birdsong", 0.0, 6.0)]
    assert beds(None, room=True) == [("room_tone", 0.0, 6.0)]
    assert beds(None, video=False) == [] and beds(True, video=False) == [("birdsong", 0.0, 6.0)]
    assert beds("city") == [("city", 0.0, 6.0)] and beds(["city", "room_tone"]) == [("city", 0.0, 6.0), ("room_tone", 0.0, 6.0)]
    assert beds(False) == [] and beds(None, foley=False) == [] and beds("city", foley=False) == []
    with pytest.raises(ValidationError):
        stage_params(ambience="traffic")


def test_set_beds_are_placed_with_their_ducking(make_project) -> None:
    project = Project.load(make_project(minimal_config()))
    timings = {"scenes": [{"beats": [{"id": "nothing_here", "start": 4.0, "end": 5.0}],
                           "ambience": [{"bed": "birdsong", "start": 0.0, "end": 9.0}, {"bed": "room_tone", "start": 0.0, "end": 9.0}]}]}
    birds, room = mix.plan_ambience(project, timings, 10 * RATE)
    assert (birds.bed, room.bed, birds.duck, room.duck) == ("birdsong", "room_tone", BIRDSONG_DUCK.depth, 0.0)
    gain = 20 * np.log10(np.maximum(birds.gain, 1e-12))
    assert gain[450] == pytest.approx(-BIRDSONG_DUCK.depth, abs=0.01)   # under the speech
    assert gain[round(SET_FADE_IN / 2 * 100)] == pytest.approx(20 * math.log10(0.5), abs=0.5)   # half-way through its fade in
    assert room.gain[450] == pytest.approx(1.0) and room.gain[700] == pytest.approx(1.0)   # the room tone never ducks


# ----- foley (no render) ---------------------------------------------------------------------------------


def test_doors_creak_and_shut() -> None:
    opened = foley_cues(PlayedAction("open", 2.0, 0.6, prop="door"))
    assert opened == [FoleyCue(2.0, "creak", DOOR_OPEN_CREAK[0], DOOR_OPEN_CREAK[1])]
    closed = foley_cues(PlayedAction("close", 2.0, 0.6, prop="door"))
    assert [(c.sound, c.time) for c in closed] == [("creak", 2.0), ("thud", pytest.approx(2.0 + RESHAPE_SHARE * 0.6))]
    assert foley_cues(PlayedAction("open", 2.0, 0.6, prop="umbrella")) == []   # only doors creak
    walk = {"heights": 2.0, "start": 1.0, "seconds": 2.0}
    sounds = lambda **kw: [c.sound for c in foley_cues(PlayedAction(**{**walk, **kw}))]   # noqa: E731
    assert sounds(action="enter")[0] == "whoosh" and "creak" not in sounds(action="enter")
    assert sounds(action="enter", through_door=True, opens_door=True)[0] == "creak"
    assert "whoosh" not in sounds(action="enter", through_door=True) and "creak" not in sounds(action="enter", through_door=True)
    assert sounds(action="exit")[-1] == "swoosh" and "swoosh" not in sounds(action="exit", through_door=True, opens_door=True)


def test_water_splashes() -> None:
    boat = foley_cues(PlayedAction("ride_to", 1.0, 4.0, vehicle="boat"))
    assert FoleyCue(1.0, "splash", BOAT_SPLASH[0], BOAT_SPLASH[1]) in boat and "engine" in [c.sound for c in boat]
    assert "splash" not in [c.sound for c in foley_cues(PlayedAction("ride_to", 1.0, 4.0, vehicle="car"))]
    [pour] = foley_cues(PlayedAction("pour", 3.0, 2.0, pours=True))
    flow = pour_flow(2.0)
    assert pour.sound == "splash" and pour.time == pytest.approx(3.0 + flow[0] + POUR_FALL_SECONDS)
    assert pour.params["duration"] == pytest.approx(flow[1] - flow[0], abs=1e-3)
    assert foley_cues(PlayedAction("pour", 3.0, 2.0)) == []   # the can's tilt itself is silent
    steps = foley_cues(PlayedAction("walk_to", 0.0, 3.0, heights=3.0))
    assert wet_steps(steps, None) == steps
    wet = wet_steps(steps, 1.0)
    splashes = [c for c in wet if c.sound == "splash"]
    assert [c.time for c in splashes] == [c.time for c in steps if c.sound == "footstep" and c.time >= 1.0] and splashes
    assert all((c.gain, c.params) == WET_STEP for c in splashes)


# ----- the knock action ----------------------------------------------------------------------------------


ROOM: dict[str, Any] = {
    "room": {"doors": [{"name": "front", "at": 0.8}, {"name": "back", "at": 0.2}]},
    "props": [{"prop": "sofa", "at": 0.5}],
    "characters": [{"name": "pip", "at": 0.6}, {"name": "kit", "at": 0.35}],
}


def test_knock_validates(make_project) -> None:
    good = [{"text": "Someone knocks.", "actions": [{"knock": "front", "at": 0.3}]}]
    assert check_project(room_project(make_project, ROOM, good)) == []
    bad = [{"text": "Hm.", "actions": [{"knock": "sofa"}, {"knock": "pip"}]}]
    problems = check_project(room_project(make_project, ROOM, bad))
    assert any("'sofa' is not a door; knock acts on doors (the stage's doors: front, back)" in p for p in problems), problems
    assert any("'pip' is not a door" in p for p in problems), problems
    scenes = [{"id": "intro", "type": "title", "params": {"title": "Hi"}, "beats": [{"text": "Hi.", "actions": [{"knock": "door"}]}]}]
    assert check_project(Project.load(make_project(minimal_config(scenes=scenes))))


# ----- renders -------------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_room_knocks_creaks_shuts_and_has_its_room_tone(make_project, tmp_path: Path) -> None:
    beats = [
        {"text": "Someone knocks at the front door.", "actions": [{"knock": "front", "at": 0.2}]},
        {"text": "Pip opens it, and kit comes in at the back.", "actions": [{"open": "front"}, {"enter": "kit", "door": "back", "at": 0.3}]},
        {"text": "Then pip shuts it again.", "actions": [{"close": "front"}]},
    ]
    params = {**ROOM, "idle": False}
    scene, _ = render_with_layout(room_project(make_project, params, beats), "home", tmp_path / "media")
    sounds = [(e.sound, round(e.time, 2)) for e in scene.sfx_log]
    names = [s for s, _ in sounds]
    assert names.count("knock") == 1 and names.count("creak") == 3 and names.count("thud") == 1, sounds
    assert "whoosh" not in names   # kit fades in through the doorway
    knock = next(t for s, t in sounds if s == "knock")
    assert scene.beat_log[0].start < knock < scene.beat_log[1].start
    assert scene.timings()["ambience"] == [{"bed": "room_tone", "start": 0.0, "end": round(float(scene.renderer.time), 6)}]


@pytest.mark.render
def test_birds_sing_by_day_until_the_night_falls(make_project, tmp_path: Path) -> None:
    beats = [{"text": "A sunny day in the park, with birds all around."}, {"text": "Then night falls.", "actions": [{"light": "night"}]}]
    scenes = [{"id": "park", "type": "stage", "params": {"characters": ["pip"], "idle": False}, "beats": beats}]
    scene, _ = render_with_layout(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), "park", tmp_path / "media")
    [bed] = scene.timings()["ambience"]
    change = scene.light_marks[1][0]
    assert bed == {"bed": "birdsong", "start": 0.0, "end": round(change, 6)} and scene.beat_log[1].start < change
    quiet = [{**scenes[0], "params": {**scenes[0]["params"], "ambience": False}}]
    scene, _ = render_with_layout(Project.load(make_project(minimal_config(characters=CAST, scenes=quiet))), "park", tmp_path / "media2")
    assert "ambience" not in scene.timings()


def test_registry_has_the_knock_action() -> None:
    extensions.load_builtins()
    assert "knock" in registry.action_names()
