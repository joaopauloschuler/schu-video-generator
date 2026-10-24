"""The ``iso_diagram`` actions and labels (DESIGN.md §90.8-90.10): the label geometry, placing
labels clear of blocks, labels and connectors, the slanted grid in 9:16, the action checks, the
``iso_labels`` lint rule, and tiny renders of every action."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import tempconfig

from test_actions import beats, project_with, render
from vidgen import extensions, registry
from vidgen.cli import project_problems
from vidgen.config import IsoLabelsRule
from vidgen.iso_blocks import BlockSpec, ItemSpec, block_outline, layout_iso_diagram, picture_size, slant
from vidgen.iso_labels import Obstacles, clip_area, convex_hull, hull_gap, ray_exit, rect_exit, rect_of, slide_out
from vidgen.lint import RULES, StillContext
from vidgen.render.worker import frame_size

SQUARE = convex_hull([(0, 0), (2, 0), (2, 2), (0, 2), (1, 1)])


# ----- label geometry ------------------------------------------------------------------------------


def test_hull_and_areas() -> None:
    assert len(SQUARE) == 4   # the inner point is dropped
    assert clip_area((1, 1, 3, 3), SQUARE) == pytest.approx(1.0)
    assert clip_area((5, 5, 6, 6), SQUARE) == 0.0
    diamond = convex_hull([(0, -1), (1, 0), (0, 1), (-1, 0)])
    assert clip_area((-5, -5, 5, 5), diamond) == pytest.approx(2.0)
    assert hull_gap((3, 0, 4, 1), SQUARE) == pytest.approx(1.0)
    assert hull_gap((1, 1, 4, 4), SQUARE) == 0.0


def test_a_label_slides_out_of_an_outline_exactly() -> None:
    # a 1 x 0.5 label from the square's middle, upwards: its bottom edge ends gap above the top
    centre = slide_out((1.0, 0.5), (1.0, 1.0), (0.0, 1.0), SQUARE, gap=0.1)
    assert centre == pytest.approx((1.0, 2.0 + 0.1 + 0.25))
    right = slide_out((1.0, 0.5), (1.0, 1.0), (1.0, 0.0), SQUARE)
    assert right == pytest.approx((2.5, 1.0))
    assert slide_out((1.0, 0.5), (9.0, 9.0), (0.0, 1.0), SQUARE) == pytest.approx((9.0, 9.0))   # clear already
    assert ray_exit(SQUARE, (1.0, 1.0), (5.0, 1.0)) == pytest.approx((2.0, 1.0))
    assert rect_exit((0.0, 0.0, 2.0, 1.0), (1.0, 5.0)) == pytest.approx((1.0, 1.0))


def test_obstacles_cost_what_a_label_covers() -> None:
    lines = {"a->b": np.array([[5.0, y] for y in np.linspace(0, 2, 11)])}
    obstacles = Obstacles({"box": SQUARE, "a->b#0": SQUARE + 10}, lines, [(20.0, 20.0, 21.0, 21.0)])
    assert obstacles.cost(rect_of((1, 1), (1, 1))) == pytest.approx(4.0)          # a block's area x BLOCK_WEIGHT
    assert obstacles.cost(rect_of((1, 1), (1, 1)), {"box"}) == 0.0
    assert obstacles.cost(rect_of((11, 11), (1, 1)), {"a->b"}) == 0.0              # a pipe segment of the skipped connector
    assert obstacles.cost(rect_of((5, 1), (1, 1))) > 0                             # over the connector
    assert obstacles.cost(rect_of((20.5, 20.5), (1, 1))) > 0                       # over a label
    near = Obstacles({"box": SQUARE}, clearance=0.3)
    assert near.cost(rect_of((2.6, 1.0), (1.0, 1.0))) > 0                          # not on it, but close enough to read as its
    pushed = near.clear_of_all((1.0, 1.0), (1.0, 1.0), (1.0, 0.0), 0.1)
    assert pushed[0] == pytest.approx(2.0 + 0.3 + 0.5)


def test_block_outlines_slant_and_picture_size() -> None:
    box = layout_iso_diagram([ItemSpec("a", (0, 0), block=BlockSpec("a"))]).blocks["a"]
    assert len(convex_hull(block_outline(box))) == 6   # a box shows six corners
    raised = block_outline(box, lift=1.0)
    assert min(v for _, v in raised) < min(v for _, v in block_outline(box))   # up the picture
    row = [ItemSpec(n, (2.0 * k, 0.0), block=BlockSpec(n)) for k, n in enumerate("abcd")]
    down = slant(row, "x")
    assert [item.at for item in down] == [(0.0, 0.0), (2.0, 2.0), (4.0, 4.0), (6.0, 6.0)]   # straight down the picture
    w0, h0 = picture_size(layout_iso_diagram(row))
    w1, h1 = picture_size(layout_iso_diagram(down))
    assert w1 < w0 and h1 > h0


# ----- params ----------------------------------------------------------------------------------------


def params(**values: Any) -> Any:
    extensions.load_builtins()
    return registry.get("iso_diagram").cls.validate_params(values)


def test_a_grid_with_at_is_slanted_down_a_tall_frame() -> None:
    blocks = [{"id": n, "at": [2 * k, 0]} for k, n in enumerate("abcd")]
    p = params(blocks=blocks)
    assert p.layout(portrait=False).blocks["d"].box.y0 == pytest.approx(0.1)
    assert p.layout(portrait=True).blocks["d"].box.y0 > 5                         # x runs down the frame
    assert params(blocks=blocks, portrait_grid="keep").layout(portrait=True).blocks["d"].box.y0 == pytest.approx(0.1)


def test_one_label_per_block_and_which_targets_have_labels() -> None:
    cls = registry.get("iso_diagram").cls
    p = params(blocks=[{"id": "side", "label": "Weights", "layers": [{"id": "w", "label": "Stored weights", "shape": "database"}]},
                       {"id": "plain", "layers": ["x"]},
                       {"id": "s", "label": "Same", "layers": [{"id": "l1", "label": "Same"}, "l2"]}],
               groups=[{"id": "g", "blocks": ["plain"]}], edges=["side -> s: loads", "plain -> s"])
    assert [(b, label) for b, label, *_ in p.all_blocks()] == [("w", "Stored weights"), ("x", "x"), ("l1", "Same"), ("l2", "l2")]
    assert cls.has_label(p, "stack:side") and cls.has_label(p, "block:w")
    assert not cls.has_label(p, "stack:s")          # its caption repeats a layer's label: not drawn
    assert not cls.has_label(p, "group:g") and cls.has_label(p, "edge:side->s") and not cls.has_label(p, "edge:plain->s")
    assert [cls.target_kind(n) for n in ("heading", "diagram", "block3", "block:w", "stack:s", "group:g", "edge:a->b")] == [
        "heading", "diagram", "block", "block", "stack", "group", "edge"]
    assert params(blocks=[{"id": "s", "layers": ["a", "b"], "label_side": "below"}]).blocks[0].label_side == "below"


# ----- action checks ---------------------------------------------------------------------------------

SCENE = {
    "heading": "Flow",
    "blocks": [{"id": "web", "label": "Web"}, {"id": "db", "label": "Data", "shape": "database"},
               {"id": "app", "label": "App", "layers": ["UI", {"id": "api", "label": "API", "shape": "box"}]}],
    "groups": [{"id": "g", "label": "Back end", "blocks": ["db", "app"]}],
    "edges": ["web -> db: SQL", {"from": "db", "to": "app", "style": "pipe"}],
}


@pytest.mark.parametrize(("action", "message"), [
    ({"raise": "edge:web->db"}, "raise acts on blocks and layers (block:<id>), stacks (stack:<id>), groups (group:<id>); 'edge:web->db' is not one"),
    ({"explode": "block:web"}, "explode acts on stacks (stack:<id>)"),
    ({"flow": "block:web"}, "flow acts on connectors"),
    ({"relabel": "edge:db->app", "text": "x"}, "'edge:db->app' has no label to change; give it a label"),
    ({"raise": "block:web", "by": 9}, "less than or equal to 4"),
])
def test_iso_actions_check_their_targets(make_project, action: dict[str, Any], message: str) -> None:
    problems = project_problems(project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": SCENE, "beats": beats([action])}]))
    assert any(message in p.message for p in problems), [p.message for p in problems]


def test_iso_actions_are_for_iso_diagrams(make_project) -> None:
    scene = {"id": "b", "type": "bullets", "params": {"items": ["One", "Two"]}, "beats": beats([{"raise": "item1"}])}
    problems = project_problems(project_with(make_project, [scene]))
    assert any("raise is an iso_diagram action" in p.message for p in problems)


def test_valid_iso_actions_pass(make_project) -> None:
    acts = [{"build": "block:web", "style": "grow"}, {"raise": "group:g"}, {"lower": "block:api"}, {"explode": "stack:app", "gap": 0.5},
            {"collapse": "stack:app"}, {"flow": "edge:*", "chain": True, "style": "packets"}, {"focus": "stack:app"},
            {"relabel": "block:db", "text": "Data 2"}, {"relabel": "edge:web->db", "text": "SQL 2"}]
    assert project_problems(project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": SCENE, "beats": beats(acts)}])) == []


# ----- lint --------------------------------------------------------------------------------------------


def frame(labels: list[dict[str, Any]], blocks: dict[str, list[list[float]]], edges: dict[str, list[list[float]]] | None = None,
          plates: dict[str, list[list[float]]] | None = None) -> StillContext:
    data = {"labels": labels, "blocks": [{"id": k, "outline": v} for k, v in blocks.items()],
            "plates": [{"id": k, "outline": v} for k, v in (plates or {}).items()], "stacks": [],
            "edges": [{"ref": k, "source": "", "target": "", "points": v} for k, v in (edges or {}).items()]}
    return StillContext({"width": 854, "height": 480}, {"iso_diagram": data}, [])


def label(text: str, kind: str, owner: str, box: list[float], **kw: Any) -> dict[str, Any]:
    return {"kind": kind, "owner": owner, "text": text, "box": box, "on_top": False, "leader": False, **kw}


def box(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def test_lint_catches_a_group_caption_among_its_blocks() -> None:
    """Step 173's still: 'Web tier' over the corner of 'Web 1'."""
    assert list(RULES).index("iso_labels") == list(RULES).index("music_check") - 1 and RULES["iso_labels"].default == "warning"
    ctx = frame([label("Web tier", "group", "web", [310, 150, 435, 180]), label("Web 1", "block", "web1", [385, 115, 470, 140])],
                {"web1": box(385, 155, 470, 245), "lb": box(165, 175, 300, 250)}, plates={"web": box(240, 180, 500, 300)})
    found = list(RULES["iso_labels"].check(ctx, IsoLabelsRule()))
    assert [f.message for f in found] == ["label 'Web tier' (of group 'web') covers block 'web1' (33% of the label); it reads as that block's label"]


