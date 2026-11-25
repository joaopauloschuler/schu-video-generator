"""tools/colab/setup_session.py and vm_state.py with a fake `colab` CLI (no network, no VM)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

COLAB_DIR = Path(__file__).resolve().parents[1] / "tools" / "colab"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"colab_{name}", COLAB_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


setup_session = _load("setup_session")
vm_state = _load("vm_state")

LOCAL_HASH = "c0de"
SESSION_LINE = "[{name}] gpu-l4-s-abc | Hardware: L4 | Shape: Standard | Variant: GPU"


def _part(marker: bool = False, missing: bool = True, running: bool = False) -> dict:
    return {"marker": marker, "missing": ["/content/ComfyUI/main.py"] if missing else [], "running": running}


class FakeVM:
    """A Colab VM as vm_state.py reports it: a started script finishes after `polls_to_finish` probes."""

    def __init__(self, ltx: dict | None = None, image: dict | None = None, comfy_up: bool = False,
                 polls_to_finish: int = 1, fail: str | None = None, vidgen_hash: str | None = LOCAL_HASH,
                 compiler_off: bool = False) -> None:
        self.parts = {"ltx": ltx or _part(), "image": image or _part()}
        self.vidgen = {"hash": vidgen_hash, "setup_running": False,
                       "log": {"exists": True, "milestones": ["### vidgen step"], "tail": ["vidgen last line"]}}
        self.vidgen_polls = 0
        self.done: set[str] = set()
        self.comfy = {"up": comfy_up, "running": comfy_up, "dir": True,
                      "models": {"unet_gguf": ["a.gguf"]} if comfy_up else {}}
        #: The running ComfyUI's arguments after main.py (colab_vm.py's state), None when none runs.
        self.comfy_args = self.args_for(compiler_off) if comfy_up else None
        self.polls_to_finish = polls_to_finish
        self.fail = fail
        self.countdown: dict[str, int] = {}

    @staticmethod
    def args_for(compiler_off: bool) -> list[str]:
        return setup_session.COMFY_COMMAND[2:] + ([setup_session.NO_COMPILER_FLAG] if compiler_off else [])

    def start_comfy(self, command: str) -> None:
        self.comfy["running"] = True
        self.comfy_args = self.args_for(setup_session.NO_COMPILER_FLAG in command)

    def stop_comfy(self) -> None:
        self.comfy.update(up=False, running=False, models={})
        self.comfy_args = None

    def start(self, part: str) -> None:
        self.parts[part]["running"] = True
        self.countdown[part] = self.polls_to_finish

    def state_json(self) -> str:
        for part, left in list(self.countdown.items()):
            if left == 0:
                self.parts[part]["running"] = False
                if part != self.fail:
                    self.parts[part].update(marker=True, missing=[])
                del self.countdown[part]
            else:
                self.countdown[part] = left - 1
        if self.comfy["running"] and not self.comfy["up"]:
            self.comfy.update(up=True, models={"unet_gguf": ["a.gguf"],
                                               "loras": ["l.safetensors", setup_session.INGREDIENTS_LORA]})
        logs = {name: {"exists": True, "milestones": [f"### {name} step"], "tail": [f"{name} last line"]}
                for name in vm_state.LOGS}
        return setup_session.STATE_PREFIX + json.dumps({"parts": self.parts, "comfy": self.comfy, "logs": logs})


class FakeColabCLI:
    """Answers the argument lists setup_session.py runs, and records them."""

    def __init__(self, vm: FakeVM, sessions: list[str] | None = None, new_results: list[str] | None = None,
                 dropped_probes: set[int] | None = None) -> None:
        self.vm = vm
        self.sessions = list(sessions or [])
        self.new_results = list(new_results or ["Session READY"])
        self.dropped_probes = dropped_probes or set()
        self.probes = 0
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], timeout_seconds: float) -> setup_session.CommandResult:
        self.calls.append(args)
        command = args[1]
        if command == "sessions":
            text = "\n".join(SESSION_LINE.format(name=n) for n in self.sessions) or "No active sessions found on server."
            return setup_session.CommandResult(0, text)
        if command == "new":
            result = self.new_results.pop(0)
            if "READY" in result:
                self.sessions.append(args[args.index("-s") + 1])
            return setup_session.CommandResult(0 if "READY" in result else 1, result)
        if command == "exec":
            script = Path(args[args.index("-f") + 1]).name
            if script == "vm_state.py":
                self.probes += 1
                if self.probes in self.dropped_probes:
                    return setup_session.CommandResult(1, "RuntimeError: Connection was lost.")
                return setup_session.CommandResult(0, self.vm.state_json())
            env = dict(a.split("=", 1) for a in args if "=" in a)
            if script == "colab_vm.py" and env["VIDGEN_ACTION"] == "cloudflared":
                reply = {"version": "cloudflared version 2026.10.7", "installed": "cloudflared" not in self.vm.done}
                self.vm.done.add("cloudflared")
                return setup_session.CommandResult(0, "VIDGEN_VM " + json.dumps(reply))
            if script == "colab_vm.py":
                assert env["VIDGEN_ACTION"] == "state"
                vidgen = self.vm.vidgen
                if vidgen["setup_running"]:
                    self.vm.vidgen_polls += 1
                    if self.vm.vidgen_polls > 1:
                        vidgen["setup_running"] = False
                        vidgen["hash"] = None if self.vm.fail == "vidgen" else vidgen["pending"]
                reply = {"vidgen": vidgen, "comfy": {"args": self.vm.comfy_args}}
                return setup_session.CommandResult(0, "VIDGEN_VM " + json.dumps(reply))
            if script == "start_setup.py":
                if env["SCRIPT"].endswith("setup_vidgen.sh"):
                    self.vm.vidgen.update(setup_running=True, pending=env["VIDGEN_HASH"])
                else:
                    self.vm.start("image" if env["SCRIPT"].endswith("setup_image.sh") else "ltx")
                return setup_session.CommandResult(0, "started")
            if script == "start_comfy.py":
                self.vm.start_comfy("")
                return setup_session.CommandResult(0, "comfy pid 1")
        raise AssertionError(f"unexpected call {args}")

    def upload(self, pairs: list[tuple[Path, str]]) -> None:
        self.calls += [["colab", "upload", str(local), remote] for local, remote in pairs]

    def close(self) -> None:
        pass

    def commands(self) -> list[str]:
        return [" ".join(c[1:2] + ([Path(c[c.index("-f") + 1]).name] if "-f" in c else [])) for c in self.calls]


@pytest.fixture(autouse=True)
def _cheap_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No hashing or packing of the real 45 MB package in these tests."""
    monkeypatch.setattr(setup_session, "package_hash", lambda package_dir=None: LOCAL_HASH)

    def archive(repo: Path, dest: Path) -> Path:
        dest.write_bytes(b"tar")
        return dest

    monkeypatch.setattr(setup_session, "source_archive", archive)


