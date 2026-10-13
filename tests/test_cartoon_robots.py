"""Step 124: robots (``species: robot`` and ``look.robot``) and costume pieces (``crown``,
``wizard_hat``, ``party_hat``, ``cape``): every robot build draws, poses, sits, walks or rolls and
talks (on a screen too), the antenna and the cape on the spring and in the wind, idle blinking,
the config rules, contrast and random casts, the ``[beep]`` voice sound, the pinned drawings of
earlier looks, and one tiny render."""

from __future__ import annotations

import itertools
import random
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_outfits import PIN_COLORS, drawing_digest
from vidgen import sfx
from vidgen.cartoon.acting import ROLLING_MOTION, RUNNING, WALKING, species_motion, walk_cycle
from vidgen.cartoon.cast import GENERATED_SHAPES, character_lines, character_part_shapes
from vidgen.cartoon.character import (
    DEFAULT_DRAW_ORDER,
    REQUIRED_PARTS,
    TRAIL_ATTRIBUTE,
    Character,
    CharacterState,
    PartPose,
    build_character,
)
from vidgen.cartoon.contrast import contrast_score, look_features
from vidgen.cartoon.effect_symbols import crown_top
from vidgen.cartoon.foley import PlayedAction, foley_cues
from vidgen.cartoon.generator import generate_parts
from vidgen.cartoon.idle import ANTENNA_DIM_SHAPE, antenna_light_on, antenna_sway_angle
from vidgen.cartoon.motion import FOLLOW_CAPE_LIMIT, follow_angles
from vidgen.cartoon.robots import SCREEN_GLOW, TYRE_COLOR
from vidgen.cartoon.transition import Walk, walking_state
from vidgen.config import TOP_OF_HEAD, CharacterEntry, CharacterLook, VoiceConfig
from vidgen.project import Project
from vidgen.random_cast import SPECIES_COLORS, random_cast, random_look
from vidgen.theme import Theme
from vidgen.voicesounds import VOICE_SOUNDS, VoiceSound, sound_voicing

#: Animals of Step 123 whose drawings must not change: :func:`drawing_digest` (side, front) taken
#: at HEAD 8dceb29 before Step 124 (the earlier looks are pinned in test_cartoon_animals).
PINNED_123: dict[str, tuple[dict[str, Any], tuple[str, str]]] = {
    "fox": ({"species": "fox"}, ("f5ad1cc8454eeaa4", "ab95c139658a688d")),
    "owl": ({"species": "owl", "outfit": "dress", "accessories": ["glasses"]}, ("eeed21d1083502ec", "333d022bcc864ac6")),
    "frog": ({"species": "frog", "outfit": "shorts"}, ("dc472d9021ce347f", "223d8b5298cda6f3")),
    "turtle": ({"species": "turtle", "outfit": "overalls", "shoes": "boots"}, ("3f40cb2ef7dc3678", "1300b370361ef77e")),
    "penguin": ({"species": "penguin", "accessories": ["hat", "scarf"], "seed": 2}, ("54148acbd6b7ae77", "d83b82e75c115039")),
}
#: Every robot build: head x face x antenna x legs / wheels.
BUILDS = [
    {"head": head, "face": face, "antenna": antenna, "moves_on": moves}
    for head, face, antenna, moves in itertools.product(("box", "round"), ("eyes", "screen"), (True, False), ("legs", "wheels"))
]
COSTUMES = (["crown"], ["wizard_hat"], ["party_hat"], ["cape"], ["crown", "cape", "glasses"], ["wizard_hat", "cape", "scarf"],
            ["party_hat", "bow", "backpack"])


@pytest.mark.parametrize("name", PINNED_123)
def test_step_123_animals_keep_their_drawings(name: str) -> None:
    values, digests = PINNED_123[name]
    look = CharacterLook(**values)
    assert (drawing_digest(look), drawing_digest(look, front=True)) == digests


def figure(height: float = 2.0, **look: Any) -> Character:
    values = CharacterLook(**look)
    return Character(generate_parts(values, PIN_COLORS), name="r", height=height, front=generate_parts(values, PIN_COLORS, front=True))


