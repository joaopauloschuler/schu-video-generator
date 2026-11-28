"""Camera moves for space scenes, ``vidgen/space-camera`` (Step 375): the module is
served by its import name and imports only ``vidgen/music-time``; its framings are registered as
parts; in Node (when it is installed): a shot puts its subject where ``place`` says with a level
horizon; lenses and the long-lens arithmetic; every move is a function of its time (the same time,
the same shot, in any order), is continuous, keeps its subject in the frame and the camera outside
the world; a fly-by passes at its closest distance; an arc shows the phase asked for and "the sun
just off the limb"; an arrival ends over a level limb; a reveal's first light is at its time, for
the sun and for a moon; the craft views; a powers-of-ten zoom multiplies its distance by a constant
every second and rests on its landing points; the checks say what is wrong in sentences; the cuts;
a SpaceView gets the camera in the data's frame and a plain camera in three.js's; mistakes are
named with a did-you-mean. ``vidgen/space-scale``'s path lines near the camera (the fix of this
step). In Chromium (``slow``): the framings draw."""

from __future__ import annotations

import json
import math
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
MODULE = MODULES / "space-camera.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
CAMERA_PARTS = {"camera-three-quarter", "camera-crescent", "camera-fly-by", "camera-arrival", "camera-sunrise"}


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-camera"] == "space-camera.js"
    assert IMPORT_MAP["imports"]["vidgen/space-camera"] == "/__vidgen__/modules/space-camera.js"
    assert vidgen_file("modules/space-camera.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-camera.js"])["__vidgen__/modules/space-camera.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["vidgen/music-time"]                # no three.js: the mathematics runs anywhere
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-camera" not in engine_id()


def test_the_framings_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-camera.js"}
    assert set(found) == CAMERA_PARTS and all(p.kind == "camera" and p.module == "vidgen/space-camera" for p in found.values())
    assert "phase: {limb: 0.12}" in found["camera-crescent"].use and "cam.reveal(" in found["camera-sunrise"].use and "spaceCamera({space, camera})" in found["camera-three-quarter"].use
    assert all(len(p.label) <= 106 for p in found.values())
    assert [p.kind for p in P.select_parts(P.read_parts(), kind="camera") if p.file == "space-camera.js"] == ["camera"] * len(CAMERA_PARTS)


def _run_in_node(tmp_path: Path, body: str, names: tuple[str, ...] = ("music-time", "space-camera"), three: bool = False) -> list:
    """Import the module in Node as ``C`` and print ``out`` as JSON."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    if three:
        folder = tmp_path / "node_modules" / "three"
        folder.mkdir(parents=True)
        for name in ("three.module.js", "three.core.js"):
            (folder / name).symlink_to(DATA / "three" / name)
        (folder / "package.json").write_text(json.dumps({"name": "three", "type": "module", "exports": {".": "./three.module.js"}}), encoding="utf-8")
    ours = tmp_path / "node_modules" / "vidgen"
    ours.mkdir(parents=True)
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        f"import * as C from 'vidgen/{names[-1]}';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const R = 6.371e6, W = {at: [0, 0, 0], radius: R, name: 'World'}, SUN = [1, 0.2, 0.1];\n"
        "const ship = {at: (t) => { const a = t * 0.0011; return [7.2e6 * Math.cos(a), 7.2e6 * Math.sin(a), 0]; }, radius: 15, name: 'Ship'};\n"
        "const moon = {at: (t) => [3.8e8 * Math.cos(0.3 + t * 1e-3), 3.8e8 * Math.sin(0.3 + t * 1e-3), 2e7], radius: 1.737e6, name: 'Moon'};\n"
        "const deg = (a, b) => Math.atan2(C.len(C.cross(a, b)), C.dot(a, b)) * 180 / Math.PI;\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_shots_lenses_and_cuts_in_node(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
        const s = C.shotAt([10, -40, 6], [1, 2, 3], {up: [0, 0, 1], fov: 30, aspect: 16 / 9, place: [-1 / 3, 0.25]}), p = C.screenOf(s, [1, 2, 3]);
        out.push({x: p.x, y: p.y, level: s.right[2], unit: [C.len(s.right), C.len(s.up), C.len(s.forward)], square: [C.dot(s.right, s.up), C.dot(s.right, s.forward), C.dot(s.up, s.forward)],
          hand: C.dot(C.cross(s.forward, s.up), s.right), focus: s.focus, rolled: C.shotAt([10, -40, 6], [1, 2, 3], {roll: 20}).right[2]});
        // the same turn in both frames: the data's (camera looks along +y, top +z) and three's (-z, top +y)
        const qd = C.quaternionOfShot(s, "data"), qt = C.quaternionOfShot(s, "three");
        const rot = (q, v) => { const u = [q[0], q[1], q[2]], t = C.scale(C.cross(u, v), 2); return C.add(C.add(v, C.scale(t, q[3])), C.cross(u, t)); };
        out.push({data: C.len(C.sub(rot(qd, [0, 1, 0]), s.forward)) + C.len(C.sub(rot(qd, [0, 0, 1]), s.up)), three: C.len(C.sub(rot(qt, [0, 0, -1]), s.forward)) + C.len(C.sub(rot(qt, [0, 1, 0]), s.up))});
        out.push({normal: C.lens("normal"), long: C.lens(135).fov, fov: C.lens({fov: 40}).mm, share: C.frameShare(1, 10, 30), back: C.frameShare(1, C.distanceFor(1, 0.4, 30), 30)});
        const loom = C.loomLens({craft: 15, world: R, gap: 4e7, craftShare: 0.2, worldShare: 1.2});
        out.push({loom, craft: C.frameShare(15, loom.distance, loom.fov), world: C.frameShare(R, 4e7 + loom.distance, loom.fov), none: C.loomLens({craft: 15, world: 100, gap: 1e9})});
        out.push({before: C.flashCut(3.9, 4), at: C.flashCut(4, 4), after: C.flashCut(4.3, 4), gone: C.flashCut(5, 4), early: C.flashCut(3, 4), warp: [C.warpCut(2.5, 4), C.warpCut(4, 4), C.warpCut(5.5, 4), C.warpCut(9, 4)]});
        // a match cut: the next shot's sun drawn exactly where and as large as this shot's planet
        const cam = C.spaceCamera({up: [0, 0, 1], sun: SUN, aspect: 16 / 9}), a = cam.arc(0, {subject: W, phase: "half", distance: {radii: 6}}), disc = cam.disc(a, W);
        const m = C.matchDisc(disc, 6.96e8, C.lens("long").fov), star = {at: [0, 0, 0], radius: 6.96e8}, b = cam.arc(0, {subject: star, sun: [0, 1, 0], phase: 40, distance: m.distance, place: m.place, lens: "long"});
        out.push({disc, next: cam.disc(b, star), px: C.discPixels(disc, 720)});
        out.push({ease: [C.eased(0.5, 1), C.eased(0.25, 0), C.eased(0.1, 1)], progress: [C.progressOf(5, [4, 8]), C.progressOf(1, [4, 8]), C.progressOf(9, [4, 8])], breathe: [C.breathe(3.3, 1, 2), C.breathe(3.3, 1, 2), C.breathe(3.3, 0, 2)]});
        out.push([err(() => C.lens("nomal")), err(() => C.spaceCamera({sunn: 1})), err(() => cam.arc(0, {subject: W, phase: "cresent"})), err(() => cam.follow(0, {subject: ship, view: "chaise"})),
          err(() => cam.flyBy(0, {subject: W})), err(() => cam.arc(0, {subject: "Earth"})), err(() => C.spaceCamera().arc(0, {subject: W})), err(() => cam.zoom(0, {stops: [{subject: W, distance: 5}]})),
          err(() => C.progressOf(1, [4, 4])), err(() => cam.flyBy(0, {subject: W, progress: 0.5, sid: "left"})), err(() => cam.follow(0, {subject: ship, view: "shoulder"}))]);
    """)
    shot, quats, lenses, loom, cuts, match, shapes, errors = got
    assert shot["x"] == pytest.approx(-1 / 3, abs=1e-12) and shot["y"] == pytest.approx(0.25, abs=1e-12)       # the subject is where place says
    assert abs(shot["level"]) < 1e-15 and shot["unit"] == pytest.approx([1, 1, 1]) and max(abs(v) for v in shot["square"]) < 1e-15 and shot["hand"] == pytest.approx(1)
    assert shot["focus"] > 0 and 0.2 < abs(shot["rolled"]) < 0.36                                                 # rolled 20 degrees, the horizon is not level
    assert quats["data"] < 1e-12 and quats["three"] < 1e-12
    assert lenses["normal"] == {"mm": 50, "fov": pytest.approx(26.99, abs=0.01), "name": "normal"} and lenses["long"] == pytest.approx(10.16, abs=0.01)
    assert lenses["fov"] == pytest.approx(32.97, abs=0.01) and lenses["share"] == pytest.approx(0.3751, abs=1e-3) and lenses["back"] == pytest.approx(0.4)
    assert loom["craft"] == pytest.approx(0.2, rel=1e-6) and loom["world"] == pytest.approx(1.2, rel=1e-6) and loom["none"] is None
    assert loom["loom"]["wide"] < 0.5 < 1.2 and 3 < loom["loom"]["fov"] < 30                                 # a wide lens shows the same craft before a far smaller world
    assert 0 < cuts["before"] < cuts["at"] == 3 and 0 < cuts["after"] < 3 and cuts["gone"] == 0 and cuts["early"] == 0 and cuts["warp"] == [0, 0.5, 1, 1]
    assert match["next"]["radius"] == pytest.approx(match["disc"]["radius"], rel=1e-9) and match["next"]["x"] == pytest.approx(match["disc"]["x"], abs=1e-9)
    assert match["px"] == pytest.approx(match["disc"]["radius"] * 360)
    assert shapes["ease"][0] == pytest.approx(0.5) and shapes["ease"][1] == 0.25 and shapes["ease"][2] < 0.02 and shapes["progress"] == [0.25, 0, 1]
    assert shapes["breathe"][0] == shapes["breathe"][1] and shapes["breathe"][2] == {"yaw": 0, "pitch": 0, "push": 0} and abs(shapes["breathe"][0]["yaw"]) <= 2.4
    assert 'no lens "nomal" (did you mean "normal"?)' in errors[0] and 'unknown option "sunn" (did you mean "sun"?)' in errors[1]
    assert 'no phase "cresent" (did you mean "crescent"?)' in errors[2] and 'no view "chaise" (did you mean "chase"?)' in errors[3]
    assert "flyBy needs progress (0..1) or over" in errors[4] and "a name needs a SpaceView" in errors[5] and "needs to know where the sun is" in errors[6]
    assert "two or more" in errors[7] and "end after start" in errors[8] and '"sid" (did you mean "side"?)' in errors[9] and 'view "shoulder" needs target' in errors[10]
    assert all(e.startswith("vidgen/space-camera: ") for e in errors)


