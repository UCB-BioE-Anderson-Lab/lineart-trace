"""Build the README figure: source, traced vectors, and the difference.

    python examples/make_readme_figure.py docs/example.png

Everything it draws comes from `lineart_trace.corpus`, so the figure is
reproducible from the repository alone -- no sample image to ship.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lineart_trace import compare, corpus, rasterize, trace_image   # noqa: E402

PANELS = ["house", "photograph"]
REAL = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures",
                    "polymerase.png")
PAD, LABEL_H = 14, 26


def _panel(gray, title):
    img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    strip = np.full((LABEL_H, img.shape[1], 3), 255, np.uint8)
    cv2.putText(strip, title, (2, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                (110, 110, 110), 1, cv2.LINE_AA)
    return np.vstack([strip, img])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out = argv[0] if argv else "docs/example.png"
    specs = [corpus.build(n) for n in PANELS]
    if os.path.exists(REAL):
        img = cv2.imread(REAL, cv2.IMREAD_UNCHANGED)
        from lineart_trace import binarize
        specs.append(corpus.Specimen("polymerase", "real", img, binarize(img),
                                     "a real drawing", {"colors": 0}))
    rows = []
    for spec in specs:
        name = spec.name
        res = trace_image(spec.image, **spec.hint)
        render = rasterize(res, res.size, supersample=3)
        m = compare(spec.truth, render)

        shape = spec.image.shape[:2]
        traced = np.full(shape, 255, np.uint8)
        traced[render > 0] = 0
        diff = np.full(shape + (3,), 255, np.uint8)
        t, r = spec.truth > 0, render > 0
        diff[t & r] = (90, 170, 90)
        diff[t & ~r] = (60, 60, 220)
        diff[~t & r] = (220, 150, 60)

        src = spec.image
        if src.ndim == 3:
            src = cv2.cvtColor(src[:, :, :3], cv2.COLOR_BGR2GRAY)
        cells = [_panel(src, f"{name}  (source)"),
                 _panel(traced, f"traced: {res.n_strokes} strokes, "
                                f"{res.n_fills} fills, {res.n_segments} cubics"),
                 np.vstack([np.full((LABEL_H, diff.shape[1], 3), 255, np.uint8),
                            diff])]
        cv2.putText(cells[2], f"coverage {m['coverage']:.3f}   "
                              f"spill {m['spill']:.3f}   IoU {m['iou']:.3f}",
                    (2, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (110, 110, 110),
                    1, cv2.LINE_AA)
        gap = np.full((cells[0].shape[0], PAD, 3), 255, np.uint8)
        rows.append(np.hstack([cells[0], gap, cells[1], gap, cells[2]]))
        print(f"{name:12s} coverage={m['coverage']:.3f} spill={m['spill']:.3f} "
              f"iou={m['iou']:.3f}")

    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)),
                   constant_values=255) for r in rows]
    sep = np.full((PAD * 2, w, 3), 255, np.uint8)
    fig = np.vstack([rows[0]] + [x for r in rows[1:] for x in (sep, r)])
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    cv2.imwrite(out, fig)
    print("wrote", out, fig.shape)
    return 0


if __name__ == "__main__":
    sys.exit(main())
