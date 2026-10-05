"""Pipeline hooks (DESIGN.md §6.2).

``@hook(event)`` registers a function ``fn(ctx: HookContext)``. :func:`dispatch` calls the hooks
of an event in registration order (built-in hooks first, then the project's). An exception in a
hook aborts the command with a :class:`VidgenError` naming the hook.

Like the scene registry there are two layers: hooks defined in ``vidgen.*`` modules are
permanent; extension hooks belong to the active project and are cleared by :func:`reset` and
saved/restored by :func:`snapshot`/:func:`restore`/:func:`isolated`. This module does not
import manim.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidgen._origin import is_builtin_module, origin_of
from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.project import Project

EVENTS: tuple[str, ...] = ("pre_tts", "post_tts", "pre_render", "post_scene", "post_render")

HookFn = Callable[["HookContext"], Any]


@dataclass
class HookContext:
    """What a hook receives: the project, the event name and event-specific ``data``.

    Hooks may modify ``data``; the caller of :func:`dispatch` gets the same context back.
    """

    project: Project
    event: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Hook:
    """A registered hook function and where it was defined."""

    event: str
    fn: HookFn
    origin: str

    @property
    def name(self) -> str:
        """``module.function`` for messages."""
        return f"{self.fn.__module__}.{self.fn.__qualname__}"


_builtin_hooks: list[Hook] = []
_extension_hooks: list[Hook] = []

Snapshot = list[Hook]


def _check_event(event: str) -> None:
    if event not in EVENTS:
        raise VidgenError(f"unknown hook event {event!r}; events: {', '.join(EVENTS)}")


def register(event: str, fn: HookFn) -> Hook:
    """Register ``fn`` for ``event`` (the function form of :func:`hook`)."""
    _check_event(event)
    if not callable(fn):
        raise VidgenError(f"@hook({event!r}) must decorate a function, got {fn!r}")
    module = getattr(fn, "__module__", "") or ""
    entry = Hook(event, fn, origin_of(module))
    (_builtin_hooks if is_builtin_module(module) else _extension_hooks).append(entry)
    return entry


def hook(event: str) -> Callable[[HookFn], HookFn]:
    """Decorator: call the function at ``event`` with a :class:`HookContext`.

    Events: ``pre_tts``, ``post_tts``, ``pre_render``, ``post_scene``, ``post_render``.
    """
    _check_event(event)

    def decorate(fn: HookFn) -> HookFn:
        register(event, fn)
        return fn

    return decorate


def registered(event: str | None = None) -> list[Hook]:
    """Registered hooks in call order, optionally only those of ``event``."""
    hooks = [*_builtin_hooks, *_extension_hooks]
    return [h for h in hooks if event is None or h.event == event]


def dispatch(event: str, project: Project, **data: Any) -> HookContext:
    """Call every hook registered for ``event``, in order; returns the (possibly modified) context.

    A hook that raises aborts dispatch with a :class:`VidgenError` naming the hook and its file.
    """
    _check_event(event)
    ctx = HookContext(project=project, event=event, data=data)
    for entry in registered(event):
        try:
            entry.fn(ctx)
        except VidgenError as exc:
            raise VidgenError(f"hook {entry.name} ({entry.origin}) failed during {event}: {exc}") from exc
        except Exception as exc:
            details = "".join(traceback.format_exception(exc)).rstrip()
            raise VidgenError(
                f"hook {entry.name} ({entry.origin}) failed during {event}: "
                f"{type(exc).__name__}: {exc}\n{details}"
            ) from exc
    return ctx


# ----- isolation -------------------------------------------------------------------------------


def reset() -> None:
    """Forget all extension hooks (built-in hooks stay)."""
    _extension_hooks.clear()


def snapshot() -> Snapshot:
    """A copy of the extension hooks, for :func:`restore`."""
    return list(_extension_hooks)


def restore(state: Snapshot) -> None:
    """Restore extension hooks saved by :func:`snapshot`."""
    _extension_hooks[:] = state


@contextmanager
def isolated() -> Iterator[None]:
    """Run with no extension hooks; the previous ones are restored on exit."""
    saved = snapshot()
    reset()
    try:
        yield
    finally:
        restore(saved)
