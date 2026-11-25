"""Find or create a Google Colab GPU session and set it up for docs/HOWTO-restyle-with-ltx-on-colab.md.

    python tools/colab/setup_session.py NAME [--gpu L4|CPU] [--high-mem] [--no-image] [--latest] [--no-comfy-compiler]
                                       [--no-vidgen | --vidgen-only]

Runs on your machine (standard library only, Windows too) and drives the `colab` CLI: it reuses the
session NAME when `colab sessions` lists it (else `colab new`, retried on 503), then installs
ComfyUI + the LTX-2.3 weights (setup.sh) and the image models (setup_image.sh), starts ComfyUI, and
installs this checkout's vidgen (setup_vidgen.sh), skipping each part that is already done; first
it installs cloudflared on the VM (the exec route's file transfers use it). It never stops the
session. See README.md here.

Two routes (``--via``): over SSH (the default) it creates the key ``~/.ssh/colab_ed25519`` when it is
missing, checks one SSH call right after the session exists (a failure stops it; it never falls back),
and starts every script with ``setsid nohup ... &`` over SSH; vidgen's setup starts while ComfyUI
loads. ``--via exec`` keeps the ``colab exec`` route (start_setup.py / start_comfy.py detach the
scripts from the Jupyter kernel).

ComfyUI starts with its model compiler on; ``--no-comfy-compiler`` starts it with
``--disable-comfy-compiler`` (needed by the node LTX Multi IC-LoRA). Over SSH a ComfyUI that runs with
the other setting, or that ran while setup.sh added nodes, is restarted (``vidgen.colab.comfy_args``
reads its flags on the VM).
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

TOOLS_DIR = Path(__file__).resolve().parent
REPO = TOOLS_DIR.parents[1]
sys.path.insert(0, str(REPO / "src"))  # this checkout's vidgen.colab, also when an older vidgen is installed

from vidgen.colab import (  # noqa: E402
    NO_COMPILER_FLAG, VM_SOURCE_ARCHIVE, Colab as _Colab, ColabError as SetupError, CommandResult, Runner,
    comfy_compiler_off, format_seconds, last_line as _last_line, package_hash, parse_prefixed_json, parse_sessions,
    run_command, say_now, shown, source_archive, via_arg,
)
from vidgen import colab_ssh  # noqa: E402
from vidgen.colab_ssh import SshLink, env_words  # noqa: E402
from vidgen.colab_transfer import Transfers  # noqa: E402

__all__ = ["CommandResult", "Runner", "SetupError", "format_seconds", "parse_sessions", "run_command", "say_now", "shown"]

STATE_PREFIX = "VIDGEN_STATE "
GPUS = ("T4", "L4", "G4", "H100", "A100")
#: `--gpu` choices: "CPU" makes a CPU runtime (no GPU; only with --vidgen-only).
HARDWARE = ("CPU", *GPUS)
#: Accelerators with one machine shape, where `colab new --high-mem` is ignored.
SINGLE_SHAPE = ("L4",)
UPLOADS = ("vm_state.py", "setup.sh", "setup_image.sh")
PART_SCRIPTS = {"ltx": "setup.sh", "image": "setup_image.sh"}
PART_LOGS = {"ltx": ("setup.log", "download.log"), "image": ("setup_image.log",)}
PART_TITLES = {"ltx": "ComfyUI + LTX-2.3 weights", "image": "image models (Qwen-Image-Edit, Z-Image)"}
VIDGEN_TITLE = "vidgen (this computer's code)"
VIDGEN_SCRIPT = "setup_vidgen.sh"
HOWTO = "docs/HOWTO-restyle-with-ltx-on-colab.md"
#: What the SSH check runs on the VM, and what it must print.
SSH_CHECK = "echo vidgen-ssh-ok"
#: ComfyUI and its VRAM sampler, as start_comfy.py starts them on the exec route.
COMFY_COMMAND = ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"]
VRAM_COMMAND = ["nvidia-smi", "--query-gpu=timestamp,memory.used,utilization.gpu", "--format=csv,noheader", "-l", "1"]
#: pkill/pgrep patterns of those two processes, anchored at the start of the command line (a shell whose
#: command text names them does not match).
COMFY_PATTERN = "^" + " ".join(COMFY_COMMAND[:6])
VRAM_PATTERN = "^" + " ".join(VRAM_COMMAND[:2])
#: The add-ons for a base video + a sheet in one LTX run (setup.sh installs them with the LTX part).
INGREDIENTS_LORA = "ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors"
ROUTING_NODE = "comfyui-hrnodes"
ROUTING_CLASS = "LTXMultiICLoRA"
#: Poll pauses (s) per route: an SSH call costs about 0.5 s, a `colab exec` 5-15 s.
POLLS = {"ssh": {"setup": 10.0, "comfy": 3.0, "vidgen": 10.0}, "exec": {"setup": 30.0, "comfy": 10.0, "vidgen": 20.0}}


def parse_state(text: str) -> dict | None:
    """The JSON that vm_state.py printed, or None when the line is missing (the exec dropped)."""
    return parse_prefixed_json(text, STATE_PREFIX)


def part_status(part: dict) -> str:
    """`marker` / `found` (files there, no marker) / `running` / `todo` for one part of vm_state's JSON;
    a marker with files missing (an older setup, before files were added) counts as not done."""
    if part["marker"] and not part["missing"]:
        return "marker"
    if part["running"]:
        return "running"
    if not part["missing"]:
        return "found"
    return "todo"


def detached(command: list[str], log: str, env: dict[str, str] | None = None, append: bool = False) -> str:
    """Shell words that start ``command`` with ``setsid nohup`` in the background, all output to the
    VM file ``log``, stdin from /dev/null (so the ssh call returns at once and the job outlives it).
    Put it after ``;``, never after ``&&``: ``a && b &`` backgrounds a subshell that keeps the ssh
    channel open until the job ends."""
    words = [*(env_words(env) if env else []), "setsid", "nohup", *(shlex.quote(w) for w in command)]
    return " ".join([*words, ">>" if append else ">", shlex.quote(log), "2>&1 < /dev/null &"])


def setup_command(script: str, env: dict[str, str]) -> str:
    """Start ``/content/<script>`` (log ``/content/<stem>.log``, as start_setup.py names it) over ssh."""
    return "cd /content || exit 3; " + detached(["bash", f"/content/{script}"], f"/content/{Path(script).stem}.log", env) \
        + " echo started $!"


def comfy_command(no_compiler: bool = False) -> str:
    """Start ComfyUI on 127.0.0.1:8188 (with ``--disable-comfy-compiler`` when ``no_compiler``) and the
    1 s VRAM sampler over ssh (as start_comfy.py does)."""
    command = [*COMFY_COMMAND, NO_COMPILER_FLAG] if no_compiler else COMFY_COMMAND
    return ("cd /content/ComfyUI || exit 3; " + detached(command, "/content/comfy.log", append=True) + " "
            + detached(VRAM_COMMAND, "/content/vram.csv", append=True) + " echo started $!")


def comfy_stop_command() -> str:
    """Stop ComfyUI and the VRAM sampler over ssh: SIGTERM, up to 30 s, then SIGKILL."""
    comfy, vram = shlex.quote(COMFY_PATTERN), shlex.quote(VRAM_PATTERN)
    return (f"pkill -f {comfy}; pkill -f {vram}; for i in $(seq 30); do pgrep -f {comfy} > /dev/null || break; "
            f"sleep 1; done; pkill -9 -f {comfy}; echo stopped")


def compiler_word(off: bool) -> str:
    return "off" if off else "on"


def ensure_key(key: Path, say: Callable[[str], None]) -> None:
    """Create the SSH route's key (ed25519, no passphrase) when it is missing; never touches another file."""
    if key.is_file():
        return
    key.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "colab-vidgen", "-f", str(key)],
                       check=True, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError as exc:
        raise SetupError(f"no SSH key at {key} and no ssh-keygen to create it (install OpenSSH's client), "
                         "or use --via exec") from exc
    except subprocess.CalledProcessError as exc:
        raise SetupError(f"ssh-keygen could not create {key}: {_last_line(exc.stderr or exc.stdout or '')}") from exc
    say(f"## created the SSH key {key} (no passphrase; colab ssh sends its public half to the VM)")


