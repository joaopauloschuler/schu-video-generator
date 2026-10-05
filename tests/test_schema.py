"""`vidgen schema`: the JSON Schema of video.yaml agrees with `vidgen validate`."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from conftest import minimal_config, write_files
from vidgen import extensions, registry, schema
from vidgen.cli import main, project_problems
from vidgen.errors import VidgenError
from vidgen.project import Project, deep_merge
from vidgen.theme import Theme

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted(p for p in (ROOT / "examples").iterdir() if (p / "video.yaml").is_file())
TEMPLATE = ROOT / "src" / "vidgen" / "templates" / "minimal" / "video.yaml"
Validator = jsonschema.Draft202012Validator


def cli_schema(argv: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """Run ``vidgen schema ...``; stdout must be exactly one (ASCII) JSON document."""
    assert main(["schema", *argv]) == 0
    out = capsys.readouterr().out
    assert out.isascii()
    doc = json.loads(out)
    Validator.check_schema(doc)
    return doc


def errors(doc: dict[str, Any], instance: Any) -> list[str]:
    """Schema errors as ``path: message`` lines."""
    return [
        f"{'.'.join(map(str, e.absolute_path))}: {e.message}"
        for e in Validator(doc).iter_errors(instance)
    ]


@pytest.fixture(scope="module")
def builtin_schema() -> dict[str, Any]:
    with registry.isolated():
        extensions.load_builtins()
        return schema.config_schema(registry.all(), [Theme()])


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ----- the examples validate ---------------------------------------------------------------------


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_examples_validate_against_their_schema(example: Path, capsys: pytest.CaptureFixture[str]) -> None:
    doc = cli_schema([str(example)], capsys)
    data = load_yaml(example / "video.yaml")
    assert errors(doc, data) == []
    for name, override in data.get("variants", {}).items():
        assert errors(doc, deep_merge(data, override)) == [], name


def test_template_validates_against_builtin_schema(builtin_schema: dict[str, Any]) -> None:
    data = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8").replace("__TITLE__", '"T"'))
    assert errors(builtin_schema, data) == []


def test_extension_types_are_not_in_builtin_schema(builtin_schema: dict[str, Any]) -> None:
    data = load_yaml(ROOT / "examples" / "kphi3" / "video.yaml")
    assert any("is not one of" in e for e in errors(builtin_schema, data))


# ----- schema and `vidgen validate` agree ----------------------------------------------------------


def scene(**fields: Any) -> dict[str, Any]:
    return {"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "Hi."}], **fields}


INVALID: dict[str, dict[str, Any]] = {
    "unknown type": minimal_config(scenes=[scene(type="nope")]),
    "missing required param": minimal_config(scenes=[scene(type="title", params={})]),
    "params omitted but required": minimal_config(scenes=[{"id": "s", "type": "title", "beats": [{"text": "a"}]}]),
    "wrong param type": minimal_config(scenes=[scene(params={"text": 3})]),
    "unknown param": minimal_config(scenes=[scene(params={"text": "x", "colour": "text"})]),
    "bad literal": minimal_config(scenes=[scene(type="bullets", params={"items": ["a"], "reveal": "later"})]),
    "unknown theme color": minimal_config(scenes=[scene(params={"text": "x", "color": "pink"})]),
    "bad hex color": minimal_config(scenes=[scene(params={"text": "x", "color": "#12"})]),
    "unknown theme size": minimal_config(scenes=[scene(params={"text": "x", "size": "huge"})]),
    "negative size": minimal_config(scenes=[scene(params={"text": "x", "size": -3})]),
    "nested model field": minimal_config(
        scenes=[scene(type="image", params={"path": "a.png", "ken_burns": {"start_scale": 9}})]
    ),
    "line chart with one x": minimal_config(
        scenes=[scene(type="line_chart", params={"x": [1], "series": {"a": [1]}})]
    ),
    "line chart without series": minimal_config(
        scenes=[scene(type="line_chart", params={"x": [1, 2], "series": {}})]
    ),
    "odd width": minimal_config(format={"width": 1919}),
    "silent scene without duration": minimal_config(scenes=[scene(beats=[])]),
    "narrated scene with duration": minimal_config(scenes=[scene(duration=2)]),
    "unknown top-level key": minimal_config(titel="x"),
    "bad beat id": minimal_config(scenes=[scene(beats=[{"id": "a-b", "text": "x"}])]),
    "bad theme color key": minimal_config(theme={"colors": {"my-color": "#fff"}}),
    "bad variant name": minimal_config(variants={"a-b": {}}),
    "unknown key in variant": minimal_config(variants={"v": {"formatt": {}}}),
    "nested variants": minimal_config(variants={"v": {"variants": {}}}),
    "invalid scene in variant": minimal_config(variants={"v": {"scenes": [scene(type="nope")]}}),
}

VALID: dict[str, dict[str, Any]] = {
    "minimal": minimal_config(),
    "beat ids omitted or null": minimal_config(scenes=[scene(beats=[{"text": "a"}, {"id": None, "text": "b"}])]),
    "silent scene": minimal_config(scenes=[scene(beats=[], duration=2)]),
    "silent scene, beats omitted": minimal_config(scenes=[{"id": "s", "type": "text_card", "params": {"text": "x"}, "duration": 1}]),
    "narrated, duration null": minimal_config(scenes=[scene(duration=None)]),
    "theme tokens and hex": minimal_config(scenes=[scene(params={"text": "x", "color": "#FFAA00", "size": 40})]),
    "project theme color": minimal_config(
        theme={"colors": {"brand": "#123456"}, "sizes": {"big": 70}},
        scenes=[scene(params={"text": "x", "color": "brand", "size": "big"})],
    ),
    "partial variant": minimal_config(variants={"v": {"format": {"width": 1080}, "voice": {"settings": {"style": 0.2}}}}),
    "variant theme color": minimal_config(
        variants={"v": {"theme": {"colors": {"night": "#000000"}}, "scenes": [scene(params={"text": "x", "color": "night"})]}}
    ),
    "line chart": minimal_config(
        scenes=[scene(type="line_chart", params={"x": ["a", "b"], "series": [{"name": "s", "values": [1, 2]}]})]
    ),
    "palette colors": minimal_config(scenes=[scene(type="bar_chart", params={"labels": ["a"], "values": [1], "colors": "palette"})]),
}


def project_errors(tmp_path: Path, data: dict[str, Any]) -> list[str]:
    """What `vidgen validate` reports (config, scene types and params of base + variants)."""
    (tmp_path / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    try:
        project = Project.load(tmp_path)
        problems = [str(p) for p in project_problems(project)]
        for name in project.config.variants:
            problems += [str(p) for p in project_problems(Project.load(tmp_path, variant=name))]
    except VidgenError as exc:
        return [str(exc)]
    return problems


def schema_for(tmp_path: Path, data: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    (tmp_path / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return cli_schema([str(tmp_path)], capsys)


@pytest.mark.parametrize("case", INVALID, ids=str)
def test_invalid_configs_are_rejected_by_both(case: str, tmp_path: Path) -> None:
    data = INVALID[case]
    assert project_errors(tmp_path, data), "vidgen validate accepts it"
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), schema.project_themes(None, Theme()))
    assert errors(doc, data), "the schema accepts it"


@pytest.mark.parametrize("case", VALID, ids=str)
def test_valid_configs_are_accepted_by_both(case: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = VALID[case]
    assert project_errors(tmp_path, data) == []
    assert errors(schema_for(tmp_path, data, capsys), data) == []


def test_theme_tokens_come_from_the_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = VALID["project theme color"]
    doc = schema_for(tmp_path, data, capsys)
    color = doc["$defs"]["scene.text_card"]["properties"]["color"]
    assert color["x-vidgen-theme"] == "color"
    assert "brand" in color["anyOf"][1]["enum"] and "primary" in color["anyOf"][1]["enum"]
    # Without the project, "brand" is unknown.
    assert errors(schema.config_schema([registry.get("text_card")], [Theme()]), data)


def test_extension_theme_defaults_and_beat_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_files(
        tmp_path,
        {
            "extensions/ext.py": """
                from vidgen.api import *

                register_theme_defaults({"k2": "#F2A541"})
                print("importing ext")  # must not end up in the schema output

                @scene("pair")
                class Pair(NarratedScene):
                    beat_count = (2, 3)

                    class Params(SceneParams):
                        color: ThemeColor = "k2"

                    def construct(self):
                        pass
            """,
        },
    )
    two = [{"text": "a"}, {"text": "b"}]
    data = minimal_config(scenes=[{"id": "p", "type": "pair", "params": {"color": "k2"}, "beats": two}])
    doc = schema_for(tmp_path, data, capsys)
    assert errors(doc, data) == []
    one, four = copy.deepcopy(data), copy.deepcopy(data)
    one["scenes"][0]["beats"] = two[:1]
    four["scenes"][0]["beats"] = two * 2
    silent = copy.deepcopy(data)
    del silent["scenes"][0]["beats"]
    silent["scenes"][0]["duration"] = 1
    for bad in (one, four, silent):
        assert errors(doc, bad)
        assert project_errors(tmp_path, bad)


# ----- command line ------------------------------------------------------------------------------


def test_scene_option(capsys: pytest.CaptureFixture[str]) -> None:
    doc = cli_schema([str(ROOT / "examples" / "custom_scene"), "--scene", "gear_pair"], capsys)
    assert doc["title"] == "gear_pair params" and "Ring" in doc["$defs"]
    assert "exactly" not in doc["description"] and "2 to 3 beats" in doc["description"]
    ring = {"teeth": 44, "color": "chainring"}
    assert errors(doc, {"front": ring, "rear": ring}) == []
    assert errors(doc, {"front": {**ring, "teeth": 3}, "rear": ring})
    assert errors(doc, {"front": {**ring, "color": "nope"}, "rear": ring})


def test_all_option_bundles_every_type(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no project here: built-ins only
    doc = cli_schema(["--all"], capsys)
    with registry.isolated():
        extensions.load_builtins()
        names = [e.name for e in registry.all()]
    assert doc["properties"]["type"]["enum"] == names
    assert all(f"scene.{name}" in doc["$defs"] for name in names)
    assert errors(doc, scene()) == []
    assert errors(doc, scene(type="title", params={"text": "x"}))


def test_default_is_the_whole_config(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    doc = cli_schema([], capsys)
    assert doc["title"] == "vidgen video.yaml" and doc["required"] == ["title", "scenes"]
    assert doc["$schema"] == schema.DIALECT


def test_unknown_scene_type(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema", str(ROOT / "examples" / "minimal"), "--scene", "titel"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "did you mean 'title'" in captured.err


def test_json_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    example = ROOT / "examples" / "minimal"
    assert main(["schema", str(example), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "schema" and doc["ok"] and doc["project"] == str(example.resolve())
    Validator.check_schema(doc["schema"])
    assert main(["schema", str(example), "--scene", "nope", "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["error"]["kind"] == "error" and "unknown scene type 'nope'" in doc["error"]["message"]
    assert main(["schema", "--scene", "title", "--all", "--json"]) == 2
    doc = json.loads(capsys.readouterr().out)
    assert doc["error"]["kind"] == "usage"


def test_invalid_config_still_gives_a_schema(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_files(
        tmp_path,
        {
            "ext/x.py": """
                from vidgen.api import *

                @scene("mine")
                class Mine(NarratedScene):
                    def construct(self):
                        pass
            """,
            "video.yaml": """
                extensions: [ext]
                theme: {colors: {brand: "#111111"}}
                scenes: [{id: a, type: mine, typo: 1}]
            """,
        },
    )
    assert main(["schema", str(tmp_path), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert "mine" in doc["schema"]["$defs"]["SceneConfig"]["properties"]["type"]["enum"]
    assert "brand" in json.dumps(doc["schema"]["$defs"]["scene.text_card"])
    assert any("is not valid" in w["message"] for w in doc["warnings"])


def test_unreadable_config_falls_back_to_defaults(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "video.yaml").write_text("title: [unclosed\n", encoding="utf-8")
    doc = cli_schema([str(tmp_path)], capsys)
    assert "title" in doc["$defs"]["SceneConfig"]["properties"]["type"]["enum"]


def test_missing_project_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema", str(tmp_path / "nowhere")]) == 1
    assert "project not found" in capsys.readouterr().err


def test_registry_is_restored(capsys: pytest.CaptureFixture[str]) -> None:
    before = registry.snapshot()
    cli_schema([str(ROOT / "examples" / "kphi3")], capsys)
    assert registry.snapshot() == before


def walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def test_only_standard_keywords_for_constraints(builtin_schema: dict[str, Any]) -> None:
    """pydantic's non-standard ``gt``/``ge`` must not leak (they would not be checked)."""
    assert not any({"gt", "ge", "lt", "le"} & set(node) for node in walk(builtin_schema) if "type" in node or "anyOf" in node)
