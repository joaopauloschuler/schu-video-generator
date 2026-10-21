"""Step 177: Phase R follow-ups (DESIGN.md §90.14). A raised block's label keeps off its tilted
connectors, pipes tilt up to raised ends (flows ride on them), lint judges a label's distance at
the diagram's own scale under a focus, and 9:16 shots on an iso place keep characters whole."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import tempconfig

from test_actions import beats, project_with, render
from test_iso_diagram_actions import box, frame, label
from vidgen import extensions, registry
from vidgen.cartoon.shots import Shot, ShotFigure, ShotView, frame_shot, portrait_shot
from vidgen.config import IsoLabelsRule
from vidgen.iso_labels import rect_of
from vidgen.lint import RULES
from vidgen.render.worker import frame_size
from vidgen.world.iso_view import ISO_RISE, iso_point

ONE_REQUEST = {   # the example's second diagram
    "heading": "Following one request",
    "blocks": [{"id": "browser", "label": "Browser", "at": [0, 1]},
               {"id": "lb", "label": "Load balancer", "at": [3, 0], "shape": "tile", "size": [1, 3]},
               {"id": "app1", "label": "App 1", "at": [5, 0], "height": 1.1}, {"id": "app2", "label": "App 2", "at": [5, 2], "height": 1.1},
               {"id": "cache", "label": "Cache", "at": [7, 1], "shape": "cylinder"},
               {"id": "db", "label": "Database", "at": [9, 1], "shape": "database", "height": 1.1}],
    "groups": [{"id": "apps", "blocks": ["app1", "app2"]}],
    "edges": ["browser -> lb: HTTPS", "lb -> app1", "lb -> app2", "app1 -> cache", "app2 -> cache", {"from": "cache", "to": "db", "style": "pipe"}],
}


def plan_with(make_project, scene: dict[str, Any], actions: list[dict[str, Any]], size: tuple[int, int]) -> Any:
    project = project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": scene, "beats": beats(actions)}])
    extensions.load_builtins()
    fw, fh = frame_size(*size)
    with tempconfig({"pixel_width": size[0], "pixel_height": size[1], "frame_width": fw, "frame_height": fh}):
        made = registry.get("iso_diagram").cls(project.scene("s"), project, extensions.activate(project))
        return made, made.plan_diagram()[2]


# ----- a raised block's label --------------------------------------------------------------------


def test_a_raised_blocks_label_keeps_off_its_tilted_connectors(make_project) -> None:
    scene, made = plan_with(make_project, ONE_REQUEST, [{"raise": "block:app2", "by": 0.4}], (854, 480))
    assert "app2->cache" in scene._raised_lines and "browser->lb" not in scene._raised_lines
    k = next(i for i, lab in enumerate(made.labels) if lab.key == ("block", "app2"))
    assert k not in made.placement.on_top
    w, h = made.labels[k].extent
    rect = rect_of(made.placement.centres[k] + np.array([0.0, 0.4 * ISO_RISE * made.scale]), (w + 2 * scene.label_pad[0], h + 2 * scene.label_pad[1]))
    for points in scene._raised_lines.values():
        pts = points * made.scale
        inside = (pts[:, 0] >= rect[0]) & (pts[:, 0] <= rect[2]) & (pts[:, 1] >= rect[1]) & (pts[:, 1] <= rect[3])
        assert int(np.count_nonzero(inside)) < 2       # Step 176: 'App 2' lay on the start of app2->cache


def test_lint_judges_a_labels_distance_at_the_diagrams_own_scale() -> None:
    labels = [label("Web", "block", "web", [100, 60, 160, 90])]
    near = frame(labels, {"web": box(100, 130, 160, 190)})          # 40 px off: over the 29 px limit
    assert any("is 40 px" in f.message for f in RULES["iso_labels"].check(near, IsoLabelsRule()))
    near.frame["iso_diagram"]["zoom"] = 2.0                          # a focus magnified it: 20 px in the diagram
    assert list(RULES["iso_labels"].check(near, IsoLabelsRule())) == []


# ----- pipes to raised blocks ----------------------------------------------------------------------


PIPES = {"blocks": [{"id": "a", "at": [0, 0]}, {"id": "b", "at": [3, 0]}, {"id": "c", "at": [3, 3]}],
         "edge_style": "pipe", "edges": ["a -> b", "b -> c"]}


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
def test_pipes_tilt_up_to_a_raised_block_and_flows_ride_on_them(make_project, media: Path) -> None:
    acts = [{"raise": "block:b", "by": 0.8}, {"flow": "edge:a->b", "style": "packets", "at": 0.5}]
    raised = render(project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": PIPES, "beats": beats(acts)}]), "s", media, size=(160, 90))
    assert raised._edge_lift[0] == pytest.approx((0.0, 0.8)) and raised._edge_lift[1] == pytest.approx((0.8, 0.0))
    for k in (0, 1):
        for piece, b in raised._pipe_pieces[k]:
            corners = [(x, y, b.z1) for x in (b.x0, b.x1) for y in (b.y0, b.y1)]
            ground_top = max(float(raised._to_scene(*iso_point(*c))[1]) for c in corners)
            assert piece.get_top()[1] > ground_top + 0.02               # up the picture towards the raised end


# ----- 9:16 shots on an iso place -------------------------------------------------------------------


def figure(name: str, x: float, facing: str = "right") -> ShotFigure:
    return ShotFigure(name, x, 0.0, 0.6, facing, 0.6)


def test_a_portrait_close_up_keeps_its_neighbour_whole_and_centres_the_figures() -> None:
    present = {"rowan": figure("rowan", 0.12, "left"), "hazel": figure("hazel", -0.37)}
    bounds = (-4.0, 4.0, -7.1, 7.1)
    view = frame_shot("closeup", [present["rowan"]], frame_width=8.0, frame_height=14.2, bounds=bounds)
    assert view.scale == pytest.approx(8.0)                              # held back by the tightest zoom
    width = 8.0 / view.scale
    hazel = present["hazel"].box()
    assert view.center_x - width / 2 > hazel[0]                          # as framed: Hazel cut at the left edge
    framed = portrait_shot(view, Shot("closeup", ("rowan",)), present, frame_width=8.0, frame_height=14.2, bounds=bounds)
    left, right = framed.center_x - width / 2, framed.center_x + width / 2
    for b in (hazel, present["rowan"].box()):
        assert left < b[0] and b[2] < right                              # both whole
    assert framed.center_y == pytest.approx(0.3)                         # the figures in the middle, not the head at the top
    far = {"rowan": figure("rowan", 0.12), "juno": figure("juno", 3.0)}
    alone = portrait_shot(view, Shot("closeup", ("rowan",)), far, frame_width=8.0, frame_height=14.2, bounds=bounds)
    assert alone.center_x == pytest.approx(view.center_x)                 # nobody at the edge: as framed
    over = ShotView(0.0, 0.0, 8.0)
    assert portrait_shot(over, Shot("over_shoulder", ("rowan",), "hazel"), present, frame_width=8.0, frame_height=14.2, bounds=bounds) is over
