"""`lineart-scene` -- every scene tool, as one command with one verb per tool.

**The calling convention, and why it is this one.** A capability in this ecosystem is
invoked as a command line with string arguments appended; nothing richer crosses that
boundary. A numpy array cannot be passed through it and a scene object cannot either. A
PATH can. So every transform here reads a scene from a path and writes one to a path, and
composition is a sequence of commands rather than a session.

* ``--in`` and ``--out`` take ``-`` for stdin and stdout, so tools also compose in a pipe.
* **The payload goes to stdout and the human report to stderr** -- the convention
  `lineart-trace` already follows, which is what lets a record's example check a one-line
  report instead of a megabyte of scene.
* ``--out`` is required on anything that transforms. In-place is ``--in-place``, spelled
  out, because a tool that silently overwrites its input is the destructive edit this
  toolkit exists to stop.

Exit codes, one scheme for the whole binary:

===== =========================================================================
0     it worked
1     the answer is no -- `validate` on a document that is not a scene
2     it could not be established: unreadable, unparseable, absent
3     refused: the request is well formed and cannot be satisfied
===== =========================================================================

2 is the one that earns its place. "Could not check" reported as "wrong" is a fabricated
finding, and reported as success it is the absence-into-success failure this repository
keeps catching in other guises. `lineart-trace` already exits 2 on an unreadable source;
this is that rule, made general.
"""
import argparse
import os
import sys

from . import (anchors, animate as animate_, build, data as data_,
               diagram as diagram_, fonts, glyphs as glyphs_,
               inspect as inspect_, io, layout as layout_, measure, model,
               overlay, palette, raster as raster_, report as report_,
               style as style_, svg, text as text_, validate, verify,
               watch as watch_)

__all__ = ["main", "build_parser"]

OK, NO, UNKNOWN, REFUSED = 0, 1, 2, 3


def _say(msg):
    print(msg, file=sys.stderr)


def _read(path):
    try:
        return io.load(path)
    except FileNotFoundError:
        _say(f"lineart-scene: cannot read {path}")
        raise SystemExit(UNKNOWN)
    except (ValueError, UnicodeDecodeError) as e:
        _say(f"lineart-scene: {path} is not JSON: {e}")
        raise SystemExit(UNKNOWN)


def _destination(a):
    if getattr(a, "in_place", False):
        if a.inp == "-":
            _say("lineart-scene: --in-place needs a file, not stdin")
            raise SystemExit(REFUSED)
        return a.inp
    if not a.out:
        _say("lineart-scene: this verb writes a scene, so it needs --out "
             "(or --in-place, which overwrites the input)")
        raise SystemExit(REFUSED)
    return a.out


def _io_args(p, writes=True):
    p.add_argument("--in", dest="inp", required=True, metavar="SCENE",
                   help="the scene to read; - for stdin")
    if writes:
        p.add_argument("--out", metavar="SCENE", help="where to write it; - for stdout")
        p.add_argument("--in-place", dest="in_place", action="store_true",
                       help="overwrite the input, deliberately")


