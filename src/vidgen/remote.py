"""``vidgen remote SESSION ARGS...``: run a vidgen command on a Colab session.

On the SSH route with an ``rsync`` here (:mod:`vidgen.colab_rsync`) it syncs the project to
``/content/projects/<name>/`` with rsync over the ssh master (files deleted here are deleted
there; the left-out folders are never touched on the VM), checks the VM's vidgen and starts the run
in one call, polls the log the same way as below, and after a run that succeeded rsyncs back the
files its JSON document names, what it made outside the left-out folders, and ``build/`` without
its big render caches (stills, storyboard sheets, the shots' cut inputs come back).

Otherwise (``--via exec``, or no rsync) it sends the files the VM lacks in one tar (which ones
comes from the VM's file list cached in ``.vidgen-remote/``, the VM reports any it still lacks;
files deleted here stay there), and in the same call checks that the VM's vidgen is this
computer's code (:func:`vidgen.colab.package_hash`) and starts ``vidgen ARGS`` there detached. It
polls the log (after 2 s, 5 s, then every 10 s), then brings back in one tar what the next step
needs: the files the command's JSON document names inside the project (not under ``build/``,
except the render's ``timings.json``) and the files the run created or changed outside the
left-out folders. The tars go over ssh, or on the exec route through Cloudflare quick tunnels
(:mod:`vidgen.colab_transfer`; the VM's one starts with the run).
``build/`` stays on the VM as a cache. Standard library only; it never stops the session.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import secrets
import tarfile
import tempfile
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from vidgen import colab_rsync
from vidgen.colab import VM_PROJECTS, Colab, ColabError, extract_archive, format_seconds, package_hash, shown
from vidgen.colab_rsync import ALWAYS_SKIPPED

#: Top folders of a project that are never synced (generated); ``--exclude`` adds more.
EXCLUDED_DIRS: tuple[str, ...] = ("build", "output", "exports", "media")
#: vidgen in the VM's venv (tools/colab/setup_vidgen.sh).
VM_VIDGEN = "/content/vidgen-venv/bin/vidgen"
LOG_TAIL_LINES = 30
#: The pauses between log polls: 2 s, 5 s, then 10 s each.
POLL_PAUSES: tuple[float, ...] = (2.0, 5.0, 10.0)
#: Where the VM's want-list goes in the sync archive (``colab_vm.WANT``).
WANT = ".vidgen-remote/want.json"


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


def parse_document(out: str) -> dict[str, Any] | None:
    """The JSON document a ``--json`` command printed on stdout, or None."""
    try:
        doc = json.loads(out)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def sync_archive(root: Path, relpaths: list[str], want: dict[str, str], dest: Path) -> Path:
    """Write ``dest`` (.tar): ``root``'s files ``relpaths`` and :data:`WANT` holding ``want``."""
    with tarfile.open(dest, "w") as archive:
        for rel in relpaths:
            archive.add(root / Path(rel), arcname=rel)
        data = json.dumps(want).encode("utf-8")
        info = tarfile.TarInfo(WANT)
        info.size = len(data)
        info.mtime = int(time.time())
        archive.addfile(info, io.BytesIO(data))
    return dest


