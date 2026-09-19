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
    g.add_argument("--colors", type=int, default=1, metavar="N",
                   help="1 (default) traces every pen as one colour; N>1 "
                        "splits the ink into N pens, each path keeping its "
                        "own colour; 0 picks the number of pens itself")
    g.add_argument("--max-colors", type=int, default=8,
                   help="ceiling when --colors 0 is choosing")

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
    g.add_argument("-x", "--x", type=float, default=0.0,
                   help="translate the output group by this many units")
    g.add_argument("-y", "--y", type=float, default=0.0)
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
    g.add_argument("--scene", action="store_true",
                   help="emit a scene document (§3.10) instead of SVG: named "
                        "elements, a frame with the page transform, and the "
                        "provenance to re-trace it when the source changes")
    g.add_argument("--scene-name", metavar="NAME",
                   help="the scene's name; default: the source's filename")
    g.add_argument("--unit", default="mm", choices=["mm", "pt", "px", "in"],
                   help="the page unit for --scene (default mm)")
    g.add_argument("--dpi", type=float, default=96.0,
                   help="px per inch for --scene when --width is not given")
    g.add_argument("--check", action="store_true",
                   help="render the result back and report round-trip scores")
    g.add_argument("-q", "--quiet", action="store_true")
    return p


def _scene_name(path):
    """A source filename as a scene name: lower case, digits and hyphens, nothing else.

    A name that is not usable is repaired here rather than refused, because the default has
    to work for any file somebody points at. An explicit --scene-name is NOT repaired: a
    name the caller chose and cannot have is an error worth hearing about.
    """
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    out = "".join(c if c.isalnum() and c.isascii() else "-" for c in stem)
    out = out.strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "traced"


def _walk_names(doc):
    from .scene import model
    return model.addresses(doc)


def main(argv=None):
    a = build_parser().parse_args(argv)
    img = cv2.imread(a.src, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"lineart-trace: cannot read {a.src}", file=sys.stderr)
        return 2

    res = trace_image(
        img, thresh=a.thresh, method=a.method, error=a.error, prune=a.prune,
        close=a.close, despeckle_area=a.despeckle, denoise=a.denoise,
        flatten=a.flatten, invert=a.invert, colors=a.colors,
        max_colors=a.max_colors, corner_angle=a.corner_angle,
        smooth=a.smooth, fill_ratio=a.fill_ratio, thin_limit=a.thin_limit,
        min_fill_area=a.min_fill_area)

    w, h = res.size

    if a.scene:
        from .scene import ingest, io as scene_io
        name = a.scene_name or _scene_name(a.src)
        params = {k: getattr(a, k) for k in
                  ("method", "thresh", "colors", "max_colors", "error", "prune",
                   "corner_angle", "smooth", "fill_ratio", "thin_limit",
                   "min_fill_area", "close", "despeckle", "denoise")}
        try:
            doc = ingest.scene_from_trace(
                res, name=name, source=a.src, params=params,
                canvas_width=(a.width or None), unit=a.unit, dpi=a.dpi)
        except ValueError as e:
            print(f"lineart-trace: {e}", file=sys.stderr)
            return 3
        scene_io.dump(doc, a.out or "-")
        if not a.quiet:
            pens = res.colors
            tail = f", {len(pens)} pens {' '.join(pens)}" if pens else ""
            c = doc["canvas"]
            print(f"[{os.path.basename(a.src)}] {w}x{h} -> scene {name!r}, "
                  f"{len(list(_walk_names(doc)))} elements on "
                  f"{c['width']:g}x{c['height']:g}{c['unit']}{tail}", file=sys.stderr)
        return 0

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
        pens = res.colors
        tail = f", {len(pens)} pens {' '.join(pens)}" if pens else ""
        print(f"[{os.path.basename(a.src)}] {w}x{h} -> {res.n_strokes} strokes"
              f" + {res.n_fills} fills, {res.n_segments} cubics, "
              f"stroke ~{res.stroke_width:.1f}px{tail}", file=sys.stderr)
    if a.check:
        ink = binarize(img, method=a.method, thresh=a.thresh,
                       flatten=a.flatten, denoise=a.denoise, invert=a.invert)
        m = compare(ink, rasterize(res, res.size))
        print(f"[check] iou={m['iou']:.3f} coverage={m['coverage']:.3f} "
              f"spill={m['spill']:.3f} d95={m['d95']:.1f}px", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
