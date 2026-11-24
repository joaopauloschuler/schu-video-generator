"""Find or create a Google Colab GPU session and set it up for docs/HOWTO-restyle-with-ltx-on-colab.md.

    python tools/colab/setup_session.py NAME [--gpu L4] [--no-image] [--latest]

Runs on your machine (standard library only, Windows too) and drives the `colab` CLI: it reuses the
session NAME when `colab sessions` lists it (else `colab new`, retried on 503), then installs
ComfyUI + the LTX-2.3 weights (setup.sh) and the image models (setup_image.sh) and starts ComfyUI,
skipping each part that is already done. It never stops the session. See README.md here.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

TOOLS_DIR = Path(__file__).resolve().parent
STATE_PREFIX = "VIDGEN_STATE "
GPUS = ("T4", "L4", "G4", "H100", "A100")
UPLOADS = ("vm_state.py", "setup.sh", "setup_image.sh")
PART_SCRIPTS = {"ltx": "setup.sh", "image": "setup_image.sh"}
PART_LOGS = {"ltx": ("setup.log", "download.log"), "image": ("setup_image.log",)}
PART_TITLES = {"ltx": "ComfyUI + LTX-2.3 weights", "image": "image models (Qwen-Image-Edit, Z-Image)"}
HOWTO = "docs/HOWTO-restyle-with-ltx-on-colab.md"


@dataclass(frozen=True)
class CommandResult:
    """Exit code and combined stdout + stderr of one `colab` call."""

    returncode: int
    output: str


Runner = Callable[[list[str], float], CommandResult]


def say_now(line: str) -> None:
    """Print a progress line at once, also when stdout is a pipe."""
    print(line, flush=True)


class SetupError(Exception):
    """A setup step failed; the message says which and shows the VM's log tail when there is one."""


def run_command(args: list[str], timeout_seconds: float) -> CommandResult:
    """Run one command and return its exit code and output (124 when it timed out)."""
    try:
        # check=False: the caller retries dropped calls, and `colab exec` exits 0 even when the code fails.
        done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout_seconds, check=False)
    except FileNotFoundError as exc:
        raise SetupError(f"{args[0]!r} not found: install and log in to the colab CLI (google-colab-cli)") from exc
    except subprocess.TimeoutExpired as exc:
        partial = "".join(_text(part) for part in (exc.stdout, exc.stderr))
        return CommandResult(124, f"{partial}\n(timed out after {timeout_seconds:.0f} s)")
    return CommandResult(done.returncode, done.stdout + done.stderr)


def _text(data: str | bytes | None) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return data or ""


def parse_sessions(text: str) -> dict[str, str]:
    """Session name -> hardware from `colab sessions` lines like `[ltx] gpu-l4-... | Hardware: L4 | ...`."""
    sessions = {}
    for line in text.splitlines():
        match = re.match(r"\s*\[(?P<name>[^\]]+)\]\s+\S+\s*\|\s*Hardware:\s*(?P<hardware>[^|]+?)\s*(\||$)", line)
        if match:
            sessions[match["name"]] = match["hardware"]
    return sessions


def parse_state(text: str) -> dict | None:
    """The JSON that vm_state.py printed, or None when the line is missing (the exec dropped)."""
    for line in text.splitlines():
        if line.startswith(STATE_PREFIX):
            try:
                return json.loads(line[len(STATE_PREFIX):])
            except ValueError:
                return None
    return None


def part_status(part: dict) -> str:
    """`marker` / `found` (files there, no marker) / `running` / `todo` for one part of vm_state's JSON."""
    if part["marker"]:
        return "marker"
    if part["running"]:
        return "running"
    if not part["missing"]:
        return "found"
    return "todo"


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "(no output)"


def format_seconds(seconds: float) -> str:
    """`75` -> `1 min 15 s`."""
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


def shown(name: str) -> str:
    """The session name as typed in a printed command (quoted when it has spaces)."""
    return f'"{name}"' if re.search(r"\s", name) else name


