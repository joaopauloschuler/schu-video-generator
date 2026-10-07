"""Translations: a video's texts in another language from a translation file (DESIGN.md §54).

A variant (or the config itself) names a YAML **translation file** with ``translations:``.
Every translatable text of the config is listed there under a stable **key** — its path in the
config, with scenes, beats and overlays named by their ids — with the source text, a hash of it
and the translation::

    entries:
      scenes.intro.beats.intro_b1.text:
        source: What if a model could ...
        hash: 3f2a9c1b7e
        text: E se um modelo pudesse ...
      scenes.list.params.items[0]: {source: Faster, hash: 1b2c3d4e5f, text: Mais rápido}

When the project loads, the texts are replaced in the raw config before it is validated, so
everything downstream — narration, TTS, subtitles, captions, on-screen text, chapters, the
thumbnail — sees the translated video. A key without a translation (or whose source changed
since it was translated: *stale*) keeps the source text; ``vidgen validate`` lists them.

**What is translatable** is declared by the models: a ``Params`` / options field typed
:data:`TranslatableStr` (or a model's :attr:`text_shorthand` / :attr:`text_defaults`) holds
on-screen text; a :data:`TextRef` field names such a text (a bar chart's ``highlight: "4K"``) and
follows its translation. Beat texts, a scene's ``chapter``, the video ``title``, ``metadata``
texts, ``chapters.intro`` and the thumbnail's ``title`` / ``subtitle`` are translatable too.
Applying a file needs no scene types (the keys are plain paths); listing the texts
(:func:`extract_texts`, ``vidgen translate-template``) needs the registered models.

**Key syntax**: ``.name`` a mapping key (or, in ``scenes`` / ``beats`` / ``overlays``, the item
with that id), ``[3]`` a list item, ``["any key"]`` a mapping value under a key that is not a
name, ``{"key"}`` the mapping key itself (the text is the key, e.g. a chart series name),
``=field`` a shorthand string standing for ``{field: string}`` (a diagram node ``Data`` is
``{id: Data}``; the next field defaults to that one), ``$:`` the text after the first ``:`` of
a shorthand string (``"a -> b: label"``).

No manim import.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import types
import typing
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, NamedTuple, Union

from pydantic import BaseModel, ConfigDict, Field, GetJsonSchemaHandler, ValidationError, field_validator, model_validator

from vidgen.config import ACTION_KEYS, OVERLAY_KEYS, LanguageTag, validation_problems
from vidgen.errors import Problem, VidgenError

if TYPE_CHECKING:
    from vidgen.project import Project

# ----- markers -----------------------------------------------------------------------------------


class TextMarker(NamedTuple):
    """Marker in a field's annotation: ``kind`` ``"text"`` (on-screen text a translation
    replaces) or ``"ref"`` (names such a text of the same scene and follows its translation)."""

    kind: str

    def __get_pydantic_json_schema__(self, core_schema: Any, handler: GetJsonSchemaHandler) -> dict[str, Any]:
        """Mark the field's JSON Schema with ``x-vidgen-text: text|ref``."""
        schema = handler(core_schema)
        schema["x-vidgen-text"] = self.kind
        return schema


TRANSLATABLE = TextMarker("text")
TEXT_REF = TextMarker("ref")
#: A ``Params`` / options field holding text shown on screen (listed by ``vidgen
#: translate-template`` and replaced by a translation file).
TranslatableStr = Annotated[str, TRANSLATABLE]
#: A field naming a text of the same scene (a label used as an id: ``highlight: "4K"``); it is
#: not listed for translators and follows the translation of the text it names.
TextRef = Annotated[str, TEXT_REF]

#: Top-level texts (besides scenes and overlays) and the ``metadata`` tags that are text.
TOP_LEVEL_TEXTS: tuple[str, ...] = ("title",)
METADATA_TEXTS: tuple[str, ...] = ("title", "album", "comment", "description")
THUMBNAIL_TEXTS: tuple[str, ...] = ("title", "subtitle")

# ----- keys --------------------------------------------------------------------------------------


class Seg(NamedTuple):
    """One step of a key: ``kind`` ``field`` (``.name``), ``index`` (``[3]``), ``item``
    (``["key"]``), ``key`` (``{"key"}``: the key itself), ``as`` (``=field``) or ``after``
    (``$:``)."""

    kind: str
    value: Any


_NAME = re.compile(r"[A-Za-z0-9_]+")
_STRING = r'"(?:[^"\\]|\\.)*"'
_TOKEN = re.compile(rf"\.([A-Za-z0-9_]+)|\[(\d+)\]|\[({_STRING})\]|\{{({_STRING})\}}|=([A-Za-z0-9_]+)|\$(.)")


def format_key(segs: Sequence[Seg]) -> str:
    """The key text of ``segs`` (the first a field name without a dot)."""
    out = ""
    for seg in segs:
        if seg.kind == "field":
            out += f".{seg.value}" if out else seg.value
        elif seg.kind == "index":
            out += f"[{seg.value}]"
        elif seg.kind == "item":
            out += f".{seg.value}" if _NAME.fullmatch(seg.value) else f"[{json.dumps(seg.value, ensure_ascii=False)}]"
        elif seg.kind == "key":
            out += "{" + json.dumps(seg.value, ensure_ascii=False) + "}"
        elif seg.kind == "as":
            out += f"={seg.value}"
        else:
            out += f"${seg.value}"
    return out