def test_every_move_is_a_smooth_function_of_time_in_node(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
        const cam = C.spaceCamera({up: [0, 0, 1], sun: SUN, aspect: 16 / 9, bodies: [W]});
        const moves = {
          flyBy: (u) => cam.flyBy(0, {subject: W, progress: u, closest: {radii: 2.2}, side: "left", roll: 10}),
          arc: (u) => cam.arc(0, {subject: W, progress: u, phase: ["three-quarter", "crescent"], distance: [{radii: 5}, {radii: 4}]}),
          arrive: (u) => cam.arrive(0, {subject: W, progress: u, lens: "wide"}),
          reveal: (u) => cam.reveal(u * 10, {behind: W, at: 5, rate: 0.5}),
          follow: (u) => cam.follow(u * 8, {subject: ship, around: W, view: "chase"}),
          shoulder: (u) => cam.follow(u * 8, {subject: ship, around: W, view: "shoulder", target: moon}),
          pass: (u) => cam.pass(u * 4, {subject: ship, around: W, progress: u}),
          zoom: (u) => cam.zoom(u * 14, {stops: [{subject: ship, distance: 100}, {subject: W, distance: {radii: 5}}, {subject: W, distance: 1e9}]}),
        };
        for (const [name, move] of Object.entries(moves)) {
          const n = 400, shots = []; for (let i = 0; i <= n; i++) shots.push(move(i / n));
          const again = [397, 3, 200, 0, 400].map((i) => JSON.stringify(move(i / n)) === JSON.stringify(shots[i])).every(Boolean);     // any order, the same shot
          const steps = shots.slice(1).map((s, i) => C.len(C.sub(s.from, shots[i].from))), turns = shots.slice(1).map((s, i) => deg(s.forward, shots[i].forward));
          const jump = Math.max(...steps.slice(1).map((v, i) => Math.abs(v - steps[i]))) / Math.max(...steps, 1e-300);
          const sub = shots.map((s) => C.screenOf(s, s.subject.at)), unit = Math.max(...shots.map((s) => Math.abs(C.len(s.forward) - 1) + Math.abs(C.dot(s.forward, s.up)) + Math.abs(C.dot(s.right, s.up))));
          out.push({name, again, jump, turn: Math.max(...turns), x: [Math.min(...sub.map((p) => p.x)), Math.max(...sub.map((p) => p.x))], y: [Math.min(...sub.map((p) => p.y)), Math.max(...sub.map((p) => p.y))],
            nearest: Math.min(...shots.map((s) => C.len(s.from))) / R, unit, ends: [steps[0], steps[n / 2], steps[n - 1]], check: cam.check(move, {steps: 60}).filter((c) => !c.includes("unlit side"))});   // the fixture's sun is not chosen for the light
        }
    """)
    by = {g["name"]: g for g in got}
    for g in got:
        assert g["again"], g["name"]                                             # a function of its time and nothing else
        assert g["jump"] < 0.05 and g["unit"] < 1e-12, (g["name"], g["jump"])   # the speed changes by under a twentieth of its peak from step to step
        assert g["nearest"] > 1.05, g["name"]                                    # never inside the world, never at its ground
    assert by["flyBy"]["x"] == pytest.approx([-0.36, 0.3], abs=1e-9) and by["flyBy"]["nearest"] == pytest.approx(2.2, abs=1e-3) and by["flyBy"]["check"] == []
    assert by["flyBy"]["ends"][1] < 0.6 * by["flyBy"]["ends"][0]               # it lingers at the pass
    assert by["arc"]["x"][0] == pytest.approx(by["arc"]["x"][1], abs=2e-3) and 0.3 < by["arc"]["x"][0] < 0.36 and by["arc"]["check"] == [] and by["arc"]["turn"] < 1
    assert by["arrive"]["nearest"] == pytest.approx(1.07, abs=1e-6) and by["arrive"]["turn"] < 1.5 and by["arrive"]["check"] == []
    assert by["reveal"]["x"][0] == pytest.approx(0.18) and by["reveal"]["check"] == [] and by["reveal"]["turn"] < 0.1
    assert by["follow"]["check"] == [] and by["follow"]["x"] == pytest.approx([-0.16, -0.16]) and by["follow"]["y"] == pytest.approx([-0.12, -0.12])
    assert by["shoulder"]["check"] == [] and -0.6 < by["shoulder"]["x"][0] and by["shoulder"]["x"][1] < 0 and by["shoulder"]["y"][1] < 0      # the craft low on the left, its target up on the right
    assert by["pass"]["check"] == [] and by["pass"]["turn"] > 1                 # a whip pan, and no jump in it
    assert by["zoom"]["turn"] < 0.5 and [c for c in by["zoom"]["check"] if "px in radius" not in c] == []


def test_the_moves_numbers_in_node(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
        const cam = C.spaceCamera({up: [0, 0, 1], sun: SUN, aspect: 16 / 9, bodies: [W]}), s = C.unit(SUN);
        // arc: the phase asked for; the sun just off the limb
        const phase = (o) => { const a = cam.arc(0, {subject: W, ...o}); return deg(C.sub(a.from, W.at), s); };
        const limb = cam.arc(0, {subject: W, phase: {limb: 0.15}, distance: {radii: 4}}), sunAt = C.screenOf(limb, C.add(limb.from, C.scale(s, 1e15))), d = C.discOf(limb, W.at, R);
        out.push({front: phase({phase: "front"}), crescent: phase({phase: "crescent"}), num: phase({phase: 77}), gap: Math.hypot((sunAt.x - d.x) * 16 / 9, sunAt.y - d.y) / d.radius, world: [d.x, d.y], sun: [sunAt.x, sunAt.y, sunAt.inFrame],
          side: [C.screenOf(cam.arc(0, {subject: W, phase: 120, around: 0}), C.add(W.at, C.scale(s, 1e15))).x < 0, C.screenOf(cam.arc(0, {subject: W, phase: 120, around: 180}), C.add(W.at, C.scale(s, 1e15))).x > 0]});
        // arrive: far and small, then low over a level limb at `horizon`
        const a0 = cam.arrive(0, {subject: W, progress: 0, lens: "wide"}), a1 = cam.arrive(0, {subject: W, progress: 1, lens: "wide", horizon: -0.4}), up1 = C.unit(a1.from);
        const edge = C.screenOf(a1, a1.subject.at), dawn = cam.arrive(0, {subject: W, progress: 1, lens: "wide", sunAhead: 9}), sunD = C.screenOf(dawn, C.add(dawn.from, C.scale(s, 1e15)));
        out.push({start: [a0.altitude / R, C.discOf(a0, W.at, R).radius, C.screenOf(a0, W.at).x], end: [a1.altitude / R, C.dot(a1.right, up1), edge.x, edge.y, C.dot(a1.up, up1)], dawn: [sunD.x, sunD.y, sunD.inFrame, C.screenOf(dawn, dawn.subject.at).y]});
        // reveal: the sun's upper edge meets the limb at `at`; a moon's too, where the moon is then
        const el = (t, o) => { const r = cam.reveal(t, {behind: W, at: 5, rate: 0.5, ...o}); return [r.elevation, r.seen]; };
        const mr = (t) => { const r = cam.reveal(t, {behind: W, of: moon, at: 5, rate: 0.25, distance: {radii: 7}, lens: "tele", place: [0, 0], horizon: -0.3}); const m = moon.at(t), toM = C.sub(m, r.from), toW = C.sub(W.at, r.from);
          return [deg(toM, toW) - Math.asin(R / C.len(toW)) * 180 / Math.PI + Math.asin(moon.radius / C.len(toM)) * 180 / Math.PI, r.seen, C.screenOf(r, m).x, C.dot(r.right, C.unit(r.from))]; };
        out.push({sun: [el(4.9), el(5), el(5.1), el(7)], air: el(5, {air: 0.1})[0], bars: cam.reveal(0, {behind: W, at: 12, time: 12, rate: 0.5}).elevation, moon: [mr(4.5), mr(5), mr(5.5)], airMargin: C.airMargin(R, R + 4.46e5)});
        // follow: every view frames the craft; locked to the flight; it breathes and closes in
        const views = Object.keys(C.VIEWS).map((v) => { const f = cam.follow(2, {subject: ship, around: W, view: v, target: moon, drift: 0}), p = C.screenOf(f, ship.at(2)); return [v, p.x, p.y, p.inFrame, C.frameShare(15, f.distance, f.fov), cam.problems(2, f).filter((c) => !c.includes("unlit side")).length]; });
        const f0 = cam.follow(2, {subject: ship, around: W, drift: 0}), vel = C.unit(C.sub(ship.at(2.001), ship.at(1.999))), hz = cam.follow(2, {subject: ship, around: W, view: "horizon", drift: 0});
        const tangent = (() => { const toShip = C.unit(C.sub(ship.at(2), hz.from)), toW = C.sub(W.at, hz.from); return deg(toShip, toW) - Math.asin(R / C.len(toW)) * 180 / Math.PI; })();
        out.push({views, forward: C.dot(f0.frame.forward, vel), behind: C.dot(C.sub(f0.from, ship.at(2)), vel) < 0, above: C.len(f0.from) > C.len(ship.at(2)), tangent,
          drift: deg(cam.follow(2, {subject: ship, around: W}).forward, f0.forward), push: cam.follow(8, {subject: ship, around: W, drift: 0, over: [0, 8], push: 0.7}).distance / f0.distance,
          stars: cam.follow(2, {subject: ship, around: W, lock: "stars", drift: 0}).frame.up, held: cam.subject({at: [1, 2, 3], radius: 2}, 0).velocity()});
        // pass: the craft comes from ahead, passes at its closest and flies on
        const pd = [0, 0.5, 0.58, 1].map((u) => { const p = cam.pass(u * 4, {subject: ship, around: W, progress: u}); return [C.dot(C.sub(p.from, ship.at(u * 4)), C.unit(C.sub(ship.at(u * 4 + 1e-3), ship.at(u * 4 - 1e-3)))), p.distance / 15, p.fov]; });
        const locked = [0.3, 0.6].map((u) => cam.pass(0, {subject: ship, around: W, progress: u, track: false}).forward);
        out.push({pd, closest: Math.min(...Array.from({length: 401}, (_, i) => cam.pass(0, {subject: ship, around: W, progress: i / 400}).distance)) / 15, locked: deg(locked[0], locked[1])});
    """)
    arc, arrive, reveal, follow, passing = got
    assert arc["front"] == pytest.approx(0, abs=1e-6) and arc["crescent"] == pytest.approx(135) and arc["num"] == pytest.approx(77)
    assert arc["gap"] == pytest.approx(1.15, abs=0.02) and arc["sun"][2] is True and arc["sun"][0] < arc["world"][0] and arc["side"] == [True, True]   # the sun 0.15 radii off the limb, the world on the other third
    assert arrive["start"][0] == pytest.approx(13) and arrive["start"][1] < 0.2 and arrive["start"][2] == pytest.approx(0.3)                          # small, off the middle
    assert arrive["end"][0] == pytest.approx(0.07) and abs(arrive["end"][1]) < 1e-12 and arrive["end"][2] == pytest.approx(0, abs=1e-9) and arrive["end"][3] == pytest.approx(-0.4, abs=1e-9)
    assert arrive["end"][4] > 0.9 and arrive["dawn"][2] is True and arrive["dawn"][1] > arrive["dawn"][3]                                             # level; at a dawn the sun stands over the limb, in the frame
    before, at, after, late = reveal["sun"]
    assert at[0] == pytest.approx(-0.2665, abs=1e-9) and at[1] < 1e-9 and before[1] == 0 and 0 < after[1] < 0.2 and late[1] == 1                         # first light exactly at `at`
    assert after[0] - at[0] == pytest.approx(0.05, abs=1e-9) and reveal["air"] == pytest.approx(-0.2665, abs=1e-9) and reveal["bars"] == pytest.approx(-0.2665, abs=1e-9)
    assert reveal["moon"][0][0] < -0.05 and abs(reveal["moon"][1][0]) < 1e-6 and reveal["moon"][2][0] > 0.05                                         # the moon's upper edge on the limb at 5 s
    assert all(abs(m[2]) < 1e-9 and abs(m[3]) < 1e-12 for m in reveal["moon"]) and reveal["airMargin"] == pytest.approx(0.196, abs=0.01)
    views = {v[0]: v for v in follow["views"]}
    assert set(views) == {"chase", "lead", "three-quarter", "side", "shoulder", "small", "horizon"} and all(v[3] is True and v[5] == 0 for v in views.values())
    assert views["chase"][1:3] == pytest.approx([-0.16, -0.12]) and views["small"][4] == pytest.approx(0.06) and views["horizon"][4] == pytest.approx(0.3)
    assert follow["forward"] == pytest.approx(1, abs=1e-6) and follow["behind"] and follow["above"] and -1.2 < follow["tangent"] < 0                 # the sight line through the craft meets the world just inside its limb
    assert 0.05 < follow["drift"] < 4 and follow["push"] == pytest.approx(0.7) and follow["stars"] == [0, 0, 1] and follow["held"] == [0, 0, 0]
    assert passing["pd"][0][0] > 20 and passing["pd"][-1][0] < -15 and passing["closest"] == pytest.approx(2.5, abs=0.01) and passing["pd"][0][2] == pytest.approx(73.74, abs=0.01)
    assert passing["locked"] == pytest.approx(0, abs=1e-9)                                                                                             # a locked-off frame does not turn