class Colab(_Colab):
    """vidgen.colab.Colab plus the probe of vm_state.py and the SSH route's check and detached starts."""

    def probe(self) -> dict:
        """Run vm_state.py on the VM and return its JSON; retries a dropped exec."""
        return self.exec_json(TOOLS_DIR / "vm_state.py", {}, STATE_PREFIX)

    def check_ssh(self) -> None:
        """Open the SSH master and run one command; a failure stops the setup (no fallback to exec)."""
        try:
            result = self.link.call(SSH_CHECK, 120)
            why = "" if result.returncode == 0 and "vidgen-ssh-ok" in result.output else _last_line(result.output)
        except SetupError as exc:
            why = str(exc)
        if why:
            raise SetupError(f"SSH to session {self.session} does not work ({why}). To use the old colab exec "
                             f"route instead: python tools/colab/setup_session.py {shown(self.session)} --via exec")
        self.say(f"## SSH to {self.session} works")

    def stop_comfy(self) -> None:
        """Stop the VM's ComfyUI and VRAM sampler over ssh; raises when the shell did not finish."""
        result = self.link.call(comfy_stop_command(), 60)
        if result.returncode != 0 or "stopped" not in result.output:
            raise SetupError(f"could not stop ComfyUI over ssh on {self.session}: {_last_line(result.output)}")

    def start_detached(self, command: str, what: str) -> None:
        """Run a ``setsid nohup ... &`` command over ssh; raises when the shell did not start it."""
        result = self.link.call(command, 60)
        if result.returncode != 0 or "started" not in result.output:
            raise SetupError(f"could not start {what} over ssh on {self.session}: {_last_line(result.output)}")


