"""Step 176: the review of Phase R (DESIGN.md §90.13). The iso diagram fills the body (labels
beside the blocks when those above and below take a wide body's height; in 9:16 the grid as
written or slanted, whichever is drawn larger), a focus fades out the labels its view would cut and
brings them back, connectors tilt up to raised blocks, the floor comes in with what stands on it
and has no ragged edge, and ripples stay inside their puddles."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from test_actions import beats, project_with, render
from test_iso_diagram_actions import SCENE, params, plan
from vidgen.cartoon.iso_drawing import Poly
from vidgen.cartoon.iso_weather import IsoPuddle, ripples
from vidgen.iso_blocks import BlockSpec, EdgeSpec, FloorCells, ItemSpec, arrow_shapes, layout_iso_diagram, ramped, slant
from vidgen.regions import Region

WEB = {   # the example's trip, shortened
    "heading": "The trip of one request",
    "blocks": [{"id": "browser", "label": "Browser", "at": [0, 1]}, {"id": "dns", "label": "DNS", "at": [0, 3], "shape": "slab", "size": [1, 1]},
               {"id": "lb", "label": "Load balancer", "at": [3, 0], "shape": "tile", "size": [1, 3]},
               {"id": "app1", "label": "App 1", "at": [5, 0]}, {"id": "app2", "label": "App 2", "at": [5, 2]},
               {"id": "cache", "label": "Cache", "at": [7, 1], "shape": "cylinder"}, {"id": "db", "label": "Database", "at": [9, 1], "shape": "database"}],
    "groups": [{"id": "apps", "blocks": ["app1", "app2"]}],
    "edges": ["browser --> dns", "browser -> lb: HTTPS", "lb -> app1", "lb -> app2", "app1 -> cache", "app2 -> cache",
              {"from": "cache", "to": "db", "style": "pipe"}],
}


# ----- the fit ---------------------------------------------------------------------------------------


def test_labels_go_beside_the_blocks_when_above_and_below_overflow_a_wide_body() -> None:
    from vidgen.scenes.iso_diagram import IsoDiagram, _Placement

    def place(scale: float, labels: list, sideways: bool = False) -> _Placement:
        height = 1.0 * scale if sideways else 1.6 * scale    # labels above and below take height
        return _Placement(bounds=(0.0, 0.0, 2.0 * scale, height))

    stub = SimpleNamespace(max_tile=2.4, portrait_tile=1.35, is_portrait=False, _place=place, _bounds=(0.0, 0.0, 1.0, 0.5))
    plan_ = IsoDiagram._largest(stub, Region(0.0, 0.0, 8.0, 2.0), [])   # type: ignore[arg-type]
    assert plan_.fits and plan_.scale == pytest.approx(2.0 / 1.2)    # the cap; 1.25 with the labels above and below


def test_the_example_grid_fills_a_wide_body(make_project) -> None:
    _scene, made = plan(make_project, WEB, (854, 480))
    assert made.fits and made.scale > 1.25       # Step 175: 1.01 (the labels above and below set the height)


def test_a_tall_frame_draws_the_grid_as_written_or_slanted_whichever_is_larger(make_project) -> None:
    p = params(**WEB)
    assert len(p.layouts(portrait=False)) == 1
    tall = p.layouts(portrait=True)
    assert len(tall) >= 3 and tall[0].items == p.layout(portrait=True).items
    scene, made = plan(make_project, WEB, (480, 854))
    assert made.fits and made.scale > 1.15        # Step 175: 1.08
    half = slant([ItemSpec("a", (0, 0), block=BlockSpec("a")), ItemSpec("b", (3, 0), block=BlockSpec("b"))], "x", 0.5)
    assert [i.at for i in half] == [(0, 0), (3, 2.0)]   # half the way, in whole cells (1.5 rounds to 2)


# ----- floor -----------------------------------------------------------------------------------------


def test_the_floor_comes_in_with_what_stands_on_it() -> None:
    layout = layout_iso_diagram([ItemSpec(n, (3 * k, 0), block=BlockSpec(n)) for k, n in enumerate("abc")],
                                edges=[EdgeSpec("a", "b"), EdgeSpec("b", "c")])
    cells = FloorCells(layout)
    first, two, every = cells.under({"a"}), cells.under({"a", "b"}), cells.under({"a", "b", "c"})
    assert first and first < two < every == cells.cells and not cells.under(set())
    shapes = cells.shapes(sorted(two - first), first, floor="grid", background="#101010", text="#ffffff")
    polys = [s for s in shapes if isinstance(s, Poly)]
    xs = [p[0] for s in polys for p in s.points]
    edge = max(cells.xs[i + 1] for i, _ in first)
    assert min(xs) < edge                       # it reaches a little under the piece shown already: no seam


# ----- connectors to raised blocks -------------------------------------------------------------------


def test_a_connector_tilts_up_to_its_raised_ends() -> None:
    layout = layout_iso_diagram([ItemSpec("a", (0, 0), block=BlockSpec("a")), ItemSpec("b", (3, 0), block=BlockSpec("b"))], edges=[EdgeSpec("a", "b")])
    edge = layout.edges[0]
    flat = arrow_shapes(edge, "#888888")
    assert ramped(flat, edge, 0.0, 0.0) == flat
    tilted = ramped(flat, edge, 0.0, 0.5)
    tip = tilted[-1].points[0]
    assert tip[2] == pytest.approx(edge.points[-1][2] + 0.5, abs=1e-6)          # the head reaches the raised block
    start = min((p for s in tilted for p in s.points), key=lambda p: p[0])
    assert start[2] == pytest.approx(edge.points[0][2], abs=0.02)               # the source end stays on the floor


# ----- puddles -----------------------------------------------------------------------------------------


def test_ripples_stay_inside_their_puddle() -> None:
    puddle = IsoPuddle(0.0, 0.0, 0.0, 0.4, 7)
    for t in np.linspace(0.0, 30.0, 301):
        for ring in ripples(puddle, float(t)):
            assert np.hypot(ring.dx, ring.dy) + ring.radius <= puddle.radius + 1e-9


# ----- renders -----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


def alpha(group) -> float:
    return max(float(np.max(m.fill_rgbas[:, 3])) for m in group.family_members_with_points())


@pytest.mark.render
def test_focus_fades_out_the_labels_it_would_cut_and_brings_them_back(make_project, media: Path) -> None:
    acts = [[{"focus": "block:db", "scale": 3}], [{"focus": "diagram"}]]
    focused = render(project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": SCENE, "beats": beats(acts[0])}]), "s", media, size=(160, 90))
    frame = focused.camera.frame
    left, right = frame.get_left()[0], frame.get_right()[0]
    texts = focused._parts["texts"]
    cut = [key for key, group in texts.items() if group.get_left()[0] < left or group.get_right()[0] > right]
    assert cut and all(alpha(texts[key]) < 1e-6 for key in cut)                  # never cut at the frame's edge
    assert alpha(texts[("block", "db")]) > 0.5
    back = render(project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": SCENE, "beats": beats(*acts)}]), "s", media, size=(160, 90))
    assert not back._veiled and all(alpha(group) > 0.5 for group in back._parts["texts"].values())


@pytest.mark.render
def test_raising_a_block_tilts_its_connectors_and_a_build_brings_the_floor_in_parts(make_project, media: Path) -> None:
    scenes = [{"id": "s", "type": "iso_diagram", "params": SCENE,
               "beats": beats([{"build": "block:web", "at": 0.5}], [{"raise": "block:web", "by": 0.6}])}]
    scene = render(project_with(make_project, scenes), "s", media, size=(160, 90))
    k = next(i for i, e in enumerate(scene.diagram_layout.edges) if e.source == "web")
    assert scene._edge_lift[k] == pytest.approx((0.6, 0.0))
    assert scene._floor_cells is not None and len(scene._parts["floor"].submobjects) >= 2   # the floor came in two parts
    assert scene._floor_shown == scene._floor_cells.cells
    whole = render(project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": SCENE, "beats": beats(None)}]), "s", media, size=(160, 90))
    assert whole._floor_cells is None                                                    # built at once: one floor, as before
