"""Icon registry: the vendored icon set and a project's own icons (DESIGN.md §22).

Built-in icons are package data (``vidgen/data/icons``): SVG files of one open-licensed set
(Lucide, ISC) with a ``manifest.json`` giving each icon's name, category, search tags and
source, plus ``aliases``: other names that resolve to the icon (Lucide's old names of renamed
icons such as ``home`` for ``house``, and a few curated synonyms). A project adds or replaces icons by name with ``assets/icons/<name>.svg``; an optional
``assets/icons/icons.json`` (``{"icons": [{"name", "category", "tags"}]}``) gives them a
category and tags for ``vidgen list-icons``.

This module does not import manim: :mod:`vidgen.icon_mobject` builds the Manim objects.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError

#: Folder of the vendored icons (package data) and its manifest.
ICONS_DIR = Path(__file__).resolve().parent / "data" / "icons"
MANIFEST_FILE = ICONS_DIR / "manifest.json"

#: A project's icon folder (relative to its root) and the optional manifest inside it.
PROJECT_ICONS_DIR = Path("assets") / "icons"
PROJECT_MANIFEST = "icons.json"

#: Categories of the built-in set, with what they cover.
CATEGORIES: dict[str, str] = {
    "tech": "computers, devices, software, networks",
    "data": "databases, charts, tables, statistics",
    "science": "physics, chemistry, biology, energy",
    "business": "work, money, growth, goals",
    "people": "persons, groups, communication, thinking",
    "ui": "arrows and interface symbols",
    "nature": "plants, weather, landscape, water",
    "education": "books, learning, ideas, teaching",
}
#: Category of a project icon that its manifest does not categorise.
PROJECT_CATEGORY = "project"

#: Icon names: letters, digits, ``-`` and ``_`` (the SVG file's stem).
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class IconInfo:
    """One available icon. ``origin`` is ``builtin`` or ``project``; ``overrides`` is true for a
    project icon that replaces a built-in of the same name. ``aliases`` are other names that
    resolve to it (built-in aliases; a project icon replacing a built-in keeps them)."""

    name: str
    path: Path
    category: str
    tags: tuple[str, ...]
    source: str
    origin: str
    overrides: bool = False
    aliases: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        """The icon as a ``vidgen list-icons --json`` entry."""
        return {
            "name": self.name,
            "category": self.category,
            "tags": list(self.tags),
            "aliases": list(self.aliases),
            "source": self.source,
            "origin": self.origin,
            "overrides": self.overrides,
            "path": str(self.path),
        }


def _tags(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
        raise VidgenError(f"{where}: 'tags' must be a list of strings")
    return tuple(value)


@lru_cache(maxsize=1)
def _builtin_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def builtin_sources() -> dict[str, dict[str, Any]]:
    """Where the built-in icons come from: ``{source: {package, version, license, ...}}``."""
    return dict(_builtin_manifest()["sources"])


@lru_cache(maxsize=1)
def builtin_icons() -> dict[str, IconInfo]:
    """The vendored icons by name (from ``data/icons/manifest.json``)."""
    icons: dict[str, IconInfo] = {}
    for entry in _builtin_manifest()["icons"]:
        name, source = entry["name"], entry["source"]
        icons[name] = IconInfo(
            name=name,
            path=ICONS_DIR / source / f"{name}.svg",
            category=entry["category"],
            tags=tuple(entry["tags"]),
            source=source,
            origin="builtin",
            aliases=tuple(entry.get("aliases", ())),
        )
    return icons


@lru_cache(maxsize=1)
def builtin_aliases() -> dict[str, str]:
    """``{alias: icon name}`` of the built-in set (e.g. ``home`` -> ``house``)."""
    return {alias: info.name for info in builtin_icons().values() for alias in info.aliases}


def _project_manifest(folder: Path) -> dict[str, dict[str, Any]]:
    """``{name: {category, tags}}`` from ``assets/icons/icons.json`` (empty when absent)."""
    path = folder / PROJECT_MANIFEST
    where = (PROJECT_ICONS_DIR / PROJECT_MANIFEST).as_posix()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise VidgenError(f"{where}: cannot read icon manifest: {exc}") from None
    entries = data.get("icons") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise VidgenError(f"{where}: expected {{\"icons\": [{{\"name\": ..., \"category\": ..., \"tags\": [...]}}]}}")
    out: dict[str, dict[str, Any]] = {}
    for i, entry in enumerate(entries):
        spot = f"{where}: icons[{i}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise VidgenError(f"{spot}: each entry needs a 'name'")
        unknown = set(entry) - {"name", "category", "tags"}
        if unknown:
            raise VidgenError(f"{spot}: unknown keys {', '.join(sorted(unknown))} (allowed: name, category, tags)")
        name = entry["name"]
        if not (folder / f"{name}.svg").is_file():
            raise VidgenError(f"{spot}: no file {(PROJECT_ICONS_DIR / f'{name}.svg').as_posix()} for icon '{name}'")
        category = entry.get("category", PROJECT_CATEGORY)
        if not isinstance(category, str) or not NAME_PATTERN.match(category):
            raise VidgenError(f"{spot}: 'category' must be a name like 'tech'")
        out[name] = {"category": category, "tags": _tags(entry.get("tags", []), spot)}
    return out


@lru_cache(maxsize=16)
def _project_icons(folder: Path, signature: tuple[tuple[str, int, int], ...]) -> dict[str, IconInfo]:
    """Project icons of ``folder``; ``signature`` (names, sizes, mtimes) keys the cache."""
    del signature
    meta = _project_manifest(folder)
    builtins = builtin_icons()
    icons: dict[str, IconInfo] = {}
    for path in sorted(folder.glob("*.svg")):
        name = path.stem
        if not NAME_PATTERN.match(name):
            rel = (PROJECT_ICONS_DIR / path.name).as_posix()
            raise VidgenError(f"{rel}: icon names may only contain letters, digits, '-' and '_' (rename the file)")
        info = meta.get(name, {})
        icons[name] = IconInfo(
            name=name,
            path=path,
            category=info.get("category", PROJECT_CATEGORY),
            tags=info.get("tags", ()),
            source="project",
            origin="project",
            overrides=name in builtins,
            aliases=builtins[name].aliases if name in builtins else (),
        )
    return icons


def project_icons(root: Path) -> dict[str, IconInfo]:
    """The icons in ``<root>/assets/icons`` by name (empty when the folder does not exist)."""
    folder = (root / PROJECT_ICONS_DIR).resolve()
    if not folder.is_dir():
        return {}
    files = [p for p in folder.iterdir() if p.suffix == ".svg" or p.name == PROJECT_MANIFEST]
    signature = tuple(sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files if p.is_file()))
    return _project_icons(folder, signature)


def available_icons(root: Path | None = None) -> dict[str, IconInfo]:
    """Built-in icons merged with those of the project at ``root`` (a project icon replaces a
    built-in of its name, and a project icon named like a built-in alias takes that name over),
    sorted by name."""
    icons = dict(builtin_icons())
    if root is not None:
        own = project_icons(root)
        icons.update(own)
        for name, info in icons.items():
            if not set(info.aliases).isdisjoint(own):
                icons[name] = replace(info, aliases=tuple(a for a in info.aliases if a not in own))
    return dict(sorted(icons.items()))


def active_icons() -> dict[str, IconInfo]:
    """:func:`available_icons` of the active project (built-ins only without one)."""
    from vidgen import runtime

    return available_icons(runtime.current_project().root if runtime.has_context() else None)


def _score(icon: IconInfo, term: str) -> int | None:
    """How well ``term`` (lower case) matches: 0 exact name, 1 name prefix or exact alias, 2 part
    of the name or an alias, 3 a tag, 4 part of a tag, 5 the category; ``None``: no match."""
    name = icon.name.lower()
    aliases = [a.lower() for a in icon.aliases]
    tags = [t.lower() for t in icon.tags]
    if term == name:
        return 0
    if name.startswith(term) or term in aliases:
        return 1
    if term in name or any(term in a for a in aliases):
        return 2
    if term in tags:
        return 3
    if any(term in t for t in tags):
        return 4
    if term == icon.category.lower():
        return 5
    return None


def search_icons(
    icons: Mapping[str, IconInfo], text: str | None = None, category: str | None = None
) -> list[IconInfo]:
    """Icons whose name, aliases or tags contain (or category is) every word of ``text``
    (case-insensitive), optionally only one ``category``; best matches first (name, then alias,
    then tag matches), then by name."""
    terms = (text or "").lower().replace("-", " ").split()
    found: list[tuple[int, str, IconInfo]] = []
    for icon in icons.values():
        if category is not None and icon.category != category:
            continue
        scores = [_score(icon, term) for term in terms]
        if any(s is None for s in scores):
            continue
        found.append((sum(s for s in scores if s is not None), icon.name, icon))
    return [icon for _, _, icon in sorted(found, key=lambda item: (item[0], item[1]))]


def categories(icons: Iterable[IconInfo]) -> list[str]:
    """The built-in categories, then any other category used by ``icons``."""
    extra = sorted({icon.category for icon in icons} - set(CATEGORIES))
    return [*CATEGORIES, *extra]


def _alias_targets(icons: Mapping[str, IconInfo]) -> dict[str, str]:
    """``{alias: icon name}`` over ``icons`` (an alias never shadows an icon's own name)."""
    return {alias: info.name for info in icons.values() for alias in info.aliases if alias not in icons}


def resolve_icon(name: str, icons: Mapping[str, IconInfo]) -> IconInfo | None:
    """The icon called ``name`` (or that has the alias ``name``) among ``icons``; ``None`` if none."""
    info = icons.get(name)
    if info is None:
        target = _alias_targets(icons).get(name)
        info = icons.get(target) if target is not None else None
    return info


def icon_names(icons: Mapping[str, IconInfo]) -> list[str]:
    """Every name that :func:`resolve_icon` accepts (icon names and aliases), sorted."""
    return sorted({*icons, *_alias_targets(icons)})


def unknown_icon_message(name: str, icons: Mapping[str, IconInfo]) -> str:
    """``unknown icon 'x'; did you mean ...`` with close names (or aliases, given as the icon they
    stand for) and icons tagged like ``name``."""
    message = f"unknown icon '{name}'"
    targets = _alias_targets(icons)
    matches = difflib.get_close_matches(name, icon_names(icons), n=4, cutoff=0.6)
    close = list(dict.fromkeys(targets.get(m, m) for m in matches))
    tagged = [icon.name for icon in search_icons(icons, name) if icon.name not in close][:6]
    hints = []
    if close:
        hints.append("did you mean " + ", ".join(f"'{c}'" for c in close) + "?")
    if tagged:
        hints.append("matching tags: " + ", ".join(tagged))
    if hints:
        message += "; " + "; ".join(hints)
    return message + " (see `vidgen list-icons --search TEXT`)"


def find_icon(name: str, icons: Mapping[str, IconInfo] | None = None) -> IconInfo:
    """The icon ``name`` (or alias) among ``icons`` (default: :func:`active_icons`); unknown names
    raise :class:`VidgenError` with suggestions."""
    icons = active_icons() if icons is None else icons
    info = resolve_icon(name, icons)
    if info is None:
        raise VidgenError(unknown_icon_message(name, icons))
    return info
