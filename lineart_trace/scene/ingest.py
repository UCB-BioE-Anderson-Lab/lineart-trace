"""The tracer, emitting named scene elements instead of a flat SVG. §3.10.

What changes here is not the tracing -- that is phase 0 and it is measured. What changes is
what comes out: a `TraceResult` is a list of curves with no names, no frame and no record of
where it came from, and phase 1's first line is that the tracer must emit a scene.

Three things the scene gets that the SVG never had:

**Names.** One group per pen, one element per path, numbered in the tracer's own order. So
"move the arrow" has something to address, which §1 lists as the second failure of
hand-written SVG.

**A frame.** The tracer works in image pixels; a figure is printed in millimetres. The scene
carries both: an ``art`` frame in px with the transform onto the page, so a recovered stroke
width of 5 px and a page rule of 1.2 pt are both expressible and neither is a guess.

**Provenance.** The source file and its SHA-256, the tool and its version, and the
parameters. That is what makes §4's "regenerate when the source art changes" a fact the
document knows rather than something a person remembers. No timestamp: determinism §4 means
a re-trace of unchanged art must produce an identical file, and a clock in the document
would break that on every run.
"""
import hashlib
import os

from .. import __version__
from . import model

__all__ = ["scene_from_trace", "sha256_of"]

_MM_PER_IN = 25.4


def sha256_of(path):
    """The digest of a file, or None if it cannot be read.

    None rather than a raised error: provenance that could not be taken is a scene with one
    field missing, and refusing to emit the trace over it would be a worse trade than saying
    so.
    """
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def _pen_name(color):
    """``#dc0000`` as the element name ``ink-dc0000``; the unnamed pen is ``ink``."""
    if not color:
        return "ink"
    return "ink-" + "".join(c for c in color.lower() if c in "0123456789abcdef")


def scene_from_trace(result, name="traced", source=None, params=None,
                     canvas_width=None, unit="mm", dpi=96.0, title=None):
    """A `TraceResult` as a scene document.

    `canvas_width` is the figure's width in `unit`; left out, the art is placed at `dpi`, so
    a 1254 px drawing at 96 dpi becomes a 331.7 mm page and the pixels keep their meaning.
    """
    if not model.NAME_RE.match(name):
        raise ValueError(f"not a usable scene name: {name!r}")
    w_px, h_px = result.size
    if canvas_width:
        scale = float(canvas_width) / float(w_px)       # unit per pixel
    else:
        per_in = 1.0 if unit == "in" else (_MM_PER_IN if unit == "mm"
                                           else _MM_PER_IN / 0.352777778 if unit == "pt"
                                           else 96.0)
        scale = per_in / float(dpi)
    doc = model.new(name, round(w_px * scale, 6), round(h_px * scale, 6), unit=unit,
                    title=title)
    doc["frames"]["art"] = {"parent": "page", "unit": "px",
                            "transform": [scale, 0.0, 0.0, scale, 0.0, 0.0]}

    prov = {"origin": "trace", "tool": "lineart.trace", "tool_version": __version__}
    if source:
        prov["source"] = source
        digest = sha256_of(source)
        if digest:
            prov["sha256"] = digest
    if params:
        prov["params"] = dict(params)

    root = {"name": "art", "type": "group", "frame": "art", "provenance": prov,
            "children": []}

    # ONE GROUP PER PEN, in the tracer's own most-used-first order. The order is the
    # tracer's, not a re-sort here: a second ordering rule is a second thing that can
    # disagree with the first, and this one has to be stable across runs for §4.
    pens = list(result.colors) or [None]
    buckets = {p: {"fills": [], "strokes": []} for p in pens}
    for f in result.fills:
        buckets.setdefault(f.color, {"fills": [], "strokes": []})["fills"].append(f)
    for s in result.strokes:
        buckets.setdefault(s.color, {"fills": [], "strokes": []})["strokes"].append(s)

    for pen in [p for p in pens if p in buckets] + [p for p in buckets if p not in pens]:
        bucket = buckets[pen]
        if not bucket["fills"] and not bucket["strokes"]:
            continue
        group = {"name": _pen_name(pen), "type": "group", "children": []}
        # Fills before strokes: the z-order the tracer's own SVG emitter uses, so the scene
        # renders the way the traced art already did.
        for i, f in enumerate(bucket["fills"], 1):
            loops = [_run(loop, close=True) for loop in f.loops]
            group["children"].append({
                "name": f"fill-{i:03d}", "type": "region",
                "style": {"fill": f.color or "#111111"},
                "geometry": {"kind": "region", "fill_rule": "evenodd", "loops": loops}})
        for i, s in enumerate(bucket["strokes"], 1):
            group["children"].append({
                "name": f"stroke-{i:03d}", "type": "path",
                "style": {"stroke": s.color or "#111111", "fill": "none",
                          "stroke_width": round(float(s.width), 6),
                          "stroke_cap": "round", "stroke_join": "round"},
                "geometry": {"kind": "path", "closed": bool(s.closed),
                             "d": _run(s.curves, close=bool(s.closed))}})
        root["children"].append(group)

    return model.add(doc, root)


def _run(curves, close=False):
    """A list of `Cubic` as scene segments: one M, then a C each, then Z if it closes.

    A `Cubic` is ``[p0, c1, c2, p3]`` of numpy points -- the fitter's own shape. Consecutive
    curves share an endpoint, so only the first contributes an M.
    """
    if not curves:
        return [["M", 0, 0]]
    p0 = curves[0][0]
    segs = [["M", float(p0[0]), float(p0[1])]]
    for c in curves:
        segs.append(["C", float(c[1][0]), float(c[1][1]), float(c[2][0]), float(c[2][1]),
                     float(c[3][0]), float(c[3][1])])
    if close:
        segs.append(["Z"])
    return segs
