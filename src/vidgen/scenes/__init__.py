"""Built-in scene library.

Built-in scene types use exactly the same API as project extensions (``from vidgen.api import *``
and ``@scene``); a module here is registered as "builtin" because it lives inside ``vidgen``.
Importing this package imports every scene module (add new modules to the import list below).
"""

from vidgen.scenes import (  # noqa: F401
    bar_chart,
    bullets,
    code,
    end_card,
    equation,
    icon_grid,
    image,
    line_chart,
    quote,
    text_card,
    title,
)
