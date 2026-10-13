"""Step 87: render speed for cartoons (part drawings cached by look, redraws that only transform
them; the stage backdrop in Manim's static image, DESIGN.md §69.20)."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import numpy as np
import pytest

from test_cartoon_character import COLORS, figure, snapshot
from vidgen.cartoon import character as character_module
from vidgen.cartoon import generator
from vidgen.cartoon.character import build_character, look_key, look_parts
from vidgen.config import CharacterEntry, CharacterLook, PartPoseEntry
from vidgen.helpers import resolve_color
from vidgen.theme import Theme

LOOK = CharacterLook(body="tall", eyes="round", hair="bun", accessories=["scarf"])


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[CharacterLook]:
    """An empty look cache and the looks ``generate_parts`` draws from now on."""
    calls: list[CharacterLook] = []
    real = generator.generate_parts

    def counting(look: CharacterLook, colors: Any, **kwargs: Any) -> Any:
        calls.append(look)
        return real(look, colors, **kwargs)

    monkeypatch.setattr(character_module, "_look_cache", OrderedDict())
    monkeypatch.setattr(generator, "generate_parts", counting)
    return calls


def test_cache_key_changes_with_the_look_not_the_pose() -> None:
    key = look_key(LOOK, COLORS)
    assert look_key(CharacterLook(body="tall", eyes="round", hair="bun", accessories=["scarf"]), dict(COLORS)) == key
    for other in (LOOK.model_copy(update={"body": "round"}), LOOK.model_copy(update={"accessories": ["scarf", "hat"]}),
                  LOOK.model_copy(update={"seed": 3})):
        assert look_key(other, COLORS) != key
    assert look_key(LOOK, {**COLORS, "clothes": "#000000"}) != key


def test_part_drawings_are_made_once_per_look(counted: list[CharacterLook]) -> None:
    theme = Theme()
    pip = CharacterEntry(name="pip", look=LOOK)
    posed = CharacterEntry(
        name="kit", voice="kit_voice", look=LOOK, idle=False,
        poses={"lean": {"body": PartPoseEntry(angle=10)}}, expressions={"grin": {"mouth": PartPoseEntry(scale=1.4)}},
    )
    first = build_character(pip, theme=theme, height=2.0)
    first.set_pose("pointing").set_expression("surprised")
    build_character(posed, theme=theme, height=4.0, facing="left").set_pose("lean")
    assert counted == [LOOK, LOOK]   # its side and front view; other name, voice, poses, height, facing and state: the same drawings
    build_character(CharacterEntry(name="pip", look=LOOK.model_copy(update={"ears": "round"})), theme=theme)
    assert len(counted) == 4
    colors = {part: resolve_color(value, theme) for part, value in pip.colors.model_dump().items()}
    assert look_parts(LOOK, colors) is look_parts(LOOK, dict(colors)) and len(counted) == 4
    assert look_parts(LOOK, colors, front=True) is not look_parts(LOOK, colors) and len(counted) == 4


def test_look_cache_keeps_the_newest_looks(counted: list[CharacterLook], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(character_module, "LOOK_CACHE_SIZE", 2)
    looks = [CharacterLook(seed=k) for k in range(3)]
    for look in looks:
        look_parts(look, COLORS)
    look_parts(looks[2], COLORS)
    assert len(counted) == 3
    look_parts(looks[0], COLORS)   # dropped as the oldest
    assert len(counted) == 4


def test_redraws_transform_the_cached_drawings_only() -> None:
    rest = figure()
    c = rest.copy()
    c.set_part("arm_left", angle=40).swap("mouth", "open").set_part("head", angle=-12, shift=(0.02, 0.0))
    c.swap("eyes", "closed").face("left")
    c.reset().face("right")
    assert all(np.allclose(points, snapshot(rest)[name]) for name, points in snapshot(c).items())
    fresh = figure().swap("mouth", "O").set_part("head", angle=20)
    c.swap("mouth", "O").set_part("head", angle=20)
    assert np.allclose(snapshot(c)["mouth"], snapshot(fresh)["mouth"])   # a swapped shape is posed like the old one
    assert all(np.allclose(points, snapshot(figure())[name]) for name, points in snapshot(rest).items())   # the copy shares nothing
