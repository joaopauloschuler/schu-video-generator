"""`--json` output of validate, list-scenes and render (shapes documented in docs/CONFIG.md)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import minimal_config, write_files
from vidgen import __version__, cli, jsonout
from vidgen.cli import check_project, main, project_problems
from vidgen.errors import Problem, VidgenError
from vidgen.project import Project

ROOT = Path(__file__).resolve().parents[1]
CONFIG_MD = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
JSON_MD = CONFIG_MD[CONFIG_MD.index("## JSON output") :]
ENVELOPE = ["version", "vidgen", "command", "ok", "warnings"]
ONE_SCENE = {"title": "T", "scenes": [{"id": "a", "type": "text_card", "params": {"text": "x"}, "duration": 1}]}


def run_json(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any], str]:
    """Run the CLI; stdout must be exactly one JSON document. Returns (code, doc, stderr)."""
    code = main(argv)
    captured = capsys.readouterr()
    doc = json.loads(captured.out)
    assert captured.out.isascii()
    assert list(doc)[: len(ENVELOPE)] == ENVELOPE
    assert doc["version"] == jsonout.SCHEMA_VERSION == 1 and doc["vidgen"] == __version__
    assert (code == 0) == doc["ok"]
    if not doc["ok"]:
        assert set(doc["error"]) == {"kind", "message", "problems", "details"}
    return code, doc, captured.err


def documented(*keys: str) -> None:
    """Each key is named in the JSON section of docs/CONFIG.md."""
    for key in keys:
        assert re.search(rf"(?<![\w-]){re.escape(key)}(?![\w-])", JSON_MD), f"JSON key {key!r} not in docs/CONFIG.md"


# ----- Problem / VidgenError ---------------------------------------------------------------------


def test_problem_text_and_json() -> None:
    p = Problem("scenes[1].type", "unknown scene type 'x'")
    assert str(p) == "scenes[1].type: unknown scene type 'x'"
    assert str(p.in_variant("vertical")) == "[variant vertical] scenes[1].type: unknown scene type 'x'"
    assert str(Problem("", "boom")) == "boom"
    assert Problem("", "boom", "v").to_json() == {"location": None, "message": "boom", "variant": "v"}
    exc = VidgenError("msg", problems=[p], details={"a": 1})
    assert str(exc) == "msg" and exc.problems == [p] and exc.details == {"a": 1}
    assert VidgenError("plain").problems == [] and VidgenError("plain").details == {}


def test_config_errors_carry_locations(make_project) -> None:
    data = minimal_config(variants={"v": {"format": {"fps": -1}}})
    data["scenes"][0]["beats"][0]["id"] = "bad id"
    root = make_project(data)
    with pytest.raises(VidgenError) as info:
        Project.load(root)
    assert [p.location for p in info.value.problems] == ["scenes[0].beats[0].id"]
    data["scenes"][0]["beats"][0]["id"] = "ok_id"
    root = make_project(data)
    with pytest.raises(VidgenError) as info:
        Project.load(root, variant="v")
    assert [(p.location, p.variant) for p in info.value.problems] == [("format.fps", "v")]


# ----- validate ----------------------------------------------------------------------------------


def test_validate_json_ok(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(title="Ação ✓", variants={"vertical": {"format": {"width": 1080, "height": 1920}}}))
    (root / "audio").mkdir()
    (root / "audio" / "intro_b1.mp3").write_bytes(b"x")  # no hash -> stale
    (root / "audio" / "gone.mp3").write_bytes(b"x")  # no beat -> orphaned
    code, doc, _ = run_json(["validate", str(root), "--json"], capsys)
    assert code == 0 and doc["command"] == "validate" and "error" not in doc
    assert doc["title"] == "Ação ✓"  # escaped as ASCII on stdout, intact after parsing
    assert doc["project"] == str(root.resolve()) and doc["config_file"] == str((root / "video.yaml").resolve())
    assert (doc["scenes"], doc["beats"], doc["problems"]) == (2, 3, [])
    assert doc["estimated_duration"] == pytest.approx(Project.load(root).estimated_duration(), abs=0.01)
    assert doc["variants"] == [
        {"name": "vertical", "loaded": True, "estimated_duration": doc["estimated_duration"], "problems": 0, "language": None, "translations": None}
    ]
    assert (doc["language"], doc["translations"]) == (None, None)
    (audio,) = doc["audio"]  # the variant shares audio/
    assert (audio["variant"], audio["ok"], audio["stale"], audio["missing"]) == (None, 0, 1, 2)
    assert audio["dir"] == str((root / "audio").resolve())
    assert audio["orphaned"] == [str((root / "audio" / "gone.mp3").resolve())]
    assert audio["beats"][0] == {"scene": "intro", "beat": "intro_b1", "state": "stale"}
    documented(*doc, *doc["variants"][0], *audio, *audio["beats"][0])


def test_validate_json_variant_with_own_audio(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(variants={"de": {"voice": {"voice_id": "other"}}}))
    _, doc, _ = run_json(["validate", str(root), "--json"], capsys)
    assert [a["variant"] for a in doc["audio"]] == [None, "de"]
    assert doc["audio"][1]["dir"] == str((root / "audio" / "de").resolve())


def test_validate_json_problems_with_locations(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    data = minimal_config(variants={"v": {"scenes": [{"id": "x", "type": "text_card", "params": {}, "duration": 1}]}})
    data["scenes"][0]["type"] = "text_crd"
    data["scenes"][1]["params"] = {"text": "Main", "size": "huge"}
    root = make_project(data)
    code, doc, err = run_json(["validate", str(root), "--json"], capsys)
    assert code == 1 and not doc["ok"] and err == ""
    locations = [(p["location"], p["variant"]) for p in doc["problems"]]
    assert locations == [("scenes[0].type", None), ("scenes[1].params.size", None), ("scenes[0].params.text", "v")]
    assert doc["problems"][0]["message"].startswith("unknown scene type 'text_crd'; did you mean 'text_card'")
    assert doc["variants"][0]["problems"] == 1 and doc["title"] == "Test video"
    assert doc["error"]["kind"] == "error" and doc["error"]["problems"] == doc["problems"]
    assert doc["error"]["message"].startswith("video.yaml: invalid project\n  scenes[0].type: unknown")
    # The human output of the same project is unchanged.
    assert main(["validate", str(root)]) == 1
    human = capsys.readouterr().err
    assert human == f"error: {doc['error']['message']}\n"
    assert "  [variant v] scenes[0].params.text: Field required" in human


def test_validate_json_structural_error(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    data = minimal_config()
    data["scenes"][0]["beats"][0]["id"] = "bad id"
    data["colour"] = 1
    code, doc, _ = run_json(["validate", str(make_project(data)), "--json"], capsys)
    assert code == 1 and doc["title"] is None and doc["scenes"] is None and doc["variants"] == []
    assert sorted(p["location"] for p in doc["problems"]) == ["colour", "scenes[0].beats[0].id"]
    assert doc["error"]["message"].startswith("video.yaml: invalid config")


def test_validate_json_broken_variant_is_a_problem(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(variants={"broken": {"format": {"fps": -1}}, "fine": {"output": "f"}}))
    code, doc, _ = run_json(["validate", str(root), "--json"], capsys)
    assert code == 1 and doc["scenes"] == 2
    assert [(v["name"], v["loaded"], v["problems"]) for v in doc["variants"]] == [("broken", False, 1), ("fine", True, 0)]
    assert doc["variants"][0]["estimated_duration"] is None
    assert [(p["location"], p["variant"]) for p in doc["problems"]] == [("format.fps", "broken")]


def test_validate_json_project_not_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, doc, _ = run_json(["validate", str(tmp_path / "missing"), "--json"], capsys)
    assert code == 1 and doc["project"] is None
    assert doc["problems"] == [{"location": None, "message": f"project not found: {tmp_path / 'missing'}", "variant": None}]


CHECKS_EXT = """
import logging
from vidgen.api import *

