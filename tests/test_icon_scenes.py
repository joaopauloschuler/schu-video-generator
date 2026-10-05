"""Icons in built-in scenes (Step 21): ``grid_shape``, ``icon:`` on ``bullets`` items, ``title``
and ``end_card``, and the ``icon_grid`` scene, at 16:9, 9:16 and with the ``large`` type scale."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pytest
import yaml
from manim import VGroup, tempconfig
from pydantic import ValidationError

from conftest import minimal_config
from vidgen import extensions, registry
from vidgen.errors import VidgenError
from vidgen.icon_mobject import Icon, icon
from vidgen.layout import shrink_to_fit
from vidgen.project import Project
from vidgen.regions import Region, grid_shape, place
from vidgen.render.worker import frame_size
from vidgen.schema import params_schema
from vidgen.theme import Theme

SIZES = {"landscape": (160, 90), "portrait": (90, 160)}


def cls_of(name: str) -> Any:
    extensions.load_builtins()
    return registry.get(name).cls


# ----- grid_shape ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "aspect", "shape"),
    [
        (1, 1.78, (1, 1)),
        (3, 2.3, (1, 3)),
        (4, 2.3, (1, 4)),  # a wide band: one row
        (6, 2.3, (2, 3)),
        (8, 2.3, (2, 4)),
        (12, 1.78, (2, 6)),  # ties with 3 x 4: fewer rows
        (2, 0.6, (2, 1)),  # 9:16: stacked
        (6, 0.6, (3, 2)),
        (12, 0.6, (4, 3)),
        (4, 1.0, (2, 2)),
    ],
)
def test_grid_shape_choices(n: int, aspect: float, shape: tuple[int, int]) -> None:
    rows, cols = grid_shape(n, aspect, cell_aspect=0.9)
    assert (rows, cols) == shape
    assert rows * cols >= n and (rows - 1) * cols < n  # no empty row


def test_grid_shape_options_and_errors() -> None:
    assert grid_shape(5, 3.0) == grid_shape(5, Region(0, 0, 3, 1))
    assert grid_shape(9, 4.0, max_cols=3) == (3, 3)
    assert grid_shape(6, 1.0, cell_aspect=3.0)[1] < grid_shape(6, 1.0, cell_aspect=0.3)[1]  # wide cells: fewer columns
    for bad in ({"n": 0, "aspect": 1.0}, {"n": 3, "aspect": 0.0}, {"n": 3, "aspect": 1.0, "cell_aspect": -1}):
        with pytest.raises(VidgenError):
            grid_shape(**bad)


def test_grid_shape_defaults_to_the_frame() -> None:
    with tempconfig({"pixel_width": 90, "pixel_height": 160, "frame_width": 8.0, "frame_height": 128 / 9, "verbosity": "ERROR"}):
        assert grid_shape(2) == (2, 1)
        assert grid_shape(6, "body")[0] > grid_shape(6, "body")[1]
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": 128 / 9, "frame_height": 8.0, "verbosity": "ERROR"}):
        assert grid_shape(2) == (1, 2)


def test_grid_shape_is_public() -> None:
    ns: dict[str, Any] = {}
    exec("from vidgen.api import *", ns)
    assert ns["grid_shape"] is grid_shape


# ----- icons scaled with their group ---------------------------------------------------------------


def stroke_widths(mob: Icon) -> list[float]:
    return [float(p.get_stroke_width()) for p in mob.parts if p.get_stroke_width() > 0]


def test_layout_helpers_scale_icon_strokes_with_the_group() -> None:
    ic = icon("cpu", height=1.0, theme=Theme())
    before = stroke_widths(ic)
    group = VGroup(ic)
    shrink_to_fit(group, max_width=0.5)
    assert stroke_widths(ic) == pytest.approx([w * 0.5 for w in before])
    place(group, Region(0, 0, 2, 2))  # scaled up 4x
    assert stroke_widths(ic) == pytest.approx([w * 2 for w in before])
    assert ic.box.get_fill_opacity() == 0 and ic.box.get_stroke_width() == 0
    alone = icon("cpu", height=1.0, theme=Theme())
    shrink_to_fit(alone, max_width=0.5)  # Icon.scale already scales strokes: not twice
    assert stroke_widths(alone) == pytest.approx([w * 0.5 for w in before])


# ----- params --------------------------------------------------------------------------------------


def test_bullet_items_are_strings_or_text_with_icon() -> None:
    cls = cls_of("bullets")
    p = cls.validate_params({"items": ["plain", {"text": "with icon", "icon": "home"}, {"text": "no icon"}]}, Theme())
    assert [(i.text, i.icon) for i in p.items] == [("plain", None), ("with icon", "home"), ("no icon", None)]
    with pytest.raises(ValidationError, match=r"items\.1\.icon\n.*unknown icon 'hme'; did you mean 'house'"):
        cls.validate_params({"items": ["a", {"text": "b", "icon": "hme"}]}, Theme())
    with pytest.raises(ValidationError, match=r"items\.0\.text"):
        cls.validate_params({"items": [{"icon": "home"}]}, Theme())
    with pytest.raises(ValidationError, match="Extra inputs"):
        cls.validate_params({"items": [{"text": "a", "colour": "red"}]})


def test_bullet_items_schema_accepts_both_forms() -> None:
    extensions.load_builtins()
    schema = params_schema(registry.get("bullets"), [Theme()])
    jsonschema.validate({"items": ["a", {"text": "b", "icon": "cpu"}]}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"items": [{"text": "b", "icon": "not-an-icon"}]}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"items": [""]}, schema)


ITEMS = [{"icon": "cpu", "label": "Compute"}, {"icon": "database", "label": "Storage"}, {"icon": "cloud", "label": "Cloud", "sublabel": "anywhere"}]


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"items": []}, "at least 1 item"),
        ({"items": ITEMS * 6}, "at most 16 items"),
        ({"items": [{"icon": "cpu"}]}, r"items\.0\.label"),
        ({"items": [{"icon": "nope", "label": "x"}]}, "unknown icon 'nope'"),
        ({"items": ITEMS, "groups": [[0, 1]]}, r"missing items \[2\]"),
        ({"items": ITEMS, "groups": [[0, 1], [1, 2]]}, r"items listed twice \[1\]"),
        ({"items": ITEMS, "groups": [[0, 1, 2], []]}, "every group needs at least one item"),
        ({"items": ITEMS, "groups": [[0, 1, 5]]}, r"index 5 out of range \(0\.\.2\)"),
        ({"items": ITEMS, "groups": [["Compute", "Disk"]]}, "'Disk' is not one of the labels"),
        ({"items": ITEMS, "highlight": 3}, r"highlight: index 3 out of range"),
        ({"items": ITEMS + [{"icon": "cpu", "label": "Compute"}], "highlight": "Compute"}, "names several items"),
        ({"items": ITEMS, "icon_color": "pallete"}, "unknown theme color"),
        ({"items": ITEMS, "columns": 0}, "greater than or equal to 1"),
    ],
)
def test_icon_grid_params_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls_of("icon_grid").validate_params(params, Theme())


def test_icon_grid_references_by_index_or_label() -> None:
    p = cls_of("icon_grid").validate_params({"items": ITEMS, "groups": [["Cloud"], [0, "Storage"]], "highlight": "Storage"}, Theme())
    assert [[p.item_index(r) for r in g] for g in p.groups] == [[2], [0, 1]]
    assert p.item_index(p.highlight) == 1


def test_title_and_end_card_icon_params() -> None:
    title = cls_of("title").validate_params({"title": "T", "icon": "idea", "icon_position": "left"}, Theme())
    assert (title.icon, title.icon_position, title.icon_color) == ("idea", "left", "primary")
    with pytest.raises(ValidationError, match="'above' or 'left'"):
        cls_of("title").validate_params({"title": "T", "icon": "idea", "icon_position": "below"})
    assert cls_of("end_card").validate_params({"icon": "heart"}, Theme()).icon == "heart"  # an icon alone is enough
    with pytest.raises(ValidationError, match="at least one of title, lines, logo or icon"):
        cls_of("end_card").validate_params({"icon_color": "accent"})


# ----- rendering -----------------------------------------------------------------------------------

GRID_ITEMS = [
    {"icon": "cpu", "label": "Compute", "sublabel": "GPUs and CPUs"},
    {"icon": "database", "label": "Storage"},
    {"icon": "network", "label": "Networking"},
    {"icon": "shield-check", "label": "Security", "sublabel": "zero trust"},
    {"icon": "gauge", "label": "Monitoring"},
    {"icon": "bot", "label": "Automation"},
    {"icon": "cloud", "label": "Cloud"},
    {"icon": "globe", "label": "Edge"},
    {"icon": "lock", "label": "Secrets"},
    {"icon": "terminal", "label": "Shell"},
    {"icon": "git-branch", "label": "Versions"},
    {"icon": "bug", "label": "Debugging"},
]
BEATS = [{"text": "one two"}, {"text": "three four"}]


@pytest.fixture(scope="module")
def icon_project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    root = tmp_path_factory.mktemp("icon_scenes")
    scenes: list[dict[str, Any]] = [
        {"id": f"grid{n}", "type": "icon_grid", "params": {"heading": "Heading", "items": GRID_ITEMS[:n]}, "beats": BEATS}
        for n in (2, 3, 5, 12)
    ]
    scenes += [
        {
            "id": "focus",
            "type": "icon_grid",
            "params": {"items": GRID_ITEMS[:4], "icon_color": "palette", "highlight": "Security", "groups": [[0, 1], [2, 3]]},
            "beats": BEATS + [{"text": "five six"}],
        },
        {"id": "plain", "type": "icon_grid", "params": {"items": GRID_ITEMS[:6], "badge": False, "columns": 2, "reveal": "all"}, "duration": 1.0},
        {
            "id": "list",
            "type": "bullets",
            "params": {
                "heading": "Why",
                "dim_previous": True,
                "items": [{"text": "Fast previews", "icon": "zap"}, "A plain bullet", {"text": "Secure by default, keys are never stored", "icon": "shield-check"}],
            },
            "beats": BEATS + [{"text": "five six"}],
        },
        {
            "id": "numbered",
            "type": "bullets",
            "params": {"numbered": True, "items": [{"text": "Write", "icon": "pencil"}, {"text": "Render", "icon": "play"}]},
            "beats": BEATS,
        },
        {"id": "above", "type": "title", "params": {"title": "A title", "kicker": "K", "icon": "lightbulb"}, "beats": BEATS},
        {"id": "beside", "type": "title", "params": {"title": "A title", "subtitle": "sub", "icon": "rocket", "icon_position": "left"}, "beats": BEATS},
        {"id": "outro", "type": "end_card", "params": {"title": "Thanks", "icon": "heart", "lines": ["example.com"]}, "beats": BEATS},
    ]
    data = minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 4.0}, variants={"large": {"theme": {"scale": "large"}}})
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return Project.load(root)


def render_unfaded(project: Project, scene_id: str, media: Path, size: tuple[int, int]) -> Any:
    """Render a scene in-process without its final fade-out; returns the scene."""
    w, h = size
    fw, fh = frame_size(w, h)
    settings = {
        "pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": 5,
        "media_dir": str(media), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR",
        "output_file": f"{scene_id}_{w}x{h}",
    }
    with tempconfig(settings):
        spec = project.scene(scene_id)
        theme = extensions.activate(project)
        scene = registry.get(spec.type).cls(spec, project, theme)
        scene.finish = lambda: None
        scene.render()
        scene.layout_safe = scene.safe_area  # while the frame is still configured
        return scene


def icons_in(scene: Any) -> list[Icon]:
    return [m for top in scene.mobjects for m in top.get_family() if isinstance(m, Icon)]


def grid_cells(scene: Any) -> list[Any]:
    """The cells of an icon grid on screen: VGroup(visual, label, sublabel?)."""
    cells = [m for top in scene.mobjects for m in top.get_family() if isinstance(m, VGroup) and len(m) >= 2 and isinstance(m[0], VGroup) and any(isinstance(x, Icon) for x in m[0].get_family())]
    return [c for c in cells if not any(c is not o and c in o.get_family() for o in cells)]


def boxes_overlap(a: Any, b: Any, eps: float = 1e-3) -> bool:
    return bool(
        a.get_left()[0] < b.get_right()[0] - eps and b.get_left()[0] < a.get_right()[0] - eps
        and a.get_bottom()[1] < b.get_top()[1] - eps and b.get_bottom()[1] < a.get_top()[1] - eps
    )


@pytest.mark.render
@pytest.mark.parametrize("variant", [None, "large"])
@pytest.mark.parametrize("orient", ["landscape", "portrait"])
@pytest.mark.parametrize("n", [2, 5, 12])
def test_icon_grid_fits_without_overlap(icon_project: Project, tmp_path: Path, n: int, orient: str, variant: str | None) -> None:
    project = Project.load(icon_project.root, variant=variant)
    scene = render_unfaded(project, f"grid{n}", tmp_path, SIZES[orient])
    cells = grid_cells(scene)
    assert len(cells) == n
    for mob in scene.mobjects:
        assert scene.layout_safe.contains(mob, tolerance=0.02), (n, orient, variant)
    for i, a in enumerate(cells):
        for b in cells[i + 1 :]:
            assert not boxes_overlap(a, b), (n, orient, variant)
    # one label size: single-line labels with capitals and no descenders are equally tall
    # one label size: the capitals of every label are equally tall
    caps = [c[1][0][0].height for c in cells]  # first glyph of the first line (a capital)
    assert max(caps) / min(caps) < 1.05, (n, orient, variant)
    # icons are on screen and drawn (not only their invisible boxes)
    assert all(ic.box.get_fill_opacity() == 0 for ic in icons_in(scene))
    assert len(icons_in(scene)) == n


@pytest.mark.render
def test_icon_grid_rows_follow_the_frame(icon_project: Project, tmp_path: Path) -> None:
    def rows(scene: Any) -> int:
        return len({round(float(c[0].get_y()), 2) for c in grid_cells(scene)})

    assert rows(render_unfaded(icon_project, "grid3", tmp_path, SIZES["landscape"])) == 1
    assert rows(render_unfaded(icon_project, "grid3", tmp_path, SIZES["portrait"])) >= 2
    plain = render_unfaded(icon_project, "plain", tmp_path, SIZES["landscape"])
    assert rows(plain) == 3  # columns: 2
    assert all(len(c[0]) == 1 and isinstance(c[0][0], Icon) for c in grid_cells(plain))  # badge: false, no disc


@pytest.mark.render
def test_icon_grid_palette_and_highlight(icon_project: Project, tmp_path: Path) -> None:
    scene = render_unfaded(icon_project, "focus", tmp_path, SIZES["landscape"])
    theme = scene.theme
    cells = grid_cells(scene)
    icons = [next(m for m in c[0].get_family() if isinstance(m, Icon)) for c in cells]
    stroke = [ic.parts[0].get_stroke_color().to_hex().upper() for ic in icons]
    assert stroke[3] == theme.color("highlight").upper()  # highlighted
    assert stroke[:3] == [theme.palette_color(i).upper() for i in range(3)]
    # the others are dimmed; their icon boxes stay invisible
    assert cells[0][1][0][0].get_fill_opacity() == pytest.approx(scene.dimmed_opacity, abs=0.02)  # a glyph
    assert cells[3][1][0][0].get_fill_opacity() == pytest.approx(1.0)
    assert all(ic.box.get_fill_opacity() == 0 for ic in icons)
    assert cells[3][0].width > cells[2][0].width * 1.1  # the chosen one grew


@pytest.mark.render
@pytest.mark.parametrize("orient", ["landscape", "portrait"])
def test_bullet_icons_align_with_the_first_line(icon_project: Project, tmp_path: Path, orient: str) -> None:
    scene = render_unfaded(icon_project, "list", tmp_path, SIZES[orient])
    rows = [m for m in scene.mobjects if isinstance(m, VGroup) and not isinstance(m, Icon) and len(m) == 2]
    assert len(rows) == 3
    for row in (rows[0], rows[2]):
        ic, text = row
        assert isinstance(ic, Icon) and ic.icon_name in ("zap", "shield-check")
        assert ic.get_right()[0] < text.get_left()[0]  # in the column left of the text
        first = text[0]
        assert abs(ic.get_y() - first.get_y()) < first.height * 0.6  # centred on the first line
    marker = rows[1][0]
    assert type(marker).__name__ == "Text"
    assert abs(marker.get_x() - rows[0][0].get_x()) < 0.05  # a bullet among icons sits in their column
    # all texts start at one x; dim_previous faded earlier rows, icon boxes stay invisible
    assert len({round(float(r[1].get_left()[0]), 3) for r in rows}) == 1
    zap = rows[0][0]
    assert zap.parts[0].get_stroke_opacity() == pytest.approx(scene.dimmed_opacity, abs=0.02)
    assert zap.box.get_fill_opacity() == 0 and zap.box.get_stroke_opacity() == 0
    assert scene.layout_safe.contains(VGroup(*rows), tolerance=0.02)


@pytest.mark.render
def test_numbered_bullets_put_the_icon_between_number_and_text(icon_project: Project, tmp_path: Path) -> None:
    scene = render_unfaded(icon_project, "numbered", tmp_path, SIZES["landscape"])
    rows = [m for m in scene.mobjects if isinstance(m, VGroup) and len(m) == 3]
    assert len(rows) == 2
    for number, ic, text in rows:
        assert isinstance(ic, Icon)
        assert number.get_right()[0] < ic.get_left()[0] and ic.get_right()[0] < text.get_left()[0]


@pytest.mark.render
@pytest.mark.parametrize("orient", ["landscape", "portrait"])
def test_title_and_end_card_icons(icon_project: Project, tmp_path: Path, orient: str) -> None:
    above = render_unfaded(icon_project, "above", tmp_path, SIZES[orient])
    (ic,) = icons_in(above)
    texts = [m for top in above.mobjects for m in top.get_family() if type(m).__name__ == "Paragraph"]
    assert ic.get_bottom()[1] > max(t.get_top()[1] for t in texts) - 1e-6  # above kicker and title
    beside = render_unfaded(icon_project, "beside", tmp_path, SIZES[orient])
    (ic,) = icons_in(beside)
    texts = VGroup(*[m for top in beside.mobjects for m in top.get_family() if type(m).__name__ == "Paragraph"])
    title = texts[0]
    if orient == "landscape":
        assert ic.get_right()[0] < title.get_left()[0]
        assert abs(ic.get_y() - texts.get_y()) < 0.3  # level with the title block
    else:  # no room beside it in a vertical frame: above
        assert ic.get_bottom()[1] > title.get_top()[1]
    outro = render_unfaded(icon_project, "outro", tmp_path, SIZES[orient])
    (ic,) = icons_in(outro)
    title = next(m for top in outro.mobjects for m in top.get_family() if type(m).__name__ == "Paragraph")
    assert ic.get_bottom()[1] > title.get_top()[1] and ic.parts[0].get_stroke_color().to_hex().upper() == outro.theme.color("primary").upper()
    for scene in (above, beside, outro):
        for mob in scene.mobjects:
            assert scene.layout_safe.contains(mob, tolerance=0.02)
            assert np.isfinite(mob.get_center()).all()
