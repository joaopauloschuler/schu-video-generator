"""The names the space modules know, read from their own source (DESIGN.md §122.12).

A declarative ``space`` scene is checked by ``vidgen validate`` in Python, with no browser and no
Node: its ready-made worlds, craft kinds, camera moves, phases, lenses, sky looks, star kinds and
every option key it passes on to a module. Those lists are the modules' own constants
(``PRESETS`` of ``vidgen/space-bodies``, ``CRAFT`` of ``vidgen/space-craft``, the option lists of
each move of ``vidgen/space-camera`` ...), read here from the shipped JavaScript files so that a
module that gains a world or an option is known to Python at once, with nothing copied.

The reader understands the literal forms those files use: ``const NAME = {...}`` or
``export const NAME = Object.freeze({...})``, keys that are names or quoted strings, method
shorthand, ``...SPREAD`` of another constant of the same file, nested objects and arrays,
strings (also template strings) and comments. A constant it cannot find is a :class:`VidgenError`
naming the file (a broken install or a module that renamed it; a test reads every one).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.web.loaded import VIDGEN_MODULES

MODULES = Path(__file__).resolve().parent.parent / "data" / "web" / "modules"
_OPEN = {"{": "}", "[": "]", "(": ")"}


def module_source(name: str) -> str:
    """The source of the shipped module ``name`` (``vidgen/space-bodies``)."""
    return (MODULES / VIDGEN_MODULES[name]).read_text(encoding="utf-8")


def _skip_string(text: str, i: int) -> int:
    """The index after the string starting at ``text[i]`` (``'``, ``"`` or a template with ``${...}``)."""
    quote = text[i]
    i += 1
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if quote == "`" and text.startswith("${", i):
            i = _matching(text, i + 1) + 1
            continue
        if c == quote:
            return i + 1
        i += 1
    raise ValueError("a string that never ends")


def _skip_comment(text: str, i: int) -> int | None:
    """The index after a comment starting at ``text[i]``, or ``None`` when there is none."""
    if text.startswith("//", i):
        end = text.find("\n", i)
        return len(text) if end == -1 else end
    if text.startswith("/*", i):
        end = text.find("*/", i + 2)
        return len(text) if end == -1 else end + 2
    return None


def _matching(text: str, i: int) -> int:
    """The index of the bracket that closes the one at ``text[i]``."""
    stack = [_OPEN[text[i]]]
    i += 1
    while i < len(text):
        c = text[i]
        after = _skip_comment(text, i)
        if after is not None:
            i = after
            continue
        if c in "'\"`":
            i = _skip_string(text, i)
            continue
        if c in _OPEN:
            stack.append(_OPEN[c])
        elif c in ")]}":
            if c != stack.pop():
                raise ValueError("brackets that do not match")
            if not stack:
                return i
        i += 1
    raise ValueError("a bracket that never closes")


def _split_top(body: str) -> list[str]:
    """``body`` (the inside of an object or array literal) cut at its top-level commas."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(body):
        c = body[i]
        after = _skip_comment(body, i)
        if after is not None:
            i = after
            continue
        if c in "'\"`":
            i = _skip_string(body, i)
            continue
        if c in _OPEN:
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
        i += 1
    parts.append(body[start:])
    return [p for p in (_strip_comments(p).strip() for p in parts) if p]


def _strip_comments(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        after = _skip_comment(text, i)
        if after is not None:
            i = after
            continue
        if text[i] in "'\"`":
            j = _skip_string(text, i)
            out.append(text[i:j])
            i = j
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _unfreeze(value: str) -> str:
    """``value`` without ``Object.freeze( ... )`` around it."""
    value = value.strip()
    while value.startswith("Object.freeze("):
        value = value[len("Object.freeze("):value.rindex(")")].strip()
    return value


def _string(item: str) -> str | None:
    item = item.strip()
    if len(item) >= 2 and item[0] == item[-1] and item[0] in "'\"":
        return item[1:-1]
    return None


_DECLARED = "(?:export\\s+)?const\\s+{name}\\s*=\\s*"


def constant_text(source: str, name: str, where: str = "the module") -> str:
    """The literal (object or array, without ``Object.freeze``) the constant ``name`` of ``source`` holds."""
    match = re.search(_DECLARED.format(name=re.escape(name)), source)
    if match is None:
        raise VidgenError(f"{where} has no constant {name} (a broken install, or the module renamed it)")
    i = match.end()
    while source.startswith("Object.freeze(", i):
        i += len("Object.freeze(")
    if source[i] not in "{[":
        raise VidgenError(f"{where}: {name} is not an object or array literal")
    return source[i:_matching(source, i) + 1]


def object_entries(text: str, source: str = "", where: str = "the module") -> dict[str, str]:
    """The entries of the object literal ``text``: key -> its value's text (``""`` for method
    shorthand), in order; ``...NAME`` spreads take the entries of that constant of ``source``."""
    text = _unfreeze(text)
    if not (text.startswith("{") and text.endswith("}")):
        raise VidgenError(f"{where}: not an object literal: {text[:40]}")
    out: dict[str, str] = {}
    for part in _split_top(text[1:-1]):
        if part.startswith("..."):
            out.update(object_entries(constant_text(source, part[3:].strip(), where), source, where))
            continue
        match = re.match(r"""^(?:"([^"]*)"|'([^']*)'|([A-Za-z_$][\w$]*))\s*(:|\()""", part)
        if match is None:
            raise VidgenError(f"{where}: cannot read the entry {part[:40]!r}")
        key = match.group(1) if match.group(1) is not None else match.group(2) if match.group(2) is not None else match.group(3)
        out[key] = part[match.end():].strip() if match.group(4) == ":" else ""
    return out


