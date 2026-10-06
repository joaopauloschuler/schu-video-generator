"""Per-beat actions, Step 24 (DESIGN.md §27): targets of every built-in scene type (kept in sync
with the table in docs/CONFIG.md), ``zoom`` (camera in and back), ``transform``, dimming that
never compounds, highlights that undim, images, the bar outline, and the lint of zoomed stills."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from PIL import Image

from conftest import minimal_config, write_files
from test_actions import BARS, BULLETS, alpha, beat_total, beats, color_of, plays, project_with, render, rgb
from test_json_output import documented
from vidgen import actions, extensions, registry, schema
from vidgen.cli import check_project, main, project_problems
from vidgen.errors import VidgenError
from vidgen.lint import RULES, StillContext
from vidgen.config import LintRules
from vidgen.project import Project
from vidgen.theme import Theme

ROOT = Path(__file__).resolve().parents[1]
FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}

#: Params for every built-in scene type that give it every kind of target.
SAMPLES: dict[str, dict[str, Any]] = {
    "title": {"kicker": "K", "title": "A title", "subtitle": "Sub", "authors": ["Me"], "icon": "rocket"},
    "text_card": {"text": "Hello"},
    "bullets": BULLETS,
    "icon_grid": {"heading": "Grid", "items": [{"icon": "cpu", "label": "One"}, {"icon": "rocket", "label": "Two"}]},
    "bar_chart": BARS,
    "line_chart": {"title": "Loss", "x": [1, 2, 3], "series": {"a": [3, 2, 1], "b": [2, 2.5, 1]}},
    "image": {"path": "assets/pic.png", "caption": "A picture"},
    "quote": {"text": "Simple.", "author": "D", "source": "1975"},
    "equation": {"latex": ["(a+b)^2", "a^2 + 2ab + b^2"], "terms": ["2ab"], "caption": "c"},
    "code": {"code": "a = 1\nb = 2\nc = 3", "title": "T"},
    "code_walkthrough": {"code": "a = 1\nb = 2\nc = 3", "title": "T", "steps": [{"lines": 1}, {"lines": "2-3", "note": "n"}]},
    "end_card": {"title": "Thanks", "lines": ["one", "two"], "icon": "rocket", "logo": "assets/pic.png"},
    "chapter": {"number": 2, "title": "Results", "subtitle": "Sub", "icon": "rocket"},
    "stat": {"value": 42, "suffix": "%", "label": "L", "context": "C", "comparison": 30, "icon": "rocket"},
    "comparison": {"heading": "H", "columns": [{"heading": "A", "points": ["x", "y"]}, {"heading": "B", "points": ["z"]}]},
    "table": {"title": "T", "header": ["Name", "N"], "rows": [["a", 1], ["b", 2]], "caption": "C"},
    "timeline": {"heading": "H", "events": [{"date": 1969, "title": "Moon"}, {"date": "1981", "title": "Shuttle", "icon": "rocket"}]},
    "diagram": {"heading": "H", "nodes": ["a", {"id": "b", "icon": "rocket"}], "edges": ["a -> b: go"]},
    "process": {"heading": "H", "stages": ["a", {"label": "b", "icon": "rocket"}], "input": "in"},
    "network": {"heading": "H", "layers": [2, {"size": 2, "label": "Out"}], "passes": 0},
    "scatter": {"title": "T", "series": {"a": [[1, 2, "p"], [2, 3]], "b": [[1, 1], [3, 2]]}, "trend": "each"},
    "histogram": {"title": "T", "counts": [1, 3, 2], "edges": [0, 10, 20, 30], "compare": {"counts": [2, 2, 1]}, "mean": True, "median": True},
    "pie": {"title": "T", "labels": ["a", "b"], "values": [3, 1], "donut": True, "legend": True},
    "heatmap": {"title": "T", "rows": ["a", "b"], "columns": ["x", "y"], "values": [[1, 2], [3, 4]]},
}
#: Built-in types registered under a second name (same class, params and targets).
ALIASES = {"flowchart": "diagram"}


def with_picture(root: Path) -> Path:
    """Put a small opaque PNG at ``assets/pic.png``."""
    (root / "assets").mkdir(exist_ok=True)
    pixels = np.zeros((30, 40, 4), dtype=np.uint8)
    pixels[..., 0], pixels[..., 1], pixels[..., 2], pixels[..., 3] = 40, 120, 200, 255
    Image.fromarray(pixels, "RGBA").save(root / "assets" / "pic.png")
    return root


def load(make_project, scenes: list[dict[str, Any]]) -> Project:
    return Project.load(with_picture(make_project(minimal_config(scenes=scenes, narration=NARRATION))))


def camera_moves(scene: Any, beat: str) -> list[Any]:
    return [p for p in scene.play_log if p.beat == beat and "MoveCamera" in p.animations]


def beat_end(scene: Any, beat: str) -> float:
    timing = next(t for t in scene.beat_log if t.beat_id == beat)
    return timing.end + scene.pad


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- the targets table ------------------------------------------------------------------------


def targets_table() -> dict[str, tuple[list[str], list[str]]]:
    """``{scene type: (targets, useful actions)}`` from docs/CONFIG.md "Beat actions"."""
    text = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    table = text[text.index("<!-- targets-table") :].split("\n\n")[0]
    rows: dict[str, tuple[list[str], list[str]]] = {}
    for line in table.splitlines()[3:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows[cells[0].strip("`")] = (re.findall(r"`([^`]+)`", cells[1]), [a.strip() for a in cells[2].split(",")])
    return rows


def test_every_builtin_type_has_targets_and_the_docs_table_matches() -> None:
    extensions.load_builtins()
    table = targets_table()
    builtin = {e.name: e.cls for e in registry.all() if e.builtin and e.name not in ALIASES}
    assert all(registry.get(alias).cls is builtin[name] for alias, name in ALIASES.items())
    assert sorted(table) == sorted(builtin) == sorted(SAMPLES)
    known = set(registry.action_names())
    for name, (targets, useful) in table.items():
        assert targets == list(builtin[name].target_patterns), name
        assert useful and set(useful) <= known, name


def test_target_names_of_every_builtin_type() -> None:
    extensions.load_builtins()

    def names(kind: str, **changes: Any) -> list[str]:
        cls = registry.get(kind).cls
        return cls.target_names(cls.validate_params({**SAMPLES[kind], **changes}))

    assert names("title") == ["icon", "kicker", "title", "subtitle", "authors"]
    assert names("title", kicker="", icon=None, subtitle="", authors=[]) == ["title"]
    assert names("text_card") == ["text"]
    assert names("quote", source="") == ["mark", "quote", "author"]
    assert names("icon_grid") == ["heading", "item1", "item:One", "item2", "item:Two"]
    assert names("line_chart") == ["title", "axes", "series1", "series:a", "point:a@1", "point:a@2", "point:a@3",
                                   "series2", "series:b", "point:b@1", "point:b@2", "point:b@3"]
    assert names("line_chart", title="", x=["Q1", "Q2", "Q3"])[:3] == ["axes", "series1", "series:a"]
    assert "point:a@Q2" in names("line_chart", x=["Q1", "Q2", "Q3"])
    assert names("image", caption="") == ["image"]
    assert names("equation") == ["step1", "step2", "caption", "term:2ab"]
    assert names("code") == ["title", "listing", "line1", "line2", "line3", "lines:1-2", "lines:1-3", "lines:2-3"]
    assert names("end_card", logo=None) == ["icon", "title", "line1", "line2"]
    assert names("chapter") == ["icon", "number", "title", "subtitle"]
    assert names("chapter", number=None, icon=None, subtitle="") == ["title"]
    assert names("chapter", number="") == ["icon", "title", "subtitle"]
    assert names("stat") == ["icon", "value", "label", "comparison", "context"]
    assert names("stat", label="", context="", comparison=None, icon=None) == ["value"]
    assert names("comparison") == ["heading", "col1", "col:A", "col1.item1", "col1.item2", "col2", "col:B", "col2.item1"]
    assert names("comparison", heading="", verdict="V") == ["col1", "col:A", "col1.item1", "col1.item2", "col2", "col:B", "col2.item1", "verdict"]
    assert names("table") == ["title", "header", "row1", "row:a", "row2", "row:b", "col1", "col:Name", "col2", "col:N",
                              "cell1.1", "cell1.2", "cell2.1", "cell2.2", "caption"]
    assert names("timeline") == ["heading", "axis", "event1", "event:1969", "event2", "event:1981"]
    assert names("timeline", heading="")[:2] == ["axis", "event1"]
    assert names("diagram") == ["heading", "node1", "node:a", "node2", "node:b", "edge:a->b"]
    assert names("process") == ["heading", "input", "stage1", "stage:a", "stage2", "stage:b", "connector1", "token"]
    assert names("process", heading="", input="", token=False, loop=True, output="o") == ["stage1", "stage:a", "stage2", "stage:b", "connector1", "loop", "output"]
    assert names("network") == ["heading", "layer1", "neuron1.1", "neuron1.2", "layer2", "layer:Out", "neuron2.1", "neuron2.2", "edges1"]
    assert names("pie") == ["title", "slice1", "slice:a", "slice2", "slice:b", "center", "legend"]
    assert names("pie", title="", donut=False, legend=None) == ["slice1", "slice:a", "slice2", "slice:b"]
    assert names("heatmap") == ["title", "legend", "row1", "row:a", "row2", "row:b", "col1", "col:x", "col2", "col:y",
                                "cell1.1", "cell1.2", "cell2.1", "cell2.2"]
    assert names("heatmap", title="", legend=False, rows=[], columns=[]) == ["row1", "row2", "col1", "col2", "cell1.1", "cell1.2", "cell2.1", "cell2.2"]
    assert names("table", title="", caption="", header=[]) == ["row1", "row:a", "row2", "row:b", "col1", "col2",
                                                               "cell1.1", "cell1.2", "cell2.1", "cell2.2"]


def test_equation_terms_must_occur_in_a_step() -> None:
    extensions.load_builtins()
    cls = registry.get("equation").cls
    with pytest.raises(Exception, match="terms: '3c' is not part of any step"):
        cls.validate_params({"latex": "a + b", "terms": ["3c"]})


def test_code_lines_of_a_file_are_counted_in_the_project(make_project) -> None:
    root = make_project(minimal_config(scenes=[{
        "id": "c", "type": "code", "params": {"path": "assets/x.py"},
        "beats": beats([{"zoom": "lines:2-3"}], [{"highlight": "line4"}]),
    }]))
    write_files(root, {"assets/x.py": "a = 1\nb = 2\nc = 3\n"})
    problems = project_problems(Project.load(root))
    assert [p.location for p in problems] == ["scenes[0].beats[1].actions[0].target"]
    assert "unknown target 'line4' for scene type 'code'" in problems[0].message


@pytest.mark.render
@pytest.mark.parametrize("kind", sorted(SAMPLES))
def test_builtin_scenes_register_their_target_names(kind: str, make_project, media: Path) -> None:
    """What ``construct`` registers is what ``target_names`` promised, and every target ends up
    on screen (the scene reveals all of them in its steps)."""
    project = load(make_project, [{"id": "s", "type": kind, "params": SAMPLES[kind], "beats": beats(None, None)}])
    scene = render(project, "s", media)
    registered = sorted(n for t in scene.targets for n in t.names)
    assert registered == sorted(type(scene).target_names(scene.params))
    hidden = [t.name for t in scene.targets if not scene.is_shown(t)]
    assert hidden == (["step1"] if kind == "equation" else [])   # an equation step morphs into the next


@pytest.mark.render
@pytest.mark.parametrize(
    ("kind", "target"),
    [("title", "authors"), ("quote", ["author", "source"]), ("end_card", "line*"), ("icon_grid", "item2"),
     ("line_chart", "series2"), ("image", "caption"), ("code", "line3"), ("code_walkthrough", "note2"), ("text_card", "text"),
     ("chapter", "subtitle"), ("stat", ["comparison", "context"]), ("comparison", "col2"), ("table", "row2"), ("timeline", "event2"),
     ("diagram", "edge:a->b"), ("network", ["layer2", "edges1"]), ("scatter", ["series2", "trend"]), ("histogram", ["mean", "median", "compare"]),
     ("pie", "slice2"), ("heatmap", "row2")],   # process: its token still moves (test_process_network)
)
def test_early_reveal_is_not_repeated_by_the_scene(kind: str, target: str | list[str], make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": kind, "params": SAMPLES[kind], "beats": beats([{"reveal": target}], None)}])
    scene = render(project, "s", media)
    assert all(scene.is_shown(t) for t in scene.find_targets(target if isinstance(target, str) else target[0]))
    assert plays(scene, "s_b2") == []   # the step meant for it found it on screen
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)


# ----- zoom -------------------------------------------------------------------------------------


@pytest.mark.render
def test_zoom_moves_the_camera_in_and_back_by_the_beat_end(make_project, media: Path) -> None:
    acts = beats(
        [{"zoom": "item1", "scale": 2}],                     # back by the end of this beat
        [{"zoom": "item2", "until": "s_b4", "at": 0.2}],     # back by the end of beat 3
        None,
        None,
        words="one two three four five six seven eight nine ten eleven twelve",
    )
    project = load(make_project, [{"id": "s", "type": "bullets", "params": BULLETS, "beats": acts}])
    scene = render(project, "s", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert [len(camera_moves(scene, b.id)) for b in scene.beats] == [2, 1, 1, 0]
    for beat in ("s_b1", "s_b3"):
        back = camera_moves(scene, beat)[-1]
        assert back.end == pytest.approx(beat_end(scene, beat), abs=1.5 / FPS) and back.requested is None
    frame = scene.camera.frame
    assert frame.width == pytest.approx(scene.frame_width) and np.allclose(frame.get_center(), 0, atol=1e-6)
    assert frame not in scene.mobjects   # a camera move does not leave the frame in the scene


@pytest.mark.render
def test_zoom_framing_and_a_short_beat(make_project, media: Path) -> None:
    acts = [{"text": " ".join(["word"] * 16), "actions": [{"zoom": "bar1", "padding": 0.3}]}]
    short = [{"text": "one two three four five six", "actions": [{"zoom": "bar1", "at": 0.5}]}]
    project = load(make_project, [
        {"id": "c", "type": "bar_chart", "params": {**BARS, "values": [0.4, 1.1, 1.3]}, "beats": acts},
        {"id": "q", "type": "bar_chart", "params": BARS, "beats": short},
    ])
    scene = render(project, "c", media)
    zoom_in, zoom_out = camera_moves(scene, "c_b1")
    assert zoom_in.end <= zoom_out.start + 1e-6 and zoom_in.requested is None and zoom_out.requested is None
    # the bar grows for most of a short beat: the zoom and its way back share what is left
    hurried = render(project, "q", media)
    moves = camera_moves(hurried, "q_b1")
    assert len(moves) == 2 and all(m.requested == 1.0 for m in moves)
    assert moves[-1].end <= beat_end(hurried, "q_b1") + 1e-6
    assert float(hurried.renderer.time) == pytest.approx(beat_total(hurried), abs=1.5 / FPS)


def test_zoom_fits_the_target_and_stays_inside_the_frame() -> None:
    """The geometry of ``zoom`` without rendering: a fake scene with a camera frame."""
    from manim import MovingCamera, Square, tempconfig

    extensions.load_builtins()
    zoom_cls = registry.find_action("zoom").cls
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": 8 * 16 / 9, "frame_height": 8.0}):
        camera = MovingCamera()

        class FakeScene:
            frame_width, frame_height = 8 * 16 / 9, 8.0
            spec = type("Spec", (), {"id": "s"})()

            def __init__(self) -> None:
                self.camera = camera

            def on_screen_parts(self, target: Any) -> list[Any]:
                return [target.mobject]

        def end_frame(mob: Any, **options: Any) -> tuple[float, np.ndarray]:
            act = zoom_cls(zoom_cls.Options(**options), None)  # type: ignore[arg-type]
            anims = act.apply(FakeScene(), [actions.Target(("t",), mob)])  # type: ignore[arg-type]
            if not anims:
                return camera.frame.width, camera.frame.get_center()
            return anims[0].target_mobject.width, anims[0].target_mobject.get_center()

        width, center = end_frame(Square(1).move_to([6, 3.5, 0]))         # small, near a corner
        assert width == pytest.approx(16 / 9 * 8 / 3)                       # max_scale 3
        assert center[0] + width / 2 == pytest.approx(8 * 16 / 9 / 2)        # pushed back inside
        assert center[1] + width * 9 / 16 / 2 == pytest.approx(4.0)
        width, _ = end_frame(Square(2), padding=0.25)
        assert width == pytest.approx(8 * 16 / 9 / (0.5 * 8 / 2))            # the square's height fits
        width, _ = end_frame(Square(2), scale=5)
        assert width == pytest.approx(8 * 16 / 9 / 5)


def test_zoom_on_a_target_that_fills_the_frame_warns(caplog: pytest.LogCaptureFixture) -> None:
    from manim import MovingCamera, Rectangle, tempconfig

    extensions.load_builtins()
    zoom_cls = registry.find_action("zoom").cls
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": 8 * 16 / 9, "frame_height": 8.0}):
        scene = type("S", (), {"frame_width": 8 * 16 / 9, "frame_height": 8.0, "camera": MovingCamera(),
                               "spec": type("Spec", (), {"id": "s"})(), "on_screen_parts": lambda self, t: [t.mobject]})()
        act = zoom_cls(zoom_cls.Options(), None)  # type: ignore[arg-type]
        with caplog.at_level(logging.WARNING, logger="vidgen"):
            assert act.apply(scene, [actions.Target(("big",), Rectangle(width=12, height=7))]) == []
        assert "zoom on big: the targets already fill the frame" in caplog.text
        assert act.revert(scene, []) == []   # the camera is home: nothing to undo


def test_lint_skips_frame_edges_while_zoomed() -> None:
    from test_lint import layout, text

    cut = text("t", [1800, 500, 2000, 540])
    margin = text("m", [40, 500, 400, 540])
    for zoom, found in ((1.0, 1), (2.0, 0)):
        frame = {"beat": "b", "k": 1, "n": 1, "time": 1.0, "camera": {"zoom": zoom}}
        for rule, obj in (("off_frame", cut), ("safe_area", margin)):
            ctx = StillContext(layout(), frame, [obj])
            assert len(list(RULES[rule].check(ctx, getattr(LintRules(), rule)))) == found
    assert not StillContext(layout(), {"camera": {}}).zoomed


# ----- transform --------------------------------------------------------------------------------


@pytest.mark.render
def test_transform_replaces_a_target_with_a_hidden_one(make_project, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    acts = beats(None, [{"transform": "item1", "into": "item4", "at": 0.3}], [{"transform": "item2", "into": "item4"}], None)
    project = load(make_project, [{"id": "s", "type": "bullets", "params": BULLETS, "beats": acts}])
    with caplog.at_level(logging.WARNING, logger="vidgen"):
        scene = render(project, "s", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert plays(scene, "s_b2")[-1][0].startswith("TransformMatchingShapes")   # text rows: matching glyphs
    assert not scene.is_shown("item1") and scene.is_shown("item4")
    # item4 already on screen: item2 fades out into its place (warning); beat 4 reveals nothing
    assert plays(scene, "s_b3")[-1] == ("FadeOut",) and "already on screen" in caplog.text
    assert not scene.is_shown("item2") and plays(scene, "s_b4") == []


@pytest.mark.render
@pytest.mark.parametrize(("style", "name"), [("replace", "ReplacementTransform"), ("fade", "FadeTransform"), ("tex", "TransformMatchingShapes")])
def test_transform_styles(style: str, name: str, make_project, media: Path) -> None:
    acts = beats([{"transform": "bar1", "into": "bar3", "style": style}])
    project = load(make_project, [{"id": "c", "type": "bar_chart", "params": {**BARS, "reveal": "per_beat"}, "beats": acts}])
    scene = render(project, "c", media)
    assert plays(scene, "c_b1")[-1][0].split("(")[0] == name   # tex needs formulas: matching shapes instead
    assert scene.is_shown("bar3") and not scene.is_shown("bar1")


def test_transform_into_is_checked(make_project) -> None:
    scenes = [{"id": "s", "type": "bullets", "params": BULLETS, "beats": beats([{"transform": "item1", "into": "item9"}, {"transform": "item1"}])}]  # one beat, two actions
    problems = {p.location: p.message for p in project_problems(project_with(make_project, scenes))}
    assert "unknown target 'item9' for scene type 'bullets'" in problems["scenes[0].beats[0].actions[0].into"]
    assert "Field required" in problems["scenes[0].beats[0].actions[1].into"]
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), [Theme()])
    shorthand = next(s for s in doc["$defs"]["ActionShorthand"]["anyOf"] if s["title"] == "transform (shorthand)")
    assert shorthand["required"] == ["transform", "into"]


@pytest.mark.render
def test_example_minimal_math_transform_and_zoom(media: Path) -> None:
    project = Project.load(ROOT / "examples" / "minimal")
    scene = render(project, "math", media)
    # beat 2: the scene's own morph, then the action's; beat 3's own morph is skipped
    assert [p[0].split("(")[0] for p in plays(scene, "math_b2")] == ["TransformMatchingShapes"] * 2
    assert plays(scene, "math_b3") == [("MoveCamera",), ("MoveCamera",)]
    assert scene.is_shown("step3") and not scene.is_shown("step2")
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)


# ----- dim, highlight, images, outline ----------------------------------------------------------


@pytest.mark.render
def test_dimming_never_compounds_and_highlight_undims(make_project, media: Path) -> None:
    params = {**BULLETS, "dim_previous": True}
    project = load(make_project, [
        {"id": "a", "type": "bullets", "params": params, "beats": beats([{"dim": "item1", "at": 0.5}], None, None)},
        {"id": "b", "type": "bullets", "params": params, "beats": beats([{"dim": "item1"}], [{"highlight": "item1", "until": "b_b3"}], None)},
        {"id": "c", "type": "bullets", "params": params, "beats": beats([{"dim": "item1"}], [{"highlight": "item1"}])},
    ])
    a = render(project, "a", media)
    rows = {t.name: t.mobject for t in a.targets}
    assert alpha(rows["item1"][-1]) == pytest.approx(0.45, abs=0.01)   # dim + dim_previous: still 0.45
    assert alpha(rows["item2"][-1]) == pytest.approx(0.45, abs=0.01)
    b = render(project, "b", media)
    item1 = next(t.mobject for t in b.targets if t.name == "item1")
    assert alpha(item1[-1]) == pytest.approx(0.45, abs=0.01) and rgb(item1[-1]) == color_of(b.theme, "text")
    c = render(project, "c", media)
    item1 = next(t.mobject for t in c.targets if t.name == "item1")
    assert alpha(item1[-1]) == pytest.approx(1.0) and rgb(item1[-1]) == color_of(c.theme, "highlight")


@pytest.mark.render
def test_images_are_dimmed_and_tinted(make_project, media: Path) -> None:
    project = load(make_project, [
        {"id": "d", "type": "image", "params": {"path": "assets/pic.png"}, "beats": beats([{"dim": "image", "opacity": 0.5}])},
        {"id": "h", "type": "image", "params": {"path": "assets/pic.png"}, "beats": beats([{"dim": "image", "until": "h_b2"}], [{"highlight": "image"}])},
    ])
    dimmed = render(project, "d", media)
    pixels = dimmed.targets[0].mobject.pixel_array
    assert int(pixels[..., 3].max()) == pytest.approx(128, abs=1) and tuple(pixels[0, 0, :3]) == (40, 120, 200)
    tinted = render(project, "h", media)
    pixels = tinted.targets[0].mobject.pixel_array
    assert int(pixels[..., 3].max()) == 255   # dim undone at beat 2
    assert tuple(pixels[0, 0, :3]) != (40, 120, 200) and int(pixels[0, 0, 0]) > 40   # tinted towards the highlight colour


@pytest.mark.render
def test_bar_box_sits_on_the_axis(make_project, media: Path) -> None:
    acts = beats([{"highlight": "bar*", "style": "box"}])
    params = {**BARS, "values": [0.4, -1.1, 9.8]}
    project = load(make_project, [{"id": "c", "type": "bar_chart", "params": params, "beats": acts}])
    scene = render(project, "c", media)
    boxes = [m for m in scene.mobjects if type(m).__name__ == "SurroundingRectangle"]
    assert len(boxes) == 3
    bars = [t.mobject[0] for t in scene.targets if t.name.startswith("bar")]
    up, down, tall = bars
    axis = up.get_bottom()[1]
    assert boxes[0].get_bottom()[1] > axis and boxes[2].get_bottom()[1] > axis     # above the axis
    assert boxes[1].get_top()[1] < down.get_top()[1] == pytest.approx(axis)       # a negative bar: below it
    assert boxes[2].get_top()[1] > tall.get_top()[1]                              # the value label is inside


# ----- framework --------------------------------------------------------------------------------


def test_temporary_and_target_option_checks() -> None:
    class NotReversible(actions.Action):
        temporary = True

        def apply(self, scene, targets):  # type: ignore[no-untyped-def]
            return []

    class BadOption(actions.Action):
        target_options = ("into",)

        def apply(self, scene, targets):  # type: ignore[no-untyped-def]
            return []

    with pytest.raises(VidgenError, match="temporary actions must be reversible"):
        actions.check_action_class("x", NotReversible)
    with pytest.raises(VidgenError, match="target_options into are not fields of its Options"):
        actions.check_action_class("x", BadOption)


def test_list_scenes_json_describes_temporary_and_target_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["list-scenes"]) == 0
    assert re.search(r"^zoom +builtin +\(run_time 1 s, until, undone by the beat's end\)$", capsys.readouterr().out, flags=re.M)
    assert main(["list-scenes", "--json"]) == 0
    acts = {a["name"]: a for a in json.loads(capsys.readouterr().out)["actions"]}
    assert (acts["zoom"]["temporary"], acts["zoom"]["target_options"]) == (True, [])
    assert (acts["transform"]["temporary"], acts["transform"]["target_options"]) == (False, ["into"])
    documented("temporary", "target_options")


def test_a_type_without_targets_rejects_actions(make_project) -> None:
    root = make_project(minimal_config(scenes=[{"id": "p", "type": "plain", "beats": beats([{"dim": "x"}])}]))
    write_files(root, {"extensions/plain.py": '''
        from vidgen.api import *


        @scene("plain")
        class Plain(NarratedScene):
            def construct(self):
                for _ in self.timeline():
                    pass
    '''})
    (problem,) = project_problems(Project.load(root))
    assert problem.message.startswith("scene type 'plain' has no action targets (types with targets: bar_chart, bullets, chapter, code,")


def test_config_md_action_examples_validate(make_project) -> None:
    text = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    section = text[text.index("## Beat actions") : text.index("**Syntax.**")]
    scenes = [s for block in re.findall(r"```yaml\n(.*?)```", section, flags=re.S) for s in yaml.safe_load(block)]
    assert [s["type"] for s in scenes] == ["bar_chart", "equation"]
    assert check_project(project_with(make_project, scenes)) == []
