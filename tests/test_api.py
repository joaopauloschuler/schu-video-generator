"""The ``vidgen.api`` star-import surface and the theme-aware helpers."""

from __future__ import annotations

import pytest

from conftest import minimal_config
from vidgen import api, runtime
from vidgen.errors import VidgenError
from vidgen.project import Project

DESIGN_NAMES = {
    "NarratedScene",
    "SceneParams",
    "scene",
    "hook",
    "HookContext",
    "register_theme_defaults",
    "current_theme",
    "current_project",
    "T",
    "MT",
    "column",
    "edges",
    "dense_pairs",
    "grouped_pairs",
    "counter",
}


def star_import() -> dict:
    ns: dict = {}
    exec("from vidgen.api import *", ns)
    return ns


def test_star_import_has_vidgen_and_manim_names() -> None:
    ns = star_import()
    assert DESIGN_NAMES <= set(ns)
    for name in api.VIDGEN_NAMES:
        assert ns[name] is getattr(api, name)
    for manim_name in ("Scene", "Text", "Circle", "FadeIn", "VGroup", "UP", "BOLD", "config", "np", "ValueTracker"):
        assert manim_name in ns


def test_only_collision_is_scene_and_vidgen_wins() -> None:
    import manim

    assert api.SHADOWED_MANIM_NAMES == {"scene"}
    ns = star_import()
    assert ns["scene"] is not manim.scene and callable(ns["scene"])
    assert ns["scene"].__module__ == "vidgen.registry"


def test_all_is_consistent() -> None:
    assert len(api.__all__) == len(set(api.__all__))
    assert all(hasattr(api, name) for name in api.__all__)
    assert not [n for n in api.__all__ if n.startswith("_")]


def glyph_color(text) -> str:
    return text[0].get_fill_color().to_hex().upper()


@pytest.fixture
def active(make_project) -> Project:
    project = Project.load(make_project(minimal_config(theme={"colors": {"accent": "#123456"}, "sizes": {"body": 30}})))
    runtime.set_context(project)
    return project


def test_text_helpers_use_current_theme(active: Project) -> None:
    t = api.T("Hi")
    assert t.font_size == pytest.approx(30)
    assert glyph_color(t) == "#E8EAED"
    m = api.MT("10<sup>22</sup>", "title", "accent", weight=api.BOLD)
    assert m.font_size == pytest.approx(56)
    assert glyph_color(m) == "#123456"
    assert glyph_color(api.T("x", 20, "#FF0000")) == "#FF0000"
    assert glyph_color(api.T("x", color=api.RED)) == api.RED.to_hex().upper()


def test_text_helpers_need_context() -> None:
    with pytest.raises(VidgenError, match="no active vidgen theme"):
        api.T("x")


def test_unknown_token_errors(active: Project) -> None:
    with pytest.raises(VidgenError, match="unknown theme color 'nope'"):
        api.T("x", color="nope")


def test_register_theme_defaults_api(active: Project) -> None:
    api.register_theme_defaults({"k2": "#F2A541", "accent": "#000000"}, sizes={"huge": 90})
    theme = api.current_theme()
    assert theme.color("k2") == "#F2A541" and theme.color("accent") == "#123456" and theme.size("huge") == 90


def test_drawing_helpers(active: Project) -> None:
    col = api.column(5, x=-2, gap=0.5, y0=1.0, color="accent")
    assert len(col) == 5
    assert col[0].get_center()[1] == pytest.approx(2.0) and col[4].get_center()[1] == pytest.approx(0.0)
    assert col[0].get_color().to_hex().upper() == "#123456"
    other = api.column(5, x=2, gap=0.5)
    assert api.dense_pairs(2, 3) == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
    assert api.grouped_pairs(4, 2) == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 2), (2, 3), (3, 2), (3, 3)]
    lines = api.edges(col, other, api.grouped_pairs(4, 2))
    assert len(lines) == 8
    assert lines[0].get_color().to_hex().upper() == "#58C4DD"  # default "primary"


def test_drawing_helpers_extensions(active: Project) -> None:
    row = api.column(3, x=1.0, gap=0.5, y0=-1.0, horizontal=True)
    assert [round(d.get_x(), 6) for d in row] == [0.5, 1.0, 1.5] and all(d.get_y() == pytest.approx(-1.0) for d in row)
    holed = api.column(4, x=0, gap=1.0, skip=2)   # 5 slots, the third left empty
    assert [round(d.get_y(), 6) for d in holed] == [2.0, 1.0, -1.0, -2.0]
    assert api.grouped_pairs(9, 3) == [(g * 3 + i, g * 3 + j) for g in range(3) for i in range(3) for j in range(3)]
    assert api.grouped_pairs(5, 2, 4) == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 2), (2, 3), (3, 2), (3, 3), (4, 2), (4, 3)]
    assert api.group_bounds(5, 2) == [0, 2, 5]
    sparse = api.sparse_pairs(6, 5, 0.3, seed=1)
    assert sparse == api.sparse_pairs(6, 5, 0.3, seed=1) and sparse == sorted(sparse)
    assert {i for i, _ in sparse} == set(range(6)) and {j for _, j in sparse} == set(range(5))
    assert len(sparse) < 30
    a, b = api.column(2, x=0, gap=1.0), api.column(2, x=2, gap=1.0)
    lines = api.edges(a, b, [(0, 0), (1, 1)], colors=["accent", "text"], shorten=0.25)
    assert lines[0].get_start()[0] == pytest.approx(0.25) and lines[0].get_end()[0] == pytest.approx(1.75)
    assert lines[0].get_color().to_hex().upper() == "#123456"


def test_counter_redraws(active: Project) -> None:
    tracker = api.ValueTracker(100)
    label = api.Dot([0, -2, 0])
    num = api.counter(tracker, "{:.0f}%", anchor=lambda: label, edge=api.UP)
    wide = num.width  # "100%"
    tracker.set_value(23)
    num.update()
    assert num.width < wide * 0.9  # "23%"
    assert num.get_bottom()[1] > label.get_top()[1]
    assert num.get_center()[0] == pytest.approx(0, abs=1e-6)
