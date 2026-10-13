"""Review of Phase I (Step 102): the screenplay sample and the series example end to end through the
CLI without rendering (`screenplay`, `validate`, `direct`); the seats every character can sit on
with its feet on the ground; `vidgen mcp`'s folder rule for SVG looks and props, sets, layers,
Kokoro `.pt` voices and a cast's own includes; a shared cast's unused voices; and one tiny render
of a stage that uses the Phase I features together (captions over an automatically directed
scene, a voice sound, an overlap, an interrupt, sitting, a prop picked up and given, a light
fade, wind)."""

from __future__ import annotations

import json
import shutil
import typing
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen.cartoon.character import build_character
from vidgen.cartoon.props import PROP_HEIGHTS
from vidgen.cartoon.seating import PROP_SEATS, SEATED_LEGS_DEGREES
from vidgen.cli import main
from vidgen.config import CharacterEntry, CharacterLook
from vidgen.errors import VidgenError
from vidgen.includes import read_include_file
from vidgen.project import CONFINE_ENV, Project, confinement_problems
from vidgen.theme import Theme

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "examples" / "screenplay" / "humming_box.md"
SERIES = REPO / "examples" / "cartoon_series"
SVG_EXAMPLE = REPO / "examples" / "svg_character"
GROUND = 1e-6


