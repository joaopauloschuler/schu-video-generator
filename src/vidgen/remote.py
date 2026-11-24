"""``vidgen remote SESSION ARGS...``: run a vidgen command on a Colab session.

From the project folder it syncs the changed files up to ``/content/projects/<name>/`` on the VM,
checks that the VM's vidgen is this computer's code (:func:`vidgen.colab.package_hash`), runs
``vidgen ARGS`` there detached and streams its log, then brings back what the next step needs:
the files the command's JSON document names inside the project (not under ``build/``, except the
render's ``timings.json``) and the files the run created or changed outside the left-out folders.
``build/`` stays on the VM as a cache. Standard library only; it never stops the session.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import tempfile
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from vidgen.colab import VM_PROJECTS, Colab, ColabError, files_archive, format_seconds, package_hash, shown

#: Top folders of a project that are never synced (generated); ``--exclude`` adds more.
EXCLUDED_DIRS: tuple[str, ...] = ("build", "output", "exports", "media")
#: Folders skipped at any depth.
ALWAYS_SKIPPED: tuple[str, ...] = ("__pycache__", ".git", ".vidgen-remote")
#: vidgen in the VM's venv (tools/colab/setup_vidgen.sh).
VM_VIDGEN = "/content/vidgen-venv/bin/vidgen"
LOG_TAIL_LINES = 30


def setup_command(session: str) -> str:
    """The command that installs this computer's vidgen on ``session``."""
    script = Path(__file__).resolve().parents[2] / "tools" / "colab" / "setup_session.py"
    where = str(script) if script.is_file() else "tools/colab/setup_session.py (in vidgen's source folder)"
    return f"python {shown(where)} {shown(session)} --vidgen-only"


def vm_name(project_dir: Path) -> str:
    """The project's folder name on the VM (characters other than letters, digits, ``._-`` become ``_``)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", project_dir.resolve().name) or "project"


def local_hashes(root: Path, exclude: Iterable[str]) -> dict[str, str]:
    """Relative POSIX path -> SHA-256 of the project's files, the ``exclude`` top folders left out
    (the same rule as ``colab_vm.file_hashes``)."""
    excluded = set(exclude)
    hashes = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts[0] in excluded or any(part in ALWAYS_SKIPPED for part in rel.parts) or not path.is_file():
            continue
        hashes[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def changed_files(local: dict[str, str], remote: dict[str, str]) -> list[str]:
    """The paths of ``local`` that the VM lacks or has with other bytes."""
    return [rel for rel, digest in local.items() if remote.get(rel) != digest]


def with_json(args: Sequence[str], json_commands: Iterable[str]) -> tuple[list[str], bool]:
    """``args`` with ``--json`` added when the command has a JSON document; and whether the
    caller asked for it themselves."""
    args = list(args)
    asked = "--json" in args
    if args and args[0] in set(json_commands) and not asked:
        args.append("--json")
    return args, asked


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def named_files(doc: dict[str, Any] | None, remote_dir: str) -> list[str]:
    """The project files a JSON document names (relative paths): none under ``build/`` except the
    render's ``outputs.timings``."""
    if not doc:
        return []
    prefix = remote_dir.rstrip("/") + "/"
    timings = (doc.get("outputs") or {}).get("timings") if isinstance(doc.get("outputs"), dict) else None
    found = []
    for text in _strings(doc):
        if text.startswith(prefix):
            rel = text[len(prefix):]
            if rel and (not rel.startswith("build/") or text == timings) and rel not in found:
                found.append(rel)
    return found


def parse_document(out: str) -> dict[str, Any] | None:
    """The JSON document a ``--json`` command printed on stdout, or None."""
    try:
        doc = json.loads(out)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