def build_parser():
    p = argparse.ArgumentParser(
        prog="lineart-scene",
        description="Build, inspect, check and export a lineart-trace scene.")
    sub = p.add_subparsers(dest="verb", required=True)

    q = sub.add_parser("new", help="an empty scene")
    q.add_argument("name", help="the scene's name: lower case, digits and hyphens")
    q.add_argument("--width", type=float, required=True)
    q.add_argument("--height", type=float, required=True)
    q.add_argument("--unit", default="mm", choices=["mm", "pt", "px", "in"])
    q.add_argument("--title")
    q.add_argument("--background", default="none")
    q.add_argument("--out", metavar="SCENE", help="where to write it; - for stdout")

    q = sub.add_parser("validate", help="is this a scene? 0 yes, 1 no, 2 could not tell")
    q.add_argument("path", help="the scene file to check")

    q = sub.add_parser("tree", help="the element tree")
    _io_args(q, writes=False)

    q = sub.add_parser("render", help="export SVG")
    _io_args(q, writes=False)
    q.add_argument("--out", metavar="SVG", required=True, help="- for stdout")
    q.add_argument("--fragment", action="store_true",
                   help="a bare <g> to inline, rather than a sized document")
    q.add_argument("--prefix", default="", help="prepended to every id, against collisions")
    q.add_argument("--places", type=int, default=svg.PRECISION)
    q.add_argument("--background")

    q = sub.add_parser("rename", help="rename an element and rewrite what referred to it")
    _io_args(q)
    q.add_argument("address")
    q.add_argument("new_name")

    q = sub.add_parser("remove", help="remove an element and everything beneath it")
    _io_args(q)
    q.add_argument("address")

    q = sub.add_parser("measure", help="take a measurement")
    q.add_argument("what", choices=sorted(measure.MEASURES))
    _io_args(q, writes=False)
    q.add_argument("target", help="an element or anchor address")
    q.add_argument("--frame", help="report in this frame; default the page")
    q.add_argument("--stroke", action="store_true",
                   help="for bbox: include the stroke width, not just the centreline")

    q = sub.add_parser("inventory", help="what is in this scene, counted")
    _io_args(q, writes=False)

    q = sub.add_parser("clearance", help="the gap between two elements")
    _io_args(q, writes=False)
    q.add_argument("target")
    q.add_argument("other")
    q.add_argument("--frame")
    q.add_argument("--tolerance", type=float, default=0.05)

    q = sub.add_parser("collide", help="every pair of elements whose ink overlaps")
    _io_args(q, writes=False)
    q.add_argument("--frame")
    q.add_argument("--within", help="only beneath this address")
    q.add_argument("--tolerance", type=float, default=0.05)

    q = sub.add_parser("probe", help="what is at this coordinate")
    _io_args(q, writes=False)
    q.add_argument("x", type=float)
    q.add_argument("y", type=float)
    q.add_argument("--frame")
    q.add_argument("--tolerance", type=float, default=0.05)

    q = sub.add_parser("textbox", help="text metrics, without drawing anything")
    q.add_argument("string")
    q.add_argument("--family", default="Helvetica")
    q.add_argument("--size", type=float, default=10.0)
    q.add_argument("--weight", default="regular")
    q.add_argument("--style", default="normal")
    q.add_argument("--width", type=float, help="fit into a box this wide")
    q.add_argument("--height", type=float, help="...and this tall")
    q.add_argument("--mode", default="wrap", choices=["wrap", "shrink", "strict"])
    q.add_argument("--unit", default="pt", choices=["mm", "pt", "px", "in"],
                   help="the unit --width, --height and --size are in (default pt)")

    q = sub.add_parser("fonts", help="the font families this installation can measure")
    q.add_argument("--match", help="only families containing this text")

    q = sub.add_parser("anchor", help="give an element a named anchor")
    _io_args(q)
    q.add_argument("element")
    q.add_argument("name")
    q.add_argument("--by", choices=sorted(anchors.RECIPES),
                   help="a recipe to derive it from the geometry")
    q.add_argument("--at", help="x,y in the element's own coordinates")
    q.add_argument("--dir", dest="direction", help="dx,dy")

    q = sub.add_parser("attach", help="declare a relation between two elements")
    _io_args(q)
    q.add_argument("element")
    q.add_argument("--to", required=True, help="the address it attaches to")
    q.add_argument("--kind", default="attach", choices=list(anchors.KINDS))
    q.add_argument("--via", help="an anchor on THIS element")
    q.add_argument("--edge", help="for --kind align")
    q.add_argument("--offset", default="0,0")

    q = sub.add_parser("solve", help="re-solve every relation and say what moved")
    _io_args(q)
    q.add_argument("--frame")
    q.add_argument("--max-iter", dest="max_iter", type=int, default=24)

    q = sub.add_parser("verify", help="is this figure correct at its printed size")
    _io_args(q, writes=False)
    q.add_argument("--rule", action="append", dest="rules", choices=list(verify.RULES))
    q.add_argument("--min-type-pt", dest="min_type_pt", type=float)
    q.add_argument("--min-stroke-pt", dest="min_stroke_pt", type=float)
    q.add_argument("--min-separation-pt", dest="min_separation_pt", type=float)
    q.add_argument("--json", action="store_true", help="the full report, not a summary")

    q = sub.add_parser("overlay", help="the annotated overlay: names, boxes, anchors")
    _io_args(q, writes=False)
    q.add_argument("--out", metavar="SVG", required=True)
    q.add_argument("--layer", action="append", dest="layers", choices=list(overlay.LAYERS))
    q.add_argument("--grid", type=float, default=10.0)
    q.add_argument("--scale", type=float, default=1.0)
    q.add_argument("--check", action="store_true",
                   help="run the verification and mark what it finds")
    q.add_argument("--depth", type=int, default=2,
                   help="how many levels of the tree to annotate; 0 for all")
    q.add_argument("--payload", metavar="JSON",
                   help="also write the payload the view was given")

    q = sub.add_parser("inspect", help="an interactive page: click a figure, learn names")
    _io_args(q, writes=False)
    q.add_argument("--out", metavar="HTML", required=True, help="- for stdout")
    q.add_argument("--depth", type=int, default=3, help="levels to make clickable; 0 all")
    q.add_argument("--guide", help="also lint against this guide and mark what it finds")
    q.add_argument("--no-check", dest="check", action="store_false", default=True)

    q = sub.add_parser("watch", help="live preview: re-renders when the scene file changes")
    _io_args(q, writes=False)
    q.add_argument("--port", type=int, default=8765, help="0 picks a free one")
    q.add_argument("--depth", type=int, default=3)
    q.add_argument("--guide")
    q.add_argument("--no-check", dest="check", action="store_false", default=True)
    q.add_argument("--once", action="store_true",
                   help="render one page to stdout and exit, instead of serving")

    q = sub.add_parser("compare", help="two versions of a figure, side by side or wiped")
    _io_args(q, writes=False)
    q.add_argument("--out", metavar="HTML", required=True)
    q.add_argument("--against", metavar="SCENE", help="another scene to compare with")
    q.add_argument("--guide", help="...or render this one under another guide")
    q.add_argument("--variant", help="...or under a variant of its own guide")
    q.add_argument("--mode", default="onion", choices=["onion", "side-by-side"])

    q = sub.add_parser("contact", help="a contact sheet of variants or build stages")
    _io_args(q, writes=False)
    q.add_argument("--out", metavar="HTML", required=True)
    q.add_argument("--variant", action="append", default=[],
                   help="a variant of the scene's guide; repeatable")
    q.add_argument("--guide", action="append", default=[],
                   help="a whole guide; repeatable")
    q.add_argument("--timeline", metavar="TIMELINE",
                   help="...or a sheet of this build's stages")

    q = sub.add_parser("truesize", help="a preview at the figure's real printed size")
    _io_args(q, writes=False)
    q.add_argument("--out", metavar="HTML", required=True)

    q = sub.add_parser("describe", help="what is in this figure, in plain language")
    _io_args(q, writes=False)
    q.add_argument("--guide")
    q.add_argument("--reference", metavar="PNG")

    q = sub.add_parser("report", help="every check over a figure, in one report")
    _io_args(q, writes=False)
    q.add_argument("--guide", help="also lint against this style guide")
    q.add_argument("--reference", metavar="PNG", help="also compare against this image")
    q.add_argument("--dpi", type=float, default=150.0)
    q.add_argument("--tolerance", type=float, default=0.0,
                   help="fraction of pixels allowed to differ")
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("snapshot", help="write the reference image a regression compares to")
    _io_args(q, writes=False)
    q.add_argument("--out", metavar="PNG", required=True)
    q.add_argument("--dpi", type=float, default=150.0)

    q = sub.add_parser("regress", help="has this figure changed since the reference?")
    _io_args(q, writes=False)
    q.add_argument("--reference", metavar="PNG", required=True)
    q.add_argument("--diff", metavar="PNG", help="write an image marking what differs")
    q.add_argument("--dpi", type=float, default=150.0)
    q.add_argument("--tolerance", type=float, default=0.0)

    q = sub.add_parser("build", help="a timeline from a staged reveal")
    _io_args(q, writes=False)
    q.add_argument("name")
    q.add_argument("--stages", required=True,
                   help='JSON: [{"name":"one","reveal":["a"],"hold":1.0}, ...]')
    q.add_argument("--rise", type=float, default=0.4)
    q.add_argument("--hold", type=float, default=1.0)
    q.add_argument("--loop", action="store_true")
    q.add_argument("--out", metavar="TIMELINE", required=True, help="- for stdout")

    q = sub.add_parser("still", help="the scene at one stage of a build")
    _io_args(q)
    q.add_argument("--timeline", required=True, metavar="TIMELINE")
    q.add_argument("--stage", help="a stage or mark name; omit and use --at")
    q.add_argument("--at", dest="when", type=float, help="a time in seconds")
    q.add_argument("--keep-hidden", dest="drop_hidden", action="store_false",
                   default=True)

    q = sub.add_parser("animate", help="one self-contained animated SVG")
    _io_args(q, writes=False)
    q.add_argument("--timeline", required=True, metavar="TIMELINE")
    q.add_argument("--out", metavar="SVG", required=True)
    q.add_argument("--places", type=int, default=3)

    q = sub.add_parser("node", help="a diagram node sized to its label")
    _io_args(q)
    q.add_argument("name")
    q.add_argument("label")
    q.add_argument("--at", default="0,0")
    q.add_argument("--shape", default="rect", choices=["rect", "ellipse", "diamond"])
    q.add_argument("--max-width", dest="max_width", type=float,
                   help="wrap the label to this width")
    q.add_argument("--parent", default="")
    q.add_argument("--frame")

    q = sub.add_parser("link", help="an edge between two nodes, routed round what is in the way")
    _io_args(q)
    q.add_argument("name")
    q.add_argument("--from", dest="a", required=True)
    q.add_argument("--to", dest="b", required=True)
    q.add_argument("--label")
    q.add_argument("--kind", default="arrow", choices=["arrow", "both", "open", "none"])
    q.add_argument("--clearance", type=float, default=1.5)
    q.add_argument("--resolution", type=float, default=0.5)
    q.add_argument("--straight", dest="routed", action="store_false", default=True)
    q.add_argument("--parent", default="")

    q = sub.add_parser("container", help="a box that fits around the elements it names")
    _io_args(q)
    q.add_argument("name")
    q.add_argument("members", nargs="+")
    q.add_argument("--label")
    q.add_argument("--pad", type=float, default=3.0)
    q.add_argument("--parent", default="")

    q = sub.add_parser("flowchart", help="a whole layered diagram from a node and edge spec")
    _io_args(q)
    q.add_argument("--nodes", required=True,
                   help='JSON: {"name": "label", ...}')
    q.add_argument("--edges", required=True,
                   help='JSON: [["a","b"], ["b","c","label"], ...]')
    q.add_argument("--at", default="0,0")
    q.add_argument("--spacing", default="10,14")
    q.add_argument("--horizontal", dest="vertical", action="store_false", default=True)
    q.add_argument("--parent", default="")
    q.add_argument("--frame")

    q = sub.add_parser("plot", help="a plot panel built from a data file")
    _io_args(q)
    q.add_argument("name")
    q.add_argument("--data", required=True, metavar="CSV")
    q.add_argument("--x", required=True, help="the column for the x axis")
    q.add_argument("--y", required=True, help="the column for the y axis")
    q.add_argument("--kind", default="scatter",
                   choices=["scatter", "line", "area", "bar", "box"])
    q.add_argument("--size", default="54,44", help="w,h of the panel")
    q.add_argument("--at", default="0,0")
    q.add_argument("--xlabel")
    q.add_argument("--ylabel")
    q.add_argument("--title")
    q.add_argument("--errors", help="a column of error half-widths")
    q.add_argument("--fit", action="store_true", help="add a least-squares line and band")
    q.add_argument("--no-grid", dest="grid", action="store_false", default=True)
    q.add_argument("--ticks", type=int, default=5)
    q.add_argument("--parent", default="")
    q.add_argument("--frame")

    q = sub.add_parser("glyph", help="place a parameterised glyph into a scene")
    _io_args(q)
    q.add_argument("glyph", help="a glyph id, such as dna.duplex")
    q.add_argument("name", help="what to call the instance")
    q.add_argument("--at", default="0,0", help="x,y")
    q.add_argument("--args", help="a JSON object of the glyph's parameters")
    q.add_argument("--parent", default="")
    q.add_argument("--frame")

    q = sub.add_parser("glyphs", help="the glyph catalogue, or one glyph's parameters")
    q.add_argument("glyph", nargs="?", help="describe just this one")
    q.add_argument("--family", help="only this family")

    q = sub.add_parser("promote", help="capture a scene subtree as a reusable glyph")
    _io_args(q, writes=False)
    q.add_argument("address")
    q.add_argument("glyph", help="the id to give it")
    q.add_argument("--version", default="1")
    q.add_argument("--out", metavar="JSON", required=True, help="- for stdout")

    q = sub.add_parser("panels", help="lay a grid of panel frames over the page")
    _io_args(q)
    q.add_argument("--rows", type=int, default=1)
    q.add_argument("--cols", type=int, default=2)
    q.add_argument("--gutter", type=float, default=4.0)
    q.add_argument("--margin", type=float, default=3.0)
    q.add_argument("--letters", default="A", help="first panel letter; '' for none")
    q.add_argument("--no-areas", dest="area_guides", action="store_false", default=True)

    q = sub.add_parser("reflow", help="retarget the figure to a different page size")
    _io_args(q)
    q.add_argument("--width", type=float)
    q.add_argument("--height", type=float)
    q.add_argument("--rows", type=int, help="re-lay on a different grid")
    q.add_argument("--cols", type=int)
    q.add_argument("--gutter", type=float)
    q.add_argument("--margin", type=float)

    q = sub.add_parser("distribute", help="space elements evenly along an axis")
    _io_args(q)
    q.add_argument("addresses", nargs="+")
    q.add_argument("--axis", default="x", choices=["x", "y"])
    q.add_argument("--spacing", type=float)
    q.add_argument("--frame")

    q = sub.add_parser("pack", help="lay elements into a target's area, wrapping")
    _io_args(q)
    q.add_argument("into")
    q.add_argument("addresses", nargs="+")
    q.add_argument("--gap", type=float, default=2.0)
    q.add_argument("--frame")

    q = sub.add_parser("connect", help="draw a routed connector that goes round obstacles")
    _io_args(q)
    q.add_argument("name")
    q.add_argument("--from", dest="start", required=True, help="x,y")
    q.add_argument("--to", dest="end", required=True, help="x,y")
    q.add_argument("--avoid", action="append", default=[],
                   help="an address to route around; repeatable")
    q.add_argument("--clearance", type=float, default=1.5)
    q.add_argument("--resolution", type=float, default=1.0)
    q.add_argument("--kind", default="orthogonal",
                   choices=["orthogonal", "curved", "straight"])
    q.add_argument("--arrow", type=float, default=0.0)
    q.add_argument("--radius", type=float, default=0.0)
    q.add_argument("--role")
    q.add_argument("--style", dest="style_json")
    q.add_argument("--frame")

    q = sub.add_parser("style", help="apply a style guide to a scene")
    _io_args(q)
    q.add_argument("guide", help="a guide name, or a path to one")
    q.add_argument("--variant", help="a named variant of it, such as dark or print")

    q = sub.add_parser("adopt", help="turn a scene's literal styles into roles")
    _io_args(q)
    q.add_argument("--guide", help="match against this guide's roles where they fit")
    q.add_argument("--variant")
    q.add_argument("--prefix", default="adopted")

    q = sub.add_parser("lint", help="what is off-guide in this scene")
    _io_args(q, writes=False)
    q.add_argument("--guide")
    q.add_argument("--variant")
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("palette", help="generate or check a set of distinguishable colours")
    q.add_argument("colours", nargs="*", help="check these; omit to generate")
    q.add_argument("-n", "--count", type=int, default=0, help="how many to generate")
    q.add_argument("--background", default="#ffffff")
    q.add_argument("--min-contrast", dest="min_contrast", type=float, default=3.0)
    q.add_argument("--min-delta-e", dest="min_delta_e", type=float, default=20.0)

    q = sub.add_parser("guides", help="the style guides this installation can reach")

    q = sub.add_parser("add", help="add a primitive to a scene")
    _io_args(q)
    q.add_argument("shape", choices=["rect", "circle", "ellipse", "line", "polyline",
                                     "polygon", "star", "text", "arrow", "group"])
    q.add_argument("name")
    q.add_argument("--at", default="0,0", help="x,y")
    q.add_argument("--size", help="w,h")
    q.add_argument("--radius", type=float, default=0.0)
    q.add_argument("--points", help="x,y x,y ...")
    q.add_argument("--sides", type=int, default=5)
    q.add_argument("--text", dest="string")
    q.add_argument("--font", default="Helvetica")
    q.add_argument("--font-size", dest="font_size", type=float, default=10.0)
    q.add_argument("--dir", dest="direction", default="1,0")
    q.add_argument("--style", help="a JSON object of literal style values")
    q.add_argument("--role")
    q.add_argument("--parent", default="")
    q.add_argument("--frame")
    return p


def _pair(s, what):
    try:
        a, b = str(s).split(",")
        return float(a), float(b)
    except (ValueError, AttributeError):
        raise SystemExit(f"lineart-scene: {what} wants two numbers as x,y -- got {s!r}")


# --------------------------------------------------------------------- the verbs
# Each verb is a function carrying its own description, and the `C11:` block in its
# docstring is what `lineart_trace.records` turns into a capability record. Nothing about
# these records is written by hand: a description copied into a separate file is a second
# source that drifts silently, and this is the arrangement that makes that impossible.


def verb_new(a):
    """Start a new empty scene: a canvas at a physical size, and nothing on it yet.

    C11:
      noun: scene
      verb: create
      tags: scene, svg, figure, canvas
      produces: scene.document
      returns: the scene document on stdout, or to --out; a one-line size report on stderr
      phrases:
        - start a new scene
        - create an empty figure at a physical size
        - make a scene to draw into
        - set up a canvas in millimetres
      requires:
        - lineart_trace/scene/model.py: the scene model the document is built by
      example: demo --width 90 --height 60 --out /dev/null
    """
    if not model.NAME_RE.match(a.name):
        _say(f"lineart-scene: {a.name!r} is not a usable name "
             f"(lower case, digits and hyphens, no dots)")
        return REFUSED
    doc = model.new(a.name, a.width, a.height, a.unit, a.title, a.background)
    io.dump(doc, a.out or "-")
    _say(f"[{a.name}] {a.width:g}x{a.height:g}{a.unit}, 0 elements")
    return OK


