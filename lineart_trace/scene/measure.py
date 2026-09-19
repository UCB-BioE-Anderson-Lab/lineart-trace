"""Measurement and inspection: §3.2, the family that most directly closes the gap.

**Done when a model never has to guess a coordinate or a size.** Everything here answers in a
named frame and a named unit, and everything that cannot be answered exactly says which
approximation it used and in which direction it errs. A measurement that is silently
optimistic -- a box slightly too small, a clearance slightly too generous -- is worse than no
measurement, because a figure built on it looks checked.

Every result is a `scene.measurement` envelope: what was measured, of what, in which frame,
in what unit, and the value.
"""
from . import fonts, geometry, model

__all__ = ["envelope", "Unmeasurable", "encloses", "runs_in_frame",
           "runs_in_local", "bbox", "length", "area", "centroid", "ink",
           "clearance", "collisions", "probe", "nearest_anchor", "text", "inventory",
           "MEASURES"]


def envelope(doc, measure, target, frame, value, **extra):
    """A measurement, in the shape `scene.measurement` declares."""
    unit = (doc.get("frames") or {}).get(frame, {}).get("unit", "mm") if doc else "pt"
    out = {"format": "lineart.measurement/1", "measure": measure, "target": target,
           "frame": frame, "unit": unit, "value": value}
    if doc and doc.get("name"):
        out["scene"] = doc["name"]
    out.update(extra)
    return out


# --------------------------------------------------------------------- geometry access
class Unmeasurable(Exception):
    """Something whose extent cannot be established -- never something with a zero extent.

    Raised, in practice, for text in a font this installation does not have. The alternative
    was what this code did first: give a text element the single point it is anchored at, so
    its bounding box came back 0 x 0. Every check downstream then passed it -- it overflowed
    nothing, collided with nothing, fitted anywhere -- which is the exact failure §1 names
    first: labels that overflow their boxes, in a system that reports no problem.
    """


def _text_runs(el, doc=None, frame=None):
    """A text element's INK BOX as a closed run, measured from the font, IN ITS OWN FRAME.

    Where the ink sits relative to the anchor point, with y running down: horizontally by
    `align`, vertically by `baseline`, and the box itself from the glyphs' own extents. When
    the face has no readable outlines the em box is used instead, which is larger than the
    ink and never smaller.

    **The size is resolved into the frame's unit before anything is measured**, by the same
    rule the rest of the format uses: a bare number is already in the frame, a suffixed
    string is a length on the page. Measuring ``"6pt"`` as the number 6 and handing the
    resulting advance back as frame units made every label in a millimetre frame come back
    about three times too wide -- and the only reason it was found is that the overlap check
    complained about captions crossing the boxes they sit inside.
    """
    g = el["geometry"]
    st = model.effective_style(doc, el)
    family = st.get("font_family")
    size = st.get("font_size")
    if not family or size is None:
        raise Unmeasurable(
            f"a text element with no font_family or font_size has no measurable extent; "
            f"declare them, or bind a role that does")
    if doc is not None and frame is not None:
        try:
            size = model.resolve_length(doc, size, frame)
        except (ValueError, KeyError) as e:
            raise Unmeasurable(str(e))
    elif isinstance(size, str):
        from . import text as _t
        try:
            size = _t.as_unit(size, "pt")
        except ValueError as e:
            raise Unmeasurable(str(e))
    try:
        m = fonts.metrics(g.get("text", ""), family, float(size))
    except fonts.FontNotFound as e:
        raise Unmeasurable(str(e))
    x, y = float(g["at"][0]), float(g["at"][1])
    dx = {"start": 0.0, "middle": -m["advance"] / 2.0,
          "end": -m["advance"]}.get(g.get("align", "start"), 0.0)
    dy = {"alphabetic": 0.0, "middle": (m["cap_height"] or m["ascent"]) / 2.0,
          "hanging": m["ascent"], "ideographic": -m["descent"]}.get(
              g.get("baseline", "alphabetic"), 0.0)
    ink = m["ink"]
    if ink is None:
        x0, x1 = 0.0, m["advance"]
        y0, y1 = -m["descent"], m["ascent"]
    else:
        x0, y0, x1, y1 = ink["x0"], ink["y0"], ink["x1"], ink["y1"]
    left, right = x + dx + x0, x + dx + x1
    top, bottom = y + dy - y1, y + dy - y0
    if right - left <= 0 or bottom - top <= 0:
        return [[["M", x + dx, y + dy]]]          # an empty string marks nothing
    return [[["M", left, top], ["L", right, top], ["L", right, bottom],
             ["L", left, bottom], ["Z"]]]


