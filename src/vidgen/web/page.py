"""Screenshots of a ``web`` scene's page in headless Chromium (DESIGN.md §118.3).

:class:`WebPage` serves the project folder on a made-up origin (``http://vidgen-web.invalid/``;
nothing is fetched from the network: a request elsewhere is refused with a warning), opens the
scene's page (or vidgen's bare canvas page that imports the scene's script), waits until it is
ready and returns frame ``n``: the page's ``frame(t, ctx)`` hook called at ``t = n / fps``, then a
screenshot of the whole viewport. An uncaught JavaScript error, at load or on a frame, is a
:class:`VidgenError` naming the scene, the file and the line.
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import re
from functools import lru_cache
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import unquote, urlsplit

import numpy as np

from vidgen.browser import chromium
from vidgen.browser.chromium import Chromium, first_line, playwright_version, png_pixels
from vidgen.errors import VidgenError
from vidgen.web.entry import WebEntry, inside

log = logging.getLogger("vidgen.web")

#: vidgen's page files (the runtime injected into every page, the bare page of a ``script:``).
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "web"
RUNTIME_FILE = DATA_DIR / "runtime.js"
CANVAS_FILE = DATA_DIR / "canvas.html"
#: The origin the project folder is served on (``.invalid`` never resolves).
WEB_ORIGIN = "http://vidgen-web.invalid/"
#: Where vidgen's bare page of a ``script:`` scene is served (not a project path).
CANVAS_PATH = "__vidgen__/canvas.html"
#: Chromium flags added for screenshots: no scroll bars, colours as sRGB.
WEB_ARGS: tuple[str, ...] = ("--hide-scrollbars", "--force-color-profile=srgb")
#: How long the page may take to become ready (milliseconds).
READY_TIMEOUT_MS = 30_000
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
    """Digest of vidgen's page files (:data:`RUNTIME_FILE`, :data:`CANVAS_FILE`)."""
    digest = hashlib.sha256()
    for path in (RUNTIME_FILE, CANVAS_FILE):
        digest.update(path.name.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def engine_id() -> str:
    """What draws the frames, for the cache key: vidgen's page files, the Chromium flags and the
    Playwright version (which pins the Chromium build)."""
    return f"web={runtime_digest()} args={' '.join(chromium.CHROMIUM_ARGS + WEB_ARGS)} playwright={playwright_version() or 'none'}"


def content_type(path: Path) -> str:
    """The ``Content-Type`` a project file is served with."""
    known = CONTENT_TYPES.get(path.suffix.lower())
    return known or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def canvas_page(script: str, size: tuple[int, int]) -> str:
    """vidgen's bare page for a ``script:`` scene: one canvas of ``size`` filling the frame and
    a module importing ``script`` (a project path), its exports put on ``window.vidgen``."""
    html = CANVAS_FILE.read_text(encoding="utf-8")
    return html.replace("@WIDTH@", str(size[0])).replace("@HEIGHT@", str(size[1])).replace("@SCRIPT@", json.dumps("/" + script))


def project_path(url: str) -> str | None:
    """The project path a request on :data:`WEB_ORIGIN` asks for (``extensions/x.css``), or
    ``None`` for any other origin."""
    if not url.startswith(WEB_ORIGIN):
        return None
    return unquote(urlsplit(url).path).lstrip("/")


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


class WebPage:
    """``with WebPage(root, entry, scene_id=..., size=(w, h), fps=..., frames=...) as page:
    page.frame(n)`` -> RGB pixels (H x W x 3).

    Starts Chromium on enter, closes it on exit; requests outside ``root`` are refused (one
    warning per URL, also in :attr:`refused`)."""

    def __init__(self, root: Path, entry: WebEntry, *, scene_id: str, size: tuple[int, int], fps: int, frames: int) -> None:
        self.root, self.entry, self.scene_id = root, entry, scene_id
        self.size, self.fps, self.frames = size, fps, frames
        self.refused: list[str] = []
        self.missing: list[str] = []
        self._chromium: Chromium | None = None
        self._page: Any = None

    # ----- serving -------------------------------------------------------------------------------

    def _serve(self, route: Any) -> None:
        """Answer from the project folder; refuse every other origin; 404 a missing file."""
        url = route.request.url
        rel = project_path(url)
        if rel is None:
            if url not in self.refused:
                self.refused.append(url)
                log.warning("scene '%s': refused %s (a web scene cannot reach the internet; put the file in the project folder)", self.scene_id, url)
            route.abort("blockedbyclient")
            return
        if rel == CANVAS_PATH and self.entry.kind == "script":
            route.fulfill(status=200, body=canvas_page(self.entry.posix, self.size), headers={"Content-Type": CONTENT_TYPES[".html"]})
            return
        path = inside(self.root, rel)
        if path is None or not path.is_file():
            if rel not in self.missing and rel != "favicon.ico":
                self.missing.append(rel)
                log.warning("scene '%s': the page asked for %s, which is not in the project folder", self.scene_id, rel)
            route.fulfill(status=404, body="", headers={"Content-Type": CONTENT_TYPES[".txt"]})
            return
        route.fulfill(status=200, body=path.read_bytes(), headers={"Content-Type": content_type(path)})

    # ----- the page ------------------------------------------------------------------------------

    def _url(self) -> str:
        return WEB_ORIGIN + (CANVAS_PATH if self.entry.kind == "script" else self.entry.posix)

    def _raise_first(self, errors: list[dict[str, Any]], when: str) -> None:
        if errors:
            raise VidgenError(error_message(self.scene_id, self.entry, errors[0], when))

    def _not_ready(self, exc: Exception) -> VidgenError:
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
        width, height = self.size
        context = self._chromium.browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)  # type: ignore[union-attr]
        context.add_init_script(path=str(RUNTIME_FILE))
        context.route("**/*", self._serve)
        self._page = page = context.new_page()
        is_script = self.entry.kind == "script"
        try:
            page.goto(self._url(), wait_until="load", timeout=READY_TIMEOUT_MS)
            page.wait_for_function(
                "s => window.__vidgen.errors.length > 0 || (document.readyState === 'complete' && (!s || window.__vidgen.ready))",
                arg=is_script, timeout=READY_TIMEOUT_MS,
            )
        except api.TimeoutError as exc:
            raise self._not_ready(exc) from None
        except api.Error as exc:
            raise VidgenError(f"scene '{self.scene_id}': {self.entry.posix} did not load: {first_line(exc)}") from None
        info = {"scene": self.scene_id, "width": width, "height": height, "fps": self.fps,
                "frames": self.frames, "duration": self.frames / self.fps}
        self._raise_first(self._evaluate("info => window.__vidgen.start(info)", info, "at load"), "at load")

    def _evaluate(self, script: str, arg: Any, when: str) -> Any:
        api = chromium.sync_api()
        try:
            return self._page.evaluate(script, arg)
        except api.Error as exc:
            raise VidgenError(f"scene '{self.scene_id}': the page {self.entry.posix} failed {when}: {first_line(exc)}") from None

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def frame(self, n: int) -> np.ndarray:
        """Frame ``n``: the page's ``frame(n / fps, ctx)`` hook (if any), then a screenshot."""
        t = n / self.fps
        when = f"in frame(t={t:.3f})"
        self._raise_first(self._evaluate("t => window.__vidgen.frame(t)", t, when), when)
        api = chromium.sync_api()
        try:
            png = self._page.screenshot(type="png", timeout=READY_TIMEOUT_MS)
        except api.Error as exc:
            raise VidgenError(f"scene '{self.scene_id}': no screenshot of {self.entry.posix} at t={t:.3f}: {first_line(exc)}") from None
        return png_pixels(png, self.size, f"scene '{self.scene_id}': the page")

    def close(self) -> None:
        """Close Chromium and Playwright (safe to call twice)."""
        if self._chromium is not None:
            self._chromium.close()
        self._chromium = self._page = None


__all__ = ["CANVAS_PATH", "READY_TIMEOUT_MS", "WEB_ORIGIN", "WebPage", "canvas_page", "content_type", "engine_id",
           "error_location", "error_message", "project_path", "runtime_digest"]
