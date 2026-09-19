"""The scene: addressing, traversal, frames, and the edits that phase 1 needs.

**The document IS the model.** There is no ``Scene`` class mirroring the schema's fields,
because a class that mirrors a schema is a second declaration of the format and the two
drift -- the same argument that keeps element identity in names rather than in a parallel
table of uids. A scene is the parsed JSON; this module is what knows how to walk it.

Three ideas carry the whole thing:

**An address is the join of sibling-scoped names.** ``panel-b.enzyme.outline`` names the
element reached by those names in turn. A name is unique among its siblings and contains no
dot, so an address splits unambiguously. Anchors share the element's child namespace, which
is what lets the spec's own spelling -- ``panel-b.enzyme.active-site`` -- resolve without a
second separator; a child and an anchor of the same name is refused by
:mod:`lineart_trace.scene.validate` so that resolution is total.

**A frame owns the unit; coordinates are bare.** An element's coordinates are in its frame,
inherited from its nearest ancestor that declares one. A length that must hold on paper
regardless of nesting is written as a string with a suffix, ``"1.2pt"``, and resolved
through the frame chain by :func:`resolve_length`.

**Edits return a new document.** Nothing here mutates its argument. Composability §4 asks
that nothing require a session, and the cheapest way to mean it is for every transform to be
a function from a document to a document.
"""
import copy
import re

__all__ = [
    "NAME_RE", "new", "walk", "find", "parent_of", "resolve", "addresses",
    "frame_of", "frame_chain", "frame_to_page", "compose", "apply", "invert", "scale_of", "element_to_page", "frame_between",
    "effective_style",
    "resolve_length", "to_unit", "add", "remove", "rename", "tree",
]

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

#: Physical units in millimetres. ``px`` is the CSS pixel, 1/96 inch -- a definition, and one
#: that only applies to a PAGE length. A pixel coordinate inside a traced frame is not this;
#: it is whatever that frame's transform says it is.
_MM = {"mm": 1.0, "pt": 25.4 / 72.0, "in": 25.4, "px": 25.4 / 96.0}

_LENGTH_RE = re.compile(r"^(-?\d+(?:\.\d+)?)(mm|pt|px|in)$")


# ----------------------------------------------------------------- construction
def new(name, width, height, unit="mm", title=None, background="none"):
    """An empty scene with a single page frame.

    The page frame is the one with no parent, and its unit is the canvas unit by
    construction. `validate` enforces that for scenes built any other way.
    """
    doc = {
        "format": "lineart.scene/1",
        "name": name,
        "canvas": {"width": width, "height": height, "unit": unit,
                   "background": background},
        "frames": {"page": {"unit": unit}},
        "elements": [],
    }
    if title:
        doc["title"] = title
    return doc


# ----------------------------------------------------------------- traversal
def walk(doc, _elements=None, _prefix=""):
    """Every element, depth first, as ``(address, element, parent_or_None)``.

    Depth first and in document order, so anything built on this -- rendering, listing,
    measuring -- inherits a stable order without asking for one.
    """
    if _elements is None:
        _elements = doc.get("elements", [])
        _prefix = ""
    for el in _elements:
        addr = f"{_prefix}{el['name']}"
        yield addr, el, None if not _prefix else _prefix[:-1]
        kids = el.get("children")
        if kids:
            for got in walk(doc, kids, addr + "."):
                yield got


def addresses(doc):
    """Every element address in the scene, in document order."""
    return [a for a, _el, _p in walk(doc)]


def find(doc, address):
    """The element at `address`, or None. Anchors are not elements; see :func:`resolve`."""
    node = None
    kids = doc.get("elements", [])
    for part in address.split("."):
        node = next((e for e in kids if e.get("name") == part), None)
        if node is None:
            return None
        kids = node.get("children", [])
    return node


def parent_of(doc, address):
    """``(parent_address, parent_element)`` -- ``("", None)`` for a top-level element."""
    if "." not in address:
        return "", None
    head = address.rsplit(".", 1)[0]
    return head, find(doc, head)


