"""Scene to SVG. The export, never the source.

Principle 1 of the spec is that the scene is the source of truth and SVG is an export, which
puts one obligation on this module: **nothing here may be the only place something is
recorded.** The SVG carries element addresses as ids and keeps the group structure, so a
person opening the file can see what they are looking at -- but it is written to be thrown
away and made again, and no tool in this toolkit reads it back.

The output is deterministic: numbers are rounded at a stated precision, attributes are
written in a fixed order, and nothing carries a timestamp.
"""
from . import model

__all__ = ["render", "PRECISION"]

PRECISION = 3

_DEFAULTS = {"path": {"stroke": "#111111", "fill": "none"},
             "region": {"stroke": "none", "fill": "#111111"},
             "text": {"stroke": "none", "fill": "#111111"}}

_ATTR = [("fill", "fill"), ("fill_rule", "fill-rule"), ("stroke", "stroke"),
         ("stroke_width", "stroke-width"), ("stroke_cap", "stroke-linecap"),
         ("stroke_join", "stroke-linejoin"), ("stroke_dash", "stroke-dasharray"),
         ("opacity", "opacity"), ("font_family", "font-family"),
         ("font_size", "font-size"), ("font_weight", "font-weight")]


def _n(x, places=PRECISION):
    v = round(float(x), places)
    if v == 0:
        v = 0.0
    return str(int(v)) if v == int(v) and abs(v) < 1e15 else repr(v)


def _d(segs, places):
    out = []
    for s in segs:
        verb, nums = s[0], s[1:]
        out.append(verb if not nums else verb + " " + " ".join(_n(x, places) for x in nums))
    return " ".join(out)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _style_of(doc, el):
    """The style an element draws with: the toolkit's defaults, then role, then literals.

    A literal override is legal and is what the tracer necessarily produces -- it recovers a
    colour and has no idea what the colour MEANS. §3.11's job is turning those into roles;
    this one's is drawing what is there. The role-then-literal part is `model.effective_style`,
    shared with the measurer and the checker so that what is drawn, what is measured and what
    is checked cannot be three different things.
    """
    out = dict(_DEFAULTS.get(el.get("type"), {}))
    out.update(model.effective_style(doc, el))
    return out


def _attrs(doc, el, frame, places):
    st = _style_of(doc, el)
    geom = el.get("geometry") or {}
    if geom.get("fill_rule"):
        st.setdefault("fill_rule", geom["fill_rule"])
    bits = []
    for key, name in _ATTR:
        if key not in st:
            continue
        v = st[key]
        if key in ("stroke_width", "font_size"):
            v = _n(model.resolve_length(doc, v, frame), places)
        elif key == "stroke_dash":
            v = ",".join(_n(model.resolve_length(doc, x, frame), places) for x in v)
        bits.append(f'{name}="{_esc(v)}"')
    return bits


def _element(doc, addr, el, frame, prefix, places, out, depth):
    pad = "  " * depth
    kind = el.get("type")
    if kind == "guide":
        return                                   # construction geometry never renders
    own_frame = el.get("frame") or frame
    head = [f'id="{_esc(prefix + addr)}"']
    t = []
    if own_frame != frame:
        # The RELATIVE matrix between the two frames, not this frame's own transform. With a
        # frame chain deeper than one, its own transform is only the last step of the way to
        # the page, so emitting it drew the element in the wrong place -- and measurement,
        # which composes the whole chain, disagreed with the drawing.
        m = model.frame_between(doc, frame, own_frame)
        if [round(v, 12) for v in m] != list(model.IDENTITY):
            t.append("matrix(" + " ".join(_n(x, 6) for x in m) + ")")
    if el.get("transform"):
        t.append("matrix(" + " ".join(_n(x, 6) for x in el["transform"]) + ")")
    if t:
        head.append(f'transform="{" ".join(t)}"')

    if kind == "group":
        out.append(f"{pad}<g {' '.join(head)}>")
        for kid in el.get("children") or []:
            _element(doc, f"{addr}.{kid['name']}", kid, own_frame, prefix, places, out,
                     depth + 1)
        out.append(f"{pad}</g>")
        return

    geom = el.get("geometry") or {}
    attrs = head + _attrs(doc, el, own_frame, places)
    if geom.get("kind") == "path":
        d = _d(geom.get("d") or [], places)
        if geom.get("closed") and not (geom.get("d") or [[""]])[-1][0] == "Z":
            d += " Z"
        out.append(f'{pad}<path {" ".join(attrs)} d="{d}"/>')
    elif geom.get("kind") == "region":
        d = " ".join(_d(loop, places) for loop in geom.get("loops") or [])
        out.append(f'{pad}<path {" ".join(attrs)} d="{d}"/>')
    elif geom.get("kind") == "text":
        x, y = geom["at"]
        anc = {"start": "start", "middle": "middle", "end": "end"}.get(
            geom.get("align", "start"), "start")
        out.append(f'{pad}<text {" ".join(attrs)} x="{_n(x, places)}" y="{_n(y, places)}" '
                   f'text-anchor="{anc}">{_esc(geom["text"])}</text>')
    elif geom.get("kind") == "image":
        out.append(f'{pad}<image {" ".join(head)} href="{_esc(geom["href"])}" '
                   f'x="{_n(geom["at"][0], places)}" y="{_n(geom["at"][1], places)}" '
                   f'width="{_n(geom["width"], places)}" '
                   f'height="{_n(geom["height"], places)}"/>')
    elif geom.get("kind") == "glyph":
        raise NotImplementedError(
            f"{addr}: glyph instances are §3.7 and are not built; refusing to draw a "
            f"placeholder that would look like the figure was complete")


def render(doc, standalone=True, prefix="", places=PRECISION, background=None):
    """The scene as SVG text.

    `standalone` wraps it in an ``<svg>`` sized in the canvas's own physical units, so the
    file opens at the size the figure is meant to be printed -- the thing §3.13 asks for and
    the thing a raster export at "final physical size" needs. Set it False for a bare ``<g>``
    to inline, in which case `prefix` is what keeps ids from colliding with the host
    document's.
    """
    canvas = doc["canvas"]
    page = model._page_frame(doc)
    out = []
    body = []
    for el in doc.get("elements", []):
        _element(doc, el["name"], el, page, prefix, places, body, 1 if standalone else 1)
    bg = background if background is not None else canvas.get("background", "none")
    if standalone:
        w, h, u = canvas["width"], canvas["height"], canvas["unit"]
        # THE CAMERA, when a timeline has moved one. `canvas.viewbox` is the window onto the
        # page; without it the window is the whole page. It was written by the animation
        # module and read by nothing -- so a camera track produced a field the exporter
        # ignored AND a scene the validator refused. A property nobody reads is the defect
        # this repository keeps finding; this one had it twice over.
        vb = canvas.get("viewbox") or [0, 0, w, h]
        out.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                   f'width="{_n(w, places)}{u}" height="{_n(h, places)}{u}" '
                   f'viewBox="{" ".join(_n(v, places) for v in vb)}">')
        if bg and bg != "none":
            out.append(f'  <rect x="0" y="0" width="{_n(w, places)}" '
                       f'height="{_n(h, places)}" fill="{_esc(bg)}"/>')
        out += body
        out.append("</svg>")
    else:
        out.append(f'<g id="{_esc(prefix + doc["name"])}">')
        out += body
        out.append("</g>")
    return "\n".join(out) + "\n"
