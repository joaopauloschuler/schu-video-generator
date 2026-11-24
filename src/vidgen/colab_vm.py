"""VM side of ``vidgen remote`` and the vidgen part of ``tools/colab/setup_session.py``:
``colab exec -s NAME --env VIDGEN_ACTION=... -f colab_vm.py`` prints one line
``VIDGEN_VM {json}``.

Actions (``--env`` values stay set in the kernel, so every call passes all the keys it uses):

- ``state``: the installed vidgen's hash, whether its setup runs, and with ``VIDGEN_PROJECT`` the
  project's files (path -> SHA-256, ``VIDGEN_EXCLUDE`` top folders left out) and its run;
- ``unpack``: extract ``VIDGEN_ARCHIVE`` (.tar.gz) into ``VIDGEN_DEST``;
- ``start``: run ``VIDGEN_BIN`` with the JSON list ``VIDGEN_ARGS`` in the project, detached, as run
  ``VIDGEN_RUN`` (a retried start of the same run does nothing);
- ``poll``: the run's log from byte ``VIDGEN_OFFSET``, and when it is done its exit code and stdout.

Standard library only: it runs in the Colab kernel's Python.
"""

import hashlib
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

PREFIX = "VIDGEN_VM "
CONTENT = Path("/content")
MARKER = CONTENT / ".vidgen_setup_vidgen_done"
SETUP_SCRIPT = "/content/setup_vidgen.sh"
SETUP_LOG = CONTENT / "setup_vidgen.log"
RUN_DIR = ".vidgen-remote"
ALWAYS_SKIPPED = ("__pycache__", ".git", RUN_DIR)
LOG_CHUNK = 64_000
OUT_LIMIT = 4_000_000
# Runs the command with stdout and stderr in files, then writes its exit code (argv: out log rc cmd...).
WRAPPER = (
    "import subprocess, sys\n"
    "out, log, rc = sys.argv[1:4]\n"
    "with open(out, 'wb') as o, open(log, 'ab') as e:\n"
    "    code = subprocess.call(sys.argv[4:], stdout=o, stderr=e)\n"
    "open(rc + '.tmp', 'w').write(str(code))\n"
    "import os; os.replace(rc + '.tmp', rc)\n"
)


def running_commands(proc=Path("/proc")):
    """The command lines of the running processes, each joined with spaces."""
    lines = []
    for entry in proc.iterdir():
        if entry.name.isdigit():
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            if raw:
                lines.append(raw.rstrip(b"\0").replace(b"\0", b" ").decode("utf-8", "replace"))
    return lines


def log_info(path, tail_lines=15, max_bytes=200_000):
    """The ### milestone lines and the last lines of a log (empty when absent)."""
    try:
        with path.open("rb") as log:
            log.seek(max(0, path.stat().st_size - max_bytes))
            lines = log.read().decode("utf-8", "replace").replace("\r", "\n").splitlines()
    except OSError:
        return {"exists": False, "milestones": [], "tail": []}
    return {"exists": True, "milestones": [ln for ln in lines if ln.startswith("###")], "tail": lines[-tail_lines:]}


