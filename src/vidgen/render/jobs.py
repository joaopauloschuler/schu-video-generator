"""``--jobs auto``: how many scenes to render in parallel on this machine (DESIGN.md §70).

``jobs = min(available physical memory // PER_JOB_BYTES, CPU cores)``, at least 1. "Available"
is the memory the system can give without swapping (Linux ``MemAvailable``, or less when a cgroup
limit leaves less; Windows ``ullAvailPhys``; macOS free + inactive pages); swap is never counted.
Read with the standard library only (``/proc``, ``ctypes``, ``vm_stat``).
"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Memory one scene render may use (worker + ffmpeg): about twice the largest peak measured,
#: 0.83 GB for a cartoon scene at 1920x1080 (0.30 GB at the 640x360 preview; HANDOFF Step 117).
PER_JOB_BYTES = 1_500_000_000
#: The ``--jobs`` value that asks for this choice.
AUTO = "auto"


@dataclass(frozen=True)
class MemoryReading:
    """Available physical memory in bytes and where the figure was read (for the reason)."""

    available_bytes: int
    source: str


@dataclass(frozen=True)
class JobsChoice:
    """What ``--jobs auto`` chose (``jobs``) and the figures it chose from."""

    jobs: int
    cores: int
    per_job_bytes: int
    memory: MemoryReading | None

    @property
    def reason(self) -> str:
        """``3.2 GB available (/proc/meminfo MemAvailable) / 1.5 GB per job = 2, 4 CPU cores``."""
        if self.memory is None:
            return f"available memory unknown on {sys.platform}; {self.cores} CPU cores"
        by_memory = self.memory.available_bytes // self.per_job_bytes
        return (
            f"{_gb(self.memory.available_bytes)} available ({self.memory.source}) / "
            f"{_gb(self.per_job_bytes)} per job = {by_memory}, {self.cores} CPU core{'s' if self.cores != 1 else ''}"
        )

    def to_json(self) -> dict[str, Any]:
        """The ``jobs`` entry of a ``--json`` document."""
        return {
            "requested": AUTO,
            "jobs": self.jobs,
            "cores": self.cores,
            "per_job_bytes": self.per_job_bytes,
            "available_bytes": None if self.memory is None else self.memory.available_bytes,
            "memory_source": None if self.memory is None else self.memory.source,
            "reason": self.reason,
        }


def jobs_for(available_bytes: int | None, cores: int, per_job_bytes: int = PER_JOB_BYTES) -> int:
    """``min(available_bytes // per_job_bytes, cores)``, at least 1; 1 when the memory is unknown."""
    if available_bytes is None:
        return 1
    return max(1, min(available_bytes // per_job_bytes, cores))


def choose_jobs(per_job_bytes: int = PER_JOB_BYTES) -> JobsChoice:
    """Read this machine's available memory and CPU cores and choose the number of jobs."""
    memory = available_memory()
    cores = cpu_cores()
    available_bytes = None if memory is None else memory.available_bytes
    return JobsChoice(jobs_for(available_bytes, cores, per_job_bytes), cores, per_job_bytes, memory)


def cpu_cores() -> int:
    """CPU cores this process may run on (its affinity where the OS tells it), at least 1."""
    if hasattr(os, "sched_getaffinity"):
        return max(1, len(os.sched_getaffinity(0)))
    return os.cpu_count() or 1


def available_memory(platform: str | None = None) -> MemoryReading | None:
    """Available physical memory on ``platform`` (default: this one, ``sys.platform``); ``None``
    when it cannot be read."""
    platform = platform or sys.platform
    if platform.startswith("linux"):
        return linux_available()
    if platform == "win32":
        return windows_available()
    if platform == "darwin":
        return macos_available()
    return None


# ----- Linux -------------------------------------------------------------------------------------


def linux_available(root: Path = Path("/")) -> MemoryReading | None:
    """``MemAvailable`` of ``/proc/meminfo``, or the cgroup headroom when that is smaller
    (``root``: where ``/proc`` and ``/sys`` are, for tests)."""
    try:
        meminfo = (root / "proc" / "meminfo").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^MemAvailable:\s+(\d+) kB", meminfo, re.MULTILINE)
    if match is None:
        return None
    reading = MemoryReading(int(match.group(1)) * 1024, "/proc/meminfo MemAvailable")
    limited = cgroup_headroom(root)
    if limited is not None and limited.available_bytes < reading.available_bytes:
        return limited
    return reading


def cgroup_headroom(root: Path = Path("/")) -> MemoryReading | None:
    """The smallest ``limit - working set`` of this process's memory cgroup and its ancestors
    (cgroup v2 ``memory.max``, v1 ``memory.limit_in_bytes``); ``None`` without a limit. The
    working set is the usage minus inactive file cache, which the kernel reclaims under the limit."""
    best: MemoryReading | None = None
    for folder, version in _cgroup_folders(root):
        limit_file, usage_file, inactive_key = (
            ("memory.max", "memory.current", "inactive_file") if version == 2
            else ("memory.limit_in_bytes", "memory.usage_in_bytes", "total_inactive_file")
        )
        limit = _read_int(folder / limit_file)
        usage = _read_int(folder / usage_file)
        if limit is None or usage is None:
            continue
        working_set = max(0, usage - _stat_value(folder / "memory.stat", inactive_key))
        headroom = max(0, limit - working_set)
        if best is None or headroom < best.available_bytes:
            best = MemoryReading(headroom, f"cgroup {limit_file} minus its use")
    return best


def _cgroup_folders(root: Path) -> list[tuple[Path, int]]:
    """This process's memory cgroup folders, leaf first then each ancestor, with their version."""
    try:
        lines = (root / "proc" / "self" / "cgroup").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    folders: list[tuple[Path, int]] = []
    for line in lines:
        _, controllers, path = (line.split(":", 2) + ["", ""])[:3]
        if controllers == "":
            base, version = root / "sys" / "fs" / "cgroup", 2
        elif "memory" in controllers.split(","):
            base, version = root / "sys" / "fs" / "cgroup" / "memory", 1
        else:
            continue
        parts = [p for p in path.strip("/").split("/") if p]
        for depth in range(len(parts), -1, -1):
            folder = base.joinpath(*parts[:depth])
            if folder.is_dir():
                folders.append((folder, version))
    return folders


def _read_int(path: Path) -> int | None:
    """The integer in a cgroup file; ``None`` if missing or ``max`` (no limit)."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def _stat_value(path: Path, key: str) -> int:
    """``key``'s value in a ``memory.stat`` file (0 if absent)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    match = re.search(rf"^{key} (\d+)$", text, re.MULTILINE)
    return int(match.group(1)) if match else 0


# ----- Windows and macOS ---------------------------------------------------------------------------


class _MemoryStatusEx(ctypes.Structure):
    """``MEMORYSTATUSEX`` of the Windows API."""

    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _kernel32() -> Any:
    return ctypes.windll.kernel32  # type: ignore[attr-defined]  # Windows only


def windows_available() -> MemoryReading | None:
    """``ullAvailPhys`` of ``GlobalMemoryStatusEx`` (physical memory only, not the page file)."""
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    try:
        ok = _kernel32().GlobalMemoryStatusEx(ctypes.byref(status))
    except (AttributeError, OSError):
        return None
    return MemoryReading(int(status.ullAvailPhys), "GlobalMemoryStatusEx") if ok else None


def macos_available() -> MemoryReading | None:
    """Free + inactive pages of ``vm_stat`` (as ``psutil`` counts available memory)."""
    try:
        text = subprocess.run(["vm_stat"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    available = parse_vm_stat(text)
    return None if available is None else MemoryReading(available, "vm_stat free + inactive")


def parse_vm_stat(text: str) -> int | None:
    """Bytes of free + inactive pages in ``vm_stat`` output; ``None`` if it does not parse."""
    page = re.search(r"page size of (\d+) bytes", text)
    free = re.search(r"^Pages free:\s+(\d+)", text, re.MULTILINE)
    inactive = re.search(r"^Pages inactive:\s+(\d+)", text, re.MULTILINE)
    if page is None or free is None or inactive is None:
        return None
    return (int(free.group(1)) + int(inactive.group(1))) * int(page.group(1))


def _gb(size_bytes: int) -> str:
    return f"{size_bytes / 1e9:.1f} GB"
