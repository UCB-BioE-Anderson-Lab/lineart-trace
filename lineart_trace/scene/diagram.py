"""Diagram constructs: §3.9. Nodes that size themselves, edges that route, boxes that fit.

**A node is sized to its contents, measured.** That is the whole difference between this and
drawing boxes: the label is measured in the font the guide supplies, and the box is built
around it. A diagram whose boxes were guessed at is a diagram that has to be nudged every
time a label changes.

Edges attach to node ANCHORS and route with :mod:`lineart_trace.scene.layout`, so an edge
that has something in its way goes round it and reports the clearance it achieved. An edge
whose route cannot exist is refused, not drawn through the obstacle.

Layout here is layered: a longest-path assignment down the graph, then ordering within each
layer. It is deterministic and it is not clever -- no crossing minimisation, no force
simulation. What it does do is say where it put everything, so a caller that wants something
else can move it with the ordinary relation tools.
"""
import math

from . import build, layout, measure, model, text as text_

__all__ = ["node", "nodes", "edge", "container", "layers", "flow", "tree", "swimlanes",
           "NODE_ROLE", "auto_size"]

NODE_ROLE = "surface-fill"
_LABEL = "caption"
_EDGE = "structure-stroke"
_EDGE_FILL = "accent-fill"
_CONTAINER = "guide-line"


def auto_size(doc, label, role=_LABEL, pad_x=3.0, pad_y=2.4, min_width=0.0,
              min_height=0.0, unit=None, max_width=None):
    """How big a box has to be to hold `label`. Returns ``(width, height, laid)``.

    Measured in the font the scene's guide supplies for `role`, which is why this takes a
    document. With `max_width` the label wraps and the height grows; without, it is one line
    and the width is whatever it needs.
    """
    body = (doc.get("style") or {}).get("roles", {}).get(role) or {}
    family = body.get("font_family")
    size = body.get("font_size")
    if not family or size is None:
        raise measure.Unmeasurable(
            f"role {role!r} does not supply a font_family and font_size in this scene, so "
            f"a node cannot be sized to its label. Apply a style guide first.")
    unit = unit or (doc.get("canvas") or {}).get("unit", "mm")
    if max_width:
        laid = text_.fit(label, max_width - 2 * pad_x, 1e6, family, size, mode="wrap",
                         unit=unit)
    else:
        laid = text_.fit(label, 1e6, 1e6, family, size, mode="strict", unit=unit)
    w = max(min_width, laid["width"] + 2 * pad_x)
    h = max(min_height, laid["height"] + 2 * pad_y)
    return w, h, laid


def node(doc, name, label, at=(0.0, 0.0), parent="", role=NODE_ROLE, label_role=_LABEL,
         radius=1.5, pad_x=3.0, pad_y=2.4, min_width=0.0, min_height=0.0,
         max_width=None, shape="rect", frame=None):
    """One node, sized to its label. Returns ``(scene, report)``.

    The group carries `n`, `s`, `e`, `w` and `centre` anchors, which is what edges attach to.
    """
    w, h, laid = auto_size(doc, label, label_role, pad_x, pad_y, min_width, min_height,
                           max_width=max_width)
    x, y = float(at[0]), float(at[1])
    if shape == "rect":
        body = build.rect("body", x, y, w, h, radius, role=role)
    elif shape == "ellipse":
        body = build.ellipse("body", x + w / 2, y + h / 2, w / 2 * 1.12, h / 2 * 1.12,
                             role=role)
    elif shape == "diamond":
        body = build.polyline("body", [(x + w / 2, y - h * 0.22), (x + w * 1.1, y + h / 2),
                                       (x + w / 2, y + h * 1.22), (x - w * 0.1, y + h / 2)],
                              closed=True, role=role)
    else:
        raise ValueError(f"no node shape called {shape!r}; known: rect, ellipse, diamond")
    kids = [body]
    top = y + pad_y + laid["ascent"]
    for i, line in enumerate(laid["lines"]):
        kids.append(build.text(f"line-{i + 1:02d}", line,
                               (x + w / 2, top + i * laid["line_height"]),
                               family=None, size=None, align="middle", role=label_role))
    g = build.group(name, kids)
    g["tags"] = ["node"]
    g["anchors"] = {
        "centre": {"how": "authored", "at": [x + w / 2, y + h / 2]},
        "n": {"how": "authored", "at": [x + w / 2, y], "dir": [0, -1]},
        "s": {"how": "authored", "at": [x + w / 2, y + h], "dir": [0, 1]},
        "w": {"how": "authored", "at": [x, y + h / 2], "dir": [-1, 0]},
        "e": {"how": "authored", "at": [x + w, y + h / 2], "dir": [1, 0]},
    }
    if frame:
        g["frame"] = frame
    out = model.add(doc, g, parent)
    where = f"{parent}.{name}" if parent else name
    return out, {"node": where, "width": w, "height": h, "lines": laid["lines"],
                 "wrapped": len(laid["lines"]) > 1}


