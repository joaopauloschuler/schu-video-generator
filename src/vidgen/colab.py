"""The ``colab`` CLI driven from this computer: shared by ``tools/colab/setup_session.py`` and
``vidgen remote``.

Standard library only (it runs before vidgen's dependencies matter, Windows too). Two routes to
the VM, chosen with ``Colab(via=...)``:

- ``"ssh"`` (the default, :mod:`vidgen.colab_ssh`): scripts and files over one held ssh master
  through ``colab ssh --proxy-mode``; no lock, calls may run in parallel.
- ``"exec"``: every call to ``colab`` is a list of arguments, one call at a time per session, also
  across processes (a lock file in :data:`LOCK_DIR`): two overlapping calls on one session drop
  each other. ``colab exec`` calls are cut at 30 s and retried after 3, 10, 20, 30 s. Files go both
  ways through Cloudflare quick tunnels (:mod:`vidgen.colab_transfer`), never ``colab upload`` /
  ``download``.

Every VM-side action is safe to repeat, since the VM's work goes on when a connection drops. A
"last call" stamp next to the lock file is touched after each call (either route). ``colab
sessions`` / ``new`` always go through the colab CLI. Nothing here stops a session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.colab_ssh import SshLink
    from vidgen.colab_transfer import Transfers

#: The VM-side script (``colab exec -f``) that reports state, unpacks, starts and polls runs.
VM_SCRIPT = Path(__file__).resolve().parent / "colab_vm.py"
#: The prefix of the JSON line :data:`VM_SCRIPT` prints.
VM_PREFIX = "VIDGEN_VM "
#: Where projects live on the VM (``/content/projects/<name>``).
VM_PROJECTS = "/content/projects"
#: The archive of vidgen's source that the setup uploads.
VM_SOURCE_ARCHIVE = "/content/vidgen-src.tar.gz"
#: The files next to ``src/`` that ``pip install`` of the source needs.
SOURCE_TOP_FILES = ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md")
_SKIPPED_PARTS = ("__pycache__",)
_SKIPPED_SUFFIXES = (".pyc", ".pyo")
#: The ``--env`` keys :data:`VM_SCRIPT` reads. ``--env`` values stay set in the kernel, so
#: :meth:`Colab.vm` passes every key, blank unless given.
VM_KEYS = ("VIDGEN_PROJECT", "VIDGEN_EXCLUDE", "VIDGEN_RUN", "VIDGEN_BIN", "VIDGEN_ARGS", "VIDGEN_HASH",
           "VIDGEN_ARCHIVE", "VIDGEN_CHECK", "VIDGEN_OFFSET", "VIDGEN_PACK", "VIDGEN_URL", "VIDGEN_FILES",
           "VIDGEN_ATTEMPT", "VIDGEN_SECRET", "VIDGEN_OFFER", "VIDGEN_RESTART", "VIDGEN_NAMED")
#: Where the per-session lock files live (one ``colab`` call at a time per session).
LOCK_DIR = Path(tempfile.gettempdir()) / "vidgen-colab-locks"
#: A ``colab exec`` is cut after this many seconds (the VM scripts answer in 5-15 s).
EXEC_SECONDS = 30.0
#: The pauses before the 2nd, 3rd, ... try of a dropped call.
RETRY_PAUSES = (3.0, 10.0, 20.0, 30.0)
#: The routes to the VM (:class:`Colab` ``via``); the first is the default.
ROUTES = ("ssh", "exec")


def via_arg(parser: argparse.ArgumentParser) -> None:
    """Add ``--via {ssh,exec}`` (default ssh): the route of this one command's Colab calls."""
    parser.add_argument("--via", choices=ROUTES, default=ROUTES[0], metavar="exec",
                        help="use the old colab exec route (default: ssh)")


class ColabError(VidgenError):
    """A ``colab`` step failed; the message says which (and shows the VM's log tail when there is one)."""


@dataclass(frozen=True)
class CommandResult:
    """Exit code and combined stdout + stderr of one ``colab`` call."""

    returncode: int
    output: str


Runner = Callable[[list[str], float], CommandResult]


def say_now(line: str) -> None:
    """Print a progress line at once, also when stdout is a pipe."""
    print(line, flush=True)


