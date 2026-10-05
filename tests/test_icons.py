"""Icons (Step 19): vendored set + manifest, project icons, search, the `icon()` mobject, the
`IconName` param type, `vidgen list-icons`, layout dump and lint, the vendoring tool."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from manim import Camera, Text, tempconfig
from manim.constants import CapStyleType, LineJointType
from PIL import Image
from pydantic import ValidationError

from conftest import minimal_config, write_files
from test_introspect import FakeScene, objects, small_config  # noqa: F401 - fixture
from vidgen import icons as icons_mod
from vidgen.cli import check_project, main
from vidgen.errors import VidgenError
from vidgen.extensions import project_session
from vidgen.icon_mobject import ICON_UNITS_PER_POINT, Icon, build_icon, icon
from vidgen.icons import (
    CATEGORIES,
    ICONS_DIR,
    available_icons,
    builtin_icons,
    builtin_sources,
    find_icon,
    search_icons,
    unknown_icon_message,
)
from vidgen.project import Project
from vidgen.scene import IconName, SceneParams
from vidgen.theme import Theme

REPO = Path(__file__).resolve().parents[1]
ICON_SET = json.loads((REPO / "tools" / "icon_set.json").read_text(encoding="utf-8"))

PROJECT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 24" fill="none" stroke="currentColor"
  stroke-width="4" stroke-linecap="butt" stroke-linejoin="bevel">
  <path d="M4 12h40" />
  <circle cx="24" cy="12" r="4" fill="#FF0000" stroke="none" />
</svg>
"""


def project_with_icons(make_project: Any, files: dict[str, str], **config: Any) -> Path:
    root = make_project(minimal_config(**config))
    write_files(root, files)
    return root


# ----- vendored set ----------------------------------------------------------------------------------


def test_seed_set_matches_the_icon_list() -> None:
    icons = builtin_icons()
    listed = {name: cat for cat, names in ICON_SET["categories"].items() for name in names}
    assert len(icons) == 40 == len(listed)
    assert {name: info.category for name, info in icons.items()} == listed
    assert list(ICON_SET["categories"]) == list(CATEGORIES)  # every category seeded, 5 each
    assert all(len(names) == 5 for names in ICON_SET["categories"].values())
    for info in icons.values():
        assert info.path.is_file() and info.path.parent == ICONS_DIR / "lucide"
        assert info.tags and info.source == "lucide" and info.origin == "builtin"
    assert sorted(p.stem for p in (ICONS_DIR / "lucide").glob("*.svg")) == sorted(listed)
    for name, extra in ICON_SET["extra_tags"].items():
        assert set(extra) <= set(icons[name].tags)


def test_licence_and_sources() -> None:
    sources = builtin_sources()
    assert sources["lucide"]["package"] == "lucide-static" and sources["lucide"]["version"] == ICON_SET["version"]
    assert sources["lucide"]["license"] == "ISC"
    licence = (ICONS_DIR / sources["lucide"]["license_file"]).read_text(encoding="utf-8")
    assert "ISC License" in licence and "Feather" in licence
    notices = (REPO / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Lucide" in notices and ICON_SET["version"] in notices


def test_icons_are_package_data() -> None:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert '"data/icons/**/*"' in text


# ----- registry, project icons, search --------------------------------------------------------------


def test_project_icons_extend_and_override(make_project: Any) -> None:
    root = project_with_icons(
        make_project,
        {
            "assets/icons/logo.svg": PROJECT_SVG,
            "assets/icons/cpu.svg": PROJECT_SVG,
            "assets/icons/icons.json": '{"icons": [{"name": "logo", "category": "brand", "tags": ["company"]}]}',
        },
    )
    icons = available_icons(root)
    assert len(icons) == 41 and list(icons) == sorted(icons)
    logo, cpu = icons["logo"], icons["cpu"]
    assert (logo.origin, logo.category, logo.tags, logo.overrides) == ("project", "brand", ("company",), False)
    assert (cpu.origin, cpu.category, cpu.overrides, cpu.path) == ("project", "project", True, (root / "assets/icons/cpu.svg").resolve())
    assert available_icons(None)["cpu"].origin == "builtin"
    assert [i.name for i in search_icons(icons, "company")] == ["logo"]


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({"assets/icons/my icon.svg": PROJECT_SVG}, "icon names may only contain"),
        ({"assets/icons/icons.json": '{"icons": [{"name": "ghost"}]}'}, "no file assets/icons/ghost.svg"),
        ({"assets/icons/a.svg": PROJECT_SVG, "assets/icons/icons.json": '{"icons": [{"name": "a", "colour": 1}]}'}, "unknown keys colour"),
        ({"assets/icons/a.svg": PROJECT_SVG, "assets/icons/icons.json": '{"icons": [{"name": "a", "tags": "x"}]}'}, "'tags' must be a list"),
        ({"assets/icons/icons.json": "[1, 2]"}, "expected"),
        ({"assets/icons/icons.json": "{nope"}, "cannot read icon manifest"),
    ],
)
def test_bad_project_icons_are_reported(make_project: Any, files: dict[str, str], message: str) -> None:
    root = project_with_icons(make_project, files)
    with pytest.raises(VidgenError, match=message):
        available_icons(root)
    problems = check_project(Project.load(root))
    assert len(problems) == 1 and problems[0].startswith("assets/icons: ") and message.split("'")[0] in problems[0]


