"""``--jobs auto``: the job formula, memory readings per platform (mocked) and the CLI (no render)."""

from __future__ import annotations

import ctypes
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from vidgen import cli
from vidgen.cli import main
from vidgen.render import jobs
from vidgen.render.jobs import PER_JOB_BYTES, JobsChoice, MemoryReading, jobs_for

GB = 1_000_000_000
MEMINFO = "MemTotal:        8000000 kB\nMemFree:          500000 kB\nMemAvailable:    4000000 kB\nSwapTotal:      16000000 kB\nSwapFree:       16000000 kB\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ----- the formula -------------------------------------------------------------------------------


def test_jobs_for_is_the_smaller_of_memory_and_cores() -> None:
    assert jobs_for(6 * GB, 8, 1 * GB) == 6  # memory-bound
    assert jobs_for(64 * GB, 4, 1 * GB) == 4  # core-bound
    assert jobs_for(int(2.9 * GB), 4, 1 * GB) == 2  # whole jobs only
    assert jobs_for(1 * GB, 4, 3 * GB) == 1 and jobs_for(0, 4) == 1  # at least 1
    assert jobs_for(None, 16) == 1  # memory unknown
    assert jobs_for(3 * PER_JOB_BYTES, 16) == 3  # the default per-job figure


@pytest.mark.parametrize(
    ("platform", "reading", "cores", "expected"),
    [
        ("linux", MemoryReading(7 * GB, "/proc/meminfo MemAvailable"), 4, 4),
        ("win32", MemoryReading(int(3.2 * GB), "GlobalMemoryStatusEx"), 8, 2),
        ("darwin", MemoryReading(int(1.2 * GB), "vm_stat free + inactive"), 10, 1),
        ("freebsd", None, 4, 1),
    ],
)
def test_choose_jobs_per_platform(
    platform: str, reading: MemoryReading | None, cores: int, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("linux_available", "windows_available", "macos_available"):
        monkeypatch.setattr(jobs, name, lambda: pytest.fail("read the memory of another platform"))
    reader = {"linux": "linux_available", "win32": "windows_available", "darwin": "macos_available"}.get(platform)
    if reader is not None:
        monkeypatch.setattr(jobs, reader, lambda: reading)
    monkeypatch.setattr(jobs.sys, "platform", platform)
    monkeypatch.setattr(jobs, "cpu_cores", lambda: cores)
    choice = jobs.choose_jobs()
    assert choice.jobs == expected and choice.memory == reading and choice.cores == cores


def test_available_memory_dispatches_by_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, platform in (("linux_available", "linux"), ("windows_available", "win32"), ("macos_available", "darwin")):
        reading = MemoryReading(1, name)
        monkeypatch.setattr(jobs, name, lambda reading=reading: reading)
        assert jobs.available_memory(platform).source == name
    assert jobs.available_memory("freebsd13") is None


def test_choose_jobs_and_its_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "available_memory", lambda: MemoryReading(int(5.2 * GB), "/proc/meminfo MemAvailable"))
    monkeypatch.setattr(jobs, "cpu_cores", lambda: 2)
    choice = jobs.choose_jobs()
    assert choice.jobs == 2
    assert choice.reason == "5.2 GB available (/proc/meminfo MemAvailable) / 1.5 GB per job = 3, 2 CPU cores"
    assert choice.to_json() == {
        "requested": "auto", "jobs": 2, "cores": 2, "per_job_bytes": PER_JOB_BYTES, "available_bytes": int(5.2 * GB),
        "memory_source": "/proc/meminfo MemAvailable", "reason": choice.reason,
    }
    monkeypatch.setattr(jobs, "available_memory", lambda: None)
    unknown = jobs.choose_jobs()
    assert unknown.jobs == 1 and "available memory unknown" in unknown.reason
    assert unknown.to_json()["available_bytes"] is None


def test_cpu_cores_uses_the_affinity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs.os, "sched_getaffinity", lambda pid: {0, 1, 2}, raising=False)
    assert jobs.cpu_cores() == 3
    monkeypatch.delattr(jobs.os, "sched_getaffinity")
    monkeypatch.setattr(jobs.os, "cpu_count", lambda: None)
    assert jobs.cpu_cores() == 1