def test_lint_catches_overlaps_far_labels_and_hidden_connectors() -> None:
    labels = [label("Load balancer", "block", "lb", [170, 40, 300, 100]), label("Orders", "block", "db", [540, 250, 640, 280]),
              label("writes", "edge", "q->db", [500, 255, 570, 285])]
    ctx = frame(labels, {"lb": box(165, 175, 300, 250), "db": box(560, 290, 620, 380)}, edges={"q->db": [[520, 330], [550, 345]], "w->q": [[505, 260], [520, 270], [540, 280]]})
    messages = [f.message for f in RULES["iso_labels"].check(ctx, IsoLabelsRule())]
    assert any("'Load balancer' (of block 'lb') is 75 px from what it names" in m for m in messages)
    assert any("'writes' (of connector 'q->db') hides part of connector w->q" in m for m in messages)
    assert any("label 'Orders' (of block 'db') and label 'writes' (of connector 'q->db') overlap" in m for m in messages)
    clean = frame([label("Web", "block", "web", [100, 60, 160, 90]), label("Top", "block", "t", [210, 160, 240, 180], on_top=True)],
                  {"web": box(100, 100, 160, 160), "t": box(200, 150, 260, 200)})
    assert list(RULES["iso_labels"].check(clean, IsoLabelsRule())) == []


