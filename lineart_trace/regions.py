"""Separating filled shapes from strokes.

Centreline tracing destroys a filled shape: a solid arrowhead thins to a
spine, so the arrowhead comes out as a line. A filled region has to be
recognised and emitted as a *contour* instead -- the one place where an
outline tracer is the right answer.

A filled shape shows up two ways, so there are two tests:

* **A shape that is filled all through** -- a solid triangle, an inked disc, a
  full stop. Found by thinness, ``4*pi*A / P**2``: 1 for a disc, near 0 for
  anything line-like, and, crucially, SCALE-FREE. That matters more than it
  looks. The obvious test is "is this much wider than a stroke?", but the
  stroke width is measured from the skeleton, and when the picture is mostly
  fill the fill sets that width and the test can never fire. Thinness needs no
  reference width, so it works on an image that is nothing but one solid
  triangle.
* **A blob welded to strokes** -- an arrowhead on a leader line, a solid node
  on a graph. The component as a whole is line-like, so thinness says stroke
  and it must be found locally: only a region surviving erosion by a disc
  wider than any stroke is a fill. This one does need a stroke width, so it
  runs second, after the solid regions are out of the way and the width can be
  measured from what is genuinely stroke.
"""
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .thinning import skeletonize

__all__ = ["split_fills", "region_contours", "thinness", "component_widths"]


def _disc(r: int) -> np.ndarray:
    r = max(1, int(r))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def thinness(area: float, perimeter: float) -> float:
    """``4*pi*A / P**2``: 1.0 for a disc, ~0.03 for a stroked circle."""
    return 4.0 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0.0


def component_widths(ink, lab, n, skel=None):
    """Typical stroke width of each labelled component.

    The MEDIAN width along the component's skeleton, not the largest. An
    arrowhead on a leader line is one component, and its widest point is the
    head -- judging the component by that swallows the shaft along with it.
    The median is set by whatever most of the component is, which for a
    leader line is the line.
    """
    if skel is None:
        skel = skeletonize(ink)
    out = np.zeros(n, np.float32)
    if skel.sum() == 0:
        return out
    d = cv2.dilate(cv2.distanceTransform(ink, cv2.DIST_L2, 5),
                   np.ones((3, 3), np.float32))
    ys, xs = np.nonzero(skel)
    ids, vals = lab[ys, xs], d[ys, xs]
    order = np.argsort(ids, kind="stable")
    ids, vals = ids[order], vals[order]
    cuts = np.searchsorted(ids, np.arange(n + 1))
    for i in range(1, n):
        a, b = cuts[i], cuts[i + 1]
        if b > a:
            out[i] = max(1.0, 2.0 * float(np.median(vals[a:b])) - 1.0)
    return out


def _compact_only(mask, limit, min_area):
    """Keep the components of `mask` that are compact rather than elongated."""
    if limit <= 0 or mask.sum() == 0:
        return mask
    out = np.zeros_like(mask)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts:
        if len(c) < 3:
            continue
        area, perim = cv2.contourArea(c), cv2.arcLength(c, True)
        if area >= min_area and thinness(area, perim) >= limit:
            cv2.drawContours(out, [c], -1, 1, -1)
    return (out & mask).astype(np.uint8)


def _solid_regions(ink, min_area, thin_limit, width_ratio, ref_width, skel):
    """Mask of whole components that are regions rather than strokes.

    Two independent tests, because neither catches everything:

    * **Thinness** ``4*pi*A / P**2`` -- scale-free, so it works on a picture
      that is nothing but one solid shape, where there is no line work to
      compare against. It is also the only one of the two that cannot be
      fooled into eating a stroke.
    * **Width against the drawing's own line work.** Thinness relies on the
      perimeter, which real drawings destroy: a sand-coloured region with a
      wiggly coastline, holes punched by the objects lying on it and black
      outlines crossing it everywhere scores 0.058 -- looking like a stroke
      while being 274,000 pixels of solid fill. Its WIDTH gives it away: 185px
      against 3.4px line work. The reference must come from every colour at
      once, since the sand layer on its own is all sand and, relative to
      itself, perfectly normal.
    """
    out = np.zeros_like(ink)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if n < 2:
        return out
    widths = (component_widths(ink, lab, n, skel)
              if (ref_width and width_ratio > 0) else np.zeros(n, np.float32))
    cnts, hier = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    hier = hier[0] if hier is not None else []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1 or len(c) < 3:
            continue
        area = cv2.contourArea(c)
        perim = cv2.arcLength(c, True)
        holes = []
        j = hier[i][2]
        while j != -1:
            holes.append(cnts[j])
            area -= cv2.contourArea(cnts[j])
            perim += cv2.arcLength(cnts[j], True)
            j = hier[j][0]
        if area < min_area:
            continue
        m = tuple(c[0][0])
        comp = int(lab[m[1], m[0]])
        wide = (ref_width and width_ratio > 0 and comp < n
                and widths[comp] > width_ratio * ref_width)
        if not (thinness(area, perim) >= thin_limit or wide):
            continue
        cv2.drawContours(out, [c], -1, 1, -1)
        if holes:
            cv2.drawContours(out, holes, -1, 0, -1)
    return (out & ink).astype(np.uint8)


