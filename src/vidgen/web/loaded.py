"""The files a ``web`` scene's page loaded, as recorded beside its clip (DESIGN.md §118.10).

``WebPage`` notes every file it serves (a project file, or one of vidgen's under ``__vidgen__/``)
with its SHA-256, and a project file that was asked for but missing as ``None``. The clip's
record keeps that map; the clip is drawn again and the render fingerprint changes when any of
those files now differs. No browser here: the fingerprint uses this module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from vidgen.web.entry import inside

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
#: The URL path prefix of vidgen's own files (not project paths).
VIDGEN_PREFIX = "__vidgen__/"
#: vidgen's files a page may load, by their path after :data:`VIDGEN_PREFIX`: the bundled
#: three.js (``three/``) and the bundled fonts (``fonts/<family folder>/<file>``).
THREE_FILES: tuple[str, ...] = ("three.module.js", "three.core.js")
FONT_SUFFIXES: tuple[str, ...] = (".ttf", ".otf")


def vidgen_file(rel: str) -> Path | None:
    """The file of vidgen's that ``__vidgen__/<rel>`` names, or ``None``."""
    folder, _, name = rel.partition("/")
    if folder == "three" and name in THREE_FILES:
        return _DATA_DIR / "three" / name
    if folder == "fonts" and Path(name).suffix.lower() in FONT_SUFFIXES:
        path = inside(_DATA_DIR / "fonts", name)
        return path if path is not None and path.is_file() else None
    return None


def served_file(root: Path, rel: str) -> Path | None:
    """The file a request for ``rel`` is answered from: vidgen's (``__vidgen__/...``) or the
    project folder's; ``None`` when there is none (outside the folder, or not vidgen's)."""
    if rel.startswith(VIDGEN_PREFIX):
        return vidgen_file(rel.removeprefix(VIDGEN_PREFIX))
    return inside(root, rel)


def file_sha(path: Path | None) -> str | None:
    """The SHA-256 of the file at ``path``, or ``None`` when it is not a readable file."""
    if path is None:
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def current_loaded(root: Path, paths: Iterable[str]) -> dict[str, str | None]:
    """Each served path -> the SHA-256 of its file now (``None``: missing)."""
    return {rel: file_sha(served_file(root, rel)) for rel in sorted(set(paths))}


def record_path(folder: Path, scene_id: str) -> Path:
    """The record of a scene's clip in ``folder`` (``<render_dir>/web``): ``<scene_id>.json``."""
    return folder / f"{scene_id}.json"


def read_record(path: Path) -> dict[str, Any] | None:
    """A clip's record (``{key, inputs, loaded}``), or ``None`` when missing or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def recorded_loaded(path: Path) -> dict[str, str | None]:
    """The ``loaded`` map of the record at ``path`` (empty without one)."""
    record = read_record(path)
    loaded = record.get("loaded") if record is not None else None
    return {str(k): v for k, v in loaded.items()} if isinstance(loaded, dict) else {}


__all__ = ["FONT_SUFFIXES", "THREE_FILES", "VIDGEN_PREFIX", "current_loaded", "file_sha", "read_record", "record_path",
           "recorded_loaded", "served_file", "vidgen_file"]
