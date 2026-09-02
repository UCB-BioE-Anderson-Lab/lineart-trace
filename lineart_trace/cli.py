"""Command line front end."""
import argparse
import os
import sys

import cv2

from . import __version__
from .binarize import binarize, to_gray
from .metrics import compare
from .raster import rasterize
from .trace import trace_image


def build_parser():
    p = argparse.ArgumentParser(
        prog="lineart-trace",
        description="Vectorise black-on-white line art into centreline SVG "
                    "Beziers (not outlines).")
    p.add_argument("src", help="input image")
    p.add_argument("-o", "--out", help="write here instead of stdout")
    p.add_argument("--version", action="version", version=__version__)

    g = p.add_argument_group("input")
    g.add_argument("--method", default="auto",
                   choices=["auto", "fixed", "otsu", "adaptive"],
                   help="binarisation; auto flattens uneven lighting (default)")
    g.add_argument("--thresh", type=int, default=200,
                   help="ink cutoff 0-255, for --method fixed")
    g.add_argument("--flatten", dest="flatten", action="store_true", default=None,
                   help="force background flattening on")
    g.add_argument("--no-flatten", dest="flatten", action="store_false",
                   help="force background flattening off")
    g.add_argument("--invert", dest="invert", action="store_true", default=None,
                   help="treat light marks on a dark ground as ink")
    g.add_argument("--denoise", action="store_true",
                   help="median filter before thresholding (photos)")
    g.add_argument("--despeckle", type=int, default=0, metavar="AREA",
                   help="drop ink blobs smaller than AREA pixels")
    g.add_argument("--close", type=int, default=0, metavar="R",
                   help="close radius; bridges antialias breaks in curves")

    g = p.add_argument_group("tracing")
    g.add_argument("--error", type=float, default=1.0,
                   help="Bezier fit tolerance in source pixels (default 1.0)")
    g.add_argument("--prune", type=float, default=0.0,
                   help="drop dead-end chains shorter than this "
                        "(default: derived from stroke width)")
    g.add_argument("--corner-angle", type=float, default=75.0,
                   help="split the fit at turns sharper than this; 0 disables")
    g.add_argument("--smooth", type=int, default=5,
                   help="chain smoothing window; 0 disables")
    g.add_argument("--fill-ratio", type=float, default=3.0,
                   help="a blob this many stroke widths across becomes a fill")
    g.add_argument("--thin-limit", type=float, default=0.32,
                   help="thinness above which a whole shape becomes a fill; "
                        "0 disables filled-region detection")
    g.add_argument("--min-fill-area", type=int, default=16,
                   help="ignore filled regions smaller than this")

    g = p.add_argument_group("output")
    g.add_argument("--width", type=float, default=0.0,
                   help="target width in output units (default: source pixels)")
    g.add_argument("-x", type=float, default=0.0)
    g.add_argument("-y", type=float, default=0.0)
    g.add_argument("--stroke", type=float, default=None,
                   help="force one stroke width for every path")
    g.add_argument("--uniform-width", action="store_true",
                   help="use the drawing's median width for every path")
    g.add_argument("--color", default="#111111")
    g.add_argument("--background", default="#ffffff",
                   help="'none' for a transparent document")
    g.add_argument("--places", type=int, default=1,
                   help="decimal places in path data")
    g.add_argument("--svg", action="store_true",
                   help="emit a standalone SVG document, not just the <g>")
    g.add_argument("--check", action="store_true",
                   help="render the result back and report round-trip scores")
    g.add_argument("-q", "--quiet", action="store_true")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    img = cv2.imread(a.src, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"lineart-trace: cannot read {a.src}", file=sys.stderr)
        return 2

    res = trace_image(
        img, thresh=a.thresh, method=a.method, error=a.error, prune=a.prune,
        close=a.close, despeckle_area=a.despeckle, denoise=a.denoise,
        flatten=a.flatten, invert=a.invert, corner_angle=a.corner_angle,
        smooth=a.smooth, fill_ratio=a.fill_ratio, thin_limit=a.thin_limit,
        min_fill_area=a.min_fill_area)

    w, h = res.size
    scale = (a.width / w) if a.width else 1.0
    bg = None if a.background.lower() in ("none", "") else a.background
    per_path = not a.uniform_width
    if a.svg:
        out = res.to_svg(scale, a.color, bg, a.stroke, per_path, a.places)
    else:
        out = res.to_svg_group(scale, a.x, a.y, a.color, a.stroke, per_path,
                               a.places)

    if a.out:
        with open(a.out, "w") as f:
            f.write(out + "\n")
    else:
        print(out)

    if not a.quiet:
        print(f"[{os.path.basename(a.src)}] {w}x{h} -> {res.n_strokes} strokes"
              f" + {res.n_fills} fills, {res.n_segments} cubics, "
              f"stroke ~{res.stroke_width:.1f}px", file=sys.stderr)
    if a.check:
        ink = binarize(to_gray(img), method=a.method, thresh=a.thresh,
                       flatten=a.flatten, denoise=a.denoise, invert=a.invert)
        m = compare(ink, rasterize(res, res.size))
        print(f"[check] iou={m['iou']:.3f} coverage={m['coverage']:.3f} "
              f"spill={m['spill']:.3f} d95={m['d95']:.1f}px", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
