"""The sky from inside an atmosphere, ``vidgen/space-air`` (Step 381, DESIGN.md §123.3): the module is
served by its import name and imports only ``three``, ``vidgen/baked`` and ``vidgen/space-bodies``; its
parts are registered under the kind ``air``; in Node (when it is installed): the airs as numbers (the
same as ``vidgen/space-bodies`` draws from outside), errors with a did-you-mean, the air along a ray
(zenith, horizon, with height), the thin absorbing layer, the sky's light (a blue zenith over a paler,
brighter horizon; a red sunset; a Mars-like sky; thin and thick air), no more light than came in, the
sun after the air, the film exposure and the stars' share, the same numbers twice; in Chromium
(``slow``): the pixels say the same, aerial perspective lightens a far thing, a frame drawn twice is
the same, the picture is the same with the table baked, from the cache and without the cache, and the
baked table agrees with the one made in JavaScript."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.web import baked as B
from vidgen.web import parts as P
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = DATA / "web" / "modules"
MODULE = MODULES / "space-air.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
PART_NAMES = {"air-earth-noon", "air-earth-golden-hour", "air-earth-sunset", "air-earth-twilight", "air-mars-day", "air-mars-sunset", "air-thin", "air-thick",
              "air-from-30-km", "air-haze"}


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-air"] == "space-air.js"
    assert IMPORT_MAP["imports"]["vidgen/space-air"] == "/__vidgen__/modules/space-air.js"
    assert vidgen_file("modules/space-air.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-air.js"])["__vidgen__/modules/space-air.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/baked", "vidgen/space-bodies"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-air" not in engine_id()


def test_the_parts_are_registered_under_their_own_kind() -> None:
    assert "air" in P.KINDS
    found = {p.name: p for p in P.read_parts() if p.file == "space-air.js"}
    assert set(found) == PART_NAMES
    assert all(p.module == "vidgen/space-air" and p.kind == "air" for p in found.values())
    assert 'air(renderer, "earth"' in found["air-earth-noon"].use and "sky.haze(" in found["air-haze"].use and "film exposure" in found["air-earth-twilight"].label
    assert "invented" in found["air-thin"].label and "invented" in found["air-thick"].label          # what is not a real world is said on the sheet
    assert [p.name for p in P.select_parts(P.read_parts(), kind="air") if p.file == "space-air.js"] == [p.name for p in P.read_parts() if p.file == "space-air.js"]      # other files add to the kind (Step 391)
    assert "Math.random" not in (P.PARTS_DIR / "space-air.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``A`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "baked", "space-bodies", "space-air")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as A from 'vidgen/space-air';\nimport * as W from 'vidgen/space-bodies';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const R = Math.PI / 180;\n"
        "// the sky's light at `e` degrees up, `az` degrees round from the sun's bearing, the sun `el` degrees up\n"
        "const sky = (m, el, e, az, h = 0) => { const mus = Math.sin(el * R), mu = Math.sin(e * R);\n"
        "  return A.skyLight(m, h, mu, Math.cos(e * R) * Math.cos(az * R) * Math.cos(el * R) + mu * mus, mus).light; };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_the_airs_are_the_ones_the_bodies_draw_from_outside(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const e = A.airOf("earth"), own = W.resolveOptions("earth").air, m = A.airOf("mars");
out.push([e.rayleigh, e.haze, e.absorb, e.ext, e.height, e.H, e.X0, e.top, e.radius, e.ozone, e.hz, e.name], [own.rayleigh, own.haze, own.absorb, own.height]);
out.push([A.airOf({air: own, radius: 6.371e6}).ext, A.airOf({world: "earth"}).ext, A.airOf("Earth").ext, A.airOf({world: "earth"}).ozone]);       // an air handed over from a body is that air
const dusty = W.resolveOptions("mars", {air: A.PRESETS.mars.air}).air;
out.push([m.ext, dusty.rayleigh.map((x, i) => x + dusty.haze[i] + dusty.absorb[i]), m.forward, m.radius, A.airOf({world: "mars"}).ext, A.airOf({world: "mars"}).forward, m.aureole, m.aureoleForward, e.aureole,
  err(() => A.airOf("mars", {aureole: [2, 0, 0]}))]);
out.push([A.airOf("titan").radius, A.airOf("thin").name, A.airOf("smoke").radius, A.airOf("thick").ext, A.airOf("earth", {radius: 5e6}).H, A.airOf("earth", {ground: 0xffffff}).ground]);
out.push([err(() => A.airOf("erth")), err(() => A.airOf("moon")), err(() => A.airOf("earth", {radus: 1})), err(() => A.airOf({world: "plutto"})), err(() => A.airOf("earth", {forward: 2})),
  err(() => A.airOf(7)), err(() => A.airOf({air: {like: "erth"}})), err(() => A.air(null)), err(() => A.airOf("earth", {radius: 10}))]);
out.push([Object.keys(A.PRESETS), A.EXPOSURES, A.QUALITIES, A.TOP, A.BURN, A.SKY_STOPS, Object.keys(A.RADII).every((w) => W.resolveOptions(w).air !== null),
  Object.keys(W.PRESETS).filter((w) => W.resolveOptions(w).air !== null).every((w) => w in A.RADII)]);
out.push([A.sunDirection(90), A.sunDirection(0, 0), A.sunDirection(0, 90), A.sunDirection(30, 180)]);
// a body of vidgen/space-bodies hands over the air it is drawn with (a stand-in: what airOf reads of one)
const body = (air, name) => ({options: {air, name}, object: {}, setSun() {}});
out.push([A.airOf(body(W.resolveOptions("titan").air, "titan")).ext, A.airOf("titan").ext, A.airOf(body(W.resolveOptions("titan").air, "titan")).radius, A.airOf(body(own, null)).radius, err(() => A.airOf(body(null, "moon")))]);
""")
    earth, own, same, mars, others, errors, names, suns, handed = out
    assert handed[0] == handed[1] and handed[2] == 2.5747e6 and handed[3] == 6.371e6 and "has no air" in handed[4]
    assert earth[0] == own[0] and earth[1] == own[1] and earth[2] == own[2] and earth[4] == own[3] == 0.0014            # the body's own numbers
    assert np.allclose(earth[3], np.sum(own[:3], axis=0)) and abs(earth[5] - 8919.4) < 0.1 and abs(earth[6] - 1 / 0.0014) < 1e-9 and abs(earth[7] - 8 * 8919.4) < 1
    assert earth[8] == 6.371e6 and earth[9] == [0.03, 0.028, 0.004] and abs(earth[10] - 25000 / 8919.4) < 1e-6 and earth[11] == "earth"
    assert same[0] == same[1] == same[2] == earth[3] and same[3] == [0, 0, 0]                                             # the layer belongs to the ready-made air, not to the world
    assert np.allclose(mars[0], mars[1]) and mars[2] == [0.36, 0.42, 0.55] and mars[3] == 3.3895e6                        # the dusty air, stated for a body too
    assert mars[6] == [0.02, 0.06, 0.35] and mars[7] == 0.93 and mars[8] == [0, 0, 0] and "0 to 1" in mars[9]              # the dust's narrow lobe, mostly blue; none in the Earth-like air
    assert max(mars[4]) < 0.5 * min(mars[0]) and len(set(mars[5])) == 1                                                   # the world's own, clearer air stays reachable
    assert others[0] == 2.5747e6 and others[1] == "thin" and others[2] == 6.371e6 and others[3][2] > 4 * earth[3][2] and abs(others[4] - 7000) < 1e-6 and others[5] == [1, 1, 1]
    wrong, airless, key, world, forward, kind, like, renderer, radius = errors
    assert 'did you mean "earth"' in wrong and "ready-made: earth, mars, thin, thick" in wrong and "titan" in wrong and "smoke" in wrong
    assert 'the world "moon" has no air' in airless and "earth" in airless and 'did you mean "radius"' in key and "plutto" in world
    assert "0 to 0.95" in forward and "a name or an options object" in kind and 'did you mean "earth"' in like and "THREE.WebGLRenderer" in renderer and "1e" in radius.lower() or "10000" in radius
    assert names == [["earth", "mars", "thin", "thick"], ["film", "camera", "auto"], ["fast", "standard", "fine"], 8, 32, 20, True, True]
    assert np.allclose(suns, [[0, 1, 0], [0, 0, -1], [1, 0, 0], [0, 0.5, np.sqrt(0.75)]], atol=1e-12)


