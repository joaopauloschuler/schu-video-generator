"""Smaller copies of the pictures a video job sends inline (DESIGN.md §113.7).

Reference sheet pictures are large (seedream-4.5: 2048x3642 PNGs of 5-7 MB), and six of them
plus a style frame made a 48 MB request. Before a local picture goes into a request as a data
URL, :func:`sendable_picture` makes a copy whose longest side is at most
:data:`PICTURE_MAX_SIDE` px, saved as JPEG (quality :data:`JPEG_QUALITY`) unless the picture has
transparency (then PNG). The copies are cached in ``build/videogen/pictures/`` by the source's
SHA-256 and the size limit; the source files are never changed. No model in OpenRouter's list
names a largest reference size, so one limit serves every model.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import replace
from pathlib import Path

from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic
from vidgen.videogen import MediaInput, VideoRequest

#: Longest side, in pixels, of a picture sent inline to a video model.
PICTURE_MAX_SIDE = 1280
#: JPEG quality of the copies.
JPEG_QUALITY = 90
#: Where the copies are cached, relative to the project.
PICTURES_DIR = Path("build") / "videogen" / "pictures"
#: Sources sent as they are when already within the size limit.
_KEPT_SUFFIXES = (".jpg", ".jpeg", ".webp")


def _has_transparency(image: object) -> bool:
    from PIL import Image

    assert isinstance(image, Image.Image)
    if image.mode in ("RGBA", "LA", "PA"):
        low, _ = image.getchannel("A").getextrema()
        return low < 255
    return image.mode == "P" and "transparency" in image.info


def sendable_picture(path: Path, root: Path, *, max_side: int = PICTURE_MAX_SIDE) -> Path:
    """The file to send for the picture ``path``: ``path`` itself when it is a JPEG / WebP within
    ``max_side``, else a copy in ``<root>/build/videogen/pictures/`` (made once; reused while the
    source's contents are the same)."""
    from PIL import Image

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise VidgenError(f"cannot read the picture {path}: {exc.strerror or exc}") from None
    digest = hashlib.sha256(data).hexdigest()[:24]
    for suffix in (".jpg", ".png"):
        cached = root / PICTURES_DIR / f"{digest}_{max_side}{suffix}"
        if cached.is_file():
            return cached
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if max(image.size) <= max_side and path.suffix.lower() in _KEPT_SUFFIXES:
                return path
            transparent = _has_transparency(image)
            if max(image.size) > max_side:
                scale = max_side / max(image.size)
                size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
                image = image.convert("RGBA" if transparent else "RGB").resize(size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            if transparent:
                image.convert("RGBA").save(buffer, "PNG", optimize=True)
            else:
                image.convert("RGB").save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True)
    except OSError as exc:
        raise VidgenError(f"cannot read the picture {path}: {exc}") from None
    cached = root / PICTURES_DIR / f"{digest}_{max_side}{'.png' if transparent else '.jpg'}"
    write_bytes_atomic(cached, buffer.getvalue())
    return cached


def _sendable(media: MediaInput, root: Path) -> MediaInput:
    if media.kind != "image" or media.path is None:
        return media
    return replace(media, path=sendable_picture(media.path, root))


def sendable_request(request: VideoRequest, root: Path) -> VideoRequest:
    """``request`` with each local picture (frame images and picture references) replaced by its
    sendable copy (:func:`sendable_picture`). Its cache key stays that of ``request``."""
    return replace(
        request,
        frame_images=tuple(_sendable(m, root) for m in request.frame_images),
        references=tuple(_sendable(m, root) for m in request.references),
    )


__all__ = ["JPEG_QUALITY", "PICTURES_DIR", "PICTURE_MAX_SIDE", "sendable_picture", "sendable_request"]
