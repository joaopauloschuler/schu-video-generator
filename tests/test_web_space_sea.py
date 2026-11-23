"""Water to the horizon, ``vidgen/space-sea`` (Step 382, DESIGN.md §123.4): the module is served by its
import name and imports only ``three``, ``vidgen/baked`` and ``vidgen/space-air``; its parts are registered
under the kind ``sea``; in Node (when it is installed): the horizon's dip and distance against the
formula, Fresnel's limits, the wind's statistics, sea states and waters with a did-you-mean, the waves
from a seed (the same twice, deep-water speeds, the stated height), the height and slope lookup; in
Chromium (``slow``): the glitter lies towards the sun, the horizon's row is where the formula says from
50 m to 100 km, the sea at dusk is not black, the picture's own waves are the lookup's, a frame drawn
twice is the same, and the picture is the same baked, from the cache and without the cache."""

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
MODULE = MODULES / "space-sea.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
PART_NAMES = {"sea-calm", "sea-breeze", "sea-rough", "sea-storm", "sea-sunset", "sea-dusk", "sea-from-20-km", "sea-methane"}
EARTH = 6.371e6


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-sea"] == "space-sea.js"
    assert IMPORT_MAP["imports"]["vidgen/space-sea"] == "/__vidgen__/modules/space-sea.js"
    assert vidgen_file("modules/space-sea.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-sea.js"])["__vidgen__/modules/space-sea.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/baked", "vidgen/space-air", "vidgen/space-clouds"]   # the endless noise (Step 396)
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-sea" not in engine_id()


