"""Step 139: the built-in outdoor sets (``set: city_street`` ... without ``sets:``) and their props."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen.cartoon.props import FLAT_PROPS, OUTDOOR_PROPS, PROP_HEIGHTS, PROP_KINDS, draw_prop
from vidgen.cartoon.seating import PROP_SEATS, SEAT_PLACES
from vidgen.cartoon.stage import depth_scale, mark_x
from vidgen.cli import check_project
from vidgen.errors import VidgenError
from vidgen.includes import builtin_sets, expand_sets
from vidgen.project import Project
from vidgen.theme import Theme

OUTDOOR_SETS = ("city_street", "park", "beach", "forest", "snowy_hills")
#: How wide a character is, in its heights (generated characters are about this wide or less).
CHARACTER_WIDTH = 0.5
#: Depths closer than this stand side by side (lint's ``DEPTH_APART``).
SAME_DEPTH = 0.15


def two_on_marks(make_project: Any, set_name: str, params: dict[str, Any] | None = None, **config: Any) -> Project:
    """A project with one stage scene using ``set_name``, pip and kit on its two clear marks."""
    own = {"characters": [{"name": "pip", "at": "stand_left"}, {"name": "kit", "at": "stand_right"}], **(params or {})}
    scenes = [{"id": "s", "type": "stage", "set": set_name, "params": own, "beats": [{"text": "Two friends meet."}]}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes, **config)))


# ----- the library (no render) -------------------------------------------------------------------


def test_the_library_has_the_outdoor_sets() -> None:
    sets = builtin_sets()
    assert set(OUTDOOR_SETS) <= set(sets)
    sets["beach"]["light"] = "night"
    assert builtin_sets()["beach"]["light"] == "day"   # a copy each time
    assert set(OUTDOOR_PROPS) <= set(PROP_KINDS)


@pytest.mark.parametrize("name", OUTDOOR_SETS)
def test_each_set_validates_with_two_characters(name: str, make_project) -> None:
    params = stage_params(**builtin_sets()[name], characters=[{"name": "pip", "at": "stand_left"}, {"name": "kit", "at": "stand_right"}])
    assert params.props and params.marks.keys() >= {"stand_left", "stand_right"}
    project = two_on_marks(make_project, name)
    assert check_project(project) == []


def test_light_and_ambience_match_the_set() -> None:
    sets = builtin_sets()
    assert sets["city_street"]["ambience"] == "city"
    assert sets["park"]["ambience"] == sets["forest"]["ambience"] == "auto"   # birdsong by day (§69.62)
    assert sets["park"]["light"] == "day" and sets["forest"]["light"] == "morning"
    assert sets["beach"]["water"] == {"left": 0.0, "right": 0.3}
    (snow,) = sets["snowy_hills"]["particles"]
    assert snow["kind"] == "snow" and snow["settle"] and snow["settled"] * snow["density"] >= 24   # the full layer lies from the start


def _width_per_height(kind: str) -> float:
    prop = draw_prop(kind, height=1.0, theme=Theme())
    return float(prop.width)


@pytest.mark.parametrize("name", OUTDOOR_SETS)
def test_marks_are_inside_the_stage_and_clear_of_the_props(name: str) -> None:
    """The two characters on stand_left / stand_right stand clear of every prop standing near
    their depth, and the set's own props do not stand on each other (lint's prop_overlap)."""
    params = stage_params(**builtin_sets()[name])
    marks = params.marks
    assert all(0.05 <= x <= 0.95 for x in marks.values()), marks
    frame_width_in_heights = 16 / 9 / params.size   # a 16:9 frame's width, in a character's heights
    boxes: list[tuple[str, float, float, float]] = []   # name, depth, left x, right x (fractions of the stage)
    for prop, prop_name in zip(params.props, params.prop_names()):
        if prop.prop in FLAT_PROPS or prop.resolved_lift() > 0:
            continue
        half = _width_per_height(prop.prop) * prop.height_factor() * depth_scale(prop.depth) / frame_width_in_heights / 2
        x = mark_x(prop.at, marks)
        boxes.append((prop_name, prop.depth, x - half, x + half))
    for a, b in combinations(boxes, 2):
        if abs(a[1] - b[1]) >= SAME_DEPTH:
            continue
        shared = min(a[3], b[3]) - max(a[2], b[2])
        assert shared < 0.15 * min(a[3] - a[2], b[3] - b[2]), (a, b)
    half = CHARACTER_WIDTH / frame_width_in_heights / 2
    spots = [marks["stand_left"], marks["stand_right"]]
    assert spots[1] - spots[0] > 4 * half   # room between them for a speech bubble
    for x in spots:
        for prop_name, depth, left, right in boxes:
            if depth < SAME_DEPTH:
                assert right <= x - half or left >= x + half, (prop_name, x)


def test_new_props_build_seat_and_lie_flat() -> None:
    for kind in OUTDOOR_PROPS:
        prop = draw_prop(kind, height=1.0, theme=Theme())
        assert prop.height == pytest.approx(1.0) and prop.kind == kind
    assert {"road", "path"} <= FLAT_PROPS
    for kind in ("bench", "log"):
        assert PROP_HEIGHTS[kind] * PROP_SEATS[kind][1] == pytest.approx(0.14)   # a seat line at 0.14 of a character (§69.36)
        assert len(SEAT_PLACES[kind]) == 2
        bench = draw_prop(kind, height=2.0, theme=Theme())
        left, right = (bench.seat_point(k) for k in range(2))
        assert bench.get_left()[0] < left[0] < right[0] < bench.get_right()[0]


# ----- overriding (no render) --------------------------------------------------------------------


def test_scene_params_override_a_built_in_set(make_project) -> None:
    project = two_on_marks(make_project, "city_street", {
        "light": "night",                                         # replaced
        "marks": {"corner": 0.95},                                # merged
        "props": [{"name": "shop_2", "color": "tertiary"}, "ball"],   # the second shop changes, a ball is added
    })
    params = project.config.scenes[0].params
    assert params["light"] == "night" and params["ambience"] == "city"
    assert params["marks"]["corner"] == 0.95 and params["marks"]["bench"] == 0.5
    shops = [p for p in params["props"] if isinstance(p, dict) and p.get("prop") == "shop"]
    assert shops[1]["color"] == "tertiary" and shops[1]["at"] == 0.76 and params["props"][-1] == "ball"
    assert check_project(project) == []


def test_empty_lists_clear_and_a_picture_replaces_the_backdrop(make_project) -> None:
    project = two_on_marks(make_project, "snowy_hills", {"particles": [], "props": [], "background": "primary"})
    params = project.config.scenes[0].params
    assert params["particles"] == [] and params["props"] == [] and params["background"] == "primary"
    assert params["ground_color"] == builtin_sets()["snowy_hills"]["ground_color"]


def test_the_projects_own_set_of_that_name_wins(make_project) -> None:
    own = {"beach": {"background": "secondary", "marks": {"stand_left": 0.2, "stand_right": 0.8}}}
    project = two_on_marks(make_project, "beach", sets=own)
    params = project.config.scenes[0].params
    assert params["background"] == "secondary" and "water" not in params and "props" not in params


def test_built_in_values_keep_the_scenes_locations() -> None:
    data = {"scenes": [{"id": "a", "type": "stage", "set": "park", "params": {"props": ["ball"]}}]}
    expanded, origins = expand_sets(data, {})
    assert expanded["scenes"][0]["params"]["props"][-1] == "ball" and expanded["scenes"][0]["params"]["light"] == "day"
    assert all(not str(location).startswith("sets.") for location in (o.location for o in origins.values()))


def test_an_unknown_set_lists_the_built_in_ones(make_project) -> None:
    scenes = [{"id": "s", "type": "stage", "set": "beech", "params": {}, "beats": [{"text": "Hi."}]}]
    with pytest.raises(VidgenError, match=r"unknown set 'beech'; did you mean 'beach'\? sets: none .*built-in sets: city_street, park, beach, forest, snowy_hills"):
        Project.load(make_project(minimal_config(scenes=scenes)))


# ----- render ------------------------------------------------------------------------------------


@pytest.mark.render
@pytest.mark.parametrize("name", OUTDOOR_SETS)
def test_each_set_renders_lint_clean(name: str, make_project, tmp_path: Path) -> None:
    from vidgen.lint.cartoon_rules import character_overlap, hidden_speaker, off_stage, prop_overlap
    from vidgen.lint.rules import StillContext
    from vidgen.config import CharacterOverlapRule, HiddenSpeakerRule, OffStageRule, PropOverlapRule

    project = two_on_marks(make_project, name, {"idle": False})
    scene, objects = render_with_layout(project, "s", tmp_path / "media")
    assert set(scene.cast) == {"pip", "kit"} and len(scene.props) == len(builtin_sets()[name]["props"])
    ctx = StillContext(layout={"width": 160, "height": 90}, frame={"camera": {"zoom": 1.0}}, objects=objects)
    found = [*prop_overlap(ctx, PropOverlapRule()), *character_overlap(ctx, CharacterOverlapRule()),
             *off_stage(ctx, OffStageRule()), *hidden_speaker(ctx, HiddenSpeakerRule())]
    assert found == [], [issue.message for issue in found]
