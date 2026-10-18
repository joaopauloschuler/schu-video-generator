"""Shared casts and sets: ``include:`` files and named ``sets:`` (DESIGN.md §69.35). No manim.

A project's config may start from other files: ``include: [cast.yaml, ../shared/sets.yaml]``
(paths relative to the file that names them) holding ``characters``, ``voices``, ``sets`` and
their own ``include``. :func:`read_project_config` reads them and merges them with
:func:`merge_config`: a file's includes first, then the file; the project's own keys last, so they
win. Mappings merge key by key, ``characters`` entries by name (an entry of a later file changes
the earlier entry of that name), other values replace.

A stage scene's ``set: <name>`` starts its ``params`` from that set (:func:`apply_set`); the
scene's own params win. :func:`expand_sets` applies the sets of every scene before the config is
validated, so the stage itself never sees ``set``. A name the project's ``sets:`` lacks falls back
to a built-in set (:func:`builtin_sets`, DESIGN.md §76).

Problems keep pointing at the text the user wrote: :class:`Origin` entries map a location of the
merged config to the file and location the value is written at (:func:`attributed`).
"""

from __future__ import annotations

import copy
import difflib
import functools
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from vidgen.cartoon.stage import numbered_names, prop_default_name
from vidgen.errors import Problem, VidgenError

#: Top-level keys an included file may hold.
INCLUDABLE_KEYS: tuple[str, ...] = ("include", "characters", "voices", "sets")
#: Set params that are one choice: a stage that gives any of them drops all of the set's.
BACKGROUND_KEYS = frozenset({"image", "generate", "background"})
#: A stage's indoor set (DESIGN.md §69.42): another choice of backdrop, see :func:`apply_set`.
ROOM_KEY = "room"
#: Set params a stage with a platform ``level`` does not take from its set (DESIGN.md §86.2): what
#: stands at a depth (props), the water and a room; everything on a level stands on its tiles.
LEVEL_DROPPED_KEYS = frozenset({"props", "water", ROOM_KEY, "ground_color"})
#: Set params whose lists combine with the stage's (the set's entries first).
COMBINED_LISTS: tuple[str, ...] = ("characters", "props", "layers", "particles")
#: The built-in sets (DESIGN.md §76): every ``*.yaml`` file here holds ``sets:``.
BUILTIN_SETS_DIR = Path(__file__).resolve().parent / "data" / "sets"


@dataclass(frozen=True)
class Origin:
    """Where a value of the merged config is written: ``file`` (relative to the project; ``None``
    for the project's config file) at ``location`` (a config path in that file)."""

    file: str | None
    location: str


@dataclass
class ConfigSource:
    """A project's config as read with its includes: the merged raw mapping (``include`` kept,
    ``set`` not yet applied), the included files in the order merged, the :class:`Origin` of
    each location written in an included file or moved by a merge, and the files the included
    files name (SVGs, pictures; for fingerprints)."""

    data: Any
    files: tuple[Path, ...] = ()
    origins: dict[str, Origin] = field(default_factory=dict)
    named_files: tuple[Path, ...] = ()


# ----- locations ------------------------------------------------------------------------------------


