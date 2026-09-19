"""The annotated overlay: §3.15, split into a producer and a VIEW.

**A view is a pure function from a payload to markup, and it may not COMPUTE.** That second
half is the one this module was rewritten for. The first version drew the right picture and
was not a view: it measured every bounding box itself, which means a number a person reads
off the overlay would have been computed in a second place, by a second code path, able to
disagree with the measurement the rest of the toolkit reports. A view that computes is a
second source of truth wearing a picture.

So there are two halves here and the split is the point:

:func:`payload`   the PRODUCER. Measures the scene and returns a `lineart.overlay/1`
                  document: every box, anchor and relation already resolved into page
                  coordinates, and the art already exported to markup.
:func:`render`    the VIEW. Takes that payload and returns SVG. It performs no I/O, reads no
                  store, measures nothing, and imports nothing that could.

**Absence is not emptiness.** Any section of the payload may instead be
``{"unavailable": "why"}``, and the view draws a visible note saying so. A layer that could
not be gathered rendered as a layer with nothing in it is the failure this rule exists to
stop: an empty section looks exactly like good news.
"""
__all__ = ["payload", "render", "LAYERS", "PAYLOAD_SCHEMA_PATH"]

import os

LAYERS = ("art", "grid", "canvas", "boxes", "names", "anchors", "relations", "findings",
          "roles", "order")

PAYLOAD_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "overlay.schema.json")

_INK = {"grid": "#d8e2ef", "canvas": "#b0bcc9", "box": "#2f6fd0", "name": "#1a4a94",
        "anchor": "#d2521e", "relation": "#7a3fbf", "error": "#c22c2c",
        "warning": "#b8860b", "note": "#6b7280"}