def test_the_parts_are_registered_under_their_own_kind() -> None:
    assert "sea" in P.KINDS and P.KINDS.index("sea") == P.KINDS.index("air") + 1
    found = {p.name: p for p in P.read_parts() if p.file == "space-sea.js"}
    assert set(found) == PART_NAMES
    assert all(p.module == "vidgen/space-sea" and p.kind == "sea" for p in found.values())
    assert "sea(renderer, sky" in found["sea-calm"].use and "water.update(t, {camera})" in found["sea-calm"].use
    assert "invented" in found["sea-methane"].label and "a look" in found["sea-methane"].label      # what is not a real sea is said on the sheet
    assert [p.name for p in P.select_parts(P.read_parts(), kind="sea")] == [p.name for p in P.read_parts() if p.file == "space-sea.js"]
    assert "Math.random" not in (P.PARTS_DIR / "space-sea.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``S`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "baked", "space-bodies", "space-air", "space-clouds", "space-sea")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as S from 'vidgen/space-sea';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_the_horizon_the_mirror_and_the_wind(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push([50, 2000, 20000, 100000].map((h) => [S.horizonDip(6.371e6, h), S.horizonDistance(6.371e6, h)]));
out.push([S.horizonDip(3.39e6, 2000), S.horizonDistance(3.39e6, 2000), S.horizonDip(6.371e6, 0), S.horizonDistance(6.371e6, -5)]);
out.push([1, 0.8, 0.5, 0.2, 0.05, 0].map((c) => S.fresnel(c)));
out.push([S.fresnel(1, 1.27), S.fresnel(1, 2), S.fresnel(0, 1.27)]);
out.push([S.slopeVariance(0), S.slopeVariance(10), S.whitecaps(1.5), S.whitecaps(6), S.whitecaps(13), S.whitecaps(22), S.whitecaps(60), S.whitecaps(22, 0), S.FOAM_MOST]);
out.push(Object.keys(S.STATES).map((n) => { const s = S.seaState(n); return [n, s.wind, s.height, s.length, s.cover, s.slopes, s.period]; }));
out.push([err(() => S.seaState("breze")), err(() => S.seaState("breeze", {wnd: 3})), err(() => S.seaState({height: 5, length: 20})), err(() => S.seaState("calm", {swell: {heigth: 1}})),
  err(() => S.waterOf("ocaen")), err(() => S.waterOf({color: [1, 2, 3]})), err(() => S.sea(null)), err(() => S.seaState("breeze", {wind: -1}))]);
out.push([S.seaState("breeze", {wind: 10}).height, S.seaState({wind: 10}).height, S.seaState("breeze", {gravity: 1.35, wind: 3}).length, S.waterOf("methane").index, S.waterOf("ocean", {glow: 2}).glow,
  Object.isFrozen(S.seaState("calm")), Object.keys(S.WATERS)]);
""")
    for (dip, far), h in zip(out[0], (50, 2000, 20000, 100000)):
        assert dip == pytest.approx(math.degrees(math.acos(EARTH / (EARTH + h))), rel=1e-9) and far == pytest.approx(math.sqrt(2 * EARTH * h + h * h), rel=1e-12)
    assert out[0][0][0] == pytest.approx(0.227, abs=0.001) and out[0][3][0] == pytest.approx(10.09, abs=0.01) and out[0][3][1] == pytest.approx(1.1332e6, rel=1e-3)
    assert out[1][0] > out[0][1][0] and out[1][1] < out[0][1][1] and out[1][2] == 0 and out[1][3] == 0          # a smaller world: a nearer, lower horizon
    mirror = out[2]
    assert mirror[0] == pytest.approx(((1.34 - 1) / (1.34 + 1)) ** 2, rel=1e-9) and mirror[-1] == pytest.approx(1.0, abs=1e-12)
    assert all(a < b for a, b in zip(mirror, mirror[1:])) and mirror[1] < 0.03 and mirror[2] < 0.07 and mirror[4] > 0.5                # little head-on, most at a grazing look
    assert out[3][0] == pytest.approx((0.27 / 2.27) ** 2, rel=1e-9) and out[3][1] == pytest.approx(1 / 9, rel=1e-9) and out[3][2] == pytest.approx(1.0)
    calm_slopes, windy, c1, c6, c13, c22, c60, none, most = out[4]
    assert calm_slopes == pytest.approx(0.003) and windy == pytest.approx(0.0542) and c1 < 1e-4 < c6 < 0.005 < c13 < c22 <= most and c60 == most and none == 0
    states = {row[0]: row[1:] for row in out[5]}
    assert list(states) == ["calm", "breeze", "swell", "rough", "storm"]
    assert states["breeze"][1] == pytest.approx(0.21 * 36 / 9.81, rel=1e-6) and states["breeze"][2] == pytest.approx(8.17 * 36 / 9.81, rel=1e-6)   # a fully developed sea from the wind
    assert states["calm"][3] < 1e-4 and states["storm"][3] > 20 * states["breeze"][3]                              # foam only when it blows
    assert all(row[1] / row[2] <= 0.1 for row in states.values()) and states["storm"][5] == pytest.approx(math.sqrt(2 * math.pi * 170 / 9.81), rel=1e-6)
    wrong = out[6]
    assert 'did you mean "breeze"' in wrong[0] and 'did you mean "wind"' in wrong[1] and "would break" in wrong[2] and 'did you mean "height"' in wrong[3]
    assert 'did you mean "ocean"' in wrong[4] and "0 to 1" in wrong[5] and "THREE.WebGLRenderer" in wrong[6] and "wind (m/s)" in wrong[7]
    assert out[7][0] == pytest.approx(out[7][1]) and out[7][0] == pytest.approx(0.21 * 100 / 9.81, rel=1e-6) and out[7][2] == pytest.approx(8.17 * 9 / 1.35, rel=1e-6)
    assert out[7][3] == 1.27 and out[7][4] == 2 and out[7][5] is True and out[7][6] == ["ocean", "green", "tropical", "grey", "methane"]


def test_the_waves_come_from_the_seed_and_the_lookup_is_their_sum(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const a = S.waveList("breeze", {seed: 3}), b = S.waveList("breeze", {seed: 3}), c = S.waveList("breeze", {seed: 4});
out.push([JSON.stringify(a) === JSON.stringify(b), JSON.stringify(a) === JSON.stringify(c), a.waves.length, a.lifted, a.gusts.length, a.bends.length, Object.isFrozen(a.waves[0])]);
out.push(a.waves.map((w) => [w.length, w.amplitude, w.omega * w.omega / w.k, Math.hypot(w.kx, w.kz) / w.k, w.sharp, w.ruffled, w.swell ? 1 : 0]));
// the height's spread against the stated significant height, by sea state
out.push(Object.keys(S.STATES).map((n) => { const l = S.waveList(n, {seed: 7}); let sq = 0, sum = 0; const N = 6000;
  for (let i = 0; i < N; i++) { const h = S.heightAt(l, (i * 137.7) % 9000, (i * 291.3) % 7000, i * 0.37); sq += h * h; sum += h; }
  const swell = l.state.swell ? l.state.swell.height : 0; return [n, 4 * Math.sqrt(sq / N), Math.hypot(l.state.height, swell), sum / N]; }));
// the slopes are the height's own (central differences), the normal is their unit vector, time moves the water
const l = S.waveList("rough", {seed: 5}), e = 1e-3, rows = [];
for (const [x, z, t] of [[0, 0, 0], [13.7, -220.4, 3.1], [5000.5, 812.25, 77.7], [-90000.2, 40000.9, 1234.5]]) {
  const [h, sx, sz] = S.surfaceAt(l, x, z, t), n = S.normalAt(l, x, z, t);
  rows.push([h, sx, (S.heightAt(l, x + e, z, t) - S.heightAt(l, x - e, z, t)) / 2 / e, sz, (S.heightAt(l, x, z + e, t) - S.heightAt(l, x, z - e, t)) / 2 / e, n, S.heightAt(l, x, z, t), S.heightAt(l, x, z, t + 0.5), S.gustAt(l, x, z, t)]);
}
out.push(rows);
out.push([S.waveList("breeze", {seed: 3, count: 16}).waves.length, S.waveList("calm", {seed: 1}).waves.filter((w) => w.swell).length, S.waveList("storm", {seed: 1}).waves.filter((w) => w.swell).length,
  err(() => S.waveList("breeze", {seed: -1})), err(() => S.waveList("breeze", {count: 500})), S.DETAIL, S.QUALITIES]);
// one wave alone travels at the deep-water speed: the crest at x = 0, t = 0 is at x = c t a moment later
const one = {...S.waveList({wind: 5, swell: null}, {seed: 2})}, w = {...one.waves[0], kx: one.waves[0].k, kz: 0, phase: 0, sharp: 0, ruffled: 0};
const alone = {...one, waves: [w], bends: [], gusts: one.gusts}, speed = Math.sqrt(9.81 / w.k);
out.push([S.heightAt(alone, 0, 0, 0), w.amplitude, S.heightAt(alone, speed * 2.5, 0, 2.5), S.heightAt(alone, w.length / 2, 0, 0)]);
// no warp of the whole pattern (it drew rings and whorls): each wave wanders by its own shares, and its crests turn by little
out.push(Object.keys(S.STATES).map((n) => { const l = S.waveList(n, {seed: 3});
  return [Math.max(...l.waves.map((v) => l.bends.reduce((sum, b, j) => sum + Math.abs(v.wobble[j]) * Math.hypot(b.kx, b.kz), 0) / v.k)),
    new Set(l.waves.map((v) => v.wobble.map((m) => Math.sign(m)).join())).size, Math.max(...l.waves.map((v) => Math.max(...v.wobble.map(Math.abs))))]; }));
""")
    same, other, count, lifted, gusts, bends, frozen = out[0]
    assert same is True and other is False and count == 32 and 1 <= lifted <= 10 and gusts == 6 and bends == 3 and frozen is True
    waves = np.array(out[1])
    assert np.all(np.diff(waves[:, 0]) < 0) and np.allclose(waves[:, 2], 9.81) and np.allclose(waves[:, 3], 1)       # the longest first; deep water: omega^2 = g k
    assert waves[:, 0].max() / waves[:, 0].min() > 100 and waves[:, 6].sum() == 6 and np.all(waves[:, 4] <= 0.2)    # several scales, a swell beside the wind sea
    assert np.all(waves[waves[:, 6] == 1, 5] == 0) and waves[-1, 5] == 1 and waves[0, 5] == 0                       # gusts ruffle the short waves only
    for name, spread, stated, mean in out[2]:
        assert spread == pytest.approx(stated, rel=0.3) and abs(mean) < 0.12 * stated, name                           # four standard deviations: the significant height
    for h, sx, dx, sz, dz, normal, again, later, gust in out[3]:
        assert sx == pytest.approx(dx, abs=0.01) and sz == pytest.approx(dz, abs=0.01) and h == again and h != later and gust >= 0.2
        length = math.hypot(sx, 1, sz)
        assert normal == pytest.approx([-sx / length, 1 / length, -sz / length], abs=1e-12)
    assert max(abs(row[1]) + abs(row[3]) for row in out[3]) > 0.02
    assert out[4][0] == 16 and out[4][1] == 6 and out[4][2] == 0 and "seed" in out[4][3] and "count" in out[4][4]
    assert out[4][5] == {"fast": [16, 6, 16, 1], "standard": [32, 10, 8, 2], "fine": [48, 14, 4, 2]} and out[4][6] == ["fast", "standard", "fine"]
    crest, amplitude, moved, trough = out[5]
    assert crest == pytest.approx(amplitude) and moved == pytest.approx(amplitude, rel=1e-9) and trough == pytest.approx(-amplitude, rel=1e-9)
    for turn, kinds, most in out[6]:     # the crests turn by under 3 x WOBBLE / WOBBLE_SPAN radians, the waves wander apart
        assert turn <= 3 * 1.4 / 8 + 1e-9 and kinds >= 5 and 0.5 < most <= 1.4