def test_the_air_along_a_ray(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const e = A.airOf({world: "earth"}), X0 = e.X0, withLayer = A.airOf("earth");
out.push([A.column(X0, 0, 1), A.column(X0, 0, 0), A.column(X0, 1, 1) / A.column(X0, 0, 1), A.column(X0, 0, -1e-9) / A.column(X0, 0, 1e-9), A.column(X0, 3, -0.05), A.column(X0, 8, 1)]);
const run = []; for (let i = 0; i <= 100; i++) run.push(A.column(X0, 0.3, i / 100)); out.push(run);
out.push([A.opticalDepth(e, 0, 1), A.transmittance(e, 0, 1), A.transmittance(e, 0, 0), A.transmittance(e, 20000, 1), A.transmittance(e, 1e6, 1), A.opticalDepth(e, 5000, 0.3), A.opticalDepth(e, 5000, 0.3)]);
out.push([A.crossings(X0, 2.8, 0, 1), A.crossings(X0, 2.8, 5, 1), A.crossings(X0, 2.8, 5, -1), A.crossings(X0, 2.8, 1, 0), A.crossings(X0, 2.8, 5, -0.2), A.crossings(X0, 2.8, 2.79, 0), A.crossings(X0, 2.8, 5, -0.05),
  A.opticalDepth(withLayer, 0, 1).map((x, i) => x - A.opticalDepth(e, 0, 1)[i]), A.opticalDepth(withLayer, 40000, 1).map((x, i) => x - A.opticalDepth(e, 40000, 1)[i])]);
out.push([A.phaseRayleigh(1), A.phaseRayleigh(0), A.phaseHaze(0, 0.3), A.phaseHaze(0.7, 1) / A.phaseHaze(0.7, -1)]);
// the phase functions keep the light: their mean over all directions is a quarter (pi times 1 / 4 pi)
let r = 0, h = 0; const n = 20000; for (let i = 0; i < n; i++) { const c = -1 + 2 * (i + 0.5) / n; r += A.phaseRayleigh(c) / n; h += A.phaseHaze(0.76, c) / n; } out.push([r, h]);
""")
    columns, run, depth, layer, phase, kept = out
    assert 0.96 < columns[0] <= 1.0 and 33 < columns[1] < 40 and abs(columns[2] - np.exp(-1)) < 0.01           # one column overhead; 38 on the Earth's horizon; a scale height up: 1 / e
    assert abs(columns[3] - 1) < 1e-6 and columns[4] > 3 * 2.0 and columns[5] < 4e-4                            # no step at the level; under the horizon more than the tangent path
    assert np.diff(run).max() < 0 and run[0] > 20 * run[-1]                                                     # less air the steeper the ray
    zenith, t_zenith, t_horizon, t_high, t_space, a, b = depth
    assert np.allclose(zenith, np.array([0.088, 0.164, 0.313]) * columns[0], atol=1e-9)                         # the zenith's optical depth is the stated one (times the closed form's 0.97)
    assert 3 < zenith[2] / zenith[0] < 6 and 0.71 < t_zenith[2] < 0.76 and 0.90 < t_zenith[0] < 0.93            # blue is scattered four times as much as red: the sky is blue
    assert t_horizon[0] > 10 * t_horizon[1] > 100 * t_horizon[2] and t_high[2] > 0.96 and min(t_space) > 0.9999 and a == b
    assert abs(layer[0] - 1) < 0.01 and layer[1] == 0 and abs(layer[2] - 2) < 0.02 and 5 < layer[3] <= 16 and 8 < layer[4] < 14 and layer[3] < layer[5] <= 41.0 and layer[6] == 0   # aslant through it; twice from above; past it
    assert np.allclose(layer[7], [0.03, 0.028, 0.004], rtol=0.02) and max(np.abs(layer[8])) < 1e-12              # the layer's own depth, under it only
    assert abs(phase[0] - 0.375) < 1e-12 and abs(phase[1] - 0.1875) < 1e-12 and abs(phase[2] - 0.25) < 1e-12 and phase[3] > 100
    assert abs(kept[0] - 0.25) < 1e-6 and abs(kept[1] - 0.25) < 1e-4


def test_the_sky_by_day_at_sunset_and_on_other_worlds(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const e = A.airOf("earth"), m = A.airOf("mars"), thin = A.airOf("thin"), thick = A.airOf("thick");
out.push([sky(e, 50, 90, 0), sky(e, 50, 3, 120), sky(e, 0.5, 3, 0), sky(e, 0.5, 60, 0), sky(e, 50, 3, 0)]);
out.push([sky(m, 40, 90, 0), sky(m, 40, 20, 120), sky(m, 2, 4, 0), sky(m, 2, 20, 100)]);
out.push([sky(thin, 50, 90, 0), sky(thick, 50, 90, 0), sky(e, 50, 90, 0, 30000), sky(e, 50, 90, 0, 80000), A.skyLight(e, 80000, -1, -Math.sin(50 * R), Math.sin(50 * R)).hit, A.skyLight(e, 2, -0.5, 0, 0.5).hit]);
// twilight: the sky dims by orders of magnitude, the zenith stays bluer than the arch
out.push([-1, -3, -5, -7].map((el) => [sky(e, el, 90, 0), sky(e, el, 3, 0)]));
// from sunset to night the zenith fades without a cliff: two degrees further never cost more than a factor of 30
out.push([4, 2, 0, -2, -4, -6, -8, -10, -12, -14, -16, -18].map((el) => sky(e, el, 90, 0)));
// no more light than came in: the sun after the air on a level ground plus the sky's light on it, over the sunlight on it without air
out.push([70, 40, 15, 5].map((el) => { const mus = Math.sin(el * R), s = A.sunlightAt(e, 0, mus), a = A.skyAmbient(e, 0, mus); return s.map((x, i) => (x * mus + a[i]) / mus); }));
out.push([40, 5].map((el) => { const mus = Math.sin(el * R), s = A.sunlightAt(thick, 0, mus), a = A.skyAmbient(thick, 0, mus); return s.map((x, i) => (x * mus + a[i]) / mus); }));
out.push([A.sunlightAt(e, 0, Math.sin(60 * R)), A.sunlightAt(e, 0, Math.sin(2 * R)), A.sunlightAt(e, 0, Math.sin(-1 * R)), A.sunlightAt(e, 0, 0), A.sunlightAt(e, 10000, Math.sin(-1 * R)), A.sunlightAt(e, 2e5, 0.5)]);
// the same numbers twice, and the tables
const p1 = A.psiTable(e), p2 = A.psiTable(e), t = A.ambientTable(e);
out.push([JSON.stringify(sky(e, 12, 30, 40)) === JSON.stringify(sky(e, 12, 30, 40)), p1.data.every((x, i) => x === p2.data[i]), p1.data.every((x) => x >= 0 && x < 1), p1.at(0, 1), p1.at(0, -0.3), p1.at(7.9, 1),
  t.n, t.at(1), t.zenithAt(1) / t.zenithAt(0), t.archAt(0) / t.zenithAt(0), A.skyLight(e, 0, 1, 0.5, 0.5, {scattered: false}).light.map((x, i) => x / A.skyLight(e, 0, 1, 0.5, 0.5).light[i])]);
""")
    earth, mars, others, twilight, fade, energy, thick_energy, sun, same = out
    zenith, horizon, sunset, over_sunset, towards = (np.array(x) for x in earth)
    luma = lambda c: float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])  # noqa: E731
    assert zenith[2] > 2.5 * zenith[0] and zenith[2] > zenith[1] > zenith[0]                                      # a blue zenith
    assert luma(horizon) > 2 * luma(zenith) and horizon[2] / horizon[0] < 0.75 * zenith[2] / zenith[0]            # the horizon is brighter and paler
    assert sunset[0] > 2 * sunset[1] > 6 * sunset[2] and sunset[0] / sunset[2] > 10 * towards[0] / towards[2]     # red, then orange: no green over red; much redder than by day
    assert over_sunset[2] > over_sunset[0] and luma(over_sunset) < 0.1 * luma(sunset)                             # the dusk above stays blue
    day, side, glow, away = (np.array(x) for x in mars)
    assert day[0] > day[1] > day[2] and day[0] > 2 * day[2] and side[0] > side[1] > side[2]                       # butterscotch by day
    assert glow[2] > glow[1] > glow[0] and away[0] > away[1] > away[2] and luma(glow) > 10 * luma(away)           # a blue glow round the setting sun in a tawny sky
    assert luma(others[0]) < 0.5 * luma(zenith) and luma(others[1]) > 3 * luma(zenith)                            # thin air: a dark sky; thick: a bright one
    assert luma(others[2]) < 0.1 * luma(zenith) and others[3] == [0, 0, 0] and others[4] is True and others[5] is True   # black above the air; down is the ground
    levels = [luma(z) for z, _ in twilight]
    assert levels[0] > 2 * levels[1] > 4 * levels[2] > 8 * levels[3] > 0 and all(z[2] / z[0] > 1.5 * a[2] / a[0] for z, a in twilight)
    steps = [luma(a) / luma(b) for a, b in zip(fade, fade[1:])]
    assert all(1 < r < 30 for r in steps) and 1e-7 < luma(fade[8]) / luma(fade[2]) < 1e-3 and fade[8][2] > 1.5 * fade[8][0]   # at -12 degrees a ten-thousandth of sunset's, and blue
    assert all(luma(a) > 20 * luma(z) for z, a in twilight[1:])                                                   # the arch: the light is low over where the sun set
    assert all(0.45 < x < 1.02 for row in energy for x in row) and all(0.2 < x < 1.02 for row in thick_energy for x in row)   # air gives no light of its own
    assert energy[0][0] > energy[0][2] and energy[3][0] > energy[3][2]                                            # blue is thrown back to space more than red
    high, low, sinking, half, from_height, space = sun
    assert high[0] > high[1] > high[2] > 0.6 and low[0] > 3 * low[2] and low[0] < 0.5 and sinking == [0, 0, 0]    # reddened towards the horizon, gone under it
    assert 0.3 < half[0] / A_HORIZON < 0.7 and from_height[0] > 0.1 and min(space) > 0.999                        # half the disc on the horizon; from 10 km it is still up
    assert same[0] is True and same[1] is True and same[2] is True and same[3][2] > same[3][0] > 0.01 and max(same[4]) < 1e-6 and same[5][2] > 0
    assert same[6] == 64 and same[7][2] > same[7][0] > 0.02 and same[8] > 5 and same[9] > 20 and all(0.55 < x < 0.95 for x in same[10])   # a fifth to a third of the zenith's light has been scattered twice


