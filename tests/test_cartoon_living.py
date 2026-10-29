"""Step 120: props that move by themselves, indoors (DESIGN.md §69.54): a running clock's hands, a
television's flickering picture, a lamp's glow, the switch_on / switch_off actions, and what Manim
redraws on every frame for them. Two tiny renders: a prop switched on later is drawn as before
until then, and a running clock changes nothing outside its own box."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen.cartoon.living import (
    DRAWN_CLOCK_SECONDS,
    FLICKER_DEPTH,
    FLICKER_STEP,
    GLOWS,
    LIVING_PART,
    TV_SHOT_JITTER,
    TV_SHOT_SECONDS,
    boxes_overlap,
    clock_seconds,
    glow_box,
    glow_rings,
    hand_angles,
    hand_tip,
    on_between,
    parse_clock_time,
    redrawn_members,
    shows_second_hand,
    switch_between,
    switched_on,
    tv_flicker,
    tv_picture,
    tv_shot,
)
from vidgen.cartoon.living_drawing import HAND_LENGTHS, LivingProp, living_parts
from vidgen.cartoon.props import draw_prop
from vidgen.cartoon.shading import LIT, mark_lit
from vidgen.cli import check_project
from vidgen.project import Project
from vidgen.theme import Theme


# ----- clocks (no render) ---------------------------------------------------------------------------


def test_hand_angles_over_time() -> None:
    drawn = hand_angles(DRAWN_CLOCK_SECONDS)   # 10:10
    assert drawn.hour == pytest.approx(305.0) and drawn.minute == pytest.approx(60.0) and drawn.second == 0.0
    assert hand_angles(0.0) == hand_angles(43200.0)   # twice round a day
    quarter = hand_angles(parse_clock_time("3:15:30"))
    assert quarter.hour == pytest.approx(97.75) and quarter.minute == pytest.approx(93.0) and quarter.second == pytest.approx(180.0)
    assert clock_seconds(DRAWN_CLOCK_SECONDS, 1.0, 30.0) == DRAWN_CLOCK_SECONDS + 30.0   # real time
    sped = hand_angles(clock_seconds(DRAWN_CLOCK_SECONDS, 60.0, 30.0))   # a minute a second: half an hour later
    assert sped.minute == pytest.approx(240.0) and sped.hour == pytest.approx(320.0)
    assert hand_tip(0.0, 0.0, 1.0, 0.0) == pytest.approx((0.0, 1.0)) and hand_tip(0.0, 0.0, 1.0, 90.0) == pytest.approx((1.0, 0.0))   # clockwise
    assert shows_second_hand(1.0) and shows_second_hand(10.0) and not shows_second_hand(60.0)


@pytest.mark.parametrize("text", ["10", "24:00", "9:60", "9:5", "a:bc", "10:10:61", "1:2:3:4", "-1:30"])
def test_bad_clock_times(text: str) -> None:
    with pytest.raises(ValueError, match="is not a clock time"):
        parse_clock_time(text)


def test_clock_times() -> None:
    assert parse_clock_time("0:00") == 0.0 and parse_clock_time("23:59:59") == 86399.0 and parse_clock_time(" 07:05 ") == 7 * 3600 + 300


# ----- switching, the picture, glows (no render) ----------------------------------------------------


def test_on_and_off_over_time() -> None:
    switches = [(2.0, True), (5.0, False), (5.0, True)]   # two at once: the later one wins
    assert [switched_on(False, switches, t) for t in (0.0, 1.99, 2.0, 4.0, 5.0, 9.0)] == [False, False, True, True, True, True]
    assert switched_on(True, [], 3.0) and not switched_on(True, [(1.0, False)], 3.0)
    assert switch_between(switches, 1.0, 2.0) and not switch_between(switches, 2.1, 4.9)
    assert on_between(False, [(2.0, True)], 1.0, 3.0) and not on_between(False, [(2.0, True)], 0.0, 1.9)
    assert on_between(True, [(1.0, False)], 0.0, 0.5) and not on_between(True, [(1.0, False)], 1.5, 3.0)


def test_tv_picture_is_seeded_and_flickers() -> None:
    times = [k * 0.05 for k in range(400)]
    pictures = [tv_picture(t, 7) for t in times]
    assert pictures == [tv_picture(t, 7) for t in times]   # the same in every render
    assert all(1.0 - FLICKER_DEPTH <= p.brightness <= 1.0 for p in pictures)
    assert len({tv_flicker(k * FLICKER_STEP, 7) for k in range(48)}) > 20   # flickers every step
    assert tv_flicker(0.01, 7) == tv_flicker(FLICKER_STEP - 0.01, 7)   # steady within a step
    shots = [p.shot for p in pictures]
    assert shots == sorted(shots) and shots[0] == 0 and shots[-1] >= 20 / (TV_SHOT_SECONDS + TV_SHOT_JITTER)
    for shot in set(shots) - {0}:   # each picture lasts about TV_SHOT_SECONDS
        first = times[shots.index(shot)]
        assert abs(first - shot * TV_SHOT_SECONDS) <= TV_SHOT_JITTER / 2 + 0.05
    assert len({p.colors for p in pictures}) > 1
    assert [tv_shot(t, 7) for t in times] == shots
    assert [p.colors for p in pictures] != [tv_picture(t, 8).colors for t in times]   # another tv differs


def test_glow_rings_and_box() -> None:
    rings = glow_rings(2.0, 0.55)
    assert [r for r, _ in rings] == sorted((r for r, _ in rings), reverse=True) and rings[0][0] == 2.0
    clear = math.prod(1.0 - a for _, a in rings)
    assert 1.0 - clear == pytest.approx(0.55)   # stacked: the glow's opacity at the middle
    assert glow_box(1.0, 2.0, 0.5) == (0.5, 1.5, 1.5, 2.5)
    assert boxes_overlap((0, 0, 1, 1), (1.05, 0, 2, 1), margin=0.1) and not boxes_overlap((0, 0, 1, 1), (1.05, 0, 2, 1))


def test_what_is_redrawn_over_a_moving_part() -> None:
    region = (0.0, 0.0, 1.0, 1.0)
    boxes = [
        (2.0, 2.0, 3.0, 3.0),   # apart: stays in the static image
        (0.5, 0.5, 1.5, 1.5),   # over the region
        None,                   # draws nothing
        (1.4, 1.4, 2.5, 2.5),   # over the one before only: still redrawn
        (5.0, 5.0, 6.0, 6.0),
    ]
    assert redrawn_members(boxes, [region]) == [1, 3]
    assert redrawn_members(boxes, []) == []


# ----- drawing and living props (no render) ---------------------------------------------------------


def test_living_props_draw_their_moving_parts_inside_their_box() -> None:
    theme = Theme()
    for kind in ("clock", "tv", "lamp"):
        plain, living = draw_prop(kind, height=2.0, theme=theme), draw_prop(kind, height=2.0, theme=theme, living=True)
        assert plain.get_bottom() == pytest.approx(living.get_bottom()) and plain.width == pytest.approx(living.width), kind
        assert plain.height == pytest.approx(living.height) and living.feet() == pytest.approx(plain.feet()), kind
        assert plain._anchor is None and living._anchor is not None
    assert len(draw_prop("sofa", height=1.0, theme=theme, living=True).submobjects) == len(draw_prop("sofa", height=1.0, theme=theme).submobjects)
    clock = draw_prop("clock", height=1.0, theme=theme, living=True)
    assert [len(living_parts(clock, part)) for part in ("hour", "minute", "second")] == [1, 1, 1]
    assert {getattr(m, LIVING_PART, None) for m in draw_prop("clock", height=1.0, theme=theme).get_family()} == {None, "hour", "minute"}


@pytest.mark.parametrize("facing", ["right", "left"])
def test_a_running_clock_turns_its_hands_clockwise(facing: str) -> None:
    clock = draw_prop("clock", height=2.0, theme=Theme(), facing=facing, living=True).shift([3.0, 1.0, 0.0])
    live = LivingProp(clock, start=parse_clock_time("3:00"), speed=60.0)
    centre = clock.prop_point(0.0, 0.5)

    def direction(part: str) -> np.ndarray:
        hand = living_parts(clock, part)[0]
        tip = hand.points[-1] - centre
        return tip[:2] / np.linalg.norm(tip[:2])

    assert direction("minute") == pytest.approx([0.0, 1.0], abs=1e-6) and direction("hour") == pytest.approx([1.0, 0.0], abs=1e-6)
    tip = living_parts(clock, "minute")[0].points[-1] - centre
    assert float(np.linalg.norm(tip[:2])) == pytest.approx(HAND_LENGTHS["minute"] * clock.unit)
    live.update(15.0)   # 15 clock minutes later: the minute hand at three o'clock, on screen
    assert direction("minute") == pytest.approx([1.0, 0.0], abs=1e-6)
    assert live.changing(0.0, 1.0) and live.glow is None
    assert living_parts(clock, "second")[0].get_stroke_opacity() == 0.0   # too fast for a second hand
    assert living_parts(draw_prop("clock", height=1.0, theme=Theme(), living=True), "second")[0].get_stroke_opacity() > 0


def test_a_tv_and_a_lamp_switch_on_and_off() -> None:
    theme = Theme()
    tv = draw_prop("tv", height=2.0, theme=theme, living=True)
    mark_lit(tv)
    live = LivingProp(tv, seed=3)
    picture = living_parts(tv, "picture")
    assert len(picture) == 4 and all(m.get_fill_opacity() == 0.0 and m.get_stroke_opacity() == 0.0 for m in picture)   # off: as drawn
    assert not getattr(picture[0], LIT) and getattr(tv.submobjects[0], LIT)   # the screen is not graded by the light
    assert live.glow is not None and live.glow.submobjects[0].get_fill_opacity() == 0.0
    assert not live.changing(0.0, 5.0)
    live.switch(True, 2.0)
    assert live.changing(1.0, 2.0) and live.changing(3.0, 4.0)   # the switch, then the flicker
    live.update(2.5)
    assert all(m.get_fill_opacity() == 1.0 for m in picture) and picture[0].get_stroke_opacity() > 0
    assert picture[0].get_fill_color().to_hex().upper() != tv_picture(2.5, 3).colors[0] or tv_picture(2.5, 3).brightness == 1.0
    assert live.glow.submobjects[0].get_fill_opacity() > 0
    live.switch(False, 4.0)
    live.update(4.5)
    assert all(m.get_fill_opacity() == 0.0 for m in picture) and not live.changing(4.5, 9.0)

    lamp = draw_prop("lamp", height=3.0, theme=theme, living=True).shift([2.0, -1.0, 0.0])
    glowing = LivingProp(lamp, on=True)
    spec = GLOWS["lamp"]
    middle = lamp.prop_point(spec.x, spec.y)
    assert glowing.glow is not None and glowing.glow.get_center() == pytest.approx(middle)
    assert glowing.glow.width == pytest.approx(2 * spec.radius * lamp.unit, rel=1e-3)
    assert not glowing.changing(0.0, 10.0)   # a lamp that stays on changes nothing: it stays in the static image
    box = glowing.region()
    assert box[0] <= middle[0] - spec.radius * lamp.unit and box[1] <= float(lamp.get_bottom()[1])
    assert LivingProp(lamp, on=True, movable=True).changing(0.0, 1.0)   # carried: its glow follows


# ----- params and actions (no render) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("prop", "message"),
    [
        ({"prop": "sofa", "on": True}, "on is for props that switch on (fireplace, kettle, lamp, phone, tv, portal, hologram_display, scanner, crystal), not sofa"),
        ({"prop": "lamp", "time": "10:00"}, "time and speed are for a clock, not lamp"),
        ({"prop": "clock", "time": "25:00"}, "is not a clock time"),
        ({"prop": "clock", "speed": 0}, "greater than 0"),
        ({"prop": "clock", "speed": 7200}, "less than or equal to 3600"),
    ],
)
def test_bad_living_props(prop: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=re.escape(message)):
        stage_params(props=[prop])


def test_living_prop_params() -> None:
    params = stage_params(props=[{"prop": "clock", "time": "21:30"}, {"prop": "clock", "speed": 60}, "clock", {"prop": "tv", "on": True}])
    clocks = params.props[:3]
    assert [c.runs() for c in clocks] == [True, True, False]
    assert clocks[0].clock_start() == 21.5 * 3600 and clocks[1].clock_start() == DRAWN_CLOCK_SECONDS


def room_project(make_project, params: dict[str, Any], beats: list[dict[str, Any]], **config: Any) -> Project:
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes, **config)))


def test_switch_actions_validate(make_project) -> None:
    params = {"room": True, "props": [{"prop": "tv", "against": "wall"}, "lamp", {"prop": "sofa", "at": 0.2}], "characters": ["pip"]}
    good = [{"text": "Pip turns the lamp on, then the television.", "actions": [{"switch_on": "lamp"}, {"switch_on": "tv", "at": 0.5}]},
            {"text": "And off again.", "actions": [{"switch_off": ["lamp", "tv"], "at": 0.5}]}]
    assert check_project(room_project(make_project, params, good)) == []
    bad = [{"text": "Hm.", "actions": [{"switch_on": "sofa"}, {"switch_off": "pip"}, {"switch_on": "radio"}]}]
    problems = check_project(room_project(make_project, params, bad))
    assert any("'sofa' cannot be switched on or off (props that can: fireplace, kettle, lamp" in p for p in problems), problems
    assert any("'pip' is not a prop; switch_off acts on props" in p for p in problems), problems
    assert any("radio" in p for p in problems), problems


# ----- renders ---------------------------------------------------------------------------------------


def frames_of(project: Project, media: Path, monkeypatch) -> tuple[Any, list[np.ndarray]]:
    """Render ``home`` at 160x90: the scene and every frame written."""
    from manim.scene.scene_file_writer import SceneFileWriter

    frames: list[np.ndarray] = []
    write = SceneFileWriter.write_frame

    def recording(self: Any, frame: Any, num_frames: int = 1) -> None:
        frames.extend([np.asarray(frame)[:, :, :3].copy()] * num_frames)
        write(self, frame, num_frames)

    monkeypatch.setattr(SceneFileWriter, "write_frame", recording)
    scene, _ = render_with_layout(project, "home", media)
    monkeypatch.setattr(SceneFileWriter, "write_frame", write)
    return scene, frames


ROOM: dict[str, Any] = {
    "light": "night",
    "room": {"wallpaper": "stripes", "windows": [0.2]},
    "props": [
        {"prop": "clock", "at": 0.5}, {"prop": "tv", "at": 0.75, "against": "wall"}, {"prop": "lamp", "at": 0.15, "depth": 0.3, "scale": 0.6},
        {"prop": "armchair", "at": 0.7, "depth": 0.15},
    ],
    "characters": [{"name": "pip", "at": 0.35, "depth": 0.1}],
}
BEATS = [{"text": "Pip waits in the room for a little while."}, {"text": "Then the lamp and the television come on."}]


@pytest.mark.render
def test_props_switched_on_later_are_drawn_as_before_until_then(make_project, tmp_path: Path, monkeypatch) -> None:
    """The lamp and the tv are drawn living (their picture, lantern and glow hidden) and redrawn
    over the static image from the animation the switch falls in: every frame before the switch
    is the same as without the switch, pixel for pixel; then the picture and the glow show."""
    from vidgen import extensions, registry

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)   # no fade out: the stage stays to look at
    plain, before = frames_of(room_project(make_project, ROOM, BEATS), tmp_path / "plain", monkeypatch)
    assert plain.living == {}
    switched = [BEATS[0], {**BEATS[1], "actions": [{"switch_on": "lamp", "at": 0.5}, {"switch_on": "tv", "at": 0.5}]}]
    scene, after = frames_of(room_project(make_project, ROOM, switched), tmp_path / "on", monkeypatch)
    assert set(scene.living) == {"lamp", "tv"} and len(after) == len(before)
    switch = round(scene.living["tv"].switches[0][0] * 5)   # 5 fps
    assert 5 < switch < len(after) - 3
    assert all(np.array_equal(a, b) for a, b in zip(after[:switch], before[:switch]))
    assert not np.array_equal(after[switch + 1], before[switch + 1])
    assert scene.living["tv"].glow in scene.mobjects and scene.mobjects.index(scene.living["tv"].glow) == scene.mobjects.index(scene.props["tv"]) - 1
    assert [s for s in scene.sfx_log if s.sound == "click"]   # foley


@pytest.mark.render
def test_a_running_clock_changes_nothing_outside_its_box(make_project, tmp_path: Path, monkeypatch) -> None:
    """Only the clock's hands leave the static image (with what is drawn over them): every frame
    differs from the same scene with a still clock inside the clock's box only, and the lamp that
    stays on is in the static image (nothing of it is redrawn)."""
    from vidgen import extensions, registry

    extensions.load_builtins()
    room = {**ROOM, "props": [*ROOM["props"][:1], *({**p, "on": True} if p["prop"] == "lamp" else p for p in ROOM["props"][1:])]}
    still, before = frames_of(room_project(make_project, room, BEATS[:1]), tmp_path / "still", monkeypatch)
    stage = registry.get("stage").cls
    seen: list[list[Any]] = []
    moving = stage.get_moving_mobjects
    monkeypatch.setattr(stage, "get_moving_mobjects", lambda self, *a: (seen.append(r := moving(self, *a)), r)[1])
    running = {**room, "props": [{"prop": "clock", "at": 0.5, "time": "8:00", "speed": 600}, *room["props"][1:]]}
    scene, after = frames_of(room_project(make_project, running, BEATS[:1]), tmp_path / "running", monkeypatch)
    assert len(after) == len(before) > 10
    clock = scene.props["clock"]
    left, bottom = clock.get_corner(np.array([-1.0, -1.0, 0.0]))[:2]
    right, top = clock.get_corner(np.array([1.0, 1.0, 0.0]))[:2]
    to_pixel = 160 / scene.frame_width
    x0, x1 = math.floor((left + scene.frame_width / 2) * to_pixel) - 1, math.ceil((right + scene.frame_width / 2) * to_pixel) + 1
    y0, y1 = math.floor((scene.frame_height / 2 - top) * to_pixel) - 1, math.ceil((scene.frame_height / 2 - bottom) * to_pixel) + 1
    changed = 0
    for a, b in zip(after, before):
        diff = np.abs(a.astype(int) - b.astype(int)).sum(axis=2) > 0
        changed += int(diff.any())
        diff[max(y0, 0):y1, max(x0, 0):x1] = False
        assert not diff.any()
    assert changed > len(after) // 2   # the hands turn
    lamp = scene.living["lamp"]
    hands = {id(m) for part in ("hour", "minute") for m in living_parts(clock, part)}
    redrawn = [ids for ids in ({id(m) for m in r} for r in seen) if hands & ids]
    assert any(id(lamp.glow.submobjects[0]) not in ids and id(lamp.prop.submobjects[0]) not in ids for ids in redrawn)   # the beat's wait: the lamp stays in the static image
