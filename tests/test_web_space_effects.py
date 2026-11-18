"""Re-entry and flight effects, ``vidgen/space-effects`` (Step 387, DESIGN.md §123.9): the module is
served by its import name; its parts are registered under the kind ``effect``; in Node (when it is
installed): the glow's colour and brightness rise with the heating and never fall, an exhaust
widens as the air thins and has shock diamonds only in dense air, a vapour cone is there only close
to Mach 1 and wing vapour only in a hard turn, contrails only above their band, a trail's rings are
born at fixed times, a flight is read between frames and before the scene, sparks repeat from the
seed, mistakes are named with a did-you-mean, and a trail's geometry is a function of the time alone
(the same after other frames) whose young rings stay where they were laid; in Chromium (``slow``):
the glow is brighter at a higher heating and on the windward side, a frame drawn after other frames
is the frame drawn first, and a vapour trail's pixels stay where they are while the plane flies on."""

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
from vidgen.web.loaded import VIDGEN_MODULES, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = DATA / "web" / "modules"
MODULE = MODULES / "space-effects.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
PARTS = {"effect-reentry", "effect-reentry-early", "effect-reentry-lander", "effect-reentry-far", "effect-contrails", "effect-exhaust-air", "effect-exhaust-thin", "effect-vapour-cone", "effect-wing-vapour"}


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-effects"] == "space-effects.js"
    assert IMPORT_MAP["imports"]["vidgen/space-effects"] == "/__vidgen__/modules/space-effects.js"
    assert vidgen_file("modules/space-effects.js") == MODULE
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/space-air"]              # it builds on the air, never on a plane's internals
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-effects" not in engine_id()


