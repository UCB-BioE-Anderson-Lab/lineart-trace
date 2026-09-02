"""Zhang-Suen thinning: ink mask -> 1px-wide skeleton."""
import numpy as np

__all__ = ["skeletonize", "crossing_number", "neighbour_count",
           "thin_redundant"]

# P2..P9 in Zhang-Suen order: N, NE, E, SE, S, SW, W, NW.
_OFFSETS = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))


def _ring(img):
    """The eight shifted neighbour planes of `img`, in Zhang-Suen order."""
    P = np.pad(img, 1)
    H, W = img.shape
    return [P[1 + dy:1 + dy + H, 1 + dx:1 + dx + W] for dy, dx in _OFFSETS]


def skeletonize(mask: np.ndarray, cleanup: bool = True) -> np.ndarray:
    """Thin a 0/1 mask to a 1px-wide skeleton.

    Zhang & Suen (1984) followed by a sequential simple-point cleanup. The
    cleanup is not optional cosmetics: parallel Zhang-Suen leaves two-pixel
    diagonal bands, and inside such a band every pixel has crossing number 2,
    so junctions read as ordinary line pixels and the graph walk never finds
    the crossing at all. See `thin_redundant`.
    """
    img = (np.asarray(mask) > 0).astype(np.uint8)
    if img.ndim != 2:
        raise ValueError("skeletonize expects a 2-D mask")
    img = img.copy()
    while True:
        removed = False
        for step in (0, 1):
            R = np.stack(_ring(img))
            P2, P4, P6, P8 = R[0], R[2], R[4], R[6]
            B = R.sum(0, dtype=np.int16)
            A = ((R == 0) & (np.roll(R, -1, axis=0) == 1)).sum(0, dtype=np.int16)
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
            return thin_redundant(img) if cleanup else img


def crossing_number(skel: np.ndarray) -> np.ndarray:
    """0->1 transitions around each pixel's 8-neighbourhood, masked to the
    skeleton. 1 = endpoint, 2 = on a line, >=3 = branch point.

    This, not the raw 8-neighbour count, is the right classifier: on a diagonal
    staircase an ordinary interior pixel has three 8-neighbours, so counting
    neighbours reports false branch points and shatters every curve.
    """
    skel = (np.asarray(skel) > 0).astype(np.uint8)
    R = np.stack(_ring(skel))
    A = ((R == 0) & (np.roll(R, -1, axis=0) == 1)).sum(0, dtype=np.int32)
    return A * skel


def neighbour_count(skel: np.ndarray) -> np.ndarray:
    """Raw count of 8-neighbours that are ink, masked to the skeleton."""
    skel = (np.asarray(skel) > 0).astype(np.uint8)
    return sum(p.astype(np.int32) for p in _ring(skel)) * skel


# --- redundant-pixel LUT -------------------------------------------------
# One bit per ring position (see _OFFSETS): N, NE, E, SE, S, SW, W, NW.
def _build_lut():
    adj = [[max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1
            for b in _OFFSETS] for a in _OFFSETS]
    lut = np.zeros(256, np.uint8)
    for code in range(256):
        on = [i for i in range(8) if code >> i & 1]
        if len(on) < 2:                     # endpoint or isolated: never drop
            continue
        seen, stack = {on[0]}, [on[0]]      # are the neighbours connected
        while stack:                        # to each other WITHOUT the centre?
            i = stack.pop()
            for j in on:
                if j not in seen and adj[i][j]:
                    seen.add(j)
                    stack.append(j)
        lut[code] = len(seen) == len(on)
    return lut


_REDUNDANT = _build_lut()
_BITS = np.array([1 << i for i in range(8)], np.int32)


def _codes(img):
    return np.tensordot(np.stack(_ring(img)).astype(np.int32), _BITS, (0, 0))


def thin_redundant(skel: np.ndarray) -> np.ndarray:
    """Remove pixels a 1-px skeleton does not need, one at a time.

    A pixel is redundant when its ink neighbours are already 8-connected to
    each other without it, and it is not an endpoint. Deleting it therefore
    cannot split the skeleton -- it only sheds the padding of two-wide
    diagonal bands and diagonal short-cut triangles.

    This matters far more than it sounds. Parallel Zhang-Suen leaves two-wide
    bands, and every pixel inside such a band has crossing number 2, so an
    eight-armed hub reads as ordinary line pixels and no junction is found at
    all. Note the test is 8-connectivity for the neighbours too: the textbook
    crossing-number simple-point test assumes a 4-connected background and
    will not cut a staircase.

    Removal must be SEQUENTIAL -- deleting every redundant pixel at once would
    cut a two-wide band from both sides simultaneously and sever the line.
    """
    img = (np.asarray(skel) > 0).astype(np.uint8).copy()
    H, W = img.shape
    while True:
        code = _codes(img)
        cand = np.nonzero((img > 0) & (_REDUNDANT[code] > 0))
        if len(cand[0]) == 0:
            return img
        dropped = 0
        for y, x in zip(cand[0].tolist(), cand[1].tolist()):
            if not img[y, x]:
                continue
            c = 0
            for i, (dy, dx) in enumerate(_OFFSETS):
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and img[yy, xx]:
                    c |= 1 << i
            if _REDUNDANT[c]:
                img[y, x] = 0
                dropped += 1
        if not dropped:
            return img