def nodes(doc, spec, parent="", **kw):
    """Several nodes at once: ``{name: (label, (x, y))}``. Returns ``(scene, reports)``."""
    reports = {}
    for name, (label, at) in spec.items():
        doc, rep = node(doc, name, label, at, parent, **kw)
        reports[name] = rep
    return doc, reports


# --------------------------------------------------------------------- edges
_SIDES = {"n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0)}


def _anchor(doc, addr, side, frame):
    el = model.find(doc, addr)
    if el is None:
        raise KeyError(addr)
    a = (el.get("anchors") or {}).get(side)
    if a is None or "at" not in a:
        raise KeyError(f"{addr}.{side}")
    m = model.compose(model.invert(model.frame_to_page(doc, frame)),
                      model.element_to_page(doc, addr))
    return model.apply(m, a["at"][0], a["at"][1])


def _best_sides(doc, a, b, frame):
    """Which side of each node an edge should leave from, by where the other one is."""
    ca = _anchor(doc, a, "centre", frame)
    cb = _anchor(doc, b, "centre", frame)
    dx, dy = cb[0] - ca[0], cb[1] - ca[1]
    if abs(dy) >= abs(dx):
        return ("s", "n") if dy > 0 else ("n", "s")
    return ("e", "w") if dx > 0 else ("w", "e")


def edge(doc, name, a, b, label=None, kind="arrow", avoid=None, clearance=1.5,
         resolution=0.5, frame=None, from_side=None, to_side=None, role=_EDGE,
         head=1.8, routed=True, label_role=_LABEL, parent="", bounds=None,
         within=None):
    """An edge between two nodes, routed around whatever is in the way.

    `kind` is ``arrow``, ``both``, ``open`` or ``none``. `avoid` defaults to every other node
    in the scene, which is what makes an edge go round rather than through.
    """
    # THE FRAME AN EDGE WORKS IN IS THE ONE ITS NODES ARE IN, not the page. Resolving this
    # to the page frame and then STAMPING it on the elements defeated inheritance outright:
    # a node placed under a group with its own frame came out carrying `frame: page`, so it
    # rendered at the page origin and every diagram on the page sat on top of the others.
    # A default that overrides what the caller already said is worse than no default.
    stamp = frame
    frame = frame or model.frame_of(doc, a)
    fs, ts = (from_side, to_side) if (from_side and to_side) else _best_sides(doc, a, b,
                                                                             frame)
    start = _anchor(doc, a, fs, frame)
    end = _anchor(doc, b, ts, frame)
    # A PARALLEL EDGE IS OFFSET SIDEWAYS. Two nodes with an edge each way -- which is most of
    # a state machine -- had both drawn along the same line, one on top of the other, with
    # their labels in the same place. Nothing was wrong with either edge; there were simply
    # two of them in one corridor.
    parallel = _parallel_count(doc, a, b)
    if parallel:
        nx_, ny_ = -(end[1] - start[1]), end[0] - start[0]
        n_ = math.hypot(nx_, ny_) or 1.0
        shift = (parallel + 1) // 2 * (1 if parallel % 2 else -1) * 3.2
        start = (start[0] + nx_ / n_ * shift, start[1] + ny_ / n_ * shift)
        end = (end[0] + nx_ / n_ * shift, end[1] + ny_ / n_ * shift)
    if avoid is None:
        # SCOPED TO THIS DIAGRAM, not to the whole page. The default was every element
        # tagged `node` anywhere in the scene, and on a page with four diagrams that
        # included nodes in other frames -- measured into this one they land hundreds of
        # millimetres away, the routing region grows to cover them all, and the search is
        # refused as too large. A node in another coordinate space is not in the way.
        scope = parent or None
        avoid = []
        for addr, el, _p in model.walk(doc):
            if "node" not in (el.get("tags") or []):
                continue
            if scope and not addr.startswith(scope + "."):
                continue
            if not scope and model.frame_of(doc, addr) != frame:
                continue
            avoid.append(addr)
        for end_ in (a, b):
            if end_ not in avoid:
                avoid.append(end_)
    # KEPT INSIDE SOMETHING, when asked. The router is bounded by the page, which is right
    # for a connector on a page and wrong for one inside a panel: a bypass in panel B went
    # round the obstacle by leaving the panel, which is on the paper and not in the figure.
    if within is not None and bounds is None:
        wb = measure.bbox(doc, within, frame)["value"]
        bounds = (wb["x"], wb["y"], wb["x"] + wb["width"], wb["y"] + wb["height"])

    if not routed:
        pts = [start, end]
        report = {"routed": False, "kind": "straight"}
        kids = [build.polyline("line", pts, role=role)]
    else:
        out, report = layout.connect(doc, name, start, end, avoid, clearance, resolution,
                                     "orthogonal", role, None,
                                     head if kind in ("arrow", "both") else 0.0, frame,
                                     parent=parent, bounds=bounds)
        if not report.get("routed"):
            return doc, report
        doc = out
        here = f"{parent}.{name}" if parent else name
        g = model.find(doc, here)
        if kind == "both":
            pts0 = [(g["anchors"]["start"]["at"][0], g["anchors"]["start"]["at"][1])]
            line = g["children"][0]["geometry"]["d"]
            second = (line[1][1] - line[0][1], line[1][2] - line[0][2])
            g["children"].append(build.arrowhead("tail-head", pts0[0],
                                                 (-second[0], -second[1]), head,
                                                 role=role))
        if kind == "none":
            g["children"] = [c for c in g["children"] if c["name"] != "head"]
        if label:
            # STAGGERED ALONG THE EDGE for a parallel pair, and the plate SIZED TO THE TEXT.
            # Two edges between the same nodes had their labels at the same fraction of the
            # way along, 3.2mm apart, on 12mm plates -- so offsetting the edges separated the
            # lines and left the labels on top of each other. And a fixed-width plate is the
            # thing this toolkit exists to stop: it is a guess at how wide a word is.
            base = 0.5 + (0.0 if not parallel else (0.18 if parallel % 2 else -0.18)
                          * ((parallel + 1) // 2))
            lw, lh, _laid = auto_size(doc, label, label_role, pad_x=1.0, pad_y=0.4)
            # THE LABEL GOES WHERE IT COVERS LEAST, tried rather than assumed. The midpoint
            # of a routed edge is often exactly where it passes another node, and a plate
            # there hides that node's own label. A handful of fractions along the route are
            # measured and the first clear one is taken; when none is clear it falls back to
            # the midpoint and `figure.verify` reports the overlap, which is the honest
            # order -- try, then tell.
            mid, at_t = _clear_label_spot(doc, g["children"][0], base, lw, lh, frame,
                                          avoid, a, b, bounds)
            report["label_at"] = at_t
            g["children"].append(build.rect("label-plate", mid[0] - lw / 2,
                                            mid[1] - lh * 0.72, lw, lh, radius=0.6,
                                            role="paper-fill"))
            g["children"].append(build.text("label", label, mid, family=None, size=None,
                                            align="middle", role=label_role))
        g["tags"] = sorted(set((g.get("tags") or []) + ["edge"]))
        g["provenance"] = {"origin": "derived", "tool": "diagram.edge",
                           "tool_version": "1", "params": {"pair": sorted([a, b])}}
        report["from"], report["to"] = a, b
        report["parallel_offset"] = parallel
        report["sides"] = [fs, ts]
        return doc, report

    g = build.group(name, kids)
    g["tags"] = ["edge"]
    g["provenance"] = {"origin": "derived", "tool": "diagram.edge", "tool_version": "1",
                       "params": {"pair": sorted([a, b])}}
    inherited = model.frame_of(doc, parent) if parent else model._page_frame(doc)
    if frame != inherited:
        g["frame"] = frame
    doc = model.add(doc, g, parent)
    report.update({"from": a, "to": b, "sides": [fs, ts],
                   "parallel_offset": parallel,
                   "element": f"{parent}.{name}" if parent else name})
    return doc, report


def _clear_label_spot(doc, line_el, base, lw, lh, frame, avoid, a, b, bounds=None):
    """A point along the route whose label plate covers no other node. ``(point, t)``.

    **The plate is held inside the same bounds as the route.** Bounding the route and not its
    label kept the line in the panel and hung the label 3.4 mm off its left edge -- which is
    the sort of thing that looks like the bound did not work.
    """
    others = [x for x in (avoid or []) if x not in (a, b)]
    boxes = []
    for addr in others:
        try:
            boxes.append(measure.bbox(doc, addr, frame)["value"])
        except (ValueError, KeyError, measure.Unmeasurable):
            continue
    for t in (base, base - 0.15, base + 0.15, base - 0.28, base + 0.28, 0.2, 0.8):
        if not 0.05 <= t <= 0.95:
            continue
        p = _midpoint(line_el, t)
        x0, y0 = p[0] - lw / 2, p[1] - lh * 0.72
        x1, y1 = x0 + lw, y0 + lh
        if bounds and not (bounds[0] <= x0 and x1 <= bounds[2]
                           and bounds[1] <= y0 and y1 <= bounds[3]):
            continue
        if not any(not (x1 < bx["x"] or bx["x"] + bx["width"] < x0
                        or y1 < bx["y"] or bx["y"] + bx["height"] < y0)
                   for bx in boxes):
            return p, round(t, 4)
    return _midpoint(line_el, base), round(base, 4)


def _parallel_count(doc, a, b):
    """How many edges already join this pair, either way round."""
    n = 0
    for _addr, el, _p in model.walk(doc):
        if "edge" not in (el.get("tags") or []):
            continue
        prov = el.get("provenance") or {}
        pair = (prov.get("params") or {}).get("pair")
        if pair and set(pair) == {a, b}:
            n += 1
    return n


def _midpoint(el, t=0.5):
    """A point a fraction `t` of the way along a polyline, by arc length."""
    from . import geometry
    d = el["geometry"].get("d") or []
    pts = []
    for seg in d:
        nums = seg[1:]
        for i in range(0, len(nums) - 1, 2):
            pts.append((nums[i], nums[i + 1]))
    if len(pts) < 2:
        return pts[0] if pts else (0.0, 0.0)
    lens = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    total = sum(lens) or 1.0
    want = max(0.0, min(1.0, t)) * total
    for (a, b), l in zip(zip(pts, pts[1:]), lens):
        if want <= l or l == 0:
            u = 0.0 if l == 0 else want / l
            return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        want -= l
    return pts[-1]


# --------------------------------------------------------------------- containers
def container(doc, name, members, pad=3.0, label=None, role=_CONTAINER,
              label_role=_LABEL, frame=None, radius=1.5, parent=""):
    """A box that fits around the elements it names, and a label on its top edge.

    Re-running it **re-fits** an existing container, which is what "resizes with its
    contents" means in practice: add a node, run it again, the box grows.
    """
    frame = frame or (model.frame_of(doc, members[0]) if members
                      else model._page_frame(doc))
    boxes = [measure.bbox(doc, m, frame)["value"] for m in members]
    if not boxes:
        raise ValueError(f"{name}: a container needs at least one member")
    x0 = min(b["x"] for b in boxes) - pad
    y0 = min(b["y"] for b in boxes) - pad
    x1 = max(b["x"] + b["width"] for b in boxes) + pad
    y1 = max(b["y"] + b["height"] for b in boxes) + pad
    lift = 0.0
    if label:
        _w, h, _laid = auto_size(doc, label, label_role, pad_x=0.0, pad_y=0.0)
        lift = h + 1.0
        y0 -= lift
    kids = [build.rect("body", x0, y0, x1 - x0, y1 - y0, radius, role=role)]
    if label:
        kids.append(build.text("label", label, (x0 + pad, y0 + lift - 1.0), family=None,
                               size=None, role=label_role))
    here = f"{parent}.{name}" if parent else name
    existing = model.find(doc, here)
    if existing is not None:
        existing["children"] = kids
        existing["anchors"] = _container_anchors(x0, y0, x1, y1)
        return doc, {"container": here, "members": list(members), "refitted": True,
                     "box": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}}
    g = build.group(name, kids)
    g["tags"] = ["container"]
    g["anchors"] = _container_anchors(x0, y0, x1, y1)
    if frame:
        g["frame"] = frame
    doc = model.add(doc, g, parent)
    return doc, {"container": here, "members": list(members), "refitted": False,
                 "box": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}}


def _container_anchors(x0, y0, x1, y1):
    return {"top-left": {"how": "authored", "at": [x0, y0]},
            "centre": {"how": "authored", "at": [(x0 + x1) / 2, (y0 + y1) / 2]},
            "bottom-right": {"how": "authored", "at": [x1, y1]},
            "n": {"how": "authored", "at": [(x0 + x1) / 2, y0], "dir": [0, -1]},
            "s": {"how": "authored", "at": [(x0 + x1) / 2, y1], "dir": [0, 1]}}


# --------------------------------------------------------------------- layout
def layers(edges, names=None):
    """Longest-path layer assignment. Returns ``(layer_of, report)``.

    A cycle has no longest path, so a graph with one is reported rather than looped on: the
    nodes still get layers, from the acyclic part, and the edges that close a cycle are
    named. A state machine is full of cycles and still has to be drawable.
    """
    names = list(names or sorted({n for e in edges for n in e[:2]}))
    outs = {n: [] for n in names}
    ins = {n: [] for n in names}
    for a, b in [(e[0], e[1]) for e in edges]:
        if a in outs and b in ins:
            outs[a].append(b)
            ins[b].append(a)
    layer = {n: 0 for n in names}
    back = []
    order, seen, stack = [], set(), set()

    def visit(n, path):
        if n in stack:
            back.append((path[-1], n) if path else (n, n))
            return
        if n in seen:
            return
        seen.add(n)
        stack.add(n)
        for m in outs[n]:
            visit(m, path + [n])
        stack.discard(n)
        order.append(n)

    for n in names:
        visit(n, [])
    for n in reversed(order):
        for m in outs[n]:
            if (n, m) in back:
                continue
            layer[m] = max(layer[m], layer[n] + 1)
    return layer, {"layers": max(layer.values()) + 1 if layer else 0,
                   "back_edges": sorted(set(back)),
                   "cyclic": bool(back)}


def flow(doc, spec, edges, at=(0.0, 0.0), spacing=(10.0, 14.0), vertical=True,
         parent="", frame=None, label=None, avoid_others=True, **node_kw):
    """A whole layered diagram: nodes sized to their labels, then edges routed between them.

    `spec` is ``{name: label}`` and `edges` a sequence of ``(a, b)`` or ``(a, b, label)``.
    Returns ``(scene, report)`` with the layer assignment, the node sizes and each edge's
    clearance -- or, for an edge that could not be routed, why.
    """
    names = list(spec)
    layer, linfo = layers(edges, names)
    by_layer = {}
    for n in names:
        by_layer.setdefault(layer[n], []).append(n)

    sizes = {}
    for n in names:
        w, h, _laid = auto_size(doc, spec[n], **{k: v for k, v in node_kw.items()
                                                 if k in ("pad_x", "pad_y", "min_width",
                                                          "min_height", "max_width")})
        sizes[n] = (w, h)

    # LAYERS ARE CENTRED ON A COMMON AXIS, not left-aligned. Two vertically connected nodes
    # of different widths otherwise have different centres, and the edge between them has to
    # jog sideways -- 0.88mm on the first flowchart drawn here, which reads as a kink in
    # what should be a straight arrow. The router was right; the layout was not.
    extents = {}
    for li, row in by_layer.items():
        extents[li] = sum((sizes[n][0] if vertical else sizes[n][1]) for n in row) \
            + spacing[0] * (len(row) - 1)
    widest = max(extents.values()) if extents else 0.0
    placed, cursor = {}, float(at[1] if vertical else at[0])
    for li in sorted(by_layer):
        row = by_layer[li]
        along = float(at[0] if vertical else at[1]) + (widest - extents[li]) / 2.0
        deep = max((sizes[n][1] if vertical else sizes[n][0]) for n in row)
        pos = along
        for n in row:
            w, h = sizes[n]
            placed[n] = (pos, cursor) if vertical else (cursor, pos)
            pos += (w if vertical else h) + spacing[0]
        cursor += deep + spacing[1]
    report_extent = {"width": widest if vertical else cursor - float(at[0]),
                     "height": cursor - float(at[1]) if vertical else widest}

    reports = {}
    for n in names:
        doc, rep = node(doc, n, spec[n], placed[n], parent, frame=frame, **node_kw)
        reports[n] = rep

    edge_reports = []
    for i, e in enumerate(edges, 1):
        a, b = e[0], e[1]
        lab = e[2] if len(e) > 2 else None
        ename = f"edge-{i:02d}"
        doc, rep = edge(doc, ename, f"{parent}.{a}" if parent else a,
                        f"{parent}.{b}" if parent else b, lab, frame=frame,
                        avoid=None if avoid_others else [], parent=parent)
        rep["name"] = ename
        edge_reports.append(rep)

    report = {"nodes": reports, "edges": edge_reports, "layer": layer,
              "extent": report_extent,
              "unrouted": [r for r in edge_reports if not r.get("routed")]}
    report.update(linfo)
    return doc, report


def tree(doc, root, children, at=(0.0, 0.0), spacing=(8.0, 12.0), parent="", frame=None,
         labels=None, **node_kw):
    """A tree from ``{parent: [children]}``. Returns ``(scene, report)``.

    Laid out by subtree width, so siblings do not collide and a parent sits over its
    children's span. Edges are straight, because a tree has nothing to route around.

    **Keys are slugged into element names and kept as labels.** A tree of gene names --
    `ampR`, `EcoRI` -- is the obvious use, and those are not element names: the scene refused
    every one of them. The mapping comes back in the report so a caller can address what it
    built.
    """
    given = {}

    def collect(n):
        given[n] = (labels or {}).get(n, n)
        for c in children.get(n, []):
            collect(c)
    collect(root)
    names = {n: _slug(n) for n in given}
    if len(set(names.values())) != len(names):
        clash = sorted(k for k in names
                       if list(names.values()).count(names[k]) > 1)
        raise ValueError(f"these node keys slug to the same element name: "
                         f"{', '.join(clash)}. Give them keys that differ by more than "
                         f"punctuation, or pass `labels` and use plain keys.")
    labels = {n: given[n] for n in given}

    widths = {}
    for n in labels:
        w, _h, _l = auto_size(doc, labels[n], **{k: v for k, v in node_kw.items()
                                                 if k in ("pad_x", "pad_y", "min_width",
                                                          "min_height", "max_width")})
        widths[n] = w

    def span(n):
        kids = children.get(n, [])
        if not kids:
            return widths[n]
        return max(widths[n], sum(span(c) for c in kids) + spacing[0] * (len(kids) - 1))

    placed = {}

    def place(n, x, depth):
        s = span(n)
        placed[n] = (x + (s - widths[n]) / 2, at[1] + depth * spacing[1] * 2)
        cur = x
        for c in children.get(n, []):
            place(c, cur, depth + 1)
            cur += span(c) + spacing[0]

    place(root, float(at[0]), 0)
    reports = {}
    for n, pos in placed.items():
        doc, rep = node(doc, names[n], labels[n], pos, parent, frame=frame, **node_kw)
        reports[n] = rep
    edges = []
    for n, kids in children.items():
        for c in kids:
            edges.append((n, c))
    edge_reports = []
    for i, (a, b) in enumerate(edges, 1):
        pa = f"{parent}.{names[a]}" if parent else names[a]
        pb = f"{parent}.{names[b]}" if parent else names[b]
        doc, rep = edge(doc, f"branch-{i:02d}", pa, pb, frame=frame, routed=False,
                        kind="none", parent=parent)
        edge_reports.append(rep)
    return doc, {"nodes": reports, "edges": edge_reports, "names": names,
                 "depth": max(_depth(root, children), 1)}


def _depth(n, children, d=1):
    kids = children.get(n, [])
    return d if not kids else max(_depth(c, children, d + 1) for c in kids)


def swimlanes(doc, lanes, at=(0.0, 0.0), width=160.0, lane_height=26.0, parent="",
              frame=None, label_role=_LABEL, role=_CONTAINER):
    """Horizontal lanes with a heading each. Returns ``(scene, report)``.

    Nodes are placed into a lane by the caller; what this makes is the lanes themselves and
    an anchor per lane to place into.
    """
    kids, anchors = [], {}
    head_w = 0.0
    for name in lanes:
        w, _h, _l = auto_size(doc, name, label_role, pad_x=2.0, pad_y=1.0)
        head_w = max(head_w, w)
    for i, name in enumerate(lanes):
        y = float(at[1]) + i * lane_height
        kids.append(build.rect(f"lane-{i + 1}", float(at[0]), y, width, lane_height,
                               role=role))
        kids.append(build.text(f"lane-{i + 1}-label", name,
                               (float(at[0]) + 1.5, y + lane_height / 2 + 1.0),
                               family=None, size=None, role=label_role))
        anchors[f"{_slug(name)}"] = {"how": "authored",
                                     "at": [float(at[0]) + head_w + 3.0,
                                            y + lane_height / 2]}
    g = build.group("swimlanes", kids)
    g["tags"] = ["swimlanes"]
    g["anchors"] = anchors
    if frame:
        g["frame"] = frame
    doc = model.add(doc, g, parent)
    return doc, {"lanes": list(lanes), "heading_width": head_w,
                 "lane_height": lane_height, "anchors": sorted(anchors)}


def _slug(s):
    out = "".join(c if (c.isalnum() and c.isascii()) else "-" for c in str(s).lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "lane"
