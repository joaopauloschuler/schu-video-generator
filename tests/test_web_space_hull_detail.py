"""The fine detail of giant hulls, ``vidgen/space-hull-detail`` (Step 389, DESIGN.md §123.11): the module
is served by its import name and builds on ``vidgen/space-hull`` and ``vidgen/baked``; its parts are
registered; in Node (when it is installed): window rows follow the decks (a floor's height apart) and a
region's use (dense on crew decks, none on tanks, radiators and engines), the lit share comes from the
seed, a scale of detail fades with the metres a pixel covers, a tiling map is the same every time and
keeps its mean tone, mistakes are named with a did-you-mean; (``slow``) on real hulls: the unique map
lights a bay's inside and leaves untouched texels neutral, marks, lamps and clutter are the same for a
seed and stay on the hull, a small craft's way into a bay ends inside it, a fleet has one livery; in
Chromium (``slow``): the night side shows lit window pixels that the day side does not, a hangar's inside
is brighter than the bare void, the picture is the same with the cache off, cold and warm, and from a
second page."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.scenes import orbit_data as od
from vidgen.web import baked as B
from vidgen.web import parts as P
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = DATA / "web" / "modules"
MODULE = MODULES / "space-hull-detail.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
CRAFT = {"hull-dressed", "hull-windows", "hull-bay", "hull-torch", "hull-fleet-dressed"}


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-hull-detail"] == "space-hull-detail.js"
    assert IMPORT_MAP["imports"]["vidgen/space-hull-detail"] == "/__vidgen__/modules/space-hull-detail.js"
    assert vidgen_file("modules/space-hull-detail.js") == MODULE
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/music-time", "vidgen/baked", "vidgen/space-craft", "vidgen/space-hull"]
    assert "Math.random" not in source and "Date.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-hull-detail" not in engine_id()


def test_the_parts_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-hull-detail.js"}
    assert {n for n, p in found.items() if p.kind == "craft"} == CRAFT and {n for n, p in found.items() if p.kind == "craft-part"} == {"hull-detail-maps"}
    assert all(p.module == "vidgen/space-hull-detail" for p in found.values())
    assert "dress(ship, renderer)" in found["hull-dressed"].use and "dressFleet(" in found["hull-fleet-dressed"].use and "ctx.music" in found["hull-windows"].use
    assert all(len(p.label) <= 106 for p in found.values())                    # (longer labels are cut off on the sheet)
    assert "Math.random" not in (P.PARTS_DIR / "space-hull-detail.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``D`` (and the hulls as ``A``) and print ``out`` as JSON."""
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
    names = ("music-time", "baked", "space-craft", "space-hull", "space-hull-detail")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as A from 'vidgen/space-hull';\nimport * as D from 'vidgen/space-hull-detail';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const sum = (a) => { let s = 0; for (let i = 0; i < a.length; i += 7) s = (s * 31 + a[i]) % 1000003; return s; };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=240, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


