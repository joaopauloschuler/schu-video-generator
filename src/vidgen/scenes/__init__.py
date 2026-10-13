"""Built-in scene library.

Built-in scene types use exactly the same API as project extensions (``from vidgen.api import *``
and ``@scene``); a module here is registered as "builtin" because it lives inside ``vidgen``.
Importing this package imports every scene module (add new modules to the import list below)
the built-in per-beat actions (``actions``: reveal, dim, highlight, zoom, pan, follow,
transform; ``callout_action``: callout; ``sfx_action``: sfx;
``particles_action``: particles; ``acting``: say, look_at, turn, emote, pose, react; ``moving``: walk_to, enter,
exit, gesture, jump; ``keyframes_action``: keyframes, move_along; ``handling``: pick_up, hold,
put_down, give, throw; ``sitting``: sit_on, lean_on, stand_up; ``shot_action``: shot;
``light_action``: light; ``wind_action``: wind; ``effect_action``: effect) and the
built-in overlays (``overlays``: lower_third, watermark; ``progress``: progress_bar,
chapter_indicator; ``captions``: captions).
"""

from vidgen.scenes import (  # noqa: F401
    acting,
    actions,
    bar_chart,
    bullets,
    callout_action,
    captions,
    card,
    chapter,
    code,
    code_walkthrough,
    comparison,
    diagram,
    effect_action,
    end_card,
    equation,
    equation_derivation,
    handling,
    heatmap,
    histogram,
    icon_grid,
    image,
    keyframes_action,
    light_action,
    line_chart,
    moving,
    network,
    overlays,
    particles_action,
    pie,
    process,
    progress,
    quote,
    scatter,
    shot_action,
    sitting,
    screenshot,
    sfx_action,
    stage,
    stat,
    table,
    text_card,
    timeline,
    title,
    video_clip,
    wind_action,
    world_map,
)