def _runs_of(el, doc=None, frame=None):
    g = el.get("geometry") or {}
    if g.get("kind") == "path":
        return [g.get("d") or []]
    if g.get("kind") == "region":
        return list(g.get("loops") or [])
    if g.get("kind") == "text":
        return _text_runs(el, doc, frame)
    if g.get("kind") == "image":
        x, y = g["at"]
        w, h = g["width"], g["height"]
        return [[["M", x, y], ["L", x + w, y], ["L", x + w, y + h], ["L", x, y + h], ["Z"]]]
    return []


def _transform_run(run, m):
    out = []
    for s in run:
        verb, n = s[0], [float(v) for v in s[1:]]
        pts = []
        for i in range(0, len(n) - 1, 2):
            pts += list(model.apply(m, n[i], n[i + 1]))
        out.append([verb] + pts)
    return out


def _subtree(doc, root):
    for addr, el, _p in model.walk(doc):
        if addr == root or addr.startswith(root + "."):
            yield addr, el


def runs_in_frame(doc, address, frame, include_guides=False):
    """Every run beneath `address`, carried into `frame`.

    One place where an element's own frame, its ancestors' frames and its own transform are
    composed. Five measures needed this and five copies of it would disagree the first time
    one of them was fixed.
    """
    want = model.invert(model.frame_to_page(doc, frame))
    return _runs_relative(doc, address, want, include_guides)


def _runs_relative(doc, address, want, include_guides=False, skip_text=False):
    """Runs beneath `address`. A guide DESCENDANT is skipped; the named element never is.

    Construction geometry must not inflate the box of a group that happens to contain it --
    that is the whole reason a guide does not render. But a guide asked for BY NAME is a
    thing somebody wants the extent of: a page margin to keep inside, a baseline to align
    to. Excluding it there made `keep this inside the page area` fail with "nothing with
    geometry to place", which reads like a bug in the scene rather than in the measure.
    """
    out = []
    for addr, el in _subtree(doc, address):
        if el.get("type") == "guide" and not include_guides and addr != address:
            continue
        if skip_text and (el.get("geometry") or {}).get("kind") == "text":
            continue
        runs = _runs_of(el, doc, model.frame_of(doc, addr))
        if not runs:
            continue
        m = model.compose(want, model.element_to_page(doc, addr))
        out += [_transform_run(r, m) for r in runs]
    return out


def runs_in_local(doc, address, include_guides=False, skip_text=False):
    """Every run beneath `address`, in that element's own local coordinates.

    The space an element's geometry and its anchors are both written in, and therefore the
    only space a derived anchor may be computed in: a recipe evaluated anywhere else
    produces a number that the next reader will transform again.
    """
    want = model.invert(model.element_to_page(doc, address))
    return _runs_relative(doc, address, want, include_guides, skip_text)


def encloses(doc, address):
    """Does anything beneath `address` enclose an area? What containment tests may assume."""
    for addr, el in _subtree(doc, address):
        g = el.get("geometry") or {}
        if g.get("kind") in ("region", "image"):
            return True
        if g.get("kind") == "path" and g.get("closed"):
            return True
    return False


def _resolved(doc, target, frame):
    got = model.resolve(doc, target)
    if got["kind"] == "anchor":
        a = got["anchor"]
        if "at" not in a:
            raise ValueError(f"{target}: this anchor has no resolved position")
        m = model.compose(model.invert(model.frame_to_page(doc, frame)),
                          model.element_to_page(doc, got["element_address"]))
        return None, model.apply(m, a["at"][0], a["at"][1])
    return got["element_address"], None


