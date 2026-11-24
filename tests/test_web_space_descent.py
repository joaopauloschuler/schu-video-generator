"""One world from orbit to the ground, ``vidgen/space-descent`` and the moves ``descend`` / ``ascend`` of
``vidgen/space-camera-air`` (Step 391, DESIGN.md §123.13): the module is served by its import name; its
parts are registered; in Node (when it is installed): the handover's weights are smooth, monotonic and
share a pixel with what is left, what is drawn at which height, the distance to the sphere, the globe's
turn, options with a did-you-mean, the descent's height profile, its end joined to a ``skim`` and its
reverse; in Chromium (``slow``): frames from orbit to the surface draw, the picture's brightness and colour
change by bounded steps across the handover heights, a frame is the same whatever was drawn before it, and
the same with the baked maps from the cache, baked cold and without the cache."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.web import baked as B
from vidgen.web import parts as P
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = DATA / "web" / "modules"
MODULE = MODULES / "space-descent.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
PART_NAMES = {"joined-ocean-orbit", "joined-ocean-handover", "joined-desert", "camera-descend"}
NODE_MODULES = ("music-time", "baked", "space-bodies", "space-air", "space-sea", "space-clouds", "space-land", "space-descent", "space-camera", "space-scene", "space-camera-air")


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-descent"] == "space-descent.js"
    assert IMPORT_MAP["imports"]["vidgen/space-descent"] == "/__vidgen__/modules/space-descent.js"
    assert vidgen_file("modules/space-descent.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-descent.js"])["__vidgen__/modules/space-descent.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/space-air", "vidgen/space-sea", "vidgen/space-land", "vidgen/space-clouds", "vidgen/space-bodies"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-descent" not in engine_id()


def test_the_parts_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-descent.js"}
    assert set(found) == PART_NAMES
    assert all(found[n].kind == "air" and found[n].module == "vidgen/space-descent" for n in PART_NAMES if n.startswith("joined-"))
    assert found["camera-descend"].kind == "camera" and found["camera-descend"].module == "vidgen/space-camera-air"
    assert "world(renderer, {" in found["joined-ocean-orbit"].use and "w.update(t, {camera})" in found["joined-ocean-orbit"].use
    assert "shot.end" in found["camera-descend"].use and "a look" in found["camera-descend"].label      # what is not true is said on the sheet
    assert "Math.random" not in (P.PARTS_DIR / "space-descent.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the modules in Node (``D``: the world's, ``A``: the camera's) and print ``out`` as JSON."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    three = tmp_path / "node_modules" / "three"
    three.mkdir(parents=True)
    for name in ("three.module.js", "three.core.js"):
        (three / name).symlink_to(DATA / "three" / name)
    (three / "package.json").write_text(json.dumps({"name": "three", "type": "module", "exports": {".": "./three.module.js"}}), encoding="utf-8")
    ours = tmp_path / "node_modules" / "vidgen"
    ours.mkdir()
    for name in NODE_MODULES:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in NODE_MODULES}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as D from 'vidgen/space-descent';\nimport * as A from 'vidgen/space-camera-air';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_the_handover_the_stages_and_the_descent_in_node(tmp_path: Path) -> None:
    hand, stages, geo, options, fall, join, wrong = _run_in_node(tmp_path, """
const H = D.HANDOVERS.low, hs = Array.from({length: 121}, (_, i) => 100 * Math.pow(10, i / 30)), ds = Array.from({length: 61}, (_, i) => 1000 * Math.pow(10, i / 20));
const mono = (v) => v.every((x, i) => i === 0 || x >= v[i - 1] - 1e-12), step = (v) => Math.max(...v.map((x, i) => (i === 0 ? 0 : Math.abs(x - v[i - 1]))));
out.push({inRange: hs.every((h) => ds.every((d) => { const w = D.globeWeight(h, d, H); return w >= 0 && w <= 1; })),
  byDistance: [3e3, 8e3, 14e3, 1e5].every((h) => mono(ds.map((d) => D.globeWeight(h, d, H)))), byHeight: [2e4, 5e4, 2e6].every((d) => mono(hs.map((h) => D.globeWeight(h, d, H)))),
  step: Math.max(step(hs.map((h) => D.globeWeight(h, 1e9, H))), step(hs.map((h) => D.globeWeight(h, h, H)))),
  ends: [D.globeWeight(2000, 1e9, H), D.globeWeight(4e5, 4e5, H), D.globeWeight(8e4, 4e5, H), D.globeWeight(5e4, 5e4, H)], high: [D.globeWeight(50e3, 1e9, D.HANDOVERS.high), D.globeWeight(7e5, 7e5, D.HANDOVERS.high)]});
