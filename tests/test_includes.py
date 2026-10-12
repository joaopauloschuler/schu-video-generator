"""Step 101: shared casts and sets (``include:`` files, named ``sets:``). The merge rules are pure
functions tested on mappings; loading, error locations, fingerprints and the audio / picture
caches are tested on small projects in ``tmp_path`` without rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen import cli
from vidgen.errors import Problem, VidgenError
from vidgen.includes import (
    Origin,
    after_variant,
    apply_set,
    attributed,
    expand_sets,
    merge_config,
    read_include_file,
    read_project_config,
)
from vidgen.project import Project, deep_merge
from vidgen.screenplay import parse_screenplay, screenplay_project

SERIES = Path(__file__).resolve().parents[1] / "examples" / "cartoon_series"

CAST = {
    "voices": {"nib_voice": {"voice": "af_sarah", "speed": 0.85, "label": "Nib"}},
    "characters": [
        {"name": "nib", "voice": "nib_voice", "look": {"body": "round", "hair": "curly"}},
        {"name": "olla", "look": {"body": "bean", "ears": "floppy"}},
    ],
}
SETS = {
    "sets": {
        "meadow": {
            "background": ["#9CCBEA", "#E4F3FB"],
            "ground_color": "tertiary",
            "light": "morning",
            "marks": {"shore": 0.62},
            "props": [{"prop": "rock", "at": "shore"}, "tree", {"prop": "tree", "at": 0.9}],
            "characters": [{"name": "olla", "at": "shore"}],
        }
    }
}


def _write(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _episode(tmp_path: Path, scenes: list[dict[str, Any]] | None = None, **top: Any) -> Path:
    """``tmp_path/shared/{cast,sets}.yaml`` and an episode ``tmp_path/ep/video.yaml`` including them."""
    _write(tmp_path / "shared" / "cast.yaml", CAST)
    _write(tmp_path / "shared" / "sets.yaml", SETS)
    config = {
        "title": "Ep",
        "include": ["../shared/cast.yaml", "../shared/sets.yaml"],
        "voice": {"provider": "kokoro", "voice": "bf_emma"},
        **top,
        "scenes": scenes or [{"id": "a", "type": "stage", "set": "meadow", "params": {"characters": ["nib"]}, "beats": [{"text": "Hi.", "voice": "nib_voice"}]}],
    }
    return _write(tmp_path / "ep" / "video.yaml", config)


# ----- merge rules (pure) ------------------------------------------------------------------------------


def test_merge_config_mappings_merge_characters_by_name_lists_replace() -> None:
    base = {"voices": {"a": {"voice": "x", "speed": 1.0}}, "characters": [{"name": "nib", "look": {"body": "round", "hair": "curly"}}, {"name": "olla"}], "sets": {"s": {"props": ["tree"]}}}
    own = {"voices": {"a": {"speed": 0.8}, "b": {"voice": "y"}}, "characters": [{"name": "nib", "look": {"hair": "bun"}}, {"name": "pip"}], "sets": {"s": {"props": ["rock"]}}}
    merged = merge_config(base, own)
    assert merged["voices"] == {"a": {"voice": "x", "speed": 0.8}, "b": {"voice": "y"}}
    assert merged["characters"] == [{"name": "nib", "look": {"body": "round", "hair": "bun"}}, {"name": "olla"}, {"name": "pip"}]
    assert merged["sets"] == {"s": {"props": ["rock"]}}                          # a list inside a set replaces
    assert base["characters"][0]["look"]["hair"] == "curly"                       # inputs untouched


def test_merge_config_records_where_values_are_written() -> None:
    origins: dict[str, Origin] = {}
    merged = merge_config({}, CAST, origins, "cast.yaml")
    merged = merge_config(merged, {"characters": [{"name": "pip"}, {"name": "olla", "voice": "v"}], "voices": {"nib_voice": {"speed": 1.0}}}, origins, None)
    def where(location: str) -> tuple[str | None, str]:
        found = attributed([Problem(location, "m")], origins)[0]
        return found.file, found.location
    assert where("characters[0].look.body") == ("cast.yaml", "characters[0].look.body")
    assert where("characters[1].look.ears") == ("cast.yaml", "characters[1].look.ears")
    assert where("characters[1].voice") == (None, "characters[1].voice")      # written by the project (its 2nd entry)
    assert where("characters[2]") == (None, "characters[0]")                    # pip: the project's first entry
    assert where("voices.nib_voice.speed") == (None, "voices.nib_voice.speed")
    assert where("voices.nib_voice.voice") == ("cast.yaml", "voices.nib_voice.voice")
    assert where("scenes[0].params") == (None, "scenes[0].params")
    # a variant that replaces the characters list owns all of it
    after = after_variant(origins, merged, {"characters": [{"name": "nib"}]})
    assert attributed([Problem("characters[0].look", "m")], after)[0].file is None
    assert attributed([Problem("voices.nib_voice.voice", "m")], after)[0].file == "cast.yaml"


def test_apply_set_rules() -> None:
    meadow = SETS["sets"]["meadow"]
    merged = apply_set(meadow, {
        "light": "sunset",
        "marks": {"gate": 0.9},
        "props": [{"name": "tree_2", "at": 0.8}, "ball"],                     # moves the set's 2nd tree, adds a ball
        "characters": ["nib", {"name": "olla", "pose": "thinking"}],
    })
    params = merged.params
    assert params["light"] == "sunset" and params["background"] == meadow["background"]
    assert params["marks"] == {"shore": 0.62, "gate": 0.9}
    assert params["props"] == [{"prop": "rock", "at": "shore"}, "tree", {"prop": "tree", "at": 0.8, "name": "tree_2"}, "ball"]
    assert params["characters"] == [{"name": "olla", "at": "shore", "pose": "thinking"}, "nib"]
    assert merged.from_set["props[0]"] == "props[0]" and merged.from_set["marks.shore"] == "marks.shore"
    assert merged.from_stage == {"props[2].name": "props[0].name", "props[2].at": "props[0].at", "props[3]": "props[1]",
                                 "characters[0].name": "characters[1].name", "characters[0].pose": "characters[1].pose", "characters[1]": "characters[0]"}
    # unnamed stage props are added (the stage numbers them), never matched by default name
    assert apply_set(meadow, {"props": ["tree"]}).params["props"][-1] == "tree"
    # an empty list clears the set's; a picture replaces the set's whole backdrop
    cleared = apply_set(meadow, {"props": [], "image": "assets/park.png"}).params
    assert cleared["props"] == [] and "background" not in cleared and cleared["image"] == "assets/park.png"
    assert "ground_color" in cleared
    # particles combine (no names)
    assert apply_set({"particles": ["dust"]}, {"particles": ["rain"]}).params["particles"] == ["dust", "rain"]


def test_expand_sets_points_set_values_at_the_set() -> None:
    data = {**SETS, "scenes": [{"id": "a", "type": "stage", "set": "meadow", "params": {"props": ["ball"]}}, {"id": "b", "type": "stage", "set": "nope"}]}
    expanded, origins = expand_sets(data, {"sets": Origin("sets.yaml", "sets")})
    assert expanded["scenes"][1] == data["scenes"][1]                            # unknown set: left for the config check
    problems = attributed([Problem("scenes[0].params.props[1].prop", "bad"), Problem("scenes[0].params.props[3]", "bad"), Problem("scenes[0].params.light", "bad")], origins)
    assert [(p.file, p.location) for p in problems] == [
        ("sets.yaml", "sets.meadow.props[1].prop"), (None, "scenes[0].params.props[0]"), ("sets.yaml", "sets.meadow.light"),
    ]


# ----- reading the files -------------------------------------------------------------------------------


def test_includes_merge_in_order_relative_to_their_file(tmp_path: Path) -> None:
    _write(tmp_path / "shared" / "base.yaml", {"voices": {"v": {"voice": "a", "speed": 1.0}}, "characters": [{"name": "nib", "look": {"svg": "art/nib.svg"}}]})
    _write(tmp_path / "shared" / "cast.yaml", {"include": "base.yaml", "voices": {"v": {"speed": 0.9}}})
    _write(tmp_path / "shared" / "more.yaml", {"include": ["base.yaml"], "voices": {"v": {"label": "V"}}})     # base twice: merged once
    config = _write(tmp_path / "ep" / "video.yaml", {"title": "t", "include": ["../shared/cast.yaml", "../shared/more.yaml"], "voices": {"v": {"speed": 0.8}}, "scenes": []})
    source = read_project_config(config)
    assert [p.name for p in source.files] == ["base.yaml", "cast.yaml", "more.yaml"]
    assert source.data["voices"] == {"v": {"voice": "a", "speed": 0.8, "label": "V"}}
    assert source.data["characters"][0]["look"]["svg"] == "../shared/art/nib.svg"   # relative to the project now
    assert source.named_files == ((tmp_path / "shared" / "base.yaml").resolve().parent / "art" / "nib.svg",)
    assert source.data["include"] == ["../shared/cast.yaml", "../shared/more.yaml"]


@pytest.mark.parametrize(
    ("files", "message", "location", "file"),
    [
        ({"video.yaml": {"include": ["cast.yaml"]}}, "video.yaml: include 'cast.yaml' not found", "include[0]", None),
        ({"video.yaml": {"include": "a.yaml"}, "a.yaml": {"include": "sub/b.yaml"}, "sub/b.yaml": {"include": "../a.yaml"}},
         "video.yaml -> a.yaml -> sub/b.yaml: include '../a.yaml' makes a cycle: a.yaml -> sub/b.yaml -> a.yaml", "include", "sub/b.yaml"),
        ({"video.yaml": {"include": ["a.yaml"]}, "a.yaml": {"include": ["gone.yaml"]}}, "video.yaml -> a.yaml: include 'gone.yaml' not found", "include[0]", "a.yaml"),
        ({"video.yaml": {"include": ["a.yaml"]}, "a.yaml": {"theme": {"preset": "x"}}}, "a.yaml: an included file holds include, characters, voices, sets; not theme", "theme", "a.yaml"),
        ({"video.yaml": {"include": [3]}}, "include: give a file name or a list", "include", None),
        ({"video.yaml": {"include": ["notes.txt"]}}, "include 'notes.txt' is not a .yaml, .yml or .json file", "include[0]", None),
    ],
)
def test_include_errors_name_the_chain(tmp_path: Path, files: dict[str, Any], message: str, location: str, file: str | None) -> None:
    for name, data in files.items():
        _write(tmp_path / name, {"title": "t", "scenes": [], **data} if name == "video.yaml" else data)
    with pytest.raises(VidgenError) as caught:
        Project.load(tmp_path)
    assert message in str(caught.value)
    assert [(p.location, p.file) for p in caught.value.problems] == [(location, file)]


def test_variant_must_not_include(tmp_path: Path) -> None:
    config = _episode(tmp_path, variants={"v": {"include": ["x.yaml"]}})
    with pytest.raises(VidgenError, match="variant 'v' must not contain 'include'"):
        Project.load(config)


def test_project_loads_merged_cast_and_set(tmp_path: Path) -> None:
    config = _episode(tmp_path, characters=[{"name": "olla", "colors": {"clothes": "accent"}}])
    project = Project.load(config)
    olla = project.config.characters[1]
    assert (olla.name, olla.look.ears, olla.colors.clothes) == ("olla", "floppy", "accent")
    params = project.config.scenes[0].params
    assert params["light"] == "morning" and [c if isinstance(c, str) else c["name"] for c in params["characters"]] == ["olla", "nib"]
    assert project.config.scenes[0].set == "meadow"
    assert project.included_labels == ["../shared/cast.yaml", "../shared/sets.yaml"]


def test_config_errors_say_which_file(tmp_path: Path) -> None:
    _episode(tmp_path)
    cast = json.loads(json.dumps(CAST))
    cast["characters"][0]["voice"] = "nibb_voice"
    _write(tmp_path / "shared" / "cast.yaml", cast)
    with pytest.raises(VidgenError) as caught:
        Project.load(tmp_path / "ep")
    assert "characters[0].voice (in ../shared/cast.yaml): unknown voice 'nibb_voice'; did you mean 'nib_voice'?" in str(caught.value)
    assert caught.value.problems[0].to_json() == {
        "location": "characters[0].voice", "message": caught.value.problems[0].message, "variant": None, "file": "../shared/cast.yaml",
    }


def test_unknown_set_is_a_config_error(tmp_path: Path) -> None:
    config = _episode(tmp_path, scenes=[{"id": "a", "type": "stage", "set": "medow", "params": {}, "beats": [{"text": "Hi."}]}])
    with pytest.raises(VidgenError, match=r"scenes\[0\]\.set: unknown set 'medow'; did you mean 'meadow'\? sets: meadow"):
        Project.load(config)


def test_validate_problems_point_into_the_sets_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sets = json.loads(json.dumps(SETS))
    sets["sets"]["meadow"]["props"][0]["prop"] = "rok"
    _episode(tmp_path, scenes=[
        {"id": "a", "type": "stage", "set": "meadow", "params": {"props": [{"name": "kite", "at": 0.5}]}, "beats": [{"text": "Hi."}]},
        {"id": "b", "type": "stage", "set": "meadow", "params": {}, "beats": [{"text": "Hi."}]},
    ])
    _write(tmp_path / "shared" / "sets.yaml", sets)
    assert cli.main(["validate", "--json", str(tmp_path / "ep")]) == 1
    doc = json.loads(capsys.readouterr().out)
    found = [(p["location"], p["file"]) for p in doc["problems"]]
    assert found == [("sets.meadow.props[0].prop", "../shared/sets.yaml"), ("scenes[0].params.props[0]", None)]   # once, not per scene
    assert [Path(p).name for p in doc["included"]] == ["cast.yaml", "sets.yaml"]


def test_series_example_episodes_validate(capsys: pytest.CaptureFixture[str]) -> None:
    for episode in ("episode_1", "episode_2"):
        assert cli.main(["validate", str(SERIES / episode)]) == 0
        assert "included:  ../shared/cast.yaml, ../shared/sets.yaml" in capsys.readouterr().out
    olla = Project.load(SERIES / "episode_2").config.characters[1]
    assert olla.look.accessories == ["hat", "scarf"] and olla.look.ears == "floppy"


# ----- caches notice the included files ----------------------------------------------------------------


def test_fingerprint_follows_included_files(tmp_path: Path) -> None:
    from vidgen.render.fingerprint import scene_fingerprint

    config = _episode(tmp_path)
    first = scene_fingerprint(Project.load(config), "a")
    sets = json.loads(json.dumps(SETS))
    sets["sets"]["unused"] = {"light": "night"}
    _write(tmp_path / "shared" / "sets.yaml", sets)
    assert scene_fingerprint(Project.load(config), "a") == first                 # a set no scene uses
    sets["sets"]["meadow"]["light"] = "sunset"
    _write(tmp_path / "shared" / "sets.yaml", sets)
    second = scene_fingerprint(Project.load(config), "a")
    assert second != first
    cast = json.loads(json.dumps(CAST))
    cast["characters"][0]["colors"] = {"clothes": "accent"}
    _write(tmp_path / "shared" / "cast.yaml", cast)
    assert scene_fingerprint(Project.load(config), "a") != second


def test_fingerprint_follows_files_named_by_includes(tmp_path: Path) -> None:
    from vidgen.render.fingerprint import scene_fingerprint

    config = _episode(tmp_path)
    cast = json.loads(json.dumps(CAST))
    cast["characters"][1]["look"] = {"svg": "art/olla.svg"}
    _write(tmp_path / "shared" / "cast.yaml", cast)
    svg = tmp_path / "shared" / "art" / "olla.svg"
    svg.parent.mkdir()
    svg.write_text("<svg/>", encoding="utf-8")
    first = scene_fingerprint(Project.load(config), "a")
    svg.write_text("<svg></svg>", encoding="utf-8")
    assert scene_fingerprint(Project.load(config), "a") != first


def test_audio_goes_stale_when_the_cast_voice_changes(tmp_path: Path) -> None:
    from vidgen.tts import audio_status, get_provider

    config = _episode(tmp_path)
    project = Project.load(config)
    beat = project.beat("a_b1")
    audio = project.audio_dir
    audio.mkdir()
    (audio / "a_b1.mp3").write_bytes(b"ID3")
    (audio / "a_b1.hash").write_text(get_provider(project.beat_voice("a_b1")).cache_key(project.spoken(beat).spoken), encoding="utf-8")
    assert [s.state for s in audio_status(project)] == ["ok"]
    cast = json.loads(json.dumps(CAST))
    cast["voices"]["nib_voice"]["speed"] = 1.0
    _write(tmp_path / "shared" / "cast.yaml", cast)
    assert [s.state for s in audio_status(Project.load(config))] == ["stale"]


def test_generated_picture_of_a_set_follows_the_sets_file(tmp_path: Path) -> None:
    from vidgen.imagegen import scene_images

    sets = {"sets": {"meadow": {"generate": "a quiet meadow"}}}
    config = _episode(tmp_path)
    _write(tmp_path / "shared" / "sets.yaml", sets)
    first = [image.request.key for image in scene_images(Project.load(config))]
    sets["sets"]["meadow"]["generate"] = "a quiet meadow at dawn"
    _write(tmp_path / "shared" / "sets.yaml", sets)
    second = [image.request.key for image in scene_images(Project.load(config))]
    assert len(first) == len(second) == 1 and first != second


# ----- vidgen screenplay --cast ------------------------------------------------------------------------


PLAY = """# The Pond Test

