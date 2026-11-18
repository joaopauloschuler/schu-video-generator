"""``vidgen/space-land``'s heights for Python (Step 385, DESIGN.md §123.7): the ground's
``definition()`` — ``{radius, recipe, macro: {n, spacing, scale, heights}}`` — fetched by opening a
small page once in headless Chromium (the macro lattice is made on the GPU) and kept in vidgen's
cache folder (``ground/``, cleared by ``vidgen cache clear``) under a key of the ground's options,
the air and the code a page runs (:func:`vidgen.web.baked.code_digest`: vidgen's modules and
three.js). :class:`vidgen.flight.terrain.LandGround` evaluates the heights from it in numpy.
"""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic

#: The folder of vidgen's cache folder the definitions are kept in, and their layout's version.
FOLDER = "ground"
VERSION = 1

PAGE = """
import * as THREE from "three";
import {air} from "vidgen/space-air";
import {land, vacuum, PRESETS, RADII} from "vidgen/space-land";
export function load(ctx) {
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  const o = ctx.data.land, preset = o.preset ? PRESETS[String(o.preset).trim().toLowerCase()] : null;
  let what = ctx.data.air ?? (preset ? preset.air : "earth");
  if (what === null) what = vacuum(RADII[preset ? preset.world : o.world]);
  try {
    const ground = land(renderer, air(renderer, what, {}), o);
    const points = ctx.data.points;
    window.__ground = {definition: ground.definition(), heights: points.map(([x, z]) => ground.heightAt(x, z))};
  } catch (e) { window.__ground = {error: e.message}; }
}
export function frame() {}
"""


def cache_dir() -> Path:
    """Where definitions are kept: ``ground/`` in vidgen's cache folder (only returns the path)."""
    from vidgen.soundfont import cache_dir as root

    return root() / FOLDER


def definition_key(options: dict[str, Any], air: Any) -> str:
    """The cache key (SHA-256 hex) of a ground's definition: its options, the air, the layout's version and the page code's digest."""
    from vidgen.web.baked import code_digest

    inputs = {"version": VERSION, "code": code_digest(), "land": options, "air": air}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _pack(definition: dict[str, Any]) -> dict[str, Any]:
    macro = dict(definition["macro"])
    macro["heights"] = base64.b64encode(np.asarray(macro["heights"], dtype="<f4").tobytes()).decode("ascii")
    return {**definition, "macro": macro}


def _unpack(stored: dict[str, Any]) -> dict[str, Any]:
    macro = dict(stored["macro"])
    macro["heights"] = np.frombuffer(base64.b64decode(macro["heights"]), dtype="<f4").astype(float)
    return {**stored, "macro": macro}


def page_heights(options: dict[str, Any], air: Any = None, points: list[list[float]] | None = None) -> dict[str, Any]:
    """Open the page once: ``{definition, heights}`` (``heights``: the page's ``heightAt(x, z)`` at ``points``)."""
    from vidgen.browser import chromium
    from vidgen.web.entry import WebEntry
    from vidgen.web.page import WebPage

    problem = chromium.missing_dependency()
    if problem is not None:
        raise VidgenError(f"the ground's heights come from a page of vidgen/space-land, which needs Chromium: {problem}")
    with tempfile.TemporaryDirectory(prefix="vidgen-ground-") as folder:
        root = Path(folder)
        (root / "ground.js").write_text(PAGE, encoding="utf-8")
        with WebPage(root, WebEntry("script", "ground.js"), scene_id="ground", size=(16, 16), fps=1, frames=1,
                     data={"land": options, "air": air, "points": points or []}) as page:
            found = page._page.evaluate("window.__ground")
    if not isinstance(found, dict) or "error" in found:
        raise VidgenError(f"ground: {found.get('error') if isinstance(found, dict) else 'the page gave no definition'}")
    return found


