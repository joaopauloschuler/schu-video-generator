"""Project loading, variants and path helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import minimal_config
from vidgen.errors import VidgenError
from vidgen.project import Project, deep_merge


@pytest.mark.parametrize("name", ["video.yaml", "video.yml", "video.json"])
def test_discovers_config_file(make_project, name: str) -> None:
    root = make_project(name=name)
    project = Project.load(root)
    assert project.root == root.resolve()
    assert project.config_file.name == name
    assert project.config.title == "Test video"


def test_load_from_config_file_path(make_project) -> None:
    root = make_project()
    project = Project.load(root / "video.yaml")
    assert project.root == root.resolve()


def test_json_and_utf8(tmp_path: Path) -> None:
    data = minimal_config(title="João Gómez")
    (tmp_path / "video.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert Project.load(tmp_path).config.title == "João Gómez"


def test_no_config_file(tmp_path: Path) -> None:
    with pytest.raises(VidgenError, match="no config file in .*video.yaml, video.yml, video.json"):
        Project.load(tmp_path)


def test_multiple_config_files(make_project) -> None:
    root = make_project()
    make_project(name="video.json")
    with pytest.raises(VidgenError, match=r"more than one config file .*\(video.yaml, video.json\)"):
        Project.load(root)


def test_missing_project(tmp_path: Path) -> None:
    with pytest.raises(VidgenError, match="project not found"):
        Project.load(tmp_path / "nope")


def test_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "video.yaml").write_text("title: [unclosed\n", encoding="utf-8")
    with pytest.raises(VidgenError, match="video.yaml: invalid YAML"):
        Project.load(tmp_path)


def test_validation_error_names_file(make_project) -> None:
    root = make_project(minimal_config(bogus=1), name="video.yml")
    with pytest.raises(VidgenError, match="video.yml: invalid config"):
        Project.load(root)


def test_deep_merge() -> None:
    base = {"a": {"b": 1, "c": [1, 2]}, "d": 1}
    merged = deep_merge(base, {"a": {"c": [3]}, "e": {"f": 1}})
    assert merged == {"a": {"b": 1, "c": [3]}, "d": 1, "e": {"f": 1}}
    assert base == {"a": {"b": 1, "c": [1, 2]}, "d": 1}


def test_variant_deep_merged(make_project) -> None:
    data = minimal_config(
        format={"width": 1920, "height": 1080, "fps": 24},
        variants={"vertical": {"format": {"width": 1080, "height": 1920}, "theme": {"font": "Roboto"}}},
    )
    root = make_project(data)
    base = Project.load(root)
    vertical = Project.load(root, variant="vertical")
    assert (base.config.format.width, base.config.format.height) == (1920, 1080)
    assert vertical.variant == "vertical"
    assert (vertical.config.format.width, vertical.config.format.height, vertical.config.format.fps) == (1080, 1920, 24)
    assert vertical.config.theme.font == "Roboto"


def test_invalid_variant_reports_variant(make_project) -> None:
    root = make_project(minimal_config(variants={"v": {"format": {"fps": 0}}}))
    with pytest.raises(VidgenError, match=r"video.yaml \(variant 'v'\): invalid config\n  format.fps"):
        Project.load(root, variant="v")


def test_unknown_variant(make_project) -> None:
    root = make_project(minimal_config(variants={"vertical": {}, "square": {}}))
    with pytest.raises(VidgenError, match="unknown variant 'wide'; available variants: square, vertical"):
        Project.load(root, variant="wide")


def test_output_name_defaults_to_folder(make_project) -> None:
    assert Project.load(make_project(folder="my_video")).output_name == "my_video"
    assert Project.load(make_project(minimal_config(output="final"), folder="x")).output_name == "final"


def test_output_paths(make_project) -> None:
    root = make_project(minimal_config(output="clip", variants={"vertical": {}}))
    p = Project.load(root)
    v = Project.load(root, variant="vertical")
    r = root.resolve()
    assert p.output_path() == r / "clip.mp4"
    assert p.output_path(preview=True) == r / "clip_preview.mp4"
    assert v.output_path() == r / "clip_vertical.mp4"
    assert v.output_path(preview=True) == r / "clip_vertical_preview.mp4"
    assert p.srt_path() == r / "clip.srt"
    assert v.srt_path(preview=True) == r / "clip_vertical_preview.srt"


def test_dirs(make_project) -> None:
    root = make_project(minimal_config(extensions=["extensions", "more/ext"], variants={"v": {}}))
    p = Project.load(root)
    r = root.resolve()
    assert p.audio_dir == r / "audio"
    assert p.build_dir == r / "build"
    assert p.extension_dirs == [r / "extensions", r / "more" / "ext"]
    assert p.render_dir(preview=False) == r / "build" / "final"
    assert Project.load(root, variant="v").render_dir(preview=True) == r / "build" / "preview_v"
    assert p.render_format(preview=True).width == 854


def test_asset(make_project) -> None:
    root = make_project()
    (root / "assets").mkdir()
    (root / "assets" / "logo.png").write_bytes(b"x")
    p = Project.load(root)
    assert p.asset("assets/logo.png") == root.resolve() / "assets" / "logo.png"
    with pytest.raises(VidgenError, match="asset not found: assets/missing.png"):
        p.asset("assets/missing.png")


def test_scene_and_beat_lookup(make_project) -> None:
    p = Project.load(make_project())
    assert [(s.id, b.id) for s, b in p.beats()] == [("intro", "intro_b1"), ("intro", "intro_b2"), ("main", "custom")]
    assert p.beat("custom").text == "One two three four."
    assert p.scene("main").type == "bullets"
    with pytest.raises(VidgenError, match="unknown beat 'nope'"):
        p.beat("nope")
    with pytest.raises(VidgenError, match="unknown scene 'nope'; scenes: intro, main"):
        p.scene("nope")


def test_estimated_duration(make_project) -> None:
    data = minimal_config(narration={"pad": 0.5, "words_per_second": 2.0})
    data["scenes"].append({"id": "pause", "type": "title", "duration": 3})
    # words: 2 + 2 + 4 = 8 -> 4 s, pads 3 * 0.5, silent scene 3 s
    assert Project.load(make_project(data)).estimated_duration() == pytest.approx(8.5)