def ensure_session(colab: Colab, gpu: str, attempts: int = 4, pause_seconds: float = 60.0,
                   high_mem: bool = False) -> tuple[bool, str]:
    """Reuse the session if listed, else `colab new` (retried); returns (created, hardware)."""
    listed = colab.sessions()
    if colab.session in listed:
        return False, listed[colab.session]
    reason = ""
    for attempt in range(1, attempts + 1):
        shape = f"{gpu}, high-RAM" if high_mem and gpu not in SINGLE_SHAPE else gpu
        colab.say(f"## creating session {colab.session} ({shape}), try {attempt}/{attempts} (8 s to 3 min)")
        result = colab.create(gpu, high_mem=high_mem)
        listed = colab.sessions()
        if colab.session in listed:
            colab.say(f"## session {colab.session} created ({listed[colab.session]}); billing has started")
            return True, listed[colab.session]
        reason = _last_line(result.output)
        if "Service Unavailable" in result.output or "503" in result.output:
            reason = f"no {gpu} capacity right now (HTTP 503)"
        if attempt < attempts:
            colab.say(f"   not created: {reason}; trying again in {pause_seconds:.0f} s")
            colab.sleep(pause_seconds)
    raise SetupError(f"could not create session {colab.session} after {attempts} tries: {reason}")


@dataclass
class Report:
    """What the run did, for the final summary."""

    created: bool = False
    hardware: str = ""
    outcomes: dict[str, str] = field(default_factory=dict)
    models: dict[str, list[str] | None] = field(default_factory=dict)
    compiler_off: bool | None = None


def _log_tail(state: dict, log_name: str) -> str:
    log = state["logs"].get(log_name, {})
    if not log.get("exists"):
        return f"(no /content/{log_name})"
    return f"last lines of /content/{log_name}:\n" + "\n".join("   " + line for line in log["tail"])