def file_hashes(root, exclude):
    """Relative POSIX path -> SHA-256 of every file under ``root``, top folders in ``exclude`` left out."""
    hashes = {}
    if not root.is_dir():
        return hashes
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if rel.parts[0] in exclude or any(part in ALWAYS_SKIPPED for part in rel.parts) or not path.is_file():
            continue
        hashes[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def pid_alive(pid, proc=Path("/proc")):
    """True when process ``pid`` runs (a zombie counts as stopped)."""
    try:
        stat = (proc / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return False
    return stat.rsplit(")", 1)[-1].split()[0] != "Z"


def run_status(project, proc=Path("/proc")):
    """The project's last run: id, running, exit code (None until it ends)."""
    run = project / RUN_DIR
    if not (run / "run.id").is_file():
        return {"id": None, "running": False, "rc": None}
    try:
        pid = int((run / "run.pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = -1
    alive = pid_alive(pid, proc)   # before reading run.rc: the wrapper writes it just before it ends
    rc_file = run / "run.rc"
    rc = int(rc_file.read_text(encoding="utf-8").strip()) if rc_file.is_file() else None
    return {"id": (run / "run.id").read_text(encoding="utf-8").strip(), "running": rc is None and alive, "rc": rc}


def state(env, proc=Path("/proc")):
    marker = MARKER.read_text(encoding="utf-8").strip() if MARKER.is_file() else None
    reply = {"vidgen": {"hash": marker or None,
                        "setup_running": any(f"bash {SETUP_SCRIPT}" in c for c in running_commands(proc)),
                        "log": log_info(SETUP_LOG)}}
    if env.get("VIDGEN_PROJECT"):
        project = Path(env["VIDGEN_PROJECT"])
        reply["project"] = {"exists": project.is_dir(),
                            "files": file_hashes(project, set(json.loads(env.get("VIDGEN_EXCLUDE") or "[]")))}
        reply["run"] = run_status(project, proc)
    return reply


def unpack(env):
    archive, dest = Path(env["VIDGEN_ARCHIVE"]), Path(env["VIDGEN_DEST"])
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                return {"error": f"unsafe path in the archive: {member.name}"}
        tar.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    return {"count": len(members)}


def start(env, proc=Path("/proc")):
    project = Path(env["VIDGEN_PROJECT"])
    run_id = env["VIDGEN_RUN"]
    run = project / RUN_DIR
    status = run_status(project, proc)
    if status["id"] == run_id:
        return {"started": False, "run": status}
    if status["running"]:
        return {"error": f"run {status['id']} is still going on in {project}; wait for it"}
    run.mkdir(parents=True, exist_ok=True)
    for name in ("run.rc", "run.out", "run.log", "run.pid"):
        (run / name).unlink(missing_ok=True)
    (run / "run.id").write_text(run_id, encoding="utf-8")
    command = [env["VIDGEN_BIN"], *json.loads(env["VIDGEN_ARGS"])]
    child = subprocess.Popen([sys.executable, "-c", WRAPPER, str(run / "run.out"), str(run / "run.log"),
                              str(run / "run.rc"), *command], cwd=project, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (run / "run.pid").write_text(str(child.pid), encoding="utf-8")
    return {"started": True, "run": run_status(project, proc)}


def poll(env, proc=Path("/proc")):
    project = Path(env["VIDGEN_PROJECT"])
    run = project / RUN_DIR
    status = run_status(project, proc)
    offset = int(env.get("VIDGEN_OFFSET") or 0)
    data = b""
    log = run / "run.log"
    if log.is_file():
        with log.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(LOG_CHUNK)
    # Done once the run ended and the whole log was sent; until then only whole lines go.
    done = not status["running"] and len(data) < LOG_CHUNK
    if not done:
        cut = data.rfind(b"\n") + 1
        data = data[:cut] if cut else data
    reply = {"run": status, "log": data.decode("utf-8", "replace"), "offset": offset + len(data), "done": done}
    if done and (run / "run.out").is_file():
        reply["out"] = (run / "run.out").read_bytes()[:OUT_LIMIT].decode("utf-8", "replace")
        reply["named"] = named_files(reply["out"], project)
    return reply


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def named_files(out, project):
    """Relative path -> size of the files in the project that the JSON document ``out`` names."""
    try:
        doc = json.loads(out)
    except ValueError:
        return {}
    prefix = str(project).rstrip("/") + "/"
    named = {}
    for text in _strings(doc):
        if text.startswith(prefix) and Path(text).is_file():
            named[text[len(prefix):]] = Path(text).stat().st_size
    return named


ACTIONS = {"state": state, "unpack": unpack, "start": start, "poll": poll}


def main(env):
    action = ACTIONS.get(env.get("VIDGEN_ACTION", ""))
    try:
        reply = action(env) if action else {"error": f"unknown VIDGEN_ACTION {env.get('VIDGEN_ACTION')!r}"}
    except Exception as exc:  # noqa: BLE001 - the local side shows it
        reply = {"error": f"{type(exc).__name__}: {exc}"}
    print(PREFIX + json.dumps(reply), flush=True)


if __name__ == "__main__":
    main(dict(os.environ))
