"""The hulls of giant ships, ``vidgen/space-hull`` (Step 388): the module is served by
its import name and builds on ``vidgen/space-craft``; its parts are registered (every family, a fleet,
a hull with a small craft beside it as kind ``craft``; the kit's shapes, surfaces and atlas as
``craft-part``); in Node (when it is installed): the atlas is laid without overlap, a bank of bells
fits its field, a cross-section has its recesses, a description is plain numbers and the same for a
seed, mistakes are named with a did-you-mean, the layouts the kit must not make are recognised on
constructed outlines; (``slow``) every family builds for several seeds with the length asked for,
regions, anchors and charts inside its bounds, charts that do not overlap and state their metres per
texel, triangles within the budget and far fewer at "far" detail, the same hull for the same seed;
``problems()`` names a pointed bow with a tower at the stern, buried bells and absurd proportions; a
hull flies a body of orbit data with its bow along the path; a fleet and a size reference build; in
Chromium (``slow``): a 3 km hull in orbit with a 50 m craft beside it draws inside a ``SpaceView``
over a world, in front of the world and with no fighting between its faces, the small craft is where
it was put, and a second page draws the same picture."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.scenes import orbit_data as od
from vidgen.web import parts as P
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = DATA / "web" / "modules"
MODULE = MODULES / "space-hull.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
FAMILIES = ["spine", "carrier", "cluster", "lance", "wheel", "ark", "twin"]
CRAFT = {f"hull-{k}" for k in FAMILIES} | {"hull-burn", "hull-scale", "hull-fleet"}
CRAFT_PARTS = {"hull-part-shapes", "hull-part-drive", "hull-surfaces", "hull-charts"}
#: The most triangles a hull may have at each detail (the stated budget).
BUDGET = {"near": 60_000, "far": 20_000}


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-hull"] == "space-hull.js"
    assert IMPORT_MAP["imports"]["vidgen/space-hull"] == "/__vidgen__/modules/space-hull.js"
    assert vidgen_file("modules/space-hull.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-hull.js"])["__vidgen__/modules/space-hull.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/music-time", "vidgen/space-craft"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-hull" not in engine_id()


def test_the_parts_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-hull.js"}
    assert {n for n, p in found.items() if p.kind == "craft"} == CRAFT and {n for n, p in found.items() if p.kind == "craft-part"} == CRAFT_PARTS
    assert all(p.module == "vidgen/space-hull" for p in found.values())
    assert 'hull("spine", {seed: 1})' in found["hull-spine"].use and "hullFleet(" in found["hull-fleet"].use and "scaleRef(" in found["hull-scale"].use
    assert all(len(p.label) <= 106 for p in found.values())                    # (longer labels are cut off on the sheet)
    assert "Math.random" not in (P.PARTS_DIR / "space-hull.js").read_text(encoding="utf-8")


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
    names = ("music-time", "space-craft", "space-hull")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as THREE from 'three';\nimport * as A from 'vidgen/space-hull';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const r4 = (x) => Math.round(x * 1e4) / 1e4;\n"
        "const sig = (c) => { let n = 0, s = 0; c.object.traverse((m) => { if (m.isMesh) { const p = m.geometry.attributes.position; n += p.count; for (let i = 0; i < p.count; i += 97) s += p.getX(i) + 2 * p.getY(i) + 3 * p.getZ(i); } }); return [n, r4(s)]; };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=240, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_the_numbers_behind_a_hull(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, r"""
// the atlas: charts of very different sizes and weights, none overlapping, each as large as its weight says
const charts = [[900, 300, 1], [300, 900, 1], [40, 40, 2], [5000, 30, 1], [120, 80, 0.5], [60, 200, 1]].map(([w, h, weight]) => ({size: [w, h], weight}));
const scale = A.packCharts(charts);
const over = (a, b) => a.rect[0] < b.rect[2] && b.rect[0] < a.rect[2] && a.rect[1] < b.rect[3] && b.rect[1] < a.rect[3];
out.push([scale > 0, charts.every((c) => c.rect.every((v) => v >= 0 && v <= 1)), charts.some((a, i) => charts.some((b, j) => i < j && over(a, b))), charts.map((c) => c.turned), r4(charts[5].scale / charts[4].scale), charts[3].scale < charts[5].scale && charts[0].scale < charts[5].scale,
  charts.every((c) => Math.abs((c.rect[2] - c.rect[0]) - Math.max(...c.size) * c.scale) < 1e-9 && Math.abs((c.rect[3] - c.rect[1]) - Math.min(...c.size) * c.scale) < 1e-9)]);
