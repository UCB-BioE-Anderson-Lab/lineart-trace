"""Trace every corpus specimen, score the round trip, write a report.

    python examples/benchmark.py               # table to stdout
    python examples/benchmark.py --gallery docs/gallery.html
    python examples/benchmark.py --md docs/benchmark.md

The score is a round trip: vectorise, render the vectors back to a mask at the
source resolution, and compare with the ink that should have been there.
"""
import argparse, base64, io, json, os, sys, time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lineart_trace import corpus, compare, rasterize, trace_image   # noqa: E402


FIXTURES = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")


def real_specimens():
    """Real images from tests/fixtures, scored against their own ink.

    There is no independent ground truth for a real drawing, so the target is
    the binarised ink itself: the score says how faithfully the vectors
    reproduce what was on the page, not how well the page was thresholded.
    """
    from lineart_trace.binarize import binarize
    out = []
    if not os.path.isdir(FIXTURES):
        return out
    for fn in sorted(os.listdir(FIXTURES)):
        if not fn.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        img = cv2.imread(os.path.join(FIXTURES, fn), cv2.IMREAD_UNCHANGED)
        if img is None:
            continue
        out.append(corpus.Specimen(os.path.splitext(fn)[0], "real",
                                   img, binarize(img),
                                   "real drawing; target is its own ink"))
    return out


def run_one(spec, **kw):
    opts = dict(spec.hint)
    opts.update(kw)
    t0 = time.time()
    res = trace_image(spec.image, **opts)
    dt = time.time() - t0
    render = rasterize(res, res.size)
    m = compare(spec.truth, render)
    m.update(name=spec.name, category=spec.category, notes=spec.notes,
             paths=res.n_paths, strokes=res.n_strokes, fills=res.n_fills,
             segments=res.n_segments, seconds=dt,
             width=round(res.stroke_width, 1))
    return res, render, m


def _png_b64(img):
    ok, buf = cv2.imencode(".png", img)
    return base64.b64encode(buf).decode() if ok else ""


def _overlay(truth, render):
    """Green = matched, red = missed ink, blue = paint on blank paper."""
    h, w = truth.shape
    out = np.full((h, w, 3), 255, np.uint8)
    t, r = truth > 0, render > 0
    out[t & r] = (90, 170, 90)
    out[t & ~r] = (60, 60, 220)
    out[~t & r] = (220, 150, 60)
    return out


def gallery(rows, path, results):
    cards = []
    for m, (spec, res, render) in zip(rows, results):
        svg = res.to_svg(scale=1.0, background=None)
        cards.append(f"""
<article>
  <h3>{m['name']} <small>{m['category']}</small></h3>
  <p class="note">{m['notes']}</p>
  <div class="row">
    <figure><img src="data:image/png;base64,{_png_b64(spec.image)}"><figcaption>input</figcaption></figure>
    <figure class="svg">{svg}<figcaption>traced SVG</figcaption></figure>
    <figure><img src="data:image/png;base64,{_png_b64(_overlay(spec.truth, render))}"><figcaption>overlay</figcaption></figure>
  </div>
  <table><tr><th>IoU<td>{m['iou']:.3f}<th>coverage<td>{m['coverage']:.3f}
     <th>spill<td>{m['spill']:.3f}<th>d95<td>{m['d95']:.1f}px</tr>
   <tr><th>paths<td>{m['paths']}<th>strokes<td>{m['strokes']}<th>fills<td>{m['fills']}
     <th>cubics<td>{m['segments']}</tr></table>
</article>""")
    html = f"""<!doctype html><meta charset="utf-8">
<title>lineart-trace gallery</title>
<style>
 body{{font:14px/1.5 system-ui,sans-serif;margin:0;padding:24px;background:#fafafa;color:#111}}
 h1{{margin:0 0 4px}} .lede{{color:#555;max-width:60em}}
 article{{background:#fff;border:1px solid #e3e3e3;border-radius:8px;padding:16px;margin:18px 0}}
 h3{{margin:0 0 2px;font-size:16px}} h3 small{{color:#888;font-weight:400;margin-left:8px}}
 .note{{margin:0 0 10px;color:#666}}
 .row{{display:flex;gap:14px;flex-wrap:wrap}}
 figure{{margin:0;flex:1 1 200px;min-width:180px}}
 figure img,figure svg{{width:100%;height:auto;border:1px solid #eee;background:#fff;display:block}}
 figcaption{{color:#888;font-size:12px;padding-top:4px}}
 table{{margin-top:10px;border-collapse:collapse;font-size:13px}}
 th{{text-align:left;color:#777;font-weight:500;padding:2px 6px 2px 0}}
 td{{padding:2px 18px 2px 0;font-variant-numeric:tabular-nums}}
 .legend span{{display:inline-block;margin-right:14px}}
 .sw{{display:inline-block;width:11px;height:11px;border-radius:2px;vertical-align:-1px;margin-right:4px}}
</style>
<h1>lineart-trace &mdash; round-trip gallery</h1>
<p class="lede">Each specimen is vectorised, the vectors are rendered back to a
raster at the source resolution, and the two are compared. Overlay legend:
<span class="legend"><span><i class="sw" style="background:#5aaa5a"></i>matched</span>
<span><i class="sw" style="background:#dc3c3c"></i>ink the trace missed</span>
<span><i class="sw" style="background:#3c96dc"></i>paint on blank paper</span></span></p>
{''.join(cards)}"""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(html)
    return path


