"""The space plane parts, ``vidgen/space-plane`` (Step 386, DESIGN.md §123.8): the module is served by
its import name and builds on ``vidgen/space-craft``; its parts are registered (every ready-made
plane as kind ``craft``, the kit's parts and surfaces as ``craft-part``); in Node (when it is
installed): a wing's outline from its numbers (area, aspect, sweep), every preset, a body's
cross-sections, the nose shapes, mistakes named with a did-you-mean; (``slow``) every ready-made
plane builds from its seed with sizes inside its stated range, the same seed gives the same plane
and another seed another, left and right mirror each other, the "far" detail has far fewer
triangles, the moving surfaces, the gear and the bay doors turn, the surfaces follow a flight's
rates, ``problems()`` names a detached wing, a span inside the body, short gear and a layout too
near a well-known real one, a fleet builds; in Chromium (``slow``): a plane on a flight of
``flight_data`` is drawn in the sun, banked the way it turns (seen from behind: the wing on the
turn's side is the lower one on the screen), and the same frame from a second page is the same
picture (a plane keeps no baked maps: there is no cached and uncached picture to differ)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.scenes import flight_data as fd
from vidgen.web import flights as wf
from vidgen.web import parts as P
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = DATA / "web" / "modules"
MODULE = MODULES / "space-plane.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
KINDS = ["glider", "freighter", "needle", "lifter", "scout", "skiff"]
PLANES = {f"plane-{k}" for k in KINDS} | {"plane-open", "plane-landing", "plane-fleet"}
PLANE_PARTS = {"plane-part-bodies", "plane-part-wings", "plane-part-tails", "plane-part-engines", "plane-part-gear", "plane-surfaces"}
#: Each kind's stated size in metres: (shortest, longest body with its bells), (smallest, widest span).
SIZES = {"glider": ((22, 34), (13, 22)), "freighter": ((56, 80), (28, 51)), "needle": ((60, 82), (21, 34)), "lifter": ((16, 28), (9, 17)), "scout": ((9, 14), (17, 33)), "skiff": ((12, 18), (8.5, 15))}


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-plane"] == "space-plane.js"
    assert IMPORT_MAP["imports"]["vidgen/space-plane"] == "/__vidgen__/modules/space-plane.js"
    assert vidgen_file("modules/space-plane.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-plane.js"])["__vidgen__/modules/space-plane.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/music-time", "vidgen/space-craft"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-plane" not in engine_id()


def test_the_parts_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-plane.js"}
    assert {n for n, p in found.items() if p.kind == "craft"} == PLANES and {n for n, p in found.items() if p.kind == "craft-part"} == PLANE_PARTS
    assert all(p.module == "vidgen/space-plane" for p in found.values())
    assert 'plane("glider", {seed: 1})' in found["plane-glider"].use and "planeFleet(" in found["plane-fleet"].use and "kit.wing({preset:" in found["plane-part-wings"].use
    assert all(len(p.label) <= 106 for p in found.values())                    # (longer labels are cut off on the sheet)
    assert "Math.random" not in (P.PARTS_DIR / "space-plane.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``A`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "space-craft", "space-plane")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as THREE from 'three';\nimport * as A from 'vidgen/space-plane';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const r4 = (x) => Math.round(x * 1e4) / 1e4;\n"
        "const sig = (c) => { let n = 0, s = 0; c.object.traverse((m) => { if (m.isMesh) { const p = m.geometry.attributes.position; n += p.count; for (let i = 0; i < p.count; i += 97) s += p.getX(i) + 2 * p.getY(i) + 3 * p.getZ(i); } }); return [n, r4(s)]; };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=180, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_wings_and_bodies_are_numbers(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, r"""
