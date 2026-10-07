"""What the MCP server (:mod:`vidgen.mcp_server`) needs that does not need the MCP SDK: the
folder policy, command lines of the tools, progress parsing and pictures sized for a model
(DESIGN.md §62). Kept apart so it is tested without the optional ``mcp`` package."""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError

#: Longest side of a picture returned to the client (Claude's vision models work at up to ~1568
#: px; larger pictures are scaled down by the client anyway and cost more tokens).
MAX_IMAGE_SIDE = 1568
#: A PNG bigger than this is sent as a JPEG instead (contact sheets stay legible at quality 85).
MAX_PNG_BYTES = 800_000
JPEG_QUALITY = 85
#: Pictures one tool call returns by default (more with ``image_offset``: the stills are reused).
DEFAULT_IMAGES = 3
#: Pictures one tool call returns at most.
MAX_IMAGES = 8


class PathOutsideRoot(VidgenError):
    """A tool was given a path outside the server's root folder."""


@dataclass(frozen=True)
class RootPolicy:
    """The one folder (and its subfolders) the tools may read and write.

    Paths given to a tool are relative to ``root`` (absolute ones must lie inside it); they are
    resolved, symbolic links included, before the check, so ``..`` or a link cannot leave it.
    """

    root: Path

    @classmethod
    def at(cls, root: Path) -> RootPolicy:
        """The policy for ``root`` (must be an existing folder)."""
        resolved = root.expanduser().resolve()
        if not resolved.is_dir():
            raise VidgenError(f"--root {root}: not a folder")
        return cls(resolved)

    def path(self, value: str, what: str = "path") -> Path:
        """``value`` (relative to the root, or absolute) resolved; outside the root: an error."""
        text = value.strip()
        if not text:
            raise VidgenError(f"{what}: empty path")
        candidate = Path(text).expanduser()
        resolved = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise PathOutsideRoot(f"{what} '{value}' is outside the folder this server may use ({self.root})")
        return resolved

    def inside(self, path: Path) -> bool:
        """Whether ``path`` (e.g. one a command reported) lies inside the root."""
        resolved = path.resolve()
        return resolved == self.root or self.root in resolved.parents


def cli_args(command: Sequence[str], positionals: Sequence[str] = (), options: Mapping[str, Any] | None = None) -> list[str]:
    """The ``vidgen`` arguments of a tool call, always with ``--json``.

    ``options`` maps option names (without ``--``) to values: ``True`` adds the flag, ``False`` /
    ``None`` / empty lists leave it out, a list repeats the option, anything else is
    ``--name=value`` (so a value starting with ``-`` is never read as an option). Positionals
    must not start with ``-`` (callers pass resolved paths or checked names).
    """
    args = list(command)
    for value in positionals:
        if value.startswith("-"):
            raise VidgenError(f"'{value}': a name or path may not start with '-'")
        args.append(value)
    for name, value in (options or {}).items():
        if value is None or value is False:
            continue
        if value is True:
            args.append(f"--{name}")
        elif isinstance(value, (list, tuple)):
            args.extend(f"--{name}={item}" for item in value)
        else:
            args.append(f"--{name}={value}")
    args.append("--json")
    return args


def cost_refusal(tool: str, what: str) -> str:
    """The message of a paid call made without ``confirm_cost=True``."""
    return (
        f"{tool} with dry_run=false {what}, which costs money. Run {tool} with dry_run=true first "
        f"(free: it lists what would be made and the size of the bill), show that to the user, then "
        f"call again with dry_run=false and confirm_cost=true."
    )


@dataclass(frozen=True)
class Picture:
    """A picture prepared for the client: encoded bytes, ``png`` or ``jpeg``, and its size."""

    data: bytes
    format: str
    width: int
    height: int
    source: Path


def prepare_picture(path: Path, max_side: int = MAX_IMAGE_SIDE) -> Picture:
    """``path`` scaled down to at most ``max_side`` pixels on its longest side; PNG unless that is
    over :data:`MAX_PNG_BYTES`, then JPEG (transparency flattened on white)."""
    from PIL import Image

    with Image.open(path) as opened:
        image = opened.convert("RGBA") if opened.mode in ("RGBA", "LA", "P") else opened.convert("RGB")
    if max(image.size) > max_side:
        scale = max_side / max(image.size)
        image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    if out.tell() <= MAX_PNG_BYTES:
        return Picture(out.getvalue(), "png", image.width, image.height, path)
    if image.mode == "RGBA":
        flat = Image.new("RGB", image.size, (255, 255, 255))
        flat.paste(image, mask=image.getchannel("A"))
        image = flat
    out = io.BytesIO()
    image.convert("RGB").save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return Picture(out.getvalue(), "jpeg", image.width, image.height, path)


def page_of(paths: Sequence[Path], offset: int, count: int) -> tuple[list[Path], dict[str, Any]]:
    """The ``count`` pictures from ``offset`` (``count`` capped at :data:`MAX_IMAGES`) and a note
    for the client: ``{total, offset, returned: [paths], next_offset}`` (``next_offset`` is
    ``None`` when nothing is left)."""
    if offset < 0 or count < 0:
        raise VidgenError("images and image_offset must be 0 or more")
    count = min(count, MAX_IMAGES)
    chosen = list(paths[offset : offset + count])
    after = offset + len(chosen)
    note = {
        "total": len(paths),
        "offset": offset,
        "returned": [str(p) for p in chosen],
        "next_offset": after if after < len(paths) else None,
    }
    return chosen, note
