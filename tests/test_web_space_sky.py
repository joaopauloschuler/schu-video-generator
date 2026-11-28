"""The sky of a space scene, ``vidgen/space-sky`` (Step 370): the module and its
star file are served by their import names; the star file is what ``tools/make_star_catalogue.py``
writes (the fixture) and the converter reads the Bright Star Catalogue's fixed-width lines; in
Node (when it is installed): right ascension and declination land in the ecliptic frame of
``ctx.orbits`` (the galactic centre lies behind the Earth in June, among Sagittarius' stars), star
counts and colours, seeded stars, options with a did-you-mean, the cube faces' windows, the
particle galaxy; the parts are registered. In Chromium (``slow``): the sky draws the same frames
twice, the real sky puts Sirius where the camera looks, and the cube map and the environment
are made."""

from __future__ import annotations

import base64
import gzip
import importlib.util
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

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
MODULE = MODULES / "space-sky.js"
STARS = MODULES / "space-sky-stars.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
PART_NAMES = {"space-sky", "space-sky-core", "space-sky-rich", "space-sky-sparse", "space-sky-emission-nebula", "space-sky-reflection-nebula",
              "space-sky-dark-nebula", "space-sky-galaxies", "space-sky-real", "spiral-galaxy", "space-sky-environment"}


