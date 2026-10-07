"""Built-in scene library.

Built-in scene types use exactly the same API as project extensions (``from vidgen.api import *``
and ``@scene``); a module here is registered as "builtin" because it lives inside ``vidgen``.
Importing this package imports every scene module (add new modules to the import list below)
the built-in per-beat actions (``actions``: reveal, dim, highlight, zoom, transform;
``callout_action``: callout; ``sfx_action``: sfx) and the
built-in overlays (``overlays``: lower_third, watermark; ``progress``: progress_bar,
chapter_indicator; ``captions``: captions).
"""

from vidgen.scenes import (  # noqa: F401
    actions,
    bar_chart,
    bullets,
    callout_action,
    captions,
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
    overlays,
    pie,
    process,
    progress,
    quote,
    scatter,
    screenshot,
    sfx_action,
    stat,
    table,
    text_card,
    timeline,
    title,
    video_clip,
    world_map,
)