# ----- placement (no render) -----------------------------------------------------------------------


def plan(make_project, scene: dict[str, Any], size: tuple[int, int]) -> Any:
    project = project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": scene, "beats": beats(None)}])
    fw, fh = frame_size(*size)
    with tempconfig({"pixel_width": size[0], "pixel_height": size[1], "frame_width": fw, "frame_height": fh}):
        spec = project.scene("s")
        made = registry.get("iso_diagram").cls(spec, project, extensions.activate(project))
        return made, made.plan_diagram()[2]


GROUPS = {
    "heading": "Services in groups",
    "blocks": [{"id": "lb", "label": "Load balancer", "at": [0, 1], "shape": "tile", "size": [1, 2]},
               {"id": "web1", "label": "Web 1", "at": [2, 0]}, {"id": "web2", "label": "Web 2", "at": [2, 2]},
               {"id": "queue", "label": "Queue", "at": [4, 1], "shape": "slab", "size": [1, 1]},
               {"id": "db", "label": "Orders", "at": [6, 1], "shape": "database"}],
    "groups": [{"id": "web", "label": "Web tier", "blocks": ["web1", "web2"], "color": "primary"}],
    "edges": ["lb -> web1", "lb -> web2", {"from": "web1", "to": "queue", "style": "pipe"}, {"from": "web2", "to": "queue", "style": "pipe"},
              "queue --> db: writes"],
}