def verb_validate(a):
    """Check that a file really is a scene, and say what is wrong with it if it is not.

    Answers by exit code: 0 it conforms, 1 it does not and the reasons are on stdout, 2 it
    could not be checked at all. The third is never given the code of either other.

    C11:
      noun: scene
      verb: validate
      tags: scene, validation, schema, conformance
      accepts: scene.document
      returns: nothing on stdout when it conforms; one line per problem when it does not
      phrases:
        - is this file a valid scene
        - check a scene against its schema
        - what is wrong with this scene
        - validate a scene document
      requires:
        - lineart_trace/scene/scene.schema.json: the schema, which is its single source
        - lineart_trace/scene/validate.py: the checks a JSON Schema cannot state
      example: tests/fixtures/scene-polymerase.json
    """
    code, lines = validate.check(a.path)
    for line in lines:
        if line.startswith("scene.validate:"):
            _say(line)
        else:
            print(line)
    if code == OK:
        _say(f"[{a.path}] conforms")
    elif code == NO:
        _say(f"[{a.path}] is not a scene: "
             f"{sum(1 for x in lines if x.startswith('not a scene'))} problem(s)")
    return code


def verb_tree(a):
    """List what is in a scene: every element by name, indented, with its type and role.

    C11:
      noun: scene
      verb: tree
      tags: scene, tree, elements, names, listing
      accepts: scene.document
      returns: the indented element tree on stdout, a count on stderr
      phrases:
        - what is in this scene
        - list the elements of a figure
        - show the element tree
        - what are the names of things in this scene
      requires:
        - lineart_trace/scene/model.py: the traversal
      example: --in tests/fixtures/scene-polymerase.json
    """
    doc = _read(a.inp)
    text = model.tree(doc)
    if text:
        print(text)
    _say(f"[{doc.get('name', '?')}] {len(model.addresses(doc))} elements")
    return OK


def verb_render(a):
    """Export a scene to SVG, sized in its own physical units.

    C11:
      noun: scene
      verb: export
      tags: svg, export, render, figure, output
      accepts: scene.document
      returns: the SVG, to --out or stdout; a size report on stderr
      phrases:
        - export a scene to SVG
        - turn a scene into an SVG file
        - render a figure at its printed size
        - write the scene out as vector art
      requires:
        - lineart_trace/scene/svg.py: the exporter
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null
    """
    doc = _read(a.inp)
    try:
        text = svg.render(doc, standalone=not a.fragment, prefix=a.prefix,
                          places=a.places, background=a.background)
    except NotImplementedError as e:
        _say(f"lineart-scene: refusing to render: {e}")
        return REFUSED
    if a.out == "-":
        sys.stdout.write(text)
    else:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    n = len(model.addresses(doc))
    _say(f"[{doc.get('name', '?')}] {n} elements -> "
         f"{'fragment' if a.fragment else 'svg'}, {len(text)} bytes")
    return OK


def verb_rename(a):
    """Rename an element, and rewrite every reference that named it or anything beneath it.

    C11:
      noun: scene
      verb: rename
      tags: scene, elements, names, edit
      accepts: scene.document
      produces: scene.document
      returns: the edited scene to --out; the reference count on stderr
      phrases:
        - rename an element in a scene
        - give this shape a better name
        - change a name and keep the references working
      requires:
        - lineart_trace/scene/model.py: the rename and the reference rewrite
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null art drawing
    """
    return _edit(a)


def verb_remove(a):
    """Remove an element from a scene, and everything beneath it.

    C11:
      noun: scene
      verb: remove
      tags: scene, elements, edit, delete
      accepts: scene.document
      produces: scene.document
      returns: the edited scene to --out; what went, on stderr
      phrases:
        - delete an element from a scene
        - remove a shape and its children
        - take this group out of the figure
      requires:
        - lineart_trace/scene/model.py: the removal
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null art.ink
    """
    return _edit(a)


def _edit(a):
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        if a.verb == "rename":
            doc, n = model.rename(doc, a.address, a.new_name)
            note = f"{a.address} -> {a.new_name}, {n} reference(s) rewritten"
        else:
            doc = model.remove(doc, a.address)
            note = f"{a.address} removed"
    except KeyError:
        _say(f"lineart-scene: {a.address} is nothing in this scene")
        return UNKNOWN
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(doc, dest)
    _say(f"[{doc.get('name', '?')}] {note}")
    return OK


def verb_measure(a):
    """Measure an element: its bounding box, in a frame you name and the unit that frame uses.

    The box is the CONTROL-POINT bound, which contains the curve and is not tight to it, and
    it is of the centreline rather than of the inked stroke. §3.2's tight ink extent
    replaces it.

    C11:
      noun: scene
      verb: measure
      tags: measurement, bbox, extent, geometry, scene
      accepts: scene.document
      produces: scene.measurement
      returns: a measurement document on stdout, a one-line summary on stderr
      phrases:
        - how big is this element
        - bounding box of a scene element
        - measure a figure before placing something next to it
        - what are the extents of this group in millimetres
      requires:
        - lineart_trace/scene/measure.py: the measurement and its envelope
      example: bbox --in tests/fixtures/scene-polymerase.json art
    """
    doc = _read(a.inp)
    try:
        fn = measure.MEASURES[a.what]
        out = fn(doc, a.target, a.frame, stroke=a.stroke) if a.what == "bbox" \
            else fn(doc, a.target, a.frame)
    except measure.Unmeasurable as e:
        _say(f"lineart-scene: cannot establish that: {e}")
        return UNKNOWN
    except KeyError:
        _say(f"lineart-scene: {a.target} is nothing in this scene")
        return UNKNOWN
    except (ValueError, NotImplementedError) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    sys.stdout.write(io.dumps(out))
    v = out["value"]
    if a.what == "bbox":
        _say(f"[{a.target}] bbox {v['width']:.4g}x{v['height']:.4g}{out['unit']} "
             f"at ({v['x']:.4g}, {v['y']:.4g}) in {out['frame']}")
    elif isinstance(v, dict):
        _say(f"[{a.target}] {a.what} "
             + " ".join(f"{k}={v[k]:.4g}" if isinstance(v[k], float) else f"{k}={v[k]}"
                        for k in sorted(v))
             + f" ({out['unit']}, {out['frame']})")
    else:
        _say(f"[{a.target}] {a.what} {v:.6g}{out['unit']} in {out['frame']}")
    return OK




def verb_inventory(a):
    """Say what is in a scene: how many of each type, which roles, colours, fonts and frames.

    C11:
      noun: scene
      verb: inventory
      tags: inventory, scene, colours, audit, summary
      accepts: scene.document
      produces: scene.measurement
      returns: the inventory on stdout, a one-line summary on stderr
      phrases:
        - what is in this figure
        - what colours does this scene use
        - summarise a scene in plain terms
        - which fonts and roles does this figure use
      requires:
        - lineart_trace/scene/measure.py: the inventory
      example: --in tests/fixtures/scene-polymerase.json
    """
    doc = _read(a.inp)
    out = measure.inventory(doc)
    sys.stdout.write(io.dumps(out))
    v = out["value"]
    _say(f"[{doc.get('name', '?')}] {v['elements']} elements, "
         f"{len(v['colours'])} colours, {len(v['roles'])} roles, "
         f"{v['anchors']} anchors, frames {', '.join(v['frames'])}")
    return OK


def verb_clearance(a):
    """Measure the gap between two elements: zero when they touch, otherwise how far apart.

    C11:
      noun: scene
      verb: gap
      tags: clearance, distance, spacing, collision, measurement
      accepts: scene.document
      produces: scene.measurement
      returns: a measurement on stdout; the gap on stderr
      phrases:
        - how far apart are these two elements
        - is there enough space between the label and the arrow
        - clearance between two shapes
        - do these two touch
      requires:
        - lineart_trace/scene/measure.py: the clearance measure
      example: --in tests/fixtures/scene-polymerase.json art.ink.stroke-001 art
    """
    doc = _read(a.inp)
    try:
        out = measure.clearance(doc, a.target, a.other, a.frame, a.tolerance)
    except measure.Unmeasurable as e:
        _say(f"lineart-scene: cannot establish that: {e}")
        return UNKNOWN
    except KeyError as e:
        _say(f"lineart-scene: {e.args[0]} is nothing in this scene")
        return UNKNOWN
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    sys.stdout.write(io.dumps(out))
    v = out["value"]
    _say(f"[{a.target} .. {a.other}] "
         + ("they overlap" if v["overlaps"] else f"{v['gap']:.4g}{out['unit']} apart"))
    return OK


def verb_collide(a):
    """Find every pair of elements whose ink overlaps.

    C11:
      noun: scene
      verb: collide
      tags: overlap, collision, verification, layout
      accepts: scene.document
      produces: scene.measurement
      returns: the pairs on stdout, a count on stderr
      phrases:
        - what overlaps in this figure
        - find colliding elements
        - do any labels sit on top of each other
        - check a scene for overlapping shapes
      requires:
        - lineart_trace/scene/measure.py: the collision scan
      example: --in tests/fixtures/scene-polymerase.json
    """
    doc = _read(a.inp)
    out = measure.collisions(doc, a.frame, a.tolerance, a.within)
    sys.stdout.write(io.dumps(out))
    v = out["value"]
    _say(f"[{doc.get('name', '?')}] {v['count']} overlapping pair(s) "
         f"among {v['compared']} elements")
    return OK


def verb_probe(a):
    """Say what is at a coordinate: every element whose ink covers it, innermost last.

    C11:
      noun: scene
      verb: probe
      tags: hit-test, coordinate, inspection, pick
      accepts: scene.document
      produces: scene.measurement
      returns: the hits on stdout, a count on stderr
      phrases:
        - what is at this point in the figure
        - which element is at these coordinates
        - pick an element by position
        - what did I just click on
      requires:
        - lineart_trace/scene/measure.py: the hit test
      example: --in tests/fixtures/scene-polymerase.json 40 40
    """
    doc = _read(a.inp)
    out = measure.probe(doc, a.x, a.y, a.frame, a.tolerance)
    sys.stdout.write(io.dumps(out))
    hits = out["value"]["hits"]
    _say(f"[({a.x:g}, {a.y:g})] {len(hits)} hit(s)"
         + (": " + ", ".join(h["address"] for h in hits) if hits else ""))
    return OK


def verb_textbox(a):
    """Measure text without drawing it, and say whether it fits a box you name.

    C11:
      noun: text
      verb: measure
      tags: text, metrics, typography, fit, label, font
      produces: scene.measurement
      returns: the metrics on stdout; with --width and --height, the lines it would take
      phrases:
        - how wide is this text
        - will this label fit in the box
        - text metrics without rendering
        - how many lines will this caption wrap to
        - measure a string in a font at a size
      requires:
        - lineart_trace/scene/fonts.py: the font tables this reads
        - lineart_trace/scene/text.py: the fitting
      example: "Polymerase" --family Helvetica --size 9
    """
    try:
        if a.width and a.height:
            laid = text_.fit(a.string, a.width, a.height, a.family, a.size, a.mode,
                             weight=a.weight, style=a.style, unit=a.unit)
            out = {"format": "lineart.measurement/1", "measure": "fit",
                   "target": a.string, "frame": "page", "unit": "pt",
                   "value": {k: laid[k] for k in ("lines", "size", "width", "height",
                                                  "slack_width", "slack_height",
                                                  "line_height", "shrunk")},
                   "font": laid["font"]}
            sys.stdout.write(io.dumps(out))
            _say(f"[{a.string!r}] fits as {len(laid['lines'])} line(s) at "
                 f"{laid['size']:.4g}: {laid['width']:.4g}x{laid['height']:.4g} "
                 f"in {a.width:g}x{a.height:g}")
            return OK
        out = measure.text(a.string, a.family, a.size, a.weight, a.style)
    except fonts.FontNotFound as e:
        _say(f"lineart-scene: {e}")
        return UNKNOWN
    except text_.TooBig as e:
        sys.stdout.write(io.dumps(e.detail))
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    sys.stdout.write(io.dumps(out))
    v = out["value"]
    _say(f"[{a.string!r}] {v['advance']:.4g} wide, {v['ascent']:.4g} up / "
         f"{v['descent']:.4g} down, line {v['line_height']:.4g} "
         f"({out['font']['family']} {out['font']['subfamily']})")
    return OK


