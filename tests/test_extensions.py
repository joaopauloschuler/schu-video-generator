"""Extension discovery/import, isolation between projects, theme defaults, validate/list-scenes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import minimal_config, write_files
from vidgen import extensions, hooks, registry, runtime
from vidgen.cli import check_project, main
from vidgen.errors import VidgenError
from vidgen.project import Project

PANEL = """
    from vidgen.api import *
    from .common import accent_color

    @scene("loss_panel")
    class LossPanel(NarratedScene):
        class Params(SceneParams):
            values: dict[str, float]
            best: str | None = None

        COLOR = accent_color()

        def construct(self):
            pass
"""

COMMON = """
    from vidgen.api import current_theme

    LOADED = []

    def accent_color():
        return current_theme().color("accent")
"""


def config_with(*scenes: dict, **overrides) -> dict:
    return minimal_config(scenes=list(scenes), **overrides)


def scene(id: str, type: str, **params) -> dict:
    return {"id": id, "type": type, "params": params, "beats": [{"text": f"{id} beat"}]}


@pytest.fixture
def ext_project(make_project):
    """Make a project with extension files: ``ext_project({"extensions/x.py": src}, config)``."""

    def make(files: dict[str, str], data: dict | None = None, folder: str = "proj") -> Project:
        root = make_project(data or config_with(scene("a", "text_card", text="hi")), folder=folder)
        write_files(root, files)
        return Project.load(root)

    return make


def test_discover_files_packages_sorted_skips_private(tmp_path: Path) -> None:
    write_files(
        tmp_path,
        {
            "zeta.py": "",
            "alpha.py": "",
            "_private.py": "raise RuntimeError('must not import')",
            "pkg/__init__.py": "",
            "_hidden_pkg/__init__.py": "",
            "data/readme.txt": "not a package",
            "notes.txt": "",
        },
    )
    assert extensions.discover(tmp_path) == ["alpha", "pkg", "zeta"]


def test_load_extensions_relative_imports_and_order(ext_project) -> None:
    order_src = "from .common import LOADED\nLOADED.append(__name__.rsplit('.', 1)[-1])\n"
    project = ext_project(
        {
            "extensions/common.py": COMMON,
            "extensions/panel.py": PANEL,
            "extensions/b_second.py": order_src,
            "extensions/a_first.py": order_src,
            "extensions/_private.py": "raise RuntimeError('must not import')",
            "extensions/tools/__init__.py": "from .shapes import make_box\nfrom ..common import LOADED\nLOADED.append('tools')\n",
            "extensions/tools/shapes.py": "def make_box():\n    return 'box'\n",
        }
    )
    with extensions.project_session(project):
        entry = registry.get("loss_panel")
        assert entry.origin == "extensions/panel.py"
        assert entry.cls.COLOR == runtime.current_theme().color("accent")
        common = sys.modules[f"{extensions.package_name(project)}.common"]
        assert common.LOADED == ["a_first", "b_second", "tools"]
    assert registry.find("loss_panel") is None
    assert not [n for n in sys.modules if n.startswith(extensions.PACKAGE_PREFIX)]
    assert str(project.root) not in sys.path


def test_package_name_is_sanitised(make_project) -> None:
    project = Project.load(make_project(folder="My Video-2"))
    assert extensions.package_name(project) == "vidgen_ext_my_video_2"


def test_missing_default_dir_is_skipped(make_project) -> None:
    project = Project.load(make_project())
    assert extensions.load_extensions(project) == []


def test_missing_explicit_dir_errors(make_project) -> None:
    project = Project.load(make_project(minimal_config(extensions=["ext", "more"])))
    (project.root / "ext").mkdir()
    with pytest.raises(VidgenError, match="extensions directory 'more' not found"):
        extensions.extension_dirs(project)


def test_explicit_dir_that_is_a_file_errors(make_project) -> None:
    project = Project.load(make_project(minimal_config(extensions=["ext"])))
    (project.root / "ext").write_text("", encoding="utf-8")
    with pytest.raises(VidgenError, match="not a directory"):
        extensions.extension_dirs(project)


def test_multiple_dirs_share_one_package(ext_project) -> None:
    project = ext_project(
        {"lib/common.py": COMMON, "scenes_ext/panel.py": PANEL},
        config_with(scene("a", "loss_panel", values={"x": 1}), extensions=["lib", "scenes_ext"]),
    )
    with extensions.project_session(project):
        assert registry.get("loss_panel").origin == "scenes_ext/panel.py"


def test_same_module_in_two_dirs_errors(ext_project) -> None:
    project = ext_project({"a/x.py": "", "b/x.py": ""}, config_with(scene("s", "text_card", text="t"), extensions=["a", "b"]))
    with pytest.raises(VidgenError, match="'x' exists in two extension directories"):
        with extensions.project_session(project):
            pass


def test_syntax_error_reports_file(ext_project) -> None:
    project = ext_project({"extensions/broken.py": "def oops(:\n    pass\n"})
    with pytest.raises(VidgenError) as info:
        with extensions.project_session(project):
            pass
    message = str(info.value)
    assert message.startswith("error while importing extension extensions/broken.py")
    assert "broken.py\", line 1" in message.splitlines()[1] and "SyntaxError" in message
    assert "importlib" not in message


def test_runtime_error_reports_traceback(ext_project) -> None:
    project = ext_project(
        {"extensions/helper.py": "def fail():\n    raise KeyError('nope')\n", "extensions/user.py": "from .helper import fail\nfail()\n"}
    )
    with pytest.raises(VidgenError) as info:
        with extensions.project_session(project):
            pass
    message = str(info.value)
    assert "extensions/user.py" in message.splitlines()[0]
    assert "helper.py" in message and "KeyError: 'nope'" in message
    assert "<frozen" not in message


def test_collision_between_extension_files(ext_project) -> None:
    src = "from vidgen.api import *\n@scene('same')\nclass S(NarratedScene):\n    pass\n"
    project = ext_project({"extensions/one.py": src, "extensions/two.py": src})
    with pytest.raises(VidgenError) as info:
        with extensions.project_session(project):
            pass
    assert "extensions/one.py" in str(info.value) and "extensions/two.py" in str(info.value)


def test_isolation_between_projects_and_reload(ext_project) -> None:
    hook_src = "from vidgen.api import *\n@hook('post_render')\ndef mark(ctx):\n    ctx.data.setdefault('seen', []).append('{name}')\n"
    p1 = ext_project(
        {"extensions/panel.py": PANEL, "extensions/common.py": COMMON, "extensions/h.py": hook_src.format(name="p1")},
        folder="p1",
    )
    p2 = ext_project(
        {
            "extensions/other.py": "from vidgen.api import *\n@scene('other')\nclass O(NarratedScene):\n    pass\n",
            "extensions/h.py": hook_src.format(name="p2"),
        },
        folder="p2",
    )
    for _ in range(2):  # loading the same projects again works (fresh modules each time)
        with extensions.project_session(p1):
            assert registry.find("loss_panel") and not registry.find("other")
            assert hooks.dispatch("post_render", p1).data["seen"] == ["p1"]
        with extensions.project_session(p2):
            assert registry.find("other") and not registry.find("loss_panel")
            assert hooks.dispatch("post_render", p2).data["seen"] == ["p2"]
    assert registry.find("other") is None and hooks.registered() == []
    assert not runtime.has_context()


def test_activate_replaces_previous_project(ext_project) -> None:
    p1 = ext_project({"extensions/panel.py": PANEL, "extensions/common.py": COMMON}, folder="p1")
    p2 = ext_project({}, folder="p2")
    theme = extensions.activate(p1)
    assert runtime.current_theme() is theme and registry.find("loss_panel")
    extensions.activate(p2)
    assert runtime.current_project() is p2 and registry.find("loss_panel") is None
    assert registry.find("text_card") is not None


def test_theme_defaults_precedence(ext_project) -> None:
    project = ext_project(
        {
            "extensions/tokens.py": """
                from vidgen.api import *
                register_theme_defaults({"k2": "#F2A541", "accent": "#000001", "text": "#000002"}, sizes={"huge": 90})
                K2 = current_theme().color("k2")
            """
        },
        config_with(scene("a", "text_card", text="t"), theme={"colors": {"text": "#ABCDEF"}}),
    )
    with extensions.project_session(project) as theme:
        assert theme.color("k2") == "#F2A541"  # registered default
        assert theme.color("accent") == "#000001"  # registered default beats built-in
        assert theme.color("text") == "#ABCDEF"  # video.yaml wins
        assert theme.size("huge") == 90
        assert sys.modules[f"{extensions.package_name(project)}.tokens"].K2 == "#F2A541"
    # a new session gets a fresh theme: registered defaults do not leak
    with extensions.project_session(Project.load(project.root.parent / "proj")) as theme:
        assert theme.color("k2") == "#F2A541"
    other = ext_project({}, folder="other")
    with extensions.project_session(other) as theme, pytest.raises(VidgenError, match="unknown theme color 'k2'"):
        theme.color("k2")


def test_register_theme_defaults_rejects_non_hex(ext_project) -> None:
    project = ext_project({"extensions/t.py": "from vidgen.api import *\nregister_theme_defaults({'x': 'red'})\n"})
    with pytest.raises(VidgenError, match="must be a hex color"):
        with extensions.project_session(project):
            pass


def test_override_builtin_from_extension(ext_project) -> None:
    project = ext_project(
        {"extensions/card.py": "from vidgen.api import *\n@scene('text_card', override=True)\nclass Mine(NarratedScene):\n    pass\n"}
    )
    with extensions.project_session(project):
        entry = registry.get("text_card")
        assert entry.origin == "extensions/card.py" and entry.overrides is not None
    assert registry.get("text_card").builtin


# ----- check_project / CLI -----------------------------------------------------------------------------


def test_check_project_reports_unknown_types_and_params(ext_project) -> None:
    project = ext_project(
        {"extensions/panel.py": PANEL, "extensions/common.py": COMMON},
        config_with(
            scene("a", "text_card", text="ok"),
            scene("b", "loss_pannel"),
            scene("c", "loss_panel", values={"x": "high"}, colour="red"),
            scene("d", "text_card"),
        ),
    )
    problems = check_project(project)
    assert problems[0].startswith("scenes[1].type: unknown scene type 'loss_pannel'; did you mean 'loss_panel'?")
    assert "known types: bar_chart, " in problems[0] and ", loss_panel, network, pie, process, quote, scatter, stat, table, text_card, timeline, title)" in problems[0]
    assert any(p.startswith("scenes[2].params.values.x:") for p in problems)
    assert "scenes[2].params.colour: Extra inputs are not permitted" in problems
    assert "scenes[3].params.text: Field required" in problems
    assert registry.find("loss_panel") is None  # nothing leaked


def test_check_project_import_error(ext_project) -> None:
    project = ext_project({"extensions/broken.py": "import does_not_exist_anywhere\n"})
    (problem,) = check_project(project)
    assert "extensions/broken.py" in problem and "ModuleNotFoundError" in problem


def test_validate_cli_with_extensions(ext_project, capsys: pytest.CaptureFixture[str]) -> None:
    project = ext_project(
        {"extensions/panel.py": PANEL, "extensions/common.py": COMMON},
        config_with(scene("a", "loss_panel", values={"x": 1.5}, best="x")),
    )
    assert main(["validate", str(project.root)]) == 0
    assert capsys.readouterr().out.endswith("ok\n")


def test_validate_cli_reports_variant_problems(ext_project, capsys: pytest.CaptureFixture[str]) -> None:
    data = config_with(
        scene("a", "text_card", text="t"),
        variants={"short": {"scenes": [scene("x", "text_cart", text="t"), scene("y", "unknown_thing")]}},
    )
    project = ext_project({}, data)
    assert main(["validate", str(project.root)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: video.yaml: invalid project\n")
    assert "  [variant short] scenes[0].type: unknown scene type 'text_cart'; did you mean 'text_card'" in err
    assert "[variant short] scenes[1].type: unknown scene type 'unknown_thing'" in err


def test_validate_cli_duplicate_problems_reported_once(ext_project, capsys: pytest.CaptureFixture[str]) -> None:
    data = config_with(scene("a", "nope"), variants={"v": {"format": {"fps": 24}}})
    project = ext_project({}, data)
    assert main(["validate", str(project.root)]) == 1
    err = capsys.readouterr().err
    assert err.count("unknown scene type 'nope'") == 1 and "[variant v]" not in err


def test_list_scenes_with_project(ext_project, capsys: pytest.CaptureFixture[str]) -> None:
    project = ext_project(
        {
            "extensions/panel.py": PANEL,
            "extensions/common.py": COMMON,
            "extensions/free.py": "from vidgen.api import *\n@scene('free_form')\nclass F(NarratedScene):\n    pass\n",
            "extensions/card.py": "from vidgen.api import *\n@scene('text_card', override=True)\nclass Mine(NarratedScene):\n    pass\n",
        }
    )
    assert main(["list-scenes", str(project.root)]) == 0
    captured = capsys.readouterr()
    assert "warning: extensions/card.py: scene type 'text_card' overrides the built-in" in captured.err
    lines = captured.out.splitlines()
    free = next(i for i, line in enumerate(lines) if line.startswith("free_form"))
    assert lines[free].split() == ["free_form", "extensions/free.py"]
    assert lines[free + 1] == "    params: free-form (no Params model)"
    assert any(line.split() == ["loss_panel", "extensions/panel.py"] for line in lines)
    assert "    values: dict[str, float]" in lines
    assert "    best: str | None = None" in lines
    assert any(line.startswith("text_card") and line.endswith("extensions/card.py  (overrides builtin)") for line in lines)
    assert registry.find("loss_panel") is None


def test_list_scenes_builtins_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["list-scenes"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("bar_chart   builtin\n")
    assert "\ntext_card   builtin\n    text: str\n    size: size = 'title'\n    color: color = 'text'\n" in out
    assert "\ntitle       builtin\n" in out


def test_list_scenes_explicit_missing_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list-scenes", str(tmp_path / "nope")]) == 1
    assert "project not found" in capsys.readouterr().err


def test_promotion_extension_module_works_as_builtin(ext_project, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import importlib.util

    source = "from vidgen.api import *\n@scene('promoted')\nclass Promoted(NarratedScene):\n    class Params(SceneParams):\n        n: int = 1\n"
    project = ext_project({"extensions/promoted.py": source})
    with extensions.project_session(project):
        assert registry.get("promoted").origin == "extensions/promoted.py"

    # The same file, imported as a module of the vidgen.scenes package, registers as a built-in.
    monkeypatch.setattr(registry, "_builtins", dict(registry._builtins))
    path = tmp_path / "promoted.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("vidgen.scenes.promoted_copy", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    entry = registry.get("promoted")
    assert entry.builtin and entry.params_model.model_fields["n"].default == 1
