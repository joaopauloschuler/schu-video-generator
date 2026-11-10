"""What cleans up a quick tunnel when vidgen itself does not get to (DESIGN.md §115.5).

- Termination signals (SIGTERM, SIGHUP, Windows SIGBREAK) close the open hosts properly, then end
  vidgen. :func:`track_host` installs the handlers only from the main thread and only over the
  default disposition, so handlers someone already set (and a ``nohup``'s ignored SIGHUP) stay.
- :class:`HostGuard` covers a death no handler can see. A small watcher process
  (``host_watcher.py``) notices that vidgen is gone and stops cloudflared and deletes the folder;
  on Windows a Job Object with kill-on-close stops cloudflared and the watcher deletes the folder.
- The share folder holds a locked marker file. The operating system releases the lock when its
  owner ends, so :func:`sweep_stale_shares`, called at the next open, can tell a dead host's
  folder from a running host's without trusting a process number.
"""

from __future__ import annotations

import ctypes
import logging
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
from collections.abc import Sequence
from ctypes import wintypes
from pathlib import Path
from typing import Any, Protocol

from vidgen.errors import VidgenError

log = logging.getLogger("vidgen.videogen")

#: The name every share folder starts with.
SHARE_PREFIX = "vidgen-share-"
#: The marker in a share folder, locked by the host that made it (the share server never serves it).
LOCK_NAME = ".vidgen-host.lock"
WATCHER_SCRIPT = Path(__file__).with_name("host_watcher.py")
_WATCHER_EXIT_WAIT_SECONDS = 3.0
_TERMINATION_SIGNALS = ("SIGTERM", "SIGHUP", "SIGBREAK")
_FOLDER_ATTEMPTS = 3
_CREATE_NO_WINDOW = 0x08000000   # subprocess.CREATE_NO_WINDOW exists only on Windows


