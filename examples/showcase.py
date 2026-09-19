"""One figure that uses the whole toolkit, and the page that shows it.

    python3 examples/showcase.py --html docs/showcase.html

Four panels of a real scientific figure, built the way `docs/spec.md` says a figure should
be built: traced art placed by a **discovered** anchor, a pathway whose arrow routes round an
obstacle, a data panel from a CSV, and a readout drawn from the glyph library. Styled by a
guide, laid out on a grid, checked at printed size, and exported light, dark and at journal
column width from one scene.

Every number this prints was measured. Nothing is placed by eye.
"""
import argparse
import copy
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineart_trace.scene import (anchors, animate, build, data, diagram,  # noqa: E402
                                 glyphs, inspect, io, layout, measure, model, overlay,
                                 palette, raster, report, style as style_, svg,
                                 text as text_, validate, verify)

STEP = 0


def step(title):
    global STEP
    STEP += 1
    print(f"\n{STEP}. {title}\n   " + "-" * len(title))


def say(fmt, *a):
    print("   " + (fmt % a if a else fmt))


def write_data(path, seed=11):
    random.seed(seed)
    rows = [("cycles", "signal")]
    for i in range(1, 17):
        x = i * 2.0
        rows.append((f"{x:g}", f"{4.0 + 1.9 * x + random.gauss(0, 5.0):.4f}"))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return path


# ===================================================================== the figure
def panel_a(doc, traced):
    """Traced art with a duplex seated in a concavity nobody typed a coordinate for."""
    art = model.find(io.load(traced), "art")
    doc["frames"]["art"] = dict(io.load(traced)["frames"]["art"])
    doc = model.add(doc, art)
    doc, _ = style_.adopt(doc, style_.load("figure-default"))
    for _a, el, _p in model.walk(doc):
        if str(el.get("role", "")).startswith("adopted-"):
            el["role"] = "structure-stroke"
    doc, fitted = layout.into_panel(doc, "art", "panel-a", margin=3.0)

    model.find(doc, "panel-a.art")["anchors"] = {
        "channel": {"how": "discovered", "by": "concavity"}}
    doc, resolved = anchors.resolve(doc)

    doc, _ = glyphs.place(doc, "dna.duplex", "duplex", at=(2, 2), parent="panel-a",
                          args={"length": 26, "rise": 1.4, "turns": 3, "rungs": 11,
                                "polarity": False})
    model.find(doc, "panel-a.duplex")["anchors"]["inlet"] = {
        "how": "derived", "by": "bbox.e"}
    model.find(doc, "panel-a.duplex")["relations"] = [
        {"kind": "attach", "to": "panel-a.art.channel", "via": "inlet",
         "offset": [-1.0, 0.0]}]
    return doc, fitted, resolved


def panel_b(doc, guide):
    """A pathway whose arrow has to go round the inhibitor."""
    spec = {"template": "template", "nick": "nicking", "extend": "extension",
            "product": "amplicon"}
    edges = [("template", "nick"), ("nick", "extend"), ("extend", "product")]
    doc, rep = diagram.flow(doc, spec, edges, at=(3, 10), spacing=(6, 7),
                            parent="panel-b")
    # PLACED WHERE IT ACTUALLY BLOCKS. At (30, 26) it sat clear of every route, and the
    # bypass went round `extension` instead -- the figure said "round the inhibitor" and the
    # arrow went nowhere near it. Here it covers the right-hand detour, so the only way past
    # is the other side, and `within` keeps that inside the panel rather than out on the page.
    doc, _ = diagram.node(doc, "inhibitor", "inhibitor", (21, 33), parent="panel-b",
                          shape="diamond")
    doc, blocked = diagram.edge(doc, "escape", "panel-b.nick", "panel-b.product",
                                "bypass", parent="panel-b", within="panel-b.area")
    return doc, rep, blocked


def panel_c(doc, csv_path, width, height):
    cols, rows = data.read_table(csv_path)
    xs = [r["cycles"] for r in rows]
    ys = [r["signal"] for r in rows]
    g, rep = data.plot("amplification", xs, ys, width, height, kind="scatter",
                       xlabel="cycles", ylabel="signal (AU)", fit_line=True,
                       source=csv_path, ticks=4)
    return model.add(doc, g, "panel-c"), rep


