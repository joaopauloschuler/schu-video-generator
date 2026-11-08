"""A quick tunnel is cleaned up when vidgen is signalled, killed or interrupted during its close
(DESIGN.md §115.5). Real child processes: a fake cloudflared and a driver that opens a host, so
signals and process death really happen. Everything is under the test's own temporary folder."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import vidgen
from tests.test_videogen_host import SETTINGS, fake_cloudflared, local_fetch, pid_alive, sources, wait_dead  # noqa: F401 - fixture
from vidgen.videogen import host as host_module
from vidgen.videogen import host_guard
from vidgen.videogen.host import QuickTunnelHost
from vidgen.videogen.ledger import Ledger

DRIVER = '''
import json, sys, time
from pathlib import Path
from vidgen.videogen.host import HostSettings, QuickTunnelHost
from vidgen.videogen.ledger import Ledger
from vidgen.videogen.openrouter import Response

work = Path(sys.argv[1])
source = work / "voice.mp3"
source.write_bytes(b"ID3 secret voice")
lines = []
settings = HostSettings(url_timeout=10, verify_timeout=1, verify_interval=0.05)
host = QuickTunnelHost([source], settings=settings, ledger=Ledger(work / "ledger.jsonl"), executable=[sys.executable, sys.argv[2]],
                       fetch=lambda method, url, timeout: Response(200, b"", {}), out=lines.append)
with host:
    print(json.dumps({"tunnel": host.tunnel.process.pid, "folder": str(host.folder), "watcher": host._guard.watcher_pid, "lines": lines}), flush=True)
    time.sleep(60)
'''

posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX signals and process groups")


@pytest.fixture(autouse=True)
def _handlers_restored() -> Iterator[None]:
    """A close in the watchdog's thread leaves the (inert) handler installed: back to default after each test."""
    yield
    host_guard._restore_handlers()


@pytest.fixture
def temp_root(tmp_path: Path) -> Path:
    root = tmp_path / "temp-root"
    root.mkdir()
    return root


class Driver:
    """A child process that opened a host and waits, as a vidgen running a paid shot would."""

    def __init__(self, tmp_path: Path, script: Path, temp_root: Path) -> None:
        env = {**os.environ, "TMPDIR": str(temp_root), "PYTHONPATH": str(Path(vidgen.__file__).parents[1])}
        driver_script = tmp_path / "driver.py"
        driver_script.write_text(DRIVER, encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, str(driver_script), str(tmp_path), str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=env, start_new_session=True,
        )
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        if not line:
            raise AssertionError(self.process.communicate()[1])
        self.info: dict[str, Any] = json.loads(line)
        self.tunnel_pid = int(self.info["tunnel"])
        self.folder = Path(self.info["folder"])
        self.watcher_pid = int(self.info["watcher"])

    def wait_ended(self) -> int:
        code = self.process.wait(20)
        self.process.communicate()
        return code

    def kill_leftovers(self) -> None:
        """Only this test's own processes: the fake cloudflared's group, the watcher, the driver."""
        for pid, kill in ((self.process.pid, os.kill), (self.watcher_pid, os.kill), (self.tunnel_pid, os.killpg)):
            try:
                kill(pid, signal.SIGKILL)
            except OSError:
                pass


@pytest.fixture
def driver(tmp_path: Path, fake_cloudflared: list[str], temp_root: Path):  # noqa: F811
    started = Driver(tmp_path, Path(fake_cloudflared[1]), temp_root)
    yield started
    started.kill_leftovers()


def closed_reason(tmp_path: Path) -> str | None:
    closes = [e for e in Ledger(tmp_path / "ledger.jsonl").events() if e["event"] == "host_close"]
    return closes[-1]["reason"] if closes else None


@posix_only
@pytest.mark.parametrize("signum, name, code", [(signal.SIGTERM, "SIGTERM", 143), (signal.SIGHUP, "SIGHUP", 129)])
def test_a_termination_signal_closes_the_host_properly(tmp_path: Path, driver: Driver, signum: int, name: str, code: int) -> None:
    child = int((tmp_path / "cf_child.txt").read_text(encoding="utf-8"))
    driver.process.send_signal(signum)
    assert driver.wait_ended() == code
    assert not driver.folder.exists()
    assert wait_dead(driver.tunnel_pid) and wait_dead(child)
    assert closed_reason(tmp_path) == f"terminated ({name})"
    assert wait_dead(driver.watcher_pid)   # a proper close also ends the watcher


