"""The SSH route of vidgen.colab.Colab (vidgen.colab_ssh), with ssh mocked: no network."""

from __future__ import annotations

import hashlib
import shlex
import subprocess
from pathlib import Path

import pytest

from vidgen import colab_ssh
from vidgen.colab import VM_PREFIX, Colab, ColabError, CommandResult
from vidgen.colab_ssh import SOCKET_PATH_MAX, SshLink, env_words, script_command


class FakeSsh:
    """Records every ssh call; ``-O check`` answers ``master`` (True: running), commands pop ``answers``."""

    def __init__(self, master: bool = True, answers: list[CommandResult] | None = None) -> None:
        self.calls: list[tuple[list[str], float, Path | bytes | None, Path | None]] = []
        self.master = master
        self.answers = answers or []

    def __call__(self, args: list[str], timeout: float, stdin: Path | bytes | None, stdout: Path | None) -> CommandResult:
        self.calls.append((args, timeout, stdin, stdout))
        if "-O" in args:
            verb = args[args.index("-O") + 1]
            if verb == "exit":
                self.master = False
            return CommandResult(0 if self.master or verb == "exit" else 255, "")
        if "-N" in args:
            self.master = True
            return CommandResult(0, "")
        return self.answers.pop(0) if self.answers else CommandResult(0, "")

    def commands(self) -> list[str]:
        """Each call's remote command, or ``-O verb`` / ``master``."""
        named = []
        for args, *_ in self.calls:
            named.append(f"-O {args[args.index('-O') + 1]}" if "-O" in args else "master" if "-N" in args else args[-1])
        return named


def _colab(tmp_path: Path, fake: FakeSsh, **kwargs: object) -> Colab:
    key = tmp_path / "key"
    key.write_text("k", encoding="utf-8")
    sessions = kwargs.pop("sessions", {"s418": "CPU"})
    return Colab("s418", lock_dir=tmp_path / "locks", say=lambda line: None, sleep=lambda s: None,
                 ssh_factory=lambda c: SshLink(c.session, runner=fake, key=key, socket_dir=tmp_path / "ssh",
                                               listed=lambda: sessions, say=c.say, multiplex=True), **kwargs)


def test_ssh_is_the_default_and_a_bad_route_is_refused(tmp_path: Path) -> None:
    assert Colab("x").via == "ssh"
    with pytest.raises(AssertionError, match="a test ran real ssh"):   # conftest's guard
        SshLink("x", key=Path(__file__)).call("true", 5)
    with pytest.raises(ColabError, match="unknown Colab route"):
        Colab("x", via="tunnel")


def test_the_command_line_uses_only_its_key_and_host_file(tmp_path: Path) -> None:
    link = SshLink("my session", cli="/opt/colab", key=tmp_path / "k", socket_dir=tmp_path / "ssh")
    args = link.ssh("root@colab", "true")
    assert args[:3] == ["ssh", "-F", __import__("os").devnull] and args[3:5] == ["-i", str(tmp_path / "k")]
    options = dict(args[i + 1].split("=", 1) for i, a in enumerate(args) if a == "-o")
    assert shlex.split(options["ProxyCommand"]) == ["/opt/colab", "ssh", "--proxy-mode", "-s", "my session",
                                                    "-i", str(tmp_path / "k")]
    assert options["StrictHostKeyChecking"] == "accept-new" and options["IdentitiesOnly"] == "yes"
    assert Path(options["UserKnownHostsFile"]).parent == tmp_path / "ssh"
    assert ".ssh/known_hosts" not in " ".join(args) and options["BatchMode"] == "yes"


def test_the_control_path_is_short(tmp_path: Path) -> None:
    real = Path.home() / ".cache" / "vidgen" / "ssh"   # the default (tests point SOCKET_DIR elsewhere)
    link = SshLink("a" * 300, socket_dir=real)
    assert len(str(link.control_path)) <= SOCKET_PATH_MAX and link.control_path.parent == real
    deep = SshLink("x", socket_dir=tmp_path / ("d" * 120))
    assert len(str(deep.control_path)) <= SOCKET_PATH_MAX   # falls back to the temporary folder
    assert SshLink("x").control_path != SshLink("y").control_path


def test_env_is_quoted_against_the_shell() -> None:
    env = {"VIDGEN_ARGS": '["render", "it\'s; rm -rf /"]', "EMPTY": "", "LINE": "a\nb $(id)"}
    command = script_command(env)
    words = shlex.split(command)
    assert words[:3] == ["cd", "/content", "&&"] and words[-2:] == ["python3", "-"]
    assert words[3:5] == ["env", "--"]
    assert dict(w.split("=", 1) for w in words[5:-2]) == env
    with pytest.raises(ColabError, match="not an environment variable name"):
        env_words({"A;B": "1"})


def test_the_quoted_env_reaches_python_unchanged(tmp_path: Path) -> None:
    env = {"V": "it's \"x\" $(echo no) `no`; *"}
    done = subprocess.run(["sh", "-c", script_command(env).replace("cd /content", f"cd {shlex.quote(str(tmp_path))}")],
                          input=b"import os; print(os.environ['V'])", capture_output=True, check=True, timeout=30)
    assert done.stdout.decode("utf-8").strip() == env["V"]