def robot(height: float = 2.0, **build: Any) -> Character:
    return figure(height, species="robot", robot=build)


def fills(c: Character, part: str) -> set[str]:
    return {m.get_fill_color().to_hex().upper() for m in c.parts[part].family_members_with_points() if m.get_fill_opacity() > 0}


# ----- robots build, pose, sit, walk and talk --------------------------------------------------------


@pytest.mark.parametrize("build", BUILDS, ids=lambda b: "-".join(str(v) for v in b.values()))
def test_every_robot_build_draws_poses_and_talks(build: dict[str, Any]) -> None:
    c = robot(**build)
    assert set(REQUIRED_PARTS) <= set(c.parts) and not c.has_part("tail")
    assert c.has_part("antenna") == build["antenna"]
    assert c.get_bottom()[1] == pytest.approx(0.0, abs=1e-6) and c.get_top()[1] == pytest.approx(2.0)
    entry = CharacterEntry(name="t", look={"species": "robot", "robot": build})
    assert {part: c.shape_names(part) for part in c.parts} == character_part_shapes(entry, Path("."))   # validate knows its parts
    assert c.shape_names("mouth") == GENERATED_SHAPES["mouth"]
    for pose in ("waving", "pointing", "thinking", "shrug", "arms_crossed", "sitting"):
        c.set_pose(pose)
    c.set_pose("stand")
    c.reach("left", c.hand_point("left") + np.array([0.3, 0.4, 0.0]))
    c.set_state(c.seated(c.posed_state(pose="stand"), 0.16))
    assert (c.pivot("leg_left")[1] - c.feet()[1]) / c.character_height == pytest.approx(0.16, abs=1e-6)
    for facing in ("right", "front"):
        c.face(facing)
        c.set_state(walking_state(c.posed_state(pose="stand"), walk_cycle(0.5), c.facing))
        heights = {}
        for shape in ("M", "A", "O"):
            c.swap("mouth", shape)
            box = c.part_box("mouth")
            heights[shape] = box[3] - box[1]
        assert heights["A"] > heights["M"] and heights["O"] > heights["M"]   # lip sync reads
        c.set_expression("sad")
        c.set_wind(30.0)
        c.set_wind(0.0)


def test_robot_builds_differ_and_keep_humans_apart() -> None:
    digests = {drawing_digest(CharacterLook(species="robot", robot=b)) for b in BUILDS}
    assert len(digests) == len(BUILDS)
    assert drawing_digest(CharacterLook(species="robot")) == drawing_digest(CharacterLook(species="robot", robot={}))   # the defaults
    assert drawing_digest(CharacterLook(species="robot")) not in {drawing_digest(CharacterLook(species=s)) for s in ("human", "cat")}


def test_a_screen_face_glows_and_an_eyes_face_does_not() -> None:
    screen, eyes = robot(face="screen"), robot(face="eyes")
    assert SCREEN_GLOW.upper() in fills(screen, "eyes") and SCREEN_GLOW.upper() not in fills(eyes, "eyes")
    for shape in ("A", "O", "M", "smile"):   # every mouth shape shows on the screen
        for c in (screen, eyes):
            c.swap("mouth", shape)
        strokes = {m.get_stroke_color().to_hex().upper() for m in screen.parts["mouth"].family_members_with_points() if m.get_stroke_width() > 0}
        assert SCREEN_GLOW.upper() in fills(screen, "mouth") | strokes and SCREEN_GLOW.upper() not in fills(eyes, "mouth")
    screen.swap("eyes", "closed")   # a blink is a glowing line
    assert {m.get_stroke_color().to_hex().upper() for m in screen.parts["eyes"].family_members_with_points()} == {SCREEN_GLOW.upper()}