class SessionSetup:
    """The steps after the session exists: probe, start what is missing, wait, start ComfyUI."""

    def __init__(self, colab: Colab, pin: bool, clock: Callable[[], float] = time.monotonic,
                 poll_seconds: float = 30.0, setup_limit_seconds: float = 45 * 60,
                 comfy_poll_seconds: float = 10.0, comfy_limit_seconds: float = 10 * 60,
                 no_compiler: bool = False) -> None:
        self.colab = colab
        self.pin = pin
        self.no_compiler = no_compiler
        self.clock = clock
        self.poll_seconds = poll_seconds
        self.setup_limit_seconds = setup_limit_seconds
        self.comfy_poll_seconds = comfy_poll_seconds
        self.comfy_limit_seconds = comfy_limit_seconds
        self.printed: set[str] = set()

    def run(self, parts: list[str], report: Report, meanwhile: Callable[[], None] | None = None) -> None:
        """Set up ``parts``; ``meanwhile`` (if given) runs once ComfyUI has been started, before waiting for it."""
        state = self.colab.probe()
        status = {part: part_status(state["parts"][part]) for part in parts}
        for part in parts:
            if status[part] == "marker":
                report.outcomes[part] = "reused (marker)"
            elif status[part] == "found":
                report.outcomes[part] = "reused (all files present, no marker)"
        to_start = [part for part in parts if status[part] == "todo"]
        if to_start:
            self.colab.say("## uploading " + ", ".join(UPLOADS))
            self.colab.upload_many([(TOOLS_DIR / name, f"/content/{name}") for name in UPLOADS])
            for part in to_start:
                state = self.start_part(part)
        waiting = [part for part in parts if status[part] in ("todo", "running")]
        if waiting:
            for part in waiting:
                if status[part] == "running":
                    self.colab.say(f"## {PART_TITLES[part]}: already running, waiting for it")
            state = self.wait_for_parts(waiting, report, started=set(to_start))
        state = self.ensure_comfy(state, report, meanwhile, new_nodes="ltx" in to_start)
        report.models = state["comfy"].get("models") or {}

    def start_part(self, part: str) -> dict:
        """Start setup.sh / setup_image.sh detached and check on the VM that it runs."""
        script = PART_SCRIPTS[part]
        if self.colab.via == "ssh":
            self.colab.say(f"## starting {script} ({PART_TITLES[part]})")
            self.colab.start_detached(setup_command(script, {"PIN": "1" if self.pin else "0"}), script)
            state = self.colab.probe()
            if part_status(state["parts"][part]) == "todo":
                raise SetupError(f"{script} stopped right after it started; " + _log_tail(state, PART_LOGS[part][0]))
            return state
        env = {"SCRIPT": f"/content/{script}", "PIN": "1" if self.pin else "0"}
        for attempt in range(1, self.colab.attempts + 1):
            self.colab.say(f"## starting {script} ({PART_TITLES[part]})")
            self.colab.exec_file(TOOLS_DIR / "start_setup.py", env)
            state = self.colab.probe()
            if part_status(state["parts"][part]) != "todo":
                return state
            self.colab.pause_before_retry(f"{script} is not running on the VM", attempt)
        raise SetupError(f"{script} did not start; " + _log_tail(state, PART_LOGS[part][0]))

    def print_milestones(self, state: dict, parts: list[str]) -> None:
        for part in parts:
            for log_name in PART_LOGS[part]:
                for line in state["logs"].get(log_name, {}).get("milestones", []):
                    if line not in self.printed:
                        self.printed.add(line)
                        self.colab.say(f"   {log_name}: {line}")

    def probe_while_waiting(self) -> dict | None:
        """A probe whose failure is not fatal: the VM's work goes on while the connection drops."""
        try:
            return self.colab.probe()
        except SetupError as exc:
            self.colab.say(f"   {exc}; still waiting")
            return None

    def wait_for_parts(self, parts: list[str], report: Report, started: set[str]) -> dict:
        """Poll until every part has its marker; fail with the log tail when a script stops early."""
        begin = self.clock()
        pending = list(parts)
        while True:
            state = self.probe_while_waiting()
            if state is not None:
                self.print_milestones(state, parts)
                for part in list(pending):
                    status = part_status(state["parts"][part])
                    if status in ("marker", "found"):
                        pending.remove(part)
                        verb = "installed" if part in started else "finished (was running)"
                        report.outcomes[part] = f"{verb} in {format_seconds(self.clock() - begin)}"
                    elif status == "todo":
                        raise SetupError(f"{PART_SCRIPTS[part]} stopped before it finished; "
                                         + _log_tail(state, PART_LOGS[part][0]))
                if not pending:
                    return state
            if self.clock() - begin > self.setup_limit_seconds:
                raise SetupError(f"setup not done after {format_seconds(self.setup_limit_seconds)}: "
                                 + ", ".join(PART_SCRIPTS[p] for p in pending) + " still running")
            self.colab.sleep(self.poll_seconds)

    def restart_reason(self, state: dict, new_nodes: bool, report: Report) -> str:
        """Why a running ComfyUI must restart ("" when it need not or cannot: only over ssh); sets
        ``report.compiler_off`` to the running one's setting."""
        comfy = state["comfy"]
        off = comfy_compiler_off(self.colab) if comfy["up"] or comfy["running"] else None
        report.compiler_off = self.no_compiler if off is None else off
        reason = ""
        if off is not None and off != self.no_compiler:
            reason = (f"it runs with the model compiler {compiler_word(off)}, "
                      f"{compiler_word(self.no_compiler)} was asked for")
        elif off is not None and new_nodes:
            reason = "setup.sh ran while it was running (new nodes load at start)"
        if reason and self.colab.via != "ssh":
            self.colab.say(f"   note: ComfyUI is not restarted on the exec route, but {reason}; "
                           "restart it by hand (HOWTO) or use the SSH route")
            return ""
        return reason

    def ensure_comfy(self, state: dict, report: Report, meanwhile: Callable[[], None] | None = None,
                     new_nodes: bool = False) -> dict:
        """Start ComfyUI unless it answers or is starting (over ssh: restart it when its compiler
        setting differs or ``new_nodes`` were installed while it ran), then wait until it answers."""
        comfy = state["comfy"]
        reason = self.restart_reason(state, new_nodes, report)
        if comfy["up"] and not reason:
            report.outcomes["comfy"] = "reused (already answering)"
            return state
        begin = self.clock()
        verb = "was starting; answers"
        if reason:
            verb = f"restarted (model compiler {compiler_word(self.no_compiler)}); answers"
            self.colab.say(f"## restarting ComfyUI: {reason}")
            self.colab.stop_comfy()
            self.colab.start_detached(comfy_command(self.no_compiler), "ComfyUI")
            report.compiler_off = self.no_compiler
            state = self.colab.probe()
            if not (state["comfy"]["up"] or state["comfy"]["running"]):
                raise SetupError("ComfyUI stopped right after its restart; " + _log_tail(state, "comfy.log"))
        elif not comfy["running"] and self.colab.via == "ssh":
            verb = "started; answers"
            self.colab.say("## starting ComfyUI (setsid nohup python main.py)")
            self.colab.start_detached(comfy_command(self.no_compiler), "ComfyUI")
            state = self.colab.probe()
            if not (state["comfy"]["up"] or state["comfy"]["running"]):
                raise SetupError("ComfyUI stopped right after it started; " + _log_tail(state, "comfy.log"))
        elif not comfy["running"]:
            verb = "started; answers"
            for attempt in range(1, self.colab.attempts + 1):
                self.colab.say("## starting ComfyUI (start_comfy.py)")
                self.colab.exec_file(TOOLS_DIR / "start_comfy.py")
                state = self.colab.probe()
                if state["comfy"]["up"] or state["comfy"]["running"]:
                    break
                self.colab.pause_before_retry("ComfyUI is not running on the VM", attempt)
            else:
                raise SetupError("ComfyUI did not start; " + _log_tail(state, "comfy.log"))
        if meanwhile is not None:
            meanwhile()
        self.colab.say("## waiting for ComfyUI on 127.0.0.1:8188 (VM)")
        last: dict = state
        while not last["comfy"]["up"]:
            if not last["comfy"]["running"]:
                raise SetupError("ComfyUI stopped while starting; " + _log_tail(last, "comfy.log"))
            if self.clock() - begin > self.comfy_limit_seconds:
                raise SetupError(f"ComfyUI not answering after {format_seconds(self.comfy_limit_seconds)}; "
                                 + _log_tail(last, "comfy.log"))
            self.colab.sleep(self.comfy_poll_seconds)
            last = self.probe_while_waiting() or last
        report.outcomes["comfy"] = f"{verb} after {format_seconds(self.clock() - begin)}"
        return last


