"""What the scene format costs, on the largest drawing in the repository.

Two decisions in phase 1 were taken with a cost attached and no number: **JSON only** -- a
figure of a few thousand Beziers becomes a large text file -- and **a new document per
transform** -- every scene tool deep-copies rather than mutating. Both are the right trade
for a format a model has to read and a toolkit with no session, and a trade without a
measurement is a hope.

So this measures them, on `examples/beach.png`: the traced scene's size against the SVG the
same trace emits, and the wall-clock of a load / transform / write round trip against the
trace that produced it.

    python3 examples/scene_cost.py [--image examples/beach.png] [--repeat 5]
"""
import argparse
import gzip
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2                                                        # noqa: E402

from lineart_trace import trace_image                             # noqa: E402
from lineart_trace.scene import ingest, io, model, svg, validate   # noqa: E402


def timed(fn, repeat):
    """Best of `repeat`, in milliseconds. Best, not mean: the slow runs are the machine."""
    out = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000.0)
    return min(out), statistics.median(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", default="examples/beach.png")
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--colors", type=int, default=0)
    p.add_argument("--keep", help="write the scene here and leave it")
    a = p.parse_args(argv)

    img = cv2.imread(a.image, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"scene_cost: cannot read {a.image}", file=sys.stderr)
        return 2

    t = time.perf_counter()
    res = trace_image(img, colors=a.colors)
    trace_ms = (time.perf_counter() - t) * 1000.0

    doc = ingest.scene_from_trace(res, name="beach", source=a.image, canvas_width=180,
                                  params={"colors": a.colors})
    text = io.dumps(doc)
    group = res.to_svg_group(1.0, 0.0, 0.0)
    n_elements = len(model.addresses(doc))

    def round_trip():
        d = io.loads(text)
        d, _n = model.rename(d, "art", "drawing")
        io.dumps(d)

    rt_best, rt_med = timed(round_trip, a.repeat)
    parse_best, _ = timed(lambda: io.loads(text), a.repeat)
    write_best, _ = timed(lambda: io.dumps(doc), a.repeat)
    val_best, _ = timed(lambda: validate.problems(doc), a.repeat)
    svg_best, _ = timed(lambda: svg.render(doc), a.repeat)

    bad, warn = validate.problems(doc)
    kb = len(text.encode()) / 1024.0
    gz = len(gzip.compress(text.encode())) / 1024.0

    print(f"[{os.path.basename(a.image)}] {res.size[0]}x{res.size[1]}, "
          f"{res.n_strokes} strokes + {res.n_fills} fills, {res.n_segments} cubics, "
          f"{len(res.colors)} pens")
    print(f"  scene         {n_elements} elements, {kb:,.0f} KB "
          f"({gz:,.0f} KB gzipped)")
    print(f"  tracer's svg  {len(group) / 1024.0:,.0f} KB  "
          f"-> scene is {len(text) / max(len(group), 1):.2f}x that")
    print(f"  conforms      {'yes' if not bad else str(len(bad)) + ' problems'}"
          f"{', ' + str(len(warn)) + ' warnings' if warn else ''}")
    print(f"  trace         {trace_ms:,.0f} ms   (the thing this all hangs off)")
    print(f"  parse         {parse_best:,.1f} ms")
    print(f"  write         {write_best:,.1f} ms")
    print(f"  round trip    {rt_best:,.1f} ms best, {rt_med:,.1f} median "
          f"(parse + a copying transform + write)")
    print(f"  validate      {val_best:,.1f} ms")
    print(f"  render svg    {svg_best:,.1f} ms")
    if a.keep:
        io.dump(doc, a.keep)
        print(f"  kept          {a.keep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
