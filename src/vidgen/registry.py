"""Scene-type registry (DESIGN.md §6.2).

Two layers:

- **built-ins** — scene types defined in modules inside the ``vidgen`` package
  (``vidgen.scenes``). They are registered once per process when those modules are first
  imported and are never reset (Python caches the modules, so they could not re-register).
- **extensions** — scene types from the active project's ``extensions/``. This layer belongs to
  one project: :func:`reset` clears it, :func:`snapshot`/:func:`restore` and :func:`isolated`
  save and restore it, so loading several projects (or variants) in one process never leaks.

Whether a registration is built-in or extension is decided by the defining module: anything
under ``vidgen.*`` is built-in. So an extension module copied into ``src/vidgen/scenes/`` becomes
a built-in unchanged.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from vidgen._origin import BUILTIN, is_builtin_module, origin_of
from vidgen.config import ID_PATTERN
from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.scene import NarratedScene

log = logging.getLogger("vidgen.registry")

S = TypeVar("S", bound=type)


@dataclass(frozen=True)
class SceneType:
    """A registered scene type.

    ``origin`` is ``"builtin"`` or the extension file that defined it (relative to the project
    root when possible). ``overrides`` is the built-in it replaces (``override=True``), if any.
    """

    name: str
    cls: type[NarratedScene]
    origin: str
    overrides: SceneType | None = None

    @property
    def builtin(self) -> bool:
        """True for built-in scene types."""
        return self.origin == BUILTIN

    @property
    def params_model(self) -> type[BaseModel] | None:
        """The class's ``Params`` model, or ``None`` if params are a plain dict."""
        return self.cls.params_model()


_builtins: dict[str, SceneType] = {}
_extensions: dict[str, SceneType] = {}

Snapshot = dict[str, SceneType]


def _check_class(name: str, cls: object) -> None:
    from vidgen.scene import NarratedScene, SceneParams

    if not (isinstance(cls, type) and issubclass(cls, NarratedScene)):
        raise VidgenError(f"@scene({name!r}) must decorate a subclass of NarratedScene, got {cls!r}")
    params = getattr(cls, "Params", None)
    if params is not None and not (isinstance(params, type) and issubclass(params, SceneParams)):
        raise VidgenError(
            f"scene type '{name}' ({cls.__qualname__}): 'Params' must be a subclass of SceneParams"
        )


def register(name: str, cls: type[NarratedScene], *, override: bool = False) -> SceneType:
    """Register ``cls`` as scene type ``name`` (the function form of :func:`scene`)."""
    if not isinstance(name, str) or not re.match(ID_PATTERN, name):
        raise VidgenError(f"invalid scene type name {name!r}: use letters, digits and '_' only")
    _check_class(name, cls)
    origin = origin_of(cls.__module__)

    if is_builtin_module(cls.__module__):
        if name in _builtins:
            raise VidgenError(
                f"built-in scene type '{name}' is defined twice "
                f"({_builtins[name].cls.__module__} and {cls.__module__})"
            )
        entry = SceneType(name, cls, origin)
        _builtins[name] = entry
        return entry

    if name in _extensions:
        raise VidgenError(
            f"scene type '{name}' is defined twice: in {_extensions[name].origin} and in {origin}; "
            "rename one of them"
        )
    builtin = _builtins.get(name)
    if builtin is not None and not override:
        raise VidgenError(
            f"scene type '{name}' in {origin} has the same name as a built-in scene type; "
            f"rename it, or use @scene({name!r}, override=True) to replace the built-in"
        )
    if builtin is None and override:
        log.warning("%s: @scene(%r, override=True) but there is no built-in '%s' to override", origin, name, name)
    if builtin is not None:
        log.warning("%s: scene type '%s' overrides the built-in scene type", origin, name)
    entry = SceneType(name, cls, origin, overrides=builtin)
    _extensions[name] = entry
    return entry


def scene(name: str, *, override: bool = False) -> Callable[[S], S]:
    """Class decorator: register a :class:`NarratedScene` subclass as scene type ``name``.

    ``name`` is what ``type:`` refers to in video.yaml. Two extensions may not use the same name.
    Reusing a built-in's name is an error unless ``override=True`` (then the extension replaces
    the built-in and a warning is logged).
    """

    def decorate(cls: S) -> S:
        register(name, cls, override=override)  # type: ignore[arg-type]
        return cls

    return decorate


def find(name: str) -> SceneType | None:
    """The scene type ``name`` (extensions shadow built-ins they override), or ``None``."""
    return _extensions.get(name) or _builtins.get(name)


def get(name: str) -> SceneType:
    """The scene type ``name``; raises :class:`VidgenError` listing known types if missing."""
    entry = find(name)
    if entry is None:
        raise VidgenError(unknown_type_message(name))
    return entry


def names() -> list[str]:
    """All registered scene type names, sorted."""
    return sorted({*_builtins, *_extensions})


def all() -> list[SceneType]:  # noqa: A001 - part of the documented registry API
    """All effective scene types sorted by name (an override replaces its built-in)."""
    return [find(n) for n in names()]  # type: ignore[misc]


def unknown_type_message(name: str) -> str:
    """``unknown scene type 'x'`` plus close matches and the list of known types."""
    import difflib

    known = names()
    message = f"unknown scene type '{name}'"
    close = difflib.get_close_matches(name, known, n=3)
    if close:
        message += f"; did you mean {' or '.join(repr(c) for c in close)}?"
    return message + f" (known types: {', '.join(known) or 'none'})"


# ----- isolation -------------------------------------------------------------------------------


def reset() -> None:
    """Forget all extension scene types (built-ins stay)."""
    _extensions.clear()


def snapshot() -> Snapshot:
    """A copy of the extension layer, for :func:`restore`."""
    return dict(_extensions)


def restore(state: Snapshot) -> None:
    """Restore the extension layer saved by :func:`snapshot`."""
    _extensions.clear()
    _extensions.update(state)


@contextmanager
def isolated() -> Iterator[None]:
    """Run with an empty extension layer; the previous one is restored on exit."""
    saved = snapshot()
    reset()
    try:
        yield
    finally:
        restore(saved)