@pytest.mark.slow
def test_the_short_waves_do_not_weave_and_the_gusts_do_not_repeat(tmp_path: Path) -> None:
    """Step 396: the short waves' phases are warped by endless noise and the gusts are endless noise (no lattice of sines)."""
    out = _run_in_node(tmp_path, """
const corr = (a, b) => { const n = a.length, ma = a.reduce((s, x) => s + x, 0) / n, mb = b.reduce((s, x) => s + x, 0) / n;
  let ab = 0, aa = 0, bb = 0; for (let i = 0; i < n; i++) { const da = a[i] - ma, db = b[i] - mb; ab += da * db; aa += da * da; bb += db * db; } return ab / Math.sqrt(aa * bb); };
// the largest correlation after it first fell under zero, along a direction, over lags (a lattice comes back to itself)
const back = (f, dir, lags, step) => { let fell = false, best = -1;
  for (const lag of lags) { const a = [], b = [];
    for (let l = 0; l < 12; l++) for (let i = 0; i < 160; i++) { const x = 37.1 * l + i * step * dir[0], z = 91.7 * l + i * step * dir[1]; a.push(f(x, z)); b.push(f(x + lag * dir[0], z + lag * dir[1])); }
    const c = corr(a, b); if (c < 0) fell = true; else if (fell) best = Math.max(best, c); }
  return best; };
const l = S.waveList("rough", {seed: 3}), cut = l.state.length / 8, d = [Math.sin(l.state.direction * Math.PI / 180), -Math.cos(l.state.direction * Math.PI / 180)];
const short = {...l, waves: l.waves.filter((w) => w.length < cut)}, flat = {...short, warps: []};
const along = (list) => (x, z) => { const s = S.surfaceAt(list, x, z, 1); return s[1] * d[0] + s[2] * d[1]; };
const lags = Array.from({length: 24}, (_, i) => cut / 16 * (i + 1));
out.push([back(along(flat), d, lags, cut / 28), back(along(short), d, lags, cut / 28)]);
out.push([l.warps.length, l.warps.map((f) => f.size), l.waves.map((w) => [w.ruffled, w.band]), S.FINE_WARP]);
const g = S.waveList("breeze", {seed: 3}), gl = Array.from({length: 16}, (_, i) => 250 * (i + 1));
out.push([[[1, 0], [0, 1], [0.7071, 0.7071]].map((dir) => back((x, z) => S.gustAt(g, x, z, 0), dir, gl, 97)), g.gusts.map((q) => q.size)]);
""")
    flat, warped = out[0]
    assert flat > 0.3 and warped < 0.15                       # the unwarped short waves come back to themselves (a weave); warped, they do not
    count, sizes, waves, warp = out[1]
    assert count == warp["fields"] == 3 and sizes == pytest.approx([warp["size"] * 80 / 8 / warp["ratio"] ** j for j in range(3)])
    assert all(0 <= band <= 2 for _, band in waves) and any(r > 0 for r, _ in waves) and waves[0][0] == 0   # the long waves keep their crests (no share)
    returns, gust_sizes = out[2]
    assert all(r < 0.15 for r in returns) and len(gust_sizes) == 6 and gust_sizes[0] > gust_sizes[-1]       # the gusts' patches never come back in rows