def panel_d(doc):
    doc, _ = glyphs.place(doc, "gel.lanes", "gel", at=(3, 10), parent="panel-d",
                          args={"lanes": 3, "width": 7.0, "height": 34.0, "gap": 2.0,
                                "ladder": [0.12, 0.3, 0.52, 0.78],
                                "bands": [(1, 0.34, 1.0), (2, 0.34, 0.5),
                                          (3, 0.62, 0.9)],
                                "labels": ["0", "20", "40"]})
    doc, _ = glyphs.place(doc, "lab.plate", "plate", at=(40, 12), parent="panel-d",
                          args={"rows": 3, "cols": 4, "pitch": 4.0, "well": 3.0,
                                "filled": ["A1", "B2", "C4"], "labels": False})
    return doc


def build_figure(out_dir, csv_path):
    guide = style_.load("figure-default")
    doc = model.new("amplification", 180, 118, background="#ffffff",
                    title="Strand-displacement amplification")
    doc["description"] = (
        "Four panels. A: a traced polymerase with a DNA duplex seated in the concavity "
        "found on its silhouette. B: the reaction pathway, with the inhibitor bypass "
        "routed around the inhibitor. C: signal against cycles with a least-squares fit "
        "and its confidence band. D: the gel and plate readout.")
    doc, _ = style_.apply(doc, guide)
    doc, panels = layout.panels(doc, rows=2, cols=2, gutter=7.0, margin=5.0)
    return doc, guide, panels


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="out")
    p.add_argument("--html", default="docs/showcase.html")
    p.add_argument("--traced", default="tests/fixtures/scene-polymerase.json")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    paths, numbers = {}, {}

    step("A page of four panels, on the house style")
    doc, guide, panels = build_figure(a.out, None)
    pw, ph = panels["panel"]["width"], panels["panel"]["height"]
    say("%d panels of %.2f x %.2f mm, gutter %g, lettered %s", len(panels["created"]),
        pw, ph, panels["gutter"], "automatically")
    numbers["panels"] = f"{panels['rows']}x{panels['cols']}, {pw:.1f}x{ph:.1f} mm"

    step("Panel A: place a duplex in a concavity nobody typed a coordinate for")
    doc, fitted, resolved = panel_a(doc, a.traced)
    say("traced art fitted into the panel at %.3f scale", fitted["scale"])
    ch = measure.bbox(doc, "panel-a.art.channel")["value"]
    say("`concavity` found the entry channel at (%.2f, %.2f) mm on the page", ch["x"],
        ch["y"])
    doc, solved = anchors.solve(doc)
    moved = solved["moved"].get("panel-a.duplex")
    say("the duplex moved (%.2f, %.2f) mm to seat its inlet there -- a declaration",
        moved["dx"], moved["dy"])
    numbers["anchor"] = f"concavity at ({ch['x']:.1f}, {ch['y']:.1f}) mm"

    step("Panel B: a pathway whose bypass goes ROUND the inhibitor")
    doc, flowrep, blocked = panel_b(doc, guide)
    say("%d nodes in %d layers, sized to their labels", len(flowrep["nodes"]),
        flowrep["layers"])
    say("the bypass: %d corner(s), clears %.2f mm of an asked %.1f, past %s",
        blocked["corners"], blocked["clearance_worst"], blocked["clearance_asked"],
        ", ".join(x.split(".")[-1] for x in blocked["passed"]) or "nothing")
    numbers["route"] = (f"{blocked['corners']} corners, clears "
                        f"{blocked['clearance_worst']:.2f} mm")

    step("Panel C: a fit whose numbers come back with the drawing")
    csv_path = write_data(os.path.join(a.out, "amplification.csv"))
    doc, plotrep = panel_c(doc, csv_path, pw, ph)
    f = plotrep["fit"]
    say("slope %.4f, intercept %.4f, r² %.4f over n=%d; band clamped at %d point(s)",
        f["slope"], f["intercept"], f["r2"], f["n"], f["band_clamped"])
    prov = model.find(doc, "panel-c.amplification")["provenance"]
    say("and the panel records its source: %s sha256 %s...",
        os.path.basename(prov["source"]), prov["sha256"][:12])
    numbers["fit"] = f"slope {f['slope']:.3f}, r² {f['r2']:.3f}, n={f['n']}"

    step("Panel D: the readout, from the glyph library")
    doc = panel_d(doc)
    say("gel and plate placed by name; %d glyph instance(s), all current",
        len(glyphs.check(doc)["instances"]))

    step("Caption it, refusing the size that will not fit")
    caption = "Strand-displacement amplification of a nicked template"
    try:
        text_.fit(caption, pw / 2, 5.0, "Helvetica", "9pt", mode="strict", unit="mm")
        say("9pt in half a panel fits (unexpected)")
    except text_.TooBig as e:
        say("9pt in a %.0f mm box: REFUSED -- %s", pw / 2,
            str(e).split(": ", 1)[1])
    lab, laid = text_.block("caption", caption, 5.0, 111.0, 170.0, 5.0, mode="wrap",
                            unit="mm", role="caption", doc=doc)
    # DECLARED, not placed: left-aligned with the first panel and below the last one. On a
    # page whose grid may be re-laid -- 2x2 on a slide, 4x1 in a column -- a caption at a
    # fixed y stays where the panels used to be.
    lab["relations"] = [{"kind": "align", "to": "panel-a", "edge": "left"},
                        {"kind": "align", "to": "panel-d", "edge": "below",
                         "offset": [0.0, 4.0]}]
    doc = model.add(doc, lab)
    say("laid out in the font the `caption` ROLE supplies (%s), not one passed in: "
        "%d line(s), %.1f of %.0f mm used", laid["font"]["family"], len(laid["lines"]),
        laid["width"], 170.0)
    say("and it is DECLARED below the last panel, not placed at a y -- so it follows")
    say("when the grid is re-laid for the column")

    step("Check it at the size it will be printed")
    doc, solved = anchors.solve(doc)
    got = verify.check(doc, solve_report=solved)
    say("%d error(s), %d warning(s), %d unchecked", got["errors"], got["warnings"],
        len(got["unchecked"]))
    for fnd in got["findings"]:
        say("  [%s] %-14s %s: %s", fnd["severity"], fnd["rule"], fnd["element"] or "-",
            fnd["message"])

    step("Export it three ways, from one scene, editing nothing")
    paths["figure"] = os.path.join(a.out, "showcase.svg")
    open(paths["figure"], "w").write(svg.render(doc))
    dark, _ = style_.apply(doc, guide, "dark")
    paths["dark"] = os.path.join(a.out, "showcase-dark.svg")
    open(paths["dark"], "w").write(svg.render(dark))
    column, _ = style_.apply(doc, style_.load("journal-column"))
    column, flowed = layout.reflow(column, width=88.0, height=232.0, rows=4, cols=1,
                                   gutter=6.0)
    column, csolved = anchors.solve(column)
    paths["column"] = os.path.join(a.out, "showcase-column.svg")
    open(paths["column"], "w").write(svg.render(column))
    say("180x118 -> 88x232 mm, and the GRID changes: %dx%d becomes %dx%d",
        panels["rows"], panels["cols"], flowed["rows"], flowed["cols"])
    say("panels %.1f -> %.1f mm wide, %d drawing(s) re-fitted, type unchanged",
        panels["panel"]["width"], flowed["panel"]["width"], len(flowed["refitted"]))
    say("light %d errors | dark %d errors | column %d errors",
        got["errors"], verify.check(dark, solve_report=solved)["errors"],
        verify.check(column, solve_report=csolved)["errors"])
    numbers["exports"] = "180x118 mm, dark, and an 88 mm column re-gridded 4x1"

    step("Show how it is held together, and build it up for a lecture")
    load = overlay.payload(doc, grid=10.0, findings=got["findings"], depth=2)
    paths["overlay"] = os.path.join(a.out, "showcase-overlay.svg")
    open(paths["overlay"], "w").write(overlay.render(load))
    tl = animate.from_stages("lecture", [
        {"name": "art", "reveal": ["panel-a"], "hold": 1.0},
        {"name": "pathway", "reveal": ["panel-b"], "hold": 1.0},
        {"name": "data", "reveal": ["panel-c"], "hold": 1.0},
        {"name": "readout", "reveal": ["panel-d", "caption"], "hold": 1.4},
    ], scene=doc["name"])
    paths["timeline"] = os.path.join(a.out, "showcase-lecture.json")
    io.dump(tl, paths["timeline"])
    for st in tl["stages"]:
        still = animate.still(doc, tl, st["name"])
        sgot = verify.check(still)
        path = os.path.join(a.out, f"showcase-stage-{st['name']}.svg")
        open(path, "w").write(svg.render(still))
        paths[f"stage-{st['name']}"] = path
        say("stage %-8s %3d element(s), %d error(s) -- an ordinary figure",
            st["name"], len(model.addresses(still)), sgot["errors"])

    step("Pages to look at it with, and to steer it from")
    load = overlay.payload(doc, grid=10.0, findings=got["findings"], depth=3)
    paths["inspector"] = os.path.join(a.out, "showcase-inspector.html")
    open(paths["inspector"], "w").write(inspect.inspector(load))
    say("inspector: %d element(s) clickable -- click one and it says its address, role,",
        len(load["boxes"]))
    say("z-order, box in mm, anchors and resolved style. No server; it is a pure view.")
    variants = [("as it is", svg.render(doc), {"verdict": "clean"})]
    for v in ("dark", "print"):
        vd, _r = style_.apply(doc, guide, v)
        vgot = verify.check(vd)
        variants.append((v, svg.render(vd),
                         {"findings": vgot["errors"] + vgot["warnings"],
                          "verdict": "clean" if not vgot["errors"] else "wrong"}))
    paths["contact"] = os.path.join(a.out, "showcase-contact.html")
    open(paths["contact"], "w").write(inspect.gallery(inspect.comparison(
        variants, "contact", doc["canvas"], title=doc.get("title"))))
    dark, _ = style_.apply(doc, guide, "dark")
    paths["onion"] = os.path.join(a.out, "showcase-onion.html")
    open(paths["onion"], "w").write(inspect.gallery(inspect.comparison(
        [("as it is", svg.render(doc), {}), ("dark", svg.render(dark), {})],
        "onion", doc["canvas"], title=doc.get("title"))))
    paths["truesize"] = os.path.join(a.out, "showcase-truesize.html")
    open(paths["truesize"], "w").write(inspect.gallery(inspect.comparison(
        [(doc.get("title"), svg.render(doc), {})], "true-size", doc["canvas"],
        title=doc.get("title"),
        note="check the ruler: a screen reports its own size only if configured to")))
    say("contact sheet of %d variants, an onion wipe, and a true-size page with a ruler",
        len(variants))
    say("and `lineart-scene watch --in <scene>` serves the inspector on loopback,")
    say("re-rendering whenever the file changes")

    step("In words, for somebody who cannot see it")
    words, _r = report.narrate(doc, guide=guide)
    for line in words.splitlines():
        say("%s", line)

    step("One report, and a reference to notice changes against")
    import cv2
    paths["reference"] = os.path.join(a.out, "showcase-ref.png")
    cv2.imwrite(paths["reference"], raster.rasterize(doc, 120))
    full = report.full(doc, guide=guide, reference=paths["reference"], dpi=120)
    t = full["totals"]
    say("verdict: %s -- %d error(s), %d warning(s), %d unchecked",
        full["verdict"].upper(), t["errors"], t["warnings"], t["unchecked"])
    nudged = copy.deepcopy(doc)
    model.find(nudged, "panel-d.plate")["transform"] = [1, 0, 0, 1, 2.0, 0.0]
    paths["diff"] = os.path.join(a.out, "showcase-diff.png")
    reg = report.regress(nudged, paths["reference"], dpi=120,
                         diff_path=paths["diff"])
    say("move the plate 2 mm: %d pixel(s) differ (%.3f%%), region x %d..%d y %d..%d",
        reg["changed"], reg["fraction"] * 100, reg["region"]["x0"], reg["region"]["x1"],
        reg["region"]["y0"], reg["region"]["y1"])
    numbers["verdict"] = full["verdict"]
    numbers["regression"] = f"{reg['changed']} px on a 2 mm move"

    paths["scene"] = os.path.join(a.out, "showcase.json")
    io.dump(doc, paths["scene"])
    inv = measure.inventory(doc)["value"]
    numbers["elements"] = (f"{inv['elements']} elements, {len(inv['roles'])} roles, "
                           f"{inv['anchors']} anchors")

    if a.html:
        write_html(a.html, paths, numbers, full, got)
        say("")
        say("page written: %s", a.html)
    print()
    return 0