def land_definition(options: dict[str, Any], air: Any = None) -> dict[str, Any]:
    """The ground's ``definition()`` for ``land(renderer, air(renderer, air), options)`` (``air``: a name of
    vidgen/space-air, default the preset's; null for an airless preset's vacuum), from the cache or
    from a page; ``macro.heights`` as a float array."""
    key = definition_key(options, air)
    path = cache_dir() / f"land-{key}.json"
    if path.is_file():
        try:
            return _unpack(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError):
            pass   # damaged: fetched again
    definition = page_heights(options, air)["definition"]
    write_text_atomic(path, json.dumps(_pack(definition), separators=(",", ":")) + "\n")
    return _unpack(_pack(definition))


#: The options of ``land()`` a flight's ground may give (the others draw, they do not shape the heights), and ``air``.
_OWN = ("preset", "world", "at", "seed")
_PART_CONSTANTS = {"mountains": "MOUNTAINS", "rough": "ROUGH", "strata": "STRATA", "dunes": "DUNES", "craters": "CRATERS",
                   "canyons": "CANYONS", "volcanoes": "VOLCANOES", "materials": "MATERIALS"}


def land_settings(options: dict[str, Any]) -> dict[str, Any]:
    """Check a flight's ``ground: {land: ...}`` against ``vidgen/space-land``'s own names (read from its
    source, with a did-you-mean) and resolve what Python needs before any page: ``{options, air, world, at}``
    (``options`` without ``air``; ``air``: the air's name, ``None`` for an airless preset's vacuum; ``world``:
    the world of the flight — the air's, or the airless preset's; ``at``: the place, the preset's by default)."""
    from vidgen.plotcore import did_you_mean
    from vidgen.web.space_names import constant_entries, constant_keys, constant_strings

    module = "vidgen/space-land"
    parts = constant_strings(module, "RECIPE_KEYS")
    known = [*_OWN, *parts, "air"]
    for key in options:
        if key not in known:
            raise ValueError(f"ground.land: unknown option '{key}'{did_you_mean(key, known)}; options: {', '.join(known)}")
    for part in parts:
        if part in options:
            if not isinstance(options[part], dict):
                raise ValueError(f"ground.land.{part} must be a mapping of numbers")
            names = constant_keys(module, _PART_CONSTANTS[part])
            for key in options[part]:
                if key not in names:
                    raise ValueError(f"ground.land.{part}: unknown key '{key}'{did_you_mean(key, names)}; keys: {', '.join(names)}")
    presets = constant_entries(module, "PRESETS")
    own = {k: v for k, v in options.items() if k != "air"}
    preset = None
    if "preset" in options:
        name = str(options["preset"]).strip().lower()
        if name not in presets:
            raise ValueError(f"ground.land.preset: no ground '{options['preset']}'{did_you_mean(name, list(presets))}; ready-made: {', '.join(presets)}")
        from vidgen.web.space_names import object_entries

        preset = {k: json.loads(v) for k, v in object_entries(presets[name]).items() if k in ("world", "at", "air")}
    elif "world" not in options or "at" not in options:
        raise ValueError("ground.land: give a preset, or a world of vidgen/space-bodies with at: [latitude, longitude]")
    at = options.get("at", preset["at"] if preset else None)
    if not (isinstance(at, (list, tuple)) and len(at) == 2 and all(isinstance(v, (int, float)) for v in at)):
        raise ValueError(f"ground.land.at must be [latitude, longitude] in degrees, got {at!r}")
    air = options["air"] if "air" in options else (preset["air"] if preset else "earth")
    world = air if air is not None else (preset["world"] if preset else str(options["world"]))
    return {"options": own, "air": air, "world": str(world), "at": [float(at[0]), float(at[1])]}


def clear() -> tuple[int, int]:
    """Remove every kept definition: (how many, bytes)."""
    folder = cache_dir()
    count = size = 0
    if folder.is_dir():
        for f in folder.glob("land-*.json"):
            size += f.stat().st_size
            f.unlink(missing_ok=True)
            count += 1
    return count, size


__all__ = ["FOLDER", "PAGE", "cache_dir", "clear", "definition_key", "land_definition", "land_settings", "page_heights"]
