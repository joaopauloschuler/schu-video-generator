"""JSON Schema export (``vidgen schema``): the schema of ``video.yaml`` and of scene params.

The schemas are generated from the pydantic models (``vidgen.config`` and each scene type's
``Params``) and then made as precise as the registered scene types allow, so an editor or an
AI agent can check a config before running ``vidgen validate``:

- ``scenes[].type`` is an ``enum`` of the registered types, and ``scenes[].params`` is checked
  against the ``Params`` schema of the scene's type (``allOf`` of ``if``/``then``); a type's
  beat count (``beat_count``) becomes ``minItems``/``maxItems`` of ``beats``;
- theme color/size params (``ThemeColor``/``ThemeSize``, marked ``x-vidgen-theme``) accept a
  hex color / positive number or one of the theme's token names (base config and variants);
- the silent-scene rule (``duration`` iff no beats), even ``width``/``height``, optional beat
  ids and the bodies of ``variants`` (partial configs) are expressed too.

What JSON Schema cannot say is left to ``vidgen validate``: unique scene/beat ids, asset files,
``validate_project`` checks and validators written in Python. Dialect: draft 2020-12.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from vidgen import __version__
from vidgen.config import HEX_COLOR_PATTERN, VideoConfig, parse_config
from vidgen.describe import scene_doc
from vidgen.errors import VidgenError
from vidgen.project import Project, find_config_file, read_config_file
from vidgen.registry import SceneType
from vidgen.theme import Theme

log = logging.getLogger("vidgen.schema")

DIALECT = "https://json-schema.org/draft/2020-12/schema"
#: Annotation on theme color/size params (set by ``vidgen.scene.ThemeToken``).
THEME_KEY = "x-vidgen-theme"
_REF_PREFIX = "#/$defs/"


def theme_tokens(themes: Iterable[Theme]) -> dict[str, list[str]]:
    """``{"color": [...], "size": [...]}``: the token names defined in any of ``themes``."""
    colors: set[str] = set()
    sizes: set[str] = set()
    for theme in themes:
        colors.update(theme.colors)
        sizes.update(theme.sizes)
    return {"color": sorted(colors), "size": sorted(sizes)}


def project_themes(project: Project | None, theme: Theme) -> list[Theme]:
    """``theme`` (the active one, with extension defaults) plus the theme of every variant of
    ``project`` that loads, so tokens a variant defines are accepted too."""
    themes = [theme]
    if project is None:
        return themes
    for name in project.config.variants:
        try:
            variant = Project.load(project.config_file, variant=name)
        except VidgenError:
            continue  # `vidgen validate` reports it
        themes.append(Theme(variant.config.theme))
    return themes


def lenient_project(path: str) -> Project:
    """Load the project at ``path`` for exporting its schema, even if its config is invalid.

    A schema is most needed while a config is broken, so when :meth:`Project.load` fails the
    project is loaded from a placeholder config that keeps the file's ``extensions`` and
    ``theme`` (each only if valid) and a warning is logged. A missing project still raises.
    """
    config_file = find_config_file(path).resolve()
    try:
        return Project.load(config_file)
    except VidgenError as exc:
        first = str(exc.problems[0]) if exc.problems else str(exc).splitlines()[0]
    try:
        raw = read_config_file(config_file)
    except VidgenError:
        raw = None
    data: dict[str, Any] = {"title": "schema", "scenes": [{"id": "s", "type": "s", "duration": 1}]}
    for key in ("extensions", "theme"):
        if isinstance(raw, dict) and key in raw:
            try:
                parse_config({**data, key: raw[key]})
            except VidgenError:
                continue
            data[key] = raw[key]
    log.warning(
        "%s is not valid (run `vidgen validate`); the schema uses its extensions and theme "
        "as far as they are valid. First problem: %s",
        config_file.name,
        first,
    )
    return Project(config_file.parent, config_file, parse_config(data, config_file.name), None)


# ----- helpers -----------------------------------------------------------------------------------


def _walk(node: Any) -> Iterable[dict[str, Any]]:
    """Every JSON object inside ``node`` (depth first, parents before children)."""
    if isinstance(node, dict):
        yield node
        for value in list(node.values()):
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _apply_theme(schema: dict[str, Any], tokens: dict[str, list[str]]) -> None:
    """Replace the type of every ``x-vidgen-theme`` node by ``hex|number`` or a token name."""
    for node in _walk(schema):
        kind = node.get(THEME_KEY)
        if kind not in ("color", "size"):
            continue
        for key in ("type", "anyOf", "pattern"):
            node.pop(key, None)
        literal = (
            {"type": "string", "pattern": HEX_COLOR_PATTERN}
            if kind == "color"
            else {"type": "number", "exclusiveMinimum": 0}
        )
        node["anyOf"] = [literal, {"enum": tokens[kind]}]


def _fix_dict_keys(schema: dict[str, Any]) -> None:
    """pydantic writes ``dict[Identifier, X]`` as ``patternProperties`` alone, which lets keys
    that do not match through; use ``propertyNames`` + ``additionalProperties`` instead."""
    for node in _walk(schema):
        patterns = node.get("patternProperties")
        if node.get("type") == "object" and isinstance(patterns, dict) and len(patterns) == 1 and "properties" not in node:
            (pattern, value), = patterns.items()
            del node["patternProperties"]
            node["propertyNames"] = {"pattern": pattern}
            node["additionalProperties"] = value


_LENGTH_KEYWORDS = {
    "array": {"minLength": "minItems", "maxLength": "maxItems"},
    "object": {"minLength": "minProperties", "maxLength": "maxProperties"},
    "string": {"minLength": "minLength", "maxLength": "maxLength"},
}


def _fix_union_lengths(schema: dict[str, Any]) -> None:
    """pydantic puts ``min_length``/``max_length`` of a union field on the ``anyOf`` as
    ``minLength``/``maxLength``, which only apply to strings; move them to each branch with the
    keyword of its type (``minItems`` for arrays, ``minProperties`` for objects)."""
    for node in _walk(schema):
        branches = node.get("anyOf")
        if not isinstance(branches, list) or "type" in node:
            continue
        for key in ("minLength", "maxLength"):
            if key not in node:
                continue
            value = node.pop(key)
            for branch in branches:
                keyword = _LENGTH_KEYWORDS.get(branch.get("type"), {}).get(key)
                if keyword is not None:
                    branch[keyword] = value


def _params(entry: SceneType, tokens: dict[str, list[str]], prefix: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The params schema of ``entry`` and its nested definitions (named ``<prefix><Model>``)."""
    model: type[BaseModel] | None = entry.params_model
    if model is None:
        return {"type": "object", "title": f"{entry.name} params", "description": "free-form params (no Params model)"}, {}
    schema = model.model_json_schema(ref_template=_REF_PREFIX + prefix + "{model}")
    defs = {prefix + name: value for name, value in schema.pop("$defs", {}).items()}
    schema["title"] = f"{entry.name} params"
    for part in (schema, defs):
        _apply_theme(part, tokens)
        _fix_dict_keys(part)
        _fix_union_lengths(part)
    return schema, defs


