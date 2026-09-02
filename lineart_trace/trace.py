"""Centreline vectorisation of black-on-white line art.

    binarize -> Zhang-Suen thinning -> skeleton graph walk -> Schneider
    cubic Bezier fitting -> open stroked SVG paths

Unlike an outline tracer (potrace, cv2.findContours), this recovers the
*centreline* of each stroke, so the result is real lines you can restyle:
change weight, colour, dash, or animate. Stroke width is recovered from the
distance transform so traced art keeps the weight it was drawn at.
"""
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

import cv2
import numpy as np

Point = Tuple[float, float]
Cubic = List[np.ndarray]          # [p0, c1, c2, p3]

NB8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


# --------------------------------------------------------------- thinning
def skeletonize(mask: np.ndarray) -> np.ndarray:
    """Zhang-Suen thinning to a 1px-wide skeleton. `mask` is 0/1 uint8."""
    img = (mask > 0).astype(np.uint8).copy()

    def nb(im):
        P = np.pad(im, 1)
        return (P[0:-2, 1:-1], P[0:-2, 2:], P[1:-1, 2:], P[2:, 2:],
                P[2:, 1:-1], P[2:, 0:-2], P[1:-1, 0:-2], P[0:-2, 0:-2])

    while True:
        removed = False
        for step in (0, 1):
            P2, P3, P4, P5, P6, P7, P8, P9 = nb(img)
            B = (P2 + P3 + P4 + P5 + P6 + P7 + P8 + P9).astype(np.int16)
            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int16)
                    for i in range(8))
            if step == 0:
                c1, c2 = P2 * P4 * P6, P4 * P6 * P8
            else:
                c1, c2 = P2 * P4 * P8, P2 * P6 * P8
            kill = ((img == 1) & (B >= 2) & (B <= 6) & (A == 1)
                    & (c1 == 0) & (c2 == 0))
            if kill.any():
                img[kill] = 0
                removed = True
        if not removed:
            return img


# ------------------------------------------------------------- graph walk
def skeleton_chains(skel: np.ndarray, prune: float = 14.0) -> List[List[Tuple[int, int]]]:
    """Walk the skeleton into ordered pixel chains, split at endpoints and
    junctions. Closed loops carrying no node are emitted whole."""
    H, W = skel.shape
    # Classify by CROSSING NUMBER, not raw 8-neighbour count. On a diagonal
    # staircase an ordinary interior pixel has three 8-neighbours, so a plain
    # neighbour count reports false branch points and shatters every curve
    # into fragments. The crossing number (0->1 transitions around the ring)
    # is 1 at an endpoint, 2 on a line, >=3 at a true branch.
    deg = crossing_number(skel)
    pix = {(y, x) for y, x in zip(*np.nonzero(skel))}
    nodes = {p for p in pix if deg[p] != 2}
    used = set()

    def neighbours(p):
        y, x = p
        return [(y + dy, x + dx) for dy, dx in NB8
                if 0 <= y + dy < H and 0 <= x + dx < W and skel[y + dy, x + dx]]

    def step_from(cur, prev):
        """Next pixel along the line. Diagonal links that merely short-cut a
        4-connected pair are skipped, and 4-connected steps win ties."""
        cand = [q for q in neighbours(cur) if q != prev]
        if prev is not None:
            cand = [q for q in cand
                    if max(abs(q[0]-prev[0]), abs(q[1]-prev[1])) > 1] or cand
        cand.sort(key=lambda q: (abs(q[0]-cur[0]) + abs(q[1]-cur[1])))
        return cand[0] if cand else None

    def walk(start, first):
        chain = [start, first]
        used.add(frozenset((start, first)))
        cur, prev = first, start
        while deg[cur] == 2:
            q = step_from(cur, prev)
            if q is None or frozenset((cur, q)) in used:
                break
            used.add(frozenset((cur, q)))
            chain.append(q)
            prev, cur = cur, q
        return chain

    chains = []
    for n in nodes:
        for q in neighbours(n):
            if frozenset((n, q)) not in used:
                chains.append(walk(n, q))
    for p in pix:                                    # leftover closed loops
        if deg[p] == 2 and not any(frozenset((p, q)) in used
                                   for q in neighbours(p)):
            c = walk(p, step_from(p, None))
            if len(c) > 2:
                c.append(c[0])
            chains.append(c)

    out = []
    for c in chains:
        if len(c) < 2:
            continue
        L = chain_length(c)
        if L < 3.0:                                  # genuine speckle
            continue
        # A short chain with a FREE end is a thinning spur. A short chain
        # running junction-to-junction is structural — the piece of a line
        # between two crossings — and must be kept or every crossing punches
        # a gap in the drawing.
        free = sum(1 for e in (c[0], c[-1]) if deg[e] == 1)
        if free and L < prune:
            continue
        out.append(c)
    return merge_chains(out)