def _join(prefix: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{prefix}[{key}]"
    return f"{prefix}.{key}" if prefix else key


def _prefixes(location: str) -> list[str]:
    """``a.b[2].c`` -> ``a.b[2].c``, ``a.b[2]``, ``a.b``, ``a`` (longest first)."""
    cuts = [i for i, char in enumerate(location) if char in ".[" and i > 0]
    return [location] + [location[:i] for i in reversed(cuts)]


def origin_of(location: str, origins: Mapping[str, Origin]) -> Origin:
    """Where ``location`` of the merged config is written (the longest recorded prefix, the
    rest of the path appended); itself in the project's config file when nothing is recorded."""
    for prefix in _prefixes(location):
        found = origins.get(prefix)
        if found is not None:
            return Origin(found.file, found.location + location[len(prefix):])
    return Origin(None, location)


def _forget(origins: dict[str, Origin], location: str) -> None:
    """Drop what is recorded at and under ``location``."""
    for key in [k for k in origins if k == location or k.startswith((location + ".", location + "["))]:
        del origins[key]


def _set_origin(origins: dict[str, Origin], location: str, origin: Origin) -> None:
    """Record that the value at ``location`` (and everything under it) is written at ``origin``."""
    _forget(origins, location)
    if origin_of(location, origins) != origin:
        origins[location] = origin


def attributed(problems: Iterable[Problem], origins: Mapping[str, Origin]) -> list[Problem]:
    """``problems`` with each location moved to where its value is written (:func:`origin_of`)
    and ``file`` set for an included file; repeats (a set used by several scenes) dropped."""
    out: list[Problem] = []
    for problem in problems:
        if origins and problem.location and problem.file is None:
            origin = origin_of(problem.location, origins)
            problem = replace(problem, location=origin.location, file=origin.file)
        if problem not in out:
            out.append(problem)
    return out


def attributed_error(error: VidgenError, origins: Mapping[str, Origin]) -> VidgenError:
    """``error`` (an invalid config) with its problems :func:`attributed` and its message
    rebuilt from them; unchanged without origins or problems."""
    if not origins or not error.problems:
        return error
    problems = attributed(error.problems, origins)
    head = str(error).splitlines()[0]
    lines = [head, *(f"  {problem}" for problem in problems)]
    return VidgenError("\n".join(lines), problems=problems, details=error.details)


# ----- merging ---------------------------------------------------------------------------------------


def _character_name(entry: Any) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, Mapping) and isinstance(entry.get("name"), str):
        return entry["name"]
    return None


def _merge(base: Any, override: Any, location: str, origins: dict[str, Origin] | None, origin: Origin, named: bool) -> Any:
    """``override`` merged onto ``base`` (mappings key by key; with ``named``, a list of
    ``characters`` entry by name; anything else replaced), recording where the override's values
    are written (``origin`` is the override's own location of ``location``)."""
    if isinstance(base, Mapping) and isinstance(override, Mapping):
        merged = copy.deepcopy(dict(base))
        for key, value in override.items():
            here = _join(location, key)
            merged[key] = _merge(base.get(key), value, here, origins, Origin(origin.file, _join(origin.location, key)), named)
        return merged
    if named and location == "characters" and isinstance(base, list) and isinstance(override, list):
        return _merge_characters(base, override, origins, origin)
    if origins is not None:
        _set_origin(origins, location, origin)
    return copy.deepcopy(override)


def _merge_characters(base: list[Any], override: list[Any], origins: dict[str, Origin] | None, origin: Origin) -> list[Any]:
    merged = copy.deepcopy(base)
    index = {name: j for j, name in enumerate(map(_character_name, base)) if name is not None}
    for q, entry in enumerate(override):
        written = Origin(origin.file, f"{origin.location}[{q}]")
        name = _character_name(entry)
        j = index.get(name) if name is not None else None
        if j is not None and isinstance(merged[j], Mapping) and isinstance(entry, Mapping):
            merged[j] = _merge(merged[j], entry, f"characters[{j}]", origins, written, named=False)
            continue
        if j is None:
            j = len(merged)
            merged.append(None)
            if name is not None:
                index[name] = j
        merged[j] = copy.deepcopy(entry)
        if origins is not None:
            _set_origin(origins, f"characters[{j}]", written)
    return merged


def merge_config(base: Mapping[str, Any], override: Mapping[str, Any], origins: dict[str, Origin] | None = None, file: str | None = None) -> dict[str, Any]:
    """``override`` (a file's top-level keys) merged onto ``base`` (what the files before it
    gave): mappings merge key by key, ``characters`` entries by name (a later entry of the same
    name changes the earlier one: its keys win), anything else is replaced. With ``origins``,
    records that the override's values are written in ``file``."""
    return _merge(base, override, "", origins, Origin(file, ""), named=True)


