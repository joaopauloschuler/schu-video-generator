"""Step 26 scene types: ``comparison`` (two or three columns, point by point) and ``table`` (a
header and rows fitted to the frame), at 16:9 and 9:16; dotted target names and the ``fill``
highlight style."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_actions import beat_total, beats, plays, render
from test_builtin_scenes import cls_of, expected_duration, render_scene
from test_schema import errors
from vidgen import actions, extensions, registry, schema
from vidgen.cli import check_project, project_problems
from vidgen.regions import MARGIN_X, MARGIN_Y, Region
from vidgen.render.worker import frame_size
from vidgen.project import Project
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
COLUMNS = [
    {"heading": "Before", "tone": "negative", "icon": "hourglass", "points": ["Slow builds", {"text": "Manual steps", "icon": "hand"}]},
    {"heading": "After", "tone": "positive", "points": ["Fast builds", "Automated", "Cached"]},
]
TABLE = {
    "title": "Results",
    "header": ["Model", "Params", "Accuracy"],
    "rows": [["Baseline", 110, 0.812], ["Sparse", 55, 0.809], ["Tiny", 14, 0.742]],
    "number_format": [None, "{:,.0f}M", "{:.1%}"],
    "caption": "Illustrative",
}


def safe_area_of(size: tuple[int, int]) -> Region:
    """The safe area of a frame of ``size`` pixels (the render's config is gone afterwards)."""
    fw, fh = frame_size(*size)
    return Region(-fw / 2 + MARGIN_X, -fh / 2 + MARGIN_Y, fw / 2 - MARGIN_X, fh / 2 - MARGIN_Y)


def load(make_project, scenes: list[dict[str, Any]]) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- target names -------------------------------------------------------------------------------


def test_dotted_target_names_are_valid() -> None:
    for name in ("col2.item3", "cell1.2", "col:Before", "row:4K", "a.b.c", "item3"):
        assert actions.TARGET_NAME.match(name), name
    for name in ("col2.", ".item", "2col", "col..x"):
        assert not actions.TARGET_NAME.match(name), name
    names = ["cell1.1", "cell1.2", "cell2.1", "col1.item1"]
    assert actions.match_names("cell1.*", names) == ["cell1.1", "cell1.2"]
    assert actions.match_names("cell?.1", names) == ["cell1.1", "cell2.1"]


# ----- comparison params --------------------------------------------------------------------------


def test_comparison_params_and_point_shorthand() -> None:
    p = cls_of("comparison").validate_params({"columns": COLUMNS}, Theme())
    assert [c.tone for c in p.columns] == ["negative", "positive"]
    assert [(pt.text, pt.icon) for pt in p.columns[0].points] == [("Slow builds", None), ("Manual steps", "hand")]
    assert p.reveal == "columns" and p.markers and p.cards and p.vs == ""


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"columns": COLUMNS[:1]}, "at least 2 items"),
        ({"columns": COLUMNS * 2}, "at most 3 items"),
        ({"columns": [{"heading": "", "points": []}, COLUMNS[1]]}, "at least 1 character"),
        ({"columns": [{"heading": "A", "tone": "good"}, COLUMNS[1]]}, "'positive', 'negative' or 'neutral'"),
        ({"columns": [{"heading": "A", "points": ["x"] * 9}, COLUMNS[1]]}, "at most 8 items"),
        ({"columns": [{"heading": "A", "points": [{"text": "x", "icon": "nope-icon"}]}, COLUMNS[1]]}, "unknown icon"),
        ({"columns": COLUMNS, "reveal": "beats"}, "'columns', 'rows' or 'all'"),
        ({"columns": COLUMNS, "verdict_color": "nope"}, "unknown theme color 'nope'"),
    ],
)
def test_comparison_params_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception, match=message):
        cls_of("comparison").validate_params(params, Theme())


def test_comparison_target_names_with_three_columns() -> None:
    cls = cls_of("comparison")
    params = cls.validate_params({"columns": [*COLUMNS, {"heading": "Later"}], "verdict": "v"}, Theme())
    assert cls.target_names(params) == [
        "col1", "col:Before", "col1.item1", "col1.item2",
        "col2", "col:After", "col2.item1", "col2.item2", "col2.item3",
        "col3", "col:Later", "verdict",
    ]


