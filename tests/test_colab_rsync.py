"""vidgen remote's rsync sync (vidgen.colab_rsync): the command lines with ssh mocked, and the filter
rules proved with the local rsync between two folders (a fake `ssh` on PATH runs the far side here)."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vidgen import colab_rsync
from vidgen.colab import CommandResult
from vidgen.colab_ssh import SshLink
from vidgen.remote import EXCLUDED_DIRS

EXCLUDE = (*EXCLUDED_DIRS, "ltx-test")
needs_rsync = pytest.mark.skipif(shutil.which("rsync") is None or os.name == "nt", reason="no local rsync")

# A stand-in for ssh: records its arguments, drops the options and runs the remote command here.
FAKE_SSH = '''import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_SSH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
i = 0
while args[i].startswith("-"):
    i += 2 if args[i] in ("-F", "-i", "-o", "-l") else 1
os.execvp("sh", ["sh", "-c", " ".join(args[i + 1:])])
'''


def _link(tmp_path: Path, runner: object = None) -> SshLink:
    key = tmp_path / "key"
    key.write_text("k", encoding="utf-8")
    return SshLink("ltx", key=key, socket_dir=tmp_path / "ssh", runner=runner, multiplex=True,  # type: ignore[arg-type]
                   listed=lambda: {"ltx": "L4"}, say=lambda line: None)


def test_up_command_uses_the_links_ssh_deletes_and_leaves_out_the_excluded_dirs(tmp_path: Path) -> None:
    link = _link(tmp_path)
    args = colab_rsync.up_args(link, "/p/my film", "/content/projects/my_film", EXCLUDE)
    assert args[:2] == ["rsync", "-rltz"] and "--delete" in args and "--delete-excluded" not in args
    assert shlex.split(args[args.index("-e") + 1]) == link.ssh("-o", "ControlMaster=no")   # the same options
    assert "--rsync-path=mkdir -p /content/projects/my_film && rsync" in args
    for top in EXCLUDE:
        assert f"--exclude=/{top}" in args
    for name in colab_rsync.ALWAYS_SKIPPED:
        assert f"--exclude={name}" in args
    assert args[-2:] == ["/p/my film/", "root@colab:/content/projects/my_film/"]


def test_rsh_quotes_each_word_for_rsync() -> None:
    assert colab_rsync.rsh_word("ProxyCommand=colab ssh -s 'a b'") == "'ProxyCommand=colab ssh -s ''a b'''"
    assert colab_rsync.literal("output/a.mp4") == "output/a.mp4"
    assert colab_rsync.literal("output/[x]*.mp4") == r"output/\[x\]\*.mp4"


def test_down_rules_bring_back_named_files_and_build_without_its_caches() -> None:
    rules = colab_rsync.down_filters(EXCLUDE, ["output/clips/v.mp4"])
    assert rules.index("--include=/output/") < rules.index("--include=/output/clips/") < rules.index(
        "--include=/output/clips/v.mp4") < rules.index("--exclude=/output")
    assert "--include=/build/videogen/***" in rules and "--exclude=/build/*/scenes/" in rules
    assert rules.index("--include=/build/videogen/***") < rules.index("--exclude=/build/*/scenes/")
    assert "--exclude=/build" not in rules and "--exclude=/ltx-test" in rules and "--exclude=/media" in rules


def test_a_dropped_connection_reconnects_once_and_a_failure_is_an_error(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    codes = [0, 255, 0, 0, 0, 23]   # check, rsync (dropped), -O exit, master, check, rsync again

    def fake(args: list[str], *rest: object) -> CommandResult:
        calls.append(args)
        return CommandResult(codes.pop(0) if codes else 0, ">> 3 a.txt\n>> 0 dir/\ndeleting old.txt\nsome error")

    link = _link(tmp_path, fake)
    with pytest.raises(colab_rsync.ColabError, match=r"rsync could not send \(exit code 23\): some error"):
        colab_rsync.run(link, ["rsync", "x"], "send")
    assert [c[0] for c in calls].count("rsync") == 2
    moved = colab_rsync.parse_moved(">> 3 a.txt\n>> 0 dir/\ndeleting old.txt\n")
    assert moved.files == {"a.txt": 3} and moved.deleted == ["old.txt"] and moved.size == 3


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


@pytest.fixture()
def fake_ssh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake ``ssh`` first on PATH; returns its argument log."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ssh").write_text(f"#!{sys.executable}\n{FAKE_SSH}", encoding="utf-8")
    (bin_dir / "ssh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("FAKE_SSH_LOG", str(log))
    return log


def local_runner(args: list[str], timeout: float, stdin: object = None, stdout: object = None) -> CommandResult:
    """Runs rsync for real; the master checks of the link succeed without ssh."""
    if args[0] != "rsync":
        return CommandResult(0, "")
    done = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    return CommandResult(done.returncode, done.stdout + done.stderr)


@needs_rsync
def test_real_rsync_deletes_there_but_never_touches_the_excluded_dirs(tmp_path: Path, fake_ssh: Path) -> None:
    here, vm = tmp_path / "here", tmp_path / "vm" / "projects" / "p"
    _write(here, {"video.yaml": "new text", "assets/a.png": "a", "build/big.bin": "local cache",
                  "output/v.mp4": "local", "ltx-test/x": "local", "__pycache__/m.pyc": "c"})
    _write(vm, {"video.yaml": "old", "assets/gone.png": "deleted here", "build/big.bin": "vm cache",
                "build/final/scenes/s.mp4": "s", "output/v.mp4": "vm", "exports/e.png": "e", "media/m": "m",
                "ltx-test/x": "vm", "ltx-test/y": "vm", ".vidgen-remote/run.id": "r1", ".git/HEAD": "h"})
    link = _link(tmp_path, local_runner)
    moved = colab_rsync.run(link, colab_rsync.up_args(link, str(here), str(vm), EXCLUDE), "send")
    assert (vm / "video.yaml").read_text() == "new text" and (vm / "assets" / "a.png").is_file()
    assert not (vm / "assets" / "gone.png").exists() and "assets/gone.png" in moved.deleted
    for rel, text in {"build/big.bin": "vm cache", "build/final/scenes/s.mp4": "s", "output/v.mp4": "vm",
                      "exports/e.png": "e", "media/m": "m", "ltx-test/x": "vm", "ltx-test/y": "vm",
                      ".vidgen-remote/run.id": "r1", ".git/HEAD": "h"}.items():
        assert (vm / rel).read_text() == text, rel
    assert not (vm / "__pycache__").exists()
    assert set(moved.files) == {"video.yaml", "assets/a.png"}
    ssh_args = json.loads(fake_ssh.read_text(encoding="utf-8").splitlines()[0])
    assert ssh_args[:len(link.options())] == link.options()   # the -e words reach ssh unchanged


@needs_rsync
def test_real_rsync_brings_back_build_without_caches_and_keeps_local_edits(tmp_path: Path, fake_ssh: Path) -> None:
    here, vm = tmp_path / "here", tmp_path / "vm"
    _write(here, {"video.yaml": "edited here during the run", "output/old.mp4": "o"})
    _write(vm, {"video.yaml": "as sent", "audio/new.mp3": "made by the run",
                "build/videogen/hook_b1/guide.mp4": "g", "build/videogen/web/first_frame.png": "f",
                "build/final/storyboard/sheet.png": "sb", "build/final/timings.json": "t",
                "build/final/scenes/s.mp4": "big", "build/preview/web/c.mkv": "big", "build/final/frames/1.png": "big",
                "build/final/padded/mix.wav": "big", "build/final/media/videos/x.mp4": "big", "build/music/m.wav": "big",
                "output/v.mp4": "named", "output/other.mp4": "not named", "exports/stills/s.png": "named too",
                "ltx-test/x": "vm only", ".vidgen-remote/run.log": "log"})
    os.utime(vm / "video.yaml", (1_000_000, 1_000_000))   # older than the local edit
    link = _link(tmp_path, local_runner)
    args = colab_rsync.down_args(link, str(vm), str(here), EXCLUDE, ["output/v.mp4", "exports/stills/s.png"])
    moved = colab_rsync.run(link, args, "bring back")
    assert (here / "video.yaml").read_text() == "edited here during the run"
    for rel in ("audio/new.mp3", "build/videogen/hook_b1/guide.mp4", "build/videogen/web/first_frame.png",
                "build/final/storyboard/sheet.png", "build/final/timings.json", "output/v.mp4", "exports/stills/s.png"):
        assert (here / rel).is_file(), rel
    for rel in ("build/final/scenes", "build/preview/web", "build/final/frames", "build/final/padded", "build/final/media",
                "build/music", "output/other.mp4", "ltx-test", ".vidgen-remote"):
        assert not (here / rel).exists(), rel
    assert (here / "output" / "old.mp4").is_file()   # nothing deleted here
    assert "output/v.mp4" in moved.files and "video.yaml" not in moved.files