@pytest.mark.slow
def test_windows_scales_and_maps_as_numbers(tmp_path: Path) -> None:
    body = """
    // a wall: rows are level, a floor apart whatever the wall's direction; decks and ceilings have none
    out.push([D.windowCoords([500, 40, 120], [1, 0, 0]), D.windowCoords([500, 43.5, 120], [1, 0, 0]), D.windowCoords([500, 40, 123.2], [1, 0, 0]), D.windowCoords([10, 40, 900], [0, 0, 1]), D.windowCoords([0, 100, 0], [0, 1, 0]), D.windowCoords([0, -100, 0], [0.2, -0.95, 0])]);
    // a round face: rows run round it (its uv), its end faces have none
    out.push([D.windowCoords([0, 0, 0], [1, 0, 0], {round: [0, 0, 1], uv: [12, 7]}), D.windowCoords([0, 0, 0], [0, 0, 1], {round: [0, 0, 1], uv: [12, 7]})]);
    out.push([D.WINDOWS, ["windows", "plating", "tank", "radiator", "engine", "hangar", "truss", "shield"].map((k) => D.windowShare(k)), D.windowShare("windows", "hull-radiator"), D.windowShare("windows", "hull-tank"), D.windowShare("windows", "hull-void"), D.windowShare("windows", "hull-b")]);
    const cells = (seed, o) => { const c = D.windowCells(seed, o); return [c.exist, c.lit, sum(c.watch), sum(c.rest), c.watch.length]; };
    out.push([cells(1), cells(1), cells(2), cells(1, {lit: 0.1}), cells(1, {lit: 0}), cells(1, {lit: 0.36, watch: 1})]);
    out.push([["fine", 0.1], ["fine", 0.35], ["fine", 0.8], ["fine", 1.4], ["fine", 20], ["mid", 1], ["mid", 5], ["mid", 9], ["mid", 50]].map(([s, m]) => D.fade(s, m)));
    const map = (k, s) => { const m = D.detailMap(k, s, 128); let tone = 0, flat = 0; for (let i = 0; i < m.data.length; i += 4) { tone += m.data[i + 2]; if (Math.abs(m.data[i] - 127.5) < 2 && Math.abs(m.data[i + 1] - 127.5) < 2) flat++; } return [m.size, m.tile, tone / (m.data.length / 4), flat / (m.data.length / 4), sum(m.data)]; };
    out.push(D.KINDS.flatMap((k) => ["mid", "fine"].map((s) => map(k, s))));
    out.push(map("plating", "mid")[4] === map("plating", "mid")[4]);
    out.push([err(() => D.detailMap("platting", "mid")), err(() => D.detailMap("plating", "fin")), err(() => D.fade("mud", 1)), D.SCALES, D.PLUME_MODES]);
    """
    walls, round_, shares, cells, fades, maps, same, errors = _run_in_node(tmp_path, body)
    a, up, along, bow, deck, ceiling = walls
    assert a[2] == 1 and up[1] - a[1] == pytest.approx(3.5) and up[0] == pytest.approx(a[0])    # one floor up: the next row, the same place along it
    assert abs(along[0] - a[0]) == pytest.approx(3.2) and along[1] == a[1]                      # along the wall: the same row
    assert bow[2] == 1 and bow[1] == 40 and abs(bow[0]) == pytest.approx(10)
    assert deck == [0, 0, 0] and ceiling == [0, 0, 0]
    assert round_ == [[12, 7, 1], [0, 0, 0]]
    table, by_use, on_radiator, on_tank, on_void, on_plate = shares
    assert by_use[0] > 3 * by_use[1] > 0 and by_use[2:] == [0, 0, 0, 0, 0, 0]                   # dense on crew decks, a few ports on plate, none on tanks, radiators, engines
    assert on_radiator == on_tank == on_void == 0 and on_plate == table["windows"]
    first, again, other, few, none, watch = cells
    assert first == again and first[2:4] != other[2:4] and first[4] == 256 * 256 * 4            # a function of the seed
    assert 0.7 < first[0] < 0.85 and first[1] == pytest.approx(0.36, abs=0.03) and few[1] == pytest.approx(0.1, abs=0.02) and none[1] == 0 and none[3] == 0
    assert watch[3] == 0 and watch[1] == first[1]                                               # all on the night watch: none left to come on
    assert fades[0] == fades[1] == 1 and 0 < fades[2] < 1 and fades[3] == fades[4] == 0         # the small scale has gone when a pixel covers 1.4 m
    assert fades[5] == 1 and 0 < fades[6] < 1 and fades[7] == fades[8] == 0 and fades[6] > 0    # the middle scale at 9 m
    for size, tile, tone, flat, _ in maps:
        assert size == 128 and tile in (192, 32) and 118 < tone < 134 and flat < 0.995          # the mean tone is kept (a faded map changes nothing), and there is relief
    assert len({m[4] for m in maps}) == 8 and same is True
    assert 'did you mean "plating"' in errors[0] and 'did you mean "fine"' in errors[1] and 'did you mean "mid"' in errors[2]
    assert errors[3]["mid"]["tile"] > errors[3]["fine"]["tile"] and errors[4] == ["both", "bank", "bells"]