def parse_key(key: str) -> list[Seg]:
    """The steps of a key; ``ValueError`` when it is not one."""
    first = _NAME.match(key)
    if first is None:
        raise ValueError(f"{key!r} is not a translation key (it starts with a config key such as title or scenes)")
    segs = [Seg("field", first.group())]
    pos = first.end()
    while pos < len(key):
        match = _TOKEN.match(key, pos)
        if match is None:
            raise ValueError(f"{key!r} is not a translation key (cannot read it from {key[pos:]!r})")
        name, index, item, mapkey, as_field, after = match.groups()
        if name is not None:
            segs.append(Seg("field", name))
        elif index is not None:
            segs.append(Seg("index", int(index)))
        elif item is not None:
            segs.append(Seg("item", json.loads(item)))
        elif mapkey is not None:
            segs.append(Seg("key", json.loads(mapkey)))
        elif as_field is not None:
            segs.append(Seg("as", as_field))
        else:
            segs.append(Seg("after", after))
        pos = match.end()
    for k, seg in enumerate(segs[:-1]):
        if seg.kind in ("key", "after"):
            raise ValueError(f"{key!r}: {format_key([seg])} must be the last step")
    return segs


def source_hash(text: str) -> str:
    """The hash stored with a translation: the first 10 hex digits of the source text's sha1."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


# ----- reading and writing the config by key -----------------------------------------------------


def default_overlay_ids(overlays: Sequence[Any]) -> list[str | None]:
    """Ids of raw ``overlays:`` entries as :mod:`vidgen.overlays` gives them: ``id``, else the
    type (``<type><n>`` when several entries without an id share it)."""
    types_ = [o.get("type") if isinstance(o, dict) and o.get("id") is None else None for o in overlays]
    counts = {t: types_.count(t) for t in types_ if t is not None}
    seen: dict[str, int] = {}
    out: list[str | None] = []
    for o, t in zip(overlays, types_):
        if isinstance(o, dict) and o.get("id") is not None:
            out.append(str(o["id"]))
        elif isinstance(t, str):
            seen[t] = seen.get(t, 0) + 1
            out.append(t if counts[t] == 1 else f"{t}{seen[t]}")
        else:
            out.append(None)
    return out


def _item_ids(owner: Any, name: Any, items: list[Any]) -> list[str | None]:
    """Ids of the items of the list ``owner[name]``: beats default to ``<scene id>_b<n>``,
    overlays to their type; others by ``id``."""
    if name == "overlays" and isinstance(owner, dict) and "scenes" in owner:
        return default_overlay_ids(items)
    out: list[str | None] = []
    for n, item in enumerate(items, start=1):
        ident = item.get("id") if isinstance(item, dict) else None
        if ident is None and name == "beats" and isinstance(owner, dict) and isinstance(owner.get("id"), str):
            ident = f"{owner['id']}_b{n}"
        out.append(None if ident is None else str(ident))
    return out


class _Cursor:
    """Where a key leads in a raw config: a ``get`` / ``set`` of the text it names."""

    def __init__(self, data: Any, segs: Sequence[Seg]) -> None:
        self.ok = False
        self._wrappers: list[tuple[dict[str, Any], Any, Any, int]] = []  # (virtual, container, key, size)
        node: Any = data
        container: Any = None
        slot: Any = None
        owner: Any = None
        name: Any = None
        default_from: str | None = None
        for seg in segs[:-1]:
            if seg.kind == "as":
                if not isinstance(node, dict):
                    virtual = {seg.value: node}
                    self._wrappers.append((virtual, container, slot, 1))
                    node = virtual
                default_from = seg.value
                continue
            step = self._step(node, seg, owner, name)
            if step is None:
                return
            owner, name = node, seg.value
            container, slot = node, step
            node = node[step]
            default_from = None
        last = segs[-1]
        self.kind = last.kind
        if last.kind == "after":
            if not isinstance(node, str) or last.value not in node:
                return
            self.container, self.slot, self.sep = container, slot, last.value
        elif last.kind == "key":
            if not isinstance(node, dict) or last.value not in node:
                return
            self.container, self.slot = node, last.value
        elif last.kind == "as":
            return
        else:
            if isinstance(node, dict) and last.kind == "field" and last.value not in node and default_from in node:
                self.default = node[default_from]
                self.container, self.slot = node, last.value
                self.ok = isinstance(self.default, str)
                return
            step = self._step(node, last, owner, name)
            if step is None:
                return
            self.container, self.slot = node, step
        self.default = None
        self.ok = isinstance(self.get(), str)

    @staticmethod
    def _step(node: Any, seg: Seg, owner: Any, name: Any) -> Any:
        if isinstance(node, dict) and seg.kind in ("field", "item"):
            return seg.value if seg.value in node else None
        if isinstance(node, list):
            if seg.kind == "index":
                return seg.value if seg.value < len(node) else None
            if seg.kind == "field":
                ids = _item_ids(owner, name, node)
                return ids.index(seg.value) if seg.value in ids else None
        return None

    def get(self) -> str | None:
        """The text the key names now (``None`` if it names none)."""
        if self.kind == "key":
            return self.slot if isinstance(self.slot, str) else None
        if getattr(self, "default", None) is not None and self.slot not in self.container:
            return self.default
        value = self.container[self.slot]
        if self.kind == "after":
            return value.split(self.sep, 1)[1].strip() or None
        return value if isinstance(value, str) else None

    def set(self, text: str) -> None:
        """Replace the text the key names with ``text``."""
        if self.kind == "key":
            items = list(self.container.items())
            self.container.clear()
            self.container.update((text if k == self.slot else k, v) for k, v in items)
            return
        if self.kind == "after":
            left = self.container[self.slot].split(self.sep, 1)[0].rstrip()
            self.container[self.slot] = f"{left}{self.sep} {text}"
            return
        self.container[self.slot] = text
        for virtual, container, key, size in reversed(self._wrappers):
            if len(virtual) > size and container is not None:
                container[key] = virtual


def read_text(data: Any, key: str) -> str | None:
    """The text ``key`` names in the raw config ``data``, or ``None`` (not there / not text)."""
    cursor = _Cursor(data, parse_key(key))
    return cursor.get() if cursor.ok else None


# ----- the translation file ----------------------------------------------------------------------


class TranslationEntry(BaseModel):
    """One text of a translation file: the ``source`` text, its ``hash`` and the translation
    ``text`` (empty: not translated yet)."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    source: str | None = None
    """The text in the source language (for the translator; the hash decides)."""
    hash: str | None = None
    """source_hash of the source text when it was translated; a different hash now marks the translation stale."""
    text: str | None = None
    """The translation; empty or missing: the source text is shown."""
    stale: bool = False
    """The source changed since the text was translated (set by translate-template): not used until a person checks it and removes the flag."""
    old_source: str | None = None
    """The source text the stale translation was made from."""
    obsolete: bool = False
    """The key no longer exists in the config (kept by translate-template so the text is not lost)."""

    @property
    def translated(self) -> bool:
        """True when ``text`` holds a translation."""
        return bool(self.text and self.text.strip())