def _beat_limits(entry: SceneType) -> dict[str, Any] | None:
    """``then`` constraints for ``beats`` from the type's ``beat_count`` (``None``: any number)."""
    spec = entry.cls.beat_count
    if spec is None:
        return None
    lo, hi = (spec, spec) if isinstance(spec, int) else spec
    beats: dict[str, Any] = {}
    if lo:
        beats["minItems"] = lo
    if hi is not None:
        beats["maxItems"] = hi
    out: dict[str, Any] = {"properties": {"beats": beats}}
    if lo:
        out["required"] = ["beats"]
    return out


def _type_description(entry: SceneType) -> str:
    lines = [f"Scene type '{entry.name}' ({entry.origin})."]
    doc = scene_doc(entry)
    if doc:
        lines.append(doc)
    beats = entry.cls.beat_count_text()
    if beats:
        lines.append(f"Narrates {beats}.")
    return "\n\n".join(lines)


def _scene_schema(entries: list[SceneType], tokens: dict[str, list[str]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The schema of one ``scenes[]`` item and the definitions it refers to."""
    scene = copy.deepcopy(VideoConfig.model_json_schema()["$defs"]["SceneConfig"])
    defs: dict[str, Any] = {"BeatConfig": _beat_schema()}
    props = scene["properties"]
    props["type"] = {
        "description": props["type"].get("description", ""),
        "enum": [e.name for e in entries],
    }
    props["beats"]["items"] = {"$ref": _REF_PREFIX + "BeatConfig"}
    rules: list[dict[str, Any]] = [
        {
            # A narrated scene has no duration; a silent scene (no beats) needs one.
            "if": {"required": ["beats"], "properties": {"beats": {"minItems": 1}}},
            "then": {"properties": {"duration": {"type": "null"}}},
            "else": {"required": ["duration"], "properties": {"duration": {"type": "number", "exclusiveMinimum": 0}}},
        }
    ]
    for entry in entries:
        name = f"scene.{entry.name}"
        params, nested = _params(entry, tokens, f"{name}.")
        params["description"] = _type_description(entry)
        defs[name] = params
        defs.update(nested)
        then: dict[str, Any] = {"properties": {"params": {"$ref": _REF_PREFIX + name}}}
        if params.get("required"):
            then["required"] = ["params"]
        limits = _beat_limits(entry)
        if limits is not None:
            then["properties"].update(limits["properties"])
            then["required"] = then.get("required", []) + limits.get("required", [])
        rules.append({"if": {"required": ["type"], "properties": {"type": {"const": entry.name}}}, "then": then})
    scene["allOf"] = rules
    return scene, defs


def _beat_schema() -> dict[str, Any]:
    """BeatConfig with an optional ``id`` (filled in as ``<scene id>_b<n>`` when omitted)."""
    beat = copy.deepcopy(VideoConfig.model_json_schema()["$defs"]["BeatConfig"])
    beat["required"] = [r for r in beat["required"] if r != "id"]
    beat_id = beat["properties"]["id"]
    beat["properties"]["id"] = {
        "description": beat_id.pop("description", ""),
        "anyOf": [beat_id, {"type": "null"}],
    }
    return beat


def _document(title: str, description: str, schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """A top-level schema: ``$schema``, our title/description, ``schema``'s keywords, ``$defs``."""
    out: dict[str, Any] = {
        "$schema": DIALECT,
        "title": title,
        "description": description,
        "$comment": f"generated by vidgen {__version__}",
    }
    out.update((k, v) for k, v in schema.items() if k not in ("title", "description", "$defs"))
    if defs:
        out["$defs"] = dict(sorted(defs.items()))
    return out


# ----- public ------------------------------------------------------------------------------------


def params_schema(entry: SceneType, themes: Iterable[Theme]) -> dict[str, Any]:
    """The JSON Schema of one scene type's ``params`` (``vidgen schema --scene TYPE``)."""
    schema, defs = _params(entry, theme_tokens(themes), "")
    return _document(f"{entry.name} params", _type_description(entry), schema, defs)


def scene_schema(entries: list[SceneType], themes: Iterable[Theme]) -> dict[str, Any]:
    """The JSON Schema of one ``scenes[]`` item with every type's params (``vidgen schema --all``)."""
    scene, defs = _scene_schema(entries, theme_tokens(themes))
    description = "One item of `scenes` in video.yaml; `params` are checked against the schema of its `type`."
    return _document("vidgen scene", description, scene, defs)


def config_schema(entries: list[SceneType], themes: Iterable[Theme]) -> dict[str, Any]:
    """The JSON Schema of the whole ``video.yaml`` for the given scene types (``vidgen schema``)."""
    schema = VideoConfig.model_json_schema()
    _fix_dict_keys(schema)
    defs = schema.pop("$defs")
    scene, scene_defs = _scene_schema(entries, theme_tokens(themes))
    defs.update(scene_defs, SceneConfig=scene)
    props = schema["properties"]
    # A variant is a partial config deep-merged onto this one: the same keys, none required.
    variant_props = {key: copy.deepcopy(value) for key, value in props.items() if key != "variants"}
    props["variants"]["additionalProperties"] = {
        "type": "object",
        "description": "Partial config deep-merged onto the base config (mappings merge, lists replace).",
        "properties": variant_props,
        "additionalProperties": False,
    }
    description = (
        "Config of a vidgen video project (docs/CONFIG.md). Scene types: "
        + ", ".join(e.name for e in entries)
        + ". Not expressible here, checked by `vidgen validate`: unique scene and beat ids, "
        "files referenced by params, and checks written in Python."
    )
    return _document("vidgen video.yaml", description, schema, defs)