@dataclass
class RemoteRun:
    """One ``vidgen remote`` call: ``run()`` returns the exit code of the command on the VM."""

    colab: Colab
    project_dir: Path
    args: list[str]
    json_commands: Sequence[str] = ()
    exclude: Sequence[str] = EXCLUDED_DIRS
    clock: Callable[[], float] = time.monotonic
    poll_seconds: float = 5.0
    max_poll_failures: int = 3
    local_hash: str | None = None
    fetched: list[str] = field(default_factory=list)

    @property
    def remote_dir(self) -> str:
        return f"{VM_PROJECTS}/{vm_name(self.project_dir)}"

    def vm_state(self) -> dict[str, Any]:
        return self.colab.vm("state", VIDGEN_PROJECT=self.remote_dir, VIDGEN_EXCLUDE=json.dumps(list(self.exclude)))

    def run(self) -> int:
        session = self.colab.session
        if session not in self.colab.sessions():
            raise ColabError(f"no Colab session {session!r} (colab sessions); create and set it up: {setup_command(session)}")
        begin = self.clock()
        state = self.vm_state()
        self.check_version(state)
        if state["run"]["running"]:
            raise ColabError(f"a vidgen run ({state['run']['id']}) is still going on in {self.remote_dir} on {session}; wait for it")
        synced = self.sync(state["project"]["files"])
        args, asked_json = with_json(self.args, self.json_commands)
        run_id = f"{int(time.time())}-{secrets.token_hex(3)}"
        self.colab.say(f"## running on {session}: vidgen {' '.join(args)}")
        self.colab.vm("start", VIDGEN_PROJECT=self.remote_dir, VIDGEN_RUN=run_id, VIDGEN_BIN=VM_VIDGEN,
                      VIDGEN_ARGS=json.dumps(args))
        reply, log = self.follow(run_id)
        rc = reply["run"]["rc"]
        seconds = format_seconds(self.clock() - begin)
        if rc != 0:
            tail = "\n".join("   " + line for line in log.splitlines()[-LOG_TAIL_LINES:])
            self.colab.say(f"## vidgen failed on {session} (exit code {rc}) after {seconds}; last lines of the log:\n{tail}")
            return 1 if rc is None else int(rc)
        doc = parse_document(reply.get("out", ""))
        named = [rel for rel in named_files(doc, self.remote_dir) if rel in reply.get("named", {})]
        self.fetch(named + self.made_by_run(synced))
        if asked_json and doc is not None:
            print(json.dumps(doc, indent=2), flush=True)
        self.colab.say(f"## done on {session} in {seconds}; brought back {len(self.fetched)} file(s); "
                       f"the rest stays in {self.remote_dir} on the VM")
        return 0

    def check_version(self, state: dict[str, Any]) -> None:
        """Fail with the setup command when the VM's vidgen is not this computer's code."""
        local = self.local_hash or package_hash()
        vm = state["vidgen"]
        if vm["hash"] == local:
            return
        found = f"vidgen {vm['hash']}" if vm["hash"] else "no vidgen"
        running = " (its setup is running now; wait for it)" if vm["setup_running"] else ""
        raise ColabError(f"{self.colab.session} has {found}{running}, this computer's code is {local}; "
                         f"install it there: {setup_command(self.colab.session)}")

    def sync(self, remote: dict[str, str]) -> dict[str, str]:
        """Upload the project's changed files in one archive; returns the local hashes."""
        local = local_hashes(self.project_dir, self.exclude)
        changed = changed_files(local, remote)
        if not changed:
            self.colab.say(f"## sync: {len(local)} files, none changed")
            return local
        size = sum((self.project_dir / rel).stat().st_size for rel in changed)
        self.colab.say(f"## sync: {len(changed)} of {len(local)} files changed ({size / 1e6:.1f} MB) -> {self.remote_dir}")
        archive_name = f".vidgen-sync-{vm_name(self.project_dir)}.tar.gz"
        with tempfile.TemporaryDirectory() as tmp:
            archive = files_archive(self.project_dir, changed, Path(tmp) / archive_name)
            self.colab.upload(archive, f"/content/{archive_name}")
        self.colab.vm("unpack", VIDGEN_ARCHIVE=f"/content/{archive_name}", VIDGEN_DEST=self.remote_dir)
        return local

    def follow(self, run_id: str) -> tuple[dict[str, Any], str]:
        """Poll the run's log until it ends, printing each new line; returns the last reply and the log."""
        offset, failures, log = 0, 0, ""
        while True:
            try:
                reply = self.colab.vm("poll", VIDGEN_PROJECT=self.remote_dir, VIDGEN_OFFSET=str(offset))
            except ColabError as exc:
                failures += 1
                if failures >= self.max_poll_failures:
                    raise ColabError(f"{exc}; the run may still go on: its log is {self.remote_dir}/.vidgen-remote/run.log") from exc
                self.colab.say(f"   {exc}; still waiting")
                continue
            failures = 0
            if reply["run"]["id"] != run_id:
                raise ColabError(f"another run ({reply['run']['id']}) replaced run {run_id} in {self.remote_dir}")
            text = reply["log"].replace("\r\n", "\n").replace("\r", "\n")
            for line in text.splitlines():
                if line.strip():
                    self.colab.say(f"   {line}")
            log += text
            offset = reply["offset"]
            if reply["done"]:
                return reply, log
            if not reply["log"]:
                self.colab.sleep(self.poll_seconds)

    def made_by_run(self, synced: dict[str, str]) -> list[str]:
        """The files outside the left-out folders that the run created or changed."""
        after = self.vm_state()["project"]["files"]
        return changed_files(after, synced)

    def fetch(self, relpaths: list[str]) -> None:
        for rel in dict.fromkeys(relpaths):
            local = self.project_dir / Path(rel)
            self.colab.download(f"{self.remote_dir}/{rel}", local)
            self.fetched.append(rel)
            self.colab.say(f"   fetched {rel} ({local.stat().st_size / 1e6:.2f} MB)")