def stroke_width_of(ink: np.ndarray, skel: Optional[np.ndarray] = None) -> float:
    """Typical stroke width of a mask, from the distance-transform ridge."""
    ink = (np.asarray(ink) > 0).astype(np.uint8)
    if ink.sum() == 0:
        return 1.0
    if skel is None:
        skel = skeletonize(ink)
    if skel.sum() == 0:
        return 1.0
    d = cv2.dilate(cv2.distanceTransform(ink, cv2.DIST_L2, 5),
                   np.ones((3, 3), np.float32))
    return max(1.0, 2.0 * float(np.median(d[skel > 0])) - 1.0)


def split_fills(ink: np.ndarray, stroke_width: Optional[float] = None,
                ratio: float = 3.0, min_area: int = 16,
                skel: Optional[np.ndarray] = None,
                thin_limit: float = 0.32, width_ratio: float = 5.0,
                ref_width: Optional[float] = None
                ) -> Tuple[np.ndarray, np.ndarray]:
    """Split an ink mask into ``(fill_mask, stroke_mask)``.

    `thin_limit` is the thinness above which a whole component counts as
    filled, and `width_ratio` how many times the drawing's own line work
    (`ref_width`, measured across every colour) a region must span to count as
    filled however long and ragged it is. `ratio` is how many times the typical stroke width a blob welded
    to strokes must measure before it counts as filled rather than merely
    bold -- 3 keeps a triple-weight stroke a stroke.
    """
    ink = (np.asarray(ink) > 0).astype(np.uint8)
    fill = np.zeros_like(ink)
    if ink.sum() == 0 or ratio <= 0:
        return fill, ink

    if thin_limit > 0 or (ref_width and width_ratio > 0):
        fill |= _solid_regions(ink, min_area, thin_limit, width_ratio,
                               ref_width, skel)
    rest = (ink & (fill == 0)).astype(np.uint8)
    if rest.sum() == 0:
        return fill, rest

    # Only now is the stroke width meaningful: it is measured on what is left
    # once the solid shapes have been taken out.
    if stroke_width is None:
        # `skel` belongs to `ink`; it still describes `rest` exactly when
        # nothing was removed, which saves a second thinning pass on the
        # common case of a drawing with no solid shapes in it.
        reuse = skel if (skel is not None and fill.sum() == 0) else None
        stroke_width = stroke_width_of(rest, reuse)
    w = float(stroke_width)
    w = max(1.0, w)

    r = int(round(ratio * w / 2.0))
    if r >= 1:
        core = cv2.morphologyEx(rest, cv2.MORPH_OPEN, _disc(r))
        if core.any():
            n2, lab2, st2, _ = cv2.connectedComponentsWithStats(core, connectivity=8)
            keep = np.zeros(n2, bool)
            keep[1:] = st2[1:, cv2.CC_STAT_AREA] >= max(min_area, r * r)
            core = keep[lab2].astype(np.uint8)
        if core.any():
            # Grow back inside the ink only, and only far enough to reach the
            # tips the erosion cut off. Unbounded reconstruction would run off
            # down every line attached to the blob.
            grown, k3 = core, np.ones((3, 3), np.uint8)
            for _ in range(int(3 * r)):
                nxt = cv2.dilate(grown, k3) & rest
                if np.array_equal(nxt, grown):
                    break
                grown = nxt
            # Surviving that erosion only proves the region is WIDE. A heavy
            # stroke among light ones is wide too, and it is still a stroke --
            # so ask the same scale-free question here: is the thing compact,
            # or is it elongated? An arrowhead scores ~0.55, a 26px rule 0.14.
            fill |= _compact_only(grown, thin_limit, min_area)

    strokes = (ink & (fill == 0)).astype(np.uint8)
    return fill.astype(np.uint8), strokes


def region_contours(fill: np.ndarray, min_area: int = 16
                    ) -> List[List[np.ndarray]]:
    """Outer boundary plus holes for each filled region, as (x, y) polygons.

    Each entry is ``[outer, hole, hole, ...]``; drawn with the even-odd rule
    the holes punch through.
    """
    fill = (np.asarray(fill) > 0).astype(np.uint8)
    if fill.sum() == 0:
        return []
    cnts, hier = cv2.findContours(fill, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []
    hier = hier[0]
    out = []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1:                       # a hole; taken with parent
            continue
        if cv2.contourArea(c) < min_area or len(c) < 4:
            continue
        loops = [c.reshape(-1, 2).astype(float)]
        j = hier[i][2]
        while j != -1:
            h = cnts[j]
            if cv2.contourArea(h) >= max(4.0, min_area / 4.0) and len(h) >= 4:
                loops.append(h.reshape(-1, 2).astype(float))
            j = hier[j][0]
        out.append(loops)
    return out