@dataclass
class Colab:
    """The `colab` CLI for one session: every call is a list of arguments, one call at a time."""

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
        """The sessions `colab sessions` lists (name -> hardware)."""
        result = self.run(["sessions"], 90)
        if result.returncode != 0:
            raise SetupError(f"`colab sessions` failed: {_last_line(result.output)}")
        return parse_sessions(result.output)

    def create(self, gpu: str) -> CommandResult:
        return self.run(["new", "-s", self.session, "--gpu", gpu], 600)

    def exec_args(self, script: Path, env: dict[str, str]) -> list[str]:
        """Arguments of `colab exec` running a local file on the VM with `--env KEY=VALUE` pairs."""
        args = ["exec", "-s", self.session, "--timeout", "45"]
        for key, value in env.items():
            args += ["--env", f"{key}={value}"]
        return [*args, "-f", str(script)]

    def exec_file(self, script: Path, env: dict[str, str] | None = None) -> CommandResult:
        # These scripts answer in 5-15 s; a call that hangs (seen while connecting) is cut at 60 s and retried.
        return self.run(self.exec_args(script, env or {}), 60)

    def upload(self, local: Path, remote: str) -> None:
        """`colab upload`, retried when the transfer fails."""
        for attempt in range(1, self.attempts + 1):
            result = self.run(["upload", "-s", self.session, str(local), remote], 300)
            if result.returncode == 0 and "Traceback" not in result.output:
                return
            self.pause_before_retry(f"upload of {local.name} failed ({_last_line(result.output)})", attempt)
        raise SetupError(f"could not upload {local} to {remote}")

    def probe(self) -> dict:
        """Run vm_state.py on the VM and return its JSON; retries a dropped exec."""
        for attempt in range(1, self.attempts + 1):
            result = self.exec_file(TOOLS_DIR / "vm_state.py")
            state = parse_state(result.output)
            if state is not None:
                return state
            self.pause_before_retry(f"exec dropped ({_last_line(result.output)})", attempt)
        raise SetupError(f"`colab exec` on {self.session} kept failing; try `colab exec -s {shown(self.session)}` by hand")

    def pause_before_retry(self, what: str, attempt: int) -> None:
        """Say what failed and wait, unless `attempt` was the last one."""
        if attempt < self.attempts:
            self.say(f"   {what}; retry {attempt + 1}/{self.attempts} in {self.retry_pause:.0f} s")
            self.sleep(self.retry_pause)


def ensure_session(colab: Colab, gpu: str, attempts: int = 4, pause_seconds: float = 60.0) -> tuple[bool, str]:
    """Reuse the session if listed, else `colab new` (retried); returns (created, hardware)."""
    listed = colab.sessions()
    if colab.session in listed:
        return False, listed[colab.session]
    reason = ""
    for attempt in range(1, attempts + 1):
        colab.say(f"## creating session {colab.session} ({gpu}), try {attempt}/{attempts} (8 s to 3 min)")
        result = colab.create(gpu)
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


def _log_tail(state: dict, log_name: str) -> str:
    log = state["logs"].get(log_name, {})
    if not log.get("exists"):
        return f"(no /content/{log_name})"
    return f"last lines of /content/{log_name}:\n" + "\n".join("   " + line for line in log["tail"])


class SessionSetup:
    """The steps after the session exists: probe, start what is missing, wait, start ComfyUI."""

    def __init__(self, colab: Colab, pin: bool, clock: Callable[[], float] = time.monotonic,
                 poll_seconds: float = 30.0, setup_limit_seconds: float = 45 * 60,
                 comfy_poll_seconds: float = 10.0, comfy_limit_seconds: float = 10 * 60) -> None:
        self.colab = colab
        self.pin = pin
        self.clock = clock
        self.poll_seconds = poll_seconds
        self.setup_limit_seconds = setup_limit_seconds
        self.comfy_poll_seconds = comfy_poll_seconds
        self.comfy_limit_seconds = comfy_limit_seconds
        self.printed: set[str] = set()

    def run(self, parts: list[str], report: Report) -> None:
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
            for name in UPLOADS:
                self.colab.upload(TOOLS_DIR / name, f"/content/{name}")
            for part in to_start:
                state = self.start_part(part)
        waiting = [part for part in parts if status[part] in ("todo", "running")]
        if waiting:
            for part in waiting:
                if status[part] == "running":
                    self.colab.say(f"## {PART_TITLES[part]}: already running, waiting for it")
            state = self.wait_for_parts(waiting, report, started=set(to_start))
        state = self.ensure_comfy(state, report)
        report.models = state["comfy"].get("models") or {}

    def start_part(self, part: str) -> dict:
        """Start setup.sh / setup_image.sh detached and check on the VM that it runs."""
        script = PART_SCRIPTS[part]
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

    def ensure_comfy(self, state: dict, report: Report) -> dict:
        """Start ComfyUI unless it answers or is starting, then wait until it answers."""
        comfy = state["comfy"]
        if comfy["up"]:
            report.outcomes["comfy"] = "reused (already answering)"
            return state
        begin = self.clock()
        verb = "was starting; answers"
        if not comfy["running"]:
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