def after_variant(origins: Mapping[str, Origin], data: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Origin]:
    """``origins`` once a variant's ``override`` is deep-merged onto the config ``data``
    (:func:`vidgen.project.deep_merge`): what the variant replaces is its own."""
    updated = dict(origins)
    if updated:
        _merge(data, override, "", updated, Origin(None, ""), named=False)
    return updated


# ----- sets ------------------------------------------------------------------------------------------


@dataclass
class SetMerge:
    """A stage's params with its set applied (:func:`apply_set`): ``params``, and for the
    locations (relative to ``params``) not where the stage wrote them, the location written in
    the set (``from_set``) or in the stage's params (``from_stage``)."""

    params: dict[str, Any]
    from_set: dict[str, str] = field(default_factory=dict)
    from_stage: dict[str, str] = field(default_factory=dict)


def entry_names(key: str, entries: Sequence[Any]) -> list[str | None]:
    """The names of a set's list entries a stage entry can change (props and layers: their own
    or default name, numbered; characters: their name; particles: none)."""
    if key == "characters":
        return [_character_name(e) for e in entries]
    if key == "props":
        pairs = [(None, e) if isinstance(e, str) else (_own_name(key, e), prop_default_name(_text(e, "prop"), _text(e, "svg"))) for e in entries]
        return list(numbered_names(pairs))
    if key == "layers":
        return list(numbered_names([(_own_name(key, e), f"{_text(e, 'place') or 'background'}_layer") for e in entries]))
    return [None] * len(entries)


def _text(entry: Any, key: str) -> str | None:
    value = entry.get(key) if isinstance(entry, Mapping) else None
    return value if isinstance(value, str) else None


def _own_name(key: str, entry: Any) -> str | None:
    """The name a stage's entry gives itself (a character's name; a prop's or layer's ``name``)."""
    if key == "characters":
        return _character_name(entry)
    return _text(entry, "name") if key in ("props", "layers") else None


def _as_mapping(key: str, entry: Any) -> Any:
    if isinstance(entry, str):
        return {"name": entry} if key == "characters" else {"prop": entry} if key == "props" else entry
    return entry


def _combine(key: str, base: list[Any], own: list[Any], result: SetMerge) -> list[Any]:
    """The set's entries, then the stage's; a stage entry named like a set entry changes it."""
    if not own:
        return []
    combined = copy.deepcopy(base)
    result.from_set.update({f"{key}[{j}]": f"{key}[{j}]" for j in range(len(base))})
    names = {name: j for j, name in enumerate(entry_names(key, base)) if name is not None}
    for q, entry in enumerate(own):
        name = _own_name(key, entry)
        j = names.get(name) if name is not None else None
        if j is not None:
            before, mine = _as_mapping(key, combined[j]), _as_mapping(key, entry)
            if isinstance(before, Mapping) and isinstance(mine, Mapping):
                combined[j] = {**copy.deepcopy(dict(before)), **copy.deepcopy(dict(mine))}
                result.from_stage.update({f"{key}[{j}].{k}": f"{key}[{q}].{k}" for k in mine})
                continue
        combined.append(copy.deepcopy(entry))
        if len(combined) - 1 != q:
            result.from_stage[f"{key}[{len(combined) - 1}]"] = f"{key}[{q}]"
    return combined


