"""Layout introspection (`build/.../layout/<scene>.json`): objects, boxes, sizes, colours, files.

Unit tests measure hand-built mobjects with a real Manim camera at 160x90 (px_per_unit 11.25);
rendering tests use 160x90 @ 10 fps.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from manim import (
    BLUE,
    WHITE,
    Camera,
    Circle,
    Code,
    ImageMobject,
    Line,
    MarkupText,
    MovingCamera,
    Paragraph,
    Square,
    Text,
    VGroup,
    tempconfig,
)
from PIL import Image

from test_render import make_tone, write_project
from vidgen.capture import CapturedFrame, still_name
from vidgen.introspect import LAYOUT_VERSION, LayoutRecorder, _backdrop
from vidgen.layout import latex_available
from vidgen.project import Project
from vidgen.render import worker
from vidgen.render.pipeline import _usable_render, render_project

W, H = 160, 90
PX = W / (8 * 16 / 9)  # pixels per Manim unit at 160x90
BG = (14, 17, 22)


@pytest.fixture
def small_config(tmp_path: Path) -> Iterator[None]:
    settings = {
        "pixel_width": W,
        "pixel_height": H,
        "frame_width": 8 * W / H,
        "frame_height": 8.0,
        "background_color": "#0E1116",
        "media_dir": str(tmp_path / "media"),
        "verbosity": "ERROR",
    }
    with tempconfig(settings):
        yield


class FakeScene:
    """What the recorder reads from a scene: camera, mobjects, attributes, margins, spec."""

    margin_x = 0.6
    margin_y = 0.5

    def __init__(self, *mobjects: Any, camera: Camera | None = None) -> None:
        self.camera = camera or Camera()
        self.mobjects = list(mobjects)
        self.spec = SimpleNamespace(id="sc", type="fake")


def frame_pixels() -> np.ndarray:
    pixels = np.zeros((H, W, 4), dtype=np.uint8)
    pixels[:, :, :3] = BG
    pixels[:, :, 3] = 255
    return pixels


def objects(scene: FakeScene, pixels: np.ndarray | None = None) -> list[dict[str, Any]]:
    return LayoutRecorder().objects(scene, frame_pixels() if pixels is None else pixels)  # type: ignore[arg-type]


def expected_box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    """Manim units (y up, origin at the centre) -> output pixels (y down, origin top-left)."""
    return [W / 2 + x0 * PX, H / 2 - y1 * PX, W / 2 + x1 * PX, H / 2 - y0 * PX]


# ----- objects -------------------------------------------------------------------------------------


def test_shape_box_colours_and_stroke(small_config: None) -> None:
    square = Square(side_length=2).set_fill(BLUE, opacity=0.5).set_stroke(WHITE, width=8, opacity=0.7).shift([1, 1, 0])
    [item] = objects(FakeScene(square))
    half = 8 * 0.01 * PX / 2  # Manim's stroke width: width * 0.01 units
    want = expected_box(0, 0, 2, 2)
    assert item["bbox"] == pytest.approx([want[0] - half, want[1] - half, want[2] + half, want[3] + half], abs=0.06)
    assert (item["kind"], item["class"], item["path"], item["name"], item["parts"]) == ("shape", "Square", "Square[0]", None, 1)
    assert item["fill"] == {"color": "#58C4DD", "opacity": 0.5}
    assert item["stroke"] == {"color": "#FFFFFF", "opacity": 0.7, "width_px": pytest.approx(8 * 0.01 * PX, abs=0.01)}
    assert item["opacity"] == 0.7 and item["z"] == 0 and item["order"] == 0


def test_curves_are_sampled_not_their_handles(small_config: None) -> None:
    circle = Circle(radius=2).set_stroke(width=0).set_fill(WHITE, 1)
    [item] = objects(FakeScene(circle))
    assert item["bbox"] == pytest.approx(expected_box(-2, -2, 2, 2), abs=0.1)


def test_invisible_parts_and_objects_are_left_out(small_config: None) -> None:
    hidden = Square().set_opacity(0)
    fading = Square().set_fill(WHITE, 0.3).set_stroke(width=0).shift([-3, 0, 0])
    group = VGroup(Square(side_length=1).shift([3, 0, 0]), Square(side_length=4).set_opacity(0))
    items = objects(FakeScene(hidden, fading, group))
    assert [i["path"] for i in items] == ["Square[1]", "VGroup[2]"]
    assert items[0]["opacity"] == 0.3
    assert items[1]["kind"] == "group" and items[1]["parts"] == 1  # the transparent big square does not count
    half = 4 * 0.01 * PX / 2  # Square's default stroke
    assert items[1]["bbox"] == pytest.approx(expected_box(2.5, -0.5, 3.5, 0.5), abs=half + 0.06)


def test_text_is_one_object_with_size_colour_and_backdrop(small_config: None) -> None:
    text = Text("Hello World", font_size=48, t2c={"World": "#FF0000"}).set_z_index(3)
    plate = Square(side_length=6).set_fill("#203040", 1).set_stroke(width=0)
    scene = FakeScene(VGroup(plate, text))
    pixels = frame_pixels()
    pixels[10:80, 45:115, :3] = (32, 48, 64)  # the plate, as the camera would have drawn it
    pixels[40:50, 60:100, :3] = 255  # some "ink"
    plate_item, item = objects(scene, pixels)
    assert (plate_item["kind"], plate_item["path"]) == ("shape", "VGroup[0]/Square[0]")
    assert (item["kind"], item["class"], item["path"], item["text"]) == ("text", "Text", "VGroup[0]/Text[1]", "Hello World")
    assert item["parts"] == 10  # one per glyph, the space has none
    assert item["color"] == "#FF0000" or item["color"] == "#FFFFFF"
    assert set(item["colors"]) == {"#FFFFFF", "#FF0000"}
    assert item["backdrop"] == "#203040"
    assert item["z"] == 3 and item["order"] > plate_item["order"]
    heights = [glyph.height * PX for glyph in text]
    assert item["font_px"] == pytest.approx(np.percentile(heights, 75), abs=0.06)
    assert text[0].height * PX <= item["font_px"] <= max(heights)  # between the cap height ("H") and the tallest
    left, top, right, bottom = expected_box(*text.get_corner([-1, -1, 0])[:2], *text.get_corner([1, 1, 0])[:2])
    assert item["bbox"] == pytest.approx([left, top, right, bottom], abs=0.3)


def test_text_kinds_and_contents(small_config: None) -> None:
    markup = MarkupText("<b>Bold</b> &amp; plain")
    para = Paragraph("first line", "second")
    code = Code(code_string="x = 1\ny = 2\n", language="python")
    items = objects(FakeScene(markup, para, code))
    texts = [(i["kind"], i["class"], i["text"]) for i in items if "text" in i]
    assert texts[:2] == [("text", "MarkupText", "Bold & plain"), ("text", "Paragraph", "first line\nsecond")]
    assert ("code", "Paragraph", "x = 1\ny = 2") in texts  # Manim's invisible alignment glyphs removed
    assert ("code", "Paragraph", "1\n2") in texts  # line numbers
    assert any(i["path"].startswith("Code[2]/") and i["kind"] in ("shape", "group") for i in items)  # the background


@pytest.mark.skipif(not latex_available(), reason="needs LaTeX")
@pytest.mark.slow
def test_math_and_numbers(small_config: None) -> None:
    from manim import DecimalNumber, MathTex

    items = objects(FakeScene(MathTex("a^2", "+b"), DecimalNumber(3.14159, num_decimal_places=2).shift([0, 2, 0])))
    assert [(i["kind"], i["text"]) for i in items] == [("math", "a^2 +b"), ("number", "3.14")]
    assert all(i["font_px"] > 0 for i in items)


def test_names_and_paths(small_config: None) -> None:
    title = Text("Hi")
    marked = Square()
    marked.name = "plate"
    lines = VGroup(*[Line([0, i * 0.2, 0], [1, i * 0.2, 0]) for i in range(5)])
    scene = FakeScene(VGroup(VGroup(title, marked), lines))
    scene.title = title  # a scene attribute names the mobject
    by_path = {i["path"]: i for i in objects(scene)}
    assert set(by_path) == {"VGroup[0]/VGroup[0]/title", "VGroup[0]/VGroup[0]/plate", "VGroup[0]/VGroup[1]"}
    assert by_path["VGroup[0]/VGroup[0]/title"]["name"] == "title"
    assert by_path["VGroup[0]/VGroup[0]/plate"]["name"] == "plate"
    assert by_path["VGroup[0]/VGroup[1]"]["parts"] == 5  # shapes only: one group object


def test_ids_are_stable_across_frames(small_config: None) -> None:
    a, b = Square(), Square().shift([2, 0, 0])
    recorder = LayoutRecorder()
    first = recorder.objects(FakeScene(a, b), frame_pixels())  # type: ignore[arg-type]
    second = recorder.objects(FakeScene(b, Square(), a), frame_pixels())  # type: ignore[arg-type]
    assert [i["id"] for i in first] == ["m1", "m2"]
    assert [i["id"] for i in second] == ["m2", "m3", "m1"]


def test_image(small_config: None) -> None:
    array = np.full((20, 40, 4), 255, dtype=np.uint8)
    image = ImageMobject(array).scale_to_fit_height(2)
    image.set_opacity(0.5)
    [item] = objects(FakeScene(image))
    assert (item["kind"], item["fill"], item["stroke"]) == ("image", None, None)
    assert item["opacity"] == pytest.approx(0.5, abs=0.01)
    assert item["bbox"] == pytest.approx(expected_box(-2, -1, 2, 1), abs=0.1)


def test_moving_camera_zoom(small_config: None) -> None:
    camera = MovingCamera()
    camera.frame.scale(0.5).move_to([1, 0, 0])  # 2x zoom on x = 1
    text = Text("Zoom")
    [square, label] = objects(FakeScene(Square(side_length=2, stroke_width=0, fill_opacity=1), text, camera=camera))
    zoom = 2 * PX
    assert square["bbox"] == pytest.approx([W / 2 - 2 * zoom, H / 2 - zoom, W / 2, H / 2 + zoom], abs=0.2)
    assert label["font_px"] == pytest.approx(np.percentile([g.height * zoom for g in text], 75), abs=0.06)


def test_backdrop() -> None:
    pixels = frame_pixels()
    assert _backdrop(pixels, [-50, -50, -1, -1], ["#FFFFFF"]) is None  # entirely off-frame
    pixels[:, :100, :3] = 255  # mostly text-coloured box: the rest is the backdrop
    assert _backdrop(pixels, [0, 0, 120, 90], ["#FFFFFF"]) == "#0E1116"
    assert _backdrop(pixels, [0, 0, 50, 90], ["#FFFFFF"]) == "#FFFFFF"  # text on its own colour


def test_document_header(small_config: None) -> None:
    recorder = LayoutRecorder()
    scene = FakeScene(Square())
    pixels = frame_pixels()
    recorder(scene, CapturedFrame("sc", "b2", 1, 1, 7, 0.7, pixels))  # type: ignore[arg-type]
    recorder(scene, CapturedFrame("sc", "b1", 1, 1, 3, 0.3, pixels))  # type: ignore[arg-type]
    doc = recorder.document(scene, 1)  # type: ignore[arg-type]
    assert doc["version"] == LAYOUT_VERSION and (doc["scene"], doc["type"]) == ("sc", "fake")
    assert (doc["width"], doc["height"], doc["background"]) == (W, H, "#0E1116")
    assert doc["px_per_unit"] == pytest.approx(PX, abs=1e-3)
    assert doc["safe_area"] == pytest.approx([0.6 * PX, 0.5 * PX, W - 0.6 * PX, H - 0.5 * PX], abs=0.06)
    assert [(f["beat"], f["frame"], f["still"]) for f in doc["frames"]] == [
        ("b1", 3, "../frames/sc/b1-1.png"), ("b2", 7, "../frames/sc/b2-1.png")]
    assert doc["frames"][0]["camera"] == {"center": [0.0, 0.0], "width": pytest.approx(8 * W / H, abs=1e-3), "height": 8.0, "zoom": 1.0}


def test_still_name() -> None:
    pixels = np.zeros((1, 1, 4), dtype=np.uint8)
    assert still_name(CapturedFrame("sc", "b1", 2, 3, 0, 0.0, pixels)) == "b1-2.png"
    assert still_name(CapturedFrame("sc", None, 1, 1, 0, 0.0, pixels)) == "sc-1.png"


# ----- rendering -------------------------------------------------------------------------------------

LAYOUT_EXT = """
from vidgen.api import *

