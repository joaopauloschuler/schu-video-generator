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
    """`colab` for one VM folder: sessions, upload/download (copies) and exec of colab_vm.py."""

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
        if command == "upload":
            target = self.local(args[-1])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args[-2], target)
            return CommandResult(0, "")
        if command == "download":
            shutil.copyfile(self.local(args[-2]), args[-1])
            return CommandResult(0, "")
        assert command == "exec" and Path(args[-1]).name == "colab_vm.py"
        if self.dropped:
            self.dropped -= 1
            return CommandResult(1, "RuntimeError: Connection was lost.")
        env = dict(a.split("=", 1) for a in args if "=" in a and a.startswith("VIDGEN_"))
        for key in ("VIDGEN_PROJECT", "VIDGEN_ARCHIVE", "VIDGEN_DEST"):
            if env.get(key):
                env[key] = str(self.local(env[key]))
        out = io.StringIO()
        with redirect_stdout(out):
            colab_vm.main(env)
        return CommandResult(0, out.getvalue())

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
        colab = Colab("ltx", runner=fake, sleep=lambda s: None, say=lines.append)
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
    # The second run sends nothing: every file is there already.
    fake.calls.clear()
    assert _run(project, colab, ["render"]) == 0, "\n".join(colab.lines[-8:])  # type: ignore[attr-defined]
    assert "upload" not in fake.names() and "none changed" in "\n".join(colab.lines)  # type: ignore[attr-defined]


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
    doc = {"outputs": {"video": "/p/x/output/a.mp4", "timings": "/p/x/build/final/timings.json"},
           "other": ["/p/x/build/y", "/elsewhere/z", "/p/x/output/a.mp4"]}
    assert remote.named_files(doc, "/p/x") == ["output/a.mp4", "build/final/timings.json"]
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