def crossing_number(skel: np.ndarray) -> np.ndarray:
    """0->1 transitions around each pixel's 8-neighbourhood, masked to the
    skeleton. 1 = endpoint, 2 = on a line, >=3 = branch point."""
    P = np.pad(skel, 1).astype(np.int16)
    ring = [P[0:-2, 1:-1], P[0:-2, 2:], P[1:-1, 2:], P[2:, 2:],
            P[2:, 1:-1], P[2:, 0:-2], P[1:-1, 0:-2], P[0:-2, 0:-2]]
    ring = ring + [ring[0]]
    A = sum(((ring[i] == 0) & (ring[i + 1] == 1)).astype(np.int32)
            for i in range(8))
    return A * skel


def merge_chains(chains):
    """Splice chains that meet end-to-end at a point where only TWO chain
    ends arrive. Thinning leaves the odd spurious branch pixel on a smooth
    curve; without this they stay as separate strokes and the curve renders
    with visible seams. Genuine junctions (3+ arriving ends) are untouched."""
    from collections import defaultdict
    chains = [list(c) for c in chains]
    while True:
        ends = defaultdict(list)
        for i, c in enumerate(chains):
            if len(c) < 2 or c[0] == c[-1]:
                continue
            ends[c[0]].append((i, 0))
            ends[c[-1]].append((i, 1))
        for _, lst in ends.items():
            if len(lst) != 2:
                continue
            (i, ei), (j, ej) = lst
            if i == j:
                continue
            a, b = chains[i], chains[j]
            if ei == 1 and ej == 0:   merged = a + b[1:]
            elif ei == 1 and ej == 1: merged = a + b[-2::-1]
            elif ei == 0 and ej == 0: merged = a[::-1] + b[1:]
            else:                     merged = b + a[1:]
            chains[i], chains[j] = merged, []
            break
        else:
            return [c for c in chains if len(c) >= 2]


def chain_length(chain: Sequence[Tuple[int, int]]) -> float:
    a = np.asarray(chain, float)
    return float(np.hypot(*(a[1:] - a[:-1]).T).sum()) if len(a) > 1 else 0.0


# ------------------------------------------------------- Bezier fitting
def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def _at(c, t):
    mt = 1 - t
    return (mt ** 3) * c[0] + 3 * (mt ** 2) * t * c[1] + \
           3 * mt * (t ** 2) * c[2] + (t ** 3) * c[3]


def _params(pts):
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*(pts[1:] - pts[:-1]).T))])
    return d / d[-1] if d[-1] > 0 else np.linspace(0, 1, len(pts))


def _solve(pts, u, t1, t2):
    """Least-squares for the two interior control points (Schneider 1990)."""
    A = np.zeros((len(u), 2, 2))
    A[:, 0] = np.outer(3 * (1 - u) ** 2 * u, t1)
    A[:, 1] = np.outer(3 * (1 - u) * u ** 2, t2)
    p0, p3 = pts[0], pts[-1]
    C = np.zeros((2, 2))
    X = np.zeros(2)
    for i, ui in enumerate(u):
        mt = 1 - ui
        base = ((mt ** 3) * p0 + 3 * (mt ** 2) * ui * p0
                + 3 * mt * (ui ** 2) * p3 + (ui ** 3) * p3)
        d = pts[i] - base
        C[0, 0] += A[i, 0] @ A[i, 0]
        C[0, 1] += A[i, 0] @ A[i, 1]
        C[1, 1] += A[i, 1] @ A[i, 1]
        X[0] += A[i, 0] @ d
        X[1] += A[i, 1] @ d
    C[1, 0] = C[0, 1]
    det = C[0, 0] * C[1, 1] - C[1, 0] * C[0, 1]
    seg = float(np.linalg.norm(p3 - p0))
    if abs(det) < 1e-12:
        a1 = a2 = seg / 3.0
    else:
        a1 = (X[0] * C[1, 1] - C[0, 1] * X[1]) / det
        a2 = (C[0, 0] * X[1] - X[0] * C[1, 0]) / det
        # The solve is unstable on near-degenerate runs and will fling a
        # control point far outside the data, drawing as a long spurious
        # line. Fall back to the chord heuristic when it does.
        lim = seg * 1.5
        if not (1e-6 < a1 < lim and 1e-6 < a2 < lim):
            a1 = a2 = seg / 3.0
    return [p0, p0 + t1 * a1, p3 + t2 * a2, p3]


