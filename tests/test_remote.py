"""vidgen remote (vidgen.remote, vidgen.colab, vidgen.colab_vm) with a fake `colab` CLI whose VM is a
folder: colab_vm.py's actions run for real there, and the "vidgen" it starts is a small script."""
from __future__ import annotations

import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from vidgen import colab_vm, remote
from vidgen.colab import Colab, ColabError, CommandResult, files_archive, package_hash, source_archive
from vidgen.errors import VidgenError

FAKE_VIDGEN = '''import json, pathlib, sys
print("[1/1] chase: rendering", file=sys.stderr, flush=True)
args = sys.argv[1:]
if "fail" in args:
    print("error: something broke", file=sys.stderr)
    sys.exit(3)
root = pathlib.Path.cwd().resolve()
(root / "output").mkdir(exist_ok=True)
(root / "output" / "v.mp4").write_bytes(b"mp4")
(root / "build" / "final").mkdir(parents=True, exist_ok=True)
(root / "build" / "final" / "timings.json").write_text("{}")
(root / "build" / "final" / "frames.json").write_text("{}")
(root / "audio").mkdir(exist_ok=True)
(root / "audio" / "new.mp3").write_bytes(b"mp3")
print(json.dumps({"ok": True, "args": args, "outputs": {
    "video": str(root / "output" / "v.mp4"), "timings": str(root / "build/final/timings.json"),
    "frames": str(root / "build/final/frames.json"), "thumbnail": None}}))
'''


class FakeColab:
    """`colab` for one VM folder: sessions and exec of colab_vm.py; also the transfers (copies)."""

    def __init__(self, vm: Path, vidgen_hash: str | None) -> None:
        self.vm = vm
        self.calls: list[list[str]] = []
        self.dropped = 0
        colab_vm.MARKER.parent.mkdir(parents=True, exist_ok=True)
        if vidgen_hash:
            colab_vm.MARKER.write_text(vidgen_hash, encoding="utf-8")

    def local(self, remote_path: str) -> Path:
        if remote_path.startswith(str(self.vm)):
            return Path(remote_path)
        return self.vm / remote_path.lstrip("/")

    def __call__(self, args: list[str], timeout_seconds: float) -> CommandResult:
        self.calls.append(args)
        command = args[1]
        if command == "sessions":
            return CommandResult(0, "[ltx] gpu-l4-x | Hardware: L4 | Shape: Standard")
        assert command == "exec" and Path(args[-1]).name == "colab_vm.py"
        if self.dropped:
            self.dropped -= 1
            return CommandResult(1, "RuntimeError: Connection was lost.")
        env = dict(a.split("=", 1) for a in args if "=" in a and a.startswith("VIDGEN_"))
        for key in ("VIDGEN_PROJECT", "VIDGEN_ARCHIVE"):
            if env.get(key):
                env[key] = str(self.local(env[key]))
        out = io.StringIO()
        with redirect_stdout(out):
            colab_vm.main(env)
        return CommandResult(0, out.getvalue())

    def upload(self, pairs: list[tuple[Path, str]]) -> None:
        for local, remote_path in pairs:
            self.calls.append(["colab", "upload", str(local), remote_path])
            target = self.local(remote_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local, target)

    def download(self, remote_path: str, local: Path) -> int:
        self.calls.append(["colab", "download", remote_path, str(local)])
        shutil.copyfile(self.local(remote_path), local)
        return local.stat().st_size

    def prestart_env(self) -> dict[str, str]:
        return {}

    def close(self) -> None:
        self.calls.append(["colab", "close"])

    def names(self) -> list[str]:
        return [c[1] if c[1] != "exec" else next(a for a in c if a.startswith("VIDGEN_ACTION")) for c in self.calls]