# ----- Linux: /proc/meminfo and cgroups ----------------------------------------------------------


def test_linux_reads_mem_available_never_swap(tmp_path: Path) -> None:
    write(tmp_path / "proc" / "meminfo", MEMINFO)
    reading = jobs.linux_available(tmp_path)
    assert reading == MemoryReading(4_000_000 * 1024, "/proc/meminfo MemAvailable")
    write(tmp_path / "proc" / "meminfo", "MemTotal: 1 kB\n")  # a kernel before 3.14
    assert jobs.linux_available(tmp_path) is None
    assert jobs.linux_available(tmp_path / "nowhere") is None


def test_linux_cgroup_v1_limit_of_the_group_or_an_ancestor(tmp_path: Path) -> None:
    write(tmp_path / "proc" / "meminfo", MEMINFO)
    write(tmp_path / "proc" / "self" / "cgroup", "5:cpu:/\n4:memory:/outer/inner\n0::/\n")
    base = tmp_path / "sys" / "fs" / "cgroup" / "memory"
    write(base / "memory.limit_in_bytes", "9223372036854771712")  # the root: no limit
    write(base / "memory.usage_in_bytes", str(6 * GB))
    write(base / "outer" / "memory.limit_in_bytes", str(3 * GB))
    write(base / "outer" / "memory.usage_in_bytes", str(int(1.5 * GB)))
    write(base / "outer" / "memory.stat", f"cache 1\ntotal_inactive_file {int(0.5 * GB)}\n")
    write(base / "outer" / "inner" / "memory.limit_in_bytes", str(8 * GB))
    write(base / "outer" / "inner" / "memory.usage_in_bytes", str(1 * GB))
    reading = jobs.linux_available(tmp_path)
    # the ancestor's limit counts: 3 GB - (1.5 GB used - 0.5 GB reclaimable cache)
    assert reading == MemoryReading(2 * GB, "cgroup memory.limit_in_bytes minus its use")
    write(base / "outer" / "memory.limit_in_bytes", str(64 * GB))
    assert jobs.linux_available(tmp_path) == MemoryReading(4_000_000 * 1024, "/proc/meminfo MemAvailable")


def test_linux_cgroup_v2(tmp_path: Path) -> None:
    write(tmp_path / "proc" / "meminfo", MEMINFO)
    write(tmp_path / "proc" / "self" / "cgroup", "0::/user.slice/job\n")
    group = tmp_path / "sys" / "fs" / "cgroup" / "user.slice" / "job"
    write(group / "memory.max", "max\n")
    write(group / "memory.current", str(1 * GB))
    assert jobs.cgroup_headroom(tmp_path) is None  # no limit
    write(group / "memory.max", f"{2 * GB}\n")
    write(group / "memory.stat", f"anon 1\ninactive_file {int(0.25 * GB)}\n")
    assert jobs.linux_available(tmp_path) == MemoryReading(int(1.25 * GB), "cgroup memory.max minus its use")
    write(group / "memory.current", str(3 * GB))
    write(group / "memory.stat", "")
    assert jobs.cgroup_headroom(tmp_path) == MemoryReading(0, "cgroup memory.max minus its use")


def test_linux_cgroup_path_missing_inside_a_container(tmp_path: Path) -> None:
    """A container sees the host's cgroup path, but its own group mounted at the root."""
    write(tmp_path / "proc" / "meminfo", MEMINFO)
    write(tmp_path / "proc" / "self" / "cgroup", "0::/kubepods/pod1/abc\n")
    write(tmp_path / "sys" / "fs" / "cgroup" / "memory.max", str(1 * GB))
    write(tmp_path / "sys" / "fs" / "cgroup" / "memory.current", str(int(0.2 * GB)))
    assert jobs.linux_available(tmp_path) == MemoryReading(int(0.8 * GB), "cgroup memory.max minus its use")


# ----- Windows and macOS (mocked) ------------------------------------------------------------------


