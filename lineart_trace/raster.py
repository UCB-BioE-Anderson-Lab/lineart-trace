"""Draw a TraceResult back to a raster mask.

Round-tripping is how this project knows whether a trace is any good: render
the vector output at the input's resolution and compare it, pixel for pixel,
with the ink it came from. Every quality claim in the README is a number out
of `metrics.compare` on top of this.
"""
from typing import List, Optional, Sequence

import cv2
import numpy as np

__all__ = ["flatten_cubic", "flatten_path", "rasterize"]


def flatten_cubic(c, tol: float = 0.2) -> np.ndarray:
    """Sample one cubic densely enough that the polyline is within `tol`."""
    p0, p1, p2, p3 = (np.asarray(p, float) for p in c)
    chord = np.linalg.norm(p3 - p0)
    net = (np.linalg.norm(p1 - p0) + np.linalg.norm(p2 - p1)
           + np.linalg.norm(p3 - p2))
    n = int(np.clip(np.sqrt(max(net, chord) / max(tol, 1e-3)) * 2, 4, 200))
    t = np.linspace(0.0, 1.0, n).reshape(-1, 1)
    mt = 1.0 - t
    return (mt ** 3 * p0 + 3 * mt ** 2 * t * p1
            + 3 * mt * t ** 2 * p2 + t ** 3 * p3)


def flatten_path(curves, tol: float = 0.2) -> np.ndarray:
    """Sample a run of cubics into one polyline of (x, y) points."""
    if not curves:
        return np.zeros((0, 2))
    out = [flatten_cubic(curves[0], tol)]
    for c in curves[1:]:
        out.append(flatten_cubic(c, tol)[1:])
    return np.vstack(out)


def rasterize(result, size: Optional[Sequence[int]] = None,
              supersample: int = 2, width: Optional[float] = None,
              tol: float = 0.2) -> np.ndarray:
    """Render a TraceResult to a 0/1 mask the size of the source image.

    `supersample` renders large and averages down, so a half-pixel of stroke
    weight is not lost to rounding; the result is thresholded back to a mask.
    """
    W, H = size if size is not None else result.size
    s = max(1, int(supersample))
    canvas = np.zeros((H * s, W * s), np.uint8)

    for f in result.fills:
        loops = [np.round(flatten_path(l, tol) * s).astype(np.int32)
                 for l in f.loops]
        loops = [l for l in loops if len(l) >= 3]
        if not loops:
            continue
        cv2.fillPoly(canvas, loops[:1], 1)
        if len(loops) > 1:
            cv2.fillPoly(canvas, loops[1:], 0)

    for st in result.strokes:
        pts = flatten_path(st.curves, tol)
        if len(pts) < 2:
            continue
        w = width if width is not None else st.width
        t = max(1, int(round(w * s)))
        cv2.polylines(canvas, [np.round(pts * s).astype(np.int32)],
                      bool(st.closed), 1, t, cv2.LINE_8)

    if s == 1:
        return canvas
    small = cv2.resize(canvas.astype(np.float32), (W, H),
                       interpolation=cv2.INTER_AREA)
    return (small > 0.5).astype(np.uint8)
