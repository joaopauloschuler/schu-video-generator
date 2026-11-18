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


def served_root(project: Any) -> Path:
    """The folder a ``web`` scene's page is served from (DESIGN.md §123.16): the project folder,
    or the folder ``web_root:`` names (relative to the project), which must hold the project folder.
    A wrong ``web_root`` is a :class:`VidgenError`."""
    rel = project.config.web_root
    if rel is None:
        return project.root
    folder = (project.root / rel).resolve()
    if not folder.is_dir():
        raise VidgenError(f"web_root: folder not found: {rel} (looked for {folder})")
    if not project.root.resolve().is_relative_to(folder):
        raise VidgenError(f"web_root: {rel} must be the project folder or a folder that holds it; {folder} does not hold {project.root.resolve()}")
    return folder


def served_params(project: Any, params: Any) -> Any:
    """``params`` (a model or a mapping) with its ``page:`` or ``script:``, written from the project
    folder, made a path from :func:`served_root`; ``params`` itself without ``web_root:``. A path
    that leaves the served folder becomes absolute, which :func:`entry_problems` refuses."""
    if project.config.web_root is None:
        return params
    entry = entry_of(params)
    target = (project.root / entry.path).resolve()
    served = served_root(project)
    rel = target.relative_to(served).as_posix() if target.is_relative_to(served) else str(target)
    return params.model_copy(update={entry.kind: rel}) if hasattr(params, "model_copy") else {**params, entry.kind: rel}


def served_entry_problems(project: Any, params: Any) -> list[str]:
    """:func:`web_entry_problems` of a ``web`` scene in ``project``: with ``web_root:``, the page or
    script (written from the project folder) must lie inside the folder it names."""
    if project.config.web_root is None:
        return web_entry_problems(project.root, params)
    entry = entry_of(params)
    try:
        served = served_root(project)
    except VidgenError as exc:
        return [f"{entry.kind}: {exc}"]
    if Path(entry.path).is_absolute() or not (project.root / entry.path).resolve().is_relative_to(served):
        return [f"{entry.kind}: must be a path inside the web_root folder ({served}), got {entry.path}"]
    return entry_problems(served, entry_of(served_params(project, params)))


def served_prefix(project: Any) -> str:
    """The project folder's URL path on its pages (``first-light/``; empty without ``web_root:``)."""
    rel = project.root.resolve().relative_to(served_root(project).resolve()).as_posix()
    return "" if rel == "." else rel + "/"


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


def is_web_type(name: str) -> bool:
    """True when the scene type ``name`` is ``web`` or a registered type whose class subclasses
    the built-in ``Web`` scene (an extension's ``class WebCut(Web)``): such a scene shows a page
    too, so its script and the files its page loaded are render inputs (DESIGN.md §120.1).

    Told by the class's bases, so nothing is imported here. A type the registry does not know
    (no project is active) counts only when it is ``web`` itself."""
    from vidgen import registry

    entry = registry.find(name)
    if entry is None:
        return name == "web"
    return any(base.__module__ == "vidgen.scenes.web" and base.__name__ == "Web" for base in entry.cls.__mro__)


__all__ = ["SUFFIXES", "WebEntry", "entry_digest", "entry_of", "entry_path", "entry_problems", "inside", "is_web_type", "served_entry_problems",
           "served_params", "served_prefix", "served_root", "web_entry_problems"]