@dataclass
class RemoteRun:
    """One ``vidgen remote`` call: ``run()`` returns the exit code of the command on the VM."""

    colab: Colab
    project_dir: Path
    args: list[str]
    json_commands: Sequence[str] = ()
    exclude: Sequence[str] = EXCLUDED_DIRS
    clock: Callable[[], float] = time.monotonic
    poll_pauses: Sequence[float] = POLL_PAUSES
    max_poll_failures: int = 3
    local_hash: str | None = None
    fetched: list[str] = field(default_factory=list)

    @property
    def remote_dir(self) -> str:
        return f"{VM_PROJECTS}/{vm_name(self.project_dir)}"

    @property
    def cache_path(self) -> Path:
        """The VM's file list as last seen, per session (``.vidgen-remote/`` is never synced)."""
        digest = hashlib.sha256(f"{self.colab.session}\0{self.remote_dir}".encode("utf-8")).hexdigest()[:12]
        return self.project_dir / ".vidgen-remote" / f"vm-files-{digest}.json"

    def known_files(self) -> dict[str, str] | None:
        try:
            files = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return files if isinstance(files, dict) else None

    def remember_files(self, files: dict[str, str]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(files), encoding="utf-8")

    def vm_state(self) -> dict[str, Any]:
        return self.colab.vm("state", VIDGEN_PROJECT=self.remote_dir, VIDGEN_EXCLUDE=json.dumps(list(self.exclude)))

    def run(self) -> int:
        session = self.colab.session
        if session not in self.colab.sessions():
            raise ColabError(f"no Colab session {session!r} (colab sessions); create and set it up: {setup_command(session)}")
        begin = self.clock()
        args, asked_json = with_json(self.args, self.json_commands)
        run_id = f"{int(time.time())}-{secrets.token_hex(3)}"
        rsync = self.colab.via == "ssh" and colab_rsync.available()
        if rsync:
            self.send_rsync()
            self.begin_run(run_id, args)
        else:
            if self.colab.via == "ssh":
                self.colab.say("   no rsync on this computer: changed files go in a tar (files deleted here stay on the VM)")
            local = local_hashes(self.project_dir, self.exclude)
            known = self.known_files()
            if known is None:   # the first run from here: ask the VM what it has
                state = self.vm_state()
                self.check_version(state["vidgen"])
                known = state["project"]["files"]
            self.start(local, known, run_id, args)
        reply, log = self.follow(run_id, pack=not rsync)
        if "files" in reply:
            self.remember_files(reply["files"])
        rc = reply["run"]["rc"]
        seconds = format_seconds(self.clock() - begin)
        if rc != 0:
            tail = "\n".join("   " + line for line in log.splitlines()[-LOG_TAIL_LINES:])
            self.colab.say(f"## vidgen failed on {session} (exit code {rc}) after {seconds}; last lines of the log:\n{tail}")
            return 1 if rc is None else int(rc)
        if rsync:
            self.fetch_rsync(reply.get("named") or [])
        else:
            self.fetch(reply.get("result") or {})
        doc = parse_document(reply.get("out", ""))
        if asked_json and doc is not None:
            print(json.dumps(doc, indent=2), flush=True)
        self.colab.say(f"## done on {session} in {format_seconds(self.clock() - begin)}; brought back "
                       f"{len(self.fetched)} file(s); the rest stays in {self.remote_dir} on the VM")
        return 0

    def check_version(self, vm: dict[str, Any]) -> None:
        """Fail with the setup command when the VM's vidgen (``vm``: hash, setup_running) is not this
        computer's code."""
        local = self.local_hash or package_hash()
        if vm["hash"] == local:
            return
        found = f"vidgen {vm['hash']}" if vm["hash"] else "no vidgen"
        running = " (its setup is running now; wait for it)" if vm["setup_running"] else ""
        raise ColabError(f"{self.colab.session} has {found}{running}, this computer's code is {local}; "
                         f"install it there: {setup_command(self.colab.session)}")

    def send_rsync(self) -> None:
        """Sync the project to the VM with rsync (:func:`vidgen.colab_rsync.up_args`)."""
        self.colab.say(f"## sync (rsync over ssh) -> {self.remote_dir}")
        sent = self.clock()
        moved = colab_rsync.run(self.colab.link, colab_rsync.up_args(self.colab.link, str(self.project_dir), self.remote_dir,
                                                                    self.exclude), "send the project")
        deleted = f", {len(moved.deleted)} deleted there" if moved.deleted else ""
        self.colab.say(f"   sent {len(moved.files)} file(s) ({moved.size / 1e6:.1f} MB){deleted} in "
                       f"{format_seconds(self.clock() - sent)}")

    def begin_run(self, run_id: str, args: list[str]) -> None:
        """Check the VM's vidgen and start the run (the files are there already)."""
        self.colab.say(f"## running on {self.colab.session}: vidgen {' '.join(args)}")
        reply = self.colab.vm("begin", VIDGEN_PROJECT=self.remote_dir, VIDGEN_RUN=run_id, VIDGEN_BIN=VM_VIDGEN,
                              VIDGEN_ARGS=json.dumps(args), VIDGEN_HASH=self.local_hash or package_hash())
        if "vidgen" in reply:
            self.check_version(reply["vidgen"])

    def fetch_rsync(self, named: list[str]) -> None:
        """Bring back with rsync the ``named`` files, the run's other files and ``build/`` without
        its caches (:func:`vidgen.colab_rsync.down_args`)."""
        got = self.clock()
        moved = colab_rsync.run(self.colab.link, colab_rsync.down_args(self.colab.link, self.remote_dir, str(self.project_dir),
                                                                      self.exclude, named), "bring back the results")
        built = [rel for rel in moved.files if rel.startswith("build/")]
        self.colab.say(f"   brought back {moved.size / 1e6:.1f} MB in {format_seconds(self.clock() - got)}"
                       + (f" ({len(built)} file(s) in build/)" if built else ""))
        for rel, size in moved.files.items():
            self.fetched.append(rel)
            if not rel.startswith("build/"):
                self.colab.say(f"   fetched {rel} ({size / 1e6:.2f} MB)")

    def start(self, local: dict[str, str], known: dict[str, str], run_id: str, args: list[str]) -> None:
        """Send the files the VM lacks in one tar and start the run in the same exec; a second round
        sends what the VM still reports missing (its files changed since the cached list)."""
        archive_name = f".vidgen-sync-{run_id}.tar"
        for _ in range(2):
            changed = changed_files(local, known)
            size = sum((self.project_dir / rel).stat().st_size for rel in changed)
            self.colab.say(f"## sync: {len(changed)} of {len(local)} files to send ({size / 1e6:.1f} MB) -> {self.remote_dir}")
            sent = self.clock()
            with tempfile.TemporaryDirectory() as tmp:
                archive = sync_archive(self.project_dir, changed, local, Path(tmp) / archive_name)
                self.colab.upload(archive, f"/content/{archive_name}")
            self.colab.say(f"   sent in {format_seconds(self.clock() - sent)}")
            self.colab.say(f"## running on {self.colab.session}: vidgen {' '.join(args)}")
            reply = self.colab.vm("begin", VIDGEN_PROJECT=self.remote_dir, VIDGEN_RUN=run_id, VIDGEN_BIN=VM_VIDGEN,
                                  VIDGEN_ARGS=json.dumps(args), VIDGEN_HASH=self.local_hash or package_hash(),
                                  VIDGEN_ARCHIVE=f"/content/{archive_name}", VIDGEN_CHECK="1",
                                  VIDGEN_EXCLUDE=json.dumps(list(self.exclude)), **self.colab.prestart_env())
            if "vidgen" in reply:
                self.check_version(reply["vidgen"])
            missing = reply.get("missing")
            if not missing:
                return
            known = {rel: digest for rel, digest in known.items() if rel not in set(missing)}
            self.colab.say(f"   the VM lacks {len(missing)} more file(s); sending them")
        raise ColabError(f"{self.colab.session} still lacks {len(missing)} file(s) after a second upload, e.g. {missing[0]}")

    def follow(self, run_id: str, pack: bool = True) -> tuple[dict[str, Any], str]:
        """Poll the run's log until it ends, printing each new line; returns the last reply and the log.
        The last reply has the result tar (``pack``) or the files the JSON document names."""
        offset, failures, polls, log = 0, 0, 0, ""
        while True:
            self.colab.sleep(self.poll_pauses[min(polls, len(self.poll_pauses) - 1)])
            polls += 1
            try:
                reply = self.colab.vm("poll", VIDGEN_PROJECT=self.remote_dir, VIDGEN_OFFSET=str(offset),
                                      **({"VIDGEN_PACK": "1"} if pack else {"VIDGEN_NAMED": "1"}),
                                      VIDGEN_EXCLUDE=json.dumps(list(self.exclude)))
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

    def fetch(self, result: dict[str, Any]) -> None:
        """Download the run's result tar (``colab_vm.pack``) and unpack it into the project."""
        if not result.get("archive"):
            return
        got = self.clock()
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "result.tar"
            self.colab.download(result["archive"], local)
            extract_archive(local, self.project_dir)
        self.colab.say(f"   result ({int(result['size']) / 1e6:.1f} MB) brought back in {format_seconds(self.clock() - got)}")
        for rel, size in result["files"].items():
            self.fetched.append(rel)
            self.colab.say(f"   fetched {rel} ({size / 1e6:.2f} MB)")