@posix_only
@pytest.mark.parametrize("whole_group", [False, True], ids=["kill", "process_group_kill_like_mcp"])
def test_a_hard_kill_is_cleaned_up_by_the_watcher(tmp_path: Path, driver: Driver, whole_group: bool) -> None:
    child = int((tmp_path / "cf_child.txt").read_text(encoding="utf-8"))
    (os.killpg if whole_group else os.kill)(driver.process.pid, signal.SIGKILL)
    assert driver.wait_ended() == -signal.SIGKILL
    assert wait_dead(driver.tunnel_pid, 8) and wait_dead(child, 8), "cloudflared outlived a killed vidgen"
    deadline = time.monotonic() + 8
    while driver.folder.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not driver.folder.exists(), "the temporary copies outlived a killed vidgen"
    assert wait_dead(driver.watcher_pid, 8)
    assert closed_reason(tmp_path) is None   # the ledger has no close: only vidgen writes it


@posix_only
def test_a_kill_of_vidgen_and_its_watcher_is_swept_at_the_next_open(tmp_path: Path, driver: Driver, temp_root: Path, fake_cloudflared: list[str]) -> None:  # noqa: F811
    os.kill(driver.watcher_pid, signal.SIGKILL)
    assert wait_dead(driver.watcher_pid)
    os.kill(driver.process.pid, signal.SIGKILL)
    assert driver.wait_ended() == -signal.SIGKILL
    time.sleep(0.2)
    assert driver.folder.exists()   # nothing outside vidgen is left to clean up
    assert pid_alive(driver.tunnel_pid)   # and nothing does; the owner closes it by hand (the docs say so)
    # the next vidgen's open sweeps it: a real second process, with its own new folder
    second = Driver(tmp_path, Path(fake_cloudflared[1]), temp_root)
    try:
        assert not driver.folder.exists()
        assert any("left by a vidgen that ended" in line for line in second.info["lines"])
        assert second.folder.exists()   # its own folder, of course
        third = host_guard.sweep_stale_shares(temp_root)
        assert third == [] and second.folder.exists()   # a running host's folder is never swept
    finally:
        second.kill_leftovers()
        second.wait_ended()


