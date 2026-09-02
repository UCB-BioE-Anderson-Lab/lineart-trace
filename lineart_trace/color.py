"""Colour line art: finding the ink, and splitting it into layers.

Two separate problems, and the first one bites even if you only want a
monochrome trace.

**Finding the ink.** Converting to grey throws away chroma, and chroma is
where some ink lives. Yellow on white has a luminance around 196 of 255 --
lighter than most paper texture -- so a grey threshold drops yellow strokes
entirely while keeping every smudge. Measuring distance from the PAPER COLOUR
in CIE Lab instead keeps yellow (a large b* excursion) and still rejects a
grey background, because it is a distance in colour, not in brightness.

**Splitting it into layers.** Once the ink is found, clustering its colour
gives one mask per pen. Each is traced on its own and its paths carry that
colour, so a five-colour drawing comes out as five sets of restylable lines
rather than one flattened silhouette.

Where two pens cross, one covers the other: the lower stroke is genuinely
broken in the image, and the trace shows the break. `close` bridges it.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

__all__ = ["Layer", "paper_color", "ink_distance", "ink_mask",
           "ink_threshold", "separate_colors", "to_hex"]

# Anything closer than this in Lab is the same pen as far as the eye cares.
SAME_PEN = 20.0


@dataclass
class Layer:
    """One pen's worth of ink: a mask, and the colour to draw it in."""
    mask: np.ndarray
    color: Tuple[int, int, int]        # BGR, as OpenCV holds it
    pixels: int = 0

    @property
    def hex(self) -> str:
        return to_hex(self.color)


def to_hex(bgr) -> str:
    b, g, r = (int(round(float(v))) for v in bgr[:3])
    return "#{:02x}{:02x}{:02x}".format(max(0, min(255, r)),
                                        max(0, min(255, g)),
                                        max(0, min(255, b)))


def _as_bgr(img: np.ndarray) -> np.ndarray:
    img = np.asarray(img)
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        a = img[:, :, 3:4].astype(np.float32) / 255.0
        return (img[:, :, :3].astype(np.float32) * a
                + 255.0 * (1 - a)).astype(np.uint8)
    return img[:, :, :3]


