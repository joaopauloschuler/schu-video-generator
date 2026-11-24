"""The ``guide: canny`` control video (DESIGN.md §113.21): white Canny edges on black, made from
a colour clip, with the edges in bright areas (a sun glint on water) removed.

The edges follow OpenCV's ``cv2.Canny(gray, low, high)`` (3x3 Sobel, L1 gradient, the same
non-maximum suppression, 8-connected hysteresis) in numpy and scipy, with no blur first (a blur
erased thin outlines in the test, Step 405). The glint mask is ``make_canny_soft.py``'s: the grey
frame blurred over :data:`GLINT_BLUR` px; edges go where it is brighter than ``glint`` (0-255),
the mask's edge softened over :data:`FEATHER` px.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from vidgen.errors import VidgenError

#: The tested defaults (Step 405, RUNLOG run 2): OpenCV's thresholds of the official workflow, and the glint luma.
LOW, HIGH, GLINT = 92, 200, 150
#: The blur (px, odd) the glint test looks at, and the softening of the mask's edge (px, odd).
GLINT_BLUR, FEATHER = 41, 31
#: H.264 quality of the edge video (thin white lines show compression).
CRF = 12


def _gaussian(image: np.ndarray, size: int) -> np.ndarray:
    """``cv2.GaussianBlur(image, (size, size), 0)`` in float (OpenCV's sigma for ``size``, mirrored border)."""
    from scipy.ndimage import gaussian_filter

    sigma = 0.3 * ((size - 1) * 0.5 - 1) + 0.8
    return gaussian_filter(image.astype(np.float32), sigma, mode="mirror", truncate=((size - 1) / 2) / sigma)


def edges(gray: np.ndarray, low: int = LOW, high: int = HIGH) -> np.ndarray:
    """Canny edges (``uint8``, 0 or 255) of the grey frame ``gray``, as ``cv2.Canny(gray, low, high)``."""
    from scipy.ndimage import convolve, label

    g = gray.astype(np.int32)
    dx = convolve(g, np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]), mode="nearest")
    dy = convolve(g, np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]]), mode="nearest")
    mag = np.abs(dx) + np.abs(dy)
    p = np.pad(mag, 1)
    h, w = mag.shape

    def at(oy: int, ox: int) -> np.ndarray:
        return p[1 + oy:1 + oy + h, 1 + ox:1 + ox + w]

    ax, ay = np.abs(dx).astype(np.float64), np.abs(dy).astype(np.float64)
    tg22 = ax * 0.4142135623730951
    horizontal = ay < tg22
    vertical = ~horizontal & (ay > tg22 + 2 * ax)
    s = np.where((dx ^ dy) < 0, -1, 1)
    diag = (np.where(s < 0, mag > at(-1, 1), mag > at(-1, -1)) & np.where(s < 0, mag > at(1, -1), mag > at(1, 1)))
    peak = np.where(horizontal, (mag > at(0, -1)) & (mag >= at(0, 1)),
                    np.where(vertical, (mag > at(-1, 0)) & (mag >= at(1, 0)), diag))
    candidate = peak & (mag > low)
    strong = candidate & (mag > high)
    labels, count = label(candidate, structure=np.ones((3, 3), dtype=bool))
    keep = np.zeros(count + 1, dtype=bool)
    keep[np.unique(labels[strong])] = True
    keep[0] = False
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def glint_edges(gray: np.ndarray, low: int = LOW, high: int = HIGH, glint: int | None = GLINT) -> np.ndarray:
    """:func:`edges` of ``gray`` without the edges where it is brighter than ``glint`` (``None``: all edges)."""
    e = edges(gray, low, high)
    if glint is None:
        return e
    bright = np.round(_gaussian(gray, GLINT_BLUR))
    keep = _gaussian((bright <= glint).astype(np.float32), FEATHER)
    return np.clip(e.astype(np.float32) * keep, 0, 255).astype(np.uint8)


def rgb_to_gray(frame: np.ndarray) -> np.ndarray:
    """OpenCV's ``COLOR_RGB2GRAY`` of an ``(h, w, 3)`` uint8 frame (its fixed-point weights)."""
    f = frame.astype(np.int32)
    return ((f[..., 0] * 4899 + f[..., 1] * 9617 + f[..., 2] * 1868 + 8192) >> 14).astype(np.uint8)


def make_canny(ffmpeg: str, source: Path, dest: Path, *, width: int, height: int,
               low: int = LOW, high: int = HIGH, glint: int | None = GLINT) -> int:
    """Write ``dest``: the edges of every frame of the colour video ``source`` scaled to cover
    ``width`` x ``height`` and centre-cropped, at its frame rate, silent H.264. Returns the frame count."""
    from vidgen.render.ffmpeg import probe

    fps = probe(source).fps
    size = f"{width}:{height}"
    decode = subprocess.Popen(
        [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-i", str(source), "-an",
         "-vf", f"scale={size}:force_original_aspect_ratio=increase:flags=lanczos,crop={size}", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    encode = subprocess.Popen(
        [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{width}x{height}",
         "-r", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264", "-crf", str(CRF), "-pix_fmt", "yuv420p", str(dest)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert decode.stdout is not None and encode.stdin is not None
    frames, frame_bytes = 0, width * height * 3
    try:
        while True:
            data = decode.stdout.read(frame_bytes)
            if len(data) < frame_bytes:
                break
            rgb = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 3)
            encode.stdin.write(glint_edges(rgb_to_gray(rgb), low, high, glint).tobytes())
            frames += 1
    finally:
        encode.stdin.close()
        decoded, encoded = decode.wait(), encode.wait()
    if decoded or encoded or frames == 0:
        failed = decode if decoded or frames == 0 else encode
        details = (failed.stderr.read() if failed.stderr else b"").decode("utf-8", errors="replace").strip()[-500:]
        raise VidgenError(f"could not make the canny guide {dest.name} from {source.name}: {details or 'no frames read'}")
    return frames


__all__ = ["FEATHER", "GLINT", "GLINT_BLUR", "HIGH", "LOW", "edges", "glint_edges", "make_canny", "rgb_to_gray"]
