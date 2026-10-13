"""Step 97: lighting and mood on a stage: the grade maths, fades, stars and shadows without
manim; the ``light`` action and param in ``vidgen validate``; two tiny renders (a sunset fading
to night with a speech bubble whose contrast lint still passes; a plain stage left as drawn)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES
from test_cartoon_stage import render_with_layout, stage_params, stage_project
from vidgen.cartoon.lighting import (
    LIGHT_PRESETS,
    SHADOW_FLATNESS,
    SHADOW_OPACITY,
    LightChange,
    LightGrade,
    blend_grades,
    grade_pixels,
    grade_rgbas,
    light_at,
    light_changing,
    light_grade,
    night_stars,
    shadow_ellipse,
    tint_grade,
)
from vidgen.cli import check_project
from vidgen.config import LintRules
from vidgen.lint import RULES, StillContext
from vidgen.particles import particle_seeds
from vidgen.project import Project

# ----- the grade (no manim) ----------------------------------------------------------------------


def test_presets_and_tints() -> None:
    day = light_grade("day")
    assert day == LightGrade() and not day.changes_colors
    for name in LIGHT_PRESETS[1:]:
        grade = light_grade(name)
        assert grade.changes_colors and all(0.0 < m <= 1.0 for m in grade.multiply), name
    night, sunset = light_grade("night"), light_grade("sunset")
    assert night.stars == 1.0 and night.shadow < 1.0 and night.multiply[2] > night.multiply[0]   # dark and blue
    assert sunset.stars == 0.0 and sunset.multiply[0] > sunset.multiply[2] and sunset.glow[0] > sunset.glow[2]   # warm
    assert tint_grade("#FFFFFF", 1.0) == LightGrade()
    assert tint_grade("#FF8000", 1.0).multiply == pytest.approx((1.0, 128 / 255, 0.0))
    assert tint_grade("#FF8000", 0.5).multiply == pytest.approx((1.0, 1 - 0.5 * (1 - 128 / 255), 0.5))
    assert tint_grade("#FF8000", 0.0) == LightGrade()
    with pytest.raises(ValueError, match="unknown light 'dusk'; presets: day, morning"):
        light_grade("dusk")


def test_grading_colours_and_pictures() -> None:
    night, sunset = light_grade("night"), light_grade("sunset")
    rgbas = np.array([[1.0, 1.0, 1.0, 0.5], [0.2, 0.4, 0.6, 1.0]])
    graded = grade_rgbas(rgbas, night)
    assert graded is not rgbas and rgbas[0, 0] == 1.0   # a new array
    assert graded[:, 3].tolist() == [0.5, 1.0]   # alpha unchanged
    assert graded[0, :3] == pytest.approx(night.multiply) and graded[1, :3] == pytest.approx(np.array([0.2, 0.4, 0.6]) * night.multiply)
    warm = grade_rgbas(np.array([[1.0, 1.0, 1.0, 1.0]]), sunset)
    assert warm[0, :3].max() <= 1.0 and warm[0, 0] == 1.0   # glow clipped at white
    assert grade_rgbas(np.zeros((0, 4)), night).shape == (0, 4)
    pixels = np.array([[[255, 255, 255, 128], [10, 20, 30, 255]]], dtype=np.uint8)
    graded_pixels = grade_pixels(pixels, night)
    assert graded_pixels.dtype == np.uint8 and graded_pixels[..., 3].tolist() == [[128, 255]]
    assert graded_pixels[0, 0, :3].tolist() == [round(255 * m) for m in night.multiply]
    assert grade_pixels(pixels, LightGrade()).tolist() == pixels.tolist()


def test_blends_and_fades() -> None:
    day, night = light_grade("day"), light_grade("night")
    assert blend_grades(day, night, 0.0) == day and blend_grades(day, night, 1.0) == night
    half = blend_grades(day, night, 0.5)
    assert half.multiply == pytest.approx(tuple((1 + m) / 2 for m in night.multiply)) and half.stars == 0.5
    fade = [LightChange(10.0, 2.0, night)]
    assert light_at(day, fade, 9.9) == day
    assert light_at(day, fade, 11.0).stars == pytest.approx(0.5)   # smoothstep: half-way at the middle
    assert light_at(day, fade, 10.5).stars == pytest.approx(0.15625)   # eased in
    assert light_at(day, fade, 12.0) == night and light_at(day, fade, 30.0) == night
    assert light_at(day, [LightChange(1.0, 0.0, night)], 1.0) == night   # at once
    # a change during another fades from where that one is then
    sunset = light_grade("sunset")
    both = [LightChange(10.0, 2.0, night), LightChange(11.0, 2.0, sunset)]
    mid = light_at(day, both[:1], 11.0)
    assert light_at(day, both, 11.0) == mid and light_at(day, both, 13.0) == sunset
    assert light_at(day, both, 12.0).stars == pytest.approx(mid.stars / 2)
    assert light_changing(fade, 9.0, 10.5) and light_changing(fade, 11.9, 20.0)
    assert not light_changing(fade, 0.0, 10.0) and not light_changing(fade, 12.0, 20.0)
    assert light_changing([LightChange(5.0, 0.0, night)], 4.0, 6.0) and not light_changing([LightChange(5.0, 0.0, night)], 5.0, 6.0)


def test_night_stars_reuse_the_sparkles() -> None:
    stars = night_stars(0.5)
    again = night_stars(0.5)
    assert len(stars) > 5 and stars.x.tolist() == again.x.tolist()   # seeded: every render the same
    assert stars.x.tolist() == particle_seeds("sparkles", len(stars), 1).x.tolist()
    assert len(night_stars(0.5, preview=True)) == (len(stars) + 1) // 2
    assert len(night_stars(1.0)) > len(stars)
    assert stars.brightness.min() >= 0.35 and stars.brightness.max() <= 1.0
    assert night_stars(0.5, seed=2).x.tolist() != stars.x.tolist()


def test_shadow_ellipses() -> None:
    ground = shadow_ellipse(1.0, -2.0, 0.8)
    assert (ground.x, ground.y, ground.width) == (1.0, -2.0, 0.8)
    assert ground.height == pytest.approx(0.8 * SHADOW_FLATNESS) and ground.opacity == pytest.approx(SHADOW_OPACITY)
    far = shadow_ellipse(1.0, -1.0, 0.8 * 0.55)   # a thing at the back: drawn smaller, so its shadow is
    assert far.width == pytest.approx(0.55 * ground.width) and far.height == pytest.approx(0.55 * ground.height)
    up = shadow_ellipse(1.0, -2.0, 0.8, above=1.0, size=2.0)   # half its height in the air
    assert up.y == -2.0 and up.width < ground.width and up.opacity < ground.opacity
    higher = shadow_ellipse(1.0, -2.0, 0.8, above=2.0, size=2.0)
    assert higher.width < up.width and higher.opacity < up.opacity
    assert shadow_ellipse(1.0, -2.0, 0.8, above=-0.1) == ground   # a little below (a crouch): as on the ground
    assert shadow_ellipse(1.0, -2.0, 0.8, strength=0.0).opacity == 0.0
    assert shadow_ellipse(1.0, -2.0, 0.8, strength=0.5).opacity == pytest.approx(SHADOW_OPACITY / 2)


# ----- config and validation ----------------------------------------------------------------------


def light_project(make_project, actions: list[Any], *, scene_type: str = "stage", params: dict[str, Any] | None = None) -> Project:
    if scene_type == "stage":
        params = {"characters": ["pip"], **(params or {})}
    else:
        params = {"text": "Hello"}
    scenes = [{"id": "s", "type": scene_type, "params": params, "beats": [{"text": "The sun goes down.", "actions": actions}]}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))


def test_validate_light_actions_and_param(make_project) -> None:
    good = [{"light": "night", "run_time": 3}, {"action": "light", "tint": "primary", "strength": 0.3, "at": 0.5}]
    assert check_project(light_project(make_project, good, params={"light": {"tint": "#FFAA66"}})) == []
    where = "scenes[0].beats[0].actions[0]"
    cases = [
        ({"light": "nigt"}, f"{where}.target: unknown light 'nigt'; did you mean 'night'?"),
        ({"light": "night", "tint": "#FF0000"}, f"{where}.tint: the light is given twice"),
        ({"action": "light"}, f"{where}.target: which light?"),
        ({"light": "night", "strength": 2}, f"{where}.strength"),
    ]
    for action, start in cases:
        problems = check_project(light_project(make_project, [action]))
        assert problems and all(p.startswith(start) for p in problems), (action, problems)
    problems = check_project(light_project(make_project, [{"light": "night"}], scene_type="text_card"))
    assert problems == [f"{where}.action: light is for stage scenes; a TextCard scene has no set to light"]
    params = stage_params(light={"tint": "#FFAA66"}, shadows=False)
    assert params.light.strength == 0.5 and params.shadows is False and stage_params().light == "day"
    with pytest.raises(Exception, match="dusk|day"):
        stage_params(light="dusk")


# ----- render ------------------------------------------------------------------------------------


@pytest.mark.render
def test_sunset_to_night_keeps_the_bubble_readable(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen import extensions, registry
    from vidgen.cartoon.shading import LIT, StageShadows, StarField
    from vidgen.introspect import LayoutRecorder

    params = {
        "background": ["#9CCBEA", "#E4F3FB"], "light": "sunset", "idle": False,
        "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}],
        "props": [{"prop": "cup", "at": 0.35}, {"prop": "tree", "at": 0.9, "depth": 0.5}, "cloud"],
    }
    beats = [
        {"id": "b1", "text": "Pip holds a cup while Kit jumps.", "voice": "pip_voice", "actions": [{"hold": "pip", "to": "cup"}, {"jump": "kit"}]},
        {"id": "b2", "text": "Night falls, and Kit says hi.", "voice": "kit_voice",
         "actions": [{"light": "night", "run_time": 0.6}, {"say": "kit", "bubble": "Hi there!"}]},
    ]
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": beats}]
    project = Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))
    recorder = LayoutRecorder()
    extensions.load_builtins()   # registry.get needs the built-ins imported; alone, no earlier test did it
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)   # no fade out: the stage stays to look at
    scene, _ = render_with_layout(project, "park", tmp_path / "media", recorder)

    night = light_grade("night")
    assert scene.light is not None and scene.light.grade == night   # the fade is over
    stage_class = registry.get("stage").cls   # and its updater is gone (Manim removes by identity)
    assert not any(getattr(f, "__func__", None) is stage_class._light_step for f in scene.updaters)
    sky = next(m for m in scene.mobjects if getattr(m, "name", None) == "background")
    camera = scene.renderer.camera
    assert camera.get_fill_rgbas(sky) == pytest.approx(grade_rgbas(sky.get_fill_rgbas(), night))   # graded as drawn
    assert sky.get_fill_rgbas()[0, :3] == pytest.approx([0x9C / 255, 0xCB / 255, 0xEA / 255])   # its colours untouched
    bubble = [m for m in scene.get_mobject_family_members() if getattr(m, "speech_bubble_of", None) == "kit"]
    assert bubble and not any(getattr(m, LIT, False) for b in bubble for m in b.get_family())
    plate = next(m for b in bubble for m in b.get_family() if len(m.points))
    assert np.array_equal(camera.get_fill_rgbas(plate), plate.get_fill_rgbas())   # bubbles are not graded

    stars = scene.stars
    assert isinstance(stars, StarField) and len(stars.submobjects) > 0
    assert max(s.get_fill_opacity() for s in stars.submobjects) > 0.3   # shown at night

    still, moving = scene.shadows
    assert isinstance(still, StageShadows) and isinstance(moving, StageShadows)
    assert [c.mobject.name for c in still.casters] == ["tree"]   # the cloud hangs: no shadow
    assert {c.mobject.name for c in moving.casters} == {"pip", "kit", "cup"}   # the cup can be held
    shadows = {c.mobject.name: s for c, s in zip(moving.casters, moving.submobjects)}
    assert shadows["cup"].submobjects[0].get_fill_opacity() == 0.0   # held: no shadow
    kit = scene.cast["kit"]
    ring = shadows["kit"].submobjects[0]
    assert ring.get_center()[0] == pytest.approx(kit.feet()[0], abs=1e-3)
    assert ring.get_fill_opacity() == pytest.approx(0.4 * SHADOW_OPACITY * night.shadow, abs=1e-6)
    width = ring.width
    kit.shift([0.0, 1.0, 0.0])   # in the air: smaller and fainter
    moving.follow()
    assert ring.width < width and ring.get_fill_opacity() < 0.4 * SHADOW_OPACITY * night.shadow

    names = {o.get("name") for f in recorder.frames for o in f["objects"]}
    assert "shadows" not in names and "stars" not in names   # not in the layout dump
    for frame in recorder.frames:   # the bubble's text keeps its contrast at night
        ctx = StillContext({"width": 160, "height": 90}, frame, frame["objects"])
        assert list(RULES["contrast"].check(ctx, LintRules().contrast)) == []
    assert any(o.get("bubble") == "kit" and o["kind"] == "text" for f in recorder.frames for o in f["objects"])

    # the set stays in Manim's static image, except while the light changes
    now = float(scene.renderer.time)
    assert sky not in scene.get_moving_mobjects()
    scene.light.change(light_grade("day"), now + 0.5, 1.0)
    assert sky in scene.get_moving_mobjects()


@pytest.mark.render
def test_plain_stage_is_drawn_as_it_was(make_project, tmp_path: Path) -> None:
    project = stage_project(make_project, {"characters": ["pip"], "props": ["box"], "shadows": False, "idle": False})
    scene, objects = render_with_layout(project, "park", tmp_path / "media")
    assert scene.light is None and scene.stars is None and scene.shadows == []
    assert "background" not in {o.get("name") for o in objects}   # no sky added: the theme's background as before
