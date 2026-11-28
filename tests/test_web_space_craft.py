"""The spacecraft kit, ``vidgen/space-craft`` (Step 374): the module is served by its
import name and imports only ``three``, its geometry add-on and ``vidgen/music-time``; its parts are
registered (every ready-made craft, the kit's parts, surfaces and plumes); in Node (when it is
installed): every craft builds, the same seed gives the same craft and another seed another, the
"far" detail has far fewer triangles, parts join at their points, the attitude modes point where
they say and a turn between them is a function of time, a burn of the orbit data becomes a stretch
of thrust with the nose along it, wings face the sun, a dish its target, lights blink by the
clock, a far craft is a steady point with a flash, mistakes are named with a did-you-mean; in
Chromium (``slow``): a probe in sunlight shows gold foil, the same frame twice, its own shadows, an
engine's plume, the sun's glare hidden behind it, and its shadows inside ``vidgen/space-scale``."""

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
MODULE = MODULES / "space-craft.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
CRAFT = {"craft-probe", "craft-satellite", "craft-station", "craft-station-ring", "craft-ship", "craft-ship-burn", "craft-lander", "craft-tug", "craft-fleet", "craft-seeds"}
CRAFT_PARTS = {"part-hulls", "part-tanks", "part-truss", "part-solar-wing", "part-solar-wing-folding", "part-radiator", "part-dish", "part-antennas", "part-instruments",
               "part-docking", "part-engine", "part-thrusters-leg", "part-ring-habitat", "part-cargo-lights", "surface-foil", "surface-plating", "surface-cells-glass",
               "plume-chemical", "plume-vacuum", "plume-ion", "plume-air"}


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-craft"] == "space-craft.js"
    assert IMPORT_MAP["imports"]["vidgen/space-craft"] == "/__vidgen__/modules/space-craft.js"
    assert vidgen_file("modules/space-craft.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-craft.js"])["__vidgen__/modules/space-craft.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "three/addons/utils/BufferGeometryUtils.js", "vidgen/music-time"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-craft" not in engine_id()


def test_the_parts_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-craft.js"}
    assert {n for n, p in found.items() if p.kind == "craft"} == CRAFT and {n for n, p in found.items() if p.kind == "craft-part"} == CRAFT_PARTS
    assert all(p.module == "vidgen/space-craft" for p in found.values())
    assert 'craft("probe", {seed: 1})' in found["craft-probe"].use and "fleet(" in found["craft-fleet"].use and "throttle" in found["plume-ion"].use
    assert all(len(p.label) <= 106 for p in found.values())                    # (longer labels are cut off on the sheet)
    assert "Math.random" not in (P.PARTS_DIR / "space-craft.js").read_text(encoding="utf-8")
    assert [p.kind for p in P.select_parts(P.read_parts(), kind="craft-part") if p.file == "space-craft.js"] == ["craft-part"] * len(CRAFT_PARTS)   # (the planes' parts share the kind)


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``C`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "space-craft")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as THREE from 'three';\nimport * as C from 'vidgen/space-craft';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const V = (x, y, z) => new THREE.Vector3(x, y, z), r4 = (x) => Math.round(x * 1e4) / 1e4;\n"
        "const sig = (c) => { let n = 0, s = 0; c.object.traverse((m) => { if (m.isMesh) { const p = m.geometry.attributes.position; n += p.count; for (let i = 0; i < p.count; i += 97) s += p.getX(i) + 2 * p.getY(i) + 3 * p.getZ(i); } }); return [n, r4(s)]; };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


@pytest.mark.slow
def test_every_craft_builds_from_its_seed(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
        for (const kind of Object.keys(C.CRAFT)) {
          const a = C.craft(kind, {seed: 3}), b = C.craft(kind, {seed: 3}), c = C.craft(kind, {seed: 4}), far = C.craft(kind, {seed: 3, detail: "far"});
          out.push({kind, same: JSON.stringify(sig(a)) === JSON.stringify(sig(b)), other: JSON.stringify(sig(a)) !== JSON.stringify(sig(c)), triangles: a.info.triangles, far: far.info.triangles,
            size: a.size, farSize: far.size, balls: a.occluders.length, engines: a.engines.length, lights: a.lights.length, wings: a.wings.length, accent: [a.kit.accent, far.kit.accent]});
        }
        const ring = C.craft("station", {seed: 2, ring: true});
        ring.update(2, {sun: [1, 0, 0]});
        out.push({spin: ring.spinners.length, turned: r4(ring.spinners[0].rotation.y), rate: r4(ring.spinners[0].userData.spin.rate)});
        out.push([err(() => C.craft("prob")), err(() => C.craft("probe", {sead: 2})), err(() => C.craftKit({detail: "close"})), err(() => C.craftKit().hull({shap: "box"})),
          err(() => C.craftKit().hull({skin: "foyl"})), err(() => C.attach(C.craftKit().hull(), "front", C.craftKit().dish())), err(() => C.craft("probe").update(0, {attitude: "sideways"})),
          err(() => C.craft("probe").update(0, {attitude: "target"}))]);
        const f = C.fleet("tug", {count: 4, seed: 9});
        out.push({fleet: f.craft.length, seeds: f.craft.map((c) => c.info.seed), far: f.craft.every((c) => c.kit.far), apart: f.craft[1].object.position.length() > f.craft[0].size.radius});
    """)
    kinds = {g["kind"]: g for g in got[:6]}
    assert set(kinds) == {"probe", "satellite", "station", "ship", "lander", "tug"}
    for g in kinds.values():
        assert g["same"] and g["other"]                                           # a seed is a craft; another seed another
        assert 20_000 < g["triangles"] < 120_000 and g["far"] < 0.45 * g["triangles"]
        assert abs(g["size"]["length"] - g["farSize"]["length"]) < 0.2 and g["accent"][0] == g["accent"][1]   # the same design at both details
        assert g["balls"] >= 8 and g["engines"] >= 1 and g["lights"] >= 1
    assert 9 < kinds["probe"]["size"]["width"] < 16 and 40 < kinds["ship"]["size"]["length"] < 65 and 18 < kinds["tug"]["size"]["length"] < 36
    assert 44 < max(kinds["station"]["size"].values()) < 70 and kinds["station"]["wings"] in (4, 8) and kinds["satellite"]["wings"] == 2
    ring = got[6]
    assert ring["spin"] == 1 and ring["turned"] == pytest.approx(2 * ring["rate"], abs=1e-3) and 0.35 < ring["rate"] < 0.45   # 0.3 g at 16 to 20 m
    errors = got[7]
    assert 'no craft "prob" (did you mean "probe"?)' in errors[0] and 'unknown option "sead" (did you mean "seed"?)' in errors[1]
    assert '"close"' in errors[2] and "near, far" in errors[2] and 'unknown option "shap" (did you mean "shape"?)' in errors[3]
    assert 'no surface "foyl" (did you mean "foil"?)' in errors[4] and 'no point "front"' in errors[5] and "fore" in errors[5]
    assert '"sideways"' in errors[6] and "prograde" in errors[6] and 'attitude "target" needs target' in errors[7]
    assert got[8] == {"fleet": 4, "seeds": [9, 10, 11, 12], "far": True, "apart": True}


def test_parts_join_at_their_points_and_attitudes_point_where_they_say(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
        const kit = C.craftKit({seed: 1, detail: "far"}), hull = kit.hull({radius: 1, length: 4}), dish = C.attach(hull, {angle: 90, along: 0.25}, kit.dish({diameter: 2}), "mount", {gap: 0.5});
        hull.updateMatrixWorld(true);
        const at = C.pointOf(hull, {angle: 90, along: 0.25}), up = V(0, 1, 0).applyQuaternion(dish.quaternion);
        out.push({place: dish.position.toArray().map(r4), want: at.p.clone().addScaledVector(at.n, 0.5).toArray().map(r4), up: up.toArray().map(r4), n: at.n.toArray().map(r4)});
        const ring = C.around(hull, () => kit.thrusters(), {count: 4, angle: 45, along: 0.5});
        out.push(ring.map((t) => Math.round(Math.atan2(t.position.z, t.position.x) * 180 / Math.PI)));
        const state = {velocity: V(0, 0, -7), radial: V(3, 0, 0), sun: V(0, 1, 0), target: V(1, 1, 0), thrust: V(0, 1, 0)}, ax = (q, a) => V(...a).applyQuaternion(q).toArray().map(r4);
        const q = (spec, t = 0) => C.attitudeAt(t, spec, state);
        out.push({prograde: [ax(q("prograde"), [0, 0, 1]), ax(q("prograde"), [0, 1, 0])], retro: ax(q("retrograde"), [0, 0, 1]), radial: ax(q("radial"), [0, 0, 1]),
          nadir: [ax(q("nadir"), [0, 1, 0]), ax(q("nadir"), [0, 0, 1])], sun: ax(q("sun"), [0, 1, 0]), sunX: ax(q({mode: "sun", axis: "-x"}), [-1, 0, 0]),
          target: ax(q("target"), [0, 0, 1]), thrust: ax(q("thrust"), [0, 0, 1]), fixed: ax(q({mode: "inertial", forward: [1, 0, 0], up: [0, 0, 1]}), [0, 0, 1])});
        const turn = ["prograde", {at: 2, turn: 4, mode: "radial"}], nose = (t) => ax(q(turn, t), [0, 0, 1]);
        out.push({before: nose(2), half: nose(4), after: nose(6), again: nose(4), early: nose(2.2), unit: r4(q(turn, 3.3).length())});
        const burns = [{frame: 60, dv: [0, 300, 0], magnitude: 300, label: "up"}, {frame: null, dv: [1, 0, 0], magnitude: 1}], w = C.burnWindows(burns, 30, {seconds: 2});
        out.push({w, throttle: [0.9, 1.05, 2, 2.9, 3.1].map((t) => r4(C.throttleAt(t, w))), weight: [-3, -0.6, 1, 2, 3, 3.5, 7].map((t) => r4(C.burnWeight(t, w[0], 2)))});
        out.push({track: [V(0, 0, 1), V(0, 1, 0), V(0, -1, 1), V(1, 0, 0)].map((s) => r4(C.trackAngle(s))), aim: C.aimAngles(V(0, 1, 0)).map(r4), aim2: C.aimAngles(V(1, 0, 0)).map(r4), aim3: C.aimAngles(V(0, -1, 0)).map(r4),
          blink: [0, 0.05, 0.1, 0.22, 0.5, 1.62].map((t) => C.blink("strobe", t)), beacon: [0.15, 0.6, 1.15].map((t) => r4(C.blink("beacon", t))), steady: C.blink("steady", 3.3),
          flicker: [0, 0.01, 0.5, 7.77].map((t) => C.flicker(t, 1)).every((f) => f > 0.85 && f < 1.15), same: C.flicker(1.234, 2) === C.flicker(1.234, 2)});
    """)
    assert got[0]["place"] == pytest.approx(got[0]["want"], abs=1e-3) and got[0]["up"] == pytest.approx(got[0]["n"], abs=1e-3)   # the dish stands on the hull, looking away from it
    assert sorted(got[1]) == [-135, -45, 45, 135]
    a = got[2]
    assert a["prograde"] == [[0, 0, -1], [1, 0, 0]] and a["retro"] == [0, 0, 1] and a["radial"] == [1, 0, 0]       # the nose along the velocity, the top away from the body
    assert a["nadir"] == [[1, 0, 0], [0, 0, -1]] and a["sun"] == [0, 1, 0] and a["sunX"] == [0, 1, 0]
    assert a["target"] == pytest.approx([0.7071, 0.7071, 0], abs=1e-3) and a["thrust"] == [0, 1, 0] and a["fixed"] == [1, 0, 0]
    t = got[3]
    assert t["before"] == [0, 0, -1] and t["after"] == [1, 0, 0] and t["half"] == pytest.approx([0.5, -0.7071, -0.5], abs=1e-3) and t["again"] == t["half"]   # half of the one turn (120 degrees) that takes nose and top across together
    assert t["early"][2] < -0.999 and t["unit"] == 1                              # eased: hardly moved a twentieth of the way in
    b = got[4]
    assert len(b["w"]) == 1 and b["w"][0]["start"] == 1 and b["w"][0]["end"] == 3 and b["w"][0]["direction"] == [0, 0, -1] and b["w"][0]["label"] == "up"   # data (x, y, z) is three's (x, z, -y)
    assert b["throttle"][0] == 0 and 0 < b["throttle"][1] < 1 and b["throttle"][2] == 1 and 0 < b["throttle"][3] < 1 and b["throttle"][4] == 0
    assert b["weight"][0] == 0 and 0 < b["weight"][1] < 1 and b["weight"][2:4] == [1, 1] and b["weight"][4] == 1 and 0 < b["weight"][5] < 1 and b["weight"][6] == 0
    m = got[5]
    assert m["track"] == pytest.approx([0, -1.5708, 0.7854, 0], abs=1e-3) and m["aim"] == [0, 0] and m["aim2"] == pytest.approx([1.5708, 1.5708], abs=1e-3) and m["aim3"][1] == 1.75
    assert m["blink"] == [1, 1, 0, 1, 0, 1] and m["beacon"][0] == 1 and m["beacon"][1] == 0 and m["beacon"][2] == 1 and m["steady"] == 1 and m["flicker"] and m["same"]


@pytest.mark.slow
def test_a_craft_follows_the_sun_a_burn_and_the_distance(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
        const sat = C.craft("satellite", {seed: 1, detail: "far"}), sun = V(0.3, 0.8, 0.5).normalize();
        sat.object.rotation.set(0.4, 1.1, -0.3); sat.update(0, {sun});
        out.push(sat.wings.map((w) => { const n = V(0, 0, 1).applyQuaternion(w.getWorldQuaternion(new THREE.Quaternion())), a = V(1, 0, 0).applyQuaternion(w.parent.getWorldQuaternion(new THREE.Quaternion()));
          return [r4(n.dot(sun)), r4(Math.sqrt(1 - a.dot(sun) ** 2))]; }));
        const ship = C.craft("ship", {seed: 1, detail: "far"}), aim = V(0.2, -0.9, 0.4).normalize();
        ship.update(0, {sun, target: aim});
        out.push(ship.dishes.map((d) => r4(V(0, 1, 0).applyQuaternion(d.el.getWorldQuaternion(new THREE.Quaternion())).dot(aim))));
        const lit = (t, o) => { ship.update(t, o); return [ship.engines.every((e) => e.plume.visible), r4(ship.engines[0].plume.material.uniforms.uNow.value.x), ship.thrusters.flat().some((p) => p.visible)]; };
        out.push([lit(1, {}), lit(1, {throttle: 1}), lit(1.01, {throttle: 1}), lit(1, {throttle: [1, 0, 0, 0, 0]}).slice(0, 1), lit(1, {rcs: 1})[2], lit(1, {throttle: (t) => t / 2})[1]]);
        // flown from orbit data: a burn straight "up" in the data (three's -z ... data (x, y, z) is three's (x, z, -y)) at frame 90 of 30 a second
        const orbits = {names: ["Earth", "Ship"], fps: 30, bodies: {Earth: {parent: null}, Ship: {parent: "Earth"}}, position: (n, t) => (n === "Ship" ? [7e6, 100 * t, 0] : [0, 0, 0]),
          velocity: (n) => (n === "Ship" ? [0, 7500, 0] : [0, 0, 0]), burns: () => [{frame: 90, dv: [0, 0, 250], magnitude: 250, label: "plane change"}]};
        const added = [], space = {orbits, add: (o, where) => added.push(where)};
        const tug = C.craft("tug", {seed: 1, detail: "far"}).fly(space, {body: "Ship", attitude: "prograde", burn: {seconds: 2, turn: 2}});
        const nose = (t) => { tug.update(t, {sun}); return V(0, 0, 1).applyQuaternion(tug.object.quaternion).toArray().map(r4).concat([tug.engines[0].plume.visible, tug.state.turning]); };
        out.push({added, windows: tug.burns, coast: nose(-1), turning: nose(-0.1), ready: nose(1.9), burning: nose(3), again: nose(3), off: nose(4.2), back: nose(7)});
        // Step 378: on a fast circular orbit (a quarter turn every 2 s) a prograde burn shown for 2 s stays prograde: the nose
        // follows the velocity of each moment, not the fixed line of the burn's instant
        const w = Math.PI / 4, circle = {names: ["Earth", "Ship"], fps: 30, bodies: {Earth: {parent: null}, Ship: {parent: "Earth"}},
          position: (n, t) => (n === "Ship" ? [7e6 * Math.cos(w * t), 7e6 * Math.sin(w * t), 0] : [0, 0, 0]), velocity: (n, t) => (n === "Ship" ? [-7e6 * w * Math.sin(w * t), 7e6 * w * Math.cos(w * t), 0] : [0, 0, 0]),
          burns: () => [{frame: 90, dv: [-Math.sin(3 * w) * 300, Math.cos(3 * w) * 300, 0], magnitude: 300, label: "prograde"}]};
        const fast = C.craft("tug", {seed: 1, detail: "far"}).fly({orbits: circle, add: () => {}}, {body: "Ship", attitude: "radial", burn: {seconds: 2, turn: 1}});
        const along = (t) => { fast.update(t, {sun}); const n = V(0, 0, 1).applyQuaternion(fast.object.quaternion), v = circle.velocity("Ship", t); return r4(n.dot(V(v[0], v[2], -v[1]).normalize())); };
        out.push({early: along(2.1), mid: along(3), late: along(3.9)});
        // far away: under a few pixels the craft is a point; turning, a flat face mirrors the sun for a moment
        const cam = new THREE.PerspectiveCamera(35, 16 / 9, 1, 1e6); cam.lookAt(0, 0, -1); cam.updateMatrixWorld();
        const far = C.craft("satellite", {seed: 2, detail: "far"}), levels = [];
        for (let n = 0; n < 90; n++) { const t = n / 30; far.object.position.set(600 + 90 * t, -250 + 30 * t, -9000); far.object.rotation.set(0.3 + 0.5 * t, 0.2 + 1.1 * t, 0.1); far.update(t, {sun: [0.5, 0.4, 0.75], camera: cam, height: 360}); levels.push(r4(far.glintLevel)); }
        const hidden = !far.root.visible && far.glint.visible;
        far.object.position.set(0, 0, -60); far.update(0, {sun: [0.5, 0.4, 0.75], camera: cam, height: 360});
        out.push({levels, hidden, near: far.root.visible && !far.glint.visible});
        const star = {occluders: [{object: new THREE.Object3D()}]}; far.shade(star); far.shade(star);
        out.push([star.occluders.length, far.occluders.length]);
    """)
    for facing, reach in got[0]:
        assert facing == pytest.approx(reach, abs=2e-3) and facing > 0.3              # each wing faces the sun as well as its one axis lets it
    assert got[1] and all(d > 0.999 for d in got[1])                              # the gimballed dish looks at the target
    off, on, later, one, puff, half = got[2]
    assert off == [False, 0, False] and on[0] and 0.85 < on[1] < 1.15 and later[1] != on[1] and one == [False] and puff and 0.4 < half < 0.6
    f = got[3]
    assert f["added"] == [{"body": "Ship"}] and f["windows"][0]["start"] == 2 and f["windows"][0]["end"] == 4 and f["windows"][0]["direction"] == [0, 1, 0]
    assert f["coast"][:4] == [0, 0, -1, False] and f["back"][:4] == [0, 0, -1, False]   # the nose along the velocity (data +y is three's -z)
    assert f["turning"][3] is False and f["turning"][4] == 1 and 0 < f["turning"][1] < 1   # turning toward the burn, thrusters puffing
    assert f["ready"][:4] == [0, 1, 0, False] and f["burning"][:4] == [0, 1, 0, True] and f["again"] == f["burning"] and f["off"][:4] == [0, 1, 0, False]
    steer = got[4]
    assert steer["early"] > 0.999 and steer["mid"] > 0.999 and steer["late"] > 0.999          # 45 degrees of the orbit either side of the burn
    g = got[5]
    levels = np.array(g["levels"])
    assert g["hidden"] and g["near"] and levels.min() > 0.5 and levels.max() > 4 * np.median(levels)      # a steady point, and a flash
    assert np.abs(np.diff(levels)).max() < 0.45 * levels.max() and (levels > 2 * np.median(levels)).sum() >= 5   # the flash rises and falls over several frames
    assert np.abs(np.diff(levels[20:])).max() < 0.02                                # no noise from frame to frame
    assert got[6][0] == 1 + got[6][1]                                              # shade() adds the craft's balls once


def test_the_surfaces_are_computed_from_numbers(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
        const foil = C.foilMaps(64, 1), again = C.foilMaps(64, 1), other = C.foilMaps(64, 2), plate = C.platingMaps(128, {seed: 1}), tiles = C.platingMaps(64, {tiles: 4, rivets: false}), cells = C.cellMaps(64, 2, 1);
        const spread = (a, k) => { let lo = 255, hi = 0; for (let i = k; i < a.length; i += 4) { lo = Math.min(lo, a[i]); hi = Math.max(hi, a[i]); } return hi - lo; };
        out.push({same: foil.normal.join() === again.normal.join(), other: foil.normal.join() !== other.normal.join(), tilt: spread(foil.normal, 0), gloss: spread(foil.orm, 1),
          panels: plate.panels, grooves: spread(plate.albedo, 0), tiles: tiles.panels, blue: cells.albedo[4 * (64 * 21 + 21) + 2] > 1.5 * cells.albedo[4 * (64 * 21 + 21)], metal: spread(cells.orm, 2),
          skins: C.SKINS.length, plumes: Object.keys(C.PLUMES), kinds: Object.keys(C.CRAFT), scales: Object.values(C.CRAFT).every((c) => / m/.test(c.scale))});
    """)[0]
    assert got["same"] and got["other"] and got["tilt"] > 120 and got["gloss"] > 40    # creases of every direction, facets of different gloss
    assert got["panels"] > 12 and got["grooves"] > 80 and got["tiles"] == 16 and got["blue"] and got["metal"] > 100
    assert got["plumes"] == ["chemical", "vacuum", "air", "ion", "rcs"] and got["kinds"] == ["probe", "satellite", "station", "ship", "lander", "tug"] and got["scales"]


PAGE = """
import * as THREE from "three";
import {star, spaceLight} from "vidgen/space-light";
import {SpaceView} from "vidgen/space-scale";
import {craft, craftKit, attach, paintedEnvironment, craftEnvironment} from "vidgen/space-craft";
window.made = {error: null};
let renderer, scene, camera, c, thing, light, sun, space;
export function load(ctx) {
  try {
    c = ctx.data;
    renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
    renderer.setSize(ctx.width, ctx.height, false);
    scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
    camera = new THREE.PerspectiveCamera(c.fov ?? 35, ctx.width / ctx.height, 0.5, 1e7);
    if (c.engine) { const kit = craftKit({seed: 1}), base = kit.hull({radius: 0.9, length: 0.6, skin: "aluminium"}); attach(base, "aft", kit.engine({exit: 0.5, kind: c.engine})); thing = kit.craft(base); }
    else thing = craft(c.kind ?? "probe", {seed: 1, detail: "far"});
    if (c.turn) thing.object.rotation.set(...c.turn);
    sun = star(renderer, "sun", {direction: c.sun ?? [0.7, 0.35, 0.6]}); scene.add(sun.object);
    if (c.space) { space = new SpaceView(ctx, {renderer, scene, camera, orbits: null}); space.add(thing.object, {at: [0, 0, 0]}); } else scene.add(thing.object);
    if (c.at) thing.object.position.set(...c.at);
    light = spaceLight({scene, camera, renderer, sun, at: thing.object, ...(c.shadows === false ? {} : {shadows: thing.shadows})});
    if (c.shade !== false) thing.shade(sun);
    const env = c.mirror ? craftEnvironment(renderer, scene, {at: thing.object}) : paintedEnvironment(renderer);
    scene.environment = env.texture;
    window.made.env = !!env.texture && env.texture.isTexture; window.made.triangles = thing.info.triangles;
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
export function frame(t) {
  try {
    const from = c.from ?? [3, 1, 6.2];
    if (space) space.update(t, {from: {offset: [from[0], -from[2], from[1]]}, to: {offset: [0, 0, 0]}});
    else { camera.position.set(...from); camera.lookAt(...(c.to ?? [0, 0, 0])); camera.updateMatrixWorld(); }
    thing.update(t, {sun, ...(c.update ?? {})}); sun.update(t); light.update(t);
    renderer.setRenderTarget(null); renderer.render(scene, camera);
    window.made.seen = sun.seen.fraction; window.made.slices = space ? space.slices.length : 0;
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
"""


@pytest.mark.slow
def test_craft_draw_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "craft.js").write_text(PAGE, encoding="utf-8")

    def draw(data: dict, frames: int = 1) -> tuple[list[np.ndarray], dict, dict]:
        with WebPage(tmp_path, WebEntry("script", "craft.js"), scene_id="s", size=(320, 180), fps=10, frames=frames, data=data) as page:
            got = [page.frame(n)[..., :3].astype(int) for n in range(frames)]
            made = page._page.evaluate("window.made")
            assert made["error"] is None, made["error"]
            return got, dict(page.loaded), made

    # a probe close up in the sun: gold foil (red over green over blue), the same picture twice, its own shadows
    close = {"turn": [-0.9, 2.3, 0.3]}
    (probe,), loaded, made = draw(close)
    (again,), _, _ = draw(close)
    (flat,), _, _ = draw({**close, "shadows": False})
    assert {"__vidgen__/modules/space-craft.js", "__vidgen__/modules/music-time.js", "__vidgen__/three/addons/utils/BufferGeometryUtils.js"} <= set(loaded)
    assert made["env"] and 5_000 < made["triangles"] < 12_000 and np.array_equal(probe, again)
    r, g, b = (probe[..., i] for i in range(3))
    gold = (r > 120) & (r > g + 25) & (g > b + 25)
    assert gold.sum() > 400 and (probe.max(axis=-1) < 6).sum() > 0.3 * gold.size      # foil in the sun before a black sky
    assert (np.abs(probe - flat).max(axis=-1) > 30).sum() > 150                     # shadows of the boom and the frames across the bus
    assert (flat.sum(axis=-1) > probe.sum(axis=-1) + 60).sum() > 100                # ... and they only darken
    # the craft's metal mirrors what is round it
    (mirror,), _, made = draw({**close, "mirror": True})
    assert made["env"] and (np.abs(mirror - probe).max(axis=-1) > 12).sum() > 200
    # an engine: no plume without throttle; with it, light behind the bell that flickers by the clock
    burn = {"engine": "chemical", "turn": [0.2, -1.95, 0.05], "from": [1.5, 1, 5], "shadows": False}
    (cold,), _, _ = draw(burn)
    (hot, hot2), _, _ = draw({**burn, "update": {"throttle": 1}}, frames=2)
    lit = hot - cold
    assert lit.min() >= -3 and lit[..., 0].sum() > 40_000 and lit[..., 0].sum() > 2.5 * lit[..., 2].sum()   # an amber plume, added light
    assert not np.array_equal(hot, hot2) and abs(float(hot2.sum()) / float(hot.sum()) - 1) < 0.1
    (ion,), _, _ = draw({**burn, "engine": "ion", "update": {"throttle": 1}})
    (ion0,), _, _ = draw({**burn, "engine": "ion"})
    assert (ion - ion0)[..., 2].sum() > 2 * (ion - ion0)[..., 0].sum() > 0          # an ion engine's beam is blue
    # before the sun: the craft hides its glare; without shade() it does not
    behind = {"kind": "tug", "sun": [0, 0, -1], "from": [0, 0, 0], "to": [0, 0, -1], "at": [-1.2, -0.36, -150], "turn": [0.3, 0.5, 0.2], "fov": 14, "shadows": False}
    (dark,), _, made = draw(behind)
    assert max(made["seen"]) < 0.05 and dark.mean() < 12
    (glare,), _, made = draw({**behind, "shade": False})
    assert min(made["seen"]) > 0.99 and glare.mean() > 3 * max(dark.mean(), 1)
    (clear,), _, made = draw({**behind, "at": [-30, -9, -150]})
    assert min(made["seen"]) > 0.99
    # inside vidgen/space-scale's depth slices the craft's own shadows are drawn too
    (sliced,), _, made = draw({**close, "space": True})
    (unshadowed,), _, _ = draw({**close, "space": True, "shadows": False})
    assert made["slices"] >= 1 and (np.abs(sliced - unshadowed).max(axis=-1) > 30).sum() > 150