def test_the_sweep_leaves_a_running_host_and_foreign_folders(temp_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tempfile.tempdir", str(temp_root))
    running, lock = host_guard.make_share_folder()
    (running / "copy.mp3").write_bytes(b"voice")
    foreign = temp_root / "vidgen-share-foreign"   # an older vidgen's folder: no marker, not ours to judge
    foreign.mkdir()
    (foreign / "x.mp3").write_bytes(b"x")
    other = temp_root / "other-folder"
    other.mkdir()
    stale, stale_lock = host_guard.make_share_folder()
    (stale / "copy.mp3").write_bytes(b"voice")
    host_guard.release_share_folder(stale_lock)   # as the operating system does when a process dies
    assert host_guard.sweep_stale_shares(temp_root) == [stale]
    assert running.exists() and (running / "copy.mp3").exists() and foreign.exists() and other.exists() and not stale.exists()
    assert host_guard.sweep_stale_shares(temp_root) == []
    host_guard.release_share_folder(lock)
    assert host_guard.sweep_stale_shares(temp_root) == [running]


@posix_only
def test_the_watcher_never_signals_a_process_that_is_no_longer_its_tunnel(tmp_path: Path) -> None:
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    folder = tmp_path / "vidgen-share-x"
    folder.mkdir()
    alive_read, alive_write = os.pipe()
    watcher = subprocess.Popen([sys.executable, "-I", "-S", str(host_guard.WATCHER_SCRIPT), str(folder), str(alive_read)], stdin=subprocess.PIPE, pass_fds=(alive_read,), text=True)
    os.close(alive_read)
    try:
        os.close(alive_write)   # the tunnel is gone: end-of-file on the pipe, as if cloudflared had exited
        assert watcher.stdin is not None
        watcher.stdin.write(f"tunnel {bystander.pid}\n")
        watcher.stdin.close()   # vidgen died
        assert watcher.wait(10) == 0
        assert not folder.exists()
        assert bystander.poll() is None and pid_alive(bystander.pid)
    finally:
        os.killpg(bystander.pid, signal.SIGKILL)
        bystander.wait(5)


def open_host(tmp_path: Path, fake_cloudflared: list[str], **options: Any) -> tuple[QuickTunnelHost, Ledger]:  # noqa: F811
    project, audio, _ = sources(tmp_path)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    host = QuickTunnelHost([audio], root=project, settings=SETTINGS, ledger=ledger, executable=fake_cloudflared, fetch=local_fetch(tmp_path), **options)
    host.open()
    return host, ledger


def test_ctrl_c_during_close_finishes_the_other_steps_and_a_later_close_resumes(tmp_path: Path, fake_cloudflared: list[str], monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    host, ledger = open_host(tmp_path, fake_cloudflared)
    real_stop = host_module.stop_process_tree
    tunnel_pid = host.tunnel.process.pid

    def interrupted(process: Any, wait_seconds: float = 5.0) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(host_module, "stop_process_tree", interrupted)
    with pytest.raises(KeyboardInterrupt):
        host.close("done")
    assert not host.folder.exists()   # the steps after the interrupted one ran
    assert host.close_reason == "done" and not host.is_open
    assert wait_dead(tunnel_pid)   # the watcher step that followed took the interrupted step over
    assert not host.wait_closed(0)   # the host says it is not finished
    assert [e for e in ledger.events() if e["event"] == "host_close"] == []
    monkeypatch.setattr(host_module, "stop_process_tree", real_stop)
    host.close("again")   # as the atexit hook or a second call would
    assert host.close_reason == "done" and host.wait_closed(0)
    assert wait_dead(tunnel_pid)
    closes = [e for e in ledger.events() if e["event"] == "host_close"]
    assert len(closes) == 1 and closes[0]["reason"] == "done" and closes[0]["folder_deleted"] is True
    host.close("nothing left")   # idempotent


def test_ctrl_c_during_close_is_resumed_by_the_watchdog(tmp_path: Path, fake_cloudflared: list[str], monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    host, _ = open_host(tmp_path, fake_cloudflared)
    real_stop = host_module.stop_process_tree
    calls: list[int] = []

    def interrupted_once(process: Any, wait_seconds: float = 5.0) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise KeyboardInterrupt
        real_stop(process, wait_seconds)

    monkeypatch.setattr(host_module, "stop_process_tree", interrupted_once)
    with pytest.raises(KeyboardInterrupt):
        host.close("interrupted")
    assert host.wait_closed(5), "the watchdog did not finish the interrupted close"
    assert wait_dead(host.tunnel.process.pid) and host.close_reason == "interrupted"


@pytest.mark.parametrize("step", ["_stop_server", "_delete_folder", "_finish_guard", "_report_closed"])
def test_an_interrupted_later_step_is_resumed_too(tmp_path: Path, fake_cloudflared: list[str], monkeypatch: pytest.MonkeyPatch, step: str) -> None:  # noqa: F811
    host, ledger = open_host(tmp_path, fake_cloudflared)
    real = getattr(host, step)

    def interrupted() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(host, step, interrupted)
    with pytest.raises(KeyboardInterrupt):
        host.close("done")
    monkeypatch.setattr(host, step, real)
    host.close("done")
    assert host.wait_closed(0) and not host.folder.exists() and wait_dead(host.tunnel.process.pid)
    assert [e["reason"] for e in ledger.events() if e["event"] == "host_close"] == ["done"]


def test_a_second_close_waits_for_the_first(tmp_path: Path, fake_cloudflared: list[str], monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    host, _ = open_host(tmp_path, fake_cloudflared)
    real_stop = host_module.stop_process_tree
    in_step = threading.Event()

    def slow_stop(process: Any, wait_seconds: float = 5.0) -> None:
        in_step.set()
        time.sleep(0.5)
        real_stop(process, wait_seconds)

    monkeypatch.setattr(host_module, "stop_process_tree", slow_stop)
    first = threading.Thread(target=host.close, args=("first",))
    first.start()
    assert in_step.wait(5)
    host.close("second")
    assert not host.folder.exists() and host.wait_closed(0) and host.close_reason == "first"   # finished when the second returned
    first.join(5)


def test_a_second_close_gives_up_after_its_wait_and_the_closer_itself_never_waits(tmp_path: Path, fake_cloudflared: list[str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:  # noqa: F811
    host, _ = open_host(tmp_path, fake_cloudflared)
    real_stop = host_module.stop_process_tree
    release = threading.Event()
    in_step = threading.Event()
    reentered_seconds: list[float] = []

    def stop_stuck_until_released(process: Any, wait_seconds: float = 5.0) -> None:
        in_step.set()
        started = time.monotonic()
        host.close("re-entered from a signal handler")   # in the closing thread: must return at once, not wait for itself
        reentered_seconds.append(time.monotonic() - started)
        release.wait(10)
        real_stop(process, wait_seconds)

    monkeypatch.setattr(host_module, "stop_process_tree", stop_stuck_until_released)
    first = threading.Thread(target=host.close, args=("first",))
    first.start()
    assert in_step.wait(5)
    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="vidgen.videogen"):
        host.close("second", wait_seconds=0.2)
    assert 0.15 <= time.monotonic() - started < 3 and not host.wait_closed(0)
    assert "still running" in caplog.text
    release.set()
    first.join(10)
    assert reentered_seconds and reentered_seconds[0] < 1.0
    assert host.wait_closed(0) and not host.folder.exists()


def test_handlers_set_by_others_stay_and_defaults_come_back(tmp_path: Path, fake_cloudflared: list[str]) -> None:  # noqa: F811
    custom = lambda signum, frame: None   # noqa: E731
    before = signal.signal(signal.SIGTERM, custom)
    try:
        with QuickTunnelHost([sources(tmp_path)[1]], settings=SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path)):
            assert signal.getsignal(signal.SIGTERM) is custom
        assert signal.getsignal(signal.SIGTERM) is custom
    finally:
        signal.signal(signal.SIGTERM, before)
    if hasattr(signal, "SIGHUP"):
        before = signal.signal(signal.SIGHUP, signal.SIG_IGN)   # nohup
        try:
            with QuickTunnelHost([sources(tmp_path / "x")[1]], settings=SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path)):
                assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
        finally:
            signal.signal(signal.SIGHUP, before)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_the_handler_comes_and_goes_with_the_open_host_and_only_in_the_main_thread(tmp_path: Path, fake_cloudflared: list[str]) -> None:  # noqa: F811
    with QuickTunnelHost([sources(tmp_path)[1]], settings=SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path)):
        assert signal.getsignal(signal.SIGTERM) == host_guard._on_termination
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    errors: list[BaseException] = []

    def in_a_thread() -> None:
        try:
            with QuickTunnelHost([sources(tmp_path / "y")[1]], settings=SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path)):
                assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
        except BaseException as exc:  # noqa: BLE001 - reported to the main thread
            errors.append(exc)

    thread = threading.Thread(target=in_a_thread)
    thread.start()
    thread.join(20)
    assert not errors


def test_windows_job_object_layout_and_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Windows path, without Windows: the structure's layout and the calls made."""
    pointer_bits = ctypes.sizeof(ctypes.c_void_p) * 8
    assert ctypes.sizeof(host_guard._ExtendedLimits) == {64: 144, 32: 112}[pointer_bits]
    calls: list[tuple[str, Any]] = []

    class Kernel32:
        def CreateJobObjectW(self, attributes: Any, name: Any) -> int:  # noqa: N802
            calls.append(("create", (attributes, name)))
            return 0x7fff_0000_1234

        def SetInformationJobObject(self, job: int, klass: int, info: Any, size: int) -> int:  # noqa: N802
            limits = info._obj
            calls.append(("limits", (job, klass, limits.BasicLimitInformation.LimitFlags, size)))
            return 1

        def AssignProcessToJobObject(self, job: int, process_handle: int) -> int:  # noqa: N802
            calls.append(("assign", (job, process_handle)))
            return 1

        def CloseHandle(self, handle: int) -> int:  # noqa: N802
            calls.append(("close", handle))
            return 1

    monkeypatch.setattr(host_guard, "_kernel32", Kernel32)
    process = SimpleNamespace(_handle=4242)
    job = host_guard._job_for_process(process)   # type: ignore[arg-type]
    assert job == 0x7fff_0000_1234
    assert calls[0] == ("create", (None, None))
    assert calls[1] == ("limits", (job, 9, 0x2000, ctypes.sizeof(host_guard._ExtendedLimits)))
    assert calls[2] == ("assign", (job, 4242))
    assert len(calls) == 3
    calls.clear()

    guard = host_guard.HostGuard.__new__(host_guard.HostGuard)
    guard._watcher = None
    guard._alive_write_fd = None
    guard._job = job
    guard.tunnel_stopped()
    assert calls == [("close", job)]   # after cloudflared is stopped the job goes


def test_windows_job_object_failure_is_a_warning(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    class NoAssign:
        def CreateJobObjectW(self, attributes: Any, name: Any) -> int:  # noqa: N802
            return 7

        def SetInformationJobObject(self, job: int, klass: int, info: Any, size: int) -> int:  # noqa: N802
            return 1

        def AssignProcessToJobObject(self, job: int, process_handle: int) -> int:  # noqa: N802
            return 0

        def CloseHandle(self, handle: int) -> int:  # noqa: N802
            return 1

    monkeypatch.setattr(host_guard, "_kernel32", NoAssign)
    with caplog.at_level(logging.WARNING, logger="vidgen.videogen"):
        assert host_guard._job_for_process(SimpleNamespace(_handle=1)) is None   # type: ignore[arg-type]
    assert "outlive" in caplog.text
