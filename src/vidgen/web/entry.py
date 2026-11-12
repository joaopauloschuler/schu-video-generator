"""The file a ``web`` scene names (``page:`` or ``script:``) and its checks (DESIGN.md §118.2).

No browser here: ``vidgen validate`` and the render fingerprint use these.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from vidgen.errors import VidgenError

#: Suffixes each kind of entry may have.
SUFFIXES: dict[str, tuple[str, ...]] = {"page": (".html", ".htm"), "script": (".js", ".mjs")}


@dataclass(frozen=True)
class WebEntry:
    """``kind`` (``page`` or ``script``) and ``path``, relative to the project folder as written."""

    kind: Literal["page", "script"]
    path: str

    @property
    def posix(self) -> str:
        """The path with forward slashes, as the page's URL has it."""
        return PurePosixPath(*Path(self.path).parts).as_posix()


def entry_of(params: Any) -> WebEntry:
    """The entry of a ``web`` scene's params (a model or a mapping); exactly one is set."""
    get = params.get if isinstance(params, Mapping) else lambda key: getattr(params, key, None)
    page, script = get("page"), get("script")
    if (page is None) == (script is None):
        raise VidgenError("a web scene needs exactly one of page: (an HTML file) or script: (a JavaScript module)")
    return WebEntry("page", page) if page is not None else WebEntry("script", script)


def inside(root: Path, rel: str) -> Path | None:
    """``root / rel`` resolved, or ``None`` when it lies outside ``root``."""
    base = root.resolve()
    path = (base / rel).resolve()
    return path if path.is_relative_to(base) else None


def entry_problems(root: Path, entry: WebEntry) -> list[str]:
    """``vidgen validate``'s problems with the entry, each starting with its param
    (``"page: file not found: extensions/gears.html"``)."""
    path = inside(root, entry.path)
    if Path(entry.path).is_absolute() or path is None:
        return [f"{entry.kind}: must be a path inside the project folder, got {entry.path}"]
    if not path.is_file():
        return [f"{entry.kind}: file not found: {entry.path} (looked for {path})"]
    if path.suffix.lower() not in SUFFIXES[entry.kind]:
        return [f"{entry.kind}: expected a {' or '.join(SUFFIXES[entry.kind])} file, got {entry.path}"]
    return []


def web_entry_problems(root: Path, params: Any) -> list[str]:
    """:func:`entry_problems` of a ``web`` scene's params (``vidgen validate``)."""
    return entry_problems(root, entry_of(params))


def entry_path(root: Path, entry: WebEntry, scene_id: str) -> Path:
    """The entry's file, or a :class:`VidgenError` naming the scene and the problem."""
    problems = entry_problems(root, entry)
    if problems:
        raise VidgenError(f"scene '{scene_id}': {problems[0]}")
    return inside(root, entry.path)  # type: ignore[return-value]


def entry_digest(root: Path, params: Any) -> dict[str, Any]:
    """What the render fingerprint takes from a ``web`` scene: its entry and the file's
    SHA-256 (``None`` when it cannot be read), so an edit to the file renders the scene again."""
    try:
        entry = entry_of(params)
    except VidgenError:
        return {}
    path = inside(root, entry.path)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path is not None else None
    except OSError:
        digest = None
    return {"kind": entry.kind, "path": entry.posix, "sha256": digest}


__all__ = ["SUFFIXES", "WebEntry", "entry_digest", "entry_of", "entry_path", "entry_problems", "inside", "web_entry_problems"]
