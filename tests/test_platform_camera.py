"""Step 154: the camera on a platform level and ``character_size`` — the size named at the video and
the scene, the level raised in a portrait frame and the camera's room over a tall one (no manim),
the gentle following camera (dead zone, easing, up and down), reframing with a hero, the
``small_speaker`` lint rule and ``off_frame`` leaving the tiles alone, and tiny renders of a hero
followed across and up a level (and walking times that do not depend on the size)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_lint import check, fig, thing
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen import extensions, registry
from vidgen.camera import FOLLOW_DEAD_ZONE, FOLLOW_MAX_OFFSET, SmoothFollow, smooth_damp
from vidgen.cartoon.level_drawing import draw_columns, drawn_rows, level_shapes
from vidgen.cartoon.level_stage import LEVEL_HEAD_ROOM, LEVEL_SIZE, level_frame, level_raise
from vidgen.cartoon.reframe import ReframeBeat, ReframeFigure, reframe_path
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.worker import frame_size
from vidgen.world import parse_level

FW, FH = frame_size(1920, 1080)
PW, PH = frame_size(1080, 1920)
FLAT = "a" + "." * 29 + "\n" + "#" * 30

#: a hero's way up: the ground, a plank four tiles up (b), one seven up (c) whose top the frame
#: (8 rows at medium) does not show with a character on it
TALL_MAP = """
..................c...........
.................========.....
..............................
............b.................
..........======..............
..............................
.a............................
##############################
"""


# ----- character_size (no manim) -----------------------------------------------------------------


def test_character_size_sets_the_default_size() -> None:
    assert stage_params().size == pytest.approx(0.45) and stage_params(character_size="medium").size == pytest.approx(0.45)
    assert stage_params(character_size="small").size == pytest.approx(0.315)
    assert stage_params(character_size="large").size == pytest.approx(0.63)
    level = {"map": FLAT}
    assert stage_params(level=level).size == pytest.approx(LEVEL_SIZE)   # medium: as before
    assert stage_params(level=level, character_size="small").size == pytest.approx(0.175)
    assert stage_params(level=level, character_size="large").size == pytest.approx(0.35)
    assert stage_params(level=level, size=0.3).size == pytest.approx(0.3)   # a size written wins
    with pytest.raises(Exception, match="give character_size .* or size .*, not both"):
        stage_params(size=0.3, character_size="large")
    with pytest.raises(Exception, match="character_size"):
        stage_params(character_size="huge")


def _scene_size(project: Project, scene_id: str) -> float:
    spec = project.scene(scene_id)
    return registry.get("stage").cls.validate_params(spec.params).size


def test_the_video_character_size_reaches_stage_scenes_and_the_scene_wins(make_project) -> None:
    extensions.load_builtins()
    scenes = [
        {"id": "plain", "type": "stage", "params": {"characters": ["pip"]}, "beats": [{"text": "Hi."}]},
        {"id": "own", "type": "stage", "params": {"character_size": "small", "level": {"map": FLAT}}, "beats": [{"text": "Hi."}]},
        {"id": "sized", "type": "stage", "params": {"size": 0.5}, "beats": [{"text": "Hi."}]},
        {"id": "hills", "type": "stage", "params": {"level": {"map": FLAT}}, "beats": [{"text": "Hi."}]},
        {"id": "card", "type": "title_card", "params": {"title": "Hi"}, "beats": [{"text": "Hi."}]},
    ]
    config = minimal_config(characters=CAST, scenes=scenes, character_size="large",
                            variants={"cinema": {"character_size": "small"}})
    project = Project.load(make_project(config))
    assert project.config.character_size == "large"
    assert _scene_size(project, "plain") == pytest.approx(0.63)
    assert _scene_size(project, "own") == pytest.approx(0.175)   # the scene's own wins
    assert _scene_size(project, "sized") == pytest.approx(0.5)   # so does a size it writes
    assert _scene_size(project, "hills") == pytest.approx(0.35)
    assert "character_size" not in project.scene("card").params
    cinema = Project.load(project.root, variant="cinema")
    assert _scene_size(cinema, "hills") == pytest.approx(0.175)
    plain = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes[:1]), folder="plain"))
    assert _scene_size(plain, "plain") == pytest.approx(0.45)   # no video setting: medium


def test_a_bad_video_character_size_is_reported_there(make_project) -> None:
    scenes = [{"id": "plain", "type": "stage", "params": {}, "beats": [{"text": "Hi."}]}]
    with pytest.raises(VidgenError, match="character_size"):
        Project.load(make_project(minimal_config(scenes=scenes, character_size="huge")))


def test_moves_take_as_long_whatever_the_size() -> None:
    """Default walking speeds scale with the size (``level_pace``) as the tiles do, and the rules
    plan in tiles, so a walk or a jump takes as long at every character_size (the render below
    checks the sounds with them)."""
    from vidgen.scenes.stage import STAGE_SIZE

    seconds_per_tile = []
    for name in ("small", "medium", "large"):
        p = stage_params(level={"map": FLAT}, character_size=name)
        seconds_per_tile.append(p.level_frame(FW, FH).tile / (p.size / STAGE_SIZE))
    assert seconds_per_tile == pytest.approx([seconds_per_tile[1]] * 3)


# ----- the level in the frame (no manim) -----------------------------------------------------------


def test_a_landscape_level_sits_on_the_frame_bottom_and_rises_room_for_a_tall_one() -> None:
    flat = parse_level(FLAT)
    frame = level_frame(flat, LEVEL_SIZE, FW, FH)
    assert frame.bottom == pytest.approx(-FH / 2) and frame.below == 0 and frame.top == pytest.approx(FH / 2)   # as before
    tall = parse_level(TALL_MAP)
    frame = level_frame(tall, LEVEL_SIZE, FW, FH)
    assert frame.tile == pytest.approx(1.0)
    assert frame.top == pytest.approx(-FH / 2 + (7 + 2 + LEVEL_HEAD_ROOM))   # a character on the top plank and a jump's room


def test_a_short_level_is_raised_in_a_portrait_frame() -> None:
    flat = parse_level(FLAT)
    frame = level_frame(flat, LEVEL_SIZE, PW, PH)   # 14.2 rows: one row of tiles would leave 11 rows of sky
    assert frame.below == 4 and frame.bottom == pytest.approx(-PH / 2 + 4 * frame.tile)
    assert level_raise(flat, PH / frame.tile) == 4
    large = level_frame(flat, 0.35, PW, PH)   # large characters: fewer rows in the frame
    assert 0 < large.below < 4
    four = parse_level("a" + "." * 9 + "\n=====.....\n" + "\n".join(["." * 10] * 3) + "\n" + "#" * 10)
    assert level_frame(four, 0.35, PW, PH).below == 0   # tiles four rows up and a character: little sky left
    sky = PH / frame.tile - (flat.used_rows() + 2 + frame.below)
    assert sky == pytest.approx(PH / frame.tile - 7)   # 7 rows of sky, not 11


def test_the_ground_runs_on_under_a_raised_level() -> None:
    level = parse_level("a...\n##.#")
    plain = draw_columns(level_shapes(level), 0, 3, drawn_rows(level), 8)
    raised = draw_columns(level_shapes(level, below=2), 0, 3, drawn_rows(level), 8, below=2)
    assert raised.height == plain.height + 16
    assert raised.crop((0, 0, raised.width, plain.height)).tobytes() == plain.tobytes()   # the map drawn as before
    assert raised.getpixel((4, raised.height - 1))[3] == 255   # ground under a ground column
    assert raised.getpixel((2 * 8 + 4, raised.height - 1))[3] == 0   # the gap goes on down


# ----- the following camera (no manim) ---------------------------------------------------------------


def test_smooth_damp_eases_without_overshoot_and_takes_a_long_step() -> None:
    value, velocity, values = 0.0, 0.0, []
    for _ in range(100):
        value, velocity = smooth_damp(value, 1.0, velocity, 0.45, 0.04)
        values.append(value)
    assert all(0.0 <= v <= 1.0 for v in values) and values == sorted(values) and values[-1] == pytest.approx(1.0, abs=1e-3)
    assert smooth_damp(0.0, 5.0, 0.0, 0.45, 60.0)[0] == pytest.approx(5.0, abs=1e-3)   # one long step: there
    assert smooth_damp(2.0, 5.0, 0.0, 0.45, 0.0) == (2.0, 0.0)


BOUNDS = (-30.0, 30.0, -FH / 2, 10.0)


def follow(xs: list[float], spans: list[tuple[float, float]] | None = None, dt: float = 0.04) -> list[tuple[float, float]]:
    """The view's centres as a character moves through ``xs`` (and ``spans``: feet, head y)."""
    at = {"k": 0}
    camera = SmoothFollow(lambda: xs[at["k"]], None if spans is None else (lambda: spans[at["k"]]))
    center, out = (xs[0], 0.0), []
    for k in range(len(xs)):
        at["k"] = k
        center = camera.view_center(center, dt, FW, FH, BOUNDS)
        out.append(center)
    return out


