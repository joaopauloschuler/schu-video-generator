"""The ``colab`` CLI driven from this computer: shared by ``tools/colab/setup_session.py`` and
``vidgen remote``.

Standard library only (it runs before vidgen's dependencies matter, Windows too). Every call to
``colab`` is a list of arguments, one call at a time; ``colab exec`` calls are cut at 60 s and
retried, since the VM's work goes on when a connection drops. Nothing here stops a session.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from vidgen.errors import VidgenError

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
    """The ``colab`` CLI for one session: every call is a list of arguments, one call at a time."""

    session: str
    cli: str = "colab"
    runner: Runner = run_command
    sleep: Callable[[float], None] = time.sleep
    say: Callable[[str], None] = say_now
    attempts: int = 5
    retry_pause: float = 20.0

    def run(self, args: list[str], timeout_seconds: float) -> CommandResult:
        return self.runner([self.cli, *args], timeout_seconds)

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
        args = ["exec", "-s", self.session, "--timeout", "45"]
        for key, value in env.items():
            args += ["--env", f"{key}={value}"]
        return [*args, "-f", str(script)]

    def exec_file(self, script: Path, env: dict[str, str] | None = None) -> CommandResult:
        # These scripts answer in 5-15 s; a call that hangs (seen while connecting) is cut at 60 s and retried.
        return self.run(self.exec_args(script, env or {}), 60)

    def exec_json(self, script: Path, env: dict[str, str], prefix: str) -> dict:
        """Run ``script`` on the VM and return the JSON it printed after ``prefix``; retries a dropped exec."""
        for attempt in range(1, self.attempts + 1):
            result = self.exec_file(script, env)
            value = parse_prefixed_json(result.output, prefix)
            if value is not None:
                return value
            self.pause_before_retry(f"exec dropped ({last_line(result.output)})", attempt)
        raise ColabError(f"`colab exec` on {self.session} kept failing; try `colab exec -s {shown(self.session)}` by hand")

    def vm(self, action: str, **env: str) -> dict:
        """Run :data:`VM_SCRIPT` with ``VIDGEN_ACTION=action``; raises when it reports an error."""
        reply = self.exec_json(VM_SCRIPT, {"VIDGEN_ACTION": action, **env}, VM_PREFIX)
        if reply.get("error"):
            raise ColabError(f"on {self.session}: {reply['error']}")
        return reply

    def upload(self, local: Path, remote: str) -> None:
        """``colab upload``, retried when the transfer fails."""
        for attempt in range(1, self.attempts + 1):
            result = self.run(["upload", "-s", self.session, str(local), remote], 300)
            if result.returncode == 0 and "Traceback" not in result.output:
                return
            self.pause_before_retry(f"upload of {local.name} failed ({last_line(result.output)})", attempt)
        raise ColabError(f"could not upload {local} to {remote}")

    def download(self, remote: str, local: Path) -> None:
        """``colab download``, retried until ``local`` exists."""
        local.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, self.attempts + 1):
            result = self.run(["download", "-s", self.session, remote, str(local)], 600)
            if result.returncode == 0 and "Traceback" not in result.output and local.is_file():
                return
            self.pause_before_retry(f"download of {remote} failed ({last_line(result.output)})", attempt)
        raise ColabError(f"could not download {remote} from {self.session}")

    def pause_before_retry(self, what: str, attempt: int) -> None:
        """Say what failed and wait, unless ``attempt`` was the last one."""
        if attempt < self.attempts:
            self.say(f"   {what}; retry {attempt + 1}/{self.attempts} in {self.retry_pause:.0f} s")
            self.sleep(self.retry_pause)


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