ORDER = ["primitive", "curve", "corner", "junction", "fill", "pattern",
         "drawing", "shading", "photo", "noise", "real"]

BLURB = {
    "primitive": "The simplest shapes, where any error has nowhere to hide.",
    "curve": "Smooth runs with no corner to cut the fit at.",
    "corner": "Sharp turns, which least squares wants to round off.",
    "junction": "Crossings, where the arms must meet at one point.",
    "fill": "Shapes with no centreline, which have to become contours.",
    "pattern": "Many strokes close together.",
    "drawing": "Ordinary line art: loops, junctions and curves at once.",
    "shading": "Tone rather than line. The honest answer is often 'no lines here'.",
    "photo": "A drawing photographed or scanned, not rendered.",
    "noise": "Damaged input: specks, dropouts, faint ink.",
    "real": "Actual drawings, scored against their own ink.",
}


def _grade(m):
    if m["coverage"] >= 0.97 and m["spill"] <= 0.02:
        return "faithful", "Reproduces the ink"
    if m["coverage"] >= 0.90:
        return "partial", "Some detail lost"
    return "limited", "Known limitation"


def _shrink(img, width=460):
    if img.shape[1] <= width:
        return img
    h = int(round(img.shape[0] * width / img.shape[1]))
    return cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)


def artifact(rows, path, results):
    """A publishable capability report: the corpus, sectioned and scored."""
    by_cat = {}
    for m, r in zip(rows, results):
        by_cat.setdefault(m["category"], []).append((m, r))

    ious = [m["iou"] for m in rows]
    covs = sorted(m["coverage"] for m in rows)
    spills = sorted(m["spill"] for m in rows)
    stats = [("specimens", f"{len(rows)}"),
             ("mean IoU", f"{np.mean(ious):.3f}"),
             ("median coverage", f"{covs[len(covs) // 2]:.3f}"),
             ("median spill", f"{spills[len(spills) // 2]:.3f}"),
             ("total cubics", f"{sum(m['segments'] for m in rows):,}")]

    sections = []
    for cat in ORDER:
        if cat not in by_cat:
            continue
        cards = []
        for m, (spec, res, render) in sorted(by_cat[cat],
                                             key=lambda kv: -kv[0]["coverage"]):
            grade, label = _grade(m)
            svg = res.to_svg(background=None).replace(
                "<svg ", '<svg preserveAspectRatio="xMidYMid meet" ', 1)
            cards.append(f"""
      <article class="card">
        <header class="card-head">
          <h3>{m['name']}</h3>
          <span class="chip chip-{grade}">{label}</span>
        </header>
        <p class="note">{m['notes']}</p>
        <div class="panels">
          <figure><div class="paper"><img alt="{m['name']} source"
            src="data:image/png;base64,{_png_b64(_shrink(spec.image))}"></div>
            <figcaption>source</figcaption></figure>
          <figure><div class="paper">{svg}</div>
            <figcaption>traced vectors</figcaption></figure>
          <figure><div class="paper"><img alt="{m['name']} overlay"
            src="data:image/png;base64,{_png_b64(_shrink(_overlay(spec.truth, render)))}"></div>
            <figcaption>overlay</figcaption></figure>
        </div>
        <dl class="stats">
          <div><dt>coverage</dt><dd>{m['coverage']:.3f}</dd></div>
          <div><dt>spill</dt><dd>{m['spill']:.3f}</dd></div>
          <div><dt>IoU</dt><dd>{m['iou']:.3f}</dd></div>
          <div><dt>d95</dt><dd>{m['d95']:.1f}px</dd></div>
          <div><dt>paths</dt><dd>{m['paths']}</dd></div>
          <div><dt>cubics</dt><dd>{m['segments']}</dd></div>
        </dl>
      </article>""")
        sections.append(f"""
    <section class="cat" id="{cat}">
      <div class="cat-head">
        <h2>{cat}</h2>
        <p>{BLURB.get(cat, '')}</p>
        <span class="count">{len(by_cat[cat])}</span>
      </div>
      <div class="grid">{''.join(cards)}</div>
    </section>""")

    nav = "".join(f'<a href="#{c}">{c}</a>' for c in ORDER if c in by_cat)
    tiles = "".join(f'<div class="stat"><span class="k">{k}</span>'
                    f'<span class="v">{v}</span></div>' for k, v in stats)

    html = f"""<title>Centreline Trace Atlas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
  :root {{
    --paper:#fbfaf8; --raise:#ffffff; --ink:#17161b; --dim:#5f5b54;
    --rule:#e4dfd6; --accent:#2f4b7c; --accent-soft:#e8edf6;
    --good:#4a7f4a; --miss:#b8402f; --spill:#3a7ca5;
    --plate:#ffffff; --plate-rule:#dcd7cd;
    --display:"Newsreader",Georgia,"Times New Roman",serif;
    --body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
    --mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --paper:#141419; --raise:#1c1c23; --ink:#e9e6df; --dim:#9a948a;
      --rule:#2e2e38; --accent:#8aa9de; --accent-soft:#232a3a;
      --good:#6faa6f; --miss:#d9695a; --spill:#5fa0c6;
    }}
  }}
  :root[data-theme="dark"] {{
    --paper:#141419; --raise:#1c1c23; --ink:#e9e6df; --dim:#9a948a;
    --rule:#2e2e38; --accent:#8aa9de; --accent-soft:#232a3a;
    --good:#6faa6f; --miss:#d9695a; --spill:#5fa0c6;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
         font-family:var(--body); font-size:15px; line-height:1.6; }}
  .wrap {{ max-width:1160px; margin:0 auto; padding:48px 24px 96px; }}

  .lede {{ border-bottom:1px solid var(--rule); padding-bottom:32px; }}
  .eyebrow {{ font-family:var(--mono); font-size:11px; letter-spacing:.14em;
              text-transform:uppercase; color:var(--accent); margin:0 0 12px; }}
  h1 {{ font-family:var(--display); font-weight:600; font-size:clamp(34px,5vw,54px);
        line-height:1.08; letter-spacing:-.015em; margin:0 0 14px;
        text-wrap:balance; }}
  .lede p {{ max-width:64ch; color:var(--dim); margin:0 0 10px; font-size:16px; }}
  .lede strong {{ color:var(--ink); font-weight:500; }}

  .stats-band {{ display:flex; flex-wrap:wrap; gap:2px; margin:28px 0 0;
                 background:var(--rule); border:1px solid var(--rule);
                 border-radius:3px; overflow:hidden; }}
  .stat {{ flex:1 1 150px; background:var(--raise); padding:14px 16px;
           display:flex; flex-direction:column; gap:2px; }}
  .stat .k {{ font-family:var(--mono); font-size:10.5px; letter-spacing:.1em;
              text-transform:uppercase; color:var(--dim); }}
  .stat .v {{ font-family:var(--display); font-size:26px; font-weight:600;
              font-variant-numeric:tabular-nums; }}

  .legend {{ display:flex; flex-wrap:wrap; gap:18px; margin:24px 0 0;
             font-size:13px; color:var(--dim); }}
  .legend b {{ display:inline-block; width:10px; height:10px; border-radius:2px;
               margin-right:6px; vertical-align:0; }}

  nav {{ position:sticky; top:0; z-index:5; display:flex; flex-wrap:wrap;
         gap:4px; padding:12px 0; margin:0 0 8px;
         background:var(--paper); border-bottom:1px solid var(--rule); }}
  nav a {{ font-family:var(--mono); font-size:11.5px; letter-spacing:.06em;
           text-transform:uppercase; text-decoration:none; color:var(--dim);
           padding:5px 10px; border-radius:3px; }}
  nav a:hover, nav a:focus-visible {{ color:var(--accent);
           background:var(--accent-soft); outline:none; }}
  nav a:focus-visible {{ box-shadow:0 0 0 2px var(--accent); }}

  .cat {{ padding-top:44px; scroll-margin-top:64px; }}
  .cat-head {{ display:flex; align-items:baseline; gap:14px;
               border-bottom:1px solid var(--rule); padding-bottom:10px; }}
  .cat-head h2 {{ font-family:var(--display); font-weight:600; font-size:27px;
                  margin:0; letter-spacing:-.01em; }}
  .cat-head p {{ margin:0; color:var(--dim); font-size:14px; flex:1 1 240px; }}
  .cat-head .count {{ font-family:var(--mono); font-size:12px; color:var(--dim);
                      font-variant-numeric:tabular-nums; }}

  .grid {{ display:grid; gap:20px; margin-top:20px;
           grid-template-columns:repeat(auto-fill,minmax(430px,1fr)); }}
  .card {{ background:var(--raise); border:1px solid var(--rule);
           border-radius:4px; padding:16px 16px 4px; }}
  .card-head {{ display:flex; align-items:center; gap:10px; }}
  .card-head h3 {{ font-family:var(--mono); font-size:13.5px; font-weight:500;
                   margin:0; letter-spacing:.01em; flex:1; }}
  .chip {{ font-family:var(--mono); font-size:10px; letter-spacing:.08em;
           text-transform:uppercase; padding:3px 8px; border-radius:2px;
           white-space:nowrap; border:1px solid currentColor; }}
  .chip-faithful {{ color:var(--good); }}
  .chip-partial {{ color:var(--spill); }}
  .chip-limited {{ color:var(--miss); }}
  .note {{ margin:6px 0 12px; font-size:13px; color:var(--dim); }}

  .panels {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
  .panels figure {{ margin:0; min-width:0; }}
  /* The panels are reproductions of ink on paper: they keep a paper ground in
     both themes, because inverting a drawing is not the same drawing. */
  .paper {{ background:var(--plate); border:1px solid var(--plate-rule);
            border-radius:2px; aspect-ratio:4/3; display:flex;
            align-items:center; justify-content:center; overflow:hidden;
            padding:4px; }}
  .paper img, .paper svg {{ max-width:100%; max-height:100%;
            width:auto; height:auto; display:block; }}
  .panels figcaption {{ font-family:var(--mono); font-size:10px;
            letter-spacing:.08em; text-transform:uppercase; color:var(--dim);
            padding-top:5px; }}

  .stats {{ display:flex; flex-wrap:wrap; gap:0 22px; margin:12px 0 0;
            padding:10px 0 12px; border-top:1px solid var(--rule); }}
  .stats div {{ display:flex; flex-direction:column; }}
  .stats dt {{ font-family:var(--mono); font-size:9.5px; letter-spacing:.08em;
               text-transform:uppercase; color:var(--dim); }}
  .stats dd {{ margin:0; font-family:var(--mono); font-size:14px;
               font-variant-numeric:tabular-nums; }}

  .footnote {{ margin-top:56px; padding-top:24px;
               border-top:1px solid var(--rule); color:var(--dim);
               font-size:14px; max-width:66ch; }}
  .footnote h2 {{ font-family:var(--display); font-size:22px; color:var(--ink);
                  margin:0 0 10px; font-weight:600; }}
  .footnote code {{ font-family:var(--mono); font-size:12.5px;
                    background:var(--accent-soft); color:var(--accent);
                    padding:1px 5px; border-radius:2px; }}
  @media (max-width:640px) {{
    .panels {{ grid-template-columns:1fr; }}
    .grid {{ grid-template-columns:1fr; }}
  }}
</style>
<div class="wrap">
  <div class="lede">
    <p class="eyebrow">lineart-trace &middot; round-trip survey</p>
    <h1>Centreline Trace Atlas</h1>
    <p>Every specimen below is vectorised into SVG cubic B&eacute;ziers, then the
    vectors are <strong>rendered back to a raster</strong> at the source
    resolution and compared with the ink that should have been there. Nothing
    here is an impression of quality; it is a measurement, and the cases that
    do badly are kept in rather than left out.</p>
    <p>Read <strong>coverage</strong> (how much of the original ink came back)
    and <strong>spill</strong> (how much paint landed on blank paper). IoU is a
    sub-pixel registration score and punishes thin strokes hard &mdash; the same
    drawing at 3px scores 0.88 and at 20px scores 0.95 with identical geometry.</p>
    <div class="stats-band">{tiles}</div>
    <p class="legend">
      <span><b style="background:var(--good)"></b>matched</span>
      <span><b style="background:var(--miss)"></b>ink the trace missed</span>
      <span><b style="background:var(--spill)"></b>paint on blank paper</span>
    </p>
  </div>
  <nav>{nav}</nav>
  {''.join(sections)}
  <div class="footnote">
    <h2>Where it breaks</h2>
    <p>Stipple and halftone have no centreline at all &mdash; dots come back as
    small filled regions, and touching dots merge, so the count falls short of
    what was drawn. Grey washes are tone, not line: they binarise away rather
    than inventing strokes. Lettering loses small counters and thin serifs.
    Crossings under about 15&deg; resolve as two junctions with a short piece
    between them. Each of these is a specimen above with a recorded floor in
    <code>tests/test_corpus.py</code>, not an untested caveat.</p>
  </div>
</div>"""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(html)
    return path


