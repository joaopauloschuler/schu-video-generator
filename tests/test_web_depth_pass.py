"""Step 403b: ``guide: depth`` of a three.js web scene. vidgen/three-finish packs
the depth buffer (distance along the view, log2 in 24 bits; 0: nothing drawn) and vidgen makes the
grey guide with one range for the shot (near / z: near white, far dark, the sky black). Cheap: the
packing, the grey, the config, which render a pass is cut from and the cut from a stub render; in
Chromium (``slow``): exact distances, a vertex shader's displacement kept, the sky "nothing drawn",
and a page that draws no depth refused."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import minimal_config, write_clip

from vidgen.browser import chromium
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.ffmpeg import find_ffmpeg, probe
from vidgen.render.pipeline import scene_pass_clips
from vidgen.videogen.inputs import SceneRender, make_inputs, render_kind
from vidgen.videogen.shots import plan_shots, project_shots
from vidgen.web.depth import LOG_MIN, LOG_SPAN, depth_grey, pack, shot_near, unpack
from test_videogen_shots import CATALOG

MODULE = Path(__file__).resolve().parent.parent / "src" / "vidgen" / "data" / "web" / "modules" / "three-finish.js"
MODEL = "bytedance/seedance-2.0-fast"


def quiet(_line: str) -> None:
    """An ``out`` that prints nothing."""


def test_the_packing_round_trips_and_the_page_uses_the_same_numbers() -> None:
    z = np.array([0.01, 0.5, 1.0, 37.25, 1e4, 3e7, np.inf])
    back = unpack(pack(z))
    assert np.isinf(back[-1]) and np.allclose(back[:-1], z[:-1], rtol=1e-5)
    assert pack(np.array([np.inf])).tolist() == [[0, 0, 0]]
    source = MODULE.read_text(encoding="utf-8")
    found = re.search(r"DEPTH_LOG = Object\.freeze\(\{min: (-?\d+), span: (\d+)\}\)", source)
    assert found and (float(found[1]), float(found[2])) == (LOG_MIN, LOG_SPAN)
    assert "16777214.0" in source


def test_the_grey_is_near_over_distance_with_one_range_for_the_shot() -> None:
    near_frame = np.full((10, 10), 4.0)
    far_frame = np.full((10, 10), 40.0)
    far_frame[0, 0] = np.inf   # the sky: not counted
    near = shot_near(iter([near_frame, far_frame]))
    assert near is not None and 4.0 <= near < 4.2   # 1 % of the shot's pixels at 4 m: they set white
    grey = depth_grey(np.array([near, 2 * near, 10 * near, np.inf]), near)
    assert grey.tolist() == [255, 128, 26, 0]
    assert shot_near(iter([np.full((4, 4), np.inf)])) is None


def web_config(guide: str = "depth", **spec: Any) -> dict[str, Any]:
    """A project with one ``web`` scene whose beat ``a`` is a generated shot with ``guide``."""
    shot = {"kind": "establishing", "model": MODEL, "prompt": "a glider over the sea", "guide": guide, "audio": "none", **spec}
    return minimal_config(
        format={"width": 320, "height": 180, "fps": 10}, draft={"width": 160, "height": 90, "fps": 5},
        videogen={"provider": "mock", "budget_usd": 2.0},
        scenes=[{"id": "w", "type": "web", "params": {"script": "page.js"}, "beats": [{"id": "a", "text": "The glider holds its line.", "generated_shot": shot}]}],
    )


def test_a_web_scene_sends_depth_but_not_the_other_passes(make_project) -> None:
    root = make_project(web_config())
    (root / "page.js").write_text("export function frame() {}\n", encoding="utf-8")
    project = Project.load(root)
    assert render_kind(project, "w", "depth") == "final" and render_kind(project, "w", None) == "render"
    clips = scene_pass_clips(project, False, "w", ("depth", "outline", "mask"))
    assert clips == {"depth": project.render_dir(False) / "web" / "w.depth.mkv"}
    other = make_project(web_config("outline"), folder="other")
    (other / "page.js").write_text("export function frame() {}\n", encoding="utf-8")
    with pytest.raises(VidgenError, match=r"guide: outline is a guide pass of a 3d scene, but scene 'w' is a web scene; .* on a web or space scene, depth"):
        Project.load(other)


def packed_clip(path: Path, frames: list[np.ndarray], fps: int) -> Path:
    """A lossless FFV1 clip of packed depth frames (metres; ``inf``: nothing drawn), as the page leaves it."""
    height, width = frames[0].shape
    data = b"".join(np.concatenate([pack(z), np.full((height, width, 1), 255, np.uint8)], axis=-1).tobytes() for z in frames)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}", "-framerate", str(fps),
                    "-i", "pipe:0", "-c:v", "ffv1", "-pix_fmt", "bgra", str(path)], input=data, check=True, capture_output=True)
    return path


@pytest.mark.slow
def test_the_depth_guide_is_cut_from_the_finished_render_with_one_range(make_project) -> None:
    root = make_project(web_config(first_frame="render"))
    (root / "page.js").write_text("export function frame() {}\n", encoding="utf-8")
    project = Project.load(root)
    frames = []
    for n in range(60):   # a near box moving across a far wall, the sky on top
        z = np.full((18, 32), 50.0)
        z[:4] = np.inf
        z[8:12, n % 28:(n % 28) + 4] = 5.0
        frames.append(z)
    depth = packed_clip(root / "fake" / "w.depth.mkv", frames, 10)
    video = write_clip(root / "fake" / "scene.mp4", seconds=6.0, size="32x18", fps=10, audio=False)
    kinds: list[tuple[str, tuple[str, ...]]] = []

    def render(_project: Project, _scene: str, passes: tuple[str, ...], kind: str = "render") -> SceneRender:
        kinds.append((kind, passes))
        return SceneRender(video, {"a": 0.5}, {"depth": depth})

    lines: list[str] = []
    written = make_inputs(project, project_shots(project, CATALOG), guide=True, out=lines.append, render=render)
    assert kinds == [("final", ("depth",))] and {p.name for p in written} >= {"guide.depth.mp4", "first_frame.png"}
    guide = root / "build" / "videogen" / "a" / "guide.depth.mp4"
    shot = project_shots(project, CATALOG)[0]
    info = probe(guide)
    assert (info.width, info.height) == (32, 18) and abs(info.duration - shot.length) < 0.11
    grey = subprocess.run([find_ffmpeg(), "-v", "error", "-i", str(guide), "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"], capture_output=True, check=True).stdout
    pictures = np.frombuffer(grey, np.uint8).reshape(-1, 18, 32)
    wall, box, sky = pictures[:, 15, 0].astype(int), pictures[:, 10].max(axis=1).astype(int), pictures[:, 1, 16].astype(int)
    assert np.all(box >= 245) and np.all(np.abs(wall - wall[0]) <= 2) and np.all(sky <= 20)   # one range: the wall never flickers
    assert any("white at 5" in line for line in lines)
    record = json.loads((root / "build" / "videogen" / "a" / "inputs.json").read_text(encoding="utf-8"))["inputs"]
    assert record["guide.depth.mp4"]["source"]["guide"] == "depth" and record["first_frame.png"]["source"]["guide"] == "final"
    assert record["guide.depth.mp4"]["source"]["draft"] == [320, 180, 10]   # the finished render's size, not the draft's
    blocked = plan_shots(project, catalog=CATALOG).shots[0].shot.blocked
    assert not any(b.startswith("inputs changed") for b in blocked), blocked


PAGE = """import * as THREE from "three";
import {Finish} from "vidgen/three-finish";
let finish, renderer, scene, camera;
export function load(ctx) {
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x203040);
  camera = new THREE.PerspectiveCamera(40, ctx.width / ctx.height, 0.1, 50);
  camera.position.set(0, 0, 5);
  const left = new THREE.Mesh(new THREE.PlaneGeometry(1, 2), new THREE.MeshBasicMaterial({color: 0xff0000}));
  left.position.set(-0.6, 0, 0);
  // a plane moved 3 m back in its vertex shader, as a sea's waves are
  const moved = new THREE.ShaderMaterial({fragmentShader: "void main() { gl_FragColor = vec4(0.0, 1.0, 0.0, 1.0); }",
    vertexShader: "void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position + vec3(0.0, 0.0, -3.0), 1.0); }"});
  const right = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 3), moved);
  right.position.set(1.2, 0, 0);
  scene.add(left, right);
  if (!ctx.data.plain) finish = new Finish(renderer, scene, camera, ctx, {bloom: false, distort: ctx.data.distort ?? false});
}
export function frame(t) { if (finish) finish.render(t); else renderer.render(scene, camera); }
"""


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")


@pytest.mark.slow
@pytest.mark.render
def test_the_page_packs_the_exact_distances_and_keeps_vertex_shaders(tmp_path: Path) -> None:
    from vidgen.web.clip import make_web_clip
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    _chromium_or_skip()
    (tmp_path / "depth.js").write_text(PAGE, encoding="utf-8")
    with WebPage(tmp_path, WebEntry("script", "depth.js"), scene_id="d", size=(160, 90), fps=10, frames=2, draw_mode="depth") as page:
        z = unpack(page.frame(0))
        assert page.depth_frames() == 1
    assert np.isinf(z[45, 5]) and np.isinf(z[2, 80])   # the background: nothing drawn
    row = z[45][np.isfinite(z[45])]
    assert np.allclose(sorted(set(np.round(row, 3))), [5.0, 8.0], atol=1e-3)   # the plain plane at 5 m, the moved one at 8 m
    with WebPage(tmp_path, WebEntry("script", "depth.js"), scene_id="d", size=(160, 90), fps=10, frames=2, data={"distort": {"amount": 4, "mm": 12}}, draw_mode="depth") as page:
        bent = unpack(page.frame(0))
    assert not np.array_equal(np.isfinite(bent), np.isfinite(z))   # through the lens's distortion, as the colour frame
    with pytest.raises(VidgenError, match=r"guide: depth needs the page to draw through vidgen/three-finish"):
        make_web_clip(tmp_path, tmp_path / "out", "d", {"script": "depth.js", "data": {"plain": True}}, size=(32, 18), fps=10, frames=2, draw_mode="depth")


#: A page that draws its picture itself and only its depth frames through Finish (Step 435).
OWN_PICTURE_PAGE = """import * as THREE from "three";
import {Finish} from "vidgen/three-finish";
let renderer, scene, camera, depth = null;
export function load(ctx) {
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x203040);
  camera = new THREE.PerspectiveCamera(40, ctx.width / ctx.height, 0.1, 50);
  camera.position.set(0, 0, 5);
  scene.add(new THREE.Mesh(new THREE.PlaneGeometry(1, 2), new THREE.MeshBasicMaterial({color: 0xff0000})));
}
export function frame(t, ctx) {
  if (ctx.draw_mode === "depth") { (depth ??= new Finish(renderer, scene, camera, ctx)).render(t); return; }
  renderer.render(scene, camera);
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_a_page_with_its_own_picture_draws_its_depth_through_finish(tmp_path: Path) -> None:
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    _chromium_or_skip()
    (tmp_path / "own.js").write_text(OWN_PICTURE_PAGE, encoding="utf-8")
    with WebPage(tmp_path, WebEntry("script", "own.js"), scene_id="o", size=(160, 90), fps=10, frames=2) as page:
        assert page.frame(0)[45, 80][:3].tolist() == [255, 0, 0]
    with WebPage(tmp_path, WebEntry("script", "own.js"), scene_id="o", size=(160, 90), fps=10, frames=2, draw_mode="depth") as page:
        z = unpack(page.frame(0))
        assert page.depth_frames() == 1
    assert abs(float(z[45, 80]) - 5.0) < 1e-3 and np.isinf(z[2, 2])
