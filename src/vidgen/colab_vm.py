"""VM side of ``vidgen remote`` and the vidgen part of ``tools/colab/setup_session.py``:
``colab exec -s NAME --env VIDGEN_ACTION=... -f colab_vm.py`` prints one line
``VIDGEN_VM {json}``.

Actions (``--env`` values stay set in the kernel, so every call passes all the keys,
``vidgen.colab.VM_KEYS``, blank when unused). Each is safe to repeat after a dropped call:

- ``state``: the installed vidgen's hash, whether its setup runs, the arguments the running
  ComfyUI was started with (:func:`comfy_args`) and its and its VRAM sampler's PIDs (:func:`comfy_pids`), and with ``VIDGEN_PROJECT`` the project's files
  (path -> SHA-256, ``VIDGEN_EXCLUDE`` top folders left out) and its run;
- ``begin``: once per run id ``VIDGEN_RUN`` (a repeat only reports the run): with ``VIDGEN_HASH``,
  stop unless the installed vidgen has that hash; extract ``VIDGEN_ARCHIVE`` (.tar or .tar.gz)
  into the project ``VIDGEN_PROJECT``; with ``VIDGEN_CHECK``, stop with the ``missing`` files
  when the project's files differ from the archive's ``.vidgen-remote/want.json`` (path ->
  SHA-256); then run ``VIDGEN_BIN`` with the JSON list ``VIDGEN_ARGS`` there, detached, with the
  ``KEY=VALUE`` lines of ``/content/vidgen.env`` (written by ``setup_vidgen.sh``, e.g.
  ``VIDGEN_WEBGL=gpu``) added to its environment;
- ``poll``: the run's log from byte ``VIDGEN_OFFSET``, and when it is done its exit code and
  stdout; with ``VIDGEN_PACK``, also the project's files after the run and, when it succeeded, one
  ``.vidgen-remote/result.tar`` of the files to bring back (:func:`bring_back`); with
  ``VIDGEN_NAMED`` (the rsync sync), when it succeeded, only the files its JSON document names
  (:func:`named_files`);
- ``fetch`` (files up, :mod:`vidgen.colab_transfer`): ``curl`` in a detached job gets the files
  ``VIDGEN_FILES`` (``name``, ``dest``, ``sha256``) from ``VIDGEN_URL`` (this computer's tunnel
  and secret path); a repeat waits for it, a new ``VIDGEN_ATTEMPT`` starts it again; a file is put
  in place only when its SHA-256 matches;
- ``serve`` (files down): start (once per secret ``VIDGEN_SECRET``; ``VIDGEN_RESTART``: a new
  one) the VM's tunnel: :data:`SERVE_CODE` with ``cloudflared``; link the ``VIDGEN_OFFER`` paths
  into its folder; reply its address and each file's name, size and SHA-256;
- ``unserve``: stop that tunnel and delete its folder;
- ``cloudflared``: install :data:`CLOUDFLARED_VERSION` (once).

Standard library only: it runs in the Colab kernel's Python.
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from urllib.parse import urlsplit

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


#: The cloudflared release the setup installs on the VM (the linux-amd64 binary).
CLOUDFLARED_VERSION = "2026.10.7"
CLOUDFLARED_URL = ("https://github.com/cloudflare/cloudflared/releases/download/"
                   f"{CLOUDFLARED_VERSION}/cloudflared-linux-amd64")
CLOUDFLARED = CONTENT / "bin" / "cloudflared"
CLOUDFLARED_MARKER = CONTENT / ".vidgen_cloudflared_done"
TUNNEL_DIR = CONTENT / ".vidgen-tunnel"
FETCH_DIR = CONTENT / ".vidgen-fetch"
#: How long one exec waits for a tunnel or a fetch before it answers "not yet".
WAIT_SECONDS = 14.0
#: A VM tunnel stops by itself after this long (a killed vidgen cannot close it).
TUNNEL_MAX_SECONDS = 6 * 3600
PART = ".vidgen-part"
MASK = "***"

# The tunnel process, on both sides (argv: folder state cloudflared max_seconds watch_stdin; the
# secret in env VIDGEN_SERVE_SECRET). It serves only GET/HEAD /<secret>/<name> of the files right
# in the folder on 127.0.0.1, a plain 404 for anything else, no listing; runs cloudflared on that
# port and writes its address to the state file; stops (cloudflared too) when cloudflared ends,
# after max_seconds, or when stdin closes (watch_stdin 1: the local vidgen ended).
SERVE_CODE = r"""
import hmac, json, os, re, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
root, state_file, cloudflared = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), sys.argv[3]
max_seconds, watch_stdin = float(sys.argv[4]), sys.argv[5] == "1"
secret = os.environ.pop("VIDGEN_SERVE_SECRET")
class Handler(BaseHTTPRequestHandler):
    def version_string(self):
        return "vidgen"
    def log_message(self, *args):
        pass
    def do_GET(self):
        self.answer(True)
    def do_HEAD(self):
        self.answer(False)
    def do_POST(self):
        self.missing()
    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST
    def missing(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "10")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b"not found\n")
    def answer(self, body):
        parts = self.path.split("?", 1)[0].split("/")
        name = parts[2] if len(parts) == 3 and parts[0] == "" else ""
        given = (parts[1] if len(parts) > 1 else "").encode("utf-8", "replace")
        if not hmac.compare_digest(given, secret.encode("utf-8")) or not name or name.startswith(".") or "\\" in name:
            return self.missing()
        path = root / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
            return self.missing()
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        if body:
            with path.open("rb") as handle:
                while chunk := handle.read(1 << 20):
                    self.wfile.write(chunk)
