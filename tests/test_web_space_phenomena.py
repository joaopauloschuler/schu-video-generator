"""Phenomena, ``vidgen/space-phenomena`` (Step 373): the module is served by its
import name and imports only ``three``, ``vidgen/music-time`` and ``vidgen/space-sky``; its parts are
registered with their measured costs; in Node (when it is installed): the bending of light past a
black hole (the weak-field value far out, without end at the shadow), the tables the lensed stars
read, the disc's shift and temperature, a wormhole's light paths, a jump's progress (a pure
function; streaks that overlap from frame to frame), rocks from a seed, their sizes, a belt's lanes,
a comet's tails and activity, and the options' errors with a did-you-mean; in Chromium (``slow``):
a black hole has a dark shadow, a lit disc over and under it, bends the sky inside its lens and
leaves it alone outside, the same frame twice and gas that moves; a wormhole shows the other sky
and a camera passes through; a jump's streaks; rocks lit from one side; a comet's two tails away
from the sun; an aurora on the night side."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.web import parts as P
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = DATA / "web" / "modules"
MODULE = MODULES / "space-phenomena.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
PART_NAMES = {"black-hole", "black-hole-from-above", "einstein-ring", "wormhole", "wormhole-tunnel", "warp-streaks", "warp-tunnel", "asteroid-field", "asteroid-belt", "asteroid",
              "comet", "aurora"}


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-phenomena"] == "space-phenomena.js"
    assert IMPORT_MAP["imports"]["vidgen/space-phenomena"] == "/__vidgen__/modules/space-phenomena.js"
    assert vidgen_file("modules/space-phenomena.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-phenomena.js"])["__vidgen__/modules/space-phenomena.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/music-time", "vidgen/space-sky"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-phenomena" not in engine_id()


def test_the_parts_are_registered_with_their_costs() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-phenomena.js"}
    assert set(found) == PART_NAMES
    assert all(p.module == "vidgen/space-phenomena" and p.kind == "phenomenon" for p in found.values())
    assert "blackHole(renderer, {sky})" in found["black-hole"].use and "passage(camera, progress)" in found["wormhole-tunnel"].use and "progress" in found["warp-streaks"].use
    costed = [n for n, p in found.items() if re.search(r"\+\d(\.\d+)? (to \d(\.\d+)? )?s a frame", p.label)]
    assert len(costed) >= 9                                                    # an agent budgets a film from the sheet
    assert all(len(p.label) <= 102 for p in found.values())                    # (longer labels are cut off on the sheet)
    assert "Math.random" not in (P.PARTS_DIR / "space-phenomena.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``P`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "baked", "space-scale", "space-sky", "space-sky-stars", "space-phenomena")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as THREE from 'three';\nimport * as P from 'vidgen/space-phenomena';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_light_past_a_black_hole(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
out.push(P.SHADOW, [200, 50, 10, 4, 3, 2.7, 2.61].map((b) => P.deflection(b)), P.deflection(P.SHADOW) === Infinity && P.deflection(1) === Infinity);
out.push([3, 6, 12].map((r) => [P.discShift(r, 0), P.discShift(r, 3), P.discShift(r, -3)]), [1, 1.2, 1.36, 2, 4].map(P.discTemperature));
out.push([P.lensRadius(10), P.lensRadius(38), P.lensRadius(200), P.lensRadius(1e6), P.lensRadius(38, 30)]);
// a camera 30 radii out: far from the hole a ray is all but straight; nearer it comes from the far side; inside the shadow it is caught
const th = (b) => Math.asin(b * Math.sqrt(1 - 1 / 30) / 30);
out.push([20, 9, 4, 2.7, 2.5].map((b) => { const p = P.lightPath(30, b); return [p.beta, th(b)]; }));
const t = P.lensTables(30, 20);
out.push([t.betaMax, th(t.top), Array.from(t.first).filter((_, i) => i % 2 === 0), Array.from(t.first).filter((_, i) => i % 2 === 1), Array.from(t.second).filter((_, i) => i % 2 === 0), Array.from(t.second).filter((_, i) => i % 2 === 1)]);
out.push([t.rows, t.columns, t.paths.length, t.paths[0], Math.max(...t.paths), Math.min(...t.paths)]);
const heat = P.heatRamp();
out.push([0, 13, 18, 63].map((i) => Array.from(heat.slice(i * 4, i * 4 + 3))));
""")
    shadow, turns, caught, shifts, temps, lens, paths, tables, grid, heat = got
    assert abs(shadow - 2.598076) < 1e-5 and caught
    # far out the turn is Einstein's 2 rs / b (4 G M / (c^2 b)), a little more with the next term; it grows without end toward the shadow
    assert abs(turns[0] / (2 / 200) - 1) < 0.02 and abs(turns[1] / (2 / 50) - 1) < 0.05 and 0.2 < turns[2] < 0.3
    assert all(a < b for a, b in zip(turns, turns[1:])) and turns[4] > 1.2 and turns[5] > 2.5 and turns[6] > 4
    # the disc's light: at rest in the picture it is only gravity's red shift; the side that comes toward the camera is brighter
    for (still, toward, away), r in zip(shifts, (3, 6, 12)):
        assert abs(still - (1 - 1.5 / r) ** 0.5) < 1e-9 and toward > still > away
    assert shifts[0][1] / shifts[0][2] > shifts[2][1] / shifts[2][2] > 1          # the more the nearer the hole
    assert temps[0] == 0 and abs(temps[2] - 1) < 0.002 and temps[1] < 1 and temps[3] < 1 and temps[4] < temps[3]
    assert lens[0] == 20 and 22 < lens[1] < 23.5 and lens[2] == 52 and lens[3] == 64 and lens[4] == 30
    (far, far_th), (mid, mid_th), (near, _), (grazing, _), (inside, _) = paths
    assert 0 < far < far_th and far_th - far < 0.13 and 0 < mid < mid_th           # outside the ring: the star stands nearer the hole than it looks
    assert near < 0 and grazing < near and inside is None                          # inside it: light from the far side; in the shadow: none
    beta_max, top, first_b, first_gain, second_b, second_gain = tables
    assert abs(beta_max - top) < 1e-6                                              # at the lens's edge the bending is eased out: the sky joins
    assert all(a <= b + 1e-9 for a, b in zip(first_b, first_b[1:])) and all(a >= b - 1e-9 for a, b in zip(second_b, second_b[1:]))
    einstein = (2 * 30) ** 0.5                                                     # the ring's radius for a star straight behind: sqrt(2 D) radii, about
    assert abs(first_b[0] - einstein) < 1.2 and abs(second_b[0] - einstein) < 1.2
    assert first_gain[0] == 24 and abs(first_gain[-1] - 1) < 0.15 and second_gain[0] > 5 and second_gain[128] < 0.01   # bright at the ring, itself far out, the far image faint
    assert min(second_b) > shadow
    assert grid[:3] == [128, 64, 128 * 64] and abs(grid[3] - 1 / 30) < 1e-6 and 0.5 < grid[4] < 1 and grid[5] == 0     # (no path of the table is caught: it starts just outside the shadow)
    red, warm, white, blue = heat
    assert red[0] > 0 and red[0] > 3 * red[1] and warm[0] == 1 and warm[0] > warm[1] > warm[2] and max(white) == 1 and min(white) > 0.8 and blue[2] == 1 and blue[2] > blue[0]


