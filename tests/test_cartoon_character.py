"""Step 67: the character model (parts, pivots, mirroring), ``characters:`` and its checks."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config, write_files
from vidgen import runtime
from vidgen.cartoon.cast import find_character
from vidgen.cartoon.character import (
    DEFAULT_PARENTS,
    PART_NAMES,
    REQUIRED_PARTS,
    Character,
    CharacterPart,
    PartPose,
    character,
)
from vidgen.cartoon.generator import generate_parts
from vidgen.cli import project_problems
from vidgen.config import CharacterLook, parse_config
from vidgen.errors import VidgenError
from vidgen.project import Project

COLORS = {"skin": "#F2A541", "clothes": "#58C4DD", "outline": "#1F2430", "features": "#1F2430", "hair": "#FF6B6B", "accessory": "#FFD166"}


def default_parts(colors: dict[str, str]) -> list[CharacterPart]:
    return generate_parts(CharacterLook(), colors)


def figure(**kwargs) -> Character:
    return Character(default_parts(COLORS), name="tester", **kwargs)


def points(mob) -> np.ndarray:
    return np.concatenate([m.points for m in mob.family_members_with_points()])


def snapshot(c: Character) -> dict[str, np.ndarray]:
    return {name: points(slot).copy() for name, slot in c.parts.items()}


# ----- part tree ------------------------------------------------------------------------------


def test_part_tree_and_draw_order() -> None:
    c = figure()
    # Step 92: arms and legs in two segments (upper / lower), one leg each instead of one `legs`
    limbs = {"arm_left_lower", "arm_right_lower", "leg_left", "leg_left_lower", "leg_right", "leg_right_lower"}
    assert set(c.parts) == {*REQUIRED_PARTS, *limbs} and not c.has_part("accessory") and not c.has_part("legs")
    assert c.draw_order == [
        "arm_right", "arm_right_lower", "leg_right", "leg_right_lower", "leg_left", "leg_left_lower", "body",
        "arm_left", "arm_left_lower", "head", "eyes", "mouth", "brows",
    ]
    assert c.parent_of("arm_left_lower") == "arm_left" and c.parent_of("leg_right_lower") == "leg_right" and c.parent_of("leg_left") == "body"
    assert c.submobjects[1:] == [c.parts[n] for n in c.draw_order]   # submobjects[0] is the anchor
    assert c.parent_of("body") is None and c.parent_of("mouth") == "head" and c.parent_of("arm_left") == "body"
    assert c.shape_names("mouth")[:2] == ["smile", "open"] and c.shape_names("eyes") == ["open", "closed"]
    assert set(DEFAULT_PARENTS) == set(PART_NAMES)


def test_size_and_feet() -> None:
    c = figure(height=2.0)
    assert np.allclose(c.feet(), 0) and c.get_bottom()[1] == pytest.approx(0) and c.get_top()[1] == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda parts: [p for p in parts if p.name != "mouth"], "missing part(s) mouth"),
        (lambda parts: [*parts, CharacterPart("wing", parts[0].shapes, (0, 0))], "unknown part(s) wing"),
        (lambda parts: [*parts, parts[0]], "part 'leg_left' given twice"),
        (lambda parts: [*parts, CharacterPart("accessory", parts[0].shapes, (0, 0), parent="hat")], "hangs from 'hat'"),
        (lambda parts: [CharacterPart(p.name, p.shapes, p.pivot, parent="eyes") if p.name == "head" else p for p in parts], "hangs from itself"),
    ],
)
def test_bad_part_sets(change: Callable, message: str) -> None:
    with pytest.raises(VidgenError, match=message.replace("(", r"\(").replace(")", r"\)")):
        Character(change(default_parts(COLORS)), name="bad")


# ----- pivots ---------------------------------------------------------------------------------


def test_rotating_a_part_moves_its_children_only() -> None:
    c = figure()
    before = snapshot(c)
    pivot = c.pivot("head")
    c.set_part("head", angle=25)
    after = snapshot(c)
    moved = {name for name in before if not np.allclose(before[name], after[name])}
    assert moved == {"head", "eyes", "brows", "mouth"}
    assert np.allclose(c.pivot("head"), pivot)
    # a rotation about the pivot keeps every point's distance to it
    assert np.allclose(np.linalg.norm(before["head"] - pivot, axis=1), np.linalg.norm(after["head"] - pivot, axis=1))
    assert c.pose_of("head") == PartPose(angle=25.0)


def test_scale_and_shift_about_the_pivot() -> None:
    c = figure()
    pivot = c.pivot("arm_left")
    c.set_part("arm_left", scale=(1.0, 0.5))
    assert np.allclose(c.pivot("arm_left"), pivot)
    assert c.parts["arm_left"].height == pytest.approx(figure().parts["arm_left"].height * 0.5, rel=0.05)
    c.set_part("eyes", shift=(0.1, 0.0))
    assert c.pivot("eyes")[0] == pytest.approx(figure().pivot("eyes")[0] + 0.1 * 3.0)


def test_swap_and_reset() -> None:
    c = figure()
    smile = points(c.parts["mouth"]).copy()
    c.swap("mouth", "open")
    assert c.pose_of("mouth").shape == "open" and not np.array_equal(points(c.parts["mouth"]), smile)
    c.set_part("head", angle=10)
    c.reset()
    assert np.allclose(points(c.parts["mouth"]), smile) and c.pose_of("head") == PartPose()
    with pytest.raises(VidgenError, match="no shape 'grin'.*shapes: smile, open, A, E"):
        c.swap("mouth", "grin")
    with pytest.raises(VidgenError, match="no part 'tail'"):
        c.set_part("tail", angle=5)


def test_poses_follow_the_placement() -> None:
    moved, still = figure(), figure()
    moved.shift([2, 1, 0]).scale(0.5, about_point=moved.feet())
    for c in (moved, still):
        c.set_part("arm_left", angle=80)
    assert np.allclose(moved.feet(), [2, 1, 0])
    expected = (points(still.parts["arm_left"]) * 0.5) + [2, 1, 0]
    assert np.allclose(points(moved.parts["arm_left"])[:, :2], expected[:, :2])


def test_state_round_trip_and_copy() -> None:
    c = figure()
    c.set_part("arm_left", angle=60).swap("eyes", "closed").face("left")
    state = c.state()
    other = figure().set_state(state)
    assert other.facing == "left" and all(np.allclose(a, b) for a, b in zip(snapshot(c).values(), snapshot(other).values()))
    twin = c.copy()
    twin.set_part("arm_left", angle=0)
    assert c.pose_of("arm_left").angle == 60   # the copy has its own poses


# ----- mirroring ------------------------------------------------------------------------------


def test_facing_left_mirrors_the_whole_character_about_the_feet() -> None:
    c = figure().shift([1.5, -1, 0])
    c.set_part("arm_left", angle=45)
    right = snapshot(c)
    c.face("left")
    left = snapshot(c)
    x = c.feet()[0]
    for name in right:
        assert np.allclose(left[name][:, 0], 2 * x - right[name][:, 0]) and np.allclose(left[name][:, 1], right[name][:, 1])
    c.turn()
    assert c.facing == "right" and all(np.allclose(right[n], p) for n, p in snapshot(c).items())
    with pytest.raises(VidgenError, match="right, left or front"):
        c.face("up")


# ----- characters: in video.yaml ----------------------------------------------------------------


def config_with(characters: list[dict], **extra) -> dict:
    return minimal_config(characters=characters, voices={"ana": {"voice_id": "a1"}}, **extra)


def test_characters_schema() -> None:
    config = parse_config(config_with([{"name": "pip", "voice": "ana", "colors": {"skin": "#A0522D"}}, {"name": "rex"}]))
    pip, rex = config.characters
    assert pip.voice == "ana" and pip.colors.skin == "#A0522D" and pip.colors.clothes == "primary"
    assert rex.voice is None and find_character(config, "rex") is rex
    assert parse_config(config_with([{"name": "pip", "voice": "default"}])).characters[0].voice == "default"


@pytest.mark.parametrize(
    ("characters", "message"),
    [
        ([{"name": "pip"}, {"name": "pip"}], "duplicate character name 'pip' (characters[0] and characters[1])"),
        ([{"name": "pip", "voice": "anna"}], "characters[0].voice: unknown voice 'anna'; did you mean 'ana'?"),
        ([{"name": "pip", "look": {"body": "blob"}}], "characters[0].look.body"),
        ([{"name": "two words"}], "characters[0].name"),
    ],
)
def test_characters_schema_errors(characters: list[dict], message: str) -> None:
    with pytest.raises(VidgenError) as info:
        parse_config(config_with(characters))
    assert message in str(info.value)


def test_unknown_character_message() -> None:
    config = parse_config(config_with([{"name": "pip"}, {"name": "rex"}]))
    with pytest.raises(VidgenError, match="unknown character 'pi'; did you mean 'pip'\\? characters: pip, rex"):
        find_character(config, "pi")
    with pytest.raises(VidgenError, match="declares no characters"):
        find_character(parse_config(minimal_config()), "pip")


EXTENSION = """
from vidgen.api import *


