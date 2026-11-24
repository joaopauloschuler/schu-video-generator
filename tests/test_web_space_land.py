"""Ground with relief, ``vidgen/space-land`` (Step 384, DESIGN.md §123.6): the module is served by its import
name and imports only ``three``, ``vidgen/baked``, ``vidgen/space-air`` and ``vidgen/space-bodies``; its parts
are registered under the kind ``land``; in Node (when it is installed): the noise (the same twice, its slope
against a difference), recipes and presets with a did-you-mean, the relief from a seed (terraces are flat
benches, craters and dunes only where the recipe has them), the macro's spline, the horizon's and the maps'
geometry, the place's frame; in Chromium (``slow``): a frame drawn twice is the same, a low sun leaves more of
the ground dark than a high one, snow lies above its line and not below, the maps' cells and the picture's own
places are ``heightAt``'s heights, the horizon's row is where the formula says from 100 m to 100 km, an airless
sky is black, a sea meets the coast, clouds shade the ground and stand behind it, and lava glows after sunset until it is put
out, and the picture is the same with the macro and the height maps baked, from the cache and without the cache."""

from __future__ import annotations

import json
import math
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
MODULE = MODULES / "space-land.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
PART_NAMES = {"land-alpine", "land-alpine-from-30-km", "land-mars", "land-canyon", "land-dunes", "land-snow", "land-volcanic", "land-airless", "land-coast"}
EARTH = 6.371e6


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-land"] == "space-land.js"
    assert IMPORT_MAP["imports"]["vidgen/space-land"] == "/__vidgen__/modules/space-land.js"
    assert vidgen_file("modules/space-land.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-land.js"])["__vidgen__/modules/space-land.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/baked", "vidgen/space-air", "vidgen/space-bodies"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-land" not in engine_id()


def test_the_parts_are_registered_under_their_own_kind() -> None:
    assert "land" in P.KINDS and P.KINDS.index("land") == P.KINDS.index("cloud") + 1
    found = {p.name: p for p in P.read_parts() if p.file == "space-land.js"}
    assert set(found) == PART_NAMES
    assert all(p.module == "vidgen/space-land" and p.kind == "land" for p in found.values())
    assert "land(renderer, sky" in found["land-alpine"].use and "ground.heightAt(x, z)" in found["land-alpine"].use
    assert "invented" in found["land-canyon"].label and "a look" in found["land-volcanic"].label      # what is not a real ground is said on the sheet
    assert [p.name for p in P.select_parts(P.read_parts(), kind="land")] == [p.name for p in P.read_parts() if p.file == "space-land.js"]
    assert "Math.random" not in (P.PARTS_DIR / "space-land.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``L`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "baked", "space-bodies", "space-air", "space-land")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as L from 'vidgen/space-land';\nimport {surfaceSource} from 'vidgen/space-bodies';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_the_noise_the_recipes_and_the_relief(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push([L.hash2(0, 0, 1), L.hash2(-7, 123456, 9), L.hash2(-7, 123456, 9), L.hash2(-7, 123457, 9), L.GRADIENTS.length, L.GRADIENTS.map((g) => Math.hypot(...g))]);
// the noise: the same twice, zero on the lattice, its slope against a difference, within its range
const pts = Array.from({length: 200}, (_, i) => [i * 0.731 - 40.3, i * 1.137 + 3.9]);
out.push(pts.map(([x, z]) => { const a = L.noised(x, z, 5), e = 1e-5; return [a[0], L.noised(x, z, 5)[0], a[1] - (L.noised(x + e, z, 5)[0] - L.noised(x - e, z, 5)[0]) / (2 * e), a[2] - (L.noised(x, z + e, 5)[0] - L.noised(x, z - e, 5)[0]) / (2 * e), L.noised(x, z, 6)[0]]; }));
out.push([L.noised(3, -8, 5)[0], L.bowl(0), L.bowl(1), L.bowl(3)]);
// recipes
const alpine = L.recipeOf("ocean", {}, 13), mars = L.recipeOf("desert", {}, 15);
out.push([Object.keys(L.TYPES), Object.keys(L.PRESETS), alpine.octaves, alpine.slots.length, alpine.slots[3].length, alpine.slots[4].length, alpine.mountains.height, mars.craters.density, alpine.craters.density, alpine.bound,
  err(() => L.recipeOf("gas")), err(() => L.recipeOf("ocean", {mountain: {}})), err(() => L.recipeOf("ocean", {mountains: {hieght: 2}})), err(() => L.recipeOf("ocean", {mountains: {height: -1}})),
  err(() => L.recipeOf("ocean", {mountains: {from: 5, to: 5}})), Object.values(L.PRESETS).every((p) => p.at.length === 2 && typeof p.world === "string")]);
// the relief: a function of the seed and the place; within the stated bound of the macro's height
const flat = L.flatMacro(6.371e6, 1500), field = {macro: flat, recipe: alpine};
const hs = pts.map(([x, z]) => L.heightOf(field, x * 337, z * 291));
out.push([hs, pts.map(([x, z]) => L.heightOf(field, x * 337, z * 291)), pts.map(([x, z]) => L.heightOf({macro: flat, recipe: L.recipeOf("ocean", {}, 14)}, x * 337, z * 291))]);
out.push([L.macroAt(flat, 123, -456), L.normalOf(field, 1000, 2000), L.heightOf(field, 1e6, -2e6) === L.heightOf(field, 1e6, -2e6)]);
// terraces: the mountains' heights gather on the benches; with none they do not
const mesa = (strength) => { const r = L.recipeOf("desert", {mountains: {height: 2000, base: 1, mid: 0, patch: 0}, rough: {height: 0}, craters: {density: 0}, strata: {step: 400, strength, soft: 0.04, from: -1e6, to: -1e6 + 1}}, 3);
  return pts.map(([x, z]) => { const h = L.reliefAt(r, 0, x * 911, z * 877) / 400; return Math.abs(h - Math.round(h)); }).filter((d) => d < 0.03).length; };
out.push([mesa(1), mesa(0)]);
// craters and dunes only where the recipe has them
const plain = (more) => L.recipeOf("rocky", {mountains: {height: 0}, rough: {height: 0}, craters: {density: 0}, ...more}, 7);
const span = (r) => { const v = pts.map(([x, z]) => L.reliefAt(r, 0, x * 173, z * 151)); return Math.max(...v) - Math.min(...v); };
out.push([span(plain({})), span(plain({craters: {density: 0.8, largest: 6000}})), span(plain({dunes: {height: 80, length: 500, field: 1}}))]);
// the macro's spline gives a plane back exactly, and holds at the lattice's edge
const n = 8, tilt = {n, spacing: 1000, scale: 2, fields: Float32Array.from({length: n * n * 4}, (_, i) => (i % 4 === 0 ? 0.5 * ((i >> 2) % n) + 0.25 * Math.floor((i >> 2) / n) : 7))};
out.push([L.macroAt(tilt, 0, 0), L.macroAt(tilt, 700, -1300), L.macroAt(tilt, 1e9, 1e9), L.macroAt(tilt, -1e9, -1e9)]);
// geometry
out.push([[100, 5000, 30000, 100000].map((h) => [L.horizonDistance(6.371e6, h), L.horizonDip(6.371e6, h)]), L.rayHeight(6.371e6, 1000, 0, 50000), L.rayHeight(6.371e6, 1000, -1, 400), L.rayHeight(6.371e6, 1000, 1, 400),
  L.mapWidths(6.371e6), L.mapWidths(2e5), L.mapFor(100), L.mapFor(0.4 * 4096), L.mapFor(0.8 * 4096), L.mapMiddle(4096, 1000, -130), L.mapMiddle(8192, 1000, -130), L.WIDTH, L.MAPS, L.FINEST, L.QUALITIES, L.MACRO]);
const f = L.placeFrame([40, -70]), dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2], np = L.placeFrame([89.999, 0]);
out.push([dot(f.up, f.up), dot(f.east, f.east), dot(f.south, f.south), dot(f.up, f.east), dot(f.up, f.south), dot(f.east, f.south), f.up[1], f.south[1], L.vacuum(1.7e6).radius, L.RADII.moon]);
// canyons cut the stated depth into a plateau and leave most of it standing; a volcano is a cone with a crater
const cut = L.recipeOf("desert", {mountains: {height: 0}, rough: {height: 0}, craters: {density: 0}, strata: {strength: 0}, canyons: {depth: 1000, width: 2000, length: 20000}}, 3);
const deep = Array.from({length: 900}, (_, i) => L.reliefAt(cut, 0, (i % 30) * 1300, Math.floor(i / 30) * 1300));
const cone = L.recipeOf("lava", {volcanoes: {height: 3000}}, 3).volcanoes;
out.push([Math.min(...deep), Math.max(...deep), deep.filter((h) => h > -1).length / 900, deep.filter((h) => h < -990).length / 900, L.coneAt(cone, 1.2, 0, 0), L.coneAt(cone, 0.5, 0.17, 0), L.coneAt(cone, cone.crater, 0, 0), L.coneAt(cone, 0, 0, 0),
  err(() => L.recipeOf("lava", {volcanoes: {radius: 9000, spacing: 20000}})), err(() => L.recipeOf("desert", {canyon: {}})), L.PRESETS.canyon.canyons.depth, L.PRESETS.volcanic.volcanoes.height, L.RISER]);
const src = surfaceSource("desert");
out.push([Object.keys(src), src.relief, surfaceSource("gas").relief, /vec4 fields\\(vec3 p\\)/.test(src.fields), /vec4 coarse\\(vec3 p, int which\\)/.test(src.coarse), err(() => surfaceSource("dessert"))]);
""")
    h0, h1, h1b, h2, count, lengths = out[0]
    assert h1 == h1b and h1 != h2 and 0 <= h0 < 2**32 and count == 16 and lengths == pytest.approx([1] * 16)
    for value, again, dx, dz, other in out[1]:
        assert value == again and abs(value) <= 1.05 and abs(dx) < 1e-5 and abs(dz) < 1e-5
    assert np.std([row[0] for row in out[1]]) > 0.2 and [row[0] for row in out[1]] != [row[4] for row in out[1]]
    assert out[2][0] == 0 and out[2][1] == pytest.approx(-0.8 + 0.3 * math.exp(-(8**1.5))) and out[2][2] == pytest.approx(0.3) and abs(out[2][3]) < 1e-6
    types, presets, octaves, slots, first, second, height, craters, none, bound, *errors, places = out[3]
    assert types == ["ocean", "desert", "rocky", "icy", "lava"] and presets == ["alpine", "mars", "canyon", "dunes", "snow", "volcanic", "airless"]
    assert octaves == 11 and slots == 34 and first == 2 * second and height > 1000 and craters > 0 and none == 0 and bound["over"] > bound["under"] > 0 and places
    assert "no ground to stand on" in errors[0] and 'did you mean "mountains"' in errors[1] and 'did you mean "height"' in errors[2] and "0 to 20000" in errors[3] and "must be over" in errors[4]
    heights, again, other = out[4]
    assert heights == again and heights != other and np.ptp(heights) > 1500
    assert min(heights) >= 1500 - bound["under"] and max(heights) <= 1500 + bound["over"]
    macro, normal, same = out[5]
    assert macro == pytest.approx([1500, 0, 0, 0]) and math.hypot(*normal) == pytest.approx(1) and normal[1] > 0.3 and same
    assert out[6][0] > 100 and out[6][1] < 40                                                   # terraces: most of the ground is on a bench
    flat, cratered, dunes = out[7]
    assert flat == 0 and cratered > 100 and 10 < dunes < 120
    middle, off, far, near = out[8]
    assert middle == pytest.approx([2 * (0.5 * 3.5 + 0.25 * 3.5), 7, 7, 7]) and off[0] == pytest.approx(2 * (0.5 * 4.2 + 0.25 * 2.2)) and 10 < far[0] <= 10.5 and 0 <= near[0] < 0.5
    horizons, level, down, up, widths, small, m0, m1, m2, mid, mid2, width, maps, finest, qualities, lattice = out[9]
    for (distance, dip), h in zip(horizons, (100, 5000, 30000, 100000)):
        assert distance == pytest.approx(math.sqrt(h * (2 * EARTH + h))) and dip == pytest.approx(math.degrees(math.acos(EARTH / (EARTH + h))))
    assert level == pytest.approx(1000 + 50000**2 / 2 / EARTH, rel=1e-3) and down == pytest.approx(600) and up == pytest.approx(1400)
    assert widths == [4096 * 2**k for k in range(11)] and len(small) == 7 and m0 == 0 and m1 == pytest.approx(1) and m2 == pytest.approx(2)
    assert mid == [1024, -256] and mid2 == [1024, 0] and (width, maps, finest) == (4096, 11, 16) and set(qualities) == {"fast", "standard", "fine"} and lattice == {"n": 384, "spacing": 1 / 400}
    uu, ee, ss, ue, us, es, up_y, south_y, radius, moon = out[10]
    assert (uu, ee, ss) == pytest.approx((1, 1, 1)) and max(abs(ue), abs(us), abs(es)) < 1e-12 and up_y == pytest.approx(math.sin(math.radians(40))) and south_y < 0 and radius == 1.7e6 and moon == 1.7374e6
    low, top, standing, floor, outside, flank, rim, middle, *errors, canyon, volcano, riser = out[11]
    assert low == pytest.approx(-1000, abs=1) and top == 0 and standing > 0.2 and floor > 0.02 and outside == 0 and 0.25 < flank < 0.4 and middle < rim < 1 and rim - middle == pytest.approx(0.5 * 0.13, rel=0.01)
    assert "volcanoes.spacing" in errors[0] and 'did you mean "canyons"' in errors[1] and canyon > 500 and volcano > 1000 and riser == 0.12
    keys, relief, gas, fields, coarse, error = out[12]
    assert keys == ["noise", "coarse", "fields", "paint", "relief"] and relief and not gas and fields and coarse and 'did you mean "desert"' in error


PAGE = """
import * as THREE from "three";
import {air, sunDirection} from "vidgen/space-air";
import {sea} from "vidgen/space-sea";
import {clouds} from "vidgen/space-clouds";
import {land, vacuum, flatMacro, RADII} from "vidgen/space-land";
let renderer, scene, camera, c, made = [];
// the ground alone into a float target, each pixel its place (metres from the camera along +x and +z) and the ground's height there
function numbers(ground, others, width, height) {
  const target = new THREE.WebGLRenderTarget(width, height, {type: THREE.FloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter});
  const background = scene.background, px = new Float32Array(width * height * 4);
  scene.background = null; others.forEach((o) => { o.visible = false; }); ground.uniforms.uLandShow.value = 1; renderer.setClearColor(0x000000, 0);
  renderer.setRenderTarget(target); renderer.clear(); renderer.render(scene, camera); renderer.readRenderTargetPixels(target, 0, 0, width, height, px);
  renderer.setRenderTarget(null); scene.background = background; others.forEach((o) => { o.visible = true; }); ground.uniforms.uLandShow.value = 0; target.dispose();
  return (x, row) => { const i = ((height - 1 - row) * width + x) * 4; return [px[i], px[i + 1], px[i + 2], px[i + 3]]; };    // row 0 is the top
}
export function load(ctx) {
  c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  renderer.debug.onShaderError = (gl, program, vs, fs) => { window.shaderError = (gl.getShaderInfoLog(fs) || "") + (gl.getShaderInfoLog(vs) || "") + (gl.getProgramInfoLog(program) || ""); };
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(60, ctx.width / ctx.height, 1, 1e8);
  window.found = []; window.errors = [];
  const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };
  const sky0 = air(renderer, "earth", {});
  window.errors = [err(() => land(renderer, sky0, {preset: "alpin"})), err(() => land(renderer, sky0, {})), err(() => land(renderer, sky0, {preset: "alpine", qualty: "fast"})), err(() => land(renderer, {}, {})), err(() => land(renderer, sky0, {world: "jupiter", at: [0, 0]}))];
  sky0.dispose();
}
function make(shot) {
  const sky = air(renderer, shot.air ?? "earth", shot.air === undefined ? {} : shot.extra ?? {});
  const options = shot.flat ? {macro: flatMacro(sky.model.radius, 0), type: "rocky", mountains: {height: 0}, rough: {height: 0}, craters: {density: 0}} : shot.land;
  const ground = land(renderer, shot.vacuum ? air(renderer, vacuum(RADII.moon), {exposure: "camera", ev: 1.3}) : sky, {quality: "fast", ...options});
  const all = [ground.sky.object, ground.object];
  let water = null, weather = null;
  if (shot.sea) { water = sea(renderer, ground.sky, {seed: 3, depth: ground.depth}); all.push(water.object); }
  if (shot.clouds) { weather = clouds(renderer, ground.sky, {seed: 4, quality: "fast", ...shot.clouds, behind: ground.behind}); ground.shadedBy(weather.shade); all.push(weather.object); }
  scene.add(...all);
  return {ground, water, weather, all};
}
export function frame(t, ctx) {
  const n = Math.round(t * ctx.fps), shot = c.shots[n], m = made[shot.as ?? n] ??= make(shot), ground = m.ground, pitch = shot.pitch * Math.PI / 180, turn = (shot.heading ?? 0) * Math.PI / 180;
  made.forEach((o, i) => { if (o) o.all.forEach((x) => { x.visible = o === m; }); });
  const [x, z] = shot.at ?? [0, 0], h = shot.height ?? ground.heightAt(x, z) + shot.over;
  camera.fov = shot.fov ?? 60; camera.updateProjectionMatrix();
  camera.position.set(x, h, z); camera.lookAt(x + Math.sin(turn) * Math.cos(pitch) * 1000, h + Math.sin(pitch) * 1000, z - Math.cos(turn) * Math.cos(pitch) * 1000); camera.updateMatrixWorld();
  ground.sky.update(t, {camera, sun: sunDirection(shot.elevation, shot.azimuth ?? 150)}); ground.update(t, {camera});
  ground.setGlow(shot.glow ?? 1);
  if (m.weather) m.weather.update(3, {camera});
  if (m.water) m.water.update(2, {camera});
  const out = {horizon: {...ground.horizon}, bakes: {...ground.bakes}, maps: ground.maps.length, cells: ground.cells, type: ground.type};
  if (shot.rows) {          // the first row of the middle column that is ground
    const size = renderer.getSize(new THREE.Vector2());
    renderer.setSize(8, shot.rows, false); camera.aspect = 8 / shot.rows; camera.updateProjectionMatrix(); ground.update(t, {camera});
    const at = numbers(ground, m.all.filter((o) => o !== ground.object), 8, shot.rows);
    out.row = Array.from({length: shot.rows}, (_, row) => at(4, row)[3]).findIndex((a) => a > 0.5);
    renderer.setSize(size.x, size.y, false); camera.aspect = size.x / size.y; camera.updateProjectionMatrix(); ground.update(t, {camera});
  }
  if (shot.lookup) {        // the maps' cells and the picture's own places against the lookup
    out.cells = [];
    for (let k = ground.horizon.finest; k < ground.maps.length; k++) { let worst = 0; for (let i = 0; i < 12; i++) { const q = ground.cell(k, (i * 37 + 11) % ground.cells, (i * 91 + 5) % ground.cells); worst = Math.max(worst, Math.abs(q.height - ground.heightAt(q.x, q.z))); } out.cells.push(worst); }
    const at = numbers(ground, m.all.filter((o) => o !== ground.object), ctx.width, ctx.height); out.pairs = [];
    for (let row = 4; row < ctx.height; row += 7) for (let col = 4; col < ctx.width; col += 13) {
      const [px, pz, high, a] = at(col, row);
      if (a > 0.5) out.pairs.push([high, ground.heightAt(x + px, z + pz), Math.hypot(px, pz), ground.above(ground.pointAt(x + px, z + pz))]);
    }
    out.above = [ground.above(camera.position), ground.normalAt(x, z), ground.definition().macro.heights.length, ground.definition().recipe.slots.length];
  }
  window.found[n] = out;
  renderer.setRenderTarget(null); renderer.render(scene, camera);
}
"""
ALPINE = {"land": {"preset": "alpine"}, "over": 2500, "pitch": -12, "heading": 80}
SHOTS = [
    {**ALPINE, "elevation": 7},                                                                                 # 0 a low sun: long shadows
    {**ALPINE, "elevation": 60, "as": 0},                                                                       # 1 the same ground under a high sun
    {**ALPINE, "elevation": 7, "as": 0},                                                                        # 2 the first again
    {**ALPINE, "elevation": 60, "land": {"preset": "alpine", "materials": {"snowLine": -5000}}},                # 3 snow everywhere it can lie
    {**ALPINE, "elevation": 60, "land": {"preset": "alpine", "materials": {"snowLine": 20000}}},                # 4 no snow
    {"land": {"preset": "alpine", "quality": "standard"}, "over": 250, "pitch": -40, "elevation": 40, "at": [5100, -2300], "lookup": True},   # 5 the lookup
    {"flat": True, "height": 100, "pitch": 0, "elevation": 30, "rows": 360, "fov": 40},                         # 6 to 9: where the horizon is
    {"flat": True, "height": 5000, "pitch": 0, "elevation": 30, "rows": 360, "fov": 40, "as": 6},
    {"flat": True, "height": 30000, "pitch": 0, "elevation": 30, "rows": 360, "fov": 40, "as": 6},
    {"flat": True, "height": 100000, "pitch": 0, "elevation": 30, "rows": 360, "fov": 40, "as": 6},
    {"vacuum": True, "land": {"preset": "airless"}, "over": 800, "pitch": -8, "elevation": 12, "heading": 40},  # 10 no air
    {"land": {"world": "earth", "at": [-11.5, -15.2], "mountains": {"from": -300, "to": 500, "base": 0.35, "height": 2600, "length": 9000}}, "sea": True, "at": [6000, 6000], "height": 900, "pitch": -7, "heading": 320, "elevation": 26, "azimuth": 215},   # 11 a coast
    {**ALPINE, "elevation": 40, "over": 3200, "clouds": {"decks": [{"type": "cumulus", "cover": 0.5, "base": 2600, "top": 3900}]}},   # 12 clouds shade it and stand behind it
    {"land": {"preset": "volcanic"}, "air": "thin", "over": 9000, "pitch": -50, "elevation": -8},                 # 13 lava glows after sunset
    {"land": {"preset": "volcanic"}, "air": "thin", "over": 9000, "pitch": -50, "elevation": -8, "as": 13, "glow": 0},   # 14 and not when it is put out
]


def test_the_grounds_shadow_in_the_air_is_kept_in_a_byte(tmp_path: Path) -> None:
    # Step 403: how high over a place the ground's shadow reaches, kept as the square root of a share of the ground's range
    out = _run_in_node(tmp_path, """
