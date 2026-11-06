"""Steps 281-282: arms that read as arms at the sides (``look.arms`` / ``cartoon_arms``, DESIGN.md
§110), the default since Step 282; ``classic`` is the opt-out."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from conftest import minimal_config
from vidgen.cartoon.character import build_character
from vidgen.cartoon.generator import ARM_GAP, ARM_STYLES, DEFAULT_ARMS, FAR_ARM_ORDER, generate_parts
from vidgen.cartoon.primitives import outline_polygon, span_at
from vidgen.config import CharacterEntry, CharacterLook, parse_config
from vidgen.errors import VidgenError
from vidgen.theme import Theme

COLORS = {"skin": "#E8B98F", "clothes": "#4F6A9E", "outline": "#222222", "features": "#222222", "hair": "#2B2018",
          "accessory": "#3A3550", "trim": "#FF7F6B"}
LOOKS = {
    "suit": CharacterLook(body="tall", outfit="suit", accessories=["fedora"]),
    "lab_coat": CharacterLook(body="pear", outfit="lab_coat", hair="wavy", accessories=["pendant"]),
    "jumpsuit": CharacterLook(body="pear", outfit="jumpsuit"),
    "dress": CharacterLook(body="pear", outfit="dress"),
    "plain": CharacterLook(),
    "coat": CharacterLook(body="bean", outfit="coat"),
}


def _inside(polygon: list[tuple[float, float]], x: float, y: float) -> bool:
    crossings = 0
    for k, (x1, y1) in enumerate(polygon):
        x0, y0 = polygon[k - 1]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) / (y1 - y0) * (x1 - x0):
            crossings += 1
    return crossings % 2 == 1


def _outline(group) -> list[tuple[float, float]]:
    """The first filled member's outline (an arm segment, the body's cloth)."""
    member = next(m for m in group.get_family() if len(m.points) and m.get_fill_opacity() > 0)
    return outline_polygon(member)


def visible_share(look: CharacterLook, arm: str, *, front: bool, arms: str) -> float:
    """The share of an arm's lower segment (forearm) drawn on screen: sampled points of it that no
    body drawn over it covers."""
    parts = {p.name: p for p in generate_parts(look, COLORS, front=front, arms=arms)}
    body = _outline(parts["body"].shapes["default"])
    forearm = _outline(parts[f"{arm}_lower"].shapes["default"])
    order = parts[f"{arm}_lower"].order
    behind = order is not None and order < 30 or (order is None and arm == "arm_right" and not front)
    xs, ys = [p[0] for p in forearm], [p[1] for p in forearm]
    total = shown = 0
    for x in np.linspace(min(xs), max(xs), 25):
        for y in np.linspace(min(ys), max(ys), 40):
            if _inside(forearm, x, y):
                total += 1
                shown += not (behind and _inside(body, x, y))
    return shown / total


@pytest.mark.parametrize("name", sorted(LOOKS))
def test_both_arms_show_in_the_side_and_front_views(name: str) -> None:
    look = LOOKS[name]
    for front in (False, True):
        for arm in ("arm_left", "arm_right"):
            assert visible_share(look, arm, front=front, arms="front") > 0.95, (name, front, arm)


def test_the_classic_far_arm_of_a_tall_suit_is_mostly_hidden() -> None:
    assert visible_share(LOOKS["suit"], "arm_right", front=False, arms="classic") < 0.7


@pytest.mark.parametrize("name", sorted(LOOKS))
def test_front_arms_hang_clear_of_the_body(name: str) -> None:
    look = LOOKS[name]
    for front in (False, True):
        parts = {p.name: p for p in generate_parts(look, COLORS, front=front, arms="front")}
        body = _outline(parts["body"].shapes["default"])
        sides = (("arm_left", 1.0), ("arm_right", -1.0)) if front else (("arm_right", -1.0),)
        for arm, side in sides:
            x, y = parts[f"{arm}_lower"].end
            span = span_at(body, y)
            if span is not None:
                edge = span[1] if side > 0 else -span[0]
                assert side * x >= edge + ARM_GAP, (name, front, arm)   # the hand out past the body (a pear's hips may touch it)


def test_the_far_arm_is_drawn_over_the_body_and_under_the_near_arm() -> None:
    c = build_character(CharacterEntry(name="m", look=LOOKS["suit"]), theme=Theme(), arms="front")
    order = c.submobjects
    index = {name: order.index(part) for name, part in c.parts.items()}
    assert index["body"] < index["arm_right"] < index["arm_right_lower"] < index["arm_left"]
    classic = build_character(CharacterEntry(name="m", look=LOOKS["suit"]), theme=Theme(), arms="classic")
    index = {name: classic.submobjects.index(part) for name, part in classic.parts.items()}
    assert index["arm_right"] < index["body"] < index["arm_left"]
    c.face("front")
    index = {name: c.submobjects.index(part) for name, part in c.parts.items()}
    assert index["body"] < index["arm_left"] and index["body"] < index["arm_right"]
    assert FAR_ARM_ORDER[0] > 30


def _rounded(point: tuple[float, float] | None) -> tuple[float, ...] | None:
    return None if point is None else tuple(round(v, 4) + 0.0 for v in point)


def parts_digest(arms: str) -> str:
    """A digest of every part (name, pivot, end, order, all shape points to 1e-4) of the looks of
    :data:`LOOKS`, side and front views, drawn with ``arms``."""
    digest = hashlib.sha256()
    for name in sorted(LOOKS):
        for front in (False, True):
            for part in generate_parts(LOOKS[name], COLORS, front=front, arms=arms):
                digest.update(repr((part.name, _rounded(part.pivot), _rounded(part.end), part.order)).encode())
                for key in sorted(part.shapes):
                    for member in part.shapes[key].get_family():
                        digest.update((np.round(member.points, 4) + 0.0).tobytes())
    return digest.hexdigest()


#: :func:`parts_digest` of ``classic`` at Step 281 (db69328), when ``classic`` was the default.
CLASSIC_DIGEST = "74186fcf00744e83fedce63fdbb936ec5e10c911050ff3622844f72c4f482653"


def test_classic_is_the_drawing_of_before() -> None:
    assert parts_digest("classic") == CLASSIC_DIGEST
    assert parts_digest("front") != CLASSIC_DIGEST


def test_a_leaning_arm_still_reaches_its_point() -> None:
    c = build_character(CharacterEntry(name="e", look=LOOKS["lab_coat"]), theme=Theme(), height=3.0, arms="front")
    shoulder = c.shoulder_point("right")
    target = shoulder + np.array([-0.3, -0.5, 0.0])
    c.reach("right", target)
    assert np.allclose(c.hand_point("right")[:2], target[:2], atol=1e-6)


def test_the_look_wins_over_the_video() -> None:
    entry = CharacterEntry(name="m", look=CharacterLook(body="tall", arms="classic"))
    a = build_character(entry, theme=Theme(), arms="front")
    b = build_character(CharacterEntry(name="m", look=CharacterLook(body="tall")), theme=Theme(), arms="front")
    assert a.limb_rest("arm_right")[0] != b.limb_rest("arm_right")[0]
    assert build_character(entry, theme=Theme()).limb_rest("arm_right")[0] == a.limb_rest("arm_right")[0]
    front = CharacterEntry(name="m", look=CharacterLook(body="tall", arms="front"))
    assert build_character(front, theme=Theme(), arms="classic").limb_rest("arm_right")[0] == b.limb_rest("arm_right")[0]


def test_front_is_the_default_and_classic_opts_out() -> None:
    assert ARM_STYLES == ("classic", "front") and DEFAULT_ARMS == "front"
    assert parts_digest(DEFAULT_ARMS) == parts_digest("front")
    plain = CharacterEntry(name="m", look=CharacterLook(body="tall"))
    default, front = build_character(plain, theme=Theme()), build_character(plain, theme=Theme(), arms="front")
    classic = build_character(plain, theme=Theme(), arms="classic")
    assert default.limb_rest("arm_right")[0] == front.limb_rest("arm_right")[0] != classic.limb_rest("arm_right")[0]
    assert parse_config(minimal_config()).cartoon_arms is None   # unset: front
    assert parse_config(minimal_config(cartoon_arms="classic")).cartoon_arms == "classic"
    with pytest.raises(Exception):
        CharacterLook(arms="behind")
    with pytest.raises(VidgenError, match="arms must be one of"):
        generate_parts(CharacterLook(), COLORS, arms="behind")


@pytest.mark.parametrize("arms", [None, "classic"])
def test_cartoon_arms_reaches_the_host_and_api_character(make_project, arms: str | None) -> None:
    from test_host import built_scene, config
    from vidgen.api import character

    root = make_project(config(host="dot", **({} if arms is None else {"cartoon_arms": arms})))
    expected = {name: build_character(CharacterEntry(name=name), theme=Theme(), arms=arms or "front").limb_rest("arm_right")[0]
                for name in ("dot", "kit")}
    host = built_scene(root, (160, 90))[0].host.character   # the project stays active
    assert host.limb_rest("arm_right")[0] == expected["dot"]
    assert character("kit").limb_rest("arm_right")[0] == expected["kit"]   # a stage's cast is drawn by it
