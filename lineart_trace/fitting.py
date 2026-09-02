"""Point chains -> cubic Bezier segments (Schneider, Graphics Gems 1990).

Three departures from the textbook algorithm, all of them things line art
needs:

* **Reparameterisation.** Schneider's Newton-Raphson step re-fits the
  chord-length parameters to the current curve before giving up and splitting.
  Without it the fitter splits far too eagerly and a smooth arc comes out as a
  dozen segments with visible kinks.
* **Corner detection.** Least squares rounds off sharp corners, so a square
  traces with soft edges. High-curvature points are found first and the chain
  is cut there, letting each side keep its own tangent.
* **Closed chains** get a seam tangent averaged across the join, so a circle
  does not show a crease where the walk started.
"""
from typing import List, Optional, Sequence

import numpy as np

__all__ = ["fit_curve", "corner_indices", "smooth_chain", "Cubic"]

Cubic = List[np.ndarray]          # [p0, c1, c2, p3]


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else np.asarray(v, float)


def _at(c, t):
    mt = 1.0 - t
    return ((mt ** 3) * c[0] + 3 * (mt ** 2) * t * c[1]
            + 3 * mt * (t ** 2) * c[2] + (t ** 3) * c[3])


def _d1(c, t):
    mt = 1.0 - t
    return (3 * mt ** 2 * (c[1] - c[0]) + 6 * mt * t * (c[2] - c[1])
            + 3 * t ** 2 * (c[3] - c[2]))


def _d2(c, t):
    mt = 1.0 - t
    return 6 * mt * (c[2] - 2 * c[1] + c[0]) + 6 * t * (c[3] - 2 * c[2] + c[1])


# --------------------------------------------------------------- smoothing
def smooth_chain(pts: np.ndarray, window: int = 5,
                 keep: Optional[Sequence[int]] = None) -> np.ndarray:
    """Moving-average a pixel chain, holding the ends and `keep` indices fixed.

    Skeleton chains are staircases: every point carries up to half a pixel of
    quantisation noise, which the fitter would otherwise chase with extra
    segments. Corners are pinned so smoothing cannot round them off.
    """
    pts = np.asarray(pts, float)
    n = len(pts)
    if n < 3 or window < 3:
        return pts
    w = min(window, n if n % 2 else n - 1)
    if w % 2 == 0:
        w -= 1
    if w < 3:
        return pts
    r = w // 2
    pad = np.vstack([np.repeat(pts[:1], r, 0), pts, np.repeat(pts[-1:], r, 0)])
    ker = np.ones(w) / w
    out = np.stack([np.convolve(pad[:, k], ker, "valid") for k in range(2)], 1)
    pin = {0, n - 1} | set(keep or ())
    for i in pin:
        if 0 <= i < n:
            out[i] = pts[i]
    return out


# -------------------------------------------------------------- corners
def corner_indices(pts: np.ndarray, angle: float = 75.0,
                   span: float = 4.0) -> List[int]:
    """Indices where the chain turns by more than `angle` degrees.

    The turn is measured across a `span`-pixel arm on each side rather than
    between adjacent pixels, so staircase jitter does not register as a corner
    and a genuine corner is not diluted by the pixels next to it.
    """
    pts = np.asarray(pts, float)
    n = len(pts)
    if n < 5:
        return []
    step = np.hypot(*(pts[1:] - pts[:-1]).T)
    s = np.concatenate([[0.0], np.cumsum(step)])
    if s[-1] < 2 * span:
        return []
    cos_lim = np.cos(np.radians(180.0 - angle))
    score = np.full(n, 1.0)
    for i in range(1, n - 1):
        lo = np.searchsorted(s, s[i] - span)
        hi = np.searchsorted(s, s[i] + span)
        lo, hi = min(lo, i - 1), max(min(hi, n - 1), i + 1)
        a = _unit(pts[lo] - pts[i])
        b = _unit(pts[hi] - pts[i])
        score[i] = float(a @ b)          # -1 straight through, 0 right angle
    out = []
    i = 1
    while i < n - 1:
        if score[i] > cos_lim:
            j = i
            while j + 1 < n - 1 and score[j + 1] > cos_lim:
                j += 1
            out.append(int(i + np.argmax(score[i:j + 1])))   # sharpest of run
            i = j + 1
        else:
            i += 1
    return out


# ------------------------------------------------------------------ fit
def _chord_params(pts):
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*(pts[1:] - pts[:-1]).T))])
    return d / d[-1] if d[-1] > 0 else np.linspace(0, 1, len(pts))