def json_out(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


def write(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


# ----- the examples end to end (no render) ----------------------------------------------------------------


def test_screenplay_sample_to_a_directed_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "humming_box"
    assert main(["screenplay", str(SAMPLE), "--out", str(out), "--json"]) == 0
    doc = json_out(capsys)
    assert doc["scene_count"] == 2 and doc["beat_count"] == 11 and doc["todo_count"] == 0
    assert main(["validate", str(out), "--json"]) == 0
    assert json_out(capsys)["ok"]
    assert main(["direct", str(out), "--json"]) == 0
    added = {b["beat"]: b["actions"] for s in json_out(capsys)["scenes"] for b in s["beats"]}
    assert {"look_at", "react", "gesture"} <= {next(iter(a)) for actions in added.values() for a in actions}


@pytest.mark.parametrize("episode", ["episode_1", "episode_2"])
def test_series_episodes_validate_with_their_includes(tmp_path: Path, episode: str, capsys: pytest.CaptureFixture[str]) -> None:
    shutil.copytree(SERIES, tmp_path / "series")
    assert main(["validate", str(tmp_path / "series" / episode), "--json"]) == 0
    doc = json_out(capsys)
    assert doc["ok"] and [Path(p).name for p in doc["included"]] == ["cast.yaml", "sets.yaml"]
    assert main(["direct", str(tmp_path / "series" / episode), "--json"]) == 0
    assert any(b["actions"] for s in json_out(capsys)["scenes"] for b in s["beats"])


def test_unused_voices_of_a_shared_cast_are_not_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shutil.copytree(SERIES / "shared", tmp_path / "shared")
    out = tmp_path / "episode_3"   # the sample's own characters; nib and olla do not speak in it
    assert main(["screenplay", str(SAMPLE), "--out", str(out), "--cast", str(tmp_path / "shared" / "cast.yaml"), "--json"]) == 0
    capsys.readouterr()
    assert main(["validate", str(out), "--json"]) == 0
    warnings = [w["message"] for w in json_out(capsys)["warnings"]]
    assert not [w for w in warnings if "is not used by any scene" in w]
    data = yaml.safe_load((out / "video.yaml").read_text(encoding="utf-8"))
    data["voices"]["spare_voice"] = {"voice": "af_heart"}   # one of the project's own still is
    write(out / "video.yaml", data)
    assert main(["validate", str(out), "--json"]) == 0
    warnings = [w["message"] for w in json_out(capsys)["warnings"]]
    assert [w for w in warnings if "is not used by any scene" in w] == ["voices: 'spare_voice' is not used by any scene or beat"]


# ----- seats: hips on the seat line, feet on the ground ---------------------------------------------------


def generated_looks() -> list[dict[str, Any]]:
    bodies = typing.get_args(CharacterLook.model_fields["body"].annotation)
    return [{"body": body, "head_size": size} for body in bodies for size in (0.6, 1.0, 1.6)]


def svg_characters() -> list[Any]:
    data = yaml.safe_load((SVG_EXAMPLE / "video.yaml").read_text(encoding="utf-8"))
    return [build_character(CharacterEntry(**entry), theme=Theme(), root=SVG_EXAMPLE) for entry in data["characters"]]


def test_every_built_in_seat_is_below_every_generated_characters_hips() -> None:
    lowest = min(build_character(CharacterEntry(name="x", look=look), theme=Theme()).hip_height() for look in generated_looks())
    lowest = min(lowest, *(c.hip_height() for c in svg_characters()))
    for prop, (_, seat_y) in PROP_SEATS.items():
        assert PROP_HEIGHTS[prop] * seat_y < lowest, prop


@pytest.mark.parametrize("prop", sorted(PROP_SEATS))
def test_seated_hips_on_the_seat_and_feet_on_the_ground(prop: str) -> None:
    seat = PROP_HEIGHTS[prop] * PROP_SEATS[prop][1]
    figures = [build_character(CharacterEntry(name="x", look=look), theme=Theme()) for look in generated_looks()]
    for c in [*figures, *svg_characters()]:
        rest = c.state()
        seated = c.seated(rest, seat)
        world = c._world({**c._poses, **seated.parts})
        assert c._hips_y(world, seated.parts) == pytest.approx(seat)
        soles = c.sole_points(seated)
        if soles:   # single legs: both soles on the ground, in front of where they stood
            assert all(y == pytest.approx(0.0, abs=GROUND) for _, y in soles.values())
            assert all(soles[foot][0] > c.sole_points()[foot][0] for foot in soles)
        else:       # one-piece legs: turned forward until they reach the ground
            assert 0 < seated.parts["legs"].angle < SEATED_LEGS_DEGREES


# ----- vidgen mcp: every file a project names stays inside the root ---------------------------------------


def test_confinement_covers_svgs_sets_layers_and_kokoro_voice_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "videos" / "p"
    root.mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "videos")   # vidgen mcp runs its commands in the root (Kokoro reads a .pt from there)
    data = {
        "voice": {"provider": "kokoro", "voice": "af_bella,../../mine.pt"},
        "voices": {"a": {"voice": "af_heart"}, "b": {"voice": "/elsewhere/own.pt"}, "c": {"voice": "assets/own.pt"}},
        "characters": [{"name": "pip", "look": {"svg": "../../pip.svg"}}, {"name": "kit", "look": {"svg": "assets/kit.svg"}}],
        "sets": {"yard": {"image": "../../sky.png", "props": [{"svg": "/tmp/../etc/x.svg"}]}},
        "scenes": [{"id": "s", "type": "stage", "params": {"layers": [{"image": "../../hills.png"}], "props": [{"svg": "assets/ok.svg"}]}}],
    }
    problems = confinement_problems(data, root, tmp_path / "videos")
    where = sorted(p.split(":")[0] for p in problems)
    assert where == [
        "characters[0].look.svg", "scenes[0].params.layers[0].image", "sets.yard.image", "sets.yard.props[0].svg",
        "voice.voice", "voices.b.voice",
    ]


def test_an_included_casts_svg_outside_the_root_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path / "videos" / "shared" / "cast.yaml", {"characters": [{"name": "pip", "look": {"svg": "../../outside.svg"}}]})
    episode = write(tmp_path / "videos" / "ep" / "video.yaml", {
        "title": "T", "include": ["../shared/cast.yaml"],
        "scenes": [{"id": "s", "type": "stage", "params": {"characters": ["pip"]}, "beats": [{"text": "Hi."}]}],
    }).parent
    Project.load(episode)   # not confined: loads (validate reports the missing file)
    monkeypatch.setenv(CONFINE_ENV, str(tmp_path / "videos"))
    with pytest.raises(VidgenError, match=r"characters\[0\]\.look\.svg: '\.\./\.\./outside\.svg' is outside the allowed folder"):
        Project.load(episode)


