"""Step 84: cartoon lint rules (``off_stage``, ``character_overlap``, ``bubble_overlap``,
``facing_away``, ``hidden_speaker``, ``mouth_without_voice``) on synthetic layout dumps, one
passing and one failing case each; ``lint_ignore`` for them; the character keys the layout dump
gives them (a tiny render)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import minimal_config
from test_cartoon_acting import FakeScene, acting_project, figure, run, target, use
from test_cartoon_stage import render_with_layout
from test_lint import fake_render
from vidgen.cartoon.transition import Walk
from vidgen.cartoon.visemes import VisemeCue, VisemeTrack
from vidgen.config import LintRules
from vidgen.lint import RULES, StillContext, lint_project
from vidgen.project import Project
from vidgen.render.worker import scene_layout_path

CARTOON_RULES = ("off_stage", "character_overlap", "bubble_overlap", "facing_away", "hidden_speaker", "mouth_without_voice")


def fig(name: str, box: list[float], *, order: int = 5, **keys: Any) -> dict[str, Any]:
    """A ``character`` object as the layout dump writes it (``facing`` right, not speaking)."""
    return {"id": name, "kind": "character", "class": "Character", "name": name, "path": f"Stage/{name}", "bbox": box,
            "opacity": 1.0, "z": 0.0, "order": order, "parts": 9, "facing": "right", "speaking": False, **keys}


def thing(oid: str, box: list[float], *, kind: str = "prop", order: int = 9, **keys: Any) -> dict[str, Any]:
    return {"id": oid, "kind": kind, "class": "Prop", "name": oid, "path": f"Stage/{oid}", "bbox": box,
            "opacity": 1.0, "z": 0.0, "order": order, "parts": 3, "fill": None, "stroke": None, **keys}


def check(name: str, objects: list[dict[str, Any]], **frame: Any) -> list[Any]:
    ctx = StillContext({"width": 854, "height": 480}, {"beat": "b2", "k": 1, "n": 1, **frame}, objects)
    return list(RULES[name].check(ctx, getattr(LintRules(), name)))


def test_off_stage() -> None:
    cut = fig("pip", [-40, 100, 60, 400])
    (issue,) = check("off_stage", [cut])
    assert issue.message.startswith("character 'pip' is partly off stage at the left edge (40% of its box outside the view)")
    assert check("off_stage", [fig("pip", [100, 100, 200, 400])]) == []
    assert check("off_stage", [fig("pip", [-40, 100, 60, 400], passage="enter")]) == []   # walking in
    assert check("off_stage", [fig("pip", [-200, 100, -100, 400])]) == []   # waiting off stage
    assert check("off_stage", [cut], camera={"zoom": 2.0}) == []
    assert check("off_frame", [cut]) == []   # characters are off_stage's


def test_character_overlap() -> None:
    kit = fig("kit", [500, 100, 600, 400])
    (issue,) = check("character_overlap", [fig("pip", [540, 100, 640, 400]), kit])
    assert issue.message.startswith("character 'pip' and character 'kit' stand on each other (60% of the narrower one's width)")
    assert check("character_overlap", [fig("pip", [590, 100, 690, 400]), kit]) == []   # side by side
    assert check("character_overlap", [fig("pip", [540, 100, 640, 400], walked_in="b2"), kit]) == []   # walk_overlap's


def test_prop_overlap() -> None:
    """Props standing on the floor at about the same depth (a door over the sofa at the wall);
    not a prop in front of another, one lifted onto another or hung above it, a rug, a held one."""
    sofa = thing("sofa", [100, 300, 260, 400], prop="sofa", depth=0.4)
    door = thing("door", [60, 200, 140, 400], prop="door", depth=0.4)
    (issue,) = check("prop_overlap", [sofa, door])
    assert issue.message.startswith("prop 'sofa' and prop 'door' stand on each other at the same depth (50% of the narrower one's width); move one")
    assert issue.value == 0.5 and issue.limit == 0.15
    assert check("prop_overlap", [sofa, thing("door", [20, 200, 100, 400], prop="door", depth=0.4)]) == []   # side by side
    assert check("prop_overlap", [sofa, thing("armchair", [150, 320, 230, 420], prop="armchair", depth=0.2)]) == []   # in front
    assert len(check("prop_overlap", [sofa, thing("plant", [150, 320, 230, 420], prop="houseplant", depth=0.3)])) == 1   # 0.1 apart: on it
    assert check("prop_overlap", [sofa, thing("picture", [140, 200, 220, 260], prop="picture", depth=0.4, raised=True)]) == []   # on the wall
    assert check("prop_overlap", [sofa, thing("basket", [150, 280, 190, 300], prop="basket", depth=0.4, raised=True)]) == []   # lifted onto it
    assert check("prop_overlap", [sofa, thing("rug", [80, 390, 300, 410], prop="rug", depth=0.4, flat=True)]) == []   # lies under it
    assert check("prop_overlap", [sofa, thing("cup", [150, 300, 170, 320], prop="cup", depth=0.4, held_by="pip")]) == []
    assert check("prop_overlap", [fig("pip", [100, 100, 200, 400], depth=0.4), sofa]) == []   # characters are character_overlap's


def test_bubble_overlap() -> None:
    kit = fig("kit", [500, 100, 600, 400], face=[500, 100, 600, 180])
    low = thing("plate", [480, 60, 640, 150], kind="shape", bubble="pip")
    (issue,) = check("bubble_overlap", [kit, low])
    assert issue.message.startswith("the speech bubble of character 'pip' covers the face of character 'kit' (62% of the face)")
    high = thing("plate", [480, 0, 640, 90], kind="shape", bubble="pip")
    assert check("bubble_overlap", [kit, high]) == []
    other = thing("plate2", [600, 20, 760, 80], kind="shape", bubble="kit")
    (issue,) = check("bubble_overlap", [kit, high, other])
    assert issue.message.startswith("the speech bubbles of character 'pip' and character 'kit' overlap (25% of the smaller one)")


def test_facing_away() -> None:
    kit = fig("kit", [600, 100, 700, 400], facing="left")
    assert check("facing_away", [fig("pip", [100, 100, 200, 400], speaking=True), kit]) == []
    (issue,) = check("facing_away", [fig("pip", [100, 100, 200, 400], speaking=True, facing="left"), kit])
    assert issue.message.startswith("character 'pip' speaks facing left, away from character 'kit' (the nearest character, on its right)")
    assert check("facing_away", [fig("pip", [100, 100, 200, 400], facing="left"), kit]) == []   # not speaking
    # the one it last looked at counts before the nearest one; the camera: it talks to the viewer
    pip = fig("pip", [300, 100, 400, 400], speaking=True, looked_at="kit")
    near = fig("bo", [450, 100, 550, 400])
    (issue,) = check("facing_away", [pip, near, fig("kit", [0, 100, 100, 400])])
    assert "away from character 'kit' (the one it last looked at, on its left)" in issue.message
    assert check("facing_away", [{**pip, "looked_at": "camera"}, near, fig("kit", [0, 100, 100, 400])]) == []


def test_hidden_speaker() -> None:
    pip = fig("pip", [300, 100, 400, 400], speaking=True, face=[310, 100, 370, 160])
    (issue,) = check("hidden_speaker", [pip, thing("tree", [280, 50, 420, 300], order=9)])
    assert issue.message.startswith("character 'pip' speaks with 100% of its face hidden behind prop 'tree'")
    assert check("hidden_speaker", [pip, thing("tree", [280, 50, 420, 300], order=3)]) == []   # drawn behind it
    assert check("hidden_speaker", [{**pip, "speaking": False}, thing("tree", [280, 50, 420, 300])]) == []


def test_mouth_without_voice() -> None:
    (issue,) = check("mouth_without_voice", [fig("pip", [100, 100, 200, 400], speaking=True, viseme="A")], narrating=False)
    assert issue.message.startswith("character 'pip' moves its mouth (lip sync shows 'A') while no narration is heard")
    assert check("mouth_without_voice", [fig("pip", [100, 100, 200, 400], speaking=True, viseme="A")], narrating=True) == []
    assert check("mouth_without_voice", [fig("pip", [100, 100, 200, 400], speaking=True, viseme="rest")], narrating=False) == []


def test_lint_ignore_and_mid_stills(make_project) -> None:
    """Each rule's finding reaches ``lint`` and ``lint_ignore`` (by rule, or by object name) drops it;
    a mid-action still with the same problems is not checked."""
    data = minimal_config(preview={"width": 854, "height": 480, "fps": 15})
    root = make_project(data)
    project = Project.load(root)
    bad = [
        fig("pip", [-40, 100, 60, 400], speaking=True, facing="left", face=[0, 100, 60, 160], viseme="A"),
        fig("kit", [500, 100, 600, 400], face=[500, 100, 600, 180], order=6),
        fig("bo", [540, 100, 640, 400], order=7),
        thing("plate", [480, 60, 640, 150], kind="shape", bubble="pip", order=8),
        thing("tree", [-50, 50, 100, 300], order=9),
    ]
    fake_render(project, "intro", [bad, bad])
    path = scene_layout_path(project, True, "intro")
    doc = json.loads(path.read_text(encoding="utf-8"))
    for frame in doc["frames"]:
        frame["narrating"] = False
    doc["frames"].append({**doc["frames"][0], "k": 0, "mid": "walk_to pip", "frame": 5})
    path.write_text(json.dumps(doc), encoding="utf-8")
    result = lint_project(Project.load(root), rules=list(CARTOON_RULES), scenes=["intro"])
    assert sorted({f.rule for f in result.findings}) == sorted(CARTOON_RULES) and result.stills == 2
    data["scenes"][0]["lint_ignore"] = [*CARTOON_RULES[:3], {"rule": "all", "object": "pip"}]
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    result = lint_project(Project.load(root), rules=list(CARTOON_RULES), scenes=["intro"])
    assert result.findings == [] and result.ignored > 0


def test_what_the_layout_dump_reads_from_a_character() -> None:
    pip, kit = figure("pip"), figure("kit").shift([4.0, 0.0, 0.0])
    scene = FakeScene(pip=pip, kit=kit)
    look = use("look_at", to="kit")
    run(look.apply(scene, [target("pip", pip)]))
    assert pip.looked_at == "kit"
    run(look.revert(scene, [target("pip", pip)]))
    assert pip.looked_at is None
    assert pip.spoken_viseme is None
    pip.lip_sync(VisemeTrack((VisemeCue(0.0, 1.0, "A"),)), clock=lambda: 0.5)
    assert pip.spoken_viseme == "A"
    walk = Walk(pip, 3.0, start_x=-10.0)
    walk.begin()
    assert pip.passage == "enter"
    walk.interpolate(1.0)
    walk.finish()
    walk.clean_up_from_scene(None)
    assert pip.passage is None


@pytest.mark.render
def test_layout_dump_character_keys(make_project, tmp_path: Path) -> None:
    from vidgen.introspect import LayoutRecorder

    project = acting_project(make_project, [
        {"text": "Hello, I am Pip.", "voice": "pip_voice", "actions": [{"look_at": "pip", "to": "kit"}]},
        {"text": "Hi.", "voice": "kit_voice", "actions": [{"say": "kit", "bubble": "Hi!"}]},
    ])
    recorder = LayoutRecorder()
    render_with_layout(project, "park", tmp_path / "media", recorder)
    ends = [f for f in recorder.frames if f["k"] == f["n"]]
    assert [f["narrating"] for f in ends] == [False, False]   # beat ends: in the pad
    last = {o["name"]: o for o in ends[-1]["objects"] if o["kind"] == "character"}
    pip, kit = last["pip"], last["kit"]
    assert kit["speaking"] and not pip["speaking"] and kit["facing"] == "left" and pip["looked_at"] == "kit"
    assert kit["viseme"] == "rest" and "passage" not in kit
    x0, y0, x1, y1 = kit["bbox"]
    assert x0 <= kit["face"][0] < kit["face"][2] <= x1 and y0 <= kit["face"][1] < kit["face"][3] <= y1
    assert {o["kind"] for o in ends[-1]["objects"] if o.get("bubble") == "kit"} == {"shape", "text"}
    for frame in ends:   # a plain two-character dialogue gives no cartoon finding
        ctx = StillContext({"width": 160, "height": 90}, frame, frame["objects"])
        for name in CARTOON_RULES:
            assert list(RULES[name].check(ctx, getattr(LintRules(), name))) == [], name