def run_command(args: list[str], timeout_seconds: float) -> CommandResult:
    """Run one command and return its exit code and output (124 when it timed out)."""
    try:
        # check=False: the caller retries dropped calls, and `colab exec` exits 0 even when the code fails.
        done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout_seconds, check=False)
    except FileNotFoundError as exc:
        raise ColabError(f"{args[0]!r} not found: install and log in to the colab CLI (google-colab-cli)") from exc
    except subprocess.TimeoutExpired as exc:
        partial = "".join(_text(part) for part in (exc.stdout, exc.stderr))
        return CommandResult(124, f"{partial}\n(timed out after {timeout_seconds:.0f} s)")
    return CommandResult(done.returncode, done.stdout + done.stderr)


def _text(data: str | bytes | None) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return data or ""


def parse_sessions(text: str) -> dict[str, str]:
    """Session name -> hardware from ``colab sessions`` lines like ``[ltx] gpu-l4-... | Hardware: L4 | ...``."""
    sessions = {}
    for line in text.splitlines():
        match = re.match(r"\s*\[(?P<name>[^\]]+)\]\s+\S+\s*\|\s*Hardware:\s*(?P<hardware>[^|]+?)\s*(\||$)", line)
        if match:
            sessions[match["name"]] = match["hardware"]
    return sessions


def parse_prefixed_json(text: str, prefix: str) -> dict | None:
    """The JSON object on the line starting with ``prefix``, or None when it is missing (the exec dropped)."""
    for line in text.splitlines():
        if line.startswith(prefix):
            try:
                value = json.loads(line[len(prefix):])
            except ValueError:
                return None
            return value if isinstance(value, dict) else None
    return None