PAGE = """
import * as THREE from "three";
import {air, sunDirection} from "vidgen/space-air";
import {sea} from "vidgen/space-sea";
let renderer, scene, camera, c, made = [];
// the sea alone into a float target, each pixel its place (metres from the camera along +x and +z) and the water's height there
function numbers(water, sky, width, height) {
  const target = new THREE.WebGLRenderTarget(width, height, {type: THREE.FloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter});
  const background = scene.background, aspect = camera.aspect, px = new Float32Array(width * height * 4);
  scene.background = null; sky.object.visible = false; water.uniforms.uSeaShow.value = 1; renderer.setClearColor(0x000000, 0);
  camera.aspect = width / height; camera.updateProjectionMatrix();
  renderer.setRenderTarget(target); renderer.clear(); renderer.render(scene, camera); renderer.readRenderTargetPixels(target, 0, 0, width, height, px);
  renderer.setRenderTarget(null); camera.aspect = aspect; camera.updateProjectionMatrix();
  scene.background = background; sky.object.visible = true; water.uniforms.uSeaShow.value = 0; target.dispose();
  return (x, row) => { const i = ((height - 1 - row) * width + x) * 4; return [px[i], px[i + 1], px[i + 2], px[i + 3]]; };    // row 0 is the top
}
export function load(ctx) {
  c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  renderer.debug.onShaderError = (gl, program, vs, fs) => { window.shaderError = (gl.getShaderInfoLog(fs) || "") + (gl.getShaderInfoLog(vs) || "") + (gl.getProgramInfoLog(program) || ""); };
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(60, ctx.width / ctx.height, 1, 1e8);
  for (const shot of c.shots) {
    const sky = air(renderer, "earth", {}), water = sea(renderer, sky, {seed: 3, ...(shot.sea ?? {})});
    sky.object.visible = water.object.visible = false; scene.add(sky.object, water.object); made.push([sky, water]);
  }
  window.found = [];
}
export function frame(t, ctx) {
  const n = Math.round(t * ctx.fps), shot = c.shots[n], [sky, water] = made[n], pitch = shot.pitch * Math.PI / 180, turn = (shot.heading ?? 0) * Math.PI / 180, h = shot.height;
  made.forEach(([s, w], i) => { s.object.visible = w.object.visible = i === n; });
  const [x, z] = shot.at ?? [0, 0];
  camera.position.set(x, h, z); camera.lookAt(x + Math.sin(turn) * Math.cos(pitch) * 1000, h + Math.sin(pitch) * 1000, z - Math.cos(turn) * Math.cos(pitch) * 1000); camera.updateMatrixWorld();
  sky.update(t, {camera, sun: sunDirection(shot.elevation, 0)}); water.update(shot.time ?? 2, {camera});
  const out = {horizon: {...water.horizon}};
  if (shot.rows) {          // the first row of the middle column that is water
    const at = numbers(water, sky, 8, shot.rows);
    out.row = Array.from({length: shot.rows}, (_, row) => at(4, row)[3]).findIndex((a) => a > 0.5);
  }
  if (shot.lookup) {        // the picture's own waves against the lookup, at places all over the water
    const at = numbers(water, sky, ctx.width, ctx.height); out.pairs = [];
    for (let row = 30; row < ctx.height; row += 9) for (let col = 8; col < ctx.width; col += 24) {
      const [px, pz, high, a] = at(col, row);
      if (a > 0.5) out.pairs.push([high, water.heightAt(x + px, z + pz), Math.hypot(px, pz), water.pointAt(x + px, z + pz)[1]]);
    }
  }
  window.found[n] = out;
  renderer.setRenderTarget(null); renderer.render(scene, camera);
}
"""
LOW = {"elevation": 25, "pitch": -20, "height": 30}
SHOTS = [
    {**LOW},                                                                            # 0 towards the sun: the glitter
    {**LOW, "heading": 180},                                                            # 1 the same sea, the sun behind
    {**LOW},                                                                            # 2 the first again
    {"elevation": -5, "pitch": -10, "height": 30},                                      # 3 dusk
    {**LOW, "sea": {"state": "storm"}, "heading": 90},                                  # 4 foam
    {"elevation": 30, "pitch": 0, "height": 50, "rows": 720},                           # 5 to 8: where the horizon is
    {"elevation": 30, "pitch": 0, "height": 2000, "rows": 720},
    {"elevation": 30, "pitch": 0, "height": 20000, "rows": 720},
    {"elevation": 30, "pitch": 0, "height": 100000, "rows": 720},
    {"elevation": 30, "pitch": -35, "height": 12, "at": [3700, -5500], "time": 41.25, "lookup": True, "sea": {"state": "rough", "filter": 0.3, "quality": "fine"}},   # 9 the lookup
]


