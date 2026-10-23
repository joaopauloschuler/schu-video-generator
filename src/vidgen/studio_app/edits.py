"""Value edits of a score's text that keep everything else as written (DESIGN.md §94.4): a control
changes one value in place, found with :func:`yaml.compose`'s node marks, so the comments, the
layout and every other line stay as they were.

An edit is ``{"op": ..., "path": ...}`` with ``path`` as a score problem's ``where``
(``tempo``, ``tracks.bass.volume``, ``sections[2].bars``):

- ``set`` ``value``: replace the value (written in flow style; a quoted string keeps its quotes),
  or add the key (and any missing parents) next to its siblings;
- ``delete``: remove a mapping's key or a list's item (with the comment lines just above it);
- ``insert`` ``index`` ``value``: put an item into a list at ``index`` (its length: at the end);
- ``rename`` ``to``: rename a mapping's key;
- ``unset`` ``keep``?: remove a mapping's key (nothing when it is not there) and the mappings
  it leaves empty, up to the first ``keep`` parts of the path (default 2: ``tracks.bass`` stays);
  a mapping at that depth left empty is written ``{}`` (a reset to the default, Step 195).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

import yaml

from vidgen.errors import VidgenError

_PART = re.compile(r"([^.\[\]]+)|\[(\d+)\]")
_PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_#()+]*( [A-Za-z][a-z]*)?")
_FLOW_UNSAFE =re.compile(r"[,\[\]{}#&*!|>'\"%@`]|: |^[-?:]\s|^\s|\s$|^$")


def parse_path(path: str) -> list[str | int]:
    """``tracks.bass.steps`` → ``["tracks", "bass", "steps"]``; ``sections[2].bars`` →
    ``["sections", 2, "bars"]``."""
    parts: list[str | int] = []
    pos = 0
    for m in _PART.finditer(path):
        if m.start() != pos and path[pos:m.start()] != ".":
            raise VidgenError(f"edit: cannot read the path {path!r}")
        parts.append(m[1] if m[1] is not None else int(m[2]))
        pos = m.end()
    if not parts or pos != len(path):
        raise VidgenError(f"edit: cannot read the path {path!r}")
    return parts


def flow(value: Any) -> str:
    """``value`` as YAML in flow style (one line)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise VidgenError(f"edit: {value!r} is not a number a score can hold")
        return str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)
    if isinstance(value, str):
        return _plain_or_quoted(value)
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{flow(str(k))}: {flow(v)}" for k, v in value.items()) + "}"
    if isinstance(value, Sequence):
        return "[" + ", ".join(flow(v) for v in value) + "]"
    raise VidgenError(f"edit: cannot write a {type(value).__name__} in a score")


def _plain_or_quoted(text: str) -> str:
    """A name (``kick``, ``fm_pluck``, ``Gm7``) or a key (``G minor``) plain, anything else
    (steps, progressions) in double quotes, as the templates write them."""
    if _PLAIN.fullmatch(text) and not _FLOW_UNSAFE.search(text):
        try:
            if yaml.safe_load(f"[{text}]") == [text]:
                return text
        except yaml.YAMLError:
            pass
    return json.dumps(text, ensure_ascii=False)


def _scalar_text(value: Any, node: yaml.Node) -> str:
    """``value`` to replace the scalar ``node``: a string keeps the node's quotes."""
    if isinstance(value, str) and isinstance(node, yaml.ScalarNode) and node.style in ('"', "'"):
        if node.style == "'":
            return "'" + value.replace("'", "''") + "'"
        return json.dumps(value, ensure_ascii=False)
    return flow(value)


# ----- finding nodes ----------------------------------------------------------------------------


def _compose(text: str) -> yaml.Node:
    try:
        node = yaml.compose(text)
    except yaml.YAMLError as exc:
        raise VidgenError(f"edit: the score is not valid YAML ({exc})") from None
    if not isinstance(node, yaml.MappingNode):
        raise VidgenError("edit: the score is not a mapping of settings")
    return node