out.push([[0, 10, 100, 1000, 3999, 4000, 9000].map((h) => L.shadowKeep(h, 4000)), [0, 10, 100, 1000, 3999].map((h) => L.shadowReach(L.shadowKeep(h, 4000), 4000)),
  [10, 100, 1000].map((h) => L.shadowReach((Math.round(255 * L.shadowKeep(h, 4000)) + 1) / 255, 4000) - L.shadowReach(Math.round(255 * L.shadowKeep(h, 4000)) / 255, 4000)), L.AIR_SHADOW]);
""")
    keep, back, steps, consts = out[0]
    assert keep[0] == 0 and keep[4] < 1 and keep[5] == keep[6] == 1 and keep == sorted(keep)
    assert back == pytest.approx([0, 10, 100, 1000, 3999])
    assert steps[0] < 2 and steps[1] < 5 and steps[2] < 16                                              # a byte keeps it finely near the ground, coarser high up
    assert consts == {"soft": 30, "cells": 1.5}

@pytest.mark.slow
@pytest.mark.render
def test_the_ground_draws_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "land.js").write_text(PAGE, encoding="utf-8")
    store = B.BakedStore(tmp_path / "baked", 10**9)

    def draw(baked: B.BakedStore | bool, shots: list) -> tuple[list[np.ndarray], list, list, list]:
        with WebPage(tmp_path, WebEntry("script", "land.js"), scene_id="s", size=(160, 90), fps=10, frames=len(shots), data={"shots": shots}, baked=baked) as page:
            frames = [page.frame(n)[..., :3].astype(int) for n in range(len(shots))]
            error, found, errors = page._page.evaluate("[window.shaderError ?? null, window.found, window.errors]")
            assert error is None, error
            return frames, found, errors, sorted({(what, name) for what, name, _ in page.baked_log})

    frames, found, errors, log = draw(False, SHOTS)
    assert log == []
    assert 'did you mean "alpine"' in errors[0] and "state the ground" in errors[1] and 'did you mean "quality"' in errors[2] and "the air the ground lies under" in errors[3] and "no ground to stand on" in errors[4]
    low, high, again, white, bare = frames[:5]
    assert np.array_equal(low, again) and not np.array_equal(low, high)                                         # a frame is a function of its inputs
    assert found[0]["maps"] == 11 and found[0]["cells"] == 256 and found[0]["type"] == "ocean" and found[1]["bakes"]["maps"] == found[0]["bakes"]["maps"]
    assert found[1]["bakes"]["shadows"] > found[0]["bakes"]["shadows"]                                          # another sun: the shadows again, not the heights
    ground = slice(45, 90)
    dark = lambda f: (f[ground].sum(axis=2) < 90).mean()  # noqa: E731
    assert dark(low) > 0.04 and dark(high) < 0.01 and high[ground].mean() > 2 * low[ground].mean()    # a low sun leaves the slopes turned from it and the valleys dark
    snowy = lambda f: (f[ground].min(axis=2) > 170).mean()  # noqa: E731
    assert snowy(white) > 0.5 and snowy(bare) < 0.01 and 0.02 < snowy(high) < snowy(white)                       # snow above its line, none below, and not on the steepest faces
    assert white[:20].mean() == pytest.approx(bare[:20].mean(), abs=2)                                          # the sky is the air's own either way
    # the maps hold heightAt's heights (the finest to centimetres, wider ones less of the fine relief), and so does every pixel's own place
    look = found[5]
    assert look["cells"][0] < 2.0 and look["cells"][1] < 5.0 and look["cells"][-1] > 100
    pairs = np.array(look["pairs"])
    close = pairs[pairs[:, 2] < 1200]
    assert len(close) > 40 and np.abs(close[:, 0] - close[:, 1]).max() < 8.0 and np.abs(close[:, 0] - close[:, 1]).mean() < 2.0 and np.corrcoef(pairs[:, 0], pairs[:, 1])[0, 1] > 0.999 and np.ptp(pairs[:, 0]) > 100
    assert np.abs(pairs[:, 3]).max() < 0.05                                                                     # a point of the ground stands on the ground
    above, normal, lattice, slots = look["above"]
    drop = (5100**2 + 2300**2) / 2 / EARTH                                                                      # the world is round: the scene's y = 0 lies that much over the sphere there
    assert above == pytest.approx(250 + drop, abs=0.02) and look["horizon"]["over"] == pytest.approx(250 + drop, abs=0.02) and math.hypot(*normal) == pytest.approx(1) and lattice == 384 * 384 and slots == 34
    # the horizon's row is where the formula says, from 100 m to 100 km (a 40 degree lens, 360 rows, a level look, a smooth world)
    for shot, got in zip(SHOTS[6:10], found[6:10]):
        dip = math.acos(EARTH / (EARTH + shot["height"]))
        assert got["horizon"]["dip"] == pytest.approx(math.degrees(dip), rel=1e-9) and got["horizon"]["height"] == pytest.approx(shot["height"], rel=1e-6)
        assert abs(got["row"] + 0.5 - (180 + 180 * math.tan(dip) / math.tan(math.radians(20)))) <= 1.5, (shot["height"], got["row"])
    assert [got["row"] for got in found[6:10]] == sorted({got["row"] for got in found[6:10]})
    assert found[9]["horizon"]["finest"] > found[6]["horizon"]["finest"] == 0                                   # from high up the finest maps are not baked
    airless = frames[10]
    assert airless[:25].max() < 60 and airless[:25].mean() < 3 and airless[50:].mean() > 25 and np.abs(airless[50:, :, 0] - airless[50:, :, 2]).mean() < 12   # a black sky, grey ground
    coast = frames[11]
    blue = (coast[..., 2] > 1.4 * coast[..., 0]) & (np.arange(90)[:, None] > 40)
    sand = (coast[..., 0] > 1.15 * coast[..., 2]) & (np.arange(90)[:, None] > 40)
    assert 0.05 < blue.mean() < 0.4 and sand.mean() > 0.1                                                       # water and land in one picture
    cloudy = frames[12]
    assert (cloudy[ground].min(axis=2) > 200).mean() > 0.01 and not np.array_equal(cloudy, high)
    glow, out = frames[13], frames[14]
    hot = (glow[..., 0] > 150) & (glow[..., 0] > 2.5 * glow[..., 2])
    assert 0.001 < hot.mean() < 0.2 and ((out[..., 0] > 150) & (out[..., 0] > 2.5 * out[..., 2])).mean() == 0 and glow.mean() > out.mean()
    # the same pixels with the macro baked and stored, from the cache, and without the cache
    cold, _, _, log = draw(store, SHOTS[:1])
    assert ("stored", "space-land/macro") in log and ("stored", "space-land/map") in log
    warm, _, _, log = draw(store, SHOTS[:1])
    assert ("hit", "space-land/macro") in log and ("hit", "space-land/map") in log and ("stored", "space-land/map") not in log
    assert np.array_equal(frames[0], cold[0]) and np.array_equal(frames[0], warm[0])
