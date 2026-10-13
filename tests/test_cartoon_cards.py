"""Step 112: cartoon transitions and title cards. The iris transitions (config, plan, the circle's
radius and coverage, validation), the ``card`` scene's layout, colours and params, the screenplay's
``# Card:`` headings, without rendering; one tiny card render checked by the lint rules and one
tiny video (stage -iris_out-> card -iris_in-> stage) rendered and joined with the ffmpeg on PATH."""

from __future__ import annotations

import contextlib
import io
import json
import math
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest
import yaml

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES
from vidgen import extensions, registry
from vidgen.cartoon.cards import (
    CARD_INK,
    CARD_WHITE,
    burst_ray_color,
    burst_rays,
    card_layout,
    card_outline_width,
    card_text_inks,
)
from vidgen.cli import main, project_problems
from vidgen.config import TransitionConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.lint.color import contrast_ratio, hex_rgb
from vidgen.project import Project
from vidgen.screenplay import CARD_SECONDS, parse_screenplay, screenplay_project
from vidgen.transitions import (
    IRIS_COLOR,
    IRIS_HOLD,
    ColorFade,
    IrisPoint,
    effective,
    iris_coverage,
    iris_full_radius,
    iris_radius,
    join_overlaps,
    requested_frames,
    resolve_color,
)
from vidgen.videoplan import VideoPlan

FPS = 10


def _stage(scene_id: str, who: str, at: str, **extra: Any) -> dict[str, Any]:
    return {"id": scene_id, "type": "stage", "params": {"characters": [{"name": who, "at": at}], "idle": False}, "duration": 1.5, **extra}


def _config(**extra: Any) -> dict[str, Any]:
    scenes = extra.pop("scenes", None) or [
        _stage("a", "pip", "left"),
        {"id": "later", "type": "card", "params": {"text": "Later"}, "duration": 1.5, "transition": {"type": "iris_out", "character": "pip"}},
        _stage("b", "kit", "right", transition={"type": "iris_in", "character": "kit", "color": "#FF0000"}),
    ]
    return minimal_config(characters=CAST, voices=VOICES, format={"width": 160, "height": 90, "fps": FPS}, scenes=scenes, **extra)


# ----- the iris transitions: config and plan ----------------------------------------------------------


