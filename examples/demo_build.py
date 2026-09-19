"""A lecture build, and the one report that says whether the figure is ready to send.

    python3 examples/demo_build.py --out out/

Two claims, checked rather than asserted. **Any frame of an animation can be exported as a
static figure** -- so each stage of the build below is measured and verified at printed size
like any other figure. And **"is this correct" has one answer**: `report` runs conformance,
layout, print legibility, style, glyph versions and visual regression, and counts what it
could *not* establish separately from what passed.
"""
import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineart_trace.scene import (animate, anchors, build, geometry, glyphs,  # noqa: E402
                                 io, measure, model, raster, report,
                                 style as style_, svg, verify)


def step(n, title):
    print(f"\n{n}. {title}\n   " + "-" * len(title))


def say(fmt, *a):
    print("   " + (fmt % a if a else fmt))


def figure():
    d = model.new("replication", 120, 62, title="Strand displacement",
                  background="#ffffff")
    d["description"] = ("A polymerase seated on a nicked duplex, with the displaced "
                        "strand labelled. Built as a three-step lecture reveal.")
    d, _ = style_.apply(d, style_.load("figure-default"))
    d, _ = glyphs.place(d, "dna.duplex", "duplex", at=(6, 8),
                        args={"length": 74, "nick": 0.42, "polarity": True})
    d, _ = glyphs.place(d, "protein.silhouette", "pol", at=(30, 24),
                        args={"width": 30, "height": 20, "cleft": 0.75, "label": "Pol"})
    d = model.add(d, build.text("caption", "strand displacement at the nick",
                                (6, 56), family=None, size=None, role="caption"))
    return d


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="out")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    paths = {}

    step(1, "A figure, and a build over it")
    doc = figure()
    tl = animate.from_stages("lecture", [
        {"name": "duplex", "reveal": ["duplex"], "hold": 1.2,
         "note": "the template, with a nick"},
        {"name": "enzyme", "reveal": ["pol"], "hold": 1.4,
         "note": "the polymerase seats in the nick"},
        {"name": "caption", "reveal": ["caption"], "hold": 1.6},
    ], scene=doc["name"])
    paths["timeline"] = os.path.join(a.out, "lecture.json")
    io.dump(tl, paths["timeline"])
    say("%g s, %d track(s), marks: %s", tl["duration"], len(tl["tracks"]),
        ", ".join(f"{k} at {v:g}s" for k, v in tl["marks"].items()))

    step(2, "Every stage is a figure: measured and checked like any other")
    for st in tl["stages"]:
        still = animate.still(doc, tl, st["name"])
        got = verify.check(still)
        box = measure.bbox(still, model.addresses(still)[0])["value"]
        say("%-8s %2d element(s), first is %.1f x %.1f mm, %d error(s), %d warning(s)",
            st["name"], len(model.addresses(still)), box["width"], box["height"],
            got["errors"], got["warnings"])
        path = os.path.join(a.out, f"stage-{st['name']}.svg")
        open(path, "w").write(svg.render(still))
        paths[f"stage-{st['name']}"] = path
    say("a still is taken AFTER the stage's rise -- at the mark itself the thing being")
    say("revealed is still at zero opacity, and the still would show the stage before")

    step(3, "A draw-on that a measurement can see")
    drawn = {"format": "lineart.timeline/1", "name": "drawon", "duration": 2.0,
             "tracks": [{"target": "duplex", "property": "draw", "easing": "ease-in-out",
                         "keys": [{"t": 0.0, "value": 0.0}, {"t": 2.0, "value": 1.0}]}]}
    full = geometry.length([model.find(doc, "duplex.strand-b")["geometry"]["d"]])
    for t in (0.5, 1.0, 1.5):
        s = animate.at(doc, drawn, t)
        got = geometry.length([model.find(s, "duplex.strand-b")["geometry"]["d"]])
        say("t=%.1fs: the strand is %.1f%% drawn, and measures that way", t,
            got / full * 100)
    say("real geometry, not a dash-offset trick -- a half-drawn stroke IS half a stroke")

    step(4, "Export the animation, and say what the file cannot carry")
    paths["animation"] = os.path.join(a.out, "lecture.svg")
    text = animate.to_svg(doc, tl)
    open(paths["animation"], "w").write(text)
    carried = [t for t in tl["tracks"] if t["property"] in animate._SMIL]
    say("%d of %d track(s) animate in the SVG itself", len(carried), len(tl["tracks"]))
    combined = copy.deepcopy(tl)
    combined["tracks"] = combined["tracks"] + drawn["tracks"]
    note = animate.to_svg(doc, combined)
    say("add the draw-on and the file says so rather than dropping it: %s",
        "yes" if "not animated in this file" in note else "no")

    step(5, "A reference image, and what happens when the figure changes")
    paths["reference"] = os.path.join(a.out, "replication-ref.png")
    import cv2
    cv2.imwrite(paths["reference"], raster.rasterize(doc, 120))
    clean = report.regress(doc, paths["reference"], dpi=120)
    say("unchanged: %d of %d pixel(s) differ", clean["changed"], clean["pixels"])
    moved = copy.deepcopy(doc)
    model.find(moved, "pol")["transform"] = [1, 0, 0, 1, 3.0, 0.0]
    paths["diff"] = os.path.join(a.out, "replication-diff.png")
    changed = report.regress(moved, paths["reference"], dpi=120,
                             diff_path=paths["diff"])
    say("polymerase moved 3 mm: %d pixel(s) (%.3f%%), region x %d..%d y %d..%d",
        changed["changed"], changed["fraction"] * 100, changed["region"]["x0"],
        changed["region"]["x1"], changed["region"]["y0"], changed["region"]["y1"])
    missing = report.regress(doc, os.path.join(a.out, "nothing.png"))
    say("and with no reference at all: %s", missing["unavailable"][:64])

    step(6, "One report, with a verdict")
    guide = style_.load("figure-default")
    for label, scene, ref in (("as built", doc, paths["reference"]),
                              ("after the move", moved, paths["reference"]),
                              ("no reference", doc, None)):
        got = report.full(scene, guide=guide, reference=ref, dpi=120)
        t = got["totals"]
        say("%-15s %-14s %d error(s), %d warning(s), %d unchecked", label,
            got["verdict"].upper(), t["errors"], t["warnings"], t["unchecked"])
        for u in got["unchecked"][:2]:
            say("                  unchecked: %s", u)
    say("`unchecked` is counted apart from `passed`, always -- a figure with nothing")
    say("wrong and four things nobody could check is not a figure with nothing wrong")

    step(7, "Files")
    paths["scene"] = os.path.join(a.out, "replication.json")
    io.dump(doc, paths["scene"])
    for k, v in paths.items():
        say("%-16s %s (%d bytes)", k, v, os.path.getsize(v))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
