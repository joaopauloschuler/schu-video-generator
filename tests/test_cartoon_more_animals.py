"""Step 123: more animals (``fox``, ``owl``, ``frog``, ``turtle``, ``penguin``): each builds, poses
and talks; a frog without a tail, a turtle's shell, the species' own gait, speed and jump; the
contrast of related species and the random cast's colours."""

from __future__ import annotations

import random
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_animals import animal
from test_cartoon_outfits import PIN_COLORS
from vidgen.cartoon.acting import RUNNING, WALKING, species_motion, walk_cycle
from vidgen.cartoon.animals import SPECIES_PROPORTIONS
from vidgen.cartoon.cast import GENERATED_SHAPES, character_part_shapes
from vidgen.cartoon.character import OUTER_HAIR_ATTRIBUTE, REQUIRED_PARTS, build_character
from vidgen.cartoon.contrast import contrast_score, look_features, species_difference
from vidgen.cartoon.effect_symbols import crown_top
from vidgen.cartoon.generator import resolve_proportions
from vidgen.cartoon.transition import SIDE_ROCK, Walk, walking_state
from vidgen.config import SPECIES_WITHOUT_TAIL, CharacterEntry, CharacterLook
from vidgen.project import Project
from vidgen.random_cast import SHELL_COLORS, SPECIES_COLORS, random_look
from vidgen.theme import Theme

NEW_SPECIES = ("fox", "owl", "frog", "turtle", "penguin")


def built(species: str, **look: Any) -> Any:
    """A stage character of ``species`` made like a project's (:func:`build_character`)."""
    entry = CharacterEntry(name=species, look={"species": species, **look}, colors=PIN_COLORS, idle=False)
    return build_character(entry, theme=Theme(), height=2.0)


# ----- each species builds, poses and talks ---------------------------------------------------------


@pytest.mark.parametrize("species", NEW_SPECIES)
def test_each_new_species_builds_poses_and_talks(species: str) -> None:
    c = animal(species, height=2.0, outfit="shorts")
    assert set(REQUIRED_PARTS) <= set(c.parts)
    assert c.has_part("tail") == (species not in SPECIES_WITHOUT_TAIL)
    assert c.get_bottom()[1] == pytest.approx(0.0, abs=1e-6) and c.get_top()[1] == pytest.approx(2.0)
    entry = CharacterEntry(name="t", look={"species": species, "outfit": "shorts"})
    assert {part: c.shape_names(part) for part in c.parts} == character_part_shapes(entry, Path("."))
    assert c.shape_names("mouth") == GENERATED_SHAPES["mouth"]
    for pose in ("waving", "pointing", "thinking", "shrug", "arms_crossed", "sitting"):
        c.set_pose(pose)
    c.set_pose("stand")
    c.reach("left", c.hand_point("left") + np.array([0.3, 0.4, 0.0]))
    c.set_state(c.seated(c.posed_state(pose="stand"), 0.14))
    assert (c.pivot("leg_left")[1] - c.feet()[1]) / c.character_height == pytest.approx(0.14, abs=1e-6)
    for front in (False, True):
        c.face("front" if front else "right")
        c.set_state(walking_state(c.posed_state(pose="stand"), walk_cycle(0.5), c.facing))
        heights = {}
        for shape in ("M", "A", "O"):
            c.swap("mouth", shape)
            box = c.part_box("mouth")
            heights[shape] = box[3] - box[1]
        assert heights["A"] > heights["M"] and heights["O"] > heights["M"]   # lip sync reads
        c.set_expression("sad")
        c.swap("mouth", "A")
        c.set_wind(30.0)
        c.set_wind(0.0)


def test_designs_differ_from_each_other_and_from_step_114() -> None:
    from test_cartoon_outfits import drawing_digest

    looks = [CharacterLook(species=s) for s in ("human", "cat", "dog", "bird", "bear", "rabbit", "mouse", *NEW_SPECIES)]
    assert len({drawing_digest(look) for look in looks}) == len(looks)
    assert len({drawing_digest(look, front=True) for look in looks}) == len(looks)


def test_species_proportions() -> None:
    plain = resolve_proportions(CharacterLook(species="cat"))
    assert plain == resolve_proportions(CharacterLook())   # Step 114 species keep a person's build
    frog, penguin = resolve_proportions(CharacterLook(species="frog")), resolve_proportions(CharacterLook(species="penguin"))
    assert frog.leg_length > plain.leg_length > penguin.leg_length
    assert frog.mouth_width == pytest.approx(SPECIES_PROPORTIONS["frog"]["mouth_width"])
    owl = resolve_proportions(CharacterLook(species="owl"))
    assert owl.eye_size > plain.eye_size and owl.eye_gap > plain.eye_gap


