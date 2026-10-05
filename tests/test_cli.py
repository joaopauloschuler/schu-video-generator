"""CLI: validate, init, stubs, error reporting."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import minimal_config
from vidgen import __version__
from vidgen.cli import main
from vidgen.config import parse_config


def test_validate_ok(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(variants={"vertical": {"format": {"width": 1080, "height": 1920}}}))
    assert main(["validate", str(root)]) == 0
    out = capsys.readouterr().out
    assert "title:     Test video" in out
    assert "scenes:    2" in out
    assert "beats:     3" in out
    assert "duration:  ~0:04" in out
    assert "variants:  vertical" in out


def test_validate_bad_config(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    data = minimal_config()
    data["scenes"][0]["beats"][0]["id"] = "bad id"
    root = make_project(data)
    assert main(["validate", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: video.yaml: invalid config\n")
    assert "scenes[0].beats[0].id" in captured.err
    assert "Traceback" not in captured.err


def test_validate_checks_every_variant(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(variants={"broken": {"format": {"fps": -1}}}))
    assert main(["validate", str(root)]) == 1
    assert "variant 'broken'" in capsys.readouterr().err


def test_validate_defaults_to_cwd(make_project, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(make_project())
    assert main(["validate"]) == 0


def test_missing_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(tmp_path / "missing")]) == 1
    assert capsys.readouterr().err.startswith("error: project not found")


@pytest.mark.parametrize(("argv", "step"), [(["render", "--preview"], 4)])
def test_not_implemented_commands(argv: list[str], step: int, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(argv) == 1
    assert f"not implemented yet (step {step})" in capsys.readouterr().err


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_init_scaffold(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "my_new-video"
    assert main(["init", str(target)]) == 0
    assert (target / "video.yaml").is_file()
    assert (target / "assets").is_dir()
    assert (target / "extensions").is_dir()
    assert not list((target / "extensions").glob("*.py"))  # example must not be auto-imported
    assert list((target / "extensions").glob("example.py*"))
    data = yaml.safe_load((target / "video.yaml").read_text(encoding="utf-8"))
    cfg = parse_config(data)
    assert cfg.title == "My New Video"
    assert [s.type for s in cfg.scenes] == ["title", "bullets"]
    capsys.readouterr()


@pytest.mark.xfail(reason="built-in scene types 'title' and 'bullets' arrive in Step 5", strict=True)
def test_init_scaffold_validates(tmp_path: Path) -> None:
    target = tmp_path / "scaffold"
    assert main(["init", str(target)]) == 0
    assert main(["validate", str(target)]) == 0


def test_init_into_empty_existing_dir(tmp_path: Path) -> None:
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "video.yaml").is_file()


def test_init_refuses_non_empty_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 1
    assert "not an empty directory" in capsys.readouterr().err
    assert not (tmp_path / "video.yaml").exists()
