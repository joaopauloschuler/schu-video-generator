"""Step 28 scene type ``diagram`` (alias ``flowchart``): params and the edge shorthand,
reference checks with suggestions, layout direction per frame, reveal order (edges grow before
the nodes they lead to), explicit steps, the highlight path, targets and timing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_actions import beat_total, beats, plays, render
from test_builtin_scenes import cls_of, expected_duration, render_scene
from test_comparison_table import safe_area_of
from test_schema import errors
from vidgen import extensions, registry, schema
from vidgen.cli import check_project, project_problems
from vidgen.project import Project
from vidgen.scenes.diagram import Diagram, parse_edges
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
FLOW = {
    "nodes": [{"id": "start", "label": "Start", "shape": "pill"}, {"id": "ok", "label": "Tests pass?", "shape": "diamond"},
              {"id": "fix", "label": "Fix it"}, {"id": "ship", "label": "Ship", "shape": "circle", "icon": "rocket"}],
    "edges": ["start -> ok", "ok -> ship: yes", "ok -> fix: no", "fix --> ok"],
}


def load(make_project, scenes: list[dict[str, Any]]) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))


def params(**changes: Any) -> Any:
    return cls_of("diagram").validate_params({**FLOW, **changes}, Theme())


def three_beats() -> list[dict[str, str]]:
    return [{"text": "one two three four five six"}, {"text": "seven eight nine ten"}, {"text": "eleven twelve thirteen"}]


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- params ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a -> b", [("a", "b", "", "solid")]),
        ("a->b", [("a", "b", "", "solid")]),
        ("Load data -> Train: 3 epochs", [("Load data", "Train", "3 epochs", "solid")]),
        ("a --> b: maybe", [("a", "b", "maybe", "dashed")]),
        ("a -> b --> c -> d", [("a", "b", "", "solid"), ("b", "c", "", "dashed"), ("c", "d", "", "solid")]),
        ("x-1 -> y.2", [("x-1", "y.2", "", "solid")]),
    ],
)
def test_edge_shorthand(text: str, expected: list[tuple[str, str, str, str]]) -> None:
    got = [(e["from"], e["to"], e.get("label", ""), e["style"]) for e in parse_edges(text)]
    assert got == expected


def test_params_shorthand_and_defaults() -> None:
    p = cls_of("diagram").validate_params({"nodes": ["a", "b", {"id": "c", "label": "Sea"}], "edges": ["a -> b -> c", {"from": "a", "to": "c", "style": "dashed"}]}, Theme())
    assert [n.text() for n in p.nodes] == ["a", "b", "Sea"]
    assert [e.ref() for e in p.edges] == ["a->b", "b->c", "a->c"] and p.edges[2].style == "dashed"
    assert (p.direction, p.routing, p.reveal, p.shape, p.steps, p.highlight) == ("auto", "curved", "nodes", "round", None, [])
    assert registry.get("flowchart").cls is Diagram is registry.get("diagram").cls


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"edges": ["start -> shp"]}, r"edges\[0\] \(start -> shp\): unknown node 'shp'; did you mean 'ship'\? \(nodes: start, ok, fix, ship\)"),
        ({"edges": ["start -> start"]}, "points to itself"),
        ({"edges": ["start -> ok", "start->ok"]}, r"edges\[1\]: start -> ok is listed twice"),
        ({"edges": ["start ok"]}, "is not an edge; write 'from -> to'"),
        ({"edges": ["start -> ok -> fix: label"]}, "a label needs a single edge"),
        ({"edges": ["start -> "]}, "needs a node id on both sides"),
        ({"edges": [{"from": "start", "target": "ok"}]}, "Field required|Extra inputs"),
        ({"nodes": ["a", "a"], "edges": []}, r"nodes\[1\]: id 'a' is used twice"),
        ({"nodes": ["a:b"], "edges": []}, "node id 'a:b'"),
        ({"nodes": [], "edges": []}, "at least 1 item"),
        ({"nodes": [{"id": "a", "shape": "star"}], "edges": []}, "'box', 'round', 'pill', 'circle', 'diamond' or 'cylinder'"),
        ({"steps": [["start"], ["sihp"]]}, r"steps\[1\]: unknown node 'sihp'; did you mean 'ship'"),
        ({"steps": [["start", "ok->fixx"]]}, r"steps\[0\]: unknown edge 'ok->fixx'; did you mean 'ok->fix'"),
        ({"steps": ["start", ["ok", "start"]]}, r"steps\[1\]: 'start' is already in an earlier step"),
        ({"highlight": ["start", "nope"]}, "highlight: unknown node 'nope'"),
        ({"direction": "RL"}, "'auto', 'LR' or 'TB'"),
        ({"node_color": "nope"}, "unknown theme color 'nope'"),
    ],
)
def test_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception, match=message):
        params(**changes)


def test_refs_tolerate_spaces_around_arrows() -> None:
    p = params(steps=["start", ["ok -> fix", "ship"]], highlight=["start", "ok", "ok ->ship"])
    assert p.resolve("ok -> fix", "x") == ("edge", ("ok", "fix")) and p.resolve("ship", "x") == ("node", "ship")


def test_target_names() -> None:
    cls = cls_of("diagram")
    assert cls.target_names(params(heading="H")) == [
        "heading", "node1", "node:start", "node2", "node:ok", "node3", "node:fix", "node4", "node:ship",
        "edge:start->ok", "edge:ok->ship", "edge:ok->fix", "edge:fix->ok",
    ]
    assert cls.target_names(params())[0] == "node1"


def test_schema_accepts_shorthands_and_objects() -> None:
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), [Theme()])
    scene = {"id": "d", "type": "flowchart", "duration": 2}
    assert errors(doc, minimal_config(scenes=[{**scene, "params": {**FLOW, "steps": ["start", ["ok", "ok->fix"]], "highlight": ["start", "ok"]}}])) == []
    assert errors(doc, minimal_config(scenes=[{**scene, "params": {"nodes": ["a"], "edges": [{"from": "a", "to": "b", "colour": "x"}]}}]))


def test_validate_reports_bad_references_and_targets(make_project) -> None:
    scenes = [{"id": "d", "type": "diagram", "params": FLOW, "beats": beats([{"highlight": ["node:ok", "edge:ok->ship"]}], [{"zoom": "node:shp"}])}]
    problems = project_problems(load(make_project, scenes))
    assert [p.location for p in problems] == ["scenes[0].beats[1].actions[0].target"]
    assert "unknown target 'node:shp' for scene type 'diagram'" in problems[0].message and "'node:ship'" in problems[0].message
    root = make_project(minimal_config(scenes=[{"id": "a", "type": "flowchart", "params": {"nodes": ["a"], "edges": ["a -> b"]}, "duration": 2}]))
    assert check_project(Project.load(root))[0] == "scenes[0].params: edges[0] (a -> b): unknown node 'b' (nodes: a)"


# ----- rendering ------------------------------------------------------------------------------------


def drawing(scene: Any) -> Any:
    return scene._drawing


def centres(scene: Any) -> dict[str, np.ndarray]:
    return {k: v[0].get_center() for k, v in drawing(scene).nodes.items()}


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)])
@pytest.mark.parametrize(
    ("p", "timing"),
    [
        ({**FLOW, "heading": "Release flow", "highlight": ["start", "ok", "ship"]}, "three"),
        ({**FLOW, "routing": "orthogonal", "reveal": "layers"}, "one"),
        ({"nodes": ["a", {"id": "b", "shape": "cylinder", "icon": "database"}, {"id": "c", "shape": "box"}], "edges": ["a -> b: store", "a -> c"], "routing": "straight", "reveal": "all"}, "three"),
        ({"nodes": ["a", "b"], "edges": ["a -> b"]}, "silent"),
    ],
)
def test_diagram_renders_within_its_beats_and_the_safe_area(p: dict[str, Any], timing: str, size: tuple[int, int], make_project, media: Path) -> None:
    extra = {"silent": {"duration": 2.0}, "one": {"beats": three_beats()[:1]}, "three": {"beats": three_beats()}}[timing]
    project = load(make_project, [{"id": "s", "type": "diagram", "params": p, **extra}])
    scene, duration, portrait = render_scene(project, "s", media, *size)
    assert portrait == (size[1] > size[0])
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    assert all(scene.beat_busy[b] <= scene.beat_duration(b) + scene.pad + 1e-6 for b in scene.beat_busy)
    registered = sorted(n for t in scene.targets for n in t.names)
    assert registered == sorted(type(scene).target_names(scene.params))
    safe = safe_area_of(size)
    for t in scene.targets:
        assert safe.contains(t.mobject, tolerance=0.05), t.name


@pytest.mark.render
def test_direction_follows_the_frame_and_can_be_forced(make_project, media: Path) -> None:
    chain = {"nodes": ["a", "b", "c"], "edges": ["a -> b -> c"]}
    project = load(make_project, [
        {"id": "auto", "type": "diagram", "params": chain, "beats": three_beats()},
        {"id": "tb", "type": "diagram", "params": {**chain, "direction": "TB"}, "beats": three_beats()},
    ])
    wide = centres(render(project, "auto", media))
    assert wide["a"][0] < wide["b"][0] < wide["c"][0] and abs(wide["a"][1] - wide["c"][1]) < 1e-6   # LR in 16:9
    tall = centres(render(project, "auto", media, size=(90, 160)))
    assert tall["a"][1] > tall["b"][1] > tall["c"][1] and abs(tall["a"][0] - tall["c"][0]) < 1e-6   # TB in 9:16
    forced = centres(render(project, "tb", media))
    assert forced["a"][1] > forced["b"][1] > forced["c"][1]


@pytest.mark.render
def test_arrowheads_end_on_the_target_outline_outside_the_node(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "diagram", "params": FLOW, "beats": three_beats()}])
    scene = render(project, "s", media)
    d = drawing(scene)
    for k, edge in enumerate(scene.params.edges):
        tip = d.edges[k].tip
        node = d.nodes[edge.to][0]
        apex = tip.get_vertices()[0]
        base = (tip.get_vertices()[1] + tip.get_vertices()[2]) / 2
        centre = node.get_center()
        # the apex touches the node's bounding box; the base is farther from the centre than the apex
        assert np.linalg.norm(base - centre) > np.linalg.norm(apex - centre)
        assert abs(apex[0] - centre[0]) <= node.width / 2 + 0.02 and abs(apex[1] - centre[1]) <= node.height / 2 + 0.02
        line = d.edges[k].line
        if line.has_points():   # solid: the line stops under the arrowhead
            assert np.linalg.norm(line.get_end() - apex) == pytest.approx(np.linalg.norm(base - apex) * 0.9, abs=0.02)


@pytest.mark.render
def test_nodes_appear_in_layout_order_after_their_incoming_edges(make_project, media: Path) -> None:
    p = {"nodes": ["a", "b", "c"], "edges": ["a -> b", "b -> c", "a -> c"]}
    project = load(make_project, [{"id": "s", "type": "diagram", "params": p, "beats": three_beats()}])
    scene = render(project, "s", media)
    shown = [[n for n in "abc" if scene.is_shown(f"node:{n}")]]
    assert shown == [["a", "b", "c"]]
    names = [" ".join(a) for b in scene.beats for a in plays(scene, b.id)]
    assert len(names) == 3   # one node per beat
    assert "Create" in names[1] and "Create" in names[2]   # the edges grow before b, then c
    assert all(scene.is_shown(f"edge:{e}") for e in ("a->b", "b->c", "a->c"))


@pytest.mark.render
def test_explicit_steps_and_edges_named_later(make_project, media: Path) -> None:
    p = {"nodes": ["a", "b", "c", "d"], "edges": ["a -> b", "a -> c", "b -> d"], "steps": [["a", "b", "c"], ["a->c"]]}
    project = load(make_project, [{"id": "s", "type": "diagram", "params": p, "beats": three_beats()}])
    scene = render(project, "s", media, fade=False)
    assert scene._step_groups(scene.graph_layout) == [(["a", "b", "c"], []), ([], ["a->c"]), (["d"], [])]
    assert all(scene.is_shown(t) for t in ("node:d", "edge:b->d", "edge:a->c"))
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)


@pytest.mark.render
def test_highlight_path_colours_nodes_and_edges_and_dims_the_rest(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "diagram", "params": {**FLOW, "highlight": ["start", "ok", "ship"]}, "beats": three_beats()}])
    scene = render(project, "s", media)
    d = drawing(scene)
    highlight = scene.theme.color("highlight").lower()
    for node in ("start", "ok", "ship"):
        assert d.nodes[node][0].get_stroke_color().to_hex().lower() == highlight
    assert d.nodes["ship"][1].get_color().to_hex().lower() == highlight   # its icon
    label = d.nodes["ok"][-1].family_members_with_points()[0]
    assert label.get_fill_color().to_hex().lower() == scene.theme.color("text").lower()   # labels keep their colour
    edges = {e.ref(): d.edges[k] for k, e in enumerate(scene.params.edges)}
    assert edges["start->ok"].line.get_stroke_color().to_hex().lower() == highlight
    assert edges["ok->ship"].line.get_stroke_color().to_hex().lower() == highlight
    assert max(m.get_stroke_opacity() for m in edges["ok->fix"].line.family_members_with_points()) == pytest.approx(scene.dimmed_opacity, abs=0.02)
    assert max(m.get_fill_opacity() for m in d.nodes["fix"][-1].family_members_with_points()) == pytest.approx(scene.dimmed_opacity, abs=0.02)


@pytest.mark.render
def test_actions_on_nodes_and_edges(make_project, media: Path) -> None:
    acts = beats([{"reveal": "node:ship"}], [{"highlight": ["node:ok", "edge:ok->*"], "style": ["box"]}, {"dim": "node:fix", "at": 0.5}], [{"zoom": "node:ok"}])
    project = load(make_project, [{"id": "s", "type": "diagram", "params": FLOW, "beats": acts}])
    scene = render(project, "s", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert scene.is_shown("node:ship")
    assert any("MoveCamera" in p.animations for p in scene.play_log)


@pytest.mark.render
@pytest.mark.slow
def test_a_crowded_diagram_warns(make_project, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    ids = [f"Stage number {i} of the pipeline" for i in range(18)]
    p = {"nodes": ids, "edges": [f"{ids[i]} -> {ids[i + 1]}" for i in range(17)]}
    project = load(make_project, [{"id": "s", "type": "diagram", "params": p, "duration": 1.0}])
    with caplog.at_level(logging.WARNING):
        scene = render(project, "s", media, size=(90, 160))
    assert any("do not fit this frame at the readable size" in r.getMessage() and "split it into smaller diagrams" in r.getMessage() for r in caplog.records)
    safe = safe_area_of((90, 160))
    assert all(safe.contains(t.mobject, tolerance=0.05) for t in scene.targets)


def test_list_scenes_shows_the_from_alias() -> None:
    from vidgen.describe import describe_params, params_json

    edge = next(f for f in params_json(Diagram.Params) if f["name"] == "edges")
    assert [f["name"] for f in edge["nested"][0]["fields"]][:2] == ["from", "to"]
    assert "    from: str" in describe_params(Diagram.Params)


@pytest.mark.render
def test_a_step_grows_edges_before_the_nodes_they_lead_to(make_project, media: Path) -> None:
    p = {"nodes": ["a", "b", "c", "d"], "edges": ["a -> b", "a -> c", "b -> d", "d -> b"], "reveal": "layers"}
    project = load(make_project, [{"id": "s", "type": "diagram", "params": p, "beats": three_beats()}])
    scene = render(project, "s", media)
    d = drawing(scene)
    scene.remove(*[d.nodes[n] for n in "bcd"], *[e.group for e in d.edges], *[e.pill for e in d.edges if e.pill])
    for mob in [*d.nodes.values(), *[e.group for e in d.edges]]:
        for part in mob.get_family():
            scene.remove(part)
    scene.add(d.nodes["a"])

    def leaves(anim: Any) -> list[Any]:
        inner = getattr(anim, "animations", None)
        return [x for a in inner for x in leaves(a)] if inner else [anim.mobject]

    nodes = {id(m): n for n, m in d.nodes.items()}
    lines = {id(e.line) for e in d.edges}

    def wave(anim: Any) -> tuple[list[str], int]:
        mobs = leaves(anim)
        return sorted(nodes[id(m)] for m in mobs if id(m) in nodes), sum(id(m) in lines for m in mobs)

    waves = scene._reveal(["b", "c"], [], set())
    assert [wave(w) for w in waves] == [([], 2), (["b", "c"], 0)]   # both edges grow, then both nodes
    scene.add(d.nodes["b"], d.nodes["c"])
    cycle = scene._reveal(["d"], [], set())   # a -> b, a -> c (between shown nodes) and b -> d grow, d appears, d -> b grows
    assert [wave(w) for w in cycle] == [([], 3), (["d"], 0), ([], 1)]