def last_line(text: str) -> str:
    """The last non-empty line of ``text`` (``(no output)`` when there is none)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "(no output)"


def format_seconds(seconds: float) -> str:
    """``75`` -> ``1 min 15 s``."""
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


def shown(name: str) -> str:
    """A session name or path as typed in a printed command (quoted when it has spaces)."""
    return f'"{name}"' if re.search(r"\s", name) else name


@dataclass
class Colab:
    """One Colab session: scripts and files over ssh (``via="ssh"``, the default) or ``colab exec``
    and quick tunnels (``via="exec"``, one call at a time); see the module docstring."""

    session: str
    cli: str = "colab"
    runner: Runner = run_command
    sleep: Callable[[float], None] = time.sleep
    say: Callable[[str], None] = say_now
    attempts: int = 5
    retry_pauses: tuple[float, ...] = RETRY_PAUSES
    lock_dir: Path | None = None   # None: :data:`LOCK_DIR`
    wall: Callable[[], float] = time.time
    transfer_factory: Callable[[Colab], Transfers] | None = None
    via: str = ROUTES[0]
    ssh_factory: Callable[[Colab], SshLink] | None = None
    _transfers: Transfers | None = field(default=None, init=False, repr=False)
    _link: SshLink | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.via not in ROUTES:
            raise ColabError(f"unknown Colab route via={self.via!r}; use one of {', '.join(ROUTES)}")

    @property
    def link(self) -> SshLink:
        """The SSH route's connection (:mod:`vidgen.colab_ssh`; the master opens on first use)."""
        if self._link is None:
            from vidgen.colab_ssh import SshLink

            self._link = (self.ssh_factory(self) if self.ssh_factory else
                          SshLink(self.session, cli=self.cli, listed=self.sessions, say=self.say))
        return self._link

    def run(self, args: list[str], timeout_seconds: float) -> CommandResult:
        if args[0] == "sessions":
            return self.runner([self.cli, *args], timeout_seconds)
        with self.locked(timeout_seconds):
            try:
                return self.runner([self.cli, *args], timeout_seconds)
            finally:
                self.touch_stamp()

    @property
    def lock_path(self) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", self.session)
        return (self.lock_dir or LOCK_DIR) / f"{safe}-{hashlib.sha256(self.session.encode('utf-8')).hexdigest()[:8]}.lock"

    @property
    def stamp_path(self) -> Path:
        """The session's "last call" stamp next to its lock (touched after every call but ``sessions``)."""
        return self.lock_path.with_suffix(".last")

    def touch_stamp(self) -> None:
        self.stamp_path.parent.mkdir(parents=True, exist_ok=True)
        self.stamp_path.touch()

    def _acquire(self, timeout_seconds: float) -> bool:
        """Take the session's lock file unless another holder's call is still on (a stale lock is taken over)."""
        path = self.lock_path
        path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._stale(path):
                    path.unlink(missing_ok=True)
                    continue
                return False
            with os.fdopen(handle, "w", encoding="utf-8") as lock:
                json.dump({"pid": os.getpid(), "until": self.wall() + timeout_seconds + 15}, lock)
            return True

    @contextmanager
    def locked(self, timeout_seconds: float) -> Iterator[None]:
        """Hold the session's lock file for one call; a lock whose holder's call should have ended
        (its ``until`` time passed) is stale and taken over."""
        waited = False
        while not self._acquire(timeout_seconds):
            if not waited:
                self.say(f"   waiting for another colab call on session {self.session} to end")
                waited = True
            self.sleep(1.0)
        try:
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)

    @contextmanager
    def try_locked(self, timeout_seconds: float) -> Iterator[bool]:
        """Hold the session's lock when it is free (yields True), else yield False at once; never waits."""
        got = self._acquire(timeout_seconds)
        try:
            yield got
        finally:
            if got:
                self.lock_path.unlink(missing_ok=True)

    def _stale(self, path: Path) -> bool:
        try:
            until = float(json.loads(path.read_text(encoding="utf-8"))["until"])
        except FileNotFoundError:
            return False
        except (OSError, ValueError, KeyError, TypeError):
            try:   # being written right now, or garbage left behind
                return self.wall() - path.stat().st_mtime > 5
            except FileNotFoundError:
                return False
        return self.wall() > until

    def sessions(self) -> dict[str, str]:
        """The sessions ``colab sessions`` lists (name -> hardware)."""
        result = self.run(["sessions"], 90)
        if result.returncode != 0:
            raise ColabError(f"`colab sessions` failed: {last_line(result.output)}")
        return parse_sessions(result.output)

    def create(self, gpu: str) -> CommandResult:
        return self.run(["new", "-s", self.session, "--gpu", gpu], 600)

    def exec_args(self, script: Path, env: dict[str, str]) -> list[str]:
        """Arguments of ``colab exec`` running a local file on the VM with ``--env KEY=VALUE`` pairs."""
        args = ["exec", "-s", self.session, "--timeout", f"{EXEC_SECONDS - 10:.0f}"]
        for key, value in env.items():
            args += ["--env", f"{key}={value}"]
        return [*args, "-f", str(script)]

    def exec_file(self, script: Path, env: dict[str, str] | None = None) -> CommandResult:
        """Run the local Python file ``script`` on the VM with ``env`` set (over ssh, or ``colab exec``)."""
        if self.via == "ssh":
            try:
                return self.link.script(script, env or {})
            finally:
                self.touch_stamp()
        # These scripts answer in 5-15 s; a call that hangs (often) is cut and retried.
        return self.run(self.exec_args(script, env or {}), EXEC_SECONDS)

    def exec_json(self, script: Path, env: dict[str, str], prefix: str) -> dict:
        """Run ``script`` on the VM and return the JSON it printed after ``prefix``; retries a dropped exec."""
        for attempt in range(1, self.attempts + 1):
            result = self.exec_file(script, env)
            value = parse_prefixed_json(result.output, prefix)
            if value is not None:
                return value
            self.pause_before_retry(f"exec dropped ({last_line(result.output)})", attempt)
        if self.via == "ssh":
            raise ColabError(f"python3 over ssh on {self.session} kept failing; try `colab ssh -s {shown(self.session)}` by hand")
        raise ColabError(f"`colab exec` on {self.session} kept failing; try `colab exec -s {shown(self.session)}` by hand")

    def vm(self, action: str, **env: str) -> dict:
        """Run :data:`VM_SCRIPT` with ``VIDGEN_ACTION=action``; raises when it reports an error."""
        reply = self.exec_json(VM_SCRIPT, {"VIDGEN_ACTION": action, **dict.fromkeys(VM_KEYS, ""), **env}, VM_PREFIX)
        if reply.get("error"):
            raise ColabError(f"on {self.session}: {reply['error']}")
        return reply

    @property
    def transfers(self) -> Transfers:
        """This command's file transfers (:mod:`vidgen.colab_transfer`; tunnels open on first use)."""
        if self._transfers is None:
            from vidgen.colab_transfer import Transfers

            self._transfers = (self.transfer_factory or Transfers)(self)
        return self._transfers

    def prestart_env(self) -> dict[str, str]:
        """Extra env for a ``begin`` call: on the exec route it starts the VM's tunnel early."""
        return {} if self.via == "ssh" else self.transfers.prestart_env()

    def upload(self, local: Path, remote: str) -> None:
        """Send ``local`` to the VM path ``remote`` (over ssh or a quick tunnel, SHA-256 checked)."""
        self.upload_many([(local, remote)])

    def upload_many(self, pairs: list[tuple[Path, str]]) -> None:
        """Send several files (on the exec route in one transfer job)."""
        try:
            if self.via == "ssh":
                self.link.upload(pairs)
            else:
                self.transfers.upload(pairs)
        finally:
            self.touch_stamp()

    def download(self, remote: str, local: Path) -> None:
        """Bring the VM file ``remote`` to ``local`` (over ssh or a quick tunnel, SHA-256 checked)."""
        try:
            if self.via == "ssh":
                self.link.download(remote, local)
            else:
                self.transfers.download(remote, local)
        finally:
            self.touch_stamp()

    def close(self) -> None:
        """Close this command's ssh master or tunnels (safe to repeat; tunnels also close at exit)."""
        if self._link is not None:
            self._link.close()
        if self._transfers is not None:
            self._transfers.close()

    def __enter__(self) -> Colab:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def pause_before_retry(self, what: str, attempt: int) -> None:
        """Say what failed and wait, unless ``attempt`` was the last one."""
        if attempt < self.attempts:
            pause = self.retry_pauses[min(attempt, len(self.retry_pauses)) - 1]
            self.say(f"   {what}; retry {attempt + 1}/{self.attempts} in {pause:.0f} s")
            self.sleep(pause)


