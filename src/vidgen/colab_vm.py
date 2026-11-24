"""VM side of ``vidgen remote`` and the vidgen part of ``tools/colab/setup_session.py``:
``colab exec -s NAME --env VIDGEN_ACTION=... -f colab_vm.py`` prints one line
``VIDGEN_VM {json}``.

Actions (``--env`` values stay set in the kernel, so every call passes all the keys,
``vidgen.colab.VM_KEYS``, blank when unused). Each is safe to repeat after a dropped call:

- ``state``: the installed vidgen's hash, whether its setup runs, and with ``VIDGEN_PROJECT`` the
  project's files (path -> SHA-256, ``VIDGEN_EXCLUDE`` top folders left out) and its run;
- ``begin``: once per run id ``VIDGEN_RUN`` (a repeat only reports the run): with ``VIDGEN_HASH``,
  stop unless the installed vidgen has that hash; extract ``VIDGEN_ARCHIVE`` (.tar or .tar.gz)
  into the project ``VIDGEN_PROJECT``; with ``VIDGEN_CHECK``, stop with the ``missing`` files
  when the project's files differ from the archive's ``.vidgen-remote/want.json`` (path ->
  SHA-256); then run ``VIDGEN_BIN`` with the JSON list ``VIDGEN_ARGS`` there, detached, with the
  ``KEY=VALUE`` lines of ``/content/vidgen.env`` (written by ``setup_vidgen.sh``, e.g.
  ``VIDGEN_WEBGL=gpu``) added to its environment;
- ``poll``: the run's log from byte ``VIDGEN_OFFSET``, and when it is done its exit code and
  stdout; with ``VIDGEN_PACK``, also the project's files after the run and, when it succeeded, one
  ``.vidgen-remote/result.tar`` of the files to bring back (:func:`bring_back`).

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
ENV_FILE = CONTENT / "vidgen.env"
RUN_DIR = ".vidgen-remote"
WANT = RUN_DIR + "/want.json"
RESULT = "result.tar"
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


def vidgen_state(proc=Path("/proc")):
    """The installed vidgen's hash (None without one), whether its setup runs, and its log."""
    marker = MARKER.read_text(encoding="utf-8").strip() if MARKER.is_file() else None
    return {"hash": marker or None, "setup_running": any(f"bash {SETUP_SCRIPT}" in c for c in running_commands(proc)),
            "log": log_info(SETUP_LOG)}


def excluded(env):
    return set(json.loads(env.get("VIDGEN_EXCLUDE") or "[]"))


def state(env, proc=Path("/proc")):
    reply = {"vidgen": vidgen_state(proc)}
    if env.get("VIDGEN_PROJECT"):
        project = Path(env["VIDGEN_PROJECT"])
        reply["project"] = {"exists": project.is_dir(), "files": file_hashes(project, excluded(env))}
        reply["run"] = run_status(project, proc)
    return reply


def unpack(archive, dest):
    """Extract ``archive`` into ``dest``; returns the member names (ValueError on an unsafe path)."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tar:
        members = tar.getmembers()
        for member in members:
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise ValueError(f"unsafe path in the archive: {member.name}")
        tar.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    return [member.name for member in members]


def missing_files(project, want):
    """The paths of ``want`` (path -> SHA-256) that the project lacks or has with other bytes."""
    missing = []
    for rel, digest in sorted(want.items()):
        path = project / rel
        if not (path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest):
            missing.append(rel)
    return missing


def begin(env, proc=Path("/proc")):
    project = Path(env["VIDGEN_PROJECT"])
    status = run_status(project, proc)
    if status["id"] == env["VIDGEN_RUN"]:
        return {"started": False, "run": status}
    if status["running"]:
        return {"error": f"run {status['id']} is still going on in {project}; wait for it"}
    if env.get("VIDGEN_HASH"):
        vidgen = vidgen_state(proc)
        if vidgen["hash"] != env["VIDGEN_HASH"]:
            return {"started": False, "vidgen": vidgen}
    archive = Path(env["VIDGEN_ARCHIVE"]) if env.get("VIDGEN_ARCHIVE") else None
    if archive is not None and archive.is_file():
        unpack(archive, project)
    if env.get("VIDGEN_CHECK"):
        want_file = project / WANT
        want = json.loads(want_file.read_text(encoding="utf-8")) if want_file.is_file() else {}
        missing = missing_files(project, want)
        if missing:
            return {"started": False, "missing": missing}
    reply = start(env, proc)
    if archive is not None:
        archive.unlink(missing_ok=True)
    return reply


def run_env(env_file=None):
    """This process's environment plus the ``KEY=VALUE`` lines of ``env_file`` (default
    :data:`ENV_FILE`; missing: nothing added; blank and ``#`` lines skipped)."""
    env_file = ENV_FILE if env_file is None else env_file
    env = dict(os.environ)
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                env[key] = value
    return env