class FakeKernel32:
    def __init__(self, available: int, ok: bool = True) -> None:
        self.available, self.ok = available, ok

    def GlobalMemoryStatusEx(self, pointer: Any) -> int:  # noqa: N802 - the Windows API name
        status = pointer._obj
        assert status.dwLength == ctypes.sizeof(jobs._MemoryStatusEx)
        status.ullTotalPhys, status.ullAvailPhys, status.ullAvailPageFile = 16 * GB, self.available, 40 * GB
        return 1 if self.ok else 0


def test_windows_reads_available_physical_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "_kernel32", lambda: FakeKernel32(int(6.5 * GB)))
    assert jobs.windows_available() == MemoryReading(int(6.5 * GB), "GlobalMemoryStatusEx")  # not the page file
    monkeypatch.setattr(jobs, "_kernel32", lambda: FakeKernel32(1, ok=False))
    assert jobs.windows_available() is None


def test_windows_reading_off_windows_is_none() -> None:
    if hasattr(ctypes, "windll"):
        pytest.skip("on Windows")
    assert jobs.windows_available() is None


VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               10000.
Pages active:                            200000.
Pages inactive:                          190000.
Pages speculative:                         5000.
Pages wired down:                         90000.
Swapouts:                                 12345.
"""


def test_macos_vm_stat(monkeypatch: pytest.MonkeyPatch) -> None:
    assert jobs.parse_vm_stat(VM_STAT) == 200_000 * 16384
    assert jobs.parse_vm_stat("nothing here") is None
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(args, 0, stdout=VM_STAT, stderr="")

    monkeypatch.setattr(jobs.subprocess, "run", run)
    assert jobs.macos_available() == MemoryReading(200_000 * 16384, "vm_stat free + inactive")
    assert calls == [["vm_stat"]]

    def missing(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(args[0])

    monkeypatch.setattr(jobs.subprocess, "run", missing)
    assert jobs.macos_available() is None


# ----- the CLI --------------------------------------------------------------------------------------


def fixed_choice(monkeypatch: pytest.MonkeyPatch, count: int = 3) -> JobsChoice:
    choice = JobsChoice(count, 4, PER_JOB_BYTES, MemoryReading(count * PER_JOB_BYTES + 1, "/proc/meminfo MemAvailable"))
    monkeypatch.setattr(cli, "choose_jobs", lambda: choice)
    return choice


@pytest.mark.parametrize("command", ["render", "storyboard", "lint", "thumbnail", "slides", "gallery"])
def test_every_jobs_option_takes_auto(command: str) -> None:
    args = cli.build_parser().parse_args([command, "--jobs", "auto"])
    assert args.jobs == "auto"
    assert cli.build_parser().parse_args([command, "-j", "3"]).jobs == 3


def test_cli_prints_the_choice(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fixed_choice(monkeypatch)
    seen: list[Any] = []
    monkeypatch.setattr(cli, "cmd_render", lambda args: seen.append(args.jobs) or 0)
    assert main(["render", str(make_project()), "--jobs", "auto"]) == 0
    out = capsys.readouterr().out
    assert seen == [3]
    assert out == "jobs: 3 (auto: 4.5 GB available (/proc/meminfo MemAvailable) / 1.5 GB per job = 3, 4 CPU cores)\n"


def test_json_document_has_the_choice(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    choice = fixed_choice(monkeypatch, count=2)
    assert main(["render", str(make_project()), "--scene", "nope", "--jobs", "auto", "--json"]) == 1
    captured = capsys.readouterr()
    doc = json.loads(captured.out)
    assert doc["error"]["message"].startswith("unknown scene(s): nope")  # failed before rendering
    assert doc["jobs"] == choice.to_json() and doc["jobs"]["jobs"] == 2
    assert "jobs: 2 (auto: " in captured.err
    assert main(["render", str(make_project()), "--scene", "nope", "--jobs", "2", "--json"]) == 1
    assert "jobs" not in json.loads(capsys.readouterr().out)  # only auto adds it


def test_jobs_must_be_a_number_or_auto(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["lint", "--jobs", "many"]) == 2
    assert "argument --jobs/-j: invalid value: 'many' (a whole number, or auto)" in capsys.readouterr().err