def _run(cli: FakeColabCLI, argv: list[str]) -> tuple[int, list[str]]:
    lines: list[str] = []
    clock = iter(range(0, 100000, 5))
    code = setup_session.main([*argv, "--via", "exec"], runner=cli, sleep=lambda s: None, clock=lambda: next(clock), say=lines.append,
                              transfer_factory=lambda colab: cli)  # type: ignore[arg-type, return-value]
    return code, lines


def test_parse_args_defaults_and_flags() -> None:
    args = setup_session.parse_args(["ltx-2"])
    assert (args.session, args.gpu, args.no_image, args.latest, args.via) == ("ltx-2", "L4", False, False, "ssh")
    args = setup_session.parse_args(["x", "--gpu", "G4", "--no-image", "--latest", "--via", "exec"])
    assert (args.gpu, args.no_image, args.latest, args.via) == ("G4", True, True, "exec")
    with pytest.raises(SystemExit):
        setup_session.parse_args(["x", "--gpu", "L5"])
    with pytest.raises(SystemExit):
        setup_session.parse_args(["--", "-bad"])
    with pytest.raises(SystemExit):
        setup_session.parse_args(["x", "--via", "scp"])


def test_parse_sessions_and_state() -> None:
    text = SESSION_LINE.format(name="ltx") + "\n[my run] gpu-t4-x | Hardware: T4 | Shape: Standard\n"
    assert setup_session.parse_sessions(text) == {"ltx": "L4", "my run": "T4"}
    assert setup_session.parse_sessions("No active sessions found on server.") == {}
    assert setup_session.parse_state('noise\nVIDGEN_STATE {"a": 1}\n') == {"a": 1}
    assert setup_session.parse_state("RuntimeError: Connection was lost.") is None


