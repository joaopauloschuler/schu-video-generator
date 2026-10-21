"""Step 169: time of day, sound and who speaks on an iso place — lit lamps and windows that glow
at night (a picture of the lights, never graded), rain landing anywhere on the place, crickets
at night, footsteps by surface and the sounds of handing things about and of changes to the
place, name tags over small speakers, and the iso lint (a speaker's eyes and mouth hidden by
what really covers them, a small tagged speaker, an action off screen); a tiny render of it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_lint import check, fig, thing
from test_cartoon_stage import CAST, render_with_layout, stage_params
from test_iso_staging import FH, FW, ISO, POND, iso_project, looks, pond, problems
from vidgen import sfx
from vidgen.ambience import set_ambience
from vidgen.cartoon.foley import (
    SURFACE_STEPS,
    PlayedAction,
    footfall_distances,
    footfall_shares,
    foley_cues,
    handling_cues,
    place_change_cues,
    surface_under,
    wet_steps,
)
from vidgen.cartoon.iso_drawing import IsoCanvas, Poly, draw_shapes
from vidgen.cartoon.iso_objects import LIT_GLASS, ObjectLook, object_shapes
from vidgen.cartoon.iso_scenery import IsoColors
from vidgen.cartoon.iso_stage import IsoScenery, iso_view, place_outline
from vidgen.cartoon.rain import NO_FLOOR, IsoRainGround, RainGround, landing_lines
from vidgen.project import Project
from vidgen.world.iso import ObjectPlacing, ObjectState, parse_iso_map, place_objects
from vidgen.world.iso_moves import IsoRoute, find_route, route_surfaces, surface_at


# ----- lights that glow (no manim) -----------------------------------------------------------------


def test_a_picture_of_the_lights_shows_only_what_glows_and_is_not_hidden() -> None:
    canvas = IsoCanvas(40.0, -2.0, -1.0, 160, 120)
    light = Poly(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)), "#FFD75E", False, glow=True)
    plain = Poly(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)), "#3366AA", False)
    lit = np.asarray(draw_shapes([light], canvas, glow=True))
    assert lit[..., 3].max() == 255 and (lit[..., 3] == 255).sum() > 100
    hidden = np.asarray(draw_shapes([light, plain], canvas, glow=True))   # drawn over it: cleared
    assert hidden[..., 3].max() < 40
    behind = np.asarray(draw_shapes([plain, light], canvas, glow=True))   # behind it: not in the picture
    assert np.array_equal(behind[..., 3] > 128, lit[..., 3] > 128)
    whole = np.asarray(draw_shapes([plain, light], canvas))   # the picture itself is as before
    assert np.array_equal(whole, np.asarray(draw_shapes([plain, light], canvas, glow=False)))


def test_lit_lamps_and_windows_glow_and_their_pictures_say_so() -> None:
    lamp = place_objects(parse_iso_map("l..\n...", names={"l": "post"}), [ObjectPlacing("lamp", "post")])
    on = object_shapes(lamp.objects[0], ObjectLook("#555555", "#FFEEAA"), 0.0, ObjectState(on=True))
    off = object_shapes(lamp.objects[0], ObjectLook("#555555", "#FFEEAA"), 0.0, ObjectState())
    assert sum(getattr(s, "glow", False) for s in on) >= 3 and not any(getattr(s, "glow", False) for s in off)   # lantern faces, pool
    scenery = IsoScenery(lamp, IsoColors(), looks(lamp), iso_view(lamp, FW, FH), 30.0, states={"lamp": ObjectState(on=True)})
    assert scenery.glows(scenery.base())
    scenery.set_state("lamp", ObjectState())
    assert not scenery.glows(scenery.base())
    house = place_objects(parse_iso_map("h...\n....\n....\n...."), [ObjectPlacing("house", (1, 1))])
    shapes = object_shapes(house.objects[0], ObjectLook("#C08040", "#E06060"), 0.0, ObjectState(on=True))
    assert any(getattr(s, "glow", False) and getattr(s, "fill", "") == LIT_GLASS for s in shapes)


# ----- rain on the place (no manim) -----------------------------------------------------------------


def test_rain_lands_anywhere_on_the_place_and_not_beside_it_or_on_a_face() -> None:
    place = pond()
    view = iso_view(place, FW, FH)
    xs, fronts, backs = place_outline(place, view)
    assert len(xs) > 100 and all(f <= b for f, b in zip(fronts, backs)) and fronts[len(xs) // 2] < backs[len(xs) // 2]
    ground = IsoRainGround(-FH / 2, -FH / 2, FH / 2, FH, (), xs, fronts, backs)
    shares = np.linspace(0.0, 1.0, 9)
    x = np.full(9, xs[len(xs) // 2])
    lines = ground.landing(shares, x)
    assert lines.min() == pytest.approx(fronts[len(xs) // 2]) and lines.max() == pytest.approx(backs[len(xs) // 2])
    assert (ground.landing(shares, np.full(9, xs[-1] + 1.0)) == NO_FLOOR).all()   # beside the place: through
    body = (x[0] - 0.1, float(lines.min()) - 0.1, x[0] + 0.1, float(lines.max()) + 0.1)
    covered = IsoRainGround(-FH / 2, -FH / 2, FH / 2, FH, (), xs, fronts, backs, (body,))
    assert (covered.landing(shares, x) == NO_FLOOR).all()
    assert (ground.depth(lines) == 0).all()   # no perspective: splashes the same size
    flat = RainGround(-3.0, -3.2, -1.0, FH)   # a flat stage's band is as before
    assert np.array_equal(flat.landing(shares, x), landing_lines(shares, flat))


@pytest.mark.parametrize("particles", [[{"kind": "rain", "puddles": True}], [{"kind": "snow", "settle": True}]])
def test_an_iso_place_takes_puddles_and_settling_snow(particles: list[dict[str, Any]]) -> None:
    # refused in Steps 169-171; drawn since Step 172 (DESIGN.md §90)
    assert stage_params(iso=ISO, characters=[{"name": "pip", "at": "start"}], particles=particles).particles


def test_no_rain_indoors_on_an_iso_place(make_project) -> None:
    room = {"place": "indoor", "map": "####\n#.a#\n#..#\n####", "spots": {"a": "middle"}}
    with pytest.raises(ValidationError, match="an indoor place has none inside"):
        stage_params(iso=room, characters=[{"name": "pip", "at": "middle"}], particles=["rain"])
    beats = [{"text": "Rain.", "actions": [{"particles": "rain", "puddles": True}]}]
    assert problems(iso_project(make_project, beats)) == []   # outdoors: puddles grow (§90.2)
    assert stage_params(iso=ISO, characters=[{"name": "pip", "at": "start"}], particles=["rain"]).particles[0].kind == "rain"


# ----- sound (no manim) --------------------------------------------------------------------------------


def test_crickets_chirp_in_the_evening_and_at_night_on_an_iso_place_only() -> None:
    night = [(0.0, "night")]
    assert set_ambience(True, room=False, lights=night, rain=[], end=10.0) == []   # a flat stage: as before
    assert set_ambience(True, room=False, lights=night, rain=[], end=10.0, crickets=True) == [("crickets", 0.0, 10.0)]
    assert set_ambience(True, room=False, lights=[(0.0, "sunset")], rain=[], end=10.0, crickets=True) == [("crickets", 0.0, 10.0)]
    day_night = set_ambience(True, room=False, lights=[(0.0, "day"), (5.0, "night")], rain=[], end=10.0, crickets=True)
    assert day_night == [("birdsong", 0.0, 5.0), ("crickets", 5.0, 10.0)]
    assert set_ambience(True, room=False, lights=night, rain=[(0.0, 10.0)], end=10.0, crickets=True) == []
    assert set_ambience(True, room=True, lights=night, rain=[], end=10.0, crickets=True) == [("room_tone", 0.0, 10.0)]
    assert stage_params(iso=ISO, characters=[{"name": "pip", "at": "start"}], ambience="crickets").ambience == "crickets"


def test_each_cell_is_a_surface_underfoot() -> None:
    village = parse_iso_map(".:1~\n..1.", names={})
    assert [surface_at(village, c, 0) for c in range(3)] == ["grass", "path", "stone"]
    room = parse_iso_map("####\n#.:#\n#..#\n####", place="indoor")
    assert surface_at(room, 1, 1) == "boards" and surface_at(room, 2, 1) == "tiles"
    place = pond()
    assert surface_at(place, 3, 1) == "bridge"
    route = find_route(place, (0, 1), (6, 1))
    found = route_surfaces(place, route)
    assert [s for _, s in found] == ["grass", "bridge", "grass"] and found[0][0] == 0.0
    assert 0.0 < found[1][0] < found[2][0] < 1.0
    assert surface_under(found, 0.0) == "grass" and surface_under(found, 0.5) == "bridge" and surface_under((), 0.5) is None
    beyond = IsoRoute(((-0.5, 1.5, 0.0), (0.5, 1.5, 0.0), (1.5, 1.5, 0.0)), (None, (0, 1), (1, 1)))
    assert route_surfaces(place, beyond) == ((0.0, "grass"),)


def test_footsteps_follow_the_surface_and_a_flat_stage_keeps_its_footstep() -> None:
    heights = 4.0
    assert len(footfall_distances(heights)) == len(footfall_shares(heights))
    assert footfall_distances(heights)[-1] == 1.0 and footfall_distances(0.0) == []
    flat = foley_cues(PlayedAction("walk_to", 1.0, 2.0, heights=heights))
    assert {c.sound for c in flat if c.sound != "whoosh"} == {"footstep"}
    iso = foley_cues(PlayedAction("walk_to", 1.0, 2.0, heights=heights, surfaces=((0.0, "grass"), (0.5, "bridge"))))
    steps = [c for c in iso]
    assert [c.time for c in steps] == [c.time for c in flat]
    assert steps[0].sound == "step_grass" and steps[-1].sound == "step_wood"
    assert steps[-1].params["pitch"] < SURFACE_STEPS["boards"][2] + 0.1   # a bridge is lower than boards
    assert all(c.sound in sfx.BUILTIN_SOUNDS for c in steps)
    assert len(wet_steps(iso, 0.0)) == 2 * len(iso)   # a splash under each surface's step too
    for name in ("step_grass", "step_gravel", "step_wood", "step_stone"):
        samples = sfx.synthesize(name)
        assert np.isfinite(samples).all() and sfx.peak_db(samples) <= -0.9 and len(samples) == round(sfx.BUILTIN_SOUNDS[name].duration * sfx.RATE)


def test_handing_things_about_and_changes_of_the_place_sound() -> None:
    (pick,) = handling_cues("pick_up", 2.0, 1.2)
    assert pick.sound == "pop" and pick.time == pytest.approx(2.0 + 0.45 * 1.2)
    assert [c.sound for c in handling_cues("give", 0.0, 1.0)] == ["swoosh"]
    assert [c.sound for c in handling_cues("put_down", 0.0, 1.0)] == ["thud"] and handling_cues("walk_to", 0.0, 1.0) == []
    assert [c.sound for c in place_change_cues("house", True, None, 1.0, 0.6)] == ["creak"]
    assert [c.sound for c in place_change_cues("door", False, None, 1.0, 0.6)] == ["creak", "thud"]
    assert [c.sound for c in place_change_cues("flowers", True, None, 1.0, 0.6)] == ["twinkle"]
    assert place_change_cues("flowers", False, None, 1.0, 0.6) == [] and place_change_cues("lamp", None, None, 1.0, 0.25) == []
    assert [c.sound for c in place_change_cues("bridge", None, True, 1.0, 0.8)] == ["twinkle"]
    assert place_change_cues("rock", None, False, 1.0, 0.8) == []


# ----- lint on synthetic dumps (no manim) -----------------------------------------------------------------


def _mask(rows: list[str]) -> str:
    return "".join(rows)


def test_hidden_speaker_on_an_iso_place_measures_what_covers_the_eyes_and_mouth() -> None:
    face = [100.0, 100.0, 220.0, 220.0]
    speaker = fig("dot", [80, 60, 240, 400], speaking=True, face=face, features=[130.0, 140.0, 190.0, 190.0])
    post = "000110000000" * 12   # a post across the face: 2 of 12 columns
    tile = thing("iso_front_dot", [0, 0, 400, 400], kind="image", scenery=True, covers={"dot": post}, pieces=["lamp"])
    assert check("hidden_speaker", [speaker, tile]) == []   # 17 % < 25 %
    pole = "000111100000" * 12
    (issue,) = check("hidden_speaker", [speaker, {**tile, "covers": {"dot": pole}}])
    assert "33% of its eyes and mouth hidden behind the place's lamp" in issue.message and issue.limit == 0.25
    empty = {**tile, "covers": {"dot": "0" * 144}}   # its box covers the face, its pixels do not (a tree's corner)
    assert check("hidden_speaker", [speaker, empty]) == []
    flat = fig("dot", [80, 60, 240, 400], speaking=True, face=face)   # a flat stage: the box, as before
    assert len(check("hidden_speaker", [flat, thing("crate", [90, 90, 230, 230])])) == 1
    tag = thing("tag", [120, 130, 200, 200], kind="shape", name_tag="kit")
    assert check("hidden_speaker", [speaker, tag]) == []


def test_a_small_speaker_with_a_name_tag_may_say_a_short_line() -> None:
    small = fig("dot", [400, 300, 420, 340], speaking=True, face=[400.0, 300.0, 420.0, 315.0])
    assert len(check("small_speaker", [small], line_words=6)) == 1   # no tag: reported as before
    tagged = {**small, "name_tag": True}
    assert check("small_speaker", [tagged], line_words=6) == []
    assert len(check("small_speaker", [tagged], line_words=20)) == 1   # too long a line for a tag
    assert len(check("small_speaker", [tagged])) == 1   # a still without the words: reported


def test_offscreen_action_names_what_the_camera_did_not_show() -> None:
    dot = fig("dot", [900, 100, 950, 300])
    acts = [{"action": "walk_to", "who": "dot", "seen": 0.2}, {"action": "open", "who": "house", "seen": 0.9},
            {"action": "switch_on", "who": "lamp", "seen": 0.0}]
    issues = check("offscreen_action", [dot], iso_actions=acts)
    assert [i.objects[0]["name"] for i in issues] == ["dot", "lamp"]
    assert "the walk_to of 'dot' happens off screen (in view on 20% of its frames)" in issues[0].message
    assert issues[1].objects[0]["kind"] == "iso_object" and issues[1].objects[0]["id"] != issues[0].objects[0]["id"]
    assert check("offscreen_action", [dot]) == []   # a flat stage's still has none


# ----- a tiny render -------------------------------------------------------------------------------


@pytest.mark.render
def test_a_night_on_the_place_renders_with_glow_tags_rain_and_sounds(make_project, tmp_path: Path) -> None:
    from vidgen.cartoon.iso_pictures import GlowTile
    from vidgen.introspect import LayoutRecorder

    beats = [
        {"text": "Night falls and it rains.", "actions": [{"particles": "rain"}]},
        {"text": "I see the lamp!", "actions": [{"say": "pip"}]},
        {"text": "Kit walks to the well while we look at pip.", "shot": "closeup pip", "actions": [{"walk_to": "kit", "to": {"column": 2, "row": 4}}]},
    ]
    wide = "\n".join(row + "." * 9 for row in POND.strip().splitlines()) + ("\n" + "." * 16) * 6   # characters small in it
    stage = {"idle": False, "background": "#BFE3F5", "iso": {**ISO, "map": wide}, "light": "night", "props": [{"prop": "gift", "at": "table"}],
             "characters": [{"name": "pip", "at": "start"}, {"name": "kit", "at": "table"}]}
    cast = [{**member, "voice": f"{member['name']}_voice"} for member in CAST]
    voices = {"pip_voice": {"voice_id": "pip_id", "label": "Pip"}, "kit_voice": {"voice_id": "kit_id"}}
    config = minimal_config(characters=cast, voices=voices, scenes=[{"id": "pond", "type": "stage", "params": stage, "beats": beats}])
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(Project.load(make_project(config)), "pond", tmp_path / "media", recorder)
    last = {frame["beat"]: frame for frame in recorder.frames}
    assert any(o["class"] == "GlowTile" for o in last["pond_b1"]["objects"])   # the lit lamp's light
    tile = GlowTile(np.zeros((2, 2, 4), dtype=np.uint8))
    tile.light_graded = True   # as mark_lit does to a lit group's members
    assert tile.light_graded is False   # never graded
    timings = scene.timings()
    assert {"crickets", "rain"} <= {bed["bed"] for bed in timings["ambience"]}
    pip = next(o for o in last["pond_b2"]["objects"] if o["kind"] == "character" and o["name"] == "pip")
    assert pip["speaking"] and pip.get("name_tag") and pip.get("features")
    assert any(o.get("name_tag") == "pip" for o in last["pond_b2"]["objects"] if o["kind"] != "character")
    assert last["pond_b2"]["line_words"] == 4
    (walk,) = last["pond_b3"]["iso_actions"]
    assert walk["who"] == "kit" and walk["action"] == "walk_to" and walk["seen"] < 0.5   # the close-up shows pip
    assert {"step_grass", "step_gravel"} & {cue["sound"] for cue in timings["sfx"]}
