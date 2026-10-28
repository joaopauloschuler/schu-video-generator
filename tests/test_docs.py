"""The docs stay in sync with the code: every config key and built-in scene param is documented
in docs/CONFIG.md with its default, and the docs' YAML snippets are valid."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from vidgen import config, extensions, registry, translation
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
    config.VoiceEntry,
    config.VoiceSettingsOverride,
    config.EmotionConfig,
    config.CharacterEntry,
    config.CharacterColors,
    config.CharacterLook,
    config.PartPoseEntry,
    config.HostConfig,
    config.HostOverride,
    config.SubtitlesConfig,
    config.NarrationConfig,
    config.PronunciationEntry,
    config.SceneConfig,
    config.TermConfig,
    config.ShotConfig,
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
    config.HostOverlapRule,
    config.ReadbackRule,
    config.ConceptColorsRule,
    config.SttConfig,
    config.ImagegenConfig,
    config.OverlayConfig,
    config.SfxConfig,
    config.SfxCue,
    config.SfxParams,
    config.StingCue,
    config.AutoDirect,
    config.MusicCue,
    config.ComposeConfig,
    config.ComposeInstrument,
    config.DuckConfig,
    config.SceneMusic,
    config.AudioConfig,
    config.TransitionConfig,
    config.ChaptersConfig,
    config.MetadataConfig,
    config.ThumbnailConfig,
    translation.TranslationFile,
    translation.TranslationEntry,
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
        shown = "null" if default is None else str(default).lower() if isinstance(default, bool) else str(default)
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


def test_music_cookbook_sketches_are_valid_score_files_and_it_is_linked() -> None:
    from vidgen.studio import parse_music_score

    text = (ROOT / "docs" / "COOKBOOK-MUSIC.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", text, flags=re.S)
    assert len(blocks) == 5   # documentary, trance, synthwave, cosmic, cartoon
    for block in blocks:
        score = parse_music_score(yaml.safe_load(block), "COOKBOOK-MUSIC.md")
        assert score.loop and score.tracks
    assert "examples/gps-time-of-flight/README.md" in text and "music/README.md" in text
    for doc in ("docs/COOKBOOK.md", "README.md", "AGENTS.md"):
        assert "COOKBOOK-MUSIC.md" in (ROOT / doc).read_text(encoding="utf-8"), doc


GENETICS_TYPES = ("cross", "pedigree", "linkage_map", "karyotype", "mutation", "crispr", "dna_lab", "population", "gwas")


@pytest.mark.parametrize("kinds", [("cell", "molecule", "pathway", "cell_cycle", "metabolism"), GENETICS_TYPES, ("plot", "calculation"), ("orbit",), ("standard_model",)],
                         ids=["cell_biology", "genetics", "science_charts", "orbits", "particles"])
def test_science_sections_name_every_nested_option(kinds: tuple[str, ...]) -> None:
    """Steps 210, 220, 227 and 229: every param of the cell-biology, the genetics, the science-chart
    and the orbit types, nested options too (an object's `coat`, a gene's `introns`, a node's marks' `domain`, a
    fit's `residuals`, a symbol's `from_scene`), is named in its CONFIG.md section."""
    from vidgen.describe import nested_models

    heads = {m.group(1): m.start() for m in re.finditer(r"^### `(\w+)`", CONFIG_MD, re.M)}
    starts = sorted(heads.values())
    missing = []
    with registry.isolated():
        extensions.load_builtins()
        for kind in kinds:
            start = heads[kind]
            section = CONFIG_MD[start:min([p for p in starts if p > start] or [len(CONFIG_MD)])]
            seen: set[type] = set()
            todo = [(registry.get(kind).params_model, "")]
            while todo:
                model, prefix = todo.pop()
                for name, info in model.model_fields.items():
                    shown = info.alias or name
                    if not re.search(rf"\b{re.escape(shown)}\b", section):   # `coat`, or {level, on: …}
                        missing.append(f"{kind}: {prefix}{shown}")
                    for nested in nested_models(info.annotation):
                        if nested not in seen:
                            seen.add(nested)
                            todo.append((nested, f"{prefix}{shown}."))
    assert not missing, missing


def test_cell_biology_cookbook_is_valid_and_linked(tmp_path: Path) -> None:
    """Step 210: the cell-biology cookbook's pattern validates, it names all five scene types and
    the README, the cookbook, the guide and the gallery point to it."""
    from vidgen.cli import validate_all
    from vidgen.project import Project

    text = (ROOT / "docs" / "COOKBOOK-CELL-BIOLOGY.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", text, flags=re.S)
    assert len(blocks) == 1
    scenes = yaml.safe_load(blocks[0])
    (tmp_path / "video.yaml").write_text(yaml.safe_dump({"title": "t", "scenes": scenes}), encoding="utf-8")
    problems, _ = validate_all(Project.load(tmp_path), keep_going=True)
    assert not problems, problems
    for kind in ("cell", "molecule", "pathway", "cell_cycle", "metabolism"):
        assert f"[`{kind}`](CONFIG.md#{kind})" in text, kind
    assert "examples/gene-to-secreted-protein/README.md" in text
    for doc in ("docs/COOKBOOK.md", "README.md", "AGENTS.md", "src/vidgen/data/guide/AGENTS.md", "docs/gallery/README.md"):
        assert "COOKBOOK-CELL-BIOLOGY.md" in (ROOT / doc).read_text(encoding="utf-8"), doc


def test_genetics_cookbook_is_valid_and_linked(tmp_path: Path) -> None:
    """Step 220: the genetics cookbook's pattern validates and is lint-clean for the genetics_*
    rules, it names all nine scene types and the README, the cookbook, the guide and the gallery
    point to it."""
    from vidgen.cli import validate_all
    from vidgen.lint.genetics_rule import genetics_issues
    from vidgen.project import Project

    text = (ROOT / "docs" / "COOKBOOK-GENETICS.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", text, flags=re.S)
    assert len(blocks) == 1
    scenes = yaml.safe_load(blocks[0])
    (tmp_path / "video.yaml").write_text(yaml.safe_dump({"title": "t", "scenes": scenes}, allow_unicode=True), encoding="utf-8")
    project = Project.load(tmp_path)
    problems, _ = validate_all(project, keep_going=True)
    assert not problems, problems
    for scene in project.config.scenes:
        assert not genetics_issues(project, scene.id, project.config.lint.rules), scene.id
    for kind in GENETICS_TYPES:
        assert f"[`{kind}`](CONFIG.md#{kind})" in text, kind
    assert "examples/cystic-fibrosis/README.md" in text
    for doc in ("docs/COOKBOOK.md", "README.md", "AGENTS.md", "src/vidgen/data/guide/AGENTS.md", "docs/gallery/README.md"):
        assert "COOKBOOK-GENETICS.md" in (ROOT / doc).read_text(encoding="utf-8"), doc


def test_science_charts_cookbook_is_valid_and_linked(tmp_path: Path) -> None:
    """Step 227: the science-charts cookbook's pattern validates and is lint-clean for the calc_*
    and plot_* rules, it names both types, and the README, the cookbook, the guide and the gallery
    point to it."""
    from vidgen.cli import validate_all
    from vidgen.lint.calc_rule import calc_issues
    from vidgen.lint.plot_rule import plot_issues
    from vidgen.project import Project

    text = (ROOT / "docs" / "COOKBOOK-SCIENCE-CHARTS.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", text, flags=re.S)
    assert len(blocks) == 1
    scenes = yaml.safe_load(blocks[0])
    (tmp_path / "video.yaml").write_text(yaml.safe_dump({"title": "t", "scenes": scenes}, allow_unicode=True), encoding="utf-8")
    project = Project.load(tmp_path)
    problems, _ = validate_all(project, keep_going=True)
    assert not problems, problems
    for scene in project.config.scenes:
        rules = project.config.lint.rules
        assert not calc_issues(project, scene.id, rules) and not plot_issues(project, scene.id, rules), scene.id
    for kind in ("plot", "calculation"):
        assert f"[`{kind}`](CONFIG.md#{kind})" in text, kind
    for rule in ("calc_numbers", "calc_units", "calc_sigfigs", "plot_units", "plot_log", "plot_errors", "plot_series", "plot_truncated",
                 "plot_conserved", "plot_fit_claims"):
        assert f"`{rule}`" in text, rule
    assert "examples/radioactive-decay/README.md" in text
    for doc in ("docs/COOKBOOK.md", "README.md", "AGENTS.md", "src/vidgen/data/guide/AGENTS.md", "docs/gallery/README.md"):
        assert "COOKBOOK-SCIENCE-CHARTS.md" in (ROOT / doc).read_text(encoding="utf-8"), doc


def test_orbits_cookbook_is_valid_and_linked(tmp_path: Path) -> None:
    """Step 235: the orbits cookbook's pattern validates and is lint-clean for the orbit_* and
    calc_* rules, it names the rules, and the README, the cookbook, the guide and the gallery
    point to it."""
    from vidgen.cli import validate_all
    from vidgen.lint.calc_rule import calc_issues
    from vidgen.lint.orbit_rule import orbit_issues
    from vidgen.project import Project

    text = (ROOT / "docs" / "COOKBOOK-ORBITS.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", text, flags=re.S)
    assert len(blocks) == 1
    scenes = yaml.safe_load(blocks[0])
    (tmp_path / "video.yaml").write_text(yaml.safe_dump({"title": "t", "scenes": scenes}, allow_unicode=True), encoding="utf-8")
    project = Project.load(tmp_path)
    problems, _ = validate_all(project, keep_going=True)
    assert not problems, problems
    for scene in project.config.scenes:
        rules = project.config.lint.rules
        assert not orbit_issues(project, scene.id, rules) and not calc_issues(project, scene.id, rules), scene.id
    for kind in ("orbit", "calculation", "plot"):
        assert f"[`{kind}`](CONFIG.md#{kind})" in text, kind
    for rule in ("orbit_period", "orbit_speed", "orbit_dv", "orbit_transfer", "orbit_distance", "orbit_date", "orbit_scale",
                 "orbit_conserved", "orbit_crash", "calc_numbers"):
        assert f"`{rule}`" in text, rule
    assert "examples/mars-transfer/README.md" in text
    for doc in ("docs/COOKBOOK.md", "README.md", "AGENTS.md", "src/vidgen/data/guide/AGENTS.md", "docs/gallery/README.md"):
        assert "COOKBOOK-ORBITS.md" in (ROOT / doc).read_text(encoding="utf-8"), doc


def test_docs_yaml_snippets_parse() -> None:
    for doc in ("docs/CONFIG.md", "docs/EXTENDING.md", "README.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        for block in re.findall(r"```yaml\n(.*?)```", text, flags=re.S):
            yaml.safe_load(block.replace("[...]", "[]"))
