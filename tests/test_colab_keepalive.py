"""tools/colab/keepalive.py with a fake `colab` CLI and a fake clock (no network, no VM)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from vidgen.colab import Colab, CommandResult

COLAB_DIR = Path(__file__).resolve().parents[1] / "tools" / "colab"
SESSION_LINE = "[ltx] gpu-l4-s-abc | Hardware: L4 | Shape: Standard | Variant: GPU"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"colab_{name}", COLAB_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


keepalive = _load("keepalive")


class FakeCli:
    """Answers `colab sessions` and the keepalive exec; the clock moves on with each call and sleep."""

    def __init__(self, listed: bool = True, answer: str = "right") -> None:
        self.now = 1_000_000.0
        self.listed = listed
        self.answer = answer
        self.calls: list[list[str]] = []
        self.gone_after: int | None = None

    def __call__(self, args: list[str], timeout: float) -> CommandResult:
        self.calls.append(args)
        if args[1] == "sessions":
            n = sum(1 for call in self.calls if call[1] == "sessions")
            listed = self.listed and (self.gone_after is None or n <= self.gone_after)
            return CommandResult(0, SESSION_LINE if listed else "No sessions")
        self.now += 5
        a = int(next(arg for arg in args if arg.startswith("KEEPALIVE_A=")).split("=")[1])
        reply = {"right": {"b": 7, "sum": a + 7}, "wrong": {"b": 7, "sum": a + 8}}.get(self.answer)
        return CommandResult(0, f"KEEPALIVE {json.dumps(reply)}" if reply else "Error: kernel died")

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def make(tmp_path: Path, cli: FakeCli, every: float = 420.0, hours: float = 1.0) -> tuple[object, list[str]]:
    colab = Colab("ltx", runner=cli, sleep=cli.sleep, say=lambda line: None, lock_dir=tmp_path / "locks",
                  wall=lambda: cli.now)
    lines: list[str] = []
    ka = keepalive.Keepalive(colab, every, hours, tmp_path / "ka.log", history_dir=tmp_path / "history",
                             rand=lambda: 41, out=lines.append)
    return ka, lines


def execs(cli: FakeCli) -> int:
    return sum(1 for call in cli.calls if call[1] == "exec")


def test_an_idle_session_gets_one_exec_and_the_sum_is_checked(tmp_path: Path) -> None:
    cli = FakeCli()
    ka, _ = make(tmp_path, cli)
    assert ka.round() == "ok rtt=5.0s"
    assert execs(cli) == 1 and not ka.colab.lock_path.exists() and ka.colab.stamp_path.exists()
    cli.answer = "wrong"
    ka.own_until = 0
    os.utime(ka.colab.stamp_path, (cli.now - 1000, cli.now - 1000))
    assert ka.round() == "wrong-sum"
    cli.answer = "none"
    os.utime(ka.colab.stamp_path, (cli.now - 1000, cli.now - 1000))
    assert ka.round() == "no-answer"


def test_a_held_lock_skips_without_waiting(tmp_path: Path) -> None:
    cli = FakeCli()
    ka, _ = make(tmp_path, cli)
    ka.colab.lock_path.parent.mkdir(parents=True)
    ka.colab.lock_path.write_text(json.dumps({"pid": 1, "until": cli.now + 60}), encoding="utf-8")
    assert ka.round() == "skip-locked"
    assert execs(cli) == 0 and ka.colab.lock_path.exists()


def test_a_recent_stamp_or_history_file_skips(tmp_path: Path) -> None:
    cli = FakeCli()
    ka, _ = make(tmp_path, cli)
    ka.colab.touch_stamp()
    os.utime(ka.colab.stamp_path, (cli.now - 100, cli.now - 100))
    assert ka.round() == "skip-recent (100s ago)"
    os.utime(ka.colab.stamp_path, (cli.now - 500, cli.now - 500))
    history = tmp_path / "history" / "ltx.jsonl"
    history.parent.mkdir()
    history.write_text("{}\n", encoding="utf-8")
    os.utime(history, (cli.now - 30, cli.now - 30))
    assert ka.round() == "skip-recent (30s ago)"
    os.utime(history, (cli.now - 421, cli.now - 421))
    assert ka.round().startswith("ok ")
    assert execs(cli) == 1


def test_every_call_through_the_helpers_touches_the_stamp(tmp_path: Path) -> None:
    cli = FakeCli()
    colab = Colab("ltx", runner=cli, lock_dir=tmp_path)
    colab.run(["sessions"], 90)
    assert not colab.stamp_path.exists()
    colab.exec_file(COLAB_DIR / "keepalive_vm.py", {"KEEPALIVE_A": "1"})
    assert colab.stamp_path.exists()


def test_its_own_call_does_not_skip_the_next_round_and_it_stops_after_hours(tmp_path: Path) -> None:
    cli = FakeCli()
    ka, lines = make(tmp_path, cli, every=420.0, hours=0.5)
    history = tmp_path / "history" / "ltx.jsonl"
    history.parent.mkdir()
    history.write_text("{}\n", encoding="utf-8")
    os.utime(history, (cli.now - 3600, cli.now - 3600))
    real = ka.ping

    def ping() -> str:   # the CLI writes its history when the exec ends
        result = real()
        os.utime(history, (cli.now, cli.now))
        os.utime(ka.colab.stamp_path, (cli.now, cli.now))
        return result

    ka.ping = ping
    start = cli.now
    assert ka.run() == 0
    results = [line.split(" ", 3)[3] for line in lines]
    assert results == ["ok rtt=5.0s"] * 5 + ["stop after 0.5 h"]   # rounds at 0, 7, 14, 21, 28 min
    assert cli.now - start < 1800
    assert (tmp_path / "ka.log").read_text(encoding="utf-8").splitlines()[0].endswith(" ltx ok rtt=5.0s")


def test_a_gone_session_stops_the_loop_and_is_never_recreated(tmp_path: Path) -> None:
    cli = FakeCli()
    cli.gone_after = 2
    ka, lines = make(tmp_path, cli, every=60.0, hours=8.0)
    ka.own_until = float("inf")   # its own stamps never count in this test
    assert ka.run() == 0
    assert [line.split(" ", 3)[3] for line in lines][-1] == "gone"
    assert len(lines) == 3 and all(call[1] in ("sessions", "exec") for call in cli.calls)


def test_durations() -> None:
    assert [keepalive.parse_duration(t) for t in ("30s", "7m", "1h", "2")] == [30, 420, 3600, 120]


def test_it_is_started_by_nothing_in_vidgen() -> None:
    repo = COLAB_DIR.parents[1]
    found = subprocess.run(["git", "grep", "-l", "keepalive", "--", "src"], cwd=repo, capture_output=True,
                           text=True, encoding="utf-8")
    assert found.stdout == ""
