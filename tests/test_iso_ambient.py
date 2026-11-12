"""Step 274: ambient life on an iso place (DESIGN.md §105.7) — where background walkers, birds, a
cat, ducks, butterflies and fireflies go (deterministic, away from the main characters), what
they look like, the stage's ``ambient`` setting and its checks, and a tiny render."""

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
from test_iso_staging import looks
from vidgen import extensions, registry
from vidgen.project import Project
from vidgen.world.iso import ObjectPlacing, parse_iso_map, place_objects
from vidgen.world.iso_ambient import (
    AMBIENT_DEFAULTS,
    AmbientPose,
    ambient_cells,
    ambient_counts,
    around,
    cell_route,
    picture_facing,
    plan_ambient,
)
from vidgen.world.iso_view import Box3

MAP = """
................
............~~~.
.....*......~~~.
::::::::::::::::
......s.........
..........g...&.
...*............
"""


def village() -> Any:
    return place_objects(parse_iso_map(MAP, names={"s": "square", "g": "gate"}),
                         [ObjectPlacing("house", (2, 1)), ObjectPlacing("tree", (16, 1)), ObjectPlacing("bench", (5, 7))])


def test_ambient_rules_do_not_import_manim() -> None:
    code = "import sys, vidgen.world.iso_ambient; assert 'manim' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


# ----- rules (no manim) ----------------------------------------------------------------------------------


def test_cells_keep_off_the_characters_and_roads() -> None:
    place = village()
    people = {(6, 4), (10, 5)}
    cells = ambient_cells(place, avoid=around(people), roads={(c, 3) for c in range(16)}, clear=around(people, 2))
    assert not cells.walk & around(people) and not any(r == 3 for _, r in cells.walk)   # nobody walks on the road
    assert (8, 4) not in cells.rest and (8, 4) in cells.walk   # near a character: passed, never stopped at
    assert len(cells.water) == 6 and cells.blooms and set(cells.air) >= {(5, 2)}
    assert (14, 2) in around([(12, 0)])   # two in front on the picture too
    way = cell_route(cells.walk, (12, 4), (15, 6), place=place)
    assert way is not None and way[0] == (12, 4) and way[-1] == (15, 6) and (14, 5) not in way   # round the bush
    assert cell_route(cells.walk, (0, 0), (15, 6), place=place) is None   # across the road
    assert cell_route({(0, 0), (2, 2)}, (0, 0), (2, 2)) is None


def test_the_same_seed_gives_the_same_life() -> None:
    place = village()
    cells = ambient_cells(place, avoid=around({(6, 4)}), clear=around({(6, 4)}, 2))
    counts = {"walker": 3, "bird": 3, "cat": 1, "duck": 2, "butterfly": 2, "firefly": 4}
    first, again = plan_ambient(place, cells, counts, 7), plan_ambient(place, cells, counts, 7)
    other = plan_ambient(place, cells, counts, 8)
    times = [0.0, 3.3, 17.5, 41.0]
    assert [[p.at(t) for t in times] for p in first] == [[p.at(t) for t in reversed(times)][::-1] for p in again]   # asked in any order
    assert [p.at(17.5) for p in first] != [p.at(17.5) for p in other]
    assert [p.name for p in first][:3] == ["ambient_walker_1", "ambient_walker_2", "ambient_walker_3"]
    for plan in first:
        poses = [plan.at(t / 4) for t in range(0, 240)]
        assert all(pose is not None for pose in poses)
        if plan.kind in ("walker", "cat"):
            assert all((int(p.point[0]), int(p.point[1])) in cells.walk for p in poses)
            stops = {(int(p.point[0]), int(p.point[1])) for p in poses if p.action in ("stand", "sit", "groom")}
            assert stops <= cells.rest | {(int(plan.at(0).point[0]), int(plan.at(0).point[1]))}
        if plan.kind == "duck":
            assert all((int(p.point[0]), int(p.point[1])) in cells.water for p in poses)
    walkers = [p.at(0.0).point for p in first if p.kind == "walker"]
    assert len({(int(x), int(y)) for x, y, _ in walkers}) == 3   # they start spread out


def test_birds_peck_hop_and_fly_off_and_fireflies_blink() -> None:
    place = village()
    cells = ambient_cells(place)
    bird = plan_ambient(place, cells, {"bird": 1}, 3)[0]
    poses = [bird.at(t / 5) for t in range(0, 600)]
    actions = {p.action for p in poses}
    assert {"peck", "hop", "fly"} <= actions
    flying = [p for p in poses if p.action == "fly"]
    assert max(p.point[2] for p in flying) > 1.5
    if "gone" in actions:   # flown out of the place: faded out, back later
        assert all(p.shown == 0.0 for p in poses if p.action == "gone")
    fly = plan_ambient(place, cells, {"firefly": 1}, 3)[0]
    glows = [fly.at(t / 10).glow for t in range(0, 100)]
    assert min(glows) < 0.2 < 0.8 < max(glows)
    assert picture_facing((0, 0), (1, 0), -1) == 1 and picture_facing((0, 0), (0, 1), 1) == -1 and picture_facing((0, 0), (1, 1), -1) == -1


