"""Theme token resolution and precedence."""

from __future__ import annotations

import pytest

from vidgen.config import ThemeConfig
from vidgen.errors import VidgenError
from vidgen.theme import DEFAULT_COLORS, DEFAULT_PALETTE, Theme


def test_defaults() -> None:
    theme = Theme()
    assert theme.background == "#0E1116"
    assert theme.font == "Inter"
    assert theme.color("primary") == "#58C4DD"
    assert theme.colors == DEFAULT_COLORS
    assert theme.size("body") == 32
    assert theme.palette == DEFAULT_PALETTE


def test_hex_and_numbers_pass_through() -> None:
    theme = Theme()
    assert theme.color("#123456") == "#123456"
    assert theme.size(40) == 40
    assert theme.size(12.5) == 12.5


def test_unknown_tokens_list_known() -> None:
    theme = Theme()
    with pytest.raises(VidgenError, match="unknown theme color 'k9'; known colors: accent, dim,"):
        theme.color("k9")
    with pytest.raises(VidgenError, match="unknown theme size 'huge'; known sizes: body,"):
        theme.size("huge")


def test_palette_wraps() -> None:
    theme = Theme(ThemeConfig(palette=["#000000", "#FFFFFF"]))
    assert [theme.palette_color(i) for i in range(3)] == ["#000000", "#FFFFFF", "#000000"]


def test_config_overrides_and_adds_tokens() -> None:
    theme = Theme(ThemeConfig(colors={"primary": "#111111", "k2": "#222222"}, sizes={"body": 30, "huge": 90}))
    assert theme.color("primary") == "#111111"
    assert theme.color("k2") == "#222222"
    assert theme.color("dim") == DEFAULT_COLORS["dim"]
    assert theme.size("body") == 30 and theme.size("huge") == 90 and theme.size("title") == 56


def test_registered_defaults_lose_to_config() -> None:
    theme = Theme(ThemeConfig(colors={"k2": "#222222"}))
    theme.add_defaults({"k2": "#AAAAAA", "k3": "#BBBBBB", "dim": "#CCCCCC"}, sizes={"huge": 80})
    assert theme.color("k2") == "#222222"   # config wins
    assert theme.color("k3") == "#BBBBBB"   # registered default
    assert theme.color("dim") == "#CCCCCC"  # registered beats built-in
    assert theme.size("huge") == 80


def test_add_defaults_rejects_non_hex() -> None:
    with pytest.raises(VidgenError, match="must be a hex string"):
        Theme().add_defaults({"x": "red"})


def test_theme_does_not_import_manim() -> None:
    import subprocess
    import sys

    code = "import sys, vidgen.theme, vidgen.project, vidgen.cli; print('manim' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "False"
