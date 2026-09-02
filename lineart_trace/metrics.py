"""How close is the trace to the drawing it came from?

`compare` answers with numbers rather than adjectives:

* **coverage** -- of the original ink, what fraction the trace paints. Low
  means dropped or truncated strokes.
* **spill**    -- of the paint the trace lays down, what fraction lands on
  blank paper. High means fattened strokes or spurious lines.
* **iou**      -- the two together, in one number.
* **d95 / dmax** -- how far, in pixels, the worst-placed original ink is from
  anything the trace drew. This is the one that catches a whole stroke going
  missing, which an area measure can hide.
"""
from typing import Dict

import cv2
import numpy as np

__all__ = ["compare", "coverage", "distance_stats"]


def _m(a):
    return (np.asarray(a) > 0).astype(np.uint8)


def coverage(target: np.ndarray, render: np.ndarray,
             slack: int = 1) -> Dict[str, float]:
    """Overlap of two masks, allowing `slack` pixels of registration error."""
    t, r = _m(target), _m(render)
    if slack > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                      (2 * slack + 1, 2 * slack + 1))
        t_d, r_d = cv2.dilate(t, k), cv2.dilate(r, k)
    else:
        t_d, r_d = t, r
    tn, rn = float(t.sum()), float(r.sum())
    hit_t = float((t & r_d).sum())
    hit_r = float((r & t_d).sum())
    inter = float((t & r).sum())
    union = float((t | r).sum())
    return {
        "coverage": hit_t / tn if tn else 1.0,
        "spill": 1.0 - (hit_r / rn) if rn else 0.0,
        "iou": inter / union if union else 1.0,
        "target_px": tn,
        "render_px": rn,
    }


def distance_stats(target: np.ndarray, render: np.ndarray) -> Dict[str, float]:
    """Distance from each ink pixel of `target` to the nearest `render` ink."""
    t, r = _m(target), _m(render)
    if t.sum() == 0:
        return {"d95": 0.0, "dmax": 0.0, "dmean": 0.0}
    if r.sum() == 0:
        big = float(max(t.shape))
        return {"d95": big, "dmax": big, "dmean": big}
    d = cv2.distanceTransform(1 - r, cv2.DIST_L2, 5)[t > 0]
    return {"d95": float(np.percentile(d, 95)), "dmax": float(d.max()),
            "dmean": float(d.mean())}


def compare(target: np.ndarray, render: np.ndarray, slack: int = 1
            ) -> Dict[str, float]:
    """All of the above, plus the f1 of coverage and 1 - spill."""
    out = coverage(target, render, slack)
    out.update(distance_stats(target, render))
    c, p = out["coverage"], 1.0 - out["spill"]
    out["f1"] = 2 * c * p / (c + p) if (c + p) else 0.0
    return out