def markdown(rows):
    out = ["| specimen | category | IoU | coverage | spill | d95 px | paths | cubics |",
           "|---|---|---:|---:|---:|---:|---:|---:|"]
    for m in rows:
        out.append(f"| `{m['name']}` | {m['category']} | {m['iou']:.3f} | "
                   f"{m['coverage']:.3f} | {m['spill']:.3f} | {m['d95']:.1f} | "
                   f"{m['paths']} | {m['segments']} |")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gallery"); ap.add_argument("--md"); ap.add_argument("--json")
    ap.add_argument("--artifact", help="publishable capability report (body-only HTML)")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)

    specs = corpus.build_all() + real_specimens()
    if a.only:
        specs = [s for s in specs if s.name in a.only]
    rows, results = [], []
    for s in specs:
        res, render, m = run_one(s)
        rows.append(m); results.append((s, res, render))
        print(f"{m['name']:18s} {m['category']:10s} iou={m['iou']:.3f} "
              f"cov={m['coverage']:.3f} spill={m['spill']:.3f} "
              f"d95={m['d95']:5.1f} paths={m['paths']:4d} cubics={m['segments']:5d} "
              f"{m['seconds']:.2f}s")
    ious = [m["iou"] for m in rows]
    print(f"\n{len(rows)} specimens  mean IoU {np.mean(ious):.3f}  "
          f"median {np.median(ious):.3f}  worst {min(ious):.3f} "
          f"({rows[int(np.argmin(ious))]['name']})")
    if a.gallery:
        print("wrote", gallery(rows, a.gallery, results))
    if a.artifact:
        print("wrote", artifact(rows, a.artifact, results))
    if a.md:
        os.makedirs(os.path.dirname(os.path.abspath(a.md)) or ".", exist_ok=True)
        open(a.md, "w").write(markdown(rows) + "\n")
        print("wrote", a.md)
    if a.json:
        open(a.json, "w").write(json.dumps(rows, indent=1, default=float))
        print("wrote", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