def test_wormhole_paths_and_a_jump(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
out.push([0, 3, -3, 5].map((l) => P.wormholeRadius(l, 3)), P.wormholeRadius(4, 0));
// from 20 mouth radii out: straight in, through the mouth, past its rim, and far past it
const at = (b, half = 0) => P.wormholePath(Math.sqrt(400 - 1) + half, Math.PI - Math.asin(b / 20), {half});
out.push([0, 0.5, 0.9, 0.999].map((b) => at(b)), [1.001, 1.5, 6, 15].map((b) => at(b)), [at(0.5, 0), at(0.5, 5), at(0.5, 20)]);
out.push([0, 0.05, 0.14, 0.3, 0.5, 0.84, 0.9, 0.96, 1].map((p) => P.warpAt(p)), P.WARP_MARKS);
const o = {speed: 2, seconds: 4, fps: 30, shutter: 4};
out.push([0.1, 0.14, 0.5, 0.9].map((p) => [P.warpStreak(p, o), (P.warpAt(p).travel - P.warpAt(p - 1 / 120).travel) * 8]));
out.push(JSON.stringify(P.warpAt(0.37)) === JSON.stringify(P.warpAt(0.37)), P.warpAt(-1).travel, P.warpAt(2).travel === P.warpAt(1).travel);
""")
    radii, flare, through, past, lengths, jump, marks, streaks, pure, before, held = got
    assert radii == [1, 1, 1, pytest.approx(5 ** 0.5)] and flare == pytest.approx(17 ** 0.5)
    assert [p["side"] for p in through] == [-1] * 4 and [p["side"] for p in past] == [1] * 4
    assert abs(through[0]["angle"]) < 1e-9 and all(a["angle"] < b["angle"] for a, b in zip(through, through[1:])) and through[3]["angle"] > 6   # wound up toward the rim
    assert past[0]["angle"] > past[1]["angle"] > past[2]["angle"] > past[3]["angle"]
    assert abs(past[3]["angle"] - (np.pi - np.arcsin(15 / 20))) < 0.03            # far from the mouth the ray is all but straight
    assert lengths[0]["angle"] < lengths[1]["angle"] < lengths[2]["angle"]          # a longer wormhole winds the picture up more
    assert abs((lengths[2]["angle"] - lengths[1]["angle"]) - 0.5 * 30 / (1 - 0.25) ** 0.5) < 0.05   # by b times the length over the cosine, exactly
    speeds, travel = [j["speed"] for j in jump], [j["travel"] for j in jump]
    assert speeds[0] == 0 and speeds[-1] == 0 and speeds[3] == speeds[4] == 1 and 0 < speeds[1] < speeds[2] <= 1
    assert all(a <= b for a, b in zip(travel, travel[1:])) and travel[0] == 0 and 0.7 < travel[-1] < 0.85
    assert jump[2]["flash"] == pytest.approx(1) and jump[0]["flash"] == 0 and jump[4]["flash"] == 0 and 0 < jump[6]["flash"] <= 0.6
    assert jump[4]["tunnel"] == 1 and jump[0]["tunnel"] == 0 and jump[-1]["tunnel"] == 0
    assert jump[0]["sky"] == 1 and jump[4]["sky"] == 0 and jump[-1]["sky"] == 1     # the ordinary sky goes out for the jump and comes back
    assert marks == {"enter": 0.14, "leave": 0.84, "out": 0.96}
    for streak, one_frame in streaks:
        assert streak >= one_frame > 0                         # a streak is as long as the star flew in the last four frames: no gaps between frames
    assert pure and before == 0 and held


def test_rocks_belts_and_comets(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
const dirs = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [-0.6, 0.64, 0.48]];
const a = P.rockShape(7), b = P.rockShape(7), c = P.rockShape(8);
out.push(dirs.map((d) => a(d)), dirs.map((d) => b(d)), dirs.map((d) => c(d)));
const g = P.rockGeometry(7, 2), fine = P.rockGeometry(7, 6, {smooth: true});
out.push([g.getAttribute("position").count, fine.getAttribute("position").count, g.boundingSphere.radius, !!g.getAttribute("color"), !!fine.getAttribute("normal")]);
const sizes = Array.from({length: 1000}, (_, i) => P.rockRadius((i + 0.5) / 1000, 0.15, 9, 1.8));
out.push([Math.min(...sizes), Math.max(...sizes), sizes.filter((r) => r < 0.3).length, sizes.filter((r) => r > 2).length]);
out.push([0, Math.PI / 2, Math.PI].map(P.phaseOfSphere), [0.05, 0.5, 0.3, 0.98].map((x) => P.beltDensity(x, [{at: 0.3, width: 0.02}])));
out.push([1, 0.5, 2, 3.3, 30].map((au) => P.cometActivity(au * 1.496e11)), P.cometActivity(2, 2));
out.push(P.cometFrame([-1, 0, 0], [0, 3, 0]), P.cometFrame([0, 0, 5], [0, 0, -1]));
const rock = P.asteroid({seed: 3, detail: 6});
out.push([rock.object.isMesh, rock.object.castShadow, rock.update(5).object.quaternion.w < 1]);
out.push(err(() => P.asteroid({detal: 3})), err(() => P.blackHole({})), err(() => P.aurora(null)), err(() => P.asteroid({axis: 3})));
out.push(P.QUALITIES, Object.keys(P.HOLE_DEFAULTS), Object.keys(P.COMET_DEFAULTS));
""")
    geometry, sizes, light, comet, frames, rock, errors, qualities, hole_keys, comet_keys = got[3], got[4], got[5:7], got[7:9], got[9:11], got[11], got[12:16], got[16], got[17], got[18]
    first, same, other = got[0], got[1], got[2]
    assert first == same and first != other                                         # a seed is a rock
    for s in first:
        assert 0.25 < float(np.linalg.norm(s["point"])) < 1.7 and 0 <= s["shade"] <= 1
    assert geometry[0] == 180 * 3 and geometry[1] == 980 * 3 and 0.6 < geometry[2] < 1.8 and geometry[3] and geometry[4]
    least, most, small, large = sizes
    assert 0.15 <= least < 0.151 and 5 < most <= 9 and small > 650 and 2 <= large < 30   # many small, few large
    assert light[0] == pytest.approx([1, 1 / np.pi, 0], abs=1e-9)
    edge, clear, lane, outside = light[1]
    assert clear > 0.9 and lane < 0.1 and edge < clear and outside < 0.15
    activity, scaled = comet
    assert activity[0] == pytest.approx(1) and activity[1] == 1.6 and activity[2] == pytest.approx(0.25) and activity[3] == 0 and activity[4] == 0 and scaled == pytest.approx(1)
    assert frames[0]["away"] == pytest.approx([1, 0, 0]) and frames[0]["lag"] == pytest.approx([0, -1, 0])   # tails away from the sun, the dust behind the motion
    away, lag = np.array(frames[1]["away"]), np.array(frames[1]["lag"])
    assert away == pytest.approx([0, 0, -1]) and abs(float(away @ lag)) < 1e-9 and abs(float(np.linalg.norm(lag)) - 1) < 1e-9   # flying straight at the sun: still a frame
    assert rock == [True, True, True]
    assert 'unknown option "detal" (did you mean "detail"?)' in errors[0] and "THREE.WebGLRenderer" in errors[1] and "space-bodies" in errors[2] and "[x, y, z]" in errors[3]
    assert qualities == ["fast", "normal", "fine"] and {"sky", "disc", "tilt", "temperature", "quality"} <= set(hole_keys) and {"space", "body", "unit", "activity"} <= set(comet_keys)