class TranslationFile(BaseModel):
    """A translation file (``vidgen translate-template``)."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    version: Literal[1] = 1
    """File format version."""
    language: LanguageTag | None = None
    """Language of the translations (BCP-47)."""
    source_language: LanguageTag | None = None
    """Language of the source texts."""
    entries: dict[str, TranslationEntry] = Field(default_factory=dict)
    """Translatable texts by key: {source, hash, text, stale, old_source, obsolete}, or the translation alone."""
    references: dict[str, str] = Field(default_factory=dict)
    """Places that name a translated text (key: the key of that text); written by translate-template."""

    @field_validator("entries", mode="before")
    @classmethod
    def _short_entries(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: {"text": v} if isinstance(v, str) or v is None else v for k, v in value.items()}
        return value

    @model_validator(mode="after")
    def _keys(self) -> TranslationFile:
        bad = []
        for key in [*self.entries, *self.references, *self.references.values()]:
            try:
                parse_key(key)
            except ValueError as exc:
                bad.append(str(exc))
        if bad:
            raise ValueError("; ".join(bad))
        return self


def read_translation_file(path: Path, rel: str) -> TranslationFile:
    """The translation file at ``path`` (``rel``: as written in the config); ``VidgenError``
    with ``translations (<rel>)`` problems if it is missing or invalid."""
    from vidgen.project import read_config_file

    where = f"translations ({rel})"
    if not path.is_file():
        message = f"file not found: {rel} (looked for {path}); `vidgen translate-template --variant NAME` writes it"
        raise VidgenError(f"translations: {message}", problems=[Problem("translations", message)])
    try:
        data = read_config_file(path)
    except VidgenError as exc:
        raise VidgenError(str(exc), problems=[Problem(where, str(exc))]) from None
    try:
        return TranslationFile.model_validate(data if data is not None else {})
    except ValidationError as exc:
        problems = [Problem(f"{where}.{p.location}" if p.location else where, p.message) for p in validation_problems(exc, model=TranslationFile, noun="key")]
        raise VidgenError(f"{rel}: invalid translation file\n" + "\n".join(f"  {p}" for p in problems), problems=problems) from None


_HEADER = """\
# Translation of {title!r} ({what}), written by `vidgen translate-template`.
# Fill in each `text:` (the `source:` is the original; an empty text shows the source).
# `stale: true`: the source changed since it was translated; check the text, then delete the
# `stale` and `old_source` lines. `obsolete: true`: the key is gone from the config (kept so the
# text is not lost; delete it when done). Run the command again after editing the config: it
# keeps your translations. `references` are written by the command (do not edit them).
"""


def _entry_dict(entry: TranslationEntry) -> dict[str, Any]:
    out: dict[str, Any] = {"source": entry.source, "hash": entry.hash, "text": entry.text}
    if entry.stale:
        out["stale"] = True
    if entry.old_source is not None:
        out["old_source"] = entry.old_source
    if entry.obsolete:
        out["obsolete"] = True
    return out


def dump_translation_file(doc: TranslationFile, title: str, what: str) -> str:
    """The YAML text of ``doc`` with an explanatory header (``what``: e.g. ``variant 'pt'``)."""
    import yaml

    body: dict[str, Any] = {"version": doc.version}
    if doc.language is not None:
        body["language"] = doc.language
    if doc.source_language is not None:
        body["source_language"] = doc.source_language
    body["entries"] = {key: _entry_dict(entry) for key, entry in doc.entries.items()}
    if doc.references:
        body["references"] = dict(doc.references)
    text = yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=100, default_flow_style=False)
    return _HEADER.format(title=title, what=what) + text


# ----- applying a file ---------------------------------------------------------------------------


@dataclass
class TranslationReport:
    """What applying a translation file did: ``applied`` key -> (source, translation), keys whose
    translation is ``stale`` (not used), ``unknown`` keys (nothing at that place of the config;
    obsolete ones not included), keys still ``untranslated`` in the file, and ``broken``
    references (the place no longer names the text)."""

    file: str
    language: str | None
    applied: dict[str, tuple[str, str]] = field(default_factory=dict)
    stale: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    untranslated: list[str] = field(default_factory=list)
    broken: list[str] = field(default_factory=list)
    references: dict[str, str] = field(default_factory=dict)
    #: The file does not exist (yet): nothing was translated.
    missing: bool = False


def apply_translations(data: dict[str, Any], doc: TranslationFile, rel: str = "") -> tuple[dict[str, Any], TranslationReport]:
    """``data`` (a raw config mapping, not modified) with the translations of ``doc`` in place,
    and a :class:`TranslationReport`. Texts first, then mapping keys, then references."""
    out = copy.deepcopy(data)
    report = TranslationReport(rel, doc.language, references=dict(doc.references))
    ordered = sorted(doc.entries.items(), key=lambda kv: parse_key(kv[0])[-1].kind == "key")
    for key, entry in ordered:
        cursor = _Cursor(out, parse_key(key))
        if not cursor.ok:
            if not entry.obsolete:
                report.unknown.append(key)
            continue
        current = cursor.get()
        assert current is not None
        if not entry.translated:
            report.untranslated.append(key)
            continue
        changed = (entry.hash is not None and entry.hash != source_hash(current)) or (
            entry.hash is None and entry.source is not None and entry.source != current
        )
        if entry.stale or changed:
            report.stale.append(key)
            continue
        text = entry.text or ""
        if not current.endswith("\n"):
            text = text.rstrip("\n")  # a YAML block scalar ends with a line break
        cursor.set(text)
        report.applied[key] = (current, text)
    for place, key in doc.references.items():
        if key not in report.applied:
            continue
        source, text = report.applied[key]
        cursor = _Cursor(out, parse_key(place))
        value = cursor.get() if cursor.ok else None
        renamed = _renamed(value, source, text) if value is not None else None
        if renamed is not None:
            cursor.set(renamed)
        elif value is None or _renamed(value, text, text) is None:
            report.broken.append(place)
    return out, report


# ----- listing the texts of a config (needs the models) ------------------------------------------


@dataclass(frozen=True)
class TextItem:
    """A translatable text: its ``key`` and ``source`` (the text in the config now)."""

    key: str
    source: str


#: ``model_for(name) -> Params / Options model or None`` for scene types, actions, overlay types.
ModelLookup = Callable[[str], "type[BaseModel] | None"]


@dataclass
class _Sink:
    texts: list[TextItem] = field(default_factory=list)
    refs: list[tuple[str, str]] = field(default_factory=list)

    def text(self, path: Sequence[Seg], value: str) -> None:
        if value.strip():
            self.texts.append(TextItem(format_key(path), value))

    def ref(self, path: Sequence[Seg], value: str) -> None:
        self.refs.append((format_key(path), value))


def _strip(ann: Any) -> tuple[Any, list[TextMarker]]:
    markers: list[TextMarker] = []
    while typing.get_origin(ann) is Annotated:
        args = typing.get_args(ann)
        markers += [m for m in args[1:] if isinstance(m, TextMarker)]
        ann = args[0]
    return ann, markers


def _is_union(ann: Any) -> bool:
    return typing.get_origin(ann) in (Union, types.UnionType)


def _is_model(ann: Any) -> bool:
    return isinstance(ann, type) and issubclass(ann, BaseModel)


def _shorthand(model: type[BaseModel], kind: type) -> Any:
    return dict(getattr(model, "text_shorthand", {}) or {}).get(kind)


def _rank(ann: Any, value: Any) -> int | None:
    """How well ``ann`` takes the raw ``value`` (lower is better; ``None``: it does not)."""
    base, markers = _strip(ann)
    origin = typing.get_origin(base)
    if _is_union(base):
        ranks = [r for r in (_rank(a, value) for a in typing.get_args(base)) if r is not None]
        return min(ranks) if ranks else None
    if isinstance(value, str):
        if base is str:
            return 0 if markers else 1
        if origin is Literal:
            return 1 if value in typing.get_args(base) else None
        if _is_model(base):
            return 2 if str in getattr(base, "also_accepts", ()) else None
        return None
    if isinstance(value, (bool, int, float)):
        kinds = (bool,) if isinstance(value, bool) else (int, float)
        if base in kinds or (origin is Literal and value in typing.get_args(base)):
            return 0
        return 2 if _is_model(base) and any(k in getattr(base, "also_accepts", ()) for k in kinds) else None
    if isinstance(value, list):
        if origin in (list, tuple):
            args = typing.get_args(base)
            if value and args and not (origin is tuple and args[-1] is not Ellipsis):
                return _rank(args[0], value[0])
            return 0
        if _is_model(base) and list in getattr(base, "also_accepts", ()):
            return 1
        return 2 if base in (list, tuple) else None
    if isinstance(value, dict):
        if _is_model(base):
            names = _field_names(base)
            return 10 - sum(1 for k in value if k in names)
        return 11 if origin in (dict, Mapping) or base is dict else None
    return None


def _field_names(model: type[BaseModel]) -> set[str]:
    names: set[str] = set()
    for name, info in model.model_fields.items():
        names.update(_raw_keys(name, info))
    return names


def _raw_keys(name: str, info: Any) -> list[str]:
    keys = [name]
    if info.alias:
        keys.append(info.alias)
    choices = getattr(info.validation_alias, "choices", None)
    if choices:
        keys += [c for c in choices if isinstance(c, str)]
    elif isinstance(info.validation_alias, str):
        keys.append(info.validation_alias)
    return list(dict.fromkeys(keys))


def walk_value(ann: Any, value: Any, path: list[Seg], sink: _Sink) -> None:
    """Report the translatable texts and text references in the raw ``value`` of a field typed
    ``ann`` at ``path``."""
    if value is None or isinstance(value, (bool, int, float)):
        return
    base, markers = _strip(ann)
    if isinstance(value, str) and markers and base is str:
        (sink.text if markers[0].kind == "text" else sink.ref)(path, value)
        return
    if _is_union(base):
        ranked = sorted(
            ((r, k, a) for k, a in enumerate(typing.get_args(base)) if (r := _rank(a, value)) is not None),
            key=lambda t: (t[0], t[1]),
        )
        if ranked:
            walk_value(ranked[0][2], value, path, sink)
        return
    origin = typing.get_origin(base)
    args = typing.get_args(base)
    if _is_model(base):
        _walk_model(base, value, path, sink)
    elif origin in (list, tuple) and isinstance(value, list):
        positional = origin is tuple and args and args[-1] is not Ellipsis
        for i, item in enumerate(value):
            if positional and i >= len(args):
                break
            walk_value(args[i] if positional else (args[0] if args else Any), item, [*path, Seg("index", i)], sink)
    elif origin in (dict, Mapping) and isinstance(value, dict) and len(args) == 2:
        _, key_markers = _strip(args[0])
        for key, item in value.items():
            if key_markers and isinstance(key, str):
                (sink.text if key_markers[0].kind == "text" else sink.ref)([*path, Seg("key", key)], key)
            walk_value(args[1], item, [*path, Seg("item", str(key))], sink)


def _walk_model(model: type[BaseModel], value: Any, path: list[Seg], sink: _Sink) -> None:
    """A model's raw value: a mapping of its fields, or a shorthand (``text_shorthand``)."""
    if isinstance(value, (str, list)):
        how = _shorthand(model, type(value))
        if how is None:
            return
        if how == "text" and isinstance(value, str):
            sink.text(path, value)
        elif how[0] == "after" and isinstance(value, str):
            if how[1] in value and value.split(how[1], 1)[1].strip():
                sink.text([*path, Seg("after", how[1])], value.split(how[1], 1)[1].strip())
        elif how[0] == "field":
            _walk_model(model, {how[1]: value}, [*path, Seg("as", how[1])], sink)
        elif how[0] == "fields" and isinstance(value, list):
            for i, (name, item) in enumerate(zip(how[1], value)):
                info = model.model_fields[name]
                walk_value(_annotation(info), item, [*path, Seg("index", i)], sink)
        return
    if not isinstance(value, dict):
        return
    other = _shorthand(model, dict)
    if other is not None and not set(value) & _field_names(model):
        walk_value(other[1], value, path, sink)   # ("model", M): a mapping of another model's fields
        return
    defaults = dict(getattr(model, "text_defaults", {}) or {})
    for name, info in model.model_fields.items():
        keys = [k for k in _raw_keys(name, info) if k in value]
        if name in defaults:
            source = value.get(keys[0]) if keys else value.get(defaults[name])
            prefix = path if path and path[-1] == Seg("as", defaults[name]) else [*path, Seg("as", defaults[name])]
            if isinstance(source, str):
                sink.text([*prefix, Seg("field", name)], source)
            continue
        if keys:
            walk_value(_annotation(info), value[keys[0]], [*path, Seg("item", keys[0])], sink)


