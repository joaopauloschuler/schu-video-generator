"""Step 113: more bodies and clothes for generated characters (proportions, outfits, patterns,
shoes, hair, facial hair, accessories), and the pinned drawings of looks made before it."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Any, get_args

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from conftest import minimal_config
from vidgen.cartoon.acting import walk_cycle
from vidgen.cartoon.cast import character_part_shapes
from vidgen.cartoon.character import OUTER_HAIR_ATTRIBUTE, REQUIRED_PARTS, TRAIL_ATTRIBUTE, Character, build_character
from vidgen.cartoon.clothes import pattern_tone
from vidgen.cartoon.effect_symbols import crown_top, head_box
from vidgen.cartoon.generator import EXPRESSION_ONLY, TRAIL_WEIGHTS, generate_parts, resolve_proportions
from vidgen.cartoon.primitives import clip_to_box, dot_centres, span_at
from vidgen.cartoon.transition import walking_state
from vidgen.config import HEAD_ACCESSORIES, NECK_ACCESSORIES, SEATED_BODY_SHAPE, SKIRTED_OUTFITS, TOP_OF_HEAD, CharacterColors, CharacterEntry, CharacterLook
from vidgen.lint.color import hex_rgb, relative_luminance
from vidgen.project import Project
from vidgen.theme import Theme

#: Seven colours, one per colour key, in the order of COLOR_KEYS before Step 113 plus trim.
PIN_COLORS = {
    "skin": "#F2A541", "clothes": "#58C4DD", "outline": "#1F2430", "features": "#1F2430",
    "hair": "#FF6B6B", "accessory": "#FFD166", "trim": "#838B98",
}
#: Looks made before Step 113 whose drawings must not change (the default look, the six looks
#: `vidgen screenplay` gives, every accessory, a seed).
PINNED_LOOKS: dict[str, dict[str, Any]] = {
    "default": {},
    "screenplay_1": {"body": "round", "head_size": 1.15, "eyes": "round", "hair": "bun", "accessories": ["scarf"]},
    "screenplay_2": {"body": "tall", "eyes": "sleepy", "nose": "round", "hair": "short", "ears": "round", "accessories": ["glasses"]},
    "screenplay_3": {"body": "square", "head_size": 0.9, "eyes": "oval", "nose": "triangle", "hair": "spiky", "ears": "pointy", "accessories": ["hat"]},
    "screenplay_4": {"body": "bean", "head_size": 1.3, "eyes": "dot", "nose": "dot", "hair": "curly", "ears": "floppy", "accessories": ["bag"]},
    "screenplay_5": {"body": "round", "head_size": 0.85, "eyes": "oval", "hair": "long", "ears": "round", "accessories": ["glasses", "scarf"]},
    "screenplay_6": {"body": "tall", "head_size": 1.1, "eyes": "round", "nose": "dot", "hair": "none", "ears": "round", "accessories": ["hat", "bag"]},
    "everything": {"body": "bean", "hair": "long", "ears": "pointy", "accessories": ["glasses", "hat", "scarf", "bag"], "seed": 7},
}
#: :func:`drawing_digest` of each pinned look (side, front), taken at HEAD 095b596 before Step 113.
PINNED_DIGESTS: dict[str, tuple[str, str]] = {
    "default": ("59759d43bd197e3b", "ba3bdca01ddc9138"),
    "screenplay_1": ("adbe878ba8222049", "24c647b6626f774c"),
    "screenplay_2": ("1d5d94f4249a9aae", "56afd4afa907f513"),
    "screenplay_3": ("099968e0fd7de2f6", "725aacb5db6b73be"),
    "screenplay_4": ("93edd19acec8fcfa", "caefe7cdbba3bd73"),
    "screenplay_5": ("77bfa3f35ffdda31", "e5098133b084a9e1"),
    "screenplay_6": ("cf0cfd025434e33c", "ec8d9ea336fdca66"),
    "everything": ("dd19dc17041d37b7", "22be3085adb15e0b"),
}


def _number_bytes(values: Any) -> bytes:
    array = np.round(np.asarray(values, dtype=float), 6) + 0.0   # + 0.0 turns -0.0 into 0.0
    return array.tobytes()


def drawing_digest(look: CharacterLook, *, front: bool = False) -> str:
    """A digest of everything the generator draws for ``look``: every part's name, pivot, end,
    parent, order and shapes, each drawn member's points, fill, stroke and trailing mark; the
    Step 125 parts and shapes (``EXPRESSION_ONLY``, added after every earlier shape) left out,
    so the pins taken before it still hold for everything drawn before it."""
    digest = hashlib.sha256()
    for part in generate_parts(look, PIN_COLORS, front=front):
        new_shapes = EXPRESSION_ONLY.get(part.name, frozenset())
        if set(part.shapes) <= new_shapes:
            continue
        digest.update(repr((part.name, part.parent, part.order)).encode())
        digest.update(_number_bytes(part.pivot) + _number_bytes(part.end if part.end is not None else ()))
        for shape_name, shape in part.shapes.items():
            if shape_name in new_shapes:
                continue
            digest.update(shape_name.encode())
            for member in shape.family_members_with_points():
                digest.update(_number_bytes(member.points))
                style = (member.get_fill_color().to_hex(), member.get_fill_opacity(), member.get_stroke_color().to_hex(),
                         member.get_stroke_width(), member.get_stroke_opacity())
                digest.update(repr(style).encode())
                trail = getattr(member, TRAIL_ATTRIBUTE, None)
                digest.update(_number_bytes(trail if trail is not None else ()))
    return digest.hexdigest()[:16]


@pytest.mark.parametrize("name", PINNED_LOOKS)
def test_looks_made_before_keep_their_drawings(name: str) -> None:
    look = CharacterLook(**PINNED_LOOKS[name])
    assert (drawing_digest(look), drawing_digest(look, front=True)) == PINNED_DIGESTS[name]


# ----- sampled combinations ---------------------------------------------------------------------

#: The look parameters with a list of values (accessories are sampled as a subset).
CHOICES = ("body", "eyes", "nose", "hair", "ears", "proportions", "outfit", "pattern", "shoes", "facial_hair")
ACCESSORIES: tuple[str, ...] = get_args(get_args(CharacterLook.model_fields["accessories"].annotation)[0])


def sampled_looks(count: int, seed: int = 113) -> list[dict[str, Any]]:
    """``count`` looks drawn at random (seeded) from every parameter's values, each with up to
    three accessories (never two worn on top of the head: the first one drawn is kept) and every
    third with a seed."""
    rng = random.Random(seed)
    looks = []
    for k in range(count):
        values: dict[str, Any] = {name: rng.choice(get_args(CharacterLook.model_fields[name].annotation)) for name in CHOICES}
        chosen = rng.sample(ACCESSORIES, rng.randint(0, 3))
        on_top = [a for a in chosen if a in TOP_OF_HEAD]
        round_neck = [a for a in chosen if a in NECK_ACCESSORIES]   # one thing round the neck
        values["accessories"] = [a for a in chosen if a not in on_top[1:] and a not in round_neck[1:]]
        values["head_size"] = round(rng.uniform(0.7, 1.4), 2)
        if k % 3 == 0:
            values["seed"] = k
        looks.append(values)
    return looks


def built(values: dict[str, Any], height: float = 1.0) -> Character:
    look = CharacterLook(**values)
    return Character(generate_parts(look, PIN_COLORS), name="t", height=height, front=generate_parts(look, PIN_COLORS, front=True))


@pytest.mark.parametrize("values", sampled_looks(24), ids=lambda v: f"{v['body']}-{v['outfit']}-{v['hair']}")
def test_sampled_combinations_build_pose_and_face_front(values: dict[str, Any]) -> None:
    c = built(values, height=2.0)
    assert set(REQUIRED_PARTS) <= set(c.parts)
    assert c.get_bottom()[1] == pytest.approx(0) and c.get_top()[1] == pytest.approx(2.0)   # shoes on the ground, top at the height
    skirted = values["outfit"] in SKIRTED_OUTFITS
    assert c.shape_names("body") == (["default", SEATED_BODY_SHAPE] if skirted else ["default"])
    assert c.has_part("accessory") == bool(HEAD_ACCESSORIES & set(values["accessories"]))
    entry = CharacterEntry(name="t", look=values)
    assert {part: c.shape_names(part) for part in c.parts} == character_part_shapes(entry, Path("."))   # validate knows the shapes
    for pose in ("sitting", "waving", "arms_crossed"):
        c.set_pose(pose)
    assert c.shown_shape("body") == "default"
    c.face("front").set_pose("sitting")
    assert c.shown_shape("body") == (SEATED_BODY_SHAPE if skirted else "default")
    c.set_state(walking_state(c.posed_state(pose="stand"), walk_cycle(0.5), "front"))
    c.face("left").set_state(walking_state(c.state(), walk_cycle(1.5), "left"))


def test_the_same_parameters_give_the_same_shapes() -> None:
    for values in sampled_looks(4, seed=7):
        assert drawing_digest(CharacterLook(**values)) == drawing_digest(CharacterLook(**values))
        assert drawing_digest(CharacterLook(**values), front=True) == drawing_digest(CharacterLook(**values), front=True)
    base = {"body": "pear", "hair": "braids", "outfit": "dress", "pattern": "dots", "shoes": "boots", "accessories": ["bow"]}
    digests = {drawing_digest(CharacterLook(**base))}
    for change in ({"outfit": "coat"}, {"pattern": "stripes"}, {"shoes": "shoes"}, {"hair": "afro"}, {"facial_hair": "beard"},
                   {"proportions": "kid"}, {"body": "triangle"}, {"accessories": ["cap", "necklace", "backpack"]}):
        digest = drawing_digest(CharacterLook(**{**base, **change}))
        assert digest not in digests, change   # every parameter changes the drawing
        digests.add(digest)


# ----- bodies, kids and seats ---------------------------------------------------------------------


def test_kid_proportions() -> None:
    adult, kid, tall = (resolve_proportions(CharacterLook(proportions=p)) for p in ("adult", "kid", "tall_kid"))
    assert kid.head_radius > tall.head_radius > adult.head_radius
    assert kid.leg_length < adult.leg_length and kid.body_height < tall.body_height < adult.body_height
    shares = {}
    for proportions in ("adult", "kid", "tall_kid"):
        c = built({"proportions": proportions})
        head_low, head_top = c.part_box("head")[1], c.part_box("head")[3]
        shares[proportions] = (head_top - head_low, c.hip_height())
    assert shares["kid"][0] > shares["tall_kid"][0] > shares["adult"][0]   # the head is a bigger share of the figure
    assert shares["kid"][1] < shares["adult"][1]                            # and the hips lower


@pytest.mark.parametrize("values", [
    {"proportions": "kid", "outfit": "dress"}, {"proportions": "tall_kid", "body": "tall", "outfit": "coat"},
    {"body": "pear", "outfit": "shorts"}, {"body": "triangle", "outfit": "overalls", "shoes": "boots"},
], ids=lambda v: "-".join(str(x) for x in v.values()))
def test_hips_stay_on_the_seat(values: dict[str, Any]) -> None:
    """Seats are 0.14 of a grown-up's height above the ground (Step 102): a kid on the stage at
    scale 0.7 meets a seat 0.2 of its own height up, above its hips; its hips still go on it."""
    for seat in (0.14, 0.2):
        c = built(values)
        c.set_state(c.seated(c.state(), seat))
        hips = (c.pivot("leg_left")[1] - c.feet()[1]) / c.character_height
        assert hips == pytest.approx(seat, abs=1e-6)
        assert min(y for _, y in c.sole_points().values()) >= -1e-6   # feet on the ground or hanging
        assert c.shown_shape("body") == (SEATED_BODY_SHAPE if values["outfit"] in SKIRTED_OUTFITS else "default")


def test_shoulders_of_a_pear_sit_on_its_narrow_top() -> None:
    pear, round_ = built({"body": "pear"}), built({"body": "round"})
    assert pear.limb_rest("arm_left")[0][0] < round_.limb_rest("arm_left")[0][0]
    body = pear.part_box("body")
    assert pear.limb_rest("arm_left")[0][0] < 0.42 * (body[2] - body[0])


# ----- clothes on the limbs ----------------------------------------------------------------------


def fills(c: Character, part: str) -> set[str]:
    return {m.get_fill_color().to_hex().upper() for m in c.parts[part].family_members_with_points() if m.get_fill_opacity() > 0}


@pytest.mark.parametrize(("outfit", "upper_arm", "forearm", "thigh", "shin"), [
    ("plain", "clothes", "clothes", "clothes", "clothes"),
    ("dress", "clothes", "skin", "skin", "skin"),
    ("overalls", "trim", "trim", "clothes", "clothes"),
    ("coat", "clothes", "clothes", "trim", "trim"),
    ("shorts", "clothes", "skin", "trim", "skin"),
    ("apron", "clothes", "clothes", "clothes", "clothes"),
])
def test_sleeves_and_trouser_legs_follow_the_segments(outfit: str, upper_arm: str, forearm: str, thigh: str, shin: str) -> None:
    c = built({"outfit": outfit})
    assert PIN_COLORS[upper_arm] in fills(c, "arm_left") and PIN_COLORS[forearm] in fills(c, "arm_left_lower")
    assert fills(c, "leg_left") == {PIN_COLORS[thigh]} and PIN_COLORS[shin] in fills(c, "leg_left_lower")


def test_shoes_are_on_the_shins_with_the_sole_on_the_ground() -> None:
    for shoes in ("shoes", "boots"):
        for front in (False, True):
            c = built({"shoes": shoes})
            if front:
                c.face("front")
            assert PIN_COLORS["accessory"] in fills(c, "leg_right_lower")
            assert c.part_box("leg_left_lower")[1] == pytest.approx(0.0, abs=1e-9)
    boots, shoes = built({"shoes": "boots"}), built({"shoes": "shoes"})
    assert boots.part_box("leg_left_lower")[2] > built({}).part_box("leg_left_lower")[2]   # the toe forward
    lifted = shoes.part_box("leg_left_lower")
    shoes.plant("left", shoes.feet() + np.array([0.1, 0.05, 0.0]))   # the shoe goes with the foot
    assert shoes.part_box("leg_left_lower")[1] > lifted[1] + 0.02


def test_a_skirt_hangs_from_the_body_and_lies_on_the_lap_when_seated() -> None:
    def lowest(c: Character) -> np.ndarray:
        points = np.vstack([m.points for m in c.parts["body"].family_members_with_points()])
        return (points[points[:, 1].argmin()] - c.feet()) / c.character_height

    c = built({"outfit": "dress"})
    knee = c.limb_rest("leg_left")[0][1] - c.limb_rest("leg_left")[1]
    hem = lowest(c)
    assert abs(hem[0]) < 0.01 and hem[1] < knee + 0.02   # the hem round the knees, below the hips
    c.set_state(c.seated(c.state(), 0.14))
    lap = lowest(c)
    assert lap[0] > 0.04 and lap[1] > 0.0   # the cloth goes forward over the lap, down towards the knees
    plain = built({})
    plain.set_state(plain.seated(plain.state(), 0.14))
    assert plain.shown_shape("body") == "default"


def test_pattern_tone_and_patterns() -> None:
    light, dark = pattern_tone("#FFD166"), pattern_tone("#2B2B2B")
    assert relative_luminance(hex_rgb(light)) < relative_luminance(hex_rgb("#FFD166"))
    assert relative_luminance(hex_rgb(dark)) > relative_luminance(hex_rgb("#2B2B2B"))
    plain, striped, dotted = (len(built({"pattern": p}).parts["body"].family_members_with_points()) for p in ("none", "stripes", "dots"))
    assert striped > plain + 3 and dotted > plain + 10
    for p in ("stripes", "dots"):
        c = built({"pattern": p, "body": "bean"})
        pieces = [m for m in c.parts["body"].family_members_with_points() if m.get_stroke_width() == 0]
        body = c.part_box("body")
        assert all(body[0] - 1e-6 <= m.get_left()[0] and m.get_right()[0] <= body[2] + 1e-6 for m in pieces)


def test_outline_maths() -> None:
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    band = clip_to_box(square, bottom=0.25, top=0.5)
    assert sorted({round(y, 9) for _, y in band}) == [0.25, 0.5] and sorted({x for x, _ in band}) == [0.0, 1.0]
    assert clip_to_box(square, left=2.0) == []
    assert span_at(square, 0.5) == (0.0, 1.0) and span_at(square, 2.0) is None
    dots = dot_centres(square, 0.2, 0.05, 0.01)
    assert dots and all(0.06 <= x <= 0.94 and 0.06 <= y <= 0.94 for x, y in dots)


# ----- hair, facial hair, accessories ----------------------------------------------------------


def trail_weights(c: Character) -> set[float]:
    return {round(getattr(m, TRAIL_ATTRIBUTE)[2], 2) for part in c.parts.values() for m in part.get_family() if getattr(m, TRAIL_ATTRIBUTE, None)}


def test_hanging_hair_and_accessories_trail_in_the_wind() -> None:
    for hair in ("ponytail", "braids"):
        c = built({"hair": hair, "accessories": ["cap", "necklace"]})
        assert trail_weights(c) == {TRAIL_WEIGHTS[k] for k in (hair, "cap", "pendant")}
        before = np.vstack([m.points for m in c.parts["head"].family_members_with_points()]).copy()
        c.set_wind(30.0)
        after = np.vstack([m.points for m in c.parts["head"].family_members_with_points()])
        assert not np.allclose(before, after)
    assert trail_weights(built({"hair": "afro", "accessories": ["bow", "backpack"], "facial_hair": "beard"})) == set()


def test_effect_symbols_go_by_the_head_and_above_hair_beyond_it() -> None:
    for hair in ("afro", "braids", "ponytail"):
        c = built({"hair": hair, "facial_hair": "beard"}, height=3.0)
        head = c.parts["head"]
        box = head_box(c)
        assert box[3] - box[1] < head.height - 1e-6   # the head itself, not the hair round it
        top = crown_top(c)
        assert top is not None   # symbols above go above the higher of it and the head (effects.spot_at)
        if hair == "afro":
            assert top == pytest.approx(head.get_top()[1])   # the afro's top
    long_hair = built({"hair": "long", "accessories": ["glasses"]}, height=3.0)   # looks before Step 113 as before
    head = long_hair.parts["head"]
    assert head_box(long_hair) == (head.get_left()[0], head.get_bottom()[1], head.get_right()[0], head.get_top()[1])
    capped = built({"accessories": ["cap"]}, height=3.0)
    assert crown_top(capped) == pytest.approx(capped.parts["accessory"].get_top()[1])
    assert crown_top(built({"hair": "short"})) is None


def test_beard_and_moustache_leave_the_mouth_seen() -> None:
    bald = built({"hair": "none", "facial_hair": "beard"})
    head_fills = [m.get_fill_color().to_hex().upper() for m in bald.parts["head"].family_members_with_points()]
    assert PIN_COLORS["hair"] in head_fills and head_fills.count(PIN_COLORS["skin"]) >= 2   # the head and the patch round the mouth
    mouth = bald.part_box("mouth")
    beard = [m for m in bald.parts["head"].family_members_with_points() if getattr(m, OUTER_HAIR_ATTRIBUTE, False)]
    assert beard and min(m.get_bottom()[1] for m in beard) < mouth[1]   # the beard goes below the mouth
    moustache = built({"facial_hair": "moustache"})
    assert len(moustache.parts["head"].family_members_with_points()) == len(built({}).parts["head"].family_members_with_points()) + 2


def test_look_schema() -> None:
    with pytest.raises(ValidationError, match="hat and cap"):
        CharacterLook(accessories=["hat", "cap"])
    with pytest.raises(ValidationError, match="svg draws the character"):
        CharacterLook(svg="a.svg", outfit="dress")
    assert CharacterColors().trim == "dim"
    shapes = character_part_shapes(CharacterEntry(name="t", look={"outfit": "coat", "accessories": ["bow"]}), Path("."))
    assert shapes["body"] == ["default", SEATED_BODY_SHAPE] and shapes["accessory"] == ["default"]


# ----- screenplay looks and voice kinds -----------------------------------------------------------


def test_screenplay_looks_keep_a_voice_kind_and_use_the_new_clothes() -> None:
    from vidgen.screenplay import LOOKS, VOICE_KINDS

    assert all(look["voice_kind"] in VOICE_KINDS for look in LOOKS)
    new = LOOKS[6:]
    assert {look["voice_kind"] for look in new} == set(VOICE_KINDS)
    for look in new:
        entry = CharacterEntry(name="t", look=look["look"], colors=look["colors"])
        assert entry.look.outfit != "plain"
        build_character(entry, theme=Theme(), height=1.0)
    digests = {drawing_digest(CharacterLook(**look["look"])) for look in LOOKS}
    assert len(digests) == len(LOOKS)


# ----- renders --------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_dressed_cast_sits_walks_and_shows_a_symbol_on_a_stage(make_project, tmp_path: Path) -> None:
    """A kid in a dress sits on the chair (its skirt over the lap); a character with an afro
    gets an idea symbol above the afro."""
    from test_cartoon_stage import render_with_layout
    from vidgen.introspect import LayoutRecorder

    cast = [
        {"name": "pip", "voice": "pip_voice", "look": {"proportions": "kid", "hair": "ponytail", "outfit": "dress", "pattern": "dots", "shoes": "shoes"}},
        {"name": "kit", "voice": "kit_voice", "look": {"hair": "afro", "outfit": "overalls", "facial_hair": "beard", "accessories": ["cap", "backpack"]}},
    ]
    params = {"idle": False, "wind": "breeze", "characters": [{"name": "pip", "at": 0.25, "scale": 0.7}, {"name": "kit", "at": "right"}],
              "props": [{"prop": "chair", "at": 0.35}]}
    beats = [
        {"text": "Pip sits down.", "voice": "pip_voice", "actions": [{"sit_on": "pip", "to": "chair"}, {"effect": "kit", "to": "idea"}]},
        {"text": "Kit walks over.", "voice": "kit_voice", "actions": [{"walk_to": "kit", "to": 0.6}]},
    ]
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": beats}]
    project = Project.load(make_project(minimal_config(characters=cast, voices={"pip_voice": {"voice_id": "p1"}, "kit_voice": {"voice_id": "k1"}}, scenes=scenes)))
    recorder = LayoutRecorder()
    scene, objects = render_with_layout(project, "park", tmp_path / "media", recorder)
    first = {o["name"]: o for o in objects if o["name"]}
    assert first["pip"]["sitting_on"] == "chair"
    idea = next(o for o in objects if o["kind"] == "effect")
    assert idea["bbox"][3] <= first["kit"]["bbox"][1] + 1   # above the afro (y grows down in the dump)
    assert scene.cast["pip"].shown_shape("body") == SEATED_BODY_SHAPE


@pytest.mark.render
def test_the_look_gallery_still(tmp_path: Path) -> None:
    from vidgen.cartoon.still import write_looks_png

    entries = [CharacterEntry(name="a", look={"outfit": "coat", "hair": "afro"}), CharacterEntry(name="b", look={"proportions": "kid"})]
    path = write_looks_png(Theme(), tmp_path / "docs" / "looks.png", entries, columns=2, cell_width=40, cell_height=70)
    with Image.open(path) as image:
        assert image.size == (160, 70) and image.mode == "P"
        pixels = np.asarray(image.convert("RGB"), dtype=int)
    drawn = np.any(np.abs(pixels - pixels[0, 0]) > 30, axis=2)
    assert [drawn[:, k * 40:(k + 1) * 40].any() for k in range(4)] == [True] * 4   # each look from the side and the front


@pytest.mark.render
def test_the_sheet_shows_the_front_view(make_project) -> None:
    from vidgen import extensions
    from vidgen.cartoon.still import write_character_sheet

    cast = [{"name": "ada", "look": {"body": "pear", "hair": "braids", "outfit": "apron", "shoes": "boots", "accessories": ["bow"]}}]
    project = Project.load(make_project(minimal_config(characters=cast)))
    theme = extensions.activate(project)
    sheet = write_character_sheet(project, project.config.characters[0], theme)
    assert [s.kind for s in sheet.sections] == ["pose", "expression", "mouth", "view"]
    assert sheet.sections[-1].names == ("front",)
    assert Image.open(sheet.path).size == (sheet.width, sheet.height)
