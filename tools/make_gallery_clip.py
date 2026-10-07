"""Make the screen-recording-like clip the scene gallery shows for ``video_clip``
(``src/vidgen/data/gallery/clip.webm``) with ffmpeg.

Not shipped with vidgen; a maintainer tool. The picture is the gallery's sample app screenshot
(``data/gallery/app.png``, made by ``tools/make_screenshot.py``) with a slow camera move from the
whole window in on the "Tasks completed" chart, as a screen recording zooming in would look;
silent, VP9 in WebM (~100 KB). Run from the repository root::

    python tools/make_gallery_clip.py [--out src/vidgen/data/gallery/clip.webm]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "src" / "vidgen" / "data" / "gallery"
SECONDS = 6
FPS = 15
SIZE = (640, 400)
#: Where the move ends: the zoom and the middle of the view (fractions of the picture).
ZOOM = 1.8
TARGET = (0.36, 0.62)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=GALLERY / "clip.webm")
    args = parser.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        sys.exit("ffmpeg not found on PATH")
    frames = SECONDS * FPS
    # eased progress 0..1 over the clip (smoothstep), the zoom and the view's middle follow it
    ease = f"(3*pow(on/{frames - 1},2)-2*pow(on/{frames - 1},3))"
    zoom = f"1+{ZOOM - 1}*{ease}"
    cx = f"(0.5+({TARGET[0]}-0.5)*{ease})*iw"
    cy = f"(0.5+({TARGET[1]}-0.5)*{ease})*ih"
    move = f"zoompan=z='{zoom}':x='{cx}-iw/zoom/2':y='{cy}-ih/zoom/2':d={frames}:s={SIZE[0]}x{SIZE[1]}:fps={FPS}"
    command = [
        ffmpeg, "-y", "-v", "error",
        "-i", str(GALLERY / "app.png"),
        "-vf", f"scale={SIZE[0] * 3}:-1:flags=lanczos,{move}",
        "-frames:v", str(frames),
        "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40", "-row-mt", "0", "-threads", "1", "-pix_fmt", "yuv420p",
        "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact",
        str(args.out),
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
