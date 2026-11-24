"""File transfers between this computer and a Colab VM, through Cloudflare quick tunnels.

Used by :class:`vidgen.colab.Colab` (``upload`` / ``download``), so by ``vidgen remote``, the
``comfyui`` Colab transport and ``tools/colab/setup_session.py``. Standard library only.

- **Up**: this computer serves the files through its own tunnel (:class:`LocalTunnel`) and the VM
  gets them with ``curl`` in a detached job (``colab_vm`` action ``fetch``), polled.
- **Down**: the VM serves the file through a tunnel on the VM (action ``serve``) and this computer
  gets it over HTTPS (:func:`http_get`).

Each side's tunnel opens once per command (on its first transfer) and closes with
:meth:`Transfers.close` (also at exit). Every tunnel runs ``colab_vm.SERVE_CODE``: 127.0.0.1 only,
only ``/<secret>/<name>`` of the files in its folder, a plain 404 for anything else, no listing.
The secret (``secrets.token_urlsafe(32)``, new per tunnel) travels only in ``colab exec``
arguments and is masked in every message. Every file's SHA-256 is checked after the transfer. A
failed transfer is retried (a new tunnel when the address does not resolve), then a
:class:`~vidgen.colab.ColabError`. There is no other route.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from vidgen.colab_vm import MASK, SERVE_CODE, TUNNEL_MAX_SECONDS
from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.colab import Colab

#: Bytes of randomness in each tunnel's secret path.
SECRET_BYTES = 32
#: Tries of one transfer (the first and two retries).
ATTEMPTS = 3
RETRY_PAUSE = 3.0
#: How long a new tunnel may take to print its address and register.
URL_TIMEOUT = 60.0
#: How long a new tunnel address may take to resolve here.
RESOLVE_SECONDS = 15.0
CLOUDFLARED_HINT = ("cloudflared was not found on PATH; install it (free, no account): Windows `winget install "
                    "Cloudflare.cloudflared`, macOS `brew install cloudflared`, Linux: "
                    "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")


class TransferError(VidgenError):
    """One try of a transfer failed (``resolve``: the tunnel's address did not resolve)."""

    def __init__(self, message: str, resolve: bool = False) -> None:
        super().__init__(message)
        self.resolve = resolve


def new_secret() -> str:
    """A fresh secret path segment."""
    return secrets.token_urlsafe(SECRET_BYTES)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def find_cloudflared() -> str:
    """``cloudflared`` on PATH (else where winget puts it on Windows); a :class:`VidgenError` with install hints."""
    found = shutil.which("cloudflared")
    if found:
        return found
    for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base and (Path(base) / "cloudflared" / "cloudflared.exe").is_file():
            return str(Path(base) / "cloudflared" / "cloudflared.exe")
    raise VidgenError(CLOUDFLARED_HINT)


def wait_resolves(host: str, seconds: float = RESOLVE_SECONDS, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Whether ``host`` resolves within ``seconds`` (a new quick tunnel name can take a moment)."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            sleep(1.0)


def http_get(url: str, dest: Path, sha256: str, timeout: float = 60.0) -> int:
    """Download ``url`` to ``dest`` (through ``dest`` + ``.part``), checking its SHA-256; returns the bytes."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if not wait_resolves(host):
        raise TransferError(f"{host} does not resolve", resolve=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    size = 0
    request = urllib.request.Request(url, headers={"User-Agent": "vidgen-transfer"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer, part.open("wb") as out:
            while chunk := answer.read(1 << 20):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    except urllib.error.HTTPError as exc:
        part.unlink(missing_ok=True)
        raise TransferError(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        part.unlink(missing_ok=True)
        reason = getattr(exc, "reason", exc)
        raise TransferError(f"{type(reason).__name__}: {reason}", resolve=isinstance(reason, socket.gaierror)) from None
    if digest.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise TransferError(f"SHA-256 differs ({size} bytes came)")
    os.replace(part, dest)
    return size


class LocalTunnel:
    """This computer's tunnel: ``colab_vm.SERVE_CODE`` in a child process that also runs cloudflared.
    It stops when :meth:`close` closes its stdin, or when vidgen ends (the pipe closes)."""

    def __init__(self, cloudflared: str, max_seconds: float = TUNNEL_MAX_SECONDS) -> None:
        self.secret = new_secret()
        self.folder = Path(tempfile.mkdtemp(prefix="vidgen-up-"))
        (self.folder / "files").mkdir()
        self.state_file = self.folder / "state.json"
        options: dict[str, Any] = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                                   else {"start_new_session": True})
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-c", SERVE_CODE, str(self.folder / "files"), str(self.state_file), cloudflared,
                 str(max_seconds), "1"],
                env={**os.environ, "VIDGEN_SERVE_SECRET": self.secret}, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
        except OSError as exc:
            shutil.rmtree(self.folder, ignore_errors=True)
            raise VidgenError(f"cannot start the transfer tunnel: {exc}") from None
        self.count = 0

    def state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def wait_url(self, timeout: float = URL_TIMEOUT, sleep: Callable[[float], None] = time.sleep) -> str:
        """The public address once cloudflared registered (a :class:`TransferError` otherwise)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.state()
            if state.get("url") and state.get("registered"):
                return str(state["url"])
            if state.get("ended") or self.process.poll() is not None:
                break
            sleep(0.2)
        tail = " | ".join(self.state().get("tail", [])[-3:]) or "nothing"
        raise TransferError(f"this computer's cloudflared gave no tunnel within {timeout:.0f} s (its last lines: {tail})")

    @property
    def base(self) -> str:
        """``https://<name>.trycloudflare.com/<secret>/`` (never print it)."""
        return f"{self.wait_url()}/{self.secret}/"

    def add(self, path: Path) -> str:
        """Put ``path`` (linked, else copied) in the served folder; its name there."""
        self.count += 1
        name = f"{self.count}-" + re.sub(r"[^A-Za-z0-9._-]", "_", path.name).lstrip(".")
        target = self.folder / "files" / name
        try:
            os.link(path, target)
        except OSError:
            shutil.copyfile(path, target)
        return name

    def close(self) -> None:
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(5)
        shutil.rmtree(self.folder, ignore_errors=True)


TunnelFactory = Callable[[], LocalTunnel]
Getter = Callable[[str, Path, str], int]


class Transfers:
    """The transfers of one command on one session (see the module docstring)."""

    def __init__(self, colab: Colab, tunnel_factory: TunnelFactory | None = None, getter: Getter = http_get,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.colab = colab
        self.tunnel_factory = tunnel_factory or (lambda: LocalTunnel(find_cloudflared()))
        self.getter = getter
        self.clock = clock
        self.local: LocalTunnel | None = None
        self.vm_secret: str | None = None
        self.vm_url: str | None = None
        self.secrets: list[str] = []
        self._at_exit = False

    def mask(self, text: str) -> str:
        """``text`` with every secret of this command replaced by ``***``."""
        for secret in self.secrets:
            text = text.replace(secret, MASK)
        return text

    def _opened(self) -> None:
        if not self._at_exit:
            atexit.register(self.close)
            self._at_exit = True

    # -- up ---------------------------------------------------------------------------------------

    def local_tunnel(self, fresh: bool = False) -> LocalTunnel:
        if fresh and self.local is not None:
            self.local.close()
            self.local = None
        if self.local is None:
            self.local = self.tunnel_factory()
            self.secrets.append(self.local.secret)
            self._opened()
            self.local.wait_url()
        return self.local

    def upload(self, pairs: Sequence[tuple[Path, str]]) -> None:
        """Send each local file to its VM path (one curl job for them all)."""
        total = sum(local.stat().st_size for local, _ in pairs)
        shas = [sha256_file(local) for local, _ in pairs]
        limit = 120.0 + total / 2e6   # at least 2 MB/s
        error = ""
        fresh = False
        for attempt in range(1, ATTEMPTS + 1):
            tunnel = self.local_tunnel(fresh)
            fresh = False
            files = [{"name": tunnel.add(local), "dest": remote, "sha256": sha} for (local, remote), sha in zip(pairs, shas)]
            env = {"VIDGEN_URL": tunnel.base, "VIDGEN_FILES": json.dumps(files), "VIDGEN_ATTEMPT": str(attempt)}
            begin = self.clock()
            reply: dict[str, Any] = {"done": False}
            while not reply.get("done") and self.clock() - begin < limit:
                reply = self.colab.vm("fetch", **env)
            if reply.get("ok"):
                return
            error = self.mask(str(reply.get("problem") or f"not done after {limit:.0f} s"))
            fresh = bool(reply.get("resolve"))
            self.retry_pause(f"upload of {pairs[0][0].name} failed ({error})", attempt)
        raise_error(f"could not upload {', '.join(local.name for local, _ in pairs)} to {self.colab.session} "
                    f"after {ATTEMPTS} tries: {error}")

    # -- down -------------------------------------------------------------------------------------

    def prestart_env(self) -> dict[str, str]:
        """``--env`` that lets a ``begin`` exec start the VM's tunnel early."""
        self._vm_secret()
        self._opened()
        assert self.vm_secret is not None
        return {"VIDGEN_SECRET": self.vm_secret}

    def _vm_secret(self, fresh: bool = False) -> str:
        if fresh or self.vm_secret is None:
            self.vm_secret = new_secret()
            self.secrets.append(self.vm_secret)
            self.vm_url = None
        return self.vm_secret

    def offer(self, remote: str, fresh: bool = False) -> tuple[str, dict[str, Any]]:
        """Serve ``remote`` from the VM's tunnel; its address and the file's name, size, SHA-256."""
        restart = fresh
        secret = self._vm_secret(fresh)
        self._opened()
        for _ in range(int(URL_TIMEOUT // 15) + 1):
            reply = self.colab.vm("serve", VIDGEN_SECRET=secret, VIDGEN_OFFER=json.dumps([remote]),
                                  VIDGEN_RESTART="1" if restart else "")
            restart = False
            if reply.get("problem"):
                raise TransferError(str(reply["problem"]), resolve=True)
            if reply.get("url"):
                self.vm_url = str(reply["url"])
                return self.vm_url, reply["files"][remote]
        raise TransferError(f"the tunnel on {self.colab.session} gave no address within {URL_TIMEOUT:.0f} s")

    def download(self, remote: str, local: Path) -> int:
        """Bring ``remote`` (a VM path) to ``local``; returns its size."""
        error = ""
        fresh = False
        for attempt in range(1, ATTEMPTS + 1):
            try:
                url, info = self.offer(remote, fresh)
                return self.getter(f"{url}/{self.vm_secret}/{info['name']}", local, info["sha256"])
            except TransferError as exc:
                error = self.mask(str(exc))
                fresh = exc.resolve
            self.retry_pause(f"download of {Path(remote).name} failed ({error})", attempt)
        raise_error(f"could not download {remote} from {self.colab.session} after {ATTEMPTS} tries: {error}")

    def retry_pause(self, what: str, attempt: int) -> None:
        """Say what failed and wait, unless ``attempt`` was the last one."""
        if attempt < ATTEMPTS:
            self.colab.say(f"   {what}; retry {attempt + 1}/{ATTEMPTS} in {RETRY_PAUSE:.0f} s")
            self.colab.sleep(RETRY_PAUSE)

    # -- end --------------------------------------------------------------------------------------

    def close(self) -> None:
        """Close both tunnels (safe to repeat)."""
        if self._at_exit:
            atexit.unregister(self.close)
            self._at_exit = False
        if self.local is not None:
            self.local.close()
            self.local = None
        if self.vm_secret is not None:
            self.vm_secret = None
            try:
                self.colab.vm("unserve")
            except VidgenError as exc:
                self.colab.say(f"   could not close the tunnel on {self.colab.session} ({self.mask(str(exc))}); it stops by itself within 6 h")


def raise_error(message: str) -> NoReturn:
    from vidgen.colab import ColabError

    raise ColabError(message)