def _entry(node: yaml.MappingNode, key: str) -> tuple[yaml.Node, yaml.Node] | None:
    return next(((k, v) for k, v in node.value if isinstance(k, yaml.ScalarNode) and k.value == key), None)


def _child(node: yaml.Node, part: str | int, path: str) -> yaml.Node | None:
    if isinstance(part, str):
        if not isinstance(node, yaml.MappingNode):
            raise VidgenError(f"edit: {path}: {part!r} is not in a mapping")
        found = _entry(node, part)
        return found[1] if found else None
    if not isinstance(node, yaml.SequenceNode):
        raise VidgenError(f"edit: {path}: [{part}] is not in a list")
    return node.value[part] if part < len(node.value) else None


def _walk(root: yaml.Node, parts: list[str | int], path: str) -> list[yaml.Node]:
    """The nodes along ``parts`` from ``root`` (shorter than ``parts`` + 1 when one is missing)."""
    nodes = [root]
    for part in parts:
        child = _child(nodes[-1], part, path)
        if child is None:
            break
        nodes.append(child)
    return nodes


def _content_end(node: yaml.Node) -> int:
    """Where the node's own text ends (a block collection's end mark is after the comments and
    blank lines that follow it; this is the end of its last value)."""
    if isinstance(node, yaml.MappingNode) and node.value and node.flow_style is not True:
        return _content_end(node.value[-1][1])
    if isinstance(node, yaml.SequenceNode) and node.value and node.flow_style is not True:
        return _content_end(node.value[-1])
    return node.end_mark.index


def _is_block(node: yaml.Node) -> bool:
    return isinstance(node, (yaml.MappingNode, yaml.SequenceNode)) and node.flow_style is not True


def _line_start(text: str, at: int) -> int:
    return text.rfind("\n", 0, at) + 1


def _line_end(text: str, at: int) -> int:
    """The index just past the newline of the line holding ``at`` (or the text's end)."""
    found = text.find("\n", at)
    return len(text) if found < 0 else found + 1


def _with_comments_above(text: str, start: int) -> int:
    """``start`` (a line's start) moved up over the comment-only lines just above it."""
    while start > 0:
        before = _line_start(text, start - 1)
        if not text[before:start].strip().startswith("#"):
            break
        start = before
    return start


def _ensure_newline(text: str) -> str:
    return text if text.endswith("\n") or not text else text + "\n"


# ----- the edits ----------------------------------------------------------------------------------


def apply_edits(text: str, ops: Sequence[Mapping[str, Any]]) -> str:
    """``text`` with ``ops`` applied one after the other (:class:`VidgenError` for a bad op)."""
    for op in ops:
        if not isinstance(op, Mapping):
            raise VidgenError("edit: each edit is a mapping like {op: set, path: tempo, value: 126}")
        kind, path = op.get("op"), op.get("path")
        if not isinstance(path, str):
            raise VidgenError(f"edit: {kind}: give the path of the value (e.g. tracks.bass.volume)")
        if kind == "set":
            text = set_value(text, path, op.get("value"))
        elif kind == "delete":
            text = delete_value(text, path)
        elif kind == "insert":
            text = insert_item(text, path, op.get("index"), op.get("value"))
        elif kind == "rename":
            text = rename_key(text, path, op.get("to"))
        elif kind == "unset":
            keep = op.get("keep", 2)
            if isinstance(keep, bool) or not isinstance(keep, int) or keep < 1:
                raise VidgenError(f"edit: unset {path}: keep is a whole number of path parts (at least 1)")
            text = unset_value(text, path, keep)
        else:
            raise VidgenError(f"edit: unknown op {kind!r} (set, delete, insert, rename, unset)")
    return text


