"""examples/custom_scene: built-ins + a project scene type with nested params, a helper module,
a vertical variant and a post_render hook. Rendered at a tiny size in both orientations."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from vidgen.cli import check_project, main
from vidgen.project import Project

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "custom_scene"


def test_example_validates(capsys: pytest.CaptureFixture[str]) -> None:
    assert check_project(Project.load(EXAMPLE)) == []
    assert check_project(Project.load(EXAMPLE, variant="vertical")) == []
    assert main(["list-scenes", str(EXAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "gear_pair".ljust(len("code_walkthrough") + 2) + "extensions/gears.py" in out
    assert "    beats: 2 to 3 beats\n    front: Ring\n        teeth: int\n" in out


def test_nested_theme_color_is_checked(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("__pycache__", "build", "*.mp4", "*.srt", "*.txt"))
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["scenes"][1]["params"]["rear"]["color"] = "sprockett"
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    problems = check_project(Project.load(root))
    assert problems == [problems[0]] and problems[0].startswith("scenes[1].params.rear.color: unknown theme color 'sprockett'")


@pytest.mark.render
@pytest.mark.parametrize("variant", [None, "vertical"])
@pytest.mark.slow
def test_tiny_render_with_hook(tmp_path: Path, variant: str | None) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH")
    from vidgen.render.pipeline import render_project

    root = tmp_path / "proj"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("__pycache__", "build", "*.mp4", "*.srt", "*.txt"))
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["preview"] = {"width": 160, "height": 90, "fps": 5}
    data["variants"]["vertical"]["preview"] = {"width": 90, "height": 160}
    data["scenes"] = [s for s in data["scenes"] if s["id"] in ("pair", "outro")]
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    result = render_project(Project.load(root, variant=variant), preview=True, jobs=2)
    assert result.output.is_file() and result.rendered == ["pair", "outro"]
    summary = result.output.with_suffix(".txt").read_text(encoding="utf-8").splitlines()
    assert [line.split(":")[0] for line in summary] == ["pair", "outro"]
