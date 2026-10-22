"""Studio sessions on disk (DESIGN.md §94.3): one folder per piece being worked on, holding every
version of its score file as written (comments kept), the session's facts in ``session.json``
and the render cache. Versions are never changed once written; a new edit is a new version.

Layout (``<studio>`` is the project's ``build/studio``, or ``studio`` in vidgen's cache folder)::

    <studio>/open.json                      the running studio: url, session, pid (for MCP, §94.8)
    <studio>/sessions/<id>/session.json     facts and the version list
    <studio>/sessions/<id>/versions/v0001.yaml
    <studio>/sessions/<id>/renders/<key>.wav, <key>.json, <key>-<section>.wav
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.fileio import remove_file, write_text_atomic

#: ``session.json``'s ``format`` (bump when its meaning changes).
SESSION_FORMAT = 1
#: The marker file a running studio writes in the studio folder.
OPEN_FILE = "open.json"
#: A session id: ``YYYYMMDD-HHMMSS-xxxx``.
SESSION_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")


def studio_dir(project_root: Path | None) -> Path:
    """Where the studio keeps its sessions: ``<project>/build/studio`` for a project, else
    ``studio`` in vidgen's cache folder (``VIDGEN_CACHE_DIR``, ``%LOCALAPPDATA%\\vidgen``...)."""
    if project_root is not None:
        return project_root / "build" / "studio"
    from vidgen.soundfont import cache_dir

    return cache_dir() / "studio"


def find_project_root(project: str | None, cwd: Path) -> Path | None:
    """The project folder ``vidgen studio PROJECT`` works in: ``project`` (a folder or a config
    file; :class:`VidgenError` if it is neither), else ``cwd`` when it holds a ``video.yaml``,
    else ``None`` (no project: sessions go to the cache folder). The config is not read."""
    from vidgen.project import CONFIG_NAMES, find_config_file

    if project is not None:
        return find_config_file(Path(project)).resolve().parent
    if any((cwd / name).is_file() for name in CONFIG_NAMES):
        return cwd.resolve()
    return None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass(frozen=True)
class Version:
    """One version of the session's score. ``origin``: ``preset`` (a built-in bed's template),
    ``text`` (a score given as text), later ``edit``, ``agent``, ``variation`` (§94.4)."""

    number: int
    parent: int | None
    origin: str
    label: str
    created: str


class StudioSession:
    """A session folder: its facts, versions and render cache. Not thread-safe on its own; the
    studio app serialises the calls."""

    def __init__(self, folder: Path, data: dict[str, Any]) -> None:
        self.folder = folder
        self.data = data

    @classmethod
    def create(cls, studio: Path, preset: str | None, title: str) -> StudioSession:
        """A new, empty session folder under ``studio/sessions``."""
        while True:
            session_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
            folder = studio / "sessions" / session_id
            if not folder.exists():
                break
        (folder / "versions").mkdir(parents=True)
        data = {"format": SESSION_FORMAT, "id": session_id, "created": _now(), "preset": preset, "title": title, "current": None, "versions": []}
        session = cls(folder, data)
        session._save()
        return session

    @classmethod
    def open(cls, studio: Path, session_id: str) -> StudioSession:
        """An existing session (:class:`VidgenError` if the id is malformed or unknown)."""
        if not SESSION_ID.match(session_id):
            raise VidgenError(f"not a studio session id: {session_id!r}")
        path = studio / "sessions" / session_id / "session.json"
        if not path.is_file():
            raise VidgenError(f"no studio session {session_id} in {studio}")
        return cls(path.parent, json.loads(path.read_text(encoding="utf-8")))

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def preset(self) -> str | None:
        return self.data["preset"]

    @property
    def current(self) -> int | None:
        return self.data["current"]

    @property
    def versions(self) -> list[Version]:
        return [Version(**v) for v in self.data["versions"]]

    @property
    def renders(self) -> Path:
        """The render cache folder (created on first use by the writer)."""
        return self.folder / "renders"

    def version_path(self, number: int) -> Path:
        return self.folder / "versions" / f"v{number:04d}.yaml"

    def text(self, number: int) -> str:
        """The score text of version ``number`` (:class:`VidgenError` if there is none)."""
        if not any(v["number"] == number for v in self.data["versions"]):
            raise VidgenError(f"session {self.id} has no version {number}")
        return self.version_path(number).read_text(encoding="utf-8")

    def add_version(self, text: str, origin: str, label: str, parent: int | None) -> Version:
        """Write ``text`` as the next version and make it the current one."""
        number = 1 + max((v["number"] for v in self.data["versions"]), default=0)
        write_text_atomic(self.version_path(number), text)
        version = Version(number, parent, origin, label, _now())
        self.data["versions"].append(asdict(version))
        self.data["current"] = number
        self._save()
        return version

    def to_json(self) -> dict[str, Any]:
        return {**self.data, "folder": str(self.folder)}

    def _save(self) -> None:
        write_text_atomic(self.folder / "session.json", json.dumps(self.data, indent=2, ensure_ascii=False) + "\n")


def write_open_marker(studio: Path, url: str, session_id: str | None) -> None:
    """Record the running studio in ``<studio>/open.json`` (read by MCP tools, §94.8)."""
    doc = {"url": url, "session": session_id, "pid": os.getpid(), "started": _now()}
    write_text_atomic(studio / OPEN_FILE, json.dumps(doc, indent=2) + "\n")


def remove_open_marker(studio: Path) -> None:
    """Remove ``open.json`` if this process wrote it (another studio may have replaced it)."""
    path = studio / OPEN_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if doc.get("pid") == os.getpid():
        remove_file(path)