def _frame(doc, frame):
    return frame or model._page_frame(doc)


# --------------------------------------------------------------------- the measures
def bbox(doc, target, frame=None, stroke=False):
    """The TIGHT bounding box: the curve's own extent, not its control points'.

    With `stroke`, the box is grown by half of each element's stroke width -- exact for
    round caps and joins, and an over-estimate of at most a miter's length otherwise. Over,
    never under: a box that is too small is a collision check that passes on a figure that
    overlaps.
    """
    frame = _frame(doc, frame)
    root, pt = _resolved(doc, target, frame)
    if pt is not None:
        return envelope(doc, "bbox", target, frame,
                        {"x": pt[0], "y": pt[1], "width": 0.0, "height": 0.0})
    box = geometry.bounds(runs_in_frame(doc, root, frame))
    if box is None:
        raise ValueError(f"{target}: nothing with geometry beneath it, so it has no extent")
    pad = 0.0
    if stroke:
        for addr, el in _subtree(doc, root):
            w = model.effective_style(doc, el).get("stroke_width")
            if w is not None:
                s = model.scale_of(model.element_to_page(doc, addr))
                t = model.scale_of(model.frame_to_page(doc, frame))
                pad = max(pad, model.resolve_length(doc, w, model.frame_of(doc, addr))
                          * s / (t or 1.0) / 2.0)
        box = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    return envelope(doc, "bbox", target, frame,
                    {"x": box[0], "y": box[1],
                     "width": box[2] - box[0], "height": box[3] - box[1]},
                    includes_stroke=bool(stroke))


def length(doc, target, frame=None):
    """Total arc length of every path beneath `target`."""
    frame = _frame(doc, frame)
    root, pt = _resolved(doc, target, frame)
    if pt is not None:
        return envelope(doc, "length", target, frame, 0.0)
    return envelope(doc, "length", target, frame,
                    geometry.length(runs_in_frame(doc, root, frame)))


def area(doc, target, frame=None):
    """Enclosed area, unsigned. Open paths enclose nothing and report zero."""
    frame = _frame(doc, frame)
    root, pt = _resolved(doc, target, frame)
    if pt is not None:
        return envelope(doc, "area", target, frame, 0.0)
    return envelope(doc, "area", target, frame,
                    abs(geometry.area(runs_in_frame(doc, root, frame))))


def centroid(doc, target, frame=None):
    """The centroid of the enclosed region, saying which kind of centroid it is.

    `basis` is ``region`` for a shape with area and ``points`` for one without -- an open
    stroke has no region centroid, and handing back the mean of its points under the same
    name would be a different quantity wearing this one's clothes.
    """
    frame = _frame(doc, frame)
    root, pt = _resolved(doc, target, frame)
    if pt is not None:
        return envelope(doc, "centroid", target, frame, {"x": pt[0], "y": pt[1]},
                        basis="anchor")
    c, basis = geometry.centroid(runs_in_frame(doc, root, frame))
    if c is None:
        raise ValueError(f"{target}: nothing with geometry beneath it")
    return envelope(doc, "centroid", target, frame, {"x": c[0], "y": c[1]}, basis=basis)


def ink(doc, target, frame=None, tol=0.05):
    """How much of the box is actually marked: enclosed area over bounding-box area."""
    frame = _frame(doc, frame)
    root, _pt = _resolved(doc, target, frame)
    runs = runs_in_frame(doc, root, frame)
    box = geometry.bounds(runs)
    if box is None:
        raise ValueError(f"{target}: nothing with geometry beneath it")
    boxarea = (box[2] - box[0]) * (box[3] - box[1])
    a = abs(geometry.area(runs))
    return envelope(doc, "ink", target, frame,
                    {"area": a, "box_area": boxarea,
                     "coverage": (a / boxarea) if boxarea > 0 else 0.0})