# ----- table params -------------------------------------------------------------------------------


def test_table_texts_alignment_and_formats() -> None:
    p = cls_of("table").validate_params(TABLE, Theme())
    assert p.texts() == [["Baseline", "110M", "81.2%"], ["Sparse", "55M", "80.9%"], ["Tiny", "14M", "74.2%"]]
    assert [p.alignment(c) for c in range(3)] == ["left", "right", "right"]
    auto = cls_of("table").validate_params({"rows": [["a", 1200, ""], ["b", 2.5, "x"]], "align": ["center", "auto", "auto"]}, Theme())
    assert auto.texts() == [["a", "1,200.0", ""], ["b", "2.5", "x"]]   # one number of decimals per column
    assert [auto.alignment(c) for c in range(3)] == ["center", "right", "left"]
    assert auto.column_count() == 3 and auto.numeric(1) and not auto.numeric(2)
    one = cls_of("table").validate_params({"rows": [[1, 2]], "number_format": "{:.2f}", "align": "center"}, Theme())
    assert one.texts() == [["1.00", "2.00"]] and one.alignment(0) == "center"


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"header": ["a", "b"], "rows": [["x", 1], ["y"]]}, r"rows\[1\] has 1 cells, expected 2 \(the header has 2\)"),
        ({"rows": [["x", 1], ["y", 2, 3]]}, r"rows\[1\] has 3 cells, expected 2 \(row 1 has 2\)"),
        ({"rows": [["x", True]]}, r"rows\[0\]\[1\]: True is not text or a number"),
        ({"rows": [["x", None]]}, "is not text or a number"),
        ({"rows": [["x", 1]], "align": ["left"]}, "align has 1 entries, expected one per column"),
        ({"rows": [["x", 1]], "number_format": "{:.1q}"}, "invalid number format"),
        ({"rows": [["x", 1]], "number_format": [None, "{:.1f}", None]}, "number_format has 3 entries"),
        ({"rows": [list(range(9))]}, "at most 8 columns"),
        ({"rows": [[]]}, "at least one column"),
        ({"rows": []}, "at least 1 item"),
        ({"rows": [["x"]], "stripe_color": "nope"}, "unknown theme color 'nope'"),
    ],
)
def test_table_params_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception, match=message):
        cls_of("table").validate_params(params, Theme())


def test_schema_accepts_points_and_mixed_cells() -> None:
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), [Theme()])
    scenes = [
        {"id": "c", "type": "comparison", "duration": 2, "params": {"columns": COLUMNS}},
        {"id": "t", "type": "table", "duration": 2, "params": TABLE},
    ]
    assert errors(doc, minimal_config(scenes=scenes)) == []
    bad = [{"id": "c", "type": "comparison", "duration": 2, "params": {"columns": [{"heading": "A", "points": [3]}, COLUMNS[1]]}}]
    assert errors(doc, minimal_config(scenes=bad))


def test_validate_checks_dotted_targets(make_project) -> None:
    scenes = [
        {"id": "c", "type": "comparison", "params": {"columns": COLUMNS}, "beats": beats([{"highlight": "col1.item2"}, {"dim": "col2.item4"}])},
        {"id": "t", "type": "table", "params": TABLE, "beats": beats([{"highlight": "cell3.3", "style": "fill"}, {"highlight": "col:Accuracy"}, {"dim": "row:Tiny"}])},
    ]
    problems = project_problems(load(make_project, scenes))
    assert [p.location for p in problems] == ["scenes[0].beats[0].actions[1].target"]
    assert "unknown target 'col2.item4' for scene type 'comparison'; did you mean 'col2.item3'" in problems[0].message


def test_validate_reports_bad_comparison_and_table_params(make_project) -> None:
    root = make_project(minimal_config(scenes=[
        {"id": "a", "type": "comparison", "params": {"columns": [{"heading": "A", "tone": "good"}, COLUMNS[1]]}, "duration": 2},
        {"id": "b", "type": "table", "params": {"header": ["a", "b"], "rows": [["x"]]}, "duration": 2},
    ]))
    problems = check_project(Project.load(root))
    assert problems[0].startswith("scenes[0].params.columns[0].tone:")
    assert problems[1].startswith("scenes[1].params: rows[0] has 1 cells, expected 2 (the header has 2)")