def test_frog_eyes_sit_high_and_effects_go_above_them() -> None:
    frog, cat = animal("frog", height=2.0), animal("cat", height=2.0)

    def eyes_rise(c: Any) -> float:
        """How far the eyes' middle is above the middle of the head part (ears and bulges too)."""
        return (c.part_box("eyes")[1] + c.part_box("eyes")[3]) / 2 - (c.part_box("head")[1] + c.part_box("head")[3]) / 2

    assert eyes_rise(frog) > eyes_rise(cat) + 0.05
    bulges = [m for m in frog.parts["head"].family_members_with_points() if getattr(m, OUTER_HAIR_ATTRIBUTE, False)]
    assert bulges and crown_top(frog) == pytest.approx(frog.parts["head"].get_top()[1], abs=0.01)
    for species in ("fox", "owl"):   # tall ears and tufts: symbols go above them
        c = animal(species, height=2.0)
        assert crown_top(c) == pytest.approx(c.parts["head"].get_top()[1], abs=0.01)


def test_turtle_shell_behind_the_body() -> None:
    turtle, person = animal("turtle"), animal("human")
    body = turtle.parts["body"].family_members_with_points()
    assert body[0].get_fill_color().to_hex().upper() != PIN_COLORS["clothes"]   # the shell comes first: behind
    assert turtle.part_box("body")[0] < person.part_box("body")[0] - 0.03   # it bulges out behind the back
    assert turtle.part_box("tail")[0] < turtle.part_box("body")[0] + 0.02   # the tail shows behind the shell
    shell = {m.get_fill_color().to_hex().upper() for m in body[:2]}
    assert any(color != PIN_COLORS["clothes"] for color in shell)
    front = animal("turtle").face("front")
    width = front.part_box("body")[2] - front.part_box("body")[0]
    assert width > person.face("front").part_box("body")[2] - person.part_box("body")[0]   # the rim shows round the body


def test_wings_flippers_and_feet() -> None:
    owl, penguin, frog = animal("owl"), animal("penguin"), animal("frog", outfit="shorts")
    assert {m.get_fill_color().to_hex().upper() for m in owl.parts["arm_left"].family_members_with_points()} == {PIN_COLORS["skin"]}
    assert {m.get_fill_color().to_hex().upper() for m in penguin.parts["arm_left_lower"].family_members_with_points()} == {PIN_COLORS["skin"]}
    assert len(animal("owl", outfit="dress").parts["leg_left_lower"].family_members_with_points()) == 4   # thin shin, three toes
    assert len(frog.parts["leg_left_lower"].family_members_with_points()) == 1 + 1 + 2   # shin, foot, two toe pads
    assert len(animal("frog", shoes="boots").parts["leg_left_lower"].family_members_with_points()) == 2   # a boot, no bare foot
    assert len(penguin.parts["leg_left_lower"].family_members_with_points()) == 2   # trouser leg and a flat foot


# ----- how they move ---------------------------------------------------------------------------------


def test_species_motion_gaits() -> None:
    person = species_motion("human")
    assert person.walking(WALKING) is WALKING and person.walking(RUNNING) is RUNNING
    assert species_motion("cat") is person   # Step 114 species move like people
    penguin = species_motion("penguin")
    assert penguin.walking(WALKING).waddle > 0 and penguin.walking(RUNNING).waddle == penguin.gait.waddle
    assert penguin.walking(RUNNING).stride == RUNNING.stride
    assert species_motion("turtle").speed < penguin.speed < 1.0 and species_motion("frog").jump > 1.0
    assert walk_cycle(0.5).rock == 0.0
    assert walk_cycle(0.5, gait=penguin.gait).rock == pytest.approx(penguin.gait.waddle)
    assert walk_cycle(1.5, gait=penguin.gait).rock == pytest.approx(-penguin.gait.waddle)   # over the other foot


def test_a_waddle_rocks_the_body_and_keeps_the_legs_upright() -> None:
    c = built("penguin")
    cycle = walk_cycle(0.5, gait=c.species_motion.gait)
    for facing, share in (("right", SIDE_ROCK), ("front", 1.0)):
        base = c.posed_state(pose="stand")
        plain = walking_state(base, replace(cycle, rock=0.0), facing)
        rocked = walking_state(base, cycle, facing)
        assert rocked.parts["body"].angle - plain.parts["body"].angle == pytest.approx(share * cycle.rock)
        assert rocked.parts["leg_left"].angle - plain.parts["leg_left"].angle == pytest.approx(-share * cycle.rock)
    c.set_state(walking_state(c.posed_state(pose="stand"), cycle, "front"))   # draws


