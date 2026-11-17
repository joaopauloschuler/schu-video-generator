"""The cache of baked maps (Step 380, DESIGN.md §123.2): ``vidgen/baked`` is served by its import
name and the space modules bake through it; the key covers every input; the store writes entries
whole, finds a damaged one and removes it, evicts the least recently used above its limit, is
cleared and reported by ``vidgen cache``; ``WebPage`` answers the page's requests; in Node (when
it is installed): inflate reads Python's raw deflate at every level, half floats survive the read
back exactly, the planes are joined. In Chromium (``slow``): a planet, a sky and a float target of
a page's own draw the same pixels with the cache off, cold and warm, and a damaged entry or the
cache switched off bakes again without an error."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from vidgen.errors import VidgenError
from vidgen.web import baked as B
from vidgen.web.entry import WebEntry
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, vidgen_file
from vidgen.web.page import INIT_FILES, WebPage, engine_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = DATA / "web" / "modules"
MODULE = MODULES / "baked.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)
ASKED = {"name": "space-bodies/surface", "inputs": {"type": "rocky", "size": 64, "inputs": {"numbers": [0.5, 1.25], "colors": [[0.1, 0.2, 0.3]]}},
         "renderer": {"renderer": "ANGLE (SwiftShader)", "extensions": ["EXT_color_buffer_float"]},
         "parts": [{"target": 0, "face": f, "width": 64, "height": 64, "type": "u8", "bytes": 16384} for f in range(6)], "module": 1}


def test_the_module_is_served_and_the_space_modules_bake_through_it() -> None:
    assert VIDGEN_MODULES["vidgen/baked"] == "baked.js"
    assert IMPORT_MAP["imports"]["vidgen/baked"] == "/__vidgen__/modules/baked.js"
    assert vidgen_file("modules/baked.js") == MODULE
    source = MODULE.read_text(encoding="utf-8")
    assert STATIC_IMPORT.findall(source) == ["three"]
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source
    assert MODULE not in INIT_FILES and "baked" not in engine_id()
    for name, call in (("space-bodies.js", 'baked(renderer, "space-bodies/surface"'), ("space-sky.js", 'baked(renderer, "space-sky/cube"')):
        text = (MODULES / name).read_text(encoding="utf-8")
        assert 'import {baked} from "vidgen/baked";' in text and call in text


def test_the_limit_comes_from_the_environment() -> None:
    assert B.limit_bytes({}) == B.DEFAULT_LIMIT_MB * 1_000_000
    assert B.limit_bytes({B.LIMIT_ENV: "0"}) == 0 and B.limit_bytes({B.LIMIT_ENV: " 512 "}) == 512_000_000
    for bad in ("lots", "-1", "nan"):
        with pytest.raises(VidgenError, match=B.LIMIT_ENV):
            B.limit_bytes({B.LIMIT_ENV: bad})
    os.environ[B.LIMIT_ENV] = "0"        # the tests' own setting (conftest): pages keep nothing
    assert B.default_store() is None


def test_the_key_covers_every_input(monkeypatch: pytest.MonkeyPatch) -> None:
    key = B.bake_key(ASKED, "engine")
    assert re.fullmatch(r"[0-9a-f]{64}", key) and B.bake_key(json.loads(json.dumps(ASKED)), "engine") == key
    reordered = {k: ASKED[k] for k in reversed(list(ASKED))}
    assert B.bake_key(reordered, "engine") == key                                        # the order of a JSON object's keys is no input
    changed = [B.bake_key({**ASKED, "name": "space-sky/cube"}, "engine"), B.bake_key(ASKED, "another Chromium"),
               B.bake_key({**ASKED, "inputs": {**ASKED["inputs"], "size": 128}}, "engine"),
               B.bake_key({**ASKED, "inputs": {**ASKED["inputs"], "inputs": {"numbers": [0.5, 1.2500001], "colors": [[0.1, 0.2, 0.3]]}}}, "engine"),
               B.bake_key({**ASKED, "renderer": {**ASKED["renderer"], "extensions": []}}, "engine"),
               B.bake_key({**ASKED, "parts": [{**p, "type": "f16", "bytes": 32768} for p in ASKED["parts"]]}, "engine"),
               B.bake_key({**ASKED, "module": 2}, "engine")]
    monkeypatch.setattr(B, "code_digest", lambda: "another version of vidgen's modules")
    changed.append(B.bake_key(ASKED, "engine"))
    assert len({key, *changed}) == len(changed) + 1


def test_the_code_digest_covers_every_module_and_three() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", B.code_digest())
    source = Path(B.__file__).read_text(encoding="utf-8")
    assert '(_DATA / "web" / "modules").glob("*.js")' in source and '"three.module.js", "three.core.js"' in source


def test_part_sizes_are_checked() -> None:
    assert B.part_sizes(ASKED) == [(16384, 1)] * 6
    assert B.part_sizes({"parts": [{"bytes": 32768, "type": "f16"}, {"bytes": 64, "type": "f32"}]}) == [(32768, 2), (64, 4)]
    for bad in ({}, {"parts": []}, {"parts": [{"bytes": 0, "type": "u8"}]}, {"parts": [{"bytes": 10, "type": "f64"}]},
                {"parts": [{"bytes": 3, "type": "f16"}]}, {"parts": [{"bytes": B.MAX_PART_BYTES + 4, "type": "u8"}]}, {"parts": ["x"]}):
        assert B.part_sizes(bad) is None


def _stored(store: B.BakedStore, key: str, parts: list[bytes], width: int = 1, meta: dict | None = None) -> bool:
    folder = store.staging(key)
    for n, data in enumerate(parts):
        assert B.write_part(B.part_file(folder, n), [data[:7], data[7:]], width) == len(data)
    return store.commit(key, folder, [len(p) for p in parts], meta or {"mipmaps": [True]})


def test_an_entry_is_stored_whole_and_read_back(tmp_path: Path) -> None:
    store, key = B.BakedStore(tmp_path / "baked", 10**9), "a" * 64
    rng = np.random.default_rng(1)
    halves = rng.normal(size=4096).astype(np.float16).tobytes()
    assert _stored(store, key, [halves, bytes(1000)], width=2)
    found = store.checked(key, [len(halves), 1000])
    assert found is not None and found.sizes == (len(halves), 1000) and found.meta == {"mipmaps": [True]}
    packed = zlib.decompress(found.part(0).read_bytes(), -15)
    assert packed == B.planes(halves, 2) and packed[:4096] == halves[0::2] and packed[4096:] == halves[1::2]
    assert zlib.decompress(found.part(1).read_bytes(), -15) == bytes(1000)
    assert found.bytes == sum(p.stat().st_size for p in found.folder.glob("*.z")) and found.bytes < len(halves) + 1000
    assert store.checked(key, [len(halves), 999]) is None and store.entry(key) is None   # asked with other sizes: dropped, baked again
    assert not (tmp_path / "baked" / ".staging").exists() or not any((tmp_path / "baked" / ".staging").iterdir())


def test_a_damaged_entry_is_removed(tmp_path: Path) -> None:
    store = B.BakedStore(tmp_path, 10**9)
    for key, damage in (("b" * 64, "flip"), ("c" * 64, "cut"), ("d" * 64, "meta")):
        assert _stored(store, key, [bytes(range(256)) * 64])
        part = store.entry(key).part(0)
        data = bytearray(part.read_bytes())
        if damage == "flip":
            data[len(data) // 2] ^= 0x40
            part.write_bytes(bytes(data))
        elif damage == "cut":
            part.write_bytes(bytes(data[:-3]))
        else:
            (store.root / key / "meta.json").write_text("{not json", encoding="utf-8")
        assert store.checked(key, [16384]) is None
        assert damage != "flip" or not (store.root / key).exists()                # a wrong hash removes the entry
    assert store.usage().entries == 0


def test_the_second_of_two_pages_storing_one_key_loses(tmp_path: Path) -> None:
    store, key = B.BakedStore(tmp_path, 10**9), "e" * 64
    first, second = store.staging(key), store.staging(key)
    for folder, byte in ((first, b"\x01"), (second, b"\x02")):
        B.write_part(B.part_file(folder, 0), [byte * 100])
    assert store.commit(key, first, [100], {})
    assert not store.commit(key, second, [100], {}) and not second.exists()
    assert zlib.decompress(store.entry(key).part(0).read_bytes(), -15) == b"\x01" * 100


def test_eviction_keeps_the_most_recently_used(tmp_path: Path) -> None:
    rng = np.random.default_rng(2)
    noise = [rng.integers(0, 256, 20000, dtype=np.uint8).tobytes() for _ in range(4)]   # does not compress: each about 20 kB on disk
    store = B.BakedStore(tmp_path, 10**9)
    keys = [c * 64 for c in "0123"]
    for n, key in enumerate(keys[:3]):
        assert _stored(store, key, [noise[n]])
        os.utime(store.root / key / "meta.json", (time.time() - 100 + n, time.time() - 100 + n))
    assert store.checked(keys[0], [20000]) is not None                                   # used now: the newest
    store.limit = 65_000
    assert _stored(store, keys[3], [noise[3]])
    assert {e.folder.name for e in store._entries()} == {keys[0], keys[2], keys[3]}       # the oldest unused one went
    stale = store.root / ".staging" / "x"
    stale.mkdir()
    os.utime(stale, (time.time() - 2 * B.STALE_STAGING_S, time.time() - 2 * B.STALE_STAGING_S))
    store.evict()
    assert not stale.exists()
    assert not store.has_room(65_001) and store.has_room(1000)


def test_clear_removes_everything_and_vidgen_cache_reports_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from vidgen.cli import main

    monkeypatch.setenv("VIDGEN_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv(B.LIMIT_ENV, "300")
    store = B.BakedStore(B.baked_dir(), B.limit_bytes())
    assert store.root == tmp_path / "baked"
    for key in ("f" * 64, "9" * 64):
        assert _stored(store, key, [b"\x07" * 5000])
    (tmp_path / "soundfonts").mkdir()
    (tmp_path / "soundfonts" / "x.sf2").write_bytes(b"x" * 3000)
    assert main(["cache"]) == 0
    out = capsys.readouterr().out
    assert f"vidgen's cache folder: {tmp_path}" in out and "baked maps: 2 (" in out and "limit 300 MB (VIDGEN_BAKED_CACHE_MB)" in out
    assert "soundfonts/: 3 KB (kept by `vidgen soundfont`)" in out
    assert main(["cache", "clear"]) == 0
    assert "removed 2 baked maps" in capsys.readouterr().out and store.usage().entries == 0 and (tmp_path / "soundfonts" / "x.sf2").exists()
    monkeypatch.setenv(B.LIMIT_ENV, "0")
    assert main(["cache", "info"]) == 0 and "baked maps: 0 (0 KB), off (VIDGEN_BAKED_CACHE_MB=0)" in capsys.readouterr().out


class _Route:
    """What ``WebPage._serve`` reads of a Playwright route, and what it answered."""

    def __init__(self, path: str, method: str = "GET", body: object = None) -> None:
        self.request = SimpleNamespace(url=f"http://vidgen-web.invalid/{path}", method=method, headers={},
                                       post_data=None if body is None else json.dumps(body))
        self.answer: dict = {}

    def fulfill(self, **answer: object) -> None:
        self.answer = answer

    def json(self) -> dict:
        return json.loads(self.answer["body"])


def test_the_page_asks_and_hands_over_through_webpage(tmp_path: Path) -> None:
    store = B.BakedStore(tmp_path / "baked", 10**9)
    page = WebPage(tmp_path, WebEntry("script", "x.js"), scene_id="s", size=(64, 36), fps=1, frames=1, baked=store)
    off = WebPage(tmp_path, WebEntry("script", "x.js"), scene_id="s", size=(64, 36), fps=1, frames=1)   # VIDGEN_BAKED_CACHE_MB=0 in the tests

    def serve(p: WebPage, path: str, method: str = "GET", body: object = None) -> _Route:
        route = _Route(f"__vidgen__/baked/{path}", method, body)
        p._serve(route)
        return route

    assert off.baked is None and serve(off, "status").json() == {"on": False} and serve(off, "lookup", "POST", ASKED).answer["status"] == 404
    assert serve(page, "status").json() == {"on": True}
    miss = serve(page, "lookup", "POST", ASKED).json()
    assert miss["found"] is False and miss["key"] == B.bake_key(ASKED, engine_id())
    key = miss["key"]
    assert serve(page, f"{key}/ready", "POST", {"parts": [16384] * 6, "meta": {"mipmaps": [True]}}).answer["status"] == 204
    assert page._baked_ready == {key: {"mipmaps": [True]}} and page._baked_asked[key] == ("space-bodies/surface", [16384] * 6, [1] * 6)
    assert serve(page, f"{key}/0").answer["status"] == 404                                   # nothing stored yet
    assert _stored(store, key, [bytes([f]) * 16384 for f in range(6)])
    hit = serve(page, "lookup", "POST", ASKED).json()
    assert hit == {"key": key, "found": True, "meta": {"mipmaps": [True]}} and page.baked_log[-1] == ("hit", "space-bodies/surface", 6 * 16384)
    part = serve(page, f"{key}/5").answer
    assert part["status"] == 200 and zlib.decompress(Path(part["path"]).read_bytes(), -15) == b"\x05" * 16384
    for bad in (f"{key}/6", f"{key}/x", "0" * 64 + "/0", "nonsense"):
        assert serve(page, bad).answer["status"] == 404
    assert serve(page, "lookup", "POST", {"parts": []}).answer["status"] == 404
    assert not page.loaded                                                                    # never a loaded file: no scene's key changes
    full = WebPage(tmp_path, WebEntry("script", "x.js"), scene_id="s", size=(64, 36), fps=1, frames=1, baked=B.BakedStore(tmp_path / "small", 1000))
    assert serve(full, "lookup", "POST", ASKED).json()["key"] is None and full.baked_log == [("baked", "space-bodies/surface", 6 * 16384)]


def _run_in_node(tmp_path: Path, body: str) -> list:
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
    (ours / "baked.js").symlink_to(MODULE)
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {"./baked": "./baked.js"}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import fs from 'fs';\nimport * as THREE from 'three';\nimport * as K from 'vidgen/baked';\nconst out = [];\n"
        "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_inflate_halves_and_planes_in_node(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    halves = rng.normal(scale=3, size=30000).astype(np.float16).tobytes()
    samples = {"noise": rng.integers(0, 256, 70000, dtype=np.uint8).tobytes(), "zeros": bytes(300000), "text": b"vidgen bakes once. " * 9000,
               "mixed": rng.integers(0, 256, 40000, dtype=np.uint8).tobytes() + bytes(50000) + b"abc" * 20000, "one": b"q", "planes": B.planes(halves, 2)}
    cases = []
    for name, data in samples.items():
        for level in (0, 1, 6, 9):
            packer = zlib.compressobj(level, zlib.DEFLATED, -15)
            (tmp_path / f"{name}-{level}.z").write_bytes(packer.compress(data) + packer.flush())
            (tmp_path / f"{name}.raw").write_bytes(data)
            cases.append([f"{name}-{level}.z", f"{name}.raw"])
    (tmp_path / "halves.raw").write_bytes(halves)
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    out = _run_in_node(tmp_path, """
const read = (f) => new Uint8Array(fs.readFileSync(f));
const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
out.push(JSON.parse(fs.readFileSync('cases.json', 'utf8')).filter(([z, raw]) => !same(K.inflate(read(z), new Uint8Array(read(raw).length)), read(raw))));
const planes = read('planes-1.z'), halves = read('halves.raw');
out.push(same(K.joinPlanes(K.inflate(planes, new Uint8Array(halves.length)), 2), halves));
const good = read('text-6.z'), cut = good.slice(0, good.length - 9), wrong = good.slice(); wrong[40] ^= 0xff;
out.push([err(() => K.inflate(cut, new Uint8Array(19 * 9000))) !== null, err(() => K.inflate(wrong, new Uint8Array(19 * 9000))) !== null || !same(K.inflate(wrong, new Uint8Array(19 * 9000)), read('text.raw')),
  err(() => K.inflate(good, new Uint8Array(19 * 9000 + 1))) !== null]);