@scene("checked")
class Checked(NarratedScene):
    class Params(SceneParams):
        data: str = "x.csv"

    @classmethod
    def validate_project(cls, params, project):
        logging.getLogger("vidgen.test").warning("checking %s", params.data)
        return ["data: file not found: x.csv", "something is off"]
"""


def test_validate_json_project_checks_and_warnings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "p"
    write_files(root, {"extensions/checks.py": CHECKS_EXT})
    (root / "video.yaml").write_text(
        yaml.safe_dump({"title": "T", "scenes": [{"id": "a", "type": "checked", "duration": 1}]}), encoding="utf-8"
    )
    _, doc, err = run_json(["validate", str(root), "--json"], capsys)
    assert [(p["location"], p["message"]) for p in doc["problems"]] == [
        ("scenes[0].params.data", "file not found: x.csv"),
        ("scenes[0].params", "something is off"),
    ]
    assert doc["warnings"] == [{"scene": None, "message": "checking x.csv"}]
    assert err == "warning: checking x.csv\n"  # still shown to a human watching stderr
    assert check_project(Project.load(root))[0] == "scenes[0].params.data: file not found: x.csv"


def test_extension_import_error_has_no_location(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "p"
    write_files(root, {"extensions/bad.py": "raise RuntimeError('nope')\n"})
    (root / "video.yaml").write_text(yaml.safe_dump(ONE_SCENE), encoding="utf-8")
    (problem,) = project_problems(Project.load(root))
    assert problem.location == "" and "bad.py" in problem.message
    _, doc, _ = run_json(["validate", str(root), "--json"], capsys)
    assert doc["problems"][0]["location"] is None and "RuntimeError: nope" in doc["problems"][0]["message"]


# ----- list-scenes -------------------------------------------------------------------------------


def test_list_scenes_json_builtins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    code, doc, _ = run_json(["list-scenes", "--json"], capsys)
    assert code == 0 and doc["project"] is None
    types = {t["name"]: t for t in doc["scene_types"]}
    assert list(types) == sorted(types) and {"title", "bullets", "image", "line_chart", "text_card"} <= set(types)
    bullets = types["bullets"]
    assert (bullets["origin"], bullets["builtin"], bullets["overrides_builtin"], bullets["beats"]) == ("builtin", True, False, None)
    assert bullets["doc"].startswith("``reveal: per_beat`` (default)")
    fields = {f["name"]: f for f in bullets["params"]}
    items = fields["items"]
    assert (items["type"], items["required"], items["default"]) == ("list[str | BulletItem]", True, None)
    assert items["doc"] == "The list items (at least one): text, or {text, icon}; item i appears at beat i."
    assert [(f["name"], f["type"]) for f in items["nested"][0]["fields"]] == [("text", "str"), ("icon", "icon | None")]
    assert (fields["reveal"]["type"], fields["reveal"]["default"]) == ("'per_beat' | 'all'", "per_beat")
    assert (fields["color"]["type"], fields["size"]["type"], fields["marker"]["default"]) == ("color", "size", "•")
    ken = {f["name"]: f for f in types["image"]["params"]}["ken_burns"]
    assert ken["type"] == "KenBurns | bool" and ken["default"] is False
    (nested,) = ken["nested"]
    assert nested["model"] == "KenBurns"
    focus = {f["name"]: f for f in nested["fields"]}["start_focus"]
    assert focus["default"] == [0.5, 0.5] and focus["doc"]
    # Every built-in param is documented.
    for t in doc["scene_types"]:
        for f in t["params"]:
            assert f["doc"], f"{t['name']}.{f['name']} has no docstring"
            assert all(g["doc"] for n in f["nested"] for g in n["fields"]), t["name"]
    documented(*doc, *bullets, *fields["items"], *nested)


LIST_EXT = """
from vidgen.api import *

