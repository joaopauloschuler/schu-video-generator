"""Astronomical scales in three.js, ``vidgen/space-scale`` (Step 368, DESIGN.md §122.4): served by its
import name, in the loaded-files record of a page that imports it and of no other; in Node (when it is
installed) on orbit data made by Python: the log view's mapping and r0 equal the flat ``orbit``
scene's, positions are subtracted in float64 before three.js sees them (a ship 1 AU out keeps
millimetres), Hermite between frames, the depth slices, the notes, the checks with a did-you-mean. In
Chromium (``slow``): the three cases of the step (a ship over a planet, the Earth and the Moon, a box
3 m away in front of both) draw without z-fighting and in the right order, where one depth range
fights."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vidgen.scenes import orbit_data as od
from vidgen.scenes import orbit_sky as osky
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULE = DATA / "web" / "modules" / "space-scale.js"
URL_PATH = "__vidgen__/modules/space-scale.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
FLAT = {"bodies": [{"preset": "earth", "e": 0, "i": 0, "raan": 0, "argp": 0}, {"preset": "mars", "e": 0.09, "i": 0, "raan": 0, "argp": 0, "nu": 95},
                   {"preset": "jupiter", "e": 0, "i": 0, "raan": 0, "argp": 0, "nu": 200}], "span": "1 yr"}
SHIP = {"central": "sun", "bodies": [{"preset": "earth"}, {"name": "Ship", "around": "Earth", "altitude": "400 km", "e": 0, "i": 51.6}], "span": "10 min"}


def test_the_module_is_served_by_its_import_name_and_imports_only_three() -> None:
    assert VIDGEN_MODULES["vidgen/space-scale"] == "space-scale.js"
    assert IMPORT_MAP["imports"]["vidgen/space-scale"] == f"/{URL_PATH}"
    assert vidgen_file("modules/space-scale.js") == MODULE
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source
    assert MODULE not in INIT_FILES and "space-scale" not in engine_id()
    assert len(current_loaded(Path("."), [URL_PATH])[URL_PATH] or "") == 64


def _run_in_node(tmp_path: Path, body: str, orbits: dict[str, Any] | None = None) -> list:
    """Import the module in Node as ``S`` (``three`` from vidgen's copy), with ``O`` the page's
    ``ctx.orbits`` built by vidgen's own helper from ``orbits``, and print ``out`` as JSON."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    package = tmp_path / "node_modules" / "three"
    package.mkdir(parents=True)
    for name in ("three.module.js", "three.core.js"):
        (package / name).symlink_to(DATA / "three" / name)
    (package / "package.json").write_text(json.dumps({"name": "three", "type": "module", "exports": {".": "./three.module.js"}}), encoding="utf-8")
    (tmp_path / "space.mjs").symlink_to(MODULE)
    (tmp_path / "data.json").write_text(json.dumps(orbits), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import fs from 'fs';\nimport * as THREE from 'three';\nimport * as S from './space.mjs';\n"
        "globalThis.window = globalThis; globalThis.top = globalThis; let O = null;\n"
        "globalThis.__vidgen = {start(info) { O = info.orbits; }};\n"
        f"(0, eval)(fs.readFileSync({json.dumps(str(DATA / 'web' / 'orbits.js'))}, 'utf8'));\n"
        "const raw = JSON.parse(fs.readFileSync('data.json', 'utf8')); if (raw) __vidgen.start({orbits: raw});\n"
        "const out = [];\nconst err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const calls = [];\nconst renderer = {render: (s, c) => calls.push([c.near, c.far]), clearDepth: () => calls.push('clear'),\n"
        "  capabilities: {logarithmicDepthBuffer: false}, domElement: {height: 180}, autoClear: true, shadowMap: {autoUpdate: true}};\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=True)
    return json.loads(done.stdout)


def _orbit_data(settings: dict[str, Any], frames: int = 21) -> tuple[od.OrbitData, dict[str, Any]]:
    s = od.OrbitData.model_validate(settings)
    return s, json.loads(json.dumps(od.make_orbit_data(s, 10, frames, frames)))


def test_the_log_view_is_the_flat_orbit_scenes(tmp_path: Path) -> None:
    settings, data = _orbit_data(FLAT)
    model = settings.model(None)
    r0 = osky.log_r0(model.system)
    out = _run_in_node(tmp_path, """
out.push(S.logR0(O));
for (const n of ["Earth", "Mars", "Jupiter"]) out.push(S.compress(O.position(n, 1.3), S.logR0(O)));
out.push(S.logR0(null) === S.AU / 10, S.compress([0, 0, 0], 1));
""", data)
    assert out[0] == pytest.approx(r0, rel=1e-12)

    class Flat(osky.OrbitSky):   # the flat scene's own mapping: D = log10(1 + r / r0), drawn in AU
        def _sky(self) -> Any:
            return osky.SkyInfo(log=True, r0=r0)
    t13 = od.frame_times(model.span, 21, 21)[13]
    for name, shown in zip(("Earth", "Mars", "Jupiter"), out[1:4]):
        np.testing.assert_allclose(np.array(shown) / osky.orbits.AU, Flat()._radial(model.position(name, t13)), rtol=1e-12, atol=1e-15)
    assert out[4] is True and out[5] == [0, 0, 0]


def test_positions_are_subtracted_in_double_precision_before_three_sees_them(tmp_path: Path) -> None:
    _, data = _orbit_data(SHIP, frames=11)
    out = _run_in_node(tmp_path, """
const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(50, 16 / 9, 1, 10);
const space = new S.SpaceView({fps: 10}, {renderer, scene, camera, orbits: O});
const ship = space.add(new THREE.Mesh(new THREE.BoxGeometry(100, 20, 20), new THREE.MeshBasicMaterial()), {body: "Ship"});
const earth = space.add(new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), new THREE.MeshBasicMaterial()), {body: "Earth"});
const off = [-150, 20, 40];
for (const t of [0, 0.5, 1]) {
  const s = O.position("Ship", t);
  space.update(t, {from: {body: "Ship", offset: off}, to: "Ship"});
  const naive = S.yUp(s.map((x, i) => Math.fround(x) - Math.fround(x + off[i])));   // made float32 before the subtraction
  out.push([ship.position.toArray(), S.yUp(off.map((x) => -x)), naive, earth.scale.x, Math.hypot(...s)]);
}
renderer.render(scene, camera);
out.push(calls, space.slices.length, space.note());
""", data)
    for shipped, exact, naive, radius, distance in out[:3]:
        assert distance > 1.4e11                                                       # the ship is 1 AU from the Sun
        assert max(abs(float(np.float32(a)) - b) for a, b in zip(shipped, exact)) < 1e-3   # millimetres once three.js makes it float32
        assert max(abs(a - b) for a, b in zip(naive, exact)) > 100                     # float32 first: kilometres off
        assert radius == next(b["radius"] for b in data["bodies"] if b["name"] == "Earth")   # true size
    calls, slices, note = out[3:]
    assert slices == 2 and len(calls) == 3 and calls[1] == "clear"                     # the planet, then the ship, the depth cleared between
    assert calls[0][0] > calls[2][1] and calls[2][1] / calls[2][0] <= 1e4 * 1.001
    assert note == {"lines": [], "text": ""}


def test_hermite_between_frames_and_the_frames_own_numbers_on_them(tmp_path: Path) -> None:
    settings, data = _orbit_data({"bodies": [{"preset": "earth"}], "span": "30 d"})
    model = settings.model(None)
    out = _run_in_node(tmp_path, """
const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(50, 1, 1, 10);
const space = new S.SpaceView({fps: 10}, {renderer, scene, camera, orbits: O});
out.push(space.position("Earth", 0.7), O.position("Earth", 0.7), space.position("Earth", 0.75), space.position("Earth", 2.0), O.position("Earth", 2.0));
out.push(S.hermite([1, 2, 3], [9, 9, 9], [4, 5, 6], [9, 9, 9], 2, 0), S.hermite([1, 2, 3], [9, 9, 9], [4, 5, 6], [9, 9, 9], 2, 1));
""", data)
    assert out[0] == out[1] and out[3] == out[4]                         # on a frame: exactly the data's numbers
    times = od.frame_times(model.span, 21, 21)
    middle = model.position("Earth", (times[7] + times[8]) / 2)
    straight = (model.position("Earth", times[7]) + model.position("Earth", times[8])) / 2
    assert float(np.linalg.norm(np.array(out[2]) - middle)) < 1e3        # 1.5 days of orbit: Hermite within a kilometre,
    assert float(np.linalg.norm(straight - middle)) > 1e6                # a straight line between the frames 10,000 km off
    assert out[5] == [1, 2, 3] and out[6] == [4, 5, 6]


def test_depth_slices(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push(S.depthSlices([[150, 300], [4e5, 1.3e7]]));                    // a ship before a planet: two slices, far first
out.push(S.depthSlices([[1e8 - 2e6, 1e8 + 2e6], [4.8e8 - 7e6, 4.8e8 + 7e6], [2.9, 3.1]]));   // Earth, Moon, a box: three
out.push(S.depthSlices([[100, 120], [110, 250], [260, 280]]));          // overlapping ones join; neighbours within 3x share
out.push(S.depthSlices([[1, 1e9]]).length, S.depthSlices([[1e-5, 1]], {near: 0.01})[0][0], S.depthSlices([]));
out.push(S.depthSlices(Array.from({length: 20}, (_, i) => [10 ** i, 2 * 10 ** i])).length);
""")
    assert out[0] == [[4e5, 1.3e7], [150, 300]]
    assert [round(a) for a, _ in out[1]] == [473000000, 98000000, 3]
    assert out[2] == [[100, 280]]
    pieces, nearest, empty, capped = out[3:]
    assert pieces == 3 and nearest == 0.01 and empty == [] and capped == 8


def test_notes_are_the_orbit_scenes_words_and_mistakes_say_what_to_do(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push(S.scaleNote("true"), S.scaleNote("enlarged", {enlarge: 50}), S.scaleNote("log"), S.scaleNote("log", {enlarge: {default: 1000, Sun: 10}}));
out.push(S.scaleNote("enlarged", {enlarge: 20, words: {sizes: "Größen nicht maßstäblich", enlarged: "Körper {factors} vergrößert"}}).text);
const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(50, 1, 1, 10), base = {renderer, scene, camera, orbits: O};
out.push(err(() => new S.SpaceView({}, {...base, enlage: 5})));
out.push(err(() => new S.SpaceView({}, {...base, mode: "enlarge"})));
out.push(err(() => new S.SpaceView({}, {...base, enlarge: 5})));
out.push(err(() => new S.SpaceView({}, {...base, mode: "enlarged"})));
out.push(err(() => new S.SpaceView({}, {...base, depth: "log"})));
out.push(err(() => new S.SpaceView({}, {...base, depth: "single", dofFocus: 3})));
const v = new S.SpaceView({fps: 10}, {...base, mode: "enlarged", enlarge: {default: 60, Moon: 20}});
out.push(err(() => v.add(new THREE.Object3D(), {body: "Mon"})));
out.push(err(() => v.add(new THREE.Object3D(), {at: [0, 0, 0], size: "body"})));
out.push(err(() => v.update(0, {from: "Moon", too: "Earth"})));
v.update(0, {from: {body: "Moon", offset: [0, 0, 4e8]}, to: "Earth"});
out.push(v.problems(), v.radius("Earth") / O.bodies.Earth.radius, v.radius("Moon") / O.bodies.Moon.radius, v.note().text);
const w = new S.SpaceView({fps: 10}, {...base, mode: "enlarged", enlarge: 20});
w.update(0, {from: {body: "Moon", offset: [0, 0, 4e8]}, to: "Earth"});
out.push(w.problems());
""", _orbit_data({"central": "earth", "bodies": [{"preset": "moon"}], "span": "1 d"})[1])
    assert out[0] == {"lines": [], "text": ""}
    assert out[1]["lines"] == ["sizes not to scale", "bodies enlarged 50×; distances to scale"]
    assert out[2]["lines"] == ["distances compressed (log)", "sizes not to scale"]
    assert out[3]["text"] == "distances compressed (log) · sizes not to scale · bodies enlarged 1000× (Sun 10×)"
    assert out[4] == "Größen nicht maßstäblich · Körper 20× vergrößert"
    assert 'unknown option "enlage" (did you mean "enlarge"?)' in out[5]
    assert 'mode must be one of "true", "enlarged", "log", got "enlarge" (did you mean "enlarged"?)' in out[6]
    assert 'mode "true" draws every size as it is' in out[7] and "needs enlarge" in out[8]
    assert "logarithmicDepthBuffer: true" in out[9] and 'dofFocus goes with depth "split"' in out[10]
    assert 'no body "Mon" (did you mean "Moon"?); bodies: Earth, Moon' in out[11]
    assert "has no radius" in out[12] and 'unknown option "too" (did you mean "to"?)' in out[13]
    problems, earth, moon, note, none = out[14:]
    assert earth == 60 and moon == 20 and note == "sizes not to scale · bodies enlarged 60× (Moon 20×); distances to scale"
    assert problems == ["Earth, drawn 60× its size, covers Moon's centre: give Earth a smaller factor (enlarge: {default: ..., Earth: ...})"]
    assert none == []                                                    # 60 Earth radii reach past the Moon; 20 do not


def test_the_reference_guide_and_cookbooks_describe_it() -> None:
    config = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    assert "**Astronomical scales: `vidgen/space-scale`**" in config and "| `dofFocus` |" in config
    guide = (ROOT / "src" / "vidgen" / "data" / "guide" / "AGENTS.md").read_text(encoding="utf-8")
    assert "**Astronomical scales: `vidgen/space-scale`.**" in guide and 'from "vidgen/space-scale"' in guide
    assert "vidgen/space-scale" in (ROOT / "docs" / "COOKBOOK-ORBITS.md").read_text(encoding="utf-8")
    assert "**Space at real scale.**" in (ROOT / "docs" / "COOKBOOK-3D.md").read_text(encoding="utf-8")
    assert "### 122.4 Scale: `vidgen/space-scale` (Step 368)" in (ROOT / "DESIGN.md").read_text(encoding="utf-8")


PAGE = """import * as THREE from "three";
import {SpaceView} from "vidgen/space-scale";
let space, renderer, scene, view;
const basic = (color) => new THREE.MeshBasicMaterial({color});
const unit = (p) => { const r = Math.hypot(...p); return p.map((x) => x / r); };
export function load(ctx) {
  const c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(c.ship ? 40 : 3, ctx.width / ctx.height, 0.1, 1000);
  space = new SpaceView(ctx, {renderer, scene, camera, depth: c.depth});
  const sphere = new THREE.SphereGeometry(1, 96, 48);
  const planet = (name, inner, outer) => {   // a red ball under a green shell 100 m higher: red showing is z-fighting
    const m = new THREE.Mesh(sphere, basic(inner));
    if (outer !== null) { const s = new THREE.Mesh(sphere, basic(outer)); s.scale.setScalar(1 + 100 / ctx.orbits.bodies[name].radius); m.add(s); }
    space.add(m, {body: name});
  };
  planet("Earth", 0xff0000, 0x00ff00);
  if (c.ship) {
    space.add(new THREE.Mesh(new THREE.BoxGeometry(100, 20, 20), basic(0x2040ff)), {body: "Ship"});
    view = (t) => { const r = unit(space.at("Ship", t)), v = unit(ctx.orbits.velocity("Ship", t));
      return {from: {body: "Ship", offset: r.map((x, i) => x * 60 - v[i] * 220)}, to: {body: "Ship", offset: r.map((x) => -x * 40)}, up: r}; };
  } else {
    planet("Moon", 0xffffff, null);
    view = (t) => { const m = space.at("Moon", t), d = unit(m), s = unit([-d[1], d[0], 0]);
      return {from: m.map((x, i) => x + d[i] * 1e8 + s[i] * 1.2e6 + (i === 2 ? 1e6 : 0)), to: "Earth"}; };
    const box = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.04, 0.04), basic(0x2040ff));   // 4 cm, 3 m in front of the camera
    space.add(box, {at: (t) => { const e = view(t).from, u = unit(space.at("Earth", t).map((x, i) => x - e[i])); return e.map((x, i) => x + u[i] * 3 + (i === 2 ? 0.03 : 0)); }});
  }
}
export function frame(t) { space.update(t, view(t)); renderer.render(scene, space.camera); }
"""


@pytest.mark.slow
@pytest.mark.render
def test_no_z_fighting_and_the_right_order_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "space.js").write_text(PAGE, encoding="utf-8")
    cases = {"ship": {"central": "earth", "bodies": [{"name": "Ship", "altitude": "400 km", "e": 0, "i": 51.6}], "span": "10 min"},
             "moon": {"central": "earth", "bodies": [{"preset": "moon"}], "span": "1 d"}}

    def draw(case: str, depth: str) -> tuple[list[np.ndarray], dict]:
        data = od.make_orbit_data(od.OrbitData.model_validate(cases[case]), 10, 3, 3)
        with WebPage(tmp_path, WebEntry("script", "space.js"), scene_id="s", size=(320, 180), fps=10, frames=3, orbits=data,
                     data={"ship": case == "ship", "depth": depth}) as page:
            return [page.frame(n)[..., :3].astype(int) for n in range(3)], dict(page.loaded)

    def count(px: np.ndarray) -> dict[str, int]:
        r, g, b = px[..., 0], px[..., 1], px[..., 2]
        return {"red": int(((r > 120) & (g < 60)).sum()), "green": int(((g > 120) & (r < 60)).sum()), "blue": int(((b > 150) & (r < 120)).sum()),
                "white": int((px.min(axis=-1) > 200).sum())}

    for case in cases:
        split, loaded = draw(case, "split")
        again, _ = draw(case, "split")
        single, _ = draw(case, "single")
        assert all(np.array_equal(a, b) for a, b in zip(split, again))     # the same frames every time
        assert "__vidgen__/modules/space-scale.js" in loaded
        for good, bad in zip(split, single):
            g, b = count(good), count(bad)
            assert g["red"] <= 3, (case, g)                                 # at most a few limb pixels
            assert b["red"] > 30, (case, b)                                 # one depth range: the shell fights the ball
            assert g["blue"] > 1000 and g["green"] > 1000                   # the ship (or the box) in front, the planet's shell
            if case == "moon":
                assert g["white"] > 5000                                    # the Moon in front of the Earth


TRAPS = """import * as THREE from "three";
import {SpaceView} from "vidgen/space-scale";
let space, renderer, scene;
const CLAMP = `void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); gl_Position.z = min(gl_Position.z, gl_Position.w * 0.999999); }`;
export function load(ctx) {
  const c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, ctx.width / ctx.height, 0.1, 1000);
  space = new SpaceView(ctx, {renderer, scene, camera, orbits: null});
  // a world added by hand (at, size), 1 km under the camera, its shell held off the far plane as a planet's is: red
  const world = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 64), new THREE.ShaderMaterial({vertexShader: CLAMP, fragmentShader: "void main() { gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0); }"}));
  space.add(world, {at: [0, 0, -1.001e6], size: 1e6});
  // a 4.4 km bar along the view whose bounding sphere holds the camera (a hull beside it): blue
  space.add(new THREE.Mesh(new THREE.BoxGeometry(4400, 20, 20), new THREE.MeshBasicMaterial({color: 0x2040ff})), {at: [2000, -30, -300]});
  // a small box in front of it, drawn without frustum culling (lamps, plumes): green
  const lamp = new THREE.Mesh(new THREE.BoxGeometry(3, 3, 3), new THREE.MeshBasicMaterial({color: 0x00ff00}));
  lamp.frustumCulled = false; space.add(lamp, {at: [60, 0, -9]});
}
export function frame(t) { space.update(t, {from: [0, 0, 0], to: [1e4, 0, -1500], up: [0, 0, 1]}); renderer.render(scene, space.camera); }
"""


@pytest.mark.slow
@pytest.mark.render
def test_a_world_added_by_hand_a_near_hull_and_unculled_things_keep_their_order_in_chromium(tmp_path: Path) -> None:
    """Step 393: a world added with ``at`` and ``size`` gets the depth it really starts at, a slice draws only what
    its depth reaches (the world's held-off shell never covers the bar's far part), and a thing drawn without
    frustum culling but with a renderOrder of 0 is in the world, not the sky."""
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "traps.js").write_text(TRAPS, encoding="utf-8")
    with WebPage(tmp_path, WebEntry("script", "traps.js"), scene_id="s", size=(320, 180), fps=10, frames=1, data={}) as page:
        px = page.frame(0)[..., :3].astype(int)
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    blue, green, red = int(((b > 150) & (r < 120)).sum()), int(((g > 150) & (r < 100) & (b < 100)).sum()), int(((r > 150) & (g < 60)).sum())
    assert red > 5000 and green > 20                         # the world under the horizon, the box in front of the bar
    # the bar recedes to its far end at 4.2 km: blue on rows down to its vanishing end, not cut off where its nearer slice ends
    rows = np.nonzero(((b > 150) & (r < 120)).any(axis=1))[0]
    assert blue > 400 and rows.max() - rows.min() > 40, (blue, rows.min(), rows.max())