# ===================================================================== producer
def payload(scene, grid=10.0, findings=None, include_art=True, depth=2):
    # DEPTH DEFAULTS TO 2, and an overlay is the one place where a default that hides
    # something is the right one. The first version drew every element at every level: a
    # DNA duplex of thirteen rungs put thirteen labels on the same line of the picture, over
    # each other, over the art. An inspection tool nobody can read has failed at the only
    # thing it does. `depth=None` still gives everything, and the payload carries the depth
    # it used so the view can say the picture is partial -- which is the difference between
    # a filtered overlay and a wrong one.
    """Everything an overlay needs, measured once, in page coordinates.

    Not a view: this measures. It is the producer half, and it is what guarantees the
    numbers on the overlay are the same numbers `scene.measure` reports -- they come from
    the same call. `depth` limits how deep into the tree it goes; None is all of it.
    """
    from . import measure, model, svg

    canvas = scene.get("canvas") or {}
    page = model._page_frame(scene)
    out = {
        "format": "lineart.overlay/1",
        "canvas": {"width": float(canvas.get("width", 0)),
                   "height": float(canvas.get("height", 0)),
                   "unit": canvas.get("unit", "mm"),
                   "background": canvas.get("background", "none")},
    }
    if scene.get("name"):
        out["scene"] = scene["name"]
    out["grid"] = {"step": float(grid)} if grid and grid > 0 else \
        {"unavailable": "no grid step was asked for"}

    if include_art:
        try:
            out["art"] = {"markup": svg.render(scene, standalone=False, prefix="art-")}
        except NotImplementedError as e:
            out["art"] = {"unavailable": f"the scene contains something that cannot be "
                                         f"drawn: {e}"}
    else:
        out["art"] = {"unavailable": "the art layer was not asked for"}

    out["depth"] = depth
    if scene.get("title"):
        out["title"] = scene["title"]
    order = {a: i for i, (a, _e, _p) in enumerate(model.walk(scene))}
    used = {}
    for _addr, el, _p in model.walk(scene):
        if el.get("role"):
            used[el["role"]] = used.get(el["role"], 0) + 1
    defined = ((scene.get("style") or {}).get("roles") or {})
    out["roles"] = [{"role": r, "count": n, "style": defined.get(r) or {},
                     "in_guide": r in defined}
                    for r, n in sorted(used.items())] or {
        "unavailable": "nothing in this scene asks for a role"}
    # The label size, and whether each label FITS, are decided here rather than in the view:
    # deciding needs text metrics, metrics need the font file, and a view may not open one.
    # This is the same split as everything else in this payload -- the producer measures,
    # the view draws what it is told.
    fs = max(out["canvas"]["width"], out["canvas"]["height"], 1.0) / 60.0
    out["label_size"] = fs
    boxes, unmeasurable = [], []
    for addr, el, _p in model.walk(scene):
        if not (el.get("geometry") or el.get("children")):
            continue
        if depth is not None and addr.count(".") + 1 > depth:
            continue
        try:
            v = measure.bbox(scene, addr, page)["value"]
        except measure.Unmeasurable as e:
            unmeasurable.append(f"{addr}: {e}")
            continue
        except (ValueError, KeyError) as e:
            unmeasurable.append(f"{addr}: {e}")
            continue
        boxes.append({"address": addr, "type": el.get("type"), "x": v["x"], "y": v["y"],
                      "width": v["width"], "height": v["height"],
                      "label": _label_fits(addr, fs, v["width"]),
                      # §3.15 asks the overlay to show z-order and style roles as well as
                      # names and boxes. They were the two items of that list this payload
                      # did not carry, so the view could not have drawn them.
                      "order": order.get(addr),
                      "role": el.get("role"),
                      "depth": addr.count(".") + 1,
                      "style": {k: v_ for k, v_ in
                                sorted(model.effective_style(scene, el).items())},
                      "tags": sorted(el.get("tags") or []),
                      "anchors": sorted((el.get("anchors") or {}))})
    # § 7.5: absence must not render as emptiness. A scene where nothing could be measured
    # gets a section that SAYS so; one where some of it could gets the boxes it has, and the
    # rest is named in the note the view draws.
    out["boxes"] = boxes if boxes else {
        "unavailable": "nothing in this scene could be measured"
        + (": " + "; ".join(unmeasurable[:3]) if unmeasurable else "")}

    anchors_ = []
    for addr, el, _p in model.walk(scene):
        if depth is not None and addr.count(".") + 1 > depth:
            continue
        for name, a in sorted((el.get("anchors") or {}).items()):
            if "at" not in a:
                anchors_.append({"address": addr, "name": name, "unresolved": True})
                continue
            m = model.compose(model.invert(model.frame_to_page(scene, page)),
                              model.element_to_page(scene, addr))
            x, y = model.apply(m, a["at"][0], a["at"][1])
            entry = {"address": addr, "name": name, "x": x, "y": y,
                     "how": a.get("how", "authored")}
            d = a.get("dir")
            if d:
                n = (d[0] ** 2 + d[1] ** 2) ** 0.5 or 1.0
                entry["dx"], entry["dy"] = d[0] / n, d[1] / n
            anchors_.append(entry)
    out["anchors"] = anchors_

    by_addr = {b["address"]: b for b in boxes}
    rels = []
    for addr, el, _p in model.walk(scene):
        for rel in el.get("relations") or []:
            a = by_addr.get(addr)
            t = by_addr.get(rel["to"]) or by_addr.get(rel["to"].rsplit(".", 1)[0])
            if not a or not t:
                rels.append({"from": addr, "to": rel["to"],
                             "kind": rel.get("kind", "attach"), "unresolved": True})
                continue
            rels.append({"from": addr, "to": rel["to"], "kind": rel.get("kind", "attach"),
                         "x0": a["x"] + a["width"] / 2.0, "y0": a["y"] + a["height"] / 2.0,
                         "x1": t["x"] + t["width"] / 2.0, "y1": t["y"] + t["height"] / 2.0})
    out["relations"] = rels

    if findings is None:
        out["findings"] = {"unavailable": "no verification was run, so whether this figure "
                                          "is correct is unknown"}
    else:
        marked = []
        for f in findings:
            b = by_addr.get(f.get("element") or "")
            entry = {"rule": f.get("rule"), "severity": f.get("severity"),
                     "element": f.get("element"), "message": f.get("message")}
            if b:
                entry.update({"x": b["x"], "y": b["y"], "width": b["width"],
                              "height": b["height"]})
            marked.append(entry)
        out["findings"] = marked
    if unmeasurable and isinstance(out["boxes"], list):
        out["unmeasured"] = unmeasurable
    return out