@pytest.mark.parametrize("size", [(854, 480), (480, 854)])
def test_labels_keep_off_other_blocks_and_each_other(make_project, size: tuple[int, int]) -> None:
    scene, made = plan(make_project, GROUPS, size)
    placed = made.placement
    rects = {lab.key: rect_of(placed.centres[k], (lab.extent[0] + 0.32, lab.extent[1] + 0.16)) for k, lab in enumerate(made.labels)}
    hulls = {n: h * made.scale for n, h in scene._hulls.items()}
    for key, rect in rects.items():
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        for name, hull in hulls.items():
            if name != key[1]:
                assert clip_area(rect, hull) / area < 0.1, (key, name)
    caption = rects[("group", "web")]
    assert all(clip_area(caption, hulls[m]) == 0 for m in ("web1", "web2"))   # the caption by the plate, not among its blocks
    keys = list(rects)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            r, s = rects[a], rects[b]
            assert min(r[2], s[2]) - max(r[0], s[0]) <= 0 or min(r[3], s[3]) - max(r[1], s[1]) <= 0, (a, b)


def test_a_stack_in_9x16_lists_its_layers_under_it_and_fills_the_frame(make_project) -> None:
    stack = {"heading": "A layered web app", "blocks": [{"id": "app", "label": "One server", "layers": ["Database", "Services", "API", "Web UI"]}]}
    tall, made = plan(make_project, stack, (480, 854))
    wide, flat = plan(make_project, stack, (854, 480))
    assert len(made.placement.swatches) == 4 and not made.placement.leaders     # listed under it, with swatches
    assert not flat.placement.swatches and len(flat.placement.leaders) == 4     # at its side in 16:9
    assert made.scale > 2.0 * 0.93   # Step 173 drew it 0.93 units a tile in 9:16
    centres = [made.placement.centres[k] for k in made.placement.swatches]
    assert [round(c[1], 3) for c in centres] == sorted((round(c[1], 3) for c in centres), reverse=True)