def test_project_icon_cache_sees_new_files(make_project: Any) -> None:
    root = project_with_icons(make_project, {"assets/icons/a.svg": PROJECT_SVG})
    assert "a" in available_icons(root) and "b" not in available_icons(root)
    (root / "assets/icons/b.svg").write_text(PROJECT_SVG, encoding="utf-8")
    assert "b" in available_icons(root)


def test_search_matches_names_tags_and_categories() -> None:
    icons = builtin_icons()
    assert [i.name for i in search_icons(icons, "chart")][:4] == ["chart-column", "chart-line", "chart-pie", "chart-scatter"]
    assert [i.name for i in search_icons(icons, "chart pie")] == ["chart-pie"]
    assert [i.name for i in search_icons(icons, "COMPUTER")] == ["cpu", "server"]  # tags, case-insensitive
    assert search_icons(icons, "user")[0].name == "user"  # exact name first
    assert {i.name for i in search_icons(icons, "nature")} >= {"leaf", "sun", "droplet", "mountain", "tree-pine"}
    assert [i.name for i in search_icons(icons, None, "data")] == ["chart-column", "chart-line", "chart-pie", "chart-scatter", "database"]
    assert search_icons(icons, "chart", "people") == [] and search_icons(icons, "zzz") == []
    assert len(search_icons(icons)) == 40


def test_unknown_icon_suggestions() -> None:
    icons = builtin_icons()
    message = unknown_icon_message("cpus", icons)
    assert message.startswith("unknown icon 'cpus'; did you mean 'cpu'?")
    assert "matching tags: cpu, server" in unknown_icon_message("computer", icons)
    assert unknown_icon_message("qqqq", icons) == "unknown icon 'qqqq' (see `vidgen list-icons --search TEXT`)"
    with pytest.raises(VidgenError, match="did you mean 'database'"):
        find_icon("databse", icons)


# ----- the Icon mobject -------------------------------------------------------------------------------


def test_icon_box_strokes_and_colour() -> None:
    mob = build_icon(builtin_icons()["cpu"], 1.2, "#FF8800")
    assert isinstance(mob, Icon) and mob.icon_name == "cpu" and mob.icon_origin == "builtin"
    assert mob.height == pytest.approx(1.2) and mob.width == pytest.approx(1.2)  # the 24x24 viewBox
    assert np.allclose(mob.get_center(), 0)
    assert mob.box.get_fill_opacity() == 0 and mob.box.get_stroke_width() == 0
    assert len(mob.parts) == 14  # cpu.svg: 12 paths + 2 rects
    expected = 2 / 24 * 1.2 / 0.01  # Lucide's 2 of 24, in Manim stroke units (0.01 frame units)
    for part in mob.parts:
        assert part.get_stroke_width() == pytest.approx(expected)
        assert part.get_stroke_color().to_hex() == "#FF8800" and part.get_fill_opacity() == 0
        assert part.cap_style == CapStyleType.ROUND and part.joint_type == LineJointType.ROUND
    mob.scale(0.5)
    assert mob.parts[0].get_stroke_width() == pytest.approx(expected / 2)  # strokes scale with the icon
    mob.scale(2, scale_stroke=False)
    assert mob.parts[0].get_stroke_width() == pytest.approx(expected / 2)
    copy = mob.copy()
    assert isinstance(copy, Icon) and copy.icon_name == "cpu"