def verb_fonts(a):
    """List the font families this installation can measure, and where they came from.

    C11:
      noun: font
      verb: list
      tags: fonts, typography, families, availability
      returns: one family per line on stdout, a count on stderr
      phrases:
        - which fonts can I use
        - list available font families
        - is Helvetica available for measuring
        - what typefaces does this machine have
      requires:
        - lineart_trace/scene/fonts.py: the index
      example: --match Courier
    """
    idx = fonts.families()
    rows = []
    for fam in sorted(idx):
        faces = idx[fam]
        name = faces[0][0]
        if a.match and a.match.lower() not in fam:
            continue
        rows.append(f"{fam}\t{len(faces)} face(s)\t{os.path.dirname(faces[0][0])}")
    for r in rows:
        print(r)
    _say(f"{len(rows)} famil{'y' if len(rows) == 1 else 'ies'} of {len(idx)} found in "
         f"{len(fonts.font_dirs())} director{'y' if len(fonts.font_dirs()) == 1 else 'ies'}")
    return OK


def verb_anchor(a):
    """Give an element a named anchor, either a point you choose or a recipe over its shape.

    C11:
      noun: anchor
      verb: declare
      tags: anchor, attach, geometry, naming, relations
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; the anchor's resolved position on stderr
      phrases:
        - put a named point on this shape
        - add an anchor to an element
        - find the deepest concavity of a silhouette
        - give this element a tip I can attach to
      requires:
        - lineart_trace/scene/anchors.py: the recipes and their resolution
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null art east --by bbox.e
    """
    doc = _read(a.inp)
    dest = _destination(a)
    if not (a.by or a.at):
        _say("lineart-scene: an anchor needs --by (a recipe) or --at (a point)")
        return REFUSED
    el = model.find(doc, a.element)
    if el is None:
        _say(f"lineart-scene: {a.element} is nothing in this scene")
        return UNKNOWN
    if not model.NAME_RE.match(a.name):
        _say(f"lineart-scene: {a.name!r} is not a usable anchor name")
        return REFUSED
    body = {"how": "authored" if a.at else
            ("discovered" if a.by == "concavity" else "derived")}
    if a.by:
        body["by"] = a.by
    if a.at:
        x, y = _pair(a.at, "--at")
        body["at"] = [x, y]
    if a.direction:
        dx, dy = _pair(a.direction, "--dir")
        body["dir"] = [dx, dy]
    el.setdefault("anchors", {})[a.name] = body
    if a.by:
        try:
            pt, direction = anchors.derive(doc, a.element, a.by)
        except ValueError as e:
            _say(f"lineart-scene: refusing: {e}")
            return REFUSED
        body["at"] = [pt[0], pt[1]]
        if direction:
            body["dir"] = [direction[0], direction[1]]
    io.dump(doc, dest)
    _say(f"[{a.element}.{a.name}] at ({body['at'][0]:.4g}, {body['at'][1]:.4g}) "
         f"({body['how']}{', ' + a.by if a.by else ''})")
    return OK


def verb_attach(a):
    """Declare that an element is positioned relative to another, and solve for where.

    C11:
      noun: relation
      verb: attach
      tags: attach, align, constraint, layout, relations, anchor
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; what moved, on stderr
      phrases:
        - attach this label to that anchor
        - keep this arrow pointing at the active site
        - align two elements
        - keep these two clear of each other
        - make one element follow another when it moves
      requires:
        - lineart_trace/scene/anchors.py: the solver
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null art.ink --to art --kind align --edge centre-x
    """
    doc = _read(a.inp)
    dest = _destination(a)
    el = model.find(doc, a.element)
    if el is None:
        _say(f"lineart-scene: {a.element} is nothing in this scene")
        return UNKNOWN
    rel = {"kind": a.kind, "to": a.to}
    if a.via:
        rel["via"] = a.via
    if a.edge:
        rel["edge"] = a.edge
    ox, oy = _pair(a.offset, "--offset")
    if ox or oy:
        rel["offset"] = [ox, oy]
    el.setdefault("relations", []).append(rel)
    bad, _warn = validate.problems(doc)
    if bad:
        _say("lineart-scene: refusing, that relation would not be a valid scene:")
        for b in bad:
            _say(f"  {b}")
        return REFUSED
    out, report = anchors.solve(doc)
    io.dump(out, dest)
    moved = report["moved"].get(a.element)
    _say(f"[{a.element}] {a.kind} -> {a.to}; "
         + (f"moved ({moved['dx']:.4g}, {moved['dy']:.4g})" if moved else "already there")
         + (f"; {len(report['unsatisfiable'])} unsatisfiable"
            if report["unsatisfiable"] else ""))
    return OK


def verb_solve(a):
    """Re-solve every relation in the scene, and report what moved and what could not.

    C11:
      noun: scene
      verb: solve
      tags: layout, constraints, relations, anchors, resolve
      accepts: scene.document
      produces: scene.document
      returns: the solved scene to --out; the report on stderr
      phrases:
        - re-solve the layout after an edit
        - update everything attached to what I just moved
        - resolve the anchors and relations in this figure
        - recompute a figure's layout
      requires:
        - lineart_trace/scene/anchors.py: the solver
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null
    """
    doc = _read(a.inp)
    dest = _destination(a)
    out, report = anchors.solve(doc, a.frame, a.max_iter)
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {report['passes']} pass(es), "
         f"{len(report['moved'])} element(s) moved, "
         f"{len(report['anchors']['resolved'])} anchor(s) resolved"
         + (f", {len(report['unsatisfiable'])} UNSATISFIABLE"
            if report["unsatisfiable"] else "")
         + ("" if report["settled"] else ", DID NOT SETTLE"))
    for item in report["unsatisfiable"]:
        _say(f"  unsatisfiable: {item['element']}: {item['why']}")
    for item in report["unsettled"]:
        _say(f"  never settled: {item['element']} {item['kind']} -> {item['to']}, "
             f"short by {item['short_by']:.4g}")
    return NO if (report["unsatisfiable"] or not report["settled"]) else OK


def verb_verify(a):
    """Check a figure at its printed size: type too small, rules too fine, things off-canvas.

    C11:
      noun: figure
      verb: verify
      tags: verification, legibility, contrast, accessibility, print, colourblind
      accepts: scene.document
      returns: one line per finding on stdout; counts on stderr; exit 1 if anything is wrong
      phrases:
        - is this figure legible at column width
        - check a figure before submitting it
        - will this print correctly
        - is this colourblind safe
        - what is wrong with this figure
      requires:
        - lineart_trace/scene/verify.py: the checks and their thresholds
      example: --in tests/fixtures/scene-polymerase.json
    """
    doc = _read(a.inp)
    th = {k: getattr(a, k) for k in
          ("min_type_pt", "min_stroke_pt", "min_separation_pt")
          if getattr(a, k, None) is not None}
    _solved, report = anchors.solve(doc)
    got = verify.check(doc, a.rules, th, solve_report=report)
    if a.json:
        sys.stdout.write(io.dumps(got))
    else:
        for f in got["findings"]:
            print(f"{f['severity']:7}  {f['rule']:22}  {f['element'] or '-'}: "
                  f"{f['message']}")
        for u in got["unchecked"]:
            print(f"unknown  {u['rule']:22}  {u['element'] or '-'}: {u['why']}")
    _say(f"[{doc.get('name', '?')}] {got['errors']} error(s), {got['warnings']} "
         f"warning(s), {len(got['unchecked'])} unchecked, at "
         f"{got['canvas']['width']:g}x{got['canvas']['height']:g}"
         f"{got['canvas']['unit']}")
    return NO if got["errors"] else OK


def verb_overlay(a):
    """Draw the figure with its structure on top: names, boxes, anchors and relations.

    C11:
      noun: scene
      verb: annotate
      tags: overlay, preview, debug, anchors, names, inspection
      accepts: scene.document
      returns: an annotated SVG to --out; a summary on stderr
      phrases:
        - show me what this figure is made of
        - draw the anchors and bounding boxes
        - annotated preview of a scene
        - which element is which in this figure
      requires:
        - lineart_trace/scene/overlay.py: the view
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null
    """
    doc = _read(a.inp)
    findings = None
    if a.check:
        _solved, report = anchors.solve(doc)
        findings = verify.check(doc, solve_report=report)["findings"]
    load = overlay.payload(doc, grid=a.grid, findings=findings,
                           depth=(a.depth or None))
    text = overlay.render(load, tuple(a.layers) if a.layers else overlay.LAYERS,
                          scale=a.scale)
    if a.out == "-":
        sys.stdout.write(text)
    else:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    if a.payload:
        io.dump(load, a.payload)
    _say(f"[{doc.get('name', '?')}] overlay of {len(model.addresses(doc))} elements, "
         f"{len(text)} bytes"
         + (f", {len(findings)} finding(s) marked" if findings is not None else ""))
    return OK


def verb_add(a):
    """Add a primitive to a scene: a rectangle, ellipse, polygon, line, star or text run.

    C11:
      noun: element
      verb: draw
      tags: primitive, shape, rectangle, ellipse, polygon, text, construction
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; what was added, on stderr
      phrases:
        - add a rectangle to the figure
        - draw a circle in this scene
        - put a text label in a figure
        - add a shape by name
      requires:
        - lineart_trace/scene/build.py: the primitives
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null rect frame --at 2,2 --size 20,10
    """
    doc = _read(a.inp)
    dest = _destination(a)
    if not model.NAME_RE.match(a.name):
        _say(f"lineart-scene: {a.name!r} is not a usable element name")
        return REFUSED
    style = None
    if a.style:
        import json as _json
        try:
            style = _json.loads(a.style)
        except ValueError as e:
            _say(f"lineart-scene: --style is not JSON: {e}")
            return REFUSED
    x, y = _pair(a.at, "--at")
    w = h = None
    if a.size:
        w, h = _pair(a.size, "--size")
    pts = None
    if a.points:
        pts = [_pair(p, "--points") for p in a.points.split()]
    try:
        if a.shape == "rect":
            el = build.rect(a.name, x, y, w or 10, h or 10, a.radius, a.role, style)
        elif a.shape == "circle":
            el = build.circle(a.name, x, y, a.radius or (w or 10) / 2, a.role, style)
        elif a.shape == "ellipse":
            el = build.ellipse(a.name, x, y, (w or 10) / 2, (h or 10) / 2,
                               role=a.role, style=style)
        elif a.shape == "line":
            if not pts or len(pts) < 2:
                _say("lineart-scene: a line needs --points 'x,y x,y'")
                return REFUSED
            el = build.line(a.name, pts[0], pts[1], a.role, style)
        elif a.shape == "polyline":
            el = build.polyline(a.name, pts or [], role=a.role, style=style)
        elif a.shape == "polygon":
            el = build.polygon(a.name, x, y, a.radius or 10, a.sides, role=a.role,
                               style=style)
        elif a.shape == "star":
            el = build.star(a.name, x, y, a.radius or 10, (a.radius or 10) / 2.5,
                            a.sides, role=a.role, style=style)
        elif a.shape == "text":
            if not a.string:
                _say("lineart-scene: a text element needs --text")
                return REFUSED
            el = build.text(a.name, a.string, (x, y), a.font, a.font_size, role=a.role,
                            style=style)
        elif a.shape == "arrow":
            el = build.arrowhead(a.name, (x, y), _pair(a.direction, "--dir"),
                                 a.radius or 3.0, role=a.role, style=style)
        else:
            el = build.group(a.name, [], frame=a.frame, role=a.role)
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    if a.frame and a.shape != "group":
        el["frame"] = a.frame
    try:
        doc = model.add(doc, el, a.parent)
    except KeyError:
        _say(f"lineart-scene: {a.parent} is nothing in this scene")
        return UNKNOWN
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(doc, dest)
    where = f"{a.parent}.{a.name}" if a.parent else a.name
    _say(f"[{doc.get('name', '?')}] added {a.shape} {where}")
    return OK