PAGE = """
import * as THREE from "three";
import {planet} from "vidgen/space-bodies";
import {spaceSky} from "vidgen/space-sky";
import * as P from "vidgen/space-phenomena";
let renderer, scene, camera, c, sky, other, made = {}, world;
export function load(ctx) {
  c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  renderer.debug.onShaderError = (gl, program, vs, fs) => { window.shaderError = (gl.getShaderInfoLog(fs) || "") + (gl.getShaderInfoLog(vs) || "") + (gl.getProgramInfoLog(program) || ""); };
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(c.fov ?? 40, ctx.width / ctx.height, 0.01, 5000);
  if (c.sky !== false) { sky = spaceSky(renderer, {seed: 4, size: 256}); scene.add(sky.object); }
  if (c.hole) { made.hole = P.blackHole(renderer, {sky, ...c.hole}); scene.add(made.hole.object); }
  if (c.worm) { other = spaceSky(renderer, {seed: 11, size: 256, look: "rich"}); made.worm = P.wormhole(renderer, {sky, other, ...c.worm}); scene.add(made.worm.object); }
  if (c.warp) { made.warp = P.warp(renderer, {fps: ctx.fps, ...c.warp}); scene.add(made.warp.object); }
  if (c.rocks) { scene.add(new THREE.DirectionalLight(0xffffff, 3).translateX(5)); made.rocks = P.asteroids(renderer, {sun: [1, 0, 0], ...c.rocks}); scene.add(made.rocks.object); }
  if (c.comet) { made.comet = P.comet(renderer, c.comet); scene.add(made.comet.object); }
  if (c.aurora) { world = planet(renderer, "earth", {size: 128, spin: 0, tilt: 0, sun: c.sun}); scene.add(world.object); made.aurora = P.aurora(world, c.aurora); }
  window.made = {};
}
export function frame(t) {
  camera.position.set(...(c.from ?? [0, 0, 8])); camera.lookAt(...(c.to ?? [0, 0, 0])); camera.updateMatrixWorld();
  const tt = t + (c.t0 ?? 0);
  let state = null;
  if (made.hole) made.hole.update(tt);
  if (made.worm && c.progress !== undefined) { state = made.worm.passage(camera, c.progress, {from: c.from}); sky.object.visible = state.side > 0; }
  if (made.warp) state = made.warp.update(tt, {progress: c.progress, camera});
  if (made.rocks) made.rocks.update(tt, {camera});
  if (made.comet) made.comet.update(tt, {sun: c.sun, velocity: c.velocity, activity: c.activity ?? 1});
  if (made.aurora) { world.update(tt); made.aurora.update(tt); }
  renderer.setRenderTarget(null); renderer.render(scene, camera);
  window.made = {error: window.shaderError ?? null, state, lens: made.hole ? made.hole.lens : null, shown: made.rocks ? made.rocks.shown : null, count: made.rocks ? made.rocks.count : null};
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_the_phenomena_draw_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "phenomena.js").write_text(PAGE, encoding="utf-8")

    def draw(data: dict, frames: int = 1) -> tuple[list[np.ndarray], dict, dict]:
        with WebPage(tmp_path, WebEntry("script", "phenomena.js"), scene_id="s", size=(320, 180), fps=10, frames=frames, data=data) as page:
            got = [page.frame(n)[..., :3].astype(int) for n in range(frames)]
            made = page._page.evaluate("window.made")
            assert made["error"] is None, made["error"]
            return got, dict(page.loaded), made

    # a black hole 34 radii away through a 40 degree lens: 7.3 px a radius; the shadow (2.6 radii: 19 px) is black, the disc lit
    view = {"from": [0, 3.2, 34], "to": [0, 0, 0]}
    (hole, later), loaded, made = draw({"hole": {}, **view}, frames=2)
    (again,), _, _ = draw({"hole": {}, **view})
    (ring,), _, _ = draw({"hole": {"disc": False}, **view})
    (plain,), _, _ = draw(view)
    assert {"__vidgen__/modules/space-phenomena.js", "__vidgen__/modules/space-sky.js", "__vidgen__/modules/music-time.js"} <= set(loaded)
    assert np.array_equal(hole, again) and not np.array_equal(hole, later)          # the same frame twice; the gas moves
    assert abs(float(later.sum()) / float(hole.sum()) - 1) < 0.03                   # ... and the disc's light is steady while it does
    assert 20 <= made["lens"] <= 64
    assert ring[80:100, 150:170].max() < 8 and hole[76:84, 154:166].max() < 40      # the shadow
    side = hole[84:96, 215:245].reshape(-1, 3).mean(axis=0)
    assert side[0] > 60 and side[0] > side[1] > side[2]                             # the disc beside it glows orange
    assert hole[58:68, 150:170].mean() > 4 * max(ring[58:68, 150:170].mean(), 1)    # its far side stands over the shadow ...
    assert hole[108:118, 150:170].mean() > 3 * max(ring[108:118, 150:170].mean(), 1)   # ... and shows under it
    left, right = hole[80:100, 60:140].sum(), hole[80:100, 180:260].sum()
    assert max(left, right) > 1.25 * min(left, right)                               # the side whose gas comes toward the camera is brighter
    # the sky is bent inside the lens and untouched outside it (a lens of 12 radii ends 91 px from the middle of this frame)
    (lensed,), _, made = draw({"hole": {"disc": False, "lens": 12}, **view})
    assert made["lens"] == 12 and np.abs(lensed - plain)[60:120, 120:200].mean() > 0.5
    assert np.array_equal(lensed[:, :55], plain[:, :55]) and np.array_equal(lensed[:, -55:], plain[:, -55:])
    # a wormhole: inside the mouth another sky; a camera passes through and comes out under it
    (ball,), _, _ = draw({"worm": {"otherGain": 3}, "from": [0, 0, 14]})                # (the mouth is 18 px across here, its lens of 6 radii ends 117 px out)
    (empty,), _, _ = draw({"from": [0, 0, 14]})
    assert np.abs(ball - empty)[75:105, 145:175].mean() > 2 and np.array_equal(ball[:, :30], empty[:, :30])
    (inside,), _, made = draw({"worm": {"length": 20, "otherGain": 3}, "from": [0, 0, 14], "progress": 0.5})
    assert made["state"]["inside"] and abs(made["state"]["l"]) < 1e-6 and inside.max() > 40 and inside[:, :20].std() > 0   # the wormhole fills the frame
    (_,), _, made = draw({"worm": {"length": 20}, "from": [0, 0, 14], "progress": 0.9})
    assert made["state"]["side"] == -1 and made["state"]["l"] < 0
    # a jump: no streaks before it, long bright ones in it, the light ahead in the middle of the frame
    (rest,), _, made = draw({"sky": False, "warp": {}, "from": [0, 0, 0], "to": [0, 0, -1], "progress": 0})
    assert rest.max() < 4 and made["state"]["speed"] == 0
    (tunnel,), _, made = draw({"sky": False, "warp": {}, "from": [0, 0, 0], "to": [0, 0, -1], "progress": 0.5})
    assert made["state"]["tunnel"] == 1 and tunnel.mean() > 8 and tunnel[80:100, 150:170].mean() > 3 * tunnel[:30, :60].mean()
    blue = tunnel.reshape(-1, 3).mean(axis=0)
    assert blue[2] > blue[0]                                                        # blue ahead
    # rocks: some near enough to be meshes, lit from the right, the same twice
    (rocks,), _, made = draw({"sky": False, "rocks": {"seed": 5}, "from": [0, 0, 0], "to": [0.2, 0.05, -5], "fov": 45})
    (rocks2,), _, _ = draw({"sky": False, "rocks": {"seed": 5}, "from": [0, 0, 0], "to": [0.2, 0.05, -5], "fov": 45})
    assert made["count"] == 3000 and 10 < made["shown"] <= 800 and np.array_equal(rocks, rocks2)
    lit = rocks.mean(axis=-1) > 40
    assert 50 < lit.sum() < 0.3 * lit.size
    # a comet: a blue tail and a yellowish one, both on the side away from the sun
    sight = {"from": [0, 0, 70], "to": [0, 0, 0], "velocity": [0, 1, 0]}
    (comet,), _, _ = draw({"sky": False, "comet": {}, "sun": [-1, 0, 0], **sight})
    (turned,), _, _ = draw({"sky": False, "comet": {}, "sun": [1, 0, 0], **sight})
    assert comet[:, 170:].sum() > 8 * max(comet[:, :150].sum(), 1) and turned[:, :150].sum() > 8 * max(turned[:, 170:].sum(), 1)
    r, g, b = (comet[:, 170:, i] for i in range(3))
    assert ((b > r + 15) & (b > 30)).sum() > 20 and ((r > b + 15) & (r > 30)).sum() > 20
    assert ((r > b + 15) & (r > 30))[95:, :].sum() > 3 * max(((r > b + 15) & (r > 30))[:85, :].sum(), 1)   # the dust lags behind the motion (the comet flies up)
    # an aurora: green light on the night side of the world, none without it
    over = {"sky": False, "sun": [0.5, -0.12, -1], "from": [-0.45, 2.3, 1.35], "to": [0.05, 0.85, 0]}
    (lights,), _, _ = draw({"aurora": {}, **over})
    (dark,), _, _ = draw({"aurora": {"brightness": 0}, **over})
    green = (lights[..., 1] > lights[..., 0] + 20) & (lights[..., 1] > lights[..., 2] + 20)
    assert green.sum() > 60 and ((dark[..., 1] > dark[..., 0] + 20) & (dark[..., 1] > dark[..., 2] + 20)).sum() == 0
