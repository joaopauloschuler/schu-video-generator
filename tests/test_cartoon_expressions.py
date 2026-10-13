"""Step 125: more expressions (laughing, blushing, tongue_out, crying, dizzy, frightened) on every
species family, side and front; their moods (sway, shiver, bounce), blinks over closed eyes,
transitions, lip sync over them, and the screenplay / voice sound / auto_direct mappings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_outfits import PIN_COLORS
from vidgen.cartoon.animals import fur_shade
from vidgen.cartoon.cast import GENERATED_SHAPES
from vidgen.cartoon.character import Character, PartPose, build_character
from vidgen.cartoon.effects import EFFECT_KINDS, EXPRESSION_EFFECTS
from vidgen.cartoon.expression_shapes import BRISTLE_SHAPES, CHEEK_SHAPES, EYE_SHAPES, MOUTH_SHAPES, TEAR_COLOR
from vidgen.cartoon.generator import generate_parts
from vidgen.cartoon.idle import (
    ANTENNA_FRIGHT_STRETCH,
    MOOD_SPRING,
    MOOD_SWAY_DEGREES,
    IdleClock,
    alternate_shape,
    mood_motion,
    shape_mood,
)
from vidgen.cartoon.poses import EXPRESSIONS
from vidgen.cartoon.still import character_sheet_sections
from vidgen.cartoon.transition import PoseChange
from vidgen.cartoon.visemes import VisemeCue, VisemeTrack
from vidgen.config import CharacterEntry, CharacterLook
from vidgen.project import Project
from vidgen.screenplay import manner_actions
from vidgen.theme import Theme
from vidgen.voicesounds import VOICE_SOUNDS

NEW = ("laughing", "blushing", "tongue_out", "crying", "dizzy", "frightened")
OLD = ("neutral", "happy", "sad", "angry", "surprised", "worried", "thinking")
#: One look per species family: a person with hair and without, a furry animal, a frog, beaked
#: animals, a robot with a face plate and one with a screen.
FAMILIES: dict[str, dict[str, Any]] = {
    "person": {"hair": "short"},
    "bald": {"hair": "none", "ears": "round"},
    "cat": {"species": "cat"},
    "dog": {"species": "dog"},
    "frog": {"species": "frog"},
    "bird": {"species": "bird"},
    "penguin": {"species": "penguin"},
    "plate_robot": {"species": "robot"},
    "screen_robot": {"species": "robot", "robot": {"face": "screen", "head": "round"}},
}
#: The shape each new expression shows on a generated character (none of the fallbacks).
SHOWN: dict[str, dict[str, str | None]] = {
    "laughing": {"eyes": "laughing", "mouth": "laugh", "cheeks": None, "bristles": None},
    "blushing": {"eyes": None, "mouth": None, "cheeks": "blush", "bristles": None},
    "tongue_out": {"eyes": "laughing", "mouth": "tongue", "cheeks": None, "bristles": None},
    "crying": {"eyes": "laughing", "mouth": "open", "cheeks": "tears", "bristles": None},
    "dizzy": {"eyes": "swirl", "mouth": "wavy", "cheeks": None, "bristles": None},
    "frightened": {"eyes": "wide", "mouth": "wavy", "cheeks": None, "bristles": "up"},
}


def figure(family: str, *, front: bool = False, idle: bool = False, height: float = 2.0) -> Character:
    look = CharacterLook(**FAMILIES[family])
    c = Character(generate_parts(look, PIN_COLORS), name=family, height=height, front=generate_parts(look, PIN_COLORS, front=True))
    if front:
        c.face("front")
    return c.start_idle(seed=3) if idle else c


def fills(c: Character, part: str) -> set[str]:
    return {m.get_fill_color().to_hex().upper() for m in c.parts[part].family_members_with_points() if m.get_fill_opacity() > 0}


def step(c: Character, seconds: float, dt: float = 0.04) -> list[dict[str, str]]:
    """Run the idle updater ``seconds`` long; the eyes', cheeks' and mouth's shown shapes per frame."""
    shown = []
    for _ in range(round(seconds / dt)):
        c.update(dt)
        shown.append({part: c.shown_shape(part) for part in ("eyes", "cheeks", "mouth")})
    return shown


# ----- every expression on every family -------------------------------------------------------


