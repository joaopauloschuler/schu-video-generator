"""vidgen's finishing module for three.js ``web`` scenes, ``vidgen/three-finish`` (Step 350, DESIGN.md
§120.11): served by its import name, only through the import map, in the loaded-files record (so in
the cache keys) of a page that imports it and of no other; its options checked with a did-you-mean
(run in Node when it is installed); in Chromium (``slow``): two fresh pages draw the same frames, a
shutter of 0 is exactly no motion blur, the chain with every effect off equals ``renderer.render``
(one sRGB conversion), a misspelt option stops the render with its message."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen.browser import chromium
from vidgen.errors import VidgenError
from vidgen.web.entry import WebEntry
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import THREE_ADDONS, VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, WebPage, engine_id

DATA = Path(__file__).resolve().parent.parent / "src" / "vidgen" / "data"
MODULE = DATA / "web" / "modules" / "three-finish.js"
URL_PATH = "__vidgen__/modules/three-finish.js"
STATIC_IMPORT = re.compile(r"^import\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]", re.M | re.S)


def test_the_module_is_served_by_its_import_name_only() -> None:
    assert VIDGEN_MODULES["vidgen/three-finish"] == "three-finish.js"
    assert IMPORT_MAP["imports"]["vidgen/three-finish"] == f"/{URL_PATH}"
    assert vidgen_file("modules/three-finish.js") == MODULE and MODULE.is_file()
    assert vidgen_file("modules/other.js") is None and vidgen_file("modules/../modules/three-finish.js") is None
    assert MODULE.stat().st_size < 60_000


def test_the_module_imports_only_three_and_shipped_add_ons() -> None:
    imports = STATIC_IMPORT.findall(MODULE.read_text(encoding="utf-8"))
    assert imports and all(i == "three" or i.removeprefix("three/addons/") in THREE_ADDONS for i in imports), imports
    assert "Math.random" not in MODULE.read_text(encoding="utf-8")


def test_a_page_that_loads_it_has_it_in_its_record_and_other_pages_are_unchanged() -> None:
    sha = current_loaded(Path("."), [URL_PATH])[URL_PATH]
    assert sha is not None and len(sha) == 64
    assert MODULE not in INIT_FILES and "three-finish" not in engine_id()


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    return node


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import the module in Node (``three`` from vidgen's copy) and print ``body``'s value as JSON."""
    package = tmp_path / "node_modules" / "three"
    package.mkdir(parents=True)
    for name in ("three.module.js", "three.core.js"):
        (package / name).symlink_to(DATA / "three" / name)
    (package / "addons").symlink_to(DATA / "three" / "addons")
    (package / "package.json").write_text(json.dumps({"name": "three", "type": "module", "exports": {
        ".": "./three.module.js", "./addons/*": "./addons/*"}}), encoding="utf-8")
    (tmp_path / "finish.mjs").symlink_to(MODULE)
    (tmp_path / "t.mjs").write_text("import * as F from './finish.mjs';\nconst out = [];\n"
                                    "const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
                                    f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([_node(), "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=30, check=True)
    return json.loads(done.stdout)


def test_options_are_checked_and_filled_in(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const o = F.resolveOptions({});
out.push([o.toneMapping, o.encoding, o.bloom, o.dof, o.motionBlur, o.antialias, o.grain, o.vignette.amount]);
out.push(err(() => F.resolveOptions({blom: 1})));
out.push(err(() => F.resolveOptions({dof: {fstop: 2}})));
out.push(err(() => F.resolveOptions({toneMapping: "filmic"})));
out.push(err(() => F.resolveOptions({motionBlur: {samples: 4}})));
out.push(err(() => F.resolveOptions({motionBlur: {samples: 2.5}, update: () => 0})));
out.push(err(() => F.resolveOptions({grade: {gamma: [1, 0, 1]}})));
out.push(F.resolveOptions({bloom: 0.6, vignette: false, motionBlur: true, update: () => 0}).bloom.strength);
out.push(F.resolveOptions({exposure: (t) => 1 + t}, 2).exposure);
out.push(F.resolveOptions({grade: {lift: 0.1, filter: "#ffffff"}}).grade.lift);
""")
    assert out[0] == ["aces", "srgb", {"strength": 0.25, "radius": 0.2, "threshold": 1, "scale": 0.5}, False, False, "fxaa", 0.02, 0.3]
    assert out[1].startswith('vidgen/three-finish: unknown option "blom" (did you mean "bloom"?)')
    assert 'unknown option dof."fstop" (did you mean "fStop"?)' in out[2]
    assert 'toneMapping must be one of "aces", "agx", "neutral", "aces-narkowicz", "none", got "filmic"' in out[3]
    assert "motionBlur needs update(t)" in out[4]
    assert "motionBlur.samples must be a whole number from 1 to 64, got 2.5" in out[5]
    assert "grade.gamma must be above 0" in out[6]
    assert out[7:] == [0.6, 3, [0.1, 0.1, 0.1]]


def test_shutter_times_are_centred_on_the_frame(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
out.push(F.shutterTimes(1, 30, 5, 180), F.shutterTimes(1, 30, 4, 360), F.shutterTimes(1, 30, 6, 0), F.shutterTimes(1, 30, 1, 180));
""")
    five, four, closed, one = out
    assert five[-1] == 1 and sorted(five) == pytest.approx([1 - 2 / 300, 1 - 1 / 300, 1, 1 + 1 / 300, 1 + 2 / 300])
    assert sorted(four) == pytest.approx([1 - 3 / 240, 1 - 1 / 240, 1 + 1 / 240, 1 + 3 / 240])
    assert closed == [1] and one == [1]


def test_the_sensor_is_off_unless_asked_and_on_when_given(tmp_path: Path) -> None:
    out = _run_in_node(tmp_path, """
const off = F.resolveOptions({});
out.push([off.noise.amount, off.range.stops, off.sharpen.amount]);
const on = F.resolveOptions({noise: true, range: true, sharpen: true});
out.push([on.noise, on.range, on.sharpen]);
out.push([F.resolveOptions({noise: {size: 2}}).noise.amount, F.resolveOptions({range: {black: 0.01}}).range.stops, F.resolveOptions({sharpen: 0.3}).sharpen.amount]);
out.push([F.resolveOptions({noise: false}).noise.amount, F.resolveOptions({range: 0}).range.stops, F.resolveOptions({noise: {amount: 0}}).noise.amount]);
out.push(err(() => F.resolveOptions({noise: {colour: 1}})), err(() => F.resolveOptions({range: 0.5})), err(() => F.resolveOptions({sharpen: {radius: 9}})));
""")
    assert out[0] == [0, 0, 0]
    assert out[1] == [{"amount": 0.012, "color": 0.5, "size": 1, "floor": 0.05}, {"stops": 2.5, "shoulder": 0.05, "black": 0},
                      {"amount": 0.5, "radius": 1, "limit": 0.06}]
    assert out[2] == [0.012, 2.5, 0.3] and out[3] == [0, 0, 0]
    assert 'unknown option noise."colour" (did you mean "color"?)' in out[4]
    assert "range.stops must be a number from 1 to 16, got 0.5" in out[5] and "sharpen.radius must be a number from 0.5 to 4, got 9" in out[6]


def test_the_sensor_curves(tmp_path: Path) -> None:
    """The JavaScript twins of the shaders' curves: the range keeps the shadows and mid tones, stretches the highlights
    to clip at the white with a soft shoulder, crushes the blacks; the noise is `amount` at mid grey once encoded,
    larger in the shadows than in the highlights, none where the picture clips, `floor` of it at black."""
    out = _run_in_node(tmp_path, """
const top = 0.77, vs = Array.from({length: 201}, (_, i) => i / 200);
out.push(vs.map((v) => F.rangeCurve(v, top, {shoulder: 0.05})), vs.map((v) => F.rangeCurve(v, top, {shoulder: 0.05, black: 0.02})));
out.push([F.rangeWhite(2.5), F.rangeCurve(0.5, 1, {shoulder: 0}), F.rangeCurve(1.2, 0.8, {shoulder: 0})]);
const enc = (x) => x <= 0.0031308 ? x * 12.92 : 1.055 * x ** (1 / 2.4) - 0.055, h = 1e-4;
const encoded = (v) => F.noiseSigma(v, 0.012, 0.05) * (enc(v + h) - enc(Math.max(v - h, 0))) / (v + h - Math.max(v - h, 0));
out.push([0.18, 0.02, 0.05, 0.5, 0.8, 0.95, 1].map(encoded));
out.push([F.noiseSigma(0, 0.012, 0.05) / Math.sqrt(F.noiseSigma(0.18, 0.012, 0.05) ** 2 / (1 - 0.18 ** 2) ** 2), F.noiseSpread(0.012, 0.05, "gamma2.2").scale]);
""")
    curve, crushed, (white, flat, clipped), noise, (floor, gamma) = out[0], out[1], out[2], out[3], out[4]
    assert all(b >= a for a, b in zip(curve, curve[1:])) and all(b >= a for a, b in zip(crushed, crushed[1:]))
    assert curve[:78] == pytest.approx([i / 200 for i in range(78)])          # below half the white: unchanged
    assert 0.98 < curve[154] < 1 and set(curve[162:]) == {1}                    # the white (0.77) at the shoulder; 5 % above it, clipped
    assert 0.95 < curve[150] < curve[154] and crushed[-1] == pytest.approx(1)
    assert crushed[2] < curve[2] * 0.5 and crushed[100] == pytest.approx(curve[100] ** 2 / (curve[100] + 0.02) * 1.02)
    assert white == pytest.approx(0.18 * 2 ** 2.5) and flat == 0.5 and clipped == 1
    mid, *rest, at_white = noise
    assert mid == pytest.approx(0.012, rel=1e-3) and at_white == 0
    assert rest[0] > rest[1] > mid > rest[2] > rest[3] > rest[4] > 0               # more in the shadows than in the highlights
    assert floor == pytest.approx(0.05) and gamma > 0


PAGE = """import * as THREE from "three";
import {Finish, studioEnvironment} from "vidgen/three-finish";
let renderer, scene, camera, finish, spin;
const update = (t) => { spin.rotation.z = t * 20; };
export function load(ctx) {
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x203040);
  scene.environment = studioEnvironment(renderer);
  camera = new THREE.PerspectiveCamera(40, ctx.width / ctx.height, 0.1, 50);
  camera.position.set(0, 0, 5);
  spin = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.3, 0.3), new THREE.MeshStandardMaterial({color: 0xd9a441, metalness: 1, roughness: 0.3}));
  const back = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 12), new THREE.MeshBasicMaterial({color: new THREE.Color(3, 2, 1)}));
  back.position.set(1.5, 0.5, -6);
  scene.add(spin, back);
  if (ctx.data.mode === "plain") return;
  finish = new Finish(renderer, scene, camera, ctx, {update, ...ctx.data.finish});
  finish.warmUp(0);
}
export function frame(t, ctx) {
  if (ctx.data.mode === "plain") { update(t); renderer.render(scene, camera); return; }
  finish.render(t);
}
"""
ALL = {"dof": {"focus": 5, "fStop": 1.4}, "motionBlur": {"samples": 4, "shutter": 180}, "fringe": 1, "grade": {"temperature": 0.3, "lift": 0.02}}
OFF = {"bloom": False, "toneMapping": "none", "vignette": 0, "grain": 0, "antialias": "none"}


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")


def _frames(root: Path, data: dict, frames: tuple[int, ...] = (3,)) -> tuple[list[np.ndarray], dict]:
    with WebPage(root, WebEntry("script", "finish.js"), scene_id="f", size=(160, 90), fps=10, frames=6, data=data) as page:
        pictures = [page.frame(n) for n in frames]
        return pictures, dict(page.loaded)


@pytest.mark.slow
@pytest.mark.render
def test_the_chain_draws_the_same_frames_every_time(tmp_path: Path) -> None:
    _chromium_or_skip()
    (tmp_path / "finish.js").write_text(PAGE, encoding="utf-8")
    first, loaded = _frames(tmp_path, {"finish": ALL})
    again, _ = _frames(tmp_path, {"finish": ALL})
    assert np.array_equal(first[0], again[0])
    assert loaded[URL_PATH] == current_loaded(tmp_path, [URL_PATH])[URL_PATH]
    assert "__vidgen__/three/addons/postprocessing/UnrealBloomPass.js" in loaded
    # a shutter of 0 draws once at t: exactly the picture without motion blur
    closed, _ = _frames(tmp_path, {"finish": {**ALL, "motionBlur": {"samples": 4, "shutter": 0}}})
    without, _ = _frames(tmp_path, {"finish": {**ALL, "motionBlur": False}})
    assert np.array_equal(closed[0], without[0]) and not np.array_equal(first[0], without[0])
    # every effect off: the picture renderer.render draws (linear half floats, sRGB encoded once)
    chain, _ = _frames(tmp_path, {"finish": OFF})
    plain, plain_loaded = _frames(tmp_path, {"mode": "plain"})
    assert np.abs(chain[0].astype(int) - plain[0].astype(int)).max() <= 1
    assert URL_PATH in plain_loaded   # imported by the page, so in its record


@pytest.mark.slow
@pytest.mark.render
def test_the_sensor_draws_the_same_frames_and_off_changes_nothing(tmp_path: Path) -> None:
    """Sensor noise, range and sharpening: two pages draw the same frames, the noise is new each frame, each
    effect changes the picture, and each one given as off draws exactly the picture without it."""
    _chromium_or_skip()
    (tmp_path / "finish.js").write_text(PAGE, encoding="utf-8")
    sensor = {**OFF, "noise": True, "range": {"stops": 1.5, "black": 0.02}, "sharpen": 1}
    first, _ = _frames(tmp_path, {"finish": sensor}, (3, 4))
    again, _ = _frames(tmp_path, {"finish": sensor}, (3, 4))
    assert np.array_equal(first[0], again[0]) and np.array_equal(first[1], again[1])
    plain, _ = _frames(tmp_path, {"finish": OFF}, (3, 4))
    assert not np.array_equal(first[0], plain[0])
    # the noise alone: new each frame (seeded by the frame number), the background the same on average
    noisy, _ = _frames(tmp_path, {"finish": {**OFF, "noise": 0.03}}, (3, 4))
    corner = (slice(0, 20), slice(0, 30), slice(0, 3))
    assert not np.array_equal(noisy[0][corner], noisy[1][corner]) and np.array_equal(plain[0][corner], plain[1][corner])
    # (noise added in linear light and encoded after darkens a dark background a little on average, as in a camera)
    assert abs(noisy[0][corner].astype(float).mean() - plain[0][corner].astype(float).mean()) < 3
    for look in ({"range": True}, {"sharpen": True}):
        changed, _ = _frames(tmp_path, {"finish": {**OFF, **look}})
        assert not np.array_equal(changed[0], plain[0]), look
    given_off, _ = _frames(tmp_path, {"finish": {**OFF, "noise": 0, "range": 0, "sharpen": 0}}, (3, 4))
    assert np.array_equal(given_off[0], plain[0]) and np.array_equal(given_off[1], plain[1])
    # with grain, FXAA, bloom and tone mapping on (the defaults), the sensor given as off changes nothing either
    defaults, _ = _frames(tmp_path, {"finish": {}})
    defaults_off, _ = _frames(tmp_path, {"finish": {"noise": False, "range": False, "sharpen": False}})
    assert np.array_equal(defaults[0], defaults_off[0])


@pytest.mark.slow
@pytest.mark.render
def test_a_misspelt_option_stops_the_render_with_its_message(tmp_path: Path) -> None:
    _chromium_or_skip()
    (tmp_path / "finish.js").write_text(PAGE, encoding="utf-8")
    with pytest.raises(VidgenError, match=r'unknown option "blom" \(did you mean "bloom"\?\)'):
        _frames(tmp_path, {"finish": {"blom": 1}})


def test_the_example_and_the_docs() -> None:
    """examples/three-finish: source only, it validates; the guide, CONFIG and the 3D cookbook teach the module."""
    from vidgen.cli import validate_all
    from vidgen.guide import find_topic
    from vidgen.project import Project

    root = Path(__file__).resolve().parent.parent
    example = root / "examples" / "three-finish"
    assert sorted(p.relative_to(example).as_posix() for p in example.rglob("*") if p.is_file()) == [
        "README.md", "extensions/still_life.js", "video.yaml"]
    problems, _ = validate_all(Project.load(example), keep_going=True)
    assert not problems, problems
    page = (example / "extensions" / "still_life.js").read_text(encoding="utf-8")
    assert 'from "vidgen/three-finish"' in page and "motionBlur" in page and "dof:" in page
    guide = find_topic("web").text
    assert "**Finishing three.js scenes: `vidgen/three-finish`.**" in guide and "extensions/finished.js" in guide
    assert "Finishing three.js scenes: `vidgen/three-finish`" in (root / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    assert "## 8. Finishing three.js `web` scenes" in (root / "docs" / "COOKBOOK-3D.md").read_text(encoding="utf-8")
    assert "examples/three-finish" in (root / "README.md").read_text(encoding="utf-8")
