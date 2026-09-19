"""A three-panel data figure built from scales, marks and measured annotations. §3.8.

    python3 examples/demo_data.py --out out/

**Done when a publication panel can be produced from a data file and remain correct, and
restyleable, after the data is revised.** So the numbers come from a CSV, the figure records
that file's digest, and the whole thing is verified at print size and exported light and dark
without one element being edited.
"""
import argparse
import csv
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineart_trace.scene import (anchors, data, io, layout, measure, model,  # noqa: E402
                                 style as style_, svg, validate, verify)


def write_data(path, seed=7):
    """The data file this figure is made from. Deterministic, so the figure is too."""
    random.seed(seed)
    rows = [("dose", "response", "strain")]
    for i in range(1, 21):
        x = i * 2.0
        rows.append((f"{x:g}", f"{3.0 + 0.42 * x + random.gauss(0, 2.0):.4f}", "wt"))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return path


def say(fmt, *a):
    print("   " + (fmt % a if a else fmt))


def step(n, title):
    print(f"\n{n}. {title}\n   " + "-" * len(title))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="out")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    csv_path = write_data(os.path.join(a.out, "dose-response.csv"))

    step(1, "Read the data file, and record which file it was")
    cols, rows = data.read_table(csv_path)
    xs = [r["dose"] for r in rows]
    ys = [r["response"] for r in rows]
    digest, nbytes = data.source_digest(csv_path)
    say("%s: %d columns %s, %d rows, sha256 %s...", os.path.basename(csv_path),
        len(cols), cols, len(rows), digest[:12])

    step(2, "A page of three panels, on the house style")
    doc = model.new("results", 180, 74, title="Results", background="#ffffff")
    doc, _ = style_.apply(doc, style_.load("figure-default"))
    doc, panels = layout.panels(doc, rows=1, cols=3, gutter=5, margin=4)
    say("%d panels of %.2f x %.2f mm", panels["cols"], panels["panel"]["width"],
        panels["panel"]["height"])
    pw, ph = panels["panel"]["width"], panels["panel"]["height"]

    step(3, "Panel A: a scatter with a least-squares fit, and the fit's numbers")
    g, rep = data.plot("dose", xs, ys, pw, ph, kind="scatter", xlabel="dose (mg)",
                       ylabel="response", fit_line=True, source=csv_path)
    doc = model.add(doc, g, "panel-a")
    f = rep["fit"]
    say("slope %.4f, intercept %.4f, r² %.4f over n=%d (%s)", f["slope"],
        f["intercept"], f["r2"], f["n"], f["confidence"])
    say("the band is drawn from those numbers, not fitted twice")

    step(4, "Panel B: bars with error bars and a significance bracket")
    cats = ["wt", "ΔA", "ΔB", "ΔAB"]
    vals = [100.0, 62.0, 71.0, 18.0]
    errs = [6.0, 5.0, 7.0, 3.0]
    g2, r2 = data.plot("activity", cats, vals, pw, ph, kind="bar", errors=errs,
                       categories=cats, ylabel="activity (%)",
                       y_scale=data.linear((0, 135), (ph - 13.0, 6.0)))
    sx, sy = r2["scales"]["x"], r2["scales"]["y"]
    g2["children"].append(data.significance("wt", "ΔAB", sy.map(118), sx, "***"))
    doc = model.add(doc, g2, "panel-b")
    say("y axis 0 at %.2f mm, 135 at %.2f mm -- the range's ORDER is its direction",
        sy.map(0), sy.map(135))
    say("bracket at 118 %% sits at %.2f mm, inside the panel", sy.map(118))

    step(5, "Panel C: a log-log decay with a legend on a backing plate")
    t = [10 ** (i / 6) for i in range(0, 19)]
    v = [1000 / (1 + (x / 30) ** 1.4) for x in t]
    g3, _r = data.plot("decay", t, v, pw, ph, kind="line",
                       x_scale=data.log((min(t), max(t)), (14.0, pw - 4.0)),
                       y_scale=data.log((min(v), max(v)), (ph - 13.0, 6.0)),
                       xlabel="time (min)", ylabel="signal")
    # PLACED WHERE IT COVERS NOTHING. At (26, 11) the plate sat squarely on the decay
    # curve: the `occluded` check reported it, and the figure had quietly lost a stretch of
    # its own data behind the thing meant to explain it.
    g3["children"].append(data.legend([("observed", "accent-stroke")], (20.0, 44.0),
                                      width=16.0))
    doc = model.add(doc, g3, "panel-c")
    say("the legend is at the empty corner: a plate over the decay curve hid the data,")
    say("which `occluded` reported rather than forgiving along with the label overlap")
    say("log ticks at the decades: %s",
        ", ".join(t3 for _v, _p, t3 in
                  data.log((min(t), max(t)), (0.0, 1.0)).ticks()))

    step(6, "Check it at print size")
    doc, solved = anchors.solve(doc)
    say("scene conforms: %s", "yes" if not validate.problems(doc)[0] else "NO")
    got = verify.check(doc, solve_report=solved)
    say("%d error(s), %d warning(s), %d unchecked", got["errors"], got["warnings"],
        len(got["unchecked"]))
    for fnd in got["findings"]:
        say("  [%s] %-14s %s: %s", fnd["severity"], fnd["rule"], fnd["element"] or "-",
            fnd["message"])

    step(7, "Export, light and dark, and lint against the guide")
    paths = {"figure": os.path.join(a.out, "results.svg"),
             "dark": os.path.join(a.out, "results-dark.svg"),
             "scene": os.path.join(a.out, "results.json")}
    open(paths["figure"], "w").write(svg.render(doc))
    dark, _ = style_.apply(doc, style_.load("figure-default"), "dark")
    open(paths["dark"], "w").write(svg.render(dark))
    io.dump(doc, paths["scene"])
    linted = style_.lint(doc, style_.load("figure-default"))
    say("lint: %d error(s), %d warning(s)", linted["errors"], linted["warnings"])
    dgot = verify.check(dark, solve_report=solved)
    say("dark: %d error(s), %d warning(s)", dgot["errors"], dgot["warnings"])
    prov = model.find(doc, "panel-a.dose")["provenance"]
    say("panel A records its source: %s sha256 %s...", prov["source"], prov["sha256"][:12])
    inv = measure.inventory(doc)["value"]
    say("%d elements, %d roles, %d colours", inv["elements"], len(inv["roles"]),
        len(inv["colours"]))
    for k, path in paths.items():
        say("%-7s %s (%d bytes)", k, path, os.path.getsize(path))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
