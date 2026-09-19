"""Is this document a scene? Three answers, and the third may never wear the code of another.

This is the `code_verification` half of the format. The JSON Schema in
``scene.schema.json`` states the shape; a great deal of what makes a scene *usable* is not a
shape and cannot be written there -- that sibling names are unique, that an anchor does not
collide with a child, that every frame reference resolves and no chain of them loops, that a
``C`` segment carries six numbers and a ``Z`` carries none. Those are here.

**Three answers, following the contract every checker in this ecosystem answers by:**

===== =========================================================================
exit  meaning
===== =========================================================================
0     conforms
1     does not conform, and the reasons are on stdout
2     could NOT be checked -- unreadable, unparseable, or no validator available
===== =========================================================================

The third is the one that matters. "I could not check this" reported as "this is wrong" turns
an unknown into a finding, and an unknown reported as conformance is worse still: it is the
absence-collapsing-into-success failure, on the one path whose whole job is to catch it. So a
missing file, malformed JSON and an absent ``jsonschema`` all exit 2, and none of them can
reach the code that says yes.
"""
import os

from . import model

__all__ = ["SCHEMA_PATH", "schema", "problems", "check"]

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene.schema.json")
MEASUREMENT_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "measurement.schema.json")

#: How many numbers each path verb carries. JSON Schema can bound the array but cannot tie
#: its length to its first element, so a ``["C", 1, 2]`` passes the schema and is not a curve.
_ARITY = {"M": 2, "L": 2, "C": 6, "Z": 0}

_TYPE_GEOMETRY = {
    "path": ("path",), "region": ("region",), "text": ("text",),
    "image": ("image",), "glyph": ("glyph",),
    "guide": ("path", "region"), "group": (),
}


class Uncheckable(Exception):
    """Raised for every way of not-knowing. Never for a document that is merely wrong."""


