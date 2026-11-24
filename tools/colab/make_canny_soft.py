"""Canny edges with the sun glint suppressed, as a control video (white edges on black).

Run on the Colab VM (OpenCV):
  colab exec -s ltx -f make_canny_soft.py --env SRC=/content/render_121_960x512.mp4 \
      --env DST=/content/cannysoft_121_960x512.mp4
Env (defaults): BLUR=5 (Gaussian kernel before Canny, odd; 0 = none), LOW=92, HIGH=200 (the
official thresholds), GLINT=150 (edges are removed where the frame, blurred over 41 px, is brighter
than this 0-255 luma: the sun-glint area), FEATHER=31 (soften the mask edge).
Also writes DST with .png -> the middle frame, for a look.
"""
import os
import subprocess

import cv2
import numpy as np


def edges(frame: np.ndarray, blur: int, low: int, high: int, glint: int, feather: int) -> np.ndarray:
    """Return the glint-suppressed edge map (uint8, 0 or 255 scaled by the mask) of a BGR frame."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    src = cv2.GaussianBlur(g, (blur, blur), 0) if blur > 1 else g
    e = cv2.Canny(src, low, high).astype(np.float32)
    if glint < 255:
        bright = cv2.GaussianBlur(g, (41, 41), 0).astype(np.float32)
        keep = (bright <= glint).astype(np.float32)
        if feather > 1:
            keep = cv2.GaussianBlur(keep, (feather, feather), 0)
        e *= keep
    return np.clip(e, 0, 255).astype(np.uint8)


def main() -> None:
    """Read SRC frame by frame and write the edges to DST as H.264 at the same size and rate."""
    src, dst = os.environ["SRC"], os.environ["DST"]
    blur = int(os.environ.get("BLUR", 5))
    low, high = int(os.environ.get("LOW", 92)), int(os.environ.get("HIGH", 200))
    glint, feather = int(os.environ.get("GLINT", 150)), int(os.environ.get("FEATHER", 31))
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        e = edges(f, blur, low, high, glint, feather)
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
    cv2.imwrite(os.path.splitext(dst)[0] + ".png", mid)
    print("canny-soft frames", len(frames), f"{w}x{h}", "edge fraction (middle frame)",
          round(float((mid[..., 0] > 127).mean()), 4))


main()
