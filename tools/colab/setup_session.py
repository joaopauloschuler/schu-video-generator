"""Find or create a Google Colab GPU session and set it up for docs/HOWTO-restyle-with-ltx-on-colab.md.

    python tools/colab/setup_session.py NAME [--gpu L4] [--no-image] [--latest] [--no-vidgen | --vidgen-only]

Runs on your machine (standard library only, Windows too) and drives the `colab` CLI: it reuses the
session NAME when `colab sessions` lists it (else `colab new`, retried on 503), then installs
ComfyUI + the LTX-2.3 weights (setup.sh) and the image models (setup_image.sh), starts ComfyUI, and
installs this checkout's vidgen (setup_vidgen.sh), skipping each part that is already done; first
it installs cloudflared on the VM (files go both ways through quick tunnels). It never stops the
session. See README.md here.
"""
from __future__ import annotations

import argparse
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
    VM_SOURCE_ARCHIVE, Colab as _Colab, ColabError as SetupError, CommandResult, Runner, format_seconds,
    last_line as _last_line, package_hash, parse_prefixed_json, parse_sessions, run_command, say_now, shown,
    source_archive, via_arg,
)
from vidgen.colab_transfer import Transfers  # noqa: E402

__all__ = ["CommandResult", "Runner", "SetupError", "format_seconds", "parse_sessions", "run_command", "say_now", "shown"]

STATE_PREFIX = "VIDGEN_STATE "
GPUS = ("T4", "L4", "G4", "H100", "A100")
UPLOADS = ("vm_state.py", "setup.sh", "setup_image.sh")
PART_SCRIPTS = {"ltx": "setup.sh", "image": "setup_image.sh"}
PART_LOGS = {"ltx": ("setup.log", "download.log"), "image": ("setup_image.log",)}
PART_TITLES = {"ltx": "ComfyUI + LTX-2.3 weights", "image": "image models (Qwen-Image-Edit, Z-Image)"}
VIDGEN_TITLE = "vidgen (this computer's code)"
VIDGEN_SCRIPT = "setup_vidgen.sh"
HOWTO = "docs/HOWTO-restyle-with-ltx-on-colab.md"


def parse_state(text: str) -> dict | None:
    """The JSON that vm_state.py printed, or None when the line is missing (the exec dropped)."""
    return parse_prefixed_json(text, STATE_PREFIX)


def part_status(part: dict) -> str:
    """`marker` / `found` (files there, no marker) / `running` / `todo` for one part of vm_state's JSON."""
    if part["marker"]:
        return "marker"
    if part["running"]:
        return "running"
    if not part["missing"]:
        return "found"
    return "todo"


class Colab(_Colab):
    """vidgen.colab.Colab plus the probe of vm_state.py."""

    def probe(self) -> dict:
        """Run vm_state.py on the VM and return its JSON; retries a dropped exec."""
        return self.exec_json(TOOLS_DIR / "vm_state.py", {}, STATE_PREFIX)


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
            self.colab.upload_many([(TOOLS_DIR / name, f"/content/{name}") for name in UPLOADS])
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

    def state(self) -> dict:
        return self.colab.vm("state", VIDGEN_PROJECT="")["vidgen"]

    def run(self, report: Report) -> None:
        code = package_hash(self.repo / "src" / "vidgen")
        state = self.state()
        if state["hash"] == code:
            report.outcomes["vidgen"] = f"reused (marker, code {code})"
            return
        begin = self.clock()
        if state["setup_running"]:
            self.colab.say(f"## {VIDGEN_TITLE}: a setup is already running, waiting for it")
        else:
            self.start(code)
        self.wait(code)
        report.outcomes["vidgen"] = f"installed code {code} in {format_seconds(self.clock() - begin)}"

    def start(self, code: str) -> None:
        self.colab.say(f"## uploading vidgen's source (code {code}) and {VIDGEN_SCRIPT}")
        with tempfile.TemporaryDirectory() as tmp:
            archive = source_archive(self.repo, Path(tmp) / "vidgen-src.tar.gz")
            self.colab.upload_many([(archive, VM_SOURCE_ARCHIVE), (TOOLS_DIR / VIDGEN_SCRIPT, f"/content/{VIDGEN_SCRIPT}")])
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
                  vidgen: bool = True) -> list[str]:
    """The final summary: session, GPU, what was installed or reused, time, the next commands."""
    name = shown(session)
    lines = [f"== session {session} is ready ({format_seconds(elapsed_seconds)})",
             f"   session:    {session} ({report.hardware or gpu}, {'created' if report.created else 'reused'})",
             f"   cloudflared (VM, for transfers): {report.outcomes.get('cloudflared', '?')}"]
    if parts:
        for part in PART_SCRIPTS:
            outcome = report.outcomes.get(part, "?") if part in parts else "skipped (--no-image)"
            lines.append(f"   {PART_TITLES[part]}: {outcome}")
        lines.append(f"   ComfyUI:    {report.outcomes.get('comfy', '?')} on 127.0.0.1:8188 (VM)")
        if report.models:
            listed = ", ".join(f"{folder} {len(names)}" for folder, names in report.models.items() if names)
            lines.append(f"   models ComfyUI lists: {listed}")
    lines.append(f"   {VIDGEN_TITLE}: {report.outcomes.get('vidgen', '?') if vidgen else 'skipped (--no-vidgen)'}")
    lines.append("next:")
    if vidgen:
        lines.append(f"   in a project folder: vidgen remote {name} render")
    if parts:
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
    parser.add_argument("--gpu", default="L4", choices=GPUS, help="GPU for a new session (default L4)")
    parser.add_argument("--no-image", action="store_true",
                        help="skip the image models (Qwen-Image-Edit, Z-Image; about 50 GB)")
    parser.add_argument("--latest", action="store_true",
                        help="latest ComfyUI and node commits instead of the tested ones (setup.sh PIN=0)")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--no-vidgen", action="store_true", help="skip installing vidgen (this checkout's code)")
    which.add_argument("--vidgen-only", action="store_true",
                       help="only install vidgen (for vidgen remote): no ComfyUI, LTX-2.3 or image models")
    parser.add_argument("--colab", default="colab", help="the colab CLI command (default: colab)")
    via_arg(parser)
    args = parser.parse_args(argv)
    if not args.session.strip() or args.session.startswith("-"):
        parser.error("the session name must not be empty or start with '-'")
    return args


def main(argv: list[str] | None = None, runner: Runner = run_command,
         sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
         say: Callable[[str], None] = say_now, transfer_factory: Callable[[Colab], Transfers] | None = None) -> int:
    """Set up the session; returns the exit code (0 ready, 1 failed, 130 interrupted)."""
    args = parse_args(argv)
    colab = Colab(args.session, cli=args.colab, runner=runner, sleep=sleep, say=say, transfer_factory=transfer_factory,
                  via=args.via)
    parts = [] if args.vidgen_only else ["ltx"] if args.no_image else ["ltx", "image"]
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
        ensure_cloudflared(colab, report)
        if parts:
            SessionSetup(colab, pin=not args.latest, clock=clock).run(parts, report)
        if not args.no_vidgen:
            VidgenSetup(colab, clock=clock).run(report)
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
    for line in summary_lines(args.session, args.gpu, report, parts, clock() - begin, vidgen=not args.no_vidgen):
        say(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