def _worst(pts, c, u):
    err, idx = 0.0, len(pts) // 2
    for i in range(1, len(pts) - 1):
        d = float(np.linalg.norm(_at(c, u[i]) - pts[i])) ** 2
        if d > err:
            err, idx = d, i
    return err, idx


def fit_curve(pts, error: float = 1.0) -> List[Cubic]:
    """Fit a chain of points with cubic Beziers to within `error` pixels."""
    pts = np.asarray(pts, float)
    if len(pts) < 2:
        return []
    return _fit(pts, _unit(pts[1] - pts[0]), _unit(pts[-2] - pts[-1]), error, 0)


def _fit(pts, t1, t2, error, depth):
    if len(pts) == 2:
        d = float(np.linalg.norm(pts[1] - pts[0])) / 3.0
        return [[pts[0], pts[0] + t1 * d, pts[1] + t2 * d, pts[1]]]
    u = _params(pts)
    c = _solve(pts, u, t1, t2)
    err, split = _worst(pts, c, u)
    if err < error * error:
        return [c]
    if depth > 18 or split <= 0 or split >= len(pts) - 1:
        return [c]
    tc = _unit(pts[split - 1] - pts[split + 1])
    return (_fit(pts[:split + 1], t1, tc, error, depth + 1)
            + _fit(pts[split:], -tc, t2, error, depth + 1))


# ------------------------------------------------------------------ API
@dataclass
class TraceResult:
    curves: List[List[Cubic]] = field(default_factory=list)
    stroke_width: float = 2.0
    size: Tuple[int, int] = (0, 0)

    @property
    def n_paths(self):
        return len(self.curves)

    @property
    def n_segments(self):
        return sum(len(c) for c in self.curves)

    def to_svg_paths(self, scale=1.0, dx=0.0, dy=0.0, places=1) -> List[str]:
        out = []
        for curves in self.curves:
            f = lambda p: f"{dx + p[0]*scale:.{places}f} {dy + p[1]*scale:.{places}f}"
            d = "M" + f(curves[0][0])
            for c in curves:
                d += "C" + f(c[1]) + " " + f(c[2]) + " " + f(c[3])
            out.append(d)
        return out

    def to_svg_group(self, scale=1.0, dx=0.0, dy=0.0,
                     color="#111111", stroke=None) -> str:
        w = stroke if stroke is not None else max(0.5, self.stroke_width * scale)
        body = "".join(f'<path d="{d}"/>' for d in self.to_svg_paths(scale, dx, dy))
        return (f'<g fill="none" stroke="{color}" stroke-width="{w:.1f}" '
                f'stroke-linecap="round" stroke-linejoin="round">{body}</g>')


def trace_image(gray: np.ndarray, thresh: int = 200, error: float = 1.0,
                prune: float = 14.0, close: int = 0) -> TraceResult:
    _, bw = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY_INV)
    ink = (bw > 0).astype(np.uint8)
    if close > 0:
        # bridge 1px breaks left by antialiasing on shallow curves
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close))
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, k)
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    skel = skeletonize(ink)
    widths = dist[skel > 0]
    res = TraceResult(size=(gray.shape[1], gray.shape[0]),
                      stroke_width=float(np.median(widths)) * 2.0 if widths.size else 2.0)
    for ch in skeleton_chains(skel, prune):
        pts = np.array([[p[1], p[0]] for p in ch], float)
        if len(pts) > 3:
            pts = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2),
                                   0.6, False).reshape(-1, 2).astype(float)
        cur = fit_curve(pts, error)
        if cur:
            res.curves.append(cur)
    return res


def trace_file(path: str, **kw) -> TraceResult:
    gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(path)
    return trace_image(gray, **kw)