@pytest.mark.parametrize("family", list(FAMILIES))
@pytest.mark.parametrize("front", [False, True], ids=["side", "front"])
def test_each_expression_shows_its_own_shapes_on_each_family(family: str, front: bool) -> None:
    c = figure(family, front=front)
    for part, names in (("eyes", EYE_SHAPES), ("mouth", MOUTH_SHAPES), ("cheeks", CHEEK_SHAPES), ("bristles", BRISTLE_SHAPES)):
        assert set(names) <= set(c.shape_names(part)), part
    assert c.shape_names("cheeks")[0] == "none" and c.shape_names("bristles")[0] == "none"
    for name in NEW:
        c.set_expression(name)
        for part, shape in SHOWN[name].items():
            assert c.pose_of(part).shape == shape, (name, part)
        points = c.get_all_points()
        assert np.isfinite(points).all()
        for part, shape in SHOWN[name].items():
            if shape is not None and part != "mouth":   # something is drawn for it
                assert len(c.parts[part].get_all_points()) > 4, (name, part)
    for name in OLD:   # the earlier expressions put the new parts back to rest
        c.set_expression(name)
        assert c.pose_of("cheeks") == PartPose() and c.pose_of("bristles") == PartPose()
        assert len(c.parts["cheeks"].get_all_points()) == 4 and len(c.parts["bristles"].get_all_points()) == 4   # one point, nothing drawn


def test_the_rest_shapes_draw_nothing_even_when_faded() -> None:
    c = figure("person")
    for part in ("cheeks", "bristles"):
        (member,) = c.parts[part].family_members_with_points()
        assert np.ptp(member.points, axis=0).max() == 0 and member.get_stroke_width() == 0
        c.parts[part].set_opacity(0.5)
        assert member.get_stroke_width() == 0


def test_hair_fur_feathers_or_fright_lines_stand_up() -> None:
    def up(family: str) -> Character:
        return figure(family).set_expression("frightened")

    assert PIN_COLORS["hair"].upper() in fills(up("person"), "bristles")
    assert PIN_COLORS["skin"].upper() in fills(up("cat"), "bristles")   # fur in its own colour
    assert fur_shade(PIN_COLORS["skin"]).upper() in fills(up("bird"), "bristles")
    for family in ("bald", "frog", "plate_robot"):   # nothing to stand up: lines only
        assert fills(up(family), "bristles") == set() and len(up(family).parts["bristles"].get_all_points()) > 4
    person = figure("person")
    rest_top = person.get_top()[1]
    assert rest_top == pytest.approx(2.0)   # standing hair never changes the figure's size
    assert person.set_expression("frightened").get_top()[1] > rest_top + 0.05
    assert figure("person").draw_order.index("bristles") < figure("person").draw_order.index("head") < figure("person").draw_order.index("cheeks")


def test_tears_and_blush_sit_under_the_eyes() -> None:
    for family in ("person", "dog", "bird", "screen_robot"):
        for front in (False, True):
            c = figure(family, front=front).set_expression("crying")
            assert TEAR_COLOR.upper() in fills(c, "cheeks")
            eyes, tears = c.parts["eyes"], c.parts["cheeks"]
            assert tears.get_top()[1] < eyes.get_top()[1] and tears.get_bottom()[1] < eyes.get_bottom()[1]
            assert c.parts["head"].get_bottom()[1] - 0.02 < tears.get_bottom()[1]   # they stop on the face
    blush = figure("person").set_expression("blushing").parts["cheeks"]
    assert blush.family_members_with_points()[0].get_fill_opacity() < 1   # see-through over the skin
    screen = figure("screen_robot").set_expression("blushing").parts["cheeks"]
    assert all(m.get_fill_opacity() == 0 for m in screen.family_members_with_points())   # glowing strokes on a screen


def test_beaks_laugh_and_stick_out_a_tongue() -> None:
    for front in (False, True):
        bird = figure("bird", front=front)
        closed = bird.set_expression("neutral").parts["mouth"].width
        assert bird.set_expression("laughing").parts["mouth"].height > closed * 0.5
        assert "#E39AA2" in fills(bird, "mouth")   # the tongue
        assert "#E39AA2" in fills(bird.set_expression("tongue_out"), "mouth")


def test_generated_shape_table_lists_the_new_shapes() -> None:
    for family in FAMILIES:
        c = figure(family)
        for part in ("eyes", "mouth", "cheeks", "bristles"):
            assert c.shape_names(part) == GENERATED_SHAPES[part], (family, part)


# ----- moods: blinking, alternating shapes, sway, shiver, bounce ---------------------------------


def test_moods_follow_the_shown_shapes() -> None:
    assert shape_mood({"eyes": "swirl"}) == "sway" and shape_mood({"eyes": "wide", "mouth": "laugh"}) == "shiver"
    assert shape_mood({"mouth": "laugh"}) == "bounce" and shape_mood({"cheeks": "tears"}) == "bounce"
    assert shape_mood({"eyes": "open", "mouth": None}) is None
    moods = {name: shape_mood({p: e.shape_choices()[0] if e.shape_choices() else None for p, e in EXPRESSIONS[name].items()}) for name in EXPRESSIONS}
    assert moods == {**dict.fromkeys(OLD), "laughing": "bounce", "blushing": None, "tongue_out": None, "crying": "bounce", "dizzy": "sway", "frightened": "shiver"}
    assert alternate_shape("eyes", "swirl", 0.1) is None and alternate_shape("eyes", "swirl", 0.3) == "swirl_turned"
    assert alternate_shape("cheeks", "tears", 0.25) == "tears_running" and alternate_shape("eyes", "open", 0.3) is None


