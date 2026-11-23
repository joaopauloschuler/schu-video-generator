"""Camera moves in the air and beside giant ships, ``vidgen/space-camera-air`` (Step 390, DESIGN.md
§123.12): the module is served by its import name and imports no three.js; its moves are registered
as parts; in Node (when it is installed): every move is a function of its time (the same time, the
same shot, in any order); bar-locked times; eased ends that start or end moving; the camera never
under its margin over a ground given as a function, with a note when it had to be lifted; "up" is
the local vertical far from the scene's anchor; no flip looking straight down; a pass along a hull
keeps its stand-off from every box of a stand-in hull and swings out round a tower; the bow enters
the frame at its time; a bay is entered through its mouth; the bank lights on its bar and the shake
is seeded and only on request; mistakes are named with a did-you-mean. In Chromium (``slow``): two
moves drawn at three times each in two orders give the same pictures, the camera over the water."""

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
MODULE = MODULES / "space-camera-air.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
AIR_PARTS = {"camera-skim", "camera-climb-through", "camera-chase", "camera-wing", "camera-fly-past", "camera-orbit-peak", "camera-rise",
             "camera-hull-pass", "camera-hull-reveal", "camera-into-bay", "camera-stern-burn", "camera-scale-zoom"}


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-camera-air"] == "space-camera-air.js"
    assert IMPORT_MAP["imports"]["vidgen/space-camera-air"] == "/__vidgen__/modules/space-camera-air.js"
    assert vidgen_file("modules/space-camera-air.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-camera-air.js"])["__vidgen__/modules/space-camera-air.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["vidgen/music-time", "vidgen/space-camera", "vidgen/space-scene"]      # no three.js: the mathematics runs anywhere
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-camera-air" not in engine_id()


def test_the_moves_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-camera-air.js"}
    assert set(found) == AIR_PARTS and all(p.kind == "camera" and p.module == "vidgen/space-camera-air" for p in found.values())
    assert "airCamera({camera, sky, ground, water})" in found["camera-skim"].use and "cam.hullPass(" in found["camera-hull-pass"].use
    assert "shot.throttle" in found["camera-stern-burn"].use and all(len(p.label) <= 108 for p in found.values())


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``A`` (and ``vidgen/space-camera`` as ``C``) and print ``out`` as JSON."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    names = ("music-time", "space-camera", "space-scene", "space-camera-air")
    ours = tmp_path / "node_modules" / "vidgen"
    ours.mkdir(parents=True)
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as A from 'vidgen/space-camera-air';\nimport * as C from 'vidgen/space-camera';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const R = 6.371e6, RAD = Math.PI / 180, deg = (a, b) => Math.atan2(C.len(C.cross(a, b)), C.dot(a, b)) / RAD;\n"
        "const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);\n"
        "const ortho = (s) => Math.max(Math.abs(C.dot(s.right, s.up)), Math.abs(C.dot(s.right, s.forward)), Math.abs(C.dot(s.up, s.forward)), Math.abs(C.len(s.right) - 1), Math.abs(C.len(s.up) - 1), Math.abs(C.len(s.forward) - 1),"
        " C.len(C.sub(C.cross(s.forward, s.up), s.right)));\n"
        # a ground with a broad hill and a ridge too narrow for the plan's samples, a flight on a circle
        "const ground = (x, z) => 300 * Math.exp(-((x - 3000) ** 2 + z * z) / 6e5) + (Math.abs(x - 316) < 6 ? 180 : 0);\n"
        "const circle = (v = 170, rate = 3, h = 2000) => { const w = rate * RAD, at = (t) => w * t; return {name: 'Plane', position: (t) => [(v / w) * (1 - Math.cos(at(t))), h, -(v / w) * Math.sin(at(t))],"
        " velocity: (t) => [v * Math.sin(at(t)), 0, -v * Math.cos(at(t))], quaternion: () => [0, 0, 0, 1], bank: () => 25}; };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_time_frames_and_envelopes_in_node(tmp_path: Path) -> None:
    eased, env, frame, look, bars, lag, pushed, names = _run_in_node(tmp_path, """
out.push({ends: [A.easedEnds(0), A.easedEnds(1), A.easedEnds(0.5)], steady: A.easedEnds(0.3, 0), rest: [A.easedRate(0, [1, 0]), A.easedRate(1, [1, 0]), A.easedRate(0, [0, 1]), A.easedRate(1, [0, 1])],
  rising: Array.from({length: 50}, (_, i) => A.easedEnds((i + 1) / 50, [1, 0.3]) - A.easedEnds(i / 50, [1, 0.3])).every((d) => d > 0),
  slope: [(A.easedEnds(1e-4, [1, 0]) - 0) / 1e-4, (1 - A.easedEnds(1 - 1e-4, [1, 0])) / 1e-4]});
const v = Array.from({length: 60}, (_, i) => (i === 30 ? 90 : 10 * Math.sin(i))), e = A.envelope(v, 4);
out.push({over: v.every((x, k) => e[k] >= x - 1e-9), early: e[27] > 40, far: e[10] < 12});
const L = A.localFrame({radius: R}), far = L.at(2.0e6, 0, 500);
out.push({up0: L.upAt([0, 0, 0]), tilt: deg(L.upAt(far), [0, 1, 0]), height: L.heightOf(far), north: C.dot(L.compass(far, 0), L.upAt(far)), east: L.compass([0, 0, 0], 90), edge: err(() => L.at(7e6, 0, 0))});
const down = A.lookFrame([0, 1, 0], [0, 0, -1], -90), near = A.lookFrame([0, 1, 0], [0, 0, -1], -89.999), upward = A.lookFrame([0, 1, 0], [0, 0, -1], 90), banked = A.lookFrame([0, 1, 0], [0, 0, -1], 0, 20);
out.push({down: down.forward, top: down.up, steady: deg(down.up, near.up) + deg(down.right, near.right), upTop: upward.up, ortho: Math.max(ortho(down), ortho(upward), ortho(banked)), bankRight: banked.right[1], bankTop: banked.up[0]});
const cam = A.airCamera({radius: R, music: {score: {bar: 2, beat: 0.5}, t0: 4}});
out.push({bar3: cam.seconds({bar: 3}), beat: cam.seconds({bar: 3, beat: 3}), plain: cam.seconds(1.5),
  start: cam.skim(0, {over: [{bar: 3}, {bar: 5}], speed: 100}).progress, end: cam.skim(4, {over: [{bar: 3}, {bar: 5}], speed: 100}).progress, mid: cam.skim(2, {over: [{bar: 3}, {bar: 5}], speed: 100}).travelled,
  none: err(() => A.airCamera({}).skim(0, {over: [{bar: 1}, {bar: 2}]}))});
out.push({now: A.lagged((t) => t, 5, 0), mean: A.lagged((t) => t, 5, 0.5), vec: A.lagged((t) => [t, 2 * t], 5, 0.5), flat: A.lagged(() => 7, 5, 2)});
out.push({before: A.pushBack(-1, 40), at: A.pushBack(0, 40), later: A.pushBack(5, 40), rises: A.pushBack(0.2, 40) < A.pushBack(0.4, 40) && A.pushBack(0.4, 40) < 40,
  shake: A.shake(1.234, {amount: 0.3, seed: 7}), again: same(A.shake(1.234, {amount: 0.3, seed: 7}), A.shake(1.234, {amount: 0.3, seed: 7})), other: !same(A.shake(1.234, {seed: 7}), A.shake(1.234, {seed: 8})),
  bank: [A.bankOf(100, 3), A.bankOf(100, -3, 0.5), A.bankOf(300, 20)], dip: A.horizonDip(R, 60000)});
out.push({air: A.AIR_MOVES, ship: A.SHIP_MOVES, all: [...A.AIR_MOVES, ...A.SHIP_MOVES].every((m) => typeof A.AirCamera.prototype[m] === "function"), old: typeof A.airCamera({}).flyBy === "function" && typeof A.airCamera({}).zoom === "function"});
""")
    assert eased["ends"][0] == 0 and eased["ends"][1] == 1 and eased["ends"][2] == pytest.approx(0.5) and eased["steady"] == pytest.approx(0.3) and eased["rising"]
    assert eased["rest"] == [0, 1, 1, 0]                                           # [1, 0]: from rest into motion; [0, 1]: from motion to rest
    assert eased["slope"][0] < 0.01 and eased["slope"][1] > 1.2                     # it ends faster than its mean speed, for a cut on motion
    assert env == {"over": True, "early": True, "far": True}
    assert frame["up0"] == [0, 1, 0] and frame["tilt"] == pytest.approx(18.3, abs=0.1) and frame["height"] == pytest.approx(500, abs=1e-6) and abs(frame["north"]) < 1e-12
    assert frame["east"] == pytest.approx([1, 0, 0], abs=1e-12) and "beyond the world's edge" in frame["edge"]
    assert look["down"] == pytest.approx([0, -1, 0], abs=1e-12) and look["top"] == pytest.approx([0, 0, -1], abs=1e-12)      # straight down: the frame's top is the heading
    assert look["steady"] < 0.01 and look["upTop"] == pytest.approx([0, 0, 1], abs=1e-12) and look["ortho"] < 1e-12
    assert look["bankRight"] < -0.3 and look["bankTop"] > 0.3                        # banked to the right: the right side goes down
    assert bars["bar3"] == 0 and bars["beat"] == 1 and bars["plain"] == 1.5 and bars["start"] == 0 and bars["end"] == 1 and bars["mid"] == pytest.approx(200)
    assert "no score" in bars["none"]
    assert lag["now"] == 5 and 4.3 < lag["mean"] < 4.7 and lag["vec"][1] == pytest.approx(2 * lag["vec"][0]) and lag["flat"] == pytest.approx(7)
    assert pushed["before"] == 0 and pushed["at"] == 0 and pushed["later"] == pytest.approx(40, abs=0.01) and pushed["rises"]
    assert pushed["again"] and pushed["other"] and all(abs(pushed["shake"][k]) <= 0.3 for k in ("yaw", "pitch", "roll"))
    assert pushed["bank"][0] == pytest.approx(28.1, abs=0.1) and pushed["bank"][1] == pytest.approx(-14.05, abs=0.1) and pushed["bank"][2] == 40 and pushed["dip"] == pytest.approx(7.82, abs=0.02)
    assert names["air"] == ["skim", "climbThrough", "descendThrough", "chase", "wing", "flyPast", "orbitPeak", "rise", "descend", "ascend"]
    assert names["ship"] == ["hullPass", "hullReveal", "intoBay", "sternBurn", "scaleZoom"] and names["all"] and names["old"]


def test_the_air_moves_in_node(tmp_path: Path) -> None:
    pure, skim, far, through, chase, wing, past, peak, rise = _run_in_node(tmp_path, """
const cam = A.airCamera({radius: R, ground, clouds: {decks: [{name: "stratus", base: 1500, top: 2300}], towers: [{x: 9000, z: -3000, radius: 1500, base: 800, top: 9000}]}, crafts: {}});
const F = circle(), O = {skim: {over: [0, 10], from: [0, 0], heading: 90, speed: 400, clearance: 40, turn: 12}, climbThrough: {over: [0, 10], adapt: 1},
  descendThrough: {over: [0, 10]}, chase: {flight: F}, wing: {flight: F}, flyPast: {flight: F, over: [0, 10]}, orbitPeak: {over: [0, 10], around: [3000, 0], radius: 3000}, rise: {over: [0, 10], at: [9000, 9000]},
  descend: {over: [0, 10], at: [9000, 9000]}, ascend: {over: [0, 10], at: [9000, 9000]}};
// the same time, the same shot, whatever was asked before
const order = [3, 1, 7, 1, 9, 3, 7], seen = {}; let stable = true, finite = true, square = 0;
for (const t of order) for (const m of A.AIR_MOVES) { const s = cam[m](t, O[m]), key = m + t, text = JSON.stringify(s); if (seen[key] !== undefined && seen[key] !== text) stable = false; seen[key] = text;
  finite = finite && [...s.from, ...s.forward, s.fov, s.focus].every(Number.isFinite); square = Math.max(square, ortho(s)); }
out.push({stable, finite, square, moves: A.AIR_MOVES.map((m) => cam[m](2, O[m]).move)});
// skim: over the hill and the narrow ridge, never under its margin
let least = Infinity, lifted = 0, notes = 0, top = 0, first = null;
for (let i = 0; i <= 600; i++) { const t = i / 60, s = cam.skim(t, O.skim); least = Math.min(least, cam.clearance(s.from, t)); lifted = Math.max(lifted, s.lifted); notes += s.notes.length; top = Math.max(top, s.height); if (s.notes.length && !first) first = s.notes[0]; }
const a = cam.skim(4.9, O.skim), b = cam.skim(5.1, O.skim), level = cam.skim(5, {...O.skim, horizon: "level"}), left = cam.skim(5, {...O.skim, turn: -12});
out.push({least, lifted, notes, first, top, before: cam.skim(5, O.skim).clearance, speed: C.len(C.sub(b.from, a.from)) / 0.2, bank: a.bank, rightDown: C.dot(a.right, [0, 1, 0]), level: Math.abs(C.dot(level.right, cam.local.upAt(level.from))), left: left.bank,
  rest: C.len(C.sub(cam.skim(0.05, {...O.skim, ease: [1, 0]}).from, cam.skim(0, {...O.skim, ease: [1, 0]}).from)) / 0.05, moving: C.len(C.sub(cam.skim(10, {...O.skim, ease: [1, 0]}).from, cam.skim(9.95, {...O.skim, ease: [1, 0]}).from)) / 0.05,
  problems: cam.problems(3, cam.skim(3, O.skim)).length, under: cam.problems(0, {from: [0, 1, 0], right: [1, 0, 0], up: [0, 1, 0], forward: [0, 0, -1], fov: 30, aspect: 1.78})});
// far from the anchor: up is the local vertical, not +y
const flat = A.airCamera({radius: R}), s2 = flat.skim(1, {over: [0, 4], from: [2.0e6, 0], heading: 0, speed: 100, clearance: 30, pitch: 0, horizon: "level"}), U = flat.local.upAt(s2.from);
out.push({up: deg(s2.up, U), y: deg(s2.up, [0, 1, 0]), right: Math.abs(C.dot(s2.right, U)), clearance: s2.clearance, height: s2.height});
// through a deck
const hs = Array.from({length: 11}, (_, i) => cam.climbThrough(i, O.climbThrough)), ds = Array.from({length: 11}, (_, i) => cam.descendThrough(i, O.descendThrough));
out.push({heights: hs.map((s) => Math.round(s.height)), rising: hs.every((s, i) => i === 0 || s.height > hs[i - 1].height), inside: hs.map((s) => s.inside), ev: hs.map((s) => s.ev), fog: Math.max(...hs.map((s) => s.fog)),
  down: ds.map((s) => Math.round(s.height)), pitch: [hs[0].forward[1] > 0.1, hs[10].forward[1] < 0], named: cam.climbThrough(5, {over: [0, 10], deck: "stratus"}).height, own: cam.climbThrough(0, {over: [0, 10], deck: {base: 100, top: 200}, below: 50}).height,
  climb: hs[5].climb});
// a chase
const c0 = cam.chase(6, {flight: F, lag: 0}), c1 = cam.chase(6, {flight: F}), cs = Array.from({length: 40}, (_, i) => cam.chase(i / 4, {flight: F}));
const low = A.airCamera({radius: R, ground: () => 1990}).chase(6, {flight: F, height: -30});
out.push({behind: deg(C.sub(F.position(6), c0.from), F.velocity(6)), wide: deg(c1.lagged, F.velocity(6)), distance: c0.distance, inFrame: cs.every((s) => C.screenOf(s, s.subject.at).inFrame), y: C.screenOf(c1, c1.subject.at).y,
  bank: c1.bank, rolled: C.dot(c1.right, [0, 1, 0]) < -0.1, lifted: low.notes.length, over: A.airCamera({radius: R, ground: () => 1990}).clearance(low.from), push: cam.chase(10, {flight: F, over: [0, 10], distance: [80, 30], lag: 0}).distance});
// locked to the plane: any attitude
const tumble = {position: () => [0, 5000, 0], velocity: () => [0, -200, 0], quaternion: (t) => { const h = t / 2; return [Math.sin(h) * 0.6, Math.sin(h) * 0.8, 0, Math.cos(h)]; }};
let worst = 0; for (let i = 0; i < 80; i++) for (const view of Object.keys(A.WING_VIEWS)) worst = Math.max(worst, ortho(cam.wing(i / 8, {flight: tumble, view})));
const w = cam.wing(0, {flight: F, view: "wingtip", side: "right", length: 30, span: 18}), wl = cam.wing(0, {flight: F, view: "wingtip", side: "left", length: 30, span: 18});
out.push({worst, views: Object.keys(A.WING_VIEWS), right: w.forward[0], left: wl.forward[0], rides: C.len(C.sub(w.from, F.position(0))) < 8, own: cam.wing(0, {flight: F, view: {at: [0, 2, 0], toward: [0, 0, 1]}}).forward,
  tip: cam.wing(0, {flight: F, craft: {size: {length: 30, width: 18}, anchors: {wingTips: [{p: [9, 0, -11]}, {p: [-9, 0, -11]}]}}}).forward[2] < -0.5});
// a fly-past: the camera stands still, the turn is fastest at the pass
const ps = Array.from({length: 101}, (_, i) => cam.flyPast(i / 10, {flight: F, at: 5, closest: 100}));
const fastest = ps.reduce((b, s, i) => (s.pan > ps[b].pan ? i : b), 0), stand = cam.flyPast(3, {flight: F, at: 5, stand: "ground", eye: 2});
out.push({still: ps.every((s) => same(s.from, ps[0].from)), fastest: fastest / 10, pan: ps[fastest].pan, closest: ps[50].distance, inFrame: ps.every((s) => C.screenOf(s, s.subject.at).inFrame), eye: cam.clearance(stand.from) + stand.notes.length, said: cam.problems(3, stand),
  middle: cam.flyPast(1, {flight: F, over: [0, 8]}).pass, need: err(() => cam.flyPast(1, {flight: F}))});
// round a peak, a tower
const os = Array.from({length: 21}, (_, i) => cam.orbitPeak(i / 2, O.orbitPeak)), tw = cam.orbitPeak(5, {over: [0, 10], around: {tower: 0}}), pk = cam.peakNear([2200, 500], 4000);
out.push({radius: os.map((s) => Math.hypot(s.from[0] - 3000, s.from[2])), inFrame: os.every((s) => C.screenOf(s, s.target).inFrame), bearing: [os[0].bearing, os[20].bearing], top: os[0].top, clear: Math.min(...os.map((s, i) => cam.clearance(s.from, i / 2))),
  tower: [tw.radius, tw.top], peak: [Math.round(pk.x), Math.round(pk.z), Math.round(pk.height)], near: cam.orbitPeak(0, {over: [0, 10], around: {near: [2200, 500], reach: 4000}}).top,
  low: A.airCamera({radius: R, ground: (x, z) => (x > 5000 ? 2000 : 0)}).orbitPeak(0, {progress: 0, around: [4000, 0], top: 300, radius: 3000, start: 90}).height});
// a crane up
const rs = Array.from({length: 11}, (_, i) => cam.rise(i, {over: [0, 10], at: [9000, 9000], from: 20, to: 60000, lens: ["normal", "ultra-wide"]})), back = cam.rise(3, {over: [0, 10], at: [9000, 9000], from: 20, to: 60000, down: true});
out.push({above: [rs[0].aboveGround, rs[10].aboveGround], rising: rs.every((s, i) => i === 0 || s.height > rs[i - 1].height), fov: [rs[0].fov, rs[10].fov], dip: rs[10].dip, pitch: rs[10].pitch,
  horizon: C.screenOf(rs[10], C.add(rs[10].from, A.lookFrame(flat.local.upAt(rs[10].from), [0, 0, -1], -rs[10].dip).forward)).y, same: Math.abs(back.height - rs[7].height), order: err(() => cam.rise(0, {progress: 0, from: 50, to: 10}))});
""")
    assert pure == {"stable": True, "finite": True, "square": pytest.approx(0, abs=1e-9), "moves": ["skim", "climbThrough", "descendThrough", "chase", "wing", "flyPast", "orbitPeak", "rise", "descend", "ascend"]}
    # the ridge is narrower than the plan's samples: the camera is lifted there, and says so; it is never under 0.4 x its clearance
    assert skim["least"] >= 16 - 1e-4 and skim["lifted"] > 50 and skim["notes"] >= 1 and "the camera was lifted" in skim["first"] and "to stay 16 m over the ground" in skim["first"]
    assert skim["top"] > 300 and skim["before"] > 60                                # over the hill; rising before it and settling after it (the look-ahead)
    assert skim["speed"] == pytest.approx(400, rel=0.02) and 0 < skim["bank"] <= 20 and skim["rightDown"] < -0.01 and skim["level"] < 1e-9 and skim["left"] < 0
    assert skim["rest"] < 5 and skim["moving"] > 300 and skim["problems"] == 0 and "only 1.0 m over the ground" in skim["under"][0]
    assert far["up"] < 1e-6 and far["y"] == pytest.approx(18.3, abs=0.1) and far["right"] < 1e-12 and far["clearance"] == pytest.approx(30, abs=1e-6) and far["height"] == pytest.approx(30, abs=1e-6)
    assert through["heights"][0] == 1000 and through["heights"][-1] == 2900 and through["rising"] and through["inside"][0] is False and through["inside"][5] is True and through["inside"][-1] is False
    assert through["ev"][0] == 0 and through["ev"][-1] == 0 and min(through["ev"]) < -0.5 and min(through["ev"]) >= -1 and through["fog"] > 0.9
    assert through["down"] == through["heights"][::-1] and through["pitch"] == [True, True] and through["named"] == through["heights"][5] and through["own"] == 50 and through["climb"] > 190
    assert chase["behind"] < 15 and 0.3 < chase["wide"] < 5 and chase["distance"] == pytest.approx(62.1, abs=0.2) and chase["inFrame"] and -0.3 < chase["y"] < -0.1
    assert chase["bank"] == pytest.approx(12.5) and chase["rolled"] and chase["lifted"] == 1 and chase["over"] == pytest.approx(3, abs=1e-6) and chase["push"] == pytest.approx(34, abs=0.5)
    assert wing["worst"] < 1e-9 and wing["views"] == ["wingtip", "tail", "belly", "nose"] and wing["right"] < -0.5 and wing["left"] > 0.5 and wing["rides"]
    assert wing["own"] == pytest.approx([0, 0, 1]) and wing["tip"]
    assert past["still"] and abs(past["fastest"] - 5) <= 0.1 and past["pan"] == pytest.approx(170 / 100 * 180 / 3.14159, rel=0.1) and past["closest"] == pytest.approx(100.7, abs=0.5)
    assert past["inFrame"] and past["eye"] == pytest.approx(2, abs=1e-6) and past["said"] == [] and past["middle"] == 4 and "flyPast needs at" in past["need"]      # the ground stand: its own eye height, under the rig's margin, without a note
    assert all(r == pytest.approx(3000, abs=1e-6) for r in peak["radius"]) and peak["inFrame"] and peak["bearing"] == [180, 270] and peak["top"] == pytest.approx(300, abs=1)
    assert peak["clear"] > 150 and peak["tower"] == [4500, 9000] and peak["peak"] == [3000, 0, 300] and peak["near"] == pytest.approx(300, abs=0.5) and peak["low"] > 2100
    assert rise["above"] == pytest.approx([20, 60000]) and rise["rising"] and rise["fov"][0] == pytest.approx(27, abs=0.1) and rise["fov"][1] == pytest.approx(73.7, abs=0.1)
    assert rise["dip"] == pytest.approx(7.8, abs=0.1) and rise["pitch"] < -rise["dip"] and rise["horizon"] == pytest.approx(0.3, abs=1e-6) and rise["same"] < 1e-6 and "must be above" in rise["order"]


def test_the_ship_moves_in_node(tmp_path: Path) -> None:
    plan, passed, turned, reveal, bay, burn, zoom = _run_in_node(tmp_path, """
// a stand-in hull: a slab, a tower on its deck, a block on its port side, a hangar in the port wall, four bells
const box = (name, min, max) => ({name, box: {min, max}, centre: min.map((v, i) => 0.5 * (v + max[i])), normal: [1, 0, 0]});
const hull = {regions: [box("midship", [-200, -100, -1000], [200, 100, 1000]), box("tower-1", [-60, 100, 200], [60, 300, 400]), box("block", [200, -50, -600], [320, 50, -400])],
  anchors: {hangars: [{name: "hangar-1", p: [200, 0, 300], n: [1, 0, 0], width: 200, height: 80, depth: 120}], bells: [[-80, -40], [80, -40], [-80, 40], [80, 40]].map(([x, y], i) => ({name: `bell-${i + 1}`, p: [x, y, -1000], n: [0, 0, -1], radius: 30})),
    points: {port: {p: [200, 0, 0], n: [1, 0, 0]}, "hangar-1": {p: [200, 0, 300], n: [1, 0, 0]}}}, size: {length: 2000, width: 520, height: 400, radius: 1100}, object: null};
const cam = A.airCamera({ships: {Ship: hull}, music: {score: {bar: 2, beat: 0.5}, t0: 0}});
const dorsal = A.passPlan(hull, {side: "dorsal", standoff: 50}), port = A.passPlan(hull, {side: "port", standoff: 50}), beside = A.passPlan(hull, {side: "dorsal", lane: 150, standoff: 50});
out.push({most: [dorsal.most, port.most, beside.most], ends: [dorsal.zMin, dorsal.zMax], atTower: dorsal.reachAt(300)[0], away: dorsal.reachAt(-700)[0], sides: [A.sideAxes("port").out, A.sideAxes("ventral").out, A.sideAxes(45).out],
  miss: err(() => A.passPlan(hull, {side: "dorsal", lane: 900})), bad: err(() => A.sideAxes("prt")), distance: [A.boxDistance([0, 0, 0], hull.regions[0].box), A.boxDistance([203, 104, 0], hull.regions[0].box)],
  nearest: A.hullClearance(hull.regions, [0, 320, 300])});
// a pass over the deck: never nearer than its stand-off, out round the tower before it
let least = Infinity, notes = 0, high = 0, stable = true, early = 0;
const O = {ship: "Ship", over: [0, 40], side: "dorsal", standoff: 50, from: 0.05, to: 0.95};
for (let i = 0; i <= 800; i++) { const t = i / 20, s = cam.hullPass(t, O); least = Math.min(least, A.hullClearance(hull.regions, s.own.from).distance); notes += s.notes.length; high = Math.max(high, s.own.from[1]); if (s.own.from[2] < 100 && s.own.from[1] > 160) early++;
  if (i % 97 === 0) stable = stable && same(s, cam.hullPass(t, O)); }
const p0 = cam.hullPass(0, O), p1 = cam.hullPass(40, O), side = cam.hullPass(20, {ship: "Ship", over: [0, 40], side: "port", standoff: 50, speed: 30}), under = cam.hullPass(20, {ship: "Ship", over: [0, 40], side: "ventral"});
out.push({least, notes, high, early, stable, from: p0.station, to: p1.station, speed: cam.hullPass(20, O).speed, fov: p0.fov, x: side.own.from[0], aft: cam.hullPass(20, {ship: "Ship", over: [0, 40], toward: "stern", from: 0.9}).own.from[2] < 800,
  ahead: side.own.target[2] > side.own.from[2] + 300, wall: side.own.target[0] < side.own.from[0], up: side.up, below: under.own.from[1], toy: cam.hullPass(1, {ship: "Ship", over: [0, 4], from: 0, to: 1}).notes, lone: A.airCamera({ships: {A: hull}}).hullPass(0, {progress: 0}).move});
// a hull turned and moved in a plain scene: the shot is in the scene's frame
const q = [0, Math.sin(Math.PI / 4), 0, Math.cos(Math.PI / 4)], placed = {...hull, object: {isObject3D: true, position: {x: 10, y: 20, z: 30}, quaternion: {x: q[0], y: q[1], z: q[2], w: q[3]}, scale: {x: 0.01}}};
const t0 = A.airCamera({}).hullPass(20, {...O, ship: placed});
out.push({from: t0.from, own: t0.own.from, forward: t0.forward});
// the bow enters at its time and the hull keeps coming
const RV = {ship: "Ship", at: {bar: 3}, speed: 100}, bow = [0, -100, 1000], seen = (t) => C.screenOf(cam.hullReveal(t, RV), bow), r0 = cam.hullReveal(0, RV), r1 = cam.hullReveal(30, RV);
out.push({first: r0.first, before: seen(3.8).y, after: seen(4.3).y, behind: seen(0).depth, clear: Math.min(r0.clearance.distance, r1.clearance.distance), covered: [r0.covered, cam.hullReveal(14, RV).covered, cam.hullReveal(40, RV).covered], stern: r0.stern,
  escort: [C.dot(C.sub(cam.hullReveal(r0.escortEnters - 1, RV).escort, cam.hullReveal(r0.escortEnters - 1, RV).own.from), [0, 0, 1]), C.dot(C.sub(cam.hullReveal(r0.escortEnters + 2, RV).escort, cam.hullReveal(r0.escortEnters + 2, RV).own.from), [0, 0, 1])],
  fixed: same(cam.hullReveal(7, RV).forward, cam.hullReveal(9, RV).forward), top: cam.hullReveal(7, RV).up[1] > 0, over: cam.hullReveal(7, {...RV, side: "over"}).own.from[1], lane: cam.hullReveal(7, {...RV, lane: 100}).own.from[0],
  limb: err(() => cam.hullReveal(0, {ship: "Ship", mode: "limb"})), mode: err(() => cam.hullReveal(0, {ship: "Ship", mode: "slide"}))});
// into the bay, and out of it
const B = {ship: "Ship", over: [0, 10]}, b0 = cam.intoBay(0, B), b1 = cam.intoBay(10, B), inside = (p) => p[0] < 200 && p[0] > 80 && Math.abs(p[1]) < 40 && Math.abs(p[2] - 300) < 100;
let entered = true; for (let i = 0; i <= 100; i++) { const s = cam.intoBay(i / 10, B); if (s.own.from[0] < 200 && !inside(s.own.from)) entered = false; }
out.push({start: b0.distance, end: b1.distance, outside: !b0.inside && b0.own.from[0] > 900, inside: b1.inside && inside(b1.own.from), entered, looksIn: b1.own.target[0] < b1.own.from[0], out: C.len(C.sub(cam.intoBay(3, {...B, out: true}).own.from, cam.intoBay(7, B).own.from)) < 1e-6,
  hangar: b0.hangar, blocked: [cam.intoBay(2, B).notes.length, cam.intoBay(2, {...B, clear: 5000}).notes.length], none: err(() => cam.intoBay(0, {...B, hangar: "hanger-1"}))});
// behind the bank as it lights
const S = {ship: "Ship", over: [0, 8], light: {bar: 3}}, sb = (t, o = {}) => cam.sternBurn(t, {...S, ...o});
const shaken = sb(4.2, {shake: {amount: 0.3, seed: 5}});
out.push({light: sb(0).light, throttle: [sb(3.9).throttle, sb(4.1).throttle > 0 && sb(4.1).throttle < 1, sb(4.5).throttle], pushed: [sb(3.9).pushed, sb(12).pushed], back: C.len(C.sub(sb(12).own.from, sb(4).own.from)), bank: sb(0).bank,
  astern: sb(0).own.from[2] < -1000, off: sb(0).own.from[0] !== 0, noShake: same(sb(4.2).forward, sb(4.2, {shake: false}).forward), tremble: deg(shaken.forward, sb(4.2).forward), again: same(shaken, sb(4.2, {shake: {amount: 0.3, seed: 5}})),
  seed: !same(shaken.forward, sb(4.2, {shake: {amount: 0.3, seed: 6}}).forward), early: same(sb(3.5, {shake: true}).forward, sb(3.5).forward), ortho: ortho(shaken), creep: C.len(C.sub(sb(0).own.from, sb(4).own.from)) > 1});
// powers of ten off the hull
const Z = {ship: "Ship", window: "hangar-1", close: 60, over: [0, 8], world: {at: [0, -7.2e6, 0], radius: 6.371e6, name: "World"}};
out.push({close: cam.scaleZoom(0, Z).distance, whole: cam.scaleZoom(0, {...Z, world: null, over: [0, 4]}).plan.distances[1], far: cam.scaleZoom(8, Z).distance, away: cam.scaleZoom(0, Z).from[0] > 200, grows: cam.scaleZoom(2, Z).distance > cam.scaleZoom(1, Z).distance,
  move: cam.scaleZoom(1, Z).move, bad: err(() => cam.scaleZoom(0, {...Z, window: "hangar-9"})), ship: err(() => cam.hullPass(0, {ship: "Shipp", progress: 0})), option: err(() => cam.hullPass(0, {ship: "Ship", progress: 0, standof: 3}))});
""")
    assert plan["most"][0] == pytest.approx(300, abs=1) and plan["most"][1] == pytest.approx(320, abs=1) and plan["most"][2] == pytest.approx(100, abs=1) and plan["ends"] == [-1000, 1000]
    assert plan["atTower"] == pytest.approx(300, abs=1) and plan["away"] == pytest.approx(100, abs=1) and plan["sides"][0] == [1, 0, 0] and plan["sides"][1] == pytest.approx([0, -1, 0]) and plan["sides"][2][0] == pytest.approx(0.7071, abs=1e-4)
    assert "misses the hull" in plan["miss"] and 'did you mean "port"' in plan["bad"] and plan["distance"] == [0, 5] and plan["nearest"] == {"distance": 20, "region": "tower-1"}
    assert passed["least"] >= 50 - 1e-6 and passed["notes"] == 0 and passed["high"] == pytest.approx(350, abs=1) and passed["early"] > 0 and passed["stable"]
    assert passed["from"] == pytest.approx(0.05) and passed["to"] == pytest.approx(0.95) and passed["speed"] == pytest.approx(45) and passed["fov"] == pytest.approx(73.7, abs=0.1)
    assert passed["x"] > 250 and passed["aft"] and passed["ahead"] and passed["wall"] and passed["up"][1] > 0.9 and passed["below"] < -150
    assert len(passed["toy"]) == 1 and "it will read as a model" in passed["toy"][0] and passed["lone"] == "hullPass"
    own = turned["own"]                                                                # a quarter turn about +y takes the hull's z to the scene's x; its metres are 0.01 scene units
    assert turned["from"] == pytest.approx([10 + 0.01 * own[2], 20 + 0.01 * own[1], 30 - 0.01 * own[0]], abs=1e-9) and turned["forward"][0] > 0.9
    assert reveal["first"] == 4 and reveal["before"] > 1 and reveal["after"] < 1 and reveal["behind"] < 0 and reveal["clear"] >= 60 - 1e-6        # the bow comes in over the top edge at bar 3
    assert reveal["covered"][0] == 0 and 0.4 < reveal["covered"][1] < 0.6 and reveal["covered"][2] == 1 and reveal["stern"] == pytest.approx(24)
    assert reveal["escort"][0] < 0 < reveal["escort"][1] and reveal["fixed"] and reveal["top"] and reveal["over"] > 300 and reveal["lane"] == 100
    assert "needs behind: the world" in reveal["limb"] and 'must be one of traverse, limb' in reveal["mode"]
    assert bay["start"] == pytest.approx(800) and bay["end"] == pytest.approx(-42) and bay["outside"] and bay["inside"] and bay["entered"] and bay["looksIn"] and bay["out"] and bay["hangar"] == "hangar-1"
    assert bay["blocked"] == [0, 1] and 'did you mean "hangar-1"' in bay["none"]
    assert burn["light"] == 4 and burn["throttle"] == [0, True, 1] and burn["pushed"][0] == 0 and burn["pushed"][1] == pytest.approx(0.5 * burn["bank"]["radius"], rel=1e-3) and burn["back"] > 40
    assert burn["bank"]["radius"] == pytest.approx(119.4, abs=0.1) and burn["astern"] and burn["off"] and burn["noShake"] and 0 < burn["tremble"] < 0.45 and burn["again"] and burn["seed"] and burn["early"]
    assert burn["ortho"] < 1e-9 and burn["creep"]
    assert zoom["close"] == pytest.approx(60) and zoom["whole"] > 2000 and zoom["far"] == pytest.approx(4 * 6.371e6) and zoom["away"] and zoom["grows"] and zoom["move"] == "scaleZoom"
    assert 'did you mean "hangar-1"' in zoom["bad"] and 'did you mean "Ship"' in zoom["ship"] and 'did you mean "standoff"' in zoom["option"]


def test_mistakes_are_named_in_node(tmp_path: Path) -> None:
    said = _run_in_node(tmp_path, """
const cam = A.airCamera({radius: R, flight: {names: ["Plane", "Tanker"], position: () => [0, 1000, 0], velocity: () => [100, 0, 0], quaternion: () => [0, 0, 0, 1], bank: () => 0.2}});
out.push(err(() => cam.skim(0, {over: [0, 1], clearence: 3})), err(() => cam.wing(0, {flight: "Plane", view: "wingtp"})), err(() => cam.chase(0, {flight: "Plan"})), err(() => cam.chase(0, {})),
  err(() => cam.skim(0, {})), err(() => cam.climbThrough(0, {progress: 0})), err(() => cam.skim(0, {progress: 0, horizon: "banked"})), err(() => cam.orbitPeak(0, {progress: 0, around: {tower: 2}})),
  err(() => A.airCamera({sky: {options: {unit: 1000}}})), err(() => A.airCamera({camra: 1})), err(() => cam.hullPass(0, {progress: 0})), cam.chase(0, {flight: "Plane"}).bank, err(() => cam.flyPast(0, {flight: "Plane", at: 1, side: "up"})));
""")
    assert 'unknown option "clearence" (did you mean "clearance"?)' in said[0] and 'no view "wingtp" (did you mean "wingtip"?)' in said[1] and 'no flight "Plan" (did you mean "Plane"?)' in said[2]
    assert "flights: Plane, Tanker" in said[3] and "skim needs progress (0..1) or over" in said[4] and "needs deck: {base, top}" in said[5] and 'did you mean "bank"' in said[6]
    assert "no tower 2" in said[7] and "`unit` must be 1" in said[8] and 'unknown option "camra" (did you mean "camera"?)' in said[9] and "needs ship: a hull" in said[10]
    assert said[11] == pytest.approx(0.5 * 0.2 * 180 / 3.141592653589793) and 'flyPast side must be one of left, right, got "up"' in said[12]      # ctx.flight's bank is in radians


def test_the_operators_curves_in_node(tmp_path: Path) -> None:
    """Step 399's pure functions: endless noise, a second-order follower settled at `since`, a handheld error that
    holds the frame on average and grows on the screen with a longer lens, a mount that only vibrates, a horizon
    held then levelled with a small overshoot, reframes that return, the meter's view of the scene."""
    noise, follow, hand, level, meter = _run_in_node(tmp_path, """
const xs = Array.from({length: 4000}, (_, i) => i * 0.137), rms = (a) => Math.sqrt(a.reduce((s, x) => s + x * x, 0) / a.length);
out.push({rms: rms(xs.map((x) => A.smoothNoise(x, 3))), most: Math.max(...xs.map((x) => Math.abs(A.smoothNoise(x, 3)))), mean: xs.reduce((s, x) => s + A.smoothNoise(x, 3), 0) / xs.length,
  same: A.smoothNoise(12.34, 5) === A.smoothNoise(12.34, 5), other: A.smoothNoise(12.34, 5) !== A.smoothNoise(12.34, 6), knot: A.smoothNoise(7, 2)});
const ts = Array.from({length: 1200}, (_, i) => i / 100), step = (x) => (x >= 1 ? 1 : 0);
const under = ts.map((t) => A.stepResponse(t, 0.5, 0.5)), critical = ts.map((t) => A.stepResponse(t, 0.5, 1));
const follower = ts.map((t) => A.responded(step, t, {delay: 0.2, rate: 0.5, damping: 0.5, n: 48}));
out.push({over: Math.max(...under), critical: Math.max(...critical), end: under[1199], before: A.stepResponse(-1, 0.5, 0.5), lateAt: follower[115], mid: follower[300], top: Math.max(...follower), settled: follower[1199],
  since: A.responded(step, 5, {rate: 0.5, damping: 0.5, since: 5}), flat: A.responded(() => 3, 4, {rate: 1})});
const seconds = Array.from({length: 3600}, (_, i) => i / 30), yaw = (mm) => rms(seconds.map((t) => A.handheld(t, {mm}).yaw));
const fovOf = (mm) => 2 * Math.atan(12 / mm) / RAD, h = seconds.map((t) => A.handheld(t, {mm: 50})), m = seconds.map((t) => A.mounted(t));
out.push({wide: yaw(16), normal: yaw(50), long: yaw(300), screenWide: yaw(16) / fovOf(16), screenLong: yaw(300) / fovOf(300), mean: h.reduce((s, x) => s + x.yaw, 0) / h.length,
  roll: rms(h.map((x) => x.roll)), mounted: rms(m.map((x) => x.yaw)), mountedLong: A.mounted(3.3, {mm: 300}).yaw === A.mounted(3.3).yaw,
  again: JSON.stringify(A.handheld(7.77, {seed: 4})) === JSON.stringify(A.handheld(7.77, {seed: 4})), seeded: A.handheld(7.77, {seed: 4}).yaw !== A.handheld(7.77, {seed: 5}).yaw,
  none: A.handheld(3, {amount: 0}).yaw, reframes: seconds.filter((t) => Math.abs(A.reframeAt(t).yaw) > 0.3).length, back: Math.max(...[60, 90, 120].map((t) => Math.abs(A.reframeAt(t, {reframe: 1e9}).yaw)))});
out.push({start: A.horizonRoll(0), held: A.horizonRoll(2.4), level: A.horizonRoll(8), over: Math.max(...ts.map((t) => -Math.sign(A.horizonRoll(0)) * A.horizonRoll(t))),
  sides: [1, 2, 3, 4, 5, 6].map((s) => Math.sign(A.horizonRoll(0, {seed: s}))), three: A.horizonRoll(0, {degrees: 3})});
const shot = (pitch, fov = 50, forward = null) => ({forward: forward ?? [0, Math.sin(pitch * RAD), -Math.cos(pitch * RAD)], fov, aspect: 16 / 9});
const sun = [0, Math.sin(20 * RAD), -Math.cos(20 * RAD)], deck = {base: 1000, top: 2000, cover: 1, density: 0.008};
const at = (height, s = shot(0), o = {}) => A.meterStops(s, {up: [0, 1, 0], height, sun, water: true, decks: [deck], ...o});
out.push({under: at(500), base: at(1100), deep: at(1500), nearTop: at(1950), over: at(2600), clear: at(500, shot(0), {decks: []}),
  sunIn: at(3000, shot(20)), sunOut: at(3000, shot(20, 50, [0, Math.sin(20 * RAD), Math.cos(20 * RAD)])), down: at(3000, shot(-60)), high: at(40000, shot(10), {decks: []}), low: at(100, shot(10), {decks: []})});
""")
    assert 0.2 < noise["rms"] < 0.4 and noise["most"] <= 1 and abs(noise["mean"]) < 0.03 and noise["same"] and noise["other"] and noise["knot"] == 0
    assert follow["over"] == pytest.approx(1 + 2.718281828 ** (-0.5 * 3.14159265 / 0.75 ** 0.5), abs=1e-3) and follow["critical"] <= 1 and follow["end"] == pytest.approx(1, abs=1e-3)
    assert follow["before"] == 0 and follow["lateAt"] < 0.05 and 0.3 < follow["mid"] < 1.1 and 1.08 < follow["top"] < 1.25 and follow["settled"] == pytest.approx(1, abs=0.01)
    assert follow["since"] == 1 and follow["flat"] == pytest.approx(3)                     # settled at `since`: nothing earlier is read
    assert 0.1 < hand["normal"] < 0.4 and hand["wide"] > hand["normal"] > hand["long"]     # a long lens is held steadier ...
    assert hand["screenLong"] > 3 * hand["screenWide"]                                      # ... but shakes more on the screen
    assert abs(hand["mean"]) < 0.08 and hand["roll"] < hand["normal"] and 0.01 < hand["mounted"] < 0.1 and hand["mountedLong"]
    assert hand["again"] and hand["seeded"] and hand["none"] == 0 and hand["reframes"] > 30 and hand["back"] < 0.05
    assert abs(level["start"]) == pytest.approx(1) and level["held"] == level["start"] and abs(level["level"]) < 0.01
    assert 0.03 < level["over"] < 0.2 and set(level["sides"]) == {-1, 1} and abs(level["three"]) == pytest.approx(3)
    assert meter["base"] < meter["deep"] < meter["nearTop"] < meter["over"] and meter["deep"] < meter["under"] - 1 and meter["under"] < meter["clear"]      # fog darkens with the deck above
    assert meter["sunIn"] > meter["sunOut"] and meter["down"] > meter["sunOut"] and meter["high"] < meter["low"]      # sunlit tops below are bright


def test_the_operator_frames_a_view_in_node(tmp_path: Path) -> None:
    """`operate` / `cam.operator`: off returns the view itself; a function of t alone (any order, the same shot);
    the frame stays square and is turned by the hand and the horizon; the horizon restarts at every cut; the
    exposure is settled at the start and at every cut, answers a jump in brightness late, overshoots with `hunt` and
    not without, never past `most`, adds to the move's own `ev` (a deck's `adapt`); mistakes named."""
    pure, cuts, exposure, said = _run_in_node(tmp_path, """
const cam = A.airCamera({radius: R, sun: [0, Math.sin(15 * RAD), -Math.cos(15 * RAD)], water: {heightAt: () => 0, list: {waves: []}},
  clouds: {decks: [{name: "stratus", base: 1500, top: 2300, cover: 1, density: 0.008}]}});
const climb = (t) => cam.climbThrough(t, {over: [0, 14], heading: 0, adapt: 1, lens: "wide"}), op = {hand: "handheld", exposure: true, horizon: true};
const seen = cam.operator(climb, op), order = [9, 2, 11, 2, 9, 5], text = {};
let stable = true, square = 0, turned = 0;
for (const t of order) { const s = seen(t), k = JSON.stringify(s); if (text[t] !== undefined && text[t] !== k) stable = false; text[t] = k; square = Math.max(square, ortho(s)); turned = Math.max(turned, deg(s.forward, climb(t).forward)); }
out.push({off: A.operate(climb, {}) === climb && cam.operator(climb, {hand: false, exposure: 0}) === climb, stable, square, turned, keeps: seen(3).from.join() === climb(3).from.join() && seen(3).fov === climb(3).fov,
  adds: seen(9).ev - seen(9).operator.ev - climb(9).ev, mounted: Math.abs(cam.operator(climb, {hand: "mounted"})(4).operator.yaw) < 0.3});
// a cut at 5 s: a new horizon error (its own side), the exposure settled there
const cutSeen = A.operate((t) => climb(t), {horizon: true, cuts: [5]}), first = cutSeen(0.5).operator.horizon, second = cutSeen(5.5).operator.horizon, late = cutSeen(4.9).operator.horizon;
const metered = cam.operator(climb, {exposure: true, cuts: [9.5]});
out.push({first, late, second, atCut: metered(9.5).operator.ev, after: metered(12).operator.ev, start: seen(0).operator.ev, seeded: A.operate(climb, {horizon: true, seed: 7})(0).operator.horizon});
// brightness that jumps up by 3 stops at 2 s: late, overshooting, limited
const jump = (x) => (x >= 2 ? 3 : 0), ts = Array.from({length: 1000}, (_, i) => i / 100), curve = (o) => ts.map((t) => A.autoExposure(t, jump, o, 0));
const hunting = curve({hunt: 1, most: 8}), calm = curve({hunt: 0, most: 8}), limited = curve({most: 1});
out.push({before: hunting[150], lateAt: hunting[215], end: hunting[999], low: Math.min(...hunting), calmLow: Math.min(...calm), calmEnd: calm[999], limited: Math.min(...limited)});
out.push([err(() => A.operate(climb, {hnd: "handheld"})), err(() => A.operate(climb, {hand: "handhled"})), err(() => A.operate(climb, {hand: {style: "mounted", drift: 1}})),
  err(() => A.operate(climb, {exposure: true})), err(() => A.operate(climb, {exposure: {hunts: 1}})), err(() => A.operate(climb, {horizon: {degrees: 40}})), err(() => A.operate(climb, {hand: {reframe: 1}}))]);
""")
    assert pure["off"] and pure["stable"] and pure["square"] < 1e-9 and 0.05 < pure["turned"] < 3 and pure["keeps"] and pure["adds"] == pytest.approx(0, abs=1e-12) and pure["mounted"]
    assert abs(cuts["first"]) == pytest.approx(1) and abs(cuts["late"]) < 0.2 and abs(cuts["second"]) == pytest.approx(1) and cuts["seeded"] != 0
    assert cuts["atCut"] == pytest.approx(0, abs=1e-9) and cuts["after"] != 0 and cuts["start"] == pytest.approx(0, abs=1e-9)
    settled = -8 * math.tanh(0.7 * 3 / 8)                                                # a share 0.7 of the jump taken back, under the soft limit
    assert exposure["before"] == 0 and abs(exposure["lateAt"]) < 0.4 and exposure["end"] == pytest.approx(settled, abs=0.06)
    assert exposure["low"] < 1.2 * settled and exposure["calmLow"] > settled - 0.02 and exposure["calmEnd"] == pytest.approx(settled, abs=0.02) and exposure["limited"] >= -1
    assert 'unknown option "hnd" (did you mean "hand"?)' in said[0] and 'did you mean "handheld"' in said[1] and 'unknown option "drift"' in said[2]
    assert "needs a meter" in said[3] and 'did you mean "hunt"' in said[4] and "degrees must be a number from -20 to 20" in said[5] and "at least 2 seconds" in said[6]


PAGE = """
import * as THREE from "three";
import {air, sunDirection} from "vidgen/space-air";
import {sea} from "vidgen/space-sea";
import {clouds} from "vidgen/space-clouds";
import {airCamera} from "vidgen/space-camera-air";
let renderer, scene, camera, sky, water, weather, cam, c;
window.made = {clear: [], heights: [], error: null};
export function load(ctx) {
  c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(40, ctx.width / ctx.height, 2, 4e6);
  sky = air(renderer, "earth", {sun: sunDirection(14, 40)});
  water = sea(renderer, sky, {state: "swell", seed: 3});
  weather = clouds(renderer, sky, {seed: 4, decks: [{type: "stratus", base: 1500, top: 2300}]});
  scene.add(sky.object, water.object, weather.object);
  cam = airCamera({camera, sky, water, clouds: weather});
}
const MOVES = {skim: (t) => cam.skim(t, {over: [0, 4], heading: 60, speed: 120, clearance: 6, turn: 20, lens: "wide"}), climb: (t) => cam.climbThrough(t, {over: [0, 4], heading: 40, below: 300, above: 500, lens: "wide"})};
export function frame(t, ctx) {
  try {
    const [move, T] = c.order[Math.round(t * ctx.fps)], shot = cam.apply(T, MOVES[move](T));
    sky.update(T, {camera}); water.update(T, {camera}); weather.update(T, {camera});
    window.made.clear.push(cam.clearance(shot.from, T)); window.made.heights.push(shot.height);
    renderer.render(scene, camera);
  } catch (e) { window.made.error = String(e && e.stack || e); }
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_two_moves_draw_the_same_frames_in_any_order_in_chromium(tmp_path: Path) -> None:
    """A low pass over a swell and a climb through a deck, three times each, drawn in two orders in two pages:
    the frame at t is the same picture whatever was drawn before it, and the camera is over the water in each."""
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "moves.js").write_text(PAGE, encoding="utf-8")
    first = [["skim", 0.5], ["climb", 1.0], ["skim", 2.0], ["climb", 2.5], ["skim", 3.5], ["climb", 3.5]]
    second = [first[k] for k in (5, 2, 3, 0, 4, 1)]

    def draw(order: list) -> tuple[dict, dict]:
        with WebPage(tmp_path, WebEntry("script", "moves.js"), scene_id="s", size=(160, 90), fps=10, frames=len(order), data={"order": order}) as page:
            frames = {f"{move}@{at}": page.frame(k)[..., :3].astype(int) for k, (move, at) in enumerate(order)}
            made = page._page.evaluate("window.made")
            assert made["error"] is None, made["error"]
            return frames, {f"{move}@{at}": (made["clear"][k], made["heights"][k]) for k, (move, at) in enumerate(order)}

    a, numbers_a = draw(first)
    b, numbers_b = draw(second)
    assert set(a) == set(b) and numbers_a == numbers_b
    for key, frame in a.items():
        assert frame.max() > 60, key                                                    # a picture, not black
        assert np.abs(frame - b[key]).max() <= 2, key                                   # the same frame after other frames
    assert all(clear >= 3 for clear, _ in numbers_a.values())                           # never under the rig's margin over the waves
    assert numbers_a["skim@2.0"][0] < 20 and numbers_a["climb@1.0"][1] < 1500 < 2300 < numbers_a["climb@3.5"][1]
    assert np.abs(a["skim@0.5"] - a["skim@3.5"]).mean() > 1 and np.abs(a["climb@1.0"] - a["climb@3.5"]).mean() > 10      # the moves move