# ----- renders ------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


def scene_with(make_project, actions: list[list[dict[str, Any]] | None], **params: Any) -> Any:
    return project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": {**SCENE, **params}, "beats": beats(*actions)}])


def bottom(mob: Any) -> float:
    return float(mob.get_bottom()[1])


@pytest.mark.render
def test_raise_lower_explode_and_collapse_move_blocks_and_their_labels(make_project, media: Path) -> None:
    scene = render(scene_with(make_project, [None, [{"raise": "block:web", "by": 1.0}, {"explode": "stack:app", "gap": 0.8}],
                                             [{"lower": "block:web"}, {"collapse": "stack:app"}]]), "s", media, size=(160, 90))
    assert scene._lifted["web"] == 0.0 and scene._lifted["api"] == 0.0                 # all back down in the end
    assert scene._own["web"] == 0.0 and scene._gaps["app"] == pytest.approx(scene.diagram_layout.stacks["app"].gap)
    assert "web" in scene._shadows                                                    # a raised block casts a shadow
    lifted = render(scene_with(make_project, [None, [{"raise": "block:web", "by": 1.0}, {"explode": "stack:app", "gap": 0.8}]]), "s", media, size=(160, 90))
    rise = ISO_UP * lifted._unit
    assert bottom(lifted._parts["blocks"]["web"]) - bottom(scene._parts["blocks"]["web"]) == pytest.approx(1.0 * rise, rel=1e-3)
    gap = 0.8 - scene.diagram_layout.stacks["app"].gap
    assert bottom(lifted._parts["blocks"]["api"]) - bottom(scene._parts["blocks"]["api"]) == pytest.approx(gap * rise, rel=1e-3)
    assert lifted._shadows["web"].get_fill_opacity() > 0


ISO_UP = math.sqrt(1.5) / 2


@pytest.mark.render
def test_build_waits_for_its_action_and_grows(make_project, media: Path) -> None:
    scene = render(scene_with(make_project, [None, [{"build": "stack:app", "style": "grow"}]], entrance="grow"), "s", media, size=(160, 90))
    assert ("block", "api") in scene._in and ("edge", 1) in scene._in             # the pipe to it came in with it
    first = render(scene_with(make_project, [[{"build": "block:db"}], None], build="each"), "s", media, size=(160, 90))
    assert all(first.is_shown(t) for t in first.targets)


@pytest.mark.render
def test_flow_relabel_focus_and_solid_recolouring(make_project, media: Path) -> None:
    acts = [{"flow": "edge:*", "chain": True}, {"flow": "edge:db->app", "style": "packets"}, {"relabel": "block:db", "text": "Data 2"},
            {"focus": "group:g"}, {"highlight": "block:web"}, {"dim": "block:db"}]
    scene = render(scene_with(make_project, [None, acts]), "s", media, size=(160, 90))
    assert scene._label_text[("block", "db")].lines_text.original_text == "Data 2"
    assert scene.camera.frame.width < scene.frame_width - 1e-3                      # focused on the group
    web = scene._parts["blocks"]["web"]
    fills = {tuple(np.round(m.fill_rgbas[0, :3], 3)) for m in web.family_members_with_points() if m.fill_rgbas[0, 3] > 0}
    assert len(fills) >= 2                                                           # highlighted with its shading kept
    db = scene._parts["blocks"]["db"]
    assert all(m.fill_rgbas[0, 3] > 0.99 for m in db.family_members_with_points() if m.fill_rgbas[0, 3] > 0)   # dimmed, still opaque
    assert not any(type(sub).__name__ == "Circle" for m in scene.mobjects for sub in m.get_family())   # the flow's dots are gone
    keys = scene.layout_keys(None)["iso_diagram"]
    assert {lab["owner"] for lab in keys["labels"]} >= {"web", "db", "g"} and keys["blocks"] and keys["edges"]