def resolve(doc, address):
    """What `address` names: an element, or an anchor on one.

    Returns a dict with ``kind`` (``"element"`` or ``"anchor"``), the ``address``, the
    ``element`` it belongs to and that element's address, and for an anchor its ``name`` and
    ``anchor`` body. Raises KeyError naming the address, because a silently-None address is
    how an operation ends up applied to nothing.
    """
    el = find(doc, address)
    if el is not None:
        return {"kind": "element", "address": address, "element": el,
                "element_address": address}
    if "." in address:
        owner_addr, anchor = address.rsplit(".", 1)
        owner = find(doc, owner_addr)
        if owner is not None and anchor in (owner.get("anchors") or {}):
            return {"kind": "anchor", "address": address, "name": anchor,
                    "anchor": owner["anchors"][anchor], "element": owner,
                    "element_address": owner_addr}
    raise KeyError(address)


# ----------------------------------------------------------------- frames
def _page_frame(doc):
    frames = doc.get("frames") or {}
    for fname, f in sorted(frames.items()):
        if not f.get("parent"):
            return fname
    return None


def frame_of(doc, address):
    """The frame an element's coordinates are in: its own, else its nearest ancestor's."""
    parts = address.split(".")
    for n in range(len(parts), 0, -1):
        el = find(doc, ".".join(parts[:n]))
        if el is not None and el.get("frame"):
            return el["frame"]
    return _page_frame(doc)


def frame_chain(doc, frame):
    """`frame` and every ancestor up to the page frame, nearest first.

    Raises ValueError on a cycle rather than looping, because a frame cycle is a scene that
    can be written and can never be rendered, and it should be named where it is found.
    """
    seen, out = set(), []
    cur = frame
    frames = doc.get("frames") or {}
    while cur:
        if cur in seen:
            raise ValueError(f"frame cycle: {' -> '.join(out + [cur])}")
        if cur not in frames:
            raise KeyError(f"no such frame: {cur}")
        seen.add(cur)
        out.append(cur)
        cur = frames[cur].get("parent")
    return out


IDENTITY = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


def compose(outer, inner):
    """``outer`` then ``inner``, as SVG matrices: the matrix that applies `inner` first."""
    a1, b1, c1, d1, e1, f1 = outer
    a2, b2, c2, d2, e2, f2 = inner
    return [a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1]


def apply(m, x, y):
    """A point through a matrix."""
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def invert(m):
    """The inverse of an affine matrix. Raises ValueError on a singular one.

    A singular frame transform is a scene where a coordinate has no way back to the page,
    which is a defect to name rather than a number to return.
    """
    a, b, c, d, e, f = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        raise ValueError("singular transform: it collapses the frame and cannot be undone")
    return [d / det, -b / det, -c / det, a / det,
            (c * f - d * e) / det, (b * e - a * f) / det]


def frame_to_page(doc, frame):
    """The matrix taking `frame` coordinates all the way to page coordinates."""
    m = list(IDENTITY)
    frames = doc.get("frames") or {}
    for f in frame_chain(doc, frame):
        t = frames[f].get("transform")
        if t:
            m = compose(t, m)
    return m


