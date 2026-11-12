"""The animation and chart libraries shipped for ``web`` scenes (DESIGN.md §118.15): each is one
build file of an npm package, copied unmodified into ``data/web/libs/<package>/`` with the
package's licence, and imported by the package's name through the page's import map. A package
whose only one-file build is UMD also has ``index.js``, written by vidgen: an ES module that runs
the UMD file and exports the names of the global it sets. No browser here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent.parent / "data" / "web" / "libs"
#: The folder of the shipped libraries after ``__vidgen__/``.
LIB_FOLDER = "libs"
#: vidgen's ES module beside a UMD build.
WRAPPER = "index.js"


@dataclass(frozen=True)
class WebLib:
    """One shipped library: the npm ``package`` and ``version``, the build ``file`` (its path in
    the package is ``source``) with its ``sha256`` and ``size`` in bytes, the import
    ``specifiers`` that name it, and ``global_name`` when the build is UMD (the global it sets)."""

    package: str
    version: str
    source: str
    file: str
    sha256: str
    size: int
    specifiers: tuple[str, ...]
    global_name: str | None = None

    @property
    def entry(self) -> str:
        """The file an import of the library loads: vidgen's wrapper of a UMD build, else the build."""
        return WRAPPER if self.global_name is not None else self.file

    @property
    def files(self) -> tuple[str, ...]:
        """The files a page may load from the library's folder."""
        return (self.file,) if self.global_name is None else (self.file, WRAPPER)


WEB_LIBS: tuple[WebLib, ...] = (
    WebLib("animejs", "4.5.0", "dist/bundles/anime.esm.min.js", "anime.esm.min.js",
           "a19015a1a92d52025a2fb6703b6d67eadd1cc2aeaf880770e96e04cf6aa07be1", 118_678, ("animejs",)),
    WebLib("motion", "14.12.0", "dist/motion.js", "motion.js",
           "a18fc08eb11c67658b34270bb71bc4ba806c87dbc1b720d7acd38c437844eee7", 188_678, ("motion",), "Motion"),
    WebLib("d3", "7.9.2", "dist/d3.min.js", "d3.min.js",
           "912111098ea99503a6f4967361d2bbdc9dbf58cf9c678c8e27e5b02d1a07f0c1", 280_622, ("d3",), "d3"),
    WebLib("chart.js", "4.6.1", "dist/chart.umd.min.js", "chart.umd.min.js",
           "87364cc2b2a76a6684929e7d6b80b18a897794db38400caff1fcf1791c6925d2", 210_082, ("chart.js", "chart.js/auto"), "Chart"),
    WebLib("lottie-web", "5.13.0", "build/player/esm/lottie.min.js", "lottie.min.js",
           "61cd35a14b6519b7b6073a32e1bb037dab613c2033a3141fc2611295acf6c18e", 589_019, ("lottie-web",)),
)
#: Libraries a page may name that vidgen does not ship, each with the reason and what to copy
#: into the project instead (:func:`unshipped_lib_message`).
NOT_SHIPPED: dict[str, str] = {
    "gsap": ("GSAP's licence is not an open-source one (its files say 'All rights reserved. Subject to the terms at "
             "https://gsap.com/standard-license'), so vidgen does not ship it. If its terms suit you, copy "
             "dist/gsap.min.js of the npm package 'gsap' into the project and load it in a page with "
             "<script src=\"lib/gsap.min.js\"></script> (it sets window.gsap; it cannot be imported as a module), or copy "
             "index.js, gsap-core.js and CSSPlugin.js into one folder and import gsap from './lib/gsap/index.js'"),
}


def lib_file(rel: str) -> Path | None:
    """The shipped file that ``<package>/<file>`` (the path after ``libs/``) names, or ``None``."""
    package, _, name = rel.partition("/")
    for lib in WEB_LIBS:
        if lib.package == package and name in lib.files:
            return LIB_DIR / package / name
    return None


def unshipped_lib_message(scene_id: str, package: str) -> str:
    """The message for a page importing ``package`` (one of :data:`NOT_SHIPPED`) by its bare name."""
    return f"scene '{scene_id}': the page imports '{package}', which is not shipped with vidgen. {NOT_SHIPPED[package]}"


__all__ = ["LIB_DIR", "LIB_FOLDER", "NOT_SHIPPED", "WEB_LIBS", "WRAPPER", "WebLib", "lib_file", "unshipped_lib_message"]