def test_the_camera_waits_in_its_dead_zone_then_eases_after_the_hero() -> None:
    small = [0.5 * FOLLOW_DEAD_ZONE * FW * k / 20 for k in range(21)]
    assert all(c == (0.0, 0.0) for c in follow(small))   # a step inside the dead zone: the camera stays
    walk = [3.0 * 0.04 * k for k in range(150)] + [3.0 * 0.04 * 149] * 100   # walks 3 units/s for 6 s, stops
    centres = [c[0] for c in follow(walk)]
    steps = [b - a for a, b in zip(centres, centres[1:])]
    assert all(s >= -1e-9 for s in steps) and max(steps) <= 3.0 * 0.04 + 1e-6   # never back, never faster than the hero
    assert max(abs(b - a) for a, b in zip(steps, steps[1:])) < 0.02   # no jerk: the speed changes gently
    assert all(abs(x - c) <= FOLLOW_MAX_OFFSET * FW + 1e-6 for x, c in zip(walk, centres))
    assert abs(walk[-1] - centres[-1]) <= FOLLOW_DEAD_ZONE * FW + 1e-3   # settled with the hero inside the dead zone
    edge = follow([25.0 + k * 0.1 for k in range(100)])
    assert edge[-1][0] == pytest.approx(30.0 - FW / 2)   # clamped to the level's edge


