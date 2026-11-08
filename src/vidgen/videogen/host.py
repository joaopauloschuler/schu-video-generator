"""Hosting a shot's audio / video inputs through a Cloudflare Quick Tunnel (DESIGN.md §115).

OpenRouter takes audio and video references only as ``https://`` URLs. :class:`QuickTunnelHost`
shares exactly the files it is given, for as short a time as it can:

1. it copies them into a fresh temporary folder outside the project (``tempfile.mkdtemp``) under
   new random names (the extension kept); symlinks and anything but regular files are refused;
2. :class:`ShareServer` (stdlib ``ThreadingHTTPServer``) serves that folder's files on
   127.0.0.1 at a random free port, only ``GET`` / ``HEAD`` of the exact paths
   ``/<secret>/<name>`` (``secrets.token_urlsafe(24)``); everything else is 404, with no
   directory listing and no ``Server`` header; requests are kept in memory (no client addresses);
3. :class:`TunnelProcess` starts ``cloudflared tunnel --url http://127.0.0.1:<port>
   --no-autoupdate [--protocol http2]`` and reads the ``https://<words>.trycloudflare.com``
   address from its output;
4. every file is checked through the public address (``HEAD``, retried while the new name
   reaches DNS) before anything is sent to a provider;
5. :meth:`QuickTunnelHost.close` stops cloudflared (its whole process tree), the server, and
   deletes the temporary folder: when the caller's ``with`` block ends (also on an error or
   Ctrl+C; for a paid run, when its job reaches a final state), or at the hard maximum lifetime,
   whichever comes first. A provider may fetch a file again after queueing the job, so a fetch
   never closes it early (the owner's decision, Step 309: a longer exposure, no lost paid job).
   Closing is resumable step by step; ``host_guard`` covers signals and a killed vidgen.

The ledger gets ``host_open`` (the host name only, never the secret path; each file's name,
size and SHA-256), ``host_fetch`` (file, method, status, bytes) and ``host_close`` (reason).
"""

from __future__ import annotations

import atexit
import hashlib
import http.client
import logging
import math
import mimetypes
import os
import re
import secrets
import shutil
import signal
import socketserver
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.videogen import host_guard
from vidgen.videogen.ledger import Ledger
from vidgen.videogen.openrouter import MEDIA_TYPES, Response

log = logging.getLogger("vidgen.videogen")

#: The address cloudflared prints for a quick tunnel (``api.trycloudflare.com`` is its own service).
QUICK_TUNNEL_URL = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com\b")
#: The line cloudflared logs once the tunnel reaches Cloudflare's edge.
REGISTERED_WORDS = "Registered tunnel connection"
PROTOCOLS = ("http2", "quic", "auto")
INSTALL_HINT = (
    "cloudflared was not found. Install it (free, no account needed for quick tunnels): "
    "Windows `winget install Cloudflare.cloudflared` (then open a new terminal), macOS `brew install cloudflared`, "
    "Linux: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ ; "
    "or set videogen: {cloudflared: <path to cloudflared>} in video.yaml"
)
_CHUNK = 64 * 1024
#: How long a second ``close`` waits for the first (longer than the first can take: the stop waits, the deletion retries).
CLOSE_WAIT_SECONDS = 30.0


@dataclass(frozen=True)
class HostSettings:
    """How a quick tunnel is run (from ``videogen:``, :meth:`from_config`)."""

    cloudflared: str | None = None
    protocol: str = "http2"
    max_seconds: float = 1200.0
    url_timeout: float = 60.0
    verify_timeout: float = 60.0
    verify_interval: float = 2.0
    #: Seconds kept free beyond the wait: the longest submit POST (120 s) and the last poll's sleep (60 s).
    submit_margin: float = 180.0

    @classmethod
    def from_config(cls, settings: Any) -> HostSettings:
        """From a :class:`vidgen.config.VideogenConfig`."""
        return cls(
            cloudflared=settings.cloudflared, protocol=settings.tunnel_protocol,
            max_seconds=settings.host_max_minutes * 60.0,
        )

    def lifetime_problem(self, poll_timeout: float) -> str | None:
        """Why a job waited on for ``poll_timeout`` s does not fit in this tunnel's lifetime (it
        could then be left waiting on a closed tunnel), else ``None``."""
        needed = poll_timeout + self.submit_margin + self.url_timeout
        if self.max_seconds >= needed:
            return None
        return (
            f"host_max_minutes ({self.max_seconds / 60:g} min) does not cover poll_timeout ({poll_timeout:g} s) plus opening the tunnel and submitting "
            f"({needed:.0f} s in all), so a job could be left waiting on a closed tunnel: set host_max_minutes to at least {math.ceil(needed / 60)} (at most 120), "
            f"or poll_timeout to at most {max(0, int(self.max_seconds - self.submit_margin - self.url_timeout))} s (vidgen then stops waiting sooner and closes "
            "the tunnel; the job keeps running and a later run polls it)"
        )