// a bank of bells: inside its field, no two through each other
const banks = [A.bankPlan({w: 300, h: 150, count: 6}), A.bankPlan({w: 200, h: 200, count: 5, layout: "ring"}), A.bankPlan({w: 200, h: 200, count: 7, layout: "ring"}), A.bankPlan({w: 400, h: 60, count: 4, layout: "row"}), A.bankPlan({w: 100, h: 100, count: 1})];
const fits = (b, w, h) => b.places.every(([x, y]) => Math.abs(x) + b.radius <= w / 2 + 1e-9 && Math.abs(y) + b.radius <= h / 2 + 1e-9) && b.places.every((p, i) => b.places.every((q, j) => i >= j || Math.hypot(p[0] - q[0], p[1] - q[1]) >= 2 * b.radius - 1e-9));
out.push([fits(banks[0], 300, 150), fits(banks[1], 200, 200), fits(banks[2], 200, 200), fits(banks[3], 400, 60), banks.map((b) => b.places.length), r4(banks[0].length / banks[0].radius), banks[4].places[0]]);
// a cross-section: a trench in the top, a slot in the port side, every edge named
const sec = A.sectionOf(300, 160, 6, {trench: {w: 40, d: 50}, slots: [{side: 1, y0: -40, y1: 20, d: 60}]});
const area = sec.poly.reduce((s, p, i) => { const q = sec.poly[(i + 1) % sec.poly.length]; return s + (p[0] * q[1] - q[0] * p[1]) / 2; }, 0);
out.push([sec.poly.length === sec.tags.length, r4(area), ["wall", "floor", "slot", "back", "top", "bottom", "port", "starboard", "chamfer"].every((t) => sec.tags.includes(t)), A.rect(4, 2).length, A.rect(4, 2, 0.5).length]);
// a description is plain numbers and words, the same for a seed, another for another
const a = A.hullSpec("carrier", {seed: 4}), b = A.hullSpec("carrier", {seed: 4}), c = A.hullSpec("carrier", {seed: 5});
out.push([JSON.stringify(a) === JSON.stringify(b), JSON.stringify(a) !== JSON.stringify(c), A.hullSpec("lance", {seed: 2, length: 4000, shield: 0.2}).length, A.hullSpec("lance", {seed: 2, shield: 0.2}).shield, Object.keys(A.HULLS), Object.keys(A.PALETTES), Object.keys(A.SURFACES).length]);
// a seed keeps a carrier clear of the forbidden layout: a blunt bow, no tower in the aft third
out.push(Array.from({length: 40}, (_, i) => A.hullSpec("carrier", {seed: i + 1})).every((s) => s.taper >= 0.8 && s.towers.every((t) => t.at <= 0.62 && t.high <= 0.5)));
// mistakes are named
out.push([err(() => A.hullSpec("carier")), err(() => A.hullSpec("spine", {gurth: 0.02})), err(() => A.hullSpec("lance", {shieldShape: "dish"})), err(() => A.hullSpec("ark", {length: 50})), err(() => A.hullSpec("cluster", {cells: ["ball", "bal"]})),
  err(() => A.bankPlan({w: 1, h: 1, count: 2, layout: "rnig"})), err(() => A.hullSpec("carrier", {towers: [{at: 0.5, side: 1, len: 0.1, wid: 0.3, hihg: 0.2}]})), err(() => A.hullSpec("wheel", {palette: "bones"}))]);
// the forbidden outlines, on numbers alone: a slab (nothing), a wedge with a tower aft (named), a dagger (named), a stick with a wide bow (nothing)
const outline = (width) => Array.from({length: 40}, (_, k) => ({z: -1950 + k * 100, x: [-width(k / 39) / 2, width(k / 39) / 2], y: [-100, 100]}));
const tower = {name: "tower-1", centre: [0, 200, -1500], box: {min: [-80, 100, -1650], max: [80, 300, -1350]}};
out.push([A.forbidden(outline(() => 600), [tower]).length, A.forbidden(outline((u) => 600 * (1 - 0.6 * Math.max(0, u - 0.3) / 0.7)), [tower]).length, A.forbidden(outline((u) => 600 * (1 - 0.6 * Math.max(0, u - 0.3) / 0.7)), []).length,
  A.forbidden(outline((u) => 600 * (1 - 0.8 * Math.max(0, u - 0.3) / 0.7)), [])[0], A.forbidden(outline((u) => (u > 0.9 ? 900 : 80)), [tower]).length]);
