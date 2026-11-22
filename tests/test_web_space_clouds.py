"""Cloud decks, towers, lightning and a giant's decks, ``vidgen/space-clouds`` (Step 383, DESIGN.md §123.5):
the module is served by its import name and imports only ``three``, ``vidgen/space-air`` and
``vidgen/space-bodies``; its parts are registered under the kind ``cloud``; in Node (when it is installed):
the noise tile is the same twice and repeats, a shell's stretch of a ray against a walk along the ray, a
deck's horizon, decks and skies with a did-you-mean, the cover a deck is asked for is roughly the cover its
pattern has, the pattern drifts with the wind, towers and a storm's flashes from a seed and from stated
times, a giant's decks in its band's colours; in Chromium (``slow``): tops are brighter than bases, a
sunset's tops are warmer than noon's, more cover hides more ground, a flash lights a tower, a giant's decks
have its band's colour, a frame drawn twice is the same, and the picture is the same with the air's table
baked, from the cache and without the cache."""

from __future__ import annotations

import json
import math
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
MODULE = MODULES / "space-clouds.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
PART_NAMES = {"clouds-fair", "clouds-sea-of-cloud", "clouds-sunset", "clouds-towers", "clouds-between-decks", "clouds-lightning", "clouds-over-sea", "clouds-giant", "clouds-ice-giant"}
EARTH = 6.371e6


