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
    o = r / "output"
    assert p.output_dir == o and not o.exists()  # created by the writers, not on access
    assert p.output_path() == o / "clip.mp4"
    assert p.output_path(preview=True) == o / "clip_preview.mp4"
    assert v.output_path() == o / "clip_vertical.mp4"
    assert v.output_path(preview=True) == o / "clip_vertical_preview.mp4"
    assert p.srt_path() == o / "clip.srt"
    assert v.srt_path(preview=True) == o / "clip_vertical_preview.srt"
    assert p.chapters_path() == o / "clip_chapters.txt"
    assert v.thumbnail_path(True, ".jpg") == o / "clip_vertical_preview_thumbnail.jpg"


def test_output_dir_from_config_is_relative_to_the_project(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    absolute = (tmp_path / "abs out").resolve()
    variants = {"elsewhere": {"output_dir": str(absolute)}, "plain": {}}
    root = make_project(minimal_config(output="clip", output_dir="../renders", variants=variants))
    (tmp_path / "cwd").mkdir()
    monkeypatch.chdir(tmp_path / "cwd")  # a relative output_dir: does not follow the current directory
    p = Project.load(root)
    assert p.output_path().resolve() == (tmp_path / "renders" / "clip.mp4").resolve()
    assert Project.load(root, variant="plain").srt_path().resolve() == (tmp_path / "renders" / "clip_plain.srt").resolve()
    assert Project.load(root, variant="elsewhere").output_path() == absolute / "clip_elsewhere.mp4"
    # build/ and exports/ stay in the project folder
    assert p.build_dir == root.resolve() / "build" and p.exports_dir == root.resolve() / "exports"


def test_output_dir_flag_wins(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_project(minimal_config(output="clip", output_dir="cfg"))
    monkeypatch.chdir(tmp_path)
    p = Project.load(root, output_dir="flag")  # relative to the current directory
    assert p.output_dir == (tmp_path / "flag").resolve()
    assert p.thumbnail_path() == (tmp_path / "flag" / "clip_thumbnail.png").resolve()
    assert p.without_overlays().output_dir == p.output_dir
    assert p.build_dir == root.resolve() / "build" and p.exports_dir == root.resolve() / "exports"


def test_cli_output_dir_flag(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from vidgen.cli import build_parser, main

    parser = build_parser()
    for argv in (["render"], ["thumbnail"], ["slides"], ["export", "gif"]):
        assert parser.parse_args([*argv, "p", "--output-dir", "d"]).output_dir == "d"
        assert parser.parse_args([*argv, "p"]).output_dir is None
    root = make_project(minimal_config(output="out", output_dir="cfg"))
    monkeypatch.chdir(tmp_path)
    assert main(["thumbnail", str(root), "--output-dir", "mine", "--json"]) == 0  # a designed card: no render
    doc = json.loads(capsys.readouterr().out)
    assert Path(doc["path"]) == (tmp_path / "mine" / "out_thumbnail.png").resolve() and Path(doc["path"]).is_file()
    assert not (root / "cfg").exists() and not (root / "output").exists()
    assert sorted(f.name for f in root.iterdir()) == ["build", "video.yaml"]  # nothing in the project root


def test_output_dir_is_confined_under_mcp(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.project import CONFINE_ENV

    root = make_project(minimal_config(output_dir="../outside"))
    monkeypatch.setenv(CONFINE_ENV, str(root))
    with pytest.raises(VidgenError, match="output_dir: '../outside' is outside the allowed folder"):
        Project.load(root)


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
    assert p.scene("main").type == "text_card"
    with pytest.raises(VidgenError, match="unknown beat 'nope'"):
        p.beat("nope")
    with pytest.raises(VidgenError, match="unknown scene 'nope'; scenes: intro, main"):
        p.scene("nope")


def test_estimated_duration(make_project) -> None:
    data = minimal_config(narration={"pad": 0.5, "words_per_second": 2.0})
    data["scenes"].append({"id": "pause", "type": "title", "duration": 3})
    # words: 2 + 2 + 4 = 8 -> 4 s, pads 3 * 0.5, silent scene 3 s
    assert Project.load(make_project(data)).estimated_duration() == pytest.approx(8.5)
