"""The studio's local web server (DESIGN.md §94.1, §94.2): standard library only
(:class:`http.server.ThreadingHTTPServer`), bound to 127.0.0.1, serving the page (package data,
no build step, no CDN), the bundled fonts, the JSON API of :class:`StudioApp` and the rendered
audio with HTTP range requests (so the browser can seek).

Guards: the ``Host`` header must name this server (no DNS rebinding); a POST must be JSON
(``Content-Type: application/json``, which a cross-site form cannot send without a CORS
preflight this server never answers) from no or the same origin; static and audio files are
served from allow-lists and name patterns only (no path from a request reaches the disk).
"""

from __future__ import annotations

import json
import logging
import re
import socket
import sys
import threading
import traceback
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from vidgen.errors import VidgenError
from vidgen.studio_app.app import StudioApp

log = logging.getLogger("vidgen.studio")

#: The page's files (package data).
STATIC_DIR = Path(__file__).parent / "static"
#: The bundled fonts the page uses (``/fonts/<file>``).
FONT_FILES = {
    "Inter-Regular.ttf": ("Inter", "Inter-Regular.ttf"),
    "Inter-Bold.ttf": ("Inter", "Inter-Bold.ttf"),
    "JetBrainsMonoNL-Regular.ttf": ("JetBrainsMono", "JetBrainsMonoNL-Regular.ttf"),
}
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ttf": "font/ttf",
    ".wav": "audio/wav",
    ".json": "application/json",
}
#: The biggest request body accepted (a score's text is a few KB).
MAX_BODY_BYTES = 2_000_000
#: Bytes sent per write when streaming a file.
CHUNK_BYTES = 256 * 1024
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
#: A client that went away mid-request (Windows says "aborted").
_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
CSP = "default-src 'self'; media-src 'self' blob:; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'"


def static_files() -> dict[str, Path]:
    """URL path → file for the page: ``/`` and ``/static/<name>`` for every file shipped in
    :data:`STATIC_DIR` (listed once; nothing else is served from it), and the fonts."""
    from vidgen.fonts import FONTS_DIR

    files = {f"/static/{p.name}": p for p in sorted(STATIC_DIR.iterdir()) if p.is_file() and p.suffix in MIME_TYPES}
    files["/"] = STATIC_DIR / "index.html"
    for name, (family, file) in FONT_FILES.items():
        files[f"/fonts/{name}"] = FONTS_DIR / family / file
    return files


class _ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def _byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """The ``(first, last)`` bytes (inclusive) a ``Range`` header asks for; ``None`` for the
    whole file (no header, or one this server does not handle, e.g. several ranges);
    :class:`_ApiError` 416 when the range is outside the file."""
    if not header:
        return None
    m = _RANGE.match(header.strip())
    if m is None:
        return None
    first_text, last_text = m.groups()
    if first_text == "" and last_text == "":
        return None
    if first_text == "":  # the last N bytes
        count = int(last_text)
        if count == 0:
            raise _ApiError(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "empty range")
        return max(0, size - count), size - 1
    first = int(first_text)
    last = min(int(last_text), size - 1) if last_text else size - 1
    if first >= size or last < first:
        raise _ApiError(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, f"range outside the file ({size} bytes)")
    return first, last


class StudioServer(ThreadingHTTPServer):
    """The HTTP server of one studio: its app, its static files and the hosts it answers to."""

    daemon_threads = True

    def __init__(self, app: StudioApp, port: int = 0) -> None:
        self.app = app
        self.files = static_files()
        try:
            super().__init__(("127.0.0.1", port), _Handler)
        except OSError as exc:
            raise VidgenError(f"studio: cannot listen on 127.0.0.1:{port} ({exc.strerror or exc}); give another --port, or none for a free one") from None
        self.port = int(self.server_address[1])
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.url = f"http://127.0.0.1:{self.port}/"
        app.url = self.url

    def handle_error(self, request: Any, client_address: Any) -> None:
        if isinstance(sys.exc_info()[1], _GONE):  # the browser dropped a connection (seeking, reloading)
            return
        super().handle_error(request, client_address)

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: never share the port with another process
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.allow_reuse_address = False
        super().server_bind()