""")
    ok, inside, overlap, turned, ratio, shrunk, sized = out[0]
    assert ok and inside and not overlap and turned == [False, True, False, False, False, True] and abs(ratio - 2) < 1e-6 and shrunk and sized
    assert out[1][:4] == [True, True, True, True] and out[1][4] == [6, 5, 7, 4, 1] and abs(out[1][5] - 3.4) < 1e-9 and out[1][6] == [0, 0]
    assert out[2][0] and abs(out[2][1] - (300 * 160 - 4 * 18 - 40 * 50 - 60 * 60)) < 1e-6 and out[2][2] and out[2][3:] == [4, 8]
    assert out[3][:4] == [True, True, 4000, 0.2] and out[3][4] == FAMILIES and out[3][5] == ["bone", "slate", "iron", "sand", "frost"] and out[3][6] == 12
    assert out[4] is True
    e = out[5]
    assert 'did you mean "carrier"' in e[0] and 'did you mean "girth"' in e[1] and 'did you mean "disc"' in e[2] and "length must be a number from 200 to 20000" in e[3]
    assert 'did you mean "ball"' in e[4] and 'did you mean "ring"' in e[5] and 'did you mean "high"' in e[6] and 'did you mean "bone"' in e[7]
    assert out[6][0] == 0 and out[6][1] == 1 and out[6][2] == 0 and "narrows to a point" in out[6][3] and out[6][4] == 0


@pytest.mark.slow
def test_every_family_builds_from_its_seed(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, r"""
const over = (a, b) => a.rect[0] < b.rect[2] - 1e-9 && b.rect[0] < a.rect[2] - 1e-9 && a.rect[1] < b.rect[3] - 1e-9 && b.rect[1] < a.rect[3] - 1e-9;
for (const family of Object.keys(A.HULLS)) {
  const rows = [];
  for (const seed of [1, 2, 3]) {
    const h = A.hull(family, {seed}), half = [h.size.width / 2, h.size.height / 2, h.size.length / 2], inside = (p, m = 1.02) => p.every((v, i) => Math.abs(v) <= half[i] * m + 1);
    const names = h.regions.map((g) => g.name), pts = Object.values(h.anchors.points);
    // every vertex's place in the atlas lies inside a chart (or in the spare corner), and the charts' texels are the stated size
    let uvOk = true, uvN = 0;
    h.object.traverse((m) => { if (m.isMesh && m.geometry.attributes.uv1) { const u = m.geometry.attributes.uv1; uvN += u.count; for (let i = 0; i < u.count; i += 7) { const x = u.getX(i), y = u.getY(i); if (!(x >= 0 && x <= 1 && y >= 0 && y <= 1)) uvOk = false; } } });
    rows.push({seed, length: h.spec.length, size: h.size, tri: h.info.triangles, sig: sig(h), problems: h.problems(), names, palette: h.spec.palette,
      boxes: h.regions.every((g) => inside(g.box.min) && inside(g.box.max) && g.area > 0 && g.surface.material && g.skin), normals: h.regions.filter((g) => Math.hypot(...g.normal) > 0.5).length,
      anchors: pts.every((a) => inside(a.p, 1.04) && Math.abs(Math.hypot(...a.n) - 1) < 1e-3), bells: h.anchors.bells.length, engines: h.engines.length, hangars: h.anchors.hangars.length, docks: h.anchors.docks.length, lights: h.anchors.lights.length, bridge: !!h.anchors.bridge,
      charts: h.charts.length, overlap: h.charts.some((a, i) => h.charts.some((b, j) => i < j && over(a, b))), texel: [Math.min(...h.charts.map((c) => h.texel(c))), Math.max(...h.charts.map((c) => h.texel(c)))],
      charted: h.charts.every((c) => h.regions.some((g) => g.name === c.region && g.charts.includes(c.id)) && c.size[0] >= 14 && c.size[1] >= 14 && (c.kind === "plane" ? c.du && c.dv && c.normal : c.axis && c.radius > 0)),
      uvOk, uvN, profile: h.profile.length, stern: h.anchors.bells.every((b) => Math.abs(b.p[2] + half[2]) < 0.02 * h.size.length + (family === "twin" ? 0.12 * h.size.length : 0)), shape: h.shape.radii.map(r4), shadow: h.shadows.size});
  }
  const near = A.hull(family, {seed: 2}), again = A.hull(family, {seed: 2}), far = A.hull(family, {seed: 2, detail: "far"}), long = A.hull(family, {seed: 2, length: 9000});
  out.push({family, rows, same: JSON.stringify(sig(near)) === JSON.stringify(sig(again)), far: far.info.triangles, near: near.info.triangles, long: [long.size.length, long.problems()], farRegions: far.regions.length === near.regions.length, farCharts: far.charts.length});
}
""")
    assert [o["family"] for o in out] == FAMILIES
    for o in out:
        rows = o["rows"]
        for r in rows:
            assert abs(r["size"]["length"] / r["length"] - 1) < 0.002, (o["family"], r["seed"], r["size"])           # the length asked for
            assert 500 <= r["length"] <= 10_000 and r["problems"] == [], (o["family"], r["seed"], r["problems"])
            assert 3_000 < r["tri"] <= BUDGET["near"], (o["family"], r["tri"])
            assert "bow" in r["names"] and any(n.startswith("engine-block") for n in r["names"]) and len(set(r["names"])) == len(r["names"]), r["names"]
            assert r["boxes"] and r["normals"] >= 3 and r["anchors"] and r["bells"] == r["engines"] >= 1 and r["docks"] >= 1 and r["lights"] == 5 and r["bridge"], (o["family"], r)
            assert r["charts"] >= 8 and not r["overlap"] and r["charted"] and r["uvOk"] and r["uvN"] > 5_000 and 0.02 < r["texel"][0] <= r["texel"][1] < 12, (o["family"], r["texel"], r["charts"])
            assert r["profile"] >= 8 and r["stern"] and abs(r["shape"][2] - r["size"]["length"] / 2) < 1e-3 and r["shadow"] > r["size"]["length"] / 2
        assert o["same"] and len({json.dumps(r["sig"]) for r in rows}) == 3                           # a seed is a hull; another seed another
        assert o["far"] <= BUDGET["far"] and o["far"] < o["near"] and o["farRegions"]
        assert abs(o["long"][0] - 9000) < 20 and o["long"][1] == []
    by = {o["family"]: o for o in out}
    assert all(any(n.startswith("hangar-") for n in r["names"]) and r["hangars"] >= 1 and "trench" in r["names"] and any(n.startswith("tower-") for n in r["names"]) for r in by["carrier"]["rows"])
    assert all({"ring-1", "ring-2"} <= set(r["names"]) for r in by["wheel"]["rows"]) and all({"rock", "collar", "hangar-1"} <= set(r["names"]) for r in by["ark"]["rows"])
    assert all(any(n.startswith("radiator-") for n in r["names"]) for o in out for r in o["rows"])
    assert all({"port-hull", "starboard-hull", "engine-block-1", "engine-block-2"} <= set(r["names"]) for r in by["twin"]["rows"])


@pytest.mark.slow
def test_problems_flight_fleet_and_scale(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, r"""
// the forbidden layout, constructed: a plan narrowing to a point with a tall tower at the stern
const wedge = A.hull("carrier", {seed: 1, taper: 0.4, side: 1, towers: [{at: 0.84, side: 0, len: 0.08, wid: 0.2, high: 1.2}]});
const dagger = A.hull("carrier", {seed: 1, taper: 0.15, towers: []});
const fine = A.hull("carrier", {seed: 1, towers: [{at: 0.84, side: 1, len: 0.08, wid: 0.2, high: 1.2}]});
out.push([wedge.problems(), dagger.problems(), fine.problems()]);
// bells sunk into the hull, a hull too short, too thin, nearly a cube
out.push([A.hull("spine", {seed: 1, inset: 0.1}).problems(), A.hull("lance", {seed: 1, length: 300}).problems(),
  A.hull("ark", {seed: 1, girth: 0.6, vaneSpan: 0.25, vaneAngles: [0, 90, 180, 270]}).problems()]);
