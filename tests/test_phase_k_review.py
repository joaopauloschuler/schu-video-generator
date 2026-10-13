"""Review of Phase K (Step 116): the indoor example `examples/cartoon-muffin-mystery` end to end
through the CLI and `vidgen mcp` without rendering (`screenplay`, `cast`, `validate`, `direct`),
and the fixes found on the way: `vidgen screenplay`'s text summary with a silent card, a prop held
by a character who waits off stage for its `enter`, a held prop fading with its holder through a
door, and a turn to the front (or a look from it) keeping the head upright."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from test_cartoon_acting import FakeScene, figure, run, target, use
from vidgen.cartoon.acting import LOOK_EYES_AHEAD, look_pose
from vidgen.cartoon.contrast import MIN_CONTRAST, character_pairs
from vidgen.cartoon.props import draw_prop
from vidgen.cartoon.transition import Walk
from vidgen.cli import main
from vidgen.project import Project
from vidgen.theme import Theme

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "cartoon-muffin-mystery"
SCREENPLAY = EXAMPLE / "muffin_mystery.md"


def json_out(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


# ----- the example end to end (no render) -------------------------------------------------------------


def test_the_example_validates_directs_and_uses_phase_k(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "muffin")
    assert main(["validate", str(root), "--json"]) == 0
    assert json_out(capsys)["ok"]
    assert main(["direct", str(root), "--json"]) == 0
    added = [a for s in json_out(capsys)["scenes"] for b in s["beats"] for a in b["actions"]]
    assert any(next(iter(a)) == "effect" for a in added)   # auto_direct's symbols too
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("room:", "species: dog", "type: card", "iris_out", "iris_in", "effect:", "run_to:", "depth: 0}", "to: front",
                 "door: door", "against: wall", "sit_on:", "jump:"):
        assert used in text, used
    pairs = character_pairs(Project.load(root).config, Theme())
    assert len(pairs) == 3 and all(pair.score >= MIN_CONTRAST for _, pair in pairs)   # lint look_alike stays quiet


def test_screenplay_summary_counts_a_silent_card(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["screenplay", str(SCREENPLAY), "--out", str(tmp_path / "draft")]) == 0   # was a KeyError: a silent card has no beats
    assert "wrote 4 scenes (12 beats), 3 characters" in capsys.readouterr().out
    assert main(["screenplay", str(SCREENPLAY), "--out", str(tmp_path / "draft2"), "--json"]) == 0
    doc = json_out(capsys)
    assert doc["scene_count"] == 4 and doc["beat_count"] == 12 and doc["todo_count"] == 0


def test_the_screenplay_with_a_random_cast_of_dogs_and_people(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cast = tmp_path / "shared" / "cast.yaml"
    assert main(["cast", "--random", "3", "--species", "dog", "human", "--seed", "2", "--out", str(cast), "--json"]) == 0
    capsys.readouterr()
    out = tmp_path / "episode"
    assert main(["screenplay", str(SCREENPLAY), "--out", str(out), "--cast", str(cast), "--json"]) == 0
    capsys.readouterr()
    assert main(["validate", str(out), "--json"]) == 0
    assert json_out(capsys)["ok"]


def test_mcp_screenplay_and_validate_of_the_example(tmp_path: Path) -> None:
    from test_mcp import doc_of, run_session

    root = tmp_path / "root"
    shutil.copytree(EXAMPLE, root / "muffin")

    async def body(client: Any) -> None:
        doc = doc_of(await client.call_tool("screenplay", {"input_path": "muffin/muffin_mystery.md", "out": "draft"}))
        assert doc["scene_count"] == 4 and doc["todo_count"] == 0
        assert doc_of(await client.call_tool("validate", {"project": "muffin"}))["ok"]

    run_session(root, body)


# ----- fixes found on the way --------------------------------------------------------------------------


def test_a_prop_held_before_its_holders_entrance_waits_off_stage_with_it() -> None:
    from vidgen import extensions, registry

    extensions.load_builtins()
    stage = registry.get("stage").cls

    def uses(*written: tuple[str, str, str | None]) -> Any:
        rows = [SimpleNamespace(kind=SimpleNamespace(name=kind), config=SimpleNamespace(targets=lambda who=who: [who]),
                                action=SimpleNamespace(options=SimpleNamespace(to=to))) for kind, who, to in written]
        return SimpleNamespace(_actions=SimpleNamespace(uses=rows), props={"basket": object(), "cup": object()})

    held = stage._held_before_entering
    assert held(uses(("hold", "olen", "basket"), ("enter", "olen", None)), {"olen": None}) == {"basket": "olen"}
    assert held(uses(("enter", "olen", None), ("hold", "olen", "basket")), {"olen": None}) == {}   # held after it came in
    assert held(uses(("hold", "mira", "cup"), ("enter", "olen", None)), {"olen": None}) == {}      # mira is on stage
    assert held(uses(("hold", "o*", "basket")), {"olen": None, "ann": None}) == {"basket": "olen"}


def test_what_a_character_carries_fades_with_it_through_a_door() -> None:
    pip = figure()
    basket = draw_prop("basket", height=0.2 * pip.character_height, theme=Theme(), name="basket")
    own = [m.fill_rgbas[:, 3].copy() for m in basket.get_family()]
    walk = Walk(pip, 2.0, start_x=-2.0, fade_in=0.35, carried=[basket])
    walk.begin()
    walk.interpolate(0.0)
    assert pip.shown == 0.0 and all(m.fill_rgbas[:, 3].max() == 0 for m in basket.get_family())
    walk.interpolate(1.0)
    assert all((m.fill_rgbas[:, 3] == a).all() for m, a in zip(basket.get_family(), own))


def test_turning_to_the_front_straightens_the_head() -> None:
    from vidgen.scenes.acting import looked_state

    pip = figure()
    pip.set_state(looked_state(pip, look_pose(1.5, -3.0, "right")))   # looking down at something low
    assert pip.state().parts["head"].angle < 0
    run(use("turn", "pip", to="front").apply(FakeScene(pip=pip), [target("pip", pip)]))
    head = pip.state().parts["head"]
    assert pip.facing == "front" and head.angle == 0.0   # its angle would tilt the front view sideways


def test_a_look_from_the_front_moves_the_eyes_not_the_head() -> None:
    down = look_pose(0.01, -2.0, "front")
    assert down.facing == "front" and down.head_angle == 0.0
    assert down.eyes_shift[0] == 0.0 and -LOOK_EYES_AHEAD <= down.eyes_shift[1] < 0
    assert look_pose(0.01, -2.0, "right").head_angle < 0   # from the side the head still tilts
