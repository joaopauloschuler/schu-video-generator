"""Describe registered scene types: params with their types, defaults and docs.

Used by ``vidgen list-scenes`` for both the human listing (:func:`describe_params`) and the
``--json`` output (:func:`scene_type_json`).
"""

from __future__ import annotations

import inspect
import sys
import types
import typing
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from vidgen.registry import SceneType


def type_name(annotation: Any, metadata: Sequence[Any] = ()) -> str:
    """Readable type: ``color`` / ``size`` for theme tokens, ``a | b`` for unions and literals."""
    from vidgen.scene import ThemeToken

    for meta in metadata:
        if isinstance(meta, ThemeToken):
            return meta.kind
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin is typing.Annotated:
        return type_name(args[0], annotation.__metadata__)
    if origin in (typing.Union, types.UnionType):
        return " | ".join(type_name(a) for a in args)
    if origin is typing.Literal:
        return " | ".join(repr(a) for a in args)
    if origin is not None and args:
        name = getattr(origin, "__name__", str(origin))
        return f"{name}[{', '.join(type_name(a) for a in args)}]"
    if annotation is type(None):
        return "None"
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def nested_models(annotation: Any) -> list[type[BaseModel]]:
    """Pydantic models used inside a field type (``Ring``, ``list[Ring]``, ``Ring | None``...)."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for arg in typing.get_args(annotation):
        found += [m for m in nested_models(arg) if m not in found]
    return found


def describe_params(model: type[BaseModel] | None, indent: str = "", _seen: tuple[type, ...] = ()) -> list[str]:
    """``name: type [= default]`` for each field of a ``Params`` model (empty for plain dicts);
    the fields of nested models follow their field, indented."""
    if model is None:
        return []
    lines = []
    for name, field in model.model_fields.items():
        line = f"{indent}{name}: {type_name(field.annotation, field.metadata)}"
        if not field.is_required():
            default = field.get_default(call_default_factory=True)
            line += f" = {default!r}"
        lines.append(line)
        for nested in nested_models(field.annotation):
            if nested not in _seen:
                lines += describe_params(nested, indent + "    ", (*_seen, model, nested))
    return lines


def _jsonable(value: Any) -> Any:
    """``value`` as JSON data (tuples become lists, models dicts); ``repr`` if not convertible."""
    try:
        return to_jsonable_python(value)
    except Exception:  # noqa: BLE001 - any unconvertible default is shown as its repr
        return repr(value)


def params_json(model: type[BaseModel], _seen: tuple[type, ...] = ()) -> list[dict[str, Any]]:
    """One object per field of ``model``: ``{name, type, required, default, doc, nested}``.

    ``default`` is ``null`` for required fields; ``doc`` is the field's description (a
    ``Field(description=...)`` or the docstring under the attribute) or ``null``; ``nested``
    lists the fields of pydantic models used in the field's type, as ``{model, fields}``.
    """
    fields = []
    for name, field in model.model_fields.items():
        required = field.is_required()
        nested = [
            {"model": m.__name__, "fields": params_json(m, (*_seen, model, m))}
            for m in nested_models(field.annotation)
            if m not in _seen
        ]
        fields.append(
            {
                "name": name,
                "type": type_name(field.annotation, field.metadata),
                "required": required,
                "default": None if required else _jsonable(field.get_default(call_default_factory=True)),
                "doc": field.description,
                "nested": nested,
            }
        )
    return fields


def _beats_json(entry: SceneType) -> dict[str, Any] | None:
    spec = entry.cls.beat_count
    if spec is None:
        return None
    lo, hi = (spec, spec) if isinstance(spec, int) else spec
    return {"min": lo, "max": hi, "text": entry.cls.beat_count_text()}


def _doc(entry: SceneType) -> str | None:
    """The class's own docstring, else its module's docstring, cleaned; ``None`` if neither."""
    doc = entry.cls.__dict__.get("__doc__")
    if not doc:
        module = sys.modules.get(entry.cls.__module__)
        doc = getattr(module, "__doc__", None)
    return inspect.cleandoc(doc) if doc else None


def scene_type_json(entry: SceneType) -> dict[str, Any]:
    """``{name, origin, builtin, overrides_builtin, doc, beats, params}`` for ``list-scenes --json``.

    ``beats`` is ``null`` (any number) or ``{min, max, text}`` (``max`` ``null`` = no limit);
    ``params`` is ``null`` when the type takes free-form params (no ``Params`` model).
    """
    model = entry.params_model
    return {
        "name": entry.name,
        "origin": entry.origin,
        "builtin": entry.builtin,
        "overrides_builtin": entry.overrides is not None,
        "doc": _doc(entry),
        "beats": _beats_json(entry),
        "params": None if model is None else params_json(model),
    }