@pytest.mark.slow
def test_the_detail_of_real_hulls_as_numbers(tmp_path: Path) -> None:
    body = """
    const h = A.hull("carrier", {seed: 1}), size = 512, u = D.uniqueMap(h, size), again = D.uniqueMap(A.hull("carrier", {seed: 1}), size), other = D.uniqueMap(A.hull("carrier", {seed: 2}), size);
    const texel = (c, cu, cv) => { const a = c.turned ? cv : cu, b = c.turned ? cu : cv, i = Math.floor((c.rect[0] + a * c.scale) * size), j = Math.floor((c.rect[1] + b * c.scale) * size); return Array.from(u.slice(4 * (j * size + i), 4 * (j * size + i) + 4)); };
    const bay = h.anchors.hangars[0], inside = h.charts.filter((c) => c.kind === "plane" && D.inBay(bay, [0, 1, 2].map((k) => c.origin[k] + c.du[k] * c.size[0] / 2 + c.dv[k] * c.size[1] / 2), 6));
    const tower = h.charts.find((c) => c.region === "tower-1" && c.kind === "plane" && Math.abs(c.normal[1]) < 0.5), aft = h.charts.find((c) => c.region === "engine-block" && c.kind === "plane" && c.normal[2] < -0.9);
    let marks = 0, lit = 0; for (let i = 0; i < u.length; i += 4) { if (u[i + 1] > 128) marks++; if (u[i + 2] > 60) lit++; }
    out.push([sum(u) === sum(again), sum(u) !== sum(other), Array.from(u.slice(4 * (2 * size + 2), 4 * (2 * size + 2) + 4)), inside.map((c) => texel(c, c.size[0] / 2, c.size[1] / 2)[2]), texel(tower, 3, 3)[2], texel(aft, aft.size[0] / 2, aft.size[1] / 2)[3], texel(tower, 3, 3)[3], marks / (size * size), lit / (size * size)]);
    const plans = (q) => [D.markPlan(q), D.floodPlan(q), D.navLights(q), D.clutterPlan(q), D.clutterPlan(q, {density: 0.25})];
    const p = plans(h), p2 = plans(A.hull("carrier", {seed: 1})), half = [h.size.width / 2 + 60, h.size.height / 2 + 60, h.size.length / 2 + 60];
    const inBox = (q) => Math.abs(q[0]) < half[0] && Math.abs(q[1]) < half[1] && Math.abs(q[2]) < half[2];
    const kinds = {}; for (const l of p[2]) kinds[l.kind] = (kinds[l.kind] ?? 0) + 1;
    const pieces = {}; for (const c of p[3]) pieces[c.kind] = (pieces[c.kind] ?? 0) + 1;
    out.push([JSON.stringify(p) === JSON.stringify(p2), p.map((x) => x.length), p[2].every((l) => inBox(l.p)), p[3].every((c) => inBox(c.p) && c.s.every((v) => v > 0 && v < 300)), kinds, pieces, p[2].filter((l) => l.color[0] > 0.9 && l.color[1] < 0.2).every((l) => l.kind !== "steady" || l.p[0] > 0),
      p[3].every((c) => !h.anchors.hangars.some((b) => D.inBay(b, c.p, 0)))]);
    const way = [0, 0.5, 1].map((k) => D.bayApproach(h, "hangar-2", k)), b2 = h.anchors.hangars[1];
    out.push([way.map((w) => D.inBay(b2, w.p, 0)), Math.hypot(...[0, 1, 2].map((k) => way[0].p[k] - b2.p[k])), way.map((w) => Math.hypot(...w.forward)), way[2].forward[0] * b2.n[0] + way[2].forward[2] * b2.n[2], err(() => D.bayApproach(h, "hangar-9", 0)), err(() => D.bayApproach(h, "hangar-1", 0, {hieght: 3}))]);
    // hulls without a bay or a deck still get lamps; tanks, radiators and engines never get windows
    out.push(["spine", "wheel", "lance", "ark", "twin", "cluster"].map((f) => { const q = A.hull(f, {seed: 1}); return [f, D.navLights(q).length, D.markPlan(q).length, q.regions.filter((g) => D.windowShare(g.detail) > 0).map((g) => g.name).filter((n) => /tank|radiator|engine/.test(n)).length, q.regions.some((g) => D.windowShare(g.detail) > 0.5)]; }));
    const fleet = A.hullFleet(["carrier", "spine", "twin"], {count: 4, seed: 3}), mixed = A.hullFleet(["carrier", "spine", "twin"], {count: 4, seed: 3, navy: false});
    out.push([fleet.hulls.map((q) => q.spec.palette + "/" + q.kit.accent), mixed.hulls.map((q) => q.spec.palette + "/" + q.kit.accent), err(() => D.dress({}, null)), err(() => D.dressFleet({}, null))]);
    const g = A.hull("carrier", {seed: 1}).object; let withChart = 0, meshes = 0; g.traverse((m) => { if (m.isMesh && m.geometry.attributes.uv1) { meshes++; if (m.geometry.attributes.chart && m.geometry.attributes.chart.count === m.geometry.attributes.position.count) withChart++; } });
    out.push([meshes, withChart]);
    """
    unique, plans, way, others, fleets, charts = _run_in_node(tmp_path, body)
    same, differs, spare, bay_light, tower_light, stern_hot, tower_hot, marks, lit = unique
    assert same and differs and spare == [128, 0, 0, 0]                           # the texel faces without a chart read changes nothing
    assert len(bay_light) >= 2 and min(bay_light) > 90                            # the inside of a bay is lit on every face
    assert tower_light < 40 and stern_hot > 60 and tower_hot == 0                 # the plumes light the stern, not a tower forward
    assert 0.0005 < marks < 0.05 and 0.02 < lit < 0.5
    same, counts, lamps_on, clutter_on, kinds, pieces, red_to_port, clear_of_bays = plans
    assert same and lamps_on and clutter_on and red_to_port and clear_of_bays
    assert counts[0] > 100 and counts[1] >= 4 and counts[2] > 100 and 1000 < counts[3] <= 5000 and counts[4] < 0.4 * counts[3]
    assert {"steady", "strobe", "beacon", "chase"} <= set(kinds) and kinds["strobe"] == 2
    assert set(pieces) == {"box", "pipe", "stack", "mast", "dish"} and pieces["box"] > pieces["pipe"] > pieces["dish"]
    inside, start, forward, heading, no_bay, bad_option = way
    assert inside == [False, False, True] and start > 500 and all(abs(f - 1) < 1e-9 for f in forward) and heading < -0.9      # it ends inside, flying in
    assert 'did you mean "hangar-2"' in no_bay or "hangar-1" in no_bay
    assert 'did you mean "height"' in bad_option
    for family, lamps, marks_n, wrong, crew in others:
        assert lamps >= 20 and wrong == 0, family
        assert crew or family in ("cluster",), family
    navy, mixed, bad_hull, bad_fleet = fleets
    assert len(set(navy)) == 1 and len(set(mixed)) > 1                            # one maker: one palette and one accent
    assert "needs a hull" in bad_hull and "needs a fleet" in bad_fleet
    assert charts[0] > 5 and charts[0] == charts[1]


