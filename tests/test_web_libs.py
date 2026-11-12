"""The animation and chart libraries shipped for ``web`` scenes (Step 336, DESIGN.md §118.15):
the shipped files are the manifest's and the npm packages' own (SHA-256), each has its licence,
the import map names them, only manifest files are served, GSAP gets a clear message; in Chromium
(``slow``): each library moves with vidgen's clock and draws the same frames twice."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pytest

from vidgen.browser import chromium
from vidgen.errors import VidgenError
from vidgen.web.entry import WebEntry
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.libs import LIB_DIR, NOT_SHIPPED, WEB_LIBS, WRAPPER, lib_file, unshipped_lib_message
from vidgen.web.loaded import unshipped_lib, vidgen_file
from vidgen.web.page import WebPage

ROOT = Path(__file__).resolve().parent.parent
LIBS = {lib.package: lib for lib in WEB_LIBS}
#: The licence files beside each build: the package's own, and for a build that contains other
#: packages, theirs.
BUNDLED = "LICENSES-bundled.txt"
WITH_BUNDLED = {"motion", "d3", "chart.js"}
#: What the owner allowed for the shipped total (bytes).
SIZE_LIMIT = 1_500_000
#: A text each build carries that names its version.
VERSION_MARKS = {"animejs": "@version v4.5.0", "d3": "https://d3js.org v7.9.2", "chart.js": "Chart.js v4.6.1"}


def test_the_shipped_files_are_the_manifest_and_the_packages_own() -> None:
    assert sorted(p.name for p in LIB_DIR.iterdir()) == sorted(LIBS)
    total = 0
    for lib in WEB_LIBS:
        folder = LIB_DIR / lib.package
        expected = {*lib.files, "LICENSE"} | ({BUNDLED} if lib.package in WITH_BUNDLED else set())
        assert {p.name for p in folder.iterdir()} == expected, lib.package
        data = (folder / lib.file).read_bytes()
        assert hashlib.sha256(data).hexdigest() == lib.sha256 and len(data) == lib.size, lib.package
        if lib.package in VERSION_MARKS:
            assert VERSION_MARKS[lib.package].encode("utf-8") in data, lib.package
        total += sum(p.stat().st_size for p in folder.iterdir())
    assert total < SIZE_LIMIT


def test_every_library_has_its_licence_and_a_notice() -> None:
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for lib in WEB_LIBS:
        licence = (LIB_DIR / lib.package / "LICENSE").read_text(encoding="utf-8")
        assert "Permission" in licence and "Copyright" in licence, lib.package
        assert f"{lib.package} {lib.version}" in notices, lib.package
    assert "Mike Bostock" in (LIB_DIR / "d3" / "LICENSE").read_text(encoding="utf-8")
    bundled = (LIB_DIR / "d3" / BUNDLED).read_text(encoding="utf-8")
    assert all(name in bundled for name in ("d3-ease", "Robert Penner", "ColorBrewer", "delaunator", "robust-predicates"))
    assert "gsap" in notices.lower() and "not shipped" in notices


def test_the_import_map_names_every_library() -> None:
    imports = IMPORT_MAP["imports"]
    assert {name: url for name, url in imports.items() if not name.startswith("three")} == {
        "animejs": "/__vidgen__/libs/animejs/anime.esm.min.js",
        "motion": "/__vidgen__/libs/motion/index.js",
        "d3": "/__vidgen__/libs/d3/index.js",
        "chart.js": "/__vidgen__/libs/chart.js/index.js",
        "chart.js/auto": "/__vidgen__/libs/chart.js/index.js",
        "lottie-web": "/__vidgen__/libs/lottie-web/lottie.min.js",
        "gsap": "/__vidgen__/libs/gsap/index.js",
    }
    for name, url in imports.items():
        if name.startswith("three") or name in NOT_SHIPPED:
            continue
        assert vidgen_file(url.removeprefix("/__vidgen__/")).is_file(), name


def test_only_manifest_files_are_served() -> None:
    assert lib_file("d3/d3.min.js") == LIB_DIR / "d3" / "d3.min.js"
    assert vidgen_file("libs/chart.js/index.js") == LIB_DIR / "chart.js" / "index.js"
    for rel in ("libs/d3/LICENSE", "libs/d3/LICENSES-bundled.txt", "libs/d3/../motion/motion.js", "libs/animejs/index.js",
                "libs/gsap/index.js", "libs/d3", "libs/", "lib/d3/index.js"):
        assert vidgen_file(rel) is None, rel
    assert unshipped_lib("__vidgen__/libs/gsap/index.js") == "gsap"
    assert unshipped_lib("__vidgen__/libs/d3/index.js") is None and unshipped_lib("libs/gsap/index.js") is None


def test_a_umd_builds_wrapper_runs_it_and_exports_its_names() -> None:
    for lib in WEB_LIBS:
        if lib.global_name is None:
            assert lib.entry == lib.file and not (LIB_DIR / lib.package / WRAPPER).exists()
            continue
        text = (LIB_DIR / lib.package / WRAPPER).read_text(encoding="utf-8")
        assert f"import './{lib.file}';" in text and f"const lib = globalThis.{lib.global_name};" in text
        assert "export default lib;" in text and lib.version in text
        names = re.search(r"export const \{(.*?)\} = lib;", text, re.S).group(1).replace("\n", " ").split(",")  # type: ignore[union-attr]
        names = [name.strip() for name in names if name.strip()]
        assert len(names) == len(set(names)) > 10 and all(re.fullmatch(r"[A-Za-z_$][\w$]*", name) for name in names)
    assert "select," in (LIB_DIR / "d3" / WRAPPER).read_text(encoding="utf-8")


def test_the_message_for_gsap() -> None:
    message = unshipped_lib_message("w", "gsap")
    assert message.startswith("scene 'w': the page imports 'gsap', which is not shipped with vidgen. GSAP's licence")
    assert "All rights reserved" in message and "dist/gsap.min.js" in message and "gsap-core.js" in message


def test_web_pages_are_drawn_without_partial_raster() -> None:
    """With partial raster two renders of a Lottie SVG at half size differed in an edge pixel."""
    from vidgen.web.page import WEB_ARGS, engine_id

    assert "--disable-partial-raster" in WEB_ARGS and "--disable-partial-raster" in engine_id()


def test_the_guide_has_a_row_for_every_library() -> None:
    from vidgen.guide import find_topic

    text = find_topic("web").text
    for specifier in ('from "animejs"', 'from "motion"', 'from "d3"', 'from "chart.js/auto"', 'from "lottie-web"'):
        assert specifier in text, specifier
    for word in ("GSAP", "tl.time(t)", "goToAndStop", "lagSmoothing(0)", "simulation.tick"):
        assert word in text, word


# ----- in Chromium -----------------------------------------------------------------------------

BOX = ('<!doctype html><meta charset="utf-8"><style>html, body { margin: 0; background: #102030; } '
       ".box { position: absolute; left: 10px; width: 20px; height: 20px; background: #f84; } #a { top: 10px; } #b { top: 50px; }"
       '</style><div id="a" class="box"></div><div id="b" class="box"></div><div id="l" style="width:160px;height:90px"></div>'
       '<script type="module">const [a, b] = document.querySelectorAll(".box");'
       "const left = (e) => Math.round(e.getBoundingClientRect().left * 100) / 100;\n")
END = "\n</script>"
#: One 2 s move of 100 px (10 px per frame at 5 fps), the natural way (the library's own loop)
#: and, where there is one, the seek way (set from ``frame(t)``); ``probe`` gives what to compare.
PAGES: dict[str, str] = {
    "animejs": BOX + 'import { animate } from "animejs";\nanimate(a, { x: 100, duration: 2000, ease: "linear" });\n'
               'const held = animate(b, { x: 100, duration: 2000, ease: "linear", autoplay: false });\n'
               "window.vidgen = { frame(t) { held.seek(t * 1000); } };\nwindow.probe = () => [left(a), left(b)];" + END,
    "motion": BOX + 'import { animate } from "motion";\nanimate(a, { x: 100 }, { duration: 2, ease: "linear" });\n'
              'animate(0, 100, { duration: 2, ease: "linear", onUpdate: (v) => { b.style.left = `${10 + v}px`; } });\n'
              "window.probe = () => [left(a), left(b)];" + END,
    "d3": BOX + 'import * as d3 from "d3";\nd3.select(a).transition().duration(2000).ease(d3.easeLinear).style("left", "110px");\n'
          "const x = d3.scaleLinear().domain([0, 2]).range([10, 110]).clamp(true);\n"
          'window.vidgen = { frame(t) { d3.select(b).style("left", `${x(t)}px`); } };\n'
          "window.probe = () => [left(a), left(b)];\nwindow.names = [Object.keys(globalThis.d3).length, typeof d3.default.select];" + END,
    "chart.js": '<!doctype html><meta charset="utf-8"><style>html, body { margin: 0; background: #fff; }</style>'
                '<canvas id="c" width="160" height="90"></canvas><script type="module">import Chart from "chart.js/auto";\n'
                'import { Chart as Named, BarController } from "chart.js";\n'
                'const chart = new Chart(document.getElementById("c"), { type: "bar", data: { labels: ["a", "b"], '
                'datasets: [{ label: "v", data: [5, 10], backgroundColor: "#36c" }] }, '
                'options: { responsive: false, animation: { duration: 2000, easing: "linear" } } });\n'
                "const y = (i) => chart.getDatasetMeta(0).data[i].y;\n"
                "window.probe = () => [Math.round((y(0) - chart.scales.y.getPixelForValue(0)) * 100) / 100, Named === Chart && typeof BarController];" + END,
    "lottie-web": '<!doctype html><meta charset="utf-8"><style>html, body { margin: 0; background: #102030; } div { width: 160px; height: 45px; }'
                  '</style><div id="a"></div><div id="b"></div><script type="module">import lottie from "lottie-web";\n'
                  'const data = await (await fetch("box.json")).json();\n'
                  "const make = (id, autoplay) => lottie.loadAnimation({ container: document.getElementById(id), renderer: 'svg', loop: true, autoplay, animationData: data });\n"
                  "const played = make('a', true), held = make('b', false);\n"
                  "window.vidgen = { frame(t) { held.goToAndStop(t * 1000, false); } };\n"
                  "window.probe = () => [played.currentFrame, held.currentFrame];" + END,
}
#: A Lottie animation of 2 s at 10 frames per second: one square moving right.
LOTTIE_JSON = ('{"v":"5.7.4","fr":10,"ip":0,"op":20,"w":160,"h":90,"nm":"box","ddd":0,"assets":[],"layers":[{"ddd":0,"ind":1,"ty":4,'
               '"nm":"box","sr":1,"ks":{"o":{"a":0,"k":100},"r":{"a":0,"k":0},"p":{"a":1,"k":[{"t":0,"s":[20,45,0],"e":[140,45,0],'
               '"i":{"x":[1],"y":[1]},"o":{"x":[0],"y":[0]}},{"t":20,"s":[140,45,0]}]},"a":{"a":0,"k":[0,0,0]},"s":{"a":0,"k":[100,100,100]}},'
               '"ao":0,"shapes":[{"ty":"gr","it":[{"ty":"rc","d":1,"s":{"a":0,"k":[20,20]},"p":{"a":0,"k":[0,0]},"r":{"a":0,"k":0}},'
               '{"ty":"fl","c":{"a":0,"k":[1,0.3,0.1,1]},"o":{"a":0,"k":100},"r":1},{"ty":"tr","p":{"a":0,"k":[0,0]},"a":{"a":0,"k":[0,0]},'
               '"s":{"a":0,"k":[100,100]},"r":{"a":0,"k":0},"o":{"a":0,"k":100}}]}],"ip":0,"op":20,"st":0,"bm":0}]}')
#: The probe of frames 0, 1 and 2 (t = 0, 0.2, 0.4 s). anime.js's own loop runs about 12 ms ahead.
EXPECTED: dict[str, list[list[object]]] = {
    "animejs": [[10, 10], [20.6, 20], [30.6, 30]],
    "motion": [[10, 10], [20, 20], [30, 30]],
    "d3": [[10, 10], [20, 20], [30, 30]],
    "lottie-web": [[0, 0], [2, 2], [4, 4]],
}


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    if chromium.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")


def _run(root: Path, name: str) -> tuple[list[np.ndarray], list[object], set[str]]:
    with WebPage(root, WebEntry("page", name), scene_id="lib", size=(160, 90), fps=5, frames=3) as page:
        frames, probes = [], []
        for n in range(3):
            frames.append(page.frame(n))
            probes.append(page._page.evaluate("window.probe()"))
        return frames, probes, set(page.loaded)


@pytest.mark.slow
@pytest.mark.render
@pytest.mark.parametrize("package", sorted(PAGES))
def test_a_shipped_library_follows_vidgens_clock(tmp_path: Path, package: str) -> None:
    _chromium_or_skip()
    (tmp_path / "p.html").write_text(PAGES[package], encoding="utf-8")
    (tmp_path / "box.json").write_text(LOTTIE_JSON, encoding="utf-8")
    frames, probes, loaded = _run(tmp_path, "p.html")
    again, probes_again, _ = _run(tmp_path, "p.html")
    lib = LIBS[package]
    assert {f"__vidgen__/libs/{package}/{name}" for name in lib.files} <= loaded
    assert probes == probes_again and all(np.array_equal(a, b) for a, b in zip(frames, again))
    assert not np.array_equal(frames[0], frames[1]) and not np.array_equal(frames[1], frames[2])
    if package == "chart.js":   # the bar grows from the axis: a tenth of its height per frame
        heights = [-p[0] for p in probes]   # type: ignore[index]
        assert heights[0] == 0 and heights[1] > 1 and heights[2] == pytest.approx(2 * heights[1], abs=0.02)
        assert probes[0][1] == "function"   # type: ignore[index]
    else:
        assert probes == EXPECTED[package]


@pytest.mark.slow
@pytest.mark.render
def test_a_wrappers_names_are_the_umd_builds(tmp_path: Path) -> None:
    _chromium_or_skip()
    umd = [lib for lib in WEB_LIBS if lib.global_name is not None]
    imports = "".join(f'import * as m{i} from "{lib.specifiers[0]}";\n' for i, lib in enumerate(umd))
    checks = ", ".join(f"[Object.keys(m{i}).filter((k) => k !== 'default').sort().join(), Object.keys(globalThis.{lib.global_name}).sort().join(), "
                       f"m{i}.default === globalThis.{lib.global_name}]" for i, lib in enumerate(umd))
    (tmp_path / "n.js").write_text(f"{imports}window.result = [{checks}];\nexport function frame() {{}}\n", encoding="utf-8")
    (tmp_path / "g.js").write_text('import gsap from "gsap";\nexport function frame() {}\n', encoding="utf-8")
    with WebPage(tmp_path, WebEntry("script", "n.js"), scene_id="w", size=(64, 36), fps=5, frames=1) as page:
        result = page._page.evaluate("window.result")
    assert len(result) == 3
    for lib, (exported, own, same) in zip(umd, result):
        assert exported == own and same is True, lib.package
    with pytest.raises(VidgenError, match=r"^scene 'w': the page imports 'gsap', which is not shipped with vidgen\. GSAP's licence"):
        WebPage(tmp_path, WebEntry("script", "g.js"), scene_id="w", size=(64, 36), fps=5, frames=1).__enter__()
