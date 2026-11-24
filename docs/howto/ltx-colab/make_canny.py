"""Canny edges of a colour clip, as a control video for the IC-LoRA (white edges on black).

Run on the Colab VM (it has OpenCV):
  colab exec -s ltx -f make_canny.py --env SRC=/content/render_121_960x512.mp4 \
      --env DST=/content/canny_121_960x512.mp4
or locally with OpenCV and ffmpeg installed:  python make_canny.py SRC DST [LOW HIGH]
LOW / HIGH default to 92 / 200, the thresholds of the official workflow's CannyEdgePreprocessor
(at 512 px tall, which the 960x512 clip already is). A sun-glint sea gives many edges that the
model reads as surf: blur first, raise the thresholds or mask the glint (untested).
"""
import os
import subprocess
import sys

import cv2
import numpy as np


def main() -> None:
    """Read SRC frame by frame, write the edges to DST as H.264 at the same size and rate."""
    args = sys.argv[1:] if len(sys.argv) > 2 and not sys.argv[1].startswith("-") else []
    src = args[0] if args else os.environ["SRC"]
    dst = args[1] if args else os.environ["DST"]
    low = int(args[2]) if len(args) > 2 else int(os.environ.get("LOW", 92))
    high = int(args[3]) if len(args) > 3 else int(os.environ.get("HIGH", 200))
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        e = cv2.Canny(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), low, high)
        frames.append(np.dstack([e, e, e]))
    cap.release()
    if not frames:
        raise SystemExit(f"no frames read from {src}")
    h, w = frames[0].shape[:2]
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                           "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-", "-c:v", "libx264",
                           "-crf", "12", "-pix_fmt", "yuv420p", dst], stdin=subprocess.PIPE)
    for f in frames:
        ff.stdin.write(f.tobytes())
    ff.stdin.close()
    if ff.wait():
        raise SystemExit("ffmpeg failed")
    mid = frames[len(frames) // 2]
    print("canny frames", len(frames), f"{w}x{h}", "edge fraction (middle frame)",
          round(float((mid[..., 0] > 0).mean()), 4))


main()
