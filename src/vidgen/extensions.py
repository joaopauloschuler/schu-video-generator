"""Discovery and import of built-in scenes and project extensions (DESIGN.md §6.1).

The usual entry points:

- :func:`activate` — for a process that works on one project (the render worker): set the
  runtime context, clear previous extension registrations, import built-ins and extensions.
- :func:`project_session` — the same as a context manager that restores the previous registry,
  hooks and runtime context on exit (``vidgen validate`` over several variants, tests).
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import re
import sys
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

from vidgen import hooks, registry, runtime
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.theme import Theme

PACKAGE_PREFIX = "vidgen_ext_"


def load_builtins() -> None:
    """Import the built-in scene library (``vidgen.scenes``); idempotent."""
    importlib.import_module("vidgen.scenes")


def package_name(project: Project) -> str:
    """The private package extensions are imported under: ``vidgen_ext_<sanitised folder name>``."""
    name = re.sub(r"\W", "_", project.root.name, flags=re.ASCII).strip("_").lower() or "project"
    return PACKAGE_PREFIX + name


def extension_dirs(project: Project) -> list[Path]:
    """Existing extension directories of ``project``.

    The default ``extensions/`` is skipped silently when absent; a directory listed explicitly
    in the config's ``extensions`` must exist.
    """
    explicit = "extensions" in project.config.model_fields_set
    dirs = []
    for entry, path in zip(project.config.extensions, project.extension_dirs):
        if path.is_dir():
            dirs.append(path)
        elif path.exists():
            raise VidgenError(f"extensions entry '{entry}' is not a directory ({path})")
        elif explicit:
            raise VidgenError(f"extensions directory '{entry}' not found (looked for {path})")
    return dirs


def discover(directory: Path) -> list[str]:
    """Module names to import from ``directory``: ``*.py`` files and packages (folders with an
    ``__init__.py``) whose names do not start with ``_``, sorted."""
    found = []
    for child in directory.iterdir():
        if child.name.startswith("_") or child.name.startswith("."):
            continue
        if child.is_file() and child.suffix == ".py":
            found.append(child.stem)
        elif child.is_dir() and (child / "__init__.py").is_file():
            found.append(child.name)
    return sorted(found)


def unload(package: str) -> None:
    """Remove ``package`` and all its submodules from ``sys.modules``."""
    for name in [n for n in sys.modules if n == package or n.startswith(package + ".")]:
        del sys.modules[name]


def _create_package(name: str, dirs: list[Path]) -> ModuleType:
    spec = importlib.machinery.ModuleSpec(name, None, is_package=True)
    spec.submodule_search_locations = [str(d) for d in dirs]
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    return package


def _import_error(path: Path, root: Path, exc: BaseException) -> VidgenError:
    """A VidgenError with the extension file and the traceback (without importlib frames)."""
    try:
        shown = path.relative_to(root).as_posix()
    except ValueError:
        shown = str(path)
    tb = traceback.TracebackException.from_exception(exc)
    importlib_dir = str(Path(importlib.__file__).parent)
    tb.stack = traceback.StackSummary.from_list(
        [
            f
            for f in tb.stack
            if not f.filename.startswith(("<frozen ", importlib_dir)) and f.filename != __file__
        ]
    )
    details = "".join(tb.format()).rstrip()
    return VidgenError(f"error while importing extension {shown}:\n{details}")


def load_extensions(project: Project) -> list[str]:
    """Import every extension module of ``project``; returns the imported module names.

    Expects the runtime context to be set (see :func:`activate`). Modules are imported as
    ``vidgen_ext_<name>.<module>`` so they can use relative imports between each other; all
    extension directories share that one package. Any previous copy of the package is removed
    from ``sys.modules`` first, so loading the same or another project again re-imports.
    """
    dirs = extension_dirs(project)
    package = package_name(project)
    unload(package)
    if not dirs:
        return []
    seen: dict[str, Path] = {}
    order: list[tuple[str, Path]] = []
    for directory in dirs:
        for module in discover(directory):
            if module in seen:
                raise VidgenError(
                    f"extension module '{module}' exists in two extension directories "
                    f"({seen[module]} and {directory}); rename one"
                )
            seen[module] = directory
            order.append((module, directory))
    _create_package(package, dirs)
    importlib.invalidate_caches()
    loaded = []
    for module, directory in order:
        path = directory / module
        path = path if path.is_dir() else path.with_suffix(".py")
        try:
            importlib.import_module(f"{package}.{module}")
        except VidgenError:
            raise
        except (Exception, SystemExit) as exc:  # sys.exit() in an extension must not end vidgen silently
            raise _import_error(path, project.root, exc) from None
        loaded.append(f"{package}.{module}")
    return loaded


def activate(project: Project, theme: Theme | None = None) -> Theme:
    """Make ``project`` the active one for the rest of the process and load its extensions.

    Sets the runtime context (a fresh ``Theme`` unless given), clears scene types and hooks
    registered by previously loaded extensions, imports built-ins, then the project's
    extensions. Returns the active theme (it includes defaults registered by extensions).
    """
    theme = runtime.set_context(project, theme)
    registry.reset()
    hooks.reset()
    load_builtins()
    load_extensions(project)
    return theme


@contextmanager
def project_session(project: Project, theme: Theme | None = None) -> Iterator[Theme]:
    """:func:`activate` ``project`` temporarily; registry, hooks, runtime context and the
    extension package are restored/removed on exit."""
    with runtime.use_context(project, theme), registry.isolated(), hooks.isolated():
        try:
            yield activate(project, runtime.current_theme())
        finally:
            unload(package_name(project))