const w = A.wingPlanform({span: 20, rootChord: 8, tipChord: 2, sweep: 30});
out.push([w.semi, r4(w.area), r4(w.aspect), w.taper, r4(w.sweepAt(0.5)), r4(w.le(1)), r4(w.chord(0)), r4(w.chord(1))]);
// every preset is a wing: a positive chord all along, the span the one given, its area between a sliver's and a square's
out.push(Object.keys(A.WINGS).map((preset) => { const p = A.wingPlanform({preset, span: 16}); return [preset, p.semi === 8, p.area > 4 && p.area < 16 * 16 * 1.3, Array.from({length: 11}, (_, i) => p.chord(i / 10)).every((c) => c >= 0)]; }));
// a double delta: steep inside the crank, shallower outside
const dd = A.wingPlanform({preset: "double-delta", span: 16});
out.push([dd.sweepAt(0.1) > dd.sweepAt(0.8) + 20, r4(dd.sweepAt(0.1)), r4(dd.sweepAt(0.8))]);
// a body: the given length, width and height, a tip of nothing, the same to the left and the right, a flat belly
const b = A.bodyShape({length: 30, width: 4, height: 3, belly: 1, nose: "ogive"});
const l = b.point(0.5, 20), r = b.point(0.5, 160);
out.push([b.length, r4(2 * b.half(0.5)), r4(b.top(0.5) - b.bottom(0.5)), r4(b.half(0)), r4(l[0] + r[0]), r4(l[1] - r[1]), r4(b.point(0, 0)[2]), r4(b.point(1, 0)[2])]);
out.push([r4(b.under(0.5, 0) - b.under(0.5, 1.2)), r4(A.bodyShape({length: 30, width: 4, height: 3, belly: 0}).under(0.5, 0) - A.bodyShape({length: 30, width: 4, height: 3, belly: 0}).under(0.5, 1.2))]);
out.push(A.NOSES.map((n) => [n, A.noseProfile(n, 0) < 1e-6, Math.abs(A.noseProfile(n, 1) - 1) < 1e-6, Array.from({length: 20}, (_, i) => A.noseProfile(n, (i + 1) / 20) - A.noseProfile(n, i / 20)).every((d) => d > 0)]));
const n = b.normal(0.5, 90); out.push([r4(n[0]), r4(n[1]), r4(n[2])]);
// mistakes are named
out.push([err(() => A.wingPlanform({preset: "dleta"})), err(() => A.wingPlanform({spam: 3})), err(() => A.bodyShape({nose: "ogiv"})), err(() => A.wingPlanform({span: 10, rootChord: 1, tipChord: 0.2, sweep: 0, sweepInner: 80, crank: 0.5})),
  err(() => A.planeSpec("glidr")), err(() => A.bodyShape({length: 2})), err(() => A.textMap("a_b"))]);
out.push([A.registration(5), A.registration(5) === A.registration(5), A.registration(5) !== A.registration(6), /^[A-Z]{2}-[1-9][0-9]{2}$/.test(A.registration(77))]);
const c = A.controlsFromRates({bankRate: 10, pitchRate: 2, slowing: 2, bank: 30});
out.push([c.roll, c.elevon, c.rudder, c.brake, A.controlsFromRates({bankRate: 99}).roll, A.controlsFromRates({}).elevon]);
out.push([Object.keys(A.PLANES), Object.keys(A.WINGS), A.FINS, Object.keys(A.SCHEMES)]);
// a description is plain numbers and words, the same for a seed
out.push([JSON.stringify(A.planeSpec("lifter", {seed: 4})) === JSON.stringify(A.planeSpec("lifter", {seed: 4})), JSON.stringify(A.planeSpec("lifter", {seed: 4})) !== JSON.stringify(A.planeSpec("lifter", {seed: 5})),
  A.planeSpec("scout", {seed: 1, wing: {span: 30}}).spec.wing.span, A.planeSpec("scout", {seed: 1, fins: null}).spec.fins]);
