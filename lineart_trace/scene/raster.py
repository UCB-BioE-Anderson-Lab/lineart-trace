"""A scene to pixels, for comparing figures rather than for looking at them.

**This is not the renderer.** SVG is the output anyone reads; this exists so that two
versions of a figure can be compared as images -- §3.14's visual regression -- and so that
"what changed" has an answer that is a picture rather than a diff of coordinates.

It is deliberately plain: paths are flattened, regions filled, strokes drawn with round caps.
No anti-aliasing subtleties, no text shaping -- a text element is drawn as its measured ink
box, which is enough to catch a label that moved or grew and honest about not being a
rendering of the glyphs. What it must be is **deterministic**, because a regression check
against a noisy rasteriser reports differences that are not there.
"""
import math

import numpy as np

from . import geometry, measure, model

__all__ = ["rasterize", "compare", "diff_image"]

_DEFAULTS = {"path": ("#111111", None), "region": (None, "#111111"),
             "text": (None, "#111111"), "image": (None, "#c0c0c0")}


def _rgb(colour, fallback=(17, 17, 17)):
    if not isinstance(colour, str) or not colour.startswith("#"):
        return fallback
    h = colour[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return fallback
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


def rasterize(doc, dpi=150.0, tol=0.06):
    """The scene as an RGB array at `dpi`. Shape ``(h, w, 3)``, uint8.

    Deterministic for a given scene and dpi: the same figure gives the same pixels, which is
    what a regression check needs to mean anything.
    """
    import cv2
    canvas = doc.get("canvas") or {}
    unit = canvas.get("unit", "mm")
    w_mm = model.to_unit(float(canvas.get("width", 1)), unit, "in")
    h_mm = model.to_unit(float(canvas.get("height", 1)), unit, "in")
    w = max(1, int(round(w_mm * dpi)))
    h = max(1, int(round(h_mm * dpi)))
    scale = w / float(canvas.get("width", 1) or 1)
    bg = canvas.get("background") or "#ffffff"
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = _rgb(bg, (255, 255, 255))[::-1]
    page = model._page_frame(doc)

    for addr, el, _p in model.walk(doc):
        if el.get("type") in ("group", "guide") or not el.get("geometry"):
            continue
        st = model.effective_style(doc, el)
        if float(st.get("opacity", 1.0)) <= 0.01:
            continue
        try:
            runs = measure.runs_in_frame(doc, addr, page)
        except measure.Unmeasurable:
            continue
        if not runs:
            continue
        kind = (el.get("geometry") or {}).get("kind")
        d_stroke, d_fill = _DEFAULTS.get(kind, (None, None))
        fill = st.get("fill", d_fill)
        stroke = st.get("stroke", d_stroke)
        polys = [np.array([[int(round(x * scale)), int(round(y * scale))] for x, y in p],
                          np.int32)
                 for p in geometry.flatten(runs, tol) if len(p) > 1]
        if not polys:
            continue
        if fill and fill != "none":
            cv2.fillPoly(img, polys, _rgb(fill)[::-1], lineType=cv2.LINE_AA)
        if stroke and stroke != "none":
            width = st.get("stroke_width")
            px = 1
            if width is not None:
                try:
                    n = model.resolve_length(doc, width, model.frame_of(doc, addr))
                    s = model.scale_of(model.element_to_page(doc, addr))
                    px = max(1, int(round(n * s * scale)))
                except (ValueError, KeyError):
                    px = 1
            closed = bool((el.get("geometry") or {}).get("closed")) or kind == "region"
            cv2.polylines(img, polys, closed, _rgb(stroke)[::-1], px,
                          lineType=cv2.LINE_AA)
    return img


def compare(a, b):
    """How two rasters differ. Returns a report; identical images give ``changed: 0``."""
    if a.shape != b.shape:
        return {"same_size": False, "shape_a": list(a.shape), "shape_b": list(b.shape),
                "why": "the two figures are different sizes, so their pixels cannot be "
                       "compared; that IS the difference"}
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    changed = int((d > 8).sum())
    total = int(d.size)
    ys, xs = np.nonzero(d > 8)
    box = None
    if changed:
        box = {"x0": int(xs.min()), "y0": int(ys.min()),
               "x1": int(xs.max()), "y1": int(ys.max())}
    return {"same_size": True, "pixels": total, "changed": changed,
            "fraction": changed / total if total else 0.0,
            "worst": int(d.max()), "region": box}


def diff_image(a, b, tint=(0, 0, 255)):
    """The two rasters overlaid, with what differs marked. For a person to look at."""
    out = ((a.astype(np.int16) + b.astype(np.int16)) // 2).astype(np.uint8)
    out = (out * 0.45 + 255 * 0.55).astype(np.uint8)
    if a.shape == b.shape:
        d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > 8
        out[d] = tint
    return out
