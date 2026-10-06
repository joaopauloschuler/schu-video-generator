"""Step 31: the colour-scale chart helpers (``color_scale``, ``ColorScale``, ``color_bar``,
``mix_colors``, ``text_color_on``) and the ``pie`` (``donut``) and ``heatmap`` scene types."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import Text, tempconfig

from conftest import minimal_config
from test_actions import beat_total, beats, plays, render
from test_builtin_scenes import cls_of, expected_duration, render_scene
from test_charts import VERTICAL, load, n_beats, overlaps
from test_comparison_table import safe_area_of
from vidgen import runtime
from vidgen.charts import ColorScale, _oklab, color_bar, color_scale, mix_colors, text_color_on
from vidgen.cli import project_problems
from vidgen.config import ThemeConfig
from vidgen.errors import VidgenError
from vidgen.lint.color import contrast_ratio, hex_rgb
from vidgen.presets import BUILTIN_PRESETS
from vidgen.project import Project
from vidgen.regions import readable_size
from vidgen.render.worker import frame_size
from vidgen.theme import Theme

FPS = 5
SHARES = {"labels": ["Frames", "Text", "Audio", "Join", "Other work"], "values": [62, 18, 9, 7, 4]}
GRID = {"rows": ["Mon", "Tue", "Wed"], "columns": ["9h", "12h", "15h", "18h"], "values": [[3, 8, 4, 9], [5, 10, 6, 11], [4, 9, None, 13]]}


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


def pie(**changes: Any) -> Any:
    return cls_of("pie").validate_params({**SHARES, **changes}, Theme())


def heatmap(**changes: Any) -> Any:
    raw = {**GRID, **changes}
    return cls_of("heatmap").validate_params({k: v for k, v in raw.items() if v is not None}, Theme())


def themes() -> list[Theme]:
    return [Theme(ThemeConfig(preset=name)) for name in BUILTIN_PRESETS]


# ----- colour helpers --------------------------------------------------------------------------


def test_sequential_scale_runs_from_a_tint_to_the_colour_with_even_lightness() -> None:
    theme = Theme()
    scale = color_scale([0, 10], theme=theme)
    assert isinstance(scale, ColorScale) and (scale.lo, scale.hi) == (0, 10)
    assert scale(10) == theme.color("primary").upper()
    assert scale(0) == mix_colors("primary", theme.background, 0.14, theme=theme)
    assert scale(-5) == scale(0) and scale(99) == scale(10)               # clamped
    lightness = [_oklab(scale(v))[0] for v in np.linspace(0, 10, 11)]
    steps = np.diff(lightness)
    assert all(steps > 0) and steps.max() / steps.min() < 1.6              # monotone, about even


def test_diverging_scale_is_symmetric_around_its_center() -> None:
    theme = Theme()
    scale = color_scale([-3, 5], kind="diverging", theme=theme)
    assert (scale.lo, scale.hi, scale.center) == (-5, 5, 0)
    assert scale(-5) == theme.color("primary").upper() and scale(5) == theme.color("accent").upper()
    assert scale(0) == mix_colors("text", theme.background, 0.1, theme=theme)
    assert scale.fraction(-2.5) == pytest.approx(0.25) and scale.fraction(2.5) == pytest.approx(0.75)
    fixed = color_scale([1, 2], kind="diverging", lo=0, hi=10, center=2, theme=theme)
    assert fixed.fraction(1) == pytest.approx(0.25) and fixed.fraction(6) == pytest.approx(0.75)
    with pytest.raises(VidgenError, match="center"):
        color_scale([1, 2], kind="diverging", lo=3, hi=10, center=2, theme=theme)
    with pytest.raises(VidgenError, match="needs values"):
        color_scale([], theme=theme)


def test_text_on_any_scale_colour_reaches_the_lint_ratio_in_every_preset() -> None:
    for theme in themes():
        for kind in ("sequential", "diverging"):
            scale = color_scale([-1, 1], kind=kind, theme=theme)  # type: ignore[arg-type]
            for f in np.linspace(0, 1, 41):
                fill = scale.at(f)
                assert contrast_ratio(hex_rgb(text_color_on(fill, theme=theme)), hex_rgb(fill)) >= 4.5, (theme.preset, kind, fill)
        for color in theme.palette:
            assert contrast_ratio(hex_rgb(text_color_on(color, theme=theme)), hex_rgb(color)) >= 4.5
    theme = Theme()
    assert text_color_on(theme.background, theme=theme) == theme.color("text")
    assert mix_colors("#FFFFFF", "#000000", 0.5, theme=theme) == "#808080"


def test_color_bar_ticks_inside_the_scale(make_project) -> None:
    project = Project.load(make_project(minimal_config()))
    runtime.set_context(project)
    try:
        scale = color_scale([0, 18])
        bar = color_bar(scale, 4.0, title="renders")
        gradient, ticks, labels, title = bar
        assert len(gradient) == 49 and len(ticks) == len(labels) >= 3
        assert [t.original_text for t in labels] == ["0", "5", "10", "15"]
        assert all(t.font_size >= readable_size() * 0.99 for t in labels)
        assert title.get_bottom()[1] > gradient.get_top()[1]
        flat = color_bar(scale, 4.0, vertical=False)
        assert flat[0].width == pytest.approx(4.0, abs=0.1) and flat[2][0].get_y() < flat[0].get_y()
    finally:
        runtime.clear_context()


def test_api_exports_the_colour_helpers() -> None:
    import vidgen.api as api

    for name in ("ColorScale", "color_scale", "color_bar", "mix_colors", "text_color_on"):
        assert name in api.__all__ and getattr(api, name).__doc__, name


# ----- pie params ------------------------------------------------------------------------------


def test_pie_slices_sorting_grouping_and_shares() -> None:
    p = pie()
    assert [s.label for s in p.slices()] == SHARES["labels"] and p.percents() == ["62%", "18%", "9%", "7%", "4%"]
    grouped = pie(other_below=8)
    assert [s.label for s in grouped.slices()] == ["Frames", "Text", "Audio", "Other"]
    assert grouped.slices()[-1].value == 11 and grouped.slices()[-1].other and grouped.slices()[-1].color == "dim"
    assert [s.label for s in pie(max_slices=3).slices()] == ["Frames", "Text", "Other"]
    assert [s.label for s in pie(other_below=5).slices()] == SHARES["labels"]           # one small slice stays itself
    assert [s.label for s in pie(sort=True, labels=["a", "b", "c"], values=[1, 3, 2]).slices()] == ["b", "c", "a"]
    assert pie(labels=["a", "b"], values=[999, 1]).percents() == ["99.9%", "0.1%"]
    assert pie(percent_decimals=2).percents()[0] == "62.00%"
    assert pie(donut=True, unit=" s").center_text() == "100 s" and pie(donut=True, center="").center_text() == ""
    assert not pie().uses_legend() and pie(legend=True).uses_legend()
    assert pie(labels=list("abcdefg"), values=[1] * 7).uses_legend()                     # more than 6 slices
    assert pie(highlight="Text").highlight_index() == 1 and pie(highlight=0).highlight_index() == 0


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"values": [1, 2]}, "labels has 5 entries but values has 2"),
        ({"labels": ["a", "a"], "values": [1, 2]}, "unique"),
        ({"values": [1, -2, 3, 4, 5]}, "must not be negative"),
        ({"values": [0, 0, 0, 0, 0]}, "add up to 0"),
        ({"colors": ["primary"]}, "colors has 1 entries"),
        ({"center": "x"}, "set donut: true"),
        ({"highlight": "Nope"}, "is not a slice"),
        ({"highlight": "Join", "other_below": 8}, "grouped into 'Other'"),
        ({"highlight": 7}, "out of range"),
        ({"labels": [f"s{i}" for i in range(30)], "values": [1] * 30}, "at most 24"),
        ({"labels": ["Other", "b", "c"], "values": [5, 1, 1], "max_slices": 2}, "other_label 'Other' is also a label"),
        ({"hole": 0.95, "donut": True}, "less than or equal to 0.85"),
    ],
)
def test_pie_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception) as caught:
        pie(**changes)
    assert message in str(caught.value)


# ----- heatmap params ----------------------------------------------------------------------------


def test_heatmap_params() -> None:
    p = heatmap()
    assert p.shape() == (3, 4) and p.kind() == "sequential" and len(p.known()) == 11
    assert heatmap(values=[[1, -1], [0, 2]], rows=None, columns=None).kind() == "diverging"
    assert heatmap(values=[[1, -1], [0, 2]], rows=None, columns=None, scale="sequential").kind() == "sequential"
    assert p.cells_of("cell2.3") == [(1, 2)] and p.cells_of("row:Tue") == [(1, c) for c in range(4)]
    assert p.cells_of("col4") == [(r, 3) for r in range(3)] and p.cells_of("col:9h") == p.cells_of("col1")
    assert heatmap(value_format="{:.1f}", unit="%").number(3) == "3.0%"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"values": [[1, 2], [3]]}, "same number of values"),
        ({"values": [[]]}, "at least one value"),
        ({"rows": ["a"]}, "rows has 1 labels but the matrix has 3 rows"),
        ({"columns": ["a", "a", "b", "c"]}, "columns labels must be unique"),
        ({"values": [[None, None, None, None]] * 3}, "no values"),
        ({"values": [[0] * 41], "rows": None, "columns": None}, "at most 40"),
        ({"scale_min": 5, "scale_max": 1}, "greater than scale_min"),
        ({"scale": "diverging", "scale_min": 1, "scale_max": 9}, "center 0 must lie between"),
        ({"highlight": ["cell4.1"]}, "3 rows and 4 columns"),
        ({"highlight": ["row:Sun"]}, "no such row"),
        ({"highlight": ["col9"]}, "no such column"),
        ({"highlight": ["diag"]}, "use cell<R>.<C>"),
        ({"value_format": "{:q}"}, "invalid number format"),
    ],
)
def test_heatmap_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception) as caught:
        heatmap(**changes)
    assert message in str(caught.value)


def test_validate_checks_pie_and_heatmap_targets(make_project) -> None:
    project = load(make_project, [
        {"id": "p", "type": "pie", "params": SHARES, "beats": [{"text": "a", "actions": [{"highlight": "slice:Txt"}]}]},
        {"id": "h", "type": "heatmap", "params": GRID, "beats": [{"text": "a", "actions": [{"highlight": "cell4.1"}]}]},
    ])
    messages = [p.message for p in project_problems(project)]
    assert any("unknown target 'slice:Txt'" in m and "did you mean 'slice:Text'" in m for m in messages)
    assert any("unknown target 'cell4.1'" in m for m in messages)


# ----- rendering ---------------------------------------------------------------------------------------


def _texts(scene: Any) -> list[Text]:
    return [m for t in scene.targets for m in t.mobject.get_family() if isinstance(m, Text)]


def _floor(project: Project, size: tuple[int, int]) -> float:
    with tempconfig({"frame_width": frame_size(*size)[0], "frame_height": frame_size(*size)[1]}):
        runtime.set_context(project)
        floor = readable_size()
        runtime.clear_context()
    return floor


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)])
@pytest.mark.parametrize(
    ("kind", "p", "timing"),
    [
        ("pie", {**SHARES, "title": "Where the time goes", "highlight": "Text"}, 2),
        ("pie", {"labels": ["Mobile", "Desktop", "Tablet", "TV", "Car", "Watch"], "values": [5200, 3100, 640, 120, 60, 80], "donut": True,
                 "center_label": "visits", "other_below": 2, "reveal": "per_beat"}, 4),
        ("pie", {"labels": [f"s{i}" for i in range(12)], "values": list(range(12, 0, -1)), "donut": True, "show_values": "both"}, 0),
        ("heatmap", {**GRID, "title": "Renders", "legend_label": "renders", "highlight": ["col:18h"]}, 2),
        ("heatmap", {"values": [[1.0, 0.8, -0.3], [0.8, 1.0, 0.1], [-0.3, 0.1, 1.0]], "rows": ["a", "b", "c"], "columns": ["a", "b", "c"],
                     "value_format": "{:.1f}", "reveal": "rows", "highlight": ["cell3.1", "row2"]}, 4),
    ],
)
@pytest.mark.slow
def test_pie_and_heatmap_render_within_their_beats_and_the_safe_area(kind: str, p: dict[str, Any], timing: int, size: tuple[int, int], make_project, media: Path) -> None:
    extra = {"beats": n_beats(timing)} if timing else {"duration": 2.5}
    project = load(make_project, [{"id": "s", "type": kind, "params": p, **extra}])
    scene, duration, _ = render_scene(project, "s", media, *size)
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    assert all(scene.beat_busy[b] <= scene.beat_duration(b) + scene.pad + 1e-6 for b in scene.beat_busy)
    safe = safe_area_of(size)
    for t in scene.targets:
        assert safe.contains(t.mobject, tolerance=0.05), t.name
    texts = _texts(scene)
    assert texts and min(t.font_size for t in texts) >= _floor(project, size) * 0.99


@pytest.mark.render
@pytest.mark.slow
def test_pie_labels_stack_without_overlaps_and_read_on_their_slices(make_project, media: Path) -> None:
    p = {"labels": ["Big", "s1", "s2", "s3", "s4", "s5"], "values": [80, 5, 5, 4, 3, 3], "highlight": "s2", "legend": False}
    project = load(make_project, [{"id": "p", "type": "pie", "params": p, "beats": n_beats(2)}])
    scene = render(project, "p", media)
    labels = [m for m in scene._labels if m is not None]
    assert len(labels) == 6
    for a in range(len(labels)):
        for b in range(a + 1, len(labels)):
            assert not overlaps(labels[a], labels[b])
    assert scene._inside == {0}                                   # only the big slice holds its label
    inside = scene._labels[0]                                     # dimmed with its slice: recoloured for it
    fill = mix_colors(scene._wedges[0].get_fill_color().to_hex(), scene.theme.background, scene.dimmed_opacity, theme=scene.theme)
    for m in inside.family_members_with_points():
        assert m.get_fill_color().to_hex().upper() == text_color_on(fill, theme=scene.theme).upper()
        assert contrast_ratio(hex_rgb(m.get_fill_color().to_hex()), hex_rgb(fill)) >= 4.5
    assert sum(1 for m in scene._leaders if m is not None) == 5
    a, s = scene._angles[2]                                       # s2 moved out along its middle
    fresh = scene._wedge(a, s, scene._wedges[2].get_fill_color().to_hex())
    d = scene._wedges[2].get_center() - fresh.get_center()
    assert np.allclose(d[:2], np.array([math.cos(a + s / 2), math.sin(a + s / 2)]) * 0.1 * scene._radius, atol=1e-6)
    assert scene._wedges[0].get_fill_opacity() < 0.5 and scene._wedges[2].get_fill_opacity() == pytest.approx(1.0)
    total = sum(abs(sw) for _, sw in scene._angles)
    assert total == pytest.approx(2 * math.pi)


@pytest.mark.render
@pytest.mark.slow
def test_pie_portrait_puts_labels_that_do_not_fit_in_a_key(make_project, media: Path) -> None:
    p = {"labels": ["Manim frames", "Text layout", "Audio", "ffmpeg join", "Other work"], "values": [62, 18, 9, 7, 4]}
    project = load(make_project, [{"id": "p", "type": "pie", "params": p, "beats": n_beats(1)}], **VERTICAL)
    scene = render(project, "p", media, size=(90, 160))
    assert all(m is None for m in scene._leaders)                 # no side labels in a narrow frame
    assert scene._radius >= 0.3 * safe_area_of((90, 160)).width
    keys = [scene._labels[i] for i in range(5) if i not in scene._inside]
    assert keys and all(k.get_top()[1] < scene._center[1] - scene._radius for k in keys)   # below the pie


@pytest.mark.render
def test_pie_per_beat_sweeps_one_slice_per_beat_and_early_reveal(make_project, media: Path) -> None:
    p = {"labels": ["a", "b", "c"], "values": [3, 2, 1], "reveal": "per_beat", "donut": True}
    project = load(make_project, [{"id": "p", "type": "pie", "params": p, "beats": beats(None, [{"reveal": "slice3"}], None)}])
    scene = render(project, "p", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert plays(scene, "p_b3") == []                             # slice 3 came early
    assert all(scene.is_shown(t) for t in scene.targets)
    hole = scene.find_targets("center")[0].mobject
    assert scene.params.center_text() == "6" and len(hole) == 1
    assert np.allclose(hole.get_center()[:2], scene._center[:2], atol=0.2) and hole.width < 2 * scene._inner


@pytest.mark.render
def test_heatmap_cells_colours_text_and_highlight(make_project, media: Path) -> None:
    p = {**GRID, "highlight": ["row:Tue", "cell1.1"]}
    project = load(make_project, [{"id": "h", "type": "heatmap", "params": p, "beats": n_beats(2)}])
    scene = render(project, "h", media)
    scale = scene._scale
    for r, row in enumerate(GRID["values"]):
        for c, v in enumerate(row):
            cell, text = scene._cells_[r][c], scene._texts[r][c]
            if v is None:
                assert text is None and cell.get_fill_color().to_hex().upper() == scene.theme.color("surface").upper()
                continue
            assert cell.get_fill_color().to_hex().upper() == scale(v)
            assert text is not None and text.original_text == str(v)
            if r == 1 or (r, c) == (0, 0):
                assert cell.get_fill_opacity() == pytest.approx(1.0)
                assert contrast_ratio(hex_rgb(text.family_members_with_points()[0].get_fill_color().to_hex()), hex_rgb(scale(v))) >= 4.5
            else:
                assert cell.get_fill_opacity() < 0.5
    boxes = [m for m in scene.mobjects if type(m).__name__ == "Rectangle" and m.get_stroke_width() >= 3.9]
    assert len(boxes) == 2
    g = scene._grid
    assert any(b.width == pytest.approx(g.width, abs=1e-6) for b in boxes)   # the whole row
    assert [t.name for t in scene.targets if not scene.is_shown(t)] == []


@pytest.mark.render
def test_heatmap_rows_reveal_and_early_row(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "h", "type": "heatmap", "params": {**GRID, "reveal": "rows"}, "beats": beats(None, [{"reveal": "row3"}], None)}])
    scene = render(project, "h", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert plays(scene, "h_b3") == []
    assert all(scene.is_shown(t) for t in scene.targets)


@pytest.mark.render
@pytest.mark.slow
def test_heatmap_too_big_for_the_frame_hides_values_and_warns(make_project, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    values = [[r * 24 + c for c in range(24)] for r in range(8)]
    project = load(make_project, [{"id": "h", "type": "heatmap", "params": {"values": values, "show_values": True}, "beats": n_beats(1)}], **VERTICAL)
    with caplog.at_level(logging.WARNING, logger="vidgen.scenes"):
        scene = render(project, "h", media, size=(90, 160))
    assert all(t is None for row in scene._texts for t in row)
    assert any("do not fit this frame at a readable size" in r.message for r in caplog.records)
    assert any("too small for readable values" in r.message for r in caplog.records)
    bar = scene.find_targets("legend")[0].mobject
    assert bar.get_top()[1] < scene._grid.y0                         # 9:16: the legend is below