class _Handler(BaseHTTPRequestHandler):
    server: StudioServer
    protocol_version = "HTTP/1.1"
    server_version = "vidgen-studio"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base class's name
        log.debug("%s " + format, self.address_string(), *args)

    # ----- routing -------------------------------------------------------------------------

    def do_GET(self) -> None:
        self._dispatch(self._get)

    def do_HEAD(self) -> None:
        self._dispatch(self._get)

    def do_POST(self) -> None:
        self._dispatch(self._post)

    def _dispatch(self, route: Callable[[str, dict[str, list[str]]], None]) -> None:
        try:
            if self.headers.get("Host", "") not in self.server.hosts:
                raise _ApiError(HTTPStatus.FORBIDDEN, "unknown Host: the studio answers only to 127.0.0.1 and localhost")
            parts = urlsplit(self.path)
            route(parts.path, parse_qs(parts.query))
        except _ApiError as exc:
            self._send_json({"ok": False, "error": str(exc)}, exc.status)
        except VidgenError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except _GONE:
            pass  # the browser stopped reading (e.g. it seeked); nothing to answer
        except Exception as exc:  # noqa: BLE001 - one bad request must not stop the studio
            log.error("studio: %s %s failed: %s", self.command, self.path, traceback.format_exc())
            try:
                self._send_json({"ok": False, "error": f"internal error: {type(exc).__name__}: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            except OSError:
                pass

    def _get(self, path: str, query: dict[str, list[str]]) -> None:
        app = self.server.app
        if path in self.server.files:
            return self._send_file(self.server.files[path], cache=False)
        if path.startswith("/audio/"):
            found = app.audio_file(path[len("/audio/") :])
            if found is None:
                raise _ApiError(HTTPStatus.NOT_FOUND, "no such render")
            return self._send_file(found, cache=True)
        routes: dict[str, Callable[[], Any]] = {
            "/api/info": app.info,
            "/api/presets": app.presets,
            "/api/patches": app.patches,
            "/api/session": app.state,
        }
        if path in routes:
            return self._send_json({"ok": True, "result": routes[path]()})
        if path == "/api/score":
            return self._send_json({"ok": True, "result": app.score(_int(query.get("version", [""])[0], "version"))})
        raise _ApiError(HTTPStatus.NOT_FOUND, f"not found: {path}")

    def _post(self, path: str, query: dict[str, list[str]]) -> None:
        body = self._json_body()
        app = self.server.app
        if path == "/api/load":
            result = app.load(preset=_opt_str(body, "preset"), text=_opt_str(body, "text"), title=_opt_str(body, "title"))
        elif path == "/api/validate":
            result = app.validate(_req_str(body, "text"))
        elif path == "/api/render":
            version = body.get("version")
            result = app.render(_int(version, "version") if version is not None else None, _opt_str(body, "section"), _str_list(body, "mute"))
        elif path == "/api/edit":
            version, ops = body.get("version"), body.get("ops")
            if not isinstance(ops, list):
                raise _ApiError(HTTPStatus.BAD_REQUEST, "ops: expected a list of edits")
            result = app.edit(_int(version, "version") if version is not None else None, ops, _opt_str(body, "label"), bool(body.get("dry_run", False)))
        else:
            raise _ApiError(HTTPStatus.NOT_FOUND, f"not found: {path}")
        self._send_json({"ok": True, "result": result})

    # ----- requests and responses ----------------------------------------------------------

    def _json_body(self) -> dict[str, Any]:
        origin = self.headers.get("Origin")
        if origin is not None and urlsplit(origin).netloc not in self.server.hosts:
            raise _ApiError(HTTPStatus.FORBIDDEN, "requests from other sites are refused")
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise _ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send JSON (Content-Type: application/json)")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise _ApiError(HTTPStatus.BAD_REQUEST, "bad Content-Length") from None
        if length > MAX_BODY_BYTES:
            raise _ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"request too large (at most {MAX_BODY_BYTES} bytes)")
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            raise _ApiError(HTTPStatus.BAD_REQUEST, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise _ApiError(HTTPStatus.BAD_REQUEST, "the body must be a JSON object")
        return body

    def _common_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Referrer-Policy", "no-referrer")

    def _send_json(self, doc: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._common_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _send_file(self, path: Path, cache: bool) -> None:
        """Send ``path``, or the byte range the request asks for (206 Partial Content)."""
        size = path.stat().st_size
        byte_range = _byte_range(self.headers.get("Range"), size)
        first, last = byte_range if byte_range is not None else (0, size - 1)
        self.send_response(HTTPStatus.PARTIAL_CONTENT if byte_range is not None else HTTPStatus.OK)
        self.send_header("Content-Type", MIME_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(max(0, last - first + 1)))
        self.send_header("Accept-Ranges", "bytes")
        if byte_range is not None:
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        # a render's name is its content's key, so it never changes; the page's files may
        self.send_header("Cache-Control", "private, max-age=31536000, immutable" if cache else "no-cache")
        self._common_headers()
        self.end_headers()
        if self.command == "HEAD" or size == 0:
            return
        with path.open("rb") as handle:
            handle.seek(first)
            left = last - first + 1
            while left > 0:
                chunk = handle.read(min(CHUNK_BYTES, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)


def _int(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise _ApiError(HTTPStatus.BAD_REQUEST, f"{name}: expected a whole number, got {value!r}") from None


def _opt_str(body: dict[str, Any], name: str) -> str | None:
    value = body.get(name)
    if value is not None and not isinstance(value, str):
        raise _ApiError(HTTPStatus.BAD_REQUEST, f"{name}: expected text")
    return value


def _str_list(body: dict[str, Any], name: str) -> list[str]:
    value = body.get(name) or []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _ApiError(HTTPStatus.BAD_REQUEST, f"{name}: expected a list of names")
    return value


def _req_str(body: dict[str, Any], name: str) -> str:
    value = _opt_str(body, name)
    if value is None:
        raise _ApiError(HTTPStatus.BAD_REQUEST, f"{name}: missing")
    return value


def start_in_thread(app: StudioApp, port: int = 0) -> tuple[StudioServer, threading.Thread]:
    """Start a studio server on a background thread (for tests and embedding); stop it with
    ``server.shutdown()`` then ``server.server_close()``."""
    server = StudioServer(app, port)
    thread = threading.Thread(target=server.serve_forever, name="vidgen-studio", daemon=True)
    thread.start()
    return server, thread