#: The red sunlight left on the Earth-like horizon: exp(-0.088 * 36.6), the whole disc up.
A_HORIZON = float(np.exp(-0.088 * 36.6))


def test_the_film_exposure_and_the_stars(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const run = []; for (let i = 0; i <= 120; i++) run.push(A.filmExposure(Math.pow(2, -i / 4), 1)); out.push(run);
out.push([A.filmExposure(2, 1), A.filmExposure(1, 1), A.filmExposure(1e-3, 1, 9), A.filmExposure(1e-3, 1, 2), A.filmExposure(1e-3, 1, 5) / A.filmExposure(1e-3, 1, 0), A.filmExposure(1e-30, 1), A.FILM_STOPS,
  A.filmExposure(1e-4, 1, 0, 0.02), Math.log2(A.DUSK_KNEE * (A.ARCH_WHITE / A.DUSK_KNEE) ** 2 / 0.02), A.filmExposure(1e-4, 1, 0, 100), A.filmExposure(1, 1, 0, 8), Math.log2(A.ARCH_WHITE / 8),
  A.filmExposure(1, 1, 0, 1e9), A.duskCurve(0), A.duskCurve(2), A.duskCurve(9), A.DUSK_CURVE]);
out.push([A.filmStars(0), A.filmStars(5), A.filmStars(8), A.filmStars(11), A.filmStars(14), A.filmStars(0, 0.001), A.filmStars(0, 0.05), A.filmStars(8, 0.001), A.filmStars(0, 0.001, 0.5), A.filmStars(14, 0.001, 0.5), A.DAY_STARS]);
// through an evening on the Earth-like ground: the exposure and what it leaves of the zenith and of the arch
const e = A.airOf("earth"), t = A.ambientTable(e), day = t.zenithAt(Math.sin(25 * R));
out.push([30, 10, 0, -2, -4, -6, -8, -12, -20].map((el) => { const mus = Math.sin(el * R), ev = A.filmExposure(t.zenithAt(mus), day, 0, t.archAt(mus)); const arch = t.archAt(mus) * 2 ** ev;
  return [ev, t.zenithAt(mus) * 2 ** ev, A.DUSK_KNEE * Math.pow(Math.max(arch / A.DUSK_KNEE, 1), 1 - A.duskCurve(ev))]; }));
""")
    run, marks, stars, evening = out
    assert run[0] == 0 and np.diff(run).min() >= 0 and np.diff(run).max() < 0.26 and run[-1] == 16                 # opens smoothly, never more than the meter, to the cap
    assert marks[0] == 0 and marks[1] == 0 and marks[2] == 0 and marks[3] == marks[4] * 0 + marks[3] and 0 < marks[4] < 1 and marks[5] == 16 and marks[6] == 16
    assert abs(marks[7] - marks[8]) < 1e-9 and -1.5 < marks[9] < 0                                                  # never so far that the arch burns out (the dusk curve allowed for)
    assert abs(marks[10] - marks[11]) < 1e-9 and marks[12] == -3                                                    # a glow brighter than that by itself closes the exposure, three stops at most
    assert marks[13] == 0 and 0 < marks[14] < marks[15] == marks[16] == 0.5                                         # the dusk curve: nothing by day, half the contrast at dusk
    assert stars[0] == 0 and stars[1] == 0 and 0 < stars[2] < 1 and stars[3] == 1 and stars[4] == 1 and stars[5] == 1 and stars[6] == 0 and stars[7] == 1
    assert stars[8] == stars[10] == 0.35 and stars[9] == 1           # over the day side from high up the band of light is dimmed; a dark sky shows all
    stops = [row[0] for row in evening]
    assert stops[0] == 0 and stops[1] < 1.6 and stops == sorted(stops) and 4 < stops[5] < 10 and stops[-1] == 16    # nothing by day; the blue hour lifted; night at the cap
    assert all(row[2] <= 1.6 + 1e-9 for row in evening) and evening[5][1] > 0.004 and evening[-1][1] < 1e-5         # the arch never burns out; the zenith is still seen at -6 degrees; then night
    drawn = [row[1] for row in evening]
    assert drawn[7] > 0.003 and all(a >= b for a, b in zip(drawn, drawn[1:])) and all(a < 3.5 * b for a, b in zip(drawn[:7], drawn[1:8]))   # still a glow at -12; down to there it fades by small steps



def test_the_earths_shadow_rises_opposite_the_sun_at_dusk(tmp_path: Path) -> None:
    # Step 403: the scattering model's own sums give the dark band and the pink band above it (no table changed for it)
    out = _run_in_node(tmp_path, """
const m = A.airOf("earth"), psi = A.psiTable(m);
for (const el of [0, -2, -4]) out.push([0.5, 2, 4, 6, 9, 12, 16, 20, 30, 45].map((e) => { const mus = Math.sin(el * R), mu = Math.sin(e * R), cosv = -Math.cos(e * R) * Math.cos(el * R) + mu * mus;
  const once = A.skyLight(m, 2, mu, cosv, mus, {scattered: false, steps: 64}).light, all = A.skyLight(m, 2, mu, cosv, mus, {psi, steps: 64}).light; return [once[1], all[1], all[0] / all[2]]; }));
""")
    for el, row in zip((0, -2, -4), out):
        once = [r[0] for r in row]
        top = int(np.argmax(once))
        assert once[0] < 0.1 * once[top] and 0 < top < len(row) - 1                     # the sun's light gone from the air low opposite the sun; brightest a band higher up
        assert row[0][1] > 0                                                             # light scattered more often fills the shadow: dark, not black
        if el < 0:
            shade = [r[2] for r, o in zip(row, once) if o < 0.1 * once[top]]
            band = max(r[2] for r, o in zip(row, once) if o >= 0.1 * once[top])
            assert band > 1.3 * min(shade) and band > row[-1][2]                         # over the shadow a band redder than the shadow and than the sky above
    assert [int(np.argmax([r[0] for r in row])) for row in out] == sorted(int(np.argmax([r[0] for r in row])) for row in out)   # the shadow rises as the sun sinks


def test_the_shadows_in_the_air_in_node(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const m = A.airOf("earth"), R6 = m.radius;
// the stretch where casters reach: under their top from the camera, from where the ray comes under it, nothing over it looking up
out.push([A.shadeSpan(R6, 10, 0, 3000, 2e5), A.shadeSpan(R6, 10, 1, 3000, 2e5), A.shadeSpan(R6, 8000, 1, 3000, 2e5), A.shadeSpan(R6, 8000, -0.5, 3000, 2e5), A.shadeSpan(R6, 10, 0.1, 3000, 1000), A.shadeSpan(R6, 10, -0.2, 3000, 2e5, 50)]);
out.push([A.shadeShareAt([0.2, 0.6], 0), A.shadeShareAt([0.2, 0.6], 0.0625), A.shadeShareAt([0.2, 0.6], 0.25), A.shadeShareAt([0.2, 0.6], 1), A.shadeShareAt([0.2, 0.6], 2)]);
// one ray towards a low sun, under a deck's top at 2 km: nothing casting, all in shadow, shadow beyond 5 km only, a cloud's diffuse light
const ray = {height: 30, mu: Math.sin(3 * R), cosv: Math.cos(5 * R), mus: Math.sin(8 * R)}, top = {top: 2000};
const none = A.shadowShares(m, ray, top), all = A.shadowShares(m, ray, {...top, sun: () => 0, sky: () => 0}), sunOnly = A.shadowShares(m, ray, {...top, sun: () => 0});
const far = A.shadowShares(m, ray, {...top, sun: (w) => (Math.hypot(...w) > 5000 ? 0 : 1)}), soft = A.shadowShares(m, ray, {...top, sun: () => 0, diffuse: 0.25});
const whole = A.skyLight(m, 30, ray.mu, ray.cosv, ray.mus).light[1];
out.push([none, all, sunOnly, far, soft, A.shadowShares(m, ray, {...top, sun: () => 0}), whole]);
out.push([A.shadowShares(m, {...ray, height: 8000, mu: 0.5}, top), A.SHADOWS]);
out.push([err(() => A.air({isWebGLRenderer: true}, "earth", {shadows: {reech: 1}}))]);
""")
    spans, shares, (none, all_, sun_only, far, soft, again, whole), (over, defaults), errors = out
    level, up, over_top, down, short, ground = spans
    assert level[0] == 0 and 150000 < level[1] < 200000 and up[0] == 0 and up[1] == pytest.approx(2990, rel=1e-3)   # from the sea along the level the top is far; straight up 2,990 m
    assert over_top[1] <= over_top[0] and down[0] == pytest.approx(10000, rel=0.01) and down[1] > down[0]            # from over the top: looking up nothing, looking down from where the ray comes under it
    assert short == [0, 1000] and ground == [0, 50]                                                                 # the reach and the ray's end bound it
    assert shares == [0, pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.6), pytest.approx(0.6)]           # none at the start, half way, all the way
    assert none == [0, 0] and 0 < all_[0] < all_[1] < 1 and sun_only[1] < all_[1] and sun_only == again           # nothing casting: no shadow; more of the stretch, more shadow; deterministic
    assert far[0] < far[1] and far[1] < sun_only[1] and soft[1] < sun_only[1]                                      # a shadow beyond 5 km darkens only the far half; a cloud's diffuse light softens it
    assert whole > 0 and over == [0, 0] and defaults == {"reach": 200000, "share": 0.25, "steps": 24}             # a ray over every caster: nothing
    assert errors[0] is not None and 'did you mean "reach"' in errors[0]