def _label_fits(addr, size, width, family="Courier New"):
    """Would this address, drawn at `size`, fit across a box this wide?

    A monospace family, because the view draws these in `monospace` and a proportional
    measurement of a monospaced rendering is the wrong number. When the family is not on this
    machine, 0.6 em per character is used -- narrower than most monospace faces, so the
    estimate errs towards drawing the label rather than towards hiding one that would have
    fitted.
    """
    from . import fonts
    try:
        advance = fonts.metrics(addr, family, size)["advance"]
    except fonts.FontNotFound:
        advance = 0.6 * size * len(addr)
    return advance <= width * 1.35


# ===================================================================== the view
def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _n(x, places=3):
    v = round(float(x), places)
    if v == 0:
        v = 0.0
    return str(int(v)) if v == int(v) and abs(v) < 1e15 else repr(v)


def _unavailable(section):
    return isinstance(section, dict) and "unavailable" in section


def render(payload_, layers=LAYERS, scale=1.0, label_size=None):
    """The payload as an annotated SVG document. A pure function; it performs no I/O.

    Everything drawn arrives in `payload_`. Nothing here opens a file, reads a scene or
    measures a curve, which is what lets this be rendered from a fixture and compared as a
    string.

    C11:
      type: view
      noun: overlay
      verb: render
      tags: overlay, view, annotation, preview, anchors, names
      binds: scene.overlay-payload
      returns: an annotated SVG document for one payload; performs no I/O
      phrases:
        - render the annotated overlay
        - draw a scene's names boxes and anchors
        - the inspection view of a figure
        - show a figure's structure over the figure
      requires:
        - lineart_trace/scene/overlay.py: the render function; payload in, markup out
    """
    canvas = payload_["canvas"]
    w, h, unit = canvas["width"], canvas["height"], canvas.get("unit", "mm")
    fs = float(label_size if label_size is not None
               else payload_.get("label_size") or max(w, h, 1.0) / 60.0)
    thin = max(w, h, 1.0) / 1200.0
    notes = []

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'width="{_n(w * scale)}{unit}" height="{_n(h * scale)}{unit}" '
           f'viewBox="0 0 {_n(w)} {_n(h)}">',
           f'  <rect x="0" y="0" width="{_n(w)}" height="{_n(h)}" fill="#ffffff"/>']

    grid = payload_.get("grid")
    if "grid" in layers:
        if _unavailable(grid):
            notes.append(("grid", grid["unavailable"]))
        elif grid and grid.get("step"):
            step = float(grid["step"])
            out.append(f'  <g id="overlay-grid" stroke="{_INK["grid"]}" '
                       f'stroke-width="{_n(thin)}" fill="none">')
            x = 0.0
            while x <= w + 1e-9:
                out.append(f'    <path d="M {_n(x)} 0 L {_n(x)} {_n(h)}"/>')
                x += step
            y = 0.0
            while y <= h + 1e-9:
                out.append(f'    <path d="M 0 {_n(y)} L {_n(w)} {_n(y)}"/>')
                y += step
            out.append("  </g>")

    art = payload_.get("art")
    if "art" in layers:
        if _unavailable(art):
            notes.append(("art", art["unavailable"]))
        elif art and art.get("markup"):
            out.append('  <g id="overlay-art" opacity="0.3">')
            out.append("\n".join("  " + l for l in art["markup"].strip().splitlines()))
            out.append("  </g>")

    if "canvas" in layers:
        out.append(f'  <rect id="overlay-canvas" x="0" y="0" width="{_n(w)}" '
                   f'height="{_n(h)}" fill="none" stroke="{_INK["canvas"]}" '
                   f'stroke-width="{_n(thin * 2)}" '
                   f'stroke-dasharray="{_n(fs / 2)},{_n(fs / 3)}"/>')

    boxes = payload_.get("boxes")
    if _unavailable(boxes):
        if "boxes" in layers or "names" in layers:
            notes.append(("boxes", boxes["unavailable"]))
        boxes = []
    if "boxes" in layers and boxes:
        out.append(f'  <g id="overlay-boxes" fill="none" stroke="{_INK["box"]}" '
                   f'stroke-width="{_n(thin * 1.5)}">')
        for b in boxes:
            dash = f' stroke-dasharray="{_n(fs / 4)},{_n(fs / 4)}"' \
                if b.get("type") == "group" else ""
            out.append(f'    <rect x="{_n(b["x"])}" y="{_n(b["y"])}" '
                       f'width="{_n(b["width"])}" height="{_n(b["height"])}"{dash}/>')
        out.append("  </g>")
    if "order" in layers and boxes:
        out.append(f'  <g id="overlay-order" fill="{_INK["name"]}" '
                   f'font-family="monospace" font-size="{_n(fs * 0.7)}" opacity="0.75">')
        for b in boxes:
            if b.get("order") is None:
                continue
            out.append(f'    <text x="{_n(b["x"] + b["width"] - fs * 0.2)}" '
                       f'y="{_n(b["y"] + b["height"] - fs * 0.2)}" '
                       f'text-anchor="end">{b["order"]}</text>')
        out.append("  </g>")

    if "roles" in layers and boxes:
        shown = 0
        out.append(f'  <g id="overlay-roles" fill="{_INK["relation"]}" '
                   f'font-family="monospace" font-size="{_n(fs * 0.75)}">')
        for b in boxes:
            if not b.get("role") or b.get("label") is False:
                continue
            shown += 1
            out.append(f'    <text x="{_n(b["x"])}" '
                       f'y="{_n(b["y"] + b["height"] + fs * 0.9)}">'
                       f'{_esc(b["role"])}</text>')
        out.append("  </g>")
        if not shown:
            notes.append(("roles", "nothing here asks for a role by a name that fits"))

    if "names" in layers and boxes:
        out.append(f'  <g id="overlay-names" fill="{_INK["name"]}" '
                   f'font-family="monospace" font-size="{_n(fs)}">')
        hidden = 0
        for b in boxes:
            if b.get("label") is False:
                hidden += 1
                continue
            out.append(f'    <text x="{_n(b["x"])}" y="{_n(b["y"] - fs * 0.3)}">'
                       f'{_esc(b["address"])}</text>')
        if hidden:
            notes.append(("names", f"{hidden} name(s) whose box is too narrow to hold "
                                   f"them; their boxes are still drawn"))
        out.append("  </g>")

    anchors_ = payload_.get("anchors")
    if "anchors" in layers:
        if _unavailable(anchors_):
            notes.append(("anchors", anchors_["unavailable"]))
        elif anchors_:
            out.append(f'  <g id="overlay-anchors" stroke="{_INK["anchor"]}" '
                       f'fill="{_INK["anchor"]}" stroke-width="{_n(thin * 1.5)}">')
            for a in anchors_:
                if a.get("unresolved"):
                    continue
                x, y, r = a["x"], a["y"], fs * 0.28
                out.append(f'    <circle cx="{_n(x)}" cy="{_n(y)}" r="{_n(r)}" '
                           f'fill="none"/>')
                out.append(f'    <circle cx="{_n(x)}" cy="{_n(y)}" r="{_n(r / 3)}"/>')
                if "dx" in a:
                    out.append(f'    <path fill="none" d="M {_n(x)} {_n(y)} '
                               f'L {_n(x + a["dx"] * fs)} {_n(y + a["dy"] * fs)}"/>')
                out.append(f'    <text x="{_n(x + r * 1.5)}" y="{_n(y - r)}" '
                           f'stroke="none" font-family="monospace" '
                           f'font-size="{_n(fs * 0.8)}">{_esc(a["name"])}</text>')
            out.append("  </g>")

    rels = payload_.get("relations")
    if "relations" in layers:
        if _unavailable(rels):
            notes.append(("relations", rels["unavailable"]))
        elif rels:
            out.append(f'  <g id="overlay-relations" stroke="{_INK["relation"]}" '
                       f'fill="none" stroke-width="{_n(thin * 1.5)}" '
                       f'stroke-dasharray="{_n(fs / 3)},{_n(fs / 4)}">')
            for r in rels:
                if r.get("unresolved"):
                    continue
                out.append(f'    <path d="M {_n(r["x0"])} {_n(r["y0"])} '
                           f'L {_n(r["x1"])} {_n(r["y1"])}"/>')
                out.append(f'    <text x="{_n((r["x0"] + r["x1"]) / 2)}" '
                           f'y="{_n((r["y0"] + r["y1"]) / 2)}" stroke="none" '
                           f'fill="{_INK["relation"]}" font-family="monospace" '
                           f'font-size="{_n(fs * 0.8)}">{_esc(r["kind"])}</text>')
            out.append("  </g>")

    findings = payload_.get("findings")
    if "findings" in layers:
        if _unavailable(findings):
            notes.append(("findings", findings["unavailable"]))
        elif findings:
            out.append(f'  <g id="overlay-findings" fill="none" '
                       f'stroke-width="{_n(thin * 3)}">')
            for f in findings:
                ink = _INK.get(f.get("severity"), _INK["note"])
                if "x" in f:
                    pad = fs * 0.3
                    out.append(f'    <rect x="{_n(f["x"] - pad)}" y="{_n(f["y"] - pad)}" '
                               f'width="{_n(f["width"] + 2 * pad)}" '
                               f'height="{_n(f["height"] + 2 * pad)}" stroke="{ink}"/>')
            out.append("  </g>")
            out.append(f'  <g id="overlay-findings-text" font-family="monospace" '
                       f'font-size="{_n(fs * 0.85)}">')
            for i, f in enumerate(findings):
                ink = _INK.get(f.get("severity"), _INK["note"])
                out.append(f'    <text x="{_n(fs * 0.5)}" '
                           f'y="{_n(h - fs * 0.6 - fs * 1.15 * (len(findings) - 1 - i))}" '
                           f'fill="{ink}">{_esc(f.get("severity", "?"))}: '
                           f'{_esc(f.get("message", ""))}</text>')
            out.append("  </g>")

    if payload_.get("depth"):
        notes.append(("depth", f"{payload_['depth']} level(s) of the tree; deeper "
                               f"elements are in the scene but not drawn here"))

    if notes:
        # On a backing, and above everything, because these say what is NOT in the picture.
        # Drawn plainly over the art they were unreadable exactly where the picture was
        # busiest -- which is where somebody is reading them.
        band = fs * (0.6 + 1.15 * len(notes))
        out.append(f'  <g id="overlay-unavailable">')
        out.append(f'    <rect x="0" y="0" width="{_n(w)}" height="{_n(band)}" '
                   f'fill="#ffffff" fill-opacity="0.88"/>')
        out.append(f'    <g font-family="monospace" font-size="{_n(fs * 0.85)}" '
                   f'fill="{_INK["note"]}">')
        for i, (what, why) in enumerate(notes):
            out.append(f'      <text x="{_n(fs * 0.5)}" y="{_n(fs * (1.0 + 1.15 * i))}">'
                       f'{_esc(what)}: not shown &#8212; {_esc(why)}</text>')
        out.append("    </g>")
        out.append("  </g>")

    out.append("</svg>")
    return "\n".join(out) + "\n"