@scene("boxes")
class Boxes(NarratedScene):
    def construct(self):
        self.plate = Square(side_length=3, fill_color=WHITE, fill_opacity=1, stroke_width=0).shift(LEFT * 3)
        self.add(self.plate)
        with self.narrate(0) as d:
            self.play(FadeIn(Square(side_length=2, color=WHITE, fill_opacity=1).shift(RIGHT * 3)), run_time=d)
        with self.narrate(1) as d:
            self.play(Write(self.text("Words", size=40)), run_time=d / 2)

@scene("zoomed")
class Zoomed(NarratedScene):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, camera_class=MovingCamera, **kwargs)

    def construct(self):
        self.add(Square(side_length=2, color=WHITE, fill_opacity=1, stroke_width=0))
        with self.narrate(0) as d:
            self.play(self.camera.frame.animate.scale(0.5), run_time=d)
"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ink_box(still: Path) -> tuple[int, int, int, int]:
    """Pixel extents (x0, y0, x1, y1 exclusive) of the bright pixels of a still."""
    with Image.open(still) as image:
        bright = np.asarray(image.convert("L")) > 128
    ys, xs = np.nonzero(bright)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


@pytest.fixture
def layout_project(tmp_path: Path) -> Path:
    scenes = [
        {"id": "b", "type": "boxes", "beats": [{"text": "One."}, {"text": "Two."}]},
        {"id": "z", "type": "zoomed", "beats": [{"text": "Zoom in."}]},
    ]
    root = write_project(tmp_path / "proj", {"scenes": scenes}, {"extensions/layout_ext.py": LAYOUT_EXT})
    make_tone(root / "audio" / "b_b1.mp3", 1.0)
    return root


