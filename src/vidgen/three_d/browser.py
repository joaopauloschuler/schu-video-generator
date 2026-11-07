"""Draw a scene description's frames with three.js in headless Chromium (DESIGN.md §114.4).

One browser per scene render: :class:`PageRenderer` launches Chromium through Playwright, serves
the page and the vendored three.js from ``vidgen/data/three`` on a made-up origin (every other
request is refused, so nothing is fetched from the network), loads the description and returns
frame ``n`` at ``t = n / fps``. WebGL runs on SwiftShader (Chromium's software GL), so the pixels
do not depend on the graphics card. :func:`write_clip` writes all frames, in order, to a
lossless FFV1 clip.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
from collections.abc import Callable
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from types import TracebackType
from typing import Any

import numpy as np

from vidgen import DIST_NAME
from vidgen.errors import VidgenError

#: The vendored three.js build and vidgen's page.
PAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "three"
#: Files the page is made of (served to the browser and part of the cache key).
PAGE_FILES: tuple[str, ...] = ("page.html", "vidgen3d.js", "three.module.js", "three.core.js")
#: The origin the page is served on (``.invalid`` never resolves; requests are answered locally).
PAGE_ORIGIN = "http://vidgen-3d.invalid/"
#: Chromium flags: WebGL through ANGLE on SwiftShader (same pixels on every machine).
CHROMIUM_ARGS: tuple[str, ...] = ("--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist")
#: How long loading the page may take (milliseconds).
LOAD_TIMEOUT_MS = 60_000
_CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8"}

INSTALL_HINT = (
    f'3D scenes need Playwright and its Chromium: pip install "{DIST_NAME}[3d]", then '
    "python -m playwright install chromium (Windows: py -m pip install "
    f'"{DIST_NAME}[3d]", then py -m playwright install chromium)'
)
BROWSER_HINT = (
    "Playwright's Chromium is not installed: run python -m playwright install chromium "
    "(Windows: py -m playwright install chromium)"
)


def _sync_api() -> Any:
    try:
        from playwright import sync_api
    except ImportError:
        raise VidgenError(INSTALL_HINT) from None
    return sync_api


def playwright_version() -> str | None:
    """The installed Playwright version (it fixes the Chromium build), or ``None``."""
    try:
        return metadata.version("playwright")
    except metadata.PackageNotFoundError:
        return None


@lru_cache(maxsize=1)
def page_digest() -> str:
    """Digest of the page files (vidgen's page and the vendored three.js)."""
    digest = hashlib.sha256()
    for name in PAGE_FILES:
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256((PAGE_DIR / name).read_bytes()).digest())
    return digest.hexdigest()


def engine_id() -> str:
    """What draws the frames, for the cache key: the page digest and the Playwright version."""
    return f"page={page_digest()} playwright={playwright_version() or 'none'}"


def _serve(route: Any) -> None:
    """Answer the page's requests from :data:`PAGE_DIR`; refuse everything else."""
    url = route.request.url
    name = url[len(PAGE_ORIGIN):].split("?", 1)[0] if url.startswith(PAGE_ORIGIN) else ""
    if name not in PAGE_FILES:
        route.abort()
        return
    path = PAGE_DIR / name
    route.fulfill(status=200, body=path.read_bytes(), headers={"Content-Type": _CONTENT_TYPES[path.suffix]})


def _browser_error(exc: Exception) -> VidgenError:
    text = str(exc)
    if "Executable doesn't exist" in text or "playwright install" in text:
        return VidgenError(BROWSER_HINT)
    return VidgenError(f"cannot start Chromium for a 3D scene: {text.splitlines()[0] if text else exc!r}")


class PageRenderer:
    """``with PageRenderer(description) as page: page.frame(n)`` -> an RGB array (H x W x 3).

    Starts Playwright and Chromium on enter, closes both on exit. Errors of the page (a bad
    description, a WebGL failure) become :class:`VidgenError`."""

    def __init__(self, description: dict[str, Any]) -> None:
        self.description = description
        self.fps = int(description["fps"])
        self.size = (int(description["width"]), int(description["height"]))
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._errors: list[str] = []

    def __enter__(self) -> PageRenderer:
        sync_api = _sync_api()
        try:
            self._playwright = sync_api.sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True, args=list(CHROMIUM_ARGS))
        except Exception as exc:  # noqa: BLE001 - Playwright raises its own Error types
            self.close()
            raise _browser_error(exc) from None
        try:
            width, height = self.size
            context = self._browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
            context.route("**/*", _serve)
            self._page = page = context.new_page()
            page.on("pageerror", lambda e: self._errors.append(str(e)))
            page.goto(PAGE_ORIGIN + "page.html", timeout=LOAD_TIMEOUT_MS)
            page.wait_for_function("() => window.vidgen3d !== undefined", timeout=LOAD_TIMEOUT_MS)
            self._call("d => window.vidgen3d.load(d)", self.description)
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def _call(self, script: str, arg: Any) -> Any:
        sync_api = _sync_api()
        try:
            return self._page.evaluate(script, arg)
        except sync_api.Error as exc:
            first = str(exc).splitlines()[0] if str(exc) else repr(exc)
            raise VidgenError(f"3D page: {first}") from None

    def frame(self, n: int) -> np.ndarray:
        """Frame ``n`` (time ``n / fps``) as RGB pixels."""
        from PIL import Image

        url = self._call("t => window.vidgen3d.frame(t)", n / self.fps)
        if self._errors:
            raise VidgenError(f"3D page: {self._errors[0]}")
        png = base64.b64decode(url.split(",", 1)[1])
        with Image.open(io.BytesIO(png)) as im:
            pixels = np.asarray(im.convert("RGB"))
        if pixels.shape[1::-1] != self.size:
            raise VidgenError(f"3D page drew {pixels.shape[1]}x{pixels.shape[0]} px, expected {self.size[0]}x{self.size[1]}")
        return pixels

    def close(self) -> None:
        """Close Chromium and Playwright (safe to call twice)."""
        for closer in (self._browser, self._playwright):
            if closer is None:
                continue
            try:
                closer.close() if closer is self._browser else closer.stop()
            except Exception:  # noqa: BLE001 - already gone
                pass
        self._browser = self._playwright = self._page = None


def write_clip(description: dict[str, Any], path: Path, progress: Callable[[int, int], None] | None = None) -> None:
    """Draw every frame of ``description`` in order and write them to ``path`` (FFV1 in
    Matroska, lossless RGB); written to a ``.partial`` file first, so a failure leaves none."""
    import av

    frames, fps = int(description["frames"]), int(description["fps"])
    width, height = int(description["width"]), int(description["height"])
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    try:
        with PageRenderer(description) as page, av.open(str(partial), mode="w", format="matroska") as container:
            stream = container.add_stream("ffv1", rate=fps)
            stream.width, stream.height, stream.pix_fmt = width, height, "bgr0"
            for n in range(frames):
                frame = av.VideoFrame.from_ndarray(page.frame(n), format="rgb24").reformat(format="bgr0")
                frame.pts = n
                container.mux(stream.encode(frame))
                if progress is not None:
                    progress(n + 1, frames)
            container.mux(stream.encode())
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


__all__ = ["BROWSER_HINT", "INSTALL_HINT", "PageRenderer", "engine_id", "page_digest", "playwright_version", "write_clip"]
