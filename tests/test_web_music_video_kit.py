"""vidgen's building blocks for music videos (Step 358): the modules
``vidgen/music-time`` (song time, bars, the score's events as arrays, reactions, seeded numbers,
easing; plain JavaScript) and ``vidgen/three-kit`` (three.js: glowing lines, crystals, the
tesseract, the nebula sky, portals, star fields, flares, shock rings, ribbons, spectrum rays,
tunnels, rings, swarms, dust, the camera), served by name through the import map and in a page's
loaded-files record; their functions run in Node when it is installed; the four examples built on
them (examples/parallel-space, escapement, signal-fire, three-finish) import them instead of
keeping their own copies. In Chromium (``slow``): a page built from both draws the same frames twice."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = {"vidgen/music-time": DATA / "web" / "modules" / "music-time.js", "vidgen/three-kit": DATA / "web" / "modules" / "three-kit.js"}
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)


def test_the_modules_are_served_by_their_import_names() -> None:
    for name, path in MODULES.items():
        assert VIDGEN_MODULES[name] == path.name
        assert IMPORT_MAP["imports"][name] == f"/__vidgen__/modules/{path.name}"
        assert vidgen_file(f"modules/{path.name}") == path and path.stat().st_size < 60_000
    assert VIDGEN_MODULES["vidgen/three-finish"] == "three-finish.js"


def test_the_modules_import_only_three_and_each_other_and_are_in_no_other_key() -> None:
    assert STATIC_IMPORT.findall(MODULES["vidgen/music-time"].read_text(encoding="utf-8")) == []
    assert STATIC_IMPORT.findall(MODULES["vidgen/three-kit"].read_text(encoding="utf-8")) == ["three", "vidgen/music-time"]
    for path in MODULES.values():
        assert "Math.random" not in path.read_text(encoding="utf-8") and path not in INIT_FILES and path.stem not in engine_id()
        rel = f"__vidgen__/modules/{path.name}"
        assert len(current_loaded(Path("."), [rel])[rel] or "") == 64


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    return node


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import both modules in Node (``three`` from vidgen's copy, ``vidgen/*`` by their import
    names) as ``T`` (music-time) and ``K`` (three-kit), and print ``body``'s ``out`` as JSON."""
    three = tmp_path / "node_modules" / "three"
    three.mkdir(parents=True)
    for name in ("three.module.js", "three.core.js"):
        (three / name).symlink_to(DATA / "three" / name)
    (three / "package.json").write_text(json.dumps({"name": "three", "type": "module", "exports": {".": "./three.module.js"}}), encoding="utf-8")
    vidgen = tmp_path / "node_modules" / "vidgen"
    vidgen.mkdir()
    for path in MODULES.values():
        (vidgen / path.name).symlink_to(path)
    (vidgen / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {
        "./music-time": "./music-time.js", "./three-kit": "./three-kit.js"}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text("import * as T from 'vidgen/music-time';\nimport * as K from 'vidgen/three-kit';\nconst out = [];\n"
                                    "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
                                    f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([_node(), "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=30, check=True)
    return json.loads(done.stdout)


# A stand-in for ctx.music: events(track) as the page's helper gives them (sorted by time).
FAKE_MUSIC = """
const ev = (track, time, duration, extra = {}) => ({track, time, duration, end: time + duration, gain: 1, dynamic: 0, dynamicEnd: 0, pitch: null, ...extra});
const tracks = {
  kick: [ev("kick", 0, 0.1), ev("kick", 0.5, 0.1, {gain: 1.5}), ev("kick", 1.0001, 0.1)],
  hook: [ev("hook", 0, 0.4, {pitch: 60}), ev("hook", 0.5, 0.5, {pitch: 64}), ev("hook", 2, 0.5)],
  low: [ev("low", 0.25, 1, {pitch: 40, dynamic: -6, dynamicEnd: 0})],
  pad: [ev("pad", 0.1, 4, {pitch: 48})],
};
const M = {events: (k, a = -Infinity, b = Infinity) => tracks[k].filter((e) => e.time >= a - 1e-6 && e.time < b - 1e-6)};
"""


def test_music_time_shapes_numbers_bars_and_reactions(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, FAKE_MUSIC + """
out.push([T.clamp(2), T.clamp(-1), T.mix(2, 4, 0.25), T.smoothstep(0, 2, 1), T.smoothstep(0, 1, 2), T.smootherstep(0.5), T.easeOutCubic(1), T.dbToGain(-20)]);
const a = T.rng(7), b = T.rng(7); out.push([a(), a(), a()].join() === [b(), b(), b()].join(), T.hash(3, 1) === T.hash(3, 1), T.hash(3, 1) !== T.hash(3, 2));
out.push(T.keyframes([[0, 0, 10], [2, 4, 20]], -1), T.keyframes([[0, 0, 10], [2, 4, 20]], 1), T.keyframes([[0, 0, 10], [2, 4, 20]], 9), T.glide([0, 0], [10, 2], 0.5));
const clock = T.barClock(2); out.push(clock, T.count(3.9999999, 2), T.count(5.9, 2));
const S = T.trackArrays(M, {hits: ["kick"], notes: {melody: ["hook"], all: ["pad", "low"]}, grid: 0.125});
out.push(Array.from(S.hits.kick.t), Array.from(S.hits.kick.g), Array.from(S.notes.melody.p), Array.from(S.notes.all.t), T.lastIndex(S.hits.kick.t, 0.49), T.lastIndex(S.hits.kick.t, -1));
out.push(T.hitEnvelope(S.hits.kick, 0.5, 0.1), T.hitEnvelope(undefined, 1, 1), T.hitCount(S.hits.kick, 0.6), T.hitAge(S.hits.kick, -1));
out.push(T.noteAt(S.notes.melody, 0.75), T.noteLevel(S.notes.melody, 0.525), T.noteLevel(S.notes.melody, 1.5, 0.05, 0.5), T.noteEnvelope(S.notes.melody, 0.6, 0.1));
out.push(T.melody(S.notes.melody, -1), T.melody(S.notes.melody, 0.5)[0], T.melody(S.notes.melody, 0.7)[0]);
out.push(T.eventLevel(tracks.low[0], 0.25), T.eventLevel(tracks.low[0], 1.25), T.signalLevel(M, "low", 1.25), T.signalLevel(M, "low", 1.55), T.signalLevel(M, "low", 1.85));out.push(T.melody(S.notes.melody, 0.01)[1], T.melody(S.notes.melody, 0.5)[1], T.melody(S.notes.melody, 0.525)[1], T.melody(S.notes.melody, 0.6)[1]);
""")
    shapes, seeded, moves, (clock, whole, short), (kick_t, kick_g, pitches, gathered, idx, before) = out[0], out[1:4], out[4:8], out[8:11], out[11:17]
    assert shapes == pytest.approx([1, 0, 2.5, 0.5, 1, 0.5, 1, 0.1])
    assert seeded == [True, True, True]
    assert moves == [[0, 10], [2, 15], [4, 20], pytest.approx([5, 1])]
    assert clock == {"bar": 2, "beat": 0.5, "sixteenth": 0.125} and whole == 2 and short == 2
    assert kick_t == pytest.approx([0, 0.5, 1.000125], abs=1e-6) and kick_g == [1, 1.5, 1]      # 1.0001 s = 8.0008 sixteenths -> 8.001
    assert pitches == [60, 64, 0] and gathered == pytest.approx([0.1, 0.25]) and idx == 0 and before == -1
    envelope, missing, hits, age = out[17:21]
    assert envelope == pytest.approx(1.25) and missing == 0 and hits == 2 and age == 1e9
    note, rising, released, glint = out[21:25]
    assert note["i"] == 1 and note["p"] == 64 and note["age"] == pytest.approx(0.25) and note["d"] == pytest.approx(0.5)
    assert rising == pytest.approx(0.5) and released == pytest.approx(np.exp(-1)) and glint == pytest.approx(np.exp(-1))
    assert out[25] == [60, 0] and out[26] == pytest.approx(60) and out[27] == pytest.approx(64)
    start, end, held, fading, gone = out[28:33]
    assert start == pytest.approx(10 ** (-6 / 20)) and end == pytest.approx(1) and held == pytest.approx(1)
    assert fading == pytest.approx(0.5) and gone == 0
    # Step 362: a note's attack rises from the level the note before has at its start (no dip on each note)
    first, onset, rising, held = out[33:37]
    carried = np.exp(-0.1 / 0.45)  # the first note ended 0.1 s before the second
    assert first == pytest.approx(0.2) and onset == pytest.approx(carried) and rising == pytest.approx(carried + (1 - carried) * 0.5) and held == 1


def test_music_time_camera_paths_colour_script_and_reactions(tmp_path: Path) -> None:
    """Step 359's additions: orbit, pathPoint, flyThrough, colourScript, reactions."""
    out = _run_in_node(tmp_path, FAKE_MUSIC + """
M.level = () => 0.25;
out.push(T.orbit(0, {radius: 10, height: 2}), T.orbit(Math.PI / 2 / 0.5, {centre: [1, 0, 0], radius: 10, height: 2, speed: 0.5}));
const P = [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]];
out.push(T.pathPoint(P, 0), T.pathPoint(P, 1 / 3), T.pathPoint(P, 1), T.pathPoint(P, 2), T.pathPoint([[0, 0, 0], [4, 2, 0]], 0.5));
out.push(T.flyThrough(P, 0.5, 0.1), T.flyThrough(P, 1, 0.1));
const S = T.colourScript([{at: 0, role: "intro", base: "#000000"}, {at: 4, role: "drop", base: "#ff8000"}]);
const G = T.colourScript([{at: 0, base: "#000000"}, {at: 4, base: "#ff8000"}], 2);
out.push(S(-1), S(3.999), S(4), S(99), G(1), G(3).base, G(3.999999).base, G(4).base);
const R = T.reactions(M, {pulse: ["kick"], ring: ["kick"], glint: ["hook"], glow: ["pad"]}, {drops: [2]});
const E = T.reactions(M, {});
out.push(R.pulse(0.5), R.glow(1), R.drop(1.9), R.drop(2.5), R.ring === R.song.hits.kick, R.glints.length, Array.from(R.glints[0].p), E.pulse(0.5), E.glow(1), E.ring, E.drop(5));
""")
    assert out[0] == pytest.approx([0, 2, 10, 0, 0, 0])
    assert out[1] == pytest.approx([11, 2, 0, 1, 0, 0], abs=1e-9)          # a quarter turn at 0.5 rad/s
    start, third, end, past, middle = out[2:7]
    assert start == pytest.approx([0, 0, 0]) and third == pytest.approx([10, 0, 0]) and end == pytest.approx([0, 10, 0])
    assert past == end and middle == pytest.approx([2, 1, 0])                  # through every point; clamped; straight for two
    mid, last = out[7:9]
    assert len(mid) == 6 and mid[:3] == pytest.approx([11.25, 5, 0]) and mid[4] > mid[1]
    assert last[:3] == pytest.approx([0, 10, 0]) and last[3] < 0                # past the end: on in its direction (-x)
    before, held, at, after, early, gliding, last_moment, cut = out[9:17]
    assert before["role"] == "intro" and before["base"] == 0 and held["base"] == 0 and at == {"at": 4, "role": "drop", "base": 0xff8000} and after["role"] == "drop"
    assert early["base"] == 0 and 0 < gliding < 0xff8000 and gliding >> 16 == 128 and last_moment >> 16 > 250 and cut == 0xff8000
    pulse, glow, before_drop, after_drop, ring, glints, pitches, no_pulse, level, no_ring, no_drop = out[17:28]
    assert pulse == pytest.approx(1.25) and glow == pytest.approx(1) and before_drop == 0 and after_drop == pytest.approx(np.exp(-1))
    assert ring is True and glints == 1 and pitches == [60, 64, 0]
    assert no_pulse == 0 and level == 0.25 and no_ring is None and no_drop == 0


def test_three_kit_geometry_and_its_stage(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push(err(() => new K.Glow(4)), err(() => K.polyhedronEdges("sphere")));
out.push(K.TESSERACT_VERTICES.length, K.TESSERACT_EDGES.length, K.project4([1, 1, 1, 1], [0, 0, 0, 0, 0, 0]), K.tesseractAngles(0, 1).slice(0, 3));
out.push(K.POLYHEDRA, K.POLYHEDRA.map((k) => K.polyhedronEdges(k).length / 6), K.circleSegments(4, 2).length, K.wrapZ(0, 0, 100, 0, 10), K.wrapZ(0, 95, 100, 0, 10));
out.push(K.mixColor(K.color(0x000000), K.color(0xffffff), 2).r, K.WARM_WHITE.getHexString());
const THREE = await import("three");
const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(50, 16 / 9, 0.3, 100);
K.setStage({scene, camera, width: 640, height: 360});
const g = new K.Glow(3, {px: 2}); g.seg(0, 0, 0, 0, 1, 2, 3); g.col(0, K.WARM_WHITE, 2, 1.5); g.count(9);
out.push(scene.children.length, Array.from(g.b.slice(0, 3)), g.c[3], g.geo.instanceCount, g.mat.uniforms.uK.value);
K.aimCamera(0, 0, 10, 0, 0, 0, 0, 40); out.push(camera.fov, camera.position.z);
const ring = K.makeTesseract({world: 0.05}); K.updateTesseract(ring, K.tesseractAngles(1), K.WARM_WHITE); out.push(ring.userData.gl.max);
""")
    assert "call setStage({scene, ...}) in load first" in out[0] and 'no polyhedron "sphere"' in out[1]
    assert out[2:4] == [16, 32] and out[4] == pytest.approx([3.1 / 2.1] * 3) and out[5] == pytest.approx([1, 0, 0.5])
    assert out[6] == ["octa", "tetra", "ico", "dodeca", "cube"] and out[7] == [12, 6, 30, 30, 12]
    assert out[8] == 24 and out[9] == -10 and out[10] == -15
    assert out[11] == 1 and out[12] == "fff4e6"
    assert out[13:18] == [1, [1, 2, 3], 1.5, 3, 0.5]
    assert out[18:20] == [40, 10] and out[20] == 48


PAGE = """import * as THREE from "three";
import {trackArrays, hitEnvelope, smootherstep} from "vidgen/music-time";
import {setStage, color, SkyDome, Glow, makeTesseract, updateTesseract, tesseractAngles, makeStarField, updateStarField, aimCamera} from "vidgen/three-kit";
let renderer, scene, camera, sky, tes, stars, lines;
export function load(ctx) {
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(50, ctx.width / ctx.height, 0.3, 4000);
  setStage({renderer, scene, camera, width: ctx.width, height: ctx.height});
  sky = new SkyDome(3); stars = makeStarField(200, [5, 60], 200, 11);
  tes = makeTesseract({world: 0.05}); tes.scale.setScalar(2);
  lines = Glow.from([-3, -2, 0, 3, -2, 0], {px: 3});
}
export function frame(t) {
  aimCamera(Math.sin(t) * 2, 0.5, 9 - smootherstep(t / 2), 0, 0, 0);
  sky.turn(t); sky.colors(color(0x010308), color(0x06203a), color(0x2a7fa0), 0.5); sky.follow(camera);
  updateStarField(stars, t, 5 * t, 0.5);
  updateTesseract(tes, tesseractAngles(t), color(0x9fdcff), 1.5);
  lines.tint(color(0xffd166), 1 + t);
  renderer.render(scene, camera);
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_a_page_built_from_the_kit_draws_the_same_frames_every_time(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "kit.js").write_text(PAGE, encoding="utf-8")

    def draw() -> tuple[list[np.ndarray], dict]:
        with WebPage(tmp_path, WebEntry("script", "kit.js"), scene_id="k", size=(160, 90), fps=10, frames=6) as page:
            return [page.frame(n) for n in (1, 4)], dict(page.loaded)

    (first, loaded), (again, _) = draw(), draw()
    assert all(np.array_equal(a, b) for a, b in zip(first, again)) and not np.array_equal(first[0], first[1])
    assert first[0][..., :3].mean() > 2      # the sky and the lines drew something
    for path in MODULES.values():
        assert f"__vidgen__/modules/{path.name}" in loaded


EXAMPLES = ROOT / "examples"


def test_the_examples_import_the_kit_instead_of_their_own_copies() -> None:
    ps = (EXAMPLES / "parallel-space" / "extensions" / "ps.js").read_text(encoding="utf-8")
    esc = (EXAMPLES / "escapement" / "extensions" / "escapement.js").read_text(encoding="utf-8")
    fire = (EXAMPLES / "signal-fire" / "extensions" / "signal_fire.js").read_text(encoding="utf-8")
    still = (EXAMPLES / "three-finish" / "extensions" / "still_life.js").read_text(encoding="utf-8")
    for page in (ps, esc, fire, still):
        assert 'from "vidgen/music-time"' in page
    for page in (ps, esc, fire):
        assert 'from "vidgen/three-kit"' in page
    for gone in ("class Glow", "GLOW_VERT", "BAKE_FRAG", "function project4", "function lastIdx", "function makeStars", "function setCam"):
        assert gone not in ps, gone
    for gone in ("function lastIdx", "function makeDust", "function path(", "const hash1"):
        assert gone not in esc, gone
    for gone in ("function levelOf", "function sounding", "const ease"):
        assert gone not in fire and "const ease" not in still, gone