def test_the_camera_rises_to_keep_the_head_in_frame_and_comes_back_down() -> None:
    ground = (-3.0, -1.0)   # feet and head on the ground: the camera rests at the bounds' bottom
    assert follow([0.0] * 20, [ground] * 20)[-1] == pytest.approx((0.0, 0.0))
    up = [(-3.0 + 7.0 * min(k / 25, 1.0), -1.0 + 7.0 * min(k / 25, 1.0)) for k in range(80)]   # climbs 7 up in a second
    centres = follow([0.0] * 80, up)
    assert all(head <= cy + FH / 2 - 0.02 * FH + 1e-6 for (_, head), (_, cy) in zip(up, centres))
    assert centres[-1][1] > 2.0
    down = up[-1:] * 5 + [ground] * 120
    back = follow([0.0] * len(down), down)
    assert back[-1][1] == pytest.approx(0.0, abs=1e-3)


def test_reframing_leaves_a_followed_hero_alone() -> None:
    figures = (ReframeFigure("pip", -10.0, 0.5), ReframeFigure("kit", 10.0, 0.5))
    beats = [ReframeBeat("b1", ("kit",), 3.0, figures)]
    assert reframe_path(beats, frame_width=FW, bounds=(-20.0, 20.0), start_x=-10.0)   # moves to kit
    assert reframe_path(beats, frame_width=FW, bounds=(-20.0, 20.0), start_x=-10.0, following=True) == []


def test_level_follow_names_a_character_of_the_stage(make_project) -> None:
    level = {"map": FLAT, "follow": "pip"}
    p = stage_params(level=level, characters=[{"name": "pip", "at": "a"}])
    assert p.level.follow == "pip"
    with pytest.raises(Exception, match="level.follow: 'kit' is not a character on the stage"):
        stage_params(level={**level, "follow": "kit"}, characters=[{"name": "pip", "at": "a"}])
    with pytest.raises(Exception, match="remove camera_at"):
        stage_params(level=level, characters=[{"name": "pip", "at": "a"}], camera_at="centre")


def test_directing_starts_on_the_followed_hero(make_project) -> None:
    from vidgen.cartoon.directing import CastMember, _start_state, stage_frame

    params = {"level": {"map": TALL_MAP + "", "follow": "pip"}, "characters": [{"name": "pip", "at": "a"}, {"name": "kit", "at": "c"}]}
    scenes = [{"id": "hills", "type": "stage", "params": params, "beats": [{"text": "Hi."}]}]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))
    with extensions.project_session(project) as theme:
        frame = stage_frame(project, registry.get("stage").cls.validate_params(project.scene("hills").params, theme))
    assert frame.follows == "pip" and frame.camera_x == pytest.approx(frame.places["pip"].x)
    assert _start_state([CastMember("pip"), CastMember("kit")], [], frame).camera_x is None   # the follow's