def test_a_missing_key_says_how_to_create_it(tmp_path: Path) -> None:
    fake = FakeSsh()
    colab = Colab("s418", lock_dir=tmp_path, ssh_factory=lambda c: SshLink(c.session, runner=fake, key=tmp_path / "none",
                                                        socket_dir=tmp_path / "ssh"))
    with pytest.raises(ColabError, match=r"ssh-keygen -t ed25519 -N \"\" -f .*none"):
        colab.exec_file(Path(__file__))
    assert fake.calls == []


def test_vm_runs_the_script_over_ssh_with_its_env_on_one_master(tmp_path: Path) -> None:
    fake = FakeSsh(master=False, answers=[CommandResult(0, VM_PREFIX + '{"ok": 1}\n')] * 2)
    with _colab(tmp_path, fake) as colab:
        assert colab.vm("state", VIDGEN_PROJECT="/content/projects/a b") == {"ok": 1}
        assert colab.vm("state") == {"ok": 1}
    assert fake.commands()[:3] == ["-O check", "master", "-O check"]
    assert fake.commands()[-1] == "-O exit"   # this object opened the master: close() ends it
    runs = [c for c in fake.calls if "python3 -" in c[0][-1]]
    assert len(runs) == 2 and "ControlMaster=no" in runs[0][0]
    assert runs[0][2] == colab_ssh_vm_script() and runs[0][1] == colab_ssh.SCRIPT_SECONDS
    assert "VIDGEN_ACTION=state" in runs[0][0][-1] and "'VIDGEN_PROJECT=/content/projects/a b'" in runs[0][0][-1]
    assert not (tmp_path / "locks").exists() or not list((tmp_path / "locks").glob("*.lock"))   # no lock


def colab_ssh_vm_script() -> bytes:
    from vidgen.colab import VM_SCRIPT

    return VM_SCRIPT.read_bytes()


def test_a_running_master_is_reused_and_not_closed(tmp_path: Path) -> None:
    fake = FakeSsh(master=True)
    with _colab(tmp_path, fake) as colab:
        colab.exec_file(Path(__file__))
    assert fake.commands()[0] == "-O check" and "master" not in fake.commands() and "-O exit" not in fake.commands()


def test_a_dropped_connection_reconnects_once(tmp_path: Path) -> None:
    fake = FakeSsh(answers=[CommandResult(255, "Connection closed"), CommandResult(0, "fine")])
    colab = _colab(tmp_path, fake)
    assert colab.exec_file(Path(__file__)).output == "fine"
    assert fake.commands()[2:5] == ["-O exit", "master", "-O check"]
    fake.answers = [CommandResult(255, "down"), CommandResult(255, "still down")]
    assert colab.exec_file(Path(__file__)).returncode == 255   # only once: exec_json's retries go on from there


def test_no_master_when_the_session_is_not_listed(tmp_path: Path) -> None:
    fake = FakeSsh(master=False)
    with pytest.raises(ColabError, match="no Colab session 's418'"):
        _colab(tmp_path, fake, sessions={}).exec_file(Path(__file__))
    assert "master" not in fake.commands()


def test_upload_and_download_check_sha256(tmp_path: Path) -> None:
    data = b"x" * 5000
    (tmp_path / "a.bin").write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()

    class Vm(FakeSsh):
        def __call__(self, args, timeout, stdin, stdout):   # type: ignore[no-untyped-def, override]
            result = super().__call__(args, timeout, stdin, stdout)
            command = args[-1]
            if command.startswith("stat "):
                return CommandResult(0, f"{len(data)}\n{sha}  /content/a.bin\n")
            if command.startswith("cat /content") and stdout is not None:
                stdout.write_bytes(self.body)
            return result

    fake = Vm()
    fake.body = data   # type: ignore[attr-defined]
    colab = _colab(tmp_path, fake)
    colab.upload(tmp_path / "a.bin", "/content/in dir/a.bin")
    up = fake.calls[-1]
    assert up[2] == tmp_path / "a.bin" and sha in up[0][-1] and "'/content/in dir/a.bin.vidgen-part'" in up[0][-1]
    colab.download("/content/a.bin", tmp_path / "out" / "a.bin")
    assert (tmp_path / "out" / "a.bin").read_bytes() == data
    fake.body = b"broken"   # type: ignore[attr-defined]
    with pytest.raises(ColabError, match="SHA-256 differs"):
        colab.download("/content/a.bin", tmp_path / "out" / "b.bin")
    assert not (tmp_path / "out" / "b.bin").exists() and not (tmp_path / "out" / "b.bin.part").exists()
    fake.answers = [CommandResult(3, "SHA-256 differs on the VM")]
    with pytest.raises(ColabError, match="could not upload a.bin"):
        colab.upload(tmp_path / "a.bin", "/content/a.bin")


def test_exec_route_is_the_old_colab_exec_with_its_lock(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    seen_lock: list[bool] = []
    colab = Colab("s418", via="exec", lock_dir=tmp_path, say=lambda line: None, sleep=lambda s: None,
                  ssh_factory=lambda c: pytest.fail("no ssh on the exec route"),  # type: ignore[arg-type, return-value]
                  runner=lambda a, t: (calls.append(a), seen_lock.append(colab.lock_path.exists()),
                                       CommandResult(0, VM_PREFIX + "{}"))[-1])
    assert colab.vm("state") == {} and colab.prestart_env().keys() == {"VIDGEN_SECRET"}
    assert calls[0][:2] == ["colab", "exec"] and seen_lock == [True]
    colab.close()
    assert Colab("x").prestart_env() == {}
