"""Four diagram constructs on one page: a state machine, a tree, swimlanes and a flowchart.

    python3 examples/demo_diagram.py --out out/

**Nothing here is a box drawn at a guessed size.** Every node is measured in the font the
guide supplies and built around its label; every edge is routed around whatever is in its way
and reports the clearance it achieved; every container fits the elements it names.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineart_trace.scene import (anchors, diagram, io, layout, measure,  # noqa: E402
                                 model, style as style_, svg, validate, verify)


def step(n, title):
    print(f"\n{n}. {title}\n   " + "-" * len(title))


def say(fmt, *a):
    print("   " + (fmt % a if a else fmt))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="out")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    doc = model.new("diagrams", 190, 180, title="Diagram constructs",
                    background="#ffffff")
    doc, _ = style_.apply(doc, style_.load("figure-default"))
    from lineart_trace.scene import build
    for i, (x, y) in enumerate([(8, 8), (108, 8), (8, 88), (8, 140)], 1):
        doc["frames"][f"q{i}"] = {"parent": "page", "unit": "mm",
                                  "transform": [1, 0, 0, 1, x, y]}
    # A GROUP PER DIAGRAM, so two diagrams on one page do not fight over element names --
    # `flow` numbers its edges `edge-01` upward, and the second flow on this page collided
    # with the first at its very first edge.
    for name, frame in (("states", "q1"), ("map", "q2"), ("protocol", "q3"),
                        ("check", "q4")):
        doc = model.add(doc, build.group(name, [], frame=frame))

    step(1, "A state machine -- which has a cycle, and is drawn anyway")
    spec = {"idle": "idle", "running": "running", "paused": "paused", "done": "done"}
    edges = [("idle", "running", "start"), ("running", "paused", "hold"),
             ("paused", "running", "go"), ("running", "done", "finish")]
    doc, r1 = diagram.flow(doc, spec, edges, at=(0, 6), spacing=(14, 14),
                           parent="states")
    say("%d layers; cyclic: %s; the edge that closes it: %s", r1["layers"], r1["cyclic"],
        ", ".join(f"{x}->{y}" for x, y in r1["back_edges"]))
    say("a longest path needs an acyclic graph, so the cycle is NAMED and the rest laid out")
    for e in r1["edges"]:
        say("%s %-8s -> %-8s parallel offset %d, %d corner(s)", e["name"], e["from"],
            e["to"], e["parallel_offset"], e["corners"])
    say("the second edge of a pair is offset sideways and its label staggered along it")

    step(2, "A tree of names that are not element names")
    doc, r2 = diagram.tree(doc, "plasmid",
                           {"plasmid": ["ori", "ampR", "mcs"],
                            "mcs": ["EcoRI", "BamHI"]},
                           at=(0, 6), spacing=(5, 9), parent="map")
    say("%d nodes, depth %d", len(r2["nodes"]), r2["depth"])
    say("keys slugged into element names: %s",
        ", ".join(f"{k}->{v}" for k, v in sorted(r2["names"].items()) if k != v))

    step(3, "Swimlanes, with a container that fits what it holds")
    doc, r3 = diagram.swimlanes(doc, ["prep", "reaction", "analysis"], at=(0, 0),
                                width=176, lane_height=17, parent="protocol")
    say("lanes %s, heading column %.2f mm wide (measured)", r3["lanes"],
        r3["heading_width"])
    placed = []
    for lane, label, x in [("prep", "weigh", 34), ("prep", "dissolve", 60),
                           ("reaction", "incubate", 34), ("analysis", "read", 34)]:
        at_ = model.find(doc, "protocol.swimlanes")["anchors"][lane]["at"]
        doc, rep = diagram.node(doc, f"{lane}-{label}", label, (x, at_[1] - 2.0),
                                parent="protocol")
        placed.append(rep)
    doc, r4 = diagram.container(doc, "batch",
                                ["protocol.prep-weigh", "protocol.prep-dissolve"],
                                pad=2.0, label="batch 1", parent="protocol")
    say("container %.2f x %.2f mm around %s", r4["box"]["width"], r4["box"]["height"],
        ", ".join(r4["members"]))
    doc, r5 = diagram.node(doc, "prep-label", "label tubes",
                           (86, model.find(doc, "protocol.swimlanes")["anchors"]
                            ["prep"]["at"][1] - 2.0), parent="protocol")
    doc, r4b = diagram.container(doc, "batch",
                                 ["protocol.prep-weigh", "protocol.prep-dissolve",
                                  "protocol.prep-label"], pad=2.0, label="batch 1",
                                 parent="protocol")
    say("add a node and re-run it: %.2f -> %.2f mm wide, refitted=%s",
        r4["box"]["width"], r4b["box"]["width"], r4b["refitted"])
    doc, r6 = diagram.edge(doc, "hand-off", "protocol.prep-dissolve",
                           "protocol.reaction-incubate", parent="protocol")
    say("cross-lane edge: %d corner(s), clears %.2f mm of an asked %.1f", r6["corners"],
        r6["clearance_worst"], r6["clearance_asked"])

    step(4, "A flowchart whose arrow has to go round something")
    doc, r7 = diagram.flow(doc, {"in": "input", "check": "valid?", "out": "output"},
                           [("in", "check"), ("check", "out")], at=(0, 4),
                           spacing=(12, 10), vertical=False, parent="check")
    doc, r8 = diagram.node(doc, "blocker", "logged", (58, 0), parent="check")
    doc, r9 = diagram.edge(doc, "skip", "check.in", "check.out", "on failure",
                           parent="check")
    say("%s: %d corner(s), %s, clears %.2f mm past %s", r9.get("name", "skip"),
        r9["corners"], "direct" if r9.get("direct") else "routed",
        r9["clearance_worst"], ", ".join(x for x in r9["passed"]) or "nothing")

    step(5, "Check the whole page at print size")
    bad, warn = validate.problems(doc)
    say("scene conforms: %s%s", "yes" if not bad else f"NO -- {bad[:1]}",
        f" ({len(warn)} warning)" if warn else "")
    doc, solved = anchors.solve(doc)
    got = verify.check(doc, solve_report=solved)
    say("%d error(s), %d warning(s), %d unchecked", got["errors"], got["warnings"],
        len(got["unchecked"]))
    for f in got["findings"]:
        say("  [%s] %-14s %s: %s", f["severity"], f["rule"], f["element"] or "-",
            f["message"])

    step(6, "Export")
    paths = {"figure": os.path.join(a.out, "diagrams.svg"),
             "dark": os.path.join(a.out, "diagrams-dark.svg"),
             "scene": os.path.join(a.out, "diagrams.json")}
    open(paths["figure"], "w").write(svg.render(doc))
    dark, _ = style_.apply(doc, style_.load("figure-default"), "dark")
    open(paths["dark"], "w").write(svg.render(dark))
    io.dump(doc, paths["scene"])
    inv = measure.inventory(doc)["value"]
    say("%d elements, %d roles, %d anchors", inv["elements"], len(inv["roles"]),
        inv["anchors"])
    for k, v in paths.items():
        say("%-7s %s (%d bytes)", k, v, os.path.getsize(v))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
