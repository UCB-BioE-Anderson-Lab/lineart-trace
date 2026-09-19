"""Verification: §3.14. **Done when "is this figure correct" has an answer that is not
"look at it".**

Every check here is against the figure's FINAL PHYSICAL SIZE, because that is the only size
at which the question means anything: a 4 pt label is legible on a screen at 200% and gone at
column width, and no amount of looking at it in a preview will tell you which you have.

Checks are declared in `RULES` with a default threshold and the reason the threshold is what
it is. A finding is ``error`` when the figure is wrong, ``warning`` when it is probably wrong
and something legitimate looks the same, and nothing is reported as a finding that the tool
cannot substantiate -- an unmeasurable check is `unchecked`, reported separately and never
folded into a pass.
"""
import math

from . import fonts, geometry, measure, model

__all__ = ["RULES", "check", "contrast_ratio", "simulate", "DEFAULTS"]

#: Thresholds in POINTS on the page, with the reason each one is the number it is. They are
#: arguments, not laws: a poster and a journal column do not share them, which is why every
#: one is overridable and why the report always states the value it used.
DEFAULTS = {
    "min_type_pt": 5.0,        # below ~5pt most journals refuse; 6-7pt is typical for panels
    "min_stroke_pt": 0.25,     # ~0.09mm: a thinner rule drops out on an offset press
    "min_separation_pt": 0.5,  # two lines closer than this merge into one when printed
    "min_contrast": 3.0,       # WCAG's ratio for graphical objects and large text
    "delta_e": 12.0,           # below this two colours are hard to tell apart side by side
}

RULES = ("type-size", "stroke-weight", "separation", "contrast", "off-canvas",
         "label-overlap", "occluded", "colour-distinguishable", "missing-glyphs",
         "unsolved", "accessibility")

# WHY `label-overlap` AND NOT `overlap`, and why `separation` only looks across objects.
#
# The first version of these two reported every overlapping pair and every close pair in the
# scene. Run on the first real figure -- a DNA duplex seated in a traced enzyme -- it
# produced 27 warnings, every one of them about the drawing being a drawing: two strands
# cross, thirteen rungs meet both strands, the duplex enters the enzyme because that is the
# point of the figure. A check that fires on every correct figure is not a strict check, it
# is one nobody will read, and it hides the one finding that matters in a wall of the ones
# that do not.
#
# So the rules say what they actually mean. **An overlap is a defect when a LABEL is
# involved** -- text on top of ink, or two labels on top of each other -- and otherwise it is
# the drawing. **A separation is a layout question between OBJECTS**, so it is measured
# between different top-level elements and never inside one: within a single drawn thing,
# closeness is the thing. The exhaustive "what overlaps anything" scan still exists and is
# `scene.collide`, where it is an answer somebody asked for rather than a verdict.
_LABELLISH = ("text",)


# --------------------------------------------------------------------- colour
def _rgb(colour):
    """``#rgb``/``#rrggbb`` to 0-1 floats, or None for anything else (``none``, a url)."""
    if not isinstance(colour, str) or not colour.startswith("#"):
        return None
    h = colour[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None


def _luminance(rgb):
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    """WCAG contrast ratio between two colours, 1.0 to 21.0, or None if either is not one."""
    ra, rb = _rgb(a), _rgb(b)
    if ra is None or rb is None:
        return None
    la, lb = _luminance(ra), _luminance(rb)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


#: Viénot, Brettel & Mollon (1999) LMS reductions, as sRGB-to-sRGB matrices.
_CVD = {
    "deuteranopia": ((0.625, 0.375, 0.0), (0.7, 0.3, 0.0), (0.0, 0.3, 0.7)),
    "protanopia": ((0.567, 0.433, 0.0), (0.558, 0.442, 0.0), (0.0, 0.242, 0.758)),
    "tritanopia": ((0.95, 0.05, 0.0), (0.0, 0.433, 0.567), (0.0, 0.475, 0.525)),
}


def simulate(colour, kind="deuteranopia"):
    """A colour as it appears under one kind of dichromacy. Returns ``#rrggbb`` or None."""
    rgb = _rgb(colour)
    if rgb is None or kind not in _CVD:
        return None
    m = _CVD[kind]
    out = tuple(min(1.0, max(0.0, sum(m[i][j] * rgb[j] for j in range(3))))
                for i in range(3))
    return "#" + "".join(f"{int(round(c * 255)):02x}" for c in out)


def _lab(rgb):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.0
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def g_(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)
    fx, fy, fz = g_(x), g_(y), g_(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(a, b):
    ra, rb = _rgb(a), _rgb(b)
    if ra is None or rb is None:
        return None
    la, lb = _lab(ra), _lab(rb)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(la, lb)))


