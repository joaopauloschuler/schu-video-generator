"""Step 76: particles (rain, snow, sparkles, dust, confetti, smoke, bubbles) as a beat action on
any scene type and as a ``stage`` param; seeded positions, the count cap, fewer at preview."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_stage import render_with_layout, stage_params, stage_project
from vidgen.cli import check_project
from vidgen.helpers import fade_out
from vidgen.lint.layout_rules import describe
from vidgen.particle_field import FADE_IN, ParticleField, ParticleSettings, particle_colors, particle_field
from vidgen.particles import (
    KINDS,
    MAX_PARTICLES,
    PARTICLE_KINDS,
    PREVIEW_SHARE,
    check_area,
    particle_count,
    particle_seeds,
    particle_states,
)
from vidgen.project import Project
from vidgen.theme import Theme

# ----- the pure model (no manim) ------------------------------------------------------------------


def test_every_kind_has_a_table_entry() -> None:
    assert set(KINDS) == set(PARTICLE_KINDS) and len(PARTICLE_KINDS) == 7


@pytest.mark.parametrize("kind", PARTICLE_KINDS)
def test_seeded_positions_repeat(kind: str) -> None:
    first = particle_states(particle_seeds(kind, 40, seed=7, colors=3), 2.5, width=1.78, height=1.0)
    again = particle_states(particle_seeds(kind, 40, seed=7, colors=3), 2.5, width=1.78, height=1.0)
    other = particle_states(particle_seeds(kind, 40, seed=8, colors=3), 2.5, width=1.78, height=1.0)
    for name in ("x", "y", "size", "angle", "flip", "opacity"):
        assert np.array_equal(getattr(first, name), getattr(again, name))
    assert not np.allclose(first.x, other.x)
    assert ((first.x >= 0) & (first.x < 1) & (first.y >= 0) & (first.y < 1)).all()
    assert ((first.opacity >= 0) & (first.opacity <= 1)).all() and (first.size > 0).all()


def test_seeded_positions_fixed_values() -> None:
    """The stream itself is fixed: a change to it moves every rendered particle."""
    seeds = particle_seeds("snow", 3, seed=1)
    assert seeds.x == pytest.approx([0.3318724, 0.611896, 0.5076327], abs=1e-6)
    assert seeds.y == pytest.approx([0.1562982, 0.8040317, 0.0188639], abs=1e-6)


def test_rain_falls_smoke_rises_and_both_wrap() -> None:
    rain = particle_seeds("rain", 20, seed=2)
    t = 0.05
    moved = particle_states(rain, t).y - particle_states(rain, 0.0).y
    expected = KINDS["rain"].fall * rain.speed * t
    assert np.allclose(np.mod(moved, 1.0), np.mod(expected, 1.0))   # down, by speed x time
    assert particle_states(rain, 0.0).angle == pytest.approx(math.atan2(KINDS["rain"].drift, KINDS["rain"].fall))
    smoke = particle_seeds("smoke", 20, seed=2)
    rise = particle_states(smoke, t).y - particle_states(smoke, 0.0).y
    assert np.all(np.mod(rise, 1.0) > 0.5)   # up (y from the top falls), wrapped into 0..1
    later = particle_states(rain, 1000.0)
    assert ((later.y >= 0) & (later.y < 1)).all()
    puffs = particle_states(smoke, 0.0)
    life = 1.0 - puffs.y
    assert puffs.size == pytest.approx(smoke.size * (1.0 + (KINDS["smoke"].grow - 1.0) * life))   # grows as it rises
    assert puffs.opacity.max() <= KINDS["smoke"].opacity


def test_confetti_spins_and_sparkles_twinkle() -> None:
    confetti = particle_seeds("confetti", 10, seed=3)
    assert not np.allclose(particle_states(confetti, 0.0).angle, particle_states(confetti, 0.3).angle)
    assert (np.abs(particle_states(confetti, 0.3).flip) <= 1).all()
    sparkles = particle_seeds("sparkles", 10, seed=3)
    opacities = np.array([particle_states(sparkles, t).opacity for t in np.linspace(0, 4, 41)])
    assert opacities.min() < 0.05 and opacities.max() > 0.5   # on and off


def test_count_scales_and_is_capped() -> None:
    assert particle_count("snow") == KINDS["snow"].count
    assert particle_count("snow", density=2.0) == 2 * KINDS["snow"].count
    assert particle_count("snow", area_share=0.5) == KINDS["snow"].count // 2
    assert particle_count("rain", density=4.0) == MAX_PARTICLES   # 640 wanted
    assert particle_count("rain", density=4.0, preview=True) == math.ceil(MAX_PARTICLES * PREVIEW_SHARE)
    assert particle_count("snow", preview=True) == math.ceil(KINDS["snow"].count * PREVIEW_SHARE)
    assert particle_count("smoke", density=0.1, area_share=0.01) == 1
    with pytest.raises(ValueError, match="unknown particles 'hail'"):
        particle_count("hail")


def test_area_checks() -> None:
    assert check_area([0.0, 0.5, 1.0, 0.5]) == [0.0, 0.5, 1.0, 0.5]
    for bad, message in (([0, 0, 1], r"\[x, y, w, h\]"), ([0, 0, 0, 1], "above 0"), ([0.5, 0, 0.6, 1], "inside the frame"), ([0, 0, 1.2, 1], "from 0 to 1")):
        with pytest.raises(ValueError, match=message):
            check_area(bad)


# ----- the field (manim objects, no render) -------------------------------------------------------


def fake_scene(preview: bool = False, time: float = 0.0) -> Any:
    """What :func:`particle_field` reads of a scene: theme, frame, renderer time, camera."""
    frame = SimpleNamespace(width=16.0, height=9.0, get_center=lambda: np.zeros(3))
    return SimpleNamespace(
        theme=Theme(), frame_width=16.0, frame_height=9.0, is_preview=preview, renderer=SimpleNamespace(time=time),
        camera=SimpleNamespace(frame=frame), get_mobject_family_members=lambda: [],
    )


def test_field_places_particles_in_its_area_and_fades_in() -> None:
    scene = fake_scene(time=10.0)
    field = particle_field(scene, "snow", ParticleSettings(area=[0.5, 0.0, 0.5, 0.5], seed=4))
    assert isinstance(field, ParticleField) and field.name == "snow" and len(field) == particle_count("snow", area_share=0.25)
    centres = np.array([p.get_center() for p in field])
    assert (centres[:, 0] > -0.1).all() and (centres[:, 1] > -0.1).all()   # the top-right quarter (x 0..8, y 0..4.5)
    assert max(p.get_fill_opacity() for p in field) == 0.0   # starts transparent
    scene.renderer.time = 10.0 + FADE_IN
    field.update(0.2)
    states = particle_states(field.seeds, FADE_IN, width=8.0 / 9.0, height=4.5 / 9.0)
    assert [p.get_fill_opacity() for p in field] == pytest.approx(states.opacity.tolist(), abs=1e-6)
    assert field[0].get_center()[0] == pytest.approx(8.0 * states.x[0], abs=0.05)


def test_field_has_fewer_particles_at_preview_and_its_colours() -> None:
    final = particle_field(fake_scene(), "confetti", ParticleSettings())
    preview = particle_field(fake_scene(preview=True), "confetti", ParticleSettings())
    assert len(preview) == math.ceil(len(final) * PREVIEW_SHARE) < len(final)
    theme = Theme()
    assert particle_colors("confetti", None, theme) == [theme.color(c) for c in KINDS["confetti"].colors]
    assert particle_colors("rain", ["primary", "#123456"], theme) == [theme.color("primary"), "#123456"]


def test_fade_out_keeps_the_field_moving_and_ends_at_zero() -> None:
    scene = fake_scene()
    field = particle_field(scene, "rain", ParticleSettings())
    animation = fade_out(field)
    assert type(animation).__name__ == "_FieldFadeOut" and animation.remover
    field.suspend_updating()
    assert not field.updating_suspended   # moves while the fade plays
    scene.renderer.time = 1.0
    animation.interpolate_mobject(1.0)
    assert field.level == 0.0 and max(p.get_fill_opacity() for p in field) == 0.0


# ----- config and validation ----------------------------------------------------------------------


def project_with_actions(make_project, actions: list[Any], **beat: Any) -> Project:
    scenes = [{"id": "card", "type": "text_card", "params": {"text": "Hello"},
               "beats": [{"id": "one", "text": "It starts to snow.", "actions": actions, **beat}, {"id": "two", "text": "Then it stops."}]}]
    return Project.load(make_project(minimal_config(scenes=scenes)))


def test_validate_particles_actions(make_project) -> None:
    good = [{"particles": "snow"}, {"action": "particles", "kind": "rain", "density": 2, "area": [0, 0, 1, 0.5], "color": ["primary", "#FFFFFF"], "keep": True}]
    assert check_project(project_with_actions(make_project, good)) == []
    where = "scenes[0].beats[0].actions[0]"
    cases = [
        ({"particles": "snw"}, f"{where}.target: unknown particles 'snw'; did you mean 'snow'?"),
        ({"particles": "snow", "kind": "rain"}, f"{where}.kind: the kind is given twice"),
        ({"action": "particles"}, f"{where}.target: which particles?"),
        ({"particles": "snow", "keep": True, "until": "two"}, f"{where}.keep: keep: stays"),
        ({"particles": "snow", "area": [0, 0, 2, 1]}, f"{where}.area"),
        ({"particles": "snow", "density": 9}, f"{where}.density"),
        ({"particles": "snow", "color": "nocolor"}, f"{where}.color"),
    ]
    for action, start in cases:
        problems = check_project(project_with_actions(make_project, [action]))
        assert problems and all(p.startswith(start) for p in problems), (action, problems)   # a colour: one problem per accepted form


def test_stage_particles_param() -> None:
    params = stage_params(particles=["snow", {"kind": "rain", "density": 0.5, "area": [0, 0, 1, 0.5], "seed": 3}])
    assert [(p.kind, p.density, p.seed) for p in params.particles] == [("snow", 1.0, 1), ("rain", 0.5, 3)]
    with pytest.raises(Exception, match="kind"):
        stage_params(particles=[{"density": 2}])
    with pytest.raises(Exception, match="hail"):
        stage_params(particles=["hail"])


def test_lint_names_particles() -> None:
    assert describe({"kind": "particles", "class": "ParticleField", "name": "snow", "path": "snow"}) == "particles 'snow'"


# ----- render ------------------------------------------------------------------------------------


@pytest.mark.render
def test_particles_action_on_a_text_card(make_project, tmp_path: Path) -> None:
    project = project_with_actions(make_project, [{"particles": "confetti"}])
    scene, objects = render_with_layout(project, "card", tmp_path / "media")
    fields = [obj for obj in objects if obj["kind"] == "particles"]
    assert [f["name"] for f in fields] == ["confetti"] and fields[0]["parts"] > 10
    assert not any(isinstance(m, ParticleField) for m in scene.mobjects)   # faded out when beat two started


@pytest.mark.render
def test_stage_particles_render(make_project, tmp_path: Path) -> None:
    project = stage_project(make_project, {"idle": False, "characters": ["pip"], "particles": [{"kind": "snow", "density": 0.3}]})
    scene, objects = render_with_layout(project, "park", tmp_path / "media")
    assert [f.name for f in scene.particles] == ["snow"] and len(scene.particles[0]) == particle_count("snow", 0.3)
    snow = next(obj for obj in objects if obj["kind"] == "particles")
    pip = next(obj for obj in objects if obj["name"] == "pip")
    assert snow["name"] == "snow" and snow["z"] > pip["z"]   # drawn in front of the characters
