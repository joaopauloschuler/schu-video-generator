"""Step 37 (review 2): text on filled shapes under dim / highlight, decorations that follow their
target, ``until`` keeping a scene's own dimming, header synonyms (``title`` / ``heading``),
unknown-key messages, single-item lists, the copy-free fade, portrait growth and the 9:16 world
map (DESIGN.md §40)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import Square, VGroup

from conftest import minimal_config
from test_actions import alpha, beats, render
from test_actions_coverage import NARRATION, with_picture
from vidgen import extensions, registry, schema
from vidgen.charts import mix_colors, text_color_on
from vidgen.cli import main, project_problems
from vidgen.config import ThemeConfig
from vidgen.helpers import Fade, fade_out
from vidgen.lint.color import contrast_ratio, hex_rgb
from vidgen.project import Project
from vidgen.theme import Theme


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


def load(make_project, scenes: list[dict[str, Any]]) -> Project:
    return Project.load(with_picture(make_project(minimal_config(scenes=scenes, narration=NARRATION))))


def hex_of(mob: Any) -> str:
    return mob.family_members_with_points()[0].get_fill_color().to_hex().upper()


def same(a: str, b: str) -> bool:
    """Equal colours, give or take rounding (one step per channel)."""
    return bool(np.all(np.abs(np.array(hex_rgb(a)) - np.array(hex_rgb(b))) <= 1.5 / 255))


def cls_of(name: str) -> Any:
    extensions.load_builtins()
    return registry.get(name).cls


# ----- text on filled shapes ------------------------------------------------------------------------


@pytest.mark.render
def test_dim_recolours_text_on_a_slice_and_until_restores_it(make_project, media: Path) -> None:
    pie = {"labels": ["Alpha", "Beta"], "values": [70, 30]}
    project = load(make_project, [
        {"id": "p", "type": "pie", "params": pie, "beats": beats([{"dim": "slice1", "until": "p_b2"}], None)},
        {"id": "q", "type": "pie", "params": pie, "beats": beats([{"dim": "slice1"}])},
    ])
    kept = render(project, "q", media)
    assert 0 in kept._inside
    wedge, label = kept._wedges[0], kept._labels[0]
    seen = mix_colors(kept.theme.palette_color(0), kept.theme.background, alpha(wedge))
    assert same(hex_of(label), text_color_on(seen, theme=kept.theme))   # readable on the dimmed slice
    assert alpha(label) == pytest.approx(0.7, abs=0.02) and alpha(wedge) == pytest.approx(0.45, abs=0.02)
    undone = render(project, "p", media)
    assert same(hex_of(undone._labels[0]), text_color_on(undone.theme.palette_color(0), theme=undone.theme))
    assert alpha(undone._labels[0]) == pytest.approx(1.0) and alpha(undone._wedges[0]) == pytest.approx(1.0)


@pytest.mark.render
def test_highlight_colour_keeps_a_callout_label_readable(make_project, media: Path) -> None:
    steps = [{"box": [0.1, 0.1, 0.3, 0.3], "label": "Box"}]
    project = load(make_project, [{"id": "s", "type": "screenshot", "params": {"path": "assets/pic.png", "steps": steps},
                                   "beats": beats([{"highlight": "callout1", "color": "accent", "at": 0.3}])}])
    scene = render(project, "s", media)
    tag = scene.find_targets("callout1")[0].mobject.tag
    plate, ink = scene.theme.color("accent"), hex_of(tag.text)
    assert same(hex_of(tag.plate), plate) and not same(ink, plate)
    assert contrast_ratio(hex_rgb(ink), hex_rgb(plate)) >= 4.5


@pytest.mark.render
def test_heatmap_values_stay_readable_under_dim_and_fill(make_project, media: Path) -> None:
    params = {"rows": ["a", "b"], "columns": ["x", "y"], "values": [[1, 2], [3, 9]]}
    project = load(make_project, [{"id": "h", "type": "heatmap", "params": params,
                                   "beats": beats([{"dim": "row1"}, {"highlight": "col2", "style": "fill"}])}])
    scene = render(project, "h", media)
    bg = scene.theme.background
    for r, c in ((0, 0), (0, 1)):   # dimmed row: values readable on the faded cells
        cell, text = scene._cells_[r][c], scene._texts[r][c]
        seen = mix_colors(hex_of(cell), bg, alpha(cell))
        assert contrast_ratio(hex_rgb(hex_of(text)), hex_rgb(seen)) >= 4.5
    cell, text = scene._cells_[1][1], scene._texts[1][1]   # under the fill plate
    tinted = mix_colors(scene.theme.color("highlight"), hex_of(cell), 0.22)
    assert same(hex_of(text), text_color_on(tinted, theme=scene.theme))


# ----- decorations follow their target; until keeps the scene's dimming ----------------------------


@pytest.mark.render
@pytest.mark.slow
def test_highlight_box_follows_a_scrolling_line_and_fades_with_it(make_project, media: Path) -> None:
    code = "\n".join(f"x{k} = {k}" for k in range(1, 31))
    params = {"code": code, "visible": 6, "steps": [{"lines": "2-3"}, {"lines": "24-25"}]}
    project = load(make_project, [{"id": "w", "type": "code_walkthrough", "params": params,
                                   "beats": beats([{"highlight": "line3", "style": "box"}, {"highlight": "line5", "style": "underline"}], None)}])
    scene = render(project, "w", media)
    boxes = [m for m in scene.mobjects if type(m).__name__ == "SurroundingRectangle" and m.get_stroke_width() > 0]
    lines = [m for m in scene.mobjects if type(m).__name__ == "Underline"]
    assert len(boxes) == 1 and len(lines) == 1
    row = scene.find_targets("line3")[0].mobject
    assert np.allclose(boxes[0].get_center()[:2], row.get_center()[:2], atol=0.02)   # moved with the scroll
    assert boxes[0].get_stroke_opacity() < 0.05   # and faded with the row, out of the window


@pytest.mark.render
def test_undoing_a_dim_keeps_the_scenes_own_dimming(make_project, media: Path) -> None:
    params = {"items": ["one", "two", "three"], "dim_previous": True}
    project = load(make_project, [{"id": "b", "type": "bullets", "params": params,
                                   "beats": beats([{"dim": "item1", "until": "b_b3"}], None, None)}])
    scene = render(project, "b", media)
    item1 = scene.find_targets("item1")[0]
    assert item1.scene_dim == pytest.approx(scene.dimmed_opacity)
    assert alpha(item1.mobject[-1]) == pytest.approx(scene.dimmed_opacity, abs=0.01)   # not back to full


# ----- header synonyms, unknown keys, single items -------------------------------------------------


def test_header_band_answers_to_title_and_heading() -> None:
    bullets, table, chapter = cls_of("bullets"), cls_of("table"), cls_of("chapter")
    p = bullets.validate_params({"title": "Steps", "title_size": "title", "items": ["a"]}, Theme())
    assert (p.heading, p.heading_size) == ("Steps", "title")
    assert table.validate_params({"heading": "Formats", "rows": [["a"]]}, Theme()).title == "Formats"
    with pytest.raises(Exception, match="Extra inputs"):   # title is chapter's own text: no synonym
        chapter.validate_params({"title": "A", "heading": "B"}, Theme())


def test_synonyms_in_messages_targets_schema_and_list_scenes(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    both = {"id": "a", "type": "bullets", "params": {"title": "x", "heading": "y", "items": ["a"]}, "beats": beats(None)}
    target = {"id": "b", "type": "bullets", "params": {"heading": "H", "items": ["a"]}, "beats": beats([{"highlight": "title"}])}
    problems = {p.location: p.message for p in project_problems(load(make_project, [both, target]))}
    assert problems == {"scenes[0].params.title": "'title' is another name for 'heading', which is given too; keep one"}
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.params_schema(registry.get("bullets"), [Theme()])
    assert doc["properties"]["title"]["description"] == "Another name for heading."
    assert {"required": ["heading", "title"]} in doc["not"]["anyOf"]
    assert main(["list-scenes", "--json"]) == 0
    types = {t["name"]: t for t in json.loads(capsys.readouterr().out)["scene_types"]}
    fields = {f["name"]: f for f in types["bar_chart"]["params"]}
    assert fields["title"]["aliases"] == ["heading"] and fields["labels"]["aliases"] == []


@pytest.mark.render
def test_title_target_selects_a_heading(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "b", "type": "bullets", "params": {"heading": "H", "items": ["a"]},
                                   "beats": beats([{"highlight": "title", "style": "box"}])}])
    scene = render(project, "b", media)
    assert [t.name for t in scene.find_targets("title")] == ["heading"]


def test_list_params_take_a_single_item() -> None:
    scatter = cls_of("scatter").validate_params({"series": {"a": [[1, 2, "p"]]}, "highlight": "p"}, Theme())
    histogram = cls_of("histogram").validate_params({"values": [1, 2, 3], "highlight": 2}, Theme())
    diagram = cls_of("diagram").validate_params({"nodes": ["a", "b"], "edges": ["a -> b"], "highlight": "a"}, Theme())
    assert (scatter.highlight, histogram.highlight, diagram.highlight) == (["p"], [2], ["a"])


# ----- the copy-free fade ---------------------------------------------------------------------------


def test_fade_animates_colours_without_copying(monkeypatch: pytest.MonkeyPatch) -> None:
    group = VGroup(Square().set_fill("#336699", 0.8), Square().shift([2, 0, 0]))
    monkeypatch.setattr(type(group), "copy", lambda self: pytest.fail("copied"))
    fade = Fade(group, shift=[0.0, 1.0, 0.0])
    start = group.get_center().copy()
    fade.begin()
    assert group[0].get_fill_opacity() == 0 and np.allclose(group.get_center(), start - [0, 1, 0])
    fade.interpolate(1.0)
    assert group[0].get_fill_opacity() == pytest.approx(0.8) and np.allclose(group.get_center(), start)
    out = fade_out(group)
    assert isinstance(out, Fade) and out.remover
    out.begin()
    out.interpolate(0.5)
    assert group[0].get_fill_opacity() == pytest.approx(0.4, abs=0.05)


# ----- portrait layouts -----------------------------------------------------------------------------


@pytest.mark.render
def test_portrait_lists_grow_into_the_tall_frame(make_project, media: Path) -> None:
    process = {"stages": ["Plan", "Build", "Ship"]}
    comparison = {"columns": [{"heading": "A", "points": ["fast"]}, {"heading": "B", "points": ["slow"]}]}
    project = load(make_project, [{"id": "p", "type": "process", "params": process, "duration": 1.0},
                                  {"id": "c", "type": "comparison", "params": comparison, "duration": 1.0}])
    tall = render(project, "p", media, size=(90, 160))
    assert tall.plan.layout == "column" and tall.plan.factor > tall.growth
    wide, narrow = render(project, "c", media), render(project, "c", media, size=(90, 160))
    point = lambda s: s.find_targets("col1.item1")[0].mobject[-1].height / s.frame_height   # noqa: E731
    assert point(narrow) > point(wide) * 1.2


@pytest.mark.render
def test_portrait_world_map_keeps_the_longitudes_of_its_items(make_project, media: Path) -> None:
    params = {"view": "world", "countries": ["Brazil", "Mexico", "Spain"]}
    project = load(make_project, [{"id": "m", "type": "map", "params": params, "duration": 1.0}])
    wide, tall = render(project, "m", media), render(project, "m", media, size=(90, 160))
    assert wide._view.box[2] - wide._view.box[0] == pytest.approx(360.0)
    assert tall._view.box[2] - tall._view.box[0] < 200.0
    assert tall._view.region.width == pytest.approx(8 - 2 * tall.margin_x)   # as wide as the 9:16 safe area


@pytest.mark.render
def test_a_box_round_a_guide_outline_stays(make_project, media: Path) -> None:
    columns = [{"heading": "A", "points": ["fast"]}, {"heading": "B", "points": ["slow"]}]
    project = load(make_project, [{"id": "c", "type": "comparison", "params": {"columns": columns, "verdict": "A"},
                                   "beats": beats([{"highlight": "col1", "style": "box"}], None)}])
    scene = render(project, "c", media)   # beat 2 plays the verdict: the box (round a guide) stays
    boxes = [m for m in scene.mobjects if type(m).__name__ == "SurroundingRectangle"]
    assert len(boxes) == 1 and boxes[0].get_stroke_opacity() == pytest.approx(1.0)


# ----- icon sheets in a theme's colours -------------------------------------------------------------


@pytest.mark.render
def test_icon_sheet_in_theme_colours(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from PIL import Image

    sheet = tmp_path / "icons.png"
    assert main(["list-icons", "--search", "rocket", "--sheet", str(sheet), "--theme", "warm_editorial"]) == 0
    theme = Theme().derive(ThemeConfig(preset="warm_editorial"))
    image = Image.open(sheet).convert("RGB")
    assert image.getpixel((2, 2)) == tuple(round(c * 255) for c in hex_rgb(theme.background))
    colors = {c for _, c in image.getcolors(1 << 20)}
    assert tuple(round(c * 255) for c in hex_rgb(theme.color("primary"))) in colors   # the icon's strokes
    assert main(["list-icons", "--search", "rocket", "--theme"]) == 1
    assert "add --sheet PNG" in capsys.readouterr().err
