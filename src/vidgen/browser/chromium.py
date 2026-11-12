"""Headless Chromium through Playwright for the scenes drawn in a browser (``3d``, ``web``;
DESIGN.md §114.4, §118).

:class:`Chromium` starts Playwright and one Chromium and stops both; :func:`missing_dependency`
checks cheaply (no browser started) that Playwright and its Chromium are installed;
:func:`write_ffv1_clip` writes frames, in order, to a lossless FFV1 clip. WebGL runs on
SwiftShader (Chromium's software GL), so the pixels do not depend on the graphics card.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from importlib import metadata
from pathlib import Path
from types import TracebackType
from typing import Any

import numpy as np

from vidgen.errors import incomplete_install, VidgenError

#: Chromium flags: WebGL through ANGLE on SwiftShader (same pixels on every machine).
CHROMIUM_ARGS: tuple[str, ...] = ("--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist")
#: The scene types drawn in Chromium (``vidgen validate`` warns when it is missing).
BROWSER_SCENE_TYPES: tuple[str, ...] = ("3d", "web")

INSTALL_HINT = (
    f'3d and web scenes need Playwright and its Chromium: {incomplete_install("Playwright")}, then '
    "python -m playwright install chromium (Windows: py -m playwright install chromium)"
)
BROWSER_HINT = (
    "Playwright's Chromium is not installed: run python -m playwright install chromium "
    "(Windows: py -m playwright install chromium)"
)


def sync_api() -> Any:
    """Playwright's ``sync_api`` module; :data:`INSTALL_HINT` as a :class:`VidgenError` without it."""
    try:
        from playwright import sync_api as api
    except ImportError:
        raise VidgenError(INSTALL_HINT) from None
    return api


def playwright_version() -> str | None:
    """The installed Playwright version (it fixes the Chromium build), or ``None``."""
    try:
        return metadata.version("playwright")
    except metadata.PackageNotFoundError:
        return None


def first_line(exc: BaseException) -> str:
    """The first line of an exception's text (Playwright appends call logs), or its repr."""
    text = str(exc)
    return text.splitlines()[0] if text else repr(exc)


def _browsers_dir() -> Path:
    """Where Playwright keeps its browsers (``PLAYWRIGHT_BROWSERS_PATH``, else its default per system)."""
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env == "0":
        import playwright

        return Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ms-playwright"


def missing_dependency() -> str | None:
    """Why a ``3d`` or ``web`` scene could not render here (:data:`INSTALL_HINT` or
    :data:`BROWSER_HINT`), or ``None``; a cheap check (no browser started): Playwright
    importable, and the folder of the Chromium build it pins present. Unknown (its
    ``browsers.json`` unreadable): ``None``."""
    import importlib.util

    spec = importlib.util.find_spec("playwright")
    if spec is None:
        return INSTALL_HINT
    origin = Path(spec.origin).parent if spec.origin else None
    try:
        listed = json.loads((origin / "driver" / "package" / "browsers.json").read_text(encoding="utf-8"))["browsers"]  # type: ignore[operator]
        folders = [f"{b['name'].replace('-', '_')}-{b['revision']}" for b in listed if b["name"] in ("chromium", "chromium-headless-shell")]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not folders:
        return None
    root = _browsers_dir()
    return None if any((root / f).is_dir() for f in folders) else BROWSER_HINT


def install_warnings(project: Any) -> list[str]:
    """``vidgen validate``'s warning, one per scene type drawn in Chromium that the project
    uses, when :func:`missing_dependency` finds Playwright or its Chromium missing."""
    used = {kind: [s.id for s in project.config.scenes if s.type == kind] for kind in BROWSER_SCENE_TYPES}
    used = {kind: ids for kind, ids in used.items() if ids}
    problem = missing_dependency() if used else None
    if not problem:
        return []
    return [f"{kind} scenes ({', '.join(ids)}) cannot render here: {problem}" for kind, ids in used.items()]