@scene("pair")
class Pair(NarratedScene):
    beat_count = (2, None)

    class Params(SceneParams):
        n: int = Field(3, description="How many.")

@scene("free")
class Free(NarratedScene):
    beat_count = 1

@scene("text_card", override=True)
class MyCard(NarratedScene):
    \"\"\"My own card.\"\"\"
"""


def test_list_scenes_json_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "p"
    write_files(root, {"extensions/mine.py": LIST_EXT})
    (root / "video.yaml").write_text(yaml.safe_dump(ONE_SCENE), encoding="utf-8")
    _, doc, _ = run_json(["list-scenes", str(root), "--json"], capsys)
    assert doc["project"] == str(root.resolve())
    types = {t["name"]: t for t in doc["scene_types"]}
    pair, free, card = types["pair"], types["free"], types["text_card"]
    assert (pair["origin"], pair["builtin"]) == (str(Path("extensions") / "mine.py"), False)
    assert pair["beats"] == {"min": 2, "max": None, "text": "at least 2 beats"}
    assert pair["params"] == [{"name": "n", "type": "int", "required": False, "default": 3, "doc": "How many.", "nested": [], "aliases": []}]
    assert free["beats"] == {"min": 1, "max": 1, "text": "exactly 1 beat"} and free["params"] is None
    assert free["doc"] is None  # neither the class nor its module has a docstring
    assert (card["overrides_builtin"], card["doc"]) == (True, "My own card.")
    assert any("overrides the built-in" in w["message"] for w in doc["warnings"])


def test_list_scenes_human_output_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["list-scenes"]) == 0
    out = capsys.readouterr().out
    assert re.match(r"bar_chart +builtin\n    title: str = ''   \(also: heading\)\n    labels: list\[str\]\n", out)
    assert "        start_scale: float = 1.0\n" in out and "{" not in out.splitlines()[0]


# ----- errors ------------------------------------------------------------------------------------


def test_usage_error_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, doc, _ = run_json(["render", "--bogus", "--json"], capsys)
    assert code == 2 and doc["command"] == "render"
    assert doc["error"] == {"kind": "usage", "message": "unrecognized arguments: --bogus", "problems": [], "details": {}}
    code, doc, _ = run_json(["validate", "--json", "--jobs", "x"], capsys)
    assert code == 2 and doc["error"]["kind"] == "usage"


def test_usage_error_human(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["render", "--jobs", "x"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("usage: vidgen render") and "vidgen render: error: argument --jobs/-j: invalid int value: 'x'" in err


def test_command_without_json_flag(capsys: pytest.CaptureFixture[str]) -> None:
    code, doc, _ = run_json(["mcp", "--json"], capsys)
    assert code == 2 and doc["command"] == "mcp"


def test_render_error_json_without_rendering(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    code, doc, _ = run_json(["render", str(root), "--scene", "nope", "--json"], capsys)
    assert code == 1 and doc["command"] == "render" and doc["error"]["kind"] == "error"
    assert doc["error"]["message"].startswith("unknown scene(s): nope")
    code, doc, _ = run_json(["render", str(root), "--jobs", "0", "--json"], capsys)
    assert doc["error"]["message"] == "--jobs must be at least 1"


def test_internal_error_json(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def broken(args: Any) -> int:
        raise RuntimeError("bug here")

    monkeypatch.setattr(cli, "cmd_validate", broken)
    code, doc, _ = run_json(["validate", str(make_project()), "--json"], capsys)
    assert code == 1 and doc["error"]["kind"] == "internal" and doc["error"]["message"] == "RuntimeError: bug here"
    assert "Traceback" in doc["error"]["details"]["traceback"]
    with pytest.raises(RuntimeError):  # without --json a bug still shows its traceback
        main(["validate", str(make_project())])


@pytest.mark.slow
def test_json_is_valid_on_a_legacy_code_page(make_project) -> None:
    root = make_project(minimal_config(title="Ação → 😀"))
    proc = subprocess.run(
        [sys.executable, "-m", "vidgen", "validate", str(root), "--json"],
        capture_output=True,
        env={"PYTHONIOENCODING": "cp1252", "PATH": ""},
        check=True,
    )
    assert json.loads(proc.stdout.decode("ascii"))["title"] == "Ação → 😀"


def test_error_kinds_and_schema_version_documented() -> None:
    assert "currently **1**" in JSON_MD
    documented("usage", "error", "internal", "kind", "message", "problems", "details", "location", "variant")


# ----- render ------------------------------------------------------------------------------------


QUIET_EXT = """
from vidgen.api import *