def verb_style(a):
    """Apply a style guide to a scene, so every element drawn by role changes at once.

    C11:
      noun: style
      verb: apply
      tags: style, guide, theme, roles, consistency, restyle
      accepts: scene.document
      produces: scene.document
      returns: the restyled scene to --out; what it bound, on stderr
      phrases:
        - apply a style guide to this figure
        - restyle a figure for a different journal
        - make this figure dark
        - use the house style on this scene
        - re-theme a figure without editing it
      requires:
        - lineart_trace/scene/style.py: the guide loader and resolver
        - guides/figure-default.json: the guide shipped with this repository
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null figure-default
    """
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        guide = style_.load(a.guide)
    except style_.GuideNotFound as e:
        _say(f"lineart-scene: {e}")
        return UNKNOWN
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    try:
        out, report = style_.apply(doc, guide, a.variant)
    except (KeyError, ValueError) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {report['guide']}"
         + (f"/{a.variant}" if a.variant else "")
         + f": {report['roles_defined']} role(s) available, "
         f"{report['elements_styled']} element(s) styled by role"
         + (f"; {len(report['roles_not_in_guide'])} role(s) NOT in this guide"
            if report["roles_not_in_guide"] else ""))
    for role, where in sorted(report["roles_not_in_guide"].items()):
        _say(f"  {role!r} asked for by {where[0]}"
             + (f" and {len(where) - 1} more" if len(where) > 1 else "")
             + (" -- carried over from what this scene already defined, so the figure is "
                "unchanged there" if role in report["roles_carried_over"]
                else " -- nothing defines it, so those elements fall back to their literals"))
    return NO if report["roles_not_in_guide"] else OK


def verb_adopt(a):
    """Convert a scene's literal colours and widths into named roles it can be restyled by.

    C11:
      noun: style
      verb: adopt
      tags: style, roles, adopt, refactor, traced, literals
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out, its literals replaced by roles; a count on stderr
      phrases:
        - turn this figure's colours into roles
        - adopt a traced drawing into a style guide
        - replace literal styles with named roles
        - make an existing figure restyleable
      requires:
        - lineart_trace/scene/style.py: the grouping and naming
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null
    """
    doc = _read(a.inp)
    dest = _destination(a)
    guide = None
    if a.guide:
        try:
            guide = style_.load(a.guide)
        except style_.GuideNotFound as e:
            _say(f"lineart-scene: {e}")
            return UNKNOWN
    try:
        out, report = style_.adopt(doc, guide, a.variant, a.prefix)
    except (KeyError, ValueError) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {report['converted']} element(s) -> "
         f"{len(report['roles'])} role(s): {report['roles_matched']} matched the guide, "
         f"{report['roles_created']} named {a.prefix}-NN")
    for name, nearest in sorted((report.get("nearest") or {}).items()):
        if nearest:
            _say(f"  {name} is closest to {nearest['role']!r}"
                 + (f", differing in {', '.join(nearest['differs_in'])}"
                    if nearest["differs_in"] else " -- identical, so it was matched"))
    for k in report["left_alone"]:
        _say(f"  kept {k['element']} on role {k['had']!r} rather than overwriting it")
    return OK


def verb_lint(a):
    """Say what in this scene is off-guide: literal styles, off-palette colours, off-scale sizes.

    C11:
      noun: style
      verb: lint
      tags: lint, style, consistency, palette, audit, guide
      accepts: scene.document
      returns: one line per finding on stdout; counts on stderr; exit 1 on an error
      phrases:
        - is this figure on style
        - what is off-palette in this scene
        - check a figure against the house style
        - find inconsistent stroke weights
      requires:
        - lineart_trace/scene/style.py: the checks
      example: --in tests/fixtures/scene-polymerase.json
    """
    doc = _read(a.inp)
    guide = None
    if a.guide:
        try:
            guide = style_.load(a.guide)
        except style_.GuideNotFound as e:
            _say(f"lineart-scene: {e}")
            return UNKNOWN
    try:
        got = style_.lint(doc, guide, a.variant)
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    if a.json:
        sys.stdout.write(io.dumps(got))
    else:
        for f in got["findings"]:
            print(f"{f['severity']:7}  {f['rule']:16}  {f['element'] or '-'}: "
                  f"{f['message']}")
        for u in got["unchecked"]:
            print(f"unknown  {u['rule']:16}  {u['element'] or '-'}: {u['why']}")
    _say(f"[{doc.get('name', '?')}] {got.get('errors', 0)} error(s), "
         f"{got.get('warnings', 0)} warning(s) against "
         f"{got.get('guide') or a.guide or 'no guide'}")
    return NO if got.get("errors") else OK


def verb_palette(a):
    """Generate colours any reader can tell apart, or check a set you already have.

    C11:
      noun: palette
      verb: choose
      tags: palette, colour, colourblind, accessibility, contrast, series
      produces: scene.measurement
      returns: the colours on stdout, one per line when generating; the report with --count 0
      phrases:
        - give me five colours people can tell apart
        - is this palette colourblind safe
        - generate a categorical palette
        - check these colours against a white background
        - which two of my colours look the same
      requires:
        - lineart_trace/scene/palette.py: the search and the checks
      example: -n 4
    """
    if a.count:
        cols, rep = palette.generate(a.count, a.background, a.min_contrast,
                                     a.min_delta_e)
        for c in cols:
            print(c)
        _say(f"{rep['produced']} of {rep['requested']} on {a.background}; worst "
             f"separation {rep['worst_separation']:.1f} delta-E across normal vision and "
             f"all three dichromacies")
        for short in rep["short"]:
            _say(f"  could not produce {short['wanted'] - short['got']} more: "
                 f"{short['why']}")
        return NO if rep["produced"] < rep["requested"] else OK
    if not a.colours:
        _say("lineart-scene: give colours to check, or -n to generate some")
        return REFUSED
    got = palette.check(a.colours, a.background, a.min_contrast, a.min_delta_e)
    sys.stdout.write(io.dumps(got))
    w = got["worst_pair"]
    _say(f"{len(a.colours)} colour(s): "
         + ("usable" if got["usable"] else
            f"{len(got['indistinguishable'])} indistinguishable pair(s), "
            f"{len(got['too_faint'])} too faint")
         + (f"; closest {w['a']} vs {w['b']} at {w['worst_delta_e']:.1f} delta-E "
            f"under {w['worst']}" if w else ""))
    return OK if got["usable"] else NO


def verb_guides(a):
    """List the style guides this installation can reach, and what each one is for.

    C11:
      noun: guide
      verb: list
      tags: guides, style, availability, themes
      returns: one guide per line on stdout, a count on stderr
      phrases:
        - which style guides are available
        - list the house styles
        - what themes can I apply
      requires:
        - lineart_trace/scene/style.py: where guides are looked for
      example:
    """
    rows = []
    for d in style_.guide_dirs():
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            try:
                g = style_.load(os.path.join(d, f))
            except (ValueError, OSError):
                continue
            variants = ", ".join(sorted(g.get("variants") or {})) or "-"
            rows.append(f"{g.get('name', f[:-5])}\t{len(g.get('roles') or {})} roles"
                        f"\t{variants}\t{g.get('title', '')}")
    for r in rows:
        print(r)
    _say(f"{len(rows)} guide(s) in {', '.join(style_.guide_dirs()) or 'no guide directory'}")
    return OK





def verb_panels(a):
    """Lay a grid of panel frames over the page, each with its own coordinates and a letter.

    C11:
      noun: panel
      verb: lay
      tags: panels, layout, grid, multi-panel, figure, lettering
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; the panel size and what was created, on stderr
      phrases:
        - make this a two panel figure
        - lay out a grid of panels
        - add panel letters automatically
        - set up a multi-panel figure
      requires:
        - lineart_trace/scene/layout.py: the grid
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null --rows 1 --cols 2
    """
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        out, rep = layout_.panels(doc, a.rows, a.cols, a.gutter, a.margin, a.letters,
                                  area_guides=a.area_guides)
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {rep['rows']}x{rep['cols']} panels of "
         f"{rep['panel']['width']:.4g}x{rep['panel']['height']:.4g}{rep['unit']}; "
         f"{len(rep['created'])} created, {len(rep['moved'])} moved")
    return OK


def verb_reflow(a):
    """Retarget a figure to a different page: re-lay the panels, keep the contents' own sizes.

    C11:
      noun: figure
      verb: reflow
      tags: reflow, retarget, column, slide, poster, layout, resize
      accepts: scene.document
      produces: scene.document
      returns: the reflowed scene to --out; the old and new page, on stderr
      phrases:
        - fit this figure into a journal column
        - retarget a slide figure for print
        - change the page size and re-lay the panels
        - reflow rather than shrink
      requires:
        - lineart_trace/scene/layout.py: the grid it was laid out to
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null --width 88
    """
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        out, rep = layout_.reflow(doc, a.width, a.height, a.rows, a.cols,
                                  a.gutter, a.margin)
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {rep['from']['width']:g}x{rep['from']['height']:g} -> "
         f"{rep['to']['width']:g}x{rep['to']['height']:g}{rep['unit']}; "
         f"{rep['rows']}x{rep['cols']} panels of "
         f"{rep['panel']['width']:.4g}x{rep['panel']['height']:.4g}"
         + (" (re-gridded)" if rep.get("regridded") else "")
         + (f", {len(rep['refitted'])} drawing(s) re-fitted" if rep["refitted"] else ""))
    return OK


def verb_distribute(a):
    """Space elements evenly along an axis.

    C11:
      noun: element
      verb: distribute
      tags: distribute, spacing, align, layout, even
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; the gap it used, on stderr
      phrases:
        - space these evenly
        - distribute elements along a row
        - even out the gaps between these shapes
      requires:
        - lineart_trace/scene/layout.py: the distribution
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null art art.ink
    """
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        out, rep = layout_.distribute(doc, a.addresses, a.axis, a.spacing, a.frame)
    except measure.Unmeasurable as e:
        _say(f"lineart-scene: cannot establish that: {e}")
        return UNKNOWN
    except KeyError as e:
        _say(f"lineart-scene: {e.args[0]} is nothing in this scene")
        return UNKNOWN
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {len(rep['moved'])} moved, gap {rep['gap']:.4g} "
         f"along {rep['axis']}")
    return OK


def verb_pack(a):
    """Lay elements into another element's area, wrapping to new rows, refusing what will not fit.

    C11:
      noun: element
      verb: pack
      tags: pack, tile, arrange, layout, wrap
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; what was placed and what would not fit, on stderr
      phrases:
        - fill this panel with these shapes
        - arrange these in rows inside a box
        - tile elements into an area
      requires:
        - lineart_trace/scene/layout.py: the packing
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null art art.ink
    """
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        out, rep = layout_.pack(doc, a.addresses, a.into, a.gap, a.frame)
    except measure.Unmeasurable as e:
        _say(f"lineart-scene: cannot establish that: {e}")
        return UNKNOWN
    except KeyError as e:
        _say(f"lineart-scene: {e.args[0]} is nothing in this scene")
        return UNKNOWN
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {rep['placed']} placed, {rep['refused']} would not fit")
    for over in rep["overflow"]:
        _say(f"  left alone: {over['element']} -- {over['why']}")
    return NO if rep["overflow"] else OK


