"""Step 32: the ``code_walkthrough`` scene type (a long listing in a window that scrolls to each
step's lines, highlights them, shows notes and can focus), its line specs (numbers, ranges,
``/regex/``), and the portrait column cap shared with ``code``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import beat_total, beats, plays, render
from test_builtin_scenes import cls_of, expected_duration, render_scene
from test_comparison_table import safe_area_of
from test_schema import errors
from vidgen import registry, runtime, schema
from vidgen.charts import mix_colors
from vidgen.cli import check_project
from vidgen.project import Project
from vidgen.scenes.code import TARGET_COLUMNS, mono_metrics, size_for_columns
from vidgen.scenes.code_walkthrough import ALL_RANGES_UP_TO, parse_lines, resolve_lines
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
#: 30 short lines: ``line k = k`` (k = 1..30), a function header at 12 and a return at 15.
LONG = "\n".join("def f(x):" if k == 12 else "    return x" if k == 15 else f"v{k} = {k}" for k in range(1, 31)) + "\n"
SOURCE = LONG.rstrip("\n").split("\n")


def params(**changes: Any) -> Any:
    return cls_of("code_walkthrough").validate_params({"code": LONG, **changes}, Theme())


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides)))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- line specs -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "lines"),
    [(3, [3]), ("2-4", [2, 3, 4]), ("1, 5-6", [1, 5, 6]), ([4, "1-2"], [1, 2, 4]), ("/def f/", [12]),
     ("/def f/-/return/", [12, 13, 14, 15]), ("/v2 = /", [2]), ("29-/v30/", [29, 30]), ("/v1\\d/", [10])],
)
def test_resolve_lines(spec: Any, lines: list[int]) -> None:
    assert resolve_lines(spec, SOURCE) == lines


def test_resolve_lines_counts_from_the_first_shown_line() -> None:
    assert resolve_lines("/def f/", SOURCE[9:20], first=10) == [12]
    assert resolve_lines("11-12", SOURCE[9:20], first=10) == [11, 12]
    with pytest.raises(ValueError, match="line 3: the code has lines 10-20"):
        resolve_lines(3, SOURCE[9:20], first=10)


@pytest.mark.parametrize(
    ("spec", "message"),
    [("x-y", "invalid line spec"), ("4-2", "invalid line range"), (0, "start at 1"), (True, "invalid line spec"),
     ([], "no lines"), ("/(/", "invalid regular expression"), ("/nothing here/", "no line matches /nothing here/"),
     ("/def f/-/v3 = /", "no line matches /v3 = / from line 12 on"), (31, "line 31: the code has only 30 lines")],
)
def test_resolve_lines_errors(spec: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace("/", "/")):
        resolve_lines(spec, SOURCE)


def test_parse_lines_checks_syntax_only() -> None:
    assert parse_lines("3, /a,b/-7") == [(3, None), ("a,b", 7)]   # commas inside a regex are its own


# ----- params ---------------------------------------------------------------------------------------


def test_step_forms_are_equivalent() -> None:
    p = params(steps=["3-4", 7, [1, 2], {"lines": "/def f/", "note": "n", "focus": 1.5}, {"note": "keep"}, {"lines": "all"}])
    assert [s.lines for s in p.steps] == ["3-4", 7, [1, 2], "/def f/", None, "all"]
    assert p.steps[3].focus == 1.5 and p.steps[4].note == "keep"
    assert p.selections(LONG) == [[3, 4], [7], [1, 2], [12], None, "all"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [({"steps": ["40"]}, r"steps\[0\].lines '40': line 40: the code has only 30 lines"),
     ({"steps": [{"lines": "/zzz/"}]}, "no line matches"),
     ({"steps": [{"lines": "a-b"}]}, "invalid line spec"),
     ({"steps": [{"lines": 2, "focus": 5}]}, "more than 1 and at most 4"),
     ({"excerpt": "5"}, "use 'a-b'"), ({"excerpt": "20-40"}, "the code has only 30 lines"),
     ({"excerpt": "10-20", "steps": [3]}, "the code has lines 10-20"),
     ({"visible": 2}, "greater than or equal to 3"), ({"note_position": "left"}, "'auto', 'side' or 'bottom'"),
     ({"path": "x.py"}, "exactly one of"), ({"style": "nope"}, "unknown style")],
)
def test_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        params(**changes)


def test_target_names_short_and_long_listings() -> None:
    cls = cls_of("code_walkthrough")
    short = cls.validate_params({"code": "a\nb\nc\n", "title": "T", "steps": [{"lines": 1, "note": "x"}, 2, {"note": "y"}]}, Theme())
    assert cls.target_names(short) == ["title", "listing", "line1", "line2", "line3", "lines:1-2", "lines:1-3", "lines:2-3", "note1", "note3"]
    long = "\n".join(f"x{k} = {k}" for k in range(1, ALL_RANGES_UP_TO + 11))
    p = cls.validate_params({"code": long, "steps": ["3-5", "1, 8-9", "3-5", 20]}, Theme())
    names = cls.target_names(p)
    assert [n for n in names if n.startswith("lines:")] == ["lines:3-5", "lines:8-9"]   # the steps' ranges only
    assert names[1:3] == ["line1", "line2"] and "line50" in names
    excerpt = cls.validate_params({"code": long, "excerpt": "10-12"}, Theme())
    assert cls.target_names(excerpt) == ["listing", "line10", "line11", "line12", "lines:10-11", "lines:10-12", "lines:11-12"]


def test_validate_checks_the_code_file(make_project) -> None:
    project = Project.load(make_project(minimal_config(scenes=[
        {"id": "w", "type": "code_walkthrough", "params": {"path": "src/train.py", "steps": ["/def train/"]}, "duration": 1},
        {"id": "gone", "type": "code_walkthrough", "params": {"path": "src/none.py"}, "duration": 1},
    ])))
    (project.root / "src").mkdir()
    (project.root / "src" / "train.py").write_text("x = 1\n", encoding="utf-8")
    assert check_project(project) == [
        "scenes[0].params.path: steps[0].lines '/def train/': no line matches /def train/",
        f"scenes[1].params.path: file not found: src/none.py (looked for {project.root / 'src' / 'none.py'})",
    ]
    cls = cls_of("code_walkthrough")
    p = cls.validate_params({"path": "src/train.py"}, Theme())
    assert cls.target_names(p) == ["listing"]   # the file is read in the active project only
    runtime.set_context(project)
    try:
        assert cls.target_names(p) == ["listing", "line1"]
    finally:
        runtime.clear_context()


def test_schema_accepts_every_step_form() -> None:
    cls_of("code_walkthrough")
    doc = schema.params_schema(registry.get("code_walkthrough"), [Theme()])
    ok = {"code": "a\nb", "steps": ["1-2", 2, [1, "2"], {"lines": "/a/", "note": "n", "focus": True}], "note_position": "side"}
    assert errors(doc, ok) == []
    assert errors(doc, {"code": "a", "steps": [{"note": "n", "zoom": 2}]})


def test_portrait_column_cap() -> None:
    """``code`` and ``code_walkthrough`` wrap at the size that keeps TARGET_COLUMNS columns (or the
    readable size), not at the requested size: a vertical listing was wrapped to ~25 columns."""
    advance, pitch = mono_metrics("JetBrains Mono NL")
    assert 0.007 < advance < 0.01 and 0.012 < pitch < 0.02 and TARGET_COLUMNS == 32
    size = size_for_columns("JetBrains Mono NL", TARGET_COLUMNS, 6.8, digits=2, padding=0.8)
    assert (TARGET_COLUMNS + 2) * advance * size + 0.25 + 0.8 == pytest.approx(6.8)


# ----- rendering --------------------------------------------------------------------------------------


def scroll_scene(**changes: Any) -> dict[str, Any]:
    return {"id": "w", "type": "code_walkthrough",
            "params": {"code": LONG, "title": "Walk", "visible": 6, **changes},
            "beats": [{"text": "one two three four"}, {"text": "five six seven eight"}, {"text": "nine ten eleven"}]}


def rows_shown(scene: Any) -> list[int]:
    """Numbers of the code lines in the scene (the rows of the listing that are not taken out)."""
    return sorted(int(n[4:]) for t in scene.targets for n in t.names if n.startswith("line") and n[4:].isdigit() and scene.is_shown(t))


@pytest.mark.render
@pytest.mark.slow
def test_scrolls_to_each_steps_lines_and_keeps_the_view(make_project, media: Path) -> None:
    project = load(make_project, [scroll_scene(steps=["2-3", "/def f/-/return/", {"note": "same view"}])])
    scene = render(project, "w", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert scene._visible == 6
    assert rows_shown(scene) == list(range(11, 17))   # lines 12-15 centred in 6 rows; step 3 kept them
    assert not scene.is_shown("line2") and scene.is_shown("lines:12-15")
    assert "_ViewChange" in plays(scene, "w_b2")[0]
    assert all("_ViewChange" not in p for p in plays(scene, "w_b3"))   # no lines: the view stays
    assert scene.is_shown("note3")
    # highlighted rows at full opacity, the others dimmed
    full = [m.get_fill_opacity() for m in scene.find_targets("line13")[0].mobject.family_members_with_points()]
    dim = [m.get_fill_opacity() for m in scene.find_targets("line11")[0].mobject.family_members_with_points()]
    assert min(full) == pytest.approx(1) and max(dim) == pytest.approx(0.35)


@pytest.mark.render
@pytest.mark.slow
def test_reveal_action_scrolls_a_line_into_view(make_project, media: Path) -> None:
    acts = beats(None, [{"reveal": "line28"}, {"highlight": "line28", "style": "box", "at": 0.5}], None)
    spec = scroll_scene(steps=["1-2"])
    spec["beats"] = acts
    scene = render(load(make_project, [spec]), "w", media)
    assert scene.is_shown("line28") and not scene.is_shown("line1")
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)


@pytest.mark.render
def test_notes_beside_in_landscape_and_below_in_portrait(make_project, media: Path) -> None:
    code = "a = 1\nb = 2\nc = a + b\nprint(c)\n"
    spec = {"id": "w", "type": "code_walkthrough", "params": {"code": code, "steps": [{"lines": 3, "note": "The sum."}]},
            "beats": [{"text": "one two three"}]}
    wide = render(load(make_project, [spec]), "w", media)
    tall = render(load(make_project, [spec], format={"width": 1080, "height": 1920}), "w", media, size=(90, 160))
    for scene, size in ((wide, (160, 90)), (tall, (90, 160))):
        for mob in scene.mobjects:
            assert safe_area_of(size).contains(mob, tolerance=0.02), type(mob).__name__
    note, window = wide.find_targets("note1")[0].mobject, wide._frame
    assert wide._mode == "side" and note[0].get_left()[0] > window.get_right()[0]
    assert len(note) == 4   # box, text, pointer line and dot
    assert note[0].get_bottom()[1] < wide._band_center(wide._views[0]) < note[0].get_top()[1]
    note, window = tall.find_targets("note1")[0].mobject, tall._frame
    assert tall._mode == "bottom" and note.get_top()[1] < window.get_bottom()[1]


@pytest.mark.render
@pytest.mark.slow
def test_focus_moves_the_camera_in_and_back(make_project, media: Path) -> None:
    spec = scroll_scene(steps=[{"lines": 2}, {"lines": "12", "note": "The header.", "focus": True}, "20"])
    scene = render(load(make_project, [spec]), "w", media)
    moves = [p for p in scene.play_log if "MoveCamera" in p.animations]
    assert [p.beat for p in moves] == ["w_b2", "w_b3"]   # in for step 2, out with step 3
    view = scene._views[1]
    assert view.camera is not None and view.camera[0] < scene.frame_width / 1.5
    assert scene.camera.frame.width == pytest.approx(scene.frame_width)
    card = scene._notes[1]
    assert card.height < 1.0 and card.get_top()[1] < scene._row_y(11, view.offset)   # a small card under the line
    assert scene._emphasis(view, 10) == 0 and scene._emphasis(view, 11) == 1   # the rest is hidden around a focus


@pytest.mark.render
def test_syntax_colours_stay_readable_on_the_window_and_the_band(make_project, media: Path) -> None:
    """warm_editorial's Pygments style (`default`) draws decorators in #AA22FF, 4.4:1 on the band."""
    from vidgen.scenes.code_walkthrough import _contrast

    code = "@dataclass\nclass Config:\n    # a comment\n    seed: int = 0\n"
    spec = {"id": "w", "type": "code_walkthrough", "params": {"code": code, "steps": ["1-2"]}, "beats": [{"text": "one two"}]}
    scene = render(load(make_project, [spec], theme={"preset": "warm_editorial"}), "w", media)
    surface = scene.theme.color("surface")
    band = mix_colors(scene.theme.color("highlight"), surface, scene._band, theme=scene.theme)
    inks = {m.get_fill_color().to_hex() for row in scene._lines for m in row.family_members_with_points()}
    assert "#AA22FF" not in inks and 0.07 <= scene._band <= 0.12
    assert all(_contrast(ink, behind) >= 4.5 for ink in inks for behind in (surface, band))