""")
    semi, area, aspect, taper, sweep, le, c0, c1 = out[0]
    assert (semi, area, aspect, taper, c0, c1) == (10, 100, 4, 0.25, 8, 2) and abs(sweep - 30) < 1e-3 and abs(le - 10 * np.tan(np.radians(30))) < 1e-3
    assert [p[0] for p in out[1]] == ["delta", "double-delta", "cranked-arrow", "swept", "straight", "ogival", "stub", "blended", "long"] and all(all(p[1:]) for p in out[1])
    assert out[2][0] and abs(out[2][1] - 76) < 0.1 and abs(out[2][2] - 46) < 0.1
    assert out[3] == [30, 4, 3, 0, 0, 0, 15, -15]
    assert abs(out[4][0]) < 0.02 and out[4][1] < -0.05                                 # flat under a flat belly, curved under a round one
    assert [n[0] for n in out[5]] == ["ogive", "blunt", "pointed", "chined", "needle"] and all(all(n[1:]) for n in out[5])
    assert abs(out[6][0]) < 1e-3 and out[6][1] > 0.999
    e = out[7]
    assert 'did you mean "delta"' in e[0] and 'did you mean "span"' in e[1] and 'did you mean "ogive"' in e[2] and "leading edge passes the trailing edge" in e[3]
    assert 'did you mean "glider"' in e[4] and "body length must be a number from 3 to 120" in e[5] and 'cannot show "_"' in e[6]
    assert out[8][1:] == [True, True, True]
    assert out[9] == [9, -6.2, 2.25, 18, 18, 0]
    assert out[10][0] == KINDS and out[10][2] == ["single", "twin", "vee"] and out[10][3] == ["tiles", "grey", "metal", "dark", "paint", "plain"]
    assert out[11] == [True, True, 30, None]


@pytest.mark.slow
def test_every_plane_builds_from_its_seed(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, r"""
for (const kind of Object.keys(A.PLANES)) {
  const rows = [];
  for (let seed = 1; seed <= 5; seed++) {
    const p = A.plane(kind, {seed, detail: seed === 1 ? "near" : "far"}), box = new THREE.Box3().setFromObject(p.root), tips = p.anchors.wingTips;
    rows.push({seed, sig: sig(p), length: p.size.length, span: p.spec.wing.span, tri: p.info.triangles, problems: p.problems(), scheme: p.kit.look.scheme, preset: p.spec.wing.preset,
      mirror: [r4(box.min.x + box.max.x), r4(tips[0].p[0] + tips[1].p[0]), r4(tips[0].p[1] - tips[1].p[1]), r4(tips[0].p[2] - tips[1].p[2])], reach: tips[0].p[0], ground: p.anchors.ground, low: p.anchors.low,
      names: [p.anchors.nozzles.length, p.anchors.gear.length, p.surfaces.length, p.registration]});
  }
  const near = A.plane(kind, {seed: 2}), again = A.plane(kind, {seed: 2});
  out.push({kind, rows, same: JSON.stringify(sig(near)) === JSON.stringify(sig(again)), near: near.info.triangles, radius: near.size.radius});
}
""")
    assert [o["kind"] for o in out] == KINDS
    for o in out:
        (lo, hi), (s0, s1) = SIZES[o["kind"]]
        rows = o["rows"]
        assert all(lo <= r["length"] <= hi and s0 <= r["span"] <= s1 for r in rows), (o["kind"], [(r["length"], r["span"]) for r in rows])
        assert all(r["problems"] == [] for r in rows), (o["kind"], [r["problems"] for r in rows])
        assert o["same"] and len({tuple(r["sig"]) for r in rows[1:]}) == 4 and len({r["names"][3] for r in rows}) == 5       # a seed is a plane; another seed another
        assert all(max(abs(v) for v in r["mirror"]) < 2e-3 for r in rows), (o["kind"], [r["mirror"] for r in rows])      # left and right are mirrored
        assert all(0.3 * r["span"] < r["reach"] < 0.62 * r["span"] for r in rows)                                          # the tips stand where the span says (tip fins lean out a little)
        assert all(r["ground"] < r["low"] - 0.3 for r in rows)                                                           # the wheels reach below the lowest part
        assert all(r["names"][0] >= 1 and r["names"][1] == 3 and r["names"][2] >= 3 for r in rows)
        assert rows[1]["tri"] < 0.45 * o["near"] and 15_000 < o["near"] < 80_000
    assert len({r["scheme"] for o in out for r in o["rows"]}) >= 4 and len({r["preset"] for o in out for r in o["rows"]}) >= 6


@pytest.mark.slow
def test_surfaces_move_and_problems_are_named(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, r"""
const p = A.plane("glider", {seed: 1, detail: "far"});
const angle = (s) => r4(2 * Math.acos(Math.min(1, Math.abs(s.quaternion.w))) * 180 / Math.PI), by = (role, side) => p.surfaces.filter((s) => s.userData.control.role === role && (side === undefined || s.userData.control.side === side));
// where a surface's trailing edge goes: the rotation's effect on a point one metre behind the hinge, in the plane's axes
const edge = (s) => { const v = new THREE.Vector3(0, 0, -1).applyQuaternion(s.quaternion); return r4(v.y); };
p.controls({elevon: 10});
out.push([by("elevon").map(angle), by("elevon").map(edge), by("rudder").map(angle)]);
p.controls({elevon: 0, roll: 12});
out.push([edge(by("elevon", 1)[0]), edge(by("elevon", -1)[0])]);                // a roll to the right: the left one down, the right one up
p.controls({roll: 0, rudder: 15, brake: 30, bodyFlap: 8, flap: 20});
out.push([by("rudder").map(angle), by("brake").map(angle), by("bodyFlap").map(angle), by("flap").map(edge), {...p.deflection}]);
out.push([err(() => p.controls({elevons: 3})), err(() => p.anchor("nozzle")), err(() => p.update(0, {gears: 1}))]);
// gear and bay
const legs = () => p.legs.map((g) => [g.leg.visible, r4(g.leg.rotation.x)]), doors = (gear) => p.doors.filter((d) => !!d.userData.door.gear === gear).map(angle);
p.gear(0); const up = [legs(), doors(true)]; p.gear(1); const down = [legs(), doors(true)]; p.update(0, {gear: 0.5, bay: 1, cabin: 1});
out.push([up, down, p.gearDown, doors(false), p.materials["plane-canopy"].emissiveIntensity, p.bay(0) === p, doors(false)]);
out.push([p.anchor("nose").toArray().map(r4), p.anchor("nozzles").length, p.anchor("leadingEdges").length, p.anchor("leadingEdges")[0].length > 3, p.anchors.nose.p]);
// the surfaces follow a flight's rates: rolling into a right turn while pulling up
const flight = {names: ["P"], fps: 30, place: (o) => o, bank: (n, t) => 0.3 * t, pitch: (n, t) => 0.05 * t, speed: (n, t) => 200 - 3 * t};
p.fly(flight, {flight: "P"}).update(1);
out.push([p.deflection.roll > 5, p.deflection.elevon < -3, p.deflection.brake > 20, r4(p.deflection.roll), r4(A.controlsFromRates({bankRate: 0.3 * 180 / Math.PI, pitchRate: 0.05 * 180 / Math.PI, slowing: 3, bank: 0.3 * 180 / Math.PI}).roll)]);
p.update(1, {auto: false, controls: {roll: 1}}); out.push(p.deflection.roll);
// a plane of one's own from the kit's parts, and what problems() says about a bad one
const kit = A.planeKit({seed: 3, scheme: "grey", scorch: 0.6});
const good = kit.body({length: 24, width: 3.6, nose: "chined", belly: 0.8}), wing = kit.wing({preset: "double-delta", span: 15}); wing.position.set(0, -0.9, 2); good.add(wing);
const fin = kit.fin({type: "twin", height: 3, rootChord: 4, spacing: 2.4}); fin.position.set(0, 1.5, -7); good.add(fin);
const mine = kit.plane(good);
out.push([mine.problems(), r4(mine.size.width), mine.surfaces.length, mine.registration === kit.registration]);
const bad = kit.body({length: 24, width: 3.6}), off = kit.wing({preset: "delta", span: 3}); off.position.set(0, 4, 2); bad.add(off);
const far = kit.wing({preset: "straight", span: 90}); far.position.set(0, 0, -40); bad.add(far);
const g = kit.gear({length: 0.3}); g.position.set(0, 0, 5); bad.add(g);
out.push(kit.plane(bad).problems());
out.push(A.planeFrom({body: {length: 30, width: 5}, wing: {preset: "double-delta", span: 20}, fins: {type: "single"}, engines: {count: 3}}).problems());
out.push(A.planeFrom({body: {length: 30, width: 5}, wing: {preset: "delta", span: 12, at: 0.02}, fins: {type: "twin"}, engines: {count: 2}, nacelles: {mount: "tail", count: 2}, intakes: {count: 2}}).problems());
out.push([err(() => A.plane("glider", {wings: {}})), err(() => A.planeKit({scheme: "tyles"})), err(() => kit.wing({preset: "delta", controls: [{name: "aileron", from: 0.2, to: 0.9}]})), err(() => kit.fin({type: "tripple"})),
  err(() => A.planeFrom({body: {length: 20, width: 3}, nacelles: {mount: "wing"}}))]);