def apply_set(set_params: Mapping[str, Any], params: Mapping[str, Any]) -> SetMerge:
    """A stage's ``params`` started from a set's (the stage's own values win):

    - ``image``, ``generate`` and ``background`` are one choice: a stage giving any of them drops
      all three of the set's, and its ``room``; a stage giving a ``room`` drops the set's three
      and its ``ground_color`` (a set's room and the stage's merge key by key, like any mapping);
    - mappings (``marks``...) merge key by key;
    - ``characters``, ``props``, ``layers`` and ``particles`` combine: the set's entries, then the
      stage's; a stage entry named like a set entry (a character's name; a prop's or layer's
      ``name:`` equal to the set entry's own or default name, ``tree``, ``tree_2``) changes that
      entry instead (its keys win); an empty list clears the set's;
    - anything else is replaced;
    - a stage with a platform ``level`` takes none of :data:`LEVEL_DROPPED_KEYS` (its own props
      stand on the tiles; the set gives the sky, the layers, the light, the ambience, the marks).
    """
    own = dict(params)
    dropped: set[str] = set(LEVEL_DROPPED_KEYS) if "level" in own else set()
    if BACKGROUND_KEYS & own.keys():
        dropped |= BACKGROUND_KEYS | {ROOM_KEY}
    if ROOM_KEY in own:
        dropped |= BACKGROUND_KEYS | {"ground_color"}
    base = {k: v for k, v in set_params.items() if k not in dropped}
    result = SetMerge({})
    for key in [*base, *(k for k in own if k not in base)]:
        if key not in own:
            result.params[key] = copy.deepcopy(base[key])
            result.from_set[key] = key
        elif key not in base:
            result.params[key] = copy.deepcopy(own[key])
        elif key in COMBINED_LISTS and isinstance(base[key], list) and isinstance(own[key], list):
            result.params[key] = _combine(key, base[key], own[key], result)
        elif isinstance(base[key], Mapping) and isinstance(own[key], Mapping):
            result.params[key] = {**copy.deepcopy(dict(base[key])), **copy.deepcopy(dict(own[key]))}
            result.from_set.update({f"{key}.{k}": f"{key}.{k}" for k in base[key] if k not in own[key]})
        else:
            result.params[key] = copy.deepcopy(own[key])
    return result


@functools.cache
def _read_builtin_sets() -> dict[str, dict[str, Any]]:
    sets: dict[str, dict[str, Any]] = {}
    for path in sorted(BUILTIN_SETS_DIR.glob("*.yaml")):
        sets.update(yaml.safe_load(path.read_text(encoding="utf-8"))["sets"])
    return sets


def builtin_sets() -> dict[str, dict[str, Any]]:
    """The built-in sets (DESIGN.md §76), name -> stage params: what ``set: NAME`` uses when the
    project's ``sets:`` has no set of that name (a copy: changing it changes nothing)."""
    return copy.deepcopy(_read_builtin_sets())


def expand_sets(data: Any, origins: Mapping[str, Origin]) -> tuple[Any, dict[str, Origin]]:
    """``data`` with every scene's ``set:`` applied to its ``params`` (:func:`apply_set`), and
    ``origins`` with where the set's values are written: the project's ``sets:`` first, else a
    built-in set (:func:`builtin_sets`; its values keep the scene's locations). A ``set`` naming no
    set is left for the config check (:func:`set_reference_problems`)."""
    updated = dict(origins)
    if not isinstance(data, Mapping) or not isinstance(data.get("scenes"), list):
        return data, updated
    sets = data.get("sets") if isinstance(data.get("sets"), Mapping) else {}
    builtin = _read_builtin_sets()
    scenes: list[Any] = []
    for i, scene in enumerate(data["scenes"]):
        name = scene.get("set") if isinstance(scene, Mapping) else None
        params = scene.get("params", {}) if isinstance(scene, Mapping) else None
        own = isinstance(name, str) and isinstance(sets.get(name), Mapping)
        if not isinstance(name, str) or not (own or name in builtin) or not isinstance(params, Mapping):
            scenes.append(scene)
            continue
        merge = apply_set(sets[name] if own else builtin[name], params)
        scenes.append({**scene, "params": merge.params})
        here = f"scenes[{i}].params"
        if own:
            for at, written in merge.from_set.items():
                updated[f"{here}.{at}"] = origin_of(f"sets.{name}.{written}", origins)
        for at, written in merge.from_stage.items():
            updated[f"{here}.{at}"] = origin_of(f"{here}.{written}", origins)
    return {**data, "scenes": scenes}, updated


#: The video's ``character_size`` values that :func:`expand_character_size` passes to the stage
#: scenes (any other value is left for the config check to report at ``character_size``).
_CHARACTER_SIZES = ("small", "medium", "large")