# ----- lint (no manim) --------------------------------------------------------------------------------


def test_small_speaker() -> None:
    face = [300, 200, 330, 230]   # 30 px of 480: 6 %
    tiny = fig("pip", [290, 200, 340, 290], speaking=True, face=face)
    (issue,) = check("small_speaker", [tiny])
    assert issue.message.startswith("character 'pip' speaks with its face 6.25% of the frame's shorter side tall (below 7.50%)")
    assert "shot: closeup pip" in issue.message and "character_size: large" in issue.message
    assert issue.value == pytest.approx(0.0625) and issue.limit == 0.075
    assert check("small_speaker", [{**tiny, "speaking": False}]) == []   # only who speaks
    assert check("small_speaker", [fig("pip", [290, 150, 360, 290], speaking=True, face=[300, 150, 350, 200])]) == []   # 50 px: fine
    assert check("small_speaker", [{**tiny, "bbox": [-200, 200, -150, 290], "face": [-190, 200, -160, 230]}]) == []   # not in view


def test_off_frame_leaves_a_levels_tiles_alone() -> None:
    chunk = thing("level_3", [700, 300, 900, 480], kind="image", scenery=True)
    assert check("off_frame", [chunk]) == []
    assert len(check("off_frame", [{**chunk, "scenery": None}])) == 1


# ----- renders ------------------------------------------------------------------------------------------