def test_joints_hands_feet_and_wheels() -> None:
    legs, wheels, person = robot(), robot(moves_on="wheels"), figure()
    assert len(legs.parts["arm_left_lower"].family_members_with_points()) > len(person.parts["arm_left_lower"].family_members_with_points())
    assert len(legs.parts["arm_left"].family_members_with_points()) == 2   # the segment and the shoulder's bolt
    assert wheels.part_box("leg_left_lower")[1] == pytest.approx(0.0, abs=1e-6)   # the wheel stands on the ground
    assert TYRE_COLOR.upper() in fills(wheels, "leg_left_lower") and TYRE_COLOR.upper() not in fills(legs, "leg_left_lower")
    assert PIN_COLORS["skin"] in fills(legs, "arm_left") and len(fills(legs, "arm_left")) == 2   # plating and a bolt
    coat = figure(species="robot", outfit="coat")
    assert PIN_COLORS["clothes"] in fills(coat, "arm_left")   # sleeves follow the outfit


def test_robots_walk_stiffly_or_roll() -> None:
    legged = species_motion("robot")
    assert legged.gait.knee < 1.0 and not legged.gait.rolls
    assert species_motion("robot", wheels=True) is ROLLING_MOTION
    roll = ROLLING_MOTION.walking(WALKING)
    cycle = walk_cycle(0.5, gait=roll)
    assert cycle.thigh_angle == cycle.arm_angle == 0.0 and cycle.knee_bends == (0.0, 0.0)
    run = ROLLING_MOTION.walking(RUNNING)
    assert run.rolls and run.swing == 0.0 and run.lean == RUNNING.lean   # leans into a fast roll
    entry = CharacterEntry(name="w", look={"species": "robot", "robot": {"moves_on": "wheels"}}, colors=PIN_COLORS, idle=False)
    built = build_character(entry, theme=Theme(), height=2.0)
    assert built.species_motion is ROLLING_MOTION and Walk(built, 3.0).gait.rolls
    rolled = PlayedAction("walk_to", 1.0, 2.0, heights=2.1, rolls=True)
    assert [cue.sound for cue in foley_cues(rolled)] == []   # no footsteps on wheels
    assert {cue.sound for cue in foley_cues(PlayedAction("walk_to", 1.0, 2.0, heights=2.1))} == {"footstep"}


# ----- the antenna -------------------------------------------------------------------------------------


def test_antenna_springs_blinks_and_trails() -> None:
    c = robot()
    assert c.shape_names("antenna") == ["default", ANTENNA_DIM_SHAPE] and c.draw_order.index("antenna") < c.draw_order.index("head")
    lit = fills(c, "antenna")
    c.swap("antenna", ANTENNA_DIM_SHAPE)
    assert fills(c, "antenna") != lit and PIN_COLORS["accessory"] in lit
    c.swap("antenna", "default")
    assert follow_angles(-1.0, 0.0, 1.0)["antenna"] > 0 > follow_angles(1.0, 0.0, 1.0)["antenna"]   # tips back as it sets off
    tip = c.part_box("antenna")[3]
    c.set_state(CharacterState(c.facing, {**c.state().parts, "antenna": PartPose(angle=20.0)}))
    assert c.part_box("antenna")[3] < tip   # turns about its socket
    c.set_state(CharacterState(c.facing, {**c.state().parts, "antenna": PartPose()}))
    assert antenna_sway_angle(0.0, 7) == 0.0 and max(abs(antenna_sway_angle(t / 10, 7)) for t in range(40)) > 1.0
    lights = [antenna_light_on(t / 20, 3) for t in range(60)]
    assert antenna_light_on(0.0, 3) and not all(lights) and sum(lights) > len(lights) / 2
    trails = [m for m in c.parts["antenna"].family_members_with_points() if getattr(m, TRAIL_ATTRIBUTE, None) is not None]
    assert trails
    assert crown_top(c) == pytest.approx(c.parts["antenna"].get_top()[1])   # effect symbols go above it
    before = c.parts["antenna"].get_right()[0]
    c.set_wind(40.0)
    assert c.parts["antenna"].get_right()[0] > before + 0.05   # the light leans with the wind


def test_idle_blinks_the_antenna_light() -> None:
    entry = CharacterEntry(name="beeper", look={"species": "robot"}, colors=PIN_COLORS)
    c = build_character(entry, theme=Theme(), height=2.0)
    shown = set()
    for _ in range(40):
        c._idle_step(0.05)
        shown.add(c._shape_name("antenna"))
    assert shown == {"default", ANTENNA_DIM_SHAPE}


