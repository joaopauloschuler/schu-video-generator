"""The clip a ``web`` or ``3d`` scene's drawn frames are kept in until the scene plays them
(DESIGN.md §120.9): lossless FFV1 by default, or with ``render.intermediate: compact`` a small
H.264 picture (4:4:4, CRF :data:`COMPACT_CRF`) and, for frames with alpha, a lossless FFV1
alpha stream beside it in the same Matroska file (stream title :data:`ALPHA_TITLE`, read back
by :class:`vidgen.clips.ClipReader`).

:func:`write_frames_clip` writes one; :func:`clip_serves` tells whether a kept clip stored one
way serves a render that asks for another.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import numpy as np

from vidgen.errors import VidgenError

#: How a scene's drawn frames are kept (``render.intermediate``).
Intermediate = Literal["lossless", "compact"]
INTERMEDIATES: tuple[str, ...] = ("lossless", "compact")
#: The compact picture: libx264 at this CRF and preset, in 4:4:4 (no chroma subsampling, so
#: coloured edges stay sharp; the final encode subsamples once). Measured on Escapement's
#: frames (§120.9): 4.6 times smaller than FFV1, 39-41 dB PSNR, SSIM 0.96-0.97 against the
#: lossless frames, and the final H.264 made from it within 0.25 dB of the one made from them.
COMPACT_CRF = "12"
COMPACT_PRESET = "veryfast"
#: Title of the lossless alpha stream of a compact clip with alpha.
ALPHA_TITLE = "alpha"


def clip_serves(stored: str | None, wanted: str) -> bool:
    """Whether a kept clip stored as ``stored`` (``None``: written before §120.9, lossless)
    serves a render asking for ``wanted``: a lossless clip serves both, a compact one only
    ``compact`` (asking for ``lossless`` draws the frames again)."""
    return (stored or "lossless") == "lossless" or wanted == "compact"


def write_frames_clip(path: Path, fps: int, size: tuple[int, int], frames: Iterable[np.ndarray], *, alpha: bool = False,
                      intermediate: str = "lossless") -> None:
    """Write ``frames`` (RGB arrays, H x W x 3, ``size`` = (W, H); with ``alpha`` RGBA, H x W x 4,
    straight alpha) in order to ``path`` (Matroska): ``lossless``, one FFV1 stream (``bgra`` with
    alpha, else ``bgr0``); ``compact``, an H.264 4:4:4 picture and, with ``alpha``, a lossless
    FFV1 ``gray`` alpha stream. Written to a ``.partial`` file first, so a failure (also one
    raised while ``frames`` is iterated) leaves none."""
    import av

    if intermediate not in INTERMEDIATES:
        raise VidgenError(f"unknown intermediate '{intermediate}' (one of {', '.join(INTERMEDIATES)})")
    width, height = size
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    given = "rgba" if alpha else "rgb24"
    try:
        with av.open(str(partial), mode="w", format="matroska") as container:
            if intermediate == "lossless":
                picture = container.add_stream("ffv1", rate=fps)
                stored = "bgra" if alpha else "bgr0"
            else:
                picture = container.add_stream("libx264", rate=fps, options={"crf": COMPACT_CRF, "preset": COMPACT_PRESET})
                stored = "yuv444p"
            picture.width, picture.height, picture.pix_fmt = width, height, stored
            mask = None
            if intermediate == "compact" and alpha:
                mask = container.add_stream("ffv1", rate=fps)
                mask.width, mask.height, mask.pix_fmt = width, height, "gray"
                mask.metadata["title"] = ALPHA_TITLE
            for n, pixels in enumerate(frames):
                frame = av.VideoFrame.from_ndarray(pixels, format=given).reformat(format=stored)
                frame.pts = n
                container.mux(picture.encode(frame))
                if mask is not None:
                    plane = av.VideoFrame.from_ndarray(np.ascontiguousarray(pixels[..., 3]), format="gray")
                    plane.pts = n
                    container.mux(mask.encode(plane))
            container.mux(picture.encode())
            if mask is not None:
                container.mux(mask.encode())
        try:
            os.replace(partial, path)
        except PermissionError:   # Windows: the old clip is open in another program (a player)
            raise VidgenError(f"cannot replace {path}: close the program that has it open and render again") from None
    finally:
        partial.unlink(missing_ok=True)


__all__ = ["ALPHA_TITLE", "COMPACT_CRF", "COMPACT_PRESET", "INTERMEDIATES", "Intermediate", "clip_serves", "write_frames_clip"]