def test_iris_forms_and_defaults() -> None:
    cfg = parse_config(_config())
    out, into = effective(cfg, 1), effective(cfg, 2)
    assert (out.type, out.character, out.at, out.seconds) == ("iris_out", "pip", None, 1.2)
    assert out.through_color and not out.overlaps and into.color == "#FF0000"
    assert TransitionConfig(type="iris_in", at=(0.25, 0.4)).at == (0.25, 0.4)
    assert requested_frames(out, FPS) == 6   # half the duration on each side, as fade_color
    assert resolve_color(None, None, "iris_out") == IRIS_COLOR   # black, not the theme's background


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"type": "fade_color", "character": "pip"}, "character is only for iris_out and iris_in"),
        ({"type": "crossfade", "at": [0.5, 0.5]}, "at is only for iris_out and iris_in"),
        ({"type": "iris_out", "character": "pip", "at": [0.5, 0.5]}, "a character or a point"),
        ({"type": "iris_in", "at": [1.5, 0.5]}, "fractions of the frame"),
        ({"type": "wipe", "color": "accent"}, "color is only for fade_color, iris_out and iris_in"),
    ],
)
def test_iris_errors(value: Any, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        parse_config(_config(transition=value))


def test_first_scene_can_iris_in_but_not_out() -> None:
    scenes = _config()["scenes"]
    scenes[0]["transition"] = "iris_out"
    with pytest.raises(VidgenError, match="first scene has no scene before it to iris_out from"):
        parse_config(_config(scenes=scenes))
    scenes[0]["transition"] = {"type": "iris_in", "character": "pip"}
    assert effective(parse_config(_config(scenes=scenes)), 0).type == "iris_in"


def test_plan_closes_and_opens_without_overlap(make_project: Any) -> None:
    project = Project.load(make_project(_config()))
    with extensions.project_session(project):
        plan = VideoPlan(project, FPS)
        slot = plan.transition(1)
        assert (slot.type, slot.overlap, slot.fade_out, slot.fade_in, slot.hold) == ("iris_out", 0, 6, 6, 0)
        assert plan.duration == pytest.approx(4.5)   # no overlap: the video keeps every frame
        assert join_overlaps(project.config, FPS, [15, 15, 15], [None, None, None]) == [0, 0, 0]


def test_validate_finds_an_iris_character_not_on_the_stage(make_project: Any) -> None:
    assert project_problems(Project.load(make_project(_config()))) == []
    scenes = _config()["scenes"]
    scenes[1]["transition"]["character"] = "kit"   # kit is in b, not in a
    scenes[2]["transition"] = {"type": "iris_in", "character": "rex"}
    problems = [str(p) for p in project_problems(Project.load(make_project(_config(scenes=scenes))))]
    assert problems == [
        "scenes[1].transition.character: the iris_out into 'later' closes on 'kit', who is not in scene 'a' (its characters: pip)",
        "scenes[2].transition.character: the iris_in into 'b' opens on 'rex', who is not in scene 'b' (its characters: kit)",
    ]


# ----- the iris: radius, coverage, the masked frames ------------------------------------------------


def test_iris_radius_eases_and_pauses_on_a_head() -> None:
    assert iris_radius(0.0, 100.0) == 100.0 and iris_radius(1.0, 100.0) == 0.0
    assert iris_radius(0.5, 100.0) == pytest.approx(50.0)
    radii = [iris_radius(k / 20, 100.0, 12.0) for k in range(21)]
    assert all(a >= b for a, b in zip(radii, radii[1:]))   # it only closes
    reach, leave = IRIS_HOLD
    assert iris_radius(reach, 100.0, 12.0) == iris_radius(leave, 100.0, 12.0) == 12.0   # paused on the head
    assert iris_radius(1.0, 100.0, 12.0) == 0.0 and iris_radius(0.3, 100.0, 200.0) == iris_radius(0.3, 100.0)   # a huge head: no pause
    assert iris_full_radius(160, 90, 80, 45) == pytest.approx(math.hypot(80, 45) + 1)
    assert iris_full_radius(160, 90, 0, 0) == pytest.approx(math.hypot(160, 90) + 1)   # to the far corner


def test_iris_coverage_is_a_soft_disc() -> None:
    inside = iris_coverage(9, 16, 8.0, 4.5, 3.0)
    assert inside.shape == (9, 16) and inside[4, 8] == 1.0 and inside[0, 0] == 0.0
    assert inside.sum() == pytest.approx(math.pi * 9, rel=0.15)
    assert iris_coverage(9, 16, 8.0, 4.5, 0.0).max() <= 0.5   # closed: nothing shows


def test_color_fade_with_irises_masks_a_circle() -> None:
    opened, closed = [], []
    fade = ColorFade(
        "#000000", 4, "#FF0000", 4, 20,
        iris_in=lambda w, h: opened.append((w, h)) or IrisPoint(w * 0.75, h / 2),
        iris_out=lambda w, h: closed.append((w, h)) or IrisPoint(4.0, 4.0, hold=2.0),
    )
    frame = np.full((18, 32, 4), 200, dtype=np.uint8)
    assert fade.apply(frame, 0)[:, :, :3].max() == 0   # the first frame: closed
    half = fade.apply(frame, 2)   # weight 0.5: a circle about (24, 9)
    assert half[9, 24, :3].tolist() == [200, 200, 200] and half[0, 0, :3].tolist() == [0, 0, 0]
    assert half[:, :, 3].tolist() == frame[:, :, 3].tolist()   # alpha untouched
    assert opened == [(32, 18), (32, 18)]   # asked on each frame it masks
    paused = fade.apply(frame, 18)   # weight 0.75: paused on the head
    assert paused[4, 4, :3].tolist() == [200, 200, 200] and paused[4, 8, :3].tolist() == [255, 0, 0]
    assert fade.apply(frame, 19)[:, :, :3].reshape(-1, 3).tolist() == [[255, 0, 0]] * (18 * 32)   # the last frame: the colour
    assert fade.apply(frame, 10) is frame and closed == [(32, 18), (32, 18)]


# ----- the card: layout, colours, params ----------------------------------------------------------------


def test_card_layout_per_style_and_shape() -> None:
    wide, tall = card_layout(14.22, 8.0, style="burst", subtitle=True), card_layout(4.5, 8.0, style="burst", subtitle=False)
    assert wide.text_width < 14.22 * 0.8 and wide.subtitle_height > 0 and wide.gap > 0 and wide.frame_outer is None
    assert tall.subtitle_height == 0.0 and tall.text_height > wide.text_height * 0.9 and tall.text_width < 4.5
    assert wide.burst_radius >= math.hypot(14.22, 8.0) / 2   # the rays reach every corner
    framed = card_layout(14.22, 8.0, style="frame", subtitle=True)
    (ow, oh), (iw, ih) = framed.frame_outer, framed.frame_inner
    assert ow < 14.22 and oh < 8.0 and iw < ow and ih < oh
    assert framed.text_width < iw and framed.text_height + framed.subtitle_height + framed.gap < ih   # clear of the lines
    with pytest.raises(ValueError, match="unknown card style 'zigzag'"):
        card_layout(14.22, 8.0, style="zigzag", subtitle=False)


def test_card_colours_and_outline() -> None:
    assert card_text_inks("#1B2140") == (CARD_WHITE, CARD_INK)   # dark card: white letters, dark outline
    assert card_text_inks("#FFE45C") == (CARD_INK, CARD_WHITE)   # light card: dark letters
    blue = "#5BC0DE"
    fill, _ = card_text_inks(blue, burst_ray_color(blue))
    assert min(contrast_ratio(hex_rgb(fill), hex_rgb(c)) for c in (blue, burst_ray_color(blue))) >= 3.0   # large text reads
    assert burst_ray_color("#000000", 0.5) == "#808080" and burst_ray_color(blue, 0.0) == blue
    assert card_outline_width(1.0) == pytest.approx(18.0) and card_outline_width(0.5) == pytest.approx(9.0)


def test_burst_rays() -> None:
    rays = burst_rays(10.0)
    assert len(rays) == 9 and all(len(r) == 3 and r[0] == (0.0, 0.0) for r in rays)
    assert all(math.hypot(*p) == pytest.approx(10.0) for r in rays for p in r[1:])
    turned = burst_rays(10.0, turn=0.1, count=4)
    assert math.atan2(turned[0][1][1], turned[0][1][0]) == pytest.approx(0.1) and len(turned) == 2
    with pytest.raises(ValueError, match="even number of rays"):
        burst_rays(10.0, count=5)


def test_card_params_and_targets() -> None:
    extensions.load_builtins()
    cls = registry.get("card").cls
    params = cls.validate_params({"text": "Episode 3", "subtitle": "The Kite", "sting": "reveal"})
    assert params.style == "burst" and params.sting.kind == "reveal" and cls.target_names(params) == ["text", "subtitle", "burst"]
    assert cls.target_names(cls.validate_params({"text": "Later", "style": "plain"})) == ["text"]
    for raw, message in (({"text": ""}, "at least 1 character"), ({"text": "x", "sting": {"kind": "sad", "at": "end"}}, "plays as the text pops in")):
        with pytest.raises(Exception, match=message):
            cls.validate_params(raw)


# ----- the screenplay's # Card: headings -----------------------------------------------------------------


PLAY = """# The Kite

# Card: Episode 3

# Scene: yard
PIP: Look, a kite!

# Card: Later that day…

## Card: Meanwhile
NARRATOR: Kit was far away.
[Kit waves]

# Scene: hill
KIT: Hello up there.
"""


def test_screenplay_cards() -> None:
    play = parse_screenplay(PLAY)
    assert play.title == "The Kite" and [(s.name, s.card) for s in play.scenes] == [
        ("Episode 3", True), ("yard", False), ("Later that day…", True), ("Meanwhile", True), ("hill", False)
    ]
    draft = screenplay_project(play)
    episode, yard, later, meanwhile, hill = draft.config["scenes"]
    assert episode == {"id": "episode_3", "type": "card", "params": {"text": "Episode 3"}, "duration": CARD_SECONDS}   # first: no iris
    assert yard["transition"] == "iris_in" and list(yard)[:3] == ["id", "type", "transition"]
    assert later == {"id": "later_that_day", "type": "card", "params": {"text": "Later that day…"}, "transition": "iris_out", "duration": CARD_SECONDS}
    assert meanwhile["beats"] == [{"text": "Kit was far away."}] and meanwhile["transition"] == "iris_out" and "duration" not in meanwhile
    assert hill["transition"] == "iris_in"
    assert any("a card has no stage" in t for t in draft.beat_todos[3][0])
    assert parse_config(draft.config).scenes[1].transition.type == "iris_in"   # a valid config
    with pytest.raises(VidgenError, match="set: belongs to a # Scene:, not to a # Card:"):
        parse_screenplay("# Card: Later\nset: background: night\n")


# ----- renders --------------------------------------------------------------------------------------------


@pytest.mark.render
def test_card_render_reads_well(make_project: Any, tmp_path: Path) -> None:
    from test_cartoon_stage import render_with_layout

    from vidgen.config import LintRules
    from vidgen.introspect import LayoutRecorder
    from vidgen.lint import RULES, StillContext

    scenes = [{"id": "c", "type": "card", "params": {"text": "Later that day…", "subtitle": "at the park"}, "duration": 2}]
    project = Project.load(make_project(minimal_config(scenes=scenes)))
    recorder = LayoutRecorder()
    extensions.load_builtins()
    scene, objects = render_with_layout(project, "c", tmp_path / "media", recorder)
    texts = [o for o in objects if o["kind"] == "text"]
    assert sorted(o["text"] for o in texts) == ["Later that day…", "at the park"]
    assert any(o["kind"] == "group" for o in objects)   # the burst and the outlines: shapes, not text
    rules = LintRules()
    for frame in recorder.frames:
        ctx = StillContext({"width": 160, "height": 90}, frame, frame["objects"])
        for name in ("contrast", "off_frame"):
            assert list(RULES[name].check(ctx, getattr(rules, name))) == [], name


def _frames(path: Path) -> np.ndarray:
    with av.open(str(path)) as container:
        return np.stack([f.to_ndarray(format="rgb24").astype(np.int16) for f in container.decode(video=0)])


@pytest.mark.render
def test_irises_through_the_join(tmp_path: Path) -> None:
    """a (pip at left) -iris_out on pip-> later (a card with a sting) -iris_in on kit, red-> b (kit
    at right) -crossfade-> end (a card), rendered and joined by the ffmpeg on PATH: the irises are
    in the renders, so they are cuts inside the run the crossfade's ``xfade`` blends with the end."""
    root = tmp_path / "proj"
    root.mkdir()
    data = _config(output="out", preview={"width": 160, "height": 90, "fps": FPS})
    data["scenes"][1]["params"]["sting"] = "comic"
    data["scenes"].append({"id": "end", "type": "card", "params": {"text": "The End", "style": "frame"}, "duration": 1.5, "transition": "crossfade"})
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    out = io.StringIO()
    with registry.isolated(), contextlib.redirect_stdout(out):
        assert main(["render", str(root), "--preview", "--json"]) == 0
    from vidgen import runtime

    runtime.clear_context()
    video = _frames(root / "output" / "out_preview.mp4")
    assert len(video) == 55   # four 1.5 s scenes, the crossfade's 5 frames overlapped, the irises none
    first_run = next(root.rglob("video_concat_0.txt")).read_text(encoding="utf-8")
    assert [line.split("/")[-1].strip("'\n") for line in first_run.splitlines()] == ["a.mp4", "later.mp4", "b.mp4"]   # cut together
    black, red = np.zeros(3), np.array([255, 0, 0])

    def near(frame: np.ndarray, color: np.ndarray) -> float:
        return float(np.abs(frame - color).max(axis=2).mean())

    assert near(video[14], black) < 4 and near(video[15], black) < 4   # a's last frame, the card's first
    assert near(video[29], red) < 8 and near(video[30], red) < 8   # the card closes to red, b opens from it
    closing = video[12]   # 2 frames before the cut: paused around pip's head on the left
    assert near(closing[:, 100:], black) < 4 and np.abs(closing[:, :70]).max() > 60
    opening = video[33]   # b's 4th frame: the circle about kit on the right
    assert near(opening[:, :50], red) < 8 and near(opening[20:60, 110:130], red) > 60
    card = video[18]   # the card opening from the centre
    assert near(card[40:50, 75:85], black) > 60 and near(card[:5, :5], black) < 4
    timings = json.loads((root / "build" / "preview" / "timings.json").read_text(encoding="utf-8"))
    later = next(s for s in timings["scenes"] if s["id"] == "later")
    [sting] = later["sfx"]
    assert sting["sound"] == "sting_comic" and sting["duck"] is True and sting["time"] == pytest.approx(1.5, abs=0.01)
    assert later["transition"]["type"] == "iris_out"