PAGE = """
import * as THREE from "three";
import {star, spaceLight} from "vidgen/space-light";
import {SpaceView} from "vidgen/space-scale";
import {planet} from "vidgen/space-bodies";
import {hull} from "vidgen/space-hull";
import {dress} from "vidgen/space-hull-detail";
let renderer, scene, camera, c, ship, detail, light, sun, space, world;
export function load(ctx) {
  c = ctx.data; window.made = {error: null};
  try {
    renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
    renderer.setSize(ctx.width, ctx.height, false); renderer.toneMapping = THREE.ACESFilmicToneMapping;
    scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
    camera = new THREE.PerspectiveCamera(c.fov ?? 30, ctx.width / ctx.height, 1, 1e9);
    space = new SpaceView(ctx, {renderer, scene, camera});
    ship = hull("carrier", {seed: 1, length: 3000}); ship.fly(space, {body: "Ship"});
    if (c.dress !== false) { detail = dress(ship, renderer, {atlas: 1024, maps: 256, ...(c.dress ?? {})}); window.made.info = detail.info; }
    world = planet(renderer, "Earth", {space, size: 256});
    sun = star(renderer, "sun", {direction: [1, 0, 0]}); scene.add(sun.object);
    light = spaceLight({scene, camera, renderer, sun, bodies: [world], at: ship.object, shine: 0, exposure: c.exposure ?? "film", ev: c.ev ?? 0});
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
const data = (v) => [v.x, -v.z, v.y];
export function frame(t) {
  try {
    space.update(t, {from: {body: "Ship", offset: [0, 0, 1000]}, to: "Ship"});
    ship.update(t, {});
    const q = ship.object.quaternion, own = (a) => data(new THREE.Vector3(...a).applyQuaternion(q)), s = new THREE.Vector3(...c.sun).normalize().applyQuaternion(q);
    sun.direction.copy(s);
    space.update(t, {from: {body: "Ship", offset: own(c.from)}, to: {body: "Ship", offset: own(c.to)}, up: own([0, 1, 0])});
    world.update(t); ship.update(t, {sun: s, throttle: c.throttle ?? 0}); sun.update(t); light.update(t);
    if (detail) detail.update(t, {lights: c.lights ?? 1, light});
    renderer.setRenderTarget(null); renderer.render(scene, camera);
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
"""


