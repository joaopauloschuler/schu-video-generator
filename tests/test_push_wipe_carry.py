"""Push and wipe transitions and carried objects (Step 47, DESIGN.md §50): config, the xfade
graph and its frame math, overlays drawn once over the moving pictures, the carry record's round
trip, render order with ``--jobs``, and a rendered video checked frame by frame."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest
import yaml

from vidgen import extensions, registry, runtime
from vidgen.carry import carried_from, carried_out, carry_problems, carry_warnings, parts_state, read_record, rebuild, write_record
from vidgen.cli import main, project_problems, validate_warnings
from vidgen.config import CarryEntry, TransitionConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.overlay_layer import OverlayLayer, RgbaClip, _Patch
from vidgen.project import Project
from vidgen.render import ffmpeg as ff
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.render.pipeline import _runs, _WorkerRun, with_carried
from vidgen.transitions import direction, effective, moves_pictures, xfade_name
from vidgen.videoplan import VideoPlan

FPS = 10


def _config(**extra: Any) -> dict[str, Any]:
    scenes = extra.pop("scenes", None) or [
        {"id": "a", "type": "title", "params": {"title": "A"}, "beats": [{"text": "one two three four five six"}]},
        {"id": "card", "type": "chapter", "params": {"number": 1, "title": "Card", "icon": "rocket"}, "duration": 2},
        {"id": "b", "type": "bullets", "params": {"heading": "Card", "items": ["x"]}, "beats": [{"text": "seven eight nine"}], "carry": ["title -> heading"]},
        {"id": "c", "type": "title", "params": {"title": "C"}, "beats": [{"text": "eleven twelve"}]},
    ]
    return {"title": "T", "format": {"width": 160, "height": 90, "fps": FPS}, **extra, "scenes": scenes}


# ----- config ------------------------------------------------------------------------------------------


def test_push_and_wipe_config() -> None:
    push = TransitionConfig(type="push")
    assert push.seconds == 0.6 and push.overlaps and moves_pictures(push)
    assert TransitionConfig(type="wipe", direction="down", soft=True).soft
    assert not moves_pictures(TransitionConfig(type="crossfade")) and TransitionConfig(type="crossfade").overlaps
    cfg = parse_config(_config(transition={"type": "wipe", "direction": "right", "duration": 0.4}))
    assert effective(cfg, 1).type == "wipe" and effective(cfg, 1).direction == "right"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"type": "crossfade", "direction": "up"}, "direction is only for push and wipe"),
        ({"type": "push", "soft": True}, "soft is only for wipe"),
        ({"type": "wipe", "direction": "sideways"}, "direction"),
    ],
)
def test_push_wipe_errors(value: Any, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        parse_config(_config(transition=value))


def test_first_scene_cannot_push_or_carry() -> None:
    scenes = _config()["scenes"]
    scenes[0]["transition"] = "push"
    with pytest.raises(VidgenError, match="no scene before it to push from"):
        parse_config(_config(scenes=scenes))
    scenes = _config()["scenes"]
    scenes[0]["carry"] = "title"
    with pytest.raises(VidgenError, match="no scene before it to carry objects from"):
        parse_config(_config(scenes=scenes))


def test_carry_entries() -> None:
    cfg = parse_config(_config())
    assert cfg.scenes[2].carry == [CarryEntry(source="title", dest="heading")]
    assert cfg.scenes[2].model_dump(mode="json")["carry"] == ["title -> heading"]
    scenes = _config()["scenes"]
    scenes[2]["carry"] = "icon"
    assert parse_config(_config(scenes=scenes)).scenes[2].carry == [CarryEntry(source="icon", dest="icon")]
    assert carried_from(parse_config(_config())) == {"b": "card"}
    assert [str(e) for e in carried_out(parse_config(_config()), "card")] == ["title -> heading"]
    assert carried_out(parse_config(_config()), "c") == [] and carried_out(parse_config(_config()), "elsewhere") == []
    for bad, message in (("a -> b -> c", "invalid carry entry"), ("9x", "invalid target name"), (["x", "y -> x"], "two entries move into 'x'")):
        scenes[2]["carry"] = bad
        with pytest.raises(VidgenError, match=message):
            parse_config(_config(scenes=scenes))


def test_xfade_names_and_default_directions() -> None:
    push, wipe = TransitionConfig(type="push"), TransitionConfig(type="wipe", soft=True)
    assert (direction(push, False), direction(push, True)) == ("left", "up")
    assert xfade_name(push, False) == "slideleft" and xfade_name(push, True) == "slideup"
    assert xfade_name(TransitionConfig(type="push", direction="right"), True) == "slideright"
    assert xfade_name(wipe, False) == "smoothleft" and xfade_name(TransitionConfig(type="wipe", direction="down"), False) == "wipedown"
    assert xfade_name(TransitionConfig(type="crossfade"), False) == "fade" and direction(TransitionConfig(type="crossfade"), False) is None


def test_validate_checks_carry_targets(make_project: Any) -> None:
    scenes = _config()["scenes"]
    scenes[2]["carry"] = ["titel -> heading", "icon -> nothing"]
    project = Project.load(make_project(_config(scenes=scenes)))
    problems = [str(p) for p in project_problems(project)]
    assert any("scenes[2].carry: 'titel -> heading': unknown target 'titel'" in p and "did you mean 'title'" in p and "'card'" in p for p in problems)
    assert any("'icon -> nothing': unknown target 'nothing' for scene type 'bullets'" in p for p in problems)
    scenes[2]["carry"] = ["title -> heading"]
    scenes[2]["transition"] = "push"
    project = Project.load(make_project(_config(scenes=scenes), folder="p2"))
    assert not project_problems(project)
    [warning] = [w for w in validate_warnings(project) if "carry" in w]
    assert "through a push" in warning
    with extensions.project_session(project):
        assert carry_problems(project.config) == [] and carry_warnings(project.config) == [warning]


def test_plan_overlaps_pushes_like_crossfades(make_project: Any) -> None:
    project = Project.load(make_project(_config(transition="push")))
    with extensions.project_session(project):
        plan = VideoPlan(project, FPS)
        assert [plan.transition(i).overlap for i in range(4)] == [0, 6, 6, 6]
        assert plan.scene("card").start == pytest.approx(plan.scene("a").end - 0.6)
    assert project.estimated_duration() == pytest.approx(Project.load(make_project(_config(), folder="x")).estimated_duration() - 1.8)


def test_fingerprints_follow_carries(make_project: Any) -> None:
    root = make_project(_config())
    project = Project.load(root)
    before = {sid: scene_fingerprint(project, sid) for sid in ("a", "card", "b", "c")}
    data = _config()
    data["scenes"][1]["params"]["title"] = "Card!"  # the card's end changes: b starts from it
    data["scenes"][2]["params"]["heading"] = "Card!"
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    changed = {sid: scene_fingerprint(Project.load(root), sid) for sid in before}
    assert changed["card"] != before["card"] and changed["b"] != before["b"]
    assert changed["a"] == before["a"] and changed["c"] == before["c"]
    data = _config()
    data["scenes"][2]["carry"] = ["icon -> heading"]  # the card keeps another target on screen
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert scene_fingerprint(Project.load(root), "card") != before["card"]


# ----- the join: xfade graph, frame math, overlays drawn once ------------------------------------------


def test_graph_strings() -> None:
    graph, label = ff.crossfade_graph([20, 15], [5], 10, ["slideup"])
    assert graph[2] == "[r0][r1]xfade=transition=slideup:duration=0.500000:offset=1.450000[x1]" and label == "x1"
    drawn, label = ff.overlay_graph("x1", [(2, 15)], 10)
    assert drawn == ["[2:v]settb=AVTB,setpts=PTS-STARTPTS+1.450000/TB[c0]", "[x1][c0]overlay=eof_action=pass:format=yuv444[o0]"]
    assert label == "o0"


def _solid(path: Path, color: tuple[int, int, int], frames: int, size: tuple[int, int] = (64, 36)) -> Path:
    with av.open(str(path), "w") as box:
        stream = box.add_stream("libx264", rate=FPS)
        stream.width, stream.height, stream.pix_fmt = size[0], size[1], "yuv444p"
        stream.options = {"qp": "0"}
        image = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        image[:] = color
        for _ in range(frames):
            for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                box.mux(packet)
        for packet in stream.encode():
            box.mux(packet)
    return path


def _decode(path: Path) -> np.ndarray:
    with av.open(str(path)) as c:
        return np.stack([f.to_ndarray(format="rgb24").astype(np.int16) for f in c.decode(video=0)])


@pytest.mark.parametrize(
    ("kind", "axis", "new_side"),
    [("slideleft", 1, "end"), ("slideright", 1, "start"), ("wipeup", 0, "end"), ("wipedown", 0, "start")],
)
def test_push_wipe_frame_math(tmp_path: Path, kind: str, axis: int, new_side: str) -> None:
    """Red joined to blue over 10 frames: at shared frame j the blue part covers (j + 0.5) / 10 of
    the picture, from the side the next scene comes in; an RGBA clip lands exactly on the shared
    frames, and the video passes unchanged after it."""
    ffmpeg = ff.find_ffmpeg()
    red, blue = _solid(tmp_path / "a.mp4", (255, 0, 0), 20), _solid(tmp_path / "b.mp4", (0, 0, 255), 20)
    audios = []
    for name in ("a", "b"):
        ff.pad_audio(ffmpeg, None, tmp_path / f"{name}.wav", 2 * ff.AUDIO_RATE)
        audios.append(tmp_path / f"{name}.wav")
    clip = RgbaClip(tmp_path / "o.mov", 64, 36, FPS)
    for j in range(10):
        mark = np.zeros((36, 64, 4), dtype=np.uint8)
        mark[16:20, 4 * j : 4 * j + 4] = 255  # a white square at x = 4 j: tells which clip frame shows
        clip.write(mark)
    clip.close()
    out = tmp_path / "out.mp4"
    ff.join(ffmpeg, [red, blue], audios, out, tmp_path, crossfades=[10], frames=[20, 20], fps=FPS, kinds=[kind], overlays=[(clip.path, 10)])
    video = _decode(out)
    assert len(video) == 30
    for j in range(10):
        frame = video[10 + j]
        known = frame.min(axis=2) <= 200  # not the clip's marks
        bluish = (frame[:, :, 2] > 128) & (frame[:, :, 0] < 128) & known
        share = bluish.sum(axis=1 - axis) / known.sum(axis=1 - axis)  # per column (axis 1) / per row (axis 0)
        assert bluish.sum() / known.sum() == pytest.approx((j + 0.5) / 10, abs=0.06), j
        edge = share[-1] if new_side == "end" else share[0]
        assert j < 2 or edge > 0.9, j  # the next scene comes in from that side
        white = (frame[16:20].min(axis=2) > 200).any(axis=0)
        assert np.nonzero(white)[0].min() // 4 == j  # the clip's frame j on shared frame j
    for k in (9, 20, 25):
        assert not (video[k][16:20].min(axis=2) > 200).any(), k  # nothing outside the clip
    assert np.abs(video[9] - [255, 0, 0]).mean() < 3 and np.abs(video[20] - [0, 0, 255]).mean() < 3


class _FakeLayer(OverlayLayer):
    """An :class:`OverlayLayer` with given patches, no Manim."""

    def __init__(self, patches: list[_Patch]) -> None:
        self.patches = patches
        self.mobjects = [object()] * len(patches)  # type: ignore[list-item]
        self.following_mobjects = []

    def _patch(self, k: int, state: Any) -> _Patch:
        return self.patches[k]


def test_overlay_rgba_composites_like_the_layer() -> None:
    """The overlays alone (RGBA, straight alpha) over a picture give what the layer composites."""
    rng = np.random.default_rng(3)

    def patch(box: tuple[int, int, int, int], alpha: float, rgb: tuple[int, int, int]) -> _Patch:
        h, w = box[1] - box[0], box[3] - box[2]
        a = np.full((h, w, 1), alpha * 255)
        return _Patch(box, np.rint(np.array(rgb) * a / 255).astype(np.uint16) * np.ones((h, w, 3), np.uint16), np.rint(255 - a).astype(np.uint16))

    layer = _FakeLayer([patch((2, 10, 2, 12), 0.5, (255, 255, 255)), patch((6, 14, 8, 20), 0.8, (20, 200, 90))])
    frame = np.zeros((16, 24, 4), dtype=np.uint8)
    frame[:, :, :3] = rng.integers(0, 256, (16, 24, 3))
    frame[:, :, 3] = 255
    composited = layer.composite(frame, ("s", "t")).astype(np.float64)
    rgba = layer.rgba(("s", "t"), 16, 24).astype(np.float64)
    a = rgba[:, :, 3:] / 255
    over = rgba[:, :, :3] * a + frame[:, :, :3] * (1 - a)
    assert np.abs(over - composited[:, :, :3]).max() <= 2
    assert rgba[0, 0, 3] == 0 and rgba[3, 3, 3] == 127  # transparent outside, half inside the first
    assert (layer.rgba((None, None), 16, 24) == 0).all()


# ----- carried objects: the record and the order of renders --------------------------------------------


def test_carried_shapes_draw_exactly_like_the_originals(tmp_path: Path) -> None:
    from manim import BLUE, RIGHT, UP, Camera, Circle, Square, Text, VGroup, tempconfig

    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": 14.22, "frame_height": 8.0, "text_dir": str(tmp_path)}):
        title = Text("Carry me", font_size=40, color="#E8EAED").shift(1.2 * UP)
        shapes = VGroup(Circle(radius=1, color=BLUE, fill_opacity=0.4, stroke_width=6), Square(1).set_fill("#FF6B6B", 1).shift(3 * RIGHT))
        original = VGroup(title, shapes)
        state, skipped = parts_state([original])
        path = tmp_path / "carry" / "s.json"
        write_record(path, "s", "abc", {"title": state})
        record = read_record(path)
        assert record is not None and record["fingerprint"] == "abc" and skipped == 0
        copy = rebuild(record["objects"]["title"])
        assert len(copy) == len(original.family_members_with_points())
        drawn = []
        for mob in (original, copy):
            camera = Camera()
            camera.capture_mobjects([mob])
            drawn.append(np.asarray(camera.pixel_array, dtype=np.int16))
        assert np.abs(drawn[0] - drawn[1]).max() <= 1
    assert read_record(tmp_path / "missing.json") is None


def test_runs_start_a_carrying_scene_after_the_scene_before() -> None:
    """With several workers, 'b' (carrying from the slow 'card') waits for it; others do not."""
    events: list[tuple[str, str]] = []
    lock = threading.Lock()

    def task(_: int, sid: str) -> _WorkerRun:
        with lock:
            events.append(("start", sid))
        time.sleep(0.3 if sid == "card" else 0.01)
        with lock:
            events.append(("end", sid))
        return _WorkerRun(sid, 0, "", 0.0)

    done = [run.scene_id for run in _runs(task, ["a", "card", "b", "c"], 4, {"b": "card"})]
    assert sorted(done) == ["a", "b", "c", "card"]
    assert events.index(("end", "card")) < events.index(("start", "b"))
    assert events.index(("end", "c")) < events.index(("end", "card"))  # c did not wait


def test_with_carried_adds_what_the_carry_needs(make_project: Any) -> None:
    project = Project.load(make_project(_config()))
    with extensions.project_session(project):
        # no record of the card: rendering b alone renders the card first
        assert with_carried(project, True, ["b"]) == ["card", "b"]
        # a current record: b alone; the card re-rendered: b follows (it never met this card)
        fingerprint = scene_fingerprint(project, "card")
        write_record(project.render_dir(True) / "carry" / "card.json", "card", fingerprint, {"title": []})
        assert with_carried(project, True, ["b"]) == ["b"]
        assert with_carried(project, True, ["card"]) == ["card", "b"]
        timings = project.render_dir(True) / "timings" / "b.json"
        timings.parent.mkdir(parents=True)
        timings.write_text(json.dumps({"render": {"carry_from": fingerprint}}), encoding="utf-8")
        assert with_carried(project, True, ["card"]) == ["card"]
        assert with_carried(project, True, ["a", "c"]) == ["a", "c"]


# ----- a rendered video ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    """intro -push-> card (chapter) -cut, carry title -> heading-> more (bullets) -wipe up-> outro,
    rendered with three workers; progress bar, watermark and captions."""
    root = tmp_path_factory.mktemp("push_wipe") / "proj"
    root.mkdir(parents=True)
    data = {
        "title": "Push",
        "output": "out",
        "format": {"width": W, "height": H, "fps": FPS},
        "preview": {"width": W, "height": H, "fps": FPS},
        "overlays": [
            {"type": "progress_bar"},
            {"type": "watermark", "text": "wm", "corner": "bottom_right", "size": 0.08, "opacity": 1.0},
            {"type": "captions"},
        ],
        "scenes": [
            {"id": "intro", "type": "title", "params": {"title": "Intro"}, "beats": [{"text": "The intro speaks here."}]},
            {"id": "card", "type": "chapter", "transition": "push", "params": {"title": "Card", "number": 2}, "duration": 2},
            {
                "id": "more", "type": "bullets", "carry": ["title -> heading"],
                "params": {"heading": "Card", "items": ["x"]}, "beats": [{"text": "The heading came from the card."}],
            },
            {"id": "outro", "type": "title", "transition": {"type": "wipe", "direction": "up"}, "params": {"title": "Bye"}, "beats": [{"text": "Goodbye now."}]},
        ],
    }
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    out = io.StringIO()
    with registry.isolated(), contextlib.redirect_stdout(out):
        assert main(["render", str(root), "--preview", "--json", "--jobs", "3"]) == 0
    runtime.clear_context()
    return root, json.loads(out.getvalue())


def _plan(root: Path) -> VideoPlan:
    project = Project.load(root)
    with extensions.project_session(project):
        plan = VideoPlan(project, FPS)
        plan.scenes
    return plan


@pytest.mark.render
@pytest.mark.slow
def test_rendered_push_wipe_timings(rendered: tuple[Path, dict[str, Any]]) -> None:
    root, _ = rendered
    plan = _plan(root)
    timings = json.loads((root / "build/preview/timings.json").read_text(encoding="utf-8"))
    assert [s["start"] for s in timings["scenes"]] == pytest.approx([s.start for s in plan.scenes], abs=1e-6)
    assert timings["scenes"][1]["transition"] == {"type": "push", "duration": 0.6, "overlap": 0.6, "direction": "left"}
    assert timings["scenes"][3]["transition"]["direction"] == "up"
    assert len(_decode(root / "out_preview.mp4")) == round(plan.duration * FPS)
    # the incoming scenes' first frames are bare; their overlays went to a clip (+ an end frame)
    for sid in ("card", "outro"):
        meta = json.loads((root / f"build/preview/timings/{sid}.json").read_text(encoding="utf-8"))["render"]
        assert meta["overlays"]["head"] == 6
        assert len(_decode(root / f"build/preview/scenes/{sid}.overlay.mov")) == 7
    assert not (root / "build/preview/scenes/more.overlay.mov").exists()


W, H = 320, 180


def _watermark(frame: np.ndarray) -> np.ndarray:
    return frame[int(0.85 * H) :, int(0.85 * W) :]


def _captions(frame: np.ndarray) -> np.ndarray:
    return frame[int(0.78 * H) : int(0.98 * H), int(0.15 * W) : int(0.8 * W)]


def _background(frame: np.ndarray) -> np.ndarray:
    return frame[H // 2, 8]


def _drawn(region: np.ndarray, background: np.ndarray, threshold: int = 40) -> np.ndarray:
    return np.abs(region - background).max(axis=2) > threshold


@pytest.mark.render
@pytest.mark.slow
def test_overlays_stay_put_through_a_push(rendered: tuple[Path, dict[str, Any]]) -> None:
    root, _ = rendered
    plan = _plan(root)
    video = _decode(root / "out_preview.mp4")
    intro = _decode(root / "build/preview/scenes/intro.mp4")
    card = _decode(root / "build/preview/scenes/card.mp4")
    start = round(plan.scene("card").start * FPS)
    steady = _watermark(video[start + 8])
    assert _drawn(steady, _background(video[start + 8])).sum() > 10  # the watermark is there
    for j in range(6):
        frame = video[start + j]
        # the watermark does not move or double during the push; the progress bar spans the top
        assert np.abs(_watermark(frame) - steady).mean() < 2, j
        assert _drawn(frame[0:1], _background(frame), 15).mean() > 0.95, j
        # neither scene's own frames have overlays there (the clip adds them once, at the join)
        assert not _drawn(_watermark(card[j]), _background(card[j])).any(), j
        assert not _drawn(_watermark(intro[start + j]), _background(intro[start + j])).any(), j
    # the pictures slide: at shared frame j the intro has moved left by (j + 0.5) / 6 of the width
    for j in (1, 3):
        shift = round((j + 0.5) / 6 * W)
        errors = []
        for s in range(shift - 12, shift + 13):
            expected = np.concatenate([intro[start + j][:, s:], card[j][:, :s]], axis=1)
            errors.append(np.abs(video[start + j][8 : int(0.75 * H)] - expected[8 : int(0.75 * H)]).mean())
        assert abs(int(np.argmin(errors)) - 12) <= 3 and min(errors) < 3, (j, errors)


@pytest.mark.render
@pytest.mark.slow
def test_captions_appear_once_through_a_wipe(rendered: tuple[Path, dict[str, Any]]) -> None:
    root, _ = rendered
    plan = _plan(root)
    video = _decode(root / "out_preview.mp4")
    outro = _decode(root / "build/preview/scenes/outro.mp4")
    start = round(plan.scene("outro").start * FPS)
    after = _captions(video[start + 7])  # the outro's caption, drawn by its own render
    assert _drawn(after, _background(video[start + 7])).sum() > 40
    for j in range(6):
        assert np.abs(_captions(video[start + j]) - after).mean() < 3, j  # the same caption, in place
        assert not _drawn(_captions(outro[j]), _background(outro[j])).any(), j  # not in the render


@pytest.mark.render
@pytest.mark.slow
def test_carried_title_is_a_match_cut_then_moves(rendered: tuple[Path, dict[str, Any]]) -> None:
    root, _ = rendered
    plan = _plan(root)
    video = _decode(root / "out_preview.mp4")
    cut = round(plan.scene("more").start * FPS)
    band = slice(int(0.1 * H), int(0.75 * H))  # between the progress bar and the captions
    # the card's last frame shows only its title (number and rule faded); the next scene's
    # first frame shows it in the same place: the cut does not show
    assert np.abs(video[cut][band] - video[cut - 1][band]).mean() < 1.0
    title = _drawn(video[cut - 1][band], _background(video[cut - 1]), 60)
    assert title.sum() > 60
    # then it moves into the heading: at the beat's end the old place is empty
    end = round((plan.scene("more").start + plan.scene("more").beats[0].end) * FPS)
    assert _drawn(video[end][band], _background(video[end]))[title].mean() < 0.1
    # the card's record of it, and the carrying scene's note of which card render it met
    record = read_record(root / "build/preview/carry/card.json")
    assert record is not None and len(record["objects"]["title"]) == 4  # C a r d
    meta = json.loads((root / "build/preview/timings/more.json").read_text(encoding="utf-8"))["render"]
    assert meta["carry_from"] == record["fingerprint"]


@pytest.mark.render
@pytest.mark.slow
def test_render_scene_alone_renders_the_scene_before_when_needed(rendered: tuple[Path, dict[str, Any]], tmp_path: Path) -> None:
    root, _ = rendered
    copy = tmp_path / "proj"
    shutil.copytree(root, copy)
    (copy / "build/preview/carry/card.json").unlink()

    def rendered_ids(*args: str) -> list[str]:
        out = io.StringIO()
        with registry.isolated(), contextlib.redirect_stdout(out):
            assert main(["render", str(copy), "--preview", "--json", *args]) == 0
        runtime.clear_context()
        return [s["id"] for s in json.loads(out.getvalue())["scenes"] if s["status"] == "rendered"]

    assert rendered_ids("--scene", "more") == ["card", "more"]  # no record of the card
    assert rendered_ids("--scene", "more", "--jobs", "2") == ["more"]  # its record is current