def element_to_page(doc, address):
    """The matrix taking an element's OWN coordinates to page coordinates.

    **The one definition of where an element is**, used by measurement, by the anchor
    recipes, by the relation solver and by the SVG exporter. It was three definitions for an
    afternoon and they disagreed in two ways that a figure shows and a test does not:

    * Measurement composed only an element's own transform, never its ancestors'. So a group
      transform moved its children in the exported SVG and moved nothing in any measured
      box -- a collision check and the drawing it checked disagreeing about where things are.
    * Anchor recipes derived a point from post-transform geometry and stored it in a field
      every other reader treats as pre-transform, so the transform was applied twice and an
      attached label drifted further away each time the scene was solved.

    The rule, and it is one sentence: **every element has a local space; its own `transform`
    maps that space to its parent's, and its geometry AND its anchors are written in it.** A
    frame declaration replaces the context, so walking from the root, an element naming a
    frame different from the one in force resets the accumulated element transform and
    adopts that frame; every element transform on the way down multiplies in.

    *Rejected: a second "local" matrix that stopped short of the element's own transform.*
    It was written to fix the double-application above and made it worse, because it
    answered a question with no referent -- there is no space in which an element's anchors
    sit but its geometry does not. Anchors move with the shape because the shape's transform
    carries both, which is the whole reason a derived anchor survives its element being
    moved.
    """
    parts = address.split(".")
    cur_frame = _page_frame(doc)
    acc = list(IDENTITY)
    for n, part in enumerate(parts, 1):
        el = find(doc, ".".join(parts[:n]))
        if el is None:
            raise KeyError(address)
        if el.get("frame") and el["frame"] != cur_frame:
            cur_frame = el["frame"]
            acc = list(IDENTITY)
        if el.get("transform"):
            acc = compose(acc, el["transform"])
    return compose(frame_to_page(doc, cur_frame), acc)


def frame_between(doc, outer, inner):
    """The matrix taking `inner` frame coordinates into `outer` frame coordinates."""
    return compose(invert(frame_to_page(doc, outer)), frame_to_page(doc, inner))


def scale_of(m):
    """The uniform-ish scale of a matrix: the geometric mean of its axis lengths.

    A single number for a matrix that may not have one is a lie when the transform is
    anisotropic, and it is what a stroke width needs. `validate` does not forbid an
    anisotropic frame; :mod:`lineart_trace.scene.validate` reports one, so the number below
    is never quietly wrong about a scene nobody was warned about.
    """
    a, b, c, d = m[0], m[1], m[2], m[3]
    sx = (a * a + b * b) ** 0.5
    sy = (c * c + d * d) ** 0.5
    return (sx * sy) ** 0.5


# ----------------------------------------------------------------- lengths
def to_unit(value, frm, to):
    """A physical length from one unit to another."""
    return value * _MM[frm] / _MM[to]


def resolve_length(doc, value, frame):
    """A length as a number in `frame`'s own coordinates.

    A bare number is already in the frame and comes back untouched. A suffixed string is a
    length on the PAGE -- ``"1.2pt"`` is 1.2pt of paper however deeply the element is nested
    -- so it converts to page units and then divides out the frame's scale.
    """
    if not isinstance(value, str):
        return float(value)
    m = _LENGTH_RE.match(value)
    if not m:
        raise ValueError(f"not a length: {value!r}")
    n, unit = float(m.group(1)), m.group(2)
    page_unit = (doc.get("canvas") or {}).get("unit", "mm")
    on_page = to_unit(n, unit, page_unit)
    s = scale_of(frame_to_page(doc, frame))
    if s == 0:
        raise ValueError(f"frame {frame!r} has zero scale; no length is resolvable in it")
    return on_page / s


# ----------------------------------------------------------------- edits
def add(doc, element, parent=""):
    """A new scene with `element` appended under `parent` (the root when empty).

    Refuses a duplicate name among the siblings it would join. A silent overwrite here is
    the edit that loses work, and the name is the only identity this format has.
    """
    out = copy.deepcopy(doc)
    if parent:
        host = find(out, parent)
        if host is None:
            raise KeyError(parent)
        if host.get("type") != "group":
            raise ValueError(f"{parent} is a {host.get('type')}, not a group; "
                             f"only a group holds children")
        kids = host.setdefault("children", [])
    else:
        kids = out.setdefault("elements", [])
    name = element["name"]
    if any(k.get("name") == name for k in kids):
        where = parent or "the scene root"
        raise ValueError(f"{where} already has a child named {name!r}")
    kids.append(copy.deepcopy(element))
    return out


