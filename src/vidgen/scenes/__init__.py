"""Built-in scene library.

Built-in scene types use exactly the same API as project extensions (``from vidgen.api import *``
and ``@scene``); a module here is registered as "builtin" because it lives inside ``vidgen``.
Importing this package imports every scene module (add new modules to the import list below).
"""

from vidgen.scenes import text_card  # noqa: F401