# --------------------------------------------------------------------- the checks
def _pt(doc, value, frame):
    """A length in a frame, as points on the page."""
    n = model.resolve_length(doc, value, frame)
    on_page = n * model.scale_of(model.frame_to_page(doc, frame))
    return model.to_unit(on_page, (doc.get("canvas") or {}).get("unit", "mm"), "pt")


def geometry_box(b):
    """A ``(x0, y0, x1, y1)`` tuple as the dict shape the box helpers pass around."""
    return {"x": b[0], "y": b[1], "width": b[2] - b[0], "height": b[3] - b[1]}


def _collapse(findings):
    """One finding per distinct fact, listing every element it applies to.

    Thirteen base-pair rungs drawn in one colour that fails contrast is ONE defect with one
    fix, and reporting it thirteen times buries whatever else the report found. The count and
    the full element list stay on the finding, so nothing is lost -- only repeated.
    """
    order, groups = [], {}
    for f in findings:
        key = (f["rule"], f["severity"], f["message"])
        if key not in groups:
            groups[key] = dict(f)
            groups[key]["elements"] = []
            order.append(key)
        if f.get("element"):
            groups[key]["elements"].append(f["element"])
    out = []
    for key in order:
        g = groups[key]
        n = len(g["elements"])
        if n > 1:
            g["count"] = n
            g["element"] = f"{g['elements'][0]} and {n - 1} more"
        else:
            g.pop("elements", None)
        out.append(g)
    return out