PAGE = """
import * as THREE from "three";
import {air, sunDirection, psiTable, skyLight, PSI_TABLE, TOP} from "vidgen/space-air";
let renderer, scene, camera, c, skies = [], boxes = [];
export function load(ctx) {
  c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  renderer.debug.onShaderError = (gl, program, vs, fs) => { window.shaderError = (gl.getShaderInfoLog(fs) || "") + (gl.getShaderInfoLog(vs) || "") + (gl.getProgramInfoLog(program) || ""); };
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(60, ctx.width / ctx.height, 1, 1e7);
  for (const shot of c.shots) { const sky = air(renderer, shot.what, shot.extra ?? {}); sky.object.visible = false; scene.add(sky.object); skies.push(sky); }
  // two black boxes of the same size in the frame, 600 m and 60 km away: only the air between differs
  const black = skies[0].haze(new THREE.MeshBasicMaterial({color: 0x000000}));
  for (const [x, d] of [[-0.25, 600], [0.25, 60000]]) { const b = new THREE.Mesh(new THREE.BoxGeometry(d * 0.2, d * 0.2, d * 0.2), black); b.position.set(x * d, d * 0.12, -d); b.visible = false; scene.add(b); boxes.push(b); }
  // the baked table against the one made in JavaScript, at the places the JavaScript one holds
  const sky = skies[0], m = sky.model, cpu = psiTable(m, {suns: 16, heights: 8, directions: 8, elevations: 14, steps: 24}), f = new Uint16Array(PSI_TABLE.suns * PSI_TABLE.heights * 4);
  renderer.readRenderTargetPixels(sky.psi, 0, 0, PSI_TABLE.suns, PSI_TABLE.heights, f);
  const at = (x, y, k) => THREE.DataUtils.fromHalfFloat(f[(Math.min(PSI_TABLE.heights - 1, Math.floor(y)) * PSI_TABLE.suns + Math.min(PSI_TABLE.suns - 1, Math.floor(x))) * 4 + k]);
  window.psi = [[0.1, 0.9], [1.5, 0.5], [4, 0.2], [0.5, 0.05], [2, -0.1]].map(([h, mus]) => {
    const x = (mus - PSI_TABLE.sunFrom) / (1 - PSI_TABLE.sunFrom) * PSI_TABLE.suns, y = Math.sqrt(h / TOP) * PSI_TABLE.heights;
    return [[0, 1, 2].map((k) => at(x, y, k)), cpu.at(h, mus)];
  });
  window.states = [];
}
export function frame(t, ctx) {
  const n = Math.round(t * ctx.fps), shot = c.shots[n], sky = skies[n], pitch = (shot.pitch ?? 20) * Math.PI / 180, h = shot.height ?? 2;
  skies.forEach((s, i) => { s.object.visible = i === n; });
  boxes.forEach((b) => { b.visible = !!shot.boxes; });
  camera.position.set(0, h, 0); camera.lookAt(0, h + Math.sin(pitch) * 1000, -Math.cos(pitch) * 1000); camera.updateMatrixWorld();
  sky.update(t, {camera, sun: sunDirection(shot.elevation, shot.azimuth ?? 0)});
  window.states[n] = {...sky.state, sun: sky.light.sun.color.toArray(), sunPower: sky.light.sun.intensity, skyColor: sky.light.sky.color.toArray(), skyPower: sky.light.sky.intensity};
  renderer.setRenderTarget(null); renderer.render(scene, camera);
}
"""
SHOTS = [
    {"what": "earth", "elevation": 50, "azimuth": 120, "pitch": 20},                    # 0 by day, away from the sun
    {"what": "earth", "elevation": 0.5, "azimuth": 0, "pitch": 10},                     # 1 sunset, towards the sun
    {"what": "mars", "elevation": 40, "azimuth": 120, "pitch": 35},                     # 2 a Mars-like day
    {"what": "mars", "elevation": 3, "azimuth": -40, "pitch": 12},                      # 3 a Mars-like sunset, the sun left of the middle
    {"what": "earth", "elevation": 50, "azimuth": 120, "pitch": 20},                    # 4 the first again
    {"what": "earth", "elevation": 50, "azimuth": 120, "pitch": 4, "boxes": True},                  # 5 aerial perspective
    {"what": "earth", "elevation": 50, "azimuth": 120, "pitch": 20, "extra": {"exposure": "camera", "ev": -2}},   # 6 two stops under
    {"what": "earth", "elevation": 30, "azimuth": 120, "pitch": -15, "height": 150000},  # 7 from space: the limb
]


