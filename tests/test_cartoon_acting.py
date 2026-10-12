"""Step 78: acting actions, part 1 (``say``, ``look_at``, ``turn``, ``emote``, ``pose``, ``react``),
who speaks a beat, lip sync timed from the beat's start, speech bubbles and their checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_stage import render_with_layout
from vidgen import actions, extensions, registry
from vidgen.cartoon.acting import CAMERA_EYES_BACK, LOOK_MAX_DEGREES, camera_look, look_pose
from vidgen.cartoon.cast import ACTION_NEEDS, beat_voice, missing_needs, say_problem, shared_voice_warnings, speaking_characters
from vidgen.cartoon.character import Character, CharacterState, build_character
from vidgen.cartoon.transition import Gesture, Jump, KeyedMotion, PoseChange, Walk
from vidgen.cartoon.visemes import VisemeCue, VisemeTrack
from vidgen.cli import check_project, validate_warnings
from vidgen.config import BeatConfig, CharacterEntry, SceneConfig, parse_config
from vidgen.project import Project
from vidgen.theme import Theme

VOICES = {"pip_voice": {"voice_id": "p1"}, "kit_voice": {"voice_id": "k1"}}
CAST = [
    {"name": "pip", "voice": "pip_voice", "look": {"body": "bean"}},
    {"name": "kit", "voice": "kit_voice", "look": {"body": "tall"}, "expressions": {"smug": {"mouth": {"shape": "smile"}}}},
    {"name": "rex"},   # no voice
]
FPS = 30
FRAME = 1.0 / FPS


def acting_project(make_project, beats: list[dict[str, Any]], characters: list[Any] | None = None, **config: Any) -> Project:
    params = {"idle": False, "characters": characters or [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}], "props": ["tree"]}
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes, **config)))


def figure(name: str = "pip") -> Character:
    entry = next(CharacterEntry(**c) for c in CAST if c["name"] == name)
    return build_character(entry, theme=Theme()).stop_idle()


# ----- where a character looks (no manim) --------------------------------------------------------


def test_look_pose_turns_and_tilts_towards_the_point() -> None:
    ahead = look_pose(3.0, 0.0, "left")
    assert ahead.facing == "right" and ahead.head_angle == 0.0 and ahead.eyes_shift[0] > 0
    up = look_pose(-1.0, 1.0, "right")
    assert up.facing == "left" and up.head_angle == LOOK_MAX_DEGREES and up.eyes_shift[1] > 0   # 45° capped at 20°
    assert look_pose(-4.0, -0.5, "right").head_angle == pytest.approx(-7.125, abs=1e-3)
    assert look_pose(0.01, 2.0, "left").facing == "left"   # straight above: keeps its facing
    camera = camera_look("left")
    assert camera.facing == "left" and camera.head_angle == 0 and camera.eyes_shift == (-CAMERA_EYES_BACK, 0.0)


# ----- who speaks (no manim) -----------------------------------------------------------------------


def test_the_beat_voice_picks_who_speaks() -> None:
    config = parse_config(minimal_config(characters=[*CAST, {"name": "ana", "voice": "default"}], voices=VOICES))
    scene = SceneConfig(id="s", type="stage", voice="pip_voice", beats=[{"text": "Hi."}, {"text": "Yo.", "voice": "kit_voice"}])
    assert [beat_voice(scene, b) for b in scene.beats] == ["pip_voice", "kit_voice"]
    assert beat_voice(SceneConfig(id="t", type="stage", beats=[{"text": "Hi."}]), BeatConfig(id="b", text="Hi.")) == "default"
    on_stage = ["kit", "pip", "rex", "ana"]
    assert speaking_characters(config, "pip_voice", on_stage) == ["pip"]
    assert speaking_characters(config, "default", on_stage) == ["ana"]   # rex has no voice: never speaks
    assert speaking_characters(config, "kit_voice", ["pip"]) == []        # kit is not on this stage
    assert say_problem(config, "pip") is None and say_problem(config, "nobody") is None
    assert say_problem(config, "rex") == "character 'rex' has no voice, so it cannot say anything (give it voice: in characters:)"
    twins = parse_config(minimal_config(characters=[*CAST, {"name": "kat", "voice": "kit_voice"}], voices=VOICES))
    assert shared_voice_warnings(config) == []
    assert shared_voice_warnings(twins) == [
        "characters 'kit', 'kat' have the same voice 'kit_voice': beats in that voice move all their mouths on a stage; "
        "add a say action to such beats to pick who speaks"
    ]


def test_action_needs() -> None:
    assert "say" in ACTION_NEEDS and missing_needs({"body": ["rest"]}, "say") == "mouth"
    assert missing_needs({"body": ["rest"], "head": ["rest"]}, "look_at") is None
    assert missing_needs({"body": ["rest"]}, "emote") == "eyes or brows or mouth"


# ----- lip sync in step with the audio --------------------------------------------------------------


def test_lip_sync_stays_in_step_through_a_pose_change() -> None:
    """The mouth follows the beat's clock (scene time), also while a PoseChange pauses the
    character's updaters: a frame-counting clock would fall behind by the change's length."""
    track = VisemeTrack(tuple(VisemeCue(k * 0.2, (k + 1) * 0.2, v) for k, v in enumerate("AOMEUFLWAO")) + (VisemeCue(2.0, 3.0, "rest"),))
    c = figure()
    now = [0.0]
    c.lip_sync(track, clock=lambda: now[0])

    def expected() -> str:
        return c.viseme_shape(track.at(now[0])) or "smile"

    for _ in range(9):   # 0.3 s of updates
        now[0] += FRAME
        c.update(FRAME)
        assert c.shown_shape("mouth") == expected()
    change = PoseChange(c, pose="pointing", expression="sad", run_time=1.0)
    change.begin()   # Manim suspends the updaters here
    for frame in range(1, FPS + 1):
        now[0] += FRAME
        change.interpolate(frame / FPS)
        assert c.shown_shape("mouth") == expected(), now[0]
    change.finish()
    c.resume_updating()
    for _ in range(30):
        now[0] += FRAME
        c.update(FRAME)
        assert c.shown_shape("mouth") == expected()
    assert c.pose_of("mouth").shape is None and c.pose_of("mouth").scale[1] < 0   # sad: the flipped rest mouth
    assert c.shown_shape("mouth") == "smile"   # rest after the track: the expression's mouth
    c.stop_lip_sync()
    assert c.lip_sync_track is None and not c.updaters


def test_lip_sync_layer_keeps_the_pose_and_an_emote_while_speaking() -> None:
    c = figure()
    now = [0.5]
    track = VisemeTrack((VisemeCue(0.0, 1.0, "O"), VisemeCue(1.0, 2.0, "rest")))
    c.lip_sync(track, clock=lambda: now[0])
    assert c.shown_shape("mouth") == "O" and c.pose_of("mouth").shape is None   # shown over the pose
    c.set_expression("surprised")   # an expression set while speaking
    assert c.shown_shape("mouth") == "O"
    now[0] = 1.5
    c.update(FRAME)
    assert c.shown_shape("mouth") == "open"   # rest: the new expression's mouth
    c.stop_lip_sync()
    assert c.shown_shape("mouth") == "open"


def _moves(c: Character) -> dict[str, Any]:
    """One of each animation that moves a character (walk_to / enter / exit, jump, gesture,
    keyframes and move_along, a pose change), made when asked (they read where it stands)."""
    x0 = float(c.feet()[0])
    return {
        "walk": lambda: Walk(c, x0 + 3.0),
        "enter": lambda: Walk(c, x0, start_x=x0 - 4.0),
        "jump": lambda: Jump(c),
        "gesture": lambda: Gesture(c, "wave"),
        "keyed": lambda: KeyedMotion(c, lambda t: {"x": x0 + 2.0 * t, "y": 0.5 * t, "rotate": 10.0 * t}, run_time=1.0),
        "pose": lambda: PoseChange(c, pose="pointing", run_time=1.0),
    }


@pytest.mark.parametrize("move", ["walk", "enter", "jump", "gesture", "keyed", "pose"])
def test_a_speaking_character_takes_its_whole_mouth_along(move: str) -> None:
    """Manim draws, every frame of an animation, the family members it listed when the
    animation began (the character's family, flattened). A mouth shape swapped by lip sync while
    the character moves must not leave the old shape in that list: no stray mouth stays behind
    where the speaking started, and the mouth stays inside the head (the Step 88 review video)."""
    from manim.utils.family import extract_mobject_family_members

    track = VisemeTrack(tuple(VisemeCue(k * 0.1, (k + 1) * 0.1, v) for k, v in enumerate("AOMEUOAOEA" * 3)))
    c = figure()
    c.start_idle()   # blinks swap the eyes' shape too
    now = [0.0]
    c.lip_sync(track, clock=lambda: now[0])
    animation = _moves(c)[move]()
    listed = c.get_family()   # what Scene.get_moving_mobjects lists when the animation begins
    animation.begin()
    shapes = set()
    for frame in range(1, FPS + 1):
        now[0] += FRAME
        animation.interpolate(frame / FPS)
        shapes.add(c.shown_shape("mouth"))
    assert len(shapes) > 2   # the mouth changed shape while it moved
    drawn = extract_mobject_family_members(listed, only_those_with_points=True)
    family = {id(m) for m in c.get_family()}
    assert [m for m in drawn if id(m) not in family] == []   # nothing left behind
    head = c.parts["head"]
    low, high = head.get_corner(np.array([-1, -1, 0])), head.get_corner(np.array([1, 1, 0]))
    mouth = c.parts["mouth"].family_members_with_points()
    assert mouth and all(m in drawn for m in mouth)
    for member in mouth:
        points = member.points[:, :2]
        assert (points >= low[:2] - 1e-6).all() and (points <= high[:2] + 1e-6).all(), move


# ----- the actions on a character (no render) ---------------------------------------------------------


def use(name: str, target: str | list[str] = "pip", **options: Any) -> actions.Action:
    extensions.load_builtins()
    cls = registry.find_action(name).cls
    config = actions.ActionConfig.model_validate({"action": name, "target": target, **options})
    return cls(cls.Options(**options), config)


def run(anims: list[Any]) -> None:
    for anim in anims:
        anim.begin()
        anim.interpolate(1.0)
        anim.finish()


def target(name: str, mob: Any) -> actions.Target:
    return actions.Target((name,), mob)


class FakeScene:
    """Enough of a stage for the acting actions: targets by name, bounds and marks."""

    spec = type("Spec", (), {"id": "park"})()
    mid_still_actions: frozenset[str] = frozenset()

    def __init__(self, **mobs: Any) -> None:
        self.mobs = mobs
        self.params = registry.get("stage").cls.validate_params({"marks": {"door": 0.9}})
        self.spoken: list[str] = []

    def find_targets(self, pattern: str) -> list[actions.Target]:
        return [target(pattern, self.mobs[pattern])] if pattern in self.mobs else []

    def camera_bounds(self) -> tuple[float, float, float, float]:
        return (-8.0, 8.0, -4.5, 4.5)

    def camera_place(self, params: Any, place: Any) -> float:
        return registry.get("stage").cls.camera_place(params, place)

    def speak(self, character: Character) -> None:
        self.spoken.append(character.name)
        character.lip_sync(VisemeTrack((VisemeCue(0.0, 1.0, "A"),)), clock=lambda: 0.5)

    current_beat = BeatConfig(id="b", text="Hello there.")


def test_emote_pose_react_and_their_undoing() -> None:
    c = figure()
    emote = use("emote", to="happy")
    run(emote.apply(FakeScene(), [target("pip", c)]))
    assert c.state() == figure().posed_state(expression="happy")
    pose = use("pose", to="pointing")
    run(pose.apply(FakeScene(), [target("pip", c)]))
    assert c.pose_of("arm_left").angle != 0 and c.state().parts["mouth"] == figure().posed_state(expression="happy").parts["mouth"]
    run(emote.revert(FakeScene(), [target("pip", c)]))   # until: the expression goes, the pose stays
    assert c.pose_of("mouth") == figure().pose_of("mouth") and c.pose_of("arm_left").angle != 0
    react = use("react", expression="surprised", pose="shrug")
    before = c.state()
    run(react.apply(FakeScene(), [target("pip", c)]))
    assert c.state() != before
    run(react.revert(FakeScene(), [target("pip", c)]))
    assert c.state() == before


def test_look_at_and_turn() -> None:
    from manim import Square

    pip, kit = figure("pip").shift([-4.0, -2.0, 0.0]), figure("kit").face("left").shift([4.0, -2.0, 0.0])
    lamp = Square(0.5).move_to([-7.0, 3.0, 0.0])
    scene = FakeScene(pip=pip, kit=kit, lamp=lamp)
    look = use("look_at", to="lamp")
    run(look.apply(scene, [target("pip", pip)]))
    assert pip.facing == "left" and pip.pose_of("head").angle == LOOK_MAX_DEGREES   # up and behind it
    run(use("look_at", to="kit").apply(scene, [target("pip", pip)]))
    assert pip.facing == "right" and abs(pip.pose_of("head").angle) < 1 and pip.pose_of("eyes").shift[0] > 0
    run(look.revert(scene, [target("pip", pip)]))   # until: back to how it looked before the first one
    assert pip.facing == "right" and pip.pose_of("head").angle == 0 and pip.pose_of("eyes").shift == (0.0, 0.0)
    run(use("look_at", to="door").apply(scene, [target("pip", pip)]))   # a mark right of pip
    assert pip.facing == "right" and pip.pose_of("head").angle == 0
    run(use("look_at", to="camera").apply(scene, [target("kit", kit)]))
    assert kit.facing == "left" and kit.pose_of("eyes").shift == (-CAMERA_EYES_BACK, 0.0)
    assert use("look_at", to="pip").apply(scene, [target("pip", pip)]) == []   # itself: nothing
    turn = use("turn")
    run(turn.apply(scene, [target("pip", pip)]))
    assert pip.facing == "left"
    assert use("turn", to="left").apply(scene, [target("pip", pip)]) == []   # already
    run(turn.revert(scene, [target("pip", pip)]))
    assert pip.facing == "right"
    assert use("emote", to="sad").apply(scene, [target("lamp", lamp)]) == []   # not a character: skipped


def test_say_starts_and_stops_lip_sync() -> None:
    c = figure()
    scene = FakeScene(pip=c)
    say = use("say")
    assert say.apply(scene, [target("pip", c)]) == [] and scene.spoken == ["pip"]
    assert c.lip_sync_track is not None and c.shown_shape("mouth") == "A"
    run(say.revert(scene, [target("pip", c)]))
    assert c.lip_sync_track is None and c.shown_shape("mouth") == "smile"
    say.apply(scene, [target("pip", c)])
    c.lip_sync(VisemeTrack((VisemeCue(0.0, 1.0, "O"),)))   # a later lip sync (the next beat's) takes over
    say.revert(scene, [target("pip", c)])
    assert c.lip_sync_track is not None   # not stopped by the earlier say


def test_speech_bubble_sits_above_the_head_with_a_tail_towards_it() -> None:
    from manim import tempconfig

    from vidgen.api import Region
    from vidgen.scenes.acting import bubble_tail, speech_bubble

    with tempconfig({"pixel_width": 320, "pixel_height": 180}):
        head = Region(-1.0, 0.0, 0.0, 1.0)
        bubble = speech_bubble("Hello there, friend.", head, color="#FFFFFF", size="caption", bounds=Region(-7, -4, 7, 4),
                               avoid=[], scale=1.0, theme=Theme())
        plate = bubble.extent(pad=0)
        assert plate.y0 > head.y1 and plate.x0 < -0.5 < plate.x1
        shape, text = bubble.mark.submobjects
        assert shape.get_bottom()[1] < plate.y0 + 0.2 and shape.get_bottom()[1] > head.y1   # the tail reaches down, not into the head
        assert text.get_center()[1] > head.y1 and len(shape.get_subpaths()) == 1
    corners = bubble_tail(np.array([0.0, 2.0, 0.0]), (2.0, 1.0), np.array([0.0, 0.0, 0.0]))
    assert [c[1] for c in corners[:2]] == pytest.approx([1.5 + 0.6 * 0.14] * 2) and corners[0][0] - corners[1][0] == pytest.approx(0.28)
    assert corners[2][:2] == pytest.approx((0.0, 1.1))   # TAIL_LENGTH (0.4) below the bottom edge
    from manim import Polygon, RoundedRectangle, Union

    plate = RoundedRectangle(width=2.0, height=1.0, corner_radius=0.14).move_to([0.0, 2.0, 0.0])
    assert len(Union(plate, Polygon(*corners)).get_subpaths()) == 1   # one outline: plate and tail joined


# ----- validate ------------------------------------------------------------------------------------


def test_validate_acting_actions(make_project) -> None:
    project = acting_project(make_project, [
        {"text": "Hello, I am Pip.", "voice": "pip_voice", "actions": [
            {"say": "pip", "bubble": True}, {"react": "kit", "expression": "surprised"}, {"look_at": "kit", "to": "pip"}]},
        {"text": "Hi.", "voice": "kit_voice", "actions": [
            {"say": "kit", "bubble": "Hi!"}, {"emote": "kit", "to": "smug"}, {"pose": "pip", "to": "waving", "until": "park_b3"},
            {"turn": "pip", "to": "left"}, {"look_at": "pip", "to": "camera"}, {"look_at": "kit", "to": "tree"}, {"look_at": "pip", "to": 0.2}]},
        {"text": "Bye.", "actions": [{"action": "react", "target": ["pip", "kit"], "pose": "shrug"}]},
    ])
    assert check_project(project) == []
    where = "scenes[0].beats[0].actions"
    bad = acting_project(make_project, [{"text": "Hello.", "actions": [
        {"say": "rex"}, {"say": "bob"}, {"emote": "pip", "to": "hapy"}, {"pose": "kit", "to": "bow"}, {"react": "pip"},
        {"look_at": "pip", "to": "nowhere"}, {"emote": "tree", "to": "happy"}, {"say": "pip", "bubble": " "}, {"turn": "pip", "to": "up"},
    ]}], characters=[{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}, {"name": "rex", "at": "centre"}])
    problems = check_project(bad)
    expected = [
        f"{where}[0].target: character 'rex' has no voice, so it cannot say anything (give it voice: in characters:)",
        f"{where}[1].target: unknown target 'bob' for scene type 'stage'",
        f"{where}[2].to: character 'pip': unknown expression 'hapy'; did you mean 'happy'?",
        f"{where}[3].to: character 'kit': unknown pose 'bow'",
        f"{where}[4].expression: react needs an expression or a pose (or both)",
        f"{where}[5].to: not a character or prop of the scene, nor camera; unknown mark 'nowhere'",
        f"{where}[6].target: 'tree' is not a character; emote acts on characters",
        f"{where}[7].bubble: the bubble's text is empty",
        f"{where}[8].to",
    ]
    for start in expected:
        assert any(p.startswith(start) for p in problems), (start, problems)
    assert len(problems) == len(expected), problems


def test_validate_warns_about_missing_parts(make_project) -> None:
    root = make_project(minimal_config(
        characters=[{"name": "blob", "voice": "default", "look": {"svg": "assets/blob.svg"}}, {"name": "pip", "voice": "default"}],
        scenes=[{"id": "park", "type": "stage", "params": {"characters": ["blob", "pip"]}, "beats": [
            {"text": "Hello.", "actions": [{"say": "blob"}, {"look_at": "*", "to": "camera"}, {"react": "blob", "pose": "shrug"}]}]}],
    ))
    (root / "assets").mkdir()
    (root / "assets" / "blob.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect id="body" width="10" height="10" fill="#3a6"/></svg>', encoding="utf-8"
    )
    project = Project.load(root)
    assert check_project(project) == []
    warnings = [w for w in validate_warnings(project) if w.startswith("scenes[")]
    assert warnings == [
        "scenes[0].beats[0].actions[0]: character 'blob' cannot say (needs mouth); the action does nothing for it",
        "scenes[0].beats[0].actions[1]: character 'blob' cannot look_at (needs head); the action does nothing for it",
    ]
    assert any("have the same voice 'default'" in w for w in validate_warnings(project))


# ----- schedules (no render) --------------------------------------------------------------------------


def test_action_schedule_in_the_beats(make_project) -> None:
    """``say`` and ``react`` last their beat, ``emote`` stays, ``pose`` until a beat."""
    project = acting_project(make_project, [
        {"text": "One two three four.", "actions": [{"say": "pip"}, {"react": "kit", "expression": "happy", "at": 0.5}, {"emote": "pip", "to": "sad"}]},
        {"text": "Five six.", "actions": [{"pose": "kit", "to": "shrug", "until": "park_b3"}]},
        {"text": "Seven.", "voice": "kit_voice"},
    ])
    spec = project.scene("park")
    with extensions.project_session(project) as theme:
        cls = registry.get("stage").cls
        uses, problems = actions.scene_actions("stage", cls, spec, cls.validate_params(spec.params, theme), theme)
    assert problems == []

    class Clock:
        time = 0.0

    scene = type("Scene", (), {"renderer": Clock(), "beats": spec.beats, "spec": spec})()
    with __import__("manim").tempconfig({"frame_rate": 10}):
        runner = actions.ActionRunner(scene, uses)
        assert [(u.config.action, u.until) for u in uses] == [("say", "park_b2"), ("react", "park_b2"), ("emote", None), ("pose", "park_b3")]
        runner.start_beat("park_b1", 1.0, 0.2)
        assert [(d.frame, d.use.config.action, d.revert) for d in runner._pending] == [(0, "say", False), (0, "emote", False), (5, "react", False)]
        for u in uses[:3]:
            u.applied = True
        Clock.time = 1.2
        runner.start_beat("park_b2", 0.5, 0.2)
        assert [(d.frame, d.use.config.action, d.revert) for d in runner._pending] == [(12, "say", True), (12, "react", True), (12, "pose", False)]


# ----- render ------------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_dialogue_on_a_stage(make_project, tmp_path: Path) -> None:
    project = acting_project(make_project, [
        {"text": "Hello, I am Pip.", "voice": "pip_voice", "actions": [{"react": "kit", "expression": "surprised"}]},
        {"text": "Hi.", "voice": "kit_voice", "actions": [{"say": "kit", "bubble": "Hi!"}, {"emote": "kit", "to": "happy"}, {"look_at": "pip", "to": "kit"}]},
    ])
    scene, _ = render_with_layout(project, "park", tmp_path / "media")
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    assert pip.lip_sync_track is None   # pip spoke beat one (its voice), stopped at that beat's end
    assert kit.lip_sync_track is not None and kit.shown_shape("mouth") == (kit.pose_of("mouth").shape or "smile")   # last beat: at rest
    played = {(record.beat, name) for record in scene.play_log for name in record.animations}
    assert {("park_b1", "PoseChange"), ("park_b2", "PoseChange"), ("park_b2", "FadeIn")} <= played   # react; emote, look_at; the bubble
    assert kit.state().parts["mouth"] == kit.posed_state(expression="happy").parts["mouth"]
    assert pip.facing == "right" and kit.state().parts["eyes"] == kit.posed_state(expression="happy").parts["eyes"]