@dataclass(frozen=True)
class SharedFile:
    """One copy in the share folder: ``label`` names it in messages and the ledger (the source
    relative to the project, else its file name); ``name`` is its random name in the URL."""

    source: Path
    label: str
    name: str
    path: Path
    size: int
    sha256: str
    content_type: str

    def to_json(self) -> dict[str, Any]:
        """What the ledger records of it."""
        return {"name": self.label, "size": self.size, "sha256": self.sha256}


@dataclass(frozen=True)
class RequestRecord:
    """One request the share server answered (kept in memory; no client address)."""

    time: float
    method: str
    path: str
    status: int
    bytes: int
    file: str | None


def _label(source: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return source.absolute().relative_to(root.absolute()).as_posix()
        except ValueError:
            pass
    return source.name


def _content_type(suffix: str) -> str:
    if suffix in MEDIA_TYPES:
        return MEDIA_TYPES[suffix]
    if suffix == ".txt":
        return "text/plain; charset=utf-8"
    return mimetypes.types_map.get(suffix, "application/octet-stream")


def _safe_suffix(source: Path) -> str:
    suffix = source.suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ""


def _link_on_the_way(source: Path, root: Path | None) -> Path | None:
    """``source`` itself when it is a link, else the first folder between the project and it that
    is one (a link in ``build/videogen/<shot>/`` must not lead elsewhere; folders above the project
    are not checked). Windows junctions count as links (Python 3.12+ can tell them)."""
    if _is_link(source):
        return source
    if root is None:
        return None
    try:
        rest = source.absolute().relative_to(root.absolute()).parts[:-1]
    except ValueError:
        return None
    folder = root.absolute()
    for part in rest:
        folder = folder / part
        if _is_link(folder):
            return folder
    return None


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def copy_into_share(sources: Sequence[Path], folder: Path, root: Path | None = None) -> list[SharedFile]:
    """Copy each source into ``folder`` under a new random name (extension kept), with its size
    and SHA-256. Refuses a symlink, a missing file, anything but a regular file, and a source
    given twice."""
    shared: list[SharedFile] = []
    seen: set[Path] = set()
    for source in sources:
        source = Path(source)
        link = _link_on_the_way(source, root)
        if link is not None:
            raise VidgenError(f"{source}: {'is' if link == source else f'goes through {link}, which is'} a symbolic link; vidgen shares only regular files, never links")
        if not source.is_file():
            raise VidgenError(f"{source}: not a file, nothing to share")
        key = source.resolve()
        if key in seen:
            raise VidgenError(f"{source}: given twice")
        seen.add(key)
        name = secrets.token_hex(8) + _safe_suffix(source)
        dest = folder / name
        digest = hashlib.sha256()
        size = 0
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(source, flags)
        except OSError as exc:
            raise VidgenError(f"{source}: cannot be read ({exc.strerror})") from None
        with os.fdopen(fd, "rb") as src, dest.open("xb") as out:
            while chunk := src.read(_CHUNK):
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        shared.append(SharedFile(source, _label(source, root), name, dest, size, digest.hexdigest(), _content_type(_safe_suffix(source))))
    return shared


class _Handler(BaseHTTPRequestHandler):
    """Answers GET / HEAD of the exact shared paths; 404 for everything else."""

    server: ShareServer
    timeout = 30

    def send_response(self, code: int, message: str | None = None) -> None:
        # The base class adds ``Server: BaseHTTP/x Python/y``; nothing about the software is sent.
        self.send_response_only(code, message)
        self.send_header("Date", self.date_time_string())

    def log_message(self, format: str, *args: Any) -> None:   # noqa: A002 - the base class's name
        pass

    def do_GET(self) -> None:   # noqa: N802 - http.server's naming
        self._serve(with_body=True)

    def do_HEAD(self) -> None:   # noqa: N802
        self._serve(with_body=False)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("do_"):
            return self._not_found
        raise AttributeError(name)

    def _not_found(self) -> None:
        body = b"not found\n"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.server.record(self.command, self.path, 404, 0, None)

    def _serve(self, *, with_body: bool) -> None:
        shared = self.server.files.get(self.path)
        if shared is None:
            self._not_found()
            return
        self.send_response(200)
        self.send_header("Content-Type", shared.content_type)
        self.send_header("Content-Length", str(shared.size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        sent = 0
        status = 200
        if with_body:
            try:
                with shared.path.open("rb") as f:
                    while chunk := f.read(_CHUNK):
                        self.wfile.write(chunk)
                        sent += len(chunk)
            except OSError:
                status = 499   # the client went away (or the share folder is gone): an incomplete fetch
        self.server.record(self.command, self.path, status, sent, shared)


class ShareServer(ThreadingHTTPServer):
    """The local HTTP server of one share: 127.0.0.1, a random free port, ``files`` by their URL
    path ``/<secret>/<name>``. ``on_request(record, shared)`` hears every answered request."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, shared: Iterable[SharedFile], secret: str, on_request: Callable[[RequestRecord, SharedFile | None], None] | None = None) -> None:
        self.secret = secret
        self.files: dict[str, SharedFile] = {f"/{secret}/{s.name}": s for s in shared}
        self.requests: list[RequestRecord] = []
        self._lock = threading.Lock()
        self._on_request = on_request
        self._thread: threading.Thread | None = None
        super().__init__(("127.0.0.1", 0), _Handler)

    def server_bind(self) -> None:
        # HTTPServer.server_bind looks up the host's full name (slow on some networks); not needed.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]

    @property
    def port(self) -> int:
        """The port it listens on."""
        return int(self.server_address[1])

    def record(self, method: str, path: str, status: int, sent: int, shared: SharedFile | None) -> None:
        """Keep one answered request (the secret is never kept, even in a wrong path)."""
        shown = path.replace(self.secret, "<secret>")[:200]
        entry = RequestRecord(time.time(), method, shown, status, sent, shared.label if shared else None)
        with self._lock:
            self.requests.append(entry)
        if self._on_request is not None:
            self._on_request(entry, shared)

    def start(self) -> None:
        """Serve in a background thread."""
        self._thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.2}, name="vidgen-share-server", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and close the socket."""
        if self._thread is not None:
            self.shutdown()
            self._thread.join(5)
            self._thread = None
        self.server_close()


def find_cloudflared(setting: str | None = None, which: Callable[[str], str | None] = shutil.which, environ: Mapping[str, str] | None = None) -> str:
    """The cloudflared program: ``videogen.cloudflared`` (a path or a command name), else
    ``cloudflared`` on PATH, else (Windows) where winget installs it; a :class:`VidgenError`
    with install hints when there is none."""
    if setting:
        path = Path(setting).expanduser()
        if path.is_file():
            return str(path)
        found = which(setting)
        if found:
            return found
        raise VidgenError(f"videogen.cloudflared: {setting} not found. {INSTALL_HINT}")
    found = which("cloudflared")
    if found:
        return found
    env = os.environ if environ is None else environ
    for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = env.get(var)
        if base:
            candidate = Path(base) / "cloudflared" / "cloudflared.exe"
            if candidate.is_file():
                return str(candidate)
    raise VidgenError(INSTALL_HINT)


def tunnel_command(executable: Sequence[str], port: int, protocol: str = "http2") -> list[str]:
    """The cloudflared command line of a quick tunnel to ``127.0.0.1:port``."""
    if protocol not in PROTOCOLS:
        raise VidgenError(f"tunnel protocol {protocol!r}: use one of {', '.join(PROTOCOLS)}")
    command = [*executable, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"]
    if protocol != "auto":
        command += ["--protocol", protocol]
    return command


def _start_process(command: list[str], keep_fds: Sequence[int] = ()) -> subprocess.Popen[str]:
    """Start ``command`` in its own process group (so it can be stopped as a tree, and Ctrl+C in
    the terminal reaches vidgen, which then stops it). ``keep_fds`` (POSIX) stay open in it."""
    options: dict[str, Any] = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
        options["pass_fds"] = tuple(keep_fds)
    return subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", **options,
    )


def stop_process_tree(process: subprocess.Popen[Any], wait_seconds: float = 5.0) -> None:
    """Stop ``process`` and every process it started (Windows: ``taskkill /T /F``; elsewhere its
    process group: SIGTERM, then SIGKILL)."""
    if os.name == "nt":
        taskkill = shutil.which("taskkill")
        if process.poll() is None and taskkill:
            # check=False: taskkill fails when the process ended in between, which is the goal.
            subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        elif process.poll() is None:
            process.kill()   # no taskkill: at least cloudflared itself
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(wait_seconds)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        process.kill()
        process.wait(wait_seconds)
    if process.stdout is not None:
        process.stdout.close()


class TunnelProcess:
    """A running ``cloudflared`` quick tunnel; its output is read in a thread (kept: the last 200 lines)."""

    def __init__(self, command: list[str], start: Callable[[list[str]], subprocess.Popen[str]] = _start_process) -> None:
        try:
            self.process = start(command)
        except OSError as exc:
            raise VidgenError(f"cannot start cloudflared ({command[0]}): {exc}. {INSTALL_HINT}") from None
        self.lines: deque[str] = deque(maxlen=200)
        self.url: str | None = None
        self._url_found = threading.Event()
        self._registered = threading.Event()
        self._ended = threading.Event()
        self._reader = threading.Thread(target=self._read, name="vidgen-cloudflared-output", daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        try:
            for line in self.process.stdout:
                self.lines.append(line.rstrip())
                if self.url is None and (match := QUICK_TUNNEL_URL.search(line)):
                    self.url = match.group(0)
                    self._url_found.set()
                if REGISTERED_WORDS in line:
                    self._registered.set()
        except (OSError, ValueError):
            pass
        finally:
            self._ended.set()

    def output(self, last: int = 12) -> str:
        """The last lines cloudflared printed."""
        return "\n".join(list(self.lines)[-last:]) or "(nothing)"

    def wait_for_url(self, timeout: float) -> str:
        """The public address, once cloudflared printed it (a :class:`VidgenError` when it ends or
        prints none within ``timeout`` seconds)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._url_found.wait(0.1):
                assert self.url is not None
                return self.url
            if self._ended.is_set() and self.process.poll() is not None:
                raise VidgenError(
                    f"cloudflared stopped (exit code {self.process.returncode}) without a quick tunnel address. Its last lines:\n{self.output()}\n"
                    "Check the network allows outgoing connections to Cloudflare (port 7844, or 443 with tunnel_protocol: http2), "
                    "and that no ~/.cloudflared/config.yml changes what `cloudflared tunnel` does"
                )
        raise VidgenError(f"cloudflared printed no quick tunnel address within {timeout:g} s. Its last lines:\n{self.output()}")

    def wait_registered(self, timeout: float) -> bool:
        """Wait (at most ``timeout`` s) until cloudflared logs its connection to Cloudflare."""
        return self._registered.wait(timeout)

    def stop(self) -> None:
        """Stop cloudflared and its child processes."""
        stop_process_tree(self.process)
        self._reader.join(2)


#: ``fetch(method, url, timeout) -> Response``; raises :class:`OSError` / :class:`VidgenError`
#: when the address cannot be reached.
Fetch = Callable[[str, str, float], Response]


def urllib_fetch(method: str, url: str, timeout: float) -> Response:
    """One request through the real network (urllib; the system's proxy settings apply)."""
    request = urllib.request.Request(url, method=method, headers={"User-Agent": "vidgen-host-check"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return Response(answer.status, answer.read(), {k.lower(): v for k, v in answer.headers.items()})
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.read(), {k.lower(): v for k, v in (exc.headers or {}).items()})
    except (urllib.error.URLError, http.client.HTTPException, ValueError) as exc:
        raise OSError(str(getattr(exc, "reason", exc))) from None


def verify_public(url: str, shared: SharedFile, fetch: Fetch, *, timeout: float, interval: float, sleep: Callable[[float], None] = time.sleep) -> int:
    """Ask the public address for ``shared`` (HEAD) until it answers 200 with the file's length (or
    no length: a proxy may leave it out of a HEAD answer; a wrong length is refused),
    retrying every ``interval`` s for ``timeout`` s (a new quick tunnel name takes a few seconds
    to reach DNS); returns the attempts. A :class:`VidgenError` with the last answer otherwise."""
    deadline = time.monotonic() + timeout
    attempts = 0
    last = "no answer"
    while True:
        attempts += 1
        try:
            answer = fetch("HEAD", url, min(15.0, max(1.0, timeout)))
            length = answer.headers.get("content-length")
            if answer.status == 200 and (length is None or length == str(shared.size)):
                return attempts
            last = f"HTTP {answer.status}" + (f", length {length} instead of {shared.size}" if answer.status == 200 else "")
        except (OSError, VidgenError) as exc:
            last = f"{type(exc).__name__}: {exc}"
        if time.monotonic() + interval > deadline:
            raise VidgenError(
                f"the quick tunnel's public address never served {shared.label} within {timeout:g} s ({attempts} tries; last: {last}); "
                "nothing was sent to a provider. Try again, or `vidgen generate host-test` to check the tunnel alone"
            )
        sleep(interval)


@dataclass
class _State:
    opened_at: float = 0.0
    close_reason: str | None = None
    #: The thread running the close steps, ``None`` while none does.
    closer: int | None = None
    finished_steps: set[str] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)
    tunnel_stopped: bool = False
    folder_deleted: bool = False


class QuickTunnelHost:
    """Shares ``sources`` through a quick tunnel for as short a time as possible (module docstring).

    Use it as a context manager: ``with QuickTunnelHost(paths, ...) as host: host.url_of(path)``.
    ``open`` returns only once every file was checked through the public address. ``ledger``
    (optional) records ``host_open`` / ``host_fetch`` / ``host_close``. ``executable`` (the
    cloudflared command, e.g. a fake for tests) and ``fetch`` replace the real ones.
    """

    def __init__(
        self,
        sources: Sequence[Path],
        *,
        root: Path | None = None,
        settings: HostSettings | None = None,
        ledger: Ledger | None = None,
        executable: Sequence[str] | None = None,
        fetch: Fetch | None = None,
        out: Callable[[str], None] | None = None,
    ) -> None:
        if not sources:
            raise VidgenError("nothing to share")
        self.sources = [Path(s) for s in sources]
        self.root = root
        self.settings = settings or HostSettings()
        self.ledger = ledger
        self.executable = list(executable) if executable is not None else None
        self.fetch = fetch
        self.out = out or (lambda line: None)
        self.folder: Path | None = None
        self.files: list[SharedFile] = []
        self.server: ShareServer | None = None
        self.tunnel: TunnelProcess | None = None
        self.public_base: str | None = None
        self.host_name: str | None = None
        self._state = _State()
        self._lock = threading.RLock()
        self._ledger_lock = threading.Lock()
        self._closed = threading.Event()
        self._close_idle = threading.Event()   # no thread is running the close steps
        self._close_idle.set()
        self._watchdog: threading.Thread | None = None
        self._guard: host_guard.HostGuard | None = None
        self._folder_lock: int | None = None

    # -- opening ---------------------------------------------------------------------------------
    def __enter__(self) -> QuickTunnelHost:
        self.open()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> None:
        if exc_type is None:
            self.close("done")
        elif issubclass(exc_type, KeyboardInterrupt):
            self.close("interrupted")
        else:
            self.close(f"error: {exc_type.__name__}")

    def open(self) -> None:
        """Copy the files, start the server and the tunnel, check every file through the public
        address. On any failure (Ctrl+C included) everything opened so far is closed again."""
        atexit.register(self._close_at_exit)
        host_guard.track_host(self)
        try:
            self._open()
        except BaseException as exc:
            self.close("interrupted while opening" if isinstance(exc, KeyboardInterrupt) else "failed to open")
            raise

    def _open(self) -> None:
        settings = self.settings
        self._state.opened_at = time.monotonic()
        executable = self.executable if self.executable is not None else [find_cloudflared(settings.cloudflared)]
        swept = host_guard.sweep_stale_shares()
        if swept:
            self.out(f"deleted {len(swept)} temporary share folder(s) left by a vidgen that ended without closing its quick tunnel")
        self.folder, self._folder_lock = host_guard.make_share_folder()
        self._guard = host_guard.HostGuard(self.folder)
        if self.root is not None and self.folder.resolve().is_relative_to(self.root.resolve()):
            raise VidgenError(f"the temporary folder {self.folder} is inside the project; set TMP / TMPDIR to a folder outside it")
        self.files = copy_into_share(self.sources, self.folder, self.root)
        secret = secrets.token_urlsafe(24)
        self.server = ShareServer(self.files, secret, self._on_request)
        self.server.start()
        self.out(f"sharing {len(self.files)} file(s) ({_size_text(sum(f.size for f in self.files))}) through a Cloudflare quick tunnel "
                 f"for at most {settings.max_seconds / 60:g} min; starting cloudflared")
        guard = self._guard
        self.tunnel = TunnelProcess(tunnel_command(executable, self.server.port, settings.protocol), start=lambda command: _start_process(command, guard.tunnel_fds()))
        guard.adopt(self.tunnel.process)
        address = self.tunnel.wait_for_url(settings.url_timeout)
        self.host_name = address.removeprefix("https://")
        self.public_base = f"{address}/{secret}"
        if self.ledger is not None:
            self._append("host_open", host=self.host_name, files=[f.to_json() for f in self.files], max_seconds=settings.max_seconds)
        self.out(f"public address {self.host_name} (the files' paths have a secret part); checking it serves the files")
        self.tunnel.wait_registered(min(15.0, settings.url_timeout))
        fetch = self.fetch if self.fetch is not None else urllib_fetch
        for shared in self.files:
            verify_public(self._url(shared), shared, fetch, timeout=settings.verify_timeout, interval=settings.verify_interval)
        self._watchdog = threading.Thread(target=self._watch, name="vidgen-share-lifetime", daemon=True)
        self._watchdog.start()

    def _url(self, shared: SharedFile) -> str:
        if not self.is_open:
            raise VidgenError(f"the quick tunnel is closed ({self.close_reason or 'not open yet'}); its addresses no longer work")
        assert self.public_base is not None
        return f"{self.public_base}/{shared.name}"

    def url_of(self, source: Path) -> str:
        """The public URL of a shared source (secret included: hand it to the provider only); a
        :class:`VidgenError` when the host is closed."""
        wanted = Path(source).resolve()
        for shared in self.files:
            if shared.source.resolve() == wanted:
                return self._url(shared)
        raise VidgenError(f"{source} is not shared by this host")

    def redact(self, text: str) -> str:
        """``text`` without this host's secret (e.g. a provider's error that quotes a URL)."""
        secret = self.server.secret if self.server is not None else None
        return text.replace(secret, "<secret>") if secret else text

    def urls(self) -> dict[Path, str]:
        """Every shared source with its public URL."""
        return {shared.source: self._url(shared) for shared in self.files}

    # -- while open ------------------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        """Whether the files are still reachable (not closed yet, and not closing)."""
        return self.server is not None and self._state.close_reason is None and not self._closed.is_set()

    @property
    def requests(self) -> list[RequestRecord]:
        """Every request the share server answered (in memory only)."""
        return list(self.server.requests) if self.server is not None else []

    @property
    def close_reason(self) -> str | None:
        """Why it closed (``None`` while open)."""
        return self._state.close_reason

    def remaining_seconds(self) -> float:
        """Seconds left before the hard maximum lifetime."""
        return max(0.0, self._state.opened_at + self.settings.max_seconds - time.monotonic())

    def ensure_time_for_job(self, poll_timeout: float) -> None:
        """Raise a :class:`VidgenError` unless the host is open and has time left for a submit and
        a wait of ``poll_timeout`` s (the ``submit_margin`` on top): called just before a paid
        submit. Opening counts against the lifetime, so a slow start uses it up."""
        if not self.is_open:
            raise VidgenError(f"the quick tunnel is already closed ({self.close_reason or 'not open'}); nothing was sent or paid. Try again, or `vidgen generate host-test` to check the tunnel")
        needed = poll_timeout + self.settings.submit_margin
        left = self.remaining_seconds()
        if left < needed:
            raise VidgenError(
                f"the quick tunnel has only {left:.0f} s left of its {self.settings.max_seconds / 60:g} min limit (opening it took {self.settings.max_seconds - left:.0f} s) "
                f"and a job may need {needed:.0f} s (poll_timeout and {self.settings.submit_margin:g} s to submit); nothing was sent or paid. "
                "Try again, or raise host_max_minutes / lower poll_timeout"
            )

    def wait_closed(self, timeout: float | None = None) -> bool:
        """Wait until it closed (by itself or by another thread); whether it did."""
        return self._closed.wait(timeout)

    def _append(self, event: str, **fields: Any) -> None:
        if self.ledger is not None:
            with self._ledger_lock:
                self.ledger.append(event, **fields)

    def _on_request(self, record: RequestRecord, shared: SharedFile | None) -> None:
        if shared is None:
            return
        self._append("host_fetch", file=shared.label, method=record.method, status=record.status, bytes=record.bytes)

    def _watch(self) -> None:
        while not self._closed.wait(0.1):
            abandoned = self._state.close_reason is not None and self._state.closer is None   # e.g. Ctrl+C stopped it
            if abandoned or time.monotonic() >= self._state.opened_at + self.settings.max_seconds:
                self.close("max lifetime")

    # -- closing ---------------------------------------------------------------------------------
    def _close_at_exit(self) -> None:
        self.close("vidgen exited")

    def close(self, reason: str, wait_seconds: float = CLOSE_WAIT_SECONDS) -> None:
        """Stop cloudflared, then the server, then delete the temporary folder, then end the
        cleanup watcher; records ``host_close``. Each step runs even when an earlier one fails.
        Ctrl+C or a termination signal during a step leaves that step to be done again and is
        raised once the other steps ran: a later ``close`` (the watchdog's, ``atexit``'s) resumes
        the unfinished ones. A close while another thread is at it waits for that one, at most
        ``wait_seconds``; closing a closed host does nothing."""
        if not self._begin_closing(reason, wait_seconds):
            return
        interrupted: BaseException | None = None
        steps = self._close_steps()
        try:
            for step, action in steps:
                if step in self._state.finished_steps:
                    continue
                if step == "report" and len(self._state.finished_steps) < len(steps) - 1:
                    continue   # an interrupted step comes first
                try:
                    action()
                except (KeyboardInterrupt, SystemExit) as exc:
                    interrupted = interrupted or exc
                    continue
                except Exception as exc:   # a step that failed is not retried; the next steps still run
                    self._state.problems.append(f"{step}: {exc}")
                self._state.finished_steps.add(step)
            if len(self._state.finished_steps) == len(steps):
                self._closed.set()
                atexit.unregister(self._close_at_exit)
                host_guard.untrack_host(self)
        finally:
            self._state.closer = None
            self._close_idle.set()
        if interrupted is not None:
            raise interrupted

    def _begin_closing(self, reason: str, wait_seconds: float) -> bool:
        """Claim the close steps for this thread; ``False`` when there is nothing to do here
        (closed, re-entered from a signal handler in the closing thread, or another thread still
        at it after ``wait_seconds``)."""
        me = threading.get_ident()
        deadline = time.monotonic() + wait_seconds
        while True:
            with self._lock:
                if self._closed.is_set():
                    return False
                if self._state.close_reason is None:
                    self._state.close_reason = reason
                if self._state.closer is None:
                    self._state.closer = me
                    self._close_idle.clear()
                    return True
                if self._state.closer == me:
                    return False
            left = deadline - time.monotonic()
            if left <= 0:
                log.warning("closing the quick tunnel: the first close is still running after %g s", wait_seconds)
                return False
            self._close_idle.wait(left)

    def _close_steps(self) -> tuple[tuple[str, Callable[[], None]], ...]:
        return (
            ("cloudflared", self._stop_tunnel), ("server", self._stop_server), ("folder", self._delete_folder),
            ("watcher", self._finish_guard), ("report", self._report_closed),
        )

    def _stop_tunnel(self) -> None:
        if self.tunnel is None:
            self._state.tunnel_stopped = True
            return
        self.tunnel.stop()
        self._state.tunnel_stopped = True
        if self._guard is not None:
            self._guard.tunnel_stopped()

    def _stop_server(self) -> None:
        if self.server is not None:
            self.server.stop()

    def _delete_folder(self) -> None:
        if self.folder is None:
            self._state.folder_deleted = True
            return
        lock, self._folder_lock = self._folder_lock, None
        host_guard.release_share_folder(lock)   # first: Windows cannot delete an open file
        for attempt in range(5):
            try:
                shutil.rmtree(self.folder)
                self._state.folder_deleted = True
                return
            except FileNotFoundError:
                self._state.folder_deleted = True
                return
            except OSError as exc:   # Windows: a file still open for a moment
                if attempt == 4:
                    self._state.problems.append(f"could not delete {self.folder}: {exc}; delete it yourself")
                    return
                time.sleep(0.2)

    def _finish_guard(self) -> None:
        if self._guard is not None:
            self._guard.finish(disarm=self._state.tunnel_stopped and self._state.folder_deleted)

    def _report_closed(self) -> None:
        reason = self._state.close_reason
        deleted = self._state.folder_deleted
        if self.host_name is not None:
            requests = self.requests
            self._append(
                "host_close", host=self.host_name, reason=reason, seconds_open=round(time.monotonic() - self._state.opened_at, 1),
                requests=len(requests), not_found=sum(1 for r in requests if r.status == 404), folder_deleted=deleted,
            )
        for problem in self._state.problems:
            log.warning("closing the quick tunnel: %s", problem)
        self.out(f"quick tunnel closed ({reason}); temporary copies {'deleted' if deleted else 'NOT deleted, see the warning'}")


@dataclass(frozen=True)
class ShareOptions:
    """How a paid run opens one host per shot (``videogen.host: quick_tunnel``): the settings,
    where progress lines go, and (tests) a fake cloudflared and network."""

    settings: HostSettings = field(default_factory=HostSettings)
    out: Callable[[str], None] | None = None
    executable: Sequence[str] | None = None
    fetch: Fetch | None = None

    @classmethod
    def from_config(cls, settings: Any, out: Callable[[str], None] | None = None) -> ShareOptions:
        """From a :class:`vidgen.config.VideogenConfig`."""
        return cls(HostSettings.from_config(settings), out)

    def host(self, sources: Sequence[Path], root: Path, ledger: Ledger | None) -> QuickTunnelHost:
        """A host (not open yet) for ``sources`` of the project ``root``; it closes when the
        caller's ``with`` block ends or at the maximum lifetime, not when a file was fetched."""
        return QuickTunnelHost(sources, root=root, settings=self.settings, ledger=ledger, executable=self.executable, fetch=self.fetch, out=self.out)


def _size_text(size: int) -> str:
    return f"{size / 1e6:.2f} MB" if size >= 100_000 else f"{size:,} bytes"


@dataclass
class HostTestResult:
    """What ``vidgen generate host-test`` found."""

    ok: bool
    host: str | None
    checks: list[tuple[str, bool, str]]
    close_reason: str | None

    def to_json(self) -> dict[str, Any]:
        return {"ok": self.ok, "host": self.host, "close_reason": self.close_reason,
                "checks": [{"check": name, "ok": ok, "detail": detail} for name, ok, detail in self.checks]}


def host_self_test(
    settings: HostSettings | None = None,
    *,
    keep_seconds: float = 0.0,
    out: Callable[[str], None] = print,
    executable: Sequence[str] | None = None,
    fetch: Fetch | None = None,
) -> HostTestResult:
    """Share one tiny generated text file through a real quick tunnel, fetch it back through the
    public address, check that other paths answer 404, keep it open ``keep_seconds`` (capped by
    the maximum lifetime) and close. Free: nothing goes to a video provider."""
    settings = settings or HostSettings()
    fetch = fetch if fetch is not None else urllib_fetch
    source_folder = Path(tempfile.mkdtemp(prefix="vidgen-host-test-"))
    checks: list[tuple[str, bool, str]] = []
    host: QuickTunnelHost | None = None
    try:
        content = f"vidgen host test {secrets.token_hex(8)}\n".encode()
        source = source_folder / "host-test.txt"
        source.write_bytes(content)
        host = QuickTunnelHost([source], settings=settings, executable=executable, fetch=fetch, out=out)
        with host:
            checks.append(("public address answers HEAD with the file's length", True, host.host_name or ""))
            url = host.url_of(source)
            answer = fetch("GET", url, 15.0)
            same = answer.status == 200 and answer.body == content
            checks.append(("GET through the tunnel returns the same bytes", same, f"HTTP {answer.status}, {len(answer.body)} bytes"))
            for what, probe in (("the address without the secret", f"https://{host.host_name}/"),
                                ("a wrong secret", f"https://{host.host_name}/{secrets.token_urlsafe(24)}/{source.name}")):
                answer = fetch("GET", probe, 15.0)
                checks.append((f"{what} answers 404", answer.status == 404, f"HTTP {answer.status}"))
            for name, ok, detail in checks:
                out(f"  {'ok  ' if ok else 'FAIL'} {name} ({detail})")
            if keep_seconds > 0:
                keep = min(keep_seconds, host.remaining_seconds())
                out(f"keeping it open {keep:g} s; open this in a browser to see the file: {url}")
                host.wait_closed(keep)
    finally:
        shutil.rmtree(source_folder, ignore_errors=True)
    ok = all(c[1] for c in checks)
    result = HostTestResult(ok, host.host_name if host else None, checks, host.close_reason if host else None)
    if not ok:
        failed = "; ".join(f"{name} ({detail})" for name, good, detail in checks if not good)
        raise VidgenError(f"host test failed: {failed}")
    return result