def test_filled_parts_and_stroke_width_override() -> None:
    mob = build_icon(builtin_icons()["chart-scatter"], 2.4, "#00FF00", stroke_width=1.5)
    dots = [p for p in mob.parts if p.get_fill_opacity() > 0]
    assert len(dots) == 5 and all(p.get_fill_color().to_hex() == "#00FF00" for p in dots)
    assert all(p.get_stroke_width() == pytest.approx(1.5 / 24 * 2.4 / 0.01) for p in mob.parts)
    with pytest.raises(VidgenError, match="size must be positive"):
        build_icon(builtin_icons()["x"], 0, "#FFFFFF")
    with pytest.raises(VidgenError, match="stroke_width"):
        build_icon(builtin_icons()["x"], 1, "#FFFFFF", stroke_width=-1)


def test_project_svg_colours_kept_with_color_none(make_project: Any) -> None:
    root = project_with_icons(make_project, {"assets/icons/wide.svg": PROJECT_SVG})
    info = available_icons(root)["wide"]
    mob = build_icon(info, 1.0, None, current="#123456")
    assert mob.width == pytest.approx(2.0)  # viewBox 48 x 24
    line, dot = mob.parts
    assert line.get_stroke_color().to_hex() == "#123456" and line.get_stroke_width() == pytest.approx(4 / 24 / 0.01)
    assert dot.get_fill_color().to_hex() == "#FF0000" and dot.get_stroke_width() == 0  # stroke="none"
    assert line.cap_style == CapStyleType.BUTT and line.joint_type == LineJointType.BEVEL
    recoloured = build_icon(info, 1.0, "#FFFFFF")
    assert recoloured.parts[1].get_fill_color().to_hex() == "#FFFFFF"


@pytest.mark.parametrize(
    ("svg", "message"),
    [
        ("<svg xmlns='http://www.w3.org/2000/svg'><path d='M0 0h1'/></svg>", "cannot read the size"),
        ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 0 24'><path d='M0 0h1'/></svg>", "invalid viewBox"),
        ("<html></html>", "not an SVG file"),
        ("<svg", "cannot read icon"),
        ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'></svg>", "draws nothing"),
    ],
)
def test_bad_svg_files(make_project: Any, svg: str, message: str) -> None:
    root = project_with_icons(make_project, {"assets/icons/bad.svg": svg})
    with pytest.raises(VidgenError, match=message):
        build_icon(available_icons(root)["bad"], 1.0, "#FFFFFF")


def test_icon_helper_uses_theme_and_project(make_project: Any) -> None:
    root = project_with_icons(make_project, {"assets/icons/wide.svg": PROJECT_SVG})
    with project_session(Project.load(root)) as theme:
        body = icon("cpu")
        assert body.height == pytest.approx(theme.size("body") * ICON_UNITS_PER_POINT)
        assert body.parts[0].get_stroke_color().to_hex() == theme.color("text").upper()
        assert icon("cpu", "title", "primary").parts[0].get_stroke_color().to_hex() == theme.color("primary").upper()
        assert icon("x", 40).height == pytest.approx(40 * ICON_UNITS_PER_POINT)
        assert icon("x", height=3).height == pytest.approx(3)
        wide = icon("wide", color=None)
        assert wide.icon_origin == "project" and wide.parts[1].get_fill_color().to_hex() == "#FF0000"
        assert wide.parts[0].get_stroke_color().to_hex() == theme.color("text").upper()
        with pytest.raises(VidgenError, match="did you mean 'cpu'"):
            icon("cpuu")
    assert icon("cpu", theme=Theme()).icon_name == "cpu"  # no project: built-ins


def test_icon_matches_text_scale() -> None:
    """A ``body`` icon's box is about 1.5 em: its drawing ~1.7x the cap height of body text."""
    theme = Theme()
    cap = Text("H", font="Inter", font_size=theme.size("body")).height
    content = icon("cpu", theme=theme).parts
    drawn = max(p.get_top()[1] for p in content) - min(p.get_bottom()[1] for p in content)
    assert 1.5 < drawn / cap < 2.0


# ----- IconName params, schema, list-scenes ---------------------------------------------------------


class _IconParams(SceneParams):
    icon: IconName
    other: IconName | None = None