def test_the_parts_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-effects.js"}
    assert set(found) == PARTS and all(p.kind == "effect" and p.module == "vidgen/space-effects" for p in found.values())
    assert "effects(ship, {flight: ctx.flight, sky, reentry: true})" in found["effect-reentry"].use and "contrails: true" in found["effect-contrails"].use
    assert "Math.random" not in (P.PARTS_DIR / "space-effects.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``E`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    three = tmp_path / "node_modules" / "three"
    three.mkdir(parents=True)
    for name in ("three.module.js", "three.core.js", "addons"):
        (three / name).symlink_to(DATA / "three" / name)
    (three / "package.json").write_text(json.dumps({"name": "three", "type": "module", "exports": {".": "./three.module.js", "./addons/*": "./addons/*"}}), encoding="utf-8")
    ours = tmp_path / "node_modules" / "vidgen"
    ours.mkdir()
    names = ("music-time", "baked", "space-bodies", "space-air", "space-effects")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as THREE from 'three';\nimport * as E from 'vidgen/space-effects';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const r4 = (x) => Math.round(x * 1e4) / 1e4;\n"
        # a flight as ctx.flight gives it: a climbing left turn at 200 m/s, 10 frames a second, flight time = scene time + 3 s
        "function flight(frames = 80, fps = 10) {\n"
        "  const s = {time: new Float64Array(frames), position: new Float64Array(3 * frames), velocity: new Float64Array(3 * frames), quaternion: new Float64Array(4 * frames)};\n"
        "  for (const k of ['heating', 'mach', 'load', 'height', 'above_ground']) s[k] = new Float64Array(frames);\n"
        "  for (let i = 0; i < frames; i++) { const t = i / fps, a = 0.05 * t; s.time[i] = t + 3; s.position.set([4000 * Math.sin(a), 9000 + 20 * t, -4000 * Math.cos(a)], 3 * i); s.velocity.set([200 * Math.cos(a), 20, 200 * Math.sin(a)], 3 * i);\n"
        "    s.quaternion.set(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 2 - a).toArray(), 4 * i); s.heating[i] = 0.1 * t; s.mach[i] = 0.6; s.load[i] = 1.2; s.height[i] = 9000 + 20 * t; s.above_ground[i] = 9000 + 20 * t; }\n"
        "  return {names: ['Plane'], fps, frames, speedup: 1, series: (n) => s};\n}\n"
        "function ship() { const g = new THREE.Group(); g.add(new THREE.Mesh(new THREE.BoxGeometry(8, 2, 20), new THREE.MeshStandardMaterial())); return g; }\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=180, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_the_flights_numbers_become_the_picture(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, r"""
const hs = Array.from({length: 101}, (_, i) => i / 100);
out.push([hs.map(E.heatLevel), hs.map((h) => E.heatColor(h)), E.heatLight(1), E.HEAT_WHITES]);
const airs = [1, 0.5, 0.1, 0.01, 0.0001, 0];
out.push(airs.map((a) => { const p = E.plumeShape(a); return [r4(p.spread), r4(p.diamonds), r4(p.gain)]; }));
out.push([E.plumeShape(1, 1).length > E.plumeShape(1, 0).length, E.plumeShape(1, 1).gain > E.plumeShape(1, 0).gain, E.plumeShape(0.001).spacing > E.plumeShape(1).spacing, E.plumeShape(1).core[2] > E.plumeShape(1).core[0], E.plumeShape(1, 1).core[0] > E.plumeShape(1, 1).core[2], E.plumeShape(1).taper > E.plumeShape(0.001).taper]);
out.push([0.7, 0.93, 0.97, 1.01, 1.1, 1.5].map((m) => r4(E.coneLevel(m, 1))).concat([r4(E.coneLevel(0.97, 0.05))]));
out.push([1, 2, 3.5, 5, 9].map((g) => r4(E.wingVapour(g, 1))).concat([r4(E.wingVapour(9, 0.05))]));
out.push([0, 7999, 8500, 9000, 12000].map((h) => r4(E.contrailLevel(h))).concat([r4(E.airDensity(0)), r4(E.airDensity(8500)), r4(E.airDensity(85000, 8500))]));
// a trail's rings: the head now, the rest at fixed multiples of the step, sparser with age, none older than the life
const step = 1 / 30, a = E.trailTimes(10.013, {life: 60, step, per: 24}), b = E.trailTimes(10.213, {life: 60, step, per: 24});
const multiple = (x, d) => Math.abs(x / d - Math.round(x / d)) < 1e-6;
out.push([a[0], a.length, a.slice(1).every((x) => multiple(x, step)), a.every((x, i) => i === 0 || x < a[i - 1]), a[a.length - 1] >= 10.013 - 60, r4(a[1] - a[2]), r4(a[a.length - 2] - a[a.length - 1]),
  a.slice(1, 12).filter((x) => b.some((y) => Math.abs(x - y) < 1e-9)).length]);
out.push([E.trailRadius(0, E.TRAILS.contrail) < E.trailRadius(10, E.TRAILS.contrail), E.trailRadius(10, E.TRAILS.contrail) < E.trailRadius(60, E.TRAILS.contrail), E.trailAlpha(0, E.TRAILS.contrail), E.trailAlpha(5, E.TRAILS.contrail), E.trailAlpha(70, E.TRAILS.contrail), E.trailAlpha(60, E.TRAILS.contrail) < E.trailAlpha(30, E.TRAILS.contrail)]);
// a flight read between frames and before the scene
const f = flight(), tr = E.tracker(f, "Plane"), k0 = tr.at(3), k1 = tr.at(3.1), mid = tr.at(3.05), before = tr.at(1);
out.push([mid.position.map((p, i) => r4(p - 0.5 * (k0.position[i] + k1.position[i]))), r4(mid.heating), before.position.map((p, i) => r4(p - (k0.position[i] - 2 * k0.velocity[i]))), tr.now(0.31).time, r4(Math.hypot(...mid.quaternion))]);
const s1 = E.sparkAt(7, 1.234, 5), s2 = E.sparkAt(7, 1.234, 5), s3 = E.sparkAt(7, 1.234, 6);
out.push([JSON.stringify(s1) === JSON.stringify(s2), JSON.stringify(s1) !== JSON.stringify(s3), s1.age >= 0 && s1.age < 1, E.hash(3, 4, 5) === E.hash(3, 4, 5), E.flicker(0.37, 2) === E.flicker(0.37, 2)]);
// mistakes are named
out.push([err(() => E.effects(ship(), {reentyr: true})), err(() => E.effects(ship(), {quality: "fats"})), err(() => E.effects(ship(), {reentry: {thicknes: 1}})), err(() => E.effects(ship(), {contrails: {from: "nozles"}})),
  err(() => E.effects(ship(), {flight: f, name: "Plan"})), err(() => E.effects(ship(), {reentry: true}).update(0, {heatng: 1})), err(() => E.effects(ship(), {exhaust: true})), err(() => E.effects(null)), err(() => E.effects(new THREE.Group(), {reentry: true}))]);
// the effects of a craft that is not a plane: the bounding shape from its meshes; a trail is a function of the time alone
const craft = ship(), fx = E.effects(craft, {flight: f, contrails: {always: true}, reentry: true, vapour: true});
const rings = () => { const m = fx.parts.contrails[0].mesh, g = m.geometry, P = g.attributes.position.array, A = g.attributes.aData.array, n = g.drawRange.count / (6 * fx.q.sides) + 1, list = [];
  for (let i = 0; i < n; i++) { const k = i * (fx.q.sides + 1); list.push([A[4 * k + 2], P[3 * k] + m.position.x, P[3 * k + 1] + m.position.y, P[3 * k + 2] + m.position.z, A[4 * k], A[4 * k + 1]]); } return list; };
fx.update(2.0); const first = rings(), heat = fx.state.heat;
fx.update(6.0); fx.update(3.5); const later = rings();
fx.update(2.0); const again = rings();
const same = later.filter((r) => r[0] < 5 - 1e-6 && r[0] > 0).map((r) => { const o = first.find((q) => Math.abs(q[0] - r[0]) < 1e-6); return o ? Math.hypot(o[1] - r[1], o[2] - r[2], o[3] - r[3]) : -1; }).filter((d) => d >= 0);
out.push([fx.shape.radii, JSON.stringify(first) === JSON.stringify(again), first.length, same.length, Math.max(...same), r4(heat), r4(fx.state.heat), fx.parts.skins.length, fx.parts.contrails.length, first[0][5], first[10][5] > 0, first[20][4] > first[2][4]]);
""")
    levels, colours, light, whites = out[0]
    assert levels[0] == 0 and levels[2] == 0 and all(b >= a for a, b in zip(levels, levels[1:])) and abs(levels[-1] - whites) < 1e-9 and levels[40] > 0.1     # brighter with the heating, never dimmer
    assert all(0.5 <= c[0] <= 1 and max(c) == c[0] for c in colours) and colours[30][0] == 1                                                              # the colour: red leads, full from 0.3 on
    green, blue = [c[1] for c in colours], [c[2] for c in colours]
    assert all(b >= a - 1e-12 for a, b in zip(green, green[1:])) and all(b >= a - 1e-12 for a, b in zip(blue, blue[1:]))                                   # red, then orange, then towards white
    assert colours[20][1] < 0.15 and 0.3 < colours[60][1] < 0.5 and colours[100][2] > 0.85 and colours[100][2] > colours[100][1]                            # dull red, orange, a white-pink
    assert light == pytest.approx([c * whites for c in colours[100]])
    spread, diamonds = [p[0] for p in out[1]], [p[1] for p in out[1]]
    assert all(b > a for a, b in zip(spread, spread[1:])) and spread[0] < 0.06 and spread[-1] > 0.55                                                       # the plume widens as the air thins
    assert all(b <= a for a, b in zip(diamonds, diamonds[1:])) and diamonds[0] > 0.5 and diamonds[-1] == 0                                                 # shock diamonds only in dense air
    assert out[2] == [True, True, True, True, True, True]                                       # the afterburner longer and brighter; diamonds further apart in thin air; a blue-white core, orange-yellow with the afterburner; a taper only in dense air
    cone = out[3]
    assert cone[2] == 1 and cone[0] == 0 and cone[4] == 0 and cone[5] == 0 and 0.05 < cone[1] < 0.15 and 0.05 < cone[3] < 0.15 and cone[6] == 0                # a cone only within about 0.04 of Mach 0.97, only in dense air
    assert out[4][:2] == [0, 0] and 0 < out[4][2] < 1 and out[4][3] == 1 and out[4][4] == 1 and out[4][5] == 0
    assert out[5][:5] == [0, 0, 0.5, 1, 1] and out[5][5] == 1 and abs(out[5][6] - 0.3679) < 1e-4 and out[5][7] < 1e-4
    head, count, multiples, falling, inside, young, old, shared = out[6]
    assert head == 10.013 and 100 < count < 260 and multiples and falling and inside and abs(young - 1 / 30) < 1e-4 and old > 20 * young
    assert shared == 11                                                                                                                                  # 0.2 s later the same rings are there
    assert out[7] == [True, True, 0, 1, 0, True]
    between, heating, earlier, now_time, unit = out[8]
    assert max(abs(x) for x in between) < 0.3 and abs(heating - 0.005) < 1e-6 and max(abs(x) for x in earlier) < 1e-3 and abs(now_time - 3.3) < 1e-9 and unit == 1
    assert out[9] == [True, True, True, True, True]
    e = out[10]
    assert 'did you mean "reentry"' in e[0] and 'did you mean "fast"' in e[1] and 'did you mean "thickness"' in e[2] and 'did you mean "nozzles"' in e[3]
    assert 'did you mean "Plane"' in e[4] and 'did you mean "heating"' in e[5] and "no engines of the craft kit" in e[6] and "a craft (anything with an `object`)" in e[7] and "no meshes to measure" in e[8]
    radii, pure, n, matched, moved, heat, heat_again, skins, trails, head_alpha, shown, wider = out[11]
    assert radii == [4, 1.5, 10] or (radii[0] == 4 and radii[2] == 10 and radii[1] >= 1)
    assert pure and n > 50 and matched > 30 and moved < 0.02                                    # the same rings after other frames; young rings stay where they were laid (an old trail snakes slowly)
    assert heat == heat_again and abs(heat - 0.2 / 0.65) < 1e-3 and skins == 1 and trails == 1 and head_alpha == 0 and shown and wider


PAGE = r"""
import * as THREE from "three";
import {air, sunDirection} from "vidgen/space-air";
import {plane} from "vidgen/space-plane";
import {effects} from "vidgen/space-effects";
let renderer, scene, camera, sky, ship, fx, c;
const at = (t) => [240 * t, 10500, 0];
export function load(ctx) {
  c = ctx.data; window.made = {error: null, rows: {}};
  try {
    renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
    renderer.setSize(ctx.width, ctx.height, false); renderer.toneMapping = THREE.ACESFilmicToneMapping;
    scene = new THREE.Scene(); camera = new THREE.PerspectiveCamera(c.fov, ctx.width / ctx.height, 2, 4e6);
    sky = air(renderer, "earth", {sun: sunDirection(c.sun[0], c.sun[1]), scene}); scene.add(sky.object);
    ship = plane("glider", {seed: 1, detail: "far", scheme: "tiles"}); scene.add(ship.object);
    fx = effects(ship, {sky, quality: "fast", ...(c.mode === "trail" ? {contrails: true, path: (tau) => ({position: at(tau), velocity: [240, 0, 0]})} : {reentry: true})}); scene.add(fx.object);
  } catch (e) { window.made.error = String(e.stack || e); }
}
export function frame(t) {
  if (window.made.error) return;
  try {
    const n = Math.round(t * 10), screen = (p) => { const v = new THREE.Vector3(...p).project(camera); return [v.x, v.y]; };
    if (c.mode === "trail") {
      ship.object.position.set(...at(t)); ship.object.rotation.set(0, Math.PI / 2, 0); ship.update(t, {});
      camera.position.set(-300, 9300, 2600); camera.lookAt(-200, 10500, 0); camera.updateMatrixWorld();
      sky.update(t, {camera}); fx.update(t, {velocity: [240, 0, 0], height: 10500});
      window.made.rows[n] = {plane: screen(at(t)), old: [screen(at(-5.5)), screen(at(-3))], rings: fx.parts.contrails[0].mesh.geometry.drawRange.count};
    } else {
      ship.object.position.set(0, 75000, 0); ship.object.rotation.set(0, Math.PI / 2, 0); ship.object.rotateX(-34 * Math.PI / 180); ship.update(t, {});
      camera.position.set(-10, 75002, 60); camera.lookAt(-10, 75000, 0); camera.updateMatrixWorld();
      sky.update(t, {camera}); fx.update(t, {velocity: [6600, 0, 0], height: 75000, heating: c.heating[n]});
      const up = new THREE.Vector3(0, 1, 0).applyQuaternion(ship.object.quaternion), mid = ship.object.position;
      window.made.rows[n] = {windward: screen(mid.clone().addScaledVector(up, -3.2).toArray()), leeward: screen(mid.clone().addScaledVector(up, 5.5).toArray()), heat: fx.state.heat, wind: fx.state.wind, map: fx._wind.draws};
    }
    renderer.render(scene, camera);
  } catch (e) { window.made.error = String(e.stack || e); }
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_the_effects_draw_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "fx.js").write_text(PAGE, encoding="utf-8")
    W, H = 320, 180

    def patch(picture: np.ndarray, point: list[float], half: int = 5) -> np.ndarray:
        x, y = int(round((point[0] + 1) / 2 * W)), int(round((1 - point[1]) / 2 * H))
        return picture[max(y - half, 0):y + half + 1, max(x - half, 0):x + half + 1].astype(float)

    # a re-entry: frames 0..4 at heating 0, 0.5, 1, 0.5, 1; drawn in the order 2, 0, 1, 3, then 2 once more
    heating = [0.0, 0.5, 1.0, 0.5, 1.0]
    with WebPage(tmp_path, WebEntry("script", "fx.js"), scene_id="r", size=(W, H), fps=10, frames=5, data={"mode": "reentry", "fov": 40, "sun": [25, 200], "heating": heating}) as page:
        peak, cold, half, half_later, peak_again = (page.frame(n)[..., :3].astype(int) for n in (2, 0, 1, 3, 2))
        made = page._page.evaluate("window.made")
        assert made["error"] is None, made["error"]
        assert "__vidgen__/modules/space-effects.js" in set(page.loaded)
    rows = made["rows"]
    assert rows["0"]["heat"] == 0 and rows["1"]["heat"] == 0.5 and rows["2"]["heat"] == 1 and rows["2"]["map"] == 1               # the windward map is drawn once for one wind
    assert abs(rows["2"]["wind"][1] + np.sin(np.radians(34))) < 1e-3 and abs(rows["2"]["wind"][2] - np.cos(np.radians(34))) < 1e-3   # the flow meets the belly at the angle of attack
    assert np.array_equal(peak, peak_again)                                                                                        # a frame after other frames is the frame drawn first
    glow_half, glow_peak = (half - cold).clip(0).sum(), (peak - cold).clip(0).sum()
    assert glow_half > 20_000 and glow_peak > 1.5 * glow_half                                                                      # brighter at a higher heating
    assert not np.array_equal(half, half_later)                                                                                    # (it flickers and streams with the time)
    wind, lee = patch(peak - cold, rows["2"]["windward"]).mean(), patch(peak - cold, rows["2"]["leeward"]).mean()
    assert wind > 25 and wind > 3 * max(lee, 1)                                                                                    # the glow is under the belly, not over the back
    assert (peak.max(axis=-1) == 255).mean() < 0.2                                                                                 # and it does not burn the picture out

    # a vapour trail: the plane flies on for 1.5 s; the stretch of trail laid 3 to 5.5 s before frame 0 stays where it is
    with WebPage(tmp_path, WebEntry("script", "fx.js"), scene_id="t", size=(W, H), fps=10, frames=16, data={"mode": "trail", "fov": 30, "sun": [50, 160]}) as page:
        first, last = (page.frame(n)[..., :3].astype(int) for n in (0, 15))
        made = page._page.evaluate("window.made")
        assert made["error"] is None, made["error"]
    a, b = made["rows"]["0"], made["rows"]["15"]
    assert b["plane"][0] - a["plane"][0] > 0.2 and a["rings"] > 0                                                                  # the plane has moved on across the picture
    (x0, y0), (x1, y1) = a["old"]
    px = lambda x, y: (int(round((x + 1) / 2 * W)), int(round((1 - y) / 2 * H)))
    (c0, r0), (c1, r1) = px(x0, y0), px(x1, y1)
    lo, hi, top, bottom = max(min(c0, c1), 0), min(max(c0, c1), W - 1), max(min(r0, r1) - 6, 0), min(max(r0, r1) + 7, H)
    assert hi - lo > 15
    box_first, box_last = first[top:bottom, lo:hi], last[top:bottom, lo:hi]
    sky = np.median(first[:10].reshape(-1, 3), axis=0)
    weight_first, weight_last = np.abs(box_first - sky).max(axis=-1).astype(float), np.abs(box_last - sky).max(axis=-1).astype(float)
    assert (weight_first > 25).sum() > 30                                                                                          # a trail is there, white before the sky
    rows = np.arange(bottom - top)[:, None]
    middle = lambda w: (w * rows).sum(axis=0) / w.sum(axis=0)
    assert np.abs(middle(weight_first) - middle(weight_last)).mean() < 0.6                                                         # and it stays where it was laid: its middle line has not moved
    assert np.abs(box_first - box_last)[weight_first > 25].mean() < 25                                                             # (it only spreads a little)
    ahead = slice(min(px(*a["plane"])[0] + 6, W - 2), min(px(*b["plane"])[0] - 2, W - 1))
    assert np.abs(last[top:bottom, ahead] - first[top:bottom, ahead]).max() > 25                                                   # where the plane flew since, new trail was laid