const fleet = A.planeFleet(["glider", "skiff"], {count: 6, seed: 3});
out.push([fleet.planes.length, fleet.planes.map((c) => c.info.kind), new Set(fleet.planes.map((c) => c.registration)).size, fleet.object.children.length, fleet.update(1, {gear: 1}) === fleet]);
""")
    angles, edges, rudders = out[0]
    assert all(9.8 < a <= 10 for a in angles) and len(angles) == 2 and all(e < -0.15 for e in edges) and rudders == [0, 0]                      # elevon +: both trailing edges down
    assert out[1][0] < -0.15 and out[1][1] > 0.15
    rud, brake, flap, flaps, defl = out[2]
    assert all(13 < a < 15.5 for a in rud) and brake == [30, 30] and flap == [8] and all(e < -0.3 for e in flaps) and defl["rudder"] == 15 and defl["elevon"] == 0
    assert 'did you mean "elevon"' in out[3][0] and 'did you mean "nozzles"' in out[3][1] and 'did you mean "gear"' in out[3][2]
    up, down, half, bay_open, cabin, chained, bay_shut = out[4]
    assert all(not v and abs(x) > 1.6 for v, x in up[0]) and all(a == 0 for a in up[1])                       # folded away behind shut doors
    assert all(v and x == 0 for v, x in down[0]) and all(87 < a < 89 for a in down[1])
    assert half == 0.5 and all(111 < a < 113 for a in bay_open) and len(bay_open) == 2 and abs(cabin - 0.4) < 1e-9 and chained and bay_shut == [0, 0]
    nose, nozzles, edges_n, long_edge, nose_p = out[5]
    assert nose == [round(v, 4) for v in nose_p] and nozzles == 2 and edges_n == 2 and long_edge
    assert out[6][:3] == [True, True, True] and out[6][3] == out[6][4] and out[7] == 1
    assert out[8][0] == [] and 14.5 < out[8][1] < 15.3 and out[8][2] >= 4 and out[8][3]
    bad = " | ".join(out[9])
    assert "the wing does not touch the body: its root is 1.8 m above its back" in bad and "hardly leaves the body" in bad and "over three times the body's length" in bad
    assert "stands off the body's tail" in bad and "does not reach below the belly" in bad
    assert len(out[10]) == 1 and "close to a well-known real vehicle" in out[10][0]
    assert len(out[11]) == 1 and "too far forward" in out[11][0]
    e = out[12]
    assert 'did you mean "wing"' in e[0] and 'did you mean "tiles"' in e[1] and "elevon, flap, rudder, canard" in e[2] and 'did you mean "single"' not in e[3] and "single, twin, vee" in e[3] and "need a wing" in e[4]
    assert out[13] == [6, ["glider", "skiff"] * 3, 6, 6, True]


SETTINGS = {"ground": "sea", "at": [-34.5, 20], "flights": [{"name": "Plane", "start": {"x": 0, "z": 0, "height": 3000, "heading": 90, "speed": 120},
            "legs": [{"straight": 1}, {"turn": {"by": 40, "bank": 40}}, {"turn": {"by": -40, "bank": 40}}]}]}
PAGE = """
import * as THREE from "three";
import {plane} from "vidgen/space-plane";
let renderer, scene, camera, ship, f, sun;
export function load(ctx) {
  f = ctx.flight;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false); renderer.shadowMap.enabled = true;
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x203a60);
  camera = new THREE.PerspectiveCamera(40, ctx.width / ctx.height, 1, 1e4);
  sun = new THREE.DirectionalLight(0xffffff, 3); sun.castShadow = true; sun.shadow.mapSize.set(1024, 1024);
  const s = sun.shadow.camera; s.left = s.bottom = -25; s.right = s.top = 25; s.near = 1; s.far = 400; s.updateProjectionMatrix();
  scene.add(sun, sun.target, new THREE.HemisphereLight(0xbcd3ff, 0x404040, 0.6));
  window.made = {error: null, rows: []};
  try {
    ship = plane(ctx.data.kind, {seed: ctx.data.seed}).fly(f, {flight: "Plane"});
    scene.add(ship.object);
    window.made.info = ship.info; window.made.problems = ship.problems();
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
export function frame(t) {
  if (!ship) return;
  ship.update(t);
  const p = ship.object.position, v = new THREE.Vector3(...f.velocity("Plane", t)).setY(0).normalize();
  camera.position.copy(p).addScaledVector(v, -40).add(new THREE.Vector3(0, 14, 0)); camera.lookAt(p); camera.updateMatrixWorld();
  sun.position.copy(p).add(new THREE.Vector3(60, 160, 40)); sun.target.position.copy(p); sun.target.updateMatrixWorld();
  const tips = ship.anchor("wingTips").map((w) => { const s = w.clone().project(camera); return [s.x, s.y]; });
  window.made.rows.push({t, bank: f.bank("Plane", t), tips, roll: ship.deflection.roll, nose: ship.anchor("nose").sub(p).normalize().dot(new THREE.Vector3(...f.velocity("Plane", t)).normalize())});
  renderer.render(scene, camera);
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_a_plane_draws_banked_the_way_it_turns_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "plane.js").write_text(PAGE, encoding="utf-8")
    fps, seconds = 10, 32
    data = fd.make_flight_data(fd.FlightData.model_validate(SETTINGS), fps, fps * seconds, fps * seconds)
    bank = np.frombuffer(__import__("base64").b64decode(data["flights"][0]["bank"]), "<f8")
    right, left = int(np.argmax(bank)), int(np.argmin(bank))
    assert np.degrees(bank[right]) > 25 and np.degrees(bank[left]) < -25 and right < left          # the right turn first, then the left one
    frames = [0, right, left]

    def draw() -> tuple[list[np.ndarray], dict, dict]:
        with WebPage(tmp_path, WebEntry("script", "plane.js"), scene_id="s", size=(320, 180), fps=fps, frames=fps * seconds, data={"kind": "glider", "seed": 1}, orbits=wf.with_flights(None, data)) as page:
            got = [page.frame(n)[..., :3].astype(int) for n in frames]
            made = page._page.evaluate("window.made")
            assert made["error"] is None, made["error"]
            return got, dict(page.loaded), made

    (level, turn_right, turn_left), loaded, made = draw()
    again, _, _ = draw()
    assert {"__vidgen__/modules/space-plane.js", "__vidgen__/modules/space-craft.js", "__vidgen__/modules/music-time.js"} <= set(loaded)
    assert made["problems"] == [] and 20_000 < made["info"]["triangles"] < 45_000
    assert all(np.array_equal(a, b) for a, b in zip((level, turn_right, turn_left), again))             # a second page draws the same pictures
    sky = np.array([32, 58, 96])
    for picture in (level, turn_right, turn_left):
        drawn = np.abs(picture - picture[2, 2]).max(axis=-1) > 12
        assert 1_500 < drawn.sum() < 0.5 * drawn.size and np.abs(picture[2, 2] - sky).max() < 40          # a plane before the sky
        assert (picture.min(axis=-1) > 100).sum() > 40                                                 # its lit back and markings in the sun (a glider is grey or dark by default)
    rows = made["rows"]
    assert all(r["nose"] > 0.98 for r in rows)                                                         # the nose along the flight (less the angle of attack)
    port, starboard = rows[0]["tips"]
    assert port[0] < -0.05 < 0.05 < starboard[0] and abs(port[1] - starboard[1]) < 0.02                 # from behind, level: the left wing on the left
    port, starboard = rows[1]["tips"]
    assert starboard[1] < port[1] - 0.15 and port[0] < starboard[0]                                    # a right turn: the right wing is the lower one
    port, starboard = rows[2]["tips"]
    assert port[1] < starboard[1] - 0.15 and port[0] < starboard[0]                                    # a left turn: the left wing
    assert (np.abs(turn_right - level).max(axis=-1) > 30).sum() > 800 and (np.abs(turn_right - turn_left).max(axis=-1) > 30).sum() > 800