def test_counts_from_the_setting() -> None:
    assert ambient_counts({"walkers": True, "birds": 2, "cat": False}, False) == {"walker": AMBIENT_DEFAULTS["walkers"], "bird": 2}
    assert ambient_counts({"walkers": 3, "cat": True, "flies": True}, True) == {"cat": 1, "fly": 1}   # indoors a cat and flies
    room = place_objects(parse_iso_map("#####\n#...#\n#.s.#\n#...#", names={"s": "middle"}, place="indoor"), [])
    assert plan_ambient(room, ambient_cells(room), {"duck": 1}, 1) == []   # no water: no duck


# ----- drawing --------------------------------------------------------------------------------------------


def test_every_kind_is_drawn_and_hides_when_not_seen() -> None:
    from vidgen.cartoon.iso_ambient import IsoCritter, critter_look, critter_shapes
    from vidgen.cartoon.iso_driving import draw_sprite
    from vidgen.cartoon.iso_stage import iso_view

    place = village()
    cells = ambient_cells(place)
    plans = plan_ambient(place, cells, {"walker": 1, "bird": 1, "cat": 1, "duck": 1, "butterfly": 1, "firefly": 1}, 2)
    assert {p.kind for p in plans} == {"walker", "bird", "cat", "duck", "butterfly", "firefly"}
    muted, bright = critter_look("walker", 5, muted=True), critter_look("walker", 5)
    assert muted.scale < bright.scale and muted.main != bright.main
    for action in ("walk", "stand", "sit", "groom", "peck", "fly", "dip", "flutter", "rest", "hover"):
        for plan in plans:
            sprite = draw_sprite(critter_shapes(plan.kind, critter_look(plan.kind, 1), AmbientPose((0.0, 0.0, 0.0), -1, action, 0.3), 1), 40.0, outline=1.0)
            assert sprite.pixels[0] is not None and sprite.pixels[0][..., 3].max() > 0
    firefly = draw_sprite(critter_shapes("firefly", critter_look("firefly", 1), AmbientPose((0.0, 0.0, 0.0), 1, "hover", 0.0), 0), 40.0, outline=1.0)
    assert firefly.pixels[1] is not None and firefly.pixels[2] is not None   # a halo (a pool of light) and its light
    view = iso_view(place, 8 * 16 / 9, 8.0)
    seen = [1.0]
    walker = IsoCritter(plans[0], critter_look("walker", 1), view, scale=40.0, density=1.0, frame_width=8 * 16 / 9, seen=lambda now: seen[0])
    walker.update_to(2.0)
    assert walker.rect() is not None and walker.slots[0].pixel_array.shape[0] > 1
    box = walker.box()
    assert box.z1 - box.z0 > 1.0 and int(box.x0) == walker.cell()[0]
    seen[0] = 0.0   # a close shot
    walker.update_to(2.1)
    assert walker.rect() is None and walker.slots[0].pixel_array.shape[0] == 1
    region = walker.region(0.0, 10.0)
    assert region[0] < region[2] and region[1] < region[3]


def test_walkers_have_faces() -> None:
    """Step 275: a background walker has a face of dots (an eye, a smile's end), muted or not."""
    from vidgen.cartoon.iso_ambient import INK, critter_look, walker_shapes
    from vidgen.cartoon.iso_drawing import Blobs

    for muted in (True, False):
        shapes = walker_shapes(critter_look("walker", 3, muted=muted), facing=1, swing=0.0)
        dots = [s for s in shapes if isinstance(s, Blobs) and not s.ink and s.radii[0] < 0.03]
        assert len(dots) == 2 and dots[0].fill == INK and shapes[-2:] == dots   # drawn over the head


def test_a_front_picture_from_pieces_found_already() -> None:
    from vidgen.cartoon.iso_scenery import IsoColors
    from vidgen.cartoon.iso_stage import IsoScenery, iso_view

    place = village()
    scenery = IsoScenery(place, IsoColors(), looks(place), iso_view(place, 8 * 16 / 9, 8.0), 20.0)
    box = Box3(1.3, 0.3, 0.0, 1.7, 0.7, 1.5)   # behind the house
    assert scenery.front(box, over=scenery.over(box)) == scenery.front(box) is not None
    assert scenery.front(box, over=()) is None


# ----- the stage's setting and its checks ----------------------------------------------------------------------

ISO = {"map": MAP, "spots": {"s": "square", "g": "gate"}, "objects": [{"object": "house", "at": {"column": 2, "row": 1}}]}


def stage_params(**params: Any) -> Any:
    from vidgen.scenes.stage import Stage

    return Stage.Params.model_validate({"iso": {**ISO, **params.pop("iso", {})}, **params})