def check(doc, rules=None, thresholds=None, solve_report=None, tol=0.05):
    """Every finding about this figure at its declared physical size.

    Returns ``{"findings": [...], "unchecked": [...], "thresholds": {...},
    "canvas": {...}}``. A finding carries `rule`, `severity`, `element`, `message` and the
    numbers behind it, so a report can be acted on without re-measuring.
    """
    want = set(rules or RULES)
    th = dict(DEFAULTS)
    th.update(thresholds or {})
    canvas = doc.get("canvas") or {}
    page = model._page_frame(doc)
    out, unchecked = [], []

    def add(rule, severity, element, message, **numbers):
        out.append(dict({"rule": rule, "severity": severity, "element": element,
                         "message": message}, **numbers))

    bg = canvas.get("background") or "none"
    bg_rgb = _rgb(bg)

    for addr, el, _p in model.walk(doc):
        st = model.effective_style(doc, el)
        frame = model.frame_of(doc, addr)
        geom = el.get("geometry") or {}

        if "type-size" in want and geom.get("kind") == "text":
            size = st.get("font_size")
            if size is None:
                unchecked.append({"rule": "type-size", "element": addr,
                                  "why": "no font_size on the element or its role"})
            else:
                pt = _pt(doc, size, frame)
                if pt < th["min_type_pt"] - 1e-9:
                    add("type-size", "error", addr,
                        f"{pt:.2f}pt type, below the {th['min_type_pt']:g}pt floor",
                        measured_pt=pt, threshold_pt=th["min_type_pt"],
                        text=geom.get("text"))

        if "stroke-weight" in want and st.get("stroke") not in (None, "none"):
            w = st.get("stroke_width")
            if w is None:
                unchecked.append({"rule": "stroke-weight", "element": addr,
                                  "why": "stroked, but no stroke_width is declared"})
            else:
                pt = _pt(doc, w, frame)
                if pt < th["min_stroke_pt"] - 1e-9:
                    add("stroke-weight", "error", addr,
                        f"{pt:.3f}pt stroke, below the {th['min_stroke_pt']:g}pt floor",
                        measured_pt=pt, threshold_pt=th["min_stroke_pt"])

        if "contrast" in want:
            # A FILL IS ONLY CHECKED WHEN IT IS THE ONLY THING MAKING THE SHAPE VISIBLE.
            # A pale surface tint behind a label, drawn with a stroke that passes on its
            # own, is a legitimate figure and the first version of this rule called every
            # one of them an error. Contrast asks whether a reader can SEE the thing; an
            # outlined shape is seen by its outline.
            stroked = st.get("stroke") and st["stroke"] != "none"
            for key in ("stroke", "fill"):
                c = st.get(key)
                if not c or c == "none":
                    continue
                if key == "fill" and stroked:
                    continue
                # A FILL EXACTLY EQUAL TO THE BACKGROUND IS DELIBERATE. A knockout or a
                # legend's backing plate is *meant* to be invisible; what has to be visible
                # is what sits on it. And an accident gives you a colour CLOSE to the
                # background, not one identical to it at eight bits a channel -- so an exact
                # match is the one case this can read as intent rather than error.
                if key == "fill" and _rgb(c) == bg_rgb:
                    continue
                if bg_rgb is None:
                    unchecked.append({"rule": "contrast", "element": addr,
                                      "why": f"the canvas background is {bg!r}, so there "
                                             f"is nothing to measure contrast against"})
                    break
                ratio = contrast_ratio(c, bg)
                if ratio is not None and ratio < th["min_contrast"]:
                    add("contrast", "error", addr,
                        f"{key} {c} on {bg} is {ratio:.2f}:1, below "
                        f"{th['min_contrast']:g}:1", ratio=ratio, colour=c,
                        background=bg, threshold=th["min_contrast"])

        if "missing-glyphs" in want and geom.get("kind") == "text":
            fam = st.get("font_family")
            if not fam:
                unchecked.append({"rule": "missing-glyphs", "element": addr,
                                  "why": "no font_family declared"})
            else:
                try:
                    m = fonts.metrics(geom.get("text", ""), fam, 10)
                except fonts.FontNotFound as e:
                    unchecked.append({"rule": "missing-glyphs", "element": addr,
                                      "why": str(e)})
                else:
                    if m.get("missing"):
                        add("missing-glyphs", "error", addr,
                            f"{fam} has no glyph for {m['missing']!r}; it will print as "
                            f"a box or fall back to another face",
                            characters=m["missing"], family=fam)

        if "off-canvas" in want and geom:
            try:
                box = measure.bbox(doc, addr, page)["value"]
            except measure.Unmeasurable as e:
                unchecked.append({"rule": "off-canvas", "element": addr, "why": str(e)})
                continue
            except (ValueError, KeyError):
                continue
            x0, y0 = box["x"], box["y"]
            x1, y1 = x0 + box["width"], y0 + box["height"]
            w, h = canvas.get("width", 0), canvas.get("height", 0)
            if x1 < 0 or y1 < 0 or x0 > w or y0 > h:
                add("off-canvas", "error", addr,
                    f"entirely outside the {w:g}x{h:g}{canvas.get('unit', '')} canvas",
                    box=box)
            elif x0 < -1e-9 or y0 < -1e-9 or x1 > w + 1e-9 or y1 > h + 1e-9:
                add("off-canvas", "warning", addr,
                    f"crosses the canvas edge and will be clipped", box=box)

    if "label-overlap" in want or "separation" in want:
        labelled = set()
        for addr, el, _p in model.walk(doc):
            if "label" in (el.get("tags") or []):
                labelled.add(addr)
        leaves = []
        for addr, el, _p in model.walk(doc):
            if el.get("type") in ("group", "guide") or not el.get("geometry"):
                continue
            try:
                runs = measure.runs_in_frame(doc, addr, page)
            except measure.Unmeasurable as e:
                unchecked.append({"rule": "label-overlap", "element": addr, "why": str(e)})
                continue
            if geometry.bounds(runs):
                is_label = el.get("type") in _LABELLISH or any(
                    addr == l or addr.startswith(l + ".") for l in labelled)
                leaves.append((addr, runs, is_label))
        # DRAWING ORDER, so the overlap check can see a backing plate. Elements are painted
        # in document order, so something opaque drawn after a line and before a label hides
        # that line where the label sits. Without this, a legend on a plate -- the standard
        # fix for a legend over a grid -- is still reported as unreadable, and a check that
        # cannot see the fix for the thing it complains about gets worked around instead of
        # heeded.
        order = {addr: i for i, (addr, _e, _p) in enumerate(model.walk(doc))}
        covers = []
        for addr, el, _p in model.walk(doc):
            st_ = model.effective_style(doc, el)
            fill = st_.get("fill")
            if not fill or fill == "none":
                continue
            if float(st_.get("opacity", 1.0)) < 0.999:
                continue
            if not measure.encloses(doc, addr):
                continue
            try:
                box = measure.bbox(doc, addr, page)["value"]
            except (ValueError, KeyError, measure.Unmeasurable):
                continue
            covers.append((order[addr], addr, box))

        def hidden_by_a_plate(other, label, label_box):
            """Is `other` hidden BEHIND THE LABEL by something opaque drawn between them?

            The box that matters is the LABEL's, not the other element's. What makes text
            unreadable is ink inside the text's own footprint, so a plate has to cover that
            -- it does not have to cover the whole gridline, which runs the height of the
            panel. Asking the wrong one of the two meant a legend plate that plainly worked
            was never recognised.
            """
            lo, up = order.get(other, -1), order.get(label, -1)
            for i, addr, box in covers:
                if addr in (other, label) or not (lo < i < up):
                    continue
                if (box["x"] <= label_box["x"] + 1e-9
                        and box["y"] <= label_box["y"] + 1e-9
                        and box["x"] + box["width"] >= label_box["x"]
                        + label_box["width"] - 1e-9
                        and box["y"] + box["height"] >= label_box["y"]
                        + label_box["height"] - 1e-9):
                    return addr
            return None

        sep_pt = th["min_separation_pt"]
        sep = model.to_unit(sep_pt, "pt", canvas.get("unit", "mm"))
        for i in range(len(leaves)):
            ai, ar, a_label = leaves[i]
            pa = geometry.flatten(ar, tol)
            abox = geometry.bounds(ar)
            for j in range(i + 1, len(leaves)):
                bi, br, b_label = leaves[j]
                same_object = ai.split(".")[0] == bi.split(".")[0]
                care_overlap = ("label-overlap" in want) and (a_label or b_label)
                care_sep = ("separation" in want) and not same_object
                if not (care_overlap or care_sep):
                    continue
                bbox_ = geometry.bounds(br)
                if (abox[2] + sep < bbox_[0] or bbox_[2] + sep < abox[0]
                        or abox[3] + sep < bbox_[1] or bbox_[3] + sep < abox[1]):
                    continue
                pb = geometry.flatten(br, tol)
                # CROSSING, not containment. A caption sitting INSIDE the box it labels is
                # the normal case and the containment test called every one of them an
                # error; what makes text unreadable is ink running THROUGH it. So the label
                # rule asks whether the outlines actually cross -- a label wholly inside a
                # filled shape does not, a label half-on-half-off it does, and a label over
                # line work does.
                crossed = geometry.polys_overlap(pa, pb, a_closed=False, b_closed=False)
                if crossed or geometry.polys_overlap(
                        pa, pb, a_closed=measure.encloses(doc, ai),
                        b_closed=measure.encloses(doc, bi)):
                    if care_overlap and crossed:
                        if a_label and not b_label:
                            label, other, lbox = ai, bi, abox
                        elif b_label and not a_label:
                            label, other, lbox = bi, ai, bbox_
                        else:
                            label, other, lbox = (ai, bi, abox) \
                                if order.get(ai, 0) > order.get(bi, 0) else (bi, ai, bbox_)
                        plate = hidden_by_a_plate(other, label, geometry_box(lbox))
                        if plate is None:
                            add("label-overlap", "error", f"{ai} .. {bi}",
                                "a label and this cross; the text will be unreadable "
                                "where they do")
                        elif ("occluded" in want
                              and plate.rsplit(".", 1)[0] != other.rsplit(".", 1)[0]):
                            # SIBLINGS ARE THE LABEL'S OWN PLATE ON ITS OWN LINE, which is
                            # how every labelled edge in every diagram is drawn. Reporting
                            # it on each one buries the case that matters: a plate covering
                            # something that belongs to a different part of the figure.
                            # NOTHING IS SILENTLY EXCUSED. The plate makes the label
                            # readable and it also HIDES whatever was underneath, and those
                            # are different facts. A plate over a gridline is the standard
                            # fix; a plate over the data is a figure that has lost some of
                            # its data -- and the first legend drawn with this exemption in
                            # place was doing exactly that, invisibly, because the overlap
                            # it would have been reported for was now forgiven.
                            add("occluded", "warning", f"{plate} .. {other}",
                                f"{plate} covers {other} where {label} sits; that is what "
                                f"makes the label readable, and it hides what is under it")
                    continue
                if not care_sep:
                    continue
                gap = min(min(geometry.nearest_point(pb, p)[1] for p in poly)
                          for poly in pa if poly)
                gap_pt = model.to_unit(gap, canvas.get("unit", "mm"), "pt")
                if gap_pt < sep_pt - 1e-9:
                    add("separation", "warning", f"{ai} .. {bi}",
                        f"{gap_pt:.2f}pt apart, below the {sep_pt:g}pt floor; they will "
                        f"merge in print", gap_pt=gap_pt, threshold_pt=sep_pt)

    if "colour-distinguishable" in want:
        # THE BACKGROUND IS NOT AN ENCODING. This rule asks whether two colours that mean
        # different things can be told apart; the page itself means nothing, and a surface
        # tint is *supposed* to be barely distinguishable from it. Comparing every colour in
        # the scene against the paper reported that as a defect on every figure with a tint
        # on it.
        inv = measure.inventory(doc)["value"]["colours"]
        cols = [c for c in inv if _rgb(c) and _rgb(c) != bg_rgb]
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                a, b = cols[i], cols[j]
                if (_delta_e(a, b) or 0) < th["delta_e"]:
                    add("colour-distinguishable", "warning", f"{a} .. {b}",
                        f"these two are {_delta_e(a, b):.1f} apart in Lab, below "
                        f"{th['delta_e']:g}; they read as one colour",
                        delta_e=_delta_e(a, b), vision="normal")
                    continue
                for kind in _CVD:
                    sa, sb = simulate(a, kind), simulate(b, kind)
                    d = _delta_e(sa, sb)
                    if d is not None and d < th["delta_e"]:
                        add("colour-distinguishable", "warning", f"{a} .. {b}",
                            f"indistinguishable under {kind}: {sa} vs {sb}, "
                            f"{d:.1f} apart in Lab", delta_e=d, vision=kind,
                            simulated=[sa, sb])
                        break

    if "accessibility" in want:
        # §3.14's "accessibility metadata completeness". A figure that carries no description
        # is unusable to a reader who cannot see it, and nothing about the geometry says so
        # -- which is exactly why it has to be a check rather than a habit.
        if not (doc.get("title") or "").strip():
            add("accessibility", "warning", None,
                "this figure has no title; a reader who cannot see it has nothing to go on")
        if not (doc.get("description") or "").strip():
            add("accessibility", "warning", None,
                "this figure has no description; the geometry cannot supply one and "
                "nothing else will")
        for addr, el, _p in model.walk(doc):
            g = el.get("geometry") or {}
            if g.get("kind") == "image" and not (el.get("description") or "").strip():
                add("accessibility", "warning", addr,
                    f"an embedded image with no description: {g.get('href')!r}")

    if "unsolved" in want:
        if solve_report is None:
            unchecked.append({"rule": "unsolved", "element": None,
                              "why": "no solve report was supplied, so whether this "
                                     "figure's relations are satisfied is unknown"})
        else:
            for item in solve_report.get("unsatisfiable", []):
                add("unsolved", "error", item.get("element"),
                    f"{item.get('kind')} to {item.get('to')}: {item.get('why')}")
            for item in solve_report.get("unsettled", []):
                add("unsolved", "error", item.get("element"),
                    f"{item.get('kind')} to {item.get('to')} never settled, still "
                    f"{item.get('short_by'):.4g} short")
            for item in (solve_report.get("anchors") or {}).get("unresolvable", []):
                add("unsolved", "error", item.get("anchor"), item.get("why"))

    out = _collapse(out)
    order = {"error": 0, "warning": 1}
    out.sort(key=lambda f: (order.get(f["severity"], 2), f["rule"], f["element"] or ""))
    return {"findings": out, "unchecked": unchecked, "thresholds": th,
            "canvas": {"width": canvas.get("width"), "height": canvas.get("height"),
                       "unit": canvas.get("unit"), "background": bg},
            "errors": sum(1 for f in out if f["severity"] == "error"),
            "warnings": sum(1 for f in out if f["severity"] == "warning")}
