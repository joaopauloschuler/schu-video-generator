"""The ``iso_diagram`` scene (DESIGN.md §90.6): the layout on the grid (arrangements, stacks,
group plates, the floor), connectors along the grid, the shapes, the params' checks, and a
tiny render in 16:9 and 9:16."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from test_actions import beats, project_with, render
from vidgen import extensions, registry
from vidgen.cartoon.iso_drawing import Blobs, Disc, Line, Poly, Upright
from vidgen.iso_blocks import (
    CLEARANCE, FLOOR_PAD, PLATE_HEIGHT, BlockSpec, EdgeSpec, GroupSpec, ItemSpec, Rect, arrange, block_shapes, diagram_shapes,
    floor_shapes, hidden_run, layout_iso_diagram, readable_ink, route,
)
from vidgen.iso_vector import picture_to_scene, shape_mobject, shapes_mobject
from vidgen.render.worker import frame_size
from vidgen.world.iso_view import ISO_RISE


def box(name: str, at: tuple[float, float] | None = None, shape: str = "box", **kw: Any) -> ItemSpec:
    return ItemSpec(name, at, block=BlockSpec(name, shape, **kw))


def stack(name: str, layers: list[str], at: tuple[float, float] | None = None, **kw: Any) -> ItemSpec:
    return ItemSpec(name, at, layers=tuple(BlockSpec(n, "slab") for n in layers), **kw)


def params(**values: Any) -> Any:
    extensions.load_builtins()
    return registry.get("iso_diagram").cls.validate_params(values)


# ----- layout --------------------------------------------------------------------------------------


def test_arrangements_place_items_in_order() -> None:
    items = [box("a"), box("b"), ItemSpec("s", layers=(BlockSpec("l", "slab"),))]   # a stack is 2x2
    assert arrange(items, "row") == [(0.0, 0.5), (2.0, 0.5), (5.5, 0.0)]      # a stack keeps more room
    assert arrange(items, "column") == [(0.5, 0.0), (0.5, 2.0), (0.0, 5.5)]
    assert arrange(items, "grid", columns=2) == [(0.5, 0.0), (3.0, 0.0), (0.0, 2.0)]
    # zigzag: right, then down-left, right... (two columns down the picture)
    assert arrange([box("a"), box("b"), box("c"), box("d")], "zigzag", spacing=2) == [(0, 0), (3, 0), (3, 3), (6, 3)]


def test_blocks_fill_their_cells_less_the_inset_and_stacks_go_up() -> None:
    layout = layout_iso_diagram([box("a", (0, 0), height=1.5), stack("s", ["bottom", "top"], (3, 0), gap=0.2)])
    a = layout.blocks["a"].box
    assert (a.x0, a.y0, a.x1, a.y1, a.z0, a.z1) == pytest.approx((0.1, 0.1, 0.9, 0.9, 0.0, 1.5))
    bottom, top = layout.blocks["bottom"].box, layout.blocks["top"].box
    assert (bottom.z0, bottom.z1, top.z0, top.z1) == pytest.approx((0.0, 0.3, 0.5, 0.8))
    assert layout.blocks["top"].stack == "s" and layout.blocks["top"].level == 1
    assert layout.stacks["s"].layers == ("bottom", "top")


def test_a_cylinder_is_round_and_square() -> None:
    layout = layout_iso_diagram([box("db", (0, 0), "database", size=(2, 1))])
    b = layout.blocks["db"].box
    assert (b.x1 - b.x0, b.y1 - b.y0) == pytest.approx((0.8, 0.8))
    shapes = block_shapes(layout.blocks["db"], "#336699")
    assert isinstance(shapes[0], Upright) and [type(s) for s in shapes[1:]] == [Line, Line]   # a database's two bands
    assert len(block_shapes(layout_iso_diagram([box("c", (0, 0), "cylinder")]).blocks["c"], "#336699")) == 1
    plain = layout_iso_diagram([box("b", (0, 0))]).blocks["b"]
    assert all(isinstance(s, Poly) for s in block_shapes(plain, "#336699"))
    raised = block_shapes(plain, "#336699", lift=1.0)   # raised a cell (for Step 174's raise / lower)
    assert max(p[2] for s in raised for p in s.points) == pytest.approx(1.8)


def test_groups_lift_their_members_onto_a_plate() -> None:
    layout = layout_iso_diagram([box("a", (0, 0)), box("b", (2, 0)), box("c", (6, 0))], [GroupSpec("g", ("a", "b"))])
    assert layout.blocks["a"].box.z0 == PLATE_HEIGHT and layout.blocks["c"].box.z0 == 0.0
    plate = layout.plates["g"]
    assert (plate.x0, plate.x1, plate.z1) == pytest.approx((-0.2, 3.2, PLATE_HEIGHT))
    assert layout.ground("a") == PLATE_HEIGHT and layout.ground("c") == 0.0


@pytest.mark.parametrize(("items", "groups", "edges", "message"), [
    ([box("a", (0, 0)), box("b", (0.5, 0))], [], [], "'a' and 'b' overlap on the grid"),
    ([box("a", (0, 0)), box("b")], [], [], r"some blocks and stacks have 'at' and some do not \(without one: b\)"),
    ([box("a", (0, 0)), box("b", (1, 0))], [GroupSpec("g", ("a",))], [], "'b' stands where group 'g''s plate lies"),
    ([box("a", (0, 0))], [GroupSpec("g", ("a",)), GroupSpec("h", ("a",))], [], "'a' is in two groups"),
    ([box("a", (0, 0))], [GroupSpec("g", ("x",))], [], "'x' is not a block or stack of the diagram"),
    ([box("a", (0, 0)), box("b", (1.2, 0))], [GroupSpec("g", ("a",)), GroupSpec("h", ("b",))], [], "the plates of groups 'g' and 'h' overlap"),
    ([stack("s", ["x", "y"], (0, 0))], [], [EdgeSpec("x", "y")], "both are in one stack"),
])
def test_layouts_that_make_no_sense_are_refused(items: list[ItemSpec], groups: list[GroupSpec], edges: list[EdgeSpec], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        layout_iso_diagram(items, groups, edges)


def test_the_floor_is_one_rectangle_unless_the_items_zigzag() -> None:
    row = layout_iso_diagram([box("a"), box("b"), box("c")])
    assert len(row.floor) == 1
    floor = row.floor[0]
    assert (floor.x0, floor.y0, floor.x1, floor.y1) == pytest.approx((0.1 - FLOOR_PAD, 0.1 - FLOOR_PAD, 4.9 + FLOOR_PAD, 0.9 + FLOOR_PAD))
    zig = layout_iso_diagram([box("a"), box("b"), box("c"), box("d")], edges=[EdgeSpec("a", "b"), EdgeSpec("b", "c"), EdgeSpec("c", "d")],
                             how="zigzag", spacing=2)
    # Step 176: whole cells of a grid half a cell off (its edges mid-cell all round), no notches
    assert all((v - 0.5) == pytest.approx(round(v - 0.5)) for r in zig.floor for v in (r.x0, r.y0, r.x1, r.y1))
    for item in zig.items.values():
        grown = item.grown(FLOOR_PAD)
        for x, y in ((grown.x0, grown.y0), (grown.x1, grown.y0), (grown.x0, grown.y1), (grown.x1, grown.y1)):
            assert any(r.x0 <= x <= r.x1 and r.y0 <= y <= r.y1 for r in zig.floor)
    assert [(r.x0, r.x1) for r in zig.floor] == [(-0.5, 4.5), (-0.5, 4.5), (2.5, 4.5), (2.5, 7.5), (2.5, 7.5)]   # a staircase
    shapes = floor_shapes(zig.floor, "#202020", "#303030")
    polys = [s for s in shapes if isinstance(s, Poly)]
    assert len(polys) == 1 and len(polys[0].points) > 4   # one stepped outline, not four squares
    assert all(isinstance(s, Line) for s in shapes[1:])


# ----- connectors ----------------------------------------------------------------------------------


def test_facing_blocks_get_a_straight_connector_with_its_tip_in_view() -> None:
    a, b = Rect(0.1, 0.1, 0.9, 0.9), Rect(2.1, 0.1, 2.9, 0.9)
    path = route(a, b, heights=(0.8, 0.8))
    # b's side at x0 is a back side: the floor before it is hidden for half the block's depth
    assert path == [pytest.approx((0.9 + CLEARANCE, 0.5)), pytest.approx((2.1 - CLEARANCE - 0.4, 0.5))]
    back = route(b, a, heights=(0.8, 0.8))   # leaving b's back side the start is hidden; a's front side shows
    assert back == [pytest.approx((2.1 - CLEARANCE - 0.4, 0.5)), pytest.approx((0.9 + CLEARANCE, 0.5))]
    flat = route(a, b, heights=(0.1, 0.1))   # a flat tile hides little of the floor behind it
    assert flat[1][0] == pytest.approx(2.1 - CLEARANCE - 2 * 0.1 * ISO_RISE)


def test_hidden_run_of_boxes_and_cylinders() -> None:
    rect = Rect(0, 0, 2, 2)
    assert hidden_run(rect, 5, (-1, 0), (0, 1)) == pytest.approx(1.0)        # half the depth, from the middle
    assert hidden_run(rect, 5, (0, -1), (1.5, 0)) == pytest.approx(0.5)
    assert hidden_run(rect, 5, (1, 0), (2, 1)) == 0.0                        # a front side hides nothing
    assert hidden_run(rect, 5, (-1, 0), (0, 1), round_end=True) == pytest.approx(math.sqrt(2) - 1)


def test_a_connector_turns_once_or_goes_round_the_front_of_what_is_in_its_way() -> None:
    a, b = Rect(0.1, 0.1, 0.9, 0.9), Rect(2.1, 2.1, 2.9, 2.9)
    path = route(a, b)
    assert len(path) == 3 and path[1] == pytest.approx((2.5, 0.5))           # along x first
    blocked = route(a, b, [Rect(1.5, 0.0, 2.5, 1.0)])                         # something on the x-first way
    assert blocked[1] == pytest.approx((0.5, 2.5))
    far = Rect(6.1, 0.1, 6.9, 0.9)
    detour = route(a, far, [Rect(3.1, 0.1, 3.9, 0.9)])
    assert len(detour) == 4 and detour[1][1] == pytest.approx(0.9 + 0.5)    # round the front, out of the way
    assert route(a, far)[0][1] == pytest.approx(0.5)                         # nothing in the way: straight


def test_two_connectors_between_the_same_blocks_run_side_by_side() -> None:
    layout = layout_iso_diagram([box("a"), box("b")], edges=[EdgeSpec("a", "b"), EdgeSpec("b", "a")])
    ys = [edge.points[0][1] for edge in layout.edges]
    assert ys[0] != pytest.approx(ys[1])


def test_connectors_and_pipes_become_shapes() -> None:
    layout = layout_iso_diagram([box("a"), box("b"), box("c")], edges=[EdgeSpec("a", "b", "dashed"), EdgeSpec("b", "c", "pipe")])
    shapes = diagram_shapes(layout, {"a": "#111111", "b": "#222222", "c": "#333333"}, ["#999999", "#888888"], {},
                            floor="grid", background="#000000", text="#FFFFFF")
    assert list(shapes.arrows) == [0] and len(shapes.arrows[0]) >= 3         # dashes and a head
    assert {k for k, _ in shapes.pipes} == {1}
    kinds = [kind for kind, _ in layout.order()]
    assert kinds.count("block") == 3 and kinds.count("pipe") == len(shapes.pipes)
    left, top, right, bottom = shapes.bounds()
    assert left < 0 < right and top < 0 < bottom
    plain = diagram_shapes(layout, {"a": "#111111", "b": "#222222", "c": "#333333"}, ["#999999", "#888888"], {},
                           floor="plain", background="#000000", text="#FFFFFF")
    assert all(isinstance(s, Poly) for s in plain.floor)
    none = diagram_shapes(layout, {"a": "#111111", "b": "#222222", "c": "#333333"}, ["#999999", "#888888"], {},
                          floor="none", background="#000000", text="#FFFFFF")
    assert none.floor == []


def test_every_iso_shape_becomes_a_mobject() -> None:
    to_scene = picture_to_scene(2.0, (1.0, -1.0))
    assert list(to_scene(0.5, 0.25)) == pytest.approx([2.0, -1.5, 0.0])
    poly = shape_mobject(Poly(((0, 0, 0), (1, 0, 0), (1, 1, 0)), "#336699"), to_scene, ink="#000000")
    assert poly.get_stroke_width() == 2.0 and poly.get_fill_opacity() == 1.0
    assert shape_mobject(Poly(((0, 0, 0), (1, 0, 0), (1, 1, 0)), "#336699", False), to_scene, ink="#000000").get_stroke_width() == 0
    assert len(shape_mobject(Upright(0, 0, 0, 1, 0.4, "#336699"), to_scene, ink="#000000")) == 4   # body, shade, sides, top
    assert len(shape_mobject(Upright(0, 0, 0, 1, 0.4, "#336699"), to_scene, ink=None)) == 3
    assert shape_mobject(Line(((0, 0, 0), (1, 0, 0)), "#FF0000", 2.0), to_scene, ink=None).get_stroke_width() == 4.0
    assert shape_mobject(Disc((0, 0, 0), 0.5, "#000000", opacity=0.3), to_scene, ink=None).get_fill_opacity() == pytest.approx(0.3)
    assert len(shape_mobject(Blobs(((0, 0, 1), (0.3, 0, 1)), (0.3, 0.2), "#00AA00"), to_scene, ink="#000000")) == 2
    assert len(shapes_mobject(block_shapes(layout_iso_diagram([box("b")]).blocks["b"], "#336699"), to_scene, ink=None)) == 3


def test_readable_ink() -> None:
    assert readable_ink("#F2A541", "#0F1115", "#E8EAED") == "#0F1115"
    assert readable_ink("#1D4ED8", "#0F1115", "#E8EAED") == "#E8EAED"


# ----- params --------------------------------------------------------------------------------------


def test_params_shorthands_targets_and_arrangements() -> None:
    p = params(heading="H", blocks=["web", {"id": "db", "label": "Data", "shape": "database"}, {"id": "app", "layers": ["ui", "api"]}],
               groups=[{"id": "g", "blocks": ["web", "db"]}], edges=["web -> db: reads", "db --> app"])
    assert [b.text() for b in p.blocks] == ["web", "Data", "app"]
    assert [(e.source, e.to, e.style, e.label) for e in p.edges] == [("web", "db", None, "reads"), ("db", "app", "dashed", "")]
    assert registry.get("iso_diagram").cls.target_names(p) == [
        "heading", "diagram", "block1", "block:web", "block2", "block:db", "block3", "block:ui", "block4", "block:api",
        "stack:app", "group:g", "edge:web->db", "edge:db->app"]
    assert p.layout().edges[0].style == "solid" and p.layout().edges[1].style == "dashed"
    assert p.layout().stacks["app"].rect.x0 == pytest.approx(5.6)               # in a row (16:9)
    assert p.layout(portrait=True).blocks["db"].box.x0 == pytest.approx(4.6)    # a zigzag 2 cells apart (9:16)
    assert params(blocks=["a"], edge_style="pipe", edges=[]).edge_style == "pipe"
    chained = params(blocks=["a", "b", "c"], edges=["a -> b -> c"])
    assert [e.ref() for e in chained.edges] == ["a->b", "b->c"]
    ordered = params(blocks=["web", {"id": "app", "color": "accent", "layers": ["ui", {"id": "api", "color": "primary"}]}, "db"])
    assert ordered.all_blocks() == [("web", "web", None, None), ("ui", "ui", "accent", "app"), ("api", "api", "primary", "app"), ("db", "db", None, None)]
    layout = ordered.layout()
    assert layout.blocks["web"].box.x1 < layout.stacks["app"].rect.x0 < layout.blocks["db"].box.x0   # in the order written


@pytest.mark.parametrize(("values", "message"), [
    ({"blocks": []}, "at least 1 item"),
    ({"blocks": ["a", "a"]}, "the id 'a' is used twice"),
    ({"blocks": ["a", {"id": "s", "layers": ["a"]}]}, "the id 'a' is used twice"),
    ({"blocks": [{"id": "s", "layers": ["a"], "shape": "box"}]}, "it is a stack: give shape to its layers instead"),
    ({"blocks": [{"id": "s", "gap": 0.3}]}, "gap are for a stack"),
    ({"blocks": ["api"], "edges": ["api -> apl"]}, "unknown block 'apl'; did you mean 'api'"),
    ({"blocks": ["a", "b"], "edges": ["a -> b", "a -> b"]}, "is listed twice"),
    ({"blocks": ["a"], "edges": ["a -> a"]}, "points to itself"),
    ({"blocks": ["a", {"id": "s", "layers": ["x"]}], "groups": [{"id": "g", "blocks": ["x"]}]}, "'x' is a layer of a stack; list the stack instead"),
    ({"blocks": [{"id": "a", "at": [0, 0]}, {"id": "b", "at": [0, 0]}]}, "'a' and 'b' overlap"),
    ({"blocks": [{"id": "a", "size": [0.2, 1]}]}, "each number must be 0.5 to 40 cells"),
    ({"blocks": [{"id": "a", "shape": "sphere"}]}, "box"),
    ({"blocks": ["a -> b"]}, "use letters, digits"),
])
def test_params_problems(values: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception, match=message):
        params(**values)


# ----- rendering -----------------------------------------------------------------------------------

SCENE = {
    "heading": "Flow",
    "blocks": [{"id": "web", "label": "Web"}, {"id": "db", "label": "Data", "shape": "database"},
               {"id": "app", "label": "App", "layers": ["UI", {"id": "api", "label": "API", "shape": "box"}]}],
    "groups": [{"id": "g", "label": "Back end", "blocks": ["db", "app"]}],
    "edges": ["web -> db: SQL", {"from": "db", "to": "app", "style": "pipe"}],
}


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)])
def test_renders_every_target_inside_the_frame(make_project, media: Path, size: tuple[int, int]) -> None:
    project = project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": SCENE, "beats": beats(None)}])
    scene = render(project, "s", media, size=size)
    assert sorted({n for t in scene.targets for n in t.names}) == sorted(type(scene).target_names(scene.params))
    assert all(scene.is_shown(t) for t in scene.targets)
    half_w, half_h = (v / 2 for v in frame_size(*size))
    for target in scene.targets:
        mob = target.mobject
        assert -half_w - 1e-6 <= mob.get_left()[0] and mob.get_right()[0] <= half_w + 1e-6, target.name
        assert -half_h - 1e-6 <= mob.get_bottom()[1] and mob.get_top()[1] <= half_h + 1e-6, target.name
    if size[1] > size[0]:   # 9:16: the blocks zigzag down the frame
        assert scene.diagram_layout.blocks["db"].box.x0 > scene.diagram_layout.blocks["web"].box.x1
