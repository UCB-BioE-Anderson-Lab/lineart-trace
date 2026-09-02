"""Skeleton -> ordered point chains.

The skeleton is a pixel graph. Turning it into strokes means three things the
naive walk gets wrong:

1. **A crossing is a blob, not a pixel.** Thinning an X of 10px strokes leaves
   a cluster of branch pixels a few pixels across, sometimes an "H" of two
   branch points joined by a bridge. Treating each branch pixel as its own
   node emits a fistful of 2-pixel junk chains at every crossing. We cluster
   branch pixels (dilated by the local stroke radius) into ONE junction and
   route every arm through its centroid, so the arms actually meet.

2. **Staircases are not branches.** Classify by crossing number, never by
   neighbour count -- see `thinning.crossing_number`.

3. **Every pixel must be accounted for.** Deleting junction pixels leaves
   components that are simple paths or closed loops, so ordering is a walk
   from an end with no bookkeeping across components. Anything the walk steps
   *over* (diagonal short-cuts) is dropped explicitly rather than left behind
   to resurface as a degenerate loop.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .thinning import crossing_number

__all__ = ["Chain", "skeleton_chains", "build_graph", "chain_length"]

Pixel = Tuple[int, int]           # (y, x)
NB8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


@dataclass
class Chain:
    """One traced stroke. `pts` are (y, x) in pixel coordinates.

    `a` / `b` are the ids of the junctions the two ends attach to, or None for
    a free end (a stroke terminus). `closed` marks a chain that returns to its
    own start.
    """
    pts: List[Tuple[float, float]] = field(default_factory=list)
    a: Optional[int] = None
    b: Optional[int] = None
    closed: bool = False

    def __len__(self):
        return len(self.pts)

    @property
    def length(self) -> float:
        return chain_length(self.pts)

    def reversed_(self) -> "Chain":
        return Chain(self.pts[::-1], self.b, self.a, self.closed)


def chain_length(pts: Sequence[Tuple[float, float]]) -> float:
    a = np.asarray(pts, float)
    if len(a) < 2:
        return 0.0
    return float(np.hypot(*(a[1:] - a[:-1]).T).sum())


# ------------------------------------------------------------------ helpers
def _neighbours(p, mask, H, W):
    y, x = p
    return [(y + dy, x + dx) for dy, dx in NB8
            if 0 <= y + dy < H and 0 <= x + dx < W and mask[y + dy, x + dx]]


def _order_path(pixels):
    """Order one connected component of thin pixels into chains.

    Returns a list of pixel sequences. A clean component yields exactly one:
    a path (walked end to end) or a loop (walked all the way round). Pixels
    stepped over as staircase short-cuts are discarded, and any genuinely
    disconnected remainder is emitted as a further chain rather than silently
    dropped.
    """
    todo = set(pixels)
    nbr = {p: [q for q in _all8(p) if q in todo] for p in todo}
    out = []
    while todo:
        live = {p for p in todo}
        deg = {p: sum(1 for q in nbr[p] if q in live) for p in live}
        ends = sorted(p for p in live if deg[p] <= 1)
        start = ends[0] if ends else min(live)
        seq = [start]
        live.discard(start)
        prev, cur = None, start
        while True:
            cand = [q for q in nbr[cur] if q in live]
            if not cand:
                break
            if prev is not None:
                # A candidate touching `prev` is a staircase short-cut sitting
                # beside the line, not the next point along it.
                far = [q for q in cand
                       if max(abs(q[0] - prev[0]), abs(q[1] - prev[1])) > 1]
                if far:
                    cand = far
            # 4-connected steps before diagonal ones; ties broken by position
            # so the walk is deterministic.
            cand.sort(key=lambda q: (abs(q[0] - cur[0]) + abs(q[1] - cur[1]), q))
            nxt = cand[0]
            seq.append(nxt)
            live.discard(nxt)
            prev, cur = cur, nxt
        for p in seq:
            todo.discard(p)
        # Anything left touching the chain we just laid down is staircase
        # padding: drop it, or it comes back as a spurious 2-pixel loop.
        touching = {q for p in seq for q in _all8(p)}
        todo -= touching
        out.append(seq)
    return out


def _all8(p):
    y, x = p
    return [(y + dy, x + dx) for dy, dx in NB8]


# -------------------------------------------------------------------- graph
def build_graph(skel: np.ndarray, junction_radius: int = 1):
    """Split the skeleton into junctions and the chains between them.

    `junction_radius` merges branch pixels within that distance into a single
    junction; pass roughly the stroke half-width so a thick crossing collapses
    to one node instead of a knot of them.

    Returns (chains, junctions) where junctions maps id -> (y, x) centroid.
    """
    skel = (np.asarray(skel) > 0).astype(np.uint8)
    H, W = skel.shape
    if skel.sum() == 0:
        return [], {}

    cn = crossing_number(skel)
    branch = ((cn >= 3) & (skel > 0)).astype(np.uint8)

    r = max(0, int(junction_radius))
    if r > 0 and branch.any():
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        branch = (cv2.dilate(branch, k) & skel).astype(np.uint8)

    n_lab, lab = cv2.connectedComponents(branch, connectivity=8)
    junctions: Dict[int, Tuple[float, float]] = {}
    if n_lab > 1:
        # Centroids from one bincount rather than a full-image scan per label.
        jy, jx = np.nonzero(branch)
        jl = lab[jy, jx]
        cnt = np.bincount(jl, minlength=n_lab).astype(float)
        sy = np.bincount(jl, weights=jy, minlength=n_lab)
        sx = np.bincount(jl, weights=jx, minlength=n_lab)
        for j in range(1, n_lab):
            if cnt[j]:
                junctions[j] = (float(sy[j] / cnt[j]), float(sx[j] / cnt[j]))

    thin = ((skel > 0) & (branch == 0)).astype(np.uint8)
    n_seg, seg = cv2.connectedComponents(thin, connectivity=8)

    chains: List[Chain] = []
    for pixels in _group_by_label(thin, seg, n_seg):
        for order in _order_path(pixels):
            if not order:
                continue
            a = _touching_junction(order[0], lab, H, W)
            b = _touching_junction(order[-1], lab, H, W)
            pts = [(float(y), float(x)) for y, x in order]
            closed = False
            if a is not None:
                pts.insert(0, junctions[a])
            if b is not None:
                pts.append(junctions[b])
            if a is None and b is None and len(pts) > 2:
                # Isolated ring (a plain circle has no branch pixel at all).
                head, tail = np.array(pts[0]), np.array(pts[-1])
                if float(np.hypot(*(head - tail))) <= 2.0:
                    pts.append(pts[0])
                    closed = True
            chains.append(Chain(pts, a, b, closed))

    # A junction with no chain but a whole ring around it (a lone loop pinched
    # by a single stray branch pixel) would otherwise vanish; the ring is the
    # thin component and is already handled above.
    return chains, junctions


def _group_by_label(mask, labels, n):
    """Pixels of each labelled component, from a single scan of the mask."""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return []
    lv = labels[ys, xs]
    order = np.argsort(lv, kind="stable")
    ys, xs, lv = ys[order], xs[order], lv[order]
    cuts = np.searchsorted(lv, np.arange(1, n + 1))
    out = []
    for i in range(1, n):
        a, b = cuts[i - 1], cuts[i] if i < n - 1 else len(lv)
        if b > a:
            out.append(list(zip(ys[a:b].tolist(), xs[a:b].tolist())))
    return out


def _touching_junction(p, lab, H, W):
    y, x = p
    best = None
    for dy, dx in NB8:
        yy, xx = y + dy, x + dx
        if 0 <= yy < H and 0 <= xx < W and lab[yy, xx]:
            j = int(lab[yy, xx])
            if best is None or j < best:
                best = j
    return best


# --------------------------------------------------------------- simplify
def prune_and_merge(chains: List[Chain], prune: float,
                    min_loop: float = 0.0) -> List[Chain]:
    """Drop thinning artefacts, then splice what is left back together.

    A short chain with a FREE end is a spur thrown off by thinning. A short
    chain running junction-to-junction is structural -- it is the piece of a
    line *between* two crossings -- and dropping it punches a visible gap at
    every crossing in the drawing. Removing a spur can leave a junction with
    only two arms, which is no longer a junction, so pruning and merging
    alternate until the result stops changing.
    """
    chains = [c for c in chains if len(c.pts) >= 2]
    while True:
        before = len(chains)
        chains = [c for c in chains if not _is_spur(c, prune)]
        chains = _merge(chains)
        if min_loop > 0:
            chains = [c for c in chains
                      if not (c.closed and c.length < min_loop)]
        if len(chains) == before:
            return chains


def _is_spur(c: Chain, prune: float) -> bool:
    if c.closed:
        return False
    free = (c.a is None) + (c.b is None)
    if free == 2:                      # a lone stroke: keep unless it is dust
        return c.length < min(prune, 3.0)
    return free == 1 and c.length < prune


def _merge(chains: List[Chain]) -> List[Chain]:
    """Splice chains at any junction where exactly two chain ends arrive."""
    from collections import defaultdict
    chains = [c for c in chains if len(c.pts) >= 2]
    while True:
        ends = defaultdict(list)
        for i, c in enumerate(chains):
            if c.closed:
                continue
            if c.a is not None:
                ends[c.a].append((i, 0))
            if c.b is not None:
                ends[c.b].append((i, 1))
        for j, lst in ends.items():
            if len(lst) != 2:
                continue
            (i, ei), (k, ek) = lst
            if i == k:                                  # chain closes on itself
                c = chains[i]
                pts = c.pts if ei == 1 else c.pts[::-1]
                chains[i] = Chain(pts + [pts[0]], None, None, True)
                break
            a = chains[i] if ei == 1 else chains[i].reversed_()
            b = chains[k] if ek == 0 else chains[k].reversed_()
            chains[i] = Chain(a.pts + b.pts[1:], a.a, b.b, False)
            chains[k] = Chain([], None, None, False)
            break
        else:
            return [c for c in chains if len(c.pts) >= 2]


# ------------------------------------------------------------- public API
def skeleton_chains(skel: np.ndarray, prune: float = 14.0,
                    junction_radius: int = 1,
                    min_loop: float = 0.0) -> List[List[Tuple[int, int]]]:
    """Walk a skeleton into ordered (y, x) pixel chains.

    Kept as the simple list-of-points entry point; `build_graph` exposes the
    junction structure for callers that need it.
    """
    chains, _ = build_graph(skel, junction_radius)
    chains = prune_and_merge(chains, prune, min_loop)
    return [[(int(round(y)), int(round(x))) for y, x in c.pts] for c in chains]
