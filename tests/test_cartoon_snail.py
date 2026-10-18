"""Step 155: the ``snail`` species (a friendly blocker for platform stories): it builds, poses and
talks like the Step 123 animals; two feelers on the head that sway, a spiral shell behind the body
in ``colors.hair``, no tail, the slowest walk; the random cast and the contrast know it."""

from __future__ import annotations

import random

import numpy as np
import pytest

from test_cartoon_animals import animal
from test_cartoon_more_animals import built, test_each_new_species_builds_poses_and_talks
from test_cartoon_outfits import PIN_COLORS, drawing_digest
from vidgen.cartoon.acting import species_motion
from vidgen.cartoon.character import OUTER_HAIR_ATTRIBUTE
from vidgen.cartoon.contrast import look_features, species_difference
from vidgen.cartoon.primitives import TRAIL_ATTRIBUTE
from vidgen.cartoon.transition import Walk
from vidgen.config import CharacterLook
from vidgen.random_cast import SHELL_COLORS, SPECIES_COLORS, random_look


def test_a_snail_builds_poses_and_talks() -> None:
    test_each_new_species_builds_poses_and_talks("snail")
    assert not animal("snail").has_part("tail")


def test_its_drawing_is_its_own() -> None:
    looks = [CharacterLook(species=s) for s in ("human", "turtle", "frog", "snail")]
    assert len({drawing_digest(look) for look in looks}) == 4
    assert len({drawing_digest(look, front=True) for look in looks}) == 4


def test_the_spiral_shell_is_behind_the_body_in_the_hair_colour() -> None:
    snail, person = animal("snail"), animal("human")
    body = snail.parts["body"].family_members_with_points()
    assert body[0].get_fill_color().to_hex().upper() != PIN_COLORS["clothes"]   # the shell comes first: behind
    assert snail.part_box("body")[0] < person.part_box("body")[0] - 0.05   # it bulges out behind the back
    assert PIN_COLORS["hair"] in {m.get_fill_color().to_hex().upper() for m in body[:3]}
    front = animal("snail").face("front")
    assert front.part_box("body")[2] - front.part_box("body")[0] > person.face("front").part_box("body")[2] - person.part_box("body")[0]


def test_the_feelers_rise_over_the_head_and_sway() -> None:
    snail, cat = animal("snail", height=2.0), animal("cat", height=2.0)
    head = snail.parts["head"]
    feelers = [m for m in head.get_family() if getattr(m, TRAIL_ATTRIBUTE, None)]
    assert feelers and all(getattr(m, OUTER_HAIR_ATTRIBUTE, False) for m in feelers)
    assert head.get_top()[1] - snail.part_box("eyes")[3] > cat.parts["head"].get_top()[1] - cat.part_box("eyes")[3]
    before = np.vstack([m.points for m in head.family_members_with_points()]).copy()
    snail.set_wind(30.0)
    assert not np.allclose(before, np.vstack([m.points for m in head.family_members_with_points()]))


def test_the_slowest_walker() -> None:
    assert species_motion("snail").speed < species_motion("turtle").speed < 1.0
    assert Walk(built("snail"), 3.0).step_length < Walk(built("human"), 3.0).step_length


def test_random_snails_and_contrast() -> None:
    rng = random.Random(7)
    for _ in range(6):
        made = random_look(rng, "neutral", ("snail",))
        assert made["look"]["species"] == "snail" and made["colors"]["skin"] in SPECIES_COLORS["snail"]
        assert made["colors"]["hair"] in SHELL_COLORS
        CharacterLook(**made["look"])
    assert species_difference("snail", "turtle") == 0.5 and species_difference("snail", "frog") == 1.0
    shell = look_features({"species": "snail"}, {"skin": "#C9B79C", "hair": "#B5652E"})
    assert shell is not None and shell.colors["hair"] == "#B5652E"   # its shell colour counts (its hair is none)


@pytest.mark.parametrize("key", ("ears", "nose"))
def test_a_snail_draws_its_own_face(key: str) -> None:
    with pytest.raises(ValueError, match="a snail draws its own"):
        CharacterLook(species="snail", **{key: "round"})
