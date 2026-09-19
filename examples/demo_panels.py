"""A three-panel figure, styled by guide, routed round obstacles, and retargeted twice.

    python3 examples/demo_panels.py --out out/

Where `demo_figure.py` shows one figure being built deliberately, this shows the two things
that only matter once you have more than one figure: **a set that stays visually consistent**,
and **a figure that survives being moved to a different page**.

Nothing is restyled by editing it. The same scene is exported three times -- house style,
dark variant, and a journal column at 88mm -- and checked at each size.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineart_trace.scene import (anchors, build, io, layout, measure, model,  # noqa: E402
                                 overlay, palette, style as style_, svg,
                                 text as text_, validate, verify)

STEP = 0


def step(title):
    global STEP
    STEP += 1
    print(f"\n{STEP}. {title}")
    print("   " + "-" * len(title))


def say(fmt, *a):
    print("   " + (fmt % a if a else fmt))


def label_width(string, guide, role="caption", unit="mm"):
    """How wide a label will actually be, in page units, before anything is drawn."""
    body = guide["roles"][role]
    family = guide["tokens"]["family"][body["font_family"].split(".")[-1]] \
        if body["font_family"].startswith("@") else body["font_family"]
    size = body["font_size"]
    if isinstance(size, str) and size.startswith("@"):
        size = guide["tokens"]["type"][size.split(".")[-1]]
    pt = text_.as_unit(size, "pt")
    return model.to_unit(measure.text(string, family, pt)["value"]["advance"], "pt", unit)


def pathway(doc, panel, frame, guide, top):
    """Panel B: boxes sized to their labels, one arrow straight and one round an inhibitor.

    **The boxes are sized from measured text, not from a guess.** The first version used a
    fixed 20mm box for a label that turned out to be 20.4mm wide, and the verification
    caught it -- which is the right outcome and a silly way to get there when the width can
    simply be asked for.
    """
    pad = 3.0
    stages = [("substrate", top + 0.0), ("complex", top + 24.0), ("product", top + 52.0)]
    widest = max(label_width(n, guide) for n, _y in stages)
    w = widest + 2 * pad
    x = 3.0
    for name, y in stages:
        doc = model.add(doc, build.rect(name, x, y, w, 9, radius=1.5,
                                        role="surface-fill"), panel)
        doc = model.add(doc, build.text(f"{name}-label", name, (x + w / 2, y + 6.0),
                                        family=None, size=None, align="middle",
                                        role="caption"), panel)
    iw = label_width("inhibitor", guide) + 2 * pad
    doc = model.add(doc, build.rect("inhibitor", x + 6, top + 38, iw, 8, radius=1.5,
                                    role="surface-fill"), panel)
    doc = model.add(doc, build.text("inhibitor-label", "inhibitor",
                                    (x + 6 + iw / 2, top + 43.6),
                                    family=None, size=None, align="middle",
                                    role="caption"), panel)
    avoid = [f"{panel}.{n}" for n, _y in stages] + [f"{panel}.inhibitor",
                                                    f"{panel}.inhibitor-label"]
    avoid += [f"{panel}.{n}-label" for n, _y in stages]
    routed = []
    mid = x + w / 2
    for i, (a, b) in enumerate(zip(stages, stages[1:]), 1):
        doc, rep = layout.connect(
            doc, f"step-{i}", (mid, a[1] + 9.0), (mid, b[1]),
            avoid=avoid, clearance=1.5, resolution=0.5, frame=frame, arrow=1.8,
            role="accent-stroke")
        routed.append(rep)
    return doc, routed, w


def describe_route(i, r):
    if not r.get("routed"):
        return (f"step-{i}: REFUSED -- {r['why']}")
    return (f"step-{i}: {r['corners']} corner(s), clears {r['clearance_worst']:.2f} mm "
            f"of an asked {r['clearance_asked']:.1f}, past "
            f"{', '.join(x.split('.')[-1] for x in r['passed']) or 'nothing'}")


def swatches(doc, panel, colours, top):
    """Panel C: the palette, one labelled swatch each."""
    for i, c in enumerate(colours):
        y = top + i * 11.0
        doc = model.add(doc, build.rect(f"swatch-{i + 1}", 3, y, 10, 7, radius=1.0,
                                        role=f"series-{i + 1}"), panel)
        # LABELLED BY ROLE, not by hex. The first version printed the colour value, which
        # is content and so does not change with the theme -- the dark export showed a
        # green swatch captioned `#2b8cee`. A label that names the role stays true under
        # every variant, which is the whole argument for roles in one small place.
        doc = model.add(doc, build.text(f"swatch-{i + 1}-label", f"series-{i + 1}",
                                        (15.5, y + 5.0), family=None, size=None,
                                        role="caption"), panel)
    return doc


def report(doc, label, solve_report=None):
    got = verify.check(doc, solve_report=solve_report)
    say("%-22s %d error(s), %d warning(s), %d unchecked", label + ":",
        got["errors"], got["warnings"], len(got["unchecked"]))
    for f in got["findings"]:
        say("    [%s] %-14s %s: %s", f["severity"], f["rule"], f["element"] or "-",
            f["message"])
    return got


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="out")
    p.add_argument("--traced", default="tests/fixtures/scene-polymerase.json")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    paths = {}

    # ---------------------------------------------------------------- 1
    step("Lay three panels on a 180x80mm page -- the letters are not typed by hand")
    doc = model.new("pathway", 180, 80, title="Inhibition of the polymerase",
                    background="#ffffff")
    guide = style_.load("figure-default")
    doc, _ = style_.apply(doc, guide)          # so the panel letters take the role, not a literal
    doc, rep = layout.panels(doc, rows=1, cols=3, gutter=6, margin=4)
    say("panels %s, each %.2f x %.2f mm, gutter %g",
        ", ".join(rep["created"]), rep["panel"]["width"], rep["panel"]["height"],
        rep["gutter"])
    letter = measure.bbox(doc, "panel-a.letter", "panel-a-frame")["value"]
    top = letter["y"] + letter["height"] + 3.0
    say("the letter is %.2f mm tall, so panel content starts at y=%.2f -- measured, not "
        "left to chance", letter["height"], top)

    # ---------------------------------------------------------------- 2
    step("Panel A: traced art, adopted into roles so it can be restyled at all")
    traced = io.load(a.traced)
    art = model.find(traced, "art")
    doc["frames"]["art"] = dict(traced["frames"]["art"])
    doc = model.add(doc, art)
    doc, adopted = style_.adopt(doc, guide)
    say("%d element(s) -> %d role(s): %s", adopted["converted"],
        len(adopted["roles"]), ", ".join(adopted["roles"]))
    for name, near in sorted((adopted.get("nearest") or {}).items()):
        if near:
            say("  %s is closest to %r, differing in %s", name, near["role"],
                ", ".join(near["differs_in"]) or "nothing")
    # BINDING IS A HUMAN DECISION, and this is where it is taken. `adopt` names what it
    # finds; it cannot know that the traced outline MEANS structure. Leave it on
    # `adopted-NN` and the drawing will not follow a theme, because nothing in the guide
    # touches that name -- which the dark variant below reports as a contrast error.
    for _addr, el, _p in model.walk(doc):
        if el.get("role", "").startswith("adopted-"):
            el["role"] = "structure-stroke"
    say("bound the adopted role to `structure-stroke` -- adopt names, a person decides")
    doc, fitted = layout.into_panel(doc, "art", "panel-a", margin=2)
    say("fitted into panel-a at %.3f scale, %.2f x %.2f mm", fitted["scale"],
        fitted["box"]["width"], fitted["box"]["height"])

    # ---------------------------------------------------------------- 3
    step("Panel B: a pathway whose arrows go ROUND the inhibitor, not through it")
    doc, routes, boxw = pathway(doc, "panel-b", "panel-b-frame", guide, top)
    say("boxes %.2f mm wide, sized to the widest label measured at 6pt", boxw)
    for i, r in enumerate(routes, 1):
        say("%s", describe_route(i, r))

    # ---------------------------------------------------------------- 4
    step("Panel C: a palette chosen by measurement, not by eye")
    series = [guide["tokens"]["colour"][f"series-{i + 1}"] for i in range(5)]
    got = palette.check(series, "#ffffff", min_delta_e=18.0)
    w = got["worst_pair"]
    say("%d colours; usable at 18 delta-E: %s", len(series), got["usable"])
    say("closest pair %s vs %s at %.1f delta-E, under %s", w["a"], w["b"],
        w["worst_delta_e"], w["worst"])
    doc = swatches(doc, "panel-c", series, top)

    # ---------------------------------------------------------------- 5
    step("Apply the house style. Every element drawn by role changes at once.")
    doc, applied = style_.apply(doc, guide)
    say("%s: %d role(s) available, %d element(s) styled by role", applied["guide"],
        applied["roles_defined"], applied["elements_styled"])
    used = ", ".join(f"{r} x{n}" for r, n in sorted(applied["roles_used"].items()))
    say("in use: %s", used)
    doc, solved = anchors.solve(doc)
    say("scene conforms: %s", "yes" if not validate.problems(doc)[0] else "NO")
    light = report(doc, "house style, 180x80")
    paths["figure"] = os.path.join(a.out, "pathway.svg")
    open(paths["figure"], "w").write(svg.render(doc))

    # ---------------------------------------------------------------- 6
    step("The same scene, dark. Not one element is edited.")
    dark, _ = style_.apply(doc, guide, "dark")
    say("background %s -> %s; the ink token flips with it",
        doc["canvas"]["background"], dark["canvas"]["background"])
    say("structure-stroke was %s, is now %s",
        doc["style"]["roles"]["structure-stroke"]["stroke"],
        dark["style"]["roles"]["structure-stroke"]["stroke"])
    say("series-5 was %s, is now %s -- the variant carries its OWN series, because a",
        doc["style"]["roles"]["series-5"]["fill"],
        dark["style"]["roles"]["series-5"]["fill"])
    say("palette is relative to the background it sits on. Keeping the light one gave")
    say("two swatches at 2.2:1 and 2.3:1 on the dark page, which the check found.")
    report(dark, "dark variant")
    paths["dark"] = os.path.join(a.out, "pathway-dark.svg")
    open(paths["dark"], "w").write(svg.render(dark))

    # ---------------------------------------------------------------- 7
    step("Retarget to an 88mm journal column: reflow, not shrink")
    column, _ = style_.apply(doc, style_.load("journal-column"))
    column, flowed = layout.reflow(column, width=88, height=150)
    say("%gx%g -> %gx%g; panels now %.2f x %.2f",
        flowed["from"]["width"], flowed["from"]["height"],
        flowed["to"]["width"], flowed["to"]["height"],
        flowed["panel"]["width"], flowed["panel"]["height"])
    for r in flowed["refitted"]:
        say("re-fitted %s to %.3f scale -- the drawing fills the new panel...",
            r["element"], r["scale"])
    cap = measure.text("substrate", "Helvetica", 7)
    say("...while the type does not move: caption is %s in both",
        column["style"]["roles"]["caption"]["font_size"])
    column, solved2 = anchors.solve(column)
    report(column, "journal column, 88mm", solved2)
    paths["column"] = os.path.join(a.out, "pathway-column.svg")
    open(paths["column"], "w").write(svg.render(column))

    # ---------------------------------------------------------------- 8
    step("Lint the set against the guide, and export the overlay")
    linted = style_.lint(doc, guide)
    say("%d error(s), %d warning(s) against %s", linted["errors"], linted["warnings"],
        linted["guide"])
    for f in linted["findings"][:4]:
        say("  [%s] %-14s %s: %s", f["severity"], f["rule"], f["element"] or "-",
            f["message"])
    load = overlay.payload(doc, grid=10.0, findings=light["findings"], depth=2)
    paths["overlay"] = os.path.join(a.out, "pathway-overlay.svg")
    open(paths["overlay"], "w").write(overlay.render(load))
    paths["scene"] = os.path.join(a.out, "pathway.json")
    io.dump(doc, paths["scene"])
    inv = measure.inventory(doc)["value"]
    say("%d elements, %d roles in use, %d colours, frames %s", inv["elements"],
        len(inv["roles"]), len(inv["colours"]), ", ".join(inv["frames"][:4]) + "...")
    for k, v in paths.items():
        say("%-8s %s  (%d bytes)", k, v, os.path.getsize(v))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