# ----- costumes ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("worn", COSTUMES, ids=lambda w: "+".join(w))
def test_costumes_build_side_and_front_on_people_animals_and_robots(worn: list[str]) -> None:
    for species in ("human", "cat", "robot"):
        c = figure(species=species, accessories=worn)
        on_head = [a for a in worn if a != "cape" and a in ("crown", "wizard_hat", "party_hat", "glasses", "bow")]
        assert c.has_part("accessory") == bool(on_head) and c.has_part("cape") == ("cape" in worn)
        entry = CharacterEntry(name="t", look={"species": species, "accessories": worn})
        assert {part: c.shape_names(part) for part in c.parts} == character_part_shapes(entry, Path("."))
        for facing in ("right", "front"):
            c.face(facing)
            c.set_pose("waving")
            c.set_state(c.seated(c.posed_state(pose="stand"), 0.16))
            c.set_wind(-30.0)
            c.set_wind(0.0)
    for piece in ("crown", "wizard_hat", "party_hat"):   # each reaches above the head, front view too
        hatted = figure(accessories=[piece])
        for facing in ("right", "front"):
            hatted.face(facing)
            assert hatted.part_box("accessory")[3] > hatted.part_box("head")[3]
    assert len({drawing_digest(CharacterLook(accessories=[p])) for p in ("crown", "wizard_hat", "party_hat", "cape")}) == 4


def test_one_piece_on_top_of_the_head() -> None:
    for a, b in itertools.combinations(TOP_OF_HEAD, 2):
        with pytest.raises(ValidationError, match="worn on top of the head"):
            CharacterLook(accessories=[a, b])
    with pytest.raises(ValidationError, match="hat and cap are both worn"):
        CharacterLook(accessories=["hat", "cap"])
    with pytest.raises(ValidationError, match="are all worn"):
        CharacterLook(accessories=["crown", "party_hat", "cap"])
    CharacterLook(accessories=["crown", "cape", "bow", "glasses", "scarf"])   # a crown goes with the rest


def test_cape_hangs_behind_swings_on_the_spring_and_trails() -> None:
    c = figure(accessories=["cape"])
    assert c.draw_order[0] == "cape" and DEFAULT_DRAW_ORDER["cape"] < DEFAULT_DRAW_ORDER["tail"]
    assert c.part_box("cape")[0] < c.part_box("body")[0] - 0.05   # flares out behind the back
    assert c.part_box("cape")[1] < c.part_box("body")[1]   # down below the body
    back, on = follow_angles(-1.0, 0.0, 1.0)["cape"], follow_angles(1.0, 0.0, 1.0)["cape"]
    assert back < 0 < on   # swings back as it sets off, on as it stops
    assert follow_angles(0.0, 1.0, 1.0)["cape"] < 0   # floats up behind while falling
    assert follow_angles(-100.0, 0.0, 1.0)["cape"] == -FOLLOW_CAPE_LIMIT
    base = c.posed_state(pose="stand")
    assert walking_state(base, walk_cycle(0.5), "right").parts["cape"].angle < base.parts["cape"].angle   # flutters back with a step
    still = c.parts["cape"].get_right()[0]
    c.set_wind(40.0)
    assert c.parts["cape"].get_right()[0] > still + 0.1   # its hem blows forward in a wind from behind
    c.face("front")
    left = c.parts["cape"].get_left()[0]
    c.set_wind(-40.0)
    assert c.parts["cape"].get_left()[0] < left - 0.1   # from the front it flies out to the side


# ----- config, cast, contrast ------------------------------------------------------------------------------


def test_robot_config_rules() -> None:
    with pytest.raises(ValidationError, match="no hair"):
        CharacterLook(species="robot", hair="short")
    with pytest.raises(ValidationError, match="draws its own head"):
        CharacterLook(species="robot", ears="round")
    with pytest.raises(ValidationError, match="only applies to species: robot"):
        CharacterLook(species="cat", robot={"face": "screen"})
    with pytest.raises(ValidationError, match="wears no shoes"):
        CharacterLook(species="robot", robot={"moves_on": "wheels"}, shoes="boots")
    with pytest.raises(ValidationError):
        CharacterLook(species="robot", robot={"head": "dome"})
    assert CharacterLook(species="robot", shoes="boots").robot_look().moves_on == "legs"
    lines = character_lines(CharacterEntry(name="zed", look={"species": "robot", "robot": {"face": "screen", "moves_on": "wheels"}}), Theme())
    assert "species robot (box head, screen face, antenna, wheels)" in lines[1]


