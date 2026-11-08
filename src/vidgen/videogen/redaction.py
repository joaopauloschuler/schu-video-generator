"""Keeps a quick tunnel's secret path out of what vidgen prints or stores (DESIGN.md §115.6).

A shared file's address is ``https://<words>.trycloudflare.com/<secret>/<name>``. A provider's
error can quote it, and that text reaches the terminal, ``--json``, MCP and the ledger.
:func:`redact_shared_addresses` needs no knowledge of the host, so it also works on the error of
a job polled by a later run, when the host and its secret are gone. The host name stays: it is
printed and in the ledger on purpose, and it opens nothing without the path.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

#: What is shown instead of a secret path.
REDACTED = "<secret>"
#: A slash as a provider may quote it: plain, escaped in JSON, or percent-encoded.
_SLASH = r"(?:\\*/|%(?:25)*2f)"
#: A quick tunnel host followed by any path (also cut off, as long error bodies are).
_TUNNEL_PATH = re.compile(rf"(\.trycloudflare\.com)(?::\d+)?{_SLASH}[^\s\"'<>()\[\]{{}}]+", re.IGNORECASE)
#: A share path without its host: the 32 characters of the secret, then the 16 hex digits of a
#: shared file's name (:func:`vidgen.videogen.host.copy_into_share`).
_SHARE_PATH = re.compile(rf"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{{32}}{_SLASH}[0-9a-f]{{16}}(?:\.[A-Za-z0-9]+)?", re.IGNORECASE)


def redact_shared_addresses(text: str) -> str:
    """``text`` with the path of every quick tunnel address replaced by :data:`REDACTED`."""
    return _SHARE_PATH.sub(REDACTED, _TUNNEL_PATH.sub(rf"\1/{REDACTED}", text))


def redact_value(value: Any, redact: Callable[[str], str]) -> Any:
    """``value`` with ``redact`` applied to every string in it (dicts, lists and tuples followed)."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_value(v, redact) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(v, redact) for v in value]
    return value
