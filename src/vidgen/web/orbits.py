"""Orbit data for ``web`` scenes with ``orbit_data:``: the cache and its key,
and the page's helper. The data itself is made by :mod:`vidgen.scenes.orbit_data` (with the
``orbit`` scene's model); ``data/web/orbits.js`` turns it into ``ctx.orbits``."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from vidgen.fileio import write_text_atomic

HELPER_FILE = Path(__file__).resolve().parent.parent / "data" / "web" / "orbits.js"
#: Where the data is kept, under the project's build folder.
CACHE_FOLDER = "orbits"
_PACKAGE = Path(__file__).resolve().parent.parent
#: The source files the data is made from (their contents are in the cache key).
_SOURCES = ("orbits", "scenes/orbit_parts.py", "scenes/orbit_sky.py", "scenes/orbit_systems.py", "scenes/orbit_data.py")


def helper_source() -> str:
    """The page's orbit helper (``data/web/orbits.js``)."""
    return HELPER_FILE.read_text(encoding="utf-8")


def helper_digest() -> str:
    return hashlib.sha256(HELPER_FILE.read_bytes()).hexdigest()


def _source_digest() -> str:
    """The SHA-256 of the source files the data is made from."""
    h = hashlib.sha256()
    for rel in _SOURCES:
        path = _PACKAGE / rel
        for p in sorted(path.rglob("*.py")) if path.is_dir() else [path]:
            h.update(p.relative_to(_PACKAGE).as_posix().encode("utf-8") + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def orbit_data_key(settings: Any, fps: int, frames: int, scene_frames: int) -> str:
    """The cache key (SHA-256 hex) of a scene's orbit data: the settings
    (:class:`~vidgen.scenes.orbit_data.OrbitData`), the frame rate, the frames drawn and the
    scene's own frames, the data version, vidgen's version and the orbit code."""
    from vidgen import __version__
    from vidgen.scenes.orbit_data import ORBIT_DATA_VERSION

    inputs = {"version": ORBIT_DATA_VERSION, "vidgen": __version__, "source": _source_digest(), "fps": fps, "frames": frames,
              "scene_frames": scene_frames, "settings": settings.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def scene_orbit_data(project: Any, settings: Any, fps: int, frames: int, scene_frames: int) -> dict[str, Any]:
    """``ctx.orbits`` of a scene as the page is given it
    (:func:`vidgen.scenes.orbit_data.make_orbit_data`), kept in ``build/orbits/orbit-data-<key>.json``."""
    from vidgen.scenes import orbit_data

    key = orbit_data_key(settings, fps, frames, scene_frames)
    cached = project.build_dir / CACHE_FOLDER / f"orbit-data-{key}.json"
    if cached.is_file():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass  # damaged: made again
    data = orbit_data.make_orbit_data(settings, fps, frames, scene_frames)
    write_text_atomic(cached, json.dumps(data, separators=(",", ":")) + "\n")
    return data


__all__ = ["CACHE_FOLDER", "HELPER_FILE", "helper_digest", "helper_source", "orbit_data_key", "scene_orbit_data"]