server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
state = {"pid": os.getpid(), "port": port, "url": None, "registered": False, "ended": False, "tail": []}
def write():
    tmp = state_file.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, state_file)
    except OSError:   # Windows: a reader holds it open; the next line writes it again
        pass
write()
command = [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate", "--protocol", "http2"]
tunnel = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace")
stop = threading.Event()
import signal
signal.signal(signal.SIGTERM, lambda *args: stop.set())   # a stop of the group: still reap cloudflared
def read():
    for line in tunnel.stdout:
        state["tail"] = (state["tail"] + [line.rstrip()])[-12:]
        found = re.search(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", line)
        if found and not state["url"]:
            state["url"] = found.group(0)
        if "Registered tunnel connection" in line:
            state["registered"] = True
        write()
    stop.set()
threading.Thread(target=read, daemon=True).start()
if watch_stdin:
    threading.Thread(target=lambda: (sys.stdin.read(), stop.set()), daemon=True).start()
stop.wait(max_seconds)
tunnel.terminate()
try:
    tunnel.wait(5)
except subprocess.TimeoutExpired:
    tunnel.kill()
state["ended"] = True
write()
server.shutdown()
"""

# The fetch job (argv: curl config, rc file, host): waits (up to 90 s) until the new tunnel's
# host resolves, runs curl with retries, then deletes the config (it holds the secret) and writes
# the exit code.
FETCH_CODE = (
    "import os, socket, subprocess, sys, time\n"
    "cfg, rc, host = sys.argv[1:4]\n"
    "for _ in range(90):\n"
    "    try:\n"
    "        socket.getaddrinfo(host, 443)\n"
    "        break\n"
    "    except OSError:\n"
    "        time.sleep(1)\n"
    "with open(rc + '.log', 'wb') as log:\n"
    "    code = subprocess.call(['curl', '-sS', '--fail', '--create-dirs', '--retry', '3', '--retry-delay', '2',\n"
    "                            '--retry-all-errors', '--connect-timeout', '20', '-K', cfg], stdout=log, stderr=log)\n"
    "os.unlink(cfg)\n"
    "open(rc + '.tmp', 'w').write(str(code))\n"
    "os.replace(rc + '.tmp', rc)\n"
)


def masked(text, secret):
    """``text`` with ``secret`` replaced by :data:`MASK`."""
    return text.replace(secret, MASK) if secret else text


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _stop_group(pid):
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _curl_quote(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fetch(env, proc=Path("/proc"), wait_seconds=None):
    """Get ``VIDGEN_FILES`` from ``VIDGEN_URL`` with a detached curl (see the module docstring)."""
    files = json.loads(env["VIDGEN_FILES"])
    base, attempt = env["VIDGEN_URL"], env.get("VIDGEN_ATTEMPT") or "1"
    secret = base.rstrip("/").rsplit("/", 1)[-1]
    job = FETCH_DIR / hashlib.sha256(env["VIDGEN_FILES"].encode("utf-8")).hexdigest()[:16]
    pending = [f for f in files if not (Path(f["dest"]).is_file() and sha256_file(Path(f["dest"])) == f["sha256"])]
    if not pending:
        shutil.rmtree(job, ignore_errors=True)
        return {"done": True, "ok": True}
    info = _read_json(job / "job.json")
    rc_file = job / "rc"
    if info.get("attempt") != attempt and not pid_alive(info.get("pid", -1), proc):
        shutil.rmtree(job, ignore_errors=True)
        job.mkdir(parents=True)
        cfg = job / "curl.cfg"
        handle = os.open(cfg, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as config:
            for f in pending:
                config.write(f"url = {_curl_quote(base + f['name'])}\noutput = {_curl_quote(f['dest'] + PART)}\n")
        child = subprocess.Popen([sys.executable, "-c", FETCH_CODE, str(cfg), str(rc_file), urlsplit(base).hostname or ""], start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (job / "job.json").write_text(json.dumps({"attempt": attempt, "pid": child.pid}), encoding="utf-8")
    deadline = time.time() + (WAIT_SECONDS if wait_seconds is None else wait_seconds)
    while not rc_file.is_file() and time.time() < deadline:
        time.sleep(0.3)
    if not rc_file.is_file():
        return {"done": False}
    rc = int(rc_file.read_text(encoding="utf-8").strip() or "1")
    bad = []
    for f in pending:
        part = Path(f["dest"] + PART)
        if part.is_file() and sha256_file(part) == f["sha256"]:
            os.replace(part, f["dest"])
        else:
            bad.append(f["dest"])
            part.unlink(missing_ok=True)
    if not bad:
        shutil.rmtree(job, ignore_errors=True)
        return {"done": True, "ok": True}
    log = (job / "rc.log").read_text(encoding="utf-8", errors="replace") if (job / "rc.log").is_file() else ""
    error = masked(log.strip().splitlines()[-1] if log.strip() else f"curl exit code {rc}", secret)
    if rc == 0:
        error = f"SHA-256 differs for {bad[0]}"
    # curl 6: the address did not resolve (the caller then opens a new tunnel)
    return {"done": True, "ok": False, "rc": rc, "resolve": rc == 6, "problem": error, "failed": bad}


def tunnel_id(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


def serve_start(secret, restart=False, proc=Path("/proc"), cloudflared=None, max_seconds=TUNNEL_MAX_SECONDS):
    """Start the VM's tunnel for ``secret`` unless it runs already; returns its folder."""
    info = _read_json(TUNNEL_DIR / "id.json")
    if not restart and info.get("id") == tunnel_id(secret) and pid_alive(info.get("pid", -1), proc):
        return TUNNEL_DIR / "files"
    serve_stop()
    (TUNNEL_DIR / "files").mkdir(parents=True)
    child = subprocess.Popen(
        [sys.executable, "-c", SERVE_CODE, str(TUNNEL_DIR / "files"), str(TUNNEL_DIR / "state.json"),
         str(cloudflared or CLOUDFLARED), str(max_seconds), "0"],
        env={**os.environ, "VIDGEN_SERVE_SECRET": secret}, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (TUNNEL_DIR / "id.json").write_text(json.dumps({"id": tunnel_id(secret), "pid": child.pid}), encoding="utf-8")
    return TUNNEL_DIR / "files"


def serve_stop():
    info = _read_json(TUNNEL_DIR / "id.json")
    if info.get("pid"):
        _stop_group(int(info["pid"]))
    shutil.rmtree(TUNNEL_DIR, ignore_errors=True)


def offer(path, folder):
    """Link (else copy) ``path`` into the tunnel's ``folder``; its name, size and SHA-256."""
    name = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12] + "-" + "".join(
        c if c.isalnum() or c in "._-" else "_" for c in path.name).lstrip(".")
    target = folder / name
    target.unlink(missing_ok=True)
    try:
        os.link(path, target)
    except OSError:
        shutil.copyfile(path, target)
    return {"name": name, "size": target.stat().st_size, "sha256": sha256_file(target)}


def serve(env, proc=Path("/proc"), wait_seconds=None):
    if not CLOUDFLARED.is_file():
        return {"error": "no cloudflared on the VM; install it: python tools/colab/setup_session.py NAME --vidgen-only"}
    folder = serve_start(env["VIDGEN_SECRET"], restart=bool(env.get("VIDGEN_RESTART")), proc=proc)
    files = {}
    for path in json.loads(env.get("VIDGEN_OFFER") or "[]"):
        if not Path(path).is_file():
            return {"error": f"{path} is not on the VM"}
        files[path] = offer(Path(path), folder)
    deadline = time.time() + (WAIT_SECONDS if wait_seconds is None else wait_seconds)
    while True:
        state = _read_json(TUNNEL_DIR / "state.json")
        if state.get("ended"):   # the caller opens a new one
            return {"url": None, "files": files, "problem": "the VM's cloudflared stopped: " + " | ".join(state.get("tail", [])[-3:])}
        if (state.get("url") and state.get("registered")) or time.time() >= deadline:
            break
        time.sleep(0.3)
    ready = bool(state.get("url") and state.get("registered"))
    return {"url": state["url"] if ready else None, "files": files}


def unserve(env, proc=Path("/proc")):
    serve_stop()
    return {"closed": True}


def install_cloudflared(env, proc=Path("/proc")):
    """Install :data:`CLOUDFLARED_VERSION` at :data:`CLOUDFLARED` unless the marker says it is there."""
    marker = CLOUDFLARED_MARKER.read_text(encoding="utf-8").strip() if CLOUDFLARED_MARKER.is_file() else ""
    if CLOUDFLARED.is_file() and CLOUDFLARED_VERSION in marker:
        return {"version": marker, "installed": False}
    CLOUDFLARED.parent.mkdir(parents=True, exist_ok=True)
    part = CLOUDFLARED.with_suffix(PART)
    subprocess.run(["curl", "-fsSL", "--retry", "2", "-o", str(part), CLOUDFLARED_URL], check=True,
                   capture_output=True, timeout=WAIT_SECONDS + 4)
    part.chmod(0o755)
    version = subprocess.run([str(part), "--version"], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    if CLOUDFLARED_VERSION not in version:
        return {"error": f"cloudflared from {CLOUDFLARED_URL} says {version!r}"}
    os.replace(part, CLOUDFLARED)
    CLOUDFLARED_MARKER.write_text(version, encoding="utf-8")
    return {"version": version, "installed": True}


def running_argvs(proc=Path("/proc")):
    """The argument lists of the running processes (from ``/proc/<pid>/cmdline``)."""
    return [argv for _, argv in running_pids(proc)]


def running_commands(proc=Path("/proc")):
    """The command lines of the running processes, each joined with spaces."""
    return [" ".join(argv) for argv in running_argvs(proc)]


def _comfy_rest(argv):
    """The arguments after ``main.py`` when ``argv`` is a ComfyUI server on port 8188, else None."""
    mains = [i for i, word in enumerate(argv) if word == "main.py" or word.endswith("/main.py")]
    return argv[mains[0] + 1:] if mains and "8188" in argv else None


def comfy_args(proc=Path("/proc")):
    """The arguments after ``main.py`` of the running ComfyUI server on port 8188 (the setup starts it
    so), or None when none runs."""
    for argv in running_argvs(proc):
        rest = _comfy_rest(argv)
        if rest is not None:
            return rest
    return None


def running_pids(proc=Path("/proc")):
    """``(pid, argv)`` of the running processes (from ``/proc/<pid>/cmdline``)."""
    found = []
    for entry in proc.iterdir():
        if entry.name.isdigit():
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            if raw:
                found.append((int(entry.name), raw.rstrip(b"\0").decode("utf-8", "replace").split("\0")))
    return sorted(found)


def comfy_pids(proc=Path("/proc")):
    """The PIDs of the ComfyUI servers on port 8188 and of the looping ``nvidia-smi ... -l`` VRAM
    samplers (setup_session.py stops them by these PIDs, never by a pattern)."""
    comfy, samplers = [], []
    for pid, argv in running_pids(proc):
        if _comfy_rest(argv) is not None:
            comfy.append(pid)
        elif Path(argv[0]).name == "nvidia-smi" and "-l" in argv:
            samplers.append(pid)
    return comfy, samplers


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
    pids, samplers = comfy_pids(proc)
    reply = {"vidgen": vidgen_state(proc), "comfy": {"args": comfy_args(proc), "pids": pids, "sampler_pids": samplers}}
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
    if env.get("VIDGEN_SECRET") and CLOUDFLARED.is_file():
        serve_start(env["VIDGEN_SECRET"], proc=proc)   # the results' tunnel starts while the run goes on
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
    if done and env.get("VIDGEN_NAMED") and status["rc"] == 0:
        reply["named"] = named_files(reply.get("out", ""), project)
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


ACTIONS = {"state": state, "begin": begin, "poll": poll, "fetch": fetch, "serve": serve, "unserve": unserve,
           "cloudflared": install_cloudflared}


def main(env):
    action = ACTIONS.get(env.get("VIDGEN_ACTION", ""))
    try:
        reply = action(env) if action else {"error": f"unknown VIDGEN_ACTION {env.get('VIDGEN_ACTION')!r}"}
    except Exception as exc:  # noqa: BLE001 - the local side shows it
        text = f"{type(exc).__name__}: {exc}"
        for secret in (env.get("VIDGEN_SECRET", ""), (env.get("VIDGEN_URL") or "").rstrip("/").rsplit("/", 1)[-1]):
            text = masked(text, secret)
        reply = {"error": text}
    print(PREFIX + json.dumps(reply), flush=True)


if __name__ == "__main__":
    main(dict(os.environ))
