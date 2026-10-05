"""Type scales, scale-aware theme sizes, font roles, colour-vision helpers, `vidgen list-themes`
and the theme contrast warnings of `vidgen validate` (Step 17)."""

from __future__ import annotations

import json
import math
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import minimal_config, write_files
from PIL import Image

from vidgen import extensions
from vidgen.cli import main
from vidgen.config import FormatConfig, ThemeConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.lint import lint_project
from vidgen.lint.color import delta_e, hex_rgb, lab, palette_distinctness, simulate_cvd
from vidgen.presets import BUILTIN_PRESETS, DEFAULT_SIZES, make_preset
from vidgen.project import Project
from vidgen.scales import AUTO_SCALES, SCALE_CHOICES, SCALE_TOKENS, TYPE_SCALES, frame_orientation, resolve_scale
from vidgen.theme import Theme

PORTRAIT = FormatConfig(width=1080, height=1920)
LANDSCAPE = FormatConfig(width=1920, height=1080)


# ----- the scales --------------------------------------------------------------------------------


def test_scales_define_every_token_and_grow() -> None:
    assert SCALE_CHOICES == ("compact", "standard", "large", "auto")
    assert dict(TYPE_SCALES["standard"]) == DEFAULT_SIZES
    for sizes in TYPE_SCALES.values():
        assert tuple(sizes) == SCALE_TOKENS
        assert [sizes[t] for t in SCALE_TOKENS] == sorted((sizes[t] for t in SCALE_TOKENS), reverse=True)
        assert sizes["small"] >= 20, "never below the standard small size (lint min_font floor)"
    for token in SCALE_TOKENS:
        assert TYPE_SCALES["compact"][token] <= TYPE_SCALES["standard"][token] < TYPE_SCALES["large"][token]


def test_orientation_and_auto() -> None:
    assert frame_orientation(1920, 1080) == "landscape"
    assert frame_orientation(1080, 1920) == "portrait"
    assert frame_orientation(1080, 1080) == "square"
    assert resolve_scale("auto", "portrait") == "large" == AUTO_SCALES["portrait"]
    assert resolve_scale("auto", "square") == "standard" and resolve_scale("compact", "portrait") == "compact"
    with pytest.raises(ValueError, match="unknown type scale 'huge'"):
        resolve_scale("huge")


# ----- theme sizes -------------------------------------------------------------------------------


def test_auto_scale_follows_the_format() -> None:
    landscape, portrait = Theme.for_format(ThemeConfig(), LANDSCAPE), Theme.for_format(ThemeConfig(), PORTRAIT)
    assert landscape.scale_setting == portrait.scale_setting == "auto"
    assert landscape.scale == "standard" and landscape.sizes == DEFAULT_SIZES
    assert portrait.scale == "large" and portrait.sizes == dict(TYPE_SCALES["large"])
    assert Theme().orientation == "landscape"
    # a variant's theme follows the variant's format
    assert landscape.derive(ThemeConfig(), PORTRAIT).scale == "large"
    assert portrait.derive(ThemeConfig()).scale == "large"


def test_scale_precedence() -> None:
    # config scale beats the preset's scale; config sizes beat the config scale
    theme = Theme(ThemeConfig(preset="bold_neon", scale="compact", sizes={"body": 31}))
    assert theme.scale == "compact" and theme.scale_setting == "compact"
    assert theme.size("title") == TYPE_SCALES["compact"]["title"] and theme.size("body") == 31
    # an explicit standard scale keeps portrait video at the standard sizes
    assert Theme(ThemeConfig(scale="standard"), orientation="portrait").sizes == DEFAULT_SIZES
    # a preset's own sizes sit above its scale; a scale written in the config sits above both
    theme = Theme(ThemeConfig(preset="acme"))
    theme.add_preset(make_preset("acme", base="bold_neon", sizes={"caption": 27}))
    assert theme.size("caption") == 27 and theme.size("body") == TYPE_SCALES["large"]["body"]
    theme = theme.derive(ThemeConfig(preset="acme", scale="compact"))
    assert theme.size("caption") == TYPE_SCALES["compact"]["caption"]


def test_registered_sizes_vs_scales() -> None:
    """Extension defaults beat the implicit (auto) scale, but a chosen scale beats them for the
    six scale tokens; extension-only tokens are untouched."""
    implicit = Theme(orientation="portrait")
    implicit.add_defaults(sizes={"body": 99, "huge": 80})
    assert implicit.size("body") == 99 and implicit.size("title") == TYPE_SCALES["large"]["title"]
    chosen = Theme(ThemeConfig(scale="compact"))
    chosen.add_defaults(sizes={"body": 99, "huge": 80})
    assert chosen.size("body") == TYPE_SCALES["compact"]["body"] and chosen.size("huge") == 80