def array_strings(text: str, source: str = "", where: str = "the module") -> list[str]:
    """The strings of the array literal ``text`` (``...NAME`` spreads another array constant of ``source``)."""
    text = _unfreeze(text)
    if not (text.startswith("[") and text.endswith("]")):
        raise VidgenError(f"{where}: not an array literal: {text[:40]}")
    out: list[str] = []
    for part in _split_top(text[1:-1]):
        if part.startswith("..."):
            out += array_strings(constant_text(source, part[3:].strip(), where), source, where)
            continue
        value = _string(part)
        if value is None:
            raise VidgenError(f"{where}: {part[:40]!r} is not a string")
        out.append(value)
    return out


def constant_keys(module: str, name: str) -> list[str]:
    """The keys of the object constant ``name`` of the shipped module ``module``."""
    source = module_source(module)
    return list(object_entries(constant_text(source, name, module), source, module))


def constant_entries(module: str, name: str) -> dict[str, str]:
    """The entries of the object constant ``name`` of the shipped module ``module``: key -> its value's text."""
    source = module_source(module)
    return object_entries(constant_text(source, name, module), source, module)


def constant_strings(module: str, name: str) -> list[str]:
    """The strings of the array constant ``name`` of the shipped module ``module``."""
    source = module_source(module)
    return array_strings(constant_text(source, name, module), source, module)


def _field_object(text: str, field: str) -> str:
    """The object literal that ``field:`` holds inside the object literal ``text``."""
    match = re.search(rf"\b{field}:\s*\{{", text)
    if match is None:
        raise VidgenError(f"no {field}: object in {text[:40]!r}")
    start = match.end() - 1
    return text[start:_matching(text, start) + 1]


def _known_lists(source: str, where: str) -> dict[str, list[str]]:
    """Each ``known("<what> options", options, [...])`` call of a module: ``what`` -> its keys."""
    out: dict[str, list[str]] = {}
    for match in re.finditer(r'known\("(\w+) options", options, \[', source):
        start = match.end() - 1
        out[match.group(1)] = array_strings(source[start:_matching(source, start) + 1], source, where)
    return out


