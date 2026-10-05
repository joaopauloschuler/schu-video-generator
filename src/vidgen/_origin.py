"""Where a registered scene type or hook comes from (built-in or a project extension file)."""

from __future__ import annotations

import sys
from pathlib import Path

from vidgen import runtime

BUILTIN = "builtin"


def is_builtin_module(module_name: str) -> bool:
    """True for modules inside the ``vidgen`` package (built-ins use the same API as extensions)."""
    return module_name == "vidgen" or module_name.startswith("vidgen.")


def origin_of(module_name: str) -> str:
    """``"builtin"`` for vidgen modules, else the defining file (relative to the project root
    when possible) or, failing that, the module name."""
    if is_builtin_module(module_name):
        return BUILTIN
    module = sys.modules.get(module_name)
    file = getattr(module, "__file__", None)
    if not file:
        return module_name
    path = Path(file)
    if runtime.has_context():
        try:
            return path.resolve().relative_to(runtime.current_project().root.resolve()).as_posix()
        except ValueError:
            pass
    return str(path)
