"""Prepare the image-model inputs from frame 0 (run on the Colab VM; OpenCV is there).

  colab exec -s ltx -f prep_image_inputs.py
Env (defaults): FF=/content/first_frame_960x512.png, DEPTH=/content/depth_121_960x512.mp4,
W=1440, H=768 (1.5x, same 15:8 aspect, multiples of 16), OUT=/content/ComfyUI/input.
Writes ff_up.png (frame 0, Lanczos), ff_canny.png (blurred canny, glint suppressed, same as
make_canny_soft.py defaults), ff_depth.png (frame 0 of the depth pass), all W x H.
"""
import os

import cv2
import numpy as np

ff, depth = os.environ.get("FF", "/content/first_frame_960x512.png"), os.environ.get(
    "DEPTH", "/content/depth_121_960x512.mp4")
w, h = int(os.environ.get("W", 1440)), int(os.environ.get("H", 768))
out = os.environ.get("OUT", "/content/ComfyUI/input")
img = cv2.imread(ff)
up = cv2.resize(img, (w, h), interpolation=cv2.INTER_LANCZOS4)
cv2.imwrite(f"{out}/ff_up.png", up)
g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
e = cv2.Canny(cv2.GaussianBlur(g, (5, 5), 0), 92, 200).astype(np.float32)
keep = cv2.GaussianBlur((cv2.GaussianBlur(g, (41, 41), 0) <= 150).astype(np.float32), (31, 31), 0)
e = cv2.resize(np.clip(e * keep, 0, 255).astype(np.uint8), (w, h), interpolation=cv2.INTER_LINEAR)
cv2.imwrite(f"{out}/ff_canny.png", e)
cap = cv2.VideoCapture(depth)
ok, d = cap.read()
cap.release()
cv2.imwrite(f"{out}/ff_depth.png", cv2.resize(d, (w, h), interpolation=cv2.INTER_LINEAR))
print("wrote ff_up.png ff_canny.png ff_depth.png", w, "x", h, "edge fraction",
      round(float((e > 127).mean()), 4))
