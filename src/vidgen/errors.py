"""Error types raised by vidgen."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class Problem:
    """One problem found in a project, tied to a config location when possible.

    ``location`` is a config path such as ``scenes[2].params.title`` (``""`` when the problem
    is not about one config value, e.g. an extension that fails to import); ``variant`` names
    the variant whose (merged) config has the problem, ``None`` for the base config.
    ``str(problem)`` is the line ``vidgen validate`` prints.
    """

    location: str
    message: str
    variant: str | None = None

    def __str__(self) -> str:
        text = f"{self.location}: {self.message}" if self.location else self.message
        return text if self.variant is None else f"[variant {self.variant}] {text}"

    def in_variant(self, variant: str | None) -> Problem:
        """This problem attributed to ``variant``."""
        return replace(self, variant=variant)

    def to_json(self) -> dict[str, Any]:
        """``{"location", "message", "variant"}`` (``location``/``variant`` may be ``null``)."""
        return {"location": self.location or None, "message": self.message, "variant": self.variant}


class VidgenError(Exception):
    """An error the user can cause and fix (bad config, missing file, unknown name, ...).

    The CLI prints these as ``error: <message>`` without a traceback. Optional structured data
    for ``--json`` output: ``problems`` (config problems with their locations) and ``details``
    (a JSON-serialisable mapping, e.g. the scenes that failed to render).
    """

    def __init__(
        self,
        message: str,
        *,
        problems: Iterable[Problem] = (),
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.problems: list[Problem] = list(problems)
        self.details: dict[str, Any] = dict(details or {})