def test_a_mood_springs_in_and_dies_away() -> None:
    clock = IdleClock(seed=1)
    assert clock.mood_levels() == {}
    clock.set_mood("shiver")
    assert clock.mood_levels() == {"shiver": 0.0}   # nothing jumps
    levels = []
    for _ in range(100):
        clock.advance(0.02)
        levels.append(clock.mood_levels()["shiver"])
    assert max(levels) > 1.05 and levels[-1] == pytest.approx(1.0, abs=0.03)   # past full, then settled
    clock.set_mood(None)
    assert clock.mood_levels()["shiver"] == pytest.approx(levels[-1])
    clock.advance(0.15)
    fading = clock.mood_levels()["shiver"]
    assert 0 < fading < levels[-1]
    clock.set_mood("shiver")   # back again: from where it was
    assert clock.mood_levels()["shiver"] == pytest.approx(fading)
    clock.advance(MOOD_SPRING.settle_seconds() + 1.0)
    assert clock.mood_levels() == {"shiver": pytest.approx(1.0, abs=0.02)}


def test_mood_motion() -> None:
    assert mood_motion({}, 1.3, 5).is_still
    sways = [mood_motion({"sway": 1.0}, t / 10, 5) for t in range(40)]
    assert max(abs(m.body_angle) for m in sways) == pytest.approx(MOOD_SWAY_DEGREES, abs=0.2)
    assert all(m.body_shift == (0.0, 0.0) for m in sways) and max(abs(m.head_angle) for m in sways) > MOOD_SWAY_DEGREES
    shiver = mood_motion({"shiver": 1.0}, 0.37, 5)
    assert shiver.antenna_stretch == pytest.approx(1 + ANTENNA_FRIGHT_STRETCH) and shiver.body_angle == 0.0
    bounces = [mood_motion({"bounce": 1.0}, t / 50, 5).body_shift[1] for t in range(50)]
    assert min(bounces) >= 0 and max(bounces) > 0.005   # the shoulders bounce up, never down


def test_closed_eyes_never_blink_and_swirls_and_tears_alternate() -> None:
    open_eyes = figure("person", idle=True)
    assert "closed" in {s["eyes"] for s in step(open_eyes, 8.0)}   # a blink in 8 s (gaps of 2 to 6 s)
    for name, part, shapes in (("laughing", "eyes", {"laughing"}), ("dizzy", "eyes", {"swirl", "swirl_turned"}), ("crying", "cheeks", {"tears", "tears_running"})):
        c = figure("person", idle=True).set_expression(name)
        shown = step(c, 8.0)
        assert {s[part] for s in shown} == shapes, name
        assert "closed" not in {s["eyes"] for s in shown}


def test_dizzy_sways_with_the_feet_kept_and_frightened_shivers() -> None:
    c = figure("person", idle=True, height=3.0)
    feet, head = c.foot_point("left"), c.parts["head"].get_center()
    c.set_expression("dizzy")
    heads, soles = [], []
    for _ in range(60):
        c.update(0.05)
        heads.append(c.parts["head"].get_center()[0] - head[0])
        soles.append(c.foot_point("left")[0] - feet[0])
    assert max(heads) - min(heads) > 0.08 and max(abs(s) for s in soles) < 0.02   # the body sways, the legs stay put
    assert c.state() == c.posed_state(expression="dizzy")   # the sway is not in the pose
    robot = figure("plate_robot", idle=True)
    _, bottom, _, rest_top = robot.part_box("antenna")
    stretched = ANTENNA_FRIGHT_STRETCH * (rest_top - bottom)
    robot.set_expression("frightened")
    tops = []
    for _ in range(25):
        robot.update(0.04)
        tops.append(robot.part_box("antenna")[3])
    assert tops[0] < rest_top + 0.2 * stretched and max(tops) > rest_top + 0.9 * stretched   # it springs up, it does not jump
    robot.set_expression("neutral")
    step(robot, 4.0)
    assert robot.part_box("antenna")[3] == pytest.approx(rest_top, abs=0.01)
    assert "legs" not in robot._overlays and "leg_left" not in robot._overlays   # at rest again


# ----- transitions and speech ---------------------------------------------------------------------


