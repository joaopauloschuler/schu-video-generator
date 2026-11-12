"""The three.js add-ons shipped for ``web`` scenes (Step 334, DESIGN.md §118.14): the shipped
files match the manifest and are the npm package's own, every static import of an add-on is a
shipped file or ``three``, the import map has both prefixes, an unshipped add-on gets a clear
message; in Chromium (``slow``): every shipped add-on imports, on one core module."""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path

import pytest

from vidgen.browser import chromium
from vidgen.errors import VidgenError
from vidgen.web.entry import WebEntry
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import ADDONS_FOLDER, THREE_ADDONS, THREE_VERSION, served_file, unshipped_addon, vidgen_file
from vidgen.web.page import WebPage, unshipped_addon_message

THREE_DIR = Path(__file__).resolve().parent.parent / "src" / "vidgen" / "data" / "three"
ADDONS_DIR = THREE_DIR / ADDONS_FOLDER
#: A static ``import``/``export … from`` at the start of a line (the add-ons' JSDoc examples are
#: inside comments, after `` * ``, so they are not matched).
STATIC_IMPORT = re.compile(r"^(?:import|export)\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]|^import\s*['\"]([^'\"]+)['\"]", re.M | re.S)
#: Left out on purpose (DESIGN.md §118.14): no shipped add-on may import one of these.
LEFT_OUT = ("FontLoader", "TextGeometry", "DRACOLoader", "KTX2Loader", "meshopt", "RGBELoader", "EXRLoader", "HDRLoader", "webgpu", "nodes/")


def test_the_shipped_files_are_the_manifest() -> None:
    shipped = sorted(p.relative_to(ADDONS_DIR).as_posix() for p in ADDONS_DIR.rglob("*") if p.is_file())
    assert shipped == sorted([*THREE_ADDONS, "LICENSE"])
    assert (ADDONS_DIR / "LICENSE").read_bytes() == (THREE_DIR / "LICENSE").read_bytes()
    assert sum((ADDONS_DIR / rel).stat().st_size for rel in THREE_ADDONS) < 1_000_000
    assert THREE_VERSION == "0.186.1" and "const REVISION = '186';" in (THREE_DIR / "three.core.js").read_text(encoding="utf-8")


def test_every_static_import_of_an_add_on_is_shipped() -> None:
    for rel in THREE_ADDONS:
        text = (ADDONS_DIR / rel).read_text(encoding="utf-8")
        specs = [a or b for a, b in STATIC_IMPORT.findall(text)]
        if rel == "loaders/GLTFLoader.js":
            assert specs == ["three", "../utils/BufferGeometryUtils.js", "../utils/SkeletonUtils.js"]
        for spec in specs:
            if spec == "three":
                continue
            assert spec.startswith("."), f"{rel} imports {spec}"
            target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
            assert target in THREE_ADDONS, f"{rel} imports {target}, which is not shipped"
            assert not any(word in target for word in LEFT_OUT)
        assert "import(" not in text.replace("import()", ""), rel


def test_the_import_map_has_both_prefixes_and_one_core() -> None:
    imports = IMPORT_MAP["imports"]
    assert imports == {"three": "/__vidgen__/three/three.module.js", "three/addons/": "/__vidgen__/three/addons/",
                       "three/examples/jsm/": "/__vidgen__/three/addons/"}
    assert json.loads(json.dumps(IMPORT_MAP)) == IMPORT_MAP


def test_only_shipped_add_ons_are_served() -> None:
    assert vidgen_file("three/addons/loaders/GLTFLoader.js") == ADDONS_DIR / "loaders" / "GLTFLoader.js"
    assert served_file(Path("/p"), "__vidgen__/three/addons/lines/Line2.js").is_file()
    for rel in ("three/addons/loaders/DRACOLoader.js", "three/loaders/GLTFLoader.js", "three/addons/LICENSE",
                "three/addons/../three.core.js", "three/addons/loaders/../loaders/GLTFLoader.js"):
        assert vidgen_file(rel) is None, rel
    assert unshipped_addon("__vidgen__/three/addons/loaders/DRACOLoader.js") == "loaders/DRACOLoader.js"
    assert unshipped_addon("__vidgen__/three/addons/loaders/GLTFLoader.js") is None
    assert unshipped_addon("extensions/x.js") is None