def clearance(doc, target, other, frame=None, tol=0.05):
    """The gap between two elements: 0 when they touch or overlap, else the closest approach.

    Measured on outlines flattened to `tol`, so the answer is exact for shapes that differ
    from the real ones by at most that much. Reported with `tol` attached, because a
    clearance quoted without its tolerance is a number nobody can act on.
    """
    frame = _frame(doc, frame)
    a_root, _ = _resolved(doc, target, frame)
    b_root, _ = _resolved(doc, other, frame)
    pa = geometry.flatten(runs_in_frame(doc, a_root, frame), tol)
    pb = geometry.flatten(runs_in_frame(doc, b_root, frame), tol)
    if not pa or not pb:
        raise ValueError(f"{target} or {other}: nothing with geometry to measure between")
    if geometry.polys_overlap(pa, pb, a_closed=encloses(doc, a_root),
                              b_closed=encloses(doc, b_root)):
        return envelope(doc, "clearance", f"{target} .. {other}", frame,
                        {"gap": 0.0, "overlaps": True}, tolerance=tol)
    best = float("inf")
    for poly in pa:
        for p in poly:
            _q, d = geometry.nearest_point(pb, p)
            best = min(best, d)
    for poly in pb:
        for p in poly:
            _q, d = geometry.nearest_point(pa, p)
            best = min(best, d)
    return envelope(doc, "clearance", f"{target} .. {other}", frame,
                    {"gap": best, "overlaps": False}, tolerance=tol)


def collisions(doc, frame=None, tol=0.05, within=None):
    """Every pair of leaf elements whose ink overlaps. §3.14's overlap detection.

    Compares leaves rather than groups, because "this group overlaps that group" is almost
    always true and almost never what was asked. Boxes are rejected first and outlines
    compared only for the pairs that survive, which is what keeps a 900-element scene from
    being a quadratic outline comparison.
    """
    frame = _frame(doc, frame)
    leaves, unmeasurable = [], []
    for addr, el, _p in model.walk(doc):
        if el.get("type") in ("group", "guide") or not el.get("geometry"):
            continue
        if within and not (addr == within or addr.startswith(within + ".")):
            continue
        try:
            runs = runs_in_frame(doc, addr, frame)
        except Unmeasurable as e:
            unmeasurable.append({"address": addr, "why": str(e)})
            continue
        box = geometry.bounds(runs)
        if box:
            leaves.append((addr, box, runs))
    hits = []
    for i in range(len(leaves)):
        ai, abox, aruns = leaves[i]
        for j in range(i + 1, len(leaves)):
            bi, bbox_, bruns = leaves[j]
            if (abox[2] < bbox_[0] or bbox_[2] < abox[0]
                    or abox[3] < bbox_[1] or bbox_[3] < abox[1]):
                continue
            if geometry.polys_overlap(geometry.flatten(aruns, tol),
                                      geometry.flatten(bruns, tol),
                                      a_closed=encloses(doc, ai),
                                      b_closed=encloses(doc, bi)):
                hits.append({"a": ai, "b": bi})
    return envelope(doc, "collisions", within or "(whole scene)", frame,
                    {"pairs": hits, "count": len(hits), "compared": len(leaves),
                     "unmeasurable": unmeasurable},
                    tolerance=tol)


def probe(doc, x, y, frame=None, tol=0.05):
    """What is at this coordinate: every element whose ink contains it, innermost last."""
    frame = _frame(doc, frame)
    hit, unmeasurable = [], []
    for addr, el, _p in model.walk(doc):
        if el.get("type") in ("group", "guide") or not el.get("geometry"):
            continue
        try:
            runs = runs_in_frame(doc, addr, frame)
        except Unmeasurable as e:
            unmeasurable.append({"address": addr, "why": str(e)})
            continue
        box = geometry.bounds(runs)
        if not box or not (box[0] <= x <= box[2] and box[1] <= y <= box[3]):
            continue
        polys = geometry.flatten(runs, tol)
        rule = (el.get("geometry") or {}).get("fill_rule", "evenodd")
        inside = geometry.contains(polys, (x, y), rule) if encloses(doc, addr) else False
        _q, d = geometry.nearest_point(polys, (x, y))
        if inside or d <= tol * 4:
            hit.append({"address": addr, "type": el.get("type"), "inside": bool(inside),
                        "distance": d})
    return envelope(doc, "probe", f"({x}, {y})", frame,
                    {"hits": hit, "count": len(hit), "unmeasurable": unmeasurable},
                    tolerance=tol)


