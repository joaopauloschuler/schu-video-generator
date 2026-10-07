"""The docs stay in sync with the code: every config key and built-in scene param is documented
in docs/CONFIG.md with its default, and the docs' YAML snippets are valid."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from vidgen import config, extensions, registry
from vidgen.presets import BUILTIN_PRESETS
from vidgen.theme import DEFAULT_COLORS, DEFAULT_PALETTE, DEFAULT_SIZES, Theme

ROOT = Path(__file__).resolve().parents[1]
CONFIG_MD = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
MODELS: list[type[BaseModel]] = [
    config.VideoConfig,
    config.FormatConfig,
    config.ThemeConfig,
    config.VoiceConfig,
    config.VoiceSettings,
    config.NarrationConfig,
    config.PronunciationEntry,
    config.SceneConfig,
    config.BeatConfig,
    config.LintConfig,
    config.LintRules,
    config.LintIgnore,
    config.OffFrameRule,
    config.SafeAreaRule,
    config.TextOverlapRule,
    config.CoveredTextRule,
    config.MinFontRule,
    config.ContrastRule,
    config.MaxWordsRule,
    config.OverlayOverlapRule,
    config.OverlayConfig,
]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_every_config_key_is_documented(model: type[BaseModel]) -> None:
    names = [field.alias or name for name, field in model.model_fields.items()]   # as written in video.yaml
    missing = [name for name in names if f"`{name}`" not in CONFIG_MD and f"{name}:" not in CONFIG_MD]
    assert not missing, f"{model.__name__} fields missing from docs/CONFIG.md: {missing}"


@pytest.mark.parametrize("model", [config.VoiceConfig, config.VoiceSettings, config.NarrationConfig], ids=lambda m: m.__name__)
def test_scalar_defaults_match(model: type[BaseModel]) -> None:
    for name, field in model.model_fields.items():
        default = field.get_default(call_default_factory=True)
        if isinstance(default, BaseModel):
            continue
        shown = str(default).lower() if isinstance(default, bool) else str(default)
        assert re.search(rf"\b{name}: {re.escape(shown)}\b", CONFIG_MD), f"{model.__name__}.{name} default {shown}"


def test_format_and_theme_defaults_match() -> None:
    fmt, prev = config.FormatConfig(), config.VideoConfig.model_fields["preview"].get_default(call_default_factory=True)
    assert f"`{{width: {fmt.width}, height: {fmt.height}, fps: {fmt.fps}}}`" in CONFIG_MD
    assert f"`{{width: {prev.width}, height: {prev.height}, fps: {prev.fps}}}`" in CONFIG_MD
    theme = Theme()
    assert f'background: "{theme.background}"' in CONFIG_MD and f"font: {theme.font}" in CONFIG_MD
    assert f"code_style: {theme.code_style}" in CONFIG_MD
    for name, value in DEFAULT_COLORS.items():
        assert f'{name}: "{value}"' in CONFIG_MD
    assert "palette: [" + ", ".join(f'"{c}"' for c in DEFAULT_PALETTE) + "]" in CONFIG_MD
    assert "sizes: {" + ", ".join(f"{k}: {v}" for k, v in DEFAULT_SIZES.items()) + "}" in CONFIG_MD


def test_every_builtin_preset_is_documented_with_its_values() -> None:
    start = CONFIG_MD.find("### Theme presets")
    assert start != -1
    section = CONFIG_MD[start : CONFIG_MD.find("\n## ", start)]
    for preset in BUILTIN_PRESETS.values():
        assert f"`{preset.name}`" in section, preset.name
        assert preset.background in section and preset.code_style in section, preset.name
        for value in [*preset.colors.values(), *(preset.palette or ())]:
            assert value in section, f"{preset.name}: {value} missing from the presets table"


def test_every_builtin_scene_and_param_is_documented() -> None:
    with registry.isolated():
        extensions.load_builtins()
        entries = registry.all()
    first_name: dict[type, str] = {}
    for entry in entries:
        start = CONFIG_MD.find(f"### `{entry.name}`")
        assert start != -1, f"built-in scene type {entry.name} not documented"
        end = CONFIG_MD.find("\n### ", start + 1)
        section = CONFIG_MD[start : end if end != -1 else None]
        if entry.cls in first_name:   # a second name of a type (flowchart = diagram): points to it
            assert f"[`{first_name[entry.cls]}`]" in section, entry.name
            continue
        first_name[entry.cls] = entry.name
        model = entry.params_model
        for name in model.model_fields if model else []:
            assert f"`{name}`" in section, f"{entry.name}.{name} missing from its CONFIG.md section"


def test_docs_yaml_snippets_parse() -> None:
    for doc in ("docs/CONFIG.md", "docs/EXTENDING.md", "README.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        for block in re.findall(r"```yaml\n(.*?)```", text, flags=re.S):
            yaml.safe_load(block.replace("[...]", "[]"))