def tall_project(make_project, shots: bool = False, **params: Any) -> Project:
    level = {"map": TALL_MAP, "follow": "pip"}
    beats = [{"text": "Pip hops up onto the first plank.", "actions": [{"jump": "pip", "to": "b"}]},
             {"text": "And then up onto the very top one, high above.", "actions": [{"jump": "pip", "to": "c", "at": 0.1}]}]
    if shots:   # a close-up from the size the scene has, then the follow again
        beats += [{"text": "Pip looks down.", "shot": "closeup pip"}, {"text": "What a view."}]
    stage = {"level": level, "idle": False, "background": ["#88bbee", "#ddeeff"], "characters": [{"name": "pip", "at": "a"}], **params}
    scenes = [{"id": "hills", "type": "stage", "params": stage, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


def recording(monkeypatch) -> list[tuple[tuple[float, float], float, float, float]]:
    """Every frame of a following camera: the view's centre, the hero's x, head and feet y."""
    seen: list[tuple[tuple[float, float], float, float, float]] = []
    original = SmoothFollow.view_center

    def record(self, center, dt, width, height, bounds):  # type: ignore[no-untyped-def]
        out = original(self, center, dt, width, height, bounds)
        feet, head = self.span_of()
        seen.append((out, self.x_of(), head, feet))
        return out

    monkeypatch.setattr(SmoothFollow, "view_center", record)
    return seen


@pytest.mark.render
def test_a_followed_hero_stays_in_frame_across_and_up_the_level(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen.introspect import LayoutRecorder

    seen = recording(monkeypatch)
    recorder = LayoutRecorder()
    scene, objects = render_with_layout(tall_project(make_project, shots=True), "hills", tmp_path / "media", recorder)
    zooms = {frame["beat"]: frame["camera"]["zoom"] for frame in recorder.frames if "mid" not in frame}
    assert zooms["hills_b3"] > 1.5 and zooms["hills_b4"] == pytest.approx(1.0)   # the close-up zooms in, the next beat follows again
    fw, fh = scene.frame_width, scene.frame_height
    assert seen and scene.camera_following is not None and scene.camera_following.followed is scene.cast["pip"]
    left, right = scene.camera_bounds()[:2]
    for (cx, cy), x, head, feet in seen:
        at_edge = cx <= left + fw / 2 + 1e-6 or cx >= right - fw / 2 - 1e-6
        assert abs(x - cx) <= FOLLOW_MAX_OFFSET * fw + 1e-6 or at_edge
        assert head <= cy + fh / 2 + 1e-6 and feet >= cy - fh / 2 - 1e-6
    ys = [c[1] for c, *_ in seen]
    assert ys[0] == pytest.approx(0.0) and max(ys) > 0.5   # it rose for the top plank
    xs = [c[0] for c, *_ in seen]
    assert xs[-1] > xs[0] + 3.0 and max(abs(b - a) for a, b in zip(xs, xs[1:])) < 1.5
    frame = scene.params.level_frame(fw, fh)
    assert scene.cast["pip"].feet()[:2] == pytest.approx(frame.point(18.5, 7.0), abs=1e-6)
    chunks = [o for o in objects if (o["name"] or "").startswith("level_")]
    assert chunks and all(o.get("scenery") for o in chunks)


@pytest.mark.render
def test_a_large_hero_in_a_portrait_frame(make_project, tmp_path: Path, monkeypatch) -> None:
    """9:16 with large characters: the level raised on more ground, the hero followed, the moves
    timed as at medium (their sounds with them)."""
    from manim import tempconfig

    from vidgen.capture import FrameCapture
    from vidgen.introspect import LayoutRecorder

    times = {}
    for size in ("medium", "large"):
        project = tall_project(make_project, character_size=size)
        pw, ph = frame_size(90, 160)
        settings = {"pixel_width": 90, "pixel_height": 160, "frame_width": pw, "frame_height": ph, "frame_rate": 5,
                    "media_dir": str(tmp_path / f"media_{size}"), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}
        with tempconfig(settings):
            spec = project.scene("hills")
            theme = extensions.activate(project)
            scene = registry.get(spec.type).cls(spec, project, theme, capture=FrameCapture(1, [LayoutRecorder()]))
            scene.render()
            frame = scene.params.level_frame(scene.frame_width, scene.frame_height)   # the portrait frame's
        times[size] = [(round(e.time, 3), e.sound) for e in scene.sfx_log]
        if size == "large":
            assert scene.params.size == pytest.approx(0.35) and frame.tile == pytest.approx(0.35 * pw / 2)
            assert scene.cast["pip"].feet()[:2] == pytest.approx(frame.point(18.5, 7.0), abs=1e-6)
            view = scene.camera.frame
            head = scene.cast["pip"].parts["head"].get_top()[1]
            assert view.get_bottom()[1] - 1e-6 <= scene.cast["pip"].feet()[1] and head <= view.get_top()[1] + 1e-6
    assert times["medium"] and times["medium"] == times["large"]



@pytest.mark.render
def test_a_raised_level_raises_its_layers_with_it(make_project, tmp_path: Path) -> None:
    """9:16 at medium: a one-row map sits four rows up on more ground, and the hills behind it rise
    as much, so they stand behind the ground as on a landscape level."""
    from manim import tempconfig

    from vidgen.capture import FrameCapture
    from vidgen.introspect import LayoutRecorder

    hills = {"place": "middle", "shapes": [{"shape": "hills", "y": 0.1, "width": 0.6, "height": 0.15, "color": "#7CC456"}]}
    stage = {"level": {"map": FLAT}, "idle": False, "layers": [hills], "characters": [{"name": "pip", "at": "a"}]}
    scenes = [{"id": "field", "type": "stage", "params": stage, "beats": [{"text": "Pip on the field."}]}]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))
    pw, ph = frame_size(90, 160)
    settings = {"pixel_width": 90, "pixel_height": 160, "frame_width": pw, "frame_height": ph, "frame_rate": 5,
                "media_dir": str(tmp_path / "media"), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}
    with tempconfig(settings):
        spec = project.scene("field")
        theme = extensions.activate(project)
        scene = registry.get(spec.type).cls(spec, project, theme, capture=FrameCapture(1, [LayoutRecorder()]))
        scene.render()
        frame = scene.params.level_frame(scene.frame_width, scene.frame_height)
    assert frame.below == 4
    assert scene.cast["pip"].feet()[1] == pytest.approx(-ph / 2 + 5 * frame.tile)   # on the raised ground's top
    tiles = scene._backdrop[-1]
    assert min(c.get_bottom()[1] for c in tiles.chunks) == pytest.approx(-ph / 2, abs=1e-6)   # ground drawn down to the frame's bottom
    layer = scene.layers["middle_layer"]
    assert layer.get_top()[1] == pytest.approx(-ph / 2 + 0.1 * ph + 0.15 * pw + 4 * frame.tile, abs=0.02)