def paper_color(img: np.ndarray, bins: int = 12) -> np.ndarray:
    """The colour of the page: the most common colour, coarsely binned.

    The mode, not the mean or the brightest pixel -- line art is mostly paper,
    so the mode is the paper even when the drawing is dark or the page is
    tinted, and it is unmoved by a bright specular highlight.
    """
    bgr = _as_bgr(img)
    q = (bgr.astype(np.int32) * bins // 256).reshape(-1, 3)
    key = (q[:, 0] * bins + q[:, 1]) * bins + q[:, 2]
    top = int(np.bincount(key, minlength=bins ** 3).argmax())
    sel = key == top
    return bgr.reshape(-1, 3)[sel].mean(axis=0)


def _lab(bgr):
    return cv2.cvtColor(bgr.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)


def ink_distance(img: np.ndarray,
                 paper: Optional[np.ndarray] = None) -> np.ndarray:
    """Per-pixel Lab distance from the paper colour."""
    bgr = _as_bgr(img)
    if paper is None:
        paper = paper_color(bgr)
    lab = _lab(bgr)
    plab = _lab(np.asarray(paper, np.float32).reshape(1, 1, 3))[0, 0]
    return np.linalg.norm(lab - plab, axis=2)


def _otsu(values: np.ndarray, hi: float) -> float:
    """Otsu's threshold over `values`, expressed back in distance units."""
    if len(values) < 2 or hi <= 0:
        return 0.0
    v = np.clip(values / hi * 255.0, 0, 255).astype(np.uint8)
    t, _ = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return float(t) / 255.0 * hi


def _is_new_pen(d: np.ndarray, t2: float, t: float, min_comp: int = 20,
                coherent_frac: float = 0.5, away_frac: float = 0.5) -> bool:
    """Do the pixels between `t2` and `t` look like another pen?

    Judged geometrically, because the histogram cannot tell. Two things sit in
    that band and neither is a pen:

    * **The antialiased halo of a darker pen.** Every blend of ink and paper
      occurs along a stroke's edge, so the halo spans the whole distance
      range. It is recognisable because it HUGS the ink already found -- it is
      a one-pixel rind on it. Accepting halo as a pen fattens every stroke.
    * **Sensor noise and JPEG mush.** Recognisable because it is incoherent:
      isolated pixels, not strokes.

    A real pale pen is coherent AND stands away from the other ink.
    """
    band = ((d > t2) & (d <= t)).astype(np.uint8)
    total = float(band.sum())
    if total < 1:
        return False

    n, lab, st, _ = cv2.connectedComponentsWithStats(band, connectivity=8)
    if n > 1:
        areas = st[1:, cv2.CC_STAT_AREA]
        coherent = float(areas[areas >= min_comp].sum()) / total
    else:
        coherent = 0.0
    if coherent < coherent_frac:
        return False

    ink = (d > t).astype(np.uint8)
    if ink.sum():
        near = cv2.dilate(ink, np.ones((5, 5), np.uint8))
        away = float((band & (near == 0)).sum()) / total
        if away < away_frac:
            return False
    return True


def ink_threshold(d: np.ndarray, floor: float = 15.0,
                  min_band: float = 0.02) -> float:
    """Where ink stops and paper starts, on a colour-distance map.

    Otsu alone is wrong here. It assumes two classes, but a drawing in several
    colours has ink spread over a wide range of distances -- black at 254,
    yellow at 93 -- and Otsu puts its threshold in the middle of the INK,
    classifying the palest pen as paper. On a red/blue/yellow/black figure it
    cut at 98.6 and lost the yellow, which sits at 93.2.

    So: take Otsu, then look again at everything it called paper. If that part
    still splits into a tight peak at zero plus a population standing clearly
    away from it, the "paper" class was really paper plus a pale pen, and the
    lower split is the right one. Repeat while it keeps finding pens.

    The guards are what stop this running away: a new band must sit above
    `floor` (below which a colour difference is not ink, it is JPEG and
    grain), must hold at least `min_band` of the pixels, and must look like a
    pen rather than the halo of a darker one -- see `_is_new_pen`.
    """
    hi = float(d.max())
    if hi <= 0:
        return 0.0
    n = d.size
    t = _otsu(d.ravel(), hi)
    for _ in range(4):
        sub = d[d < t]
        if len(sub) < 16:
            break
        t2 = _otsu(sub, hi)
        if t2 < floor:
            break
        band = float(((d > t2) & (d <= t)).sum())
        if band / n < min_band and band < 200:
            break
        if not _is_new_pen(d, t2, t):
            break
        t = t2
    return max(t, floor if hi > floor else 0.0)


def ink_mask(img: np.ndarray, paper: Optional[np.ndarray] = None,
             tol: Optional[float] = None) -> np.ndarray:
    """0/1 ink mask by distance from the paper colour, not by brightness."""
    d = ink_distance(img, paper)
    if tol is None:
        tol = ink_threshold(d)
    return (d > tol).astype(np.uint8)


def _kmeans(samples, k, seed=0):
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    cv2.setRNGSeed(seed)
    _, labels, centres = cv2.kmeans(samples, k, None, crit, 4,
                                    cv2.KMEANS_PP_CENTERS)
    return labels.ravel(), centres


def separate_colors(img: np.ndarray, k: int = 0, mask: Optional[np.ndarray] = None,
                    min_pixels: int = 40, max_k: int = 8,
                    same_pen: float = SAME_PEN,
                    min_component: int = 12) -> List[Layer]:
    """Split the ink into one Layer per pen.

    `k` is the number of ink colours; 0 or negative picks it automatically by
    adding clusters until every ink pixel is within `same_pen` of its cluster
    colour, which is roughly the point where a person stops calling two
    samples the same pen.

    `min_component` drops islands smaller than that from each layer. Along the
    edge of a red stroke the antialiased pixels shade off towards the paper,
    and a few land nearer some other pen; left in, each becomes its own
    two-pixel "stroke" of the wrong colour.
    """
    bgr = _as_bgr(img)
    if mask is None:
        mask = ink_mask(bgr)
    mask = (np.asarray(mask) > 0).astype(np.uint8)
    if mask.sum() == 0:
        return []

    lab = _lab(bgr)
    ys, xs = np.nonzero(mask)
    ink_lab = lab[ys, xs]

    # Cluster on the INTERIOR of each stroke only. Every antialiased edge
    # pixel is a blend of ink and paper, and those blends form a smear between
    # the real pen colours that would drag the cluster centres off the pens.
    #
    # Select the interior geometrically, by depth into the stroke -- NOT by
    # how far the colour sits from the paper. A colour cut throws away the
    # palest pen wholesale: yellow is the nearest ink to white, so a "keep the
    # most ink-like pixels" rule discards every yellow pixel and the yellow
    # stroke is then assigned to whichever other pen is least unlike it.
    depth = cv2.distanceTransform(mask, cv2.DIST_L2, 3)[ys, xs]
    core = depth >= 1.5
    if core.sum() < max(min_pixels * 2, 40):
        core = depth > np.min(depth)           # thin strokes: shed one ring
    seed_lab = ink_lab[core] if core.sum() >= max(min_pixels, 20) else ink_lab

    if len(seed_lab) < 2:
        centres = seed_lab[:1] if len(seed_lab) else np.zeros((1, 3), np.float32)
        labels = np.zeros(len(ink_lab), np.int32)
    else:
        sample = seed_lab
        if len(sample) > 60000:                     # k-means is O(n k iters)
            step = len(sample) // 60000 + 1
            sample = sample[::step]
        sample = np.ascontiguousarray(sample, np.float32)
        if k and k > 0:
            _, centres = _kmeans(sample, min(int(k), len(sample)))
        else:
            centres = None
            for guess in range(1, max(1, int(max_k)) + 1):
                if guess > len(sample):
                    break
                lb, cs = _kmeans(sample, guess)
                spread = np.linalg.norm(sample - cs[lb], axis=1)
                centres = cs
                if np.percentile(spread, 90) <= same_pen:
                    break
        # Assign every ink pixel, fringe included, to its nearest pen.
        labels = np.argmin(
            np.linalg.norm(ink_lab[:, None, :] - centres[None, :, :], axis=2),
            axis=1).astype(np.int32)

    layers = []
    for i in range(len(centres)):
        sel = labels == i
        n = int(sel.sum())
        if n < min_pixels:
            continue
        m = np.zeros(mask.shape, np.uint8)
        m[ys[sel], xs[sel]] = 1
        if min_component > 1:
            cn, clab, cst, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
            keep = np.zeros(cn, bool)
            keep[1:] = cst[1:, cv2.CC_STAT_AREA] >= min_component
            m = keep[clab].astype(np.uint8)
            n = int(m.sum())
            if n < min_pixels:
                continue
            sel = sel & m[ys, xs].astype(bool)
        # Name the layer by the median of the pixels it actually holds, in
        # BGR: a Lab centroid converted back can land on a colour no pixel has.
        med = np.median(bgr[ys[sel], xs[sel]].astype(np.float32), axis=0)
        layers.append(Layer(m, tuple(med), n))
    layers.sort(key=lambda l: -l.pixels)
    return layers
