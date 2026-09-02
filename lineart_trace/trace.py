"""Centreline vectorisation of line art.

    binarize -> split fills from strokes -> thin -> skeleton graph ->
    corner-aware Schneider Bezier fitting -> SVG

Unlike an outline tracer (potrace, ``cv2.findContours``), which returns a
closed loop *around* every stroke, this recovers the CENTRELINE, so the output
is real lines you can restyle: change weight, colour, dash, or animate. Stroke
width is recovered per path from the distance transform, so a drawing with
mixed weights stays mixed. Regions too solid to be strokes are emitted as
filled contours instead, because a centreline cannot represent them.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .binarize import binarize, despeckle, has_chroma, to_gray
from .color import Layer, separate_colors, to_hex
from .fitting import Cubic, fit_curve
from .graph import build_graph, prune_and_merge
from .regions import region_contours, split_fills
from .thinning import skeletonize

__all__ = ["TraceResult", "StrokePath", "FillPath", "trace_image", "trace_file",
           "trace_mask"]


# ------------------------------------------------------------------ model
@dataclass
class StrokePath:
    curves: List[Cubic] = field(default_factory=list)
    width: float = 2.0
    closed: bool = False
    color: Optional[str] = None        # e.g. "#dc0000"; None = the group's


@dataclass
class FillPath:
    loops: List[List[Cubic]] = field(default_factory=list)
    color: Optional[str] = None


@dataclass
class TraceResult:
    strokes: List[StrokePath] = field(default_factory=list)
    fills: List[FillPath] = field(default_factory=list)
    stroke_width: float = 2.0
    size: Tuple[int, int] = (0, 0)          # (width, height) in pixels

    # ---- counts
    @property
    def curves(self) -> List[List[Cubic]]:
        """Stroke centrelines, as a plain list of Bezier runs."""
        return [s.curves for s in self.strokes]

    @property
    def n_paths(self) -> int:
        return len(self.strokes) + len(self.fills)

    @property
    def n_strokes(self) -> int:
        return len(self.strokes)

    @property
    def n_fills(self) -> int:
        return len(self.fills)

    @property
    def n_segments(self) -> int:
        return (sum(len(s.curves) for s in self.strokes)
                + sum(len(l) for f in self.fills for l in f.loops))

    @property
    def widths(self) -> List[float]:
        return [s.width for s in self.strokes]

    @property
    def colors(self) -> List[str]:
        """The distinct ink colours found, most-used first."""
        from collections import Counter
        n = Counter()
        for s in self.strokes:
            if s.color:
                n[s.color] += len(s.curves)
        for f in self.fills:
            if f.color:
                n[f.color] += sum(len(l) for l in f.loops)
        return [c for c, _ in n.most_common()]

    # ---- output
    def to_svg_paths(self, scale=1.0, dx=0.0, dy=0.0, places=1) -> List[str]:
        """`d` attributes for the stroke centrelines."""
        return [_path_d(s.curves, scale, dx, dy, places, s.closed)
                for s in self.strokes]

    def to_fill_paths(self, scale=1.0, dx=0.0, dy=0.0, places=1) -> List[str]:
        out = []
        for f in self.fills:
            out.append(" ".join(_path_d(l, scale, dx, dy, places, True)
                                for l in f.loops))
        return out

    def to_svg_group(self, scale=1.0, dx=0.0, dy=0.0, color="#111111",
                     stroke: Optional[float] = None, per_path_width=True,
                     places=1) -> str:
        """One `<g>` holding the fills and then the stroked centrelines."""
        body = []
        for f, d in zip(self.fills, self.to_fill_paths(scale, dx, dy, places)):
            body.append(f'<path fill="{f.color or color}" fill-rule="evenodd" '
                        f'stroke="none" d="{d}"/>')
        base = stroke if stroke is not None else max(0.4, self.stroke_width * scale)
        for s, d in zip(self.strokes, self.to_svg_paths(scale, dx, dy, places)):
            if stroke is None and per_path_width:
                w = max(0.4, s.width * scale)
            else:
                w = base
            attr = "" if abs(w - base) < 0.05 else f' stroke-width="{w:.2f}"'
            if s.color and s.color != color:
                attr += f' stroke="{s.color}"'
            body.append(f'<path{attr} d="{d}"/>')
        return (f'<g fill="none" stroke="{color}" stroke-width="{base:.2f}" '
                f'stroke-linecap="round" stroke-linejoin="round">'
                f'{"".join(body)}</g>')

    def to_svg(self, scale=1.0, color="#111111", background="#ffffff",
               stroke=None, per_path_width=True, places=1) -> str:
        w, h = self.size[0] * scale, self.size[1] * scale
        bg = (f'<rect width="100%" height="100%" fill="{background}"/>'
              if background else "")
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
                f'height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">{bg}'
                f'{self.to_svg_group(scale, 0, 0, color, stroke, per_path_width, places)}'
                f'</svg>')


def _path_d(curves, scale, dx, dy, places, closed):
    if not curves:
        return ""
    f = lambda p: f"{dx + p[0] * scale:.{places}f} {dy + p[1] * scale:.{places}f}"
    d = "M" + f(curves[0][0])
    for c in curves:
        d += "C" + f(c[1]) + " " + f(c[2]) + " " + f(c[3])
    return d + "Z" if closed else d


# --------------------------------------------------------------- pipeline
def trace_mask(ink: np.ndarray, error: float = 1.0, prune: float = 0.0,
               corner_angle: float = 75.0, smooth: int = 5,
               fill_ratio: float = 3.0, min_fill_area: int = 16,
               thin_limit: float = 0.32,
               junction_radius: Optional[int] = None,
               extend_ends: bool = False, min_loop: float = 0.0,
               per_path_width: bool = True) -> TraceResult:
    """Vectorise a 0/1 ink mask. See `trace_image` for the parameters."""
    ink = (np.asarray(ink) > 0).astype(np.uint8)
    H, W = ink.shape
    res = TraceResult(size=(W, H))
    if ink.sum() == 0:
        return res

    dist = _ridge(cv2.distanceTransform(ink, cv2.DIST_L2, 5))
    skel0 = skeletonize(ink)
    med_half = float(np.median(dist[skel0 > 0])) if skel0.any() else 1.0
    res.stroke_width = _width_from(med_half)

    fill, strokes = split_fills(ink, None, fill_ratio, min_fill_area, skel0,
                                thin_limit=thin_limit)
    for loops in region_contours(fill, min_fill_area):
        fitted = [fit_curve(l, max(error, 0.8), closed=True,
                            corner_angle=corner_angle, smooth=smooth)
                  for l in loops]
        fitted = [f for f in fitted if f]
        if fitted:
            res.fills.append(FillPath(fitted))

    if strokes.sum() == 0:
        return res

    # Thinning is the most expensive step; skip the repeat when taking the
    # fills out changed nothing.
    skel = skel0 if fill.sum() == 0 else skeletonize(strokes)
    if skel.sum() == 0:
        return res
    sdist = _ridge(cv2.distanceTransform(strokes, cv2.DIST_L2, 5))
    half = float(np.median(sdist[skel > 0]))
    if not per_path_width:
        res.stroke_width = _width_from(half)

    if junction_radius is None:
        junction_radius = int(max(1, round(half)))
    if prune <= 0:
        # Thinning throws a spur of up to about the stroke radius off every
        # end and junction; anything shorter than a stroke width is one.
        prune = max(3.0, 1.5 * half * 2.0)

    chains, _ = build_graph(skel, junction_radius)
    chains = prune_and_merge(chains, prune, min_loop)

    for ch in chains:
        pts = np.array([(x, y) for y, x in ch.pts], float)
        if len(pts) < 2:
            continue
        w = _chain_width(sdist, ch.pts, half)
        if extend_ends and not ch.closed:
            pts = _extend(pts, ch, w / 2.0)
        curves = fit_curve(pts, error, closed=ch.closed,
                           corner_angle=corner_angle, smooth=smooth)
        if curves:
            res.strokes.append(StrokePath(curves, w, ch.closed))
    return res


def _ridge(dist: np.ndarray) -> np.ndarray:
    """Local max of the distance transform.

    The skeleton does not always land exactly on the ridge of the distance
    transform -- on a curve it sits up to half a pixel off, and reading the
    transform there understates the width by more than a pixel (a 9px circle
    measures 7.8). Taking the largest value in the 3x3 neighbourhood reads the
    ridge itself.
    """
    return cv2.dilate(dist, np.ones((3, 3), np.float32))


def _width_from(half: float) -> float:
    """Stroke width from a distance-transform reading at the centreline.

    The transform reports the distance to the nearest blank pixel, so the
    centre of an n-pixel-wide stroke reads (n + 1) / 2, not n / 2: the two
    outermost ink pixels are both counted. Doubling alone therefore overstates
    every stroke by a pixel, which shows up as visible fattening.
    """
    return max(0.5, 2.0 * float(half) - 1.0)


def _chain_width(dist, pts, fallback):
    """Median stroke width along one chain, from the distance transform."""
    H, W = dist.shape
    vals = []
    for y, x in pts:
        yi, xi = int(round(y)), int(round(x))
        if 0 <= yi < H and 0 <= xi < W:
            v = float(dist[yi, xi])
            if v > 0:
                vals.append(v)
    if not vals:
        return _width_from(fallback)
    # Trim the ends: thinning stops short of a stroke's tip, and the last few
    # samples sit where the distance transform is already falling away.
    if len(vals) > 8:
        vals = vals[len(vals) // 8: -len(vals) // 8]
    return _width_from(float(np.median(vals)))


def _extend(pts, ch, reach):
    """Push free ends outward along their tangent.

    Thinning stops roughly a stroke radius short of a stroke's tip, so a
    traced line is visibly shorter than the one it came from. Only free ends
    move; an end that meets a junction is already in the right place.
    """
    if reach <= 0.5 or len(pts) < 3:
        return pts
    out = pts
    k = min(6, len(pts) - 1)
    if ch.a is None:
        t = pts[0] - pts[k]
        n = float(np.linalg.norm(t))
        if n > 1e-6:
            out = np.vstack([pts[0] + t / n * reach, out])
    if ch.b is None:
        t = pts[-1] - pts[-1 - k]
        n = float(np.linalg.norm(t))
        if n > 1e-6:
            out = np.vstack([out, pts[-1] + t / n * reach])
    return out


def trace_image(img: np.ndarray, thresh: int = 200, error: float = 1.0,
                prune: float = 0.0, close: int = 0, method: str = "auto",
                despeckle_area: int = 0, denoise: bool = False,
                flatten: Optional[bool] = None, invert: Optional[bool] = None,
                colors: int = 1, max_colors: int = 8,
                **kw) -> TraceResult:
    """Vectorise an image array.

    thresh / method
        ``method="fixed"`` uses `thresh` directly; ``auto`` (the default)
        flattens uneven lighting when it detects any and then applies Otsu.
    error
        maximum Bezier deviation, in input pixels.
    prune
        drop dead-end chains shorter than this; 0 derives it from stroke width.
    close
        morphological close radius, bridging antialias breaks in shallow curves.
    despeckle_area
        drop ink blobs smaller than this many pixels.
    colors
        1 (the default) traces every pen as one colour. A number above 1
        splits the ink into that many pens and gives each path its own
        colour; 0 picks the number of pens automatically. Where two pens
        cross, the upper one covers the lower, so the lower stroke really is
        broken in the image -- raise `close` to bridge it.
    corner_angle, smooth, fill_ratio, min_fill_area, junction_radius,
    extend_ends, min_loop
        passed through to `trace_mask`.
    """
    gray = to_gray(img)
    ink = binarize(img, method=method, thresh=thresh, flatten=flatten,
                   denoise=denoise, invert=invert)
    if close or despeckle_area:
        ink = despeckle(ink, despeckle_area, close)
    size = (gray.shape[1], gray.shape[0])

    if colors == 1 or not has_chroma(img):
        res = trace_mask(ink, error=error, prune=prune, **kw)
        res.size = size
        return res

    layers = separate_colors(img, k=max(0, int(colors)), mask=ink,
                             max_k=max_colors)
    res = TraceResult(size=size)
    widths = []
    for layer in layers:
        m = layer.mask
        if close or despeckle_area:
            # Per layer, not just once over all the ink: a stroke crossed by
            # another pen is broken in ITS OWN layer, and closing the combined
            # mask cannot mend a gap that only exists after the split.
            m = despeckle(m, despeckle_area, close)
        sub = trace_mask(m, error=error, prune=prune, **kw)
        for s in sub.strokes:
            s.color = layer.hex
        for f in sub.fills:
            f.color = layer.hex
        res.strokes.extend(sub.strokes)
        res.fills.extend(sub.fills)
        if sub.strokes:
            widths.extend(s.width for s in sub.strokes)
    res.stroke_width = float(np.median(widths)) if widths else 2.0
    return res


def trace_file(path: str, **kw) -> TraceResult:
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    return trace_image(img, **kw)