def browser_error(exc: Exception, what: str) -> VidgenError:
    """The message for Chromium failing to start for ``what`` (``"a 3D scene"``)."""
    text = str(exc)
    if "Executable doesn't exist" in text or "playwright install" in text:
        return VidgenError(BROWSER_HINT)
    return VidgenError(f"cannot start Chromium for {what}: {first_line(exc)}")


class Chromium:
    """``with Chromium("a 3D scene") as chromium: chromium.browser.new_context(...)``.

    Starts Playwright and one headless Chromium (:data:`CHROMIUM_ARGS` plus ``extra_args``) on
    enter, stops both on exit (also :meth:`close`, safe to call twice). A failed start is a
    :class:`VidgenError` (:func:`browser_error`)."""

    def __init__(self, what: str, extra_args: tuple[str, ...] = ()) -> None:
        self.what = what
        self.args = CHROMIUM_ARGS + extra_args
        self.playwright: Any = None
        self.browser: Any = None

    def __enter__(self) -> Chromium:
        api = sync_api()
        try:
            self.playwright = api.sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True, args=list(self.args))
        except Exception as exc:  # noqa: BLE001 - Playwright raises its own Error types
            self.close()
            raise browser_error(exc, self.what) from None
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def close(self) -> None:
        """Close Chromium and Playwright (safe to call twice)."""
        for closer in (self.browser, self.playwright):
            if closer is None:
                continue
            try:
                closer.close() if closer is self.browser else closer.stop()
            except Exception:  # noqa: BLE001 - already gone
                pass
        self.browser = self.playwright = None


def write_ffv1_clip(path: Path, fps: int, size: tuple[int, int], frames: Iterable[np.ndarray], *, alpha: bool = False) -> None:
    """Write ``frames`` (RGB arrays, H x W x 3, ``size`` = (W, H); with ``alpha`` RGBA, H x W x 4,
    straight alpha, kept as ``bgra``) in order to ``path`` (FFV1 in Matroska, lossless); to a
    ``.partial`` file first, so a failure (also one raised while ``frames`` is iterated) leaves none."""
    import av

    width, height = size
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    try:
        with av.open(str(partial), mode="w", format="matroska") as container:
            stream = container.add_stream("ffv1", rate=fps)
            stored, given = ("bgra", "rgba") if alpha else ("bgr0", "rgb24")
            stream.width, stream.height, stream.pix_fmt = width, height, stored
            for n, pixels in enumerate(frames):
                frame = av.VideoFrame.from_ndarray(pixels, format=given).reformat(format=stored)
                frame.pts = n
                container.mux(stream.encode(frame))
            container.mux(stream.encode())
        try:
            os.replace(partial, path)
        except PermissionError:   # Windows: the old clip is open in another program (a player)
            raise VidgenError(f"cannot replace {path}: close the program that has it open and render again") from None
    finally:
        partial.unlink(missing_ok=True)


def png_pixels(png: bytes, size: tuple[int, int] | None, what: str, *, alpha: bool = False) -> np.ndarray:
    """A PNG's RGB pixels (RGBA with ``alpha``), checked to be ``size`` (W, H; ``None``: not
    checked); ``what`` names the page in the error."""
    import io

    from PIL import Image

    with Image.open(io.BytesIO(png)) as im:
        pixels = np.asarray(im.convert("RGBA" if alpha else "RGB"))
    if size is not None and pixels.shape[1::-1] != size:
        raise VidgenError(f"{what} drew {pixels.shape[1]}x{pixels.shape[0]} px, expected {size[0]}x{size[1]}")
    return pixels


__all__ = [
    "BROWSER_HINT", "BROWSER_SCENE_TYPES", "CHROMIUM_ARGS", "INSTALL_HINT", "Chromium", "browser_error", "first_line",
    "install_warnings", "missing_dependency", "playwright_version", "png_pixels", "sync_api", "write_ffv1_clip",
]
