"""Make the short video clip used by ``examples/gallery`` (``assets/clip.webm``) with ffmpeg.

Not shipped with vidgen; a maintainer tool. The picture is ffmpeg's own ``testsrc2`` test
pattern (colour bars, a moving gradient band and a frame counter; generated, so free of any
licence), the sound a quiet two-note chord, encoded as VP9 + Opus in WebM so the file stays
small (~150 KB). Run from the repository root::

    python tools/make_clip.py [--out examples/gallery/assets/clip.webm]

Regions the example's callouts point at (fractions of 480 x 270, ``[x, y, w, h]`` from the top
left): the time code and frame counter ``[0.0, 0.0, 0.21, 0.14]``, the cyan colour bar
``[0.835, 0.0, 0.165, 1.0]`` (its middle ``[0.92, 0.45]``). The gradient band and the squares move.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECONDS = 6
SIZE = "480x270"
FPS = 15


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "gallery" / "assets" / "clip.webm")
    args = parser.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        sys.exit("ffmpeg not found on PATH")
    chord = f"aevalsrc=0.05*sin(2*PI*220*t)+0.04*sin(2*PI*330*t):s=48000:d={SECONDS}"
    command = [
        ffmpeg, "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=s={SIZE}:r={FPS}:d={SECONDS}",
        "-f", "lavfi", "-i", chord,
        "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "42", "-row-mt", "0", "-threads", "1", "-pix_fmt", "yuv420p",
        "-c:a", "libopus", "-b:a", "24k", "-ac", "1",
        "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
        "-shortest", str(args.out),
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
