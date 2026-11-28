"""The depth pass of a three.js ``web`` scene: ``guide: depth`` of a ``space`` scene,
or of a ``web`` scene whose page draws through ``vidgen/three-finish``.

The page draws the scene as for its picture (the scene's own shaders: a sea displaced in its vertex
shader keeps its waves), then ``Finish`` packs the depth buffer, as the distance ``z`` along the view in
metres, into the red, green and blue of each pixel: ``n = 1 + round(u (2^24 - 2))`` with
``u = (log2 z - LOG_MIN) / LOG_SPAN``; ``n = 0`` where nothing was drawn (the sky, the background). The
frames are kept lossless beside the scene's clip, ``<render_dir>/web/<scene>.depth.mkv``.

:func:`cut_depth` makes the grey guide from a part of it, with **one range for the whole shot** (no
range per frame, so nothing flickers as things move): grey ``= near / z`` (near white, far dark, the sky
and the background black: ``z`` infinite), ``near`` the distance only :data:`NEAR_SHARE` of the shot's
drawn pixels are nearer than (they are white). Proportional to ``1 / z`` (disparity), as depth
estimators and the depth-control video models trained on them give it; a ``3d`` scene's pass is linear
in ``z`` between a fitted near and far, which suits a bounded set, not a sea to the horizon.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from vidgen.config import GUIDES_OF_WEB_SCENES
from vidgen.errors import VidgenError

#: The guide passes a three.js web scene draws (``depth`` only).
WEB_GUIDE_PASSES: tuple[str, ...] = GUIDES_OF_WEB_SCENES
#: The packing's range of log2 metres: 2^-16 m to 2^32 m (vidgen/three-finish's ``DEPTH_LOG``).
LOG_MIN = -16.0
LOG_SPAN = 48.0
#: The largest packed number (``n`` runs from 1 to it; 0 is "nothing drawn").
LEVELS = 2 ** 24 - 1
#: The share of a shot's drawn pixels nearer than its ``near`` (white).
NEAR_SHARE = 0.01
#: The histogram of a shot's depths: bins per octave of distance.
BINS_PER_OCTAVE = 64


def pack(metres: np.ndarray) -> np.ndarray:
    """The page's packing of distances (``inf``: nothing drawn) as RGB bytes ``(..., 3)`` (for tests and checks)."""
    z = np.asarray(metres, dtype=np.float64)
    drawn = np.isfinite(z)
    u = np.clip((np.log2(np.where(drawn, np.maximum(z, 1e-30), 1.0)) - LOG_MIN) / LOG_SPAN, 0.0, 1.0)
    n = np.where(drawn, np.floor(u * (LEVELS - 1) + 0.5) + 1, 0).astype(np.int64)
    return np.stack([(n >> 16) & 255, (n >> 8) & 255, n & 255], axis=-1).astype(np.uint8)


def unpack(rgb: np.ndarray) -> np.ndarray:
    """The distances (metres, float32; ``inf`` where nothing was drawn) of packed depth pixels ``(..., 3+)``."""
    c = np.asarray(rgb)[..., :3].astype(np.int64)
    n = (c[..., 0] << 16) | (c[..., 1] << 8) | c[..., 2]
    log2z = (n - 1) / (LEVELS - 1) * LOG_SPAN + LOG_MIN
    return np.where(n > 0, np.exp2(log2z), np.inf).astype(np.float32)


def _histogram_edges() -> np.ndarray:
    return np.linspace(LOG_MIN, LOG_MIN + LOG_SPAN, int(LOG_SPAN * BINS_PER_OCTAVE) + 1)


def shot_near(frames: Iterator[np.ndarray]) -> float | None:
    """The ``near`` of a shot's depth frames (metres, :data:`NEAR_SHARE`); ``None`` when nothing was drawn."""
    edges = _histogram_edges()
    counts = np.zeros(len(edges) - 1, dtype=np.int64)
    for z in frames:
        drawn = z[np.isfinite(z)]
        if drawn.size:
            counts += np.histogram(np.log2(np.maximum(drawn, 2.0 ** LOG_MIN)), bins=edges)[0]
    total = int(counts.sum())
    if total == 0:
        return None
    k = int(np.searchsorted(np.cumsum(counts), NEAR_SHARE * total))
    return float(2.0 ** edges[min(k + 1, len(edges) - 1)])


def depth_grey(z: np.ndarray, near: float) -> np.ndarray:
    """Grey bytes of distances ``z``: ``255 near / z`` clipped (near white, far dark, ``inf`` black)."""
    with np.errstate(divide="ignore"):
        v = np.clip(near / np.asarray(z, dtype=np.float64), 0.0, 1.0)
    return np.round(v * 255).astype(np.uint8)


def _decoded(ffmpeg: str, source: Path, start: float, length: float, size: tuple[int, int]) -> Iterator[np.ndarray]:
    """The distances of the frames of ``source`` from ``start`` for ``length`` seconds (as ``cut_video`` cuts them)."""
    width, height = size
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-ss", f"{start:.6f}", "-i", str(source), "-t", f"{length:.6f}",
           "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        assert proc.stdout is not None and proc.stderr is not None
        frame_bytes = width * height * 3
        while chunk := proc.stdout.read(frame_bytes):
            if len(chunk) < frame_bytes:
                break
            yield unpack(np.frombuffer(chunk, dtype=np.uint8).reshape(height, width, 3))
        errors = proc.stderr.read().decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise VidgenError(f"ffmpeg failed while reading the depth pass {source.name}:\n{errors[-2000:]}")


def cut_depth(ffmpeg: str, source: Path, dest: Path, start: float, length: float, encode_args: list[str]) -> float | None:
    """``dest``: the grey guide (:func:`depth_grey`) of the packed depth pass ``source`` from ``start`` for
    ``length`` seconds, one ``near`` for all its frames (:func:`shot_near`), encoded with ``encode_args``
    (ffmpeg output options before ``dest``), silent. Returns ``near`` (``None``: nothing drawn, all black)."""
    from vidgen.render.ffmpeg import probe

    info = probe(source)
    size = (info.width, info.height)
    near = shot_near(_decoded(ffmpeg, source, start, length, size))
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-hide_banner", "-nostdin", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{size[0]}x{size[1]}",
           "-framerate", str(info.fps), "-i", "pipe:0", "-an", *encode_args, str(dest)]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        assert proc.stdin is not None and proc.stderr is not None
        try:
            for z in _decoded(ffmpeg, source, start, length, size):
                proc.stdin.write(depth_grey(z, near if near is not None else 1.0).tobytes())
        finally:
            proc.stdin.close()
        errors = proc.stderr.read().decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise VidgenError(f"ffmpeg failed while writing the depth guide {dest.name}:\n{errors[-2000:]}")
    return near


__all__ = ["BINS_PER_OCTAVE", "LEVELS", "LOG_MIN", "LOG_SPAN", "NEAR_SHARE", "WEB_GUIDE_PASSES", "cut_depth", "depth_grey", "pack",
           "shot_near", "unpack"]