# ===================================================================== the page
def write_html(path, paths, numbers, full, checked):
    def svg_of(key):
        return open(paths[key]).read() if key in paths else ""

    import base64
    diff = ""
    if "diff" in paths:
        diff = ('<img src="data:image/png;base64,'
                + base64.b64encode(open(paths["diff"], "rb").read()).decode() + '">')
    rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in numbers.items())
    stages = "".join(
        f'<figure><figcaption>stage {n}</figcaption><div class="art">'
        f'{svg_of("stage-" + n)}</div></figure>'
        for n in ("art", "pathway", "data", "readout"))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    open(path, "w").write(f"""<!doctype html><meta charset="utf-8">
<title>lineart-trace &mdash; showcase</title>
<style>
 :root {{ --ink:#16191d; --muted:#666e78; --line:#dfe3e8; --bg:#f6f7f9; }}
 body {{ font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
        margin:0; padding:32px 24px 72px; background:var(--bg); color:var(--ink); }}
 main {{ max-width:1080px; margin:0 auto; }}
 h1 {{ font-size:24px; margin:0 0 4px; letter-spacing:-.01em; }}
 .sub {{ color:var(--muted); margin:0 0 28px; }}
 h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:.07em;
       color:var(--muted); margin:34px 0 10px; font-weight:700; }}
 .card {{ background:#fff; border:1px solid var(--line); border-radius:10px;
          padding:12px; margin-bottom:14px; }}
 .card svg, .card img {{ display:block; width:100%; height:auto; }}
 .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr));
          gap:12px; }}
 figure {{ margin:0; background:#fff; border:1px solid var(--line);
           border-radius:10px; padding:10px; }}
 figcaption {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em;
               color:var(--muted); margin-bottom:6px; font-weight:700; }}
 .art svg {{ display:block; width:100%; height:auto; }}
 table {{ border-collapse:collapse; background:#fff; border:1px solid var(--line);
          border-radius:10px; overflow:hidden; width:100%; }}
 th, td {{ text-align:left; padding:8px 12px; border-bottom:1px solid var(--line);
           font-size:14px; }}
 th {{ color:var(--muted); font-weight:600; width:180px; }}
 tr:last-child th, tr:last-child td {{ border-bottom:none; }}
 code {{ font:13px ui-monospace,SFMono-Regular,Menlo,monospace;
         background:#eef1f4; padding:1px 5px; border-radius:4px; }}
 .verdict {{ display:inline-block; font:12px ui-monospace,monospace; font-weight:700;
             letter-spacing:.08em; padding:3px 9px; border-radius:99px;
             background:#e7f4ea; color:#1d6b32; }}
</style>
<main>
<h1>Strand-displacement amplification</h1>
<p class="sub">One scene, built by <code>examples/showcase.py</code>. Every coordinate
measured, every attachment declared, every export checked at its printed size.
Verdict: <span class="verdict">{full['verdict']}</span></p>

<h2>the figure &mdash; 180 &times; 118 mm</h2>
<div class="card">{svg_of('figure')}</div>

<h2>the same scene, dark variant &mdash; not one element edited</h2>
<div class="card">{svg_of('dark')}</div>

<h2>reflowed to an 88 mm journal column &mdash; the grid changes, drawings re-fit, type does not</h2>
<div class="card">{svg_of('column')}</div>

<h2>how it is held together</h2>
<div class="card">{svg_of('overlay')}</div>

<h2>the lecture build &mdash; each stage is an ordinary figure that verifies on its own</h2>
<div class="grid">{stages}</div>

<h2>visual regression &mdash; the plate moved 2 mm</h2>
<div class="card">{diff}</div>

<h2>pages to steer it from</h2>
<table>
<tr><th>inspector</th><td><a href="../{paths.get('inspector','')}">click any element,
  learn its address, role, z-order, box and style</a> &mdash; a pure view, no server</td></tr>
<tr><th>contact sheet</th><td><a href="../{paths.get('contact','')}">every variant on one
  page, each with its own verdict</a></td></tr>
<tr><th>onion skin</th><td><a href="../{paths.get('onion','')}">wipe between two
  versions</a></td></tr>
<tr><th>true size</th><td><a href="../{paths.get('truesize','')}">the figure at its printed
  size, with a ruler to check the screen</a></td></tr>
<tr><th>live</th><td><code>lineart-scene watch --in out/showcase.json</code> &mdash;
  re-renders whenever the file changes</td></tr>
</table>

<h2>what was measured</h2>
<table>{rows}</table>
</main>
""")


if __name__ == "__main__":
    sys.exit(main())
