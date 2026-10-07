"""Overlays, Step 38 (DESIGN.md §41): config and validation, the planned timeline, the overlay
registry and schema, drawing fixed to the screen (zoom, fades, cuts, frozen waits), reserved
space, the built-in ``lower_third`` and ``watermark``, and lint."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pytest
import yaml
from manim import Camera, Square, tempconfig
from PIL import Image

from conftest import minimal_config, write_files
from test_json_output import documented, run_json
from vidgen import extensions, registry, schema
from vidgen.activity import MotionTrack
from vidgen.capture import FrameCapture, StillWriter
from vidgen.cli import check_project, project_problems
from vidgen.config import LintRules, OverlayConfig, SceneConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.introspect import LayoutRecorder
from vidgen.lint import RULES, StillContext
from vidgen.overlays import Overlay, avoid, overlay_entries, with_opacity
from vidgen.project import Project
from vidgen.regions import Region, safe_area
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.render.worker import frame_size
from vidgen.videoplan import VideoPlan

ROOT = Path(__file__).resolve().parents[1]
FPS = 10
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
BULLETS = {"heading": "Steps", "items": ["Write the beats", "Pick scene types", "Render it"]}
WORDS = "one two three four five six seven eight"   # 2 s at 4 words per second


def project(make_project, scenes: list[dict[str, Any]], overlays: list[dict[str, Any]], **extra: Any) -> Project:
    root = make_project(minimal_config(scenes=scenes, overlays=overlays, narration=NARRATION, **extra))
    (root / "assets").mkdir(exist_ok=True)
    if (root / "assets" / "logo.png").is_file():
        return Project.load(root)
    pixels = np.zeros((20, 50, 4), dtype=np.uint8)
    pixels[..., 0], pixels[..., 1], pixels[..., 3] = 250, 200, 255
    Image.fromarray(pixels, "RGBA").save(root / "assets" / "logo.png")
    return Project.load(root)


def bullets(sid: str = "s", beats: int = 2, **extra: Any) -> dict[str, Any]:
    return {"id": sid, "type": "bullets", "params": BULLETS, "beats": [{"text": WORDS} for _ in range(beats)], **extra}


def render(project: Project, scene_id: str, media: Path, size: tuple[int, int] = (320, 180), per_beat: int = 0) -> Any:
    """Render one scene in-process, with ``per_beat`` stills per beat (layout in ``scene.layout``)."""
    w, h = size
    fw, fh = frame_size(w, h)
    settings = {
        "pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": FPS,
        "media_dir": str(media), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR",
        "output_file": f"{scene_id}_{w}x{h}_{per_beat}",
    }
    with tempconfig(settings):
        spec = project.scene(scene_id)
        theme = extensions.activate(project)
        writer, recorder = StillWriter(media / f"stills_{scene_id}_{w}x{h}"), LayoutRecorder()
        capture = FrameCapture(per_beat, [writer, recorder], MotionTrack()) if per_beat else None
        scene = registry.get(spec.type).cls(spec, project, theme, capture=capture)
        frames: list[np.ndarray] = []
        writer_out = scene.renderer.file_writer
        write = writer_out.write_frame

        def keep(frame: np.ndarray, num_frames: int = 1) -> None:   # what goes into the video
            frames.extend([np.array(frame)] * num_frames)
            write(frame, num_frames=num_frames)

        writer_out.write_frame = keep
        scene.render()
        scene.frames_seen = frames
        scene.layout = recorder.frames
        scene.layout_doc = recorder.document(scene, per_beat)
        scene.safe_box = scene.safe_area   # with reserved overlays
        scene.frame_safe = safe_area()     # without
        return scene


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


def objects_of(frame: dict[str, Any], overlay: str) -> list[dict[str, Any]]:
    return [o for o in frame["objects"] if o.get("overlay") == overlay]


def union(objects: list[dict[str, Any]]) -> list[float]:
    boxes = np.array([o["bbox"] for o in objects])
    return [float(boxes[:, 0].min()), float(boxes[:, 1].min()), float(boxes[:, 2].max()), float(boxes[:, 3].max())]


# ----- config ----------------------------------------------------------------------------------------


def test_overlay_config_keys_and_options() -> None:
    cfg = OverlayConfig.model_validate({"type": "watermark", "text": "x", "from": 3, "to": "outro", "scenes": ["a"]})
    assert (cfg.type, cfg.from_, cfg.to, cfg.scenes, cfg.options) == ("watermark", 3.0, "outro", ["a"], {"text": "x"})
    assert OverlayConfig.model_validate({"type": "w", "from": "12"}).from_ == "12"   # a quoted number is a scene id
    with pytest.raises(ValueError):
        OverlayConfig.model_validate({"type": "w", "from": -1})
    scene = SceneConfig.model_validate({"id": "a", "type": "t", "duration": 1, "overlays": {"logo": False, "lt": {"name": "x"}}})
    assert scene.overlays == {"logo": False, "lt": {"name": "x"}}
    assert SceneConfig.model_validate({"id": "a", "type": "t", "duration": 1}).overlays is True
    config = parse_config(minimal_config(overlays=[{"type": "watermark", "text": "x"}]))
    assert config.overlays[0].options == {"text": "x"}


def test_default_ids_and_duplicates(make_project) -> None:
    p = project(make_project, [bullets()], [
        {"type": "watermark", "text": "a"},
        {"type": "lower_third", "name": "A"},
        {"type": "lower_third", "name": "B"},
        {"type": "watermark", "id": "lower_third1", "text": "b"},
    ])
    with extensions.project_session(p):
        entries, problems = overlay_entries(p)
    assert [e.id for e in entries] == ["watermark", "lower_third1", "lower_third2", "lower_third1"]
    assert [str(x) for x in problems] == ["overlays[3].id: two overlays are called 'lower_third1'; give them different ids"]


def test_validate_reports_overlay_problems(make_project) -> None:
    scenes = [
        bullets("intro", overlays={"lower_third1": {"type": "watermark"}, "ghost": False, "mine": {"type": "watermark"},
                                   "lower_third2": {"name": "", "scenes": ["intro"]}}),
        {"id": "two", "type": "text_card", "params": {"text": "x"}, "duration": 2, "overlays": {"lower_third1": False}},
    ]
    p = project(make_project, scenes, [
        {"type": "watermak", "text": "x"},
        {"type": "watermark", "image": "assets/nope.png", "scenes": ["intro", "nosuch"]},
        {"type": "lower_third", "name": "Ada", "scene": "two", "colr": "red"},
        {"type": "lower_third", "name": "Bob", "from": 5, "to": 2, "at": "no_beat"},
    ])
    lines = check_project(p)
    expected = [
        "overlays[0].type: unknown overlay type 'watermak'; did you mean 'watermark'?",
        "overlays[1].scenes: unknown scene 'nosuch' (scenes: intro, two)",
        "overlays[3].to: must be after from (2 <= 5 s)",
        "scenes[0].overlays.lower_third1: a scene can override options and reserve of an overlay, not type",
        "scenes[0].overlays.ghost: unknown overlay 'ghost'",
        "scenes[0].overlays.lower_third2: a scene can override options and reserve of an overlay, not scenes",
        "overlays[1].image: file not found: assets/nope.png",
        "overlays[2].colr: unknown option 'colr'; did you mean 'color'?",
        "overlays[3].at: scene 'intro' has no beat 'no_beat' (beats: intro_b1, intro_b2)",
        "scenes[0].overlays.lower_third2.name: String should have at least 1 character",   # the override's own
        "scenes[0].overlays.mine: give exactly one of image, text, icon (got none)",
    ]
    for line in expected:
        assert any(x.startswith(line) for x in lines), (line, lines)
    assert len(lines) == len(expected), lines
    # an override's own problems are reported at the override; a scene the lower third does not draw on
    two = {**scenes[1], "overlays": {"lower_third": False}}
    p2 = project(make_project, [two, bullets("b")], [{"type": "lower_third", "name": "A", "scene": "two"}])
    assert check_project(p2) == ["overlays[0].scene: the overlay is not drawn on scene 'two' (see its scenes / exclude, or the scene's overlays)"]
    p3 = project(make_project, [bullets("a", overlays={"watermark": {"opacity": 2}})], [{"type": "watermark", "text": "x"}])
    assert check_project(p3) == ["scenes[0].overlays.watermark.opacity: Input should be less than or equal to 1"]


def test_render_refuses_invalid_overlays_before_any_worker(make_project) -> None:
    from vidgen.render.pipeline import _check_scenes

    p = project(make_project, [bullets()], [{"type": "watermark"}])
    with extensions.project_session(p), pytest.raises(VidgenError, match="give exactly one of image, text, icon") as err:
        _check_scenes(p)
    assert [x.location for x in err.value.problems] == ["overlays[0]"]


# ----- the planned timeline ------------------------------------------------------------------------


@pytest.mark.render
def test_plan_matches_the_rendered_scenes(make_project, media: Path) -> None:
    scenes = [
        bullets("a"),   # outro 0.5 (bullets)
        {"id": "b", "type": "text_card", "params": {"text": "x"}, "duration": 1.3},
        {"id": "c", "type": "chapter", "params": {"title": "Results", "number": 2}, "duration": 1.5},
        {"id": "d", "type": "text_card", "params": {"text": "y"}, "beats": [{"text": "one two three"}]},
    ]
    p = project(make_project, scenes, [{"type": "watermark", "text": "w"}])
    with extensions.project_session(p):
        plan = VideoPlan(p, FPS)
        slots = plan.scenes
    assert [s.id for s in slots] == ["a", "b", "c", "d"]
    assert [s.chapter for s in slots] == [None, None, "Results", "Results"]
    assert plan.chapters[0].title == "Results" and plan.chapters[0].number == "2" and plan.chapters[0].start == slots[2].start
    beat = slots[0].beats[1]
    assert (beat.id, beat.start, beat.end) == ("a_b2", pytest.approx(2.2), pytest.approx(4.2))
    for slot in slots:
        scene = render(p, slot.id, media)
        assert float(scene.renderer.time) == pytest.approx(slot.duration, abs=1e-6), slot.id
    assert slots[1].start == pytest.approx(slots[0].end) and plan.duration == pytest.approx(slots[-1].end)
    assert plan.resolve("b", end=False) == pytest.approx(slots[1].start) and plan.resolve("b", end=True) == pytest.approx(slots[1].end)
    assert plan.resolve(7, end=True) == 7.0 and plan.resolve(None, end=False) is None


def test_fingerprint_follows_other_scenes_only_with_overlays(make_project) -> None:
    def fingerprints(overlays: list[dict[str, Any]], text: str) -> str:
        p = project(make_project, [bullets("a"), {**bullets("b"), "beats": [{"text": text}]}], overlays)
        with extensions.project_session(p):
            return scene_fingerprint(p, "a")

    assert fingerprints([], "one") == fingerprints([], "one two")
    with_overlays = [{"type": "watermark", "text": "w"}]
    assert fingerprints(with_overlays, "one") != fingerprints(with_overlays, "one two")


# ----- registry, listing, schema --------------------------------------------------------------------


def extending_example() -> str:
    """The overlay type of docs/EXTENDING.md section 9."""
    text = (ROOT / "docs" / "EXTENDING.md").read_text(encoding="utf-8")
    return re.search(r"```python\n# extensions/badge.py\n(.*?)```", text, re.S).group(1)


BADGE = extending_example()


def test_project_overlay_type_is_registered_listed_and_validated(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(overlays=[{"type": "badge", "label": "ON AIR"}], scenes=[bullets()]))
    write_files(root, {"extensions/badge.py": BADGE})
    p = Project.load(root)
    assert check_project(p) == []
    _, doc, _ = run_json(["list-scenes", str(root), "--json"], capsys)
    entries = {o["name"]: o for o in doc["overlays"]}
    assert set(entries) == {"badge", "lower_third", "watermark", "progress_bar", "chapter_indicator", "captions"}
    badge = entries["badge"]
    assert (badge["origin"], badge["builtin"], badge["layer"], badge["lint_skip"]) == (str(Path("extensions") / "badge.py"), False, 0, [])
    assert badge["doc"].startswith('A "LIVE" badge')
    assert [f["name"] for f in badge["options"]] == ["label", "color"] and entries["watermark"]["lint_skip"] == ["contrast"]
    documented("overlays", "layer", "lint_skip")
    bad = project(make_project, [bullets()], [{"type": "badge", "label": 3}])
    write_files(bad.root, {"extensions/badge.py": BADGE})
    assert check_project(Project.load(bad.root)) == ["overlays[0].label: Input should be a valid string"]


@pytest.mark.render
def test_the_extending_example_blinks_in_video_time(make_project, media: Path) -> None:
    root = make_project(minimal_config(overlays=[{"type": "badge", "label": "ON AIR"}], narration=NARRATION,
                                       scenes=[bullets("a", beats=1), bullets("b", beats=1)]))
    write_files(root, {"extensions/badge.py": BADGE})
    p = Project.load(root)
    b = render(p, "b", media)
    layer = b.overlay_layer
    start = layer.offset
    assert start == pytest.approx(2.7)   # a: one 2 s beat + pad 0.2 + bullets' outro 0.5
    shown = [layer.states(k)[0] is not None for k in range(len(b.frames_seen))]
    times = [layer.video_time(k) for k in range(len(shown))]
    assert shown == [int(t + 1e-9) % 2 == 0 for t in times]


def test_overlay_class_checks() -> None:
    from vidgen.overlays import OverlayOptions

    class NoBuild(Overlay):
        pass

    class Reserved(Overlay):
        class Options(OverlayOptions):
            scenes: int = 1

        def build(self):  # type: ignore[no-untyped-def]
            return Square()

    with pytest.raises(VidgenError, match="implement build"):
        registry.register_overlay("nobuild", NoBuild)
    with pytest.raises(VidgenError, match="option names scenes are reserved"):
        registry.register_overlay("reserved", Reserved)
    with pytest.raises(VidgenError, match='use @overlay\\("name"\\)'):
        registry.overlay(NoBuild)  # type: ignore[arg-type]
    assert "watermark" in registry.overlay_names() and registry.find_overlay("nope") is None


@pytest.mark.slow
def test_schema_checks_overlay_types_and_options(make_project) -> None:
    p = project(make_project, [bullets("intro")], [{"type": "watermark", "image": "assets/logo.png"}])
    with extensions.project_session(p) as theme:
        doc = schema.config_schema(registry.all(), schema.project_themes(p, theme))
    raw = yaml.safe_load(p.config_file.read_text(encoding="utf-8"))
    jsonschema.validate(raw, doc)
    for bad in ({"type": "watermark", "image": "x", "bogus": 1}, {"type": "nope"}, {"type": "lower_third", "title": "no name"},
                {"type": "watermark", "text": "x", "corner": "middle"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**raw, "overlays": [bad]}, doc)
    for example in ("minimal", "gallery"):
        config = yaml.safe_load((ROOT / "examples" / example / "video.yaml").read_text(encoding="utf-8"))
        jsonschema.validate(config, doc)


def test_config_md_documents_every_builtin_overlay_option() -> None:
    text = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    with registry.isolated():
        extensions.load_builtins()
        overlays = registry.all_overlays()
    for entry in overlays:
        start = text.index(f"### `{entry.name}`", text.index("## Overlays"))
        section = text[start : text.find("\n### ", start + 1)]
        for name in entry.cls.Options.model_fields:
            assert f"`{name}`" in section, f"{entry.name}.{name} missing from docs/CONFIG.md"


# ----- reserved space ------------------------------------------------------------------------------


def test_avoid_keeps_the_largest_free_part() -> None:
    area = Region(-6, -3.5, 6, 3.5)
    assert avoid(area, Region(-6, -3.5, -1, -2.5), gap=0.2) == Region(-6, -2.3, 6, 3.5)   # a band at the bottom: above it
    assert avoid(area, Region(5, -3, 6.5, 3), gap=0.2) == Region(-6, -3.5, 4.8, 3.5)       # a column at the right: left of it
    assert avoid(area, Region(7, 4, 8, 5)) == area                                          # outside: nothing changes


# ----- drawing ---------------------------------------------------------------------------------------


def test_composite_matches_drawing_over_the_frame() -> None:
    """The cached patch (drawn over black and white) blends like Cairo drawing on the frame."""
    from vidgen.overlay_layer import OverlayLayer

    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_rate": FPS}):
        square = Square(2).set_fill("#FF8800", opacity=0.6).set_stroke("#00FF00", width=6, opacity=0.5)
        frame = np.zeros((90, 160, 4), dtype=np.uint8)
        frame[..., 0], frame[..., 1], frame[..., 2], frame[..., 3] = 30, 60, 200, 255
        frame[:, 80:, :3] = (240, 240, 240)

        class Fake(Overlay):
            def build(self):  # type: ignore[no-untyped-def]
                return square

        layer = OverlayLayer.__new__(OverlayLayer)
        layer.overlays, layer.mobjects, layer._cache, layer._camera = [Fake.__new__(Fake)], [square], {}, None
        layer.following, layer.following_mobjects = [], []
        out = layer.composite(frame, ("on",))
        reference = Camera()
        reference.set_pixel_array(frame.copy())
        reference.capture_mobjects([square])
        assert np.abs(out.astype(int) - reference.pixel_array.astype(int)).max() <= 2
        assert out is not frame and layer.composite(frame, (None,)) is frame


def test_with_opacity_scales_a_copy() -> None:
    square = Square().set_fill("#FFFFFF", opacity=0.8).set_stroke(width=2, opacity=1)
    faded = with_opacity(square, 0.5)
    assert faded.get_fill_opacity() == pytest.approx(0.4) and faded.get_stroke_opacity() == pytest.approx(0.5)
    assert square.get_fill_opacity() == pytest.approx(0.8)


@pytest.mark.render
def test_overlays_stay_on_screen_through_zoom_and_fade(make_project, media: Path) -> None:
    """A watermark is drawn into every frame at the same place while the scene's camera zooms in
    and while the scene fades out; it never joins the scene's mobjects and changes no timing."""
    scene_cfg = bullets("z", beats=1)
    scene_cfg["beats"][0]["actions"] = [{"zoom": "item1", "scale": 2, "at": 0.1}]
    plain = project(make_project, [scene_cfg], [])
    p = project(make_project, [scene_cfg], [{"type": "watermark", "image": "assets/logo.png", "opacity": 1.0}])
    without = render(plain, "z", media, per_beat=8)
    scene = render(p, "z", media, per_beat=8)
    assert float(scene.renderer.time) == float(without.renderer.time) and len(scene.frames_seen) == len(without.frames_seen)
    assert scene.timings() == without.timings()
    assert not any(m in scene.mobjects for m in scene.overlay_layer.mobjects)
    zoomed = [f for f in scene.layout if f["camera"]["zoom"] > 1.5]
    assert zoomed, "no still while zoomed in"
    boxes = {tuple(union(objects_of(f, "watermark"))) for f in scene.layout}
    assert len(boxes) == 1   # the same place in every still, zoomed or not
    x0, y0, x1, y1 = (int(round(v)) for v in boxes.pop())
    assert x1 > 300 and y1 > 165   # bottom right corner
    for frame in (scene.frames_seen[len(scene.frames_seen) // 2], scene.frames_seen[-1]):   # mid-zoom; the last (faded) frame
        patch = frame[y0 + 2 : y1 - 2, x0 + 2 : x1 - 2, :3].reshape(-1, 3)
        assert np.all(np.abs(patch.astype(int) - (250, 200, 0)).max(axis=1) <= 3)
    assert all(f["overlays"] == [{"id": "watermark", "type": "watermark", "settled": True, "skip": ["contrast"]}] for f in scene.layout)


@pytest.mark.render
@pytest.mark.slow
def test_lower_third_slides_in_and_out_within_its_window(make_project, media: Path) -> None:
    overlays = [{"type": "lower_third", "name": "Ada Lovelace", "title": "Mathematician", "at": "s_b1", "duration": 1.5, "enter": 0.5, "exit": 0.5}]
    p = project(make_project, [bullets("s", beats=2)], overlays)
    scene = render(p, "s", media, per_beat=0)
    layer = scene.overlay_layer
    (start, end), = [o.interval() for o in layer.overlays]
    assert (start, end) == (pytest.approx(0.0), pytest.approx(1.5))
    states = [layer.states(k)[0] for k in range(int(2.5 * FPS))]
    assert states[0] is None and states[5] == 1.0 and states[2] is not None and 0 < states[2] < 1 and states[15] is None
    assert states.index(1.0) == 5 and max(k for k, s in enumerate(states) if s is not None) == 14
    full = layer.posed(8)[0][1]
    half = layer.posed(2)[0][1]
    assert half.get_center()[0] < full.get_center()[0]   # bottom left: it slides in from the left
    # drawn: frames inside the window differ from the plain render there, frames after it do not
    plain = render(project(make_project, [bullets("s", beats=2)], []), "s", media)
    assert np.any(scene.frames_seen[8] != plain.frames_seen[8]) and np.array_equal(scene.frames_seen[20], plain.frames_seen[20])


@pytest.mark.render
@pytest.mark.slow
def test_lower_third_runs_on_across_a_cut_and_joins_seamlessly(make_project, media: Path) -> None:
    overlays = [{"type": "lower_third", "name": "Across", "scene": "a", "at": 3.0, "duration": 3.0, "across_cuts": True}]
    p = project(make_project, [bullets("a", beats=2), bullets("b", beats=2)], overlays)
    a = render(p, "a", media)
    b = render(p, "b", media)
    (la,), (lb,) = a.overlay_layer.overlays, b.overlay_layer.overlays
    assert la.interval() == lb.interval()
    last_a, first_b = a.overlay_layer.written - 1, 0
    ta, tb = a.overlay_layer.video_time(last_a), b.overlay_layer.video_time(first_b)
    assert tb == pytest.approx(ta + 1 / FPS)   # b's first frame follows a's last in the video
    assert a.overlay_layer.states(last_a) == b.overlay_layer.states(first_b) == (1.0,)
    box_a = a.overlay_layer.posed(last_a)[0][1].get_center()
    box_b = b.overlay_layer.posed(first_b)[0][1].get_center()
    assert np.allclose(box_a, box_b)
    # without across_cuts it is gone by the end of its scene, and scene b has no overlay at all
    q = project(make_project, [bullets("a", beats=2), bullets("b", beats=2)], [{**overlays[0], "across_cuts": False}])
    assert render(q, "b", media).overlay_layer is None
    qa = render(q, "a", media).overlay_layer
    assert qa.overlays[0].interval()[1] == pytest.approx(qa.overlays[0].context.scene.end)


@pytest.mark.render
def test_frozen_waits_are_split_where_overlays_change(make_project, media: Path) -> None:
    """A silent card is one long frozen wait; a lower third entering in the middle of it is still
    drawn frame by frame (its slide), and the scene's length does not change."""
    card = {"id": "c", "type": "text_card", "params": {"text": "Hold"}, "duration": 3}
    p = project(make_project, [card], [{"type": "lower_third", "name": "Ada", "at": 1.0, "duration": 1.5}])
    scene = render(p, "c", media)
    frames = scene.frames_seen
    assert len(frames) == 3 * FPS
    changed = [k for k in range(9, len(frames)) if not np.array_equal(frames[k], frames[k - 1])]   # after the card's fade-in
    assert changed[0] in (10, 11) and changed[-1] in (24, 25) and len(changed) >= 8   # in from 1.0 s, out by 2.5 s


@pytest.mark.render
def test_reserve_shrinks_the_safe_area_and_the_layout_dump(make_project, media: Path) -> None:
    overlays = [{"type": "lower_third", "name": "A long name that needs room", "reserve": True, "duration": 30}]
    p = project(make_project, [bullets("s", beats=1)], overlays)
    scene = render(p, "s", media, per_beat=1)
    box = scene._reserved[0]
    assert scene.layout_doc["safe_area"][1] == pytest.approx((scene.frame_height / 2 - scene.safe_box.y1) * 180 / 8, abs=0.1)
    assert scene.safe_box.y0 == pytest.approx(box.y1 + 0.2) and scene.safe_box.y1 == scene.frame_safe.y1
    assert scene.layout_doc["safe_area"][3] < 180 - 0.5 / 8 * 180   # its bottom is above the lower third
    texts = [o for o in scene.layout[-1]["objects"] if o["kind"] == "text" and not o.get("overlay")]
    lower = union(objects_of(scene.layout[-1], "lower_third"))
    assert all(t["bbox"][3] <= lower[1] for t in texts)   # the bullets stay above it


@pytest.mark.render
@pytest.mark.parametrize("size", [(320, 180), (180, 320)])
def test_lower_third_and_watermark_placement(size: tuple[int, int], make_project, media: Path) -> None:
    overlays = [
        {"type": "lower_third", "name": "Ada Lovelace", "title": "Mathematician and writer", "icon": "user", "duration": 30},
        {"type": "watermark", "text": "vidgen", "corner": "top_right"},
    ]
    p = project(make_project, [bullets("s", beats=1)], overlays)
    scene = render(p, "s", media, size=size, per_beat=1)
    frame = scene.layout[-1]
    w, h = size
    lower = union(objects_of(frame, "lower_third"))
    fw, fh = frame_size(w, h)
    sx, sy = w / fw, h / fh
    safe = scene.safe_box
    left, bottom = (safe.x0 + fw / 2) * sx, (fh / 2 - safe.y0) * sy
    assert lower[0] == pytest.approx(left, abs=1.5)
    if w > h:
        assert lower[3] == pytest.approx(bottom, abs=1.5)
    else:   # raised in 9:16
        assert lower[3] == pytest.approx(bottom - 0.12 * safe.height * sy, abs=1.5)
    mark = union(objects_of(frame, "watermark"))
    assert mark[2] > w * 0.9 and mark[1] < h * 0.1
    texts = {o["text"] for o in frame["objects"] if o.get("overlay") and o["kind"] == "text"}
    assert {"Ada Lovelace", "Mathematician and writer", "vidgen"} <= texts


# ----- lint ------------------------------------------------------------------------------------------


def still(objects: list[dict[str, Any]], overlays: list[dict[str, Any]] = ()) -> StillContext:
    layout = {"width": 320, "height": 180, "safe_area": [20, 10, 300, 170], "background": "#000000"}
    return StillContext(layout, {"camera": {"zoom": 1.0}, "overlays": list(overlays)}, objects)


def obj(oid: str, kind: str, bbox: list[float], order: int, overlay: str | None = None, **extra: Any) -> dict[str, Any]:
    out = {"id": oid, "kind": kind, "class": "Text", "path": f"P[{order}]", "name": None, "bbox": bbox, "opacity": 1.0,
           "z": 0.0, "order": order, "parts": 3, "text": oid, "font_px": 10, "color": "#FFFFFF", "colors": ["#FFFFFF"],
           "backdrop": "#000000", "fill": {"color": "#222222", "opacity": 1.0}, "stroke": None, **extra}
    if overlay:
        out["overlay"] = overlay
        out["path"] = f"overlay:{overlay}/{out['path']}"
    return out


def test_lint_rules_leave_overlays_to_overlay_overlap() -> None:
    rules = LintRules()
    scene_text = obj("Scene text", "text", [20, 150, 120, 165], 1)
    plate = obj("plate", "shape", [10, 140, 160, 175], 10, overlay="lower_third")
    name = obj("Ada", "text", [30, 150, 100, 165], 11, overlay="lower_third")
    mark = obj("logo", "text", [300, 2, 318, 8], 12, overlay="watermark")
    ctx = still([scene_text, plate, name, mark])
    found = list(RULES["overlay_overlap"].check(ctx, rules.overlay_overlap))
    assert len(found) == 1 and found[0].objects[0]["id"] == "Scene text" and "overlay 'lower_third' covers text 'Scene text'" in found[0].message
    assert list(RULES["text_overlap"].check(ctx, rules.text_overlap)) == []
    assert list(RULES["safe_area"].check(ctx, rules.safe_area)) == []    # the watermark sits in the margin on purpose
    two = still([name, obj("Other", "text", [40, 152, 110, 163], 13, overlay="watermark")])
    assert len(list(RULES["text_overlap"].check(two, rules.text_overlap))) == 1   # two overlays still may not overlap


@pytest.mark.render
@pytest.mark.slow
def test_lint_reports_a_lower_third_over_text_and_skips_watermark_contrast(make_project) -> None:
    from vidgen.lint import lint_project

    overlays = [
        {"type": "lower_third", "name": "Covering the heading", "align": "top", "duration": 60},
        {"type": "watermark", "text": "faint", "color": "#20242C"},   # 1.2:1 on the background
    ]
    p = project(make_project, [bullets("s", beats=1)], overlays, preview={"width": 320, "height": 180, "fps": FPS})
    result = lint_project(p, rules=[name for name, entry in RULES.items() if entry.scope == "still"])
    rules = sorted({f.rule for f in result.findings})
    assert rules == ["overlay_overlap"], [f.message for f in result.findings]
    layout = json.loads((p.render_dir(True) / "layout" / "s.json").read_text(encoding="utf-8"))
    assert {o["overlay"] for o in layout["frames"][-1]["objects"] if o.get("overlay")} == {"lower_third", "watermark"}
    assert all(re.match(r"overlay:(lower_third|watermark)/", o["path"]) for o in layout["frames"][-1]["objects"] if o.get("overlay"))


def test_problem_locations_point_at_the_entry(make_project) -> None:
    p = project(make_project, [bullets()], [{"type": "watermark", "text": "x", "opacity": 0}])
    assert [x.location for x in project_problems(p)] == ["overlays[0].opacity"]


def test_list_scenes_prints_the_overlay_types(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from vidgen.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["list-scenes"]) == 0
    out = capsys.readouterr().out
    section = out[out.index("overlays (video `overlays:`"):]
    assert re.search(r"\nlower_third +builtin\n", section) and re.search(r"\nwatermark +builtin  \(lint skips: contrast\)", section)
    assert "    corner: 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right' = 'bottom_right'" in section


def test_join_warns_when_a_scene_does_not_start_where_planned(make_project, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A scene that ran longer than planned shifts the next one; its timed overlays are off."""
    from vidgen.render import pipeline
    from vidgen.render.ffmpeg import VideoInfo

    p = project(make_project, [bullets("a", beats=1), bullets("b", beats=1)], [{"type": "lower_third", "name": "x", "scene": "b"}])
    plan_start = 2.7
    lengths = {"a": 3.2, "b": 2.7}   # a ran 0.5 s longer than its plan
    for sid, length in lengths.items():
        video = pipeline.scene_video_path(p, False, sid)
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"")
        drawn = {"ids": ["lower_third"], "timed": True, "start": 0.0 if sid == "a" else plan_start, "duration": 2.7}
        pipeline.write_json(pipeline.scene_timings_path(p, False, sid), {"scene": sid, "duration": length, "beats": [], "render": {"overlays": drawn}})
    monkeypatch.setattr(pipeline.ff, "probe", lambda path: VideoInfo(320, 180, 30, lengths[path.stem]))
    monkeypatch.setattr(pipeline.ff, "pad_audio", lambda *args: None)
    monkeypatch.setattr(pipeline.ff, "join", lambda *args, **kwargs: None)
    with caplog.at_level("WARNING", logger="vidgen.render"):
        pipeline.join_scenes(p, False, True, "ffmpeg")
    assert "overlays timed in the video are off" in caplog.text and "'b' starts at 3.20 s, planned 2.70 s" in caplog.text