def _annotation(info: Any) -> Any:
    """A pydantic field's type with its metadata (pydantic moves ``Annotated`` extras there)."""
    return Annotated[(info.annotation, *info.metadata)] if info.metadata else info.annotation


def _action_parts(raw: dict[str, Any], known: Callable[[str], bool]) -> tuple[str | None, str | None]:
    """``(action name, key holding the targets)`` of a raw action (canonical or shorthand)."""
    if "action" in raw:
        return (str(raw["action"]), "target")
    names = [k for k in raw if isinstance(k, str) and k not in ACTION_KEYS]
    if not names:
        return None, None
    chosen = names[0] if known(names[0]) or len([k for k in names if known(k)]) != 1 else next(k for k in names if known(k))
    return chosen, chosen


def extract_texts(
    data: Mapping[str, Any],
    scene_model: ModelLookup,
    action_model: ModelLookup,
    overlay_model: ModelLookup,
) -> tuple[list[TextItem], dict[str, str]]:
    """Every translatable text of the raw config ``data`` in config order, and the references:
    places (action targets ``kind:<label>``, :data:`TextRef` fields) that name a text of their
    scene, mapped to that text's key."""
    sink = _Sink()
    references: dict[str, str] = {}
    for name in TOP_LEVEL_TEXTS:
        if isinstance(data.get(name), str):
            sink.text([Seg("field", name)], data[name])
    for group, names in (("metadata", METADATA_TEXTS), ("thumbnail", THUMBNAIL_TEXTS)):
        section = data.get(group)
        if isinstance(section, dict):
            for name in names:
                if isinstance(section.get(name), str):
                    sink.text([Seg("field", group), Seg("field", name)], section[name])
    chapters = data.get("chapters")
    if isinstance(chapters, dict) and isinstance(chapters.get("intro"), str):
        sink.text([Seg("field", "chapters"), Seg("field", "intro")], chapters["intro"])
    overlays = data.get("overlays") if isinstance(data.get("overlays"), list) else []
    overlay_types: dict[str, str] = {}
    for entry, oid in zip(overlays, default_overlay_ids(overlays)):
        if not isinstance(entry, dict) or oid is None:
            continue
        overlay_types[oid] = str(entry.get("type"))
        _walk_options(overlay_model(str(entry.get("type"))), entry, OVERLAY_KEYS, [Seg("field", "overlays"), Seg("field", oid)], sink)
    for scene in data.get("scenes", []) if isinstance(data.get("scenes"), list) else []:
        if not isinstance(scene, dict) or not isinstance(scene.get("id"), str):
            continue
        _scene_texts(scene, scene_model, action_model, overlay_model, overlay_types, sink, references)
    return sink.texts, references