out.push({names: [400e3, 30e3, 5e3, 2000, 10].map((h) => D.stageOf(h, H).name), drawn: [400e3, 30e3, 2000].map((h) => [D.stageOf(h, H).globe, D.stageOf(h, H).local]),
  mars: [700e3, 200e3, 50e3].map((h) => D.stageOf(h, D.HANDOVERS.high).name), stages: D.STAGES});
const R = 6.371e6, t = D.globeTurn([8, -150]), dotp = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
out.push({down: D.surfaceDistance(R, 400e3, -1), near: D.surfaceDistance(R, 0.5, -1), tangent: D.surfaceDistance(R, 400e3, 0.5), limb: D.surfaceDistance(R, 400e3, -Math.sqrt(400e3 * (2 * R + 400e3)) / (R + 400e3)),
  ortho: [dotp(t[0], t[1]), dotp(t[0], t[2]), dotp(t[1], t[2]), dotp(t[0], t[0]), dotp(t[1], t[1]), dotp(t[2], t[2])], north: D.globeTurn([90, 0])[1], sun: [D.sunOf([90, 0]), D.sunOf([0, 3, 0]), D.sunOf([0, 90])]});
const mars = D.resolveWorld({land: "mars"}), sea = D.resolveWorld({sea: true, clouds: "fair", at: [8, -150]});
out.push({mars: [mars.planet, mars.at, mars.air, mars.handover.near, mars.land.world, mars.sea, mars.clouds], sea: [sea.planet, sea.air, sea.handover.near, sea.sea, sea.clouds, sea.land], own: D.resolveWorld({handover: {near: [5e3, 5e4], height: [1e3, 2e4]}}).handover});
const cam = A.airCamera({radius: R}), o = {over: [0, 10], from: 400e3, to: 300, heading: 300, turn: 30, speed: 90, lens: ["normal", "wide"]};
const shots = Array.from({length: 101}, (_, i) => cam.descend(i / 10, o)), logs = shots.map((s) => Math.log10(s.aboveGround));
out.push({top: shots[0].aboveGround, bottom: shots[100].aboveGround, falling: shots.every((s, i) => i === 0 || s.aboveGround <= shots[i - 1].aboveGround), middle: [logs[30] - logs[40], logs[40] - logs[50], logs[50] - logs[60]],
  sinkEnd: shots[100].sink, sinkMid: shots[50].sink, pitch: [shots[0].pitch, shots[100].pitch], heading: [shots[0].heading, shots[100].heading], speed: [shots[0].speed, shots[40].speed, shots[100].speed],
  fov: [shots[0].fov, shots[100].fov], up: Math.max(...shots.map((s) => Math.abs(Math.hypot(...s.up) - 1))), look: cam.descend(0, {...o, look: 70}).pitch, lookEnd: cam.descend(10, {...o, look: 70}).pitch, again: JSON.stringify(cam.descend(3.3, o)) === JSON.stringify(cam.descend(3.3, o))});
const a = cam.descend(10, o), e = a.end, k = {over: [10, 13], ...e, follow: 0}, b = cam.skim(10, k), a1 = cam.descend(9.99, o), b1 = cam.skim(10.01, k), gap = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
const up = cam.ascend(3, o), dn = cam.descend(7, o);
out.push({place: gap(a.from, b.from), view: gap(a.forward, b.forward) + gap(a.up, b.up), fov: a.fov - b.fov, before: gap(a.from, a1.from), after: gap(b1.from, b.from), end: e,
  reverse: gap(up.from, dn.from) + gap(up.forward, dn.forward), sinks: [up.sink, dn.sink], move: [up.move, dn.move]});