def test_the_module_is_served_by_its_import_name() -> None:
    assert VIDGEN_MODULES["vidgen/space-clouds"] == "space-clouds.js"
    assert IMPORT_MAP["imports"]["vidgen/space-clouds"] == "/__vidgen__/modules/space-clouds.js"
    assert vidgen_file("modules/space-clouds.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/space-clouds.js"])["__vidgen__/modules/space-clouds.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three", "vidgen/space-air", "vidgen/space-bodies"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source and "globalThis" not in source
    assert MODULE not in INIT_FILES and "space-clouds" not in engine_id()


def test_the_parts_are_registered_under_their_own_kind() -> None:
    assert "cloud" in P.KINDS and P.KINDS.index("cloud") == P.KINDS.index("sea") + 1
    found = {p.name: p for p in P.read_parts() if p.file == "space-clouds.js"}
    assert set(found) == PART_NAMES
    assert all(p.module == "vidgen/space-clouds" and p.kind == "cloud" for p in found.values())
    assert "clouds(renderer, sky" in found["clouds-fair"].use and "weather.update(t, {camera})" in found["clouds-fair"].use
    assert "a look" in found["clouds-giant"].label and "a look" in found["clouds-lightning"].label      # what is chosen for the picture is said on the sheet
    assert "shade: weather.shade" in found["clouds-over-sea"].use
    assert [p.name for p in P.select_parts(P.read_parts(), kind="cloud")] == [p.name for p in P.read_parts() if p.file == "space-clouds.js"]
    assert "Math.random" not in (P.PARTS_DIR / "space-clouds.js").read_text(encoding="utf-8")


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node as ``C`` (``three`` and vidgen's modules from the package) and print ``out`` as JSON."""
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
    names = ("music-time", "baked", "space-bodies", "space-air", "space-clouds")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as C from 'vidgen/space-clouds';\nimport {bandRamp, resolveOptions, linearColor} from 'vidgen/space-bodies';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_the_tile_a_shell_and_a_decks_horizon(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const tile = C.noiseTile(), sums = [0, 0, 0, 0]; let lo = 255, hi = 0, hash = 0;
for (let k = 0; k < tile.data.length; k++) { sums[k % 4] += tile.data[k] / 255; lo = Math.min(lo, tile.data[k]); hi = Math.max(hi, tile.data[k]); hash = (hash * 31 + tile.data[k]) >>> 0; }
out.push([tile.size, tile.data.length, sums.map((x) => x / tile.size ** 2), lo, hi, hash, C.noiseTile() === tile, tile.at(0.3, 0.7), tile.at(1.3, -0.3), tile.at(7.3, 4.7), C.TILE]);
// the first stretch of a ray in a shell, against a walk along the ray in steps of a metre or so
const R = 6.371e6, walk = (h, mu, a, b) => { const r0 = R + h; let from = null, to = null;
  for (let t = 0; t < 4e5; t += 2) { const r = Math.sqrt(r0 * r0 + 2 * r0 * mu * t + t * t) - R, inside = r >= a && r <= b; if (inside && from === null) from = t; if (!inside && from !== null) { to = t; break; } }
  return from === null ? null : [from, to]; };
const cases = [[10000, -0.2, 1800, 3000], [10000, -0.03, 1800, 3000], [100, 0.3, 1000, 2100], [100, 0.02, 1000, 2100], [2000, 0.05, 1800, 3000], [2000, -0.05, 1800, 3000], [2000, 0, 1800, 3000], [10000, 0.1, 1800, 3000], [5000, -0.02, 1800, 3000], [4600, -0.005, 1600, 2800]];
out.push(cases.map((c) => [C.shellSpan(R, ...c), walk(...c)]));
out.push([[10000, 3000], [3600, 3000], [1.25e5, 9e4], [100, 2100]].map(([h, d]) => { const z = C.deckHorizon(R, h, d); return [z.distance, z.dip, C.shellSpan(R, h, -Math.sin((z.dip + 0.01) * Math.PI / 180), d - 1200, d) !== null, C.shellSpan(R, h, -Math.sin((z.dip - 0.01) * Math.PI / 180), d - 1200, d) !== null]; }));
""")
    size, count, means, lo, hi, digest, kept, here, again, far, tile = out[0]
    assert size == tile == 256 and count == 256 * 256 * 4 and lo == 0 and hi == 255 and kept is True
    assert digest == 865162837                                                         # the same numbers on every machine
    assert all(0.25 < m < 0.75 for m in means) and here == pytest.approx(again, abs=1e-12) and here == pytest.approx(far, abs=1e-9)   # it repeats
    for got, walked in out[1]:
        if walked is None:
            assert got is None
        else:
            assert got[0] == pytest.approx(walked[0], abs=3) and got[1] == pytest.approx(walked[1], abs=3), (got, walked)
    assert out[1][7][0] is None and out[1][0][0][0] > 30000 and out[1][4][0][0] == 0                                    # looking up from above: nothing; from inside: from the eye on
    for (distance, dip, under, over), (h, d) in zip(out[2], ((10000, 3000), (3600, 3000), (1.25e5, 9e4), (100, 2100))):
        if h >= d:
            assert dip == pytest.approx(math.degrees(math.acos((EARTH + d) / (EARTH + h))), rel=1e-9) and distance == pytest.approx(math.sqrt((EARTH + h) ** 2 - (EARTH + d) ** 2), rel=1e-9)
            assert under is True and over is False                                                                      # the deck ends where its horizon is
        else:
            assert dip == 0 and distance == pytest.approx(math.sqrt((EARTH + d) ** 2 - (EARTH + h) ** 2), rel=1e-9)


def test_decks_cover_drift_towers_and_storms(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push([Object.keys(C.DECKS), Object.keys(C.SKIES), Object.keys(C.QUALITIES), C.MOST, C.deckOf("stratus").top - C.deckOf("stratus").base, C.deckOf({type: "stratus", base: 5000}).top, C.deckOf({type: "cirrus", base: 8000, top: 8200}).top, Object.isFrozen(C.deckOf("cumulus"))]);
out.push([err(() => C.deckOf("cumlus")), err(() => C.deckOf({type: "cirrus", covr: 1})), err(() => C.deckOf({type: "stratus", base: 3000, top: 2000})), err(() => C.deckOf("cumulus", {cover: 2})),
  err(() => C.towerList({count: 9})), err(() => C.towerList({radius: 3, cnt: 1})), err(() => C.clouds(null)), err(() => C.giantSky("earth")), err(() => C.giantAir("mars")), err(() => C.stormOf({rate: 5, tmes: []}, {deck: C.deckField("cumulus")})),
  err(() => C.stormOf({times: ["a"]}, {deck: C.deckField("cumulus")})), err(() => C.stormOf({rate: 5})), err(() => C.deckOf({type: "stratus", stripes: {colors: [[1, 1, 1]], span: 5}}))]);
// the cover asked for against the share of places where the pattern stands over its level
const share = (f, t) => { let n = 0; const N = 12000; for (let i = 0; i < N; i++) if (f.coverAt((i * 7919.3) % 3e6 - 1.5e6, (i * 104729.7) % 2.7e6 - 1e6, t) > 0) n++; return n / N; };
out.push(["cumulus", "stratus", "cirrus"].map((type) => [0.2, 0.5, 0.8].map((cover) => share(C.deckField({type, cover, fronts: 0}, {seed: 5}), 100))));
// the broad weather: round the place the cover asked for, far off it varies (clear lanes, closed fields) and never repeats
const near = (f) => { let n = 0; const N = 6000; for (let i = 0; i < N; i++) if (f.coverAt(((i * 7919.3) % 2e4) - 1e4, ((i * 104729.7) % 2e4) - 1e4, 0) > 0) n++; return n / N; };
const patch = (f, x0, z0) => { let n = 0; for (let i = 0; i < 900; i++) if (f.coverAt(x0 + (i % 30) * 700, z0 + Math.floor(i / 30) * 700, 0) > 0) n++; return n / 900; };
const fair = C.deckField({type: "cumulus", cover: 0.4}, {seed: 5}), patches = Array.from({length: 40}, (_, k) => patch(fair, 3e5 + k * 9.7e4, -2e5 + k * 3.1e4));
out.push([near(fair) - near(C.deckField({type: "cumulus", cover: 0.4, fronts: 0}, {seed: 5})), share(fair, 0), Math.min(...patches), Math.max(...patches), C.broadNoise(3.3, -7.9, 11) === C.broadNoise(3.3, -7.9, 11), C.broadNoise(3.3, -7.9, 11) !== C.broadNoise(3.3 + 1024, -7.9, 11), fair.middle !== 0 && fair.broadAt(0, 0, 0) === 0]);
out.push([share(C.deckField({type: "stratus", cover: 1}), 0), share(C.deckField({type: "cumulus", cover: 0}), 0)]);
// a seed is a sky; time moves it with the wind, and changes it (the readings move at their own speeds)
const a = C.deckField("cumulus", {seed: 3}), b = C.deckField("cumulus", {seed: 3}), c = C.deckField("cumulus", {seed: 4}), still = C.deckField("cumulus", {seed: 3, wind: 0});
const at = (f, t, dx = 0) => [0, 1, 2, 3, 4, 5].map((k) => f.valueAt(k * 911 + dx, k * -577, t));
const wind = [Math.sin(70 * Math.PI / 180) * 12, -Math.cos(70 * Math.PI / 180) * 12];
out.push([at(a, 0), at(b, 0), at(c, 0), at(a, 60), at(still, 0), at(still, 60), a.reads.length, a.level, a.span, a.reads[2].drift, wind,
  [0, 1, 2, 3, 4, 5].map((k) => Math.abs(a.valueAt(k * 911 + wind[0] * 60, k * -577 + wind[1] * 60, 60) - a.valueAt(k * 911, k * -577, 0)))]);
const tw = C.towerList({count: 5}, 4), tw2 = C.towerList({count: 5}, 4), placed = C.towerList({at: [[1000, -2000], [5, 6]], radius: 3000, top: 9000}, 1);
out.push([JSON.stringify(tw) === JSON.stringify(tw2), tw.list.length, tw.list.map((t) => [Math.hypot(t.x, t.z), t.radius, t.base, t.top, t.anvil]), placed.list.map((t) => [t.x, t.z]), C.towerList(0).list.length, C.towerList(true).list.length]);
const times = C.strikeTimes(3, {rate: 12, to: 600}), same = C.strikeTimes(3, {rate: 12, to: 600}), other = C.strikeTimes(4, {rate: 12, to: 600});
out.push([times.length, JSON.stringify(times) === JSON.stringify(same), JSON.stringify(times) === JSON.stringify(other), Math.min(...times.slice(1).map((t, i) => t - times[i])), times[0], times[times.length - 1],
  C.strikeTimes(3, {rate: 0}).length, C.strikeTimes(3, {rate: 12, from: 20, to: 30}).every((t) => t >= 20 && t < 30)]);
out.push([[-0.01, 0, 0.005, 0.01, 0.05, 0.11, 0.125, 0.3, 0.54, 0.55, 2].map((age) => C.flashLevel(age, 3)), C.flashLevel(0.125, 1), C.FLASH_SECONDS]);
const storm = C.stormOf({times: {t: new Float32Array([4, 2]), g: new Float32Array([1, 0.5])}, rate: 6, to: 20, power: 2}, {seed: 4, towers: tw.list});
const events = C.stormOf({times: [{time: 1.5, gain: 1}, 3]}, {seed: 4, deck: C.deckField("stratus")});
out.push([storm.map((f) => [f.time, f.power, f.follows, f.strokes, tw.list.some((t) => Math.hypot(f.place[0] - t.x, f.place[2] - t.z) <= 0.5 * t.radius + 1e-6 && f.place[1] > t.base && f.place[1] < t.top)]),
  events.map((f) => [f.time, f.follows, f.place[1]]), C.stormOf(true, {seed: 1, deck: C.deckField("stratus")}).length]);
""")
    decks, skies, qualities, most, depth, moved, stated, frozen = out[0]
    assert decks == ["cumulus", "stratus", "cirrus"] and skies == ["fair", "overcast", "layers", "towers", "storm"] and qualities == ["fast", "standard", "fine"]
    assert most == {"decks": 4, "towers": 6, "flashes": 3} and depth == 1200 and moved == 6200 and stated == 8200 and frozen is True      # a deck moved by its base keeps its depth
    wrong = out[1]
    assert 'did you mean "cumulus"' in wrong[0] and 'did you mean "cover"' in wrong[1] and "top (metres)" in wrong[2] and "cover must be" in wrong[3]
    assert "towers.count" in wrong[4] and 'did you mean "count"' in wrong[5] and "THREE.WebGLRenderer" in wrong[6] and "not a giant" in wrong[7] and "not a giant" in wrong[8]
    assert 'did you mean "times"' in wrong[9] and "ctx.music" in wrong[10] and "towers or a deck" in wrong[11] and "stripes.colors" in wrong[12]
    for row in out[2]:
        for got, asked in zip(row, (0.2, 0.5, 0.8)):
            assert got == pytest.approx(asked, abs=0.06), out[2]                                                         # roughly the cover asked for
    here, world, least, most_, same, endless, centred = out[3]
    assert abs(here) < 0.06 and world == pytest.approx(0.4, abs=0.12) and least < 0.2 and most_ > 0.6       # the cover asked for round the place; lanes and closed fields far off
    assert same and endless and centred
    assert out[4] == pytest.approx([1, 0], abs=0.002)
    first, again, other, later, calm, calm_later, reads, level, span, drift, wind, carried = out[5]
    assert first == again and first != other and first != later and calm == calm_later and reads == 4 and 0.3 < level < 0.8 and span > 0.02
    assert drift == pytest.approx(wind) and max(carried) < 0.12 and max(abs(a - b) for a, b in zip(first, later)) > max(carried)   # the clouds go with the wind, and change a little on the way
    same, count, towers, placed, none, default = out[6]
    assert same is True and count == 5 and none == 0 and default == 4 and placed == [[1000, -2000], [5, 6]]
    assert all(0.3 * 60000 <= far <= 60000 and 0.75 * 4200 <= radius <= 1.25 * 4200 and base == 1100 and 9000 < top <= 11500 and 1.8 < anvil < 2.6 for far, radius, base, top, anvil in towers)
    n, same, other, gap, first_time, last, none, within = out[7]
    assert n == pytest.approx(120, rel=0.25) and same is True and other is False and gap >= 0.25 and 0 <= first_time < last < 600 and none == 0 and within is True
    levels, single, seconds = out[8]
    assert levels[0] == 0 and levels[1] == 0 and levels[3] > levels[2] > 0 and levels[3] > levels[4] > levels[5] and levels[6] > levels[5] and levels[-2] == 0 and levels[-1] == 0 and seconds == 0.55
    assert single < levels[6] and levels[8] < 0.01                                                                        # a second stroke 0.11 s after the first; it ends without a step
    storm, events, default_storm = out[9]
    assert [row[0] for row in storm] == sorted(row[0] for row in storm) and {2, 4} <= {row[0] for row in storm} and len(storm) == 4
    by_time = {row[0]: row for row in storm}
    assert by_time[2][1] < by_time[4][1] * 0.95 and all(row[2] is False and 1 <= row[3] <= 4 and row[4] is True for row in storm)        # the track's gains; every flash inside a tower
    assert [row[0] for row in events] == [1.5, 3] and all(row[1] is True and 1800 < row[2] < 3000 for row in events) and default_storm == pytest.approx(100, rel=0.3)


def test_the_pattern_never_repeats_and_the_weather_has_more_say_from_high_up(tmp_path: Path) -> None:
    """Step 395: the tile is read through untiled() (a warp and cells at their own offsets and turns), so a deck's
    pattern is no longer like itself one repeat away; the blend keeps the tile's mean and contrast and has no jumps
    at the cells' edges; seen from high up the broad weather has more say, but not over a closed deck."""
    out = _run_in_node(tmp_path, """
const tile = C.noiseTile(), N = 20000, mean = [0, 0, 0, 0], sq = [0, 0, 0, 0], plainSq = [0, 0, 0, 0];
for (let i = 0; i < N; i++) { const u = (i * 0.6180339887) % 1 * 97 - 40, v = (i * 0.7548776662) % 1 * 89 - 31, a = C.untiled(u, v, 77), b = tile.at(u, v);
  for (let k = 0; k < 4; k++) { mean[k] += a[k] / N; sq[k] += (a[k] - tile.mean[k]) ** 2 / N; plainSq[k] += (b[k] - tile.mean[k]) ** 2 / N; } }
// across a cell's edge (u a whole number) and in a cell's middle: steps of a thousandth of a repeat
const jump = (u0) => Math.max(...[0, 1, 2, 3].map((k) => Math.abs(C.untiled(u0 + 5e-4, 3.37, 9, false)[k] - C.untiled(u0 - 5e-4, 3.37, 9, false)[k])));
const f = C.deckField({type: "cumulus", fronts: 0}, {seed: 5}), r = f.reads[2], det = r.u[0] * r.v[1] - r.u[1] * r.v[0], rep = [r.v[1] / det, -r.v[0] / det];
const a = [], b = [], c = [];
for (let i = 0; i < 4000; i++) { const x = (i * 7919.3) % 4e5 - 2e5, z = (i * 104729.7) % 3e5 - 1.5e5; a.push(f.valueAt(x, z)); b.push(f.valueAt(x + rep[0], z + rep[1])); c.push(f.valueAt(x + 2 * rep[0], z + 2 * rep[1])); }
const corr = (p, q) => { const m = (s) => s.reduce((x, y) => x + y, 0) / s.length, mp = m(p), mq = m(q); let pq = 0, pp = 0, qq = 0; p.forEach((x, i) => { pq += (x - mp) * (q[i] - mq); pp += (x - mp) ** 2; qq += (q[i] - mq) ** 2; }); return pq / Math.sqrt(pp * qq); };
const cu = C.deckOf("cumulus"), closed = C.deckOf("stratus"), fair = C.deckField("cumulus", {seed: 5});
out.push([mean, tile.mean, sq, plainSq, [1, 2, 3].map(jump), [1.5, 2.5].map(jump), corr(a, b), corr(a, c), f.reads.map((q) => q.salt), C.warpNoise(1.3, 2.7, 4), C.broadNoise(1.3, 2.7, 4),
  [0, cu.top + 2 * cu.size, cu.top + 9 * cu.size, cu.top + 15 * cu.size, 4e5].map((h) => C.aloft(cu, h)), C.aloft(closed, 4e5), fair.valueAt(3e5, 2e5, 0) === fair.valueAt(3e5, 2e5, 0, 0), fair.valueAt(3e5, 2e5, 0) !== fair.valueAt(3e5, 2e5, 0, 4e5), fair.valueAt(0, 0, 0, 4e5) - fair.valueAt(0, 0, 0)]);
""")
    mean, tile_mean, sq, plain_sq, edges, middles, one, two, salts, warp, broad, aloft, closed, same, changed, centre = out[0]
    assert mean == pytest.approx(tile_mean, abs=0.02)                                                       # the tile's mean kept
    assert all(0.75 * p < s < 1.25 * p for s, p in zip(sq, plain_sq))                                       # and its contrast (the blend's weights)
    assert max(edges) < 0.04 and max(middles) < 0.04                                                        # no jump at a cell's edge (no more change than in a middle)
    assert abs(one) < 0.15 and abs(two) < 0.15                                                              # one and two repeats away: unlike (0.8 before Step 395)
    assert len(set(salts)) == 4 and warp[0] == pytest.approx(broad) and warp[1] != warp[0]
    assert aloft[0] == aloft[1] == 1 and 1 < aloft[2] < 3 and aloft[3] == aloft[4] == 3 and closed == 1
    assert same and changed and abs(centre) < 1e-9                                                          # round the place still the cover asked for


def test_a_giants_decks_take_its_bands_colours(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const g = C.giantSky("jupiter", {latitude: 24, scale: 112000}), again = C.giantSky("jupiter", {latitude: 24, scale: 112000}), o = resolveOptions("jupiter");
const lin = (c) => linearColor("c", c), ramp = bandRamp(o.seed, {bands: o.bands, contrast: o.contrast, zones: o.palette.zones.map(lin), belts: o.palette.belts.map(lin)});
const entry = ramp[Math.round((Math.sin(24 * Math.PI / 180) + 1) / 2 * ramp.length - 0.5)].slice(0, 3);
const st = g.decks[1].stripes, true1 = C.giantSky("jupiter", {latitude: 24, scale: 112000, squeeze: 1}).decks[1].stripes;
out.push([JSON.stringify(g) === JSON.stringify(again), g.band, entry, g.decks.map((d) => [d.name, d.type, d.base / 112000, d.top / 112000, d.density * (d.top - d.base)]), g.decks[1].color, [st.colors.length, st.span / 112000, st.colors[32], st.colors.map((c) => c[3]), Math.max(...st.colors.map((c) => c[0])) - Math.min(...st.colors.map((c) => c[0])), Math.max(...true1.colors.map((c) => c[0])) - Math.min(...true1.colors.map((c) => c[0]))], g.next, g.floor, g.towers.count, g.towers.top / 112000, C.GIANT, g.wind, g.direction, C.giantSky("jupiter", {towers: 3}).towers.count]);
out.push(["jupiter", "saturn", "neptune", "tempest", "azure"].map((w) => { const s = C.giantSky(w, {latitude: -8}); return [s.band, s.decks.length, s.decks[1].color]; }));
const air = C.giantAir("jupiter"), ice = C.giantAir("neptune"), own = resolveOptions("jupiter").air;
out.push([air.world, air.air.rayleigh, own.rayleigh, air.air.height, own.height, ice.air.rayleigh, resolveOptions("neptune").air.rayleigh, C.giantSky("jupiter", {latitude: 0}).band, C.giantSky("jupiter", {latitude: -8}).band]);
""")
    same, band, entry, decks, colour, stripes, nxt, floor, towers, tower_top, giant, wind, direction, asked = out[0]
    assert same is True and band == pytest.approx(entry)                                                # the colour the planet is painted with at that latitude, from outside
    assert [d[0] for d in decks] == ["deep", "main", "haze"] and [d[1] for d in decks] == ["stratus", "stratus", "cirrus"]
    assert [d[2] for d in decks] == pytest.approx([giant["deep"][0], giant["main"][0], giant["haze"][0]]) and decks[0][3] < decks[1][2] < decks[1][3] < decks[2][2]
    assert decks[0][4] == pytest.approx(10) and decks[1][4] == pytest.approx(9) and decks[2][4] == pytest.approx(0.3)      # two closed decks and a haze you see through
    count, span, here, lifts, squeezed, true_bands = stripes
    assert colour == pytest.approx([min(1, x * 1.05) for x in band]) and count == 64 and span == pytest.approx(12) and here[:3] == pytest.approx(colour, abs=0.12)
    assert squeezed > 0.25 and true_bands < 0.5 * squeezed and max(lifts) > 0.02 and min(lifts) < -0.02 and max(abs(x) for x in lifts) <= 0.1 + 1e-9   # several bands in view (a look); at the true width one
    assert max(abs(a - b) for a, b in zip(nxt, here[:3])) > 0.05 and max(floor) < 0.03 and towers == 0 and asked == 3 and tower_top == pytest.approx(giant["towers"][1])
    assert wind == 90 and direction == 90                                                                # the wind blows along the bands
    worlds = out[1]
    assert all(n == 3 for _, n, _ in worlds) and worlds[2][0][2] > 3 * worlds[2][0][0] and worlds[0][0][0] > worlds[0][0][2]      # the ice giant blue, the gas giant tawny
    world, deep, own, height, own_height, ice, ice_own, equator, belt = out[2]
    assert world == "jupiter" and deep == pytest.approx([8 * x for x in own]) and height == own_height and ice == pytest.approx([8 / 3 * x for x in ice_own])
    assert equator != belt


PAGE = """
import * as THREE from "three";
import {air, sunDirection} from "vidgen/space-air";
import {clouds, giantSky, giantAir} from "vidgen/space-clouds";
let renderer, scene, camera, c, made = [];
export function load(ctx) {
  c = ctx.data;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  renderer.debug.onShaderError = (gl, program, vs, fs) => { window.shaderError = (gl.getShaderInfoLog(fs) || "") + (gl.getShaderInfoLog(vs) || "") + (gl.getProgramInfoLog(program) || ""); };
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(60, ctx.width / ctx.height, 1, 1e8);
  for (const shot of c.shots) {
    const sky = air(renderer, shot.giant ? giantAir(shot.giant) : "earth", {});
    const weather = clouds(renderer, sky, shot.giant ? {...giantSky(shot.giant, {scale: sky.model.H}), seed: 4} : {seed: 4, ...shot.clouds});
    sky.object.visible = weather.object.visible = false; scene.add(sky.object, weather.object); made.push([sky, weather]);
  }
}
export function frame(t, ctx) {
  const n = Math.round(t * ctx.fps), shot = c.shots[n], [sky, weather] = made[n], pitch = shot.pitch * Math.PI / 180;
  made.forEach(([s, w], i) => { s.object.visible = w.object.visible = i === n; });
  camera.fov = shot.fov ?? 60; camera.updateProjectionMatrix();
  camera.position.set(0, shot.height, 0); camera.up.set(0, pitch < -1.5 ? 0 : 1, pitch < -1.5 ? -1 : 0); camera.lookAt(0, shot.height + Math.sin(pitch) * 1000, -Math.cos(pitch) * 1000); camera.updateMatrixWorld();
  sky.update(t, {camera, sun: sunDirection(shot.elevation, shot.azimuth ?? 0)}); weather.update(shot.time ?? 0, {camera});
  renderer.setRenderTarget(null); renderer.render(scene, camera);
}
"""
SEA_OF_CLOUD = {"clouds": {"sky": "overcast"}, "height": 8000, "pitch": -25, "elevation": 40, "azimuth": 150}
DOWN = {"height": 40000, "pitch": -90, "fov": 50, "elevation": 50, "azimuth": 90}
STORM = {"clouds": {"decks": ["stratus"], "towers": {"at": [[0, -14000]], "radius": 4000}, "lightning": {"times": [1.0]}}, "height": 5000, "pitch": 5, "elevation": -4, "azimuth": 180}
SHOTS = [
    {**SEA_OF_CLOUD},                                                                     # 0 a cloud sea from above at noon
    {**SEA_OF_CLOUD, "elevation": 3, "azimuth": 150},                                     # 1 the same at sunset
    {**SEA_OF_CLOUD},                                                                     # 2 the first again
    {"clouds": {"sky": "overcast"}, "height": 300, "pitch": 35, "elevation": 40, "azimuth": 150},   # 3 the same deck from below
    {**DOWN, "clouds": {"decks": [{"type": "cumulus", "cover": 0.25}]}},                  # 4, 5 straight down on little and much cumulus
    {**DOWN, "clouds": {"decks": [{"type": "cumulus", "cover": 0.75}]}},
    {**STORM, "time": 1.02},                                                              # 6 a flash in a tower at dusk
    {**STORM, "time": 0.5},                                                               # 7 the same tower before it
    {"giant": "jupiter", "height": 125000, "pitch": -20, "elevation": 40, "azimuth": 120},   # 8 a giant's decks
    {**SEA_OF_CLOUD, "clouds": {"sky": "overcast", "quality": "fast"}},                   # 9 the first, cheaper
]


@pytest.mark.slow
@pytest.mark.render
def test_the_clouds_draw_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "clouds.js").write_text(PAGE, encoding="utf-8")
    store = B.BakedStore(tmp_path / "baked", 10**9)

    def draw(baked: B.BakedStore | bool) -> tuple[list[np.ndarray], list]:
        with WebPage(tmp_path, WebEntry("script", "clouds.js"), scene_id="s", size=(160, 90), fps=10, frames=len(SHOTS), data={"shots": SHOTS}, baked=baked) as page:
            frames = [page.frame(n)[..., :3].astype(int) for n in range(len(SHOTS))]
            error = page._page.evaluate("window.shaderError ?? null")
            assert error is None, error
            return frames, sorted({(what, name) for what, name, _ in page.baked_log})

    frames, log = draw(False)
    noon, sunset, again, below, little, much, flash, dark, giant, fast = frames
    assert log == []
    assert np.array_equal(noon, again) and not np.array_equal(noon, sunset)                                          # a frame is a function of its inputs
    top, base = noon[40:].mean(axis=(0, 1)), below[:50].mean(axis=(0, 1))
    assert top.sum() > 540 and top.sum() > 1.5 * base.sum() and base.min() > 15                                       # tops bright, bases grey: not white, not black
    assert noon[40:].std() > 2 and abs(top[0] - top[2]) < 25                                                          # a top with relief, white by day
    warm = sunset[40:].mean(axis=(0, 1))
    assert warm[0] / warm[2] > 1.25 * top[0] / top[2] and warm[0] > warm[1] > warm[2]                                 # a sunset's tops are warmer than noon's
    white = [float((shot.min(axis=2) > 150).mean()) for shot in (little, much)]
    assert white[0] == pytest.approx(0.25, abs=0.15) and white[1] == pytest.approx(0.75, abs=0.15) and white[1] > white[0] + 0.3   # roughly the cover asked for
    assert flash.mean() > dark.mean() + 4 and flash.max() > dark.max() + 40                                           # a flash lights the tower from within
    deck = giant[45:].mean(axis=(0, 1))
    assert deck[0] > deck[2] * 1.15 and deck.sum() > 150                                                              # a giant's tawny decks
    assert abs(fast[40:].mean() - noon[40:].mean()) < 12 and not np.array_equal(fast, noon)                           # cheaper, the same sky
    # the same pixels with the air's table baked and stored, from the cache, and without the cache (the clouds bake nothing themselves)
    cold, log = draw(store)
    assert log == [("stored", "space-air/psi")]
    warm_frames, log = draw(store)
    assert log == [("hit", "space-air/psi")]
    assert all(np.array_equal(a, b) and np.array_equal(a, w) for a, b, w in zip(frames, cold, warm_frames))