def verb_connect(a):
    """Draw a connector between two points that routes around whatever is in the way.

    C11:
      noun: connector
      verb: route
      tags: connector, route, edge, arrow, avoidance, diagram, leader
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; the clearance it achieved, on stderr
      phrases:
        - draw an arrow between these that avoids the box in between
        - route a connector around obstacles
        - connect two things without crossing anything
        - add a leader line that goes round
      requires:
        - lineart_trace/scene/layout.py: the router
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null link --from 5,5 --to 80,80
    """
    doc = _read(a.inp)
    dest = _destination(a)
    style = None
    if a.style_json:
        import json as _json
        try:
            style = _json.loads(a.style_json)
        except ValueError as e:
            _say(f"lineart-scene: --style is not JSON: {e}")
            return REFUSED
    out, rep = layout_.connect(doc, a.name, _pair(a.start, "--from"),
                               _pair(a.end, "--to"), a.avoid, a.clearance,
                               a.resolution, a.kind, a.role, style, a.arrow, a.frame,
                               a.radius)
    if rep.get("routed") is False and rep.get("kind") != "straight":
        _say(f"lineart-scene: refusing: {rep['why']}")
        return REFUSED
    io.dump(out, dest)
    got = rep.get("clearance_worst")
    _say(f"[{out.get('name', '?')}] {a.name}: {rep.get('kind', a.kind)}, "
         f"{rep.get('corners', 0)} corner(s)"
         + (f", clears {got:.3g} (asked {rep['clearance_asked']:g})"
            if got is not None else ""))
    return OK





def verb_glyph(a):
    """Place a reusable glyph -- a DNA duplex, a plasmid map, a gel, a plate -- by name.

    C11:
      noun: glyph
      verb: place
      tags: glyph, library, dna, plasmid, gel, protein, membrane, plate, reusable
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; what was placed and its anchors, on stderr
      phrases:
        - draw a DNA duplex
        - put a plasmid map in this figure
        - add a gel with lanes and bands
        - place a protein silhouette with a cleft
        - instantiate a glyph from the library
      requires:
        - lineart_trace/scene/glyphs/__init__.py: the catalogue and the instantiation
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null dna.duplex duplex --at 10,10
    """
    doc = _read(a.inp)
    dest = _destination(a)
    args = None
    if a.args:
        import json as _json
        try:
            args = _json.loads(a.args)
        except ValueError as e:
            _say(f"lineart-scene: --args is not JSON: {e}")
            return REFUSED
    try:
        out, rep = glyphs_.place(doc, a.glyph, a.name, _pair(a.at, "--at"), a.parent,
                                 a.frame, args)
    except glyphs_.GlyphNotFound as e:
        _say(f"lineart-scene: {e}")
        return UNKNOWN
    except KeyError:
        _say(f"lineart-scene: {a.parent} is nothing in this scene")
        return UNKNOWN
    except (TypeError, ValueError) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {rep['glyph']} v{rep['version']} as {rep['element']}: "
         f"{rep['elements']} element(s), anchors {', '.join(rep['anchors'])}")
    if rep["roles_not_in_scene"]:
        _say(f"  this scene defines none of: {', '.join(rep['roles_not_in_scene'])} -- "
             f"apply a style guide, or the glyph draws with nothing")
    return OK


def verb_glyphs(a):
    """List the glyph library, or say what one glyph takes.

    C11:
      noun: glyph
      verb: list
      tags: glyph, catalogue, library, parameters, introspection
      returns: one glyph per line on stdout; a parameter list when one is named
      phrases:
        - what glyphs are there
        - list the glyph library
        - what arguments does the DNA duplex take
        - which reusable figures can I place
      requires:
        - lineart_trace/scene/glyphs/__init__.py: the catalogue
      example: --family dna
    """
    if a.glyph:
        try:
            got = glyphs_.describe(a.glyph)
        except glyphs_.GlyphNotFound as e:
            _say(f"lineart-scene: {e}")
            return UNKNOWN
        sys.stdout.write(io.dumps(got))
        _say(f"[{got['id']}] v{got['version']}, {len(got['parameters'])} parameter(s)")
        return OK
    rows = []
    for gid, g in glyphs_.catalogue().items():
        if a.family and g.family != a.family:
            continue
        rows.append(f"{gid}\tv{g.version}\t{g.family}\t{g.summary}")
    for r in rows:
        print(r)
    _say(f"{len(rows)} glyph(s) in "
         f"{len({g.family for g in glyphs_.catalogue().values()})} famil(y/ies)")
    return OK


def verb_promote(a):
    """Capture part of a scene as a reusable glyph definition.

    C11:
      noun: glyph
      verb: capture
      tags: glyph, promote, reuse, library, subtree
      accepts: scene.document
      returns: the glyph definition to --out; what it captured, on stderr
      phrases:
        - turn this part of the figure into a reusable glyph
        - promote a subtree into the library
        - save this shape so I can place it again
      requires:
        - lineart_trace/scene/glyphs/__init__.py: the capture
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null art lineart.polymerase
    """
    doc = _read(a.inp)
    try:
        got = glyphs_.promote(doc, a.address, a.glyph, a.version)
    except KeyError:
        _say(f"lineart-scene: {a.address} is nothing in this scene")
        return UNKNOWN
    io.dump(got, a.out)
    n = len(model.addresses({"elements": [got["element"]]}))
    _say(f"[{a.glyph}] v{got['version']} captured from {a.address}: {n} element(s), "
         f"{len(got['anchors'])} anchor(s). A captured glyph records geometry, not a "
         f"construction, so it takes no parameters.")
    return OK





def verb_plot(a):
    """Build a plot panel from a data file: axes, ticks, marks and an optional fit.

    C11:
      noun: plot
      verb: draw
      tags: plot, chart, data, axes, scatter, bar, fit, panel, publication
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; the scales and any fit statistics, on stderr
      phrases:
        - plot this CSV as a scatter
        - make a bar chart from a data file
        - add a panel with axes and ticks
        - draw a chart with a fitted line
        - turn a table into a figure panel
      requires:
        - lineart_trace/scene/data.py: the scales, marks and annotations
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null p --data tests/fixtures/dose-response.csv --x dose --y response --fit
    """
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        cols, rows = data_.read_table(a.data)
    except (OSError, ValueError) as e:
        _say(f"lineart-scene: cannot read {a.data}: {e}")
        return UNKNOWN
    for col in (a.x, a.y) + ((a.errors,) if a.errors else ()):
        if col not in cols:
            _say(f"lineart-scene: {a.data} has no column {col!r}; it has "
                 f"{', '.join(cols)}")
            return REFUSED
    xs = [r[a.x] for r in rows]
    ys = [r[a.y] for r in rows]
    if any(v is None for v in ys) or any(v is None for v in xs):
        n = sum(1 for v in ys if v is None) + sum(1 for v in xs if v is None)
        _say(f"lineart-scene: refusing: {n} blank value(s) in {a.x!r}/{a.y!r}. Dropping "
             f"them silently would draw a figure of a different dataset than the file.")
        return REFUSED
    errs = [r[a.errors] for r in rows] if a.errors else None
    w, h = _pair(a.size, "--size")
    try:
        g, rep = data_.plot(a.name, xs, ys, w, h, a.kind, xlabel=a.xlabel,
                            ylabel=a.ylabel, title=a.title, errors=errs, ticks=a.ticks,
                            grid=a.grid, source=a.data, fit_line=a.fit,
                            categories=xs if a.kind in ("bar", "box") else None)
    except (ValueError, KeyError) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    at = _pair(a.at, "--at")
    if at[0] or at[1]:
        g["transform"] = [1, 0, 0, 1, at[0], at[1]]
    if a.frame:
        g["frame"] = a.frame
    try:
        out = model.add(doc, g, a.parent)
    except KeyError:
        _say(f"lineart-scene: {a.parent} is nothing in this scene")
        return UNKNOWN
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {a.kind} {a.name} from {os.path.basename(a.data)}: "
         f"{len(rows)} row(s), x {rep['x']}, y {rep['y']}")
    if rep.get("fit"):
        f = rep["fit"]
        _say(f"  fit: slope {f['slope']:.6g}, intercept {f['intercept']:.6g}, "
             f"r2 {f['r2']:.4f}, n {f['n']}")
    return OK





def verb_node(a):
    """Add a diagram node, sized to hold its label in the font the guide supplies.

    C11:
      noun: node
      verb: add
      tags: node, diagram, box, label, autosize, flowchart
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; the size it worked out, on stderr
      phrases:
        - add a box with this label
        - a diagram node sized to its text
        - put a labelled node in the figure
        - add a step to a flowchart
      requires:
        - lineart_trace/scene/diagram.py: the node and its anchors
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null step "lyse cells"
    """
    doc = _read(a.inp)
    dest = _destination(a)
    if not model.NAME_RE.match(a.name):
        _say(f"lineart-scene: {a.name!r} is not a usable element name")
        return REFUSED
    try:
        out, rep = diagram_.node(doc, a.name, a.label, _pair(a.at, "--at"), a.parent,
                                 shape=a.shape, max_width=a.max_width, frame=a.frame)
    except measure.Unmeasurable as e:
        _say(f"lineart-scene: cannot establish that: {e}")
        return UNKNOWN
    except KeyError:
        _say(f"lineart-scene: {a.parent} is nothing in this scene")
        return UNKNOWN
    except (ValueError, text_.TooBig) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {rep['node']}: {rep['width']:.4g}x"
         f"{rep['height']:.4g}, {len(rep['lines'])} line(s)"
         + (" (wrapped)" if rep["wrapped"] else ""))
    return OK


def verb_link(a):
    """Join two nodes with an edge that goes round whatever is between them.

    C11:
      noun: edge
      verb: join
      tags: edge, diagram, connector, arrow, routing, flowchart
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; the clearance it achieved, on stderr
      phrases:
        - draw an arrow between these two nodes
        - connect two boxes in a diagram
        - add a labelled edge
        - join these avoiding what is in between
      requires:
        - lineart_trace/scene/diagram.py: the edge and its side choice
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null e --from art --to art.ink --straight
    """
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        out, rep = diagram_.edge(doc, a.name, a.a, a.b, a.label, a.kind,
                                 clearance=a.clearance, resolution=a.resolution,
                                 routed=a.routed, parent=a.parent)
    except KeyError as e:
        _say(f"lineart-scene: {e.args[0]} is nothing in this scene, or has no such anchor")
        return UNKNOWN
    except (ValueError, measure.Unmeasurable) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    if rep.get("routed") is False and rep.get("kind") != "straight":
        _say(f"lineart-scene: refusing: {rep['why']}")
        return REFUSED
    io.dump(out, dest)
    got = rep.get("clearance_worst")
    _say(f"[{out.get('name', '?')}] {a.name}: {a.a} -> {a.b} via {'/'.join(rep['sides'])}"
         + (f", {rep['corners']} corner(s)" if "corners" in rep else "")
         + (f", clears {got:.3g}" if got is not None else "")
         + (f", parallel offset {rep['parallel_offset']}"
            if rep.get("parallel_offset") else ""))
    return OK