@pytest.mark.render
@pytest.mark.slow
def test_vertical_listing_wraps_with_its_numbers(make_project, media: Path) -> None:
    code = "\n".join(f"result_{k} = compute_something(argument_one, argument_two, k={k})" for k in range(1, 9))
    spec = {"id": "w", "type": "code_walkthrough", "params": {"code": code, "steps": ["3-4"]}, "beats": [{"text": "one two"}]}
    scene = render(load(make_project, [spec], format={"width": 1080, "height": 1920}), "w", media, size=(90, 160))
    assert scene._rows > 8                                    # wrapped
    labels = [n for n in scene._numbers if len(n)]
    assert len(labels) == 8                                   # one number per line
    rows = [j for n in (3, 4) for j in scene._groups[n - 1]]
    assert len(rows) > 2 and set(rows) == set(scene._views[0].chosen)
    longest = max(len(line) for line in scene._paragraphs[0][2])
    assert longest >= 26                                      # not the ~20 columns the requested size gave


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
@pytest.mark.slow
def test_silent_scene_and_duration(make_project, media: Path, size: tuple[int, int]) -> None:
    project = load(make_project, [{"id": "s", "type": "code_walkthrough", "params": {"code": LONG, "steps": ["3", "25"]}, "duration": 2.0},
                                  scroll_scene(steps=["1", "20-22", "29"])])
    scene, duration, _ = render_scene(project, "w", media, *size)
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    silent, duration, _ = render_scene(project, "s", media, *size)
    assert duration == pytest.approx(2.0, abs=1.5 / FPS) and silent.mobjects == []