def ensure_cloudflared(colab: Colab, report: Report) -> None:
    """Install cloudflared on the VM (the pinned linux-amd64 release) unless it is there: files
    come back from the VM through its quick tunnel."""
    for attempt in range(1, 4):
        try:
            reply = colab.vm("cloudflared")
            break
        except SetupError as exc:
            if attempt == 3:
                raise
            colab.say(f"   cloudflared install on the VM failed ({exc}); trying again")
    report.outcomes["cloudflared"] = f"{'installed' if reply['installed'] else 'reused'} ({reply['version']})"


class VidgenSetup:
    """The vidgen part: upload this checkout's source and install it unless the VM has its hash."""

    def __init__(self, colab: Colab, clock: Callable[[], float] = time.monotonic, repo: Path = REPO,
                 poll_seconds: float = 20.0, limit_seconds: float = 40 * 60) -> None:
        self.colab = colab
        self.clock = clock
        self.repo = repo
        self.poll_seconds = poll_seconds
        self.limit_seconds = limit_seconds
        self.printed: set[str] = set()
        self.code = ""
        self.started_at: float | None = None

    def state(self) -> dict:
        return self.colab.vm("state", VIDGEN_PROJECT="")["vidgen"]

    def begin(self, report: Report) -> None:
        """Start the install unless the VM has this code (then the outcome is set); safe to call once."""
        self.code = package_hash(self.repo / "src" / "vidgen")
        state = self.state()
        if state["hash"] == self.code:
            report.outcomes["vidgen"] = f"reused (marker, code {self.code})"
            return
        self.started_at = self.clock()
        if state["setup_running"]:
            self.colab.say(f"## {VIDGEN_TITLE}: a setup is already running, waiting for it")
        else:
            self.start(self.code)

    def run(self, report: Report) -> None:
        """Install vidgen (or finish the install :meth:`begin` started) and wait for its marker."""
        if not self.code:
            self.begin(report)
        if self.started_at is None:
            return
        self.wait(self.code)
        report.outcomes["vidgen"] = f"installed code {self.code} in {format_seconds(self.clock() - self.started_at)}"

    def start(self, code: str) -> None:
        self.colab.say(f"## uploading vidgen's source (code {code}) and {VIDGEN_SCRIPT}")
        with tempfile.TemporaryDirectory() as tmp:
            archive = source_archive(self.repo, Path(tmp) / "vidgen-src.tar.gz")
            self.colab.upload_many([(archive, VM_SOURCE_ARCHIVE), (TOOLS_DIR / VIDGEN_SCRIPT, f"/content/{VIDGEN_SCRIPT}")])
        if self.colab.via == "ssh":
            self.colab.say(f"## starting {VIDGEN_SCRIPT} ({VIDGEN_TITLE})")
            self.colab.start_detached(setup_command(VIDGEN_SCRIPT, {"PIN": "1", "VIDGEN_HASH": code}), VIDGEN_SCRIPT)
            return
        env = {"SCRIPT": f"/content/{VIDGEN_SCRIPT}", "PIN": "1", "VIDGEN_HASH": code}
        for attempt in range(1, self.colab.attempts + 1):
            self.colab.say(f"## starting {VIDGEN_SCRIPT} ({VIDGEN_TITLE})")
            self.colab.exec_file(TOOLS_DIR / "start_setup.py", env)
            state = self.state()
            if state["setup_running"] or state["hash"] == code:
                return
            self.colab.pause_before_retry(f"{VIDGEN_SCRIPT} is not running on the VM", attempt)
        raise SetupError(f"{VIDGEN_SCRIPT} did not start; " + _vidgen_tail(state))

    def wait(self, code: str) -> dict:
        """Poll until the marker holds `code`; fail with the log tail when the script stops first."""
        begin = self.clock()
        while True:
            try:
                state = self.state()
            except SetupError as exc:
                self.colab.say(f"   {exc}; still waiting")
            else:
                for line in state["log"]["milestones"]:
                    if line not in self.printed:
                        self.printed.add(line)
                        self.colab.say(f"   setup_vidgen.log: {line}")
                if state["hash"] == code:
                    return state
                if not state["setup_running"]:
                    if state["hash"]:
                        raise SetupError(f"another setup installed code {state['hash']}, not {code}; run this again")
                    raise SetupError(f"{VIDGEN_SCRIPT} stopped before it finished; " + _vidgen_tail(state))
            if self.clock() - begin > self.limit_seconds:
                raise SetupError(f"{VIDGEN_SCRIPT} not done after {format_seconds(self.limit_seconds)}")
            self.colab.sleep(self.poll_seconds)