def expand_character_size(data: Any, origins: Mapping[str, Origin]) -> tuple[Any, dict[str, Origin]]:
    """``data`` with the video's ``character_size`` (DESIGN.md §86.10) given to every ``stage``
    scene whose params (after its set) give neither ``character_size`` nor ``size``, and
    ``origins`` pointing those at the video's key; the scene's own setting wins."""
    updated = dict(origins)
    named = data.get("character_size") if isinstance(data, Mapping) else None
    if named not in _CHARACTER_SIZES or not isinstance(data.get("scenes"), list):
        return data, updated
    scenes: list[Any] = []
    for i, scene in enumerate(data["scenes"]):
        params = scene.get("params", {}) if isinstance(scene, Mapping) else None
        if not isinstance(params, Mapping) or scene.get("type") != "stage" or "character_size" in params or "size" in params:
            scenes.append(scene)
            continue
        scenes.append({**scene, "params": {**params, "character_size": named}})
        updated[f"scenes[{i}].params.character_size"] = origin_of("character_size", origins)
    return {**data, "scenes": scenes}, updated


def set_reference_problems(config: Any) -> list[Problem]:
    """Scenes whose ``set`` names neither a set of ``sets:`` nor a built-in set (with a
    did-you-mean and the known names of both)."""
    problems = []
    builtin = [name for name in _read_builtin_sets() if name not in config.sets]
    for i, scene in enumerate(config.scenes):
        if scene.set is not None and scene.set not in config.sets and scene.set not in builtin:
            close = difflib.get_close_matches(scene.set, [*config.sets, *builtin], n=1, cutoff=0.6)
            hint = f"; did you mean '{close[0]}'?" if close else ""
            known = ", ".join(config.sets) or "none (add sets: to the config or an include: file)"
            problems.append(Problem(f"scenes[{i}].set", f"unknown set '{scene.set}'{hint} sets: {known}; built-in sets: {', '.join(builtin)}"))
    return problems


# ----- reading the files ------------------------------------------------------------------------------


#: Locations of file paths in an included file: (top-level key, path inside each entry).
_PATHS_IN_INCLUDES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("characters", ("look", "svg")),
    ("sets", ("image",)),
    ("sets", ("layers", "*", "image")),
    ("sets", ("props", "*", "svg")),
)


def project_relative(path: Path, root: Path) -> str:
    """``path`` relative to the project folder ``root`` (``cast.yaml``, ``../shared/sets.yaml``)."""
    try:
        return Path(os.path.relpath(path, root)).as_posix()
    except ValueError:  # another drive (Windows)
        return path.as_posix()


def _rebased(body: dict[str, Any], folder: Path, root: Path, named: list[Path]) -> dict[str, Any]:
    """``body`` (an included file in ``folder``) with its file paths made relative to the project
    ``root`` (``named`` collects them)."""
    body = copy.deepcopy(body)

    def walk(node: Any, path: Sequence[str]) -> None:
        if not path:
            return
        head, rest = path[0], path[1:]
        children = list(node) if head == "*" and isinstance(node, list) else []
        if head != "*" and isinstance(node, dict) and head in node:
            if not rest and isinstance(node[head], str):
                target = folder / node[head]
                named.append(target)
                node[head] = node[head] if Path(node[head]).is_absolute() else project_relative(target, root)
                return
            children = [node[head]]
        for child in children:
            walk(child, rest)

    for key, path in _PATHS_IN_INCLUDES:
        section = body.get(key)
        entries = section.values() if isinstance(section, dict) else section if isinstance(section, list) else []
        for entry in entries:
            walk(entry, path)
    return body


def _include_names(value: Any, where: str, location: str, file: str | None) -> list[str]:
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not all(isinstance(n, str) and n for n in names):
        message = "include: give a file name or a list of file names (YAML or JSON, relative to this file)"
        raise VidgenError(f"{where}: {message}", problems=[Problem(location, message, file=file)])
    return names


