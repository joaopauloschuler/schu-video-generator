"""The active Project and Theme (DESIGN.md §6.3).

The context is set *before* extensions are imported, so module-level code in an extension may
read theme values (``C_BASE = current_theme().color("primary")``). Helpers such as ``api.T`` use
the current theme. This module does not import manim.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from vidgen.errors import VidgenError
from vidgen.theme import Theme

if TYPE_CHECKING:
    from vidgen.project import Project

_project: Project | None = None
_theme: Theme | None = None


def set_context(project: Project, theme: Theme | None = None) -> Theme:
    """Make ``project`` (and ``theme``, default: a fresh ``Theme`` from its config) current.

    Returns the active theme.
    """
    global _project, _theme
    _project = project
    _theme = theme if theme is not None else Theme(project.config.theme)
    return _theme


def clear_context() -> None:
    """Unset the current project and theme."""
    global _project, _theme
    _project = None
    _theme = None


def current_project() -> Project:
    """The active project. Raises :class:`VidgenError` if no project is active."""
    if _project is None:
        raise VidgenError(
            "no active vidgen project: current_project() is only available while a project is "
            "loaded (in extensions and scenes run by vidgen)"
        )
    return _project


def current_theme() -> Theme:
    """The active theme. Raises :class:`VidgenError` if no project is active."""
    if _theme is None:
        raise VidgenError(
            "no active vidgen theme: current_theme() is only available while a project is "
            "loaded (in extensions and scenes run by vidgen)"
        )
    return _theme


def has_context() -> bool:
    """True if a project is active."""
    return _project is not None


@contextmanager
def use_context(project: Project, theme: Theme | None = None) -> Iterator[Theme]:
    """Temporarily make ``project``/``theme`` current; the previous context is restored on exit."""
    global _project, _theme
    saved = (_project, _theme)
    try:
        yield set_context(project, theme)
    finally:
        _project, _theme = saved