@pytest.fixture()
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vm = tmp_path / "vm"
    monkeypatch.setattr(colab_vm, "MARKER", vm / "content" / ".vidgen_setup_vidgen_done")
    monkeypatch.setattr(colab_vm, "SETUP_LOG", vm / "content" / "setup_vidgen.log")
    fake_bin = tmp_path / "fake_vidgen"
    fake_bin.write_text(f"#!{sys.executable}\n{FAKE_VIDGEN}", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setattr(remote, "VM_VIDGEN", str(fake_bin))
    monkeypatch.setattr(remote, "VM_PROJECTS", str(vm / "content" / "projects"))
    project = tmp_path / "my project"
    (project / "assets").mkdir(parents=True)
    (project / "video.yaml").write_text("title: x\n", encoding="utf-8")
    (project / "assets" / "a.png").write_bytes(b"png")
    (project / "build").mkdir()
    (project / "build" / "big.bin").write_bytes(b"cache")
    (project / "ltx-test").mkdir()
    (project / "ltx-test" / "x.mp4").write_bytes(b"x")

    def make(vidgen_hash: str | None = "c0de") -> tuple[FakeColab, Colab]:
        fake = FakeColab(vm, vidgen_hash)
        lines: list[str] = []
        colab = Colab("ltx", runner=fake, sleep=lambda s: None, say=lines.append, lock_dir=tmp_path / "locks",
                      transfer_factory=lambda c: fake)  # type: ignore[arg-type, return-value]
        colab.lines = lines  # type: ignore[attr-defined]
        return fake, colab

    return project, make


def _run(project: Path, colab: Colab, args: list[str]) -> int:
    run = remote.RemoteRun(colab, project, args, json_commands=("render",),
                           exclude=(*remote.EXCLUDED_DIRS, "ltx-test"), local_hash="c0de")
    return run.run()


@pytest.mark.slow
def test_render_syncs_changed_files_runs_and_brings_back_outputs(setup) -> None:
    project, make = setup
    fake, colab = make()
    assert _run(project, colab, ["render"]) == 0
    vm_project = fake.vm / "content" / "projects" / "my_project"
    assert (vm_project / "video.yaml").is_file() and (vm_project / "assets" / "a.png").is_file()
    assert not (vm_project / "build" / "big.bin").exists() and not (vm_project / "ltx-test").exists()
    assert (project / "output" / "v.mp4").read_bytes() == b"mp4"
    assert (project / "build" / "final" / "timings.json").is_file()
    assert not (project / "build" / "final" / "frames.json").exists()   # build/ stays on the VM
    assert (project / "audio" / "new.mp3").is_file()                     # made by the run
    text = "\n".join(colab.lines)  # type: ignore[attr-defined]
    assert "[1/1] chase: rendering" in text and "brought back 3 file(s)" in text
    assert json.loads((vm_project / ".vidgen-remote" / "run.out").read_text())["args"] == ["render", "--json"]
    assert fake.names()[:4] == ["sessions", "VIDGEN_ACTION=state", "upload", "VIDGEN_ACTION=begin"]
    assert fake.names()[-1] == "download" and fake.names().count("download") == 1   # one result tar
    # The second run asks nothing first (the VM's file list is cached) and sends no file.
    fake.calls.clear()
    assert _run(project, colab, ["render"]) == 0, "\n".join(colab.lines[-8:])  # type: ignore[attr-defined]
    names = fake.names()
    assert names[:3] == ["sessions", "upload", "VIDGEN_ACTION=begin"] and "VIDGEN_ACTION=state" not in names
    assert "0 of 3 files to send" in "\n".join(colab.lines)  # type: ignore[attr-defined]
    # The VM lost the project (a new session): begin reports the missing files, a second tar sends them.
    shutil.rmtree(vm_project)
    fake.calls.clear()
    assert _run(project, colab, ["render"]) == 0
    assert fake.names().count("upload") == 2 and (vm_project / "video.yaml").is_file()
    assert "the VM lacks 3 more file(s)" in "\n".join(colab.lines)  # type: ignore[attr-defined]


def test_failure_shows_the_log_tail_and_returns_the_exit_code(setup) -> None:
    project, make = setup
    fake, colab = make()
    fake.dropped = 1   # the first exec drops and is retried
    assert _run(project, colab, ["validate", "fail"]) == 3
    text = "\n".join(colab.lines)  # type: ignore[attr-defined]
    assert "exit code 3" in text and "error: something broke" in text.split("last lines of the log")[1]
    assert "download" not in fake.names()


def test_other_code_on_the_vm_fails_with_the_setup_command(setup) -> None:
    project, make = setup
    _, colab = make(vidgen_hash="0ld")
    with pytest.raises(ColabError, match=r"has vidgen 0ld, this computer's code is c0de.*setup_session.py.* ltx --vidgen-only"):
        _run(project, colab, ["render"])
    _, colab = make(vidgen_hash=None)
    colab_vm.MARKER.unlink()
    with pytest.raises(VidgenError, match="has no vidgen"):
        _run(project, colab, ["render"])
    # With a cached file list the check happens in the begin exec.
    run = remote.RemoteRun(colab, project, ["render"], local_hash="c0de")
    run.remember_files({})
    fake, colab = make(vidgen_hash="0ld")
    run.colab = colab
    with pytest.raises(ColabError, match="has vidgen 0ld"):
        run.run()
    assert "VIDGEN_ACTION=state" not in fake.names()


def test_unknown_session_is_an_error_without_fallback(setup) -> None:
    project, make = setup
    _, colab = make()
    colab.session = "other"
    with pytest.raises(ColabError, match="no Colab session 'other'"):
        _run(project, colab, ["render"])


def test_with_json_named_files_and_changes() -> None:
    assert remote.with_json(["render", "--preview"], ["render"]) == (["render", "--preview", "--json"], False)
    assert remote.with_json(["render", "--json"], ["render"]) == (["render", "--json"], True)
    assert remote.with_json(["studio"], ["render"]) == (["studio"], False)
    assert remote.changed_files({"a": "1", "b": "2"}, {"a": "1", "b": "3"}) == ["b"]
    assert remote.vm_name(Path("my project!")) == "my_project_"


def test_poll_sends_whole_lines_until_the_run_ends(tmp_path: Path) -> None:
    run = tmp_path / colab_vm.RUN_DIR
    run.mkdir()
    (run / "run.id").write_text("r1")
    (run / "run.pid").write_text("999999999")
    (run / "run.log").write_bytes(b"one\ntw")
    env = {"VIDGEN_PROJECT": str(tmp_path), "VIDGEN_OFFSET": "0"}
    (run / "run.rc").write_text("0")
    reply = colab_vm.poll(env)
    assert reply["done"] and reply["log"] == "one\ntw" and reply["run"]["rc"] == 0
    (run / "run.rc").unlink()
    (run / "run.pid").write_text(str(__import__("os").getpid()))
    reply = colab_vm.poll(env)
    assert not reply["done"] and reply["log"] == "one\n" and reply["offset"] == 4


def test_package_hash_and_archives(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "vidgen" / "__pycache__").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (repo / "src" / "vidgen" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "src" / "vidgen" / "__pycache__" / "a.cpython-313.pyc").write_bytes(b"cache")
    first = package_hash(repo / "src" / "vidgen")
    (repo / "src" / "vidgen" / "__pycache__" / "b.pyc").write_bytes(b"more cache")
    assert package_hash(repo / "src" / "vidgen") == first
    (repo / "src" / "vidgen" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert package_hash(repo / "src" / "vidgen") != first
    import tarfile
    with tarfile.open(source_archive(repo, tmp_path / "s.tar.gz")) as tar:
        assert sorted(tar.getnames()) == ["vidgen-src/pyproject.toml", "vidgen-src/src/vidgen/a.py"]
    with tarfile.open(files_archive(repo, ["pyproject.toml"], tmp_path / "f.tar.gz")) as tar:
        assert tar.getnames() == ["pyproject.toml"]
    with pytest.raises(ColabError, match="not vidgen's source folder"):
        source_archive(tmp_path, tmp_path / "t.tar.gz")


def test_run_env_adds_the_vm_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEP", "1")
    assert colab_vm.run_env(tmp_path / "missing.env")["KEEP"] == "1"
    env_file = tmp_path / "vidgen.env"
    env_file.write_text("VIDGEN_WEBGL=gpu\n# note\n\nLD_LIBRARY_PATH=/a:/b=c\n", encoding="utf-8")
    env = colab_vm.run_env(env_file)
    assert env["VIDGEN_WEBGL"] == "gpu" and env["LD_LIBRARY_PATH"] == "/a:/b=c" and env["KEEP"] == "1"
    assert "# note" not in env


def test_bring_back_names_and_changes(tmp_path: Path) -> None:
    for rel in ("output/a.mp4", "build/final/timings.json", "build/y", "audio/n.mp3"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"x")
    p = str(tmp_path)
    doc = json.dumps({"outputs": {"video": f"{p}/output/a.mp4", "timings": f"{p}/build/final/timings.json"},
                      "other": [f"{p}/build/y", "/elsewhere/z", f"{p}/output/a.mp4", f"{p}/output/gone.mp4"]})
    assert colab_vm.named_files(doc, tmp_path) == ["output/a.mp4", "build/final/timings.json"]
    after = {"audio/n.mp3": "1", "video.yaml": "2", "output/a.mp4": "3"}
    assert colab_vm.bring_back(doc, tmp_path, after, {"video.yaml": "2"}) == [
        "output/a.mp4", "build/final/timings.json", "audio/n.mp3"]
    packed = colab_vm.pack(tmp_path, ["output/a.mp4", "audio/n.mp3"])
    assert packed["files"] == {"output/a.mp4": 1, "audio/n.mp3": 1} and packed["size"] > 0
    assert colab_vm.pack(tmp_path, [])["archive"] is None


def test_begin_starts_a_run_once_and_checks_the_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(colab_vm, "start", lambda env, proc=None: {"started": True, "run": {"id": env["VIDGEN_RUN"]}})
    project = tmp_path / "p"
    archive = tmp_path / "sync.tar"
    want = {"a.txt": __import__("hashlib").sha256(b"A").hexdigest()}
    (tmp_path / "src").mkdir()
    remote.sync_archive(tmp_path / "src", [], want, archive)
    env = {"VIDGEN_PROJECT": str(project), "VIDGEN_RUN": "r1", "VIDGEN_ARCHIVE": str(archive), "VIDGEN_CHECK": "1"}
    assert colab_vm.begin(env) == {"started": False, "missing": ["a.txt"]} and archive.is_file()
    (tmp_path / "src" / "a.txt").write_bytes(b"A")
    remote.sync_archive(tmp_path / "src", ["a.txt"], want, archive)
    assert colab_vm.begin(env)["started"] and not archive.exists() and (project / "a.txt").read_bytes() == b"A"
    (project / colab_vm.RUN_DIR / "run.id").write_text("r1")
    assert colab_vm.begin(env)["started"] is False     # a retried begin of the same run does nothing


def test_lock_waits_for_another_call_and_takes_over_a_stale_one(tmp_path: Path) -> None:
    now = [1000.0]
    colab = Colab("ltx", runner=lambda a, t: CommandResult(0, ""), sleep=lambda s: now.__setitem__(0, now[0] + s),
                  say=lambda line: None, lock_dir=tmp_path, wall=lambda: now[0])
    colab.lock_path.write_text(json.dumps({"pid": 1, "until": 1005.0}), encoding="utf-8")
    colab.run(["exec", "-s", "ltx"], 30)
    assert now[0] > 1005.0 and not colab.lock_path.exists()   # waited until the holder's call ended
    colab.lock_path.write_text("", encoding="utf-8")            # unreadable and old: garbage
    now[0] += 100
    __import__("os").utime(colab.lock_path, (now[0] - 50, now[0] - 50))
    colab.run(["exec", "-s", "ltx"], 30)
    assert not colab.lock_path.exists()


def test_retries_pause_longer_each_time(tmp_path: Path) -> None:
    pauses: list[float] = []
    colab = Colab("ltx", runner=lambda a, t: CommandResult(124, "(timed out after 30 s)"), sleep=pauses.append,
                  say=lambda line: None, lock_dir=tmp_path)
    with pytest.raises(ColabError, match="kept failing"):
        colab.vm("state")
    assert pauses == [3.0, 10.0, 20.0, 30.0]
