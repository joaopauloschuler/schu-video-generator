"""Cleaning up a studio's disk (DESIGN.md §94.18): renders and exports are caches, versions are
not. A render (about 9 MB a minute, more with its listening mixes, sections and narration) can
always be made again from its version, and an export was downloaded by the browser when it was
made; so old ones go, by a fixed rule:

- **renders** of a session are kept for its current version, its first (A: the original), its
  starred versions, its last :data:`KEEP_VERSIONS` versions and the candidates of its newest
  variation batch; the others are removed. What is kept is then capped at :data:`CAP_BYTES` a
  session (the current, first and starred versions are never dropped by the cap);
- **exports** older than ``export_age`` seconds are removed (:data:`EXPORT_AGE` by itself, an
  hour when the person asks for a clean-up);
- other sessions of the studio keep only the renders of their current and starred versions.

Never removed: score versions, notes, hand-offs, proposals, variation candidates' texts, checks
(small reports agents and cards read) and ``session.json``. A file that cannot be removed (a
render being streamed, on Windows) is left for the next time.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from vidgen.errors import VidgenError
from vidgen.studio_app.session import SESSION_ID, StudioSession

#: Renders of this many most recent versions are kept (besides current, first, starred).
KEEP_VERSIONS = 8
#: At most this many bytes of renders a session (the newest and marked versions first).
CAP_BYTES = 1_000_000_000
#: Exports older than this (s) go by themselves; a clean-up asked for removes those older than an hour.
EXPORT_AGE = 24 * 3600
ASKED_EXPORT_AGE = 3600
#: The render key a render file's name starts with.
_KEY = re.compile(r"^([0-9a-f]{20})[.-]")


def _render_key(text: str) -> str | None:
    from vidgen.studio_app.app import render_key

    try:
        return render_key(yaml.safe_load(text))
    except yaml.YAMLError:
        return None


def _newest_batch_keys(folder: Path) -> list[str]:
    top = folder / "variations"
    if not top.is_dir():
        return []
    batches = sorted((p for p in top.iterdir() if re.match(r"^b\d{4}$", p.name)), key=lambda p: p.name)
    if not batches:
        return []
    try:
        doc = json.loads((batches[-1] / "batch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(i["key"]) for i in doc.get("items", []) if isinstance(i, dict) and i.get("key")]


def kept_keys(session: StudioSession, keep_versions: int = KEEP_VERSIONS, extra: Iterable[str] = ()) -> tuple[list[str], set[str]]:
    """The render keys a session keeps, most wanted first, and the ones the cap never drops
    (the current, first and starred versions', and ``extra``: the render just played)."""
    def keys(numbers: Iterable[int]) -> list[str]:
        out = []
        for number in numbers:
            try:
                key = _render_key(session.text(number))
            except (OSError, VidgenError):
                key = None
            if key is not None:
                out.append(key)
        return out

    versions = session.versions
    sure = ([session.current] if session.current is not None else []) + [v.number for v in versions[:1]]
    sure += [v.number for v in reversed(versions) if v.starred]
    recent = [v.number for v in reversed(versions)][:keep_versions]
    extra = list(extra)
    protected = set(keys(sure)) | set(extra)
    order: list[str] = []
    for key in [*extra, *keys(sure), *_newest_batch_keys(session.folder), *keys(recent)]:
        if key not in order:
            order.append(key)
    return order, protected


def _files_by_key(renders: Path) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    if not renders.is_dir():
        return out
    for path in renders.iterdir():
        m = _KEY.match(path.name)
        if m and path.is_file():
            out.setdefault(m[1], []).append(path)
    return out


def _remove(paths: Iterable[Path], tally: dict[str, int]) -> None:
    for path in paths:
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError:
            tally["busy"] += 1  # being streamed (Windows) or gone: the next clean-up
            continue
        tally["files"] += 1
        tally["bytes"] += size


def _size(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total


def clean_session(session: StudioSession, keep_versions: int = KEEP_VERSIONS, cap_bytes: int = CAP_BYTES,
                  export_age: float = EXPORT_AGE, now: float | None = None, extra: Iterable[str] = ()) -> dict[str, int]:
    """Remove a session's old renders and exports by the module's rule: ``{files, bytes,
    busy, kept_bytes}`` (what was removed, files that could not be, the renders left).
    ``extra``: render keys kept besides (the one just played)."""
    tally = {"files": 0, "bytes": 0, "busy": 0, "kept_bytes": 0}
    order, protected = kept_keys(session, keep_versions, extra)
    groups = _files_by_key(session.renders)
    _remove((p for key, paths in groups.items() if key not in order for p in paths), tally)
    used = 0
    for key in order:
        paths = groups.get(key, [])
        size = _size(paths)
        if key not in protected and used + size > cap_bytes:
            _remove(paths, tally)
            continue
        used += size
    tally["kept_bytes"] = used
    exports = session.folder / "exports"
    if exports.is_dir():
        limit = (time.time() if now is None else now) - export_age
        old = []
        for path in exports.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < limit:
                    old.append(path)
            except OSError:
                pass
        _remove(old, tally)
    return tally


def clean_studio(studio: Path, open_id: str | None, export_age: float = EXPORT_AGE) -> dict[str, int]:
    """Clean the studio's other sessions (renders of their current and starred versions kept,
    old exports removed): the totals."""
    total = {"files": 0, "bytes": 0, "busy": 0, "kept_bytes": 0, "sessions": 0}
    folder = studio / "sessions"
    if not folder.is_dir():
        return total
    for path in sorted(folder.iterdir()):
        if not SESSION_ID.match(path.name) or path.name == open_id:
            continue
        try:
            session = StudioSession.open(studio, path.name)
            one = clean_session(session, keep_versions=0, export_age=export_age)
        except (OSError, ValueError, KeyError, TypeError, VidgenError):
            continue  # a broken session folder is left alone
        total["sessions"] += 1
        for k in ("files", "bytes", "busy", "kept_bytes"):
            total[k] += one[k]
    return total


def disk_use(studio: Path, session: StudioSession | None) -> dict[str, Any]:
    """Bytes of renders and exports of the open session and of the whole studio folder."""

    def size_of(folder: Path, sub: str) -> int:
        top = folder / sub
        return _size(p for p in top.iterdir() if p.is_file()) if top.is_dir() else 0

    out: dict[str, Any] = {"session_renders": 0, "session_exports": 0, "studio_renders": 0, "studio_exports": 0}
    if session is not None:
        out["session_renders"] = size_of(session.folder, "renders")
        out["session_exports"] = size_of(session.folder, "exports")
    sessions = studio / "sessions"
    if sessions.is_dir():
        for path in sessions.iterdir():
            if SESSION_ID.match(path.name):
                out["studio_renders"] += size_of(path, "renders")
                out["studio_exports"] += size_of(path, "exports")
    return out