def test_part_status_order() -> None:
    assert setup_session.part_status(_part(marker=True, running=True, missing=False)) == "marker"
    assert setup_session.part_status(_part(marker=True, running=True)) == "running"   # an older setup, files added since
    assert setup_session.part_status(_part(marker=True)) == "todo"
    assert setup_session.part_status(_part(running=True, missing=False)) == "running"
    assert setup_session.part_status(_part(missing=False)) == "found"
    assert setup_session.part_status(_part()) == "todo"


def test_exec_args_pass_the_name_as_one_argument() -> None:
    colab = setup_session.Colab("two words; rm -rf")
    args = colab.exec_args(Path("start_setup.py"), {"SCRIPT": "/content/setup.sh", "PIN": "1"})
    assert args == ["exec", "-s", "two words; rm -rf", "--timeout", "20", "--env", "SCRIPT=/content/setup.sh",
                    "--env", "PIN=1", "-f", "start_setup.py"]


def test_existing_ready_session_is_all_skipped() -> None:
    vm = FakeVM(ltx=_part(missing=False), image=_part(marker=True, missing=False), comfy_up=True)
    cli = FakeColabCLI(vm, sessions=["ltx"])
    code, lines = _run(cli, ["ltx"])
    assert code == 0
    assert cli.commands() == ["sessions", "exec colab_vm.py", "exec vm_state.py", "exec colab_vm.py", "exec colab_vm.py"]
    text = "\n".join(lines)
    assert "cloudflared (VM, for transfers): installed (cloudflared version 2026.10.7)" in text
    assert "reused (marker, code c0de)" in text and "vidgen remote ltx render" in text
    assert "reused (all files present, no marker)" in text and "reused (marker)" in text
    assert "reused (already answering)" in text and "colab stop -s ltx" in text


def test_new_session_retries_503_then_installs_everything() -> None:
    vm = FakeVM(polls_to_finish=2)
    cli = FakeColabCLI(vm, new_results=["ColabRequestError ... accelerator=L4: Service Unavailable", "Session READY"])
    code, lines = _run(cli, ["fresh", "--latest"])
    assert code == 0
    commands = cli.commands()
    assert commands.count("new") == 2
    assert commands.count("upload") == len(setup_session.UPLOADS)
    assert commands.count("exec start_setup.py") == 2 and commands.count("exec start_comfy.py") == 1
    starts = [c for c in cli.calls if "start_setup.py" in c[-1]]
    assert all("PIN=0" in c for c in starts)
    assert ["new", "-s", "fresh", "--gpu", "L4"] == cli.calls[1][1:]
    text = "\n".join(lines)
    assert "HTTP 503" in text and "created" in text and "installed in" in text
    assert "setup.log: ### setup.log step" in text and text.count("### setup.log step") == 1


def test_create_gives_up_after_the_tries() -> None:
    cli = FakeColabCLI(FakeVM(), new_results=["Service Unavailable"] * 4)
    code, lines = _run(cli, ["fresh"])
    assert code == 1 and cli.commands().count("new") == 4
    assert "could not create session fresh" in "\n".join(lines)


def test_no_image_and_running_part_is_waited_for_not_restarted() -> None:
    vm = FakeVM(ltx=_part(running=True))
    vm.countdown["ltx"] = 1
    cli = FakeColabCLI(vm, sessions=["s"])
    code, lines = _run(cli, ["s", "--no-image"])
    assert code == 0
    assert "exec start_setup.py" not in cli.commands() and "upload" not in cli.commands()
    assert "skipped (--no-image)" in "\n".join(lines)


def test_dropped_first_exec_is_retried() -> None:
    vm = FakeVM(ltx=_part(marker=True, missing=False), image=_part(marker=True, missing=False), comfy_up=True)
    cli = FakeColabCLI(vm, sessions=["s"], dropped_probes={1, 2})
    code, _ = _run(cli, ["s"])
    assert code == 0 and cli.commands().count("exec vm_state.py") == 3