def _walk_options(model: type[BaseModel] | None, raw: dict[str, Any], common: Sequence[str], path: list[Seg], sink: _Sink) -> None:
    if model is not None:
        _walk_model(model, {k: v for k, v in raw.items() if k not in common}, path, sink)


def _scene_texts(
    scene: dict[str, Any],
    scene_model: ModelLookup,
    action_model: ModelLookup,
    overlay_model: ModelLookup,
    overlay_types: dict[str, str],
    sink: _Sink,
    references: dict[str, str],
) -> None:
    sid = scene["id"]
    base = [Seg("field", "scenes"), Seg("field", sid)]
    chapter = scene.get("chapter")
    if isinstance(chapter, str):
        sink.text([*base, Seg("field", "chapter")], chapter)
    elif isinstance(chapter, dict) and isinstance(chapter.get("title"), str):
        sink.text([*base, Seg("field", "chapter"), Seg("field", "title")], chapter["title"])
    first_text, first_ref = len(sink.texts), len(sink.refs)
    model = scene_model(str(scene.get("type")))
    if model is not None and isinstance(scene.get("params"), dict):
        _walk_model(model, scene["params"], [*base, Seg("field", "params")], sink)
    params_texts = {item.source: item.key for item in sink.texts[first_text:]}
    refs = sink.refs[first_ref:]
    del sink.refs[first_ref:]
    beats = scene.get("beats") if isinstance(scene.get("beats"), list) else []
    ids = _item_ids(scene, "beats", beats)
    for beat, bid in zip(beats, ids):
        if not isinstance(beat, dict) or bid is None:
            continue
        path = [*base, Seg("field", "beats"), Seg("field", bid)]
        if isinstance(beat.get("text"), str):
            sink.text([*path, Seg("field", "text")], beat["text"])
        actions = beat.get("actions") if isinstance(beat.get("actions"), list) else []
        for k, raw in enumerate(actions):
            if not isinstance(raw, dict):
                continue
            name, target_key = _action_parts(raw, lambda n: action_model(n) is not None)
            if name is None:
                continue
            at = [*path, Seg("field", "actions"), Seg("index", k)]
            _walk_options(action_model(name), raw, (*ACTION_KEYS, target_key or "target"), at, sink)
            targets = raw.get(target_key) if target_key else None
            if isinstance(targets, str):
                refs.append((format_key([*at, Seg("item", target_key)]), targets))
            elif isinstance(targets, list):
                refs += [
                    (format_key([*at, Seg("item", target_key), Seg("index", i)]), t) for i, t in enumerate(targets) if isinstance(t, str)
                ]
    own = scene.get("overlays")
    if isinstance(own, dict):
        for key, value in own.items():
            if isinstance(value, dict):
                kind = value.get("type") or overlay_types.get(str(key))
                if isinstance(kind, str):
                    _walk_options(overlay_model(kind), value, OVERLAY_KEYS, [*base, Seg("field", "overlays"), Seg("item", str(key))], sink)
    for place, value in refs:
        named = next((part for part in _named_parts(value) if part in params_texts), None)
        if named is not None:
            references[place] = params_texts[named]


