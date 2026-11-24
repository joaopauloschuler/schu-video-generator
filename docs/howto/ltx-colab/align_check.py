"""Alignment check of photoreal candidates against frame 0 (run on the VM, or locally with OpenCV).

  colab exec -s ltx -f align_check.py --env REF=/content/first_frame_960x512.png \
      --env CANDS="/content/cand_a.png /content/cand_b.png" --env OUT=/content/align
For each candidate (resized to REF's size): Canny (blur 5, 50/150) of both, then
- an overlay PNG: REF edges red, candidate edges green, both yellow, over a dark REF;
- an edge F-score with a 3 px tolerance (distance transform), in all the frame and in the
  glider box (x0,y0,x1,y1 for the 960x512 glider shot; GLIDER env to change it). The sea's texture
  counts too, so a candidate that (rightly) replaces a CG sea scores lower: read the overlay;
- the horizon row: the row of the largest sky-to-sea drop in mean luma, over the left half
  of the frame (away from the sun) inside the HORIZON band (rows y0,y1), REF vs candidate.
  Haze added by the model softens the step and moves it a few rows down.
Prints one line per candidate and writes OUT/align.json.
"""
import json
import os

import cv2
import numpy as np


def edge(img: np.ndarray) -> np.ndarray:
    """Binary edges of a BGR image."""
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    return cv2.Canny(g, 50, 150) > 0


def fscore(a: np.ndarray, b: np.ndarray, tol: float = 3.0) -> float:
    """Symmetric edge F-score of two binary maps with a tolerance in pixels."""
    if a.sum() == 0 or b.sum() == 0:
        return 0.0
    da = cv2.distanceTransform((~a).astype(np.uint8), cv2.DIST_L2, 3)
    db = cv2.distanceTransform((~b).astype(np.uint8), cv2.DIST_L2, 3)
    prec = float((da[b] <= tol).mean())
    rec = float((db[a] <= tol).mean())
    return 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)


def horizon_row(img: np.ndarray, y0: int, y1: int) -> int:
    """Row of the largest drop in mean luma (bright sky to darker sea), left half, y0..y1."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    prof = g[y0:y1, : g.shape[1] // 2].mean(axis=1)
    return int(y0 + np.argmax(-np.diff(prof)))


def crop(m: np.ndarray, b: tuple[int, int, int, int]) -> np.ndarray:
    """The part of m inside the box x0,y0,x1,y1."""
    return m[b[1]:b[3], b[0]:b[2]]


def box(spec: str) -> tuple[int, int, int, int]:
    """Parse x0,y0,x1,y1."""
    x0, y0, x1, y1 = (int(v) for v in spec.split(","))
    return x0, y0, x1, y1


ref = cv2.imread(os.environ["REF"])
h, w = ref.shape[:2]
out = os.environ.get("OUT", "/content/align")
os.makedirs(out, exist_ok=True)
gb = box(os.environ.get("GLIDER", "300,240,660,420"))
y0, y1 = (int(v) for v in os.environ.get("HORIZON", "60,160").split(","))
er = edge(ref)
res = []
for path in os.environ["CANDS"].split():
    c = cv2.resize(cv2.imread(path), (w, h), interpolation=cv2.INTER_AREA)
    ec = edge(c)
    ov = (ref * 0.3).astype(np.uint8)
    ov[er & ~ec] = (0, 0, 255)
    ov[ec & ~er] = (0, 255, 0)
    ov[er & ec] = (0, 255, 255)
    name = os.path.splitext(os.path.basename(path))[0]
    cv2.imwrite(f"{out}/{name}_overlay.png", ov)
    r = {"cand": name, "f_all": round(fscore(er, ec), 3),
         "f_glider": round(fscore(crop(er, gb), crop(ec, gb)), 3),
         "horizon_ref": horizon_row(ref, y0, y1), "horizon_cand": horizon_row(c, y0, y1)}
    res.append(r)
    print(r)
json.dump(res, open(f"{out}/align.json", "w"), indent=1)