def unset_value(text: str, path: str, keep: int = 2) -> str:
    """Remove the key at ``path`` (``text`` unchanged when it is not there) and every parent
    mapping it leaves empty, keeping the first ``keep`` parts of the path; a kept mapping left
    empty becomes ``{}``."""
    parts = parse_path(path)
    if not isinstance(parts[-1], str):
        raise VidgenError(f"edit: unset {path}: name a key, not a list item")
    nodes = _walk(_compose(text), parts, path)
    if len(nodes) != len(parts) + 1:
        return text
    k = len(parts)
    # nodes[i] is the node at parts[:i]: the parent of parts[:k] is nodes[k - 1]
    while k - 1 > keep and isinstance(nodes[k - 1], yaml.MappingNode) and len(nodes[k - 1].value) == 1 and isinstance(parts[k - 2], str):
        k -= 1
    parent = nodes[k - 1]
    if isinstance(parent, yaml.MappingNode) and len(parent.value) == 1 and k - 1 >= 1:
        return set_value(text, _path_text(parts[: k - 1]), {})
    return delete_value(text, _path_text(parts[:k]))


def _path_text(parts: Sequence[str | int]) -> str:
    out = ""
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else part)
    return out


def set_value(text: str, path: str, value: Any) -> str:
    """Replace the value at ``path`` or add it (with missing parent mappings) by its siblings."""
    parts = parse_path(path)
    root = _compose(text)
    nodes = _walk(root, parts, path)
    if len(nodes) == len(parts) + 1:
        node = nodes[-1]
        if not _is_block(node):
            return text[: node.start_mark.index] + _scalar_text(value, node) + text[node.end_mark.index :]
        parent = nodes[-2]
        if not isinstance(parent, yaml.MappingNode):
            raise VidgenError(f"edit: {path}: cannot replace a block list item; edit its values")
        key = _entry(parent, str(parts[-1]))
        assert key is not None
        colon = text.index(":", key[0].end_mark.index) + 1
        return text[:colon] + " " + flow(value) + text[_content_end(node) :]
    missing = parts[len(nodes) - 1 :]
    if not isinstance(missing[0], str):
        raise VidgenError(f"edit: {path}: no item {missing[0]} in the list (insert it)")
    nested: Any = value
    for part in reversed(missing[1:]):
        if not isinstance(part, str):
            raise VidgenError(f"edit: {path}: cannot make a list item in a missing list")
        nested = {part: nested}
    return _add_key(text, nodes[-1], missing[0], nested, path)


def _add_key(text: str, mapping: yaml.Node, key: str, value: Any, path: str) -> str:
    if not isinstance(mapping, yaml.MappingNode):
        raise VidgenError(f"edit: {path}: the parent of {key!r} is not a mapping")
    if not _is_block(mapping):
        close = mapping.end_mark.index - 1
        if not mapping.value:
            return text[:close] + f"{flow(key)}: {flow(value)}" + text[close:]
        at = _content_end(mapping.value[-1][1])
        return text[:at] + f", {flow(key)}: {flow(value)}" + text[at:]
    if not mapping.value:
        raise VidgenError(f"edit: {path}: cannot add to an empty block mapping")
    indent = mapping.value[0][0].start_mark.column
    at = _line_end(text, _content_end(mapping.value[-1][1]))
    if at == len(text):
        text = _ensure_newline(text)
        at = len(text)
    return text[:at] + _block_entry(key, value, indent) + text[at:]


def _block_entry(key: str, value: Any, indent: int) -> str:
    """``key: value`` as lines at ``indent``: a mapping of two or more values one key a line."""
    pad = " " * indent
    if isinstance(value, Mapping) and len(value) > 1:
        lines = [f"{pad}{flow(key)}:"] + [f"{pad}  {flow(str(k))}: {flow(v)}" for k, v in value.items()]
        return "\n".join(lines) + "\n"
    return f"{pad}{flow(key)}: {flow(value)}\n"