# ----- rendering ----------------------------------------------------------------------------------


def three_beats() -> list[dict[str, str]]:
    return [{"text": "one two three four five six"}, {"text": "seven eight nine ten"}, {"text": "eleven twelve thirteen"}]


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)])
@pytest.mark.parametrize(
    ("kind", "params", "beat_list"),
    [
        ("comparison", {"heading": "H", "columns": COLUMNS, "verdict": "Pick after", "vs": "vs"}, "three"),
        ("comparison", {"columns": [*COLUMNS, {"heading": "Third", "points": ["x"]}], "reveal": "rows"}, "three"),
        ("comparison", {"columns": COLUMNS, "reveal": "all", "markers": False, "cards": False}, "one"),
        ("comparison", {"columns": [{"heading": "A"}, {"heading": "B"}]}, "silent"),
        ("table", TABLE, "three"),
        ("table", {**TABLE, "reveal": "all", "zebra": False}, "one"),
        ("table", {"rows": [["a", 1], ["b", 2], ["c", 3], ["d", 4], ["e", 5]]}, "three"),
        ("table", {"header": ["x"], "rows": [["only"]]}, "silent"),
    ],
)
@pytest.mark.slow
def test_scenes_render_within_their_beats(kind: str, params: dict[str, Any], beat_list: str, size: tuple[int, int], make_project, media: Path) -> None:
    timing: dict[str, Any] = {"silent": {"duration": 2.0}, "one": {"beats": three_beats()[:1]}, "three": {"beats": three_beats()}}[beat_list]
    project = load(make_project, [{"id": "s", "type": kind, "params": params, **timing}])
    scene, duration, portrait = render_scene(project, "s", media, *size)
    assert portrait == (size[1] > size[0])
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    assert all(scene.beat_busy[b] <= scene.beat_duration(b) + scene.pad + 1e-6 for b in scene.beat_busy)
    safe = safe_area_of(size)
    on_screen = [t for t in scene.targets if t.mobject.has_points() or t.mobject.submobjects]
    for t in on_screen:   # everything stays inside the safe area
        m = t.mobject
        assert m.get_left()[0] >= safe.x0 - 0.05 and m.get_right()[0] <= safe.x1 + 0.05, t.name
        assert m.get_bottom()[1] >= safe.y0 - 0.05 and m.get_top()[1] <= safe.y1 + 0.05, t.name


@pytest.mark.render
def test_comparison_reveals_one_column_per_beat(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "comparison", "params": {"columns": COLUMNS, "verdict": "V"}, "beats": three_beats()}])
    scene = render(project, "s", media)
    names = {b.id: plays(scene, b.id) for b in scene.beats}
    assert all(names[b] for b in names)   # each beat has its own step: column 1, column 2, verdict
    assert all(scene.is_shown(t) for t in scene.targets)
    col1, col2 = scene.find_targets("col1")[0], scene.find_targets("col2")[0]
    assert col1.mobject.get_x() < col2.mobject.get_x()   # side by side in 16:9
    assert col1.outline.width < safe_area_of((160, 90)).width / 2


@pytest.mark.render
@pytest.mark.slow
def test_comparison_stacks_columns_in_portrait_and_aligns_rows_side_by_side(make_project, media: Path) -> None:
    params = {"columns": COLUMNS, "reveal": "rows"}
    project = load(make_project, [{"id": "s", "type": "comparison", "params": params, "beats": three_beats()}])
    scene = render(project, "s", media, size=(90, 160))
    col1, col2 = scene.find_targets("col1")[0], scene.find_targets("col2")[0]
    assert col1.mobject.get_y() > col2.mobject.get_y() and abs(col1.mobject.get_x() - col2.mobject.get_x()) < 0.3
    wide = render(load(make_project, [{"id": "w", "type": "comparison", "params": params, "beats": three_beats()}]), "w", media)
    first = [wide.find_targets(f"col{c}.item1")[0].mobject[-1] for c in (1, 2)]
    assert first[0][0].get_bottom()[1] == pytest.approx(first[1][0].get_bottom()[1], abs=0.05)   # row 1 on one baseline