class _Includes:
    """Reads the include tree of one project, depth first (a file's includes before the file)."""

    def __init__(self, root: Path, confine: Path | None) -> None:
        self.root = root
        self.confine = confine
        self.order: list[tuple[Path, dict[str, Any]]] = []
        self.named: list[Path] = []

    def read(self, value: Any, owner: Path, chain: list[Path]) -> None:
        from vidgen.project import read_config_file

        owner_label = None if owner == chain[0] else project_relative(owner, self.root)
        where = " -> ".join(project_relative(p, self.root) for p in chain)
        for k, name in enumerate(_include_names(value, where, "include", owner_label)):
            location = f"include[{k}]" if not isinstance(value, str) else "include"
            path = owner.parent / name

            def fail(message: str) -> VidgenError:
                return VidgenError(f"{where}: {message}", problems=[Problem(location, message, file=owner_label)])

            if path.suffix.lower() not in (".yaml", ".yml", ".json"):
                raise fail(f"include '{name}' is not a .yaml, .yml or .json file")
            if not path.is_file():
                raise fail(f"include '{name}' not found (looked for {path})")
            resolved = path.resolve()
            if self.confine is not None and not resolved.is_relative_to(self.confine):
                raise fail(f"include '{name}' is outside the allowed folder {self.confine}")
            if resolved in chain:
                cycle = " -> ".join(project_relative(p, self.root) for p in [*chain[chain.index(resolved):], resolved])
                raise fail(f"include '{name}' makes a cycle: {cycle}")
            if any(resolved == done for done, _ in self.order):
                continue  # included twice (two files share it): merged once, where first reached
            label = project_relative(resolved, self.root)
            try:
                data = read_config_file(resolved)
            except VidgenError as exc:
                raise fail(str(exc)) from None
            data = {} if data is None else data
            if not isinstance(data, dict):
                raise fail(f"{label}: the top level must be a mapping (key: value pairs)")
            extra = [key for key in data if key not in INCLUDABLE_KEYS]
            if extra:
                message = f"{label}: an included file holds {', '.join(INCLUDABLE_KEYS)}; not {', '.join(map(str, extra))} (put it in the project's config)"
                raise VidgenError(f"{where}: {message}", problems=[Problem(str(extra[0]), message, file=label)])
            if "include" in data:
                self.read(data["include"], resolved, [*chain, resolved])
            body = {key: value for key, value in data.items() if key != "include"}
            self.order.append((resolved, _rebased(body, resolved.parent, self.root, self.named)))


def read_project_config(config_file: Path, confine: Path | None = None) -> ConfigSource:
    """The config at ``config_file`` with its ``include:`` files merged (see the module doc); a
    missing, unreadable or circular include, or one outside ``confine``, is a
    :class:`VidgenError` naming the chain of files."""
    from vidgen.project import read_config_file

    config_file = config_file.resolve()
    own = read_config_file(config_file)
    if not isinstance(own, dict) or own.get("include") in (None, []):
        return ConfigSource(own)
    root = config_file.parent
    reader = _Includes(root, confine.resolve() if confine is not None else None)
    reader.read(own["include"], config_file, [config_file])
    origins: dict[str, Origin] = {}
    merged: dict[str, Any] = {}
    for path, body in reader.order:
        merged = merge_config(merged, body, origins, project_relative(path, root))
    merged = merge_config(merged, own, origins, None)
    return ConfigSource(merged, tuple(path for path, _ in reader.order), origins, tuple(dict.fromkeys(reader.named)))


def read_include_file(path: Path) -> dict[str, Any]:
    """An include file read on its own, its own includes merged (``vidgen screenplay --cast``);
    errors name the chain from ``--cast``. File paths in it stay relative to it. Under ``vidgen
    mcp`` (``CONFINE_ENV`` set) its includes must lie in that folder, as a project's do."""
    from vidgen.project import CONFINE_ENV

    folder = path.resolve().parent
    confine = os.environ.get(CONFINE_ENV)
    reader = _Includes(folder, Path(confine).resolve() if confine else None)
    reader.read([path.name], folder / "--cast", [folder / "--cast"])
    merged: dict[str, Any] = {}
    for _, body in reader.order:
        merged = merge_config(merged, body)
    return merged