def render(root: Path, **kwargs: Any):
    from vidgen import hooks, registry, runtime

    with registry.isolated(), hooks.isolated():
        result = render_project(Project.load(root), **kwargs)
    runtime.clear_context()
    return result


@pytest.mark.render
@pytest.mark.slow
def test_layout_matches_the_stills(layout_project: Path) -> None:
    root = layout_project
    build = root / "build" / "final"
    result = render(root, frames=2)
    layout = read_json(build / "layout" / "b.json")
    stills = read_json(build / "frames" / "b" / "index.json")
    assert (layout["scene"], layout["type"], layout["per_beat"], layout["width"], layout["height"]) == ("b", "boxes", 2, W, H)
    assert layout["background"] == "#203040"
    # keyed by the same frames as the stills index
    keys = [(f["beat"], f["k"], f["n"], f["frame"], f["time"]) for f in layout["frames"]]
    assert keys == [(s["beat"], s["k"], s["n"], s["frame"], s["time"]) for s in stills["frames"]]
    assert all((build / "layout" / f["still"]).is_file() for f in layout["frames"])

    first, end1, _, end2 = layout["frames"]
    plate = next(o for o in end1["objects"] if o["name"] == "plate")
    assert plate["path"] == "plate" and plate["fill"] == {"color": "#FFFFFF", "opacity": 1.0}
    # mid-fade: the square is partly transparent; at the beat's end it is opaque
    fading = [o for o in first["objects"] if o["name"] is None]
    assert len(fading) == 1 and 0 < fading[0]["opacity"] < 1
    assert [o["opacity"] for o in end1["objects"]] == [1.0, 1.0]
    # boxes agree with the pixels of the stills (the plate and the square are the only bright things)
    x0, y0, x1, y1 = ink_box(build / "layout" / end1["still"])
    boxes = [o["bbox"] for o in end1["objects"]]
    assert min(b[0] for b in boxes) == pytest.approx(x0, abs=1) and max(b[2] for b in boxes) == pytest.approx(x1, abs=1)
    assert min(b[1] for b in boxes) == pytest.approx(y0, abs=1) and max(b[3] for b in boxes) == pytest.approx(y1, abs=1)
    words = next(o for o in end2["objects"] if o["kind"] == "text")
    assert words["text"] == "Words" and words["font_px"] > 3 and words["backdrop"] == "#203040"

    zoomed = read_json(build / "layout" / "z.json")["frames"][-1]
    assert zoomed["camera"]["width"] == pytest.approx(8 * W / H / 2, abs=0.01) and zoomed["camera"]["zoom"] == pytest.approx(2.0)
    [square] = zoomed["objects"]
    assert square["bbox"] == pytest.approx([W / 2 - 2 * PX, H / 2 - 2 * PX, W / 2 + 2 * PX, H / 2 + 2 * PX], abs=0.5)
    sx0, sy0, sx1, sy1 = ink_box(build / "layout" / zoomed["still"])
    assert square["bbox"] == pytest.approx([sx0, sy0, sx1, sy1], abs=1)

    combined = read_json(result.frames_index)
    assert [s["layout"] for s in combined["scenes"]] == ["../layout/b.json", "../layout/z.json"]
    assert [s["activity"] for s in combined["scenes"]] == ["../activity/b.json", "../activity/z.json"]
    project = Project.load(root)
    assert _usable_render(project, False, "b", False, frames=2)
    worker.scene_activity_path(project, False, "b").rename(build / "activity.json")  # nor without activity
    assert not _usable_render(project, False, "b", False, frames=2)
    (build / "activity.json").rename(worker.scene_activity_path(project, False, "b"))
    (build / "layout" / "b.json").unlink()  # stills without their layout must be rendered again
    assert not _usable_render(project, False, "b", False, frames=2)

    # rendering without frames removes the scene's layout with its stills
    render(root, scenes=["z"])
    assert not worker.scene_layout_path(project, False, "z").exists()
    assert not worker.scene_activity_path(project, False, "z").exists()


def test_rotated_text_is_measured_across_its_line(small_config: None) -> None:
    level = Text("Render time", font_size=40)
    turned = Text("Render time", font_size=40).rotate(np.pi / 2).shift([3, 0, 0])
    tilted = Text("Render time", font_size=40).rotate(np.radians(30)).shift([-3, 0, 0])
    stacked = Text("a\nb\nc", font_size=40).shift([0, 2.5, 0])
    tilted_item, flat, lines, up = sorted(objects(FakeScene(level, turned, tilted, stacked)), key=lambda i: (i["bbox"][0] + i["bbox"][2], i["text"]))
    assert lines["text"].startswith("a") and lines["rotation"] == 0.0 and flat["rotation"] == 0.0
    assert abs(up["rotation"]) == pytest.approx(90.0, abs=1.0) and tilted_item["rotation"] == pytest.approx(30.0, abs=2.0)
    assert up["font_px"] == pytest.approx(flat["font_px"], rel=0.05)
    assert tilted_item["font_px"] == pytest.approx(flat["font_px"], rel=0.1)
