"""Step 28 graph layout (``vidgen.graph``, exported by ``vidgen.api``): layered placement of
directed graphs on known graphs — trees without crossings, cycles, long edges, both
directions, ports on the node outlines, orthogonal routes, label room, determinism."""

from __future__ import annotations

import itertools
import math

import pytest

from vidgen import api
from vidgen.errors import VidgenError
from vidgen.graph import GraphEdge, GraphNode, layered_layout

TREE = [("a", "b"), ("a", "c"), ("b", "d"), ("b", "e"), ("c", "f"), ("c", "g")]


def boxes(ids: str, w: float = 1.0, h: float = 0.5, shape: str = "box") -> list[GraphNode]:
    return [GraphNode(i, w, h, shape) for i in ids]  # type: ignore[arg-type]


def overlap(a: api.NodePlace, b: api.NodePlace, gap: float = 0.0) -> bool:
    return abs(a.x - b.x) < (a.width + b.width) / 2 + gap - 1e-9 and abs(a.y - b.y) < (a.height + b.height) / 2 + gap - 1e-9


def segments(points: tuple[tuple[float, float], ...]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return list(zip(points, points[1:]))


def crosses(p: tuple[tuple[float, float], tuple[float, float]], q: tuple[tuple[float, float], tuple[float, float]]) -> bool:
    """Proper intersection of two segments (touching ends do not count)."""

    def side(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    (a, b), (c, d) = p, q
    return side(a, b, c) * side(a, b, d) < -1e-9 and side(c, d, a) * side(c, d, b) < -1e-9


def test_exported_by_the_api() -> None:
    for name in ("layered_layout", "GraphLayout", "GraphNode", "GraphEdge", "EdgeRoute", "NodePlace"):
        assert name in api.__all__ and getattr(api, name) is not None


def test_a_tree_has_no_crossings_and_parents_centred_on_their_children() -> None:
    layout = layered_layout(boxes("abcdefg"), TREE)
    assert layout.crossings == 0 and layout.reversed_edges == []
    assert layout.layers == [["a"], ["b", "c"], ["d", "e", "f", "g"]]
    n = layout.nodes
    assert n["a"].x < n["b"].x == n["c"].x < n["d"].x   # LR: layers left to right
    assert n["b"].y > n["c"].y   # first in order on top
    assert n["b"].y == pytest.approx((n["d"].y + n["e"].y) / 2, abs=1e-6)
    assert n["a"].y == pytest.approx((n["b"].y + n["c"].y) / 2, abs=1e-6)
    for p, q in itertools.combinations(layout.edges, 2):   # drawn, no two edges cross either
        assert not any(crosses(s, t) for s in segments(p.points) for t in segments(q.points))


@pytest.mark.parametrize("seed_order", [list("hgfedcba"), list("aebfcgdh")])
def test_barycenter_sweeps_untangle_a_crossed_input(seed_order: list[str]) -> None:
    edges = [("a", "f"), ("a", "g"), ("b", "e"), ("c", "h"), ("d", "e"), ("b", "f")]
    layout = layered_layout(seed_order, edges)
    assert layout.crossings == 0


def test_unavoidable_crossings_are_counted() -> None:
    layout = layered_layout(list("abcdef"), [(u, v) for u in "abc" for v in "def"])   # K3,3
    assert layout.crossings == 9   # every two edges from different sources to different targets cross


def test_layout_is_centred_and_nodes_keep_their_gap() -> None:
    layout = layered_layout(boxes("abcdefg", 1.2, 0.6), TREE, node_gap=0.4, layer_gap=0.8)
    xs = [v for p in layout.nodes.values() for v in (p.x - p.width / 2, p.x + p.width / 2)]
    ys = [v for p in layout.nodes.values() for v in (p.y - p.height / 2, p.y + p.height / 2)]
    assert min(xs) == pytest.approx(-max(xs), abs=1e-6) and min(ys) == pytest.approx(-max(ys), abs=1e-6)
    assert layout.width == pytest.approx(3 * 1.2 + 2 * 0.8) and layout.height == pytest.approx(4 * 0.6 + 3 * 0.4)
    for p, q in itertools.combinations(layout.nodes.values(), 2):
        assert not overlap(p, q, 0.39)


def test_top_to_bottom_direction() -> None:
    layout = layered_layout(boxes("abcdefg"), TREE, direction="TB")
    n = layout.nodes
    assert n["a"].y > n["b"].y == n["c"].y > n["d"].y
    assert n["b"].x < n["c"].x   # first in order on the left
    a_b = layout.edges[0]
    assert a_b.points[0] == pytest.approx((a_b.points[0][0], n["a"].y - 0.25))   # leaves a's bottom
    assert a_b.points[-1][1] == pytest.approx(n["b"].y + 0.25)                    # enters b's top


def test_routes_start_and_end_on_box_outlines_with_spread_ports() -> None:
    layout = layered_layout(boxes("abcdefg"), TREE)
    n = layout.nodes
    out = [e for e in layout.edges if e.source == "a"]
    assert [e.points[0][0] for e in out] == pytest.approx([n["a"].x + 0.5] * 2)
    assert out[0].points[0][1] > n["a"].y > out[1].points[0][1]   # two ports, the upper edge on top
    for e in layout.edges:
        assert e.points[-1][0] == pytest.approx(n[e.target].x - 0.5)


@pytest.mark.parametrize("shape", ["ellipse", "diamond", "stadium"])
def test_ports_are_clipped_to_the_shape(shape: str) -> None:
    nodes = [GraphNode("a", 2.0, 1.0, shape), *boxes("bc")]  # type: ignore[arg-type]
    layout = layered_layout(nodes, [("a", "b"), ("a", "c")], port_spacing=0.4)
    a = layout.nodes["a"]
    for e in layout.edges:
        x, y = e.points[0]
        dx, dy = (x - a.x) / 1.0, (y - a.y) / 0.5
        if shape == "ellipse":
            assert dx * dx + dy * dy == pytest.approx(1.0, abs=1e-6)
        elif shape == "diamond":
            assert abs(dx) + abs(dy) == pytest.approx(1.0, abs=1e-6)
        else:   # a pill: semicircle ends of radius 0.5
            assert (x - (a.x + 0.5)) ** 2 + (y - a.y) ** 2 == pytest.approx(0.25, abs=1e-6)


def test_cycles_are_broken_by_reversing_back_edges() -> None:
    edges = [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")]
    layout = layered_layout(boxes("abcd"), edges)
    assert layout.reversed_edges == [2]
    back = layout.edges[2]
    assert back.reversed and (back.source, back.target) == ("c", "a")
    n = layout.nodes
    assert n["a"].x < n["b"].x < n["c"].x
    assert back.points[0][0] == pytest.approx(n["c"].x - 0.5)   # leaves c on the side facing a
    assert back.points[-1][0] == pytest.approx(n["a"].x + 0.5)  # and enters a from the far side
    assert len(back.points) == 3   # through a dummy in b's layer
    assert not overlap(layout.nodes["b"], api.NodePlace(back.points[1][0], back.points[1][1], 0, 0, 0, 0))


def test_long_edges_pass_between_the_nodes_of_the_layers_they_skip() -> None:
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("a", "d")]
    layout = layered_layout(boxes("abcd"), edges)
    long = layout.edges[3]
    assert len(long.points) == 4   # start, two dummies, end
    for x, y in long.points[1:-1]:
        assert all(not overlap(p, api.NodePlace(x, y, 0.0, 0.0, 0, 0), 0.1) for p in layout.nodes.values())


def test_sources_sit_just_before_their_successor() -> None:
    layout = layered_layout(boxes("abcdx"), [("a", "b"), ("b", "c"), ("c", "d"), ("x", "d")])
    assert layout.nodes["x"].layer == layout.nodes["c"].layer == 2


def test_orthogonal_routes_use_right_angles_and_their_own_channels() -> None:
    layout = layered_layout(boxes("abcdefg"), TREE, routing="orthogonal")
    for e in layout.edges:
        for (x0, y0), (x1, y1) in segments(e.points):
            assert abs(x0 - x1) < 1e-9 or abs(y0 - y1) < 1e-9
    verticals = {round(p[0], 6) for e in layout.edges for p, q in segments(e.points) if abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) > 1e-9}
    assert len(verticals) >= 2


def test_label_room_is_reserved_in_the_gap_and_anchored_on_the_route() -> None:
    plain = layered_layout(boxes("ab"), [("a", "b")], layer_gap=0.5)
    labelled = layered_layout(boxes("ab"), [GraphEdge("a", "b", (2.0, 0.3))], layer_gap=0.5, label_margin=0.1)
    assert plain.edges[0].label_at is None
    assert labelled.width == pytest.approx(plain.width - 0.5 + 2.2)
    x, y = labelled.edges[0].label_at  # type: ignore[misc]
    a, b = labelled.nodes["a"], labelled.nodes["b"]
    assert x == pytest.approx((a.x + 0.5 + b.x - 0.5) / 2) and y == pytest.approx(a.y)
    tall = layered_layout(boxes("ab"), [GraphEdge("a", "b", (2.0, 0.3))], direction="TB", layer_gap=0.5, label_margin=0.1)
    assert tall.height == pytest.approx(0.5 + 0.5 + 0.5)   # 0.3 + 2 x 0.1 fits the 0.5 gap


def test_isolated_nodes_and_no_edges() -> None:
    layout = layered_layout(["solo"], [])
    assert layout.layers == [["solo"]] and layout.edges == [] and (layout.width, layout.height) == (0.0, 0.0)
    layout = layered_layout(boxes("abc"), [("a", "b")])
    assert layout.nodes["c"].layer == 0 and layout.crossings == 0


def test_deterministic() -> None:
    edges = [("a", "c"), ("b", "c"), ("c", "d"), ("d", "a"), ("b", "e"), ("e", "d"), ("a", "e")]
    first = layered_layout(boxes("abcde"), edges, routing="orthogonal")
    assert all(layered_layout(boxes("abcde"), edges, routing="orthogonal") == first for _ in range(3))


@pytest.mark.parametrize(
    ("nodes", "edges", "kwargs", "message"),
    [
        (["a", "a"], [], {}, "node 'a' is listed twice"),
        (["a"], [("a", "b")], {}, "unknown node 'b'"),
        (["a"], [("a", "a")], {}, "cannot point to itself"),
        (["a"], [], {"direction": "RL"}, "unknown direction 'RL'"),
        (["a"], [], {"routing": "curvy"}, "unknown routing 'curvy'"),
        ([GraphNode("a", 1, 1, "star")], [], {}, "unknown shape 'star'"),  # type: ignore[arg-type]
    ],
)
def test_errors(nodes: list, edges: list, kwargs: dict, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        layered_layout(nodes, edges, **kwargs)


def test_a_larger_graph_is_quick_and_clean() -> None:
    ids = [f"n{i}" for i in range(30)]
    edges = [(ids[i], ids[j]) for i in range(30) for j in (2 * i + 1, 2 * i + 2) if j < 30]   # a binary tree
    edges += [(ids[i], ids[i + 3]) for i in range(0, 27, 5)]
    layout = layered_layout(boxes_named(ids), edges)
    for p, q in itertools.combinations(layout.nodes.values(), 2):
        assert not overlap(p, q)
    assert all(math.isfinite(v) for e in layout.edges for pt in e.points for v in pt)


def boxes_named(ids: list[str]) -> list[GraphNode]:
    return [GraphNode(i, 0.8, 0.4) for i in ids]
