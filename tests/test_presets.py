"""Theme presets: built-in presets, precedence, project presets, validation, schema and a render
of the built-in scenes with every preset (lint contrast clean)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import minimal_config, write_files

from vidgen import extensions
from vidgen.cli import main, project_problems
from vidgen.config import ThemeConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.lint import lint_project
from vidgen.lint.color import ACCENT_TOKENS, GRAPHIC_RATIO, TEXT_RATIO, TEXT_TOKENS, theme_contrast
from vidgen.presets import BUILTIN_PRESETS, DEFAULT_COLORS, make_preset
from vidgen.project import Project
from vidgen.theme import DEFAULT_PALETTE, Theme

PRESETS = sorted(BUILTIN_PRESETS)


def preset_theme(name: str | None, **config: object) -> Theme:
    return Theme(ThemeConfig(preset=name, **config))


# ----- the built-in presets ----------------------------------------------------------------------


def test_builtin_presets() -> None:
    assert PRESETS == ["dark_tech", "high_contrast", "light_academic"]


@pytest.mark.parametrize("name", PRESETS)
def test_preset_passes_wcag_aa(name: str) -> None:
    checks = theme_contrast(preset_theme(name))
    failures = [str(c) for c in checks if not c.ok]
    assert not failures, failures
    subjects = {c.subject for c in checks}
    assert {f"colors.{t}" for t in (*TEXT_TOKENS, *ACCENT_TOKENS)} <= subjects
    assert {f"palette[{i}]" for i in range(len(preset_theme(name).palette))} <= subjects
    assert {c.minimum for c in checks if c.subject in ("colors.text", "colors.dim")} == {TEXT_RATIO}
    assert {c.minimum for c in checks if c.subject.startswith("palette")} == {GRAPHIC_RATIO}


def test_high_contrast_reaches_aaa() -> None:
    assert all(c.ok for c in theme_contrast(preset_theme("high_contrast"), text_ratio=7, graphic_ratio=7))


@pytest.mark.parametrize("name", PRESETS)
def test_preset_values_are_valid(name: str) -> None:
    p = BUILTIN_PRESETS[name]
    again = make_preset(p.name, description=p.description, base=p.base, background=p.background, font=p.font,
                        code_style=p.code_style, colors=p.colors, palette=p.palette, sizes=p.sizes)
    assert again == p
    assert set(p.colors) == set(DEFAULT_COLORS), "built-in presets define every built-in color token"
    assert p.background and p.font and p.code_style and p.palette


def test_default_dim_passes_and_dark_tech_is_the_default_look() -> None:
    default, dark = Theme(), preset_theme("dark_tech")
    assert DEFAULT_COLORS["dim"] == "#838B98"
    assert all(c.ok for c in theme_contrast(default))
    for attr in ("background", "font", "code_style", "colors", "palette", "sizes"):
        assert getattr(default, attr) == getattr(dark, attr), attr


def test_contrast_check_reports_failures() -> None:
    theme = Theme(ThemeConfig(colors={"dim": "#6B7280"}, palette=["#58C4DD", "#202020"]))
    failing = {(c.subject, c.against): c for c in theme_contrast(theme) if not c.ok}
    assert set(failing) == {("colors.dim", "background"), ("colors.dim", "colors.surface"), ("palette[1]", "background")}
    on_background = failing["colors.dim", "background"]
    assert round(on_background.ratio, 2) == 3.91
    assert str(on_background) == "colors.dim #6B7280 on background #0E1116: 3.91:1 (needs 4.5:1, too low)"
    # short hex and alpha forms are understood
    assert all(c.ok for c in theme_contrast(Theme(ThemeConfig(colors={"text": "#FFF", "dim": "#AAAAAAFF"}))))


# ----- precedence --------------------------------------------------------------------------------


def test_precedence_config_over_preset_over_registered_over_builtin() -> None:
    theme = preset_theme("light_academic", colors={"primary": "#111111"}, sizes={"body": 30}, background="#FFFFFF")
    theme.add_defaults({"text": "#AAAAAA", "k2": "#BBBBBB"}, sizes={"huge": 80, "body": 99})
    light = BUILTIN_PRESETS["light_academic"]
    assert theme.color("primary") == "#111111"            # config wins
    assert theme.color("text") == light.colors["text"]   # preset beats a registered default
    assert theme.color("k2") == "#BBBBBB"                 # registered default (no preset value)
    assert theme.size("body") == 30 and theme.size("huge") == 80 and theme.size("title") == 56
    assert theme.background == "#FFFFFF"
    assert theme.font == "Inter" and theme.code_style == "xcode"
    assert theme.palette == list(light.palette)
    assert preset_theme("light_academic", palette=["#000000"], code_style="vs").palette == ["#000000"]
    assert preset_theme("light_academic", code_style="vs").code_style == "vs"


def test_without_preset_registered_defaults_still_override_builtins() -> None:
    theme = Theme()
    theme.add_defaults({"dim": "#CCCCCC"})
    assert theme.color("dim") == "#CCCCCC" and theme.palette == DEFAULT_PALETTE
    assert theme.preset is None and theme.preset_chain() == []


def test_high_contrast_raises_small_sizes() -> None:
    theme = preset_theme("high_contrast")
    assert theme.size("small") == 24 and theme.size("caption") == 26 and theme.size("body") == 32


def test_unknown_preset() -> None:
    theme = preset_theme("nope")
    with pytest.raises(VidgenError, match="unknown theme preset 'nope'; known presets: dark_tech, high_contrast, light_academic"):
        theme.color("text")
    with pytest.raises(VidgenError, match="unknown theme preset"):
        _ = theme.background


# ----- project presets ---------------------------------------------------------------------------


def test_project_preset_with_base_chain() -> None:
    theme = preset_theme("acme_dark")
    theme.add_preset(make_preset("acme", base="light_academic", colors={"primary": "#0B5FFF", "brand": "#0B5FFF"}))
    theme.add_preset(make_preset("acme_dark", base="acme", background="#101010", sizes={"body": 34}))
    assert [p.name for p in theme.preset_chain()] == ["light_academic", "acme", "acme_dark"]
    assert theme.background == "#101010"
    assert theme.color("primary") == "#0B5FFF" and theme.color("brand") == "#0B5FFF"
    assert theme.color("text") == BUILTIN_PRESETS["light_academic"].colors["text"]
    assert theme.size("body") == 34 and theme.code_style == "xcode"
    assert sorted(theme.presets) == ["acme", "acme_dark", *PRESETS]


def test_project_preset_without_base_falls_back_to_defaults() -> None:
    theme = preset_theme("mono")
    theme.add_defaults({"k2": "#123456"})
    theme.add_preset(make_preset("mono", colors={"text": "#FFFFFF"}))
    assert theme.color("text") == "#FFFFFF" and theme.color("dim") == DEFAULT_COLORS["dim"]
    assert theme.color("k2") == "#123456" and theme.background == "#0E1116" and theme.palette == DEFAULT_PALETTE


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "bad-name"}, "letters, digits and _"),
        ({"name": "x", "background": "white"}, "background must be a hex color"),
        ({"name": "x", "colors": {"text": "#12"}}, r"colors\.text must be a hex color"),
        ({"name": "x", "colors": {"my-color": "#123456"}}, "color name 'my-color'"),
        ({"name": "x", "palette": ["#123456", "red"]}, r"palette\[1\] must be a hex color"),
        ({"name": "x", "palette": []}, "at least one color"),
        ({"name": "x", "sizes": {"body": 0}}, "size 'body' must be a positive number"),
        ({"name": "x", "code_style": "nope"}, "unknown code style 'nope'"),
        ({"name": "x", "font": ""}, "font must be a font family name"),
    ],
)
def test_make_preset_rejects_bad_values(kwargs: dict, message: str) -> None:
    name = kwargs.pop("name")
    with pytest.raises(VidgenError, match=message):
        make_preset(name, **kwargs)


def test_add_preset_rejects_clashes_and_unknown_base() -> None:
    theme = Theme()
    with pytest.raises(VidgenError, match="'dark_tech' is a built-in preset"):
        theme.add_preset(make_preset("dark_tech"))
    theme.add_preset(make_preset("acme", origin="extensions/a.py"))
    with pytest.raises(VidgenError, match="'acme' is already registered by extensions/a.py"):
        theme.add_preset(make_preset("acme"))
    with pytest.raises(VidgenError, match="unknown base preset 'ghost'"):
        theme.add_preset(make_preset("x", base="ghost"))


def test_derive_shares_registered_presets_and_defaults() -> None:
    theme = Theme()
    theme.add_defaults({"k2": "#123456"})
    theme.add_preset(make_preset("acme", colors={"text": "#010101"}))
    variant = theme.derive(ThemeConfig(preset="acme"))
    assert variant.color("text") == "#010101" and variant.color("k2") == "#123456"
    assert theme.preset is None


# ----- config, variants, extensions, validate, schema --------------------------------------------


def test_config_code_style_is_checked() -> None:
    with pytest.raises(VidgenError, match="theme.code_style: .*unknown code style 'nope'"):
        parse_config(minimal_config(theme={"code_style": "nope"}))
    with pytest.raises(VidgenError, match="theme.preset"):
        parse_config(minimal_config(theme={"preset": "light academic"}))


def test_variant_switches_preset_and_base_values_still_win(make_project: Callable[..., Path]) -> None:
    root = make_project(minimal_config(
        theme={"preset": "dark_tech", "colors": {"primary": "#123456"}},
        variants={"light": {"theme": {"preset": "light_academic"}}},
    ))
    base = Theme(Project.load(root).config.theme)
    light = Theme(Project.load(root, variant="light").config.theme)
    assert base.background == "#0E1116" and light.background == "#F8F7F3"
    assert light.color("primary") == "#123456"   # written in the base theme: wins over the preset
    assert light.color("text") == BUILTIN_PRESETS["light_academic"].colors["text"]


BRAND = """
    from vidgen.api import *

    register_theme_preset("acme", base="light_academic", colors={"primary": "#0B5FFF"},
                          description="ACME look")
    PRIMARY = current_theme().color("primary")