def test_a_probe_that_keeps_failing_while_waiting_does_not_stop_the_wait() -> None:
    vm = FakeVM(ltx=_part(running=True), polls_to_finish=8)
    vm.countdown["ltx"] = 8
    cli = FakeColabCLI(vm, sessions=["s"], dropped_probes=set(range(2, 8)))
    code, lines = _run(cli, ["s", "--no-image"])
    assert code == 0 and "still waiting" in "\n".join(lines)


def test_failed_setup_shows_the_log_tail_and_never_stops_the_session() -> None:
    cli = FakeColabCLI(FakeVM(fail="ltx"), sessions=["s"])
    code, lines = _run(cli, ["s", "--no-image"])
    text = "\n".join(lines)
    assert code == 1
    assert "setup.sh stopped before it finished" in text and "setup.log last line" in text
    assert "colab stop -s s" in text and "stop" not in cli.commands()


def test_vm_state_reports_markers_files_and_processes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, proc = tmp_path / "content", tmp_path / "proc"
    models = root / "ComfyUI" / "models"
    for rel in vm_state.MODEL_FILES["ltx"]:
        (models / rel).parent.mkdir(parents=True, exist_ok=True)
        (models / rel).write_bytes(b"x")
    (root / "ComfyUI" / "main.py").write_text("x", encoding="utf-8")
    for node in vm_state.CUSTOM_NODES:
        (root / "ComfyUI" / "custom_nodes" / node).mkdir(parents=True)
        (root / "ComfyUI" / "custom_nodes" / node / "__init__.py").write_text("x", encoding="utf-8")
    (root / vm_state.MARKERS["image"]).write_text("", encoding="utf-8")
    (proc / "42").mkdir(parents=True)
    (proc / "42" / "cmdline").write_bytes(b"bash\0/content/setup_image.sh\0")
    (root / "setup.log").write_text("+ x\n### 10:00 +1s SETUP DONE\nlast\n", encoding="utf-8")
    monkeypatch.setattr(vm_state, "comfy_get", lambda path, timeout=3.0: None)
    state = vm_state.state(root, proc)
    assert state["parts"]["ltx"] == {"marker": False, "missing": [], "running": False}
    assert state["parts"]["image"]["marker"] and state["parts"]["image"]["running"]
    assert len(state["parts"]["image"]["missing"]) == len(vm_state.MODEL_FILES["image"])
    assert state["comfy"]["up"] is False and state["comfy"]["dir"] is True
    assert state["logs"]["setup.log"]["milestones"] == ["### 10:00 +1s SETUP DONE"]
    assert state["logs"]["comfy.log"]["exists"] is False


def test_vidgen_only_installs_this_code_and_skips_the_models() -> None:
    cli = FakeColabCLI(FakeVM(vidgen_hash="old1"), sessions=["s"])
    code, lines = _run(cli, ["s", "--vidgen-only"])
    assert code == 0
    assert "exec vm_state.py" not in cli.commands()
    uploads = [c[-1] for c in cli.calls if c[1] == "upload"]
    assert uploads == ["/content/vidgen-src.tar.gz", "/content/setup_vidgen.sh"]
    start = next(c for c in cli.calls if "start_setup.py" in c[-1])
    assert "VIDGEN_HASH=c0de" in start and "SCRIPT=/content/setup_vidgen.sh" in start
    text = "\n".join(lines)
    assert "installed code c0de" in text and "setup_vidgen.log: ### vidgen step" in text
    assert "ComfyUI" not in text


def test_no_vidgen_skips_it_and_a_failed_vidgen_setup_shows_its_log() -> None:
    vm = FakeVM(ltx=_part(marker=True, missing=False), image=_part(marker=True, missing=False),
                comfy_up=True, vidgen_hash=None)
    cli = FakeColabCLI(vm, sessions=["s"])
    code, lines = _run(cli, ["s", "--no-vidgen"])
    assert code == 0 and cli.commands().count("exec colab_vm.py") == 2 and "skipped (--no-vidgen)" in "\n".join(lines)
    vm.fail = "vidgen"
    code, lines = _run(FakeColabCLI(vm, sessions=["s"]), ["s", "--vidgen-only"])
    text = "\n".join(lines)
    assert code == 1 and "setup_vidgen.sh stopped before it finished" in text and "vidgen last line" in text
    with pytest.raises(SystemExit):
        setup_session.parse_args(["s", "--no-vidgen", "--vidgen-only"])


