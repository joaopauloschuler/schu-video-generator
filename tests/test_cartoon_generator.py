"""Step 68: the parametric character generator (``look:``), stroke scaling, ``vidgen character``."""

from __future__ import annotations

from typing import Any, get_args

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from conftest import minimal_config
from vidgen import cli
from vidgen.cartoon.cast import character_lines
from vidgen.cartoon.character import OUTLINE_WIDTH, REQUIRED_PARTS, Character
from vidgen.cartoon.generator import COLOR_KEYS, SEED_VARIATION, generate_parts, resolve_proportions
from vidgen.config import CharacterColors, CharacterEntry, CharacterLook
from vidgen.theme import Theme

COLORS = dict(zip(COLOR_KEYS, ("#F2A541", "#58C4DD", "#1F2430", "#1F2430", "#FF6B6B", "#FFD166")))
LOOK_FIELDS = ("body", "eyes", "nose", "hair", "ears")


def every_value() -> list[dict[str, Any]]:
    """One look per value of every ``look`` parameter (others at their defaults)."""
    looks = [{name: value} for name in LOOK_FIELDS for value in get_args(CharacterLook.model_fields[name].annotation)]
    looks += [{"accessories": [a]} for a in get_args(get_args(CharacterLook.model_fields["accessories"].annotation)[0])]
    looks += [{"head_size": 0.6}, {"head_size": 1.6}, {"seed": 0}, {"seed": 12345}]
    return looks


def points(mob) -> np.ndarray:
    return np.concatenate([m.points for m in mob.family_members_with_points()])


def shapes_of(look: CharacterLook) -> dict[str, np.ndarray]:
    return {f"{part.name}.{name}": points(shape) for part in generate_parts(look, COLORS) for name, shape in part.shapes.items()}


@pytest.mark.parametrize("values", every_value(), ids=lambda v: ",".join(f"{k}={v[k]}" for k in v))
def test_every_parameter_value_builds(values: dict[str, Any]) -> None:
    c = Character(generate_parts(CharacterLook(**values), COLORS), name="t", height=2.0)
    assert set(REQUIRED_PARTS) <= set(c.parts)
    assert c.get_bottom()[1] == pytest.approx(0) and c.get_top()[1] == pytest.approx(2.0)
    assert c.shape_names("eyes") == ["open", "closed"] and c.shape_names("mouth") == ["smile", "open"]
    c.set_part("head", angle=20).face("left")   # posing still works on every look


def test_all_accessories_together() -> None:
    look = CharacterLook(body="tall", hair="long", ears="pointy", accessories=["glasses", "hat", "scarf", "bag"])
    c = Character(generate_parts(look, COLORS), name="t")
    assert c.parent_of("accessory") == "head" and len(c.parts["accessory"].submobjects[0].submobjects) == 7   # glasses 4, hat 3
    worn_on_body = Character(generate_parts(CharacterLook(accessories=["scarf", "bag"]), COLORS), name="t")
    assert not worn_on_body.has_part("accessory")   # scarf and bag are drawn with the body


def test_same_parameters_give_the_same_shapes() -> None:
    look = {"body": "bean", "hair": "curly", "eyes": "round", "accessories": ["hat"], "seed": 7}
    first, second = shapes_of(CharacterLook(**look)), shapes_of(CharacterLook(**look))
    assert first.keys() == second.keys() and all(np.array_equal(first[k], second[k]) for k in first)
    other = shapes_of(CharacterLook(**{**look, "seed": 8}))
    assert any(not np.array_equal(first[k], other[k]) for k in first)


def test_parameters_change_the_shapes() -> None:
    base = shapes_of(CharacterLook())
    for values in ({"body": "square"}, {"head_size": 1.3}, {"eyes": "oval"}, {"hair": "short"}, {"nose": "dot"}):
        changed = shapes_of(CharacterLook(**values))
        assert changed.keys() != base.keys() or any(not np.array_equal(base[k], changed[k]) for k in base), values


