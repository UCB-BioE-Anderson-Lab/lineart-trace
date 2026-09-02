import argparse, sys
from .trace import trace_file

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="lineart-trace",
        description="Vectorise black-on-white line art into centreline SVG Beziers.")
    p.add_argument("src")
    p.add_argument("--width", type=float, default=0.0,
                   help="target width in output units (default: source pixels)")
    p.add_argument("--x", type=float, default=0.0)
    p.add_argument("--y", type=float, default=0.0)
    p.add_argument("--thresh", type=int, default=200, help="ink cutoff 0-255")
    p.add_argument("--error", type=float, default=1.0,
                   help="Bezier fit tolerance in source pixels")
    p.add_argument("--prune", type=float, default=14.0,
                   help="drop dead-end chains shorter than this")
    p.add_argument("--close", type=int, default=0,
                   help="morphological close radius; bridges antialias breaks")
    p.add_argument("--stroke", type=float, default=None, help="override stroke width")
    p.add_argument("--color", default="#111111")
    p.add_argument("--svg", action="store_true", help="emit a standalone SVG document")
    a = p.parse_args(argv)

    r = trace_file(a.src, thresh=a.thresh, error=a.error, prune=a.prune, close=a.close)
    w, h = r.size
    scale = (a.width / w) if a.width else 1.0
    g = r.to_svg_group(scale, a.x, a.y, a.color, a.stroke)
    if a.svg:
        print(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w*scale:.0f}" '
              f'height="{h*scale:.0f}" viewBox="0 0 {w*scale:.0f} {h*scale:.0f}">'
              f'<rect width="100%" height="100%" fill="#fff"/>{g}</svg>')
    else:
        print(g)
    print(f"[{a.src}] {w}x{h} -> {r.n_paths} paths, {r.n_segments} cubics, "
          f"stroke ~{r.stroke_width:.1f}px", file=sys.stderr)

if __name__ == "__main__":
    main()