def _named_parts(value: str) -> list[str]:
    """The parts of a reference that may name a text: all of it, what follows ``kind:``, and
    what comes before an ``@`` of those (``point:<series>@<label>`` names the series)."""
    parts = [value]
    if ":" in value:
        parts.append(value.split(":", 1)[1])
    parts += [p.split("@", 1)[0] for p in list(parts) if "@" in p]
    return parts


def _renamed(value: str, source: str, text: str) -> str | None:
    """``value`` (a reference) with the name ``source`` replaced by ``text``, where
    :func:`_named_parts` would find it; ``None`` when it does not name ``source``."""
    if value == source:
        return text
    kind, sep, rest = value.partition(":")
    for head, tail in ((kind + sep, rest), ("", value)) if sep else (("", value),):
        if tail == source:
            return head + text
        if tail.startswith(source + "@"):
            return head + text + tail[len(source):]
    return None


# ----- the template: listing merged with an existing file ----------------------------------------


@dataclass
class MergeStats:
    """What :func:`merge_template` did: keys ``untranslated`` (listed without a translation),
    ``kept`` (translation still current), ``stale`` (source changed: text kept and marked),
    ``moved`` (a translation found under another key of the scene with the same source),
    ``obsolete`` (translated keys gone from the config, kept and marked), ``dropped``
    (untranslated keys gone)."""

    untranslated: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    moved: list[str] = field(default_factory=list)
    obsolete: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)

    @property
    def translated(self) -> int:
        """Keys with a current translation."""
        return len(self.kept) + len(self.moved)