def schema(path=None):
    """The JSON Schema, read from the file that is its single source."""
    import json
    with open(path or SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _shape_problems(doc, schema_path=None):
    try:
        import jsonschema
    except ImportError as e:      # absence-ok: unchecked is not the same as wrong
        raise Uncheckable(
            "jsonschema is not importable, so the document's shape could not be checked "
            "at all; `pip install -e .` here") from e
    v = jsonschema.Draft202012Validator(schema(schema_path))
    out = []
    for err in sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(document)"
        out.append(f"{where}: {err.message}")
    return out


def _segment_problems(segs, where):
    out = []
    for i, s in enumerate(segs):
        if not s:
            out.append(f"{where}[{i}]: an empty segment")
            continue
        verb, nums = s[0], s[1:]
        want = _ARITY.get(verb)
        if want is None:
            out.append(f"{where}[{i}]: unknown verb {verb!r}")
        elif len(nums) != want:
            out.append(f"{where}[{i}]: {verb} takes {want} numbers, got {len(nums)}")
        if i == 0 and verb != "M":
            out.append(f"{where}[{i}]: a run must open with M, not {verb}")
        if verb == "Z" and i != len(segs) - 1:
            out.append(f"{where}[{i}]: Z closes a run and must be its last segment")
        if verb == "M" and i != 0:
            out.append(f"{where}[{i}]: a second M -- a path element holds ONE run; "
                       f"use a region's loops, or separate elements")
    return out


def problems(doc, schema_path=None):
    """Everything wrong with `doc`, as ``(problems, warnings)``.

    A problem means this is not a scene. A warning means it is a scene that will behave in a
    way somebody probably did not intend -- an anisotropic frame, an image whose file is not
    where the scene says. Warnings are reported and do not fail, because a scene is often
    validated somewhere other than beside its assets, and refusing there would teach people
    to stop running the check.
    """
    bad = _shape_problems(doc, schema_path)
    warn = []
    if bad:
        # Structural checks below assume the shape held. Running them on a document that
        # failed the schema produces cascades of nonsense rooted in one real error.
        return bad, warn

    frames = doc.get("frames") or {}
    canvas = doc.get("canvas") or {}
    roots = [f for f, b in sorted(frames.items()) if not b.get("parent")]
    if len(roots) != 1:
        bad.append(f"frames: exactly one frame must have no parent (the page); "
                   f"found {len(roots)}: {', '.join(roots) or 'none'}")
    elif frames[roots[0]].get("unit") != canvas.get("unit"):
        bad.append(f"frames/{roots[0]}: the page frame's unit "
                   f"({frames[roots[0]].get('unit')!r}) must be the canvas unit "
                   f"({canvas.get('unit')!r}); nothing else could make a page length mean "
                   f"one thing")
    for f in sorted(frames):
        p = frames[f].get("parent")
        if p and p not in frames:
            bad.append(f"frames/{f}: parent {p!r} is not a frame in this scene")
    for f in sorted(frames):
        try:
            model.frame_chain(doc, f)
        except ValueError as e:
            bad.append(f"frames/{f}: {e}")
        except KeyError:
            pass                      # already reported as a dangling parent
        else:
            t = frames[f].get("transform")
            if t:
                sx = (t[0] ** 2 + t[1] ** 2) ** 0.5
                sy = (t[2] ** 2 + t[3] ** 2) ** 0.5
                if sx > 0 and sy > 0 and abs(sx - sy) / max(sx, sy) > 0.001:
                    warn.append(f"frames/{f}: anisotropic transform (x {sx:.4g}, y "
                                f"{sy:.4g}); one stroke width cannot hold in both axes")

    seen_siblings = {}
    for addr, el, _p in model.walk(doc):
        head = addr.rsplit(".", 1)[0] if "." in addr else ""
        seen_siblings.setdefault(head, []).append(el["name"])

        kind = el.get("type")
        geom = el.get("geometry")
        if kind == "group":
            if geom:
                bad.append(f"{addr}: a group has children, not geometry")
        else:
            if el.get("children"):
                bad.append(f"{addr}: a {kind} cannot have children; only a group can")
            if geom is None:
                if kind != "guide":
                    bad.append(f"{addr}: a {kind} needs geometry")
            elif geom.get("kind") not in _TYPE_GEOMETRY.get(kind, ()):
                bad.append(f"{addr}: type {kind!r} does not take "
                           f"{geom.get('kind')!r} geometry")

        anchors = el.get("anchors") or {}
        kids = {k.get("name") for k in (el.get("children") or [])}
        for clash in sorted(anchors.keys() & kids):
            bad.append(f"{addr}: {clash!r} is both a child and an anchor, so "
                       f"{addr}.{clash} names two things")
        for aname, a in sorted(anchors.items()):
            if a.get("how") == "authored" and "at" not in a:
                bad.append(f"{addr}.{aname}: an authored anchor must say where it is")
            if a.get("how") in ("derived", "discovered") and not a.get("by"):
                bad.append(f"{addr}.{aname}: a {a['how']} anchor must name the recipe "
                           f"that produced it, or it cannot be produced again")

        if geom:
            if geom.get("kind") == "path":
                bad += _segment_problems(geom.get("d") or [], f"{addr}/d")
            elif geom.get("kind") == "region":
                for li, loop in enumerate(geom.get("loops") or []):
                    bad += _segment_problems(loop, f"{addr}/loops[{li}]")
                    if loop and loop[-1][0] != "Z":
                        bad.append(f"{addr}/loops[{li}]: a region's loop must close with Z")
            elif geom.get("kind") == "image":
                href = geom.get("href")
                if href and not os.path.isabs(href) and not os.path.exists(href):
                    warn.append(f"{addr}: image {href!r} is not readable from here")

        if el.get("frame") and el["frame"] not in frames:
            bad.append(f"{addr}: frame {el['frame']!r} is not a frame in this scene")

    for head, names in sorted(seen_siblings.items()):
        dupes = sorted({n for n in names if names.count(n) > 1})
        for d in dupes:
            where = head or "the scene root"
            bad.append(f"{where}: {d!r} names more than one child; an address must "
                       f"resolve to exactly one element")

    for addr, el, _p in model.walk(doc):
        for field, ref in _address_refs(el):
            # `model.resolve`, not a membership test against the element addresses. An
            # address may legitimately name an ANCHOR, and the cheap version of this check
            # -- "the part before the last dot is an element" -- accepts `enzyme.nowhere`
            # for any element named `enzyme`, which is every dangling anchor reference there
            # can be. One resolver, used by the tools and by the check on them.
            try:
                model.resolve(doc, ref)
            except KeyError:
                bad.append(f"{addr}: {field} names {ref!r}, which is nothing in this scene")
                continue
            if ref == addr or ref.startswith(addr + "."):
                bad.append(f"{addr}: {field} names {ref!r}, which is itself or something "
                           f"inside it -- a relation to your own descendant is a cycle no "
                           f"layout can solve")
        for rel in el.get("relations") or []:
            via = rel.get("via")
            if via and via not in (el.get("anchors") or {}):
                bad.append(f"{addr}: relation via {via!r}, which is not an anchor on this "
                           f"element")

    return bad, warn


def _address_refs(el):
    out = []

    def rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "children":
                    continue
                if k in model.ADDRESS_FIELDS and isinstance(v, str):
                    out.append((k, v))
                else:
                    rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)

    rec({k: v for k, v in el.items() if k != "children"})
    return out


def check(path, schema_path=None):
    """Check the scene file at `path`. Returns ``(exit_code, lines)``.

    Takes a PATH, not a parsed document, because a checker that takes contents cannot tell a
    file that is absent from one that is empty -- and those are different answers.
    """
    from . import io
    try:
        doc = io.load(path)
    except FileNotFoundError:
        return 2, [f"scene.validate: cannot read {path}"]
    except (ValueError, UnicodeDecodeError) as e:
        return 2, [f"scene.validate: {path} is not JSON: {e}"]
    try:
        bad, warn = problems(doc, schema_path)
    except Uncheckable as e:
        return 2, [f"scene.validate: {e}"]
    lines = [f"not a scene: {b}" for b in bad] + [f"warning: {w}" for w in warn]
    return (1 if bad else 0), lines