def verb_container(a):
    """Draw a box that fits around the elements it names, and re-fit it when they change.

    C11:
      noun: container
      verb: fit
      tags: container, grouping, box, diagram, swimlane, resize
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; the box it worked out, on stderr
      phrases:
        - put a box around these elements
        - group these visually
        - a container that resizes with its contents
        - draw a boundary round this part of the diagram
      requires:
        - lineart_trace/scene/diagram.py: the fitting
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null around art --pad 2
    """
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        out, rep = diagram_.container(doc, a.name, a.members, a.pad, a.label,
                                      parent=a.parent)
    except measure.Unmeasurable as e:
        _say(f"lineart-scene: cannot establish that: {e}")
        return UNKNOWN
    except KeyError as e:
        _say(f"lineart-scene: {e.args[0]} is nothing in this scene")
        return UNKNOWN
    except ValueError as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    b = rep["box"]
    _say(f"[{out.get('name', '?')}] {rep['container']}: {b['width']:.4g}x"
         f"{b['height']:.4g} around {len(rep['members'])} element(s)"
         + (" (refitted)" if rep["refitted"] else ""))
    return OK


def verb_flowchart(a):
    """Lay out a whole diagram: nodes sized to their labels, then edges routed between them.

    C11:
      noun: diagram
      verb: lay
      tags: flowchart, diagram, state-machine, pathway, layers, routing
      accepts: scene.document
      produces: scene.document
      returns: the scene to --out; the layer assignment and any unroutable edge, on stderr
      phrases:
        - lay out a flowchart
        - draw a state machine
        - make a pathway diagram from nodes and edges
        - turn this graph into a figure
      requires:
        - lineart_trace/scene/diagram.py: the layering and the edges
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null --nodes '{"a":"start","b":"end"}' --edges '[["a","b"]]'
    """
    import json as _json
    doc = _read(a.inp)
    dest = _destination(a)
    try:
        spec = _json.loads(a.nodes)
        edges = [tuple(e) for e in _json.loads(a.edges)]
    except (ValueError, TypeError) as e:
        _say(f"lineart-scene: --nodes/--edges is not the JSON this expects: {e}")
        return REFUSED
    bad = [n for n in spec if not model.NAME_RE.match(n)]
    if bad:
        _say(f"lineart-scene: these node keys are not usable element names: "
             f"{', '.join(bad)}")
        return REFUSED
    try:
        out, rep = diagram_.flow(doc, spec, edges, _pair(a.at, "--at"),
                                 _pair(a.spacing, "--spacing"), a.vertical, a.parent,
                                 a.frame)
    except measure.Unmeasurable as e:
        _say(f"lineart-scene: cannot establish that: {e}")
        return UNKNOWN
    except KeyError as e:
        _say(f"lineart-scene: {e.args[0]} is nothing in this scene")
        return UNKNOWN
    except (ValueError, text_.TooBig) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] {len(spec)} node(s) in {rep['layers']} layer(s), "
         f"{len(rep['edges'])} edge(s), extent {rep['extent']['width']:.4g}x"
         f"{rep['extent']['height']:.4g}"
         + (f"; CYCLIC, closed by "
            f"{', '.join(f'{x}->{y}' for x, y in rep['back_edges'])}"
            if rep["cyclic"] else ""))
    for e in rep["unrouted"]:
        _say(f"  could not route {e.get('name')}: {e.get('why', '')}")
    return NO if rep["unrouted"] else OK





def verb_build(a):
    """Turn a staged reveal into a timeline, with a mark at every stage.

    C11:
      noun: build
      verb: stage
      tags: animation, stages, reveal, lecture, timeline, slides
      accepts: scene.document
      produces: scene.timeline
      returns: the timeline to --out; its duration and marks on stderr
      phrases:
        - make a staged build for a lecture slide
        - reveal these parts one at a time
        - a timeline that shows things in order
        - build up a figure step by step
      requires:
        - lineart_trace/scene/animate.py: the stage-to-track construction
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null lecture --stages '[{"name":"one","reveal":["art"]}]'
    """
    import json as _json
    doc = _read(a.inp)
    try:
        stages = _json.loads(a.stages)
    except (ValueError, TypeError) as e:
        _say(f"lineart-scene: --stages is not JSON: {e}")
        return REFUSED
    missing = [t for st in stages for t in (st.get("reveal", []) + st.get("hide", []))
               if model.find(doc, t) is None]
    if missing:
        _say(f"lineart-scene: refusing: these are nothing in this scene: "
             f"{', '.join(sorted(set(missing)))}. A build that reveals something absent "
             f"looks like a build that works.")
        return REFUSED
    tl = animate_.from_stages(a.name, stages, a.rise, a.hold, a.loop,
                              scene=doc.get("name"))
    io.dump(tl, a.out)
    _say(f"[{a.name}] {tl['duration']:g}s, {len(tl['tracks'])} track(s), "
         f"{len(tl['marks'])} mark(s): "
         + ", ".join(f"{k}@{v:g}s" for k, v in tl["marks"].items()))
    return OK


def verb_still(a):
    """The scene at one stage of a build, as an ordinary scene you can measure and check.

    C11:
      noun: still
      verb: take
      tags: animation, still, frame, stage, export, slides
      accepts: scene.document
      produces: scene.document
      returns: the scene at that moment to --out; what is on it, on stderr
      phrases:
        - export step three of this build as a figure
        - what does the slide look like at this stage
        - a still from an animation
        - the figure partway through a reveal
      requires:
        - lineart_trace/scene/animate.py: the sampling
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null --timeline tests/fixtures/lecture.json --stage one
    """
    doc = _read(a.inp)
    dest = _destination(a)
    tl = _read(a.timeline)
    try:
        if a.stage:
            out = animate_.still(doc, tl, a.stage, a.drop_hidden)
        elif a.when is not None:
            out = animate_.at(doc, tl, a.when, a.drop_hidden)
        else:
            _say("lineart-scene: give --stage or --at")
            return REFUSED
    except KeyError as e:
        _say(f"lineart-scene: {e.args[0]}")
        return UNKNOWN
    except animate_.Incompatible as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    io.dump(out, dest)
    _say(f"[{out.get('name', '?')}] "
         + (f"stage {a.stage}" if a.stage else f"t={a.when:g}s")
         + f": {len(model.addresses(out))} element(s)"
         + (" (hidden ones removed)" if a.drop_hidden else ""))
    return OK


def verb_animate(a):
    """Export one self-contained animated SVG, saying what it could not carry.

    C11:
      noun: animation
      verb: export
      tags: animation, svg, smil, export, explainer, loop
      accepts: scene.document
      returns: an animated SVG to --out; what could not be animated in it, on stderr
      phrases:
        - export this as an animated SVG
        - make a looping explainer
        - save the animation as one file
      requires:
        - lineart_trace/scene/animate.py: the SMIL export
      example: --in tests/fixtures/scene-polymerase.json --timeline tests/fixtures/lecture.json --out /dev/null
    """
    doc = _read(a.inp)
    tl = _read(a.timeline)
    text = animate_.to_svg(doc, tl, a.places)
    if a.out == "-":
        sys.stdout.write(text)
    else:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    carried = [t for t in tl.get("tracks", []) if t["property"] in animate_._SMIL]
    dropped = [f"{t['target']}:{t['property']}" for t in tl.get("tracks", [])
               if t["property"] not in animate_._SMIL]
    _say(f"[{doc.get('name', '?')}] {animate_.duration_of(tl):g}s, "
         f"{len(carried)} track(s) animated in the file, {len(text)} bytes"
         + (f"; {len(dropped)} need frames instead: {', '.join(sorted(dropped))}"
            if dropped else ""))
    return NO if dropped else OK





def verb_report(a):
    """Run every check over a figure and give one verdict: clean, questionable, or wrong.

    C11:
      noun: figure
      verb: report
      tags: report, verification, audit, submit, checklist, quality
      accepts: scene.document
      returns: one section per check on stdout; the verdict and totals on stderr
      phrases:
        - is this figure ready to send
        - check everything about this figure
        - one report over a whole figure
        - what is wrong with this before I submit it
      requires:
        - lineart_trace/scene/report.py: the consolidation
      example: --in tests/fixtures/scene-polymerase.json
    """
    doc = _read(a.inp)
    guide = None
    if a.guide:
        try:
            guide = style_.load(a.guide)
        except style_.GuideNotFound as e:
            _say(f"lineart-scene: {e}")
            return UNKNOWN
    got = report_.full(doc, guide, a.reference, a.dpi, tolerance=a.tolerance)
    if a.json:
        sys.stdout.write(io.dumps(got))
    else:
        for name, sec in got["sections"].items():
            if isinstance(sec, str):
                print(f"{name:11}  {sec}")
                continue
            if "unavailable" in sec:
                print(f"{name:11}  unchecked -- {sec['unavailable']}")
                continue
            if name == "print":
                for f in sec["findings"]:
                    print(f"{f['severity']:11}  {f['rule']:22} "
                          f"{f['element'] or '-'}: {f['message']}")
                for u in sec["unchecked"]:
                    print(f"unchecked    {u['rule']:22} {u['element'] or '-'}: {u['why']}")
            elif name == "style":
                for f in sec.get("findings", []):
                    print(f"{f['severity']:11}  {f['rule']:22} "
                          f"{f['element'] or '-'}: {f['message']}")
            elif name == "conforms" and not sec["ok"]:
                for pb in sec["problems"]:
                    print(f"error        conforms               {pb}")
            elif name == "layout" and not sec["ok"]:
                for u in sec["unsatisfiable"] + sec["unsettled"]:
                    print(f"error        layout                 {u.get('element')}: "
                          f"{u.get('why', u.get('kind'))}")
            elif name == "glyphs":
                for g_ in sec["stale"] + sec["gone"]:
                    print(f"warning      glyph-version          {g_['element']}: "
                          f"{g_['why']}")
            elif name == "regression" and sec.get("changed_beyond_tolerance"):
                print(f"error        regression             -: "
                      f"{sec.get('changed', '?')} pixel(s) differ from "
                      f"{sec.get('reference')}")
    t = got["totals"]
    _say(f"[{got['figure']}] {got['verdict'].upper()}: {t['errors']} error(s), "
         f"{t['warnings']} warning(s), {t['unchecked']} unchecked")
    return NO if got["verdict"] == "wrong" else (
        UNKNOWN if got["verdict"] == "unestablished" else OK)


def verb_snapshot(a):
    """Write the reference image a later regression check compares against.

    C11:
      noun: figure
      verb: snapshot
      tags: regression, reference, snapshot, raster, baseline
      accepts: scene.document
      returns: a PNG at --out; its size on stderr
      phrases:
        - save a reference image of this figure
        - take a baseline for visual regression
        - snapshot this figure so I can tell if it changes
      requires:
        - lineart_trace/scene/raster.py: the deterministic rasteriser
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null --dpi 40
    """
    import cv2
    doc = _read(a.inp)
    img = raster_.rasterize(doc, a.dpi)
    if not cv2.imwrite(a.out, img):
        _say(f"lineart-scene: could not write {a.out}")
        return UNKNOWN
    _say(f"[{doc.get('name', '?')}] {img.shape[1]}x{img.shape[0]} px at {a.dpi:g} dpi "
         f"-> {a.out}")
    return OK


def verb_regress(a):
    """Say whether a figure has changed since its reference, and where.

    C11:
      noun: figure
      verb: compare
      tags: regression, diff, reference, visual, change
      accepts: scene.document
      produces: scene.measurement
      returns: the comparison on stdout; what changed, on stderr
      phrases:
        - has this figure changed
        - compare a figure against its reference
        - visual regression with a diff image
        - show me what moved in this figure
      requires:
        - lineart_trace/scene/report.py: the comparison
      example: --in tests/fixtures/scene-polymerase.json --reference /nonexistent.png
    """
    doc = _read(a.inp)
    got = report_.regress(doc, a.reference, a.dpi, a.tolerance, a.diff)
    sys.stdout.write(io.dumps(got))
    if got.get("unavailable"):
        _say(f"lineart-scene: {got['unavailable']}")
        return UNKNOWN
    if not got.get("same_size"):
        _say(f"lineart-scene: {got['why']}")
        return NO
    _say(f"[{doc.get('name', '?')}] {got['changed']} of {got['pixels']} pixel(s) differ "
         f"({got['fraction'] * 100:.4f}%)"
         + (f", worst channel delta {got['worst']}" if got["changed"] else "")
         + (f"; region x {got['region']['x0']}..{got['region']['x1']} "
            f"y {got['region']['y0']}..{got['region']['y1']}" if got["region"] else "")
         + (f"; diff written to {got['diff']}" if got.get("diff") else ""))
    return NO if got["changed_beyond_tolerance"] else OK





