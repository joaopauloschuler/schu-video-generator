"""Scene-type and action registry (DESIGN.md §6.2, §26).

Scene types (``@scene``) and per-beat action types (``@action``) are registered the same way, in
two layers each:

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
    from vidgen.actions import Action
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


@dataclass(frozen=True)
class ActionType:
    """A registered per-beat action type (``@action``); fields as in :class:`SceneType`."""

    name: str
    cls: type[Action]
    origin: str
    overrides: ActionType | None = None

    @property
    def builtin(self) -> bool:
        """True for built-in action types."""
        return self.origin == BUILTIN


_builtins: dict[str, SceneType] = {}
_extensions: dict[str, SceneType] = {}
_builtin_actions: dict[str, ActionType] = {}
_extension_actions: dict[str, ActionType] = {}

#: The extension layer (scene types, action types), saved by :func:`snapshot`.
Snapshot = tuple[dict[str, SceneType], dict[str, ActionType]]


def _check_class(name: str, cls: object) -> None:
    from vidgen.scene import NarratedScene, SceneParams

    if not (isinstance(cls, type) and issubclass(cls, NarratedScene)):
        raise VidgenError(f"@scene({name!r}) must decorate a subclass of NarratedScene, got {cls!r}")
    params = getattr(cls, "Params", None)
    if params is not None and not (isinstance(params, type) and issubclass(params, SceneParams)):
        raise VidgenError(
            f"scene type '{name}' ({cls.__qualname__}): 'Params' must be a subclass of SceneParams"
        )
    if not _valid_beat_count(cls.beat_count):
        raise VidgenError(
            f"scene type '{name}' ({cls.__qualname__}): beat_count must be None, a number of beats "
            f"(e.g. 2) or a (min, max) tuple with max None for no limit, got {cls.beat_count!r}"
        )


def _valid_beat_count(spec: object) -> bool:
    def count(v: object) -> bool:
        return isinstance(v, int) and not isinstance(v, bool) and v >= 0

    if spec is None or count(spec):
        return True
    if not (isinstance(spec, tuple) and len(spec) == 2 and count(spec[0])):
        return False
    hi = spec[1]
    return hi is None or (count(hi) and hi >= spec[0])  # type: ignore[operator]


E = TypeVar("E", SceneType, ActionType)


def _add(kind: str, decorator: str, layers: tuple[dict[str, E], dict[str, E]], entry: E, override: bool) -> E:
    """Put ``entry`` into the built-in or extension layer; collisions as documented on :func:`scene`."""
    builtins, extensions = layers
    name, cls, origin = entry.name, entry.cls, entry.origin
    if is_builtin_module(cls.__module__):
        if name in builtins:
            raise VidgenError(
                f"built-in {kind} '{name}' is defined twice ({builtins[name].cls.__module__} and {cls.__module__})"
            )
        builtins[name] = entry
        return entry
    if name in extensions:
        raise VidgenError(
            f"{kind} '{name}' is defined twice: in {extensions[name].origin} and in {origin}; rename one of them"
        )
    builtin = builtins.get(name)
    if builtin is not None and not override:
        raise VidgenError(
            f"{kind} '{name}' in {origin} has the same name as a built-in {kind}; "
            f"rename it, or use @{decorator}({name!r}, override=True) to replace the built-in"
        )
    if builtin is None and override:
        log.warning("%s: @%s(%r, override=True) but there is no built-in '%s' to override", origin, decorator, name, name)
    if builtin is not None:
        log.warning("%s: %s '%s' overrides the built-in %s", origin, kind, name, kind)
    entry = type(entry)(name, cls, origin, overrides=builtin)  # type: ignore[arg-type]
    extensions[name] = entry
    return entry


def register(name: str, cls: type[NarratedScene], *, override: bool = False) -> SceneType:
    """Register ``cls`` as scene type ``name`` (the function form of :func:`scene`)."""
    if not isinstance(name, str) or not re.match(ID_PATTERN, name):
        raise VidgenError(f"invalid scene type name {name!r}: use letters, digits and '_' only")
    _check_class(name, cls)
    entry = SceneType(name, cls, origin_of(cls.__module__))
    return _add("scene type", "scene", (_builtins, _extensions), entry, override)


def scene(name: str, *, override: bool = False) -> Callable[[S], S]:
    """Class decorator: register a :class:`NarratedScene` subclass as scene type ``name``.

    ``name`` is what ``type:`` refers to in video.yaml. Two extensions may not use the same name.
    Reusing a built-in's name is an error unless ``override=True`` (then the extension replaces
    the built-in and a warning is logged).
    """

    if isinstance(name, type):
        raise VidgenError(f'use @scene("name") with a scene type name, not bare @scene (on {name.__qualname__})')

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


# ----- actions -----------------------------------------------------------------------------------


def register_action(name: str, cls: type[Action], *, override: bool = False) -> ActionType:
    """Register ``cls`` as action type ``name`` (the function form of :func:`action`)."""
    from vidgen.actions import check_action_class

    if not isinstance(name, str) or not re.match(ID_PATTERN, name):
        raise VidgenError(f"invalid action name {name!r}: use letters, digits and '_' only")
    check_action_class(name, cls)
    entry = ActionType(name, cls, origin_of(cls.__module__))
    return _add("action", "action", (_builtin_actions, _extension_actions), entry, override)


def action(name: str, *, override: bool = False) -> Callable[[S], S]:
    """Class decorator: register an :class:`~vidgen.actions.Action` subclass as per-beat action
    ``name`` (what ``action:`` refers to in a beat's ``actions``). Name collisions are handled
    as for :func:`scene`."""

    if isinstance(name, type):
        raise VidgenError(f'use @action("name") with an action name, not bare @action (on {name.__qualname__})')

    def decorate(cls: S) -> S:
        register_action(name, cls, override=override)  # type: ignore[arg-type]
        return cls

    return decorate


def find_action(name: str) -> ActionType | None:
    """The action type ``name`` (extensions shadow built-ins they override), or ``None``."""
    return _extension_actions.get(name) or _builtin_actions.get(name)


def action_names() -> list[str]:
    """All registered action names, sorted."""
    return sorted({*_builtin_actions, *_extension_actions})


def all_actions() -> list[ActionType]:
    """All effective action types sorted by name."""
    return [find_action(n) for n in action_names()]  # type: ignore[misc]


def unknown_action_message(name: str) -> str:
    """``unknown action 'x'`` plus close matches and the list of known actions."""
    import difflib

    known = action_names()
    message = f"unknown action '{name}'"
    close = difflib.get_close_matches(name, known, n=3)
    if close:
        message += f"; did you mean {' or '.join(repr(c) for c in close)}?"
    return message + f" (known actions: {', '.join(known) or 'none'})"


# ----- isolation -------------------------------------------------------------------------------


def reset() -> None:
    """Forget all extension scene types and actions (built-ins stay)."""
    _extensions.clear()
    _extension_actions.clear()


def snapshot() -> Snapshot:
    """A copy of the extension layer, for :func:`restore`."""
    return dict(_extensions), dict(_extension_actions)


def restore(state: Snapshot) -> None:
    """Restore the extension layer saved by :func:`snapshot`."""
    scenes, actions = state
    _extensions.clear()
    _extensions.update(scenes)
    _extension_actions.clear()
    _extension_actions.update(actions)


@contextmanager
def isolated() -> Iterator[None]:
    """Run with an empty extension layer; the previous one is restored on exit."""
    saved = snapshot()
    reset()
    try:
        yield
    finally:
        restore(saved)
