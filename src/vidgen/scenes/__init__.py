"""Built-in scene library.

Built-in scene types use exactly the same API as project extensions (``from vidgen.api import *``
and ``@scene``); a module here is registered as "builtin" because it lives inside ``vidgen``.
Importing this package imports every scene module (add new modules to the import list below)
and the built-in per-beat actions (``actions``: reveal, dim, highlight).
"""

from vidgen.scenes import (  # noqa: F401
    actions,
    bar_chart,
    bullets,
    chapter,
    code,
    code_walkthrough,
    comparison,
    diagram,
    end_card,
    equation,
    equation_derivation,
    heatmap,
    histogram,
    icon_grid,
    image,
    line_chart,
    network,
    pie,
    process,
    quote,
    scatter,
    screenshot,
    stat,
    table,
    text_card,
    timeline,
    title,
    video_clip,
)