@scene("cartoon_demo")
class CartoonDemo(NarratedScene):
    class Params(SceneParams):
        who: CharacterName
        other: CharacterName | None = None

    def construct(self):
        area = self.region("center")
        hero = character(self.params.who, height=area.height * 0.9)
        hero.move_to(area.center)
        with self.narrate(0) as d:
            self.play(FadeIn(hero), run_time=min(0.6, d / 2))
            self.play(UpdateFromAlphaFunc(hero, lambda m, a: m.set_part("arm_left", angle=120 * a)), run_time=min(0.6, d / 2))
            hero.swap("mouth", "open").turn()
            self.wait(0.2)
            self.shown = self.renderer.get_frame().copy()
        self.finish()
"""


def cartoon_project(make_project, characters: list[dict], who: str = "pip") -> Project:
    scenes = [{"id": "toon", "type": "cartoon_demo", "params": {"who": who}, "beats": [{"text": "Hello there friend."}]}]
    root = make_project(minimal_config(characters=characters, scenes=scenes))
    write_files(root, {"extensions/cartoon_demo.py": EXTENSION})
    return Project.load(root)


def test_validate_checks_character_names_and_colors(make_project) -> None:
    project = cartoon_project(make_project, [{"name": "pip", "colors": {"clothes": "nope"}}], who="pop")
    problems = {p.location: p.message for p in project_problems(project)}
    assert "unknown character 'pop'; did you mean 'pip'?" in problems["scenes[0].params.who"]
    assert "unknown theme color 'nope'" in problems["characters[0].colors.clothes"]
    good = cartoon_project(make_project, [{"name": "pip"}])
    assert project_problems(good) == []


def test_character_helper_uses_the_project(make_project) -> None:
    project = cartoon_project(make_project, [{"name": "pip", "voice": None, "colors": {"clothes": "accent"}}])
    with runtime.use_context(project) as theme:
        c = character("pip", height=2.0, facing="left")
        assert c.name == "pip" and c.facing == "left" and c.get_top()[1] == pytest.approx(2.0)
        body = c.parts["body"].family_members_with_points()[0]
        assert body.get_fill_color().to_hex().upper() == theme.color("accent").upper()
        with pytest.raises(VidgenError, match="unknown character 'bob'"):
            character("bob")


@pytest.mark.render
def test_character_renders(make_project, tmp_path: Path) -> None:
    from test_builtin_scenes import render_scene

    project = cartoon_project(make_project, [{"name": "pip"}])
    scene, duration, _ = render_scene(project, "toon", tmp_path / "media", 160, 90)
    assert duration > 0
    background = np.asarray(scene.shown[0, 0, :3], dtype=int)
    drawn = np.any(np.abs(scene.shown[:, :, :3].astype(int) - background) > 30, axis=2)
    assert 0.03 < drawn.mean() < 0.6   # the figure covers part of the frame
