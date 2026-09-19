"""Build a figure the way the toolkit is meant to be used, and show the evidence at each step.

    python3 examples/demo_figure.py --out out/

This is the spec's own thesis, run end to end: **a person and a model should converge on a
correct figure in a few deliberate steps instead of many blind ones.** Nothing below places
anything by eye. Every coordinate is measured, every attachment is declared, the one label
that will not fit says so and is not drawn, and the figure is checked at the size it will be
printed at.

The last step is the one that matters. The enzyme is edited -- moved and made larger -- and
the figure is re-solved. Everything attached to it follows, and nothing is redrawn.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineart_trace.scene import (anchors, build, io, measure, model, overlay,  # noqa: E402
                                 svg, text as text_, validate, verify)

STEP = 0


def step(title):
    global STEP
    STEP += 1
    print(f"\n{STEP}. {title}")
    print("   " + "-" * (len(title)))


def say(fmt, *a):
    print("   " + (fmt % a if a else fmt))


def duplex(name, x, y, length, rise=2.2, turns=3.0, rungs=13):
    """A DNA duplex as two antiparallel strands with base-pair rungs. §3.7 in miniature."""
    kids = []
    for s, phase in (("strand-a", 0.0), ("strand-b", math.pi)):
        pts = [(x + length * t / 60.0,
                y + rise * math.sin(2 * math.pi * turns * t / 60.0 + phase))
               for t in range(61)]
        kids.append(build.through(s, pts, style={"stroke": "#1f3f6b", "fill": "none",
                                                 "stroke_width": "0.7pt"}))
    for i in range(rungs):
        t = 60.0 * (i + 0.5) / rungs
        px = x + length * t / 60.0
        y0 = y + rise * math.sin(2 * math.pi * turns * t / 60.0)
        y1 = y + rise * math.sin(2 * math.pi * turns * t / 60.0 + math.pi)
        kids.append(build.line(f"pair-{i + 1:02d}", (px, y0), (px, y1),
                               style={"stroke": "#7aa3d0", "fill": "none",
                                      "stroke_width": "0.4pt"}))
    g = build.group(name, kids)
    g["tags"] = ["glyph"]
    return g


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="out")
    p.add_argument("--scene", default="tests/fixtures/scene-polymerase.json")
    p.add_argument("--font", default="Helvetica")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    # ---------------------------------------------------------------- 1
    step("Start from traced art, on a page with a real physical size")
    doc = io.load(a.scene)
    doc["name"] = "pol-entry"
    doc["title"] = "Polymerase entry channel"
    doc["canvas"].update({"width": 90.0, "height": 60.0, "background": "#ffffff"})
    doc["frames"]["art"]["transform"] = [0.028, 0, 0, 0.028, 8.0, 3.0]
    doc, _ = model.rename(doc, "art", "enzyme")
    prov = model.find(doc, "enzyme")["provenance"]
    say("page      %g x %g %s", doc["canvas"]["width"], doc["canvas"]["height"],
        doc["canvas"]["unit"])
    say("traced    %s  sha256 %s...", prov["source"], prov["sha256"][:12])
    box = measure.bbox(doc, "enzyme")["value"]
    say("enzyme    %.2f x %.2f mm at (%.2f, %.2f)  -- measured, not assumed",
        box["width"], box["height"], box["x"], box["y"])

    # ---------------------------------------------------------------- 2
    step("Find the entry channel by looking at the shape, not by guessing a coordinate")
    el = model.find(doc, "enzyme")
    el["anchors"] = {"channel": {"how": "discovered", "by": "concavity"},
                     "east": {"how": "derived", "by": "bbox.e"},
                     "south": {"how": "derived", "by": "bbox.s"},
                     "top": {"how": "derived", "by": "extreme.top"}}
    doc, report = anchors.resolve(doc)
    for got in report["resolved"]:
        pt = measure.bbox(doc, got["anchor"])["value"]
        say("%-16s -> (%.2f, %.2f) mm", got["anchor"], pt["x"], pt["y"])
    if report["unresolvable"]:
        for bad in report["unresolvable"]:
            say("could not: %s", bad["why"])

    # ---------------------------------------------------------------- 3
    step("Seat the duplex in that channel -- a declaration, not a pair of numbers")
    dup = duplex("duplex", 0, 0, 22)
    dup["anchors"] = {"inlet": {"how": "derived", "by": "bbox.e"},
                      "free-end": {"how": "derived", "by": "bbox.w"}}
    dup["relations"] = [{"kind": "attach", "to": "enzyme.channel", "via": "inlet",
                         "offset": [-1.0, 0.0]}]
    doc = model.add(doc, dup)
    doc, rep = anchors.solve(doc)
    moved = rep["moved"].get("duplex")
    say("duplex moved (%.2f, %.2f) mm to seat its inlet in the channel",
        moved["dx"], moved["dy"])
    gap = measure.clearance(doc, "duplex", "enzyme")["value"]
    say("clearance duplex..enzyme: %s",
        "overlapping (they interlock, as they should)" if gap["overlaps"]
        else f"{gap['gap']:.2f} mm")

    # ---------------------------------------------------------------- 4
    step("Label it -- and refuse the label that will not fit rather than overflowing it")
    caption = "DNA duplex entering the active site"
    try:
        text_.fit(caption, 26, 5, a.font, "7pt", mode="strict", unit="mm")
        say("fits at 7pt (unexpected)")
    except text_.TooBig as e:
        say("strict 7pt in 26x5mm: REFUSED -- %s", str(e).split(": ", 1)[1])
        say("  needs %.1f mm, has 26", e.detail["needs"]["width"])
    label, laid = text_.block("caption", caption, 2.0, 52.0, 34.0, 6.0, family=a.font,
                              size="6pt", mode="wrap", role="caption", unit="mm",
                              style={"fill": "#1f3f6b"})
    say("wrap into 34x8mm: %d lines at 6pt, using %.1f x %.1f mm",
        len(laid["lines"]), laid["width"], laid["height"])
    for line in laid["lines"]:
        say("  | %s", line)
    doc = model.add(doc, label)

    # ---------------------------------------------------------------- 5
    step("A leader that points at the channel and keeps pointing at it")
    tipx, tipy = measure.bbox(doc, "enzyme.channel")["value"]["x"], \
        measure.bbox(doc, "enzyme.channel")["value"]["y"]
    leader = build.group("leader", [
        build.line("shaft", (0, 0), (10, 0),
                   style={"stroke": "#c2452c", "fill": "none", "stroke_width": "0.5pt"}),
        build.arrowhead("head", (10, 0), (1, 0), 1.6,
                        style={"fill": "#c2452c", "stroke": "none"}),
    ])
    leader["anchors"] = {"tip": {"how": "derived", "by": "bbox.e"}}
    leader["relations"] = [{"kind": "attach", "to": "enzyme.channel", "via": "tip",
                            "offset": [-0.6, 0.0]}]
    doc = model.add(doc, leader)
    doc, rep = anchors.solve(doc)
    say("leader tip attached to enzyme.channel; %d element(s) placed by relation",
        len(rep["moved"]))

    # ---------------------------------------------------------------- 6
    step("Check it at the size it will be printed, before anyone looks at it")
    doc, rep = anchors.solve(doc)
    got = verify.check(doc, solve_report=rep)
    say("%d error(s), %d warning(s), %d unchecked", got["errors"], got["warnings"],
        len(got["unchecked"]))
    for f in got["findings"]:
        say("  [%s] %-9s %s: %s", f["severity"], f["rule"], f["element"] or "-",
            f["message"])
    if got["errors"]:
        say("")
        say("...so fix it, and ask again rather than looking at it:")
        for addr, el, _p in model.walk(doc):
            st = el.get("style") or {}
            if st.get("stroke") == "#7aa3d0":
                st["stroke"] = "#4a76a8"
        got = verify.check(doc, solve_report=rep)
        say("after darkening the rungs to #4a76a8: %d error(s), %d warning(s) "
            "(contrast now %.2f:1)", got["errors"], got["warnings"],
            verify.contrast_ratio("#4a76a8", "#ffffff"))

    # ---------------------------------------------------------------- 7
    step("Now EDIT the enzyme. Everything attached to it follows; nothing is redrawn.")
    before = {k: measure.bbox(doc, k)["value"] for k in ("duplex", "leader")}
    model.find(doc, "enzyme")["transform"] = [1.45, 0, 0, 1.45, 600.0, 380.0]
    doc, rep = anchors.solve(doc)
    after = {k: measure.bbox(doc, k)["value"] for k in ("duplex", "leader")}
    ch = measure.bbox(doc, "enzyme.channel")["value"]
    say("enzyme scaled 1.45x and shifted (in ITS frame -- image pixels, not mm);")
    say("its channel is now at (%.2f, %.2f) mm", ch["x"], ch["y"])
    for k in ("duplex", "leader"):
        say("%-7s followed: (%.2f, %.2f) -> (%.2f, %.2f) mm", k,
            before[k]["x"], before[k]["y"], after[k]["x"], after[k]["y"])
    say("re-solve is stable: %s", anchors.solve(doc)[1]["moved"] == {})

    # ---------------------------------------------------------------- 8
    step("Ask again -- the edit broke something two millimetres wide")
    got = verify.check(doc, solve_report=rep)
    say("%d error(s), %d warning(s)", got["errors"], got["warnings"])
    for f in got["findings"]:
        say("  [%s] %-14s %s: %s", f["severity"], f["rule"], f["element"] or "-",
            f["message"])
    if not got["findings"]:
        say("  (none -- this edit happened to be safe)")
    else:
        say("...which is a 2mm strip off the bottom of a 60mm page: visible in print, "
            "invisible on screen.")

    # ---------------------------------------------------------------- 9
    step("Fix it by declaring what must be true, not by nudging until it looks right")
    page_guide = build.rect("page-area", 2.0, 2.0,
                            doc["canvas"]["width"] - 4.0, doc["canvas"]["height"] - 4.0)
    page_guide["type"] = "guide"
    doc = model.add(doc, page_guide)
    model.find(doc, "enzyme")["relations"] = [{"kind": "inside", "to": "page-area"}]
    model.find(doc, "caption")["relations"] = [
        {"kind": "clear", "to": "enzyme", "offset": [2.0, 0.0]},
        {"kind": "inside", "to": "page-area"}]
    say("enzyme  must be inside page-area (a guide -- construction geometry, never drawn)")
    say("caption must clear the enzyme by 2mm, and stay inside page-area too")
    doc, rep = anchors.solve(doc)
    say("solved in %d pass(es); %s", rep["passes"],
        "settled" if rep["settled"] else "DID NOT SETTLE")
    for k in sorted(rep["moved"]):
        say("  %-8s moved (%.2f, %.2f) mm", k, rep["moved"][k]["dx"],
            rep["moved"][k]["dy"])
    for item in rep["unsatisfiable"]:
        say("  unsatisfiable: %s", item["why"])
    got = verify.check(doc, solve_report=rep)
    say("check again: %d error(s), %d warning(s), %d unchecked",
        got["errors"], got["warnings"], len(got["unchecked"]))
    for f in got["findings"]:
        say("  [%s] %-14s %s: %s", f["severity"], f["rule"], f["element"] or "-",
            f["message"])
    gap = measure.clearance(doc, "caption", "enzyme")["value"]
    say("caption..enzyme is now %.2f mm", gap["gap"])

    # ---------------------------------------------------------------- 10
    step("Export: the scene, the figure, and the overlay that shows how it is held together")
    bad, warn = validate.problems(doc)
    say("scene conforms: %s%s", "yes" if not bad else f"NO -- {bad[:1]}",
        f" ({len(warn)} warning)" if warn else "")
    paths = {}
    paths["scene"] = os.path.join(a.out, "pol-entry.json")
    io.dump(doc, paths["scene"])
    paths["figure"] = os.path.join(a.out, "pol-entry.svg")
    open(paths["figure"], "w").write(svg.render(doc))
    load = overlay.payload(doc, grid=10.0, findings=got["findings"])
    paths["overlay"] = os.path.join(a.out, "pol-entry-overlay.svg")
    open(paths["overlay"], "w").write(overlay.render(load))
    paths["payload"] = os.path.join(a.out, "pol-entry-overlay.json")
    io.dump(load, paths["payload"])
    inv = measure.inventory(doc)["value"]
    say("%d elements, %d anchors, colours %s", inv["elements"], inv["anchors"],
        ", ".join(list(inv["colours"])[:4]))
    for k, v in paths.items():
        say("%-8s %s  (%d bytes)", k, v, os.path.getsize(v))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