def delete_value(text: str, path: str) -> str:
    """Remove the key or list item at ``path``."""
    parts = parse_path(path)
    root = _compose(text)
    nodes = _walk(root, parts, path)
    if len(nodes) != len(parts) + 1:
        raise VidgenError(f"edit: {path}: nothing there to delete")
    parent, last = nodes[-2], parts[-1]
    if isinstance(parent, yaml.MappingNode):
        found = _entry(parent, str(last))
        assert found is not None
        start, end = found[0].start_mark.index, _content_end(found[1])
        items = [k for k, _ in parent.value]
        index = items.index(found[0])
    else:
        assert isinstance(parent, yaml.SequenceNode) and isinstance(last, int)
        node = parent.value[last]
        start, end, index = node.start_mark.index, _content_end(node), last
        if _is_block(parent):
            start = text.rfind("-", _line_start(text, start), start)
    count = len(parent.value)
    if _is_block(parent):
        line = _line_start(text, start)
        if text[line:start].strip():
            raise VidgenError(f"edit: {path}: cannot delete a value that shares its line with another")
        if count == 1:
            raise VidgenError(f"edit: {path}: the last value of a block; delete or replace its parent instead")
        return text[: _with_comments_above(text, line)] + text[_line_end(text, end) :]
    if index + 1 < count:  # up to the next item
        nxt = parent.value[index + 1]
        nxt_start = (nxt[0] if isinstance(nxt, tuple) else nxt).start_mark.index
        return text[:start] + text[nxt_start:]
    if index > 0:  # from the end of the item before
        prev = parent.value[index - 1]
        prev_end = _content_end(prev[1] if isinstance(prev, tuple) else prev)
        return text[:prev_end] + text[end:]
    return text[:start] + text[end:]


def insert_item(text: str, path: str, index: Any, value: Any) -> str:
    """Insert ``value`` into the list at ``path`` before item ``index`` (its length: append)."""
    parts = parse_path(path)
    nodes = _walk(_compose(text), parts, path)
    if len(nodes) != len(parts) + 1 or not isinstance(nodes[-1], yaml.SequenceNode):
        raise VidgenError(f"edit: {path}: not a list")
    seq = nodes[-1]
    count = len(seq.value)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= count:
        raise VidgenError(f"edit: {path}: the index is a whole number from 0 to {count}")
    if not _is_block(seq):
        if count == 0:
            at = seq.end_mark.index - 1
            return text[:at] + flow(value) + text[at:]
        if index < count:
            at = seq.value[index].start_mark.index
            return text[:at] + flow(value) + ", " + text[at:]
        at = _content_end(seq.value[-1])
        return text[:at] + ", " + flow(value) + text[at:]
    first = seq.value[0].start_mark.index
    dash = text.rfind("-", _line_start(text, first), first)
    pad = " " * (dash - _line_start(text, dash))
    line = f"{pad}- {flow(value)}\n"
    if index < count:
        at = _with_comments_above(text, _line_start(text, seq.value[index].start_mark.index))
    else:
        at = _line_end(text, _content_end(seq.value[-1]))
        if at == len(text):
            text = _ensure_newline(text)
            at = len(text)
    return text[:at] + line + text[at:]


def rename_key(text: str, path: str, to: Any) -> str:
    """Rename the mapping key at ``path`` to ``to`` (its value and comments stay)."""
    if not isinstance(to, str) or not to:
        raise VidgenError(f"edit: {path}: give the new name (to)")
    parts = parse_path(path)
    nodes = _walk(_compose(text), parts, path)
    if len(nodes) != len(parts) + 1 or not isinstance(nodes[-2], yaml.MappingNode) or not isinstance(parts[-1], str):
        raise VidgenError(f"edit: {path}: no such key to rename")
    if _entry(nodes[-2], to) is not None:
        raise VidgenError(f"edit: {path}: {to!r} is already there")
    key = _entry(nodes[-2], parts[-1])
    assert key is not None
    return text[: key[0].start_mark.index] + flow(to) + text[key[0].end_mark.index :]