// names: a region, an anchor, an option
const h = A.hull("carrier", {seed: 1, length: 3000});
out.push([err(() => h.region("trnch")), err(() => h.anchor("hangar-9")), err(() => A.hull("carrier", {lenght: 3000})), err(() => h.scaleRef("ship", {att: "port"})), err(() => A.hullKit({pallete: "bone"}))]);
// the contract in numbers: a hangar's mouth, a chart's frame puts a texel on its face, uv in metres
const hg = h.anchors.hangars[0], reg = h.region(hg.name), chart = h.charts.find((c) => c.region === "midship" && c.kind === "plane" && c.name.endsWith("/top"));
const at = (cu, cv) => chart.origin.map((v, i) => v + chart.du[i] * cu + chart.dv[i] * cv), mid = at(chart.size[0] / 2, chart.size[1] / 2);
out.push([hg.name, Math.abs(hg.n[0]), hg.width > 100 && hg.height > 30 && hg.depth > 30, reg.detail, reg.surface.expects.length > 10, reg.skin, r4(chart.normal[1]), r4(mid[1] - chart.origin[1]) === 0 && Math.abs(mid[0]) < h.size.width / 2 && Math.abs(mid[2]) < h.size.length / 2, r4(h.texel(chart, 4096) * 2 - h.texel(chart, 2048)),
  h.anchor("bridge").p.length, h.anchor("bow").p[2] === h.size.length / 2, h.anchors.nozzles.length === h.anchors.bells.length, h.family, h.spec.length]);
