"""Bundled fonts (Step 18): package data, licences, registration with Pango, font roles."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import ImageFont

from vidgen import fonts
from vidgen.config import ThemeConfig, VideoConfig
from vidgen.errors import VidgenError
from vidgen.fonts import (
    BUNDLED_FAMILIES,
    MONO_FAMILY,
    SANS_FAMILY,
    SERIF_FAMILY,
    bundled_font_file,
    bundled_font_files,
    register_bundled_fonts,
)
from vidgen.presets import BUILTIN_PRESETS, make_preset
from vidgen.theme import Theme

from conftest import minimal_config

REPO = Path(__file__).resolve().parent.parent


# ----- package data ------------------------------------------------------------------------------


@pytest.mark.parametrize("family", BUNDLED_FAMILIES, ids=lambda f: f.family)
def test_bundled_files_are_the_named_family_with_their_licence(family: fonts.BundledFamily) -> None:
    assert family.license.is_file()
    licence = family.license.read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    styles = []
    for path in family.files:
        assert path.is_file() and path.suffix == ".ttf"
        name, style = ImageFont.truetype(str(path), 20).getname()
        assert name == family.family
        styles.append(style)
    assert styles[:2] == ["Regular", "Bold"]
    assert all(s == "Italic" for s in styles[2:])


def test_bundle_stays_small_and_is_package_data() -> None:
    total = sum(p.stat().st_size for p in bundled_font_files())
    assert total < 2_500_000  # Regular/Bold (+Italic) only
    assert '"data/fonts/**/*"' in (REPO / "pyproject.toml").read_text(encoding="utf-8")
    notice = (REPO / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for family in BUNDLED_FAMILIES:
        assert family.family in notice and "Open Font License" in notice


def test_bundled_font_file() -> None:
    assert bundled_font_file(SERIF_FAMILY).name == "SourceSerif4-Regular.ttf"
    assert bundled_font_file(SERIF_FAMILY, bold=True).name == "SourceSerif4-Bold.ttf"
    assert bundled_font_file(SANS_FAMILY, italic=True).name == "Inter-Italic.ttf"
    assert bundled_font_file(MONO_FAMILY, italic=True).name == "JetBrainsMonoNL-Regular.ttf"  # no italic bundled
    assert bundled_font_file("Comic Sans MS") is None


# ----- registration ------------------------------------------------------------------------------


def test_registration_registers_every_file_even_if_installed() -> None:
    # Inter is installed system-wide in the test environment: registering it again must work
    import manimpango

    assert register_bundled_fonts() == bundled_font_files()
    assert register_bundled_fonts() == bundled_font_files()  # idempotent
    installed = manimpango.list_fonts()
    for family in (SANS_FAMILY, SERIF_FAMILY, MONO_FAMILY):
        assert family in installed


def test_registration_failure_is_a_warning(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    import manimpango

    monkeypatch.setattr(fonts, "_registered", None)
    monkeypatch.setattr(manimpango, "register_font", lambda path: False)
    with caplog.at_level(logging.WARNING, logger="vidgen.fonts"):
        assert register_bundled_fonts() == []
    assert "could not register bundled font" in caplog.text


def _system_has(family: str) -> bool:
    """Whether a fresh process without vidgen knows ``family`` (i.e. it is installed)."""
    code = f"import manimpango; print({family!r} in manimpango.list_fonts())"
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    return out.stdout.strip() == "True"


@pytest.mark.slow
def test_fonts_need_no_system_install() -> None:
    if _system_has(SERIF_FAMILY) or _system_has(MONO_FAMILY):
        pytest.skip("Source Serif 4 / JetBrains Mono NL are installed system-wide here")
    code = (
        "import vidgen.helpers, manimpango; fonts = manimpango.list_fonts(); "
        f"print({SERIF_FAMILY!r} in fonts and {MONO_FAMILY!r} in fonts)"
    )
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert out.stdout.strip() == "True"


SAMPLES = ("Hamburgefonstiv", "MWillow", "il1|0O")


def _ink_widths(family: str, bold: bool) -> list[float]:
    """Ink widths of SAMPLES as laid out by Pango (Manim Text) divided by the same widths
    measured with FreeType straight from the bundled file: constant iff Pango used that file."""
    from manim import BOLD, NORMAL, Text

    path = bundled_font_file(family, bold=bold)
    assert path is not None
    face = ImageFont.truetype(str(path), 200)
    ratios = []
    for s in SAMPLES:
        left, _, right, _ = face.getbbox(s)
        ratios.append(float(Text(s, font=family, font_size=48, weight=BOLD if bold else NORMAL).width) / (right - left))
    return ratios


@pytest.mark.render
def test_pango_renders_with_the_bundled_faces(tmp_path: Path) -> None:
    from manim import tempconfig

    register_bundled_fonts()
    with tempconfig({"text_dir": str(tmp_path)}):
        rows = [_ink_widths(family, bold) for family in (SANS_FAMILY, SERIF_FAMILY, MONO_FAMILY) for bold in (False, True)]
    for i in range(len(SAMPLES)):  # a substituted face would be off by far more on some sample
        reference = sum(row[i] for row in rows) / len(rows)
        for row in rows:
            assert row[i] == pytest.approx(reference, rel=0.02)


# ----- theme tokens and roles --------------------------------------------------------------------


def test_font_tokens_default_to_the_bundled_families() -> None:
    theme = Theme()
    assert (theme.font, theme.font_serif, theme.font_mono) == (SANS_FAMILY, SERIF_FAMILY, MONO_FAMILY)
    assert theme.font_for("body") == theme.font_for("heading") == theme.font_for("quote") == SANS_FAMILY
    assert theme.font_for("code") == MONO_FAMILY and theme.font_for("quote_mark") == SERIF_FAMILY
    assert theme.font_for("anything_else") == SANS_FAMILY


def test_font_tokens_and_roles_from_config_and_presets() -> None:
    theme = Theme(ThemeConfig(preset="warm_editorial"))
    assert theme.font_for("heading") == theme.font_for("quote") == SERIF_FAMILY
    assert theme.font_for("body") == SANS_FAMILY and theme.font_for("code") == MONO_FAMILY
    assert Theme(ThemeConfig(preset="light_academic")).font_for("heading") == SERIF_FAMILY
    assert Theme(ThemeConfig(preset="light_academic")).font_for("quote") == SANS_FAMILY
    custom = Theme(
        ThemeConfig(preset="warm_editorial", font="Lato", font_serif="Georgia", font_mono="Consolas", fonts={"quote": "sans", "kicker": "Impact"})
    )
    assert custom.font_for("body") == "Lato" and custom.font_for("heading") == "Georgia"
    assert custom.font_for("quote") == "Lato" and custom.font_for("code") == "Consolas"
    assert custom.font_for("kicker") == "Impact"
    assert custom.fonts == {"heading": "serif", "quote": "sans", "kicker": "Impact"}


def test_preset_font_families() -> None:
    theme = Theme(ThemeConfig(preset="mono_look"))
    theme.add_preset(make_preset("mono_look", base="dark_tech", font_mono="Fira Mono", font_serif="Lora", fonts={"heading": "mono"}))
    assert theme.font_mono == "Fira Mono" and theme.font_serif == "Lora"
    assert theme.font_for("heading") == "Fira Mono" and theme.font_for("quote_mark") == "Lora"
    assert Theme(ThemeConfig(preset="mono_look", font_mono="Courier New")).font_mono == "Courier New"


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"font_serif": " "}, "font_serif must be a font family name"),
        ({"font_mono": ""}, "font_mono must be a font family name"),
        ({"fonts": {"heading": ""}}, "or one of sans, serif, mono"),
    ],
)
def test_preset_font_validation(values: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        make_preset("x", **values)


def test_config_font_keys() -> None:
    cfg = VideoConfig.model_validate(minimal_config(theme={"font_serif": "Lora", "fonts": {"heading": "serif"}}))
    assert cfg.theme.font_serif == "Lora" and cfg.theme.fonts == {"heading": "serif"}
    with pytest.raises(Exception, match="fonts"):
        VideoConfig.model_validate(minimal_config(theme={"fonts": {"bad-role": "serif"}}))
    with pytest.raises(Exception, match="font_mono"):
        VideoConfig.model_validate(minimal_config(theme={"font_mono": ""}))


def test_only_editorial_presets_change_roles() -> None:
    changed = {name for name, p in BUILTIN_PRESETS.items() if p.fonts}
    assert changed == {"light_academic", "warm_editorial"}


def test_api_register_theme_preset_accepts_font_families() -> None:
    import inspect

    from vidgen.api import register_theme_preset

    params = inspect.signature(register_theme_preset).parameters
    assert {"font", "font_serif", "font_mono", "fonts"} <= set(params)


# ----- built-in scenes use the roles ------------------------------------------------------------


def _render(project_dir: Path, scene_id: str, media: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    """Render a scene in-process (tiny); returns it and the font families of every Text built."""
    from manim import Text, tempconfig

    from vidgen import extensions, registry
    from vidgen.project import Project
    from vidgen.render.worker import frame_size

    used: set[str] = set()
    original = Text.__init__

    def recording(self: Any, *args: Any, **kwargs: Any) -> None:
        used.add(kwargs.get("font", ""))
        original(self, *args, **kwargs)

    monkeypatch.setattr(Text, "__init__", recording)
    project = Project.load(project_dir)
    fw, fh = frame_size(160, 90)
    settings = {
        "pixel_width": 160, "pixel_height": 90, "frame_width": fw, "frame_height": fh, "frame_rate": 5,
        "media_dir": str(media), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR",
        "output_file": scene_id,
    }
    with tempconfig(settings):
        spec = project.scene(scene_id)
        theme = extensions.activate(project)
        scene = registry.get(spec.type).cls(spec, project, theme)
        scene.render()
    monkeypatch.setattr(Text, "__init__", original)
    return scene, used


@pytest.mark.render
@pytest.mark.slow
def test_scenes_use_font_roles(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenes = [
        {"id": "listing", "type": "code", "params": {"code": "x = 1\n", "title": "Code"}, "duration": 0.4},
        {"id": "own", "type": "code", "params": {"code": "x = 1\n", "font": "DejaVu Sans Mono"}, "duration": 0.4},
        {"id": "saying", "type": "quote", "params": {"text": "Less is more", "author": "M"}, "duration": 0.4},
        {"id": "intro", "type": "title", "params": {"title": "Big", "subtitle": "small"}, "duration": 0.4},
    ]
    root = make_project(minimal_config(scenes=scenes, theme={"preset": "warm_editorial"}))
    listing, used = _render(root, "listing", tmp_path, monkeypatch)
    assert listing._font == MONO_FAMILY and {MONO_FAMILY, SERIF_FAMILY} <= used  # serif window title
    own, used = _render(root, "own", tmp_path, monkeypatch)
    assert own._font == "DejaVu Sans Mono" and MONO_FAMILY not in used
    _, used = _render(root, "saying", tmp_path, monkeypatch)
    assert {SERIF_FAMILY, SANS_FAMILY} <= used  # serif quote and mark, sans attribution
    _, used = _render(root, "intro", tmp_path, monkeypatch)
    assert {SERIF_FAMILY, SANS_FAMILY} <= used  # serif title, sans subtitle
    plain = make_project(minimal_config(scenes=scenes), folder="plain")
    _, used = _render(plain, "intro", tmp_path, monkeypatch)
    assert SERIF_FAMILY not in used