out.push({option: err(() => D.resolveWorld({see: true})), handover: err(() => D.handoverOf("lo")), spans: err(() => D.handoverOf({near: [5e3, 1e3]})), order: err(() => D.handoverOf({near: [1e3, 5e3], height: [1e3, 9e3]})),
  air: err(() => D.resolveWorld({air: false})), sun: err(() => D.sunOf([1])), renderer: err(() => D.world({}, {})), key: err(() => cam.descend(0, {...o, headng: 3})), ends: err(() => cam.descend(0, {...o, from: 100, to: 300})),
  globeAir: err(() => D.resolveWorld({globe: {air: "earth"}}))});
""")
    assert hand["inRange"] and hand["byDistance"] and hand["byHeight"]                 # a share of the pixel: 1 - weight is the sea's, the ground's and the decks'
    assert hand["step"] < 0.12                                                          # no jump between heights 8 % apart
    assert hand["ends"] == [0, 1, 1, 0] and hand["high"] == [0, 1]
    assert stages["names"] == ["globe", "handover", "handover", "local", "local"] and stages["drawn"] == [[True, False], [True, True], [False, True]]
    assert stages["mars"] == ["globe", "handover", "local"] and stages["stages"] == ["globe", "handover", "local"]
    assert geo["down"] == pytest.approx(400e3, rel=1e-12) and geo["near"] == pytest.approx(0.5, rel=1e-9)       # no difference of large numbers near the ground
    assert geo["tangent"] == pytest.approx(geo["limb"], rel=1e-6) and geo["limb"] == pytest.approx((400e3 * (2 * 6.371e6 + 400e3)) ** 0.5, rel=1e-9)
    assert np.allclose(geo["ortho"], [0, 0, 0, 1, 1, 1], atol=1e-12) and np.allclose(geo["north"], [0, 1, 0], atol=1e-12)
    assert np.allclose(geo["sun"], [[0, 1, 0], [0, 1, 0], [1, 0, 0]], atol=1e-12)
    assert options["mars"] == ["mars", [-8, 40], "mars", [150e3, 600e3], "mars", None, None]                    # the ground's own planet, place and air; bare ground hands over high
    assert options["sea"] == ["earth", "earth", [60e3, 400e3], {}, {"sky": "fair"}, None] and options["own"] == {"near": [5e3, 5e4], "height": [1e3, 2e4]}
    assert fall["top"] == pytest.approx(400e3, rel=1e-6) and fall["bottom"] == pytest.approx(300, rel=1e-6) and fall["falling"]
    assert max(fall["middle"]) - min(fall["middle"]) < 1e-6 and fall["middle"][0] > 0.3                         # equal time for each power of ten of height
    assert abs(fall["sinkEnd"]) < 1e-6 and fall["sinkMid"] > 1000                                               # it ends level; a camera's fall, not a vehicle's
    assert fall["pitch"][0] < -20 and -12 < fall["pitch"][1] < -4 and fall["heading"] == [270, 300] and fall["speed"][0] == 0 and fall["speed"][1] == 0 and fall["speed"][2] == pytest.approx(90)
    assert fall["fov"][0] < fall["fov"][1] and fall["up"] < 1e-9 and fall["look"] == pytest.approx(-70) and fall["lookEnd"] == pytest.approx(fall["pitch"][1]) and fall["again"]
    assert join["place"] < 1e-6 and join["view"] < 1e-9 and abs(join["fov"]) < 1e-9                             # a skim given shot.end starts where, how and as fast as the descent ends
    assert join["before"] == pytest.approx(0.9, abs=0.01) and join["after"] == pytest.approx(0.9, abs=0.01)
    assert set(join["end"]) == {"from", "heading", "speed", "clearance", "pitch", "lens"}
    assert join["reverse"] < 1e-9 and join["sinks"][0] == pytest.approx(-join["sinks"][1]) and join["sinks"][1] > 0 and join["move"] == ["ascend", "descend"]
    assert 'did you mean "sea"' in wrong["option"] and 'did you mean "low"' in wrong["handover"] and "from < to" in wrong["spans"] and "near[1]" in wrong["order"]
    assert "needs an air" in wrong["air"] and "elevation" in wrong["sun"] and "WebGLRenderer" in wrong["renderer"] and 'did you mean "heading"' in wrong["key"] and "above" in wrong["ends"] and "no air of its own" in wrong["globeAir"]


PAGE = """
import * as THREE from "three";
import {world} from "vidgen/space-descent";
import {airCamera} from "vidgen/space-camera-air";
let renderer, scene, camera, w, cam, c;
export function load(ctx) {
  c = ctx.data; window.made = {error: null, stages: [], heights: [], problems: []};
  try {
    renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false}); renderer.setSize(ctx.width, ctx.height, false);
    scene = new THREE.Scene(); camera = new THREE.PerspectiveCamera(50, ctx.width / ctx.height, 2, 4e7);
    w = world(renderer, {planet: "earth", at: [8, -150], sun: [38, 250], sea: {state: "breeze", seed: 3}, clouds: {sky: "fair", seed: 4}, quality: "fast", scene});
    scene.add(w.object); cam = airCamera({camera, ...w.rig});
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
export function frame(t, ctx) {
  try {
    const h = c.heights[c.order[Math.round(t * ctx.fps)]];
    cam.apply(0, cam.rise(0, {progress: 0.5, from: h * 0.999, to: h * 1.001, heading: 300, lens: {fov: 50}}));
    w.update(0, {camera});
    window.made.stages.push(w.state.stage); window.made.heights.push(w.heightOf(camera)); window.made.problems.push(w.problems(camera).length);
    renderer.render(scene, camera);
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
"""
# from orbit to the surface; the handover (HANDOVERS.low: 80 km down to 2.5 km) in steps of a sixth of a power of ten
HEIGHTS = [400e3, 150e3] + [100e3 * 10 ** (-k / 6) for k in range(11)] + [1000.0, 300.0]


@pytest.mark.slow
@pytest.mark.render
def test_the_joined_world_draws_from_orbit_to_the_surface_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "world.js").write_text(PAGE, encoding="utf-8")
    store = B.BakedStore(tmp_path / "baked", 10**9)
    n = len(HEIGHTS)
    forward, shuffled = list(range(n)), [(k * 7 + 3) % n for k in range(n)]

    def draw(order: list[int], baked: B.BakedStore | bool) -> tuple[dict[int, np.ndarray], dict]:
        with WebPage(tmp_path, WebEntry("script", "world.js"), scene_id="s", size=(160, 90), fps=10, frames=n, data={"heights": HEIGHTS, "order": order}, baked=baked) as page:
            frames = {k: page.frame(i)[..., :3].astype(int) for i, k in enumerate(order)}
            made = page._page.evaluate("window.made")
            assert made["error"] is None, made["error"]
            return frames, {k: (made["stages"][i], made["heights"][i], made["problems"][i]) for i, k in enumerate(order)}

    plain, numbers = draw(forward, False)
    cold, _ = draw(shuffled, store)
    warm, _ = draw(forward, store)
    assert sorted(set(shuffled)) == forward
    for k in forward:
        assert plain[k].max() > 60, HEIGHTS[k]                                           # a picture at every height
        assert np.abs(plain[k] - cold[k]).max() <= 2, HEIGHTS[k]                         # the same frame after other frames, baked cold ...
        assert np.abs(plain[k] - warm[k]).max() <= 2, HEIGHTS[k]                         # ... and from the cache
        assert abs(numbers[k][1] - HEIGHTS[k]) < 0.002 * HEIGHTS[k] + 3 and numbers[k][2] == 0          # over the waves' crests
    assert [numbers[k][0] for k in forward] == ["globe"] + ["handover"] * 11 + ["local"] * 3
    # across the handover (100 km down to 3.2 km: above the cumulus, which the next sample is level with) the lower half of the
    # picture (the surface) and its top rows (the sky) change by bounded steps
    ground = np.array([plain[k][45:].mean(axis=(0, 1)) for k in range(2, 12)])
    sky = np.array([plain[k][:12].mean(axis=(0, 1)) for k in range(2, 12)])
    # the decks' shadows on the sea (Step 403) change the ground's mean as other clouds come into view: up to 34 levels between two heights
    assert np.abs(np.diff(ground, axis=0)).max() < 40 and np.abs(np.diff(sky, axis=0)).max() < 40
    assert plain[0][:8].mean() < 40 and plain[n - 1][:8, :, 2].mean() > 90                # black over the limb from orbit, a blue sky at the surface