def test_a_casts_own_includes_are_confined(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path / "secret.yaml", {"voices": {"x": {"voice": "af_heart"}}})
    cast = write(tmp_path / "videos" / "cast.yaml", {"include": ["../secret.yaml"]})
    assert read_include_file(cast)["voices"] == {"x": {"voice": "af_heart"}}
    monkeypatch.setenv(CONFINE_ENV, str(tmp_path / "videos"))
    with pytest.raises(VidgenError, match="outside the allowed folder"):
        read_include_file(cast)


def test_mcp_validate_refuses_an_svg_look_outside_the_root(tmp_path: Path) -> None:
    from test_mcp import error_text, run_session

    root = tmp_path / "root"
    write(root / "toon" / "video.yaml", {
        "title": "T", "characters": [{"name": "pip", "look": {"svg": "../../outside.svg"}}],
        "scenes": [{"id": "s", "type": "stage", "params": {"characters": ["pip"]}, "beats": [{"text": "Hi."}]}],
    })

    async def body(client: Any) -> None:
        assert "outside the allowed folder" in error_text(await client.call_tool("validate", {"project": "toon"}))

    run_session(root, body)


# ----- the Phase I features together, rendered small ---------------------------------------------------------


def showcase_config() -> dict[str, Any]:
    """A stage with captions over automatically directed beats, a laugh, an overlap, an interrupt,
    sitting, a prop picked up and given, wind and a fade to night (160x90, 5 fps, no audio)."""
    tiny = {"width": 160, "height": 90, "fps": 5}
    return {
        "title": "Phase I", "format": tiny, "preview": tiny, "auto_direct": True,
        "narration": {"pad": 0.3, "words_per_second": 3.0},
        "overlays": [{"type": "captions", "speakers": "color"}],
        "voices": {"a_voice": {"label": "A", "color": "primary"}, "b_voice": {"label": "B", "color": "accent"}},
        "characters": [{"name": "ann", "voice": "a_voice"}, {"name": "bo", "voice": "b_voice", "look": {"body": "tall"}}],
        "scenes": [{
            "id": "yard", "type": "stage",
            "params": {
                "light": "sunset", "wind": "breeze",
                "props": [{"prop": "rock", "at": 0.3}, {"prop": "box", "name": "crate", "at": 0.5}, {"prop": "tree", "at": 0.85}],
                "characters": [{"name": "ann", "at": 0.35}, {"name": "bo", "at": 0.45}],
            },
            "beats": [
                {"text": "[laugh] There it is, the crate.", "voice": "a_voice", "actions": [{"sit_on": "ann", "to": "rock"}]},
                {"text": "It hums all day long, you know.", "voice": "b_voice", "overlap": 0.3, "actions": [{"pick_up": "bo", "to": "crate"}]},
                {"text": "Then give it here.", "voice": "a_voice", "interrupt": True, "shot": "two_shot ann bo"},
                {"text": "Here, take it.", "voice": "b_voice", "actions": [{"give": "bo", "to": "ann"}]},
                {"text": "And night came.", "actions": [{"light": "night", "run_time": 1}, {"wind": "windy"}]},
            ],
        }],
    }


@pytest.mark.render
@pytest.mark.slow
def test_phase_i_features_render_together(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write(tmp_path / "toon" / "video.yaml", showcase_config()).parent
    assert main(["validate", str(root), "--json"]) == 0
    assert json_out(capsys)["ok"]
    assert main(["render", str(root), "--preview", "--json"]) == 0   # captions with automatic actions (Step 102 fix)
    doc = json_out(capsys)
    assert Path(doc["outputs"]["video"]).is_file()
    timings = json.loads((root / "build" / "preview" / "timings" / "yard.json").read_text(encoding="utf-8"))
    beats = {b["id"]: b for b in timings["beats"]}
    assert beats["yard_b2"]["start"] < beats["yard_b1"]["end"]          # the overlap
    assert beats["yard_b2"]["end"] == pytest.approx(beats["yard_b3"]["start"])   # cut by the interrupt
    srt = Path(doc["outputs"]["subtitles"]).read_text(encoding="utf-8")
    assert "There it is, the crate." in srt and "[laugh]" not in srt