def _group(key: str) -> str:
    """Texts may move between keys within one scene (a list item inserted before them)."""
    segs = parse_key(key)
    return format_key(segs[:2]) if segs[0].value == "scenes" and len(segs) > 1 else ""


def _entry_hash(entry: TranslationEntry) -> str | None:
    if entry.hash is not None:
        return entry.hash
    return source_hash(entry.source) if entry.source is not None else None


def merge_template(
    items: Sequence[TextItem],
    references: Mapping[str, str],
    existing: TranslationFile | None,
    language: str | None,
    source_language: str | None,
) -> tuple[TranslationFile, MergeStats]:
    """The translation file listing ``items`` (in order), keeping what ``existing`` holds. In
    order: a translation under the same key with the same source is kept; one whose source now
    sits under another key of the same scene moves there (an item inserted before it); one whose
    key remains but whose source changed is kept with ``stale: true`` and ``old_source``; a
    translated entry used by none of these is kept as ``obsolete``, an untranslated one dropped.
    A hand-written entry without ``source`` / ``hash`` is kept as it is."""
    stats = MergeStats()
    old = dict(existing.entries) if existing is not None else {}
    digests = {item.key: source_hash(item.source) for item in items}
    used: set[str] = set()
    found: dict[str, tuple[str, TranslationEntry]] = {}   # item key -> (how, entry)
    for item in items:   # 1. same key, same source (or nothing to compare with)
        previous = old.get(item.key)
        if previous is not None and previous.translated and _entry_hash(previous) in (None, digests[item.key]):
            found[item.key] = ("stale" if previous.stale else "kept", previous)
            used.add(item.key)
    pool: dict[tuple[str, str], list[str]] = {}
    for key, entry in old.items():
        digest = _entry_hash(entry)
        if key not in used and entry.translated and digest is not None:
            pool.setdefault((_group(key), digest), []).append(key)
    for item in items:   # 2. the same source under another key of the scene
        if item.key in found:
            continue
        candidates = [k for k in pool.get((_group(item.key), digests[item.key]), []) if k not in used]
        if candidates:
            found[item.key] = ("moved", old[candidates[0]])
            used.add(candidates[0])
    for item in items:   # 3. the key remains, its source changed
        previous = old.get(item.key)
        if item.key not in found and item.key not in used and previous is not None and previous.translated:
            found[item.key] = ("changed", previous)
            used.add(item.key)
    entries: dict[str, TranslationEntry] = {}
    for item in items:
        digest = digests[item.key]
        how, previous = found.get(item.key, ("new", TranslationEntry()))
        if how == "new":
            entries[item.key] = TranslationEntry(source=item.source, hash=digest, text=None)
            stats.untranslated.append(item.key)
        elif how == "changed":
            entries[item.key] = TranslationEntry(
                source=item.source, hash=digest, text=previous.text, stale=True, old_source=previous.old_source or previous.source
            )
            stats.stale.append(item.key)
        else:
            entries[item.key] = previous.model_copy(update={"source": item.source, "hash": digest, "obsolete": False})
            {"kept": stats.kept, "stale": stats.stale, "moved": stats.moved}[how].append(item.key)
    for key, entry in old.items():
        if key in used or key in entries:
            continue
        if entry.translated:
            entries[key] = entry.model_copy(update={"obsolete": True})
            stats.obsolete.append(key)
        else:
            stats.dropped.append(key)
    doc = TranslationFile(
        language=language or (existing.language if existing else None),
        source_language=source_language or (existing.source_language if existing else None),
        entries=entries,
        references=dict(references),
    )
    return doc, stats


# ----- a project's translations ------------------------------------------------------------------

#: Where ``vidgen translate-template`` writes a variant's file when the config names none.
DEFAULT_FOLDER = "translations"
#: How many keys a warning lists before "and N more".
_SHOWN = 8


def project_texts(project: Project) -> tuple[list[TextItem], dict[str, str]]:
    """The translatable texts and references of ``project``'s source config (before its own
    translations), with the registered scene types, actions and overlays (call inside a
    project session: :func:`vidgen.extensions.project_session`)."""
    from vidgen import registry

    def scene_model(name: str) -> type[BaseModel] | None:
        entry = registry.find(name)
        return entry.params_model if entry is not None else None

    def action_model(name: str) -> type[BaseModel] | None:
        entry = registry.find_action(name)
        return entry.cls.Options if entry is not None else None

    def overlay_model(name: str) -> type[BaseModel] | None:
        entry = registry.find_overlay(name)
        return entry.cls.Options if entry is not None else None

    return extract_texts(project.source_data, scene_model, action_model, overlay_model)


def template_path(project: Project) -> tuple[Path, str]:
    """The translation file of ``project`` and its path as written in the config: the
    ``translations:`` it names, else ``translations/<variant>.yaml`` (``<language>.yaml``, or
    ``translations.yaml``, without a variant)."""
    rel = project.source_config.translations
    if rel is None:
        stem = project.variant or project.config.language or "translations"
        rel = f"{DEFAULT_FOLDER}/{stem}.yaml"
    return project.root / rel, rel


