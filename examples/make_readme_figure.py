"""Build the README figures.

    python examples/make_readme_figure.py

Writes two:

  docs/example.png    the lead: source beside traced vectors, side by side and
                      large enough to read. No metrics, no jargon -- it has one
                      job, which is to show that the output looks like the input.
  docs/roundtrip.png  the diagnostic: source, trace, and the difference between
                      them, for the cases the README's claims rest on.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lineart_trace import (binarize, compare, corpus, rasterize,   # noqa: E402
                           render, trace_image)

FIX = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")
LEAD = "beach.png"
# beach.png needs its fill threshold lowered; see the limitations table.
LEAD_OPTS = {"colors": 0, "thin_limit": 0.05}
DIAGNOSTIC = ["house", "photograph"]

PAD, LABEL, MARGIN = 18, 46, 10
FONT = cv2.FONT_HERSHEY_SIMPLEX
GREY, DARK = (125, 125, 125), (60, 60, 60)


def _label(width, text, scale=0.72, color=DARK, height=LABEL):
    """A caption strip, set large enough to actually read in a README."""
    strip = np.full((height, width, 3), 255, np.uint8)
    (tw, th), _ = cv2.getTextSize(text, FONT, scale, 2)
    cv2.putText(strip, text, (MARGIN, (height + th) // 2), FONT, scale,
                color, 2, cv2.LINE_AA)
    return strip


def _panel(img, title, sub=None, scale=0.72):
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    framed = cv2.copyMakeBorder(img, 1, 1, 1, 1, cv2.BORDER_CONSTANT,
                                value=(222, 222, 222))
    w = framed.shape[1]
    parts = [_label(w, title, scale)]
    if sub:
        parts.append(_label(w, sub, scale * 0.8, GREY, 34))
    return np.vstack(parts + [framed])


def _row(panels):
    h = max(p.shape[0] for p in panels)
    panels = [np.pad(p, ((0, h - p.shape[0]), (0, 0), (0, 0)),
                     constant_values=255) for p in panels]
    gap = np.full((h, PAD, 3), 255, np.uint8)
    out = [panels[0]]
    for p in panels[1:]:
        out += [gap, p]
    return np.hstack(out)


def _fit(img, width):
    if img.shape[1] == width:
        return img
    h = int(round(img.shape[0] * width / img.shape[1]))
    return cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)


def lead(out="docs/lead.png", panel_w=900):
    """Source beside output, as large as a README will show it."""
    path = os.path.join(FIX, LEAD)
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"skipping lead figure: {LEAD} not present")
        return None
    res = trace_image(img, **LEAD_OPTS)
    src = _fit(img[:, :, :3] if img.ndim == 3 else img, panel_w)
    got = _fit(render(res), panel_w)
    kb_in = os.path.getsize(path) // 1024
    kb_out = len(res.to_svg()) // 1024
    fig = _row([
        _panel(src, "raster in", f"{LEAD}  -  {kb_in} KB of pixels", 0.8),
        _panel(got, "vectors out",
               f"{res.n_fills} filled regions + {res.n_strokes} strokes, "
               f"{res.n_segments} curves  -  {kb_out} KB of SVG", 0.8),
    ])
    _write(out, fig)
    return res


def diagnostic(out="docs/roundtrip.png", panel_w=560):
    """Source, trace, and what differs -- the picture behind the numbers."""
    rows = []
    for name in DIAGNOSTIC:
        spec = corpus.build(name)
        res = trace_image(spec.image, **spec.hint)
        ren = rasterize(res, res.size, supersample=3)
        m = compare(spec.truth, ren)

        traced = np.full(spec.image.shape[:2], 255, np.uint8)
        traced[ren > 0] = 0
        diff = np.full(spec.image.shape[:2] + (3,), 255, np.uint8)
        t, r = spec.truth > 0, ren > 0
        diff[t & r] = (90, 170, 90)
        diff[t & ~r] = (60, 60, 220)
        diff[~t & r] = (220, 150, 60)

        src = spec.image
        if src.ndim == 3:
            src = cv2.cvtColor(src[:, :, :3], cv2.COLOR_BGR2GRAY)
        rows.append(_row([
            _panel(_fit(src, panel_w), f"{name}", "source"),
            _panel(_fit(traced, panel_w), "traced", f"{res.n_segments} curves"),
            _panel(_fit(diff, panel_w), "difference",
                   f"coverage {m['coverage']:.3f}   spill {m['spill']:.3f}"),
        ]))
        print(f"{name:12s} coverage={m['coverage']:.3f} spill={m['spill']:.3f}")
    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)),
                   constant_values=255) for r in rows]
    sep = np.full((PAD * 2, w, 3), 255, np.uint8)
    legend = _label(w, "green: matched    red: ink the trace missed    "
                       "blue: paint on blank paper", 0.62, GREY, 40)
    _write(out, np.vstack([rows[0], sep, rows[1], sep, legend]))


def _write(path, img):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    cv2.imwrite(path, img)
    print(f"wrote {path}  {img.shape[1]}x{img.shape[0]}  "
          f"{os.path.getsize(path) // 1024} KB")


def main(argv=None):
    res = lead()
    if res is not None:
        print(f"lead: {res.n_strokes} strokes, {res.n_fills} fills, "
              f"pens {res.colors}")
    diagnostic()
    return 0


if __name__ == "__main__":
    sys.exit(main())