@pytest.mark.slow
def test_the_ambient_setting() -> None:
    from vidgen.config import validation_problems
    from vidgen.scenes.stage import Stage

    everything = stage_params(ambient=True).ambient
    assert everything.auto and set(everything.counts(indoor=False)) == {"walkers", "birds", "cat", "ducks", "butterflies", "fireflies"}
    assert set(everything.counts(indoor=True)) == {"cat", "flies"}
    given = stage_params(ambient={"walkers": 5, "cat": True, "seed": 3, "muted": False}).ambient
    assert given.counts(indoor=False) == {"walkers": 5, "cat": True} and given.seed == 3 and not given.muted
    with pytest.raises(ValidationError, match="leave ambient out"):
        stage_params(ambient=False)
    with pytest.raises(ValidationError, match="less than or equal to 8"):
        stage_params(ambient={"walkers": 20})
    with pytest.raises(ValidationError) as typo:
        stage_params(ambient={"walker": 3})
    assert "did you mean 'walkers'" in str(validation_problems(typo.value, (), Stage.Params)[0])
    room = {"place": "indoor", "map": "#####\n#...#\n#.s.#", "spots": {"s": "middle"}, "objects": []}
    with pytest.raises(ValidationError, match="birds live outdoors"):
        stage_params(iso=room, ambient={"birds": 2})
    assert stage_params(iso=room, ambient={"cat": True, "flies": 2}).ambient.flies == 2
    with pytest.raises(ValidationError, match="ducks swim on water"):
        stage_params(iso={"map": "....\n..s.", "spots": {"s": "middle"}, "objects": []}, ambient={"ducks": 2})
    with pytest.raises(ValidationError, match="ambient life goes about an iso place"):
        Stage.Params.model_validate({"ambient": True})


# ----- a tiny render ------------------------------------------------------------------------------------------


def ambient_project(make_project, beats: list[dict[str, Any]], **params: Any) -> Project:
    params = {"idle": False, "iso": ISO, "characters": [{"name": "pip", "at": "square"}, {"name": "kit", "at": "gate"}], **params}
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


@pytest.mark.slow
@pytest.mark.render
def test_ambient_life_on_a_village(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    beats = [{"text": "The village goes about its day."}, {"text": "Pip says hello.", "shot": "closeup pip"}]
    project = ambient_project(make_project, beats, ambient={"walkers": 2, "birds": 2, "cat": True, "ducks": 1, "seed": 1})
    scene, frames = frames_of(project, tmp_path / "ambient", monkeypatch)
    critters = scene.iso_critters
    assert {c.kind for c in critters.values()} == {"walker", "bird", "cat", "duck"}
    assert all(c in scene.mobjects and c in scene.story_things for c in critters.values())
    order = [scene.mobjects.index(m) for m in [*scene.cast.values(), *critters.values()]]
    assert len(set(order)) == len(order)
    assert all(c.shown == 0.0 for c in critters.values())   # the scene ends on a close-up: none shown
    assert "ambient_walker_1" not in scene.target_names(scene.params)   # no action targets
    assert len(frames) > 10 and max(np.abs(b.astype(int) - a.astype(int)).max() for a, b in zip(frames[2:8], frames[3:9])) > 0


RIVER = """
................
~~~~~~~~~~~~~~~~
~~~~~~~~~~~~~~~~
~~~~~~~~~~~~~~~~
~~~~~~~~~~~~~~~~
::::::::::::::::
......s.........
..........g.....
"""


@pytest.mark.slow
@pytest.mark.render
def test_walkers_pick_up_lamplight_and_ducks_keep_off_a_boats_way(make_project, tmp_path: Path, monkeypatch) -> None:
    """Step 275: at night a lamp lights the walkers and the cat near it as it lights the
    characters; ducks never swim where a sailing boat goes."""
    from vidgen.cartoon.shading import LAMP_LIT

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    iso = {"map": RIVER, "spots": {"s": "square", "g": "gate"},
           "objects": [{"object": "lamp", "at": {"column": 9, "row": 7}, "on": True}, {"object": "boat", "at": {"column": 1, "row": 2}}]}
    beats = [{"text": "The boat sails down the river at night.", "actions": [{"sail_to": "boat", "to": {"column": 14, "row": 2}}]}]
    project = ambient_project(make_project, beats, iso=iso, light="night", ambient={"walkers": 2, "cat": True, "ducks": 2, "seed": 2})
    scene, _ = frames_of(project, tmp_path / "river", monkeypatch)
    critters = scene.iso_critters
    lit = {c.kind: getattr(c.slots[0], LAMP_LIT, None) is not None for c in critters.values()}
    assert lit["walker"] and lit["cat"] and not lit["duck"]
    lanes = scene._ambient_lanes(scene.params.iso.parsed())
    assert {(c, 1) for c in range(2, 13)} <= lanes
    ducks = [c for c in critters.values() if c.kind == "duck"]
    assert ducks and all((int(p.point[0]), int(p.point[1])) not in lanes for d in ducks for p in d.plan.samples(0.0, 6.0))