def test_the_powers_of_ten_zoom_and_the_checks_in_node(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
        const cam = C.spaceCamera({up: [0, 0, 1], sun: SUN, aspect: 16 / 9, bodies: [W]});
        const plan = C.zoomPlan([100, 1e5, 1e9], {hold: 1, ease: 0.6});
        const at = (t) => C.zoomAt(plan, t), ratio = (t) => at(t + 1).distance / at(t).distance;
        out.push({seconds: plan.seconds, legs: plan.legs.map((l) => [l.start, l.end]), ratios: [ratio(1), ratio(3), ratio(5.8), ratio(9), ratio(12)], ends: [at(0).distance, at(plan.seconds).distance, at(-3).distance, at(99).distance],
          rest: [at(7).distance, at(7).resting, at(7).speed, at(3).resting, at(3).speed], mono: Array.from({length: 300}, (_, i) => at(i * plan.seconds / 299).distance).every((d, i, a) => i === 0 || d >= a[i - 1]),
          fit: C.zoomPlan([100, 1e9], {seconds: 10}).seconds, into: C.zoomAt(C.zoomPlan([1e9, 100], {ease: 0}), 2).distance, steady: C.zoomPlan([1, 1e3, 1e6], {ease: 0}).legs.map((l) => [l.easeIn, l.easeOut]),
          bad: [err(() => C.zoomPlan([5])), err(() => C.zoomPlan([5, 5])), err(() => C.zoomPlan([1, 10], {rate: 0.5})), err(() => C.zoomPlan([1, 10, 100], {seconds: 1, hold: 2}))]});
        const z = (t, o = {}) => cam.zoom(t, {stops: [{subject: ship, distance: 100}, {subject: W, distance: {radii: 5}, hold: 1}, {subject: W, distance: 1e9}], ...o});
        const line = [0.5, 1.5, 2.5, 3.5].map((t) => cam.zoom(t, {stops: [{subject: W, distance: {radii: 2}}, {subject: W, distance: 1e9}]}).from), dir = (a, b) => C.unit(C.sub(b, a));
        out.push({first: [C.len(C.sub(z(0).from, ship.at(0))), C.screenOf(z(0), ship.at(0))], last: [C.len(z(99).from), C.screenOf(z(99), W.at).x], straight: deg(dir(line[0], line[1]), dir(line[2], line[3])), power: z(3).power, middle: [z(3).place, z(3).resting, z(3).seconds],
          over: [z(4, {over: [4, 12]}).distance, z(12, {over: [4, 12]}).distance, z(8, {over: [4, 12]}).seconds], start: z(5, {start: 5}).distance});
        // the checks: inside a world, at its ground, through it, out of frame, too small, hidden, a jump
        const inside = C.shotAt([0, 0, R * 0.5], [1e8, 0, 0]), low = C.shotAt([0, 0, R + 800], [1e8, 0, 0]), away = C.shotAt([0, 0, 3 * R], [0, 0, 9 * R]), far = cam.arc(0, {subject: W, distance: 4e10}), behind = C.shotAt([-3 * R, 0, 0], [3 * R, 0, 0]);
        out.push({inside: cam.problems(0, inside), low: cam.problems(0, low), away: cam.problems(0, away, {subject: W}), far: cam.problems(0, far), tiny: cam.problems(0, far, {minPixels: 0.01}), hidden: cam.problems(0, behind, {subject: {at: [3 * R, 0, 0], radius: 10, name: "Probe"}}),
          box: cam.problems(0, cam.arc(0, {subject: W, place: [0.5, 0]}), {box: [-0.4, -0.4, 0.4, 0.4]}), fine: cam.problems(0, cam.arc(0, {subject: W})),
          through: cam.check((t) => C.shotAt([-3 * R + 6 * R * t, 0, 0.2 * R], [9 * R, 0, 0]), {steps: 3}), kink: cam.check((t) => C.shotAt([3 * R, 0, 0], t < 0.5 ? [9 * R, t * R, 0] : [9 * R, 0, 4 * R]), {steps: 20}),
          bank: cam.check((t) => cam.flyBy(0, {subject: W, progress: t, closest: {radii: 2}, roll: 12}), {steps: 40})});
    """)
    plan, zoom, checks = got
    assert plan["ratios"][:2] == pytest.approx([math.sqrt(10)] * 2) and plan["ratios"][3:] == pytest.approx([math.sqrt(10)] * 2)     # every second multiplies the distance by one constant
    assert plan["ratios"][2] < math.sqrt(10) and plan["ends"] == pytest.approx([100, 1e9, 100, 1e9]) and plan["mono"]
    assert plan["legs"][0] == pytest.approx([0, 6.6]) and plan["legs"][1] == pytest.approx([7.6, 16.2]) and plan["seconds"] == pytest.approx(16.2)
    assert plan["rest"][0] == pytest.approx(1e5) and plan["rest"][1] is True and plan["rest"][2] == 0 and plan["rest"][3] is False and plan["rest"][4] == pytest.approx(0.5)
    assert plan["fit"] == pytest.approx(10) and plan["into"] == pytest.approx(1e8) and plan["steady"] == [[True, False], [False, True]]
    assert "two or more distances" in plan["bad"][0] and "must differ" in plan["bad"][1] and "rate must be above 1" in plan["bad"][2] and "no time left" in plan["bad"][3]
    assert zoom["first"][0] == pytest.approx(100) and abs(zoom["first"][1]["x"]) < 1e-9 and abs(zoom["first"][1]["y"]) < 1e-9                # the zoom's axis is the frame's middle
    assert zoom["last"][0] == pytest.approx(1e9) and abs(zoom["last"][1]) < 1e-9 and zoom["straight"] < 1e-3 and zoom["middle"][0] == [0, 0]  # away from one subject: one straight line
    assert zoom["over"][0] == pytest.approx(100) and zoom["over"][1] == pytest.approx(1e9) and zoom["over"][2] == pytest.approx(8) and zoom["start"] == pytest.approx(100)
    assert "the camera is inside World" in checks["inside"][0] and "a sphere is no ground" in checks["low"][0] and "800 m above World" in checks["low"][0]
    assert checks["away"] == ["World is behind the camera"] and "px in radius, under 3" in checks["far"][0] and checks["tiny"] == [] and checks["hidden"][-1] == "Probe is hidden behind World"
    assert "outside its box" in checks["box"][0] and checks["fine"] == [] and checks["bank"] == []
    assert any("goes through World" in c for c in checks["through"]) and any("a jump in the move" in c for c in checks["kink"])


def test_the_rig_places_a_space_view_and_a_plain_camera_in_node(tmp_path: Path) -> None:
    got = _run_in_node(tmp_path, """
        // a stand-in SpaceView: two bodies of "orbit data", the Sun among them
        const places = {Sun: () => [-1.5e11, 0, 0], Earth: () => [0, 0, 0], Ship: (t) => [7e6 * Math.cos(t * 1e-3), 7e6 * Math.sin(t * 1e-3), 0]}, radii = {Sun: 6.96e8, Earth: R, Ship: 0};
        const frozen = {Ship: (t) => places.Ship(Math.min(t, 2))};
        const view = (at) => ({orbits: {names: ["Sun", "Earth", "Ship"], bodies: {Sun: {parent: null}, Earth: {parent: "Sun"}, Ship: {parent: "Earth"}}, speedup: 20, velocity: (n) => (n === "Ship" ? [0, 350, 0] : [0, 0, 0])}, camera: {fov: 50, aspect: 2, updateProjectionMatrix() { this.updated = true; }},
          renderer: {domElement: {height: 1080}}, at: (n, t) => (at[n] ?? places[n])(t), radius: (n) => radii[n], update(t, v) { this.got = [t, v]; return this; }});
        const space = view({}), cam = C.spaceCamera({space}), shot = cam.apply(3, cam.arc(3, {subject: "Earth", phase: "half", lens: "long"}));
        out.push({up: cam.up, aspect: cam.aspect, height: cam.height, fov: space.camera.fov, updated: space.camera.updated === true, t: space.got[0], from: space.got[1].from, q: space.got[1].quaternion, want: C.quaternionOfShot(shot, "data"), eye: shot.from,
          sun: cam.toSun([0, 0, 0], 0), phase: deg(C.sub(shot.from, [0, 0, 0]), [-1, 0, 0]), kept: cam.shot === shot});
        // a craft by its body's name, by {body, offset}, and as a flown craft; near its world the horizon is the world's
        const craft = {flight: {body: "Ship"}, size: {radius: 22}, object: {isObject3D: true}}, f = cam.follow(1, {subject: craft, drift: 0}), p = cam.pass(1, {subject: craft, progress: 0.2});
        out.push({name: f.subject.name, radius: f.subject.radius, levelFollow: C.dot(f.right, C.unit(f.from)), levelPass: C.dot(p.right, C.unit(p.from)), offset: cam.subject({body: "Ship", offset: [0, 0, 5]}, 1).at[2],
          zoom: C.dot(C.unit(C.sub(cam.zoom(0, {stops: [{subject: "Ship", distance: 50}, {subject: "Earth", distance: {radii: 4}}]}).from, places.Ship(0))), [1, 0, 0]),
          lit: C.dot(C.unit(cam.zoom(0, {stops: [{subject: "Earth", distance: {radii: 4}}, {subject: "Sun", distance: 3e11}]}).from), [-1, 0, 0]),
          worlds: cam.problems(0, C.shotAt([0, 0, R / 2], [1, 0, 0])).length, object: err(() => cam.subject({isObject3D: true, position: {x: 0, y: 0, z: 0}}, 0))});
        // on the frames a scene holds after its data's end nothing moves: the data's velocity keeps the camera's frame
        const held = C.spaceCamera({space: view(frozen)}).follow(5, {subject: "Ship", drift: 0});
        out.push({forward: held.frame.forward, inFrame: C.screenOf(held, frozen.Ship(5)).inFrame});
        // a plain three.js scene: y up, objects as subjects, the camera set itself
        const camera = {fov: 40, aspect: 1.5, position: {set(...v) { this.v = v; }}, quaternion: {set(...q) { this.q = q; }}, updateProjectionMatrix() {}, updateMatrixWorld() { this.done = true; }};
        const earth = {object: {isObject3D: true, position: {x: 2, y: 0, z: -1}, scale: {x: 3}}}, rig = C.spaceCamera({camera, sun: {infinite: true, direction: {isVector3: true, x: 0, y: 0, z: 1}}, bodies: [earth]});
        const a = rig.apply(0, rig.arc(0, {subject: earth, phase: "front", distance: {radii: 4}}));
        out.push({up: rig.up, v: camera.position.v, q: camera.quaternion.q, want: C.quaternionOfShot(a, "three"), done: camera.done, radius: a.subject.radius, level: a.right[1], inside: rig.problems(0, C.shotAt([2, 1, -1], [9, 9, 9])).length,
          starThree: C.spaceCamera({space, sun: {infinite: true, direction: {isVector3: true, x: 0, y: 1, z: 0}}}).toSun([0, 0, 0])});
    """)
    placed, craft, held, plain = got
    assert placed["up"] == [0, 0, 1] and placed["aspect"] == 2 and placed["height"] == 1080 and placed["fov"] == pytest.approx(10.16, abs=0.01) and placed["updated"] and placed["t"] == 3
    assert placed["from"] == {"offset": placed["eye"]} and placed["q"] == placed["want"] and placed["kept"]            # float64, untouched, to space.update
    assert placed["sun"] == pytest.approx([-1, 0, 0]) and placed["phase"] == pytest.approx(90)
    assert craft["name"] == "Ship" and craft["radius"] == 22 and abs(craft["levelFollow"]) < 1e-9 and abs(craft["levelPass"]) < 1e-9 and craft["offset"] == 5
    assert craft["zoom"] > 0.6 and craft["lit"] > 0.3 and craft["worlds"] == 1 and "with a SpaceView an object's place is the camera's own" in craft["object"]
    assert held["forward"] == pytest.approx([0, 1, 0]) and held["inFrame"] is True
    assert plain["up"] == [0, 1, 0] and plain["v"] == pytest.approx([2, 0, 11]) and plain["q"] == plain["want"] and plain["done"] and plain["radius"] == 3 and abs(plain["level"]) < 1e-12
    assert plain["inside"] == 1 and plain["starThree"] == pytest.approx([0, 0, 1])                                     # a star's three.js direction, in the data's frame


def test_a_path_line_is_cut_short_near_the_camera_in_node(tmp_path: Path) -> None:
    """``vidgen/space-scale`` (this step's fix): a path's piece far longer than its distance from the camera
    is drawn as shorter pieces, the same straight line."""
    got = _run_in_node(tmp_path, """
        const a = [-26000, 300, 0], b = [26000, 300, 0], cuts = C.nearCuts(a, b, 300), pts = [0, ...cuts, 1].map((u) => C.add(a, C.scale(C.sub(b, a), u)));
        const worst = Math.max(...pts.slice(1).map((p, i) => C.norm(C.sub(p, pts[i])) / Math.max(300, C.segmentDistance(pts[i], p))));
        out.push({n: cuts.length, rising: cuts.every((u, i) => i === 0 || u > cuts[i - 1]), nearest: cuts.includes(0.5), worst, short: C.nearCuts([0, 300, 0], [900, 300, 0], 300), none: C.nearCuts(a, b, 300, 0), spare: C.PATH_SPARE,
          on: C.nearCuts([-1e4, 0, 0], [1e4, 0, 0], 0).length, capped: C.nearCuts(a, b, 300, 5).length});
    """, names=("space-scale",), three=True)
    cut = got[0]
    assert 10 <= cut["n"] <= 48 and cut["rising"] and cut["nearest"] and cut["worst"] <= 4.01 and cut["short"] == [] and cut["none"] == [] and cut["spare"] == 96
    assert 0 < cut["on"] <= 48 and cut["capped"] <= 5
    source = (MODULES / "space-scale.js").read_text(encoding="utf-8")
    assert "o.userData.nearest * 0.999 * cx * cy" in source                      # a line's nearest distance is not its depth at the frame's corner


def test_follow_rides_on_the_sunlit_side_and_says_when_the_craft_is_unlit_in_node(tmp_path: Path) -> None:
    """Step 378: ``follow`` takes ``side`` ("left", "right", "sun"); ``problems`` says when the camera sees a craft's
    unlit side or the craft is in a world's shadow (demo (b) of Step 376 was a black ship on stars)."""
    got = _run_in_node(tmp_path, """
        const sideOf = (sun, side) => { const cam = C.spaceCamera({up: [0, 0, 1], sun, aspect: 16 / 9, bodies: [W]}), s = cam.follow(0.5, {subject: ship, view: "chase", around: W, drift: 0, side});
          const f = s.frame, rel = C.sub(s.from, ship.at(0.5)); return {right: C.dot(rel, C.cross(f.forward, f.up)), problems: cam.problems(0.5, s)}; };
        const toRight = (() => { const cam = C.spaceCamera({up: [0, 0, 1], sun: SUN, bodies: [W]}), s = cam.follow(0.5, {subject: ship, view: "chase", around: W, drift: 0}); return C.cross(s.frame.forward, s.frame.up); })();
        out.push({plain: sideOf([0, 0, 1], undefined).right, left: sideOf([0, 0, 1], "left").right, sunRight: sideOf(toRight, "sun").right, sunLeft: sideOf(C.scale(toRight, -1), "sun").right});
        // the ship at (7.2e6, ~0, 0): the sun along -x puts it in the world's shadow; the sun ahead of a chase camera hides its lit side
        const behind = C.spaceCamera({up: [0, 0, 1], sun: [-1, 0, 0], bodies: [W]}), sb = behind.follow(0.5, {subject: ship, view: "chase", around: W, drift: 0});
        const ahead = C.spaceCamera({up: [0, 0, 1], sun: C.scale(sb.forward, 1), bodies: [W]}), sa = ahead.follow(0.5, {subject: ship, view: "chase", around: W, drift: 0});
        const lit = C.spaceCamera({up: [0, 0, 1], sun: C.scale(sb.forward, -1), bodies: [W]}), sl = lit.follow(0.5, {subject: ship, view: "chase", around: W, drift: 0});
        out.push({shadow: behind.problems(0.5, sb), ahead: ahead.problems(0.5, sa), lit: lit.problems(0.5, sl), world: lit.problems(0.5, lit.arc(0, {subject: W, phase: "thin-crescent", distance: {radii: 4}})),
          bad: err(() => lit.follow(0.5, {subject: ship, view: "chase", around: W, side: "up"}))});
    """)
    sides, unlit = got
    assert sides["plain"] > 0 and sides["left"] < 0 and sides["sunRight"] > 0 and sides["sunLeft"] < 0
    assert sides["left"] == pytest.approx(-sides["plain"])
    assert any("in World's shadow" in p for p in unlit["shadow"]) and any("unlit side of Ship" in p and 'side: "sun"' in p for p in unlit["ahead"])
    assert not any("unlit" in p or "shadow" in p for p in unlit["lit"]) and not any("unlit" in p for p in unlit["world"])   # a world's crescent is meant
    assert 'follow side must be "left", "right" or "sun", got "up"' in unlit["bad"]


@pytest.mark.slow
@pytest.mark.render
def test_the_framings_draw_in_chromium(tmp_path: Path) -> None:
    """The five framings at 160x90 in one browser (a plain three.js scene through the rig): none black; the
    crescent is a dark frame with a brilliant sun, the arrival's lower half is the lit world under a dark sky."""
    tiles: list[np.ndarray] = []
    found = [p for p in P.read_parts() if p.file == "space-camera.js"]
    original = P.compose_sheet

    def keep(drawn, columns, title):
        tiles.extend(pixels for pixels, _ in drawn)
        return original(drawn, columns, title)

    P.compose_sheet = keep
    try:
        result = P.make_parts_sheet(found, tmp_path / "sheet.png", tile=(160, 90), columns=5)
    finally:
        P.compose_sheet = original
    by = {t.part.name: pixels.astype(float) for t, pixels in zip(result.tiles, tiles)}
    assert set(by) == CAMERA_PARTS and result.skipped == [] and all(t.max() > 60 for t in by.values())
    crescent, arrival, quarter = by["camera-crescent"], by["camera-arrival"], by["camera-three-quarter"]
    assert crescent.max() > 240 and np.median(crescent) < 30 and crescent[:, :80].mean() > crescent[:, 80:].mean()     # the sun on the left, the dark world on the right
    assert arrival[60:].mean() > 4 * arrival[:30].mean() and arrival[60:].mean() > 60                                 # the limb across the bottom
    assert quarter[:, 80:].mean() > 2 * quarter[:, :80].mean()                                                         # the world on the right third
