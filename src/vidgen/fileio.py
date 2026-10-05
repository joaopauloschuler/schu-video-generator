"""Replacing output files safely, also on Windows.

On Windows a file that another program has open (a video player showing the last render, an
editor, a virus scanner looking at a new file) usually cannot be replaced or deleted:
``os.replace`` raises ``PermissionError``. :func:`replace_file` retries briefly (scanners let go
quickly) and then raises a :class:`VidgenError` that says what to do.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from vidgen.errors import VidgenError

#: Waits (seconds) between attempts when the target is locked; about 1.5 s in total.
RETRY_DELAYS: tuple[float, ...] = (0.1, 0.2, 0.4, 0.8)


def locked_message(path: Path, exc: OSError) -> str:
    """The error shown when ``path`` cannot be written because another program holds it."""
    reason = exc.strerror or str(exc)
    return f"cannot write {path} ({reason}); is it open in another program, e.g. a video player? Close it and try again"


def replace_file(src: Path, dst: Path) -> None:
    """``os.replace(src, dst)``, retried for a moment while ``dst`` is locked.

    Raises :class:`VidgenError` if ``dst`` stays locked; ``src`` is left in place then.
    """
    for delay in (*RETRY_DELAYS, None):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:
            if delay is None:
                raise VidgenError(locked_message(dst, exc)) from None
            time.sleep(delay)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to a temporary file next to ``path``, then replace ``path`` with it.

    ``path`` is either left untouched or fully written; the temporary file is removed on failure.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        replace_file(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_text_atomic(path: Path, text: str) -> None:
    """:func:`write_bytes_atomic` for UTF-8 text (``\\n`` line endings on every platform)."""
    write_bytes_atomic(path, text.encode("utf-8"))


def remove_file(path: Path) -> None:
    """Delete ``path`` if it exists; a locked file becomes a :class:`VidgenError`."""
    for delay in (*RETRY_DELAYS, None):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError as exc:
            if delay is None:
                raise VidgenError(locked_message(path, exc)) from None
            time.sleep(delay)
