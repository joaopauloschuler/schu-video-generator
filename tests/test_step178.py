"""Step 178: a part of an ``iso_diagram`` that comes in never shows its final look first
(DESIGN.md §90.15). A block grown in a ``Succession`` (after the floor or a plate fades in, or
after the heading at the scene's start) was in the scene at full size until its turn came, then
jumped back to nothing and grew. The tests record what every rendered frame shows of each part
and check that it is unseen before it comes in, starts from its start state on the first frame it
is seen, and only then goes on to its final state; for every build style, kind of target and
timing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import tempconfig
from manim.renderer.cairo_renderer import CairoRenderer

from test_actions import beats, project_with
from test_phase_r_review import WEB
from vidgen import extensions, registry
from vidgen.render.worker import frame_size
from vidgen.world.iso_view import ISO_RISE

FPS = 15
SCENE = {
    "heading": "Flow",
    "blocks": [{"id": "web", "label": "Web"}, {"id": "db", "label": "Data", "shape": "database"},
               {"id": "app", "label": "App", "layers": ["UI", {"id": "api", "label": "API", "shape": "box"}]}],
    "groups": [{"id": "g", "label": "Back end", "blocks": ["db", "app"]}],
    "edges": ["web -> db: SQL", {"from": "db", "to": "app", "style": "pipe"}],
}


def _alpha(mob: Any, present: set[int]) -> float:
    """The most opaque part of ``mob`` drawn now (0 when none of it is in the scene)."""
    out = 0.0
    for m in mob.family_members_with_points():
        if id(m) in present:
            out = max(out, float(np.max(m.fill_rgbas[:, 3], initial=0.0)), float(np.max(m.stroke_rgbas[:, 3], initial=0.0)))
    return out


def _snapshot(scene: Any) -> dict[str, Any]:
    """What this frame shows of every part of the diagram: each block's opacity, height and
    bottom, its labels' opacity, each connector's, plate's and the floor's opacity."""
    present = {id(m) for m in scene.get_mobject_family_members()}
    parts = scene._parts
    out: dict[str, Any] = {"time": float(scene.renderer.time)}
    for name, block in parts["blocks"].items():
        labels = [scene._parts["texts"][key] for key in (("block", name), ("layer", name)) if key in scene._parts["texts"]]
        out[f"block:{name}"] = (_alpha(block, present), float(block.height), float(block.get_bottom()[1]),
                                max([_alpha(lab, present) for lab in labels], default=0.0))
    for k, edge in parts["edges"].items():
        out[f"edge:{k}"] = _alpha(edge, present)
    for gid, plate in parts["plates"].items():
        out[f"plate:{gid}"] = _alpha(plate, present)
    out["floor"] = _alpha(parts["floor"], present)
    return out


def record(make_project, monkeypatch: pytest.MonkeyPatch, media: Path, params: dict[str, Any], acts: list[Any],
           size: tuple[int, int] = (160, 90), **scene: Any) -> tuple[Any, list[dict[str, Any]]]:
    """Render an iso_diagram scene with ``params`` and one beat per entry of ``acts``; the
    snapshot of every frame rendered."""
    frames: list[dict[str, Any]] = []
    original = CairoRenderer.render

    def render(self: CairoRenderer, made: Any, time: float, moving: Any) -> None:
        original(self, made, time, moving)
        if hasattr(made, "_parts"):
            frames.append(_snapshot(made))

    monkeypatch.setattr(CairoRenderer, "render", render)
    project = project_with(make_project, [{"id": "s", "type": "iso_diagram", "params": params, "beats": beats(*acts), **scene}])
    w, h = size
    fw, fh = frame_size(w, h)
    settings = {"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": FPS,
                "media_dir": str(media), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR", "output_file": "s"}
    with tempconfig(settings):
        spec = project.scene("s")
        theme = extensions.activate(project)
        made = registry.get("iso_diagram").cls(spec, project, theme)
        made.finish = lambda: None
        made.render()
    assert frames
    return made, frames


SEEN = 0.02   # an opacity above this is seen


def check_grows_in(scene: Any, frames: list[dict[str, Any]], name: str) -> int:
    """``block:<name>`` is unseen until it comes in; on its first frame it is low (under half its
    height) with no label; it then only grows to its full height. The index of that first frame."""
    full = frames[-1][f"block:{name}"][1]
    box = scene.diagram_layout.blocks[name].box
    rise = (box.z1 - box.z0) * ISO_RISE * scene._unit   # how much taller its picture gets as it grows
    first = next(i for i, f in enumerate(frames) if f[f"block:{name}"][0] > SEEN)
    _alpha, height, _bottom, label = frames[first][f"block:{name}"]
    grown = 1 - (full - height) / rise
    assert grown < 0.5, f"{name} first seen at {grown:.0%} of its height (t={frames[first]['time']:.2f})"
    assert label < SEEN, f"{name}'s label seen on the block's first frame"
    heights = [f[f"block:{name}"][1] for f in frames[first:]]
    assert all(b >= a - 1e-6 for a, b in zip(heights, heights[1:])), f"{name} shrinks after it is first seen: {np.round(np.array(heights) / full, 2)}"
    assert heights[-1] == pytest.approx(full)
    return first


def check_fades_in(frames: list[dict[str, Any]], key: str, *, drops: bool = False) -> int:
    """``key`` (a block, connector, plate or the floor) is unseen until it comes in, then only
    grows more opaque (``drops``: a block also comes down onto its place). Its first frame."""
    def alpha(f: dict[str, Any]) -> float:
        value = f[key]
        return value[0] if isinstance(value, tuple) else value

    first = next(i for i, f in enumerate(frames) if alpha(f) > SEEN)
    alphas = [alpha(f) for f in frames[first:]]
    assert alphas[0] < 0.9, f"{key} first seen at opacity {alphas[0]:.2f} (t={frames[first]['time']:.2f})"
    assert all(b >= a - 1e-6 for a, b in zip(alphas, alphas[1:])), f"{key} fades back after it is first seen: {np.round(alphas, 2)}"
    if drops:
        bottoms = [f[key][2] for f in frames[first:]]
        assert bottoms[0] > bottoms[-1] + 1e-3, f"{key} does not come down onto its place"
        assert all(b <= a + 1e-6 for a, b in zip(bottoms, bottoms[1:]))
    return first


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
def test_a_block_built_mid_beat_grows_from_the_floor_on_its_first_frame(make_project, monkeypatch, media: Path) -> None:
    """The owner's case (examples/iso-web-page): built mid-beat with the floor under it coming
    in first; at the beat's start; and on a word."""
    acts = [[{"build": "block:web", "at": 0.5}], [{"build": "block:db", "at": "@three"}], [{"build": "stack:app"}]]
    scene, frames = record(make_project, monkeypatch, media, SCENE, acts)
    web = check_grows_in(scene, frames, "web")
    assert frames[web]["time"] > 0.4                     # not before its at: (the beat has 6 words)
    db = check_grows_in(scene, frames, "db")
    assert db > web
    assert check_fades_in(frames, "plate:g") <= db
    ui, api = check_grows_in(scene, frames, "UI"), check_grows_in(scene, frames, "api")
    assert db < ui <= api                                # a stack layer by layer
    check_fades_in(frames, "edge:0")                     # web -> db once both ends are there
    check_fades_in(frames, "edge:1")
    check_fades_in(frames, "floor")