def test_built_animals_walk_their_way() -> None:
    turtle, penguin, person = built("turtle"), built("penguin"), built("human")
    assert turtle.species_motion is species_motion("turtle") and person.species_motion is species_motion("human")
    assert Walk(penguin, 3.0).gait.waddle > 0 and Walk(person, 3.0).gait == WALKING
    assert Walk(turtle, 3.0).step_length < Walk(person, 3.0).step_length


def test_default_speeds_and_jumps_follow_the_species() -> None:
    from vidgen import extensions, registry

    extensions.load_builtins()
    walk, jump = registry.find_action("walk_to").cls, registry.find_action("jump").cls
    turtle, frog, person = built("turtle"), built("frog"), built("human")
    from vidgen.scenes.moving import _speed

    default, given = walk.Options(to=0.5), walk.Options(to=0.5, speed=2.5)
    assert _speed(default, turtle) == pytest.approx(0.4 * default.speed) and _speed(default, person) == default.speed
    assert _speed(given, turtle) == 2.5   # a written speed is kept
    action = jump(jump.Options(), None)
    assert action._height(frog) == pytest.approx(1.8 * action.options.height) and action._height(person) == action.options.height
    assert jump(jump.Options(height=0.3), None)._height(frog) == 0.3


# ----- contrast and the random cast ------------------------------------------------------------------


def test_related_species_contrast_less() -> None:
    assert species_difference("bird", "owl") == species_difference("cat", "fox") == 0.5
    assert species_difference("bird", "frog") == species_difference("cat", "dog") == 1.0 and species_difference("owl", "owl") == 0.0

    def score(a: str, b: str) -> float:
        return contrast_score(look_features({"species": a}, {}), look_features({"species": b}, {}))

    assert score("bird", "frog") > score("bird", "owl") > score("bird", "bird") == 0.0
    shell = look_features({"species": "turtle"}, {"skin": "#9DB06B", "hair": "#7A5C3E"})
    assert shell.colors["hair"] == "#7A5C3E"   # a turtle's shell colour counts (its hair is none)


@pytest.mark.parametrize("species", NEW_SPECIES)
def test_random_looks_of_new_species(species: str) -> None:
    rng = random.Random(5)
    for _ in range(6):
        made = random_look(rng, "neutral", (species,))
        assert made["look"]["species"] == species and made["colors"]["skin"] in SPECIES_COLORS[species]
        CharacterLook(**made["look"])
        if species == "turtle":
            assert made["colors"]["hair"] in SHELL_COLORS


# ----- a stage --------------------------------------------------------------------------------------


@pytest.mark.render
def test_new_animals_on_a_stage(make_project, tmp_path: Path) -> None:
    from test_cartoon_stage import render_with_layout
    from vidgen.introspect import LayoutRecorder

    cast = [
        {"name": "shel", "voice": "a", "look": {"species": "turtle"}, "colors": {"skin": "#9DB06B", "hair": "#7A5C3E"}},
        {"name": "pip", "voice": "b", "look": {"species": "penguin"}, "colors": {"skin": "#3B4A5F"}},
        {"name": "hop", "voice": "c", "look": {"species": "frog", "outfit": "shorts"}, "colors": {"skin": "#6FA84A"}},
    ]
    params = {"characters": [{"name": "shel", "at": 0.15}, {"name": "pip", "at": 0.5, "facing": "front"}, {"name": "hop", "at": "right", "facing": "left"}]}
    beats = [
        {"text": "Pip waddles over.", "voice": "b", "actions": [{"walk_to": "pip", "to": 0.65}, {"jump": "hop"}]},
        {"text": "Shel says hello.", "voice": "a", "actions": [{"walk_to": "shel", "to": 0.3}]},
    ]
    scenes = [{"id": "pond", "type": "stage", "params": params, "beats": beats}]
    voices = {"a": {"voice_id": "a1"}, "b": {"voice_id": "b1"}, "c": {"voice_id": "c1"}}
    project = Project.load(make_project(minimal_config(characters=cast, voices=voices, scenes=scenes)))
    scene, objects = render_with_layout(project, "pond", tmp_path / "media", LayoutRecorder())
    assert scene.cast["shel"].species_motion.speed < 1.0 and not scene.cast["hop"].has_part("tail")
    assert scene.cast["pip"].has_part("tail") and objects