@scene("lazy")
class Lazy(NarratedScene):
    def construct(self):
        with self.narrate(0):
            self.add(Square())

@scene("boom")
class Boom(NarratedScene):
    def construct(self):
        raise RuntimeError("kaput")
"""


@pytest.fixture
def render_project_dir(tmp_path: Path) -> Callable[[list[dict[str, Any]]], Path]:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not found on PATH")

    def make(scenes: list[dict[str, Any]]) -> Path:
        root = tmp_path / "proj"
        config = {
            "title": "JSON render",
            "output": "out",
            "format": {"width": 160, "height": 90, "fps": 5},
            "preview": {"width": 96, "height": 54, "fps": 5},
            "narration": {"pad": 0.2, "words_per_second": 3.0},
            "scenes": scenes,
        }
        write_files(root, {"extensions/quiet.py": QUIET_EXT})
        (root / "video.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        return root

    return make


@pytest.mark.render
@pytest.mark.slow
def test_render_json(render_project_dir: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    root = render_project_dir(
        [
            {"id": "a", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Hello there."}]},
            {"id": "b", "type": "lazy", "chapter": "Second", "beats": [{"text": "One two three."}, {"text": "Never said."}]},
        ]
    )
    code, doc, err = run_json(["render", str(root), "--preview", "--json", "--no-audio"], capsys)
    assert code == 0 and doc["command"] == "render"
    assert "[1/2] a: rendering" in err and "joining scenes" in err  # progress went to stderr
    assert (doc["project"], doc["variant"], doc["preview"], doc["audio"]) == (str(root.resolve()), None, True, False)
    assert doc["format"] == {"width": 96, "height": 54, "fps": 5}
    assert doc["outputs"] == {
        "video": str((root / "out_preview.mp4").resolve()),
        "subtitles": str((root / "out_preview.srt").resolve()),
        "timings": str((root / "build" / "preview" / "timings.json").resolve()),
        "frames": None,
        "chapters": str((root / "out_preview_chapters.txt").resolve()),
        "thumbnail": None,
    }
    intro, second = doc["chapters"]  # the intro chapter before the first chapter (DESIGN.md §52)
    assert (intro["title"], intro["intro"], intro["start"], second["title"], second["scene"]) == ("Intro", True, 0.0, "Second", "b")
    assert second["start"] == pytest.approx(doc["scenes"][1]["start"]) and second["end"] == pytest.approx(doc["duration"])
    assert any("at least 3" in w["message"] for w in doc["warnings"])  # YouTube's rules
    documented(*intro)
    assert all(Path(p).is_file() for p in doc["outputs"].values() if p is not None)
    timings = json.loads((root / "build" / "preview" / "timings.json").read_text(encoding="utf-8"))
    assert doc["duration"] == timings["duration"] and doc["elapsed"] > 0
    a, b = doc["scenes"]
    assert (a["id"], a["type"], a["status"], a["start"]) == ("a", "text_card", "rendered", 0.0)
    assert a["render_seconds"] > 0 and b["start"] == pytest.approx(a["duration"])
    assert a["duration"] + b["duration"] == pytest.approx(doc["duration"])
    assert [beat["id"] for beat in b["beats"]] == ["b_b1"]  # the second beat was never narrated
    assert set(a["beats"][0]) == {"id", "start", "end"}
    scene_warnings = [w for w in doc["warnings"] if w["scene"] == "b"]
    assert len(scene_warnings) == 1 and "b_b2" in scene_warnings[0]["message"]
    assert any(w["scene"] is None and "audio missing" in w["message"] for w in doc["warnings"])
    documented(*doc, *doc["outputs"], *a)

    code, doc, _ = run_json(["render", str(root), "--preview", "--json", "--no-audio", "--scene", "b"], capsys)
    assert [(s["id"], s["status"]) for s in doc["scenes"]] == [("a", "reused"), ("b", "rendered")]
    assert doc["scenes"][0]["render_seconds"] is None


@pytest.mark.render
@pytest.mark.slow
def test_render_json_failure_details(render_project_dir: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    root = render_project_dir(
        [
            {"id": "ok", "type": "text_card", "params": {"text": "x"}, "duration": 0.4},
            {"id": "bad", "type": "boom", "duration": 1},
        ]
    )
    code, doc, _ = run_json(["render", str(root), "--preview", "--json", "--keep-going"], capsys)
    assert code == 1 and doc["error"]["kind"] == "error"
    assert doc["error"]["message"].startswith("1 scene(s) failed: bad")
    (failed,) = doc["error"]["details"]["failed"]
    assert (failed["scene"], failed["exit_code"]) == ("bad", 2) and "RuntimeError: kaput" in failed["output_tail"]
    assert doc["error"]["details"]["rendered"] == ["ok"]
    documented("failed", "rendered", "exit_code", "output_tail")

    code, doc, _ = run_json(["render", str(root), "--preview", "--json", "--scene", "bad"], capsys)
    assert code == 1 and doc["error"]["message"].startswith("scene 'bad' failed (worker exit code 2):")
    assert [f["scene"] for f in doc["error"]["details"]["failed"]] == ["bad"]
    assert doc["error"]["details"]["rendered"] == []


def test_docs_mention_every_json_command() -> None:
    for command in cli.JSON_COMMANDS:
        assert f"### `vidgen {command} --json`" in JSON_MD, command