def _converter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_star_catalogue", ROOT / "tools" / "make_star_catalogue.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_modules_are_served_by_their_import_names() -> None:
    for name, file in (("vidgen/space-sky", "space-sky.js"), ("vidgen/space-sky-stars", "space-sky-stars.js")):
        assert VIDGEN_MODULES[name] == file
        assert IMPORT_MAP["imports"][name] == f"/__vidgen__/modules/{file}"
        assert vidgen_file(f"modules/{file}") == MODULES / file
        assert len(current_loaded(Path("."), [f"__vidgen__/modules/{file}"])[f"__vidgen__/modules/{file}"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/music-time", "vidgen/space-scale", "vidgen/baked", "vidgen/space-sky-stars"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source
    assert MODULE not in INIT_FILES and "space-sky" not in engine_id()


def test_the_star_file_is_the_converters_fixture() -> None:
    tool = _converter()
    data = tool.read_star_file(STARS)
    assert data["approximate"] is True and "fixture" in data["catalog"] and data["epoch"] == "J2000.0"
    assert data["columns"] == ["ra_deg", "dec_deg", "v_mag", "b_minus_v", "name"] and data["complete_to"] == tool.FIXTURE_COMPLETE_TO
    rows = data["stars"]
    assert len(rows) >= 150 and [r[2] for r in rows] == sorted(r[2] for r in rows)
    names = [r[4] for r in rows]
    assert len(set(names)) == len(names) and {"Sirius", "Betelgeuse", "Rigel", "Alnilam", "Kaus Australis", "Acrux", "Polaris"} <= set(names)
    for ra, dec, v_mag, b_v, _ in rows:
        assert 0 <= ra < 360 and -90 <= dec <= 90 and -1.5 <= v_mag <= 4.5 and -0.4 <= b_v <= 2.0
    # the shipped file is exactly what the tool writes from its table
    expected = tool.star_file_text(tool.FIXTURE_NAME, True, tool.FIXTURE_COMPLETE_TO, sorted(tool.fixture_stars(), key=lambda r: (r[2], r[0])))
    assert STARS.read_text(encoding="utf-8") == expected
    sirius = next(r for r in rows if r[4] == "Sirius")
    assert abs(sirius[0] - 101.29) < 0.1 and abs(sirius[1] + 16.72) < 0.1 and sirius[2] == -1.46


def _bsc_line(ra: tuple[int, int, float], dec: tuple[str, int, int, int], v_mag: float | None, b_v: float | None) -> str:
    """A line in the Bright Star Catalogue's layout (197 bytes; only the columns the converter reads)."""
    line = [" "] * 197

    def put(first: int, text: str) -> None:
        line[first - 1:first - 1 + len(text)] = text

    if ra is not None:
        put(76, f"{ra[0]:02d}{ra[1]:02d}{ra[2]:04.1f}")
        put(84, f"{dec[0]}{dec[1]:02d}{dec[2]:02d}{dec[3]:02d}")
    if v_mag is not None:
        put(103, f"{v_mag:5.2f}")
    if b_v is not None:
        put(110, f"{b_v:5.2f}")
    return "".join(line)


def test_the_converter_reads_the_bright_star_catalogues_lines(tmp_path: Path) -> None:
    tool = _converter()
    text = "\n".join([
        _bsc_line((6, 45, 8.9), ("-", 16, 42, 58), -1.46, 0.00),      # Sirius
        _bsc_line(None, None, None, None),                             # an entry that is not a star: no position
        _bsc_line((5, 55, 10.3), ("+", 7, 24, 25), 0.50, 1.85),        # Betelgeuse
        _bsc_line((0, 5, 9.9), ("+", 45, 13, 45), 6.70, None),         # a faint star without B-V
    ]) + "\n"
    rows = tool.parse_bsc5(text)
    assert rows == [[101.287, -16.716, -1.46, 0.0], [88.793, 7.407, 0.5, 1.85], [1.291, 45.229, 6.7, tool.DEFAULT_B_MINUS_V]]
    assert tool.carry_names(rows, tool.fixture_stars()) == 2
    assert rows[0][4] == "Sirius" and rows[1][4] == "Betelgeuse" and len(rows[2]) == 4
    out = tool.star_file_text(tool.BSC5_NAME, False, tool.BSC5_COMPLETE_TO, rows)
    (tmp_path / "s.js").write_text(out, encoding="utf-8")
    back = tool.read_star_file(tmp_path / "s.js")
    assert back["stars"] == rows and back["approximate"] is False and back["complete_to"] == 6.5
    with pytest.raises(SystemExit, match="line 1 does not fit"):
        tool.parse_bsc5(text.replace("0645", "06x5", 1))
    with pytest.raises(SystemExit, match="out of range"):
        tool.parse_bsc5(_bsc_line((6, 45, 8.9), ("-", 16, 42, 58), 14.0, 0.0))
    # a .gz is unpacked; too few stars is refused (a wrong file), and nothing is written
    packed = tmp_path / "bsc5.dat.gz"
    packed.write_bytes(gzip.compress(text.encode("ascii")))
    assert tool.read_catalogue_text(packed) == text
    with pytest.raises(SystemExit, match="only 3 stars"):
        tool.main([str(packed), "--out", str(tmp_path / "out.js")])
    assert not (tmp_path / "out.js").exists()
    assert tool.main(["--fixture", "--out", str(tmp_path / "f.js")]) == 0
    assert (tmp_path / "f.js").read_text(encoding="utf-8") == STARS.read_text(encoding="utf-8")


def test_the_parts_are_registered() -> None:
    found = {p.name: p for p in P.read_parts() if p.file == "space-sky.js"}
    assert set(found) == PART_NAMES
    assert all(p.module == "vidgen/space-sky" for p in found.values())
    assert found["space-sky-environment"].kind == "environment" and all(p.kind == "sky" for n, p in found.items() if n != "space-sky-environment")
    assert "spaceSky(renderer, {seed})" in found["space-sky"].use and 'stars: \\"real\\"' not in found["space-sky-real"].use and 'stars: "real"' in found["space-sky-real"].use
    assert "Math.random" not in (P.PARTS_DIR / "space-sky.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str, data: object = None) -> list:
    """Import the module in Node as ``S`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "baked", "space-scale", "space-sky", "space-sky-stars")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import fs from 'fs';\nimport * as THREE from 'three';\nimport * as S from 'vidgen/space-sky';\nimport {yUp} from 'vidgen/space-scale';\n"
        "const data = JSON.parse(fs.readFileSync('data.json', 'utf8'));\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        "const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];\n"
        "const angle = (a, b) => Math.acos(Math.max(-1, Math.min(1, dot(a, b) / Math.hypot(...a) / Math.hypot(...b)))) * 180 / Math.PI;\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_the_real_sky_is_in_the_frame_of_the_orbit_data(tmp_path: Path) -> None:
    # the Earth on 19 June: seen from the Sun it lies toward Sagittarius, so the night side looks at the galactic centre
    settings = od.OrbitData.model_validate({"central": "sun", "date": "2026-06-19", "bodies": [{"preset": "earth"}], "span": "1 h"})
    body = next(b for b in od.make_orbit_data(settings, 10, 2, 2)["bodies"] if b["name"] == "Earth")
    earth = np.frombuffer(base64.b64decode(body["position"]), "<f8")[:3].tolist()        # metres, ecliptic J2000, from the Sun
    out = _run_in_node(tmp_path, """
const e = S.equatorialToEcliptic;
out.push(e(0, 0), e(270, 90 - S.OBLIQUITY), e(90, 0));                           // the equinox, the ecliptic's pole, the solstice point
const gc = e(...S.GALACTIC.center); out.push([(Math.atan2(gc[1], gc[0]) * 180 / Math.PI + 360) % 360, Math.asin(gc[2]) * 180 / Math.PI]);
out.push(angle(S.skyDirection(12.3, 45.6), yUp(e(12.3, 45.6))));               // the world frame is space-scale's
const band = S.realBand(); out.push([dot(band.center, band.pole), dot(band.center, band.side), Math.hypot(...band.pole)]);
const stars = S.catalogStars(), at = (name) => [...stars.dir.subarray(stars.names.get(name) * 3, stars.names.get(name) * 3 + 3)];
const b = (name) => 90 - angle(at(name), band.pole);
out.push([angle(at("alnasl"), band.center), angle(at("kaus australis"), band.center), b("deneb"), b("betelgeuse"), b("acrux"), b("arcturus")]);
out.push(angle(yUp(data), band.center));                                        // the Earth's direction from the Sun against the galactic centre
out.push([stars.count, stars.mag[stars.names.get("sirius")], angle(at("polaris"), yUp(e(0, 90)))]);
out.push(S.bandDirection(band, 0, 0).map((x, i) => x - band.center[i]), angle(S.bandDirection(band, 90, 0), band.side), angle(S.bandDirection(band, 0, 90), band.pole));
""", earth)
    equinox, pole, solstice, centre, same, frame, places, earth_angle, catalogue, zero, side, top = out
    assert np.allclose(equinox, [1, 0, 0], atol=1e-12) and np.allclose(pole, [0, 0, 1], atol=1e-9)
    assert np.allclose(solstice, [0, math.cos(math.radians(23.4392911)), -math.sin(math.radians(23.4392911))], atol=1e-12)
    assert abs(centre[0] - 266.84) < 0.02 and abs(centre[1] + 5.54) < 0.02       # the galactic centre's ecliptic longitude and latitude
    assert same < 1e-9
    assert abs(frame[0]) < 1e-4 and abs(frame[1]) < 1e-12 and abs(frame[2] - 1) < 1e-12
    alnasl, kaus, deneb, betelgeuse, acrux, arcturus = places
    assert alnasl < 6 and kaus < 11                                               # Sagittarius' stars round the centre
    assert abs(deneb - 2.0) < 1.0 and abs(betelgeuse + 9.0) < 1.0 and abs(acrux + 0.4) < 1.0 and abs(arcturus - 69.1) < 1.0   # galactic latitudes
    assert earth_angle < 7                                                        # the Sun-Earth line in June points at the centre (5.5 degrees off the ecliptic)
    assert catalogue[0] >= 150 and abs(catalogue[1] + 1.46) < 1e-6 and catalogue[2] < 1.0
    assert np.allclose(zero, 0, atol=1e-12) and side < 1e-6 and top < 1e-6


def test_star_counts_colours_and_seeded_stars(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push([1, 2, 3, 4, 5, 6, 7, 8, 9].map((m) => S.starCount(m + 1) / S.starCount(m)));
out.push([0.5, 4, 48, 9000, 60000].map((n) => S.starCount(S.magnitudeOfRank(n)) / n));
out.push([-1.46, 0, 2.5, 4, 6, 8.5].map((m) => S.starAmplitude(m)), S.starAmplitude(6, 1) / S.starAmplitude(7, 1));
out.push(S.blackbody(6500), S.starColor(-0.2, 1), S.starColor(0.65, 1), S.starColor(1.6, 1), S.starColor(1.6, 0), [S.temperature(0.65), S.temperature(0), S.temperature(1.5)]);
const band = S.seededBand(4), a = S.seededStars(4, {frame: band}), again = S.seededStars(4, {frame: band}), other = S.seededStars(5, {frame: S.seededBand(5)});
const even = S.seededStars(4, {frame: band, gather: 0, clusters: false}), few = S.seededStars(4, {frame: band, density: 0.25, limit: 7, clusters: false});
const near = (s) => { let n = 0; for (let i = 0; i < s.count; i++) if (Math.abs(dot([...s.dir.subarray(i * 3, i * 3 + 3)], band.pole)) < Math.sin(10 * Math.PI / 180)) n++; return n / s.count; };
const under = (s, m) => s.mag.filter((x) => x < m).length;
out.push([a.count, S.starCount(8.5), even.count, few.count, S.starCount(7) * 0.25]);
out.push([a.dir.every((x, i) => x === again.dir[i]) && a.mag.every((x, i) => x === again.mag[i]), a.dir.slice(0, 30).some((x, i) => x !== other.dir[i])]);
out.push([near(a), near(even)], [under(even, 0), under(even, 3), under(even, 5), under(even, 6), under(even, 7), under(even, 8)]);
const tinted = (s) => { let n = 0; for (let i = 0; i < s.count; i++) { const c = S.starColor(s.bv[i], 0.7); if (Math.max(...c) / Math.min(...c) > 2) n++; } return n / s.count; };
out.push([tinted(even), Math.min(...even.mag), Math.max(...even.mag), [...even.dir.subarray(0, 3)].reduce((s, x) => s + x * x, 0)]);
const b = S.seededBand(4), c = S.seededBand(9); out.push([dot(b.center, b.pole), dot(b.center, band.center), angle(b.pole, c.pole)]);
const cut = S.seededStars(4, {frame: band, from: 2.5}); out.push([Math.min(...cut.mag), cut.count, S.starCount(8.5) - S.starCount(2.5)]);
""")
    ratios, round_trip, amplitudes, true_ratio, white, blue, sun, red, plain, kelvin, counts, same, near, ladder, colours, frames, cut = out
    assert all(2.3 < r < 4.0 for r in ratios)                                    # about three times as many per magnitude
    assert np.allclose(round_trip, 1, rtol=1e-6)
    assert amplitudes == sorted(amplitudes, reverse=True) and abs(amplitudes[2] - 1) < 1e-9
    assert 5 < amplitudes[0] < 12 and amplitudes[5] > 0.008                      # Sirius glares a little; the faintest clears ACES's toe (0.002)
    assert abs(true_ratio - 2.512) < 0.001
    assert np.allclose(white, [1, 1, 1], atol=0.06)                              # 6,500 K is white
    assert blue[2] > blue[0] and red[0] > red[1] > red[2] and max(sun) / min(sun) < 1.35 and plain == [1, 1, 1]
    assert abs(kelvin[0] - 5780) < 40 and kelvin[1] > 9500 and kelvin[2] < 4000
    stars, expected, even, few, few_expected = counts
    assert abs(even - expected) <= 1 and 0 < stars - even < 400 and abs(few - few_expected) <= 1     # the counts, and a few clusters' stars more
    assert same == [True, True]
    assert near[0] > 0.30 and abs(near[1] - 0.174) < 0.01                        # gathered toward the band; evenly: sin 10 degrees
    assert ladder[0] <= 8 and 100 < ladder[1] < 250 and 1300 < ladder[2] < 1900 and 4300 < ladder[3] < 5300 and 12500 < ladder[4] < 15500 and 37000 < ladder[5] < 45000
    assert colours[0] < 0.15 and colours[1] < -0.5 and colours[2] <= 8.5 and abs(colours[3] - 1) < 1e-5     # few strongly tinted stars
    assert abs(frames[0]) < 1e-12 and abs(frames[1] - 1) < 1e-12 and frames[2] > 1
    assert cut[0] >= 2.5 and abs(cut[1] - cut[2]) < 400


def test_options_windows_and_the_particle_galaxy(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const o = S.resolveOptions({});
out.push([o.seed, o.stars, o.look, o.limit, o.milkyWay, o.nebulae.length, o.galaxies.length, dot(o.band.center, o.band.pole)]);
const rich = S.resolveOptions({look: "rich", seed: 3, density: 2}); out.push([rich.density, rich.milkyWay, rich.nebulae.length, rich.galaxies.length, rich.nebulae.every((n) => Math.abs(Math.hypot(...n.direction) - 1) < 1e-9)]);
const real = S.resolveOptions({stars: "real", galaxies: [{kind: "elliptical", at: [0, 1, 0], size: 2}]});
out.push([real.galaxies.length, real.galaxies[0].kind, real.galaxies[3].kind, angle(real.band.center, S.realBand().center)]);
const placed = S.resolveOptions({center: [1, 0, 0], pole: [0.2, 1, 0], nebulae: [{kind: "dark", at: {l: 90, b: 0}, size: 5}, {at: [0, 0, -2]}]});
out.push([placed.band.center, dot(placed.band.center, placed.band.pole), placed.nebulae[0].direction, placed.nebulae[1].direction, placed.nebulae[1].kind]);
out.push([err(() => S.resolveOptions({desity: 2})), err(() => S.resolveOptions({look: "ritch"})), err(() => S.resolveOptions({stars: "reel"})),
  err(() => S.resolveOptions({stars: "real", center: [1, 0, 0]})), err(() => S.resolveOptions({nebulae: [{kind: "emision"}]})), err(() => S.resolveOptions({seed: 1.5})),
  err(() => S.resolveOptions({galaxies: 40})), err(() => S.resolveOptions({center: [1, 0, 0], pole: [2, 0, 0]})), err(() => S.spaceSky({})), err(() => S.spiralGalaxy({arm: 3}))]);
out.push([0, 1, 2, 3, 4, 5].map((f) => S.faceWindow(f, [1, 0.1, 0.05], 0.1)), [0, 1, 2, 3, 4, 5].map((f) => S.faceWindow(f, [1, 1, 1], 0.2) !== null), S.faceWindow(0, [1, 0, 0], 2));
const g = S.spiralGalaxy({seed: 2, radius: 5, stars: 3000, clouds: 400}), h = S.spiralGalaxy({seed: 2, radius: 5, stars: 3000, clouds: 400});
const [glow, specks, dust] = [g.object.children[0], g.object.children[2], g.object.children[1]];
const p = specks.geometry.getAttribute("position").array, far = Math.max(...Array.from({length: 3000}, (_, i) => Math.hypot(p[i * 3], p[i * 3 + 2])));
out.push([g.object.children.length, glow.geometry.instanceCount, specks.geometry.getAttribute("position").count, far, Math.max(...Array.from({length: 3000}, (_, i) => Math.abs(p[i * 3 + 1]))),
  p.every((x, i) => x === h.object.children[2].geometry.getAttribute("position").array[i]), dust.geometry.instanceCount > 0]);
""")
    defaults, rich, real, placed, errors, windows, corner, whole, galaxy = out
    assert defaults[:7] == [1, "seed", "natural", 8.5, 1, 0, 0] and abs(defaults[7]) < 1e-12
    assert rich == [2, 1.3, 5, 2, True]                                           # the page's option wins over the look's
    assert real[:3] == [4, "irregular", "elliptical"] and real[3] < 1e-9           # the Magellanic Clouds and Andromeda, then the page's
    assert np.allclose(placed[0], [1, 0, 0]) and abs(placed[1]) < 1e-12
    assert np.allclose(placed[2], [0, 0, -1], atol=1e-9) or np.allclose(placed[2], [0, 0, 1], atol=1e-9)
    assert np.allclose(placed[3], [0, 0, -1]) and placed[4] == "emission"
    assert 'unknown option "desity" (did you mean "density"?)' in errors[0] and '(did you mean "rich"?)' in errors[1] and '(did you mean "real"?)' in errors[2]
    assert "the real sky's band is where it is" in errors[3] and '(did you mean "emission"?)' in errors[4] and "seed must be a whole number" in errors[5]
    assert "galaxies must be a number from 0 to 12" in errors[6] and "point the same way" in errors[7] and "THREE.WebGLRenderer" in errors[8]
    assert 'unknown option "arm" (did you mean "arms"?)' in errors[9]
    assert windows[0] is not None and all(w is None for w in windows[1:])           # a small cap near +x: one face, a small window
    s0, t0, s1, t1 = windows[0]
    assert -1 <= s0 < s1 <= 1 and -1 <= t0 < t1 <= 1 and s1 - s0 < 0.3 and t1 - t0 < 0.3
    assert corner == [True, False, True, False, True, False] and whole == [-1, -1, 1, 1]
    assert galaxy[0] == 3 and galaxy[1] == 400 and galaxy[2] == 3000 and galaxy[3] <= 5.0001 and galaxy[4] < 1.2 and galaxy[5] is True and galaxy[6] is True


PAGE = """
import * as THREE from "three";
import {spaceSky} from "vidgen/space-sky";
let renderer, scene, camera, sky, made = {};
export function load(ctx) {
  const c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(40, ctx.width / ctx.height, 0.1, 100);
  sky = spaceSky(renderer, {size: 128, ...c.sky});
  if (c.background) scene.background = sky.background; else scene.add(sky.object);
  if (c.environment) { scene.environment = sky.environment; made.environment = scene.environment.isTexture === true; }
  made.info = {stars: sky.info.stars, mode: sky.info.mode, approximate: sky.info.approximate, catalogStars: sky.info.catalogStars, size: sky.info.size};
  window.skyMade = made;
  camera.lookAt(sky.direction(c.toward));
}
export function frame(t, ctx) { camera.rotation.y += 0; renderer.render(scene, camera); }
"""


@pytest.mark.slow
@pytest.mark.render
def test_the_sky_draws_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "sky.js").write_text(PAGE, encoding="utf-8")

    def draw(data: dict) -> tuple[np.ndarray, dict, dict]:
        with WebPage(tmp_path, WebEntry("script", "sky.js"), scene_id="s", size=(320, 180), fps=10, frames=2, data=data) as page:
            frames = [page.frame(n)[..., :3].astype(int) for n in range(2)]
            assert np.array_equal(frames[0], frames[1])                          # nothing moves by itself
            return frames[0], dict(page.loaded), page._page.evaluate("window.skyMade")

    core, loaded, made = draw({"sky": {"seed": 1}, "toward": "center"})
    again, _, _ = draw({"sky": {"seed": 1}, "toward": "center"})
    other, _, _ = draw({"sky": {"seed": 2}, "toward": "center"})
    assert np.array_equal(core, again) and not np.array_equal(core, other)       # a seed is a sky
    assert {"__vidgen__/modules/space-sky.js", "__vidgen__/modules/space-sky-stars.js"} <= set(loaded)
    assert made["info"]["mode"] == "seed" and made["info"]["stars"] > 60000 and made["info"]["size"] == 128
    luma = core.mean(axis=-1)
    assert luma.mean() > 12                                                        # the band's bulge fills the frame
    assert (core.min(axis=-1) < 3).mean() < 0.9 and luma.max() > 150               # stars on it
    away, _, _ = draw({"sky": {"seed": 1}, "toward": "pole"})
    assert np.percentile(away.mean(axis=-1), 50) < 4 and (away.mean(axis=-1) > 60).sum() > 20     # black between the stars: black is black
    assert away.mean() < luma.mean() / 3                                           # and far darker than the band
    # the real sky: Sirius where the camera looks, the brightest thing in the frame
    real, _, made = draw({"sky": {"stars": "real"}, "toward": "Sirius"})
    assert made["info"]["mode"] == "real" and made["info"]["approximate"] is True and made["info"]["catalogStars"] >= 150
    y, x = np.unravel_index(real.mean(axis=-1).argmax(), real.shape[:2])
    assert abs(y - 90) <= 2 and abs(x - 160) <= 2 and real[y, x].min() > 200
    # as scene.background and as an environment
    back, _, made = draw({"sky": {"seed": 1}, "toward": "center", "background": True, "environment": True})
    assert made["environment"] is True and back.mean() > 8
    assert np.corrcoef(back.mean(axis=-1).ravel(), luma.ravel())[0, 1] > 0.6       # the same sky, the same way up


def test_a_long_lens_reads_the_cube_coarser() -> None:
    """Step 378: through a long lens a texel of the 1024 cube spans many pixels (soft blobs of the faint
    stars, streaks of the band's clouds behind a craft); the sky then reads the cube's coarser levels.
    At 1280x720 a normal lens reads the finest level, a 300 mm lens a level of about 1.1 degree texels."""
    source = (MODULES / "space-sky.js").read_text(encoding="utf-8")
    pixels = float(re.search(r"LENS_PIXELS = ([0-9.]+)", source).group(1))
    soft = float(re.search(r"LENS_SOFT = ([0-9.]+)", source).group(1))
    assert "textureLod(uSky, vD, max(0.0, LENS_SOFT * log2(texels / LENS_PIXELS)))" in source and "uSize: {value: this.size}" in source

    def level(fov_deg: float, height: int = 720, size: int = 1024) -> float:
        texels = (math.pi / 2 / size) / (math.radians(fov_deg) / height)
        return max(0.0, soft * math.log2(texels / pixels))

    assert level(26.99) == 0 and level(37.85) == 0                      # normal and wide-normal lenses: as before
    assert 0 < level(15.9) < 1.2 and level(4.58) > 3.5                   # portrait a little coarser, tele smooth
    assert math.degrees(math.pi / 2 / 1024) * 2 ** level(4.58) > 1.0     # texels wider than a degree: no blob in a 4.6 degree frame
