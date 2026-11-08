"""The small process beside a quick tunnel: cleans up when vidgen dies without closing it (DESIGN.md §115.5).

Run as a file, standard library only: ``python -I -S host_watcher.py FOLDER [ALIVE_FD]``.

vidgen holds the only write end of this process's stdin. It sends ``tunnel <pid>`` once cloudflared
has started, ``tunnel-stopped`` when it stopped it, and ``disarm`` when nothing is left to clean up.
When stdin ends without ``disarm``, vidgen is gone, however it ended (SIGKILL included): this
process stops that cloudflared's process group and deletes ``FOLDER``.

``ALIVE_FD`` (POSIX) is the read end of a pipe whose only write end cloudflared inherited: it
reads end-of-file once cloudflared is gone. Without that check a recycled process number could
lead this process to signal a stranger. On Windows there is no ``ALIVE_FD``: a Job Object stops
cloudflared there (``host_guard``), and this process only deletes the folder.
"""

from __future__ import annotations

import os
import select
import shutil
import signal
import sys
import time

_STOP_WAIT_SECONDS = 5.0
_DELETE_ATTEMPTS = 5
_DELETE_RETRY_SECONDS = 0.2


def _tunnel_is_gone(alive_fd: int) -> bool:
    return bool(select.select([alive_fd], [], [], 0)[0])


def _stop_tunnel(pid: int, alive_fd: int) -> None:
    """SIGTERM to cloudflared's process group, SIGKILL after a wait; only while it is still alive."""
    if _tunnel_is_gone(alive_fd):
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + _STOP_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _tunnel_is_gone(alive_fd):
            return
        time.sleep(0.05)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass


def _delete_folder(folder: str) -> None:
    for attempt in range(_DELETE_ATTEMPTS):
        try:
            shutil.rmtree(folder)
            return
        except FileNotFoundError:
            return
        except OSError:   # Windows: a file still open for a moment
            if attempt < _DELETE_ATTEMPTS - 1:
                time.sleep(_DELETE_RETRY_SECONDS)


def main(arguments: list[str]) -> int:
    """Wait for vidgen's lines on stdin; clean up when stdin ends without ``disarm``."""
    folder = arguments[0]
    alive_fd = int(arguments[1]) if len(arguments) > 1 else None
    for name in ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is not None:
            signal.signal(signum, signal.SIG_IGN)   # a signal for vidgen must not end its cleaner
    tunnel_pid: int | None = None
    for line in sys.stdin:
        word = line.strip()
        if word == "disarm":
            return 0
        if word == "tunnel-stopped":
            tunnel_pid = None
        elif word.startswith("tunnel "):
            tunnel_pid = int(word.split()[1])
    if tunnel_pid is not None and alive_fd is not None:
        _stop_tunnel(tunnel_pid, alive_fd)
    _delete_folder(folder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
