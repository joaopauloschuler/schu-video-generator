"""Built-in scene library: params validation, project-aware checks and tiny renders."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import pytest
from manim import tempconfig
from pydantic import ValidationError

from conftest import minimal_config
from vidgen import extensions, registry
from vidgen.cli import check_project, main
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.worker import frame_size
from vidgen.scenes.code import parse_line_spec
from vidgen.theme import Theme

BUILTINS = ["bar_chart", "bullets", "chapter", "code", "code_walkthrough", "comparison", "diagram", "end_card", "equation", "equation_derivation", "flowchart", "heatmap", "histogram", "icon_grid", "image", "line_chart", "network", "pie", "process", "quote", "scatter", "screenshot", "stat", "table", "text_card", "timeline", "title"]
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "minimal"
FPS = 5

#: Valid params for every built-in (the image/logo/code files are written by `asset_project`).
SAMPLES: dict[str, dict[str, Any]] = {
    "title": {"title": "A title with highlight", "highlight": "highlight", "subtitle": "Sub", "kicker": "K", "authors": ["A", "B"], "icon": "idea"},
    "bullets": {"heading": "Heading", "items": ["one", {"text": "two", "icon": "cpu"}, "three is longer than the others"], "numbered": True, "dim_previous": True},
    "bar_chart": {"title": "Bars", "labels": ["a", "b", "c"], "values": [1, 2.5, -1], "highlight": "b", "unit": "%"},
    "line_chart": {"title": "Lines", "x": [1, 2, 3], "series": {"s1": [1, 2, 3], "s2": [3, 2, 2.5]}, "x_label": "x", "y_label": "y"},
    "image": {"path": "assets/pic.png", "caption": "Caption", "ken_burns": True},
    "screenshot": {"path": "assets/pic.png", "title": "Shot", "frame": "browser", "url": "example.org",
                   "steps": [{"box": [0.1, 0.1, 0.4, 0.3], "label": "Box"}, [{"arrow": [0.7, 0.6], "label": "Arrow", "curved": True}, {"circle": [0.5, 0.5]}],
                             {"callouts": [{"magnifier": [0.1, 0.5, 0.3, 0.3], "label": "Zoom"}, {"spotlight": [0.1, 0.5, 0.3, 0.3]}], "focus": True}]},
    "quote": {"text": "“To be or not to be.”", "author": "Someone", "source": "Somewhere"},
    "equation": {"latex": ["x^2", "x \\cdot x"], "caption": "Square"},
    "equation_derivation": {"title": "Solve", "colors": {"x": "accent"}, "terms": ["3"],
                            "steps": ["{{ 2x }} + 3 = 5", {"tex": "{{ 2x }} = 2", "note": "minus 3", "match": ["2"]}, {"tex": "x = 1", "note": "halve"}]},
    "code": {"code": "a = 1\nb = 2\nprint(a + b)\n", "language": "python", "highlight": ["1-2", 3], "title": "Code"},
    "code_walkthrough": {"code": "\n".join(f"x{k} = {k}" for k in range(1, 13)), "title": "Walk", "visible": 4,
                         "steps": [{"lines": "2-3", "note": "Two lines."}, {"lines": "/x11/", "focus": True}, {"note": "Kept."}]},
    "end_card": {"title": "Thanks", "lines": ["example.com"], "logo": "assets/pic.png", "icon": "heart"},
    "icon_grid": {"heading": "Grid", "items": [{"icon": "cpu", "label": "CPU", "sublabel": "compute"}, {"icon": "home", "label": "Home"}, {"icon": "cloud", "label": "Cloud"}], "highlight": 1, "icon_color": "palette"},
    "text_card": {"text": "Hello world"},
    "chapter": {"number": 3, "title": "Results", "subtitle": "What we found", "icon": "chart-line"},
    "comparison": {"heading": "A vs B", "columns": [{"heading": "A", "tone": "positive", "icon": "cpu", "points": ["fast", {"text": "cheap", "icon": "coins"}]}, {"heading": "B", "tone": "negative", "points": ["slow"]}], "verdict": "Pick A", "vs": "vs"},
    "table": {"title": "T", "header": ["Name", "Value"], "rows": [["a", 1.5], ["b", 1200]], "caption": "c"},
    "timeline": {"heading": "History", "events": [{"date": 1957, "title": "Sputnik", "text": "First satellite", "icon": "satellite"}, {"date": "1969", "title": "Apollo 11"}, {"date": "1981", "title": "Shuttle"}], "spacing": "proportional", "highlight": "Apollo 11", "now": 1},
    "diagram": {"heading": "Flow", "nodes": ["a", {"id": "b", "label": "Bee", "shape": "diamond", "icon": "cpu"}, {"id": "c", "shape": "cylinder"}], "edges": ["a -> b: go", "b --> c", "c -> a"], "highlight": ["a", "b"]},
    "process": {"heading": "Flow", "input": "in", "output": "out", "token_label": "job", "loop": True, "stages": ["a", {"label": "b", "icon": "cpu", "text": "detail"}, "c"]},
    "network": {"heading": "Net", "layers": [3, {"size": 100, "label": "Hidden"}, {"size": 2, "label": "Out", "connect": "sparse:0.5"}], "highlight": ["1.1", "2.1"]},
    "flowchart": {"nodes": ["start", "end"], "edges": ["start -> end"], "routing": "orthogonal", "steps": [["start"], ["end"]]},
    "stat": {"value": 1234.5, "prefix": "$", "unit": "k", "label": "Revenue", "context": "2025", "icon": "banknote", "comparison": {"value": 1000, "delta": "percent"}},
    "scatter": {"title": "Points", "series": {"a": [[1, 2], [2, 3.5, "two"], [3, 3]], "b": [[1.5, 1], [2.5, 2]]}, "trend": "each", "trend_label": "both", "highlight": ["two"], "x_label": "x"},
    "histogram": {"title": "Spread", "values": [1, 2, 2, 3, 3, 3, 4, 4, 5, 7], "mean": True, "median": True, "compare": {"name": "b", "values": [2, 3, 4, 4, 5, 6]}, "highlight": [1]},
    "pie": {"title": "Shares", "labels": ["a", "b", "c", "d", "e"], "values": [50, 25, 15, 6, 4], "donut": True, "center_label": "total", "other_below": 10, "highlight": "b"},
    "heatmap": {"title": "Grid", "rows": ["r1", "r2"], "columns": ["c1", "c2", "c3"], "values": [[1, -2, 3], [None, 0.5, -1]], "legend_label": "v", "highlight": ["row:r2"]},
}


@pytest.fixture
def builtins_loaded() -> None:
    extensions.load_builtins()


def cls_of(name: str) -> Any:
    extensions.load_builtins()
    return registry.get(name).cls


def write_png(path: Path, size: tuple[int, int] = (64, 40)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 120, 40)).save(path)
    return path


@pytest.fixture
def asset_project(make_project):
    """A project folder with assets/pic.png and the given scenes."""

    def make(scenes: list[dict[str, Any]], **overrides: Any) -> Project:
        root = make_project(minimal_config(scenes=scenes, **overrides))
        write_png(root / "assets" / "pic.png")
        return Project.load(root)

    return make


# ----- registry and params --------------------------------------------------------------------------


def test_every_builtin_is_registered(builtins_loaded: None) -> None:
    assert registry.names() == BUILTINS
    assert all(registry.get(n).builtin for n in BUILTINS)


def test_builtins_use_only_the_public_api() -> None:
    """Built-ins are the proof that the extension API suffices: no private vidgen imports."""
    for module in (Path(__file__).resolve().parents[1] / "src/vidgen/scenes").glob("*.py"):
        if module.name == "__init__.py":
            continue
        imports = [line for line in module.read_text(encoding="utf-8").splitlines() if line.startswith(("import ", "from "))]
        vidgen_imports = [line for line in imports if "vidgen" in line]
        assert vidgen_imports == ["from vidgen.api import *"], module.name


@pytest.mark.parametrize("name", BUILTINS)
def test_sample_params_are_valid(name: str) -> None:
    cls_of(name).validate_params(SAMPLES[name], Theme())


@pytest.mark.parametrize("name", BUILTINS)
def test_unknown_keys_are_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        cls_of(name).validate_params({**SAMPLES[name], "colour": "red"})


@pytest.mark.parametrize(
    ("name", "params", "message"),
    [
        ("title", {"title": 3}, "valid string"),
        ("title", {"title": "Hello", "highlight": "bye"}, "not part of the title"),
        ("bullets", {"items": []}, "at least 1 item"),
        ("bullets", {"items": ["a"], "reveal": "sometimes"}, "'per_beat' or 'all'"),
        ("bar_chart", {"labels": ["a"], "values": ["x"]}, "valid number"),
        ("bar_chart", {"labels": ["a", "b"], "values": [1]}, "labels has 2 entries but values has 1"),
        ("bar_chart", {"labels": ["a"], "values": [1], "highlight": "z"}, "not one of the labels"),
        ("bar_chart", {"labels": ["a"], "values": [1], "highlight": 3}, "out of range"),
        ("bar_chart", {"labels": ["a"], "values": [1], "colors": ["primary", "accent"]}, "colors has 2 entries"),
        ("bar_chart", {"labels": ["a"], "values": [1], "value_format": "{:q}"}, "invalid number format"),
        ("line_chart", {"x": [1, 2], "series": {"s": [1]}}, "has 1 values but x has 2"),
        ("line_chart", {"x": [2, 1], "series": {"s": [1, 2]}}, "strictly increasing"),
        ("line_chart", {"x": [1, 2], "series": {"s": [1, 2]}, "y_min": 3, "y_max": 1}, "y_max must be greater"),
        ("image", {"path": "a.png", "fit": "stretch"}, "'contain' or 'cover'"),
        ("image", {"path": "a.png", "ken_burns": {"start_focus": [2, 0]}}, "between 0 and 1"),
        ("image", {"path": "a.png", "ken_burns": {"end_scale": 0.5}}, "greater than or equal to 1"),
        ("quote", {"text": ""}, "at least 1 character"),
        ("equation", {"latex": []}, "non-empty"),
        ("code", {"code": "x", "path": "y.py"}, "exactly one of"),
        ("code", {}, "exactly one of"),
        ("code", {"code": "x", "style": "nope"}, "unknown style"),
        ("code", {"code": "x", "language": "klingon"}, "unknown language"),
        ("code", {"code": "a\nb\n", "highlight": ["2-3"]}, "only 2 lines"),
        ("code", {"code": "a", "highlight": ["x-y"]}, "invalid line spec"),
        ("end_card", {}, "at least one of title, lines, logo or icon"),
        ("text_card", {"text": "x", "color": "#12"}, "invalid hex color"),
    ],
)
def test_params_errors(name: str, params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls_of(name).validate_params(params)


def test_theme_tokens_checked_against_theme() -> None:
    cls = cls_of("bullets")
    cls.validate_params({"items": ["a"], "color": "nonexistent"})  # no theme: only hex is checked
    with pytest.raises(ValidationError, match="unknown theme color 'nonexistent'"):
        cls.validate_params({"items": ["a"], "color": "nonexistent"}, Theme())
    with pytest.raises(ValidationError, match="unknown theme size 'huge'"):
        cls.validate_params({"items": ["a"], "size": "huge"}, Theme())
    with pytest.raises(ValidationError, match="size must be positive"):
        cls.validate_params({"items": ["a"], "size": -3})
    params = cls.validate_params({"items": ["a"], "color": "surface", "size": 40}, Theme())
    assert params.size == 40


def test_bar_colors_accept_palette_token_or_list() -> None:
    cls = cls_of("bar_chart")
    base = {"labels": ["a", "b"], "values": [1, 2]}
    assert cls.validate_params({**base, "colors": "palette"}, Theme()).colors == "palette"
    assert cls.validate_params({**base, "colors": ["accent", "#123456"]}, Theme()).colors == ["accent", "#123456"]
    with pytest.raises(ValidationError):
        cls.validate_params({**base, "colors": "pallete"}, Theme())


def test_line_chart_series_forms_are_equivalent() -> None:
    cls = cls_of("line_chart")
    a = cls.validate_params({"x": ["a", "b"], "series": {"s": [1, 2]}})
    b = cls.validate_params({"x": ["a", "b"], "series": [{"name": "s", "values": [1, 2]}]})
    assert a.series_list() == b.series_list()
    assert a.x == ["a", "b"]


@pytest.mark.parametrize(
    ("spec", "lines"),
    [(3, [3]), ("2-4", [2, 3, 4]), ("1, 5-6", [1, 5, 6]), ([4, 1, 4], [1, 4]), ("7 - 7", [7])],
)
def test_parse_line_spec(spec: Any, lines: list[int]) -> None:
    assert parse_line_spec(spec) == lines


@pytest.mark.parametrize("spec", ["4-2", "a", "0", [0], True, ""])
def test_parse_line_spec_errors(spec: Any) -> None:
    with pytest.raises(ValueError):
        parse_line_spec(spec)


# ----- project-aware validation (vidgen validate) -----------------------------------------------------


def test_validate_reports_missing_image(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(scenes=[{"id": "pic", "type": "image", "params": {"path": "assets/nope.png"}, "duration": 1}]))
    assert main(["validate", str(root)]) == 1
    assert "scenes[0].params.path: file not found: assets/nope.png" in capsys.readouterr().err


def test_validate_reports_unsupported_image_and_missing_logo_and_code(asset_project) -> None:
    project = asset_project(
        [
            {"id": "a", "type": "image", "params": {"path": "video.yaml"}, "duration": 1},
            {"id": "b", "type": "end_card", "params": {"title": "x", "logo": "assets/logo.png"}, "duration": 1},
            {"id": "c", "type": "code", "params": {"path": "src/x.py"}, "duration": 1},
            {"id": "d", "type": "image", "params": {"path": "assets/pic.png"}, "duration": 1},
        ]
    )
    problems = check_project(project)
    assert problems[0].startswith("scenes[0].params.path: unsupported image type '.yaml'")
    assert problems[1].startswith("scenes[1].params.logo: file not found: assets/logo.png")
    assert problems[2].startswith("scenes[2].params.path: file not found: src/x.py")
    assert len(problems) == 3


def test_validate_checks_code_file_highlight_lines(asset_project) -> None:
    project = asset_project([{"id": "c", "type": "code", "params": {"path": "snippet.py", "highlight": [5]}, "duration": 1}])
    (project.root / "snippet.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    assert check_project(project) == ["scenes[0].params.path: highlight 5: the code has only 2 lines"]


def test_validate_checks_theme_tokens_including_project_colors(asset_project) -> None:
    project = asset_project(
        [
            {"id": "a", "type": "text_card", "params": {"text": "x", "color": "brand"}, "duration": 1},
            {"id": "b", "type": "text_card", "params": {"text": "x", "color": "brnd"}, "duration": 1},
        ],
        theme={"colors": {"brand": "#123456"}},
    )
    (problem,) = check_project(project)
    assert problem.startswith("scenes[1].params.color: unknown theme color 'brnd'; known colors: accent, brand,")


def test_validate_warns_when_latex_missing(asset_project, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    import vidgen.scenes.equation as equation

    monkeypatch.setattr(equation, "latex_available", lambda: False)
    project = asset_project([{"id": "e", "type": "equation", "params": {"latex": "x"}, "duration": 1}])
    with caplog.at_level(logging.WARNING, logger="vidgen"):
        assert check_project(project) == []
    assert "need LaTeX" in caplog.text


def test_example_minimal_validates(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(EXAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "variants:  vertical" in out and out.endswith("ok\n")
    used = {s.type for s in Project.load(EXAMPLE).config.scenes}
    assert used == set(BUILTINS) - {"flowchart"}   # = diagram


# ----- rendering (tiny, both orientations) ---------------------------------------------------------------


@pytest.fixture(scope="module")
def shared_media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One Manim media dir for the module, so text/LaTeX caches are reused between renders."""
    return tmp_path_factory.mktemp("media")