def _solve(pts, u, t1, t2):
    """Least squares for the two interior control points."""
    p0, p3 = pts[0], pts[-1]
    a0 = np.outer(3 * (1 - u) ** 2 * u, t1)
    a1 = np.outer(3 * (1 - u) * u ** 2, t2)
    mt = 1 - u
    base = (np.outer(mt ** 3 + 3 * mt ** 2 * u, p0)
            + np.outer(3 * mt * u ** 2 + u ** 3, p3))
    d = pts - base
    c00 = float((a0 * a0).sum())
    c01 = float((a0 * a1).sum())
    c11 = float((a1 * a1).sum())
    x0 = float((a0 * d).sum())
    x1 = float((a1 * d).sum())
    det = c00 * c11 - c01 * c01
    seg = float(np.linalg.norm(p3 - p0))
    if abs(det) < 1e-12:
        al = ar = seg / 3.0
    else:
        al = (x0 * c11 - c01 * x1) / det
        ar = (c00 * x1 - x0 * c01) / det
        # The solve is unstable on near-degenerate runs and will fling a
        # control point far outside the data, drawing as a long spurious line.
        lim = max(seg * 1.5, 1e-6)
        if not (1e-6 < al < lim and 1e-6 < ar < lim):
            al = ar = seg / 3.0
    return [p0, p0 + t1 * al, p3 + t2 * ar, p3]


def _reparam(pts, c, u):
    """One Newton-Raphson pass pulling each parameter onto its closest point."""
    t = u.reshape(-1, 1)
    d = _at(c, t) - pts
    d1 = _d1(c, t)
    den = (d1 * d1).sum(1) + (d * _d2(c, t)).sum(1)
    step = np.where(np.abs(den) > 1e-12, (d * d1).sum(1) / np.where(den, den, 1),
                    0.0)
    out = u - step
    out[0], out[-1] = 0.0, 1.0
    return np.clip(out, 0.0, 1.0)


def _max_error(pts, c, u):
    e = np.linalg.norm(np.array([_at(c, ui) for ui in u]) - pts, axis=1)
    if len(e) < 3:
        return 0.0, len(pts) // 2
    k = int(np.argmax(e[1:-1])) + 1
    return float(e[k]), k


def _fit(pts, t1, t2, error, depth):
    if len(pts) < 3:
        d = float(np.linalg.norm(pts[-1] - pts[0])) / 3.0
        return [[pts[0], pts[0] + t1 * d, pts[-1] + t2 * d, pts[-1]]]
    u = _chord_params(pts)
    c = _solve(pts, u, t1, t2)
    err, split = _max_error(pts, c, u)
    if err < error:
        return [c]
    if err < error * 4.0:
        for _ in range(6):                       # Schneider's reparameterise
            u = _reparam(pts, c, u)
            c = _solve(pts, u, t1, t2)
            err, split = _max_error(pts, c, u)
            if err < error:
                return [c]
    if depth >= 20 or split <= 0 or split >= len(pts) - 1:
        return [c]
    tc = _unit(pts[split - 1] - pts[split + 1])
    return (_fit(pts[:split + 1], t1, tc, error, depth + 1)
            + _fit(pts[split:], -tc, t2, error, depth + 1))


def fit_curve(pts, error: float = 1.0, closed: bool = False,
              corner_angle: float = 75.0, smooth: int = 5) -> List[Cubic]:
    """Fit an ordered chain of (x, y) points with cubic Beziers.

    `error` is the maximum deviation in input pixels. Corners sharper than
    `corner_angle` degrees become segment boundaries instead of being smoothed
    over; pass 0 to disable corner detection.
    """
    pts = np.asarray(pts, float)
    if len(pts) < 2:
        return []
    if closed and len(pts) > 2 and not np.allclose(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[:1]])

    corners = corner_indices(pts, corner_angle) if corner_angle > 0 else []
    if closed and len(pts) > 3:
        # Detect a corner sitting ON the seam by looking across the join, then
        # rotate the chain to start there. Otherwise the seam either splits a
        # smooth curve or hides a real corner in the wrap-around.
        n = len(pts) - 1
        span = int(min(n // 2, 12))
        if span >= 2:
            wrapped = np.vstack([pts[n - span:n], pts[:span + 1]])
            if any(abs(i - span) <= 1 for i in
                   corner_indices(wrapped, corner_angle)):
                corners = sorted(set(corners) | {0})
        if corners and corners[0] != 0:
            k = corners[0]
            pts = np.vstack([pts[k:n], pts[:k + 1]])
            corners = sorted((i - k) % n for i in corners if i != k)
            corners = [i for i in corners if 0 < i < len(pts) - 1]

    cuts = sorted({0, len(pts) - 1} |
                  {i for i in corners if 0 < i < len(pts) - 1})
    seam_free = closed and len(cuts) == 2
    out: List[Cubic] = []
    for k in range(len(cuts) - 1):
        seg = pts[cuts[k]:cuts[k + 1] + 1]
        if len(seg) < 2:
            continue
        # Smooth each corner-delimited piece on its own, ends pinned: a shared
        # pass would bleed the corner into the straight run beside it and the
        # fitter would then split that run to chase the bend.
        if smooth:
            seg = smooth_chain(seg, smooth)
        if seam_free and len(seg) > 3:
            t = _unit(seg[1] - seg[-2])      # average across the join
            t1, t2 = t, -t
        else:
            t1 = _unit(seg[1] - seg[0])
            t2 = _unit(seg[-2] - seg[-1])
        out.extend(_fit(seg, t1, t2, error, 0))
    return out