// a known-size craft beside it: a child of the hull, off the anchor along its direction
const small = h.scaleRef("ship", {at: hg.name, gap: 100, detail: "far"}), sp = small.object.position;
out.push([small.object.parent === h.object, r4(Math.hypot(sp.x - hg.p[0], sp.y - hg.p[1], sp.z - hg.p[2])), small.size.length > 40 && small.size.length < 60, h.refs.length]);
// flown from orbit data: the bow along the path, the deck away from the world; the bells fire with the throttle; the rings turn
const orbits = {names: ["Earth", "Ship"], fps: 30, bodies: {Earth: {parent: null}, Ship: {parent: "Earth"}}, position: (n) => (n === "Ship" ? [7.3e6, 0, 0] : [0, 0, 0]), velocity: (n) => (n === "Ship" ? [0, 7400, 0] : [0, 0, 0]), burns: () => []};
const added = [];
h.fly({orbits, add: (o, where) => added.push(where)}, {body: "Ship"}).update(1, {throttle: 0.5});
const bow = new THREE.Vector3(0, 0, 1).applyQuaternion(h.object.quaternion), up = new THREE.Vector3(0, 1, 0).applyQuaternion(h.object.quaternion);
out.push([added, r4(bow.z), r4(up.x), h.engines.every((e) => e.plume.visible), h.state.throttle]);
const w = A.hull("wheel", {seed: 1});
w.update(0); const q0 = w.spinners.map((s) => s.rotation.y); w.update(10); const q1 = w.spinners.map((s) => s.rotation.y);
out.push([w.spinners.length, q0, q1.map(r4), r4(Math.sqrt(9.81 / (w.spec.ring * w.spec.length)) * 10)]);
// a fleet from seeds, in turn through the families, at far detail
const f = A.hullFleet(["carrier", "spine", "twin"], {count: 5, seed: 3});
out.push([f.hulls.map((s) => s.family), f.hulls.map((s) => s.spec.seed), f.hulls.every((s) => s.info.triangles <= 20000), f.object.children.length, new Set(f.hulls.map((s) => s.object.position.toArray().map(Math.round).join())).size, f.update(0, {}) === f]);
// star occluders for shade()
const star = {occluders: [1]}; h.shade(star); out.push([star.occluders.length === 1 + h.occluders.length, h.occluders.length > 20]);
""")
    wedge, dagger, fine = out[0]
    assert len(wedge) == 1 and "raised tower at the stern (tower-1)" in wedge[0] and "well-known fictional ship" in wedge[0]
    assert len(dagger) == 1 and "narrows to a point" in dagger[0] and fine == []
    buried, short, fat = out[1]
    assert buried and all("is buried" in p for p in buried) and len(short) == 1 and "300 m long" in short[0] and any("not a ship with a long axis" in p for p in fat)
    e = out[2]
    assert 'did you mean "trench"' in e[0] and 'no anchor "hangar-9"' in e[1] and 'did you mean "length"' in e[2] and 'did you mean "at"' in e[3] and 'did you mean "palette"' in e[4]
    c = out[3]
    assert c[0] == "hangar-1" and c[1] == 1 and c[2] and c[3] == "hangar" and c[4] and c[5] in ("hull-c", "hull-void") and c[6] == 1 and c[7] and c[8] == 0 and c[9] == 3 and c[10] and c[11] and c[12] == "carrier" and c[13] == 3000
    assert out[4][0] and abs(out[4][1] - 100) < 1e-3 and out[4][2] and out[4][3] == 1
    assert out[5][0] == [{"body": "Ship"}] and out[5][1] < -0.999 and out[5][2] > 0.999 and out[5][3] and out[5][4] == 0.5      # data +y is three's -z; data +x is three's +x
    n, q0, q1, turn = out[6]
    assert n == 2 and q0 == [0, 0] and q1[0] > 0 > q1[1] and abs(q1[0] - turn) < 1e-3                 # two rings turning against each other, 1 g at the first's rim
    assert out[7][0] == ["carrier", "spine", "twin", "carrier", "spine"] and out[7][1] == [3, 4, 5, 6, 7] and out[7][2] and out[7][3] == 5 and out[7][4] == 5 and out[7][5]
    assert out[8] == [True, True]


PAGE = """
import * as THREE from "three";
import {star, spaceLight} from "vidgen/space-light";
import {SpaceView} from "vidgen/space-scale";
import {planet} from "vidgen/space-bodies";
import {paintedEnvironment} from "vidgen/space-craft";
import {hull} from "vidgen/space-hull";
window.made = {error: null};
let renderer, scene, camera, c, ship, small, light, sun, space, world, flat;
export function load(ctx) {
  try {
    c = ctx.data;
    renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
    renderer.setSize(ctx.width, ctx.height, false);
    scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
    camera = new THREE.PerspectiveCamera(c.fov ?? 30, ctx.width / ctx.height, 1, 1e9);
    space = new SpaceView(ctx, {renderer, scene, camera});
    ship = hull("carrier", {seed: 1, length: 3000, detail: c.detail ?? "far"}).fly(space, {body: "Ship"});
    small = ship.scaleRef("ship", {at: "hangar-1", gap: 300, detail: "far"});
    world = planet(renderer, "Earth", {space, size: 256});
    sun = star(renderer, "sun", {direction: [1, 0, 0]}); scene.add(sun.object);
    light = spaceLight({scene, camera, renderer, sun, bodies: [world], at: ship.object, shadows: c.shadows === false ? false : ship.shadows});
    ship.shade(sun);
    scene.environment = paintedEnvironment(renderer).texture;
    if (c.flat) {                                            // every face one colour by its direction: two faces fighting show as a mix
      flat = new THREE.MeshNormalMaterial();
      ship.object.traverse((m) => { if (m.isMesh && !m.userData.keep && m.material.isMeshStandardMaterial) m.material = flat; });
    }
    if (c.red) small.object.traverse((m) => { if (m.isMesh && !m.userData.keep) m.material = new THREE.MeshBasicMaterial({color: 0xff0000}); });
    window.made.triangles = ship.info.triangles; window.made.length = ship.size.length; window.made.problems = ship.problems();
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
const data = (v) => [v.x, -v.z, v.y];
export function frame(t) {
  try {
    space.update(t, {from: {body: "Ship", offset: [0, 0, 1000]}, to: "Ship"});
    ship.update(t, {});
    const q = ship.object.quaternion, own = (a) => data(new THREE.Vector3(...a).applyQuaternion(q)), s = new THREE.Vector3(...(c.sun ?? [0.6, 0.6, 0.5])).normalize().applyQuaternion(q);
    sun.direction.copy(s);
    const sp = small.object.position, from = c.aim ? [sp.x + Math.sign(sp.x) * c.aim[0], sp.y + c.aim[1], sp.z + c.aim[2]] : c.from, to = c.aim ? sp.toArray() : (c.to ?? [0, 0, 0]);   // aim: from the open side of the small craft
    space.update(t, {from: {body: "Ship", offset: own(from)}, to: {body: "Ship", offset: own(to)}, up: own([0, 1, 0])});
    world.update(t); ship.update(t, {sun: s}); small.update(t, {sun: s}); sun.update(t); light.update(t);
    renderer.setRenderTarget(null); renderer.render(scene, camera);
    const p = small.object.getWorldPosition(new THREE.Vector3()).project(camera);
    window.made.small = [(p.x + 1) / 2, (1 - p.y) / 2]; window.made.slices = space.slices.length; window.made.up = new THREE.Vector3(0, 1, 0).applyQuaternion(q).dot(ship.object.position.clone().sub(world.object.position).normalize());
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
"""


@pytest.mark.slow
def test_a_hull_draws_beside_a_small_craft_over_a_world_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "hull.js").write_text(PAGE, encoding="utf-8")
    settings = od.OrbitData.model_validate({"central": "earth", "speedup": 1, "bodies": [{"name": "Ship", "altitude": "900 km"}]})
    orbits = json.loads(json.dumps(od.make_orbit_data(settings, 10, 2, 2)))

    def draw(data: dict) -> tuple[np.ndarray, dict, dict]:
        with WebPage(tmp_path, WebEntry("script", "hull.js"), scene_id="s", size=(320, 180), fps=10, frames=2, data=data, orbits=orbits) as page:
            frame = page.frame(0)[..., :3].astype(int)
            made = page._page.evaluate("window.made")
            assert made["error"] is None, made["error"]
            return frame, dict(page.loaded), made

    # from above, the world behind: the hull is drawn in front of it, lit, with its dark hangar slots
    above = {"from": [1500, 3000, 2100], "to": [0, 0, 0], "fov": 34}
    lit, loaded, made = draw(above)
    again, _, _ = draw(above)
    assert {"__vidgen__/modules/space-hull.js", "__vidgen__/modules/space-craft.js", "__vidgen__/modules/space-scale.js"} <= set(loaded)
    assert abs(made["length"] - 3000) < 5 and made["problems"] == [] and made["slices"] >= 1 and made["up"] > 0.99      # in orbit, its deck away from the world
    assert np.array_equal(lit, again)                                               # a second page draws the same picture
    marked, _, made = draw({**above, "flat": True})
    hull_px = np.abs(marked - lit).max(axis=-1) > 40                                # where the hull's own faces are
    assert 6_000 < hull_px.sum() < 40_000 and hull_px[70:110, 120:200].mean() > 0.5
    world_px = ~hull_px & (lit.max(axis=-1) > 30)
    assert world_px.sum() > 12_000                                                  # the world fills the frame behind
    # no fighting between faces: with every face coloured by its direction, the deck is one colour over large patches
    # (two coplanar or mis-sorted faces would speckle)
    codes = (marked // 16 * np.array([4096, 64, 1])).sum(axis=-1)
    values, counts = np.unique(codes[hull_px], return_counts=True)
    deck = hull_px & (codes == values[counts.argmax()])                             # the largest face direction in view: the deck
    assert deck.sum() > 0.15 * hull_px.sum()
    speckle = (deck[1:-1, 1:-1] & ~deck[1:-1, :-2] & ~deck[1:-1, 2:] & ~deck[:-2, 1:-1] & ~deck[2:, 1:-1]).sum()
    assert speckle < 0.02 * deck.sum()
    # the small craft: red, 50 m long, where it was put (off the first hangar), in front of the hull's side
    close = {"aim": [900, 150, 500], "fov": 24, "detail": "near"}
    plain, _, _ = draw(close)
    red, _, made = draw({**close, "red": True})
    px = (red[..., 0] > 200) & (red[..., 1] < 40) & (red[..., 2] < 40)
    ys, xs = np.nonzero(px)
    assert 4 <= px.sum() < 400 and abs(xs.mean() / 320 - made["small"][0]) < 0.03 and abs(ys.mean() / 180 - made["small"][1]) < 0.04
    assert (np.abs(plain - red).max(axis=-1) > 40).sum() < 3 * px.sum() + 20        # nothing else changed
    # its own shadows: turning them off only brightens
    unshadowed, _, _ = draw({**above, "shadows": False})
    assert (unshadowed.sum(axis=-1) > lit.sum(axis=-1) + 60).sum() > 100 and (lit.sum(axis=-1) > unshadowed.sum(axis=-1) + 60).sum() < 30