@pytest.mark.parametrize("name", NEW)
def test_pose_change_into_and_out_of_each_new_expression(name: str) -> None:
    c = figure("dog", idle=True)
    change = PoseChange(c, expression=name, run_time=1)
    change.begin()
    change.interpolate(0.05)
    assert c.pose_of("cheeks").shape is None and c.pose_of("bristles").shape is None
    change.finish()
    for part, pose in c.posed_state(expression=name).parts.items():   # (blending leaves -0.9 as -0.8999999999999999)
        now = c.pose_of(part)
        assert now.shape == pose.shape and np.allclose([now.angle, *now.scale, *now.shift], [pose.angle, *pose.scale, *pose.shift]), part
    back = PoseChange(c, expression="neutral", run_time=1)
    back.begin()
    back.finish()
    assert c.pose_of("cheeks") == PartPose() and c.pose_of("bristles") == PartPose() and c.pose_of("eyes").shape is None


@pytest.mark.parametrize("family", ["person", "bird", "screen_robot"])
def test_laughing_while_talking(family: str) -> None:
    c = figure(family, idle=True).set_expression("laughing")
    now = {"t": 0.0}
    track = VisemeTrack((VisemeCue(0.0, 0.3, "A"), VisemeCue(0.3, 0.6, "rest"), VisemeCue(0.6, 1.0, "O")))
    c.lip_sync(track, clock=lambda: now["t"])
    shown = {}
    for t in (0.1, 0.45, 0.8):
        now["t"] = t
        c.update(0.04)
        shown[t] = (c.shown_shape("mouth"), c.shown_shape("eyes"))
    assert shown == {0.1: ("A", "laughing"), 0.45: ("laugh", "laughing"), 0.8: ("O", "laughing")}
    c.stop_lip_sync()
    assert c.shown_shape("mouth") == "laugh"


# ----- the mappings ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("manner", "expression"), [
    ("laughing", "laughing"), ("giggling", "laughing"), ("embarrassed", "blushing"), ("tongue out", "tongue_out"),
    ("cheeky", "tongue_out"), ("crying", "crying"), ("sobbing", "crying"), ("dizzy", "dizzy"), ("dazed", "dizzy"),
    ("scared", "frightened"), ("terrified", "frightened"), ("nervous", "worried"), ("upset", "sad"),
])
def test_screenplay_manners_name_the_expressions(manner: str, expression: str) -> None:
    assert manner_actions(manner) == ({"expression": expression}, [])


def test_voice_sounds_and_auto_direct_use_them() -> None:
    assert VOICE_SOUNDS["laugh"].expression == "laughing" and VOICE_SOUNDS["giggle"].expression == "laughing"
    assert VOICE_SOUNDS["gasp"].expression == "surprised" and VOICE_SOUNDS["sigh"].expression == "sad"
    assert EXPRESSION_EFFECTS["dizzy"] == "stars" and EXPRESSION_EFFECTS["frightened"] == "sweat" and "crying" not in EXPRESSION_EFFECTS
    assert set(EXPRESSION_EFFECTS.values()) <= set(EFFECT_KINDS)
    assert set(EXPRESSION_EFFECTS) <= set(EXPRESSIONS)


def test_character_sheet_lists_the_new_expressions_and_mouths() -> None:
    sections = {s.kind: s for s in character_sheet_sections(CharacterEntry(name="pip", look={"species": "owl"}), Path("."))}
    assert set(NEW) <= set(sections["expression"].names) and {"laugh", "tongue", "wavy"} <= set(sections["mouth"].names)


# ----- render ---------------------------------------------------------------------------------------


@pytest.mark.render
def test_moods_play_on_a_stage(make_project, tmp_path: Path) -> None:
    from test_cartoon_stage import render_with_layout

    cast = [
        {"name": "zed", "voice": "a", "look": {"species": "robot"}},
        {"name": "ida", "voice": "b", "look": {"hair": "long"}},
    ]
    params = {"characters": [{"name": "zed", "at": 0.3}, {"name": "ida", "at": 0.7, "facing": "left"}]}
    beats = [
        {"text": "Zed is scared.", "voice": "a", "actions": [{"emote": "zed", "to": "frightened"}]},
        {"text": "[laugh] Ida laughs at it.", "voice": "b"},
    ]
    scenes = [{"id": "yard", "type": "stage", "params": params, "beats": beats}]
    project = Project.load(make_project(minimal_config(characters=cast, voices={"a": {"voice_id": "a1"}, "b": {"voice_id": "b1"}}, scenes=scenes)))
    scene, objects = render_with_layout(project, "yard", tmp_path / "media")
    zed, ida = scene.cast["zed"], scene.cast["ida"]
    assert zed.shown_shape("eyes") == "wide" and zed.shown_shape("bristles") == "up" and objects
    assert zed.part_box("antenna")[3] > build_character(CharacterEntry(**cast[0]), theme=Theme()).part_box("antenna")[3] + 0.01
    assert ida.pose_of("mouth").shape == "laugh" and ida.shown_shape("eyes") == "laughing"