def test_contrast_and_random_robots() -> None:
    def features(**look: Any) -> Any:
        return look_features(look, {})

    crowned, capped, bare = features(accessories=["crown"]), features(accessories=["cap"]), features()
    assert crowned.silhouette["headwear"] == "crown" and contrast_score(crowned, capped) > 0 and contrast_score(crowned, bare) > 0
    box, ball = features(species="robot"), features(species="robot", robot={"head": "round", "face": "screen"})
    assert contrast_score(box, ball) > 0 and contrast_score(box, features(species="human")) > contrast_score(box, ball)
    rng = random.Random(3)
    for _ in range(12):
        made = random_look(rng, "neutral", ("robot",))
        look = CharacterLook(**made["look"])
        assert look.species == "robot" and look.hair == "none" and made["colors"]["skin"] in SPECIES_COLORS["robot"]
    cast = random_cast(6, seed=2, species=("robot", "human"))
    assert any(c["look"].get("species") == "robot" for c in cast.characters) and cast.lowest_contrast > 0.3
    assert random_cast(4, seed=1).characters == random_cast(4, seed=1, species=("human",)).characters


# ----- the beep ----------------------------------------------------------------------------------------------


def test_a_robot_beeps() -> None:
    kind = VOICE_SOUNDS["beep"]
    assert kind.sfx == "beep" and kind.expression == "happy"
    kokoro = VoiceConfig(provider="kokoro")
    assert sound_voicing(kokoro, VoiceSound("beep", 0), 3) is None   # generated before the line
    assert sound_voicing(kokoro, VoiceSound("beep", 3), 3) is None   # ... or after it
    assert sound_voicing(kokoro, VoiceSound("beep", 1), 3) == "Beep boop!"   # inside the line: said
    samples = sfx.synthesize("beep")
    assert len(samples) == round(sfx.BUILTIN_SOUNDS["beep"].duration * sfx.RATE)
    assert sfx.loudness(samples) == pytest.approx(sfx.LOUDNESS_TARGET, abs=0.5) and samples[0] == samples[-1] == 0.0
    assert np.array_equal(samples, sfx.synthesize("beep"))


# ----- a stage ----------------------------------------------------------------------------------------------


@pytest.mark.render
def test_robots_and_a_cape_on_a_windy_stage(make_project, tmp_path: Path) -> None:
    from test_cartoon_stage import render_with_layout
    from vidgen.introspect import LayoutRecorder

    cast = [
        {"name": "zed", "voice": "a", "look": {"species": "robot", "robot": {"face": "screen", "moves_on": "wheels"}}},
        {"name": "ida", "voice": "b", "look": {"accessories": ["crown", "cape"], "hair": "long"}},
    ]
    params = {"wind": "breeze", "characters": [{"name": "zed", "at": 0.2}, {"name": "ida", "at": 0.7, "facing": "left"}]}
    beats = [
        {"text": "[beep] Zed rolls over.", "voice": "a", "actions": [{"walk_to": "zed", "to": 0.45}]},
        {"text": "Ida waves.", "voice": "b", "actions": [{"gesture": "ida", "to": "wave"}]},
    ]
    scenes = [{"id": "yard", "type": "stage", "params": params, "beats": beats}]
    voices = {"a": {"voice_id": "a1"}, "b": {"voice_id": "b1"}}
    project = Project.load(make_project(minimal_config(characters=cast, voices=voices, scenes=scenes)))
    scene, objects = render_with_layout(project, "yard", tmp_path / "media", LayoutRecorder())
    assert scene.cast["zed"].species_motion is ROLLING_MOTION and scene.cast["zed"].has_part("antenna")
    assert scene.cast["ida"].has_part("cape") and objects