def test_seed_varies_proportions_within_bounds() -> None:
    plain = resolve_proportions(CharacterLook())
    assert resolve_proportions(CharacterLook(seed=3)) == resolve_proportions(CharacterLook(seed=3)) != plain
    for seed in range(20):
        varied = resolve_proportions(CharacterLook(seed=seed))
        for name, value in vars(varied).items():
            assert abs(value / getattr(plain, name) - 1) <= SEED_VARIATION + 1e-9, (seed, name)
    assert resolve_proportions(CharacterLook(head_size=1.5)).head_radius == pytest.approx(0.3)


def test_look_schema_errors() -> None:
    with pytest.raises(ValidationError, match="accessory listed twice: hat"):
        CharacterLook(accessories=["hat", "scarf", "hat"])
    with pytest.raises(ValidationError):
        CharacterLook(head_size=2.0)
    with pytest.raises(ValidationError):
        CharacterLook(hair="mohawk")
    assert CharacterColors().hair == "accent" and CharacterColors().accessory == "highlight"


def stroke_widths(c: Character) -> list[float]:
    return [m.get_stroke_width() for m in c.parts["body"].family_members_with_points() if m.get_stroke_width() > 0]


def test_outline_scales_with_height_and_keeps_one_pixel() -> None:
    from manim import tempconfig

    with tempconfig({"pixel_width": 1920, "pixel_height": 1080, "frame_width": 14.22, "frame_height": 8.0}):
        assert stroke_widths(Character(generate_parts(CharacterLook(), COLORS), height=3.0)) == [pytest.approx(OUTLINE_WIDTH)]
        assert stroke_widths(Character(generate_parts(CharacterLook(), COLORS), height=6.0)) == [pytest.approx(2 * OUTLINE_WIDTH)]
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": 14.22, "frame_height": 8.0}):
        one_pixel = 100 * 8.0 / 90
        assert stroke_widths(Character(generate_parts(CharacterLook(), COLORS), height=1.0)) == [pytest.approx(one_pixel)]


def test_character_lines() -> None:
    entry = CharacterEntry(name="pip", voice="ana", look={"hair": "bun", "accessories": ["hat", "bag"], "seed": 2}, colors={"skin": "#C68B59"})
    lines = character_lines(entry, Theme())
    assert lines[0] == "character pip  (voice: ana)"
    assert "hair bun" in lines[1] and "accessories hat, bag, seed 2" in lines[1]
    assert "skin #C68B59, clothes primary (#58C4DD)" in lines[2]


def cartoon_config(**look: Any) -> dict[str, Any]:
    return minimal_config(characters=[{"name": "pip", "look": look}])


def test_character_command_prints_the_look(make_project, capsys) -> None:
    root = make_project(cartoon_config(body="tall", eyes="sleepy"))
    assert cli.main(["character", "pip", str(root)]) == 0
    out = capsys.readouterr().out
    assert "body tall" in out and "eyes sleepy" in out and "png:" not in out
    assert cli.main(["character", "pi", str(root)]) == 1
    assert "unknown character 'pi'; did you mean 'pip'?" in capsys.readouterr().err


@pytest.mark.render
def test_character_command_writes_a_png(make_project, capsys) -> None:
    root = make_project(cartoon_config(hair="short", accessories=["glasses"], seed=1))
    assert cli.main(["character", "pip", str(root), "--png"]) == 0
    path = root / "exports" / "character_pip.png"
    assert f"png: {path}  (1280x720, facing right)" in capsys.readouterr().out
    image = np.asarray(Image.open(path).convert("RGB"), dtype=int)
    drawn = np.any(np.abs(image - image[0, 0]) > 30, axis=2)
    assert image.shape == (720, 1280, 3) and 0.05 < drawn.mean() < 0.5
    custom = root / "stills" / "pip_left.png"
    assert cli.main(["character", "pip", str(root), "--png", str(custom), "--facing", "left"]) == 0
    assert Image.open(custom).size == (1280, 720)