# Scene: shore
set: meadow; props: ball at 0.4

NIB: Look at the rock!

[Nib walks to the rock]

PIP: It is a rock.
"""


def test_screenplay_reuses_a_cast(tmp_path: Path) -> None:
    _write(tmp_path / "shared" / "sets.yaml", SETS)
    _write(tmp_path / "shared" / "cast.yaml", {"include": ["sets.yaml"], **CAST})
    cast = read_include_file(tmp_path / "shared" / "cast.yaml")
    draft = screenplay_project(parse_screenplay(PLAY), cast=cast, include="../shared/cast.yaml")
    config = draft.config
    assert config["include"] == ["../shared/cast.yaml"]
    assert [c["name"] for c in config["characters"]] == ["pip"] and draft.generated == ["pip"]   # nib comes from the cast
    scene = config["scenes"][0]
    assert scene["set"] == "meadow" and scene["params"]["props"] == [{"prop": "ball", "at": 0.4}]
    assert "background" not in scene["params"]                                  # the set's sky, not the default one
    assert {"name": "olla", "at": "shore"} not in scene["params"]["characters"]   # only who is in the scene
    first, second = scene["beats"]
    assert first["voice"] == "nib_voice"
    assert second["actions"][0]["walk_to"] == "nib" and second["actions"][0]["to"] < 0.62   # beside the set's rock


def test_screenplay_cli_with_cast_validates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path / "shared" / "sets.yaml", SETS)
    _write(tmp_path / "shared" / "cast.yaml", {"include": ["sets.yaml"], **CAST})
    play = tmp_path / "pond.md"
    play.write_text(PLAY, encoding="utf-8")
    out = tmp_path / "episodes" / "pond"
    assert cli.main(["screenplay", str(play), "--cast", str(tmp_path / "shared" / "cast.yaml"), "--out", str(out), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["problems"] == [] and {c["name"] for c in doc["characters"]} == {"nib", "olla", "pip"}
    assert yaml.safe_load((out / "video.yaml").read_text(encoding="utf-8"))["include"] == ["../../shared/cast.yaml"]
    assert cli.main(["screenplay", str(play), "--cast", str(tmp_path / "nope.yaml"), "--out", str(tmp_path / "x")]) == 1
    with pytest.raises(VidgenError, match="--cast: cast.yaml: an included file holds"):
        _write(tmp_path / "bad" / "cast.yaml", {"title": "no"})
        read_include_file(tmp_path / "bad" / "cast.yaml")


def test_deep_merge_is_unchanged_for_variants() -> None:
    assert deep_merge({"characters": [{"name": "a"}]}, {"characters": [{"name": "b"}]}) == {"characters": [{"name": "b"}]}