const f16 = (h) => { const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 31, m = h & 1023; return e === 0 ? s * m * 2 ** -24 : e === 31 ? (m ? NaN : s * Infinity) : s * (1 + m / 1024) * 2 ** (e - 15); };
let wrongHalves = 0; for (let h = 0; h < 65536; h++) { if (((h >> 10) & 31) === 31 && (h & 1023)) continue; if (K.halfBits(f16(h)) !== h) wrongHalves++; }
out.push(wrongHalves, [K.halfBits(65520), K.halfBits(1e-9), K.halfBits(-0), K.halfBits(NaN) & 0x7e00]);
const cube = new THREE.WebGLCubeRenderTarget(8, {type: THREE.HalfFloatType}), flat = new THREE.WebGLRenderTarget(4, 2, {type: THREE.FloatType});
out.push(K.layout([cube, null, flat]), K.layout([new THREE.WebGLRenderTarget(4, 4, {format: THREE.RedFormat})]), K.layout([new THREE.WebGLRenderTarget(4, 4, {samples: 4})]));
out.push(K.baked(null, 'x', {}, {targets: () => [flat], draw: ([t]) => { t.texture.userData.drawn = true; }})[0].texture.userData.drawn);   // no vidgen here: it bakes
""")
    assert out[0] == [] and out[1] is True and out[2] == [True, True, True]
    assert out[3] == 0 and out[4] == [0x7c00, 0, 0x8000, 0x7e00]
    assert len(out[5]) == 7 and out[5][0] == {"target": 0, "face": 0, "width": 8, "height": 8, "type": "f16", "bytes": 512}
    assert out[5][6] == {"target": 2, "face": 0, "width": 4, "height": 2, "type": "f32", "bytes": 128} and out[6] is None and out[7] is None
    assert out[8] is True


PAGE = """
import * as THREE from "three";
import {planet} from "vidgen/space-bodies";
import {spaceSky} from "vidgen/space-sky";
import {baked} from "vidgen/baked";
let renderer, scene, camera, own;
export function load(ctx) {
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(30, ctx.width / ctx.height, 0.01, 1000);
  scene.add(spaceSky(renderer, {seed: 3, size: 64}).object);
  const body = planet(renderer, "earth", {size: 64}); body.update(0, {sun: [1, 0.3, 0.6]}); scene.add(body.object);
  // a page's own bake: a float target with a gradient no 8-bit or half-float value holds
  [own] = baked(renderer, "test/gradient", {version: 1}, {
    targets: () => [new THREE.WebGLRenderTarget(16, 8, {type: THREE.FloatType, depthBuffer: false})],
    draw: ([t]) => { const q = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({vertexShader: "varying vec2 v; void main() { v = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: "varying vec2 v; void main() { gl_FragColor = vec4(v.x / 3.0, v.y * 1000.0, 1.0 / (1.0 + v.x * 7.0), 0.123456789); }"}));
      const s = new THREE.Scene(); s.add(q); renderer.setRenderTarget(t); renderer.render(s, new THREE.Camera()); renderer.setRenderTarget(null); window.drew = (window.drew ?? 0) + 1; },
  });
  const f = new Float32Array(16 * 8 * 4); renderer.readRenderTargetPixels(own, 0, 0, 16, 8, f); window.own = Array.from(f);
}
export function frame() {
  camera.position.set(0, 0, 5); camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
  renderer.setRenderTarget(null); renderer.render(scene, camera);
}
"""


@pytest.mark.slow
def test_pixels_are_the_same_cold_warm_and_without_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("playwright.sync_api")
    from vidgen.browser import chromium

    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    (tmp_path / "page.js").write_text(PAGE, encoding="utf-8")
    store = B.BakedStore(tmp_path / "baked", 10**9)

    def draw(baked: B.BakedStore | bool) -> tuple[np.ndarray, list, list, int]:
        with WebPage(tmp_path, WebEntry("script", "page.js"), scene_id="s", size=(160, 90), fps=10, frames=1, baked=baked) as page:
            picture = page.frame(0)
            own, drew = page._page.evaluate("[window.own, window.drew ?? 0]")
            return picture, own, sorted(page.baked_log), drew

    names = ["space-bodies/surface", "space-sky/cube", "test/gradient"]
    off, own_off, log, drew = draw(False)
    assert log == [] and drew == 1 and not (tmp_path / "baked").exists()
    cold, own_cold, log, drew = draw(store)
    assert [(what, name) for what, name, _ in log] == [("stored", n) for n in names] and drew == 1
    warm, own_warm, log, drew = draw(store)
    assert [(what, name) for what, name, _ in log] == [("hit", n) for n in names] and drew == 0
    assert np.array_equal(off, cold) and np.array_equal(off, warm) and off[..., :3].std() > 5
    assert own_off == own_cold == own_warm and len(set(own_off)) > 30
    # a damaged part: the page bakes that map again (no error) and stores it anew; the others still come from the cache
    body = next(e for e in store._entries() if len(e.sizes) == 12)
    data = bytearray(body.part(3).read_bytes())
    data[len(data) // 2] ^= 0x10
    body.part(3).write_bytes(bytes(data))
    again, _, log, _ = draw(store)
    assert sorted((what, name) for what, name, _ in log) == [("hit", "space-sky/cube"), ("hit", "test/gradient"), ("stored", "space-bodies/surface")]
    assert np.array_equal(off, again)
    # a part the page cannot inflate (here past vidgen's own check of its hash): the page says so, bakes, and the map is kept anew
    class Trusting(B.BakedStore):
        def checked(self, key: str, sizes: list[int]) -> B.Entry | None:
            return self.entry(key)

    sky = next(e for e in store._entries() if len(e.sizes) == 6)
    sky.part(2).write_bytes(bytes(sky.part(2).stat().st_size))
    trusting = Trusting(store.root, store.limit)
    again, _, log, _ = draw(trusting)
    assert ("damaged", "space-sky/cube") in [(what, name) for what, name, _ in log] and ("stored", "space-sky/cube") in [(what, name) for what, name, _ in log]
    assert np.array_equal(off, again) and store.checked(sky.folder.name, list(sky.sizes)) is not None
    # switched off by the environment: nothing read or written, the same pixels
    monkeypatch.setenv(B.LIMIT_ENV, "0")
    before = sorted(p.name for p in (tmp_path / "baked").iterdir())
    plain, _, log, drew = draw(True)
    assert log == [] and drew == 1 and np.array_equal(off, plain) and sorted(p.name for p in (tmp_path / "baked").iterdir()) == before
