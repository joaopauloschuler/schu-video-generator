"""Draw a scene description's frames with three.js in headless Chromium (DESIGN.md §114.4).

One browser per scene render: :class:`PageRenderer` starts Chromium (:class:`~vidgen.browser.chromium.Chromium`,
shared with the ``web`` scene), serves the page and the vendored three.js from ``vidgen/data/three``
on a made-up origin (every other request is refused, so nothing is fetched from the network),
loads the description and returns frame ``n`` at ``t = n / fps``. :func:`write_clip` writes all
frames, in order, to a lossless FFV1 clip.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from pathlib import Path
from types import TracebackType
from typing import Any

import numpy as np

from vidgen.browser import chromium
from vidgen.browser.chromium import Chromium, first_line, playwright_version, png_pixels, write_ffv1_clip
from vidgen.errors import VidgenError
from vidgen.fonts import FONTS_DIR

#: The vendored three.js build and vidgen's page.
PAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "three"
#: Files the page is made of (served to the browser and part of the cache key).
PAGE_FILES: tuple[str, ...] = ("page.html", "vidgen3d.js", "three.module.js", "three.core.js")
#: Other files served to the page, by the name it asks for: the labels' font (bundled Inter Bold).
EXTRA_FILES: dict[str, Path] = {"inter-bold.ttf": FONTS_DIR / "Inter" / "Inter-Bold.ttf"}
#: The origin the page is served on (``.invalid`` never resolves; requests are answered locally).
PAGE_ORIGIN = "http://vidgen-3d.invalid/"
#: How long loading the page may take (milliseconds).
LOAD_TIMEOUT_MS = 60_000
_CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".ttf": "font/ttf"}


@lru_cache(maxsize=1)
def page_digest() -> str:
    """Digest of the page files (vidgen's page, the vendored three.js, the labels' font)."""
    digest = hashlib.sha256()
    for name, path in _served().items():
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _served() -> dict[str, Path]:
    """Every file the page may ask for, by name."""
    return {**{name: PAGE_DIR / name for name in PAGE_FILES}, **EXTRA_FILES}


def engine_id() -> str:
    """What draws the frames, for the cache key: the page digest and the Playwright version."""
    return f"page={page_digest()} playwright={playwright_version() or 'none'}"


def _serve(route: Any) -> None:
    """Answer the page's requests from :data:`PAGE_DIR`; refuse everything else."""
    url = route.request.url
    name = url[len(PAGE_ORIGIN):].split("?", 1)[0] if url.startswith(PAGE_ORIGIN) else ""
    path = _served().get(name)
    if path is None:
        route.abort()
        return
    route.fulfill(status=200, body=path.read_bytes(), headers={"Content-Type": _CONTENT_TYPES[path.suffix]})


class PageRenderer:
    """``with PageRenderer(description) as page: page.frame(n)`` -> an RGB array (H x W x 3).

    Starts Playwright and Chromium on enter, closes both on exit. Errors of the page (a bad
    description, a WebGL failure) become :class:`VidgenError`."""

    def __init__(self, description: dict[str, Any]) -> None:
        self.description = description
        self.fps = int(description["fps"])
        self.size = (int(description["width"]), int(description["height"]))
        self._chromium: Chromium | None = None
        self._page: Any = None
        self._errors: list[str] = []

    def __enter__(self) -> PageRenderer:
        api = chromium.sync_api()
        self._chromium = Chromium("a 3D scene").__enter__()
        try:
            width, height = self.size
            context = self._chromium.browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
            context.route("**/*", _serve)
            self._page = page = context.new_page()
            page.on("pageerror", lambda e: self._errors.append(str(e)))
            page.goto(PAGE_ORIGIN + "page.html", timeout=LOAD_TIMEOUT_MS)
            page.wait_for_function("() => window.vidgen3d !== undefined", timeout=LOAD_TIMEOUT_MS)
        except api.Error as exc:   # a timeout, a crashed page: a message, not a traceback
            self.close()
            raise VidgenError(f"3D page did not load: {self._errors[0] if self._errors else first_line(exc)}") from None
        except BaseException:
            self.close()
            raise
        try:
            self._call("d => window.vidgen3d.load(d)", self.description)
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def _call(self, script: str, arg: Any) -> Any:
        api = chromium.sync_api()
        try:
            return self._page.evaluate(script, arg)
        except api.Error as exc:
            raise VidgenError(f"3D page: {first_line(exc)}") from None

    def frame(self, n: int) -> np.ndarray:
        """Frame ``n`` (time ``n / fps``) as RGB pixels."""
        url = self._call("t => window.vidgen3d.frame(t)", n / self.fps)
        if self._errors:
            raise VidgenError(f"3D page: {self._errors[0]}")
        return png_pixels(base64.b64decode(url.split(",", 1)[1]), self.size, "3D page")

    def close(self) -> None:
        """Close Chromium and Playwright (safe to call twice)."""
        if self._chromium is not None:
            self._chromium.close()
        self._chromium = self._page = None


def write_clip(description: dict[str, Any], path: Path) -> None:
    """Draw every frame of ``description`` in order and write them to ``path`` (FFV1 in
    Matroska, lossless RGB); written to a ``.partial`` file first, so a failure leaves none."""
    frames, fps = int(description["frames"]), int(description["fps"])
    size = (int(description["width"]), int(description["height"]))
    with PageRenderer(description) as page:
        write_ffv1_clip(path, fps, size, (page.frame(n) for n in range(frames)))


__all__ = ["PageRenderer", "engine_id", "page_digest", "write_clip"]
