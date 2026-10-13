"""Review of Phase L (Step 130): the example `examples/cartoon-rainbow-ride` end to end through the
CLI and `vidgen mcp` without rendering (`screenplay`, `cast`, `validate`, `direct`, `list-music`),
and the fixes found on the way: `vidgen screenplay` wrote an exit's edge as `side` (exit's option
is `to`), a watering can held by a character facing left poured backwards onto its holder, and a
prop held by a character waiting off stage for its `enter` showed at the edge of the view."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_acting import figure, run, target, use
from test_cartoon_moving import StageFake
from test_cartoon_stage import render_with_layout
from vidgen.cartoon.contrast import MIN_CONTRAST, character_pairs
from vidgen.cartoon.props import WATERING_SPOUT, draw_prop
from vidgen.cartoon.small_props_drawing import WaterFlow
from vidgen.cli import main
from vidgen.project import Project
from vidgen.theme import Theme

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "cartoon-rainbow-ride"
SCREENPLAY = EXAMPLE / "rainbow_ride.md"


def json_out(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


# ----- the example end to end (no render) -------------------------------------------------------------


def test_the_example_validates_directs_and_uses_phase_l(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "rainbow")
    assert main(["validate", str(root), "--json"]) == 0
    assert json_out(capsys)["ok"]
    assert main(["direct", str(root), "--json"]) == 0
    added = [a for s in json_out(capsys)["scenes"] for b in s["beats"] for a in b["actions"]]
    assert any(next(iter(a)) == "effect" for a in added)   # auto_direct's symbols too
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("species: robot", "moves_on: wheels", "party_hat", "species: fox", "species: owl",   # Steps 123-124
                 "bicycle", "get_in:", "ride_to:",                                                     # Step 118
                 "time:", "fireplace", '"on": true', "switch_on: kettle", "switch_on: lamp",           # Steps 120-121
                 "fruit: true", "drop_fruit:", "birds:",                                              # Step 121
                 "watering_can", "pour:", "gift", "open: gift", "cake",                               # Step 122
                 "dizzy", "laughing", "frightened", "blushing", "tongue_out",                          # Step 125
                 "particles: rain", "lightning:", "rainbow:",                                          # Step 127
                 "knock:", "door: door", "source: cartoon"):                                           # Steps 128-129
        assert used in text, used
    assert len(text.encode("utf-8")) <= 10_000   # examples may be up to 10 KB (Phase L)
    pairs = character_pairs(Project.load(root).config, Theme())
    assert len(pairs) == 3 and all(pair.score >= MIN_CONTRAST for _, pair in pairs)   # lint look_alike stays quiet


def test_the_screenplay_of_the_example_validates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`[Tibbo exits right.]` wrote `side: right`, which `exit` refuses (its edge option is `to`)."""
    out = tmp_path / "draft"
    assert main(["screenplay", str(SCREENPLAY), "--out", str(out), "--json"]) == 0
    doc = json_out(capsys)
    assert doc["scene_count"] == 4 and doc["beat_count"] == 16 and doc["todo_count"] == 0
    assert "{exit: tibbo, to: right" in (out / "video.yaml").read_text(encoding="utf-8")
    assert main(["validate", str(out), "--json"]) == 0
    assert json_out(capsys)["ok"]


def test_a_random_cast_of_robots_and_animals_and_the_music_beds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cast = tmp_path / "shared" / "cast.yaml"
    assert main(["cast", "--random", "3", "--species", "robot", "fox", "owl", "--seed", "4", "--out", str(cast), "--json"]) == 0
    capsys.readouterr()
    out = tmp_path / "episode"
    assert main(["screenplay", str(SCREENPLAY), "--out", str(out), "--cast", str(cast), "--json"]) == 0
    capsys.readouterr()
    assert main(["validate", str(out), "--json"]) == 0
    assert json_out(capsys)["ok"]
    assert main(["list-music", "--json"]) == 0
    beds = json.dumps(json_out(capsys))
    assert '"cartoon"' in beds and '"lullaby"' in beds


def test_mcp_screenplay_validate_and_list_music_of_the_example(tmp_path: Path) -> None:
    from test_mcp import doc_of, run_session

    root = tmp_path / "root"
    shutil.copytree(EXAMPLE, root / "rainbow")

    async def body(client: Any) -> None:
        doc = doc_of(await client.call_tool("screenplay", {"input_path": "rainbow/rainbow_ride.md", "out": "draft"}))
        assert doc["scene_count"] == 4 and doc["todo_count"] == 0
        assert doc_of(await client.call_tool("validate", {"project": "draft"}))["ok"]
        assert doc_of(await client.call_tool("validate", {"project": "rainbow"}))["ok"]
        assert "lullaby" in json.dumps(doc_of(await client.call_tool("list_music", {})))

    run_session(root, body)


# ----- fixes found on the way --------------------------------------------------------------------------


def _pour(facing: str) -> tuple[Any, Any, list[Any]]:
    kit = figure("kit").face(facing).shift([0.0, -2.0, 0.0])
    can = draw_prop("watering_can", height=0.5, theme=Theme(), name="can").shift([0.6, -2.0, 0.0])
    can.height_factor = 0.5 / kit.character_height
    scene = StageFake(kit=kit, can=can)
    scene.mobjects = [can, kit]
    run(use("hold", "kit", to="can").apply(scene, [target("kit", kit)]))
    return kit, can, use("pour", "kit").apply(scene, [target("kit", kit)])


@pytest.mark.parametrize("facing", ["left", "right"])
def test_a_watering_can_pours_the_way_its_holder_faces(facing: str) -> None:
    """The can is drawn with its spout to the right; held by a character facing left it poured
    backwards, onto its holder's feet. `pour` now turns it round in the hand first."""
    kit, can, anims = _pour(facing)
    flow = next(a for a in anims if isinstance(a, WaterFlow))
    ahead = 1.0 if facing == "right" else -1.0
    assert flow.direction() == ahead and can.facing == facing
    spout, grip = can.prop_point(*WATERING_SPOUT), can.grip_point()
    assert (spout[0] - grip[0]) * ahead > 0   # the spout in front of the hand
    run(anims)
    (hand,) = kit.holding
    assert can.grip_point()[:2] == pytest.approx(kit.hand_point(hand)[:2], abs=1e-6)   # still in the hand after the pour


@pytest.mark.render
def test_a_prop_held_off_stage_before_an_entrance_stays_out_of_view(make_project, tmp_path: Path) -> None:
    """kit waits beyond the right edge holding the gift: the gift in its hand (in front of it,
    towards the stage) showed at the edge of the view before kit came in."""
    cast = [{"name": "pip", "look": {"body": "bean"}}, {"name": "kit", "look": {"body": "tall"}}]
    beats = [{"text": "Pip waits for a visitor.", "actions": [{"hold": "kit", "to": "gift", "at": 0}]},
             {"text": "Here comes Kit with a present.", "actions": [{"enter": "kit"}]}]
    params = {"props": [{"prop": "gift", "at": 0.8}], "characters": [{"name": "pip", "at": 0.3}, {"name": "kit", "at": 0.7}]}
    project = Project.load(make_project(minimal_config(characters=cast, scenes=[{"id": "park", "type": "stage", "params": params, "beats": beats}])))
    _, objects = render_with_layout(project, "park", tmp_path / "media")
    gift = next((o for o in objects if o["name"] == "gift"), None)
    assert gift is None or gift["bbox"][0] >= 160, gift["bbox"]   # not in the 160 px wide view