def test_the_unshipped_add_on_message() -> None:
    message = unshipped_addon_message("w", "loaders/DRACOLoader.js")
    assert message.startswith("scene 'w': the page imports the three.js add-on 'loaders/DRACOLoader.js' "
                              "(three/addons/loaders/DRACOLoader.js), which is not shipped with vidgen")
    assert "three.js 0.186.1" in message and "examples/jsm/loaders/DRACOLoader.js" in message
    assert "extensions/lib/DRACOLoader.js" in message and "'./lib/DRACOLoader.js'" in message


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")


@pytest.mark.slow
@pytest.mark.render
def test_every_shipped_add_on_imports_in_chromium(tmp_path: Path) -> None:
    _chromium_or_skip()
    entry_points = THREE_ADDONS
    lines = ["import * as THREE from 'three';"]
    lines += [f"import * as m{i} from 'three/addons/{rel}';" for i, rel in enumerate(entry_points)]
    lines.append("import * as old from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';")
    exported = ", ".join(f"m{i}" for i in range(len(entry_points)))
    lines.append(f"const mods = [{exported}];")
    lines.append("window.result = {revision: THREE.REVISION, empty: mods.filter((m) => Object.keys(m).length === 0).length,"
                 " same: old.RoundedBoxGeometry === m2.RoundedBoxGeometry && new m2.RoundedBoxGeometry() instanceof THREE.BufferGeometry"
                 " && new m3.Line2() instanceof THREE.Mesh};")
    (tmp_path / "all.js").write_text("\n".join(lines) + "\nexport function frame() {}\n", encoding="utf-8")
    (tmp_path / "page.html").write_text("<!doctype html><script type=\"module\">import {OrbitControls} from 'three/addons/controls/OrbitControls.js';"
                                        " import * as THREE from 'three'; window.ok = new OrbitControls(new THREE.PerspectiveCamera()) !== null;</script>",
                                        encoding="utf-8")
    (tmp_path / "draco.js").write_text("import {DRACOLoader} from 'three/addons/loaders/DRACOLoader.js';\nexport function frame() {}\n",
                                       encoding="utf-8")
    assert THREE_ADDONS[2] == "geometries/RoundedBoxGeometry.js" and THREE_ADDONS[3] == "lines/Line2.js"
    with WebPage(tmp_path, WebEntry("script", "all.js"), scene_id="w", size=(64, 36), fps=5, frames=1) as page:
        page.frame(0)
        result = page._page.evaluate("window.result")
        loaded = set(page.loaded)
    assert result == {"revision": "186", "empty": 0, "same": True}
    assert {f"__vidgen__/three/addons/{rel}" for rel in THREE_ADDONS} <= loaded
    assert sorted(p for p in loaded if not p.startswith("__vidgen__/three/addons/")) == [
        "__vidgen__/three/three.core.js", "__vidgen__/three/three.module.js", "all.js"]
    with WebPage(tmp_path, WebEntry("page", "page.html"), scene_id="w", size=(64, 36), fps=5, frames=1) as page:
        assert page._page.evaluate("window.ok") is True
    with pytest.raises(VidgenError, match=r"^scene 'w': the page imports the three\.js add-on 'loaders/DRACOLoader\.js'"):
        WebPage(tmp_path, WebEntry("script", "draco.js"), scene_id="w", size=(64, 36), fps=5, frames=1).__enter__()


def test_the_guide_lists_the_add_ons_and_what_is_left_out() -> None:
    from vidgen.guide import find_topic

    text = find_topic("web").text
    helpers = {"postprocessing/Pass.js", "postprocessing/MaskPass.js", "shaders/CopyShader.js",
               "shaders/LuminosityHighPassShader.js", "shaders/OutputShader.js", "utils/SkeletonUtils.js"}
    for rel in THREE_ADDONS:
        if rel not in helpers:
            assert Path(rel).stem in text, rel
    for name in ("FontLoader", "TextGeometry", "DRACOLoader", "KTX2Loader", "Meshopt", "WebGPU"):
        assert name in text, name