def summary_lines(session: str, gpu: str, report: Report, parts: list[str], elapsed_seconds: float) -> list[str]:
    """The final summary: session, GPU, what was installed or reused, time, the next commands."""
    name = shown(session)
    lines = [f"== session {session} is ready ({format_seconds(elapsed_seconds)})",
             f"   session:    {session} ({report.hardware or gpu}, {'created' if report.created else 'reused'})"]
    for part in PART_SCRIPTS:
        outcome = report.outcomes.get(part, "?") if part in parts else "skipped (--no-image)"
        lines.append(f"   {PART_TITLES[part]}: {outcome}")
    lines.append(f"   ComfyUI:    {report.outcomes.get('comfy', '?')} on 127.0.0.1:8188 (VM)")
    if report.models:
        listed = ", ".join(f"{folder} {len(names)}" for folder, names in report.models.items() if names)
        lines.append(f"   models ComfyUI lists: {listed}")
    lines += [f"next: upload your inputs and go on with {HOWTO} section 6.3, e.g.",
              f"   colab upload -s {name} ltx-inputs/render_121_960x512.mp4 /content/render_121_960x512.mp4",
              f"stop it when you are done (an idle L4 still bills about 1.94 units/h): colab stop -s {name}"]
    return lines


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="setup_session.py",
        description="Find or create a Colab GPU session and set it up for the LTX-2.3 HOWTO "
                    "(ComfyUI, LTX-2.3, image models). Never stops the session.")
    parser.add_argument("session", help="Colab session name (reused when `colab sessions` lists it)")
    parser.add_argument("--gpu", default="L4", choices=GPUS, help="GPU for a new session (default L4)")
    parser.add_argument("--no-image", action="store_true",
                        help="skip the image models (Qwen-Image-Edit, Z-Image; about 50 GB)")
    parser.add_argument("--latest", action="store_true",
                        help="latest ComfyUI and node commits instead of the tested ones (setup.sh PIN=0)")
    parser.add_argument("--colab", default="colab", help="the colab CLI command (default: colab)")
    args = parser.parse_args(argv)
    if not args.session.strip() or args.session.startswith("-"):
        parser.error("the session name must not be empty or start with '-'")
    return args


def main(argv: list[str] | None = None, runner: Runner = run_command,
         sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
         say: Callable[[str], None] = say_now) -> int:
    """Set up the session; returns the exit code (0 ready, 1 failed, 130 interrupted)."""
    args = parse_args(argv)
    colab = Colab(args.session, cli=args.colab, runner=runner, sleep=sleep, say=say)
    parts = ["ltx"] if args.no_image else ["ltx", "image"]
    report = Report()
    begin = clock()
    session_exists = False
    try:
        report.created, report.hardware = ensure_session(colab, args.gpu)
        session_exists = True
        if not report.created:
            say(f"## reusing session {args.session} ({report.hardware})")
            if report.hardware != args.gpu:
                say(f"   note: it has a {report.hardware}; --gpu only applies to a new session")
        SessionSetup(colab, pin=not args.latest, clock=clock).run(parts, report)
    except (SetupError, KeyboardInterrupt) as exc:
        say(f"error: {exc}" if isinstance(exc, SetupError) else "interrupted")
        if not session_exists:
            say("check `colab sessions`: a session may still have been created")
        else:
            say(f"session {args.session} is still running (this script never stops it); "
                f"run this again to resume, or stop it: colab stop -s {shown(args.session)}")
        return 1 if isinstance(exc, SetupError) else 130
    for line in summary_lines(args.session, args.gpu, report, parts, clock() - begin):
        say(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