@dataclass
class TemplateResult:
    """What ``vidgen translate-template`` wrote: the ``path`` (``rel`` as the config would name
    it), the file's ``language``, the texts listed (``total``), the merge ``stats``, how many
    references and whether the config already names the file (``linked``)."""

    path: Path
    rel: str
    language: str | None
    total: int
    stats: MergeStats
    references: int
    linked: bool


def write_template(project: Project, language: str | None = None, output: Path | None = None) -> TemplateResult:
    """Write (or update) the translation file of ``project`` (a variant, usually): every
    translatable text of its source config merged with what the file already holds
    (:func:`merge_template`). ``language`` (BCP-47) defaults to the config's ``language``;
    ``output`` to :func:`template_path`."""
    from vidgen import extensions
    from vidgen.fileio import write_text_atomic
    from vidgen.languages import normalize_language

    if language is not None:
        try:
            language = normalize_language(language)
        except ValueError as exc:
            raise VidgenError(f"--lang: {exc}") from None
    path, rel = template_path(project)
    if output is not None:
        path = output
        try:
            rel = path.resolve().relative_to(project.root.resolve()).as_posix()
        except ValueError:
            rel = str(path)
    with extensions.project_session(project):
        items, references = project_texts(project)
    existing = read_translation_file(path, rel) if path.is_file() else None
    # A variant that does not set its own language has the base's: only --lang names the file's.
    own = project.source_config.language
    if project.variant is not None and own == project.base_config.language:
        own = None
    lang = language or own
    doc, stats = merge_template(items, references, existing, lang, project.base_config.language)
    what = f"variant '{project.variant}'" if project.variant else "the base config"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, dump_translation_file(doc, project.source_config.title, what))
    linked = project.source_config.translations is not None and (project.root / project.source_config.translations).resolve() == path.resolve()
    return TemplateResult(path, rel, doc.language, len(items), stats, len(doc.references), linked)


def _few(keys: Sequence[str]) -> str:
    shown = ", ".join(keys[:_SHOWN])
    return shown + (f" and {len(keys) - _SHOWN} more" if len(keys) > _SHOWN else "")


def translation_warnings(project: Project) -> list[str]:
    """``vidgen validate`` warnings about the project's translation file (DESIGN.md §54): texts
    not translated (shown in the source language), stale translations (not used), entries that
    name nothing, places that name a translated text but are not updated, a file language other
    than the config's. Empty without ``translations:``."""
    from vidgen import extensions
    from vidgen.languages import primary_language

    report = project.translation
    if report is None:
        return []
    where = f"translations ({report.file})"
    try:
        with extensions.project_session(project):
            items, references = project_texts(project)
    except VidgenError:
        return []  # a project that does not load its extensions: `vidgen validate` reports it
    out = []
    keys = [item.key for item in items]
    if report.missing:
        return [
            f"{where}: the file does not exist, so all {len(keys)} texts show the source text; "
            f"`vidgen translate-template{' --variant ' + project.variant if project.variant else ''}` writes it"
        ]
    missing = [k for k in keys if k not in report.applied and k not in report.stale]
    if missing:
        out.append(f"{where}: {len(missing)} of {len(keys)} texts are not translated and show the source text: {_few(missing)}")
    if report.stale:
        out.append(
            f"{where}: {len(report.stale)} translations are not used because their source text changed (stale): "
            f"{_few(report.stale)}; check them, then delete their `stale: true` (`vidgen translate-template` marks them)"
        )
    if report.unknown:
        out.append(
            f"{where}: {len(report.unknown)} entries name nothing in the config: {_few(report.unknown)}; "
            "run `vidgen translate-template` (it keeps their texts as obsolete)"
        )
    outdated = [p for p, k in references.items() if k in report.applied and report.references.get(p) != k]
    if outdated or report.broken:
        places = list(dict.fromkeys([*outdated, *report.broken]))
        out.append(
            f"{where}: {len(places)} places name a translated text but keep its source name: {_few(places)}; "
            "run `vidgen translate-template` to update the file's references"
        )
    file_lang, video_lang = report.language, project.config.language
    if file_lang is not None and primary_language(file_lang) != primary_language(video_lang):
        out.append(f"{where}: the file is in {file_lang} but the video's language is {video_lang or 'not set (English rules)'}; set language: {file_lang}")
    return out


def language_warnings(project: Project) -> list[str]:
    """A variant in another language than the base config that keeps the base's pronunciation
    entries unchanged (they were written for the base language; DESIGN.md §54)."""
    from vidgen.languages import primary_language
    from vidgen.pronunciation import applies_to

    if project.variant is None:
        return []
    lang, base_lang = project.config.language, project.base_config.language
    if primary_language(lang) == primary_language(base_lang):
        return []
    texts = [beat.text for scene in project.config.scenes for beat in scene.beats]
    inherited = [
        term
        for term, value in project.base_config.pronunciation.items()
        if value is not None
        and project.config.pronunciation.get(term) == value
        and applies_to(value, lang)
        and any(project.pronunciation.apply(text).matched & {term} for text in texts)
    ]
    if not inherited:
        return []
    terms = ", ".join(f"'{t}'" for t in inherited)
    return [
        f"pronunciation: {terms} from the base config ({base_lang or 'English rules'}) also apply in this variant's "
        f"language ({lang}); override them in the variant, set them to null, or give them language: {primary_language(base_lang)}"
    ]
