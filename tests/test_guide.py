"""The author guide for AI agents (AGENTS.md / ``vidgen guide``, DESIGN.md §59): its topics
resolve, the command prints them, and everything it names exists: commands and their options,
scene types and their params, actions, presets, lint rules, sounds; every YAML snippet is a
valid project once wrapped into a config."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen import cli, config, extensions, registry
from vidgen.errors import VidgenError
from vidgen.guide import GUIDE_FILE, find_topic, guide_text, guide_topics
from vidgen.music import BUILTIN_BEDS as BEDS
from vidgen.presets import BUILTIN_PRESETS
from vidgen.project import Project
from vidgen.sfx import BUILTIN_SOUNDS

ROOT = Path(__file__).resolve().parents[1]
GUIDE = GUIDE_FILE.read_text(encoding="utf-8")
FENCE = re.compile(r"```(\w*)\n(.*?)```", re.S)
#: Example files copied into a snippet's project for the paths it names, by suffix.
ASSETS = {
    ".png": ROOT / "examples" / "gallery" / "assets" / "app.png",
    ".mp4": ROOT / "examples" / "gallery" / "assets" / "clip.webm",
    ".webm": ROOT / "examples" / "gallery" / "assets" / "clip.webm",
    ".py": ROOT / "examples" / "gallery" / "assets" / "train.py",
}


def topic_text(name: str) -> str:
    return find_topic(name).text


def table_rows(text: str) -> list[list[str]]:
    """The body rows of the Markdown tables in ``text``, as lists of cells."""
    rows = []
    for line in text.splitlines():
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return [r for r in rows if not all("`" not in c for c in r)]


def ticked(cell: str) -> list[str]:
    return re.findall(r"`([^`]+)`", cell)


# ----- topics and the command ----------------------------------------------------------------------


def test_root_agents_md_is_the_packaged_guide() -> None:
    root = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert root == GUIDE, "AGENTS.md differs from src/vidgen/data/guide/AGENTS.md: copy the packaged file over it"


def test_the_guide_is_package_data() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"data/guide/*"' in pyproject


def test_both_agent_files_say_who_they_are_for() -> None:
    assert "**use** vidgen" in GUIDE[:600] and "CLAUDE.md" in GUIDE[:600]
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in claude[:600] and "vidgen guide" in claude[:600]
    assert "vidgen guide" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_topics_are_unique_and_resolve_by_name_and_alias() -> None:
    topics = guide_topics()
    names = [t.name for t in topics] + [a for t in topics for a in t.aliases]
    assert len(names) == len(set(names))
    assert [t.name for t in topics][:3] == ["start", "workflow", "pacing"]
    for topic in topics:
        assert topic.text.startswith("## "), topic.name
        assert find_topic(topic.name) == topic and find_topic(topic.name.upper()) == topic
        for alias in topic.aliases:
            assert find_topic(alias) == topic
    required = {"workflow", "pacing", "social", "scenes", "design", "actions", "overlays", "audio", "examples", "outputs", "troubleshooting"}
    assert required <= {t.name for t in topics}
    intro = GUIDE[: GUIDE.find("<!-- topic:")]
    for topic in topics:   # the list of topics at the top names every one
        assert f"`{topic.name}`" in intro, topic.name


def test_unknown_topic_suggests() -> None:
    with pytest.raises(VidgenError, match=r"unknown guide topic 'scene'; did you mean 'scenes'"):
        find_topic("scene")


def test_guide_text_has_no_markers_and_every_section() -> None:
    text = guide_text()
    assert "<!--" not in text and "\n\n\n" not in text
    for topic in guide_topics():
        assert topic.text.strip() in text


def test_cli_prints_the_guide_a_topic_and_the_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["guide"]) == 0
    assert capsys.readouterr().out == guide_text()
    assert cli.main(["guide", "vertical"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("## Vertical and social videos") and "## Choosing the scene type" not in out
    assert cli.main(["guide", "--list"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("start") and "troubleshooting" in out


def test_cli_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["guide", "nope"]) == 1
    assert "unknown guide topic 'nope'" in capsys.readouterr().err
    assert cli.main(["guide", "scenes", "--list"]) == 1
    assert "either a TOPIC or --list" in capsys.readouterr().err


def test_cli_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["guide", "pacing", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] and doc["command"] == "guide" and doc["topic"] == "pacing"
    assert doc["title"] == "Storytelling and pacing" and doc["text"] == find_topic("pacing").text
    assert {"name": "social", "title": "Vertical and social videos", "aliases": list(find_topic("social").aliases)} in doc["topics"]
    assert Path(doc["path"]) == GUIDE_FILE
    assert cli.main(["guide", "--list", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["topic"] is None and doc["text"] is None and len(doc["topics"]) == len(guide_topics())
    assert cli.main(["guide", "nope", "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert not doc["ok"] and "unknown guide topic" in doc["error"]["message"]


# ----- everything the guide names exists ---------------------------------------------------------


def code_fragments() -> list[str]:
    """Inline code spans outside fenced blocks, and every line of the fenced blocks."""
    fragments = []
    for _, body in FENCE.findall(GUIDE):
        fragments.extend(body.splitlines())
    fragments.extend(re.findall(r"`([^`\n]+)`", FENCE.sub("", GUIDE)))
    return fragments


def test_every_command_and_option_named_exists() -> None:
    parser = cli.build_parser()
    subparsers = next(a for a in parser._actions if a.dest == "command").choices
    seen = set()
    for fragment in code_fragments():
        for match in re.finditer(r"\bvidgen ([a-z][a-z-]*)(.*?)(?=\bvidgen |$)", fragment):
            command, rest = match[1], match[2].split("#")[0]
            assert command in subparsers, f"`vidgen {command}` is not a command ({fragment!r})"
            seen.add(command)
            options = subparsers[command]._option_string_actions
            for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", rest):
                assert flag in options, f"`vidgen {command}` has no option {flag} ({fragment!r})"
    for command in ("validate", "storyboard", "lint", "tts", "render", "readback", "slides", "export", "thumbnail",
                    "translate-template", "imagegen", "list-icons", "list-themes", "list-scenes", "list-sfx", "list-music",
                    "schema", "guide", "init"):
        assert command in seen, f"the guide never shows `vidgen {command}`"


def builtin_types() -> dict[str, Any]:
    with registry.isolated():
        extensions.load_builtins()
        return {e.name: e for e in registry.all()}


def field_names(model: Any) -> set[str]:
    from vidgen.describe import other_names

    if model is None:
        return set()
    names = set()
    for name, field in model.model_fields.items():
        names |= {name, field.alias or name, *other_names(field)}
    return names


def test_scene_chooser_names_every_type_and_real_params() -> None:
    types = builtin_types()
    rows = table_rows(topic_text("scenes"))
    covered = set()
    for row in rows:
        names = ticked(row[1])
        assert names, row
        for name in names:
            assert name in types, f"unknown scene type {name!r} in the chooser"
            covered.add(name)
            fields = field_names(types[name].params_model)
            for param in ticked(row[2]):
                assert param.split(".")[0] in fields, f"{name} has no param {param!r}"
    assert covered == set(types), f"chooser misses {sorted(set(types) - covered)}"


def test_every_scene_type_has_a_snippet_in_the_chooser() -> None:
    blocks = [yaml.safe_load(body) for lang, body in FENCE.findall(topic_text("scenes")) if lang == "yaml"]
    shown = {scene["type"] for block in blocks for scene in block}
    missing = set(builtin_types()) - shown - {"diagram"}   # `flowchart` is the same type as `diagram`
    assert not missing and "flowchart" in shown, sorted(missing)


def test_presets_actions_rules_and_sounds_are_real_and_complete() -> None:
    presets = [ticked(r[0])[0] for r in table_rows(topic_text("design"))]
    assert set(presets) == set(BUILTIN_PRESETS)
    with registry.isolated():
        extensions.load_builtins()
        actions = {a.name for a in registry.all_actions()}
    action_rows = [ticked(r[0])[0] for r in table_rows(topic_text("actions"))]
    assert set(action_rows) == actions
    trouble = topic_text("troubleshooting")
    rules = [ticked(r[0])[0] for r in table_rows(trouble) if len(r) == 3]
    assert set(rules) == set(config.LINT_RULES)
    audio = topic_text("audio")
    for sound in BUILTIN_SOUNDS:
        assert f"`{sound}`" in audio, sound
    for bed in BEDS:
        assert f"`{bed}`" in audio, bed
    for name in re.findall(r"`(\w+)` \(", audio):   # "`whoosh` (something moves in)"
        assert name in BUILTIN_SOUNDS or name in BEDS, name


# ----- YAML snippets -----------------------------------------------------------------------------


def yaml_snippets() -> list[tuple[str, str]]:
    snippets = []
    for match in FENCE.finditer(GUIDE):
        if match[1] == "yaml":
            line = GUIDE.count("\n", 0, match.start()) + 1
            snippets.append((f"line{line}", match[2]))
    return snippets


def as_config(data: Any) -> dict[str, Any]:
    """A snippet as a whole config: a list of scenes, a (partial) config with ``scenes``, or a
    fragment of top-level keys (given one narrated scene)."""
    if isinstance(data, list):
        return {"title": "Guide snippet", "scenes": data}
    assert isinstance(data, dict), data
    if "scenes" in data:
        return {"title": "Guide snippet", **data}
    scene = {"id": "main", "type": "text_card", "params": {"text": "Snippet"}, "beats": [{"text": "A snippet of the guide."}]}
    return {"title": "Guide snippet", **data, "scenes": [scene]}


def asset_paths(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.startswith("assets/") else []
    if isinstance(value, dict):
        return [p for v in value.values() for p in asset_paths(v)]
    if isinstance(value, list):
        return [p for v in value for p in asset_paths(v)]
    return []


def test_the_guide_has_many_snippets() -> None:
    assert len(yaml_snippets()) >= 25
    examples = topic_text("examples")
    assert examples.count("```yaml") >= 10   # at least 5 before / after pairs


@pytest.mark.parametrize("name,body", yaml_snippets(), ids=[name for name, _ in yaml_snippets()])
def test_yaml_snippet_validates(name: str, body: str, tmp_path: Path) -> None:
    data = as_config(yaml.safe_load(body))
    for rel in asset_paths(data):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ASSETS[Path(rel).suffix], target)
    (tmp_path / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    try:
        project = Project.load(tmp_path)
    except VidgenError as exc:
        pytest.fail(f"snippet at {name} does not load:\n{exc}")
    problems, _ = cli.validate_all(project, keep_going=True)
    assert not problems, f"snippet at {name}:\n" + "\n".join(str(p) for p in problems)
