"""Suns and light, ``vidgen/space-light`` (Step 372, DESIGN.md §122.8): the module is served by its
import name and imports only ``three``, ``vidgen/music-time`` and ``vidgen/space-sky``; its parts are
registered; in Node (when it is installed): the stars' options and errors with a did-you-mean,
colours by temperature, spots, loops and the corona's map from a seed, how much of a sun shows past
a body (smoothly, reddened by air), planet-shine, ring-shine, the film convention, sunlight with
distance, the exposure modes and the automatic exposure, and ``spaceLight`` on stand-in bodies (each
body's sun, its second light, eclipses, the lights for ordinary meshes); in Chromium (``slow``): a
star is a round disc with a darker limb and a corona, the same frame twice, steady while it boils; a
far sun is a glare that a body hides; planet-shine lights a night side; an eclipse darkens the
ground; an honest exposure takes the stars away; and the Sun of ``ctx.orbits`` is placed and its
glare drawn over a world through ``vidgen/space-scale``."""

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
MODULE = MODULES / "space-light.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
STARS = ["red-dwarf", "orange", "sun", "white", "blue-giant"]
PART_NAMES = ({f"sun-{s}" for s in STARS if s != "sun"} | {"sun-yellow", "sun-far", "sunrise-limb", "sunrise-diamond", "planet-shine", "eclipse-shadow", "eclipse-moon",
                                              "exposure-film", "exposure-camera", "exposure-camera-stars", "exposure-auto"})


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-light"] == "space-light.js"
    assert IMPORT_MAP["imports"]["vidgen/space-light"] == "/__vidgen__/modules/space-light.js"
    assert vidgen_file("modules/space-light.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-light.js"])["__vidgen__/modules/space-light.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/music-time", "vidgen/space-sky"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-light" not in engine_id()


def test_the_parts_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-light.js"}
    assert set(found) == PART_NAMES
    assert all(p.module == "vidgen/space-light" and p.kind == "light" for p in found.values())
    assert 'star(renderer, "sun")' in found["sun-yellow"].use and "spaceLight(" in found["planet-shine"].use and "eclipses: true" in found["eclipse-shadow"].use
    assert "honest" in found["exposure-camera"].label and "convention" in found["exposure-film"].label     # which mode is honest is said on the sheet
    assert "Math.random" not in (P.PARTS_DIR / "space-light.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``L`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "space-scale", "space-sky", "space-sky-stars", "space-light")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as THREE from 'three';\nimport * as L from 'vidgen/space-light';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_stars_from_a_name_a_temperature_and_a_seed(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push(Object.keys(L.STARS), L.EXPOSURES, L.QUALITIES);
out.push(Object.keys(L.STARS).map((k) => { const o = L.resolveStar(k); return [o.name, o.temperature, o.spots, o.prominences, o.granulation]; }));
out.push([err(() => L.resolveStar("sn")), err(() => L.resolveStar("sun", {spikes: 5})), err(() => L.resolveStar({temperatur: 5000})), err(() => L.resolveStar("sun", {quality: "fine"})),
  err(() => L.resolveStar("sun", {direction: [0, 0, 0]})), err(() => L.resolveStar({like: "sol"})), err(() => L.resolveStar("sun", {spots: 99}))]);
const mine = L.resolveStar({temperature: 12000, seed: 4}), like = L.resolveStar({like: "red-dwarf", spots: 1}), far = L.resolveStar("Sun", {direction: [1, 0, 0], flare: 0});
out.push([mine.temperature, mine.cells, like.temperature, like.spots, like.cells, far.direction, far.flare, far.name, Math.abs(far.angularRadius - 0.2665) < 1e-3]);
out.push([3200, 4600, 5772, 8500, 22000].map((T) => L.starTint(T, 1)), L.sunlightColor(5772), L.sunlightColor(3200), L.sunlightColor(22000));
const a = L.starSpots(13, 5, 1), b = L.starSpots(13, 5, 1), c = L.starSpots(14, 5, 1);
out.push([a.length, JSON.stringify(a) === JSON.stringify(b), JSON.stringify(a) === JSON.stringify(c), a.every((s) => Math.abs(Math.hypot(s[0], s[1], s[2]) - 1) < 1e-9 && Math.abs(s[1]) < 0.6 && s[3] > 0.01 && s[3] < 0.12),
  L.starSpots(13, 0).length, L.starSpots(13, 5, 2)[0][3] / a[0][3]]);
const l = L.starLoops(13, 4), l2 = L.starLoops(13, 4);
out.push([l.length, JSON.stringify(l) === JSON.stringify(l2), l.every((x) => Math.abs(x.foot[0] * x.along[0] + x.foot[1] * x.along[1] + x.foot[2] * x.along[2]) < 1e-9 && x.radius > 0.04 && x.radius < 0.17)]);
const f = L.coronaFaces(13, 16, 1), g = L.coronaFaces(13, 16, 1), h = L.coronaFaces(14, 16, 1);
const mean = (d, k) => { let s = 0; for (let i = k; i < d.length; i += 4) s += d[i]; return s / (d.length / 4); };
out.push([f.length, f[0].length, f.every((d, i) => d.every((v, j) => v === g[i][j])), f.some((d, i) => d.some((v, j) => v !== h[i][j])), f.map((d) => mean(d, 0)), Math.max(...f.map((d) => Math.max(...d))), Math.min(...f.map((d) => Math.min(...d)))]);
out.push([L.pointShare(3), L.pointShare(1), L.glareShare(5), L.glareShare(85) > 0 && L.glareShare(85) < 1, L.glareShare(200)]);
""")
    names, exposures, qualities, stars, errors, merged, colours, spots, loops, corona, shares = out[0], out[1], out[2], out[3], out[4], out[5], out[6:10], out[10], out[11], out[12], out[13]
    assert names == STARS and exposures == ["film", "camera", "auto"] and qualities == ["fast", "standard"]
    by = {s[0]: s for s in stars}
    assert [by[n][1] for n in STARS] == sorted(by[n][1] for n in STARS) and by["sun"][1] == 5772        # from cool to hot
    assert by["blue-giant"][2] == 0 and by["blue-giant"][3] == 0 and by["red-dwarf"][4] > by["sun"][4] > by["white"][4]   # hot stars: no spots, smooth
    wrong_name, bad_spikes, wrong_key, bad_quality, zero, bad_like, many = errors
    assert 'did you mean "sun"' in wrong_name and "red-dwarf, orange, sun" in wrong_name and "0, 4, 6 or 8" in bad_spikes
    assert 'did you mean "temperature"' in wrong_key and '"standard"' in bad_quality and "direction" in zero and 'did you mean "sun"' in bad_like and "0 to 12" in many
    assert merged == [12000, 32, 3200, 1, 16, [1, 0, 0], 0, "sun", True]
    tints, white, red, blue = colours
    assert all(abs(max(t) - 1) < 1e-9 for t in tints)
    assert tints[0][0] == 1 and tints[0][2] < 0.35 and tints[4][2] == 1 and tints[4][0] < 0.8                 # a red dwarf is red, a blue giant blue
    assert [t[2] / t[0] for t in tints] == sorted(t[2] / t[0] for t in tints)                                 # bluer with temperature
    assert np.allclose(white, [1, 1, 1], atol=1e-9) and red[0] > red[1] > red[2] and blue[2] > blue[1] > blue[0]   # the Sun's light is white here
    assert abs(0.2126 * red[0] + 0.7152 * red[1] + 0.0722 * red[2] - 1) < 1e-9
    assert spots[:4] == [5, True, False, True] and spots[4] == 0 and abs(spots[5] - 2) < 1e-9
    assert loops == [4, True, True]
    assert corona[:4] == [6, 16 * 16 * 4, True, True] and all(60 < m < 180 for m in corona[4]) and corona[5] > 200 and corona[6] < 40
    assert shares[0] == 0 and shares[1] == 1 and shares[2] == 1 and shares[3] is True and shares[4] == 0


def test_how_much_of_the_sun_a_body_leaves(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const sun = [0, 0, -1000], R = 4.65;                                   // 0.27 degrees, as the Sun from the Earth
const at = (up) => ({at: [0, up - 100, -300], radius: 100, air: null});   // a body whose limb stands `up` over the sun's middle
out.push(L.sunVisibility(sun, R, []), L.sunVisibility(sun, R, [{at: [0, 0, 300], radius: 100, air: null}]), L.sunVisibility(sun, R, [{at: [0, 0, -2000], radius: 100, air: null}]));
out.push(L.sunVisibility(sun, R, [at(-5)]), L.sunVisibility(sun, R, [at(5)]), L.sunVisibility(sun, R, [at(0)]));
const run = []; for (let i = 0; i <= 200; i++) run.push(L.sunVisibility(sun, R, [at(-2 + 4 * i / 200)]).fraction[1]);
out.push(run);
const air = {height: 0.0014, ext: [0.02, 0.05, 0.11]};
out.push(L.sunVisibility(sun, R, [{at: [0, -100.6, -300], radius: 100, air}]), L.sunVisibility(sun, R, [{at: [0, -103, -300], radius: 100, air}]));
out.push([L.tangentColumn(0, 0.0014), L.tangentColumn(0.0014, 0.0014) / L.tangentColumn(0, 0.0014), L.tangentColumn(0.02, 0.0014)]);
out.push(L.sunVisibility(sun, R, [{at: [-100, 0, -300], radius: 100, air: null}]).offset);
""")
    free, behind_eye, beyond, clear, hidden, half, run, low, high, column, side = out
    assert free["fraction"] == [1, 1, 1] and behind_eye["fraction"] == [1, 1, 1] and beyond["fraction"] == [1, 1, 1]    # only what stands between counts
    assert clear["fraction"] == [1, 1, 1] and clear["covered"] == 0 and max(hidden["fraction"]) == 0 and hidden["covered"] == 1
    assert abs(half["fraction"][0] - 0.5) < 0.03 and half["offset"][1] > 0.3 and abs(half["offset"][0]) < 0.05           # the upper half is left: its light's middle is up
    steps = np.diff(run)
    assert run[0] == 1 and run[-1] == 0 and steps.max() <= 1e-9 and steps.min() > -0.02                                    # sinking smoothly: no step over 2 % in 200
    assert low["fraction"][0] > low["fraction"][1] > low["fraction"][2] > 0 and low["fraction"][0] < 0.9                  # through the air: dimmed, red most of what is left
    assert min(high["fraction"]) > 0.97                                                                                   # well over the air: as it is
    assert 60 < column[0] < 75 and abs(column[1] - np.exp(-1)) < 0.01 and column[2] < 1e-4
    assert side[0] > 0.3 and abs(side[1]) < 0.05                                                                           # a body at the left leaves the right half


def test_planet_shine_and_exposure(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push([L.planetShine(0.3, 6371, 384400, 0), L.planetShine(0.3, 6371, 384400, Math.PI), L.planetShine(0.3, 6371, 384400, Math.PI / 2) / L.planetShine(0.3, 6371, 384400, 0),
  L.planetShine(0.3, 6371, 6771, 0), L.planetShine(0.5, 71492, 421700, 0), L.phaseLight(0), L.phaseLight(Math.PI / 2)]);
out.push([L.filmShine(0), L.filmShine(5.5e-5), L.filmShine(0.18), L.filmShine(1e-12), L.filmShine(0.01) > L.filmShine(0.001), L.ringShine(1, 0), L.ringShine(1, 0.35), L.ringShine(0.5, 0.35) / L.ringShine(1, 0.35)]);
out.push([L.sunlight(30, 1, 2), L.sunlight(30, 1, 0), L.sunlight(30, 1, 1), L.sunlight(1, 1, 2), L.AU, L.SKY_STOPS, L.LIGHTS_STOPS, L.BURN]);
out.push([L.exposureGains("film"), L.exposureGains("camera", 0), L.exposureGains("camera", 20), L.exposureGains("auto", 12), err(() => L.exposureGains("camra"))]);
out.push([L.autoExposure([]), L.autoExposure([{ev: 0, share: 0.3}]), L.autoExposure([{ev: 0, share: 1e-6}]), L.autoExposure([{ev: 0, share: 2e-3}]),
  L.autoExposure([{ev: 12.6, share: 0.2}]), L.autoExposure([{ev: 12.6, share: 0.2}, {ev: 0, share: 0.3}]), L.autoExposure([{ev: 9.8, share: 0.3}]), L.autoExposure([], {evMax: 14})]);
const open = []; for (let i = 0; i <= 100; i++) open.push(L.autoExposure([{ev: 0, share: Math.pow(10, -5 + 4 * i / 100)}]));
out.push(open);
""")
    shine, film, sun, gains, auto, opening = out
    assert 4.5e-5 < shine[0] < 6.5e-5 and shine[1] < 1e-12 and abs(shine[2] - 1 / np.pi) < 1e-9          # the full Earth on the Moon; a new Earth; half an Earth
    assert shine[3] <= 0.3 and shine[3] > 0.15 and 0.005 < shine[4] < 0.02 and shine[5] == 1              # a low orbit: under the albedo; Jupiter on Io: a hundredth
    assert film[0] == 0 and abs(film[1] - 0.05) < 0.003 and abs(film[2] - 0.18) < 0.005 and film[3] < 1e-6 and film[4] is True
    assert film[5] == 0 and 0.03 < film[6] < 0.05 and abs(film[7] - 0.5) < 1e-9
    assert abs(sun[0] - 1 / 900) < 1e-12 and sun[1] == 1 and abs(sun[2] - 1 / 30) < 1e-12 and sun[3] == 1 and sun[5:] == [20, 10, 32]
    assert gains[0] == {"sun": 1, "sky": 1, "lights": 1, "film": True, "ev": 0}
    assert gains[1]["sun"] == 1 and abs(gains[1]["sky"] - 2 ** -20) < 1e-12 and gains[1]["film"] is False   # honest: the stars are a million times fainter
    assert gains[2]["sun"] == 2 ** 20 and gains[2]["sky"] == 1 and gains[2]["lights"] == 1 and gains[3]["ev"] == 12 and 'did you mean "camera"' in gains[4]
    assert auto[0] == 20 and auto[1] == 0 and auto[2] == 20 and 0 < auto[3] < 20                            # nothing lit; a day side; a few pixels; a sliver
    assert auto[4] == 12.6 and auto[5] == 0 and auto[6] == 9.8 and auto[7] == 14
    assert opening[0] == 20 and opening[-1] == 0 and np.diff(opening).max() <= 1e-9 and np.diff(opening).min() > -0.8   # opens smoothly as the lit share shrinks


NODE_LIGHT = """
// stand-ins for bodies of vidgen/space-bodies: what spaceLight reads and sets
function body(name, at, radius, extra = {}) {
  const object = new THREE.Group(); object.position.set(...at); object.scale.setScalar(radius);
  const b = {name, object, options: {light: 1, air: null, ...extra}, albedo: extra.albedo ?? [0.3, 0.3, 0.3], fill: {direction: new THREE.Vector3(0, 1, 0), color: new THREE.Color(0, 0, 0)}, got: null,
    setSun(direction, o) { this.got = {direction: [...direction], ...o}; return this; }};
  return b;
}
const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 1000);
camera.position.set(0, 0, 8); camera.lookAt(0, 0, 0);
const sky = {level: null, skyMaterial: {uniforms: {uGain: {value: 1.5}}}, set({brightness}) { this.level = brightness; }};
const build = (o = {}, sun = [1, 0, 0]) => {
  const earth = body("earth", [0, 0, 0], 1, {albedo: [0.2, 0.3, 0.5], air: {height: 0.0014, rayleigh: [0.02, 0.05, 0.11], haze: [0, 0, 0], absorb: [0, 0, 0]}});
  const moon = body("moon", [0, 0, 60], 0.27, {albedo: [0.12, 0.12, 0.12]});
  scene.add(earth.object, moon.object);
  const light = L.spaceLight({scene, camera, sun, bodies: [earth, moon], sky, ...o});
  light.update(0);
  return {earth, moon, light};
};
"""


def test_the_light_of_a_scene_on_stand_in_bodies(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, NODE_LIGHT + """
let w = build();
out.push([w.earth.got, w.moon.got, w.moon.fill.direction.toArray(), w.moon.fill.color.toArray(), w.light.state.bodies[1].honest, w.light.state.ev, sky.level,
  w.light.directional.intensity, w.light.fill.intensity, w.light.directional.parent === scene, w.earth.fill.color.toArray()]);
w = build({shine: 0}); out.push(w.moon.fill.color.toArray());
w = build({exposure: "camera", ev: 3}); out.push([w.earth.got.intensity, sky.level, w.moon.fill.color.g / w.light.state.bodies[1].honest, w.light.directional.intensity / Math.PI]);
w = build({exposure: "camera", ev: 20}); out.push([w.earth.got.intensity, sky.level, w.light.state.bodies[1].shine]);
w = build({exposure: "camera", ev: (t) => 2 + t}); out.push(w.light.state.ev);
w = build({exposure: "auto"}); const lit = w.light.state.ev; w = build({exposure: "auto"}, [-0.02, 0, -1]); out.push([lit, w.light.state.ev, sky.level]);
// a sun standing in the scene: directions differ from body to body, and its light falls with the square of the distance if asked
const far = new THREE.Group(); far.position.set(23455, 0, 0); far.scale.setScalar(109); scene.add(far);
w = build({falloff: 2}, far);
const jup = body("far", [-23455 * 4.2, 0, 0], 11); scene.add(jup.object);
const l2 = L.spaceLight({scene, camera, sun: far, bodies: [w.earth, jup], sky, falloff: 2}); l2.update(0);
const l0 = L.spaceLight({scene, camera, sun: far, bodies: [w.earth, jup], sky}); l0.update(0);
out.push([w.moon.got.direction, l2.state.bodies.map((b) => b.intensity), l0.state.bodies.map((b) => b.intensity)]);
// behind the world: its shadow takes the light for ordinary meshes; at the edge of the air what is left is red
const craft = new THREE.Group(); craft.position.set(-1.5, 0, 0); scene.add(craft);
w = build({at: craft}); const dark = w.light.directional.color.toArray();
craft.position.set(-1.5, 1.003, 0); w = build({at: craft}); const red = w.light.directional.color.toArray();
craft.position.set(1.5, 0, 0); w = build({at: craft});
out.push([dark, red, w.light.directional.color.toArray(), w.light.directional.position.toArray(), w.light.fill.intensity / Math.PI, w.light.state.light.source === w.earth]);
out.push([err(() => L.spaceLight({scene, camera})), err(() => L.spaceLight({scene, camera, sun: [1, 0, 0], exposur: "film"})), err(() => L.spaceLight({scene, camera, sun: [1, 0, 0], exposure: "kino"})),
  err(() => L.spaceLight({scene, camera, sun: [1, 0, 0], bodies: [{}]})), err(() => L.spaceLight({scene, camera, sun: [1, 0, 0], shadows: true})), err(() => L.spaceLight({camera, sun: [1, 0, 0]})),
  err(() => L.spaceLight({scene, camera, sun: [1, 0, 0], environment: true}))]);
w.light.dispose(); out.push([w.light.directional.parent === null, sky.level]);
""")
    film, no_shine, cam3, cam20, moving, auto, placed, craft, errors, gone = out
    earth, moon, fill_dir, fill, honest, ev, sky, key, second, in_scene, earth_fill = film
    assert earth == {"direction": [1, 0, 0], "color": [1, 1, 1], "intensity": 1} and moon["intensity"] == 1 and ev == 0 and sky == 1.5     # film: nothing changed
    assert fill_dir[2] < -0.99 and 0 < fill_dir[0] < 0.02                                    # the moon's second light comes from the world, a little from its lit side
    assert 1e-5 < honest < 4e-5 and 0.02 < 0.2126 * fill[0] + 0.7152 * fill[1] + 0.0722 * fill[2] < 0.06 and fill[2] > fill[0]   # half an Earth: lifted by the convention, blue
    assert abs(key - np.pi) < 1e-12 and 0.05 * np.pi < second < 0.12 * np.pi and in_scene is True and max(earth_fill) < 0.01   # at the camera, 8 radii out: a lifted, weak second light
    assert no_shine == [0, 0, 0]
    assert cam3[0] == 8 and abs(cam3[1] - 1.5 * 2 ** -17) < 1e-12 and 7 < cam3[2] < 16 and cam3[3] == 8          # honest: everything 3 stops up, the sky 17 down, shine as faint as it is
    assert cam20[0] == 32 and cam20[1] == 1.5 and cam20[2] > 10                                                   # exposed for the stars: the day side at the burn-out cap
    assert moving == 2
    assert auto[0] == 0 and auto[1] > 6 and auto[2] > 1.5 * 2 ** -14                                              # a day side in the frame; then only a sliver of it
    assert abs(placed[0][0] - 1) < 1e-5 and abs(placed[0][2] + 60 / 23455) < 1e-4                                 # towards the sun from where the moon stands
    assert placed[1][0] == 1 and abs(placed[1][1] - 1 / 5.2 ** 2) < 1e-9 and placed[2] == [1, 1]                  # the first body is the reference; falloff 0 by default
    dark, red, lit, position, shine, source = craft
    assert max(dark) < 1e-6 and red[0] > 1.3 * red[2] and 0.01 < red[0] < 0.99 and lit == [1, 1, 1]
    assert abs(position[0] - 2.5) < 1e-9 and 0.1 < shine < 0.25 and source is True                                  # over the day side: ground-shine from below
    no_sun, wrong_key, wrong_mode, not_a_body, no_renderer, no_scene, no_sky = errors
    assert "direction" in no_sun and 'did you mean "exposure"' in wrong_key and '"film", "camera", "auto"' in wrong_mode and "planet(" in not_a_body
    assert "renderer" in no_renderer and "scene" in no_scene and "sky" in no_sky
    assert gone == [True, 1.5]


PAGE = """
import * as THREE from "three";
import {planet} from "vidgen/space-bodies";
import {spaceSky} from "vidgen/space-sky";
import {SpaceView} from "vidgen/space-scale";
import {star, spaceLight} from "vidgen/space-light";
let renderer, scene, camera, c, sun, light, space, sky, bodies = [];
export function load(ctx) {
  c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  renderer.debug.onShaderError = (gl, program, vs, fs) => { window.shaderError = (gl.getShaderInfoLog(fs) || "") + (gl.getProgramInfoLog(program) || ""); };
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(c.fov ?? 30, ctx.width / ctx.height, 0.01, 1000);
  if (c.sky) { sky = spaceSky(renderer, {seed: 3, size: 512}); scene.add(sky.object); }
  if (c.orbit) space = new SpaceView(ctx, {renderer, scene, camera});
  for (const b of c.bodies ?? []) {
    const body = planet(renderer, b.what, {size: 128, ...(space ? {space} : {}), ...(b.options ?? {})});
    if (!space) { body.object.position.set(...(b.at ?? [0, 0, 0])); body.object.scale.setScalar(b.radius ?? 1); scene.add(body.object); }
    bodies.push(body);
  }
  if (c.star) { sun = star(renderer, c.star.what ?? "sun", {...(space ? {space} : {}), ...(c.star.options ?? {})}); scene.add(sun.object); }
  if (c.light) light = spaceLight({scene, camera, sun: sun ?? c.sun, bodies, sky, ...c.light});
  window.made = {};
}
export function frame(t) {
  if (space) space.update(t, {from: {body: "Earth", offset: c.orbit.offset}, to: c.orbit.to ?? "Sun"});
  else { camera.position.set(...(c.from ?? [0, 0, 8])); camera.lookAt(...(c.to ?? [0, 0, 0])); camera.updateMatrixWorld(); }
  for (const b of bodies) b.update(t, light ? {} : {sun: c.sun ?? [0, 0, 1]});
  if (sun) sun.update(t + (c.t0 ?? 0));
  if (light) light.update(t);
  renderer.setRenderTarget(null); renderer.render(scene, camera);
  window.made = {error: window.shaderError ?? null, seen: sun ? sun.seen : null, state: light ? {ev: light.state.ev, bodies: light.state.bodies.map((b) => [b.intensity, b.shine])} : null,
    scale: sun ? sun.object.scale.x : null, slices: space ? space.slices.length : 0};
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_stars_and_light_draw_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "light.js").write_text(PAGE, encoding="utf-8")

    def draw(data: dict, orbits: dict | None = None, frames: int = 2) -> tuple[list[np.ndarray], dict, dict]:
        with WebPage(tmp_path, WebEntry("script", "light.js"), scene_id="s", size=(320, 180), fps=10, frames=frames, data=data, orbits=orbits) as page:
            got = [page.frame(n)[..., :3].astype(int) for n in range(frames)]
            made = page._page.evaluate("window.made")
            assert made["error"] is None, made["error"]
            return got, dict(page.loaded), made

    # a star close up: a round disc of the right size (radius 1 from 8 with a 30 degree lens: 42 px), limb darker and redder, a corona outside
    (first, second), loaded, made = draw({"star": {"what": "sun", "options": {"glare": 0}}})
    (again, _), _, _ = draw({"star": {"what": "sun", "options": {"glare": 0}}})
    (other, _), _, _ = draw({"star": {"what": "sun", "options": {"glare": 0, "seed": 5}}})
    (bare, _), _, _ = draw({"star": {"what": "sun", "options": {"glare": 0, "corona": 0, "prominences": 0}}})
    assert np.array_equal(first, again) and not np.array_equal(first, other)                     # a seed is a star
    assert {"__vidgen__/modules/space-light.js", "__vidgen__/modules/space-sky.js", "__vidgen__/modules/music-time.js"} <= set(loaded)
    disc = bare.mean(axis=-1) > 60
    assert abs(disc[90].sum() - 84) <= 4 and abs(disc[:, 160].sum() - 84) <= 4 and bare[:, :100].max() < 4
    centre, limb = bare[86:94, 156:164].reshape(-1, 3).mean(axis=0), bare[88:92, 160 + 37:160 + 40].reshape(-1, 3).mean(axis=0)
    assert centre.mean() > limb.mean() + 15 and limb[0] / max(limb[2], 1) > 1.2 * centre[0] / centre[2]   # the limb is darker, and redder
    luma = first.mean(axis=-1)
    near, far = luma[90, 160 + 46:160 + 52].mean(), luma[90, 160 + 120:160 + 140].mean()
    assert 60 < near < 250 and far < near * 0.5 and luma[:4, :4].max() < 30                         # the corona: bright at the limb, fading outward
    # it boils: the cells change from frame to frame, the disc's light does not
    assert not np.array_equal(first, second)
    inside = np.hypot(*np.mgrid[-90:90, -160:160]) < 36
    assert abs(second[inside].mean() / first[inside].mean() - 1) < 0.004 and np.abs(second - first)[inside].mean() < 12   # ... and gently
    # a hot star is white and blue, a cool one red
    (blue, _), _, _ = draw({"star": {"what": "blue-giant", "options": {"glare": 0}}})
    (red, _), _, _ = draw({"star": {"what": "red-dwarf", "options": {"glare": 0}}})
    b, r = blue[60:120, 130:190].reshape(-1, 3).mean(axis=0), red[60:120, 130:190].reshape(-1, 3).mean(axis=0)
    assert b[2] > b[0] + 20 and r[0] > 2 * r[2]
    # a far sun in the sky: a glare where the sun is, spikes, and a world in front takes it away
    view = {"from": [0, 0, 6], "to": [0, 0, 0], "fov": 40}
    (glare, _), _, made = draw({"star": {"what": "sun", "options": {"direction": [0, 0, -1], "flare": 0}}, **view})
    assert made["seen"]["fraction"] == [1, 1, 1] and 0.9 < made["seen"]["pixels"] < 1.4
    g = glare.mean(axis=-1)
    assert g[90, 160] > 250 and g[84:96, 154:166].mean() > 120 and g[90, 200] < 60 and g[:20, :20].max() < 8
    ring = [g[90 - int(round(24 * np.sin(np.radians(a)))), 160 + int(round(24 * np.cos(np.radians(a))))] for a in (15, 45, 75, 105, 135, 165)]
    assert min(ring[0::2]) > max(ring[1::2]) + 3                                                  # six spikes: at 15, 75 and 135 degrees and across, none between
    (covered, _), _, made = draw({"star": {"what": "sun", "options": {"direction": [0, 0, -1]}}, "bodies": [{"what": "moon"}], "sun": [0, 0, -1], "light": {}, **view})
    assert max(made["seen"]["fraction"]) == 0 and covered.max() < 10                              # behind the moon: no glare, no ghosts, a dark frame
    (edge, _), _, made = draw({"star": {"what": "sun", "options": {"direction": [0.1668, 0, -1]}}, "bodies": [{"what": "moon"}], "light": {}, **view})
    assert 0.2 < made["seen"]["fraction"][0] < 0.8 and made["seen"]["offset"][0] > 0.15           # half past the limb: half the light, its middle outward
    assert edge.mean(axis=-1)[80:100, 150:230].max() > 200 and edge.sum() < 0.8 * glare.sum()
    # planet-shine: the world behind the camera lights the moon's night side; without it the night is black
    pair = {"bodies": [{"what": "moon"}, {"what": "earth", "at": [-60, 20, 200], "radius": 3.67}], "sun": [0.8, 0.1, -1], "from": [0, 0, 5.6], "fov": 26}
    (shine, _), _, made = draw({**pair, "light": {}})
    (none, _), _, _ = draw({**pair, "light": {"shine": 0}})
    night = (slice(70, 110), slice(120, 160))
    assert shine[night].mean() > 5 and none[night].mean() < 1.5 and 0.03 < made["state"]["bodies"][0][1] < 0.08
    assert np.array_equal(shine[60:120, 215:225], none[60:120, 215:225]) or np.abs(shine[60:120, 215:225] - none[60:120, 215:225]).mean() < 6   # the sunlit crescent is the same
    # an eclipse: the moon's shadow darkens a patch of the day side, and only with the option
    ecl = {"bodies": [{"what": "earth", "options": {"spin": 0}}, {"what": "moon", "at": [0.3, 0.2, 58], "radius": 0.2725}], "sun": [0, 0, 1], "from": [0, 0, 5]}
    (shadow, _), _, _ = draw({**ecl, "light": {"eclipses": True}})
    (plain, _), _, _ = draw({**ecl, "light": {}})
    spot = (slice(90 - 24, 90 - 4), slice(160 + 10, 160 + 30))                                    # the shadow falls right of and above the middle (y is up in the scene)
    assert shadow[spot].mean() < 0.4 * plain[spot].mean() and np.abs(shadow[100:140, 100:140] - plain[100:140, 100:140]).mean() < 3
    # exposure: the film convention keeps the stars beside a day side, an honest exposure for the day side has none
    world = {"bodies": [{"what": "earth", "at": [1.6, 0, 0]}], "sun": [1, 0.3, 0.6], "sky": True, "from": [0, 0, 7], "fov": 40}
    (film, _), _, _ = draw({**world, "light": {}})
    (honest, _), _, made = draw({**world, "light": {"exposure": "camera", "ev": 0}})
    stars = (slice(0, 180), slice(0, 110))
    assert film[stars].max() > 60 and honest[stars].max() < 6 and made["state"]["ev"] == 0
    assert np.abs(film[60:120, 200:260] - honest[60:120, 200:260]).mean() < 3                      # the day side is the same picture
    (night_sky, _), _, made = draw({**world, "sun": [0.05, 0, -1], "light": {"exposure": "auto"}})
    assert made["state"]["ev"] > 8                                                                  # nearly nothing lit in the frame: the exposure opens
    # the Sun of ctx.orbits through vidgen/space-scale: placed, as large as the data says, its glare drawn over the night side of the Earth
    settings = od.OrbitData.model_validate({"central": "sun", "date": "2026-06-19", "bodies": [{"preset": "earth"}], "speedup": 1})
    data = json.loads(json.dumps(od.make_orbit_data(settings, 10, 2, 2)))
    offset = _behind_the_earth(data)
    (placed, _), _, made = draw({"orbit": {"offset": offset}, "bodies": [{"what": "Earth"}], "star": {"what": "sun", "options": {"flare": 0}}, "light": {}, "fov": 40}, data)
    assert abs(made["scale"] - 6.957e8) < 1e6 and made["slices"] == 2 and 0.8 < made["seen"]["pixels"] < 1.4
    assert 0 < made["seen"]["covered"] < 1 and made["seen"]["fraction"][0] > made["seen"]["fraction"][2]     # through the Earth's air: red
    p = placed.mean(axis=-1)
    y, x = np.unravel_index(p.argmax(), p.shape)
    assert p.max() > 200 and abs(x - 160) < 12 and abs(y - 90) < 12                                    # the glare sits where the camera looks: at the Sun
    assert p[min(y + 10, 179), x] > 12                                                                 # ... and lies over the dark ground under it


def _behind_the_earth(data: dict) -> list[float]:
    """A camera offset (m, the data's axes) 1.3 Earth radii from the Earth's middle, on its night side, from where the Sun's
    middle stands 0.1 degrees over the limb."""
    import base64

    def first(body: dict) -> np.ndarray:
        return np.frombuffer(base64.b64decode(body["position"]), dtype=np.float64)[:3]

    by = {b["name"]: b for b in data["bodies"]}
    to_sun = first(by["Sun"]) - first(by["Earth"])
    s = to_sun / np.linalg.norm(to_sun)
    side = np.cross(s, [0.0, 0.0, 1.0])
    side /= np.linalg.norm(side)
    radius, r = by["Earth"]["radius"], 1.3
    angle = np.arcsin(1 / r) + np.radians(0.1)
    return list((-np.cos(angle) * s + np.sin(angle) * side) * radius * r)