@pytest.mark.render
def test_the_scenes_own_steps_grow_their_blocks_from_the_first_frame(make_project, monkeypatch, media: Path) -> None:
    """At the scene's start the heading and the floor fade in first (a crossfade shows these
    frames): the blocks are unseen meanwhile; ``build: each`` too, on later beats."""
    scene, frames = record(make_project, monkeypatch, media, {**SCENE, "entrance": "grow"}, [None, None])
    for name in ("web", "db", "UI", "api"):
        check_grows_in(scene, frames, name)
    scene, frames = record(make_project, monkeypatch, media, {**SCENE, "entrance": "grow", "build": "each"}, [None, None, None])
    firsts = [check_grows_in(scene, frames, name) for name in ("web", "db", "UI")]
    assert firsts == sorted(firsts)


@pytest.mark.render
@pytest.mark.parametrize("style", ["drop", "fade"])
def test_drop_and_fade_builds_start_unseen(make_project, monkeypatch, media: Path, style: str) -> None:
    acts = [[{"build": "group:g", "style": style, "at": 0.4}], [{"build": "block:web", "style": style, "at": "@two"}]]
    scene, frames = record(make_project, monkeypatch, media, SCENE, acts)
    for name in ("db", "UI", "api", "web"):
        check_fades_in(frames, f"block:{name}", drops=style == "drop")
    check_fades_in(frames, "plate:g")


