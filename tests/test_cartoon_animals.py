"""Step 114: original animal characters (``look.species``) and the ``tail`` part, and the pinned
drawings of the human looks made before it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_outfits import PIN_COLORS, PINNED_DIGESTS, PINNED_LOOKS, drawing_digest
from vidgen.cartoon.acting import walk_cycle
from vidgen.cartoon.animals import BEAK_OPENINGS, fur_tint, is_animal
from vidgen.cartoon.cast import GENERATED_SHAPES, character_lines, character_part_shapes
from vidgen.cartoon.character import OUTER_HAIR_ATTRIBUTE, REQUIRED_PARTS, TRAIL_ATTRIBUTE, Character
from vidgen.cartoon.effect_symbols import crown_top, head_box
from vidgen.cartoon.generator import generate_parts
from vidgen.cartoon.idle import tail_sway_angle
from vidgen.cartoon.motion import FOLLOW_TAIL_LIMIT, follow_angles
from vidgen.cartoon.poses import POSE_PARTS
from vidgen.cartoon.svg_look import default_pivot, svg_character_parts
from vidgen.cartoon.transition import Walk, walking_state
from vidgen.config import CharacterEntry, CharacterLook
from vidgen.lint.color import hex_rgb, relative_luminance
from vidgen.project import Project
from vidgen.theme import Theme

SPECIES = ("cat", "dog", "bird", "bear", "rabbit", "mouse")
#: Looks of Step 113 whose drawings must not change: :func:`drawing_digest` (side, front) taken
#: at HEAD 96dfd2b before Step 114 (the five screenplay looks it added, two kids).
PINNED_113: dict[str, tuple[dict[str, Any], tuple[str, str]]] = {
    "screenplay_7": ({"body": "pear", "head_size": 1.05, "eyes": "oval", "hair": "ponytail", "outfit": "dress", "pattern": "dots",
                      "shoes": "shoes", "accessories": ["necklace"]}, ("d124de522c601d72", "04d77f66b8011842")),
    "screenplay_8": ({"body": "triangle", "eyes": "dot", "nose": "round", "hair": "none", "facial_hair": "beard", "outfit": "coat",
                      "shoes": "boots", "accessories": ["cap"]}, ("232319e1d666a6d3", "70179cf565c202f4")),
    "screenplay_9": ({"body": "bean", "head_size": 1.2, "eyes": "round", "hair": "afro", "outfit": "overalls", "pattern": "stripes",
                      "accessories": ["backpack"]}, ("a25f5c5279d8ccd2", "63cad20d26e9cc45")),
    "screenplay_10": ({"body": "square", "eyes": "sleepy", "nose": "triangle", "hair": "braids", "outfit": "apron", "shoes": "shoes",
                       "accessories": ["bow"]}, ("29677afb691b0145", "a5317c082a88b846")),
    "screenplay_11": ({"body": "round", "eyes": "oval", "hair": "short", "facial_hair": "moustache", "outfit": "shorts",
                       "pattern": "stripes", "shoes": "shoes"}, ("b0376513f65ebe7d", "a47f439a15a7e693")),
    "kid": ({"proportions": "kid", "hair": "ponytail", "outfit": "dress", "pattern": "dots", "shoes": "shoes"},
            ("548d839d9a3ad173", "fa8583600b8ad0a1")),
    "tall_kid": ({"proportions": "tall_kid", "body": "tall", "outfit": "coat", "accessories": ["necklace", "backpack"], "seed": 3},
                 ("650668deff1c4c81", "ed3d50a8d112282a")),
}


@pytest.mark.parametrize("name", [*PINNED_LOOKS, *PINNED_113])
def test_humans_keep_their_drawings(name: str) -> None:
    values, digests = PINNED_113[name] if name in PINNED_113 else (PINNED_LOOKS[name], PINNED_DIGESTS[name])
    look = CharacterLook(**values)
    assert (drawing_digest(look), drawing_digest(look, front=True)) == digests


#: Animals of Step 114 whose drawings must not change: :func:`drawing_digest` (side, front) taken
#: at HEAD ddfeaf6 before Step 123.
PINNED_114: dict[str, tuple[dict[str, Any], tuple[str, str]]] = {
    "cat": ({"species": "cat"}, ("4eb837539a5f81ef", "a97f153b2ea57bfe")),
    "dog": ({"species": "dog", "outfit": "coat", "shoes": "boots"}, ("44314e01632845a1", "b66b1091b8c8f26c")),
    "bird": ({"species": "bird", "outfit": "dress"}, ("263cd04fa8a77f1f", "795f89264f08aaee")),
    "bird_shoes": ({"species": "bird", "outfit": "shorts", "shoes": "shoes", "accessories": ["scarf"]}, ("a2f5b254e6ec0586", "51d5831c4dd7543a")),
    "bear": ({"species": "bear", "outfit": "apron", "body": "square"}, ("f19ac80e9330d3f0", "c3c0a770706e8935")),
    "rabbit": ({"species": "rabbit", "outfit": "dress", "pattern": "stripes", "eyes": "oval"}, ("c880cecf5b130157", "a9e375c41ad173c4")),
    "mouse": ({"species": "mouse", "hair": "short", "accessories": ["backpack"], "seed": 4}, ("326bf7368f90ea49", "32c611ba9c12e314")),
}


@pytest.mark.parametrize("name", PINNED_114)
def test_step_114_animals_keep_their_drawings(name: str) -> None:
    values, digests = PINNED_114[name]
    look = CharacterLook(**values)
    assert (drawing_digest(look), drawing_digest(look, front=True)) == digests


def animal(species: str, height: float = 1.0, **look: Any) -> Character:
    values = CharacterLook(species=species, **look)
    return Character(generate_parts(values, PIN_COLORS), name=species, height=height, front=generate_parts(values, PIN_COLORS, front=True))


# ----- each species builds and poses -----------------------------------------------------------------


@pytest.mark.parametrize("species", SPECIES)
def test_each_species_builds_and_poses(species: str) -> None:
    c = animal(species, height=2.0, outfit="shorts", shoes="none")
    assert set(REQUIRED_PARTS) | {"tail"} <= set(c.parts)
    assert c.draw_order[0] == "tail"   # behind everything
    assert c.get_bottom()[1] == pytest.approx(0.0, abs=1e-6) and c.get_top()[1] == pytest.approx(2.0)
    entry = CharacterEntry(name="t", look={"species": species, "outfit": "shorts"})
    assert {part: c.shape_names(part) for part in c.parts} == character_part_shapes(entry, Path("."))   # validate knows the tail
    assert c.shape_names("mouth") == GENERATED_SHAPES["mouth"]   # every viseme, for lip sync
    for pose in ("waving", "pointing", "thinking", "shrug", "arms_crossed", "sitting"):
        c.set_pose(pose)
    c.set_pose("stand")
    hand = c.hand_point("left")
    c.reach("left", hand + np.array([0.3, 0.4, 0.0]))
    c.set_state(c.seated(c.posed_state(pose="stand"), 0.14))
    hips = (c.pivot("leg_left")[1] - c.feet()[1]) / c.character_height
    assert hips == pytest.approx(0.14, abs=1e-6)
    c.set_state(walking_state(c.posed_state(pose="stand"), walk_cycle(0.5), "right"))
    c.face("front").set_state(walking_state(c.state(), walk_cycle(1.5), "front"))
    c.face("left").set_expression("surprised")
    assert "tail" in POSE_PARTS


def test_species_differ_and_change_the_head() -> None:
    digests = {drawing_digest(CharacterLook(species=s)) for s in ("human", *SPECIES)}
    assert len(digests) == 7
    human = animal("human")
    assert not human.has_part("tail") and not is_animal(CharacterLook())
    for species in SPECIES:
        c = animal(species)
        head = c.parts["head"].family_members_with_points()
        assert len(head) > len(human.parts["head"].family_members_with_points())   # ears, muzzle or beak, nose
        assert any(getattr(m, OUTER_HAIR_ATTRIBUTE, False) for m in head)   # ears, a snout or a beak beyond the head


def test_paws_and_wings() -> None:
    human, cat, bird = animal("human"), animal("cat"), animal("bird")
    assert len(cat.parts["arm_left_lower"].family_members_with_points()) == len(human.parts["arm_left_lower"].family_members_with_points()) + 2
    wing = bird.part_box("arm_left_lower")
    assert wing[2] - wing[0] > human.part_box("arm_left_lower")[2] - human.part_box("arm_left_lower")[0]   # wider than an arm
    feathers = {m.get_fill_color().to_hex().upper() for m in bird.parts["arm_left"].family_members_with_points()}
    assert feathers == {PIN_COLORS["skin"]}   # a wing is feathers, not a sleeve
    bare = animal("bird", outfit="dress")
    assert len(bare.parts["leg_left_lower"].family_members_with_points()) == 4   # a thin shin and three toes from the side


def test_look_schema() -> None:
    with pytest.raises(ValidationError, match="draws its own ears"):
        CharacterLook(species="cat", ears="pointy")
    with pytest.raises(ValidationError, match="facial_hair"):
        CharacterLook(species="dog", facial_hair="beard")
    with pytest.raises(ValidationError, match="svg draws the character"):
        CharacterLook(svg="a.svg", species="cat")
    assert CharacterLook(species="cat", ears="none", hair="short", accessories=["cap", "scarf"]).species == "cat"
    lines = character_lines(CharacterEntry(name="tib", look={"species": "rabbit"}), Theme())
    assert lines[1].startswith("  look:   species rabbit, body round")
    assert character_lines(CharacterEntry(name="pip"), Theme())[1].startswith("  look:   body round")
    assert relative_luminance(hex_rgb(fur_tint("#5A3B22"))) > relative_luminance(hex_rgb("#5A3B22"))


# ----- lip sync on muzzles and beaks -----------------------------------------------------------------


@pytest.mark.parametrize("species", ("cat", "dog", "bear", "rabbit", "mouse", "fox", "frog", "turtle"))
def test_the_mouth_sits_on_the_muzzle_and_opens(species: str) -> None:
    for front in (False, True):
        c = animal(species)
        if front:
            c.face("front")
        head = c.part_box("head")
        sizes = {}
        for shape in ("smile", "A", "O", "M"):
            c.swap("mouth", shape)
            left, bottom, right, top = c.part_box("mouth")
            assert head[0] < left and right < head[2] and head[1] < bottom and top < head[3]   # on the face
            sizes[shape] = top - bottom
        assert sizes["A"] > sizes["M"] and sizes["O"] > sizes["M"]


@pytest.mark.parametrize("species", ("bird", "owl", "penguin"))
def test_a_bird_talks_with_its_beak(species: str) -> None:
    for front in (False, True):
        c = animal(species)
        if front:
            c.face("front")
        hinge = c.pivot("mouth")
        gaps = {}
        for shape in ("M", *BEAK_OPENINGS):
            c.swap("mouth", shape)
            left, bottom, right, top = c.part_box("mouth")
            gaps[shape] = c.parts["mouth"].family_members_with_points()[0].height   # the dark inside (M: the closed line)
            if shape != "M":   # symmetric about the hinge's line: a frown's flip keeps the beak the right way up
                assert top - hinge[1] / c.character_height == pytest.approx(hinge[1] / c.character_height - bottom, abs=1e-6)
        assert gaps["open"] > gaps["A"] > gaps["O"] > gaps["E"] > gaps["F"] > gaps["M"]
        c.set_expression("sad")
        c.swap("mouth", "A")   # lip sync over a sad face
        assert c.part_box("mouth")[3] - c.part_box("mouth")[1] > 0


# ----- the tail: spring, idle, walk, wind -------------------------------------------------------------


def test_tail_follow_through_on_the_spring() -> None:
    assert follow_angles(-1.0, 0.0, 1.0)["tail"] > 0 > follow_angles(1.0, 0.0, 1.0)["tail"]   # back as it sets off, on as it stops
    assert follow_angles(0.0, -1.0, 1.0)["tail"] > 0   # down as it rises
    assert follow_angles(-100.0, 0.0, 1.0)["tail"] == FOLLOW_TAIL_LIMIT
    angles = {}
    for motion in ("lively", "none"):
        c = animal("cat")
        c.motion = motion
        walk = Walk(c, 8.0)
        walk.begin()
        walk.interpolate(walk.phases.before + 0.03)   # just set off
        angles[motion] = c.pose_of("tail").angle
        walk.finish()
    assert angles["lively"] > angles["none"] + 1.0   # the tail trails behind


def test_tail_swishes_while_idle_and_swings_in_a_walk() -> None:
    assert tail_sway_angle(0.0, 5) == pytest.approx(0.0)
    assert max(abs(tail_sway_angle(t / 10, 5)) for t in range(60)) > 3.0
    c = animal("dog")
    before = np.vstack([m.points for m in c.parts["tail"].family_members_with_points()]).copy()
    c.start_idle(seed=5)
    c._idle_step(1.0)
    after = np.vstack([m.points for m in c.parts["tail"].family_members_with_points()])
    assert not np.allclose(before, after) and c.pose_of("tail").angle == 0.0   # a layer, not the pose
    c.stop_idle()
    swung = walking_state(c.state(), walk_cycle(0.5), "right")
    assert swung.parts["tail"].angle != 0.0


@pytest.mark.parametrize("species", [*SPECIES, "fox", "owl", "turtle", "penguin"])
def test_tails_trail_in_the_wind(species: str) -> None:
    c = animal(species)
    marked = [m for m in c.parts["tail"].get_family() if getattr(m, TRAIL_ATTRIBUTE, None)]
    assert bool(marked) == (species not in ("bear", "rabbit"))   # round tails do not trail
    if marked:
        before = np.vstack([m.points for m in c.parts["tail"].family_members_with_points()]).copy()
        c.set_wind(30.0)
        assert not np.allclose(before, np.vstack([m.points for m in c.parts["tail"].family_members_with_points()]))


def test_effect_symbols_go_by_the_head_not_the_ears() -> None:
    rabbit = animal("rabbit", height=3.0)
    box = head_box(rabbit)
    assert box[3] - box[1] < rabbit.parts["head"].height - 0.1   # the ears are left out
    assert crown_top(rabbit) == pytest.approx(rabbit.parts["head"].get_top()[1], abs=0.01)   # symbols above go above the ears


# ----- SVG characters --------------------------------------------------------------------------------


def test_an_svg_tail(tmp_path: Path) -> None:
    path = tmp_path / "fox.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 200">'
        '<path id="tail" d="M 30 150 Q 5 150 5 110 L 15 110 Q 15 140 30 140 Z"/>'
        '<rect x="30" y="80" width="40" height="120"/></svg>', encoding="utf-8")
    parts = {p.name: p for p in svg_character_parts(path, where="fox.svg")}
    tail = parts["tail"]
    assert tail.parent == "body"
    drawn = tail.shapes["rest"]
    assert tail.pivot == pytest.approx((drawn.get_right()[0], drawn.get_bottom()[1]))   # where it leaves the body
    assert default_pivot("tail", (-1.0, 0.0, -0.5, 1.0), 0.0) == (-0.5, 0.0)
    c = Character(parts.values(), required=("body",))
    assert c.has_trails
    c.set_part("tail", angle=20)


# ----- a stage --------------------------------------------------------------------------------------


@pytest.mark.render
def test_animals_walk_talk_and_sit_on_a_windy_stage(make_project, tmp_path: Path) -> None:
    from test_cartoon_stage import render_with_layout
    from vidgen.introspect import LayoutRecorder

    cast = [
        {"name": "tib", "voice": "tib_voice", "look": {"species": "cat", "outfit": "overalls"}, "colors": {"skin": "#9C8E80"}},
        {"name": "wren", "voice": "wren_voice", "look": {"species": "bird", "outfit": "shorts"}, "colors": {"skin": "#5E86B5"}},
    ]
    params = {"wind": "windy", "characters": [{"name": "tib", "at": 0.25}, {"name": "wren", "at": "right", "facing": "left"}],
              "props": [{"prop": "chair", "at": 0.5}]}
    beats = [
        {"text": "Tib walks over and sits.", "voice": "tib_voice",
         "actions": [{"walk_to": "tib", "to": 0.45}, {"effect": "wren", "to": "idea"}]},
        {"text": "Wren says hello.", "voice": "wren_voice", "actions": [{"sit_on": "tib", "to": "chair"}]},
    ]
    scenes = [{"id": "yard", "type": "stage", "params": params, "beats": beats}]
    voices = {"tib_voice": {"voice_id": "t1"}, "wren_voice": {"voice_id": "w1"}}
    project = Project.load(make_project(minimal_config(characters=cast, voices=voices, scenes=scenes)))
    scene, objects = render_with_layout(project, "yard", tmp_path / "media", LayoutRecorder())
    assert scene.cast["tib"].has_part("tail") and scene.cast["tib"].sitting_on == "chair"
    assert any(o["kind"] == "effect" for o in objects)