@pytest.mark.slow
@pytest.mark.render
def test_the_sea_draws_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "sea.js").write_text(PAGE, encoding="utf-8")
    store = B.BakedStore(tmp_path / "baked", 10**9)

    def draw(baked: B.BakedStore | bool) -> tuple[list[np.ndarray], list, list]:
        with WebPage(tmp_path, WebEntry("script", "sea.js"), scene_id="s", size=(160, 90), fps=10, frames=len(SHOTS), data={"shots": SHOTS}, baked=baked) as page:
            frames = [page.frame(n)[..., :3].astype(int) for n in range(len(SHOTS))]
            error, found = page._page.evaluate("[window.shaderError ?? null, window.found]")
            assert error is None, error
            return frames, found, sorted({(what, name) for what, name, _ in page.baked_log})

    frames, found, log = draw(False)
    towards, away, again, dusk, storm = frames[:5]
    assert log == []
    assert np.array_equal(towards, again) and not np.array_equal(towards, away)                                     # a frame is a function of its inputs
    assert towards[30:80].mean() > 2.5 * away[30:80].mean() and towards[30:80].max() > 240 and away[30:].max() < 110  # the glitter lies towards the sun
    water = away[30:].mean(axis=(0, 1))
    assert water[2] > 1.5 * water[0] and water[2] > water[1] and away[20:26].mean() < away[40:60].mean() + 80          # blue water under a horizon
    arch, far, near = dusk[20:30].mean(axis=(0, 1)), dusk[35:45].mean(axis=(0, 1)), dusk[60:].mean(axis=(0, 1))
    assert far.sum() > 90 and far[0] > 1.3 * far[2] and far.sum() < arch.sum() and near.sum() > 6 and dusk[45:60].sum(axis=2).mean() > 20                     # at dusk the sea mirrors the arch: not black
    assert (storm[30:].min(axis=2) > 100).mean() > 0.002 and (away[30:].min(axis=2) > 100).mean() == 0               # foam in a storm, none in a breeze
    # the horizon's row is where the formula says, from 50 m to 100 km (a 60 degree lens, 720 rows, a level look)
    for shot, got in zip(SHOTS[5:9], found[5:9]):
        dip = math.acos(EARTH / (EARTH + shot["height"]))
        assert got["horizon"]["dip"] == pytest.approx(math.degrees(dip), rel=1e-9) and got["horizon"]["height"] == pytest.approx(shot["height"], rel=1e-6)
        assert abs(got["row"] + 0.5 - (360 + 360 * math.tan(dip) / math.tan(math.radians(30)))) <= 1.0, (shot["height"], got["row"])
    assert [got["row"] for got in found[5:9]] == sorted({got["row"] for got in found[5:9]})
    # the picture's own waves are the lookup's (a pixel's filter takes a few centimetres of the finest), 6.6 km from the origin
    pairs = np.array(found[9]["pairs"])
    assert len(pairs) > 30 and np.abs(pairs[:, 0] - pairs[:, 1]).max() < 0.08 and pairs[:, 0].std() > 0.25 and np.corrcoef(pairs[:, 0], pairs[:, 1])[0, 1] > 0.995
    # the world is round: 6.6 km from where the sea touches the scene's y = 0 the water lies 3.45 m lower, and the camera is that much higher over it
    drop = (3700**2 + 5500**2) / 2 / EARTH
    assert found[9]["horizon"]["height"] == pytest.approx(12 + drop, abs=0.02) and np.allclose(pairs[:, 3], pairs[:, 1] - drop, atol=0.06)
    # the same pixels with the foam's pattern baked and stored, from the cache, and without the cache
    cold, _, log = draw(store)
    assert log == [("stored", "space-air/psi"), ("stored", "space-sea/lace")]
    warm, _, log = draw(store)
    assert log == [("hit", "space-air/psi"), ("hit", "space-sea/lace")]
    assert all(np.array_equal(a, b) and np.array_equal(a, w) for a, b, w in zip(frames, cold, warm))
