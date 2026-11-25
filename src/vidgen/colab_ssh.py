"""The SSH route to a Colab VM (``Colab(via="ssh")``, the default): ``ssh`` through
``colab ssh --proxy-mode`` as its ProxyCommand, one held master connection per session.

- **Key**: only :data:`KEY` (``~/.ssh/colab_ed25519``); ``colab ssh`` sends its public half to the VM.
- **Master**: opened on first use (after ``colab sessions`` lists the session, since
  ``colab ssh -s NAME`` would create a missing one), checked with ``ssh -O check``, reopened once
  when a call fails with ssh's own exit code 255, closed by :meth:`SshLink.close` when this
  object opened it. Its socket lives in :data:`SOCKET_DIR` (mode 0700), named from a short hash
  of the session name, so the ControlPath stays under 108 bytes.
- **Host keys**: every VM has a new one. Each session has its own known_hosts file in
  :data:`SOCKET_DIR`, emptied when this object opens a master, and ``StrictHostKeyChecking=accept-new``.
  ``~/.ssh/known_hosts`` and ``~/.ssh/config`` are never read or written (``-F /dev/null``).
- **Scripts**: ``python3 -`` on the VM in ``/content``, the script on stdin, the env vars as
  ``env -- KEY=VALUE`` words quoted with :func:`shlex.quote`.
- **Files**: ``cat`` over the master both ways, SHA-256 checked, through a ``.vidgen-part`` file.
- No lock: calls on one session may run in parallel. Windows' OpenSSH has no ControlMaster, so
  there every call opens its own connection.

Standard library only.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from vidgen.colab import ColabError, CommandResult, last_line
from vidgen.colab_transfer import sha256_file

#: The only key the SSH route uses.
KEY = Path.home() / ".ssh" / "colab_ed25519"
#: Where the master sockets and per-session known_hosts files live.
SOCKET_DIR = Path.home() / ".cache" / "vidgen" / "ssh"
#: A Unix socket path must fit in 108 bytes (``sun_path``), its end byte included.
SOCKET_PATH_MAX = 107
#: The login on a Colab VM (``colab ssh`` maps any host name to the session).
LOGIN = "root@colab"
#: A script call is cut after this long (long jobs run detached on the VM already).
SCRIPT_SECONDS = 600.0
#: The idle time after which a forgotten master ends by itself.
PERSIST = "20m"
KEY_HINT = ("no SSH key at {key}: create it with `ssh-keygen -t ed25519 -N \"\" -f {key}` (colab ssh sends "
            "its public half to the VM), or use the colab exec route (via=\"exec\")")
_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
#: ssh's exit code when the connection (not the remote command) failed.
SSH_FAILED = 255


SshRunner = Callable[[list[str], float, "Path | bytes | None", "Path | None"], CommandResult]


def run_ssh(args: list[str], timeout_seconds: float, stdin: Path | bytes | None = None,
            stdout: Path | None = None) -> CommandResult:
    """Run ``args`` with ``stdin`` (a file or bytes) and stdout to the file ``stdout`` (else
    captured). Output goes through temporary files, not pipes, since a master that ssh puts in
    the background keeps them open. Exit code 124 when it timed out."""
    with ExitStack() as stack:
        err = stack.enter_context(tempfile.TemporaryFile())
        out = stack.enter_context(tempfile.TemporaryFile()) if stdout is None else stack.enter_context(stdout.open("wb"))
        source: Any = subprocess.DEVNULL
        if isinstance(stdin, Path):
            source = stack.enter_context(stdin.open("rb"))
        elif isinstance(stdin, bytes):
            source = stack.enter_context(tempfile.TemporaryFile())
            source.write(stdin)
            source.seek(0)
        try:
            code = subprocess.run(args, stdin=source, stdout=out, stderr=err, timeout=timeout_seconds,
                                  check=False).returncode
        except FileNotFoundError as exc:
            raise ColabError(f"{args[0]!r} not found: install OpenSSH's client (ssh), or use via=\"exec\"") from exc
        except subprocess.TimeoutExpired:
            code = 124
        text = b""
        for handle in ((out,) if stdout is None else ()) + (err,):
            handle.seek(0)
            text += handle.read()
    output = text.decode("utf-8", "replace")
    return CommandResult(code, output + (f"\n(timed out after {timeout_seconds:.0f} s)" if code == 124 else ""))


def env_words(env: dict[str, str]) -> list[str]:
    """``env -- KEY=VALUE ...`` as shell words, each quoted; a bad key raises :class:`ColabError`."""
    for key in env:
        if not _ENV_KEY.match(key):
            raise ColabError(f"not an environment variable name: {key!r}")
    return ["env", "--", *(shlex.quote(f"{key}={value}") for key, value in env.items())]


def script_command(env: dict[str, str]) -> str:
    """The remote command that runs the script on stdin with ``env`` set, in ``/content``."""
    return " ".join(["cd /content &&", *env_words(env), "python3 -"])


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class SshLink:
    """ssh, scp-free file copies and a held master for one Colab session (see the module docstring)."""

    def __init__(self, session: str, cli: str = "colab", runner: SshRunner | None = None, key: Path | None = None,
                 socket_dir: Path | None = None, listed: Callable[[], dict[str, str]] | None = None,
                 say: Callable[[str], None] = print, multiplex: bool = os.name != "nt") -> None:
        self.session = session
        self.cli = cli
        self.runner = runner or run_ssh
        self.key = key or KEY
        self.socket_dir = socket_dir or SOCKET_DIR
        self.listed = listed
        self.say = say
        self.multiplex = multiplex
        self.ready = False
        self.opened = False

    @property
    def control_path(self) -> Path:
        """The master's socket: under :data:`SOCKET_DIR`, else the temporary folder when that is too long."""
        path = self.socket_dir / short_hash(self.session)
        if len(os.fsencode(str(path))) > SOCKET_PATH_MAX:
            path = Path(tempfile.gettempdir()) / f"vidgen-ssh-{short_hash(str(Path.home()))[:6]}" / short_hash(self.session)
        return path

    @property
    def known_hosts(self) -> Path:
        return self.socket_dir / f"{short_hash(self.session)}.known_hosts"

    def options(self) -> list[str]:
        """The ssh options every call uses (no user config, only :data:`KEY`, the per-session host file)."""
        proxy = " ".join(shlex.quote(word) for word in
                         [self.cli, "ssh", "--proxy-mode", "-s", self.session, "-i", str(self.key)])
        options = ["-F", os.devnull, "-i", str(self.key), "-o", "IdentitiesOnly=yes", "-o", f"ProxyCommand={proxy}",
                   "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={self.known_hosts}",
                   "-o", "BatchMode=yes", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
                   "-o", "LogLevel=ERROR"]
        if self.multiplex:
            options += ["-o", f"ControlPath={self.control_path}"]
        return options

    def ssh(self, *extra: str) -> list[str]:
        return ["ssh", *self.options(), *extra]

    # -- master -----------------------------------------------------------------------------------

    def ensure(self) -> None:
        """Make sure the key exists and (first time) that a master runs; opens one when none does."""
        if not self.key.is_file():
            raise ColabError(KEY_HINT.format(key=self.key))
        if self.ready:
            return
        for folder in {self.socket_dir, self.control_path.parent}:
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                folder.chmod(0o700)
        if self.multiplex and not self.check():
            self.open_master()
        self.ready = True

    def check(self) -> bool:
        """Whether a master for this session answers (``ssh -O check``, local and cheap)."""
        return self.runner(self.ssh("-O", "check", LOGIN), 15, None, None).returncode == 0

    def open_master(self) -> None:
        if self.listed is not None and self.session not in self.listed():
            raise ColabError(f"no Colab session {self.session!r} (colab sessions); `colab ssh` would create one")
        self.known_hosts.unlink(missing_ok=True)   # a new VM has a new host key
        self.control_path.unlink(missing_ok=True)
        result = self.runner(self.ssh("-o", "ControlMaster=yes", "-o", f"ControlPersist={PERSIST}", "-f", "-N", LOGIN),
                             90, None, None)
        if result.returncode != 0 or not self.check():
            raise ColabError(f"cannot open an SSH connection to {self.session}: {last_line(result.output)}")
        self.opened = True

    def close(self) -> None:
        """End the master when this object opened it (safe to repeat)."""
        if self.opened:
            self.runner(self.ssh("-O", "exit", LOGIN), 15, None, None)
            self.opened = False
        self.ready = False

    # -- calls ------------------------------------------------------------------------------------

    def call(self, command: str, timeout_seconds: float, stdin: Path | bytes | None = None,
             stdout: Path | None = None) -> CommandResult:
        """Run the shell ``command`` on the VM; a dropped connection reopens the master once and retries."""
        self.ensure()
        args = self.ssh("-o", "ControlMaster=no", LOGIN, command)
        result = self.runner(args, timeout_seconds, stdin, stdout)
        if result.returncode == SSH_FAILED:
            self.say(f"   ssh to {self.session} failed ({last_line(result.output)}); reconnecting once")
            if self.multiplex:
                self.runner(self.ssh("-O", "exit", LOGIN), 15, None, None)
                self.open_master()
            result = self.runner(args, timeout_seconds, stdin, stdout)
        return result

    def script(self, script: Path, env: dict[str, str]) -> CommandResult:
        """Run the local Python file ``script`` on the VM with ``env``."""
        return self.call(script_command(env), SCRIPT_SECONDS, script.read_bytes())

    def upload(self, pairs: Sequence[tuple[Path, str]]) -> None:
        """Send each local file to its VM path (through ``<path>.vidgen-part``, SHA-256 checked there)."""
        for local, remote in pairs:
            part, sha = shlex.quote(remote + ".vidgen-part"), sha256_file(local)
            command = (f"mkdir -p {shlex.quote(str(Path(remote).parent.as_posix()))} && cat > {part} && "
                       f"if [ \"$(sha256sum {part} | cut -c1-64)\" = {sha} ]; then mv -f {part} {shlex.quote(remote)}; "
                       f"else rm -f {part}; echo 'SHA-256 differs on the VM' >&2; exit 3; fi")
            result = self.call(command, _transfer_seconds(local.stat().st_size), local)
            if result.returncode != 0:
                raise ColabError(f"could not upload {local.name} to {self.session}:{remote}: {last_line(result.output)}")

    def download(self, remote: str, local: Path) -> int:
        """Bring the VM file ``remote`` to ``local`` (through ``local`` + ``.part``); returns its size."""
        quoted = shlex.quote(remote)
        answer = self.call(f"stat -c %s {quoted} && sha256sum {quoted}", 60)
        words = answer.output.split()
        if answer.returncode != 0 or len(words) < 2 or not words[0].isdigit():
            raise ColabError(f"cannot read {remote} on {self.session}: {last_line(answer.output)}")
        size, sha = int(words[0]), words[1]
        local.parent.mkdir(parents=True, exist_ok=True)
        part = local.with_name(local.name + ".part")
        result = self.call(f"cat {quoted}", _transfer_seconds(size), None, part)
        if result.returncode != 0 or sha256_file(part) != sha:
            part.unlink(missing_ok=True)
            why = last_line(result.output) if result.returncode != 0 else "SHA-256 differs"
            raise ColabError(f"could not download {remote} from {self.session}: {why}")
        os.replace(part, local)
        return size


def _transfer_seconds(size: int) -> float:
    """Time allowed for ``size`` bytes: 2 min plus 0.5 MB/s (about 2-3 MB/s measured)."""
    return 120.0 + size / 5e5
