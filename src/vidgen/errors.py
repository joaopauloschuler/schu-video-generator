"""Error types raised by vidgen."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from vidgen import DIST_NAME

#: What to do when a package of vidgen's own dependencies is absent or has the wrong version.
REINSTALL = f"reinstall {DIST_NAME} with pip in this Python environment (pip install . from its folder)"


def incomplete_install(package: str) -> str:
    """The message for a missing ``package``: a plain install brings it, so vidgen is what to reinstall."""
    return f"this installation of {DIST_NAME} is incomplete ({package} is missing): {REINSTALL}"


@dataclass(frozen=True)
class Problem:
    """One problem found in a project, tied to a config location when possible.

    ``location`` is a config path such as ``scenes[2].params.title`` (``""`` when the problem
    is not about one config value, e.g. an extension that fails to import); ``variant`` names
    the variant whose (merged) config has the problem, ``None`` for the base config; ``file`` is
    the ``include:`` file the value is written in (relative to the project, DESIGN.md §69.35),
    ``None`` for the project's own config file. ``str(problem)`` is the line ``vidgen validate``
    prints.
    """

    location: str
    message: str
    variant: str | None = None
    file: str | None = None

    def __str__(self) -> str:
        where = f"{self.location} (in {self.file})" if self.file else self.location
        text = f"{where}: {self.message}" if where else self.message
        return text if self.variant is None else f"[variant {self.variant}] {text}"

    def in_variant(self, variant: str | None) -> Problem:
        """This problem attributed to ``variant``."""
        return replace(self, variant=variant)

    def to_json(self) -> dict[str, Any]:
        """``{"location", "message", "variant", "file"}`` (all but ``message`` may be ``null``)."""
        return {"location": self.location or None, "message": self.message, "variant": self.variant, "file": self.file}


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
