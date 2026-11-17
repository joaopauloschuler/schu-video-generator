"""Planets, moons and rings, ``vidgen/space-bodies`` (Step 371, DESIGN.md §122.7): the module is
served by its import name and imports only ``three`` and ``vidgen/music-time``; its parts are
registered; in Node (when it is installed): every ready-made world's options resolve, a wrong
name gets a did-you-mean, palettes, air and rings are checked, a seed gives the same bands, rings
and placed things every time; in Chromium (``slow``): a body is a round disc of the right size
with a day and a night side, the same frame twice, air glows outside the limb and an airless body
does not, rings are lit and shadowed, a body smaller than a pixel is a steady spot holding the
disc's light, and a body of ``ctx.orbits`` is placed, sized and lit through ``vidgen/space-scale``."""

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
MODULE = MODULES / "space-bodies.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
TYPES = ["ocean", "rocky", "icy", "desert", "lava", "gas", "ice-giant"]
WORLDS = ["mercury", "venus", "earth", "moon", "mars", "jupiter", "saturn", "uranus", "neptune", "io", "europa", "ganymede", "callisto", "titan",
          "ember", "boreas", "ochre", "tempest", "verdant", "cinder", "azure"]
PART_NAMES = ({f"body-{t}" for t in TYPES} | {f"world-{w}" for w in WORLDS}
              | {"rings-broad", "rings-narrow", "rings-far-side", "body-crescent", "body-limb"})


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-bodies"] == "space-bodies.js"
    assert IMPORT_MAP["imports"]["vidgen/space-bodies"] == "/__vidgen__/modules/space-bodies.js"
    assert vidgen_file("modules/space-bodies.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-bodies.js"])["__vidgen__/modules/space-bodies.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/music-time"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-bodies" not in engine_id()


def test_the_parts_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-bodies.js"}
    assert set(found) == PART_NAMES
    assert all(p.module == "vidgen/space-bodies" and p.kind == "body" for p in found.values())
    assert 'planet(renderer, "saturn")' in found["world-saturn"].use and "{space}" in found["world-saturn"].use and "{space}" not in found["world-ember"].use
    assert "Math.random" not in (P.PARTS_DIR / "space-bodies.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``B`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "space-bodies")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as B from 'vidgen/space-bodies';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_worlds_types_and_options(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push(B.TYPES, Object.keys(B.PRESETS), B.QUALITIES, B.RING_STYLES);
out.push(Object.keys(B.PRESETS).map((k) => { const o = B.resolveOptions(k); return [o.name, o.type, o.seed, !!o.air, !!o.rings, o.tilt]; }));
out.push(B.TYPES.map((t) => B.PALETTES[t].every((p) => B.resolveOptions({type: t, palette: p}).type === t)));
out.push([err(() => B.resolveOptions("satrun")), err(() => B.resolveOptions({type: "gass"})), err(() => B.resolveOptions("earth", {cloud: 1})),
  err(() => B.resolveOptions({type: "rocky", palette: "mon"})), err(() => B.resolveOptions("earth", {air: "erth"})), err(() => B.resolveOptions("earth", {air: {hight: 1}})),
  err(() => B.resolveOptions("saturn", {rings: {iner: 1}})), err(() => B.resolveOptions("saturn", {rings: {inner: 2, outer: 1.5}})), err(() => B.resolveOptions("earth", {spin: "fast"})),
  err(() => B.resolveOptions("earth", {size: 500})), err(() => B.resolveOptions({type: "gas", clouds: 1})), err(() => B.resolveOptions("moon", {quality: "best"}))]);
const e = B.resolveOptions("Earth", {clouds: 0.8, space: 1, body: "x"}), m = B.resolveOptions("moon"), s = B.resolveOptions("saturn", {rings: {gaps: 3}}), n = B.resolveOptions("earth", {air: false, rings: true});
out.push([e.clouds, e.land, "space" in e, m.air, s.rings.gaps, s.rings.inner, s.rings.style, s.oblateness, n.air, n.rings.style, n.rings.seed]);
const thick = B.resolveOptions("mars", {air: {density: 2}}), mars = B.resolveOptions("mars");
out.push([thick.air.haze[0] / mars.air.haze[0], thick.air.height === mars.air.height, B.resolveOptions("titan").air.height > 5 * B.resolveOptions("earth").air.height]);
out.push([B.sizeFor(180), B.sizeFor(720), B.sizeFor(1080), B.AIR_STEPS, B.linearColor("c", 0xffffff), B.linearColor("c", [0.2, 0.3, 0.4])]);
""")
    types, presets, qualities, styles, worlds, palettes, errors, merged, air, misc = out
    assert sorted(types) == sorted(TYPES) and presets == WORLDS and qualities == ["fast", "standard", "fine"] and styles == ["broad", "narrow"]
    by = {w[0]: w for w in worlds}
    assert len(by) == len(WORLDS) and len({w[2] for w in worlds}) == len(WORLDS)                  # each world its own seed
    assert by["earth"][1] == "ocean" and by["moon"][1] == "rocky" and by["jupiter"][1] == "gas" and by["neptune"][1] == "ice-giant" and by["europa"][1] == "icy"
    assert {n for n, w in by.items() if w[4]} == {"saturn", "uranus", "boreas", "tempest", "azure"}                      # the ringed ones
    assert not by["moon"][3] and not by["mercury"][3] and not by["europa"][3] and by["earth"][3] and by["mars"][3] and by["titan"][3]   # air where there is air
    assert abs(by["earth"][5] - 23.44) < 0.01 and by["uranus"][5] > 90
    assert all(palettes)
    wrong_world, wrong_type, wrong_key, wrong_palette, wrong_air, wrong_air_key, wrong_ring, bad_ring, bad_spin, bad_size, not_this_type, bad_quality = errors
    assert 'did you mean "saturn"' in wrong_world and "mercury, venus, earth" in wrong_world
    assert 'did you mean "gas"' in wrong_type and 'did you mean "clouds"' in wrong_key and 'did you mean "moon"' in wrong_palette
    assert 'did you mean "earth"' in wrong_air and 'did you mean "height"' in wrong_air_key and 'did you mean "inner"' in wrong_ring
    assert "rings.outer" in bad_ring and "seconds of film" in bad_spin and "512" in bad_size and '"clouds"' in not_this_type and '"fast"' in bad_quality
    assert merged == [0.8, 0.3, False, None, 3, 1.24, "broad", 0.098, None, "broad", 13]
    assert abs(air[0] - 2) < 1e-9 and air[1] is True and air[2] is True
    assert misc[:3] == [256, 512, 1024] and misc[3] == {"fast": 2, "standard": 4, "fine": 8}
    assert np.allclose(misc[4], [1, 1, 1]) and misc[5] == [0.2, 0.3, 0.4]


def test_a_seed_is_a_world(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const j = B.resolveOptions("jupiter"), pal = j.palette;
const zones = pal.zones.map((c) => B.linearColor("c", c)), belts = pal.belts.map((c) => B.linearColor("c", c));
const a = B.bandRamp(5, {bands: 13, zones, belts}), b = B.bandRamp(5, {bands: 13, zones, belts}), c = B.bandRamp(6, {bands: 13, zones, belts}), flat = B.bandRamp(5, {bands: 13, contrast: 0, zones, belts, n: 64});
const luma = (x) => x[0] + x[1] + x[2];
let turns = 0; for (let i = 2; i < a.length - 2; i++) { const d0 = luma(a[i]) - luma(a[i - 2]), d1 = luma(a[i + 2]) - luma(a[i]); if (Math.abs(d0) > 0.02 && Math.abs(d1) > 0.02 && d0 * d1 < 0) turns++; }
out.push([a.length, a[0].length, JSON.stringify(a) === JSON.stringify(b), JSON.stringify(a) === JSON.stringify(c), turns, Math.max(...a.map((x) => x[3])), Math.min(...a.map((x) => x[3])),
  Math.max(...flat.map(luma)) - Math.min(...flat.map(luma))]);
const r = B.ringProfile(3), r2 = B.ringProfile(3), r3 = B.ringProfile(4), thin = B.ringProfile(3, {style: "narrow", gaps: 5}), faint = B.ringProfile(3, {opacity: 0.5});
const tau = (p) => p.map((x) => x[3]), empty = (p) => tau(p).filter((x) => x < 0.02).length / p.length;
out.push([r.length, JSON.stringify(r) === JSON.stringify(r2), JSON.stringify(r) === JSON.stringify(r3), r[0][3], r[r.length - 1][3], Math.max(...tau(r)), empty(r), empty(thin), Math.max(...tau(thin)),
  tau(faint)[500] / tau(r)[500]]);
const i1 = B.bakeInputs(B.resolveOptions("moon")), i2 = B.bakeInputs(B.resolveOptions("moon")), i3 = B.bakeInputs(B.resolveOptions("moon", {seed: 99}));
out.push([JSON.stringify(i1) === JSON.stringify(i2), JSON.stringify(i1) === JSON.stringify(i3), i1.spots.length, i1.numbers.length, i1.colors.length, i1.ramp === null, i1.bump,
  i1.spots.every((s) => Math.abs(Math.hypot(s[0], s[1], s[2]) - 1) < 1e-9), B.bakeInputs(j).ramp.length, B.bakeInputs(j).bump]);
out.push(Object.keys(B.PRESETS).map((k) => { const i = B.bakeInputs(B.resolveOptions(k)); return i.numbers.every(Number.isFinite) && i.colors.flat().every((x) => x >= 0 && x <= 1) && i.spots.flat().every(Number.isFinite); }));
out.push([B.levelFor(0.5, 1), B.levelFor(0.1587, 1), B.levelFor(0.3, 0.2) > 0, B.phaseLight(0), B.phaseLight(Math.PI / 2), B.phaseLight(Math.PI), B.spotSigma(0.1), B.spotSigma(2), B.pointShare(3), B.pointShare(2), B.pointShare(1),
  B.onGlobe(90, 0), B.onGlobe(0, 0), B.onGlobe(0, 90)]);
""")
    bands, rings, inputs, finite, numbers = out
    assert bands[:4] == [512, 4, True, False] and bands[4] >= 8                                  # many belts and zones, the same for a seed
    assert 0.9 < bands[5] <= 1.0 and bands[6] >= 0 and bands[7] < 1e-9                             # contrast 0: one colour
    assert rings[:3] == [1024, True, False] and rings[3] < 0.01 and rings[4] < 0.01              # the edges fade out
    assert 1.0 < rings[5] <= 4.0 and 0.005 < rings[6] < 0.3 and rings[7] > 0.7 and rings[8] > 0.3  # gaps in a broad sheet; narrow rings are mostly gaps
    assert abs(rings[9] - 0.5) < 1e-6
    assert inputs[:2] == [True, False] and inputs[2:6] == [32, 24, 12, True] and inputs[6] == 1 and inputs[7] is True and inputs[8] == 512 and inputs[9] == 0
    assert all(finite)
    assert abs(numbers[0]) < 1e-9 and abs(numbers[1] - 1.0) < 0.02 and numbers[2] is True
    assert abs(numbers[3] - 1) < 1e-12 and abs(numbers[4] - 1 / np.pi) < 1e-12 and abs(numbers[5]) < 1e-12   # a Lambert sphere's phases
    assert numbers[6] == 0.62 and abs(numbers[7] - 1.42) < 1e-9 and numbers[8:11] == [0, 0.5, 1]
    assert np.allclose(numbers[11], [0, 1, 0], atol=1e-12) and np.allclose(numbers[12], [1, 0, 0], atol=1e-12) and np.allclose(numbers[13], [0, 0, -1], atol=1e-12)


PAGE = """
import * as THREE from "three";
import {planet} from "vidgen/space-bodies";
import {SpaceView} from "vidgen/space-scale";
let renderer, scene, camera, body, space, c;
export function load(ctx) {
  c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  renderer.debug.onShaderError = (gl, program, vs, fs) => { window.shaderError = (gl.getShaderInfoLog(fs) || "") + (gl.getProgramInfoLog(program) || ""); };
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(30, ctx.width / ctx.height, 0.01, 1000);
  if (c.orbit) {
    space = new SpaceView(ctx, {renderer, scene, camera});
    body = planet(renderer, c.what, {space, size: 128, ...(c.options ?? {})});
  } else {
    body = planet(renderer, c.what, {size: 128, ...(c.options ?? {})});
    body.object.scale.setScalar(c.radius ?? 1); body.object.position.set(...(c.at ?? [0, 0, 0]));
    scene.add(body.object);
  }
  window.made = {problems: body.problems(), turn: body.turnPerFrame(), body: body.body, defines: Object.keys(body.material.defines), rings: !!body.rings};
}
export function frame(t) {
  if (space) { space.update(t, {from: {body: body.body, offset: c.orbit.offset}, to: body.body}); body.update(t); window.made.sun = body.sun.toArray(); window.made.scale = body.object.scale.x; }
  else {
    camera.position.set(...(c.from ?? [0, 0, 5])); camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
    body.update(t, {sun: c.sun ?? [0, 0, 1]});
  }
  renderer.setRenderTarget(null); renderer.render(scene, camera);
  window.made.error = window.shaderError ?? null;
}
"""


@pytest.mark.slow
@pytest.mark.render
def test_bodies_draw_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "bodies.js").write_text(PAGE, encoding="utf-8")

    def draw(data: dict, orbits: dict | None = None) -> tuple[np.ndarray, dict, dict]:
        with WebPage(tmp_path, WebEntry("script", "bodies.js"), scene_id="s", size=(320, 180), fps=10, frames=2, data=data, orbits=orbits) as page:
            frames = [page.frame(n)[..., :3].astype(int) for n in range(2)]
            made = page._page.evaluate("window.made")
            assert made["error"] is None, made["error"]
            assert orbits is not None or np.array_equal(frames[0], frames[1])    # nothing moves by itself (a body of the orbit data turns)
            return frames[0], dict(page.loaded), made

    # a full moon: a round disc of the right size (radius 1 seen from 5 with a 30 degree lens: 69 px), black round it
    moon, loaded, made = draw({"what": "moon"})
    again, _, _ = draw({"what": "moon"})
    other, _, _ = draw({"what": "moon", "options": {"seed": 99}})
    assert np.array_equal(moon, again) and not np.array_equal(moon, other)       # a seed is a world
    assert {"__vidgen__/modules/space-bodies.js", "__vidgen__/modules/music-time.js"} <= set(loaded) and not any("space-sky" in k for k in loaded)
    assert "SHADOWS" in made["defines"] and "AIR" not in made["defines"] and made["problems"] == [] and made["turn"] == 0
    luma = moon.mean(axis=-1)
    lit = luma > 20
    assert abs(lit[90].sum() - 138) <= 4 and abs(lit[:, 160].sum() - 138) <= 4
    assert luma[:8].max() == 0 and luma[:, :60].max() == 0                        # black is black
    assert luma[90, 160] > 60 and luma[60:120, 130:190].std() > 4                # ground with features, not a flat disc
    rim = luma[90, 160 + 60:160 + 67].mean() / luma[90, 150:170].mean()
    assert rim > 0.5                                                              # dusty ground: a full moon has no dark limb
    # the far side is a whole globe too (all six faces of the maps)
    back, _, _ = draw({"what": "moon", "from": [0, 0, -5], "sun": [0, 0, -1]})
    assert abs((back.mean(axis=-1) > 20)[90].sum() - 138) <= 4 and abs((back.mean(axis=-1) > 20)[:, 160].sum() - 138) <= 4
    under, _, _ = draw({"what": "moon", "from": [0, -5, 0.01], "sun": [0, -1, 0]})
    assert abs((under.mean(axis=-1) > 20)[90].sum() - 138) <= 4
    # half lit: the sun to the right
    half, _, _ = draw({"what": "moon", "sun": [1, 0, 0]})
    assert half[60:120, 100:150].mean() < 2 and half[60:120, 175:215].mean() > 25
    # air: a blue line outside the limb of the Earth-like world, nothing outside the moon's
    earth, _, made = draw({"what": "earth"})
    assert {"AIR", "CLOUDS", "GLINT", "GLOW_LIGHTS"} <= set(made["defines"])
    outside = earth[88:93, 160 + 71:160 + 73].reshape(-1, 3).mean(axis=0)
    assert outside[2] > 3 and outside[2] > outside[0] and moon[88:93, 160 + 71:160 + 73].max() == 0
    assert earth[40:140, 110:210].reshape(-1, 3).std(axis=0).mean() > 20          # sea, land and cloud
    # the night side with the sun behind: dark, and the air's lit rim on the sunward limb
    night, _, _ = draw({"what": "earth", "sun": [0.6, 0, -1]})
    assert night[80:100, 150:170].mean() < 12 and night[80:100, 160 + 62:160 + 70].mean() > night[80:100, 160 - 70:160 - 62].mean() + 5
    # rings: lit outside the globe, gone without them, and their shadow darkens a band of the globe
    view = {"from": [0, 2.2, 7.5], "sun": [-0.6, 0.5, 0.6]}
    ringed, _, made = draw({"what": "saturn", **view})
    bare, _, _ = draw({"what": "saturn", "options": {"rings": False}, **view})
    assert made["rings"] is True and "RINGS" in made["defines"]
    sky = bare.max(axis=-1) == 0                                                    # where the bare globe leaves the frame black
    assert (ringed[sky].mean(axis=-1) > 25).sum() > 1500                            # the rings beside the globe, lit
    on_globe = np.abs(ringed - bare).mean(axis=-1)[~sky]
    assert (on_globe > 25).mean() > 0.05 and (on_globe < 3).mean() > 0.3            # the shadow and the near half cross it; the rest is the same globe
    # smaller than a pixel: a steady spot whose light goes with the disc's area, wherever it falls on the pixel grid
    def light(radius: float, at: list[float]) -> float:
        tiny, _, _ = draw({"what": "moon", "radius": radius, "at": at})
        assert tiny[:80].max() == 0 and tiny[100:].max() == 0
        return float((tiny / 255.0).sum())

    px = 2 * np.tan(np.radians(15)) * 5 / 180                                      # one pixel at the body's distance
    small, large, moved = light(0.3 * px, [0, 0, 0]), light(0.6 * px, [0, 0, 0]), light(0.6 * px, [0.37 * px, 0.21 * px, 0])
    assert small > 0.02 and 2.2 < large / small < 6.5 and abs(moved / large - 1) < 0.3

    # a body of ctx.orbits: found by its name, sized by the data, lit from the Sun, turning as the data says
    settings = od.OrbitData.model_validate({"central": "sun", "date": "2026-06-19", "bodies": [{"preset": "earth"}], "speedup": 1})
    data = json.loads(json.dumps(od.make_orbit_data(settings, 10, 2, 2)))
    placed, _, made = draw({"what": "Earth", "orbit": {"offset": [-2.2e7, 1.5e7, 0.9e7]}}, data)
    assert made["body"] == "Earth" and abs(made["scale"] - 6.371e6) < 1e4 and made["problems"] == []
    assert abs(made["turn"] - 360 / 86164.1 / 10) < 1e-5
    assert placed[70:110, 140:180].mean() > 20 and placed[:10, :60].max() == 0
    fast = od.OrbitData.model_validate({"central": "sun", "date": "2026-06-19", "bodies": [{"preset": "earth"}], "speedup": 86400 * 5})
    _, _, made = draw({"what": "Earth", "orbit": {"offset": [-2.2e7, 1.5e7, 0.9e7]}}, json.loads(json.dumps(od.make_orbit_data(fast, 10, 2, 2))))
    assert len(made["problems"]) == 1 and "flicker" in made["problems"][0] and 'spin: "locked"' in made["problems"][0]
    _, _, made = draw({"what": "Earth", "options": {"spin": 30}, "orbit": {"offset": [-2.2e7, 1.5e7, 0.9e7]}}, json.loads(json.dumps(od.make_orbit_data(fast, 10, 2, 2))))
    assert made["problems"] == [] and abs(made["turn"] - 1.2) < 1e-9
