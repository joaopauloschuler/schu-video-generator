"""A day passing in one scene, Step 270 (DESIGN.md §105.3): the ``time_of_day`` action, dusk and
dawn, the lights switching on and off by themselves, the sky of the time of day."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST
from test_iso_moves import problems
from vidgen import extensions, registry
from vidgen.cartoon.lighting import (
    AUTO_SPREAD,
    DUSK_DARK,
    auto_switch_time,
    darkness,
    day_stages,
    dusk_crossing,
    light_grade,
    pool_strength,
)
from vidgen.project import Project
from vidgen.world.iso import AUTO_LIGHT_KINDS, SWITCHED_KINDS


@pytest.mark.slow
def test_daylight_rules_do_not_import_manim() -> None:
    code = "import sys, vidgen.cartoon.lighting; assert 'manim' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_dusk_falls_between_day_and_sunset_and_night() -> None:
    dark = {name: darkness(light_grade(name)) for name in ("day", "morning", "indoor", "sunset", "night")}
    assert dark["day"] == 0.0 and dark["night"] == 1.0
    assert dark["day"] < dark["morning"] < dark["indoor"] < DUSK_DARK < dark["sunset"] < dark["night"]
    # the pools of light grow with it (Phase AC's rule)
    assert pool_strength(light_grade("day")) < pool_strength(light_grade("sunset")) < pool_strength(light_grade("night")) == 1.0


def test_where_a_fade_crosses_dusk_or_dawn() -> None:
    day, sunset, night, morning = (light_grade(n) for n in ("day", "sunset", "night", "morning"))
    time, on = dusk_crossing(day, night, 10.0, 6.0)
    assert on and 10.0 < time < 16.0
    time, on = dusk_crossing(night, morning, 2.0, 4.0)
    assert not on and 2.0 < time < 6.0
    assert dusk_crossing(day, sunset, 0.0, 4.0)[1] is True   # the sunset is past dusk
    assert dusk_crossing(sunset, night, 0.0, 4.0) is None   # dark already: nothing switches again
    assert dusk_crossing(day, morning, 0.0, 4.0) is None
    assert dusk_crossing(day, night, 3.0, 0.0) == (3.0, True)   # at once


def test_lights_switch_one_after_another_inside_the_fade() -> None:
    times = [auto_switch_time(f"street_lamp_{k}", 12.0, 10.0, 6.0) for k in range(8)]
    assert len(set(times)) == len(times) and all(abs(t - 12.0) <= AUTO_SPREAD + 1e-9 for t in times)
    assert times == [auto_switch_time(f"street_lamp_{k}", 12.0, 10.0, 6.0) for k in range(8)]   # the same in every render
    assert all(10.0 <= auto_switch_time(f"lamp_{k}", 10.1, 10.0, 1.0) <= 11.0 for k in range(8))   # short fade: less spread, inside it


def test_day_to_night_goes_through_a_sunset() -> None:
    assert day_stages(light_grade("day"), "night") == [("sunset", 0.5), ("night", 1.0)]
    assert day_stages(light_grade("night"), "day") == [("morning", 0.5), ("day", 1.0)]
    assert day_stages(light_grade("sunset"), "night") == [("night", 1.0)]
    assert day_stages(light_grade("night"), "morning") == [("morning", 1.0)]


def test_auto_lit_kinds_switch() -> None:
    assert AUTO_LIGHT_KINDS <= SWITCHED_KINDS and "tower" not in AUTO_LIGHT_KINDS and "campfire" not in AUTO_LIGHT_KINDS


# ----- the action ---------------------------------------------------------------------------------------

MAP = """
............
............
............
::::::::::::
....s.......
"""
OBJECTS = [{"object": "street_lamp", "at": {"column": 5, "row": 3}}, {"object": "house", "at": {"column": 1, "row": 1}},
           {"object": "lamp", "at": {"column": 11, "row": 1}, "auto_light": False}, {"object": "tree", "at": {"column": 8, "row": 1}},
           {"object": "car", "at": {"column": 1, "row": 4}}]


def village(make_project, beats: list[dict[str, Any]], **params: Any) -> Project:
    params = {"idle": False, "iso": {"map": MAP, "spots": {"s": "square"}, "objects": OBJECTS}, "characters": [{"name": "pip", "at": "square"}], **params}
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


@pytest.mark.slow
@pytest.mark.parametrize(
    "action,message",
    [
        ({"time_of_day": "sunst"}, "unknown time of day 'sunst'; did you mean 'sunset'?"),
        ({"time_of_day": ["night", "day"]}, "one time of day per action"),
        ({"action": "time_of_day"}, "which time of day? write `- time_of_day: PRESET`"),
        ({"time_of_day": "night", "move_sun": True}, "move_sun moves the stage's sun or moon: it needs a sun or a moon prop"),
        ({"time_of_day": "night", "auto_light": False}, "auto_lights"),
    ],
)
def test_bad_time_of_day(make_project, action: dict[str, Any], message: str) -> None:
    found = problems(village(make_project, [{"text": "Night falls.", "actions": [action]}]), "home")
    assert any(message in text for _, text in found), found


def test_time_of_day_is_for_stages(make_project) -> None:
    scenes = [{"id": "home", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Night falls.", "actions": [{"time_of_day": "night"}]}]}]
    texts = [text for _, text in problems(Project.load(make_project(minimal_config(scenes=scenes))), "home")]
    assert any("time_of_day is for stage scenes" in t for t in texts), texts


def test_good_time_of_day_validates(make_project) -> None:
    beats = [{"text": "Evening comes.", "actions": [{"time_of_day": "night", "run_time": 6}]},
             {"text": "Then morning.", "actions": [{"time_of_day": "morning", "auto_lights": False}]}]
    assert problems(village(make_project, beats), "home") == []


def test_auto_light_opt_out_and_who_switches(make_project) -> None:
    from vidgen.scenes.stage import IsoObjectParam, StageIso, StageProp

    iso = StageIso(map=MAP, spots={"s": "square"}, objects=OBJECTS)
    assert iso.auto_lit() == {"street_lamp": "street_lamp", "house": "house", "car": "car"}   # not the lamp kept off, not the tree
    with pytest.raises(ValidationError, match="auto_light is for the lights a time_of_day switches"):
        IsoObjectParam(object="tree", at="s", auto_light=False)
    with pytest.raises(ValidationError, match="auto_light is for a lamp"):
        StageProp(prop="tree", auto_light=False)


def test_a_setting_sun_sinks_behind_the_ground() -> None:
    """Step 275: with a ground band in front of the sky, the sun shows whole down to the horizon
    and sinks behind the ground (it faded out above it, beside the characters' feet)."""
    from manim import Circle

    from vidgen.cartoon.sun_path import path_height
    from vidgen.cartoon.weather_drawing import SkyBody

    low = 0.995   # just over the horizon: path height ~0.016
    assert 0.0 < path_height(low) < 0.05
    for sink, expected in ((0.0, 0.0), (0.1, 1.0)):
        sun = Circle(radius=0.2, fill_opacity=1.0)
        body = SkyBody(sun, "sun", low, lambda x, h: (x, h), sink)
        body.update(0.0)
        assert sun.fill_rgbas[:, 3].max() == pytest.approx(expected, abs=0.05)
    sun = Circle(radius=0.2, fill_opacity=1.0)
    gone = SkyBody(sun, "sun", 1.06, lambda x, h: (x, h), 0.1)   # under the horizon by more than its height
    gone.update(0.0)
    assert sun.fill_rgbas[:, 3].max() == 0.0 and sun.get_center()[1] < -0.1


@pytest.mark.slow
@pytest.mark.render
def test_lamps_come_on_when_a_rainy_day_turns_to_night(make_project, tmp_path: Path, monkeypatch) -> None:
    """Step 275: a rainy iso day starts overcast, past dusk already: the lights still come on
    early in a time_of_day to night."""
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    beats = [{"text": "Evening comes to the wet village.", "actions": [{"time_of_day": "night", "run_time": 2}]}]
    project = village(make_project, beats, particles=[{"kind": "rain", "puddles": True}])
    scene, _ = frames_of(project, tmp_path / "rain", monkeypatch)
    assert darkness(scene.base_light) > DUSK_DARK   # overcast from the start
    assert scene._iso_planned_states["street_lamp"].on and scene._iso_planned_states["house"].on


@pytest.mark.slow
@pytest.mark.render
def test_a_day_passes_and_the_lights_come_on_by_themselves(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    beats = [{"text": "Evening comes to the village.", "actions": [{"time_of_day": "night", "run_time": 3}]},
             {"text": "And the night is quiet and dark.", "actions": [{"drive_to": "car", "to": {"column": 11, "row": 4}}]}]
    project = village(make_project, beats)
    scene, frames = frames_of(project, tmp_path / "day", monkeypatch)
    states = scene._iso_planned_states
    assert states["street_lamp"].on and states["house"].on and "lamp" not in states   # auto_light: false: left alone
    assert scene.iso_vehicles["car"].on_at(2.0) and not scene.iso_vehicles["car"].on_at(0.0)   # the driven car's headlights
    assert scene.day_sky is not None and scene.stars is not None
    # the sky goes from the day's blue to the night's dark blue, smoothly (no frame jumps far)
    top = [f[2, f.shape[1] // 2].astype(float) for f in frames]
    first = max(range(len(top) // 3), key=lambda k: top[k].sum())   # once the scene has faded in
    assert top[first][2] > 150 and top[first][2] > top[first][0] and top[-1].sum() < top[first].sum() / 2
    assert max(np.abs(b - a).max() for a, b in zip(top[first:], top[first + 1:])) < 40