@pytest.mark.slow
def test_a_dressed_hull_draws_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "hull.js").write_text(PAGE, encoding="utf-8")
    settings = od.OrbitData.model_validate({"central": "earth", "speedup": 1, "bodies": [{"name": "Ship", "altitude": "900 km"}]})
    orbits = json.loads(json.dumps(od.make_orbit_data(settings, 10, 2, 2)))

    def draw(data: dict, baked: object = False) -> tuple[np.ndarray, dict, list]:
        with WebPage(tmp_path, WebEntry("script", "hull.js"), scene_id="s", size=(320, 180), fps=10, frames=2, data=data, orbits=orbits, baked=baked) as page:
            frame = page.frame(0)[..., :3].astype(int)
            made = page._page.evaluate("window.made")
            assert made["error"] is None, made["error"]
            return frame, made, list(page.baked_log)

    # the port side from outside, the sun behind the hull: the night side
    night = {"from": [1500, 250, 900], "to": [400, 40, 0], "fov": 34, "sun": [-0.7, 0.3, -0.6]}
    lit, made, _ = draw(night)
    assert made["info"]["windows"] > 20_000 and made["info"]["lamps"] > 100 and made["info"]["clutter"] > 500 and made["info"]["craft"] >= 2
    bare, _, _ = draw({**night, "dress": False})
    warm_light = (lit[..., 0] > 110) & (lit[..., 0] > lit[..., 2] + 25)             # the yellow of a lit window or a lit bay
    assert warm_light.sum() > 150 and ((bare[..., 0] > 110) & (bare[..., 0] > bare[..., 2] + 25)).sum() < 10
    dark, _, _ = draw({**night, "dress": {"windows": False, "hangars": False, "nav": False}})
    windows = (lit.sum(axis=-1) > dark.sum(axis=-1) + 90)
    assert windows.sum() > 150                                                      # windows, lamps and bays are light the bare night side does not have
    # the same wall in sunlight: the windows step back (film), the surface is not flat
    day = {**night, "sun": [0.7, 0.4, 0.5]}
    sunny, _, _ = draw(day)
    plain, _, _ = draw({**day, "dress": False})
    hull_px = plain.sum(axis=-1) > 150
    assert hull_px.sum() > 8_000 and (np.abs(sunny - plain).max(axis=-1)[hull_px] > 12).mean() > 0.04     # seams, clutter and marks change the lit hull (and the world behind it not at all)
    # an honest exposure for sunlight: the windows are far too faint to see
    honest, _, _ = draw({**night, "exposure": "camera", "ev": 0})
    assert ((honest[..., 0] > 110) & (honest[..., 0] > honest[..., 2] + 25)).sum() < 0.1 * warm_light.sum()
    # a hangar from outside, its mouth in shadow: lit inside where the bare hull has a black void
    bay = {"from": [1000, 20, 300], "to": [487, -40, 125], "fov": 24, "sun": [0.1, 0.8, 0.6]}
    inside, _, _ = draw(bay)
    void, _, _ = draw({**bay, "dress": False})
    centre = (slice(60, 120), slice(110, 210))
    assert inside[centre].sum(axis=-1).mean() > void[centre].sum(axis=-1).mean() + 60
    # the same picture from a second page, with the cache off, cold and warm
    again, _, _ = draw(night)
    assert np.array_equal(lit, again)
    store = B.BakedStore(tmp_path / "baked", 10**9)
    cold, _, log_cold = draw(night, store)
    warm, _, log_warm = draw(night, store)
    assert np.array_equal(lit, cold) and np.array_equal(lit, warm)
    names = [name for what, name, _ in log_warm if what == "hit"]
    assert names.count("space-hull-detail/tile") == 8 and "space-hull-detail/unique" in names     # the maps came from the cache
    assert not any(what == "hit" for what, name, _ in log_cold if name.startswith("space-hull-detail"))