def start(env, proc=Path("/proc")):
    project = Path(env["VIDGEN_PROJECT"])
    run_id = env["VIDGEN_RUN"]
    run = project / RUN_DIR
    run.mkdir(parents=True, exist_ok=True)
    for name in ("run.rc", "run.out", "run.log", "run.pid", RESULT):
        (run / name).unlink(missing_ok=True)
    (run / "run.id").write_text(run_id, encoding="utf-8")
    command = [env["VIDGEN_BIN"], *json.loads(env["VIDGEN_ARGS"])]
    child = subprocess.Popen([sys.executable, "-c", WRAPPER, str(run / "run.out"), str(run / "run.log"),
                              str(run / "run.rc"), *command], cwd=project, env=run_env(), start_new_session=True,
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
    if done and env.get("VIDGEN_PACK"):
        reply["files"] = file_hashes(project, excluded(env))
        if status["rc"] == 0:
            want_file = project / WANT
            want = json.loads(want_file.read_text(encoding="utf-8")) if want_file.is_file() else {}
            reply["result"] = pack(project, bring_back(reply.get("out", ""), project, reply["files"], want))
    return reply


def pack(project, relpaths):
    """Write ``.vidgen-remote/result.tar`` with ``relpaths``; its path, size and each file's size."""
    if not relpaths:
        return {"archive": None, "size": 0, "files": {}}
    target = project / RUN_DIR / RESULT
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".tmp")
    with tarfile.open(partial, "w") as tar:
        for rel in relpaths:
            tar.add(project / rel, arcname=rel)
    os.replace(partial, target)
    return {"archive": str(target), "size": target.stat().st_size,
            "files": {rel: (project / rel).stat().st_size for rel in relpaths}}


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
    """The project files the JSON document ``out`` names (relative paths, existing files): none under
    ``build/`` except the render's ``outputs.timings``."""
    try:
        doc = json.loads(out)
    except ValueError:
        return []
    if not isinstance(doc, dict):
        return []
    outputs = doc.get("outputs")
    timings = outputs.get("timings") if isinstance(outputs, dict) else None
    prefix = str(project).rstrip("/") + "/"
    named = []
    for text in _strings(doc):
        rel = text[len(prefix):] if text.startswith(prefix) else ""
        if rel and (not rel.startswith("build/") or text == timings) and rel not in named and Path(text).is_file():
            named.append(rel)
    return named


def bring_back(out, project, after, want):
    """What a run sends back: the files its JSON document names, then the files outside the
    left-out folders (``after``, path -> SHA-256) that differ from what was sent (``want``)."""
    changed = [rel for rel, digest in sorted(after.items()) if want.get(rel) != digest]
    return list(dict.fromkeys(named_files(out, project) + changed))


ACTIONS = {"state": state, "begin": begin, "poll": poll}


def main(env):
    action = ACTIONS.get(env.get("VIDGEN_ACTION", ""))
    try:
        reply = action(env) if action else {"error": f"unknown VIDGEN_ACTION {env.get('VIDGEN_ACTION')!r}"}
    except Exception as exc:  # noqa: BLE001 - the local side shows it
        reply = {"error": f"{type(exc).__name__}: {exc}"}
    print(PREFIX + json.dumps(reply), flush=True)


if __name__ == "__main__":
    main(dict(os.environ))