def test_config_scale_is_validated_and_in_the_schema(make_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    assert parse_config(minimal_config(theme={"scale": "large"})).theme.scale == "large"
    with pytest.raises(VidgenError, match="theme.scale"):
        parse_config(minimal_config(theme={"scale": "huge"}))
    root = make_project(minimal_config())
    assert main(["schema", str(root)]) == 0
    props = json.loads(capsys.readouterr().out)["$defs"]["ThemeConfig"]["properties"]
    assert set(SCALE_CHOICES) <= set(props["scale"]["anyOf"][0]["enum"])


def test_project_context_uses_the_variant_format(make_project: Callable[..., Path]) -> None:
    root = make_project(minimal_config(variants={"vertical": {"format": {"width": 1080, "height": 1920}}}))
    with extensions.project_session(Project.load(root)) as theme:
        assert theme.scale == "standard"
    with extensions.project_session(Project.load(root, variant="vertical")) as theme:
        assert theme.scale == "large" and theme.size("body") == TYPE_SCALES["large"]["body"]


# ----- font roles --------------------------------------------------------------------------------


def test_font_roles_hook() -> None:
    theme = Theme(ThemeConfig(preset="serif_look"))
    theme.add_preset(make_preset("serif_look", base="warm_editorial", fonts={"heading": "Georgia"}))
    assert theme.fonts == {"heading": "Georgia"}
    assert theme.font_for("heading") == "Georgia" and theme.font_for("body") == "Inter"
    # a font written in video.yaml sets every text, roles included
    written = theme.derive(ThemeConfig(preset="serif_look", font="DejaVu Sans"))
    assert written.font_for("heading") == "DejaVu Sans"
    assert Theme().fonts == {} and Theme().font_for("mono") == "Inter"


# ----- colour vision -----------------------------------------------------------------------------


def test_cvd_helpers() -> None:
    assert simulate_cvd((0.2, 0.4, 0.6), "normal") == (0.2, 0.4, 0.6)
    # red and green collapse for deuteranopes far more than for normal vision
    red, green = hex_rgb("#D62728"), hex_rgb("#2CA02C")
    normal = delta_e(lab(red), lab(green))
    deutan = delta_e(lab(simulate_cvd(red, "deuteranopia")), lab(simulate_cvd(green, "deuteranopia")))
    assert normal > 40 and deutan < normal / 2
    # CIEDE2000 reference pair (Sharma, Wu & Dalal 2005, pair 1)
    assert round(delta_e((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485)), 4) == 2.0425
    assert lab(hex_rgb("#FFFFFF"))[0] == pytest.approx(100, abs=0.01)
    assert palette_distinctness(["#123456"]) == {v: math.inf for v in ("normal", "protanopia", "deuteranopia", "tritanopia")}


# ----- vidgen list-themes ------------------------------------------------------------------------

BRAND = """
    from vidgen.api import *

    register_theme_preset("acme", base="brand_neutral", colors={"primary": "#0B5FFF"}, scale="compact",
                          description="ACME look")
"""


def test_list_themes_text(make_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(theme={"preset": "acme"}))
    write_files(root, {"extensions/brand.py": BRAND})
    assert main(["list-themes", str(root)]) == 0
    out = capsys.readouterr().out
    for name in BUILTIN_PRESETS:
        assert f"\n{name} " in f"\n{out}"
    assert "acme" in out and "extensions/brand.py  scale compact  [selected]" in out
    assert "bold_neon" in out and "scale large" in out and "auto = standard here" in out
    assert "compact   48 36 32 28 22 20" in out and "auto = standard for this landscape video" in out


def test_list_themes_json_and_swatches(make_project: Callable[..., Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(theme={"preset": "acme"}, format={"width": 1080, "height": 1920, "fps": 30}))
    write_files(root, {"extensions/brand.py": BRAND})
    png = tmp_path / "out" / "themes.png"
    assert main(["list-themes", str(root), "--json", "--swatches", str(png)]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "list-themes" and doc["ok"] and doc["version"] == 1
    assert doc["orientation"] == "portrait" and doc["swatches"] == str(png.resolve())
    assert doc["current"] == {"preset": "acme", "scale": "compact", "scale_resolved": "compact"}
    assert doc["type_scales"]["auto"]["portrait"] == "large"
    assert doc["type_scales"]["scales"]["large"] == dict(TYPE_SCALES["large"])
    entries = {e["name"]: e for e in doc["presets"]}
    assert list(entries) == [*BUILTIN_PRESETS, "acme"]
    acme, dark = entries["acme"], entries["dark_tech"]
    assert acme["selected"] and acme["origin"] == "extensions/brand.py" and acme["base"] == "brand_neutral"
    assert acme["colors"]["primary"] == "#0B5FFF" and acme["background"] == BUILTIN_PRESETS["brand_neutral"].background
    assert dark["scale"] == "auto" and dark["scale_resolved"] == "large" and dark["sizes"]["body"] == TYPE_SCALES["large"]["body"]
    assert set(dark) >= {"description", "font", "fonts", "code_style", "palette", "contrast", "palette_distinctness"}
    assert all(e["contrast"]["ok"] and e["contrast"]["failures"] == [] for e in doc["presets"])
    assert dark["contrast"]["min_text_ratio"] >= 4.5 and dark["contrast"]["min_graphic_ratio"] >= 3
    with Image.open(png) as image:
        assert image.width == 1280 and image.height == 190 * len(entries)
        assert image.getpixel((5, 5)) == tuple(int(dark["background"][i : i + 2], 16) for i in (1, 3, 5))


def test_list_themes_without_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["list-themes", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["project"] is None and doc["current"]["preset"] is None and doc["swatches"] is None
    assert [e["name"] for e in doc["presets"]] == list(BUILTIN_PRESETS)


# ----- vidgen validate: theme contrast warnings --------------------------------------------------


def test_validate_warns_about_the_projects_theme_contrast(make_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(
        theme={"colors": {"dim": "#6B7280"}},
        variants={"light": {"theme": {"preset": "light_academic", "colors": {"primary": "#FFE0E0"}}}},
    ))
    assert main(["validate", str(root)]) == 0
    captured = capsys.readouterr()
    assert "warning: theme contrast: colors.dim #6B7280 on background #0E1116: 3.91:1 (needs 4.5:1, too low)" in captured.err
    assert "warning: [light] theme contrast: colors.primary #FFE0E0 on background #F8F7F3" in captured.err
    assert captured.err.count("colors.dim #6B7280 on background #0E1116") == 1
    assert captured.out.rstrip().endswith("ok")
    assert main(["validate", str(root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    messages = [w["message"] for w in doc["warnings"]]
    assert doc["ok"] and any(m.startswith("theme contrast: colors.dim") for m in messages)
    assert any(m.startswith("[light] theme contrast: colors.primary") for m in messages)


def test_validate_no_warnings_with_a_builtin_preset(make_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(theme={"preset": "soft_pastel"}))
    assert main(["validate", str(root)]) == 0
    assert "theme contrast" not in capsys.readouterr().err


# ----- the large scale in a vertical frame keeps layouts intact -----------------------------------

VERTICAL_SCENES = [
    {"id": "intro", "type": "title", "params": {"kicker": "KICKER", "title": "Narrated videos from a single config file",
                                                 "highlight": "single config file", "subtitle": "A tour of the built-in scene types",
                                                 "authors": ["Made with Manim, ElevenLabs and ffmpeg"]},
     "beats": [{"text": "One."}]},
    {"id": "steps", "type": "bullets", "params": {"heading": "How a video is made", "numbered": True,
                                                   "items": ["Write the narration as short beats", "Pick a scene type and its parameters",
                                                             "Generate the voice once", "Render a preview, then the final video"]},
     "beats": [{"text": "One."}]},
    {"id": "saying", "type": "quote", "params": {"text": "Simplicity is prerequisite for reliability.", "author": "Edsger W. Dijkstra",
                                                  "source": "How do we tell truths that might hurt? (1975)"}, "beats": [{"text": "One."}]},
    {"id": "outro", "type": "end_card", "params": {"title": "Thanks for watching", "lines": ["Built-in scenes: docs/CONFIG.md"]},
     "beats": [{"text": "One."}]},
]


@pytest.mark.render
def test_large_scale_in_portrait_keeps_text_on_frame(make_project: Callable[..., Path]) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH")
    root = make_project(minimal_config(
        scenes=VERTICAL_SCENES,
        format={"width": 1080, "height": 1920},
        preview={"width": 180, "height": 320, "fps": 5},
        theme={"preset": "bold_neon"},
    ))
    project = Project.load(root)
    result = lint_project(project, rules=["off_frame", "safe_area", "text_overlap"], jobs=4)
    assert [f.message for f in result.findings] == []
    layout = json.loads((project.render_dir(True) / "layout" / "steps.json").read_text(encoding="utf-8"))
    assert layout["frames"]