def nearest_anchor(doc, x, y, frame=None):
    """The anchor closest to a point, and how far away it is."""
    frame = _frame(doc, frame)
    want = model.invert(model.frame_to_page(doc, frame))
    best = None
    for addr, el, _p in model.walk(doc):
        for name, a in sorted((el.get("anchors") or {}).items()):
            if "at" not in a:
                continue
            m = model.compose(want, model.element_to_page(doc, addr))
            px, py = model.apply(m, a["at"][0], a["at"][1])
            d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
            if best is None or d < best["distance"]:
                best = {"address": f"{addr}.{name}", "x": px, "y": py, "distance": d}
    if best is None:
        raise ValueError("this scene has no anchor with a resolved position")
    return envelope(doc, "nearest-anchor", f"({x}, {y})", frame, best)


def text(string, family, size, weight="regular", style="normal", doc=None, frame=None):
    """Text metrics without drawing anything: §1's "extent is unknowable without rendering".

    Sizes are in the unit `size` is given in. The face that was measured comes back with the
    numbers, digest and all, because a metric is only reproducible alongside the file it was
    read from.
    """
    m = fonts.metrics(string, family, size, weight, style)
    out = {"advance": m["advance"], "ascent": m["ascent"], "descent": m["descent"],
           "line_height": m["line_height"], "cap_height": m["cap_height"],
           "x_height": m["x_height"], "ink": m["ink"]}
    env = envelope(doc, "text", string, frame or "page", out, font=m["font"],
                   kerning=m["kerning"])
    if doc is None:
        env["unit"] = "pt"
        env.pop("scene", None)
    if m.get("missing"):
        env["missing"] = m["missing"]
    return env


def inventory(doc):
    """What is in this scene, counted: types, roles, colours, fonts, frames. §3.15.

    The plain-language answer to "what am I looking at", which is also the colour inventory
    §3.2 asks for and the input to §3.11's style linting.
    """
    types, roles, colours, families_, tags = {}, {}, {}, {}, {}
    anchors = 0
    for _addr, el, _p in model.walk(doc):
        types[el["type"]] = types.get(el["type"], 0) + 1
        if el.get("role"):
            roles[el["role"]] = roles.get(el["role"], 0) + 1
        for t in el.get("tags") or []:
            tags[t] = tags.get(t, 0) + 1
        st = model.effective_style(doc, el)
        for key in ("stroke", "fill"):
            v = st.get(key)
            if v and v != "none":
                colours[v] = colours.get(v, 0) + 1
        if st.get("font_family"):
            families_[st["font_family"]] = families_.get(st["font_family"], 0) + 1
        anchors += len(el.get("anchors") or {})
    value = {
        "elements": len(model.addresses(doc)),
        "types": dict(sorted(types.items())),
        "roles": dict(sorted(roles.items())),
        "tags": dict(sorted(tags.items())),
        "colours": dict(sorted(colours.items(), key=lambda kv: (-kv[1], kv[0]))),
        "fonts": dict(sorted(families_.items())),
        "frames": sorted((doc.get("frames") or {}).keys()),
        "anchors": anchors,
    }
    return envelope(doc, "inventory", doc.get("name", "(scene)"),
                    model._page_frame(doc), value)


#: The measures `lineart-scene measure` performs, each taking ``(doc, target, frame)``.
MEASURES = {"bbox": bbox, "length": length, "area": area, "centroid": centroid, "ink": ink}
