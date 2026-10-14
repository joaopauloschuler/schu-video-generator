"""Composed music played with real instruments: symusic (optional extra ``music``) renders notes
with a SoundFont (:mod:`vidgen.soundfont`). Nothing here imports symusic until it is needed."""

from __future__ import annotations

import importlib.metadata
from typing import Any

from vidgen import DIST_NAME
from vidgen.errors import VidgenError

INSTALL_COMMAND = f'pip install "{DIST_NAME}[music]"'
#: The symusic release the extra pins; 0.6.0's SoundFont render fails (TypeError in ``render``).
SYMUSIC_VERSION = "0.5.9"


def symusic_version() -> str | None:
    """The installed symusic version, or ``None`` when it is not installed."""
    try:
        return importlib.metadata.version("symusic")
    except importlib.metadata.PackageNotFoundError:
        return None


def symusic_status() -> str:
    """One line on symusic: installed and usable, another version, or how to install it."""
    version = symusic_version()
    if version is None:
        return f"not installed: {INSTALL_COMMAND}"
    if version != SYMUSIC_VERSION:
        return f"{version} installed, but vidgen needs {SYMUSIC_VERSION}: {INSTALL_COMMAND}"
    return version


def require_symusic() -> Any:
    """Import and return the ``symusic`` module; :class:`VidgenError` naming the extra when it is
    missing or another version than :data:`SYMUSIC_VERSION` is installed."""
    version = symusic_version()
    if version is None:
        raise VidgenError(f"composed music needs the optional extra: {INSTALL_COMMAND} (symusic {SYMUSIC_VERSION}, ~3 MB)")
    if version != SYMUSIC_VERSION:
        raise VidgenError(
            f"composed music needs symusic {SYMUSIC_VERSION}, and {version} is installed "
            f"(0.6.0 cannot render with a SoundFont): {INSTALL_COMMAND}"
        )
    import symusic

    return symusic
