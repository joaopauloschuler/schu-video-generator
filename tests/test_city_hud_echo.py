"""A city at night on an iso place, glowing particles, the HUD overlay and echo characters
(DESIGN.md §102): towers, traffic lanes of hover pods, ``glow`` on particles, ``hud``, ``echo``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST, stage_params
from test_overlays import bullets, project, render
from vidgen import extensions, hud, registry
from vidgen.cartoon import iso_city
from vidgen.cartoon.character import build_character
from vidgen.cartoon.echo import ECHO_COLOR, apply_echo, echo_fill, is_echo
from vidgen.cartoon.iso_objects import LIT_OBJECTS, ObjectLook, object_lights, object_shapes, tower_screen
from vidgen.cartoon.iso_stage import iso_view, wide_view
from vidgen.cli import check_project
from vidgen.config import CharacterEntry
from vidgen.particle_field import GLOW_HALO_OPACITY, GLOW_HALO_WIDTH, ParticleField, ParticleSettings, glow_colors
from vidgen.particles import particle_seeds
from vidgen.project import Project
from vidgen.theme import Theme
from vidgen.world.iso import OBJECT_FEATURES, SWITCHED_KINDS, TALL_KINDS, ObjectPlacing, ObjectState, default_state, parse_iso_map, place_objects
from vidgen.world.iso_view import Box3

CITY = "........\n........\n::::::::\na......b\n::::::::\n........"


def _city(objects: list[ObjectPlacing] = ()) -> Any:
    return place_objects(parse_iso_map(CITY, names={"a": "west", "b": "east"}), tuple(objects))


# ----- towers ----------------------------------------------------------------------------------------


def test_a_tower_stands_as_tall_as_it_is_given() -> None:
    place = _city([ObjectPlacing("tower", (1, 1), height=12.0, features=("screen", "garden")), ObjectPlacing("tower", (4, 1))])
    tall, plain = place.objects
    assert (tall.height, tall.features, (tall.width, tall.depth)) == (12.0, ("screen", "garden"), (2, 2))
    assert plain.height == 9.0 and default_state("tower").on and "tower" in SWITCHED_KINDS and "tower" in TALL_KINDS
    assert OBJECT_FEATURES["tower"] == ("screen", "garden")
    with pytest.raises(Exception, match="height is for a tower"):
        _city([ObjectPlacing("house", (1, 1), height=5.0)])
    with pytest.raises(Exception, match="no balcony"):
        _city([ObjectPlacing("tower", (1, 1), features=("balcony",))])
    with pytest.raises(Exception, match="2 to 30"):
        _city([ObjectPlacing("tower", (1, 1), height=40.0)])


def test_a_towers_windows_neon_screen_and_antenna() -> None:
    place = _city([ObjectPlacing("tower", (1, 1), height=10.0, features=("screen", "garden"))])
    tower = place.objects[0]
    look = ObjectLook("#2A3050", "#FF2E8B")
    lit = object_shapes(tower, look, 0.0)
    dark = object_shapes(tower, look, 0.0, ObjectState(on=False))
    glowing = [s for s in lit if getattr(s, "glow", False)]
    assert len(glowing) > len([s for s in dark if getattr(s, "glow", False)]) + 20   # lit windows
    assert any(getattr(s, "fill", None) == iso_city.TOWER_GARDEN_COLOR for s in glowing)   # the algae farms
    corners = tower_screen(tower, 0.0)
    assert corners is not None and corners[2][2] > corners[0][2]   # the screen's top above its bottom
    assert "tower" in LIT_OBJECTS and object_lights(tower, 0.0)[0][2] == pytest.approx(10.0 + iso_city.TOWER_ANTENNA)
    assert tower_screen(_city([ObjectPlacing("tower", (1, 1))]).objects[0], 0.0) is None


def test_the_city_maths() -> None:
    s0, s1, z0, z1 = iso_city.screen_box(3.0)
    assert 0 < s0 < s1 < 1 and z1 - z0 >= iso_city.TOWER_SCREEN_MIN - 1e-9
    assert all(0 < a < b < 12.0 for a, b in iso_city.garden_bands(12.0)) and iso_city.garden_bands(12.0)
    first, later = iso_city.screen_lines(0.0, seed=3), iso_city.screen_lines(1.0, seed=3)
    assert len(first) == iso_city.SCREEN_LINES and first != later and first == iso_city.screen_lines(0.0, seed=3)
    assert all(0 < up < 1 and 0.3 <= length <= 0.92 for up, length in later)
    loop = iso_city.lane_pods(2.0, seconds=6.0, count=3)
    assert len(loop) == 3 and all(0 <= p.share < 1 and 0 <= p.shown <= 1 for p in loop)
    assert iso_city.lane_pods(0.5, 6.0, 1, at=1.0) == []   # not yet set off
    mid = iso_city.lane_pods(4.0, 6.0, 1, at=1.0)
    assert len(mid) == 1 and mid[0].share == pytest.approx(0.5) and mid[0].shown == 1.0
    assert iso_city.lane_pods(8.0, 6.0, 1, at=1.0) == []   # it has crossed


def test_a_pod_behind_a_building_is_hidden() -> None:
    tower = Box3(4.0, 4.0, 0.0, 6.0, 6.0, 10.0)
    occluders = [(tower, iso_city.box_outline(tower))]
    assert iso_city.pod_hidden((3.0, 3.0, 3.0), occluders)   # behind it, where its picture covers
    assert not iso_city.pod_hidden((7.0, 7.0, 3.0), occluders)   # in front of it
    assert not iso_city.pod_hidden((3.0, 3.0, 14.0), occluders)   # high over its roof on the picture


def test_towers_may_reach_out_of_the_wide_view() -> None:
    place = _city([ObjectPlacing("tower", (1, 1), height=14.0, name="spire")])
    view = iso_view(place, 16.0, 9.0)
    assert wide_view(place, view, 16.0, 9.0, placed=["spire"]) == wide_view(place, view, 16.0, 9.0, placed=[])


def test_tower_and_traffic_params() -> None:
    iso = {"map": CITY, "spots": {"a": "west", "b": "east"},
           "objects": [{"object": "tower", "at": {"column": 1, "row": 1}, "height": 8, "screen": True}],
           "traffic": [{"from": "west", "to": "east", "height": 4, "at": 1.5, "count": 1}]}
    params = stage_params(iso=iso)
    lane = params.iso.traffic[0]
    assert params.iso.objects[0].state().on and lane.at == 1.5
    start, end = params.iso.lane_ends(lane)
    assert start[2] == end[2] == pytest.approx(4.0) and end[0] > start[0]
    assert params.iso.objects[0].placing().features == ("screen",)
    assert stage_params(iso={**iso, "objects": [{"object": "tower", "at": {"column": 1, "row": 1}, "on": False}]}).iso.objects[0].state().on is False
    for bad, message in (({**iso, "objects": [{"object": "house", "at": {"column": 1, "row": 1}, "screen": True}]}, "screen is for a tower"),
                         ({**iso, "traffic": [{"from": "west", "to": "nowhere"}]}, "no spot 'nowhere'"),
                         ({**iso, "traffic": [{"from": "west", "to": "west"}]}, "the same place"),
                         ({**iso, "place": "indoor", "map": "####\n#ab#\n####", "objects": []}, "outdoor")):
        with pytest.raises(ValidationError, match=message):
            stage_params(iso=bad)


# ----- glowing particles -----------------------------------------------------------------------------


def test_glowing_particles_have_a_core_and_a_halo() -> None:
    core, halo = glow_colors("#3080FF")
    assert core != halo and halo.upper() == "#3080FF"
    assert ParticleSettings().glow is False and ParticleSettings(glow=True).glow
    seeds = particle_seeds("rain", 20, 1)
    view = [(-7.0, -4.0, 7.0, 4.0)]
    common = dict(clock=lambda: 1.0, view=lambda: view[0], area=[0.0, 0.0, 1.0, 1.0], short_side=8.0, frame_width=14.0)
    plain = ParticleField(seeds, ["#3080FF"], **common)   # type: ignore[arg-type]
    shining = ParticleField(seeds, ["#3080FF"], glow=True, **common)   # type: ignore[arg-type]
    drop = shining.drops[0]
    assert drop.get_stroke_width() == pytest.approx(GLOW_HALO_WIDTH) and drop.stroke_rgbas[0, 3] <= GLOW_HALO_OPACITY + 1e-9
    plain.draw_at(2.0)
    shining.draw_at(2.0)
    alpha = lambda field: sum(float(d.fill_rgbas[0, 3]) for d in field.drops)  # noqa: E731
    assert alpha(shining) > alpha(plain) * 1.3   # brighter than plain rain
    view[0] = (-3.5, -2.0, 3.5, 2.0)   # zoomed in twice: the halo stays as wide on screen
    shining.draw_at(1.0)
    assert drop.get_stroke_width() == pytest.approx(GLOW_HALO_WIDTH / 2)


# ----- echo characters ------------------------------------------------------------------------------


def test_an_echo_keeps_its_colours_translucent() -> None:
    entry = CharacterEntry.model_validate({"name": "ana", "echo": {"opacity": 0.4}, "look": {"body": "tall"}, "colors": {"clothes": "#2B3350"}})
    look = entry.echo_look()
    assert look is not None and look.opacity == 0.4 and look.flicker and CharacterEntry(name="x").echo_look() is None
    figure = build_character(entry, theme=Theme())
    assert is_echo(figure)
    fills = [m.get_fill_opacity() for m in figure.get_family() if hasattr(m, "get_fill_opacity") and len(m.points)]
    assert max(fills) <= 0.4 + 1e-6
    assert echo_fill("#2B3350", ECHO_COLOR) != ECHO_COLOR   # its own colour, a little towards the echo's
    with pytest.raises(ValidationError, match="hologram or an echo"):
        CharacterEntry.model_validate({"name": "ana", "echo": True, "hologram": True})
    assert apply_echo(build_character(CharacterEntry(name="b"), theme=Theme()), "#FF0000", 0.5).echo == ("#FF0000", 0.5)


# ----- the HUD ----------------------------------------------------------------------------------------


def test_the_hud_maths() -> None:
    assert hud.alert_on(0.1) and not hud.alert_on(0.75)
    assert hud.lines_shown(0.0, 2) == [0.0, 0.0] and hud.lines_shown(2.0, 2) == [1.0, 1.0]
    steady = hud.heart_beats(4.0, hud.HeartMonitor(60.0), since=0.0)
    assert steady == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0])
    skipping = hud.heart_beats(4.0, hud.HeartMonitor(60.0, at=1.5, skips=2), since=0.0)
    assert skipping == pytest.approx([0.0, 1.0, 4.0])   # the beats at 2 and 3 are skipped
    assert hud.heart_rate(10.0, hud.HeartMonitor(70.0, 130.0, 1.0)) == pytest.approx(130.0)
    assert hud.ecg(0.13) > 0.9 and hud.ecg(1.0) == 0.0
    trace = hud.heart_trace(2.05, hud.HeartMonitor(60.0), samples=30)
    assert len(trace) == 30 and max(trace) > 0.5
    spike = hud.ScanMeter(0.3, 1.6, 1.0)
    assert hud.scan_level(0.5, spike) == 0.3 and hud.scan_level(5.0, spike) == pytest.approx(1.6)
    assert max(abs(v) for v in hud.scan_wave(5.0, spike)) > max(abs(v) for v in hud.scan_wave(0.5, spike))


def test_hud_options_validate(make_project) -> None:
    extensions.load_builtins()
    options = registry.find_overlay("hud").cls.Options
    good = options.model_validate({"alert": "ALERT", "lines": ["A"], "heart": {"bpm": 70, "to": 120, "skips": 3}, "scan": {"to": 1.5}, "at": "s_b2"})
    assert good.heart.skips == 3 and good.scan.to == 1.5
    for bad in ({"heart": {"bpm": 500}}, {"scan": {"wave": "jagged"}}, {"at": -1}, {"colour": "red"}):
        with pytest.raises(ValidationError):
            options.model_validate(bad)
    scene = bullets("s", beats=2, overlays={"implant": {"type": "hud", "at": "s_b9", "alert": "x"}})
    problems = check_project(project(make_project, [scene], []))
    assert any("no beat 's_b9'" in p for p in problems), problems


@pytest.mark.render
def test_the_hud_moves_on_every_frame(make_project, tmp_path: Path) -> None:
    hud_entry = {"type": "hud", "at": 0.2, "duration": 2.0, "alert": "INCOMING", "lines": ["ONE", "TWO"],
                 "heart": {"bpm": 80, "to": 120, "at": 0.5, "skips": 1}, "scan": {"level": 0.4, "to": 1.4, "at": 0.8}}
    scene_cfg = bullets("s", beats=1, overlays={"implant": hud_entry})
    scene = render(project(make_project, [scene_cfg], []), "s", tmp_path)
    layer = scene.overlay_layer
    states = [layer.states(k)[0] for k in range(25)]
    assert states[0] is None and states[10] is not None and states[10] != states[11]   # on from 0.2 s; it moves
    posed = layer.posed(15)[0][1]
    assert len(posed.submobjects) > len(layer.mobjects[0].submobjects)   # the trace, the meter, their words
    plain = render(project(make_project, [bullets("s", beats=1)], []), "s", tmp_path)
    assert np.any(scene.frames_seen[15] != plain.frames_seen[15])


@pytest.mark.render
def test_a_city_at_night_renders(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    cast = [*CAST, {"name": "ghost", "echo": True, "look": {"body": "bean"}}]
    iso = {"map": CITY, "spots": {"a": "west", "b": "east"},
           "objects": [{"object": "tower", "at": {"column": 2, "row": 1}, "height": 7, "screen": True, "garden": True}],
           "traffic": [{"from": "west", "to": "east", "height": 3, "count": 2, "seconds": 3}]}
    params = {"light": "night", "iso": iso, "particles": [{"kind": "rain", "glow": True, "color": ["#5FFFE0"]}],
              "characters": [{"name": "pip", "at": "west"}, {"name": "ghost", "at": "east"}]}
    beats = [{"text": "Pods glide over the wet street.", "actions": [{"materialise": "ghost", "at": 0.2}]}]
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    scene, frames = frames_of(Project.load(make_project(minimal_config(characters=cast, scenes=scenes))), tmp_path / "city", monkeypatch)
    names = {type(thing).__name__ for thing in scene.story_things}
    assert {"IsoScreens", "IsoTraffic", "IsoBlinkers"} <= names
    assert is_echo(scene.cast["ghost"])
    assert len(frames) > 5 and np.any(frames[-1] != frames[2])