@pytest.mark.render
def test_comparison_early_point_reveal_brings_its_column(make_project, media: Path) -> None:
    acts = beats([{"reveal": "col2.item2"}], None, None)
    project = load(make_project, [{"id": "s", "type": "comparison", "params": {"columns": COLUMNS}, "beats": acts}])
    scene = render(project, "s", media)
    assert scene.is_shown("col2.item2") and scene.is_shown("col2.item1")
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)


@pytest.mark.render
@pytest.mark.slow
def test_table_fits_and_aligns_numbers_right(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "table", "params": TABLE, "beats": three_beats()}])
    scene = render(project, "s", media)
    rights = [scene.find_targets(f"cell{r}.2")[0].mobject.get_right()[0] for r in (1, 2, 3)]
    assert max(rights) - min(rights) < 0.02
    lefts = [scene.find_targets(f"cell{r}.1")[0].mobject.get_left()[0] for r in (1, 2, 3)]
    assert max(lefts) - min(lefts) < 0.02
    header = scene.find_targets("header")[0].mobject
    assert header.get_y() > scene.find_targets("row1")[0].mobject.get_y() > scene.find_targets("row3")[0].mobject.get_y()
    row = scene.find_targets("row:Sparse")[0]
    assert row.outline.width > row.mobject.width   # a highlight box spans the whole row
    assert [t.name for t in scene.targets if not scene.is_shown(t)] == []


@pytest.mark.render
def test_table_wraps_text_columns_in_portrait(make_project, media: Path) -> None:
    long = {"header": ["Name", "Notes"], "rows": [["a", "a fairly long note that has to wrap in a narrow frame"], ["b", "short"]]}
    project = load(make_project, [{"id": "s", "type": "table", "params": long, "beats": three_beats()[:1]}])
    scene = render(project, "s", media, size=(90, 160))
    note = scene.find_targets("cell1.2")[0].mobject
    assert len(note) > 1   # wrapped onto several lines
    assert note.get_right()[0] <= safe_area_of((90, 160)).x1 + 1e-6


@pytest.mark.render
@pytest.mark.slow
def test_table_too_big_for_the_frame_warns(make_project, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    rows = [[f"row {i} with a long description", i * 1000, i / 7, "more words here"] for i in range(1, 25)]
    project = load(make_project, [{"id": "s", "type": "table", "params": {"rows": rows}, "duration": 1.0}])
    with caplog.at_level(logging.WARNING):
        scene = render(project, "s", media, size=(90, 160))
    assert any("does not fit this frame at the readable size" in r.getMessage() and "split it" in r.getMessage() for r in caplog.records)
    table = scene.find_targets("col*")
    assert all(safe_area_of((90, 160)).contains(t.mobject, tolerance=0.05) for t in table)


@pytest.mark.render
@pytest.mark.slow
def test_fill_highlight_lies_under_the_cells_and_is_removed(make_project, media: Path) -> None:
    acts = beats([{"highlight": "row2", "style": "fill", "until": "s_b2"}], [{"highlight": "col2", "style": ["fill", "box"]}])
    project = load(make_project, [{"id": "s", "type": "table", "params": {**TABLE, "reveal": "all"}, "beats": acts}])
    scene = render(project, "s", media)
    plates = [m for m in scene.mobjects if type(m).__name__ == "SurroundingRectangle" and m.get_stroke_width() == 0]
    assert len(plates) == 1   # row 2's plate went with until; column 2's stays
    plate = plates[0]
    assert plate.get_fill_opacity() == pytest.approx(0.22, abs=0.01)
    cells = [scene.find_targets(f"cell{r}.2")[0].mobject for r in (1, 2, 3)]
    index = scene.mobjects.index
    assert all(index(plate) < index(c) for c in cells)            # drawn under the cells it covers
    stripes = [m for m in scene.mobjects if m.z_index < 0]
    assert stripes and all(plate.z_index > s.z_index for s in stripes)   # and over the zebra stripes
    outline = scene.find_targets("col2")[0].outline
    assert plate.width == pytest.approx(outline.width + 2 * 0.12, abs=0.02)
    assert np.allclose(plate.get_center(), outline.get_center(), atol=0.02)