def test_icon_name_param(make_project: Any) -> None:
    assert _IconParams.model_validate({"icon": "anything"}).icon == "anything"  # no theme: syntax only
    with pytest.raises(ValidationError, match="invalid icon name"):
        _IconParams.model_validate({"icon": "../x"})
    with pytest.raises(ValidationError, match="did you mean 'cpu'"):
        _IconParams.model_validate({"icon": "cpuu"}, context={"theme": Theme()})
    root = project_with_icons(make_project, {"assets/icons/wide.svg": PROJECT_SVG})
    with project_session(Project.load(root)) as theme:
        assert _IconParams.model_validate({"icon": "wide", "other": "cpu"}, context={"theme": theme}).icon == "wide"
    schema = _IconParams.model_json_schema()
    assert schema["properties"]["icon"]["x-vidgen-theme"] == "icon"


def test_icon_params_in_validate_schema_and_list_scenes(make_project: Any, capsys: pytest.CaptureFixture[str]) -> None:
    extension = """
        from vidgen.api import *

        @scene("badge")
        class Badge(NarratedScene):
            class Params(SceneParams):
                symbol: IconName = "cpu"
                \"\"\"The icon.\"\"\"

            def construct(self):
                with self.narrate(0):
                    self.add(icon(self.params.symbol))
    """
    data = minimal_config()
    data["scenes"][0] = {"id": "intro", "type": "badge", "params": {"symbol": "wide"}, "beats": [{"text": "Hi."}]}
    data["scenes"][1]["type"] = "badge"
    data["scenes"][1]["params"] = {"symbol": "databse"}
    root = make_project(data)
    write_files(root, {"extensions/badge.py": extension, "assets/icons/wide.svg": PROJECT_SVG})
    problems = check_project(Project.load(root))
    assert len(problems) == 1 and problems[0].startswith("scenes[1].params.symbol: unknown icon 'databse'; did you mean 'database'?")
    assert main(["schema", str(root), "--scene", "badge"]) == 0
    doc = json.loads(capsys.readouterr().out)
    names = doc["properties"]["symbol"]["enum"]
    assert "wide" in names and "cpu" in names and len(names) == 41
    assert main(["list-scenes", str(root)]) == 0
    assert "    symbol: icon = 'cpu'" in capsys.readouterr().out


# ----- vidgen list-icons ------------------------------------------------------------------------------