def _vidgen_tail(state: dict) -> str:
    log = state["log"]
    if not log["exists"]:
        return "(no /content/setup_vidgen.log)"
    return "last lines of /content/setup_vidgen.log:\n" + "\n".join("   " + line for line in log["tail"])


def summary_lines(session: str, gpu: str, report: Report, parts: list[str], elapsed_seconds: float,
                  vidgen: bool = True, via: str = "ssh") -> list[str]:
    """The final summary: session, GPU, what was installed or reused, time, the next commands."""
    name = shown(session)
    lines = [f"== session {session} is ready ({format_seconds(elapsed_seconds)})",
             f"   session:    {session} ({report.hardware or gpu}, {'created' if report.created else 'reused'})",
             f"   cloudflared (VM, for transfers): {report.outcomes.get('cloudflared', '?')}"]
    if parts:
        for part in PART_SCRIPTS:
            outcome = report.outcomes.get(part, "?") if part in parts else "skipped (--no-image)"
            lines.append(f"   {PART_TITLES[part]}: {outcome}")
        compiler = "?" if report.compiler_off is None else compiler_word(report.compiler_off)
        lines.append(f"   ComfyUI:    {report.outcomes.get('comfy', '?')} on 127.0.0.1:8188 (VM), "
                     f"model compiler {compiler}" + (f" ({NO_COMPILER_FLAG})" if report.compiler_off else ""))
        if report.models:
            listed = ", ".join(f"{folder} {len(names)}" for folder, names in report.models.items() if names)
            lines.append(f"   models ComfyUI lists: {listed}")
            listed_lora = "ComfyUI lists it" if INGREDIENTS_LORA in (report.models.get("loras") or []) else "NOT listed"
            lines.append(f"   base video + sheet: loras/{INGREDIENTS_LORA} ({listed_lora}); node {ROUTING_NODE} "
                         f"(LTX Multi IC-LoRA, class {ROUTING_CLASS}), both installed by the LTX part")
    lines.append(f"   {VIDGEN_TITLE}: {report.outcomes.get('vidgen', '?') if vidgen else 'skipped (--no-vidgen)'}")
    lines.append("next:")
    if vidgen:
        lines.append(f"   in a project folder: vidgen remote {name} render")
    if parts and via == "ssh":
        lines.append(f"   LTX shots (provider: comfyui, colab: {name}): vidgen remote {name} generate run --pay")
    elif parts:
        lines += [f"   or go on with {HOWTO} section 6.3, e.g.",
                  f"   colab upload -s {name} ltx-inputs/render_121_960x512.mp4 /content/render_121_960x512.mp4"]
    lines.append(f"stop it when you are done (an idle L4 still bills about 1.94 units/h): colab stop -s {name}")
    return lines


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="setup_session.py",
        description="Find or create a Colab GPU session and set it up: ComfyUI, LTX-2.3 and image models "
                    "(the LTX-2.3 HOWTO), and this checkout's vidgen (vidgen remote). Never stops the session.")
    parser.add_argument("session", help="Colab session name (reused when `colab sessions` lists it)")
    parser.add_argument("--gpu", default="L4", choices=HARDWARE,
                        help="GPU for a new session (default L4); CPU: no GPU, only with --vidgen-only")
    parser.add_argument("--high-mem", action="store_true",
                        help="high-RAM machine shape for a new session (colab new --high-mem; ignored on L4)")
    parser.add_argument("--no-image", action="store_true",
                        help="skip the image models (Qwen-Image-Edit, Z-Image; about 50 GB)")
    parser.add_argument("--latest", action="store_true",
                        help="latest ComfyUI and node commits instead of the tested ones (setup.sh PIN=0)")
    parser.add_argument("--no-comfy-compiler", action="store_true",
                        help=f"start ComfyUI with {NO_COMPILER_FLAG} (for LTX Multi IC-LoRA); over SSH a running "
                             "ComfyUI with the other setting is restarted (without this option: compiler on)")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--no-vidgen", action="store_true", help="skip installing vidgen (this checkout's code)")
    which.add_argument("--vidgen-only", action="store_true",
                       help="only install vidgen (for vidgen remote): no ComfyUI, LTX-2.3 or image models")
    parser.add_argument("--colab", default="colab", help="the colab CLI command (default: colab)")
    via_arg(parser)
    args = parser.parse_args(argv)
    if not args.session.strip() or args.session.startswith("-"):
        parser.error("the session name must not be empty or start with '-'")
    if args.gpu == "CPU" and not args.vidgen_only:
        parser.error("a CPU session has no GPU for ComfyUI and LTX-2.3: add --vidgen-only")
    if args.no_comfy_compiler and (args.vidgen_only or args.via == "exec"):
        parser.error("--no-comfy-compiler needs ComfyUI over the SSH route: leave out --vidgen-only and --via exec")
    return args


def main(argv: list[str] | None = None, runner: Runner = run_command,
         sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
         say: Callable[[str], None] = say_now, transfer_factory: Callable[[Colab], Transfers] | None = None,
         ssh_factory: Callable[[Colab], SshLink] | None = None) -> int:
    """Set up the session; returns the exit code (0 ready, 1 failed, 130 interrupted)."""
    args = parse_args(argv)
    colab = Colab(args.session, cli=args.colab, runner=runner, sleep=sleep, say=say, transfer_factory=transfer_factory,
                  via=args.via, ssh_factory=ssh_factory)
    polls = POLLS[args.via]
    parts = [] if args.vidgen_only else ["ltx"] if args.no_image else ["ltx", "image"]
    report = Report()
    begin = clock()
    session_exists = False
    if args.high_mem and args.gpu in SINGLE_SHAPE:
        say(f"   note: --high-mem is ignored on {args.gpu} (one machine shape)")
    try:
        if args.via == "ssh":
            ensure_key(colab_ssh.KEY, say)
        report.created, report.hardware = ensure_session(colab, args.gpu, high_mem=args.high_mem)
        session_exists = True
        if not report.created:
            say(f"## reusing session {args.session} ({report.hardware})")
            if report.hardware != args.gpu:
                say(f"   note: it has a {report.hardware}; --gpu only applies to a new session")
        if args.via == "ssh":
            colab.check_ssh()
        ensure_cloudflared(colab, report)
        vidgen = None if args.no_vidgen else VidgenSetup(colab, clock=clock, poll_seconds=polls["vidgen"])
        if parts:
            # Over ssh vidgen's install starts while ComfyUI loads (setup.sh's pip installs are over by then).
            early = (lambda: vidgen.begin(report)) if vidgen and args.via == "ssh" else None
            SessionSetup(colab, pin=not args.latest, clock=clock, poll_seconds=polls["setup"],
                         comfy_poll_seconds=polls["comfy"], no_compiler=args.no_comfy_compiler,
                         ).run(parts, report, meanwhile=early)
        if vidgen:
            vidgen.run(report)
    except (SetupError, KeyboardInterrupt) as exc:
        say(f"error: {exc}" if isinstance(exc, SetupError) else "interrupted")
        if not session_exists:
            say("check `colab sessions`: a session may still have been created")
        else:
            say(f"session {args.session} is still running (this script never stops it); "
                f"run this again to resume, or stop it: colab stop -s {shown(args.session)}")
        return 1 if isinstance(exc, SetupError) else 130
    finally:
        colab.close()
    for line in summary_lines(args.session, args.gpu, report, parts, clock() - begin, vidgen=not args.no_vidgen,
                              via=args.via):
        say(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