def _page(text, where):
    if where == "-":
        sys.stdout.write(text)
        return
    with open(where, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _findings_for(doc, guide_name):
    guide = style_.load(guide_name) if guide_name else None
    _solved, srep = anchors.solve(doc)
    got = report_.full(doc, guide=guide)
    return (got["sections"].get("print") or {}).get("findings", []), got


def verb_inspect(a):
    """An interactive page: click anything in the figure and it tells you what it is.

    C11:
      noun: figure
      verb: inspect
      tags: inspect, interactive, pick, names, overlay, preview, steer
      accepts: scene.document
      returns: one self-contained HTML page to --out; a count on stderr
      phrases:
        - let me click on this figure and see what things are called
        - what is this element called
        - open a figure so I can poke at it
        - an interactive inspector for a scene
      requires:
        - lineart_trace/scene/inspect.py: the view this renders
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null --no-check
    """
    doc = _read(a.inp)
    findings = None
    if a.check:
        try:
            findings, _got = _findings_for(doc, a.guide)
        except style_.GuideNotFound as e:
            _say(f"lineart-scene: {e}")
            return UNKNOWN
    load = overlay.payload(doc, grid=10.0, findings=findings,
                           depth=(a.depth or None))
    text = inspect_.inspector(load)
    _page(text, a.out)
    n = len(load["boxes"]) if isinstance(load["boxes"], list) else 0
    _say(f"[{doc.get('name', '?')}] {n} element(s) clickable, "
         f"{len(findings) if findings is not None else 0} finding(s) marked, "
         f"{len(text)} bytes")
    return OK


def verb_watch(a):
    """Serve a live preview on loopback that re-renders whenever the scene file changes.

    C11:
      noun: figure
      verb: watch
      tags: live, preview, watch, interactive, iterate, steer
      accepts: scene.document
      returns: a URL on stderr, then serves until interrupted; --once prints one page
      phrases:
        - show me the figure as I edit it
        - live preview of a scene
        - watch this file and re-render
        - open a figure that updates itself
      requires:
        - lineart_trace/scene/watch.py: the watcher and the loopback server
      example: --in tests/fixtures/scene-polymerase.json --once --no-check
    """
    if a.inp == "-":
        _say("lineart-scene: watch needs a file to watch, not stdin")
        return REFUSED
    if not os.path.exists(a.inp):
        _say(f"lineart-scene: cannot read {a.inp}")
        return UNKNOWN
    guide = None
    if a.guide:
        try:
            guide = style_.load(a.guide)
        except style_.GuideNotFound as e:
            _say(f"lineart-scene: {e}")
            return UNKNOWN
    if a.once:
        sys.stdout.write(watch_.render_page(a.inp, guide, a.depth or None, a.check,
                                            live=False))
        _say(f"[{os.path.basename(a.inp)}] one page, not serving")
        return OK

    def ready(port):
        _say(f"[{os.path.basename(a.inp)}] http://127.0.0.1:{port}/ -- loopback only; "
             f"the page reloads when the file changes. Ctrl-C to stop.")
    watch_.serve(a.inp, a.port, guide, a.depth or None, a.check, on_ready=ready)
    return OK


def _render_variant(doc, guide_name=None, variant=None):
    """One rendering of this scene under a named guide or variant. ``(markup, note)``."""
    out = doc
    if guide_name or variant:
        guide = style_.load(guide_name or (doc.get("style") or {}).get("guide")
                            or "figure-default")
        out, _rep = style_.apply(doc, guide, variant)
    got = verify.check(out)
    return svg.render(out), {"findings": got["errors"] + got["warnings"],
                             "verdict": "clean" if not got["errors"] else "wrong"}


def verb_compare(a):
    """Two versions of a figure together: wiped over each other, or side by side.

    C11:
      noun: figure
      verb: compare-visually
      tags: compare, onion, side-by-side, versions, guides, variants, review
      accepts: scene.document
      returns: one self-contained HTML page to --out
      phrases:
        - show me these two versions side by side
        - onion skin the before and after
        - what does this look like under the other style guide
        - compare a figure with its dark variant
      requires:
        - lineart_trace/scene/inspect.py: the gallery view
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null --variant dark
    """
    doc = _read(a.inp)
    items = []
    try:
        base, meta = _render_variant(doc)
        items.append(("as it is", base, meta))
        if a.against:
            other = _read(a.against)
            m, meta2 = _render_variant(other)
            items.append((os.path.basename(a.against), m, meta2))
        elif a.guide or a.variant:
            m, meta2 = _render_variant(doc, a.guide, a.variant)
            items.append((a.variant or a.guide, m, meta2))
        else:
            _say("lineart-scene: give --against, --guide or --variant to compare with")
            return REFUSED
    except style_.GuideNotFound as e:
        _say(f"lineart-scene: {e}")
        return UNKNOWN
    except (KeyError, ValueError) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    load = inspect_.comparison(items, a.mode, doc.get("canvas"),
                               title=doc.get("title") or doc.get("name"))
    text = inspect_.gallery(load)
    _page(text, a.out)
    _say(f"[{doc.get('name', '?')}] {a.mode}: "
         + " vs ".join(i[0] for i in items) + f", {len(text)} bytes")
    return OK


def verb_contact(a):
    """A contact sheet: every variant, guide or build stage of a figure on one page.

    C11:
      noun: figure
      verb: sheet
      tags: contact-sheet, variants, stages, review, gallery, themes
      accepts: scene.document
      returns: one self-contained HTML page to --out
      phrases:
        - a contact sheet of the variants
        - show every theme of this figure at once
        - all the stages of the build on one page
        - let me see the options together
      requires:
        - lineart_trace/scene/inspect.py: the gallery view
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null --variant dark
    """
    doc = _read(a.inp)
    items = []
    try:
        if a.timeline:
            tl = _read(a.timeline)
            for st in tl.get("stages", []):
                still = animate_.still(doc, tl, st["name"])
                got = verify.check(still)
                items.append((st["name"], svg.render(still),
                              {"note": st.get("note"),
                               "findings": got["errors"] + got["warnings"]}))
        else:
            base, meta = _render_variant(doc)
            items.append(("as it is", base, meta))
            for v in a.variant:
                m, meta2 = _render_variant(doc, None, v)
                items.append((v, m, meta2))
            for g in a.guide:
                m, meta2 = _render_variant(doc, g, None)
                items.append((g, m, meta2))
    except style_.GuideNotFound as e:
        _say(f"lineart-scene: {e}")
        return UNKNOWN
    except (KeyError, ValueError) as e:
        _say(f"lineart-scene: refusing: {e}")
        return REFUSED
    if len(items) < 2:
        _say("lineart-scene: a contact sheet of one thing is a picture; give "
             "--variant, --guide or --timeline")
        return REFUSED
    load = inspect_.comparison(items, "contact", doc.get("canvas"),
                               title=doc.get("title") or doc.get("name"))
    text = inspect_.gallery(load)
    _page(text, a.out)
    _say(f"[{doc.get('name', '?')}] contact sheet of {len(items)}: "
         + ", ".join(i[0] for i in items))
    return OK


def verb_truesize(a):
    """A preview at the figure's real printed size, with a ruler to check the screen against.

    C11:
      noun: figure
      verb: preview
      tags: true-size, physical, legibility, print, preview, ruler
      accepts: scene.document
      returns: one self-contained HTML page to --out
      phrases:
        - show this at its actual printed size
        - is this legible at column width
        - true size preview
        - how big will this really be
      requires:
        - lineart_trace/scene/inspect.py: the gallery view
      example: --in tests/fixtures/scene-polymerase.json --out /dev/null
    """
    doc = _read(a.inp)
    got = verify.check(doc)
    load = inspect_.comparison(
        [(doc.get("title") or doc.get("name") or "figure", svg.render(doc),
          {"findings": got["errors"] + got["warnings"]})],
        "true-size", doc.get("canvas"),
        title=doc.get("title") or doc.get("name"),
        note="a screen reports its own size only if it is configured to; check the ruler")
    text = inspect_.gallery(load)
    _page(text, a.out)
    c = doc.get("canvas") or {}
    _say(f"[{doc.get('name', '?')}] shown at {c.get('width', 0):g}x"
         f"{c.get('height', 0):g}{c.get('unit', '')}, with a ruler to verify the screen")
    return OK


def verb_describe(a):
    """Say what is in this figure, what styles it uses and what is wrong with it, in prose.

    C11:
      noun: figure
      verb: describe
      tags: describe, inventory, plain-language, summary, audit, accessibility
      accepts: scene.document
      returns: a few sentences on stdout; the verdict on stderr
      phrases:
        - tell me what is in this figure
        - describe this figure in words
        - what am I looking at
        - summarise a scene in plain language
      requires:
        - lineart_trace/scene/report.py: the narration and the checks behind it
      example: --in tests/fixtures/scene-polymerase.json
    """
    doc = _read(a.inp)
    guide = None
    if a.guide:
        try:
            guide = style_.load(a.guide)
        except style_.GuideNotFound as e:
            _say(f"lineart-scene: {e}")
            return UNKNOWN
    text, got = report_.narrate(doc, guide=guide, reference=a.reference)
    print(text)
    t = got["totals"]
    _say(f"[{doc.get('name', '?')}] {got['verdict'].upper()}: {t['errors']} error(s), "
         f"{t['warnings']} warning(s), {t['unchecked']} unchecked")
    return NO if got["verdict"] == "wrong" else OK



#: Every verb this command performs, and therefore every record generated from it. A verb
#: absent here is not reachable and gets no record; a verb here with no `C11:` block is
#: NAMED by the generator rather than described from a guess at its name.
VERBS = {"new": verb_new, "validate": verb_validate, "tree": verb_tree,
         "render": verb_render, "rename": verb_rename, "remove": verb_remove,
         "measure": verb_measure, "inventory": verb_inventory,
         "clearance": verb_clearance, "collide": verb_collide, "probe": verb_probe,
         "textbox": verb_textbox, "fonts": verb_fonts, "anchor": verb_anchor,
         "attach": verb_attach, "solve": verb_solve, "verify": verb_verify,
         "overlay": verb_overlay, "add": verb_add, "style": verb_style,
         "adopt": verb_adopt, "lint": verb_lint, "palette": verb_palette,
         "guides": verb_guides, "panels": verb_panels, "reflow": verb_reflow,
         "distribute": verb_distribute, "pack": verb_pack, "connect": verb_connect,
         "glyph": verb_glyph, "glyphs": verb_glyphs, "promote": verb_promote,
         "plot": verb_plot, "node": verb_node, "link": verb_link,
         "container": verb_container, "flowchart": verb_flowchart,
         "build": verb_build, "still": verb_still, "animate": verb_animate,
         "report": verb_report, "snapshot": verb_snapshot, "regress": verb_regress,
         "inspect": verb_inspect, "watch": verb_watch, "compare": verb_compare,
         "contact": verb_contact, "truesize": verb_truesize,
         "describe": verb_describe}


def main(argv=None):
    a = build_parser().parse_args(argv)
    return VERBS[a.verb](a)


if __name__ == "__main__":
    sys.exit(main())
