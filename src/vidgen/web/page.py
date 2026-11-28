"""Screenshots of a ``web`` scene's page in headless Chromium.

:class:`WebPage` serves the project folder on a made-up origin (``http://vidgen-web.invalid/``;
nothing is fetched from the network: a request elsewhere is refused with a warning), opens the
scene's page (or vidgen's bare canvas page that imports the scene's script), waits until it is
ready and returns frame ``n``: vidgen's clock moved to ``t = n / fps`` (the page's timers,
animation-frame callbacks, animations and videos follow it), the page's ``frame(t, ctx)``
hook, then a screenshot of the whole viewport with its alpha (Chromium's default background is
transparent, so what the page leaves transparent shows what vidgen draws behind it; the PNG
Playwright's screenshot gives, encoded faster). An uncaught JavaScript error, at load or on a frame,
is a :class:`VidgenError` naming the scene, the file and the line; so is a ``load`` or a frame that
does not return within its time limit (vidgen then stops the page's renderer process).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import mimetypes
import os
import re
import shutil
import signal
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from html import escape
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

import numpy as np

from vidgen.browser import chromium
from vidgen.browser.chromium import Chromium, first_line, playwright_version, png_pixels
from vidgen.errors import VidgenError
from vidgen.web.baked import BakedStore, bake_key, default_store, part_file, part_sizes, write_part
from vidgen.web.entry import WebEntry
from vidgen.web.inputs import css_height, declared_families, page_head, page_shape, page_viewport, with_head
from vidgen.web.libs import unshipped_lib_message
from vidgen.web.loaded import THREE_VERSION, VIDGEN_PREFIX, served_file, unshipped_addon, unshipped_lib

log = logging.getLogger("vidgen.web")

#: Google Fonts: the host of its style sheets and the host of its font files.
GOOGLE_FONTS_CSS_HOST = "fonts.googleapis.com"
GOOGLE_FONTS_FILE_HOST = "fonts.gstatic.com"
#: Where the guide says how to use another font (named in the Google Fonts warning).
FONT_RECIPE = 'see "Using another font" in `vidgen guide web`'

#: vidgen's page files: the parts of the script run before any script of the page (joined in
#: this order by :func:`init_script`) and the bare page of a ``script:``.
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "web"
CLOCK_FILE = DATA_DIR / "clock.js"
MEDIA_FILE = DATA_DIR / "media.js"
RUNTIME_FILE = DATA_DIR / "runtime.js"
INIT_FILES: tuple[Path, ...] = (CLOCK_FILE, MEDIA_FILE, RUNTIME_FILE)
CANVAS_FILE = DATA_DIR / "canvas.html"
#: vidgen's layout reader (a function evaluated after a screenshot; not part of the frames).
LAYOUT_FILE = DATA_DIR / "layout.js"
#: The origin the project folder is served on (``.invalid`` never resolves).
WEB_ORIGIN = "http://vidgen-web.invalid/"
#: Where vidgen's bare page of a ``script:`` scene is served (not a project path).
CANVAS_PATH = "__vidgen__/canvas.html"
#: Where a page's ``vidgen/baked`` asks for and hands over baked maps (not a file, never in ``loaded``).
BAKED_PATH = "__vidgen__/baked/"
#: Bytes of a baked map read from the page per CDP ``IO.read``.
BAKED_READ_BYTES = 4 * 1024 * 1024
#: Chromium flags added for screenshots: no scroll bars, colours as sRGB, and every changed tile
#: drawn whole (with partial raster an edge pixel of content at a fractional position, changed in
#: an animation-frame callback, came out differently from one render to the next).
WEB_ARGS: tuple[str, ...] = ("--hide-scrollbars", "--force-color-profile=srgb", "--disable-partial-raster")
#: How long the page may take to become ready (milliseconds).
READY_TIMEOUT_MS = 30_000
#: Milliseconds between two looks at whether the page is ready.
READY_POLL_MS = 20
#: How long vidgen's start (fonts, pictures, videos, then the page's ``load(ctx)``) may take (seconds):
#: generous, since a space scene bakes its worlds' maps there (an Earth-like world's 2048 maps took 30 s on 2 cores, a cratered one's longer).
LOAD_TIMEOUT_S = 90.0
#: How long one frame (its timers, animation-frame callbacks and ``frame(t, ctx)``) may take (seconds).
FRAME_TIMEOUT_S = 10.0
#: How long the first frame a page draws may take (seconds): a WebGL page's shaders are compiled
#: then, so a page needs no warm-up of its own.
FIRST_FRAME_TIMEOUT_S = LOAD_TIMEOUT_S
#: The screenshot: ``Page.captureScreenshot`` with what Playwright's
#: ``page.screenshot(type="png")`` sends (the viewport at the visual viewport's place and scale) and
#: ``optimizeForSpeed`` (Chromium's quicker PNG compression: the same pixels, larger files, about
#: 0.3 s less per 1280x720 frame of a detailed page). Carets are hidden around it as Playwright
#: hides them (its ``inPagePrepareForScreenshots``, in every frame of the page).
_HIDE_CARETS = """() => {
  const roots = [];
  const collect = (root) => {
    roots.push(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    do {
      const node = walker.currentNode;
      if (node instanceof Element && node.shadowRoot) collect(node.shadowRoot);
    } while (walker.nextNode());
  };
  collect(document);
  const kept = new Map();
  for (const root of roots) {
    root.querySelectorAll('input,textarea,[contenteditable]').forEach((element) => {
      const style = element.style;
      kept.set(element, { value: style.getPropertyValue('caret-color'), priority: style.getPropertyPriority('caret-color') });
      element.style.setProperty('caret-color', 'transparent', 'important');
    });
  }
  if (kept.size) window.__vidgenShownCarets = kept;
}"""
_SHOW_CARETS = """() => {
  const kept = window.__vidgenShownCarets;
  if (!kept) return;
  delete window.__vidgenShownCarets;
  for (const [element, caret] of kept) element.style.setProperty('caret-color', caret.value, caret.priority);
}"""
#: Chromium's default background behind the page: transparent (the screenshot keeps the alpha).
TRANSPARENT = {"r": 0, "g": 0, "b": 0, "a": 0}
#: The page's time zone and locale (``Date`` and ``Intl`` give the same text on every machine).
TIMEZONE, LOCALE = "UTC", "en-US"
#: Content types by suffix (not the system's table: Windows may map ``.js`` to ``text/plain``,
#: and Chromium refuses a module served so).
CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf", ".wasm": "application/wasm",
    ".txt": "text/plain; charset=utf-8", ".csv": "text/csv; charset=utf-8", ".mp4": "video/mp4", ".webm": "video/webm",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".glb": "model/gltf-binary", ".gltf": "model/gltf+json",
}
_LOCATION = re.compile(re.escape(WEB_ORIGIN) + r"([^\s()]+?):(\d+):(\d+)")


@lru_cache(maxsize=1)
def runtime_digest() -> str:
    """Digest of vidgen's page files (:data:`INIT_FILES`, :data:`CANVAS_FILE`)."""
    digest = hashlib.sha256()
    for path in (*INIT_FILES, CANVAS_FILE):
        digest.update(path.name.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


@lru_cache(maxsize=1)
def layout_reader() -> str:
    """The source of :data:`LAYOUT_FILE` (an async function of ``t``)."""
    return LAYOUT_FILE.read_text(encoding="utf-8")


def layout_digest() -> str:
    """Digest of the layout reader, for the layout record beside a clip."""
    return hashlib.sha256(layout_reader().encode("utf-8")).hexdigest()


def engine_id() -> str:
    """What draws the frames, for the cache key: vidgen's page files (the clock among them), the
    Chromium flags, the time zone and locale, and the Playwright version (which pins the Chromium build)."""
    return (f"web={runtime_digest()} args={' '.join(chromium.chromium_args() + WEB_ARGS)} tz={TIMEZONE} locale={LOCALE} "
            f"playwright={playwright_version() or 'none'}")


def random_seed(scene_id: str) -> list[int]:
    """Eight 32-bit words from the scene id: the seeds of the page's ``Math.random`` (the first
    four) and ``crypto.getRandomValues`` (the last four)."""
    digest = hashlib.sha256(f"vidgen-web-random:{scene_id}".encode("utf-8")).digest()
    return [int.from_bytes(digest[i:i + 4], "little") for i in range(0, 32, 4)]


def init_script(scene_id: str) -> str:
    """The script Chromium runs before any script of the page (top frame only): the files of
    :data:`INIT_FILES` in one function, with the random seed of ``scene_id``."""
    body = "\n".join(path.read_text(encoding="utf-8") for path in INIT_FILES)
    return f"(() => {{\nif (window.top !== window) return;\nconst VIDGEN_SEED = {json.dumps(random_seed(scene_id))};\n{body}\n}})();\n"


def content_type(path: Path) -> str:
    """The ``Content-Type`` a project file is served with."""
    known = CONTENT_TYPES.get(path.suffix.lower())
    return known or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def script_base(script: str) -> str:
    """The URL path of the folder of ``script`` (a project path): ``/extensions/`` for
    ``extensions/x.js``, ``/`` for a script in the project folder itself."""
    folder = PurePosixPath(script).parent.as_posix()
    return "/" if folder == "." else f"/{quote(folder)}/"


def canvas_page(script: str, size: tuple[int, int]) -> str:
    """vidgen's bare page for a ``script:`` scene: one canvas of ``size`` filling the viewport on
    a transparent background (what the script does not draw shows the video's background) and a
    module importing ``script`` (a project path), its exports put on ``window.vidgen``. Its
    ``<base>`` is the script's folder, so a relative URL in the script (``fetch("data.json")``,
    an image's ``src``) names a file beside the script, as its relative imports do."""
    html = CANVAS_FILE.read_text(encoding="utf-8")
    return (html.replace("@WIDTH@", str(size[0])).replace("@HEIGHT@", str(size[1]))
            .replace("@BASE@", escape(script_base(script), quote=True)).replace("@SCRIPT@", json.dumps("/" + script)))


def byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """The first and last byte a ``Range: bytes=a-b`` header asks for (a video seeks with it),
    within a file of ``size`` bytes; ``None`` for no header, another unit or a range out of the file."""
    match = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*", header or "")
    if match is None or size == 0 or not (match[1] or match[2]):
        return None
    if not match[1]:   # the last N bytes
        return max(0, size - int(match[2])), size - 1
    start = int(match[1])
    end = min(int(match[2]), size - 1) if match[2] else size - 1
    return (start, end) if start <= end else None


def project_path(url: str) -> str | None:
    """The project path a request on :data:`WEB_ORIGIN` asks for (``extensions/x.css``), or
    ``None`` for any other origin."""
    if not url.startswith(WEB_ORIGIN):
        return None
    return unquote(urlsplit(url).path).lstrip("/")


def google_font_families(url: str) -> list[str] | None:
    """The font families a request to Google Fonts asks for: from ``family=`` of a style sheet
    on :data:`GOOGLE_FONTS_CSS_HOST` (``css2?family=Space+Grotesk:wght@400;700&family=Lora``, or
    the older ``css?family=Lora:400,700|Inter``), the family's folder name of a font file on
    :data:`GOOGLE_FONTS_FILE_HOST` (``/s/spacegrotesk/v16/x.woff2``); ``[]`` when the URL names
    none, ``None`` for any other host."""
    parts = urlsplit(url)
    if parts.hostname == GOOGLE_FONTS_CSS_HOST:
        values = [name for value in parse_qs(parts.query).get("family", []) for name in value.split("|")]
        return [family for value in values if (family := value.partition(":")[0].strip())]
    if parts.hostname == GOOGLE_FONTS_FILE_HOST:
        folder = re.match(r"/s/([^/]+)/", parts.path)
        return [folder[1]] if folder else []
    return None


def google_font_message(scene_id: str, family: str | None, declared: bool) -> str:
    """The warning for a refused Google Fonts request for ``family`` (``None``: not known);
    ``declared``: vidgen's style sheet already gives the page that family."""
    asked = f"the page asks Google Fonts for {json.dumps(family, ensure_ascii=False) if family else 'a font'}"
    if declared:
        return (f"scene '{scene_id}': {asked}, but the internet is off during a render. vidgen already gives the page this "
                "family: remove the link to Google Fonts.")
    return (f"scene '{scene_id}': {asked}, but the internet is off during a render, so that text is drawn in a fallback font. "
            "Put the font's .ttf, .otf or .woff file in the project's fonts/ folder and remove the link to Google Fonts "
            f"({FONT_RECIPE}).")


def _family_key(family: str) -> str:
    return re.sub(r"[\s+_-]", "", family).lower()


def error_location(error: dict[str, Any]) -> str | None:
    """``extensions/gears.js line 12`` for a page error (from its file and line, else from the
    first project file in its stack), or ``None`` when neither names one."""
    candidates = []
    if error.get("file") and error.get("line"):
        candidates.append((str(error["file"]), int(error["line"])))
    candidates += [(WEB_ORIGIN + m[1], int(m[2])) for m in _LOCATION.finditer(str(error.get("stack") or ""))]
    for url, line in candidates:
        rel = project_path(url.split("?", 1)[0])
        if rel and not rel.startswith("__vidgen__/"):
            return f"{rel} line {line}"
    return None


def error_message(scene_id: str, entry: WebEntry, error: dict[str, Any], when: str) -> str:
    """The message for a page error: the scene, where (file and line, else the entry), when."""
    where = error_location(error) or entry.posix
    text = str(error.get("message") or "unknown error").removeprefix("Uncaught ")
    return f"scene '{scene_id}': JavaScript error in {where} {when}: {text}"


def unshipped_addon_message(scene_id: str, addon: str) -> str:
    """The message for a page importing a three.js add-on vidgen does not ship (``addon``:
    its path under ``three/addons/``, e.g. ``loaders/DRACOLoader.js``)."""
    name = addon.rsplit("/", 1)[-1]
    return (
        f"scene '{scene_id}': the page imports the three.js add-on '{addon}' (three/addons/{addon}), which is not "
        f"shipped with vidgen (the shipped ones are listed in 'vidgen guide web'). To use it, copy {name} from "
        f"three.js {THREE_VERSION} (the npm package 'three', examples/jsm/{addon}) into the project, e.g. "
        f"extensions/lib/{name}, and import it by relative path ('./lib/{name}'); its own imports of 'three' "
        "keep working, and any '../' import inside it needs that file copied beside it too"
    )


def fit_pixels(pixels: np.ndarray, size: tuple[int, int], scale: float, what: str) -> np.ndarray:
    """A screenshot of a window at device scale ``scale`` cut to ``size`` (W, H): the window is
    a whole number of CSS pixels, so its picture may be up to ``ceil(scale) + 1`` output pixels
    larger than ``size`` (:func:`~vidgen.web.inputs.page_viewport`); those rows at the bottom
    (columns at the right) are cut off. Any other size is an error naming ``what``."""
    height, width = pixels.shape[:2]
    spare = math.ceil(scale) + 1
    if not (size[0] <= width <= size[0] + spare and size[1] <= height <= size[1] + spare):
        raise VidgenError(f"{what} drew {width}x{height} px, expected {size[0]}x{size[1]}")
    return pixels[:size[1], :size[0]]


def renderer_pids(browser: Any) -> list[int]:
    """The process ids of a Chromium's renderer processes (``SystemInfo.getProcessInfo``), or
    none when Chromium does not tell."""
    try:
        info = browser.new_browser_cdp_session().send("SystemInfo.getProcessInfo")
    except Exception:  # noqa: BLE001 - an older Chromium: no time limit can be enforced
        return []
    return [int(p["id"]) for p in info.get("processInfo", []) if p.get("type") == "renderer"]


def _in_every_frame(frames: list[Any], script: str) -> None:
    """``script`` evaluated in each of a page's frames; a frame that fails (gone meanwhile) is
    skipped, as Playwright skips it around its own screenshots."""
    api = chromium.sync_api()
    for frame in frames:
        try:
            frame.evaluate(script)
        except api.Error:
            pass


class _TimeLimit:
    """Stops a page that does not return in time: after ``seconds`` a timer thread ends the
    renderer processes (the blocked Playwright call then fails); :attr:`expired` says so."""

    def __init__(self, pids: list[int]) -> None:
        self.pids = pids
        self.expired = False

    def _stop(self) -> None:
        self.expired = True
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

    @contextmanager
    def running(self, seconds: float) -> Iterator[None]:
        timer = threading.Timer(seconds, self._stop)
        timer.daemon = True
        timer.start()
        try:
            yield
        finally:
            timer.cancel()


class WebPage:
    """``with WebPage(root, entry, scene_id=..., size=(w, h), fps=..., frames=...) as page:
    page.frame(n)`` -> RGBA pixels (H x W x 4, straight alpha).

    Starts Chromium on enter, closes it on exit; requests outside ``root`` are refused (one
    warning per URL, also in :attr:`refused`). ``theme`` (``ctx.theme``, also the CSS custom
    properties), ``data`` (``ctx.data``) and ``beats`` (``ctx.beats``) are what the page is given;
    ``shape`` is the video's shape (:func:`~vidgen.web.inputs.page_shape`; default:
    a page filling a frame of ``size``), in ``ctx`` and as attributes of ``<html>``.
    ``design_width``: the page's window is that many CSS pixels wide (:attr:`viewport`)
    and drawn at the device scale :attr:`scale`, so the frames are still ``size``; without it the
    window is ``size`` at scale 1. ``music``: the scene's music data
    (:func:`vidgen.web.music.scene_music`), given to the page as ``ctx.music`` by vidgen's music
    helper; ``None``: no helper, no ``ctx.music``. ``orbits``: the scene's orbit data
    (:func:`vidgen.scenes.orbit_data.scene_orbit_data`), given as ``ctx.orbits`` by vidgen's orbit
    helper; ``None``: no helper, no ``ctx.orbits``. ``draw_mode``: ``"depth"`` is given as
    ``ctx.draw_mode`` (vidgen/three-finish then draws the depth pass); ``None``: no ``ctx.draw_mode``. ``baked``: the cache of baked maps the
    page's ``vidgen/baked`` uses (``True``: :func:`~vidgen.web.baked.default_store`, which is off
    when ``VIDGEN_BAKED_CACHE_MB=0``; ``False``: none; or a store); :attr:`baked_log` lists
    ``("hit" | "damaged" | "stored" | "baked", name, bytes)`` per bake (``baked``: not kept).
    :attr:`loaded` maps every file served so far (project path, or ``__vidgen__/...``)
    to its SHA-256, a missing project file to ``None``."""

    def __init__(self, root: Path, entry: WebEntry, *, scene_id: str, size: tuple[int, int], fps: int, frames: int,
                 theme: dict[str, Any] | None = None, data: dict[str, Any] | None = None,
                 beats: list[dict[str, Any]] | None = None, shape: dict[str, Any] | None = None,
                 design_width: int | None = None, music: dict[str, Any] | None = None, orbits: dict[str, Any] | None = None,
                 baked: BakedStore | bool = True, draw_mode: str | None = None) -> None:
        self.root, self.entry, self.scene_id = root, entry, scene_id
        self.draw_mode = draw_mode
        self.baked: BakedStore | None = (default_store() if baked else None) if isinstance(baked, bool) else baked
        self.baked_log: list[tuple[str, str, int]] = []
        self._baked_seen: dict[str, tuple[str, list[int], list[int]]] = {}
        self._baked_asked: dict[str, tuple[str, list[int], list[int]]] = {}
        self._baked_ready: dict[str, dict[str, Any]] = {}
        self.music = music
        self.orbits = orbits
        self.size, self.fps, self.frames = size, fps, frames
        self.design_width = design_width
        self.viewport, self.scale = page_viewport(size, design_width)
        self.theme, self.data, self.beats = theme, dict(data or {}), list(beats or [])
        self.shape = dict(shape) if shape is not None else page_shape(size)
        self.refused: list[str] = []
        self._google_fonts: set[str] = set()
        self.missing: list[str] = []
        self.unshipped: list[str] = []
        self.unshipped_libs: list[str] = []
        #: Sentences the page left for vidgen's log at load (``globalThis.__vidgenNotes``: a space scene's checks).
        self.notes: list[str] = []
        self.loaded: dict[str, str | None] = {}
        self._chromium: Chromium | None = None
        self._page: Any = None
        self._cdp: Any = None
        self._advanced = False
        self._device_scale: float = 1
        self._limit = _TimeLimit([])

    # ----- serving -------------------------------------------------------------------------------

    def _serve(self, route: Any) -> None:
        """Answer from the project folder (or vidgen's files under ``__vidgen__/``); refuse every
        other origin; 404 a missing file. Notes what it served in :attr:`loaded`."""
        url = route.request.url
        rel = project_path(url)
        if rel is not None and rel.startswith(BAKED_PATH):
            self._serve_baked(route, rel.removeprefix(BAKED_PATH))
            return
        if rel is None:
            if url not in self.refused:
                self.refused.append(url)
                families = google_font_families(url)
                if families is None:
                    log.warning("scene '%s': refused %s (a web scene cannot reach the internet; put the file in the project folder)", self.scene_id, url)
                else:
                    self._warn_google_fonts(families)
            route.abort("blockedbyclient")
            return
        if rel == CANVAS_PATH and self.entry.kind == "script":
            body = with_head(canvas_page(self.entry.posix, self.viewport).encode("utf-8"), page_head(self.theme, self.shape))
            route.fulfill(status=200, body=body, headers={"Content-Type": CONTENT_TYPES[".html"]})
            return
        addon = unshipped_addon(rel)
        if addon is not None:
            if addon not in self.unshipped:
                self.unshipped.append(addon)
                log.warning("scene '%s': the three.js add-on %s is not shipped with vidgen", self.scene_id, addon)
            route.fulfill(status=404, body="", headers={"Content-Type": CONTENT_TYPES[".txt"]})
            return
        lib = unshipped_lib(rel)
        if lib is not None:
            if lib not in self.unshipped_libs:
                self.unshipped_libs.append(lib)
                log.warning("scene '%s': %s is not shipped with vidgen", self.scene_id, lib)
            route.fulfill(status=404, body="", headers={"Content-Type": CONTENT_TYPES[".txt"]})
            return
        path = served_file(self.root, rel)
        if path is None or not path.is_file():
            if path is not None and not rel.startswith(VIDGEN_PREFIX) and rel != "favicon.ico":
                self.loaded[rel] = None   # created later, it draws the clip again
            if rel not in self.missing and rel != "favicon.ico":
                self.missing.append(rel)
                log.warning("scene '%s': the page asked for %s, which is not in the project folder", self.scene_id, rel)
            route.fulfill(status=404, body="", headers={"Content-Type": CONTENT_TYPES[".txt"]})
            return
        body = path.read_bytes()
        self.loaded[rel] = hashlib.sha256(body).hexdigest()
        if self.entry.kind == "page" and rel == self.entry.posix:
            body = with_head(body, page_head(self.theme, self.shape))
        headers = {"Content-Type": content_type(path), "Accept-Ranges": "bytes"}
        span = byte_range(route.request.headers.get("range"), len(body))
        if span is None:
            route.fulfill(status=200, body=body, headers=headers)
            return
        start, end = span
        headers["Content-Range"] = f"bytes {start}-{end}/{len(body)}"
        route.fulfill(status=206, body=body[start:end + 1], headers=headers)

    # ----- baked maps -----------------------------------------------------------

    def _serve_baked(self, route: Any, what: str) -> None:
        """``status``; ``lookup`` (POST: the bake's key and whether an entry is there); ``<key>/<n>``
        (a stored part's bytes); ``<key>/damaged`` (POST: the page could not use the entry, which is
        removed); ``<key>/ready`` (POST: the page holds a new bake for :meth:`_store_baked`)."""
        request, store = route.request, self.baked
        if what == "status":
            self._answer(route, {"on": store is not None})
            return
        key, _, part = what.partition("/")
        try:
            if store is None:
                raise LookupError(what)
            if what == "lookup" and request.method == "POST":
                asked = json.loads(request.post_data or "")
                described = part_sizes(asked)
                if described is None:
                    raise LookupError(what)
                sizes, widths = [n for n, _ in described], [w for _, w in described]
                key = bake_key(asked, engine_id())
                found = store.checked(key, sizes)
                name = str(asked.get("name"))
                self._baked_seen[key] = (name, sizes, widths)
                if found is not None:
                    self.baked_log.append(("hit", name, sum(found.sizes)))
                elif store.has_room(sum(sizes)):
                    self._baked_asked[key] = self._baked_seen[key]
                else:
                    self.baked_log.append(("baked", name, sum(sizes)))
                    key = ""
                self._answer(route, {"key": key or None, "found": found is not None, "meta": found.meta if found is not None else None})
                return
            if part == "damaged" and request.method == "POST" and key in self._baked_seen:   # the page could not use it: baked again, kept anew
                store.remove(key)
                self._baked_asked[key] = self._baked_seen[key]
                self.baked_log.append(("damaged", self._baked_seen[key][0], sum(self._baked_seen[key][1])))
                route.fulfill(status=204, body=b"")
                return
            if part == "ready" and request.method == "POST" and key in self._baked_asked:
                told = json.loads(request.post_data or "")
                if told.get("parts") == self._baked_asked[key][1] and isinstance(told.get("meta"), dict):
                    self._baked_ready[key] = told["meta"]
                route.fulfill(status=204, body=b"")
                return
            found = store.entry(key) if part.isdigit() else None
            if found is None or int(part) >= len(found.sizes):
                raise LookupError(what)
            route.fulfill(status=200, path=str(found.part(int(part))), headers={"Content-Type": "application/octet-stream"})
        except (LookupError, ValueError, TypeError, OSError):
            route.fulfill(status=404, body=b"", headers={"Content-Type": CONTENT_TYPES[".txt"]})

    @staticmethod
    def _answer(route: Any, data: dict[str, Any]) -> None:
        route.fulfill(status=200, body=json.dumps(data), headers={"Content-Type": CONTENT_TYPES[".json"]})

    def _store_baked(self) -> None:
        """Keep the bakes the page announced (``globalThis.__vidgenBaked``: each a key, its parts as
        Blobs and its ``meta``): each part read with CDP ``IO.read`` into a staged folder, then
        committed. A failure loses only that entry (logged); the page is never stopped for it."""
        if not self._baked_ready or self.baked is None or self._page is None:
            return
        ready, self._baked_ready = self._baked_ready, {}
        store = self.baked
        try:
            listed = self._page.evaluate("() => (globalThis.__vidgenBaked || []).map((e) => ({key: e.key, sizes: e.blobs.map((b) => b.size)}))")
            for index, item in enumerate(listed):
                key = str(item.get("key"))
                if key not in ready or key not in self._baked_asked:
                    continue
                name, sizes, widths = self._baked_asked.pop(key)
                if item.get("sizes") != sizes or store.entry(key) is not None:
                    continue
                folder = store.staging(key)
                try:
                    for n, size in enumerate(sizes):
                        if write_part(part_file(folder, n), self._blob_chunks(f"globalThis.__vidgenBaked[{index}].blobs[{n}]"), widths[n]) != size:
                            raise ValueError(f"part {n} of {key} is not {size} bytes")
                    stored = store.commit(key, folder, sizes, ready[key])
                except BaseException:
                    shutil.rmtree(folder, ignore_errors=True)
                    raise
                self.baked_log.append(("stored" if stored else "baked", name, sum(sizes)))
        except Exception as exc:  # noqa: BLE001 - the cache never stops a page: the bake stands, it is only not kept
            log.warning("scene '%s': a baked map was not kept in the cache: %s", self.scene_id, first_line(exc))
        finally:
            try:
                self._page.evaluate("() => { if (globalThis.__vidgenBaked) globalThis.__vidgenBaked.length = 0; }")
                self._cdp.send("Runtime.releaseObjectGroup", {"objectGroup": "vidgen-baked"})
            except Exception:  # noqa: BLE001 - a page gone meanwhile has nothing left to free
                pass

    def _blob_chunks(self, expression: str) -> Iterator[bytes]:
        """The bytes of the Blob ``expression`` names in the page, in pieces (CDP ``IO.resolveBlob`` and ``IO.read``)."""
        found = self._cdp.send("Runtime.evaluate", {"expression": expression, "objectGroup": "vidgen-baked"})
        handle = "blob:" + self._cdp.send("IO.resolveBlob", {"objectId": found["result"]["objectId"]})["uuid"]
        try:
            while True:
                chunk = self._cdp.send("IO.read", {"handle": handle, "size": BAKED_READ_BYTES})
                data = chunk.get("data", "")
                yield base64.b64decode(data) if chunk.get("base64Encoded") else data.encode("latin-1")
                if chunk.get("eof"):
                    break
        finally:
            self._cdp.send("IO.close", {"handle": handle})

    def _warn_google_fonts(self, families: list[str]) -> None:
        """One warning per family asked of Google Fonts (a style sheet's ``Space Grotesk`` and a
        font file's ``spacegrotesk`` are one family)."""
        declared = {_family_key(family) for family in declared_families(self.theme)} if self.theme is not None else set()
        for family in families or [None]:
            key = _family_key(family or "")
            if key not in self._google_fonts:
                self._google_fonts.add(key)
                log.warning("%s", google_font_message(self.scene_id, family, key in declared))

    # ----- the page ------------------------------------------------------------------------------

    def _url(self) -> str:
        return WEB_ORIGIN + (CANVAS_PATH if self.entry.kind == "script" else self.entry.posix)

    def _unshipped_message(self) -> str | None:
        """The message for the first three.js add-on or library the page asked for that vidgen does not ship."""
        if self.unshipped:
            return unshipped_addon_message(self.scene_id, self.unshipped[0])
        if self.unshipped_libs:
            return unshipped_lib_message(self.scene_id, self.unshipped_libs[0])
        return None

    def _raise_first(self, errors: list[dict[str, Any]], when: str) -> None:
        unshipped = self._unshipped_message()
        if errors and unshipped is not None:
            raise VidgenError(unshipped)
        if errors:
            raise VidgenError(error_message(self.scene_id, self.entry, errors[0], when))

    def _not_ready(self, exc: Exception) -> VidgenError:
        unshipped = self._unshipped_message()
        if unshipped is not None:
            return VidgenError(unshipped)
        seconds = READY_TIMEOUT_MS / 1000
        unanswered = self.missing + self.refused
        detail = f"; not answered: {', '.join(unanswered)}" if unanswered else ""
        return VidgenError(
            f"scene '{self.scene_id}': {self.entry.posix} did not become ready within {seconds:g} s "
            f"(its load event never came or a module never finished loading{detail}): {first_line(exc)}"
        )

    def __enter__(self) -> WebPage:
        api = chromium.sync_api()
        self._chromium = Chromium("a web scene", WEB_ARGS).__enter__()
        try:
            self._open(api)
        except BaseException:
            self.close()
            raise
        return self

    def _open(self, api: Any) -> None:
        width, height = self.viewport
        browser = self._chromium.browser  # type: ignore[union-attr]
        self._device_scale = 1 if self.design_width is None else self.scale
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=self._device_scale,
                                      timezone_id=TIMEZONE, locale=LOCALE)
        context.add_init_script(script=init_script(self.scene_id))
        if self.music is not None:   # ctx.music: only on pages of scenes with music_data
            from vidgen.web.music import helper_source

            context.add_init_script(script=helper_source())
        if self.orbits is not None:   # ctx.orbits: only on pages of scenes with orbit_data
            from vidgen.web.orbits import helper_source as orbit_helper

            context.add_init_script(script=orbit_helper())
            if "flights" in self.orbits:   # ctx.flight: the flights travel in the orbit payload
                from vidgen.web.flights import helper_source as flight_helper

                context.add_init_script(script=flight_helper())
        context.route("**/*", self._serve)
        self._page = page = context.new_page()
        self._cdp = context.new_cdp_session(page)
        self._cdp.send("Emulation.setDefaultBackgroundColorOverride", {"color": TRANSPARENT})
        is_script = self.entry.kind == "script"
        try:
            page.goto(self._url(), wait_until="load", timeout=READY_TIMEOUT_MS)
            self._wait_until_ready(is_script)
        except (api.TimeoutError, TimeoutError) as exc:
            raise self._not_ready(exc) from None
        except api.Error as exc:
            raise VidgenError(f"scene '{self.scene_id}': {self.entry.posix} did not load: {first_line(exc)}") from None
        self._limit = _TimeLimit(renderer_pids(browser))
        info = {"scene": self.scene_id, "width": width, "height": height, "fps": self.fps,
                "frames": self.frames, "duration": self.frames / self.fps, "theme": self.theme, "data": self.data,
                "beats": self.beats, **self.shape, **({} if self.music is None else {"music": self.music}),
                **({} if self.orbits is None else {"orbits": self.orbits}),
                **({} if self.draw_mode is None else {"draw_mode": self.draw_mode})}
        errors = self._evaluate("info => window.__vidgen.start(info)", info, "at load", "load(ctx)", LOAD_TIMEOUT_S)
        self._raise_first(errors, "at load")
        self._store_baked()
        self.notes = [str(n) for n in self._page.evaluate("() => Array.isArray(globalThis.__vidgenNotes) ? globalThis.__vidgenNotes.map(String) : []")]
        for note in self.notes:
            log.warning("scene '%s': %s", self.scene_id, note)

    def _wait_until_ready(self, is_script: bool) -> None:
        """Wait until the page has loaded (and, for a ``script:``, its module has finished, with
        every top-level ``await``) or has reported an error; :class:`TimeoutError` after
        :data:`READY_TIMEOUT_MS`.

        Asked from here every :data:`READY_POLL_MS`, not with Playwright's ``wait_for_function``:
        that polls inside the page on ``requestAnimationFrame`` or ``setTimeout``, which are
        vidgen's clock standing still at 0, so it looked once and a module still waiting for a
        ``fetch`` at that moment was never looked at again (Step 341).
        ``wait_for_timeout`` keeps Playwright answering the page's requests meanwhile."""
        ready = "s => window.__vidgen.errors.length > 0 || (document.readyState === 'complete' && (!s || window.__vidgen.ready))"
        end = time.monotonic() + READY_TIMEOUT_MS / 1000
        while not self._page.evaluate(ready, is_script):
            if time.monotonic() >= end:
                raise TimeoutError(f"not ready after {READY_TIMEOUT_MS} ms")
            self._page.wait_for_timeout(READY_POLL_MS)

    def _overrun(self, hook: str, seconds: float) -> VidgenError:
        extra = " (time stands still at 0 before frame 0, so a timer it waits for never fires)" if hook == "load(ctx)" else ""
        return VidgenError(
            f"scene '{self.scene_id}': {hook} in {self.entry.posix} did not return within {seconds:g} s{extra}: "
            "a loop that never ends or a promise that never settles, in the hook or in a timer, "
            "requestAnimationFrame callback, fetch, picture, font or video it waits for; vidgen stopped the page"
        )

    def _evaluate(self, script: str, arg: Any, when: str, hook: str, seconds: float) -> Any:
        """``page.evaluate(script, arg)``, stopped after ``seconds`` (:meth:`_overrun` names ``hook``)."""
        api = chromium.sync_api()
        try:
            with self._limit.running(seconds):
                return self._page.evaluate(script, arg)
        except api.Error as exc:
            if self._limit.expired:
                raise self._overrun(hook, seconds) from None
            raise VidgenError(f"scene '{self.scene_id}': the page {self.entry.posix} failed {when}: {first_line(exc)}") from None

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def advance(self, n: int) -> None:
        """Move the clock and the page to frame ``n`` (``t = n / fps``) and run the page's
        ``frame(t, ctx)`` hook (if any), without a screenshot. The first frame of a page may take
        :data:`FIRST_FRAME_TIMEOUT_S`, every later one :data:`FRAME_TIMEOUT_S`."""
        t = n / self.fps
        when = f"in frame(t={t:.3f})"
        seconds = FRAME_TIMEOUT_S if self._advanced else FIRST_FRAME_TIMEOUT_S
        self._advanced = True
        errors = self._evaluate("n => window.__vidgen.frame(n)", n, when, f"frame(t={t:.3f})", seconds)
        self._raise_first(errors, when)
        self._store_baked()

    def layout(self, n: int) -> dict[str, Any]:
        """What text the page shows now, the page at frame ``n`` (call after :meth:`advance` or
        :meth:`frame` of ``n``): ``data/web/layout.js``'s reading, in page pixels."""
        t = n / self.fps
        when = f"in layout(t={t:.3f})"
        api = chromium.sync_api()
        try:
            with self._limit.running(FRAME_TIMEOUT_S):
                reading = dict(self._page.evaluate(layout_reader(), t))
        except api.Error as exc:
            if self._limit.expired:
                raise self._overrun(f"layout(t={t:.3f})", FRAME_TIMEOUT_S) from None
            message = first_line(exc).removeprefix("Error: ").removeprefix("page.evaluate: ")
            raise VidgenError(f"scene '{self.scene_id}': reading the page's text {when} failed: {message}") from None
        if self.design_width is not None:   # the part of the window the frame shows (its height is rounded up)
            reading["height"] = round(css_height(self.size, self.design_width), 3)
        return reading

    def frame(self, n: int) -> np.ndarray:
        """Frame ``n``: the clock and the page moved to ``t = n / fps``, the page's ``frame(t, ctx)``
        hook (if any), then a screenshot (:meth:`advance`, :meth:`screenshot`, :meth:`pixels`)."""
        self.advance(n)
        return self.pixels(self.screenshot(n))

    def depth_frames(self) -> int:
        """How many depth frames the page drew so far (vidgen/three-finish's count, ``ctx.draw_mode`` ``"depth"``)."""
        return int(self._page.evaluate("() => Number(globalThis.__vidgenDepthFrames) || 0"))

    def screenshot(self, n: int) -> bytes:
        """A PNG of the page as it is now (frame ``n``, for the error message), with its alpha:
        the pixels of Playwright's ``page.screenshot(type="png")``, encoded faster."""
        t = n / self.fps
        api = chromium.sync_api()
        frames = self._page.frames
        try:
            with self._limit.running(READY_TIMEOUT_MS / 1000):
                _in_every_frame(frames, _HIDE_CARETS)
                try:
                    viewport = self._cdp.send("Page.getLayoutMetrics")["visualViewport"]
                    width, height = self.viewport
                    # Playwright's device scale (design_width) is an override of its own CDP session, not of this one: given here
                    clip = {"x": viewport["pageX"], "y": viewport["pageY"], "scale": viewport["scale"] * self._device_scale,
                            "width": math.floor(width / viewport["scale"] + 1e-3), "height": math.floor(height / viewport["scale"] + 1e-3)}
                    shot = self._cdp.send("Page.captureScreenshot", {"format": "png", "clip": clip, "captureBeyondViewport": False,
                                                                      "optimizeForSpeed": True})
                finally:
                    _in_every_frame(frames, _SHOW_CARETS)
        except api.Error as exc:
            if self._limit.expired:
                raise VidgenError(f"scene '{self.scene_id}': no screenshot of {self.entry.posix} at t={t:.3f}: it did not come "
                                  f"within {READY_TIMEOUT_MS / 1000:g} s; vidgen stopped the page") from None
            raise VidgenError(f"scene '{self.scene_id}': no screenshot of {self.entry.posix} at t={t:.3f}: {first_line(exc)}") from None
        return base64.b64decode(shot["data"])

    def pixels(self, png: bytes) -> np.ndarray:
        """The RGBA pixels (H x W x 4, straight alpha) of a screenshot of this page, ``size`` big."""
        what = f"scene '{self.scene_id}': the page"
        if self.design_width is None:
            return png_pixels(png, self.size, what, alpha=True)
        return fit_pixels(png_pixels(png, None, what, alpha=True), self.size, self.scale, what)

    def close(self) -> None:
        """Close Chromium and Playwright (safe to call twice)."""
        if self._chromium is not None:
            self._chromium.close()
        self._chromium = self._page = self._cdp = None


__all__ = ["BAKED_PATH", "BAKED_READ_BYTES", "CANVAS_PATH", "FIRST_FRAME_TIMEOUT_S", "FRAME_TIMEOUT_S", "LAYOUT_FILE", "LOAD_TIMEOUT_S", "READY_POLL_MS", "READY_TIMEOUT_MS", "TRANSPARENT", "WEB_ORIGIN", "WebPage", "byte_range", "canvas_page",
           "content_type", "engine_id", "error_location", "error_message", "fit_pixels", "google_font_families", "google_font_message", "init_script", "layout_digest", "layout_reader", "project_path", "random_seed",
           "renderer_pids", "runtime_digest", "script_base", "unshipped_addon_message"]