def render_scene(project: Project, scene_id: str, media: Path, width: int, height: int) -> tuple[Any, float, bool]:
    """Render one scene in-process; returns (scene, duration, is_portrait as seen while rendering)."""
    fw, fh = frame_size(width, height)
    settings = {
        "pixel_width": width,
        "pixel_height": height,
        "frame_width": fw,
        "frame_height": fh,
        "frame_rate": FPS,
        "media_dir": str(media),
        "disable_caching": True,
        "progress_bar": "none",
        "verbosity": "ERROR",
        "output_file": f"{scene_id}_{width}x{height}",
    }
    with tempconfig(settings):
        spec = project.scene(scene_id)
        theme = extensions.activate(project)
        scene = registry.get(spec.type).cls(spec, project, theme)
        scene.render()
        return scene, float(scene.renderer.time), scene.is_portrait


def expected_duration(scene: Any) -> float:
    """Every beat lasts exactly d + pad (animations never overrun), then the outro fade."""
    if not scene.beats:
        return scene.spec.duration
    return sum(scene.beat_duration(i) + scene.pad for i in range(len(scene.beats))) + scene.outro


@pytest.fixture(scope="module")
def render_project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    root = tmp_path_factory.mktemp("builtins")
    import yaml

    scenes = [
        {"id": name, "type": name, "params": SAMPLES[name], "beats": [{"text": "one two"}, {"text": "three four five"}]}
        for name in BUILTINS
    ]
    scenes += [
        {"id": "silent_bullets", "type": "bullets", "params": {"items": ["a", "b", "c"]}, "duration": 1.2},
        {"id": "crowded", "type": "bullets", "params": {"items": [f"item {i}" for i in range(12)], "reveal": "per_beat"}, "beats": [{"text": "short"}]},
        {"id": "hbars", "type": "bar_chart", "params": {"labels": list("abcdefg"), "values": [1, 2, 3, 4, 5, 6, 7], "reveal": "per_beat"}, "beats": [{"text": "a b"}, {"text": "c d"}]},
        {"id": "cover", "type": "image", "params": {"path": "assets/pic.png", "fit": "cover", "caption": "c"}, "duration": 1.0},
    ]
    data = minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 4.0})
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    write_png(root / "assets" / "pic.png")
    return Project.load(root)