class FakeLink:
    """The SSH route's link for setup_session.py: scripts go to the fake CLI as if by exec, shell commands are recorded."""

    def __init__(self, cli: FakeColabCLI, check_ok: bool = True) -> None:
        self.cli = cli
        self.check_ok = check_ok
        self.commands: list[str] = []

    def script(self, script: Path, env: dict[str, str]) -> setup_session.CommandResult:
        args = ["colab", "exec", "-s", "s"]
        for key, value in env.items():
            args += ["--env", f"{key}={value}"]
        return self.cli([*args, "-f", str(script)], 60)

    def call(self, command: str, timeout_seconds: float, stdin: object = None, stdout: object = None) -> setup_session.CommandResult:
        self.commands.append(command)
        if command == setup_session.SSH_CHECK:
            if not self.check_ok:
                raise setup_session.SetupError("cannot open an SSH connection to s: Connection closed by UNKNOWN port 65535")
            return setup_session.CommandResult(0, "vidgen-ssh-ok")
        if command == setup_session.comfy_stop_command():
            self.cli.vm.stop_comfy()
            return setup_session.CommandResult(0, "stopped")
        assert "setsid nohup" in command and command.rstrip().endswith("echo started $!"), command
        if "setup_vidgen.sh" in command:
            code = command.split("VIDGEN_HASH=")[1].split()[0].strip("'")
            self.cli.vm.vidgen.update(setup_running=True, pending=code)
        elif "main.py" in command:
            self.cli.vm.start_comfy(command)
        else:
            self.cli.vm.start("image" if "setup_image.sh" in command else "ltx")
        return setup_session.CommandResult(0, "started 123")

    def upload(self, pairs: list[tuple[Path, str]]) -> None:
        self.cli.upload(pairs)

    def close(self) -> None:
        pass


def _run_ssh(cli: FakeColabCLI, argv: list[str], link: FakeLink | None = None) -> tuple[int, list[str], FakeLink]:
    lines: list[str] = []
    link = link or FakeLink(cli)
    clock = iter(range(0, 100000, 5))
    code = setup_session.main(argv, runner=cli, sleep=lambda s: None, clock=lambda: next(clock), say=lines.append,
                              ssh_factory=lambda colab: link)  # type: ignore[arg-type, return-value]
    return code, lines, link


def _have_key() -> None:
    key = setup_session.colab_ssh.KEY
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text("key", encoding="utf-8")


def test_ssh_route_starts_everything_with_nohup_and_vidgen_while_comfy_loads() -> None:
    _have_key()
    vm = FakeVM(polls_to_finish=2, vidgen_hash="old1")
    cli = FakeColabCLI(vm)
    code, lines, link = _run_ssh(cli, ["fresh"])
    text = "\n".join(lines)
    assert code == 0, text
    assert "exec start_setup.py" not in cli.commands() and "exec start_comfy.py" not in cli.commands()
    assert link.commands[0] == setup_session.SSH_CHECK
    starts = link.commands[1:]
    assert ["setup.sh" in c for c in starts] == [True, False, False, False]
    assert "setup_image.sh" in starts[1] and "main.py" in starts[2] and "setup_vidgen.sh" in starts[3]
    assert starts[0] == ("cd /content || exit 3; env -- PIN=1 setsid nohup bash /content/setup.sh > /content/setup.log "
                         "2>&1 < /dev/null & echo started $!")
    assert "nvidia-smi" in starts[2] and ">> /content/comfy.log" in starts[2]
    assert text.index("starting setup_vidgen.sh") < text.index("waiting for ComfyUI")
    assert "## SSH to fresh works" in text and "installed code c0de" in text
    assert "vidgen remote fresh generate run --pay" in text and "colab upload" not in text
    assert not any(c[1] == "exec" and "start_setup.py" in c[-1] for c in cli.calls)