def remove(doc, address):
    """A new scene without the element at `address` and everything beneath it."""
    out = copy.deepcopy(doc)
    head, host = parent_of(out, address)
    kids = out["elements"] if host is None else host.get("children", [])
    leaf = address.rsplit(".", 1)[-1]
    keep = [k for k in kids if k.get("name") != leaf]
    if len(keep) == len(kids):
        raise KeyError(address)
    if host is None:
        out["elements"] = keep
    else:
        host["children"] = keep
    return out


def rename(doc, address, new_name):
    """A new scene with the element at `address` renamed, and every reference rewritten.

    **This is the cost of addressing by name, paid where it falls.** Nothing in the document
    holds a second, stable identity, so a rename moves every address beneath this element --
    and any reference elsewhere that names one of them has to move with it. The count of
    references rewritten comes back with the scene so a caller can report it rather than
    discover it.

    Returns ``(scene, rewritten)``.
    """
    if not NAME_RE.match(new_name):
        raise ValueError(f"not a usable name: {new_name!r} "
                         f"(lower case, digits and hyphens, no dots)")
    out = copy.deepcopy(doc)
    el = find(out, address)
    if el is None:
        raise KeyError(address)
    head, host = parent_of(out, address)
    kids = out["elements"] if host is None else host.get("children", [])
    if any(k.get("name") == new_name for k in kids if k is not el):
        where = head or "the scene root"
        raise ValueError(f"{where} already has a child named {new_name!r}")
    el["name"] = new_name
    old_prefix = address
    new_prefix = f"{head}.{new_name}" if head else new_name
    rewritten = _rewrite_refs(out, old_prefix, new_prefix)
    return out, rewritten


#: Fields whose value is an ADDRESS, and therefore what a rename has to follow. Exactly one
#: today: a relation's `to`. A relation's `via` names an anchor on the element that carries
#: it, not an address, and rewriting it here would corrupt a scene rather than maintain one.
#:
#: This list was five entries long for an afternoon -- `of`, `to`, `from`, `target`,
#: `anchor` -- guessing at fields §3.5 might add. None of them existed in the schema, so no
#: scene could legally carry one, so the rewrite maintained nothing and the check that
#: dangling references are caught could not be written at all. A guarantee about a field
#: nothing may carry is not a weak guarantee, it is the appearance of one.
ADDRESS_FIELDS = ("to",)


def _rewrite_refs(doc, old, new):
    n = 0

    def walk_any(o):
        nonlocal n
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ADDRESS_FIELDS and isinstance(v, str) and (
                        v == old or v.startswith(old + ".")):
                    o[k] = new + v[len(old):]
                    n += 1
                else:
                    walk_any(v)
        elif isinstance(o, list):
            for v in o:
                walk_any(v)

    walk_any(doc.get("elements", []))
    return n


def effective_style(doc, el):
    """The style an element actually draws with: its role's tokens, then its own literals.

    **One resolution, used by the renderer, the measurer and the checker.** It was three
    readings of `el["style"]` before style guides existed, which was harmless while every
    element carried literals and wrong the moment one asked for a role instead: a figure
    drawn entirely by role measured as having no stroke width, no type size and no colour,
    so every check passed and every text element was unmeasurable. A style system that makes
    a figure LESS checkable is worse than none.
    """
    roles = ((doc.get("style") or {}).get("roles") or {}) if doc else {}
    out = {}
    if el.get("role") in roles:
        out.update(roles[el["role"]])
    out.update({k: v for k, v in (el.get("style") or {}).items() if v is not None})
    return out


def tree(doc, show=("type", "role")):
    """The element tree as indented lines -- the plain-language inventory of §3.15, minimal.

    Deliberately a string rather than a print: a tool that formats and a tool that writes are
    the same tool only until one of them needs testing.
    """
    lines = []
    for addr, el, _p in walk(doc):
        depth = addr.count(".")
        bits = []
        for k in show:
            if el.get(k):
                bits.append(str(el[k]))
        anchors = sorted((el.get("anchors") or {}))
        if anchors:
            bits.append("@" + ",".join(anchors))
        lines.append("  " * depth + el["name"] + ("  " + " ".join(bits) if bits else ""))
    return "\n".join(lines)
