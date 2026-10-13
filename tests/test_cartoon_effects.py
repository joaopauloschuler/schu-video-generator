"""Step 107: effect symbols over characters (``effect``): placement per head size and facing,
timing (pop, motion, exit), the symbols' shapes, their sounds, the ``auto_direct`` rules, the
screenplay grammar, the lint and layout dump keys, and one tiny render."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_cartoon_acting import acting_project, figure
from test_cartoon_directing import TRIO, beat, plan
from test_cartoon_lint import check, fig
from test_cartoon_stage import render_with_layout
from test_screenplay import stage
from vidgen import extensions
from vidgen.cli import check_project
from vidgen.cartoon.effects import (
    ALTERNATE_SPOTS,
    EFFECT_KINDS,
    EFFECT_STYLES,
    EXIT_SECONDS,
    POP_SECONDS,
    effect_pieces,
    effect_spot,
    exit_scale,
    piece_center,
    piece_pose,
    pop_scale,
    spot_at,
    thick_path,
)
from vidgen.cartoon.foley import EFFECT_SOUNDS, PlayedAction, foley_cues
from vidgen.config import AutoDirect, directing_kinds
from vidgen.screenplay import direction_actions

HEAD = (-0.5, 1.0, 0.5, 2.0)   # a head 1 wide and 1 tall, its middle at x 0


# ----- placement (no manim) --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", EFFECT_KINDS)
def test_placement_scales_with_the_head_and_mirrors_with_the_facing(kind: str) -> None:
    right = effect_spot(kind, HEAD, "right")
    left = effect_spot(kind, HEAD, "left")
    assert right.size == pytest.approx(EFFECT_STYLES[kind].size) and right.spot == EFFECT_STYLES[kind].spot
    assert left.x == pytest.approx(-right.x) and left.y == pytest.approx(right.y) and left.size == right.size
    big = effect_spot(kind, (-1.0, 2.0, 1.0, 4.0), "right")   # the head twice as big, its middle 2 higher
    assert big.size == pytest.approx(2 * right.size)
    assert big.x == pytest.approx(2 * right.x) and big.y - 3.0 == pytest.approx(2 * (right.y - 1.5))


def test_where_each_spot_is() -> None:
    above, front, back = (spot_at(s, "idea", HEAD, "right") for s in ("above", "front", "back"))
    assert above.box()[1] > HEAD[3] and abs(above.x) < 0.2               # over the head
    assert front.box()[0] > HEAD[2] and back.x < HEAD[0] < back.box()[2]   # beside it, the back one overlapping its edge
    assert spot_at("corner", "anger", HEAD, "right").x > 0 > spot_at("corner", "anger", HEAD, "left").x
    hat = spot_at("above", "idea", HEAD, "right", crown=2.6)              # a hat: over it, the size by the head
    assert hat.y == pytest.approx(above.y + 0.6) and hat.size == above.size
    tear = spot_at("eye", "tear", HEAD, "right", eye=(0.3, 1.6))
    assert tear.y < 1.6 and tear.x == pytest.approx(0.3 + 0.15 * tear.size)
    with pytest.raises(ValueError, match="unknown spot"):
        spot_at("elbow", "idea", HEAD, "right")
    with pytest.raises(ValueError, match="unknown effect"):
        effect_spot("rainbow", HEAD, "right")


def test_a_speech_bubble_moves_the_symbol_to_another_spot() -> None:
    bubble = (-1.0, 2.3, 0.6, 3.0)   # a bubble over the head
    moved = effect_spot("question", HEAD, "right", avoid=[bubble])
    assert moved.spot == ALTERNATE_SPOTS["above"][0] == "front"
    everywhere = [(-9.0, -9.0, 9.0, 9.0)]
    assert effect_spot("question", HEAD, "right", avoid=everywhere).spot == "above"   # nowhere free: its own
    assert effect_spot("stars", HEAD, "right", avoid=everywhere).spot == "ring"       # a spot with no other
    over_corner = (0.0, 1.7, 0.6, 2.4)
    assert effect_spot("anger", HEAD, "right", avoid=[over_corner]).spot == "front"


# ----- timing and shapes (no manim) --------------------------------------------------------------------


def test_the_pop_bounces_settles_and_the_exit_shrinks() -> None:
    assert pop_scale(0.0) == 0.0 == pop_scale(-1.0)
    lively = [pop_scale(k / 100) for k in range(1, 200)]
    assert max(lively) > 1.15 and pop_scale(2.0) == pytest.approx(1.0, abs=0.02)   # overshoots, then settles
    calm = [pop_scale(k / 100, strength=0.0) for k in range(1, 200)]
    assert max(calm) == pytest.approx(1.0) and pop_scale(POP_SECONDS, strength=0.0) == pytest.approx(1.0)
    assert calm == sorted(calm)   # cartoon_motion none: an eased grow, no bounce
    assert exit_scale(0.0) == 1.0 and exit_scale(EXIT_SECONDS) == 0.0 and 0 < exit_scale(EXIT_SECONDS / 2) < 1


@pytest.mark.parametrize("kind", EFFECT_KINDS)
def test_pieces_are_closed_counterclockwise_outlines_that_move_repeatably(kind: str) -> None:
    pieces = effect_pieces(kind)
    assert pieces
    for piece in pieces:
        for shape in piece.shapes:
            points = shape.points
            area = 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, [*points[1:], points[0]]))
            assert len(points) >= 3 and area > 0
            assert all(abs(x) <= 0.8 and abs(y) <= 0.8 for x, y in points)   # about 1 tall round its middle
    for k in range(len(pieces)):
        assert [piece_pose(kind, k, t / 10) for t in range(30)] == [piece_pose(kind, k, t / 10) for t in range(30)]
        right, left = piece_center(kind, k, 0.7, "right"), piece_center(kind, k, 0.7, "left")
        assert left == pytest.approx((-right[0], right[1]))


def test_the_motions() -> None:
    assert piece_pose("sweat", 0, 3.0).dy == pytest.approx(-0.25) and piece_pose("sweat", 0, 0.0).dy == 0.0   # slides down, stays
    zs = [piece_pose("sleep", k, 0.5) for k in range(3)]
    assert len({round(z.dy, 6) for z in zs}) == 3   # the Zs rise one after another
    assert piece_pose("sleep", 0, 0.0).scale == 0.0   # each starts small
    orbit = [piece_center("stars", 0, t / 20, "right") for t in range(33)]
    assert max(p[0] for p in orbit) > 0.5 > -0.5 > min(p[0] for p in orbit)   # round the head
    assert piece_pose("exclaim", 0, 3.0).angle == pytest.approx(0.0, abs=0.1)   # the shake calms down
    assert piece_pose("tear", 0, 0.5).dy < piece_pose("tear", 0, 0.2).dy < 0   # runs down the cheek
    with pytest.raises(ValueError):
        piece_pose("rainbow", 0, 0.0)


def test_thick_path_is_a_band_round_the_path() -> None:
    band = thick_path([(0.0, 0.0), (1.0, 0.0)], 0.2)
    assert sorted(band) == sorted([(0.0, 0.1), (1.0, 0.1), (1.0, -0.1), (0.0, -0.1)])
    with pytest.raises(ValueError):
        thick_path([(0.0, 0.0)], 0.2)


# ----- sounds (no manim) -------------------------------------------------------------------------------


def test_symbols_sound_as_they_pop_up() -> None:
    (ding,) = foley_cues(PlayedAction("effect", 2.0, 0.4, effect="idea"))
    assert (ding.sound, ding.time, ding.gain) == ("chime", 2.0, EFFECT_SOUNDS["idea"][1]) and ding.params["duration"] == 0.5
    assert foley_cues(PlayedAction("effect", 2.0, 0.4, effect="sleep")) == []   # a quiet one
    assert foley_cues(PlayedAction("effect", 2.0, 0.4)) == []                   # sound: false
    extensions.load_builtins()
    from vidgen import sfx

    for sound, _, params in EFFECT_SOUNDS.values():   # every one is a built-in sound with valid params
        assert sound in sfx.BUILTIN_SOUNDS
        lo, hi = sfx.BUILTIN_SOUNDS[sound].duration_range
        assert lo <= params.get("duration", sfx.BUILTIN_SOUNDS[sound].duration) <= hi


# ----- automatic directing (no manim) --------------------------------------------------------------------

EFFECTS = frozenset({"effects"})


def test_auto_direct_marks_a_strong_change_of_expression() -> None:
    assert "effects" in directing_kinds(None, None, True) and "effects" not in directing_kinds(AutoDirect(effects=False))
    added = plan([
        beat("b1", "Look out!", ("pip",), [{"emote": "kit", "to": "surprised", "at": 0.3}], kinds=EFFECTS),
        beat("b2", "Hmm.", ("pip",), [{"react": "kit", "expression": "thinking"}, {"emote": "rex", "to": "angry"}], kinds=EFFECTS),
        beat("b3", "Hi.", ("pip",), [{"emote": "kit", "to": "happy"}], kinds=EFFECTS),   # not a strong one
        beat("b4", "Grr.", ("pip",), [{"emote": "kit", "to": "angry"}, {"effect": "pip", "to": "sweat"}], kinds=EFFECTS),   # written wins
        beat("b5", "Grr.", ("pip",), [{"emote": "kit", "to": "angry"}], kinds=frozenset()),   # off
    ])
    assert added == {
        "b1": [{"effect": "kit", "to": "exclaim", "at": 0.3}],
        "b2": [{"effect": "kit", "to": "question"}],   # at most one per line: the first change
    }


def test_auto_direct_marks_its_own_reactions_once_per_line() -> None:
    kinds = frozenset({"reactions", "effects"})
    added = plan([beat("b1", "What is it?", ("pip",), kinds=kinds)])
    reactions = [a for a in added["b1"] if "react" in a]
    effects = [a for a in added["b1"] if "effect" in a]
    marked = [a for a in reactions if a["expression"] in ("surprised", "thinking")]
    assert len(effects) == 1 and effects[0]["effect"] == marked[0]["react"] and effects[0]["at"] == marked[0]["at"]
    assert effects[0]["to"] == {"surprised": "exclaim", "thinking": "question"}[marked[0]["expression"]]


def test_no_symbol_for_a_character_off_stage() -> None:
    added = plan([
        beat("b1", "Hello.", ("pip",), [{"emote": "rex", "to": "surprised"}], kinds=EFFECTS),   # rex waits off stage
        beat("b2", "Here.", ("rex",), [{"enter": "rex"}, {"emote": "rex", "to": "surprised", "at": 0.5}], kinds=EFFECTS),
    ], TRIO)
    assert added == {"b2": [{"effect": "rex", "to": "exclaim", "at": 0.5}]}


# ----- screenplay (no manim) ------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "kind"), [
    ("Wren has an idea", "idea"), ("Wren gets a bright idea", "idea"), ("Wren looks confused", "question"),
    ("Wren is startled", "exclaim"), ("Wren sweats", "sweat"), ("Wren is furious", "anger"), ("Wren falls asleep", "sleep"),
    ("Wren nods off", "sleep"), ("Wren falls in love with Ash", "hearts"), ("Wren sees stars", "stars"),
    ("Wren sparkles", "sparkle"), ("Wren cries", "tear"),
])
def test_screenplay_directions_put_up_symbols(text: str, kind: str) -> None:
    groups, unmatched = direction_actions(text, stage())
    assert unmatched == [] and [{k: v for k, v in a.items() if not k.startswith("_")} for g in groups for a in g] == [{"effect": "wren", "to": kind}]


def test_screenplay_inline_symbol_and_one_after_a_walk() -> None:
    groups, _ = direction_actions("has an idea", stage(), "wren")
    assert groups[0][0]["effect"] == "wren"
    groups, _ = direction_actions("Wren walks to the light and falls asleep", stage())
    assert [next(iter(a)) for g in groups for a in g] == ["walk_to", "effect"]


# ----- lint and the layout dump (no render) -------------------------------------------------------------


def symbol(box: list[float], of: str = "pip", effect: str = "idea", order: int = 20) -> dict[str, Any]:
    return {"id": f"e{order}", "kind": "effect", "class": "EffectSymbol", "name": effect, "path": f"EffectSymbol[{order}]", "bbox": box,
            "opacity": 1.0, "z": 1.0, "order": order, "parts": 4, "effect": effect, "effect_of": of}


def bubble_obj(box: list[float], speaker: str = "kit") -> dict[str, Any]:
    return {"id": "b", "kind": "group", "class": "VGroup", "name": None, "path": "VGroup[30]", "bbox": box, "opacity": 1.0,
            "z": 2.0, "order": 30, "parts": 2, "bubble": speaker}


def test_bubble_overlap_reports_a_bubble_over_a_symbol() -> None:
    idea = symbol([100, 40, 140, 80])
    (issue,) = check("bubble_overlap", [idea, bubble_obj([90, 30, 300, 90])])
    assert issue.message.startswith("the speech bubble of character 'kit' covers the effect 'idea' of character 'pip' (100% of the symbol)")
    assert check("bubble_overlap", [idea, bubble_obj([200, 30, 300, 90])]) == []


def test_a_symbol_does_not_hide_its_speaker() -> None:
    speaker = fig("pip", [100, 100, 200, 400], order=5, speaking=True, face=[110, 100, 190, 200])
    assert check("hidden_speaker", [speaker, symbol([110, 100, 190, 200], effect="tear")]) == []


# ----- the symbol follows the character (manim, no render) ----------------------------------------------


def test_the_symbol_follows_the_head_and_leaves_the_character_alone() -> None:
    from vidgen.cartoon.effect_symbols import EffectSymbol, head_box

    pip = figure()
    family = list(pip.get_family())
    idea = EffectSymbol("idea", color="#FFD166", character_height=pip.character_height)
    idea.follow(pip)
    assert idea.age == 0.0 and not idea.family_members_with_points()   # popped to nothing yet
    for _ in range(20):
        idea.update(1 / 30)
    top = head_box(pip)[3]
    assert idea.get_bottom()[1] > top and idea.effect_of == "pip"
    before = idea.get_center()
    pip.shift([2.0, 0.5, 0.0])   # a walk, a jump
    idea.update(1 / 30)
    assert idea.get_center()[:2] == pytest.approx(before[:2] + [2.0, 0.5], abs=0.05)
    assert list(pip.get_family()) == family   # nothing added to the character (DESIGN.md §69.22)
    sweat = EffectSymbol("sweat", color="#58C4DD", character_height=pip.character_height).follow(pip)
    sweat.update(0.5)
    pip.face("left")
    sweat.update(0.0)
    x0, _, x1, _ = head_box(pip)
    assert sweat.get_center()[0] > (x0 + x1) / 2   # behind the head: now on its right
    idea.leaving = idea.age
    idea.update(1.0)
    assert not idea.family_members_with_points()   # shrunk away


# ----- validate -------------------------------------------------------------------------------------------


def test_validate_effect_actions(make_project) -> None:
    ok = [{"text": "Oh!", "actions": [{"effect": "pip", "to": "idea"}, {"action": "effect", "target": ["pip", "kit"], "to": "hearts", "until": "park_b2"}]},
          {"text": "Ah."}]
    assert check_project(acting_project(make_project, ok)) == []
    bad = [{"text": "Oh!", "actions": [{"effect": "tree", "to": "tear"}, {"effect": "kit", "to": "rainbow"}, {"effect": "pip"}]}]
    problems = check_project(acting_project(make_project, bad))
    where = "scenes[0].beats[0].actions"
    assert problems[0].startswith(f"{where}[0].target: 'tree' is not a character; effect acts on characters"), problems
    assert problems[1].startswith(f"{where}[1].to") and "sweat" in problems[1], problems
    assert problems[2].startswith(f"{where}[2].to") and len(problems) == 3, problems


# ----- one render --------------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_stage_shows_and_sounds_a_symbol(make_project, tmp_path: Path) -> None:
    from vidgen.introspect import LayoutRecorder

    beats: list[dict[str, Any]] = [
        {"text": "Pip has a very good idea about the kite.", "voice": "pip_voice",
         "actions": [{"effect": "pip", "to": "idea"}, {"effect": "kit", "to": "sleep", "sound": False}]},
        {"text": "And now it is gone again.", "voice": "kit_voice"},
    ]
    project = acting_project(make_project, beats)
    recorder = LayoutRecorder()
    scene, objects = render_with_layout(project, "park", tmp_path / "media", recorder)
    effects = [o for o in recorder.frames[0]["objects"] if o["kind"] == "effect"]
    assert {(o["effect"], o["effect_of"]) for o in effects} == {("idea", "pip"), ("sleep", "kit")}
    pip = next(o for o in recorder.frames[0]["objects"] if o.get("name") == "pip" and o["kind"] == "character")
    idea = next(o for o in effects if o["effect"] == "idea")
    assert idea["bbox"][3] <= pip["bbox"][1] + 1   # above pip's head (y grows down in the dump)
    assert not [o for o in recorder.frames[-1]["objects"] if o["kind"] == "effect"]   # gone in the next beat
    assert [e.sound for e in scene.sfx_log if e.sound == "chime"] == ["chime"]   # the idea's ding, the Zs silent
    assert not [m for m in scene.mobjects if type(m).__name__ == "EffectSymbol"]
    quiet = acting_project(make_project, beats, foley=False)
    scene, _ = render_with_layout(quiet, "park", tmp_path / "media2")
    assert scene.sfx_log == []