"""


def test_extension_registers_a_preset(make_project: Callable[..., Path]) -> None:
    root = make_project(minimal_config(theme={"preset": "acme"}, variants={"plain": {"theme": {"preset": "dark_tech"}}}))
    write_files(root, {"extensions/brand.py": BRAND})
    project = Project.load(root)
    assert project_problems(project) == []
    with extensions.project_session(project) as theme:
        assert theme.color("primary") == "#0B5FFF" and theme.background == "#F8F7F3"
        preset = theme.presets["acme"]
        assert preset.origin == "extensions/brand.py" and preset.description == "ACME look"
        module = next(m for n, m in __import__("sys").modules.items() if n.endswith(".brand"))
        assert module.PRIMARY == "#0B5FFF"
    assert main(["validate", str(root)]) == 0


def test_validate_reports_unknown_preset(make_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(theme={"preset": "acme"}, variants={"v": {"theme": {"preset": "nope"}}}))
    problems = project_problems(Project.load(root))
    assert [p.location for p in problems] == ["theme.preset"]
    assert "unknown theme preset 'acme'; known presets: dark_tech, high_contrast, light_academic" in problems[0].message
    assert main(["validate", str(root), "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert {(p["location"], p["variant"]) for p in doc["problems"]} == {("theme.preset", None), ("theme.preset", "v")}


def test_schema_lists_presets_and_code_styles(make_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    root = make_project(minimal_config(theme={"preset": "acme"}))
    write_files(root, {"extensions/brand.py": BRAND})
    assert main(["schema", str(root)]) == 0
    schema = json.loads(capsys.readouterr().out)
    props = schema["$defs"]["ThemeConfig"]["properties"]
    assert props["preset"]["anyOf"][0]["enum"] == ["acme", *PRESETS]
    assert {"github-dark", "xcode"} <= set(props["code_style"]["anyOf"][0]["enum"])
    validator = jsonschema.Draft202012Validator(schema)
    assert not list(validator.iter_errors(minimal_config(theme={"preset": "acme", "code_style": "xcode"})))
    assert list(validator.iter_errors(minimal_config(theme={"preset": "nope"})))
    assert list(validator.iter_errors(minimal_config(variants={"v": {"theme": {"code_style": "nope"}}})))


# ----- every built-in scene renders cleanly with every preset ------------------------------------

SCENES = [
    {"id": "intro", "type": "title", "params": {"kicker": "KICKER", "title": "A title with a highlight",
                                                 "highlight": "highlight", "subtitle": "Sub", "authors": ["An author"]},
     "beats": [{"text": "One."}, {"text": "Two."}]},
    {"id": "steps", "type": "bullets", "params": {"heading": "List", "numbered": True, "dim_previous": True,
                                                   "items": ["First item", "Second item"]},
     "beats": [{"text": "One."}, {"text": "Two."}]},
    {"id": "bars", "type": "bar_chart", "params": {"title": "Bars", "labels": ["alpha", "beta", "gamma"], "values": [1, 2, 3],
                                                   "colors": "palette", "highlight": "alpha"},
     "beats": [{"text": "One."}, {"text": "Two."}]},
    {"id": "lines", "type": "line_chart", "params": {"title": "Lines", "x": [1, 2, 3], "series": {"s": [1, 3, 2], "t": [2, 1, 3]}},
     "beats": [{"text": "One."}, {"text": "Two."}]},
    {"id": "saying", "type": "quote", "params": {"text": "A short quote.", "author": "Someone"}, "beats": [{"text": "One."}]},
    {"id": "listing", "type": "code", "params": {"code": "def f(x):\n    # comment\n    return x + 1  # 'str'\n",
                                                  "highlight": ["1", "3"]},
     "beats": [{"text": "One."}, {"text": "Two."}]},
    {"id": "outro", "type": "end_card", "params": {"title": "Thanks", "lines": ["docs/CONFIG.md"]}, "beats": [{"text": "One."}]},
]


@pytest.fixture(scope="module")
def preset_projects(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One project with a variant per preset (rendered lazily by lint)."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH")
    root = tmp_path_factory.mktemp("presets") / "proj"
    root.mkdir()
    data = minimal_config(
        scenes=SCENES,
        preview={"width": 640, "height": 360, "fps": 5},  # glyphs big enough to sample a backdrop
        theme={"preset": "dark_tech"},
        variants={name: {"theme": {"preset": name}} for name in PRESETS},
    )
    (root / "video.yaml").write_text(json.dumps(data), encoding="utf-8")
    return root


@pytest.mark.render
@pytest.mark.parametrize("name", PRESETS)
def test_builtin_scenes_pass_contrast_lint_with_every_preset(preset_projects: Path, name: str) -> None:
    project = Project.load(preset_projects, variant=name)
    result = lint_project(project, rules=["contrast"], jobs=4)
    assert [f.message for f in result.findings] == []
    layout = json.loads((project.render_dir(True) / "layout" / "listing.json").read_text(encoding="utf-8"))
    assert layout["background"] == BUILTIN_PRESETS[name].background
    code_colors = {c for frame in layout["frames"] for o in frame["objects"] if o["kind"] == "code" for c in o["colors"]}
    fills = {o["fill"]["color"] for frame in layout["frames"] for o in frame["objects"] if o.get("fill")}
    assert BUILTIN_PRESETS[name].colors["surface"] in fills   # the code window
    assert len(code_colors) > 2   # syntax colours of the theme's code_style
