"""Flight data for ``web`` scenes with ``flight_data:``: the cache and its key, and
the page's helper. The data is made by :mod:`vidgen.scenes.flight_data` (with :mod:`vidgen.flight`)
and travels to the page inside the orbit bridge's payload (``orbits.flights``, Step 367's plumbing);
``data/web/flight.js`` turns it into ``ctx.flight``."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from vidgen.fileio import write_text_atomic

HELPER_FILE = Path(__file__).resolve().parent.parent / "data" / "web" / "flight.js"
#: Where the data is kept, under the project's build folder.
CACHE_FOLDER = "flights"
_PACKAGE = Path(__file__).resolve().parent.parent
#: The source files the data is made from (their contents are in the cache key).
_SOURCES = ("flight", "orbits", "scenes/flight_data.py", "scenes/space_params.py", "web/land.py")


def helper_source() -> str:
    """The page's flight helper (``data/web/flight.js``)."""
    return HELPER_FILE.read_text(encoding="utf-8")


def helper_digest() -> str:
    return hashlib.sha256(HELPER_FILE.read_bytes()).hexdigest()


def _source_digest() -> str:
    h = hashlib.sha256()
    for rel in _SOURCES:
        path = _PACKAGE / rel
        for p in sorted(path.rglob("*.py")) if path.is_dir() else [path]:
            h.update(p.relative_to(_PACKAGE).as_posix().encode("utf-8") + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def flight_data_key(settings: Any, fps: int, frames: int, scene_frames: int, music: dict[str, Any] | None = None,
                    orbits: dict[str, Any] | None = None) -> str:
    """The cache key (SHA-256 hex) of a scene's flight data: the settings
    (:class:`~vidgen.scenes.flight_data.FlightData`), the frame rate, the frames drawn and the scene's
    own, the data version, vidgen's version, the flight code, the page code (a land's heights come from
    it) and, when the flights read them, the music (bars) and the orbit data (a start from orbit)."""
    from vidgen import __version__
    from vidgen.scenes.flight_data import FLIGHT_DATA_VERSION

    inputs: dict[str, Any] = {"version": FLIGHT_DATA_VERSION, "vidgen": __version__, "source": _source_digest(), "fps": fps, "frames": frames,
                              "scene_frames": scene_frames, "settings": settings.model_dump(mode="json", by_alias=True)}
    if settings.ground.kind == "land":
        from vidgen.web.baked import code_digest

        inputs["page_code"] = code_digest()
    if settings.uses_bars and music is not None:
        score = music.get("score") or {}
        inputs["music"] = {"bar": score.get("bar"), "beat": score.get("beat"), "t0": music.get("t0")}
    if settings.orbit_bodies and orbits is not None:
        inputs["orbits"] = _digest({k: v for k, v in orbits.items() if k != "flights"})
    return _digest(inputs)


def scene_flight_data(project: Any, settings: Any, fps: int, frames: int, scene_frames: int, music: dict[str, Any] | None = None,
                      orbits: dict[str, Any] | None = None) -> dict[str, Any]:
    """``ctx.flight`` of a scene as the page is given it (:func:`vidgen.scenes.flight_data.make_flight_data`),
    kept in ``build/flights/flight-data-<key>.json``."""
    from vidgen.scenes import flight_data

    key = flight_data_key(settings, fps, frames, scene_frames, music, orbits)
    cached = project.build_dir / CACHE_FOLDER / f"flight-data-{key}.json"
    if cached.is_file():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass  # damaged: made again
    data = flight_data.make_flight_data(settings, fps, frames, scene_frames, music=music, orbits=orbits)
    write_text_atomic(cached, json.dumps(data, separators=(",", ":")) + "\n")
    return data


def with_flights(orbits: dict[str, Any] | None, flights: dict[str, Any]) -> dict[str, Any]:
    """The orbit bridge's payload carrying the flights too (``orbits.flights``; a scene without orbit data: the flights alone)."""
    return {**(orbits or {}), "flights": flights}


__all__ = ["CACHE_FOLDER", "HELPER_FILE", "flight_data_key", "helper_digest", "helper_source", "scene_flight_data", "with_flights"]