# -- the share folder and its lock ---------------------------------------------------------------
def _try_lock(fd: int) -> bool:
    """Take the lock of the open file ``fd`` without waiting; whether it was free."""
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def make_share_folder() -> tuple[Path, int]:
    """A new private temporary folder with its marker locked; returns it and the marker's open
    file (keep it open while the host runs, :func:`release_share_folder` releases it)."""
    for _ in range(_FOLDER_ATTEMPTS):
        folder = Path(tempfile.mkdtemp(prefix=SHARE_PREFIX))
        fd = os.open(folder / LOCK_NAME, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
        if _try_lock(fd):
            return folder, fd
        os.close(fd)   # another vidgen's sweep took this new folder for a dead host's and deletes it
    raise VidgenError(f"could not lock a new temporary folder in {tempfile.gettempdir()}")


def release_share_folder(fd: int | None) -> None:
    """Close the marker of a share folder (Windows cannot delete a file that is open)."""
    if fd is not None:
        os.close(fd)


def _delete_abandoned(folder: Path, marker_fd: int) -> None:
    """Delete a share folder whose marker lock this process holds; the marker goes last, so that
    a host cannot start using a folder this has begun to empty."""
    marker = folder / LOCK_NAME
    try:
        for entry in folder.iterdir():
            if entry.name != LOCK_NAME:
                entry.unlink()
        try:
            marker.unlink()
        except PermissionError:   # Windows: not while it is open
            os.close(marker_fd)
            marker_fd = -1
            marker.unlink()
    finally:
        if marker_fd != -1:
            os.close(marker_fd)
    folder.rmdir()


def _sweep_one(folder: Path) -> bool:
    """Delete ``folder`` if it is a share folder of ours whose host is gone; whether it did."""
    try:
        info = folder.lstat()
        if not stat.S_ISDIR(info.st_mode) or (hasattr(os, "getuid") and info.st_uid != os.getuid()):
            return False
        # No O_CREAT: a folder without the marker (an older vidgen's) is left alone.
        fd = os.open(folder / LOCK_NAME, os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return False
    if not _try_lock(fd):
        os.close(fd)
        return False
    try:
        _delete_abandoned(folder, fd)
    except OSError:
        return False
    return True


def sweep_stale_shares(temp_root: Path | None = None) -> list[Path]:
    """Delete the share folders in ``temp_root`` (default: the system's temporary folder) left by
    hosts that are gone. A folder whose marker is still locked (a running host) or that has no
    marker is not touched. Returns the folders deleted."""
    root = Path(temp_root) if temp_root is not None else Path(tempfile.gettempdir())
    try:
        candidates = sorted(root.glob(f"{SHARE_PREFIX}*"))
    except OSError:
        return []
    return [folder for folder in candidates if _sweep_one(folder)]


# -- Windows: a job that stops cloudflared when vidgen's handle to it closes --------------------
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


class _BasicLimits(ctypes.Structure):
    """``JOBOBJECT_BASIC_LIMIT_INFORMATION``."""

    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    """``IO_COUNTERS``."""

    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _ExtendedLimits(ctypes.Structure):
    """``JOBOBJECT_EXTENDED_LIMIT_INFORMATION``."""

    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32() -> Any:
    """kernel32 with the signatures of the calls below (without them a handle is cut to 32 bits)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)   # type: ignore[attr-defined]  # Windows only
    kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _job_for_process(process: subprocess.Popen[Any]) -> Any:
    """A kill-on-close Job Object holding ``process``; its handle (``None`` when it could not be
    made: then only the normal close and the sweep are left, a warning says so)."""
    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        log.warning("quick tunnel: could not create a Windows Job Object; cloudflared would outlive a killed vidgen")
        return None
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    set_ok = kernel32.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits))
    if not set_ok or not kernel32.AssignProcessToJobObject(job, int(process._handle)):   # type: ignore[attr-defined]  # Windows only
        log.warning("quick tunnel: could not put cloudflared in a Windows Job Object; it would outlive a killed vidgen")
        kernel32.CloseHandle(job)
        return None
    return job


# -- the watcher process ----------------------------------------------------------------------------
class HostGuard:
    """One host's protection against vidgen dying: the watcher process and, on Windows, the job."""

    def __init__(self, folder: Path) -> None:
        self._watcher: subprocess.Popen[str] | None = None
        self._alive_write_fd: int | None = None
        self._job: Any = None
        self._start_watcher(folder)

    @property
    def watcher_pid(self) -> int | None:
        """The watcher's process number (``None`` when it could not be started)."""
        return self._watcher.pid if self._watcher is not None else None

    def _start_watcher(self, folder: Path) -> None:
        command = [sys.executable or "", "-I", "-S", str(WATCHER_SCRIPT), str(folder)]
        options: dict[str, Any] = {}
        read_fd: int | None = None
        try:
            if os.name == "nt":
                options["creationflags"] = _CREATE_NO_WINDOW
            else:
                read_fd, self._alive_write_fd = os.pipe()
                command.append(str(read_fd))
                options.update(start_new_session=True, pass_fds=(read_fd,))
            # stdout / stderr: never vidgen's, or whoever reads them (MCP) would wait for this process too.
            self._watcher = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=folder.parent, text=True, encoding="utf-8", **options,
            )
        except OSError as exc:
            log.warning("quick tunnel: could not start the cleanup watcher (%s); a killed vidgen would leave cloudflared and the temporary copies behind", exc)
        finally:
            if read_fd is not None:
                os.close(read_fd)

    def tunnel_fds(self) -> Sequence[int]:
        """The file descriptors cloudflared must inherit (see ``host_watcher``)."""
        return () if self._alive_write_fd is None else (self._alive_write_fd,)

    def adopt(self, process: subprocess.Popen[Any]) -> None:
        """Protect the just-started cloudflared: the watcher learns its process group, a job holds it on Windows."""
        if os.name == "nt":
            self._job = _job_for_process(process)
        else:
            self._send(f"tunnel {process.pid}")
            self._close_alive_write_end()

    def tunnel_stopped(self) -> None:
        """cloudflared is stopped: nothing may signal its process number any more."""
        self._send("tunnel-stopped")
        self._close_job()

    def finish(self, *, disarm: bool) -> None:
        """End the watcher: ``disarm`` when nothing is left for it to do; otherwise it cleans up what remains now."""
        self._close_alive_write_end()
        if self._watcher is None:
            return
        if disarm:
            self._send("disarm")
        assert self._watcher.stdin is not None
        try:
            self._watcher.stdin.close()
        except (OSError, ValueError):   # it is gone
            pass
        try:
            self._watcher.wait(_WATCHER_EXIT_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            pass   # it ends by itself, its cleanup still running
        self._watcher = None

    def _send(self, line: str) -> None:
        if self._watcher is None or self._watcher.stdin is None:
            return
        try:
            self._watcher.stdin.write(line + "\n")
            self._watcher.stdin.flush()
        except (OSError, ValueError):   # the watcher is gone; the normal close still works
            log.warning("quick tunnel: the cleanup watcher stopped early")

    def _close_alive_write_end(self) -> None:
        if self._alive_write_fd is not None:
            os.close(self._alive_write_fd)
            self._alive_write_fd = None

    def _close_job(self) -> None:
        if self._job is not None:
            _kernel32().CloseHandle(self._job)
            self._job = None


# -- termination signals ----------------------------------------------------------------------------
class _ClosableHost(Protocol):
    def close(self, reason: str) -> None: ...


_registry_lock = threading.RLock()   # an RLock: the signal handler may interrupt a holder in the main thread
_open_hosts: dict[int, _ClosableHost] = {}
_installed_signals: set[int] = set()


def _on_termination(signum: int, frame: Any) -> None:
    """Close the open hosts, then end vidgen (exit status 128 + the signal), running ``finally`` blocks and ``atexit``."""
    with _registry_lock:
        hosts = list(_open_hosts.values())
    if not hosts:   # only a close outside the main thread left this handler installed
        signal.signal(signum, signal.SIG_DFL)
        signal.raise_signal(signum)
        return
    name = signal.Signals(signum).name
    for host in hosts:
        host.close(f"terminated ({name})")
    raise SystemExit(128 + signum)


def _install_handlers() -> None:
    """Handle the termination signals that still have the default disposition (main thread only)."""
    if threading.current_thread() is not threading.main_thread():
        return
    with _registry_lock:
        for name in _TERMINATION_SIGNALS:
            signum = getattr(signal, name, None)
            if signum is None or signum in _installed_signals:
                continue
            if signal.getsignal(signum) == signal.SIG_DFL:
                signal.signal(signum, _on_termination)
                _installed_signals.add(signum)


def _restore_handlers() -> None:
    """Put back the default disposition where the handler is still this module's (main thread only)."""
    if threading.current_thread() is not threading.main_thread():
        return
    with _registry_lock:
        for signum in _installed_signals:
            if signal.getsignal(signum) == _on_termination:
                signal.signal(signum, signal.SIG_DFL)
        _installed_signals.clear()


def track_host(host: _ClosableHost) -> None:
    """``host`` is opening: a termination signal now closes it."""
    with _registry_lock:
        _open_hosts[id(host)] = host
    _install_handlers()


def untrack_host(host: _ClosableHost) -> None:
    """``host`` is closed: the handlers go away with the last open host."""
    with _registry_lock:
        _open_hosts.pop(id(host), None)
        is_last = not _open_hosts
    if is_last:
        _restore_handlers()
