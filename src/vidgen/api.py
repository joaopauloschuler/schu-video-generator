"""The public surface for project extensions and built-in scenes (DESIGN.md §6.4).

Use ``from vidgen.api import *``: it gives every name of ``from manim import *`` plus the vidgen
names below. Where a manim name and a vidgen name collide, vidgen wins; the only collision is
``scene`` (manim's ``manim.scene`` subpackage, shadowed by vidgen's ``@scene`` decorator).
Anything not exported here is internal and may change.
"""

from __future__ import annotations

_before = set(globals())
from manim import *  # noqa: E402,F403

_MANIM_NAMES = frozenset(n for n in set(globals()) - _before if not n.startswith("_"))
del _before

from vidgen.errors import VidgenError  # noqa: E402
from vidgen.helpers import MT, T, column, counter, dense_pairs, edges, grouped_pairs, resolve_color  # noqa: E402
from vidgen.hooks import HookContext, hook  # noqa: E402
from vidgen.registry import scene  # noqa: E402
from vidgen.runtime import current_project, current_theme  # noqa: E402
from vidgen.scene import NarratedScene, SceneParams  # noqa: E402


def register_theme_defaults(colors: dict[str, str] | None = None, sizes: dict[str, float] | None = None) -> None:
    """Add default theme tokens for this project (``video.yaml`` values still win).

    Call at module level in an extension: ``register_theme_defaults({"k2": "#F2A541"})``.
    """
    current_theme().add_defaults(colors=colors, sizes=sizes)


VIDGEN_NAMES: tuple[str, ...] = (
    "NarratedScene",
    "SceneParams",
    "scene",
    "hook",
    "HookContext",
    "register_theme_defaults",
    "current_theme",
    "current_project",
    "VidgenError",
    "T",
    "MT",
    "resolve_color",
    "column",
    "edges",
    "dense_pairs",
    "grouped_pairs",
    "counter",
)

#: manim names replaced by a vidgen name of the same spelling.
SHADOWED_MANIM_NAMES = frozenset(_MANIM_NAMES & set(VIDGEN_NAMES))

__all__ = sorted(_MANIM_NAMES | set(VIDGEN_NAMES))