def _package_files(package_dir: Path) -> list[Path]:
    files = []
    for path in package_dir.rglob("*"):
        if path.is_file() and not any(part in _SKIPPED_PARTS for part in path.parts) and path.suffix not in _SKIPPED_SUFFIXES:
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(package_dir).as_posix())


def package_hash(package_dir: Path | None = None) -> str:
    """The SHA-256 (16 hex digits) of vidgen's package folder: every file's relative path and bytes,
    caches left out. The setup records it on the VM; ``vidgen remote`` compares it."""
    root = package_dir or Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in _package_files(root):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()[:16]


def source_archive(repo: Path, dest: Path) -> Path:
    """Write ``dest`` (.tar.gz): the working tree's ``src/vidgen`` (uncommitted changes too) and the
    top files ``pip install`` needs, under ``vidgen-src/``."""
    package = repo / "src" / "vidgen"
    if not (repo / "pyproject.toml").is_file() or not package.is_dir():
        raise ColabError(f"{repo} is not vidgen's source folder (no pyproject.toml and src/vidgen)")
    with tarfile.open(dest, "w:gz") as archive:
        for name in SOURCE_TOP_FILES:
            if (repo / name).is_file():
                archive.add(repo / name, arcname=f"vidgen-src/{name}")
        for path in _package_files(package):
            archive.add(path, arcname="vidgen-src/" + path.relative_to(repo).as_posix())
    return dest


def files_archive(root: Path, relpaths: list[str], dest: Path) -> Path:
    """Write ``dest`` (.tar.gz) with ``root``'s files ``relpaths`` (POSIX paths relative to ``root``)."""
    with tarfile.open(dest, "w:gz") as archive:
        for rel in relpaths:
            archive.add(root / Path(rel), arcname=rel)
    return dest


def extract_archive(archive: Path, dest: Path) -> list[str]:
    """Extract ``archive`` (.tar or .tar.gz) into ``dest``; returns its member names. Raises
    :class:`ColabError` on an absolute path or ``..``."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tar:
        members = tar.getmembers()
        for member in members:
            if member.name.startswith(("/", "\\")) or ".." in Path(member.name).parts:
                raise ColabError(f"unsafe path in {archive.name}: {member.name}")
        tar.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    return [member.name for member in members]