@pytest.mark.slow
@pytest.mark.render
def test_the_sky_draws_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "air.js").write_text(PAGE, encoding="utf-8")
    store = B.BakedStore(tmp_path / "baked", 10**9)

    def draw(baked: B.BakedStore | bool) -> tuple[list[np.ndarray], list, list, list]:
        with WebPage(tmp_path, WebEntry("script", "air.js"), scene_id="s", size=(160, 90), fps=10, frames=len(SHOTS), data={"shots": SHOTS}, baked=baked) as page:
            frames = [page.frame(n)[..., :3].astype(int) for n in range(len(SHOTS))]
            error, psi, states = page._page.evaluate("[window.shaderError ?? null, window.psi, window.states]")
            assert error is None, error
            return frames, psi, states, sorted({(what, name) for what, name, _ in page.baked_log})

    frames, psi, states, log = draw(False)
    day, sunset, mars, mars_sunset, again, boxes, under, limb = frames
    assert log == []
    top, low = day[4:14].mean(axis=(0, 1)), day[66:72].mean(axis=(0, 1))                 # the sky high up and just over the horizon
    assert top[2] > 1.6 * top[0] and top[2] > top[1] > top[0] and low.sum() > 1.3 * top.sum() and low[2] / low[0] < 0.8 * top[2] / top[0]
    ground = day[82:].mean(axis=(0, 1))
    assert ground.sum() < 0.8 * low.sum() and abs(int(day[78, 80].sum()) - int(day[72, 80].sum())) > 30    # a plain ground under a horizon
    glow = sunset[52:58, 60:100].mean(axis=(0, 1))
    assert glow[0] > 1.5 * glow[2] and glow[0] > glow[1] > glow[2] and glow[0] / glow[2] > 2 * low[0] / low[2]    # sunset is redder than noon
    assert sunset[2:8].mean(axis=(0, 1))[2] >= sunset[2:8].mean(axis=(0, 1))[0] - 12                                # the dusk over it is no longer red
    sky_mars = mars[4:40].mean(axis=(0, 1))
    assert sky_mars[0] > sky_mars[1] > sky_mars[2] and sky_mars[0] > 1.4 * sky_mars[2]                              # butterscotch
    near, far = mars_sunset[30:44, 22:34].mean(axis=(0, 1)), mars_sunset[4:16, 140:158].mean(axis=(0, 1))          # round the sun, and far from it
    assert near[2] > near[0] and far[0] > far[2] and near.sum() > far.sum()                                         # a blue glow in a tawny sky
    assert np.array_equal(day, again)                                                                               # a frame is a function of its inputs
    near_box, far_box, behind = boxes[38:44, 57:64].mean(axis=(0, 1)), boxes[38:44, 96:103].mean(axis=(0, 1)), boxes[38:44, 76:84].mean(axis=(0, 1))
    assert near_box.sum() < 40 and far_box.sum() > 150 and far_box[2] > far_box[0] and far_box.sum() < behind.sum()   # the far box has taken most of the sky's colour, not all
    assert under[4:14].mean() < 0.6 * day[4:14].mean()                                                              # a camera two stops under shows it darker
    assert limb[:20].mean() < 3 and limb[60:].mean() > 30                                                           # black space over a lit world
    band = limb[:, 80].astype(float)
    assert band[:, 2].max() > 80 and band[int(band[:, 2].argmax()), 2] > 1.3 * band[int(band[:, 2].argmax()), 0]    # the limb's blue line
    # the baked table agrees with JavaScript's (coarser) one
    for gpu, cpu in psi:
        assert np.allclose(gpu, cpu, rtol=0.25, atol=2e-4), (gpu, cpu)
    s = states[0]
    assert s["ev"] == 0 and s["inside"] is True and abs(s["height"] - 2) < 1e-6 and abs(s["elevation"] - 50) < 1e-6 and s["stars"] == 0
    assert s["sun"][0] >= s["sun"][1] > s["sun"][2] and 0.7 * np.pi < s["sunPower"] < np.pi and s["skyColor"][2] > s["skyColor"][0] and 0.03 * np.pi < s["skyPower"] < 0.4 * np.pi
    assert states[1]["ev"] > 0.5 and states[1]["sun"][0] > 5 * max(states[1]["sun"][2], 1e-9) and states[6]["ev"] == -2 and states[7]["inside"] is False and states[7]["stars"] == 0.35   # high over the day side: the band of light dimmed (DAY_STARS)
    # the same pixels with the table baked and stored, from the cache, and without the cache
    cold, _, _, log = draw(store)
    assert log == [("stored", "space-air/psi")]
    warm, _, _, log = draw(store)
    assert log == [("hit", "space-air/psi")]
    assert all(np.array_equal(a, b) and np.array_equal(a, w) for a, b, w in zip(frames, cold, warm))