RENDER_IDS = BUILTINS + ["silent_bullets", "crowded", "hbars", "cover"]


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
@pytest.mark.parametrize("scene_id", RENDER_IDS)
def test_builtin_renders(render_project: Project, shared_media: Path, scene_id: str, size: tuple[int, int]) -> None:
    if scene_id in ("equation", "equation_derivation") and shutil.which("dvisvgm") is None:
        pytest.skip("LaTeX (dvisvgm) not installed")
    scene, duration, portrait = render_scene(render_project, scene_id, shared_media, *size)
    assert portrait == (size[1] > size[0])
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    assert [t.beat_id for t in scene.beat_log] == [b.id for b in scene.beats]
    if scene.outro > 0:  # finish() faded everything out
        assert scene.mobjects == []


@pytest.mark.render
def test_image_missing_at_render_is_a_clear_error(render_project: Project, shared_media: Path, tmp_path: Path) -> None:
    import yaml

    data = minimal_config(scenes=[{"id": "p", "type": "image", "params": {"path": "assets/gone.png"}, "duration": 1}])
    (tmp_path / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(VidgenError, match="scene 'p': path: file not found: assets/gone.png"):
        render_scene(Project.load(tmp_path), "p", shared_media, 160, 90)


@pytest.mark.render
def test_equation_without_latex_is_a_clear_error(render_project: Project, shared_media: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen import layout

    monkeypatch.setattr(layout.shutil, "which", lambda name: None)
    with pytest.raises(VidgenError, match=r"scene 'equation' \(type equation\) needs LaTeX.*MiKTeX"):
        render_scene(render_project, "equation", shared_media, 160, 90)


def test_validate_project_hook_for_extensions(make_project) -> None:
    from conftest import write_files

    root = make_project(minimal_config(scenes=[{"id": "a", "type": "needs_file", "params": {"data": "data.csv"}, "duration": 1}]))
    write_files(
        root,
        {
            "extensions/needs.py": """
            from vidgen.api import *

            @scene("needs_file")
            class NeedsFile(NarratedScene):
                class Params(SceneParams):
                    data: str

                @classmethod
                def validate_project(cls, params, project):
                    problems = super().validate_project(params, project)
                    if not (project.root / params.data).is_file():
                        problems.append(f"data: file not found: {params.data}")
                    return problems
            """
        },
    )
    assert check_project(Project.load(root)) == ["scenes[0].params.data: file not found: data.csv"]
    (root / "data.csv").write_text("x\n", encoding="utf-8")
    assert check_project(Project.load(root)) == []


def test_beat_count_checked_by_validate_and_listed(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    from conftest import write_files

    scenes = [
        {"id": "a", "type": "two_beats", "beats": [{"text": "one"}]},
        {"id": "b", "type": "two_beats", "beats": [{"text": "one"}, {"text": "two"}]},
        {"id": "c", "type": "two_beats", "duration": 1},
    ]
    root = make_project(minimal_config(scenes=scenes))
    write_files(
        root,
        {
            "extensions/fixed.py": """
            from vidgen.api import *

            @scene("two_beats")
            class TwoBeats(NarratedScene):
                beat_count = 2

                def construct(self):
                    with self.narrate(0):
                        pass
                    with self.narrate(1):
                        pass
            """
        },
    )
    assert check_project(Project.load(root)) == [
        "scenes[0].beats: type 'two_beats' needs exactly 2 beats, got 1",
        "scenes[2].beats: type 'two_beats' needs exactly 2 beats, got 0",
    ]
    assert main(["list-scenes", str(root)]) == 0
    out = capsys.readouterr().out
    assert "extensions/fixed.py\n    beats: exactly 2 beats\n" in out
    assert "\n    beats:" not in out.split("two_beats")[0]  # built-ins accept any number of beats