def test_list_icons_text(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no config here: built-ins only
    assert main(["list-icons"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 41 and lines[-1] == "40 icons; built-in set: Lucide (lucide-static 1.52.0, ISC)"
    assert lines[0].split()[:2] == ["arrow-right", "ui"]
    assert main(["list-icons", "--search", "computer", "--category", "tech"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in out[:-1]] == ["cpu", "server"] and out[-1].startswith("2 of 40 icons")
    assert main(["list-icons", "--category", "food"]) == 1
    assert "unknown icon category 'food'; categories: tech, data, science" in capsys.readouterr().err


def test_list_icons_json_with_project(make_project: Any, capsys: pytest.CaptureFixture[str]) -> None:
    root = project_with_icons(
        make_project,
        {"assets/icons/wide.svg": PROJECT_SVG, "assets/icons/icons.json": '{"icons": [{"name": "wide", "category": "brand"}]}'},
    )
    assert main(["list-icons", str(root), "--json", "--category", "brand"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "list-icons" and doc["ok"] and doc["version"] == 1
    assert doc["project"] == str(root.resolve()) and doc["category"] == "brand" and doc["search"] is None
    assert doc["sources"]["lucide"]["version"] == "1.52.0" and doc["sheets"] == [] and doc["count"] == 1
    assert doc["icons"] == [
        {"name": "wide", "category": "brand", "tags": [], "source": "project", "origin": "project", "overrides": False,
         "path": str((root / "assets/icons/wide.svg").resolve())}
    ]
    cats = {c["name"]: c for c in doc["categories"]}
    assert list(cats)[:8] == list(CATEGORIES) and cats["brand"] == {"name": "brand", "description": "", "count": 1}
    assert cats["tech"]["count"] == 5 and cats["tech"]["description"]
    assert main(["list-icons", str(root), "--json", "--category", "food"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["message"].startswith("unknown icon category")


@pytest.mark.render
def test_list_icons_sheet(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen import iconlist

    monkeypatch.chdir(tmp_path)
    png = tmp_path / "out" / "icons.png"
    assert main(["list-icons", "--search", "chart", "--sheet", str(png)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == f"sheet: {png}"
    image = np.asarray(Image.open(png).convert("L"))
    assert image.shape[1] == iconlist.SHEET_WIDTH and image.shape[0] == iconlist.HEADER_HEIGHT + iconlist.CELL_HEIGHT
    cell = image[iconlist.HEADER_HEIGHT : iconlist.HEADER_HEIGHT + 14 + iconlist.ICON_PX + 6, : iconlist.SHEET_WIDTH // 8]
    assert (cell < 100).mean() > 0.03  # the first icon is drawn (dark strokes on white)
    blank = image[iconlist.HEADER_HEIGHT : iconlist.HEADER_HEIGHT + 90, 4 * iconlist.SHEET_WIDTH // 8 :]
    assert (blank < 250).mean() == 0  # only 4 icons: the rest of the row is empty
    # several pages: <stem>-2.png ...; pages of an earlier, longer listing are removed
    monkeypatch.setattr(iconlist, "CELL_HEIGHT", 800)
    assert main(["list-icons", "--json", "--sheet", str(png)]) == 0
    sheets = json.loads(capsys.readouterr().out)["sheets"]
    assert sheets == [str(png)] + [str(png.with_name(f"icons-{n}.png")) for n in range(2, 6)]
    assert main(["list-icons", "--category", "ui", "--sheet", str(png)]) == 0
    assert sorted(p.name for p in png.parent.iterdir()) == ["icons.png"]
    assert main(["list-icons", "--search", "zzz", "--sheet", str(png)]) == 1
    assert "no icons to draw" in capsys.readouterr().err


# ----- layout dump and lint ----------------------------------------------------------------------------


def test_layout_dump_reports_one_icon_object(small_config: None) -> None:  # noqa: F811 - fixture
    mob = build_icon(builtin_icons()["cpu"], 3.0, "#FF8800").shift([2, 0, 0])
    [item] = objects(FakeScene(mob))
    assert (item["kind"], item["class"], item["icon"], item["path"]) == ("icon", "Icon", "cpu", "Icon[0]")
    assert item["parts"] == 14 and item["fill"] is None and item["stroke"]["color"] == "#FF8800"
    width_px = item["stroke"]["width_px"]
    assert width_px == pytest.approx(2 / 24 * 3.0 * 160 / (8 * 16 / 9), abs=0.01)
    # the box is what is drawn (the invisible design box does not count): cpu spans 2..22 of 24
    px = 160 / (8 * 16 / 9)
    assert item["bbox"][2] - item["bbox"][0] == pytest.approx(20 / 24 * 3.0 * px + width_px, abs=0.2)


EXTENSION = """
from vidgen.api import *

@scene("icons")
class Icons(NarratedScene):
    def construct(self):
        label = self.text("Processing", size="heading")
        mark = icon("cpu", "heading", "primary").next_to(label, LEFT, buff=0.2)
        cover = self.text("Covered text here", size="heading").shift(DOWN * 2)
        over = icon("x", height=1.4, color="accent").move_to(cover)
        with self.narrate(0):
            self.add(label, mark, cover, over)
"""


@pytest.mark.render
def test_lint_sees_icons_as_objects(make_project: Any) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH")
    from vidgen.lint import lint_project

    data = minimal_config(preview={"width": 640, "height": 360, "fps": 5})
    data["scenes"] = [{"id": "main", "type": "icons", "beats": [{"text": "Icons beside and over text."}]}]
    root = make_project(data)
    write_files(root, {"extensions/icons.py": EXTENSION})
    result = lint_project(Project.load(root), rules=["covered_text", "text_overlap", "off_frame", "safe_area"])
    assert [(f.rule, f.objects[1]["icon"], f.objects[0]["text"]) for f in result.findings] == [
        ("covered_text", "x", "Covered text here")
    ]
    assert "icon 'x' is drawn over text 'Covered text here'" in result.findings[0].message
    assert result.findings[0].to_json()["other"]["icon"] == "x"
    layout = json.loads((Project.load(root).render_dir(True) / "layout" / "main.json").read_text(encoding="utf-8"))
    kinds = sorted((o["kind"], o.get("icon")) for o in layout["frames"][-1]["objects"])
    assert kinds == [("icon", "cpu"), ("icon", "x"), ("text", None), ("text", None)]
    data["scenes"][0]["lint_ignore"] = [{"rule": "covered_text", "object": "x"}]
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    ignored = lint_project(Project.load(root), rules=["covered_text"])
    assert ignored.findings == [] and ignored.ignored == 1


@pytest.mark.render
@pytest.mark.parametrize("size", [(480, 270), (1920, 1080)])
def test_icon_strokes_are_resolution_independent(tmp_path: Path, size: tuple[int, int]) -> None:
    """The same icon covers the same share of the frame at any resolution (strokes included)."""
    w, h = size
    with tempconfig({"pixel_width": w, "pixel_height": h, "frame_width": 8 * w / h, "frame_height": 8.0,
                     "background_color": "#000000", "media_dir": str(tmp_path)}):
        camera = Camera()
        camera.capture_mobjects([build_icon(builtin_icons()["check"], 4.0, "#FFFFFF")])
        ink = (np.asarray(camera.get_image().convert("L")) > 127).mean()
    # check.svg is one 2-unit-wide stroke 22.6 units long (+ round caps): ~47.5 of 24 x 24 units,
    # at 4/24 Manim units per unit 1.32 square units of the 14.2 x 8 frame
    assert ink == pytest.approx(47.5 * (4 / 24) ** 2 / (8 * 8 * w / h), rel=0.03)


# ----- fingerprint, API, tool --------------------------------------------------------------------------


def test_icons_count_in_the_fingerprint() -> None:
    from vidgen.render import fingerprint

    assert "iconlist.py" in fingerprint.NOT_RENDER_INPUTS
    assert "icons.py" not in fingerprint.NOT_RENDER_INPUTS and "icon_mobject.py" not in fingerprint.NOT_RENDER_INPUTS
    source = (REPO / "src" / "vidgen" / "render" / "fingerprint.py").read_text(encoding="utf-8")
    assert '"data" / "icons"' in source


def test_api_exports() -> None:
    from vidgen import api

    assert {"icon", "Icon", "IconName"} <= set(api.__all__)
    assert api.icon is icon and api.Icon is Icon


def _tool() -> Any:
    spec = importlib.util.spec_from_file_location("vendor_icons", REPO / "tools" / "vendor_icons.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_package(root: Path, names: list[str], version: str = "9.9.9") -> Path:
    package = root / "package"
    (package / "icons").mkdir(parents=True)
    for name in names:
        (package / "icons" / f"{name}.svg").write_text(PROJECT_SVG, encoding="utf-8")
    (package / "package.json").write_text(json.dumps({"version": version, "license": "ISC", "homepage": "h"}), encoding="utf-8")
    (package / "tags.json").write_text(json.dumps({"a": ["one", "two"]}), encoding="utf-8")
    (package / "LICENSE").write_text("ISC License\n", encoding="utf-8")
    return package


def test_vendor_tool(tmp_path: Path) -> None:
    tool = _tool()
    package = _fake_package(tmp_path, ["a", "b"])
    out = tmp_path / "out"
    (out / "lucide").mkdir(parents=True)
    (out / "lucide" / "stale.svg").write_text("x", encoding="utf-8")
    icon_set = {"package": "lucide-static", "version": "9.9.9", "categories": {"tech": ["a"], "data": ["b"]},
                "extra_tags": {"a": ["two", "three"]}}
    manifest = tool.vendor(package, icon_set, out, CATEGORIES)
    assert sorted(p.name for p in (out / "lucide").iterdir()) == ["LICENSE", "a.svg", "b.svg"]
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8")) == manifest
    assert manifest["icons"] == [
        {"name": "a", "category": "tech", "tags": ["one", "two", "three"], "source": "lucide"},
        {"name": "b", "category": "data", "tags": [], "source": "lucide"},
    ]
    assert manifest["sources"]["lucide"] == {"package": "lucide-static", "version": "9.9.9", "license": "ISC",
                                             "license_file": "lucide/LICENSE", "homepage": "h"}
    for broken, message in [
        ({**icon_set, "version": "1.0"}, "differs"),
        ({**icon_set, "categories": {"food": ["a"]}}, "unknown category"),
        ({**icon_set, "categories": {"tech": ["a", "zz"]}}, "not in lucide-static"),
        ({**icon_set, "categories": {"tech": ["a"], "data": ["a"]}}, "listed twice"),
        ({**icon_set, "categories": {"tech": ["b"]}}, "extra_tags for icons not listed: a"),
    ]:
        with pytest.raises(SystemExit, match=message):
            tool.build_manifest(package, broken, CATEGORIES)


def test_vendored_manifest_is_what_the_tool_writes() -> None:
    """The committed manifest equals the tool's output for tools/icon_set.json (no hand edits)."""
    manifest = json.loads((ICONS_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == 1 and set(manifest) == {"version", "sources", "icons"}
    assert [e["name"] for e in manifest["icons"]] == sorted(e["name"] for e in manifest["icons"])
    assert icons_mod.MANIFEST_FILE == ICONS_DIR / "manifest.json"