@lru_cache(maxsize=1)
def space_names() -> dict[str, Any]:
    """Everything a ``space`` scene's checks need, read from the shipped modules (module doc):

    ``worlds`` (ready-made worlds) and ``world_types`` (``rocky`` ...), ``world_options`` (the
    options a world of each type takes), ``airs``, ``ring_options``; ``sky_options``,
    ``sky_looks``, ``nebula_kinds``, ``galaxy_kinds``; ``stars`` (star kinds), ``star_options``,
    ``light_options``, ``exposures``; ``phenomena`` (kind -> its options); ``craft`` (kind -> its
    own options), ``craft_options`` (what every craft takes), ``attitudes``, ``details``;
    ``moves`` (move -> its options), ``phases``, ``lenses`` (name -> mm), ``views``;
    ``finish_options`` (option -> its sub-options, ``[]`` for a plain value); ``title_options``,
    ``end_options``."""
    bodies, bodies_src = "vidgen/space-bodies", module_source("vidgen/space-bodies")
    kinds = object_entries(constant_text(bodies_src, "KINDS", bodies), bodies_src, bodies)
    common = list(object_entries(constant_text(bodies_src, "COMMON", bodies), bodies_src, bodies))
    defaults = {k: list(object_entries(_field_object(v, "defaults"), bodies_src, bodies)) for k, v in kinds.items()}
    world_options = {k: [*common, *(o for o in v if o not in common)] for k, v in defaults.items()}
    light, light_src = "vidgen/space-light", module_source("vidgen/space-light")
    phen = "vidgen/space-phenomena"
    craft, craft_src = "vidgen/space-craft", module_source("vidgen/space-craft")
    craft_kinds = object_entries(constant_text(craft_src, "CRAFT", craft), craft_src, craft)
    own = {k: array_strings(re.search(r"options:\s*(\[[^\]]*\])", v).group(1), craft_src, craft) for k, v in craft_kinds.items()}  # type: ignore[union-attr]
    kit = constant_keys(craft, "KIT_DEFAULTS")
    every_craft = [k for k in dict.fromkeys([*kit, *constant_keys(craft, "CRAFT_DEFAULTS")]) if k not in ("fore", "kind")]
    camera, camera_src = "vidgen/space-camera", module_source("vidgen/space-camera")
    common_moves = constant_strings(camera, "COMMON")
    moves = _known_lists(camera_src, camera)
    moves["pass"] = [*moves["flyBy"], "side"]   # pass is a fly-by with its own defaults ("every flyBy option applies")
    lenses = object_entries(constant_text(camera_src, "LENSES", camera), camera_src, camera)
    finish, finish_src = "vidgen/three-finish", module_source("vidgen/three-finish")
    fin = object_entries(constant_text(finish_src, "DEFAULTS", finish), finish_src, finish)
    groups = {"dof": constant_keys(finish, "DOF_DEFAULTS"), "motionBlur": constant_keys(finish, "MOTION_DEFAULTS")}
    finish_options = {k: (list(object_entries(v, finish_src, finish)) if v.startswith("{") else groups.get(k, [])) for k, v in fin.items()}
    return {
        "worlds": constant_keys(bodies, "PRESETS"), "world_types": list(kinds), "world_options": world_options,
        "airs": constant_keys(bodies, "AIRS"), "ring_options": constant_strings(bodies, "RING_KEYS"),
        "world_qualities": constant_strings(bodies, "QUALITIES"),
        "sky_options": constant_keys("vidgen/space-sky", "DEFAULTS"), "sky_looks": constant_keys("vidgen/space-sky", "LOOKS"),
        "nebula_kinds": constant_strings("vidgen/space-sky", "NEBULA_KINDS"), "galaxy_kinds": constant_strings("vidgen/space-sky", "GALAXY_KINDS"),
        "stars": list(object_entries(constant_text(light_src, "STARS", light), light_src, light)),
        "star_options": constant_keys(light, "STAR_DEFAULTS"), "light_options": constant_keys(light, "LIGHT_DEFAULTS"),
        "exposures": constant_strings(light, "EXPOSURES"),
        "phenomena": {"black-hole": constant_keys(phen, "HOLE_DEFAULTS"), "wormhole": constant_keys(phen, "WORMHOLE_DEFAULTS"),
                      "warp": constant_keys(phen, "WARP_DEFAULTS"), "asteroids": constant_keys(phen, "ASTEROIDS_DEFAULTS"),
                      "asteroid": constant_keys(phen, "ASTEROID_DEFAULTS"), "comet": constant_keys(phen, "COMET_DEFAULTS"),
                      "aurora": constant_keys(phen, "AURORA_DEFAULTS")},
        "craft": own, "craft_options": every_craft, "attitudes": constant_strings(craft, "ATTITUDES"),
        "details": constant_strings(craft, "DETAILS"), "fly_options": constant_strings(craft, "FLY_KEYS"),
        "moves": {"arc": moves["arc"], "fly-by": moves["flyBy"], "pass": moves["pass"], "arrive": moves["arrive"], "reveal": moves["reveal"],
                  "follow": moves["follow"], "zoom": moves["zoom"], "look": moves["look"]},
        "move_common": common_moves,
        "phases": constant_keys(camera, "PHASES"), "lenses": {k: float(v) for k, v in lenses.items()}, "views": constant_keys(camera, "VIEWS"),
        "finish_options": finish_options,
        "title_options": constant_keys("vidgen/title-cards", "TITLE_DEFAULTS"), "end_options": constant_keys("vidgen/title-cards", "END_DEFAULTS"),
    }


__all__ = ["MODULES", "array_strings", "constant_entries", "constant_keys", "constant_strings", "constant_text", "module_source", "object_entries", "space_names"]