@pytest.mark.render
def test_reveal_and_building_the_whole_diagram_or_a_connector_start_from_nothing(make_project, monkeypatch, media: Path) -> None:
    acts = [[{"build": "diagram", "at": 0.3}]]
    scene, frames = record(make_project, monkeypatch, media, SCENE, acts)
    for name in ("web", "db", "UI", "api"):
        check_grows_in(scene, frames, name)
    for key in ("floor", "plate:g", "edge:0", "edge:1"):
        check_fades_in(frames, key)
    acts = [[{"build": "edge:web->db", "at": 0.2}], [{"reveal": "block:web", "at": "@three"}]]
    scene, frames = record(make_project, monkeypatch, media, {**SCENE, "entrance": "grow"}, acts)
    assert check_fades_in(frames, "edge:0") < check_grows_in(scene, frames, "web")   # an action shows its target, even early


ISO_MAP = """
.......
.......
...b...
.......
.......
"""


@pytest.mark.render
def test_an_iso_place_object_revealed_and_hidden_never_shows_at_full_early_or_late(make_project, monkeypatch, media: Path) -> None:
    """The same bug class on an iso stage (Step 168): a pine revealed in front of a lamp (whose
    layer shows the pine) and a bush in front of a character (whose front picture shows it).
    Their other pictures swapped at the change's start (the pine at full on its first frame), a
    picture taken out mid-play was still drawn (a hidden pine came back at full), and a picture
    made mid-play was not drawn at all. Every frame now changes a little from the one before, and
    after the hide the place looks as before the reveal."""
    from test_cartoon_stage import CAST
    from conftest import minimal_config
    from vidgen.project import Project

    objects = [{"object": "lamp", "at": {"column": 2, "row": 2}}, {"object": "pine", "name": "tree", "at": {"column": 2, "row": 3}, "shown": False},
               {"object": "bush", "at": {"column": 5, "row": 4}, "shown": False}]
    stage = {"idle": False, "background": "#BFE3F5", "iso": {"map": ISO_MAP, "spots": {"b": "spot"}, "objects": objects},
             "characters": [{"name": "pip", "at": "spot"}]}
    acts = [None, [{"reveal": "tree", "at": 0.3}, {"reveal": "bush", "at": 0.3}], [{"hide": "tree", "at": 0.3}, {"hide": "bush", "at": 0.3}]]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=[{"id": "s", "type": "stage", "params": stage, "beats": beats(*acts)}])))
    shots: list[np.ndarray] = []
    original = CairoRenderer.render

    def render(self: CairoRenderer, made: Any, time: float, moving: Any) -> None:
        original(self, made, time, moving)
        shots.append(self.camera.pixel_array[..., :3].astype(int).copy())

    monkeypatch.setattr(CairoRenderer, "render", render)
    w, h = 256, 144
    fw, fh = frame_size(w, h)
    settings = {"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": FPS,
                "media_dir": str(media), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR", "output_file": "stage"}
    with tempconfig(settings):
        spec = project.scene("s")
        theme = extensions.activate(project)
        scene = registry.get("stage").cls(spec, project, theme)
        scene.finish = lambda: None
        scene.render()
    steps = [np.abs(b - a).sum(axis=2) for a, b in zip(shots, shots[1:])]
    still = next(k for k, step in enumerate(steps) if k > 0 and step.max() == 0)   # the scene's own fade-in is over
    assert any(step.max() > 0 for step in steps[still:])                            # the changes are drawn
    jumps = [(k, int((step > 300).sum())) for k, step in enumerate(steps) if k >= still and (step > 300).sum()]
    assert not jumps, f"pixels jump most of the way at once on frames {jumps}"
    assert np.abs(shots[-1] - shots[still]).sum(axis=2).max() < 30                  # hidden again: as before the reveal
    assert not scene._iso_follows


@pytest.mark.render
def test_the_example_trip_builds_each_block_without_a_flash(make_project, monkeypatch, media: Path) -> None:
    """The example's first iso scene (shortened): every block built on its word."""
    acts = [[{"build": "block:browser", "at": "@one"}, {"build": "block:dns", "style": "drop", "at": "@four"}],
            [{"build": "block:lb", "at": "@two"}, {"build": "group:apps", "at": "@five"}],
            [{"build": "block:cache", "at": "@two"}, {"build": "block:db", "style": "drop", "at": "@five"}]]
    scene, frames = record(make_project, monkeypatch, media, {**WEB, "entrance": "grow"}, acts)
    for name in ("browser", "lb", "app1", "app2", "cache"):
        check_grows_in(scene, frames, name)
    for name in ("dns", "db"):
        check_fades_in(frames, f"block:{name}", drops=True)
    check_fades_in(frames, "plate:apps")