def test_ssh_route_creates_a_missing_key_with_ssh_keygen(monkeypatch: pytest.MonkeyPatch) -> None:
    key = setup_session.colab_ssh.KEY
    ran: list[list[str]] = []

    def keygen(args: list[str], **kwargs: object) -> object:
        ran.append(args)
        Path(args[-1]).write_text("key", encoding="utf-8")
        return setup_session.subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(setup_session.subprocess, "run", keygen)
    vm = FakeVM(ltx=_part(marker=True, missing=False), image=_part(marker=True, missing=False), comfy_up=True)
    code, lines, _ = _run_ssh(FakeColabCLI(vm, sessions=["s"]), ["s"])
    assert code == 0 and key.is_file()
    assert ran == [["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "colab-vidgen", "-f", str(key)]]
    assert sum("created the SSH key" in line for line in lines) == 1
    ran.clear()
    _run_ssh(FakeColabCLI(vm, sessions=["s"]), ["s"])
    assert ran == []   # an existing key is left alone


def test_ssh_check_failure_stops_and_names_via_exec() -> None:
    _have_key()
    cli = FakeColabCLI(FakeVM(), sessions=["s"])
    code, lines, link = _run_ssh(cli, ["s"], FakeLink(cli, check_ok=False))
    text = "\n".join(lines)
    assert code == 1
    assert "SSH to session s does not work" in text and "setup_session.py s --via exec" in text
    assert link.commands == [setup_session.SSH_CHECK]
    assert [c[1] for c in cli.calls] == ["sessions"]   # nothing ran on the VM after the failed check, no fallback


def test_exec_route_keeps_start_setup_and_never_uses_ssh() -> None:
    vm = FakeVM(ltx=_part(), image=_part(marker=True, missing=False))
    cli = FakeColabCLI(vm, sessions=["s"])
    lines: list[str] = []
    clock = iter(range(0, 100000, 5))
    code = setup_session.main(["s", "--via", "exec"], runner=cli, sleep=lambda s: None, clock=lambda: next(clock),
                              say=lines.append, transfer_factory=lambda colab: cli,  # type: ignore[arg-type, return-value]
                              ssh_factory=lambda colab: pytest.fail("no ssh on the exec route"))  # type: ignore[arg-type, return-value]
    assert code == 0
    assert cli.commands().count("exec start_setup.py") == 1 and cli.commands().count("exec start_comfy.py") == 1
    assert not setup_session.colab_ssh.KEY.exists()   # no key made on the exec route
    assert "colab upload -s s" in "\n".join(lines)


def test_high_mem_cpu_session_with_vidgen_only_makes_no_gpu_or_model_calls() -> None:
    _have_key()
    cli = FakeColabCLI(FakeVM(vidgen_hash="old1"))
    code, lines, link = _run_ssh(cli, ["cpu", "--gpu", "CPU", "--high-mem", "--vidgen-only"])
    text = "\n".join(lines)
    assert code == 0, text
    assert ["new", "-s", "cpu", "--high-mem"] == cli.calls[1][1:]
    assert "(CPU, high-RAM)" in text and "ignored" not in text
    assert "exec vm_state.py" not in cli.commands() and "ComfyUI" not in text
    assert not any("nvidia-smi" in c or "main.py" in c or "setup.sh" in c.split("/")[-1] for c in link.commands)
    assert any("setup_vidgen.sh" in c for c in link.commands) and "installed code c0de" in text


def test_high_mem_on_l4_is_passed_on_with_one_ignored_line_and_cpu_needs_vidgen_only() -> None:
    _have_key()
    cli = FakeColabCLI(FakeVM(polls_to_finish=1, vidgen_hash="old1"))
    code, lines, _ = _run_ssh(cli, ["fresh", "--high-mem"])
    text = "\n".join(lines)
    assert code == 0, text
    assert ["new", "-s", "fresh", "--gpu", "L4", "--high-mem"] == cli.calls[1][1:]
    assert text.count("--high-mem is ignored on L4") == 1
    with pytest.raises(SystemExit):
        setup_session.parse_args(["s", "--gpu", "CPU"])
    assert setup_session.parse_args(["s", "--gpu", "CPU", "--vidgen-only"]).high_mem is False


def _comfy_starts(link: FakeLink) -> list[str]:
    return [c for c in link.commands if "main.py" in c or c == setup_session.comfy_stop_command()]


def test_no_comfy_compiler_starts_comfyui_with_the_flag_and_the_summary_says_off() -> None:
    _have_key()
    cli = FakeColabCLI(FakeVM(polls_to_finish=1, vidgen_hash="old1"))
    code, lines, link = _run_ssh(cli, ["fresh", "--no-comfy-compiler"])
    text = "\n".join(lines)
    assert code == 0, text
    [start] = _comfy_starts(link)
    assert "python main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch --disable-comfy-compiler >>" in start
    assert "model compiler off (--disable-comfy-compiler)" in text and "restarting" not in text
    assert f"loras/{setup_session.INGREDIENTS_LORA} (ComfyUI lists it); node comfyui-hrnodes" in text
    assert "class LTXMultiICLoRA" in text


def test_rerun_switches_a_running_comfyui_compiler_both_ways_and_reuses_a_matching_one() -> None:
    _have_key()
    done = {"ltx": _part(marker=True, missing=False), "image": _part(marker=True, missing=False)}
    vm = FakeVM(**done, comfy_up=True)
    code, lines, link = _run_ssh(FakeColabCLI(vm, sessions=["s"]), ["s", "--no-comfy-compiler"])
    text = "\n".join(lines)
    assert code == 0, text
    stop, start = _comfy_starts(link)
    assert stop == setup_session.comfy_stop_command() and "--disable-comfy-compiler" in start
    assert "## restarting ComfyUI: it runs with the model compiler on, off was asked for" in text
    assert "restarted (model compiler off); answers" in text and "model compiler off (" in text
    code, lines, link = _run_ssh(FakeColabCLI(vm, sessions=["s"]), ["s", "--no-comfy-compiler"])
    assert code == 0 and _comfy_starts(link) == [] and "reused (already answering)" in "\n".join(lines)
    code, lines, link = _run_ssh(FakeColabCLI(vm, sessions=["s"]), ["s"])
    text = "\n".join(lines)
    stop, start = _comfy_starts(link)
    assert code == 0 and "--disable-comfy-compiler" not in start
    assert "it runs with the model compiler off, on was asked for" in text and "(VM), model compiler on" in text
    assert vm.comfy_args == setup_session.COMFY_COMMAND[2:]


def test_marker_from_an_older_setup_reruns_setup_sh_and_restarts_comfyui() -> None:
    _have_key()
    vm = FakeVM(ltx=_part(marker=True), image=_part(marker=True, missing=False), comfy_up=True)
    code, lines, link = _run_ssh(FakeColabCLI(vm, sessions=["s"]), ["s", "--no-image"])
    text = "\n".join(lines)
    assert code == 0, text
    assert any("bash /content/setup.sh" in c for c in link.commands)
    assert "## restarting ComfyUI: setup.sh ran while it was running" in text
    assert [c == setup_session.comfy_stop_command() for c in _comfy_starts(link)] == [True, False]


def test_exec_route_reports_the_compiler_but_never_restarts_and_rejects_the_option() -> None:
    vm = FakeVM(ltx=_part(marker=True, missing=False), image=_part(marker=True, missing=False), comfy_up=True,
                compiler_off=True)
    code, lines = _run(FakeColabCLI(vm, sessions=["s"]), ["s"])
    text = "\n".join(lines)
    assert code == 0 and "note: ComfyUI is not restarted on the exec route" in text
    assert "reused (already answering) on 127.0.0.1:8188 (VM), model compiler off" in text
    for argv in (["s", "--no-comfy-compiler", "--via", "exec"], ["s", "--no-comfy-compiler", "--vidgen-only"]):
        with pytest.raises(SystemExit):
            setup_session.parse_args(argv)
    assert setup_session.parse_args(["s", "--no-comfy-compiler"]).no_comfy_compiler is True


def test_vm_state_needs_the_ingredients_lora_and_the_routing_node() -> None:
    assert f"loras/{setup_session.INGREDIENTS_LORA}" in vm_state.MODEL_FILES["ltx"]
    assert setup_session.ROUTING_NODE in vm_state.CUSTOM_NODES
    setup_sh = (COLAB_DIR / "setup.sh").read_text(encoding="utf-8")
    assert "hashu786/comfyui-hrnodes" in setup_sh and "comfyui-hrnodes checkout -q 1f91974824c7e4e1" in setup_sh
    assert f"dl Comfy-Org/ltx-2.3 split_files/loras/{setup_session.INGREDIENTS_LORA}" in setup_sh
